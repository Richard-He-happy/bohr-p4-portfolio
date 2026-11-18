#!/usr/bin/env python3
# audit.py - review-04 scaffold: parse inputs, locate sentences, emit unadjudicated leads,
# write a legal PARTIAL result.json first, then digest + issues_draft.json + .audit/index.json.
# Stdlib only, no network, CWD-independent. Exit code always 0.
import argparse, bisect, json, re, sys, time, unicodedata, zipfile, zlib
from datetime import datetime
from html import unescape
from pathlib import Path
V = "1.0.0"
T0 = time.time()
CATS = ["factual", "citation", "method", "statistics", "argument", "compliance"]
SKIP = {"__pycache__", "node_modules", ".git", ".audit"}
STOP = set("the a an and or of to in for on with by as at is are was were be this that these those we our study paper "
 "results data method conclusion significant difference based also can may show shown provide present suggest table "
 "figures fig doi all any both more most other some such only group effect level increase among".split())
TXT = {".md", ".markdown", ".tex", ".txt", ".csv", ".tsv", ".json", ".bib", ".ris", ".html", ".htm", ".yaml", ".yml"}
def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def norm(s):
 s = unicodedata.normalize("NFKC", str(s)).replace("\u00ad", "").replace("\u2019", "'")
 return re.sub(r"\s+", " ", s.replace("\u201c", '"').replace("\u201d", '"')).strip()
def wj(p, o):
 p.parent.mkdir(parents=True, exist_ok=True)
 t = p.with_suffix(p.suffix + ".tmp")
 t.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
 t.replace(p)
UNESC = ((b"\\(", b"("), (b"\\)", b")"), (b"\\\\", b"\\"), (b"\\n", b"\n"), (b"\\r", b""), (b"\\t", b" "))
def ctext(cs):
 def dec(s):
  for a, b in UNESC: s = s.replace(a, b)
  return s.decode("utf-8", "replace")
 out, i, n = [], 0, len(cs)
 while i < n:
  c = cs[i]
  if c == 92: i += 2; continue
  if c == 40:
   depth, j, buf = 1, i + 1, bytearray()
   while j < n and depth:
    b = cs[j]
    if b == 92: buf += cs[j:j + 2]; j += 2; continue
    if b == 40: depth += 1
    elif b == 41:
     depth -= 1
     if not depth: break
    buf.append(b); j += 1
   out.append(dec(bytes(buf))); i = j + 1; continue
  if c == 60 and cs[i:i + 2] != b"<<":
   j = cs.find(b">", i)
   if j > 0:
    try: out.append(bytes.fromhex(re.sub(rb"\s", b"", cs[i + 1:j]).decode()).decode("utf-16-be", "replace"))
    except ValueError: pass
    i = j + 1; continue
  if cs[i:i + 2] in (b"T*", b"Td", b"TD", b"ET"): out.append("\n")
  i += 1
 return "".join(out)
def read_pdf(p):
 d, w, ch = p.read_bytes(), [], []
 npg = len(re.findall(rb"/Type\s*/Page[^s]", d))
 for m in re.finditer(rb"(?<![A-Za-z])stream(\r\n|\r|\n)", d):
  e = d.find(b"endstream", m.end())
  if e < 0: continue
  raw, buf = d[m.end():e], None
  for t in (raw, raw.rstrip(b"\r\n")):
   try: buf = zlib.decompressobj().decompress(t) or None
   except zlib.error: continue
   if buf: break
  if buf is None:
   if b"BT" not in raw or b"Tj" not in raw: continue
   buf = raw
  t = ctext(buf)
  if t.strip(): ch.append(t)
 txt = "\f".join(ch) if (npg and len(ch) == npg) else "\n".join(ch)
 if not ch: w.append("no decodable content stream (image-only/encrypted PDF)")
 elif len(txt.strip()) < 200: w.append("text layer under 200 chars (possible scan, OCR needed)")
 return txt, {"pages": npg or None}, w
def read_docx(p):
 with zipfile.ZipFile(p) as z:
  if "word/document.xml" not in z.namelist(): return "", {}, ["word/document.xml missing"]
  x = z.read("word/document.xml").decode("utf-8", "replace")
 return unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", x))), {}, []
def read_txt(p):
 b = p.read_bytes()
 for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
  try: return b.decode(enc), {}, []
  except UnicodeDecodeError: pass
 return b.decode("utf-8", "replace"), {}, ["decoded with replacement chars"]
def load(p, cap=400000):
 ext = p.suffix.lower()
 if ext in TXT: txt, meta, w = read_txt(p)
 elif ext == ".pdf": txt, meta, w = read_pdf(p)
 elif ext == ".docx": txt, meta, w = read_docx(p)
 else: return {"path": str(p), "kind": ext.lstrip(".") or "bin", "text": "", "meta": {}, "chars": 0,
  "warn": ["binary/table/image not parsed; its content is a stated evidence gap"]}
 if len(txt) > cap:
  w = w + ["truncated at %d chars (source had %d)" % (cap, len(txt))]
  txt = txt[:cap]
 return {"path": str(p), "kind": ext.lstrip(".") or "txt", "text": txt, "meta": meta, "warn": w, "chars": len(txt)}
SEC = re.compile(r"^(?:\d{1,2}(?:\.\d{1,3}){0,3}[.)]?\s*)?(abstract|summary|introduction|background|related\s+work|"
 r"literature\s+review|materials?\s+and\s+methods?|methods?|methodology|results?(?:\s+and\s+discussion)?|"
 r"discussion|conclusions?|limitations?|references?|bibliography|acknowledge?ments?|supplementary|appendix|"
 r"摘要|引言|前言|研究背景|材料与方法|方法与材料|方法|结果(?:与分析)?|讨论|结论|局限(?:性)?|参考文献|致谢|附录)$", re.I)
CMAP = ("abstract=Abstract|摘要=Abstract|introduction=Introduction|引言=Introduction|前言=Introduction|"
 "background=Introduction|背景=Introduction|related=Related Work|literature=Related Work|method=Methods|"
 "material=Methods|方法=Methods|experimental=Methods|result=Results|结果=Results|discussion=Discussion|讨论=Discussion|"
 "conclusion=Conclusion|结论=Conclusion|limitation=Limitations|reference=References|bibliograph=References|"
 "参考文献=References|ack=Acknowledgments|致谢=Acknowledgments|appendix=Appendix|附录=Appendix")
ABBRX = re.compile(r"(?:\bet al|e\.g|i\.e|fig|figs|tab|vs|cf|eq|ref|no|vol|pp|approx|ca)\.$", re.I)
def canon(s):
 s = re.sub(r"\s+", " ", s.strip().lower())
 for kv in CMAP.split("|"):
  k, v = kv.split("=")
  if k in s: return v
 return s[:40] or "Front"
def sents(txt):
 out, i, n, b = [], 0, len(txt), 0
 while i < n:
  if txt[i] in ".!?。！？":
   j = i + 1
   while j < n and txt[j] in "\"'”’)]」』": j += 1
   if j >= n or txt[j] in " \n\t\f":
    if not (ABBRX.search(txt[max(0, i - 25):i + 1]) or (i + 1 < n and txt[i].isdigit() and txt[i + 1].isdigit())
     or len(txt[b:i].strip()) < 3):
     out.append((b, i + 1))
     k = j
     while k < n and txt[k] in " \n\t\f": k += 1
     b = i = k
     continue
  i += 1
 if txt[b:].strip(): out.append((b, n))
 return out
def segment(text):
 po, lines, o = [], [], 0
 if "\f" in text:
  for part in text.split("\f"):
   po.append(o); o += len(part) + 1
 o = 0
 for ln in text.split("\n"):
  lines.append((o, ln)); o += len(ln) + 1
 sec, cur, paras, buf = [], "Front", [], []
 for i, (_, ln) in enumerate(lines):
  t = ln.strip()
  if t:
   if 3 < len(t) <= 90 and not t.endswith((",", ";")):
    m = SEC.match(t) or SEC.match(re.sub(r"^[#>*\s]+|[*#\s:]+$", "", t)) or \
     re.match(r"\\(?:sub)?section\*?\{\s*(.{2,40}?)\}", t)
    if m: cur = canon(m.group(1))
   buf.append(i)
  elif buf:
   paras.append(buf); buf = []
  sec.append(cur)
 if buf: paras.append(buf)
 segs, k = [], 0
 for pi, idx in enumerate(paras, 1):
  st = lines[idx[0]][0]
  blk = text[st:lines[idx[-1]][0] + len(lines[idx[-1]][1])]
  for a, b in sents(blk):
   body = blk[a:b].strip()
   if len(body) > 1:
    k += 1
    segs.append({"sid": "S%04d" % k, "section": sec[idx[0]], "para": pi, "text": body,
     "page": bisect.bisect_right(po, st + a) if po else None, "start": st + a, "end": st + b})
 return segs
RULES = [
 (r"\bTODO\b|\bTBD\b|\bXXX+\b|\[\?\]|\?\?|待补|待定", "compliance", "major", "high", 1, "compliance:clean",
  "未清理的占位符/待补文本"),
 (r"\bp\s*[=<≤]\s*0?\.0{2,3}\b", "statistics", "minor", "high", 1, "statistics:reporting", "p 值报为 0.000"),
 (r"significan|显著", "statistics", "minor", "low", 0, "statistics:reporting", "显著性措辞，需核对统计量"),
 (r"±", "statistics", "suggestion", "low", 0, "statistics:reporting", "± 未说明 SD 还是 SE"),
]
BR = re.compile(r"\[(\d{1,3}(?:\s*[-–—,]\s*\d{1,3})*)\]")
CAUSAL = re.compile(r"\b(cause[sd]?|leads? to|led to|results? in|resulted in|drives?|induces?|determines?|attributable "
 r"to|due to|accounts? for|improves?|improved|reduces?|reduced|increases?|increased)\b|导致|造成|引起|决定|归因于|改善|提高|降低", re.I)
DESIGN = re.compile(r"\b(randomi[sz]\w+|randomly assign\w*|intervention|manipulat\w+|knock\w*|ablat\w*|treated with|"
 r"transfect\w*|crossover|placebo|sham|experimental group|control group)\b|随机|干预|敲除|转染|处理组|对照组", re.I)
CLAIM = re.compile(r"\b(therefore|thus|hence|these (?:results|findings|data)|our (?:results|findings|data)|we (?:show|"
 r"showed|demonstrate|demonstrated|found|find|conclude|concluded)|this (?:study|work|paper) (?:shows|demonstrates|"
 r"provides|suggests|reveals)|indicat\w+|suggest\w+|reveal\w+|confirm\w+)\b|因此|因而|表明|说明|证明|证实|提示", re.I)
PROMISE = re.compile(r"\b(we (?:aim|aimed|investigate|investigated|examine|examined|test|tested|address|explore|"
 r"quantif\w+)|this (?:study|paper|work) (?:aims?|investigates?|examines?|addresses?)|the (?:aim|goal|objective) of "
 r"(?:this|our))\b|本研究(?:旨在|拟|试图|考察|检验|探讨)|研究目的", re.I)
PVAL = re.compile(r"\bp\s*[=<>≤≥]", re.I)
def cited(segs):
 got = {}
 for s in segs:
  if s["section"] == "References": continue
  for m in BR.finditer(s["text"]):
   for p in re.split(r"[,\s]+", m.group(1)):
    if p.isdigit(): got.setdefault(int(p), 1)
    elif re.match(r"^\d+[-–—]\d+$", p):
     a, b = re.split(r"[-–—]", p)
     if int(b) - int(a) <= 60:
      for x in range(int(a), int(b) + 1): got.setdefault(x, 1)
 return got
def leads(segs):
 out = []
 def add(cat, sev, s, msg, conf="medium", hard=0, item="", hit=""):
  out.append({"category": cat, "severity": sev, "sid": s["sid"], "section": s["section"], "page": s["page"],
   "rule": item.replace(":", "."), "quote": s["text"][:400],
   "detail": msg + (("；触发 %s" % hit[:40]) if hit else ""), "confidence": conf, "hard": bool(hard),
   "check_item": item})
 body = [s for s in segs if s["section"] != "References"]
 allt = " ".join(s["text"] for s in segs)
 for s in body:
  for rx, cat, sev, conf, hard, item, msg in RULES:
   m = re.search(rx, s["text"], re.I)
   if m and not (rx.startswith("significan") and PVAL.search(s["text"])):
    add(cat, sev, s, msg, conf, hard, item, m.group(0))
  if CAUSAL.search(s["text"]) and not DESIGN.search(allt):
   add("argument", "major", s, "因果措辞，全文无实验/随机化设计", "medium", 0, "argument:strength")
  if (s["section"] in ("Results", "Discussion", "Conclusion") and CLAIM.search(s["text"])
   and not (BR.search(s["text"]) or re.search(r"\d|表\s*\d|图\s*\d", s["text"]))):
   add("argument", "minor", s, "结论句内无数据也无引用，支撑不可见", "low", 0, "argument:support")
 nums = set(int(m.group(1)) for s in segs if s["section"] == "References"
  for m in re.finditer(r"^\s*\[?(\d{1,3})[\]\.\)]?\s+\S", s["text"]))
 if nums and cited(segs):
  mx = max(nums)
  for s in body:
   bad = [p for m in BR.finditer(s["text"]) for p in re.split(r"[,\s]+", m.group(1))
    if p.isdigit() and int(p) > mx]
   if bad:
    add("citation", "major", s, "引用编号 [%s] 超出文献表最大编号 %d" % (bad[0], mx), "high", 1,
     "citation:integrity", "[%s]" % bad[0])
 deliv = norm(" ".join(s["text"] for s in segs if s["section"] in ("Results", "Discussion", "Conclusion"))).lower()
 hit = 0
 for s in segs:
  if not deliv or s["section"] not in ("Abstract", "Introduction") or not PROMISE.search(s["text"]): continue
  ws = sorted(set(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", s["text"]) if w.lower() not in STOP))
  if len(ws) < 2 or any(re.search(r"\b" + re.escape(w), deliv) for w in ws): continue
  hit += 1
  if hit <= 4:
   add("argument", "major", s, "引言/摘要承诺的分析在结果/讨论中未出现（%s）" % ", ".join(ws[:5]), "low", 0,
    "argument:coherence")
 return out
def cdef(contract):
 dv = {}
 for k, v in (contract.items() if isinstance(contract, dict) else []):
  t = str(v.get("type") or "").lower() if isinstance(v, dict) else ""
  dv[k] = [] if (isinstance(v, list) or t in ("array", "list")) else (
   {} if (t in ("object", "dict", "map", "json") or (isinstance(v, dict) and not t)) else None)
 return dv
def base(cid, contract):
 r = {"case_id": cid, "status": "partial", "summary": {}, "issues": [], "candidate_issues": [], "claims": [],
  "checks": {k: {"status": "partial", "scope": "scaffold only", "items_checked": 0, "findings": [],
    "unreviewed": ["adjudication not run"], "note": ""} for k in CATS},
  "review_records": {}, "sources": [], "uncertainty": [], "pending_human": [], "errors": [], "degradations": [],
  "changes": [], "runtime": {}, "artifacts": {}, "output_contract": contract if isinstance(contract, dict) else {}}
 for k, v in cdef(contract).items(): r.setdefault(k, v)
 return r
def discover(inp):
 case, cp, errs = {}, None, []
 if inp.is_dir():
  for c in sorted(inp.glob("**/case*.json")):
   if c.is_file() and cp is None:
    try:
     o = json.loads(c.read_text("utf-8", "replace"))
     if isinstance(o, dict): case, cp = o, c
    except Exception as e: errs.append("case json parse failed (%s): %s" % (c.name, e))
 files = sorted(p for p in inp.rglob("*") if p.is_file() and not any(x in SKIP for x in p.parts)) if inp.is_dir() else []
 return case, cp, files, errs
def picks(files):
 src, skipped = [], []
 for p in files[:50]:
  try: src.append(load(p))
  except Exception as e: skipped.append("%s: parse error %s" % (p.name, e))
 src.sort(key=lambda s: (s["kind"] not in ("pdf", "docx", "md", "tex", "txt"), -s["chars"]))
 for i, s in enumerate(src, 1): s["id"] = "SRC%d" % i
 return src, skipped
def outline(segs):
 o = []
 for s in segs:
  if o and o[-1]["section"] == s["section"]: o[-1]["last"], o[-1]["count"] = s["sid"], o[-1]["count"] + 1
  else: o.append({"section": s["section"], "first": s["sid"], "last": s["sid"], "count": 1})
 return o
def digest(cid, src, segs, cands, budget):
 L = ["# Audit digest - case %s" % cid, "", "Scaffold v%s. Leads are guesses, NOT findings: adjudicate, write "
  "`issues_draft.json`, run `verify.py`." % V, "", "## Section outline"]
 L += ["- %s: %s-%s (%d sentences)" % (o["section"], o["first"], o["last"], o["count"]) for o in outline(segs)]
 L += ["", "## Leads (unadjudicated)"]
 L += ["[C%03d] %s/%s %s §%s %s%s | %s | %s" % (i, c["category"], c["severity"], c["sid"], c["section"], c["rule"],
  " (hard)" if c["hard"] else "", c["detail"], c["quote"][:200].replace("\n", " ")) for i, c in enumerate(cands[:120], 1)]
 if len(cands) > 120: L.append("_%d more leads in .audit/index.json_" % (len(cands) - 120))
 L += ["", "## Sentences"]
 used = sum(len(x) + 1 for x in L)
 for s in segs:
  line = "%s §%s ¶%s p%s | %s" % (s["sid"], s["section"], s["para"], s["page"] or "-", s["text"].replace("\n", " "))
  if used + len(line) > budget:
   L.append("_truncated at %s (budget %d); rest in .audit/index.json_" % (s["sid"], budget)); break
  L.append(line); used += len(line) + 1
 L += ["", "## Next: fill issues_draft.json (schema in references/schema.md; sentence_id suffices), then run "
  "`python3 -B scripts/verify.py --input /input --output /app/output`."]
 return "\n".join(L) + "\n"
def draft(cid, cands):
 return {"_template": True, "_note": "示例模板，非正式案例结果。补 reason/suggestion；仅给 sentence_id 亦可。",
  "case_id": cid, "verdict": "",
  "issues": [{"category": c["category"], "severity": c["severity"], "sentence_id": c["sid"], "quote": c["quote"][:400],
   "title": "", "reason": "", "suggestion": "", "evidence": [], "confidence": "medium", "status": "confirmed",
   "check_item": c["check_item"]} for c in cands if c["hard"]][:40],
  "checks": {}, "pending_human": [], "uncertainty": [], "rejected_candidates": []}
def fail(res, outp, status, err, note=None):
 res["status"] = status
 res["errors"].append(err)
 if note: res["uncertainty"].append(note)
 res["runtime"]["duration_s"] = round(time.time() - T0, 2)
 wj(outp / "result.json", res)
 return 0
def main():
 ap = argparse.ArgumentParser(description="review-04 scaffold: parse inputs, locate sentences, emit leads; writes "
  "PARTIAL result.json + digest + issues_draft.json. Exit code always 0.")
 ap.add_argument("--input", help="input dir (default /input)")
 ap.add_argument("--output", help="output dir (default /app/output)")
 ap.add_argument("--max-chars", type=int, default=60000, help="digest char budget (default 60000)")
 ap.add_argument("--version", action="version", version=V)
 a = ap.parse_args()
 inp = Path(a.input) if a.input else next((p for p in map(Path, ("/input", "input", "../input")) if p.is_dir()), Path("/input"))
 outp = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else Path("output"))
 res = base(None, {})
 res["runtime"] = {"skill": "paper-argument-audit", "version": V, "script": "audit.py", "started": now()}
 try: outp.mkdir(parents=True, exist_ok=True)
 except OSError: outp = Path("output"); outp.mkdir(parents=True, exist_ok=True)
 wj(outp / "result.json", res)
 try:
  case, cp, files, errs = discover(inp)
  ct = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
  cid = case.get("case_id") or case.get("id") or inp.name or "case-unknown"
  res["case_id"], res["output_contract"], res["errors"] = cid, ct, errs
  res["review_records"] = {"case_json": str(cp) if cp else None, "input_files": len(files), "rounds": 0}
  for k, v in cdef(ct).items(): res.setdefault(k, v)
  if not files: return fail(res, outp, "input_error", "no input files under %s" % inp, "no material; nothing audited")
  src, skipped = picks(files)
  res["degradations"] = skipped + ["%s: %s" % (Path(s["path"]).name, w) for s in src for w in s["warn"]]
  res["sources"] = [{"id": s["id"], "path": s["path"], "kind": s["kind"], "chars": s["chars"],
   "pages": s["meta"].get("pages"), "warnings": s["warn"]} for s in src]
  ms = next((s for s in src if s["text"].strip()), None)
  if not ms:
   return fail(res, outp, "insufficient_evidence", "no text-extractable source among %d files" % len(files),
    "all materials unreadable as text; OCR or a text version is required")
  segs = segment(ms["text"])
  if not segs: return fail(res, outp, "insufficient_evidence", "manuscript text could not be segmented")
  for s in res["sources"]: s["segments"] = len(segs) if s["id"] == ms["id"] else 0
  cands = leads(segs)
  res["candidate_issues"] = cands
  res["summary"] = {"counts_by_category": {k: sum(1 for c in cands if c["category"] == k) for k in CATS},
   "counts_by_severity": {k: 0 for k in ("blocker", "major", "minor", "suggestion")}, "total_issues": 0,
   "blockers": [], "coverage_note": "scaffold: %d leads, 0 adjudicated issues" % len(cands),
   "facet_coverage": {k: "not_run" for k in CATS}}
  # partial keeps only what the agent needs; verify.py adds full summary/review_records
  res["review_records"].update({"manuscript": Path(ms["path"]).name, "manuscript_chars": ms["chars"],
   "segments": len(segs), "section_outline": outline(segs),
   "rules_fired": {r: sum(1 for c in cands if c["rule"] == r) for r in sorted(set(c["rule"] for c in cands))}})
  wj(outp / "result.json", res)
  wj(outp / ".audit" / "index.json", {"case_id": cid, "generated": now(), "scaffold_version": V, "output_contract": ct,
   "errors": res["errors"], "sources": [{"id": s["id"], "path": s["path"], "kind": s["kind"], "meta": s["meta"],
    "text": s["text"], "warn": s["warn"]} for s in src],
   "segments": segs, "candidate_issues": cands,
   "case_meta": {k: case[k] for k in ("topic", "domain", "citation_style", "task_instruction", "checklist")
    if k in case}})
  (outp / "audit_digest.md").write_text(digest(cid, src, segs, cands, a.max_chars), encoding="utf-8")
  wj(outp / "issues_draft.json", draft(cid, cands))
  res["artifacts"] = {"result_json": str(outp / "result.json"), "review_report": None, "issues_csv": None,
   "audit_digest": str(outp / "audit_digest.md"), "issues_draft": str(outp / "issues_draft.json"),
   "index": str(outp / ".audit" / "index.json")}
  res["changes"].append({"at": now(), "action": "scaffold_written",
   "detail": "%d segments, %d leads" % (len(segs), len(cands))})
  res["runtime"]["duration_s"] = round(time.time() - T0, 2)
  wj(outp / "result.json", res)
 except Exception as e:  # noqa: BLE001
  return fail(res, outp, "partial", "scaffold exception: %s: %s" % (type(e).__name__, e))
 return 0
if __name__ == "__main__":
 sys.exit(main())
