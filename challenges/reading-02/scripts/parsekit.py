"""parsekit.py - stdlib-only primitives for reading-02: PNG raster figure
structure (frame, ticks, colour series, calibration) + literal table/PDF text.
No third-party imports, no network, no CWD dependence.
Coordinates are ORIGINAL image px; `analysis_scale` gives the +/- quantisation.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, re, struct, zipfile, zlib
from pathlib import Path
import xml.etree.ElementTree as ET

SIG = b"\x89PNG\r\n\x1a\n"
MAXP = 2_200_000
CH = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def sniff(p):
    """Coarse kind from magic bytes (never from the file name)."""
    try: head = Path(p).read_bytes()[:16]
    except OSError: return "unreadable"
    if head.startswith(SIG): return "png"
    if head.startswith(b"\xff\xd8\xff"): return "jpeg"
    if head[:4] == b"%PDF": return "pdf"
    if head[:4] == b"PK\x03\x04":
        try: names = set(zipfile.ZipFile(p).namelist())
        except Exception: return "zip"
        if any(n.startswith("xl/") for n in names): return "xlsx"
        return "docx" if any(n.startswith("word/") for n in names) else "zip"
    for s, k in ((b"BM", "bmp"), (b"II*\x00", "tiff"), (b"MM\x00*", "tiff")):
        if head.startswith(s): return k
    try: txt = Path(p).read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError): return "binary"
    return "json" if txt.lstrip()[:1] in "{[" else ("csv" if txt.count(",") >= 3 else "text")


def read_png(p):
    """Decode 8-bit non-interlaced PNG to RGB rows."""
    data = Path(p).read_bytes()
    if not data.startswith(SIG): raise ValueError("not a PNG stream")
    pos, idat, plte, ihdr = 8, [], None, None
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR": ihdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT": idat.append(body)
        elif typ == b"PLTE": plte = body
        elif typ == b"IEND": break
        pos += 12 + ln
    if not ihdr or not idat: raise ValueError("PNG missing IHDR/IDAT")
    w, h, bd, ct, _c, _f, inter = ihdr
    if bd != 8 or ct not in CH: raise ValueError("unsupported bd=%d ct=%d" % (bd, ct))
    if inter != 0: raise ValueError("interlaced PNG")
    nch, stride = CH[ct], w * CH[ct]
    raw = zlib.decompress(b"".join(idat))
    if len(raw) < (stride + 1) * h: raise ValueError("truncated PNG data")
    prev, rows, pos = bytearray(stride), [], 0
    for _y in range(h):
        ft, pos = raw[pos], pos + 1
        line, pos = bytearray(raw[pos:pos + stride]), pos + stride
        if ft > 4: raise ValueError("bad PNG filter %d" % ft)
        if ft:
            for i in range(nch, stride):
                a = line[i - nch] if i >= nch else 0
                b, c = prev[i], (prev[i - nch] if i >= nch else 0)
                if ft == 1: add = a
                elif ft == 2: add = b
                elif ft == 3: add = (a + b) >> 1
                else:
                    pp = a + b - c
                    pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                    add = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + add) & 255
        rows.append(line)
        prev = line
    def rgb(line):
        if ct == 2: return bytearray(line)
        if ct == 6: return bytearray(b for x in range(w) for b in line[4 * x:4 * x + 3])
        if ct in (0, 4):
            st = 1 if ct == 0 else 2
            return bytearray(v for x in range(w) for v in (line[st * x],) * 3)
        if not plte: raise ValueError("no PLTE chunk")
        return bytearray(b for x in range(w) for b in plte[3 * line[x]:3 * line[x] + 3])
    return {"w": w, "h": h, "rows": [rgb(line) for line in rows]}


def load_image(p):
    """Decode a raster to RGB rows, strided down when large."""
    kind = sniff(p)
    if kind != "png": raise ValueError("no stdlib decoder for kind=%s (PNG only)" % kind)
    img = read_png(p)
    w, h, scale = img["w"], img["h"], 1
    if w * h > MAXP:
        scale = int(math.ceil(math.sqrt(w * h / MAXP)))
        rows = []
        for y in range(0, h, scale):
            src, r = img["rows"][y], bytearray()
            for x in range(0, w, scale): r += src[3 * x:3 * x + 3]
            rows.append(r)
        img = {"w": len(rows[0]) // 3, "h": len(rows), "rows": rows}
    return img, {"format": "png", "decoder": "stdlib zlib+unfilter", "orig_w": w,
                 "orig_h": h, "analysis_scale": scale, "analysis_w": img["w"],
                 "analysis_h": img["h"]}


def dist(p, q):
    return max(abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2]))


def px(rows, y, x):
    i = 3 * x
    return (rows[y][i], rows[y][i + 1], rows[y][i + 2])


def background(img):
    """Modal colour of a sparse sample = canvas / paper colour."""
    from collections import Counter
    w, h, rows = img["w"], img["h"], img["rows"]
    c, sx, sy = Counter(), max(1, w // 80), max(1, h // 80)
    for y in range(0, h, sy):
        for x in range(0, w, sx): c[px(rows, y, x)] += 1
    return tuple(c.most_common(1)[0][0])


def group_ints(vals, gap=1):
    out = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= gap: out[-1].append(v)
        else: out.append([v])
    return out


def longest_run(img, bg, horizontal=True, thr=60, min_frac=0.45):
    """Long ink runs -> grouped spines."""
    w, h, rows = img["w"], img["h"], img["rows"]
    hits, outer, inner = [], h if horizontal else w, w if horizontal else h
    for o in range(outer):
        run = best = 0
        for i in range(inner):
            p = px(rows, o, i) if horizontal else px(rows, i, o)
            if dist(p, bg) > thr:
                run += 1
                best = max(best, run)
            else: run = 0
        if best >= min_frac * inner: hits.append(o)
    return group_ints(hits)


def ticks(img, bg, spine, box, axis="x", band=14, thr=60, min_dark=3):
    """Outward tick marks along a spine -> cluster centres (analysis px)."""
    w, h, rows = img["w"], img["h"], img["rows"]
    pos = []
    if axis == "x":
        rng, lim = range(max(0, spine + 1), min(h, spine + band)), min(w, box[2] + 1)
        for x in range(box[0], lim):
            if sum(1 for y in rng if dist(px(rows, y, x), bg) > thr) >= min_dark: pos.append(x)
    else:
        rng, lim = range(max(0, spine - band), max(0, spine)), min(h, box[3] + 1)
        for y in range(box[1], lim):
            if sum(1 for x in rng if dist(px(rows, y, x), bg) > thr) >= min_dark: pos.append(y)
    return [sum(g) / len(g) for g in group_ints(pos) if len(g) <= max(6, band)]


def spacing_report(c):
    """Tick-gap geometry: uniform major gaps and within-decade minor gaps."""
    gaps = [round(c[i + 1] - c[i], 2) for i in range(len(c) - 1)]
    if len(c) < 3:
        return {"n": len(c), "gaps": gaps, "uniform_major": None, "minor_gaps": [],
                "minor_pattern": "undetermined"}
    big, minor = max(gaps), [g for g in gaps if g <= 0.6 * max(gaps)]
    pat = "undetermined"
    if len(minor) >= 3:
        pat = "decreasing (log-decade style)" if minor[0] > minor[-1] * 1.3 else "even (linear style)"
    return {"n": len(c), "gaps": gaps,
            "uniform_major": (big - min(gaps)) <= 0.12 * big, "minor_gaps": minor,
            "minor_pattern": pat}


def color_clusters(img, box, bg, thr=45, top=10, min_count=40):
    """Saturated non-background colour clusters in the plot box."""
    from collections import defaultdict
    w, rows = img["w"], img["rows"]
    acc = defaultdict(lambda: [0, 0, 0, 0])
    for y in range(box[1], min(box[3], img["h"])):
        for x in range(box[0], min(box[2], w)):
            p = px(rows, y, x)
            if dist(p, bg) <= thr or max(p) - min(p) < 42: continue  # skip bg/achromatic ink
            a = acc[(p[0] >> 5, p[1] >> 5, p[2] >> 5)]
            a[0] += 1
            a[1] += p[0]
            a[2] += p[1]
            a[3] += p[2]
    cl = [{"rgb": [round(a[1] / a[0]), round(a[2] / a[0]), round(a[3] / a[0])],
           "pixels": a[0]} for _k, a in acc.items() if a[0] >= min_count]
    cl.sort(key=lambda d: -d["pixels"])
    return cl[:top]


def mask_for(img, color, tol=60, box=None):
    """Mask of one series colour inside the plot box."""
    w, h, rows = img["w"], img["h"], img["rows"]
    x0, y0, x1, y1 = box or (0, 0, w, h)
    x1, y1 = min(x1, w), min(y1, h)
    m = [bytearray(x1 - x0) for _ in range(max(0, y1 - y0))]
    for y in range(y0, y1):
        row = m[y - y0]
        for x in range(x0, x1):
            p = px(rows, y, x)
            if abs(p[0] - color[0]) <= tol and abs(p[1] - color[1]) <= tol \
                    and abs(p[2] - color[2]) <= tol:
                row[x - x0] = 1
    return m


def components(m, min_px=12, max_px=60000):
    """8-connected components (row runs + union-find)."""
    h, w = len(m), len(m[0]) if m else 0
    lab = [[0] * w for _ in range(h)]
    par = []

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for y in range(h):
        prow = lab[y - 1] if y else None
        x = 0
        while x < w:
            if not m[y][x]:
                x += 1
                continue
            x2 = x
            while x2 < w and m[y][x2]: x2 += 1
            nb = {find(prow[i]) for i in range(x, x2) if prow and prow[i]}
            if nb:
                idn = min(nb)
                for o in nb:
                    if o != idn: par[find(o)] = idn
            else:
                par.append(len(par)); idn = len(par) - 1
            for i in range(x, x2): lab[y][i] = idn
            x = x2
    bx = {}
    for y in range(h):
        for x in range(w):
            if not lab[y][x]: continue
            r = find(lab[y][x])
            b = bx.get(r)
            if b is None:
                bx[r] = [x, y, x, y, 1]
                continue
            b[0] = min(b[0], x); b[1] = min(b[1], y)
            b[2] = max(b[2], x); b[3] = max(b[3], y); b[4] += 1
    out = [{"bbox": b[:4], "w": b[2] - b[0], "h": b[3] - b[1], "pixels": b[4]}
           for b in bx.values() if min_px <= b[4] <= max_px]
    out.sort(key=lambda d: -d["pixels"])
    return out


def trace(m, box):
    """Column-wise mask extent -> digitisation trace."""
    x0, y0, pts = box[0], box[1], []
    for cx in range(len(m[0]) if m else 0):
        ys = [y for y in range(len(m)) if m[y][cx]]
        if ys:
            pts.append({"x_px": x0 + cx, "y_px": y0 + sum(ys) / len(ys),
                        "y_top_px": y0 + min(ys), "y_bot_px": y0 + max(ys), "n_px": len(ys)})
    return pts


def calibrate(pixels, values, scale="auto"):
    """Least squares pixel->value map; slope = data units per pixel."""
    if len(pixels) > 2 and (values[-1] - values[0]) * (pixels[-1] - pixels[0]) < 0:
        pixels = list(reversed(pixels))  # values rise as pixels fall (y axes)
    pairs = [(float(p), float(v)) for p, v in zip(pixels, values) if v is not None]
    if len(pairs) < 2: return None
    trials = []
    for sc in (["log"] if scale == "log" else
               ["linear"] if scale == "linear" else ["linear", "log"]):
        if sc == "log" and any(v <= 0 for _p, v in pairs): continue
        ts = [math.log10(v) if sc == "log" else v for _p, v in pairs]
        n, mp, mt = len(pairs), sum(p[0] for p in pairs) / len(pairs), sum(ts) / len(ts)
        sxx = sum((p[0] - mp) ** 2 for p in pairs)
        if sxx == 0: continue
        a = sum((pairs[i][0] - mp) * (ts[i] - mt) for i in range(n)) / sxx
        b = mt - a * mp
        ss = sum((ts[i] - (a * pairs[i][0] + b)) ** 2 for i in range(n))
        tot = sum((t - mt) ** 2 for t in ts)
        r2 = 1 - ss / tot if tot > 0 else (1.0 if ss == 0 else 0.0)
        devs = [abs((10 ** (a * q[0] + b) if sc == "log" else a * q[0] + b) - q[1]) / abs(q[1])
                for q in pairs if q[1]]
        trials.append({"scale": sc, "slope": a, "intercept": b, "r2": round(r2, 6),
                       "max_rel_dev": round(max(devs), 6) if devs else None,
                       "value_per_px": round(abs(a), 8) if sc == "linear" else None,
                       "px_decade": round(abs(1 / a), 2) if sc == "log" else None})
    if not trials: return None
    trials.sort(key=lambda d: (d["max_rel_dev"] if d["max_rel_dev"] is not None else 1, -d["r2"]))
    best = dict(trials[0])
    best["alternatives"] = [{k: t[k] for k in ("scale", "r2", "max_rel_dev")} for t in trials[1:]]
    best["ambiguous"] = bool(len(trials) > 1 and trials[1]["r2"] >= 0.9995
                             and (trials[1]["max_rel_dev"] or 0) <= 0.01)
    if best["ambiguous"]:
        best["ambiguity_note"] = "linear and log fits indistinguishable; use printed labels"
    return best


def apply_calib(c, v):
    y = c["slope"] * v + c["intercept"]
    return 10 ** y if c["scale"] == "log" else y


def sig(x, n=4):
    if x is None or x == 0: return x
    return round(x, -int(math.floor(math.log10(abs(x)))) + (n - 1))


def digitize_img(img, box, color, cal_x, cal_y, scale=1, tol=60, max_rows=3000):
    """Colour-isolated curve trace mapped through fitted calibrations."""
    pts = trace(mask_for(img, color, tol=tol, box=box), box)
    if not pts: return []
    keep, rows = max(1, len(pts) // max_rows), []
    for k, q in enumerate(pts):
        if k % keep: continue
        yt = apply_calib(cal_y, q["y_top_px"]) if cal_y else None
        yb = apply_calib(cal_y, q["y_bot_px"]) if cal_y else None
        rows.append({"x": sig(apply_calib(cal_x, q["x_px"])) if cal_x else None,
                     "y": sig(apply_calib(cal_y, q["y_px"])) if cal_y else None,
                     "y_lo": sig(min(yt, yb)) if yb is not None else None,
                     "y_hi": sig(max(yt, yb)) if yb is not None else None,
                     "x_px": round(q["x_px"], 1), "y_px": round(q["y_px"], 1),
                     "px_thickness": q["n_px"], "approx": True,
                     "err_x_data": sig(0.5 * scale * abs(cal_x["slope"])) if cal_x else None,
                     "err_y_data": sig(0.5 * scale * abs(cal_y["slope"])) if cal_y else None})
    return rows


def analyze_image(p):
    """Structural analysis of one raster figure; never raises."""
    out = {"file": str(p), "sha256": sha256_file(p), "kind": sniff(p), "plot_box_px": None,
           "spines_px": {}, "ticks_px": {}, "spacing": {}, "color_clusters": [],
           "legend_candidates": [], "annotation_candidates": [], "image_px": {},
           "analysis_scale": 1, "traceable": False, "warnings": []}
    try: img, meta = load_image(p)
    except Exception as e:
        out["warnings"].append("decode_failed")
        out["decode_error"] = "%s: %s" % (type(e).__name__, e)
        return out
    s = meta["analysis_scale"]
    out.update({"image_px": {"w": meta["orig_w"], "h": meta["orig_h"]}, "analysis_scale": s,
                "analysis_px": {"w": meta["analysis_w"], "h": meta["analysis_h"]}})
    bg = background(img)
    out["background_rgb"] = list(bg)
    w, h = img["w"], img["h"]
    if w < 60 or h < 60:
        out["warnings"].append("image_too_small")
        return out
    rl, cl = longest_run(img, bg, True), longest_run(img, bg, False)
    out["horizontal_lines_px"] = [round(sum(g) / len(g) * s, 1) for g in rl][:12]
    out["vertical_lines_px"] = [round(sum(g) / len(g) * s, 1) for g in cl][:12]
    if not rl or not cl:
        out["warnings"].append("no_axis_frame_detected: photo, diagram or borderless plot")
        out["color_clusters"] = color_clusters(img, (0, 0, w, h), bg)
        return out
    rw, ybot, xl = img["rows"], max(g[-1] for g in rl), min(g[0] for g in cl)
    yg = [g for g in rl if g[-1] < ybot - 5]
    xg = [g for g in cl if g[0] > xl + 5]
    ytop = min(g[0] for g in yg) if yg else next(
        (y for y in range(h) if dist(px(rw, y, xl), bg) > 60), 0)
    xr = max(g[-1] for g in xg) if xg else max(
        (x for x in range(w) if dist(px(rw, ybot, x), bg) > 60), default=w - 1)
    box = (xl, ytop, xr, ybot)
    out["plot_box_px"] = [round(v * s, 1) for v in box]
    out["spines_px"] = {"left": round(xl * s, 1), "bottom": round(ybot * s, 1),
                        "top": round(ytop * s, 1), "right": round(xr * s, 1)}
    xt, yt = ticks(img, bg, ybot, box, "x"), ticks(img, bg, xl, box, "y")
    out["ticks_px"] = {"x": [round(c * s, 1) for c in xt],
                       "y": [round(c * s, 1) for c in yt],
                       "x_wide": [round(c * s, 1) for c in ticks(img, bg, ybot, box, "x", band=26)]}
    out["spacing"] = {"x": spacing_report(xt), "y": spacing_report(yt)}
    out["color_clusters"] = color_clusters(img, box, bg)
    sw = []
    for c in out["color_clusters"][:8]:
        for comp in components(mask_for(img, c["rgb"], tol=55, box=box), 40, 20000):
            bw, bh = comp["w"], comp["h"]
            if bh <= max(3, 2 * s) and 6 <= bw <= 90 and bw >= 2 * bh:
                b = comp["bbox"]
                sw.append({"rgb": c["rgb"], "bbox": [b[0] + box[0], b[1] + box[1],
                                                    b[2] + box[0], b[3] + box[1]]})
    sw.sort(key=lambda d: (d["bbox"][1], d["bbox"][0]))
    groups = []
    for d in sw:
        for g in groups:
            if abs(g[-1]["bbox"][0] - d["bbox"][0]) <= max(6, 3 * s) and \
                    d["bbox"][1] - g[-1]["bbox"][3] <= max(30, 8 * s):
                g.append(d)
                break
        else: groups.append([d])
    for g in groups:
        if len(g) < 2 or all(d["rgb"] == g[0]["rgb"] for d in g): continue
        xs = [d["bbox"][0] for d in g] + [d["bbox"][2] for d in g]
        ys = [d["bbox"][1] for d in g] + [d["bbox"][3] for d in g]
        out["legend_candidates"].append({
            "bbox_px": [round(min(xs) * s, 1), round(min(ys) * s, 1),
                        round(max(xs) * s, 1), round(max(ys) * s, 1)],
            "entries_top_to_bottom": [d["rgb"] for d in g], "n_entries": len(g),
            "read_basis": "swatch order"})
    out["traceable"] = True
    return out


# ------------------------------------------------- material + table text
def pdf_text(p, cap=300000):
  """Literal strings from PDF content streams (no OCR, no layout geometry)."""
  try: raw = Path(p).read_bytes()
  except OSError: return ""
  out = []
  for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
    b = m.group(1)
    try: b = zlib.decompress(b)
    except Exception: pass
    out += [re.sub(rb"\\([()\\])", rb"\1", t.group(0)[1:-1]).decode("latin-1")
            for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", b)]
  return re.sub(r"\s+", " ", " ".join(out))[:cap]


# ----------------------------------------------------------- table helpers


def pad(g):
  w = max(len(r) for r in g)
  return [list(r) + [""] * (w - len(r)) for r in g]


def csv_table(p):
  raw = Path(p).read_text(encoding="utf-8-sig", errors="replace")
  head = raw[:4000]
  d = "," if head.count(",") >= max(head.count(";"), head.count("\t")) else \
      ";" if head.count(";") >= head.count("\t") else "\t"
  g = [r for r in csv.reader(io.StringIO(raw), delimiter=d) if any(str(c).strip() for c in r)]
  return {"format": "csv", "delimiter": d, "columns": g[0] if g else [], "rows": g[1:],
          "grid": g, "n_rows": max(0, len(g) - 1)}


def json_tables(o, where="$"):
  """Tables literally present in JSON (e.g. material.json) are first-class."""
  out = []
  if isinstance(o, dict):
    tid = next((o[k] for k in o if k.lower() in ("table_id", "label") and isinstance(o[k], str)), None)
    for k, v in o.items():
      if isinstance(v, list) and v and all(isinstance(r, list) for r in v) and \
          all(all(not isinstance(x, (list, dict)) for x in r) for r in v):
        g = pad([[str(x) for x in r] for r in v])
        out.append({"table_id": tid or k, "json_pointer": "%s/%s" % (where, k), "columns": g[0],
                    "rows": g[1:], "grid": g, "n_rows": len(g) - 1, "format": "json-inline"})
      else: out += json_tables(v, "%s/%s" % (where, k))
  elif isinstance(o, list):
    for i, v in enumerate(o): out += json_tables(v, "%s/%d" % (where, i))
  return out


def files_of(root, cap=400):
  return [p for p in sorted(root.rglob("*")) if p.is_file() and not any(
      x.startswith(".") for x in p.relative_to(root).parts)][:cap]
