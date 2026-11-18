"""vizlib.py - stdlib-only SVG chart engine + statistics for skill sciviz-figure-forge.

viz_skill.py builds a *render plan* (plain data, SKILL.md §6); _marks() flattens it to a mark
list and render_svg() draws a real vector SVG whose user unit is 1 mm (true print size).
Stdlib only; raster preview is left to the platform renderer.
"""
import math
import unicodedata
from pathlib import Path

PT = 25.4 / 72.0
FONT = ("'Noto Sans CJK SC','Source Han Sans SC','WenQuanYi Micro Hei','SimHei',"
        "Helvetica,Arial,sans-serif")
PROFILES = {"nature": (89.0, 183.0, 7.0, .25, .5), "science": (55.0, 120.0, 7.0, .25, .5),
            "cell": (85.0, 174.0, 8.0, .35, .75), "ieee": (88.9, 181.0, 8.0, .25, .6),
            "report": (160.0, 170.0, 9.0, .3, .6), "screen": (180.0, 180.0, 10.0, .3, .7)}
PROFILES = {k: dict(zip(("single", "double", "fs", "axis", "data"), v)) for k, v in PROFILES.items()}
PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#666666")
HATCHES = ("", "h1", "h2")
PATTERNS = {
    "h1": '<pattern id="h1" width="1.4" height="1.4" patternUnits="userSpaceOnUse" '
          'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="1.4" stroke="#000" '
          'stroke-width="0.16"/></pattern>',
    "h2": '<pattern id="h2" width="1.5" height="1.5" patternUnits="userSpaceOnUse">'
          '<circle cx="0.75" cy="0.75" r="0.26" fill="#000"/></pattern>',
    }


def fmt_num(v, sig=4):
    """Deterministic compact number text; plain notation between 1e-3 and 1e5."""
    if v is None:
        return "NA"
    if isinstance(v, bool):
        return "true" if v else "false"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:
        return "NA"
    if f in (float("inf"), float("-inf")):
        return "inf" if f > 0 else "-inf"
    if f == 0:
        return "0"
    a = abs(f)
    if a >= 1e5 or a < 1e-3:
        return (f"%.{max(sig - 1, 1)}e" % f).replace("e+", "e").replace("e0", "e")
    s = f"%.{max(0, min(6, sig - 1 - int(math.floor(math.log10(a)))))}f" % f
    return (s.rstrip("0").rstrip(".") if "." in s else s) or "0"


def tlen(s, size=7.0):
    """Estimated rendered text width in mm (CJK = 1 em); drives margins and label rotation."""
    w = 0.0
    for ch in str(s):
        w += (1.0 if unicodedata.east_asian_width(ch) in "WF" else
              .30 if ch in "ijlt.,;:!|'`" else .56 if ch.isdigit() else
              .68 if ch.isupper() else .54)
    return w * size * PT


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def nice_ticks(lo, hi, n=5):
    lo, hi = float(lo), float(hi)
    if not (lo == lo and hi == hi) or hi <= lo:
        return ([lo] if lo == lo else [0.0]), None
    raw = (hi - lo) / max(1, n - 1)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw * .999), 10 * mag)
    start, out, k = math.ceil(lo / step - 1e-9) * step, [], 0
    while start + k * step <= hi + 1e-9 * max(1., abs(step)) and k < 40:
        out.append(round(start + k * step, 10))
        k += 1
    return (out or [lo, hi]), step


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in c)


def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4


def rel_lum(h):
    r, g, b = (_lin(v) for v in hex2rgb(h))
    return .2126 * r + .7152 * g + .0722 * b


def contrast(a, b="#FFFFFF"):
    x, y = rel_lum(a), rel_lum(b)
    return (max(x, y) + .05) / (min(x, y) + .05)


CVD = {"deutan": ((.367, .861, -.228), (.280, .673, .047), (-.012, .043, .969)),
       "protan": ((.152, 1.053, -.205), (.115, .786, .099), (-.004, -.048, 1.052))}


def simulate_cvd(h, kind="deutan"):
    """Machado 2009 severity-1.0 dichromacy simulation in linear RGB (deutan / protan)."""
    r, g, b = (_lin(v) for v in hex2rgb(h))
    m = CVD[kind]
    out = []
    for i in range(3):
        v = max(0.0, min(1.0, m[i][0] * r + m[i][1] * g + m[i][2] * b))
        out.append((12.92 * v if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055) * 255)
    return rgb2hex(out)


def palette(n, base=PALETTE):
    return [base[i % len(base)] for i in range(max(1, n))]


def hatch_for(i):
    return HATCHES[i % len(HATCHES)]


def accessibility(series):
    """Measured grayscale / colour-vision / white-background separability of the encoding."""
    out = {"grayscale_ok": True, "cvd_ok": True, "contrast_ok": True, "worst_pair": None,
           "thresholds": {"luminance_delta": .10, "cvd_delta": .15, "bg_contrast": 3.0}}
    worst = 1.0
    for i, a in enumerate(series):
        out["contrast_ok"] &= contrast(a["color"]) >= 3.0
        for b in series[i + 1:]:
            dl = abs(rel_lum(a["color"]) - rel_lum(b["color"]))
            tex = bool(a.get("hatch")) and bool(b.get("hatch")) and a["hatch"] != b["hatch"]
            cv = min(math.dist([_lin(c) for c in hex2rgb(simulate_cvd(a["color"], k))],
                               [_lin(c) for c in hex2rgb(simulate_cvd(b["color"], k))])
                     for k in CVD)
            out["grayscale_ok"] &= dl >= .10 or tex
            out["cvd_ok"] &= cv >= .15 or tex
            if min(dl, cv) < worst:
                worst = min(dl, cv)
                out["worst_pair"] = {"a": a["name"], "b": b["name"], "delta_luminance": round(dl, 4),
                                     "cvd_delta_min": round(cv, 4), "texture_differs": tex}
    out["pass"] = bool(out["grayscale_ok"] and out["cvd_ok"] and out["contrast_ok"])
    return out


# ------------------------------------------------------------------ statistics
def mean(v):
    return sum(v) / len(v) if v else None


def var(v):
    if len(v) < 2:
        return None
    m = mean(v)
    return sum((x - m) ** 2 for x in v) / (len(v) - 1)


def sd(v):
    s = var(v)
    return None if s is None else math.sqrt(s)


def quantile(sv, q):
    if not sv:
        return None
    if len(sv) == 1:
        return float(sv[0])
    pos = (len(sv) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (pos - lo)


def describe(v):
    v = sorted(float(x) for x in v)
    if not v:
        return {"n": 0}
    m, s = mean(v), sd(v)
    q1, q2, q3 = quantile(v, .25), quantile(v, .5), quantile(v, .75)
    return {"n": len(v), "mean": m, "sd": s, "se": None if s is None else s / math.sqrt(len(v)),
            "median": q2, "q1": q1, "q3": q3, "iqr": q3 - q1, "min": v[0], "max": v[-1]}


def _betacf(a, b, x):
    tiny, eps, qab, qap, qam = 1e-300, 3e-14, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularised incomplete beta I_x(a,b) via Lentz continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    fr = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
                  a * math.log(x) + b * math.log(1 - x))
    return (fr * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2)
            else 1.0 - fr * _betacf(b, a, 1 - x) / b)


def t_cdf(t, df):
    if not df or df <= 0:
        return None
    p = .5 * betainc(df / 2.0, .5, df / (df + t * t))
    return 1.0 - p if t > 0 else p


def t_ppf(p, df):
    """Inverse Student-t CDF by deterministic bisection."""
    if not df or df <= 0 or not 0 < p < 1:
        return None
    lo, hi = -60.0, 60.0
    for _ in range(120):
        mid = (lo + hi) / 2
        if (t_cdf(mid, df) or 0.0) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ci95(v):
    d = describe(v)
    q = t_ppf(.975, d["n"] - 1) if d["n"] >= 2 else None
    return None if not q or d["se"] is None else q * d["se"]


def welch(a, b):
    """Welch two-sample t-test; returns nulls (never a fabricated p) when not computable."""
    n1, n2 = len(a), len(b)
    r = {"test": "welch_t", "n1": n1, "n2": n2, "t": None, "df": None, "p": None}
    if n1 < 2 or n2 < 2:
        r["note"] = "n<2, test not computed"
        return r
    v1, v2 = var(a), var(b)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        r["note"] = "zero variance, test not computed"
        return r
    den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = (v1 / n1 + v2 / n2) ** 2 / den if den > 0 else n1 + n2 - 2
    t = (mean(a) - mean(b)) / se
    r.update({"t": t, "df": df, "p": 2 * (1 - t_cdf(abs(t), df)), "mean1": mean(a),
              "mean2": mean(b), "diff": mean(a) - mean(b)})
    return r


def ols(x, y):
    """OLS with slope SE, R2 and two-sided p (t distribution, df = n-2)."""
    n = len(x)
    out = {"method": "ordinary_least_squares", "n": n, "slope": None, "intercept": None,
           "r2": None, "se_slope": None, "p": None}
    if n < 3:
        out["note"] = "n<3, regression not computed"
        return out
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        out["note"] = "x has zero variance"
        return out
    sl = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    ic = my - sl * mx
    sse = sum((b - (ic + sl * a)) ** 2 for a, b in zip(x, y))
    sst = sum((b - my) ** 2 for b in y)
    out.update({"slope": sl, "intercept": ic, "r2": (1 - sse / sst) if sst > 0 else None})
    if sst > 0:
        se = math.sqrt(sse / (n - 2) / sxx) if sse > 0 else 0.0
        out["se_slope"] = se
        if se > 0:
            out["t"] = sl / se
            out["p"] = 2 * (1 - t_cdf(abs(out["t"]), n - 2))
        else:
            out["note"] = "zero residual variance"
    return out


# ------------------------------------------------------------------ SVG primitives
_B, _W, _H = [], 100.0, 75.0


def _new(w, h):
    global _B, _W, _H
    _B, _W, _H = [], float(w), float(h)


def _r(x, y, w, h, fill="none", stroke="none", sw=.2):
    _B.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{max(0., w):.3f}" height="{max(0., h):.3f}" '
              f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.3f}"/>')


def _l(x1, y1, x2, y2, stroke="#000", sw=.25):
    _B.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{stroke}" '
              f'stroke-width="{sw:.3f}"/>')


def _p(pts, stroke="#000", sw=.5, fill="none"):
    _B.append('<polyline points="%s" fill="%s" stroke="%s" stroke-width="%.3f" '
              'stroke-linejoin="round"/>' % (" ".join(f"{x:.3f},{y:.3f}" for x, y in pts), fill,
                                             stroke, sw))


def _c(cx, cy, r, fill="#000", stroke="none", sw=.2):
    _B.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" fill="{fill}" '
              f'stroke="{stroke}" stroke-width="{sw:.3f}"/>')


def _t(x, y, s, size=7.0, anchor="start", fill="#000", rot=None, weight="normal"):
    tr = f' transform="rotate({rot:.2f} {x:.3f} {y:.3f})"' if rot else ""
    _B.append(f'<text x="{x:.3f}" y="{y:.3f}" font-family="{FONT}" font-size="{size * PT:.3f}" '
              f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}"{tr}>{esc(s)}</text>')


def _doc():
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{_W:.2f}mm" height="{_H:.2f}mm" viewBox="0 0 {_W:.2f} {_H:.2f}" version="1.1">'
            '<desc>SciViz; 1 unit = 1 mm; labels are live text</desc>\n<defs>'
            f'{"".join(PATTERNS.values())}</defs>\n<g>{"".join(_B)}</g>\n</svg>\n')


def _sc(lo, hi, p0, p1, log=False):
    if log:
        lo, hi = math.log10(max(lo, 1e-300)), math.log10(max(hi, 1e-300))

    def f(v):
        v = math.log10(max(float(v), 1e-300)) if log else float(v)
        return (p0 + p1) / 2 if hi == lo else p0 + (v - lo) / (hi - lo) * (p1 - p0)
    return f


def _geom(plan, W, H, fs):
    """Margins from measured text, scales, tick label pairs and legend rows."""
    kind, xt, yt = plan["kind"], plan["x"], plan["y"]
    ylim = yt.get("lim") or [0, 1]
    xp = ([(float(v), str(l)) for v, l in xt["tick_labels"]] if xt.get("tick_labels") else
          [(v, fmt_num(v)) for v in nice_ticks(xt["lim"][0], xt["lim"][1], 5)[0]]
          if xt["type"] == "numeric" else [(i, str(l)) for i, l in enumerate(xt["categories"])])
    yp = [(v, fmt_num(v)) for v in nice_ticks(ylim[0], ylim[1], plan.get("n_yticks", 5))[0]]
    rot = float(plan.get("x_label_rot") or 0)
    ml = 4.6 + (3.6 if yt.get("label") else 0) + max([tlen(l, fs) for _, l in yp] + [3.0])
    ay0 = 3.0 + (4.6 if plan.get("title") else 0)
    leg = ([{"name": s["name"], "color": s["color"], "hatch": s.get("hatch", "")}
            for s in plan.get("series") or []] if plan.get("legend") and plan.get("series") else [])
    row, cur = 1, 0.0
    for it in leg:
        w = 7.2 + tlen(it["name"], fs)
        if cur + w > W - 6.0 and cur > 0:
            row, cur = row + 1, 0.0
        cur += w
    legh = row * (fs * PT + 1.4) + .8 if leg else 0.0
    xth = max([tlen(l, fs) for _, l in xp] + [3.0]) if rot else 2.4
    bot = 1.0 + legh + (4.0 if xt.get("label") else 0) + (xth * .78 + 1.2 if rot else 2.8)
    ax0, aw, ah = ml, max(12.0, W - ml - 3.0), max(12.0, H - ay0 - bot)
    return {"xp": xp, "yp": yp, "rot": rot, "ax0": ax0, "ay0": ay0, "aw": aw, "ah": ah, "leg": leg,
            "legh": legh, "ybase": ay0 + ah, "xlabel_y": H - 1.2 - legh, "ylim": ylim,
            "sx": (_sc(xt["lim"][0], xt["lim"][1], ax0, ax0 + aw, xt.get("log"))
                   if xt["type"] == "numeric" else _sc(-.5, max(1, len(xp) - .5), ax0, ax0 + aw)),
            "sy": _sc(ylim[0], ylim[1], ay0 + ah, ay0, yt.get("log"))}


def _marks(plan):
    """Flatten the plan to marks: bar / pt / ln / box tuples in data coordinates."""
    k, out = plan["kind"], []
    if k == "bar":
        for b in plan.get("bars", []):
            out.append(("bar", b["xi"], b.get("si", 0), b["value"], b.get("err"), b.get("base", 0.)))
    else:
        for q in plan.get("points", []):
            out.append(("pt", q["x"], q["y"], q.get("si", 0), float(q.get("r", 1.0)),
                        q.get("filled", True)))
        for lg in plan.get("lines", []):
            out.append(("ln", lg["pts"], lg.get("si", 0)))
        for bx in plan.get("boxes", []):
            out.append(("box", bx["xi"], bx))
    return out


def render_svg(plan, path, profile="report"):
    """Draw the plan to a real vector SVG; returns layout facts used by consistency checks."""
    prof = PROFILES.get(profile, PROFILES["report"])
    W, H = plan["size_mm"]
    fs, axis, dat = float(plan.get("font_pt") or prof["fs"]), prof["axis"], prof["data"]
    kind, series = plan["kind"], plan.get("series") or []
    _new(W, H)
    g = _geom(plan, W, H, fs)
    xp, yp, sx, sy = g["xp"], g["yp"], g["sx"], g["sy"]
    ax0, ay0, aw, ah, ybase, ylim = g["ax0"], g["ay0"], g["aw"], g["ah"], g["ybase"], g["ylim"]
    xt, yt = plan["x"], plan["y"]
    col = lambda i: (series[i] if series else {"color": PALETTE[0], "hatch": ""})

    if plan.get("grid", True):
        for v, _lb in yp:
            if ay0 - .1 <= sy(v) <= ay0 + ah + .1:
                _l(ax0, sy(v), ax0 + aw, sy(v), "#E6E6E6", .15)
    _l(ax0, ybase, ax0 + aw, ybase, "#000", axis)
    _l(ax0, ay0, ax0, ybase, "#000", axis)
    for v, lab in yp:
        if ay0 - .1 <= sy(v) <= ay0 + ah + .1:
            _l(ax0 - 1.0, sy(v), ax0, sy(v), "#000", axis)
            _t(ax0 - 1.5, sy(v) + fs * PT * .35, lab, fs, "end")
    for i, (v, lab) in enumerate(xp):
        x = sx(v) if xt["type"] == "numeric" else sx(i)
        if ax0 - .6 <= x <= ax0 + aw + .6:
            _l(x, ybase, x, ybase + 1.0, "#000", axis)
            if g["rot"]:
                _t(x, ybase + 1.6, lab, fs, "end", rot=-abs(g["rot"]))
            else:
                _t(x, ybase + 1.0 + fs * PT * .9, lab, fs, "middle")
    gw, ns, bw = .78, max(1, len(series)), .78 / max(1, len(series))
    for mk in _marks(plan):
        if mk[0] == "bar":
            _, i, si, val, e, base = mk
            s = col(si)
            if plan.get("stacked"):
                x, w, xc, y0 = sx(i - gw / 2), sx(i + gw / 2) - sx(i - gw / 2), sx(i), sy(base)
            else:
                x = sx(i - gw / 2 + si * bw)
                w = (sx(i - gw / 2 + (si + 1) * bw) - x) * .92
                xc = sx(i - gw / 2 + (si + .5) * bw)
                y0 = sy(0) if ylim[0] <= 0 <= ylim[1] else ybase
            y1 = sy(val)
            _r(x, min(y0, y1), w, abs(y0 - y1), s["color"], "#000", axis * .8)
            if s.get("hatch"):
                _r(x, min(y0, y1), w, abs(y0 - y1), f"url(#{s['hatch']})", "none", 0)
            if e:
                _l(xc, sy(val - e), xc, sy(val + e), "#000", dat * .9)
                for yy in (sy(val + e), sy(val - e)):
                    _l(xc - .7, yy, xc + .7, yy, "#000", dat * .9)
        elif mk[0] == "pt":
            _, px, py, si, r, filled = mk
            if ax0 - .6 <= sx(px) <= ax0 + aw + .6:
                _c(sx(px), sy(py), r, col(si)["color"] if filled else "#FFF", col(si)["color"], .25)
        elif mk[0] == "ln":
            _, pts, si = mk
            if pts:
                _p([(sx(q[0]), sy(q[1])) for q in pts], col(si)["color"], dat)
                if not plan.get("fit_only"):
                    for q in pts:
                        _c(sx(q[0]), sy(q[1]), .8, col(si)["color"], "#FFF", .2)
        elif mk[0] == "box":
            _, xi, bx = mk
            x, w = sx(xi), min(6.0, aw / max(1, len(plan.get("boxes", []))) * .5)
            _r(x - w / 2, sy(bx["q3"]), w, abs(sy(bx["q1"]) - sy(bx["q3"])), "#FFF", "#000", axis)
            _l(x - w / 2, sy(bx["median"]), x + w / 2, sy(bx["median"]), "#000", dat)
            _l(x, sy(bx["q3"]), x, sy(bx["whisker_hi"]), "#000", axis)
            _l(x, sy(bx["q1"]), x, sy(bx["whisker_lo"]), "#000", axis)
            for v in (bx["whisker_hi"], bx["whisker_lo"]):
                _l(x - 1.4, sy(v), x + 1.4, sy(v), "#000", axis)
            for f in bx.get("fliers", []):
                _c(x, sy(f), .45, "#000")
    dy = 0.0
    for sg in plan.get("sig", []):
        x1, x2, y = sx(sg["i"]), sx(sg["j"]), sy(sg["top"]) - 1.6 - dy
        _p([(x1, y + 1.4), (x1, y), (x2, y), (x2, y + 1.4)], "#000", axis)
        _t((x1 + x2) / 2, y - .7, sg.get("label", "p<0.05"), fs * .95, "middle")
        dy += 3.4
    for an in plan.get("annotations", []):
        _t(ax0 + aw - 1.5, ay0 + 1.6 + an.get("dy", 0.), an["text"], fs * .95, "end")
    if xt.get("label"):
        _t(ax0 + aw / 2, g["xlabel_y"],
           xt["label"] + (f" ({xt['unit']})" if xt.get("unit") else ""), fs, "middle")
    if yt.get("label"):
        _t(1.8, ay0 + ah / 2, yt["label"] + (f" ({yt['unit']})" if yt.get("unit") else ""), fs,
           "middle", rot=-90)
    if plan.get("title"):
        _t(W / 2, 4.2, plan["title"], fs, "middle", weight="bold")
    if g["leg"]:
        x, y = 3.0, H - g["legh"] + 1.5
        for it in g["leg"]:
            w = 7.2 + tlen(it["name"], fs)
            if x + w > W - 3.0:
                x, y = 3.0, y + fs * PT + 1.4
            _r(x, y - 1.3, 3.0, 2.1, it["color"], "#000", axis * .7)
            if it.get("hatch"):
                _r(x, y - 1.3, 3.0, 2.1, f"url(#{it['hatch']})", "none", 0)
            _t(x + 3.8, y + .4, it["name"], fs)
            x += w
    data = _doc()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)
    return {"path": str(path), "format": "svg", "size_mm": [W, H], "font_pt": fs, "axis_mm": axis,
            "data_mm": dat, "bytes": len(data.encode("utf-8")), "legend_items": len(g["leg"]),
            "elements": len(_B), "profile": profile, "x_tick_labels": [l for _, l in xp],
            "y_tick_labels": [l for _, l in yp],
            "axes_box_mm": [round(ax0, 2), round(ay0, 2), round(aw, 2), round(ah, 2)]}
