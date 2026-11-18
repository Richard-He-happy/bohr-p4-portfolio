# -*- coding: utf-8 -*-
"""main.py — 审查入口；恒 exit 0。"""
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import feas as F

T0 = time.time()
HELP = """实验方案可行性审查 v%s
python3 -B scripts/main.py [--input DIR] [--output DIR] [--help]
  --input 输入目录  --output 产物目录；恒 exit 0，中断仍有 partial。""" % F.VERSION
_LIB = {}
RH = ["risk_id", "mode", "status", "trigger", "mitigation", "escalation", "locator"]
CH = ["check_id", "plan", "class", "item", "severity", "verdict", "basis", "needs_human",
      "locator", "quote", "arithmetic", "action"]



def args(argv):
    a = {"input": "/input", "output": "/app/output", "help": False}
    for i, k in enumerate(argv):
        if k in ("-h", "--help"):
            a["help"] = True
        elif k.startswith("--") and i + 1 < len(argv):
            a[k[2:].replace("-", "_")] = argv[i + 1]
    return a


def pdf_text(p):
    try:
        import pypdf
        return "\n".join((g.extract_text() or "") for g in pypdf.PdfReader(str(p)).pages)
    except Exception:
        return ""


def read_text(p):
    """按扩展名抽文本，失败返回空串。"""
    e = p.suffix.lower()
    try:
        if e == ".pdf":
            return pdf_text(p)
        if e in (".docx", ".xlsx", ".pptx"):
            with zipfile.ZipFile(str(p)) as z:
                raw = " ".join(z.read(n).decode("utf-8", "replace") for n in z.namelist()
                               if n.endswith(".xml") and re.search(
                                   r"(document|sheet|slide|sharedStrings)", n))
            return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]{1,300}>", " ", raw))
        return p.read_text(encoding="utf-8", errors="replace")[:400000]
    except Exception:
        return ""


def discover(indir):
    """返回 (files, case, errors, sources)。"""
    files, case, err, srcs = [], {}, [], {}
    root = Path(indir)
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            try:
                if p.is_file() and p.stat().st_size <= 4_000_000:
                    files.append(p)
            except OSError:
                pass
    cj = [p for p in files if p.name.lower() == "case.json"] or \
         [p for p in files if re.match(r"case.*\.json$", p.name.lower())]
    if cj:
        try:
            case = json.loads(cj[0].read_text(encoding="utf-8", errors="replace"))
            if not isinstance(case, dict):
                err.append("%s 非对象" % cj[0].name)
                case = {}
        except Exception as ex:
            err.append("坏 JSON：%s" % str(ex)[:120])
    elif files:
        err.append("无 case.json")
    for p in files[:80]:
        if p.name.lower() == "case.json":
            continue
        t = read_text(p)
        if not t.strip():
            err.append("%s 无文本" % p.name)
            continue
        pool = F.Pool(p.name, "file")
        pool.add(t)
        srcs[p.name] = pool
    return files, case, err, srcs


def mk(cid, v, evd=None, note="", ar=None):
    d = _LIB[cid]
    return {"check_id": cid, "class": d["cls"], "item": d["item"], "basis": d["basis"],
            "severity": d["sev"], "verdict": v, "note": note, "plan": "",
            "action": d["action"], "evidence": evd or [], "arithmetic": ar,
            "needs_human": bool(d["human"]) or (v in ("gap", "partial") and d["sev"] == "major")}


def cap(cid, val, lim, unit, formula, note, evd=None, **kw):
    """val ≤ lim → met，否则 blocked，缺基准 → gap。"""
    ar = {"formula": formula, "inputs": kw, "unit": unit, "right": lim,
          "left": None if val is None else round(val, 4),
          "delta": None if (val is None or lim is None) else round(val - lim, 4)}
    if val is None or lim is None:
        return mk(cid, "gap", [], "缺基准", ar=ar)
    return mk(cid, "met" if val <= lim else "blocked", evd,
              note if val <= lim else "%s；超出 %s %s" % (note, F.fmt(abs(val - lim)), unit),
              ar=ar)


def presence(pl, ids):
    out, p = [], pl["pool"]
    for cid in ids:
        pos = F.probe(p, _LIB[cid]["groups"])
        out.append(mk(cid, "met" if pos is not None else "gap",
                      [F.ev(p, pos)] if pos is not None else [],
                      "" if pos is not None else "未写（≠满足）"))
    return out


def ranges(pl, ctx):
    hi, lo = {}, {}
    for a in ctx["assets"]:
        for r in a["ranges"]:
            d = r["dim"]
            if not d or d == "time":
                continue
            if r["hi"] is not None and (d not in hi or r["hi"] > hi[d]):
                hi[d] = r["hi"]
            if r["lo"] is not None and (d not in lo or r["lo"] < lo[d]):
                lo[d] = r["lo"]
    if not hi and not lo:
        return "gap", None, "无量程"
    for pm in pl["params"]:
        d, v = pm.get("dim"), pm.get("value")
        if not d or v is None or d in ("time", "count", "pct"):
            continue
        b = v * F.UNIT.get(pm.get("unit", ""), (None, 1.0))[1]
        for k, lim in (("hi", hi), ("lo", lo)):
            if d in lim:
                over = b - lim[d] if k == "hi" else lim[d] - b
                if over > 1e-9 * max(1.0, abs(b)):
                    return ("blocked", {"formula": "参数/量程",
                                        "inputs": {"参数": pm["name"],
                                                   "值": "%s %s" % (F.fmt(v), pm["unit"]),
                                                   "边界": F.fmt(lim[d]), "量纲": d},
                                        "left": round(b, 4), "right": lim[d], "unit": d,
                                        "delta": round(over, 4)}, "越量程")
    return "met", None, "量程内"


def chk_res(pl, ctx):
    out, p, A, M = [], pl["pool"], ctx["assets"], ctx["materials"]
    tl = p.text.lower()
    named = [a for a in A if a["name"] and a["name"][:6].lower() in tl]
    st = [a for a in named if a["status"]]
    out.append(mk("R-01", "gap" if not named else ("met" if len(st) == len(named) else "partial"),
                  [F.ev_first(p, [a["name"] for a in named])] if named else [],
                  "无设备清单" if not A else ("未点名" if not named else
                                              "命中 %d/%d/%d"
                                              % (len(named), len(A), len(st)))))
    v, ar, note = ranges(pl, ctx)
    ev2 = [F.ev_first(p, [q["name"] for q in pl["params"]])] if v == "blocked" else []
    out.append(mk("R-02", v, ev2, note, ar=ar))
    out.append(mk("P-02", v, ev2, note, ar=ar))
    used = [m for m in M if m["name"] and m["name"][:6].lower() in tl]
    if not used:
        out.append(mk("R-03", "gap", [], "无试剂或未点名"))
    else:
        ok = all(m["stock"] and m["spec"] for m in used)
        out.append(mk("R-03", "met" if ok else "partial",
                      [F.ev_first(p, [m["name"] for m in used])],
                      "规格与库存齐全" if ok else "部分缺规格/库存"))
    lead = [x["lead"] for x in A + M if x["lead"]]
    out.append(cap("R-04", max(lead) if lead else None, ctx["deadline"], "day",
                   "max(货期) vs 时间窗",
                   "最长货期 %.1f 天" % max(lead) if lead else "",
                   **{"货期天": sorted(set(lead)) if lead else [], "时间窗天": ctx["deadline"]}))
    out.append(mk("P-05", "na", [], "输入无取值域"))
    return out


def chk_time(pl, ctx):
    out, p = [], pl["pool"]
    tot, n = 0.0, 0
    for s in pl["steps"]:
        qs = [q for q in F.quantities(s if isinstance(s, str) else " ".join(map(str,
              s.values()))) if q["dim"] == "time"]
        if qs:
            tot += max(q["base"] for q in qs) / 1440.0
            n += 1
    src = "步骤累加"
    if n < 2:
        lit = [q["base"] for q in F.quantities(p.text) if q["dim"] == "time"]
        tot = (max(lit) / 1440.0) if lit else 0.0
        src = "无步骤"
    out.append(cap("T-02", tot if tot > 0 else None, ctx["deadline"], "day", "总历时 vs 时间窗",
                   "%s %.2f 天" % (src, tot),
                   **{"历时天": round(tot, 3), "口径": src, "时间窗天": ctx["deadline"]}))
    cost, parts, tl = 0.0, [], p.text.lower()
    for m in ctx["materials"]:
        if not m["price"] or not m["name"] or m["name"][:6].lower() not in tl:
            continue
        need = max([1.0] + [q["value"] for _, ln in p.lines
                            if m["name"][:6].lower() in F.norm_txt(ln).lower()
                            for q in F.quantities(ln)
                            if not m["stock"] or q["dim"] == m["stock"]["dim"]])
        cost += m["price"] * need
        parts.append("%s:%s×%s" % (m["name"][:10], F.fmt(m["price"]), F.fmt(need)))
    out.append(cap("T-04", cost if parts else None, ctx["budget"], "currency",
                   "Σ单价×用量 vs 预算", "材料费 %.2f" % cost,
                   **{"明细": parts, "预算": ctx["budget"]}))
    return out


ETH = (("E-01", "human", "人体", ["伦理", "irb", "批件", "审批", "知情同意"]),
       ("E-02", "animal", "动物", ["伦理", "iacuc", "批件", "审批"]),
       ("E-03", "hazard", "危险试剂", ["sds", "ppe", "防护", "废液", "废弃物", "生物安全"]),
       ("E-04", "pdata", "个人或基因数据", ["脱敏", "匿名", "加密", "存储", "共享", "gdpr"]))


def chk_eth(pl, ctx):
    out, p, t = [], pl["pool"], pl["pool"].text + ctx.get("gtext", "")
    for cid, key, cn, need in ETH:
        if not re.search(F.TRIG[key], t, re.I):
            out.append(mk(cid, "na", [], "无关%s" % cn))
            continue
        pos = F.probe(p, [need])
        out.append(mk(cid, "met" if pos is not None else "gap",
                      [F.ev(p, pos)] if pos is not None else [],
                      "%s无措施" % cn if pos is None else "已提及"))
    trig = any(re.search(F.TRIG[k], t, re.I) for k in ("human", "animal", "hazard", "pdata"))
    if not trig:
        out.append(mk("E-05", "na", [], "无触发"))
    else:
        ap = re.search(r"已获批|已批准|批件号|伦理号|approval no", t, re.I)
        pd = re.search(r"在审|已提交|待批|审批中|pending", t, re.I)
        out.append(mk("E-05", "met" if ap else ("partial" if pd else "gap"),
                      [F.ev(p, ap.start())] if ap else [],
                      "审批%s" % (ap or pd).group(0) if (ap or pd) else "未获批"))
    return out


def run_checks(lib, plans, ctx):
    global _LIB
    _LIB = lib
    checks, pres = [], [c for c, v in lib.items() if v["groups"]]
    for pl in plans:
        got = presence(pl, pres) + chk_res(pl, ctx) + chk_time(pl, ctx) + chk_eth(pl, ctx)
        have = {c["check_id"] for c in got}
        for cid in lib:
            if cid not in have:
                got.append(mk(cid, "gap", [], "降级"))
        for c in got:
            c["plan"] = pl["id"]
        checks += got
    return checks


def verdict(checks, plan):
    cnt = {}
    for c in checks:
        cnt[c["verdict"]] = cnt.get(c["verdict"], 0) + 1
    blk = [c for c in checks if c["verdict"] == "blocked"]
    maj = [c for c in checks if c["verdict"] == "gap" and c["severity"] == "major"]
    mnr = [c for c in checks if c["verdict"] == "gap" and c["severity"] == "minor"]
    conds = []
    for c in blk + maj + mnr:
        a = (c.get("action") or "").strip()
        if a and a not in conds:
            conds.append(a)
    den = max(1, len(checks) - cnt.get("na", 0))
    return {"plan": plan, "verdict": "infeasible" if blk else
            ("feasible_with_conditions" if (maj or mnr) else "feasible"),
            "counts": cnt, "coverage": round(cnt.get("met", 0) / den, 3),
            "blocking": [{"check_id": c["check_id"], "item": c["item"], "note": c["note"]}
                         for c in blk],
            "conditions": conds, "n_checks": len(checks), "n_blocked": len(blk),
            "n_major_gap": len(maj),
            "score": round((cnt.get("met", 0) + 0.5 * cnt.get("partial", 0)) / den * 100, 1)}


def fill_contract(res, contract):
    back = {}
    for k, v in (contract or {}).items():
        d = [] if isinstance(v, list) else ({} if isinstance(v, dict) else None)
        if k not in res:
            res[k] = d
        back[k] = "default" if res[k] == d else "filled"
    res["contract_backfill"] = back
    return res


def csvl(rows):
    return "\n".join(",".join('"%s"' % str(c).replace('"', "'").replace("\n", " ")
                              for c in r) for r in rows) + "\n"


def run(a):
    out = Path(a["output"])
    out.mkdir(parents=True, exist_ok=True)
    files, case, errs, srcs = discover(a["input"])
    ct = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    res = {"case_id": case.get("case_id") or case.get("id") or "unknown", "status": "partial",
           "task": {}, "checks": [], "gaps": [], "pending_human": [], "uncertainty": [],
           "sources": [], "errors": list(errs),
           "summary": {"stage": "partial"},
           "runtime": {"skill_version": F.VERSION}}

    def save():
        (out / "result.json").write_text(
            json.dumps(fill_contract(res, ct), ensure_ascii=False, indent=1), "utf-8")
    save()
    try:
        cp = F.Pool("case.json", "case")
        for ptr, k, v in F.walk(case):
            if isinstance(v, str):
                cp.add("%s: %s" % (k, v) if isinstance(k, str) else v, ptr)
        res["sources"] = [{"source_id": "case.json", "kind": "json", "chars": len(cp.text),
                           "scheme": "JSON Pointer"}] + \
            [{"source_id": k, "chars": len(v.text)} for k, v in srcs.items()]
        lib, libsrc = F.load_lib(Path(__file__).resolve().parent)
        ctx = F.harvest(case)
        ctx["gtext"] = " ".join([cp.text] + [v.text for v in srcs.values()])[:200000]
        plans = F.build_plans(case, cp, srcs)
        checks = run_checks(lib, plans, ctx)
        rows = [verdict([c for c in checks if c["plan"] == p["id"]], p["id"]) for p in plans]
        best = min(rows, key=lambda r: (len(r["blocking"]), -r["score"],
                                        len(r["conditions"]), r["plan"]))
        mp = next(p for p in plans if p["id"] == best["plan"])
        res["task"] = {"goal": str(case.get("goal") or case.get("研究目标") or "")[:300]}
        res["plans"], res["checks"] = rows, checks
        res["recommended"] = best["plan"]
        res["gaps"] = [{"class": c["class"], "check_id": c["check_id"], "item": c["item"],
                        "supply": c["action"], "plan": c["plan"]}
                       for c in checks if c["verdict"] == "gap"]
        res["pending_human"] = [{"check_id": c["check_id"], "plan": c["plan"],
                                 "item": c["item"], "why": c["note"] or "待定",
                                 "action": c["action"]}
                                for c in checks if c["needs_human"]]
        res["uncertainty"] = [{"check_id": c["check_id"], "note": c["note"],
                               "basis": (c["arithmetic"] or {}).get("formula")}
                              for c in checks if c["arithmetic"] and c["note"]
                              and c["verdict"] != "met"][:40]
        res["resource_rows"] = F.resource_rows(ctx)
        res["param_rows"] = [[q["name"][:34], F.fmt(q["value"]), q["unit"] or "—",
                              (q["range"] or "—")[:24]] for q in mp["params"]]
        miss = [k for k in ("deadline", "budget") if ctx[k] is None]
        if miss:
            res["uncertainty"].append({"issue": "未给 %s" % "/".join(miss),
                                       "impact": "降级"})
        res["status"] = ("input_error" if (errs and not case) else "ok" if (checks and case)
                         else "insufficient_evidence" if not checks else "partial")
        res["summary"] = {"plans": len(rows), "recommended": best["plan"],
                          "verdict": best["verdict"], "coverage": best["coverage"],
                          "counts": {k: sum(r["counts"].get(k, 0) for r in rows)
                                     for k in ("met", "partial", "gap", "blocked", "na")},
                          "blocking": best["blocking"], "conditions": best["conditions"],
                          "gaps": sum(1 for c in checks if c["verdict"] == "gap"),
                          "checks_total": len(checks), "lib_source": libsrc}
        res["runtime"].update({"lib_source": libsrc, "plans": len(plans),
                               "sources": len(res["sources"]),
                               "deadline_src": ctx["deadline_src"],
                               "budget_src": ctx["budget_src"]})
        q = lambda c: (c["evidence"] or [{}])[0]
        ev = {c["check_id"]: q(c).get("quote", "") for c in checks if c["plan"] == best["plan"]}
        for k, v in (("feasibility", best), ("anomaly", res["uncertainty"]),
                     ("comparison", {"recommended": best["plan"],
                                     "ranking": [r["plan"] for r in rows]}),
                     ("variables", {"iv": ev.get("H-02", ""), "dv": ev.get("H-03", "")}),
                     ("validation", {"criteria": ev.get("H-04", ""),
                                     "stopping": ev.get("K-06", "")})):
            if not res.get(k):
                res[k] = v
        rr = [c for c in checks if c["class"] == "RISK" and c["plan"] == best["plan"]]
        res["risks"] = [{"mode": c["item"], "status": c["verdict"],
                         "trigger": q(c).get("quote", ""),
                         "mitigation": q(c).get("quote", "") or c["action"],
                         "escalation": "转 PI", "locator": q(c).get("locator", "")}
                        for c in rr]
        art = {"protocol.md": F.protocol_md(res),
               "risk_table.csv": csvl([RH] + [[i, c["item"], c["verdict"], q(c).get("quote", ""),
                   q(c).get("quote", "") or c["action"],
                   "" if c["verdict"] == "met" else "需补", "转 PI",
                   q(c).get("locator", "")] for i, c in enumerate(rr, 1)]),
               "check_matrix.csv": csvl([CH] + [[
                   c["check_id"], c["plan"], c["class"], c["item"], c["severity"], c["verdict"],
                   c["basis"], c["needs_human"], q(c).get("locator", ""), q(c).get("quote", ""),
                   ("%s=%s" % ((c["arithmetic"] or {}).get("formula", ""),
                               (c["arithmetic"] or {}).get("left", "")))
                   if c["arithmetic"] else "", c["action"]] for c in checks])}
        outs = {}
        for n, txt in art.items():
            (out / n).write_text(txt, "utf-8")
            outs[n] = str(out / n)
        res["artifacts"] = outs
        res["selftest"] = {"checks": len(checks), "contract_missing": [k for k in ct
                                                                      if k not in res],
                           "artifacts_missing": [n for n in outs
                                                 if not Path(outs[n]).exists()],
                           "classes": sorted({c["class"] for c in checks})}
    except Exception as ex:
        res["errors"].append("pipeline %s" % str(ex)[:180])
    finally:
        res["runtime"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        res["runtime"]["elapsed_sec"] = round(time.time() - T0, 2)
        try:
            save()
        except OSError as ex:
            print("err")
        print("%s %s checks=%d %.1fs"
              % (res.get("case_id"), res.get("status"), len(res.get("checks") or []), time.time() - T0))


def main(argv):
    a = args(argv)
    if a["help"]:
        print(HELP)
        return 0
    try:
        run(a)
    except Exception as ex:
        print("degraded: %s" % str(ex)[:180])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
