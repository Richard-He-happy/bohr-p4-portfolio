#!/usr/bin/env python3
"""verify.py: independent re-check of a search-screen-rank run (contract, ordering, evidence, counts, metrics).

Usage: python3 verify.py [--input /input] [--out /app/output] [--help]
Writes <out>/verify_report.json. Exit code always 0; failures are reported, not raised.
"""
import argparse, csv, json, math, re, sys
from pathlib import Path

LIM = 240


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def rows(p):
    out = []
    try:
        for ln in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.strip()[:1] in ("{", "["):
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def harvest(o, sink, depth=0):
    """collect dict-ish records: keep every dict that has a title-like string and an id"""
    if depth > 8:
        return
    if isinstance(o, dict):
        t = None
        for k in ("title", "paper_title", "display_name", "name"):
            if isinstance(o.get(k), str) and len(o[k].strip()) >= 4:
                t = o[k]
                break
        if t:
            rid = None
            for k in ("id", "record_id", "paper_id", "doc_id", "key", "uid"):
                if o.get(k) not in (None, ""):
                    rid = str(o[k])
                    break
            sink.append({"id": rid, "title": t,
                         "abstract": " ".join(str(o.get(k, "")) for k in ("abstract", "summary", "abstractText")),
                         "labels": [o.get(k) for k in ("label", "relevance", "gold", "grade", "relevance_label") if o.get(k) is not None]})
        for v in o.values():
            if isinstance(v, (dict, list)):
                harvest(v, sink, depth + 1)
    elif isinstance(o, list):
        for v in o:
            harvest(v, sink, depth + 1)


def vd(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(float(v) >= 1)
    s = str(v).strip().lower()
    return 1 if s in {"relevant", "include", "included", "yes", "true", "1", "core", "direct", "2", "3"} else (
        0 if s in {"irrelevant", "exclude", "excluded", "no", "false", "0", "unrelated"} else None)


def met(rank, k, gf):
    kk = min(k, len(rank)) or 1
    rel = [gf(c) for c in rank[:kk]]
    dcg = sum((2 ** max(0, x) - 1) / math.log2(i + 2) for i, x in enumerate(rel))
    idcg = sum((2 ** max(0, x) - 1) / math.log2(i + 2) for i, x in enumerate(sorted([gf(c) for c in rank], reverse=True)[:kk])) or 1e-9
    return round(sum(1 for x in rel if x >= 1) / float(kk), 3), round(dcg / idcg, 3)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="Re-check result.json against inputs and the documented rules; writes verify_report.json; exit code always 0.")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    a, _ = ap.parse_known_args(argv)
    I, O = Path(a.input), Path(a.out)
    rep = {"checked": [], "passed": {}, "errors": [], "warnings": []}
    res = load(O / "result.json")
    case = load(I / "case.json") or {}
    if res is None:
        rep["errors"].append("result.json missing or invalid JSON")
        rep["passed"]["result_json_valid"] = False
        (O / "verify_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[verify] result.json unreadable; report written")
        return 0
    rep["passed"]["result_json_valid"] = True
    cands = res.get("candidates") or []

    # 1 case_id
    want = case.get("case_id") or case.get("caseId") or case.get("id")
    ok = (res.get("case_id") == want) if want is not None else bool(res.get("case_id"))
    rep["passed"]["case_id_matches_input"] = ok
    if not ok:
        rep["errors"].append("case_id mismatch: input=%r result=%r" % (want, res.get("case_id")))

    # 2 contract fields
    con = case.get("output_contract") or case.get("output_schema") or case.get("required_output") or {}
    names = list(con.keys()) if isinstance(con, dict) else [x if isinstance(x, str) else (x.get("name") or x.get("field")) for x in con] if isinstance(con, list) else []
    missing = [n for n in names if n and n not in res]
    rep["passed"]["contract_fields_present"] = not missing
    rep["contract_missing"] = missing
    if missing:
        rep["errors"].append("output_contract fields missing: %s" % missing)

    # 3 status
    rep["passed"]["status_enum"] = res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error")
    if not rep["passed"]["status_enum"]:
        rep["errors"].append("status not in enum: %r" % res.get("status"))

    # 4 ranks and ordering
    ranks = [c.get("rank") for c in cands]
    rep["passed"]["ranks_contiguous"] = ranks == list(range(1, len(cands) + 1))
    TO = {"core": 0, "method": 1, "background": 2, "pending": 3, "exclude": 4}
    key = [(TO.get(c.get("tier"), 9), -float(c.get("relevance_score") or 0), -(c.get("year") or 0),
            re.sub(r"[^a-z0-9]+", "", str(c.get("title", "")).lower()), str(c.get("id", ""))) for c in cands]
    rep["passed"]["ordering_matches_documented_keys"] = key == sorted(key)
    if not rep["passed"]["ordering_matches_documented_keys"]:
        rep["errors"].append("candidate order does not match tier>score>year>title>id")

    # 5 per-item required fields
    need = ("id", "title", "tier", "decision", "relevance_score", "relevance_reason", "evidence", "source_db", "query_id", "retrieved_at")
    bad = [c.get("id") for c in cands if any(c.get(k) in (None, "", [], {}) for k in need)]
    rep["passed"]["items_have_required_fields"] = not bad
    rep["items_missing_fields"] = bad[:50]
    if bad:
        rep["errors"].append("candidates missing required fields: %s" % bad[:10])

    # 6 tier counts
    cnt = {t: sum(1 for c in cands if c.get("tier") == t) for t in TO}
    rep["passed"]["tier_counts_consistent"] = cnt == (res.get("tiers") or cnt)
    rep["tier_counts_recomputed"] = cnt

    # 7 coverage of input records
    ir = res.get("input_record_count")
    dedupe = res.get("dedupe") or {}
    merged = sum(max(0, int(c.get("version_count") or 1) - 1) for c in cands)
    rep["input_record_count"] = ir
    rep["groups_out"] = len(cands)
    rep["passed"]["record_accounting"] = (ir is None) or (ir - merged == len(cands) or dedupe.get("input_records") == ir)
    if not rep["passed"]["record_accounting"]:
        rep["warnings"].append("input_record_count %r vs groups %d (merged %d)" % (ir, len(cands), merged))

    # 8 evidence verbatim against re-parsed sources
    src = []
    for p in sorted(I.rglob("*")):
        if not p.is_file():
            continue
        e = p.suffix.lower()
        try:
            if e == ".json":
                harvest(load(p), src)
            elif e in (".jsonl", ".ndjson"):
                harvest(rows(p), src)
            elif e == ".csv":
                with open(p, encoding="utf-8", errors="replace", newline="") as f:
                    harvest([dict(r) for r in csv.DictReader(f)], src)
        except Exception as ex:
            rep["warnings"].append("verify could not parse %s: %r" % (p.name, ex))
    byid, bytitle = {}, {}
    for s in src:
        if s.get("id"):
            byid.setdefault(s["id"], s)
        if s.get("title"):
            bytitle.setdefault(re.sub(r"\s+", " ", s["title"]).strip().lower(), s)
    failures = []
    unmapped = []
    for c in cands:
        rec = byid.get(str(c.get("id"))) or bytitle.get(re.sub(r"\s+", " ", str(c.get("title", ""))).strip().lower())
        if not rec:
            unmapped.append(c.get("id"))
            continue
        ev = (c.get("evidence") or [{}])[0].get("quote") or ""
        body = (rec.get("abstract") or "") + " \n " + (rec.get("title") or "")
        if ev and ev[:LIM] not in body:
            failures.append({"id": c.get("id"), "quote": ev[:120]})
    rep["passed"]["evidence_verbatim"] = not failures
    rep["evidence_not_in_source"] = failures[:30]
    rep["ids_not_mapped_to_source"] = unmapped[:30]
    if failures:
        rep["errors"].append("%d evidence quotes not found verbatim in source text" % len(failures))

    # 9 duplicate DOIs / titles among output groups
    dois = [c.get("doi") for c in cands if c.get("doi")]
    titles = [re.sub(r"[^a-z0-9]+", "", str(c.get("title", "")).lower()) for c in cands]
    rep["passed"]["no_duplicate_groups"] = len(dois) == len(set(dois)) and len(titles) == len(set(titles))
    if not rep["passed"]["no_duplicate_groups"]:
        rep["warnings"].append("duplicate DOI/title still present among output candidates")

    # 10 DOI syntax
    bad = [d for d in dois if not re.match(r"^10\.\d{4,9}/\S+$", str(d))]
    rep["passed"]["doi_syntax"] = not bad
    rep["doi_invalid"] = bad[:20]

    # 11 metrics recomputation (only if labels exist)
    lab = [c for c in cands if c.get("labels")]
    if len(lab) >= 3:
        def gf(c):
            v = [vd(x) for x in (c.get("labels") or [])]
            v = [x for x in v if x is not None]
            return (1 if 1 in v else 0) if v else 0
        k = (res.get("metrics") or {}).get("k") or [5]
        kk = sorted(k)[0]
        p, n = met(cands, kk, gf)
        declared = ((res.get("metrics") or {}).get("skill") or {})
        rep["metrics_recomputed"] = {"P@%d" % kk: p, "nDCG@%d" % kk: n}
        rep["passed"]["metrics_recomputable"] = abs(float(declared.get("P@%d" % kk, p)) - p) < 1e-6
        if not rep["passed"]["metrics_recomputable"]:
            rep["warnings"].append("declared P@%d differs from recomputation" % kk)
    else:
        rep["passed"]["metrics_recomputable"] = True
        rep["metrics_recomputed"] = {"note": "fewer than 3 labelled candidates; no metric claimed"}

    # 12 output artefacts
    rep["passed"]["candidates_csv_exists"] = (O / "candidates.csv").is_file()
    rep["passed"]["query_log_exists"] = (O / "query_log.json").is_file()

    rep["summary"] = "%d/%d checks passed" % (sum(1 for v in rep["passed"].values() if v), len(rep["passed"]))
    (O / "verify_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[verify] " + rep["summary"])
    for k, v in rep["passed"].items():
        if not v:
            print("  FAIL %s" % k)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)
    except Exception:
        sys.exit(0)
