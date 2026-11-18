#!/usr/bin/env python3
"""citation-tracer: seed -> citation graph -> deduplicated, ranked, evidenced literature set. Offline; exit 0."""
import argparse, csv, difflib, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import citelib as C
V = "1.3.0"
T0 = time.monotonic()
DL = T0 + 780.0
DOIRE = r"10\.\d{4,9}/[^\s\"'<>(){}\[\],;]+"
STOP = set("the of and for with using a an in on to from via based model study analysis data results paper this "
      "that we our its their into over new".split())
AL = [x.split("=") for x in ("uncertain=uncertainty candidate=candidates paper=candidates literatur=candidates "
   "quer=queries screen=screening edge=edges citation=edges seed=seeds coverage=coverage gap=coverage "
   "missing=missing path=paths metric=metrics status=status source=sources").split()]


def utc():
 return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def U(R, k, d, a=""):
 R["uncertainty"].append({"kind":k, "detail":d, "affected":a})


def Q(q, db, raw, kind, hits=0, kept=0, st="ok", note=""):
 e = {"query_id":"q%03d" % len(q), "db":db, "query":raw, "kind":kind, "filters":None, "hits":hits,
    "retained":kept, "status":st, "retrieved_at":utc()}
 q.append(dict(e, note=note) if note else e)


def rd(p):
 b = p.read_bytes()[:24000000]
 try:
  return b.decode("utf-8-sig")
 except Exception:
  return b.decode("utf-8", "replace")


def blk(p):
 t = rd(p)
 if p.suffix.lower() in (".csv", ".tsv"):
  return C.tbl(t), 0
 if p.suffix.lower() in (".yaml", ".yml", ".txt", ".bib", ".ris", ".xml"):
  return C.trs(t), 0
 if p.suffix.lower() not in (".jsonl", ".ndjson"):
  try:
   return [json.loads(t)], 0
  except Exception:
   return [], 1
 o, n = [], 0
 for x in t.splitlines():
  if x.strip():
   try:
    o.append(json.loads(x))
   except Exception:
    n += 1
 return o, n


def ptxt(p):
 try:
  r = subprocess.run(["pdftotext", "-l", "2", str(p), "-"], capture_output=True, timeout=20)
  return C.nsp(r.stdout.decode("utf-8", "replace")) if r.returncode == 0 else ""
 except Exception:
  return ""


def wj(p, o):
 p.parent.mkdir(parents=True, exist_ok=True)
 t = p.with_name(p.name + ".tmp")
 t.write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
 os.replace(str(t), str(p))


def dbo(s):
 t = str(s).lower()
 return next((v for k, v in (("crossref", "crossref"), ("epmc", "europepmc"), ("europepmc", "europepmc"),
               ("openalex", "openalex"), ("semantic", "semanticscholar"), ("s2", "semanticscholar"), ("pubmed", "pubmed"),
               ("arxiv", "arxiv"), ("patent", "patent")) if k in t), "retained_input")


def fill(P, ct):
 items = [(str(k), v) for k, v in ct.items()] if isinstance(ct, dict) else \
   [(it if isinstance(it, str) else C.as_text(C.getf(it, "field", "name", "key"), 160), it) for it in (ct or [])]
 miss = []
 for f, spec in items:
  top = re.split(r"[./\[]", f)[0] if f else ""
  if not top or top in P:
   continue
  kn = re.sub(r"[^a-z0-9]", "", top.lower())
  v = next((P[x] for k, x in AL if x in P and k in kn), None)
  if v is None and isinstance(spec, dict):
   t = str(C.getf(spec, "type", "dtype", "kind") or "")
   v = [] if ("array" in t or "list" in t) else ({} if ("object" in t or "dict" in t) else C.getf(spec, "default"))
  P[top] = v
  if v in (None, [], {}):
   miss.append(top)
 return miss


def lcase(inp):
 cs = [inp / n for n in ("case.json", "input.json", "task.json") if (inp / n).is_file()] or \
    sorted(inp.rglob("case*.json"))[:3]
 for p in cs:
  try:
   o = json.loads(rd(p))
   if isinstance(o, dict):
    return o, p
  except Exception:
   pass
 return {}, None


def rslv(s, k2w):
 s = (s or "").strip()
 if not s:
  return None
 for key in (("doi", C.ndoi(s)), ("pmid", s if re.fullmatch(r"\d{6,9}", s) else ""), ("openalex", C.noa(s)),
       ("title", C.tkey(s))):
  if key[1] and key in k2w:
   return k2w[key]
 pr = C.tkey(s) or C.nttl(s)
 sc = [(difflib.SequenceMatcher(None, pr, k[1]).ratio(), v) for k, v in k2w.items() if k[0] == "title"]
 best = max(sc) if sc else (0.0, None)
 return best[1] if best[0] >= 0.9 else None


def grow(works, edges, seeds, depth, fanout, cap, tok):
 oe, ie = C.adjacency(edges)
 cd = {s: {"id":s, "hop":0, "channel":"seed", "via":None, "edges":[]} for s in seeds}
 q, g = [(s, 0) for s in seeds], 0
 while q and g < 20000 and time.monotonic() < DL:
  g += 1
  w, h = q.pop(0)
  if h >= depth:
   continue
  for ch, el in (("backward", oe.get(w, [])), ("forward", ie.get(w, []))):
   for e in el[:fanout]:
    nb = e["dst"] if ch == "backward" else e["src"]
    if nb in cd:
     cd[nb]["edges"].append(e)
    elif len(cd) < cap:
     cd[nb] = {"id":nb, "hop":h + 1, "channel":ch, "via":w, "edges":[e]}
     q.append((nb, h + 1))
 rf, ct, srf, sct = {}, {}, set(), set()
 for e in edges:
  rf.setdefault(e["src"], set()).add(e["dst"])
  ct.setdefault(e["dst"], set()).add(e["src"])
 for s in seeds:
  srf |= rf.get(s, set())
  sct |= ct.get(s, set())
 rel = []
 for wid in works:
  if wid in seeds:
   continue
  sh, co = sorted(rf.get(wid, set()) & srf), sorted(ct.get(wid, set()) & sct)
  if len(sh) >= 2 or co:
   rel.append({"work_id":wid, "coupling":len(sh), "cocitation":len(co), "shared_references":sh[:5],
         "co_citing_works":co[:5], "basis":"%d shared refs; co-cited by %d" % (len(sh), len(co))})
 rel.sort(key=lambda r: (-r["coupling"], -r["cocitation"]))
 rel = rel[:40]
 for x in rel:
  if x["work_id"] not in cd and len(cd) < cap * 2:
   cd[x["work_id"]] = {"id":x["work_id"], "hop":2, "channel":"parallel", "via":seeds[0], "edges":[]}
 deg = C.degree_map(edges)
 md = max(deg.values()) if deg else 1
 ys = [w.get("year") for w in works.values() if w.get("year")]
 y0, y1 = (min(ys), max(ys)) if ys else (0, 0)
 for c in cd.values():
  w = works.get(c["id"], {})
  y = w.get("year")
  base = {"forward":1.0, "backward":0.85, "parallel":0.6, "seed":1.0}.get(c["channel"], 0.4)
  r = round(max(0.3, min(1.0, (base - 0.05 * max(0, c["hop"] - 1)) *
             (0.85 if w.get("metadata_confidence") == "low" else 1.0))), 3)
  c["bd"] = {"relation":r, "proximity":round(1.0 / (1.0 + c["hop"]), 3),
        "topical":C.overlap(tok, (w.get("title") or "") + " " + (w.get("abstract") or "")[:400]),
        "centrality":round(deg.get(c["id"], 0) / float(md), 3),
        "recency":round((y - y0) / float(y1 - y0), 3) if (y and y1 > y0) else 0.0}
  d = c["bd"]
  c["score"] = round(0.4 * d["relation"] + 0.2 * d["proximity"] + 0.15 * d["topical"]
            + 0.15 * d["centrality"] + 0.1 * d["recency"], 4)
 return cd, rel, deg


def scn(inp, R, recs, raw, srcs, ql, imp):
 pdfd, pdft, files = [], [], sorted(p for p in inp.rglob("*") if p.is_file())
 for p in files:
  if time.monotonic() > DL - 90:
   R["degradations"].append({"what":"scan stopped at deadline", "fallback":"partial corpus"})
   break
  rel, suf = str(p.relative_to(inp)), p.suffix.lower()
  if suf == ".pdf":
   t = ptxt(p)
   if not t:
    srcs.append({"name":rel, "kind":"pdf", "parsed":False})
    R["degradations"].append({"what":"pdf text unavailable: " + rel, "fallback":"metadata only"})
    continue
   ds = [x for x in (C.ndoi(y) for y in re.findall(DOIRE, t)) if x][:5]
   pdfd += [x for x in ds if x not in pdfd]
   ln = [x.strip() for x in t.splitlines() if len(x.strip()) > 20][:1]
   if ln and C.tkey(ln[0]):
    pdft.append(ln[0][:200])
   srcs.append({"name":rel, "kind":"pdf", "text_chars":len(t), "doi_candidates":ds})
   Q(ql, "local_pdf", "text:" + rel, "pdf_seed_scan", len(ds), len(ds), "ok", "doi + first line = seed hints")
   continue
  if suf not in (".json", ".jsonl", ".ndjson", ".txt", ".xml", ".bib", ".ris", ".csv", ".tsv",
      ".yaml", ".yml") or p.stat().st_size > 12000000:
   continue
  mt = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
  objs, errs = blk(p)
  if errs:
   R["degradations"].append({"what":"unparseable lines in " + rel, "fallback":"kept valid lines", "count":errs})
  n0, e0 = len(recs), len(raw)
  for o in objs:
   C.harvest(o, rel, mt, Path(rel).stem, "", recs, raw)
   if isinstance(o, dict) and re.search(r"import|sync|state", rel, re.I):
    d = {k: v for k, v in ((k, C.getf(o, k)) for k in ("state", "status", "imported", "imported_count",
                              "pending", "pending_count", "iteration"))
       if isinstance(v, (str, int, float))}
    if d:
     imp.append(dict(d, file=rel))
  nr, ne = len(recs) - n0, len(raw) - e0
  if nr or ne:
   srcs.append({"name":rel, "kind":"records", "retrieved_at":mt, "records":nr, "edges":ne, "db":dbo(rel)})
  Q(ql, dbo(rel), "scan:" + rel, "retained_cache_scan", max(nr, 0), max(ne, 0), "ok" if not errs else "partial")
 return len(files), pdfd, pdft


def emt(out, R, cands):
 cols = ["candidate_id", "work_id", "title", "authors", "year", "venue", "doi", "url", "source_db", "hop",
     "channel", "relevance_score", "metadata_confidence", "flags", "source_file", "json_pointer", "retrieved_at"]
 with open(out / "candidates.csv", "w", encoding="utf-8", newline="") as f:
  w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
  w.writeheader()
  for c in cands:
   w.writerow(dict(c, authors="; ".join(c.get("authors") or []), flags=";".join(c.get("flags") or []),
           source_file=(c.get("source_locator") or {}).get("file", ""),
           json_pointer=(c.get("source_locator") or {}).get("json_pointer", "")))
 wj(out / "query_log.json", {"case_id":R.get("case_id"), "generated_at":utc(), "network_used":False,
               "entries":R["queries"]})
 R["artifacts"] = {"candidates_csv":"candidates.csv", "query_log":"query_log.json"}


def stop(R, st, sm, pend=None, miss=None, ct=None):
 R.update(status=st, summary=sm)
 if pend:
  R["pending_human"].append(pend)
 if miss is not None:
  R["missing"] = miss
 if ct is not None:
  R["contract_missing"] = fill(R, ct)
 R["checks"], R["self_check_pass"] = C.self_check(R, R.get("candidates") or [], R.get("edges") or [])


def run(a, inp, out, R):
 if not inp.exists():
  return stop(R, "input_error", "input directory not found: %s" % inp,
        {"action":"mount the case at /input", "why":"no readable input"},
        [{"item":"input", "why":"path missing", "action":"mount /input"}])
 case, cp = lcase(inp)
 ct = C.getf(case, "output_contract", "outputContract", "required_output")
 sc = C.getf(case, "organizer_supplied_scope", "scope", "constraints") or {}
 wk = C.getf(case, "organizer_workorder", "workorder") or {}
 R["case_id"] = C.as_text(C.getf(case, "case_id", "caseId", "id", "task_id"), 200) or "case-unknown"
 ins = C.as_text(C.getf(case, "task_instruction", "instruction", "task", "question"), 4000)
 if (inp / "task.md").is_file():
  ins += " " + rd(inp / "task.md")[:6000]
 if not ct:
  R["degradations"].append({"what":"no output_contract in case.json", "fallback":"canonical schema"})
 R["changes"].append({"step":"located", "at":utc()})
 recs, raw, srcs, ql, imp = [], [], [], [], []
 nf, pdfd, pdft = scn(inp, R, recs, raw, srcs, ql, imp)
 R["counts"] = {"input_files":nf, "records_raw":len(recs), "edges_raw":len(raw)}
 merges = []
 works, k2w = C.build_index(recs, merges)
 st = {}
 edges = C.resolve_edges(raw, works, k2w, st)
 R["counts"].update({"works_after_merge":len(works), "edges_kept":len(edges),
           "edges_unresolved":st.get("edges_unresolved", 0), "identity_merges":len(merges)})
 R["sources"], R["queries"] = srcs, ql
 if not works:
  return stop(R, "insufficient_evidence", "no bibliographic record in the retained inputs",
        {"action":"provide records / citation artifacts", "why":"no work records"},
        [{"item":"bibliographic records", "why":"none parseable in /input",
         "action":"supply records"}], ct)
 specs = C.seed_specs(case) + pdfd + pdft + [C.ndoi(x) for x in re.findall(DOIRE, ins)[:3]]
 seeds, unrs = [], []
 for s in specs[:20]:
  w = rslv(s, k2w)
  Q(ql, "local_index", "seed:" + s[:150], "local_index_lookup", 1 if w else 0, 1 if w else 0,
   "ok" if w else "no_match")
  if w and w not in seeds:
   seeds.append(w)
  elif not w:
   unrs.append(s[:120])
 oe, ie = C.adjacency(edges)
 if not seeds:
  rr = sorted(works, key=lambda w: -(len(ie.get(w, [])) + len(oe.get(w, []))))
  if rr:
   seeds = [rr[0]]
   U(R, "seed_inferred", "no resolvable seed id; most-connected retained work used", "entire expansion")
   R["pending_human"].append({"action":"confirm the intended seed paper", "why":"seed was inferred"})
 if not seeds:
  return stop(R, "insufficient_evidence", "no seed resolved",
        {"action":"supply seed DOI/PMID/title", "why":"seed unresolved"},
        [{"item":s, "why":"identifier absent from retained records", "action":"confirm seed"}
         for s in unrs[:8]] or [{"item":"seed", "why":"none supplied", "action":"supply seed"}], ct)
 rows = []
 for s in seeds:
  w = works.get(s, {})
  nb, nfwd = len(ie.get(s, [])), len(oe.get(s, []))
  rows.append({"work_id":s, "title":w.get("title", ""), "doi":w.get("doi", ""), "year":w.get("year"),
         "metadata_confidence":w.get("metadata_confidence"), "backward_edges":nfwd,
         "forward_edges":nb, "provenance":w.get("provenance", [])[:2]})
  if not nb:
   U(R, "seed_without_forward_citations", "nothing retained cites " + (w.get("doi") or s), "forward coverage")
   Q(ql, "crossref/europepmc", "fwd:" + (w.get("doi") or s), "planned_query", 0, 0, "not_executed",
    "offline: retained records only")
  if not nfwd:
   U(R, "seed_without_reference_list", "no retained reference list for " + (w.get("doi") or s),
    "upstream coverage")
 R["seeds"] = rows
 dep = next((C.getf(sc, k) for k in ("depth", "expansion_depth", "hops") if isinstance(C.getf(sc, k), int)
       and 1 <= C.getf(sc, k) <= 4), a.depth)
 cap = next((C.getf(sc, k) for k in ("max_k", "top_k", "k") if isinstance(C.getf(sc, k), int)
       and 4 <= C.getf(sc, k) <= 200), a.max_candidates)
 txt = " ".join(str(x) for x in (ins, C.as_text(C.getf(sc, "topic", "query", "question", "title"), 600),
                 C.as_text(C.getf(case, "topic", "research_question"), 600),
                 C.as_text(C.getf(wk, "topic", "question"), 300)))
 tok = [w for w in set(C.nttl(txt).split()) if len(w) > 3 and w not in STOP][:40]
 cd, rel, deg = grow(works, edges, seeds, dep, 30, max(cap * 3, 60), tok)
 cands = C.assemble([(w, c) for w, c in sorted(cd.items(), key=lambda kv: -kv[1]["score"])
           if w not in seeds][:cap], works, rel, dbo)
 R["candidates"] = cands
 R["edges"] = [{"edge_id":e["id"], "citing":e["src"], "cited":e["dst"], "relation":e["rel"],
         "source_file":e["src_file"], "evidence":e["evidence"][:2]} for e in edges[:4000]]
 cw = set(c["work_id"] for c in cands)
 R["screening"] = [{"candidate_id":c["candidate_id"], "include":True,
           "criteria":"edge from a seed within depth %d; identity merged" % dep,
           "reason":c["relevance_reason"]} for c in cands]
 exc = [w for w in works if w not in cw and w not in seeds]
 R["metrics"] = C.set_metrics([{"uniq":c["work_id"], "doi":c["doi"], "locator":bool(c["source_locator"]),
                 "direction":c["citation_relation"]["direction"],
                 "basis":bool(c["related_evidence"])} for c in cands])
 se = set(e["id"] for e in edges if e["src"] in seeds or e["dst"] in seeds)
 cov = sum(1 for e in edges if e["id"] in se and (e["src"] in cw or e["dst"] in cw))
 fw = sum(1 for s in rows if s["forward_edges"])
 low = sum(1 for c in cands if c["metadata_confidence"] == "low")
 flg = sum(1 for c in cands if c["flags"])
 gaps = [t for c, t in (
   (fw < len(seeds), "no forward citations for %d/%d seeds" % (len(seeds) - fw, len(seeds))),
   (st.get("edges_unresolved"), "%d edges unresolved to a retained record" % st.get("edges_unresolved", 0)),
   (low, "%d identifier-only candidates" % low),
   (flg, "retraction/correction/preprint/patent/non-English flags on %d item(s)" % flg),
   (unrs, "%d seed identifier(s) unresolved" % len(unrs))) if c]
 R["coverage"] = {"seeds":len(seeds), "seeds_with_forward_citations":fw, "retained_works":len(works),
          "retained_edges":len(edges), "returned_candidates":len(cands), "excluded_works":len(exc),
          "related_works":len(rel), "seed_neighbourhood_edges":len(se), "recall_estimate":None,
          "seed_neighbourhood_coverage":round(cov / float(len(se) or 1), 3), "import_states":imp,
          "doi_rate":round(sum(1 for c in cands if c["doi"]) / float(len(cands) or 1), 3), "gaps":gaps}
 if [d for d in imp if any(str(v).lower() in ("pending", "partial", "incomplete") or (isinstance(v, int) and v > 0)
              for k, v in d.items() if k in ("pending", "pending_count", "state", "status"))]:
  U(R, "incremental_import_pending", "organizer-local import state marks unimported records", "coverage")
 R["missing"] = [{"item":g, "why":"retained inputs cannot supply it", "action":"back-fill when permitted"}
         for g in gaps] + [{"item":"seed unresolved: " + f, "why":"identifier absent from retained records",
                   "action":"confirm seed"} for f in unrs[:8]]
 bm = C.set_metrics([{"uniq":r["ids"].get("doi") or r["title_key"] or r["src"], "doi":r["doi"], "locator":True}
           for r in recs if r["title_key"] and set(C.nttl(r["title"]).split()) & set(tok)][:cap])
 R["baseline"] = {"protocol":"naive keyword match, no merge, no direction, first-k", "metrics":bm,
          "delta":{k: (None if R["metrics"].get(k) is None or bm.get(k) is None
                 else round(R["metrics"][k] - bm[k], 3)) for k in ("duplicate_rate", "doi_rate",
               "direction_labeled_rate", "locator_rate", "related_basis_rate")}}
 R["counts"].update({"queries":len(ql), "candidates":len(cands)})
 R["status"] = "insufficient_evidence" if not cands else (
   "partial" if (R["uncertainty"] or R["degradations"]) else "ok")
 if not cands:
  U(R, "empty_candidate_set", "seeds resolved but no expandable edge retained", "candidate list")
 R["summary"] = "%d seeds -> %d candidates / %d works (%d records); %d edges; %d gaps" % (
   len(seeds), len(cands), len(works), len(recs), len(edges), len(gaps))
 try:
  emt(out, R, cands)
 except Exception as e:
  R["errors"].append({"stage":"artifacts", "error":"%s: %s" % (type(e).__name__, e),
            "impact":"result.json still written"})
 R["contract_missing"] = fill(R, ct)
 R["checks"], R["self_check_pass"] = C.self_check(R, cands, edges)


def main(argv=None):
 ap = argparse.ArgumentParser(prog="citation-tracer", description="Offline citation tracing: seeds -> backward/forward/parallel edges -> merge -> ranked set.")
 ap.add_argument("--input", help="case dir (/input)")
 ap.add_argument("--output", help="output dir (/app/output)")
 ap.add_argument("--depth", type=int, default=2)
 ap.add_argument("--max-candidates", type=int, default=60)
 a = ap.parse_args(argv)
 inp = Path(a.input or "/input").resolve()
 if not inp.exists() and (H.parent / "input").exists():
  inp = H.parent / "input"
 out = Path(a.output or "/app/output").resolve()
 try:
  out.mkdir(parents=True, exist_ok=True)
 except Exception:
  out = H.parent / "output"
  out.mkdir(parents=True, exist_ok=True)
 R = {"skill":{"name":"citation-tracer", "version":V}, "case_id":None, "status":"partial", "candidates":[], "edges":[], "queries":[], "seeds":[], "coverage":{},
    "screening":[], "missing":[], "metrics":{}, "sources":[], "uncertainty":[], "pending_human":[],
    "errors":[], "degradations":[], "changes":[{"step":"partial_scaffold", "at":utc()}]}
 try:
  wj(out / "result.json", R)
 except Exception:
  pass
 try:
  run(a, inp, out, R)
 except Exception as e:
  R["errors"].append({"stage":"pipeline", "error":"%s: %s" % (type(e).__name__, e),
            "impact":"partial result retained"})
  if R.get("status") == "ok":
   R["status"] = "partial"
 R["runtime"] = {"started_at":R["changes"][0]["at"], "finished_at":utc(),
         "duration_s":round(time.monotonic() - T0, 2), "deadline_s":780,
         "python":sys.version.split()[0], "skill_version":V, "network_used":False,
         "pdf_tool":shutil.which("pdftotext") or "none"}
 R["changes"].append({"step":"finalized", "at":utc(),
            "detail":{"candidates":len(R.get("candidates") or []),
                 "edges":len(R.get("edges") or [])}})
 try:
  wj(out / "result.json", R)
 except Exception:
  pass
 return 0


if __name__ == "__main__":
 try:
  sys.exit(main())
 except SystemExit:
  raise
 except Exception:
  sys.exit(0)
