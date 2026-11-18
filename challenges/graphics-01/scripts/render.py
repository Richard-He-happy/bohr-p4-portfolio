"""render.py - figure_model -> layered editable SVG + real PNG/PDF (stdlib only).
PNG: external converters -> stdlib zlib bitmap (5x7 font, ASCII). PDF: external converters -> stdlib vector PDF (base-14 Helvetica, Latin text)."""
import math, re, shutil, struct, subprocess, zlib
from pathlib import Path

FS = "Arial, Helvetica, 'DejaVu Sans', sans-serif"
CJK = re.compile(r"[\u2e80-\u9fff\uff00-\uffef]")
INK = "#111111"
LAYERS = ["background", "panels", "edges", "entities", "labels", "legend", "title"]


def est_w(s, size):
    return sum(1.0 if CJK.match(c) else .55 for c in str(s)) * size


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def wrap(label, maxch=22):
    label, words = str(label), str(label).split()
    if len(label) <= maxch:
        return [label]
    if len(words) == 1:
        return [label[i:i + maxch] for i in range(0, len(label), maxch)]
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip() if cur else w
        if len(t) <= maxch:
            cur = t
        else:
            lines.append(cur); cur = w
    return lines + ([cur] if cur else [])


def num(v):
    f = float(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else ("%.3f" % f).rstrip("0").rstrip(".")


def rgb(h):
    h = (h or "#000000").lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (0, 0, 0)


def rect(i, layer, x, y, w, h, fill=None, stroke=None, lw=1.0, rx=0, dash=None, data=None):
    return {"k": "rect", "id": i, "layer": layer, "x": float(x), "y": float(y), "w": float(w), "h": float(h),
            "fill": fill, "stroke": stroke, "lw": lw, "rx": rx, "dash": dash, "data": data or {}}


def poly(i, layer, pts, fill=None, stroke=None, lw=1.0, dash=None, closed=False, marker=None, data=None):
    return {"k": "poly", "id": i, "layer": layer, "pts": [[float(a), float(b)] for a, b in pts], "fill": fill,
            "stroke": stroke, "lw": lw, "dash": dash, "closed": closed, "marker": marker, "data": data or {}}


def text(i, layer, x, y, s, size, anchor="middle", fill=INK, weight="normal", data=None):
    return {"k": "text", "id": i, "layer": layer, "x": float(x), "y": float(y), "s": str(s), "size": size,
            "anchor": anchor, "fill": fill, "weight": weight, "data": data or {}}


def heads(pts, kind, color):
    """Marker glyph from the last segment; matches the SVG <marker> shapes."""
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    a = math.atan2(y2 - y1, x2 - x1) if (x2, y2) != (x1, y1) else 0.0
    if kind == "inhibition":
        px, py = -math.sin(a), math.cos(a)
        return [poly(None, "edges", [[x2 - px * 4.6, y2 - py * 4.6], [x2 + px * 4.6, y2 + py * 4.6]], stroke=color, lw=2.2)]
    if kind == "binding":
        return [poly(None, "edges", [[x2, y2], [x2 - 4, y2 - 3.2], [x2 - 8, y2], [x2 - 4, y2 + 3.2]],
                    fill=color, stroke=color, lw=0.8, closed=True)]
    return [poly(None, "edges", [[x2, y2], [x2 - 8 * math.cos(a - .36), y2 - 8 * math.sin(a - .36)],
                                 [x2 - 8 * math.cos(a + .36), y2 - 8 * math.sin(a + .36)]],
                fill=color, stroke=color, lw=.6, closed=True)]


def layout(m):
    """Deterministic rank-column layout; fits the canvas to the content."""
    cv, st = m["canvas"], m["style"]
    fs, pal = st["font_pt"], st["palette"]
    M, ents, chart = 38.0, m.get("entities") or [], m.get("chart")
    rels = m.get("relations") or []
    for e in ents:
        e["lines"] = wrap(e.get("label", ""))
        tw = max([est_w(l, fs["label"]) for l in e["lines"]] or [20])
        e["box"] = {"w": max(74.0, tw + 24), "h": max(30.0, len(e["lines"]) * fs["label"] * 1.5 + 15)}
    ids = [e["id"] for e in ents]
    known = set(ids)
    rank = {k: 0 for k in ids}
    edges = [r for r in rels if r.get("from") in known and r.get("to") in known and r["from"] != r["to"]]
    for _ in range(len(ids) + 1):
        moved = False
        for r in edges:
            if rank[r["to"]] < rank[r["from"]] + 1:
                rank[r["to"]] = rank[r["from"]] + 1
                moved = True
        if not moved:
            break
    top = max(rank.values()) if rank else 0
    if top > max(1, len(ids) - 1):
        s = max(1, len(ids) - 1) / float(top)
        rank = {k: int(v * s) for k, v in rank.items()}
    cols = {}
    for e in ents:
        cols.setdefault(rank[e["id"]], []).append(e)
    y_top = M + (44.0 if m.get("title") else 10.0)
    x, band = M, 0.0
    for r in sorted(cols):
        cw = max(e["box"]["w"] for e in cols[r])
        y = y_top
        for e in cols[r]:
            e["box"].update({"x": x, "y": y, "w": cw})
            y += e["box"]["h"] + 26.0
        band = max(band, sum(e["box"]["h"] for e in cols[r]) + 26.0 * (len(cols[r]) - 1))
        x += cw + 74.0
    content = (x - 74.0) if cols else M + 240.0
    y_cur = y_top + band
    if chart:
        chart["box"] = {"x": M, "y": y_cur + 26.0, "w": max(520.0, content - M), "h": 214.0}
        content = max(content, chart["box"]["x"] + chart["box"]["w"])
        y_cur = chart["box"]["y"] + 214.0
    m["panels"] = []
    if chart and ents:
        m["panels"] = [{"id": "panel-a", "label": "A", "box": {"x": M - 14, "y": y_top - 20, "w": content - M + 28, "h": band + 32}},
                       {"id": "panel-b", "label": "B", "box": {"x": chart["box"]["x"] - 14, "y": chart["box"]["y"] - 20,
                                                               "w": chart["box"]["w"] + 20, "h": 208.0}}]
    leg = m.get("legend") or []
    for i, lg in enumerate(leg):
        lg.setdefault("color", pal[i % len(pal)])
    lb = {"x": M, "y": y_cur + 24.0, "w": max(170.0, max(est_w(l["label"], fs["legend"]) for l in leg) + 76),
          "h": 19.0 * len(leg) + 16} if leg else None
    m["legend_box"] = lb
    cv["width"] = int(round(max(float(cv.get("width") or 0), content + M, (lb["x"] + lb["w"] + M) if lb else 0, 860.0)))
    cv["height"] = int(round(max(float(cv.get("height") or 0), (lb["y"] + lb["h"] if lb else y_cur) + M, 520.0)))
    cv["auto_fit"] = True
    by = {e["id"]: e for e in ents}
    for r in rels:
        a, b = by.get(r.get("from")), by.get(r.get("to"))
        if not a or not b or a is b:
            r["path"] = []
            continue
        ab, bb = a["box"], b["box"]
        x1, y1, x2, y2 = ab["x"] + ab["w"], ab["y"] + ab["h"] / 2, bb["x"], bb["y"] + bb["h"] / 2
        if x2 < x1 + 16:
            yb = max(ab["y"] + ab["h"], bb["y"] + bb["h"]) + 16
            r["path"] = [[x1, y1], [x1 + 13, y1], [x1 + 13, yb], [x2 - 13, yb], [x2 - 13, y2], [x2, y2]]
            r["route"] = "under"
        else:
            xm = (x1 + x2) / 2.0
            r["path"] = [[x1, y1], [xm, y1], [xm, y2], [x2, y2]]
            r["route"] = "elbow"
        r.setdefault("color", st.get("rel_color", {}).get(r.get("type"), "#333333"))
        r.setdefault("marker", st.get("rel_marker", {}).get(r.get("type"), "activation"))
    return m


def _chart(m, P):
    ch, st = m.get("chart") or {}, m["style"]
    b = ch.get("box")
    if not b:
        return
    pal, ft = st["palette"], max(6.0, st["font_pt"]["legend"] - 0.5)
    x0, y0, pw, ph = b["x"] + 64, b["y"] + 30, b["w"] - 96, b["h"] - 66
    P.append(text("chart-title", "labels", b["x"] + 8, b["y"] + 15, ch.get("title") or "",
                  st["font_pt"]["label"] + .5, "start", INK, "bold"))
    series = ch.get("series") or []
    vals = [v for s in series for v in s.get("values", []) if isinstance(v, (int, float))]
    vmax = (max(vals) if vals else 1.0) * 1.12 or 1.0
    for t in range(5):
        ty = y0 + ph - ph * t / 4.0
        P.append(text("tick-%d" % t, "labels", x0 - 5, ty + 2.5, num(vmax * t / 4.0), ft, "end", "#444444"))
    for i, pts in (("axis-x", [[x0, y0 + ph], [x0 + pw, y0 + ph]]), ("axis-y", [[x0, y0], [x0, y0 + ph]])):
        P.append(poly(i, "labels", pts, stroke="#333333", lw=.9))
    yl = " ; ".join(sorted({s.get("unit") or "" for s in series if s.get("unit")})) or ch.get("unit") or ""
    if yl:
        P.append(text("axis-y-label", "labels", x0 - 40, y0 + ph / 2.0, yl, ft, "middle", "#333333"))
    cats = ch.get("categories") or []
    grp = pw / float(max(1, len(cats)))
    bw = grp / (len(series) + 0.6) if series else grp * 0.6
    for ci, cat in enumerate(cats):
        for si, s in enumerate(series):
            vs = s.get("values") or []
            v = vs[ci] if ci < len(vs) else None
            if not isinstance(v, (int, float)):
                continue
            hh = ph * (v / vmax)
            bx = x0 + grp * ci + grp * 0.08 + si * bw
            col = pal[(si + (1 if len(series) > 1 else 0)) % len(pal)]
            P.append(rect("bar-%d-%d" % (ci + 1, si + 1), "entities", bx, y0 + ph - hh, max(6.0, bw - 3), hh, fill=col,
                          stroke=col, lw=.6, data={"data-series": s.get("name", ""), "data-category": str(cat)}))
        P.append(text("cat-%d" % (ci + 1), "labels", x0 + grp * ci + grp / 2., y0 + ph + 12,
                      wrap(str(cat), 12)[0], ft, "middle", "#222222"))


def primitives(m, for_svg=False):
    cv, st = m["canvas"], m["style"]
    fs, lw = st["font_pt"], st.get("line_width", 1.2)
    P = [rect("bg-canvas", "background", 0, 0, cv["width"], cv["height"], fill="#FFFFFF")]
    for p in m.get("panels") or []:
        b = p["box"]
        P.append(rect(p["id"], "panels", b["x"], b["y"], b["w"], b["h"], "#FFFFFF", "#9aa4ad", .8, 6, "4 3"))
        P.append(text("lbl-" + p["id"], "labels", b["x"] + 7, b["y"] + 15, p["label"], fs["title"], "start", INK, "bold"))
    if m.get("title"):
        P.append(text("title-main", "title", 38, 34, m["title"], fs["title"] + 1.5, "start", INK, "bold"))
    for r in m.get("relations") or []:
        pts = r.get("path") or []
        if len(pts) < 2:
            continue
        col = r.get("color", "#333333")
        P.append(poly("edge-" + r["id"], "edges", pts, stroke=col, lw=lw, dash=r.get("dash"),
                      data={"data-rel-type": r.get("type", ""), "data-from": r["from"], "data-to": r["to"]}))
        if not for_svg:
            P += heads(pts, r.get("marker", "activation"), col)
        if r.get("label"):
            md = pts[len(pts) // 2]
            P.append(text("lbl-edge-" + r["id"], "labels", md[0] + 3, md[1] - 4, r["label"], fs["legend"], "start", "#444444"))
    for e in m["entities"]:
        b, n = e["box"], len(e["lines"])
        P.append(rect("ent-" + e["id"], "entities", b["x"], b["y"], b["w"], b["h"], fill=e.get("fill", st["entity_fill"]),
                      stroke=e.get("stroke", st["entity_stroke"]), lw=lw, rx=4,
                      data={"data-entity-id": e["id"], "data-entity-type": e.get("type", "")}))
        for i, ln in enumerate(e["lines"]):
            ty = b["y"] + b["h"] / 2. + (i - (n - 1) / 2.) * fs["label"] * 1.5 + fs["label"] * .36
            P.append(text("lbl-" + e["id"] if n == 1 else "lbl-%s-%d" % (e["id"], i + 1), "labels",
                          b["x"] + b["w"] / 2., ty, ln, fs["label"], "middle", INK, data={"data-entity-id": e["id"]}))
    _chart(m, P)
    lb, leg = m.get("legend_box"), m.get("legend") or []
    if lb and leg:
        P.append(rect("legend-box", "legend", lb["x"], lb["y"], lb["w"], lb["h"], fill="#FFFFFF", stroke="#8d979f", lw=.8, rx=3))
        P.append(text("legend-title", "legend", lb["x"] + 8, lb["y"] + 12.5, "Legend", fs["legend"] + .5, "start", INK, "bold"))
        for i, lg in enumerate(leg):
            ly, col = lb["y"] + 26 + i * 19, lg.get("color", "#333333")
            if lg.get("kind") == "relation":
                P.append(poly("lg-" + lg["id"], "legend", [[lb["x"] + 10, ly - 3], [lb["x"] + 40, ly - 3]], stroke=col, lw=lw))
                P += heads([[lb["x"] + 10, ly - 3], [lb["x"] + 40, ly - 3]], lg.get("marker", "activation"), col)
            else:
                P.append(rect("lg-" + lg["id"], "legend", lb["x"] + 10, ly - 8, 16, 9, fill=col, stroke=col, lw=.6))
            P.append(text("lglbl-" + lg["id"], "legend", lb["x"] + 48, ly, lg["label"], fs["legend"], "start", INK))
    return P


MARKERS = ('<marker id="mk-activation" refX="8" refY="4" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#333333"/></marker>'
           '<marker id="mk-inhibition" refX="9" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto"><path d="M9,0 L9,10" stroke="#333333" stroke-width="2"/></marker>'
           '<marker id="mk-binding" refX="9" refY="4" markerWidth="9" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,4 L4.5,0 L9,4 L4.5,8 z" fill="#333333"/></marker>')


def _el(p):
    at = ' id="%s"' % p["id"] if p.get("id") else ""
    for a, v in (p.get("data") or {}).items():
        at += ' %s="%s"' % (a, esc(v))
    if p["k"] == "rect":
        s = '<rect%s x="%g" y="%g" width="%g" height="%g" fill="%s" stroke="%s" stroke-width="%g"' % (
            at, p["x"], p["y"], p["w"], p["h"], p["fill"] or "none", p["stroke"] or "none", p.get("lw") or 0)
        s += (' rx="%g"' % p["rx"]) if p.get("rx") else ""
        s += (' stroke-dasharray="%s"' % p["dash"]) if p.get("dash") else ""
        return s + "/>"
    if p["k"] == "poly":
        s = '<path%s d="M%s%s" fill="%s" stroke="%s" stroke-width="%g" stroke-linejoin="round"' % (
            at, " L".join("%g,%g" % (a, b) for a, b in p["pts"]), " Z" if p.get("closed") else "",
            p["fill"] or "none", p["stroke"] or "none", p.get("lw") or 0)
        s += (' stroke-dasharray="%s"' % p["dash"]) if p.get("dash") else ""
        s += (' marker-end="url(#mk-%s)"' % p["marker"]) if p.get("marker") else ""
        return s + "/>"
    return ('<text%s x="%g" y="%g" font-size="%g" text-anchor="%s" fill="%s" font-weight="%s">%s</text>'
            % (at, p["x"], p["y"], p["size"], p.get("anchor", "middle"), p["fill"], p.get("weight", "normal"), esc(p["s"])))


def svg(m):
    cv = m["canvas"]
    W, H = cv["width"], cv["height"]
    P = primitives(m, True)
    rels = {str(r.get("id")): r for r in m.get("relations") or []}
    for p in P:
        if p["k"] == "poly" and (p.get("id") or "").startswith("edge-"):
            p["marker"] = rels.get(p["id"][5:], {}).get("marker", "activation")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img">' % (W, H, W, H),
           '  <title>%s</title>' % esc(m.get("title") or m.get("figure_id") or "schematic"),
           '  <desc>Layered editable schematic (scifig-editable 1.0); live text, ids map to content_map.</desc>',
           '  <defs>' + MARKERS + '</defs>']
    for L in m.get("layers") or LAYERS:
        els = [p for p in P if p.get("layer") == L]
        if els:
            out.append('  <g id="layer-%s" data-layer="%s" font-family="%s" fill="%s">' % (L, L, FS, INK))
            out += ["    " + _el(p) for p in els]
            out.append('  </g>')
    return "\n".join(out + ['</svg>']) + "\n"


def _sh(*n):
    return next((p for p in (shutil.which(x) for x in n) if p), None)


def _run(argv, out, minb=600):
    try:
        subprocess.run(argv, check=True, capture_output=True, timeout=240)
        return Path(out).exists() and Path(out).stat().st_size > minb
    except Exception:
        return False


def _convert(svg, out, png_w=0, dpi=300):
    """figure.svg -> real PNG/PDF with whatever the image ships (engine name returned)."""
    svg, out = Path(svg), Path(out)
    if not svg.exists():
        return None
    t = _sh("rsvg-convert")
    if t and _run(([t, "-w", str(png_w), "-o", str(out), str(svg)] if png_w else [t, "-f", "pdf", "-o", str(out), str(svg)]), out):
        return "rsvg-convert"
    t = _sh("cairosvg")
    if t and _run(([t, str(svg), "--output-width", str(png_w), "-o", str(out)] if png_w else [t, str(svg), "-o", str(out)]), out):
        return "cairosvg"
    t = _sh("inkscape")
    if t and _run(([t, str(svg), "--export-type=png", "--export-filename=" + str(out), "--export-width=%d" % png_w]
                   if png_w else [t, str(svg), "--export-type=pdf", "--export-filename=" + str(out)]), out):
        return "inkscape"
    if png_w:  # vector PDF then poppler raster: keeps text crisp even without an SVG rasteriser
        p = _sh("pdftoppm")
        eng = _convert(svg, out.with_suffix(".pdf"), dpi=dpi) if p else None
        if eng and _run([p, "-png", "-r", str(dpi), "-singlefile", str(out.with_suffix(".pdf")), str(out.with_suffix(""))], out, 800):
            return eng + "+pdftoppm"
        t = _sh("convert", "magick")
        if t and _run([t, "-density", str(dpi), "-background", "white", "-flatten", "-depth", "8", str(svg), str(out)], out, 800):
            return "imagemagick"
        return None
    t = _sh("soffice", "libreoffice")
    if t and _run([t, "--headless", "--convert-to", "pdf", "--outdir", str(out.parent), str(svg)], out):
        return "libreoffice-draw"
    return None


F7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["00000"] * 7, "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ",": ["00000", "00000", "00000", "00000", "00110", "00100", "01000"], "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"], "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"], "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"], ";": ["00000", "01100", "01100", "00000", "00110", "00100", "01000"],
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"], "_": ["00000", "00000", "00000", "00000", "00000", "00000", "11111"],
    "*": ["00000", "10101", "01110", "11111", "01110", "10101", "00000"], "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"],
    "#": ["01010", "11111", "01010", "01010", "11111", "01010", "00000"],
}


def _png_stdlib(m, out):
    """Degraded real PNG: stdlib zlib + 5x7 bitmap font (ASCII only). Never raises to caller."""
    S, W, H = 2, int(m["canvas"]["width"]) * 2, int(m["canvas"]["height"]) * 2
    px = bytearray([255, 255, 255]) * (W * H)

    def fill_rect(x0, y0, x1, y1, c):
        x0 = max(0, int(x0)); y0 = max(0, int(y0)); x1 = min(W - 1, int(x1)); y1 = min(H - 1, int(y1))
        for y in range(y0, y1 + 1):
            o = (y * W + x0) * 3
            for _ in range(x0, x1 + 1):
                px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2]; o += 3

    def line(x0, y0, x1, y1, c, t):
        t = max(1, int(t)); dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1; sy = 1 if y0 < y1 else -1; err = dx - dy
        x, y, r = int(x0), int(y0), t // 2
        while True:
            fill_rect(x - r, y - r, x + r, y + r, c)
            if x == int(x1) and y == int(y1):
                break
            e2 = 2 * err
            if e2 > -dy: err -= dy; x += sx
            if e2 < dx: err += dx; y += sy

    def polyline(pts, c, t):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            line(x0 * S, y0 * S, x1 * S, y1 * S, c, t * S)

    def fill_poly(pts, c):
        xs = [p[0] * S for p in pts]; ys = [p[1] * S for p in pts]
        x0, x1 = int(min(xs)), int(max(xs)); y0, y1 = int(min(ys)), int(max(ys))
        for y in range(max(0, y0), min(H - 1, y1) + 1):
            for x in range(max(0, x0), min(W - 1, x1) + 1):
                inside, j = False, len(pts) - 1
                for i in range(len(pts)):
                    if (ys[i] > y) != (ys[j] > y) and x < (xs[j] - xs[i]) * (y - ys[i]) / (ys[j] - ys[i]) + xs[i]:
                        inside = not inside
                    j = i
                if inside:
                    o = (y * W + x) * 3; px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2]

    def glyph(ch):
        return F7.get(ch.upper()) or ["11111", "10001", "10001", "10001", "10001", "10001", "11111"]

    def text(x, y, s, size, c):
        step = max(1, int(round(size * S / 7.0))); cx, cy = int(x * S), int(y * S) - 3 * step
        for ch in str(s):
            g = glyph(ch)
            for rr, row in enumerate(g):
                for cc, bit in enumerate(row):
                    if bit == "1":
                        fill_rect(cx + cc * step, cy + rr * step, cx + (cc + 1) * step - 1, cy + (rr + 1) * step - 1, c)
            cx += 6 * step

    for p in primitives(m, False):
        if p["k"] == "rect":
            x, y, w, h = p["x"] * S, p["y"] * S, p["w"] * S, p["h"] * S
            if p.get("fill") and rgb(p["fill"]) != (255, 255, 255):
                fill_rect(x, y, x + w - 1, y + h - 1, rgb(p["fill"]))
            if p.get("stroke"):
                c = rgb(p["stroke"]); t = max(1, int(p.get("lw", 1) * S))
                line(x, y, x + w, y, c, t); line(x + w, y, x + w, y + h, c, t)
                line(x + w, y + h, x, y + h, c, t); line(x, y + h, x, y, c, t)
        elif p["k"] == "poly":
            if p.get("closed") and p.get("fill"):
                fill_poly(p["pts"], rgb(p["fill"]))
            if p.get("stroke") and not p.get("closed"):
                polyline(p["pts"], rgb(p["stroke"]), p.get("lw", 1))
        elif p["k"] == "text":
            text(p["x"], p["y"], p["s"], p["size"], rgb(p.get("fill") or "#111111"))
    raw = b"".join(b"\x00" + bytes(px[y * W * 3:(y + 1) * W * 3]) for y in range(H))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    Path(out).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _pdf_escape(s):
    o = []
    for c in s:
        if ord(c) < 32 or ord(c) > 255:
            return None
        o.append("\\" + c if c in "()\\" else c)
    return "".join(o)


def _path(pts):
    parts = ["%.2f %.2f m" % pts[0]]
    parts += ["%.2f %.2f l" % pt for pt in pts[1:]]
    return " ".join(parts)


def _pdf_stdlib(m, out):
    """Degraded real vector PDF: catalog + page + content stream, base-14 Helvetica (Latin only)."""
    W, H = int(m["canvas"]["width"]), int(m["canvas"]["height"])
    cmds = ["1 1 1 rg 0 0 %d %d re f" % (W, H)]
    for p in primitives(m, False):
        if p["k"] == "rect":
            x, y, w, h = p["x"], H - p["y"] - p["h"], p["w"], p["h"]
            if p.get("fill") and rgb(p["fill"]) != (255, 255, 255):
                r, g, b = [v / 255.0 for v in rgb(p["fill"])]
                cmds.append("%.4f %.4f %.4f rg %.2f %.2f %.2f %.2f re f" % (r, g, b, x, y, w, h))
            if p.get("stroke"):
                r, g, b = [v / 255.0 for v in rgb(p["stroke"])]
                cmds.append("%.4f %.4f %.4f RG %.2f w %.2f %.2f %.2f %.2f re S" % (r, g, b, p.get("lw", 1), x, y, w, h))
        elif p["k"] == "poly":
            pts = [(px, H - py) for (px, py) in p["pts"]]
            if len(pts) < 2:
                continue
            if p.get("closed") and p.get("fill"):
                r, g, b = [v / 255.0 for v in rgb(p["fill"])]
                cmds.append("%.4f %.4f %.4f rg %s h f" % (r, g, b, _path(pts)))
            if p.get("stroke") and not p.get("closed"):
                r, g, b = [v / 255.0 for v in rgb(p["stroke"])]
                cmds.append("%.4f %.4f %.4f RG %.2f w %s S" % (r, g, b, p.get("lw", 1), _path(pts)))
        elif p["k"] == "text":
            s = _pdf_escape(str(p["s"]))
            if s is None:
                continue
            size, x = p["size"], p["x"]
            if p.get("anchor") == "middle":
                x -= 0.26 * size * len(s)
            elif p.get("anchor") == "end":
                x -= 0.52 * size * len(s)
            r, g, b = [v / 255.0 for v in rgb(p.get("fill") or "#111111")]
            cmds.append("BT %.4f %.4f %.4f rg /F1 %.2f Tf %.2f %.2f Td (%s) Tj ET" % (r, g, b, size, x, H - p["y"], s))
    stream = "\n".join(cmds).encode("latin-1")
    chunks, offsets = [b"%PDF-1.4\n"], []

    def add(num, body):
        offsets.append(sum(len(c) for c in chunks))
        chunks.append(("%d 0 obj\n" % num).encode("latin-1") + body + b"\nendobj\n")
    add(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add(2, b"<< /Type/Pages /Kids [3 0 R] /Count 1 >>")
    add(3, b"<< /Type/Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>" % (W, H))
    add(4, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    add(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    xref, n = sum(len(c) for c in chunks), len(offsets)
    chunks.append(("xref\n0 %d\n0000000000 65535 f \n" % (n + 1)).encode("latin-1"))
    chunks.append(b"".join(("%010d 00000 n \n" % off).encode("latin-1") for off in offsets))
    chunks.append(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n + 1, xref))
    Path(out).write_bytes(b"".join(chunks))


def export_all(m, out_dir, dpi=300):
    """Returns real exports + engine per artifact + degradations. Never raises."""
    out_dir, res = Path(out_dir), {"png": None, "pdf": None, "degradations": [], "engines": {}}
    W, H = float(m["canvas"]["width"]), float(m["canvas"]["height"])
    svg_path, png, pdf = out_dir / "figure.svg", out_dir / "figure.png", out_dir / "figure.pdf"
    for f, out in (("png", png), ("pdf", pdf)):
        eng = _convert(svg_path, out, png_w=int(W * 2) if f == "png" else 0, dpi=dpi)
        if eng:
            res["engines"][f] = eng
            res[f] = out
            continue
        try:
            (_png_stdlib if f == "png" else _pdf_stdlib)(m, out)
            eng = "stdlib-zlib" if f == "png" else "stdlib-pdf"
            res["engines"][f] = eng
            res[f] = out
            res["degradations"].append({"artifact": f, "engine": eng, "status": "degraded",
                                        "reason": "no external converter; stdlib renderer used (ASCII/Latin text only)"})
        except Exception as e:
            res["degradations"].append({"artifact": f, "engine": None, "status": "missing",
                                        "reason": "no converter and stdlib renderer failed: %s" % e})
    return res
