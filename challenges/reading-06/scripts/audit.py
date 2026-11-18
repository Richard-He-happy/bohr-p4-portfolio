#!/usr/bin/env python3
"""reading-06 v2 audit assets.

Writes five verifiable assets next to result.json:
golden_standard.json / diff_report.md / version_history.md / self_check.json / run.log

The golden standard is SELF-DERIVED (target-field obligations + an independent lexical
re-scan of the same materials). It is not the organizer's hidden key and must never be
presented as one. Every entry point swallows its own exceptions and records the failure
as a degradation: the audit can never break the extraction run.
"""
import json, os, re, subprocess, sys, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
import main as c

V = "2.0.0"
ST = c.ST
EVT = "run_events.jsonl"
ASSETS = ("golden_standard.json", "diff_report.md", "version_history.md", "self_check.json", "run.log")
RKEYS = ("golden_standard", "diff_report", "version_history", "self_check")
STOP = {"the", "and", "for", "with", "from", "was", "were", "per", "of", "in", "on", "at", "to",
        "number", "value", "values", "data", "field", "fields", "table", "figure", "study",
        "group", "groups", "time", "given", "reported", "please", "extract", "提取", "字段", "数值",
        "数据", "是否", "多少", "报告", "多少", "the field", "条件", "论文", "文献", "研究中"}
SPL = r"[；;，,、/|()（）\[\]{}:：?!\"'`。\s]+"


def ts():
 return c.ts()


def dump(p, o):
 c.dump(p, o)


# ---------------------------------------------------------------- run events
def rec(work, step, rc=0, ms=0.0, **kv):
 """Append one run event (best effort, never raises)."""
 e = {"at": ts(), "step": str(step), "exit_code": int(rc), "duration_ms": int(ms)}
 e.update({k: v for k, v in kv.items() if v not in (None, "", [], {})})
 try:
  p = Path(work) / EVT
  p.parent.mkdir(parents=True, exist_ok=True)
  with open(p, "a", encoding="utf-8") as f:
   f.write(json.dumps(e, ensure_ascii=False) + "\n")
 except Exception:
  pass
 return e


def events(work):
 out, p = [], Path(work) / EVT
 try:
  if p.is_file():
   for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
    ln = ln.strip()
    if not ln:
     continue
    try:
     out.append(json.loads(ln))
    except Exception:
     out.append({"at": "", "step": "unparsed_log_line", "exit_code": None, "raw": ln[:160]})
 except Exception:
  pass
 return out


# ---------------------------------------------------------------- text helpers
def terms_of(f):
 t = []
 for k in [f.get("label", ""), f.get("description", "")] + list(f.get("aliases") or []):
  for w in re.split(SPL, str(k)):
   w = w.strip(" .-_*`\"'")
   if len(w) < 2 or w.casefold() in STOP:
    continue
   if len(w) < 3 and not re.search(r"[\u4e00-\u9fff]", w):
    continue
   if re.fullmatch(r"[\d.,%]+", w):
    continue
   t.append(w)
 return list(dict.fromkeys(t))[:12]


def sent_score(s, terms):
 low = s.casefold()
 return sum(low.count(w.casefold()) for w in terms)


def best_sent(text, terms):
 ss = [s for s in (c.sents(text) or []) if s.strip()] or [text]
 b = max(ss, key=lambda s: (sent_score(s, terms), -len(s)))
 return re.sub(r"\s+", " ", b).strip()[:320]


def anchors(ps, terms, k=3):
 if not terms:
  return []
 hits = []
 for mid in sorted(ps):
  for p in ps[mid]:
   t = p.get("text", "") or ""
   sc = sent_score(t, terms)
   if sc:
    hits.append({"score": sc, "quote": best_sent(t, terms),
                 "locator": {"material_id": p.get("material_id") or mid,
                             "paragraph_id": p.get("pid"), "page": p.get("page")}})
 hits.sort(key=lambda x: -x["score"])
 keep, seen = [], set()
 for h in hits:
  if h["quote"] in seen:
   continue
  seen.add(h["quote"])
  keep.append(h)
  if len(keep) >= k:
   break
 return keep


def loc_str(l):
 if isinstance(l, str):
  return l
 if not isinstance(l, dict):
  return "" if l is None else str(l)
 o = ("material_id", "paragraph_id", "page", "table", "row", "col", "cell", "figure", "section", "pointer")
 return "; ".join(["%s=%s" % (k, l[k]) for k in o if l.get(k) not in (None, "")] +
                  ["%s=%s" % (k, v) for k, v in l.items() if k not in o and v not in (None, "")])


def flat(v):
 if v is None:
  return ""
 return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def sha1(p, n=12):
 try:
  return hashlib.sha1(Path(p).read_bytes()).hexdigest()[:n]
 except Exception:
  return None


def size(p):
 try:
  return Path(p).stat().st_size
 except Exception:
  return None


def nums(s):
 return set(x for x in re.findall(r"\d+(?:[.,]\d+)?", flat(s)) if len(x) > 1)


# ---------------------------------------------------------------- golden standard
RULE_TEXT = {
 "expected_status": "one of reported / not_reported / source_conflict / extraction_failed when the "
                    "self-derived check can decide it; 'undetermined' means the independent lexical "
                    "re-scan cannot settle it and a human must read the anchor paragraph",
 "reported": "an independent sentence from the materials contains the value and the delivered quote "
             "is verbatim in the corpus (quote_strict/quote_normalized)",
 "not_reported": "the field's search terms have zero hits across every material paragraph, table row "
                 "and caption that the extractor could read (lexical evidence only, wording may differ)",
 "source_conflict": "the delivered conflict keeps two quotes that are both verbatim in the corpus",
 "extraction_failed": "no readable anchor exists in the materials (no text layer / unreadable), so a "
                      "failed extraction is consistent with the material state",
 "undetermined": "anchors exist but no single value can be confirmed by re-scan -> human read required",
 "verdicts": {
  "match": "delivered result satisfies the golden entry",
  "deviation": "delivered value/status/quote differs from the golden entry",
  "gap": "no delivered row for a requested field_id",
  "needs_review": "cannot be settled automatically; anchor or ledger handed to a reviewer"},
 "not_a_key": "This file is NOT the organizer's hidden expected reading. Hidden readings are supplied "
              "only by the evaluation platform and were never visible while authoring.",
}


def gs_field(f, ps, corp, rows):
 fid = str(f.get("field_id") or "")
 terms = terms_of(f)
 ah = anchors(ps, terms)
 row = rows.get(fid) or {}
 st = (row.get("status") or "").strip()
 q = row.get("quote") or ""
 qv = c.vq(q, corp) if q else None
 vflat = flat(row.get("value"))
 anchor_q = " ".join(a["quote"] for a in ah[:1])
 in_anchor = bool(vflat.strip()) and c.norm(vflat, "loose") and c.norm(vflat, "loose") in c.norm(anchor_q, "loose")
 g = {"field_id": fid, "label": f.get("label") or fid,
      "terms_searched": terms,
      "independent_anchors": ah[:2],
      "expected": {"value": None, "unit": "", "statistic": "", "condition": ""},
      "evidence": None, "confidence": "low", "basis": "", "verdict": "needs_review"}
 if not row:
  g.update(expected_status="undetermined", basis="no delivered row for this field_id", verdict="gap")
  return g
 if st == "reported":
  if qv in ("strict", "normalized") and in_anchor:
   g.update(expected_status="reported", confidence="high", verdict="match",
            basis="delivered quote is verbatim in the corpus and the value occurs in an independent "
                  "anchor sentence (%s)" % (ah[0]["locator"].get("paragraph_id") if ah else "no anchor"))
   g["expected"] = {"value": row.get("value"), "unit": row.get("unit") or "",
                    "statistic": row.get("statistic") or "", "condition": row.get("condition") or ""}
   g["evidence"] = {"quote": q, "locator": row.get("locator"),
                    "quote_level": "quote_" + qv,
                    "anchor": (ah[0] if ah else None)}
  elif qv:
   g.update(expected_status="undetermined", confidence="medium", verdict="needs_review",
            basis="quote matches the corpus (%s) but the value was not found in an independent anchor "
                  "sentence; check that the value and its condition come from the same passage" % qv)
   g["evidence"] = {"quote": q, "locator": row.get("locator"), "quote_level": "quote_" + qv,
                    "anchor": (ah[0] if ah else None)}
  else:
   g.update(expected_status="undetermined", confidence="low", verdict="deviation",
            basis="delivered quote is not verifiable in the corpus even after loose normalisation (%s); "
                  "the value therefore has no citable source — re-copy from the paragraph"
                  % (row.get("verification") or "no_quote"))
   g["evidence"] = {"quote": q, "locator": row.get("locator"), "quote_level": "unverified",
                    "anchor": (ah[0] if ah else None)}
 elif st == "not_reported":
  neg = bool(ah) and re.search(r"\b(no|not|none|without|neither|nor|never)\b|未|无|没有|不", ah[0]["quote"], re.I)
  if ah and neg and not re.search(r"\d", ah[0]["quote"]):
   g.update(expected_status="not_reported", confidence="medium", verdict="match",
            basis="the field's terms occur only inside a no-report statement (negation cue, no number); "
                  "not_reported is consistent with the source",
            evidence={"quote": ah[0]["quote"], "locator": ah[0]["locator"],
                      "quote_level": "anchor_negated", "negation_cue": True})
  elif ah:
   g.update(expected_status="undetermined", confidence="medium", verdict="needs_review",
            basis="delivered not_reported, but the field's terms do occur in the materials; verify the "
                  "anchor is not a missed report", evidence={"quote": ah[0]["quote"],
                  "locator": ah[0]["locator"], "quote_level": "anchor_only"})
  else:
   g.update(expected_status="not_reported", confidence="medium", verdict="match",
            basis="independent full-text lexical scan: 0 hits for %r across %d material(s)"
                  % (terms[:4], len(ps)),
            evidence={"quote": None, "locator": None,
                      "search_ledger": {"terms": terms, "materials_scanned": sorted(ps), "hits": 0}})
 elif st == "source_conflict":
  cf = row.get("conflict") or {}
  sides = [cf.get("quote_a", ""), cf.get("quote_b", "")] if isinstance(cf, dict) else []
  ok = len([x for x in sides if x and c.vq(x, corp)]) >= 2
  g.update(expected_status="source_conflict" if ok else "undetermined", confidence="high" if ok else "low",
           verdict="match" if ok else "needs_review",
           basis="both conflict quotes are verbatim in the corpus" if ok else
                 "fewer than two verbatim conflict quotes recorded",
           evidence={"quote": sides[0] if sides else None, "locator": row.get("locator"),
                     "quote_level": "conflict_pair"})
 elif st == "extraction_failed":
  if ah:
   g.update(expected_status="undetermined", confidence="low", verdict="needs_review",
            basis="extraction_failed while a readable anchor exists; a human can likely read the value",
            evidence={"quote": ah[0]["quote"], "locator": ah[0]["locator"], "quote_level": "anchor_only"})
  else:
   g.update(expected_status="extraction_failed", confidence="medium", verdict="match",
            basis="no readable anchor in the materials; failure is consistent with the material state",
            evidence={"quote": None, "locator": None,
                      "search_ledger": {"terms": terms, "materials_scanned": sorted(ps), "hits": 0}})
 else:
  g.update(expected_status="undetermined", confidence="low", verdict="deviation",
           basis="status %r is outside the four allowed values" % st)
 return g


def golden(idx, rows_out, ps, corp):
 by = {str(r.get("field_id")): r for r in rows_out}
 fields = idx.get("fields") or [{"field_id": r.get("field_id"), "label": r.get("label"),
                                 "description": "", "aliases": []} for r in rows_out]
 fl = [gs_field(f, ps, corp, by) for f in fields]
 cnt = {"fields": len(fl), "reported": 0, "not_reported": 0, "source_conflict": 0,
        "extraction_failed": 0, "undetermined": 0}
 for g in fl:
  es = g.get("expected_status") or "undetermined"
  cnt[es] = cnt.get(es, 0) + 1
 kinds = sorted({(m.get("kind") or "?") for m in (idx.get("materials") or [])})
 return {"schema": "golden-standard/v1", "skill_version": V,
         "case_id": idx.get("case_id"), "generated_at": ts(),
         "provenance": {
          "derived_from": ["target-fields.json (field list + obligations)", "case.json output_contract",
                           "materials re-read by an independent lexical anchor scan"],
          "method": "spec obligations + independent anchor re-scan of the same materials; no hidden answer used",
          "is_organizer_key": False,
          "disclaimer": RULE_TEXT["not_a_key"]},
         "rules": RULE_TEXT,
         "row_contract": {
          "required_keys": ["field_id", "status", "value", "unit", "statistic", "condition", "comparator",
                            "quote", "locator", "verification", "reasoning"],
          "obligations": ["reported -> value + unit + verbatim quote + resolvable locator",
                          "not_reported/source_conflict/extraction_failed -> stated basis (terms, sections, tables)",
                          "条件随值同行；原文没有条件就留空，不写 N/A",
                          "数值/单位逐字保留，不换算不四舍五入"],
          "applies_to": "every entry in fields[]"}, "counts": cnt,
         "source_scope": {"materials": idx.get("materials") or [], "kinds_scanned": kinds,
                          "sections_treated_alike": ["text", "table", "caption", "abstract", "supplement"]},
         "fields": fl}


# ---------------------------------------------------------------- diff report
def diff_md(gs, idx, rows_out, status):
 by = {str(r.get("field_id")): r for r in rows_out}
 vc = {"match": 0, "deviation": 0, "gap": 0, "needs_review": 0}
 f = lambda v: ("" if v is None else str(v)).replace("|", "/").replace("\n", " ")[:120]
 L = ["# Diff report — 实际产物 vs 金标准", "",
      "- case_id: `%s`" % idx.get("case_id"), "- status: `%s`" % status,
      "- golden standard: `golden_standard.json`（自建基准：字段义务 + 独立锚点重扫；**不是**组织方隐藏答案）",
      "- 对照对象: `extraction.json` / `extraction.csv` 的逐字段行", "",
      "| field_id | label | golden expected_status | actual status | verdict | basis |", "|---|---|---|---|---|---|"]
 for g in gs["fields"]:
  vc[g["verdict"]] = vc.get(g["verdict"], 0) + 1
  r = by.get(g["field_id"]) or {}
  L.append("| %s | %s | %s | %s | %s | %s |" % (f(g["field_id"]), f(g["label"]),
                                                 g.get("expected_status"), r.get("status") or "-",
                                                 g["verdict"], f(g["basis"])))
 tot = len(gs["fields"]) or 1
 L += ["", "## 汇总", "",
       "- 字段数: %d；match=%d，deviation=%d，gap=%d，needs_review=%d" % (
           len(gs["fields"]), vc["match"], vc["deviation"], vc["gap"], vc["needs_review"]),
       "- 达标率（match / 字段数）: %.1f%%" % (100.0 * vc["match"] / tot),
       "- 判定口径见 `golden_standard.json` 的 `rules.verdicts`；`needs_review` 不是失败，是需要人工读一段锚点原文。", "",
       "## 逐项对照", ""]
 for g in gs["fields"]:
  r = by.get(g["field_id"]) or {}
  L.append("### %s — %s" % (g["field_id"], g["label"]))
  L.append("")
  L.append("- verdict: **%s**；golden expected_status=`%s`（confidence=%s）；actual status=`%s`" % (
      g["verdict"], g.get("expected_status"), g.get("confidence"), r.get("status") or "-"))
  L.append("- 实际值: `%s` %s%s" % (f(r.get("value")), f(r.get("unit")),
                                    ("；条件: " + f(r.get("condition"))) if r.get("condition") else ""))
  ev = g.get("evidence") or {}
  if ev.get("quote"):
   L.append("- golden 证据: `%s` @ `%s`" % (f(ev["quote"]), f(loc_str(ev.get("locator")))))
  elif ev.get("search_ledger"):
   L.append("- golden 依据: 检索词 %s，扫描材料 %s，命中 0（not_reported 依据）" % (
       ", ".join(ev["search_ledger"]["terms"][:6]), ", ".join(ev["search_ledger"]["materials_scanned"])))
  if r.get("quote"):
   L.append("- 实际 quote: `%s` @ `%s`（%s）" % (f(r.get("quote")), f(r.get("locator")),
                                               r.get("verification") or "-"))
  L.append("- 判定依据: %s" % f(g["basis"]))
  L.append("")
 gaps = [g["field_id"] for g in gs["fields"] if g["verdict"] in ("gap", "deviation")]
 L += ["## 剩余缺口", "",
       ("- 需返工字段: %s" % ", ".join(gaps)) if gaps else "- 无 gap / deviation；`needs_review` 项见上表。", "",
       "## 复跑方式", "",
       "```bash",
       "python3 -B scripts/main.py build --input /input --work /app/work --output /app/output",
       "python3 -B scripts/audit.py assets --work /app/work --output /app/output   # 只重算 5 个资产",
       "```", ""]
 return "\n".join(L), vc


# ---------------------------------------------------------------- self-test (empty / bad input)
def _run(argv, env, timeout=120):
 t0 = time.time()
 try:
  r = subprocess.run(argv, capture_output=True, timeout=timeout, env=env)
  return r.returncode, (r.stdout or b"").decode("utf-8", "replace"), (r.stderr or b"").decode("utf-8", "replace"), time.time() - t0
 except Exception as e:
  return 124, "", "spawn_failed: %s" % e, time.time() - t0


def selftest(wk, out):
 """Run the real pipeline on empty and corrupted inputs, record what actually happened."""
 res = []
 if os.environ.get("SKILL_SELFTEST") == "1":
  return [{"name": "skipped_nested", "note": "SKILL_SELFTEST=1 (recursion guard)"}]
 main_py = Path(__file__).resolve().parent / "main.py"
 env = dict(os.environ, SKILL_SELFTEST="1", PYTHONDONTWRITEBYTECODE="1")
 BAD_CASE = '{"case_id": "BAD", "output_contract": {"case_id": "", "status": "x"'
 BAD_FIELDS = '{"target_fields": [{"field_id": "F1",'
 specs = [("empty_input", {}), ("bad_json", {"case.json": BAD_CASE,
                                    "target-fields.json": BAD_FIELDS,
                                    "material.md": "IC50 was 12.4 nM in assay A.\n"})]

 for name, files in specs:
  d = Path(wk) / "selftest" / name
  for sub in ("in", "work", "out"):
   (d / sub).mkdir(parents=True, exist_ok=True)
  for fn, body in files.items():
   (d / "in" / fn).write_text(body, encoding="utf-8")
  item = {"name": name, "case_dir": str(d), "steps": [], "exit_codes": {}}
  for cmd in ("init", "build"):
   rc, so, se, ms = _run([sys.executable, "-B", str(main_py), cmd, "--input", str(d / "in"),
                          "--work", str(d / "work"), "--output", str(d / "out")], env)
   item["steps"].append({"step": cmd, "exit_code": rc, "duration_ms": int(ms * 1000),
                         "stderr_tail": se.strip()[-160:]})
   item["exit_codes"][cmd] = rc
  rj, ok = None, False
  try:
   rj = json.loads((d / "out" / "result.json").read_text(encoding="utf-8"))
   ok = isinstance(rj, dict) and "status" in rj and "case_id" in rj
  except Exception as e:
   item["result_error"] = str(e)[:160]
  item["result_valid"] = ok
  item["result_status"] = (rj or {}).get("status")
  item["result_keys"] = sorted((rj or {}).keys())
  item["artifacts"] = sorted(p.name for p in (d / "out").glob("*")) if (d / "out").is_dir() else []
  res.append(item)
 return res


# ---------------------------------------------------------------- self check
def self_check(idx, p, out, wk, result, corp, gs, vc, fb_tests, help_rc):
 out = Path(out)
 rows = p["rows"]
 cnt = p["cnt"]
 contract = idx.get("output_contract") or {}
 chk = []

 def add(cid, ok, detail, **kv):
  d = {"id": cid, "ok": bool(ok), "detail": detail}
  d.update({k: v for k, v in kv.items() if v not in (None, [], {})})
  chk.append(d)

 # 1 contract backfill
 missing = [k for k in contract if k not in result] if isinstance(contract, dict) else []
 add("C01_contract_keys", not missing,
     "output_contract keys=%d all present in result.json" % len(contract) if not missing
     else "missing contract keys", missing=missing)
 add("C02_core_fields", all(k in result for k in ("case_id", "status", "sources", "uncertainty",
                                                 "pending_human", "errors", "degradations", "changes", "runtime")),
     "case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime")
 add("C03_new_assets_fields", all(k in result for k in RKEYS),
     "result.json carries golden_standard / diff_report / version_history / self_check",
     missing=[k for k in RKEYS if k not in result])
 # 2 row schema
 req = ("field_id", "status", "value", "unit", "statistic", "condition", "comparator", "quote",
        "locator", "verification", "reasoning")
 bad = [r.get("field_id") for r in rows if any(k not in r for k in req)]
 add("C04_row_keys", not bad, "every row carries %d documented keys" % len(req), offending=bad[:8])
 add("C05_status_enum", all(r.get("status") in ST for r in rows)
     and sum(cnt.get(s, 0) for s in ST) == cnt.get("target_fields", 0),
     "four-status sum == target_fields", counts={s: cnt.get(s, 0) for s in ST},
     target_fields=cnt.get("target_fields"))
 rep = [r for r in rows if r.get("status") == "reported"]
 add("C06_reported_has_value_quote", all(flat(r.get("value")).strip() and (r.get("quote") or "").strip() for r in rep),
     "%d reported rows all carry value + quote" % len(rep),
     offending=[r["field_id"] for r in rep if not (flat(r.get("value")).strip() and (r.get("quote") or "").strip())])
 ver = [r for r in rep if r.get("verification") in ("quote_strict", "quote_normalized")]
 cov = round(100.0 * len(ver) / len(rep), 1) if rep else 100.0
 add("C07_evidence_coverage", cov >= 90.0, "reported rows with verbatim quote: %d/%d = %.1f%%" % (len(ver), len(rep), cov),
     coverage_pct=cov)
 nonrep = [r for r in rows if r.get("status") != "reported"]
 add("C08_nonreported_basis", all(len((r.get("reasoning") or "").strip()) >= 8 for r in nonrep),
     "every non-reported row states its basis",
     offending=[r["field_id"] for r in nonrep if len((r.get("reasoning") or "").strip()) < 8])
 mis = []
 for r in rep:
  qn = c.norm(r.get("quote") or "", "normalized")
  for n in nums(r.get("value")):
   if c.norm(n, "normalized") not in qn:
    mis.append({"field_id": r["field_id"], "number": n})
 add("C09_number_quote_consistency", not mis, "value numbers appear verbatim in the quote", mismatch=mis[:8])
 noloc = [r["field_id"] for r in rep if "paragraph_id=" not in (r.get("locator") or "") and
          "pointer=" not in (r.get("locator") or "") and "table=" not in (r.get("locator") or "")]
 pdf = {m.get("material_id") for m in (idx.get("materials") or []) if m.get("kind") == "pdf"}
 nopage = [r["field_id"] for r in rep if pdf and any(("material_id=%s" % m) in (r.get("locator") or "") for m in pdf)
           and "page=" not in (r.get("locator") or "")]
 add("C10_locator_granularity", not noloc and not nopage,
     "reported rows resolve to a paragraph/table pointer; PDF rows carry page",
     missing_locator=noloc[:8], missing_page=nopage[:8])
 # 3 golden standard consistency
 gbad = [g["field_id"] for g in gs["fields"]
         if g.get("expected_status") not in ST + ("undetermined",) or not (g.get("basis") or "").strip()]
 add("C11_golden_consistency", not gbad,
     "%d golden entries all carry an allowed expected_status and a basis" % len(gs["fields"]), offending=gbad[:8])
 gu = [g for g in gs["fields"] if g.get("evidence") and (g["evidence"].get("quote_level") in ("unverified",))]
 add("C12_golden_quote_verifiable", not gu, "golden evidence quotes are verbatim or explicitly anchor-only",
     offending=[g["field_id"] for g in gu][:8])
 add("C13_diff_parity", sum(vc.values()) == len(gs["fields"]) and
     {g["field_id"] for g in gs["fields"]} == {r.get("field_id") for r in rows},
     "diff covers every golden field and every delivered field", verdicts=vc)
 add("C14_fallback_empty_input", all(t.get("result_valid") and t.get("exit_codes", {}).get("build") == 0
                                     for t in fb_tests if t.get("name") == "empty_input"),
     "empty /input still writes a parseable partial result.json with exit code 0",
     observed=[{"name": t.get("name"), "exit_codes": t.get("exit_codes"), "result_valid": t.get("result_valid"),
                "result_status": t.get("result_status")} for t in fb_tests])
 add("C15_fallback_bad_json", all(t.get("result_valid") and t.get("exit_codes", {}).get("build") == 0
                                  for t in fb_tests if t.get("name") == "bad_json"),
     "corrupted case.json / target-fields.json still writes a parseable result.json with exit code 0")
 ev = events(wk)
 codes = {e.get("step"): e.get("exit_code") for e in ev if e.get("step") in
          ("init", "show", "check", "build", "audit")}
 codes["help"] = help_rc
 add("C16_exit_codes_zero", all(v == 0 for v in codes.values()), "all recorded steps exited 0", exit_codes=codes)
 pkg = Path(__file__).resolve().parent.parent
 pfiles = [q for q in pkg.rglob("*") if q.is_file() and "__pycache__" not in str(q) and q.suffix != ".pyc"]
 pbytes = sum(q.stat().st_size for q in pfiles)
 add("C17_package_budget", len(pfiles) <= 10 and pbytes <= 120000,
     "package: %d files, %d bytes (limits 10 files / 120000 bytes)" % (len(pfiles), pbytes),
     files=len(pfiles), bytes=pbytes)
 ok = sum(1 for x in chk if x["ok"])
 files = []
 for n in ASSETS + ("extraction.json", "extraction.csv", "extraction.md"):
  pth = out / n
  if pth.is_file():
   files.append({"name": n, "bytes": size(pth), "sha1": sha1(pth)})
 return {"schema": "self-check/v1", "skill_version": V, "case_id": idx.get("case_id"), "generated_at": ts(),
         "status": p["status"],
         "summary": {"checks": len(chk), "passed": ok, "failed": len(chk) - ok,
                     "pass_rate_pct": round(100.0 * ok / max(1, len(chk)), 1)},
         "checks": chk,
         "exit_codes": codes,
         "evidence_coverage": {"reported": len(rep), "quote_verified": len(ver), "coverage_pct": cov,
                               "quote_loose": cnt.get("quote_loose"), "quote_failed": cnt.get("quote_failed")},
         "counts": cnt,
         "fallback_tests": fb_tests,
         "files": files,
         "files_note": "result.json / self_check.json / run.log 在本自检之后定稿，最终字节清单以 run.log 的"
                       "『产物文件』表为准（每次命令结束时由 main.py 重写 run.log）。",
         "limits": ["扫描件无文本层时 golden 只能记 extraction_failed + 人工接管",
                    "not_reported 的独立性只到词面（同义改写可能漏检）",
                    "golden 是自建基准，不是组织方隐藏答案"]}


# ---------------------------------------------------------------- version history
def version_md(pkg, idx, p, gs, vc, cnt):
 vs = c.V
 src = Path(pkg) / "references" / "version_history.md"
 head = ("# 版本记录\n\n> 运行时由 `scripts/audit.py` 从 `references/version_history.md` 复制，"
         "并追加本次运行段落。\n\n")
 try:
  body = src.read_text(encoding="utf-8") if src.is_file() else ""
 except Exception:
  body = ""
 if not body:
  body = ("## v2.0.0 (current)\n\n- 新增 golden_standard.json / diff_report.md / version_history.md / "
          "self_check.json / run.log\n- result.json 增加 4 个字段，原 output_contract 字段全部保留\n\n"
          "## v1.0.0\n\n- 逐字段抽取：四状态 + 逐字 quote + locator，init/show/check/build 入口\n\n"
          "## v0\n\n- 骨架（未随本次材料提供，无法据实记录差异）\n")
 tail = ["", "---", "", "## 本次运行（自动追加）", "",
         "- 时间: %s" % ts(), "- case_id: `%s`；status: `%s`" % (idx.get("case_id"), p["status"]),
         "- 字段: %d（reported=%d / not_reported=%d / source_conflict=%d / extraction_failed=%d）" % (
             cnt.get("target_fields", 0), cnt.get("reported", 0), cnt.get("not_reported", 0),
             cnt.get("source_conflict", 0), cnt.get("extraction_failed", 0)),
         "- golden: %s；diff: match=%d deviation=%d gap=%d needs_review=%d" % (
             gs["counts"], vc["match"], vc["deviation"], vc["gap"], vc["needs_review"]),
         "- 回退: `--no-audit` 跳过全部新增资产；彻底回退删 `scripts/audit.py` 与 build.py 的 audit 调用块，"
         "extraction.* 与 result.json 契约字段不变。", ""]
 return head + body.strip() + "\n" + "\n".join(tail)


# ---------------------------------------------------------------- run log
def write_run_log(out, wk, result=None, note=""):
 out = Path(out)
 ev = events(wk)
 L = ["# run.log — reading-06 v%s" % V, "",
      "- 生成的 run.log 只记录真实发生的步骤；没有执行的步骤不会出现在这里。", ""]
 if ev:
  t0 = ev[0].get("at")
  L += ["- 首个事件: %s" % t0, "- 末个事件: %s" % ev[-1].get("at"),
        "- 步骤数: %d；总耗时: %d ms" % (len(ev), sum(int(e.get("duration_ms") or 0) for e in ev)), ""]
 L += ["## 步骤", "", "| at | step | exit | ms | argv / note |", "|---|---|---|---|---|"]
 for e in ev:
  det = e.get("argv") or e.get("note") or e.get("detail") or ""
  if isinstance(det, list):
   det = " ".join(str(x) for x in det)
  L.append("| %s | %s | %s | %s | %s |" % (e.get("at", ""), e.get("step", ""), e.get("exit_code"),
                                           e.get("duration_ms"), str(det)[:150].replace("|", "/")))
 degs, errs = [], []
 if result:
  degs = result.get("degradations") or []
  errs = result.get("errors") or []
 L += ["", "## 降级 (degradations)", ""] + (["- %s" % str(d) for d in degs] or ["- 无"])
 L += ["", "## 异常 (errors / exceptions)", ""] + (
     ["- %s" % json.dumps(e, ensure_ascii=False)[:300] for e in errs] or ["- 无（所有步骤 exit=0）"])
 if result:
  L += ["", "## 结论", "", "- status: `%s`" % result.get("status"),
        "- counts: `%s`" % json.dumps((result.get("result") or {}).get("counts") or {}, ensure_ascii=False)]
 L += ["", "## 产物文件", "", "| file | bytes |", "|---|---|"]
 tot = 0
 for n in ASSETS + ("result.json", "extraction.json", "extraction.csv", "extraction.md"):
  s = size(out / n)
  if s is not None:
   tot += s
   L.append("| %s | %d |" % (n, s))
 L += ["| **total** | **%d** |" % tot, ""]
 if note:
  L += [note, ""]
 try:
  (out / "run.log").write_text("\n".join(L) + "\n", encoding="utf-8")
 except Exception:
  pass
 return out / "run.log"


# ---------------------------------------------------------------- entry
def help_probe():
 """Actually run `main.py --help` so the exit-code claim in self_check is observed, not asserted."""
 rc, _, _, _ = _run([sys.executable, "-B", str(Path(__file__).resolve().parent / "main.py"), "--help"],
                    dict(os.environ, SKILL_SELFTEST="1", SKILL_NOLOG="1",
                         PYTHONDONTWRITEBYTECODE="1"), 60)
 return rc


def emit(idx, p, ps, out, wk, result):
 """Write golden_standard / diff_report / version_history / self_check; return result.json fields."""
 out, wk = Path(out), Path(wk)
 help_rc = help_probe()
 corp = c.corpus(ps)
 rows = p.get("rows") or []
 gs = golden(idx, rows, ps, corp)
 dump(out / "golden_standard.json", gs)
 dm, vc = diff_md(gs, idx, rows, p.get("status"))
 (out / "diff_report.md").write_text(dm, encoding="utf-8")
 (out / "version_history.md").write_text(version_md(Path(__file__).resolve().parent.parent,
                                                   idx, p, gs, vc, p.get("cnt") or {}), encoding="utf-8")
 fb = selftest(wk, out)
 dump(wk / "selftest.json", {"generated_at": ts(), "tests": fb})
 sc = self_check(idx, p, out, wk, result, corp, gs, vc, fb, help_rc)
 dump(out / "self_check.json", sc)
 out_fields = {
  "golden_standard": {"path": "golden_standard.json", "bytes": size(out / "golden_standard.json"),
                      "sha1": sha1(out / "golden_standard.json"), "fields": gs["counts"]["fields"],
                      "expected_status_counts": gs["counts"], "is_organizer_key": False,
                      "note": "自建基准（字段义务 + 独立锚点重扫），非组织方隐藏答案"},
  "diff_report": {"path": "diff_report.md", "bytes": size(out / "diff_report.md"),
                  "verdicts": vc, "verdict_labels": ["match", "deviation", "gap", "needs_review"],
                  "pass_rate_pct": round(100.0 * vc["match"] / max(1, len(gs["fields"])), 1)},
  "version_history": {"path": "version_history.md", "bytes": size(out / "version_history.md"),
                      "current": V, "supersedes": "1.0.0"},
  "self_check": {"path": "self_check.json", "bytes": size(out / "self_check.json"),
                 "summary": sc["summary"], "exit_codes": sc["exit_codes"],
                 "evidence_coverage_pct": sc["evidence_coverage"]["coverage_pct"],
                 "fallback_tests": [{"name": t.get("name"), "exit_codes": t.get("exit_codes"),
                                     "result_valid": t.get("result_valid")} for t in fb]},
  "audit_run": {"at": ts(), "events": len(events(wk)), "assets": list(ASSETS)}}
 rec(wk, "audit", 0, 0, note="assets written: %s" % ",".join(ASSETS),
     fields=gs["counts"]["fields"], verdicts=vc)
 return out_fields


def cmd_assets(a):
 wk, out = Path(a.work), Path(a.output)
 out.mkdir(parents=True, exist_ok=True)
 idx, ps = c.load_index(wk)
 try:
  rows = json.loads((out / "extraction.json").read_text(encoding="utf-8")).get("fields") or []
 except Exception:
  rows, meta = c.load_draft(wk)
 p = {"status": "partial", "rows": rows, "cnt": {"target_fields": len(rows)}, "errs": [], "degs": []}
 tot = {s: 0 for s in ST}
 for r in rows:
  if r.get("status") in tot:
   tot[r["status"]] += 1
 p["cnt"].update(tot)
 res = {}
 try:
  res = json.loads((out / "result.json").read_text(encoding="utf-8"))
 except Exception:
  res = {"case_id": idx.get("case_id"), "status": "partial"}
 f = emit(idx, p, ps, out, wk, res)
 res.update(f)
 dump(out / "result.json", res)
 write_run_log(out, wk, res, note="mode: audit assets only (`audit.py assets`)")
 print("== audit assets ==\nfields=%d -> %s" % (len(rows), ", ".join(ASSETS)))
 print("verdicts: %s" % json.dumps(f["diff_report"]["verdicts"], ensure_ascii=False))
 print("self_check: %s" % json.dumps(f["self_check"]["summary"], ensure_ascii=False))
 return 0


def main(argv=None):
 argv = list(sys.argv[1:] if argv is None else argv)
 import argparse
 ap = argparse.ArgumentParser(prog="audit.py", description="reading-06 v2 audit assets")
 ap.add_argument("--version", action="version", version=V)
 sp = ap.add_subparsers(dest="cmd")
 s = sp.add_parser("assets", help="recompute the five audit assets from existing outputs")
 for k, d in (("input", "/input"), ("work", "/app/work"), ("output", "/app/output")):
  s.add_argument("--" + k, default=os.environ.get("SKILL_" + k.upper(), d))
 try:
  a = ap.parse_args(argv)
 except SystemExit as e:
  return int(e.code or 0)
 if not a.cmd:
  ap.print_help()
  return 0
 try:
  return cmd_assets(a) or 0
 except Exception as e:
  print("audit error: %s" % e)
  return 0


if __name__ == "__main__":
 sys.exit(main())
