#!/usr/bin/env python3
"""reading-06 core: input discovery, paragraph index, evidence corpus, init/show."""
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, time, unicodedata, zipfile, zlib
from datetime import datetime, timezone
from pathlib import Path

V = "2.0.0"
ST = ("reported", "not_reported", "source_conflict", "extraction_failed")
CFG = {"case.json", "target-fields.json", "task.md", "output-contract.md", "output_contract.json",
       "public-manifest.json", "resources.yaml", "resources.yml", "result.json",
       "extraction.json", "extraction.csv", "extraction.md", "index.json", "paragraphs.json",
       "draft.json", "check_report.json"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PREF = {"ok": ("ok", "answered", "success", "complete"), "partial": ("partial", "incomplete"),
        "insufficient_evidence": ("insufficient_evidence", "insufficient"),
        "input_error": ("input_error", "error")}
CHUNK, MAXP = 1800, 6000


def ts():
 return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(p, o):
 p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
 p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dec(b):
 if b.startswith(b"\xef\xbb\xbf"): return b[3:].decode("utf-8", "replace")
 if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
  try: return b.decode("utf-16")
  except Exception: pass
 for e in ("utf-8", "gb18030", "big5", "latin-1"):
  try: return b.decode(e)
  except Exception: pass
 return b.decode("utf-8", "replace")


def jload(p):
 t = dec(Path(p).read_bytes()).replace("\x00", "").lstrip("\ufeff").strip()
 for c in (t, re.sub(r",(\s*[}\]])", r"\1", t)):
  try: return json.loads(c)
  except Exception: pass
 raise ValueError("bad json: %s" % p)


def norm(s, lv="loose"):
 s = unicodedata.normalize("NFKC", str(s)).replace("\u00ad", "").replace("\u2011", "-")
 s = re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s)).strip()
 if lv == "strict": return s
 s = s.casefold()
 return s if lv == "normalized" else re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s)


def sha(p):
 with open(p, "rb") as f: return hashlib.sha1(f.read(4 << 20)).hexdigest()[:16]


def sniff(p):
 e = p.suffix.lower().lstrip(".")
 try: h = p.read_bytes()[:16]
 except Exception: h = b""
 if h.startswith(b"%PDF"): return "pdf"
 if h.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"II*\x00", b"MM\x00*", b"RIFF")): return "image"
 if h.startswith(b"PK\x03\x04"):
  try: n = zipfile.ZipFile(p).namelist()
  except Exception: n = []
  for pre, k in (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx")):
   if any(x.startswith(pre) for x in n): return k
  return "zip"
 return {"json": "json", "jsonl": "json", "csv": "csv", "tsv": "tsv", "md": "md", "markdown": "md",
         "xlsx": "xlsx", "xlsm": "xlsx", "docx": "docx", "pdf": "pdf", "txt": "txt", "text": "txt",
         "xml": "txt", "yaml": "txt", "yml": "txt", "tex": "txt", "html": "txt"}.get(e, "binary")


def pstr(s):
 out, i = [], 0
 while i < len(s):
  c = s[i]
  if c == "\\" and i + 1 < len(s):
   n = s[i + 1]
   if n in "()\\": out.append(n); i += 2; continue
   if n == "n": out.append("\n"); i += 2; continue
   if n in "rt": out.append(" "); i += 2; continue
   m = re.match(r"[0-7]{1,3}", s[i + 1:])
   if m: out.append(chr(int(m.group(0), 8))); i += 1 + len(m.group(0)); continue
   i += 2; continue
  out.append(c); i += 1
 return "".join(out)


def pdf_ops(s):
 out = []
 for m in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]|\\.)*\]\s*TJ|T\*|Td|TD|ET", s):
  g = m.group(0)
  if g[0] == "(": out.append(pstr(g[1:g.rfind(")")]))
  elif g[0] == "[": out.append("".join(pstr(x[1:-1]) for x in re.findall(r"\((?:\\.|[^\\()])*\)", g)))
  else: out.append("\n")
 return "".join(out)


def pdf_std(p):
 d, out = p.read_bytes(), []
 for m in re.finditer(rb"stream\r?\n", d):
  e = d.find(b"endstream", m.end())
  if e < 0: continue
  raw = d[m.end():e]
  try: raw = zlib.decompress(raw)
  except Exception: pass
  if b"Tj" in raw or b"TJ" in raw: out.append(pdf_ops(raw.decode("latin-1")))
 return "\n".join(out)


def zip_t(p):
 import xml.etree.ElementTree as ET
 with zipfile.ZipFile(p) as z:
  n = z.namelist()
  if not any(x.startswith("xl/") for x in n):
   part = "word/document.xml" if "word/document.xml" in n else (n[0] if n else "")
   x = z.read(part).decode("utf-8", "replace") if part else ""
   return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "\n", x))
  sh = ["".join(t.text or "" for t in si.iter(S + "t")) for si in
        ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si")] if "xl/sharedStrings.xml" in n else []
  out = []
  for f in sorted(x for x in n if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
   for row in ET.fromstring(z.read(f)).iter(S + "row"):
    cs = []
    for c in row.iter(S + "c"):
     v, t = c.find(S + "v"), ""
     if v is not None and v.text:
      t = sh[int(v.text)] if c.get("t") == "s" and v.text.isdigit() and int(v.text) < len(sh) else v.text
     if not t:
      i = c.find(S + "is"); t = "" if i is None else "".join(x.text or "" for x in i.iter(S + "t"))
     if t.strip(): cs.append("%s=%s" % (c.get("r", ""), t.strip()))
    if cs: out.append("[%s] %s" % (Path(f).stem, " | ".join(cs)))
  return "\n\n".join(out)


def text_of(p, k, deg):
 if k == "pdf":
  if shutil.which("pdftotext"):
   try:
    r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=120)
    if r.returncode == 0 and r.stdout.strip(): return r.stdout.decode("utf-8", "replace"), "pdftotext"
   except Exception: pass
  t = pdf_std(p)
  if t.strip(): deg.append("pdf_stdlib:%s:pages_unknown" % p.name); return t, "stdlib-zlib"
  deg.append("pdf_no_text_layer:%s" % p.name); return "", "none"
 if k in ("docx", "xlsx"):
  try: return zip_t(p), k + "-xml"
  except Exception: deg.append("%s_failed:%s" % (k, p.name)); return "", "none"
 if k in ("json", "md", "txt", "csv", "tsv"):
  try: t = dec(p.read_bytes())
  except Exception: deg.append("read_failed:%s" % p.name); return "", "none"
  if k in ("csv", "tsv"):
   try:
    rows = list(csv.reader(t.splitlines(), delimiter="\t" if k == "tsv" else ","))
    return "\n\n".join(" | ".join(c.strip() for c in r) for r in rows if any(r)), "csv"
   except Exception: return t, "csv"
  return t, "text"
 deg.append("no_text_extractor:%s:%s" % (p.name, k)); return "", "none"



def sents(t):
 """Sentence split that does not break decimals like 12.4."""
 return [x for x in re.split(r"(?<=[。！？；])|(?<=[.!?;])\s+(?=[A-Z\u4e00-\u9fff（(\"'])|\s*\n\s*", t) if x and x.strip()]


def jl(a, b):
 if not a: return b
 if not b: return a
 if re.search(r"[\u4e00-\u9fff]$", a) and re.match(r"^[\u4e00-\u9fff（(]", b): return a + b
 return a[:-1] + b if (a.endswith("-") and re.match(r"^[a-z]", b)) else a + " " + b


def split_long(b, size=CHUNK):
 if len(b) <= size: return [b]
 parts, buf = [], ""
 for s in sents(b):
  if not s: continue
  if len(buf) + len(s) > size and buf: parts.append(buf.strip()); buf = s
  else: buf = jl(buf, s)
 if buf.strip(): parts.append(buf.strip())
 out = []
 for p in parts:
  while len(p) > 2 * size: out.append(p[:size]); p = p[size:]
  out.append(p)
 return [x for x in out if x.strip()]


def segment(t, mid):
 ps, i = [], 0
 pages = t.split("\f")
 for pno, page in enumerate(pages, 1):
  lines = page.splitlines()
  if not page.strip(): continue
  blocks, buf = [], []
  if sum(1 for l in lines if not l.strip()) / max(1, len(lines)) < 0.04 and len(lines) > 25:
   blocks = split_long(" ".join(l.strip() for l in lines if l.strip())); lines = []
  for l in lines:
   if l.strip(): buf.append(l.strip())
   elif buf: blocks.append((" " if buf[0].isascii() else "").join(buf)); buf = []
  if buf: blocks.append((" " if buf[0].isascii() else "").join(buf))
  for b in blocks:
   for piece in split_long(b):
    i += 1
    ps.append({"pid": "%s-p%04d" % (mid, i), "material_id": mid,
               "page": pno if len(pages) > 1 else None, "text": piece})
 return ps


def findx(root, *names):
 for n in names:
  p = Path(root) / n
  if p.is_file(): return p
  h = sorted(Path(root).rglob(n))
  if h: return h[0]
 return None


def norm_field(f, i):
 d = {"field_id": None, "label": "", "description": "", "aliases": []}
 if isinstance(f, dict):
  for k in ("field_id", "id", "key", "field"):
   if f.get(k) not in (None, ""): d["field_id"] = str(f[k]); break
  for k in ("label", "name", "title", "field_label", "question", "description", "definition"):
   if isinstance(f.get(k), str) and f[k].strip(): d["label"] = f[k].strip(); break
  for k in ("description", "definition", "instruction", "question", "note"):
   if isinstance(f.get(k), str) and f[k].strip() and f[k].strip() != d["label"]:
    d["description"] = f[k].strip(); break
  for k in ("aliases", "keywords", "synonyms", "unit", "expected_unit"):
   v = f.get(k)
   if isinstance(v, str): d["aliases"].append(v)
   elif isinstance(v, list): d["aliases"] += [str(x) for x in v if isinstance(x, (str, int, float))]
 else: d["label"] = str(f)
 d["field_id"] = d["field_id"] or "F%02d" % (i + 1)
 d["label"] = d["label"] or d["field_id"]
 return d


def load_fields(case, root):
 cand = [findx(root, "target-fields.json")]
 for k in ("target_fields", "target-fields", "fields", "field_spec", "extraction_fields"):
  if isinstance(case.get(k), (list, dict)): cand.insert(0, case[k])
 for c in cand:
  if c is None: continue
  try: d = c if isinstance(c, (list, dict)) else jload(c)
  except Exception: continue
  if isinstance(d, dict):
   for k in ("target_fields", "fields", "items", "targets", "field_list", "data"):
    if isinstance(d.get(k), (list, dict)): d = d[k]; break
   else:
    if d and all(isinstance(v, dict) for v in d.values()):
     d = [dict(v, field_id=v.get("field_id") or k) for k, v in d.items()]
  if isinstance(d, list):
   fs = [norm_field(f, i) for i, f in enumerate(d) if isinstance(f, (str, dict))]
   if fs: return fs
 return []


def build_index(indir, work, deg, err):
 root = Path(indir)
 cp, case = findx(root, "case.json", "case*.json"), {}
 if cp:
  try:
   case = jload(cp)
   if not isinstance(case, dict): case = {}; err.append("case.json is not an object")
  except Exception as e: err.append("case.json unreadable: %s" % e)
 fields = load_fields(case, root)
 files = []
 if root.is_dir():
  for dp, dn, fn in os.walk(root):
   dn[:] = [d for d in dn if not d.startswith(".") and d != "__pycache__"]
   files += [Path(dp) / f for f in sorted(fn)]
   if len(files) > 400: break
 mats, allp = [], {}
 for p in files:
  if p.name in CFG or p.name.startswith(".") or not p.is_file(): continue
  k = sniff(p); mid = "M%d" % (len(mats) + 1)
  t, how = text_of(p, k, deg)
  ps = segment(t, mid) if t.strip() else []
  if len(ps) > MAXP: deg.append("paragraph_cap:%s" % p.name); ps = ps[:MAXP]
  mats.append({"material_id": mid, "name": p.name, "path": str(p), "kind": k,
               "bytes": p.stat().st_size if p.exists() else None, "sha1": sha(p), "extractor": how,
               "paragraphs": len(ps)})
  allp[mid] = ps
 idx = {"skill_version": V, "built_at": ts(), "input_root": str(root),
        "case_path": str(cp) if cp else None, "case_id": case.get("case_id") or case.get("id") or None,
        "task_instruction": case.get("task_instruction") or case.get("instruction") or "",
        "output_contract": case.get("output_contract") or {}, "source": case.get("source") or {},
        "workorder": {k: case[k] for k in ("organizer_supplied_scope", "organizer_workorder",
                                           "organizer_edit_workorder", "formal_inputs", "runtime_files",
                                           "task_specific_interface") if case.get(k)},
        "fields": fields, "materials": mats, "errors": err, "degradations": deg}
 dump(Path(work) / "index.json", idx); dump(Path(work) / "paragraphs.json", allp)
 return idx, mats, fields


def load_index(work):
 return jload(Path(work) / "index.json"), jload(Path(work) / "paragraphs.json")


def corpus(ps):
 c = {k: [] for k in ("strict", "normalized", "loose")}
 for mid in sorted(ps):
  for p in ps[mid]:
   for k in c: c[k].append(norm(p.get("text", ""), k))
 return {k: "\n".join(v) for k, v in c.items()}


def vq(q, corp):
 for lv in ("strict", "normalized", "loose"):
  n = norm(q, lv)
  if len(n) >= 6 and n in corp[lv]: return lv
 return None


def blank_result(idx, status, note):
 c = idx.get("output_contract") or {}
 o = {k: ([] if re.search(r"s$|list", k) else None) for k in (c if isinstance(c, dict) else {})}
 o.update({"case_id": idx.get("case_id"), "status": status, "sources": [], "uncertainty": [note],
           "pending_human": [], "errors": list(idx.get("errors") or []),
           "degradations": list(idx.get("degradations") or []),
           "changes": [{"at": ts(), "action": "partial_result", "detail": note}],
           "runtime": {"skill_version": V, "phase": "init"}})
 return o


def cmd_init(a):
 wk, out = Path(a.work), Path(a.output)
 wk.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
 dump(out / "result.json", blank_result({"output_contract": {}, "errors": ["index pending"]},
                                        "partial", "init: index not built yet"))
 deg, err = [], []
 idx, mats, fields = build_index(a.input, wk, deg, err)
 dump(out / "result.json", blank_result(idx, "partial", "init: index built, extraction pending"))
 w = ["# Workorder", "", "case_id: `%s`" % idx.get("case_id"), "", "## Task instruction", "",
      (idx.get("task_instruction") or "(none)").strip(), ""]
 if idx.get("workorder"):
  w.append("## Organizer workorder")
  for k, v in idx["workorder"].items(): w.append("- **%s**: %s" % (k, json.dumps(v, ensure_ascii=False)[:700]))
  w.append("")
 w += ["## Target fields (%d)" % len(fields), "", "| field_id | label | description |", "|---|---|---|"]
 w += ["| %s | %s | %s |" % (f["field_id"], f["label"].replace("|", "/"),
                             (f["description"] or "").replace("|", "/")[:140]) for f in fields]
 w += ["", "## Materials", "", "| id | name | kind | bytes | extractor | paragraphs |", "|---|---|---|---|---|---|"]
 w += ["| %s | %s | %s | %s | %s | %s |" % (m["material_id"], m["name"], m["kind"], m["bytes"],
                                            m["extractor"], m["paragraphs"]) for m in mats]
 w += ["", "## Output contract keys", "", "`%s`" % "`, `".join((idx.get("output_contract") or {})), "",
       "Next: `show` -> write %s/draft.json -> `check` -> `build`" % wk, ""]
 (wk / "workorder.md").write_text("\n".join(w), encoding="utf-8")
 print("== init ==\ninput: %s\ncase_id: %s\ncontract keys: %s\n-> %s/result.json (partial), %s/workorder.md"
       % (idx["input_root"], idx.get("case_id"), ", ".join((idx.get("output_contract") or {})), out, wk))
 print("materials=%d target_fields=%d" % (len(mats), len(fields)))
 for m in mats:
  print("  %-4s %-34s %-6s paras=%-4d %s" % (m["material_id"], m["name"][:34], m["kind"],
                                              m["paragraphs"], m["extractor"]))
 for f in fields: print("  field %-10s %s" % (f["field_id"], f["label"][:70]))
 for x in err + deg: print("  note: %s" % x)
 return 0


def cmd_show(a):
 idx, ps = load_index(a.work)
 pat = re.compile(a.grep, re.I) if a.grep else None
 n = 0
 for mid in sorted(ps):
  if a.material and mid != a.material: continue
  for p in ps[mid]:
   if a.para and p["pid"] != a.para: continue
   t = p.get("text", "")
   if pat and not pat.search(t): continue
   print("%s [%s p%s] %s" % (p["pid"], mid, p.get("page") or "?",
                             t if len(t) <= a.max_chars else t[:a.max_chars] + " …"))
   n += 1
   if n >= a.limit: return print("-- truncated at %d --" % n) or 0
 print("-- %d paragraph(s) --" % n)
 return 0



def rows_of(d):
 r = []
 if isinstance(d, list): r = d
 elif isinstance(d, dict):
  for k in ("fields", "field_results", "extractions", "results", "items", "rows", "data"):
   v = d.get(k)
   if isinstance(v, list): r = v; break
   if isinstance(v, dict):
    r = [dict(x, field_id=x.get("field_id") or kk) if isinstance(x, dict) else {"field_id": kk, "value": x}
         for kk, x in v.items()]
    break
  if not r and d and all(isinstance(v, dict) for v in d.values()):
   r = [dict(v, field_id=v.get("field_id") or k) for k, v in d.items() if "value" in v or "status" in v]
 return [x for x in r if isinstance(x, dict)]


def pk(d, ks, dflt=""):
 for k in ks:
  if k and k in d and d[k] not in (None, ""): return d[k]
 return dflt


def load_draft(w):
 w = Path(w)
 cand = ([w / "draft.json"] if (w / "draft.json").is_file() else []) + \
        [f for f in sorted(w.glob("*.json")) if f.name not in
         ("index.json", "paragraphs.json", "check_report.json", "draft.json")] + \
        [f for f in sorted(w.glob("*.md")) if f.name != "workorder.md"]
 for f in cand:
  try:
   if f.suffix == ".json":
    d = jload(f); r = rows_of(d)
    if r:
     ex = {k: d.get(k) for k in ("uncertainties", "pending_human")
           if isinstance(d, dict) and d.get(k)}
     return r, {"path": str(f), "claims": d.get("claims") if isinstance(d, dict) else None, "extra": ex}
   else:
    r = md_rows(f.read_text(encoding="utf-8", errors="replace"))
    if r: return r, {"path": str(f), "claims": None, "extra": {}}
  except Exception: continue
 return [], {}


def md_rows(t):
 ls = [x for x in t.splitlines() if x.strip().startswith("|")]
 if len(ls) < 3: return []
 cells = lambda x: [y.strip() for y in x.strip().strip("|").split("|")]
 head = [y.lower() for y in cells(ls[0])]
 def g(r, *ns):
  for n in ns:
   for i, h in enumerate(head):
    if n in h and i < len(r): return r[i]
  return ""
 out = [{"field_id": g(r, "field_id", "id"), "label": g(r, "label", "字段"), "status": g(r, "status"),
         "value": g(r, "value", "值"), "unit": g(r, "unit"), "condition": g(r, "condition", "条件"),
         "comparator": g(r, "comparator"), "quote": g(r, "quote", "证据"),
         "locator": g(r, "locator", "定位"), "reasoning": g(r, "reasoning", "依据")}
        for r in (cells(l) for l in ls[2:] if not re.match(r"^\|[\s:\-|]+\|$", l.strip()))]
 return [x for x in out if x["field_id"] or x["value"]]

def add_common(x):
 for k, d in (("input", "/input"), ("work", "/app/work"), ("output", "/app/output")):
  x.add_argument("--" + k, default=os.environ.get("SKILL_" + k.upper(), d))


def parser(prog="main.py", sub=("init", "show", "check", "build", "audit")):
 p = argparse.ArgumentParser(prog=prog, description="reading-06 literature field extraction")
 p.add_argument("--version", action="version", version=V)
 sp = p.add_subparsers(dest="cmd")
 if "init" in sub:
  add_common(sp.add_parser("init", help="scan input, index paragraphs, write partial result.json"))
 if "show" in sub:
  s = sp.add_parser("show", help="print paragraphs with locators")
  add_common(s)
  s.add_argument("--grep", default=None, help="case-insensitive regex")
  s.add_argument("--material", default=None, help="material id (M1)")
  s.add_argument("--para", default=None, help="paragraph id (M1-p0012)")
  s.add_argument("--limit", type=int, default=60)
  s.add_argument("--max-chars", type=int, default=1200)
 if "check" in sub: add_common(sp.add_parser("check", help="validate draft coverage/status/quotes"))
 if "build" in sub:
  b = sp.add_parser("build", help="write extraction.* and result.json (+ the five audit assets)")
  add_common(b)
  b.add_argument("--no-audit", action="store_true",
                 help="skip golden_standard/diff_report/self_check/run.log (v1 behaviour)")
 if "audit" in sub:
  add_common(sp.add_parser("audit", help="recompute the five audit assets from existing outputs"))
 return p


def forward(cmd, argv, script="build.py"):
 """Run a subcommand implemented in build.py (or audit.py) with the same interpreter."""
 try:
  r = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve().parent / script), cmd] + argv,
                     timeout=600)
  return r.returncode
 except Exception as e:
  print("forward failed: %s" % e); return 0


def _arg(argv, name, dflt):
 for i, x in enumerate(argv):
  if x == name and i + 1 < len(argv): return argv[i + 1]
  if x.startswith(name + "="): return x.split("=", 1)[1]
 return os.environ.get("SKILL_" + name.lstrip("-").upper(), dflt)


def _warg(argv):
 return _arg(argv, "--work", "/app/work")


def main(argv=None):
 """Entry point: dispatch, then append one real run event (never changes the exit code)."""
 argv = list(sys.argv[1:] if argv is None else argv)
 t0 = time.time()
 rc = _main(argv)
 try:
  if os.environ.get("SKILL_NOLOG") == "1":
   raise StopIteration
  import audit as _au
  _au.rec(_warg(argv), argv[0] if argv and not argv[0].startswith("-") else "help", rc,
          (time.time() - t0) * 1000.0, argv=argv)
  out = Path(_arg(argv, "--output", "/app/output"))
  rj = None
  try: rj = jload(out / "result.json")
  except Exception: pass
  _au.write_run_log(out, _warg(argv), rj)
 except Exception:
  pass
 return rc


def _main(argv):
 try: a = parser().parse_args(argv)
 except SystemExit as e: return int(e.code or 0)
 if not a.cmd: parser().print_help(); return 0
 if a.cmd in ("check", "build"): return forward(a.cmd, argv[argv.index(a.cmd) + 1:])
 if a.cmd == "audit": return forward("assets", argv[argv.index(a.cmd) + 1:], "audit.py")
 try: return {"init": cmd_init, "show": cmd_show}[a.cmd](a) or 0
 except Exception as e:
  print("error in %s: %s" % (a.cmd, e))
  args = []
  for k, d in (("input", "/input"), ("work", "/app/work"), ("output", "/app/output")):
   args += ["--" + k, getattr(a, k, d)]
  return forward("build", args)


if __name__ == "__main__":
 sys.exit(main())
