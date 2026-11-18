#!/usr/bin/env python3
"""Content layer: locatable text units, metadata with provenance, version keys, query terms,
hard filters, case.json questions/notes, section locators, verbatim quotes. Stdlib only, no I/O."""
import html, io, json, re, sys, unicodedata, zipfile, zlib
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".html",
      ".htm", ".yaml", ".yml", ".log", ".tex", ".bib", ".ini", ".cfg", ".srt"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
OLE_EXT = {".doc", ".xls", ".ppt"}
MAGIC = [(b"%PDF", "pdf"), (b"PK\x03\x04", "zip"), (b"\xd0\xcf\x11\xe0", "ole"),
    (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpeg"), (b"II*\x00", "tiff"), (b"MM\x00*", "tiff")]


def clean(t):
  t = (t or "").replace("\x00", " ")
  return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t\u3000\u00a0]+", " ", t)).strip()


def kind_of(path, head):
  for sig, k in MAGIC:
    if head.startswith(sig):
      return k
  e = Path(path).suffix.lower()
  return "text" if e in TEXT_EXT else "image" if e in IMG_EXT else "ole" if e in OLE_EXT else "binary"


def _unesc(b):
  def rep(m):
    g = m.group(1)
    if g[:1].isdigit():
      return bytes([int(g, 8) & 255])
    return {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(g, b"" if g in b"\r\n" else g)
  return re.sub(rb"\\([0-7]{1,3}|.)", rep, b)


_TOK = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]{2,}>|T\*|\bT[Dd]\b|\bET\b")


def _ctext(c):
  buf = []
  for m in _TOK.finditer(c):
    s = m.group(0)
    if s[:1] == b"(":
      buf.append(_unesc(s[1:-1]).decode("latin-1", "ignore"))
    elif s[:1] == b"<":
      h = re.sub(rb"[^0-9A-Fa-f]", b"", s[1:-1])
      if h:
        try:
          bb = bytes.fromhex((h + b"0" * (len(h) % 2)).decode())
          buf.append(bb.decode("utf-16-be") if len(bb) > 2 else bb.decode("latin-1", "ignore"))
        except Exception:
          pass
    else:
      buf.append("\n")
  return clean("".join(buf))


def _stream(body):
  i = body.find(b"stream")
  if i < 0:
    return None
  j = i + 6
  while j < len(body) and body[j:j + 1] in (b"\r", b"\n"):
    j += 1
  k = body.rfind(b"endstream")
  raw = (body[j:k] if k > j else body[j:]).rstrip(b"\r\n")
  if b"/FlateDecode" in body[:i]:
    try:
      return zlib.decompressobj().decompress(raw)
    except Exception:
      return None
  return None if b"/Filter" in body[:i] else raw


def pdf_pages(d):
  """-> (page_texts | None, status, page_order_basis). Page numbers are physical pages, 1-based."""
  if re.search(rb"/Encrypt\s*(\d+\s+\d+\s*R|<<)", d):
    return None, "encrypted_pdf", None
  objs = {int(m.group(1)): m.group(3)
      for m in re.finditer(rb"(?<![0-9])(\d{1,7})\s+(\d{1,5})\s+obj\b(.*?)\bendobj", d, re.S)}
  pages = [(n, b) for n, b in objs.items() if re.search(rb"/Type\s*/Page\b", b)]
  texts = []
  for n, b in pages:
    refs = [int(x) for x in re.findall(rb"/Contents\s+(\d+)\s+\d+\s+R", b)]
    ar = re.search(rb"/Contents\s*\[(.*?)\]", b, re.S)
    if ar:
      refs += [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", ar.group(1))]
    texts.append("\n".join(x for x in (_ctext(_stream(objs.get(r, b"")) or b"") for r in (refs or [n])) if x))
  basis = "page_object_sequence"
  if not texts:
    basis = "stream_sequence_fallback"
    texts = [t for t in (_ctext(_stream(b) or b"") for b in objs.values()) if sum(c.isalnum() for c in t) > 20]
  if not [t for t in texts if sum(c.isalnum() for c in t) > 20]:
    return None, "scanned_no_text_layer", basis
  return texts, "ok", basis


def docx_units(raw):
  x = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode("utf-8", "ignore")
  out, i = [], 0
  for m in re.finditer(r"<w:p[ >].*?</w:p>|<w:p/>", x, re.S):
    i += 1
    t = clean(re.sub(r"<[^>]+>", "", html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(0), re.S)))))
    if t:
      out.append({"loc": {"kind": "docx_para", "para": i}, "text": t})
  return out


def xlsx_units(raw):
  z = zipfile.ZipFile(io.BytesIO(raw))
  names = z.namelist()
  shared, titles = [], []
  if "xl/sharedStrings.xml" in names:
    s = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
    shared = [html.unescape(re.sub(r"<[^>]+>", "", si)) for si in re.findall(r"<si>(.*?)</si>", s, re.S)]
  if "xl/workbook.xml" in names:
    wb = z.read("xl/workbook.xml").decode("utf-8", "ignore")
    titles = [html.unescape(x) for x in re.findall(r'<sheet[^>]*name="([^"]*)"', wb)]
  parts = sorted([n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)],
         key=lambda s: int(re.findall(r"\d+", s)[-1]))
  out = []
  for k, nm in enumerate(parts):
    x = z.read(nm).decode("utf-8", "ignore")
    sheet = titles[k] if k < len(titles) else nm.rsplit("/", 1)[-1][:-4]
    for rn, body in re.findall(r'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', x, re.S):
      cells = []
      for at, inner in re.findall(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", body, re.S):
        mc, tz = re.search(r'r="([A-Z]{1,3})\d+"', at), re.search(r't="(\w+)"', at)
        tz = tz.group(1) if tz else ""
        v = re.search(r"<v>(.*?)</v>", inner, re.S)
        if tz == "s" and v and v.group(1).strip().isdigit():
          i = int(v.group(1))
          val = shared[i] if i < len(shared) else ""
        elif tz == "inlineStr":
          val = html.unescape(re.sub(r"<[^>]+>", "", inner))
        else:
          val = html.unescape(v.group(1)) if v else ""
        if val.strip():
          cells.append("%s=%s" % (mc.group(1) if mc else "?", val.strip()))
      if cells:
        out.append({"loc": {"kind": "xlsx_row", "sheet": sheet, "row": int(rn)},
              "text": clean(" | ".join(cells))})
  return out


def pptx_units(raw):
  z = zipfile.ZipFile(io.BytesIO(raw))
  ns = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
  ns.sort(key=lambda s: int(re.findall(r"\d+", s)[-1]))
  out = []
  for i, nm in enumerate(ns, 1):
    x = z.read(nm).decode("utf-8", "ignore")
    ts = [html.unescape(re.sub(r"<[^>]+>", "", t)) for t in re.findall(r"<a:t>(.*?)</a:t>", x, re.S)]
    out.append({"loc": {"kind": "pptx_slide", "slide": i}, "text": clean("\n".join(t for t in ts if t.strip()))})
  return out


def text_units(raw):
  lines = None
  for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
    try:
      lines = raw.decode(enc).splitlines()
      break
    except Exception:
      lines = None
  if lines is None:
    return [], "undecodable_text", None
  out = []
  for i in range(0, len(lines), 40):
    blk = lines[i:i + 40]
    if "".join(blk).strip():
      out.append({"loc": {"kind": "text_line", "line_start": i + 1, "line_end": i + len(blk)},
            "text": clean("\n".join(blk))})
  return out, "ok", "encoding=%s" % enc


def units_of(path, raw, kind=None):
  """-> (units, status, note). Malformed input yields a status, never an exception."""
  kind = kind or kind_of(path, raw[:16])
  ext = Path(path).suffix.lower()
  try:
    if kind == "pdf":
      pages, st, basis = pdf_pages(raw)
      if not pages:
        return [], st, ("pdf_page_order=%s" % basis) if basis else None
      return ([{"loc": {"kind": "pdf_page", "page": i + 1}, "text": clean(t)} for i, t in enumerate(pages)],
          st, "pdf_page_order=%s" % basis)
    if ext == ".docx":
      return docx_units(raw), "ok", None
    if ext == ".xlsx":
      return xlsx_units(raw), "ok", None
    if ext == ".pptx":
      return pptx_units(raw), "ok", None
    if kind == "text":
      return text_units(raw)
    if kind in ("image", "png", "jpeg", "tiff"):
      return [], "image_no_text_layer", None
    if kind == "ole":
      return [], "unsupported_legacy_office", None
    return [], "unsupported_binary", None
  except PermissionError:
    return [], "permission_denied", None
  except Exception as e:
    return [], "parse_error:%s" % type(e).__name__, str(e)[:160]


RX_PROJ = re.compile(r"(?:project|proj|项目|课题)[\s_\-:：#]*([A-Za-z]{1,5}[\-_]?\d{1,6})", re.I)
RX_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
RX_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
RX_VER = re.compile(r"(?<![A-Za-z])(v(?:er)?\.?\s?\d{1,3}(?:\.\d{1,3})?|rev(?:ision)?\.?\s?\d{0,2}|r\d{1,2}|final|"
          r"draft|定稿|终稿|初稿|修订[版]?|新版|旧版)(?![A-Za-z])", re.I)
RX_BATCH = re.compile(r"(?:batch|lot|批次|批号)[\s_\-:：#]*([A-Za-z0-9\-]{1,12})", re.I)
FIELDS = (("project_id", RX_PROJ), ("year", RX_YEAR), ("version_label", RX_VER), ("batch", RX_BATCH))
DOCTYPE = [("protocol", r"protocol|sop|规程|操作规范|实验方案|procedure"), ("record", r"记录|record|notebook|日志"),
     ("report", r"报告|report|总结"), ("manuscript", r"manuscript|投稿|正文|论文"),
     ("supplementary", r"supplement|补充材料|附录|appendix"), ("data", r"dataset|数据表|raw ?data|原始数据"),
     ("figure", r"figure|fig\.|图注|示意图"), ("slide", r"slide|汇报|讲座|讲义"),
     ("admin", r"invoice|采购|订单|审批|合同|基金")]


def vord(label):
  if not label:
    return None
  s = label.lower().strip()
  if "定稿" in s or "终稿" in s or s == "final":
    return 900.0
  if "初稿" in s or s == "draft":
    return 1.0
  m = re.search(r"\d+(?:\.\d+)?", s)
  if m:
    return float(m.group(0)) + (900 if "final" in s else 0)
  return 500.0 if "修订" in s else None


def meta(name, text, mtime, iso=lambda t: ""):
  md, pv = {}, {}
  for k, rx in FIELDS:
    m = rx.search(name)
    if m:
      md[k], pv[k] = m.group(1).strip(), {"source": "filename", "evidence": m.group(0)}
  body = (text or "")[:4000]
  if "project_id" not in md and RX_PROJ.search(body):
    m = RX_PROJ.search(body)
    md["project_id"], pv["project_id"] = m.group(1).strip(), {"source": "content", "evidence": m.group(0)}
  if "year" not in md:
    m = RX_DATE.search(body) or RX_YEAR.search(body)
    if m:
      md["year"], pv["year"] = m.group(1), {"source": "content", "evidence": m.group(0)}
    else:
      md["year"], pv["year"] = iso(mtime)[:4], {"source": "fs_mtime", "evidence": iso(mtime)[:10]}
  low = (name + " " + body[:2500]).lower()
  for dt, rx in DOCTYPE:
    m = re.search(rx, low)
    if m:
      md["doc_type"] = dt
      pv["doc_type"] = {"source": "filename" if re.search(rx, name.lower()) else "content", "evidence": m.group(0)}
      break
  if "doc_type" not in md:
    md["doc_type"] = "document" if name.lower().endswith((".pdf", ".docx", ".doc")) else "file"
    pv["doc_type"] = {"source": "extension", "evidence": Path(name).suffix}
  return md, pv


def stem_key(name):
  """Grouping key with version/copy/date tokens stripped. Grouping stays a hypothesis:
  content hashes and timestamps confirm or reject it."""
  s = unicodedata.normalize("NFKC", name.rsplit(".", 1)[0]).lower()
  for rx, rep in ((r"[\(（]\s*\d{1,2}\s*[\)）]", " "), (r"copy|副本|备份|backup", " "),
          (r"(?<![a-z])v(?:er)?\.?\s?\d{1,3}(?:\.\d{1,3})?", " "), (r"(?<![a-z])rev(?:ision)?\.?\s?\d{0,2}", " "),
          (r"(?<![a-z])r\d{1,2}(?![0-9a-z])", " "), (r"final|draft|定稿|终稿|初稿|修订版?|新版|旧版|new|old", " "),
          (r"(?<!\d)(?:19|20)\d{2}[-_.]?(?:0[1-9]|1[0-2])[-_.]?(?:0[1-9]|[12]\d|3[01])(?!\d)", " "),
          (r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ")):
    s = re.sub(rx, rep, s)
  return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s)


def norm(s):
  s = unicodedata.normalize("NFKC", s or "").lower()
  return re.sub(r"\s+", " ", re.sub(r"[\u2010-\u2015]", "-", s))


def toks(s):
  s, res = norm(s), set()
  for t in re.findall(r"[a-z0-9][a-z0-9.+#/_-]*", s):
    t = t.strip("-./")
    if len(t) >= 2:
      res.add(t)
      if len(t) > 4 and t.isalpha() and t.endswith("s"):
        res.add(t[:-1])
  for run in re.findall(r"[\u3400-\u9fff]{2,}", s):
    res |= {run[i:i + 2] for i in range(len(run) - 1)}
  return res


SYNS = ("缓冲液=buffer;配方=formulation recipe composition;批次=batch lot;样品=sample specimen;抗体=antibody;"
    "方法=method protocol sop;设备=instrument device equipment;版本=version revision;记录=record note log;"
    "浓度=concentration;温度=temperature;数据=data dataset;图=figure;表=table;实验=experiment assay;"
    "权限=permission access;重复=duplicate")
SYN = [tuple(x.split("=")) for x in SYNS.split(";")]


def expand(q):
  """Literal tokens weigh 1.0, synonym/abbreviation expansions 0.55: expansions rank, never decide."""
  low, base = norm(q), toks(q)
  ex = set()
  for zh, en in SYN:
    if zh in low:
      ex |= toks(en)
    if any(norm(w) in low for w in en.split()):
      ex |= toks(zh)
  return {t: 1.0 for t in base} | {t: 0.55 for t in (ex - base)}


FKS = ("year=year 年份 年度;project=project 项目 课题 proj;ext=type ext 格式 文件类型 format;"
   "batch=batch lot 批次 批号;version=version rev 版本;path=path dir folder 目录 路径 prefix")
FK = {d.split("=")[0]: d.split("=")[1].split() for d in FKS.split(";")}


def dim_match(key, names):
  k = " " + re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(key).lower()).strip() + " "
  for n in names:
    if n.isascii():
      if (" " + n + " ") in k:
        return True
    elif n in k:
      return True
  return False


def filters_of(qo, qtext):
  f = {}
  def scan(d):
    for k, v in d.items():
      if isinstance(v, dict):
        scan(v)
        continue
      if v in (None, "", [], {}):
        continue
      for dim, names in FK.items():
        if dim_match(k, names):
          f.setdefault(dim, []).extend(v if isinstance(v, list) else [str(v)])
  if isinstance(qo, dict):
    scan(qo)
  t = norm(qtext)
  f.setdefault("year", []).extend(re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", t))
  m = RX_PROJ.search(qtext)
  if m:
    f.setdefault("project", []).append(m.group(1))
  ext = [e for w, e in (("pdf", ".pdf"), ("word", ".docx"), ("docx", ".docx"), ("excel", ".xlsx"),
             ("xlsx", ".xlsx"), ("表格", ".xlsx"), ("ppt", ".pptx"), ("幻灯片", ".pptx")) if w in t]
  if ext:
    f.setdefault("ext", []).extend(ext)
  if re.search(r"最新|latest|current|定稿", t):
    f.setdefault("version", []).append("current")
  return {k: sorted({str(x).lower() for x in v}) for k, v in f.items() if v}


def match_dim(r, dim, vals):
  """One hard constraint against one record: no relaxation, no fuzzy fallback."""
  if dim == "year":
    return str(r.get("year") or "") in vals
  if dim == "project":
    p = str(r.get("project_id") or "").lower()
    return bool(p) and any(v == p or v in p for v in vals)
  if dim == "ext":
    return r.get("ext", "").lower() in vals
  if dim == "batch":
    b = str(r.get("batch") or "").lower()
    return bool(b) and b in vals
  if dim == "version":
    return bool(r.get("is_current")) if "current" in vals else str(r.get("version_label") or "").lower() in vals
  if dim == "path":
    return any(v in r["path"].lower() for v in vals)
  return True


QKEY = re.compile(r"\bquer(?:y|ies)\b|\bquestions?\b|\basks?\b|\brequests?\b|检索|提问|问题", re.I)


def walk_q(node, out, d=0):
  """Questions are found by meaning at any depth; key names are not assumed."""
  if d > 6 or not isinstance(node, (dict, list)):
    return
  for k, v in (node.items() if isinstance(node, dict) else [(None, x) for x in node]):
    key, hit = str(k), bool(k) and bool(QKEY.search(str(k)))
    if isinstance(v, dict):
      t = next((v[x] for x in v if isinstance(v[x], str) and len(v[x]) >= 8
                and re.search(r"text|query|question|内容", x, re.I)), None) if hit else None
      if t:
        out.append({"qid": str(v.get("id") or v.get("qid") or ""), "query": t.strip(),
                    "origin": "case.json:" + key, "obj": v})
      else:
        walk_q(v, out, d + 1)
    elif isinstance(v, list):
      for i, it in enumerate(v):
        t = it if isinstance(it, str) else (next((it[x] for x in it if isinstance(it[x], str) and len(it[x]) >= 8), None)
                                           if isinstance(it, dict) else None)
        if hit and t and len(t) >= 8:
          out.append({"qid": str(it.get("id") or it.get("qid") or "") if isinstance(it, dict) else "", "query": t.strip(),
                      "origin": "case.json:%s[%d]" % (key, i), "obj": it if isinstance(it, dict) else None})
        elif isinstance(it, (dict, list)):
          walk_q(it, out, d + 1)
    elif hit and isinstance(v, str) and 8 <= len(v) <= 400:
      out.append({"qid": "", "query": v.strip(), "origin": "case.json:" + key})




def apply_notes(files, case, res):
  """Organiser notes/aliases (note|alias|version-like keys): applied with provenance."""
  ov = []
  if isinstance(case, dict):
    for k, v in case.items():
      if not isinstance(v, (dict, list)) or not re.search(r"note|alias|rename|metadata|version|admin|备注|别名|版本说明", str(k), re.I):
        continue
      pairs = list(v.items()) if isinstance(v, dict) else []
      for it in (v if isinstance(v, list) else []):
        if isinstance(it, dict):
          m = next((str(it[x]) for x in it if re.search(r"file|path|name|文件|名称", x, re.I)), "")
          if m:
            pairs.append((m, it))
      for a, b in pairs:
        f = {"note": b} if isinstance(b, str) else {kk: str(vv) for kk, vv in b.items() if isinstance(vv, (str, int, float))}
        ov.append({"source": "case.json:%s" % k, "match": str(a), "fields": f})
  hit = 0
  for r in files:
    for o in ov:
      m = o["match"].lower().strip()
      if not m or not (m == r["name"].lower() or m == r["path"].lower() or (len(m) > 5 and m in r["path"].lower())):
        continue
      hit += 1
      r["admin_notes"].append({"source": o["source"], "fields": o["fields"]})
      for kk, vv in o["fields"].items():
        tgt = ("version_label" if re.search(r"version|版本", kk, re.I) else "project_id" if re.search(r"project|项目", kk, re.I)
               else "year" if re.search(r"year|年份", kk, re.I) else "batch" if re.search(r"batch|批次", kk, re.I) else None)
        if tgt:
          r[tgt], r["meta_sources"][tgt] = vv, "case_note"
          r["meta_evidence"][tgt] = o["source"]
  res["admin_overlays"] = {"defined": len(ov), "applied": hit}




HEAD = re.compile(r"^\s*(?:(\d+(?:\.\d+){0,3})[\.\s、]|(第[一二三四五六七八九十百\d]{1,4}[章节篇])|([A-Z][A-Z \-]{3,40})$|"
         r"(摘\s*要|目\s*录|引\s*言|前\s*言|方\s*法|材料与方法|结\s*果|讨\s*论|结\s*论|参\s*考\s*文\s*献|附\s*录|实验方法|数据分析)\s*$)", re.I)
LF = {"pdf_page": ("p.{page}", "page={page}"), "docx_para": ("\u00b6{para}", "para={para}"),
   "xlsx_row": ("{sheet}!row{row}", "sheet={sheet}&row={row}"), "pptx_slide": ("slide {slide}", "slide={slide}"),
   "text_line": ("lines {line_start}-{line_end}", "line={line_start}")}


def sections(units):
  """Section heading in force for each unit: a printed heading carries across page/slide breaks."""
  carry = ""
  for u in units:
    heads = [clean(m.group(0))[:80] for m in HEAD.finditer(u["text"])]
    u["sec"] = heads[0] if heads else carry
    if heads:
      carry = heads[-1]









def loc_str(loc, c0, c1, sec=""):
  """Human hint + machine fragment of one locator (the backlink target)."""
  h, f = LF.get(loc.get("kind"), ("unit", "unit"))
  safe = {k: ("" if v is None else v) for k, v in loc.items()}
  try:
    return h.format(**safe) + (" \u00a7%s" % sec if sec else ""), f.format(**safe) + "&char=%s-%s" % (c0, c1)
  except Exception:
    return str(loc), str(loc)


def quote_at(txt, terms):
  """Verbatim slice around the first strong hit, trimmed to sentence boundaries."""
  low, b = txt.lower(), 0
  for t in sorted(terms, key=len, reverse=True):
    i = low.find(t.lower())
    if i >= 0:
      b = max(0, i - 70)
      break
  s, e = b, min(len(txt), b + 300)
  while s > 0 and txt[s - 1] not in "。！？.!?\n":
    s -= 1
  while e < len(txt) and txt[e] not in "。！？.!?\n":
    e += 1
  return txt[s:e + 1].strip(), s, min(e + 1, len(txt))
