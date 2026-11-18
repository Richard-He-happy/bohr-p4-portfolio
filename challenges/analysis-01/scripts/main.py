#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analysis-01 scientific data cleaning, Python stdlib only.

Cleans a dirty table against a data dictionary and workorder (missing / censored /
sentinel codes, format-unit-encoding faults, duplicates, outliers) without
statistical imputation, then writes the cleaned table and a field-level report.

  python3 main.py --input /input --output /app/output
"""
import argparse, csv, hashlib, json, math, re, sys, time, traceback, unicodedata
from datetime import datetime, timedelta
from pathlib import Path

V = "1.2.0"
HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"
DOC = (".md", ".json", ".docx", ".pdf", ".yaml", ".yml", ".txt")
SUP = str.maketrans({"\u207b": "-", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2070": "0", "\u2074": "4",
                     "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9"})
G = {"r": {}, "flat": {}}
S = {"errors": [], "degradations": [], "pending": [], "changes": [], "sources": [], "unc": []}


def add(k, c, m, **kw):
    d = {"code": c, "message": m}
    d.update(kw)
    S[k].append(d)
    return d


def hfile(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read(8 << 20)).hexdigest()[:40]
    except Exception:
        return None


def wjson(p, o):
    p, t = Path(p), Path(p).with_suffix(".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    t.replace(p)


def wcsv(p, hdr, rows):
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(hdr)
        for r in rows:
            w.writerow(["" if c is None else c for c in r])


def fn(x, prec=None):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return ""
    if prec is not None:
        return ("%." + str(int(prec)) + "f") % float(x)
    s = "%.12g" % float(x)
    return "0" if s in ("-0", "-0.0") else s


def med(xs):
    xs, n = sorted(xs), len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def quant(xs, q):
    xs, n = sorted(xs), len(xs)
    pos = (n - 1) * q
    lo = min(int(math.floor(pos)), n - 1)
    hi = min(lo + 1, n - 1)
    return xs[lo] if n == 1 else xs[lo] * (1 - (pos - lo)) + xs[hi] * (pos - lo)


def cv(v):
    if v is None:
        return ""
    s = str(v).translate(SUP)
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("\u00a0", " "), ("\u2007", " "), ("\u202f", " "), ("\ufeff", ""), ("\u2212", "-"),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u2010", "-")):
        s = s.replace(a, b)
    return re.sub(r"[ \t]+", " ", s).strip()


def nks(s):
    return re.sub(r"\s+", " ", cv(s).casefold()).strip(" .;,")


def nkl(s):
    return re.sub(r"^0+(?=\d)", "", re.sub(r"[\s_\-/\\.]+", "", nks(s)))


# ------------------------------------------------------------------ rules units
def load_rules():
    try:
        r = json.loads((REF / "cleaning_rules.json").read_text(encoding="utf-8"))
    except Exception as e:
        r = {"date_formats": ["%Y-%m-%d"], "missing_tokens": {"missing_blank": ["", "-", "na"]}}
        add("degradations", "RULES_FALLBACK", "builtin rules used: %s" % e)
    mt = r.get("missing_tokens") or {}
    for a, b in (("miss", "missing_blank"), ("nd", "not_detected"), ("loq", "below_loq"),
                 ("sent", "sentinel"), ("zero", "explicit_zero_keep")):
        G["t_" + a] = {str(x).strip().casefold() for x in (mt.get(b) or [])}
    G["t_miss"].add("")
    flat = {}
    for dim, sp in (r.get("units") or {}).items():
        for k, f in (sp.get("factors") or {}).items():
            flat[usig(k)] = (dim, f, sp.get("canonical"), 0)
        for k, ab in (sp.get("affine") or {}).items():
            flat[usig(k)] = (dim, tuple(ab), sp.get("canonical"), 1)
    G["r"], G["flat"] = r, flat
    rp = r.get("role_patterns") or {}
    G["kr"] = re.compile(rp.get("key") or r"(^|[^a-z])(id|no|code|sample|subject|site)([^a-z]|$)", re.I)
    G["tr"] = re.compile(rp.get("time") or r"(date|time|day|week|month|year)", re.I)
    return r


def usig(t):
    t = unicodedata.normalize("NFKC", cv(t)).casefold()
    t = t.replace("\u03bc", "u").replace("\u00b5", "u").replace("\u00b7", "").replace("\u2022", "")
    t = re.sub(r"\s+", "", t.replace("*", "").replace("^", ""))
    t = re.sub(r"^(~|\u2248|ca\.|about|approx\.?)", "", t.replace("per", "/").replace(".", ""))
    t = re.sub(r"^1/", "", t)
    if t.endswith("-1"):
        b = t[:-2].lstrip("/")
        if b in G["flat"]:
            return "/" + b
        for c in range(len(b) - 1, 0, -1):
            if b[:c] in G["flat"] and b[c:] in G["flat"]:
                return b[:c] + "/" + b[c:]
    return t


def ui(tok):
    s = usig(tok)
    if s in G["flat"]:
        d, f, c, a = G["flat"][s]
        return {"sig": s, "dim": d, "fac": f, "canon": c, "affine": a}
    return None


def pnum(s):
    """token -> (value|None, fault codes, meta{unit}); records each rewrite."""
    t, fl, meta = s.strip(), [], {}
    if not t:
        return None, fl, meta
    if re.search(r"\d\s*[xX\u00d7*]\s*10", t):
        t = re.sub(r"\s*[xX\u00d7*]\s*10\s*\^?\s*(-?)\s*(\d+)",
                   lambda m: "e" + ("-" if m.group(1) == "-" else "+") + m.group(2), t)
        fl.append("F1_sci_notation")
    if re.search(r"\d", t) and re.search(r"[*\u2020\u2021\u00a7#]$", t):
        t, fl = re.sub(r"[*\u2020\u2021\u00a7#]+$", "", t), fl + ["F1_footnote_marker"]
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t, fl = t[1:-1], fl + ["F1_parenthesis_negative"]
    t = t.lstrip("+")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t, fl = t.replace(".", "").replace(",", "."), fl + ["F1_decimal_comma"]
        else:
            t, fl = t.replace(",", ""), fl + ["F1_thousands_sep"]
    elif "," in t:
        p = t.split(",")
        if len(p) == 2 and p[0].isdigit() and 0 < len(p[1]) <= 2:
            t, fl = p[0] + "." + p[1], fl + ["F1_decimal_comma"]
        elif len(p) == 2 and len(p[1]) == 3:
            t, fl = p[0] + p[1], fl + ["F1_thousands_sep_ambiguous"]
        else:
            t, fl = "".join(p), fl + ["F1_thousands_sep"]
    elif t.count(".") > 1:
        t, fl = t.replace(".", "", t.count(".") - 1), fl + ["F1_multi_dot"]
    if t.endswith("%"):
        t, meta["unit"], fl = t[:-1], "%", fl + ["F1_percent_suffix"]
    u = re.search(r"(?<=[\d\)])\s*([A-Za-z\u00b5\u03bc][A-Za-z0-9\u00b5\u03bc/.^\-]{0,11})$", t)
    if u and not re.search(r"[eE][+-]?\d+$", t):
        meta["unit"], t, fl = u.group(1), t[:u.start()].strip(), fl + ["F1_trailing_unit"]
    t = t.strip()
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?([eE][+-]?\d+)?", t.strip()):
        return None, fl, meta
    return (-float(t) if neg else float(t)), fl, meta


def pdate(s):
    t = s.strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", t):
        try:
            n = float(t)
            if 20000 <= n <= 80000:
                return (datetime(1899, 12, 30) + timedelta(days=n)).strftime("%Y-%m-%d"), "excel_serial"
        except Exception:
            return None, None
        return None, None
    if not re.search(r"\d{1,4}[/.\-]\d{1,2}", t):
        return None, None
    for f in G["r"].get("date_formats") or []:
        try:
            d = datetime.strptime(t, f)
            return d.strftime("%Y-%m-%dT%H:%M:%S" if ("%H" in f or "%M" in f) else "%Y-%m-%d"), f
        except Exception:
            pass
    return None, None


def nv(raw, pol):
    """One cell -> {raw,out,v,kind,faults,...}; pure function of (raw,policy)."""
    r = cv(raw)
    o = {"raw": r, "out": r, "v": None, "kind": "value", "faults": [], "censor": None,
         "unit": None, "factor": None, "note": None}
    low, prec = r.casefold(), pol.get("prec")
    if low in G["t_zero"]:
        return dict(o, v=0.0, out=fn(0.0, prec))
    for k, code in (("miss", "M1_missing_blank"), ("nd", "M2_not_detected"), ("loq", "M3_below_loq")):
        if low in G["t_" + k]:
            return dict(o, kind="missing", censor=code[3:], out="", faults=[code])
    if low in G["t_sent"]:
        try:
            sv = float(low)
        except Exception:
            sv = None
        lo, hi = pol.get("min"), pol.get("max")
        if sv is not None and (lo is None or sv >= lo) and (hi is None or sv <= hi):
            return dict(o, v=sv, out=fn(sv, prec), faults=["R1_range_violation"])
        return dict(o, kind="missing", censor="sentinel_code", out="", faults=["M4_sentinel"])
    if low[:1] in ("<", "\u2264", ">"):
        v, fl, _ = pnum(r[1:])
        if v is None:
            return dict(o, kind="text", faults=fl + ["T1_type_conflict"])
        return dict(o, kind="censored", v=v, out=fn(v, prec), faults=fl + [
            "R1_range_violation" if low[0] == ">" else "M3_below_loq"],
            censor="above_range" if low[0] == ">" else "below_loq")
    if pol.get("role") == "time":
        d, pat = pdate(r)
        if d:
            return dict(o, out=d, note=pat, faults=[] if pat == "%Y-%m-%d" else ["F2_date_format"])
        return o
    v, fl, meta = pnum(r)
    if v is None:
        return dict(o, kind="text", faults=fl + ["T1_type_conflict"]) if r and pol.get("is_num") else dict(o, faults=fl)
    faults = fl + (["F1_numeric_format"] if fl else [])
    if pol.get("role") in ("key", "text", "cat") and not pol.get("is_num"):
        return dict(o, v=v, faults=faults)
    if meta.get("unit"):
        info, ti = ui(meta["unit"]), ui(pol.get("unit") or "")
        if not info:
            add("unc", "U2_unit_ambiguous", "unit %r not in the unit table; value kept as reported" % meta["unit"],
                column=pol.get("name"))
            return dict(o, v=v, out=fn(v, prec), faults=faults + ["U2_unit_ambiguous"])
        v2 = v * info["fac"][0] + info["fac"][1] if info["affine"] else v * info["fac"]
        if ti and ti["dim"] == info["dim"]:
            v2 = (v2 - ti["fac"][1]) / ti["fac"][0] if ti["affine"] else v2 / ti["fac"]
        faults.append("U1_unit_inconsistent" if abs(v2 - v) > 1e-12 * max(1.0, abs(v)) else "U1_unit_alias")
        return dict(o, v=v2, out=fn(v2, prec), unit=meta["unit"], factor=info["fac"], dim=info["dim"], faults=faults)
    return dict(o, v=v, out=fn(v, prec), faults=faults)


# ------------------------------------------------------------------- io bridge
sys.path.insert(0, str(HERE))
try:
    import verify as IO
except Exception as _e:
    IO = None
    add("degradations", "IO_MODULE", "verify.py unavailable (%s); CSV-only fallback reader" % _e)


def read_table(p):
    """Delegate to verify.rany; standalone fallback reads plain UTF-8 CSV only."""
    if IO:
        return IO.rany(p)
    e = Path(p).suffix.lower()
    rows = [r for r in csv.reader(Path(p).read_text(encoding="utf-8", errors="replace").splitlines())
            if any(c.strip() for c in r)] if e in (".csv", ".tsv") else []
    if len(rows) < 2:
        return None
    w = len(rows[0])
    return {"name": Path(p).stem, "path": str(p), "header": rows[0], "loc": "line", "enc": "utf-8",
            "rows": [(i + 2, (r + [""] * w)[:w]) for i, r in enumerate(rows[1:])]}


# --------------------------------------------------------------------- pipeline
def policy(col, rows, i, dct, canon):
    sp = IO.dspec(col, dct) if IO else {"name": col, "unit": None, "dim": None, "min": None, "max": None,
                                        "prec": None, "role": None, "is_num": False, "desc": "",
                                        "declared": False, "type": None}
    nn = [cv(r[i]) for _, r in rows if cv(r[i])][:400]
    rate = (sum(1 for v in nn if pnum(v)[0] is not None) / float(len(nn))) if nn else 0.0
    uniq = len({nks(v) for v in nn}) / float(len(nn)) if nn else 0.0
    role = sp["role"] or ("time" if G["tr"].search(col) and rate < 0.9 else
                          "key" if G["kr"].search(col) and uniq >= 0.8 else
                          "measure" if rate >= 0.6 or str(sp["type"] or "").lower()[:4] in
                          ("floa", "int", "numb", "doub", "deci", "real") else
                          "cat" if nn and uniq <= 0.25 else "text")
    sp["role"], sp["is_num"] = role, role == "measure"
    u = ui(sp["unit"]) if sp["unit"] else None
    if u:
        sp["dim"] = u["dim"]
        if canon.get(u["dim"]):
            sp["unit"] = canon[u["dim"]]
    return sp


def clean(tab, dct, canon):
    hdr, rows = tab["header"], tab["rows"]
    pols = [policy(c, rows, i, dct, canon) for i, c in enumerate(hdr)]
    base, out = Path(tab["path"]).name, []
    for i, (ln, row) in enumerate(rows):
        rec = {"rid": "R%05d" % (i + 1), "src": "%s:%s" % (base, ln), "c": {}, "f": []}
        for j, p in enumerate(pols):
            o = nv(row[j], p)
            rec["c"][hdr[j]] = o
            if o["faults"]:
                rec["f"].extend(hdr[j] + ":" + x for x in o["faults"])
        out.append(rec)
    return pols, out


def dedup(recs, keys):
    keep, dup, seen = [], [], {}
    for r in recs:
        k = tuple(nks(r["c"][c]["out"]) for c in keys)
        if k not in seen:
            seen[k] = r
            keep.append(r)
            continue
        a = seen[k]
        cf = lambda x: sum(1 for o in x["c"].values() if o["out"] != "")
        w, l = (r, a) if cf(r) > cf(a) else (a, r)
        dup.append((l, w, k))
        if w is r:
            keep[keep.index(a)] = r
            seen[k] = r
    return keep, dup


def near(recs, keys):
    g = {}
    for r in recs:
        g.setdefault(tuple(nkl(r["c"][c]["out"]) for c in keys), set()).add(
            tuple(nks(r["c"][c]["out"]) for c in keys))
    return [(k, len(v)) for k, v in g.items() if len(v) > 1][:40]


def outl(kept, pols):
    res = {}
    for p in pols:
        if not p["is_num"]:
            continue
        col = p["name"]
        xs = [(r["rid"], r["c"][col]["v"]) for r in kept if r["c"][col]["v"] is not None]
        if not xs:
            continue
        lo_, hi_ = p["min"], p["max"]
        hard = [x for x in xs if (lo_ is not None and x[1] < lo_) or (hi_ is not None and x[1] > hi_)]
        vals, st = [v for _, v in xs], []
        if len(vals) >= 8:
            m = med(vals)
            s = 1.4826 * med([abs(v - m) for v in vals])
            q1, q3 = quant(vals, .25), quant(vals, .75)
            st = ([(i, v) for i, v in xs if abs(v - m) / s > 3.5] if s > 0 else
                  [(i, v) for i, v in xs if v < q1 - 1.5 * (q3 - q1) or v > q3 + 1.5 * (q3 - q1)]
                  if q3 > q1 else [])
        res[col] = {"n_used": len(vals), "hard": hard, "stat": st}
    return res

# ------------------------------------------------------------------ orchestrate
def run(indir, outdir, case, cf, limit):
    tabs, docs = IO.scan(indir, outdir) if IO else ([], [])
    for p in tabs + docs:
        S["sources"].append({"id": "S%d" % (len(S["sources"]) + 1), "file": str(p), "sha256": hfile(p)})
    dct = IO.load_dict([p for p in docs if p.suffix.lower() in DOC], case) if IO else {}
    tables = [t for t in (read_table(p) for p in tabs) if t and t["rows"]]
    txt = "\n".join([json.dumps(case, ensure_ascii=False)]) if case else ""
    tab = IO.primary(tables, txt) if IO else (max(tables, key=lambda t: len(t["rows"])) if tables else None)
    Q = {"n_tables": len(tables), "dictionary_columns": len(dct), "rows": {"in": 0, "out": 0}, "status": "partial"}
    if not tab:
        Q["status"] = "input_error" if not case else "insufficient_evidence"
        add("pending", "NO_TABLE", "no readable table in %s" % indir)
        return Q
    canon = IO.canon_units(case, indir) if IO else {}
    Q["canonical_units"] = canon
    if len(tab["rows"]) > limit:
        add("degradations", "ROW_LIMIT", "rows truncated at %d" % limit)
        tab["rows"] = tab["rows"][:limit]
    pols, recs = clean(tab, dct, canon)
    keyed = [p["name"] for p in pols if p["role"] == "key"]
    keys = keyed or [p["name"] for p in pols]
    if not keyed:
        add("pending", "KEY_NOT_FOUND", "no primary key declared or inferable: dedup fell back to full-row identity")
    kept, dup = dedup(recs, keys)
    nearg = near(kept, keys) if len(keys) > 1 else []
    ol = outl(kept, pols)
    R = {r["rid"]: r for r in kept}
    for c, d in ol.items():
        for rid in [x[0] for x in d["hard"]]:
            R[rid]["f"].append(c + ":R1_range_violation")
        for rid in [x[0] for x in d["stat"]]:
            R[rid]["f"].append(c + ":R2_distribution_outlier")
    Q.update({"primary": {"file": Path(tab["path"]).name, "rows": len(recs), "cols": len(tab["header"]),
                          "locator": tab["loc"], "encoding": tab.get("enc")},
              "rows": {"in": len(recs), "out": len(kept), "duplicates_removed": len(dup),
                       "near_duplicate_groups": len(nearg)},
              "key_fields": keys[:8], "units": {p["name"]: p["unit"] for p in pols if p["unit"]},
              "roles": {p["name"]: p["role"] for p in pols},
              "preview": [{c: r["c"][c]["out"] for c in tab["header"]} for r in kept[:5]],
              "missing_cells": sum(1 for r in kept for o in r["c"].values() if o["kind"] == "missing"),
              "outliers": {c: [len(v["hard"]), len(v["stat"])] for c, v in ol.items() if v["hard"] or v["stat"]}})
    if IO:
        try:
            Q["stats"] = IO.stats(kept, pols)
            Q["emitted"] = IO.emit(outdir, tab, pols, kept, dup, nearg, ol, Q["stats"])
            IO.report(outdir, Q, S)
            Q["checks"] = IO.checks(outdir)
        except Exception as e:
            add("errors", "EMIT", "artifact or report step failed: %s" % e)
    return Q


def _partial(outdir, cid, contract):
    r = {"case_id": cid, "status": "partial", "skill": "sci-data-cleaning@" + V,
         "note": "placeholder written before processing; overwritten by the final run",
         "sources": [], "uncertainty": [], "pending_human": [], "errors": [], "runtime": {"version": V}}
    for k in (contract or {}):
        r.setdefault(k, None)
    try:
        wjson(Path(outdir) / "result.json", r)
    except Exception:
        pass


def _mkdirs(p):
    for c in (Path(p), Path.cwd() / "output", Path(__import__("tempfile").gettempdir()) / "sciclean"):
        try:
            c.mkdir(parents=True, exist_ok=True)
            (c / ".wt").write_text("x")
            (c / ".wt").unlink()
            return c
        except Exception:
            pass
    return Path(".")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Clean a scientific table against a data dictionary and workorder.",
                                 epilog="writes result.json, cleaned.csv, field_issues.csv, transform_log.csv, "
                                        "duplicates.csv, stats.json, quality_report.json/.md, assertions.json, run.log")
    ap.add_argument("--input", default="/input" if Path("/input").is_dir() else "input", help="case dir")
    ap.add_argument("--output", default="/app/output", help="output dir")
    ap.add_argument("--case", default=None, help="explicit case.json path")
    ap.add_argument("--rows", type=int, default=200000, help="row cap")
    ap.add_argument("--version", action="version", version="sci-data-cleaning " + V)
    a, _ = ap.parse_known_args(argv)
    t0 = time.time()
    outdir = _mkdirs(a.output)
    try:
        load_rules()
    except Exception:
        add("errors", "RULES", "rule table load failed: %s" % traceback.format_exc(limit=1))
    case, cf, cid, contract = IO.case_meta(Path(a.input), a.case, add) if IO else ({}, None, "", {})
    _partial(outdir, cid, contract)
    Q = {"status": "partial", "rows": {"in": 0, "out": 0}}
    try:
        Q = run(Path(a.input), outdir, case, cf, a.rows)
    except Exception:
        add("errors", "PIPELINE", "pipeline aborted: %s" % traceback.format_exc(limit=4).replace("\n", " | "))
    try:
        if IO:
            IO.finalize(outdir, cid, contract, Q, t0, cf, S, V)
        else:
            _partial(outdir, cid, contract)
    except Exception:
        add("errors", "FINALIZE", "result assembly failed: %s" % traceback.format_exc(limit=3).replace("\n", " | "))
        _partial(outdir, cid, contract)
    return 0


if __name__ == "__main__":
    sys.exit(main())
