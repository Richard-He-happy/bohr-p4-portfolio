#!/usr/bin/env python3
"""Engine for literature-data-cleaner: unit parsing/conversion, value parsing,
row shaping, row cleaning and duplicate/conflict detection. Stdlib only.

Imported by main.py; has no CLI of its own.
"""
import csv, json, re
from pathlib import Path

V = "1.0.0"
MISS = {"", "-", "--", "\u2014", "\u2013", "na", "n/a", "nan", "none", "null", "nr", "n.r", "n.r.",
        "n.d.", "nd", "not reported", "\u672a\u62a5\u544a", "tbd"}

def rd(p):
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            t = raw.decode(enc)
            return t, enc, t.count("\ufffd"), None
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace"), "latin-1", 1, "decode_fallback"

def ljson(p):
    t, e, b, err = rd(p)
    if err:
        return None, err
    try:
        return json.loads(t), None
    except Exception as exc:
        return None, "json_error:%s" % exc

def wjson(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def wcsv(p, rows, fields):
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in fields} for r in rows)

def nat(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]

def fmt(x, sig=6):
    if x is None or x == "":
        return ""
    if isinstance(x, str):
        return x
    if x == 0:
        return "0"
    if abs(x) >= 1e6 or abs(x) < 1e-4:
        return ("%.*e" % (sig - 1, x)).replace("e+", "e").replace("e-0", "e-")
    return "%.*g" % (sig, x)

class Units:

    def __init__(s, t):
        s.pf, s.base, s.canon = t.get("prefixes", {}), t.get("base_units", {}), t.get("canonical", {})
        s.unk = {str(x).lower() for x in t.get("unknown_unit_tokens", [])}
        s.sym = {}
        for k, v in t.get("units", {}).items():
            e = (dict(v.get("dim", {})), float(v.get("scale", 1.0)), float(v.get("offset", 0.0)))
            s.sym[k] = e
            for a in v.get("aliases", []):
                s.sym.setdefault(a, e)

    def tok(s, t):
        if t in ("1", "1.0"):
            return {}, 1.0, 0.0
        m = re.fullmatch(r"([A-Za-z%\u00b0\u00b5\u03bc\u2030]+)(?:\^?([+-]?\d+))?", t)
        if not m:
            return None
        sym, ex, h = m.group(1), int(m.group(2) or 1), None
        if sym in s.sym:
            h = s.sym[sym]
        else:
            for i in range(len(sym) - 1, 0, -1):
                p, rest = sym[:i], sym[i:]
                if p in s.pf and rest in s.sym:
                    d, sc, o = s.sym[rest]
                    h = (d, sc * s.pf[p], 0.0)
                    break
        if h is None:
            return None
        d, sc, o = h
        return {k: v * ex for k, v in d.items()}, sc ** ex, o if ex == 1 else 0.0

    def parse(s, txt):
        if txt is None:
            return None
        raw = str(txt).strip()
        if not raw or raw.lower() in s.unk:
            return None
        for a, b in (("\u2212", "-"), ("\u00b7", "*"), ("\u22c5", "*"), ("\u00d7", "*"),
                     ("\u00b5", "u"), ("\u03bc", "u"), ("\u00a0", " ")):
            raw = raw.replace(a, b)
        dim, sc, sg, off, n = {}, 1.0, 1, 0.0, 0
        for tk in re.findall(r"[*/]|[^\s*/]+", re.sub(r"\(.*?\)|\[.*?\]", " ", raw)):
            if tk in ("*", "/"):
                sg = 1 if tk == "*" else -1
                continue
            h = s.tok(tk)
            if h is None:
                return None
            d, f, o = h
            for k, v in d.items():
                dim[k] = dim.get(k, 0) + v * sg
            sc *= f ** sg
            off += o if sg == 1 else 0.0
            n += 1
        return {"dim": {k: v for k, v in dim.items() if v}, "scale": sc,
                "offset": off if n == 1 else 0.0}

    def convert(s, src):
        """unit/factor/offset/derived with after = before*factor + offset."""
        p = s.parse(src)
        if p is None:
            return None
        key = ",".join("%s:%d" % (k, p["dim"][k]) for k in sorted(p["dim"]) if p["dim"][k])
        name, der = s.canon.get(key), False
        if name is None:  # unknown dimension combination -> derive from base units
            name = "*".join("%s^%d" % (s.base.get(k, k), p["dim"][k]) for k in sorted(p["dim"])) or "1"
            der = True
        t = s.parse(name) or {"scale": 1.0, "offset": 0.0}
        return {"unit": name, "derived": der, "factor": p["scale"] / t["scale"],
                "offset": (p["offset"] - t["offset"]) / t["scale"]}

SUP = str.maketrans("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207b\u207a",
                    "0123456789-+")
NUM = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
TAIL = r"(?:\s*([A-Za-z%\u00b0\u00b5\u03bc][A-Za-z0-9%\u00b0\u00b5\u03bc*/.^\-]*))?"

def pq(raw):
    """number | range | value+-err | missing | text, with inline unit if present."""
    q = {"kind": "missing", "raw": "" if raw is None else str(raw)}
    if raw is None:
        return q
    t = str(raw).strip().translate(SUP)
    for a, b in (("\u2212", "-"), ("\u2013", "-"), ("\u2014", "-"), ("\u00d7", "x"),
                 ("\u00a0", " "), ("\u2264", "<="), ("\u2265", ">="), ("\u2248", "~")):
        t = t.replace(a, b)
    t = re.sub(r"\s*[xX*]\s*10\s*\^?\s*([+-]?\d+)", r"e\1", t)
    t = re.sub(r"\(([^)]*)\)", " ", t)
    body = t.strip().strip(";,").strip()
    if body.lower().rstrip(".") in MISS:
        return q
    ineq = ""
    m = re.match(r"^(<=|>=|<|>|~|ca\.?|about|approx\.?)\s*", body, flags=re.I)
    if m:
        ineq, body = m.group(1), body[m.end():].strip()
    body = body.replace("+/-", "\u00b1").replace("+-", "\u00b1")
    if "\u00b1" in body:
        a, b = body.split("\u00b1", 1)
        la, lb = re.search(NUM, a.replace(" ", "")), re.search(NUM, b.replace(" ", ""))
        if la and lb:
            return {"kind": "error", "raw": q["raw"], "ineq": ineq,
                    "value": float(la.group(0).replace(",", "")), "err": abs(float(lb.group(0).replace(",", "")))}
    if re.fullmatch(r"[0-9eE.,+\-\s]*", body):
        body = body.replace(" ", "")
    m = re.fullmatch(r"(%s)(?:-|~|to)(%s)%s" % (NUM, NUM, TAIL), body, flags=re.I)
    if m:
        a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        q.update(kind="range", low=min(a, b), high=max(a, b), ineq=ineq, swapped=a > b, unit=(m.group(3) or "").strip())
        return q
    m = re.fullmatch(r"(%s)%s" % (NUM, TAIL), body, flags=re.I)
    if m:
        q.update(kind="number", ineq=ineq, unit=(m.group(2) or "").strip(),
                 value=float(m.group(1).replace(",", "")))
        return q
    return {"kind": "text", "raw": q["raw"]}

SUBS = str.maketrans("\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089", "0123456789")

def nkey(s):
    t = str(s or "").strip().translate(SUBS).lower().replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", t).strip(" .;,:*")

def hdr_unit(name):
    """'band gap (eV)' -> ('band gap', 'eV')."""
    s = str(name).strip()
    m = re.search(r"[（(]\s*([^)）]{1,18})\s*[)）]\s*$", s)
    if m:
        return s[:m.start()].strip(), m.group(1).strip()
    if "/" in s:
        h, t = s.rsplit("/", 1)
        if h.strip() and re.fullmatch(r"[A-Za-z%\u00b0\u00b5\u03bc][A-Za-z0-9%\u00b0\u00b5\u03bc*^.\-]*", t.strip()):
            return h.strip(), t.strip()
    return s, ""

def roles_of(cols, fsyn):
    roles, used = {}, set()
    for role in ("row_id", "source_document_id", "source_locator", "unit", "value", "indicator", "material"):
        keys = [str(k).lower().replace("-", "_").replace(" ", "_") for k in fsyn.get(role, [])]
        best = None
        for c in cols:
            if c in used:
                continue
            low = str(c).lower().replace("-", "_").replace(" ", "_")
            if low in keys:
                best = (0, keys.index(low), c)
                break
            for i, k in enumerate(keys):
                if best is None and len(k) >= 3 and k in low:
                    best = (1, i, c)
        if best:
            roles[best[2]] = role
            used.add(best[2])
    return roles

def nm(text, syn):
    raw = str(text or "").strip()
    k = nkey(raw)
    if k in syn:
        return syn[k]
    c = raw.replace(" ", "")
    if c.lower() in syn:
        return syn[c.lower()]
    return c if re.search(r"\d", c) and re.fullmatch(r"[A-Za-z0-9().\-]+", c) else raw

def shape(tab, roles, conds, msyn, isyn, res):
    out, seen, g = [], {}, lambda r: next((c for c, x in roles.items() if x == r), None)
    for i, src in enumerate(tab["rows"]):
        rid = str(src.get(g("row_id"), "")).strip() if g("row_id") else ""
        if not rid:
            rid = "derived-%d" % (i + 1)
            res["degradations"].append({"stage": "identity", "file": tab["file"].name, "index": i + 1,
                                        "note": "row id missing -> derived (R002)"})
        elif rid in seen:
            seen[rid] += 1
            res["degradations"].append({"stage": "identity", "file": tab["file"].name, "row_id": rid,
                                        "note": "repeated row id -> suffix #%d (R002)" % seen[rid]})
            rid = "%s#%d" % (rid, seen[rid])
        else:
            seen[rid] = 1
        ind = str(src.get(g("indicator"), "")).strip()
        head, hu = hdr_unit(ind)
        cv = {c: str(src.get(c, "")).strip() for c in conds}
        out.append({"row_id": rid, "source_document_id": str(src.get(g("source_document_id"), "")).strip(),
                    "source_locator": str(src.get(g("source_locator"), "")).strip(),
                    "material": nm(src.get(g("material"), ""), msyn), "indicator": nm(head or ind, isyn),
                    "conds": cv, "condition_summary": "; ".join("%s=%s" % kv for kv in sorted(cv.items()) if kv[1]),
                    "value_raw": str(src.get(g("value"), "")).strip(),
                    "unit_raw": str(src.get(g("unit"), "")).strip() or hu, "original_field": ind})
    return out

def clean(row, units):
    """-> (clean_row, change_entries, pending_entries, uncertainties)."""
    ch, pe, un, rules = [], [], [], set()
    vr, ur = row["value_raw"], row["unit_raw"]
    q = pq(vr)
    ut = ur.strip() or q.get("unit", "").strip()
    if not ur.strip() and q.get("unit"):
        rules.add("R004")
    cond = "|".join("%s=%s" % (nkey(k), nkey(v)) for k, v in sorted(row["conds"].items()) if str(v).strip())
    o = {"row_id": row["row_id"], "source_document_id": row["source_document_id"],
         "source_locator": row["source_locator"], "indicator": row["indicator"], "material": row["material"],
         "condition_summary": row["condition_summary"], "value": None, "value_low": None,
         "value_high": None, "value_err": None, "value_text": "", "unit": "",
         "original_field": row["original_field"], "original_value": vr, "original_unit": ur,
         "rule_ids": "", "status": "ok", "duplicate_of": "", "note": "", "_conds": row["conds"],
         "judgment_key": "|".join([row["source_document_id"] or "-", cond or "-",
                                   nkey(row["indicator"]) or "-", nkey(row["material"]) or "-"])}

    def pend(code, reason, action, field="unit"):
        pe.append({"row_id": o["row_id"], "field": field, "reason_code": code, "reason": reason,
                   "suggested_action": action, "original_value": vr, "original_unit": ur or ut,
                   "source_document_id": row["source_document_id"], "source_locator": row["source_locator"]})
        un.append({"type": code, "row_id": o["row_id"], "detail": "%s %s" % (vr, ut), "action": "pending"})

    if q["kind"] == "missing":
        o.update(status="missing", value_text="(missing: %s)" % vr.strip(), rule_ids="R006")
        return o, ch, pe, un
    if q["kind"] == "text":
        o.update(status="needs_review", value_text=vr.strip(), rule_ids="R006;R010")
        pend("unparsed_value", "cell is neither a number, a range nor a +/- value",
             "enter the numeric value or missing code from source", "value")
        return o, ch, pe, un
    if not ut:
        o.update(status="needs_review", value_text="%s (no unit)" % q.get("raw", ""), rule_ids="R011")
        pend("missing_unit", "numeric value without a unit; conversion and comparison unsafe",
             "confirm unit from the header or caption")
        return o, ch, pe, un
    cvt = units.convert(ut)
    if cvt is None:
        o.update(status="needs_review", value_text="%s %s" % (q.get("raw", ""), ut), rule_ids="R010")
        pend("unknown_unit", "unit not resolvable by the unit table (a.u./arb./unparsable)",
             "confirm unit; arbitrary units stay out of statistics")
        return o, ch, pe, un
    fac, off = cvt["factor"], cvt["offset"]
    dec = len((re.search(r"\.(\d+)", str(vr)) or ["", ""])[1])
    o["unit"] = cvt["unit"]
    if q["kind"] == "range":
        todo, rules = [("value_low", q["low"]), ("value_high", q["high"])], rules | {"R007"}
    elif q["kind"] == "error":
        todo, rules = [("value", q["value"]), ("value_err", q["err"])], rules | {"R008"}
    else:
        todo = [("value", q["value"])]
    for field, num in todo:
        use = off if field != "value_err" else 0.0
        new = num * fac + use
        o[field] = abs(new) if field == "value_err" else new
        if abs(fac - 1.0) > 1e-12 or abs(use) > 1e-12:
            ftxt = ("v*%s" % fmt(fac, 10) if abs(fac - 1.0) > 1e-12 else "v") + (
                (("+%s" if use > 0 else "-%s") % fmt(abs(use), 10)) if abs(use) > 1e-12 else "")
            rid = "R008" if field == "value_err" else "R009"
            rules.add(rid)
            ch.append({"row_id": o["row_id"], "field": field, "before": fmt(num), "after": fmt(new),
                       "unit_before": ut, "unit_after": cvt["unit"], "factor": fmt(fac, 10),
                       "offset": fmt(use, 10), "formula": ftxt, "precision": "src_decimals=%d" % dec,
                       "rule_id": rid, "source_document_id": row["source_document_id"],
                       "source_locator": row["source_locator"],
                       "note": "range bound converted separately (R007)" if q["kind"] == "range" else ""})
        else:
            o["note"] = (o["note"] + " same_unit").strip()
    if q["kind"] == "range":
        o["value_text"] = "%s-%s" % (fmt(q["low"]), fmt(q["high"]))
    elif q["kind"] == "error":
        o["value_text"] = "%s +/- %s" % (fmt(q["value"]), fmt(q["err"]))
    else:
        o["value_text"] = fmt(q["value"])
    if q.get("ineq"):
        o["note"] = (o["note"] + " ineq=%s" % q["ineq"]).strip()
        un.append({"type": "inequality", "row_id": o["row_id"], "detail": q["ineq"] + str(vr),
                   "action": "note: bound"})
    o["rule_ids"] = ";".join(sorted(rules))
    return o, ch, pe, un

def spread(vals):
    n = [abs(v) for v in vals if v is not None]
    return 0.0 if len(n) < 2 or not max(n) else (max(n) - min(n)) / max(n)

def dedup(rows, lib, res):
    """Exact repeats merge; replicates stay; conflicts are flagged."""
    jk = lib.get("judgment_key", {})
    tol = float(jk.get("conflict_relative_tolerance", .05))
    rep = float(jk.get("replicate_relative_tolerance", .05))
    groups, dups, confl = {}, [], []
    for r in rows:
        if r["status"] not in ("missing", "needs_review"):
            groups.setdefault(r["judgment_key"], []).append(r)
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda x: nat(x["row_id"]))
        if len(g) < 2:
            continue
        ids = [r["row_id"] for r in g]
        vals = [r["value"] if r["value"] is not None else r["value_low"] for r in g]
        units = sorted({r["unit"] for r in g})
        if len(units) > 1:
            confl.append({"judgment_key": key, "row_ids": ids, "kind": "unit_conflict",
                          "values": [fmt(v) for v in vals], "reason": "same key, units %s" % units})
            for r in g:
                r["status"] = "conflict"
            res["uncertainties"].append({"type": "source_conflict", "row_id": ids[0], "action": "pending_review",
                                         "detail": "units differ inside one judgment key"})
            continue
        same = all(v is not None and abs(v - vals[0]) <= 1e-9 * max(abs(v) for v in vals) for v in vals)
        sp = spread(vals)
        if same:
            for r in g[1:]:
                r["status"], r["duplicate_of"] = "merged_duplicate", g[0]["row_id"]
            dups.append({"judgment_key": key, "row_ids": ids, "merged_row_ids": ids[1:], "kept_row_id": ids[0],
                         "action": "merge", "reason": "identical source+condition+indicator+value (R013)"})
        elif sp <= rep:
            for r in g[1:]:
                r["status"] = "replicate"
            dups.append({"judgment_key": key, "row_ids": ids, "merged_row_ids": [], "kept_row_id": ids[0],
                         "action": "keep_separate", "reason": "same key, spread <=%.0f%%: repeat "
                         "measurement, not duplicate record (R014)" % (rep * 100)})
        else:
            confl.append({"judgment_key": key, "row_ids": ids, "kind": "value_conflict", "unit": units[0],
                          "values": [fmt(v) for v in vals], "reason": "same source+condition, spread %.0f%% > "
                          "%.0f%%: conversion cannot resolve (R015)" % (sp * 100, tol * 100)})
            for r in g:
                r["status"] = "conflict"
            res["uncertainties"].append({"type": "source_conflict", "row_id": ids[0],
                                         "detail": "values %s %s" % ([fmt(v) for v in vals], units[0]),
                                         "action": "pending_review"})
    return dups, confl

def counts_of(ch, pe):
    out = {}
    pairs = [(c["rule_id"], "%s:%s %s->%s" % (c["row_id"], c["field"], c["before"], c["after"])) for c in ch]
    pairs += [({"unknown_unit": "R010", "missing_unit": "R011", "unparsed_value": "R006"}.get(p["reason_code"]),
               "%s:%s" % (p["row_id"], p["reason_code"])) for p in pe]  # pending -> rule id
    for rid, ex in pairs:
        if rid:
            e = out.setdefault(rid, {"count": 0, "examples": []})
            e["count"] += 1
            if len(e["examples"]) < 3:
                e["examples"].append(ex)
    return out

def claims_of(ch, pe, rows, s, cap, txt):
    T, out = txt.get("claim", {}), []

    def add(kind, rdb, stmt, quote, rid, sid, loc, cond=""):
        if len(out) < cap:
            out.append({"claim_id": "C%04d" % (len(out) + 1), "kind": kind, "readability": rdb,
                        "statement": stmt, "evidence": {"quote": quote, "rule_id": rid}, "source_id": sid,
                        "location": loc, "condition": cond})

    for c in ch[:int(cap * .7)]:
        add("inferred", "inferred", T.get("converted", "") % (c["row_id"], c["field"], c["before"],
            c["unit_before"], c["rule_id"], c["after"], c["unit_after"]), "%s %s" % (c["before"], c["unit_before"]),
            c["rule_id"], c["source_document_id"], {"row_id": c["row_id"], "field": c["field"],
                                                    "source_locator": c["source_locator"]})
    for p in pe[:int(cap * .2)]:
        add("undetermined", "undetermined", T.get("pending", "") % (p["row_id"], p["field"], p["reason_code"]),
            "%s %s" % (p["original_value"], p["original_unit"] or ""), "R010", p["source_document_id"],
            {"row_id": p["row_id"], "field": p["field"], "source_locator": p["source_locator"]})
    add("reported", "directly_read", T.get("counts", "") % (s["input_rows"], s["cleaned_rows"],
        s["analytic_rows"], s["merged_duplicates"], s["conflicts"], s["pending_review"]), "", "", "",
        {"file": "cleaned.csv"})
    return out

