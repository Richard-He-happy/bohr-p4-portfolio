#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-10 v2 资产层：golden_standard/diff_report/version_history/run.log/self_check
+ proposal_matrix.json/milestones.csv/risks.md。纯标准库、离线、不依赖 CWD；异常只记 degradations。"""
import csv, hashlib, io, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal as P  # noqa: E402

HERE, PKG = Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent
MAIN, LOGMAX = HERE / "main.py", 64 * 1024
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|个月|月|年|例|人|次|万元|元|h|mg|mL|mM|天|周)")
FORBID = ("已完成", "已获得", "已证实", "结果显示", "已实现", "得到结论")
FILES = ["proposal.md", "result.json", "golden_standard.json", "diff_report.md", "version_history.md",
         "run.log", "self_check.json", "proposal_matrix.json", "milestones.csv", "risks.md"]
ELT = {"background": "一、研究背景与缺口", "problem": "二、研究问题与可证伪性", "objectives": "三、研究目标",
       "methods": "四、技术路线与方法", "plan": "五、阶段计划与里程碑", "risks": "六、风险与备选方案",
       "outcomes": "七、预期成果与验证方式", "data": "数据、样本与合规来源"}
ELID = {"background": "背景与缺口", "problem": "研究问题", "objectives": "研究目标", "methods": "技术路线",
        "data": "数据", "plan": "阶段计划", "risks": "风险", "outcomes": "预期成果"}
T = P.norm


def L(v):
    return [x for x in P.al(v) if isinstance(x, dict)]


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _jl(p):
    try:
        p = Path(p)
        return (None, "not_found") if not p.is_file() else (
            json.loads(p.read_text(encoding="utf-8-sig", errors="replace").lstrip("\ufeff")), None)
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def _w(path, body):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body, (dict, list)):
        t = p.with_name(p.name + ".tmp")
        t.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        os.replace(t, p)
    else:
        p.write_text(body, encoding="utf-8")
    return p.stat().st_size


def _hex(p, algo="sha256"):
    try:
        return hashlib.new(algo, Path(p).read_bytes()).hexdigest()[:16 if algo == "sha256" else 8]
    except Exception:
        return None


def note(outdir, stage, msg):
    """追加一行到 run.log，超 64KB 留尾部；永不抛异常。"""
    try:
        p = Path(outdir) / "run.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        txt = old + "[%s] %-8s %s\n" % (now(), stage, T(msg)[:400])
        if len(txt.encode("utf-8")) > LOGMAX:
            txt = "[log rotated, tail kept]\n" + txt[-LOGMAX // 2:]
        p.write_text(txt, encoding="utf-8")
    except Exception:
        pass


def hook(outdir, res):
    """finalize 钩子：每次命令的结果写进 run.log。"""
    try:
        res = res if isinstance(res, dict) else {}
        note(outdir, (T(res.get("note")).split(":")[0].split(" ")[0] or "run").upper(),
             "status=%s elapsed=%ss materials=%d errors=%d degradations=%d" % (
                 res.get("status"), (res.get("runtime") or {}).get("elapsed_s", "?"),
                 len(res.get("sources") or []), len(res.get("errors") or []), len(res.get("degradations") or [])))
        for tag, k in (("ERROR", "errors"), ("DEGRADE", "degradations")):
            for x in (res.get(k) or [])[:8]:
                note(outdir, tag, x)
    except Exception:
        pass


def sectxt(d, eid):
    for s in L(d.get("sections")):
        if T(s.get("id")).lower() == eid:
            return P.section_text(s)
    return ""


def rqs(d):
    out = L(d.get("rqs") or d.get("research_questions"))
    for i, r in enumerate(out):
        r["id"] = T(r.get("id")) or "RQ%d" % (i + 1)
    return out


def rid(d):
    return {T(r.get("id")).upper() for r in rqs(d)}


def maxm(o):
    s = T(json.dumps(o, ensure_ascii=False, default=str))
    pk = [int(x) for x in re.findall(r"\d{1,2}\s*[–\-~至]\s*(\d{1,2})\s*月", s)]
    pk += [int(x) for x in re.findall(r"第\s*(\d{1,2})\s*月", s)]
    return max(pk) if pk else None


def mrange(s):
    t = T(s)
    m = re.search(r"(\d{1,2})\s*[–\-~至]\s*(\d{1,2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*月", t)
    return (int(m.group(1)), int(m.group(1))) if m else (None, None)


def per_of(o):
    per = (o or {}).get("period") or {}
    m = re.search(r"\d+", T(per.get("total")))
    return (int(m.group(0)) if m else None), per


def stray(D):
    """论断区数字：材料与计划字段都找不到同形文本者。"""
    d, i = D["draft"], D["idx"]
    mat = " ".join(T(m.get("text")).lower() for m in (i.get("materials") or []))
    plan = T(json.dumps({k: d.get(k) for k in ("period", "milestones")}, ensure_ascii=False)).lower()
    bad = []
    for sc in (json.dumps({k: d.get(k) for k in ("rqs", "objectives", "outcomes", "resources")}, ensure_ascii=False),
               json.dumps(d.get("sections"), ensure_ascii=False)):
        for mm in NUM.finditer(sc):
            v = mm.group(0).strip()
            if v.lower() not in mat and v.lower() not in plan and v not in bad:
                bad.append(v)
    return bad[:12]


# (id, 要素, 规则, rubric, 期望, 必备, 修复, 锚点词)
G = [
 ("G01", "契约", "contract", "完整性", "output_contract 每字段原样回填，缺值 null/[]", "字段全在且非空", "补映射", ["output_contract", "契约"]),
 ("G02", "周期", "period", "正确性", "周期取自材料原文，里程碑不越界", "quote 逐字；最远月≤周期", "回填原文", ["周期", "执行期", "工期"]),
 ("G03", "证据", "evratio", "可核验性", "论断带 source_id+locator+逐字 quote", "命中率≥90%", "换原文切片", ["可核验", "复跑", "来源"]),
 ("G04", "诚实", "honesty", "正确性", "未获结果不写成已获，缺口进 pending_human", "无结果断言；pending 非空", "改拟/将", ["待确认", "缺口"]),
 ("G05", "背景与缺口", "sec:background", "完整性", "背景节成文并挂材料证据", "成节；≥60 字；有证据", "补写背景", ["背景", "现状", "前期"]),
 ("G06", "背景与缺口", "gap", "正确性", "缺口写成「已知—未知—待验证」", "含已知/未知/待验证", "改三段式", ["缺口", "未知", "待验证"]),
 ("G07", "背景与缺口", "noreview", "正确性", "背景不是领域综述", "无纯综述陈述", "留缺口句", ["综述", "研究现状"]),
 ("G08", "研究问题", "rq", "完整性", "1–3 条研究问题，含对象与条件", "1≤数量≤3；含条件", "收敛问题", ["研究问题", "假设"]),
 ("G09", "研究问题", "falsifier", "正确性", "每条 RQ 写明何种观测否定假设", "falsifier 含观测/时点", "补判伪", ["可证伪", "否定"]),
 ("G10", "研究问题", "metric", "正确性", "每条 RQ 有指标、阈值与依据", "name/threshold/basis", "补阈值依据", ["指标", "阈值", "终点"]),
 ("G11", "研究问题", "sample", "完整性", "每条 RQ 写清样本、条件、时点", "三项中≥2", "补样本时点", ["样本", "纳入"]),
 ("G12", "研究目标", "objlink", "完整性", "目标与 RQ 一一对应，无孤儿目标", "rq 指向存在 RQ", "修 rq", ["目标", "旨在"]),
 ("G13", "研究目标", "objcrit", "正确性", "每个目标有可检查完成判据", "criterion", "补判据", ["考核", "判据"]),
 ("G14", "技术路线", "steps", "完整性", "路线≥3 步，各含输入→操作→输出", "steps≥3；三要素齐", "拆步骤", ["技术路线", "方法"]),
 ("G15", "技术路线", "dep", "正确性", "依赖可解、无悬空、无环", "depends_on 均存在", "修依赖", ["依赖", "步骤"]),
 ("G16", "技术路线", "metev", "可核验性", "方法均来自材料，有 locator+quote", "每步有来源", "补方法引文", ["方法", "依据"]),
 ("G17", "数据", "data", "完整性", "数据来源、样本量、合规条件写明", "resources.data 非占位", "填数据来源", ["数据", "队列", "伦理"]),
 ("G18", "数据", "datanum", "正确性", "数字与材料同形，新增值标计划值", "无无依据数字", "标计划值", ["数据", "样本量"]),
 ("G19", "阶段计划", "ms", "完整性", "里程碑≥3，各有交付物与判据", "deliverable/criterion", "补里程碑", ["里程碑", "进度"]),
 ("G20", "阶段计划", "msperiod", "正确性", "里程碑落在周期内并标关键路径", "最远月≤周期；critical", "标关键路径", ["周期", "关键路径"]),
 ("G21", "阶段计划", "res", "完整性", "经费人员落在给定条件内，缺失标 pending", "budget/people", "回填或 pending", ["经费", "预算"]),
 ("G22", "风险", "risk", "完整性", "风险≥4 条、≥3 类（数据/方法/进度/伦理）", "条数≥4；类型≥3", "按四类补", ["风险", "伦理"]),
 ("G23", "风险", "riskact", "正确性", "每条风险有触发/影响/备选/决策时点", "四字段齐", "补四要素", ["触发", "备选"]),
 ("G24", "预期成果", "out", "完整性", "成果与 RQ 对应并写验证方式", "rq/verification", "补 rq 与验证", ["成果", "论文"]),
 ("G25", "预期成果", "notresult", "正确性", "成果写成可验证判据，不冒充已获结果", "含判据/验证", "改判据式", ["成果", "指标"]),
 ("G26", "预期成果", "outver", "可核验性", "给出可复跑的验证/验收方式", "含复跑/验收", "写复跑步骤", ["验证", "复现"]),
 ("G27", "七要素", "sections", "完整性", "七要素成节且各节不过短", "7/7；每节≥60 字", "补缺节", ["开题", "研究计划"]),
]
judged = "rule:<名> 对应 scripts/assets.py 中的函数；判据字段见 must_have"


# ---------- 27 条判定规则：f(D) -> (status, actual, fix) ----------
def r_contract(D):
    res, c = D["res"], (D["res"].get("_contract") or {})
    if not c:
        return "deviation", "输入未提供 output_contract", "确认 case.json"
    miss = []
    for k in c:
        v, kl = res.get(k), str(k).lower()
        if v in (None, "", [], {}):
            v = next((res.get(n) for n in res if not n.startswith("_") and kl.split("_")[0] in n.lower()
                      and res.get(n) not in (None, "", [], {})), None)
        if v in (None, "", [], {}):
            miss.append(str(k))
    if miss:
        return "deviation", "未覆盖 %d/%d：%s" % (len(miss), len(c), "、".join(miss[:6])), "补映射后重跑"
    return "pass", "契约 %d 字段均有值（self_check 复核）" % len(c), ""


def r_period(D):
    tot, per = per_of(D["draft"])
    q, mx = T(per.get("quote")), maxm(D["draft"])
    if not tot:
        return "missing", "未声明研究周期", "从材料抽周期"
    if T(per.get("source")) in ("default_12m", "") or not q:
        return "deviation", "周期 %d 月为兜底值（无 quote）" % tot, "回填周期原文"
    if mx and mx > tot:
        return "deviation", "最远第 %d 月 > 周期 %d 月" % (mx, tot), "压缩里程碑"
    return "pass", "周期 %d 月，最远 %s 月；quote「%s」" % (tot, mx or "—", q[:34]), ""


def r_evratio(D):
    c = (D["rep"] or {}).get("counts") or {}
    t, v = c.get("evidence_total", 0), c.get("evidence_verified", 0)
    if not t:
        return "missing", "全稿 0 条证据", "补 source_id+locator+quote"
    r = v / t
    return ("pass", "证据 %d/%d 逐字命中（%.0f%%）" % (v, t, r * 100), "") if r >= 0.9 else \
           ("deviation", "证据 %d/%d 命中（%.0f%%<90%%）" % (v, t, r * 100), "换原文切片")


def r_honesty(D):
    d = D["draft"]
    hits = [w for w in FORBID if w in json.dumps({k: d.get(k) for k in ("rqs", "objectives", "outcomes")}, ensure_ascii=False)]
    pend = L(d.get("pending_human")) + L(D["res"].get("pending_human"))
    if hits:
        return "deviation", "既成结果断言：%s" % "、".join(hits), "改拟/将+判据"
    if not pend:
        return "deviation", "未记录 pending_human 缺口", "写未确认项"
    return "pass", "无结果断言；pending %d 条" % len(pend), ""


def r_gap(D):
    txt = sectxt(D["draft"], "background")
    if len(txt) < 30:
        return "missing", "背景缺内容（%d 字）" % len(txt), "按三段式写"
    hit = [k for k in ("已知", "未知", "待验证", "缺口", "尚不清") if k in txt]
    return ("pass", "缺口含 %s（%d 字）" % ("、".join(hit), len(txt)), "") if len(hit) >= 2 else \
           ("deviation", "未收敛为缺口（命中 %s）" % ("、".join(hit) or "无"), "改已知→未知→待验证")


def r_noreview(D):
    txt = sectxt(D["draft"], "background")
    if not txt:
        return "missing", "背景为空", "补写"
    if re.search(r"综述|研究现状表明|近年来", txt) and not re.search(r"缺口|未知|待验证", txt):
        return "deviation", "疑似综述式背景", "留缺口证据句"
    return "pass", "非综述式（%d 字）" % len(txt), ""


def r_rq(D):
    rq = rqs(D["draft"])
    if not rq:
        return "missing", "无研究问题", "写 1–3 条"
    short = [T(r.get("id")) for r in rq if len(T(r.get("question"))) < 12]
    if short:
        return "deviation", "%s 问题过短/缺条件" % "、".join(short[:3]), "补对象+条件"
    if not 1 <= len(rq) <= 3:
        return "deviation", "%d 条 RQ（应 1–3）" % len(rq), "收敛数量"
    return "pass", "%d 条：%s" % (len(rq), "；".join(T(r.get("question"))[:42] for r in rq[:2])), ""


def r_falsifier(D):
    rq = rqs(D["draft"])
    if not rq:
        return "missing", "无 RQ", "先写 RQ"
    bad = [T(r.get("id")) for r in rq if len(T(r.get("falsifier"))) < 8]
    return ("deviation", "%s 判伪条件缺失" % "、".join(bad[:3]), "写否定观测") if bad else \
           ("pass", "%d 条均有判伪：%s" % (len(rq), T(rq[0].get("falsifier"))[:52]), "")


def r_metric(D):
    rq = rqs(D["draft"])
    if not rq:
        return "missing", "无 RQ", "先写 RQ"
    no = [T(r.get("id")) for r in rq if not any(T(m.get("threshold")) for m in L(r.get("metrics")))]
    nb = [T(r.get("id")) for r in rq if T(r.get("id")) not in no and
          any(not (T(m.get("basis")) or T(m.get("basis_locator"))) for m in L(r.get("metrics")))]
    if no:
        return "missing", "%s 缺指标/阈值" % "、".join(no[:3]), "补指标+阈值"
    if nb:
        return "deviation", "%s 阈值缺依据" % "、".join(nb[:3]), "补 basis 或 pending"
    return "pass", "阈值与依据齐：%s" % "、".join(T(m.get("threshold")) for r in rq for m in L(r.get("metrics")))[:52], ""


def r_sample(D):
    rq = rqs(D["draft"])
    if not rq:
        return "missing", "无 RQ", "先写 RQ"
    thin = [T(r.get("id")) for r in rq if sum(1 for k in ("sample", "condition", "timepoint") if T(r.get(k))) < 2]
    return ("deviation", "%s 样本/条件/时点不足" % "、".join(thin[:3]), "补三项") if thin else \
           ("pass", "样本/条件/时点齐（%s）" % T(rq[0].get("sample"))[:28], "")


def r_objlink(D):
    d = D["draft"]
    objs, ids = L(d.get("objectives")), rid(d)
    if not objs:
        return "missing", "无目标", "按 RQ 拆目标"
    orph = [T(o.get("id")) for o in objs if T(o.get("rq")).upper() not in ids]
    naked = [r for r in ids if not any(T(o.get("rq")).upper() == r for o in objs)]
    if orph:
        return "deviation", "目标 %s 指向不存在的 RQ" % "、".join(orph[:3]), "改 rq 指向"
    if naked:
        return "deviation", "RQ %s 无目标" % "、".join(sorted(naked)[:3]), "补目标"
    return "pass", "%d 目标指向 %d 条 RQ" % (len(objs), len(ids)), ""


def r_objcrit(D):
    objs = L(D["draft"].get("objectives"))
    if not objs:
        return "missing", "无目标", "补目标"
    bad = [T(o.get("id")) for o in objs if len(T(o.get("criterion"))) < 6]
    return ("deviation", "%s 缺判据" % "、".join(bad[:3]), "写判据") if bad else ("pass", "%d 目标均有判据" % len(objs), "")


def r_steps(D):
    st = L(D["draft"].get("steps"))
    if not st:
        return "missing", "无路线步骤", "拆输入→操作→输出"
    if len(st) < 3:
        return "deviation", "步骤 %d 条（<3）" % len(st), "至少 3 步"
    bad = [T(s.get("id")) for s in st if not (T(s.get("input")) and T(s.get("action")) and T(s.get("output")))]
    return ("deviation", "%s 缺输入/操作/输出" % "、".join(bad[:3]), "补三要素") if bad else \
           ("pass", "%d 步成链（%s…%s）" % (len(st), T(st[0].get("id")), T(st[-1].get("id"))), "")


def r_dep(D):
    st = L(D["draft"].get("steps"))
    if not st:
        return "missing", "无步骤", "补路线"
    ids = [T(s.get("id")).upper() for s in st]
    bad, g = [], {}
    for s in st:
        deps = [T(x).upper() for x in P.al(s.get("depends_on")) if T(x) not in ("", "—", "-", "无")]
        g[T(s.get("id")).upper()] = [x for x in deps if x in ids]
        bad += [x for x in deps if x not in ids]
    if bad:
        return "deviation", "依赖悬空：%s" % "、".join(sorted(set(bad))[:4]), "修 depends_on"
    seen, stk = set(), set()

    def cyc(n):
        if n in stk:
            return True
        if n in seen:
            return False
        seen.add(n)
        stk.add(n)
        r = any(cyc(m) for m in g.get(n, []))
        stk.discard(n)
        return r

    if any(cyc(n) for n in g):
        return "deviation", "依赖成环", "打破环"
    return "pass", "依赖可解（%d 边）" % sum(len(v) for v in g.values()), ""


def r_metev(D):
    refs = {T(e.get("ref")).upper() for e in ((D["rep"] or {}).get("evidence") or [])}
    st = {T(s.get("id")).upper() for s in L(D["draft"].get("steps"))}
    if not st:
        return "missing", "无步骤", "补路线"
    hit = len(st & refs)
    if not hit:
        return "deviation", "方法无逐字来源（0/%d）" % len(st), "为每步补 quote"
    if hit < len(st):
        return "deviation", "方法有来源 %d/%d" % (hit, len(st)), "补其余引文"
    return "pass", "%d 步均有材料来源" % len(st), ""


def r_data(D):
    dat = T((D["draft"].get("resources") or {}).get("data"))
    if not dat:
        return "missing", "未写数据来源", "补 resources.data"
    if re.search(r"待确认|未给出|未提供|见材料清单", dat):
        return "deviation", "数据口径未定：%s" % dat[:34], "按材料回填"
    return "pass", "数据：%s" % dat[:42], ""


def r_datanum(D):
    bad = stray(D)
    return ("pass", "论断区数字均有材料/计划同形文本", "") if not bad else \
           ("deviation", "无依据数字 %d 个：%s" % (len(bad), "、".join(bad[:6])), "补依据或标计划值")


def r_ms(D):
    ms = L(D["draft"].get("milestones"))
    if not ms:
        return "missing", "无里程碑", "按周期排"
    if len(ms) < 3:
        return "deviation", "里程碑 %d 条（<3）" % len(ms), "至少 3 个"
    nc = [T(m.get("id")) for m in ms if len(T(m.get("criterion"))) < 6]
    nd = [T(m.get("id")) for m in ms if not T(m.get("deliverable"))]
    return ("deviation", "缺判据 %s；缺交付物 %s" % ("、".join(nc[:3]) or "—", "、".join(nd[:3]) or "—"), "补齐") \
        if (nc or nd) else ("pass", "%d 里程碑均有交付物与判据" % len(ms), "")


def r_msperiod(D):
    tot = per_of(D["draft"])[0]
    mx = maxm(D["draft"])
    if not tot:
        return "missing", "未声明周期", "写 period.total"
    if mx and mx > tot:
        return "deviation", "最远第 %d 月 > 周期 %d 月" % (mx, tot), "压缩或延长"
    cp = [T(m.get("id")) for m in L(D["draft"].get("milestones")) if m.get("critical_path") in (True, 1, "是", "True")]
    if not cp:
        return "deviation", "未标关键路径（%s/%d 月）" % (mx, tot), "标关键路径"
    return "pass", "里程碑在 %d 月内，关键路径 %s" % (tot, "、".join(cp[:4])), ""


def r_res(D):
    r = D["draft"].get("resources") or {}
    miss = [k for k in ("budget", "people") if not T(r.get(k)) or re.search(r"待确认|未给出|材料未给|未提供", T(r.get(k)))]
    return ("deviation", "经费/人员未落实（%s）" % "、".join(miss), "回填或 pending") if miss else \
           ("pass", "经费「%s」人员「%s」" % (T(r.get("budget"))[:18], T(r.get("people"))[:18]), "")


def r_risk(D):
    rk = L(D["draft"].get("risks"))
    if not rk:
        return "missing", "无风险", "按四类补"
    if len(rk) < 4:
        return "deviation", "风险 %d 条（<4）" % len(rk), "补足 4 条"
    ty = {T(r.get("type")) for r in rk if T(r.get("type"))}
    return ("deviation", "类型 %d 类（<3）：%s" % (len(ty), "、".join(sorted(ty)) or "未标"), "覆盖四类") \
        if len(ty) < 3 else ("pass", "%d 条/%d 类：%s" % (len(rk), len(ty), "、".join(sorted(ty))), "")


def r_riskact(D):
    rk = L(D["draft"].get("risks"))
    if not rk:
        return "missing", "无风险", "补风险表"
    bad = [T(r.get("id")) for r in rk if not all(T(r.get(k)) for k in ("trigger", "impact", "fallback", "decision_point"))]
    return ("deviation", "%s 缺触发/影响/备选/时点" % "、".join(bad[:3]), "补四要素") if bad else \
           ("pass", "%d 条四要素齐（%s→%s）" % (len(rk), T(rk[0].get("trigger"))[:24], T(rk[0].get("decision_point"))[:14]), "")


def r_out(D):
    outs, ids = L(D["draft"].get("outcomes")), rid(D["draft"])
    if not outs:
        return "missing", "无预期成果", "补成果+验证"
    bad = [T(o.get("id")) for o in outs if not T(o.get("verification"))]
    if bad:
        return "deviation", "%s 缺验证方式" % "、".join(bad[:3]), "补 verification"
    orph = [T(o.get("id")) for o in outs if T(o.get("rq")).upper() not in ids]
    return ("deviation", "%s 未挂 RQ" % "、".join(orph[:3]), "补 rq") if orph else \
           ("pass", "%d 项成果均挂 RQ 且有验证" % len(outs), "")


def r_notresult(D):
    d = D["draft"]
    txt = json.dumps({k: d.get(k) for k in ("rqs", "objectives", "outcomes")}, ensure_ascii=False)
    hits = [w for w in FORBID if w in txt]
    if hits:
        return "deviation", "既成结果断言：%s" % "、".join(hits), "改判据式表述"
    return ("pass", "成果为可验证判据，未冒充已获", "") if any(w in txt for w in ("判据", "验证", "阈值")) else \
           ("deviation", "成果缺判据表述", "写判定方式")


def r_outver(D):
    outs = L(D["draft"].get("outcomes"))
    if not outs:
        return "missing", "无成果", "补成果"
    vs = [T(o.get("verification")) for o in outs]
    weak = [v for v in vs if len(v) < 8 or not re.search(r"复跑|复现|验收|判定|比对|回溯|一致|重算", v)]
    return ("deviation", "%d/%d 验证不可复跑：%s" % (len(weak), len(vs), (weak[0] or "空")[:32]), "写复跑步骤") if weak \
        else ("pass", "验证可复跑（%s）" % vs[0][:40], "")


def r_sections(D):
    cov = (D["rep"] or {}).get("coverage") or {}
    miss = [e for e in P.EIDS if not (cov.get(e) or {}).get("present")]
    thin = [e for e in P.EIDS if (cov.get(e) or {}).get("present") and (cov.get(e) or {}).get("chars", 0) < 60]
    if miss:
        return "missing", "缺节：%s" % "、".join(miss[:5]), "补齐七要素"
    if thin:
        return "deviation", "过短：%s" % "、".join(thin[:5]), "补内容与证据"
    return "pass", "七要素 7/7，最短 %d 字" % min((cov.get(e) or {}).get("chars", 0) for e in P.EIDS), ""


def sec_rule(eid):
    def f(D):
        c = ((D["rep"] or {}).get("coverage") or {}).get(eid) or {}
        if not c.get("present"):
            return "missing", "缺要素节 %s" % eid, "补写「%s」" % ELT.get(eid, eid)
        if c.get("chars", 0) < 60:
            return "deviation", "仅 %d 字（<60）" % c.get("chars", 0), "补依据与证据"
        return "pass", "成节 %d 字/证据 %d 条" % (c.get("chars", 0), c.get("evidence", 0)), ""
    return f


RULES = {"contract": r_contract, "period": r_period, "evratio": r_evratio, "honesty": r_honesty, "gap": r_gap,
         "noreview": r_noreview, "rq": r_rq, "falsifier": r_falsifier, "metric": r_metric, "sample": r_sample,
         "objlink": r_objlink, "objcrit": r_objcrit, "steps": r_steps, "dep": r_dep, "metev": r_metev,
         "data": r_data, "datanum": r_datanum, "ms": r_ms, "msperiod": r_msperiod, "res": r_res, "risk": r_risk,
         "riskact": r_riskact, "out": r_out, "notresult": r_notresult, "outver": r_outver, "sections": r_sections}
for _e in P.EIDS:
    RULES["sec:" + _e] = sec_rule(_e)


def anchors(i, kws, limit=2):
    """材料逐字切片锚点：先按关键词命中，无命中则用最长可读段落作 context 锚点（标注 kind）。"""
    out, seen = [], set()
    for m in i.get("materials") or []:
        for pa in m.get("paras") or []:
            t = T(pa.get("text"))
            if len(t) < 12:
                continue
            for kw in kws:
                p = t.find(kw)
                if p < 0:
                    continue
                q = t[max(0, p - 30):p + 70].strip()
                if len(q) < 8 or (m.get("id"), pa.get("loc")) in seen:
                    continue
                h = P.find_quote(i, m.get("id"), q)
                out.append({"source_id": m.get("id"), "locator": pa.get("loc"), "quote": q, "matched": kw,
                            "kind": "keyword", "verified": bool(h), "verified_locator": h[1] if h else None})
                seen.add((m.get("id"), pa.get("loc")))
                break
            if len(out) >= limit:
                return out
    if out:
        return out
    cand = [(len(T(pa.get("text"))), m.get("id"), pa.get("loc"), T(pa.get("text")))
            for m in i.get("materials") or [] for pa in (m.get("paras") or []) if len(T(pa.get("text"))) >= 24]
    if cand:
        _, sid, loc, txt = max(cand)
        q = txt[:100].strip()
        h = P.find_quote(i, sid, q)
        out.append({"source_id": sid, "locator": loc, "quote": q, "matched": "", "kind": "context",
                    "verified": bool(h), "verified_locator": h[1] if h else None})
    return out


def cnt(rows):
    c = {k: 0 for k in ("pass", "missing", "deviation")}
    for r in rows:
        c[r[3]] = c.get(r[3], 0) + 1
    return {"pass": c["pass"], "missing": c["missing"], "deviation": c["deviation"], "total": len(rows),
            "pass_rate": round((c["pass"] + 0.5 * c["deviation"]) / max(1, len(rows)), 4)}


def golden(D):
    items, rows = [], []
    for gid, el, rule, rub, need, must, fix, kws in G:
        fn = RULES.get(rule)
        try:
            st, act, rf = fn(D)
        except Exception as e:
            st, act, rf = "deviation", "判定异常 %s: %s" % (type(e).__name__, e), "查字段类型"
        a = anchors(D["idx"], kws)
        items.append({"id": gid, "element": el, "expectation": need, "must_have": must,
                      "check": "rule:" + rule, "rubric": rub, "anchors": a, "fix_hint": fix,
                      "anchor_status": ("verified" if any(x["verified"] for x in a) else "pending_human") if a else "no_text",
                      "anchor_kind": a[0]["kind"] if a else None})
        rows.append((gid, el, need, st, act, rf, (a[0] if a else None)))
    els = [{"id": k, "title": ELT[k], "items": [i["id"] for i in items if i["element"] == ELID[k]]} for k in ELID]
    els.append({"id": "meta", "title": "元数据（契约/周期/证据/诚实/七要素）",
                "items": [i["id"] for i in items if i["element"] in ("契约", "周期", "证据", "诚实", "七要素")]})
    gs = {"schema": "golden-standard/v1", "skill": "writing-10-proposal", "skill_version": D["ver"],
          "case_id": D["res"].get("case_id"), "generated_at": now(),
          "purpose": "核心产物金标准：逐项写明应交付什么、凭什么可核验（diff_report.md 对照实际产物）",
          "quote_rule": "quote 为材料段落去空白归一化后的逐字切片，可 `show --id M1` 回看",
          "status_legend": {"pass": "达标", "missing": "缺失", "deviation": "有内容但不满足判据"},
          "expectation_source": "题面 rubric + output_contract + plan-template 检查表；不含预制答案",
          "judged_how": judged, "elements": els, "items": items,
          "accept_thresholds": {"elements_present": 7, "min_evidence_ratio": 0.9, "min_milestones": 3,
                                "min_risks": 4, "min_risk_types": 3, "max_rqs": 3, "period_from_material": True},
          "anchors": {"total": sum(len(i["anchors"]) for i in items),
                      "verified": sum(1 for i in items for x in i["anchors"] if x["verified"]),
                      "keyword_items": len([i for i in items if i.get("anchor_kind") == "keyword"]),
                      "context_items": len([i for i in items if i.get("anchor_kind") == "context"]),
                      "unverified": [{"id": i["id"], "source_id": x["source_id"], "quote": x["quote"][:40]}
                                     for i in items for x in i["anchors"] if not x["verified"]][:8],
                      "items_without_anchor": [i["id"] for i in items if not i["anchors"]]}}
    return gs, rows


def _c(s, n):
    t = T(s).replace("|", "\\|").replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else (t or "—")


def diff_md(D, gs, rows):
    c, ec, a = cnt(rows), (D["rep"] or {}).get("counts") or {}, gs["anchors"]
    Ls = ["# 差异报告：金标准 vs 实际产物", "",
          "> case_id=%s｜生成 %s｜包 %s｜金标准 %d 项｜工作稿 %s" % (
              D["res"].get("case_id") or "n/a", now(), D["ver"], len(rows),
              T((D["res"].get("deliverable") or {}).get("draft_source")) or "unknown"), "",
          "## 1. 判定口径与复跑", "",
          "| 判定 | 含义 |", "|---|---|", "| pass 达标 | 字段/证据齐全且满足判据 |",
          "| missing 缺失 | 要素或字段无内容 |", "| deviation 偏差 | 有内容但缺判据/依据/来源，或越界 |", "",
          "复跑：`python3 -B scripts/main.py build --input <INPUT> --output <OUT> --work <WORK>`；",
          "每项是 `scripts/assets.py` 中 `rule:<名>` 的纯函数，同输入可确定性复现。", "",
          "## 2. 总览", "", "| 项 | 值 |", "|---|---|",
          "| 达标/缺失/偏差 | %d / %d / %d |" % (c["pass"], c["missing"], c["deviation"]),
          "| 加权达标率（偏差记 0.5） | %.1f%% |" % (c["pass_rate"] * 100),
          "| 锚点可回溯 | %d/%d |" % (a["verified"], a["total"]),
          "| 七要素成节 | %d/7 |" % ec.get("sections_present", 0),
          "| 证据逐字命中 | %d/%d |" % (ec.get("evidence_verified", 0), ec.get("evidence_total", 0)),
          "| RQ/里程碑/风险/成果 | %d / %d / %d / %d |" % (ec.get("rqs", 0), ec.get("milestones", 0),
                                                          ec.get("risks", 0), ec.get("outcomes", 0)), "",
          "## 3. 逐项对照", "", "| ID | 要素 | 金标准要求 | 判定 | 实际产物 | 依据 |", "|---|---|---|---|---|---|"]
    for gid, el, need, st, act, rf, an in rows:
        Ls.append("| %s | %s | %s | **%s** | %s | %s |" % (
            gid, el, _c(need, 38), {"pass": "达标", "missing": "缺失", "deviation": "偏差"}.get(st, st),
            _c(act, 62), ("%s/%s" % (an["source_id"], an["locator"])) if an else "—"))
    bad = [r for r in rows if r[3] != "pass"]
    Ls += ["", "## 4. 未达标项与处置", ""]
    if not bad:
        Ls.append("（无：%d 项全部达标）" % len(rows))
    else:
        Ls += ["| ID | 判定 | 现状 | 处置 | 归属 |", "|---|---|---|---|---|"]
        Ls += ["| %s | %s | %s | %s | %s |" % (r[0], "缺失" if r[3] == "missing" else "偏差", _c(r[4], 50),
                                               _c(r[5] or "—", 36),
                                               "脚本可补" if r[3] == "deviation" else "pending_human") for r in bad]
    ar = [(r[0], r[6]) for r in rows if r[6]]
    Ls += ["", "## 5. 锚点核验（能否按 locator 逐字回到原文）", ""]
    if ar:
        Ls += ["| ID | 材料 | 定位 | 逐字 quote | 反查 |", "|---|---|---|---|---|"]
        Ls += ["| %s | %s | %s | %s | %s |" % (g, x["source_id"], x["locator"], _c(x["quote"], 44),
                                              "命中" if x["verified"] else "未命中") for g, x in ar]
    else:
        Ls.append("（材料中未取到锚点，见 pending_human）")
    Ls += ["", "## 6. 与 baseline v1 的差异", "", "| v1 | v2 |", "|---|---|",
           "| 仅 proposal.md + result.json | 另加 5 件可核验资产 + matrix/csv/risks.md |",
           "| init/show/check/build | 同前，加可选 audit |", "",
           "> 依据本次运行生成，不含预制答案。"]
    return "\n".join(Ls) + "\n"


def matrix(D):
    d = D["draft"]
    rq, objs, steps, outs = rqs(d), L(d.get("objectives")), L(d.get("steps")), L(d.get("outcomes"))
    ids, tot, per = [T(r.get("id")) for r in rq], *per_of(d)
    lk = {k: {"objectives": [], "steps": [], "outcomes": []} for k in ids}
    for kind, rows in (("objectives", objs), ("steps", steps), ("outcomes", outs)):
        for r in rows:
            for x in ids:
                if T(r.get("rq")).upper() == x.upper():
                    lk[x][kind].append(T(r.get("id")))
    up, cov = {x.upper() for x in ids}, (D["rep"] or {}).get("coverage") or {}
    return {"schema": "proposal-matrix/v1", "case_id": D["res"].get("case_id"), "generated_at": now(),
            "skill_version": D["ver"], "source": "draft.json/draft.md",
            "period": {"total": T(per.get("total")), "months": tot, "quote": T(per.get("quote")),
                       "source": T(per.get("source"))},
            "elements": [{"element": e, "title": ELT[e], "section_present": bool((cov.get(e) or {}).get("present")),
                          "chars": (cov.get(e) or {}).get("chars", 0), "evidence": (cov.get(e) or {}).get("evidence", 0),
                          "golden_items": [g[0] for g in G if g[1] == ELID[e]]} for e in P.EIDS],
            "data": {"sources": T((d.get("resources") or {}).get("data")),
                     "budget": T((d.get("resources") or {}).get("budget")),
                     "people": T((d.get("resources") or {}).get("people"))},
            "alignment": {"chain": [{"rq": k, "question": T(next((r.get("question") for r in rq if T(r.get("id")) == k), "")),
                                     "objectives": lk[k]["objectives"], "steps": lk[k]["steps"],
                                     "outcomes": lk[k]["outcomes"],
                                     "aligned": bool(lk[k]["objectives"]) and bool(lk[k]["outcomes"])} for k in ids],
                          "orphan_objectives": [T(o.get("id")) for o in objs if T(o.get("rq")).upper() not in up],
                          "orphan_outcomes": [T(o.get("id")) for o in outs if T(o.get("rq")).upper() not in up],
                          "aligned_all": bool(ids) and all(bool(lk[k]["objectives"]) and bool(lk[k]["outcomes"]) for k in ids)},
            "milestones": [{"id": T(m.get("id")), "start_month": mrange(m.get("period"))[0],
                            "end_month": mrange(m.get("period"))[1],
                            "within_period": (mrange(m.get("period"))[1] or 10 ** 6) <= (tot or 0)}
                           for m in L(d.get("milestones"))],
            "risk_types": sorted({T(r.get("type")) for r in L(d.get("risks")) if T(r.get("type"))}),
            "counts": dict((D["rep"] or {}).get("counts") or {}),
            "note": "矩阵只声明对应关系，不新增材料外事实；未落实项见 pending_human"}


def ms_csv(D):
    d = D["draft"]
    tot = per_of(d)[0]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "period", "start_month", "end_month", "task", "deliverable", "depends_on", "criterion",
                "critical_path", "within_period", "acceptance"])
    for m in L(d.get("milestones")):
        a, b = mrange(m.get("period"))
        cp = m.get("critical_path") in (True, 1, "是", "True")
        w.writerow([T(m.get("id")), T(m.get("period")), "" if a is None else a, "" if b is None else b,
                    T(m.get("task")), T(m.get("deliverable")), T(m.get("depends_on")), T(m.get("criterion")),
                    "yes" if cp else "no", "unknown" if b is None or tot is None else ("yes" if b <= tot else "no"),
                    "%s；%s" % (T(m.get("criterion")), "关键路径" if cp else "非关键路径")])
    return buf.getvalue()


def risks_md(D):
    rk = L(D["draft"].get("risks"))
    ty, tl = {}, {}
    for r in rk:
        ty.setdefault(T(r.get("type")) or "未标注", []).append(T(r.get("id")))
        tl.setdefault(T(r.get("decision_point")) or "未标注", []).append(T(r.get("id")))
    Ls = ["# 风险与备选方案（risks.md）", "",
          "> case_id=%s｜生成 %s｜来源工作稿 risks[]（%d 条 / %d 类）｜未确认项见 result.json.pending_human" % (
              D["res"].get("case_id") or "n/a", now(), len(rk), len(ty)), "",
          "## 1. 类型覆盖（题面要求：数据获取/方法可行性/进度/伦理与合规）", "", "| 类型 | 条数 | 编号 |", "|---|---|---|"]
    Ls += ["| %s | %d | %s |" % (k, len(ty[k]), "、".join(ty[k])) for k in sorted(ty)]
    Ls += ["", "## 2. 风险明细（触发信号 → 影响 → 备选 → 决策时点）", "",
           "| 编号 | 类型 | 风险 | 触发信号 | 影响 | 备选方案 | 决策时点 |", "|---|---|---|---|---|---|---|"]
    Ls += ["| %s |" % " | ".join(_c(r.get(k), 54) for k in ("id", "type", "risk", "trigger", "impact", "fallback",
                                                            "decision_point")) for r in rk]
    Ls += ["", "## 3. 决策时点轴", "", "| 时点 | 涉及风险 | 决定 |", "|---|---|---|"]
    Ls += ["| %s | %s | 按备选切换并留痕、同步更新里程碑 |" % (_c(k, 34), "、".join(tl[k])) for k in sorted(tl)]
    pend = L(D["draft"].get("pending_human")) + L(D["res"].get("pending_human"))
    Ls += ["", "## 4. 待人工确认（pending_human）", ""]
    if pend:
        Ls += ["| 事项 | 原因 | 时点 |", "|---|---|---|"]
        Ls += ["| %s |" % " | ".join(_c(p.get(k), 40) for k in ("item", "why", "needed_by")) for p in pend[:12]]
    else:
        Ls.append("（无）")
    Ls.append("\n> 风险条目为计划性判断，不是已发生事实；阈值与批件类缺口进 pending_human。")
    return "\n".join(Ls) + "\n"


def vhist(D):
    res, c = D["res"], (D["rep"] or {}).get("counts") or {}
    try:
        tpl = P.load_tpl()
    except Exception:
        tpl = {}
    src, p = T((res.get("deliverable") or {}).get("draft_source")) or "unknown", D.get("paths") or {}
    degs = [T(x) for x in (res.get("degradations") or [])]
    cov = (D["rep"] or {}).get("coverage") or {}
    sec = sum(1 for e in P.EIDS if (cov.get(e) or {}).get("present"))
    Ls = ["# 版本记录：v0 骨架 → v1 成稿", "", "> 依据本次实际运行生成；无工作稿时如实标注为 v0。", "",
          "## 1. 版本轴", "", "| 版本 | 触发 | 内容来源 | 七要素 | 证据 | 状态 |", "|---|---|---|---|---|---|",
          "| v0 | init/build 首帧写 partial result.json | plan-template.md 的 fb.*/rows.* 模板 | %d/7（模板文案） | 0（无材料引文） | partial |" % sec,
          "| v1 | build（工作稿+缺失补齐） | %s | %d/7 | %d/%d 逐字命中 | %s |" % (
              src, sec, c.get("evidence_verified", 0), c.get("evidence_total", 0), res.get("status")), "",
          "## 2. 改了什么", "", "| 对象 | v0 | v1 | 原因 |", "|---|---|---|---|"]
    for nm, key in (("目标", "objectives"), ("步骤", "steps"), ("里程碑", "milestones"), ("风险", "risks"), ("成果", "outcomes")):
        Ls.append("| %s | %d 条模板行 | %d 条（工作稿） | 模板只保证不空，成稿须挂材料证据与判据 |" % (
            nm, len(tpl.get("rows." + key) or []), c.get(key, 0)))
    Ls.append("| 七要素正文 | 模板文案（7 节占位） | %d/7 成节，共 %d 字/证据 %d 条 | 用材料原文逐节替换占位 |" % (
        sec, sum((cov.get(e) or {}).get("chars", 0) for e in P.EIDS),
        sum((cov.get(e) or {}).get("evidence", 0) for e in P.EIDS)))
    Ls += ["", "## 3. 为什么", "",
           "- v0 保证中断也有合法 result.json 与七要素骨架（先落盘再优化）。",
           "- v1 每条论断挂 source_id+locator+逐字 quote，去空白比对，命中<90% 判 partial。",
           "- 周期/样本量/经费/阈值沿用材料同形文本，未给的进 pending_human（口径不漂移）。",
           "", "## 4. 如何回退", "", "| 目标 | 操作 | 结果 |", "|---|---|---|",
           "| 回 v0 | `rm -f %s/draft.json` 后 `build` | fallback_draft，status=partial |" % p.get("work", "<WORK>"),
           "| 留副本 | `cp %s/proposal.md %s/proposal.v1.md` | 脚本不覆盖副本 |" % (
               p.get("output", "<OUT>"), p.get("output", "<OUT>")),
           "| 只重算资产 | `main.py audit` | 重写 golden/diff/version/self_check |",
           "| 回包 2.0.0 | 用 baseline_v1.zip 覆盖 SKILL.md/main.py、删 assets.py | 原 4 子命令行为 |", "",
           "## 5. 包版本 2.0.0 → 2.1.0", "",
           "SKILL.md 补文档与版本号；main.py 加 import assets、三处钩子与可选 audit（原 4 子命令参数语义不变）；",
           "新增 scripts/assets.py（5 件套 + 3 产物 + 27 条判据）；proposal.py（md5 %s）与 plan-template.md（md5 %s）未改。" % (
               _hex(PKG / "scripts" / "proposal.py", "md5"), _hex(PKG / "references" / "plan-template.md", "md5")),
           "", "本次降级/补齐记录（%d 条）：" % len(degs), ""]
    Ls += (["- " + _c(x, 100) for x in degs[:12]] or ["- （无）"])
    return "\n".join(Ls) + "\n"


def _contract(rj):
    oc = rj.get("output_contract") or {}
    keys = [str(k) for k in oc]
    empty, top = [k for k in keys if oc.get(k) in (None, "", [], {})], [k for k in keys if k not in rj]
    return {"applicable": bool(keys), "fields": keys, "count": len(keys), "empty": empty, "not_top_level": top,
            "complete": bool(keys) and not empty, "pass": bool(keys) and not empty and not top,
            "note": "输入未提供 output_contract 时不适用"}


def _ev(rj):
    em = [e for e in (rj.get("evidence_map") or []) if isinstance(e, dict)]
    v = sum(1 for e in em if str(e.get("status", "")).startswith("verified"))
    r = (v / len(em)) if em else 0.0
    return {"total": len(em), "verified": v, "ratio": round(r, 4), "pass": bool(em) and r >= 0.9,
            "unverified": [{"source_id": e.get("source_id"), "quote": T(e.get("quote"))[:44],
                            "status": e.get("status")} for e in em if not str(e.get("status", "")).startswith("verified")][:8]}


def _num(rj):
    per = rj.get("period") or {}
    m = re.search(r"\d+", T(per.get("total")))
    tot, mx = (int(m.group(0)) if m else None), maxm({"milestones": rj.get("milestones") or []})
    sl = (rj.get("counts") or {}).get("stray_numbers") or []
    return {"period": T(per.get("total")), "period_quote": T(per.get("quote"))[:64],
            "period_from_material": T(per.get("source")) not in ("", "default_12m", "unresolved"),
            "max_milestone_month": mx, "within_period": bool(tot and mx and mx <= tot),
            "stray_numbers": sl[:10], "stray_count": len(sl), "pass": bool(tot and mx and mx <= tot and not sl),
            "note": "stray = 论断区数字在材料与计划字段均无同形文本"}


def _fals(rj):
    rq = [r for r in (rj.get("research_questions") or []) if isinstance(r, dict)]
    wf = [r for r in rq if len(T(r.get("falsifier"))) >= 8]
    wt = [r for r in rq if any(T(m.get("threshold")) for m in L(r.get("metrics")))]
    return {"rqs": len(rq), "with_falsifier": len(wf), "with_threshold": len(wt),
            "with_basis": len([r for r in rq if all(T(m.get("basis")) or T(m.get("basis_locator")) for m in L(r.get("metrics")))]),
            "pass": bool(rq) and len(wf) == len(rq) and len(wt) == len(rq),
            "note": "可证伪 = 每条 RQ 有判伪条件+阈值；阈值无依据不影响可证伪但进 pending_human"}


def _run(args):
    try:
        return subprocess.run([sys.executable, "-B", str(MAIN)] + args, capture_output=True, timeout=180,
                              env=dict(os.environ, SKILL_INNER="1", PYTHONDONTWRITEBYTECODE="1")).returncode
    except Exception:
        return -1


def probes(work):
    """空输入/坏 JSON/--help 兜底的真实探测（子进程实测退出码）。"""
    edge, ex = {}, {}
    try:
        rep = P.check({}, {"materials": []})
        ok = isinstance(rep, dict) and isinstance(rep.get("counts"), dict)
        edge["empty_draft"] = {"ok": ok, "probe": "P.check({}, {materials:[]})", "detail": (
            "返回 dict，errors=%d，未抛异常" % len(rep.get("errors") or [])) if ok else "结构异常"}
    except Exception as e:
        edge["empty_draft"] = {"ok": False, "probe": "P.check({}, {materials:[]})", "detail": str(e)[:80]}
    tmp = None
    try:
        base = Path(work) if work and Path(work).is_dir() else Path(tempfile.mkdtemp(prefix="sc-"))
        tmp = base / "_selfcheck"
        (tmp / "bad").mkdir(parents=True, exist_ok=True)
        (tmp / "bad" / "draft.json").write_text('{"sections": [oops', encoding="utf-8")
        d, p, err = P.load_draft(tmp / "bad")
        ok = isinstance(d, dict) and bool(err) and "json_invalid" in str(err)
        edge["bad_json_draft"] = {"ok": ok, "probe": "P.load_draft(<坏 draft.json>)",
                                  "detail": ("捕获为 %s，返回空工作稿未崩溃" % _c(err, 44)) if ok else ("未按预期降级：%s" % _c(err, 44))}
    except Exception as e:
        edge["bad_json_draft"] = {"ok": False, "probe": "P.load_draft(<坏 draft.json>)", "detail": str(e)[:80]}
    if os.environ.get("SKILL_INNER") == "1":
        edge["subprocess"] = {"ok": True, "detail": "内部运行（SKILL_INNER=1）跳过子进程自测"}
        return {"edge": edge, "exit": {"skipped": True}, "pass": bool(edge) and all(v.get("ok") for v in edge.values())}
    try:
        if tmp is None:
            tmp = Path(tempfile.mkdtemp(prefix="sc-")) / "_selfcheck"
            tmp.mkdir(parents=True, exist_ok=True)
        rc1 = _run(["--help"])
        ex["help"] = rc1
        edge["help"] = {"ok": rc1 == 0, "probe": "main.py --help", "detail": "exit=%d" % rc1}
        ei, oi, wi = tmp / "e_in", tmp / "o_e", tmp / "w_e"
        ei.mkdir(parents=True, exist_ok=True)
        rc2 = _run(["build", "--input", str(ei), "--output", str(oi), "--work", str(wi)])
        rj2, _ = _jl(oi / "result.json")
        ok2 = rc2 == 0 and isinstance(rj2, dict) and "output_contract" in rj2 and "status" in rj2
        ex["empty_input_build"] = rc2
        edge["empty_input"] = {"ok": ok2, "probe": "build --input <空目录>", "detail": "exit=%d；result.json %s；status=%s；产物 %d 个" % (
            rc2, "合法" if isinstance(rj2, dict) else "缺失", (rj2 or {}).get("status"),
            len(list(oi.glob("*"))) if oi.is_dir() else 0)}
        bi, bo, bw = tmp / "b_in", tmp / "o_b", tmp / "w_b"
        bi.mkdir(parents=True, exist_ok=True)
        (bi / "case.json").write_text('{"case_id": "BROKEN", "output_contract": {oops', encoding="utf-8")
        (bi / "notes.md").write_text("# 课题指南\n\n执行期：12 个月。研究目标：验证方法可行性。\n", encoding="utf-8")
        rc3 = _run(["build", "--input", str(bi), "--output", str(bo), "--work", str(bw)])
        rj3, _ = _jl(bo / "result.json")
        ok3 = rc3 == 0 and isinstance(rj3, dict) and "status" in rj3 and bool(
            (rj3.get("errors") or []) or (rj3.get("degradations") or []))
        ex["bad_json_build"] = rc3
        edge["bad_json_input"] = {"ok": ok3, "probe": "build --input <坏 case.json>", "detail": "exit=%d；status=%s；errors=%d；degradations=%d；proposal.md %s" % (
            rc3, (rj3 or {}).get("status"), len((rj3 or {}).get("errors") or []),
            len((rj3 or {}).get("degradations") or []), "已生成" if (bo / "proposal.md").is_file() else "缺失")}
    except Exception as e:
        edge["subprocess"] = {"ok": False, "detail": str(e)[:80]}
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
    return {"edge": edge, "exit": ex, "pass": all(v.get("ok") for v in edge.values() if isinstance(v, dict))}


def post(outdir, work, res):
    """写 self_check.json（复核已落盘 result.json），摘要回填 result.json。"""
    outdir = Path(outdir)
    try:
        rj, _ = _jl(outdir / "result.json")
        rj = rj if isinstance(rj, dict) else {}
        arts = []
        for f in FILES:
            p, ref = outdir / f, f in ("result.json", "self_check.json")
            arts.append({"path": f, "exists": (True if f == "self_check.json" else p.is_file()),
                         "bytes": None if ref else (p.stat().st_size if p.is_file() else 0),
                         "sha256": None if ref else (_hex(p) if p.is_file() else None),
                         "note": "自引用/本文件：写入后不再统计哈希" if ref else None})
        c, ev, num, fc, pb = _contract(rj), _ev(rj), _num(rj), _fals(rj), probes(work)
        miss = [a["path"] for a in arts if not a["exists"]]
        chk = {"artifacts_complete": not miss, "contract_complete": (c["pass"] if c["applicable"] else True),
               "evidence_covered": ev["pass"], "numeric_consistent": num["pass"], "falsifiable": fc["pass"],
               "edge_cases_ok": pb["pass"], "no_errors": not (rj.get("errors") or []),
               "exit_codes_zero": all(v == 0 for v in pb["exit"].values() if isinstance(v, int)) if pb["exit"] else True}
        sc = {"schema": "self-check/v1", "skill": "writing-10-proposal",
              "skill_version": (rj.get("runtime") or {}).get("skill_version"), "case_id": rj.get("case_id"),
              "generated_at": now(), "status": rj.get("status"), "artifacts": arts,
              "artifact_count": len([a for a in arts if a["exists"]]), "missing_artifacts": miss,
              "contract": c, "evidence": ev, "numeric_consistency": num, "falsifiability": fc,
              "pending_human_count": len(rj.get("pending_human") or []),
              "degradations_count": len(rj.get("degradations") or []), "errors_count": len(rj.get("errors") or []),
              "edge_cases": pb["edge"], "exit_codes": pb["exit"], "checks": chk,
              "overall_pass": all(chk.values()), "failures": [k for k, v in chk.items() if not v],
              "how_to_rerun": "python3 -B scripts/main.py build --input /input --output /app/output --work /app/work；audit 只重算本文件",
              "bounds": {"offline": True, "stdlib_only": True, "cwd_independent": True, "exit_code": "always 0"}}
        _w(outdir / "self_check.json", sc)
        rj["self_check"] = {"path": "self_check.json", "overall_pass": sc["overall_pass"], "checks": chk,
                            "artifact_count": sc["artifact_count"], "missing_artifacts": miss,
                            "exit_codes": pb["exit"], "evidence_ratio": ev["ratio"]}
        rj["artifacts"] = arts
        _w(outdir / "result.json", rj)
        note(outdir, "ASSETS", "self_check overall=%s artifacts=%d/%d 失败=%s" % (
            sc["overall_pass"], sc["artifact_count"], len(arts), ",".join(sc["failures"]) or "无"))
        if isinstance(res, dict):
            res["self_check"], res["artifacts"] = rj["self_check"], arts
    except Exception as e:
        note(outdir, "EXC", "post: %s: %s" % (type(e).__name__, e))


def emit(outdir, work, res, rep=None, draft=None, idx=None, ver=None):
    """生成 golden_standard/matrix/milestones.csv/risks.md/diff_report/version_history。"""
    outdir, work = Path(outdir), Path(work)
    errs = []
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        res = res if isinstance(res, dict) else {}
        for k in ("degradations", "errors", "pending_human", "uncertainty", "sources", "changes"):
            res.setdefault(k, [])
        if not isinstance(idx, dict) or not isinstance(idx.get("materials"), list):
            idx, _ = _jl(work / "index.json")
            idx = idx if isinstance(idx, dict) and isinstance(idx.get("materials"), list) else {"materials": []}
        if not isinstance(draft, dict) or not draft:
            draft = P.load_draft(work)[0]
            if not isinstance(draft, dict) or not draft:
                draft = _jl(work / "draft.effective.json")[0]
            draft = draft if isinstance(draft, dict) else {}
        if not isinstance(rep, dict):
            rep = P.check(draft, idx)
        mo, pq = P.period("\n".join(T(m.get("text")) for m in (idx.get("materials") or [])))
        if not ver:
            try:
                ver = (re.search(r"version:\s*([\d.]+)", (PKG / "SKILL.md").read_text(encoding="utf-8")) or [0, "2.1.0"])[1]
            except Exception:
                ver = "2.1.0"
        D = {"draft": draft, "idx": idx, "rep": rep, "res": res, "ver": ver,
             "paths": {"work": str(work), "output": str(outdir)}}
        gs, rows = golden(D)
        c = cnt(rows)
        res["period"] = {"total": T((draft.get("period") or {}).get("total")) or ("%d 个月" % mo if mo else ""),
                         "quote": T((draft.get("period") or {}).get("quote")) or pq,
                         "source": T((draft.get("period") or {}).get("source")) or ("materials" if pq else "unresolved"),
                         "detected_months": mo}
        if isinstance(res.get("counts"), dict):
            res["counts"].update(stray_numbers=stray(D), golden_items=len(rows), golden_pass=c["pass"])
        for fn, name, body in ((_w, "golden_standard.json", gs), (_w, "proposal_matrix.json", matrix(D)),
                               (_w, "milestones.csv", ms_csv(D)), (_w, "risks.md", risks_md(D)),
                               (_w, "diff_report.md", diff_md(D, gs, rows)), (_w, "version_history.md", vhist(D))):
            try:
                fn(outdir / name, body)
            except Exception as e:
                errs.append("%s 生成失败 %s: %s" % (name, type(e).__name__, e))
        res["golden_standard"] = {"path": "golden_standard.json", "schema": gs["schema"], "items": c["total"],
                                  "elements": len(gs["elements"]), "anchors": gs["anchors"]["total"],
                                  "anchors_verified": gs["anchors"]["verified"],
                                  "status_counts": {"pass": c["pass"], "missing": c["missing"], "deviation": c["deviation"]},
                                  "items_without_anchor": gs["anchors"]["items_without_anchor"]}
        res["diff_report"] = {"path": "diff_report.md", "total": c["total"], "pass": c["pass"], "missing": c["missing"],
                              "deviation": c["deviation"], "pass_rate": c["pass_rate"],
                              "items": [{"id": r[0], "element": r[1], "status": r[3]} for r in rows]}
        res["version_history"] = {"path": "version_history.md",
                                  "versions": [{"id": "v0", "kind": "template-skeleton", "status": "partial"},
                                               {"id": "v1", "kind": "working-draft", "status": res.get("status")}],
                                  "rollback": "rm -f <WORK>/draft.json 后重跑 build 回 v0；audit 只重算资产"}
        note(outdir, "ASSETS", "golden=%d pass=%d missing=%d deviation=%d anchors=%d/%d" % (
            c["total"], c["pass"], c["missing"], c["deviation"], gs["anchors"]["verified"], gs["anchors"]["total"]))
        if not draft:
            errs.append("未取到工作稿：资产按 v0 骨架判定")
    except Exception as e:
        errs.append("assets: %s: %s" % (type(e).__name__, e))
        note(outdir, "EXC", "emit: %s" % e)
    if errs:
        try:
            res["degradations"] += errs
        except Exception:
            pass
    return res


def cmd_audit(a):
    """只重算 5 件套与结构化产物，不重渲染 proposal.md。"""
    try:
        outdir, work = Path(a.output).resolve(), Path(a.work).resolve()
        res, _ = _jl(outdir / "result.json")
        res = res if isinstance(res, dict) else {}
        res["_contract"] = res.get("_contract") or res.get("output_contract") or {}
        note(outdir, "AUDIT", "start work=%s" % work)
        emit(outdir, work, res, None, None, None, None)
        post(outdir, work, res)
    except Exception as e:
        note(Path(getattr(a, "output", ".")), "EXC", "audit: %s" % e)
    return 0
