#!/usr/bin/env python3
"""literature-data-cleaner (reading-11): clean literature extraction records into a
statistical table, a change log, a pending-list and a duplicate/conflict report.
Stdlib only, offline, no CWD dependency.
  python3 main.py --input /input --output /app/output [--determinism]
"""
import argparse, csv, json, subprocess, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_core import (V, Units, claims_of, clean, counts_of, dedup, ljson, nat, nkey, rd, roles_of,
                        shape, wcsv, wjson)

R = Path(__file__).resolve().parent.parent / "references"
ND = ("note", "comment", "remark", "memo", "flag")
ARTS = {"clean|table|csv": "cleaned.csv", "change|log": "change_log.csv",
        "pending|review": "pending_review.csv", "anomal|report": "anomaly_report.md",
        "rule|\u89c4\u5219": "rules.json", "mapping|\u6620\u5c04": "field_mapping.json",
        "unit|\u5355\u4f4d": "unit_table.json"}
CH_F = ["row_id", "field", "before", "after", "unit_before", "unit_after", "factor", "offset", "formula",
        "precision", "rule_id", "source_document_id", "source_locator", "note"]
PE_F = ["row_id", "field", "reason_code", "reason", "suggested_action", "original_value", "original_unit",
        "source_document_id", "source_locator"]

def discover(d):
    f = {"case": None, "cp": None, "records": [], "rules": [], "schema": []}
    files = sorted(p for p in d.rglob("*") if p.is_file()) if d.exists() else []
    for p in sorted([x for x in files if x.suffix.lower() == ".json"],
                    key=lambda x: (not x.name.lower().startswith("case"), str(x))):
        o, _ = ljson(p)
        if isinstance(o, dict) and ("output_contract" in o or o.get("case_id")):
            f["case"], f["cp"] = o, p
            break
    for p in files:
        if p == f["cp"] or p.suffix.lower() not in (".csv", ".json"):
            continue
        if p.suffix.lower() == ".csv":
            f["records"].append(p)
            continue
        o, err = ljson(p)
        if err or o is None:
            f["records"].append(p)
            continue
        low, head = p.name.lower(), json.dumps(o, ensure_ascii=False)[:3000].lower()
        key = "rules" if ("rule" in low or '"rule_id"' in head) else (
            "schema" if ("schema" in low or "dictionar" in low or '"fields"' in head) else "records")
        f[key].append((p, o) if key != "records" else p)
    return f

def find_rows(o):
    if isinstance(o, list):
        return [r for r in o if isinstance(r, dict)]
    if not isinstance(o, dict):
        return []
    for k in ("records", "rows", "data", "items", "measurements", "extractions", "entries", "table",
              "values", "results", "artifacts") + tuple(sorted(o)):
        v = o.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        if isinstance(v, dict) and find_rows(v):
            return find_rows(v)
    return []

def flat(v):
    return "" if v is None else (str(v) if isinstance(v, (str, int, float))
                                 else json.dumps(v, ensure_ascii=False, sort_keys=True))

def load_rules(f, lib):
    rules, supp = [dict(r) for r in lib.get("rules", [])], []
    for path, obj in f["rules"]:
        cand = obj.get("rules") if isinstance(obj, dict) else None
        for r in (cand if isinstance(cand, list) else ([obj] if obj.get("rule_id") else [])):
            if not isinstance(r, dict) or not r.get("rule_id"):
                continue
            rec = {"rule_id": str(r["rule_id"]), "priority": int(r.get("priority", 10)),
                   "applies_to": r.get("applies_to", "value"), "condition": r.get("condition", ""),
                   "transform": r.get("transform", r.get("action", "")), "examples": r.get("examples", []),
                   "failure_mode": r.get("failure_mode", ""), "human_gate": bool(r.get("human_gate", False))}
            for i, old in enumerate(rules):
                if old["rule_id"] == rec["rule_id"]:
                    win = rec["priority"] <= old["priority"]
                    supp.append({"rule_id": (old if win else rec)["rule_id"],
                                 "by": (rec if win else old)["rule_id"], "reason": "lower priority number wins"})
                    if win:
                        rules[i] = rec
                    break
            else:
                rules.append(rec)
    return sorted(rules, key=lambda r: (r["priority"], r["rule_id"])), supp

def fill_contract(tpl, res):
    """contract leaf -> artifact path, summary value or null."""
    mp, r = {}, res.get("result") or {}

    def leaf(path):
        low = path.lower()
        for k, v in ARTS.items():
            if any(h in low for h in k.split("|")):
                return mp.setdefault(path, v)
        for h, tag in (("count", "counts"), ("claim", "claims"), ("uncertain", "uncertainties"),
                       ("case_id", "case_id"), ("status", "status"), ("result", "result")):
            if h in low:
                mp[path] = tag
                return r.get(tag) if tag == "counts" else res.get(tag)
        mp[path] = "null"
        return None

    def walk(n, p):
        if isinstance(n, (dict, list)) and not n and p:
            return leaf(p)
        if isinstance(n, list):
            return [walk(v, p) for v in n]
        if isinstance(n, dict):
            return {k: walk(v, p + "." + k if p else k) for k, v in n.items()}
        return leaf(p) if isinstance(n, str) and n.strip() in ("", "string", "null") else n

    return walk(tpl, ""), mp

def formula_ok(r):
    try:
        return abs(float(r["before"]) * float(r["factor"]) + float(r["offset"]) - float(r["after"])) \
            <= 1e-6 * max(1.0, abs(float(r["after"])))
    except Exception:
        return False

def selfcheck(out, s, res):
    """Recompute change_log formulas from written files; check counts/ids/rules."""
    def read(n):
        p = out / n
        return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []

    cl, ch, pe = read("cleaned.csv"), read("change_log.csv"), read("pending_review.csv")
    ids = [r["row_id"] for r in cl]
    rids = {r["rule_id"] for r in (ljson(out / "rules.json")[0] or {}).get("rules", [])}
    ok = sum(1 for r in ch if formula_ok(r))
    rate = 100.0 * ok / len(ch) if ch else 100.0
    chk = [("counts match", [len(cl), len(ch), len(pe)] == [s["cleaned_rows"], s["changed_values"],
            s["pending_review"]], "%d/%d/%d" % (len(cl), len(ch), len(pe))),
           ("row_id unique", bool(ids) and len(ids) == len(set(ids)), str(len(ids))),
           ("after = before*factor + offset", ok == len(ch), "%.1f%% consistent" % rate),
           ("rule_id resolves", not ({r["rule_id"] for r in ch} - rids), ""),
           ("no leaked value", not [r["row_id"] for r in cl
                                                if r["status"] == "needs_review" and r["value"]], "")]
    bad = [c for c in chk if not c[1]]
    wjson(out / "verify_report.json", {"checks": [{"name": n, "pass": bool(p), "detail": d} for n, p, d in chk],
                                       "passed": len(chk) - len(bad), "total": len(chk),
                                       "formula_consistency_pct": round(rate, 2),
                                       "verdict": "PASS" if not bad else "CHECK"})
    print("[selfcheck] %d/%d passed, formula %.1f%% %s" % (len(chk) - len(bad), len(chk), rate, "PASS" if not bad else "CHECK"))

def run(ctx):
    ind, out, res, a = ctx["ind"], ctx["out"], ctx["res"], ctx["a"]
    utab = ljson(R / "unit_table.json")[0]
    lib = ljson(R / "rules_library.json")[0] or {}
    if not utab:
        raise RuntimeError("references/unit_table.json unreadable")
    units, f = Units(utab), discover(ind)
    case = f["case"] or {}
    res["case_id"], ctx["tpl"] = case.get("case_id"), case.get("output_contract") or {}
    if f["case"] is None:
        res["degradations"].append({"stage": "discover", "note": "no case.json"})
    rules, supp = load_rules(f, lib)
    schema = dict(lib.get("target_schema", {}))
    fsyn = {k: list(v) for k, v in lib.get("field_roles", {}).items()}
    syn = {"material": {nkey(k): v for k, v in lib.get("material_synonyms", {}).items()},
           "indicator": {nkey(k): v for k, v in lib.get("indicator_synonyms", {}).items()}}
    for _, o in f["schema"]:
        if isinstance(o, dict):
            schema["fields"] = next((o[k] for k in ("fields", "schema", "target_schema")
                                     if isinstance(o.get(k), dict)), schema.get("fields", {}))
            fsyn.update({k: v if isinstance(v, list) else [v] for k, v in (o.get("field_roles") or {}).items()})
            for k, tag in (("synonyms", "material"), ("material_synonyms", "material"),
                           ("indicator_synonyms", "indicator")):
                syn[tag].update({nkey(x): y for x, y in (o.get(k) or {}).items()})

    tables, sources = [], []
    for p in f["records"]:
        rows, enc, bad, err = [], "json", 0, None
        if p.suffix.lower() == ".csv":
            txt, enc, bad, err = rd(p)
            rows = [] if err else [{k: flat(v) for k, v in r.items() if k is not None}
                                   for r in csv.DictReader(txt.splitlines())]
        else:
            o, err = ljson(p)
            rows = [] if err else [{k: flat(v) for k, v in r.items()} for r in find_rows(o)]
        if err:
            res["errors"].append({"stage": "read", "file": p.name, "error": err})
            continue
        if bad:
            res["degradations"].append({"stage": "read", "file": p.name, "count": bad, "note": "encoding (R019)"})
        rows = [r for r in rows if any(str(v).strip() for v in r.values())]
        sources.append({"source_id": p.stem, "path": str(p), "rows": len(rows)})
        if rows:
            tables.append({"file": p, "rows": rows})
        else:
            res["degradations"].append({"stage": "read", "file": p.name, "note": "no rows (R020)"})
    if not tables:
        res["degradations"].append({"stage": "discover", "note": "no record table"})
        res["status"] = "insufficient_evidence"
        return

    lrows, fmap = [], []
    for tab in tables:
        cols = []
        for r in tab["rows"]:
            cols += [k for k in r if k not in cols]
        roles = roles_of(cols, fsyn)
        conds = [c for c in cols if c not in roles and not any(h in str(c).lower() for h in ND)]
        if "value" not in roles:
            res["degradations"].append({"stage": "shape", "note": "%s: no value col (R003)" % tab["file"].name})
        fmap += [{"original": c, "file": tab["file"].name, "target": roles.get(c, ""), "mapped": c in roles,
                  "basis": ("synonym hit -> %s" % roles[c]) if c in roles
                           else "no hit; kept as condition/annotation"} for c in cols]
        lrows += shape(tab, roles, conds, syn["material"], syn["indicator"], res)
    if not lrows:
        res["degradations"].append({"stage": "shape", "note": "no measurable row"})
        res["status"] = "insufficient_evidence"
        return

    cleaned, changes, pending, unc, nchg = [], [], [], [], 0
    for row in lrows:
        o, ch, pe, un = clean(row, units)
        cleaned.append(o)
        changes += ch
        pending += pe
        unc += un
        nchg += 1 if (not ch and o["value"] is not None) else 0
    dups, confl = dedup(cleaned, lib, res)
    fields = ["row_id", "source_document_id", "source_locator", "indicator", "material", "condition_summary",
              "value", "value_low", "value_high", "value_err", "value_text", "unit", "original_field",
              "original_value", "original_unit", "rule_ids", "judgment_key", "status", "duplicate_of", "note"]
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in cleaned]
    rows.sort(key=lambda r: (str(r["source_document_id"]), nat(r["row_id"])))
    changes.sort(key=lambda c: (str(c["source_document_id"]), nat(c["row_id"]), c["field"]))
    pending.sort(key=lambda p: (str(p["source_document_id"]), nat(p["row_id"]), p["reason_code"]))
    for name, recs, flds in (("cleaned.csv", rows, fields), ("change_log.csv", changes, CH_F),
                             ("pending_review.csv", pending, PE_F)):
        wcsv(out / name, recs, flds)
    wjson(out / "rules.json", {"version": lib.get("version", "1.0.0"), "precedence": lib.get("precedence", ""),
                               "rules": rules, "suppressed_rules": supp, "applied_counts": counts_of(changes, pending)})
    wjson(out / "field_mapping.json", {
        "target_schema_version": schema.get("version", "1.0.0"),
        "schema_source": "case supplied" if f["schema"] else "references/rules_library.json",
        "columns": fmap, "unmapped": [c["original"] for c in fmap if not c["mapped"]],
        "note": "basis is a synonym hit or a schema field name; unmapped columns are reported, not guessed"})
    seen = {}
    for c in changes:
        e = seen.setdefault("%s -> %s" % (c["unit_before"], c["unit_after"]),
                            {"from": c["unit_before"], "to": c["unit_after"], "factor": c["factor"],
                             "offset": c["offset"], "count": 0})
        e["count"] += 1
    uto = dict(utab)
    uto["observed_conversions"] = [seen[k] for k in sorted(seen)]
    wjson(out / "unit_table.json", uto)

    s = {"input_rows": len(lrows), "cleaned_rows": len(rows), "changed_values": len(changes),
         "unchanged_values": nchg, "pending_review": len(pending), "anomalies": len(pending) + len(unc),
         "analytic_rows": len([r for r in rows if r["status"] in ("ok", "replicate")]),
         "missing_values": len([r for r in rows if r["status"] == "missing"]),
         "range_values": len([r for r in rows if r["value_low"] is not None]),
         "error_term_values": len([r for r in rows if r["value_err"] is not None]),
         "merged_duplicates": len([r for d in dups for r in d["merged_row_ids"]]),
         "conflicts": len({r for d in confl for r in d["row_ids"]}),
         "rows_with_row_id_and_source": len([r for r in rows if r["row_id"] and r["source_document_id"]])}
    txt = lib.get("texts", {})
    res["result"] = dict(res["result"], **{
        "counts": s,
        "rules_applied": [{"rule_id": k, "count": v["count"], "examples": v["examples"]}
                          for k, v in sorted(counts_of(changes, pending).items())],
        "duplicates": dups, "conflicts": confl,
        "unknown_units": sorted({p["original_unit"] for p in pending}),

        "coverage": {"columns_seen": len(fmap), "columns_mapped": len([c for c in fmap if c["mapped"]]),
                     "columns_unmapped": [c["original"] for c in fmap if not c["mapped"]],
                     "rows_fully_traceable": s["rows_with_row_id_and_source"],
                     "rows_with_locator": len([r for r in rows if r["source_locator"]])},
        "condition_columns": sorted({c for r in cleaned for c in r["_conds"]}),
        "judgment_key_template": lib.get("judgment_key", {}).get("template", ""),
        "method_notes": txt.get("method_notes", []), "artifacts": txt.get("artifacts", {})})
    res["changes"] = changes[:400]
    res["pending_human"] = [{k: p[k] for k in ("row_id", "field", "reason_code", "reason", "suggested_action")}
                            for p in pending[:400]]
    res["uncertainties"] = res["uncertainty"] = unc[:400]
    res["sources"] = sources
    res["claims"] = claims_of(changes, pending, rows, s, 200, txt)
    res["status"] = ("insufficient_evidence" if not rows else "partial" if (pending or confl) else "ok")
    report(ctx, s, fmap, dups, confl, changes, pending, txt)

def report(ctx, s, fmap, dups, confl, changes, pending, txt):
    res, out, agg = ctx["res"], ctx["out"], {}
    for p in pending:
        agg[p["reason_code"]] = agg.get(p["reason_code"], 0) + 1
    un = [c["original"] for c in fmap if not c["mapped"]]
    L = ["# " + txt.get("report_title", "Cleaning report"), "", txt.get("report_intro", "") % V, "",
         "counts: " + ", ".join("%s=%s" % (k, s.get(k)) for k in s),
         "mapped %d/%d; unmapped: %s"
         % (len(fmap) - len(un), len(fmap), ", ".join(un[:20]) or "none"),
         "pending review: " + (", ".join("`%s`=%d" % (k, agg[k]) for k in sorted(agg)) or "none"),
         "rules: " + (", ".join("%s x%d" % (k, v["count"])
                                for k, v in sorted(counts_of(changes, pending).items())) or "none"),
         "duplicates / conflicts:"]
    L += ["- %s `%s` [%s]: %s" % (x.get("action", "conflict"), x["judgment_key"], ",".join(x["row_ids"]),
                                  x["reason"]) for x in confl + dups]
    L += ["degradations: %s" % "; ".join(
        ["%s: %s" % (d.get("stage"), d.get("note")) for d in res["degradations"][:25]] +
        ["error %s: %s" % (e.get("stage"), e.get("error")) for e in res["errors"][:20]])]
    L += ["boundaries:"] + ["- " + x for x in txt.get("boundary", [])]
    Path(out / "anomaly_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

def finalize(ctx):
    res, out = ctx["res"], ctx["out"]
    tpl = ctx.get("tpl") or {}
    if isinstance(tpl, dict) and tpl:
        filled, mp = fill_contract(tpl, res)
        for k, v in filled.items():
            res.setdefault(k, v)
        res["contract_mapping"] = mp
    wjson(out / "result.json", res)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description=(
        "Clean literature extraction records: field mapping, unit conversion, synonym normalization, "
        "dedup, traceable change log."))
    ap.add_argument("--input", help="input dir (default /input, else ../input)")
    ap.add_argument("--output", help="output dir (default /app/output, else ../output)")
    ap.add_argument("--determinism", action="store_true", help="two-run byte check")
    a = ap.parse_args(argv)
    base = R.parent
    ind = Path(a.input).resolve() if a.input else next(
        (Path(p) for p in ("/input", str(base / "input")) if Path(p).exists()), Path("/input"))
    out = Path(a.output).resolve() if a.output else (Path("/app/output") if Path("/app").exists()
                                                     else base / "output")
    out.mkdir(parents=True, exist_ok=True)
    if a.determinism:
        dg = []
        for k in ("_d1", "_d2"):
            d = out / k
            d.mkdir(parents=True, exist_ok=True)
            subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--input", str(ind),
                            "--output", str(d)], capture_output=True)
            dg.append({p.name: p.read_bytes() for p in sorted(d.iterdir()) if p.is_file()})
            for p in sorted(d.iterdir()):
                p.unlink()
            d.rmdir()
        diff = sorted(n for n in set(dg[0]) | set(dg[1]) if dg[0].get(n) != dg[1].get(n))
        print("[determinism] %s %s" % ("identical" if not diff else "DIFFERS", diff))
        return 0
    res = {"case_id": None, "status": "partial", "result": {}, "claims": [], "uncertainties": [],
           "uncertainty": [], "sources": [], "pending_human": [], "errors": [], "degradations": [],
           "changes": [], "contract_mapping": {},
           "runtime": {"tool": "literature-data-cleaner", "version": V, "python": sys.version.split()[0]}}
    wjson(out / "result.json", res)                    # partial result first, always
    ctx = {"ind": ind, "out": out, "res": res, "a": a, "tpl": {}}
    try:
        run(ctx)
    except Exception as exc:
        res["errors"].append({"stage": "pipeline", "error": "%s: %s" % (type(exc).__name__, exc),
                              "traceback": traceback.format_exc(limit=3)[-800:]})
    finalize(ctx)
    try:
        s = (res.get("result") or {}).get("counts") or {}
        if s:
            selfcheck(out, s, res)
    except Exception as exc:
        print("[selfcheck] skipped: %s" % exc)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        sys.exit(0)
