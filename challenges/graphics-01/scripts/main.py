#!/usr/bin/env python3
"""scifig-editable: source-bound editable schematic -> layered SVG + real PNG/PDF + result.json.
figure_model.json is the single source for SVG, exports and content_map. Exits 0 always and
writes a partial result.json before analysis. Usage: python3 -B scripts/main.py --input /input --output /app/output"""
import argparse, csv, hashlib, io, json, re, shutil, struct, subprocess, sys, time, unicodedata, zlib
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as R
V, RS = "1.0.0", "relationship_schematic"
REL = [("activation", r"activates?|activated|promotes?|induces?|upregulates?|up-regulates?|stimulates?|enhances?|促进|激活|上调|诱导|增强", "activation", "#0072B2"),
       ("inhibition", r"inhibits?|inhibited|suppress(?:es|ed)?|repress(?:es|ed)?|blocks?|downregulates?|down-regulates?|attenuates?|抑制|下调|阻遏|阻断", "inhibition", "#D55E00"),
       ("binding", r"binds?|binding|interacts? with|forms? a complex|recruits?|结合|互作|相互作用|复合物|招募", "binding", "#009E73"),
       ("phosphorylation", r"phosphorylates?|phosphorylated|phosphorylation|磷酸化", "activation", "#CC79A7"),
       ("expression", r"expresses?|encoded? by|encodes?|表达|编码", "activation", "#56B4E9"),
       ("containment", r"contains?|includes?|comprises?|consists? of|is part of|subunit of|包含|包括|属于", "activation", "#8d979f"),
       ("conversion", r"converts?|converted to|produces?|generates?|yields?|转化为|生成", "activation", "#E69F00"),
       ("causal", r"leads? to|results? in|causes?|caused by|therefore|thus|hence|导致|引起|因此", "activation", "#333333"),
       ("causal2", r"subsequently|随后|之后|接着", "activation", "#999999")]
STY = {"font_pt": {"title": 11.0, "label": 8.5, "legend": 7.0}, "line_width": 1.2, "entity_fill": "#F2F7FB",
       "entity_stroke": "#0B5F8A", "palette": ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#117733", "#333333"],
       "rel_marker": {t: m for t, _p, m, _c in REL}, "rel_color": {t: c for t, _p, _m, c in REL}}
FLIP, NUM = re.compile(r"^\s*(is|are|was|were|been|被|受到|由)\s*", re.I), re.compile(r"[\(\[]([^)\]]+)[\)\]]")
TOK = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,15}|[\u4e00-\u9fa5]{2,8}")
SRC_EXT = (".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".tex", ".xml")
SKIP = ("result.json", "figure_model.json", "edit_record.json")

def nrm(s):
    return re.sub(r"[\s\u00a0]+", " ", unicodedata.normalize("NFKC", str(s or "")).lower()).strip()

def pk(d, *ns, default=None):
    """Semantic key lookup: exact, *_name, name_*; case-insensitive; empty values skipped."""
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for n in ns:
        for k, v in low.items():
            if (k == n or k.endswith("_" + n) or k.startswith(n)) and v not in (None, "", [], {}):
                return v
    return default

def ckeys(c):
    if isinstance(c, dict):
        return list(c.keys())
    o = []
    for it in c if isinstance(c, list) else []:
        o += [it] if isinstance(it, str) else [str(it[k]) for k in ("name", "field", "key", "id") if isinstance(it, dict) and it.get(k)]
    return [k for k in dict.fromkeys(o) if k]

def jl(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

def rpdf(p):
    """PDF text via pdftotext (poppler); the caller records when it is unavailable."""
    ex = shutil.which("pdftotext")
    if ex:
        try:
            r = subprocess.run([ex, "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace"), "pdftotext"
        except Exception:
            pass
    return "", "no_text_layer"

def corpus(root):
    docs, tabs, notes = [], [], []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or p.stat().st_size > 8_000_000:
            continue
        rel = str(p.relative_to(root))
        if rel.split("/")[0] in ("output", "work") or p.name in SKIP:
            continue
        e, txt = p.suffix.lower(), ""
        try:
            if e in SRC_EXT:
                txt = p.read_text(encoding="utf-8", errors="replace")
            elif e == ".pdf":
                txt, how = rpdf(p)
                if how != "pdftotext":
                    notes.append("%s:%s" % (how, rel))
            else:
                if e in (".xlsx", ".xlsm", ".docx"):
                    notes.append("unsupported_source:" + rel)
                continue
            if e in (".csv", ".tsv"):
                rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(txt)) if any(c.strip() for c in r)]
                if len(rows) > 1:
                    tabs.append({"id": rel, "header": rows[0], "rows": rows[1:]})
            if txt.strip():
                docs.append({"id": rel, "kind": e[1:], "text": txt, "lines": txt.splitlines()})
        except Exception as exc:
            notes.append("read_failed:%s:%s" % (rel, type(exc).__name__))
    return docs, tabs, notes

def loc(docs, label):
    n = nrm(label)
    if len(n) < 2:
        return None, False
    for d in docs:
        for i, ln in enumerate(d["lines"], 1):
            if n in nrm(ln):
                q = ln.strip()
                q = q if len(q) <= 300 else ln[max(0, nrm(ln).find(n) - 60):][:300]
                w = "%s#L%d" % (d["id"], i)
                if d["kind"] == "pdf":
                    w = "%s#p%d+L%d" % (d["id"], d["text"].count("\f", 0, sum(len(x) + 1 for x in d["lines"][:i - 1])) + 1, i)
                return {"kind": d["kind"], "source_id": d["id"], "locator": w, "quote": q}, True
    return None, False

def tok(ch, head):
    t = TOK.findall(ch)
    if not t:
        return ""
    v = t[-1] if head else t[0]
    return (t[-2] + " " + v if head and len(t) > 1 and v[:1].islower() and t[-2][:1].isupper() else v).strip(" -")

def ext(docs):
    ents, rels, seen = [], [], {}
    for d in docs:
        for ln in d["lines"]:
            if not 6 < len(ln) < 500:
                continue
            for typ, pat, _m, _c in REL:
                for m in re.finditer(pat, ln, re.I):
                    h, t = tok(ln[:m.start()], True), tok(ln[m.end():], False)
                    if len(h) < 2 or len(t) < 2 or nrm(h) == nrm(t):
                        continue
                    if FLIP.match(ln[m.end():m.end() + 14]):
                        h, t = t, h
                    for lab in (h, t):
                        if nrm(lab) not in seen and len(ents) < 16:
                            seen[nrm(lab)] = "e%d" % (len(ents) + 1)
                            ents.append({"id": seen[nrm(lab)], "label": lab})
                    if len(rels) < 22 and (seen[nrm(h)], seen[nrm(t)], typ) not in {(r["from"], r["to"], r["type"]) for r in rels}:
                        rels.append({"id": "r%d" % (len(rels) + 1), "from": seen[nrm(h)], "to": seen[nrm(t)], "type": typ})
    return ents, rels

def build(wo, docs, tabs, ex):
    raw = pk(wo, "required_entities", "entities", "nodes", default=[]) or []
    if isinstance(raw, dict):
        raw = [dict(v, id=k) if isinstance(v, dict) else {"id": k, "label": v} for k, v in raw.items()]
    ents = []
    for i, e in enumerate(raw if isinstance(raw, list) else []):
        lab = e if isinstance(e, str) else pk(e, "label", "name", "text", "term", "id")
        if lab:
            ents.append({"id": str(pk(e, "id", "key", default="e%d" % (i + 1))) if isinstance(e, dict) else "e%d" % (i + 1),
                         "label": str(lab), "type": pk(e, "entity_type", "type", "kind") if isinstance(e, dict) else None})
    rels, mode = [], "workorder" if ents else "extracted"
    if ents:
        by = {nrm(e["label"]): e["id"] for e in ents}
        by.update({nrm(e["id"]): e["id"] for e in ents})
        for i, r in enumerate(pk(wo, "required_relations", "relations", "edges", "links", default=[]) or []):
            if isinstance(r, str):
                m = re.split(r"\s*(?:->|→|=>|-\\|⊣|\|)\s*", r)
                m = m if len(m) > 1 else re.split(r"\s+(?:activates?|inhibits?|promotes?)\s+", r, flags=re.I)
                if len(m) >= 2:
                    rels.append({"id": "r%d" % (i + 1), "from": by.get(nrm(m[0]), m[0]), "to": by.get(nrm(m[-1]), m[-1]),
                                 "type": "inhibition" if re.search(r"inhibit|抑制|-\\|⊣", r, re.I) else "activation"})
            elif isinstance(r, dict):
                a, b = pk(r, "from", "source", "src", "subject"), pk(r, "to", "target", "object", "tail")
                if a and b:
                    rels.append({"id": "r%d" % (i + 1), "from": by.get(nrm(a), str(a)), "to": by.get(nrm(b), str(b)),
                                 "type": str(pk(r, "relation_type", "type", "predicate", default="activation")).lower(),
                                 "label": pk(r, "label", "text"), "direction": pk(r, "direction")})
    else:
        ents, rels = ext(docs)
    wot = json.dumps(wo, ensure_ascii=False) if wo else ""
    for e in ents:
        s, ok = loc(docs, e["label"])
        if not ok and wot and nrm(e["label"]) in nrm(wot):
            s, ok = {"kind": "workorder", "source_id": "workorder", "locator": "workorder#required_entities", "quote": e["label"]}, True
        e["source"], e["verified"] = s, bool(ok)
        if not ok:
            ex.append({"type": "label_not_in_source", "object": e["label"], "locator": None,
                       "reason": "not found verbatim in any provided material",
                       "action": "kept but flagged unverified; confirm before publication"})
    alive = {e["id"] for e in ents if e["verified"]}
    for r in rels:
        r["verified"] = r["from"] in alive and r["to"] in alive
        r["type"] = r["type"] if r["type"] in STY["rel_marker"] else "activation"
        r["direction"] = r.get("direction") or "forward"
        r["source"] = next((e["source"] for e in ents if e["id"] == r["from"]), None) if r["verified"] else None
        if not r["verified"]:
            ex.append({"type": "relation_unverified", "object": "%s-%s" % (r["from"], r["to"]),
                       "reason": "an endpoint is unverified or absent", "action": "excluded from the figure"})
    rels = [r for r in rels if r["verified"]]
    chart = None
    for t in ([] if rels else tabs):
        hdr, rows = t.get("header") or [], t.get("rows") or []
        if len(hdr) < 2 or len(rows) < 2:
            continue
        ser = []
        for ci in range(1, len(hdr)):
            try:
                v = [float(str(r[ci] if ci < len(r) else "").replace(",", "").strip()) for r in rows]
            except Exception:
                continue
            u = NUM.search(str(hdr[ci]))
            ser.append({"name": NUM.sub("", str(hdr[ci])).strip() or "value", "unit": u.group(1).strip() if u else "",
                        "values": v, "quote": [str(r[ci] if ci < len(r) else "") for r in rows]})
        if ser:
            chart = {"title": str(pk(wo, "figure_title", "title", default="") or t["id"]), "table": t,
                     "categories": [str(r[0]) for r in rows], "quotes": [s["quote"] for s in ser],
                     "series": [{"name": s["name"], "unit": s["unit"], "values": s["values"]} for s in ser]}
            break
    nser = len((chart or {}).get("series") or [])
    leg = [{"id": "l%d" % (i + 1), "kind": "relation", "label": t, "marker": STY["rel_marker"][t], "color": STY["rel_color"][t]}
           for i, t in enumerate(dict.fromkeys(r["type"] for r in rels))]
    for i, s in enumerate((chart or {}).get("series") or []):
        leg.append({"id": "l%d" % (len(leg) + 1), "kind": "series", "label": s["name"] + ((" (%s)" % s["unit"]) if s["unit"] else ""),
                    "color": STY["palette"][(i + (nser > 1)) % 8]})
    return {"schema": "figure-model/1.0", "figure_id": str(pk(wo, "figure_id", "id", default="figure") or "figure"),
            "kind": "data_chart" if chart and not rels else (RS + "+chart" if chart else RS),
            "title": str(pk(wo, "figure_title", "title", default="") or ""), "entities": ents, "relations": rels,
            "legend": leg, "chart": chart, "layers": list(R.LAYERS), "extraction_mode": mode,
            "canvas": {"width": 1200, "height": 760, "unit": "px", "background": "#FFFFFF"},
            "style": json.loads(json.dumps(STY))}, mode

def pprobe(path):
    """Real IHDR + genuine non-white ratio (PNG filters 0-4 undone)."""
    try:
        b = Path(path).read_bytes()
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            return {"ok": False, "reason": "not_png_signature"}
        pos, ih, idat = 8, None, b""
        while pos < len(b) - 8:
            n = struct.unpack(">I", b[pos:pos + 4])[0]
            t = b[pos + 4:pos + 8]
            if t == b"IHDR":
                ih = struct.unpack(">IIBBBBB", b[pos + 8:pos + 21])
            elif t == b"IDAT":
                idat += b[pos + 8:pos + 8 + n]
            pos += 12 + n
        if not ih:
            return {"ok": False, "reason": "no_ihdr"}
        w, h, dep, ct = ih[0], ih[1], ih[2], ih[3]
        r = {"ok": True, "width": w, "height": h, "bit_depth": dep, "color_type": ct, "bytes": len(b)}
        if dep != 8 or ct not in (2, 6) or w * h > 12_000_000:
            return r
        bpp, raw = (3 if ct == 2 else 4), zlib.decompress(idat)
        stride, prev, nw, tot = w * bpp, bytearray(w * bpp), 0, 0
        sy, sx = max(1, h // 60), max(1, w // 60)
        for y in range(h):
            f, ln = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            if f:
                for i in range(stride):
                    a = ln[i - bpp] if i >= bpp else 0
                    if f == 1:
                        ln[i] = (ln[i] + a) & 0xFF
                    elif f == 2:
                        ln[i] = (ln[i] + prev[i]) & 0xFF
                    elif f == 3:
                        ln[i] = (ln[i] + ((a + prev[i]) >> 1)) & 0xFF
                    else:
                        c, q = (prev[i - bpp] if i >= bpp else 0), None
                        q = a + prev[i] - c
                        pa, pb, pc = abs(q - a), abs(q - prev[i]), abs(q - c)
                        ln[i] = (ln[i] + (a if pa <= pb and pa <= pc else (prev[i] if pb <= pc else c))) & 0xFF
            if y % sy == 0:
                for x in range(0, w, sx):
                    o = x * bpp
                    tot += 1
                    nw += 0 if (ln[o] > 245 and ln[o + 1] > 245 and ln[o + 2] > 245) else 1
            prev = ln
        r["nonwhite_ratio"] = round(nw / float(tot or 1), 4)
        r["blank"] = r["nonwhite_ratio"] < 0.004
        return r
    except Exception as e:
        return {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}

def fprobe(path):
    try:
        b = Path(path).read_bytes()
        return {"ok": b[:5] == b"%PDF-" and b"%%EOF" in b[-2048:], "bytes": len(b),
                "pages": b.count(b"/Type/Page") - b.count(b"/Type/Pages") + b.count(b"/Type /Page") - b.count(b"/Type /Pages ")}
    except Exception as e:
        return {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}

def cmap(m, svgt):
    """content_map (element -> source + verbatim quote) plus the machine checks, from one model."""
    ids = {e.get("id") for e in ET.fromstring(svgt).iter() if e.get("id")}
    ents = [{"id": e["id"], "label": e["label"], "entity_type": e.get("type") or "entity", "verified": bool(e.get("verified")),
             "svg_ids": ["ent-" + e["id"]] + (["lbl-" + e["id"]] if len(e["lines"]) == 1 else ["lbl-%s-%d" % (e["id"], i + 1) for i in range(len(e["lines"]))]),
             "source": e.get("source")} for e in m["entities"]]
    rels = [{"id": r["id"], "svg_id": "edge-" + r["id"], "from": r["from"], "to": r["to"], "relation_type": r["type"], "marker": r.get("marker"),
             "direction": r.get("direction"), "route": r.get("route"), "verified": r.get("verified"), "source": r.get("source")} for r in m["relations"]]
    leg = [{"id": l["id"], "kind": l["kind"], "label": l["label"], "color": l["color"], "svg_id": "lg-" + l["id"],
            "encoding": l.get("marker") or "colour swatch"} for l in m["legend"]]
    dp, ch = [], m.get("chart")
    if ch:
        for ci, cat in enumerate(ch["categories"]):
            for si, s in enumerate(ch["series"]):
                dp.append({"id": "bar-%d-%d" % (ci + 1, si + 1), "category": cat, "series": s["name"], "unit": s["unit"],
                           "value": s["values"][ci], "source": {"kind": "table", "source_id": ch["table"]["id"],
                                                                "locator": "%s#row=%d,col=%s" % (ch["table"]["id"], ci + 2, s["name"]),
                                                                "quote": ch["quotes"][si][ci]}})
    exp = [s for e in ents for s in e["svg_ids"]] + [r["svg_id"] for r in rels] + [l["svg_id"] for l in leg] + [d["id"] for d in dp]
    mp = sum(1 for e in ents if e["verified"] and e["source"])
    cm = {"entities": ents, "relations": rels, "legend": leg, "data_points": dp,
          "coverage": {"required_entities": len(ents), "mapped_entities": mp, "required_relations": len(rels), "legend_items": len(leg),
                       "entity_coverage": round(mp / float(len(ents) or 1), 3), "complete": mp == len(ents)},
          "svg_ids_expected": exp, "svg_sha256": hashlib.sha256(svgt.encode()).hexdigest(),
          "svg_sha256_recheck": hashlib.sha256(R.svg(json.loads(json.dumps(m))).encode()).hexdigest()}
    st, cv = m["style"], m["canvas"]
    bx = [e["box"] for e in m["entities"]]
    ov = sum(1 for i in range(len(bx)) for j in range(i + 1, len(bx))
             if bx[i]["x"] < bx[j]["x"] + bx[j]["w"] - 1 and bx[j]["x"] < bx[i]["x"] + bx[i]["w"] - 1
             and bx[i]["y"] < bx[j]["y"] + bx[j]["h"] - 1 and bx[j]["y"] < bx[i]["y"] + bx[i]["h"] - 1)
    W, H, mk = cv["width"], cv["height"], len(set(re.findall(r'<marker id="([^"]+)"', svgt)))
    out = sum(1 for b in bx if b["x"] < 0 or b["y"] < 0 or b["x"] + b["w"] > W + .5 or b["y"] + b["h"] > H + .5)
    tight = sum(1 for e in m["entities"] if max([R.est_w(x, st["font_pt"]["label"]) for x in e["lines"]] or [0]) > e["box"]["w"] - 8)
    used, nser, miss = {r["type"] for r in m["relations"]}, len((m.get("chart") or {}).get("series") or []), [s for s in exp if s not in ids]
    ck = {"canvas": {"ok": 0 < W <= 4000 and 0 < H <= 4000, "width_px": W, "height_px": H},
          "svg_wellformed": {"ok": svgt.count("<text") > 0 and len([i for i in ids if i.startswith("layer-")]) >= 4,
                             "layers": sorted(i for i in ids if i.startswith("layer-")), "text_elements": svgt.count("<text"), "marker_defs": mk},
          "id_map": {"ok": not miss, "content_map_ids": len(exp), "missing": miss[:8]},
          "labels_verbatim": {"ok": all(e.get("verified") for e in m["entities"]), "unverified": [e["label"] for e in m["entities"] if not e.get("verified")]},
          "style": {"ok": min(st["font_pt"].values()) >= 6 and .4 <= st["line_width"] <= 3, "family": R.FS,
                    "sizes_pt": st["font_pt"], "line_width_pt": st["line_width"]},
          "fonts": {"ok": min(st["font_pt"].values()) >= 6, "family": R.FS, "sizes_pt": st["font_pt"]},
          "line_widths": {"ok": .4 <= st["line_width"] <= 3, "pt": st["line_width"]},
          "markers": {"ok": mk >= 2, "distinct_markers": mk, "relation_types": sorted(used)},
          "legend_consistency": {"ok": len([l for l in leg if l["kind"] == "relation"]) == len(used) and len(leg) == len(used) + nser,
                                 "legend_items": len(leg), "encoding_categories": len(used) + nser},
          "overlap": {"ok": ov == 0, "pairs": ov},
          "overflow": {"ok": out == 0 and tight == 0, "outside_canvas": out, "text_overflow": tight},
          "determinism": {"ok": cm["svg_sha256"] == cm["svg_sha256_recheck"]}}
    ck["pass"] = all(v["ok"] for v in ck.values() if isinstance(v, dict) and isinstance(v.get("ok"), bool))
    ck["failures"] = [k for k, v in ck.items() if isinstance(v, dict) and v.get("ok") is False]
    return cm, ck

def edits(m, base, wo, out, ex, res):
    """Source-preserving edit: keep ids/layers/coordinates, replace only the workorder-named labels."""
    raw = base.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except Exception as e:
        ex.append({"type": "baseline_unparsable", "object": base.name, "reason": str(e), "action": "generated a new SVG instead"})
        return m, "generated"
    done = []
    for op in (pk(wo, "edit_operations", "edits", "changes", default=[]) or []):
        if not isinstance(op, dict):
            continue
        eid = str(pk(op, "target", "element_id", "id", "selector", default="") or "")
        new, old = pk(op, "new_label", "new_text", "text", "value"), pk(op, "old_label", "old_text", "from")
        for el in root.iter():
            if not str(el.tag).endswith("text"):
                continue
            cur = "".join(el.itertext())
            if (eid and el.get("id") == eid) or (old and nrm(cur) == nrm(old)):
                if new:
                    el.text = str(new)
                    done.append({"element_id": el.get("id"), "original": cur, "revised": str(new), "locator": "%s#%s" % (base.name, el.get("id"))})
                break
    if not done:
        ex.append({"type": "no_edit_applied", "object": base.name, "reason": "no operation matched an id or label",
                   "action": "baseline preserved unchanged"})
    t = ET.tostring(root, encoding="unicode")
    t = t if t.lstrip().startswith("<?xml") else '<?xml version="1.0" encoding="UTF-8"?>\n' + t
    (out / "figure.svg").write_text(t, encoding="utf-8")
    (out / "edit_record.json").write_text(json.dumps({"baseline": {"path": str(base), "sha256": hashlib.sha256(raw.encode()).hexdigest()},
                                                     "revised": {"path": str(out / "figure.svg"), "sha256": hashlib.sha256(t.encode()).hexdigest()},
                                                     "changes": done, "preserved": ["element ids", "layer groups", "coordinates", "styles"]},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    res["changes"] = done
    return m, "edited"

def wr(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")

def main(argv=None):
    t0 = time.time()
    ap = argparse.ArgumentParser(prog="scifig-editable", description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Outputs: figure.svg (editable, layered, live text), figure.png/figure.pdf (real exports), "
                                        "figure_model.json, edit_record.json (edit cases), result.json. Exit code is always 0.")
    ap.add_argument("--input", help="case dir; default /input, /app/input, ./input")
    ap.add_argument("--output", help="artifact dir; default /app/output or ./output")
    ap.add_argument("--case", help="explicit case.json path")
    a = ap.parse_args(argv)
    inp = Path(a.case).parent if a.case else Path(next((p for p in [a.input, "/input", "/app/input", "input"] if p and Path(p).is_dir()), "."))
    out = Path(a.output or ("/app/output" if Path("/app").is_dir() else "output"))
    out.mkdir(parents=True, exist_ok=True)
    cp = Path(a.case) if a.case else next((p for p in [inp / "case.json", inp / "input" / "case.json"] if p.exists()), None)
    cp = cp or next(iter(sorted(inp.glob("**/case*.json"))), None)
    raw_case = jl(cp) if cp else {}
    broken_case = bool(cp) and not isinstance(raw_case, dict)
    case = raw_case if isinstance(raw_case, dict) else {}
    keys, ex = ckeys(pk(case, "output_contract", default=[])), []
    res = {"case_id": pk(case, "case_id", "id"), "status": "partial", "editable_source": None, "export_artifact": None, "content_map": None,
           "compliance_checks": None, "exceptions": [], "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
           "degradations": [], "changes": [], "output_contract_echo": pk(case, "output_contract", default=[]),
           "runtime": {"script": "main.py", "version": V, "python": sys.version.split()[0], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}}
    for k in keys:
        res.setdefault(k, None)
    wr(out / "result.json", res)
    try:
        docs, tabs, notes = corpus(inp)
        res["errors"] = notes + (["case.json could not be parsed as a JSON object; continuing with empty case"] if broken_case else [])
        wo = pk(case, "organizer_workorder", "workorder", "figure_workorder") or {}
        if not isinstance(wo, dict) or not wo:
            wo = pk(jl(next(iter(sorted(inp.glob("**/*workorder*.json"))), None) or ""), "workorder", "figure_workorder", default={}) or {}
        if not wo:
            wo = pk(jl(next((p for p in sorted(inp.glob("**/material.json"))), None) or ""), "workorder", "figure", default={}) or {}
        res["sources"] = ([{"id": d["id"], "kind": d["kind"], "chars": len(d["text"])} for d in docs] +
                          [{"id": "table:" + t["id"], "kind": "table", "rows": len(t["rows"]), "cols": len(t["header"])} for t in tabs])
        if not docs and not tabs:
            raise LookupError("no readable material under %s" % inp)
        model, mode = build(wo, docs, tabs, ex)
        if not model["entities"] and not model.get("chart"):
            ex.append({"type": "no_drawable_content", "object": "figure", "locator": None,
                       "reason": "no entity/relation/table could be read from the materials",
                       "action": "empty canvas written; supply a workorder or readable source text"})
        base = pk(wo, "source_artifact", "baseline", "base_figure")
        base = Path(str(base)) if base and Path(str(base)).is_file() else next(iter(sorted(inp.glob("**/*.svg"))), None)
        if base and Path(base).suffix.lower() == ".svg":
            model, mode = edits(model, Path(base), wo, out, ex, res)
        R.layout(model)
        svgt = R.svg(model)
        (out / "figure.svg").write_text(svgt, encoding="utf-8")
        exp = {"png": None, "pdf": None, "engines": {}, "degradations": []}
        if mode == "edited":
            for f in ("png", "pdf"):
                eng = R._convert(out / "figure.svg", out / ("figure." + f), png_w=int(model["canvas"]["width"] * 2))
                if eng:
                    exp[f], exp["engines"][f] = out / ("figure." + f), eng
                else:
                    exp["degradations"].append({"artifact": f, "engine": None, "status": "missing",
                                                "reason": "an edited baseline needs an SVG converter; matplotlib would redraw other geometry"})
        else:
            exp = R.export_all(model, out, dpi=300)
        res["degradations"] += exp["degradations"]
        cm, ck = cmap(model, svgt)
        model["export"] = {"formats": ["svg"] + [f for f in ("png", "pdf") if exp.get(f)], "dpi": 300, "color_space": "RGB", "engines": exp["engines"]}
        wr(out / "figure_model.json", model)
        if mode == "edited":
            ck["edited_source"] = {"ok": bool(res.get("changes")), "changes": len(res.get("changes") or [])}
            ck["pass"] = bool(res.get("changes"))
            ck["failures"] = [k for k, v in ck.items() if isinstance(v, dict) and v.get("ok") is False]
        ea = {}
        for f in ("png", "pdf"):
            p = exp.get(f)
            if p:
                pr = pprobe(p) if f == "png" else fprobe(p)
                ea[f] = {"path": str(p), "engine": exp["engines"].get(f), "width": pr.get("width"), "height": pr.get("height"),
                         "dpi": 300 if f == "png" else None, "pages": pr.get("pages"), "bytes": p.stat().st_size, "color_space": "RGB", "probe": pr}
            else:
                ea[f] = {"path": None, "engine": None, "status": "missing"}
        for f, k in (("png", "pixel_probe"), ("pdf", "pdf_probe")):
            ck[k] = ea[f].get("probe") or {"ok": None, "reason": "no_" + f}
        if mode != "edited":
            ck["pass"] = bool(ck["pass"]) and all(ck[k].get("ok") is not False for k in ("pixel_probe", "pdf_probe"))
            ck["failures"] = [k for k, v in ck.items() if isinstance(v, dict) and v.get("ok") is False]
        res.update({"export_artifact": ea, "content_map": cm, "compliance_checks": ck, "exceptions": ex,
                    "editable_source": {"path": str(out / "figure.svg"), "format": "svg", "editable": True, "text_live": True,
                                        "layers": model["layers"], "element_count": len(re.findall(r' id="', svgt)), "text_count": svgt.count("<text"),
                                        "marker_types": sorted(set(re.findall(r'<marker id="mk-([^"]+)"', svgt))),
                                        "sha256": hashlib.sha256(svgt.encode()).hexdigest(), "mode": mode,
                                        "coordinate_system": "%dx%d px" % (model["canvas"]["width"], model["canvas"]["height"])}})
        res["pending_human"] = [{"item": e["label"], "why": "label not verifiable in the provided sources",
                                 "action": "confirm the name or supply the missing source"} for e in model["entities"] if not e.get("verified")]
        res["uncertainty"] = [{"topic": "layout", "detail": "deterministic heuristic placement, not a curated journal layout"}]
        if mode == "extracted":
            res["uncertainty"].append({"topic": "extraction", "detail": "relations parsed by sentence patterns; modality, timing and conditions are not modelled"})
        if mode == "edited":
            res["uncertainty"].append({"topic": "edit", "detail": "only workorder-named elements were touched"})
        ok = bool(exp.get("png") or exp.get("pdf")) and ck.get("pass") is not False
        ok = ok and (mode == "edited" or all(e.get("verified") for e in model["entities"]))
        res["status"] = "ok" if ok else "partial"
        if not ok:
            res["uncertainty"].append({"topic": "status", "detail": "partial: see compliance_checks.failures / degradations"})
    except Exception as e:
        res["status"] = "input_error"
        res["errors"] = (res.get("errors") or []) + ["%s: %s" % (type(e).__name__, e)]
        res["exceptions"] = res.get("exceptions") or [{"type": "no_result", "object": "figure",
                                                       "reason": "case/workorder/material could not be read", "action": "nothing produced; see errors"}]
    finally:
        res["runtime"].update({"elapsed_s": round(time.time() - t0, 2), "contract_fields": len(keys), "input_dir": str(inp), "output_dir": str(out)})
        for k in keys:
            res.setdefault(k, None)
        wr(out / "result.json", res)
    return 0

if __name__ == "__main__":
    sys.exit(main())
