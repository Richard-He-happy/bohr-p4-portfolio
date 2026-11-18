#!/usr/bin/env python3
"""deckbuild: editable .pptx from a deck model (template surgery or minimal OOXML) + PDF export. stdlib only."""
import hashlib, re, shutil, subprocess, zipfile, zlib
from pathlib import Path
from xml.sax.saxutils import escape as _x
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = 'xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (A, R, P)
X = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
CP = "application/vnd.openxmlformats-officedocument.presentationml."
CT = {"pres": CP + "presentation.main+xml", "slide": CP + "slide+xml", "layout": CP + "slideLayout+xml", "master": CP + "slideMaster+xml", "notes": CP + "notesSlide+xml", "nmaster": CP + "notesMaster+xml", "theme": "application/vnd.openxmlformats-officedocument.theme+xml"}
SZ = (12192000, 6858000)
CMAP = '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
GRP = '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
def nm(s):
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s or "")).strip()
def x(t):
    return _x("" if t is None else str(t))
def paras(items, sz=None, bullet=True, bold=False):
    it = [i for i in (items if isinstance(items, (list, tuple)) else [items]) if str(i or "").strip()]
    if not it:
        return '<a:p><a:endParaRPr lang="en-US" dirty="0"/></a:p>'
    rp = '<a:rPr lang="en-US" altLang="zh-CN" sz="%d" b="%d" dirty="0"/>' % (sz or 1800, 1 if bold else 0)
    bu = '<a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>'
    return "".join('<a:p><a:pPr>%s</a:pPr><a:r>%s<a:t>%s</a:t></a:r></a:p>' % (bu, rp, x(t)) for t in it)
def sp(i, ph, txt, sz=None, bullet=True, bold=False, geom=None, name="Shape"):
    nv = '<p:ph type="%s"%s/>' % (ph[0], ' idx="%s"' % ph[1] if ph[1] not in (None, "") else "") if ph else ""
    box = '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>' if ph else '<p:cNvSpPr txBox="1"/>'
    geo = '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>' % tuple(geom) if geom else ""
    ex = "" if ph else '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s %d"/>%s<p:nvPr>%s</p:nvPr></p:nvSpPr><p:spPr>%s%s</p:spPr>'
            '<p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>' % (i, x(name), i, box, nv, geo, ex, paras(txt, sz, bullet, bold)))
def sld(shapes):
    return X + '<p:sld %s><p:cSld><p:spTree>%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>' % (NS, GRP, "".join(shapes))
def notes_xml(t):
    return X + '<p:notes %s><p:cSld><p:spTree>%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>' % (NS, GRP, sp(2, ("body", "1"), [t] if t else [], None, False, name="Notes"))
def rels_xml(pairs):
    return X + '<Relationships xmlns="%s">%s</Relationships>' % (PKG, "".join('<Relationship Id="%s" Type="%s" Target="%s"/>' % p for p in pairs))
def relmap(s):
    o = {}
    for tag in re.findall(r"<Relationship\b[^>]*/>", s):
        i, t, ty = re.search(r'Id="([^"]+)"', tag), re.search(r'Target="([^"]+)"', tag), re.search(r'Type="([^"]+)"', tag)
        if i and t:
            o[i.group(1)] = (t.group(1), ty.group(1) if ty else "")
    return o
def geom(w, h, k):
    d = {"left": (.05, .24, .44, .66), "sub": (.05, .55, .90, .20), "body": (.05, .24, .90, .66)}
    if k == "top":
        return (838200, 365125, w - 1676400, 1143000)
    a, b, c, e = d[k]
    return (int(w * a), int(h * b), int(w * c), int(h * e))
def shapes(s, w, h, tph, bph):
    out=[sp(2, tph, [s.get("title")], None, False, True, name="Title") if tph else sp(2, None, [s.get("title")], 3000, False, True, geom(w, h, "top"), "Title")]
    if s.get("role") == "title":
        out.append(sp(3, bph, s.get("bullets"), None, False, name="Subtitle") if bph else sp(3, None, s.get("bullets"), 1800, False, False, geom(w, h, "sub"), "Subtitle"))
    else:
        out.append(sp(3, bph, s.get("bullets"), None, True, name="Content") if bph else sp(3, None, s.get("bullets"), 1800, True, False, geom(w, h, "body"), "Content"))
    return out
def lay_xml(kind):
    sz = (("ctrTitle", None, 4000, True, (838200, 1600200, 10515600, 1905000), "Title"), ("subTitle", "1", 1800, False, (838200, 3657600, 10515600, 1651000), "Sub")) if kind == 1 else \
         (("title", None, 3000, True, (838200, 365125, 10515600, 1143000), "Title"), ("body", "1", 1800, False, (838200, 1600200, 10515600, 4525963), "Content"))
    head = 'type="title" preserve="1"><p:cSld name="Title Slide"' if kind == 1 else 'type="obj" preserve="1"><p:cSld name="Title and Content"'
    body = sp(2, (sz[0][0], sz[0][1]), ["Title"], sz[0][2], False, sz[0][3], sz[0][4], sz[0][5]) + sp(3, (sz[1][0], sz[1][1]), ["Body"], sz[1][2], kind == 2, False, sz[1][4], sz[1][5])
    return X + '<p:sldLayout %s %s><p:spTree>%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>' % (NS, head, GRP, body)
def master_xml():
    tx = ('<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="3000" b="1"/></a:lvl1pPr></p:titleStyle><p:bodyStyle>'
          '<a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle><p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle></p:txStyles>')
    return X + ('<p:sldMaster %s><p:cSld><p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
                '<p:spTree>%s</p:spTree></p:cSld>%s<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/><p:sldLayoutId id="2147483650" r:id="rId2"/></p:sldLayoutIdLst>%s</p:sldMaster>') % (NS, GRP, CMAP, tx)
def theme_xml():
    kn, acc = ("dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"), ("1F3864", "E7E6E6", "2F5597", "C55A11", "70AD47", "7F6000", "4472C4", "808080")
    sch = ('<a:clrScheme name="PaperDeck"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
           + "".join('<a:%s><a:srgbClr val="%s"/></a:%s>' % (k, v, k) for k, v in zip(kn, acc))
           + '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>')
    fnt = ('<a:fontScheme name="PaperDeck"><a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
           '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>')
    f, ln, ef = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>', '<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>', '<a:effectStyle><a:effectLst/></a:effectStyle>'
    fmt = ('<a:fmtScheme name="PaperDeck"><a:fillStyleLst>%s%s%s</a:fillStyleLst><a:lnStyleLst>%s%s%s</a:lnStyleLst><a:effectStyleLst>%s%s%s</a:effectStyleLst>'
           '<a:bgFillStyleLst>%s%s%s</a:bgFillStyleLst></a:fmtScheme>' % (f, f, f, ln, ln, ln, ef, ef, ef, f, f, f))
    return X + '<a:theme xmlns:a="%s" name="PaperDeck"><a:themeElements>%s%s%s</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>' % (A, sch, fnt, fmt)
def nmaster_xml():
    return X + ('<p:notesMaster %s><p:cSld><p:spTree>%s%s</p:spTree></p:cSld>%s<p:notesStyle><a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr></p:notesStyle></p:notesMaster>') % (
        NS, GRP, sp(2, ("body", "1"), [], 1200, False, False, (685800, 1143000, 5486400, 4800600), "Notes"), CMAP)
def skeleton(sz=SZ):
    w, h = sz
    lr = rels_xml([("rId1", R + "/slideMaster", "../slideMasters/slideMaster1.xml")])
    return {"_rels/.rels": rels_xml([("rId1", R + "/officeDocument", "ppt/presentation.xml")]),
            "ppt/slideMasters/slideMaster1.xml": master_xml(),
            "ppt/slideMasters/_rels/slideMaster1.xml.rels": rels_xml([("rId1", R + "/slideLayout", "../slideLayouts/slideLayout1.xml"), ("rId2", R + "/slideLayout", "../slideLayouts/slideLayout2.xml"), ("rId3", R + "/theme", "../theme/theme1.xml")]),
            "ppt/slideLayouts/slideLayout1.xml": lay_xml(1), "ppt/slideLayouts/slideLayout2.xml": lay_xml(2),
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": lr, "ppt/slideLayouts/_rels/slideLayout2.xml.rels": lr,
            "ppt/theme/theme1.xml": theme_xml(), "ppt/notesMasters/notesMaster1.xml": nmaster_xml(),
            "ppt/notesMasters/_rels/notesMaster1.xml.rels": rels_xml([("rId1", R + "/theme", "../theme/theme1.xml")]),
            "ppt/presentation.xml": (X + '<p:presentation %s saveSubsetFonts="1"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                                     '<p:sldIdLst></p:sldIdLst><p:sldSz cx="%d" cy="%d"/><p:notesSz cx="6858000" cy="9144000"/><p:defaultTextStyle><a:lvl1pPr>'
                                     '<a:defRPr sz="1800"/></a:lvl1pPr></p:defaultTextStyle></p:presentation>') % (NS, w, h),
            "ppt/_rels/presentation.xml.rels": rels_xml([("rId1", R + "/slideMaster", "slideMasters/slideMaster1.xml"), ("rId2", R + "/theme", "theme/theme1.xml"), ("rId3", R + "/notesMaster", "notesMasters/notesMaster1.xml")])}
def ct_xml(rows):
    return (X + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Default Extension="jpeg" ContentType="image/jpeg"/>'
            + "".join('<Override PartName="/%s" ContentType="%s"/>' % r for r in rows) + "</Types>")
def write_zip(path, parts):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k in ["[Content_Types].xml"] + sorted(k for k in parts if k != "[Content_Types].xml"):
            v = parts[k]
            z.writestr(k, v.encode("utf-8") if isinstance(v, str) else v)
def layouts(z):
    out = []
    for name in sorted((n for n in z if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n)), key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1))):
        s = z[name].decode("utf-8", "ignore") if isinstance(z[name], bytes) else z[name]
        ty, nm = re.search(r'<p:sldLayout\b[^>]*\btype="([^"]+)"', s), re.search(r'<p:cSld\b[^>]*\bname="([^"]*)"', s)
        ph = []
        for a1 in re.findall(r"<p:ph\b([^>]*?)/?>", s):
            t1, i1 = re.search(r'type="([^"]+)"', a1), re.search(r'idx="(\d+)"', a1)
            ph.append((t1.group(1) if t1 else "body", i1.group(1) if i1 else None))
        out.append({"part": name, "type": ty.group(1) if ty else "", "name": nm.group(1) if nm else "", "phs": ph})
    return out
def build(slides, out, template=None):
    th = mh = None
    if template:
        with zipfile.ZipFile(template) as zin:
            z = {n: zin.read(n) for n in zin.namelist() if not n.endswith("/")}
        if "ppt/presentation.xml" not in z:
            raise ValueError("template lacks ppt/presentation.xml")
        th = {n: hashlib.sha256(z[n]).hexdigest() for n in z if re.match(r"ppt/theme/theme\d+\.xml$", n)}
        mh = {n: hashlib.sha256(z[n]).hexdigest() for n in z if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", n)}
        ct = []
    else:
        z, ct = skeleton(), [("ppt/presentation.xml", CT["pres"]), ("ppt/slideMasters/slideMaster1.xml", CT["master"]), ("ppt/slideLayouts/slideLayout1.xml", CT["layout"]), ("ppt/slideLayouts/slideLayout2.xml", CT["layout"]), ("ppt/theme/theme1.xml", CT["theme"]), ("ppt/notesMasters/notesMaster1.xml", CT["nmaster"])]
    g = lambda k: (z.get(k) or b"").decode("utf-8", "ignore") if isinstance(z.get(k), bytes) else (z.get(k) or "")
    pres, rl = g("ppt/presentation.xml"), relmap(g("ppt/_rels/presentation.xml.rels"))
    m = re.search(r'<p:sldSz\b[^>]*cx="(\d+)"[^>]*cy="(\d+)"', pres)
    w, h = (int(m.group(1)), int(m.group(2))) if m else SZ
    nm = next((t.replace("../", "") for t, ty in rl.values() if ty.endswith("/notesMaster")), None)
    nm = "ppt/" + nm if nm and not nm.startswith("ppt/") else nm
    nm = nm if nm and nm in z else None
    cts = g("[Content_Types].xml")
    dropped = 0
    if template:
        for p in [q for q in z if re.match(r"ppt/(slides|notesSlides)/", q)]:
            cts = re.sub(r'<Override PartName="/%s"[^>]*/>' % re.escape(p), "", cts)
            z.pop(p, None)
            dropped += 1 if re.match(r"ppt/slides/slide\d+\.xml$", p) else 0
    ls = layouts(z)
    lt = next((L for L in ls if L["type"] == "title"), None) or (ls[0] if ls else None)
    lb = next((L for L in ls if L["type"] in ("obj", "tx", "secHead")), None) or (ls[-1] if ls else lt)
    ids, ro = [], [(rid, ty, t) for rid, (t, ty) in rl.items() if not re.search(r"/(slide|notesSlide)$", ty)]
    for i, s in enumerate(slides):
        n, ttl = i + 1, s.get("role") == "title"
        L = lt if ttl else lb
        phs = (L or {}).get("phs", [])
        tph = next((q for q in phs if q[0] in ("title", "ctrTitle")), None)
        bph = next((q for q in phs if q[0] in ("body", "obj", "subTitle", "tx")), None)
        sr = ([("rId1", R + "/slideLayout", "../slideLayouts/" + Path(L["part"]).name)] if L else []) + ([("rId2", R + "/notesSlide", "../notesSlides/notesSlide%d.xml" % n)] if nm else [])
        z["ppt/slides/slide%d.xml" % n] = sld(shapes(s, w, h, tph, bph))
        z["ppt/slides/_rels/slide%d.xml.rels" % n] = rels_xml(sr)
        ct.append(("ppt/slides/slide%d.xml" % n, CT["slide"]))
        ro.append(("rIdS%d" % n, R + "/slide", "slides/slide%d.xml" % n))
        ids.append('<p:sldId id="%d" r:id="rIdS%d"/>' % (256 + i, n))
        if nm:
            z["ppt/notesSlides/notesSlide%d.xml" % n] = notes_xml(s.get("notes"))
            z["ppt/notesSlides/_rels/notesSlide%d.xml.rels" % n] = rels_xml([("rId1", R + "/slide", "../slides/slide%d.xml" % n), ("rId2", R + "/notesMaster", "../" + nm.replace("ppt/", ""))])
            ct.append(("ppt/notesSlides/notesSlide%d.xml" % n, CT["notes"]))
            ro.append(("rIdN%d" % n, R + "/notesSlide", "notesSlides/notesSlide%d.xml" % n))
    lst = "<p:sldIdLst>%s</p:sldIdLst>" % "".join(ids)
    pres = re.sub(r"<p:sldIdLst>.*?</p:sldIdLst>", lst, pres, flags=re.S) if "<p:sldIdLst>" in pres else pres.replace("</p:sldMasterIdLst>", "</p:sldMasterIdLst>" + lst)
    z["ppt/presentation.xml"] = pres.encode("utf-8")
    z["ppt/_rels/presentation.xml.rels"] = rels_xml(ro).encode("utf-8")
    z["[Content_Types].xml"] = (cts.replace("</Types>", "".join('<Override PartName="/%s" ContentType="%s"/>' % c for c in ct) + "</Types>") if "</Types>" in cts else ct_xml(ct)).encode("utf-8")
    write_zip(out, z)
    return {"engine": "stdlib-ooxml-template-surgery" if template else "stdlib-ooxml-minimal", "template": str(template) if template else None,
            "master": [Path(p).name for p in sorted(mh)] if mh else ["slideMaster1.xml"],
            "layout_names": sorted({(lt or {}).get("name", ""), (lb or {}).get("name", "")} - {""}),
            "layouts_used": sorted({Path((L or {}).get("part", "")).name for L in (lt, lb)} - {"."}),
            "theme_unchanged": (th == {n: hashlib.sha256(z[n]).hexdigest() for n in th if n in z}) if th else None,
            "master_unchanged": (mh == {n: hashlib.sha256(z[n]).hexdigest() for n in mh if n in z}) if mh else None,
            "sz": [w, h], "dropped_slides": dropped}
def export_pdf(pptx, outdir, work=None, timeout=240):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tgt = outdir / (Path(pptx).stem + ".pdf")
    tries = []
    lo = shutil.which("soffice") or shutil.which("libreoffice")
    if lo:
        try:
            subprocess.run([lo, "-env:UserInstallation=file://%s" % (Path(work or outdir) / "_lo_profile"), "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(outdir), str(pptx)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            tries.append(["libreoffice", bool(tgt.exists())])
        except Exception:  # noqa: BLE001
            tries.append(["libreoffice", "error"])
    r = shutil.which("office-renderer")
    if r and not tgt.exists():
        try:
            subprocess.run([r, str(pptx), str(tgt)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            tries.append(["office-renderer", bool(tgt.exists())])
        except Exception:  # noqa: BLE001
            tries.append(["office-renderer", "error"])
    if tgt.exists() and tgt.read_bytes()[:5] == b"%PDF-":
        return {"pdf": str(tgt), "engine": "libreoffice" if tries and tries[0][1] is True else (tries[-1][0] if tries else None), "tries": tries, "degraded": False}
    return {"pdf": None, "engine": None, "tries": tries, "degraded": True}
def extract(path):
    """Chain: pdftotext -> stdlib FlateDecode/Tj -> docx/pptx/md/txt."""
    txt, pages, eng, suf = "", [], "none", path.suffix.lower()
    if suf == ".pdf":
        try:
            r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            if r.stdout and len(r.stdout.strip()) > 200:
                txt, eng = r.stdout.decode("utf-8", "ignore"), "pdftotext"
        except Exception:
            pass
        if not txt:
            raw = []
            for m in re.finditer(rb"stream\r?\n(.*?)endstream", path.read_bytes(), re.S):
                try:
                    b = zlib.decompress(m.group(1))
                except Exception:
                    continue
                if b"Tj" in b or b"TJ" in b:
                    raw += [t[1:-1].decode("latin-1", "ignore") for t in re.findall(rb"\((?:\\\\.|[^\\\\()])*\)", b)]
            txt, eng = " ".join(raw), ("stdlib-inflate" if len(" ".join(raw).strip()) > 100 else "none")
        pages = pages or txt.split("\f")
    elif suf in (".docx", ".pptx"):
        with zipfile.ZipFile(path) as z:
            qs = [q for q in z.namelist() if re.match(r"word/document\.xml$|ppt/slides/slide\d+\.xml$", q)]
            txt = re.sub(r"\s+", " ", " ".join(re.sub(r"<[^>]+>", " ", z.read(q).decode("utf-8", "ignore")) for q in qs))
        pages, eng = [txt], suf[1:]
    else:
        txt = path.read_text(encoding="utf-8", errors="ignore")
        pages, eng = txt.split("\f"), (suf[1:] or "txt")
    L = [l.strip() for l in (pages[0] if pages else "").split("\n") if l.strip()][:8]
    meta = {"title": next((l for l in L[:5] if 25 <= len(l) <= 190 and not re.search(r"@|doi|http|arxiv|copyright|©", l, re.I)), ""),
            "byline": [l for l in L[1:6] if re.search(r"[A-Z][a-z]+ [A-Z]", l) and len(l) < 160][:2], "stem": path.stem}
    return {"text": nm(txt), "pages": pages or [txt], "engine": eng, "meta": meta}
def validate_pptx(path, expect=None):
    import xml.etree.ElementTree as ET
    rep = {"path": str(path), "ok": False, "members": 0, "slides": 0, "notes": 0, "issues": []}
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:  # noqa: BLE001
        rep["issues"].append("not a zip: %s" % e)
        return rep
    names = z.namelist()
    rep["members"] = len(names)
    rep["issues"] += ["missing " + n for n in ("[Content_Types].xml", "ppt/presentation.xml") if n not in names]
    sl = sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))
    rep["slides"] = len(sl)
    rep["notes"] = len([n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)])
    for n in sl:
        try:
            ET.fromstring(z.read(n))
        except Exception as e:  # noqa: BLE001
            rep["issues"].append("bad xml %s: %s" % (n, e))
    if expect and rep["slides"] != expect:
        rep["issues"].append("slide count %d != expected %d" % (rep["slides"], expect))
    rep["ok"] = not rep["issues"]
    return rep
def pdf_info(path):
    try:
        b = Path(path).read_bytes()
    except Exception:
        return {"path": str(path), "ok": False, "pages": 0}
    n = len(re.findall(rb"/Type\s*/Page[^s]", b))
    return {"path": str(path), "ok": b[:5] == b"%PDF-" and n > 0, "pages": n}
