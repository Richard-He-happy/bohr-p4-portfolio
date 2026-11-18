#!/usr/bin/env python3
"""experiment-05: interpret measured experimental data into five verifiable sections and write
result.json with the output_contract backfilled plus protocol.md and CSV tables. Stdlib only,
offline, CWD independent, exit code always 0, partial result written first."""
import argparse, csv, json, os, re, sys, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis import CFG, analyse, causes, pnum, unit_of

T0 = time.time()
SKILL, VERSION = "experiment-result-anomaly-explainer", "1.0.0"
IO = dict(rows=4000, sheets=24, files=200, mb=8)
def sniff(p, h):
    if h[:4] == b"%PDF":
        return "pdf"
    if h[:2] == b"PK":
        try:
            return "xlsx" if any(x[:3] == "xl/" for x in zipfile.ZipFile(p).namelist()) else "docx"
        except Exception:
            return "zip"
    e = p.suffix.lower().lstrip(".")
    return "table" if e in ("csv", "tsv", "txt", "dat", "prn") else "xlsx" if e in ("xlsx", "xlsm") else "text"
def rtext(p):
    raw = p.read_bytes()[: IO["mb"] * 1048576]
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        if e:
            try:
                return raw.decode(e)
            except Exception:
                pass
    return raw.decode("utf-8", "replace")
def tgrid(txt):
    lines = [l for l in txt.splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    d = max((",", "\t", ";", "|"), key=lines[0].count)
    return [("", [l.split(d) if d in l else re.split(r"\s{2,}", l.strip()) for l in lines])]
def xlsx(p):
    N = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    out = []
    with zipfile.ZipFile(p) as z:
        nm = z.namelist()
        ss = ["".join(t.text or "" for t in si.iter() if t.tag.endswith("}t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml"))] if "xl/sharedStrings.xml" in nm else []
        for k, tgt in enumerate(sorted(y for y in nm if y.startswith("xl/worksheets/sheet"))[: IO["sheets"]]):
            g = []
            for row in ET.fromstring(z.read(tgt)).iter():
                if row.tag != N + "row":
                    continue
                c = {}
                for cell in row:
                    if cell.tag != N + "c":
                        continue
                    col = 0
                    for ch in re.sub(r"\d", "", cell.get("r") or ""):
                        col = col * 26 + ord(ch) - 64
                    iv = cell.find(N + "v")
                    v = "" if iv is None else (iv.text or "")
                    if cell.get("t") == "s" and v.strip().isdigit():
                        v = ss[int(v)] if int(v) < len(ss) else ""
                    c[max(col - 1, 0)] = v
                if c:
                    g.append([c.get(x, "") for x in range(max(c) + 1)])
            if g:
                out.append(("sheet:第%d表" % (k + 1), g))
    return out
def find_dir(ex, env, dflt):
    for x in ([Path(ex)] if ex else []) + ([Path(os.environ[env])] if os.environ.get(env) else []) + \
            [Path(d) for d in dflt]:
        try:
            if x.is_dir():
                return x.resolve()
        except Exception:
            pass
    return None
def ljson(p):
    try:
        return json.loads(rtext(p))
    except Exception:
        return None
def norm(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())
def nfind(o, want, d=0):
    if d > 3:
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if norm(k) in want and v not in (None, "", [], {}):
                return v
    for v in (o.values() if isinstance(o, dict) else o[:8] if isinstance(o, list) else []):
        r = nfind(v, want, d + 1)
        if r not in (None, "", [], {}):
            return r
    return None
def find_case(ind, errs):
    if ind is None:
        return None
    p = ind / "case.json"
    if p.is_file():
        d = ljson(p)
        if isinstance(d, dict):
            return d
        errs.append({"stage": "case", "detail": "case.json unparsable"})
    return None
def discover(ind):
    recs = []
    if ind is None:
        return recs
    for p in sorted(ind.rglob("*")):
        if len(recs) >= IO["files"]:
            break
        if not p.is_file() or p.name in ("case.json", "task.md", "material.json"):
            continue
        try:
            with p.open("rb") as f:
                h = f.read(16)
            recs.append({"path": p, "rel": str(p.relative_to(ind)), "kind": sniff(p, h), "bytes": p.stat().st_size})
        except Exception:
            continue
    return recs
def mktable(sid, rel, loc, grid):
    g = [list(r) for r in grid if any(str(c).strip() != "" for c in r)]
    if len(g) < 2:
        return None
    nc = max(len(r) for r in g)
    g = [r + [""] * (nc - len(r)) for r in g]
    h = 0
    while h < min(6, len(g)) and sum(1 for c in g[h] if str(c).strip()) < 2:
        h += 1
    if h >= len(g) - 1:
        return None
    hdr, f = g[h], [c for c in g[h] if str(c).strip()]
    if f and sum(1 for c in f if pnum(c) is not None) > len(f) / 2:
        cols, data = ["col%d" % (i + 1) for i in range(nc)], g[h:]
    else:
        cols = [(re.sub(r"\s+", " ", str(c)).strip() or "col%d" % (i + 1))[:60] for i, c in enumerate(hdr)]
        data = g[h + 1:]
    seen, names = {}, []
    for nm in cols:
        seen[nm] = seen.get(nm, 0) + 1
        names.append(nm if seen[nm] == 1 else "%s#%d" % (nm, seen[nm]))
    data = data[: IO["rows"]]
    kind = []
    for i in range(nc):
        ne = [r[i] for r in data if str(r[i]).strip()]
        nn = [v for v in ne if pnum(v) is not None]
        kind.append("empty" if not ne else "num" if len(nn) >= 2 and len(nn) * 10 >= 7 * len(ne) else "cat")
    return {"sid": sid, "rel": rel, "loc": loc, "cols": names, "rows": data, "rowbase": h + 2, "kind": kind}

RECHECK = [("short_reps", "P2", "补平行至 n>=3 记 CV", "replicate_short", "组内 CV 可算",
            "CV 在范围内", "CV 偏大，查加样"),
           ("clipping", "P1", "稀释或降增益重测封顶点并记倍数", "clip", "重测落量程中部",
            "与倍数一致即饱和", "仍极值即真实高值"),
           ("batch", "P1", "插质控样比其它批", "binding", "质控样批间差<允差",
            "确认批/通道偏差", "排除系统偏差"),
           ("no_control", "P2", "补空白/阴性对照", "design", "对照稳定",
            "可作基线", "对照波动大")]
def recheck(ctx):
    out, T = [], ctx["tags"]
    f0 = ctx["anomalies"][0]["file"] if ctx["anomalies"] else ""

    def st(pr, act, f, fld, cond, ok, no, eff):
        out.append({"id": "R%02d" % (len(out) + 1), "priority": pr, "action": act, "file": f, "field": fld,
                    "condition": cond, "if_confirmed": ok, "if_refuted": no, "effort": eff})
    for x in [y for y in ctx["anomalies"] if y["type"] in ("outlier", "oos_limit")][:6]:
        st("P1", "回查导出/单位/限度口径", x["file"], x["locator"],
           "导出值=表中值；单位 %s" % (unit_of(x.get("metric") or "") or "见表头"),
           "真实读数，转原因复核", "录入错误，改正后重跑", "10 min")
    for key, pr, act, fld, cond, ok, no in RECHECK:
        if key in T:
            st(pr, act, f0, fld, cond, ok, no, "1 批")
    if not out:
        st("P2", "抽 5 行按原始记录复算", f0, "trend", "复算一致", "结论可核", "有偏差需修", "30 min")
    return out

NEXT = [("batch", "区组随机化批次/通道并插质控", "区分批次偏差", "批次混杂"),
        ("short_reps", "每组重复提到 n>=3", "尺度需 n>=3", "重复不足"),
        ("clipping", "设稀释系列覆盖量程中段", "防封顶", "量程/饱和"),
        ("no_control", "每板加空白/阴性对照", "建基线", "无对照"),
        ("magnitude", "同列输出单位", "消除单位歧义", "单位不一")]
def nxt(ctx):
    out = [{"id": "N%d" % (i + 1), "change": c, "rationale": w, "closes_gap": g, "relative_cost": "中"}
           for i, (k, c, w, g) in enumerate([r for r in NEXT if r[0] in ctx["tags"]])]
    for t in [x for x in ctx["trend"] if x.get("breakpoint")][:2]:
        out.append({"id": "N%d" % (len(out) + 1), "change": "x≈%s 加密采样" % t["breakpoint"]["x"],
                    "rationale": "拐点采样稀疏", "closes_gap": "拐点不确定", "relative_cost": "中"})
    if not out:
        out.append({"id": "N1", "change": "扩大样本量", "rationale": "未检出异常但区间宽",
                    "closes_gap": "样本量", "relative_cost": "中"})
    return out

CONFIRM = [("设备可用性", "量程/状态待核"), ("安全", "SOP 负责人确认"),
           ("伦理", "涉人畜需批件"), ("专家确认", "结论须复核")]

def protocol(ctx, case):
    C = ctx["causes"][:3]
    eq, ma = [], []
    if isinstance(case, dict):
        for k in ("equipment", "instruments", "reagents", "materials"):
            for it in (case.get(k) if isinstance(case.get(k), list) else [])[:6]:
                (eq if k in ("equipment", "instruments") else ma).append(
                    str(it.get("name") or it)[:80] if isinstance(it, dict) else str(it)[:80])
    return {"hypotheses": [{"id": "H%d" % (i + 1), "statement": "异常源自「%s」" % c["candidate"], "tested_by": c["test"],
                            "supported_if": c["supported_if"], "refuted_if": c["refuted_if"]} for i, c in enumerate(C)],
            "variables": {"independent": [c["candidate"] for c in C[:2]],
                          "dependent": [t["metric"] for t in ctx["trend"][:4]],
                          "controlled": ["批次", "通道", "操作者", "上样顺序"]},
            "controls": [{"control": "空白/基质空白"}, {"control": "同批质控样"}],
            "steps": [{"step": s["action"], "target": s["field"]} for s in ctx["recheck"][:5]],
            "parameters": ctx["thresholds"], "materials": ma, "equipment": eq,
            "schedule": ["%s: %s" % (k, case[k]) for k in ("time", "budget", "personnel")
                         if isinstance(case, dict) and case.get(k)],
            "reading_criteria": [{"criterion": "|z|<%.1f" % CFG["z"]}, {"criterion": "CV<%.0f%%" % CFG["cv"]},
                                 {"criterion": "n>=%d" % CFG["reps"]}],
            "risks": [{"risk": "波动误判为异常", "trigger": "阈值不匹配", "mitigation": "补重复重算尺度"},
                      {"risk": "归错对象", "trigger": "键自动选择", "mitigation": "核对分组键/记录"}],
            "confirmations": [{"item": k, "status": "unconfirmed", "need": v} for k, v in CONFIRM],
            "basis": ([{"choice": "异常定位", "source": x["file"], "locator": x["locator"], "quote": x["quote"]}
                       for x in ctx["anomalies"][:1]] +
                      [{"choice": "阈值", "source": "scripts/analysis.py#CFG",
                        "quote": "z=%.1f cv=%.0f n=%d" % (CFG["z"], CFG["cv"], CFG["reps"])}]),
            "gold_standard": "原始导出+同批对照+验证文件"}

_ALIAS = ("summary:summary conclusion 结论|trend:trend 趋势|anomalies:anomalies outliers 异常|"
          "causes:causes reasons 原因|recheck:recheck 复核|next_experiment:nextexperiment next 后续|"
          "protocol:protocol plan 方案|risks:risks 风险|validation:validation 判据|feasibility:feasibility 可行性|"
          "hypotheses:hypotheses 假设|variables:variables 变量|controls:controls 对照|"
          "materials:materials 材料|equipment:equipment 设备|sources:sources 来源|"
          "uncertainty:uncertainty 不确定")
SLOT = {}
for _seg in _ALIAS.split("|"):
    _k, _v = _seg.split(":", 1)
    for _n in _v.split():
        SLOT[norm(_n)] = _k
def fillc(c, P):
    if isinstance(c, dict):
        o = {}
        for k, v in c.items():
            s = SLOT.get(norm(k))
            if s and P.get(s) not in (None, [], {}):
                o[k] = P[s]
            else:
                o[k] = fillc(v, P) if isinstance(v, (dict, list)) else (v if v not in (None, "") else None)
        return o
    if isinstance(c, list):
        return [P.get(SLOT.get(norm(it.get("name") or it.get("field") or it.get("key") or "")), None)
                or fillc(it.get("schema") or it, P) for it in c if isinstance(it, dict)]
    s = SLOT.get(norm(c)) if isinstance(c, str) else None
    return P.get(s) if s and P.get(s) not in (None, [], {}) else None
def wjson(p, o):
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
def pmd(res):
    p = res["protocol"]
    s = ["# 方案 %s" % res["case_id"], "", "## 假设"]
    s += ["- %s %s｜验证 %s" % (h["id"], h["statement"], h["tested_by"]) for h in p["hypotheses"]] or ["- 无"]
    s += ["", "## 变量与对照", "- IV %s｜DV %s" % ("、".join(p["variables"]["independent"]),
                                               "、".join(p["variables"]["dependent"]) or "见趋势"),
          "- 控制 %s｜对照 %s" % ("、".join(p["variables"]["controlled"]), "、".join(c["control"] for c in p["controls"])),
          "", "## 步骤"] + ["- %s → %s" % (x["step"], x["target"]) for x in p["steps"]]
    s += ["", "## 判据 " + "；".join(c["criterion"] for c in p["reading_criteria"]),
          "", "## 依据"] + ["- %s：%s" % (b["choice"], b.get("locator") or b["source"]) for b in p["basis"]]
    s += ["", "## 确认项"] + ["- %s:%s" % (c["item"], c["status"]) for c in p["confirmations"]]
    s += ["", "## 风险"] + ["- %s｜处置 %s" % (r["risk"], r["mitigation"]) for r in p["risks"]]
    s += ["", "## 缺口"] + ["- %s" % u for u in res["uncertainty"]]
    return "\n".join(s) + "\n"

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py",
                                 description="Interpret experimental data into five verifiable sections (trend, "
                                             "anomalies, causes, recheck, next round); write result.json with the "
                                             "output_contract backfilled, plus protocol.md and CSV. Exit code 0.")
    ap.add_argument("--input", help="input dir with case.json + artifacts")
    ap.add_argument("--output", help="output dir")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args(argv)
    out = Path(a.output) if a.output else (find_dir(None, "OUTPUT_DIR", ["/app/output", "/bohr-workspace/output"])
                                           or (Path.cwd() / "output"))
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        out = Path.cwd()
    errs, pend, tables, sources = [], [], [], []
    ind = find_dir(a.input, "INPUT_DIR", ["/input", "/bohr-workspace/input"])
    if ind is None:
        errs.append({"stage": "input", "detail": "no input dir"})
    case = find_case(ind, errs) or {}
    res = {"case_id": str(case.get("case_id") or case.get("id") or "UNKNOWN"), "status": "partial",
           "skill": {"name": SKILL, "version": VERSION}, "summary": "partial", "output_contract": {},
           "errors": errs, "pending_human": pend, "degradations": [],
           "changes": [{"version": VERSION, "note": "partial"}]}
    wjson(out / "result.json", res)
    for i, r in enumerate(discover(ind)):
        src = {"id": "S%02d" % (i + 1), "file": r["rel"], "kind": r["kind"], "bytes": r.get("bytes")}
        try:
            if r["kind"] in ("xlsx", "table", "text"):
                for loc, g in (xlsx(r["path"]) if r["kind"] == "xlsx" else tgrid(rtext(r["path"]))):
                    t = mktable(src["id"], r["rel"], loc, g)
                    if t:
                        tables.append(t)
                src["parsed"] = "workbook" if r["kind"] == "xlsx" else "delimited"
            else:
                src["parsed"] = "not-read"
                pend.append({"item": r["rel"], "reason": "%s 未解析，需人工给数值" % r["kind"]})
        except Exception as e:
            errs.append({"stage": "parse", "file": r["rel"], "detail": str(e)[:160]})
            src["parsed"] = "error"
        sources.append(src)
    ctx = analyse(tables, errs)
    ctx["causes"], ctx["recheck"] = causes(ctx), recheck(ctx)
    proto, grp = protocol(ctx, case), ctx["groups"][:10]
    nA = len([x for x in ctx["anomalies"] if x["type"] in ("outlier", "series_outlier")])
    st = ("input_error" if ind is None else "insufficient_evidence" if not tables
          else "partial" if (errs or pend) else "ok")
    res.update({"topic": str(case.get("topic") or ""), 
                "goal": str(nfind(case, {"goal", "objective", "question"}) or ""), "status": st,
                "trend": ctx["trend"][:16], "anomalies": ctx["anomalies"], "causes": ctx["causes"],
                "recheck": ctx["recheck"], "next_experiment": nxt(ctx), "protocol": proto,
                "hypotheses": proto["hypotheses"], "variables": proto["variables"], "controls": proto["controls"],
                "materials": proto["materials"], "equipment": proto["equipment"], "schedule": proto["schedule"],
                "parameters": ctx["thresholds"], "risks": proto["risks"], "groups": grp,
                "validation": {"criteria": proto["reading_criteria"], "gold_standard": proto["gold_standard"]},
                "sources": sources, "binding": ctx["binding"],
                "artifacts": ["result.json"]})
    res["counts"] = {"files": len(sources), "tables": len(tables), "anomalies": len(res["anomalies"]), "confirmed": nA, "causes": len(res["causes"]),
                     "recheck": len(res["recheck"]), "next": len(res["next_experiment"]),
                     "gaps": len(pend), "errors": len(errs)}
    res["uncertainty"] = ["阈值 |z|≥%.1f 为默认值，未经方法验证校准" % CFG["z"],
                          "分组键自动选择，需核对 groups[].key",
                          "原因为候选，非结论",
                          "图像/PDF 未读数"]
    res["feasibility"] = {"data_sufficient": bool(tables) and bool(res["trend"] or res["anomalies"]),
                          "blocking": [] if tables else ["无数值表"]}
    res["summary"] = ("%s：%d 文件/%d 表；异常 %d、趋势 %d、原因 %d、复核 %d、后续 %d；%s" %
                      (res["case_id"], len(sources), len(tables), nA, len(res["trend"]), len(res["causes"]),
                       len(res["recheck"]), len(res["next_experiment"]), st))
    try:
        (out / "protocol.md").write_text(pmd(res), encoding="utf-8")
        res["artifacts"].append("protocol.md")
    except Exception as e:
        errs.append({"stage": "emit", "detail": "protocol.md: %s" % str(e)[:120]})
    for fn, keys in (("anomaly_table.csv", ["id", "type", "verdict", "object", "metric", "value",
                                            "reference", "dev_pct", "robust_z", "n_ref", "batch",
                                            "file", "locator", "quote"]),
                     ("recheck_checklist.csv", ["id", "priority", "action", "file", "field", "condition",
                                                "if_confirmed", "if_refuted", "effort"]),
                     ("risk_table.csv", ["risk", "trigger", "mitigation", "alternative"])):
        src = res["anomalies"] if fn[0] == "a" else res["recheck"] if "check" in fn else res["risks"]
        try:
            with (out / fn).open("w", encoding="utf-8-sig", newline="") as fh:
                wr = csv.writer(fh)
                wr.writerow(keys)
                for r in src:
                    wr.writerow(["" if r.get(k) is None else r.get(k) for k in keys])
            res["artifacts"].append(fn)
        except Exception as e:
            errs.append({"stage": "csv", "file": fn, "detail": str(e)[:100]})
    filled = fillc(case.get("output_contract") or nfind(case, {"outputcontract"}), res)
    res["output_contract"] = filled or {}
    for k, v in (filled or {}).items():
        if k not in res:
            res[k] = v
    el = round(time.time() - T0, 2)
    res["runtime"] = {"elapsed_s": el, "budget_s": 900, "within_budget": el < 780}
    wjson(out / "result.json", res)
    print("%s %s %d %d" % (out / "result.json", st, len(tables), nA))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("degraded: %s" % exc)
        sys.exit(0)
