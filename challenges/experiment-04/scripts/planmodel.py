#!/usr/bin/env python3
"""plan-compare core: semantic extraction, arithmetic, gating, scoring.

Standard library only. Every number keeps the JSON Pointer that produced it so
scripts/verify.py can re-derive it independently.
"""

import json
import re

# The seven comparable fields any experimental plan must specify.
REQ = [
    ("hypothesis", ("hypothes", "假设", "假说")),
    ("variables", ("variable", "factor", "变量", "因子")),
    ("controls", ("control", "对照", "blank", "sham")),
    ("steps", ("step", "procedure", "protocol", "workflow", "流程", "步骤")),
    ("parameters", ("param", "setting", "参数", "窗口", "domain")),
    ("resources", ("resource", "equipment", "instrument", "consumable", "material",
                   "budget", "设备", "耗材", "资源")),
    ("acceptance", ("accept", "criteria", "criterion", "threshold", "tolerance",
                    "判读", "验收", "标准")),
]

W_DEFAULT = {"completeness": 0.30, "feasibility": 0.20, "cost": 0.20,
             "time": 0.15, "risk": 0.15}
W_SETS = {
    "default": W_DEFAULT,
    "equal": {k: 0.20 for k in W_DEFAULT},
    "cost_led": {"completeness": 0.15, "feasibility": 0.15, "cost": 0.40,
                 "time": 0.15, "risk": 0.15},
    "time_led": {"completeness": 0.15, "feasibility": 0.15, "cost": 0.15,
                 "time": 0.40, "risk": 0.15},
    "risk_led": {"completeness": 0.15, "feasibility": 0.15, "cost": 0.15,
                 "time": 0.15, "risk": 0.40},
}

SEV = {"critical": 4.0, "severe": 4.0, "major": 3.0, "high": 3.0, "medium": 2.0,
       "moderate": 2.0, "minor": 1.0, "low": 1.0,
       "重大": 4.0, "严重": 4.0, "高": 3.0, "中": 2.0, "低": 1.0}
SEV_KEYS = ("severity", "level", "grade", "rating", "risklevel", "等级", "严重", "级别")


def norm(x):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff%]", "", str(x).lower())


def has(key, *toks):
    n = norm(key)
    return any(t in n for t in toks)


def num(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("，", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s)
    return None


def qnum(x):
    return str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)


def walk(node, ptr=""):
    yield ptr, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, ptr + "/" + str(k).replace("~", "~0").replace("/", "~1"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, "%s/%d" % (ptr, i))


def bfs(node, pred, maxdepth=9):
    q = [("", node, 0)]
    while q:
        p, v, d = q.pop(0)
        try:
            if pred(p, v):
                return p, v
        except Exception:
            pass
        if d < maxdepth:
            if isinstance(v, dict):
                q.extend((p + "/" + str(k), vv, d + 1) for k, vv in v.items())
            elif isinstance(v, list):
                q.extend(("%s/%d" % (p, i), vv, d + 1) for i, vv in enumerate(v))
    return None, None


def dget(d, *toks):
    """(value, key) of the first entry whose key matches any token; scalars first."""
    if not isinstance(d, dict):
        return None, None
    for k, v in d.items():
        if has(k, *toks) and not isinstance(v, (dict, list)):
            return v, k
    for k, v in d.items():
        if has(k, *toks):
            return v, k
    return None, None


PLAN_KEY_TOK = ("candidateplan", "candidates", "plans", "planlist", "options",
                "alternatives", "proposals", "arms", "schemes", "方案", "候选")


def find_plans(case):
    """Locate the candidate-plan collection -> (pointer, list of dicts)."""
    def as_list(p, v):
        return isinstance(v, list) and len(v) >= 1 and all(isinstance(x, dict) for x in v)

    def p_key(p, v):
        return as_list(p, v) and has(p.rsplit("/", 1)[-1], *PLAN_KEY_TOK)

    p, v = bfs(case, p_key)
    if p:
        return p, v

    def p_struct(p, v):
        if not as_list(p, v) or len(v) < 2:
            return False
        return min(sum(1 for _, t in REQ if any(has(k, *t) for k in x)) for x in v) >= 2

    p, v = bfs(case, p_struct)
    if p:
        return p, v

    def p_dict(p, v):
        return (isinstance(v, dict) and len(v) >= 2
                and all(isinstance(x, dict) for x in v.values())
                and has(p.rsplit("/", 1)[-1], *PLAN_KEY_TOK))

    p, v = bfs(case, p_dict)
    if p:
        out = []
        for k, x in v.items():
            y = dict(x)
            y.setdefault("plan_key", k)
            out.append(y)
        return p, out
    return None, None


def collect_contract(case):
    """Organizer resource / price / booking contract, each value with its locator."""
    out = {"machine_rate": None, "labor_rate": None, "budget": None,
           "available_hours": None, "deadline_days": None, "currency": None,
           "locator": {}}
    for p, v in walk(case):
        if not isinstance(v, dict):
            continue
        for k, x in v.items():
            kn, path, n = norm(k), p + "/" + str(k), num(x)
            if n is None:
                if out["currency"] is None and isinstance(x, str) and "currency" in kn:
                    out["currency"] = x
                continue
            if out["budget"] is None and any(t in kn for t in ("budget", "cap", "ceiling", "预算", "上限")) \
                    and not any(t in kn for t in ("per", "rate", "hour")):
                out["budget"], out["locator"]["budget"] = n, path
            elif out["machine_rate"] is None and "hours" not in kn \
                    and any(t in kn for t in ("machine", "instrument", "equipment", "机时")) \
                    and any(t in kn for t in ("rate", "hour", "fee", "费")):
                out["machine_rate"], out["locator"]["machine_rate"] = n, path
            elif out["labor_rate"] is None and "hours" not in kn \
                    and any(t in kn for t in ("labor", "person", "staff", "man", "人工", "工时")) \
                    and any(t in kn for t in ("rate", "hour", "fee", "费")):
                out["labor_rate"], out["locator"]["labor_rate"] = n, path
            elif out["available_hours"] is None and any(t in kn for t in ("availab", "capacity", "档期", "可用")):
                out["available_hours"], out["locator"]["available_hours"] = n, path
            elif out["deadline_days"] is None and any(t in kn for t in ("deadline", "maxdays", "期限")) \
                    and any(t in kn for t in ("day", "天", "week", "周")):
                out["deadline_days"], out["locator"]["deadline_days"] = n, path
    out["found"] = sorted(out["locator"])
    return out


def collect_limits(case):
    """Finite parameter domains / equipment windows: norm(name) -> {min,max,locator}."""
    out = {}
    for p, v in walk(case):
        if not isinstance(v, dict):
            continue
        lo = num(dget(v, "min", "minimum", "lower", "下限", "最小")[0])
        hi = num(dget(v, "max", "maximum", "upper", "上限", "最大")[0])
        if lo is None and hi is None:
            rng = dget(v, "range", "allowed", "domain", "window", "区间", "范围")[0]
            if isinstance(rng, list) and len(rng) == 2:
                lo, hi = num(rng[0]), num(rng[1])
        if lo is None and hi is None:
            continue
        seg = p.rsplit("/", 1)[-1]
        if seg.isdigit():
            seg = p.rsplit("/", 2)[-2] + "[]"
        out[norm(seg)] = {"name": seg, "min": lo, "max": hi, "locator": p}
    return out


def field_presence(plan):
    out = {}
    for name, toks in REQ:
        loc = None
        for p, v in walk(plan):
            seg = p.rsplit("/", 1)[-1]
            if seg and v not in (None, "", [], {}) and has(seg, *toks):
                loc = p
                break
        out[name] = loc
    return out


def find_num_ptr(d, *toks):
    """(pointer, value) of the first scalar whose key matches tokens."""
    for p, v in walk(d):
        seg = p.rsplit("/", 1)[-1]
        if seg and not isinstance(v, (dict, list)) and num(v) is not None and has(seg, *toks):
            return p, num(v)
    return None, None


def extract_cost(plan, pptr, contract):
    """consumables*n + machine_h*rate_m + labor_h*rate_l + one-off."""
    lines = []
    one_off = num(dget(plan, "oneoff", "fixedcost", "setupcost", "capex", "一次性")[0]) or 0.0
    runs = num(dget(plan, "nruns", "runs", "replicates", "replicate", "repeat",
                    "重复", "批次", "平行")[0])
    runs = 1.0 if runs is None else max(runs, 1.0)
    for p, v in walk(plan, pptr):
        if not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
            continue
        seg = p.rsplit("/", 1)[-1]
        if has(seg, "rate", "hour", "tariff", "机时", "工时"):
            continue
        rows = []
        for i, x in enumerate(v):
            pv = num(dget(x, "unitprice", "unitcost", "price", "costper", "fee",
                          "tariff", "单价", "价格", "费用", "报价")[0])
            if pv is None:
                rows = []
                break
            qv = num(dget(x, "qty", "quantity", "count", "amount", "pcs", "num",
                          "数量", "件数")[0])
            lab = dget(x, "item", "name", "consumable", "material", "reagent", "名称", "耗材")[0]
            tag = norm(str(lab or "") + seg)
            rows.append({
                "label": str(lab) if lab not in (None, "") else "line%d" % (i + 1),
                "qty": 1.0 if qv is None else qv,
                "unit_price": pv,
                "scaling": "one_off" if any(t in tag for t in ("oneoff", "fixed", "setup", "一次性")) else "per_run",
                "subtotal": round((1.0 if qv is None else qv) * pv, 4),
                "locator": "%s/%d" % (p, i), "quote": qnum(pv)})
        lines.extend(rows)

    mh_loc, mh = find_num_ptr(plan, "machinehours", "instrumenthours", "equipmenthours", "机时")
    lh_loc, lh = find_num_ptr(plan, "laborhours", "personhours", "manhours", "workhours", "人工工时")
    mrate, lrate = contract.get("machine_rate"), contract.get("labor_rate")
    per_run = sum(l["subtotal"] for l in lines if l["scaling"] == "per_run")
    fixed = sum(l["subtotal"] for l in lines if l["scaling"] == "one_off") + one_off
    mcost = mh * mrate if (mh is not None and mrate is not None) else None
    lcost = lh * lrate if (lh is not None and lrate is not None) else None
    missing = []
    if not lines:
        missing.append("耗材/采购明细（缺含单价的数量行）")
    if mh is None:
        missing.append("机时 machine_hours")
    if mrate is None:
        missing.append("机时费率 contract.machine_rate")
    if lh is None:
        missing.append("人工工时 labor_hours")
    if lrate is None:
        missing.append("人工费率 contract.labor_rate")
    total = None
    if lines or mcost is not None or lcost is not None:
        total = runs * per_run + fixed + (mcost or 0.0) + (lcost or 0.0)
    declared = num(dget(plan, "totalcost", "totalbudget", "costestimate", "budgettotal",
                        "预算合计", "总成本")[0])
    check = {"declared": declared, "status": "not_declared"}
    if declared is not None and total:
        d = abs(total - declared) / declared * 100.0
        check = {"declared": declared, "computed": round(total, 2), "delta_pct": round(d, 2),
                 "status": "match" if d <= 1.0 else "mismatch"}
    return {"runs": runs, "lines": lines, "machine_locator": mh_loc, "labor_locator": lh_loc, "per_run_cost": round(per_run, 2),
            "fixed_cost": round(fixed, 2), "machine_hours": mh, "machine_rate": mrate,
            "machine_cost": None if mcost is None else round(mcost, 2),
            "labor_hours": lh, "labor_rate": lrate,
            "labor_cost": None if lcost is None else round(lcost, 2),
            "total_cost": None if total is None else round(total, 2),
            "currency": contract.get("currency") or "CNY",
            "formula": "total = runs*sum(qty*unit_price) + fixed + machine_h*rate_m + labor_h*rate_l",
            "declared_check": check, "missing": missing, "complete": not missing}


PHASES = [("prep", ("prep", "samplepreparation", "制样", "样品制备")),
          ("run", ("runhours", "experimenthours", "acquisition", "实验时长")),
          ("queue", ("queue", "waiting", "booking", "排期", "排队", "等待")),
          ("analysis", ("analysis", "characteri", "measure", "表征", "测试", "分析")),
          ("rework", ("rework", "redo", "retest", "返工", "重做"))]


def extract_time(plan):
    phases, seen, days = [], set(), None
    for p, v in walk(plan):
        seg = p.rsplit("/", 1)[-1]
        if not seg or isinstance(v, (dict, list)):
            continue
        x = num(v)
        if x is None:
            continue
        if days is None and has(seg, "totaldays", "durationdays", "预计天数", "总天数"):
            days = x
        for name, toks in PHASES:
            if has(seg, *toks):
                h = x / 60.0 if has(seg, "min", "分钟") else (x * 24.0 if has(seg, "day", "天") else x)
                if (name, p) not in seen:
                    seen.add((name, p))
                    phases.append({"phase": name, "hours": round(h, 3),
                                   "locator": p, "quote": qnum(v)})
                break
    total_h = sum(ph["hours"] for ph in phases) if phases else None
    if days is None and total_h is not None:
        days, basis = round(total_h / 8.0, 2), "derived: 8 h/working day"
    else:
        days, basis = (days, "explicit in plan") if days is not None else (None, "unavailable")
    return {"phases": phases, "total_hours": None if total_h is None else round(total_h, 2),
            "total_days": days, "days_basis": basis,
            "phases_covered": sorted({ph["phase"] for ph in phases})}


def _risk_items(v, ptr):
    out = []
    if isinstance(v, list):
        for i, x in enumerate(v):
            out.extend(_risk_items(x, "%s/%d" % (ptr, i)))
    elif isinstance(v, dict):
        inner = [k for k in v if has(k, "risk", "hazard", "failure", "风险", "异常")
                 and isinstance(v[k], (dict, list))]
        if inner:
            for k in inner:
                out.extend(_risk_items(v[k], ptr + "/" + str(k)))
        else:
            out.append({"text": json.dumps(v, ensure_ascii=False)[:300],
                        "severity": dget(v, *SEV_KEYS)[0],
                        "trigger": dget(v, "trigger", "condition", "when", "触发")[0],
                        "mitigation": dget(v, "mitigation", "control", "action", "缓解", "措施")[0],
                        "locator": ptr, "quote": ""})
    elif isinstance(v, str):
        out.append({"text": v[:300], "severity": None, "trigger": None,
                    "mitigation": None, "locator": ptr, "quote": v[:60]})
    return out


def extract_risk(plan):
    items = []

    def visit(node, ptr=""):
        if isinstance(node, dict):
            for k, v in node.items():
                pth = ptr + "/" + str(k)
                if has(k, "risk", "hazard", "failure", "风险", "异常"):
                    items.extend(_risk_items(v, pth))
                else:
                    visit(v, pth)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                visit(v, "%s/%d" % (ptr, i))

    visit(plan)
    pen = 0.0
    for it in items:
        s = it.get("severity")
        w = SEV.get(norm(s)) if isinstance(s, str) else None
        w = 2.0 if w is None and s is not None else (1.5 if w is None else w)
        it["weight"] = w
        pen += w
    return items, round(pen, 2)


def extract_params(plan):
    out = {}
    for p, v in walk(plan):
        seg = p.rsplit("/", 1)[-1]
        if isinstance(v, dict) and has(seg, "param", "参数", "setting", "condition", "条件"):
            for k, x in v.items():
                if not isinstance(x, (dict, list)):
                    out[k] = {"value": x, "num": num(x), "locator": p + "/" + str(k)}
        elif isinstance(v, list) and has(seg, "param", "参数"):
            for i, x in enumerate(v):
                if isinstance(x, dict):
                    nm = dget(x, "name", "param", "key", "名称")[0]
                    vl = dget(x, "value", "val", "setting", "值")[0]
                    if nm is not None:
                        out[str(nm)] = {"value": vl, "num": num(vl),
                                        "locator": "%s/%d" % (p, i)}
    return out


def plan_id(plan, i):
    for t in ("planid", "id", "name", "title", "label", "code", "编号"):
        v = dget(plan, t)[0]
        if isinstance(v, (str, int)) and str(v).strip() and len(str(v)) < 80:
            return str(v).strip()
    return str(plan.get("plan_key") or "P%d" % (i + 1))


def build_metrics(plans, pptr, contract):
    out = []
    for i, plan in enumerate(plans):
        fp = field_presence(plan)
        cov = [k for k, v in fp.items() if v]
        items, pen = extract_risk(plan)
        cost, tm = extract_cost(plan, "%s/%d" % (pptr, i), contract), extract_time(plan)
        if tm["total_hours"] is None and (cost["machine_hours"] or cost["labor_hours"]):
            h = (cost["machine_hours"] or 0.0) + (cost["labor_hours"] or 0.0)
            tm.update({"total_hours": round(h, 2), "total_days": round(h / 8.0, 2),
                       "days_basis": "derived: (machine_h+labor_h)/8"})
        out.append({
            "id": plan_id(plan, i), "index": i, "pointer": "%s/%d" % (pptr, i),
            "fields": fp, "fields_covered": cov,
            "fields_missing": [k for k in fp if k not in cov],
            "completeness": round(len(cov) / float(len(REQ)), 3),
            "cost": cost, "time": tm, "risk_items": items, "risk_penalty": pen,
            "risk_declared": bool(items),
            "params": extract_params(plan)})
    return out
