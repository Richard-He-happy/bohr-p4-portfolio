#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search-01 literature retrieval CLI."""
import argparse, csv, json, math, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import engine as E
except Exception as exc:
    sys.stderr.write("engine import failed: %s\n" % exc)
    E = None

SKILL = {"name": "traceable-literature-retrieval", "version": "1.0.0"}
T0, BUDGET = time.time(), 780.0
ACR = re.compile(r"([A-Za-z][A-Za-z\-]+(?:\s+[A-Za-z\-]{2,}){0,6})\s*\(([A-Z][A-Za-z0-9\-]{1,10})\)")
SCOPE_KEYS = {"topic", "research_question", "question", "search_topic", "keywords", "include", "exclude",
              "years", "year_from", "year_to", "language", "databases", "db", "max_k", "k", "seeds",
              "known_items"}
COLS = ["rank", "id", "title", "authors", "year", "venue", "doi", "url", "source_db", "sources", "retrieved_at",
        "query_id", "relevance_score", "relevance_reason", "evidence_snippet", "flags"]


def nw(x):
    return re.sub(r"\s+", " ", "" if x is None else str(x)).strip()


def dump(o):
    return json.dumps(o, ensure_ascii=False, default=str)


def atomic_write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def blank():
    return {"case_id": None, "status": "partial", "candidates": [], "queries": [], "screening": {},
            "coverage": {}, "evaluation": {}, "sources": [], "uncertainty": [], "missing": [], "errors": [],
            "degradations": [], "pending_human": [], "runtime": {}, "summary": "",
            "task_understanding": {}, "search_scope": {}, "citation_chaining": {}, "input_inventory": [],
            "skill": SKILL}


def get_ci(d, names):
    low = {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    for n in names:
        if low.get(n.lower()) not in (None, "", [], {}):
            return low[n.lower()]
    return None


def load_case(inp, res):
    inp, case, src = Path(inp), {}, None
    for p in [inp / "case.json"] + sorted(inp.glob("case*.json")) + sorted(inp.rglob("*.json"))[:50]:
        if p.is_file():
            try:
                obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                res["errors"].append({"stage": "case_json", "file": str(p), "error": str(exc)[:120]})
                continue
            if isinstance(obj, dict) and (p.name.lower().startswith("case")
                                          or get_ci(obj, ["output_contract"]) is not None):
                case, src = obj, str(p)
                break
    cid = get_ci(case, ["case_id", "caseId", "case"])
    return case, get_ci(case, ["output_contract"]), (str(cid) if cid is not None else None), src


def al(v):
    if isinstance(v, str):
        return [nw(x) for x in re.split(r"[;,、]", v) if nw(x)]
    return [nw(x if isinstance(x, str) else E.fs(x, 120)) for x in v if x] if isinstance(v, list) else []


def ai(v):
    m = re.search(r"\d{2,4}", str(v))
    return int(m.group(0)) if m else None


def scope_of(case, md):
    sc = {}

    def dig(o, d=0):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() in SCOPE_KEYS and v not in (None, "", [], {}):
                    sc.setdefault(str(k).lower(), v)
                elif isinstance(v, (dict, list)) and d < 3:
                    dig(v, d + 1)
        elif isinstance(o, list) and d < 3:
            for v in o[:20]:
                dig(v, d + 1)

    dig(case)
    topic = next((nw(sc[k]) for k in ("topic", "research_question", "question", "search_topic")
                  if isinstance(sc.get(k), str) and len(nw(sc[k])) > 3), "")
    if not topic:
        x = get_ci(case, ["task_instruction", "instruction", "task"])
        topic = nw(x)[:400] if isinstance(x, str) else (nw(md.splitlines()[0])[:300] if md.strip() else "")
    yrs, yf, yt = sc.get("years"), sc.get("year_from"), sc.get("year_to")
    if isinstance(yrs, dict):
        yf, yt = yrs.get("from") or yrs.get("start") or yf, yrs.get("to") or yrs.get("end") or yt
    elif yrs is not None:
        m = re.findall(r"(1[89]\d{2}|20\d{2})", " ".join(map(str, yrs)) if isinstance(yrs, list) else str(yrs))
        yf, yt = (m[0], m[1]) if len(m) > 1 else ((m[0], yt) if m else (yf, yt))
    raw = sc.get("seeds") or sc.get("known_items") or []
    seeds = [{"doi": E.norm_doi(x if isinstance(x, str) else get_ci(x, ["doi"]))}
             for x in (raw if isinstance(raw, list) else [])[:40]]
    return {"topic": topic, "keywords": al(sc.get("keywords")), "exclude_terms": al(sc.get("exclude")),
            "year_from": ai(yf), "year_to": ai(yt), "languages": al(sc.get("language")),
            "databases": al(sc.get("databases") or sc.get("db")),
            "max_k": ai(sc.get("max_k") or sc.get("k")) or 20, "seeds": seeds}


def variants(term, acr, zh2en):
    out = {term.lower()} | acr.get(term.lower(), set())
    if " " in term:
        out |= {x for x in re.split(r"\W+", term.lower()) if x not in E.STOP and
                (len(x) > 4 or (len(x) > 1 and "\u4e00" <= x[0] <= "\u9fff"))}
    out.add((term[:-1] if term.lower().endswith("s") and len(term) > 4 else term + "s").lower())
    for a, b in (("-", " "), (" ", "-")):
        if a in term:
            out.add(term.replace(a, b).lower())
    for zh, en in zh2en.items():
        if zh in term:
            out |= {en.lower()} | acr.get(en.lower(), set())
    return [x for x in out if len(x) > 1]


def facets_of(scope, ctx, lex, cn):
    out, seen, acr = [], set(), {}
    for g in ACR.finditer(ctx[:60000]):
        lng, ab = nw(g.group(1)).lower(), g.group(2).lower()
        if len(ab) >= 2 and len(lng) > len(ab) + 3:
            acr.setdefault(ab, set()).add(lng)
            acr.setdefault(lng, set()).add(ab)
    probe = (scope["topic"] + " " + ctx[:8000]).lower()
    groups = [("research_problem", scope["keywords"])] + \
             [(g["label"], g["terms"]) for g in (lex or []) if any(t in probe for t in g["terms"])]
    core = []
    for p in re.split(r"[;；,，/、:]|\band\b|\bwith\b|\bfor\b|\bof\b|\bin\b|\bon\b", scope["topic"] or ""):
        if len(nw(p)) > 3:
            core += variants(nw(p), acr, cn or {})
    groups[0] = ("research_problem", core + scope["keywords"])
    for label, terms in groups:
        terms = [nw(x).lower() for x in terms if len(nw(x)) > 1]
        k = tuple(sorted(set(terms)))
        if k and k not in seen:
            seen.add(k)
            out.append({"label": label, "terms": list(dict.fromkeys(terms))[:20]})
    return out[:8]


def plan_of(scope, facets, observed, merged):
    plan = []

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    flt = {k: scope[k] for k in ("year_from", "year_to", "languages", "databases", "exclude_terms")}

    def add(stage, raw, groups):
        n = sum(1 for w in merged if all(any(E.tmatch(
            (w["title"] + " " + w["keywords"] + " " + w["abstract"]).lower(), x)
            for x in facets[g]["terms"]) for g in groups)) if groups else None
        plan.append({"query_id": "q%d" % (len(plan) + 1), "stage": stage, "raw": raw,
                     "facets": [facets[g]["label"] for g in groups], "hits": n, "filters": flt,
                     "db": scope["databases"] or ["provided_corpus"], "retrieved_at": ts,
                     "status": "ok" if n else "empty"})
    if facets:
        add("core", scope["topic"] or facets[0]["label"], [0])
    for i in range(1, len(facets)):
        add("facet", " OR ".join(facets[i]["terms"][:6]), [i])
    seen_q = set()
    for c in observed[:15]:
        seen_q.add(c["query_id"])
    plan += [{"query_id": c["query_id"], "stage": "replay_source_query", "raw": c.get("raw"), "facets": [],
              "hits": c.get("hits"), "status": "recorded", "target_db": [c.get("db")],
              "source_file": c.get("source_file"), "retrieved_at": c.get("retrieved_at")}
             for c in [x for i, x in enumerate(observed[:15]) if x["query_id"] not in
                       {y["query_id"] for y in observed[:i]}]]
    return plan


def chain(merged, scope, corp):
    idx = {w["doi"]: i for i, w in enumerate(merged) if w.get("doi")}
    ids = list(dict.fromkeys([s["doi"] for s in scope["seeds"] if s.get("doi")]
                             + [s["doi"] for s in corp.get("seeds", []) if s.get("doi")]))
    found, missing = [d for d in ids if d in idx], [d for d in ids if d not in idx]
    edges = [e for e in corp.get("edges", []) if e.get("from") in idx]
    nbr = {}
    for e in edges:
        nbr.setdefault(e["to"], set()).add(e["from"])
    for w in merged:
        w["route"] = "citation_chaining" if nbr.get(w.get("doi") or "") else "query_match"
    for d in found:
        merged[idx[d]]["route"] = "seed_direct"
    return {"n_seed_identifiers": len(ids), "seeds_found": found, "seeds_missing": missing,
            "n_reference_edges": len(edges),
            "n_chained": sum(1 for w in merged if w.get("route") == "citation_chaining")}


def evaluation(cands, ch, removed):
    c = lambda w: len(w.get("matched_facets") or []) / max(1, len(w.get("matched_facets") or []) + 1)
    lab = [2 if c(w) >= .6 else (1 if c(w) >= .5 else 0) for w in cands]
    d = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(lab))
    i2 = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(sorted(lab, reverse=True)))
    return {"p_at_k": round(sum(1 for x in lab if x) / max(1, len(lab)), 4),
            "ndcg_at_k": round(d / i2, 4) if i2 else None,
            "known_item_recall": round(len(ch["seeds_found"]) / ch["n_seed_identifiers"], 4)
            if ch["n_seed_identifiers"] else None,
            "n_dedup_removed": removed}


def fill_contract(spec, data):
    """Backfill every output_contract key; unknown keys kept, missing values null/[]."""
    if isinstance(spec, dict):
        out = {}
        for k, v in spec.items():
            key = str(k)
            if key in data:
                out[key] = data[key]
            elif isinstance(v, (dict, list)):
                out[key] = fill_contract(v, data)
            elif isinstance(v, bool) or (isinstance(v, str) and len(v) < 60 and not re.search(r"[。:：|]", v)):
                out[key] = v
            else:
                out[key] = None
        return out
    if isinstance(spec, list):
        if spec and all(isinstance(x, str) for x in spec[:20]):
            return {str(x): data.get(str(x), []) for x in spec}
        return [fill_contract(x, data) for x in spec[:20]]
    return spec if isinstance(spec, (int, float)) else None


def candidate(w, rank):
    snip = next((x for x in re.split(r"(?<=[.!?])\s+", w["abstract"])
                 if any(E.has(x.lower(), t) for t in (w.get("matched_terms") or []))), "")[:300]
    mt, srcs = w.get("matched_facets") or [], w.get("sources") or [w.get("source_db")]
    flags = ["missing_" + k for k in ("doi", "year", "venue", "abstract", "retrieved_at") if not w.get(k)]
    flags += ["single_source"] if len(srcs) < 2 else []
    flags += ["year_conflict"] if w.get("conflict_year") else []
    flags += ["missing_query_id"] if not w.get("query_ids") else []
    return {"id": "c%03d" % rank, "rank": rank, "title": w["title"], "authors": w.get("authors") or [],
            "year": w.get("year"), "venue": w.get("venue") or None, "doi": w.get("doi"), "url": w.get("url"),
            "source_db": srcs[0], "sources": srcs, "retrieved_at": w.get("retrieved_at"),
            "query_id": (w.get("query_ids") or [None])[0], "route": w.get("route", "query_match"),
            "relevance_score": w.get("relevance_score"), "matched_facets": mt,
            "relevance_reason": "%d/%d facets [%s]; terms: %s; route=%s; %d rec from %s" % (
                len(mt), len(mt) + len(w.get("missing_facets") or []), ", ".join(mt) or "none",
                ", ".join((w.get("matched_terms") or [])[:5]) or "none", w.get("route", "query_match"),
                w.get("n_records") or 1, ", ".join(srcs)),
            "evidence_snippet": snip or w["title"], "flags": flags,
            "provenance": w.get("provenance") or []}


def coverage(scope, facets, merged, cands, corp, ch, removed):
    miss = lambda k: sum(1 for c in cands if not c.get(k))
    cov = {f["label"]: sum(1 for c in cands if f["label"] in (c.get("matched_facets") or [])) for f in facets}
    return {"k_returned": len(cands), "n_records_read": len(corp["works"]), "n_unique": len(merged),
            "n_duplicates_merged": removed, "facet_coverage": cov,
            "uncovered_facets": [k for k, v in cov.items() if not v],
            "metadata_gaps": {k + "_missing": miss(k) for k in ("doi", "year", "venue", "retrieved_at")},
            "seed_coverage": {"n_seed_identifiers": ch["n_seed_identifiers"],
                              "found": len(ch["seeds_found"]), "missing": ch["seeds_missing"]},
            "recall_estimate": round(len(ch["seeds_found"]) / ch["n_seed_identifiers"], 4)
            if ch["n_seed_identifiers"] else None,
            "sources_used": sorted({x["source_db"] for x in cands})}


def write_outputs(out, res):
    out = Path(out)
    atomic_write(out / "result.json", dump(res))
    rows = [{k: (json.dumps(c[k], ensure_ascii=False) if isinstance(c[k], (list, dict)) else c[k])
             for k in COLS if k in c} for c in res["candidates"]]
    with (out / "candidates.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    atomic_write(out / "candidates.json", dump(res["candidates"]))
    atomic_write(out / "query_log.json", dump(res["queries"]))


def run(inp, out, max_k=None):
    res = blank()
    case, contract, cid, src = load_case(inp, res)
    res.update({"case_id": cid, "output_contract": contract})
    res.update(fill_contract(contract, res) or {})
    atomic_write(Path(out) / "result.json", dump(res))            # step 1: legal partial result
    md = ""
    for n in ("task.md", "TASK.md"):
        try:
            if (Path(inp) / n).is_file():
                md = (Path(inp) / n).read_text(encoding="utf-8", errors="replace")[:60000]
        except Exception:
            pass
    scope = scope_of(case, md)
    if max_k:
        scope["max_k"] = max_k
    res["search_scope"] = scope
    corp = E.new_corpus()
    try:
        E.scan(inp, corp)
    except Exception as exc:
        res["errors"].append({"stage": "scan", "error": str(exc)[:250]})
    lex, cn = E.load_lexicon()
    facets = facets_of(scope, md + " " + json.dumps(case, ensure_ascii=False)[:20000], lex, cn)
    plan = plan_of(scope, facets, corp["queries"], corp["works"])
    merged, removed = E.dedupe(corp["works"])
    ch = chain(merged, scope, corp)
    ranked = E.rank(merged, facets) if facets else merged
    kept, excl = E.screen(ranked, scope, scope["max_k"])
    cands = [candidate(w, i + 1) for i, w in enumerate(kept)]
    res.update({
        "candidates": cands, "queries": plan, "citation_chaining": ch,
        "screening": {"included": len(kept), "excluded": len(excl), "excluded_items": excl[:40]},
        "coverage": coverage(scope, facets, merged, cands, corp, ch, removed),
        "evaluation": evaluation(cands, ch, removed),
        "sources": [{"source_db": d, "n": sum(1 for w in corp["works"] if w["source_db"] == d)}
                    for d in sorted({w["source_db"] for w in corp["works"]})],
        "degradations": [{"stage": "offline_execution", "note": "no live database query; retrieval runs over the "
                                                                 "records supplied in the input"}]})
    res["uncertainty"] = [
        "Offline: %d recs/%d files; live-db recall unknown."
        % (len(corp["works"]), len(corp["inventory"])),
        "hits count provided records, not DB totals."]
    res["missing"] = ([{"item": "seed not in records", "id": d} for d in ch["seeds_missing"][:15]]
                      + [{"item": "not ingested", "file": u["file"], "reason": u["reason"]}
                         for u in corp["unparsed"][:10]])
    if not contract:
        res["pending_human"].append("output_contract missing: add it and re-run.")
    if not cands:
        res["pending_human"].append("No candidate passed screening: live search expected, or no records.")
    if ch["seeds_missing"]:
        res["pending_human"].append("Verify %d missing seed id(s) online." % len(ch["seeds_missing"]))
    res["status"] = ("input_error" if not corp["inventory"] else "insufficient_evidence" if not corp["works"]
                     else "partial" if (not contract or not cands or res["errors"] or res["missing"]
                                        or res["pending_human"]) else "ok")
    res["summary"] = ("%d query step(s) (%d replayed), %d records, %d unique (%d dup), %d cand. of k=%d, "
                      "%d facet(s) (%d uncovered), %d seed id(s); %s." %
                      (len(plan), sum(1 for q in plan if q["stage"] == "replay_source_query"), len(corp["works"]),
                       len(merged), removed, len(cands), scope["max_k"], len(facets),
                       len(res["coverage"].get("uncovered_facets") or []), len(ch["seeds_found"]), res["status"]))
    res["runtime"] = {"elapsed_s": round(time.time() - T0, 2), "budget_s": BUDGET,
                      "python": sys.version.split()[0], "network_used": False,
                      "generated_at": datetime.now(timezone.utc).isoformat()}
    res["artifacts"] = {k: str(Path(out) / v) for k, v in (("result", "result.json"),
                                                           ("candidates_csv", "candidates.csv"),
                                                           ("candidates_json", "candidates.json"),
                                                           ("query_log", "query_log.json"))}
    res.update(fill_contract(contract, res) or {})
    res["self_check"] = {"contract_backfilled": bool(contract) and all(k in res for k in contract),
                         "candidates_have_provenance": all(c["sources"] and c["relevance_reason"] for c in cands),
                         "retrieved_at_or_flag": all(c.get("retrieved_at") or "missing_retrieved_at" in c["flags"]
                                                     for c in cands),
                         "status_enum": res["status"] in ("ok", "partial", "insufficient_evidence",
                                                          "input_error")}
    write_outputs(out, res)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="search-01 literature retrieval")
    ap.add_argument("--input", default="/input", help="case dir")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--max-k", type=int, default=None, help="candidate cap")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = run(Path(a.input), Path(a.output), a.max_k)
        if not a.quiet:
            print(res["summary"])
    except Exception as exc:
        sys.stderr.write("fatal: %s\n" % exc)
        try:
            Path(a.output).mkdir(parents=True, exist_ok=True)
            atomic_write(Path(a.output) / "result.json", dump(
                {"case_id": None, "status": "input_error", "candidates": [], "queries": [], "sources": [],
                 "uncertainty": ["run aborted before retrieval"], "errors": [
                     {"stage": "fatal", "error": "%s: %s" % (type(exc).__name__, str(exc)[:300])}],
                 "degradations": [], "pending_human": ["inspect the error and re-run"],
                 "runtime": {"elapsed_s": round(time.time() - T0, 2)}}))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
