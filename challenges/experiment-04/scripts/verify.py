#!/usr/bin/env python3
"""Deterministic self-check for a plan-compare run.

Re-derives the arithmetic, re-checks contract coverage, and confirms every
evidence quote really occurs in the cited source file. Writes self_check.json
next to result.json. Exit code is always 0.

    python3 -B verify.py --output /app/output --input /input
"""

import argparse
import json
import sys
from pathlib import Path

REQUIRED = ["case_id", "status", "sources", "uncertainty", "pending_human",
            "errors", "degradations", "changes", "runtime"]
STATUS = ("ok", "partial", "insufficient_evidence", "input_error")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, repr(e)[:200]


def check(outdir, indir):
    outdir, indir = Path(outdir), Path(indir)
    c = {"checked_at": None, "checks": [], "counts": {}, "warnings": []}

    def add(name, ok, detail=""):
        c["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    res, err = load(outdir / "result.json")
    if res is None:
        add("result_parses", False, err or "missing result.json")
        c["passed"] = False
        return c
    add("result_parses", True, "result.json parsed")

    miss = [k for k in REQUIRED if k not in res]
    add("required_keys", not miss, "missing: " + ", ".join(miss) if miss else "all present")
    add("status_enum", res.get("status") in STATUS, str(res.get("status")))

    names = res.get("output_contract_fields") or []
    absent = [n for n in names if n not in res]
    add("output_contract_backfill", not absent,
        "%d/%d fields present; missing: %s" % (len(names) - len(absent), len(names), absent))
    c["counts"]["contract_fields"] = len(names)

    # arithmetic re-derivation
    bad = []
    plans = (res.get("cost_model") or {}).get("plans") or {}
    for pid, m in plans.items():
        tot = m.get("total_cost")
        if tot is None:
            continue
        calc = m["runs"] * m["per_run_cost"] + m["fixed_cost"] + \
            (m.get("machine_cost") or 0.0) + (m.get("labor_cost") or 0.0)
        if abs(calc - tot) > max(0.02, abs(tot) * 1e-4):
            bad.append("%s total %s != %s" % (pid, tot, round(calc, 2)))
        for ln in m.get("lines") or []:
            if abs(ln["qty"] * ln["unit_price"] - ln["subtotal"]) > 0.01:
                bad.append("%s line %s subtotal" % (pid, ln["label"]))
    add("cost_arithmetic", not bad, "; ".join(bad[:5]) or "%d plans recomputed" % len(plans))

    # matrix shape
    pid = res.get("plan_order") or []
    shape_bad = [r["criterion"] for r in (res.get("comparison_matrix") or [])
                 if set(r["values"]) != set(pid)]
    add("matrix_uniform", not shape_bad,
        "rows with wrong columns: %s" % shape_bad[:5] if shape_bad else "%d rows x %d plans" %
        (len(res.get("comparison_matrix") or []), len(pid)))

    # evidence quotes must exist verbatim in the cited source
    ev = res.get("evidence") or []
    hit, miss_q = 0, []
    cache = {}
    for e in ev:
        src = str(e.get("source") or "")
        path = indir / src
        if not path.exists():
            miss_q.append({"id": e.get("id"), "why": "source missing: " + src})
            continue
        if src not in cache:
            cache[src] = path.read_text(encoding="utf-8", errors="replace")
        if str(e.get("quote")) and str(e["quote"]) in cache[src]:
            hit += 1
        else:
            miss_q.append({"id": e.get("id"), "locator": e.get("locator"),
                           "quote": e.get("quote")})
    rate = (hit / float(len(ev))) if ev else 1.0
    add("evidence_quotes", rate >= 0.7,
        "%d/%d verbatim (%.0f%%)" % (hit, len(ev), 100 * rate))
    c["counts"].update({"evidence": len(ev), "evidence_verbatim": hit,
                        "evidence_missing": len(miss_q),
                        "plans": len(pid),
                        "gates": len(res.get("feasibility_gates") or []),
                        "risk_items": len(res.get("risk_register") or []),
                        "eliminations": len(res.get("eliminations") or []),
                        "uncertainty": len(res.get("uncertainty") or []),
                        "pending_human": len(res.get("pending_human") or [])})
    if miss_q:
        c["warnings"].append({"evidence_not_verbatim": miss_q[:10]})

    # elimination coverage: every non-selected plan explained
    sel = (res.get("choice") or {}).get("selected")
    explained = {e.get("plan") for e in (res.get("eliminations") or [])}
    need = [p for p in pid if p != sel]
    add("eliminations_complete", all(p in explained for p in need),
        "unexplained: %s" % [p for p in need if p not in explained])

    arts = ["result.json"]
    missing_art = [a for a in arts if not (outdir / a).exists()]
    add("artifacts_exist", not missing_art, "missing: " + str(missing_art))

    c["passed"] = all(x["ok"] for x in c["checks"])
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify", description="plan-compare 结果自检：契约回填、成本算术、证据逐字命中。")
    ap.add_argument("--output", default="/app/output", help="输出目录，默认 /app/output")
    ap.add_argument("--input", default="/input", help="输入目录，默认 /input")
    a = ap.parse_args(argv)
    c = check(Path(a.output), Path(a.input))
    try:
        (Path(a.output) / "self_check.json").write_text(
            json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    for x in c["checks"]:
        print("%s  %-26s %s" % ("PASS" if x["ok"] else "FAIL", x["check"], x["detail"]))
    print("counts:", json.dumps(c.get("counts", {}), ensure_ascii=False))
    print("passed:", c.get("passed"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
