#!/usr/bin/env python3
"""render.py - layout engine: one pass feeds a layered editable SVG and a vector PDF
with an embedded TrueType font (stdlib only)."""
import json, re, struct, zlib
from pathlib import Path

INK, MUT, LINE, BG, PL, AC = "#1f2937", "#6b7280", "#cbd5e1", "#ffffff", "#d1d5db", "#1d4ed8"
LB, LP, LE, LN, LS, LL, LT = ("layer-background", "layer-panels", "layer-edges", "layer-nodes",
                              "layer-steps", "layer-legend", "layer-annotations")
LA = [LB, LP, LE, LN, LS, LL, LT]
FL = {"material": ("物料 / 样品流", "#2563eb", None), "energy": ("能量 / 热流", "#ea580c", "7 4"),
      "signal": ("信号 / 控制", "#7c3aed", "2.5 3"), "recycle": ("回流 / 循环", "#16a34a", "7 4"),
      "waste": ("废液 / 尾气", "#b91c1c", "7 4"), "inferred": ("顺序（推断）", "#9ca3af", "4 4")}
RO = {"device": ("#eff6ff", "#2563eb"), "material": ("#f0fdf4", "#16a34a"),
      "measurement": ("#f5f3ff", "#7c3aed"), "waste": ("#fef2f2", "#b91c1c")}
PEND = ("#fffbeb", "#d97706")
CAND = ["/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf",
        "/usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
_F = [None]


class Face:
  """TrueType reader: cmap fmt 4 + advance widths (no rasterising)."""

  def __init__(s, p):
    s.path, d = str(p), open(p, "rb").read()
    s.data, s.name = d, re.sub(r"[^A-Za-z0-9]", "", Path(p).stem)[:18] or "F"
    T = {}
    for i in range(struct.unpack(">H", d[4:6])[0]):
      o = 12 + 16 * i
      T[d[o:o + 4].decode("latin1")] = struct.unpack(">II", d[o + 8:o + 16])
    t = s.t = {k: d[o:o + n] for k, (o, n) in T.items()}
    s.upm = struct.unpack(">H", t["head"][18:20])[0] or 1000
    s.ng, s.nh = struct.unpack(">H", t["maxp"][4:6])[0], struct.unpack(">H", t["hhea"][34:36])[0]
    c, m = t["cmap"], {}
    for i in range(struct.unpack(">H", c[2:4])[0]):
      off = struct.unpack(">I", c[4 + 8 * i + 4:4 + 8 * i + 8])[0]
      if struct.unpack(">H", c[off:off + 2])[0] != 4:
        continue
      sx = struct.unpack(">H", c[off + 6:off + 8])[0]
      seg, so = sx // 2, off + 16 + sx
      en, st = struct.unpack(">%dH" % seg, c[off + 14:off + 14 + sx]), struct.unpack(">%dH" % seg, c[so:so + sx])
      dl = struct.unpack(">%dh" % seg, c[so + sx:so + 2 * sx])
      ro = so + 2 * sx
      rs = struct.unpack(">%dH" % seg, c[ro:ro + sx])
      for j in range(seg):
        if st[j] == 0xFFFF:
          continue
        for ch in range(st[j], min(en[j], 0xFFFE) + 1):
          if rs[j]:
            g = struct.unpack(">H", c[ro + 2 * j + rs[j] + 2 * (ch - st[j]):][:2])[0]
            g = (g + dl[j]) & 0xFFFF if g else 0
          else:
            g = (ch + dl[j]) & 0xFFFF
          if g:
            m.setdefault(ch, g)
    s.cm = m
    w = struct.unpack(">%dH" % s.nh, t["hmtx"][:2 * s.nh])
    s.w = list(w) + [w[-1]] * (s.ng - s.nh) if w else [s.upm] * s.ng

  def gid(s, c):
    return s.cm.get(ord(c), 0)

  def a1000(s, g):
    return int(round(s.w[g] * 1000.0 / s.upm))

  def adv(s, c, z):
    return s.a1000(s.gid(c)) * z / 1000.0


def faces(chars=""):
  if _F[0] is None:
    best, bn = None, -1
    for p in CAND:
      try:
        f = Face(p)
      except Exception:
        continue
      n = len([1 for c in set(chars) if f.gid(c)])
      best, bn = (f, n) if n > bn else (best, bn)
    _F[0] = [best] if best else []
  return _F[0][0] if _F[0] else None


def measure(t, z):
  f = _F[0][0] if _F[0] else None
  return sum(f.adv(c, z) for c in t) if f else sum((1.0 if ord(c) > 0x2E7F else 0.56) * z for c in t)


def wrap(t, mw, z):
  out, cur = [], ""
  for tok in re.findall(r"[\u4e00-\u9fff]|[^\u4e00-\u9fff\s]+|\s+", t):
    if cur.strip() and measure((cur + tok).strip(), z) > mw:
      out.append(cur.strip())
      cur = tok.lstrip()
    else:
      cur += tok
  return (out + [cur.strip()]) if cur.strip() else (out or [""])


def R(x, y, w, h, f=None, s=None, sw=1.0, d=None, l=None):
  return {"k": "rect", "x": x, "y": y, "w": w, "h": h, "fill": f, "stroke": s, "sw": sw, "dash": d, "layer": l}


def P(pts, s, sw=1.7, d=None, l=None):
  return {"k": "poly", "pts": pts, "stroke": s, "sw": sw, "dash": d, "layer": l}


def G(pts, f, l=None):
  return {"k": "poly", "pts": pts, "fill": f, "layer": l}


def T(x, y, t, z=12, c=INK, a="start", l=None):
  return {"k": "text", "x": x, "y": y, "text": t, "size": z, "fill": c, "anchor": a, "layer": l}


def _dep(nodes, edges):
  d = {n["id"]: 0 for n in nodes}
  for _ in range(len(d) + 1):
    ch = 0
    for e in edges:
      a, b = e["from"], e["to"]
      if a in d and b in d and a != b and d[b] < d[a] + 1 and d[a] < 9:
        d[b], ch = d[a] + 1, 1
    if not ch:
      break
  return d


def _tri(p1, p2, z=7.5):
  (x1, y1), (x2, y2) = p1, p2
  d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
  ux, uy = (x2 - x1) / d, (y2 - y1) / d
  return [[x2, y2], [x2 - (ux + uy * .45) * z, y2 - (uy - ux * .45) * z],
          [x2 - (ux - uy * .45) * z, y2 - (uy + ux * .45) * z]]


def _route(x1, y1, w, h, x2, y2, j1, j2):
  a, b = [x1 + w, y1 + h / 2.0], [x2, y2 + h / 2.0]
  if j2 > j1:
    ax, bx = a[0] + 10, b[0] - 10
    return [a, [ax, a[1]], [ax, b[1]], b] if abs(a[1] - b[1]) < 1.5 else [a, [ax, a[1]], [bx, a[1]], [bx, b[1]], b]
  dy = max(y1, y2) + h + 24
  if j2 == j1:
    return [a, [a[0] + 16, a[1]], [a[0] + 16, dy], [x2 + w / 2.0, dy], [x2 + w / 2.0, y2 + h]]
  return [[x1 + w / 2.0, y1 + h], [x1 + w / 2.0, dy], [x2 + w / 2.0, dy], [x2 + w / 2.0, y2 + h]]


def plan(m, W=1200, H=800):
  nodes = [n for n in (m.get("nodes") or []) if n.get("label")]
  ids = {n["id"]: n for n in nodes}
  edges = [e for e in (m.get("edges") or []) if e.get("from") in ids and e.get("to") in ids and e["from"] != e["to"]]
  steps, stages = m.get("steps") or [], m.get("stages") or []
  dep = _dep(nodes, edges)
  mx = max(dep.values()) if dep else 0
  ncol = min(4, max(1, mx + 1))
  cols = {}
  for n in nodes:
    cols.setdefault(dep[n["id"]] if mx < ncol else int(round(dep[n["id"]] * (ncol - 1) / mx)), []).append(n["id"])
  ax, aw, by, bh, bx, bw = 22, 818, 86, H - 212, 856, W - 878
  base, groups = [], []

  def bt(x, y, t, z, c=MUT, a="start", l=LT):
    base.append(T(x, y, t, z, c, a, l))

  base.append(R(0, 0, W, H, BG, l=LB))
  bt(ax, 40, (m.get("title") or "实验装置与技术路线图").strip()[:46], 22, INK, l=LB)
  if m.get("subtitle"):
    bt(ax, 66, m["subtitle"][:118], 11, l=LB)
  bt(W - ax, 36, "FIG. 1 · 装置 / 技术路线示意", 10, l=LB)
  bt(W - ax, 62, "单元 %d · 连接 %d · 步骤 %d · 阶段 %d" % (len(nodes), len(edges), len(steps), len(stages)), 10, l=LB)
  base.append(P([[ax, 76], [W - ax, 76]], LINE, 1, None, LB))
  for x0, wd, t1 in ((ax, aw, "A　装置结构与物料流向"), (bx, bw, "B　技术路线与操作序列")):
    base.append(R(x0, by, wd, bh, "#ffffff", PL, 1, l=LP))
    bt(x0 + 14, by + 26, t1, 13.5, INK, l=LP)
  for x0, t1 in ((ax + aw, "上游 → 下游"), (bx + bw, "%d 步 / %d 阶段" % (len(steps), len(stages)))):
    bt(x0 - 14, by + 26, t1, 10, MUT, "end", LP)
  nw, nh, pos = min(188, int((aw - 28) / max(1, ncol)) - 34), 58, {}
  cw, cy0, chh = aw - 28, by + 40, bh - 50
  for j in sorted(cols):
    g, rg = cols[j], min(112.0, chh / max(1, len(cols[j])))
    for k, nid in enumerate(g):
      pos[nid] = (ax + 14 + (cw / ncol) * (j + .5) - nw / 2.0,
                  cy0 + chh / 2.0 + (k - (len(g) - 1) / 2.0) * rg - nh / 2.0, j)
  for e in edges:
    f = "inferred" if e.get("inferred") else (e.get("flow") or "material")
    f = f if f in FL else "material"
    col, dsh = FL[f][1], FL[f][2]
    x1, y1, j1 = pos[e["from"]]
    x2, y2, j2 = pos[e["to"]]
    pts = _route(x1, y1, nw, nh, x2, y2, j1, j2)
    items = [P(pts, col, 1.7, dsh, LE), G(_tri(pts[-2], pts[-1]), col, LE)]
    lbl = str(e["label"])[:16] if e.get("label") else FL[f][0].split(" / ")[0]
    i = max(range(len(pts) - 1), key=lambda k: (pts[k][0] - pts[k + 1][0]) ** 2 + (pts[k][1] - pts[k + 1][1]) ** 2)
    mxp, myp = (pts[i][0] + pts[i + 1][0]) / 2.0, (pts[i][1] + pts[i + 1][1]) / 2.0
    tw = measure(lbl, 10) + 8
    lx = max(ax + 4, min(W - ax - tw - 4, mxp - tw / 2.0))
    items += [R(lx, myp - 12, tw, 14, "#ffffff", l=LE), T(lx + tw / 2.0, myp - 2, lbl, 10, col, "middle", LE)]
    groups.append({"id": "edge-%s" % e["id"], "layer": LE, "items": items, "src": e,
                   "meta": {"kind": "connection", "label": lbl, "from": e["from"], "to": e["to"], "flow": f}})
  for n in nodes:
    x, y, _ = pos[n["id"]]
    fill, sk = PEND if n.get("pending") else RO.get(n.get("role") or "device", RO["device"])
    items = [R(x, y, nw, nh, fill, sk, 1.6, "5 4" if n.get("pending") else None, LN)]
    lines = wrap(n["label"], nw - 16, 14)[:2]
    ty = y + (20 if len(lines) == 1 else 17)
    items += [T(x + nw / 2.0, ty + i * 15, ln, 13.5, INK, "middle", LN) for i, ln in enumerate(lines)]
    par = " · ".join((n.get("params") or [])[:2]) or ("×%s" % n["qty"] if n.get("qty") else "")
    if par:
      items.append(T(x + nw / 2.0, y + nh - (13 if len(lines) == 2 else 20), par, 9.5, MUT, "middle", LN))
    groups.append({"id": "node-%s" % n["id"], "layer": LN, "items": items, "src": n,
                   "meta": {"kind": "part", "label": n["label"], "role": n.get("role") or "device",
                            "params": n.get("params") or [], "qty": n.get("qty"),
                            "pending": bool(n.get("pending"))}})
  rows = steps or [{"id": s["id"], "no": "S%d" % (i + 1), "text": s["label"], "kind": "stage",
                    "stage": None, "quote": s.get("quote", ""), "locator": s.get("locator", ""),
                    "source": s.get("source", "")} for i, s in enumerate(stages)]
  groups += _pb(rows, stages, bx + 14, by + 42, bw - 28)
  used = [k for k in dict.fromkeys("inferred" if e.get("inferred") else (e.get("flow") or "material")
                                   for e in edges) if k in FL]
  used += [k for k in ("material", "pending") if k not in used]
  ly = H - 112
  base.append(R(ax, ly, W - 2 * ax, 74, "#f8fafc", PL, 1, l=LL))
  bt(ax + 12, ly + 18, "图例 LEGEND · 线型＝流向类型，琥珀虚线框＝待确认", 10, MUT, l=LL)
  for i, k in enumerate(used[:6]):
    lb, col, dsh = ("待确认（pending）", PEND[1], "5 4") if k == "pending" else FL[k]
    r, c = divmod(i, 3)
    ex, ey = ax + 12 + c * ((W - 2 * ax - 24) / 3.0), ly + 36 + r * 17
    base += [P([[ex, ey], [ex + 26, ey]], col, 2.0, dsh, LL), G(_tri([ex, ey], [ex + 26, ey], 5.5), col, LL),
             T(ex + 32, ey + 4, lb, 10, INK, "start", LL)]
    groups.append({"id": "legend-L%d" % (i + 1), "layer": LL, "items": [],
                   "meta": {"kind": "legend", "label": lb, "flow": lb}})
  bt(ax, H - 26, "每个图元带 data-quote / data-locator（见 content_map.json）；虚线框＝待确认；图元 %d"
     % len(groups), 9.5)
  if m.get("caption"):
    bt(ax, H - 10, m["caption"][:118], 9.5)
  return {"items": base, "groups": groups, "W": W, "H": H, "pos": pos}


def _pb(steps, stages, x, y, w):
  base, groups, st, cap = [], [], {s["id"]: s for s in stages}, (7 if stages else 8)
  yy, cur = y, None
  for s in steps[:cap]:
    sg = st.get(s.get("stage"))
    if sg and sg["id"] != cur:
      cur = sg["id"]
      base += [R(x, yy, 3, 15, AC, l=LS), T(x + 9, yy + 11, sg["label"][:22], 10.5, AC, "start", LS)]
      groups.append({"id": "stage-%s" % sg["id"], "layer": LS, "meta": dict(sg, kind="stage")})
      yy += 19
    items = [R(x, yy, w, 42, "#ffffff", LINE, 1.1, "5 4" if s.get("pending") else None, LS),
             R(x + 6, yy + 11, 21, 19, "#eef2ff", AC, 1.1, None, LS),
             T(x + 16.5, yy + 25, str(s.get("no", ""))[:3], 10, AC, "middle", LS)]
    items += [T(x + 33, yy + 18 + i * 14, ln, 11.5, INK, "start", LS)
              for i, ln in enumerate(wrap(s.get("text", ""), w - 46, 11.5)[:2])]
    groups.append({"id": "%s-%s" % (s.get("kind", "step"), s["id"]), "layer": LS, "items": items, "src": s,
                   "meta": {"kind": s.get("kind", "step"), "label": s.get("text", "")[:40], "no": s.get("no"),
                            "pending": bool(s.get("pending"))}})
    yy += 52
  return [{"id": "note-steps", "layer": LS, "items": base, "meta": {"kind": "note", "label": "步骤"}}] + groups


def esc(s):
  return str(s).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _c(h):
  h = (h or "#000000").lstrip("#")
  h = "".join(c * 2 for c in h) if len(h) == 3 else h
  return " ".join("%.3f" % (int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def _n(v):
  return ("%.2f" % v).rstrip("0").rstrip(".") or "0"


def emit(g):
  """One pass over the display list -> per-layer SVG bodies, group bodies, PDF ops."""
  W, H = g["W"], g["H"]
  f = _F[0][0] if _F[0] else None
  po, used, lay, gb = [], {}, {l: [] for l in LA}, {}

  def stroke(it):
    if not it.get("stroke"):
      return ""
    return ' stroke="%s" stroke-width="%.2f"%s' % (it["stroke"], it["sw"],
                                                   ' stroke-dasharray="%s"' % it["dash"] if it.get("dash") else "")

  def draw(items):
    sv = []
    for it in items:
      k = it["k"]
      if k == "rect":
        sv.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"%s/>'
                  % (it["x"], it["y"], it["w"], it["h"], it.get("fill") or "none", stroke(it)))
        if it.get("fill"):
          po.append(_c(it["fill"]) + " rg")
        if it.get("stroke"):
          po.append("%s RG %s w [%s] 0 d" % (_c(it["stroke"]), _n(it["sw"]), it.get("dash") or "[]"))
        po.append("%s %s %s %s re %s" % (_n(it["x"]), _n(H - it["y"] - it["h"]), _n(it["w"]), _n(it["h"]),
                                         "B" if it.get("fill") and it.get("stroke") else ("f" if it.get("fill") else "S")))
      elif k == "poly":
        p, pts = it["pts"], " ".join("%.1f,%.1f" % (q[0], q[1]) for q in it["pts"])
        if it.get("fill"):
          sv.append('<polygon points="%s" fill="%s"/>' % (pts, it["fill"]))
          po.append(_c(it["fill"]) + " rg")
          op = "f"
        else:
          sv.append('<polyline points="%s" fill="none"%s stroke-linejoin="round"/>' % (pts, stroke(it)))
          po.append("%s RG %s w [%s] 0 d 1 J" % (_c(it["stroke"]), _n(it["sw"]), it.get("dash") or "[]"))
          op = "S"
        po.append("%s %s m %s %s" % (_n(p[0][0]), _n(H - p[0][1]), " ".join(
            "%s %s l" % (_n(q[0]), _n(H - q[1])) for q in p[1:]), op))
      elif it["text"].strip():
        t, z = it["text"], it["size"]
        sv.append('<text x="%.1f" y="%.1f" font-family="AR PL SungtiL GB, Noto Sans CJK SC, Helvetica, sans-serif" font-size="%.1f" fill="%s" text-anchor="%s" xml:space="preserve">%s</text>'
                  % (it["x"], it["y"], z, it["fill"], it.get("anchor", "start"), esc(t)))
        x = it["x"] - (measure(t, z) / 2.0 if it.get("anchor") == "middle" else
                       measure(t, z) if it.get("anchor") == "end" else 0)
        if f:
          for c in t:
            used[f.gid(c)] = c
          po.append("BT /F1 %s Tf %s 1 0 0 1 %s %s Tm <%s> Tj ET" % (
              _n(z), _c(it["fill"]), _n(x), _n(H - it["y"]), "".join("%04X" % f.gid(c) for c in t)))
        else:
          a = "".join(c for c in t if 32 < ord(c) < 127).strip()
          if a:
            po.append("BT /F1 %s Tf %s 1 0 0 1 %s %s Tm (%s) Tj ET" % (
                _n(z), _c(it["fill"]), _n(x), _n(H - it["y"]),
                a.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")))
    return sv

  for l in LA:
    lay[l] = draw([it for it in g["items"] if it.get("layer") == l])
  for gr in g["groups"]:
    gb[gr["id"]] = draw(gr.get("items") or [])
  return lay, gb, po, used


def svg(g, title="", desc=""):
  W, H = g["W"], g["H"]
  lay, gb = emit(g)[:2]
  out = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" version="1.1" role="img">'
         % (W, H, W, H), "<title>%s</title>" % esc(title or "实验装置与技术路线图"),
         "<desc>%s</desc>" % esc(desc or "apparatus and technical route, layered editable SVG"),
         '<metadata>{"generator":"apparatus-route-figure","canvas":"%dx%d","layers":%s}</metadata>'
         % (W, H, json.dumps(LA))]
  for l in LA:
    out.append('<g id="%s">' % l)
    out += ["  " + s for s in lay[l]]
    for gr in g["groups"]:
      if gr["layer"] != l:
        continue
      mt = dict(gr.get("meta") or {}, **(gr.get("src") or {}))
      out.append('  <g id="%s" %s>' % (esc(gr["id"]), " ".join(
          'data-%s="%s"' % (k, esc(str(mt[k])[:400])) for k in
          ("kind", "quote", "locator", "source", "resolution", "role") if mt.get(k))))
      out += ["    " + s for s in gb[gr["id"]]]
      out.append("  </g>")
    out.append("</g>")
  return "\n".join(out + ["</svg>"]) + "\n"


def _tou(m):
  it = sorted(m.items())
  h = ["/CIDInit /ProcSet findresource begin 12 dict begin begincmap",
       "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
       "/CMapName /Adobe-Identity-UCS def /CMapType 2 def",
       "1 begincodespacerange <0000> <FFFF> endcodespacerange"]
  for i in range(0, len(it), 100):
    h.append("%d beginbfchar" % len(it[i:i + 100]))
    h += ["<%04X> <%s>" % (g, "%04X" % ord(c) if ord(c) <= 0xFFFF else "%08X" % ord(c)) for g, c in it[i:i + 100]]
    h.append("endbfchar")
  return "\n".join(h + ["endcmap CMapName currentdict /CMap defineresource pop end end"])


def pdf(g):
  W, H = g["W"], g["H"]
  f = _F[0][0] if _F[0] else None
  po, used = emit(g)[2:]
  cs = zlib.compress("\n".join(po).encode("latin1"), 9)
  objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
          ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << %s >> >> /Contents 4 0 R >>"
           % (W, H, "/F1 5 0 R" if f else "/F1 6 0 R")).encode(),
          b"<< /Length %d /Filter /FlateDecode >>stream\n" % len(cs) + cs + b"\nendstream"]
  if f:
    objs += [("<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H /DescendantFonts [6 0 R] "
              "/ToUnicode 8 0 R >>" % f.name).encode(),
             ("<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s /CIDSystemInfo << /Registry (Adobe) "
              "/Ordering (Identity) /Supplement 0 >> /FontDescriptor 7 0 R /W [%s] /DW 1000 /CIDToGIDMap "
              "/Identity >>" % (f.name, " ".join("%d [%d]" % (g, f.a1000(g)) for g in sorted(used)) or "0 [500]")).encode(),
             ("<< /Type /FontDescriptor /FontName /%s /Flags 4 /FontBBox [-200 -250 1200 900] /ItalicAngle 0 "
              "/Ascent 880 /Descent -120 /CapHeight 700 /StemV 80 /FontFile2 9 0 R >>" % f.name).encode()]
    tb = _tou(used).encode("latin1")
    z = zlib.compress(f.data, 9)
    objs += [b"<< /Length %d >>stream\n" % len(tb) + tb + b"\nendstream",
             ("<< /Length %d /Length1 %d /Filter /FlateDecode >>stream\n"
              % (len(z), len(f.data))).encode() + z + b"\nendstream"]
  else:
    objs += [b"null", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
  buf, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
  for i, o in enumerate(objs):
    offs.append(len(buf))
    buf += ("%d 0 obj\n" % (i + 1)).encode() + o + b"\nendobj\n"
  xr, n = len(buf), len(objs) + 1
  buf += ("xref\n0 %d\n" % n).encode() + b"0000000000 65535 f \n"
  buf += "".join("%010d 00000 n \n" % o for o in offs).encode()
  buf += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n, xr)).encode()
  return bytes(buf)


def build(model, outdir, W=1200, H=None):
  """Layout once; write figure.svg + figure.pdf."""
  outdir = Path(outdir)
  outdir.mkdir(parents=True, exist_ok=True)
  H = int(H or (900 if len(model.get("nodes") or []) > 10 or len(model.get("steps") or []) > 8 else 800))
  faces(json.dumps(model, ensure_ascii=False))
  g, ttl, cap = plan(model, W, H), model.get("title") or "", model.get("caption") or ""
  doc = svg(g, ttl, cap)
  (outdir / "figure.svg").write_text(doc, encoding="utf-8")
  (outdir / "figure.pdf").write_bytes(pdf(g))
  return {"grid": g, "canvas": (W, H), "layers": LA,
          "deterministic": doc == svg(plan(model, W, H), ttl, cap)}


if __name__ == "__main__":
  import sys
  if "--help" in sys.argv:
    print(__doc__)
  raise SystemExit(0)
