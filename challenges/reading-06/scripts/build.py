#!/usr/bin/env python3
"""reading-06 check/build: validate the agent draft, write extraction.* and result.json."""
import argparse, csv, json, os, re, sys
from pathlib import Path
import main as c

ST, PREF = c.ST, c.PREF
A = {"field_id": ("field_id", "id", "key", "field"), "label": ("label", "name", "title"),
     "value": ("value", "answer"), "unit": ("unit", "units"), "statistic": ("statistic", "stat", "error"),
     "condition": ("condition", "conditions", "context"), "comparator": ("comparator", "comparison"),
     "status": ("status", "state"), "quote": ("quote", "evidence", "text"),
     "locator": ("locator", "location", "loc"), "reasoning": ("reasoning", "rationale", "basis", "note"),
     "source_kind": ("source_kind", "source_type"), "conflict": ("conflict", None)}
TOK = (("case", "case_id"), ("stat", "status"), ("claim", "claims"), ("evidence", "claims"),
       ("source", "sources"), ("uncertain", "unc"), ("pending", "pend"), ("error", "errs"),
       ("degrad", "degs"), ("change", "changes"), ("runtime", "runtime"), ("count", "cnt"),
       ("coverage", "cnt"), ("result", "res"), ("field", "rows"), ("verification", "verif"),
       ("note", "notes"), ("summary", "notes"))
ROW = {"field_id": "", "label": "", "status": "", "value": None, "unit": "", "statistic": "",
       "condition": "", "comparator": "", "source_kind": "", "quote": "", "locator": "",
       "verification": "", "reasoning": "", "conflict": None}




def nrow(r):
 o = {k: c.pk(r, ks) for k, ks in A.items()}
 o["value"] = c.pk(r, A["value"], None)
 o["conflict"] = c.pk(r, A["conflict"], None)
 for k in ("field_id", "label", "quote", "reasoning", "source_kind", "statistic", "unit", "condition",
           "comparator"): o[k] = "" if o[k] is None else str(o[k])
 o["status"] = o["status"].strip().lower()
 return o


def loc_str(l):
 if l is None: return ""
 if isinstance(l, str): return l
 if not isinstance(l, dict): return str(l)
 o = ("material_id", "paragraph_id", "page", "table", "row", "col", "cell", "figure", "section",
      "pointer", "text")
 return "; ".join(["%s=%s" % (k, l[k]) for k in o if l.get(k) not in (None, "")] +
                  ["%s=%s" % (k, v) for k, v in l.items() if k not in o and v not in (None, "")])




def match(f, rows, used):
 fid = str(f["field_id"])
 for i, r in enumerate(rows):
  if i not in used and str(r.get("field_id", "")).strip() == fid: return i
 nf = c.norm(fid, "loose")
 for i, r in enumerate(rows):
  if i not in used and c.norm(str(r.get("field_id", "")), "loose") == nf: return i
 nl = c.norm(f["label"], "loose")
 for i, r in enumerate(rows):
  if i in used: continue
  rl = c.norm(str(r.get("label", "")), "loose")
  if rl and nl and (rl == nl or (len(nl) > 6 and (nl in rl or rl in nl))): return i
 return None


def check_one(f, row, ps, corp):
 fid, iss = f["field_id"], []
 res = {"field_id": fid, "label": f["label"], "row": row,
        "status": (row or {}).get("status") or "missing", "quote_level": None}
 def bad(code, msg, sev="error"): iss.append({"sev": sev, "field_id": fid, "code": code, "msg": msg})
 if row is None:
  bad("missing_field", "no draft entry for this field_id")
  return iss, res
 st, q = row["status"], row["quote"].strip()
 if st not in ST: bad("bad_status", "status must be one of %s, got %r" % ("/".join(ST), st))
 lv = c.vq(q, corp) if q else None
 res["quote_level"] = lv
 if q and not lv: bad("quote_not_found", "quote not found verbatim in materials")
 elif lv == "loose": bad("quote_loose", "quote matched only after normalization", "warning")
 loc = loc_str(row["locator"])
 if not loc: bad("no_locator", "locator empty", "warning")
 else:
  m = re.search(r"[A-Za-z0-9]+-p\d{3,5}", loc)
  if m and not any(x["pid"] == m.group(0) for mm in ps for x in ps[mm]):
   bad("bad_locator", "paragraph %s not in corpus" % m.group(0))
 if st == "reported":
  if row["value"] in (None, "", []): bad("empty_value", "reported needs a value")
  if len(q) < 8: bad("quote_missing", "reported needs a verbatim quote")
  val = row["value"] if isinstance(row["value"], str) else json.dumps(row["value"], ensure_ascii=False)
  for num in set(re.findall(r"\d+(?:[.,]\d+)?", val)):
   if len(num) > 1 and c.norm(num, "normalized") not in c.norm(q, "normalized"):
    bad("number_not_in_quote", "number %s not literally in quote" % num, "warning"); break
  if not row["reasoning"]:
   bad("no_reasoning", "state how the value was read (cell/sentence/figure)", "warning")
 else:
  if len(row["reasoning"].strip()) < 8:
   bad("no_justification", "%s needs stated basis (terms searched, sections checked)" % st)
  if st == "source_conflict":
   cf = row["conflict"]
   qs = [str(cf.get(k, "")) for k in ("quote_a", "quote_b", "value_a", "value_b")] \
       if isinstance(cf, dict) else ([cf] if isinstance(cf, str) else [])
   if len([x for x in qs if c.vq(x, corp)]) < 2:
    bad("conflict_sides", "record both sides (quote_a/quote_b)", "warning")
 return iss, res


def validate(rows, fields, ps, corp):
 iss, res, used = [], [], set()
 for f in fields:
  i = match(f, rows, used)
  if i is not None: used.add(i)
  a, b = check_one(f, nrow(rows[i]) if i is not None else None, ps, corp)
  iss += a; res.append(b)
 for i, r in enumerate(rows):
  if i not in used and str(r.get("field_id", "")).strip():
   iss.append({"sev": "warning", "field_id": str(r["field_id"]), "code": "extra_field", "msg": "not a target field"})
 return iss, res


def fallback(f, ps):
 words = []
 for k in [f["label"]] + list(f["aliases"]):
  words += [w for w in re.split(r"[；;，,、/|()（）:：\s]+", str(k)) if len(w) >= 2]
 words = list(dict.fromkeys(words))[:24]
 best, sc = None, 0
 for mid in sorted(ps):
  for p in ps[mid]:
   n = sum(p.get("text", "").casefold().count(w.casefold()) for w in words)
   if n > sc and len(p.get("text", "")) < 4000: best, sc = p, n
 row = {"field_id": f["field_id"], "label": f["label"], "value": None, "status": "extraction_failed",
        "quote": "", "locator": "", "reasoning": "", "conflict": None}
 if not best:
  row["reasoning"] = "fallback: no readable text"
  return row
 ss = c.sents(best["text"])
 pick = max(ss, key=lambda x: sum(x.casefold().count(w.casefold()) for w in words)) if ss else ""
 row.update({"quote": pick.strip()[:400], "locator": {"material_id": best["material_id"],
             "paragraph_id": best["pid"], "page": best.get("page")},
             "reasoning": ("fallback candidate only (%d keyword hits, terms=%r); unverified, not a result"
                           % (sc, words[:5]))})
 return row


def status_val(contract, internal):
 hint = next((v for k, v in (contract if isinstance(contract, dict) else {}).items()
              if "status" in str(k).lower() and isinstance(v, str)), "")
 for t in re.findall(r"[a-z_]+", hint.lower()):
  if t in PREF.get(internal, ()): return t
 return PREF.get(internal, ("partial",))[0]


def fill(contract, p):
 if not isinstance(contract, dict) or not contract: return dict(p["res"], **core(p))
 out = {}
 for k, hint in contract.items():
  low, h = str(k).lower(), hint if isinstance(hint, str) else ""
  g = None
  for tk, key in TOK:
   if tk in low: g = p[key]; break
  if g is None:
   for tk, key in TOK:
    if tk in h.lower(): g = p[key]; break
  out[k] = g if g is not None else ([] if re.search(r"list|\[\]|array|s\b", h + low) else None)
 for k, v in core(p).items(): out.setdefault(k, v)
 return out


def core(p):
 return {"case_id": p["case_id"], "status": p["status"], "sources": p["sources"],
         "uncertainty": p["unc"], "pending_human": p["pend"], "errors": p["errs"],
         "degradations": p["degs"], "changes": p["changes"], "runtime": p["runtime"]}


def claim_list(meta, rows_out, corp):
 dc, claims = meta.get("claims"), []
 for i, x in enumerate(dc if isinstance(dc, list) else []):
  if not isinstance(x, dict): continue
  q = x.get("quote") or ""
  claims.append({"id": x.get("id") or "C%d" % (i + 1), "kind": x.get("kind") or "unspecified",
                 "text": x.get("text") or x.get("claim") or "", "field_ids": x.get("field_ids") or [],
                 "quote": q, "locator": loc_str(x.get("locator") or x.get("location")),
                 "source_kind": x.get("source_kind") or "",
                 "quote_verification": "quote_" + c.vq(q, corp) if q and c.vq(q, corp) else
                                       ("no_quote" if not q else "quote_unverified")})
 if not claims:
  claims = [{"id": "C-" + r["field_id"], "kind": "extracted_value", "field_ids": [r["field_id"]],
             "text": "%s: %s %s" % (r["label"] or r["field_id"], r["value"], r["unit"]),
             "quote": r["quote"], "locator": r["locator"], "source_kind": r["source_kind"],
             "quote_verification": r["verification"], "generated_by": "build"}
            for r in rows_out if r["status"] == "reported" and r["quote"]]
 return claims


def write_artifacts(out, idx, status, cnt, rows_out, claims, unc):
 c.dump(out / "extraction.json", {"case_id": idx.get("case_id"), "status": status, "counts": cnt,
                                  "fields": rows_out, "claims": claims, "uncertainties": unc,
                                  "field_dictionary": "references/field_dictionary.md"})
 cols = ["field_id", "label", "status", "value", "unit", "statistic", "condition", "comparator",
         "source_kind", "quote", "locator", "conflict", "verification", "reasoning"]
 with open(out / "extraction.csv", "w", encoding="utf-8", newline="") as fh:
  w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
  w.writeheader()
  for r in rows_out: w.writerow({x: r.get(x, "") for x in cols})
 f = lambda v: ("" if v is None else str(v)).replace("|", "/").replace("\n", " ")[:220]
 md = ["# Field extraction table", "", "- case_id: `%s`" % idx.get("case_id"),
       "- status: `%s`" % status, "- counts: %s" % json.dumps(cnt, ensure_ascii=False), "",
       "| field_id | label | status | value | unit | condition | quote | locator |",
       "|---|---|---|---|---|---|---|---|"]
 md += ["| %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(
        f(x) for x in (r["field_id"], r["label"], r["status"], r["value"], r["unit"],
                       r["condition"], r["quote"], r["locator"])) for r in rows_out]
 (out / "extraction.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def build_payload(idx, ps, rows, meta, deg):
 fields, corp = idx.get("fields") or [], c.corpus(ps)
 changes = [{"at": c.ts(), "action": "draft_loaded", "detail": meta.get("path") or "no draft; fallback"},
            {"at": c.ts(), "action": "index_loaded",
             "detail": "%d materials, %d fields" % (len(idx.get("materials") or []), len(fields))}]
 if not fields:
  fields = [{"field_id": str(r.get("field_id")), "label": str(r.get("label", "")), "description": "",
             "aliases": []} for r in rows]
 iss, res = validate(rows, fields, ps, corp) if fields else ([], [])
 fb = []
 for i, f in enumerate(fields):
  r = res[i] if i < len(res) else {"row": None}
  if r.get("row") is not None: continue
  row = fallback(f, ps); fb.append(f["field_id"])
  iss = [x for x in iss if not (x["code"] == "missing_field" and x.get("field_id") == f["field_id"])]
  iss.append({"sev": "error", "field_id": f["field_id"], "code": "fallback_used",
              "msg": "no draft entry; unverified"})
  res[i] = {"field_id": f["field_id"], "label": f["label"], "row": row, "status": row["status"],
            "quote_level": c.vq(row["quote"], corp) if row["quote"] else None}
 rows_out = []
 for f, r in zip(fields, res):
  row, lv = r.get("row") or {}, r.get("quote_level")
  o = dict(ROW)
  o.update(field_id=str(f["field_id"]), label=f.get("label", ""), value=row.get("value"),
           status=r.get("status", "extraction_failed"), quote=str(row.get("quote") or ""),
           locator=loc_str(row.get("locator")),
           verification="quote_" + lv if lv else ("no_quote" if not row.get("quote") else "quote_unverified"),
           reasoning=str(row.get("reasoning") or ""), conflict=row.get("conflict"))
  for k in ("unit", "statistic", "condition", "comparator", "source_kind"):
   o[k] = str(row.get(k) or "")
  rows_out.append(o)
 cnt = {"target_fields": len(fields), "reported": 0, "not_reported": 0, "source_conflict": 0,
        "extraction_failed": 0}
 for r in rows_out:
  if r["status"] in cnt: cnt[r["status"]] += 1
 cnt["quote_verified"] = sum(1 for r in rows_out if r["verification"] in ("quote_strict", "quote_normalized"))
 cnt["quote_loose"] = sum(1 for r in rows_out if r["verification"] == "quote_loose")
 cnt["quote_failed"] = sum(1 for r in rows_out if "unverified" in r["verification"])
 cnt["fallback_fields"] = len(fb)
 cnt["coverage_pct"] = round(100.0 * (len(fields) - len(fb)) / len(fields), 1) if fields else 0.0
 errs = [x for x in iss if x["sev"] == "error"]
 warns = [x for x in iss if x["sev"] != "error"]
 if not idx.get("materials"):
  status = "input_error"; errs.append({"code": "no_material", "msg": "no material files in input"})
 elif not ps or not fields: status = "insufficient_evidence"
 elif fb or cnt["quote_failed"] or cnt["extraction_failed"] or any(
      x["code"] in ("missing_field", "empty_value", "quote_missing", "bad_status") for x in errs):
  status = status_val(idx.get("output_contract"), "partial")
 else: status = status_val(idx.get("output_contract"), "ok")
 claims = claim_list(meta, rows_out, corp)
 unc = [{"field_id": r["field_id"], "status": r["status"], "basis": r["reasoning"][:300] or "not stated"}
        for r in rows_out if r["status"] != "reported"]
 unc += [{"field_id": r["field_id"], "issue": "quote_unverified",
          "detail": "quote not matched verbatim; re-check source"} for r in rows_out
         if r["status"] == "reported" and r["verification"] not in ("quote_strict", "quote_normalized")]
 unc += [{"field_id": x.get("field_id"), "issue": x["code"], "detail": x["msg"]} for x in warns
         if x["code"] in ("quote_loose", "number_not_in_quote", "conflict_sides", "no_locator",
                          "no_reasoning")]
 extra = meta.get("extra") or {}
 if isinstance(extra.get("uncertainties"), list): unc += [u for u in extra["uncertainties"] if u]
 pend = [{"field_id": r["field_id"], "action": "verify value against source paragraph",
          "locator": r["locator"]} for r in rows_out if r["status"] == "extraction_failed"]
 if isinstance(extra.get("pending_human"), list): pend += [x for x in extra["pending_human"] if x]
 src = [{"material_id": m.get("material_id"), "name": m.get("name"), "kind": m.get("kind"),
         "path": m.get("path"), "sha1": m.get("sha1"), "paragraphs": m.get("paragraphs"),
         "extractor": m.get("extractor")} for m in idx.get("materials") or []]
 if idx.get("source"):
  src.append({"material_id": "CASE", "name": idx["source"].get("title") or "case source",
              "kind": "metadata", "doi": idx["source"].get("doi"), "path": idx.get("case_path")})
 notes = ("Per-field extraction; reported requires a verbatim quote, other statuses state their basis. "
          "verification=quote_strict|quote_normalized|quote_loose|quote_unverified")
 return {"case_id": idx.get("case_id"), "status": status, "rows": rows_out, "cnt": cnt, "claims": claims,
         "unc": unc, "pend": pend, "errs": errs,
         "degs": list(idx.get("degradations") or []) +
                 [x for x in deg if x not in (idx.get("degradations") or [])],
         "changes": changes + [{"at": c.ts(), "action": "finalize",
                                "detail": "status=%s fallback=%d" % (status, len(fb))}],
         "runtime": {"skill_version": c.V, "started_at": changes[0]["at"], "finished_at": c.ts(),
                     "argv": sys.argv[1:], "python": sys.version.split()[0], "phase": "build"},
         "sources": src, "notes": notes,
         "verif": {"issues": iss, "errors": len(errs), "warnings": len(warns),
                   "quote_verified": cnt["quote_verified"], "quote_failed": cnt["quote_failed"],
                   "fallback_fields": fb},
         "res": {"field_results": rows_out, "counts": cnt,
                 "field_dictionary": "references/field_dictionary.md",
                 "files": {"extraction_json": "extraction.json", "extraction_csv": "extraction.csv",
                           "extraction_md": "extraction.md", "result_json": "result.json"},
                 "notes": notes}}


def cmd_build(a):
 wk, out = Path(a.work), Path(a.output)
 wk.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
 err, deg = [], []
 try: idx, ps = c.load_index(wk)
 except Exception as e:
  err.append("index unavailable (%s); rebuilt" % e); deg.append("index_rebuild")
  try:
   idx, _, _ = c.build_index(a.input, wk, deg, err); idx, ps = c.load_index(wk)
  except Exception as e2:
   idx = {"case_id": None, "output_contract": {}, "fields": [], "materials": [], "source": {},
          "errors": [str(e2)], "degradations": []}; ps = {}
 rows, meta = c.load_draft(wk)
 p = build_payload(idx, ps, rows, meta, deg)
 result = fill(idx.get("output_contract") or {}, p)
 result.setdefault("case_id", idx.get("case_id")); result.setdefault("status", p["status"])
 c.dump(out / "result.json", result)          # always a valid, contract-complete file on disk
 write_artifacts(out, idx, p["status"], p["cnt"], p["rows"], p["claims"], p["unc"])
 # v2 audit assets: golden standard, diff report, version history, self check, run log.
 # A failure here only degrades; the extraction result above is already complete.
 au, audited = None, False
 if getattr(a, "no_audit", False):
  p["degs"].append("audit_disabled_by_flag")
 else:
  try:
   import audit as au
   for k in ("golden_standard", "diff_report", "version_history", "self_check"):
    result.setdefault(k, {})
   result.update(au.emit(idx, p, ps, out, wk, result))
   audited = True
  except Exception as e:
   p["errs"].append({"code": "audit_failed", "msg": str(e)[:200]})
   p["degs"].append("audit_assets_skipped")
   for k in ("golden_standard", "diff_report", "version_history", "self_check"):
    result[k] = {"path": None, "status": "not_generated", "reason": str(e)[:200]}
  result["errors"] = p["errs"]; result["degradations"] = p["degs"]
  if audited:
   p["res"].setdefault("files", {}).update({"golden_standard": "golden_standard.json",
     "diff_report": "diff_report.md", "version_history": "version_history.md",
     "self_check": "self_check.json", "run_log": "run.log"})
 c.dump(out / "result.json", result)
 if audited:
  try: au.write_run_log(out, wk, result)
  except Exception as e: print("run.log skipped: %s" % e)
 cnt = p["cnt"]
 print("== build ==\ncase_id: %s | status: %s" % (idx.get("case_id"), p["status"]))
 print("fields=%d reported=%d not_reported=%d conflict=%d failed=%d fallback=%d quote_failed=%d" % (
     cnt["target_fields"], cnt["reported"], cnt["not_reported"], cnt["source_conflict"],
     cnt["extraction_failed"], cnt["fallback_fields"], cnt["quote_failed"]))
 print("contract keys: %s" % ", ".join((idx.get("output_contract") or {})))
 print("artifacts: result.json extraction.json extraction.csv extraction.md"
       + (" golden_standard.json diff_report.md version_history.md self_check.json run.log" if audited
          else " (audit assets skipped)"))
 for e in p["errs"][:6]: print("  ! %s: %s" % (e.get("field_id", "-"), e.get("msg")))
 return 0


def cmd_check(a):
 wk = Path(a.work)
 try: idx, ps = c.load_index(wk)
 except Exception as e:
  print("check: index missing (%s); run init first" % e); return 0
 fields = idx.get("fields") or []
 rows, meta = c.load_draft(wk)
 iss, res = validate(rows, fields, ps, c.corpus(ps)) if fields else ([], [])
 errs = [x for x in iss if x["sev"] == "error"]
 warns = [x for x in iss if x["sev"] != "error"]
 c.dump(wk / "check_report.json", {"checked_at": c.ts(), "draft": meta.get("path"), "fields": len(fields),
                                   "rows": len(rows), "errors": errs, "warnings": warns,
                                   "per_field": [{"field_id": r["field_id"], "status": r["status"],
                                                  "quote_level": r.get("quote_level")} for r in res]})
 print("== check == draft=%s fields=%d rows=%d" % (meta.get("path"), len(fields), len(rows)))
 for x in errs: print("ERROR %-10s %-17s %s" % (x.get("field_id"), x["code"], x["msg"]))
 for x in warns: print("WARN  %-10s %-17s %s" % (x.get("field_id"), x["code"], x["msg"]))
 print("=> %s (%d errors, %d warnings) %s" % ("PASS" if not errs else "FIX", len(errs), len(warns),
                                             wk / "check_report.json"))
 return 0


def emergency(argv):
 out = Path(os.environ.get("SKILL_OUTPUT", "/app/output"))
 for i, x in enumerate(argv):
  if x == "--output" and i + 1 < len(argv): out = Path(argv[i + 1])
 try:
  c.dump(out / "result.json", {"case_id": None, "status": "partial", "sources": [], "errors": ["fatal"],
                               "uncertainty": ["fatal error before build"], "pending_human": [],
                               "degradations": [], "changes": [], "runtime": {"phase": "emergency"}})
 except Exception: pass
 return 0


def main(argv=None):
 argv = list(sys.argv[1:] if argv is None else argv)
 try: a = c.parser("build.py", ("check", "build")).parse_args(argv)
 except SystemExit as e: return int(e.code or 0)
 if not a.cmd:
  c.parser("build.py", ("check", "build")).print_help(); return 0
 try: return {"check": cmd_check, "build": cmd_build}[a.cmd](a) or 0
 except Exception as e:
  print("error in %s: %s" % (a.cmd, e))
  if a.cmd == "build": return emergency(argv)
  try:
   return cmd_build(argparse.Namespace(input=getattr(a, "input", "/input"),
                                       work=getattr(a, "work", "/app/work"),
                                       output=getattr(a, "output", "/app/output"))) or 0
  except Exception: return emergency(argv)


if __name__ == "__main__":
 sys.exit(main())
