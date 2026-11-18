#!/usr/bin/env python3
"""Deterministic figure renderer: one display list -> SVG + PDF + PNG (stdlib only).

SVG and PDF are emitted in one pass over the same primitives, so the editable source
and the vector export cannot disagree; the PNG reuses the same geometry.
"""
import math
import sys
import zlib

W_DEF, BW, BH, M, GAP, WHITE = 1240, 156, 58, 32, 46, "#ffffff"
KIND = {"protein": "#dce9f7", "gene": "#e4f2dd", "complex": "#f0def7", "cell": "#fff1d6",
        "metabolite": "#eeeeee", "ligand": "#fde9dd", "phenotype": "#f5e2e2", "unspecified": "#f2f2f2"}
REL = {"activation": ("#1f6fb2", None, "fill"), "inhibition": ("#c0392b", None, "bar"),
       "binding": ("#2e7d32", None, "open"), "modification": ("#7b1fa2", "7,4", "fill"),
       "transport": ("#e67e22", None, "double"), "indirect": ("#777777", "2,4", "open"),
       "unspecified": ("#999999", "4,4", "open")}
_AL = ("activation:activate activation activates promote promotes induce induces upregulate upregulates "
       "stimulate 促进 激活 上调|inhibition:inhibit inhibits inhibition repress represses suppress suppresses "
       "block feedback 抑制 下调 阻断 负反馈|binding:bind binds binding interacts interact recruit recruits "
       "dimerize associate 结合 募集 互作|modification:phosphorylate phosphorylates phosphorylation "
       "ubiquitinate ubiquitinates ubiquitination cleave cleavage methylate acetylate 磷酸化 泛素化 修饰 剪切|"
       "transport:transport transports translocate translocation secrete secretes release releases traffic "
       "转运 转位 分泌 释放|indirect:indirect complex|unspecified:unspecified unknown")
ALIAS = {}
for _grp in _AL.split("|"):
    _k, _ws = _grp.split(":")
    ALIAS.update(dict((w.lower(), _k) for w in _ws.split()))
HEAD = {"activation": "activation (arrowhead)", "inhibition": "inhibition (T-bar)",
        "binding": "binding / recruitment (open head)", "modification": "modification: dashed, labelled (P, Ub)",
        "transport": "transport / translocation (double head)", "indirect": "indirect or inferred (dotted)",
        "unspecified": "type or direction not stated in source (grey)"}


def rtype(t):
    k = str(t or "").strip().lower().replace("-", "_").replace(" ", "_")
    return ALIAS.get(k) or (k if k in REL else "unspecified")


def txt(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(txt(x) for x in v)
    if isinstance(v, dict):
        return txt(v.get("label") or v.get("name") or v.get("text") or v.get("id"))
    return str(v).strip()


def sid(s):
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(s)).strip("_") or "x"


def norm_plan(plan):
    """Tolerant: never raises on odd-but-usable plans; drops relations to unknown nodes."""
    plan = plan if isinstance(plan, dict) else {}
    comps = []
    for i, c in enumerate(plan.get("compartments") or []):
        d = c if isinstance(c, dict) else {"label": txt(c)}
        try:
            order = int(d.get("order", i))
        except Exception:
            order = i
        cid = txt(d.get("id")) or "c%d" % i
        comps.append({"id": cid, "label": txt(d.get("label")) or cid, "order": order})
    comps.sort(key=lambda x: x["order"])
    cids = [c["id"] for c in comps]
    ents, seen = [], set()
    for i, e in enumerate(plan.get("entities") or []):
        e = e if isinstance(e, dict) else {"label": txt(e)}
        eid = txt(e.get("id")) or txt(e.get("label")) or "e%d" % i
        while eid in seen:
            eid += "_"
        seen.add(eid)
        comp = txt(e.get("compartment"))
        if comp not in cids:
            if "unspecified" not in cids:
                cids.append("unspecified")
                comps.append({"id": "unspecified", "label": "unspecified / not stated", "order": 999})
            comp = "unspecified"
        ents.append({"id": eid, "label": txt(e.get("label")) or eid,
                     "kind": (txt(e.get("kind")) or "unspecified").lower(), "compartment": comp,
                     "evidence": e.get("evidence") or {}, "encoding": e.get("encoding")})
    out = {"title": txt(plan.get("title")), "subtitle": txt(plan.get("subtitle")), "compartments": comps,
           "entities": ents, "relations": [], "citation": txt(plan.get("citation")),
           "gaps": [txt(g) for g in (plan.get("gaps") or []) if txt(g)],
           "legend_extra": [txt(g) for g in (plan.get("legend_extra") or []) if txt(g)]}
    byid = dict((e["id"].lower(), e["id"]) for e in ents)
    for i, r in enumerate(plan.get("relations") or []):
        if not isinstance(r, dict):
            continue
        s, t = byid.get(txt(r.get("source")).lower()), byid.get(txt(r.get("target")).lower())
        if s and t and s != t:
            out["relations"].append({"id": txt(r.get("id")) or "r%d" % (i + 1), "source": s, "target": t,
                                     "type": rtype(r.get("type") or r.get("relation")),
                                     "label": txt(r.get("label")), "evidence": r.get("evidence") or {}})
    return out


def wrap(s, maxc, maxl=2):
    out, cur = [], ""
    for w in str(s).split():
        if len(cur) + len(w) + 1 <= maxc:
            cur = (cur + " " + w).strip()
        elif cur:
            out.append(cur)
            cur = w
        else:
            out.extend([w[:maxc], w[maxc:]])
            cur = ""
    out = out + ([cur] if cur else [])
    out = out or [""]
    if len(out) > maxl:
        out = out[:maxl]
        out[-1] = out[-1][:max(1, maxc - 1)] + "\u2026"
    return out


def R(L, g, x, y, w, h, fill=WHITE, stroke=None, sw=1.2, rx=0, grp=None):
    L.append(("R", g, grp, x, y, w, h, fill, stroke, sw, rx))


def T(L, g, x, y, s, size=12, anchor="start", fill="#1a1a1a", bold=False, grp=None):
    L.append(("T", g, grp, x, y, str(s), size, anchor, fill, bold))


def S(L, g, pts, stroke="#333333", sw=1.6, dash=None, grp=None):
    L.append(("S", g, grp, list(pts), stroke, sw, dash))


def F(L, g, pts, fill="#333333", grp=None):
    L.append(("F", g, grp, list(pts), fill))


def arrow(L, g, pts, key_, label=None, grp=None):
    """Head shape + dash carry the semantics: filled = activation, bar = inhibition, etc."""
    c, dash, head = REL[key_]
    S(L, g, pts, c, 1.8, dash, grp)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    n = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / n, (y2 - y1) / n
    px, py = -uy, ux

    def tri(x, y, vx, vy):
        F(L, g, [(x, y), (x - vx * 11 + px * 5.2, y - vy * 11 + py * 5.2),
                 (x - vx * 11 - px * 5.2, y - vy * 11 - py * 5.2)], c, grp)

    if head == "fill":
        tri(x2, y2, ux, uy)
    elif head == "open":
        bx, by = x2 - ux * 11, y2 - uy * 11
        S(L, g, [(bx + px * 5.2, by + py * 5.2), (x2, y2), (bx - px * 5.2, by - py * 5.2)], c, 1.6, None, grp)
    elif head == "bar":
        S(L, g, [(x2 - px * 8, y2 - py * 8), (x2 + px * 8, y2 + py * 8)], c, 2.8, None, grp)
    else:
        tri(x2, y2, ux, uy)
        tri(pts[0][0], pts[0][1], -ux, -uy)
    if label:
        T(L, g, pts[0][0] + 7, pts[0][1] - 7, label, 10, "start", c, False, grp)


def build_display(plan, meta=None):
    """Return (items, width, height, stats). Deterministic; degrades instead of raising."""
    meta = meta or {}
    p = norm_plan(plan)
    L, W, y = [], W_DEF, 0
    for i, ln in enumerate(wrap(p["title"] or "Biological mechanism figure", 95, 2)):
        T(L, "title", M, 40 + 27 * i, ln, 22, "start", "#1a1a1a", True)
    y = 40 + 27 * min(2, len(wrap(p["title"] or "x", 95, 2)))
    if p["subtitle"]:
        T(L, "title", M, y + 12, p["subtitle"], 12, "start", "#555555")
        y += 22
    T(L, "title", M, y + 12, meta.get("byline", "compartments run upstream (top) to downstream (bottom)"),
      10, "start", "#888888")
    y += 26
    pos, boxes = {}, 0
    order = [c for c in p["compartments"] if any(e["compartment"] == c["id"] for e in p["entities"])] or \
            [{"id": "unspecified", "label": "unspecified / not stated", "order": 999}]
    x0, x1 = M + 120, W - 40
    for ci, comp in enumerate(order):
        ents = [e for e in p["entities"] if e["compartment"] == comp["id"]]
        per = max(1, min(4, int((x1 - x0) // (BW + 44))))
        rows = max(1, int(math.ceil(len(ents) / float(per))))
        bh = 34 + rows * (BH + 26) + 10
        R(L, "compartments", M, y, W - 2 * M, bh, "#f7fafc" if ci % 2 == 0 else WHITE, "#c9d6e3", 1.0, 3)
        T(L, "compartments", M + 10, y + 20, comp["label"], 12, "start", "#2c3e50", True)
        for ri in range(rows):
            row = ents[ri * per:(ri + 1) * per]
            if not row:
                continue
            ry = y + 32 + ri * (BH + 26)
            span = (x1 - x0) / float(len(row))
            for ei, e in enumerate(row):
                bx = x0 + ei * span + max(0, (span - BW) / 2.0)
                pos[e["id"]] = (bx, ry, BW, BH)
                grp = "ent-%s" % sid(e["id"])
                R(L, "entities", bx, ry, BW, BH, KIND.get(e["kind"], KIND["unspecified"]), "#33475b", 1.4, 7, grp)
                lines = wrap(e["label"], 19, 2)
                ty = ry + (BH - len(lines) * 15) / 2.0 + 11
                for li, ln in enumerate(lines):
                    T(L, "entities", bx + BW / 2.0, ty + li * 15, ln, 12, "middle", "#1a1a1a", False, grp)
                if e["kind"] in KIND and e["kind"] != "unspecified":
                    T(L, "entities", bx + BW - 7, ry + BH - 7, e["kind"], 9, "end", "#5a6b7b", False, grp)
                if e.get("encoding"):
                    enc = e["encoding"]
                    T(L, "entities", bx + 6, ry + 12,
                      txt(enc.get("label") or enc.get("value")) if isinstance(enc, dict) else txt(enc),
                      9, "start", "#1f3b57", False, grp)
                boxes += 1
        y += bh + GAP

    types, up = [], 0
    for r in p["relations"]:
        ax, ay, aw, ah = pos[r["source"]]
        bx, by, bw, bh = pos[r["target"]]
        acx, acy, bcx, bcy = ax + aw / 2.0, ay + ah / 2.0, bx + bw / 2.0, by + bh / 2.0
        if bcy > acy + ah * 0.6:                      # downstream: cross-band orthogonal drop
            yc = (ay + ah + by) / 2.0
            pts = [(acx, ay + ah), (acx, yc), (bcx, yc), (bcx, by)]
        elif bcy < acy - ah * 0.6:                    # upstream: side lane (feedback loops)
            up += 1
            xl = W - M - 10 - 12 * ((up - 1) % 5)
            pts = [(ax + aw, acy), (xl, acy), (xl, bcy), (bx + bw, bcy)]
        elif bx > ax + aw:
            pts = [(ax + aw, acy), (bx, acy)]
        elif bx + bw < ax:
            pts = [(ax, acy), (bx + bw, acy)]
        else:
            yc = ay + ah + 20
            pts = [(acx, ay + ah), (acx, yc), (bcx, yc), (bcx, by + bh)]
        arrow(L, "relations", pts, r["type"], r["label"] or None, "rel-%s" % sid(r["id"]))
        if r["type"] not in types:
            types.append(r["type"])

    ly = y + 4
    T(L, "legend", M, ly + 18, "Legend", 13, "start", "#1a1a1a", True)
    ly += 34
    kinds = []
    for e in p["entities"]:
        if e["kind"] not in kinds:
            kinds.append(e["kind"])
    col2 = M + 420
    for i, k in enumerate(kinds):
        R(L, "legend", M, ly + i * 22 - 11, 22, 14, KIND.get(k, KIND["unspecified"]), "#33475b", 1.2, 3)
        T(L, "legend", M + 30, ly + i * 22, "node fill: %s" % k, 11)
    for i, k in enumerate(types):
        yy = ly + i * 22
        S(L, "legend", [(col2, yy - 5), (col2 + 46, yy - 5)], REL[k][0], 1.8, REL[k][1])
        arrow(L, "legend", [(col2, yy - 5), (col2 + 52, yy - 5)], k)
        T(L, "legend", col2 + 62, yy, HEAD[k], 11)
    ly += max(len(kinds), len(types), 1) * 22 + 6
    notes = p["legend_extra"] or [
        "Edge direction = upstream source -> downstream target, as stated by the evidence quote.",
        "Grey dotted edges mark relations whose type or direction the source does not state."]
    for i, n in enumerate(notes[:6]):
        T(L, "legend", M, ly + i * 18, "- " + n, 11, "start", "#333333")
    ly += min(len(notes), 6) * 18 + 10
    if p["gaps"]:
        T(L, "notes", M, ly + 14, "Gaps and unverified items", 12, "start", "#8a4b08", True)
        hh = 18 * min(len(p["gaps"]), 8) + 14
        R(L, "notes", M, ly + 4, W - 2 * M, hh, "#fff8e6", "#e0b060", 1.0, 4)
        for i, gp in enumerate(p["gaps"][:8]):
            T(L, "notes", M + 12, ly + 26 + i * 18, "- " + wrap(gp, 118, 1)[0], 11, "start", "#6b4a12")
        ly += hh + 16
    if meta.get("sources_line"):
        T(L, "notes", M, ly + 16, wrap(meta["sources_line"], 150, 1)[0], 9, "start", "#777777")
        ly += 20
    T(L, "notes", M, ly + 16, meta.get("footer", "graphics-03 skill; editable source = figure.svg"),
      9, "start", "#999999")
    stats = {"entities": len(p["entities"]), "relations": len(p["relations"]), "bands": len(order),
             "types": types, "plan": p, "boxes": boxes,
             "unplaced": [e["id"] for e in p["entities"] if e["id"] not in pos]}
    return L, W, int(ly + 34), stats


def _rgb(h):
    h = (h or "#000000").lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        return (0.0, 0.0, 0.0)


def vector(L, W, H, meta=None):
    """One pass over the primitives -> (svg text, pdf bytes, chars dropped)."""
    meta = meta or {}
    S_, lost, pw, ph = 0.75, [0], W * 0.75, H * 0.75
    n = lambda v: ("%.2f" % v).rstrip("0").rstrip(".") or "0"
    xe = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

    def pe(s):
        out = []
        for ch in str(s):
            try:
                ch.encode("latin-1")
                out.append(ch)
            except UnicodeEncodeError:
                lost[0] += 1
        return "".join(out).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    Y = lambda v: ph - v * S_
    pp = lambda pts: " ".join("%s %s %s" % (n(q[0] * S_), n(Y(q[1])), "m" if i == 0 else "l")
                              for i, q in enumerate(pts))
    so = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
          'font-family="DejaVu Sans, Helvetica, Arial, sans-serif">' % (W, H, W, H),
          "<title>%s</title>" % xe(meta.get("title", "mechanism figure")),
          "<desc>%s</desc>" % xe(meta.get("desc", "biological mechanism or pathway diagram; every text run is editable")),
          '<rect id="layer-background" x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H)]
    ops, cg, cgrp = [], None, None
    for it in L:
        if it[1] != cg:
            if cgrp:
                so.append("</g>")
                cgrp = None
            if cg:
                so.append("</g>")
            so.append('<g id="layer-%s">' % it[1])
            cg = it[1]
        if it[2] != cgrp:
            if cgrp:
                so.append("</g>")
            if it[2]:
                so.append('<g id="%s">' % sid(it[2]))
            cgrp = it[2]
        t = it[0]
        if t == "R":
            _, _, _, x, y, w, h, fill, stroke, sw, rx = it
            so.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="%s"%s/>' % (
                x, y, w, h, rx, fill, ' stroke="%s" stroke-width="%.1f"' % (stroke, sw) if stroke else ""))
            r, g, b = _rgb(fill)
            ops.append("%s %s %s rg %s %s %s %s re f" % (n(r), n(g), n(b), n(x * S_), n(Y(y + h)), n(w * S_), n(h * S_)))
        elif t == "T":
            _, _, _, x, y, s, size, anchor, fill, bold = it
            so.append('<text x="%.1f" y="%.1f" font-size="%s" text-anchor="%s" fill="%s"%s>%s</text>' % (
                x, y, size, anchor, fill, ' font-weight="bold"' if bold else "", xe(s)))
            p2 = pe(s)
            if p2.strip():
                fs = size * S_
                tx = x * S_ - 0.52 * fs * len(p2) * (0.5 if anchor == "middle" else (1.0 if anchor == "end" else 0.0))
                r, g, b = _rgb(fill)
                ops.append("BT /%s %s Tf %s %s %s rg %s %s Td (%s) Tj ET" % (
                    "F2" if bold else "F1", n(fs), n(r), n(g), n(b), n(tx), n(Y(y)), p2))
        elif t == "S":
            _, _, _, pts, stroke, sw, dash = it
            so.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.1f"%s/>' % (
                " ".join("%.1f,%.1f" % q for q in pts), stroke, sw, ' stroke-dasharray="%s"' % dash if dash else ""))
            r, g, b = _rgb(stroke)
            ops.append("%s %s %s RG %s w %s %s S [] 0 d" % (
                n(r), n(g), n(b), n(sw * S_),
                "[%s] 0 d" % " ".join(n(float(v) * S_) for v in dash.split(",")) if dash else "[] 0 d", pp(pts)))
        else:
            so.append('<polygon points="%s" fill="%s"/>' % (" ".join("%.1f,%.1f" % q for q in it[3]), it[4]))
            r, g, b = _rgb(it[4])
            ops.append("%s %s %s rg %s h f" % (n(r), n(g), n(b), pp(it[3])))
    so += (["</g>"] if cgrp else []) + (["</g>"] if cg else []) + ["</svg>"]
    stream = zlib.compress("\n".join(ops).encode("latin-1", "replace"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> "
             "/Contents 4 0 R >>" % (n(pw), n(ph))).encode(),
            b"<< /Length " + str(len(stream)).encode() + b" /Filter /FlateDecode >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            ("<< /Title (%s) /Producer (graphics-03 renderer, python stdlib) >>" % pe(meta.get("title", ""))).encode()]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += ("xref\n0 %d\n" % (len(objs) + 1)).encode() + b"0000000000 65535 f \n"
    for o in offs:
        out += ("%010d 00000 n \n" % o).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, len(objs), xref)).encode()
    return "\n".join(so) + "\n", bytes(out), lost[0]


def render_all(plan, meta=None):
    """Plan dict -> {svg, pdf, geometry}. Never raises."""
    L, W, H, stats = build_display(plan, meta)
    stats["svg"], stats["pdf"], stats["pdf_chars_lost"] = vector(L, W, H, meta)
    stats.update({"width": W, "height": H, "items": len(L)})
    return stats


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("render.py - deterministic mechanism-figure emitter used by main.py build.\n"
              "  python3 -B render.py --help      this text\n"
              "  python3 -B render.py --selftest  render a 2-node plan, print artefact sizes\n"
              "plan dict -> display list -> SVG (editable text) + single-page vector PDF.")
        sys.exit(0)
    demo = {"title": "render selftest", "compartments": [{"id": "c", "label": "Cytoplasm", "order": 0}],
            "entities": [{"id": "A", "label": "A", "kind": "protein", "compartment": "c"},
                         {"id": "B", "label": "B", "kind": "protein", "compartment": "c"}],
            "relations": [{"id": "r1", "source": "A", "target": "B", "type": "inhibition"}],
            "gaps": ["demo only"]}
    st = render_all(demo)
    print("W=%s H=%s svg=%d pdf=%d" % (st["width"], st["height"], len(st["svg"]), len(st["pdf"])))
    sys.exit(0)
