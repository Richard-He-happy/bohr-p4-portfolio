"""dbanalysis: filter binding, join-path inference and fan-out measurement,
data-quality checks, field-role inference and SVG rendering. Stdlib only."""

import re
from pathlib import Path

from dbcore import coded, esc, groups, metrics, numeric, q, run


# ---------------------------------------------------------------- filters
def filters(text, card):
    out, seen = [], set()
    toks = set(re.findall(r"[\"'“”‘’]([^\"'“”‘’]{1,40})[\"'“”‘’]", text))
    toks |= set(re.findall(r"\b[A-Za-z][A-Za-z0-9_\-]{2,30}\b", text))
    for tok in toks:
        tl = tok.strip().lower()
        for tb in card["tables"]:
            for c in tb["columns"]:
                if numeric(c) or (c.get("distinct") or 0) > 60:
                    continue
                for v in c.get("samples") or []:
                    if isinstance(v, str) and v.strip().lower() == tl != c["name"].lower() \
                            and (tb["name"], c["name"], v) not in seen:
                        seen.add((tb["name"], c["name"], v))
                        out.append({"table": tb["name"], "column": c["name"],
                                    "op": "=", "value": v,
                                    "basis": "literal found in task text"})
    for tb in card["tables"]:
        for c in tb["columns"]:
            if numeric(c):
                for m in re.finditer(re.escape(c["name"]) + r"[^\n]{0,40}?(>=|<=|>|<)\s*(\d+(?:\.\d+)?)",
                                     text, re.I):
                    out.append({"table": tb["name"], "column": c["name"],
                                "op": m.group(1), "value": float(m.group(2)),
                                "basis": "operator adjacent to column name"})
    return out[:6]


def where(fs):
    """AND across columns, IN within one column (avoids contradictory equals)."""
    eq, ops = {}, []
    for f in fs:
        if f["op"] == "=":
            eq.setdefault(f["column"], []).append(f["value"])
        else:
            ops.append(f)
    parts, prm = [], []
    for col, vals in eq.items():
        parts.append("%s IN (%s)" % (q(col), ",".join("?" * len(vals))))
        prm += vals
    for f in ops:
        parts.append("%s %s ?" % (q(f["column"]), f["op"]))
        prm.append(f["value"])
    return (" WHERE " + " AND ".join(parts) if parts else ""), prm


# ---------------------------------------------------------------- joins
def join_cands(card):
    names = {t["name"].lower(): t for t in card["tables"]}
    out, seen = [], set()

    def add(j):
        k = (j["child"], j["child_key"], j["parent"])
        if k not in seen:
            seen.add(k)
            out.append(j)

    for t in card["tables"]:
        for fk in t["foreign_keys"]:
            add({"child": t["name"], "child_key": fk["from"],
                 "parent": fk["to_table"], "parent_key": fk["to_col"] or "id",
                 "basis": "declared foreign key"})
    for t in card["tables"]:
        for c in t["columns"]:
            m = re.match(r"^(.*?)_?id$", c["name"].lower())
            if not m or c["name"].lower() in ("id", "rowid"):
                continue
            base = m.group(1).rstrip("_")
            for pn, pt in names.items():
                if pn == t["name"].lower() or len(base) < 2:
                    continue
                if (pn in (base, base + "s") or pn.rstrip("s") == base) and \
                        any(x["name"].lower() == "id" for x in pt["columns"]):
                    add({"child": t["name"], "child_key": c["name"], "parent": pt["name"],
                         "parent_key": "id", "basis": "name pattern %s -> %s.id"
                         % (c["name"], pt["name"])})
    return out[:3]


def measure(conn, j, log):
    c, ck, p, pk = j["child"], j["child_key"], j["parent"], j["parent_key"]
    e = run(conn, "SELECT (SELECT COUNT(*) FROM %s) AS child_rows,"
                  " (SELECT COUNT(*) FROM %s) AS parent_rows,"
                  " (SELECT COUNT(*) FROM %s c WHERE c.%s IS NOT NULL AND EXISTS"
                  " (SELECT 1 FROM %s p WHERE p.%s = c.%s)) AS matched"
                  % (q(c), q(p), q(c), q(ck), q(p), q(pk), q(ck)),
            "join accounting %s->%s" % (c, p), log)
    if e["error"] or not e["data"]:
        return None
    d = e["data"][0]
    f = run(conn, "SELECT MAX(n) AS mx, AVG(n) AS av FROM (SELECT %s, COUNT(*) n"
                  " FROM %s WHERE %s IS NOT NULL GROUP BY %s)"
            % (q(ck), q(c), q(ck), q(ck)), "fan-out %s.%s" % (c, ck), log)
    fr = (f["data"] or [{}])[0] if not f["error"] else {}
    mx = fr.get("mx")
    return {"parent_table": p, "parent_key": pk, "child_table": c, "child_key": ck,
            "basis": j["basis"], "parent_rows": d["parent_rows"],
            "child_rows": d["child_rows"], "child_rows_with_parent": d["matched"],
            "orphan_child_rows": (d["child_rows"] or 0) - (d["matched"] or 0),
            "max_children_per_key": mx,
            "avg_children_per_key": round(fr["av"], 3) if fr.get("av") else None,
            "fanout_note": ("join fans out up to %s rows per key; aggregate the child "
                            "side before joining" % mx) if (mx or 0) > 1 else
                           "at most one child row per key; join safe for row counts",
            "query_id": e["id"], "sql": e["sql"]}


# ---------------------------------------------------------------- analysis
def analyse(conn, card, text, ctx, log):
    tb_list = [t for t in card["tables"] if t["rows"]]
    if not tb_list:
        return
    primary = max(tb_list, key=lambda t: t["rows"])
    ctx["main"].update({"primary_table": primary["name"], "n_rows": primary["rows"]})
    fs = filters(text, card)
    ctx["assumptions"] += ["filter %s.%s %s %r applied: literal appears in task text"
                           % (f["table"], f["column"], f["op"], f["value"]) for f in fs]
    for tb in [primary] + [t for t in tb_list if t is not primary][:1]:
        for g in groups(tb):
            for mc in metrics(tb)[:2]:
                e = run(conn, "SELECT %s AS grp, COUNT(*) AS n, AVG(%s) AS mean,"
                              " MIN(%s) AS mn, MAX(%s) AS mx, SUM(%s) AS total"
                              " FROM %s GROUP BY %s ORDER BY n DESC LIMIT 20"
                        % (q(g["name"]), q(mc["name"]), q(mc["name"]), q(mc["name"]),
                           q(mc["name"]), q(tb["name"]), q(g["name"])),
                        "group profile %s.%s by %s" % (tb["name"], mc["name"], g["name"]), log)
                if not e["error"] and e["data"]:
                    ctx["main"].setdefault("aggregates", []).append(
                        {"table": tb["name"], "group_by": g["name"],
                         "metric": mc["name"], "query_id": e["id"], "rows": e["data"]})
    by = {}
    for f in fs:
        by.setdefault(f["table"], []).append(f)
    for tn, fl in list(by.items())[:2]:
        w, prm = where(fl)
        e = run(conn, "SELECT COUNT(*) AS n FROM %s" % q(tn) + w,
                "filtered row count %s" % tn, log, prm)
        ctx["main"].setdefault("filtered", []).append(
            {"table": tn, "where": w.strip(), "params": prm, "query_id": e["id"],
             "n_rows": (e["data"] or [{}])[0].get("n") if not e["error"] else None,
             "error": e["error"]})
    for mc in metrics(primary)[:3]:
        e = run(conn, "SELECT COUNT(%s) AS n, AVG(%s) AS mean, MIN(%s) AS mn,"
                      " MAX(%s) AS mx FROM %s"
                % (q(mc["name"]), q(mc["name"]), q(mc["name"]), q(mc["name"]),
                   q(primary["name"])), "summary %s.%s" % (primary["name"], mc["name"]), log)
        if not e["error"]:
            ctx["main"].setdefault("summaries", []).append(
                {"table": primary["name"], "column": mc["name"], "query_id": e["id"],
                 "stats": (e["data"] or [{}])[0], "sql": e["sql"]})
    e = run(conn, "SELECT * FROM %s LIMIT 5" % q(primary["name"]),
            "sample rows %s" % primary["name"], log)
    ctx["main"]["sample_rows"] = [] if e["error"] else e["data"]
    keep = {t["name"] for t in card["tables"]}
    for j in join_cands(card):
        if j["parent"] in keep:
            m = measure(conn, j, log)
            if m:
                ctx["cross_table"].append(m)
    # cross-table aggregate: parent dimension label x child measure
    jj = join_cands(card)
    if jj:
        j = jj[0]
        par = next((t for t in card["tables"] if t["name"] == j["parent"]), None)
        chi = next((t for t in card["tables"] if t["name"] == j["child"]), None)
        dims, mets = (groups(par) if par else [])[:2], (metrics(chi) if chi else [])[:2]
        made = 0
        for g in dims[:2]:
            for mc in mets[:1]:
                e = run(conn, "SELECT p.%s AS grp, COUNT(*) AS n, AVG(c.%s) AS mean"
                              " FROM %s c JOIN %s p ON p.%s = c.%s GROUP BY p.%s"
                              " ORDER BY n DESC LIMIT 20"
                        % (q(g["name"]), q(mc["name"]), q(j["child"]), q(j["parent"]),
                           q(j["parent_key"]), q(j["child_key"]), q(g["name"])),
                        "joined aggregate %s.%s by %s.%s"
                        % (j["child"], mc["name"], j["parent"], g["name"]), log)
                if not e["error"] and e["data"]:
                    ctx["main"].setdefault("join_aggregates", []).append(
                        {"parent_table": j["parent"], "child_table": j["child"],
                         "group_by": "%s.%s" % (j["parent"], g["name"]),
                         "metric": "%s.%s" % (j["child"], mc["name"]),
                         "rows": e["data"], "query_id": e["id"], "sql": e["sql"],
                         "note": "dimension taken from the parent table, measure from "
                                 "the child; fan-out checked by the join query"})
                    made += 1


def quality(conn, card):
    rep = {"duplicate_rows": [], "missing_values": [], "coded_fields": [],
           "outliers": [], "type_mix": []}
    for tb in card["tables"]:
        if not tb["rows"]:
            continue
        try:
            d = tb["rows"] - conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT *"
                                          " FROM %s)" % q(tb["name"])).fetchone()[0]
            if d:
                rep["duplicate_rows"].append({"table": tb["name"], "rows": tb["rows"],
                                              "duplicate_rows": d})
        except Exception:
            pass
        pk = {c["name"] for c in tb["columns"] if c.get("pk")}
        cols = [c["name"] for c in tb["columns"] if c["name"] not in pk]
        if cols and pk:
            try:
                d2 = tb["rows"] - conn.execute(
                    "SELECT COUNT(*) FROM (SELECT DISTINCT %s FROM %s)"
                    % (",".join(q(x) for x in cols), q(tb["name"]))).fetchone()[0]
                if d2:
                    rep["duplicate_rows"].append(
                        {"table": tb["name"], "duplicate_rows_ignoring_pk": d2,
                         "key_columns": sorted(pk),
                         "note": "rows repeat on every non-key column; deduplicate "
                                 "before counting"})
            except Exception:
                pass
        for c in tb["columns"]:
            if c.get("nulls"):
                rep["missing_values"].append({"table": tb["name"], "column": c["name"],
                                              "nulls": c["nulls"]})
            if coded(c):
                rep["coded_fields"].append({"table": tb["name"], "column": c["name"],
                                            "values": c.get("samples"),
                                            "rule": "low-cardinality numeric treated as a "
                                                    "code; never averaged"})
            elif numeric(c) and not c.get("pk") and tb["rows"] >= 8 \
                    and not re.search(r"(id|key)$", c["name"].lower()):
                try:
                    vals = [r[0] for r in conn.execute(
                        "SELECT %s FROM %s WHERE %s IS NOT NULL ORDER BY %s"
                        % (q(c["name"]), q(tb["name"]), q(c["name"]), q(c["name"])))]
                except Exception:
                    continue
                if len(vals) >= 8 and all(isinstance(v, (int, float)) for v in vals):
                    k = len(vals)
                    a, b = vals[max(0, k // 4 - 1)], vals[min(k - 1, 3 * k // 4)]
                    iqr, lo, hi = b - a, a - 1.5 * (b - a), b + 1.5 * (b - a)
                    n = sum(1 for v in vals if v < lo or v > hi)
                    if n and iqr:
                        rep["outliers"].append({"table": tb["name"], "column": c["name"],
                                                "method": "1.5xIQR", "fence": [lo, hi],
                                                "count": n, "checked": k})
            else:
                try:
                    kinds = [r for r in conn.execute(
                        "SELECT typeof(%s) t, COUNT(*) n FROM %s GROUP BY t"
                        % (q(c["name"]), q(tb["name"]))).fetchall() if r[0] != "null"]
                    if len(kinds) > 1:
                        rep["type_mix"].append({"table": tb["name"], "column": c["name"],
                                                "types": {r[0]: r[1] for r in kinds}})
                except Exception:
                    pass
    return rep


def fields(card, dm, rep):
    code = {(d["table"], d["column"]) for d in rep.get("coded_fields", [])}
    out = []
    for tb in card["tables"]:
        for c in tb["columns"]:
            d = dm.get(c["name"].lower())
            role = ("key" if c["pk"] else "code" if (tb["name"], c["name"]) in code
                    else "measure" if numeric(c) else "dimension")
            out.append({
                "table": tb["name"], "column": c["name"], "declared_type": c["decl"],
                "role": role, "distinct": c.get("distinct"), "nulls": c.get("nulls"),
                "samples": c.get("samples"),
                "dictionary": d["text"] if d else None,
                "dictionary_at": ("%s:%s" % (d["src"], d["loc"])) if d else None,
                "caution": "code field: do not average" if role == "code" else
                           "dictionary label applied" if d else
                           "no dictionary entry; role inferred from type and values"})
    return out[:120]


def svg(path, title, labels, values, ylabel):
    w, h, pl, pb, pt = 560, 340, 70, 70, 40
    vmax = max([abs(v) for v in values if isinstance(v, (int, float))] or [0]) or 1
    bw = (w - pl - 20) / max(1, len(values))
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
         'viewBox="0 0 %d %d">' % (w, h, w, h),
         '<rect width="100%" height="100%" fill="#fff"/>',
         '<text x="%d" y="24" font-family="sans-serif" font-size="15">%s</text>'
         % (pl, esc(title)),
         '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (pl, h - pb, w - 10, h - pb),
         '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>' % (pl, pt, pl, h - pb),
         '<text x="6" y="%d" font-family="sans-serif" font-size="11">%s</text>'
         % (pt + 4, esc(ylabel))]
    for i, (lb, v) in enumerate(zip(labels, values)):
        if not isinstance(v, (int, float)):
            continue
        bh = (h - pb - pt) * abs(v) / vmax
        x, y = pl + 10 + i * bw, h - pb - bh
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#3b6ea5"/>'
                 % (x, y, bw * .7, bh))
        s.append('<text x="%.1f" y="%.1f" font-size="9">%s</text>' % (x, y - 3, esc(round(v, 2))))
        s.append('<text x="%.1f" y="%.1f" font-size="10" transform="rotate(-35 %.1f %.1f)">%s</text>'
                 % (x, h - pb + 14, x, h - pb + 14, esc(str(lb)[:18])))
    s.append("</svg>")
    Path(path).write_text("\n".join(s), encoding="utf-8")
    return path
