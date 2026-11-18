"""toolkit.py - stdlib-only helpers for source_value_chart: readers, workorder parsing, SVG
primitives, PNG/PDF probes, export chains, checks."""
import csv, io, json, math, os, re, shutil, struct, subprocess, zipfile, zlib
from pathlib import Path
from xml.sax.saxutils import escape

NULL = {"", "na", "n/a", "nan", "null", "none", "-", "--", "—", "–", "nd", "n.d", "n.d.", "#n/a",
        "?", "not reported", "nr"}
CENS = re.compile(r"^\s*[<>]\s*[-+]?\d")
CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3040-\u30ff]")
PAL = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#8C6D1F", "#333333"]
MARK = ["o", "s", "^", "D", "v", "P", "X", "*"]
STY = {"default": (9., 7., 1., .9, .4, .18, .12, 11.), "journal": (8., 6.5, .9, .8, .35, .15, .1, 9.),
       "nature": (7., 6., .8, .7, .3, .12, .08, 8.), "thesis": (10.5, 8.5, 1.1, 1., .5, .22, .15, 12.),
       "presentation": (13., 10., 1.4, 1.2, .6, .26, .18, 16.)}
ERRH = re.compile(r"(^|[ _-])(sd|s\.d\.|sem|se|err|error|ci95|ci|std|stdev)([ _-]|$)|(_sd|_sem|_err|_ci)$", re.I)
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

def has_cjk(t):
    return bool(CJK.search(t or ""))

def style_for(n):
    k = (n or "").lower()
    key = next((x for x in STY if x in k), "default")
    f, s, lw, axl, gl, bg, gg, ti = STY[key]
    return dict(f=f, s=s, lw=lw, axl=axl, gl=gl, bg=bg, gg=gg, ti=ti, name=key)

def parse_number(raw):
    if raw is None or str(raw).strip().lower() in NULL:
        return None, "nan"
    s = str(raw).strip().replace("\u2212", "-").replace("\u00a0", "").replace(" ", "")
    if CENS.match(s):
        return None, "censored"
    pct = s.endswith("%")
    s = s[:-1] if pct else s
    if re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", s):
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None, "text"
    return (None, "nan") if (v != v or v in (float("inf"), float("-inf"))) else ((v / 100. if pct else v), "ok")

def split_header(h):
    h = str(h or "").strip()
    m = re.search(r"[\(\[（]\s*([^\(\)\[\]（）]{1,24})\s*[\)\]）]\s*$", h)
    return ((h[:m.start()].strip(" ,;:-") or h), m.group(1).strip()) if m else (h, "")

def norm_key(t):
    return re.sub(r"[\s_\-\.\(\)\[\]/]+", "", split_header(t)[0].lower())

def fmt_num(v):
    a = abs(v)
    if v == 0:
        return "0"
    if a >= 1e5 or a < 1e-3:
        return f"{v:.2e}"
    return f"{v:.0f}" if a >= 100 else (f"{v:.1f}" if a >= 10 else f"{v:g}")

def nice_ticks(a, b, n=6):
    a, b = (a or 0.), (b or 1.)
    b = b if b > a else a + 1.
    raw = (b - a) / max(1, n - 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    lo, hi = math.floor(a / step) * step, math.ceil(b / step) * step
    hi = hi if hi > lo else lo + step
    out, v = [], lo
    while v <= hi + step * 1e-9:
        out.append(round(v, 12))
        v += step
    return lo, hi, out

def log_ticks(a, b):
    lo, hi = 10 ** math.floor(math.log10(max(a, 1e-12))), 10 ** math.ceil(math.log10(max(b, 1e-12)))
    out, v = [], lo
    while v <= hi * 1.0000001:
        out.append(v)
        v *= 10
    return lo, hi, out

def text_width(t, size):
    return sum(1. if CJK.match(c) else .55 for c in str(t or "")) * size

def _grid_table(path, sheet, grid, lines):
    grid = [r for r in grid if any(str(c).strip() for c in r)]
    if not grid:
        return None
    hi, heads = 0, grid[0]
    if len(grid) > 1 and sum(parse_number(c)[1] == "ok" for c in heads) > \
            sum(parse_number(c)[1] == "ok" for c in grid[1]):
        hi, heads = 1, grid[1]
    w = max([len(heads)] + [len(r) for r in grid])
    rows = [{"row": i + 1, "cells": [str(c) for c in r] + [""] * (w - len(r)),
             "line": lines[i] if i < len(lines) else ""} for i, r in enumerate(grid[hi + 1:], hi + 1)]
    return {"file": os.path.basename(str(path)), "sheet": sheet, "header_row": hi + 1,
            "headers": [str(h) for h in heads] + [""] * (w - len(heads)), "rows": rows}

def read_delim(path, delim=None):
    raw = open(path, "r", encoding="utf-8-sig", errors="replace").read()
    lines = raw.splitlines()
    if delim is None:
        h = "\n".join(lines[:5])
        c = {",": h.count(","), "\t": h.count("\t"), ";": h.count(";"), "|": h.count("|")}
        delim = max(c, key=lambda k: c[k]) if max(c.values()) else ","
    grid = [[c.strip() for c in r] for r in csv.reader(io.StringIO(raw), delimiter=delim)]
    if grid and lines and delim not in (",", ";", "\t"):
        lines = [delim.join(r) for r in grid]
    return _grid_table(path, "csv", grid, lines)

def _cidx(ref):
    m = re.match(r"([A-Z]+)", ref or "")
    n = 0
    for ch in (m.group(1) if m else "A"):
        n = n * 26 + ord(ch) - 64
    return n - 1

def read_xlsx(path):
    import xml.etree.ElementTree as ET
    try:
        z = zipfile.ZipFile(str(path))
    except Exception:
        return []
    names, shared = set(z.namelist()), []
    try:
        shared = ["".join(x.text or "" for x in si.iter(M + "t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    except Exception:
        pass
    out = []
    for tgt in sorted(n for n in names if "worksheets/sheet" in n):
        try:
            grid = []
            for row in ET.fromstring(z.read(tgt)).iter(M + "row"):
                cells = {}
                for c in row.iter(M + "c"):
                    t, v = c.get("t") or "n", c.find(M + "v")
                    if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                        val = shared[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(M + "t"))
                    else:
                        val = (v.text or "") if v is not None else ""
                    cells[_cidx(c.get("r"))] = str(val).strip()
                if cells:
                    grid.append([cells.get(i, "") for i in range(max(cells) + 1)])
        except Exception:
            continue
        tb = _grid_table(path, tgt.split("/")[-1], grid, ["	".join(r) for r in grid]) if grid else None
        tb and out.append(tb)
    return out

def read_table(path):
    low = str(path).lower()
    try:
        if low.endswith((".xlsx", ".xlsm")):
            return read_xlsx(path)
        t = read_delim(path, "\t" if low.endswith((".tsv", ".tab")) else None)
        return [t] if t else []
    except Exception:
        return []

def inspect_png(path):
    o = {"path": os.path.basename(str(path)), "exists": os.path.exists(str(path))}
    if not o["exists"]:
        return o
    d = open(str(path), "rb").read()
    o["bytes"], o["magic_ok"] = len(d), d[:8] == b"\x89PNG\r\n\x1a\n"
    if not o["magic_ok"]:
        return o
    w, h, bd, ct = struct.unpack(">IIBB", d[16:26])
    o.update(width=w, height=h, bit_depth=bd, color_type=ct)
    if shutil.which("convert"):
        rc, out = run(["convert", str(path), "-format", "%[fx:mean]", "info:"], 90)
        try:
            o["mean_level"] = round(float(out.strip()), 4)
            o["ink_present"] = o["mean_level"] < 0.999
        except Exception:
            pass
    return o

def inspect_pdf(path):
    o = {"path": os.path.basename(str(path)), "exists": os.path.exists(str(path))}
    if not o["exists"]:
        return o
    d = open(str(path), "rb").read()
    o["bytes"], o["header_ok"] = len(d), d[:5] == b"%PDF-"
    o["pages"] = len(re.findall(rb"/Type\s*/Page[^s]", d))
    o["has_font"] = b"/FontFile" in d or b"/Type /Font" in d
    o["text_preserved"] = bool(re.search(rb"\bT[jJ]\b", d)) or o["has_font"]
    m = re.search(rb"/MediaBox\s*\[\s*([\d.\-]+) +([\d.\-]+) +([\d.\-]+) +([\d.\-]+)", d)
    if m:
        v = [float(x) for x in m.groups()]
        o["mediabox_pt"] = [round(v[2] - v[0], 2), round(v[3] - v[1], 2)]
    return o

def run(cmd, timeout=240):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, (p.stderr or b"")[-250:].decode("utf-8", "replace")
    except Exception as e:
        return 127, str(e)[:80]

def export_pdf(svg, pdf, log):
    so = shutil.which("soffice") or shutil.which("libreoffice")
    chain = [("rsvg-convert", ["rsvg-convert", "-f", "pdf", "-o", pdf, svg])] if shutil.which("rsvg-convert") else []
    if so:
        chain.append(("soffice", [so, "--headless", "--convert-to", "pdf", "--outdir", os.path.dirname(pdf), svg]))
    for nm, cmd in chain:
        os.path.exists(pdf) and os.remove(pdf)
        rc, err = run(cmd, 180)
        if nm == "soffice" and not os.path.exists(pdf):
            alt = os.path.join(os.path.dirname(pdf), os.path.splitext(os.path.basename(svg))[0] + ".pdf")
            os.path.exists(alt) and os.replace(alt, pdf)
        if os.path.exists(pdf) and os.path.getsize(pdf) > 400 and inspect_pdf(pdf)["header_ok"]:
            log.append("pdf_engine=" + nm)
            return nm
        log.append(f"pdf_fail={nm}")
    return None

def pdf_png(pdf, png, dpi, log):
    for nm, cmd in (("pdftoppm", ["pdftoppm", "-r", str(dpi), "-png", "-singlefile", pdf,
                                  os.path.splitext(png)[0]]),
                    ("gs", ["gs", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", "-r%d" % dpi,
                            "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", "-sOutputFile=" + png, pdf])):
        if not shutil.which(nm):
            continue
        rc, err = run(cmd, 180)
        if os.path.exists(png) and inspect_png(png)["magic_ok"]:
            log.append(f"png_from_pdf={nm}")
            return nm
        log.append(f"{nm}_fail")
    return None

def tx(i, x, y, s, t, a="middle", e="", f="#111111"):
    return f'<text id="{i}" x="{x:.2f}" y="{y:.2f}" font-size="{s:g}" fill="{f}" text-anchor="{a}"{e}>{escape(str(t))}</text>'

def ln(i, x1, y1, x2, y2, c, w):
    return f'<line id="{i}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{c}" stroke-width="{w:g}"/>'

def ymap(v, lo, hi, y0, y1, log):
    if log:
        return None if (v <= 0 or lo <= 0) else y1 - (math.log10(v) - math.log10(lo)) / (
            math.log10(hi) - math.log10(lo)) * (y1 - y0)
    return y1 - (v - lo) / (hi - lo) * (y1 - y0)

def pick(d, *ns, default=None):
    if not isinstance(d, dict):
        return default
    lo = {str(k).lower(): v for k, v in d.items()}
    for n in ns:
        if lo.get(n) not in (None, "", [], {}):
            return lo[n]
    for n in ns:
        for k, v in lo.items():
            if n in k and v not in (None, "", [], {}):
                return v
    return default

def bind(hs, w):
    if w is None:
        return None
    if isinstance(w, int):
        return w if 0 <= w < len(hs) else None
    nk = norm_key(str(w))
    for i, h in enumerate(hs):
        if nk and norm_key(h) == nk:
            return i
    for i, h in enumerate(hs):
        hk = norm_key(h)
        if nk and hk and (nk in hk or hk in nk):
            return i
    return None

def disc(inp):
    d = {"case": {}, "cp": None, "tables": [], "json": [], "wo": {}, "cerr": []}
    case = [inp / "case.json"] + sorted(inp.glob("case*.json"))
    for c in case:
        if c.is_file():
            d["cp"] = str(c)
            try:
                d["case"] = json.loads(c.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                d["cerr"].append("case_json_unparsable:" + c.name)
            break
    for p in sorted(inp.rglob("*")):
        sf = p.suffix.lower() if p.is_file() else ""
        if sf in (".csv", ".tsv", ".tab", ".xlsx", ".xlsm"):
            d["tables"].append(p)
        elif sf == ".json":
            d["json"].append(p)
            if "workorder" in p.name.lower() or "figure" in p.name.lower():
                try:
                    d["wo"].update(json.loads(p.read_text(encoding="utf-8", errors="replace")))
                except Exception:
                    pass
    for k, v in (d["case"] if isinstance(d["case"], dict) else {}).items():
        if isinstance(v, dict) and "workorder" in str(k).lower():
            d["wo"].update(v)
    return d

def spec(w):
    w = w if isinstance(w, dict) else {}
    ax = pick(w, "axis", "axes") or {}
    xa, ya = (pick(ax, "x") or {}), (pick(ax, "y") or {})
    xa, ya = (xa if isinstance(xa, dict) else {}), (ya if isinstance(ya, dict) else {})
    ep, eb = (pick(w, "export", "output_spec") or {}), (pick(w, "error_bar", "error_bars") or {})
    ep, eb = (ep if isinstance(ep, dict) else {}), (eb if isinstance(eb, dict) else {})
    yv = pick(w, "y", "y_fields", "y_columns", "value_column")
    yv = pick(yv, "fields", "columns") if isinstance(yv, dict) else yv
    yv = [yv] if isinstance(yv, (str, int)) else list(yv or [])
    s = {"t": str(pick(w, "chart_type", "figure_type") or "").lower(), "y": yv,
         "x": pick(w, "x", "x_field", "category"), "sc": pick(w, "series_field", "grouping"),
         "ti": pick(w, "title", "chart_title"), "lt": pick(w, "legend_title"),
         "xl": pick(w, "x_label") or pick(xa, "label"), "yl": pick(w, "y_label") or pick(ya, "label"),
         "xu": pick(w, "x_unit") or pick(xa, "unit"), "yu": pick(w, "y_unit") or pick(ya, "unit"),
         "ysc": str(pick(ya, "scale") or "linear").lower(), "ylim": pick(ya, "limits"),
         "em": str(pick(eb, "mode") or "").lower(), "ec": pick(eb, "source_column", "column"),
         "st": str(pick(w, "style", "style_preset") or "").lower(),
         "wm": pick(ep, "width_mm", "width"), "hm": pick(ep, "height_mm", "height"),
         "dpi": pick(ep, "dpi", "resolution"), "tb": pick(w, "source_table_ref", "source_table")}
    for k, dv in (("wm", 170.), ("hm", None)):
        try:
            s[k] = float(s[k]) if s[k] else dv
        except Exception:
            s[k] = dv
    try:
        s["dpi"] = int(s["dpi"]) if s["dpi"] else 300
    except Exception:
        s["dpi"] = 300
    return s

def kind(sp, B):
    t = sp["t"]
    if "line" in t:
        return "line"
    if "scatter" in t or "point" in t:
        return "scatter"
    if "bar" in t or "column" in t:
        return "bar"
    if t:
        sp.setdefault("warn", []).append(f"{t} unsupported, bar marks used")
    return "bar" if B["xc"] else ("line" if max(len(s["p"]) for s in B["ser"]) >= 6 else "scatter")

def cols(tb, sp):
    hs, rows, issues = tb["headers"], tb["rows"], []
    mt = [(i, *split_header(h), sum(parse_number(r["cells"][i])[1] == "ok" for r in rows) / max(1, len(rows)))
          for i, h in enumerate(hs)]
    xi = bind(hs, sp["x"])
    if xi is None:
        xi = next((m[0] for m in mt if m[3] < .5), 0)
    yl = []
    for w in sp["y"]:
        b = bind(hs, w)
        if b is None:
            issues.append(("column_not_found", f"y column {w!r} not in {tb['file']}", "skipped"))
        elif b not in yl:
            yl.append(b)
    if not yl:
        yl = [m[0] for m in mt if m[3] >= .6 and m[0] != xi]
    errs = {}
    for yi in yl:
        c = bind(hs, sp["ec"]) if sp["ec"] else None
        c = None if c in (yi, xi) else c
        if c is None:
            b0 = norm_key(hs[yi])
            for m in mt:
                st = norm_key(re.sub(ERRH, " ", m[1])) if m[0] not in (xi, yi) and ERRH.search(m[1]) else ""
                if st and (st == b0 or st.startswith(b0) or b0.startswith(st)):
                    c = m[0]
                    break
        if c is not None:
            errs[yi] = c
    if sp["em"] and not errs:
        issues.append(("error_column_missing", f"{sp['em']} error bars requested, no error column",
                       "none drawn, nothing invented"))
    sc = bind(hs, sp["sc"]) if sp["sc"] else None
    ser = []

    def grab(nm, un, ci, rs):
        ps = []
        for r in rs:
            raw, (v, k) = r["cells"][ci], parse_number(r["cells"][ci])
            if k != "ok":
                if k in ("nan", "censored"):
                    issues.append(("missing_value", f"row {r['row']} {hs[ci]}={raw!r}",
                                   "point skipped, never plotted as 0"))
                continue
            ps.append({"r": raw, "v": v, "x": r["cells"][xi].strip(), "row": r, "c": ci})
        ps and ser.append({"n": nm, "u": un, "c": ci, "p": ps})

    if sc is None:
        for yi in yl:
            grab(mt[yi][1] or hs[yi], mt[yi][2], yi, rows)
    else:
        gs = {}
        for r in rows:
            if r["cells"][sc].strip():
                gs.setdefault(r["cells"][sc].strip(), []).append(r)
        for g, rs in gs.items():
            grab(g, mt[yl[0]][2], yl[0], rs)
    return {"xi": xi, "xc": mt[xi][3] < .5, "ser": ser, "errs": errs, "issues": issues,
            "xl": sp["xl"] or mt[xi][1], "xu": sp["xu"] or mt[xi][2]}

def cmap(m):
    ser, req, mp, miss = [], 0, 0, []
    for sr in m["series"]:
        ps = []
        for p in sr["points"]:
            req += 1
            ok = bool(p.get("g") and p["src"].get("quote"))
            mp, miss = mp + (1 if ok else 0), miss + ([] if ok else [p["id"]])
            d = {"id": p["id"], "x": p["x"], "y_raw": p["yr"], "y": p["y"], "unit": sr["unit"] or None,
                 "source": p["src"], "geometry": p.get("g", {}),
                 "derivation": f"{m['axes']['y']['scale']} axis; value copied from source cell"}
            for k, kk in (("eraw", "error_raw"), ("err", "error"), ("emode", "error_mode"), ("esrc", "error_source")):
                if k in p:
                    d[kk] = p[k]
            ps.append({k: v for k, v in d.items() if v is not None})
        ser.append({k: sr[k] for k in ("id", "name", "column", "color", "marker", "unit")} | {"points": ps})
    xa, ya = m["axes"]["x"], m["axes"]["y"]
    return {"chart": {"type": m["chart_type"], "title": m["title"], "source_table": m["source_table"]},
            "series": ser,
            "axes": [{"axis": "x", "label": xa["label"], "unit": xa["unit"] or None, "scale": xa["scale"],
                      "categories": xa["categories"], "source": xa["source"]},
                     {"axis": "y", "label": ya["label"], "unit": ya["unit"] or None, "scale": ya["scale"],
                      "min": ya["min"], "max": ya["max"], "ticks": ya["ticks"], "source": ya["source"]}],
            "legend": m["legend"],
            "coverage": {"required": req, "mapped": mp, "missing": miss,
                         "ratio": round(mp / req, 4) if req else 0.0}}

def gcheck(m):
    lo, hi = m["axes"]["y"]["min"], m["axes"]["y"]["max"]
    log = m["axes"]["y"]["scale"] == "log"
    bad, n = [], 0
    for sr in m["series"]:
        for p in sr["points"]:
            g = p.get("g") or {}
            span = g.get("pb", 0) - g.get("pt", 0)
            if g.get("kind") != "bar" or not g.get("h") or span <= 0:
                continue
            bk = (10 ** (math.log10(lo) + g["h"] / span * (math.log10(hi) - math.log10(lo))) if log
                  else g["bv"] + g["h"] / span * (hi - lo))
            n += 1
            if abs(bk - p["y"]) / max(abs(p["y"]), 1e-12) > .02:
                bad.append({"id": p["id"], "expected": p["y"], "recomputed": round(bk, 6)})
    return {"checked": n, "mismatch_count": len(bad), "mismatches": bad[:5], "ok": not bad,
            "method": "bar height px -> value vs the source cell (2% tol)"}

def lcheck(m):
    it, ns = len(m["legend"]), len([s for s in m["series"] if s["points"]])
    nc = len({s["color"] for s in m["series"] if s["points"]})
    return {"legend_items": it, "series": ns, "distinct_colors": nc, "ok": it == ns == nc,
            "mapping": {i["label"]: {"color": i["color"], "series": i["series_id"]} for i in m["legend"]}}

def fin(S, out):
    keys = ("case_id", "status", "editable_source", "export_artifact", "content_map", "compliance_checks")
    r = {k: S.get(k) for k in keys}
    r.update((k, S[k]) for k in ("exceptions", "sources", "uncertainty", "pending_human", "errors",
                                 "degradations", "changes", "runtime"))
    r["task"] = {"skill": "source-value-chart", "version": "1.0.0",
                 "instruction": (S.get("instruction") or "")[:600]}
    for k, v in (S.get("contract") or {}).items():
        if k not in r:
            r[k] = [] if isinstance(v, list) else ({} if isinstance(v, dict) else None)
    p = Path(S["out"]) / "result.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0
