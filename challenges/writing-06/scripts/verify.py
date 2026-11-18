#!/usr/bin/env python3
"""Rule engine + verifier for paper-structure-logic-review.

Holds the six structural detectors (each finding needs a verbatim quote + locator), the
action builder and the artifact checks. Can be run standalone:

  python3 verify.py --out /app/output [--input /input]
"""
import argparse, json, re
from pathlib import Path

H = Path(__file__).resolve().parent
M = {}
for _c in (H.parent / "references" / "messages.json", H / "messages.json"):
 if _c.is_file():
  try: M = json.loads(_c.read_text(encoding="utf-8")); break
  except Exception: M = {}

DIMS = ["research_question_alignment", "section_structure", "argument_chain",
        "paragraph_relations", "duplication", "conclusion_boundary"]
OPS = ["move", "merge", "split", "narrow", "delete", "insert"]
OPB = {"duplication": "merge", "section_structure": "move", "argument_chain": "insert",
       "paragraph_relations": "split", "conclusion_boundary": "narrow",
       "research_question_alignment": "narrow"}
DF = {"rq": "research question", "contr": "we show", "cite": r"\[\d+\]",
      "numu": r"\d+(?:\.\d+)?\s*(?:%|mg|kg|mm|cm|h|min|s|K|nM|mM|mL|L)",
      "figr": r"Fig\w*\.?\s*(\d+)", "fcap": r"(?i)^(?:figure|fig|table)\s*(\d+)",
      "claim": "(?i)suggest|indicate|therefore", "conn": "(?i)^however|moreover|therefore",
      "causal": "(?i)caus|leads? to", "hedge": "(?i)may|might|suggest", "abs": "(?i)always|never|prove",
      "corr": "(?i)correlat|associat", "causd": "(?i)control group|randomi|intervention",
      "refn": r"(?m)^\s*\[?(\d{1,3})[\]\.\)]\s+\S"}
P = {k: re.compile(v) for k, v in DF.items()}
for k, v in (M.get("pat") or {}).items():
 try: P[k] = re.compile(v)
 except Exception: pass
ROLE = [(a, re.compile(b)) for a, b in (M.get("role") or [])]
STOP = set(("the a an and or of to in for on with as at by from that this these those is are was were be "
            "been we our it its not no than then using used use can may also such more most other into "
            "between within under over all any both each how what which while where when who has have had "
            "do does did one two three study paper results data").split())
F, A, D2, PH, ER, DS = [], [], [], [], [], {}
CO, TR = "", False


def T(_k, **kw):
 s = M.get(_k)
 if not isinstance(s, str): return ""
 try: return s.format(**kw)
 except Exception: return s


def D_(d): return (M.get("dim_cn") or {}).get(d, d)


def S_(s): return (M.get("sev_cn") or {}).get(s, s)


def sec_cn(r): return (M.get("sec") or {}).get(r, r)


def norm(t): return re.sub(r"\s+", " ", t or "").strip()


def ground(q):
 q = norm(q)
 return bool(q) and (q in CO or q.lower() in CO.lower())


def wc(t):
 return len(re.findall(r"[A-Za-z][A-Za-z\-']*", t)) + len(re.findall(r"[\u4e00-\u9fff]", t)) // 2


def toks(t):
 low = t.lower(); cjk = re.findall(r"[\u4e00-\u9fff]", low)
 lat = [w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", low) if w not in STOP]
 if len(cjk) > max(6, len(lat) * 3): return [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)] + lat
 return lat


def jacc(a, b): return 0.0 if not a or not b else len(a & b) / float(len(a | b))


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


def _first_sent_end(t, lo, hi):
 for i in range(lo, min(len(t), hi) + 1):
  if t[i - 1] in _SENT_TERM and _is_sent_boundary(t, i - 1):
   return i
 return None


def snip(t, lim=150):
 t = norm(t); b = _first_sent_end(t, 15, lim)
 for c in ([t[:b]] if b else []) + [t[:lim], t[:lim * 2], t[:lim * 3]]:
  if ground(c): return norm(c)
 for k in range(min(len(t), 240), 8, -3):
  if ground(t[:k]): return norm(t[:k])
 return ""


def pend(kind, detail, need):
 PH.append({"item_id": "PH%02d" % (len(PH) + 1), "kind": kind, "detail": detail, "needed_action": need})


def add(dim, sev, loc, q, _r, op, conf, to="", **kw):
 g = snip(q)
 if not g:
  ER.append({"stage": "grounding", "detail": "dropped %s at %s (quote not verbatim)" % (dim, loc)}); return None
 f = {"finding_id": "F%02d" % (len(F) + 1), "dimension": dim, "severity": sev, "locator": loc,
      "quote": g, "diagnosis": T(_r, **kw) or _r, "evidence_for_judgment": T(_r + "_b", **kw),
      "confidence": conf}
 f["_o"], f["_t"] = op or OPB[dim], to or loc
 f["_e"] = T(_r + "_e", **kw) or (M.get("exp") or {}).get(dim, "")
 f["_r"] = T(_r + "_r", **kw) or (M.get("risk") or {}).get(f["_o"], "")
 F.append(f); return f


def cp_text(pa, roles): return "\n".join(p["text"] for p in pa if p["role"] in roles)


def det_sec(ch, pa):
 R = {}
 for p in pa: R.setdefault(p["role"], []).append(p)
 DS["chapters"] = len(ch)
 if len(ch) <= 1:
  add("section_structure", "high", pa[0]["loc"], pa[0]["text"], "s1", "insert", "high",
      ch=len(ch), pp=len(pa)); return
 pres = sorted(R)
 for r in ("introduction", "method", "result", "conclusion"):
  if r == "conclusion" and ({"conclusion", "discussion"} & set(pres)): continue
  if r in pres: continue
  if TR: pend("truncated_manuscript", T("pd_trunc_dim", label=sec_cn(r)), T("pd_trunc_dim_n")); continue
  add("section_structure", "high", pa[-1]["loc"], pa[-1]["text"], "s2", "insert", "high",
      label=sec_cn(r), present=pres, role=r, pp=len(pa))
 sq = [(c["loc"], c["role"]) for c in ch
       if c["role"] in ("introduction", "method", "result", "discussion", "conclusion")]
 rs = [r for _, r in sq]
 for a, b in (("method", "result"), ("result", "discussion"), ("result", "conclusion")):
  if a in rs and b in rs and rs.index(a) > rs.index(b):
   cl = [x for x, r in sq if r == b][0]; ce = [x for x, r in sq if r == a][0]
   p = [x for x in pa if x["loc"].startswith(cl)][0]
   add("section_structure", "high", p["loc"], p["text"], "s3", "move", "high", to=ce, a=sec_cn(a),
       b=sec_cn(b), seq=" > ".join("%s(%s)" % (x, r) for x, r in sq), cl=cl, ce=ce); break
 tt = sum(c["words"] for c in ch) or 1
 DS["share"] = {c["loc"] + " " + (c["title"] or "")[:40]: round(c["words"] / float(tt), 3) for c in ch}
 if "references" in R and not P["refn"].search(R["references"][0]["text"]):
  add("section_structure", "medium", R["references"][0]["loc"], R["references"][0]["text"],
      "s5", "insert", "medium")


def det_rq(pa, tx):
 cd = [p for p in pa if p["role"] in ("abstract", "introduction", "body")] or pa
 rq = loc = ""
 for p in cd[:8]:
  for sl, s in p["sents"]:
   if P["rq"].search(s) and wc(s) >= 8: rq, loc = s, sl; break
  if rq: break
 if not rq:
  if wc(tx) < 300: pend("no_research_question", T("pd_no_rq"), T("pd_no_rq_n")); return
  add("research_question_alignment", "high", cd[0]["loc"], cd[0]["text"], "r1", "insert", "medium"); return
 tg = set(toks(cp_text(pa, ("result", "discussion", "conclusion")) or tx))
 tm = [t for t in toks(rq) if len(t) > 4][:10]; ms = [t for t in tm if t not in tg]
 if tm and len(ms) >= max(3, int(.5 * len(tm))):
  add("research_question_alignment", "high", loc, rq, "r2", "narrow", "medium",
      terms=tm, k=len(ms), miss=ms[:6])
 for p in cd[:6]:
  for sl, s in p["sents"]:
   if P["contr"].search(s) and len(s) > 40:
    ct = [t for t in toks(s) if len(t) > 4][:8]; cm = [t for t in ct if t not in tg]
    if ct and len(cm) >= max(3, int(.6 * len(ct))):
     add("research_question_alignment", "medium", sl, s, "r3", "narrow", "low-medium",
         terms=ct, k=len(cm)); return


def det_arg(pa, tx):
 rf = set(int(x) for x in P["refn"].findall(tx))
 us, wh = set(), {}
 for p in pa:
  if p["role"] in ("references", "ack", "appendix"): continue
  ev = [s for _, s in p["sents"] if P["cite"].search(s) or P["numu"].search(s) or P["figr"].search(s)]
  cl = [(sl, s) for sl, s in p["sents"] if P["claim"].search(s)
        and not (P["cite"].search(s) or P["numu"].search(s) or P["figr"].search(s))]
  for sl, s in p["sents"]:
   for m in P["cite"].finditer(s):
    for n in re.findall(r"\d+", m.group(0)):
     us.add(int(n)); wh.setdefault(int(n), (sl, s))
  if cl and not ev and wc(p["text"]) >= 30 and p["role"] != "abstract":
   add("argument_chain", "high" if p["role"] in ("result", "discussion", "conclusion") else "medium",
       cl[0][0], cl[0][1], "a1", "insert", "medium", n=len(p["sents"]), c=len(cl))
 for n in (sorted(us - rf)[:3] if rf else []):
  add("argument_chain", "high", wh.get(n, ("", ""))[0], wh.get(n, ("", ""))[1], "a2", "insert", "high",
      n=n, u=len(us), r=len(rf), bad=sorted(us - rf)[:5])
 if us and not rf: pend("no_reference_list", T("pd_noref", n=len(us)), T("pd_noref_n"))
 cp = set(m.group(1) for m in (P["fcap"].match(ln.strip()) for ln in tx.splitlines()) if m)
 rl, ms = set(P["figr"].findall(tx)), []
 ms = sorted(rl - cp)
 if ms:
  for p in pa:
   hit = [(sl, s) for sl, s in p["sents"] if ms[0] in P["figr"].findall(s)]
   if hit:
    add("argument_chain", "medium", hit[0][0], hit[0][1], "a3", "insert", "medium",
        lab=ms[0], ref=sorted(rl), cap=sorted(cp)); break
 DS["cit"] = {"in_text": len(us), "refs": len(rf), "unresolved": sorted(us - rf)[:10] if rf else [],
              "fig_ref": sorted(rl), "caps": sorted(cp)}


def det_par(pa):
 bd = [p for p in pa if p["role"] not in ("references", "ack", "appendix")]
 tj = {p["loc"]: set(toks(p["text"])) for p in bd}
 jm = sp = 0
 for a, b in zip(bd, bd[1:]):
  if a["ch"] != b["ch"] or jm >= 2 or wc(a["text"]) < 55 or wc(b["text"]) < 55: continue
  v = jacc(tj[a["loc"]], tj[b["loc"]])
  if v < 0.05 and not P["conn"].match(b["text"]):
   jm += 1
   add("paragraph_relations", "low", b["sents"][0][0], b["sents"][0][1], "p1", "insert", "low-medium",
       a=a["loc"], b=b["loc"], v=v)
 for p in bd:
  if sp >= 2: break
  nn = sum(1 for _, s in p["sents"] if P["numu"].search(s))
  nc = sum(1 for _, s in p["sents"] if P["claim"].search(s))
  if wc(p["text"]) >= 120 and nn >= 2 and nc >= 1:
   sp += 1
   add("paragraph_relations", "medium", p["loc"], p["text"], "p2", "split", "medium",
       to=p["sents"][0][0], w=wc(p["text"]), nn=nn, nc=nc)
 DS["pp"] = max(0, len(bd) - 1)


def det_dup(pa):
 bd = [p for p in pa if p["role"] not in ("references", "ack", "appendix") and wc(p["text"]) >= 45]
 sh = {}
 for p in bd:
  t = toks(p["text"]); sh[p["loc"]] = set(tuple(t[i:i + 8]) for i in range(max(0, len(t) - 7)))
 pr = []
 for i in range(len(bd)):
  for j in range(i + 1, len(bd)):
   a, b = bd[i], bd[j]
   if sh[a["loc"]] and sh[b["loc"]]:
    v = jacc(sh[a["loc"]], sh[b["loc"]])
    if v >= 0.30: pr.append((v, a, b))
 pr.sort(key=lambda x: -x[0])
 for v, a, b in pr[:5]:
  cross = a["ch"] != b["ch"]
  add("duplication", "high" if (cross and v >= 0.5) else "medium", b["loc"], b["text"], "d1", "merge",
      "high" if v >= 0.5 else "medium", to=a["loc"], a=a["loc"], b=b["loc"], v=v,
      kind=T("d1_cross") if cross else T("d1_intra"))
 sd = {}
 for p in pa:
  if p["role"] in ("references", "ack", "appendix") or wc(p["text"]) < 25: continue
  for sl, s in p["sents"]:
   k = re.sub(r"\W+", "", s.lower())
   if len(k) >= 55: sd.setdefault(k, []).append((sl, s, p["loc"]))
 for k, v in sd.items():
  if len(v) >= 2 and len(F) < 40:
   add("duplication", "medium", v[-1][0], v[-1][1], "d2", "delete", "high",
       a=v[0][2], b=v[-1][2], n=len(k), k=len(v))
 DS["dp"], DS["pm"] = len(pr), round(pr[0][0], 3) if pr else 0.0


def det_con(pa):
 sc = cp_text(pa, ("method", "result", "abstract")); scn = set(re.findall(r"\d+(?:\.\d+)?", sc))
 tg = [p for p in pa if p["role"] in ("conclusion", "discussion", "abstract")]
 if not tg: return
 cor, cau = bool(P["corr"].search(sc)), bool(P["causd"].search(sc))
 n = nm = 0
 for p in tg:
  for sl, s in p["sents"]:
   if n >= 6: break
   if P["causal"].search(s) and not P["hedge"].search(s) and cor and not cau:
    n += 1
    add("conclusion_boundary", "high", sl, s, "c1", "narrow", "high",
        terms=",".join(sorted(set(x.lower() for x in P["corr"].findall(sc)))[:3]))
   elif P["abs"].search(s) and not P["hedge"].search(s) and wc(s) >= 8:
    n += 1
    add("conclusion_boundary", "medium", sl, s, "c2", "narrow", "medium",
        terms=",".join(sorted(set(x.lower() for x in P["abs"].findall(s)))[:3]))
   elif nm < 2 and wc(s) >= 6 and P["numu"].search(s):
    vv = [m.group(0) for m in P["numu"].finditer(s)
          if re.match(r"\d+(?:\.\d+)?", m.group(0)).group(0) not in scn]
    if vv:
     nm += 1; n += 1
     add("conclusion_boundary", "low", sl, s, "c3", "narrow", "low-medium", vals=vv[:2])
 DS["cn"] = sum(len(p["sents"]) for p in tg)


def mkacts():
 for f in F:
  o, t = f.pop("_o"), f.pop("_t")
  f["action_id"] = "A%02d" % (len(A) + 1)
  A.append({"action_id": f["action_id"], "finding_id": f["finding_id"], "operation": o,
            "from_locator": f["locator"], "to_locator": t, "expected_effect": f.pop("_e"),
            "risk": f.pop("_r"), "priority": {"high": "P1", "medium": "P2", "low": "P3"}[f["severity"]],
            "executable": True})
  D2.append({"aid": f["action_id"], "pr": A[-1]["priority"], "dim": D_(f["dimension"]),
             "sev": S_(f["severity"]), "floc": f["locator"],
             "arrow": "" if t == f["locator"] else " -> `%s`" % t, "quote": f["quote"],
             "diag": f["diagnosis"], "basis": f["evidence_for_judgment"], "op": o,
             "eff": A[-1]["expected_effect"], "risk": A[-1]["risk"]})


def coverage(pa):
 ev = {"duplication": T("cov_dup", n=DS.get("pp", 0), v=DS.get("pm", 0.0)),
       "section_structure": T("cov_sec", n=DS.get("chapters", 0)),
       "argument_chain": T("cov_arg", n=len([p for p in pa if p["role"] not in ("references", "ack", "appendix")])),
       "paragraph_relations": T("cov_par", n=DS.get("pp", 0)),
       "conclusion_boundary": T("cov_con", n=DS.get("cn", 0)),
       "research_question_alignment": T("cov_rq")}
 o = {}
 for d in DIMS:
  ids = [f["finding_id"] for f in F if f["dimension"] == d]
  o[d] = {"status": "findings" if ids else "no_issue_with_evidence", "finding_ids": ids,
          "checked": T("co_checked") if ids else ev[d]}
 return o


def facts(pa):
 o = []
 for p in pa:
  if p["role"] in ("references", "ack", "appendix"): continue
  for sl, s in p["sents"]:
   if len(o) >= 25: return o
   if P["numu"].search(s) or P["cite"].search(s) or P["hedge"].search(s):
    o.append({"fact_id": "PF%02d" % (len(o) + 1), "locator": sl, "quote": s, "note": T("pf_note"),
              "kind": "number" if P["numu"].search(s) else (
                  "citation" if P["cite"].search(s) else "scope")})
 return o


def argmap(pa):
 ch = []
 for p in pa:
  if p["role"] in ("references", "ack", "appendix"): continue
  cl = [{"locator": sl, "quote": s} for sl, s in p["sents"] if P["claim"].search(s)]
  ev = [{"locator": sl, "quote": s, "kind": "citation" if P["cite"].search(s)
         else ("number" if P["numu"].search(s) else "figure")}
        for sl, s in p["sents"] if P["cite"].search(s) or P["numu"].search(s) or P["figr"].search(s)]
  if cl: ch.append({"chapter": "C%02d" % p["ch"], "paragraph": p["loc"], "claim": cl[0],
                    "evidence": ev, "status": "supported" if ev else "unsupported"})
 rq = next((f for f in F if f["dimension"] == "research_question_alignment"), None)
 return {"research_question": {"quote": rq["quote"], "locator": rq["locator"]} if rq
         else {"quote": "", "locator": ""}, "chains": ch,
         "unsupported_chains": len([c for c in ch if c["status"] == "unsupported"]),
         "method": T("arg_method")}


def run(ch, pa, tx, tr=False):
 global CO, TR
 CO, TR = norm(tx), tr
 for fn in (lambda: det_sec(ch, pa), lambda: det_rq(pa, tx), lambda: det_arg(pa, tx),
            lambda: det_par(pa), lambda: det_dup(pa), lambda: det_con(pa)):
  try: fn()
  except Exception as e: ER.append({"stage": "detector", "detail": str(e)})
 try: mkacts()
 except Exception as e: ER.append({"stage": "actions", "detail": str(e)})
 return {"findings": F, "actions": A, "rows": D2, "pending": PH, "errors": ER, "stats": DS,
         "coverage": coverage(pa), "facts": facts(pa), "argmap": argmap(pa)}


def verify(out, keys=None):
 out = Path(out)
 try:
  rv = json.loads((out / "structural_review.json").read_text(encoding="utf-8"))
  res = json.loads((out / "result.json").read_text(encoding="utf-8"))
 except Exception as e:
  return {"pass": False, "error": "cannot read artifacts: %s" % e, "checks": []}
 f, acts = rv.get("findings", []), rv.get("actions", [])
 ids = [x.get("finding_id") for x in f]
 chk = [("findings_quotes_verbatim", all(x.get("quote") for x in f)),
        ("six_dimensions", len(rv.get("dimension_coverage", {})) == 6),
        ("finding_action_join", all(a.get("finding_id") in ids for a in acts)),
        ("actions_valid", all(a.get("operation") in OPS and a.get("from_locator")
                              and a.get("expected_effect") for a in acts)),
        ("contract_keys", all(k in res for k in (keys or []))),
        ("no_full_rewrite_file", not any((out / n).exists()
                                         for n in ("manuscript.md", "rewrite.md", "revised.md"))),
        ("case_id_kept", bool(res.get("case_id")))]
 return {"pass": all(v for _, v in chk), "checks": [{"check": k, "pass": v} for k, v in chk],
         "counts": {"findings": len(f), "actions": len(acts),
                    "dimensions_with_findings": sum(1 for v in rv.get("dimension_coverage", {}).values()
                                                    if v.get("finding_ids")),
                    "quote_hit_rate": rv.get("grounding", {}).get("hit_rate"),
                    "pending_human": len(res.get("pending_human") or []),
                    "errors": len(res.get("errors") or [])}}


def main(argv=None):
 ap = argparse.ArgumentParser(description="Verify structural-review artifacts: quote grounding, "
                                         "six-dimension coverage, action validity, contract keys.")
 ap.add_argument("--out", default=str(Path("/app/output") if Path("/app").is_dir() else Path.cwd() / "output"))
 ap.add_argument("--input", default=str(Path("/input") if Path("/input").is_dir() else Path.cwd() / "input"))
 a = ap.parse_args(argv)
 keys = []
 try:
  cj = Path(a.input) / "case.json"
  if cj.is_file():
   keys = list((json.loads(cj.read_text(encoding="utf-8")).get("output_contract") or {}).keys())
 except Exception: keys = []
 r = verify(a.out, keys)
 print(json.dumps(r, ensure_ascii=False, indent=2))
 return 0


if __name__ == "__main__":
 try: main()
 except SystemExit: raise
 except Exception as e: print(json.dumps({"pass": False, "error": str(e)}))
 raise SystemExit(0)
