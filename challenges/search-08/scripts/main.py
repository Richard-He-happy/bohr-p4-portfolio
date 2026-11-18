#!/usr/bin/env python3
"""CLI of the systematic search & screening skill.

run: /input snapshot -> criteria -> query log -> dedup -> title/abstract screening with reason codes
and verbatim evidence -> arbitration -> audit; writes result.json (all output_contract fields) +
candidates/labels/arbitration CSVs + logs to /app/output. --check verifies. Offline; exit code 0."""
import argparse, csv, json, os, re, sys, time, zipfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import V, arb, bcr, check, collect, ddp, isrec, nrec, nt, rt, scr, tk, ws, ywin  # noqa: E402

SEM = [(g.partition("=")[0], g.partition("=")[2].split(",")) for g in
       ("candidates=candidate,record,paper,literature,result,article,hit;queries=quer;"
        "screening=screen,label,decision,exclud;dedup=dedup,duplicate,merge,cluster;arbitration=conflict,arbitr,disagree;"
        "audit=audit,trace,log,flow;coverage=coverage,gap,missing;criteria=criteria,criterion,standard,protocol;"
        "metrics=metric,evaluat,benchmark,gain,baseline;counts=count,number,stat,summary;sources=source,database;"
        "uncertainty=uncertain,limitation,risk,recall;status=status,state").split(";")]


def tfile(p):

    e = p.suffix.lower()
    try:
        if e == ".docx":
            with zipfile.ZipFile(p) as z:
                x = z.read("word/document.xml").decode("utf-8", "replace")
            return ws(re.sub(r"<[^>]+>", " ", re.sub(r"</w:p>", " ", x)))
    except Exception:
        return ""
    return rt(p)


def dj(o, p):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2, default=str), "utf-8")
    os.replace(t, p)


def wcsv(p, rows, default):
    cols = list(rows[0].keys()) if rows else default
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("; ".join if k == "authors" else "|".join)(map(str, r[k]))
                        if isinstance(r.get(k), list) else r.get(k) for k in cols})


def kap(a, b):
    n = len(a)
    if not n:
        return None
    pa = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in set(a) | set(b))
    return 1.0 if pe >= 1 else round((pa - pe) / (1 - pe), 4)


def fillc(contract, pay):
    """Backfill every input output_contract field: keys unchanged, unknown keys kept, missing null/[]/{}."""
    keys = [k if isinstance(k, str) else (k.get("name") or k.get("field"))
            for k in (list(contract) if isinstance(contract, dict) else list(contract or []))]
    out = {}
    for k in [x for x in keys if x]:
        low = str(k).lower().replace("-", "_")
        v = next((pay.get(t) for t, w in SEM if any(x in low for x in w)), None)
        if v is None:
            sp = contract.get(k) if isinstance(contract, dict) else None
            ty = str(sp.get("type", "")).lower() if isinstance(sp, dict) else ""
            v = (sp or {}).get("default", [] if ("arr" in ty or "list" in ty) else ({} if "obj" in ty else None))
        out[k] = v
    return out, [x for x in keys if x]


def scan(case):

    inc, exc, sc, qn, seen, q = [], [], {}, "", 0, [case]
    ks = ("research_question", "question", "topic", "task_instruction", "objective", "aim", "instruction")
    while q and seen < 400:
        d, seen = q.pop(0), seen + 1
        if isinstance(d, dict):
            for k, v in d.items():
                kk = str(k).lower().replace("-", "_")
                if isinstance(v, list) and ("include" in kk or "inclusion" in kk) and "exclude" not in kk and "exclusion" not in kk:
                    inc += [str(x) for x in v if str(x).strip()]
                elif isinstance(v, list) and ("exclude" in kk or "exclusion" in kk):
                    exc += [str(x) for x in v if str(x).strip()]
                elif isinstance(v, (dict, list)):
                    q.append(v)
                if isinstance(v, dict) and ("scope" in kk or "constraints" in kk):
                    sc = v
                qn = v if (kk in ks and isinstance(v, str) and len(v) > len(qn)) else qn
        elif isinstance(d, list):
            q += [v for v in d if isinstance(v, (dict, list))]
    return [ws(x) for x in dict.fromkeys(inc)], [ws(x) for x in dict.fromkeys(exc)], sc, ws(qn)


def run(a):
    t0 = time.time()
    out = Path(a.output)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / ".w").write_text("1")
        (out / ".w").unlink()
    except Exception:
        out = Path.cwd() / "output"
        out.mkdir(parents=True, exist_ok=True)
    errs, unc, res = [], [], out / "result.json"
    dj({"case_id": None, "status": "partial", "note": "partial written before pipeline", "errors": [],
        "uncertainty": ["pipeline still running"]}, res)
    inp, case = Path(a.input), None
    for cp in dict.fromkeys([inp / "case.json"] + (sorted(inp.rglob("case*.json")) if inp.exists() else [])):
        try:
            case = json.loads(rt(cp))
            break
        except Exception as e:
            errs.append({"stage": "input", "message": f"{cp.name} unparsable: {e}"}) if cp.exists() else None
    if not isinstance(case, dict):
        errs.append({"stage": "input", "message": f"no parsable case.json under {inp}"})
        case = {}
    cid = case.get("case_id") or case.get("caseId") or case.get("id")
    contract = case.get("output_contract") or case.get("outputContract") or {}
    inc, exc, sc, qn = scan(case)
    cr = bcr(inc, exc)
    lo, hi = ywin(sc, cr)
    dbs = next((str(v)[:80] for k, v in (sc.items() if isinstance(sc, dict) else []) if "db" in str(k).lower()),
               "unspecified")
    pf, keys = fillc(contract, {t: [] for t, _ in SEM})
    part = {"case_id": cid, "status": "partial", "research_question": qn, "criteria_version": cr["version"],
            "criteria_fingerprint": cr["fingerprint"], "errors": errs, "uncertainty": ["run in progress"],
            "generated_by": "systematic-screening-audit " + V}
    part.update(pf)
    dj(part, res)

    raw = collect(inp)
    if not any(isrec(r) for r, _ in raw) and inp.exists():
        for p in sorted(x for x in inp.rglob("*") if x.is_file() and x.suffix.lower() == ".docx"):
            t = tfile(p)
            if len(t) > 200:
                raw.append(({"title": p.stem.replace("_", " "), "abstract": t[:4000], "source_db": "local_material"},
                            str(p.relative_to(inp))))
    recs, seen = [], set()
    for i, (r, s) in enumerate([x for x in raw if isrec(x[0])], 1):
        rr = nrec(r, s, i, dbs)
        key = (rr["doi"], nt(rr["t"]))
        if key in seen and not rr["doi"]:
            continue
        seen.add(key)
        recs.append(rr)
    if not recs:
        unc.append("no candidate records parsed from the input snapshot")
    qt = tk(qn)[:8]
    qm = {}
    for r in recs:
        qm.setdefault(r["qid"] or "QUERY-UNSPECIFIED", []).append(r["id"])
    qm = qm or {"QUERY-NONE": []}
    qs = [{"query_id": k, "db": dbs, "raw": " ".join(qt) if k.startswith("QUERY-") else k,
           "hits": len(v), "record_ids": v[:200], "expanded": " AND ".join(qt[:4]) or None,
           "filters": {"years": [lo, hi] if lo else None, "language": sc.get("lang") if isinstance(sc, dict) else None},
           "status": "returned_in_snapshot" if v else "not_executed_offline",
           "error": None if v else "no records for this query",
           "retrieved_at": next((x["rat"] for x in recs if x["rat"] and (x["qid"] or "QUERY-UNSPECIFIED") == k), None)}
          for k, v in qm.items()]
    if any(x["status"] != "returned_in_snapshot" for x in qs):
        unc.append("some planned queries have no retrieved records in the snapshot; no live database was queried")
    dd = ddp(recs)
    uniq = [recs[i] for i in dd["keep"]]
    dmap = {m: (c["keeper"], c["cluster_id"]) for c in dd["clusters"] for m in c["members"][1:]}
    cells = [scr(r, cr, lo, hi) for r in uniq]
    for r in recs:
        if r["id"] in dmap:
            kp, cl = dmap[r["id"]]
            cells.append({"record_id": r["id"], "decision_A": "exclude", "decision_B": "exclude", "final": "exclude",
                          "reason_codes": ["DUP-MERGED"], "include_coverage": 0.0, "matched_criteria": [],
                          "flags": ["DUPLICATE"], "score": 0.0, "confidence": 0.9, "hard_exclusions": [],
                          "evidence": [{"criterion": "SYS-DUP", "field": "metadata", "cue": cl, "quote":
                                        f"merged into {kp}", "locator": "dedup:" + cl}]})
    arbs = []
    for c in cells:
        if "final" in c:
            continue
        c["final"], c["arbitration_rule"], c["arbitration_basis"] = arb(c)
        if c["decision_A"] != c["decision_B"]:
            arbs.append({"conflict_id": f"C{len(arbs)+1:03d}", "record_id": c["record_id"],
                         "annotator_A": c["decision_A"], "annotator_B": c["decision_B"],
                         "conflict_type": ("threshold_policy" if "uncertain" in (c["decision_A"], c["decision_B"])
                                           else "criteria_boundary"), "include_coverage": c["include_coverage"],
                         "rule": c["arbitration_rule"], "basis": c["arbitration_basis"], "final": c["final"],
                         "requires_human": c["final"] == "pending_human" or c["confidence"] < 0.5,
                         "arbiter": "rule-based arbitration policy v1"})
    cnt = {"retrieved_total": len(recs), "unique_after_dedup": len(uniq),
           "duplicates_removed": len(dd["duplicates_removed"]), "screened_total": len(cells),
           "include": sum(c.get("final") == "include" for c in cells),
           "exclude": sum(c.get("final") == "exclude" for c in cells),
           "pending_human": sum(c.get("final") == "pending_human" for c in cells), "conflicts": len(arbs)}
    ok1 = cnt["retrieved_total"] == cnt["unique_after_dedup"] + cnt["duplicates_removed"]
    ok2 = cnt["screened_total"] == cnt["include"] + cnt["exclude"] + cnt["pending_human"]
    for ok, m in ((ok1, "dedup count closure"), (ok2, "screening count closure")):
        if not ok:
            errs.append({"stage": "audit", "message": m + " failed"})
    byid = {r["id"]: r for r in recs}
    cands = []
    for i, c in enumerate(sorted([x for x in cells if x.get("final") == "include"], key=lambda x: -x["score"]), 1):
        r, e = byid[c["record_id"]], (c["evidence"][0] if c["evidence"] else {})
        cands.append({"rank": i, "id": r["id"], "title": r["t"], "authors": r["au"], "year": r["y"], "venue": r["v"],
                      "doi": r["doi"] or None, "url": r["u"] or None, "source_db": r["db"], "query_id": r["qid"] or None,
                      "retrieved_at": r["rat"] or None, "source_file": r["src"], "relevance_score": c["score"],
                      "relevance_reason": c["reason_codes"][0], "matched_criteria": c["matched_criteria"],
                      "evidence_snippet": e.get("quote"), "evidence_locator": e.get("locator"),
                      "metadata_confidence": c["confidence"], "flags": c["flags"]})

    met = {"records_per_second": round(len(cells) / max(0.001, time.time() - t0), 2),
           "human_review_load": round((cnt["pending_human"] + cnt["conflicts"]) / max(1, len(cells)), 3),
           "criteria_traceability": round(sum(1 for c in cells if c["matched_criteria"] or c["hard_exclusions"]) /
                                          len(cells), 3) if cells else None,
           "evidence_rate": round(sum(1 for c in cells if any(e.get("quote") for e in c["evidence"])) /
                                  max(1, len(cells)), 3),
           "kappa_A_B": kap([c["decision_A"] for c in cells], [c["decision_B"] for c in cells]),
           "gold_labels_present": any(byid[c["record_id"]].get("gold") is not None for c in cells),
           "note": "no gold labels in snapshot: no accuracy gain claimed; base-Agent contrast is the platform's"}
    srcs = sorted({r["src"] for r in recs})
    audit = {"pipeline": "retrieval->dedup->screening->arbitration->final","closure": {"dedup_ok": ok1, "screening_ok": ok2, "retrieved=unique+duplicates": ok1,
                         "screened=include+exclude+pending": ok2},
             "per_query_hits": {x["query_id"]: x["hits"] for x in qs}, "input_files": srcs,
             "criteria_version": cr["version"], "fingerprint": cr["fingerprint"],
             "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0))}
    cov = {"files": srcs, "no_abstract": sum(not r["ab"] for r in recs), "no_doi": sum(not r["doi"] for r in recs),
           "no_year": sum(not r["y"] for r in recs), "no_language": sum(not r["lg"] for r in recs),
           "near_miss_not_merged": len(dd["near_misses_not_merged"]), "recall_estimate": None,
           "recall_basis": "finite snapshot; no live database, so global recall is not estimable",
           "gaps": ["no live query execution", "full-text screening out of scope", "pdf material not parsed"]}
    disc = ("Deterministic criteria matcher over title/abstract. A (strict) and B (lenient, >=50% coverage) are "
            "PRE-DECLARED RULE CONFIGURATIONS, not human reviewers; every include needs confirmation.")
    for c in cells:
        c["evidence_quote"] = c["evidence"][0]["quote"] if c["evidence"] else ""
    status = "input_error" if (cid is None and not case) else ("insufficient_evidence" if not recs
                                                              else ("partial" if errs else "ok"))
    result = {"case_id": cid, "status": status, "research_question": qn, "criteria_version": cr["version"],
              "criteria_fingerprint": cr["fingerprint"],
              "method_disclosure": {"engine": "deterministic rule-based criteria matcher (offline, stdlib)",
                                    "annotators": "A=strict, B=lenient rule configs (NOT human annotators)",
                                    "live_database": False, "recall_claim": "none (finite snapshot)", "note": disc},
              "sources": [{"source": s, "type": Path(s).suffix.lstrip(".") or "unknown",
                           "records": sum(r["src"] == s for r in recs)} for s in srcs],
              "uncertainty": unc + ["records lacking abstract/DOI/year are flagged per record",
                                    "no full-text screening was performed"],
              "pending_human": [{"record_id": c["record_id"], "reason": c.get("arbitration_rule"),
                                 "decision_A": c["decision_A"], "decision_B": c["decision_B"]}
                                for c in cells if c.get("final") == "pending_human"],
              "errors": errs, "degradations": [],
              "changes": [{"change": "criteria operationalized into rule cues", "fingerprint": cr["fingerprint"],
                           "criteria_version": cr["version"]}],
              "runtime": {"skill_version": V, "elapsed_s": round(time.time() - t0, 2),
                          "python": sys.version.split()[0], "budgets": [64,900]},
              "candidates": cands, "queries": qs, "screening": cells,
              "dedup": {"clusters": dd["clusters"], "duplicates_removed": dd["duplicates_removed"],
                        "near_misses_not_merged": dd["near_misses_not_merged"],
                        "removed_count": len(dd["duplicates_removed"])},
              "arbitration": arbs, "counts": cnt, "audit": audit, "coverage": cov, "metrics": met,
              "criteria": {"version": cr["version"], "fingerprint": cr["fingerprint"], "include": cr["include"],
                           "exclude": cr["exclude"], "year_window": [lo, hi],
                           "operationalization": "criterion text -> cue tokens (references/criteria-codes.md)"}}
    fl, keys = fillc(contract, result)
    for k2, v2 in fl.items():
        if result.get(k2) in (None, [], {}):
            result[k2] = v2
    result["contract_fields_filled"] = keys
    result["contract_fields_missing"] = [x for x in keys if x not in result]
    art = {}
    try:
        wcsv(out / "candidates.csv", cands, ["id", "title", "authors", "year", "venue", "doi", "url", "source_db",
                                            "query_id", "retrieved_at", "relevance_score", "relevance_reason",
                                            "matched_criteria", "evidence_snippet", "metadata_confidence", "flags"])
        wcsv(out / "screening_labels.csv", cells, ["record_id", "decision_A", "decision_B", "final", "reason_codes",
                                                  "matched_criteria", "include_coverage", "score", "confidence",
                                                  "flags", "evidence_quote"])
        wcsv(out / "arbitration.csv", arbs, ["conflict_id", "record_id", "annotator_A", "annotator_B",
                                             "conflict_type", "rule", "basis", "final", "requires_human", "arbiter"])
        for nm, o in (("query_log.json", {"case_id": cid, "queries": qs}),
                      ("dedup_log.json", dict(dd, case_id=cid)), ("audit.json", dict(audit, case_id=cid))):
            dj(o, out / nm)
        art = {"candidates_csv": "candidates.csv", "screening_labels_csv": "screening_labels.csv",
               "arbitration_csv": "arbitration.csv", "query_log_json": "query_log.json",
               "dedup_log_json": "dedup_log.json", "audit_json": "audit.json"}
    except Exception as e:
        errs.append({"stage": "write_artifacts", "message": str(e)})
    result.update({"artifacts": art, "errors": errs})
    dj(result, res)
    print(f"[done] status={status} include={cnt['include']} exclude={cnt['exclude']} pending={cnt['pending_human']} "
          f"candidates={len(cands)} -> {res}", flush=True)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="Offline systematic search & screening: writes "
                               "result.json, candidates.csv, screening_labels.csv, arbitration.csv, query/dedup/audit "
                               "logs. --check verifies a finished run.")
    ap.add_argument("-i", "--input", default=os.environ.get("SCREENING_INPUT", "/input"), help="case dir (/input)")
    ap.add_argument("-o", "--output", default=os.environ.get("SCREENING_OUTPUT", "/app/output"),
                    help="output dir (/app/output)")
    ap.add_argument("--check", action="store_true", help="only verify an existing run in the output dir")
    ap.add_argument("--version", action="version", version="systematic-screening-audit " + V)
    a = ap.parse_args(argv)
    if not a.check:
        return run(a)
    rep = check(Path(a.input), Path(a.output))
    try:
        dj(rep, Path(a.output) / "verification_report.json")
    except Exception:
        pass
    for c in rep["checks"]:
        print(("PASS " if c["pass"] else "FAIL ") + c["check"] + ("" if c["pass"] else f"  << {c['detail']}"))
    s = rep.get("summary", {})
    print(f"[verify] {s.get('passed', 0)}/{s.get('checks', 0)} checks passed; status={rep['status']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        for p in (Path(os.environ.get("SCREENING_OUTPUT", "/app/output")) / "result.json", Path.cwd() / "result.json"):
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                dj({"case_id": None, "status": "partial",
                    "errors": [{"stage": "fatal", "message": f"{type(e).__name__}: {e}"}],
                    "uncertainty": ["pipeline crashed; partial result only"]}, p)
                break
            except Exception:
                continue
        print(f"[fatal] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
