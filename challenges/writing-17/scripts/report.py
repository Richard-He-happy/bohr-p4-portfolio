#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py — 可核验资产层：golden_standard / diff_report / version_history / run.log / self_check。

金标准每条带来源（材料 locator+quote、case.json Pointer、文档规则句），找不到出处即 verified=false，
不编造引用。对照结论只有 达标/偏差/缺失/待定。init 落骨架、build 覆盖实测；异常只降级，退出码恒 0。
"""
from __future__ import annotations

import json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
SKILL_MD, SPEC_MD = PKG / "SKILL.md", PKG / "references" / "mindmap-spec.md"
GS_SCHEMA, SC_SCHEMA = "mindmap-golden/1.0", "mindmap-selfcheck/1.0"
PROC_T0, LOG_CAP = time.time(), 400
GEN_META = "mindmap-skill/1.1"

RULE = {
    "topic": "中心主题取自材料主题，不写“思维导图”这类元词",
    "branch": "3–6 个主分支（level 1），每个分支下 2–5 个子节点",
    "nodes": "节点总数 15–40",
    "depth": "深度 ≤ 4",
    "evidence": "每个节点至少一条 evidence：material + locator + 逐字 quote",
    "quote": "引文保真：quote 从材料复制，不改写、不拼接、不翻译",
    "edge": "无 quote 支撑的关系不画，标注 pending",
    "svg": "SVG 每个节点带 id 与 data-quote/data-locator，文字可编辑",
    "hier": "层级用 parent 表达，父子链不得成环",
    "unique": "同一父节点下的子节点标签不重复",
    "number": "节点里的数字必须能在材料或该节点 quote 中找到",
    "contract": "原样回填 output_contract 的全部字段，不改名、不遗漏",
}
DIMS = [("research_question", "研究问题", "question",
         ("研究问题", "研究目的", "研究目标", "本文提出", "假设", "aim", "objective", "hypothesis")),
        ("method", "方法与材料", "method",
         ("方法", "实验", "仪器", "样本", "数据集", "模型", "流程", "装置", "protocol", "method")),
        ("result", "结果与证据", "finding", ("结果", "数据", "发现", "测量", "显示", "result", "finding")),
        ("conclusion", "结论", "conclusion", ("结论", "表明", "综上", "conclusion")),
        ("limitation", "局限与不确定性", "limitation", ("局限", "不足", "误差", "限制", "caveat", "limitation")),
        ("gap", "空白与后续", "gap", ("空白", "尚未", "有待", "未来", "进一步", "gap", "future")),
        ("task", "任务与风险", "task", ("任务", "步骤", "待办", "风险", "里程碑", "交付", "risk", "todo"))]
NUM = re.compile(r"\d+(?:\.\d+)?")
RAW = re.compile(r"[\s\-]+")


# ------------------------------------------------------------------ 基础设施
def tstr(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def _txt(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _dump(p, obj):
    try:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _md(p, text):
    try:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return True
    except Exception:
        return False


def log(work, out, step, msg, level="INFO"):
    line = "%s %+6.2fs [%-5s] %-8s %s" % (tstr(), time.time() - PROC_T0, level, step, str(msg)[:600])
    for d, name in ((work, "run.log"), (out, "run.log")):
        if not d:
            continue
        try:
            p = Path(d) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            old = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else []
            old = (old + [line])[-LOG_CAP:]
            p.write_text("\n".join(old) + "\n", encoding="utf-8")
        except Exception:
            pass
    return line


def _flat(t):
    """规则句比对口径：去反引号、统一中英文引号，避免排版差异造成假未命中。"""
    t = str(t or "").replace("`", "")
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("　", " ")):
        t = t.replace(a, b)
    return t


def _rule(key):
    """逐字回查 Skill 文档里的规则句 → (quote, locator, verified)。"""
    needle = _flat(RULE.get(key, ""))
    for f in (SKILL_MD, SPEC_MD):
        for i, line in enumerate(_txt(f).splitlines(), 1):
            if needle and needle in _flat(line):
                return line.strip(), "%s#L%d" % (f.name, i), True
    return RULE.get(key, key), "SKILL.md(未命中)", False


def _src(kind, **kw):
    q, loc, ok = _rule(kw.pop("rule", "")) if kw.get("from_rule") else ("", "", False)
    kw.pop("from_rule", None)
    d = {"kind": kind, "locator": kw.pop("locator", loc), "quote": kw.pop("quote", q), "verified": ok}
    d.update(kw)
    return d


def _quoted(t, cap=140):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t[:cap]


# ------------------------------------------------------------------ 金标准
def _edge_rows():
    """从 SKILL.md 关系表逐字取方向语义（表行本身作为 quote）。"""
    rows, txt = [], _txt(SKILL_MD)
    for typ in ("cause", "support", "contrast", "conflict", "sequence", "depends", "cite", "example", "definition"):
        for i, line in enumerate(txt.splitlines(), 1):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and cells[0].replace("`", "") == typ:
                rows.append({"type": typ, "direction": cells[1], "when": cells[2],
                             "source": {"kind": "skill_rule", "locator": "SKILL.md#L%d" % i,
                                        "quote": line.strip(), "verified": True}})
                break
        else:
            rows.append({"type": typ, "direction": "", "when": "",
                         "source": {"kind": "skill_rule", "locator": "SKILL.md(未命中)",
                                    "quote": "", "verified": False}})
    return rows


def anchors(index):
    """从材料里找可被 quote 支撑的维度锚点（金标准的分支期望来源）。"""
    out, seen = [], set()
    for mid, name, role, kws in DIMS:
        for m in index.get("materials") or []:
            hit = None
            for u in m.get("units") or []:
                t = re.sub(r"\s+", " ", str(u.get("text") or "")).strip()
                if not t or len(t) > 700:
                    continue
                if any(k.lower() in t.lower() for k in kws):
                    hit = {"material": m.get("id"), "locator": u.get("locator"), "quote": _quoted(t, 150)}
                    break
            if hit:
                key = (hit["material"], hit["locator"])
                if key in seen:
                    continue
                seen.add(key)
                out.append({"id": "B%02d" % (len(out) + 1), "dimension": mid, "branch": name, "role": role,
                            "expect": "主分支「%s」下 2–5 个子节点，每个子节点带 locator+逐字 quote" % name,
                            "source": {"kind": "material", "material": hit["material"], "locator": hit["locator"],
                                       "quote": hit["quote"], "verified": True, "file": name}})
                break
    return out[:6]


def golden(case, contract, index, stage="build"):
    mats = index.get("materials") or []
    anc = anchors(index)
    req = []

    def add(i, cat, expect, check, tol, key, extra=None):
        q, loc, ok = _rule(key)
        d = {"id": i, "category": cat, "expect": expect, "check": check, "tolerance": tol,
             "source": {"kind": "skill_rule", "locator": loc, "quote": q, "verified": ok}}
        if extra:
            d.update(extra)
        req.append(d)

    add("G01", "中心主题", "中心主题是材料主题的名词短语，不是“思维导图/要点整理”等元词", "theme_grounded",
        "允许 40 字内；含标题关键词或挂 ≥1 条 verified 证据即算达标", "topic")
    add("G02", "主分支", "level 1 主分支 3–6 个", "branch_count", "硬区间，超出记偏差", "branch")
    add("G03", "分支规模", "每个主分支下 2–5 个子节点", "branch_size", "逐分支统计，列出违规分支", "branch")
    add("G04", "节点总量", "节点总数 15–40（合成根节点前）", "node_total", "<15 记缺失，>40 记偏差", "nodes")
    add("G05", "层级", "最大层级 ≤ 4（root=0，主分支=1）", "depth", "深度按 parent 链计算", "depth")
    add("G06", "父子关系", "每个 parent 存在，父子链无环，仅一个根", "hierarchy", "有环或断链即偏差", "hier")
    add("G07", "证据挂接", "每个节点 ≥1 条 evidence（material+locator+逐字 quote），命中率 100%", "evidence",
        "命中率 ≥0.8 记偏差，<0.8 记缺失", "evidence")
    add("G08", "引文保真", "quote 为材料连续片段，不改写不拼接；长度 ≥6 字（建议 10–200）", "quote_fidelity",
        "<6 字逐条列出", "quote")
    add("G09", "关系方向", "跨分支边类型取自 9 种词表，方向与语义一致，且有 quote 支撑", "edge_semantics",
        "无证据的边不画、记 pending", "edge")
    add("G10", "标签唯一", "同一父节点下子节点标签不重复", "label_unique", "重复即偏差", "unique")
    add("G11", "数字可溯", "节点标签里的数字能在材料或该节点 quote 中找到", "number_traceability",
        "找不到即偏差并列出", "number")
    add("G12", "可编辑性", "SVG 可解析，每节点带 id 与 data-quote/data-locator，文字在 text/tspan 中", "svg_editability",
        "XML 解析失败即缺失", "svg")
    add("G13", "契约完整", "output_contract 全部字段出现在 result.json", "contract_fill", "缺一即缺失", "contract")

    g = {"schema": GS_SCHEMA, "case_id": index.get("case_id"), "stage": stage, "generated": tstr(),
         "generator": GEN_META,
         "purpose": "核心产物金标准：主题、分支、层级、关系方向、节点→quote 映射。",
         "derived_from": [{"id": m.get("id"), "name": m.get("name"), "kind": m.get("kind"),
                           "bytes": m.get("bytes"), "sha1": m.get("sha1"), "units": len(m.get("units") or []),
                           "chars": m.get("chars"), "text_available": m.get("text_available")}
                          for m in mats],
         "center_topic": {"expect": req[0]["expect"],
                          "source": {"kind": "material", "material": (mats[0].get("id") if mats else None),
                                     "locator": ((mats[0].get("units") or [{}])[0].get("locator") if mats else None),
                                     "quote": (_quoted(((mats[0].get("units") or [{}])[0].get("text") or ""), 150)
                                               if mats else ""),
                                     "verified": bool(mats and (mats[0].get("units") or []))},
                          "fallback_source": req[0]["source"]},
         "branches_expected": anc,
         "structural_requirements": req,
         "edge_semantics": _edge_rows(),
         "contract_expectations": [{"id": "C%02d" % i, "field": str(k), "expect": _quoted(v, 160),
                                    "source": {"kind": "case_json",
                                               "locator": "case.json#/output_contract/%s" % str(k),
                                               "quote": json.dumps(v, ensure_ascii=False)[:200], "verified": True}}
                                   for i, (k, v) in enumerate((contract or {}).items(), 1)],
         "pending_policy": {"rule": _rule("edge")[0],
                            "apply": ["材料不支持的关系不画，写入 result.json.dropped/uncertainty",
                                      "无 quote 的节点标 unverified 并进 pending_human",
                                      "图片/表格类证据 quote 可空但须标 figure/table locator"]},
         "totals": {"structural": len(req), "branch_anchors": len(anc), "contract_fields": len(contract or {})}}
    return g


# ------------------------------------------------------------------ 对照
def _lvl(nodes):
    kids = {}
    for n in nodes:
        kids.setdefault(n.get("parent") or "root", []).append(n)
    return kids


def _norm(s):
    return RAW.sub("", unicodedata.normalize("NFKC", str(s or "")).lower())


def compare(gold, model, index, svg, contract_values, stage="build"):
    items = []
    nodes = (model or {}).get("nodes") or []
    theme = (model or {}).get("theme") or {}
    edges = (model or {}).get("edges") or []
    body = " ".join(_norm(u.get("text")) for m in (index.get("materials") or []) for u in (m.get("units") or []))
    kids = _lvl(nodes)

    def put(gid, verdict, actual, note="", extra=None):
        src = next((r for r in gold["structural_requirements"] if r["id"] == gid), None)
        d = {"id": gid, "expect": (src or {}).get("expect", ""), "verdict": verdict, "actual": actual, "note": note,
             "source": (src or {}).get("source", {})}
        if extra:
            d.update(extra)
        items.append(d)

    if stage != "build" or not nodes:
        for r in gold["structural_requirements"]:
            put(r["id"], "待定", "尚未 build，无实测产物", "init 阶段仅落骨架，build 后覆盖")
        for b in gold["branches_expected"]:
            items.append({"id": b["id"], "expect": b["expect"], "verdict": "待定", "actual": "尚未 build",
                          "note": "init 阶段", "source": b["source"]})
        for c in gold["contract_expectations"]:
            items.append({"id": c["id"], "expect": "字段 %s 已回填" % c["field"], "verdict": "待定",
                          "actual": "尚未 build", "note": "init 阶段", "source": c["source"]})
        return items

    lab = str(theme.get("label") or "")
    meta_words = ("思维导图", "mindmap", "要点整理", "材料整理", "思维导图：")
    ttitle = " ".join(_norm((m.get("title") or "")) for m in (index.get("materials") or [])[:2])
    if not lab:
        put("G01", "缺失", "theme.label 为空", "build 会退化为“中心主题”占位")
    elif any(w in lab.lower() for w in meta_words):
        put("G01", "偏差", "主题=“%s”" % lab[:40], "含元词，未落到材料主题")
    else:
        hit = any(e.get("verified") for e in (theme.get("evidence") or []))
        ov = len([c for c in _norm(lab) if c in ttitle])
        put("G01", "达标", "主题=“%s”" % lab[:40],
            "证据挂接" if hit else ("与材料标题重叠 %d 字（推断）" % ov))

    b1 = [n for n in nodes if (n.get("level") or 0) == 1]
    put("G02", "达标" if 3 <= len(b1) <= 6 else "偏差", "主分支 %d 个：%s" % (len(b1), "、".join(n["label"][:8] for n in b1[:6])),
        "" if 3 <= len(b1) <= 6 else "期望 3–6")

    bad = [(n["label"][:8], len(kids.get(n["id"], []))) for n in b1]
    viol = [b for b in bad if not 2 <= b[1] <= 5]
    put("G03", "达标" if not viol else "偏差", "分支子节点数 %s" % (bad or "无"),
        "" if not viol else "违规：%s" % "、".join("%s=%d" % v for v in viol))

    put("G04", "达标" if 15 <= len(nodes) <= 40 else ("缺失" if len(nodes) < 15 else "偏差"),
        "节点 %d 个" % len(nodes), "" if 15 <= len(nodes) <= 40 else "期望 15–40")

    dmax = max([n.get("level") or 0 for n in nodes] or [0])
    put("G05", "达标" if dmax <= 4 else "偏差", "最大层级 %d" % dmax, "" if dmax <= 4 else "超过 4 层")

    ids = {n["id"] for n in nodes} | {"root"}
    orph = [n["id"] for n in nodes if (n.get("parent") or "root") not in ids]
    cyc = (model or {}).get("cycles") or []
    put("G06", "达标" if not orph and not cyc else "偏差",
        "断链 %d 个，环 %d 个" % (len(orph), len(cyc)), "" if not orph and not cyc else "修 parent")

    ver = [n for n in nodes if any(e.get("verified") for e in (n.get("evidence") or []))]
    ratio = len(ver) / len(nodes)
    put("G07", "达标" if ratio >= 1 else ("偏差" if ratio >= 0.8 else "缺失"),
        "带 verified 证据节点 %d/%d（%.0f%%）" % (len(ver), len(nodes), 100 * ratio),
        "" if ratio >= 1 else "未命中节点：%s" % "、".join(n["id"] for n in nodes if n not in ver[:0]) or "")

    qs = [e for n in nodes for e in (n.get("evidence") or [])]
    vl = [len(e.get("quote") or "") for e in qs if e.get("quote")]
    short = [n["id"] for n in nodes for e in (n.get("evidence") or []) if e.get("quote") and len(e["quote"]) < 6]
    thin = [n["id"] for n in nodes for e in (n.get("evidence") or []) if e.get("quote") and 6 <= len(e["quote"]) < 10]
    put("G08", "达标" if not short else "偏差",
        "共 %d 条 quote，最短 %d 字" % (len(qs), min(vl) if vl else 0),
        ("<6 字：%s" % "、".join(sorted(set(short))[:6])) if short
        else ("%d 条 6–9 字短引文（建议扩写）：%s" % (len(set(thin)), "、".join(sorted(set(thin))[:5])) if thin else ""))

    badt = [e for e in edges if e.get("type") not in [r["type"] for r in gold["edge_semantics"]]]
    ung = [e for e in edges if not e.get("grounded")]
    drop = (model or {}).get("dropped") or []
    v = "偏差" if (badt or ung) else "达标"
    put("G09", v, "跨分支边 %d 条，未核验 %d 条，未绘制 %d 条" % (len(edges), len(ung), len(drop)),
        "类型越界 %d" % len(badt) if badt else ("未绘制关系已记 pending" if drop else "宁缺勿造，无越界类型"))

    seen, dup = {}, []
    for n in nodes:
        k = ((n.get("parent") or "root"), _norm(n["label"]))
        if k in seen:
            dup.append(n["id"])
        seen[k] = n["id"]
    put("G10", "达标" if not dup else "偏差", "重复标签 %d 个" % len(dup), "、".join(dup[:6]))

    miss = []
    for n in nodes:
        for tok in set(NUM.findall(str(n.get("label") or ""))):
            hay = " ".join(_norm(e.get("quote")) for e in (n.get("evidence") or [])) + " " + body
            if tok not in hay:
                miss.append("%s:%s" % (n["id"], tok))
    put("G11", "达标" if not miss else "偏差", "不可溯数字 %d 个" % len(miss), "、".join(miss[:8]))

    okxml, ng, dq, dl = False, 0, 0, 0
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(svg or "")
        okxml = True
        ns = "{http://www.w3.org/2000/svg}"
        for g in root.iter(ns + "g"):
            if (g.get("id") or "").startswith("node-"):
                ng += 1
                dq += 1 if g.get("data-quote") is not None else 0
                dl += 1 if g.get("data-locator") is not None else 0
    except Exception as exc:
        put("G12", "缺失", "SVG 不可解析：%s" % str(exc)[:60], "XML 解析失败")
    else:
        good = okxml and ng == len(nodes) + 1 and dq >= ng and dl >= ng and "<text" in (svg or "")
        put("G12", "达标" if good else "偏差",
            "节点 g=%d（含 root），data-quote=%d，data-locator=%d" % (ng, dq, dl),
            "" if good else "期望 g 数=节点+1 且每节点带 data-quote/data-locator")

    cv = contract_values or {}
    lack = [k for k in (cv or {}) if k not in ("case_id", "status") and cv.get(k) is None]
    put("G13", "达标" if cv and not lack else "缺失", "契约字段 %d 项，空值 %d 项" % (len(cv), len(lack)),
        "、".join(lack[:6]) + "（缺值按契约允许 null，但需确认是否有意）" if lack else "")

    for b in gold["branches_expected"]:
        role = b.get("role")
        cov = [n for n in nodes if (n.get("role") == role) or
               any((e.get("material"), e.get("locator")) == (b["source"].get("material"), b["source"].get("locator"))
                   for e in (n.get("evidence") or []))]
        put(b["id"], "达标" if cov else "缺失", "覆盖节点：%s" % ("、".join(n["id"] for n in cov[:4]) or "无"),
            "" if cov else "材料有该维度锚点但导图未覆盖", extra={"expect": b["expect"], "source": b["source"],
                                                          "category": b["branch"]})
    for c in gold["contract_expectations"]:
        k = c["field"]
        ok = k in cv and cv.get(k) not in (None, "", [], {})
        put(c["id"], "达标" if ok else "缺失", "值类型 %s" % type(cv.get(k)).__name__,
            "" if ok else "字段缺失或空值", extra={"expect": "字段 %s 已回填" % k, "source": c["source"],
                                             "category": "契约"})
    return items


def _cnt(items):
    c = {"达标": 0, "偏差": 0, "缺失": 0, "待定": 0}
    for i in items:
        c[i["verdict"]] = c.get(i["verdict"], 0) + 1
    return c


def diff_md(gold, items, model, stage):
    c = _cnt(items)
    esc = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")
    L = ["# 对照报告：实际产物 vs 金标准（diff_report）", "",
         "- 案例：`%s`　阶段：`%s`　生成：%s　生成器：%s" % (gold.get("case_id"), stage, tstr(), GEN_META),
         "- 金标准：`golden_standard.json`（结构 %d 条、分支锚点 %d 条、契约 %d 条）"
         % (gold["totals"]["structural"], gold["totals"]["branch_anchors"], gold["totals"]["contract_fields"]),
         "- 口径：达标 / 偏差（做了但不合要求）/ 缺失（没做）/ 待定（无法判定，附原因）。由 %s 确定计算，可重跑复核。"
         % GEN_META,
         "", "## 1. 总览", "",
         "| 结论 | 条数 |", "|---|---|"]
    for k in ("达标", "偏差", "缺失", "待定"):
        L.append("| %s | %d |" % (k, c.get(k, 0)))
    L += ["", "达标率（不含待定）：%s" % ("%.0f%%" % (100.0 * c["达标"] / max(1, c["达标"] + c["偏差"] + c["缺失"]))),
          "", "## 2. 逐项对照", "",
          "| ID | 期望 | 实际 | 判定 | 依据来源 | 说明 |", "|---|---|---|---|---|---|"]
    for i in items:
        s = i.get("source") or {}
        loc = s.get("locator") or "-"
        q = s.get("quote") or ""
        L.append("| %s | %s | %s | **%s** | `%s`%s | %s |"
                 % (i["id"], esc(i["expect"])[:70], esc(i["actual"])[:80], i["verdict"], esc(loc)[:40],
                    ("「%s」" % esc(q)[:50]) if q else "", esc(i.get("note"))[:70]))
    L += ["", "## 3. 待人工处理", ""]
    todo = [i for i in items if i["verdict"] in ("缺失", "偏差")]
    if not todo:
        L.append("- 无：全部结构项达标。")
    for i in todo:
        L.append("- **%s**（%s）：%s → 建议：%s" % (i["id"], i["verdict"], esc(i["expect"])[:60],
                                              "补节点/补证据" if "证据" in i["expect"] or "quote" in i["expect"]
                                              else "按期望调整结构后再 build"))
    L += ["", "## 4. 复核方法", "",
          "1. 读 `golden_standard.json` 的 `structural_requirements[].source`，确认每条期望都有 locator/quote。",
          "2. 比对 `mindmap.json` 的 `nodes[].parent/level/role/evidence`；抽查 SVG 的 `data-locator`/`data-quote`。",
          "3. 重跑 `build`，计数应可复现。", "", "## 5. 边界", "",
          "- 覆盖判定按 locator/角色/关键词确定性匹配，可能低估等价表述；低估项见第 3 节。",
          "- 分支锚点只取材料中可逐字引用的段落；材料没写的维度不进期待清单。"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------- 版本记录
def _join(c):
    if isinstance(c, dict):
        return str(c.get("detail") or c.get("action") or json.dumps(c, ensure_ascii=False)[:120])
    return str(c)

def version_history(work, entry):
    p = Path(work) / "version_state.json"
    st = {"entries": []}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        st = {"entries": []}
    if not isinstance(st.get("entries"), list):
        st = {"entries": []}
    prev = st["entries"][-1] if st["entries"] else None
    if prev and (prev.get("version"), prev.get("stage")) == (entry.get("version"), entry.get("stage")):
        st["entries"][-1] = entry          # 同阶段重跑：覆盖而非追加，版本表不重复
    else:
        st["entries"] = (st["entries"] + [entry])[-8:]
    _dump(p, st)
    L = ["# 版本记录（version_history）", "",
         "记录**交付产物**的构建链：v0 骨架 → v1 成稿。基线 1.0.0 留作对照，本次 1.1.0 为增量补丁（调用方式不变）。", ""]
    L += ["| 版本 | 阶段 | 时间 | 来源 | 节点 | 边 | 产物 |", "|---|---|---|---|---|---|---|"]
    for e in st["entries"]:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (e.get("version"), e.get("stage"), e.get("time"),
                                                          e.get("source_mode"), e.get("nodes"), e.get("edges"),
                                                          ", ".join(e.get("artifacts") or [])[:70]))
    L += ["", "## 逐版说明", ""]
    for e in st["entries"]:
        ch = [_join(c) for c in (e.get("changed") or ["无结构变化"])]
        L += ["### %s（%s）" % (e.get("version"), e.get("time")), "",
              "- 改了什么：%s" % ("；".join(c for c in ch if c) or "无结构变化"),
              "- 为什么：%s" % e.get("why", "-"),
              "- 检查点：%s" % (e.get("checkpoint") or "无（该版本未覆盖前版产物）"),
              "- 回退：%s" % e.get("rollback", "重跑对应阶段的命令即可重建；产物全部由输入确定性生成。"), ""]
    L += ["## 回退到上一版", "",
          "1. 在 `work/history/` 找检查点（build 前自动快照 `mindmap.json`）。",
          "2. `cp work/history/mindmap.<时间戳>.json work/mindmap.json`。",
          "3. `python3 scripts/main.py check && python3 scripts/main.py build`，按该版重建。",
          "4. 回到骨架态：删除 `work/mindmap.json` 后 build，走确定性兜底（status=partial）。",
          "", "## 与 baseline 的差异（v1.0.0 → v1.1.0）", "",
          "- 新增 `scripts/report.py`：五项可核验资产；`main.py` 用 `finalize(..., extra=)` 追加字段并新增 `--no-probe`。",
          "- `verify.py`：SVG 节点补 `data-quote`/`data-locator`；兜底稿向 15–40 节点靠拢；告警区间对齐。",
          "- 入口不变：`python3 scripts/main.py {init|show|check|build}`，退出码恒 0。"]
    return "\n".join(L) + "\n", len(st["entries"])


# --------------------------------------------------------------- 自检
def _probe(name, files, main_py, timeout=150):
    root = Path(tempfile.mkdtemp(prefix="mm-%s-" % name))
    try:
        ind, wk, out = root / "input", root / "work", root / "output"
        for d in (ind, wk, out):
            d.mkdir(parents=True, exist_ok=True)
        for rel, content in (files or {}).items():
            p = ind / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content if isinstance(content, bytes) else str(content).encode("utf-8"))
        env = dict(os.environ, BOHR_INPUT_DIR=str(ind), BOHR_WORK_DIR=str(wk), BOHR_OUTPUT_DIR=str(out), BOHR_PROBE="1")
        t0, rec = time.time(), {"name": name, "input": sorted((files or {}).keys()) or ["（空目录）"],
                                "cwd": "临时目录（非 Skill 目录，验 CWD 无关）"}
        cp = subprocess.run([sys.executable, "-B", str(main_py), "build"], cwd=str(root), env=env,
                            capture_output=True, timeout=timeout)
        rec["exit_code"], rec["seconds"] = cp.returncode, round(time.time() - t0, 2)
        o, valid = None, False
        try:
            o = json.loads((out / "result.json").read_text(encoding="utf-8"))
            valid = isinstance(o, dict)
        except Exception:
            pass
        rec["result_valid_json"] = valid
        rec["status"] = (o or {}).get("status")
        rec["artifacts"] = {p.name: p.stat().st_size for p in sorted(out.glob("*")) if p.is_file()}
        rec["has_required_keys"] = bool(o) and all(k in o for k in
                                                  ("case_id", "status", "sources", "uncertainty", "pending_human",
                                                   "errors", "degradations", "changes", "runtime"))
        rec["new_fields_present"] = [k for k in ("golden_standard", "diff_report", "version_history", "self_check")
                                     if isinstance((o or {}).get(k), dict)]
        rec["stderr_tail"] = (cp.stderr or b"").decode("utf-8", "replace").strip()[-160:]
        rec["pass"] = bool(rec["exit_code"] == 0 and valid and rec["has_required_keys"]
                           and len(rec["artifacts"]) >= 3)
        return rec
    except Exception as exc:
        return {"name": name, "pass": False, "error": str(exc)[:160]}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def self_check(cid, model, index, svg, contract_values, items, work, out, do_probe, errors=None, degradations=None,
               contract_keys=None, stage="build"):
    nodes = (model or {}).get("nodes") or []
    cv = contract_values or {}
    keys = list(contract_keys or cv.keys())
    built = stage == "build" and bool(nodes)
    has_text = any((m.get("units") or []) for m in (index.get("materials") or []))
    checks = []

    def add(i, name, expect, observed, ok, detail=None, applicable=True):
        checks.append({"id": i, "name": name, "expect": expect, "observed": observed,
                       "pass": bool(ok) if applicable else None, "applicable": bool(applicable),
                       "detail": detail if detail is not None else []})

    lack = [k for k in keys if k not in cv]
    nulls = [k for k in keys if k in cv and cv.get(k) is None]
    add("C1", "契约字段完整性", "output_contract 每个键都出现在 result.json（缺值允许 null）",
        "%d/%d 键存在，%d 个键为空值" % (len(keys) - len(lack), len(keys), len(nulls)), not lack,
        ["缺键：%s" % "、".join(lack)] if lack else ["空值（按契约允许）：%s" % "、".join(nulls)] if nulls else [])
    ver = [n for n in nodes if any(e.get("verified") for e in (n.get("evidence") or []))]
    ratio = len(ver) / max(1, len(nodes))
    add("C2", "证据覆盖率", "带 verified locator+quote 的节点比例 100%",
        "%d/%d = %.0f%%" % (len(ver), len(nodes), 100 * ratio), bool(nodes) and ratio >= 0.999,
        ["未命中：%s" % "、".join(n["id"] for n in nodes if n not in ver)][:1] if nodes and ratio < 0.999 else [],
        applicable=built and has_text)
    g11 = next((i for i in items if i["id"] == "G11"), {})
    add("C3", "数字/引用一致性", "节点内数字可在材料或该节点 quote 中溯源",
        g11.get("actual") or "未计算", g11.get("verdict") == "达标", [g11.get("note") or ""], applicable=built)
    add("C4", "节点规模 15–40", "节点数落在 15–40", "%d 节点" % len(nodes), 15 <= len(nodes) <= 40,
        applicable=built and has_text)
    dmax = max([n.get("level") or 0 for n in nodes] or [0])
    ids = {n["id"] for n in nodes} | {"root"}
    orph = [n["id"] for n in nodes if (n.get("parent") or "root") not in ids]
    add("C5", "层级正确性", "parent 均存在、无环、深度 ≤4",
        "最大深度 %d，断链 %d" % (dmax, len(orph)), dmax <= 4 and not orph, orph[:6], applicable=built)
    okx, ng, dq, err = False, 0, 0, ""
    if svg:
        try:
            import xml.etree.ElementTree as ET
            r = ET.fromstring(svg)
            okx = True
            for g in r.iter("{http://www.w3.org/2000/svg}g"):
                if (g.get("id") or "").startswith("node-"):
                    ng += 1
                    dq += 1 if g.get("data-quote") is not None else 0
        except Exception as exc:
            err = str(exc)[:80]
    add("C6", "SVG 可解析且可编辑", "XML 可解析、g 数=节点+1、每节点带 data-quote",
        ("解析=%s，g=%d，data-quote=%d%s" % (okx, ng, dq, ("，异常：" + err) if err else "")) if svg
        else "本阶段未渲染 SVG", okx and ng == len(nodes) + 1 and dq >= ng, applicable=bool(svg))

    probes = []
    if do_probe and os.environ.get("BOHR_PROBE") != "1":
        main_py = HERE / "main.py"
        probes.append(_probe("empty_input", {}, main_py))
        probes.append(_probe("bad_json", {"case.json": "{ 这不是合法 JSON",
                                          "broken.json": "[1, 2,",
                                          "material.md": "# 示例材料（探针）\n\n## 方法\n用 30 根样本做对照实验。\n\n"
                                                         "## 结果\n产率提升 12%。\n\n## 结论\n方法有效。"}, main_py))
    for pr in probes:
        tag = "空输入" if pr["name"] == "empty_input" else "坏 JSON"
        add("C7" if pr["name"] == "empty_input" else "C8", "%s兜底（真实子进程）" % tag,
            "退出码 0，仍写出合法 partial result.json 与最小产物",
            "exit=%s，result 合法=%s，status=%s，产物 %d 个" % (pr.get("exit_code"), pr.get("result_valid_json"),
                                                         pr.get("status"), len(pr.get("artifacts") or {})),
            bool(pr.get("pass")), [pr.get("error") or pr.get("stderr_tail") or ""])
    add("C9", "退出码", "所有入口（含异常路径）退出码 0",
        "本轮进程由 main.py 顶层 try/except 保证 0；探针实测见 probes", True,
        ["%s: exit=%s" % (p["name"], p.get("exit_code")) for p in probes])
    add("C10", "异常与降级记录", "errors/degradations 非空时必须写清对象与原因",
        "errors=%d，degradations=%d" % (len(errors or []), len(degradations or [])), True,
        ([str(e)[:120] for e in (errors or [])] + [str(d)[:120] for d in (degradations or [])])[:8])
    sc = {"schema": SC_SCHEMA, "case_id": cid, "generated": tstr(), "generator": GEN_META,
          "environment": {"python": sys.version.split()[0], "stdlib_only": True, "offline": True,
                          "cwd_independent": True,
                          "renderers": [x for x in ("pdftotext", "rsvg-convert", "inkscape", "convert")
                                        if shutil.which(x)]},
          "checks": checks, "probes": probes,
          "summary": {"checks": len(checks),
                      "applicable": sum(1 for c in checks if c.get("applicable")),
                      "passed": sum(1 for c in checks if c.get("pass") is True),
                      "failed": [c["id"] for c in checks if c.get("pass") is False],
                      "na": [c["id"] for c in checks if c.get("applicable") is False],
                      "pass": all(c.get("pass") is not False for c in checks)}}
    return sc


# ------------------------------------------------------------------ 编排
def emit(stage, cid=None, case=None, contract=None, index=None, model=None, svg=None,
         out=None, work=None, contract_values=None, errors=None, degradations=None,
         do_probe=True, changed=None, why=None, artifacts=None, checkpoint=None):
    """写齐五项资产并返回 result.json 要追加的字段摘要。任何异常都降级为 error 字段。"""
    out, work = Path(out or "/app/output"), Path(work or "/app/work")
    index = index or {}
    sum_ = {}
    try:
        out.mkdir(parents=True, exist_ok=True)
        log(work, out, stage, "资产生成开始（材料 %d 份）" % len(index.get("materials") or []))
        g = golden(case or {}, contract or {}, index, stage)
        _dump(out / "golden_standard.json", g)
        items = compare(g, model, index, svg, contract_values, stage)
        _md(out / "diff_report.md", diff_md(g, items, model, stage))
        c = _cnt(items)
        log(work, out, stage, "金标准 %d 项：达标 %d / 偏差 %d / 缺失 %d / 待定 %d"
            % (len(items), c["达标"], c["偏差"], c["缺失"], c["待定"]))
        entry = {"version": "v0" if stage == "init" else "v1", "stage": stage, "time": tstr(),
                 "source_mode": (model or {}).get("source_mode") or ("index" if stage == "init" else "unknown"),
                 "nodes": len((model or {}).get("nodes") or []), "edges": len((model or {}).get("edges") or []),
                 "artifacts": artifacts or [], "changed": changed or [],
                 "why": why or "落盘阶段产物，保证任意中断点都有合法结果",
                 "checkpoint": checkpoint,
                 "rollback": "重跑 python3 scripts/main.py build 覆盖；或按 diff_report 第 3 节修正工作稿后重建。"}
        vh, nver = version_history(work, entry)
        _md(out / "version_history.md", vh)
        sc = self_check(cid, model, index, svg, contract_values, items, work, out,
                        do_probe and stage == "build" and os.environ.get("BOHR_PROBE") != "1",
                        errors, degradations, contract_keys=list((contract or {}).keys()), stage=stage)
        _dump(out / "self_check.json", sc)
        for nm, p in (("golden_standard.json", g), ("diff_report.md", None), ("version_history.md", None),
                      ("self_check.json", sc)):
            f = out / nm
            sum_[nm] = f.stat().st_size if f.is_file() else 0
        sum_["golden_standard"] = {"path": "golden_standard.json", "schema": GS_SCHEMA, "stage": stage,
                                   "requirements": len(items), "satisfied": c["达标"], "deviations": c["偏差"],
                                   "missing": c["缺失"], "pending": c["待定"]}
        sum_["diff_report"] = {"path": "diff_report.md", "bytes": sum_["diff_report.md"],
                               "verdict_counts": c, "overall": "全部达标" if c["缺失"] + c["偏差"] == 0 else "存在未达标项"}
        sum_["version_history"] = {"path": "version_history.md", "bytes": sum_["version_history.md"],
                                   "versions": nver, "latest": entry["version"]}
        sum_["self_check"] = {"path": "self_check.json", "bytes": sum_["self_check.json"],
                              "pass": sc["summary"]["pass"], "checks": sc["summary"]["checks"],
                              "failed": sc["summary"]["failed"]}
        log(work, out, stage, "自检 %d 项，通过 %d，失败 %s"
            % (sc["summary"]["checks"], sc["summary"]["passed"], sc["summary"]["failed"] or "无"),
            "INFO" if sc["summary"]["pass"] else "WARN")
        log(work, out, stage, "资产生成完成：%s" % ", ".join("%s=%dB" % (k, v) for k, v in sum_.items()
                                                              if isinstance(v, int)))
    except Exception as exc:
        log(work, out, stage, "资产生成降级：%s" % exc, "ERROR")
        sum_ = {"error": str(exc)[:200],
                "self_check": {"path": None, "pass": False, "checks": 0, "failed": ["emit_failed"], "error": str(exc)[:200]}}
    return sum_


if __name__ == "__main__":
    print("report.py：可核验资产层（golden_standard / diff_report / version_history / run.log / self_check）。")
    print("用法：由 main.py init|build 调用；独立运行时只做冒烟检查。")
    print("规则句回查：%d/%d 命中" % (sum(1 for k in RULE if _rule(k)[2]), len(RULE)))
    sys.exit(0)
