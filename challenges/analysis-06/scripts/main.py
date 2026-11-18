#!/usr/bin/env python3
"""science-db-query-analysis: read-only SQLite/CSV query and analysis harness.

usage: main.py [--input DIR] [--output DIR] [--work DIR] [--max-seconds N]
               [--row-limit N] [--quiet] [--version]

Writes <output>/result.json with every output_contract field echoed, plus
queries.sql, query_log.json, schema_card.json, aggregate CSV and an SVG chart.
A partial result.json is written first; exit code is always 0.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
import traceback
from pathlib import Path

import dbcore
from dbcore import (card_of, connect, csv_table, dictionary, discover, instr_text,
                    isdb, load_case, now, questions, sha1, norm)
from contractmap import value_for, write
from dbanalysis import analyse, fields, quality, svg

SKILL, VERSION = "science-db-query-analysis", "1.0.0"
RESERVED = {"case_id", "status", "sources", "uncertainty", "pending_human",
            "errors", "degradations", "changes", "runtime", "output_contract"}
T0 = time.time()


def build_parser():
    p = argparse.ArgumentParser(
        prog="main.py",
        description="%s %s: profile SQLite snapshots under the input dir, run read-only "
                    "SQL, explain field semantics, report data quality and join fan-out, "
                    "and write result.json with all output_contract fields. Exit code 0."
                    % (SKILL, VERSION),
        epilog="example: python3 main.py --input /input --output /app/output --work "
               "/app/work (env: SKILL_INPUT_DIR/SKILL_OUTPUT_DIR/SKILL_WORK_DIR)")
    p.add_argument("--input", help="case dir (default /input)")
    p.add_argument("--output", help="result dir (default /app/output)")
    p.add_argument("--work", help="scratch dir (default /app/work)")
    p.add_argument("--max-seconds", type=float, default=660.0,
                   help="soft deadline before finalizing (default 660)")
    p.add_argument("--row-limit", type=int, default=500, help="rows kept per query")
    p.add_argument("--quiet", action="store_true", help="suppress stdout summary")
    p.add_argument("--version", action="version", version="%s %s" % (SKILL, VERSION))
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    dbcore.ROW_LIMIT = max(1, int(a.row_limit))
    indir = Path(a.input or os.environ.get("SKILL_INPUT_DIR") or "/input")
    outdir = Path(a.output or os.environ.get("SKILL_OUTPUT_DIR") or "/app/output")
    workdir = Path(a.work or os.environ.get("SKILL_WORK_DIR") or "/app/work")
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except Exception:
        workdir = outdir

    ctx = {"main": {}, "log": [], "schema": [], "fields": [], "cross_table": [],
           "quality": {}, "charts": [], "evidence": [], "uncertainty": [],
           "assumptions": [], "degradations": [], "errors": [], "sources": [],
           "artifacts": [], "pending": [], "q_attempts": [], "changes": []}
    case, contract, status = {}, {}, "partial"

    def result():
        r = {"case_id": ctx.get("case_id", "unknown"), "status": status,
             "skill": {"name": SKILL, "version": VERSION},
             "output_contract": contract, "summary": ctx.get("summary", ""),
             "main_result": ctx.get("main") or {}, "queries": ctx.get("log") or [],
             "schema": ctx.get("schema") or [],
             "field_explanations": ctx.get("fields") or [],
             "cross_table": ctx.get("cross_table") or [],
             "data_quality": ctx.get("quality") or {}, "charts": ctx.get("charts") or [],
             "assumptions": ctx.get("assumptions") or [],
             "question_attempts": ctx.get("q_attempts") or [],
             "sources": ctx.get("sources") or [],
             "evidence": (ctx.get("evidence") or [])[:40],
             "artifacts": ctx.get("artifacts") or [],
             "uncertainty": ctx.get("uncertainty") or [],
             "pending_human": ctx.get("pending") or [],
             "errors": ctx.get("errors") or [],
             "degradations": ctx.get("degradations") or [],
             "changes": ctx.get("changes") or [],
             "runtime": {"started_at": ctx.get("started"),
                         "seconds": round(time.time() - T0, 2),
                         "python": sys.version.split()[0],
                         "sqlite": sqlite3.sqlite_version,
                         "budget_seconds": a.max_seconds, "row_limit": a.row_limit}}
        return r

    try:
        found = discover(indir)
        case = load_case(found)
        if found["case"] and not case:
            status = "input_error"
            ctx["errors"].append({"stage": "case_json", "file": found["case"].name,
                                  "error": "case.json is empty or not a valid JSON object",
                                  "detail": "analysis proceeded without instruction or contract"})
            ctx["pending"].append("repair /input/case.json; contract fields unknown")
        contract = case.get("output_contract") or case.get("output") or {}
        if isinstance(contract, list):
            contract = {str(k): None for k in contract}
        if not isinstance(contract, dict):
            contract = {}
        ctx["case_id"] = str(case.get("case_id") or case.get("id") or
                             (found["case"].stem if found["case"] else "unknown"))
        ctx["started"] = now()
        ctx["sources"] = [{"id": "S%d" % (i + 1), "path": str(p), "name": p.name,
                           "bytes": p.stat().st_size, "sha1": sha1(p)}
                          for i, p in enumerate(found["files"])]
        for k in contract:
            if k not in RESERVED:
                ctx.setdefault("_echo", {})[k] = None
        # partial first: contract echoed with nulls, always valid JSON
        pre = {"case_id": ctx["case_id"], "status": "partial", "skill":
               {"name": SKILL, "version": VERSION}, "output_contract": contract,
               "summary": "runtime started; no analysis yet", "sources": ctx["sources"],
               "uncertainty": [], "pending_human": [], "errors": [],
               "degradations": [], "changes": [], "runtime": {"started_at": ctx["started"]}}
        for k in contract:
            pre.setdefault(k, None)
        write(outdir, pre)
        ctx["changes"].append({"action": "partial_result_written",
                               "detail": "contract echoed with null values before analysis"})

        if not found["case"]:
            status = "input_error"
            ctx["errors"].append({"stage": "discover", "error": "case.json not found",
                                  "detail": "searched recursively under %s" % indir})
            ctx["pending"].append("provide /input/case.json with task_instruction and "
                                  "output_contract, then re-run")
        text = instr_text(case)
        if not text:
            ctx["uncertainty"].append("no task instruction text in case.json; analysis "
                                      "is dataset-level only")

        conns = []
        for db in found["dbs"]:
            try:
                conns.append((db, connect(db), "sqlite snapshot in input"))
            except Exception as e:
                ctx["errors"].append({"stage": "connect", "file": db.name, "error": str(e)})
        if found["csvs"]:
            try:
                snap = workdir / "snapshot.sqlite"
                if snap.exists():
                    snap.unlink()
                conn = sqlite3.connect(str(snap))
                conn.row_factory = sqlite3.Row
                made = []
                for p in found["csvs"][:8]:
                    try:
                        made.append(dict(zip(("table", "rows"),
                                             csv_table(conn, p, {m["table"] for m in made}))))
                    except Exception as e:
                        ctx["errors"].append({"stage": "csv_materialize",
                                              "file": p.name, "error": str(e)})
                if made:
                    conns.append((snap, conn, "derived snapshot from CSV material"))
                    ctx["degradations"].append({"what": "no SQLite file in input",
                                                "fallback": "CSV materials loaded into a "
                                                            "derived snapshot in the work dir",
                                                "detail": made})
            except Exception as e:
                ctx["errors"].append({"stage": "snapshot", "error": str(e)})

        cards, cols = [], []
        for db, conn, origin in conns:
            try:
                c = card_of(conn, db)
                c["origin"] = origin
                cards.append((db, conn, c))
                cols += [x["name"] for t in c["tables"] for x in t["columns"]]
            except Exception as e:
                ctx["errors"].append({"stage": "schema", "file": db.name, "error": str(e)})
        dm = dictionary(found, cols) if cols else {}
        if not conns and status != "input_error":
            status = "insufficient_evidence"
            ctx["pending"].append("no queryable SQLite/CSV material found; supply a snapshot")

        for db, conn, card in cards:
            if time.time() - T0 > a.max_seconds:
                ctx["degradations"].append({"what": "deadline reached",
                                            "detail": "remaining databases skipped; partial "
                                                      "results kept"})
                break
            ctx["schema"].append(card)
            try:
                ctx["quality"] = quality(conn, card)
            except Exception as e:
                ctx["errors"].append({"stage": "quality", "file": db.name, "error": str(e)})
            try:
                analyse(conn, card, text, ctx, ctx["log"])
            except Exception as e:
                ctx["errors"].append({"stage": "analyse", "file": db.name, "error": str(e),
                                      "trace": traceback.format_exc()[-500:]})
            ctx["fields"] = fields(card, dm, ctx["quality"]) or ctx["fields"]
            for t in card["tables"]:
                if t["rows"] is not None:
                    ctx["evidence"].append({
                        "id": "E%d" % (len(ctx["evidence"]) + 1),
                        "claim": "table %s holds %s rows in snapshot %s"
                                 % (t["name"], t["rows"], card["name"]),
                        "kind": "sql_aggregation", "source_id": card["name"],
                        "source_path": card["path"],
                        "locator": "%s#table=%s;sha1 prefix" % (card["sha1"][:12], t["name"]),
                        "sql": "SELECT COUNT(*) FROM %s" % dbcore.q(t["name"]),
                        "quote": str(t["rows"])})
            for k2, d in list(dm.items())[:6]:
                if d.get("raw") and d.get("path"):
                    ctx["evidence"].append({
                        "id": "E%d" % (len(ctx["evidence"]) + 1),
                        "claim": "dictionary entry for column %s: %s"
                                 % (d.get("column") or k2, d["text"][:120]),
                        "kind": "dictionary_entry", "source_id": Path(d["path"]).name,
                        "source_path": d["path"],
                        "locator": "%s:%s" % (Path(d["path"]).name, d["loc"]),
                        "quote": d["raw"]})
            for e in [x for x in ctx["log"] if not x["error"] and x["rows"]][-5:]:
                first = json.dumps(e["data"][0], ensure_ascii=False, default=str)
                ctx["evidence"].append({
                    "id": "E%d" % (len(ctx["evidence"]) + 1), "claim": e["purpose"],
                    "kind": "query_result", "source_id": card["name"],
                    "locator": "%s#%s;row=1" % (card["sha1"][:12], e["id"]),
                    "quote": first[:200], "sql": e["sql"]})

        agg = (ctx["main"].get("aggregates") or [None])[0]
        if agg and agg["rows"]:
            p = outdir / "chart_group_counts.svg"
            try:
                svg(p, "%s by %s: row counts" % (agg["table"], agg["group_by"]),
                    [str(r.get("grp")) for r in agg["rows"][:10]],
                    [r.get("n") or 0 for r in agg["rows"][:10]], "rows")
                ctx["charts"].append({"kind": "bar_svg", "path": str(p),
                                      "shows": "row counts per %s" % agg["group_by"],
                                      "query_id": agg["query_id"],
                                      "note": "rendered from logged SQL, not hand-drawn"})
                ctx["artifacts"].append({"path": str(p), "kind": "chart_svg",
                                         "bytes": p.stat().st_size})
            except Exception as e:
                ctx["errors"].append({"stage": "chart", "error": str(e)})

        try:
            (outdir / "queries.sql").write_text(
                "-- generated by %s %s; re-runnable on the same snapshot\n\n"
                % (SKILL, VERSION) + "\n\n".join("-- %s\n%s;" % (e["purpose"], e["sql"])
                                                 for e in ctx["log"]), encoding="utf-8")
            (outdir / "query_log.json").write_text(
                json.dumps(ctx["log"], ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            (outdir / "schema_card.json").write_text(
                json.dumps(ctx["schema"], ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
            for f in ("queries.sql", "query_log.json", "schema_card.json"):
                ctx["artifacts"].append({"path": str(outdir / f), "kind": "text",
                                         "bytes": (outdir / f).stat().st_size})
            if agg and agg["rows"]:
                cp = outdir / ("aggregate_%s_by_%s.csv"
                               % (norm(agg["table"]), norm(agg["group_by"])))
                with open(cp, "w", encoding="utf-8", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(agg["rows"][0]))
                    w.writeheader()
                    w.writerows(agg["rows"])
                ctx["artifacts"].append({"path": str(cp), "kind": "table_csv",
                                         "bytes": cp.stat().st_size})
        except Exception as e:
            ctx["errors"].append({"stage": "artifacts", "error": str(e)})

        join_words = ("join", "连接", "关联", "跨表", "膨胀", "fan-out", "fanout", "foreign")
        for qs in questions(case):
            nq = norm(qs)
            agg = [x for x in ctx["main"].get("aggregates") or []
                   if any(norm(w) and norm(w) in nq for w in (x["group_by"], x["metric"]))]
            jag = [x for x in ctx["main"].get("join_aggregates") or []
                   if any(w and w in nq for w in x["group_by"].split("."))]
            if jag:
                st, ans, ids, lim = ("answered_from_join_aggregate", jag[0]["rows"][:5],
                                     [x["query_id"] for x in jag],
                                     "grouping column chosen by cardinality, not by the "
                                     "question wording; confirm before quoting")
            elif agg:
                g = agg[0]["group_by"]
                st, ans, ids = ("answered_from_aggregate", agg[0]["rows"][:5],
                                [x["query_id"] for x in agg])
                lim = None if norm(g) in nq else (
                    "grouping key %s was chosen by cardinality, not identified from the "
                    "question wording" % g)
            elif any(w in nq for w in join_words) and ctx["cross_table"]:
                c0 = {k: v for k, v in ctx["cross_table"][0].items() if k != "sql"}
                st, ans, ids, lim = ("answered_from_cross_table", c0,
                                     [x["query_id"] for x in ctx["cross_table"]], None)
            else:
                st, ans, ids = "deferred", None, []
                lim = ("no automatic mapping from this question to a column/metric; needs "
                       "the data dictionary or a human target definition")
            ctx["q_attempts"].append({"question": qs[:300], "status": st, "query_ids": ids,
                                      "answer": ans, "limitation": lim})
            if st == "deferred":
                ctx["pending"].append("confirm metric/field scope of: %s" % qs[:100])

        failed = [e for e in ctx["log"] if e["error"]]
        if status != "input_error":
            status = ("ok" if ctx["main"].get("aggregates") and not failed else
                      "partial" if (ctx["main"].get("aggregates") or
                                    ctx["main"].get("summaries")) else
                      "insufficient_evidence")
        if status == "ok" and (ctx["pending"] or
                               any(x["status"] == "deferred" for x in ctx["q_attempts"])):
            status = "partial"
        if not dm:
            ctx["uncertainty"].append("no data dictionary matched any column; field roles "
                                      "are inferred from declared types and observed values")
        ctx["summary"] = ("%d snapshot(s), %d table(s), %d SQL statement(s), %d aggregate(s), "
                          "%d join path(s), %d error(s), %d pending item(s)."
                          % (len(ctx["schema"]), sum(len(c["tables"]) for c in ctx["schema"]),
                             len(ctx["log"]), len(ctx["main"].get("aggregates") or []),
                             len(ctx["cross_table"]), len(ctx["errors"]), len(ctx["pending"])))
    except Exception as e:
        ctx["errors"].append({"stage": "main", "error": str(e),
                              "trace": traceback.format_exc()[-1000:]})
        status = "partial"

    ctx["status"] = status
    filled, nulls = {}, []
    try:
        res = result()
        res["status"] = status
        for k in contract:
            if k in RESERVED:
                filled[k] = res.get(k)
                continue
            try:
                v = value_for(k, ctx)
            except Exception:
                v = None
            if v is None:
                nulls.append(k)
            res[k] = v
            filled[k] = v
        res["contract_fill"] = {
            "fields": len(filled),
            "filled_non_null": sum(1 for v in filled.values() if v is not None),
            "null_fields": nulls,
            "note": "top-level contract keys are the verbatim echo; unknown fields "
                    "kept as null, never renamed"}
        if nulls:
            res["pending_human"] = list(res.get("pending_human") or []) + [
                "output_contract field(s) with no generator: %s" % ", ".join(nulls)]
    except Exception as exc:
        res = {"case_id": ctx.get("case_id", "unknown"), "status": "partial",
               "output_contract": contract,
               "errors": (ctx.get("errors") or []) +
                         [{"stage": "finalize", "error": str(exc)}],
               "summary": "finalization failed; only the partial deliverable is valid",
               "uncertainty": ["figures in this file were not cross-checked because "
                               "result assembly raised an error"]}
        for k in contract:
            res.setdefault(k, None)
    path = write(outdir, res)
    if not a.quiet:
        print("%s %s | case=%s status=%s queries=%d filled=%d/%d -> %s"
              % (SKILL, VERSION, res["case_id"], res["status"], len(ctx["log"]),
                 sum(1 for v in filled.values() if v is not None), len(filled), path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
