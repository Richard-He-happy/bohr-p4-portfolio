#!/usr/bin/env python3
"""Comparable-field plumbing: matrix, evidence, output_contract backfill.

Standard library only. Imported by scripts/main.py.
"""

import planmodel as pm
import scoring as sc

# output_contract field name -> result key (first token match wins).
FIELD_MAP = [
    (("matrix", "compar", "table", "矩阵", "对比"), "comparison_matrix"),
    (("eliminat", "reject", "exclude", "淘汰", "舍弃", "排除"), "eliminations"),
    (("choice", "select", "recommend", "decision", "ranking", "pick",
      "选择", "推荐", "结论"), "choice"),
    (("cost", "budget", "price", "成本", "预算", "费用"), "cost_model"),
    (("time", "schedule", "timeline", "duration", "周期", "排期", "时间"), "time_model"),
    (("feasib", "gate", "availab", "可行", "资源", "门"), "feasibility_gates"),
    (("risk", "safety", "hazard", "exception", "风险", "安全", "异常"), "risk_register"),
    (("sensitiv", "stabil", "robust", "敏感", "稳健"), "sensitivity"),
    (("evidence", "locator", "citation", "quote", "证据", "定位", "引用"), "evidence"),
    (("uncertain", "limitation", "gap", "不确定", "局限", "缺口"), "uncertainty"),
    (("pending", "human", "confirm", "approval", "待确认", "人工"), "pending_human"),
    (("param", "domain", "window", "参数", "窗口", "区间"), "parameter_table"),
    (("score", "rubric", "grade", "评分", "打分"), "scoring"),
    (("assumption", "假设", "前提"), "assumptions"),
    (("change", "revision", "变更"), "changes"),
    (("error", "错误"), "errors"),
    (("plan", "design", "protocol", "方案", "步骤"), "candidate_plans"),
    (("status", "状态"), "status"),
    (("caseid",), "case_id"),
    (("runtime", "elapsed", "运行"), "runtime"),
    (("source", "来源文件"), "sources"),
]


def contract_fields(oc):
    """Field names declared by output_contract, whatever its shape."""
    names = []

    def add(x):
        if isinstance(x, str) and x.strip() and x.strip() not in names:
            names.append(x.strip())

    def add_spec(v):
        if isinstance(v, dict):
            for kk in v:
                add(kk)
        elif isinstance(v, list):
            for y in v:
                if isinstance(y, str):
                    add(y)
                elif isinstance(y, dict):
                    add(y.get("name") or y.get("field") or y.get("key"))

    if isinstance(oc, dict):
        nested = False
        for k, v in oc.items():
            if pm.has(k, "fields", "properties", "required", "columns", "keys") and isinstance(v, (dict, list)):
                add_spec(v)
                nested = True
        if not nested:
            for k in oc:
                add(k)
    elif isinstance(oc, list):
        add_spec(oc)
    return names


def fill_field(name, res):
    """(result key, value) chosen for a contracted field; (None, None) if unmapped."""
    n = pm.norm(name)
    for toks, key in FIELD_MAP:
        if any(t in n for t in toks):
            return key, res.get(key)
    return None, None


def build_matrix(metrics, rows_by_plan):
    rows = []
    pid = [m["id"] for m in metrics]

    def row(label, unit, better, get):
        vals = {}
        for m in metrics:
            try:
                vals[m["id"]] = get(m)
            except Exception:
                vals[m["id"]] = None
        rows.append({"criterion": label, "unit": unit, "better": better, "values": vals})

    for fname in [r[0] for r in pm.REQ]:
        row("字段:%s" % fname, "present/absent", "present",
            lambda m, f=fname: "present" if m["fields"].get(f) else "absent")
    row("字段完整度", "0-1", "higher", lambda m: m["completeness"])
    row("耗材/采购（每轮）", "money", "lower", lambda m: m["cost"]["per_run_cost"])
    row("一次性投入", "money", "lower", lambda m: m["cost"]["fixed_cost"])
    row("机时", "h", "lower", lambda m: m["cost"]["machine_hours"])
    row("机时费", "money", "lower", lambda m: m["cost"]["machine_cost"])
    row("人工工时", "h", "lower", lambda m: m["cost"]["labor_hours"])
    row("人工费", "money", "lower", lambda m: m["cost"]["labor_cost"])
    row("成本合计", "money", "lower", lambda m: m["cost"]["total_cost"])
    row("总周期", "day", "lower", lambda m: m["time"]["total_days"])
    row("风险声明", "present/absent", "present",
        lambda m: "present" if m.get("risk_declared") else "absent")
    row("风险条目", "count", "lower", lambda m: len(m["risk_items"]))
    row("风险罚分", "score", "lower", lambda m: m["risk_penalty"])
    row("硬门通过数", "count", "higher",
        lambda m: sum(1 for r in rows_by_plan[m["id"]] if r["status"] == "pass"))
    row("硬门失败数", "count", "lower",
        lambda m: sum(1 for r in rows_by_plan[m["id"]] if r["status"] == "fail"))
    row("硬门未判定数", "count", "lower",
        lambda m: sum(1 for r in rows_by_plan[m["id"]] if r["status"] == "unknown"))
    return rows, pid


def build_evidence(case_name, metrics, contract, limits, cap=90):
    ev = []

    def add(claim, value, locator, kind="measured"):
        if len(ev) >= cap or not locator:
            return
        ev.append({"id": "E%02d" % (len(ev) + 1), "claim": claim, "value": value,
                   "source": case_name,
                   "locator": "%s#%s" % (case_name, locator),
                   "quote": pm.qnum(value) if isinstance(value, (int, float)) else str(value)[:80],
                   "kind": kind})

    for key, label in (("budget", "预算上限"), ("machine_rate", "机时费率"),
                       ("labor_rate", "人工费率"), ("available_hours", "可预约机时"),
                       ("deadline_days", "截止周期(天)")):
        v = contract.get(key)
        if v is not None:
            add("组织方契约：%s" % label, v, contract["locator"].get(key))
    for m in metrics:
        c = m["cost"]
        for ln in c["lines"][:6]:
            add("%s 采购项「%s」单价" % (m["id"], ln["label"]), ln["unit_price"], ln["locator"])
        if c["machine_hours"] is not None:
            add("%s 机时" % m["id"], c["machine_hours"], c.get("machine_locator") or m["pointer"], "pointer")
        if c["labor_hours"] is not None:
            add("%s 人工工时" % m["id"], c["labor_hours"], c.get("labor_locator") or m["pointer"], "pointer")
        if c["declared_check"].get("declared") is not None:
            add("%s 方案自报总成本" % m["id"], c["declared_check"]["declared"], m["pointer"], "pointer")
        for f, loc in m["fields"].items():
            if loc:
                add("%s 字段 %s" % (m["id"], f), loc.rsplit("/", 1)[-1], loc, "pointer")
        for it in m["risk_items"][:3]:
            add("%s 风险" % m["id"], it["text"][:60], it["locator"], "narrative")
    for ln, lim in list((limits or {}).items())[:8]:
        add("参数窗口 %s=[%s,%s]" % (lim["name"], lim["min"], lim["max"]), lim["name"],
            lim["locator"], "limit")
    return ev


def sensitivity_block(metrics, rows_by_plan, cost_of, base):
    runs, winners = [], []
    for name, w in pm.W_SETS.items():
        s = sc.scores_for(metrics, rows_by_plan, w)
        r = sc.rank(metrics, s, cost_of)
        winners.append(r[0] if r else None)
        runs.append({"weight_set": name, "weights": w, "order": r,
                     "winner": r[0] if r else None,
                     "top_score": round(s[r[0]]["total"], 4) if r else None})
    stable = sum(1 for x in winners if x == base)
    return {"runs": runs, "base_winner": base, "agreement": stable,
            "sets": len(winners),
            "stability": round(stable / float(len(winners)), 3) if winners else None,
            "flip": sorted({x for x in winners if x and x != base})}
