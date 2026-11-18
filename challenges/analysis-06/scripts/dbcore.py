"""dbcore: material discovery, schema cards, data-dictionary mapping and
read-only SQL execution for the science-db-query-analysis skill. Stdlib only."""

import csv
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

MAGIC = b"SQLite format 3\x00"
ROW_LIMIT = 500


def q(x):
    return '"' + str(x).replace('"', '""') + '"'


def sha1(p):
    h = hashlib.sha1()
    try:
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(65536), b""):
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


def read(p, cap=2000000):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")[:cap]
    except Exception:
        return ""


def isdb(p):
    try:
        with open(p, "rb") as f:
            return f.read(16) == MAGIC
    except Exception:
        return False


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def norm(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", str(s).lower()).strip("_")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- discovery
def discover(d):
    f = {"case": None, "dbs": [], "csvs": [], "jsons": [], "texts": [], "files": []}
    if not d.exists():
        return f
    for p in sorted(x for x in d.rglob("*") if x.is_file()):
        f["files"].append(p)
        n, e = p.name.lower(), p.suffix.lower()
        if n == "case.json" or (e == ".json" and n.startswith("case")):
            if f["case"] is None:
                f["case"] = p
        elif e in (".db", ".sqlite", ".sqlite3", ".db3") and isdb(p):
            f["dbs"].append(p)
        elif e == ".csv":
            f["csvs"].append(p)
        elif e == ".json":
            f["jsons"].append(p)
        elif e in (".md", ".txt", ".tsv", ".yaml", ".yml", ".log"):
            f["texts"].append(p)
    return f


def load_case(f):
    if not f["case"]:
        return {}
    try:
        d = json.loads(read(f["case"], 4000000))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def flat(o, d=0, out=None):
    out = [] if out is None else out
    if d > 6:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            out.append((str(k), v if isinstance(v, str) else ""))
        for v in o.values():
            flat(v, d + 1, out)
    elif isinstance(o, list):
        for v in o:
            flat(v, d + 1, out)
    return out


def instr_text(case):
    keys = ("instruction", "task", "question", "goal", "requirement", "prompt",
            "description", "scope", "workorder", "output_contract", "note")
    return "\n".join(v for k, v in flat(case)
                     if v and any(s in k.lower() for s in keys))[:20000]


def questions(case):
    qs, seen = [], set()

    def walk(o, d=0):
        if d > 5:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and len(v) > 8 and any(
                        s in k.lower() for s in ("question", "task", "requirement")):
                    qs.append(v)
                else:
                    walk(v, d + 1)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, str) and len(v) > 8:
                    qs.append(v)
                else:
                    walk(v, d + 1)
    walk(case.get("questions") or case.get("tasks") or {})
    return [s for s in qs if not (s in seen or seen.add(s))][:6]


# ---------------------------------------------------------------- dictionary
def dictionary(f, cols):
    low = {c.lower(): c for c in cols}
    dm = {}

    def put(k, txt, src, loc, raw=None, path=None):
        k = str(k).strip().lower()
        if k in low:
            dm.setdefault(k, {"text": "", "src": src, "loc": loc,
                              "raw": raw, "path": path})
            dm[k]["text"] = (dm[k]["text"] + " | " + str(txt)[:400]).lstrip(" |")

    def walk(o, src, path, d=0):
        if d > 5:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in low and isinstance(v, (str, dict, list)):
                    put(k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False),
                        src, path + "/" + str(k))
                walk(v, src, path + "/" + str(k), d + 1)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, src, "%s/%d" % (path, i), d + 1)

    for p in f["jsons"]:
        try:
            walk(json.loads(read(p, 3000000)), p.name, "#")
        except Exception:
            continue
    for p in f["texts"]:
        for i, line in enumerate(read(p, 400000).splitlines()):
            cells = [c.strip() for c in re.split(r"\|", line)] if "|" in line \
                else [c.strip() for c in line.split("\t")]
            while cells and cells[0] == "":      # markdown rows start/end with a pipe
                cells = cells[1:]
            while cells and cells[-1] == "":
                cells = cells[:-1]
            if len(cells) >= 2 and cells[0].strip("`* ").lower() in low:
                put(cells[0].strip("`* "), " ; ".join(x for x in cells[1:] if x),
                    p.name, "line:%d" % (i + 1), raw=line.strip()[:300], path=str(p))
    return dm


# ---------------------------------------------------------------- schema
def connect(p):
    conn = sqlite3.connect("file:%s?mode=ro" % Path(p).resolve().as_posix(),
                           uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def card_of(conn, p):
    c = {"name": Path(p).name, "path": str(p), "bytes": Path(p).stat().st_size,
         "sha1": sha1(p), "tables": []}
    for t in tables(conn):
        cols = []
        for r in conn.execute("PRAGMA table_info(%s)" % q(t)):
            d = {"name": r["name"], "decl": r["type"] or "", "pk": bool(r["pk"])}
            try:
                d["nulls"] = conn.execute("SELECT COUNT(*) FROM %s WHERE %s IS NULL"
                                          % (q(t), q(r["name"]))).fetchone()[0]
                d["distinct"] = conn.execute("SELECT COUNT(DISTINCT %s) FROM %s"
                                             % (q(r["name"]), q(t))).fetchone()[0]
                d["samples"] = [x[0] for x in conn.execute(
                    "SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL LIMIT 8"
                    % (q(r["name"]), q(t), q(r["name"])))]
            except Exception as e:
                d["error"] = str(e)
            cols.append(d)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM %s" % q(t)).fetchone()[0]
        except Exception:
            rows = None
        fks = [{"from": r["from"], "to_table": r["table"], "to_col": r["to"]}
               for r in conn.execute("PRAGMA foreign_key_list(%s)" % q(t))]
        c["tables"].append({"name": t, "rows": rows, "columns": cols,
                            "foreign_keys": fks})
    return c


def numeric(c):
    if any(k in (c.get("decl") or "").upper()
           for k in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC")):
        return True
    s = [v for v in (c.get("samples") or []) if v is not None]
    return bool(s) and all(isinstance(v, (int, float)) for v in s)


def coded(c):
    """Enumerated field: few distinct INTEGER values. Floats are never codes."""
    n, decl = (c.get("distinct") or 0), (c.get("decl") or "").upper()
    if not numeric(c) or not 2 <= n <= 12:
        return False
    if re.search(r"(id|key)$", c["name"].lower()):
        return False
    s = [v for v in (c.get("samples") or []) if v is not None]
    ints = bool(s) and all(isinstance(v, int) and not isinstance(v, bool) for v in s)
    return "INT" in decl or (not decl and ints)


def groups(tb):
    return [c for c in tb["columns"]
            if (not numeric(c) and 2 <= (c.get("distinct") or 0) <= 30) or coded(c)][:2]


def metrics(tb):
    return [c for c in tb["columns"]
            if numeric(c) and not coded(c) and not c.get("pk")
            and not re.search(r"(id|key)$", c["name"].lower())][:3]


# ---------------------------------------------------------------- execution
def repair(conn, err):
    m = re.search(r"no such (column|table):\s*([\w\.\"]+)", err, re.I)
    if not m:
        return None
    kind, bad = m.group(1).lower(), m.group(2).strip('"')
    want = bad.split(".")[-1].lower()
    for t in tables(conn):
        if kind == "table" and t.lower() == want:
            return t, bad
        if kind == "column":
            for r in conn.execute("PRAGMA table_info(%s)" % q(t)):
                if r["name"].lower() == want:
                    return r["name"], bad
    return None


def run(conn, sql, purpose, log, params=None, limit=None):
    limit = limit or ROW_LIMIT
    e = {"id": "Q%d" % (len(log) + 1), "purpose": purpose, "sql": sql,
         "params": params or [], "rows": 0, "ms": 0, "error": None, "data": []}
    s = time.time()
    try:
        e["data"] = [dict(r) for r in conn.execute(sql, params or []).fetchmany(limit)]
        e["rows"] = len(e["data"])
        e["rows"] = len(e["data"])
    except Exception as exc:
        msg = str(exc)
        fix = repair(conn, msg)
        if fix:
            good = re.sub(re.escape(fix[1]), q(fix[0]), sql, flags=re.I)
            try:
                e["data"] = [dict(r) for r in conn.execute(good, params or [])
                             .fetchmany(limit)]
                e.update({"rows": len(e["data"]), "sql": good,
                          "error": None, "repaired": {"error": msg, "to": fix[0]}})
            except Exception as exc2:
                e["error"] = "%s | retry: %s" % (msg, exc2)
        else:
            e["error"] = msg
    e["ms"] = round((time.time() - s) * 1000, 1)
    log.append(e)
    return e


# ---------------------------------------------------------------- CSV intake
def csv_table(conn, p, taken):
    name, i = norm(Path(p).stem) or "material", 2
    base = name
    while name in taken:
        name, i = "%s_%d" % (base, i), i + 1
    rows = list(csv.reader(read(p, 8000000).splitlines()))
    if len(rows) < 2:
        raise ValueError("csv has no data rows")
    head = [norm(h) or "col_%d" % i for i, h in enumerate(rows[0])]
    body = rows[1:]
    types = []
    for j in range(len(head)):
        vals = [r[j].strip() for r in body[:200] if j < len(r) and r[j].strip()]
        t = "INTEGER"
        for v in vals:
            if re.match(r"^-?\d+$", v):
                continue
            if re.match(r"^-?\d*\.?\d+([eE][-+]?\d+)?$", v):
                t = "REAL"
                continue
            t = "TEXT"
            break
        types.append(t)
    conn.execute("CREATE TABLE %s (%s)" % (q(name), ", ".join(
        "%s %s" % (q(h), t) for h, t in zip(head, types))))
    conn.executemany("INSERT INTO %s VALUES (%s)"
                     % (q(name), ",".join("?" * len(head))),
                     [r[:len(head)] + [None] * (len(head) - len(r)) for r in body])
    conn.commit()
    return name, len(body)
