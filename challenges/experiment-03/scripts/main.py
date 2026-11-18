#!/usr/bin/env python3
"""experiment-03 bounded parameter optimization."""
import argparse, itertools, json, math, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import *  # noqa: F401,F403

KEYS = ("goal", "summary", "comparison", "parameters", "metrics", "search", "schedule", "materials", "equipment",
        "validation", "risks", "pending", "hypotheses", "variables", "feasibility", "steps")

def collect(case, ctx, rel):
  R, E, M, P = {}, [], [], []
  for ptr, v in walk(case):
    if not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
      continue
    low = ptr.lower()
    if re.search(r"plan|candidate|version|方案|候选|版本", low):
      P += [{"ptr": "%s/%d" % (ptr, i), "record": x} for i, x in enumerate(v)]
      continue
    for i, x in enumerate(v):
      nm = pick(x, ("name", "名称", "parameter", "参数", "material", "试剂", "instrument", "设备"))
      rg, dom = pick(x, ("range", "量程", "范围", "spec")), pick(x, ("domain", "levels", "values", "取值"))
      lo, hi, u = prange(rg if rg is not None else dom)
      sid = asrc(ctx, rel, "%s/%d" % (ptr, i), qs(rg if rg is not None else (dom if dom is not None else nm)), "输入")
      if re.search(r"equip|instrument|设备|仪器|device", low):
        E.append({"name": str(nm or "eq%d" % i), "lo": lo, "hi": hi, "unit": u, "spec": qs(rg) if rg is not None else None,
                  "source_id": sid, "setting": None, "gap": None if (lo is not None or hi is not None) else "未解析"})
        addb(R, ckey(nm, u), nm, u, lo, hi, sid, "equipment_limit", "量程")
      elif re.search(r"reagent|material|耗材|试剂|材料|chemical", low):
        sp = pick(x, ("spec", "规格", "purity", "纯度", "grade", "catalog", "货号"))
        pv, am = pick(x, ("price", "单价", "价格")), pick(x, ("amount", "用量", "qty", "dosage"))
        M.append({"name": str(nm or "mat%d" % i), "spec": qs(sp) if sp is not None else None, "unit_price": num(pv),
                  "price_unit": un(pick(x, ("price_unit", "计价单位")) or (ut(pv) if isinstance(pv, str) else "")),
                  "price_raw": qs(pv) if pv is not None else None, "amount": num(am),
                  "amount_unit": ut(am) if isinstance(am, str) else "",
                  "gap": None if (pv is not None and am is not None) else "缺单价/用量", "source_id": sid})
      elif isinstance(nm, str) and (dom is not None or lo is not None or hi is not None):
        uu = pick(x, ("unit", "units", "单位")) or ""
        e = rget(R, ckey(nm, uu if isinstance(uu, str) else u), nm, uu if isinstance(uu, str) else u)
        if isinstance(dom, list):
          e["levels"] += [z for z in map(num, dom) if z is not None and z not in e["levels"]]
        e["step"] = e["step"] or num(pick(x, ("step", "步长")))
        e["fixed"] = e["fixed"] if e["fixed"] is not None else num(pick(x, ("default", "value", "fixed", "baseline")))
        e["name"] = str(nm) if nm else e["name"]
        addb(R, e["key"], nm, uu, lo, hi, sid, "declared_domain", "域")
  return R, E, M, P

def fitlin(xs, ys):
  n = len(xs)
  sx, sy = sum(xs), sum(ys)
  sxx, sxy = sum(x * x for x in xs), sum(x * y for x, y in zip(xs, ys))
  den = n * sxx - sx * sx
  if n < 3 or abs(den) < 1e-12:
    return None
  b = (n * sxy - sx * sy) / den
  a = (sy - b * sx) / n
  f = lambda x: a + b * x
  mu = sy / n
  st, sr = sum((y - mu) ** 2 for y in ys), sum((y - f(x)) ** 2 for x, y in zip(xs, ys))
  return {"coef": [a, b], "deg": 1, "r2": (1 - sr / st) if st else 0.0,
          "sigma": math.sqrt(sr / max(1, n - 2)), "n": n, "f": f, "ran": [min(xs), max(xs)]}

def models(case, ctx, R):
  out = []
  for t in tables(case, ctx):
    rows = [r for r in t["rows"] if isinstance(r, dict)]
    if len(rows) < 3:
      continue
    mc = [c for c in rows[0] if re.search(MET, str(c), re.I)]
    for a in [c for c in rows[0] if c not in mc and ckey(c) in R]:
      for b in mc:
        xy = [(x, y) for x, y in ((num(r.get(a)), num(r.get(b))) for r in rows) if x is not None and y is not None]
        if len(xy) >= 3 and len({x for x, _ in xy}) >= 3:
          f = fitlin([x for x, _ in xy], [y for _, y in xy])
          if f:
            out.append(dict(f, metric=str(b), param=ckey(a), ok=f["r2"] >= 0.5))
  return out

def feas(R):
  L, C, F = {}, [], {}
  for k, e in R.items():
    lo, hi, bl, bh = eff(e)
    if lo is not None and hi is not None and lo > hi + 1e-12:
      C.append({"parameter": k, "name": e["name"], "lower": rnd(lo), "upper": rnd(hi), "gap": rnd(lo - hi),
                "lower_source": bl["source_id"] if bl else None, "upper_source": bh["source_id"] if bh else None})
      continue
    lv = [x for x in sorted(e["levels"]) if (lo is None or x >= lo - 1e-9) and (hi is None or x <= hi + 1e-9)]
    if len(lv) < 2 and lo is not None and hi is not None and hi - lo > 1e-12:
      n = max(2, min(int(round((hi - lo) / e["step"])) + 1 if e["step"] else 5, 5))
      lv = [round(lo + i * (hi - lo) / (n - 1), 8) for i in range(n)]
    if len(lv) >= 2:
      L[k] = lv
    elif (lv[0] if lv else e["fixed"]) is not None:
      F[k] = lv[0] if lv else e["fixed"]
  return L, C, F

def srch(R, L, F, mods, mats, a, t0):
  per = {k: L[k] for k in sorted(L)}
  while per and math.prod(len(v) for v in per.values()) > max(8, a.max_candidates):
    k = max(per, key=lambda x: len(per[x]))
    if len(per[k]) <= 2:
      break
    per[k] = per[k][::2]
  combos = [dict(zip(per, v)) for v in itertools.product(*per.values())] if per else []
  ms = sorted({m["metric"] + "/" + m["param"] for m in mods})
  dr = {m: ("min" if re.search(MINL, m.split("/")[0]) and not re.search("purity|纯度", m) else "max") for m in ms}
  rc = rcost(mats)
  pool = []
  for c in combos:
    pt = dict(F)
    pt.update(c)
    pool.append({"pt": pt, "pr": {m["metric"] + "/" + m["param"]: m["f"](pt[m["param"]]) for m in mods if m["param"] in pt}, "cost": rc["subtotal"]})
  rng = {m: [min([p["pr"][m] for p in pool if m in p["pr"]] or [0]), max([p["pr"][m] for p in pool if m in p["pr"]] or [0])] for m in ms}

  def score(p):
    out = []
    for m in ms:
      if m in p["pr"] and rng[m][1] > rng[m][0]:
        s = (p["pr"][m] - rng[m][0]) / (rng[m][1] - rng[m][0])
        out.append(1 - s if dr[m] == "min" else s)
    return max(0.0, sum(out) / len(out)) if out else None

  for p in pool:
    p["sc"] = score(p)
  rank = sorted([p for p in pool if p["sc"] is not None], key=lambda p: (-p["sc"], p["cost"] or 0))
  best = rank[0] if rank else None
  rounds = [{"round": 1, "method": "full_factorial" if per else "no_domain", "evaluated": len(pool),
             "best": best["pt"] if best else None, "best_score": rnd(best["sc"]) if best else None, "note": "枚举"}]
  if best is None and combos:
    anc = {k: v[len(v) // 2] for k, v in per.items()}
    anc.update({k: v for k, v in F.items() if k not in anc})
    best = {"pt": anc, "pr": {}, "sc": None, "cost": rc["subtotal"]}
    rounds[0].update({"method": "screening_anchor(no_data)", "best": anc, "note": "无数据：中心锚点，非最优"})
  if best:
    rounds.append({"round": 2, "method": "local_half_step", "status": "planned", "evaluated": 0, "best": None,
                   "note": "边界>1%域宽则±半步补点；改进<1%或预算耗尽即停"})
  return {"rounds": rounds, "best": best or {}, "pool": pool, "metrics": ms, "rc": rc}

def proto(D):
  tp = Path(__file__).resolve().parent.parent / "references" / "protocol_template.md"
  T = tp.read_text(encoding="utf-8") if tp.is_file() else "# 方案\n\n{{goal}}\n"
  d = {"goal": D["goal"] or "-", "ver": V, "at": iso(), "status": D["status"], "cid": D["case_id"] or "-",
       "hyp": "\n".join("**%s** %s → 检验: %s" % (h["id"], h["statement"], h["test"]) for h in D["hypotheses"]),
       "params": tbl(["参数", "建议值", "区间", "单位", "绑定约束", "依据"],
                     [[p["name"], ft(p["recommended"]), "%s – %s" % (ft(p["lower"]), ft(p["upper"])), p["unit"] or "-",
                       p["binding"] or "-", ",".join(b["source_id"] for b in p["basis"]) or "-"] for p in D["parameters"]]),
       "vars": "IV: %s；DV: %s；对照: %s" % ("/".join(D["variables"]["iv"]) or "-", "/".join(D["variables"]["dv"]) or "-", "/".join(D["variables"]["control"])),
       "mat": tbl(["对象", "规格", "缺口"], [[x["name"], x.get("spec") or x.get("setting") or "-", x.get("gap") or "-"] for x in D["materials"] + D["equipment"]]),
       "steps": "\n".join("%d. %s" % (i + 1, x) for i, x in enumerate(D["steps"])),
       "valid": "\n".join(["- %s: %s（%s）" % (v["metric"], v["criterion"], v["method"]) for v in D["validation"]["criteria"]] +
                          ["- STOP: %s" % x for x in D["validation"]["stop"]]),
       "risks": tbl(["风险", "触发", "处置", "替代"], [[r["risk"], r["trigger"], r["contingency"], r["alternative"]] for r in D["risks"]]),
       "sched": "批次 %s · 单批材料成本 %s · 预算 %s %s" % (D["schedule"].get("runs"), ft(D["schedule"].get("cost_per_run")),
                                                       ft(D["cost"].get("budget")), D["cost"].get("currency") or "-"),
       "pending": "\n".join("- [%s] %s → %s" % ("阻断" if p.get("blocking") else "确认", p["item"], p["action"]) for p in D["pending"]) or "- 无"}
  return re.sub(r"\{\{(\w+)\}\}", lambda m: str(d.get(m.group(1), "")), T)

def run(a):
  t0 = time.monotonic()
  out = Path(a.output)
  out.mkdir(parents=True, exist_ok=True)
  ctx = {"errors": [], "degradations": [], "changes": [], "sources": [], "texts": {}}
  cid, cf = None, []
  try:
    d = Path(a.input)
    if not d.is_dir():
      d = next((p for p in (Path.cwd() / "input", Path("/input")) if p.is_dir()), d)
    recs = disc(d, ctx)
    case, crel = lcase(d, ctx)
    cid = next((x for x in (case.get("case_id"), case.get("caseId"), case.get("id")) if isinstance(x, (str, int))), None)
    cf = clist(fcon(case, d, ctx)[0])
    wj(out / "result.json", dict({"case_id": cid, "status": "partial", "sources": [], "uncertainty": [], "pending_human": [],
                                  "errors": [], "degradations": [], "changes": [], "runtime": {"started": iso()}}, **backfill(cf, {})[0]))
    ctx["changes"].append({"at": iso(), "change": "partial first: contract keys placeheld"})
    R, E, M, P = collect(case, ctx, crel)
    mods = models(case, ctx, R)
    goal = next((v.strip() for v in (pick(case, (k,)) for k in ("goal", "objective", "aim", "研究目标", "目标", "question"))
                 if isinstance(v, str) and v.strip()), "") or next(
        (" ".join(t.split())[:280] for r, t in ctx["texts"].items() if r.lower().endswith((".md", ".txt")) and len(t) > 40), "")
    budget = next((num(v) for p, v in walk(case) if re.search(r"budget|预算|经费", p, re.I) and not isinstance(v, bool) and num(v) is not None), None)
    cur = next((("CNY" if re.search(r"CNY|RMB|元|¥", m["price_raw"]) else "USD") for m in M
                if m.get("price_raw") and re.search(r"CNY|RMB|元|¥|USD", m["price_raw"])), "")
    L, cons, F = feas(R)
    S = srch(R, L, F, mods, M, a, t0)
    rc, bp = S["rc"], (S["best"] or {}).get("pt") or {}
    parameters = []
    for k in sorted(R):
      e = R[k]
      lo, hi, bl, bh = eff(e)
      rec = bp.get(k, F.get(k, e["fixed"]))
      if rec is None and lo is not None and hi is not None:
        rec = (lo + hi) / 2
      parameters.append({"name": e["name"], "canon": k, "unit": e["unit"], "recommended": rnd(rec), "lower": rnd(lo),
                         "upper": rnd(hi), "step": e["step"], "binding": (bh or bl or {}).get("kind"),
                         "basis": [{"source_id": b["source_id"], "quote": next((s["quote"] for s in ctx["sources"]
                                                                              if s["source_id"] == b["source_id"]), "")} for b in (bl, bh) if b]})
    runs = max(1, len(L)) * (3 if mods else 1)
    schedule = {"runs": runs, "cost_per_run": rc["subtotal"], "budget": budget,
                "within_budget": None if (rc["subtotal"] is None or not budget) else bool(rc["subtotal"] * runs <= budget)}
    steps = ["核对参数表单位与量程。",
             "按建议值配制：" + ("; ".join("%s=%s%s" % (p["name"], ft(p["recommended"]), p["unit"] or "") for p in parameters
                                          if p["recommended"] is not None) or "参数待补") + "。",
             "运行并记录设定/实测值（" + (", ".join(e["name"] for e in E) or "设备待补") + "），每点3次按第7节比较。"]
    validation = {"criteria": [{"metric": m["metric"], "criterion": "%s: 实测∈预测±2σ（σ=%s, R²=%s）" % (m["param"], ft(m["sigma"]), ft(m["r2"])),
                                "method": "3批均值±极差"} for m in mods] or
                  [{"metric": "响应指标", "criterion": "重复偏差≤10%",
                    "method": "重复3次报均值±极差"}],
                  "gold_standard": "无独立参比",
                  "stop": ["2批≤max(2σ,精度)→接受", "越约束→停机复核",
                           "预算/机时90%→停"]}
    lim = next(((e["name"], bh or bl) for e in R.values() for lo, hi, bl, bh in [eff(e)]
                if (bh or bl) and lo is not None and hi is not None and hi > lo
                and (bh or bl)["kind"] in ("equipment_limit", "material_limit", "safety_limit")), None)
    r2 = []
    if lim:
      bd = lim[1]
      r2.append(["%s近限值%s" % (lim[0], ft(bd["hi"] if bd["hi"] is not None else bd["lo"])), "%s越界" % lim[0], bd["source_id"],
                 "回退区间", "换设备"])
    if rc["subtotal"] and budget and runs and rc["subtotal"] * runs > budget:
      r2.append(["超预算%s>%s" % (ft(rc["subtotal"] * runs), ft(budget)), "单批超预算", None, "减批次", "追加预算"])
    if rc["unknown"] or not mods:
      r2.append(["成本缺口", "缺报价/数据", None, "按成本", "补报价"])
    if mods:
      r2.append(["改善<批间波动", "最优-次优", None, "按均值", "加密重复"])
    risks = [{"risk": n, "likelihood": "high", "impact": "high", "trigger": t, "detection": "逐批",
              "contingency": c, "alternative": a, "owner": "执行人",
              "source_id": sid} for n, t, sid, c, a in r2]
    pending = [{"item": "约束冲突:%s 下限%s>上限%s" % (c["name"], ft(c["lower"]), ft(c["upper"])),
                "blocking": True, "action": "放宽受限侧或换料"} for c in cons]
    if not mods:
      pending.append({"item": "无响应数据/成本缺口", "blocking": False, "action": "补预实验与报价"})
    if E:
      pending.append({"item": "设备/机时待确认", "blocking": False,
                      "action": ", ".join(x["name"] for x in E[:3]) + " 待确认"})
    if re.search(r"人|动物|细胞|临床|受试|patient|serum", goal, re.I):
      pending.append({"item": "涉人体/动物需伦理审批", "blocking": True, "action": "批件前禁执行"})
    nm2k = {e["name"]: k for k, e in R.items()}
    comparison = []
    for pl in P:
      v = {n: num(pick(pl["record"], (n, k))) for n, k in nm2k.items()}
      v = {n: x for n, x in v.items() if x is not None}
      ok = all((eff(R[nm2k[n]])[0] is None or x >= eff(R[nm2k[n]])[0] - 1e-9)
               and (eff(R[nm2k[n]])[1] is None or x <= eff(R[nm2k[n]])[1] + 1e-9) for n, x in v.items())
      comparison.append({"plan": str(pick(pl["record"], ("plan_id", "id", "name")) or pl["ptr"]), "params": v,
                         "feasible": bool(v) and ok,
                         "verdict": "feasible" if (v and ok) else ("infeasible" if v else "unparsed")})
    status = "insufficient_evidence" if not R else ("partial" if (cons or rc["subtotal"] is None or not mods) else "ok")
    if not case:
      status = "input_error"
    metrics, search, materials, equipment = S["metrics"], S["rounds"], M, E
    hypotheses = [{"id": "H1", "statement": "改变 %s 影响 %s" % ("/".join([p["name"] for p in parameters][:3]) or "关键参数",
                                                               "/".join(metrics[:3]) or "响应指标"),
                   "test": "±一步长各2批", "falsifier": "实测稳定越出预测区间"},
                  {"id": "H2", "statement": "建议点满足设备/材料/安全约束", "test": "逐行核对 binding", "falsifier": "任一参数越界"}]
    if cons:
      hypotheses.append({"id": "H3", "statement": "约束交集非空（当前为假）", "test": "复核冲突两侧", "falsifier": "冲突不复现"})
    variables = {"iv": [p["name"] for p in parameters if p["recommended"] is not None][:8], "dv": metrics,
                 "control": ["基线批次（输入原方案参数）", "同参数重复批次（3次，设计默认）"],
                 }
    feasibility = {"feasible": not cons and bool(parameters), "conflicts": cons,
                   "domain_sizes": {k: len(v) for k, v in L.items()}, "evaluated": len(S["pool"])}
    summary = {"goal": goal[:80], "recommended": ["%s=%s%s" % (p["name"], ft(p["recommended"]), p["unit"] or "") for p in parameters if p["recommended"] is not None],
               "cost_per_run": rc["subtotal"], "confidence": "high" if (mods and not cons) else ("medium" if mods else "low")}
    D = {k: locals()[k] for k in KEYS}
    D.update({"case_id": cid, "status": status, "cost": dict(schedule, currency=cur),
              "plan": {"protocol_md": "protocol.md", "steps": len(steps)},
              "response_model": [{k: m[k] for k in ("metric", "param", "coef", "deg", "r2", "sigma", "n", "ok")} for m in mods]})
    arts = []
    for name, purpose, rows in (
        ("protocol.md", "可执行实验方案（主产物）", None),
        ("parameter_plan.csv", "参数建议表",
         [{"parameter": x["name"], "unit": x["unit"], "recommended": ft(x["recommended"]), "lower": ft(x["lower"]),
           "upper": ft(x["upper"]), "binding": x["binding"] or "", "basis_ids": [b["source_id"] for b in x["basis"]]} for x in parameters]),
        ("risk_table.csv", "风险", [dict(r, risk_id="R%02d" % (i + 1)) for i, r in enumerate(risks)])):
      try:
        p = out / name
        p.write_text(proto(D), encoding="utf-8") if rows is None else wcsv(p, rows)
        arts.append({"path": str(p), "bytes": p.stat().st_size, "purpose": purpose})
      except Exception as e:
        ctx["errors"].append("%s: %s" % (name, e))
    fill, used = backfill(cf, dict(D, sources=ctx["sources"]))
    res = dict(D)
    res.update({"artifacts": arts, "sources": ctx["sources"], "pending_human": pending, "errors": ctx["errors"],
                "degradations": ctx["degradations"], "changes": ctx["changes"], "input_files": [r["path"] for r in recs],
                "uncertainty": [{"item": "响应-参数关系", "level": "high" if not mods else "medium",
                                 "reason": "无历史数据，建议值为可行域内设计选择" if not mods else "基于 %d 个数据点的线性拟合" % sum(m["n"] for m in mods),
                                 "how_to_reduce": "补≥5点预实验重跑"}],
                "runtime": {"started_utc": iso(), "seconds": rnd(time.monotonic() - t0), "budget_s": a.time_budget}})
    res["contract_backfill"] = used
    for k, v in fill.items():
      if res.get(k) in (None, "", [], {}): res[k] = v
    wj(out / "result.json", res)
    print("[ok]", status, len(parameters), len(cons))
    return 0
  except Exception as e:
    import traceback
    ctx["errors"].append("fatal: %s: %s" % (type(e).__name__, e))
    ctx["degradations"].append(traceback.format_exc()[-500:])
    try:
      wj(out / "result.json", dict({"case_id": cid, "status": "partial", "errors": ctx["errors"],
                                    "degradations": ctx["degradations"]}, **backfill(cf, {})[0]))
    except Exception:
      pass
    return 0

def main(argv=None):
  ap = argparse.ArgumentParser(prog="main.py", description="experiment-03 参数优化")
  ap.add_argument("--input", "-i", default="/input", help="输入")
  ap.add_argument("--output", "-o", default="/app/output", help="输出")
  a = ap.parse_args(argv)
  a.max_candidates, a.time_budget = 600, 780.0
  try:
    return run(a)
  except Exception:
    return 0

if __name__ == "__main__":
  try:
    main()
  except SystemExit:
    pass
  except Exception:
    pass
  raise SystemExit(0)
