#!/usr/bin/env python3
"""slides-04 toolkit: text extraction, outline/slide planning, OOXML emitters, deck checks.

CLI: python3 verify.py --out /app/output   (uses run_context.json from the builder)
stdlib only; pdftotext is probed and skipped when absent.
"""
import hashlib, json, math, re, shutil, subprocess, sys, zipfile, zlib
from pathlib import Path

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NSD = 'xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (NS_A, NS_R, NS_P)
LADDER = (24, 20, 18, 16, 14, 12)
KEYH = {"abstract", "introduction", "background", "relatedwork", "methods", "materialsandmethods",
        "methodology", "approach", "results", "result", "discussion", "conclusion", "conclusions",
        "limitations", "futurework", "acknowledgements", "references", "experiments", "evaluation",
        "summary", "motivation"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def clip(s, n=200):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "\u2026"


def nk(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def xesc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pdf_text(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            t = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True,
                               timeout=150).stdout.decode("utf-8", "replace")
            if len(t.strip()) > 200:
                return t.replace("\f", "\n<<P>>\n"), "pdftotext"
        except Exception:
            pass
    return "", "no-pdf-text-tool"


def read_any(p):
    p = Path(p)
    e = p.suffix.lower()
    if e == ".pdf":
        return pdf_text(p)
    if e == ".docx":
        try:
            with zipfile.ZipFile(str(p)) as z:
                b = z.read("word/document.xml").decode("utf-8", "replace")
            return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", b)), "docx"
        except Exception:
            return "", "unreadable"
    for enc in ("utf-8", "latin-1"):
        try:
            return p.read_text(enc, "replace"), "text-" + enc
        except Exception:
            pass
    return "", "unreadable"


def is_head(s):
    s = s.strip()
    if not s or len(s) > 96 or s.endswith((".", ";", ",", "\u3002", "\uff1b", "\uff0c", ":")):
        return False
    if s.startswith("#"):
        return True
    if re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[IVXLC]+\.\s+)", s) and len(s.split()) <= 12:
        return True
    return nk(s) in KEYH or (s.isupper() and 1 <= len(s.split()) <= 8)


def sents(t):
    """sentence split that keeps decimals and units intact: '6.8 C' / '0.3 to 25 um' stay whole.

    v1 used \\s* (zero-width allowed), so every '.' split the text and evidence quotes began or
    ended mid-number. Requires whitespace after the terminator, and drops the ';' rule.
    """
    out = []
    for p in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", " ".join(str(t).split())):
        p = p.strip()
        if len(p) >= 18 and not re.fullmatch(r"[\d.\s%]+", p):
            out.append(p)
    return out


def outline(text):
    """<<P>>-marked text -> [{'title','inferred','units':[{'page','para','sents'}]}]"""
    secs, cur = [], None
    for pi, ptxt in enumerate(text.split("<<P>>"), 1):
        blocks = [b.strip() for b in re.split(r"\n\s*\n", ptxt) if b.strip()] or \
                 [l.strip() for l in ptxt.splitlines() if l.strip()]
        for b in blocks:
            lines = [l.strip() for l in b.splitlines() if l.strip()]
            if not lines:
                continue
            head, body = None, lines
            if is_head(lines[0]):
                head = clip(re.sub(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[IVXLC]+\.\s+)", "",
                                   lines[0].lstrip("#").strip()), 70)
                body = lines[1:]
            if head:
                cur = {"title": head, "inferred": False, "units": []}
                secs.append(cur)
            elif cur is None:
                ss = sents(" ".join(body))
                cur = {"title": clip(ss[0] if ss else "Overview", 60), "inferred": True, "units": []}
                secs.append(cur)
            ss = sents(" ".join(body))
            if ss:
                cur["units"].append({"page": pi, "para": len(cur["units"]) + 1, "sents": ss})
    return [s for s in secs if s["units"]]


def score(t):
    v = 2 if re.search(r"\d", t) else 0
    v += 2 if re.search(r"%|\u00b1|\u00d7|p\s*[<=]|CI|n\s*=|mmol|mg\b|nm\b", t) else 0
    v += 1 if re.search(r"\b(we|our|this study|significant|increas|decreas|report)\w*\b", t, re.I) else 0
    v += 2 if re.search(r"fig(ure)?\.?\s*\d|table\s*\d", t, re.I) else 0
    return v - (1 if len(t) > 260 else 0)


def pick_bullets(units, cap=5, ml=210, exclude=None):
    cand = sorted(((score(t), s, u, t) for s, u in units for t in u["sents"]), key=lambda x: -x[0])
    out, seen = [], set(exclude or ())
    for _, s, u, t in cand:
        if nk(t)[:60] in seen:
            continue
        seen.add(nk(t)[:60])
        out.append({"text": clip(t, ml), "quote": t, "sec": s["title"], "page": u["page"],
                    "locator": "\u00a7%s \u00b6%d / p.%d" % (s["title"], u["para"], u["page"])})
        if len(out) >= cap:
            break
    return out


def fit(items, rect, min_pt, nominal):
    """font size that fits the placeholder box; text shortened only as last resort"""
    if not rect:
        return nominal, items, False
    w = (rect[2] - rect[0]) / 12700.0 * 0.90
    h = (rect[3] - rect[1]) / 12700.0 * 0.86
    cand = sorted([s for s in LADDER if min_pt <= s <= max(nominal, min_pt)] or [max(min_pt, 14)], reverse=True)
    for sz in cand:
        cpl, lines = max(8, int(w / (sz * 0.92))), max(2, int(h / (sz * 1.32)))
        if sum(max(1, math.ceil(len(t) / cpl)) for t in items) <= lines:
            return sz, items, False
    sz = cand[-1]
    cpl, lines = max(8, int(w / (sz * 0.92))), max(2, int(h / (sz * 1.32)))
    tot = sum(len(t) for t in items) or 1
    cut = [clip(t, max(24, int(cpl * lines * len(t) / tot))) for t in items]
    return sz, cut, sum(max(1, math.ceil(len(t) / cpl)) for t in cut) > lines


# ---- OOXML emitters (shapes keep <p:ph>, so geometry/fonts inherit) ----
def run_xml(t, sz=None, b=False):
    a = ' lang="%s" dirty="0"' % ("zh-CN" if CJK.search(str(t)) else "en-US")
    a += (' sz="%d"' % int(sz * 100)) if sz else ""
    a += ' b="1"' if b else ""
    return '<a:r><a:rPr%s/><a:t>%s</a:t></a:r>' % (a, xesc(t))


def body_xml(items, sz=None, bullet=True):
    return "".join('<a:p><a:pPr lvl="0">%s</a:pPr>%s</a:p>'
                   % ("" if bullet else "<a:buNone/>", run_xml(it, sz)) for it in items) or "<a:p/>"


def pnum_p(n):
    h = hashlib.sha256(("pnum%d" % n).encode()).hexdigest()[:32].upper()
    return ('<a:p><a:pPr lvl="0"><a:buNone/></a:pPr><a:fld id="{%s-%s-%s-%s-%s}" type="slidenum">'
            '<a:rPr lang="en-US"/><a:t>%d</a:t></a:fld></a:p>'
            % (h[:8], h[8:12], h[12:16], h[16:20], h[20:32], n))


def ph_attr(ph):
    if not ph:
        return ""
    a = '<p:ph type="%s"' % ph["type"]
    return a + (' idx="%s"/>' % ph["idx"] if ph["idx"] not in ("", None, "0") else "/>")


def sp(sid, ph, inner):
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr><a:spLocks noGrp="1"/>'
            '</p:cNvSpPr><p:nvPr>%s</p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            '%s</p:txBody></p:sp>' % (sid, ph["type"] if ph else "TextBox", ph_attr(ph), inner))


def tb(sid, rect, inner):
    """free text box, used only when the chosen layout has no matching placeholder"""
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="TextBox %d"/><p:cNvSpPr txBox="1"/><p:nvPr/>'
            '</p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody>'
            '<a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (sid, sid, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1], inner))


def pic(sid, rect, rid, ph, name="Figure"):
    return ('<p:pic><p:nvPicPr><p:cNvPr id="%d" name="%s"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
            '</p:cNvPicPr><p:nvPr>%s</p:nvPr></p:nvPicPr><p:blipFill><a:blip r:embed="%s"/>'
            '<a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
            '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '</p:pic>' % (sid, xesc(name).replace('"', ""), ph_attr(ph), rid,
                          rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]))


GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
       '<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
       '</a:xfrm></p:grpSpPr>')


def sld_xml(shapes):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<p:sld %s><p:cSld><p:spTree>'
            '%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
            % (NSD, GRP, shapes))


def img_dims(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
    if b[:2] == b"\xff\xd8":
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            mk = b[i + 1]
            if mk in (0xC0, 0xC1, 0xC2):
                return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            i += 2 if (mk in (0xD8, 0xD9, 0x01) or 0xD0 <= mk <= 0xD7) else 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return None


def fit_rect(rect, iw, ih):
    x0, y0, x1, y1 = rect
    W, Hh = x1 - x0, y1 - y0
    if iw and ih:
        s = min(W / float(iw), Hh / float(ih))
        w, h = int(iw * s), int(ih * s)
    else:
        w, h = int(W * 0.9), int(Hh * 0.9)
    return (x0 + (W - w) // 2, y0 + (Hh - h) // 2, x0 + (W + w) // 2, y0 + (Hh + h) // 2)


# ---- planning ----
def labels(cn):
    return {"outline": "\u6c47\u62a5\u5927\u7eb2" if cn else "Outline",
            "closing": "\u7ed3\u8bba\u4e0e\u5c55\u671b" if cn else "Conclusions"}


def build_plan(secs, n, nfig):
    flat = [(s, u) for s in secs for u in s["units"]]
    if not flat:
        return [{"role": "title"}, {"role": "closing"}]
    fig = 1 if (nfig and n >= 6) else 0
    k = max(1, min(n - 3 - fig, len(flat)))

    def make(k, fig):
        pgs = [{"role": "title"}, {"role": "outline"}]
        pgs += [{"role": "content", "sec": flat[i * len(flat) // k:(i + 1) * len(flat) // k]}
                for i in range(k) if flat[i * len(flat) // k:(i + 1) * len(flat) // k]]
        return pgs + ([{"role": "picture"}] if fig else []) + [{"role": "closing"}]

    def with_dividers(pgs, budget):
        """insert section-header pages before the first content page of each section"""
        out, seen, added = [], set(), 0
        for pg in pgs:
            if pg["role"] == "content" and added < budget:
                t = pg["sec"][0][0]["title"]
                if t not in seen:
                    seen.add(t)
                    out.append({"role": "section", "sec": [pg["sec"][0][0]]})
                    added += 1
            out.append(pg)
        return out

    pgs = make(k, fig)
    for drop in ("outline", "picture"):
        if len(pgs) > n:
            pgs = [p for p in pgs if p["role"] != drop]
    while len(pgs) > n and k > 1:
        pgs, k = make(k - 1, 0), k - 1
    while len(pgs) < n and k < len(flat):
        pgs, k = make(k + 1, fig), k + 1
    if len(pgs) < n:                      # source too thin for n content pages:
        pgs = with_dividers(pgs, n - len(pgs))   # use the template's section-header layout
    return pgs[:n]


def fig_caption(txt):
    """figure caption/lead-in, verbatim. v1 required 10 chars *before* 'Figure N' on the same
    line, so a sentence that simply starts with 'Figure 1 shows ...' was never found."""
    for m in re.finditer(r"(?m)^\s*(?:Figure|Fig\.?|\u56fe)\s*\d+[.:]?\s*(.{10,300})$", txt):
        return clip(m.group(0).strip(), 210)
    for m in re.finditer(r"(?:Figure|Fig\.?|\u56fe)\s*\d+[^.\n]{5,240}", txt):
        return clip(m.group(0).strip(), 210)
    return ""


def page_specs(d, wo, txt, title, lb):
    """paper -> per-page claims, bullets and verbatim evidence"""
    secs = outline(txt)
    out, used = [], set()
    for i, p in enumerate(build_plan(secs, int(wo["slides"] or 10), 1 if d["figures"] else 0), 1):
        s = {"n": i, "role": p["role"], "title": "", "sub": "", "bullets": [], "evidence": [],
             "notes": [], "fig": None, "layout": None, "deviation": None, "claim": ""}
        r = p["role"]
        if r == "title":
            s.update(title=title, claim=title,
                     sub=clip(str(wo.get("audience") or (Path(d["paper"]).name if d["paper"] else "")), 80))
        elif r == "outline":
            s.update(title=lb["outline"], claim="\u6309\u6b63\u6587\u7ae0\u8282\u987a\u5e8f\u5c55\u5f00",
                     bullets=["%d. %s" % (j + 1, x["title"]) for j, x in enumerate(secs[:7])],
                     evidence=[{"quote": x["title"],
                                "locator": "\u00a7%s p.%d" % (x["title"], x["units"][0]["page"]),
                                "kind": "section_heading"} for x in secs[:7]])
        elif r == "section":
            hd = p["sec"][0]
            s.update(title=clip(hd["title"], 60), claim=hd["title"], bullets=[],
                     evidence=[{"quote": hd["title"], "locator": "\u00a7%s p.%d" % (hd["title"], hd["units"][0]["page"]),
                                "kind": "section_heading"}] if hd.get("units") else [])
        elif r == "content":
            b = pick_bullets(p["sec"])
            s.update(title=clip(" / ".join(dict.fromkeys(u[0]["title"] for u in p["sec"])), 70),
                     bullets=[x["text"] for x in b], claim=b[0]["quote"] if b else "",
                     evidence=[{"quote": x["quote"], "locator": x["locator"], "kind": "sentence"} for x in b])
        elif r == "picture":
            cap, f = fig_caption(txt), d["figures"][0]
            s.update(fig=f, title=clip(cap, 70) if cap else lb["closing"] + " \u00b7 " + Path(f).stem,
                     bullets=[cap] if cap else [], claim=cap or Path(f).name,
                     evidence=[{"quote": cap, "locator": "caption in text; file %s" % Path(f).name,
                                "kind": "figure_caption"}] if cap else [],
                     deviation=None if cap else "figure_embedded_without_verbatim_caption")
        else:
            # closing page: prefer结论/总结/展望, then the abstract, never re-use earlier quotes
            pref = [x for x in secs if re.search(r"conclusion|summary|outlook|discussion|\u7ed3\u8bba|\u603b\u7ed3|\u5c55\u671b", x["title"], re.I)]
            b = []
            for sec in (pref + secs[:1] + secs[-1:]):
                b = pick_bullets([(sec, u) for u in sec["units"]], cap=3, exclude=used)
                if b:
                    break
            if not b and secs:
                # a closing slide may legitimately restate the headline result
                pool = [x for x in (pref + secs[:1]) if x] or secs
                b = pick_bullets([(sec, u) for sec in pool for u in sec["units"]], cap=3)
            s.update(title=lb["closing"], bullets=[x["text"] for x in b] or [lb["closing"]],
                     claim=b[0]["quote"] if b else lb["closing"],
                     evidence=[{"quote": x["quote"], "locator": x["locator"], "kind": "sentence"} for x in b])
        used.update(nk(e.get("quote", ""))[:60] for e in s["evidence"] if e.get("quote"))
        locs = "\u3001".join(dict.fromkeys(e["locator"] for e in s["evidence"]))[:150]
        s["notes"] = ["\u8bb2\u7a3f\uff1a%s\u672c\u9875\u8981\u70b9\u9010\u5b57\u5f15\u81ea %s\uff1b\u5148\u7ed9\u7ed3\u8bba\u518d\u6307\u5411\u8bc1\u636e\u3002"
                      % ("\u5c01\u9762\u9875\u3002" if r == "title" else "", locs)
                      if locs else "\u5c01\u9762\u9875\uff1a\u53e3\u5934\u4ecb\u7ecd\u9898\u76ee\u4e0e\u672c\u6b21\u6c47\u62a5\u7684\u4e3b\u7ebf\u3002"]
        out.append(s)
    return out, secs


# ---- checks ----
def rels_of(zf, part):
    d, n = part.rsplit("/", 1)
    p = "%s/_rels/%s.rels" % (d, n)
    if p not in zf.namelist():
        return {}
    out = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/>", zf.read(p).decode("utf-8", "replace")):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        out[a.get("Id")] = (a.get("Type", ""), a.get("Target", ""))
    return out


def pdf_pages(p):
    try:
        b = Path(p).read_bytes()
    except Exception:
        return 0, False
    if not b.startswith(b"%PDF"):
        return 0, False
    n = len(re.findall(rb"/Type\s*/Page[^s]", b))
    c = max([int(x) for x in re.findall(rb"/Count\s+(\d+)", b)] or [0])
    return max(n, c), True


def check(out, ctx):
    """artefact-level checks; per-page facts come from ctx written by the builder"""
    p, w = Path(out) / "presentation.pptx", []
    if not p.exists():
        return {"failures": ["presentation.pptx missing"], "warnings": [], "pass": False}
    try:
        zf = zipfile.ZipFile(str(p))
    except Exception as e:
        return {"failures": ["pptx unreadable: %s" % e], "warnings": [], "pass": False}
    with zf:
        nm = zf.namelist()
        sl = sorted((n for n in nm if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda x: int(re.findall(r"\d+", x)[-1]))
        bad, nolay, miss, fill, avail, notitle = [], [], [], 0, 0, []
        for i, s in enumerate(sl, 1):
            lay = [t for t in rels_of(zf, s).values() if t[0].endswith("/slideLayout")]
            if not lay:
                nolay.append(i)
            elif lay[0][1].replace("../", "ppt/") not in nm:
                miss.append(i)
            x = zf.read(s).decode("utf-8", "replace")
            ph, tx = len(re.findall(r"<p:ph\b", x)), len(re.findall(r"<a:t>[^<]", x))
            fill, avail = fill + min(ph, tx), avail + max(ph, 1)
            if not re.search(r'type="(ctrTitle|title)"', x):
                notitle.append(i)
        for k in ("master_sha256", "theme_sha256"):
            for part, want in (ctx.get(k) or {}).items():
                if part not in nm:
                    bad.append(part + " absent")
                elif hashlib.sha256(zf.read(part)).hexdigest() != want:
                    bad.append(part + " modified")
        nmedia = len([n for n in nm if n.startswith("ppt/media/")])
    pages = ctx.get("pages") or []
    seq = [str(pg.get("page_number_text") or "") for pg in pages]
    npg, ok = pdf_pages(Path(out) / "presentation.pdf")
    req = ctx.get("required_slides")
    if req and int(req) != len(sl):
        bad.append("slide count %d != required %s" % (len(sl), req))
    if not ok:
        w.append("no inspectable PDF export")
    return {"failures": bad, "warnings": w, "slide_count": len(sl),
            "template_inheritance": {
                "slides_with_layout_ref": len(sl) - len(nolay), "missing_layout_rel": nolay,
                "layout_parts_missing": miss, "layout_ids_exist": not miss,
                "master_sha256_unchanged": not any("master" in x for x in bad),
                "theme_sha256_unchanged": not any("theme" in x for x in bad), "media_parts": nmedia},
            "placeholder_fill_rate": round(fill / float(avail), 3) if avail else None,
            "slides_without_title_placeholder": notitle,
            "overflow_slides": [pg["n"] for pg in pages if pg.get("overflow")],
            "batch_consistency": {
                "footer_texts": sorted({pg.get("footer") for pg in pages if pg.get("footer")}),
                "footer_uniform": len({pg.get("footer") for pg in pages if pg.get("footer")}) <= 1,
                "page_numbers_sequential": (seq == [str(i) for i in range(1, len(seq) + 1)])
            if any(seq) else None,
            "page_numbers_rendered": any(seq),
            "note": "page numbers need a sldNum placeholder in the template layout" if not any(seq) else "",
                "title_placeholder_all_slides": not notitle,
                "font_scale_levels": sorted({pg.get("body_pt") for pg in pages if pg.get("body_pt")}),
                "freetext_boxes": sum(int(pg.get("freetext") or 0) for pg in pages)},
            "pptx_pdf_consistency": {"pdf_present": ok, "pdf_pages": npg, "pptx_pages": len(sl),
                                     "pages_match": bool(ok and npg == len(sl))},
            "fonts": ctx.get("fonts") or {}, "pass": not bad}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="slides-04 verifier: re-read an emitted deck and report conformance.")
    ap.add_argument("--out", default=".", help="directory holding presentation.pptx/.pdf/run_context.json")
    ap.add_argument("--ctx", default=None, help="builder context json (default <out>/run_context.json)")
    a = ap.parse_args(argv)
    ctx = {}
    for c in [a.ctx, str(Path(a.out) / "run_context.json")]:
        if c and Path(c).exists():
            try:
                ctx = json.loads(Path(c).read_text("utf-8"))
                break
            except Exception:
                pass
    print(json.dumps(check(a.out, ctx), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
