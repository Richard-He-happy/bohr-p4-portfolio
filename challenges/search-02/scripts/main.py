#!/usr/bin/env python3
"""search-02 research-question-retrieval: offline question-driven retrieval.
decompose -> query waves -> retrieve -> screen -> dedupe -> rank -> result.json.
Engine in retrieval.py. stdlib only, no network; partial result.json first; exit 0."""
import argparse, csv, json, os, re, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval as R

V, T0, MAXR, H, LEX_OK = R.V, R.T0, R.MAXR, R.H, R.LEX_OK
now, cl, wj, wt, lj = R.now, R.cl, R.wj, R.wt, R.lj
scan, q_of, scope_of = R.scan, R.q_of, R.scope_of
facets, anchors, decompose = R.facets, R.anchors, R.decompose
dedupe, build_index, execute = R.dedupe, R.build_index, R.execute
screen, snip, tk, ntitle, POS, NEG = R.screen, R.snip, R.tk, R.ntitle, R.POS, R.NEG

CMAP = ((("subquestion", "sub_question", "decomposition", "拆解", "子问题"), "sub_questions"),
        (("candidate", "paper", "article", "候选", "文献", "record", "记录"), "candidates"),
        (("quer", "查询"), "queries"), (("screen", "filter", "筛选"), "screening"),
        (("cover", "gap", "覆盖", "遗漏"), "coverage"), (("citation", "引文"), "citations"),
        (("conflict", "冲突"), "conflicts"), (("missing", "缺口"), "missing"),
        (("metric", "evalu", "指标"), "metrics"), (("uncertain", "不确定"), "uncertainty"),
        (("source", "来源"), "sources"), (("stop", "收敛", "停止"), "stopping"), (("log", "日志"), "logs"),
        (("status", "状态"), "status"), (("error", "异常"), "errors"), (("degrad", "降级"), "degradations"),
        (("pending", "human", "人工"), "pending_human"), (("change", "变更"), "changes"),
        (("runtime", "运行"), "runtime"), (("baseline", "对照"), "baseline"))

def pol(t):
    s = (t or "").lower()
    if any(x in s for x in NEG):
        return "negative"
    return "positive" if any(x in s for x in POS) else "mixed_or_neutral"

def conflicts(cs):
    """Heuristic: same-topic candidates whose snippets carry opposite polarity cues."""
    out = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            a, b = cs[i], cs[j]
            ta, tb = set(ntitle(a.get("title")).split()), set(ntitle(b.get("title")).split())
            pa, pb = pol(a.get("evidence_snippet")), pol(b.get("evidence_snippet"))
            if len(ta & tb) >= 3 and {pa, pb} == {"positive", "negative"}:
                out.append({"conflict_id": "cf%02d" % (len(out) + 1),
                            "candidate_ids": [a["candidate_id"], b["candidate_id"]], "directions": [pa, pb],
                            "snippets": [a.get("evidence_snippet"), b.get("evidence_snippet")],
                            "topic_overlap_terms": sorted(ta & tb)[:6],
                            "confidence": "low (lexical polarity heuristic)",
                            "resolution": "unresolved - requires human review"})
    return out[:8]

CSVF = ["candidate_id", "title", "authors", "year", "venue", "doi", "url", "source_db", "retrieved_at",
        "query_id", "relevance_score", "relevance_reason", "evidence_snippet", "evidence_locator",
        "metadata_confidence", "flags"]

def baseline(ix, q, cls_, sc, k):
    ts = [t for t in dict.fromkeys(tk(q)) if len(t) > 3][:8]
    rows = sorted(((sum(ix["idf"].get(t, .5) * ix["docs"][c["cid"]]["tf"][t] for t in ts
                        if ix["docs"][c["cid"]]["tf"].get(t)), c) for c in cls_), key=lambda x: -x[0])
    rows = [r for r in rows if r[0] > 0]
    got = rows[:k]
    return {"description": "flat keyword query, same snapshot: no decomposition/expansion/dedupe/screening", "query": " OR ".join(ts), "hits": len(rows),
            "returned": len(got), "candidate_ids": [c["cid"] for _, c in got],
            "in_scope_share": round(sum(1 for _, c in got if screen(c["cand"], sc)["keep"]) / len(got), 3)
            if got else None, "duplicate_exports_in_returned": sum(c["dup"] for _, c in got),
            "note": "internal control; not the organizer whiteboard"}

def fill(p, contract):
    flds = list(contract.items()) if isinstance(contract, dict) else (
        [(x, None) for x in contract] if isinstance(contract, list) else [])
    mapped = []
    for name, spec in flds:
        low = str(name).lower()
        tgt = next((t for ks, t in CMAP if any(k in low for k in ks)), None)
        arr = "array" in str(spec.get("type", "")).lower() if isinstance(spec, dict) else \
            bool(re.search(r"\b(list|array)", str(spec or ""), re.I))
        if tgt and p.get(tgt) not in (None, {}, ""):
            p[str(name)] = p[tgt]; mapped.append(str(name))
        else:
            p[str(name)] = [] if arr else None
    return p, mapped

def shell(case_id, contract):
    return {"case_id": case_id, "skill": {"name": "research-question-retrieval", "version": V, "track": "search",
                                          "lexicon_loaded": LEX_OK}, "status": "partial", "question": None,
            "sub_questions": [], "candidates": [], "queries": [],
            "screening": {"criteria_used": {}, "decisions": [], "counts": {}},
            "coverage": {"per_sub_question": [], "gaps": [], "recall_estimate": None},
            "citations": {"graph_available": False, "edges": []}, "conflicts": [],
            "missing": [], "metrics": {}, "baseline": {}, "stopping": {}, "sources": [], "uncertainty": [],
            "pending_human": [], "errors": [], "degradations": [], "changes": [], "logs": [],
            "output_contract_echo": contract,
            "runtime": {"skill_version": V, "started_at": now(), "python": sys.version.split()[0],
                        "network": "disabled", "model_requests": 0}}

def cand_row(c, best, s, why, sn, loc, rc):
    r, bs, b = c["cand"], (best or {}).get("score", 0), best or {}
    fc = len({m["group"] for m in b.get("matched", [])} - {"topic"})
    return {"candidate_id": c["cid"], "title": r.get("title"), "authors": r.get("authors") or [],
            "year": r.get("year"), "venue": r.get("venue"), "doi": r.get("doi"), "url": r.get("url"),
            "source_db": (c["sources"] or [r.get("src")])[0] if (c["sources"] or r.get("src")) else None,
            "retrieved_at": b.get("ts") or now(), "query_id": b.get("q"),
            "sub_question_ids": sorted(set(b.get("sqs") or []) | ({b.get("sq")} - {None})),
            "relevance_score": round(min(1.0, .55 * (bs / (bs + 4.0)) + .3 * min(1.0, fc / 2.0) + .15 * rc), 3),
            "relevance_reason": "; ".join(why[:4]), "evidence_snippet": sn, "evidence_locator": loc,
            "metadata_confidence": "high" if (r.get("doi") and r.get("authors") and r.get("year")) else "medium",
            "screening": {"decision": s["keep"], "flags": s["flags"]}, "provenance": c["members"],
            "flags": sorted(set(s["flags"] + (["duplicate_export_merged"] if c["dup"] else [])))}

def run(a):
    inp, out = Path(a.input).expanduser(), Path(a.output).expanduser()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        out = Path(os.environ.get("TMPDIR", "/tmp")) / "search02-out"
        out.mkdir(parents=True, exist_ok=True)
    rp, case, cerr = out / "result.json", {}, None
    for c in (inp / "case.json", inp / "input" / "case.json"):
        if c.is_file():
            case, cerr = lj(c); break
    if not isinstance(case, dict) and inp.exists():
        for c in sorted(inp.glob("case*.json")):
            case, cerr = lj(c)
            if isinstance(case, dict):
                break
    case = case if isinstance(case, dict) else {}
    contract = case.get("output_contract") or case.get("output_template") or {}
    case_id = case.get("case_id") or case.get("id") or case.get("caseId")
    p = shell(case_id, contract)
    if cerr or not case:
        p["errors"].append({"stage": "load_case", "detail": cerr or "no parsable case.json in %s" % inp})
    wj(rp, fill(dict(p), contract)[0])
    print("[search-02] partial result:", rp, flush=True)
    md = ""
    for c in (inp / "task.md", inp / "TASK.md"):
        if c.is_file():
            md = c.read_text(encoding="utf-8", errors="replace"); break
    h = scan(inp)
    rec = h["r"]
    q, qsrc = q_of(case, md)
    sc = scope_of(case, q, [r["year"] for r in rec if r.get("year")])
    p["question"] = q or None
    p["logs"] = (p["logs"] + h["notes"])[:60]
    p["sources"] = [{"path": f["path"], "bytes": f["bytes"]} for f in h["files"]] + [
        {"path": "case.json", "question_field": qsrc}, {"path": "references/lexicon.md", "loaded": LEX_OK}]
    p["scope_used"] = {"year_from": sc["y0"], "year_to": sc["y1"], "lang": sc["lang"], "max_k": sc["max_k"],
                       "include": sc["inc"], "exclude": sc["exc"], "dbs": sc["dbs"], "inferred_from": sc["src"]}
    if not q:
        p["uncertainty"].append({"topic": "research_question", "detail": "no question text in input",
                                 "impact": "decomposition skipped; supplied records only"})
    fg = facets(q)
    anc = anchors(q, fg)
    subs = decompose(q, fg, anc)
    p["sub_questions"] = subs
    cls_, qlog, seen = dedupe(rec), [], {}
    ix = build_index(cls_)
    k = int(a.max_k or sc["max_k"] or 20)
    wst = execute(ix, subs, cls_, sc, int(a.max_queries), qlog, seen)
    dec, cands = [], []
    for c in cls_:
        r, s, best = c["cand"], screen(c["cand"], sc), seen.get(c["cid"])
        mt = (best or {}).get("matched", [])
        d = "include" if s["keep"] else "exclude"
        if s["keep"] and not best:
            d = "defer"
            s["reasons"] = s["reasons"] + ["screened in but no sub-question match"]
        why = list(s["reasons"])
        if mt:
            why.append("matched %s via %s" % (best.get("sq"), ", ".join(
                "%s:%s" % (m["group"], m["term"]) for m in mt[:4])))
        for m in c["members"]:
            dec.append({"record_id": m["record_id"], "cluster_id": c["cid"], "decision": d,
                        "title": cl(m.get("title"), 120), "source_db": m.get("source_db"), "reasons": why})
        if d == "include":
            sn, loc = snip(r, [m["term"] for m in mt] or tk(r.get("title")))
            rc = 0.0
            if r.get("year") and sc["y0"] and sc["y1"]:
                rc = max(0.0, min(1.0, (r["year"] - sc["y0"]) / max(sc["y1"] - sc["y0"], 1)))
            cands.append(cand_row(c, best, s, why, sn, loc, rc))
    cands.sort(key=lambda x: (-x["relevance_score"], x["candidate_id"]))
    top, low = cands[:k], cands[k:]
    p["candidates"] = top
    p["queries"] = qlog
    cnt = {d: sum(1 for x in dec if x["decision"] == d) for d in ("include", "exclude", "defer")}
    p["screening"] = {"criteria_used": {"year_from": sc["y0"], "year_to": sc["y1"], "lang": sc["lang"],
                                        "include_terms": sc["inc"], "exclude_terms": sc["exc"]},
                      "decisions": dec,
                      "counts": dict(cnt, records_screened=len(dec), below_cutoff=len(low))}
    p["missing"] = [{"record_id": x["record_id"], "title": x["title"], "reason": "; ".join(x["reasons"])}
                    for x in dec if x["decision"] == "defer"]
    per, gaps = [], []
    for s in subs:
        got = [c for c in top if s["sub_question_id"] in c["sub_question_ids"]]
        s["status"] = "covered" if got else "uncovered"
        per.append({"sub_question_id": s["sub_question_id"], "facet": s["facet"], "wave": s["wave"],
                    "status": s["status"], "n_included": len(got), "question": s["question"],
                    "candidate_ids": [c["candidate_id"] for c in got][:10], "query_ids": s["query_ids"]})
        if not got:
            gaps.append({"sub_question_id": s["sub_question_id"],
                         "reason": "no included candidate met this facet", "action": "widen expansion"})
    p["coverage"] = {"per_sub_question": per, "gaps": gaps, "n_records_in_snapshot": len(rec),
                     "n_clusters": len(cls_), "recall_estimate": None,
                     "scope_note": "finite snapshot; recall needs labels/live DB"}
    p["conflicts"] = conflicts(top)
    p["pending_human"] = [{"item": c["conflict_id"], "type": "conflicting_evidence",
                           "detail": "opposite polarity: %s" % ", ".join(c["candidate_ids"]),
                           "action": "read both; decide"} for c in p["conflicts"]]
    n = len(top)
    base = baseline(ix, q, cls_, sc, k) if cls_ else None
    if base:
        bset = set(base["candidate_ids"])
        base["facets"] = sum(1 for x in subs if not bset.isdisjoint(x["evidence_ids"]))
    p["baseline"] = base or {"available": False}
    p["metrics"] = {
        "n_candidates": n, "n_sub_questions": len(subs), "n_sq_with_evidence": len(subs) - len(gaps),
        "sub_question_coverage": round((len(subs) - len(gaps)) / len(subs), 3) if subs else None,
        "n_queries": len(qlog), "n_queries_empty": sum(1 for x in qlog if x["status"] == "empty"),
        "n_raw_records": len(rec), "n_clusters": len(cls_), "n_dup_merged": sum(c["dup"] for c in cls_),
        "doi_wellformed_rate": round(sum(1 for c in top if c.get("doi")) / n, 3) if n else None,
        "snippet_rate": round(sum(1 for c in top if c.get("evidence_snippet")) / n, 3) if n else None,
        "comparison_vs_baseline": {
            "baseline_in_scope_share": (base or {}).get("in_scope_share"),
            "skill_in_scope_share_by_construction": 1.0 if n else None,
            "baseline_facets_covered": (base or {}).get("facets", 0), "skill_facets_covered": len(subs) - len(gaps),
            "baseline_duplicate_exports": (base or {}).get("duplicate_exports_in_returned"),
            "skill_duplicate_exports": 0, "queries": {"baseline": 1, "skill": len(qlog)},
            "note": "same snapshot/k; no labels: facet coverage, in-scope, dup leakage"}}
    p["stopping"] = {"rule": "stop when all SQs covered, a wave adds nothing, or budget ends", "waves": wst,
                     "reason": "all_sub_questions_covered" if not gaps else "gaps_after_wave_3",
                     "queries_executed": len(qlog),
                     "budget": {"max_queries": int(a.max_queries), "model_requests": 0,
                                "elapsed_s": round(time.time() - T0, 2)}}
    p["uncertainty"] += [
        {"topic": "gold_labels", "detail": "no key-paper labels",
         "impact": "P/R/nDCG need labels; structural coverage used"},
        {"topic": "coverage_ceiling", "detail": "%d records in snapshot" % len(rec),
         "impact": "no live DB"}]
    if not LEX_OK:
        p["degradations"].append({"what": "lexicon.md not loaded", "effect": "minimal facet table"})
    if sum(1 for r in rec if not r.get("doi")):
        p["degradations"].append({"what": "records without DOI", "count": sum(1 for r in rec if not r.get("doi")),
                                  "effect": "confidence lowered; no DOI invented"})
    p["status"] = "insufficient_evidence" if (not rec or not top) else ("partial" if (gaps or p["errors"]) else "ok")
    p["changes"] = [{"step": "decompose", "what": "%d sub-questions/%d facets" % (len(subs), len(fg))},
                    {"step": "retrieve", "what": "%d queries" % len(qlog)},
                    {"step": "dedupe", "what": "%d->%d" % (len(rec), len(cls_))},
                    {"step": "rank", "what": "0.55*BM25+0.30*facet+0.15*recency"},
                    {"step": "cut", "what": "kept %d, below %d" % (k, len(low))}]
    p["runtime"].update({"finished_at": now(), "duration_s": round(time.time() - T0, 2), "input_dir": str(inp),
                         "output_dir": str(out)})
    p, mapped = fill(p, contract)
    p["contract_report"] = {"mapped_fields": mapped, "n": len(mapped)}
    wj(rp, p)
    try:
        with (out / "candidates.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(CSVF)
            for c in top:
                w.writerow([c["candidate_id"], c["title"], "; ".join(c["authors"]), c["year"], c["venue"],
                            c["doi"], c["url"], c["source_db"], c["retrieved_at"], c["query_id"],
                            c["relevance_score"], c["relevance_reason"], c["evidence_snippet"],
                            c["evidence_locator"], c["metadata_confidence"], ";".join(c["flags"])])
        wj(out / "query_log.json", {"case_id": case_id, "queries": qlog})
        wt(out / "query_log.jsonl", "".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in qlog))
        wt(out / "screening_log.csv", "record_id,cluster_id,decision,title,source_db,reasons\n" + "".join(
            '"%s","%s","%s","%s","%s","%s"\n' % (d["record_id"], d["cluster_id"], d["decision"],
                                                 str(d["title"]).replace('"', "'"), d["source_db"],
                                                 "; ".join(d["reasons"]).replace('"', "'")) for d in dec))
    except Exception as e:
        p["errors"].append({"stage": "write_artifacts", "detail": str(e)[:200]})
        wj(rp, p)
    print("[search-02] done:", p["status"], "candidates=%d" % len(top), flush=True)
    return p
def selfcheck(inp, out):
    """Deterministic post-run checks: contract, presence, quotes."""
    d = json.load(open(out / "result.json", encoding="utf-8"))
    rec = {r["rid"]: ((r.get("title") or "") + " " + (r.get("abstract") or "")).lower()
           for r in scan(Path(inp).expanduser())["r"]}
    qids = {q["query_id"] for q in d.get("queries") or []}
    issues = []
    for c in d.get("candidates") or []:
        cid = c.get("candidate_id")
        for f in ("title", "source_db", "retrieved_at", "query_id", "relevance_reason", "evidence_snippet"):
            if not c.get(f):
                issues.append({"candidate": cid, "issue": "missing_" + f})
        if c.get("query_id") and c["query_id"] not in qids:
            issues.append({"candidate": cid, "issue": "query_id_not_in_log"})
        if c.get("doi") and not re.match(r"^10\.\d{4,9}/\S+$", c["doi"]):
            issues.append({"candidate": cid, "issue": "malformed_doi"})
        sn = (c.get("evidence_snippet") or "").lower().strip()
        srcs = [rec.get(m["record_id"], "") for m in c.get("provenance") or []]
        if sn and srcs and not any(sn in s for s in srcs if s):
            issues.append({"candidate": cid, "issue": "snippet_not_found_in_source_record"})
    rep = {"status": "pass" if not issues else "warn", "n_issues": len(issues), "issues": issues[:40],
           "candidates": len(d.get("candidates") or []), "queries": len(d.get("queries") or []),
           "contract_fields": len(d.get("output_contract_echo") or {}), "run_status": d.get("status"),
           "screening_records": (d.get("screening") or {}).get("counts", {}).get("records_screened")}
    wj(out / "selfcheck.json", rep)
    print("[search-02] self-check:", rep["status"], "issues=%d" % rep["n_issues"], flush=True)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="research-question-retrieval",
                                 description="Question-driven offline retrieval over a case snapshot")
    ap.add_argument("--input", default="/input", help="input dir")
    ap.add_argument("--output", default="/app/output", help="output dir")
    ap.add_argument("--max-queries", type=int, default=24, help="query budget")
    ap.add_argument("--max-k", type=int, default=0, help="candidate cap; 0=scope")
    ap.add_argument("--self-check", action="store_true", help="verify result")
    ap.add_argument("--version", action="version", version=V)
    a = ap.parse_args(argv)
    try:
        run(a)
        if a.self_check:
            selfcheck(a.input, Path(a.output).expanduser())
    except Exception:
        tb = traceback.format_exc()
        print("[search-02] fatal:", tb, flush=True)
        try:
            rp = Path(a.output) / "result.json"
            Path(a.output).mkdir(parents=True, exist_ok=True)
            cur, _ = lj(rp) if rp.is_file() else (None, None)
            cur = cur if isinstance(cur, dict) else shell(None, {})
            cur["status"] = "partial"
            cur.setdefault("errors", []).append({"stage": "fatal", "detail": cl(tb, 800)})
            cur["runtime"] = {"skill_version": V, "finished_at": now(), "model_requests": 0, "network": "disabled"}
            wj(rp, cur)
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
