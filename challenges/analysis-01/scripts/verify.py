#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I/O adapters, artifact emitters and audit for sci-data-cleaning (stdlib only)."""
import csv, hashlib, html, json, math, re, sys, time, unicodedata, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"
_R, NOTES = {}, []
FI_HDR = ["column", "role", "in_dictionary", "canonical_unit", "n_rows", "n_missing", "missing_pct",
          "missing_reasons", "n_invalid_text", "n_out_of_range", "n_dist_outlier"]


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


def rows_of(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))



def fn(x, prec=None):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return ""
    if prec is not None:
        return ("%." + str(int(prec)) + "f") % float(x)
    return "0" if "%.12g" % float(x) in ("-0", "-0.0") else "%.12g" % float(x)


def rules():
    if not _R:
        try:
            _R.update(json.loads((REF / "cleaning_rules.json").read_text(encoding="utf-8")))
        except Exception:
            _R.update({})
    return _R


def _sig(t):
    t = re.sub(r"[\s.\u00b7]", "", str(t).casefold().replace("\u03bc", "u").replace("\u00b5", "u"))
    return re.sub(r"^1/", "", t)


def unitdim(tok):
    if "_flat" not in _R:
        fl = {}
        for dim, sp in (rules().get("units") or {}).items():
            for k in list(sp.get("factors") or {}) + list(sp.get("affine") or {}):
                fl[_sig(k)] = dim
        _R["_flat"] = fl
    s = _sig(tok)
    return _R["_flat"].get(s) or (_R["_flat"].get(s[1:-2]) if s.endswith("-1") else None)


def cv(v):
    s = unicodedata.normalize("NFKC", "" if v is None else str(v))
    for a, b in (("\u00a0", " "), ("\u2007", " "), ("\u202f", " "), ("\ufeff", ""), ("\u2212", "-"),
                 ("\u2013", "-"), ("\u2014", "-")):
        s = s.replace(a, b)
    return re.sub(r"[ \t]+", " ", s).strip()


def dec(b):
    """decode bytes; repair GBK-read-as-latin-1 mojibake when it lowers the Latin-1 share"""
    def lat(s):
        return (sum(1 for c in s if "\u00c0" <= c <= "\u00ff") / float(len(s))) if s else 0.0
    for e in ("utf-8-sig", "utf-8"):
        try:
            return b.decode(e), e, None
        except Exception:
            pass
    best = None
    for e in ("gb18030", "latin-1"):
        try:
            t = b.decode(e)
        except Exception:
            continue
        if best is None or lat(t) < best[0]:
            best = (lat(t), t, e)
    sc, t, e = best or (0, b.decode("latin-1", "replace"), "latin-1")
    if sc > 0.03:
        try:
            t2 = t.encode("latin-1", "ignore").decode("gb18030")
            if lat(t2) < sc:
                return t2, "gb18030(repaired)", "mojibake repaired (latin-1 view re-decoded as GB18030)"
        except Exception:
            pass
    return t, e, None


def rcsv(p, note=None):
    t, enc, n2 = dec(Path(p).read_bytes())
    if n2 and note:
        note("F3_encoding", "%s: %s (encoding=%s)" % (Path(p).name, n2, enc), file=str(p))
    head = "\n".join(t.splitlines()[:5])
    dl = max([",", ";", "\t", "|"], key=lambda d: head.count(d))

    hdr, rows = None, []
    try:
        rd = csv.reader(t.splitlines(True), delimiter=dl)
        for rec in rd:
            if not any(c.strip() for c in rec):
                continue
            if hdr is None:
                hdr = [cv(c) for c in rec]
                continue
            rows.append((rd.line_num, [cv(c) for c in rec]))
    except Exception as e:
        if note:
            note("CSV_PARSE", "csv stopped: %s" % e, file=str(p))
    if not hdr:
        return None
    w = len(hdr)
    return {"name": Path(p).stem, "path": str(p), "header": hdr, "loc": "line", "enc": enc,
            "rows": [(n, (r + [""] * w)[:w]) for n, r in rows]}



def rtext(p, note=None):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def rany(p, note=None):
    if Path(p).suffix.lower() in (".csv", ".tsv", ".txt", ".dat"):
        return rcsv(p, note)
    NOTES.append({"code": "UNSUPPORTED_FORMAT", "file": str(p), "message": "%s: convert to CSV"
                  % Path(p).name})
    return None


def get(o, *names):
    flat = {}
    for d in [o] + [x for x in (o.values() if isinstance(o, dict) else []) if isinstance(x, dict)]:
        for k, x in d.items():
            flat.setdefault(re.sub(r"[^a-z0-9]", "", str(k).casefold()), x)
    for n in names:
        x = flat.get(re.sub(r"[^a-z0-9]", "", n.casefold()))
        if x not in (None, "", [], {}):
            return x
    return None


HK = ("name", "field", "column", "variable", "\u5b57\u6bb5", "\u53d8\u91cf", "\u5217\u540d")


def dtext(t):
    out, hdr = {}, None
    for line in t.splitlines():
        if line.count("|") >= 2:
            c = [cv(x) for x in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", x) or not x for x in c):
                continue
            if c[0].casefold() in HK:
                hdr = c
            elif hdr and len(c) == len(hdr):
                out[c[0].casefold()] = dict(zip(hdr, c))
    return out


def normrec(o):
    if isinstance(o, dict):
        return {str(k): (x if isinstance(x, dict) else {"__text__": cv(x)}) for k, x in o.items()}
    r = {}
    if isinstance(o, list):
        for x in o:
            if isinstance(x, dict):
                nm = x.get("name") or x.get("field") or x.get("column")
                if nm:
                    r[str(nm)] = {k: cv(y) for k, y in x.items()}
    return r

def load_dict(paths, case, note=None):
    d = {}
    for p in paths:
        t = rtext(p, note)
        if Path(p).suffix.lower() == ".json":
            try:
                d.update(normrec(json.loads(t)))
                continue
            except Exception:
                pass
        d.update(dtext(t))
    for k in ("data_dictionary", "dictionary", "fields", "columns", "schema"):
        if get(case, k):
            d.update(normrec(get(case, k)))
    return {str(k).casefold(): (x if isinstance(x, dict) else {"__text__": x}) for k, x in d.items()}

def dspec(col, dct):
    key = re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", col.casefold())
    rec = next((x for k, x in dct.items() if re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", k) == key), None)
    sp = {"name": col, "unit": None, "dim": None, "min": None, "max": None, "prec": None,
          "role": None, "is_num": False, "desc": "", "declared": bool(rec), "type": None}
    m = re.search(r"[\(\[]\s*([^\)\]]{1,18})\s*[\)\]]\s*$", col)
    if m and unitdim(m.group(1)):
        sp["unit"] = m.group(1)
    if not rec:
        return sp
    sp["desc"] = str(rec.get("__text__", ""))[:400]
    hk = rules().get("dict_header_keys") or {}
    for k, x in rec.items():
        f = next((f for f, ks in hk.items() if str(k).casefold() in ks), None)
        sv = str(x)
        if f == "unit":
            m = re.search(r"([A-Za-z%\u00b5\u03bc][A-Za-z0-9\u00b5\u03bc%/^.\-]{0,15})", sv)
            if m and unitdim(m.group(1)):
                sp["unit"] = m.group(1)
        elif f in ("desc", "type"):
            sp[f] = sv[:400]
        elif f == "prec":
            m = re.search(r"\d", sv)
            sp["prec"] = int(m.group(0)) if m else None
        elif f == "key" and sv.casefold() not in (
                "", "-", "--", "/", "no", "n", "false", "0", "none", "na", "null", "n/a",
                "\u5426", "\u975e", "\u65e0", "\u4e0d\u662f"):
            sp["role"] = "key"
        elif f in ("min", "max", "range"):
            mm = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*(?:-|\u2013|\u2014|to|~|\u2026)\s*"
                          r"([-+]?\d+(?:\.\d+)?)\s*$", sv.replace(",", ""))
            q = [float(y) for y in re.findall(r"[-+]?\d+(?:\.\d+)?", sv.replace(",", ""))]
            if f == "range" and mm:
                sp["min"], sp["max"] = float(mm.group(1)), float(mm.group(2))
            elif f == "range" and len(q) >= 2:
                sp["min"], sp["max"] = q[0], q[1]
            elif f != "range" and q:
                sp[f] = q[0]
    sp["dim"] = unitdim(sp["unit"]) if sp["unit"] else None
    return sp

def scan(indir, outdir):
    tabs, docs = [], []
    for p in sorted(Path(indir).rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            if outdir and Path(outdir).resolve() == p.resolve().parent:
                continue
        except Exception:
            pass
        e = p.suffix.lower()
        if e in (".csv", ".tsv", ".txt", ".dat", ".xlsx", ".xlsm", ".json") and not p.name.startswith("case"):
            tabs.append(p)
        if e in (".md", ".json", ".docx", ".yaml", ".yml", ".txt"):
            docs.append(p)
    return tabs, docs


def primary(tabs, txt):
    hit = [t for t in tabs if Path(t["path"]).name in txt] if tabs else []
    return max(hit or tabs, key=lambda t: len(t["rows"])) if tabs else None



def load_case(indir, cf):
    cs = ([Path(cf)] if cf else []) + [Path(indir) / "case.json"]
    for p in cs + sorted(Path(indir).glob("*.json")) + sorted(Path(indir).rglob("case*.json")):
        if p and Path(p).is_file():
            try:
                o = json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
                return (o if isinstance(o, dict) else {"files": o}), Path(p)
            except Exception:
                pass
    return {}, None

def case_meta(indir, cf, add):
    case, path = load_case(indir, cf)
    cid = str(get(case, "case_id", "id", "case", "uid") or "")
    c = get(case, "output_contract", "contract", "outputs", "output_schema")
    contract = {str(k): None for k in c} if isinstance(c, list) else (c if isinstance(c, dict) else {})
    if not path:
        add("errors", "CASE_MISSING", "no case.json in %s" % indir)
    return case, path, cid, contract

def canon_units(case, indir):
    t = [json.dumps(case, ensure_ascii=False) if case else ""]
    for k in ("task", "task_instruction", "instruction", "workorder", "cleaning_workorder", "organizer_workorder"):
        x = get(case, k)
        t += [x] if isinstance(x, str) else ([str(y) for y in x] if isinstance(x, list) else [])
    p = Path(indir) / "task.md"
    if p.is_file():
        t.append(p.read_text(encoding="utf-8", errors="replace"))
    txt = "\n".join(t)
    out = {}
    pat = (r"(?:\u7edf\u4e00|\u6362\u7b97|\u8f6c\u6362\u4e3a|standardis|standardiz|convert|reported in)"
           r"[^.;\n]{0,40}?([A-Za-z%\u00b5\u03bc][A-Za-z0-9\u00b5\u03bc/^.\-]{0,10})")
    for m in re.finditer(pat, txt):
        d = unitdim(m.group(1))
        if d:
            out[d] = m.group(1)
    return out


def stats(kept, pols):
    out = {}
    for p in pols:
        if not p["is_num"]:
            continue
        xs = [r["c"][p["name"]] for r in kept]
        v = sorted(x["v"] for x in xs if x["kind"] == "value" and x["v"] is not None)
        d = {"unit": p.get("unit") or p.get("dim"), "n_total": len(xs), "n_used": len(v),
             "n_missing": sum(1 for x in xs if x["kind"] == "missing"),
             "n_censored": sum(1 for x in xs if x["kind"] == "censored"),
             "n_invalid": sum(1 for x in xs if x["kind"] == "text")}
        if v:
            mu, n = sum(v) / len(v), len(v)
            d.update(mean=round(mu, 12), median=v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0,
                     min=v[0], max=v[-1])
            d["sd"] = round((sum((x - mu) ** 2 for x in v) / (n - 1)) ** .5, 12) if n > 1 else None
        out[p["name"]] = d
    return out

def emit(outdir, tab, pols, kept, dup, nearg, ol, st):
    o, hdr = Path(outdir), tab["header"]
    wcsv(o / "cleaned.csv", ["__row_id", "__src"] + hdr + ["__flags"],
         [[r["rid"], r["src"]] + [r["c"][c]["out"] for c in hdr] + ["|".join(sorted(set(r["f"])))] for r in kept])
    tl = [[r["rid"], r["src"], c, x["raw"], x["out"], "|".join(x["faults"]), x["kind"],
           ("factor=" + fn(x["factor"])) if x["factor"] else "reversible", x["note"] or ""]
          for r in kept for c in hdr for x in [r["c"][c]] if x["out"] != x["raw"] or x["faults"]]
    wcsv(o / "transform_log.csv", ["row_id", "locator", "column", "original_value", "cleaned_value",
                                   "fault_codes", "kind", "reversible"], [r[:8] for r in tl])
    fi = []
    for p in pols:
        xs = [r["c"][p["name"]] for r in kept]
        m = {}
        for x in xs:
            if x["kind"] == "missing":
                m[x["censor"]] = m.get(x["censor"], 0) + 1
        nm, of = sum(m.values()), ol.get(p["name"], {})
        fi.append([p["name"], p["role"], "yes" if p["declared"] else "no", p.get("unit") or "", len(xs), nm,
                   round(100.0 * nm / max(1, len(xs)), 2), ";".join("%s=%d" % kv for kv in sorted(m.items())),
                   sum(1 for x in xs if x["kind"] == "text"),
                   len(of.get("hard", [])), len(of.get("stat", []))])
    wcsv(o / "field_issues.csv", FI_HDR, fi)
    wcsv(o / "duplicates.csv", ["row_id", "locator", "status", "duplicate_of", "match", "key"],
         [[l["rid"], l["src"], "removed", w["rid"], "D1_duplicate_exact" if len(k) == len(hdr)
           else "D2_duplicate_key", "|".join(k)] for l, w, k in dup] +
         [["", "", "near", "", "D3_near_duplicate", "|".join(k)] for k, _n in nearg])
    wjson(o / "stats.json", {"method": {"sd": "sample n-1", "imputation": "none"}, "columns": st})
    return {"transform_log_rows": len(tl), "field_issues": len(fi)}

def resolve(contract, Q, S):
    reg = {"cleaned_table": {"path": "cleaned.csv", "rows": (Q.get("rows") or {}).get("out")},
           "cleaned_rows": Q.get("preview", []),
           "quality_report": {"md": "quality_report.md", "json": "quality_report.json"},
           "field_issues": "field_issues.csv", "stats": Q.get("stats", {}),
           "duplicates": {"key_fields": Q.get("key_fields"), "counts": Q.get("rows")},
           "missing": {"cells": Q.get("missing_cells")},
           "outliers": Q.get("outliers", {}), "unit_mapping": Q.get("units", {}),
           "conversions": {"canonical_units": Q.get("canonical_units", {}),
                           "rewritten_cells": (Q.get("emitted") or {}).get("transform_log_rows")},
           "log": "run.log", "assertions": "assertions.json", "row_counts": Q.get("rows", {}),
           "workorder_compliance": {"canonical_units": Q.get("canonical_units", {}),
                                    "note": "only unit-standardisation directives are parsed from the workorder text"},
           "data_dictionary": Q.get("roles", {}), "sources": S["sources"],
           "uncertainty": S["unc"], "pending_human": S["pending"], "errors": S["errors"],
           "degradations": S["degradations"]}
    norm = lambda s: re.sub(r"[^a-z0-9\u4e00-\u9fa5]", "", str(s).casefold())
    alias = {}
    for name, al in (rules().get("contract_synonyms") or {}).items():
        for a in [name] + list(al):
            alias.setdefault(norm(a), name)
    out, bad = {}, []
    for k in contract:
        nk = norm(k)
        hit = alias.get(nk) or next((x for kk, x in alias.items() if len(kk) > 3 and (kk in nk or nk in kk)), None)
        if hit in reg:
            out[k] = reg[hit]
        else:
            out[k] = [] if re.search(r"list|array|rows|issues|records|items", str(k).casefold()) else None
            bad.append({"field": k, "reason": "no registry match"})
    return out, bad

def report(outdir, Q, S):
    o = Path(outdir)
    fi = rows_of(o / "field_issues.csv") if (o / "field_issues.csv").exists() else []
    wjson(o / "quality_report.json", {"summary": Q, "field_issues": fi})
    R, E, P = Q.get("rows") or {}, Q.get("emitted") or {}, Q.get("primary") or {}
    v = {"FILE": P.get("file") or "n/a", "STATUS": Q.get("status"), "ROWS_IN": R.get("in"),
         "ROWS_OUT": R.get("out"), "COLS": P.get("cols"), "DICT_COLS": Q.get("dictionary_columns"),
         "TASK": (Q.get("task") or "see case.json")[:200],
         "KEY": "`, `".join(Q.get("key_fields") or []) or "none declared",
         "MISSING": Q.get("missing_cells"),
         "OUTLIERS": len(Q.get("outliers") or {}), "DUPS": R.get("duplicates_removed"),
         "NEAR": R.get("near_duplicate_groups"), "REWRITTEN": E.get("transform_log_rows")}
    v["FIELD_TABLE"] = "\n".join("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
        r["column"], r["role"], r["canonical_unit"] or "-", r["n_rows"], r["n_missing"], r["missing_pct"],
        r["missing_reasons"] or "-", r["n_dist_outlier"]) for r in fi[:30]) or "| - |"
    v["UNITS"] = "\n".join("- %s" % k for k in (Q.get("units") or {})) or "- none declared"
    v["OVERRIDES"] = "\n".join("- %s -> %s" % (d, u) for d, u in (Q.get("canonical_units") or {}).items()) \
        or "- none stated in the workorder"
    v["STATS"] = "n, mean, median, sd, min, max, q1, q3 per column with the exclusion rule: `stats.json`."
    v["PENDING"] = "\n".join("- **%s** %s" % (x.get("code"), x.get("message")) for x in S["pending"]) or "- none"
    tpl = (REF / "quality_report_template.md").read_text(encoding="utf-8")
    for k, val in v.items():
        tpl = tpl.replace("{{%s}}" % k, str(val))
    (o / "quality_report.md").write_text(tpl, encoding="utf-8")

def checks(outdir):
    o, A = Path(outdir), []

    def ck(c, ok, d):
        A.append({"check": c, "pass": bool(ok), "detail": d})
    try:
        cl, tl, fi = rows_of(o / "cleaned.csv"), rows_of(o / "transform_log.csv"), rows_of(o / "field_issues.csv")
        Q = json.loads((o / "quality_report.json").read_text(encoding="utf-8")).get("summary", {})
        ck("A1_row_count", len(cl) == ((Q.get("rows") or {}).get("out") or 0),
           "table %d vs report %s" % (len(cl), (Q.get("rows") or {}).get("out")))
        ck("A2_missing_total", sum(int(r["n_missing"] or 0) for r in fi) == int(Q.get("missing_cells") or 0),
           "issue sum vs report")
        ix = {x.get("__row_id"): x for x in cl}
        bad = [t for t in tl
               if (ix.get(t.get("row_id"), {}).get(t.get("column")) or "") != (t.get("cleaned_value") or "")]
        ck("A3_log_matches_table", not bad, "log rows disagreeing with table: %d" % len(bad))
    except Exception as e:
        ck("A0_artifacts", False, str(e)[:90])
    res = {"checks": A, "passed": sum(1 for a in A if a["pass"]), "total": len(A)}
    res["failed"] = [a["check"] for a in A if not a["pass"]]
    wjson(o / "assertions.json", res)
    return {"passed": res["passed"], "total": res["total"], "failed": res["failed"]}

def finalize(outdir, cid, contract, Q, t0, cf, S, V):
    o = Path(outdir)
    S["degradations"] += NOTES
    del NOTES[:]
    filled, bad = resolve(contract, Q, S)
    st = Q.get("status") or "partial"
    if st == "partial" and (Q.get("rows") or {}).get("out") and not (S["errors"] or bad):
        st = "ok"
    Q["status"], Q["needs_human_review"] = st, bool(S["pending"])
    log = ["%s %s rows_in=%s rows_out=%s" % (V, st, (Q.get("rows") or {}).get("in"),
                                               (Q.get("rows") or {}).get("out"))]
    log += ["%-11s %s %s" % (k.upper(), d.get("code"), d.get("message"))
            for k in ("errors", "degradations", "pending", "unc") for d in S[k]]
    (o / "run.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    arts = [{"path": str(p.relative_to(o)), "bytes": p.stat().st_size,
             "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:40]} for p in sorted(o.rglob("*"))
            if p.is_file() and p.name != "result.json"]
    res = {"case_id": cid, "status": st, "summary": Q,
           "sources": S["sources"], "uncertainty": S["unc"], "pending_human": S["pending"],
           "errors": S["errors"], "degradations": S["degradations"], "changes": S["changes"],
           "artifacts": arts, "unresolved_contract_fields": bad,
           "runtime": {"skill_version": V, "python": sys.version.split()[0],
                       "seconds": round(time.time() - t0, 3), "case_file": str(cf) if cf else None}}
    res.update({k: x for k, x in filled.items() if k not in res})
    wjson(o / "result.json", res)
    return res

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="verify.py", description="Re-derive report numbers from the tables.")
    ap.add_argument("--output", default="/app/output", help="run artifacts dir")
    a, _ = ap.parse_known_args(argv)
    print(json.dumps(checks(Path(a.output)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
