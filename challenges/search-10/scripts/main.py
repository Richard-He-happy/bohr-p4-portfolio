#!/usr/bin/env python3
"""Cross-lingual known-item literature retrieval: CLI, screening, outputs.
Runs engine.py on the case input and writes result.json, candidates.csv/json,
query_log.json, term_table.json, verification.json. Offline, stdlib only."""
import argparse, csv, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E

V = E.V
T0 = time.time()
HK = ("task_instruction", "research_question", "question", "user_query", "query",
      "request", "task", "instruction", "known_item", "citation")


def build(recs, cs, an, maxk):
  """score, merge language versions of a work, screen; returns cands, log, works, th"""
  sc = [E.score(r, cs, an) for r in recs]
  works, rules = E.cluster(recs)
  th = max(0.12, round(0.35 * max([x["score"] for x in sc], default=0.0), 3))
  cands, scr = [], []
  for w in sorted(works, key=lambda w: -max(sc[i]["score"] for i in w["ix"])):
    w["ml"] = sorted({recs[j]["lang"] for j in w["ix"] if sc[j]["score"] > 0})
    w["pi"] = max(w["ix"], key=lambda i: ("origin" in str(recs[i]["ver"]).lower(),
                                          sc[i]["score"]))
    i, s = w["pi"], sc[w["pi"]]
    if s["score"] <= 0:
      scr.append({"work_id": w["wid"], "include": False, "score": 0.0,
                  "reason": "no_query_term_matched",
                  "criteria": "no variant found in record text"})
      continue
    if s["score"] < th or len(cands) >= maxk:
      scr.append({"work_id": w["wid"], "include": False, "score": s["score"],
                  "reason": "below_threshold" if s["score"] < th else "max_k_cut",
                  "criteria": "score %.3f vs threshold %.3f, max_k %d" % (s["score"], th, maxk)})
      continue
    r, e = recs[i], E.evid(recs[i], s["matched"])
    txt = (" ".join(map(str, r["ver"].keys())) + " " +
           " ".join(map(str, r["ver"].values()))).lower()
    tags = [t for t, k in (("exact_duplicate", "duplicat"), ("translation_view", "translat"),
                           ("translation_view", "tradu"), ("original_view", "origin"),
                           ("abstract_only_view", "abstract")) if k in txt]
    if len(w["langs"]) > 1:
      tags.append("multilingual_version_set")
    tags = list(dict.fromkeys(tags)) or ["single_view"]
    cands.append({
        "candidate_id": "c%02d" % (len(cands) + 1), "work_id": w["wid"],
        "rank": len(cands) + 1, "title": r["title"], "authors": r["authors"],
        "year": r["year"], "venue": r["venue"], "doi": r["doi"], "url": r["url"],
        "language": r["lang"], "language_confidence": r["lang_conf"],
        "language_evidence": r["lang_ev"], "version_label": tags[0], "version_tags": tags,
        "version_confidence": 0.9 if r["ver"] else 0.45,
        "version_basis": r["ver"] or {"inferred": "%d view(s), %d chars"
                                      % (len(w["langs"]), len(r["abstract"]))},
        "n_views": len(w["ix"]), "languages_in_work": w["langs"],
        "matched_languages": w["ml"],
        "view_records": ["%s:%s:%s" % (recs[j]["rec_id"], recs[j]["lang"], recs[j]["doi"] or "-")
                         for j in w["ix"]],
        "source_db": "local_corpus", "source_file": r["src"], "retrieved_at": E.now(),
        "query_id": "q01", "relevance_score": s["score"],
        "matched_terms": s["matched"],
        "relevance_reason": "; ".join(
            ["%s via '%s' (%s, %s) in %s" % (m["concept"], m["surface"], m["method"],
                                              m["alignment"], m["field"])
             for m in s["matched"][:8]] +
            (["anchor:" + ",".join(s["bonus_evidence"])] if s["bonus_evidence"] else [])),
        "evidence_snippet": e["quote"], "evidence_locator": e["locator"],
        "evidence_quote_match": e["quote_match"],
        "flags": [f for f, c in (("missing_doi", not r["doi"]),
                                 ("language_low_confidence", r["lang_conf"] < 0.6),
                                 ("quote_unverified", e["quote_match"] == "failed")) if c]})
    scr.append({"work_id": w["wid"], "include": True, "reason": "kept", "score": s["score"],
                "criteria": "score >= %.3f and a variant matched the record text" % th,
                "candidate_id": cands[-1]["candidate_id"]})
  for w in works:
    for j in [x for x in w["ix"] if x != w["pi"]]:
      scr.append({"work_id": w["wid"], "include": False, "score": sc[j]["score"],
                  "reason": "duplicate_view_merged", "record_id": recs[j]["rec_id"],
                  "criteria": "same work as %s (%s)" % (recs[w["pi"]]["rec_id"],
                                                       ",".join(w["langs"]))})
  return cands, scr, works, rules, th, sc


def checks(out, res):
  """deterministic audit: contract fields present, quote still in source, id links"""
  cands, cache, bad, miss = res.get("candidates") or [], {}, [], []
  con = res.get("output_contract")
  keys = list(con) if isinstance(con, dict) else [
      e if isinstance(e, str) else (e.get("name") or e.get("field") or e.get("key"))
      for e in (con or []) if isinstance(e, (str, dict))]
  miss = [k for k in keys if k and k not in res]
  qids = {q.get("query_id") for q in (res.get("queries") or [])}
  for c in cands:
    src = c.get("source_file") or ""
    if src not in cache:
      try:
        cache[src] = Path(src).read_text(encoding="utf-8", errors="replace")
      except Exception:
        cache[src] = ""
    q = c.get("evidence_snippet") or ""
    if not (q and (q in cache[src] or E.nz(q) in E.nz(cache[src]))) \
            or c.get("query_id") not in qids:
      bad.append(c.get("candidate_id"))
  rep = {"checked_at": E.now(), "candidates": len(cands), "contract_fields": len(keys),
         "contract_missing": miss, "unverified_candidates": bad,
         "verdict": "fail" if (miss or bad) else "pass"}
  E.wj(out / "verification.json", rep)
  return rep


def main(argv=None):
  ap = argparse.ArgumentParser(
      prog="main.py",
      description="Cross-lingual known-item literature retrieval: concept table, per-language "
                  "queries, language/version labels, version merge, verbatim evidence. "
                  "Writes result.json, candidates.csv/json, query_log.json, term_table.json. "
                  "Exit code is always 0.",
      epilog="examples:\n  python3 main.py --input /input --out /app/output\n"
             "  python3 main.py --input /input --records hits.jsonl --max-k 10",
      formatter_class=argparse.RawDescriptionHelpFormatter)
  for f, k in (("--input", {"default": "/input", "help": "case directory"}),
               ("--out", {"default": "/app/output", "help": "output directory"}),
               ("--records", {"nargs": "*", "default": [], "help": "extra record file(s)"}),
               ("--max-k", {"type": int, "default": 0, "help": "max candidates (0: scope/15)"}),
               ("--quiet", {"action": "store_true", "help": "less stdout"})):
    ap.add_argument(f, **k)
  a = ap.parse_args(argv)
  try:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
  except Exception:
    out = Path.cwd()
  ind = Path(a.input)
  res = {"case_id": None, "status": "partial", "stage": "started", "skill_version": V,
         "candidates": [], "queries": [], "screening": [], "coverage": {}, "sources": [],
         "uncertainty": [], "pending_human": [], "errors": [], "degradations": [],
         "changes": [], "runtime": {}}
  E.wj(out / "result.json", res)  # partial first
  ch = lambda s, d="": res["changes"].append({"ts": E.now(), "action": s, "detail": d})

  def unc(kind, detail, impact, action):
    res["uncertainty"].append({"id": "U%d" % (len(res["uncertainty"]) + 1), "kind": kind,
                               "detail": detail, "impact": impact, "action": action})

  case, con = {}, None
  try:
    c = ind / "case.json"
    if not c.exists():
      f = sorted(ind.rglob("case*.json"))
      c = f[0] if f else None
    if c and c.exists():
      case, nt = E.jload(c)
      if not isinstance(case, dict):
        res["errors"].append({"stage": "case_parse", "file": str(c), "detail": str(nt),
                              "handled": True})
        case = {"items": case} if case else {}
    con = case.get("output_contract") if isinstance(case, dict) else None
    if con is None and isinstance(case, dict):
      con = next((v for k, v in case.items() if "output_contract" in str(k).lower()), None)
  except Exception as e:
    res["errors"].append({"stage": "case_load", "detail": repr(e), "handled": True})
  res["case_id"] = case.get("case_id") if isinstance(case, dict) else None
  res["output_contract"] = con
  E.fill(res, con)
  E.wj(out / "result.json", res)
  ch("partial_result_written", "contract keys defaulted before retrieval")

  q = ""
  try:
    low = {str(k).lower(): v for k, v in case.items()}
    for k in HK:
      v = low.get(k)
      if isinstance(v, str) and len(v) > 20:
        q = v
        break
      if isinstance(v, list) and v and isinstance(v[0], str):
        q = " ".join(v)
        break
    if len(q) < 20:
      for k, v in case.items():
        if isinstance(v, dict) and "scope" in str(k).lower():
          q = str(v.get("topic") or v.get("research_question") or "")
    if len(q) < 20 and (ind / "task.md").exists():
      q = (ind / "task.md").read_text(encoding="utf-8", errors="replace")[:4000]
      res["degradations"].append({"feature": "question_extraction",
                                  "reason": "no instruction field in case.json",
                                  "fallback": "task.md head used as question text"})
  except Exception as e:
    res["errors"].append({"stage": "question", "detail": repr(e), "handled": True})

  scope = {}
  for k, v in case.items():
    if isinstance(v, dict) and ("scope" in str(k).lower() or "workorder" in str(k).lower()):
      scope.update(v)
  maxk = a.max_k or int(scope.get("max_k") or scope.get("top_k") or 15)
  ql, qc, qev = E.langid(q)
  gl, gh, gerr = E.glossary()
  if gerr:
    res["degradations"].append({"feature": "glossary", "reason": gerr,
                                "fallback": "concept table limited to literal terms"})
  cs = E.concepts_of(q, ql, gl, gh) if q else []
  recs, files, errs, unsup = E.scan(ind, a.records)
  res["errors"] += errs
  for u in unsup:
    res["degradations"].append({"feature": "read_" + Path(u["path"]).suffix,
                                "reason": u["reason"],
                                "fallback": "listed as unparsed material, never cited"})
  an = E.anchors(q)
  sl = []
  for k in ("lang", "language", "languages", "target_languages", "langs"):
    v = scope.get(k)
    sl += [str(x).strip().lower()[:2] for x in ([v] if isinstance(v, str) else (v or []))]
  sl = [x for x in dict.fromkeys(sl) if x in E.OKL]
  tgt = sl or [x for x in dict.fromkeys([ql] + [v["lang"] for c in cs for v in c["variants"]
                                               if v["lang"] not in ("und", ql, "unknown")])][:4]
  tgt = [t for t in tgt if t in E.OKL][:6] or ["en"]
  res["question"] = {"text": q[:1200], "language": ql, "confidence": qc, "evidence": qev}
  res["anchor_extraction"] = an
  res["term_table"] = cs

  blob = " " + " ".join(E.nz(r["title"] + " " + r["abstract"][:1200]) for r in recs) + " "
  gained = E.expand(cs, gh, ql, blob) if cs else []
  log, _plan = E.retrieve(recs, cs, tgt, an)
  cands, scr, works, rules, th, sc = build(recs, cs, an, maxk)
  for c in cands:
    for lg in log:
      if lg["status"] == "ok" and any(m["variant_lang"] == lg["lang"]
                                      for m in c["matched_terms"]):
        c["query_id"] = lg["query_id"]
        break
  have = sorted({l for c in cands for l in (c["matched_languages"] or [c["language"]])
                 if l not in ("unknown", "")})
  gaps = [{"type": "language_without_result", "language": x,
           "note": "no verified candidate"} for x in tgt if x not in have]
  gaps += [{"type": "material_not_parsed", "path": u["path"], "note": u["reason"]}
           for u in unsup]
  if not recs:
    gaps.insert(0, {"type": "no_corpus", "note": "no record-like object; nothing retrieved"})
    for qq in log:
      qq["status"], qq["db"], qq["error"] = ("not_executed_no_backend", "none",
                                             "no record corpus supplied")
    unc("no_record_corpus",
        "no record-like object found; no search backend reachable offline",
        "no candidate can be produced without fabricating records",
        "run queries[] with an available search tool, save hits as JSONL, rerun --records")
    res["pending_human"].append({"item": "candidate retrieval",
                                 "why": "the case supplied no record corpus",
                                 "action": "execute queries[] and rerun with --records"})
    res["degradations"].append({"feature": "record_corpus",
                                "reason": "no record-like object found in the input",
                                "fallback": "query plan only; no candidate fabricated"})
  res["coverage"] = {
      "question_language": ql, "target_languages_declared": tgt,
      "languages_with_results": have, "records_in_corpus": len(recs),
      "works_after_dedup": len(works), "candidates_returned": len(cands),
      "non_source_language_works": sum(1 for w in works
                                       if any(recs[i]["lang"] != ql for i in w["ix"])),
      "duplicates_merged": sum(len(w["ix"]) - 1 for w in works),
      "gaps": gaps,
      "recall_estimate": {"value": None, "method": "no reference set in case",
                          "proxy": {"candidate_share_of_corpus":
                                    round(len(cands) / max(len(recs), 1), 3)}}}
  gain = {"note": "internal ablation on this corpus; the platform runs its own baseline"}
  if cs and recs:
    lit = [{"id": w, "weight": 1.0, "variants": [{"lang": ql, "surface": w, "norm": w,
                                                  "method": "question_literal", "weight": 1.0}]}
           for w in dict.fromkeys(E.toks(q)) if len(w) > 3
           and w not in (E.STOP.get(ql, set()) | E.STOP["en"])][:40]
    bs = [E.score(r, lit, an) for r in recs]
    bk = [i for i, s in enumerate(bs) if s["score"] >= th]
    bl = sorted({recs[i]["lang"] for i in bk})
    bw = len(E.cluster([recs[i] for i in bk])[0]) if bk else 0
    sk = sorted({l for c in cands for l in c["matched_languages"]})
    gain.update({
        "baseline": {"mode": "literal tokens, one language, no table, no merge",
                     "works": bw, "records": len(bk), "languages": bl, "queries": 1},
        "skill": {"mode": "concept table + per-language queries + merge",
                  "works": len(cands), "records": sum(1 for x in sc if x["score"] > 0),
                  "languages": sk, "queries": len([x for x in log if x["status"] != "no_term_mapping"])},
        "delta": {"languages_reached": len(sk) - len(bl), "works": len(cands) - bw},
        "caveat": "single run, same corpus and threshold; quote checks are per candidate in verification.json; scoreable only against a reference set"})
  if gained:
    unc("heuristic_term_expansion",
        "%d cognate variants added for languages absent from the glossary" % len(gained),
        "irregular and compound forms may be missed",
        "review term_table entries whose method is cognate_rule")
  for c in cands:
    if "quote_unverified" in c["flags"]:
      res["pending_human"].append({"item": c["candidate_id"] + " evidence",
                                   "why": "quote failed the verbatim check",
                                   "action": "inspect the source record manually"})
  if not cands:
    res["status"] = "insufficient_evidence" if (recs or case) else "input_error"
    unc("empty_result", "%d records scanned, none above threshold %.3f" % (len(recs), th),
        "empty candidate list", "supply more records or widen the scope")
  else:
    bad = [c["candidate_id"] for c in cands if "quote_unverified" in c["flags"]]
    nd = sum(1 for c in cands if "missing_doi" in c["flags"])
    res["status"] = "partial" if (bad or nd or gaps) else "ok"
    if nd:
      unc("metadata_incomplete", "%d candidates lack a DOI" % nd,
          "identity rests on title and venue only", "resolve DOIs before citing")
    if bad:
      unc("evidence_not_verbatim", "candidates %s have unverified quotes" % bad,
          "not independently verifiable", "human inspection of the source")

  res.update({"queries": log, "candidates": cands, "screening": scr,
              "term_expansion": {"n_concepts": len(cs),
                                 "n_variants": sum(len(c["variants"]) for c in cs),
                                 "heuristic_variants_added": len(gained)},
              "dedup": {"n_works": len(works), "rules": rules,
                        "multilingual_works": [{"work_id": w["wid"], "languages": w["langs"],
                                                "n_views": len(w["ix"])}
                                               for w in works if len(w["ix"]) > 1]},
              "gain_analysis": gain,
              "sources": [{"source_id": "S%02d" % (i + 1), "kind": "local_case_file",
                           "path": f["path"], "records_used": f["records"],
                           "retrieved_at": E.now(), "backend": "filesystem_read",
                           "network": False} for i, f in enumerate(files)],
              })
  E.fill(res, con)
  res["stage"] = "finalized"
  res["runtime"] = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0)),
                    "finished_at": E.now(), "seconds": round(time.time() - T0, 2),
                    "python": sys.version.split()[0], "skill_version": V, "network": False,
                    "model_requests": 0, "argv": sys.argv}
  ch("finalized", "status=%s candidates=%d" % (res["status"], len(cands)))
  for n, o in (("candidates.json", cands), ("query_log.json", log), ("term_table.json", cs)):
    E.wj(out / n, o)
  cols = ["candidate_id", "rank", "work_id", "title", "year", "venue", "doi", "url",
          "language", "version_label", "n_views", "query_id", "retrieved_at",
          "relevance_score", "relevance_reason", "evidence_snippet", "locator",
          "evidence_quote_match", "flags"]
  with open(out / "candidates.csv", "w", encoding="utf-8-sig", newline="") as fh:
    wr = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    wr.writeheader()
    for c in cands:
      r2 = dict(c)
      r2["locator"] = c["evidence_locator"]
      r2["flags"] = "|".join(c["flags"])
      wr.writerow(r2)
  E.wj(out / "result.json", res)
  try:
    rep = checks(out, res)
  except Exception as e:
    rep = {"verdict": "unavailable", "error": str(e)[:120]}
  if not a.quiet:
    print("[main] status=%s candidates=%d langs=%s check=%s secs=%s" % (
        res["status"], len(cands), have, rep.get("verdict"), round(time.time() - T0, 2)))
  return 0


if __name__ == "__main__":
  try:
    sys.exit(main())
  except SystemExit:
    raise
  except Exception as exc:
    try:
      d = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path("/app/output")
      d.mkdir(parents=True, exist_ok=True)
      p = d / "result.json"
      prev = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
      prev.setdefault("case_id", None)
      prev["status"] = "partial"
      prev.setdefault("candidates", [])
      prev.setdefault("uncertainty", []).append({"id": "U-fatal", "kind": "uncaught_exception",
                                                 "detail": repr(exc)})
      prev.setdefault("errors", []).append({"stage": "main", "detail": str(exc),
                                            "handled": True})
      prev["stage"] = "degraded_finalized"
      E.wj(p, prev)
    except Exception:
      pass
    print("[main] degraded exit: %s" % exc, file=sys.stderr)
    sys.exit(0)
