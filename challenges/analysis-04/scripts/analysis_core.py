"""analysis_core.py - stdlib-only tabular IO, cleaning and statistics.

Values are computed from the real input bytes; no canned data, no third-party
imports, no randomness. Iteration order, rounding and quantile rule are fixed.
"""
import csv
import io
import json
import math
import re
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ENC = ("utf-8-sig", "utf-8", "gb18030", "cp1252", "latin-1")
MISS = {"", "na", "n/a", "n.a.", "nan", "null", "none", "-", "--", "—", "?", "nd", "n.d.", "*",
        "#n/a", ".", "missing", "未测", "无", "缺"}
SENT = {-999.0, -9999.0, -99999.0, 9999.0, 99999.0, 999.0}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_text(p):
    raw = Path(p).read_bytes() if isinstance(p, (str, Path)) else p
    for e in ENC:
        try:
            return raw.decode(e), e
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode("latin-1", "replace"), "latin-1+replace"


def norm(s):
    s = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", str(s).strip().strip('"').replace("%", "pct")
                .replace("³", "3").replace("²", "2"))
    return re.sub(r"_{2,}", "_", re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", s).strip("_").lower()) or "col"


def unit_of(raw):
    m = re.search(r"[\(\[\{]\s*([^\)\]\}]*)\s*[\)\]\}]", str(raw))
    return m.group(1).strip() if m else ""


def isnum(s):
    try:
        float(str(s).strip().replace(" ", "").replace(",", ""))
        return bool(str(s).strip())
    except ValueError:
        return False


def fmt(v, nd=4):
    if isinstance(v, float):
        if not math.isfinite(v):
            return "-"
        if abs(v) >= 1e5 or 0 < abs(v) < 1e-3:
            return ("%.3e" % v).replace("e-0", "e-").replace("e+0", "e")
        return ("%.*f" % (nd, v)).rstrip("0").rstrip(".") or "0"
    return "-" if v is None else str(v)


class Table:
    def __init__(self, name, cols, rows, path, src=None, raw=None, sheet="", enc=""):
        self.name, self.cols, self.rows, self.path = name, cols, rows, str(path)
        self.src, self.raw, self.sheet, self.enc = src or [], raw or list(cols), sheet, enc

    def col(self, c):
        i = self.cols.index(c)
        return [r[i] if i < len(r) else "" for r in self.rows]


def build_table(rows, name, path, src=None, sheet="", enc=""):
    rows = [list(r) for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return Table(name, [], [], path, [], [], sheet, enc)
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    src = list(src or range(1, len(rows) + 1))
    h = rows[0]
    if sum(1 for c in h if isnum(c)) >= max(1, sum(1 for c in h if str(c).strip()) // 2):
        raw, body, body_src = ["col_%d" % (i + 1) for i in range(w)], rows, src
    else:
        raw, body, body_src = h, rows[1:], (src[1:] if len(src) > 1 else src)
    cols, seen = [], {}
    for i, x in enumerate(raw):
        b = norm(x) if str(x).strip() else "col_%d" % (i + 1)
        seen[b] = seen.get(b, 0) + 1
        cols.append(b if seen[b] == 1 else "%s_%d" % (b, seen[b]))
    return Table(name or Path(path).stem, cols, body, path, body_src, [str(x) for x in raw], sheet, enc)


def delimiter(s):
    best, sc = ",", -1
    for d in (",", ";", "\t", "|"):
        n = [ln.count(d) for ln in s.splitlines()[:30] if ln.strip()]
        if n and n.count(max(set(n), key=n.count)) * max(set(n), key=n.count) > sc:
            best, sc = d, n.count(max(set(n), key=n.count)) * max(set(n), key=n.count)
    return best


def parse_csv(path, name=None):
    txt, enc = read_text(path)
    d = delimiter(txt[:60000])
    rows, src, rd = [], [], csv.reader(io.StringIO(txt), delimiter=d)
    for r in rd:
        rows.append([c.strip() for c in r])
        src.append(rd.line_num)
    return build_table(rows, name or Path(path).stem, path, src, enc=enc), \
        {"encoding": enc, "delimiter": d, "bytes": Path(path).stat().st_size}


def parse_xlsx(path, name=None):
    out = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        sh = ["".join(t.text or "" for t in si.iter(NS + "t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")] \
            if "xl/sharedStrings.xml" in names else []
        for k in sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
            rows, src = [], []
            for row in ET.fromstring(z.read(k)).iter(NS + "row"):
                d = {}
                for c in row.findall(NS + "c"):
                    ref = re.match(r"[A-Z]+", c.get("r") or "")
                    idx = len(d)
                    if ref:
                        idx = 0
                        for ch in ref.group(0):
                            idx = idx * 26 + ord(ch) - 64
                        idx -= 1
                    v, t, ins = c.find(NS + "v"), c.get("t"), c.find(NS + "is")
                    if t == "s" and v is not None and v.text and int(v.text) < len(sh):
                        d[idx] = sh[int(v.text)]
                    elif t == "inlineStr" and ins is not None:
                        d[idx] = "".join(x.text or "" for x in ins.iter(NS + "t"))
                    else:
                        d[idx] = (v.text if v is not None else "") or ""
                if d:
                    rows.append([str(d.get(i, "")).strip() for i in range(max(d) + 1)])
                    src.append(int(row.get("r") or len(rows)))
            t = build_table(rows, "%s-s%s" % (name or Path(path).stem, k[-6:-4]), path, src, enc="xlsx")
            if t.cols:
                out.append(t)
    return out


def parse_sqlite(path, cap=200000):
    tabs, meta = [], {"path": str(path), "tables": [], "errors": []}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % Path(path).as_posix(), uri=True)
        for nm in [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]:
            try:
                cur = con.execute('SELECT * FROM "%s" LIMIT %d' % (nm.replace('"', '""'), cap))
                cols = [d[0] for d in cur.description]
                rows = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
                meta["tables"].append({"table": nm, "n_rows": len(rows), "columns": cols})
                tabs.append(Table(nm, [norm(c) for c in cols], rows, path, list(range(1, len(rows) + 1)),
                                  cols, enc="sqlite"))
            except sqlite3.Error as e:
                meta["errors"].append("%s: %s" % (nm, e))
        con.close()
    except sqlite3.Error as e:
        meta["errors"].append("open failed: %s" % e)
    return tabs, meta


def kind_of(vals):
    v = [x for x in vals if str(x).strip().lower() not in MISS]
    if not v:
        return "empty"
    if sum(1 for x in v if isnum(str(x).replace(" ", ""))) / len(v) >= 0.9:
        return "numeric"
    if sum(1 for x in v if re.match(r"^\d{4}[-/]\d{1,2}", str(x).strip())) / len(v) >= 0.9:
        return "datetime"
    return "categorical" if len({str(x).strip() for x in v}) <= max(20, int(0.2 * len(v))) else "text"


def parse_number(raw):
    if raw is None:
        return {"status": "missing", "value": None, "unit": "", "note": "null"}
    t = str(raw).strip()
    if t.lower() in MISS:
        return {"status": "missing", "value": None, "unit": "", "note": "missing token"}
    t, note = t.replace("\u2212", "-").replace("\u00a0", "").replace(" ", ""), []
    m = re.match(r"^(<=|>=|<|>|~|±|\+/-)(.*)$", t)
    if m:
        t = m.group(2).strip()
        note.append("qualified(%s)" % m.group(1))
    um = re.match(r"^([+-]?\d[\d.,]*(?:[eE][+-]?\d+)?)([^\d.,].*)?$", t)
    if not um:
        return {"status": "invalid", "value": None, "unit": "", "note": "not numeric: %r" % t[:24]}
    num, unit = um.group(1), (um.group(2) or "").strip()
    if "," in num and "." in num:
        num, _ = num.replace(",", ""), note.append("thousands_sep")
    elif "," in num:
        if all(len(x) == 3 for x in num.split(",")[1:]):
            num, _ = num.replace(",", ""), note.append("thousands_sep")
        else:
            num, _ = num.replace(",", "."), note.append("decimal_comma")
    try:
        val = float(num)
    except ValueError:
        return {"status": "invalid", "value": None, "unit": "", "note": "not numeric: %r" % t[:24]}
    if not math.isfinite(val):
        return {"status": "invalid", "value": None, "unit": unit, "note": "non-finite"}
    if unit:
        note.append("unit_in_cell")
    return {"status": "ok", "value": val, "unit": unit.strip().lower().strip("()[]"), "note": "; ".join(note)}


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    if len(xs) < 2:
        return None
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def quantile(xs, p):
    s = sorted(xs)
    if not s:
        return None
    if len(s) == 1:
        return s[0]
    h = (len(s) - 1) * p
    lo = int(math.floor(h))
    return s[lo] + (h - lo) * (s[min(lo + 1, len(s) - 1)] - s[lo])


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    def frac(p, q, xx):
        eps, fpm = 3e-14, 1e-300
        qab, qap, qam = p + q, p + 1.0, p - 1.0
        d = 1.0 - qab * xx / qap
        d = 1.0 / (d if abs(d) > fpm else fpm)
        c, h = 1.0, d
        for m in range(1, 201):
            m2 = 2 * m
            for aa in (m * (q - m) * xx / ((qam + m2) * (p + m2)),
                       -(p + m) * (qab + m) * xx / ((p + m2) * (qap + m2))):
                d = 1.0 + aa * d
                d = 1.0 / (d if abs(d) > fpm else fpm)
                c = 1.0 + aa / c
                c = c if abs(c) > fpm else fpm
                h *= d * c
            if abs(d * c - 1.0) < eps:
                break
        return h

    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    return bt * frac(a, b, x) / a if x < (a + 1.0) / (a + b + 2.0) else 1.0 - bt * frac(b, a, 1.0 - x) / b


def t_sf(t, df):
    if df <= 0:
        return None
    p = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))
    return p if t > 0 else 1.0 - p


def t_ppf(p, df):
    lo, hi = -1e3, 1e3
    for _ in range(120):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if t_sf(mid, df) > 1 - p else (lo, mid)
    return (lo + hi) / 2


def pearson(x, y):
    n = min(len(x), len(y))
    if n < 3:
        return {"n": n, "r": None, "p": None, "note": "n<3"}
    mx, my = mean(x[:n]), mean(y[:n])
    sxy = sum((a - mx) * (b - my) for a, b in zip(x[:n], y[:n]))
    sxx = sum((a - mx) ** 2 for a in x[:n])
    syy = sum((b - my) ** 2 for b in y[:n])
    if sxx <= 0 or syy <= 0:
        return {"n": n, "r": None, "p": None, "note": "zero variance"}
    r = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))
    if abs(r) >= 1.0:
        return {"n": n, "r": r, "p": 0.0, "df": n - 2}
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return {"n": n, "r": r, "t": t, "df": n - 2, "p": 2 * t_sf(abs(t), n - 2)}


def welch(x, y):
    n1, n2 = len(x), len(y)
    if n1 < 2 or n2 < 2:
        return {"status": "not_run", "reason": "group n<2", "n1": n1, "n2": n2}
    m1, m2, v1, v2 = mean(x), mean(y), sd(x) ** 2, sd(y) ** 2
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return {"status": "not_run", "reason": "zero variance in both groups"}
    t = (m1 - m2) / se
    df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    ci = se * t_ppf(0.975, df)
    pooled = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    return {"status": "ok", "test": "Welch two-sample t", "n1": n1, "n2": n2, "mean1": m1, "mean2": m2,
            "diff": m1 - m2, "t": t, "df": df, "p": 2 * t_sf(abs(t), df),
            "ci95_diff": [m1 - m2 - ci, m1 - m2 + ci], "cohen_d": (m1 - m2) / pooled if pooled else None,
            "variance_ratio": (v1 / v2) if v2 else None}


def holm(ps):
    order = sorted([i for i, p in enumerate(ps) if p is not None], key=lambda i: ps[i])
    out, run, m = [None] * len(ps), 0.0, len(order)
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        out[i] = run
    return out


def describe(xs, label=""):
    if not xs:
        return {"n": 0, "label": label, "note": "no valid values"}
    m, s = mean(xs), sd(xs)
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    se = s / math.sqrt(len(xs)) if s else None
    ci = [m - t_ppf(0.975, len(xs) - 1) * se, m + t_ppf(0.975, len(xs) - 1) * se] if se and len(xs) > 1 else None
    n = len(xs)
    sp = math.sqrt(sum((x - m) ** 2 for x in xs) / n)
    g1 = sum(((x - m) / sp) ** 3 for x in xs) / n if sp and n > 2 else None
    g2 = sum(((x - m) / sp) ** 4 for x in xs) / n - 3.0 if sp and n > 3 else None
    return {"n": n, "label": label, "mean": m, "sd": s, "se": se, "ci95_mean": ci, "min": min(xs), "q1": q1,
            "median": quantile(xs, 0.5), "q3": q3, "max": max(xs), "iqr": q3 - q1, "sum": sum(xs), "skew": g1,
            "excess_kurtosis": g2, "cv": (s / m) if (s and m) else None}


def out_tukey(xs):
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    if q1 is None:
        return set()
    iqr = q3 - q1
    return {i for i, v in enumerate(xs) if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr}


def out_mad(xs):
    med = quantile(xs, 0.5)
    if med is None:
        return set()
    mad = quantile([abs(v - med) for v in xs], 0.5)
    return set() if not mad else {i for i, v in enumerate(xs) if 0.6745 * abs(v - med) / mad > 3.5}


# ---------------- cleaning ----------------
CATS = (("miss", "missing", "missing_or_blank", "空值/缺失标记", "可用值统计，不填补", None),
        ("inv", "format", "unparsable_number", "无法解析为数值", "原文保留，按缺失处理", None),
        ("sent", "format", "suspect_sentinel", "疑似哨兵值(-999等)", "排除并标记", "确认是否为缺失代码"))


def issue(field, cat, name, rows, rule, act, ph=None):
    return {"field": field, "category": cat, "issue": name, "count": len(rows), "rows": rows[:20],
            "rule": rule, "action": act, "pending_human": ph}


def clean(tbl, dic, kinds, rules, log):
    cols, raw = tbl.cols, tbl.raw
    U = {c: (str(dic.get(c, {}).get("unit", "")) or (unit_of(raw[i]) if i < len(raw) else "")).strip().lower()
         for i, c in enumerate(cols)}
    P, issues, conv = {}, [], []
    for c in cols:
        if kinds[c] != "numeric":
            continue
        d = {"v": {}, "miss": [], "inv": [], "sent": [], "cu": {}}
        for j, cell in enumerate(tbl.col(c)):
            p = parse_number(cell)
            if p["status"] != "ok":
                d["miss" if p["status"] == "missing" else "inv"].append(j)
            elif p["value"] in SENT and p["value"] < 0:
                d["sent"].append(j)
            else:
                d["v"][j] = p["value"]
                if p["unit"]:
                    d["cu"].setdefault(p["unit"], []).append(j)
        P[c] = d
        for u, js in d["cu"].items():
            if not U[c] or u == U[c]:
                continue
            hit = next((r for r in rules.get("unit_conversions", [])
                        if u in [x.lower() for x in r.get("from", [])] and U[c] == r.get("to")), None)
            if hit:
                for j in js:
                    d["v"][j] = d["v"][j] * hit.get("factor", 1) + hit.get("offset", 0)
                f, o = hit.get("factor", 1), hit.get("offset", 0)
                conv.append({"field": c, "from_unit": u, "to_unit": U[c], "factor": f, "offset": o,
                             "forward": "canonical = raw*%s+%s" % (f, o),
                             "inverse": "raw = (canonical-%s)/%s" % (o, f),
                             "rows": [tbl.src[j] for j in js[:20]]})
            else:
                issues.append(issue(c, "unit_encoding", "unit_mismatch_not_convertible",
                                    [tbl.src[j] for j in js], "cell unit %r vs declared %r" % (u, U[c]),
                                    "kept raw value, flagged", "确认单位口径后再换算"))
    flags = {}
    for c, d in P.items():
        s = sorted(d["v"])
        out = (out_tukey(s) | out_mad(s)) if len(s) > 3 else set()
        pos = {k: i for i, k in enumerate(s)}
        flags[c] = {j for j in d["v"] if pos[d["v"][j]] in out}
        for k, cat, nm, rule, act, ph in CATS:
            if d[k]:
                issues.append(issue(c, cat, nm, [tbl.src[j] for j in d[k]], rule, act, ph))
        if d["cu"]:
            issues.append(issue(c, "unit_encoding", "unit_in_cell",
                                [tbl.src[j] for j in sorted({j for v in d["cu"].values() for j in v})],
                                "单元格内含单位", "已剥离单位并记录"))
        if flags[c]:
            issues.append(issue(c, "outlier", "tukey_or_mad_flag", [tbl.src[j] for j in sorted(flags[c])],
                                "Tukey 1.5*IQR 或 MAD-z>3.5", "标记保留；统计去/留两套口径"))
    recs = []
    for i in range(len(tbl.rows)):
        r = {"_src_row": tbl.src[i] if i < len(tbl.src) else i + 1}
        for c in cols:
            if kinds[c] == "numeric":
                r[c], r[c + "__flag"] = P[c]["v"].get(i, ""), ""
            else:
                r[c] = str(tbl.col(c)[i]).strip()
        recs.append(r)
    for c, d in P.items():
        for js, lab in ((d["miss"], "missing"), (d["inv"], "invalid"), (d["sent"], "sentinel"), (flags[c], "outlier")):
            for i in js:
                recs[i][c + "__flag"] = lab
    sig = {}
    for r in recs:
        sig.setdefault(tuple("" if r.get(c) == "" else (fmt(r[c], 6) if isinstance(r[c], float) else str(r[c]))
                             for c in cols), []).append(r["_src_row"])
    for r in recs:
        r["_dup_group"] = next(("dup-%d" % v[0] for v in sig.values() if len(v) > 1 and r["_src_row"] in v), "")
    dups = sorted(x for v in sig.values() if len(v) > 1 for x in v)
    if dups:
        issues.append(issue("*", "duplicate", "exact_duplicate_rows", dups, "清洗后各字段完全相同",
                            "标记 _dup_group，保留全部行，未去重", "确认是否合法重复观测"))
    for c in [c for c in cols if str(dic.get(c, {}).get("pk", "")).lower() in ("true", "1", "yes", "是", "pk")]:
        cnt = {}
        for r in recs:
            cnt[r.get(c, "")] = cnt.get(r.get(c, ""), 0) + 1
        bad = [r["_src_row"] for r in recs if cnt.get(r.get(c, ""), 0) > 1]
        if bad:
            issues.append(issue(c, "duplicate", "primary_key_conflict", bad, "字典声明主键 %s" % c, "保留并标记"))
    imp = {}
    for c, d in P.items():
        if d["miss"] and d["v"] and len(d["miss"]) <= max(1, int(0.3 * len(recs))):
            med = quantile(list(d["v"].values()), 0.5)
            imp[c] = {"strategy": "median", "value": med, "n_filled": len(d["miss"]),
                      "column": c + "__imputed", "used_in_stats": False}
            for i in d["miss"]:
                recs[i][c + "__imputed"] = med
    log("cleaned rows=%d issues=%d numeric=%d" % (len(recs), len(issues), len(P)))
    return recs, issues, conv, imp, U
