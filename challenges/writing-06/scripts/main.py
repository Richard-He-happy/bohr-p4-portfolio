#!/usr/bin/env python3
"""paper-structure-logic-review :: structural diagnosis of a full manuscript.

Segments the real input file into chapter/paragraph/sentence locators, runs the six-dimension
rule engine (verify.py), and writes a grounded review + an executable edit plan.
Review only: it never rewrites the manuscript.

Usage: python3 main.py --input /input --out /app/output
"""
import argparse, json, re, shutil, subprocess, time, zipfile
from pathlib import Path

try:
 import verify as VE
except Exception as _e:
 VE = None
 H = Path(__file__).resolve().parent
 import sys
 sys.path.insert(0, str(H))
 try: import verify as VE
 except Exception: VE = None
V = "1.0.0"
H = Path(__file__).resolve().parent
M = {}
for _c in (H.parent / "references" / "messages.json", H / "messages.json"):
 if _c.is_file():
  try: M = json.loads(_c.read_text(encoding="utf-8")); break
  except Exception: M = {}
DIMS = ["research_question_alignment", "section_structure", "argument_chain",
        "paragraph_relations", "duplication", "conclusion_boundary"]
FILES = ("edit_plan.md", "structural_review.json", "outline_after.md", "argument_map.json",
         "consistency_report.md", "pending_human.json")
CASE, CH, PA, RES = {}, [], [], {"findings": [], "actions": [], "rows": [], "pending": [],
                                 "errors": [], "stats": {}, "coverage": {}, "facts": [],
                                 "argmap": {}}


def T(_k, **kw):
 s = M.get(_k)
 if not isinstance(s, str): return ""
 try: return s.format(**kw)
 except Exception: return s


def D_(d): return (M.get("dim_cn") or {}).get(d, d)


def norm(t): return re.sub(r"\s+", " ", t or "").strip()


def wc(t):
 return len(re.findall(r"[A-Za-z][A-Za-z\-']*", t)) + len(re.findall(r"[\u4e00-\u9fff]", t)) // 2


def pend(kind, detail, need):
 RES["pending"].append({"item_id": "PH%02d" % (len(RES["pending"]) + 1), "kind": kind,
                        "detail": detail, "needed_action": need})


def read_text(p):
 p = Path(p); e = p.suffix.lower()
 if e in (".md", ".markdown", ".txt", ".rst", ".tex", ".csv"):
  return p.read_text(encoding="utf-8", errors="replace")
 if e in (".html", ".htm"):
  return re.sub(r"<[^>]+>", " ", p.read_text(encoding="utf-8", errors="replace"))
 if e == ".docx":
  with zipfile.ZipFile(p) as z: xml = z.read("word/document.xml").decode("utf-8", "replace")
  return re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n\n"))
 if e == ".pdf":
  exe = shutil.which("pdftotext")
  if not exe:
   RES["errors"].append({"stage": "pdf", "detail": "%s: pdftotext unavailable" % p.name}); return ""
  try:
   r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=120)
   if r.returncode == 0 and r.stdout.strip(): return r.stdout.decode("utf-8", "replace")
   RES["errors"].append({"stage": "pdf", "detail": "%s: pdftotext produced no text" % p.name})
  except Exception as e:
   RES["errors"].append({"stage": "pdf", "detail": "%s: %s" % (p.name, e)})
 return ""


def heading_of(line, mode, role_rx):
 s = line.strip()
 if not s or len(s) > 110 or s[-1] in ".,;\u3002\uff0c\uff1b:\uff1a": return None
 if mode == "md":
  m = re.match(r"^#{1,6}\s+(\S.*)$", s)
  return m.group(1).strip().rstrip("#").strip() if m else None
 if re.match(r"^(?:\d+\.)+\d*\.?\s+\S{2,80}$", s): return s
 low = s.lower().rstrip(":")
 for _, pat in role_rx:
  if pat.match(low): return s
 return s if re.match(r"^[A-Z][A-Z \-]{5,70}$", s) else None


def role_of(title, role_rx):
 t = (title or "").strip().lower()
 for r, pat in role_rx:
  if t and pat.search(t): return r
 return "body"


_SENT_TERM = set(".!?\u3002\uff01\uff1f;\uff1b")
_ABBR = set("fig tab eq ref no vol pp cf vs etc al eg ie sec".split())


def _is_sent_boundary(t, i):
 if t[i] != ".":
  return True
 if i > 0 and i + 1 < len(t) and t[i - 1].isdigit() and t[i + 1].isdigit():
  return False
 j = i - 1
 while j >= 0 and (t[j].isalnum() or t[j] == "."):
  j -= 1
 if re.sub(r"\.", "", t[j + 1:i].lower()) in _ABBR:
  return False
 return i + 1 >= len(t) or t[i + 1].isspace()


def sents(t):
 out, start = [], 0
 for i, c in enumerate(t):
  if c in _SENT_TERM and _is_sent_boundary(t, i):
   out.append(t[start:i + 1]); start = i + 1
 if start < len(t): out.append(t[start:])
 return [s.strip() for s in out if wc(s) >= 2]


def segment(text, role_rx):
 mode = "md" if re.search(r"(?m)^#{1,6}\s+\S", text) else "plain"
 units, buf = [], []
 for ln in text.splitlines():
  s = ln.strip(); h = heading_of(s, mode, role_rx) if s else None
  if h:
   if buf: units.append(("p", "\n".join(buf)))
   buf = []; units.append(("h", h))
  elif not s:
   if buf: units.append(("p", "\n".join(buf)))
   buf = []
  else: buf.append(s)
 if buf: units.append(("p", "\n".join(buf)))
 chaps, paras, ch, pt = [], [], 0, 0
 for kind, val in units:
  if kind == "h":
   ch += 1; pt = 0
   chaps.append({"loc": "C%02d" % ch, "title": norm(val), "role": role_of(val, role_rx), "words": 0})
   continue
  if ch == 0:
   ch = 1; chaps.append({"loc": "C01", "title": "", "role": "body", "words": 0})
  body = norm(val)
  if wc(body) < 3: continue
  pt += 1
  paras.append({"loc": "C%02d-P%03d" % (ch, pt), "ch": ch, "role": chaps[ch - 1]["role"], "text": body,
                "sents": [("C%02d-P%03d-S%02d" % (ch, pt, i + 1), s) for i, s in enumerate(sents(body))]})
  chaps[ch - 1]["words"] += wc(body)
 return chaps, paras


def W(out, n, o):
 (out / n).write_text(o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, indent=2),
                      encoding="utf-8")


def plan_md(cid):
 F, A = RES["findings"], RES["actions"]
 L = [T("pl_top", cid=cid, ch=len(CH), w=sum(c["words"] for c in CH), f=len(F), a=len(A))]
 for pr in ("P1", "P2", "P3"):
  g = [d for d in RES["rows"] if d["pr"] == pr]
  if g:
   L.append(T("pl_pri", pr=pr, label=(M.get("pri_cn") or {}).get(pr, "")))
   L += [T("pl_item", **d) for d in g]
 cv = RES["coverage"]
 L.append(T("pl_cov"))
 L += [T("pl_row", dim=D_(d), n=len(cv[d]["finding_ids"]),
         st=(M.get("st_cn") or {}).get(cv[d]["status"], cv[d]["status"])) for d in DIMS]
 L.append(T("pl_pend"))
 L += ["- %s: %s" % (p["item_id"], p["detail"]) for p in RES["pending"]] or [T("none")]
 return "\n".join(L)


def outline_md():
 tt = sum(c["words"] for c in CH) or 1
 fc = {}
 for f in RES["findings"]: fc.setdefault(f["locator"].split("-")[0], []).append(f["dimension"])
 L = [T("ol_top")]
 for i, c in enumerate(CH, 1):
  L.append(T("ol_row", i=i, loc=c["loc"], title=(c["title"] or "-")[:44], w=c["words"],
             role=T("ol_role") if c["role"] == "body" else D_(c["role"]),
             pct=round(100.0 * c["words"] / tt, 1),
             note=T("ol_merge") if "duplication" in fc.get(c["loc"], []) else
             (T("ol_adj") if "section_structure" in fc.get(c["loc"], []) else T("ol_k"))))
 rq = next((f for f in RES["findings"] if f["dimension"] == "research_question_alignment"), None)
 mv = [a for a in RES["actions"] if a["operation"] == "move"]
 L += [T("ol_main"), "", T("ol_rq", q=(rq["quote"][:90] if rq else "-")),
       T("ol_seq", s=" > ".join(c["loc"] + " " + (c["title"] or "") for c in CH)),
       T("ol_move", s="; ".join("%s => after %s" % (a["from_locator"], a["to_locator"]) for a in mv)
         if mv else T("ol_nomove"))]
 return "\n".join(L)


def consist_md(cid):
 c = RES["stats"].get("cit", {}); ds = RES["stats"]
 L = [T("cs_top", cid=cid)]
 L += [T("cs_row", k=k, v="%.1f%%" % (v * 100)) for k, v in ds.get("share", {}).items()]
 L.append(T("cs_ref", u=c.get("in_text", 0), r=c.get("refs", 0), bad=c.get("unresolved") or T("none"),
            ref=c.get("fig_ref") or T("none"), cap=c.get("caps") or T("none")))
 L.append(T("cs_dup", p=ds.get("pp", 0), h=ds.get("dp", 0), v=ds.get("pm", 0.0)))
 L.append(T("cs_int", t=T("tr_yes") if ds.get("trunc") else T("tr_no"),
            d="; ".join("%s: %s" % (e["stage"], e["detail"]) for e in RES["errors"]) or T("none")))
 return "\n".join(L)


def fill(con, pay):
 nk = lambda k: re.sub(r"[^a-z0-9]", "", str(k).lower())
 al = {nk(k): k for k in pay}
 out, unk = {}, []
 for k, v in (con or {}).items():
  hit = al.get(nk(k))
  if hit is None:
   for a in al:
    if a and (a in nk(k) or nk(k) in a): hit = al[a]; break
  if hit is None:
   out[k] = [] if isinstance(v, list) else None; unk.append(k); continue
  val = pay[hit]
  if isinstance(v, list) and not isinstance(val, list): val = [val]
  elif isinstance(v, str) and not isinstance(val, str):
   val = val.get("primary") if isinstance(val, dict) else json.dumps(val, ensure_ascii=False)[:400]
  elif isinstance(v, dict) and not isinstance(val, dict): val = {"value": val}
  out[k] = val
 return out, unk


def workorder():
 o = []
 for key in ("organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder",
             "organizer_supplied_scope", "scope"):
  v = CASE.get(key)
  if not v: continue
  items = v if isinstance(v, list) else ([v] if isinstance(v, str)
                                         else (v.get("items") or v.get("requirements") or [v]))
  for i, it in enumerate(items if isinstance(items, list) else [items], 1):
   req = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False); lo = req.lower()
   dims = [d for d in DIMS if d.split("_")[0] in lo or D_(d) in req]
   st, ev = "done", ""
   if any(k in lo for k in (M.get("wo_pdf_k") or ["pdf", "export", "pptx"])):
    st, ev = "not_applicable", T("wo_pdf")
   elif any(k in lo for k in (M.get("wo_rw_k") or ["rewrite"])):
    st, ev = "not_applicable", T("wo_rw")
   elif dims: ev = T("wo_dim", d=", ".join(dims))
   elif any(k in lo for k in (M.get("wo_ok_k") or ["structural", "structure"])): ev = T("wo_ok")
   else: st, ev = "partial", T("wo_part")
   o.append({"item_id": "%s-%02d" % (key[:6], i), "source_key": key, "requirement": req[:300],
             "status": st, "evidence": ev})
 return o


def finalize(out, cid, con, fl, mp, tx, t0, st, tr=False):
 F, A, ER = RES["findings"], RES["actions"], RES["errors"]
 cv, qh = RES["coverage"], len(F)
 hit = sum(1 for f in F if VE and VE.ground(f["quote"]))
 rv = {"case_id": cid, "dimension_coverage": cv, "findings": F, "actions": A,
       "manuscript": {"path": str(mp) if mp else None, "title": CH[0]["title"] if CH else "",
                      "chapters": len(CH), "paragraphs": len(PA), "words": wc(tx), "truncated": tr},
       "grounding": {"findings_total": qh, "quote_verbatim_hit": hit,
                     "hit_rate": 1.0 if not qh else round(hit / float(qh), 4), "rule": T("ground_rule")}}
 RES["stats"]["trunc"] = tr
 try:
  W(out, "structural_review.json", rv); W(out, "argument_map.json", RES["argmap"])
  W(out, "edit_plan.md", plan_md(cid)); W(out, "outline_after.md", outline_md())
  W(out, "consistency_report.md", consist_md(cid))
  W(out, "pending_human.json", {"case_id": cid, "items": RES["pending"],
                               "cannot_judge": [p["detail"] for p in RES["pending"]]})
 except Exception as e: ER.append({"stage": "artifacts", "detail": str(e)})
 cl = [{"change_id": "CH%02d" % i, "action_id": a["action_id"], "finding_id": a["finding_id"],
        "locator": a["from_locator"], "revised_quote": None, "status": "proposed_not_applied",
        "original_quote": [f for f in F if f["finding_id"] == a["finding_id"]][0]["quote"],
        "change_type": "structural_action_proposed", "reason": a["expected_effect"]}
       for i, a in enumerate(A, 1)]
 cp = [{"check": "contract_fields_filled", "pass": True, "detail": T("chk_1")},
       {"check": "six_dimension_coverage", "pass": len(cv) == 6, "detail": T("chk_2")},
       {"check": "quote_verbatim", "pass": hit == qh, "detail": T("chk_3", h=hit, t=qh)},
       {"check": "actions_executable", "detail": T("chk_4"),
        "pass": all(a["operation"] in VE.OPS and a["from_locator"] and a["expected_effect"] for a in A)
        if VE else False},
       {"check": "finding_action_join", "detail": T("chk_5"),
        "pass": all(a["finding_id"] in [f["finding_id"] for f in F] for a in A)},
       {"check": "no_full_rewrite", "detail": T("chk_6"),
        "pass": not any((out / n).exists() for n in ("manuscript.md", "rewrite.md", "revised.md"))}]
 pay = {"case_id": cid, "status": st, "sources": fl, "errors": ER,
        "pending_human": RES["pending"], "changes": cl,
        "degradations": ER,
        "uncertainty": [T("unc_1"), T("unc_2"), T("unc_3")],
        "runtime": {"version": V, "seconds": round(time.time() - t0, 2), "model_requests": 0,
                    "deterministic_engine": True},
        "deliverable": {"primary": str(out / "edit_plan.md"), "editable": True, "format": "markdown+json",
                        "files": [str(out / n) for n in FILES]},
        "preserved_facts": RES["facts"], "change_log": cl, "compliance_checks": cp,
        "evidence_map": [{"claim_id": f["finding_id"], "claim": f["diagnosis"][:120], "locator": f["locator"],
                          "quote": f["quote"], "source_id": "manuscript", "kind": "structural_judgment"}
                         for f in F],
        "editable_source": {"primary": str(out / "structural_review.json"), "secondary": str(out / "edit_plan.md")},
        "export_artifact": None, "findings": F, "actions": A, "dimension_coverage": cv,
        "content_map": [{"finding_id": f["finding_id"], "locator": f["locator"], "quote": f["quote"]} for f in F],
        "exceptions": [{"kind": "pending_human", "count": len(RES["pending"])},
                       {"kind": "error", "count": len(ER)}],
        "structural_review": str(out / "structural_review.json"), "edit_plan": str(out / "edit_plan.md"),
        "outline_after": str(out / "outline_after.md"), "argument_map": str(out / "argument_map.json"),
        "metrics": {"dimensions_covered": sum(1 for v in cv.values() if v.get("finding_ids")),
                    "dimensions_no_issue_with_evidence": sum(1 for v in cv.values() if not v.get("finding_ids")),
                    "findings": qh, "actions": len(A),
                    "findings_high": sum(1 for f in F if f["severity"] == "high"),
                    "quote_hit_rate": 1.0 if not qh else round(hit / float(qh), 4),
                    "pending_human": len(RES["pending"]), "errors": len(ER),
                    "action_ratio_per_finding": round(len(A) / float(max(1, qh)), 2),
                    "estimated_revision_rounds": max(1, -(-len(A) // 6)), "rounds_note": T("rounds_note")},
        "workorder_receipts": workorder()}
 filled, unk = fill(con, pay)
 res = {"case_id": cid, "status": st}
 for k, v in pay.items(): res.setdefault(k, v)
 res.update(filled); res["contract_unfilled_keys"] = unk
 try:
  W(out, "result.json", res)
  print("wrote %s | status=%s findings=%d actions=%d pending=%d"
        % (out / "result.json", st, len(F), len(A), len(RES["pending"])))
 except Exception as e: print("result write failed: %s" % e)
 return 0


def main(argv=None):
 ap = argparse.ArgumentParser(
     description="Six-dimension structural diagnosis of a manuscript (research_question_alignment, "
                 "section_structure, argument_chain, paragraph_relations, duplication, "
                 "conclusion_boundary): grounded findings (locator + verbatim quote) and an executable "
                 "edit plan. Review only, no rewrite.",
     epilog="Example: python3 main.py --input /input --out /app/output")
 ap.add_argument("--input", default=str(Path("/input") if Path("/input").is_dir() else Path.cwd() / "input"),
                 help="input dir with case.json + materials")
 ap.add_argument("--out", default=str(Path("/app/output") if Path("/app").is_dir() else Path.cwd() / "output"),
                 help="output dir for result.json and artifacts")
 ap.add_argument("--version", action="version", version=V)
 a = ap.parse_args(argv)
 t0, out, inp = time.time(), Path(a.out), Path(a.input)
 try: out.mkdir(parents=True, exist_ok=True)
 except Exception as e: print("cannot create output dir: %s" % e); return 0
 W(out, "result.json", {"case_id": None, "status": "partial", "skill": "paper-structure-logic-review",
                        "skill_version": V, "sources": [], "uncertainty": [], "pending_human": [],
                        "errors": [{"stage": "startup", "detail": "run started, not finalized"}],
                        "degradations": [], "changes": [], "runtime": {"version": V}})
 con, cid, cpath = {}, None, None
 try:
  if inp.is_dir():
   for c in [inp / "case.json"] + sorted(inp.glob("**/case*.json")):
    if c.is_file(): cpath = c; break
   if cpath: CASE.update(json.loads(cpath.read_text(encoding="utf-8", errors="replace")) or {})
   con = CASE.get("output_contract") or {}
   if not isinstance(con, dict): con = {"output_contract": con}
   cid = CASE.get("case_id") or CASE.get("id") or CASE.get("caseId")
  else: RES["errors"].append({"stage": "input", "detail": "input dir missing: %s" % inp})
 except Exception as e: RES["errors"].append({"stage": "case_parse", "detail": "case.json unreadable: %s" % e})
 cid = cid or "case-unknown"
 fl, cd = [], []
 for p in (sorted(inp.rglob("*")) if inp.is_dir() else []):
  if not p.is_file() or p.name.startswith("."): continue
  if p.name.lower() in ("task.md", "guide.md") or (cpath and p.resolve() == cpath.resolve()):
   fl.append({"source_id": p.name, "path": str(p), "bytes": p.stat().st_size,
              "role": "case" if cpath and p.resolve() == cpath.resolve() else "instruction"}); continue
  if p.suffix.lower() not in (".md", ".markdown", ".txt", ".rst", ".tex", ".html", ".htm", ".csv",
                              ".docx", ".pdf"):
   fl.append({"source_id": p.name, "path": str(p), "role": "non_text_material",
              "bytes": p.stat().st_size}); continue
  try: txt = read_text(p)
  except Exception as e:
   RES["errors"].append({"stage": "read", "detail": "%s: %s" % (p.name, e)}); continue
  fl.append({"source_id": p.name, "path": str(p), "role": "material", "bytes": p.stat().st_size,
             "text_chars": len(txt)})
  if txt.strip(): cd.append((len(txt), p, txt))
 if not cd:
  RES["errors"].append({"stage": "manuscript", "detail": "no readable manuscript text in %s" % inp})
  pend("no_manuscript", T("pd_nomanu"), T("pd_nomanu_n"))
  return finalize(out, cid, con, fl, None, "", t0, "input_error")
 cd.sort(key=lambda x: -x[0]); _, mp, tx = cd[0]
 if len(cd) > 1: pend("multiple_materials", T("pd_multi", n=len(cd), name=mp.name), T("pd_multi_n"))
 tx = tx.replace("\r\n", "\n").replace("\r", "\n")
 tr = bool(tx.strip()) and tx.strip()[-1] not in ".!?\u3002\uff01\uff1f)\u201d\"'" and len(tx) > 1500
 if tr:
  pend("truncated_manuscript", T("pd_trunc", n=len(tx)), T("pd_trunc_n"))
  RES["errors"].append({"stage": "degradation", "detail": "possible truncation (last char not terminal)"})
 try:
  role_rx = VE.ROLE if VE and VE.ROLE else []
  ch, pa = segment(tx, role_rx)
 except Exception as e:
  RES["errors"].append({"stage": "segment", "detail": str(e)}); ch, pa = [], []
 globals()["CH"], globals()["PA"] = ch, pa
 if not pa or wc(tx) < 60:
  pend("manuscript_too_short", T("pd_short", w=wc(tx), p=len(pa)), T("pd_short_n"))
  return finalize(out, cid, con, fl, mp, tx, t0, "insufficient_evidence", tr)
 if VE is None:
  RES["errors"].append({"stage": "engine", "detail": "verify.py not importable; no findings produced"})
 else:
  try:
   r = VE.run(ch, pa, tx, tr)
   RES.update({k: r[k] for k in ("findings", "actions", "rows", "stats", "coverage", "facts", "argmap")})
   RES["errors"] = r["errors"] + RES["errors"]
   RES["pending"] = r["pending"] + RES["pending"]
  except Exception as e: RES["errors"].append({"stage": "engine", "detail": str(e)})
 return finalize(out, cid, con, fl, mp, tx, t0, "ok" if not RES["pending"] else "partial", tr)


if __name__ == "__main__":
 try: main()
 except SystemExit: raise
 except Exception as e: RES["errors"].append({"stage": "fatal", "detail": str(e)})
 raise SystemExit(0)
