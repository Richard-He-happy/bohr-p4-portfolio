#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_core: extraction, cost/time arithmetic, constraint audit and plan repair for experiment-01.
Pure library over an already-parsed case dict; never writes. Used by scripts/build_plan.py."""
import json, re
from pathlib import Path

SD = Path(__file__).resolve().parent
try:
    CAT = json.loads((SD.parent / "references" / "catalog.json").read_text(encoding="utf-8"))
except Exception:
    CAT = {}


def G(k, d=None):
    v = CAT.get(k)
    return d if v is None else v


def L(k, **kw):
    t = (CAT.get("labels") or {}).get(k, k)
    try:
        return t.format(**kw)
    except Exception:
        return t


def TH(k):
    return (CAT.get("th") or {}).get(k, [])


def jd(o):
    return json.dumps(o, ensure_ascii=False)


def pe(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def pu(k):
    return k.replace("~1", "/").replace("~0", "~")


def walk(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            q = p + "/" + pe(k)
            yield q, k, v
            yield from walk(v, q)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            q = p + "/" + str(i)
            yield q, None, v
            yield from walk(v, q)


def pget(d, p):
    c = d
    for t in str(p).split("/")[1:]:
        if t:
            c = c[int(t)] if isinstance(c, list) else c[pu(t)]
    return c


NR = re.compile(r"-?\d+(?:\.\d+)?")
_U = G("units", {})
DU = _U.get("duration", {})
CUR = [tuple(x) for x in _U.get("currency", [])]
CV = _U.get("convert", {})


def fnum(x, d=None):
    if isinstance(x, bool):
        return d
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        m = NR.search(x.replace(",", "").replace("−", "-").replace("–", "-"))
        return float(m.group()) if m else d
    return d


def dur(x):
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if not isinstance(x, str):
        return None
    t, hit = 0.0, False
    for q, u in re.findall(r"(\d+(?:\.\d+)?)\s*([A-Za-zµμ.]+|[\u4e00-\u9fff]+)?", x):
        u = (u or "").strip().lower().rstrip(".")
        if u in DU:
            t, hit = t + float(q) * DU[u], True
    return t if hit else fnum(x)


def money(x):
    if isinstance(x, bool) or x is None:
        return None, None
    if isinstance(x, (int, float)):
        return float(x), "unspecified"
    if not isinstance(x, str):
        return None, None
    low, c = x.lower(), "unspecified"
    for k, v in CUR:
        if k in low:
            c = v
            break
    n = fnum(x)
    return (n, c) if n is not None else (None, None)


def rng(x):
    if isinstance(x, dict):
        u = pk(x, r"(unit|单位)")
        return fnum(pk(x, r"(min|lower|from|lo)")), fnum(pk(x, r"(max|upper|to|hi)")), u if isinstance(u, str) else None
    if isinstance(x, (list, tuple)) and len(x) >= 2:
        return fnum(x[0]), fnum(x[1]), None
    if not isinstance(x, str):
        return None, None, None
    s = x.replace("−", "-").replace("–", "-").replace("—", "-")
    s2 = re.sub(r"(?<=\d)\s*(?:-|~|to\b|and|至|到)\s*", "\x00", s, flags=re.I)
    ns = [float(m.group()) for m in (NR.search(g) for g in s2.split("\x00")) if m]
    u = re.sub(r"[0-9.\-+±<>=≤≥~,\s°·]|to\b|and|至|到", "", s).strip() or None
    if len(ns) >= 2:
        return ns[0], ns[1], u
    if len(ns) == 1:
        if re.search(r"[<≤]", s):
            return None, ns[0], u
        if re.search(r"[>≥]", s):
            return ns[0], None, u
        return ns[0], ns[0], u
    return None, None, None


def pk(d, pat, dflt=None):
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(k, str) and re.search(pat, k, re.I):
                return v
    return dflt


def nk(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(s).lower())


def uu(u):
    return (u or "").strip().lower().replace("µ", "u").replace("μ", "u").replace("°", "").rstrip(".")


def conv(q, uf, ut):
    if q is None:
        return None
    a, b = uu(uf), uu(ut)
    if a == b:
        return q
    if a in CV and b in CV and CV[a][1] == CV[b][1]:
        return q * CV[a][0] / CV[b][0]
    return None


PV = r"(temp|temperature|rpm|speed|conc|concentration|vol|volume|ph\b|pressure|power|wavelength|dose|cycle|rate|humidity|电压|温度|转速|浓度|体积|流速|功率|压力|剂量|循环)"


def pval(v):
    if isinstance(v, bool):
        return None, None
    if isinstance(v, (int, float)):
        return float(v), None
    if isinstance(v, str):
        return fnum(v), (re.sub(r"[0-9.\-+±<>=≤≥~,\s]", "", v).strip() or None)
    return None, None


def params_of(d):
    o, pv = {}, pk(d, r"(param|setting|condition|参数|条件)")
    if isinstance(pv, dict):
        o.update({str(k): v for k, v in pv.items()})
    elif isinstance(pv, list):
        for e in pv:
            if isinstance(e, dict) and pk(e, r"(name|param|key|参数|名称)") is not None:
                o[str(pk(e, r"(name|param|key|参数|名称)"))] = pk(e, r"(value|val|set|值|取值)")
    for k, v in (d or {}).items():
        if isinstance(k, str) and re.search(PV, k, re.I) and not isinstance(v, (dict, list)):
            o.setdefault(k, v)
    return o


def blocks(doc, pat, need=None):
    o = []
    for p, k, v in walk(doc):
        if not isinstance(k, str) or not re.search(pat, k, re.I):
            continue
        if isinstance(v, list) and v and all(isinstance(i, (dict, str)) for i in v):
            o.append((p, v))
        elif isinstance(v, dict) and v and all(isinstance(i, dict) for i in v.values()):
            o.append((p, [dict(i) for i in v.values()]))
    o.sort(key=lambda t: t[0].count("/"))
    for p, v in o:
        if need is None or any(need(i) for i in v):
            return p, v
    return None, []


def ext_eq(doc):
    p, items = blocks(doc, r"(equipment|instruments?|devices?|apparatus|仪器|设备|装置)",
                      lambda i: isinstance(i, dict) and pk(i, r"(name|model|名称|型号)"))
    o = []
    for i, it in enumerate(items):
        it = it if isinstance(it, dict) else {"name": it}
        lo, hi, un = rng(pk(it, r"(range|量程|working_?range|capacity|spec)"))
        rt, rc = money(pk(it, r"(hourly|per_?hour|rate|fee|price|cost|机时|租|费用|单价)"))
        av = pk(it, r"(available|remaining|capacity_?hours|可用|剩余|free)")
        o.append({"id": f"E{i+1}", "name": str(pk(it, r"^(name|equip|instrument|device|名称)$") or f"E{i+1}"),
                  "model": pk(it, r"(model|型号)"), "range": pk(it, r"(range|量程|working_?range|capacity)"),
                  "lo": lo, "hi": hi, "unit": un, "prec": pk(it, r"(precision|accuracy|resolution|精度|分辨率)"),
                  "rate": rt, "cur": rc, "avail_h": (float(av) if isinstance(av, (int, float)) and not isinstance(av, bool)
                                                       else (dur(av) or 0) / 60) if av is not None else None,
                  "sub": pk(it, r"(substitut|alternat|backup|替代)"), "ptr": f"{p}/{i}" if p else None})
    return o


def ext_rg(doc):
    p, items = blocks(doc, r"(reagents?|consumables?|materials?|chemicals?|kits?|supplies|试剂|耗材|材料|药品)",
                      lambda i: isinstance(i, dict) and pk(i, r"(name|名称|id|item)"))
    o = []
    for i, it in enumerate(items):
        it = it if isinstance(it, dict) else {"name": it}
        pr, pc = money(pk(it, r"(price|unit_?cost|单价|价格)"))
        st = pk(it, r"(stock|inventory|on_?hand|库存|余量)")
        o.append({"id": f"R{i+1}", "name": str(pk(it, r"^(name|reagent|material|chemical|名称|item)$") or f"R{i+1}"),
                  "spec": pk(it, r"(spec|规格|grade|purity|纯度|cat|catalog|货号|cas)"), "unit": pk(it, r"(unit|单位)"),
                  "price": pr, "cur": pc, "punit": pk(it, r"(price_?unit|per|每)"),
                  "stock": fnum(pk(st, r"(qty|amount|value|量)")) if isinstance(st, dict) else fnum(st),
                  "sub": pk(it, r"(substitut|alternat|backup|替代)"), "ptr": f"{p}/{i}" if p else None})
    return o


def ext_dom(doc):
    o = {}
    for p, k, v in walk(doc):
        if not isinstance(k, str) or not re.search(r"(domains?|allowed|permitted|取值|可选|候选值|levels?|grid)", k, re.I):
            continue
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, list) and vv and all(isinstance(i, (int, float, str)) for i in vv):
                    o[nk(kk)] = {"name": kk, "values": vv, "ptr": f"{p}/{pe(kk)}"}
        elif isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
            for i, it in enumerate(v):
                n, vals = pk(it, r"(name|param|参数|factor|变量)"), pk(it, r"(values|allowed|domain|options|levels|取值|可选)")
                if n and isinstance(vals, list):
                    o[nk(n)] = {"name": str(n), "values": vals, "ptr": f"{p}/{i}"}
    return o


def ext_plans(doc):
    best = (None, [])
    for p, k, v in walk(doc):
        if not isinstance(k, str) or not re.search(r"(candidate|plans?|protocols?|schemes?|variants?|versions?|方案|候选|版本)", k, re.I):
            continue
        if isinstance(v, list) and v and all(isinstance(i, dict) for i in v) \
                and any(pk(i, r"(steps?|stages?|procedures?|步骤|流程|操作)") for i in v):
            best = (p, v) if len(v) >= len(best[1]) else best
        elif isinstance(v, dict) and any(isinstance(i, dict) and pk(i, r"(steps?|stages?|步骤|流程)") for i in v.values()):
            lst = [dict(i) for i in v.values() if isinstance(i, dict)]
            best = (p, lst) if len(lst) >= len(best[1]) else best
    return best


def parse_rg(x):
    o = []
    for e in (x if isinstance(x, list) else [x]):
        if isinstance(e, str):
            m = re.search(r"(\d+(?:\.\d+)?)\s*([A-Za-zµμ%]+|[\u4e00-\u9fff]{1,3})\s*$", e)
            o.append({"name": e[:m.start()].strip(" ,，:：;") if m else e,
                      "qty": float(m.group(1)) if m else None, "unit": m.group(2) if m else None})
        elif isinstance(e, dict):
            q, u = pval(pk(e, r"(qty|quantity|amount|volume|用量|数量)"))
            o.append({"name": str(pk(e, r"(name|reagent|试剂|名称|item)") or "?"), "qty": q,
                      "unit": u or pk(e, r"(unit|单位)")})
    return o


def ext_steps(pl):
    raw = pk(pl, r"(steps?|stages?|procedures?|actions?|workflow|步骤|流程|操作|阶段)")
    it = []
    if isinstance(raw, list):
        it = raw
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, list):
                it += [dict(s, __s=k) if isinstance(s, dict) else {"action": str(s), "__s": k} for s in v]
            elif isinstance(v, dict):
                it.append(dict(v, __s=k))
    if not it and isinstance(pl, dict) and pk(pl, r"(action|operation|description|操作|步骤)"):
        it = [pl]
    o = []
    for i, s in enumerate(it):
        s = s if isinstance(s, dict) else {"action": str(s)}
        rgk = pk(s, r"(reagents?|materials?|consumable|试剂|耗材|材料)")
        eqv = pk(s, r"(equipment|instrument|device|仪器|设备)")
        o.append({"id": f"S{i+1}",
                  "act": str(pk(s, r"(action|step|operation|task|description|title|动作|步骤|操作|内容)") or f"S{i+1}"),
                  "min": dur(pk(s, r"(duration|time_?min|minutes|时长|耗时|时间)")),
                  "stage": str(pk(s, r"(stage|phase|parallel|阶段|并行)") or s.get("__s") or f"s{i+1}"),
                  "eq": [eqv] if isinstance(eqv, str) else [jd(i) for i in eqv] if isinstance(eqv, list) else [],
                  "rg": parse_rg(rgk) if rgk else [], "params": params_of(s)})
    return o


def match(nm, lst):
    k = nk(nm)
    for it in lst:
        if nk(it["name"]) == k:
            return it
    for it in lst:
        kn = nk(it["name"])
        if kn and k and (kn in k or k in kn):
            return it
    return None


def evl(pl, C):
    mat = eqc = 0.0
    eqh, note, vio, stg, unk = {}, [], [], {}, 0
    for s in pl["steps"]:
        unk += s["min"] is None
        h = (s["min"] or 0) / 60.0
        stg[s["stage"]] = max(stg.get(s["stage"], 0), s["min"] or 0)
        for en in s["eq"]:
            e = match(en, C["eq"])
            if e:
                eqh[e["name"]] = eqh.get(e["name"], 0) + h
        for r in s["rg"]:
            g = match(r["name"], C["rg"])
            if not g:
                note.append({"kind": "reagent_not_in_list", "item": r["name"], "detail": "缺契约"})
                continue
            if g["price"] is None or r["qty"] is None:
                note.append({"kind": "unpriced", "item": g["name"], "detail": "缺价或量"})
                continue
            q = conv(r["qty"], r["unit"] or g["unit"], g["punit"] or g["unit"])
            if q is None:
                note.append({"kind": "unit_mismatch", "item": g["name"],
                             "detail": f"{r['qty']} {r['unit']} 与计价 {g['punit'] or g['unit']} 不可换算"})
                continue
            mat += q * g["price"]
    for nm, h in eqh.items():
        e = match(nm, C["eq"])
        if e and e["rate"]:
            eqc += h * e["rate"]
    wall = sum(stg.values())
    for e in C["eq"]:
        need = eqh.get(e["name"])
        if need and e["avail_h"] is not None and need > e["avail_h"] + 1e-9:
            vio.append({"code": "BOOKING", "ref": e["name"], "ptr": e["ptr"],
                        "detail": f"需 {need:.2f} h > 可用 {e['avail_h']:.2f} h"})
    if C["budget"] is not None and mat + eqc > C["budget"] + 1e-9:
        vio.append({"code": "BUDGET", "ref": "budget", "ptr": C["bptr"],
                    "detail": f"成本 {mat+eqc:.2f} > 预算 {C['budget']:.2f}"})
    if C["window"] is not None and wall > C["window"] + 1e-9:
        vio.append({"code": "TIME_WINDOW", "ref": "time_window", "ptr": C["wptr"],
                    "detail": f"墙钟 {wall/1440:.2f} d > 时间窗 {C['window']/1440:.2f} d"})
    for s in pl["steps"]:
        e = match(s["eq"][0], C["eq"]) if s["eq"] else None
        for pn, pv in s["params"].items():
            val, un = pval(pv)
            if val is None:
                continue
            if e and e["lo"] is not None and e["hi"] is not None:
                if e["unit"] and un and uu(e["unit"]) != uu(un):
                    note.append({"kind": "unit_mismatch_param", "item": pn,
                                 "detail": f"参数单位 {un} 与设备单位 {e['unit']} 不一致"})
                elif val < e["lo"] - 1e-9 or val > e["hi"] + 1e-9:
                    vio.append({"code": "PARAM_RANGE", "ref": f"{s['id']}:{pn}", "ptr": e["ptr"],
                                "detail": f"{pn}={val}{un or ''} 超出 {e['name']} 量程 [{e['lo']}, {e['hi']}]"})
            d = C["dom"].get(nk(pn))
            if d:
                cand = [x for x in (fnum(y) for y in d["values"]) if x is not None]
                if cand and not any(abs(val - x) < 1e-9 for x in cand):
                    vio.append({"code": "PARAM_DOMAIN", "ref": f"{s['id']}:{pn}", "ptr": d["ptr"],
                                "detail": f"{pn}={val} 不在允许域 {d['values']} 内"})
        for r in s["rg"]:
            g = match(r["name"], C["rg"])
            if g and g["stock"] is not None and r["qty"] is not None:
                q = conv(r["qty"], r["unit"], g["unit"])
                if q is not None and q > g["stock"] + 1e-9:
                    vio.append({"code": "STOCK", "ref": g["name"], "ptr": g["ptr"],
                                "detail": f"需 {q} {g['unit'] or ''} > 库存 {g['stock']}"})
    return {"cost": round(mat + eqc, 4), "matc": round(mat, 4), "eqc": round(eqc, 4), "wall": round(wall, 2),
            "person": round(sum(s["min"] or 0 for s in pl["steps"]), 2), "eqh": eqh, "vio": vio, "note": note,
            "unk": unk, "stages": {k: round(x, 2) for k, x in stg.items()},
            "score": round(len(vio) * 1000 + mat + eqc + wall / 60.0, 4)}


def clip(v, lo, hi):
    if v is None:
        return None
    return lo if (lo is not None and v < lo) else hi if (hi is not None and v > hi) else v


def snap(v, vals):
    c = [x for x in (fnum(y) for y in vals) if x is not None]
    return min(c, key=lambda x: abs(x - v)) if c else None


def repair(pl, C, meta, ch, nmin=3):
    for _ in range(12):
        m = evl(pl, C)
        if not m["vio"]:
            return m
        done = False
        for v in m["vio"]:
            if v["code"] in ("PARAM_RANGE", "PARAM_DOMAIN"):
                sid, _, pn = v["ref"].partition(":")
                for s in pl["steps"]:
                    if s["id"] != sid or pn not in s["params"]:
                        continue
                    val, un = pval(s["params"][pn])
                    e = match(s["eq"][0], C["eq"]) if s["eq"] else None
                    d = C["dom"].get(nk(pn))
                    new = snap(val, d["values"]) if (d and val is not None) else val
                    new = clip(new, e["lo"], e["hi"]) if e else new
                    if new is None or val is None or abs(new - val) < 1e-9:
                        continue
                    s["params"][pn] = new if un is None else f"{new} {un}"
                    ch.append({"op": "clip_parameter", "field": f"{sid}.{pn}", "before": val, "after": new,
                               "rule": "参数裁剪进设备量程与有限允许域", "detail": v["detail"],
                               "evidence": meta.get(v.get("ptr") or "")})
                    done = True
                    break
            elif v["code"] == "STOCK":
                g = match(v["ref"], C["rg"])
                sub = match(g["sub"], C["rg"]) if g and isinstance(g["sub"], str) else None
                if sub and (sub["stock"] or 0) > 0:
                    for s in pl["steps"]:
                        for r in s["rg"]:
                            if match(r["name"], [g]) is g:
                                r["name"] = sub["name"]
                    ch.append({"op": "substitute_reagent", "field": g["name"], "before": g["name"],
                               "after": sub["name"], "rule": "换用输入给出的有库存替代试剂",
                               "detail": v["detail"], "evidence": meta.get(sub["ptr"] or "")})
                    done = True
                    break
            elif v["code"] == "BUDGET":
                n = pl.get("n")
                if n and n > nmin:
                    pl["n"] = max(nmin, n - 1)
                    ch.append({"op": "reduce_replicates", "field": "n_per_arm", "before": n, "after": pl["n"],
                               "rule": f"削减重复以适配预算，下界 n={nmin}", "detail": v["detail"], "evidence": None})
                    done = True
                    break
        if not done:
            break
    return evl(pl, C)


def groups_of(n):
    return [dict(g, id=f"G{i+1}", n=n) for i, g in enumerate(G("groups", []))]


def risks_of(C, m):
    out = [dict(r, owner="实验负责人", source_ref=None) for r in G("risks", [])]
    cond = G("risks_cond", {})
    if m["wall"] and C["window"] and m["wall"] > 0.8 * C["window"] and "R-TIME" in cond:
        out.append(dict(cond["R-TIME"], owner="实验负责人", source_ref=C["wptr"]))
    if C["budget"] and m["cost"] > 0.8 * C["budget"] and "R-COST" in cond:
        out.append(dict(cond["R-COST"], owner="实验负责人", source_ref=C["bptr"]))
    for i, r in enumerate(out):
        r["id"] = f"K{i+1}"
    return out


def T(h, rows):
    return "| " + " | ".join(h) + " |\n|" + "---|" * len(h) + "\n" + "".join(
        "| " + " | ".join("—" if x is None or x == "" else str(x) for x in r) + " |\n" for r in rows)


def names(v):
    return [] if v is None else [v] if isinstance(v, str) else \
        [x if isinstance(x, str) else jd(x) for x in v] if isinstance(v, list) else [jd(v)]
