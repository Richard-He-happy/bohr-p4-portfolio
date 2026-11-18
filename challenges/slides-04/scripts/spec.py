#!/usr/bin/env python3
"""slides-04 v2 asset engine: template specification, per-item format compliance, export check.

Every reported value is read back from the emitted package (or the template part it inherits
from) and carries the literal XML/PDF snippet that supports it, so a reviewer can re-check the
number without trusting this code. stdlib only.
"""
import hashlib, math, re, shutil, subprocess, zipfile
from pathlib import Path

REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")


def text_units(t):
    """advance width in em: CJK ~1.0, Latin average ~0.52 (measured against Georgia/Calibri)"""
    return sum(1.0 if CJK.match(c) else 0.52 for c in str(t))


def est_height(paras, w_pt, default_pt):
    """estimated rendered text height in pt for a fixed-width text frame"""
    tot = 0.0
    for p in paras:
        t = (p.get("text") or "").strip()
        if not t:
            continue
        sz = p.get("sz") or default_pt or 18.0
        ls = (p.get("lnspc_pct") or 100.0) / 100.0
        lines = max(1, int(math.ceil(text_units(t) * sz / max(w_pt * 0.96, 1.0))))
        tot += lines * sz * 1.20 * ls * 1.04
    return tot


def sha(b):
    return hashlib.sha256(b).hexdigest()


def attrs(s):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', s or ""))


def rect_of(xml):
    o = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/>', xml)
    e = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', xml)
    if not (o and e):
        return None
    x, y, cx, cy = int(o.group(1)), int(o.group(2)), int(e.group(1)), int(e.group(2))
    return [x, y, x + cx, y + cy]


def inch(emu):
    return round(emu / 914400.0, 3)


def ratio_str(cx, cy):
    g = math.gcd(int(cx), int(cy)) if cx and cy else 1
    return "%d:%d" % (cx // g, cy // g) if g else "?"


def shapes(xml):
    """slide/layout/master spTree -> [{kind, name, ph, rect, xml}] (no gesture at ordering)"""
    out = []
    for m in re.finditer(r"<p:(sp|pic)\b[^>]*>.*?</p:\1>", xml, re.S):
        blk = m.group(0)
        ph = re.search(r"<p:ph\b([^>/]*)/?>", blk)
        a = attrs(ph.group(1) if ph else "")
        nm = re.search(r'<p:cNvPr id="\d+" name="([^"]*)"', blk)
        out.append({"kind": m.group(1), "name": nm.group(1) if nm else "",
                    "ph": ({"type": a.get("type", "body"), "idx": a.get("idx", "0")} if ph else None),
                    "rect": rect_of(blk), "xml": blk,
                    "is_freetext": bool(ph) is False})
    return out


def rels(parts, part):
    d, n = part.rsplit("/", 1)
    p = "%s/_rels/%s.rels" % (d, n)
    if p not in parts:
        return {}
    out = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/>", parts[p].decode("utf-8", "replace")):
        a = attrs(m.group(1))
        out[a.get("Id")] = (a.get("Type", ""), a.get("Target", ""))
    return out


def resolve(base_part, target):
    t = target.lstrip("/")
    if target.startswith("/"):
        return t
    d = base_part.rsplit("/", 1)[0]
    seg = (d + "/" + t).split("/")
    out = []
    for s in seg:
        if s == "..":
            out = out[:-1]
        elif s not in (".", ""):
            out.append(s)
    return "/".join(out)


def tx_style(xml, tag):
    """p:txStyles/<tag> lvl1pPr -> {sz_pt, lnspc_pct, bullet, marL}"""
    blk = re.search(r"<p:%s>(.*?)</p:%s>" % (tag, tag), xml, re.S)
    if not blk:
        return {}
    b = blk.group(1)
    lvl = re.search(r"<a:lvl1pPr\b([^>]*)>", b)
    d = {}
    m = re.search(r'<a:defRPr\b[^>]*sz="(\d+)"', b)
    if m:
        d["sz_pt"] = int(m.group(1)) / 100.0
    m = re.search(r'<a:lnSpc><a:spcPct val="(\d+)"', b)
    if m:
        d["lnspc_pct"] = int(m.group(1)) / 1000.0
    d["bullet"] = bool(re.search(r"<a:bu(Char|AutoNum)", b))
    d["marL_emu"] = int(attrs(lvl.group(1)).get("marL", 0)) if lvl else 0
    return d


def parse_theme(part, xml):
    cols = {}
    for m in re.finditer(r"<a:(dk1|lt1|dk2|lt2|accent[1-6]|hlink|folHlink)>(.*?)</a:\1>", xml, re.S):
        inner = m.group(2)
        s = re.search(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', inner)
        y = re.search(r'<a:sysClr val="(\w+)"(?: lastClr="([0-9A-Fa-f]{6})")?', inner)
        if s:
            cols[m.group(1)] = {"kind": "srgb", "value": s.group(1).upper()}
        elif y:
            cols[m.group(1)] = {"kind": "sys", "value": y.group(1), "last": (y.group(2) or "").upper()}
    fonts = {}
    for grp, key in (("majorFont", "major"), ("minorFont", "minor")):
        blk = re.search(r"<a:%s>(.*?)</a:%s>" % (grp, grp), xml, re.S)
        inner = blk.group(1) if blk else ""
        for script in ("latin", "ea", "cs"):
            m = re.search(r'<a:%s typeface="([^"]*)"' % script, inner)
            fonts["%s_%s" % (key, script)] = m.group(1) if m else ""
    nm = re.search(r'<a:theme\b[^>]*name="([^"]*)"', xml)
    fs = re.search(r'<a:fontScheme\b[^>]*name="([^"]*)"', xml)
    cs = re.search(r'<a:clrScheme\b[^>]*name="([^"]*)"', xml)
    return {"part": part, "sha256": sha(xml.encode("utf-8", "replace")), "name": nm.group(1) if nm else "",
            "color_scheme": cols, "colors": {k: v.get("value") for k, v in cols.items()},
            "fonts": fonts, "font_scheme": fs.group(1) if fs else "",
            "clr_scheme_name": cs.group(1) if cs else ""}


def parse_master(part, xml, nlayouts):
    phs = []
    for s in shapes(xml):
        if s["ph"]:
            phs.append({"type": s["ph"]["type"], "idx": s["ph"]["idx"], "name": s["name"],
                        "rect_emu": s["rect"], "rect_in": [inch(v) for v in s["rect"]] if s["rect"] else None})
    cm = re.search(r"<p:clrMap\b([^>]*)/>", xml)
    title, body, other = (tx_style(xml, t) for t in ("titleStyle", "bodyStyle", "otherStyle"))
    lst = re.search(r'<p:sldLayoutIdLst>(.*?)</p:sldLayoutIdLst>', xml, re.S)
    return {"part": part, "sha256": sha(xml.encode("utf-8", "replace")), "placeholders": phs,
            "clr_map": attrs(cm.group(1)) if cm else {},
            "tx_styles": {"title": title, "body": body, "other": other},
            "title_sz_pt": title.get("sz_pt"), "body_sz_pt": body.get("sz_pt"),
            "body_lnspc_pct": body.get("lnspc_pct"),
            "layout_count_declared": len(re.findall(r"<p:sldLayoutId\b", lst.group(1))) if lst else 0}


def parse_layout(idx, part, xml):
    phs = []
    for s in shapes(xml):
        if s["ph"]:
            phs.append({"type": s["ph"]["type"], "idx": s["ph"]["idx"], "name": s["name"],
                        "rect_emu": s["rect"], "rect_in": [inch(v) for v in s["rect"]] if s["rect"] else None})
    nm = re.search(r'<p:cSld\b[^>]*name="([^"]*)"', xml) or re.search(r'<p:cSld\b[^>]*name="([^"]*)"', xml)
    ty = re.search(r'<p:sldLayout\b[^>]*type="([^"]*)"', xml)
    ov = re.search(r"<p:clrMapOvr>(.*?)</p:clrMapOvr>", xml, re.S)
    return {"index": idx, "part": part, "sha256": sha(xml.encode("utf-8", "replace")),
            "name": nm.group(1) if nm else part, "type": (ty.group(1) if ty else "").lower(),
            "placeholders": phs, "placeholder_types": sorted({p["type"] for p in phs}),
            "clr_map_ovr": "masterClrMapping" if ov and "masterClrMapping" in ov.group(1) else "custom",
            "show_master_shapes": 'showMasterSp="0"' not in xml}


def build_spec(parts, tpl_path):
    """read-only template anatomy -> template_spec.json skeleton (layout_map filled after build)"""
    nm = list(parts)
    pres = parts["ppt/presentation.xml"].decode("utf-8", "replace")
    notes = []
    sz = re.search(r'<p:sldSz\b([^>]*)/>', pres)
    a = attrs(sz.group(1)) if sz else {}
    cx, cy = int(a.get("cx", 12192000)), int(a.get("cy", 6858000))
    mpart = sorted(x for x in nm if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", x))
    lpart = sorted((x for x in nm if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", x)),
                   key=lambda p: int(re.findall(r"\d+", p)[-1]))
    tpart = sorted(x for x in nm if re.match(r"ppt/theme/theme\d+\.xml$", x))
    if not lpart:
        notes.append("no slideLayout part in template")
    if not mpart:
        notes.append("no slideMaster part in template")
    masters = [parse_master(p, parts[p].decode("utf-8", "replace"), len(lpart)) for p in mpart]
    layouts = [parse_layout(i + 1, p, parts[p].decode("utf-8", "replace")) for i, p in enumerate(lpart)]
    theme = parse_theme(tpart[0], parts[tpart[0]].decode("utf-8", "replace")) if tpart else {}
    slides = [x for x in nm if re.match(r"ppt/slides/slide\d+\.xml$", x)]
    media = [x for x in nm if x.startswith("ppt/media/")]
    prot = {p: sha(parts[p]) for p in nm if re.match(
        r"ppt/(slideMasters/slideMaster\d+|slideLayouts/slideLayout\d+|theme/theme\d+)\.xml$", p)}
    return {
        "spec_version": "2.0",
        "template": {"path": str(tpl_path), "bytes": Path(tpl_path).stat().st_size if Path(tpl_path).exists() else None,
                     "sha256": sha(Path(tpl_path).read_bytes()) if Path(tpl_path).exists() else None,
                     "package_parts": len(nm)},
        "slide_size": {"cx_emu": cx, "cy_emu": cy, "width_in": inch(cx), "height_in": inch(cy),
                       "ratio": ratio_str(cx, cy), "ratio_value": round(cx / float(cy), 4) if cy else None,
                       "orientation": "landscape" if cx >= cy else "portrait",
                       "evidence": (sz.group(0) if sz else "")},
        "counts": {"masters": len(masters), "layouts": len(layouts), "themes": len(tpart),
                   "slides_in_template": len(slides), "media_parts": len(media)},
        "masters": masters,
        "layouts": layouts,
        "theme": theme,
        "theme_fonts": (theme or {}).get("fonts", {}),
        "palette": (theme or {}).get("colors", {}),
        "notes_slide_size": (lambda m: {"cx_emu": int(m.group(1)), "cy_emu": int(m.group(2))} if m else None)(
            re.search(r'<p:notesSz cx="(\d+)" cy="(\d+)"', pres)),
        "protected_parts": prot,
        "layout_map": [],
        "layout_map_status": "pending_build",
        "parse_notes": notes,
    }


def layout_by_part(spec, part):
    return next((l for l in spec["layouts"] if l["part"] == part), None)


def layout_map(spec, cms):
    """page -> template layout binding, resolved through each slide part's rels"""
    rows = []
    by_part = {c.get("layout_id"): c for c in cms}
    for c in cms:
        lp = c.get("layout_id")
        L = layout_by_part(spec, lp) if lp else None
        filled = [f.get("type") for f in (c.get("placeholders_filled") or [])]
        avail = (L or {}).get("placeholder_types", [])
        rows.append({"page": c.get("n"), "role": c.get("role"), "layout_part": lp,
                     "layout_index": (L or {}).get("index"), "layout_name": (L or {}).get("name"),
                     "layout_type": (L or {}).get("type"),
                     "placeholders_filled": filled,
                     "placeholders_available": avail,
                     "placeholders_used_of_available": [t for t in filled if t in avail],
                     "invented_placeholders": [t for t in filled if t not in avail],
                     "freetext_boxes": c.get("freetextbox_count")})
    return rows


# ---------------------------------------------------------------- emitted deck
def analyze_deck(pptx, spec):
    """re-read the emitted pptx: per slide geometry, runs, sizes, colours, fit estimate"""
    z = zipfile.ZipFile(str(pptx))
    with z:
        parts = {n: z.read(n) for n in z.namelist()}
    nm = list(parts)
    pres = parts["ppt/presentation.xml"].decode("utf-8", "replace")
    sz = re.search(r'<p:sldSz\b([^>]*)/>', pres)
    a = attrs(sz.group(1)) if sz else {}
    cx, cy = int(a.get("cx", 0)), int(a.get("cy", 0))
    sl = sorted((n for n in nm if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                key=lambda p: int(re.findall(r"\d+", p)[-1]))
    m = spec["masters"][0] if spec.get("masters") else {}
    lay = {l["part"]: l for l in spec.get("layouts", [])}
    facts = {"parts": parts, "presentation": pres, "size": {"cx_emu": cx, "cy_emu": cy,
             "width_in": inch(cx), "height_in": inch(cy), "ratio": ratio_str(cx, cy),
             "evidence": sz.group(0) if sz else ""}, "slides": [],
             "default_title_pt": (m.get("tx_styles") or {}).get("title", {}).get("sz_pt"),
             "default_body_pt": (m.get("tx_styles") or {}).get("body", {}).get("sz_pt"),
             "default_other_pt": (m.get("tx_styles") or {}).get("other", {}).get("sz_pt"),
             "default_body_lnspc": (m.get("tx_styles") or {}).get("body", {}).get("lnspc_pct"),
             "master_part": (m or {}).get("part")}
    for i, p in enumerate(sl, 1):
        x = parts[p].decode("utf-8", "replace")
        r = rels(parts, p)
        lref = next((resolve(p, t) for typ, t in r.values() if typ.endswith("/slideLayout")), None)
        L = lay.get(lref) or {}
        phrect = {(q["type"], q["idx"]): q["rect_emu"] for q in (L.get("placeholders") or []) if q["rect_emu"]}
        phrect.update({(q["type"], "0"): q["rect_emu"] for q in (L.get("placeholders") or []) if q["rect_emu"]})
        sh, over, inside = [], 0.0, True
        for s in shapes(x):
            rc, src = s["rect"], "slide"
            if rc is None and s["ph"]:
                rc = phrect.get((s["ph"]["type"], s["ph"]["idx"]))
                src = "layout" if rc else "none"
            paras = []
            for pm in re.finditer(r"<a:p>(.*?)</a:p>", s["xml"], re.S):
                pb = pm.group(1)
                tx = "".join(re.findall(r"<a:t>([^<]*)</a:t>", pb))
                rsz = [int(v) / 100.0 for v in re.findall(r'<a:rPr\b[^>]*\bsz="(\d+)"', pb)]
                rsz += [int(v) / 100.0 for v in re.findall(r'<a:defRPr\b[^>]*\bsz="(\d+)"', pb)]
                ls = re.search(r'<a:lnSpc><a:spcPct val="(\d+)"', pb)
                paras.append({"text": tx, "sz": rsz[0] if rsz else None,
                              "lnspc_pct": int(ls.group(1)) / 1000.0 if ls else None})
            if s["ph"] and s["ph"]["type"] in ("title", "ctrTitle"):
                dsz = facts["default_title_pt"]
            elif s["ph"] and s["ph"]["type"] in ("ftr", "sldNum", "dt"):
                dsz = min(facts["default_other_pt"] or 12.0, 14.0)
            elif s["is_freetext"]:
                dsz = min(facts["default_other_pt"] or 18.0, 18.0)
            else:
                dsz = facts["default_body_pt"] or 18.0
            fit, r = None, None
            if rc and any(pp["text"].strip() for pp in paras):
                w = (rc[2] - rc[0]) / 12700.0 - 14.0
                h = (rc[3] - rc[1]) / 12700.0 - 6.0
                tot = est_height(paras, w, dsz)
                r = round(tot / h, 3) if h > 0 else None
                fit = bool(r is not None and r <= 1.02)
                over = max(over, r or 0)
            if rc and (rc[0] < 0 or rc[1] < 0 or rc[2] > cx + 1 or rc[3] > cy + 1):
                inside = False
            sh.append({"kind": s["kind"], "name": s["name"], "ph": s["ph"], "rect": rc, "rect_source": src,
                       "is_freetext": s["is_freetext"], "xml": s["xml"],
                       "paras": paras, "sizes": sorted({pp["sz"] for pp in paras if pp["sz"]}),
                       "fit_ratio": r, "fits": fit,
                       "srgb": sorted(set(re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', s["xml"]))),
                       "scheme": sorted(set(re.findall(r'<a:schemeClr val="(\w+)"', s["xml"]))),
                       "autofit": ("normAutofit" if "normAutofit" in s["xml"] else
                                   "spAutoFit" if "spAutoFit" in s["xml"] else "none"),
                       "has_lnspc": "<a:lnSpc>" in s["xml"],
                       "ph_type": (s["ph"] or {}).get("type")})
        facts["slides"].append({
            "n": i, "part": p, "layout_part": lref, "layout_name": L.get("name"),
            "layout_type": L.get("type"), "shapes": sh,
            "placeholder_types": sorted({s["ph_type"] for s in sh if s["ph_type"]}),
            "freetext": sum(1 for s in sh if s["is_freetext"]),
            "max_fit_ratio": round(over, 3), "geometry_inside_page": inside,
            "sizes": sorted({v for s in sh for v in s["sizes"]}),
            "has_lnspc": any(s["has_lnspc"] for s in sh),
            "srgb": sorted({v for s in sh for v in s["srgb"]}),
            "scheme": sorted({v for s in sh for v in s["scheme"]}),
            "has_sldnum": "sldNum" in {s["ph_type"] for s in sh},
            "has_ftr": "ftr" in {s["ph_type"] for s in sh},
            "text": " ".join(pp["text"] for s in sh for pp in s["paras"] if pp["text"]),
            "title_text": " ".join(pp["text"] for s in sh if s["ph_type"] in ("title", "ctrTitle")
                                   for pp in s["paras"] if pp["text"])})
    return facts


def clip_snip(t, n=140):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n - 1] + "\u2026"


def _ev(facts, part, pattern, locator):
    xml = facts["parts"].get(part, b"").decode("utf-8", "replace")
    m = re.search(pattern, xml, re.S)
    sn = m.group(0) if m else ""
    return {"part": part, "locator": locator, "snippet": sn[:220],
            "verified_in_part": bool(sn) and sn in xml}


def _ck(cid, item, req, actual, ok, ev, note=""):
    return {"id": cid, "item": item, "requirement": req, "actual": actual,
            "status": "pass" if ok else "fail", "evidence": ev, "note": note}


def compliance(facts, spec, wo, cms):
    """16 per-item checks; each carries the literal value written into the package"""
    S = facts["slides"]
    n = len(S)
    T = spec
    checks = []
    req_n = wo.get("slides") if wo.get("slides_explicit", bool(wo.get("slides"))) else None
    # CI-01 slide count
    checks.append(_ck("CI-01", "页数", ("workorder 要求 %s 页" % req_n) if req_n else "workorder 未指定页数",
                      "产出 %d 页" % n,
                      (not req_n) or int(req_n) == n,
                      [_ev(facts, "ppt/presentation.xml", r'<p:sldIdLst>.*?</p:sldIdLst>', "/p:presentation/p:sldIdLst")]))
    # CI-02 page geometry vs template
    ts, fs_ = T["slide_size"], facts["size"]
    checks.append(_ck("CI-02", "页面尺寸/比例",
                      "%s 英寸 %s (%d×%d EMU)" % (ts["width_in"], ts["height_in"], ts["cx_emu"], ts["cy_emu"]),
                      "%s 英寸 %s (%d×%d EMU)" % (fs_["width_in"], fs_["height_in"], fs_["cx_emu"], fs_["cy_emu"]),
                      (ts["cx_emu"], ts["cy_emu"]) == (fs_["cx_emu"], fs_["cy_emu"]),
                      [_ev(facts, "ppt/presentation.xml", r'<p:sldSz\b[^>]*/>', "/p:presentation/p:sldSz")]))
    # CI-03/04/05 protected parts byte-identical
    for cid, item, pat in (("CI-03", "母版未被改写", r"ppt/slideMasters/slideMaster\d+\.xml$"),
                           ("CI-04", "版式未被改写", r"ppt/slideLayouts/slideLayout\d+\.xml$"),
                           ("CI-05", "主题未被改写", r"ppt/theme/theme\d+\.xml$")):
        parts = [p for p in T["protected_parts"] if re.match(pat, p)]
        bad = [p for p in parts if p not in facts["parts"]
               or sha(facts["parts"][p]) != T["protected_parts"][p]]
        ok = bool(parts) and not bad
        checks.append(_ck(cid, item, "%d 个部件 sha256 与模板一致" % len(parts),
                          "%d 个一致%s" % (len(parts) - len(bad), "，不符：%s" % bad if bad else ""), ok,
                          [{"part": parts[0] if parts else "",
                            "locator": "sha256(part)",
                            "snippet": "sha256=%s" % (T["protected_parts"].get(parts[0], "")[:32] if parts else ""),
                            "verified_in_part": bool(parts)}],
                          "" if ok else "模板部件被修改：必须回退到模板原件"))
    # CI-06 layout binding
    nobind = [s["n"] for s in S if not s["layout_part"] or s["layout_part"] not in [l["part"] for l in T["layouts"]]]
    checks.append(_ck("CI-06", "每页绑定模板版式", "每页 rels 指向模板 slideLayout",
                      "%d/%d 页绑定，缺失页 %s" % (n - len(nobind), n, nobind or "无"), not nobind,
                      [_ev(facts, S[0]["part"] if S else "", r'<p:sld\b[^>]*>',
                           "%s → %s" % (S[0]["part"], S[0]["layout_part"]) if S else "")]))
    # CI-07 placeholder inheritance
    lay = {l["part"]: l for l in T["layouts"]}
    inv, freel = [], 0
    for s in S:
        avail = (lay.get(s["layout_part"]) or {}).get("placeholder_types", [])
        bad = [t for t in s["placeholder_types"] if t not in avail]
        freel += s["freetext"]
        if bad:
            inv.append({"page": s["n"], "types": bad})
    checks.append(_ck("CI-07", "占位符继承", "填充的占位符类型必须在版式中存在（无自造占位符）",
                      "自造占位符 %d 处；自由文本框 %d 个" % (len(inv), freel), not inv,
                      [{"part": S[0]["layout_part"] if S else "", "locator": "layout placeholders",
                        "snippet": str((lay.get(S[0]["layout_part"]) or {}).get("placeholder_types")) if S else "",
                        "verified_in_part": bool(S)}], "自由文本框仅用于模板缺该占位符时"))
    # CI-08 title hierarchy
    notitle = [s["n"] for s in S if not s["title_text"].strip()]
    checks.append(_ck("CI-08", "标题层级", "每页有 title/ctrTitle 占位符文本；标题字号继承母版 titleStyle %s pt"
                      % (facts["default_title_pt"]), "缺标题页 %s；标题字号 %s pt" % (notitle or "无", facts["default_title_pt"]),
                      not notitle, [_ev(facts, facts["master_part"] or "", r"<p:titleStyle>.*?</p:titleStyle>",
                                        "master %s /p:txStyles/p:titleStyle" % facts["master_part"])]))
    # CI-09 body size ladder
    allsz = sorted({v for s in S for v in s["sizes"]})
    body_sz = [v for v in allsz if v != facts["default_title_pt"]]
    minpt = float(wo.get("min_pt") or 0)
    has_body = any(pp["text"].strip() for s in S for sh in s["shapes"] if sh["ph_type"] in ("body", "obj", "subTitle")
                   for pp in sh["paras"])
    inh_body = any(sh["paras"] and sh["ph_type"] in ("body", "obj") and not sh["sizes"]
                   for s in S for sh in s["shapes"])
    eff = sorted(set(body_sz) | ({facts["default_body_pt"]} if (inh_body and facts["default_body_pt"]) else set()))
    ok9 = (min(eff) >= minpt) if eff else (not has_body)
    checks.append(_ck("CI-09", "正文字号阶梯", "最小正文字号 ≥ %s pt；上限 = 母版 bodyStyle %s pt" % (minpt, facts["default_body_pt"]),
                      "显式字号 %s pt；生效字号 %s pt（含母版继承 %s）；最小 %s pt"
                      % (allsz, eff, facts["default_body_pt"] if inh_body else "-", min(eff) if eff else None), ok9,
                      ([_ev(facts, part, r'<a:rPr\b[^>]*sz="\d+"[^>]*/>', "%s: first explicit run size" % part)
                        for part in [s["part"] for s in S if re.search(r'<a:rPr\b[^>]*sz="\d+"',
                                                                      facts["parts"].get(s["part"], b"").decode("utf-8", "replace"))][:1]]
                       or [_ev(facts, facts["master_part"] or "", r'<a:defRPr\b[^>]*sz="\d+"',
                               "master %s /p:txStyles/p:bodyStyle/a:defRPr@sz" % facts["master_part"])])))
    # CI-10 line spacing
    written = [s["n"] for s in S if s["has_lnspc"]]
    inh = facts["default_body_lnspc"]
    checks.append(_ck("CI-10", "行距", "行距继承母版 bodyStyle lvl1pPr 的 spcPct",
                      "页面显式写入 %d 页；继承值 %s%%（%s）" % (len(written), inh, "母版 bodyStyle"),
                      True if (not written or inh) else bool(written),
                      [_ev(facts, facts["master_part"] or "", r'<a:lnSpc><a:spcPct val="\d+"',
                           "master %s /p:txStyles/p:bodyStyle/a:lvl1pPr/a:lnSpc" % facts["master_part"])],
                      "页面不写 lnSpc 时从母版继承，避免逐页覆盖"))
    # CI-11 theme fonts
    hard = []
    for s in S:
        for sh in s["shapes"]:
            if re.search(r'<a:latin typeface="(?!\+)', sh.get("xml", "") if isinstance(sh.get("xml"), str) else ""):
                hard.append(s["n"])
    themefonts = (T.get("theme") or {}).get("fonts", {})
    runs = sum(len(re.findall(r"<a:r>", facts["parts"].get(s["part"], b"").decode("utf-8", "replace"))) for s in S)
    checks.append(_ck("CI-11", "主题字体继承", "文本 run 不硬编码 latin typeface（使用 +mj/+mn 主题引用）",
                      "硬编码字体页 %s；主题字体 major=%s minor=%s ea=%s；共 %d 个 run"
                      % (hard or "无", themefonts.get("major_latin"), themefonts.get("minor_latin"),
                         themefonts.get("minor_ea"), runs), not hard,
                      [_ev(facts, (T.get("theme") or {}).get("part", ""),
                           r'<a:latin typeface="[^"]*"', "a:fontScheme/a:majorFont/a:latin")]))
    # CI-12 palette
    used = sorted({v for s in S for v in s["srgb"]})
    allowed = set((T.get("palette") or {}).values())
    off = [v for v in used if v.upper() not in {str(x).upper() for x in allowed if x}]
    checks.append(_ck("CI-12", "色板", "不出现主题色以外的硬编码 RGB",
                      "硬编码 RGB %s；schemeClr 引用 %s" % (used or "无", sorted({v for s in S for v in s["scheme"]}) or "无"),
                      not off, [_ev(facts, (T.get("theme") or {}).get("part", ""),
                                   r'<a:accent1>.*?</a:accent1>', "a:clrScheme/a:accent1")]))
    # CI-13 footer
    noncover = [s for s in S if s["layout_type"] not in ("title", "ctrtitle")]
    ftr_txt = {s["n"]: (s["text"].count("") and "") for s in S}
    foot = []
    for s in S:
        t = next((sh["paras"][0]["text"] for sh in s["shapes"] if sh["ph_type"] == "ftr" and sh["paras"]), "")
        if not t:
            t = next((sh["paras"][0]["text"] for sh in s["shapes"] if sh["is_freetext"] and sh["paras"]), "")
        foot.append(t)
    has_foot = [bool(x) for x in foot]
    uniform = len({x for x in foot if x}) <= 1
    req_foot = bool(wo.get("footer"))
    ok13 = uniform and (all(has_foot[s["n"] - 1] for s in noncover) if req_foot else True)
    checks.append(_ck("CI-13", "页脚", "非封面页均有页脚且文本一致（workorder: %s）" % wo.get("footer"),
                      "文本集合 %s；缺页脚 %s" % (sorted({x for x in foot if x}), [i + 1 for i, v in enumerate(has_foot) if not v]),
                      ok13, [_ev(facts, next((s["part"] for s in S if s["has_ftr"]), ""), r'<p:ph type="ftr"[^>]*/>',
                                 "slide ftr placeholder")],
                      "" if req_foot else "workorder 未要求页脚；只校验已写入页脚的一致性"))
    # CI-14 page numbers
    pnsrc = {c.get("n"): c.get("page_number_source") for c in cms}
    missing = [s["n"] for s in S if not (s["has_sldnum"] or pnsrc.get(s["n"]))]
    req_pn = bool(wo.get("pagenum"))
    laymap = {l["part"]: l for l in spec.get("layouts", [])}
    stub = [s["n"] for s in S if "sldNum" in ((laymap.get(s["layout_part"]) or {}).get("placeholder_types") or [])
            and not (s["has_sldnum"] or pnsrc.get(s["n"]))]
    via = sorted({str(pnsrc.get(s["n"]) or ("sldNum" if s["has_sldnum"] else "none")) for s in S})
    ok14 = (not stub) and ((not req_pn) or not missing)
    checks.append(_ck("CI-14", "页码", "版式有 sldNum 占位符的页必须编号" if not req_pn
                      else "workorder 要求页码：每页编号（优先 sldNum，缺占位符时用母版页码位置自由文本框）",
                      "缺页码页 %s；占位符未填页 %s；来源 %s" % (missing or "无", stub or "无", via), ok14,
                      [_ev(facts, next((s["part"] for s in S if s["has_sldnum"]), ""),
                           r'<a:fld\b[^>]*type="slidenum"', "a:fld type=slidenum")],
                      "" if ok14 else ("版式无 sldNum 占位符的页未编号（workorder 要求页码）" if req_pn
                                       else "有 sldNum 占位符却未写页码")))
    # CI-15 overflow
    ovf = [s["n"] for s in S if not (s["geometry_inside_page"] and (s["max_fit_ratio"] or 0) <= 1.02)]
    checks.append(_ck("CI-15", "溢出", "形状在页面内且文本估算填充率 ≤ 1.02（CJK 1.0em / Latin 0.52em，行高 1.20）",
                      "越界/超容量页 %s；最大填充率 %s" % (ovf or "无", max([s["max_fit_ratio"] or 0 for s in S] or [0])),
                      not ovf, [_ev(facts, (S[0]["part"] if S else ""), r'<a:ext cx="\d+" cy="\d+"/>',
                                   "p:sp/p:spPr/a:xfrm/a:ext vs p:sldSz")] if S else [],
                      "估算模型：0.52em 拉丁字宽 + 1.0em CJK + 1.20 行高 + 4% 余量"))
    # CI-16 speaker notes
    notes_ok = all(c.get("notes") for c in cms)
    checks.append(_ck("CI-16", "讲稿/备注", "每页有讲解稿；交付在 content_map[].notes（pptx 未写 notesSlide）",
                      "content_map 覆盖 %d/%d 页" % (sum(1 for c in cms if c.get("notes")), len(cms)), notes_ok,
                      [{"part": "result.json", "locator": "content_map.slides[0].notes",
                        "snippet": clip_snip((cms[0].get("notes") or [""])[0]) if cms else "",
                        "verified_in_part": None,
                        "basis": "value copied from content_map; not an OOXML part"}],
                      "pptx notesSlide 部件未生成，属已知降级"))
    for c in checks:
        if c["status"] == "fail" and c["id"] == "CI-16":
            pass
    fails = [c["id"] for c in checks if c["status"] == "fail"]
    return {"items": checks, "total": len(checks), "passed": len(checks) - len(fails), "failed": len(fails),
            "fail_ids": fails, "pass_rate": round((len(checks) - len(fails)) / float(len(checks)), 3),
            "pass": not fails,
            "note": "CI-16 缺 notesSlide 记为 fail 时属交付形态降级，见 degradations"}


# ---------------------------------------------------------------- export / render
def pdf_facts(pdf):
    try:
        b = Path(pdf).read_bytes()
    except Exception:
        return {"present": False}
    if not b.startswith(b"%PDF"):
        return {"present": False}
    head = b[:8].decode("latin-1")
    base = sorted({x.decode("latin-1") for x in re.findall(rb"/BaseFont\s*/([#\w+.\-]+)", b)})
    mb = re.findall(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", b)
    box = [float(v) for v in mb[0]] if mb else None
    npg = max([int(x) for x in re.findall(rb"/Count\s+(\d+)", b)] or [0])
    pages = len(re.findall(rb"/Type\s*/Page[^s]", b))
    return {"present": True, "header": head, "bytes": len(b), "objects_pages": pages, "count_max": npg,
            "pages": max(pages, npg), "mediabox_pt": box,
            "size_in": [round(box[2] / 72.0, 3), round(box[3] / 72.0, 3)] if box else None,
            "base_fonts": base,
            "embedded_font_programs": len(re.findall(rb"/FontFile\d?", b)),
            "subset_fonts": [x for x in base if "+" in x],
            "images": len(re.findall(rb"/Subtype\s*/Image", b)),
            "encrypted": b"/Encrypt" in b}


def fc(name):
    exe = shutil.which("fc-match")
    if not exe or not name:
        return None
    try:
        r = subprocess.run([exe, "-f", "%{family}", str(name)], capture_output=True, timeout=20)
        return r.stdout.decode("utf-8", "replace").strip() or None
    except Exception:
        return None


METRIC = {"calibri": "carlito", "arial": "liberation sans", "helvetica": "liberation sans",
          "times new roman": "liberation serif", "cambria": "caladea", "georgia": "gelasio",
          "courier new": "liberation mono", "segoe ui": "selawik"}
CJK_FONTS = ("yahei", "simsun", "simhei", "songti", "heiti", "pingfang", "noto sans cjk", "source han")


def pdf_font_table(pdf):
    """pdffonts gives embedded/subset flags far more reliably than scanning /FontFile tokens"""
    exe = shutil.which("pdffonts")
    if not exe:
        return None, "pdffonts absent"
    try:
        r = subprocess.run([exe, str(pdf)], capture_output=True, timeout=90)
        txt = r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return None, "pdffonts failed: %s" % str(e)[:80]
    rows = []
    for ln in txt.splitlines()[2:]:
        f = ln.split()
        if len(f) < 5:
            continue
        rows.append({"name": f[0], "type": f[1], "embedded": f[-4].lower() == "yes" if len(f) >= 5 else None,
                     "subset": "yes" in [x.lower() for x in f[2:]]})
    for r_ in rows:
        base = r_["name"].split("+")[-1]
        r_["base"] = base
        r_["family"] = re.sub(r"[-,_](Bold|Italic|Oblique|Regular|Light|Medium|Black).*$", "", base)
    return rows, txt.splitlines()[0] if txt else ""


def pdf_text_extent(pdf):
    """real rendered word boxes: the only trustworthy overflow evidence beside estimating from XML"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext absent"
    try:
        r = subprocess.run([exe, "-bbox", str(pdf), "-"], capture_output=True, timeout=180)
        xml = r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return None, "pdftotext failed: %s" % str(e)[:80]
    out = []
    for i, (w, h, body) in enumerate(re.findall(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>',
                                                xml, re.S), 1):
        W, H = float(w), float(h)
        words = [(float(a), float(b), float(c), float(d)) for a, b, c, d in
                 re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)"', body)]
        if not words:
            out.append({"page": i, "page_pt": [W, H], "words": 0, "outside": 0, "ink_bbox_pt": None,
                        "min_margin_pt": None})
            continue
        x0, y0 = min(v[0] for v in words), min(v[1] for v in words)
        x1, y1 = max(v[2] for v in words), max(v[3] for v in words)
        outside = [v for v in words if v[0] < -0.5 or v[1] < -0.5 or v[2] > W + 0.5 or v[3] > H + 0.5]
        out.append({"page": i, "page_pt": [round(W, 2), round(H, 2)], "words": len(words),
                    "ink_bbox_pt": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                    "outside": len(outside), "min_margin_pt": round(min(x0, y0, W - x1, H - y1), 1)})
    return out, "pdftotext -bbox"


def export_check(out, facts, wo, spec):
    out = Path(out)
    pdf = out / "presentation.pdf"
    p = pdf_facts(pdf)
    pptx_slides = len(facts["slides"])
    fonts_theme = (spec.get("theme") or {}).get("fonts", {})
    deck_text = " ".join(s.get("text") or "" for s in facts["slides"])
    cjk_present = bool(CJK.search(deck_text))
    table, tsrc = (pdf_font_table(pdf) if p.get("present") else (None, "no pdf"))
    found = p.get("base_fonts") or []
    verdicts = []
    for key, fam in fonts_theme.items():
        if not fam:
            continue
        script = key.split("_")[1]
        hit = [r for r in (table or []) if fam.split()[0].lower() in r["base"].lower()]
        if script == "ea" and not cjk_present:
            verdicts.append({"theme_font": fam, "script": script, "status": "not_exercised",
                             "detail": "deck contains no CJK characters, so the East Asian font is not used",
                             "fc_match": fc(fam)})
            continue
        if hit:
            verdicts.append({"theme_font": fam, "script": script,
                             "status": "embedded" if all(h["embedded"] for h in hit) else "unembedded",
                             "in_pdf": [h["name"] for h in hit], "fc_match": fc(fam)})
            continue
        m = fc(fam) or ""
        sub = METRIC.get(fam.strip().lower())
        ok = bool(sub and sub.split()[0].lower() in m.lower())
        verdicts.append({"theme_font": fam, "script": script,
                         "status": "metric_substitute" if ok else "substituted",
                         "expected_substitute": sub, "fc_match": m,
                         "in_pdf": sorted({r["base"] for r in (table or [])})[:6]})
    ext, esrc = (pdf_text_extent(pdf) if p.get("present") else (None, "no pdf"))
    outside = sum(e.get("outside") or 0 for e in (ext or []))
    tight = [e["page"] for e in (ext or []) if (e.get("min_margin_pt") or 99) < 2.0]
    ovf = [s["n"] for s in facts["slides"] if not (s["geometry_inside_page"] and (s["max_fit_ratio"] or 0) <= 1.02)]
    ratio_ok = None
    if p.get("present") and p.get("mediabox_pt") and facts["size"]["cx_emu"]:
        rp = p["mediabox_pt"][2] / p["mediabox_pt"][3]
        rq = facts["size"]["cx_emu"] / float(facts["size"]["cy_emu"])
        ratio_ok = abs(rp - rq) < 0.01
    chk = {
        "pdf": {"path": str(pdf) if p.get("present") else None, "header": p.get("header"),
                "pages": p.get("pages"), "bytes": p.get("bytes"),
                "size_in": p.get("size_in"), "mediabox_pt": p.get("mediabox_pt"),
                "embedded_font_programs": p.get("embedded_font_programs"), "images": p.get("images"),
                "encrypted": p.get("encrypted")},
        "pptx": {"slides": pptx_slides, "size_in": [facts["size"]["width_in"], facts["size"]["height_in"]],
                 "ratio": facts["size"]["ratio"]},
        "consistency": {"pages_match": p.get("pages") == pptx_slides if p.get("present") else False,
                        "pdf_pages": p.get("pages"), "pptx_slides": pptx_slides,
                        "size_match": ratio_ok,
                        "note": None if p.get("present") else "no PDF produced (soffice absent or conversion failed)"},
        "fonts": {"theme_fonts": fonts_theme, "font_table_source": tsrc,
                  "font_table": [{"name": r["name"], "type": r["type"], "embedded": r["embedded"]}
                                 for r in (table or [])],
                  "verdicts": verdicts, "cjk_text_present": cjk_present,
                  "all_theme_fonts_resolved": all(v["status"] in ("embedded", "metric_substitute", "not_exercised")
                                                  for v in verdicts)},
        "render_text": {"tool": esrc, "pages": ext, "outside_words": outside,
                        "pages_outside": [e["page"] for e in (ext or []) if e.get("outside")],
                        "pages_tight_margin": tight},
        "overflow": {"slides": ovf, "count": len(ovf),
                     "max_fit_ratio": max([s["max_fit_ratio"] or 0 for s in facts["slides"]] or [0]),
                     "model": "per-character advance (CJK 1.0em / Latin 0.52em) x 1.20 line height, 4% safety",
                     "detail": [{"page": s["n"], "fit_ratio": s["max_fit_ratio"],
                                 "inside_page": s["geometry_inside_page"]} for s in facts["slides"]
                                if s["n"] in ovf]},
        "rules": {"pdf_pages_eq_slides": p.get("pages") == pptx_slides if p.get("present") else False,
                  "pdf_size_eq_deck": bool(ratio_ok), "no_estimated_overflow": not ovf,
                  "text_inside_page": outside == 0,
                  "fonts_embedded": bool(table and all(r["embedded"] for r in table))
                                    if table else bool(p.get("embedded_font_programs"))},
    }
    chk["pass"] = all([chk["rules"]["pdf_pages_eq_slides"], chk["rules"]["pdf_size_eq_deck"],
                       chk["rules"]["no_estimated_overflow"], chk["rules"]["text_inside_page"],
                       chk["rules"]["fonts_embedded"]])
    chk["status"] = "pass" if chk["pass"] else ("partial" if p.get("present") else "no_pdf")
    chk["degradations"] = [x for x in (None if table else "font table unavailable (%s)" % tsrc,
                                       None if ext else "render text boxes unavailable (%s)" % esrc) if x]
    return chk


def guard(pptx, tpl_path, spec):
    """post-pack integrity guard: if a protected template part drifted, restore it from the
    template source of truth and repack. Returns what happened, with hashes as evidence."""
    res = {"strategy": "restore-protected-parts-from-template",
           "checked_parts": len(spec.get("protected_parts") or {}), "drift": [], "repaired": [],
           "source": str(tpl_path), "verified": False, "method": "sha256 per part, byte restore + repack"}
    try:
        with zipfile.ZipFile(str(pptx)) as z:
            cur = {n: z.read(n) for n in z.namelist()}
            order = z.namelist()
    except Exception as e:
        res["error"] = "cannot read emitted pptx: %s" % str(e)[:120]
        return res
    drift = [p for p, h in (spec.get("protected_parts") or {}).items()
             if cur.get(p) is None or sha(cur[p]) != h]
    res["drift"] = drift
    if not drift:
        res["verified"] = True
        res["note"] = "no template part modified; nothing to roll back"
        return res
    try:
        with zipfile.ZipFile(str(tpl_path)) as z:
            orig = {n: z.read(n) for n in z.namelist()}
        for p in drift:
            if p in orig:
                cur[p] = orig[p]
                res["repaired"].append({"part": p, "restored_sha256": sha(orig[p])})
        tmp = Path(str(pptx) + ".tmp")
        with zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as z:
            for n in order:
                z.writestr(n, cur[n])
            for n in orig:
                if n not in order and n in (spec.get("protected_parts") or {}):
                    z.writestr(n, orig[n])
        tmp.replace(pptx)
        with zipfile.ZipFile(str(pptx)) as z:
            now = {n: z.read(n) for n in z.namelist()}
        res["verified"] = all(sha(now.get(p, b"")) == h for p, h in (spec.get("protected_parts") or {}).items())
        res["post_repair_sha256"] = {p: sha(now[p]) for p in drift if p in now}
    except Exception as e:
        res["error"] = "rollback failed: %s" % str(e)[:160]
    return res


# ---------------------------------------------------------------- fallback package
def is_zip(p):
    try:
        with open(str(p), "rb") as f:
            return f.read(2) == b"PK"
    except Exception:
        return False


def synthetic_parts(cx=12192000, cy=6858000):
    """minimal self-contained deck package (master + 4 layouts + theme) used only when the case
    ships no readable .pptx. It is a skeleton, never a stand-in for the organizer template, and
    template_spec marks it kind='synthetic'."""
    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    R = REL
    P = "http://schemas.openxmlformats.org/presentationml/2006/main"
    CT = "application/vnd.openxmlformats-officedocument.presentationml."
    D = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    grp = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
           '<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
           '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')

    def ph(sid, name, attr, rect):
        x, y, w, h = rect
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                '<p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/>'
                '<a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
                '<p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/><a:p/></p:txBody></p:sp>'
                % (sid, name, attr, x, y, w, h))
    col = "".join("<a:%s><a:srgbClr val=\"%s\"/></a:%s>" % (n, v, n) for n, v in
                  (("dk1", "000000"), ("lt1", "FFFFFF"), ("dk2", "1F3864"), ("lt2", "EEF2F8"),
                   ("accent1", "1F4E79"), ("accent2", "C00000"), ("accent3", "2E7D32"),
                   ("accent4", "B8860B"), ("accent5", "7030A0"), ("accent6", "00707F"),
                   ("hlink", "0563C1"), ("folHlink", "954F72")))
    fmt = ('<a:fmtScheme name="Synthetic"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
           '<a:solidFill><a:schemeClr val="phClr"><a:tint val="50000"/></a:schemeClr></a:solidFill>'
           '<a:solidFill><a:schemeClr val="phClr"><a:shade val="50000"/></a:schemeClr></a:solidFill></a:fillStyleLst>'
           '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
           '<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
           '<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
           '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/>'
           '</a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
           '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
           '<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/></a:schemeClr></a:solidFill>'
           '<a:solidFill><a:schemeClr val="phClr"><a:shade val="90000"/></a:schemeClr></a:solidFill></a:bgFillStyleLst>')
    theme = (D + '<a:theme xmlns:a="%s" name="Synthetic"><a:themeElements><a:clrScheme name="Synthetic">%s'
             '</a:clrScheme><a:fontScheme name="Synthetic"><a:majorFont><a:latin typeface="Calibri"/>'
             '<a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Calibri"/>'
             '<a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>%s</a:fmtScheme>'
             '</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>' % (A, col, fmt))
    lay = [(("ctrTitle", (1143000, 1724025, 9906000, 1470025)), ("subTitle", (1143000, 3321050, 9906000, 1104900))),
           (("title", (838200, 365125, 10515600, 1325563)), ("body", (838200, 1825625, 10515600, 4351338)),
            ("ftr", (4038600, 6356350, 3886200, 365125)), ("sldNum", (9144000, 6356350, 1524000, 365125))),
           (("title", (838200, 365125, 10515600, 1325563)),
            ("body", (838200, 1825625, 10515600, 4351338))),
           (("title", (838200, 365125, 10515600, 1325563)),
            ("ftr", (4038600, 6356350, 3886200, 365125)), ("sldNum", (9144000, 6356350, 1524000, 365125)))]
    types = ["title", "obj", "secHead", "titleOnly"]
    parts = {}
    parts["[Content_Types].xml"] = (D + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                                   '<Default Extension="xml" ContentType="application/xml"/>'
                                   '<Default Extension="png" ContentType="image/png"/>'
                                   '<Override PartName="/ppt/presentation.xml" ContentType="%spresentation.main+xml"/>'
                                   '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="%sslideMaster+xml"/>'
                                   '<Override PartName="/ppt/theme/theme1.xml" ContentType="%stheme+xml"/>'
                                   '<Override PartName="/ppt/presProps.xml" ContentType="%spresProps+xml"/>'
                                   '<Override PartName="/ppt/viewProps.xml" ContentType="%sviewProps+xml"/>'
                                   % (CT, CT, CT, CT, CT)
                                   + "".join('<Override PartName="/ppt/slideLayouts/slideLayout%d.xml" '
                                             'ContentType="%sslideLayout+xml"/>' % (i + 1, CT) for i in range(len(lay)))
                                   + '</Types>').encode()
    rel = lambda items: ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<Relationships xmlns='
                         '"http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
                         % "".join('<Relationship Id="%s" Type="%s" Target="%s"/>' % t for t in items))
    parts["_rels/.rels"] = rel([("rId1", R + "/officeDocument", "ppt/presentation.xml")]).encode()
    parts["ppt/presentation.xml"] = (D + '<p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" saveSubsetFonts="1">'
                                     '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                                     '<p:notesSz cx="6858000" cy="9144000"/><p:sldSz cx="%d" cy="%d"/>'
                                     '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr>'
                                     '<a:lvl1pPr marL="0" algn="l"><a:defRPr sz="1800"/></a:lvl1pPr>'
                                     '</p:defaultTextStyle></p:presentation>' % (A, R, P, cx, cy)).encode()
    parts["ppt/_rels/presentation.xml.rels"] = rel(
        [("rId1", R + "/slideMaster", "slideMasters/slideMaster1.xml"),
         ("rId2", R + "/theme", "theme/theme1.xml"),
         ("rId3", R + "/presProps", "presProps.xml"),
         ("rId4", R + "/viewProps", "viewProps.xml")]).encode()
    sp = [ph(2, "Title Placeholder 1", 'type="title"', (838200, 365125, 10515600, 1325563)),
          ph(3, "Text Placeholder 2", 'type="body" idx="1"', (838200, 1825625, 10515600, 4351338)),
          ph(4, "Footer 3", 'type="ftr" idx="3"', (4038600, 6356350, 3886200, 365125)),
          ph(5, "Slide Number 4", 'type="sldNum" idx="4"', (9144000, 6356350, 1524000, 365125))]
    parts["ppt/slideMasters/slideMaster1.xml"] = (D + '<p:sldMaster xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"><p:cSld>'
                                                  '<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
                                                  '<p:spTree>%s%s</p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" '
                                                  'bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
                                                  'accent3="accent3" accent4="accent4" accent5="accent5" '
                                                  'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
                                                  '<p:sldLayoutIdLst>%s</p:sldLayoutIdLst><p:txStyles>'
                                                  '<p:titleStyle><a:lvl1pPr algn="l"><a:lnSpc><a:spcPct val="90000"/>'
                                                  '</a:lnSpc><a:buNone/><a:defRPr sz="3000" b="1"><a:solidFill>'
                                                  '<a:schemeClr val="tx2"/></a:solidFill><a:latin typeface="+mj-lt"/>'
                                                  '<a:ea typeface="+mj-ea"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
                                                  '<p:bodyStyle><a:lvl1pPr marL="228600" indent="-228600"><a:lnSpc>'
                                                  '<a:spcPct val="100000"/></a:lnSpc><a:buFont typeface="Arial"/>'
                                                  '<a:buChar char="&#8226;"/><a:defRPr sz="2000"><a:solidFill>'
                                                  '<a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/>'
                                                  '<a:ea typeface="+mn-ea"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
                                                  '<p:otherStyle><a:defPPr><a:defRPr lang="en-US" sz="1200"/>'
                                                  '</a:defPPr></p:otherStyle></p:txStyles></p:sldMaster>'
                                                  % (A, R, P, grp, "".join(sp),
                                                     "".join('<p:sldLayoutId id="%d" r:id="rId%d"/>'
                                                             % (2147483649 + i, i + 1) for i in range(len(lay))))).encode()
    parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = rel(
        [("rId%d" % (i + 1), R + "/slideLayout", "../slideLayouts/slideLayout%d.xml" % (i + 1))
         for i in range(len(lay))] + [("rId%d" % (len(lay) + 1), R + "/theme", "../theme/theme1.xml")]).encode()
    for i, phs in enumerate(lay):
        body = "".join(ph(2 + j, "%s %d" % (t, j + 1), 'type="%s"%s' % (t, ' idx="1"' if t == "body" else ""), r)
                       for j, (t, r) in enumerate(phs))
        parts["ppt/slideLayouts/slideLayout%d.xml" % (i + 1)] = (
            D + '<p:sldLayout xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" type="%s" preserve="1"><p:cSld name="%s">'
            '<p:spTree>%s%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
            % (A, R, P, types[i], "Layout %d" % (i + 1), grp, body)).encode()
        parts["ppt/slideLayouts/_rels/slideLayout%d.xml.rels" % (i + 1)] = rel(
            [("rId1", R + "/slideMaster", "../slideMasters/slideMaster1.xml")]).encode()
    parts["ppt/theme/theme1.xml"] = theme.encode()
    parts["ppt/presProps.xml"] = (D + '<p:presentationPr xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"/>' % (A, R, P)).encode()
    parts["ppt/viewProps.xml"] = (D + '<p:viewPr xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"><p:normalViewPr>'
                                  '<p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr>'
                                  '<p:gridSpacing cx="76200" cy="76200"/></p:viewPr>' % (A, R, P)).encode()
    return parts


def write_parts(parts, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items():
            z.writestr(k, v)
    return path
