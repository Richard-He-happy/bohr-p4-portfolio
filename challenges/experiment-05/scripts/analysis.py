#!/usr/bin/env python3
import math, re
from collections import Counter

CFG = dict(z=3.5, zw=2.5, reps=3, cv=30.0, anom=40, brk=0.15, minz=0.02)
BATCH = re.compile(r"batch|lot|批次|批号|plate|板|channel|通道|well|孔|组次", re.I)
CTRL = re.compile(r"ctrl|control|blank|vehicle|对照|空白|阴性|基线", re.I)
LIM = re.compile(r"(?:≤|<=|NMT|不超过|限度|limit)\s*[:：]?\s*(\d+(?:\.\d+)?)", re.I)
UNIT = re.compile(r"[\(\[]([^\)\]]{1,14})[\)\]]")
PLC = re.compile(r"^(>>?|>=|over|overflow|saturat\w*|超量程|溢出|饱和|nd)$", re.I)
NUMRE = re.compile(r"^([<>≤≥]{0,2})\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*[%a-zA-Zμ°µ/^0-9.\-]*$")
def pnum(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    s = str(v).strip().replace("−", "-").replace("\u00a0", " ")
    if not s or PLC.match(s):
        return None
    if re.fullmatch(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    m = NUMRE.match(s)
    if not m:
        return None
    try:
        f = float(m.group(2))
    except ValueError:
        return None
    return f if math.isfinite(f) else None
def med(x):
    x = sorted(x)
    n = len(x)
    return 0.0 if not n else (x[n // 2] if n % 2 else (x[n // 2 - 1] + x[n // 2]) / 2)
def sd(x):
    n = len(x)
    if n < 2:
        return 0.0
    m = sum(x) / n
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
def rnd(v, k=6):
    return None if v is None else round(v, k)
def rb(v):
    m = med(v)
    s = 1.4826 * med([abs(a - m) for a in v])
    if s <= 1e-12:
        s = sd(v)
    return m, max(s, CFG["minz"] * abs(m))
def fit(x, y):
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return {"slope": sxy / sxx, "ic": my - sxy / sxx * mx,
            "r2": sxy * sxy / (sxx * syy) if syy > 0 else 0.0}
def res(x, y, f):
    return sum((b - f["ic"] - f["slope"] * a) ** 2 for a, b in zip(x, y))
def bpt(x, y):
    n = len(y)
    if n < 8:
        return None
    f = fit(x, y)
    base = res(x, y, f) if f else 0
    if base <= 0:
        return None
    best = None
    for k in range(3, n - 2, max(1, n // 80)):
        f1, f2 = fit(x[:k], y[:k]), fit(x[k:], y[k:])
        if not f1 or not f2:
            continue
        s = res(x[:k], y[:k], f1) + res(x[k:], y[k:], f2)
        if best is None or s < best[0]:
            best = (s, k, f1, f2)
    if not best or 1 - best[0] / base < CFG["brk"]:
        return None
    return {"x": rnd(x[best[1]]), "gain": round(1 - best[0] / base, 3),
            "slope_before": rnd(best[2]["slope"]), "slope_after": rnd(best[3]["slope"]),
            "sign_flip": (best[2]["slope"] > 0) != (best[3]["slope"] > 0)}
def unit_of(nm):
    m = UNIT.search(str(nm))
    return m.group(1).strip() if m else ""
def feats(x, y):
    n = len(y)
    if n < 4:
        return None
    ym, rg, im = max(y), max(y) - min(y), y.index(max(y))
    f = fit(x[:max(2, int(n * 0.12))], y[:max(2, int(n * 0.12))])
    return {"n": n, "ymax": rnd(ym), "k_init": rnd(f["slope"]) if f else None,
            "auc": rnd(sum((x[i + 1] - x[i]) * (y[i + 1] + y[i]) / 2.0 for i in range(n - 1))),
            "plateau_frac": round(sum(1 for v in y if rg > 0 and v >= ym - 0.02 * rg) / n, 3),
            "drop_after_peak_pct": round(100 * (ym - max(y[im:])) / rg, 2) if rg > 0 else None}
def uniq(t, i):
    out = []
    for r in t["rows"]:
        v = str(r[i]).strip()
        if v and v not in out:
            out.append(v)
    return out
def bcol(t):
    best = None
    for i, k in enumerate(t["kind"]):
        if k != "cat":
            continue
        vals = [str(r[i]).strip() for r in t["rows"]]
        u = []
        for v in vals:
            if v and v not in u:
                u.append(v)
        if 2 <= len(u) <= 80:
            tr = sum(1 for x, y in zip(vals, vals[1:]) if x != y)
            if tr <= max(1, len(vals) // 2) and (best is None or len(u) > best[1]):
                best = (i, len(u))
    return best[0] if best else None
def traces(t):
    num = [i for i, k in enumerate(t["kind"]) if k == "num"]
    if len(num) < 2:
        return None
    rows, bc = t["rows"], bcol(t)
    if bc is None:
        blocks = [("", list(range(len(rows))))]
    else:
        blocks, cur, acc = [], None, []
        for i, r in enumerate(rows):
            lab = str(r[bc]).strip()
            if lab != cur and acc:
                blocks.append((cur, acc))
                acc = []
            cur = lab
            acc.append(i)
        if acc:
            blocks.append((cur, acc))
    xc = None
    for i in num:
        vv = [v for v in (pnum(rows[j][i]) for j in blocks[0][1]) if v is not None]
        if len(vv) >= 6 and len(set(vv)) == len(vv) and all(b > a for a, b in zip(vv, vv[1:])):
            xc = i
            break
    if xc is None:
        return None
    ys, ser = [i for i in num if i != xc], []
    if bc is None and len(ys) >= 4 and len(rows) <= 2000:
        for i in ys:
            pp = [(pnum(r[xc]), pnum(r[i])) for r in rows]
            pp = [(a, b) for a, b in pp if a is not None and b is not None]
            fl = feats([a for a, _ in pp], [b for _, b in pp]) if len(pp) >= 6 else None
            if fl:
                ser.append({"label": t["cols"][i], "n": len(pp), "feat": {t["cols"][i]: fl}})
    else:
        for lab, idx in blocks:
            xs, pt = [], dict((i, []) for i in ys)
            for j in idx:
                xv = pnum(rows[j][xc])
                if xv is None:
                    continue
                xs.append(xv)
                for i in ys:
                    pt[i].append(pnum(rows[j][i]))
            if len(xs) < 6:
                continue
            fd = {}
            for i in ys:
                pp = [(a, b) for a, b in zip(xs, pt[i]) if b is not None]
                fl = feats([a for a, _ in pp], [b for _, b in pp]) if len(pp) >= 6 else None
                if fl:
                    fd[t["cols"][i]] = fl
            if fd:
                ser.append({"label": lab or t["rel"], "n": len(xs), "feat": fd})
    if len(ser) < 2:
        return None
    rep = max(ser, key=lambda z: z["n"])
    nm = list(rep["feat"])[0]
    fd = rep["feat"][nm]
    return {"table": t, "x": t["cols"][xc], "series": ser[:300],
            "trend": {"metric": nm, "x": t["cols"][xc], "n": rep["n"], "slope": fd.get("k_init"), "r2": None,
                      "direction": "上升" if (fd.get("k_init") or 0) > 0 else "下降", "amplitude_pct": None,
                      "breakpoint": None, "plateau": (fd.get("plateau_frac") or 0) > 0.3, "file": t["rel"],
                      "note": "代表曲线 k_init",
                      "locator": "%s | %s | series %s" % (t["rel"], t["loc"] or "-", rep["label"])}}
def add(ctx, t, typ, mi, obj, key, row, val, ref, z, verdict, quote, nref):
    loc = "%s | %s | " % (t["rel"], t["loc"] or "-")
    if row is not None and mi is not None:
        loc += "row %d | col %s" % (row + t["rowbase"], t["cols"][mi])
    elif mi is not None:
        loc += "col %s" % t["cols"][mi]
    else:
        loc += "series %s" % obj
    d = {"type": typ, "verdict": verdict, "metric": t["cols"][mi] if mi is not None else "", "object": obj,
         "scope_key": key, "batch": "", "value": rnd(val), "reference": rnd(ref), "n_ref": nref, "file": t["rel"],
         "dev_pct": round(100 * (val - ref) / abs(ref), 2) if val is not None and ref else None,
         "robust_z": rnd(z, 2), "threshold": CFG["z"], "quote": str(quote)[:160], "locator": loc}
    if row is not None:
        for i, k in enumerate(t["kind"]):
            if k == "cat" and BATCH.search(t["cols"][i]) and str(t["rows"][row][i]).strip():
                d["batch"] = str(t["rows"][row][i]).strip()
                break
    ctx["anomalies"].append(d)
def gstat(ctx, t):
    num = [i for i, k in enumerate(t["kind"]) if k == "num"]
    cats = [(i, uniq(t, i)) for i, k in enumerate(t["kind"]) if k == "cat"]
    cats = [c for c in cats if 2 <= len(c[1]) <= 40][:2]
    for mi in num[:10]:
        pairs = [(j, pnum(t["rows"][j][mi])) for j in range(len(t["rows"]))]
        pairs = [(j, v) for j, v in pairs if v is not None]
        if len(pairs) < 4:
            continue
        vals = [v for _, v in pairs]
        gm, gs = rb(vals)
        top = Counter(round(v, 9) for v in vals).most_common(1)[0]
        if len(pairs) >= 8 and top[1] >= max(3, 0.15 * len(pairs)) and top[0] in (max(vals), min(vals)):
            ctx["tags"].add("clipping")
            ctx["clip"].append({"metric": t["cols"][mi], "value": top[0], "count": top[1], "n": len(pairs),
                                "file": t["rel"], "quote": "同值 %s×%d（共 %d）" % (top[0], top[1], len(pairs)),
                                "locator": "%s | %s | col %s" % (t["rel"], t["loc"] or "-", t["cols"][mi])})
        ref, kx = {}, next((i for i in num if i != mi and 2 <= len(set(
            v for v in (pnum(r[i]) for r in t["rows"]) if v is not None)) <= 15), None)
        if kx is not None:
            g = {}
            for j, v in pairs:
                xv = pnum(t["rows"][j][kx])
                if xv is not None:
                    g.setdefault(xv, []).append(v)
            if len(g) >= 2 and min(len(v) for v in g.values()) >= 2:
                for k2, vs in g.items():
                    ref[k2] = rb(vs)
        for j, v in pairs:
            m, s = gm, gs
            if ref and kx is not None:
                m, s = ref.get(pnum(t["rows"][j][kx]), (gm, gs))
            z = (v - m) / s if s > 1e-12 else 0.0
            if abs(z) >= CFG["zw"]:
                add(ctx, t, "outlier", mi, "", t["cols"][kx] if kx is not None else "", j, v, m, z,
                    "confirmed_outlier" if abs(z) >= CFG["z"] else "watch", t["rows"][j][mi], len(pairs))
        for ki, ku in cats:
            lv = {}
            for j, v in pairs:
                lab = str(t["rows"][j][ki]).strip()
                if lab:
                    lv.setdefault(lab, []).append(v)
            if len(lv) < 2:
                continue
            allv = [v for vs in lv.values() for v in vs]
            m0 = sum(allv) / len(allv)
            sst = sum((a - m0) ** 2 for a in allv)
            ssb = sum(len(vs) * (sum(vs) / len(vs) - m0) ** 2 for vs in lv.values())
            blk = {"key": t["cols"][ki], "metric": t["cols"][mi], "n": len(allv),
                   "eta2": round(ssb / sst, 3) if sst > 0 else 0.0, "file": t["rel"],
                   "locator": "%s | %s | cols %s,%s" % (t["rel"], t["loc"] or "-", t["cols"][ki], t["cols"][mi]),
                   "levels": [{"level": lab, "n": len(vs), "mean": rnd(sum(vs) / len(vs)), "sd": rnd(sd(vs)),
                               "cv": round(100 * sd(vs) / abs(sum(vs) / len(vs)), 2) if sum(vs) else None}
                              for lab, vs in lv.items()]}
            ctx["groups"].append(blk)
            if not any(CTRL.search(l["level"]) for l in blk["levels"]):
                ctx["tags"].add("no_control")
            if blk["eta2"] >= 0.5 and all((l["cv"] or 0) < CFG["cv"] for l in blk["levels"] if l["n"] >= 2):
                ctx["tags"].add("hetero")
            if min(len(vs) for vs in lv.values()) < CFG["reps"]:
                ctx["tags"].add("short_reps")
def trends(ctx, t):
    num = [i for i, k in enumerate(t["kind"]) if k == "num"]
    rows = t["rows"]
    for xi in num[:4]:
        xs = [pnum(r[xi]) for r in rows]
        ok = [v for v in xs if v is not None]
        u, mono = set(ok), all(y >= x for x, y in zip(ok, ok[1:]))
        if len(ok) < 5 or len(u) < 5 or (len(u) > 0.8 * len(ok) + 2 and not mono):
            continue
        for mi in num[:8]:
            if mi == xi:
                continue
            agg = {}
            for a, r in zip(xs, rows):
                b = pnum(r[mi])
                if a is not None and b is not None:
                    agg.setdefault(a, []).append(b)
            if len(agg) < 5:
                continue
            X = sorted(agg)
            Y = [sum(agg[a]) / len(agg[a]) for a in X]
            f = fit(X, Y)
            if not f:
                continue
            bp = bpt(X, Y)
            d = "上升" if f["slope"] > 0 else "下降"
            if f["r2"] < 0.1:
                d = "无显著趋势"
            if bp and bp["sign_flip"]:
                d = "先升后降" if bp["slope_before"] > 0 else "先降后升"
            elif bp and abs(bp["slope_after"]) < 0.25 * abs(bp["slope_before"]):
                d += "（后转平台）"
            mm = med(Y)
            ctx["trend"].append({"metric": t["cols"][mi], "x": t["cols"][xi], "n": len(Y), "slope": rnd(f["slope"]),
                                 "r2": round(f["r2"], 3), "direction": d, "breakpoint": bp,
                                 "amplitude_pct": round(100 * (max(Y) - min(Y)) / abs(mm), 2) if mm else None,
                                 "file": t["rel"],
                                 "locator": "%s | %s | cols %s,%s" % (t["rel"], t["loc"] or "-", t["cols"][xi], t["cols"][mi])})
def sscan(ctx, tr):
    ser, names, t = tr["series"], [], tr["table"]
    for s in ser:
        for k in s["feat"]:
            if k not in names:
                names.append(k)
    for nm in names[:2]:
        for f in ("ymax", "auc", "k_init"):
            vv = [(i, s["feat"][nm][f]) for i, s in enumerate(ser) if nm in s["feat"] and s["feat"][nm].get(f) is not None]
            if len(vv) < 5:
                continue
            m, s0 = rb([v for _, v in vv])
            for i, v in vv:
                z = (v - m) / s0 if s0 > 1e-12 else 0.0
                if abs(z) >= CFG["z"]:
                    ctx["anomalies"].append({
                        "type": "series_outlier", "verdict": "confirmed_outlier", "metric": nm, "feature": f,
                        "object": ser[i]["label"], "scope_key": "series/" + f, "value": rnd(v), "reference": rnd(m),
                        "dev_pct": round(100 * (v - m) / abs(m), 2) if m else None, "robust_z": round(z, 2),
                        "n_ref": len(vv), "file": t["rel"], "batch": "",
                        "quote": "%s: %s=%s (n=%d)" % (ser[i]["label"], f, v, ser[i]["n"]),
                        "locator": "%s | %s | series %s" % (t["rel"], t["loc"] or "-", ser[i]["label"])})
def post(ctx):
    best = {}
    for x in ctx["anomalies"]:
        k = (x.get("file"), x.get("locator"), x.get("metric"), x.get("type"))
        if k not in best or abs(x.get("robust_z") or 0) > abs(best[k].get("robust_z") or 0):
            best[k] = x
    ctx["anomalies"] = sorted(best.values(), key=lambda x: (x["verdict"] != "confirmed_outlier",
                                                           -abs(x.get("robust_z") or 0)))[:CFG["anom"]]
    for i, x in enumerate(ctx["anomalies"]):
        x["id"] = "A%02d" % (i + 1)
    out = [x for x in ctx["anomalies"] if x["type"] in ("outlier", "series_outlier")]
    cnt = Counter(x["batch"] for x in out if x.get("batch"))
    tot = sum(cnt.values())
    if tot >= 2 and cnt.most_common(1)[0][1] >= max(2, 0.5 * tot):
        b, c = cnt.most_common(1)[0]
        ctx["tags"].add("batch")
        ctx["binding"] = {"dimension": "batch/channel", "level": b, "n": c, "total": tot,
                          "locator": "result.json#anomalies", "quote": "%d/%d 异常集中在 %s" % (c, tot, b)}
    for x in out:
        v, m0 = x.get("value"), x.get("reference")
        if v and m0 and any(0.9 * k <= abs(v / m0) <= 1.1 * k or 0.9 / k <= abs(v / m0) <= 1.1 / k
                            for k in (10, 100, 1000)):
            ctx["tags"].add("magnitude")
def analyse(tables, errs):
    ctx = {"trend": [], "anomalies": [], "groups": [], "clip": [], "tags": set(), "series": [], "binding": None,
           "thresholds": {"robust_z_outlier": CFG["z"], "robust_z_watch": CFG["zw"], "min_replicates": CFG["reps"]}}
    for t in tables:
        tr = None
        try:
            tr = traces(t)
        except Exception as e:
            errs.append({"stage": "traces", "file": t["rel"], "detail": str(e)[:150]})
        if tr:
            ctx["trend"].append(tr["trend"])
            ctx["series"].append({"file": t["rel"], "locator": t["loc"] or "-", "x": tr["x"],
                                  "n": len(tr["series"]), "labels": [s["label"] for s in tr["series"]][:40]})
            try:
                sscan(ctx, tr)
            except Exception as e:
                errs.append({"stage": "sscan", "file": t["rel"], "detail": str(e)[:150]})
        for fn in ((gstat,) if not tr or len(tr["series"]) < 5 else ()):
            try:
                fn(ctx, tr["table"] if tr else t)
            except Exception as e:
                errs.append({"stage": "gstat", "file": t["rel"], "detail": str(e)[:150]})
        try:
            trends(ctx, t)
        except Exception as e:
            errs.append({"stage": "trends", "file": t["rel"], "detail": str(e)[:150]})
    try:
        post(ctx)
    except Exception as e:
        errs.append({"stage": "post", "detail": str(e)[:150]})
    return ctx

CAUSE = [("magnitude", "单位换算或数量级录入错误", "与组中位数差约 10^n", 5, "回查导出值与表头单位",
          "比值≈10^n 单位不一", "单位一致、可由稀释解释"),
         ("clipping", "读数封顶/信号饱和", "同值在极值反复出现", 5, "对照量程/增益稀释重测",
          "重测回量程中部", "重测仍为同一极值"),
         ("batch", "批次/通道系统偏差", "", 4, "该批/通道重测质控样", "质控样同样偏移",
          "质控样正常，差异来自样品"),
         ("short_reps", "重复数不足的伪异常", "组内 n<3，尺度不可靠", 5, "补 n>=3 重算 MAD",
          "补齐后 z 回阈值内", "补齐后仍显著偏离"),
         ("no_control", "缺对照，难分系统偏差与效应", "无空白/阴性组", 4, "补同批空白/阴性对照",
          "对照稳定可归一化", "对照本身波动大")]
def causes(ctx):
    T = ctx["tags"]
    A = [x for x in ctx["anomalies"] if x["type"] in ("outlier", "series_outlier", "oos_limit")]
    ev = [{"id": a["id"], "detail": "%s=%s（参照 %s，z=%s）" % (a.get("metric"), a.get("value"), a.get("reference"),
                                                               a.get("robust_z")),
           "locator": a["locator"], "quote": a["quote"]} for a in A[:4]]
    C = []
    for key, name, mech, scr, test, ok, no in CAUSE:
        if key not in T:
            continue
        evd = ev
        if key == "batch" and ctx["binding"]:
            b = ctx["binding"]
            mech = "%d/%d 个确认异常集中在 %s" % (b["n"], b["total"], b["level"])
            evd = [{"id": "-", "detail": b["quote"], "locator": b["locator"], "quote": b["quote"]}]
        elif key == "clipping" and ctx["clip"]:
            mech = ctx["clip"][0]["quote"]
        C.append({"candidate": name, "mechanism": mech or "", "support_evidence": evd, "counter_evidence": [],
                  "testability": scr, "test": test, "supported_if": ok, "refuted_if": no,
                  "caveat": "候选原因，需 test 后定论"})
    if A and not (T & {"magnitude", "clipping", "batch"}):
        C.append({"candidate": "单点操作误差", "mechanism": "异常点孤立，邻点正常",
                  "support_evidence": ev, "counter_evidence": [], "testability": 3, "test": "回查原始记录与操作日志",
                  "supported_if": "日志显示该点有偏差", "refuted_if": "日志无异常且复测可复现", "caveat": "候选原因"})
    if not A:
        C.append({"candidate": "未检出离群点", "mechanism": "稳健 z 均低于 %.1f" % CFG["z"],
                  "support_evidence": [], "counter_evidence": [], "testability": 5, "test": "复核噪声估计与阈值",
                  "supported_if": "CV 与方法验证值一致", "refuted_if": "CV 偏大需查测量系统", "caveat": "未检出不等于不存在"})
    for c in C:
        c["score"] = round(min(len(c["support_evidence"]), 3) * 2 + c["testability"] / 2.0, 2)
    C.sort(key=lambda c: -c["score"])
    for i, c in enumerate(C):
        c["rank"], c["id"] = i + 1, "C%d" % (i + 1)
    return C
