#!/usr/bin/env python3
"""plan-compare scoring: hard gates, normalised criteria, rank stability.

Standard library only. Imported by scripts/main.py.
"""

from planmodel import W_DEFAULT, W_SETS, norm

def _gate(name, pid, val, lim, unit, loc, note, missing=None):
    if val is None or lim is None:
        return {"gate": name, "plan": pid, "status": "unknown",
                "missing": missing or [], "locator": loc, "note": note}
    ok = val <= lim + 1e-9
    return {"gate": name, "plan": pid, "status": "pass" if ok else "fail",
            "value": val, "limit": lim, "unit": unit,
            "over_by": 0.0 if ok else round(val - lim, 2), "locator": loc, "note": note}


def gate_rows(m, contract, limits):
    c, t, rows = m["cost"], m["time"], []
    rows.append(_gate("budget", m["id"], c["total_cost"], contract.get("budget"),
                      c["currency"], contract["locator"].get("budget"),
                      "总成本（耗材+机时+人工，含重复次数）对比预算上限",
                      ["预算上限 budget", "总成本 total_cost"]))
    rows.append(_gate("time_window", m["id"], t["total_days"], contract.get("deadline_days"),
                      "day", contract["locator"].get("deadline_days"),
                      "含制样/排期/表征/返工的总周期对比截止周期",
                      ["截止周期 deadline_days", "方案总周期 total_days"]))
    rows.append(_gate("machine_hours", m["id"], c["machine_hours"], contract.get("available_hours"),
                      "h", contract["locator"].get("available_hours"),
                      "需占机时对比可预约机时",
                      ["可预约机时 available_hours", "方案机时 machine_hours"]))
    for pname, pv in m["params"].items():
        pn = norm(pname)
        for ln, lim in (limits or {}).items():
            if not pn or not (pn == ln or pn in ln or ln in pn):
                continue
            if pv.get("num") is None or (lim["min"] is None and lim["max"] is None):
                continue
            v = pv["num"]
            bad = (lim["min"] is not None and v < lim["min"] - 1e-9) or \
                  (lim["max"] is not None and v > lim["max"] + 1e-9)
            over = max(0.0, v - lim["max"]) if (lim["max"] is not None and v > lim["max"]) else \
                (max(0.0, lim["min"] - v) if (lim["min"] is not None and v < lim["min"]) else 0.0)
            rows.append({"gate": "param_window", "plan": m["id"],
                         "status": "fail" if bad else "pass", "param": pname,
                         "value": v, "limit": [lim["min"], lim["max"]], "over_by": round(over, 3),
                         "locator": pv["locator"], "limit_locator": lim["locator"],
                         "note": "参数取值对比有限取值域/设备窗口"})
    return rows


def hard_fail(rows):
    return [r for r in rows if r["status"] == "fail"]


def scores_for(metrics, rows_by_plan, weights):
    feas = [m for m in metrics if not hard_fail(rows_by_plan[m["id"]])] or metrics
    costs = [m["cost"]["total_cost"] for m in feas if m["cost"]["total_cost"]]
    times = [m["time"]["total_days"] for m in feas if m["time"]["total_days"]]
    cmin = min(costs) if costs else None
    tmin = min(times) if times else None
    declared = sorted(m["risk_penalty"] for m in metrics if m.get("risk_declared"))
    neutral = declared[len(declared) // 2] if declared else 2.0
    out = {}
    for m in metrics:
        g = rows_by_plan[m["id"]]
        known = [r for r in g if r["status"] in ("pass", "fail")]
        passrate = sum(1 for r in known if r["status"] == "pass") / float(len(known)) if known else 0.5
        c, t = m["cost"]["total_cost"], m["time"]["total_days"]
        comp = {"completeness": m["completeness"],
                "feasibility": round(passrate, 4),
                "cost": round(min(cmin / c, 1.0), 4) if (c and cmin) else 0.5,
                "time": round(min(tmin / t, 1.0), 4) if (t and tmin) else 0.5,
                "risk": round(1.0 - (m["risk_penalty"] if m.get("risk_declared") else neutral) /
                              ((m["risk_penalty"] if m.get("risk_declared") else neutral) + 2.0), 4)}
        comp["risk_penalty_used"] = m["risk_penalty"] if m.get("risk_declared") else neutral
        out[m["id"]] = {"components": comp,
                        "total": round(sum(comp[k] * weights[k] for k in weights), 4),
                        "infeasible": bool(hard_fail(g))}
    return out


def rank(metrics, sc, cost_of):
    ids = [m["id"] for m in metrics if not sc[m["id"]]["infeasible"]] or [m["id"] for m in metrics]
    ids.sort(key=lambda i: (-sc[i]["total"], cost_of.get(i, 1e18)))
    return ids


def dominant_gap(sel_sc, other_sc):
    """Weighted component deficits -> the criterion that actually decided the call."""
    gaps = []
    for k, w in W_DEFAULT.items():
        d = (sel_sc["components"][k] - other_sc["components"][k]) * w
        if abs(d) > 1e-9:
            gaps.append({"criterion": k, "weighted_delta": round(d, 4)})
    gaps.sort(key=lambda g: -abs(g["weighted_delta"]))
    return gaps[0] if gaps else None
