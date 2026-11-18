"""statslib.py - deterministic standard-library statistics and SVG charting.

Used by run.py (skill analysis-05). No RNG, clock, locale or set-order
dependence. Formulas, degrees of freedom, test preconditions and known limits
are documented in references/methods.md.
"""
import math

PAL = ["#2f6fb0", "#cf6a1a", "#3f8f4a", "#b3384e", "#6f5aa8", "#2b8f96", "#8a6d1f", "#555"]
W, H, ML, MT, MR, MB = 820, 480, 84, 70, 32, 84
PW, PH = W - ML - MR, H - MT - MB
EPS, FPMIN = 3.0e-14, 1.0e-300


def num(x):
    """Parse one cell to float, or None. Handles %, unicode minus, thin spaces."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
        return v if math.isfinite(v) else None
    s = str(x).strip().replace("\u2212", "-").replace("\u2013", "-")
    s = s.replace("\u00a0", "").replace(" ", "").replace("\u2009", "")
    if not s:
        return None
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    try:
        v = float(s)
    except ValueError:
        try:
            v = float(s.replace(",", "."))
        except ValueError:
            return None
    if not math.isfinite(v):
        return None
    return v / 100.0 if pct else v


def clean(xs):
    return [x for x in xs if x is not None]


def mean(xs):
    v = clean(xs)
    return sum(v) / len(v) if v else None


def var(xs):
    v = clean(xs)
    if len(v) < 2:
        return None
    m = sum(v) / len(v)
    return sum((x - m) ** 2 for x in v) / (len(v) - 1)


def sd(xs):
    v = var(xs)
    return None if v is None else math.sqrt(v)


def quantile(xs, p):
    v = sorted(clean(xs))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def median(xs):
    return quantile(xs, 0.5)


def skew(xs):
    v = clean(xs)
    n = len(v)
    if n < 3:
        return None
    m = sum(v) / n
    s = math.sqrt(sum((x - m) ** 2 for x in v) / n)
    if s == 0:
        return 0.0
    return sum(((x - m) / s) ** 3 for x in v) / n


def fmt(v, sig=4):
    if v is None:
        return "NA"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if v != v or v in (float("inf"), float("-inf")):
        return "NA"
    if v == 0:
        return "0"
    if abs(v) >= 1e5 or abs(v) < 1e-4:
        return "%.3e" % v
    return "%.*g" % (sig, v)


def pretty(p):
    """p-value for reports: never claims more precision than is computed."""
    if p is None:
        return "NA"
    if p < 1e-4:
        return "<1e-4"
    return "%.4g" % p


def rank(values):
    idx = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and values[idx[j + 1]] == values[idx[i]]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[idx[k]] = r
        i = j + 1
    return out


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (FPMIN if abs(d) < FPMIN else d)
    c, h = 1.0, d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (FPMIN if abs(d) < FPMIN else d)
        c = 1.0 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (FPMIN if abs(d) < FPMIN else d)
        c = 1.0 + aa / c
        c = FPMIN if abs(c) < FPMIN else c
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    """Regularized incomplete beta I_x(a,b) (Numerical Recipes continued fraction)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _gser(a, x):
    ap, delta, s = a, 1.0 / a, 1.0 / a
    for _ in range(500):
        ap += 1.0
        delta *= x / ap
        s += delta
        if abs(delta) < abs(s) * EPS:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a, x):
    b, c = x + 1.0 - a, 1.0 / FPMIN
    d = 1.0 / (b if b else FPMIN)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        e = an * d + b
        d = 1.0 / (e if abs(e) > FPMIN else FPMIN)
        c = b + an / c
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(x, k):
    if x <= 0 or k <= 0:
        return 1.0
    a, y = k / 2.0, x / 2.0
    return 1.0 - _gser(a, y) if y < a + 1.0 else _gcf(a, y)


def t_sf2(t, df):
    """Two-sided p of Student t."""
    if t is None or df <= 0:
        return None
    return betai(df / 2.0, 0.5, df / (df + t * t))


def f_sf(f, d1, d2):
    return 1.0 if f <= 0 else betai(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def t_crit(df, p=0.975):
    lo, hi = 0.0, 1e3
    for _ in range(120):
        mid = (lo + hi) / 2.0
        if betai(df / 2.0, 0.5, df / (df + mid * mid)) > 2 * (1 - p):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def welch_t(a, b):
    a, b = clean(a), clean(b)
    if len(a) < 2 or len(b) < 2:
        return {"ok": False, "reason": "group with n<2"}
    ma, mb, va, vb = mean(a), mean(b), var(a), var(b)
    se2 = va / len(a) + vb / len(b)
    if se2 <= 0:
        return {"ok": False, "reason": "zero variance in both groups"}
    se = math.sqrt(se2)
    df = se2 ** 2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
    t = (ma - mb) / se
    tc = t_crit(df)
    pooled = math.sqrt((va + vb) / 2.0)
    return {"ok": True, "test": "Welch two-sample t (two-sided)", "statistic": t, "df": df,
            "p": t_sf2(t, df), "mean_a": ma, "mean_b": mb, "n_a": len(a), "n_b": len(b),
            "diff": ma - mb, "se": se, "ci95": [ma - mb - tc * se, ma - mb + tc * se],
            "cohens_d": (ma - mb) / pooled if pooled else None}


def anova(groups):
    groups = [g for g in (clean(x) for x in groups) if g]
    k, n = len(groups), sum(len(g) for g in groups)
    if k < 2 or n <= k:
        return {"ok": False, "reason": "fewer than 2 non-empty groups, or n<=k"}
    gm = sum(sum(g) for g in groups) / n
    ssb = sum(len(g) * (mean(g) - gm) ** 2 for g in groups)
    ssw = sum(sum((x - mean(g)) ** 2 for x in g) for g in groups)
    if ssw <= 0:
        return {"ok": False, "reason": "zero within-group variance"}
    d1, d2 = k - 1, n - k
    f = (ssb / d1) / (ssw / d2)
    return {"ok": True, "test": "one-way ANOVA (F test)", "statistic": f, "df": [d1, d2],
            "p": f_sf(f, d1, d2), "n": n, "k": k, "eta_sq": ssb / (ssb + ssw)}


def mannwhitney(a, b):
    a, b = clean(a), clean(b)
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return {"ok": False, "reason": "group with n<2"}
    allv, n = a + b, n1 + n2
    r = rank(allv)
    u1 = sum(r[:n1]) - n1 * (n1 + 1) / 2.0
    u = min(u1, n1 * n2 - u1)
    ties = {}
    for x in allv:
        ties[x] = ties.get(x, 0) + 1
    v = n1 * n2 / 12.0 * ((n + 1) - sum(t ** 3 - t for t in ties.values()) / (n * (n - 1)))
    if v <= 0:
        return {"ok": False, "reason": "zero variance"}
    z = (u - n1 * n2 / 2.0 + 0.5) / math.sqrt(v)
    return {"ok": True, "test": "Mann-Whitney U (normal approx., tie corrected)",
            "statistic": u, "z": z, "p": min(1.0, 2 * norm_sf(abs(z))),
            "n_a": n1, "n_b": n2, "rank_biserial": 1 - 2 * u / (n1 * n2)}


def pearson(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        return {"ok": False, "reason": "fewer than 3 complete pairs"}
    mx, my = mean([p[0] for p in pairs]), mean([p[1] for p in pairs])
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return {"ok": False, "reason": "constant variable; correlation undefined"}
    r = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))
    p = 0.0 if abs(r) >= 1.0 else t_sf2(r * math.sqrt((n - 2) / (1 - r * r)), n - 2)
    return {"ok": True, "test": "Pearson product-moment r", "r": r, "n": n, "p": p, "r2": r * r}


def spearman(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 3:
        return {"ok": False, "reason": "fewer than 3 complete pairs"}
    res = pearson(rank([p[0] for p in pairs]), rank([p[1] for p in pairs]))
    if not res.get("ok"):
        return res
    return {"ok": True, "test": "Spearman rho (Pearson on ranks)", "rho": res["r"],
            "n": res["n"], "p": res["p"]}


def _inv(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(a[r][i]))
        if abs(a[p][i]) < 1e-12:
            return None
        a[i], a[p] = a[p], a[i]
        piv = a[i][i]
        a[i] = [v / piv for v in a[i]]
        for r in range(n):
            if r != i and a[r][i]:
                f = a[r][i]
                a[r] = [v - f * w for v, w in zip(a[r], a[i])]
    return [row[n:] for row in a]


def ols(y, xs, names):
    rows = [(yy,) + tuple(c[i] for c in xs) for i, yy in enumerate(y)
            if yy is not None and all(c[i] is not None for c in xs)]
    n, p = len(rows), len(xs) + 1
    if n <= p + 1:
        return {"ok": False, "reason": "complete rows n=%d <= parameters+1=%d" % (n, p + 1)}
    X = [[1.0] + list(r[1:]) for r in rows]
    Y = [r[0] for r in rows]
    xtx = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    xty = [sum(X[i][a] * Y[i] for i in range(n)) for a in range(p)]
    inv = _inv(xtx)
    if inv is None:
        return {"ok": False, "reason": "singular design matrix (collinear predictors)"}
    beta = [sum(inv[a][b] * xty[b] for b in range(p)) for a in range(p)]
    resid = [Y[i] - sum(b * x for b, x in zip(beta, X[i])) for i in range(n)]
    ssr = sum(r * r for r in resid)
    my = sum(Y) / n
    sst = sum((y - my) ** 2 for y in Y)
    if sst <= 0:
        return {"ok": False, "reason": "constant response"}
    df, s2 = n - p, ssr / (n - p)
    terms = []
    for a in range(p):
        se = math.sqrt(max(s2 * inv[a][a], 0.0))
        t = beta[a] / se if se > 0 else None
        terms.append({"term": names[a - 1] if a else "intercept", "coef": beta[a], "se": se,
                      "t": t, "p": t_sf2(t, df) if t is not None else None})
    r2 = 1 - ssr / sst
    sd_res = math.sqrt(s2) if s2 >= 0 else None
    worst = max((abs(r) for r in resid), default=None)
    return {"ok": True, "test": "OLS with intercept", "n": n, "df": df, "r2": r2,
            "adj_r2": 1 - (1 - r2) * (n - 1) / df, "resid_se": sd_res,
            "max_abs_resid": worst, "terms": terms}


def holm(pvals):
    """Holm-Bonferroni adjusted p-values; None entries are skipped, order preserved."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    out = [None] * len(pvals)
    if not idx:
        return out
    m, running = len(idx), 0.0
    for k, i in enumerate(sorted(idx, key=lambda i: pvals[i])):
        running = max(running, min(1.0, (m - k) * pvals[i]))
        out[i] = running
    return out


def outlier_scan(xs, rule="iqr"):
    vals = clean(xs)
    if rule == "z":
        m, s = mean(vals), sd(vals)
        if not s:
            return [0] * len(xs), {"rule": "z", "skipped": "sd=0"}
        return ([1 if (x is not None and abs((x - m) / s) > 3.0) else 0 for x in xs],
                {"rule": "z", "criterion": "|z|>3", "mean": m, "sd": s})
    if len(vals) < 4:
        return [0] * len(xs), {"rule": rule, "skipped": "n<4"}
    if rule == "mad":
        med = median(vals)
        mad = median([abs(x - med) for x in vals])
        if not mad:
            return [0] * len(xs), {"rule": "mad", "skipped": "MAD=0"}
        return ([1 if (x is not None and abs(0.6745 * (x - med) / mad) > 3.5) else 0 for x in xs],
                {"rule": "mad", "criterion": "modified z>3.5", "median": med, "mad": mad})
    q1, q3 = quantile(vals, .25), quantile(vals, .75)
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return ([1 if (x is not None and (x < lo or x > hi)) else 0 for x in xs],
            {"rule": "iqr", "criterion": "Tukey fence q1-1.5IQR, q3+1.5IQR",
             "q1": q1, "q3": q3, "lower": lo, "upper": hi})


def describe(xs):
    """Descriptive statistics for one field; every key is computed, never assumed."""
    v = clean(xs)
    n = len(v)
    d = {"n": n, "n_missing": len(xs) - n}
    if not n:
        return d
    m, s = mean(v), sd(v)
    q1, q2, q3 = quantile(v, .25), quantile(v, .5), quantile(v, .75)
    d.update({"mean": m, "sd": s, "se": (s / math.sqrt(n)) if s is not None else None,
              "median": q2, "q1": q1, "q3": q3, "iqr": q3 - q1,
              "min": min(v), "max": max(v), "range": max(v) - min(v), "skew": skew(v),
              "cv": (s / m) if (s is not None and m) else None,
              "n_zero": sum(1 for x in v if x == 0)})
    fl, meta = outlier_scan(xs, "iqr")
    d["n_outlier_iqr"] = sum(fl)
    d["iqr_fence"] = [meta.get("lower"), meta.get("upper")]
    fl2, meta2 = outlier_scan(xs, "mad")
    d["n_outlier_mad"] = sum(fl2)
    d["mad_fence"] = [meta2.get("median"), meta2.get("mad")]
    return d


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def nice_ticks(lo, hi, n=6):
    if not (hi > lo):
        hi = lo + 1.0
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = 10 * mag
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    if step <= 0:
        step = 1.0
    v = math.floor(lo / step) * step
    out = []
    for _ in range(120):
        if v > hi + step * 1e-9:
            break
        out.append(round(v, 12))
        v += step
    return out, step


def lbl(v, step):
    if abs(v) >= 1e5 or (v != 0 and abs(v) < 1e-3):
        return "%.2g" % v
    d = 0 if step >= 1 else min(4, int(math.ceil(-math.log10(step) - 1e-9)))
    return "%.*f" % (d, v)


class Canvas:
    """Minimal SVG canvas: text, lines, rects, circles. Text stays selectable."""

    def __init__(self, w=W, h=H):
        self.w, self.h, self.p = w, h, []

    def line(self, x1, y1, x2, y2, c="#333", w=1.0, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.p.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"'
                      ' stroke-width="%s"%s/>' % (x1, y1, x2, y2, c, w, d))

    def rect(self, x, y, w, h, fill="#fff", stroke="none", sw=1.0, op=None):
        o = ' fill-opacity="%.2f"' % op if op is not None else ""
        self.p.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"'
                      ' stroke="%s" stroke-width="%s"%s/>'
                      % (x, y, max(w, 0), max(h, 0), fill, stroke, sw, o))

    def circle(self, x, y, r, fill, op=0.75):
        self.p.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%.2f"/>'
                      % (x, y, r, fill, op))

    def text(self, x, y, s, size=12, anchor="start", fill="#222", rot=None, weight="normal"):
        tr = ' transform="rotate(%.0f %.1f %.1f)"' % (rot, x, y) if rot else ""
        self.p.append('<text x="%.1f" y="%.1f" font-family="DejaVu Sans,Helvetica,sans-serif"'
                      ' font-size="%s" fill="%s" text-anchor="%s" font-weight="%s"%s>%s</text>'
                      % (x, y, size, fill, anchor, weight, tr, esc(s)))

    def svg(self, title, desc):
        return "\n".join(['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"'
                          ' viewBox="0 0 %d %d" role="img">' % (self.w, self.h, self.w, self.h),
                          "<title>%s</title><desc>%s</desc>" % (esc(title), esc(desc)),
                          '<rect width="100%" height="100%" fill="#ffffff"/>'] + self.p + ["</svg>"])


def _axes(title, ylo, yhi, xlab, ylab, note):
    c = Canvas()
    c.text(W / 2, 26, title, size=15, anchor="middle", weight="bold")
    ticks, step = nice_ticks(ylo, yhi, 6)
    lo, hi = min(ylo, ticks[0]), max(yhi, ticks[-1])
    if hi <= lo:
        hi = lo + 1.0

    def Y(v):
        return H - MB - (v - lo) / (hi - lo) * PH

    c.rect(ML, MT, PW, PH, "#fff", "#9a9a9a", 1.0)
    for t in ticks:
        y = Y(t)
        if MT - 1 <= y <= H - MB + 1:
            c.line(ML, y, ML + PW, y, "#ebebeb", 1.0)
            c.text(ML - 8, y + 4, lbl(t, step), size=11, anchor="end", fill="#444")
    c.line(ML, MT, ML, H - MB, "#666", 1.2)
    c.line(ML, H - MB, ML + PW, H - MB, "#666", 1.2)
    if ylab:
        c.text(22, MT + PH / 2, ylab, size=12, anchor="middle", rot=-90, fill="#333")
    if xlab:
        c.text(ML + PW / 2, H - 24, xlab, size=12, anchor="middle", fill="#333")
    if note:
        c.text(ML, H - 7, note, size=10, fill="#777")
    return c, Y, lo, hi


def _xticks(c, lo, hi, X, n=7):
    ticks, step = nice_ticks(lo, hi, n)
    for t in ticks:
        if lo - 1e-9 <= t <= hi + 1e-9:
            c.line(X(t), H - MB, X(t), H - MB + 4, "#666", 1.0)
            c.text(X(t), H - MB + 16, lbl(t, step), size=10, anchor="middle", fill="#444")


def fig_bars(title, cats, vals, errs=None, ylab="", xlab="", note=""):
    """Bar chart of group means with optional error bars, zero baseline when possible."""
    vals = list(vals)
    pool = clean(vals)
    if not cats or not pool:
        return None
    hi = max(pool) + (max(errs) if errs else 0.0)
    lo = 0.0 if min(pool) >= 0 else min(pool) * 1.15
    c, Y, ylo, yhi = _axes(title, lo, hi * 1.08 or 1.0, xlab, ylab, note)
    base, bw = Y(0.0 if lo <= 0 <= yhi else ylo), PW / len(cats)
    for i, cat in enumerate(cats):
        cx = ML + bw * (i + 0.5)
        v = vals[i]
        if v is None:
            c.text(cx, base - 6, "NA", size=10, anchor="middle", fill="#999")
            continue
        top = Y(v)
        c.rect(cx - bw * 0.31, min(top, base), bw * 0.62, abs(base - top),
               PAL[i % len(PAL)], "#fff", 0.8, 0.92)
        if errs and errs[i]:
            e = errs[i]
            c.line(cx, Y(v - e), cx, Y(v + e), "#333", 1.4)
            for yy in (Y(v - e), Y(v + e)):
                c.line(cx - 5, yy, cx + 5, yy, "#333", 1.2)
        c.text(cx, min(top, base) - 6, fmt(v, 3), size=10, anchor="middle")
        if len(cats) <= 14:
            c.text(cx, H - MB + 16, str(cat)[:14], size=10, anchor="middle", fill="#444")
    return c


def fig_box(title, cats, series, ylab="", xlab="", note=""):
    """Box plot (Tukey fences) with jittered outliers and per-group n."""
    pool = clean([v for s in series for v in s])
    if not cats or not pool:
        return None
    lo, hi = min(pool), max(pool)
    pad = (hi - lo) * 0.1 or 1.0
    c, Y, ylo, yhi = _axes(title, lo - pad, hi + pad, xlab, ylab, note)
    bw = PW / len(cats)
    for i, cat in enumerate(cats):
        vals = clean(series[i])
        cx = ML + bw * (i + 0.5)
        if not vals:
            c.text(cx, H - MB - 10, "NA", size=10, anchor="middle", fill="#999")
            continue
        q1, q2, q3 = quantile(vals, .25), quantile(vals, .5), quantile(vals, .75)
        iqr, w = q3 - q1, bw * 0.44
        wlo = min([v for v in vals if v >= q1 - 1.5 * iqr] or [q1])
        whi = max([v for v in vals if v <= q3 + 1.5 * iqr] or [q3])
        c.rect(cx - w / 2, Y(q3), w, max(1.0, Y(q1) - Y(q3)), PAL[i % len(PAL)], "#333", 1.0, 0.5)
        c.line(cx - w / 2, Y(q2), cx + w / 2, Y(q2), "#222", 2.2)
        c.line(cx, Y(q3), cx, Y(whi), "#444", 1.2)
        c.line(cx, Y(q1), cx, Y(wlo), "#444", 1.2)
        for yy in (Y(whi), Y(wlo)):
            c.line(cx - w / 3, yy, cx + w / 3, yy, "#444", 1.2)
        for j, v in enumerate([v for v in vals if v < wlo or v > whi][:150]):
            c.circle(cx + ((j % 9) - 4) * 0.9, Y(v), 2.0, "#b3384e", 0.7)
        c.text(cx, Y(q3) - 6, "n=%d" % len(vals), size=9, anchor="middle", fill="#555")
        if len(cats) <= 14:
            c.text(cx, H - MB + 16, str(cat)[:14], size=10, anchor="middle", fill="#444")
    return c


def fig_scatter(title, xs, ys, fit=None, xlab="", ylab="", note=""):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if not pairs:
        return None
    xr = (min(p[0] for p in pairs), max(p[0] for p in pairs))
    yr = (min(p[1] for p in pairs), max(p[1] for p in pairs))
    xp = (xr[1] - xr[0]) * 0.05 or 1.0
    yp = (yr[1] - yr[0]) * 0.08 or 1.0
    c, Y, ylo, yhi = _axes(title, yr[0] - yp, yr[1] + yp, xlab, ylab, note)

    def X(v):
        return ML + (v - (xr[0] - xp)) / ((xr[1] + xp) - (xr[0] - xp)) * PW

    _xticks(c, xr[0] - xp, xr[1] + xp, X)
    for x, y in pairs[:4000]:
        c.circle(X(x), Y(y), 2.4, PAL[0], 0.5)
    if fit:
        c.line(X(fit[0]), Y(fit[1]), X(fit[2]), Y(fit[3]), PAL[3], 2.2, "6,4")
    return c


def fig_hist(title, xs, bins=12, xlab="", ylab="count", note=""):
    vals = clean(xs)
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        lo, hi = lo - 0.5, hi + 0.5
    w = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        counts[min(int((v - lo) / w), bins - 1)] += 1
    c, Y, ylo, yhi = _axes(title, 0.0, max(counts) * 1.08, xlab, ylab, note)
    bw = PW / bins
    for i, n in enumerate(counts):
        c.rect(ML + i * bw + 1, Y(n), bw - 2, abs(Y(0) - Y(n)), PAL[0], "#fff", 0.8, 0.85)
    for t in range(bins + 1):
        if t % 2 == 0:
            x = ML + t * bw
            c.line(x, H - MB, x, H - MB + 4, "#666", 1.0)
            c.text(x, H - MB + 16, lbl(lo + t * w, w), size=10, anchor="middle", fill="#444")
    c.text(ML + PW / 2, H - MB + 34, "bin width %s (n=%d)" % (fmt(w, 3), len(vals)),
           size=10, anchor="middle", fill="#666")
    return c


def fig_line(title, xs, ys, xlab="", ylab="", note=""):
    pairs = sorted((x, y) for x, y in zip(xs, ys) if x is not None and y is not None)
    if len(pairs) < 2:
        return None
    xr = (pairs[0][0], pairs[-1][0])
    yr = (min(p[1] for p in pairs), max(p[1] for p in pairs))
    yp = (yr[1] - yr[0]) * 0.1 or 1.0
    c, Y, ylo, yhi = _axes(title, yr[0] - yp, yr[1] + yp, xlab, ylab, note)
    xp = (xr[1] - xr[0]) or 1.0

    def X(v):
        return ML + (v - xr[0]) / xp * PW

    _xticks(c, xr[0], xr[1], X)
    pts = " ".join("%.1f,%.1f" % (X(x), Y(y)) for x, y in pairs[:2000])
    c.p.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.0"/>' % (pts, PAL[0]))
    for x, y in pairs[:2000]:
        c.circle(X(x), Y(y), 2.2, PAL[0], 0.6)
    return c


def png(kind, path, **g):
    """Optional matplotlib rendering of the same plotted values; False when absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    fig = None
    try:
        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=120)
        if kind == "box":
            data = [clean(s) for s in g["series"]]
            try:
                ax.boxplot(data, labels=[str(c) for c in g["cats"]])
            except TypeError:
                ax.boxplot(data, tick_labels=[str(c) for c in g["cats"]])
        elif kind == "bars":
            ax.bar([str(c) for c in g["cats"]], g["vals"], yerr=g.get("errs"),
                   capsize=3, color=PAL[0], alpha=0.9)
        elif kind == "scatter":
            ax.scatter(g["xs"], g["ys"], s=14, alpha=0.6, color=PAL[0])
            f = g.get("fit")
            if f:
                ax.plot([f[0], f[2]], [f[1], f[3]], color=PAL[3], lw=1.6, ls="--")
        elif kind == "hist":
            ax.hist(clean(g["xs"]), bins=g.get("bins", 12), color=PAL[0], alpha=0.8)
        elif kind == "line":
            pairs = sorted((x, y) for x, y in zip(g["xs"], g["ys"])
                           if x is not None and y is not None)
            ax.plot([p[0] for p in pairs], [p[1] for p in pairs], color=PAL[0], lw=1.8)
        else:
            return False
        ax.set_title(g.get("title", ""))
        ax.set_xlabel(g.get("xlab", ""))
        ax.set_ylabel(g.get("ylab", ""))
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(path)
        return True
    except Exception:
        return False
    finally:
        try:
            plt.close(fig)
        except Exception:
            pass
