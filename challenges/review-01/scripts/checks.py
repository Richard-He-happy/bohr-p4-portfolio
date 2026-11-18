#!/usr/bin/env python3
"""checks.py - review rule engine + evidence verification (stdlib only).
Rule data: ../references/rules.json; see SKILL.md for the call contract."""
from __future__ import annotations

import json
import re
import sys
import unicodedata

FACETS = ["fact_check", "citation_support", "method_design",
     "statistics_report", "argument_chain", "academic_norms"]
LABEL = {"fact_check": "事实与数值一致性", "citation_support": "引用与论断支持",
    "method_design": "方法设计与可复现性", "statistics_report": "统计报告完整性",
    "argument_chain": "论证链与逻辑一致性", "academic_norms": "学术规范与可发表性"}
SEV = ["major", "minor", "info"]
BASIS = ["error", "insufficient_evidence", "suggestion"]
NVAL = re.compile(r"(?:^|[^A-Za-z])(?:n|N|样本量|例数)\s*[=:：]\s*(\d{1,6})|共(?:纳入|收集|选取)\s*(\d{1,6})\s*[例人份]")
CITE = re.compile(r"\[\s*\d{1,3}(?:\s*[-,]\s*\d{1,3})*\s*\]")
EXH = re.compile(r"\b(Fig(?:ure)?s?\.?|Tables?)\s*(\d{1,2})[a-z]?|\b(图|表)\s*(\d{1,2})")
CAP = re.compile(r"^\s*(?:Fig(?:ure)?\.?|Table|图|表)\s*(\d{1,2})[a-z]?[\s.:：|]")
DOI = re.compile(r"\b10\.\d{4,9}/\S+")
BLANK = {"text": "", "start": 0, "sid": "", "pid": "", "section": None, "page": None, "source_id": None}
PROF = {}
FALLBACK = {"rules": [
  {"id": "ST-01", "facet": "statistics_report", "item": "p 值被报告为 0", "sev": "major", "basis": "error",
  "match": r"\bp\s*[=＝]\s*0?\.0+(?![1-9])", "why": "p 值不可能精确为 0。", "fix": "改报精确值或 p < 0.001。"},
  {"id": "FC-03", "facet": "fact_check", "item": "残留占位符", "sev": "major", "basis": "error",
  "match": r"\bTODO\b|\bTBD\b|待补充", "why": "稿件保留未完成标记。", "fix": "补齐内容并删除标记。"}],
  "specs": [], "computed": {}}


def _rx(p, flags=0):
  try:
    return re.compile(p, flags)
  except re.error:
    return re.compile(r"(?!x)x")


def load_rules(path=None):
  from pathlib import Path
  cands = ([Path(path)] if path else []) + [
    Path(__file__).resolve().parent.parent / "references" / "rules.json",
    Path(__file__).resolve().parent / "rules.json"]
  for c in cands:
    try:
      data = json.loads(Path(c).read_text(encoding="utf-8"))
    except Exception:
      continue
    for r in data.get("rules", []):
      r["_re"] = _rx(r.get("match", ""))
    PROF.update(data.get("profile") or {})
    return data
  for r in FALLBACK["rules"]:
    r["_re"] = _rx(r["match"])
  return FALLBACK


def norm(s):
  s = unicodedata.normalize("NFKC", s or "")
  for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u00a0", " "),
        ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"), ("\u3000", " "), ("\u00ad", "")):
    s = s.replace(a, b)
  return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", s)).strip()


def key(s):
  return re.sub(r"[^0-9a-z\u4e00-\u9fff%\.]+", "", norm(s).lower())


def _expand(tok):
  out = []
  for part in re.split(r"[,\s]+", tok.strip("[] ")):
    m = re.match(r"(\d{1,3})\s*-\s*(\d{1,3})", part or "")
    if m and 0 <= int(m.group(2)) - int(m.group(1)) <= 40:
      out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
    elif part.isdigit():
      out.append(int(part))
  return out


def analyze(corpus):
  flat, low, secs = corpus["flat"], corpus["flat"].lower(), corpus["sections"]
  st = {"words": len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", flat)),
     "section_set": sorted({s["name"] for s in secs})}
  cites = set()
  for m in CITE.finditer(flat):
    cites.update(_expand(m.group(0)))
  st["cited_numbers"] = sorted(cites)
  refs = ""
  for i, s in enumerate(secs):
    if s["name"] == "references":
      refs = flat[s["start"]:secs[i + 1]["start"] if i + 1 < len(secs) else len(flat)]
      break
  refs = re.sub(r"^\s*(?:\d+(?:\.\d+)*[\.\)]?\s*)?(?:references?|bibliography|参考文献|文献)[^\n]*\n",
                "", refs, flags=re.I)
  ent = []
  for blk in re.split(r"\n(?=\[?\d{1,3}[\]\.\)]?\s+\S)", refs):
    b = blk.strip()
    if len(b) >= 25:
      m = re.match(r"^\[?(\d{1,3})[\]\.\)]?\s", b)
      ent.append({"num": int(m.group(1)) if m else None, "text": b})
  nums = [e["num"] for e in ent if e["num"]]
  st.update({"refs_present": bool(ent), "ref_count": len(ent),
       "ref_max_num": max(nums) if nums else None,
       "ref_doi_bad": [d for d in (x.rstrip(".,;)") for e in ent for x in DOI.findall(e["text"]))
               if len(d) < 10 or re.search(r"[^\x21-\x7e]", d)],
       "ref_no_year": [e["text"][:100] for e in ent if not re.search(r"(?:19|20)\d{2}", e["text"])]})
  seen, dups = {}, []
  for e in ent:
    k = key(e["text"][:90])
    if len(k) > 25 and k in seen:
      dups.append(e["text"][:100])
    seen[k] = 1
  st["ref_dups"] = dups
  caps, exc = set(), {}
  for s in corpus["sentences"]:
    m = CAP.match(s["text"])
    if m:
      caps.add(int(m.group(1)))
    for m in EXH.finditer(s["text"]):
      n = m.group(2) or m.group(4)
      if n and n.isdigit():
        exc.setdefault(int(n), s["sid"])
  st["caption_numbers"] = sorted(caps)
  st["exhibit_cites"] = {str(k): v for k, v in sorted(exc.items())}
  st["caption_uncited"] = [n for n in st["caption_numbers"] if str(n) not in st["exhibit_cites"]]
  st["n_values"] = [[int(m.group(1) or m.group(2)), s["sid"]] for s in corpus["sentences"] for m in NVAL.finditer(s["text"])]
  st["p_present"] = bool(re.search(r"\bp\s*[<=>＜＝]\s*0?\.\d+|p\s*值", low))
  st["ci_present"] = bool(re.search(r"95\s*%\s*(?:ci|confidence)|confidence interval|置信区间", low))
  st["sd_present"] = bool(re.search(r"\b(?:sd|sem|s\.d\.|s\.e\.)\b|standard deviation|standard error|标准差|标准误|\biqr\b", low))
  st["mean_present"] = bool(re.search(r"\bmean\b|\bmedian\b|均值|中位数", low))
  st["sd_symbol"] = "±" in flat
  ab = ""
  for i, s in enumerate(secs):
    if s["name"] == "abstract":
      ab = flat[s["start"]:secs[i + 1]["start"] if i + 1 < len(secs) else len(flat)]
      break
  st["abstract"] = ab[:4000]
  st["abstract_len"] = len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", ab))
  st["abstract_numbers"] = sorted({x for x in re.findall(r"\d+(?:\.\d+)?", ab) if len(x) >= 2})
  st["keywords"] = re.findall(r"(?:key\s?words?|关键词)\s*[:：]?\s*([^\n]{3,200})", flat, re.I)
  return st


def profile(corpus, st):
 low, p = corpus["flat"].lower(), {}
 for k, rx in PROF.items():
  p[k] = bool(re.search(rx, low))
 p["empirical"] = bool(p.get("human") or p.get("animal") or p.get("invitro") or p.get("empirical_text"))
 p["inferential"], p["full"] = st["p_present"], st["words"] >= 900
 return p

def _issue(rid, meta, sev, sent, quote, off, why, fix, conf="high", extra=""):
  return {"id": None, "rule_id": rid, "facet": meta["facet"], "facet_label": LABEL.get(meta["facet"], meta["facet"]),
      "check_item": meta["item"], "severity": sev, "basis_type": meta.get("basis", "insufficient_evidence"),
      "title": meta["item"], "quote": quote,
      "locator": {"source_id": sent.get("source_id"), "page": sent.get("page"), "section": sent.get("section"),
            "paragraph_id": sent.get("pid"), "sentence_id": sent.get("sid"),
            "char_start": off, "char_end": off + len(quote)},
      "rationale": why, "suggestion": fix, "confidence": conf,
      "review_status": "confirmed" if conf == "high" else "needs_review",
      "verifiable_by": "在 locator 指向的位置检索 quote 原文串" + ("；全文计数：" + extra if extra else ""),
      "evidence": {"rule_id": rid, "matched": re.sub(r"\s+", " ", quote)[:90], "doc_level": extra},
      "quote_verified": None, "origin": "rule"}


def _win(sent, start, end, pad=110, maxlen=280):
  t = sent["text"]
  a, b = max(0, start - pad), min(len(t), end + pad)
  if b - a > maxlen:
    b = a + maxlen
  seg = t[a:b]
  return seg.strip(), sent["start"] + a + (len(seg) - len(seg.lstrip()))


def _sev(rule, prof):
  for k, v in (rule.get("sev_if") or {}).items():
    if prof.get(k):
      return v
  return rule.get("sev", "minor")


def gate_ok(g, sent, prof, m, first_sid):
  if not g:
    return True
  if any(re.search(rx, sent["text"], re.I) for rx in g.get("sentence_absent", [])):
    return False
  if any(not re.search(rx, sent["text"], re.I) for rx in g.get("sentence_has", [])):
    return False
  for k, v in (g.get("profile") or {}).items():
    if bool(prof.get(k)) != bool(v):
      return False
  if "numeric_gt" in g:
    ng = g["numeric_gt"]
    try:
      return float(m.group(ng["group"])) > ng["threshold"]
    except Exception:
      return False
  if g.get("first_sentence"):
    return sent["sid"] == first_sid and len(re.findall(r"\S+", sent["text"])) >= g.get("min_tokens", 0)
  return True


def _first(corpus, rx):
  r = _rx(rx, re.I)
  for s in corpus["sentences"]:
    m = r.search(s["text"])
    if m:
      return s, m
  return (corpus["sentences"][0] if corpus["sentences"] else BLANK), None


def run(corpus, st, prof, rules, cap=4):
  issues, ran, skipped, fired = [], set(), {}, {}
  first_sid = corpus["sentences"][0]["sid"] if corpus["sentences"] else ""
  for s in corpus["sentences"]:
    for r in rules.get("rules", []):
      m = r["_re"].search(s["text"])
      if not m or not gate_ok(r.get("gate"), s, prof, m, first_sid):
        ran.add(r["id"])
        continue
      if fired.get(r["id"], 0) >= r.get("cap", cap):
        continue
      fired[r["id"]] = fired.get(r["id"], 0) + 1
      ran.add(r["id"])
      q, off = _win(s, m.start(), m.end())
      issues.append(_issue(r["id"], r, _sev(r, prof), s, q, off, r.get("why", ""), r.get("fix", "")))
  issues += spec_rules(corpus, st, prof, rules, ran, skipped)
  issues += computed_rules(corpus, st, rules, ran, skipped)
  return issues, fired, ran, skipped


def spec_rules(corpus, st, prof, rules, ran, skipped):
  flat, out = corpus["flat"], []
  for sp in rules.get("specs", []):
    ap = sp.get("applies", {})
    if not (all(prof.get(k) for k in ap.get("profile", []))
        and all(st.get(k) for k in ap.get("stat_true", []))
        and all(k in st["section_set"] for k in ap.get("section", []))):
      skipped.setdefault(sp["id"], sp.get("need") or "适用条件不满足（%s）" %
               "/".join(ap.get("profile", []) + ap.get("stat_true", []) + ap.get("section", [])))
      continue
    ran.add(sp["id"])
    f = sp.get("fire", {})
    if "absent" in f:
      hit = not any(re.search(rx, flat, re.I) for rx in f["absent"])
    elif "profile_false" in f:
      hit = not prof.get(f["profile_false"])
    elif "stat_false" in f:
      hit = not st.get(f["stat_false"])
    elif "stat_true" in f:
      hit = bool(st.get(f["stat_true"]))
    elif "none_stat" in f:
      hit = not any(st.get(k) for k in f["none_stat"])
    elif "absent_section" in f:
      hit = f["absent_section"] not in st["section_set"]
    elif "count_not_between" in f:
      c, v = f["count_not_between"], st.get(f["count_not_between"]["stat"]) or 0
      hit = bool(v) and not (c["lo"] <= v <= c["hi"])
    elif "list_count" in f:
      c = f["list_count"]
      v = len([x for x in re.split(c["split"], (st.get(c["stat"]) or [""])[0]) if x.strip()])
      hit = bool(v) and not (c["lo"] <= v <= c["hi"])
    else:
      hit = bool(sp.get("always"))
    if not hit:
      continue
    s, m = _first(corpus, sp.get("quote", r"."))
    q, off = _win(s, m.start(), m.end()) if m else _win(s, 0, min(70, len(s["text"])))
    out.append(_issue(sp["id"], sp, sp.get("sev", "minor"), s, q, off, sp.get("why", ""), sp.get("fix", ""),
             sp.get("conf", "medium"), sp.get("count", "")))
  return out


def computed_rules(corpus, st, rules, ran, skipped):
  C = rules.get("computed", {})
  out = []

  def mk(rid, sev, sent, m, conf, extra="", n=60):
    meta = C.get(rid)
    if not meta:
      return
    q, off = _win(sent, m.start(), m.end()) if m else _win(sent, 0, min(n, len(sent["text"])))
    out.append(_issue(rid, meta, meta.get("sev", sev), sent, q, off, meta.get("why", ""), meta.get("fix", ""), conf, extra))

  if not st["refs_present"] and st["cited_numbers"]:
    ran.add("CT-01")
    s, m = _first(corpus, r"\[\s*\d")
    mk("CT-02", "major", s, m, "high", "正文引用编号数=%d，文献条目=0" % len(st["cited_numbers"]))
  if st["refs_present"]:
    ran.add("CT-01")
    mx = st["ref_max_num"] or st["ref_count"]
    over = [n for n in st["cited_numbers"] if n > mx]
    if over:
      s, m = _first(corpus, r"\[[^\]]*\b%d\b" % over[0])
      if not m:
        s, m = _first(corpus, r"\[\s*\d")
      mk("CT-01", "major", s, m, "high", "正文最大编号=%d，文献表最大编号=%s，条目=%d"
       % (max(st["cited_numbers"] or [0]), st["ref_max_num"], st["ref_count"]))
    orphan = [n for n in range(1, mx + 1) if n not in st["cited_numbers"]]
    if orphan:
      s, m = _first(corpus, re.escape("[%d]" % orphan[0]))
      mk("CT-03", "info", s, m, "medium", "未引用编号=%s" % orphan[:8])
  if st["n_values"]:
    ran.add("FC-01")
    vals = {}
    for v, sid in st["n_values"]:
      vals.setdefault(v, []).append(sid)
    if len(vals) > 1:
      s = next((x for x in corpus["sentences"] if x["sid"] == vals[sorted(vals)[0]][0]), corpus["sentences"][0])
      mk("FC-01", "major", s, NVAL.search(s["text"]), "medium",
       "n 值分布=%s" % json.dumps({str(k): len(v) for k, v in sorted(vals.items())}))
  else:
    skipped.setdefault("FC-01", "全文未检出 n= 或样本量数值，未做样本量一致性核对")
  if st["exhibit_cites"] and st["caption_numbers"]:
    ran.add("FC-02")
    miss = [n for n in st["exhibit_cites"] if n > max(st["caption_numbers"])]
    if miss:
      s = next((x for x in corpus["sentences"] if x["sid"] == st["exhibit_cites"][str(miss[0])]), corpus["sentences"][0])
      mk("FC-02", "major", s, EXH.search(s["text"]), "high", "图注编号=%s，正文引用=%s"
       % (st["caption_numbers"], sorted(int(k) for k in st["exhibit_cites"])))
  else:
    ran.add("FC-02")
    skipped.setdefault("FC-02", "未同时检出图注与正文图表引用，无法核对图表编号对应关系")
  if st["abstract"] and st["abstract_numbers"]:
    ran.add("FC-04")
    body = corpus["flat"].replace(st["abstract"], " ", 1)
    miss = [x for x in st["abstract_numbers"] if x not in body]
    if len(miss) >= 2 and st["words"] > 600:
      s, m = _first(corpus, r"\d+\.\d+|\d{2,}")
      mk("FC-04", "minor", s, m, "low", "未在正文命中的摘要数值=%s" % miss[:8])
  else:
    ran.add("FC-04")
    skipped.setdefault("FC-04", "未检出摘要段或摘要无数值")
  return out


def coverage(rules, ran, skipped, issues):
  out = {}
  items = [(r["facet"], r["id"], r["item"]) for r in rules.get("rules", [])]
  items += [(s["facet"], s["id"], s["item"]) for s in rules.get("specs", [])]
  items += [(m["facet"], k, m["item"]) for k, m in rules.get("computed", {}).items()]
  for facet, rid, item in items:
    v = out.setdefault(facet, {"label": LABEL.get(facet, facet), "items": []})
    v["items"].append({"rule_id": rid, "item": item,
             "status": "not_checked" if rid in skipped else "checked",
             "reason": skipped.get(rid, ""),
             "findings": sum(1 for i in issues if i["rule_id"] == rid)})
  for f in FACETS:
    v = out.setdefault(f, {"label": LABEL[f], "items": []})
    x = [i["status"] for i in v["items"]]
    v["status"] = ("checked" if x and all(y == "checked" for y in x)
           else "partially_checked" if "checked" in x else "not_checked")
    v["checked_items"], v["total_items"] = x.count("checked"), len(x)
  return out


def verify_quotes(issues, corpus, min_len=10):
  k = key(corpus["flat"])
  keep, rejected = [], []
  for it in issues:
    qk = key(it.get("quote") or "")
    ok = len(qk) >= min_len and qk in k
    if not ok and len(qk) >= min_len and qk[:40] in k:
      ok = "partial"
    if ok is False:
      rejected.append({"reason": "quote_not_found", "issue": it,
              "detail": "quote 未在抽取文本中逐字命中，已降级为待复核"})
      continue
    it["quote_verified"] = True if ok is True else "partial"
    keep.append(it)
  return keep, rejected


def report_md(res, out, skill):
 """Render review_report.md from the result dict using references/report_template.md."""
 from pathlib import Path
 m, cov, iss = res["metrics"], res["review"]["facet_coverage"], res["issues"]
 F = ("- **%s** %s · %s · %s ｜ %s %s · 段%s · 句%s · 字符%s~%s\n  原文> %s\n  判断 %s ｜ 建议 %s\n"
   "  %s · %s · quote校验 %s · %s")
 L = []
 for f in FACETS:
  sub = [i for i in iss if i["facet"] == f]
  L += ["### " + LABEL[f], ""]
  for i in sub:
   lo = i["locator"]
   L.append(F % (i["id"], i["severity"], i["facet"], i["check_item"], lo.get("source_id") or "S?",
          ("p%s" % lo["page"]) if lo.get("page") else "页码未标注", lo.get("paragraph_id"),
          lo.get("sentence_id"), lo.get("char_start"), lo.get("char_end"),
          i["quote"].replace("\n", " ")[:400], i["rationale"], i["suggestion"], i["basis_type"],
          i["confidence"], i["quote_verified"], i["origin"]))
  L += [""] if sub else ["该分面未发现具体问题（覆盖见第 4 节）。", ""]
 basis = ["- 抽取：%s" % ("；".join("%s(%s,%s字符)" % (x["name"], x["engine"], x["chars"]) for x in res["sources"]) or "无材料"),
     "- quote 校验：%d/%d 条逐字命中（去空白标点后比对全文），未命中项降级为待复核。" % (
       m["quotes_verified"], m["quotes_total"]),
     "- 口径：`error` 可确证；`insufficient_evidence` 需补材料；`suggestion` 为建议；`origin=rule` 规则命中，"
     "`origin=agent` 语义补充。规则只覆盖可形式化缺陷；扫描件与图片图表未做 OCR，相关项标未执行。"]
 for k, t in (("uncertainty", "不确定性"), ("degradations", "降级记录"), ("errors", "错误记录")):
  basis += (["", "%s：" % t] + ["- %s" % (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)[:280])
                 for x in res[k]]) if res[k] else []
 v = {"case_id": res.get("case_id"), "status": res.get("status"),
   "skill": "%s %s" % (skill.get("name"), skill.get("version")),
   "fingerprint": "；".join("%s=%s" % (x["name"], x["sha256"]) for x in res["sources"]) or "无材料",
   "generated": res["runtime"].get("finished_at") or "", "summary": res["review"]["summary"],
   "issues": "\n".join(L),
   "pending": "\n".join(["- `%s` %s — %s ｜ %s" % (p.get("id") or "-", p.get("reason", ""),
                           str(p.get("detail", ""))[:140], str(p.get("action", ""))[:100])
              for p in res["pending_human"][:40]] or ["无。"]),
   "unchecked": "\n".join(["- `%s` %s — %s" % (u["rule_id"], u["item"], u["reason"]) for u in res["unchecked"]]
               or ["全部检查项均已执行。"]),
   "coverage": "\n".join("| %s | %s | %s/%s |" % (
     LABEL[f], cov.get(f, {}).get("status", ""), cov.get(f, {}).get("checked_items", 0),
     cov.get(f, {}).get("total_items", 0)) for f in FACETS),
   "basis": "\n".join(basis), "top_major": ""}
 tpl = Path(__file__).resolve().parent.parent / "references" / "report_template.md"
 try:
  t = tpl.read_text(encoding="utf-8")
  for k, x in v.items():
   t = t.replace("{{%s}}" % k, str(x))
 except Exception:
  t = "# 论文质量审查报告\n\n" + "\n\n".join("%s：%s" % (k, x) for k, x in v.items())
 Path(out, "review_report.md").write_text(t, encoding="utf-8")


def main():
  import argparse
  ap = argparse.ArgumentParser(description="verify a review result against its corpus (quote + count audit)")
  ap.add_argument("--result", required=True)
  ap.add_argument("--corpus", required=True)
  a = ap.parse_args()
  res = json.load(open(a.result, encoding="utf-8"))
  cor = json.load(open(a.corpus, encoding="utf-8"))
  if not cor.get("flat"):
   cor["flat"] = "\n\n".join(p.get("text", "") for p in cor.get("paragraphs") or [])
  keep, rej = verify_quotes([dict(i) for i in (res.get("issues") or [])], cor)
  print(json.dumps({"issues": len(res.get("issues") or []), "verified": len(keep), "rejected": len(rej),
           "rejected_titles": [r["issue"].get("title") for r in rej]}, ensure_ascii=False, indent=1))
  return 0


if __name__ == "__main__":
  sys.exit(main())
