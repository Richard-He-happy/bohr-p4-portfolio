# -*- coding: utf-8 -*-
"""writing-06 engine (stdlib): number traceability, table series, gap scan, evidence-bound narrative, manuscript assembly."""
import json, re, unicodedata
from pathlib import Path
CAP, MAXB, IMG = 6000, 800, "IMAGE_MATERIAL"
NUMP = re.compile(r"[-+\u2212]?\d+(?:[.,]\d+)*")
UN = ("%", "\u2030", "mg", "g", "kg", "\u00b5g", "\u03bcg", "ng", "mL", "ml", "L", "\u00b5L", "\u03bcL", "nM",
      "\u00b5M", "\u03bcM", "mM", "M", "h", "min", "ms", "s", "d", "wk", "\u00b0C", "K", "nm", "mm", "cm",
      "kDa", "Da", "fold", "x")
URE = re.compile(r"^\s?(" + "|".join(re.escape(u) for u in sorted(UN, key=len, reverse=True)) + r")(?![A-Za-z])")
EXCL = re.compile(r"(fig|figs|figure|table|tab|eq|equation|section|ref|reference|no|#|\u56fe|\u8868|\u5f0f)\s*\.?\s*$", re.I)
FIG = re.compile(r"(Fig(?:ure)?s?\.?\s*\d+[A-Za-z]?|Table\s*\d+[A-Za-z]?|\u56fe\s*\d+[A-Za-z]?|\u8868\s*\d+[A-Za-z]?)")
HINT = re.compile(r"(dose|conc|time|dur|hour|day|week|level|group|treat|temp|batch|\u6d53\u5ea6|\u65f6\u95f4|\u5242\u91cf|\u7ec4\u522b|\u5904\u7406)", re.I)
MEAS = re.compile(r"(pct|percent|rate|ratio|viabil|activ|inhibit|yield|recover|growth|surviv|value|mean|median|response|signal|output|level|content|score|titr|\u6d3b\u529b|\u6291\u5236|\u4ea7\u7387|\u542b\u91cf|\u6570\u503c)", re.I)
DISP = re.compile(r"(^|[\W_])(sd|std|stdev|sem|se|ci|error)([\W_]|$)|(\u6807\u51c6\u5dee|\u8bef\u5dee)", re.I)
NCOL = re.compile(r"(^|[\W_])(n|repl|sample|count)([\W_]|$)|(\u91cd\u590d|\u4f8b\u6570)", re.I)
LIT = re.compile(r"(et al\.|doi:\s*10|\(\d{4}\)|\uff08\d{4}\uff09|\[\d+\])")
UMS = (("pct", "%"), ("percent", "%"), ("um", "\u00b5M"), ("nm", "nM"), ("mm", "mM"), ("mg_ml", "mg/mL"),
       ("ml", "mL"), ("ul", "\u00b5L"), ("hr", "h"), ("h", "h"), ("min", "min"), ("day", "d"), ("fold", "fold"))
Z = {"rh": "{m} \u968f {h} \u7684\u53d8\u5316",
     "r1": "{h} \u53d6 {x0} \u81f3 {x1} {xu}\uff08{n} \u4e2a\u6c34\u5e73\uff09\u65f6\uff0c{m} \u7531 {y0}{mu} \u53d8\u4e3a {y1}{mu}{xr}\u3002",
     "r2": "\u8d8b\u52bf\u5f62\u6001\uff1a{verb}\u3002",
     "r3": "{dh} \u5728 {x} {xu} \u5904\u6700\u5927\uff08{d}\uff09\uff1b\u8bef\u5dee\u68d2\u672a\u5b9a\u4e49\uff1bn = {ns}\u3002",
     "d1a": "\u8bfb\u6570\u53ea\u652f\u6301\u65b9\u5411\u4e0e\u5e45\u5ea6\uff1a\u4e24\u8005\u4f34\u968f\u53d8\u5316\uff0c\u4e0e\u201c\u5b58\u5728\u5173\u8054\u201d\u4e00\u81f4\uff1b\u65e0\u5e72\u9884\u5b9e\u9a8c\uff0c\u4e0d\u63a8\u65ad\u56e0\u679c\u3002",
     "d1b": "\u8bfb\u6570\u975e\u5355\u8c03\uff0c\u53ea\u9648\u8ff0\u5404\u6c34\u5e73\u5b9e\u6d4b\u503c\uff0c\u4e0d\u6982\u62ec\u8d8b\u52bf\u3002",
     "d2": "\u6750\u6599\u672a\u9644\u53ef\u5bf9\u7167\u6587\u732e\uff0c\u4e0d\u4f5c\u4e00\u81f4/\u4e0d\u4e00\u81f4\u6bd4\u8f83\uff1b\u9700\u4f5c\u8005\u8865\u5f15\u6587\u3002",
     "d3": "\u4e0d\u63d0\u673a\u5236\u5047\u8bbe\uff1a\u53ea\u6709\u7ec8\u70b9\u8bfb\u6570\uff0c\u673a\u5236\u89e3\u91ca\u4f1a\u8d85\u51fa\u6570\u636e\uff1b\u68c0\u9a8c\u56e0\u679c\u9700\u5e72\u9884\u7ec4\u4e0e\u9634\u6027\u5bf9\u7167\u3002",
     "lm": "\u65b9\u6cd5\u5c42\uff1a\u4ec5\u6709\u6c47\u603b\u8bfb\u6570\uff0c\u672a\u89c1\u65b9\u6cd5\u4e0e\u5bf9\u7167\uff0c\u7ec4\u95f4\u5dee\u5f02\u4e0d\u80fd\u5f53\u4f5c\u5904\u7406\u6548\u5e94\u3002",
     "ls": "\u7edf\u8ba1\u5c42\uff1a\u65e0\u591a\u91cd\u6bd4\u8f83\u6821\u6b63\u4e0e\u6548\u5e94\u91cf\uff0c\u4e0d\u62a5\u663e\u8457\u6027\u3002",
     "ph": ["\u8bf7\u4f5c\u8005\u786e\u8ba4\u56fe/\u8868\u7f16\u53f7", "\u8bf7\u4f5c\u8005\u8865\u6587\u732e\u5bf9\u7167\u4e0e\u673a\u5236\u8ba8\u8bba"],
     "h1": "\u6570\u636e\u652f\u6301\u5230\u4ec0\u4e48\u7a0b\u5ea6", "h2": "\u4e0e\u5df2\u6709\u8bc1\u636e\u7684\u5173\u7cfb",
     "h3": "\u673a\u5236\u4e0e\u56e0\u679c\u8fb9\u754c", "ttl": "\u7ed3\u679c\u4e0e\u8ba8\u8bba",
     "qres": "\u6750\u6599\u8bb0\u8f7d\uff1a\u201c{q}\u201d\uff08{loc}\uff09\u3002", "qhead": "\u8bfb\u6570\uff08{f}\uff09",
     "notab": "\u65e0\u7ed3\u6784\u5316\u8868\uff1aResults \u4e3a\u9010\u5b57\u5f15\u6587\uff0c\u9700\u6539\u5199\u3002",
     "unn": "\u65e0\u7ed3\u6784\u5316\u8868\uff1a\u8bfb\u6570\u6765\u81ea\u6587\u672c\u5f15\u6587\u3002",
     "v": {"down": "\u5355\u8c03\u4e0b\u964d", "up": "\u5355\u8c03\u4e0a\u5347", "nonmono": "\u975e\u5355\u8c03\u6ce2\u52a8", "flat": "\u57fa\u672c\u6301\u5e73"}}
E = {"rh": "{m} across {h}",
     "r1": "Across {n} levels of {h} ({x0} to {x1} {xu}), {m} moved from {y0}{mu} to {y1}{mu}{xr}.",
     "r2": "Course: {verb}.",
     "r3": "{dh} was largest at {x} {xu} ({d}); error bars undefined; n = {ns}.",
     "d1a": "The readouts support direction and magnitude only: both co-varied, consistent with an association. Without an intervention arm, causation is not inferred.",
     "d1b": "The readouts are non-monotonic, so only measured values are reported and no trend is claimed.",
     "d2": "No comparable literature was supplied, so no consistency comparison is made and no study is cited.",
     "d3": "No mechanism is proposed: endpoint readouts only, so any mechanistic account would exceed the data. Causation would need independent replicates plus an intervention arm; none is present.",
     "lm": "Method level: aggregate readouts only, no methods text or controls, so differences are not a treatment effect.",
     "ls": "Statistics level: no multiplicity correction or effect size, so significance is not claimed.",
     "ph": ["Author to confirm figure/table numbering", "Author to add literature comparison and mechanism"],
     "h1": "What the data support", "h2": "Relation to existing evidence", "h3": "Mechanism and causal boundary",
     "ttl": "Results and Discussion", "qres": "The material reports: \u201c{q}\u201d ({loc}).", "qhead": "Readout {f}",
     "notab": "No structured table: Results are quote-bound readouts needing rewrite.",
     "unn": "No structured table: readouts come from text quotes.",
     "v": {"down": "decreased monotonically", "up": "increased monotonically",
           "nonmono": "changed non-monotonically", "flat": "stayed essentially flat"}}
T = {"zh": Z, "en": E}


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or ""))).strip().casefold()


def cjk(t):
    t = t or ""
    c, l = len(re.findall(r"[\u4e00-\u9fff]", t)), len(re.findall(r"[A-Za-z]", t))
    return c / (c + l) if c + l else 0.0


def numval(raw):
    s = str(raw).replace("\u2212", "-").replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    if s.count(",") and s.count("."):
        s = s.replace(",", "")
    elif s.count(",") == 1:
        s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None


def numbers(text):
    out, t = [], unicodedata.normalize("NFKC", text or "")
    for m in NUMP.finditer(t):
        raw, s, e = m.group(0), m.start(), m.end()
        if s and re.match(r"[A-Za-z\u03b1-\u03c9\u0391-\u03a9]", t[s - 1:s]):
            continue
        if EXCL.search(t[max(0, s - 18):s]):
            continue
        post = t[e:e + 9]
        u = URE.match(post)
        if not u and re.match(r"^\s?[A-Za-z\u03b1-\u03c9]", post):
            continue
        b = re.sub(r"[.,]", "", raw.lstrip("+-"))
        if len(b) == 4 and b[:2] in ("19", "20"):
            continue
        v = numval(raw)
        if v is not None:
            out.append({"raw": raw, "value": v, "unit": u.group(1) if u else ""})
    return out


def fmt(v):
    if v is None:
        return "?"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.4f" % v).rstrip("0").rstrip(".")


def find_block(idx, loc):
    loc = (loc or "").strip()
    hit = next((b for b in idx.get("blocks", []) if b["loc"] == loc), None)
    if hit:
        return hit
    m = re.match(r"^(.*?)#(\D*)(\d+)$", loc)
    if not m:
        return next((b for b in idx.get("blocks", []) if b["file"] == loc), None)
    f, tag, n = m.group(1).split("/")[-1], m.group(2), int(m.group(3))
    for b in idx.get("blocks", []):
        bm = re.match(r"^(.*?)#(\D*)(\d+)$", b["loc"])
        if bm and bm.group(2) == tag and int(bm.group(3)) == n and bm.group(1).split("/")[-1] == f:
            return b
    return None


def quote_status(idx, quote, loc):
    q = norm(quote)
    if not q:
        return "empty", None
    b = find_block(idx, loc) if loc else None
    if b and q in norm(b["text"]):
        return "exact", b["loc"]
    hit = next((x["loc"] for x in idx.get("blocks", []) if q in norm(x["text"])), None)
    if hit:
        return "misplaced", hit
    per = {}
    for x in idx.get("blocks", []):
        per.setdefault(x["file"], []).append(x["text"])
    for f, tx in per.items():
        if q in norm(" ".join(tx)):
            return "span", f
    return "notfound", None


def cand_quote(idx, val, limit=2):
    if val is None:
        return []
    out = []
    for b in idx.get("blocks", []):
        if any(abs(n["value"] - val) < 1e-9 for n in numbers(b["text"])):
            out.append(b["loc"] + " :: " + b["text"][:130].replace("\n", " "))
            if len(out) >= limit:
                break
    return out


def unit_from_header(h):
    h = str(h or "").strip()
    m = re.search(r"%|\u2030", h)
    if m:
        return m.group(0)
    for suf, u in UMS:
        if h.lower() == suf or re.search(r"[_\-]" + suf + r"$", h, re.I):
            return u
    m = re.search(r"\((\u00b5M|\u03bcM|nM|mM|mg/mL|%|h|min|s|d|\u00b0C)\)", h)
    return m.group(1) if m else ""


def series(tb):
    hd, rows = tb.get("header") or [], tb.get("rows") or []
    if not hd or not rows:
        return None
    cols = []
    for j, h in enumerate(hd):
        vals = [r[j] for r in rows if j < len(r) and str(r[j]).strip()]
        ok = bool(vals) and len([v for v in vals if numval(v) is not None]) >= max(1, int(0.8 * len(vals)))
        cols.append({"j": j, "head": h, "ok": ok, "unit": unit_from_header(h)})
    num = [c for c in cols if c["ok"] and c["head"]]
    if not num:
        return None
    hint = next((c for c in num if HINT.search(c["head"])), None)
    disp = next((c for c in num if DISP.search(c["head"])), None)
    ncol = next((c for c in num if NCOL.search(c["head"].strip())), None)
    meas = next((c for c in num if MEAS.search(c["head"]) and c not in (hint, disp, ncol)), None) or \
        next((c for c in num if c not in (hint, disp, ncol)), None)
    if not meas:
        return None
    locs, pts = tb.get("locs") or [], []
    for i, row in enumerate(rows):
        def g(c):
            try:
                return numval(row[c["j"]])
            except Exception:
                return None
        y = g(meas)
        if y is None:
            continue
        x = g(hint) if hint else None
        pts.append({"x": x if x is not None else float(i + 1), "y": y, "d": g(disp) if disp else None,
                    "n": g(ncol) if ncol else None, "loc": locs[i] if i < len(locs) else None})
    return {"pts": pts, "meas": meas, "hint": hint, "disp": disp, "ncol": ncol} if pts else None


def mono(ys):
    if len(ys) < 2:
        return "flat"
    if all(b > a for a, b in zip(ys, ys[1:])):
        return "up"
    return "down" if all(b < a for a, b in zip(ys, ys[1:])) else "nonmono"


def xref_for(idx, tb):
    names = [n for n in (str(h).split("_")[0].lower() for h in (tb.get("header") or [])) if len(n) > 3]
    out = []
    for b in idx.get("blocks", []):
        if b["file"] != tb.get("rel") and any(n in b["text"].lower() for n in names):
            out += [m.group(1) for m in FIG.finditer(b["text"]) if m.group(1) not in out]
    return out[:2]


def gaps(idx):
    txt = "\n".join(b["text"] for b in idx.get("blocks", []) if b["file"] != idx.get("case_rel"))
    zh, g = cjk(txt) > 0.15, []

    def a(c, z, e):
        g.append({"code": c, "limit": z if zh else e})

    if not re.search(r"\u00b1|\bSD\b|\bSEM\b|\bCI\b|error bar|\u8bef\u5dee|\u6807\u51c6\u5dee", txt, re.I):
        a("no_errorbar", "\u8bef\u5dee\u68d2\u672a\u5b9a\u4e49\uff1a\u4e0d\u89e3\u8bfb\u79bb\u6563\u5ea6\u3002", "Error bars undefined: dispersion not interpreted.")
    if not re.search(r"p\s*[<>=]\s*0?\.\d+|ANOVA|t-?test|Mann|Kruskal|Wilcoxon", txt, re.I):
        a("no_stats", "\u65e0\u68c0\u9a8c/p \u503c\uff1a\u53ea\u63cf\u8ff0\u3002", "No test/p: descriptive only.")
    if not re.search(r"\bn\s*=\s*\d+", txt, re.I):
        a("no_n", "\u672a\u7ed9 n\uff1a\u968f\u673a\u8bef\u5dee\u4e0d\u53ef\u8bc4\u4f30\u3002", "No n: random error not assessable.")
    if any(m["kind"] == "image" for m in idx.get("materials", [])):
        a("figure_visual", "\u56fe\u4e3a\u4f4d\u56fe\uff1a\u8bfb\u6570\u4e3a\u76ee\u89c6\u8fd1\u4f3c\uff0c\u9700\u6807\u201c\u7ea6\u201d\u3002", "Raster figure: approximate readouts.")
    if any(m.get("quality") in ("low", "unreadable", "visual_only") for m in idx.get("materials", [])):
        a("low_text", "\u63d0\u53d6\u8d28\u91cf\u4f4e\uff1a\u5f15\u7528\u524d\u5bf9\u7167\u539f\u9875\u3002", "Parsed poorly: verify before quoting.")
    if not LIT.search(txt):
        a("no_lit", "\u672a\u9644\u6587\u732e\uff1a\u4e0d\u505a\u4e00\u81f4\u6027\u5224\u65ad\u3002", "No literature: no consistency claims.")
    return g


def human(h):
    s = re.sub(r"[_\-](pct|percent|um|nm|mm|hr|min|d|sd|std|sem|se|ci|n|h)$", "", str(h or ""), flags=re.I)
    s = s.replace("_", " ").strip()
    return s.upper() if 0 < len(s) <= 3 else s


def narrative(idx):
    zh = cjk(" ".join(b["text"] for b in idx["blocks"] if b["file"] != idx.get("case_rel"))) > 0.15
    t = T["zh" if zh else "en"]
    res, disc, ev, der, d = [], [], [], [], "flat"
    pend, unc = list(t["ph"]), []
    tabs = [x for x in idx.get("tables") or [] if x.get("rows") and x.get("header")]
    for tb in tabs[:3]:
        s = series(tb)
        if not s:
            continue
        pts, ys = s["pts"], [p["y"] for p in s["pts"]]
        mh = human(s["meas"]["head"])
        hu = human(s["hint"]["head"]) if s["hint"] else ("row order" if not zh else "\u884c\u5e8f")
        mu, xu = s["meas"]["unit"], (s["hint"]["unit"] if s["hint"] else "")
        d, xr = mono(ys), xref_for(idx, tb)
        ps = [t["r1"].format(m=mh, h=hu, n=len(pts), y0=fmt(ys[0]), y1=fmt(ys[-1]), mu=mu, x0=fmt(pts[0]["x"]),
                             x1=fmt(pts[-1]["x"]), xu=xu, xr=(" (%s)" % "; ".join(xr)) if xr else ""),
              t["r2"].format(verb=t["v"][d])]
        if s["disp"] and all(p["d"] is not None for p in pts):
            hi = max(pts, key=lambda p: p["d"] or 0)
            ps.append(t["r3"].format(dh=human(s["disp"]["head"]), x=fmt(hi["x"]), xu=xu, d=fmt(hi["d"]),
                                     ns="/".join(sorted({fmt(p["n"]) for p in pts if p["n"] is not None})) or "-"))
        res.append({"heading": t["rh"].format(m=mh, h=hu), "xref": xr, "paragraphs": ps})
        for p in pts:
            b = find_block(idx, p["loc"]) if p["loc"] else None
            if b:
                ev.append({"id": "e%d" % (len(ev) + 1), "quote": b["text"][:300], "locator": p["loc"]})
        if ys[0]:
            der.append({"value": fmt(ys[-1] - ys[0]), "formula": "%s-%s" % (fmt(ys[-1]), fmt(ys[0])),
                        "note": "endpoint change of %s" % mh})
    if not res:
        for b in [x for x in idx["blocks"] if x["file"] != idx.get("case_rel") and numbers(x["text"])
                  and not x["text"].startswith(IMG)][:6]:
            res.append({"heading": t["qhead"].format(f=b["file"].split("/")[-1]), "xref": [],
                        "paragraphs": [t["qres"].format(q=b["text"][:300], loc=b["loc"])]})
            ev.append({"id": "e%d" % (len(ev) + 1), "quote": b["text"][:300], "locator": b["loc"]})
        if res:
            pend.append(t["notab"])
            unc.append(t["unn"])
    for k, hk in (("d1a" if d in ("up", "down") else "d1b", "h1"), ("d2", "h2"), ("d3", "h3")):
        disc.append({"heading": t[hk], "xref": [], "paragraphs": [t[k]]})
    return ({"title": t["ttl"], "language": "zh" if zh else "en", "results": res, "discussion": disc,
             "limitations": [x["limit"] for x in gaps(idx)] + [t["lm"], t["ls"]],
             "evidence": [e for e in ev if e.get("quote")], "derived": der,
             "preserved_facts": [{"fact": "readout @%s" % e["locator"], "quote": e["quote"], "locator": e["locator"]}
                                 for e in ev if e.get("quote")][:20],
             "changes": [], "pending_human": pend, "uncertainty": unc}, gaps(idx))


def assemble(d, L):
    """Markdown manuscript: numbered Results / Discussion sections, then limitations."""
    lang = d.get("language") or ("zh" if cjk(json.dumps(d, ensure_ascii=False)) > 0.15 else "en")
    out, part = ["# %s" % ((d.get("title") or "").strip() or L["ttl"][lang]), ""], 0
    for key, lab in (("results", L["results"][lang]), ("discussion", L["discussion"][lang])):
        secs = [s for s in (d.get(key) or []) if isinstance(s, dict)]
        if not secs:
            continue
        part += 1
        out += ["## %d. %s" % (part, lab), ""]
        for j, sec in enumerate(secs, 1):
            h = re.sub(r"^\d+(?:\.\d+)*[.\u3001)]?\s*", "", re.sub(r"^\s*#{1,6}\s*", "", str(sec.get("heading") or "")).strip()) or "Section"
            out += ["### %d.%d %s" % (part, j, h), ""]
            ps = [str(p).strip() for p in (sec.get("paragraphs") or []) if str(p).strip()]
            for p in ps:
                out += [p, ""]
            xr = [str(x) for x in (sec.get("xref") or []) if str(x).strip()]
            if xr and not all(x in " ".join(ps) for x in xr):
                out += ["(%s)" % "; ".join(xr), ""]
    lims = [str(x).strip() for x in (d.get("limitations") or []) if str(x).strip()]
    if lims:
        out += ["### %s" % L["limits"][lang], ""] + ["- %s" % x for x in lims] + [""]
    return "\n".join(out).rstrip() + "\n", lang


def digest(idx, cid, cerr):
    print("== INDEX %s ==\ncase_id %s | %s | contract(%d): %s" % (idx.get("input_root"), cid, cerr or "loaded",
          len(idx.get("contract") or []), ", ".join(idx.get("contract") or [])))
    for m in idx.get("materials", []):
        locs = [b["loc"] for b in idx["blocks"] if b["file"] == m["rel"]]
        print("%-26s %-5s %4d %-10s %s" % (m["rel"][:26], m["kind"], m["blocks"], m["quality"],
                                           ("%s..%s" % (locs[0], locs[-1])) if locs else "-"))
    for tb in idx.get("tables", []):
        s = series(tb)
        print("[table] %s: %s (%d rows)" % (tb["rel"], " | ".join(tb["header"]), len(tb["rows"])))
        for b in [x for x in idx["blocks"] if x["file"] == tb["rel"]][:12]:
            print("   %s :: %s" % (b["loc"], b["text"][:200]))
    for b in [x for x in idx["blocks"] if x["file"] != idx.get("case_rel") and FIG.search(x["text"])][:4]:
        print("[caption] %s :: %s" % (b["loc"], b["text"][:170].replace("\n", " ")))
    for g in gaps(idx):
        print("[gap] %s: %s" % (g["code"], g["limit"]))
    print("NEXT: write work/draft.json (schema in SKILL.md), run check, then build.")




def read_text(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return b.decode(e)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def load_json(p):
    if not p:
        return None, "no path"
    try:
        return json.loads(read_text(p)), None
    except FileNotFoundError:
        return None, "not found: %s" % Path(p).name
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def kind_of(p):
    e = Path(p).suffix.lower()
    try:
        h = Path(p).open("rb").read(8)
    except Exception:
        h = b""
    if h.startswith(b"%PDF"):
        return "pdf"
    if h[:4] in (b"\x89PNG", b"GIF8") or e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".svg", ".webp"):
        return "image"
    if e in (".csv", ".tsv"):
        return e[1:]
    return "text" if e in (".md", ".txt", ".json", ".tex", ".yml", ".yaml") else "binary"
