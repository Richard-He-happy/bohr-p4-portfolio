#!/usr/bin/env python3
"""plan-compare: put candidate experimental plans on one comparable matrix.

Reads /input/case.json (+ task.md), normalises every candidate plan onto the
same seven fields, does the cost/time arithmetic, applies hard feasibility
gates, ranks with a weight-sensitivity sweep, and writes result.json (all
output_contract fields echoed), comparison_matrix.csv and decision_record.md.
Exit code is always 0.
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fields as fx          # noqa: E402
import planmodel as pm       # noqa: E402
import scoring as sc         # noqa: E402
from report import money, render_md, write_csv  # noqa: E402

VERSION = "1.0.0"
T0 = time.time()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def resolve_case(indir, explicit):
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for name in ("case.json", "input.json", "case_data.json"):
        if (indir / name).exists():
            return indir / name
    for p in sorted(indir.rglob("case*.json")):
        return p
    return None


def list_inputs(indir):
    return [p for p in sorted(indir.rglob("*")) if p.is_file()] if indir.exists() else []


def load_case(path, res):
    if not path:
        res["errors"].append({"stage": "read_case", "error": "未找到 case.json"})
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        res["errors"].append({"stage": "read_case", "file": str(path), "error": repr(e)[:300]})
        return {}


def find_contract(case):
    if isinstance(case, dict):
        for k, v in case.items():
            if pm.has(k, "output") and pm.has(k, "contract"):
                return v
    return None


def analyse(case, casepath, res, outdir):
    contracted = res["output_contract_fields"]
    pptr, plans = pm.find_plans(case) if isinstance(case, dict) else (None, None)
    contract = pm.collect_contract(case if isinstance(case, dict) else {})
    limits = pm.collect_limits(case) if isinstance(case, dict) else {}
    if not plans:
        res["status"] = "insufficient_evidence" if case else "partial"
        res["status_reason"] = ("输入中未找到候选方案集合" if case else
                                "未读到可解析的 case.json，仅产出契约骨架与缺口说明")
        res["uncertainty"].append({"item": "candidate_plans", "why": "未出现可识别的方案列表",
                                   "impact": "无法产出比较矩阵与选择结论"})
        res["pending_human"].append({"item": "候选方案清单",
                                     "action": "确认 case 是否包含 plans/candidates 列表",
                                     "owner": "case owner"})
        return

    metrics = pm.build_metrics(plans, pptr, contract)
    gates = {m["id"]: sc.gate_rows(m, contract, limits) for m in metrics}
    cost_of = {m["id"]: (m["cost"]["total_cost"] or 1e18) for m in metrics}
    base = sc.scores_for(metrics, gates, pm.W_DEFAULT)
    order = sc.rank(metrics, base, cost_of)
    sens = fx.sensitivity_block(metrics, gates, cost_of, order[0] if order else None)
    feasible = [i for i in order if not base[i]["infeasible"]]
    sel = feasible[0] if feasible else None

    elim, unc, pend, asm = [], [], [], []
    for m in metrics:
        fails = sc.hard_fail(gates[m["id"]])
        if m["id"] == sel:
            continue
        if fails:
            reasons = ["%s: 取值 %s 超上限 %s（超出 %s）" %
                       (r["gate"], r.get("value"), r.get("limit"), r.get("over_by")) for r in fails]
            item = {"plan": m["id"], "kind": "hard_gate", "reasons": reasons, "gates": fails}
            b, c = contract.get("budget"), m["cost"]["total_cost"]
            if b and c and c > b:
                per = (m["cost"]["per_run_cost"] or 0.0) + (m["cost"]["machine_cost"] or 0.0) \
                    + (m["cost"]["labor_cost"] or 0.0)
                fits = int((b - m["cost"]["fixed_cost"]) // per) if per > 0 else 0
                item["remediation"] = {"over_budget": round(c - b, 2),
                                       "per_run": round(per, 2),
                                       "min_runs_to_fit": max(fits, 0),
                                       "note": "或追加预算 %s，或把重复次数降到 %s" %
                                               (money(round(c - b, 2), m["cost"]["currency"]), max(fits, 0))}
            elim.append(item)
        else:
            gap = sc.dominant_gap(base[sel], base[m["id"]]) if sel else None
            parts, sm = [], next((x for x in metrics if x["id"] == sel), None)
            if sm:
                c2, c1 = m["cost"]["total_cost"], sm["cost"]["total_cost"]
                if c1 and c2:
                    parts.append("成本 %s vs %s（%+.1f%%）" %
                                 (money(c2), money(c1), (c2 - c1) / c1 * 100.0))
                t2, t1 = m["time"]["total_days"], sm["time"]["total_days"]
                if t1 and t2:
                    parts.append("周期 %s vs %s 天" % (t2, t1))
                parts.append("风险罚分 %s vs %s" %
                             (base[m["id"]]["components"]["risk_penalty_used"],
                              base[sel]["components"]["risk_penalty_used"]))
                if not m.get("risk_declared"):
                    parts.append("（%s 未声明风险，按中性罚分计）" % m["id"])
                parts.append("字段完整度 %.2f vs %.2f" % (m["completeness"], sm["completeness"]))
            elim.append({"plan": m["id"], "kind": "scored", "score": base[m["id"]]["total"],
                         "score_gap": round(base[sel]["total"] - base[m["id"]]["total"], 4) if sel else None,
                         "dominant_gap": gap, "comparison": parts,
                         "reason": "低于 %s：%s；主因 %s" %
                                   (sel, "；".join(parts), gap["criterion"] if gap else "无显著差异")})

    for m in metrics:
        if m["fields_missing"]:
            unc.append({"item": "%s 缺字段" % m["id"],
                        "why": "未找到：" + ", ".join(m["fields_missing"]),
                        "impact": "该方案不能直接交付执行，需补齐后再比较"})
        if m["cost"]["missing"]:
            unc.append({"item": "%s 成本缺口" % m["id"], "why": "；".join(m["cost"]["missing"]),
                        "impact": "成本合计为下界，排名可能变化"})
        if m["time"]["days_basis"].startswith("derived"):
            asm.append({"item": "%s 周期折算" % m["id"],
                        "assumption": "总工时按 8 h/工作日折天",
                        "locator": "%s#%s" % (casepath.name, m["pointer"]) if casepath else None})
        if not m.get("risk_declared"):
            unc.append({"item": "%s 风险未声明" % m["id"],
                        "why": "方案未列风险条目，不能据此认定低风险",
                        "impact": "按已声明方案罚分中位数 %s 中性计入，需专家补评" %
                                  base[m["id"]]["components"]["risk_penalty_used"]})
        dc = m["cost"]["declared_check"]
        if dc.get("status") == "mismatch":
            unc.append({"item": "%s 自报成本不符" % m["id"],
                        "why": "declared=%s computed=%s Δ=%s%%" %
                               (dc["declared"], dc.get("computed"), dc.get("delta_pct")),
                        "impact": "以逐项核算为准，需与方案作者核对"})
    for k, label in (("machine_rate", "机时费率"), ("labor_rate", "人工费率"),
                     ("available_hours", "可预约机时"), ("budget", "预算上限")):
        if contract.get(k) is None:
            unc.append({"item": "契约缺 %s" % label, "why": "输入中未找到对应数值",
                        "impact": "相关成本或硬门降级为未判定"})
    pend += [{"item": "安全与合规审批",
              "action": "确认危化品/生物/辐射等审批覆盖所选方案条件", "owner": "安全负责人"},
             {"item": "设备与耗材可得",
              "action": "确认机时预约与货期落在截止周期内", "owner": "平台管理员"}]
    if sel:
        pend.append({"item": "判读阈值冻结",
                     "action": "开跑前冻结 %s 的接受阈值并留档" % sel, "owner": "课题负责人"})

    ev = fx.build_evidence(casepath.name if casepath else "case.json", metrics, contract, limits)
    matrix, pid = fx.build_matrix(metrics, gates)
    empty_core = [m["id"] for m in metrics if not m["fields_covered"]]
    status = "ok"
    if empty_core or any(m["fields_missing"] or m["cost"]["missing"] or
                         m["time"]["total_hours"] is None for m in metrics):
        status = "partial"
    if sel is None:
        status = "partial"

    res.update({
        "status": status,
        "status_reason": None if status == "ok" else (
            "所有候选方案均触发硬门失败，未给出可执行选择" if sel is None else "部分字段或成本输入缺失"),
        "task": {"instruction": (case.get("task_instruction") or case.get("instruction") or "")[:1200],
                 "plans_found": len(metrics), "plans_pointer": pptr},
        "comparison_basis": {"fields": [r[0] for r in pm.REQ],
                             "cost_formula": metrics[0]["cost"]["formula"],
                             "weights": pm.W_DEFAULT,
                             "units": {"cost": contract.get("currency") or "CNY",
                                       "time": "day", "machine": "h"},
                             "elimination_rule": "任一硬门 fail 即淘汰；其余按加权总分排序，同分取成本低者"},
        "candidate_plans": metrics,
        "comparison_matrix": matrix,
        "plan_order": pid,
        "cost_model": {"plans": {m["id"]: m["cost"] for m in metrics},
                       "currency": contract.get("currency") or "CNY",
                       "contract": {k: contract.get(k) for k in
                                    ("budget", "machine_rate", "labor_rate",
                                     "available_hours", "deadline_days")},
                       "contract_locators": contract.get("locator", {})},
        "time_model": {"plans": {m["id"]: m["time"] for m in metrics}},
        "feasibility_gates": [r for m in metrics for r in gates[m["id"]]],
        "risk_register": [dict(it, plan=m["id"]) for m in metrics for it in m["risk_items"]],
        "scoring": {"weights": pm.W_DEFAULT, "per_plan": base,
                    "components_meaning": {
                        "completeness": "七字段覆盖比例",
                        "feasibility": "已判定硬门通过率",
                        "cost": "可行集最低成本 / 本方案成本",
                        "time": "可行集最短周期 / 本方案周期",
                        "risk": "1 - 罚分/(罚分+2)，罚分按风险等级加权"}},
        "choice": {"selected": sel, "score": base[sel]["total"] if sel else None,
                   "rank": order, "runner_up": feasible[1] if len(feasible) > 1 else None,
                   "margin": round(base[feasible[0]]["total"] - base[feasible[1]]["total"], 4)
                   if len(feasible) > 1 else None,
                   "confidence": "high" if sel and (sens["stability"] or 0) >= 0.999 else
                                 ("medium" if sel and (sens["stability"] or 0) >= 0.6 else "low"),
                   "confidence_basis": "5 组权重一致率 %.0f%%；%s 已判定硬门 %d 项" %
                                       (100 * (sens["stability"] or 0), sel or "-",
                                        sum(1 for r in gates[sel] if r["status"] != "unknown") if sel else 0)},
        "eliminations": elim,
        "sensitivity": sens,
        "assumptions": asm,
        "uncertainty": unc + (res.get("uncertainty") or []),
        "pending_human": pend,
        "evidence": ev,
        "parameter_table": [{"plan": m["id"], "params": m["params"]} for m in metrics],
        "changes": (res.get("changes") or []) + [
            {"v": 2, "what": "字段归一、成本/时间核算、硬门与敏感性"},
            {"v": 3, "what": "生成 comparison_matrix.csv / decision_record.md 并 finalize"}],
    })
    if sel is None:
        res["pending_human"].append({"item": "全方案不可行",
                                     "action": "放宽预算/周期或增加机时后重跑，或降低重复次数",
                                     "owner": "课题负责人"})

    for n in contracted:
        key, val = fx.fill_field(n, res)
        res[n] = val
        res["output_contract_map"][n] = key

    write_csv(outdir / "comparison_matrix.csv", matrix, pid)
    (outdir / "decision_record.md").write_text(render_md(res), encoding="utf-8")
    res["artifacts"] = ["result.json", "comparison_matrix.csv", "decision_record.md"]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="plan-compare",
        description=("把候选实验方案放到同一张可比矩阵：统一七字段 -> 成本/时间核算 -> "
                     "硬门可行性 -> 加权排序与权重敏感性 -> 选择与舍弃理由 -> 证据定位 -> "
                     "回填 output_contract 全部字段。"),
        epilog=("示例：python3 -B main.py --input /input --output /app/output"
                "（示例调用，非正式案例结果）。退出码恒为 0，状态见 result.json.status。"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="/input", help="输入目录，默认 /input")
    ap.add_argument("--output", default="/app/output", help="输出目录，默认 /app/output")
    ap.add_argument("--case", default=None, help="case.json 路径，默认在 --input 下自动发现")
    ap.add_argument("--version", action="version", version="plan-compare %s" % VERSION)
    a = ap.parse_args(argv)

    indir, outdir = Path(a.input), Path(a.output)
    outdir.mkdir(parents=True, exist_ok=True)
    res = {"case_id": None, "status": "partial", "status_reason": "分析尚未完成",
           "sources": [], "artifacts": [], "uncertainty": [], "pending_human": [], "errors": [],
           "degradations": [], "changes": [], "runtime": {}}
    dump(outdir / "result.json", {"status": "partial", "status_reason": "running"})

    try:
        casepath = resolve_case(indir, a.case)
        files = list_inputs(indir)
        res["sources"] = [{"id": "S%d" % (i + 1), "path": str(p),
                           "type": p.suffix.lower() or "none", "bytes": p.stat().st_size}
                          for i, p in enumerate(files)]
        case = load_case(casepath, res)
        names = fx.contract_fields(find_contract(case) if case else None)
        res["output_contract_fields"] = names
        res["output_contract_map"] = {}
        for n in names:
            res[n] = None
        res["case_id"] = (case.get("case_id") or case.get("id")) if isinstance(case, dict) else None
        res["case_id"] = res["case_id"] or (casepath.stem if casepath else None)
        res["changes"].append({"v": 1, "what": "读取 %s，登记 %d 个输入文件" %
                               (casepath.name if casepath else "无", len(files))})
        dump(outdir / "result.json", res)          # partial with contract skeleton

        analyse(case, casepath, res, outdir)
    except Exception as e:
        res["errors"].append({"stage": "main", "error": repr(e)[:300],
                              "trace": traceback.format_exc()[-600:]})
        res["status"] = "partial"
        res["status_reason"] = "流程异常，保留已完成部分"
    finally:
        for n in res.get("output_contract_fields") or []:
            res.setdefault(n, None)
        res["runtime"] = {"version": VERSION, "elapsed_s": round(time.time() - T0, 3),
                          "python": sys.version.split()[0], "argv": sys.argv[1:]}
        dump(outdir / "result.json", res)
        try:
            import verify
            res["self_check"] = verify.check(outdir, indir)
            dump(outdir / "result.json", res)
        except Exception as e:
            res["degradations"].append({"what": "self_check", "why": repr(e)[:200]})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
