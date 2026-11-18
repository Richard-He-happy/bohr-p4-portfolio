#!/usr/bin/env python3
"""run_skill.py - data-analysis-runner (Python standard library only).

Reads /input, writes /app/output: result.json with every output_contract field
filled, cleaned.csv, stats.json, quality_report.json, analysis.md, figures/*.svg,
queries.sql, query_results.json, solution.py (if a code template exists), run.log
and re-runnable copies of the code. Exit code is always 0; failures are recorded
in result.json under errors / degradations / pending_human.
"""
import argparse
import ast
import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis_core as C  # noqa: E402

DATA = {".csv", ".tsv", ".psv", ".tab", ".txt", ".xlsx", ".xlsm", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
CODE_RE = re.compile(r"(code_template|template|task|starter|solution).*\.py$", re.I)
DICT_RE = re.compile(r"(dict|schema|codebook|variable|字段|变量|说明|readme|metadata)", re.I)
SPEC_RE = re.compile(r"(chart_spec|figure_spec|plot_spec|viz_spec).*\.json$", re.I)


def rules_load():
    try:
        return json.loads((HERE.parent / "references" / "rules.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def jsonable(v):
    if isinstance(v, float):
        return None if not math.isfinite(v) else round(v, 6)
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x) for x in (sorted(v) if isinstance(v, set) else v)]
    return v if isinstance(v, (str, int, bool)) or v is None else str(v)


class Log:
    def __init__(self):
        self.l = []

    def __call__(self, m):
        self.l.append("%s %s" % (time.strftime("%H:%M:%S", time.gmtime()), m))

    def text(self):
        return "\n".join(self.l) + "\n"


def wjson(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(jsonable(o), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wcsv(p, header, rows):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else (C.fmt(v, 6) if isinstance(v, float) else v) for v in r])


def rel(p, base):
    try:
        return str(Path(p).resolve().relative_to(Path(base).resolve()))
    except Exception:
        return str(p)


def discover(inp):
    fs = [p for p in sorted(inp.rglob("*")) if p.is_file() and p.name != ".DS_Store"]
    cp = next((p for p in fs if p.name.lower() == "case.json"), None) or \
        next((p for p in fs if re.match(r"case.*\.json$", p.name, re.I)), None)
    case, cerr = {}, None
    if cp:
        try:
            case = json.loads(cp.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            cerr = {"file": str(cp), "stage": "read_case", "type": type(e).__name__, "message": str(e)[:300]}
    tp = next((p for p in fs if p.name.lower() == "task.md"), None)
    task = tp.read_text(encoding="utf-8", errors="replace") if tp else ""
    pool = [p for p in fs if "submission" not in p.parts and p != cp and p.suffix != ".pyc"]
    code = [p for p in pool if p.suffix.lower() == ".py" and CODE_RE.search(p.name)]
    dics = [p for p in pool if p not in code and (DICT_RE.search(p.name) or p.suffix == ".sql")]
    spec = [p for p in pool if SPEC_RE.search(p.name)]
    data = [p for p in pool if p.suffix.lower() in DATA and p not in dics + spec]
    if not task:
        task = next((case[k] for k in ("task", "task_instruction", "instruction", "question", "objective")
                     if isinstance(case.get(k), str) and case[k].strip()), "")
    return {"files": fs, "case_path": cp, "case": case if isinstance(case, dict) else {}, "case_error": cerr,
            "task": task, "data": data, "dics": dics, "specs": spec, "code": code}


def find_contract(case):
    for k in ("output_contract", "outputContract", "output_format", "expected_output", "output_fields"):
        if isinstance(case.get(k), (dict, list)) and case[k]:
            return case[k], "/" + k
    for k, v in case.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (dict, list)) and v2 and re.search(r"contract|输出|字段", str(k2), re.I):
                    return v2, "/%s/%s" % (k, k2)
    return {}, None


def fields_of(contract):
    out = []
    items = contract if isinstance(contract, list) else \
        ((contract.get(k) for k in ("fields", "required", "properties", "items") if isinstance(contract.get(k), list))
        and next(contract.get(k) for k in ("fields", "required", "properties", "items") if isinstance(contract.get(k), list))
        or contract.items())
    if isinstance(contract, dict) and not any(k in contract for k in ("type", "description", "desc")):
        for k in ("fields", "required", "properties", "items"):
            if isinstance(contract.get(k), list) and contract[k]:
                return fields_of(contract[k])
    for it in (items if isinstance(contract, list) else []):
        if isinstance(it, str):
            out.append((it, None))
        elif isinstance(it, dict):
            n = it.get("name") or it.get("field") or it.get("key")
            out.extend([(str(n), it)] if n else [(str(k), None) for k in it])
    if isinstance(contract, dict):
        out = [(str(k), v if isinstance(v, dict) else ({"type": v} if isinstance(v, str) else None))
               for k, v in contract.items()]
    return out


def skeleton(fs):
    return {n: ([] if str((s or {}).get("type", "")).lower() in ("array", "list", "table", "figure") else None)
            for n, s in fs}


def fill(fs, ctx, R):
    out = {}
    for n, spec in fs:
        low = n.lower()
        key = next((e["as"] for e in R.get("contract_map", []) if any(p in low for p in e.get("patterns", []))), None)
        v = ctx.get(key) if key else None
        t = str((spec or {}).get("type", "")).lower() if isinstance(spec, dict) else ""
        if v is None:
            v = [] if t in ("array", "list", "table", "figure") else None
        elif t in ("string", "text", "str", "markdown") and not isinstance(v, str):
            v = "\n".join("- %s" % x for x in v) if isinstance(v, list) else json.dumps(jsonable(v), ensure_ascii=False)
        elif t in ("array", "list") and not isinstance(v, list):
            v = [v]
        elif t in ("file", "path") and isinstance(v, dict):
            v = v.get("path")
        out[n] = jsonable(v)
    return out


def case_id(case, path):
    for k in ("case_id", "id", "caseId", "case_name", "name"):
        if isinstance(case.get(k), (str, int)) and str(case[k]).strip():
            return str(case[k])
    return Path(path).stem if path else "unknown-case"


def read_dictionary(fs, log):
    dic = {}
    A = {"name": ("field", "column", "variable", "name", "字段", "变量", "列名"),
         "desc": ("description", "desc", "meaning", "说明", "含义", "描述"),
         "unit": ("unit", "units", "单位", "量纲"), "type": ("type", "dtype", "类型"),
         "allowed": ("allowed", "values", "range", "取值", "范围", "编码"), "pk": ("primary", "key", "主键")}
    for f in fs:
        try:
            txt, _ = C.read_text(f)
        except Exception:
            continue
        if f.suffix.lower() == ".json":
            try:
                o = json.loads(txt)
            except Exception:
                continue
            c = o.get("columns") or o.get("fields") or o.get("variables") or o
            if isinstance(c, list):
                c = {(x.get("name") or x.get("field") or ""): x for x in c if isinstance(x, dict)}
            if isinstance(c, dict):
                for k, v in c.items():
                    if k and isinstance(v, dict):
                        dic.setdefault(C.norm(k), {}).update(
                            {x: v[x] for x in ("unit", "type", "description", "desc", "allowed", "range") if x in v})
            continue
        lines = txt.splitlines()
        hi = next((i for i, ln in enumerate(lines) if ln.strip().startswith("|") and ln.count("|") > 2), None)
        if hi is None:
            continue
        mp = {}
        for i, h in enumerate([x.strip().lower() for x in lines[hi].strip().strip("|").split("|")]):
            for k, ps in A.items():
                if k not in mp and any(p in h for p in ps):
                    mp[k] = i
        ni = mp.get("name", 0)
        for ln in lines[hi + 1:]:
            if not ln.strip().startswith("|"):
                continue
            cs = [x.strip().strip("`*") for x in ln.strip().strip("|").split("|")]
            if len(cs) > ni and cs[ni] and not set(cs[ni]) <= set("-: "):
                rec = {k: cs[i] for k, i in mp.items() if k != "name" and i < len(cs) and cs[i]}
                if rec:
                    dic.setdefault(C.norm(cs[ni]), {}).update(rec)
    log("dictionary: %d fields / %d file(s)" % (len(dic), len(fs)))
    return dic


def read_tables(fs, log):
    tabs, errs, meta = [], [], {"csv": [], "sqlite": [], "xlsx": []}
    for f in fs:
        e = f.suffix.lower()
        try:
            if e in (".csv", ".tsv", ".psv", ".tab", ".txt"):
                if b"\x00" in f.read_bytes()[:8192]:
                    raise ValueError("binary/utf-16 content, not parsed as text")
                t, info = C.parse_csv(f)
                if e == ".txt" and len(t.cols) < 2:
                    continue
                tabs.append(t)
                meta["csv"].append(dict(info, path=str(f), rows=len(t.rows), cols=len(t.cols)))
            elif e in (".xlsx", ".xlsm"):
                tabs.extend(C.parse_xlsx(f))
                meta["xlsx"].append({"path": str(f)})
            elif e in (".json", ".jsonl"):
                d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                rec = d if isinstance(d, list) else next((d[k] for k in ("data", "rows", "records", "items")
                                                          if isinstance(d.get(k), list)), None)
                if rec and isinstance(rec[0], dict):
                    ks = list(rec[0])
                    tabs.append(C.build_table([ks] + [[r.get(k, "") for k in ks] for r in rec], f.stem, f,
                                              list(range(1, len(rec) + 2)), enc="json"))
            elif e in (".db", ".sqlite", ".sqlite3"):
                ts, m = C.parse_sqlite(f)
                tabs.extend(ts)
                meta["sqlite"].append(m)
        except Exception as exc:
            errs.append({"file": str(f), "stage": "parse", "type": type(exc).__name__, "message": str(exc)[:300]})
            log("parse failed %s: %s" % (f.name, exc))
    return tabs, errs, meta


def analyse(recs, cols, kinds, R):
    num = [c for c in cols if kinds[c] == "numeric"]
    cat = [c for c in cols if kinds[c] == "categorical" and 1 < len({r.get(c) for r in recs}) <= 12]
    desc = {c: C.describe([r[c] for r in recs if isinstance(r.get(c), float)], c) for c in num}
    lim, pairs = num[:12], []
    for i, a in enumerate(lim):
        for b in lim[i + 1:]:
            xy = [(r[a], r[b]) for r in recs if isinstance(r.get(a), float) and isinstance(r.get(b), float)]
            pairs.append(dict(C.pearson([p[0] for p in xy], [p[1] for p in xy]), x=a, y=b))
    pairs.sort(key=lambda p: (-(abs(p["r"]) if p.get("r") is not None else -1), p["x"], p["y"]))
    tests, ps = [], []
    for g in cat[:3]:
        lv = sorted({r.get(g) for r in recs if r.get(g) not in ("", None)})
        for y in num[:4]:
            grp = [[r[y] for r in recs if r.get(g) == x and isinstance(r.get(y), float)] for x in lv]
            grp = [q for q in grp if len(q) > 1]
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    res = C.welch(grp[i], grp[j])
                    res.update({"group_field": g, "value_field": y})
                    tests.append(res)
                    ps.append(res.get("p"))
    for t, a in zip(tests, C.holm(ps)):
        t["p_holm"], t["significant"] = a, bool(a is not None and a < R.get("alpha", 0.05))
    cats = {}
    for c in cat:
        cnt = {}
        for r in recs:
            cnt[r.get(c, "")] = cnt.get(r.get(c, ""), 0) + 1
        cats[c] = {"n_levels": len(cnt), "top": [{"value": k, "n": v} for k, v in
                                                 sorted(cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))[:15]]}
    return {"descriptive": desc, "correlations": {"pairs": pairs[:50], "labels": lim},
            "group_tests": tests, "categorical": cats, "numeric_fields": num, "categorical_fields": cat,
            "alpha": R.get("alpha", 0.05),
            "methods": [{"name": "mean/sd", "formula": "mean=sum(x)/n; sd=sqrt(sum((x-mean)^2)/(n-1))"},
                        {"name": "quantile", "formula": "linear interpolation, h=(n-1)p"},
                        {"name": "95%CI(mean)", "formula": "mean +- t(0.975,n-1)*sd/sqrt(n)"},
                        {"name": "pearson", "formula": "t=r*sqrt((n-2)/(1-r^2)) on complete cases"},
                        {"name": "group test", "formula": "pairwise Welch t; Holm adjustment over all pairs"},
                        {"name": "outlier", "formula": "Tukey 1.5*IQR or 0.6745*|x-med|/MAD>3.5 (flag only)"}]}


class Fig:
    """Minimal SVG canvas: text/line/rect/circle/polyline, fixed axes helper."""

    def __init__(self, w=760, h=470):
        self.w, self.h, self.e, self.l, self.r, self.t, self.b = w, h, [], 84, 24, 52, 76

    def raw(self, s):
        self.e.append(s)

    def txt(self, x, y, s, size=11, a="start", fill="#1a1a1a", rot=None):
        tr = ' transform="rotate(%s %.1f %.1f)"' % (rot, x, y) if rot is not None else ""
        self.raw('<text x="%.1f" y="%.1f" font-size="%d" text-anchor="%s" fill="%s" '
                 'font-family="DejaVu Sans, Arial, sans-serif"%s>%s</text>' % (x, y, size, a, fill, tr, C.esc(s)))

    def ln(self, x1, y1, x2, y2, stroke="#333", w=1.0):
        self.raw('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s"/>'
                 % (x1, y1, x2, y2, stroke, w))

    def rc(self, x, y, w, h, fill="#7aa6c2"):
        self.raw('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="#2b4a5c" stroke-width="0.8"/>'
                 % (x, y, max(w, 0.4), max(h, 0.4), fill))

    def dot(self, x, y, r=2.6):
        self.raw('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="#c0392b" fill-opacity="0.75"/>' % (x, y, r))

    def save(self, path, title, cap):
        Path(path).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
                              '<rect width="100%%" height="100%%" fill="#fff"/>' % (self.w, self.h, self.w, self.h)
                              + "".join(self.e) +
                              '<text x="%d" y="%d" font-size="10" fill="#555" font-family="DejaVu Sans, Arial, sans-serif">%s</text></svg>\n'
                              % (self.l, self.h - 14, C.esc(cap)), encoding="utf-8")


def axis(f, xs, ys, xl, yl):
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    x1 = x0 + 1 if x1 == x0 else x1
    y0, y1 = (y0 - 1, y1 + 1) if y1 == y0 else (y0, y1)
    y0, y1 = y0 - (y1 - y0) * 0.08, y1 + (y1 - y0) * 0.08
    W, H = f.w - f.l - f.r, f.h - f.t - f.b
    px = lambda x: f.l + (x - x0) / (x1 - x0) * W
    py = lambda y: f.t + H - (y - y0) / (y1 - y0) * H
    raw = (y1 - y0) / 5
    mag = 10 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), raw)
    v = math.ceil(y0 / step) * step
    while v <= y1:
        f.ln(f.l, py(v), f.l + W, py(v), "#e8e8e8")
        f.txt(f.l - 8, py(v) + 4, C.fmt(v), 10, "end")
        v += step
    f.ln(f.l, f.t, f.l, f.t + H)
    f.ln(f.l, f.t + H, f.l + W, f.t + H)
    f.txt(f.l + W / 2.0, f.t + H + 40, xl, 11, "middle")
    f.txt(18, f.t + H / 2.0, yl, 11, "middle", rot=-90)
    return px, py


def fig_hist(vals, path, title, xl):
    k = max(5, min(20, int(round(math.sqrt(len(vals))))))
    lo, hi = (min(vals), max(vals)) if max(vals) != min(vals) else (min(vals) - .5, max(vals) + .5)
    w, cnt = (hi - lo) / k, [0] * k
    for v in vals:
        cnt[min(k - 1, int((v - lo) / w))] += 1
    f = Fig()
    px, py = axis(f, [lo, hi], [0, max(cnt)], xl, "count")
    f.txt(f.w / 2.0, 26, title, 15, "middle")
    for i, n in enumerate(cnt):
        f.rc(px(lo + i * w) + 1, py(n), max(px(lo + (i + 1) * w) - px(lo + i * w) - 2, 1), py(0) - py(n))
    f.save(path, title, "n=%d bins=%d range=[%s,%s]; counts recomputed from cleaned.csv (equal-width bins)"
           % (len(vals), k, C.fmt(lo), C.fmt(hi)))
    return {"n": len(vals), "bins": [{"lo": lo + i * w, "hi": lo + (i + 1) * w, "count": cnt[i]} for i in range(k)]}


def fig_box(groups, path, title, xl, yl):
    groups = [(k, v) for k, v in groups if len(v) > 1]
    if not groups:
        return None
    f = Fig()
    px, py = axis(f, [0, len(groups)], [x for _, v in groups for x in v], xl, yl)
    f.txt(f.w / 2.0, 26, title, 15, "middle")
    step, data = (f.w - f.l - f.r) / len(groups), []
    for i, (nm, vals) in enumerate(groups):
        q1, md, q3 = C.quantile(vals, .25), C.quantile(vals, .5), C.quantile(vals, .75)
        iqr = q3 - q1
        lo = min([v for v in vals if v >= q1 - 1.5 * iqr] or [min(vals)])
        hi = max([v for v in vals if v <= q3 + 1.5 * iqr] or [max(vals)])
        cx = f.l + step * (i + .5)
        f.ln(cx, py(lo), cx, py(hi))
        f.ln(cx - 12, py(hi), cx + 12, py(hi))
        f.ln(cx - 12, py(lo), cx + 12, py(lo))
        f.rc(cx - step * .28, py(q3), step * .56, py(q1) - py(q3), "#cfe0ea")
        f.ln(cx - step * .28, py(md), cx + step * .28, py(md), "#b03a2e", 2.0)
        for v in vals:
            if v < lo or v > hi:
                f.dot(cx, py(v), 2.0)
        f.txt(cx, f.h - f.b + 16, str(nm)[:14], 9, "middle")
        data.append({"group": nm, "n": len(vals), "min": min(vals), "q1": q1, "median": md, "q3": q3,
                     "max": max(vals), "whisker_lo": lo, "whisker_hi": hi})
    f.save(path, title, "Tukey box (1.5*IQR whiskers), red line = median; statistics recomputed from cleaned.csv")
    return {"n": sum(len(v) for _, v in groups), "groups": data}
