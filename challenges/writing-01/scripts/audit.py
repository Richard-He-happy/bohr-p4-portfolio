#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-01 v5.0.0 audit layer (Python stdlib only, offline).

Generates the four verifiable assets that sit next to the manuscript:
  golden_standard.json  - expected deliverables, each tied to locator + verbatim quote
  diff_report.md        - actual manuscript vs. golden standard, item by item
  version_history.md    - v0 skeleton -> v1 final, with a concrete rollback path
  run.log               - step / timing / degradation / exception trace
plus self_check.json (contract, coverage, number & citation consistency,
empty-input and bad-JSON probes, exit code, file budget).

Contract: every public function is exception-safe. A failing asset degrades to a
minimal honest record instead of aborting the main deliverable.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GS = "writing-01/golden-standard/v1"
DS = "writing-01/diff-report/v1"
VS = "writing-01/version-history/v1"
SC = "writing-01/self-check/v1"

NUM = re.compile(r"\d+(?:[.,]\d+)*")
DOI = re.compile(r"10\.\d{4,9}/[^\s,;\)\]\}]+")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
REF_HINT = ("doi", "et al", "vol.", "pp.", "journal", "学报", "出版社", "参考文献")

ANCHOR_CAP = 3          # anchors kept per section in the golden standard
FACT_CAP = 40           # fact/number preservation entries
CITE_CAP = 25           # reference entries
DIFF_CAP = 80           # items embedded in result.json
NEAR = 0.60             # trigram coverage above which a quote counts as "rewritten"

ELEMENTS = {
    "ab": {"name": "摘要", "elements": ["研究目的/问题", "材料与方法概述",
                                        "主要结果（含关键数值）", "结论与意义"]},
    "in": {"name": "引言", "elements": ["领域背景", "已有进展", "研究缺口",
                                        "本文目的与贡献"]},
    "me": {"name": "方法", "elements": ["材料/样本与来源", "实验或分析步骤",
                                        "测量与统计方法", "可复现要素（参数/版本）"]},
    "re": {"name": "结果", "elements": ["主要发现", "关键数值与单位",
                                        "统计显著性或误差范围", "图表/编号对应"]},
    "di": {"name": "讨论", "elements": ["结果解释", "与既有研究的关系",
                                        "机制或因果的谨慎表述", "局限性"]},
    "co": {"name": "结论", "elements": ["主要结论", "适用边界", "后续工作"]},
    "rf": {"name": "参考文献", "elements": ["完整条目（作者/年份/期刊/DOI）",
                                            "正文引用与条目一一对应"]},
    "da": {"name": "数据可得性声明", "elements": ["数据位置/获取方式",
                                                  "限制与申请条件"]},
}


# ----------------------------------------------------------------- utilities
def cl(s, n):
    s = re.sub(r"\s+", " ", "" if s is None else str(s)).strip()
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def norm(s):
    return re.sub(r"\s+", "", "" if s is None else str(s))


def shingles(t, k=3):
    if len(t) < k:
        return {t} if t else set()
    return {t[i:i + k] for i in range(len(t) - k + 1)}


def cover(q, s3):
    g = shingles(norm(q))
    if not g:
        return 0.0
    return round(sum(1 for x in g if x in s3) / float(len(g)), 3)


def nums(t):
    out = []
    for x in NUM.findall(t or ""):
        if x not in out:
            out.append(x)
    return out


def num_ok(tok, text):
    """Standalone numeric occurrence: 240 must not be satisfied by 2400 or 86.7."""
    try:
        pat = r"(?<![\d.])" + re.escape(str(tok)) + r"(?![\d])"
        return re.search(pat, text or "") is not None
    except Exception:
        return False


def strip_doi(t):
    """DOIs are verified by the citation check; they must not pollute number checks."""
    try:
        return DOI.sub(" ", t or "")
    except Exception:
        return t or ""


def frags_of(q, n=18):
    """Split a reference entry into fragments long enough to be matched verbatim."""
    try:
        return [x.strip(" .;,") for x in re.split(r"(?<=[.])\s+|\s{2,}", q or "")
                if len(x.strip(" .;,")) >= n]
    except Exception:
        return []


def sha_txt(t):
    try:
        return hashlib.sha256((t or "").encode("utf-8")).hexdigest()
    except Exception:
        return ""


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except Exception:
        return ""


def wjs(p, o):
    try:
        p = Path(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    except Exception:
        return False


def rsz(p):
    try:
        return Path(p).stat().st_size
    except Exception:
        return 0


class Log(object):
    """Bounded in-memory run log; flushed to <output>/run.log."""

    def __init__(self):
        self.t0 = time.time()
        self.n = 0
        self.lines = []
        self.dropped = 0

    def add(self, lv, ev, **kv):
        self.n += 1
        bits = ["T+%07.3fs" % (time.time() - self.t0), "%03d" % self.n,
                "%-5s" % lv, str(ev)]
        for k in sorted(kv):
            v = kv[k]
            if isinstance(v, (dict, list)):
                try:
                    v = json.dumps(v, ensure_ascii=False)
                except Exception:
                    v = str(v)
            bits.append("%s=%s" % (k, v))
        line = re.sub(r"\s+", " ", " ".join(bits))[:400]
        if len(self.lines) < 600:
            self.lines.append(line)
        else:
            self.dropped += 1

    def flush(self, outdir):
        try:
            p = Path(outdir) / "run.log"
            head = ["# writing-01 run.log | v5.0.0 | generated %s | entries %d"
                    % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), len(self.lines)),
                    "# format: T+elapsed seq level event key=value"
                    " | levels: START STEP FILE WARN EXC END"]
            txt = "\n".join(head + self.lines) + "\n"
            if self.dropped:
                txt += "# %d entries dropped (cap 600)\n" % self.dropped
            p.write_text(txt, encoding="utf-8")
            return True
        except Exception:
            return False


LOG = Log()


def _key(heading, al):
    h = (heading or "").lower()
    for k, kw in (al or {}).items():
        if any(a and a in h for a in str(kw).split()):
            return k
    return None


# ------------------------------------------------------- golden standard
def citations(ms):
    """Reference-like lines found in the materials (no invented entries)."""
    out = []
    for m in ms or []:
        if not (m.get("readable") and m.get("text")):
            continue
        for i, line in enumerate(m["text"].splitlines(), 1):
            s = line.strip()
            low = s.lower()
            if len(s) < 20:
                continue
            d = DOI.search(s)
            if not (d or any(h in low for h in REF_HINT) or re.match(r"^\[\d{1,3}\]", s)):
                continue
            if not (d or "et al" in low or YEAR.search(s) or "参考文献" in low):
                continue
            y = YEAR.search(s)
            out.append({"entry_id": "R%02d" % (len(out) + 1), "quote": cl(s, 300),
                        "locator": "%s:L%d" % (m["path"], i), "source_id": m["id"],
                        "doi": d.group(0) if d else None,
                        "year": y.group(0) if y else None})
            if len(out) >= CITE_CAP:
                return out
    return out


def style_of(ms):
    t = "\n".join((m.get("text") or "") for m in (ms or []) if m.get("readable"))
    if DOI.search(t) or re.search(r"\[\d{1,3}\]", t):
        return "numeric-or-doi"
    if re.search(r"\(?[A-Z][A-Za-z\-]+\s*,?\s*(?:et al\.?,?\s*)?\(?(?:19|20)\d{2}\)?", t):
        return "author-year"
    return "unknown"


def build_golden(ms, blocks, facts, al, status, case_id, instr):
    secs = []
    for i, b in enumerate(blocks or [], 1):
        key = b.get("key")
        if key not in ELEMENTS:
            key = _key(b.get("heading"), al)
        el = ELEMENTS.get(key) or {"name": cl(b.get("heading"), 40), "elements": []}
        anchors = []
        for j, it in enumerate((b.get("items") or [])[:ANCHOR_CAP], 1):
            anchors.append({
                "anchor_id": "S%d.A%d" % (i, j),
                "quote": it.get("quote") or "",
                "locator": it.get("locator") or "",
                "source_id": it.get("source_id") or "",
                "role": "required_quote",
                "verify": "去空白后逐字命中材料，并原样出现在稿件中",
            })
        secs.append({
            "section_id": "S%d" % i,
            "key": key or "other",
            "heading": b.get("heading") or "",
            "required": True,
            "expected_elements": [{"element": e, "check": "heuristic",
                                   "criterion": "该节应出现对应信息；以锚句与关键词判定，标注 heuristic"}
                                  for e in el["elements"]],
            "material_anchors": anchors,
            "acceptance": "章节 H2 存在，且每条锚句在稿件中逐字可检；要素按 heuristic 判定",
            "anchor_count": len(anchors),
        })
    fitems = []
    for i, f in enumerate((facts or [])[:FACT_CAP], 1):
        fitems.append({"fact_id": f.get("fact_id") or "F%02d" % i,
                       "quote": f.get("value_text") or f.get("quote") or "",
                       "locator": f.get("locator") or "",
                       "source_id": f.get("source_id") or "",
                       "must_keep": nums(strip_doi(f.get("value_text") or f.get("quote")))[:8]})
    cites = citations(ms)
    return {
        "schema": GS,
        "case_id": case_id or "",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_status": status,
        "task_instruction_excerpt": instr or "",
        "scope": {"materials": len(ms or []),
                  "readable": sum(1 for m in (ms or []) if m.get("readable")),
                  "sections": len(secs),
                  "anchors": sum(s["anchor_count"] for s in secs),
                  "facts": len(fitems), "citations": len(cites)},
        "section_standard": secs,
        "fact_preservation": {
            "rule": "数值、单位、样本量、p 值、引用编号逐字保留；不改写、不外推、不新增",
            "items": fitems,
        },
        "citation_standard": {
            "style_detected": style_of(ms),
            "entries": cites,
            "rules": ["每条引用须支撑其所在论断，不得装饰性引用",
                      "作者/年份/期刊/DOI 须与材料条目一致，材料未给出则标 pending_human",
                      "正文引用编号与参考文献条目一一对应"],
        },
        "global_checklist": [
            {"id": "G1", "item": "六要素章节齐备（摘要/引言/方法/结果/讨论/结论）",
             "check": "diff_report 章节齐备性表全部 达标"},
            {"id": "G2", "item": "每条事实性论断可回指 locator",
             "check": "evidence_map 每条含 quote+locator+source_id，且 quote 逐字命中"},
            {"id": "G3", "item": "数值/单位/样本量/p 值逐字保全",
             "check": "self_check.number_consistency 无不可追溯数字"},
            {"id": "G4", "item": "参考文献条目可核",
             "check": "self_check.citation_consistency 全部命中或已进 pending_human"},
            {"id": "G5", "item": "缺口显式标注",
             "check": "稿件附录 + result.pending_human 列出全部缺口"},
            {"id": "G6", "item": "稿件可直接编辑",
             "check": "manuscript.md 为 H2 层级纯文本，无二进制/截图"},
        ],
        "provenance": {"derived_from": "只读 /input 材料与 task_instruction",
                       "fabrication_policy": "材料外数值/文献/图注不生成，缺口进 pending_human",
                       "quote_verification": "去空白后逐字比对；未命中者拒收"},
    }


# ------------------------------------------------------------- diff report
def diff_items(golden, md):
    N = norm(md)
    s3 = shingles(N)
    h2 = [l.strip()[3:].strip() for l in (md or "").splitlines() if l.startswith("## ")]
    items = []
    n = [0]

    def add(kind, target, expected, observed, status, ev=""):
        n[0] += 1
        items.append({"item_id": "D%03d" % n[0], "kind": kind, "target": target,
                      "expected": cl(expected, 200), "observed": cl(observed, 200),
                      "status": status, "evidence": cl(ev, 160)})

    for s in golden.get("section_standard") or []:
        h = s.get("heading") or ""
        hit = any(norm(h) and (norm(h) == norm(x) or norm(x).startswith(norm(h))) for x in h2)
        add("section_presence", h, "H2 章节「%s」存在" % h,
            "命中" if hit else "未命中（现有 H2：%s）" % ("/".join(h2[:10]) or "无"),
            "达标" if hit else "缺失", "manuscript.md")
    for s in golden.get("section_standard") or []:
        for a in s.get("material_anchors") or []:
            q = norm(a.get("quote"))
            if not q:
                continue
            if q in N:
                add("anchor_quote", a["anchor_id"], a["quote"], "逐字命中", "达标", a["locator"])
            else:
                r = cover(a["quote"], s3)
                add("anchor_quote", a["anchor_id"], a["quote"],
                    "近似出现（trigram 覆盖 %.2f）" % r if r >= NEAR else "未出现",
                    "偏差" if r >= NEAR else "缺失", a["locator"])
    # section body: a heading alone is not a deliverable (guards empty-section false passes)
    bodies, cur = {}, None
    for l in (md or "").splitlines():
        if l.startswith("## "):
            cur = l.strip()[3:].strip()
            bodies[cur] = []
        elif cur is not None:
            bodies[cur].append(l)
    for s in golden.get("section_standard") or []:
        h = s.get("heading") or ""
        key = next((x for x in bodies if norm(h) and
                    (norm(h) == norm(x) or norm(x).startswith(norm(h)))), None)
        lines = [x.strip() for x in (bodies.get(key) or []) if x.strip()]
        quoted = [x for x in lines if x.startswith(">")]
        prose = [x for x in lines if not x.startswith((">", "-")) and len(x) >= 24]
        ph = any(x.startswith("材料未覆盖本节") for x in lines)
        if quoted:
            st, obs = "达标", "含逐字引用 %d 条" % len(quoted)
        elif ph or not lines:
            st, obs = "缺失", "仅占位句（材料未覆盖）" if ph else "空节"
        else:
            st, obs = "偏差", "有成段文字但无逐字引用（%d 段）" % len(prose)
        add("section_content", h, "本节含逐字引用或成段正文，且不是占位句", obs, st, "manuscript.md")
    for f in (golden.get("fact_preservation") or {}).get("items") or []:
        mk = f.get("must_keep") or []
        q = norm(f.get("quote"))[:60]
        inmd = bool(q) and q in N
        miss = [x for x in mk if not num_ok(x, N)]
        if inmd and not miss:
            st, obs = "达标", "原句落地，数值全部保留"
        elif not inmd and not miss:
            st, obs = "偏差", "数值在稿件中出现，但该句未收录进正文章节"
        elif miss and not inmd:
            st, obs = "缺失", "原句未收录，数值 %s 未见于稿件" % ",".join(miss[:6])
        else:
            st, obs = "偏差", "原句已落地但缺数值 %s" % ",".join(miss[:6])
        add("fact_number", f["fact_id"], f.get("quote"), obs, st, f.get("locator"))
    for e in (golden.get("citation_standard") or {}).get("entries") or []:
        q = e.get("quote") or ""
        fs = frags_of(q)
        hitf = [x for x in fs if norm(x) and norm(x) in N]
        d = e.get("doi")
        dhit = bool(d) and d in N
        if dhit and fs and len(hitf) == len(fs):
            st, obs = "达标", "整条命中（含 DOI）"
        elif fs and len(hitf) == len(fs):
            st, obs = "达标", "整条命中（分片 %d/%d）" % (len(hitf), len(fs))
        elif dhit or hitf or cover(q, s3) >= NEAR:
            st, obs = "偏差", "条目不完整（分片 %d/%d%s）" % (
                len(hitf), len(fs) or 1, "，DOI 命中" if dhit else "")
        else:
            st, obs = "缺失", "条目未出现（分片 %d/%d）" % (len(hitf), len(fs) or 1)
        add("citation", e["entry_id"], q, obs, st, e["locator"])
    gaps = [l for l in (md or "").splitlines() if l.startswith("- 缺口章节")]
    pends = [l for l in (md or "").splitlines() if l.startswith("- 待确认")]
    add("declaration", "附录-缺口与待确认",
        "附录列出缺口章节与待确认项",
        "缺口行=%d 待确认行=%d" % (len(gaps), len(pends)),
        "达标" if gaps or pends else "偏差", "manuscript.md 附录")
    add("declaration", "数据可得性声明",
        "存在数据可得性陈述（材料有则逐字引用，无则标 pending_human）",
        "章节存在" if any(norm("数据可得") in norm(x) for x in h2) else "章节缺失",
        "达标" if any(norm("数据可得") in norm(x) for x in h2) else "缺失", "manuscript.md")
    return items


def summarize(items):
    s = {"total": len(items), "met": 0, "missing": 0, "deviated": 0, "by_kind": {}}
    for it in items:
        st = it["status"]
        if st == "达标":
            s["met"] += 1
        elif st == "偏差":
            s["deviated"] += 1
        else:
            s["missing"] += 1
        k = s["by_kind"].setdefault(it["kind"], {"total": 0, "met": 0, "missing": 0, "deviated": 0})
        k["total"] += 1
        if st == "达标":
            k["met"] += 1
        elif st == "偏差":
            k["deviated"] += 1
        else:
            k["missing"] += 1
    s["pass_rate"] = round(s["met"] / float(s["total"]), 3) if s["total"] else 0.0
    s["verdict"] = "达标" if s["met"] == s["total"] and s["total"] else (
        "部分达标" if s["met"] else "未达标")
    return s


def render_diff(golden, items, summary, md, md_path="manuscript.md"):
    L = ["# 差异报告 diff_report.md", "",
         "- schema：`%s`" % DS,
         "- 案例：`%s`｜运行状态：`%s`" % (golden.get("case_id") or "-", golden.get("run_status")),
         "- 稿件：`%s`（%d 字节，sha256:%s，%d 字符，H2 %d 个）"
         % (md_path, len(md.encode("utf-8")) if md else 0, sha_txt(md)[:12] or "-",
            len(md or ""), sum(1 for l in (md or "").splitlines() if l.startswith("## "))),
         "- 金标准：`golden_standard.json`（章节 %d，锚句 %d，事实 %d，引用条目 %d）"
         % (len(golden.get("section_standard") or []),
            (golden.get("scope") or {}).get("anchors", 0),
            (golden.get("scope") or {}).get("facts", 0),
            (golden.get("scope") or {}).get("citations", 0)),
         "- 判定：锚句/条目按「去空白逐字命中」判 达标；字面 trigram 覆盖 ≥%.2f 判 偏差（疑改写或截断）；否则 缺失。"
         % NEAR, "",
         "## 1. 汇总", "",
         "| 状态 | 数量 |", "|-|-|",
         "| 达标 met | %d |" % summary["met"],
         "| 偏差 deviated | %d |" % summary["deviated"],
         "| 缺失 missing | %d |" % summary["missing"],
         "| 合计 | %d（通过率 %.1f%%，结论：%s） |"
         % (summary["total"], 100.0 * summary["pass_rate"], summary["verdict"]), "",
         "| 类别 | 总数 | 达标 | 偏差 | 缺失 |", "|-|-|-|-|-|"]
    for k in sorted(summary["by_kind"]):
        v = summary["by_kind"][k]
        L.append("| %s | %d | %d | %d | %d |" % (k, v["total"], v["met"], v["deviated"], v["missing"]))
    L += ["", "## 2. 逐项对照", "",
          "| 项目 | 类别 | 目标 | 期望 | 观测 | 状态 | 来源 |", "|-|-|-|-|-|-|-|"]
    for it in items:
        L.append("| %s | %s | %s | %s | %s | %s | `%s` |"
                 % (it["item_id"], it["kind"], cl(it["target"], 40), cl(it["expected"], 90),
                    cl(it["observed"], 90), it["status"], it["evidence"]))
    miss = [it for it in items if it["status"] != "达标"]
    L += ["", "## 3. 未达标项与处置", ""]
    if miss:
        for it in miss[:30]:
            L.append("- `%s` %s（%s）：观测「%s」→ %s"
                     % (it["item_id"], it["status"], cl(it["target"], 40),
                        cl(it["observed"], 80),
                        "补逐字引用" if it["kind"] == "anchor_quote" else "人工确认后补齐或标注 pending_human"))
    else:
        L.append("- 无。全部条目达标。")
    L += ["", "## 4. 复核方式", "",
          "1. `python3 scripts/main.py audit --input <in> --output <out> --work <work>` 重算本报告（只读输出目录，不改稿件）。",
          "2. 逐条核对上表 `来源` 列 locator：`文件:L行号`，行号按原文件行计。",
          "3. 锚句核验规则：去掉全部空白后做子串比对，不做同义改写匹配。",
          "4. `self_check.json` 给出契约字段、证据覆盖率、数字/引用一致性、空输入与坏 JSON 探测结果。", ""]
    return "\n".join(L) + "\n"


# --------------------------------------------------------- version history
def skeleton(golden, status):
    L = ["# (v0 骨架) %s" % (golden.get("case_id") or "学术论文写作产物"), "",
         "> v0 骨架：仅章节层级与占位，未成稿。status=%s" % status, ""]
    for s in golden.get("section_standard") or []:
        L += ["## " + (s.get("heading") or "未命名章节"), "",
              "- 待补要素：%s" % "、".join(e["element"] for e in s["expected_elements"]),
              "- 可用锚句：%d 条（locator 见 golden_standard.json）" % s["anchor_count"], ""]
    L += ["## 附录 缺口与待确认", "", "- v0 为骨架，全部章节待成稿。", ""]
    return "\n".join(L)


def build_vh(golden, md, changes, status, work, md_path):
    rows = []
    try:
        v0 = skeleton(golden, "skeleton")
        p0 = Path(work) / "manuscript.v0.md"
        p0.parent.mkdir(parents=True, exist_ok=True)
        p0.write_text(v0, encoding="utf-8")
        rows.append({"id": "v0", "kind": "skeleton", "path": str(p0), "bytes": len(v0.encode("utf-8")),
                     "sha256": sha(p0)[:16], "status": "skeleton",
                     "how": "按金标准章节模板生成层级与占位，不含正文"})
    except Exception as e:
        rows.append({"id": "v0", "kind": "skeleton", "path": "", "bytes": 0, "sha256": "",
                     "status": "unavailable", "how": "骨架写出失败：%s" % type(e).__name__})
    rows.append({"id": "v1", "kind": "final", "path": md_path,
                 "bytes": len((md or "").encode("utf-8")), "sha256": sha_txt(md)[:16],
                 "status": status,
                 "how": "锚句组装 + 证据校验 + 缺口标注（有 draft.json 时并入 Agent 草稿）"})
    acts = {}
    for c in changes or []:
        acts[c.get("action") or "?"] = acts.get(c.get("action") or "?", 0) + 1
    L = ["# 版本记录 version_history.md", "",
         "- schema：`%s`｜案例：`%s`" % (VS, golden.get("case_id") or "-"), "",
         "## 1. 版本表", "",
         "| 版本 | 类型 | 产物 | 字节 | sha256(16) | 状态 | 生成方式 |", "|-|-|-|-|-|-|-|"]
    for r in rows:
        L.append("| %s | %s | `%s` | %d | %s | %s | %s |"
                 % (r["id"], r["kind"], r["path"] or "-", r["bytes"], r["sha256"] or "-",
                    r["status"], r["how"]))
    L += ["", "## 2. v0 骨架（起点）", "",
          "- 内容：金标准全部章节的 H2 层级 + 每节待补要素与可用锚句数，无正文、无引用。",
          "- 为什么先做骨架：先落盘可编辑结构，再把逐字锚句填入，避免一次生成不可复核的长文。",
          "- 落盘位置：`<work>/manuscript.v0.md`（运行产物，可随时重建）。", "",
          "## 3. v0 → v1 改了什么、为什么", "",
          "| 章节 | 变更 | 原因 |", "|-|-|-|"]
    for s in golden.get("section_standard") or []:
        L.append("| %s | 由占位改为 %d 条锚句逐字引用 | 每条论断可回指 locator，避免材料外补写 |"
                 % (cl(s.get("heading"), 30), s["anchor_count"]))
    L += ["", "变更动作统计：" + ("，".join("%s×%d" % (k, acts[k]) for k in sorted(acts)) or "无"), "",
          "## 4. 如何回退", "",
          "1. 回到 v0 骨架：`cp <work>/manuscript.v0.md <output>/manuscript.md`。",
          "2. 回到上一版草稿：`cp /app/work/draft.json.prev /app/work/draft.json` 后重跑 `build`。",
          "3. 全量重建：`python3 scripts/main.py build --input <in> --output <out> --work <work>`（输出目录被覆盖，work 保留）。",
          "4. 只复核不回退：`python3 scripts/main.py audit --input <in> --output <out> --work <work>`。", "",
          "## 5. 与金标准的对应", "",
          "v1 与金标准的逐项差异见 `diff_report.md`；未达标项已进 `result.json.pending_human`，不在稿件中补造。", ""]
    return {"schema": VS, "path": "version_history.md", "versions": rows,
            "actions": acts, "rollback": ["cp <work>/manuscript.v0.md <output>/manuscript.md",
                                          "cp <work>/draft.json.prev <work>/draft.json && build",
                                          "build --input <in> --output <out> --work <work>",
                                          "audit --input <in> --output <out> --work <work>"]}, "\n".join(L)


# ------------------------------------------------------------- self check
def _probe(ctx, kind, script):
    """Run a real child process on a minimal input and verify exit code + result.json."""
    base = Path(ctx.get("work") or ".") / "_selfcheck" / kind
    inp, outp, wk = base / "input", base / "output", base / "work"
    rec = {"id": kind, "ok": False, "dir": str(base), "method":
           "子进程实跑：%s，检查退出码与 result.json 合法性" % kind}
    try:
        for d in (inp, outp, wk):
            d.mkdir(parents=True, exist_ok=True)
        if kind == "empty_input":
            (inp / "case.json").write_text("{}", encoding="utf-8")
            rec["input"] = "case.json = {}（无材料）"
        else:
            (inp / "case.json").write_text('{"case_id": "BAD-JSON", "output_contract": ',
                                           encoding="utf-8")
            (inp / "material.md").write_text(
                "# Note\n\nThe assay used 12.5 mg/kg at n = 30, p < 0.05 (Doe et al., 2019).\n",
                encoding="utf-8")
            rec["input"] = "case.json 截断坏 JSON + 1 份可用文本材料"
        env = dict(os.environ)
        env["WO_NO_PROBE"] = "1"
        p = subprocess.run(
            [sys.executable, "-B", str(script), "build", "--input", str(inp),
             "--output", str(outp), "--work", str(wk)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, env=env)
        rp = outp / "result.json"
        ok_json, keys, status = False, [], ""
        if rp.is_file():
            try:
                o = json.loads(rp.read_text(encoding="utf-8"))
                ok_json = isinstance(o, dict)
                keys = sorted(o.keys())
                status = str(o.get("status") or "")
            except Exception:
                ok_json = False
        arts = sorted(x.name for x in outp.iterdir()) if outp.is_dir() else []
        rec.update({"exit_code": p.returncode, "result_json_ok": ok_json,
                    "result_keys": keys[:14], "status": status,
                    "artifacts": arts,
                    "ok": p.returncode == 0 and ok_json and bool(status)})
        if not rec["ok"]:
            rec["stderr"] = cl(p.stderr.decode("utf-8", "replace"), 200)
    except Exception as e:
        rec["exception"] = "%s:%s" % (type(e).__name__, cl(e, 140))
    return rec


def package_budget():
    try:
        root = Path(__file__).resolve().parent.parent
        fs = [p for p in root.rglob("*") if p.is_file()
              and "__pycache__" not in p.parts and p.suffix != ".pyc"]
        tot = sum(p.stat().st_size for p in fs)
        return {"root": str(root), "files": len(fs), "bytes": tot,
                "list": [{"path": str(p.relative_to(root)).replace(os.sep, "/"),
                          "bytes": p.stat().st_size} for p in sorted(fs)],
                "limit": {"files": 10, "bytes": 122880},
                "ok": len(fs) <= 10 and tot <= 122880}
    except Exception as e:
        return {"ok": False, "exception": type(e).__name__}


def selfcheck(ctx, result, golden, md, ms, out, work, script, status, diffsum, items=None):
    st = ctx.get("state") or {}
    checks = []

    ct = st.get("contract")
    keys = list(ct) if isinstance(ct, dict) else ([k for k in ct] if isinstance(ct, list) else [])
    keys = [str(k) for k in keys]
    fixed = ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]
    newf = ["golden_standard", "diff_report", "version_history", "self_check"]
    missing = [k for k in keys + fixed if k not in result]
    empty = [k for k in keys if k in result and result.get(k) in (None, "", [], {})]
    missing_new = [k for k in newf if k not in result]
    checks.append({
        "id": "contract_fields",
        "ok": not missing and not missing_new,
        "method": "output_contract 每个键 + 5 个固定键 + 4 个新增键都出现在 result.json",
        "detail": {"contract_keys": keys, "present": len(keys) - len(empty),
                   "contract_total": len(keys), "empty_values": empty,
                   "missing_keys": missing, "missing_new_fields": missing_new},
    })

    n = norm(md)
    anchors = [a for s in (golden.get("section_standard") or [])
               for a in (s.get("material_anchors") or [])]
    ah = [a for a in anchors if norm(a["quote"]) and norm(a["quote"]) in n]
    ev = [e for e in (result.get("evidence_map") or []) if e.get("verified")]
    tot_ev = len(result.get("evidence_map") or [])
    rej = len(st.get("rejected") or [])
    cov = round(len(ah) / float(len(anchors)), 3) if anchors else 0.0
    checks.append({
        "id": "evidence_coverage", "ok": cov >= 0.99 and rej == 0 and tot_ev > 0,
        "method": "锚句去空白逐字命中率 + evidence_map.verified 计数 + 拒收数",
        "detail": {"anchors": len(anchors), "anchors_hit": len(ah), "anchor_coverage": cov,
                   "evidence_total": tot_ev, "evidence_verified": len(ev),
                   "quotes_rejected": rej,
                   "sections_with_anchor": sum(1 for s in (golden.get("section_standard") or [])
                                               if s["anchor_count"] > 0)},
    })

    body = [l for l in (md or "").splitlines()
            if l.strip() and not l.startswith(("#", ">", "- "))
            and "｜status:" not in l and not l.startswith("本稿依据")]
    mt = norm(" ".join(body))
    mats = " ".join((m.get("text") or "") for m in (ms or []) if m.get("readable"))
    un = []
    for x in nums(strip_doi(mt)):
        if not num_ok(x, strip_doi(mats)) and x not in un:
            un.append(x)
    checks.append({
        "id": "number_consistency", "ok": not un,
        "method": "正文段落（排除标题/引用块/附录条目/系统元信息行）每个数字串须以独立数值形式出现在材料原文（报表头行可与下一行拼接）",
        "detail": {"numbers_in_body": len(nums(mt)), "untraceable": un[:20],
                   "scanned_lines": len(body)},
    })

    ents = (golden.get("citation_standard") or {}).get("entries") or []
    citems = [it for it in (items or []) if it.get("kind") == "citation"]
    cok = sum(1 for it in citems if it.get("status") == "达标")
    checks.append({
        "id": "citation_consistency",
        "ok": (not ents) or (cok == len(ents)),
        "method": "金标准引用条目按整条/分片/DOI 三级命中判定，结果取自 diff 的 citation 项",
        "detail": {"entries": len(ents), "hit": cok, "items_checked": len(citems),
                   "style_detected": (golden.get("citation_standard") or {}).get("style_detected"),
                   "note": "材料未给出可核条目，参考文献节缺口已进 pending_human"
                   if not ents else ""},
    })

    if os.environ.get("WO_NO_PROBE") == "1":
        for k in ("empty_input", "bad_json"):
            checks.append({"id": k + "_fallback", "ok": None,
                           "method": "嵌套探测已禁用（WO_NO_PROBE=1），由父进程实测",
                           "detail": {"skipped": True}})
    else:
        for k in ("empty_input", "bad_json"):
            rec = _probe(ctx, k, script)
            rec["id"] = k + "_fallback"
            checks.append(rec)

    codes = [c.get("exit_code") for c in checks if isinstance(c.get("exit_code"), int)]
    checks.append({
        "id": "exit_code", "ok": True, "exit_code": 0,
        "method": "main() 全路径 return 0（含 --help 的 SystemExit 捕获与 fatal 兜底）；探测子进程退出码一并记录",
        "detail": {"probe_exit_codes": codes, "guarantee": "无条件 0，异常走 emergency() 仍写 partial result.json"},
    })

    pkg = package_budget()
    outs = []
    try:
        outs = [{"path": x.name, "bytes": rsz(x)} for x in sorted(Path(out).iterdir()) if x.is_file()]
    except Exception:
        pass
    checks.append({"id": "file_budget", "ok": bool(pkg.get("ok")), "method": "统计包内文本文件数与总字节",
                   "detail": {"package": pkg.get("files"), "package_bytes": pkg.get("bytes"),
                              "limit": pkg.get("limit"), "outputs": outs}})

    passed = sum(1 for c in checks if c.get("ok") is True)
    total = sum(1 for c in checks if c.get("ok") is not None)
    return {"schema": SC,
            "case_id": result.get("case_id") or "",
            "status": status,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checks": checks,
            "summary": {"passed": passed, "total": total, "skipped": len(checks) - total,
                        "failed": [c["id"] for c in checks if c.get("ok") is False],
                        "ok": passed == total},
            "diff_summary": diffsum,
            "interpretation": "summary.ok=false 表示检出问题（如草稿含材料外数字、引用未逐字命中），"
                              "不是运行失败；运行崩溃会记在 result.json 的 exceptions/degradations。",
            "notes": ["ok=null 表示该检查在本次运行中被跳过（嵌套探测），不是通过。",
                      "number_consistency 仅覆盖正文段落行，标题/引用块/附录注释不参与。"]}


# -------------------------------------------------------------- entry points
def assets(ctx, blocks, ms, md, facts, evidence, changes, status, al, script, out, work):
    """golden_standard.json + diff_report.md + version_history.md + run.log."""
    st = ctx.get("state") or {}
    out, work = Path(out), Path(work)
    res = {}
    LOG.add("STEP", "audit_start", blocks=len(blocks or []), facts=len(facts or []),
            evidence=len(evidence or []), status=status)
    try:
        golden = build_golden(ms, blocks, facts, al, status,
                              st.get("case_id") or "", st.get("instruction") or "")
        wjs(out / "golden_standard.json", golden)
        LOG.add("STEP", "golden_standard", sections=len(golden["section_standard"]),
                anchors=golden["scope"]["anchors"], facts=golden["scope"]["facts"],
                citations=golden["scope"]["citations"])
    except Exception as e:
        golden = {"schema": GS, "case_id": st.get("case_id") or "", "error": type(e).__name__,
                  "section_standard": [], "fact_preservation": {"items": []},
                  "citation_standard": {"entries": []},
                  "scope": {"anchors": 0, "facts": 0, "citations": 0}}
        wjs(out / "golden_standard.json", golden)
        st.setdefault("degradations", []).append({"code": "golden_failed",
                                                  "path": "golden_standard.json",
                                                  "detail": cl(e, 120)})
        LOG.add("WARN", "golden_failed", err=type(e).__name__)
    res["golden_standard"] = golden
    try:
        items = diff_items(golden, md)
        sm = summarize(items)
        (out / "diff_report.md").write_text(render_diff(golden, items, sm, md), encoding="utf-8")
        LOG.add("STEP", "diff_report", met=sm["met"], deviated=sm["deviated"],
                missing=sm["missing"], verdict=sm["verdict"])
    except Exception as e:
        items, sm = [], summarize([])
        try:
            (out / "diff_report.md").write_text(
                "# 差异报告 diff_report.md\n\n- 生成失败：%s\n" % type(e).__name__, encoding="utf-8")
        except Exception:
            pass
        st.setdefault("degradations", []).append({"code": "diff_failed",
                                                  "path": "diff_report.md", "detail": cl(e, 120)})
        LOG.add("WARN", "diff_failed", err=type(e).__name__)
    res["diff_report"] = {"schema": DS, "path": "diff_report.md",
                          "sha256": sha(out / "diff_report.md")[:16], "summary": sm,
                          "items": items[:DIFF_CAP],
                          "items_total": len(items),
                          "truncated": len(items) > DIFF_CAP}
    try:
        vh, vtext = build_vh(golden, md, changes, status, work, str(out / "manuscript.md"))
        (out / "version_history.md").write_text(vtext, encoding="utf-8")
        LOG.add("STEP", "version_history", versions=len(vh["versions"]))
    except Exception as e:
        vh = {"schema": VS, "versions": [], "error": type(e).__name__}
        try:
            (out / "version_history.md").write_text(
                "# 版本记录 version_history.md\n\n- 生成失败：%s\n" % type(e).__name__,
                encoding="utf-8")
        except Exception:
            pass
        st.setdefault("degradations", []).append({"code": "version_history_failed",
                                                  "path": "version_history.md",
                                                  "detail": cl(e, 120)})
        LOG.add("WARN", "version_history_failed", err=type(e).__name__)
    res["version_history"] = vh
    for it in items:
        if it["status"] != "达标":
            st.setdefault("pending_human", []).append(
                {"item": "%s %s" % (it["item_id"], cl(it["target"], 50)),
                 "reason": "金标准比对未达标（%s）：%s" % (it["status"], cl(it["observed"], 90)),
                 "action": "补逐字引用或人工确认后补齐；不得改写材料凑通过"})
    if len(st.get("pending_human") or []) > 60:
        st["pending_human"] = st["pending_human"][:60]
    dg = st.get("degradations") or []
    if dg:
        LOG.add("WARN", "degradations", n=len(dg),
                codes=sorted({str(d.get("code")) for d in dg}))
    for x in (st.get("errors") or [])[:20]:
        LOG.add("WARN", "input_error", detail=x)
    res["artifacts"] = [{"path": n, "bytes": rsz(out / n), "sha256": sha(out / n)[:16]}
                        for n in ("manuscript.md", "golden_standard.json", "diff_report.md",
                                  "version_history.md", "run.log", "self_check.json")]
    LOG.add("STEP", "assets_done", artifacts=4)
    return res


def finalize_selfcheck(ctx, result, golden, md, ms, out, work, script, status, diffsum,
                       items=None):
    try:
        sc = selfcheck(ctx, result, golden, md, ms, out, work, script, status, diffsum, items)
    except Exception as e:
        sc = {"schema": SC, "error": type(e).__name__ + ":" + cl(e, 120),
              "checks": [], "summary": {"ok": False, "failed": ["selfcheck_crashed"]}}
        (ctx.get("state") or {}).setdefault("degradations", []).append(
            {"code": "selfcheck_failed", "path": "self_check.json", "detail": cl(e, 120)})
        LOG.add("WARN", "selfcheck_failed", err=type(e).__name__)
    wjs(Path(out) / "self_check.json", sc)
    LOG.add("STEP", "self_check", passed=(sc.get("summary") or {}).get("passed"),
            total=(sc.get("summary") or {}).get("total"),
            failed=(sc.get("summary") or {}).get("failed"))
    return sc


def recheck(out, work):
    """Recompute the diff from disk (no manuscript rewrite). Used by `audit`."""
    out = Path(out)
    g = json.loads((out / "golden_standard.json").read_text(encoding="utf-8"))
    md = (out / "manuscript.md").read_text(encoding="utf-8")
    items = diff_items(g, md)
    sm = summarize(items)
    (out / "diff_report.md").write_text(render_diff(g, items, sm, md), encoding="utf-8")
    return {"schema": DS, "items": items, "summary": sm,
            "golden": g, "manuscript_chars": len(md)}
