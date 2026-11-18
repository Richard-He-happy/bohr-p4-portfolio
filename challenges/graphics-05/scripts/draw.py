"""draw.py - one display list, three renderers (SVG / PDF / PNG).

Deterministic: same plan -> same geometry. stdlib only; matplotlib (optional)
is used for the PNG preview. Standalone: python3 draw.py --plan P --out DIR
"""
import json, sys
from pathlib import Path

W, H, MARGIN, PS = 1200, 760, 40, 0.72  # PS: model units -> PDF points
ROLE = {"problem": ("PROBLEM", "#D55E00"), "method": ("METHODS", "#0072B2"),
        "results": ("KEY RESULTS", "#009E73"), "implication": ("IMPLICATION", "#CC79A7"),
        "other": ("NOTE", "#555555")}
LAYERS = ["background", "structure", "content", "legend", "footer", "titles"]
_LI = {n: i for i, n in enumerate(LAYERS)}


def strip(s):
    return " ".join(str(s or "").split())


def norm_role(r):
    r = str(r or "").lower()
    for k, ns in (("problem", ("problem", "question", "gap", "aim", "motivation", "challenge")),
                  ("method", ("method", "approach", "pipeline", "strategy", "experiment", "workflow")),
                  ("results", ("results", "finding", "outcome", "evidence", "data", "effect")),
                  ("implication", ("implication", "conclusion", "significance", "impact", "outlook"))):
        if any(n in r for n in ns):
            return k
    return "other"


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def mix(h, keep):  # blend with white; keep = colour fraction
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(255 * (1 - keep) + c * 255 * keep))) for c in rgb(h))


def shade(h, f=0.72):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255 * f))) for c in rgb(h))


def cw(ch, size):
    if ord(ch) > 0x2E7F:
        return size
    if ch in "ilj.,;:'!|()[]":
        return size * 0.29
    if ch in "mwMW":
        return size * 0.85
    return size * (0.65 if ch.isupper() else 0.56 if ch.isdigit() else 0.52)


def tw(s, size):
    return sum(cw(c, size) for c in s)


def wrap(s, size, width, maxl=0):
    s = strip(s)
    if not s:
        return []
    toks, buf = [], ""
    for ch in s:
        if ord(ch) > 0x2E7F or ch == " ":
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(ch)
        else:
            buf += ch
    if buf:
        toks.append(buf)
    lines, cur = [], ""
    for tk in toks:
        if not cur or tw((cur + tk).strip(), size) <= width:
            cur += tk
        else:
            if cur.strip():
                lines.append(cur.strip())
            cur = "" if tk == " " else tk
    if cur.strip():
        lines.append(cur.strip())
    if maxl and len(lines) > maxl:
        lines = lines[:maxl]
        lines[-1] = lines[-1].rstrip(" ,.;:") + "..."
    return lines


def T(x, y, s, size, weight="normal", color="#1A1A1A", anchor="start", eid=None, layer="content"):
    return dict(op="text", x=float(x), y=float(y), text=s, size=float(size), weight=weight,
                color=color, anchor=anchor, eid=eid, layer=layer)


def R(x, y, w, h, fill=None, stroke=None, sw=1.0, rx=0, eid=None, layer="structure"):
    return dict(op="rect", x=float(x), y=float(y), w=float(w), h=float(h), fill=fill, stroke=stroke,
                sw=float(sw), rx=float(rx), eid=eid, layer=layer)


def L(x1, y1, x2, y2, color="#666666", sw=1.0, eid=None, layer="structure"):
    return dict(op="line", x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2), stroke=color,
                sw=float(sw), eid=eid, layer=layer)


# --- item layout ---
def lay_item(it, w, sc, accent):
    k = str(it.get("kind") or "text").lower()
    lab, det = strip(it.get("label")), strip(it.get("detail") or it.get("note"))
    val, ops = strip(it.get("value")), []
    if k == "value":
        vs, ds = 20 * sc, 11.5 * sc
        v = wrap(val or lab, vs, w - 20) or [""]
        d = wrap(det, ds, w - 20)
        h = 8 + len(v) * (vs + 2) + (len(d) * (ds + 3) + 2 if d else 0) + 8
        ops += [R(0, 0, w, h, mix(accent, 0.12), None, 0, 8), R(0, 5, 3.5, h - 10, accent, None, 0, 1.5)]
        yy = 8 + vs * 0.85
        for ln in v:
            ops.append(T(11, yy, ln, vs, "bold", shade(accent)))
            yy += vs + 2
        yy += 2 if d else 0
        for ln in d:
            ops.append(T(11, yy, ln, ds, "normal", "#3A3A3A"))
            yy += ds + 3
        return ops, h + 10
    ls, ds = 13.5 * sc, 11.8 * sc
    l, d = wrap(lab, ls, w), wrap(det, ds, w)
    h = len(l) * (ls + 2) + len(d) * (ds + 3.4) + 6
    yy = ls * 0.85
    for ln in l:
        ops.append(T(0, yy, ln, ls, "bold", "#1A1A1A"))
        yy += ls + 2
    for ln in d:
        ops.append(T(0, yy, ln, ds, "normal", "#3A3A3A"))
        yy += ds + 3.4
    return ops, h + 8


def fit_items(items, w, avail, accent):
    for sc in (1.0, 0.94, 0.88, 0.82, 0.76):
        lays, tot = [], 0.0
        for it in items:
            ops, h = lay_item(it, w, sc, accent)
            lays.append((it, ops, h))
            tot += h
        if tot <= avail:
            return sc, lays, []
    sc, lays, tot, drop = 0.76, [], 0.0, []
    for it in items:
        ops, h = lay_item(it, w, sc, accent)
        if tot + h <= avail:
            lays.append((it, ops, h))
            tot += h
        else:
            drop.append(it.get("id") or it.get("label"))
    return sc, lays, drop


# --- model ---
def _panel(g, sizes, warns, els, dropped):
    p, role = g["panel"], g["role"]
    label, color = ROLE[role]
    x, y, w, h, pid = g["x"], g["y"], g["w"], g["h"], g["id"]
    ops = [R(x, y, w, h, "#FCFCFC", "#D9D9D9", 1.0, 10, pid + "-card"),
           R(x, y, w, 34, color, None, 0, 10, pid + "-header"),
           R(x, y + 17, w, 17, color, None, 0, 0, pid + "-headerb")]
    heading, hts = strip(p.get("heading")) or label, 14.5
    while tw(heading, hts) > w - 34 and hts > 9:
        hts -= 0.5
    ops.append(T(x + 12, y + 23, heading, hts, "bold", "#FFFFFF", "start", pid + "-heading"))
    sizes.append(hts)
    if role != "other" and heading.upper() != label:
        ops.append(T(x + w - 10, y + 21, label, 9.0, "normal", "#FFFFFF", "end", pid + "-roletag"))
        sizes.append(9.0)
    items = [i for i in (p.get("items") or []) if isinstance(i, dict)]
    ix, iw = x + 13, w - 26
    sc, lays, drop = fit_items(items, iw, h - 58, color)
    if drop:
        dropped.append({"panel": pid, "items": drop, "reason": "vertical overflow at smallest font scale"})
        warns.append(f"panel {pid}: {len(drop)} item(s) dropped")
    cy = y + 46
    for it, iops, ih in lays:
        eid = str(it.get("id") or f"{pid}-I{len(els) + 1}")
        for o in iops:
            o = dict(o, x=o["x"] + ix, y=o["y"] + cy)
            if o["op"] == "text":
                o["eid"] = eid
                sizes.append(o["size"])
            ops.append(o)
        els.append({"id": eid, "panel": pid, "role": role, "kind": str(it.get("kind") or "text"),
                    "text": " ".join([strip(it.get("label")), strip(it.get("value")),
                                      strip(it.get("detail") or it.get("note"))]).strip(),
                    "bbox": [round(ix, 1), round(cy, 1), round(iw, 1), round(ih, 1)]})
        cy += ih
    return ops


def build_model(plan):
    title = strip(plan.get("title")) or "Graphical abstract"
    subtitle = strip(plan.get("subtitle") or plan.get("one_line_message"))
    caption = strip(plan.get("caption"))
    panels = [p for p in (plan.get("panels") or []) if isinstance(p, dict)]
    ops = [R(0, 0, W, H, "#FFFFFF", None, 0, 0, "canvas", "background")]
    els, warns, dropped, sizes = [], [], [], []
    ts = 30.0
    while tw(title, ts) > W - 2 * MARGIN and ts > 16:
        ts -= 1
    ops.append(T(MARGIN, 50, title, ts, "bold", "#111111", "start", "title", "titles"))
    sizes.append(ts)
    y = 76
    for line in wrap(subtitle, 14.5, W - 2 * MARGIN, 2):
        ops.append(T(MARGIN, y, line, 14.5, "normal", "#3F3F3F", "start", "subtitle", "titles"))
        sizes.append(14.5)
        y += 19
    top, bottom = max(112, y + 12), H - 140
    n = max(1, len(panels))
    rows = 1 if n <= 4 else 2
    cols, gap = max(1, -(-n // rows)), 26
    pw = (W - 2 * MARGIN - (cols - 1) * gap) / cols
    ph = (bottom - top - (rows - 1) * gap) / rows
    geom = []
    for i, p in enumerate(panels):
        r_, c_ = divmod(i, cols)
        geom.append({"id": str(p.get("id") or f"P{i + 1}"), "panel": p,
                     "role": norm_role(p.get("role") or p.get("heading")),
                     "x": MARGIN + c_ * (pw + gap), "y": top + r_ * (ph + gap), "w": pw, "h": ph})
    for g in geom:
        ops += _panel(g, sizes, warns, els, dropped)
    for i in range(len(geom) - 1):
        a, b = geom[i], geom[i + 1]
        if abs(a["y"] - b["y"]) < 1 and b["x"] > a["x"] + 1:
            mid, x1, x2 = a["y"] + a["h"] / 2, a["x"] + a["w"] + 3, b["x"] - 4
            ops += [L(x1, mid, x2, mid, "#6E6E6E", 2.0, f"flow-{i + 1}"),
                    L(x2, mid, x2 - 8, mid - 4.2, "#6E6E6E", 2.0), L(x2, mid, x2 - 8, mid + 4.2, "#6E6E6E", 2.0)]
            flow = strip(b["panel"].get("flow"))
            if flow:
                ops.append(T((x1 + x2) / 2, mid - 9, flow, 9.5, "normal", "#555555", "middle", f"flow-{i + 1}-l", "structure"))
                sizes.append(9.5)
    ly = bottom + 16
    ops.append(L(MARGIN, ly, W - MARGIN, ly, "#DDDDDD", 1.0, "rule-legend", "legend"))
    pal = ["#D55E00", "#0072B2", "#009E73", "#CC79A7", "#555555"]
    entries = [(strip(e.get("label")), strip(e.get("meaning")), pal[i % 5])
               for i, e in enumerate(e for e in (plan.get("legend") or []) if isinstance(e, dict))]
    if not entries:
        entries = [(ROLE[g["role"]][0].title(), strip(g["panel"].get("heading")) or ROLE[g["role"]][0], ROLE[g["role"]][1])
                   for g in geom if g["role"] != "other"]
    lx = MARGIN
    for i, (lab, mea, col) in enumerate(entries[:6]):
        ops.append(R(lx, ly + 12, 11, 11, col, None, 0, 2, f"legend-{i + 1}", "legend"))
        txt = (f"{lab} - {mea}" if mea and mea.lower() != lab.lower() else lab)[:70]
        ops.append(T(lx + 17, ly + 22, txt, 10.5, "normal", "#333333", "start", f"legend-{i + 1}-t", "legend"))
        sizes.append(10.5)
        lx += 51 + tw(txt, 10.5)
    cy = ly + 52
    for line in wrap(caption, 10.8, W - 2 * MARGIN, 2):
        ops.append(T(MARGIN, cy, line, 10.8, "normal", "#4A4A4A", "start", "caption", "footer"))
        sizes.append(10.8)
        cy += 15
    ops.append(T(MARGIN, H - 26, f"{len(geom)} panels - {len(els)} traced elements - editable SVG / vector PDF",
                 9.2, "normal", "#8A8A8A", "start", "footer-note", "footer"))
    sizes.append(9.2)
    ops.sort(key=lambda o: _LI.get(o.get("layer", "content"), 2))
    maxy = max([o["y"] + (o["h"] if o["op"] == "rect" else 0) for o in ops if o["op"] != "line"] or [0])
    return {"W": W, "H": H, "title": title, "subtitle": subtitle, "caption": caption, "ops": ops,
            "elements": els, "warnings": warns, "dropped": dropped,
            "stats": {"panels": len(geom), "items": len(els), "text_ops": sum(o["op"] == "text" for o in ops),
                      "min_font": round(min(sizes), 2) if sizes else 0, "max_y": round(maxy, 1)}}


# --- SVG ---
def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def to_svg(m):
    o = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="ga-title">',
         f'  <title id="ga-title">{_esc(m["title"])}</title>',
         '  <defs><style type="text/css"><![CDATA[text{font-family:Helvetica,Arial,"Noto Sans",sans-serif;}]]></style></defs>']
    cur = None
    for op in m["ops"]:
        lay = op.get("layer", "content")
        if lay != cur:
            if cur:
                o.append("  </g>")
            o.append(f'  <g id="layer-{lay}" data-layer="{lay}">')
            cur = lay
        eid = f' id="{_esc(op["eid"])}"' if op.get("eid") else ""
        if op["op"] == "rect":
            st = f' stroke="{op["stroke"]}" stroke-width="{op["sw"]}"' if op["stroke"] else ""
            rx = f' rx="{op["rx"]}"' if op["rx"] else ""
            o.append(f'    <rect{eid} x="{op["x"]:.1f}" y="{op["y"]:.1f}" width="{op["w"]:.1f}" height="{op["h"]:.1f}" fill="{op["fill"] or "none"}"{st}{rx}/>')
        elif op["op"] == "line":
            o.append(f'    <line{eid} x1="{op["x1"]:.1f}" y1="{op["y1"]:.1f}" x2="{op["x2"]:.1f}" y2="{op["y2"]:.1f}" stroke="{op["stroke"]}" stroke-width="{op["sw"]}" stroke-linecap="round"/>')
        else:
            fw = ' font-weight="bold"' if op["weight"] == "bold" else ""
            an = {"middle": "middle", "end": "end"}.get(op["anchor"], "start")
            o.append(f'    <text{eid} x="{op["x"]:.1f}" y="{op["y"]:.1f}" font-size="{op["size"]:.1f}" fill="{op["color"]}"{fw} text-anchor="{an}">{_esc(op["text"])}</text>')
    if cur:
        o.append("  </g>")
    o.append("</svg>")
    return "\n".join(o) + "\n"


# --- PDF ---
def _rrect(x, yb, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r < 0.3:
        return f"{x:.2f} {yb:.2f} {w:.2f} {h:.2f} re"
    k = 0.5523 * r
    s = f"{x + r:.2f} {yb:.2f} m {x + w - r:.2f} {yb:.2f} l"
    s += f" {x + w - r + k:.2f} {yb:.2f} {x + w:.2f} {yb + r - k:.2f} {x + w:.2f} {yb + r:.2f} c"
    s += f" {x + w:.2f} {yb + h - r:.2f} l"
    s += f" {x + w:.2f} {yb + h - r + k:.2f} {x + w - r + k:.2f} {yb + h:.2f} {x + w - r:.2f} {yb + h:.2f} c"
    s += f" {x + r:.2f} {yb + h:.2f} l"
    s += f" {x + r - k:.2f} {yb + h:.2f} {x:.2f} {yb + h - r + k:.2f} {x:.2f} {yb + h - r:.2f} c"
    s += f" {x:.2f} {yb + r:.2f} l"
    s += f" {x:.2f} {yb + r - k:.2f} {x + r - k:.2f} {yb:.2f} {x + r:.2f} {yb:.2f} c h"
    return s


def to_pdf(m):
    S = PS  # one CTM scales the whole page
    cs, cjk = ["%.4f 0 0 %.4f 0 0 cm" % (S, S)], set()
    for op in m["ops"]:
        if op["op"] == "rect":
            if not op["fill"] and not op["stroke"]:
                continue
            cs.append("q")
            if op["fill"]:
                cs.append("%.3f %.3f %.3f rg" % rgb(op["fill"]))
            if op["stroke"]:
                cs.append("%.3f %.3f %.3f RG %.2f w" % (rgb(op["stroke"]) + (op["sw"],)))
            cs.append(_rrect(op["x"], H - op["y"] - op["h"], op["w"], op["h"], op["rx"]))
            cs.append("B" if (op["fill"] and op["stroke"]) else ("f" if op["fill"] else "S"))
            cs.append("Q")
        elif op["op"] == "line":
            cs.append("q %.3f %.3f %.3f RG %.2f w 1 J %.2f %.2f m %.2f %.2f l S Q"
                      % (rgb(op["stroke"]) + (op["sw"], op["x1"], H - op["y1"], op["x2"], H - op["y2"])))
        elif op["text"]:
            s, size = op["text"], op["size"]
            x = op["x"] - (tw(s, size) / 2.0 if op["anchor"] == "middle" else tw(s, size) if op["anchor"] == "end" else 0)
            base, col = H - op["y"], rgb(op["color"])
            i = 0
            while i < len(s):
                j, is_c = i, ord(s[i]) >= 0x2E80
                while j < len(s) and (ord(s[j]) >= 0x2E80) == is_c:
                    j += 1
                part = s[i:j]
                fn = "F3" if is_c else ("F2" if op["weight"] == "bold" else "F1")
                if is_c:
                    hx = part.encode("utf-16-be").hex().upper()
                    cjk.update(hx[k:k + 4] for k in range(0, len(hx), 4))
                    lit = f"<{hx}>"
                else:
                    lit = "(" + "".join("\\" + c if c in "()\\" else c
                                        for c in part.encode("latin-1", "replace").decode("latin-1")) + ")"
                cs.append("BT /%s %.2f Tf %.3f %.3f %.3f rg 1 0 0 1 %.2f %.2f Tm %s Tj ET"
                          % (fn, size, col[0], col[1], col[2], x, base - size * 0.22, lit))
                x += tw(part, size)
                i = j
    content = "\n".join(cs).encode("latin-1", "replace")
    codes, bf = sorted(cjk), ""
    for i in range(0, len(codes), 100):
        ch = codes[i:i + 100]
        bf += "%d beginbfchar\n" % len(ch) + "".join(f"<{c}> <{c}>\n" for c in ch) + "endbfchar\n"
    tu = ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
          "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
          "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\n"
          "endcodespacerange\n" + bf + "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n").encode("latin-1")

    def stream(d):
        return b"<< /Length %d >>\nstream\n" % len(d) + d + b"\nendstream"

    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W * S:.2f} {H * S:.2f}] /Resources << /ProcSet [/PDF /Text] /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> /Contents 8 0 R >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H /DescendantFonts [7 0 R] /ToUnicode 9 0 R >>",
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>",
            stream(content), stream(tu),
            b"<< /Producer (SciMaster graphical-abstract builder) /Creator (main.py build) >>"]
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, body in enumerate(objs):
        offs.append(len(out))
        out += b"%d 0 obj\n" % (i + 1) + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offs:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 10 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


# --- PNG ---
def to_png(m, png_path):
    """Preview only. Returns (ok, method, note)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        fig = plt.figure(figsize=(W / 100.0, H / 100.0), dpi=300)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        for op in m["ops"]:
            if op["op"] == "rect":
                ax.add_patch(Rectangle((op["x"], op["y"]), op["w"], op["h"], facecolor=op["fill"] or "none",
                                       edgecolor=op["stroke"] or "none", linewidth=op["sw"] * .75, zorder=2))
            elif op["op"] == "line":
                ax.plot([op["x1"], op["x2"]], [op["y1"], op["y2"]], color=op["stroke"], linewidth=op["sw"] * .75,
                        solid_capstyle="round", zorder=3)
            else:
                ax.text(op["x"], op["y"], op["text"], fontsize=op["size"] * .72, color=op["color"], zorder=4,
                        ha={"middle": "center", "end": "right"}.get(op["anchor"], "left"), va="baseline",
                        fontweight="bold" if op["weight"] == "bold" else "normal")
        fig.savefig(png_path, dpi=300, facecolor="white", metadata={"Software": None})
        plt.close(fig)
        return True, "matplotlib Agg @ 300 dpi", ""
    except Exception as exc:
        return False, "none", f"matplotlib unavailable or failed ({exc}); SVG+PDF kept"


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Render plan.json to SVG + PDF (+ PNG preview).")
    ap.add_argument("--plan", default="work/plan.json", help="plan.json written by the agent")
    ap.add_argument("--out", default="output", help="output directory")
    a = ap.parse_args(argv)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = build_model(plan)
    (out / "graphical_abstract.svg").write_text(to_svg(m), encoding="utf-8")
    (out / "graphical_abstract.pdf").write_bytes(to_pdf(m))
    print("png:", to_png(m, str(out / "graphical_abstract.png")))
    print("elements:", len(m["elements"]), "warnings:", m["warnings"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
