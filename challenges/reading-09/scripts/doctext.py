"""doctext.py - stdlib-only document text/layout extraction + segmentation.

PDF (objects/object-streams/Flate/ToUnicode CMaps/page tree), DOCX, XLSX, CSV,
HTML, JSON, TXT. CLI: python3 doctext.py --help | doctext.py FILE [--json]
"""
import argparse
import bisect
import csv
import io
import json
import re
import sys
import zipfile
import zlib
from pathlib import Path

LIG = {11: "ff", 12: "fi", 13: "fl", 27: "ffi", 28: "ffl"}


class PdfError(Exception):
  pass


def _stream(body):
  i = body.find(b"stream")
  if i < 0:
    return None
  j = i + 6
  j += 2 if body[j:j + 2] == b"\r\n" else (1 if body[j:j + 1] in (b"\n", b"\r") else 0)
  k = body.rfind(b"endstream")
  return body[j:k if k > 0 else len(body)]


def _decode(body, data):
  if data is None:
    return b""
  m = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", body)
  for f in ([x.decode("latin-1") for x in re.findall(rb"/(\w+)", m.group(1))] if m else []):
    try:
      if f in ("FlateDecode", "Fl"):
        try:
          data = zlib.decompress(data)
        except zlib.error:
          data = zlib.decompressobj().decompress(data[2:])
      elif f in ("ASCIIHexDecode", "AHx"):
        h = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">")[0])
        data = bytes.fromhex((h + b"0" * (len(h) % 2)).decode())
      else:
        return b""
    except Exception:
      return b""
  return data


def _objs(data):
  o = {}
  for m in re.finditer(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b", data):
    e = data.find(b"endobj", m.end())
    o[int(m.group(1))] = data[m.end():e if e > 0 else len(data)]
  for n, b in list(o.items()):
    if not re.search(rb"/Type\s*/ObjStm", b):
      continue
    d = _decode(b, _stream(b))
    mn, mf = re.search(rb"/N\s+(\d+)", b), re.search(rb"/First\s+(\d+)", b)
    if not (d and mn and mf):
      continue
    first, hdr = int(mf.group(1)), d[:int(mf.group(1))].split()
    pr = []
    for i in range(0, min(len(hdr) - 1, 2 * int(mn.group(1))), 2):
      try:
        pr.append((int(hdr[i]), int(hdr[i + 1])))
      except ValueError:
        break
    for i, (num, off) in enumerate(pr):
      s, e = first + off, (first + pr[i + 1][1]) if i + 1 < len(pr) else len(d)
      o.setdefault(num, d[s:e])
  return o


def _hextext(b):
  try:
    return bytes.fromhex(b.decode("latin-1")).decode("utf-16-be", "ignore")
  except Exception:
    return ""


def _cmap(raw):
  m = {}
  for blk in re.findall(rb"beginbfchar(.*?)endbfchar", raw, re.S):
    for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
      m[int(a, 16)] = _hextext(b)
  pat = rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])"
  for blk in re.findall(rb"beginbfrange(.*?)endbfrange", raw, re.S):
    for a, b, t in re.findall(pat, blk):
      lo, hi = int(a, 16), int(b, 16)
      if hi < lo or hi - lo > 4096:
        continue
      if t.startswith(b"["):
        for k, h in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", t)):
          if lo + k <= hi:
            m[lo + k] = _hextext(h)
      else:
        base = int(t.strip(b"<>"), 16)
        for k in range(hi - lo + 1):
          if base + k <= 0x10FFFF:
            m[lo + k] = chr(base + k)
  return m or None


def _cmap_of(objs, num):
  b = objs.get(num, b"")
  mt = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", b)
  if not mt:
    return None
  t = int(mt.group(1))
  return _cmap(_decode(objs.get(t, b""), _stream(objs.get(t, b""))))


def _fonts(objs, body):
  m = re.search(rb"/Font\s*<<(.*?)>>", body, re.S)
  src = m.group(1) if m else None
  if src is None:
    mr = re.search(rb"/Font\s+(\d+)\s+0\s+R", body)
    if mr:
      fb = objs.get(int(mr.group(1)), b"")
      m2 = re.search(rb"<<(.*?)>>", fb, re.S)
      src = m2.group(1) if m2 else fb
  if src is None:
    return {}
  return {n.decode("latin-1"): _cmap_of(objs, int(k))
      for n, k in re.findall(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", src)}


def _walk(objs, num, res, out, depth=0):
  body = objs.get(num)
  if body is None or depth > 40 or len(out) > 4000:
    return
  if re.search(rb"/Font\s*<<|/Font\s+\d+\s+0\s+R", body):
    res = _fonts(objs, body)
  if re.search(rb"/Type\s*/Page\b", body) and b"/Kids" not in body:
    out.append((num, res))
    return
  km = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
  for kid in (re.findall(rb"(\d+)\s+0\s+R", km.group(1)) if km else []):
    _walk(objs, int(kid), res, out, depth + 1)


ESC = {110: 10, 114: 13, 116: 9, 98: 8, 102: 12}


def _dstr(b, cmap):
  if not cmap:
    return "".join(LIG.get(ord(c), c if ord(c) > 31 or c in "\n\t" else "")
           for c in b.decode("latin-1", "ignore"))
  st = 2 if any(k > 255 for k in cmap) else 1
  return "".join(cmap.get(int.from_bytes(b[k:k + st], "big"), "")
         for k in range(0, len(b) - st + 1, st))


def _ctext(s, fonts):
  out, st, i, n, cur = [], [], 0, len(s), None

  def nl():
    if not out or out[-1] != "\n":
      out.append("\n")

  while i < n:
    c = s[i]
    if c in b" \t\r\n\x00":
      i += 1
      continue
    if c == 37:
      j = s.find(b"\n", i)
      i = n if j < 0 else j + 1
      continue
    if c == 40:
      d, j, v = 1, i + 1, bytearray()
      while j < n and d:
        ch = s[j]
        if ch == 92 and j + 1 < n:
          nx = s[j + 1]
          if nx in ESC:
            v.append(ESC[nx]); j += 2; continue
          if 48 <= nx <= 55:
            t, k = 0, j + 1
            for _ in range(3):
              if k < n and 48 <= s[k] <= 55:
                t = t * 8 + s[k] - 48; k += 1
              else:
                break
            v.append(t & 255); j = k; continue
          if nx in (10, 13):
            j += 2; continue
          v.append(nx); j += 2; continue
        if ch == 40:
          d += 1
        elif ch == 41:
          d -= 1
          if not d:
            j += 1; break
        v.append(ch); j += 1
      st.append(("s", bytes(v))); i = j; continue
    if c == 60:
      if s[i + 1:i + 2] == b"<":
        d, j = 1, i + 2
        while j < n and d:
          if s[j:j + 2] == b"<<":
            d += 1; j += 2; continue
          if s[j:j + 2] == b">>":
            d -= 1; j += 2; continue
          j += 1
        i = j; continue
      j = s.find(b">", i)
      if j < 0:
        break
      h = re.sub(rb"[^0-9A-Fa-f]", b"", s[i + 1:j])
      st.append(("s", bytes.fromhex((h + b"0" * (len(h) % 2)).decode()))); i = j + 1; continue
    if c == 62:
      i += 1; continue
    if c == 91:
      st.append(("[", None)); i += 1; continue
    if c == 93:
      st.append(("]", None)); i += 1; continue
    if c == 47:
      j = i + 1
      while j < n and s[j] not in b" \t\r\n/[]<>()%":
        j += 1
      st.append(("n", s[i + 1:j].decode("latin-1", "ignore"))); i = j; continue
    j = i
    while j < n and s[j] not in b" \t\r\n/[]<>()%":
      j += 1
    j = max(j, i + 1)
    tok, i = s[i:j].decode("latin-1", "ignore"), j
    try:
      st.append(("d", float(tok))); continue
    except ValueError:
      pass
    if tok == "Tf":
      names = [v for t, v in st if t == "n"]
      cur = names[-1] if names else cur
    elif tok in ("Tj", "'", '"'):
      ss = [v for t, v in st if t == "s"]
      if tok in ("'", '"'):
        nl()
      if ss:
        out.append(_dstr(ss[-1], fonts.get(cur) if cur else None))
    elif tok == "TJ":
      k = max([x for x, (t, _) in enumerate(st) if t == "["], default=-1)
      for t, v in st[k + 1:]:
        if t == "s":
          out.append(_dstr(v, fonts.get(cur) if cur else None))
        elif t == "d" and v < -150:
          out.append(" ")
      if k >= 0:
        st = st[:k]
    elif tok in ("Td", "TD", "T*", "Tm", "BT", "ET"):
      if tok in ("T*", "TD"):
        nl()
      elif tok == "Td":
        nums = [v for t, v in st if t == "d"]
        if len(nums) > 1 and abs(nums[-1]) > 0.8:
          nl()
        elif out and out[-1] not in ("\n", " "):
          out.append(" ")
      elif tok in ("Tm", "BT") and out and out[-1] != "\n":
        nl()
    st = st[-64:]
  return "".join(out)


def _tidy(raw):
  t = re.sub(r"[ \t\u00a0]+", " ", raw.replace("\r", "\n"))
  t = re.sub(r" ?\n ?", "\n", t)
  out = []
  for ln in re.sub(r"\n{3,}", "\n\n", t).split("\n"):
    s = ln.strip()
    if s and out and out[-1].endswith("-") and s[:1].islower():
      out[-1] = out[-1][:-1] + s
    else:
      out.append(s)
  return "\n".join(out).strip()


def pdf_pages(path):
  data = Path(path).read_bytes()
  if not data.startswith(b"%PDF"):
    raise PdfError("not a pdf")
  if re.search(rb"/Encrypt\s+\d+\s+0\s+R", data):
    raise PdfError("encrypted /Encrypt")
  objs, order = _objs(data), []
  root = next((n for n, b in objs.items() if re.search(rb"/Type\s*/Catalog", b)), None)
  if root is not None:
    mp = re.search(rb"/Pages\s+(\d+)\s+0\s+R", objs[root])
    if mp:
      _walk(objs, int(mp.group(1)), {}, order)
  if not order:
    order = [(n, _fonts(objs, objs[n])) for n in sorted(objs)
        if re.search(rb"/Type\s*/Page\b", objs[n]) and b"/Kids" not in objs[n]]
  pages = []
  for k, (num, fonts) in enumerate(order, 1):
    body = objs.get(num, b"")
    mc = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", body, re.S)
    txt = []
    for cn in ([int(x) for x in re.findall(rb"(\d+)\s+0\s+R", mc.group(1))] if mc else []):
      cb = objs.get(cn, b"")
      txt.append(_ctext(_decode(cb, _stream(cb)), fonts))
    pages.append({"page": k, "text": _tidy("\n".join(txt)), "obj": num})
  if not pages:
    raise PdfError("no page objects")
  freq = {}
  for p in pages:
    for ln in set(p["text"].split("\n")):
      if 3 < len(ln.strip()) < 90:
        freq[ln.strip()] = freq.get(ln.strip(), 0) + 1
  noise = {s for s, c in freq.items() if c >= max(3, int(0.4 * len(pages)))} if len(pages) > 2 else set()
  for p in pages:
    ls = [ln for ln in p["text"].split("\n") if ln.strip() not in noise]
    while ls and re.fullmatch(r"\d{1,3}", ls[-1].strip()):
      ls.pop()
    p["text"] = "\n".join(ls).strip()
    p["chars"] = len(p["text"])
  return pages


def _xml(raw):
  s = raw.decode("utf-8", "ignore")
  s = re.sub(r"</(w|a|text):p>", "\n", s)
  s = re.sub(r"<(w|a):tab[^>]*/>", "\t", s)
  s = re.sub(r"<[^>]+>", "", s)
  for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
    s = s.replace(a, b)
  return _tidy(s)


def _docx(path):
  with zipfile.ZipFile(path) as z:
    names = sorted(n for n in z.namelist() if re.match(r"word/(document|footnotes)\d*\.xml", n))
    return _paginate("\n\n".join(_xml(z.read(n)) for n in names))


def _xlsx(path):
  with zipfile.ZipFile(path) as z:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
      sx = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
      for si in re.findall(r"<si>(.*?)</si>", sx, re.S):
        shared.append(re.sub(r"<[^>]+>", "", si).strip())
    rows = []
    for sh in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
      sx = z.read(sh).decode("utf-8", "ignore")
      for row in re.findall(r"<row[^>]*>(.*?)</row>", sx, re.S):
        vals = []
        for t, body in re.findall(r'<c[^>]*?(?:t="(\w+)")?[^>]*>(.*?)</c>', row, re.S):
          v = re.search(r"<v>(.*?)</v>", body, re.S)
          if not v:
            vals.append("")
          elif t == "s" and v.group(1).isdigit() and int(v.group(1)) < len(shared):
            vals.append(shared[int(v.group(1))])
          elif t != "s":
            vals.append(v.group(1))
          else:
            vals.append("")
        if any(x.strip() for x in vals):
          rows.append("\t".join(vals))
  return [{"page": 1, "text": _tidy("\n".join(rows))}]


def _paginate(txt, size=3200):
  pages, i, k = [], 0, 1
  while i < len(txt):
    cut = txt.find("\n\n", i + size)
    cut = len(txt) if cut < 0 else cut
    if txt[i:cut].strip():
      pages.append({"page": k, "text": txt[i:cut].strip()})
      k += 1
    i = cut
  return pages or [{"page": 1, "text": txt.strip()}]


def quality(text):
  n = len(text)
  if not n:
    return {"class": "empty", "score": 0.0, "chars": 0}
  alpha = sum(c.isalpha() for c in text)
  bad = sum(1 for c in text if ord(c) < 32 and c not in "\n\t") + text.count("\ufffd")
  words = re.findall(r"[A-Za-z]{2,}", text)
  sw = len(re.findall(r"\b(the|of|and|in|to|we|was|were|that|is|with)\b", text, re.I))
  per_k = 1000.0 * sw / max(1, len(words))
  sc = (0.45 * min(1.0, alpha / n * 1.6) + 0.35 * min(1.0, per_k / 22.0)
     + 0.20 * (1 - min(1.0, bad / n * 50)))
  if len(re.findall(r"[\u4e00-\u9fff]", text)) > n * 0.15:
    sc = max(sc, 0.8)
  cls = "good" if sc >= 0.62 else ("low_text" if sc >= 0.30 else "garbled")
  return {"class": cls, "score": round(sc, 3), "chars": n, "words": len(words),
      "stopword_per_k": round(per_k, 1)}


def read_document(path):
  p, ext, warn = Path(path), Path(path).suffix.lower(), []
  pages, kind = [], ext.lstrip(".") or "unknown"
  try:
    if ext == ".pdf":
      pages = pdf_pages(p)
    elif ext == ".docx":
      pages = _docx(p)
    elif ext in (".xlsx", ".xlsm"):
      pages = _xlsx(p)
    elif ext in (".csv", ".tsv"):
      raw = p.read_text(encoding="utf-8", errors="ignore")
      if ext == ".csv":
        try:
          raw = "\n".join("\t".join(r) for r in csv.reader(io.StringIO(raw)))
        except Exception:
          warn.append("csv_fallback")
      pages, kind = _paginate(raw, 4000), "csv"
    else:
      raw = p.read_text(encoding="utf-8", errors="ignore")
      if ext in (".html", ".htm"):
        raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
        raw = re.sub(r"<[^>]+>", " ", re.sub(r"</(p|div|h\d|li|tr)>", "\n", raw))
        kind = "html"
      if ext == ".json":
        try:
          raw = json.dumps(json.loads(raw), ensure_ascii=False, indent=1)
        except Exception:
          warn.append("json_fallback")
      pages = _paginate(_tidy(raw))
  except PdfError as e:
    warn.append("pdf_error:%s" % e)
  except Exception as e:
    warn.append("read_error:%s:%s" % (type(e).__name__, str(e)[:100]))
  txt = "\n\n".join(pg["text"] for pg in pages)
  q = quality(txt)
  if kind == "pdf" and q["class"] != "good":
    warn.append("pdf_text_quality:%s" % q["class"])
  return {"source_id": "", "path": str(p), "kind": kind, "pages": pages, "text": txt,
      "title": _title(pages), "warnings": warn, "quality": q}


def _title(pages):
  for ln in (pages[0]["text"].split("\n")[:12] if pages else []):
    s = ln.strip()
    if (12 <= len(s) <= 220 and sum(c.isalpha() for c in s) > len(s) * 0.55
        and not re.match(r"^(abstract|keywords|doi|arxiv|http|www)\b", s, re.I)):
      return s
  return (pages[0]["text"].split("\n")[0][:200] if pages and pages[0]["text"] else "")


HEAD_KINDS = [("abstract", r"abstract|summary|摘\s*要"), ("intro", r"introduction|background|motivation"),
       ("related", r"related work|literature review|prior work"),
       ("methods", r"method|material|experimental|procedure|approach|study design|participants|protocol"),
       ("results", r"result|finding|outcome|evaluation"), ("discussion", r"discussion|interpretation"),
       ("conclusion", r"conclusion|outlook|perspective"), ("limitation", r"limitation|caveat"),
       ("references", r"references|bibliography|works cited|参考文献"),
       ("ack", r"acknowledg|funding|author contribution|competing interest|conflict of interest"
           r"|data availability|supplementary")]
NUM_HEAD = re.compile(r"^(?P<n>(?:\d{1,2})(?:\.\d{1,2}){0,3})\.?\s+(?P<t>[A-Z][^.!?]{2,70})$")


def classify(title):
  for k, pat in HEAD_KINDS:
    if re.search(pat, title.strip().lower()):
      return k
  return "other"


def _heading(line):
  s = line.strip()
  if not 3 < len(s) <= 90:
    return None
  if s.endswith((".", ",", ";", ":")) and not re.match(r"^\d+(\.\d+)*\.?\s", s):
    return None
  m = NUM_HEAD.match(s)
  if m and s.count(" ") <= 12 and sum(c.isdigit() for c in s) < 6:
    return (m.group("t").strip(), m.group("n").count(".") + 1, m.group("n"))
  if re.match(r"^(abstract|introduction|related work|background|materials? and methods|methods?"
        r"|results?( and discussion)?|discussion|conclusions?|limitations?|references"
        r"|acknowledg(e)?ments?|supplementary (material|information)|keywords)$", s, re.I):
    return (s, 1, "")
  if s.isupper() and 4 <= len(s) <= 60 and sum(c.isalpha() for c in s) > len(s) * 0.6:
    return (s.title(), 1, "")
  return None


ABBR = re.compile(r"\b(e\.g|i\.e|et al|Fig|Figs|Tab|Eq|Eqs|vs|approx|ca|No|Dr|Prof|Sec|Ref|resp)\.", re.I)
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"'\u201c])|\n{2,}|(?<=[。！？])")


def split_sentences(text):
  t = ABBR.sub(lambda m: m.group(0)[:-1] + "\x01", text)
  t = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + "\x02" + m.group(2), t)
  return [p.replace("\x01", ".").replace("\x02", ".").strip()
      for p in SPLIT.split(t) if p and len(p.strip()) >= 12]


def _page_of(starts, off):
  return bisect.bisect_right(starts, off) if starts else 1


def build_index(doc):
  text, starts, pos = doc["text"], [], 0
  for pg in doc["pages"]:
    starts.append(pos)
    pos += len(pg["text"]) + 2
  heads, off = [], 0
  for ln in text.split("\n"):
    h = _heading(ln)
    if h and not (heads and off - heads[-1][0] < 60):
      heads.append((off, h[0], h[1], h[2]))
    off += len(ln) + 1
  secs = []
  if len(heads) >= 2:
    if heads[0][0] > 200:
      secs.append({"section_id": "S0", "title": "Front matter", "level": 1, "kind": "front",
            "start": 0, "end": heads[0][0], "num": ""})
    for k, (o, t, lv, num) in enumerate(heads):
      secs.append({"section_id": "S%d" % (len(secs) + 1), "title": t, "level": lv,
            "kind": classify(t), "start": o, "num": num,
            "end": heads[k + 1][0] if k + 1 < len(heads) else len(text)})
  else:
    secs = [{"section_id": "S1", "title": "Full text (no headings detected)", "level": 1,
        "kind": "other", "start": 0, "end": len(text), "num": ""}]
  parent = "other"
  for s in secs:
    nl = text.find("\n", s["start"])
    s["body"] = nl + 1 if 0 < nl < s["end"] else s["start"]
    s["text"] = text[s["body"]:s["end"]]
    s["page_start"] = _page_of(starts, s["start"])
    s["page_end"] = _page_of(starts, max(s["start"], s["end"] - 1))
    s["n_sent"] = len(split_sentences(s["text"]))
    if s["level"] <= 1:
      parent = s["kind"]
    elif s["kind"] == "other":
      s["kind"] = parent
  return {"text": text, "page_starts": starts, "sections": secs, "headings_found": len(heads)}


def main(argv=None):
  ap = argparse.ArgumentParser(prog="doctext.py", description="text extraction + heading segmenter inspector")
  ap.add_argument("file", nargs="?", help="pdf/docx/xlsx/csv/html/json/txt to inspect")
  ap.add_argument("--json", action="store_true", help="summary only")
  ap.add_argument("--preview", type=int, default=800, help="preview chars (default 800)")
  a = ap.parse_args(argv)
  if not a.file:
    ap.print_help()
    return 0
  fp = Path(a.file)
  if not fp.is_file():
    print("missing: %s" % fp)
    return 0
  doc = read_document(fp)
  ix = build_index(doc)
  print(json.dumps({"file": str(fp), "kind": doc["kind"], "pages": len(doc["pages"]),
           "chars": len(doc["text"]), "quality": doc["quality"], "title": doc["title"],
           "headings": ix["headings_found"], "warnings": doc["warnings"],
           "sections": [{"id": s["section_id"], "title": s["title"], "kind": s["kind"],
                  "pages": [s["page_start"], s["page_end"]], "sentences": s["n_sent"]}
                 for s in ix["sections"]]}, ensure_ascii=False, indent=1))
  if not a.json:
    print("--- preview ---\n" + doc["text"][:a.preview])
  return 0


if __name__ == "__main__":
  sys.exit(main())
