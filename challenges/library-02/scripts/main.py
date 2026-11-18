#!/usr/bin/env python3
"""library-02 research file library -- pipeline: inventory, hash dedup, version chains, filtered
section-level search with quotes/backlinks, result.json (contract passthrough), inventory.csv,
version_chain.json, operations.log, verification. Partial first; exit code always 0."""
import argparse, csv, hashlib, json, math, os, re, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
  sys.path.insert(0, str(HERE))
try:
  import engine
except Exception:  # extraction must never kill the run
  engine = None

VERSION = "1.0.0"
TS = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
LOG = []
COLS = ("path role kind ext size sha256 mtime mode readable extract units project_id year doc_type "
    "version_label batch chain_id version_ordinal is_current dup_group meta_sources").split()
BK = ("sources directories files duplicates version_chains queries failures skipped permissions operations "
   "artifacts uncertainty pending_human errors degradations changes").split()
ACT = {"encrypted_pdf": "supply decrypted copy", "scanned_no_text_layer": "OCR or supply text layer",
       "image_no_text_layer": "OCR the image", "unsupported_legacy_office": "convert to OOXML",
       "permission_denied": "grant read permission"}


def log(op, **kw):
  LOG.append({"ts": TS(time.time()), "op": op, "detail": kw})


def jwrite(path, obj):
  path = Path(path)
  tmp = path.with_name(path.name + ".tmp")
  tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
  os.replace(tmp, path)


def sha(p):
  h = hashlib.sha256()
  with open(p, "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""):
      h.update(b)
  return h.hexdigest()


def paths(a):
  inp = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else Path.cwd() / "input")
  outp = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else Path.cwd() / "output")
  return inp, outp


def skel():
  r = {k: [] for k in BK}
  r.update(skill={"name": "research-file-library", "version": VERSION}, case_id=None, status="partial",
           status_note="partial written before scan; finalization pending", counts={}, index_stats={},
           verification={}, runtime={}, output_contract={}, output_contract_spec=None)
  return r




MAPS = ("version_chains=versionchain versions versionrel chain 版本关系 版本;duplicates=duplicate dedup alias 重复;"
    "permissions=permission access 权限;uncertainty=uncertain ambigu 不确定;pending_human=pending human manual 人工;"
    "metadata_summary=metadata 字段 元数据;queries=quer question search answer finding 检索 问答;"
    "operations=operation log evidence audit 操作 证据;failures=fail error skip 异常 失败 跳过;"
    "counts=count stat metric 计数;status=status state 状态;artifacts=artifact output deliverable 产物;"
    "summary=summary overview 摘要 概述;directories=dir folder tree structure 目录结构;"
    "files=inventory filelist listing catalog 清单 documents files 文件")
MAP = [(d.split("=")[0], d.split("=")[1].split()) for d in MAPS.split(";")]


def fillcon(con, res):
  if isinstance(con, list):
    con = {str(i.get("name") or i.get("field") or n): i for n, i in enumerate(con) if isinstance(i, dict)}
  if not isinstance(con, dict):
    return {}
  return {k: next((res.get(v) for v, pats in MAP if any(p in re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(k).lower())
                                                         for p in pats)), None) for k in con}




def scan_one(p, inp, res, a):
  rel = p.relative_to(inp).as_posix()
  rec = dict.fromkeys(COLS)
  rec.update({"path": rel, "name": p.name, "ext": p.suffix.lower(), "extract": "not_attempted", "units": 0,
              "is_current": True, "meta_sources": {}, "meta_evidence": {}, "admin_notes": [], "_units": [],
              "role": "input_contract" if p.name.lower() in ("case.json", "task.md") else "material"})
  try:
    st = p.stat()
    rec.update(size=st.st_size, mtime=TS(st.st_mtime), mode=oct(st.st_mode)[-4:], readable=os.access(p, os.R_OK))
  except Exception as e:
    res["failures"].append({"path": rel, "stage": "stat", "reason": str(e)[:120]})
    rec["extract"] = "stat_error"
    return rec
  try:
    rec["sha256"] = sha(p)
    raw = p.read_bytes()
  except Exception as e:
    perm = isinstance(e, PermissionError)
    rec["extract"] = "permission_denied" if perm else "read_error"
    (res["permissions"] if perm else res["failures"]).append(
      {"path": rel, "mode": rec["mode"], "stage": "read", "reason": str(e)[:120]})
    if perm:
      res["pending_human"].append({"item": rel, "action": ACT["permission_denied"]})
    return rec
  if not engine:
    rec["extract"] = "extraction_module_unavailable"
    return rec
  rec["kind"] = engine.kind_of(p, raw[:16])
  units, status, note = engine.units_of(p, raw, rec["kind"])
  md, pv = engine.meta(rec["name"], "\n".join(u["text"] for u in units)[:20000], st.st_mtime, TS)
  rec.update(md, extract=status, _units=units, meta_sources={k: v["source"] for k, v in pv.items()})
  rec["meta_evidence"] = {k: v["evidence"] for k, v in pv.items()}
  if note:
    rec["extract_note"] = note
  if status != "ok":
    res["pending_human"].append({"item": rel, "status": status, "action": ACT.get(status, "inspect manually")})
    res["degradations"].append({"capability": "text extraction", "path": rel, "status": status,
                                "effect": "inventoried and hashed but not searchable"})
  return rec






def scan(inp, res, a):
  files, items = [], []
  try:
    items = sorted(inp.rglob("*"), key=str)
  except Exception as e:
    res["errors"].append({"where": "list", "error": str(e)[:120]})
  for p in items:
    if p.is_symlink():
      res["skipped"].append({"path": str(p), "reason": "symlink_not_followed"})
    elif p.is_dir():
      try:
        cnt = sum(1 for c in p.iterdir() if c.is_file())
      except Exception:
        cnt = None
      res["directories"].append({"path": p.relative_to(inp).as_posix(), "n_files": cnt,
                                 "readable": os.access(p, os.R_OK)})
    else:
      try:
        files.append(scan_one(p, inp, res, a))
      except Exception as e:
        res["failures"].append({"path": str(p), "stage": "scan_one", "reason": str(e)[:120]})
  log("scan", files=len(files), directories=len(res["directories"]))
  return files




def link(files, res):
  g, grp = {}, {}
  for r in files:
    if r.get("sha256"):
      g.setdefault(r["sha256"], []).append(r)
    grp.setdefault((r.get("project_id") or "NA", engine.stem_key(r["name"])), []).append(r)
  n = 0
  for h, v in sorted(g.items()):
    if len(v) < 2:
      continue
    n += 1
    gid, canon = "dup-%02d" % n, sorted(v, key=lambda r: (len(r["path"]), r["mtime"] or ""))[0]
    for r in v:
      r["dup_group"], r["dup_of"] = gid, None if r is canon else canon["path"]
    res["duplicates"].append({"dup_group": gid, "sha256": h, "count": len(v), "canonical": canon["path"],
                              "paths": [r["path"] for r in v], "basis": "identical sha256: not independent evidence"})
  m = 0
  for key, v in sorted(grp.items()):
    if len(v) < 2:
      continue
    m += 1
    cid = "ver-%02d" % m
    lab = "version_label" if sum(engine.vord(r.get("version_label")) is not None for r in v) >= 2 else "mtime"
    order = sorted(v, key=(lambda r: (engine.vord(r.get("version_label")) or -1.0, r["mtime"] or "", r["path"]))
                   if lab == "version_label" else (lambda r: (r["mtime"] or "", r["path"])))
    top = order[-1].get("sha256")
    cur = next((r for r in order if r.get("sha256") == top and not r.get("dup_of")), order[-1])
    for i, r in enumerate(order):
      r.update(chain_id=cid, version_ordinal=i, is_current=(r is cur))
    mt = [r["mtime"] or "" for r in order]
    res["version_chains"].append({
      "chain_id": cid, "group_key": "%s|%s" % key, "ordering_basis": lab, "n_members": len(order),
      "distinct_contents": len({r.get("sha256") for r in order}),
      "timestamp_anomaly": "mtime_not_monotonic_with_labels" if lab != "mtime" and mt != sorted(mt) else None,
      "members": [{"path": r["path"], "label": r.get("version_label"), "sha256": (r.get("sha256") or "")[:16],
                   "mtime": r["mtime"], "extract": r["extract"], "ordinal": r["version_ordinal"],
                   "is_current": r["is_current"], "dup_group": r["dup_group"]} for r in order]})
  log("link", duplicate_groups=n, version_chains=m)








def build_index(files, res):
  segs = []
  for r in files:
    us = r.pop("_units", None) or []
    engine.sections(us)
    r["units"] = len(us)
    if r["role"] != "material":
      continue
    for u in us:
      if len(u["text"]) > 1:
        segs.append({"f": r["path"], "loc": u["loc"], "sec": u.get("sec", ""), "nt": engine.norm(u["text"]), "t": u["text"]})
  res["index_stats"] = {"searchable_units": len(segs), "chars": sum(len(x["t"]) for x in segs)}
  return segs




def search(q, files, segs, res, k):
  terms, f = engine.expand(q["query"]), engine.filters_of(q.get("obj"), q["query"])
  out = {"qid": q.get("qid") or "q%d" % (len(res["queries"]) + 1), "query": q["query"], "origin": q.get("origin"),
         "filters": f, "status": "ok", "hits": [], "candidates": 0, "filtered_out": 0, "notes": []}
  allow, dp = set(), {d: 0 for d in f}
  for r in files:
    bad = [d for d, v in f.items() if not engine.match_dim(r, d, v)]
    for d in f:
      dp[d] += d not in bad
    if bad:
      out["filtered_out"] += 1
    else:
      allow.add(r["path"])
  out["candidates"] = len(allow)
  out["notes"] = ["filter %r=%s: 0 files, not relaxed" % (d, f[d]) for d in f if dp[d] == 0]
  if not allow:
    out["status"] = "insufficient_evidence"
    out["notes"].append("every file was excluded by a hard filter")
    return out
  sub = [c for c in segs if c["f"] in allow]
  N = max(1, len(sub))
  idf = {t: math.log(1 + N / (1 + sum(1 for c in sub if t in c["nt"]))) for t in terms}
  scored = []
  for c in sub:
    fn, se, s, hit = engine.norm(c["f"].rsplit("/", 1)[-1]), engine.norm(c["sec"] or ""), 0.0, []
    for t, w in terms.items():
      n = c["nt"].count(t)
      if n:
        s += idf[t] * w * (1 + math.log(n)) * (1.8 if t in se else 1.0) * (1.4 if t in fn else 1.0)
        hit.append(t)
    if s > 0:
      scored.append((s, c, hit))
  scored.sort(key=lambda x: -x[0])
  recs, seen = {r["path"]: r for r in files}, set()
  for s, c, hit in scored:
    rec, h = recs.get(c["f"], {}), recs.get(c["f"], {}).get("sha256")
    if h and h in seen:
      continue
    seen.add(h)
    qt, a0, a1 = engine.quote_at(c["t"], hit)
    hint, frag = engine.loc_str(c["loc"], a0, a1, c["sec"])
    out["hits"].append({"rank": len(out["hits"]) + 1, "file": c["f"], "sha256": (h or "")[:16], "locator": c["loc"],
                        "section": c["sec"], "locator_hint": hint, "backlink": frag, "quote": qt,
                        "score": round(s, 3), "matched_terms": sorted(set(hit))[:24], "quote_verified": None,
                        "matched_primary": len({t for t in hit if terms.get(t) == 1.0}),
                        "dup_group": rec.get("dup_group"),
                        "version": {"chain": rec.get("chain_id"), "ordinal": rec.get("version_ordinal"),
                                    "is_current": rec.get("is_current"), "label": rec.get("version_label")},
                        "meta": {kk: rec.get(kk) for kk in ("project_id", "year", "doc_type")}})
    if len(out["hits"]) >= k:
      break
  if not out["hits"]:
    out["status"] = "insufficient_evidence"
    out["notes"].append("no candidate unit scored above zero")
  elif not any(h["matched_primary"] for h in out["hits"]):
    out["status"] = "partial"
    out["notes"].append("only synonym/expansion terms matched: weak hit")
  return out











def write_out(res, outp):
  def reg(p, note):
    res["artifacts"].append({"file": p.name, "path": str(p), "bytes": p.stat().st_size, "sha256": sha(p), "note": note})
    log("write", file=p.name)
  try:
    p = outp / "inventory.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
      w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
      w.writeheader()
      for r in res["files"]:
        w.writerow(dict({k: r.get(k) for k in COLS},
                        meta_sources="; ".join("%s:%s" % kv for kv in (r.get("meta_sources") or {}).items())))
    reg(p, "one row per input file; meta_sources = per-field provenance")
  except Exception as e:
    res["errors"].append({"where": "inventory.csv", "error": str(e)[:120]})
  try:
    p = outp / "version_chain.json"
    jwrite(p, {"version_chains": res["version_chains"], "duplicates": res["duplicates"]})
    reg(p, "version relations and alias groups")
  except Exception as e:
    res["errors"].append({"where": "version_chain.json", "error": str(e)[:120]})
  try:
    p = outp / "operations.log"
    p.write_text("".join("%s\t%s\t%s\n" % (x["ts"], x["op"], json.dumps(x["detail"], ensure_ascii=False, sort_keys=True))
                         for x in LOG), encoding="utf-8")
    reg(p, "operation trail")
  except Exception as e:
    res["errors"].append({"where": "operations.log", "error": str(e)[:120]})


def verify(res, inp):
  ch, tot, ok, cache = [], 0, 0, {}
  con = res.get("output_contract_spec")
  if isinstance(con, dict):
    miss = [k for k in con if k not in (res.get("output_contract") or {})]
    ch.append({"check": "output_contract_keys", "expected": len(con), "missing": miss, "pass": not miss})
  for q in res["queries"]:
    for h in q["hits"]:
      tot += 1
      if h["file"] not in cache:
        try:
          p = inp / h["file"]
          cache[h["file"]] = engine.units_of(p, p.read_bytes())[0] if engine and p.is_file() else []
        except Exception:
          cache[h["file"]] = []
      u = next((x for x in cache[h["file"]] if x["loc"] == h["locator"]), None)
      qq = re.sub(r"\s+", "", h.get("quote") or "")
      h["quote_verified"] = bool(u and qq and qq in re.sub(r"\s+", "", u["text"]))
      ok += h["quote_verified"]
      if not h["quote_verified"]:
        res["pending_human"].append({"item": h["file"], "locator": h["locator_hint"],
                                     "action": "quote not re-extractable at locator"})
  ch.append({"check": "quotes_re_extracted_at_locator", "total": tot, "verified": ok, "pass": ok == tot})
  return {"checks": ch, "pass": all(c["pass"] for c in ch), "note": "quotes re-extracted from source files"}










def cid(case, inp):
  if isinstance(case, dict):
    for k in ("case_id", "caseId", "case", "id", "name", "slug"):
      if isinstance(case.get(k), (str, int)) and str(case[k]).strip():
        return str(case[k])
  return inp.name or None


def run(a):
  t0 = time.time()
  inp, outp = paths(a)
  res = skel()
  try:
    outp.mkdir(parents=True, exist_ok=True)
  except Exception as e:
    res["errors"].append({"where": "mkdir", "error": str(e)[:100]})
  case, cp = {}, None
  if inp.is_dir():
    cands = sorted(inp.glob("case*.json"))
    cp = next((p for p in cands if p.name in ("case.json", "input.json", "task.json")), cands[0] if cands else None)
  if cp:
    try:
      case = json.loads(cp.read_text(encoding="utf-8", errors="replace"))
      res["sources"].append({"path": str(cp), "sha256": sha(cp), "bytes": cp.stat().st_size, "role": "input_contract"})
    except Exception as e:
      res["errors"].append({"where": "parse:" + cp.name, "error": str(e)[:120]})
      res["degradations"].append({"capability": "case contract", "status": "unparsable JSON", "effect": "contract empty"})
  else:
    res["errors"].append({"where": "discover", "error": "no case.json under %s" % inp})
    res["degradations"].append({"capability": "case contract", "status": "case.json missing", "effect": "contract empty"})
  con = case.get("output_contract") if isinstance(case, dict) else None
  res["output_contract_spec"] = con
  res["case_id"] = next((str(case[k]) for k in ("case_id", "caseId", "case", "id")
                         if isinstance(case, dict) and case.get(k) not in (None, "")), inp.name or None)
  res["output_contract"] = fillcon(con, res)
  jwrite(outp / "result.json", res)
  try:
    res["files"] = files = scan(inp, res, a)
    if engine:
      engine.apply_notes(files, case, res)
    link(files, res)
    qs = [{"qid": "", "query": x.strip(), "origin": "cli"} for x in a.query if x.strip()]
    if not qs and engine:
      engine.walk_q(case, qs)
    segs = build_index(files, res)
    res["queries"] = [search(q, files, segs, res, a.top_k) for q in qs[:40]]
  except Exception as e:
    res["errors"].append({"where": "pipeline", "error": str(e)[:120], "trace": traceback.format_exc()[-250:]})
  try:
    files = res["files"]
    res["counts"] = dict(files=len(files), directories=len(res["directories"]),
                         extracted_ok=sum(r["extract"] == "ok" for r in files),
                         not_searchable=sum(r["extract"] != "ok" for r in files),
                         duplicate_groups=len(res["duplicates"]), version_chains=len(res["version_chains"]),
                         queries=len(res["queries"]), hits=sum(len(q["hits"]) for q in res["queries"]),
                         no_hit=sum(1 for q in res["queries"] if not q["hits"]),
                         failures=len(res["failures"]), skipped=len(res["skipped"]),
                         permission_denied=len(res["permissions"]), pending_human=len(res["pending_human"]))
    res["status"] = "input_error" if not files else ("partial" if res["errors"] else "ok")
    res["status_note"] = ("no files under %s" % inp if not files else
                          "%d error(s); delivered parts stay valid" % len(res["errors"]) if res["errors"] else
                          "%d files, %d chains, %d duplicate groups, %d question(s)" % (
                            len(files), len(res["version_chains"]), len(res["duplicates"]), len(res["queries"])))
    write_out(res, outp)
    if not a.skip_verify:
      res["verification"] = verify(res, inp)
      if not res["verification"]["pass"]:
        res["status"] = "partial"
        res["status_note"] += "; see verification.checks"
    res["operations"] = LOG[-2000:]
    res["runtime"] = {"started": TS(t0), "finished": TS(time.time()), "ms": int((time.time() - t0) * 1000),
                      "python": sys.version.split()[0], "input": str(inp), "output": str(outp)}
    res["output_contract"] = fillcon(res["output_contract_spec"], res)
  except Exception:
    res["errors"].append({"where": "finalize", "error": traceback.format_exc()[-250:]})
    res["status"], res["status_note"] = "partial", "finalization error; partial result kept"
  try:
    jwrite(outp / "result.json", res)
  except Exception:
    pass








def main(argv=None):
  ap = argparse.ArgumentParser(prog="main.py", description="Research file library: inventory, hash dedup, "
                               "version chains, section-level filtered search with quotes and backlinks.",
                               )
  ap.add_argument("--input"); ap.add_argument("--output")
  ap.add_argument("--query", action="append", default=[], help="extra question")
  ap.add_argument("--top-k", type=int, default=5, help="hits per question")
  ap.add_argument("--skip-verify", action="store_true", help="skip verification")
  ap.add_argument("--version", action="version", version=VERSION)
  a = ap.parse_args(argv)
  try:
    run(a)
  except Exception:
    try:
      inp, outp = paths(a)
      outp.mkdir(parents=True, exist_ok=True)
      r = skel()
      r["errors"].append({"where": "fatal", "error": traceback.format_exc()[-800:]})
      r["status"], r["status_note"] = "partial", "fatal error before finalization"
      jwrite(outp / "result.json", r)
    except Exception:
      pass
  return 0








if __name__ == "__main__":
  sys.exit(main())
