#!/usr/bin/env python3
"""verify: deterministic self-check of a result.json produced by main.py.

usage: verify.py [--result PATH] [--out PATH] [--no-reexec] [--quiet]

Checks, without any model in the loop:
  1. result.json exists, parses, is an object;
  2. required meta keys exist and status is in the allowed set;
  3. every output_contract field is present at top level (echo complete);
  4. every aggregate/join query_id cited by the results exists in the query log,
     and the log rows are consistent with the aggregate row counts;
  5. sql_aggregation evidence re-executes against its snapshot and reproduces the
     quoted value (skipped with --no-reexec);
  6. text quotes are literal substrings of their source file;
  7. every listed artifact exists and is non-empty.

Exit code is 0 whenever the report was written, whatever the verdict; the
verdict (pass|fail) and counterexample list are the deliverable.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

META = ("case_id", "status", "sources", "uncertainty", "pending_human", "errors",
        "degradations", "changes", "runtime")
STATUS = {"ok", "partial", "insufficient_evidence", "input_error"}


def check(name, ok, detail, examples=None):
    return {"check": name, "ok": bool(ok), "detail": detail,
            "examples": (examples or [])[:5]}


def reexec(item, cache):
    path = item.get("source_path")
    sql = item.get("sql")
    if not path or not sql:
        return None
    if path not in cache:
        cache[path] = sqlite3.connect("file:%s?mode=ro" % Path(path).resolve().as_posix(),
                                      uri=True, timeout=10)
    row = cache[path].execute(sql).fetchone()
    return None if row is None else str(row[0])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description=__doc__.split("\n")[0])
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default=None, help="report path (default beside result)")
    ap.add_argument("--no-reexec", action="store_true", help="skip SQL re-execution")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    rp = Path(a.result)
    out = Path(a.out) if a.out else rp.parent / "verify_report.json"
    checks, res = [], {}
    if not rp.exists():
        report = {"verdict": "fail", "checks": [
            check("result_exists", False, "no result.json at %s" % rp)]}
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not a.quiet:
            print("FAIL result_exists -> %s" % out)
        return 0
    try:
        res = json.loads(rp.read_text(encoding="utf-8"))
        ok = isinstance(res, dict)
    except Exception as exc:
        ok = False
        checks.append(check("result_parses", False, "json error: %s" % exc))
    if ok:
        checks.append(check("result_parses", True,
                            "%d top-level keys" % len(res)))

    if isinstance(res, dict) and res:
        missing = [k for k in META if k not in res]
        checks.append(check("meta_keys", not missing,
                            "missing: %s" % (missing or "none"), missing))
        st = res.get("status")
        checks.append(check("status_allowed", st in STATUS,
                            "status=%r allowed=%s" % (st, sorted(STATUS))))

        contract = res.get("output_contract") or {}
        if isinstance(contract, dict) and contract:
            absent = [k for k in contract if k not in res]
            nulls = [k for k in contract if res.get(k) is None]
            checks.append(check("contract_echo", not absent,
                                "%d/%d contract fields present; %d null"
                                % (len(contract) - len(absent), len(contract), len(nulls)),
                                absent))
            cf = res.get("contract_fill") or {}
            checks.append(check("contract_fill_counts",
                                cf.get("fields") == len(contract),
                                "contract_fill.fields=%r vs %d contract fields"
                                % (cf.get("fields"), len(contract))))
        else:
            checks.append(check("contract_echo", True,
                                "case declared no output_contract; nothing to echo"))

        log = {e.get("id"): e for e in (res.get("queries") or []) if isinstance(e, dict)}
        bad, examples = [], []
        main_res = res.get("main_result") or {}
        cites = list(main_res.get("aggregates") or []) + list(main_res.get("summaries") or []) \
            + list(main_res.get("join_aggregates") or []) + list(res.get("cross_table") or [])
        for item in cites:
            qid = item.get("query_id")
            if qid not in log:
                bad.append(qid)
                examples.append("missing query %r for %r" % (qid, item.get("metric")))
                continue
            rows = item.get("rows")
            if isinstance(rows, list) and log[qid].get("rows") not in (None, len(rows)):
                bad.append(qid)
                examples.append("%s: log says %s rows, result keeps %d"
                                % (qid, log[qid].get("rows"), len(rows)))
        checks.append(check("query_references", not bad,
                            "%d citation(s) traced to the query log; %d problem(s)"
                            % (len(cites), len(bad)), examples))

        ev = res.get("evidence") or []
        cache, failures, textual, skipped = {}, [], 0, 0
        for item in ev:
            src = item.get("source_path")
            quote = item.get("quote")
            if item.get("kind") == "sql_aggregation":
                if a.no_reexec:
                    skipped += 1
                    continue
                try:
                    got = reexec(item, cache)
                except Exception as exc:
                    failures.append("%s: re-execution error %s" % (item.get("id"), exc))
                    continue
                if got is None or str(got) != str(quote):
                    failures.append("%s: quoted %r, re-executed %r"
                                    % (item.get("id"), quote, got))
            elif src and quote and Path(src).suffix.lower() in (".md", ".txt", ".csv", ".json"):
                textual += 1
                try:
                    body = Path(src).read_text(encoding="utf-8", errors="replace")
                except Exception as exc:
                    failures.append("%s: source unreadable %s" % (item.get("id"), exc))
                    continue
                if str(quote) not in body:
                    failures.append("%s: quote not found verbatim in %s"
                                    % (item.get("id"), Path(src).name))
        checks.append(check("evidence_reproducible", not failures,
                            "%d evidence item(s); %d SQL re-executed; %d text quote(s) "
                            "matched; %d skipped; %d rejection(s)"
                            % (len(ev), len(ev) - skipped - textual, textual, skipped,
                               len(failures)), failures))

        arts, miss = res.get("artifacts") or [], []
        for art in arts:
            p = Path(art.get("path") or "")
            if not p.exists() or p.stat().st_size == 0:
                miss.append(str(p))
        charts = res.get("charts") or []
        for c in charts:
            p = Path(c.get("path") or "")
            if not (p.exists() and p.stat().st_size > 0):
                miss.append(str(p))
        checks.append(check("artifacts_present", not miss,
                            "%d artifact(s), %d chart(s), %d missing"
                            % (len(arts), len(charts), len(miss)), miss))
    else:
        checks.append(check("result_object", False, "result.json is not a JSON object"))

    failures = [c for c in checks if not c["ok"]]
    verdict = "pass" if not failures else "fail"
    report = {"verdict": verdict, "checked": str(rp), "n_checks": len(checks),
              "n_failed": len(failures), "checks": checks}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not a.quiet:
        print("%s %d/%d checks passed -> %s"
              % (verdict.upper(), len(checks) - len(failures), len(checks), out))
        for c in failures:
            print("  FAIL %s: %s %s" % (c["check"], c["detail"], c["examples"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
