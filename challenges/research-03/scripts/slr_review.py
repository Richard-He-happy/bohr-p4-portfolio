#!/usr/bin/env python3
"""SLR stage 1/2 (stdlib): discovery and parsing (PDF/DOCX/JSON/CSV/MD/TXT), question
decomposition, term refinement, Boolean search protocol, frozen criteria -> work/state.json
+ partial result.json; verify.py screens, appraises, synthesises, renders, verifies.
Usage: python3 slr_review.py [--input D] [--output D] [--work D] [--no-stage2]
"""
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, time, zipfile, zlib
from pathlib import Path
from datetime import datetime, timezone

SD, REF = Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "references"
T0, NOW = time.time(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
SK, VER, CV = "systematic-literature-review", "1.0.0", "v1.0"
CJK = re.compile(r"[\u4e00-\u9fff]")
LANG = "en"

def loadmsg():
  try:
    s = (REF / "slr-protocol.md").read_text(encoding="utf-8")
    return {p[0]: (p[1], p[2]) for p in ([x.strip() for x in ln.split("|")] for ln in
        re.search(r"<!--slr:msg\s*\n(.*?)-->", s, re.S).group(1).strip().splitlines()) if len(p) > 2 and p[0]}
  except Exception:
    return {}

MSG = loadmsg()
STOP = set("the and for with from that this these are was were has have had into not but can may also such than then their which while about used study studies research results result paper article based between among within more most both each other some its of in on to by as at or an we they them".split())

def M(_k, **f):
  v = MSG.get(_k) or (_k, _k)
  s = v[0] if LANG == "zh" else v[1]
  try: return s.format(**f)
  except Exception: return s

def nx(s):
  if not isinstance(s, str): return ""
  return re.sub(r"[ \t\u00a0]+", " ", s.replace("\u00ad", "").replace("\ufeff", "").replace("\r\n", "\n")).strip()

def nz(s):
  return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", nx(s).lower())).strip()

def tk(s):
  return [w for w in nz(s).split() if len(w) > 3 and w not in STOP]

def h12(b):
  return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8", "replace")).hexdigest()[:12]

def jw(p, o):
  p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(o, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def rd(p):
  b = Path(p).read_bytes()
  for e in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
    try: return b.decode(e)
    except Exception: pass
  return b.decode("utf-8", "replace")

def pdftxt(p):
  w = shutil.which("pdftotext")
  if w:
    try:
      o = subprocess.run([w, "-layout", str(p), "-"], capture_output=True, timeout=90)
      if o.returncode == 0 and len(o.stdout) > 200: return nx(o.stdout.decode("utf-8", "replace")), "pdftotext"
    except Exception: pass
  raw = Path(p).read_bytes(); out = []
  for m in re.finditer(rb"stream\r?\n", raw):
    e = raw.find(b"endstream", m.end())
    if e < 0: continue
    try: seg = zlib.decompress(raw[m.end():e])
    except Exception: seg = raw[m.end():e]
    if b"Tj" not in seg and b"TJ" not in seg: continue
    buf = []
    for tm in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]|\\.)*\]\s*TJ|T\*|TD|Td|ET", seg):
      g = tm.group(0)
      buf.append(_ps(g[1:g.rfind(b")")]) if g.endswith(b"Tj") else
           ("".join(_ps(x.group(0)[1:-1]) for x in re.finditer(rb"\((?:\\.|[^\\()])*\)", g)) if g.endswith(b"TJ") else "\n"))
    out.append("".join(buf))
  return nx("\n".join(out)), "stdlib_flate"

def _ps(b):
  b = re.sub(rb"\\([nrt])", lambda m: {b"n": b"\n", b"r": b"\n", b"t": b" "}[m.group(1)], b)
  return re.sub(rb"\\(.)", rb"\1", b).decode("latin-1", "replace")

def read_doc(p):
  e = p.suffix.lower()
  try:
    if e == ".pdf": return pdftxt(p)
    if e in (".docx", ".doc"):
      with zipfile.ZipFile(p) as z: x = z.read("word/document.xml").decode("utf-8", "replace")
      return nx(html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>|<w:br[^>]*/>", "\n", re.sub(r"<w:tab[^>]*/>", "\t", x))))), "zip_ooxml"
    return rd(p), "text"
  except Exception as ex:
    return "", "failed:" + type(ex).__name__

FR = re.compile(r"(?im)^[ \t>|*\-]*(title|标题|题名|abstract|摘要|authors?|作者|year|年份|journal|期刊|venue|source|doi|url|link)\s*[:：]\s*(.*\S)\s*$")
FK = {"title": ("title", "标题", "题名", "name", "heading"), "abstract": ("abstract", "摘要", "summary", "description"),
   "authors": ("authors", "author", "作者"), "year": ("year", "年份", "publication_year", "pubyear", "date"),
   "journal": ("journal", "期刊", "venue", "source", "container", "booktitle"), "doi": ("doi",),
   "url": ("url", "link", "href"), "full": ("fulltext", "full_text", "content", "body", "text")}
LAB = {a: b for b, ks in (("title", ("title", "标题", "题名")), ("abstract", ("abstract", "摘要")), ("authors", ("author", "authors", "作者")),
   ("year", ("year", "年份")), ("journal", ("journal", "期刊", "venue", "source")), ("doi", ("doi",)), ("url", ("url", "link"))) for a in ks}
KIND = {".json": "json", ".jsonl": "json", ".csv": "csv", ".tsv": "tsv", ".md": "text", ".txt": "text", ".pdf": "text", ".docx": "text"}

def pick(d, f):
  low = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in d.items()} if isinstance(d, dict) else {}
  for c in FK[f]:
    c = re.sub(r"[^a-z0-9]", "", c)
    if c in low and low[c] not in (None, "", [], {}): return low[c]
  return None

def to_rec(d, src):
  g = lambda f: str(pick(d, f) or "")
  r = dict(title=nx(g("title")), abstract=nx(g("abstract")), authors=pick(d, "authors") or "", year=pick(d, "year"),
      journal=nx(g("journal")), doi=nx(g("doi")), url=nx(g("url")), src=src, xf="", record_id="")
  y = r["year"]
  y = int(re.search(r"(1[89]\d\d|20\d\d)", y).group(1)) if isinstance(y, str) and re.search(r"(1[89]\d\d|20\d\d)", y) else y
  r["year"] = int(y) if isinstance(y, (int, float)) and 1800 < int(y) < 2200 else None
  if not isinstance(r["authors"], str): r["authors"] = ", ".join(map(str, r["authors"])) if isinstance(r["authors"], list) else ""
  ft = nx(g("full"))
  r["text"] = (r["title"] + "\n\n" + r["abstract"] + ("\n\n" + ft if ft else "")).strip()
  r["aspan"] = [len(r["title"]) + 2, len(r["title"]) + 2 + len(r["abstract"])]
  r["has_full"] = bool(ft) and len(ft) > 300
  r["lang"] = "zh" if len(CJK.findall(r["text"])) > max(20, len(r["text"]) // 25) else ("en" if re.search(r"[a-zA-Z]{4}", r["text"]) else "unknown")
  return r

def jrecs(o, out, d=0):
  if d > 6: return
  if isinstance(o, list):
    g = [x for x in o if isinstance(x, dict) and pick(x, "title") and (pick(x, "abstract") or pick(x, "doi"))]
    if g and len(g) >= max(1, len([x for x in o if isinstance(x, dict)]) - 1): out.extend(g); return
    for x in o: jrecs(x, out, d + 1)
  elif isinstance(o, dict):
    for v in o.values(): jrecs(v, out, d + 1)

def blkparse(t):
  t = t[:200000]
  st = [m.start() for m in FR.finditer(t) if m.group(1).lower() in ("title", "标题", "题名")]
  if len(st) < 2: st = [m.start() for m in re.finditer(r"(?m)^#{2,4} \S|^(?:R|S|Record)\s?\d{1,3}[.:]?\s*$", t)] or [0]
  cuts, out = st + [len(t)], []
  for i in range(len(cuts) - 1):
    b, e = cuts[i], cuts[i + 1]
    if e - b < 60: continue
    f, cur = {}, None
    for ln in re.finditer(r"[^\n]+", t[b:e]):
      a0, a1 = b + ln.start(), b + ln.end()
      m = FR.match(t[a0:a1])
      if m: cur = LAB.get(m.group(1).lower(), "other"); f[cur] = t[a0 + m.start(2):a1].strip()
      elif cur == "abstract" and t[a0:a1].strip(): f[cur] = (f[cur] + " " + t[a0:a1].strip()).strip()
      else: cur = None
    if f.get("title"): out.append(f)
  return out

def parse_recs(p, txt, kind):
  try:
    if kind == "json":
      raw = []; jrecs(json.loads(txt), raw); return [to_rec(d, p.name) for d in raw]
    if kind in ("csv", "tsv"):
      import csv
      return [to_rec(r, p.name) for r in csv.DictReader(txt.splitlines(), delimiter="," if kind == "csv" else "\t") if pick(r, "title")]
    return [to_rec(f, p.name) for f in blkparse(txt)]
  except Exception:
    return []

def discover(d):
  files = sorted(p for p in d.rglob("*") if p.is_file() and 0 < p.stat().st_size < 25000000 and not p.name.startswith("."))
  case, cpath = {}, None
  for p in sorted((x for x in files if x.suffix.lower() == ".json"), key=lambda x: x.name != "case.json"):
    try: o = json.loads(rd(p))
    except Exception: continue
    if isinstance(o, dict) and any(k in o for k in ("output_contract", "outputContract", "case_id", "caseId", "task_instruction")):
      case, cpath = o, p; break
  task = next((rd(p) for p in files if p.name.lower() in ("task.md", "task.txt", "prompt.md")), "")
  return files, case, cpath, task

def getq(case, task):
  raw = next((v.strip() for k in ("research_question", "question", "task_instruction", "objective", "topic")
        for v in [case.get(k)] if isinstance(v, str) and len(v.strip()) > 8), "")
  if not raw:
    m = re.search(r"(?m)^#{1,4}\s*(?:研究问题|Research question|Question|题目|Task)[^\n]*\n+(.{20,800}?)(?:\n#{1,4}\s|\Z)", task, re.S)
    raw = nx(m.group(1)) if m else nx(task[:600])
  el, kw = {}, []
  for k in ("population", "intervention", "comparison", "outcome", "study_design", "time_frame", "language", "setting"):
    for sc in (case, case.get("scope") or {}, case.get("constraints") or {}, case.get("pico") or {}):
      if isinstance(sc, dict) and sc.get(k): el[k] = sc[k]
  for k in ("keywords", "terms", "concepts", "controlled_vocabulary", "mesh", "search_terms"):
    v = case.get(k)
    kw += [str(x) for x in v] if isinstance(v, list) else ([x for x in re.split(r"[,;、]", v)] if isinstance(v, str) else [])
  return dict(raw=raw, elements=el, keywords=[x.strip() for x in kw if x.strip()][:40])

def qstruct(q):
  el = dict(q.get("elements") or {}); meth, conf = "case_fields", "high"
  if not el.get("population") and not el.get("outcome"):
    meth, conf = "heuristic_from_wording", "low"
    p_ = [nx(x) for x in re.split(r"(?:[;；]|\band\b|\bversus\b|\bvs\.?\b|在|对于|关于)", q["raw"]) if len(nx(x)) > 6]
    if len(p_) >= 2: el["population"], el["outcome"] = p_[0][:160], p_[1][:160]
    else: el["topic"] = nx(q["raw"])[:200]
  for k in ("population", "intervention", "outcome"):
    if isinstance(el.get(k), str): el[k] = el[k][:300]
  core, seen = [], set()
  for k in ("population", "intervention", "outcome", "comparison", "topic"):
    core += tk(str(el[k])) if el.get(k) else []
  core += [x.lower() for x in q.get("keywords", [])]
  return dict(structured=el, core_terms=[c for c in core if c not in STOP and not (c in seen or seen.add(c))][:12],
        derivation=dict(method=meth, confidence=conf, needs_human=conf == "low"))

def build_search(st, recs):
  T = st["core_terms"]; blocks = []
  for bid, ts, elm in (("B_pop", T[:1], "population"), ("B_int", T[1:4], "intervention_or_exposure"), ("B_out", T[4:7], "outcome")):
    if not ts: continue
    exp = [x for w in ts for x in (w, w + "s" if not w.endswith("s") else w[:-1], w[:-3] + "y" if w.endswith("ies") else w)]
    blocks.append(dict(block_id=bid, element=elm, terms=ts, expanded=sorted({x for x in exp if len(x) > 3})[:24], boolean="AND",
             fields=["title", "abstract", "keywords"], intent=M("s_intent"), vocab_note=M("s_vocab")))
  qs = {st_: " AND ".join("(" + " OR ".join(f'"{x}"' + ("[tiab]" if st_ == "pubmed" else "") for x in b["expanded"][:10]) + ")" for b in blocks)
     for st_ in ("pubmed", "generic")}
  hit = {b["block_id"]: [r["record_id"] for r in recs if any(x in nz(r["text"]) for x in b["expanded"])] for b in blocks}
  full = [r["record_id"] for r in recs if all(r["record_id"] in hit.get(b["block_id"], []) for b in blocks)]
  return {"databases": [dict(name="supplied_corpus", status="executed_locally", date=NOW[:10], n_records=len(recs),
               limits=dict(time="as given", language="as given"), note=M("s_db_corpus")),
             dict(name="PubMed/MEDLINE", status="protocol_only", date=None, fields=["Title/Abstract", "MeSH"],
               limits=dict(time="as protocol", language="as protocol"), note=M("s_db_pubmed"))],
      "blocks": blocks, "queries": dict(pubmed_style=qs["pubmed"], generic_boolean=qs["generic"]),
      "execution": dict(mode="corpus_only", corpus_size=len(recs), matched_by_block={k: len(v) for k, v in hit.items()},
               matched_all_blocks=len(full), matched_ids=full), "limitations": [M("s_lim")]}

def build_crit(st):
  TT, k = ", ".join(st["core_terms"][:6]), min(2, max(1, len(st["core_terms"]) // 3))
  rows = [("IC1", "include", 2, M("c_ic1", k=k, t=TT), "core_term_hits>=%d" % k), ("IC2", "include", 3, M("c_ic2"), "empirical_markers"),
      ("IC3", "include", 3, M("c_ic3"), "outcome_marker"), ("EC1", "exclude", 1, M("c_ec1"), "core_hits==0"),
      ("EC2", "exclude", 2, M("c_ec2"), "population_absent"), ("EC3", "exclude", 1, M("c_ec3"), "EDIT_marker_no_data"),
      ("EC4", "exclude", 3, M("c_ec4"), "outcome_absent"), ("EC6", "exclude", 1, M("c_ec6"), "year_lang_window")]
  cl = [dict(id=i, type=ty, priority=pr, checkable="auto", text=tx, rule=ru) for i, ty, pr, tx, ru in rows]
  cl.append(dict(id="EC7", type="exclude", priority=5, checkable="auto", soft=True, text=M("c_ec7"), rule="fulltext_unavailable_soft"))
  return dict(version=CV, frozen_at=NOW, conflict_policy=M("c_policy"), clauses=cl,
        priority_order=["EC1", "EC3", "EC6", "EC2", "IC1", "IC3", "EC4", "EC7"])

def refine_terms(st, recs):
  tx = " ".join(nz(r["text"]) for r in recs)
  keep = [t for t in st["core_terms"] if len(t) > 1 and t in tx]
  if not keep:
    cand = {}
    for t in st["core_terms"]:
      for n in (3, 2, 4):
        for i in range(len(t) - n + 1):
          g = t[i:i + n]
          if CJK.search(g):
            c = sum(g in nz(r["title"] + " " + r["abstract"]) for r in recs)
            if c >= 2: cand[g] = (c, n)
    keep = [g for g, c in sorted(cand.items(), key=lambda z: (-z[1][0], -z[1][1]))][:8]
    if not keep:
      freq = {}
      for r in recs:
        for w in set(tk(r["title"])):
          freq[w] = freq.get(w, 0) + 1
      keep = [w for w, c in sorted(freq.items(), key=lambda z: -z[1]) if c >= max(2, len(recs) // 3)][:6]
      st["derivation"].update(needs_human=True, language_mismatch=True)
  st["core_terms"] = keep[:12]
  return st

def main():
  ap = argparse.ArgumentParser(prog="slr_review.py",
    description="SLR stage 1/2: discovery, records, question decomposition, search protocol, eligibility freeze; verify.py screens, appraises, synthesises, renders, verifies.",
    epilog="Exit code always 0. A partial result.json is written first; verify.py finalises it.")
  ap.add_argument("--input", default=os.environ.get("SLR_INPUT", ""), help="input dir (/input or ./input)")
  ap.add_argument("--output", default=os.environ.get("SLR_OUTPUT", ""), help="output dir (/app/output or ./output)")
  ap.add_argument("--work", default=os.environ.get("SLR_WORK", ""), help="work dir (/app/work or ./work)")
  ap.add_argument("--no-stage2", action="store_true", help="stop after stage 1")
  a = ap.parse_args()
  indir = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else SD.parent / "input")
  out = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else Path.cwd() / "output")
  wk = Path(a.work) if a.work else (Path("/app/work") if Path("/app").is_dir() else Path.cwd() / "work")
  (wk / "extracted").mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
  errs, degs, pend, chg, mats, recs, st = [], [], [], [], [], [], None
  R = dict(skill=dict(name=SK, version=VER), case_id=None, status="partial", stage="init", language="en", output_contract={},
      sources=[], coverage={}, pending_human=pend, errors=errs, degradations=degs, changes=chg,
      artifacts={k: v for k, v in (("result_json", "result.json"), ("review_md", "review.md"), ("evidence_map_csv", "evidence_map.csv"),
            ("screening_log_csv", "screening_log.csv"), ("appraisal_csv", "appraisal.csv"),
            ("search_protocol_json", "search_protocol.json"), ("flow_counts_json", "flow_counts.json"))})
  jw(out / "result.json", R)
  case, cpath = {}, None
  try:
    files, case, cpath, task = discover(indir)
    R["output_contract"] = next((case[k] for k in ("output_contract", "outputContract", "output_schema") if k in case), {})
    R["case_id"] = case.get("case_id") or case.get("caseId") or case.get("id") or (cpath.stem if cpath else None)
    if not case: errs.append(dict(stage="discover", error="no case json with output_contract/case_id", input_dir=str(indir)))
    q = getq(case, task); globals()["LANG"] = "zh" if len(CJK.findall(q["raw"])) > 12 else "en"; R["language"] = LANG
    if not nx(q["raw"]): pend.append(dict(action="confirm_research_question", why="no question text in case.json or task.md"))
    R["stage"] = "extract"
    for f in files:
      if (cpath and f == cpath) or f.name.lower() in ("task.md", "task.txt", "prompt.md") or f.suffix.lower() not in KIND: continue
      txt, how = read_doc(f)
      if how.startswith("failed"): degs.append(dict(file=f.name, issue=how, action="file_skipped")); continue
      rs = parse_recs(f, txt, KIND[f.suffix.lower()]); recs += rs
      mats.append(dict(path=f.name, kind=f.suffix.lower().lstrip("."), bytes=f.stat().st_size, sha256_12=h12(f.read_bytes()),
              records_found=len(rs), extractor=how, char_count=len(txt)))
      if len(txt) < 40: degs.append(dict(file=f.name, issue="empty_or_unreadable_text", action="no_records"))
    if not recs and case:
      raw = []; jrecs(case, raw); recs = [to_rec(d, cpath.name if cpath else "case.json") for d in raw]
    seen, uniq = {}, []
    for r in recs:
      k = r["doi"].lower() if r["doi"] else re.sub(r"[^a-z0-9]", "", nz(r["title"]))[:90]
      if k and k in seen: degs.append(dict(record=r["title"][:80], issue="duplicate_merged", kept=seen[k])); continue
      if k: seen[k] = "R%02d" % (len(uniq) + 1)
      uniq.append(r)
    recs = uniq
    for i, r in enumerate(recs):
      r["record_id"] = "R%02d" % (i + 1); r["xf"] = "extracted/%s.txt" % r["record_id"]
      (wk / r["xf"]).write_text(r["text"], encoding="utf-8")
    R["stage"] = "protocol"; st = refine_terms(qstruct(q), recs)
    R["research_question"] = dict(raw=q["raw"], language=LANG, answerable_scope=M("q_scope", n=len(recs)), **st)
    R["search"], R["criteria"] = build_search(st, recs), build_crit(st)
    R["materials"], R["case_path"] = mats, (str(cpath) if cpath else None)
    if st["derivation"]["needs_human"]:
      pend.append(dict(action="confirm_structured_question", why="PICO derived heuristically from wording", derived=st["structured"]))
    if not recs:
      R["status"] = "insufficient_evidence"
      pend.append(dict(action="supply_literature_records", why="no record parsed from supplied materials", files_seen=[m["path"] for m in mats]))
    jw(wk / "state.json", dict(R=R, recs=recs, st=st, lang=LANG, mats=mats))
    if not a.no_stage2 and (SD / "verify.py").exists():
      try:
        o = subprocess.run([sys.executable, "-B", str(SD / "verify.py"), "--work", str(wk), "--output", str(out)], capture_output=True, timeout=400)
        if o.returncode: degs.append(dict(stage="stage2", issue=o.stderr.decode("utf-8", "replace")[-300:], action="stage1_outputs_kept"))
      except Exception as ex: degs.append(dict(stage="stage2", issue=type(ex).__name__, action="stage1_outputs_kept"))
    else: degs.append(dict(stage="stage2", issue="verify.py_absent_or_skipped", action="stage1_outputs_kept"))
  except Exception as ex:
    errs.append(dict(stage="stage1", error=type(ex).__name__, detail=str(ex)[:400]))
  finally:
    try:
      if not recs and R["status"] == "partial": R["status"] = "insufficient_evidence"
      R["stage"], R["pending_human"], R["errors"], R["degradations"] = "stage1_done", pend, errs, degs
      R["runtime"] = dict(stage1_seconds=round(time.time() - T0, 1), started_utc=NOW, python=sys.version.split()[0],
                network=False, model_requests=None, mode="corpus_only")
      chg.append(dict(at=NOW, stage="protocol_freeze", change="criteria %s frozen before screening" % CV, by="pipeline"))
      if not (out / "review.md").exists(): jw(out / "result.json", R)
    except Exception: pass
  return 0

if __name__ == "__main__":
  sys.exit(main())
