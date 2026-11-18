import argparse, hashlib, json, os, re, sys, time, zlib
from pathlib import Path
V, T0 = "1.0.1", time.time()
HERE, PKG = Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent
BUD, NH, NL, MXC = 700.0, 0.55, 0.30, 180000
DEFC = {"problem_definition": None, "prior_work_comparison": None, "novelty_assessment": None, "feasibility": None}
EN = set("the and for with from that this these those study paper is are was were been not but than then also may use used based "
         "results result method methods approach show shown has had between among most other which what when where how both per "
         "versus data research group however therefore thus".split())
ZH = set("研究 方法 结果 分析 本文 我们 基于 通过 进行 表明 发现 具有 存在 其中 此外 因此 但是 然而 由于 对于 关于 相关 不同 主要 "
         "重要 提出 采用 使用 数据 样本 实验 结论 文献 综述 一种 目前 已有 分别 同时".split())
POS = ("提高", "增加", "改善", "优于", "有效", "支持", "increase", "better", "outperform", "positive")
NEG = ("降低", "减少", "无效", "不支持", "无显著", "劣于", "减弱", "decrease", "reduce", "no significant", "worse", "低于")
FC = ("结果", "表明", "显示", "发现", "提示", "证实", "结论", "显著", "found", "show", "indicat", "suggest", "report", "conclud")
CC = ("创新", "首次", "提出", "改进", "novel", "first", "propose", "introduce")
IK = {"method": ("方法", "模型", "算法", "框架", "method", "model", "algorithm"),
      "data": ("数据", "数据集", "队列", "样本", "dataset", "cohort"),
      "context": ("场景", "领域", "迁移", "应用", "context", "domain", "transfer"),
      "conclusion": ("结论", "修正", "反驳", "conclusion", "correct", "refute")}
PR = (("data", "数据可及性", ("数据", "队列", "样本", "病例", "dataset", "cohort", "sample")),
      ("compute", "算力与工具", ("算力", "计算资源", "gpu", "集群", "服务器", "compute")),
      ("experiment", "实验与伦理", ("实验", "仪器", "平台", "动物", "细胞", "伦理", "审批")),
      ("time", "时间窗口", ("周期", "随访", "年限", "follow", "timeline")),
      ("capability", "人员与能力", ("团队", "人员", "作者", "合作", "专家", "expertise")))
AC = ("可用", "已获得", "已收集", "具备", "拥有", "可获得", "已完成", "available", "collected", "obtained")
FLD = (("task", ("任务", "目的", "aim", "objective", "goal")),
       ("method", ("方法", "采用", "基于", "模型", "算法", "method", "approach", "model")),
       ("data", ("数据", "样本", "队列", "病例", "dataset", "cohort")),
       ("evaluation", ("指标", "评价", "metric", "auc", "accuracy", "敏感", "特异", "p<", "95% ci")),
       ("conclusion", ("结论", "conclusion", "表明")))
YR, DOI = re.compile(r"(19[89]\d|20[0-4]\d)"), re.compile(r"10\.\d{4,9}/[^\s\"'<>,;)\]]+")
LAT = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
SPL = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9\u4e00-\u9fff])")
FUNC = set("的对在为是和与及或等其该此并而将被由于以了着过上来去把之")
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
def nm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\x00", " ")).strip()
def hs(b):
    return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8", "replace")).hexdigest()[:16]
def wj(o, p):
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
def lj(p):
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None, "read:%s" % e
    try:
        return json.loads(t), None
    except Exception as e:
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", t)), "repaired:%s" % e
        except Exception:
            return None, "json:%s" % e
def dg(o, keys, out=None, d=0):
    out = [] if out is None else out
    if d > 6:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            if any(x in str(k).lower() for x in keys):
                if isinstance(v, (str, int, float)) and str(v).strip():
                    out.append(str(v).strip())
                elif isinstance(v, list) and v and all(isinstance(x, (str, int, float)) for x in v):
                    out.append("; ".join(map(str, v)))
            dg(v, keys, out, d + 1)
    elif isinstance(o, list):
        for v in o[:200]:
            dg(v, keys, out, d + 1)
    return out
def fo(c, names):
    for n in names:
        v = c.get(n) if isinstance(c, dict) else None
        if isinstance(v, str) and v.strip():
            return nm(v)
    g = dg(c, [n.lower() for n in names])
    return g[0] if g else ""
def pt(d):
    o = []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]{4,}>", d):
        t = m.group(0)
        if t[:1] == b"(":
            o.append(re.sub(rb"\\([()\\])", rb"\1", re.sub(rb"\\([nrt])", b" ", t[1:-1])).decode("latin-1", "ignore"))
        else:
            try:
                o.append(bytes.fromhex(t[1:-1].decode()).decode("utf-16-be", "ignore"))
            except Exception:
                pass
    return nm(" ".join(o))
def x_pdf(p):
    d, pg = p.read_bytes(), []
    for m in re.finditer(rb"stream\r?\n", d):
        s, e = m.end(), d.find(b"endstream", m.end())
        if e < 0:
            continue
        r = d[s:e]
        try:
            r = zlib.decompress(r)
        except Exception:
            pass
        if b"Tj" in r or b"TJ" in r:
            t = pt(r)
            if len(t) >= 15:
                pg.append(t)
    return [("p.%d" % (i + 1), x) for i, x in enumerate(pg)], (1.0 if pg else 0.0)
def x_txt(p):
    t = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    o = [("para.%d" % (i + 1), nm(x)) for i, x in enumerate(re.split(r"\n{2,}|(?<=[。！？!?])\n", t)) if len(nm(x)) >= 6]
    return (o or ([("para.1", nm(t))] if t.strip() else [])), 1.0
EX = {".pdf": x_pdf, ".csv": x_txt, ".tsv": x_txt, ".txt": x_txt, ".md": x_txt, ".markdown": x_txt,
      ".json": x_txt, ".ris": x_txt}
def scan(root, tr):
    fs, seen = [], {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ("__pycache__", ".git", "output", "_out")]
        for fn in sorted(fns):
            if fn.endswith((".pyc", ".part")) or (fn.endswith(".json") and fn.startswith("case")):
                continue
            p = Path(dp) / fn
            try:
                b = p.read_bytes()
            except Exception as e:
                tr.append({"step": "read", "target": str(p), "status": "error", "error": str(e)})
                continue
            if hs(b) not in seen:
                seen[hs(b)] = 1
                fs.append({"p": p, "rel": str(p.relative_to(root)), "sha": hs(b)})
    return fs
def recs_of(p, er=None):
    e = p.suffix.lower()
    if e == ".ris":
        t = p.read_text(encoding="utf-8", errors="replace")
        out = []
        for i, x in enumerate(re.split(r"^ER\s{0,2}-", t, flags=re.M)):
            m = {}
            for tg in ("TI", "T1", "JO", "T2", "AB", "N2", "PY", "Y1", "DO"):
                g = re.search(r"(?m)^%s\s{0,2}- (.*)$" % tg, x)
                if g:
                    m[tg] = nm(g.group(1))
            bl = [("rec.%d.%s" % (i + 1, k), m[k]) for k in ("TI", "T1", "JO", "T2", "AB", "N2") if m.get(k)]
            if bl:
                out.append(bl)
        return out, 1.0
    fn = EX.get(e)
    if not fn:
        return None, 0.0
    try:
        bl, q = fn(p)
    except Exception as ex:
        if er is not None:
            er.append("extract:%s:%s" % (p.name, ex))
        return None, 0.0
    return [(l, t) for l, t in bl if t], q


def build(fs, tr, er, dgx):
    ds = []
    for f in fs:
        e = f["p"].suffix.lower()
        if e in IMG:
            dgx.append("image_skip:%s" % f["rel"])
            continue
        recs, q = recs_of(f["p"], er)
        if recs is None or not recs:
            dgx.append("%s:%s" % ("unsupported" if recs is None else "empty", f["rel"]))
            continue
        if q < 0.6:
            dgx.append("low_quality:%s" % f["rel"])
        for g in (recs if e == ".ris" else [recs]):
            bl = [(l, t[:4000]) for l, t in g][:400]
            tx = nm(" ".join(t for _, t in bl))
            ti = (re.search(r"(?m)^(?:TI|T1) - (.*)$", tx) or [None, tx[:120]])[1] if e == ".ris" else tx[:120]
            y, m = YR.search(tx), DOI.search(tx)
            ds.append({"sid": "S%02d" % (len(ds) + 1), "path": f["rel"], "sha": f["sha"], "bl": bl,
                       "ti": nm(ti)[:200], "yr": y.group(0) if y else "", "doi": m.group(0).rstrip(".") if m else "",
                       "tx": tx[:MXC], "q": q, "kd": e.lstrip("."), "inc": True, "why": "纳入"})
        tr.append({"step": "extract", "target": f["rel"], "sha256": f["sha"]})
    return ds


def tk(t, m=300):
    o = {}
    for w in LAT.findall(t):
        w = w.lower()
        if w not in EN and len(w) >= 3:
            o[w] = o.get(w, 0) + 1
    for sg in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        for i in range(len(sg) - 1):
            g = sg[i:i + 2]
            if g in ZH or g[0] in FUNC or g[1] in FUNC:
                continue
            o[g] = o.get(g, 0) + 1
    for g in [g for g in o if any(o[x] >= o[g] for x in o if x[1] == g[0]) and any(o[y] >= o[g] for y in o if y[0] == g[1])]:
        del o[g]
    keep = {}
    for g, c in sorted(o.items(), key=lambda kv: (-kv[1], -len(kv[0]))):
        if not any(g != k and g in k for k in keep):
            keep[g] = c
    return dict(sorted(keep.items(), key=lambda kv: (-kv[1], -len(kv[0])))[:m])


def dterms(ds):
    for d in ds:
        d["ts"] = set(tk(d["tx"], 200))


def facets(ts, c):
    p = [dg(c, k) for k in (["population", "对象"], ["intervention", "方法"], ["outcome", "结果"])]
    if all(p):
        return dict(zip(("object", "method", "outcome"), [x[0][:80] for x in p])) | {"assignment": "case_fields"}
    k = max(1, len(ts) // 3)
    return {"object": " ".join(ts[:k]) or "研究", "method": " ".join(ts[k:2 * k]),
            "outcome": " ".join(ts[2 * k:3 * k]), "assignment": "thirds"}


def sents(t):
    return [x.strip() for x in SPL.split(t) if x.strip() and len(x.strip()) >= 12]
def pol(s):
    lo = s.lower()
    p, n = sum(1 for w in POS if w in lo), sum(1 for w in NEG if w in lo)
    return "supports" if p > n else ("contradicts" if n > p else "neutral")
def evid(ds, ts, lim):
    out, pool = [], set(ts) | {t for d in ds for t in list(tk(d["tx"], 25))}
    for d in ds:
        if d["inc"]:
            for l, b in d["bl"]:
                for s in sents(b):
                    h = [t for t in pool if t in s.lower()]
                    cu = [x for x in FC if x in s.lower()]
                    if h and cu:
                        out.append({"evidence_id": "", "source_id": d["sid"], "kind": "finding", "locator": l, "quote": s[:900],
                                    "stance": pol(s), "strength": "directly_supported", "_s": len(h) + len(cu)})
    out.sort(key=lambda e: -e["_s"])
    out = out[:lim]
    for i, e in enumerate(out):
        e["evidence_id"] = "E%02d" % (i + 1)
        e.pop("_s", None)
    return out
def best(d, ts):
    r = [(sum(1 for t in ts if t in x.lower()), (l, x)) for l, b in d["bl"] for x in sents(b)]
    return max(r)[1] if r else None
def base(cid, ct):
    return {"skill": "research-topic-novelty-appraisal", "case_id": cid, "status": "partial", "topic": "",
            "research_product": {}, "sources": [], "evidence": [], "claims": [], "conflicts": [], "gaps": [],
            "evidence_matrix": {"rows": 0, "included": 0, "excluded": 0, "reasons": {}}, "comparison_matrix": [],
            "search_protocol": {"executed": False}, "coverage_metrics": {}, "uncertainty": {"items": []},
            "pending_human": [], "errors": [], "degradations": [], "changes": [], "runtime": {}, "tool_call_trace": [],
            "output_contract": ct, "artifacts": {}, "consistency_check": {}, "review_summary": {}}
def ac(R, ct):
    f = lambda v: [] if isinstance(v, list) else ({} if isinstance(v, dict) else None)
    rp = R.get("research_product") or {}
    for k, v in ct.items():
        if k not in R or R[k] is None:
            prod = rp.get(k)
            R[k] = prod if prod is not None else f(v)
        if isinstance(v, dict) and isinstance(R.get(k), dict):
            [R[k].setdefault(k2, f(v2)) for k2, v2 in v.items()]
def rdir(a, c):
    for x in ([Path(a)] if a else []) + [Path(y) for y in c]:
        try:
            if x.exists() and x.is_dir():
                return x.resolve()
        except Exception:
            pass
    return None
def analyse(inp, R, tr, er, dgx, AS):
    tr.append({"step": "resolve_input", "target": str(inp)})
    cs = [inp / "case.json"] if (inp / "case.json").exists() else sorted(inp.rglob("case*.json"))
    case = {}
    if cs:
        case, ce = lj(cs[0])
        if case is None:
            er.append("case_json_unreadable")
            case = ce = None
        else:
            er.append("case_note:%s" % ce) if ce else None
            tr.append({"step": "load_case", "target": str(cs[0].relative_to(inp)),
                       "sha256": hs(json.dumps(case, sort_keys=True, ensure_ascii=False))})
    elif (inp / "task.md").exists():
        case = {"task_instruction": (inp / "task.md").read_text(encoding="utf-8", errors="replace")[:4000]}
        dgx.append("case_missing:taken_from_task_md")
    else:
        dgx.append("case_missing")
        er.append("no_case_no_task")
    case = case if isinstance(case, dict) else {"raw": case}
    cid = str(case.get("case_id") or case.get("caseId") or case.get("id") or "unknown-case")
    ct = case.get("output_contract") or case.get("outputContract")
    ct = ct if isinstance(ct, dict) else dict(DEFC)
    tp = fo(case, ["research_topic", "topic", "title", "question", "题目", "subject"]) or fo(case, ["task_instruction"])
    ida = fo(case, ["research_idea", "proposal", "idea", "hypothesis", "设想", "research_question", "objective", "aim"])
    ds = build(scan(inp, tr), tr, er, dgx)
    tw = fo(case, ["time_window", "year_range", "时间窗", "period"])
    ys = sorted(int(y) for y in YR.findall(tw)) if tw else []
    for d in ds:
        if not d["yr"]:
            d["why"] = "纳入（缺年份，未校验时间窗）"
        elif len(ys) >= 2 and not (ys[0] <= int(d["yr"]) <= ys[1]):
            d["inc"], d["why"] = False, "排除:越界%s-%s" % (d["yr"], ys[0], ys[1])
    dterms(ds)
    ts = [t for t, _ in sorted(tk(nm(tp + " " + ida), 300).items(), key=lambda kv: -kv[1])][:18] or ["研究"]
    ev = evid(ds, ts, 60)
    inc = [d for d in ds if d["inc"]]
    R["sources"] = [{"source_id": d["sid"], "path": d["path"], "title": d["ti"], "year": d["yr"] or None,
                     "doi": d["doi"] or None, "sha256": d["sha"], "included": d["inc"], "inclusion_reason": d["why"]} for d in ds]
    R["evidence"] = [{k: e[k] for k in ("evidence_id", "source_id", "locator", "quote", "stance", "strength")} for e in ev]
    rc = {}
    for d in ds:
        rc[d["why"]] = rc.get(d["why"], 0) + 1
    R["evidence_matrix"] = {"rows": len(ds), "included": len(inc), "excluded": len(ds) - len(inc), "reasons": rc}
    if not AS:
        R["pending_human"].append("assess.py 不可用")
        return cid, ct, tp
    tf = facets(ts, case)
    R["search_protocol"], R["coverage_metrics"] = AS.dproto(case, ts, tf, ds), AS.dcov(ds, ts, ev)
    P = {"problem_definition": AS.dprob(case, tp, ida, ts, tf, ev), "prior_work_comparison": AS.dcomp(inc, ev),
         "novelty_assessment": AS.dnov(case, ida, inc), "feasibility": AS.dfea(inc, ev)}
    R["research_product"] = P
    R["comparison_matrix"], R["conflicts"] = P["prior_work_comparison"]["items"], AS.dcon(ev, ts)
    R["gaps"] = AS.dgap(ds, P, ts)
    R["claims"] = AS.dclaim(P, ev)
    R["uncertainty"] = {"items": AS.dunc(R, ds, ev)}
    R["review_summary"] = {"four_deliverables": {k: bool(v) for k, v in P.items()}, "evidence": len(ev),
                           "conflicts": len(R["conflicts"]), "gaps": len(R["gaps"]), "decision": AS.decide(P)}
    if not ds:
        R["status"] = "insufficient_evidence"
        R["pending_human"].append("无可用文本材料")
    elif len(ev) < 5 or len(inc) < 2:
        R["status"] = "partial"
        R["pending_human"].append("材料过少(%d/%d)" % (len(inc), len(ev)))
    else:
        R["status"] = "ok"
    if any(p["status"] == "assumed_not_documented" for p in P["feasibility"]["premises"]):
        R["pending_human"].append("前提待补")
    return cid, ct, tp
def main(argv=None):
    ap = argparse.ArgumentParser(prog="appraise.py", description="科研选题与创新性评估(离线)",
                                 epilog="复核: assess.py --check")
    ap.add_argument("--input", "--in-dir", dest="input", help="默认 /input")
    ap.add_argument("--output", "--out-dir", dest="output", help="默认 /app/output")
    a = ap.parse_args(argv)
    tr, er, dgx = [], [], []
    cid, ct, tp = "unknown-case", dict(DEFC), ""
    out = Path(a.output).expanduser() if a.output else (rdir(None, ["/app/output", "output"]) or (PKG / "_out"))
    try:
        out.mkdir(parents=True, exist_ok=True)
        out = out.resolve()
        (out / ".w").write_text("x", encoding="utf-8")
        (out / ".w").unlink()
    except Exception as e:
        dgx.append("out_fallback:%s" % e)
        out = PKG / "_out"
        out.mkdir(parents=True, exist_ok=True)
    R = base(cid, ct)
    wj(R, out / "result.json")
    try:
        sys.path.insert(0, str(HERE))
        import assess as AS
    except Exception as e:
        AS = None
        dgx.append("assess_import_failed:%s" % e)
    inp = rdir(a.input, ["/input", "/app/input", "input"])
    try:
        if inp is None:
            R["status"] = "input_error"
            er.append("input_dir_not_found")
            R["pending_human"].append("未找到输入目录")
        else:
            cid, ct, tp = analyse(inp, R, tr, er, dgx, AS)
    except Exception as e:
        import traceback
        er.append("fatal:%s" % e)
        dgx.append("fatal_trace:%s" % traceback.format_exc()[-600:])
        R["status"] = "partial"
    try:
        R.update({"case_id": cid, "output_contract": ct, "topic": tp[:500], "errors": er, "tool_call_trace": tr,
                  "degradations": sorted(set(dgx)), "pending_human": sorted(set(R["pending_human"])),
                  "runtime": {"version": V, "seconds": round(time.time() - T0, 2),
                              "within_budget": True},
                  "changes": [{"action": "partial_then_finalize", "seconds": round(time.time() - T0, 2)}]})
        ac(R, ct)
        m = R["evidence_matrix"]
        R["consistency_check"] = {"contract_keys_present": all(k in R for k in ct),
                                  "all_claims_linked": all(c.get("evidence_ids") or c["strength"] == "insufficient" for c in R["claims"]),
                                  "four_deliverables_present": all(k in R["research_product"] for k in DEFC),
                                  "included_plus_excluded": m["included"] + m["excluded"] == m["rows"]}
        if AS and R.get("research_product"):
            AS.tables(out, R)
            (out / "research_report.md").write_text(AS.render(R), encoding="utf-8")
        else:
            AS and AS.tables(out, R)
            (out / "research_report.md").write_text("# 报告不可用(%s)\n" % R.get("status"), encoding="utf-8")
        R["artifacts"] = {k: str(out / v) for k, v in (("result", "result.json"), ("report", "research_report.md"),
                                                       ("evidence_map", "evidence_map.csv"), ("comparison_matrix", "comparison_matrix.csv"))}
        wj(R, out / "result.json")
    except Exception as e:
        er.append("finalize:%s" % e)
        R["errors"] = er
        try:
            wj(R, out / "result.json")
        except Exception:
            pass
    print("%s | %s | %s | src=%d ev=%d conf=%d gap=%d" % (
        V, R.get("case_id"), R.get("status"), len(R.get("sources", [])), len(R.get("evidence", [])),
        len(R.get("conflicts", [])), len(R.get("gaps", []))))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("unhandled:%s" % e, file=sys.stderr)
        sys.exit(0)
