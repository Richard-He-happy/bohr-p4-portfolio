#!/usr/bin/env python3
"""Rendered decision record (markdown) and matrix export (CSV)."""

import csv


def money(x, cur="CNY"):
    if x is None:
        return "n/a"
    s = "{:,.2f}".format(x) if abs(x - round(x)) > 1e-9 else "{:,.0f}".format(x)
    return "%s %s" % (cur, s)


def pct(x):
    return "n/a" if x is None else "%.1f%%" % x


def write_csv(path, rows, pid):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["criterion", "unit", "better"] + pid)
        for r in rows:
            w.writerow([r["criterion"], r["unit"], r["better"]] +
                       [r["values"].get(p) for p in pid])


def render_md(res):
    L = []
    ch = res.get("choice") or {}
    cur = (res.get("cost_model") or {}).get("currency") or "CNY"
    pid = res.get("plan_order") or []
    L.append("# 实验方案比较与选择记录（案例 %s）\n" % res.get("case_id"))
    L.append("- 状态：`%s`%s" % (res.get("status"),
                                ("（%s）" % res["status_reason"]) if res.get("status_reason") else ""))
    L.append("- 选择结论：**%s**%s" % (ch.get("selected") or "无（全部不可行）",
                                      ("，领先第二名 %.3f 分" % ch["margin"])
                                      if ch.get("margin") is not None else ""))
    L.append("- 置信度：%s（%s）\n" % (ch.get("confidence"), ch.get("confidence_basis")))

    L.append("## 1. 统一比较口径\n")
    L.append("七类必填字段：假设、变量、对照、步骤、参数、资源、判读标准。")
    L.append("成本口径：`total = 重复次数×Σ(数量×单价) + 一次性投入 + 机时×机时费率 + 人工工时×人工费率`（机时/人工为全程总量，不随重复次数翻倍）。")
    L.append("淘汰规则：任一硬门 fail 直接淘汰；其余按加权总分排序，同分取成本低者。\n")

    L.append("## 2. 候选方案矩阵\n")
    L.append("| 指标 | 单位 | 更优 | " + " | ".join(pid) + " |")
    L.append("|---|---|---|" + "---|" * len(pid))
    for r in res.get("comparison_matrix") or []:
        L.append("| %s | %s | %s | %s |" % (r["criterion"], r["unit"], r["better"],
                                            " | ".join(str(r["values"].get(p)) for p in pid)))
    L.append("")

    L.append("## 3. 成本核算\n")
    for p, c in (res.get("cost_model") or {}).get("plans", {}).items():
        L.append("**%s**：每轮耗材 %s；一次性 %s；机时 %s h × %s → %s；人工 %s h × %s → %s；"
                 "重复 %s 次；**合计 %s**。缺项：%s"
                 % (p, money(c["per_run_cost"], cur), money(c["fixed_cost"], cur),
                    c["machine_hours"], money(c["machine_rate"], cur), money(c["machine_cost"], cur),
                    c["labor_hours"], money(c["labor_rate"], cur), money(c["labor_cost"], cur),
                    c["runs"], money(c["total_cost"], cur),
                    "、".join(c["missing"]) or "无"))
        if c["declared_check"].get("status") != "not_declared":
            L.append("自报成本核对：declared=%s computed=%s → %s"
                     % (c["declared_check"]["declared"],
                        c["declared_check"].get("computed"),
                        c["declared_check"]["status"]))
        L.append("")

    L.append("## 4. 可行性硬门\n")
    L.append("| 方案 | 门 | 状态 | 取值 | 上限 | 超出 |")
    L.append("|---|---|---|---|---|---|")
    for g in res.get("feasibility_gates") or []:
        L.append("| %s | %s | %s | %s | %s | %s |" %
                 (g["plan"], g["gate"], g["status"], g.get("value"),
                  g.get("limit"), g.get("over_by")))
    L.append("")

    L.append("## 5. 选择与舍弃理由\n")
    if ch.get("selected"):
        L.append("选择 **%s**：总分 %.3f。分量：%s\n" %
                 (ch["selected"], ch.get("score") or 0,
                  "，".join("%s=%.3f" % (k, v) for k, v in
                            sorted(((res.get("scoring") or {}).get("per_plan", {})
                                    .get(ch["selected"], {}).get("components") or {}).items()))))
    for e in res.get("eliminations") or []:
        if e["kind"] == "hard_gate":
            L.append("- **%s 舍弃**：硬门失败（%s）" % (e["plan"], "；".join(e["reasons"])))
            if e.get("remediation"):
                L.append("  回退：需削减 %s，或在 %s 轮内完成"
                         % (money(e["remediation"]["over_budget"], cur),
                            e["remediation"]["min_runs_to_fit"]))
        else:
            L.append("- **%s 未选**：%s（总分 %.3f，差 %.3f）"
                     % (e["plan"], e["reason"], e.get("score") or 0, e.get("score_gap") or 0))
    L.append("")

    L.append("## 6. 权重敏感性\n")
    sn = res.get("sensitivity") or {}
    L.append("5 组权重下结论一致率 %s；翻转方案：%s。\n"
             % (pct(100 * sn["stability"] if sn.get("stability") is not None else None),
                "、".join(sn.get("flip") or []) or "无"))

    L.append("## 7. 证据与定位（节选）\n")
    L.append("| 编号 | 主张 | 定位 | 逐字引用 |")
    L.append("|---|---|---|---|")
    for e in (res.get("evidence") or [])[:25]:
        L.append("| %s | %s | `%s` | `%s` |" % (e["id"], e["claim"], e["locator"], e["quote"]))
    L.append("")

    L.append("## 8. 不确定性与待人工确认\n")
    for u in res.get("uncertainty") or []:
        L.append("- %s：%s → %s" % (u.get("item"), u.get("why"), u.get("impact")))
    for p in res.get("pending_human") or []:
        L.append("- [待确认] %s → %s（%s）" % (p.get("item"), p.get("action"), p.get("owner")))
    L.append("")
    L.append("> 本文件由脚本按输入自动生成，不含预制答案；数值均来自输入文件并可回溯到 locator。")
    return "\n".join(L)
