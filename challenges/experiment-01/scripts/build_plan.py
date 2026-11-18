

"""build_plan.py -- experiment-01 entry: research goal + resource/price/booking contracts +
candidate plan versions -> executable, costed, scheduled protocol.
Writes result.json / protocol.md / risk_table.csv. Stdlib only, no network, exit 0."""
import argparse, csv, hashlib, json, math, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plan_core import (G, L, TH, T, names, jd, pget, walk, pk, nk, fnum, dur, money, ext_eq, ext_rg, ext_dom, ext_plans, ext_steps, evl, repair, groups_of, risks_of, conv)

V = "1.0.0"
TS = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
COLS = G("risk_cols", ["id", "failure_mode"])
CM = [(t, re.compile(p, re.I)) for t, p in G("contract_map", [])]

def wj(p, o):
 p = Path(p)
 p.parent.mkdir(parents=True, exist_ok=True)
 p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def rd(p):
 b = Path(p).read_bytes()[:400000]
 for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
  try:
   return b.decode(e)
  except UnicodeDecodeError:
   continue
 return b.decode("utf-8", "replace")

def sha(p):
 h = hashlib.sha256()
 try:
  with open(p, "rb") as f:
   for c in iter(lambda: f.read(1 << 16), b""):
    h.update(c)
  return h.hexdigest()[:16]
 except OSError:
  return None

def inventory(ind):  
 ip = Path(ind)
 if not ip.is_dir():
  return []
 return [{"source_id": str(p.relative_to(ip)), "bytes": p.stat().st_size, "sha256_16": sha(p)} for p in sorted(ip.rglob("*")) if p.is_file() and not p.name.startswith(".")][:80]

def load_case(ind, errs):  
 ip = Path(ind)
 cs = [ip / "case.json"] if (ip / "case.json").is_file() else []
 cs += [p for p in sorted(ip.rglob("*.json")) if p.name.lower().startswith("case")]
 cs += [p for p in sorted(ip.rglob("*.json"))][:3]
 seen = set()
 for p in cs:
  if str(p) in seen:
   continue
  seen.add(str(p))
  try:
   d = json.loads(rd(p))
   if isinstance(d, dict) and d:
    return d, p, None
  except Exception as e:
   errs.append({"stage": "load_case", "file": str(p), "error": f"{type(e).__name__}: {e}"})
 return {}, None, L("no_case_file")

def ckeys(doc):
 c = (pk(doc, r"output_contract") or pk(doc, r"^(contract|output_schema)$")) if isinstance(doc, dict) else None
 if isinstance(c, dict):
  return [str(k) for k in c]
 return [x if isinstance(x, str) else str(pk(x, r"(name|字段)")) for x in c] if isinstance(c, list) else []

def scan(doc, pat, fn):
 for p, k, v in walk(doc):
  if isinstance(k, str) and re.search(pat, k, re.I) and not isinstance(v, bool):
   r = fn(v)
   if r[0] is not None:
    return r[0], r[1]
 return None, None

def nsize(doc):
 nc = fnum(pk(doc, r"(n_?per_?group|n_?per_?arm|sample_?size|replicates?|重复数|样本量)"))
 if nc:
  return int(nc), G("std", {}).get("n_input", ""), False
 dl, sd = fnum(pk(doc, r"(effect|delta|difference|效应|差值)")), fnum(pk(doc, r"(sd|sigma|std|标准差)"))
 if dl and sd:
  n = max(2, math.ceil(2 * ((1.959964 + 0.841621) / (abs(dl) / sd)) ** 2))
  return n, f"Δ={dl}, σ={sd} -> n=2((z0.975+z0.80)/(Δ/σ))^2≈{n}/组（双侧 α=0.05，power=0.80）", False
 return 3, G("std", {}).get("n_convention", ""), True

def build(ind, out, mode, doc, cerr):
 t0, errs, degr, gaps, evd, ch = time.time(), [], [], [], [], []
 src = inventory(ind)
 cid = None
 if doc:
  cid = next((str(doc[k]) for k in ("case_id", "caseId", "id", "case") if isinstance(doc.get(k), (str, int)) and not isinstance(doc.get(k), bool)), None)
 R = {"case_id": cid, "status": "partial", "runtime": {"started_utc": TS(), "skill_version": V, "mode": mode}}
 if not doc:
  R.update(status="input_error", errors=errs, sources=src, summary={"goal": "", "note": L("no_case_note")}, uncertainty=[{"item": L("no_case_file"), "why": cerr, "effect_on_plan": L("skeleton"), "how_to_resolve": "/input/case.json"}])
  return R, doc, None
 C = {"eq": ext_eq(doc), "rg": ext_rg(doc), "dom": ext_dom(doc), "goal": pk(doc, r"^(goal|research_?goal|objective|aim|" r"research_?question|task_?instruction|目标|研究目标)$") or pk(doc, r"(goal|objective|aim|目标)") or "", "budget": None, "cur": None, "window": None}
 C["goal"] = C["goal"].strip() if isinstance(C["goal"], str) else ""
 def bcur(v):
  if not isinstance(v, dict):
   return money(v)
  a, c = money(pk(v, r"(amount|total|金额|额度)"))
  return a, v.get("currency") or c
 C["budget"], C["cur"] = scan(doc, r"(budget|预算|费用上限|经费)", bcur)
 C["window"], _ = scan(doc, r"(time_?window|deadline|工期|时限|总时长|完成时间)", lambda v: (dur(v), None))
 if not any(x["source_id"] == "case.json" for x in src):
  src.append({"source_id": "case.json", "bytes": None, "sha256_16": None})
 GAP = G("gaps", {})
 n, basis, ngap = nsize(doc)
 if ngap:
  gaps.append(dict(GAP.get("n", {})))
 cands = []
 for i, pl in enumerate(ext_plans(doc)[1]):
  st = ext_steps(pl)
  if st:
   c = {"label": str(pk(pl, r"(version|id|label|名称|版本)") or f"cand{i+1}"), "steps": st, "n": n}
   c["m"] = evl(c, C)
   cands.append(c)
 if mode == "revise" and not cands:
  degr.append({"stage": "plan_selection", "what": L("revise_nofallback"), "effect": L("degraded_gen")})
 if mode == "generate" or not cands:
  mode = "generate"
  cands = [{"label": "generated", "n": n, "steps": [{"id": "S1", "act": L("gen_step"), "min": None, "stage": "s1", "rg": [], "params": {}, "eq": [C["eq"][0]["name"]] if C["eq"] else []}]}]
  cands[0]["m"] = evl(cands[0], C)
  gaps.append(dict(GAP.get("steps", {})))
 else:
  mode = "revise"
 cands.sort(key=lambda c: (c["m"]["score"], c["label"]))
 sel, meta = cands[0], {}
 for e in C["eq"] + C["rg"]:
  if e.get("ptr"):
   meta[e["ptr"]] = {"locator": "case.json#" + e["ptr"], "quote": jd(pget(doc, e["ptr"]))}
   evd.append({"claim_id": f"src_{e['id']}", "claim": f"{e['name']} 资源/价格/排期契约行", "kind": "json", "source_id": "case.json", "verified": None, **meta[e["ptr"]]})
 m = repair(sel, C, meta, ch)
 n = sel.get("n") or n
 grp = groups_of(n)
 ivs, dvs = [], []
 for p, k, v in walk(doc):
  if not isinstance(k, str):
   continue
  if re.search(r"(independent|factor|treatment|干预|自变量|因素)", k, re.I):
   ivs += [{"name": x, "basis": "input"} for x in names(v)[:6]]
  elif re.search(r"(dependent|readout|endpoint|measurement|指标|因变量|读出|检测指标)", k, re.I):
   dvs += [{"name": x, "basis": "input"} for x in names(v)[:6]]
 if len(ivs) < 2:
  ivs += [{"name": str(d["name"]), "basis": "input"} for d in list(C["dom"].values())[:2 - len(ivs)]]
 if not ivs:
  for s2 in sel["steps"]:
   for k2 in s2["params"]:
    if all(nk(k2) != nk(x["name"]) for x in ivs):
     ivs.append({"name": k2, "basis": "input"})
 if not dvs:
  dvs = [{"name": x, "basis": "input"} for x in names(pk(doc, r"(readout|endpoint|assay|指标|检测)"))[:3]]
 for bucket, tag in ((ivs, "iv"), (dvs, "dv")):
  if not bucket:
   bucket.append({"name": L(tag + "_tbd"), "basis": "missing"})
   gaps.append({"item": L(tag + "_tbd"), "why": L("gap_" + tag), "blocking": True, "action": L("act_" + tag)})
 use = {}
 for s in sel["steps"]:
  s["params_txt"] = "; ".join(f"{k}={v}" for k, v in s["params"].items())
  for r in s["rg"]:
   if isinstance(r, dict):
    use.setdefault(nk(r["name"]), []).append(r)
  s["rg"] = [r["name"] if isinstance(r, dict) else r for r in s["rg"]]
 mats = [{**g, "need": "; ".join(f"{r['qty']} {r['unit'] or ''}".strip() for r in use.get(nk(g["name"]), [])) or None, "cost": round(sum((conv(r["qty"], r["unit"] or g["unit"], g["punit"] or g["unit"]) or 0) * (g["price"] or 0) for r in use.get(nk(g["name"]), [])), 4) if use.get(nk(g["name"])) else None} for g in C["rg"]]
 for e in C["eq"]:
  e["need_h"] = round(m["eqh"].get(e["name"], 0.0), 2)
  e["verdict"] = (L("unused") if not e["need_h"] else L("book_unknown") if e["avail_h"] is None else L("book_ok") if e["need_h"] <= e["avail_h"] + 1e-9 else L("book_short"))
 risks = risks_of(C, m)
 crit = [{"id": c["id"], "basis_type": c["basis_type"], "text": L(c["t"], dv=dvs[0]["name"], iv=ivs[0]["name"])} for c in G("criteria", [])]
 gold = pk(doc, r"(gold_?standard|existing_?result|previous_?result|历史|金标准)")
 gs = {"text": G("std", {}).get("gold_input" if gold is not None else "gold_missing"), "basis_type": "input" if gold is not None else "missing"}
 hard = [{"name": v["code"], "status": L("fail"), "evidence": v["detail"]} for v in m["vio"]]
 if C["budget"] is not None:
  hard.append({"name": "budget", "status": L("pass") if m["cost"] <= C["budget"] else L("fail"), "evidence": f"{m['cost']:.2f} / {C['budget']:.2f}"})
 if C["window"] is not None:
  hard.append({"name": "time_window", "status": L("pass") if m["wall"] <= C["window"] else L("fail"), "evidence": f"{m['wall']:.0f} min / {C['window']:.0f} min"})
 verdict = ("not_feasible" if [h for h in hard if h["status"] == L("fail")] else "feasible_with_changes" if ch else "feasible")
 gaps += [{"item": nt.get("item"), "why": jd(nt), "blocking": False, "action": GAP.get("unpriced", {}).get("action")} for nt in m["note"]]
 gaps += [{"item": "排期:" + e["name"], "why": GAP.get("booking", {}).get("why"), "blocking": True, "action": GAP.get("booking", {}).get("action")} for e in C["eq"] if e["need_h"] and e["avail_h"] is None]
 for cond, key in ((C["budget"] is None, "budget"), (C["window"] is None, "window"), (not any(s["min"] for s in sel["steps"]), "duration")):
  if cond:
   gaps.append(dict(GAP.get(key, {})))
 total = n * len(grp)
 for i, c in enumerate(ch, 1):
  c["id"], c["version_from"], c["version_to"] = f"V{i}", sel["label"], "v-final"
 R.update({ "summary": {"goal": C["goal"], "mode": mode, "candidates": [c["label"] for c in cands], "selected": sel["label"], "cost": m["cost"], "currency": C["cur"], "wall_h": round(m["wall"] / 60, 2), "total_n": total, "verdict": verdict, "version": "v-final", "title": (C["goal"][:80] or "实验方案") + " " + L("title_suffix"), "protocol_file": "protocol.md", "risk_file": "risk_table.csv"}, "hypotheses": [{"id": "H1", "statement": L("hyps", iv=ivs[0]["name"], dv=dvs[0]["name"]), "null": L("hyp0", iv=ivs[0]["name"], dv=dvs[0]["name"]), "decision_rule": L("hyprule"), "basis_type": "derived" if ivs[0]["basis"] == "input" else "missing"}], "variables": [{"role": "independent", "name": ivs[0]["name"], "operational": L("iv_op"), "basis_type": ivs[0]["basis"], "levels": next((jd(d["values"]) for d in C["dom"].values() if nk(d["name"]) in nk(ivs[0]["name"])), None)}, {"role": "dependent", "name": dvs[0]["name"], "operational": L("dv_op"), "basis_type": dvs[0]["basis"]}, {"role": "confounder", "name": L("conf_name"), "operational": L("conf_op"), "basis_type": "principle"}], "groups": grp, "sample_size": {"per_group": n, "total": total, "groups": len(grp), "basis": basis}, "materials": mats, "equipment": C["eq"], "steps": sel["steps"], "schedule": {"total_wall_min": m["wall"], "total_person_min": m["person"], "stages": m["stages"], "estimated_cost": m["cost"], "material_cost": m["matc"], "equipment_cost": m["eqc"], "currency": C["cur"], "budget_limit": C["budget"], "time_window_min": C["window"], "within_budget": None if C["budget"] is None else m["cost"] <= C["budget"], "within_time_window": None if C["window"] is None else m["wall"] <= C["window"], "unknown_duration_steps": m["unk"]}, "risks": risks, "validation": {"criteria": crit, "gold_standard": gs}, "feasibility": {"verdict": verdict, "hard_constraints": hard}, "changes": ch, "pending_human": [g for g in gaps if g.get("blocking")], "uncertainty": [{"item": g.get("item"), "why": g.get("why"), "effect_on_plan": L("gap_struct"), "how_to_resolve": g.get("action")} for g in gaps] + [{"item": f"{nt['kind']}:{nt.get('item')}", "why": nt.get("detail", nt["kind"]), "effect_on_plan": L("not_costed"), "how_to_resolve": L("fill_units")} for nt in m["note"]], "evidence": evd, "sources": src, "errors": errs, "degradations": degr, "coverage": {"elements": {"hypothesis_variables": True, "controls": len(grp) >= 2, "equipment_materials": bool(C["eq"] and mats), "time_cost": m["wall"] > 0, "parameter_range": any(x["params"] for x in sel["steps"]), "risk_anomaly": bool(risks)}, "counts": {"steps": len(sel["steps"]), "materials": len(mats), "risks": len(risks), "changes": len(ch), "evidence": len(evd), "gaps": len(gaps)}}})
 ok = all(R["coverage"]["elements"].values()) and not m["vio"] and not R["pending_human"]
 R["status"] = "ok" if ok else "partial"
 R["runtime"]["elapsed_s"] = round(time.time() - t0, 2)
 return R, doc, C

TPL = HERE.parent / "references" / "protocol_template.md"

def protocol(R, C, m):
 sm, ss, cr, t = R["summary"], R["sample_size"], G("cost_rows", {}), {}
 for sp in G("report", []):
  t[sp["src"]] = T(TH(sp["th"]), [["; ".join(v[c]) if isinstance(v.get(c), list) else v.get(c) for c in sp["cols"]] for v in R.get(sp["src"]) or []])
 rows, acc = [], 0.0
 for g in dict.fromkeys(x["stage"] for x in R["steps"]):
  seg = [x for x in R["steps"] if x["stage"] == g]
  rows += [[x["id"], g, acc, acc + (x["min"] or 0)] for x in seg]
  acc += max((x["min"] or 0) for x in seg)
 t["sched"] = T(TH("sched"), rows)
 t["risk"] = T(TH("risk"), [[x.get(c) for c in ("id", "failure_mode", "early_signal", "mitigation", "stop_condition", "fallback")] for x in R["risks"]])
 cost = (f"{cr.get('material')} {m['matc']:.2f} + {cr.get('equipment')} {m['eqc']:.2f} = **{m['cost']:.2f} " f"{C.get('cur') or ''}**（{cr.get('budget')} {C['budget']:.2f}）" if C.get("budget") is not None else f"{m['cost']:.2f} {C.get('cur') or ''}（{L('not_given')}）")
 v = {"title": sm["title"], "version": sm["version"], "selected": sm["selected"], "mode": sm["mode"], "case_id": R["case_id"], "status": R["status"], "ts": R["runtime"].get("started_utc"), "goal": sm.get("goal") or L("goal_missing"), "verdict": sm["verdict"], "cost": sm["cost"], "cur": sm["currency"] or "", "wall_h": sm["wall_h"], "n": sm["total_n"], "n_note": L("s_n", n=ss["per_group"], tot=ss["total"], b=ss["basis"]), "wall_note": L("wall", h=f"{m['wall']/60:.2f}", u=m["unk"]) + "；" + L("person", h=f"{m['person']/60:.2f}") + "；" + L("win", w=f"{C['window']/60:.2f} h" if C.get("window") else L("not_given")), "cost_note": L("costline", c=cost), "criteria": "\n".join(f"- **{c['id']}** {c['text']}（{c['basis_type']}）" for c in R["validation"]["criteria"]), "gold": f"- {L('gold')}：{R['validation']['gold_standard']['text']}", "hard": "\n".join(f"- {x['name']}：{x['status']}（{x['evidence']}）" for x in R["feasibility"]["hard_constraints"]), "verdict_note": L("concl", v=R["feasibility"]["verdict"]), "pending": "\n".join(L("pend", i=k, item=x["item"], why=x["why"], act=x["action"]) for k, x in enumerate(R["pending_human"], 1)) or L("none"), "evidence": "\n".join(L("evl", cid=e["claim_id"], claim=e["claim"], loc=e["locator"], q=str(e["quote"])[:150]) for e in R["evidence"]), "sel_note": L("sel_from", s=sm["selected"], v=sm["version"]), "changes": "\n".join(L("chg", id=c["id"], op=c["op"], field=c["field"], before=c["before"], after=c["after"], rule=c["rule"]) for c in R["changes"]) or L("nochg"), "repro": L("repro"), "repro2": L("repro2")}
 out = TPL.read_text(encoding="utf-8") if TPL.is_file() else ""
 for k, val in {**t, **v}.items():
  out = out.replace("{{t:%s}}" % k, str(val)).replace("{{%s}}" % k, str(val))
 return out + "\n"

def echo(R, ks):  
 un = []
 for k in ks:
  if R.get(k) is None:
   R[k] = next((R.get(t) for t, p in CM if p.search(k) and R.get(t) is not None), None)
   if R[k] is None:
    un.append(k)
 if un:
  R.setdefault("uncertainty", []).append({"item": L("unmapped") + ", ".join(un), "why": L("no_target"), "effect_on_plan": L("null_shape"), "how_to_resolve": "references/io_contract.md"})
 return R

def resolve_out(s):
 for p in (Path(s), Path.cwd() / "output"):
  try:
   p.mkdir(parents=True, exist_ok=True)
   t = p / ".t"
   t.write_text("1", encoding="utf-8")
   t.unlink()
   return p
  except OSError:
   continue
 return Path.cwd()

def risk_csv(R, out):
 with open(out / "risk_table.csv", "w", encoding="utf-8-sig", newline="") as fh:
  w = csv.writer(fh)
  w.writerow(["risk_id" if c == "id" else c for c in COLS])
  w.writerows([[r.get(c, "") for c in COLS] for r in R.get("risks") or []])

def finish(R, ks, doc, C, out, t0):
 R = echo(R, ks)
 for k, d in (("case_id", None), ("status", "partial"), ("errors", []), ("degradations", []), ("changes", []), ("sources", []), ("uncertainty", []), ("pending_human", []), ("runtime", {})):
  R.setdefault(k, d)
 for k in ks:
  R.setdefault(k, None)
 R["runtime"].update({"elapsed_s_total": round(time.time() - t0, 2), "finalized_utc": TS()})
 sc = R.get("schedule") or {}
 m = {a: (sc.get(b) or 0) for a, b in (("wall", "total_wall_min"), ("person", "total_person_min"), ("matc", "material_cost"), ("eqc", "equipment_cost"), ("cost", "estimated_cost"), ("unk", "unknown_duration_steps"))}
 for name, need, fn in (("protocol.md", "steps", lambda: (out / "protocol.md").write_text(protocol(R, C or {}, m), encoding="utf-8")), ("risk_table.csv", "risks", lambda: risk_csv(R, out))):
  if R.get(need):
   try:
    fn()
   except Exception as e:
    R["degradations"].append({"stage": name, "error": f"{type(e).__name__}: {e}", "effect": "not_written"})
 bad = 0
 for e in R.get("evidence") or []:
  try:
   ok = e.get("kind") == "json" and jd(pget(doc or {}, e["locator"].split("#", 1)[-1])) == e["quote"]
  except Exception:
   ok = False
  e["verified"], bad = bool(ok), bad + (not ok)
 ss = R.get("sample_size") or {}
 arith = (abs(round(sum(x.get("cost") or 0 for x in (R.get("materials") or [])), 4) - m["matc"]) <= 0.01 and (ss.get("per_group") or 0) * (ss.get("groups") or 0) == (ss.get("total") or -1))
 R["self_check"] = {"quotes_failed": bad, "arithmetic_ok": arith, "contract_missing": [k for k in ks if R.get(k) is None], "elements": {k: bool(v) for k, v in ((R.get("coverage") or {}).get("elements") or {}).items()}}
 if (bad or not arith) and R.get("status") == "ok":
  R["status"] = "partial"
 wj(out / "result.json", R)
 return R

def main(argv=None):
 ap = argparse.ArgumentParser(prog="build_plan.py", description="experiment-01: 研究目标 + 资源契约 + 候选方案版本 -> 可执行、可计价、可排期实验方案", epilog="读 --input（默认 /input）的 case.json 与材料，向 --output（默认 /app/output）写 " "result.json / protocol.md / risk_table.csv；退出码恒为 0。")
 ap.add_argument("--input", default="/input", help="输入根目录")
 ap.add_argument("--output", default="/app/output", help="输出根目录")
 ap.add_argument("--mode", default="auto", choices=["auto", "generate", "revise"], help="auto=有候选版本则修订，否则生成")
 ap.add_argument("--version", action="version", version=f"%(prog)s {V}")
 a = ap.parse_args(argv)
 out, t0 = resolve_out(a.output), time.time()
 pre = {"case_id": None, "status": "partial", "errors": [], "degradations": [], "sources": [], "changes": [], "uncertainty": [{"item": "run", "why": L("partial_pre"), "effect_on_plan": L("skeleton")}], "runtime": {"started_utc": TS(), "stage": "partial"}}
 doc, cerr, ks = {}, None, []
 try:
  doc, _, cerr = load_case(a.input, [])
  ks = ckeys(doc)
  if doc:
   pre["case_id"] = str(next((doc[k] for k in ("case_id", "caseId", "id", "case") if isinstance(doc.get(k), (str, int))), "") or "") or None
  for k in ks:
   pre.setdefault(k, None)
 except Exception:
  pass
 wj(out / "result.json", pre)
 try:
  R, doc, C = build(a.input, out, a.mode, doc, cerr)
 except Exception as e:
  R, C = {"case_id": pre["case_id"], "status": "partial", "sources": [], "uncertainty": [], "degradations": [{"stage": "build", "what": L("build_abort"), "effect": L("only_skeleton")}], "errors": [{"stage": "build", "error": f"{type(e).__name__}: {e}"}]}, None
 try:
  R = finish(R, ckeys(doc) or ks, doc, C, out, t0)
 except Exception as e:
  try:
   wj(out / "result.json", {**pre, "errors": [{"stage": "finalize", "error": f"{type(e).__name__}: {e}"}]})
  except Exception:
   pass
 try:
  print(jd({"case_id": R.get("case_id"), "status": R.get("status"), "files": sorted(p.name for p in out.iterdir() if p.is_file()), "counts": (R.get("coverage") or {}).get("counts"), "self_check": R.get("self_check")}))
 except Exception:
  pass
 return 0

if __name__ == "__main__":
 sys.exit(main())
