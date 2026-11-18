#!/usr/bin/env python3
"""slides-04 v2: fit paper content into a real .pptx template and emit an auditable deck.

Pages are bound to existing slideLayouts and write real placeholders, so geometry, theme
fonts and bullet levels inherit from the master; master/layout/theme parts stay byte-identical
and are re-hashed after packing (restored from the template if they drift).
stdlib only; exit code always 0 and result.json is written partial first, finalized last.

v2 additions (patch over v1, original CLI unchanged): template_spec.json, format_compliance.json,
page_diff.md, version_history.md, run.log, export_check.json, protected-part rollback.
"""
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time, traceback, zipfile
from pathlib import Path

H = Path(__file__).resolve().parent
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CTB = "application/vnd.openxmlformats-officedocument.presentationml."
MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "bmp": "image/bmp", "gif": "image/gif"}
HDR = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<Relationships xmlns='
       '"http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>')
T0 = time.time()
sha = lambda b: hashlib.sha256(b).hexdigest()


def _load(name, fname):
  """sibling module by path: no sys.path / CWD assumptions"""
  s = importlib.util.spec_from_file_location(name, H / fname)
  m = importlib.util.module_from_spec(s)
  s.loader.exec_module(m)
  return m


V = _load("_sl04v", "verify.py")
SP = _load("_sl04s", "spec.py")
RP = _load("_sl04r", "reports.py")
LOG = RP.Log(Path(os.environ.get("OUTPUT_DIR", "/app/output")) / "run.log")


def log(stage, msg, level="INFO"):
  """never let logging break the pipeline"""
  try:
    LOG(stage, msg, level)
  except Exception:
    pass


def clip(s, n=200):
  s = " ".join(str(s).split())
  return s if len(s) <= n else s[:n - 1] + "\u2026"


def rj(p):
  try:
    return json.loads(Path(p).read_text("utf-8", "replace"))
  except Exception:
    return None


def wj(p, o):
  p = Path(p)
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(o, ensure_ascii=False, indent=2), "utf-8")


def nk(k):
  return re.sub(r"[^a-z0-9]", "", str(k).lower())


def dfind(o, names, d=None, dep=0):
  """semantic key lookup: normalised names at any depth, no key names assumed"""
  if dep > 7 or o is None:
    return d
  names = {nk(n) for n in names} if dep == 0 else names
  if isinstance(o, dict):
    for k, v in o.items():
      if nk(k) in names and v not in (None, "", [], {}):
        return v
    pool = list(o.values())
  elif isinstance(o, list):
    pool = o
  else:
    return d
  for v in pool:
    r = dfind(v, names, None, dep + 1)
    if r not in (None, "", [], {}):
      return r
  return d


def discover(inp, a):
  """template / starting deck / paper / figures / workorders, by name then by content"""
  inp = Path(inp)
  d = {"template": None, "deck": None, "paper": None, "workorders": [], "figures": [], "docs": [],
       "case": None, "case_path": None}
  cp = inp / "case.json"
  if not cp.exists() and inp.exists():
    c = sorted(inp.glob("**/case*.json"))
    cp = c[0] if c else None
  if cp and cp.exists():
    d["case"], d["case_path"] = rj(cp), str(cp)
  pptx = []
  for f in (Path(x) for x in sorted(str(y) for y in (inp.rglob("*") if inp.exists() else []))):
    e = f.suffix.lower()
    if e in (".pptx", ".potx"):
      pptx.append(f)
    elif e in (".md", ".markdown", ".txt", ".docx", ".pdf", ".tex"):
      d["docs"].append(f)
    elif e in (".png", ".jpg", ".jpeg", ".bmp", ".gif") and "logo" not in f.name.lower():
      d["figures"].append(f)
    elif e == ".json" and f.name.lower() != "case.json":
      o = rj(f)
      if isinstance(o, dict) and dfind(o, ["mode", "slidecount", "totalslidecount", "totalslides"]) is not None:
        d["workorders"].append((str(f), o))
  tgt = Path(a.template) if a.template else None
  if tgt is None and pptx:
    g = [c for c in pptx if re.search(r"template|master|layout|theme|brand|style", c.name.lower())]
    tgt = (g or pptx)[0]
  if tgt is not None and not Path(tgt).exists():
    tgt = pptx[0] if pptx else None
  d["template"] = tgt
  c = [x for x in pptx if re.search(r"start|deck|draft|current|original|source", x.name.lower())]
  d["deck"] = Path(a.deck) if a.deck else (c[0] if c else tgt)
  if d["deck"] is not None and not Path(d["deck"]).exists():
    d["deck"] = tgt
  order = {".md": 0, ".markdown": 0, ".txt": 1, ".docx": 2, ".pdf": 3, ".tex": 4}
  d["docs"].sort(key=lambda p: (order.get(p.suffix.lower(), 9), -(p.stat().st_size if p.exists() else 0)))
  d["paper"] = d["docs"][0] if d["docs"] else None
  return d


def wo_parse(d, txt):
  """echo the frozen items: mode / slide count / source preservation / template inheritance"""
  src = ([d["case"]] if d["case"] else []) + [o for _, o in d["workorders"]]
  g = lambda n, x=None: dfind(src, n, x)
  raw_slides = g(["totalslidecount", "slidecount", "totalslides"])
  w = {"slides_explicit": raw_slides not in (None, "", [], {}),
       "mode": g(["mode", "requestedmode", "taskmode"], "create"),
       "slides": g(["totalslidecount", "slidecount", "totalslides"]),
       "source_preservation": g(["sourcepreservation", "preserveallsource", "fullsource"]),
       "template_inheritance": g(["templateinheritance", "inheritmaster"]),
       "footer": g(["footertext", "footer"]), "pagenum": g(["pagenumberrequired", "shownumber"]),
       "min_pt": g(["minfontpt", "minfontsize"]), "audience": g(["audience", "targetaudience"])}
  if not isinstance(w["slides"], (int, float)):
    try:
      w["slides"] = int(re.sub(r"[^0-9]", "", str(w["slides"] or ""))) or None
    except Exception:
      w["slides"] = None
  if not w["slides"]:
    m = re.search(r"(\d{1,2})\s*(?:-|\u2013|to)?\s*(?:slides?|pages?|\u9875)", txt or "", re.I)
    w["slides"] = int(m.group(1)) if m else 10
  w["mode"] = str(w["mode"] or "create").lower()
  try:
    w["min_pt"] = float(w["min_pt"] or 12)
  except Exception:
    w["min_pt"] = 12.0
  return w


def doc_title(d, txt):
  """deck title: case metadata first, else the first heading-like line of the paper"""
  t = dfind(d["case"] or {}, ["title", "papertitle", "documenttitle", "casename"])
  if not t:
    for l in txt.splitlines():
      l = l.strip().lstrip("#").strip()
      if 15 <= len(l) <= 140 and not re.fullmatch(r"[\d\W]+", l):
        return clip(l, 110)
  return clip(t or (Path(d["paper"]).stem if d["paper"] else "Academic Report"), 110)


def ph_blocks(xml):
  """<p:sp> placeholder blocks -> type/idx/rect, straight from the part XML"""
  out = []
  for m in re.finditer(r"<p:sp>.*?</p:sp>", xml, re.S):
    blk = m.group(0)
    ph = re.search(r"<p:ph\b([^>/]*)/>", blk)
    if not ph:
      continue
    ty = re.search(r'type="([^"]+)"', ph.group(1))
    ix = re.search(r'idx="([^"]+)"', ph.group(1))
    off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"', blk)
    ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', blk)
    rect = (int(off.group(1)), int(off.group(2)), int(off.group(1)) + int(ext.group(1)),
            int(off.group(2)) + int(ext.group(2))) if off and ext else None
    out.append({"type": ty.group(1) if ty else "body", "idx": ix.group(1) if ix else "0",
                "name": "", "rect": rect})
  return out


def scan(parts):
  """read-only template anatomy: slide size, masters, layouts+placeholders, theme fonts"""
  nm = list(parts)
  inv = {"size": (12192000, 6858000), "layouts": [], "master_sha256": {}, "theme_sha256": {},
         "theme": {}, "body_sz": 18.0, "slide_parts": [], "parse_notes": []}
  pres = parts["ppt/presentation.xml"].decode("utf-8", "replace")
  m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', pres)
  if m:
    inv["size"] = (int(m.group(1)), int(m.group(2)))
  mph = {}
  for mp in sorted(x for x in nm if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", x)):
    inv["master_sha256"][mp] = sha(parts[mp])
    t = parts[mp].decode("utf-8", "replace")
    for q in ph_blocks(t):
      mph.setdefault((q["type"], q["idx"]), q["rect"])
    m2 = re.search(r'<p:bodyStyle>.*?<a:defRPr sz="(\d+)"', t, re.S)
    if m2:
      inv["body_sz"] = int(m2.group(1)) / 100.0
  inv["master_phs"] = [{"type": k[0], "idx": k[1], "rect": v} for k, v in mph.items() if v]
  for lp in sorted(x for x in nm if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", x)):
    t = parts[lp].decode("utf-8", "replace")
    cs = re.search(r'<p:cSld(?:\s+name="([^"]*)")?', t)
    ty = re.search(r'<p:sldLayout\b[^>]*type="([^"]*)"', t)
    phs = ph_blocks(t)
    for q in phs:
      if q["rect"] is None:
        q["rect"] = mph.get((q["type"], q["idx"])) or mph.get((q["type"], "0"))
    inv["layouts"].append({"part": lp, "name": (cs.group(1) if cs and cs.group(1) else lp),
                           "type": (ty.group(1) if ty else "").lower(), "phs": phs,
                           "has": {q["type"] for q in phs}})
  for tp in sorted(x for x in nm if re.match(r"ppt/theme/theme\d+\.xml$", x)):
    if inv["theme"]:
      break
    inv["theme_sha256"][tp] = sha(parts[tp])
    th = SP.parse_theme(tp, parts[tp].decode("utf-8", "replace"))
    f = th["fonts"]
    inv["theme"] = {"part": tp, "major_latin": f.get("major_latin", ""), "minor_latin": f.get("minor_latin", ""),
                    "major_ea": f.get("major_ea", ""), "minor_ea": f.get("minor_ea", ""),
                    "major_cs": f.get("major_cs", ""), "minor_cs": f.get("minor_cs", ""),
                    "palette_size": len(th.get("color_scheme") or {}), "name": th.get("name")}
  rid2t = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"',
                          parts["ppt/_rels/presentation.xml.rels"].decode("utf-8", "replace")))
  for m2 in re.finditer(r'<p:sldId [^>]*r:id="([^"]+)"', pres):
    t = rid2t.get(m2.group(1), "").lstrip("/")
    if t:
      inv["slide_parts"].append(t if t.startswith("ppt/") else "ppt/" + t.replace("../", ""))
  return inv


def pick_layout(inv, role):
  """role -> best existing layout by placeholder composition (never invents one)"""
  best, bs = None, -1
  for l in inv["layouts"]:
    t, h = l["type"], l["has"]
    if role == "title":
      s = 90 if "ctrTitle" in h else (70 if t in ("title", "ctrtitle") else (45 if "title" in h else -1))
    elif role == "section":
      s = 92 if t in ("sechead", "sectionheader") else (60 if ("title" in h and h & {"body", "obj"}) else 30)
    elif role == "picture":
      s = 95 if "pic" in h else (72 if (t.startswith("pic") or ("title" in h and h & {"obj", "body"})) else -1)
    else:
      s = 82 if ("title" in h and h & {"body", "obj", "subTitle"}) else (40 if "title" in h else -1)
      s -= 20 if t in ("twoobj", "twobj") else 0
    if s > bs:
      best, bs = l, s
  if best is None:
    best = next((l for l in inv["layouts"] if l["has"] & {"title", "ctrTitle"}),
                inv["layouts"][0] if inv["layouts"] else None)
  return best


def band(inv, g0=0.22, g1=0.86):
  W, Hh = inv["size"]
  return (int(W * 0.08), int(Hh * g0), int(W * 0.92), int(Hh * g1))


def render(sp, lay, inv, wo, i, footer):
  """page -> (slide xml, meta). A size is written only when the ladder shrinks below the
  template nominal; filled placeholders and every fallback are recorded per page."""
  phs = (lay or {}).get("phs") or []
  g = lambda *t: next((q for q in phs if q["type"] in t), None)
  pt, pb, ps, pp, pf, pn = (g("ctrTitle", "title"), g("body", "obj"), g("subTitle"),
                            g("pic"), g("ftr"), g("sldNum"))
  sh, fill, media, sid, ft, fsrc = [], [], [], 2, 0, None

  def add(x, ph=None):
    nonlocal sid
    sh.append(x)
    sid += 1
    if ph:
      fill.append({"type": ph["type"], "idx": ph["idx"], "name": ph["name"]})

  def note(t):
    sp["deviation"] = (sp["deviation"] + "; " if sp["deviation"] else "") + t

  if sp["title"] and pt:
    add(V.sp(sid, pt, V.body_xml([sp["title"]], None, False)), pt)
  if sp["sub"] and ps:
    add(V.sp(sid, ps, V.body_xml([sp["sub"]], None, False)), ps)
  bpt, ov, it = None, False, list(sp["bullets"])
  if it and pb:
    sz, cut, ov = V.fit(it, pb["rect"], wo["min_pt"], inv["body_sz"])
    bpt = sz
    trimmed = sum(1 for a, b in zip(it, cut) if a != b)
    if trimmed:
      note("text_trimmed_to_fit:%d" % trimmed)
    add(V.sp(sid, pb, V.body_xml(cut, sz if sz < inv["body_sz"] else None, True)), pb)
  elif it:
    note("body_placeholder_absent")
  if sp["fig"]:
    try:
      data = Path(sp["fig"]).read_bytes()
    except Exception:
      data = b""
    rect = (pp or {}).get("rect") or band(inv, g1=0.72)
    if data:
      ext = Path(sp["fig"]).suffix.lower().lstrip(".").replace("jpeg", "jpg")
      add(V.pic(sid, V.fit_rect(rect, *(V.img_dims(data) or (16, 9))), "rId2", pp, Path(sp["fig"]).name))
      media.append(("fig%d.%s" % (i, ext if ext in MIME else "png"), data))
    else:
      note("figure_unreadable")
  if footer and pf:
    add(V.sp(sid, pf, V.body_xml([footer])), pf)
    fsrc = "ftr_placeholder"
  elif footer:
    W, Hh = inv["size"]
    add(V.tb(sid, (int(W * .08), int(Hh * .875), int(W * .92), int(Hh * .965)), V.body_xml([footer])))
    ft, fsrc = 1, "freetext"
    note("footer_placeholder_absent")
  pnsrc = None
  if pn:
    add(V.sp(sid, pn, V.pnum_p(i)), pn)
    pnsrc = "sldNum"
  elif wo.get("pagenum"):
    W, Hh = inv["size"]
    q = next((x for x in inv.get("master_phs") or [] if x.get("type") == "sldNum"), None)
    rect = (q or {}).get("rect") or (int(W * .75), int(Hh * .875), int(W * .92), int(Hh * .965))
    add(V.tb(sid, rect, V.pnum_p(i)))
    ft += 1
    pnsrc = "freetext"
    note("page_number_freetext_layout_without_sldnum")
  return V.sld_xml("".join(sh)), {"filled": fill, "freetext": ft, "overflow": ov, "body_pt": bpt,
                                  "footer": footer if fsrc else None, "footer_source": fsrc,
                                  "page_number_text": str(i) if pnsrc else None,
                                  "page_number_source": pnsrc, "media": media}


def rp(part):
  d, n = part.rsplit("/", 1)
  return "%s/_rels/%s.rels" % (d, n)


def rels_doc(items):
  return HDR % "".join('<Relationship Id="%s" Type="%s" Target="%s"/>' % t for t in items)


def ct_add(x, part, ct):
  return x if 'PartName="/%s"' % part in x else x.replace(
    "</Types>", '<Override PartName="/%s" ContentType="%s"/></Types>' % (part, ct))


def ct_default(x, ext):
  ext = ext.lower()
  if ext not in MIME or 'Extension="%s"' % ext in x:
    return x
  return x.replace("</Types>", '<Default Extension="%s" ContentType="%s"/></Types>' % (ext, MIME[ext]))


def set_ids(x, inner):
  if re.search(r"<p:sldIdLst\s*/>|<p:sldIdLst>.*?</p:sldIdLst>", x, re.S):
    return re.sub(r"<p:sldIdLst\s*/>|<p:sldIdLst>.*?</p:sldIdLst>",
                  lambda m: "<p:sldIdLst>%s</p:sldIdLst>" % inner, x, count=1, flags=re.S)
  return x.replace("</p:presentation>", "<p:sldIdLst>%s</p:sldIdLst></p:presentation>" % inner)


def pack(parts, path):
  with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
    for n, b in parts.items():
      z.writestr(n, b)


def strip_slides(parts):
  """drop the template's own sample slides; masters/layouts/theme stay byte-identical"""
  pres = parts["ppt/presentation.xml"].decode("utf-8", "replace")
  rpp = "ppt/_rels/presentation.xml.rels"
  rels = parts[rpp].decode("utf-8", "replace")
  rid2t = dict(re.findall(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
  drop = set()
  for m in re.finditer(r'<p:sldId [^>]*r:id="([^"]+)"', pres):
    t = rid2t.get(m.group(1), "")
    if t:
      drop.update([q := "ppt/" + t.lstrip("/").replace("../", ""), rp(q)])
  for q in drop:
    parts.pop(q, None)
  ct = parts["[Content_Types].xml"].decode("utf-8", "replace")
  for q in drop:
    ct = re.sub(r'<Override PartName="/%s"[^>]*/>' % re.escape(q), "", ct)
  parts["[Content_Types].xml"] = ct.encode()
  keep = [m.group(0) for m in re.finditer(r"<Relationship\b[^>]*/>", rels)
          if not re.search(r'Type="[^"]*/slide"', m.group(0))]
  parts[rpp] = (HDR % "".join(keep)).encode()
  parts["ppt/presentation.xml"] = set_ids(pres, "").encode()


def build_slides(parts, inv, pages, wo, footer):
  """one slide part per page, each carrying a slideLayout relationship to the template"""
  ct = parts["[Content_Types].xml"].decode("utf-8", "replace")
  rpp = "ppt/_rels/presentation.xml.rels"
  n = max([int(re.findall(r"\d+", q)[-1]) for q in parts if re.match(r"ppt/slides/slide\d+\.xml$", q)] or [0])
  used = {int(x) for x in re.findall(r'Id="rId(\d+)"', parts[rpp].decode("utf-8", "replace"))}
  cms, metas, ids, prel = [], [], [], []
  for s in pages:
    lay = pick_layout(inv, s["role"])
    s["layout"] = lay["part"] if lay else None
    xml, m = render(s, lay, inv, wo, s["n"], footer)
    metas.append(m)
    n += 1
    sn = "ppt/slides/slide%d.xml" % n
    parts[sn] = xml.encode()
    rel = [("rId1", NS_R + "/slideLayout", "../slideLayouts/" + Path(lay["part"]).name)] if lay else []
    for j, (fn, data) in enumerate(m["media"], 2):
      parts["ppt/media/" + fn] = data
      rel.append(("rId%d" % j, NS_R + "/image", "../media/" + fn))
      ct = ct_default(ct, fn.rsplit(".", 1)[-1])
    parts[rp(sn)] = rels_doc(rel).encode()
    ct = ct_add(ct, sn, CTB + "slide+xml")
    rid = "rId%d" % (max(used) + 1)
    used.add(int(rid[3:]))
    ids.append('<p:sldId id="%d" r:id="%s"/>' % (256 + len(ids), rid))
    prel.append((rid, NS_R + "/slide", "slides/slide%d.xml" % n))
    cms.append({"n": s["n"], "role": s["role"], "layout_id": s["layout"],
                "layout_name": (lay or {}).get("name"), "placeholders_filled": m["filled"],
                "claim": clip(s["claim"], 220), "evidence": s["evidence"],
                "freetextbox_count": m["freetext"], "deviation": s["deviation"],
                "body_pt": m["body_pt"], "overflow": m["overflow"], "notes": s["notes"],
                "page_number_source": m.get("page_number_source"),
                "footer_source": m.get("footer_source")})
  keep = re.findall(r"<Relationship\b[^>]*/>", parts[rpp].decode("utf-8", "replace"))
  parts[rpp] = (HDR % "".join(keep + ['<Relationship Id="%s" Type="%s" Target="%s"/>' % t
                                        for t in prel])).encode()
  parts["ppt/presentation.xml"] = set_ids(parts["ppt/presentation.xml"].decode("utf-8", "replace"),
                                          "".join(ids)).encode()
  return cms, metas


def export(out, npages, res):
  """soffice -> pdf, pdftoppm -> png previews; failures recorded, never fatal.

  v2: all paths absolute -- a relative --output made soffice drop the PDF elsewhere and the
  export silently degraded to 'no pdf artifact'.
  """
  out = Path(out).resolve()
  pdf = out / "presentation.pdf"
  exe = shutil.which("soffice") or shutil.which("libreoffice")
  log("export", "engine=%s target=%s" % (exe or "none", pdf))
  if exe:
    try:
      r = subprocess.run([exe, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(out),
                          str(out / "presentation.pptx")], capture_output=True, timeout=300,
                         env=dict(os.environ, HOME=str(out / "_home")))
      log("export", "soffice rc=%d stdout=%s" % (r.returncode, clip(r.stdout.decode("utf-8", "replace"), 120)))
    except Exception as e:
      res["degradations"].append({"stage": "pdf_export", "detail": str(e)[:160]})
      log("export", "soffice exception: %s" % str(e)[:120], "ERROR")
  if not (pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"):
    res["degradations"].append({"stage": "pdf_export", "fallback": "no pdf artifact",
                                "detail": "conversion failed" if exe else "soffice absent"})
    return None
  if shutil.which("pdftoppm"):
    (out / "preview").mkdir(exist_ok=True)
    try:
      subprocess.run(["pdftoppm", "-png", "-r", "50", "-f", "1", "-l", str(min(3, npages)), str(pdf),
                      str(out / "preview" / "slide")], capture_output=True, timeout=240)
    except Exception:
      pass
  return {"path": str(pdf), "engine": "libreoffice-headless", "bytes": pdf.stat().st_size}


def run(a, out, res, case):
  d = discover(Path(a.input), a)
  tp = Path(a.input) / "task.md"
  wo = wo_parse(d, (tp.read_text("utf-8", "replace")[:3000] if tp.exists() else "")
                + str(dfind(case or {}, ["taskinstruction"], "")))
  if a.slides:
    wo["slides"], wo["slides_explicit"] = a.slides, True
  res["workorder_echo"] = {k: wo[k] for k in ("mode", "slides", "source_preservation",
                                              "template_inheritance", "footer", "pagenum", "min_pt")}
  for f, kind in ([(d["template"], "template"), (d["deck"], "starting_deck"), (d["paper"], "paper")]
                  + [(w, "workorder") for w, _ in d["workorders"]] + [(d["case_path"], "case")]):
    if f and Path(f).exists():
      b = Path(f).read_bytes()
      res["sources"].append({"id": Path(f).name, "path": str(f), "kind": kind,
                             "bytes": len(b), "sha256": sha(b)})
  base = d["deck"] if (d["deck"] and Path(d["deck"]).exists()) else d["template"]
  parts, synthetic = None, False
  if base and Path(base).exists():
    try:
      with zipfile.ZipFile(str(base)) as z:
        parts = {n: z.read(n) for n in z.namelist()}
      if "ppt/presentation.xml" not in parts:
        res["exceptions"].append({"code": "template_incomplete", "detail": "no ppt/presentation.xml in package"})
        parts = None
    except Exception as e:
      res["exceptions"].append({"code": "template_unreadable", "detail": str(e)[:160]})
      parts = None
  if parts is None:
    synthetic = True
    parts = SP.synthetic_parts()
    base = out / "_synthetic_template.pptx"
    SP.write_parts(parts, base)
    res["degradations"].append({"stage": "template", "fallback": "built-in synthetic skeleton package",
                                "detail": "no readable organizer template; master/layout/theme are synthetic, "
                                          "so template inheritance cannot be credited"})
    res["pending_human"].append("supply the organizer template .pptx for real template inheritance")
    log("template", "no readable template -> synthetic skeleton package (%s)" % base.name, "WARN")
  txt, eng = "", "none"
  for f in ([d["paper"]] if d["paper"] else []) + d["docs"]:
    if f and Path(f).exists():
      t, e = V.read_any(f)
      if len(t) > len(txt):
        txt, eng = t, e
      if len(txt) >= 1500:
        break
  inv = scan(parts)
  res["exceptions"] += [{"code": "template_parse_note", "detail": x} for x in inv["parse_notes"]]
  log("template", "masters=%d layouts=%d theme=%s body=%.0fpt ea=%s"
      % (len(inv["master_sha256"]), len(inv["layouts"]), (inv["theme"] or {}).get("part"),
         inv["body_sz"], (inv["theme"] or {}).get("minor_ea") or "none"))
  spec = SP.build_spec(parts, base)
  spec["template"]["kind"] = "synthetic" if synthetic else "case_template"
  spec["workorder"] = {"slides": wo["slides"], "footer": wo["footer"], "min_pt": wo["min_pt"],
                       "page_numbers": wo["pagenum"], "mode": wo["mode"]}
  spec["layout_map_note"] = "per-page layout binding is appended after the deck is packed"
  wj(out / "template_spec.json", spec)
  log("template_spec", "slide=%sx%s %s parts=%d protected=%d (written)"
      % (spec["slide_size"]["cx_emu"], spec["slide_size"]["cy_emu"], spec["slide_size"]["ratio"],
         spec["counts"]["layouts"], len(spec["protected_parts"])))
  pages, secs = V.page_specs(d, wo, txt, doc_title(d, txt),
                             V.labels(sum(1 for ch in txt[:6000] if "\u4e00" <= ch <= "\u9fff") > 60))
  if not secs:
    res["exceptions"].append({"code": "no_source_text", "action": "title-only deck",
                              "detail": "no extractable sentences (%s)" % eng})
    res["pending_human"].append("supply a text-extractable paper (pdf text layer / md / docx)")
  strip_slides(parts)
  footer = clip(str(wo["footer"]), 60) if wo["footer"] else None
  cms, metas = build_slides(parts, inv, pages, wo, footer)
  pptx = out / "presentation.pptx"
  pack(parts, pptx)
  log("pack", "wrote %s (%d bytes, %d slides)" % (pptx.name, pptx.stat().st_size, len(pages)))
  rb = SP.guard(pptx, base, spec)
  log("guard", "checked=%d drift=%s verified=%s" % (rb.get("checked_parts"), rb.get("drift") or "none",
                                                     rb.get("verified")), "WARN" if rb.get("drift") else "INFO")
  if rb.get("drift"):
    res["degradations"].append({"stage": "template_guard", "detail": "%d protected part(s) drifted; restored from %s"
                                % (len(rb["drift"]), Path(base).name)})
  exp = None if a.no_pdf else export(out, len(pages), res)
  ctx = {"required_slides": wo["slides"], "mode": wo["mode"], "master_sha256": inv["master_sha256"],
         "theme_sha256": inv["theme_sha256"], "fonts": inv["theme"],
         "pages": [{"n": s["n"], "title": s["title"], "overflow": m["overflow"], "body_pt": m["body_pt"],
                    "footer": m["footer"], "page_number_text": m["page_number_text"],
                    "freetext": m["freetext"]} for s, m in zip(pages, metas)]}
  wj(out / "run_context.json", ctx)
  comp = V.check(out, ctx)
  roles = [p["role"] for p in pages]
  roles = [p["role"] for p in pages]
  comp["workorder_conformance"] = {
    "mode": wo["mode"], "slide_count_required": wo["slides"], "slide_count_actual": len(pages),
    "source_preservation": wo["source_preservation"], "template_inheritance": wo["template_inheritance"],
    "min_font_pt": wo["min_pt"], "footer_text_required": wo["footer"],
    "page_numbers_required": wo["pagenum"],
    "page_roles": {"title": "title" in roles, "outline": "outline" in roles,
                   "figure": "picture" in roles, "conclusion": "closing" in roles},
    "footer_source": sorted({m["footer_source"] for m in metas if m["footer_source"]}),
    "page_numbers_filled": any(m["page_number_text"] for m in metas)}
  res["compliance_checks"] = comp
  res["editable_source"] = {"path": str(pptx), "format": "pptx", "slides": len(pages), "mode": wo["mode"],
                            "template": {"path": str(base), "master_sha256": inv["master_sha256"],
                                         "theme_sha256": inv["theme_sha256"],
                                         "layouts_used": sorted({c["layout_id"] for c in cms if c["layout_id"]})},
                            "sha256": sha(pptx.read_bytes()), "bytes": pptx.stat().st_size}
  res["content_map"] = {"slides": cms}
  pdf = out / "presentation.pdf"
  pngs = sorted((out / "preview").glob("*.png")) if (out / "preview").exists() else []
  res["export_artifact"] = {
    "pdf": {"path": str(pdf) if exp else None, "engine": (exp or {}).get("engine"),
            "pages": (comp.get("pptx_pdf_consistency") or {}).get("pdf_pages"),
            "bytes": pdf.stat().st_size if exp else None},
    "png": {"path": str(out / "preview") if pngs else None, "count": len(pngs)},
    "consistency": comp.get("pptx_pdf_consistency")}
  spec["layout_map"] = SP.layout_map(spec, cms)
  spec["layout_map_status"] = "resolved"
  spec["layout_map_summary"] = {"pages": len(spec["layout_map"]),
                                "distinct_layouts": len({m["layout_part"] for m in spec["layout_map"]}),
                                "invented_placeholders": sum(len(m["invented_placeholders"]) for m in spec["layout_map"])}
  spec["pass"] = None
  wj(out / "template_spec.json", spec)
  facts = SP.analyze_deck(pptx, spec)
  fmt = SP.compliance(facts, spec, wo, cms)
  fmt["template"] = Path(base).name
  fmt["template_kind"] = spec["template"]["kind"]
  if synthetic:
    fmt["note"] = "deck built on the synthetic fallback package; CI-03..CI-06 certify internal consistency only"
  fmt["generated"] = RP.now()
  wj(out / "format_compliance.json", fmt)
  expo = SP.export_check(out, facts, wo, spec)
  wj(out / "export_check.json", expo)
  log("compliance", "%d/%d pass, fail=%s" % (fmt["passed"], fmt["total"], fmt["fail_ids"] or "none"))
  log("export_check", "pdf=%s pages=%s match=%s overflow=%d" % (expo["status"], (expo["pdf"] or {}).get("pages"),
                                                              expo["rules"]["pdf_pages_eq_slides"], expo["overflow"]["count"]))
  res["template_spec"] = {"path": str(out / "template_spec.json"),
                          "sha256": sha((out / "template_spec.json").read_bytes()),
                          "slide_size": spec["slide_size"], "counts": spec["counts"],
                          "theme_fonts": spec.get("theme_fonts"), "palette_size": len(spec.get("palette") or {}),
                          "protected_parts": len(spec.get("protected_parts") or {}),
                          "layout_map_pages": len(spec["layout_map"]),
                          "layout_map_summary": spec["layout_map_summary"]}
  res["format_compliance"] = {"path": str(out / "format_compliance.json"),
                              "sha256": sha((out / "format_compliance.json").read_bytes()),
                              "total": fmt["total"], "passed": fmt["passed"], "failed": fmt["failed"], "fail_ids": fmt["fail_ids"],
                              "pass_rate": fmt["pass_rate"], "pass": fmt["pass"],
                              "items": [{"id": c["id"], "item": c["item"], "status": c["status"],
                                         "actual": c["actual"]} for c in fmt["items"]]}
  res["export_check"] = expo
  res["rollback"] = {"strategy": rb.get("strategy"), "source_of_truth": Path(base).name,
                     "protected_parts": spec.get("protected_parts"),
                     "checked": rb.get("checked_parts"), "drift": rb.get("drift"),
                     "repaired": rb.get("repaired"), "verified": rb.get("verified"),
                     "method": rb.get("method"),
                     "manual_path": ["compare sha256 of protected parts against template_spec.protected_parts",
                                     "unzip -p <template> <protected part> to extract the pristine part",
                                     "rerun scripts/main.py --input <in> --output <out> --template <template>"],
                     "level": "template parts auto-restored; page level = idempotent rerun"}
  rdiff = RP.page_diff(out / "page_diff.md", {"cms": cms, "facts": facts, "spec": spec, "wo": wo,
                                              "paper_name": Path(d["paper"]).name if d["paper"] else None,
                                              "source_text": txt, "pptx": str(pptx), "case_id": res.get("case_id"),
                                              "export_check": expo, "format_compliance": fmt,
                                              "rollback": rb, "compliance_checks": comp,
                                              "footers": [m["footer"] for m in metas],
                                              "out": str(out), "pkg": str(H.parent), "default_body_pt": inv["body_sz"]})
  res["page_diff"] = {"path": rdiff["path"], "sha256": rdiff["sha256"], "pages": rdiff["pages"],
                      "rows": rdiff["rows"], "quote_hit": rdiff["quote_hit"], "quote_miss": rdiff["quote_miss"],
                      "deviations": rdiff["deviations"]}
  log("page_diff", "pages=%d evidence=%d hit=%d miss=%d" % (rdiff["pages"], rdiff["evidence_rows"],
                                                         rdiff["quote_hit"], rdiff["quote_miss"]))
  res["changes"] = [{"what": "template_slides_replaced",
                     "detail": "%d template slide part(s) removed, %d page(s) on template layouts"
                               % (len(inv["slide_parts"]), len(pages))},
                    {"what": "font_ladder", "detail": "body sizes %s pt (nominal %.0f, floor %.0f)"
                     % (sorted({m["body_pt"] for m in metas if m["body_pt"]}), inv["body_sz"], wo["min_pt"])},
                    {"what": "notes_delivery", "detail": "speaker notes in content_map[].notes"}]
  if any(p["role"] == "picture" and not p["evidence"] for p in pages):
    res["uncertainty"].append("figure without a verbatim caption in the source text")
  if any(x["inferred"] for x in secs):
    res["uncertainty"].append("section headings inferred from paragraph text")
  if eng in ("none", "", "no-pdf-text-tool", "unreadable"):
    res["uncertainty"].append("source text extraction quality low (%s)" % eng)
  if not fmt["pass"]:
    res["uncertainty"].append("format compliance items failed: %s (see format_compliance.json)"
                               % ", ".join(fmt["fail_ids"]))
  if not expo.get("pass"):
    res["uncertainty"].append("export/render check not clean: %s" % expo["status"])
  if rdiff["quote_miss"]:
    res["pending_human"].append("%d deck claim(s) not verified verbatim against the source" % rdiff["quote_miss"])
  if synthetic:
    res["uncertainty"].append("deck uses a synthetic master/layout/theme: the organizer template was not read")
  res["status"] = "ok" if (comp.get("pass") and exp and fmt["pass"] and expo.get("pass")
                            and not synthetic and not res["errors"]) else "partial"
def finish(out, res, case):
  """echo every declared output_contract field verbatim, preserving unknown keys"""
  c = dfind(case or {}, ["outputcontract", "resultcontract", "outputschema"])
  fields = []
  if isinstance(c, dict):
    for k, v in c.items():
      fields.append(k)
      if k not in res:
        res[k] = v
  elif isinstance(c, list):
    for k in c:
      k = k if isinstance(k, str) else str(k)
      fields.append(k)
      res.setdefault(k, None)
  for k in ("case_id", "status", "editable_source", "export_artifact", "content_map",
            "compliance_checks", "exceptions"):
    res.setdefault(k, None)
  res["output_contract_fields"] = fields
  res["runtime"] = {"seconds": round(time.time() - T0, 2), "stdlib_only": True,
                    "external_tools": {k: bool(shutil.which(k)) for k in
                                       ("soffice", "libreoffice", "pdftoppm", "pdftotext")}}
  wj(Path(out) / "result.json", res)


def main(argv=None):
  ap = argparse.ArgumentParser(
    description="Fit paper content into a real .pptx template: editable deck, rendered PDF, per-slide evidence map, conformance report.",
    epilog="Writes presentation.pptx, presentation.pdf, template_spec.json, format_compliance.json, "
           "page_diff.md, version_history.md, export_check.json, run.log, result.json under --output. "
           "Exit code is always 0.")
  ap.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"), help="case input directory")
  ap.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "/app/output"), help="output directory")
  ap.add_argument("--template", default=None, help="explicit template .pptx")
  ap.add_argument("--deck", default=None, help="explicit starting deck .pptx (defaults to the template)")
  ap.add_argument("--slides", type=int, default=None, help="override target slide count")
  ap.add_argument("--no-pdf", action="store_true", help="skip PDF export")
  a = ap.parse_args(argv)
  out = Path(a.output).resolve()
  out.mkdir(parents=True, exist_ok=True)
  try:
    LOG.__init__(out / "run.log")
  except Exception:
    pass
  log("main.start", "argv=%s" % (argv if argv is not None else sys.argv[1:]))
  log("main.init", "input=%s output=%s python=%s" % (Path(a.input).resolve(), out, sys.version.split()[0]))
  res = {"case_id": None, "status": "partial", "task": "slides-04", "editable_source": None,
         "export_artifact": None, "content_map": {"slides": []}, "compliance_checks": {},
         "exceptions": [], "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
         "degradations": [], "changes": [], "runtime": {}}
  wj(out / "result.json", res)
  case = rj(Path(a.input) / "case.json")
  case = case if isinstance(case, dict) else None
  if case:
    res["case_id"] = case.get("case_id") or dfind(case, ["caseid"])
    wj(out / "result.json", res)
  try:
    run(a, out, res, case)
  except Exception:
    res["errors"].append({"stage": "run", "detail": traceback.format_exc()[-1200:]})
    res["status"] = "partial"
    log("run", traceback.format_exc()[-300:], "ERROR")
  finally:
    try:
      if res.get("page_diff"):
        vh = RP.version_history(out / "version_history.md", {
          "out": str(out), "pkg": str(H.parent), "case_id": res.get("case_id"), "runtime": {"seconds": round(time.time() - T0, 2), "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0))},
          "spec": {"protected_parts": (res.get("rollback") or {}).get("protected_parts") or {},
                   "rollback_note": "auto guard on protected template parts; manual path = rerun with --template"},
          "format_compliance": res.get("format_compliance") or {}})
        res["version_history"] = {"path": vh["path"], "sha256": vh["sha256"], "versions": vh["versions"],
                                  "artifacts": vh["artifacts"], "rollback": vh["rollback"]}
        log("version_history", "versions=%s written" % vh["versions"])
    except Exception:
      res.setdefault("errors", []).append({"stage": "version_history", "detail": traceback.format_exc()[-500:]})
    try:
      finish(out, res, case)
      res["run_log"] = {"path": str(LOG.path), "lines": len(LOG.lines), "stages": LOG.summary()["stages"]}
      wj(out / "result.json", res)
      log("main.done", "status=%s seconds=%.2f" % (res.get("status"), time.time() - T0))
    except Exception:
      res.setdefault("errors", []).append({"stage": "finish", "detail": traceback.format_exc()[-600:]})
      try:
        wj(out / "result.json", res)
      except Exception:
        pass
  return 0


if __name__ == "__main__":
  sys.exit(main())
