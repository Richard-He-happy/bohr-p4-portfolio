#!/usr/bin/env python3
"""review.py - source-bound manuscript review (stdlib only, no network, exit code 0).

 python3 review.py [--input DIR] [--output DIR] [--merge FILE]
Writes result.json (output_contract echoed), review_report.md, issues.csv, corpus.json.
"""
import argparse, csv, hashlib, html, json, os, re, shutil, subprocess, sys, time, traceback, zipfile
from datetime import datetime, timezone
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import checks as C  # noqa: E402

SK, T0 = {"name": "paper-quality-review", "version": "1.0.0"}, time.time()
EXT = {("." + k): v for k, v in dict(
  pdf="pdf", docx="docx", doc="docx", xlsx="xlsx", xls="xlsx", csv="csv", tsv="csv", json="json",
  md="md", markdown="md", txt="txt", tex="tex", html="html", htm="html", png="img", jpg="img",
  jpeg="img", tif="img", tiff="img", gif="img", bmp="img", zip="bin").items()}
ABBR = re.compile(r"\b(?:et al|e\.g|i\.e|fig|figs|eq|vs|dr|no|approx|ref|refs|tab|cf|inc|ltd|sp|spp|min|max|ca)\.$", re.I)
SEM = [("count|number|total|num", lambda r: r["metrics"].get("issues_total")),
   ("verdict|judgement|judgment|recommend", lambda r: r["review"].get("verdict")),
   ("report", lambda r: r["artifacts"].get("review_report_md")),
   ("issue|finding|problem|comment|concern", lambda r: r["issues"]),
   ("summary|overview|conclusion|verdict|judge|opinion", lambda r: r["review"]["summary"]),
   ("facet|dimension|categor|checklist|coverage", lambda r: r["review"]["facet_coverage"]),
   ("pending|human|manual", lambda r: r["pending_human"]),
   ("uncertain|limit|gap|caveat|risk", lambda r: r["uncertainty"]),
   ("count|metric|stat|number|severit", lambda r: r["metrics"]),
   ("source|input|document|material", lambda r: r["sources"]), ("status|state", lambda r: r["status"]),
   ("artifact|output|path|report|file", lambda r: r["artifacts"]), ("error|fail", lambda r: r["errors"]),
   ("degrad|warning", lambda r: r["degradations"]), ("change|log", lambda r: r["changes"]),
   ("runtime|timing|budget", lambda r: r["runtime"])]
G = {"rx": re.compile(r"^(abstract|introduction|methods?|results?|discussion|conclusions?|references?|"
           r"摘要|方法|结果|讨论|结论|参考文献)", re.I), "map": []}


def now():
 return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(p):
 h = hashlib.sha256()
 with open(p, "rb") as f:
  for b in iter(lambda: f.read(1 << 20), b""):
   h.update(b)
 return h.hexdigest()[:16]


def rt(p):
 raw = Path(p).read_bytes()
 for e in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "latin-1"):
  try:
   return raw.decode(e)
  except Exception:
   pass
 return raw.decode("latin-1", "replace")


def lj(p):
 return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))


def wj(p, o):
 Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def setup(sec):
 """Section vocabulary comes from rules.json (data); built-in default kept otherwise."""
 try:
  G["rx"], G["map"] = re.compile(sec["heading"], re.I), [(a, re.compile(b, re.I)) for a, b in sec["map"]]
 except Exception:
  pass


def textof(p):
 """PDF via pdftotext/mutool; OOXML by XML strip; plain text formats read directly."""
 k = EXT.get(p.suffix.lower(), "")
 if k == "pdf":
  for cmd, e in ((["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], "pdftotext"),
         (["mutool", "draw", "-F", "txt", "-o", "-", str(p)], "mutool")):
   if shutil.which(cmd[0]):
    try:
     t = subprocess.run(cmd, capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
     if len(re.sub(r"\s", "", t)) > 200:
      return t.replace("\r\n", "\n"), e
    except Exception:
     pass
  return "", "none"
 if k in ("docx", "xlsx"):
  with zipfile.ZipFile(p) as z:
   xml = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()
          if re.search(r"(document|sharedStrings|sheet\d+)\.xml$", n))
  xml = xml.replace("</w:p>", "\n\n").replace("</row>", "\n\n").replace("</w:tc>", " | ").replace("</c>", " | ")
  return re.sub(r"<[^>]+>", " ", html.unescape(xml)), "zip-xml"
 if k == "html":
  t = re.sub(r"(?is)<(?:script|style).*?</(?:script|style)>", " ", rt(p))
  return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>", "\n\n", t))), "html"
 if k in ("md", "txt", "tex", "csv", "json"):
  t = rt(p)
  return (re.sub(r"(?m)^%.*$", "", t) if k == "tex" else t), "text/" + k
 return None, ""


def blocks(t):
 out = []
 for pi, page in enumerate(t.split("\f"), 1):
  for ch in re.split(r"\n\s*\n", page):
   s = ch.strip()
   ln = s.split("\n")
   f = re.sub(r"^[#*\s]+", "", ln[0])
   if len(ln) > 1 and len(f.split()) <= 12 and (G["rx"].match(f) or f.isupper()):
    out.append({"type": "heading", "text": f, "page": pi})
    s = "\n".join(ln[1:]).strip()
    ln = s.split("\n")
    f = re.sub(r"^[#*\s]+", "", ln[0]) if s else ""
   if s:
    h = len(s) < 95 and len(f.split()) <= 14 and (bool(G["rx"].match(f)) or f.isupper())
    out.append({"type": "heading" if h else "para", "text": s, "page": pi})
 return out


def extract(p):
 k = EXT.get(p.suffix.lower(), "other")
 d = {"source_id": "S%d" % (abs(hash(str(p))) % 9000 + 1000), "path": str(p), "kind": k, "engine": "none",
   "blocks": [], "chars": 0, "pages": None, "note": ""}
 try:
  t, e = textof(p)
  if t is None:
   d.update(engine="skipped", note="未支持的二进制/图片材料（%s），未做 OCR" % (p.suffix or "无扩展名"))
  else:
   d.update(engine=e, blocks=blocks(t), pages=t.count("\f") + 1 if e.startswith("pdf") else None,
       note="文本抽取：%s" % e)
 except Exception as ex:
  d.update(engine="failed", note="解析失败 %s: %s" % (type(ex).__name__, ex))
 d["chars"] = sum(len(b["text"]) for b in d["blocks"])
 return d


def spans(t, base):
 sp, st = [], 0
 for m in re.finditer(r"[.!?。！？]+[\"'”’)\]]?(?=\s|$)|\n", t):
  seg, end = t[st:m.end()], m.end()
  if not seg.strip() or (m.group(0)[0] == "." and ABBR.search(seg.strip())):
   st = end
   continue
  sp.append([st, end])
  st = end
 if st < len(t) and t[st:].strip():
  sp.append([st, len(t)])
 mg = []
 for a, b in sp:
  if mg and b - a < 24:
   mg[-1][1] = b
  else:
   mg.append([a, b])
 return [(base + a, base + b) for a, b in mg]


def build(docs):
 parts, off, P = [], 0, []
 for d in docs:
  for b in d["blocks"]:
   t = C.norm(b["text"])
   if t:
    P.append({"pid": "P%04d" % (len(P) + 1), "source_id": d["source_id"], "page": b.get("page"),
         "text": t, "start": off, "heading": b["type"] == "heading"})
    parts += [t, "\n\n"]
    off += len(t) + 2
 flat = "".join(parts).rstrip("\n")
 secs, cur = [], ""
 for p in P:
  t = re.sub(r"^[#*\s]+", "", p["text"])
  if p["heading"] or (len(t) < 80 and G["rx"].match(t)):
   for name, rx in G["map"]:
    if rx.search(t):
     cur = name
     secs.append({"name": name, "start": p["start"]})
     break
  p["section"] = cur or None
 S, per = [], {}
 for p in P:
  per[p["pid"]] = 0
  for a, b in spans(p["text"], p["start"]):
   if flat[a:b].strip():
    per[p["pid"]] += 1
    S.append({"sid": "%sS%02d" % (p["pid"], per[p["pid"]]), "pid": p["pid"], "source_id": p["source_id"],
         "page": p["page"], "section": p["section"], "text": flat[a:b], "start": a, "end": b})
 return {"flat": flat, "paragraphs": P, "sentences": S, "sections": secs}


def discover(inp):
 case, cp, errs, files, gaps = {}, None, [], [], []
 if inp and inp.exists():
  for c in dict.fromkeys([inp / "case.json"] + sorted(inp.glob("*.json"))):
   if not c.is_file() or "findings" in c.name or "corpus" in c.name:
    continue
   try:
    o = lj(c)
   except Exception as e:
    errs.append({"stage": "discover", "error": "%s 解析失败: %s" % (c.name, e), "path": str(c)})
    continue
   if isinstance(o, dict) and (c.name == "case.json" or "output_contract" in o or "case_id" in o):
    case, cp = o, str(c)
    break
  for root, _d, ns in os.walk(inp):
   files += [Path(root) / n for n in sorted(ns) if not n.startswith(".")
        and n not in ("case.json", "task.md", "agent_findings.json", "corpus.json")]
  for v in case.values():
   for x in (v if isinstance(v, list) else [v]):
    x = x if isinstance(x, str) else (x.get("path") or x.get("name") if isinstance(x, dict) else "")
    if isinstance(x, str) and re.search(r"\.(pdf|docx?|xlsx?|csv|tsv|json|md|txt|tex)$", x, re.I) \
        and not (inp / x).exists() and not list(inp.rglob(Path(x).name)):
     gaps.append({"declared": x, "reason": "case 中声明，但输入目录内未找到"})
 return case, cp, files, gaps, errs


def merge(res, cor, path):
 try:
  d = lj(path)
 except Exception as e:
  res["errors"].append({"stage": "merge", "error": "findings 解析失败: %s" % e, "path": str(path)})
  return 0, []
 items = d.get("findings") if isinstance(d, dict) else d
 if not isinstance(items, list):
  res["errors"].append({"stage": "merge", "error": "findings 结构非法"})
  return 0, []
 key, n, rej = C.key(cor["flat"]), 0, []
 for f in items[:200]:
  if not isinstance(f, dict):
   continue
  fc = str(f.get("facet") or "").lower()
  fc = fc if fc in C.FACETS else next((x for x in C.FACETS if x in fc), "")
  q = C.norm(f.get("quote") or f.get("evidence") or "")
  if not fc or len(C.key(q)) < 10 or key.find(C.key(q)) < 0:
   rej.append({"reason": "facet_or_quote_invalid", "detail": "facet 非法或 quote 未逐字命中：%s" % q[:60]})
   continue
  pos = cor["flat"].find(q[:40])
  sn = max(cor["sentences"], key=lambda x: min(x["end"], pos + len(q)) - max(x["start"], pos)) if cor["sentences"] else None
  if not sn:
   rej.append({"reason": "locator_failed", "detail": "无法映射到句子：%s" % q[:60]})
   continue
  sv = str(f.get("severity") or "minor").lower().replace("high", "major").replace("medium", "minor")
  it = C._issue("AGENT", {"facet": fc, "item": f.get("title") or "语义审查项",
              "basis": f.get("basis_type") if f.get("basis_type") in C.BASIS else "insufficient_evidence"},
         sv if sv in C.SEV else "minor", sn, q, pos, f.get("rationale") or "",
         f.get("suggestion") or "", str(f.get("confidence") or "medium").lower(), "语义阅读补充")
  it["origin"] = "agent"
  res["issues"].append(it)
  n += 1
 return n, rej


def echo(res, ct):
 rep = {"keys": 0, "filled": [], "defaulted": [], "preserved": []}
 if not isinstance(ct, dict):
  return rep
 rep["keys"] = len(ct)
 for k, v in ct.items():
  if k in res and res[k] not in (None, [], {}, ""):
   rep["preserved"].append(k)
   continue
  got = None
  for rx, fn in SEM:
   if re.search(rx, re.sub(r"[^a-z0-9_]", "", str(k).lower())):
    try:
     got = fn(res)
    except Exception:
     got = None
    break
  if got not in (None, [], {}, ""):
   res[k], _ = got, rep["filled"].append(k)
  else:
   res[k], _ = res.get(k, v), rep["defaulted"].append(k)
 return rep


def assign(iss):
 order, pre, seen, out = {f: n for n, f in enumerate(C.FACETS)}, {"major": "MJ", "minor": "MN", "info": "IN"}, set(), []
 for i in iss:
  k = (i["facet"], C.key(i.get("quote", ""))[:80])
  if not (k[1] and k in seen):
   seen.add(k)
   out.append(i)
 for n, i in enumerate(sorted(out, key=lambda x: (C.SEV.index(x["severity"]), order.get(x["facet"], 9))), 1):
  i["id"] = "%s-%03d" % (pre.get(i["severity"], "IS"), n)
 return sorted(out, key=lambda x: x["id"])


def wcsv(path, iss):
 cols = ["id", "facet", "check_item", "severity", "basis_type", "review_status", "confidence", "source_id",
     "page", "section", "paragraph_id", "sentence_id", "char_start", "char_end", "quote", "rationale",
     "suggestion", "verifiable_by", "quote_verified", "origin"]
 loc = ("source_id", "page", "section", "paragraph_id", "sentence_id", "char_start", "char_end")
 with open(path, "w", encoding="utf-8", newline="") as fh:
  w = csv.writer(fh)
  w.writerow(cols)
  for i in iss:
   w.writerow([str(i["locator"].get(c) if c in loc else i.get(c) or "").replace("\n", " ") for c in cols])



def base():
 return {"case_id": None, "status": "partial", "skill": dict(SK),
     "input": {"case_json": None, "files": [], "material_gaps": [], "task_instruction": None},
     "review": {"summary": "", "facet_coverage": {}, "issues_by_severity": {}},
     "issues": [], "pending_human": [], "unchecked": [], "uncertainty": [], "sources": [],
     "metrics": {}, "errors": [], "degradations": [], "changes": [], "artifacts": {},
     "contract_fill": {}, "runtime": {}}


def ingest(a, res, ex, out):
 inp = Path(a.input)
 case, cp, files, gaps, errs = discover(inp)
 res["errors"] += errs
 res["case_id"] = case.get("case_id") or case.get("id") or (Path(cp).stem if cp else None)
 ex["contract"] = case.get("output_contract") or case.get("output") or {}
 res["input"].update({"case_json": cp, "material_gaps": gaps,
           "task_instruction": str(case.get("task_instruction") or case.get("task") or "")[:1500],
           "files": [{"name": p.name, "bytes": p.stat().st_size} for p in files]})
 if not files:
  res["errors"].append({"stage": "discover", "error": "输入目录无可审材料", "path": str(inp)})
 docs = [extract(p) for p in files]
 for p, d in zip(files, docs):
  res["sources"].append({"source_id": d["source_id"], "name": p.name, "path": str(p), "kind": d["kind"],
             "engine": d["engine"], "chars": d["chars"], "pages": d["pages"],
             "sha256": sha(p), "note": d["note"]})
  if d["engine"] in ("skipped", "failed", "none") or not d["chars"]:
   res["degradations"].append("%s：%s" % (p.name, d["note"] or "无可抽取文本"))
   res["pending_human"].append({"id": None, "reason": "material_unreadable",
                 "detail": "%s（%s）" % (p.name, d["engine"]),
                 "action": "该材料未参与自动审查，需人工阅读或提供可解析版本"})
 cor = build(docs)
 wj(out / "corpus.json", {k: cor[k] for k in ("paragraphs", "sentences", "sections")})
 if len(cor["flat"]) < 400:
  res["degradations"].append("抽取文本仅 %d 字符，证据不足" % len(cor["flat"]))
 if not cor["sections"]:
  res["degradations"].append("未识别章节标题：章节齐备性检查项将标记为未执行")
 return cor


def finalize(a, res, cor, ex):
 out = Path(a.output)
 out.mkdir(parents=True, exist_ok=True)
 keep, rej = C.verify_quotes(assign(res["issues"])[:120], cor) if cor.get("flat") else (res["issues"], [])
 for r in rej:
  res["pending_human"].append({"id": r["issue"].get("rule_id"), "reason": r["reason"],
                "detail": "quote 未逐字命中：%s" % (r["issue"].get("quote") or "")[:110],
                "action": "人工确认原文表述后判定"})
 res["issues"] = assign(keep)
 m, cov = {}, res["review"]["facet_coverage"]
 m.update({"issues_total": len(res["issues"]), "chars": len(cor.get("flat", "")),
      "quotes_total": len(keep) + len(rej),
      "quotes_verified": sum(1 for i in res["issues"] if i.get("quote_verified") is True),
      "quotes_rejected": len(rej), "pending_human": len(res["pending_human"]), "rules_fired": ex.get("fired", 0),
      "by_severity": {s: sum(1 for i in res["issues"] if i["severity"] == s) for s in C.SEV},
      "by_facet": {f: sum(1 for i in res["issues"] if i["facet"] == f) for f in C.FACETS},
      "by_basis": {b: sum(1 for i in res["issues"] if i["basis_type"] == b) for b in C.BASIS}})
 res["metrics"], res["review"]["issues_by_severity"] = m, m["by_severity"]
 res["review"]["verdict"] = ("major_issues_present" if m["by_severity"]["major"] else
                             "minor_issues_only" if m["by_severity"]["minor"] else
                             "no_issue_detected" if m["issues_total"] == 0 else "info_only")
 cov.update(ex.get("coverage") or {})
 res["unchecked"] = [{"rule_id": i["rule_id"], "item": i["item"], "reason": i.get("reason", "")}
           for v in cov.values() for i in v["items"] if i["status"] == "not_checked"]
 res["review"]["summary"] = ("共 %d 条问题（阻断 %d / 建议 %d / 提示 %d）；分面全执行 %d、部分执行 %d；待复核 %d 条，"
               "未执行项 %d 个。" % (m["issues_total"], m["by_severity"]["major"],
                        m["by_severity"]["minor"], m["by_severity"]["info"],
                        sum(1 for v in cov.values() if v.get("status") == "checked"),
                        sum(1 for v in cov.values() if v.get("status") == "partially_checked"),
                        len(res["pending_human"]), len(res["unchecked"])))
 if res["status"] != "input_error":
  res["status"] = ("insufficient_evidence" if m["chars"] < 400 else
          "partial" if (res["pending_human"] or res["unchecked"] or m["quotes_rejected"]) else "ok")
 res["runtime"].update({"finished_at": now(), "elapsed_s": round(time.time() - T0, 2)})
 wcsv(out / "issues.csv", res["issues"])
 C.report_md(res, out, SK)
 res["artifacts"] = {"result_json": str(out / "result.json"), "review_report_md": str(out / "review_report.md"),
           "issues_csv": str(out / "issues.csv"), "corpus_json": str(out / "corpus.json")}
 res["contract_fill"] = echo(res, ex.get("contract") or {})
 wj(out / "result.json", res)


def main(argv=None):
 ap = argparse.ArgumentParser(prog="review.py", description="Source-bound manuscript quality review: located, "
               "quoted, severity-graded issue list.", epilog="Writes result.json (output_contract "
               "echoed), review_report.md, issues.csv, corpus.json; exit code is always 0.")
 ap.add_argument("--input", default="/input", help="输入目录（case.json / task.md / 材料）")
 ap.add_argument("--output", default="/app/output", help="输出目录")
 ap.add_argument("--merge", default=None, help="agent findings JSON（默认 <output>/agent_findings.json）")
 a = ap.parse_args(argv)
 out = Path(a.output)
 out.mkdir(parents=True, exist_ok=True)
 res, cor, ex = base(), {}, {"contract": {}, "coverage": {}, "fired": 0}
 wj(out / "result.json", res)
 rules = {"rules": [], "specs": [], "computed": {}, "sections": {}}
 try:
  rules = C.load_rules()
  setup(rules.get("sections") or {})
  cor = ingest(a, res, ex, out)
  st = C.analyze(cor)
  iss, fired, ran, skip = C.run(cor, st, C.profile(cor, st), rules)
  res["issues"] = iss
  ex.update(fired=sum(fired.values()), coverage=C.coverage(rules, ran, skip, iss))
  res["changes"].append({"seq": 1, "action": "rule_pass", "detail": "%d 条命中；%d 项已执行" % (len(iss), len(ran))})
  mp = Path(a.merge) if a.merge else (out / "agent_findings.json")
  if mp.is_file():
   n, rej = merge(res, cor, mp)
   for r in rej:
    res["pending_human"].append({"id": None, "reason": r["reason"], "detail": r["detail"],
                  "action": "人工核对后决定是否保留"})
   res["changes"].append({"seq": 2, "action": "merge_agent_findings",
              "detail": "并入 %d 条，拒收 %d 条（%s）" % (n, len(rej), mp.name)})
  res["runtime"].update({"python": sys.version.split()[0], "started_at": now(),
             "rules_total": len(rules.get("rules", [])) + len(rules.get("specs", []))})
  res["uncertainty"] = ["规则类问题由确定性模式与全文计数产生；语义级缺陷由 origin=agent 条目覆盖，报告中分开标注。",
             "page 取决于抽取引擎；无页码时 page 为 null，段落与字符区间仍可定位。"]
 except Exception as e:
  res["errors"].append({"stage": "pipeline", "error": "%s: %s" % (type(e).__name__, e),
             "traceback": traceback.format_exc()[-900:]})
  if not cor.get("flat"):
   res["status"] = "input_error"
 finally:
  try:
   finalize(a, res, cor, ex)
  except Exception as e:
   res["errors"].append({"stage": "finalize", "error": "%s: %s" % (type(e).__name__, e)})
   res["artifacts"] = {"result_json": str(out / "result.json")}
   try:
    wj(out / "result.json", res)
   except Exception:
    pass
 return 0


if __name__ == "__main__":
 try:
  sys.exit(main())
 except SystemExit:
  sys.exit(0)
 except Exception:
  traceback.print_exc()
  sys.exit(0)
