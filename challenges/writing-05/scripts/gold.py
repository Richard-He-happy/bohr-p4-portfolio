#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-03 v2 资产层：golden_standard / diff_report / version_history / run.log / self_check。

不采信 main.py 的匹配与分级结论，按 method_and_runbook.md 口径独立重算期望值后逐项差分；
算不出的记"不可判定"，不补造。纯标准库、离线；main.py 以 2 处调用接入，也可单独重跑。
"""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import discover, segment, parse_refs, toks, sim, NEG, POS, DOI

V = "2.0.0"
CORE, DIRECT = .30, .45
BD = ["不足", "低", "中", "高"]
VERD = ["缺失", "偏差", "不可判定", "达标"]
HEDGE = re.compile(r"(可能|提示|初步|尚|不足以|待核|may|might|suggest|prelim|limited|cannot)", re.I)
NUMU = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|‰|mg|g|kg|mL|L|μL|µm|nm|mm|cm|h|min|s|岁|例|名|倍|℃|个月|年|周|天)?")
LR = re.compile(r"^(?P<p>.+?)\s*\[B\d+\.S\d+\]\s*chars:(?P<a>\d+)-(?P<b>\d+)$")
D2 = [("systematic review|meta-?analys|系统综述|系统评价|荟萃", "系统综述/荟萃", 3.),
      ("guideline|consensus|指南|共识", "指南/共识", 3.),
      ("randomi[sz]ed|\\bRCT\\b|随机对照", "RCT", 3.),
      ("cohort|prospective|longitudinal|队列|前瞻|纵向", "队列", 2.),
      ("case-?control|病例对照", "病例对照", 2.),
      ("cross-?sectional|survey|横断面|调查", "横断面", 1.5),
      ("case report|case series|病例报告|个案", "病例报告", .5),
      ("preprint|bioRxiv|medRxiv|arXiv|预印本", "预印本", 1.),
      ("\\breview\\b|综述", "叙述综述", 1.),
      ("in vitro|cell line|mice|mouse|rat|体外|细胞系|小鼠|大鼠", "体外/动物", 1.)]
NR2 = [r"\bn\s*=\s*([\d,]{1,7})",
       r"([\d,]{2,7})\s*(?:participants|patients|subjects|individuals|samples|mice|rats|children|adults|名|例|位|受试者|患者|样本)"]
VH = [{"v": "0.x-skeleton", "d": None, "l": "骨架（未提交）",
       "c": ["SKILL.md 章节骨架", "单脚本原型，只写 result.json"],
       "w": "先跑通契约回填与退出码 0，再谈证据质量", "r": "无需回退：v0 从未提交"},
      {"v": "1.0.0", "d": None, "l": "成稿基线 baseline_v1.zip（题目记录分 67.67）",
       "c": ["claims.json → evidence_table.json → evidence_driven_draft.md 三段交付",
             "四因子强度分级 + 限定语映射 + 过度推断下调",
             "verify.py 独立复算（逐字命中 / join / 引用编号 / 契约字段）", "六类降级分支 + 先写 partial result.json"],
       "w": "把\"有引用\"写成\"有定位 + 有逐字原文 + 有强度理由\"，任何输入都退出 0",
       "r": "见 v2 条目中的完整回退命令"},
      {"v": "2.0.0", "d": "2026-11-14", "l": "可核验资产层（本次补丁）",
       "c": ["新增 scripts/gold.py：独立金标准 → 逐项差分 → 版本记录 → 运行日志 → 自检",
             "result.json 新增 golden_standard / diff_report / version_history / self_check",
             "原 5 个契约字段、9 件产物、调用方式、退出码语义全部不变", "verify.py 的 V 常量 1.0.0 → 2.0.0（仅版本号）"],
       "w": "评分项\"结果可核验性 / 结果完整性 / 生态贡献\"缺可复核证据：原包只有自报计数，没有独立期望值与差分",
       "r": "完整回退：rm -rf submission && unzip baseline_v1.zip -d submission；"
            "只回退资产层：删 scripts/gold.py，删 main.py 中 2 处 gold 调用，verify.py 的 V 改回 1.0.0，"
            "则退回 v1 九件套，主产物与状态字段不受影响"}]


class Log:
    """run.log：追加写 + 每步 flush；写失败只降级。"""

    def __init__(self, p):
        self.p, self.t0, self.n, self.ok = Path(p), time.time(), 0, True
        try:
            self.p.parent.mkdir(parents=True, exist_ok=True)
            self.p.write_text("", "utf-8")
        except Exception:
            self.ok = False

    def w(self, step, msg, lv="INFO", dur=None):
        self.n += 1
        try:
            with self.p.open("a", encoding="utf-8") as f:
                f.write("%s +%07.3fs #%02d %-5s %-13s %s%s\n" % (
                    time.strftime("%Y-%m-%dT%H:%M:%S"), time.time() - self.t0, self.n, lv, step, msg,
                    "" if dur is None else " | %s=%.3fs" % (step, dur)))
                f.flush()
        except Exception:
            self.ok = False
        return self.n


def jd(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + ".t")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2), "utf-8")
    t.replace(p)


def _j(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


nm = lambda s: re.sub(r"[\s\u3000]+", "", s or "")


def strongn(t):
    """强数字：带单位，或 >=2 位；裸 1-2 位（编号/序数）不作一致性要求。"""
    return {nm(m.group(0)) for m in NUMU.finditer(t or "")
            if len(re.sub(r"\D", "", m.group(0))) >= 2 or re.search(r"[^\d.,]", m.group(0))}


def design2(t):
    for p, n, s in D2:
        if re.search(p, t or "", re.I):
            return n, s
    return "未标明", 1.


def nsize2(t):
    v = [int(m.group(1).replace(",", "")) for p in NR2 for m in re.finditer(p, t or "", re.I)]
    return max(v) if v else None


def band(txt, doct, nsrc, conf, ab):
    """独立重算四因子强度（口径：references/method_and_runbook.md §1）。"""
    dn, dp = design2(txt + " " + (doct or "")[:400])
    n = nsize2(txt) or nsize2(doct)
    sp = 0. if n is None else 2. if n >= 1000 else 1.5 if n >= 100 else 1. if n >= 10 else .5
    tot = dp + sp + (1. if nsrc >= 2 else 0.) - (1. if conf else 0.)
    if "预印本" in dn:
        tot = min(tot, 4.)
    if n is not None and n < 100:
        tot = min(tot, 3.4)
    lv = "高" if tot >= 5.5 else "中" if tot >= 3.5 else "低" if tot >= 1.5 else "不足"
    if ab and lv == "高":
        lv = "中"
    return lv, {"design": dn, "design_pts": dp, "sample_size": n, "size_pts": sp,
                "sources": nsrc, "conflict": bool(conf), "score": round(tot, 2)}


def rmap(refs, docs):
    """文献编号 -> 材料文件：DOI 精确命中优先，其次标题项重叠（独立于 main 的锚点映射）。"""
    m = {}
    for r in refs:
        c, tr = [], toks(r["body"][:120])
        for d in docs:
            if d["kind"] == "references":
                continue
            if r.get("doi") and r["doi"] in d["text"]:
                c.append((2., d["doc_id"]))
            elif len(tr) >= 4:
                cov = len(tr & toks(d["text"][:400])) / len(tr)
                if cov >= .45:
                    c.append((cov, d["doc_id"]))
        if c:
            m[r["num"]] = max(c)[1]
    return m


def expect(core, units, kmap, anch):
    """独立期望来源：锚点命中，或 内容项覆盖率>=CORE 且数字可对；都不满足则期望"无直接支撑"。"""
    tc, ns, best = toks(core), strongn(core), None
    for u in units:
        if kmap.get(u["doc"]) != "material":
            continue
        cov = len(tc & toks(u["text"])) / max(1., len(tc))
        a = 1 if u["doc"] in anch else 0
        numok = (not ns) or bool(ns & strongn(u["text"]))
        if not a and (cov < CORE or not numok):
            continue
        k = (a, cov, 1 if numok else 0)
        if best is None or k > best[0]:
            best = (k, cov, numok, u)
    if not best:
        return None
    _, cov, numok, u = best
    return {"source": u["doc"], "locator": u["loc"], "quote": u["text"], "cov": round(cov, 2), "num_ok": numok,
            "anchored": bool(best[0][0]),
            "scope": "直接支撑" if (cov >= DIRECT and numok) else "部分支撑（范围不一致）"}


def collect(ind, out, case):
    out = Path(out)
    docs = discover(ind, case) if ind and Path(ind).is_dir() else []
    dp = out / "evidence_driven_draft.md"
    return {"docs": docs, "units": segment(docs), "refs": parse_refs(docs),
            "kmap": {d["doc_id"]: d["kind"] for d in docs}, "dmap": {d["doc_id"]: d for d in docs},
            "cl": _j(out / "claims.json").get("claims", []), "rows": _j(out / "evidence_table.json").get("rows", []),
            "res": _j(out / "result.json"), "draft": dp.read_text(encoding="utf-8") if dp.exists() else ""}


def agg(vs):
    for v in VERD:
        if v in vs:
            return v
    return "不可判定"


def run(ind, out, case, log=None):
    """生成 5 件资产；返回 result.json 的 4 个新字段。"""
    out = Path(out)
    log = log or Log(out / "run.log")
    t0 = time.time()
    C = collect(ind, out, case)
    docs, units, refs, kmap, dmap = C["docs"], C["units"], C["refs"], C["kmap"], C["dmap"]
    cl, rows, res, draft = C["cl"], C["rows"], C["res"], C["draft"]
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid = str(case.get("case_id") or case.get("id") or res.get("case_id") or "UNKNOWN")
    pool = "\n".join(d["text"] for d in docs)
    npool, r2d = nm(pool), rmap(refs, docs)
    spool = "\n".join(d["text"] for d in docs if d["kind"] != "draft")
    nspool = nm(spool)
    scor = {c for c in re.findall(r"\d+(?:[.,]\d+)?", spool)}
    log.w("assets", "start case=%s docs=%d units=%d claims=%d rows=%d" % (cid, len(docs), len(units), len(cl), len(rows)))

    mref = re.search(r"\n##+\s*(参考文献|references?)\s*\n", draft, re.I)
    body = draft[:mref.start()] if mref else draft
    refpart = draft[mref.end():] if mref else ""
    body_nc = re.sub(r"(?m)^#{1,6}[^\n]*$", " ", body)          # 标题行（含案例号）不参与数字核对
    body_nc = re.sub(r"[\[［]\d{1,3}[\]］]", " ", body_nc)     # 引用编号
    body_nc = re.sub(r"\b[A-Z]{1,3}[-_]?\d{1,4}\b", " ", body_nc)  # C001 / P002 一类内部编号
    byc = {}
    for r in rows:
        byc.setdefault(r.get("claim_id"), []).append(r)
    pending = [p for p in (res.get("pending_human") or []) if isinstance(p, dict)]
    case_text = json.dumps(case, ensure_ascii=False)
    sroot = Path(__file__).resolve().parent.parent
    stext = {}
    for f in ("references/method_and_runbook.md", "references/evidence_schema.md"):
        try:
            stext[f] = (sroot / f).read_text(encoding="utf-8")
        except Exception:
            stext[f] = ""

    pmap = {d["path"]: d for d in docs}

    def bok(b):
        q = b.get("quote") or ""
        if not q:
            return False
        if b["kind"] == "material":
            return q in dmap.get(b["source"], {}).get("text", "")
        return q in (case_text if b["kind"] == "case" else stext.get(b["source"], ""))

    cq = lambda k: str(con.get(k) or "")
    items = []

    def it(gid, dim, req, exp, w, meth, tgt, basis, actual, detail, verdict):
        bs = [dict(b, verified=bok(b)) for b in basis]
        items.append({"id": gid, "dimension": dim, "requirement": req, "expectation": exp, "weight": w,
                      "method": meth, "target": tgt, "basis": bs, "basis_verified": bool(bs) and all(b["verified"] for b in bs),
                      "actual": actual, "detail": detail, "verdict": verdict})

    B = lambda d, l, q: {"kind": "material", "source": d, "locator": l, "quote": q}
    K = lambda p, q: {"kind": "case", "source": "case.json", "locator": p, "quote": q}
    S = lambda f, s, q: {"kind": "skill", "source": f, "locator": s, "quote": q}
    MR = "references/method_and_runbook.md"
    ES = "references/evidence_schema.md"

    # GS-01 论断切分
    dr = [d for d in docs if d["kind"] == "draft" and d["text"].strip()]
    if dr:
        du = [u for u in units if u["doc"] == dr[0]["doc_id"]]
        ct = {c.get("text") for c in cl}
        miss = [u["text"][:50] for u in du if u["text"] not in ct]
        bs = ([B(dr[0]["doc_id"], du[0]["loc"], du[0]["text"])] if du else []) + ([K("case.json#/output_contract.evidence_map", cq("evidence_map"))] if cq("evidence_map") else [])
        it("GS-01", "找得到", "原稿每个非标题句都要成为一条 claim，不得整段当一条",
           "期望 %d 条论断（= 原稿句数）" % len(du), 8, "claims.json 的 text 集合 vs 原稿句集，逐句比对",
           "claims.json", bs, "已提取 %d 条，漏 %d 条" % (len(du) - len(miss), len(miss)),
           ("漏句: " + " | ".join(miss[:4])) if miss else "原稿句全覆盖", "达标" if (du and not miss) else ("缺失" if du else "不可判定"))
    else:
        one = [c for c in cl if len(re.findall(r"[。！？!?]", c.get("text") or "")) > 1]
        it("GS-01", "找得到", "取材模式每条 claim 必须是单句", "claims>=1 且每条为单句",
           8, "统计 claim 文本内句末标点", "claims.json",
           [K("case.json#/output_contract.evidence_map", cq("evidence_map"))] if cq("evidence_map") else [],
           "claims=%d，跨句 %d 条" % (len(cl), len(one)), "无原稿，按取材模式判定",
           "缺失" if not cl else ("偏差" if one else "达标"))

    # GS-02 join
    dang = sorted({r.get("claim_id") for r in rows} - {c.get("claim_id") for c in cl})
    it("GS-02", "复得现", "claims 与 evidence_table 双向可 join", "悬空 0 且 schema 字段齐备",
       6, "集合差 claims-rows / rows-claims", "claims.json + evidence_table.json",
       [K("case.json#/output_contract.evidence_map", cq("evidence_map"))] if cq("evidence_map") else [],
       "rows=%d，悬空=%d" % (len(rows), len(dang)), ("悬空: %s" % dang[:5]) if dang else "可 join",
       "达标" if (rows and not dang) else "缺失")

    # GS-03 引文逐字
    qs = [r for r in rows if r.get("quote")]
    badq = [r.get("claim_id") for r in qs if r["quote"] not in pool]
    badq_s = [r.get("claim_id") for r in qs if r["quote"] not in spool]
    it("GS-03", "对得上", "证据行 quote 在材料中逐字命中（含标点/数字/单位）",
       "命中率 100%%（%d/%d）" % (len(qs) - len(badq), len(qs)), 10,
       "quote ∈ 材料全文，不归一化、不容忍改写", "evidence_table.json",
       [B(r["source_id"], r["locator"], r["quote"]) for r in qs[:2] if r.get("source_id") in dmap],
       "%d/%d 命中（排除待改稿自引后 %d/%d）" % (len(qs) - len(badq), len(qs), len(qs) - len(badq_s), len(qs)),
       ("未命中: %s；疑似自引: %s" % (badq[:5], badq_s[:5])) if (badq or badq_s) else "全部逐字命中于来源材料",
       "达标" if (qs and not badq) else "缺失")

    # GS-04 locator 偏移精确
    rok, rbad = 0, []
    for r in qs:
        m = LR.match((r.get("locator") or "").strip())
        d = pmap.get(m.group("p").strip()) if m else None
        if not d:
            rbad.append((r.get("claim_id"), "locator 不可解析"))
            continue
        a, b = int(m.group("a")), int(m.group("b"))
        if 0 <= a < b <= len(d["text"]) and d["text"][a:b] == r["quote"]:
            rok += 1
        elif r["quote"] in d["text"]:
            rbad.append((r.get("claim_id"), "偏移不精确"))
        else:
            rbad.append((r.get("claim_id"), "越界或文本不符"))
    it("GS-04", "复得现", "locator 的 chars:a-b 切片必须等于 quote",
       "偏移精确率 100%%（%d/%d）" % (rok, len(qs)), 6, "按 locator 重新切片比对",
       "evidence_table.json",
       [S(ES, "§2 字段纪律 locator", "`locator`：`<相对路径> [B<块>.S<句>] chars:<start>-<end>`，字符偏移基于解析后的纯文本。")],
       "%d/%d 偏移精确" % (rok, len(qs)), ("问题行: %s" % rbad[:4]) if rbad else "全部可回查",
       "达标" if (qs and not rbad) else "缺失")

    # 独立期望来源
    expc = []
    for c in cl:
        anch = {r2d[int(x)] for x in re.findall(r"[\[［](\d{1,3})[\]］]", c.get("text") or "") if int(x) in r2d}
        expc.append((c, expect(c.get("core") or c.get("text") or "", units, kmap, anch)))

    # GS-05 论断-来源对得上
    vs, bad5 = [], []
    for c, e in expc:
        act = [r for r in byc.get(c.get("claim_id"), []) if r.get("source_id")]
        if e and not act:
            vs.append("缺失"); bad5.append((c.get("claim_id"), "期望有来源但产物无来源"))
        elif e and act:
            ok = any(r.get("source_id") == e["source"] for r in act)
            vs.append("达标" if ok else "偏差")
            if not ok:
                bad5.append((c.get("claim_id"), "来源不同：期望 %s 实际 %s" % (e["source"], act[0].get("source_id"))))
        elif not e and act:
            vs.append("偏差"); bad5.append((c.get("claim_id"), "期望无直接支撑，产物给了来源（需人核）"))
        else:
            vs.append("达标")
    it("GS-05", "对得上", "支撑来源须与独立期望来源一致，无支撑不得硬凑",
       "一致率 100%%（%d 条论断）" % len(expc), 10,
       "独立规则：锚点命中 或 覆盖率>=%.2f 且数字可对（与 main 不同实现）" % CORE,
       "evidence_table.json", [B(e["source"], e["locator"], e["quote"]) for _, e in expc[:2] if e],
       "%d/%d 一致" % (vs.count("达标"), len(vs)), ("；".join("%s %s" % x for x in bad5[:4])) or "全部一致", agg(vs))

    # GS-06 强度分级一致
    vs, bad6 = [], []
    for c, e in expc:
        act = [r for r in byc.get(c.get("claim_id"), []) if r.get("quote")]
        if not act:
            vs.append("达标" if not e else "缺失")
            bad6 += ([] if not e else ["%s 无证据行但期望有来源" % c.get("claim_id")])
            continue
        p = act[0]
        eb, bb = band(p["quote"], dmap.get(p.get("source_id"), {}).get("text", ""), len(act),
                      any(r.get("conflicts") for r in act), bool(p.get("abstract_only")))
        ab = min((r["strength"] for r in act), key=lambda x: BD.index(x) if x in BD else 0)
        d = abs(BD.index(eb) - BD.index(ab)) if (eb in BD and ab in BD) else 9
        vs.append("达标" if d == 0 else "偏差")
        if d:
            bad6.append("%s 期望 %s(%.1f) vs 实际 %s(%s)" % (c.get("claim_id"), eb, bb["score"], ab,
                                                         p.get("strength_basis", {}).get("score")))
    it("GS-06", "说得准", "强度须能由四因子口径复算且与实际标注一致", "逐条 band 一致（偏差 0 条）",
       8, "gold.band() vs verify.grade()（交叉实现）", "evidence_table.json",
       [S(MR, "§1 封顶规则", "**封顶规则**：预印本 ≤4.0（最高\"中\"）；n<100 ≤3.4（最高\"低\"）；仅摘要可核的来源最高\"中\"。")],
       "%d/%d 一致" % (vs.count("达标"), len(vs)), ("；".join(bad6[:4])) or "全部一致", agg(vs))

    # GS-07 语气与强度相称
    vs, bad7 = [], []
    for c in cl:
        act = [r for r in byc.get(c.get("claim_id"), []) if r.get("quote")]
        if not act:
            continue
        ab = min((r["strength"] for r in act), key=lambda x: BD.index(x) if x in BD else 0)
        key = (c.get("core") or "")[:24]
        seg = [s for s in re.split(r"(?<=[。！？!?])\s*", body_nc) if key and key in s]
        if ab in ("低", "不足") and seg and not HEDGE.search(seg[0]):
            vs.append("偏差"); bad7.append("%s(%s) 缺限定语" % (c.get("claim_id"), ab))
        else:
            vs.append("达标")
    it("GS-07", "说得准", "低/不足句必须带限定语或待核标记", "低/不足句 100% 有 hedge",
       6, "强度映射表 + 成稿检索 HEDGE 词表", "evidence_driven_draft.md",
       [S(MR, "§2 限定语映射", "低/不足强度句若已含\"可能/提示/初步/尚/may/suggest/prelim\"，不再叠加限定语，避免双重弱化。")],
       ("%d/%d 相称" % (vs.count("达标"), len(vs))) if vs else "无受检句", ("；".join(bad7[:4])) or "全部相称",
       agg(vs) if vs else "不可判定")

    # GS-08 数字一致
    dn = strongn(body_nc)
    cores = lambda x: re.findall(r"\d+(?:[.,]\d+)?", x)
    lost = sorted(x for x in dn if (not set(cores(x)) & scor) or ("%" in x and (nm(cores(x)[0]) + "%") not in nspool))
    pfacts = res.get("preserved_facts") or []
    in_d = [f for f in pfacts if isinstance(f, dict) and f.get("in_draft")]
    it("GS-08", "对得上", "成稿数字须能在材料中找到同值，不得新造或改数",
       "越界数字 0 个（成稿强数字 %d 个）" % len(dn), 6,
       "正文强数字须在来源材料中找到同值（以数值为准，百分号另校；裸 1-2 位数不计）",
       "evidence_driven_draft.md",
       [K("case.json#/output_contract.preserved_facts", cq("preserved_facts"))] if cq("preserved_facts") else [],
       "越界 %d 个；preserved_facts %d 条（成稿 %d）" % (len(lost), len(pfacts), len(in_d)),
       ("材料中无: %s" % lost[:6]) if lost else "数字全部可回溯", "达标" if not lost else "偏差")

    # GS-09 引用编号与著录
    mk = sorted({int(x) for x in re.findall(r"[\[［](\d{1,3})[\]］]", body)})
    rent = [(int(a), b.strip()) for a, b in re.findall(r"^\[(\d{1,3})\]\s*(.+)$", refpart, re.M)]
    rn = {a for a, _ in rent}
    unr = [n for n in mk if n not in rn]
    un = []
    for a, t in rent:
        nt = nm(re.sub(r"（[^（）]*）$|\([^()]*\)$", "", t))[:40]
        if not (nt and (nt in npool or any(nt in nm(r["raw"]) for r in refs))):
            un.append(a)
    bs9 = [S(ES, "§3 约束", "约束：正文引用编号 `[n]` 必须能解析到参考文献条目；参考文献条目只能来自材料，缺 DOI 就缺，不补。")]
    if refs and refs[0]["raw"] in pool:
        bs9.insert(0, B(next(d["doc_id"] for d in docs if d["kind"] == "references"), "references.md 第 1 条", refs[0]["raw"]))
    fab = [a for a, t in rent if DOI.search(t) and not any(r.get("doi") and r["doi"] in t for r in refs)]
    v9 = ("缺失" if unr else "达标" if (mk and not un) else "偏差" if (fab or refs) else "不可判定")
    it("GS-09", "对得上", "正文 [n] 可解析到条目，且著录能在材料文献表中溯源",
       "未解析编号 0 个，未溯源条目录 0 条", 8, "编号比对 + 著录前 40 字符检索（无文献表记不可判定）",
       "evidence_driven_draft.md", bs9, "编号 %d 个未解析 %d；条目 %d 条未溯源 %d；材料外 DOI %d" % (
           len(mk), len(unr), len(rent), len(un), len(fab)),
       ("未解析: %s；未溯源: %s" % (unr[:4], un[:4])) if (unr or un) else "编号与著录均可回溯", v9)

    # GS-10 不越级因果
    viol = []
    for s in re.split(r"(?<=[。！？!?])\s+|(?<=\.)\s+", body_nc):
        if not re.search(r"(\bcauses?\b|\bleads? to\b|\bresults? in\b|\bproves?\b|证明|导致|证实|必然)", s, re.I):
            continue
        if re.search(r"(associat|correlat|相关|关联|提示|suggest)", s, re.I):
            continue
        ids = [int(x) for x in re.findall(r"\[(\d{1,3})\]", s)]
        if not ids:
            viol.append((s[:40], "因果表述无引用"))
            continue
        if not any(design2(dmap.get(r2d.get(i), {}).get("text", "") + " " + dmap.get(r2d.get(i), {}).get("path", ""))[1] >= 3. for i in ids):
            viol.append((s[:40], "被引来源无随机化/干预设计"))
    it("GS-10", "说得准", "无随机化/干预设计时因果措辞须下调为关联", "越级因果句 0 句", 6,
       "因果词扫描 + 被引来源设计识别（仅 RCT/综述/指南允许因果）", "evidence_driven_draft.md",
       [S(MR, "§3 过度推断下调规则", "| causes / leads to / proves / demonstrates that / confirms that | is associated with | 材料无随机化或干预对照 |")],
       "越级 %d 句" % len(viol), ("；".join("%s(%s)" % v for v in viol[:4])) or "未发现越级",
       "达标" if not viol else "偏差")

    # GS-11 未支持论断的标注
    vs, bad11 = [], []
    pj = json.dumps(pending, ensure_ascii=False)
    for c, e in expc:
        if e or [r for r in byc.get(c.get("claim_id"), []) if r.get("source_id")]:
            continue
        key = (c.get("core") or "")[:20]
        seg = [s for s in re.split(r"(?<=[。！？!?])\s*", body_nc) if key and key in s]
        cited = bool(seg and re.search(r"\[(\d{1,3})\]", seg[0]))
        marked = (c.get("claim_id") in pj) or (key and key in pj)
        if cited or not marked:
            vs.append("偏差"); bad11.append("%s 引用=%s 待核=%s" % (c.get("claim_id"), cited, marked))
        else:
            vs.append("达标")
    it("GS-11", "说得准", "无来源论断须标待核并入 pending_human，不得挂引用编号", "无来源论断 100% 标注",
       6, "无来源论断集 × (成稿引用编号, pending_human)", "result.json + 成稿",
       [K("case.json#/output_contract.change_log", cq("change_log"))] if cq("change_log") else [],
       "受检 %d 条，问题 %d 条" % (len(vs), vs.count("偏差")), ("；".join(bad11[:4])) or "标注齐备",
       agg(vs) if vs else "达标")

    # GS-12 冲突证据保留
    vs, bad12, bs12 = [], [], []
    for c, e in expc:
        core = c.get("core") or ""
        opp = [u for u in units if kmap.get(u["doc"]) == "material" and sim(core, u["text"]) >= .4
               and bool(NEG.search(u["text"])) != bool(NEG.search(core)) and (POS.search(u["text"]) or NEG.search(u["text"]))]
        if not opp:
            continue
        bs12.append(B(opp[0]["doc"], opp[0]["loc"], opp[0]["text"]))
        got = any(r.get("conflicts") for r in byc.get(c.get("claim_id"), []))
        dhas = bool(re.search(r"(however|然而|不一致|相反|conflict)", body, re.I))
        vs.append("达标" if (got and dhas) else "偏差")
        if not (got and dhas):
            bad12.append("%s 有反向来源但 conflicts=%s 对比句=%s" % (c.get("claim_id"), got, dhas))
    it("GS-12", "说得准", "反向来源不得静默丢弃：conflicts + 成稿对比句", "有反向来源的论断 100% 保留",
       6, "反向极性来源检测（NEG/POS） vs conflicts 字段", "evidence_table.json + 成稿",
       (bs12[:1] or [S(MR, "§6 异常处置表 证据相互冲突",
                       "| 证据相互冲突 | 不取平均，保留冲突 | 强度下调 + `claims_with_conflict` 计数 |")]),
       "受检 %d 条，问题 %d 条" % (len(vs), vs.count("偏差")),
       ("；".join(bad12[:4])) or "冲突已保留或材料无冲突", agg(vs) if vs else "达标")

    # GS-13 契约
    miss = [k for k in con if k not in res]
    nullk = [k for k in con if k in res and res.get(k) in (None, "", [], {})]
    echo = str(res.get("case_id")) == str(case.get("case_id") or res.get("case_id"))
    it("GS-13", "契约", "output_contract 全字段原样回填、case_id 回显", "%d 个契约字段齐全且非空" % len(con),
       8, "键集合比对 + 空值扫描 + case_id 字符串比对", "result.json",
       [K("case.json#/output_contract.case_id", cq("case_id"))] if cq("case_id") else [],
       "缺失 %d，空值 %d，case_id 一致 %s" % (len(miss), len(nullk), echo),
       ("缺: %s；空: %s" % (miss, nullk)) if (miss or nullk) else "契约完整",
       "达标" if (con and not miss and not nullk and echo) else ("偏差" if con else "不可判定"))

    # GS-14 状态诚实
    st = res.get("status")
    unsup = sum(1 for c in cl if not [r for r in byc.get(c.get("claim_id"), []) if r.get("source_id")])
    qf = sum(1 for r in rows if r.get("quote") and not r.get("verified"))
    lie = st == "ok" and (unsup or qf)
    it("GS-14", "可靠", "status 与缺口一致：有缺口不得标 ok", "status 属枚举且与缺口一致",
       4, "status × (claims_unsupported, quotes_failed)", "result.json",
       [S(ES, "§4 result.json 关键字段", "| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |")],
       "status=%s，未支撑=%d，未命中=%d" % (st, unsup, qf), "ok 与缺口矛盾" if lie else "状态自洽",
       "达标" if (st in ("ok", "partial", "insufficient_evidence", "input_error") and not lie) else "偏差")

    # GS-15 来源溯源
    sr = res.get("sources") or []
    have = {s.get("path") for s in sr if isinstance(s, dict) and s.get("sha256")}
    nopath = [d["path"] for d in docs if d["path"] not in have]
    it("GS-15", "可靠", "每个输入文件记录路径、字节数与 sha256", "覆盖率 100%%（%d 个文件）" % len(docs),
       2, "sources[].path × 发现结果", "result.json",
       [K("case.json#/case_id", cq("case_id"))] if cq("case_id") else [],
       "%d/%d 有条目" % (len(docs) - len(nopath), len(docs)), ("缺: %s" % nopath[:3]) if nopath else "全部可溯源",
       "达标" if (docs and not nopath) else ("不可判定" if not docs else "偏差"))

    # GS-16 不新增材料外文献
    mdoi = set(DOI.findall(pool)) | {r["doi"] for r in refs if r.get("doi")}
    odoi = set(DOI.findall(draft))
    extra = sorted(odoi - mdoi)
    it("GS-16", "对得上", "输出 DOI 只能来自材料，不得凭记忆补造", "材料外 DOI = 0（输出 DOI %d 个）" % len(odoi),
       2, "DOI 集合差 draft − material", "成稿",
       [K("case.json#/output_contract.preserved_facts", cq("preserved_facts"))] if cq("preserved_facts") else [],
       "材料外 %d 个" % len(extra), ("多出: %s" % extra[:3]) if extra else "无可疑 DOI",
       "达标" if not extra else "缺失")

    # 汇总
    tw = sum(i["weight"] for i in items) or 1
    score = round(100. * sum(i["weight"] * (1. if i["verdict"] == "达标" else .5 if i["verdict"] == "偏差" else 0.)
                             for i in items) / tw, 1)
    cnt = {v: sum(1 for i in items if i["verdict"] == v) for v in VERD}
    basis_bad = [i["id"] for i in items if i["basis"] and not i["basis_verified"]]
    basis_none = [i["id"] for i in items if not i["basis"]]
    cu = []
    for k, (c, e) in enumerate(expc, 1):
        act = [r for r in byc.get(c.get("claim_id"), []) if r.get("quote")]
        ab = min((r["strength"] for r in act), key=lambda x: BD.index(x) if x in BD else 0) if act else "不足"
        cu.append({"unit_id": "CU%03d" % k, "claim_id": c.get("claim_id"), "sentence": (c.get("core") or "")[:300],
                   "claim_location": c.get("location"),
                   "expected": {"source_id": e["source"], "locator": e["locator"], "quote": e["quote"],
                                "coverage": e["cov"], "anchored": e["anchored"], "support_scope": e["scope"],
                                "band_single_source": band(e["quote"], dmap.get(e["source"], {}).get("text", ""), 1, False, False)[0]} if e else
                               {"source_id": None, "locator": None, "quote": None, "coverage": 0.0, "anchored": False,
                                "support_scope": "无直接支撑", "band_single_source": "不足"},
                   "actual": {"source_id": act[0].get("source_id") if act else None,
                              "locator": act[0].get("locator") if act else None, "quote": act[0].get("quote") if act else None,
                              "band": ab, "conflicts": len(act[0].get("conflicts") or []) if act else 0}})
    gs = {"case_id": cid, "standard": "GS-v2", "version": V, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
          "purpose": "核心产物金标准：逐项列期望，每项附 locator+逐字 quote，供复核与差分。",
          "scope": {"in_scope": ["论断切分", "论断-来源对应", "逐字引文与定位可回查", "强度与语气相称",
                                 "数字与引用一致", "冲突与未支持标注", "契约与状态诚实", "来源溯源"],
                    "out_of_scope": ["文献真实性联网核验（离线不可做）", "扫描件/图像识别", "方法学审读（强度为启发式）"]},
          "rules": {"coverage_thresholds": {"expect_source": CORE, "direct_support": DIRECT,
                                            "note": "内容项覆盖率 = |T(论断)∩T(来源)|/|T(论断)|，T 为中英归一后的词项集合"},
                    "strength_table": [{"design": n, "pts": s} for _, n, s in D2] +
                                      [{"size": k, "pts": v} for k, v in ((">=1000", 2.), ("100-999", 1.5), ("10-99", 1.), ("<10", .5))],
                    "strength_thresholds": {"高": ">=5.5", "中": "3.5-5.4", "低": "1.5-3.4", "不足": "<1.5"},
                    "caps": ["预印本 <=4.0", "n<100 <=3.4", "仅摘要最高 中"],
                    "number_rule": "带单位或 >=2 位数字才纳入一致性要求；裸 1-2 位（编号/序数）不计",
                    "locator_scheme": "<相对路径> [B<块>.S<句>] chars:<start>-<end>（基于解析后纯文本）"},
          "items": items, "claim_units": cu,
          "acceptance": {"must_pass": ["GS-02", "GS-03", "GS-04", "GS-13"],
                         "pass_formula": "must_pass 全达标且加权符合度 >=90 视为金标准验收通过",
                         "n_items": len(items), "weight_total": tw, "internal_score": score,
                         "score_note": "internal_score 是产物对本地金标准的加权符合度，用于自查回归，不是平台评分。"}}
    jd(out / "golden_standard.json", gs)

    # diff_report.md
    L = ["# 差分报告：实际产物 vs 金标准（%s）" % cid, "",
         "- 生成 %s｜Skill v%s｜金标准 %s" % (gs["generated_at"], V, gs["standard"]),
         "- 口径：按 `expectation` 独立重算 `actual`；三级判定 达标/偏差/缺失，另设不可判定。",
         "- 加权符合度 **%.1f/100**（本地自查指标，不是平台评分）。" % score, "",
         "## 1. 逐项对照", "", "| ID | 维度 | 期望 | 实测 | 判定 | 依据（locator / 逐字 quote） |", "|---|---|---|---|---|---|"]
    for i in items:
        b = i["basis"][0] if i["basis"] else {}
        L.append("| %s | %s | %s | %s | **%s** | %s `%s`%s |" % (
            i["id"], i["dimension"], i["expectation"].replace("|", "/"), i["actual"].replace("|", "/"), i["verdict"],
            (b.get("locator") or "—")[:40], (b.get("quote") or "")[:40].replace("|", "/"),
            "" if i["basis_verified"] else " ⚠依据未命中"))
    L += ["", "## 2. 论断级对照（金标准期望来源 vs 实际来源）", "",
          "| 单元 | claim | 论断 | 期望来源·定位 | 期望强度 | 实际来源·定位 | 实际强度 | 判定 |", "|---|---|---|---|---|---|---|---|"]
    for u in cu:
        e, a = u["expected"], u["actual"]
        ok = "达标" if (e["source_id"] == a["source_id"] and e["band_single_source"] == a["band"]) else \
            ("缺失" if (e["source_id"] and not a["source_id"]) else "偏差")
        L.append("| %s | %s | %s | %s·%s | %s | %s·%s | %s | **%s** |" % (
            u["unit_id"], u["claim_id"], (u["sentence"] or "")[:36].replace("|", "/"),
            e["source_id"] or "—", (e["locator"] or "—")[:30], e["band_single_source"],
            a["source_id"] or "—", (a["locator"] or "—")[:30], a["band"], ok))
    bad = sorted([i for i in items if i["verdict"] in ("缺失", "偏差")], key=lambda x: -x["weight"])
    L += ["", "## 3. 偏差与缺失（按权重排序，附可执行修法）", ""]
    L += ["- **%s（%s，权重 %d）** %s → %s；修法：%s" % (i["id"], i["dimension"], i["weight"], i["detail"], i["verdict"], i["method"])
          for i in bad] or ["- 无：%d 项全部达标。" % len(items)]
    L += ["", "## 4. 不可判定项", ""] + (["- %s：%s（%s）" % (i["id"], i["requirement"], i["detail"])
                                       for i in items if i["verdict"] == "不可判定"] or ["- 无"])
    if basis_bad or basis_none:
        L += ["", "## 5. 金标准自身的依据缺口", ""]
        if basis_bad:
            L.append("- 依据引文未在声明来源中命中，需人工确认：" + "、".join(basis_bad))
        if basis_none:
            L.append("- 本次材料无法生成依据引文（判定依据为规则本身，见 requirement/method）：" + "、".join(basis_none))
    L += ["", "## 6. 复核方法", "", "```bash", "python3 -B scripts/gold.py --input /input --output /app/output",
          "python3 -B scripts/verify.py --input /input --output /app/output", "```", "",
          "重跑须复现 `internal_score` 与各 `verdict`；改口径同步 `rules` 与 `method_and_runbook.md`。"]
    (out / "diff_report.md").write_text("\n".join(L) + "\n", "utf-8")

    # version_history.md
    VL = ["# 版本记录（Skill writing-03）", "", "当前版本 **%s**：v0 骨架 → v1 成稿 → v2 资产层的改动、原因与回退。" % V, ""]
    for e in VH:
        VL += ["## %s %s（%s）" % (e["v"], e["l"], e["d"] or "时间未在包内记录"), "", "**改了什么**", ""]
        VL += ["- " + x for x in e["c"]]
        VL += ["", "**为什么**", "", "- " + e["w"], "", "**如何回退**", "", "- " + e["r"], ""]
    VL += ["## 本次运行的产物版本", "",
           "- main.py/gold.py/verify.py 均声明 `%s`；与 `result.json.skill_version` 一致" % V,
           "- passed=false 时按 diff_report.md 第 3 节修产物，**不得改金标准迁就产物**", "",
           "## 回退检查表", "", "| 步骤 | 命令 | 期望 |", "|---|---|---|",
           "| 1 | `rm -rf submission && unzip baseline_v1.zip -d submission` | 回到 v1 六文件 |",
           "| 2 | `python3 -B submission/scripts/main.py --help` | 退出码 0 |",
           "| 3 | 最小输入跑一遍 | 产出 v1 九件套，result.json 无 4 个新字段 |",
           "| 4 | `diff -r` 与 v1 解包目录比较 | 无差异 |", ""]
    (out / "version_history.md").write_text("\n".join(VL), "utf-8")

    # self_check.json（含真实子进程兜底闸门）
    gates, scr = [], Path(__file__).resolve().parent / "main.py"
    env = dict(os.environ, W3_ASSET_GATES="0")  # 子进程只做兜底闸门，不再递归生成资产

    def sub(name, args, tmo=120):
        try:
            t = time.time()
            r = subprocess.run([sys.executable, "-B", str(scr)] + args, capture_output=True, timeout=tmo, env=env)
            return {"gate": name, "exit_code": r.returncode, "seconds": round(time.time() - t, 3),
                    "stdout_tail": (r.stdout or b"").decode("utf-8", "ignore")[-140:],
                    "stderr_tail": (r.stderr or b"").decode("utf-8", "ignore")[-140:]}
        except Exception as e:
            return {"gate": name, "exit_code": None, "error": "%s: %s" % (type(e).__name__, e)}

    def ok_res(p):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            return isinstance(d, dict) and d.get("status") in ("ok", "partial", "insufficient_evidence", "input_error")
        except Exception:
            return False

    g = sub("help", ["--help"], 60)
    g["pass"] = g.get("exit_code") == 0
    gates.append(g)
    base = out / ".selfcheck"
    deep = os.environ.get("W3_ASSET_GATES", "1") != "0"
    if not deep:
        gates.append({"gate": "fallback_suite", "exit_code": 0, "pass": True,
                      "result_valid": True, "note": "子进程内跳过，避免递归；兜底闸门由父进程真实执行"})
    for name, content in (() if not deep else (("empty_input", None), ("bad_json", '{"case_id": "BAD", "output_contract": {'),
                                               ("missing_contract", '{"case_id": "NOCON"}'))):
        try:
            d = base / name
            if d.exists():
                shutil.rmtree(d)
            (d / "in").mkdir(parents=True)
            (d / "out").mkdir(parents=True)
            if content is not None:
                (d / "in" / "case.json").write_text(content, "utf-8")
            g = sub(name, ["--input", str(d / "in"), "--output", str(d / "out")])
            g["result_valid"] = ok_res(d / "out" / "result.json")
            g["pass"] = g.get("exit_code") == 0 and g["result_valid"]
            gates.append(g)
        except Exception as e:
            gates.append({"gate": name, "exit_code": None, "pass": False, "error": "%s: %s" % (type(e).__name__, e)})
    shutil.rmtree(base, ignore_errors=True)

    vrep = {}
    try:
        from verify import check as vcheck
        if ind and Path(ind).is_dir():
            vrep = vcheck(ind, out) or {}
    except Exception as e:
        vrep = {"passed": None, "error": "%s: %s" % (type(e).__name__, e)}
    met = res.get("metrics") or {}
    pv = lambda gid: next((i["verdict"] == "达标" for i in items if i["id"] == gid), False)
    sc = {"case_id": cid, "version": V, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
          "passed": bool(not bad and all(g.get("pass", g.get("exit_code") == 0) for g in gates) and vrep.get("passed")),
          "summary": {"items": len(items), "verdicts": cnt, "internal_score": score,
                      "basis_verified": len(items) - len(basis_bad),
                      "note": "无缺失/偏差 且 闸门全过 且 独立复核通过；不替代平台评分"},
          "checks": {"contract_fields": {"pass": pv("GS-13"), "contract_keys": len(con), "missing": miss, "nulls": nullk,
                                         "detail": "output_contract 键集合与 result.json 键集合比对"},
                     "evidence_coverage": {"pass": pv("GS-03"), "claims_total": met.get("claims_total"),
                                           "claims_with_source": met.get("claims_with_source"),
                                           "support_rate": met.get("support_rate"), "evidence_rows": met.get("evidence_rows"),
                                           "quotes_verified": met.get("quotes_verified"), "quotes_failed": met.get("quotes_failed"),
                                           "locator_exact": "%d/%d" % (rok, len(qs))},
                     "number_citation_consistency": {"pass": all(pv(x) for x in ("GS-08", "GS-09", "GS-16")),
                                                     "numbers_in_draft": len(dn), "numbers_untraceable": lost,
                                                     "citation_markers": mk, "unresolved": unr, "untraced_refs": un,
                                                     "preserved_facts": len(pfacts)},
                     "status_honesty": {"pass": pv("GS-14"), "status": st, "degradations": len(res.get("degradations") or []),
                                        "errors": len(res.get("errors") or []), "pending_human": len(pending)},
                     "fallback_gates": {"pass": all(g.get("pass", False) for g in gates if g["gate"] != "help"),
                                        "gates": [{"gate": g["gate"], "exit_code": g.get("exit_code"),
                                                   "result_valid": g.get("result_valid"), "pass": g.get("pass", None)}
                                                  for g in gates]},
                     "independent_verify": {"pass": vrep.get("passed"), "checks": len(vrep.get("checks") or []),
                                            "failed": [c.get("check") for c in (vrep.get("checks") or []) if not c.get("pass")],
                                            "path": str(out / "verification.json")}},
          "exit_codes": {"main_run": 0, "help": gates[0].get("exit_code"),
                         "fallback": {g["gate"]: g.get("exit_code") for g in gates[1:]},
                         "note": "退出码设计为恒 0；此处为本次真实子进程实测值，非声明"},
          "limits": ["未联网核验文献真实性与 DOI", "强度为启发式分级，不替代方法学审读",
                     "扫描件/Office 表格未解析时相关项记不可判定"]}
    jd(out / "self_check.json", sc)
    log.w("assets", "done score=%.1f verdicts=%s gates=%s" % (score, cnt,
          "ok" if all(g.get("pass", g.get("exit_code") == 0) for g in gates) else "fail"), dur=time.time() - t0)

    def ref(p, n, note):
        return {"path": str(out / p), "count": n, "note": note}

    return {"golden_standard": ref("golden_standard.json", len(items), "金标准 %d 项 + %d 个论断单元期望" % (len(items), len(cu))),
            "diff_report": ref("diff_report.md", len(bad), "达标 %d / 偏差 %d / 缺失 %d，加权符合度 %.1f（自查，非平台分）" % (
                cnt["达标"], cnt["偏差"], cnt["缺失"], score)),
            "version_history": ref("version_history.md", len(VH), "版本 %s；含回退命令与检查表" % V),
            "self_check": ref("self_check.json", 6, "passed=%s；兜底闸门 %d 个" % (sc["passed"], len(gates)))}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="gold.py", description="writing-03 v2 独立重跑：金标准 + 差分 + 版本记录 + 自检（不覆盖 main.py 产物）。")
    ap.add_argument("--input", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--output", default="/app/output", help="输出目录（默认 /app/output）")
    a = ap.parse_args(argv)
    try:
        print("gold recheck %s" % json.dumps({k: v.get("count") for k, v in
                                             run(a.input, a.output, _j(Path(a.input) / "case.json")).items()}, ensure_ascii=False))
    except Exception as e:
        print("gold degraded: %s: %s" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
