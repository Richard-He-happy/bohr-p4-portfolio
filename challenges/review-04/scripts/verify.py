#!/usr/bin/env python3
# verify.py - review-04 finalizer. Reads .audit/index.json (built by audit.py) plus the findings
# the agent wrote to issues_draft.json, verifies every quote verbatim against the manuscript,
# derives locators, fills output_contract, then writes result.json + review_report.md + issues.csv.
# Exit code is always 0.
import argparse, bisect, csv, json, re, sys, time, unicodedata
from datetime import datetime
from pathlib import Path
V = "1.0.0"
T0 = time.time()
CATS = ["factual", "citation", "method", "statistics", "argument", "compliance"]
LABEL = {"factual": "事实核验", "citation": "引用支持", "method": "方法设计", "statistics": "统计报告",
         "argument": "论证链", "compliance": "学术规范"}
SEVS = ["blocker", "major", "minor", "suggestion"]
RANK = {s: i for i, s in enumerate(SEVS)}
CAL = [("factual", "factual"), ("事实", "factual"), ("数值", "factual"), ("citation", "citation"),
       ("引用", "citation"), ("文献", "citation"), ("method", "method"), ("方法", "method"), ("设计", "method"),
       ("stat", "statistics"), ("统计", "statistics"), ("argument", "argument"), ("论证", "argument"),
       ("逻辑", "argument"), ("inference", "argument"), ("compliance", "compliance"), ("规范", "compliance"),
       ("ethic", "compliance")]
SAL = [("block", "blocker"), ("critical", "blocker"), ("fatal", "blocker"), ("阻断", "blocker"), ("致命", "blocker"),
       ("major", "major"), ("high", "major"), ("重要", "major"), ("主要", "major"), ("moderate", "major"),
       ("minor", "minor"), ("medium", "minor"), ("次要", "minor"), ("一般", "minor"), ("suggestion", "suggestion"),
       ("low", "suggestion"), ("建议", "suggestion"), ("info", "suggestion"), ("note", "suggestion")]
CS = ["ok", "issues_found", "partial", "not_applicable"]
def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def norm(s):
 s = unicodedata.normalize("NFKC", str(s)).replace("\u00ad", "").replace("\u2019", "'")
 return re.sub(r"\s+", " ", s.replace("\u201c", '"').replace("\u201d", '"')).strip()
def qnorm(s):
 return s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
def lj(p, d):
 try: return json.loads(Path(p).read_text("utf-8", "replace"))
 except Exception: return d
def wj(p, o):
 p.parent.mkdir(parents=True, exist_ok=True)
 t = p.with_suffix(p.suffix + ".tmp"); t.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
 t.replace(p)
def cat_of(v):
 v = str(v or "").strip().lower()
 if v in CATS: return v
 for k, c in CAL:
  if k in v: return c
 return ""
def sev_of(v):
 v = str(v or "").strip().lower()
 if v in RANK: return v
 for k, s in SAL:
  if k in v: return s
 return "minor"
def cdef(ct):
 dv = {}
 for k, v in (ct.items() if isinstance(ct, dict) else []):
  t = str(v.get("type") or "").lower() if isinstance(v, dict) else ""
  dv[k] = [] if (isinstance(v, list) or t in ("array", "list")) else (
   {} if (t in ("object", "dict", "map", "json") or (isinstance(v, dict) and not t)) else None)
 return dv
# ---- quote matching: character-exact, whitespace-tolerant, on raw manuscript text
def qrx(q):
 toks = [t for t in norm(q).split(" ") if t]
 return re.compile(r"\s*".join(re.escape(t) for t in toks), re.I) if toks else None
def span_of(q, texts):
 rx = qrx(q)
 if not rx: return None
 for sid, txt in texts:
  m = rx.search(txt)
  if m: return (sid, m.start(), m.end())
 return None
def build(idx):
 segs = idx.get("segments") or []
 srcs = idx.get("sources") or []
 texts = [(s["id"], qnorm(s.get("text") or "")) for s in srcs if (s.get("text") or "").strip()]
 by = {s["sid"]: s for s in segs}
 starts = [s["start"] for s in segs]
 def seg_at(off):
  i = bisect.bisect_right(starts, off) - 1
  return segs[i] if i >= 0 and off <= segs[i]["end"] + 40 else None
 return segs, by, texts, seg_at
def loc_text(l):
 bits = ["§" + str(l.get("section") or "?")]
 if l.get("paragraph"): bits.append("¶%s" % l["paragraph"])
 if l.get("sentence_id"): bits.append(l["sentence_id"])
 if l.get("page"): bits.append("p.%s" % l["page"])
 if l.get("char_start") is not None: bits.append("chars %s-%s" % (l["char_start"], l["char_end"]))
 return " ".join(bits)
def resolve(raw, ctx, rejected, fixed):
 segs, by, texts, seg_at = ctx
 q = norm(raw.get("quote") or "")
 sid = str(raw.get("sentence_id") or raw.get("sid") or "").strip()
 if not q and sid in by: q = norm(by[sid]["text"])
 if len(q) < 8 and not re.search(r"\d|\[|\]|表|图", q):
  rejected.append({"quote": q[:80], "reason": "quote missing or shorter than 8 chars", "sid": sid}); return None
 hit = span_of(q, texts)
 if not hit:
  rejected.append({"quote": q[:160], "reason": "quote not found verbatim in manuscript", "sid": sid}); return None
 src_id, a, b = hit
 seg = seg_at(a)
 if sid in by and not (a < by[sid]["end"] and b > by[sid]["start"]):
  fixed.append({"given_sid": sid, "corrected_sid": seg["sid"] if seg else None,
                "quote": q[:120], "action": "locator auto-corrected from verbatim match"})
  sid = seg["sid"] if seg else ""
 loc = {"section": seg["section"] if seg else (raw.get("locator") or {}).get("section"),
        "paragraph": seg["para"] if seg else None, "sentence_id": seg["sid"] if seg else (sid or None),
        "page": seg["page"] if seg else None, "char_start": a, "char_end": b, "source_id": src_id}
 return {"quote": by[seg["sid"]]["text"] if (seg and norm(q) == norm(seg["text"])) else q, "locator": loc}
def checks_of(raw, issues):
 out = {}
 for k in CATS:
  src = (raw.get("checks") or {}).get(k) or {}
  st = str(src.get("status") or "").strip().lower()
  st = st if st in CS else ("issues_found" if any(i["category"] == k for i in issues) else "partial")
  if st == "ok" and any(i["category"] == k for i in issues): st = "issues_found"
  out[k] = {"status": st, "scope": src.get("scope") or ("reviewed by skill agent" if st != "partial" else
   "not fully reviewed - see unreviewed / pending_human"),
   "items_checked": src.get("items_checked") or sum(1 for i in issues if i["category"] == k),
   "findings": src.get("findings") or [i["id"] for i in issues if i["category"] == k],
   "unreviewed": src.get("unreviewed") or [], "note": src.get("note") or ""}
 return out
def build_issues(raw_list, ctx, rejected, fixed, res):
 out, seen = [], {}
 for raw in raw_list or []:
  if not isinstance(raw, dict): continue
  cat = cat_of(raw.get("category") or raw.get("type") or raw.get("check_item"))
  if not cat: cat = cat_of(raw.get("check_item")) or "argument"
  sev = sev_of(raw.get("severity") or raw.get("level"))
  r = resolve(raw, ctx, rejected, fixed)
  if not r: continue
  key = (cat, norm(r["quote"])[:140])
  if key in seen: continue
  seen[key] = 1
  ev = []
  for e in (raw.get("evidence") or [])[:6]:
   if isinstance(e, dict) and e.get("quote"):
    er = resolve(e, ctx, rejected, fixed)
    if er: ev.append({"quote": er["quote"], "locator": er["locator"], "kind": e.get("kind") or "support"})
  out.append({"category": cat, "severity": sev, "title": (raw.get("title") or "").strip()[:160],
              "locator": r["locator"], "locator_text": loc_text(r["locator"]), "quote": r["quote"], "evidence": ev,
              "reason": (raw.get("reason") or "").strip(), "suggestion": (raw.get("suggestion") or "").strip(),
              "severity_basis": raw.get("severity_basis") or {"affects_main_conclusion": None, "fixable_by": "",
                                                              "affects_reproducibility": None},
              "check_item": raw.get("check_item") or (cat + ":manual"), "confidence": raw.get("confidence") or "medium",
              "status": "pending_human" if str(raw.get("status") or "").lower().startswith("pending") else "confirmed",
              "basis": raw.get("basis") or "agent"})
 out.sort(key=lambda i: (RANK[i["severity"]], i["locator"]["char_start"] or 0))
 for n, i in enumerate(out, 1): i["id"] = "R%02d" % n
 bad = [i["id"] for i in out if not i["reason"] or not i["suggestion"]]
 if bad: res["review_records"]["issues_missing_reason_or_suggestion"] = bad
 return [{k: i[k] for k in ("id", "category", "severity", "severity_basis", "title", "locator", "locator_text",
                            "quote", "evidence", "reason", "suggestion", "check_item", "confidence", "status", "basis")}
         for i in out]
def claims_of(segs):
 CL = re.compile(r"\b(therefore|thus|hence|these (?:results|findings|data)|our (?:results|findings|data)|we (?:show|"
  r"showed|demonstrate|demonstrated|find|found|conclude|concluded)|this (?:study|work|paper) (?:shows|demonstrates|"
  r"provides|suggests|reveals)|indicat\w+|suggest\w+|reveal\w+)\b|因此|因而|表明|说明|证明|证实|提示", re.I)
 out = []
 for s in segs:
  if len(out) >= 200: break
  if not (CL.search(s["text"]) or s["section"] in ("Abstract", "Conclusion")): continue
  t = s["text"]
  kind = "assumption" if re.search(r"assum|假设|假定|为简化|for simplicity", t, re.I) else (
   "others_view" if re.search(r"reported by|according to|已有研究|据.{0,8}报道", t, re.I) else (
    "citation" if re.search(r"\[\d", t) else ("own_data" if re.search(r"\d|表\s*\d|图\s*\d", t) else "none")))
  out.append({"sid": s["sid"], "section": s["section"], "page": s["page"], "kind": kind, "quote": t[:400],
              "support_type": {"own_data": "own_data", "citation": "citation", "assumption": "assumption"}.get(kind, "none"),
              "support_refs": re.findall(r"\[(\d{1,3})\]", t)[:6]})
 return out
def report(cid, res, art):
 L = ["# 论文逻辑与论证审查报告", "", "- case_id: `%s`" % cid, "- status: **%s**" % res["status"],
      "- generated: %s (skill paper-argument-audit v%s)" % (now(), V), "- 问题总数: %d（%s）" % (
       res["summary"]["total_issues"], "，".join("%s %d" % (s, res["summary"]["counts_by_severity"][s]) for s in SEVS)),
      "", "## 1 结论摘要", ""]
 L.append(res.get("verdict") or ("本轮审查产出 %d 条带定位与逐字原文的问题；阻断项 %d 条。%s" % (
  res["summary"]["total_issues"], len(res["summary"]["blockers"]),
  "存在阻断性问题，主结论或方法-问题匹配需先修。" if res["summary"]["blockers"] else "未见阻断性问题，其余按严重度排序修改。")))
 top = [i for i in res["issues"] if i["severity"] in ("blocker", "major")][:5]
 for i in top: L.append("- **%s** [%s/%s] %s — `%s`" % (i["id"], i["severity"], i["category"], i["title"] or i["reason"][:60], i["locator_text"]))
 L += ["", "## 2 问题清单", "", "| ID | 类别 | 严重度 | 位置 | 问题 |", "|-|-|-|-|-|"]
 for i in res["issues"]:
  L.append("| %s | %s | %s | `%s` | %s |" % (i["id"], LABEL[i["category"]], i["severity"], i["locator_text"],
   (i["title"] or i["reason"])[:70].replace("|", "/").replace("\n", " ")))
 L += ["", "## 3 逐条意见", ""]
 for i in res["issues"]:
  L += ["### %s [%s / %s] %s" % (i["id"], i["severity"], LABEL[i["category"]], i["title"] or "（未命名）"), "",
        "- 位置: `%s`" % i["locator_text"], "- 检查项: `%s`，置信度: %s，状态: %s" % (i["check_item"], i["confidence"], i["status"]),
        "- 原文:", "", "> " + i["quote"].replace("\n", " "), "", "- 判断依据: " + (i["reason"] or "（缺失）"), "",
        "- 修改建议: " + (i["suggestion"] or "（缺失）")]
  if i["evidence"]:
   L += ["- 佐证:"]
   for e in i["evidence"]: L += ["  - `%s` %s" % (e["locator"]["sentence_id"], e["quote"][:160])]
  sb = i["severity_basis"] or {}
  L += ["- 严重度判据: 影响主结论=%s；可修正方式=%s；影响可复现=%s" % (
   sb.get("affects_main_conclusion"), sb.get("fixable_by") or "补证据/降强度", sb.get("affects_reproducibility")), ""]
 L += ["## 4 六类检查覆盖", "", "| 检查项 | 状态 | 覆盖范围 | 发现 | 未审 |", "|-|-|-|-|-|"]
 for k in CATS:
  c = res["checks"][k]
  L.append("| %s `%s` | %s | %s | %s | %s |" % (LABEL[k], k, c["status"], (c["scope"] or "")[:60],
   ", ".join(c["findings"]) or "-", ", ".join(str(u) for u in c["unreviewed"]) or "-"))
 L += ["", "## 5 待复核与材料缺口", ""]
 for x in res["pending_human"] or ["（无）"]: L.append("- 待复核: %s" % (x.get("quote") if isinstance(x, dict) else x))
 for x in res["uncertainty"] or []: L.append("- 不确定: %s" % x)
 for x in res["degradations"] or []: L.append("- 降级: %s" % x)
 L += ["", "## 6 运行记录与复现", "", "```bash", "python3 -B scripts/audit.py --input /input --output /app/output",
       "# 写入 issues_draft.json 后", "python3 -B scripts/verify.py --input /input --output /app/output", "```", "",
       "- 产物: `result.json`、`review_report.md`、`issues.csv`（另有 `audit_digest.md`、`.audit/index.json`）",
       "- 校验: quote 逐字命中 %d 条，拒收 %d 条（见 pending_human）" % (len(res["issues"]), len(res["pending_human"])),
       "- %s" % "; ".join("%s=%s" % (k, art[k]) for k in sorted(art))]
 return "\n".join(L) + "\n"
def main():
 ap = argparse.ArgumentParser(description="review-04 finalizer: verify quotes, derive locators, fill "
  "output_contract, write result.json + review_report.md + issues.csv. Exit code always 0.")
 ap.add_argument("--input", help="input dir (default /input)")
 ap.add_argument("--output", help="output dir (default /app/output)")
 ap.add_argument("--issues", help="findings file (default <output>/issues_draft.json)")
 ap.add_argument("--version", action="version", version=V)
 a = ap.parse_args()
 inp = Path(a.input) if a.input else next((p for p in map(Path, ("/input", "input", "../input")) if p.is_dir()), Path("/input"))
 outp = Path(a.output) if a.output else (Path("/app/output") if Path("/app").is_dir() else Path("output"))
 try: outp.mkdir(parents=True, exist_ok=True)
 except OSError: outp = Path("output"); outp.mkdir(parents=True, exist_ok=True)
 res = {"case_id": None, "status": "partial", "summary": {}, "issues": [], "candidate_issues": [], "claims": [],
        "checks": {k: {"status": "partial", "scope": "", "items_checked": 0, "findings": [], "unreviewed": ["not run"],
                       "note": ""} for k in CATS},
        "review_records": {"rounds": 1, "script": "verify.py", "version": V}, "sources": [], "uncertainty": [],
        "pending_human": [], "errors": [], "degradations": [], "changes": [], "runtime": {}, "artifacts": {},
        "output_contract": {}}
 wj(outp / "result.json", res)
 try:
  ct, cid, case = {}, None, lj(inp / "case.json", {}) if inp.is_dir() else {}
  for c in sorted(inp.glob("**/case*.json")) if inp.is_dir() else []:
   case = lj(c, {}) or case
   if not ct: ct = (case or {}).get("output_contract") or {}
   cid = cid or (case or {}).get("case_id")
  idx = lj(outp / ".audit" / "index.json", {})
  if not idx:
   res["degradations"].append("scaffold index missing: run scripts/audit.py first")
   res["errors"].append("no .audit/index.json: case inputs were never parsed")
  res["errors"] += [e for e in (idx.get("errors") or []) if e]
  cid = cid or idx.get("case_id") or "case-unknown"
  ct = ct or idx.get("output_contract") or {}
  res["case_id"], res["output_contract"] = cid, ct
  for k, v in cdef(ct).items(): res.setdefault(k, v)
  segs, by, texts, seg_at = build(idx)
  ctx = (segs, by, texts, seg_at)
  res["sources"] = idx.get("sources") and [{"id": s["id"], "path": s["path"], "kind": s["kind"],
   "chars": len(s.get("text") or ""), "segments": len(segs)} for s in idx["sources"]] or []
  draft = lj(Path(a.issues) if a.issues else outp / "issues_draft.json", {})
  raw = [i for i in (draft.get("issues") or []) if isinstance(i, dict)]
  rejected, fixed = [], []
  if not raw or not any((i.get("reason") or "").strip() for i in raw):
   raw = [dict(c, status="confirmed", basis="deterministic_rule", confidence=c.get("confidence") or "high",
               reason="规则确定性判定：" + (c.get("detail") or ""), suggestion="按 references/checks.md 对应修法处理")
          for c in (idx.get("candidate_issues") or []) if c.get("hard")]
   if raw: res["degradations"].append("no agent findings found; only deterministic hard rules were reported")
  res["issues"] = build_issues(raw, ctx, rejected, fixed, res)
  if fixed: res["review_records"]["locator_corrections"] = fixed
  res["claims"] = claims_of(segs)
  res["candidate_issues"] = idx.get("candidate_issues") or []
  res["pending_human"] = [{"quote": r["quote"], "reason": r["reason"], "sid": r["sid"]} for r in rejected]
  res["pending_human"] += [x for x in (draft.get("pending_human") or []) if x]
  res["uncertainty"] = [x for x in (draft.get("uncertainty") or []) if x]
  for s in idx.get("sources") or []:
   res["degradations"] += ["%s: %s" % (Path(s["path"]).name, w) for w in (s.get("warn") or [])]
  res["checks"] = checks_of(draft, res["issues"])
  cnt = {s: sum(1 for i in res["issues"] if i["severity"] == s) for s in SEVS}
  res["summary"] = {"counts_by_category": {k: sum(1 for i in res["issues"] if i["category"] == k) for k in CATS},
                    "counts_by_severity": cnt, "total_issues": len(res["issues"]),
                    "blockers": [i["id"] for i in res["issues"] if i["severity"] == "blocker"],
                    "coverage_note": "%d verified issues over %d sentences; %d rejected quotes; facets: %s" % (
                     len(res["issues"]), len(segs), len(res["pending_human"]),
                     ",".join("%s=%s" % (k, res["checks"][k]["status"]) for k in CATS)),
                    "facet_coverage": {k: res["checks"][k]["status"] for k in CATS}}
  if len(res["issues"]) >= 4 and max(cnt.values()) / len(res["issues"]) > 0.8:
   res["degradations"].append("severity distribution skewed (>80%% on one level); re-check severity_basis")
  res["verdict"] = (draft.get("verdict") or "").strip()
  ok = bool(texts) and bool(segs)
  st = "ok" if ok and (res["issues"] or any(res["checks"][k]["status"] != "partial" for k in CATS)) else "partial"
  if not texts: st = "insufficient_evidence"
  if res["errors"]: st = "partial"
  res["status"] = st
  res["review_records"].update({"audit_scope": {"segments": len(segs), "sources": len(res["sources"]),
   "manuscript_chars": max([len(t) for _, t in texts] or [0])},
   "agent_findings": len(raw), "verified": len(res["issues"]), "rejected_quotes": len(rejected),
   "checks_reported_by_agent": sorted((draft.get("checks") or {}).keys()),
   "rerun_stable": "deterministic ids by (severity, char offset); same input -> same ids",
   "limits": ["引用文献仅做文内-文献表一致性，未联网核验 DOI/全文", "统计问题基于文内报告，未重算原始数据"]})
  res["changes"].append({"at": now(), "action": "finalized", "detail": "%d verified / %d rejected" % (
   len(res["issues"]), len(rejected))})
  rep = report(cid, res, {"issues.csv": "issues.csv", "review_report.md": "review_report.md"})
  (outp / "review_report.md").write_text(rep, encoding="utf-8")
  with (outp / "issues.csv").open("w", newline="", encoding="utf-8") as f:
   w = csv.writer(f)
   w.writerow(["id", "category", "severity", "check_item", "section", "page", "paragraph", "sentence_id",
               "char_start", "char_end", "quote", "reason", "suggestion", "confidence", "status"])
   for i in res["issues"]:
    l = i["locator"]
    w.writerow([i["id"], i["category"], i["severity"], i["check_item"], l.get("section"), l.get("page"),
                l.get("paragraph"), l.get("sentence_id"), l.get("char_start"), l.get("char_end"), i["quote"],
                i["reason"], i["suggestion"], i["confidence"], i["status"]])
  res["artifacts"] = {"result_json": str(outp / "result.json"), "review_report": str(outp / "review_report.md"),
                      "issues_csv": str(outp / "issues.csv"), "audit_digest": str(outp / "audit_digest.md")}
  res["runtime"] = {"skill": "paper-argument-audit", "version": V, "script": "verify.py", "started": now(),
                    "duration_s": round(time.time() - T0, 2)}
  wj(outp / "result.json", res)
 except Exception as e:  # noqa: BLE001
  res["status"] = "partial"; res["errors"].append("finalize exception: %s: %s" % (type(e).__name__, e))
  res["runtime"] = {"skill": "paper-argument-audit", "version": V, "script": "verify.py",
                    "duration_s": round(time.time() - T0, 2)}
  wj(outp / "result.json", res)
 return 0
if __name__ == "__main__":
 sys.exit(main())
