"""contractmap: output_contract field-to-value mapping and atomic result writing
for the science-db-query-analysis skill."""

import json
import os
from pathlib import Path

from dbcore import norm


def value_for(name, ctx):
    k, main = norm(name), ctx["main"]
    if any(t in k for t in ("unmapped", "unknown", "custom", "other", "misc", "extra",
                            "tbd", "free_form")):
        return None
    rules = [
        (("sql", "quer", "statement"), lambda: [
            {"id": e["id"], "purpose": e["purpose"], "sql": e["sql"],
             "rows": e["rows"], "error": e["error"]} for e in ctx["log"]]),
        (("schema", "table", "database", "snapshot"), lambda: [
            {"database": c["name"], "sha1": c["sha1"], "tables": [
                {"name": t["name"], "rows": t["rows"],
                 "columns": [x["name"] for x in t["columns"]]} for t in c["tables"]]}
            for c in ctx["schema"]]),
        (("field", "dictionary", "semantic", "explain", "column"), lambda: ctx["fields"]),
        (("join", "cross", "relation", "link"), lambda: {
            "paths": ctx["cross_table"],
            "aggregates": ctx["main"].get("join_aggregates") or []}),
        (("chart", "figure", "plot", "visual"), lambda: ctx["charts"] or None),
        (("quality", "clean", "dirty", "missing", "duplicate", "outlier", "check"),
         lambda: ctx["quality"]),
        (("evidence", "source", "locator", "provenance", "trace"), lambda: ctx["evidence"]),
        (("caveat", "uncertain", "limit", "risk"), lambda: ctx["uncertainty"]),
        (("assumption",), lambda: ctx["assumptions"]),
        (("status_note", "state", "status"), lambda: ctx.get("status") or "unknown"),
        (("question", "sub_task", "subtask"), lambda: ctx["q_attempts"]),
        (("row_count", "rowcount", "n_rows", "count"), lambda: main.get("n_rows")),
        (("code", "script", "program"), lambda: {
            "entry": str(Path(__file__).resolve()),
            "verify": str(Path(__file__).resolve().parent / "verify.py")}),
    ]
    hit = [fn for keys, fn in rules if any(x in k for x in keys)]
    if hit:
        return hit[0]()
    if any(x in k for x in ("conclusion", "finding", "insight", "answer", "result",
                            "output", "summary", "analysis", "stat", "metric", "value")):
        return {"primary_table": main.get("primary_table"), "row_count": main.get("n_rows"),
                "aggregates": main.get("aggregates"), "summaries": main.get("summaries"),
                "join_aggregates": main.get("join_aggregates"),
                "filtered_counts": main.get("filtered"),
                "sample_rows": main.get("sample_rows")}
    return None


def write(out, res):
    out.mkdir(parents=True, exist_ok=True)
    t = out / ".result.json.tmp"
    t.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, out / "result.json")
    return out / "result.json"
