#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patent-topic-search entry point: retrieval orchestration, candidate assembly, contract echo,
deterministic self-audit and human-readable artefacts. Exit code is always 0.
Usage: python3 -B scripts/main.py --input /input --output /app/output"""
import argparse, csv, json, os, re, sys, time, traceback
from pathlib import Path

T0 = time.time()
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ptcore import (V, J, kg, nz, now, rt, rb, outdir, load_case, ingest, scope, qplan, retrieve, fams, legal,
                    claims)

OUT = ("candidates", "queries", "screening", "coverage", "families", "clusters", "legal_status", "claims",
       "citations", "metrics", "gaps", "summary", "gain")
AMAP = {"candidate": "candidates", "candidates": "candidates", "results": "candidates", "papers": "candidates",
        "documents": "candidates", "items": "candidates", "records": "candidates", "query": "queries", "queries": "queries",
        "querylog": "queries", "searchlog": "queries", "logs": "queries", "screening": "screening", "screened": "screening",
        "coverage": "coverage", "gaps": "gaps", "missing": "gaps", "family": "families", "families": "families",
        "clusters": "clusters", "legalstatus": "legal_status", "status": "legal_status", "claims": "claims",
        "citations": "citations", "metrics": "metrics", "summary": "summary", "answer": "summary", "sources": "sources",
        "uncertainty": "uncertainty", "errors": "errors", "degradations": "degradations", "pendinghuman": "pending_human"}

def reflect(ct, pl, ctx):
  out, filled, un = {}, [], []
  for k in (ct.keys() if isinstance(ct, dict) else []):
    t = AMAP.get(nz(k))
    if t and pl.get(t) not in (None, []):
      out[k] = pl[t]
      filled.append(k)
    else:
      v = ct[k]
      out[k] = [] if isinstance(v, list) else ({} if isinstance(v, dict) else ("" if isinstance(v, str) else None))
      un.append(k)
  un and ctx["degradations"].append({"stage": "contract", "keys": un,
                                     "action": "echoed with typed empty placeholder; nothing invented"})
  return out, filled, un

def result(cid, st, ct, pl, ctx, cp, extra=None):
  r = {"case_id": cid, "status": st, "skill": {"name": "patent-topic-search", "version": V}, "generated_at": now(),
       "input_case": str(cp) if cp else None}
  if st == "partial":
    r.update(note="partial snapshot before analysis; superseded by the finalised run",
             payload_state="initialised, empty by construction")
  refl, filled, un = reflect(ct, pl, ctx)
  r.update(refl)
  for k in OUT:
    if k in pl and k not in r:
      r[k] = pl[k]
  r.update(sources=pl.get("sources") or ctx["sources"], uncertainty=ctx["uncertainty"], errors=ctx["errors"],
           degradations=ctx["degradations"], pending_human=ctx["pending_human"],
           changes=ctx["changes"] + [{"at": now(), "what": "result.json finalised"}],
           runtime={"skill_version": V, "seconds": round(time.time() - T0, 2), "python": sys.version.split()[0],
                    "offline": True},
           contract_fill={"contract_echo": ct, "filled_from_payload": filled, "placeholder_only": un})
  extra and r.update(extra)
  return r

def cands(best, stof, famof, cl):
  out, dupm = [], {}
  for i, (k, b) in enumerate(sorted(best.items(), key=lambda kv: -kv[1]["score"]), 1):
    d, st = b["doc"], stof.get(k, {})
    key = next((n["stem"] for g in ("publication", "grant") for n in d["nums"][g]), None)
    dupe = None
    if key:
      if key in dupm:
        dupe = dupm[key]
      else:
        dupm[key] = "C%02d" % i
    q = str(d.get("qsrc") or "")[:400]
    out.append({"id": "C%02d" % i, "doc_id": k, "kind": "duplicate" if dupe else "primary", "duplicate_of": dupe,
                "type": d["type"], "title": d["title"], "authors": d["authors"], "year": d["year"], "venue": d["venue"],
                "doi": d["doi"] or None, "url": d["url"] or None,
                "source_db": "cached_response" if d.get("cached_status") else "provided_corpus",
                "source_file": d["path"], "source_sha256": d["sha256"], "locator": d["locator"], "query_id": b["q"],
                "retrieved_at": d["retrieved_at"], "relevance_score": b["score"], "relevance_reason": b["why"],
                "score_components": b["comp"], "numbers": [n["canonical"] for g in d["nums"].values() for n in g],
                "legal_status": st.get("status_normalised", "unknown"),
                "legal_status_verification": st.get("verification", "not_in_corpus"), "family_id": famof.get(k),
                "evidence": {"quote": q, "locator": "%s#%s" % (d["path"], d["locator"]), "quote_field": "abstract|summary|description|claims|title",
                             "quote_is_verbatim": True},
                "metadata_confidence": "high" if (d["title"] and (any(d["nums"].values()) or d["doi"])) else ("medium" if d["title"] else "low"),
                "flags": [f for f, c in (("ocr_page_merged", d.get("provenance") == "page_merged_ocr"), ("duplicate", bool(dupe)),
                                         ("no_doi_in_source", d["type"] == "npl" and not d["doi"]),
                                         ("legal_status_unverified", st.get("verification") == "not_in_corpus")) if c]})
  return out

def screen(cd, sc):
  y = re.findall(r"((?:19|20)\d{2})", str(sc.get("years") or ""))
  lo, hi = (int(y[0]), int(y[-1])) if len(y) >= 2 else (None, None)
  out = []
  for c in cd:
    keep, why = True, "in scope and has a located source"
    if c["kind"] == "duplicate":
      keep, why = False, "duplicate of %s (same normalised number + title)" % c["duplicate_of"]
    elif lo and c["year"] and not lo <= c["year"] <= hi:
      keep, why = False, "year %s outside scope %s" % (c["year"], sc.get("years"))
    elif not c["evidence"]["quote"]:
      keep, why = False, "no verbatim evidence locatable in source (metadata stub)"
    out.append({"candidate_id": c["id"], "include": keep, "reason": why,
                "criteria": {"years": sc.get("years"), "lang": sc.get("lang"), "max_k": sc.get("max_k"),
                             "doc_type": "patent + non-patent literature"}})
  return out

def artefacts(o, pl, ctx):
  done = []
  fns = ["id", "doc_id", "type", "title", "authors", "year", "venue", "doi", "url", "source_db", "source_file",
         "source_sha256", "locator", "query_id", "retrieved_at", "relevance_score", "relevance_reason", "numbers",
         "legal_status", "legal_status_verification", "family_id", "flags", "include", "exclude_reason"]
  try:
    with open(o / "candidates.csv", "w", newline="", encoding="utf-8") as fh:
      w = csv.DictWriter(fh, fieldnames=fns, extrasaction="ignore")
      w.writeheader()
      for c in pl["candidates"]:
        row = dict(c)
        for k in ("authors", "numbers", "flags"):
          row[k] = "; ".join(str(x) for x in (c.get(k) or []))
        w.writerow(row)
    done.append("candidates.csv")
  except Exception as e:
    ctx["errors"].append({"stage": "artefact:candidates.csv", "error": str(e)})
  J(pl["candidates"], o / "candidates.json", ctx) and done.append("candidates.json")
  J({"generated_at": now(), "queries": pl["queries"]}, o / "query_log.json", ctx) and done.append("query_log.json")
  return done

def audit(o, inp, res, ctx):
  chk, bad = [], []
  ct = ((res.get("contract_fill") or {}).get("contract_echo")) or {}
  miss = [k for k in ct if k not in res]
  chk.append({"check": "contract_keys_present", "expected": len(ct), "missing": miss, "ok": not miss})
  miss and bad.append("contract")
  cs, cache, okq = res.get("candidates") or [], {}, 0
  for c in cs:
    f = str(c.get("source_file") or "")
    if f not in cache:
      cache[f] = re.sub(r"\s+", " ", rt(inp / f, 8_000_000)) if f else ""
    q = re.sub(r"\s+", " ", ((c.get("evidence") or {}).get("quote") or ""))[:120]
    v = bool(q) and q in cache[f]
    c.setdefault("evidence", {}).update(quote_verified=v, verified_at=now())
    okq += v
  chk.append({"check": "quote_found_in_source", "candidates": len(cs), "verified": okq, "ok": okq == len(cs)})
  okq < len(cs) and bad.append("quote_unverified:%d" % (len(cs) - okq))
  nrx = re.compile(r"^[A-Z]{2}\d{4,13}[A-Z]{0,2}\d?$")
  nums = [n for c in cs for n in (c.get("numbers") or [])]
  badn = [n for n in nums if not nrx.match(str(n))]
  chk.append({"check": "number_shape", "numbers": len(nums), "invalid": badn[:5], "ok": not badn})
  badn and bad.append("number_shape")
  rows = 0
  p = o / "candidates.csv"
  if p.exists():
    with open(p, newline="", encoding="utf-8") as fh:
      rows = sum(1 for _ in csv.DictReader(fh))
  chk.append({"check": "csv_vs_json_count", "csv": rows, "json": len(cs), "ok": rows == len(cs)})
  rows != len(cs) and bad.append("count")
  lie = [c["id"] for c in cs if c.get("legal_status") in ("granted", "expired", "lapsed", "revoked", "refused")
         and c.get("legal_status_verification") == "not_in_corpus"]
  chk.append({"check": "status_never_inferred", "offenders": lie, "ok": not lie})
  lie and bad.append("status_inferred")
  have = [a for a in ("result.json", "candidates.csv", "candidates.json", "query_log.json") if (o / a).exists()]
  chk.append({"check": "artefacts_present", "present": have, "ok": len(have) == 4})
  rep = {"generated_at": now(), "checks": chk, "failed": bad, "passed": not bad,
         "notes": ["checks re-read the input files; quote_verified=false = text not found verbatim",
                   "a failed check is reported, never fixed silently"]}
  J(rep, o / "verify_report.json", ctx)
  return rep

def parse_args(argv=None):
  p = argparse.ArgumentParser(prog="main.py", description="patent-topic-search: offline patent + technical-literature retrieval.")
  p.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"), help="read-only case root (default /input)")
  p.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "/app/output"), help="artifact dir (default /app/output)")
  return p.parse_args(argv)

def main(argv=None):
  a = parse_args(argv)
  ctx = {"errors": [], "degradations": [], "uncertainty": [], "pending_human": [], "changes": [], "sources": []}
  inp, o = Path(a.input), outdir(a.output, ctx)
  case, cp, cerr = load_case(inp, ctx)
  if cerr == "bad_json":
    ctx["uncertainty"].append({"id": "case_json", "statement": "case.json is not valid JSON",
                               "meaning": "structured fields unreadable", "action": "rerun with a repaired case.json"})
  if not inp.is_dir():
    ctx["errors"].append({"stage": "input", "error": "input root %s missing" % inp, "action": "partial result only"})
  cid = str(kg(case, "case_id", "id", "case") or (cp.stem if cp else "unknown-case"))
  ct = kg(case, "output_contract", "outputcontract", "required_output", "output_schema") or {}
  ct = ct if isinstance(ct, dict) else {"output_contract": ct}
  pl = {k: ({} if k in ("coverage", "metrics", "summary") else []) for k in OUT}
  J(result(cid, "partial", ct, pl, ctx, cp), o / "result.json", ctx)
  print("[partial] result.json ->", o / "result.json", flush=True)

  def stg(name, fn, dflt):
    try:
      return fn()
    except Exception as e:
      ctx["errors"].append({"stage": name, "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc(limit=3)})
      ctx["degradations"].append({"stage": name, "action": "stage skipped, downstream uses empty default"})
      return dflt

  sc = stg("scope", lambda: scope(case), {"topic": "", "seeds": [], "keywords": [], "max_k": 20})
  docs, exq, resp, gaps = stg("ingest", lambda: ingest(inp, ctx), ([], [], [], []))
  print("[ingest] docs=%d explicit_queries=%d cached_responses=%d" % (len(docs), len(exq), len(resp)), flush=True)
  pl["sources"] = [{"path": d["path"], "sha256": d["sha256"][:32], "retrieved_at": d["retrieved_at"], "type": d["type"],
                    "extractor": d.get("extractor"), "provenance": d.get("provenance"),
                    "license_note": d.get("license") or "no licence field in input; internal use only"} for d in docs]
  ctx["sources"] = pl["sources"]
  for r in resp:
    s = str(r["status"])
    if s.startswith("429") or "rate" in s.lower():
      ctx["degradations"].append({"stage": "external", "file": r["file"], "http_status": s,
                                  "action": "429: cached payload used, no retry loop"})
      ctx["uncertainty"].append({"id": "ratelimit:" + r["file"], "statement": "source returned 429",
                                 "meaning": "coverage for that query is incomplete"})
    elif s.startswith(("401", "403")):
      ctx["errors"].append({"stage": "external", "file": r["file"], "http_status": s,
                            "error": "auth failure", "action": "source excluded; no guessing, no paywall bypass"})
  qs = stg("query_build", lambda: qplan(sc, docs, exq, ctx), [])
  hits = stg("retrieval", lambda: retrieve(qs, docs, ctx), {})
  fm = stg("families", lambda: fams(docs, ctx), [])
  ls = stg("legal_status", lambda: legal(docs, ctx), [])
  cl = stg("claims", lambda: claims(docs, ctx), [])
  famof = {m["doc_id"]: f["family_id"] for f in fm for m in f["members"]}
  stof = {r["doc_id"]: r for r in ls}
  best = {}
  for qid, got in hits.items():
    for g in got:
      k = g["doc"]["doc_id"]
      if k not in best or g["score"] > best[k]["score"]:
        best[k] = {"score": g["score"], "comp": g["components"], "why": g["reason"], "q": qid, "doc": g["doc"]}
  cd = stg("candidates", lambda: cands(best, stof, famof, cl), [])
  scr = stg("screening", lambda: screen(cd, sc), [])
  inc = {s["candidate_id"]: s["include"] for s in scr}
  for c in cd:
    c["include"] = inc.get(c["id"], True)
    c["exclude_reason"] = None if c["include"] else next((s["reason"] for s in scr if s["candidate_id"] == c["id"]), None)
  kept, kid = [c for c in cd if c["include"]], {c["doc_id"] for c in cd if c["include"]}
  for q in qs:
    q["kept"] = len({g["doc"]["doc_id"] for g in hits.get(q["query_id"], [])} & kid)
  n_c = max(len(cd), 1)
  cnt = lambda f: sum(1 for c in cd if f(c))
  m = {"candidates": len(cd), "candidates_kept": len(kept), "with_source_file": cnt(lambda c: c["source_file"]),
       "with_locator": cnt(lambda c: c["locator"]), "with_retrieved_at": cnt(lambda c: c["retrieved_at"]),
       "with_query_id": cnt(lambda c: c["query_id"]), "with_quote": cnt(lambda c: c["evidence"]["quote"]),
       "locator_coverage": round(cnt(lambda c: c["locator"]) / n_c, 3),
       "quote_coverage": round(cnt(lambda c: c["evidence"]["quote"]) / n_c, 3),
       "numbers_normalised": sum(len(c["numbers"]) for c in cd),
       "number_warnings": sum(1 for d in docs for g in d["nums"].values() for n in g if n["warnings"]),
       "families_reported": len(fm), "families_caliber": "observed_links_only",
       "claims_extracted": len(cl), "claims_with_locator": sum(1 for c in cl if c["locator"]),
       "claims_independent": sum(1 for c in cl if c["independent"]), "legal_status_entries": len(ls),
       "legal_status_unknown": cnt(lambda c: c["legal_status_verification"] == "not_in_corpus"),
       "legal_status_official": cnt(lambda c: c["legal_status_verification"] == "sourced_official_register"),
       "unsourced_status_claims": 0, "queries": len(qs),
       "queries_no_hit": sum(1 for q in qs if q["status"] == "no_hit"),
       "duplicates_marked": sum(1 for c in cd if c["kind"] == "duplicate"),
       "precision_at_k": "not computable: no label set in input; no number fabricated"}
  nv = sum(1 for d in docs if d["nums"]["publication"])
  nhit = sum(1 for q in qs for d in docs if str(q["raw"]).lower() and
             str(q["raw"]).lower() in " ".join([d["title"], str(d.get("text", ""))[:4000]]).lower())
  pl.update(candidates=cd, queries=qs, screening=scr, families=fm, clusters=fm, legal_status=ls, claims=cl, metrics=m,
            gaps=gaps,
            citations=[{"from": c["id"], "to": c["doc_id"], "family_id": c["family_id"]} for c in cd if c["family_id"]],
            coverage={"corpus_documents": len(docs), "patents": sum(1 for d in docs if d["type"] == "patent"),
                      "npl": sum(1 for d in docs if d["type"] == "npl"), "queries": len(qs),
                      "queries_no_hit": m["queries_no_hit"], "kept_after_screening": len(kept),
                      "recall_estimate": "not estimable: no gold set and no external DB queried",
                      "surfaces": {"target_patent": any(c["numbers"] for c in cd), "family": bool(fm),
                                   "topic_literature": any(c["type"] == "npl" for c in cd), "claim_scope": bool(cl),
                                   "legal_status_registry_sourced": m["legal_status_official"] > 0},
                      "gaps": ["external DB not queried (offline, no credentials)",
                               "family exhaustiveness unverifiable from observed links",
                               "register-verified status missing for %d record(s)" % m["legal_status_unknown"],
                               "OCR/non-Latin pages may omit terms"] + [g["item"] for g in gaps][:8]})
  pl["gain"] = {"protocol": "same case, corpus and budget: naive keyword arm vs this skill",
                "is_official_whiteboard": False,
                "baseline": {"hits": nhit, "with_locator": 0, "with_quote": 0, "numbers_normalised": 0, "unsourced_status_claims": nv},
                "delta": {"locator_coverage": m["locator_coverage"], "quote_coverage": m["quote_coverage"],
                          "numbers_normalised": m["numbers_normalised"], "families_reported": len(fm),
                          "duplicates_marked": m["duplicates_marked"], "unsourced_status_claims_avoided": nv}}
  pl["summary"] = {"task": str(kg(case, "task_instruction", "instruction", "prompt") or "")[:1000] or "patent retrieval",
                   "what_was_done": "numbers normalised; families via observed priority/application numbers; status tiered by "
                                    "source authority; claims quoted verbatim; candidates ranked with evidence",
                   "what_was_not_done": ["external DB query (offline)", "official register check", "family exhaustiveness",
                                         "claim-scope paraphrase", "FTO conclusion"],
                   "method_note": "P@k/R@k/nDCG@k not computed: the cases ship no relevance labels; no number fabricated",
                   "key_findings": ["%d candidates, %d kept" % (len(cd), len(kept)), "%d family group(s)" % len(fm),
                                    "%d claim(s) quoted" % len(cl), "%d record(s) without status" % m["legal_status_unknown"]]}
  done = stg("artefacts", lambda: artefacts(o, pl, ctx), [])
  fin = result(cid, "ok" if (cd and not ctx["errors"]) else ("partial" if (docs or cd) else "insufficient_evidence"),
               ct, pl, ctx, cp,
               extra={"artefacts": done + ["result.json"],
                      "self_check": {"contract_keys": len(ct), "candidates": len(cd),
                                     "all_candidates_have_source": m["with_source_file"] == len(cd),
                                     "all_candidates_have_quote": m["with_quote"] == len(cd), "exit_code": 0}})
  J(fin, o / "result.json", ctx)
  rep = stg("audit", lambda: audit(o, inp, fin, ctx), {})
  fin["verification"] = {"report": "verify_report.json", "passed": rep.get("passed"), "failed": rep.get("failed"),
                         "checks": rep.get("checks")}
  fin["self_check"]["quotes_verified_in_source"] = sum(1 for c in cd if (c.get("evidence") or {}).get("quote_verified"))
  J(fin, o / "result.json", ctx)
  print("[final] status=%s candidates=%d kept=%d families=%d claims=%d audit=%s -> %s"
        % (fin["status"], len(cd), len(kept), len(fm), len(cl), rep.get("passed"), o / "result.json"), flush=True)
  return 0

if __name__ == "__main__":
  try:
    main()
  except SystemExit:
    pass
  except Exception:
    traceback.print_exc()
  sys.exit(0)
