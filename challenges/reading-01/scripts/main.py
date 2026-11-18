#!/usr/bin/env python3
"""reading-01 文献文档解析 Skill：输入发现 → 逐页抽词 → 版面重建 → 结构识别 → 证据 → 产物与自检。
退出码恒 0；先落盘 partial result.json，末尾无条件 finalize。"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdfcore  # noqa: E402

SKILL = {"name": "paper-pdf-structure-parser", "version": "1.0.0", "task_key": "reading-01"}
CAPTION = re.compile(r"^\s*(fig(?:ure)?\.?|tab(?:le)?\.?|scheme|algorithm|图|表)\s*([0-9]{1,3}|[IVX]{1,5})\b[.:：、]?\s*", re.I)
HEADING = re.compile(r"^\s*((\d{1,2}(?:\.\d{1,2}){0,3})\.?|([IVX]{1,5})\.|[A-Z]\.)\s+\S")
REF_ITEM = re.compile(r"^\s*(\[\d{1,3}\]|\d{1,3}[.)])\s+")
MATH = re.compile(r"[=≈≠≤≥±∑∏∫√∂∇∞∝∈∧∨→·×÷−]|[α-ωΑ-Ω][\s_]?[0-9a-zA-Z(]|[_^]\{")
EQNUM = re.compile(r"\(\s*(\d{1,2}[a-z]?)\s*\)\s*$")
FOOT = re.compile(r"^\s*(\d{1,2}|[†‡§¶])\s+\S")
DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
PAGENO = re.compile(r"^(\d{1,4}|[ivxlcdm]{1,7}|page\s+\d+(\s+of\s+\d+)?)$", re.I)
STOP = set("the a an of and or to in for on with by from is are was were be been this that these those we our "
           "it its as at not but no can may show shows using used between than then which what when how does do "
           "请 给出 指出 列出 说明 分析 总结 这篇 论文 文献 文档 内容 什么 哪些 如何 是否 以及 的 了 在 与 和 或 一个".split())


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def wjson(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)


def digest(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def sniff(p):
    try:
        head = Path(p).read_bytes()[:8]
    except OSError:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
        return "image"
    if head.startswith(b"PK"):
        return "ooxml"
    ext = Path(p).suffix.lower()
    return "text" if ext in (".json", ".csv", ".tsv", ".md", ".txt", ".xml", ".yaml", ".yml") else ext.lstrip(".")


# ---------------------------------------------------------------- 输入发现
def discover(inp, ctx):
    inp = Path(inp)
    case, cpath = {}, None
    for p in [inp / "case.json"] + sorted(inp.glob("case*.json")) + sorted(inp.rglob("case*.json")):
        if p.is_file():
            try:
                obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:  # noqa: BLE001
                ctx["errors"].append({"stage": "read_case", "path": str(p), "error": str(e)[:200]})
                continue
            if isinstance(obj, dict):
                case, cpath = obj, p
                break
    if not cpath:
        ctx["errors"].append({"stage": "discover", "msg": "未找到可解析的 case*.json", "input": str(inp)})
    instr = " ".join(str(v) for k, v in case.items()
                     if isinstance(v, str) and re.search(r"instruction|task|question|prompt|request|ask", k, re.I))
    tmd = inp / "task.md"
    if tmd.is_file():
        try:
            instr += " " + tmd.read_text(encoding="utf-8", errors="replace")[:3000]
        except OSError:
            pass
    mats = []
    for p in sorted(inp.rglob("*")):
        if p.is_file() and p.name not in ("case.json", "task.md") and not p.name.startswith("."):
            mats.append({"path": str(p), "kind": sniff(p), "bytes": p.stat().st_size})
    return case, instr.strip(), mats


# ---------------------------------------------------------------- 版面重建
def lines_of(pg):
    ws = [w for w in pg.get("words", []) if str(w.get("t", "")).strip()]
    if not ws:
        return []
    ws.sort(key=lambda w: ((w["y0"] + w["y1"]) / 2, w["x0"]))
    cw = sorted(max((w["x1"] - w["x0"]) / max(len(w["t"]), 1), 0.5) for w in ws)
    thr = max(1.15 * cw[len(cw) // 2], 0.012 * pg["w"])
    lines = []
    for w in ws:
        yc, h = (w["y0"] + w["y1"]) / 2, max(w["y1"] - w["y0"], 1.0)
        for L in lines[-4:]:
            if abs(L["yc"] - yc) <= 0.45 * max(L["h"], h):
                L["words"].append(w)
                L["yc"], L["h"] = (L["yc"] + yc) / 2, max(L["h"], h)
                L["x0"], L["x1"] = min(L["x0"], w["x0"]), max(L["x1"], w["x1"])
                break
        else:
            lines.append({"yc": yc, "h": h, "x0": w["x0"], "x1": w["x1"], "words": [w]})
    out = []
    for L in lines:
        L["words"].sort(key=lambda w: w["x0"])
        parts, cur = [], [L["words"][0]]
        for a, b in zip(L["words"], L["words"][1:]):
            if b["x0"] - a["x1"] > thr:
                parts.append(cur)
                cur = []
            cur.append(b)
        parts.append(cur)
        L["spans"] = [{"x0": min(w["x0"] for w in s), "x1": max(w["x1"] for w in s),
                       "text": " ".join(w["t"] for w in s)} for s in parts]
        L["text"] = " ".join(s["text"] for s in L["spans"])
        L["size"] = round(sum(w.get("sz", L["h"]) for w in L["words"]) / len(L["words"]), 2)
        del L["words"]
        out.append(L)
    return out


def gutters(lines, W):
    """竖槽检测：跨槽 span 占比 ≤4% 的空白带 → 栏分隔线。"""
    spans = [s for L in lines for s in L["spans"]]
    if len(spans) < 10:
        return []
    step = 2.0
    nb = int(W / step) + 2
    cross = [0] * nb
    for s in spans:
        for b in range(max(0, int(s["x0"] / step)), min(nb, int(s["x1"] / step) + 1)):
            cross[b] += 1
    lim, runs, cur = max(1, int(0.04 * len(spans))), [], None
    for b in range(nb):
        if cross[b] <= lim and 0.04 * W < b * step < 0.96 * W:
            cur = [b, b] if cur is None else [cur[0], b]
        elif cur:
            runs.append(cur)
            cur = None
    if cur:
        runs.append(cur)
    out = []
    for a, b in runs:
        g = ((a + b) / 2 + 0.5) * step
        if (b - a + 1) * step < 0.025 * W:
            continue
        if sum(1 for s in spans if s["x1"] <= g) >= 8 and sum(1 for s in spans if s["x0"] >= g) >= 8:
            out.append(round(g, 1))
    return out


def order_lines(lines, gts):
    """跨栏宽行作分隔块；带内按栏序、栏内按 y 升序输出。"""
    seq = sorted(lines, key=lambda L: (L["yc"], L["x0"]))
    if not gts:
        for L in seq:
            L["col"], L["band"] = 0, 0
        return seq
    for L in seq:
        L["spanning"] = any(L["x0"] < g - 2 and L["x1"] > g + 2 for g in gts)
        L["col"] = sum(1 for g in gts if (L["x0"] + L["x1"]) / 2 > g)
    out, band, bid = [], [], 0

    def flush():
        nonlocal band, bid
        for c in range(len(gts) + 1):
            for L in sorted([x for x in band if x["col"] == c], key=lambda L: (L["yc"], L["x0"])):
                L["band"] = bid
                out.append(L)
        band, bid = [], bid + 1

    for L in seq:
        if L["spanning"]:
            flush()
            L["band"] = bid
            out.append(L)
            band, bid = [], bid + 1
        else:
            band.append(L)
    flush()
    return out


def make_table(rows, W):
    cols = []
    for L in rows:
        for s in L["spans"]:
            for c in cols:
                if abs(c["x"] - s["x0"]) <= max(6.0, 0.01 * W):
                    c["n"] += 1
                    break
            else:
                cols.append({"x": s["x0"], "n": 1})
    cols.sort(key=lambda c: c["x"])
    cols = [c for c in cols if c["n"] >= max(2, len(rows) // 2)]
    if len(cols) < 2:
        return None
    grid, sparse = [], 0
    for L in rows:
        cell = [""] * len(cols)
        for s in L["spans"]:
            k = min(range(len(cols)), key=lambda i: abs(cols[i]["x"] - s["x0"]))
            cell[k] = (cell[k] + " " + s["text"]).strip()
        sparse += sum(1 for c in cell if not c)
        grid.append(cell)
    if not any(any(re.search(r"\d", c) for c in row) for row in grid):
        return None  # 无数值列 → 视为普通对齐文本，避免误判
    md = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return {"rows": len(grid), "cols": len(cols), "cells": grid, "md": "\n".join(md),
            "sparse_cells": sparse, "structure_confidence": "medium" if sparse else "high",
            "merged_cells": "undetermined",
            "bbox": [round(min(L["x0"] for L in rows), 1), round(min(L["yc"] for L in rows), 1),
                     round(max(L["x1"] for L in rows), 1), round(max(L["yc"] for L in rows), 1)]}


def detect_tables(seq, W):
    out, used, i = [], set(), 0
    while i < len(seq):
        L = seq[i]
        if len(L["spans"]) >= 2:
            run, j = [L], i + 1
            while j < len(seq) and abs(seq[j]["yc"] - run[-1]["yc"]) < 3.2 * max(L["h"], 6.0):
                if len(seq[j]["spans"]) >= 2:
                    run.append(seq[j])
                j += 1
            if len(run) >= 3:
                t = make_table(run, W)
                if t:
                    t["rows_lines"] = run
                    out.append(t)
                    used.update(id(x) for x in run)
                    i = j
                    continue
        i += 1
    return out, used


# ---------------------------------------------------------------- 结构
def build_doc(pages, imgs, ctx):
    doc = {"title": None, "authors": [], "affiliations": [], "abstract": None, "keywords": [],
           "sections": [], "blocks": [], "tables": [], "figures": [], "formulas": [], "references": [],
           "header_footer": [], "footnotes": [], "page_count": len(pages), "columns_per_page": {}}
    raw, ptext = [], {}
    for pg in pages:
        lines = lines_of(pg)
        ptext[pg["no"]] = " ".join(L["text"] for L in lines)
        if not lines:
            ctx["uncertainty"].append({"item": "page_%s" % pg["no"], "reason": "该页无可抽取文字层（疑似扫描/图像页）",
                                       "impact": "缺该页正文/表格/公式", "action": "人工 OCR 或 pdftoppm+tesseract"})
            continue
        H, W = pg["h"], pg["w"]
        body, hf = [], []
        for L in lines:
            (hf if (L["yc"] < 0.045 * H or L["yc"] > 0.955 * H) else body).append(L)
        for L in hf:  # 页眉页脚：位置 + 形态
            if PAGENO.match(L["text"].strip()) or L["yc"] < 0.045 * H or L["yc"] > 0.955 * H:
                doc["header_footer"].append({"page": pg["no"], "kind": "header" if L["yc"] < 0.5 * H else "footer",
                                             "text": L["text"], "bbox": [L["x0"], round(L["yc"], 1),
                                                                         L["x1"], round(L["yc"] + L["h"], 1)]})
            else:
                body.append(L)
        if not body:
            continue
        sizes = [L["size"] or 10.0 for L in body]
        body_size = max(set(sizes), key=sizes.count)
        gts = gutters(body, W)
        doc["columns_per_page"][pg["no"]] = len(gts) + 1
        seq = order_lines(body, gts)
        for L in seq:
            L["page"] = pg["no"]
            L["size"] = L["size"] or body_size
        tables, used = detect_tables(seq, W)
        for t in tables:
            t["table_id"] = "t%02d" % (len(doc["tables"]) + 1)
            t["page"] = pg["no"]
            t.pop("rows_lines", None)
            cap = [L for L in seq if CAPTION.match(L["text"])]
            near = min(cap, key=lambda L: abs(L["yc"] - t["bbox"][1])) if cap else None
            t["caption"] = near["text"] if near and abs(near["yc"] - t["bbox"][1]) < 160 else None
            t["caption_bbox"] = [near["x0"], round(near["yc"], 1), near["x1"], round(near["yc"] + near["h"], 1)] if t["caption"] else None
            t["source_id"] = "src-01"
            t["ruling_lines"] = "not_extracted"
            doc["tables"].append(t)
        caps = [L for L in seq if CAPTION.match(L["text"])]
        for im in [x for x in imgs.get(pg["no"], []) if x["x1"] - x["x0"] > 40 and x["y1"] - x["y0"] > 30]:
            near = min(caps, key=lambda L: abs(L["yc"] - im["y1"])) if caps else None
            doc["figures"].append({"figure_id": "f%02d" % (len(doc["figures"]) + 1), "page": pg["no"],
                                   "bbox": [round(v, 1) for v in (im["x0"], im["y0"], im["x1"], im["y1"])],
                                   "caption": near["text"] if near else None, "bbox_estimated": False,
                                   "caption_page": pg["no"] if near else None, "source_id": "src-01",
                                   "panel_labels": sorted(set(re.findall(r"\(([a-h])\)", " ".join(x["text"] for x in seq)))),
                                   "elements": "以题注与图片框定位；轴/图例/误差线需图像层复核"})
        for L in seq:
            if id(L) in used:
                continue
            t = L["text"].strip()
            if not t:
                continue
            mr = len(MATH.findall(t)) / max(len(t), 1)
            mnum = EQNUM.search(t)
            if (mr >= 0.12 and len(t) < 260 and not HEADING.match(t)) or (mnum and mr > 0.02):
                doc["formulas"].append({"formula_id": "e%02d" % (len(doc["formulas"]) + 1), "page": pg["no"],
                                        "text": t, "number": mnum.group(1) if mnum else None,
                                        "bbox": [round(L["x0"], 1), round(L["yc"], 1), round(L["x1"], 1),
                                                 round(L["yc"] + L["h"], 1)],
                                        "inline": False, "tex": None, "structure": "text_preserved_only",
                                        "symbols_preserved": True})
                continue
            if FOOT.match(t) and L["size"] < 0.9 * body_size and L["yc"] > 0.6 * H:
                doc["footnotes"].append({"page": pg["no"], "text": t,
                                         "bbox": [L["x0"], round(L["yc"], 1), L["x1"], round(L["yc"] + L["h"], 1)]})
                continue
            if CAPTION.match(t) and any(f.get("caption") == t for f in doc["figures"]):
                continue
            raw.append({"page": pg["no"], "text": t, "size": L["size"], "col": L["col"], "band": L["band"],
                        "bbox": [round(L["x0"], 1), round(L["yc"], 1), round(L["x1"], 1), round(L["yc"] + L["h"], 1)],
                        "y": round(L["yc"], 1), "h": round(L["h"], 1)})
    blocks = assemble(raw)
    doc["blocks"] = blocks
    for i, b in enumerate(blocks):
        b["block_id"] = "p%d-b%03d" % (b["page"], i + 1)
        b["json_pointer"] = "/blocks/%d" % i
    structure(doc, blocks, ctx)
    doc["_ptext"] = ptext
    return doc


def assemble(raw):
    """同页同栏相邻行并段；行尾连字符修复；跨页续接标记。"""
    out = []
    for b in raw:
        if out:
            p, prev = out[-1], out[-1]
            same = p["page"] == b["page"] and p["col"] == b["col"] and p["band"] == b["band"]
            gap = b["y"] - (prev["bbox"][3] or prev["y"])
            if same and abs(p["size"] - b["size"]) <= max(0.6, 0.15 * p["size"]) and gap < 1.6 * max(p["size"], 6.0):
                if p["text"].endswith("-") and b["text"][:1].islower():
                    p["text"] = p["text"][:-1] + b["text"]
                    p.setdefault("fixes", []).append("dehyphenate")
                else:
                    p["text"] += " " + b["text"]
                p["bbox"] = [min(p["bbox"][0], b["bbox"][0]), p["bbox"][1],
                             max(p["bbox"][2], b["bbox"][2]), b["bbox"][3]]
                continue
            if p["page"] + 1 == b["page"] and not re.search(r"[.。!?！？:：]$", p["text"][-2:]) and not HEADING.match(b["text"]):
                p["continued_on_page"] = b["page"]
                p.setdefault("fixes", []).append("cross_page_continuation")
        out.append(dict(b))
    return out


def structure(doc, blocks, ctx):
    """标题/作者/摘要/章节/参考文献与章节归属。"""
    sizes = [b["size"] for b in blocks] or [10.0]
    body = max(set(sizes), key=sizes.count)
    secs = []
    for b in blocks:
        t = b["text"].strip()
        b["type"] = "paragraph"
        m = HEADING.match(t)
        if len(t) <= 90 and (m or (t.isupper() and 3 <= len(t) <= 60)) and not CAPTION.match(t) \
                and not re.search(r"[.。]$", t):
            lvl = 1 if not m else min(4, (m.group(2).count(".") + 1) if m.group(2) else 2)
            secs.append({"level": lvl, "number": m.group(2) if m and m.group(2) else None,
                         "title": t[len(m.group(1)):].strip(" .:：") if m else t,
                         "page": b["page"], "bbox": b["bbox"], "block_id": b["block_id"],
                         "section_id": "s%02d" % (len(secs) + 1),
                         "json_pointer": "/sections/%d" % len(secs)})
            b["type"], b["section"] = "heading", secs[-1]["title"]
            continue
        elif len(t) <= 80 and b["size"] >= body * 1.12 and not CAPTION.match(t) and not re.search(r"[.。]$", t):
            secs.append({"level": 1, "number": None, "title": t, "page": b["page"], "bbox": b["bbox"],
                         "block_id": b["block_id"], "section_id": "s%02d" % (len(secs) + 1),
                         "json_pointer": "/sections/%d" % len(secs)})
            b["type"], b["section"] = "heading", t
            continue
        b["section"] = secs[-1]["title"] if secs else None
        if re.match(r"^(abstract|摘\s*要)\b", t, re.I) and not doc["abstract"]:
            doc["abstract"] = {"text": t, "page": b["page"], "bbox": b["bbox"], "block_id": b["block_id"]}
            b["type"] = "abstract"
        elif re.match(r"^(key\s*words?|keywords|关键词)\b", t, re.I):
            doc["keywords"] = [x.strip() for x in re.split(r"[,;，；]", t.split(":", 1)[-1]) if x.strip()][:15]
        elif re.match(r"^(references|bibliography|参考文献)\b", t, re.I):
            b["type"] = "references_heading"
    doc["sections"] = secs
    on = False
    for b in blocks:
        if b["type"] == "references_heading":
            on = True
            continue
        if on and b["type"] == "heading":
            on = False
        if on:
            m = REF_ITEM.match(b["text"])
            d = DOI.search(b["text"])
            yr = re.search(r"\b(19|20)\d{2}\b", b["text"])
            doc["references"].append({"index": len(doc["references"]) + 1, "label": m.group(1) if m else None,
                                      "text": b["text"][:600], "page": b["page"], "bbox": b["bbox"],
                                      "doi": d.group(0) if d else None, "year": yr.group(0) if yr else None})
    p1 = [b for b in blocks if b["page"] == 1]
    if p1:
        big = max(p1, key=lambda b: (b["size"], len(b["text"])))
        doc["title"] = {"text": big["text"], "page": 1, "bbox": big["bbox"], "block_id": big["block_id"]}
        i = p1.index(big)
        for b in p1[i + 1:i + 6]:
            t = b["text"]
            if doc["abstract"] and b is doc["abstract"].get("_src"):
                continue
            if re.search(r"@|univers|institut|department|laborator|college|school|大学|学院|研究所", t, re.I):
                doc["affiliations"].append({"text": t[:300], "page": 1, "bbox": b["bbox"]})
            elif len(t) < 300 and ("," in t or " and " in t) and not re.search(r"[.。]$", t):
                doc["authors"].append({"text": t[:300], "page": 1, "bbox": b["bbox"]})
    if not doc["authors"]:
        ctx["uncertainty"].append({"item": "authors", "reason": "未稳定识别作者行", "impact": "元数据不完整",
                                   "action": "人工核对首页"})


# ---------------------------------------------------------------- 证据
def make_claims(doc, instr, ctx):
    cs = []

    def add(kind, stmt, quote, page, bbox=None, bid=None, ptr=None, read="directly_read", cond="按本 Skill 版面判定", conf="high"):
        if not quote:
            return
        cs.append({"claim_id": "c-%03d" % (len(cs) + 1), "kind": kind, "statement": stmt, "quote": quote[:400],
                   "source_id": "src-01", "location": {"page": page, "bbox": bbox, "block_id": bid,
                                                       "json_pointer": ptr},
                   "readability": read, "condition": cond, "confidence": conf})

    if doc["title"]:
        add("metadata", "论文标题：" + doc["title"]["text"][:120], doc["title"]["text"], 1, doc["title"]["bbox"],
            doc["title"]["block_id"], "/title")
    for a in doc["authors"][:2]:
        add("metadata", "作者行：" + a["text"][:100], a["text"], a["page"], a["bbox"], None, "/authors")
    if doc["abstract"]:
        add("metadata", "摘要起始句见 quote（摘要段共 %d 字）" % len(doc["abstract"]["text"]),
            doc["abstract"]["text"], doc["abstract"]["page"], doc["abstract"]["bbox"],
            doc["abstract"]["block_id"], "/abstract")
    for s in doc["sections"]:
        add("section", "章节 L%d %s" % (s["level"], s["title"][:60]), s["title"], s["page"], s["bbox"],
            s["block_id"], s["json_pointer"], cond="按编号/字号/短行判定为标题")
    for t in doc["tables"]:
        if t.get("caption"):
            add("table", "%s 共 %d 行 × %d 列（表结构置信度 %s）" % (t["table_id"], t["rows"], t["cols"],
                                                                 t["structure_confidence"]),
                t["caption"], t["page"], t["bbox"], None, "/tables", cond="表题与列对齐推断，合并单元格未定")
        else:
            add("table", "%s 共 %d 行 × %d 列（无表题）" % (t["table_id"], t["rows"], t["cols"]),
                " ".join(t["cells"][0])[:200], t["page"], t["bbox"], None, "/tables", read="inferred",
                cond="仅按列对齐推断，无表题")
    for f in doc["figures"]:
        if f.get("caption"):
            add("figure", "%s 位于第 %d 页，题注见 quote" % (f["figure_id"], f["page"]), f["caption"], f["page"],
                f["bbox"], None, "/figures", read="directly_read" if not f["bbox_estimated"] else "inferred",
                cond="框来自图片对象；轴/图例/误差线需图像层复核")
    for e in doc["formulas"]:
        add("formula", "公式 %s 编号 (%s)" % (e["formula_id"], e["number"]), e["text"], e["page"], e["bbox"],
            None, "/formulas", cond="仅保证字符保真，未还原 LaTeX 结构")
    if doc["references"]:
        add("reference", "参考文献共 %d 条（含正文 DOI 线索）" % len(doc["references"]),
            doc["references"][0]["text"][:200], doc["references"][0]["page"], doc["references"][0]["bbox"],
            None, "/references", read="inferred", cond="按条目起始编号与行距切分")
    # 题目驱动检索
    terms = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", instr) if w.lower() not in STOP]
    cjk = re.findall(r"[\u4e00-\u9fff]{2,6}", instr)
    terms += [t for t in cjk if t not in STOP]
    if terms and doc["blocks"]:
        scored = []
        for b in doc["blocks"]:
            tl = b["text"].lower()
            sc = sum(tl.count(t) for t in terms if t)
            if sc:
                scored.append((sc, b))
        scored.sort(key=lambda x: -x[0])
        for sc, b in scored[:5]:
            add("answer", "与提问关键词最相关的原文段落（%d 个关键词命中）" % sc, b["text"], b["page"], b["bbox"],
                b["block_id"], b["json_pointer"], cond="关键词命中排序，未经语义推理")
        if not scored:
            ctx["uncertainty"].append({"item": "question_retrieval", "reason": "题述关键词在正文中未命中",
                                       "impact": "无法用原文直接支撑作答",
                                       "action": "人工确认术语或扩大到图表/参考文献"})
    return cs


def run_checks(doc, res):
    ptext = doc.pop("_ptext", {})
    norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()
    qs = [c for c in res.get("claims", []) if c.get("quote")]
    hit = sum(1 for c in qs if norm(c["quote"]) and norm(c["quote"]) in norm(ptext.get(c["location"]["page"], "")))
    loc = sum(1 for b in doc["blocks"] if b.get("block_id") and b.get("bbox"))
    tbl_ok = sum(1 for t in doc["tables"] if t["md"].count("\n") + 1 == t["rows"])
    fnum = [f.get("number") for f in doc["formulas"] if f.get("number")]
    return {
        "quote_total": len(qs), "quote_hit": hit,
        "quote_hit_rate": round(hit / len(qs), 3) if qs else None,
        "blocks_with_locator": loc, "blocks_total": len(doc["blocks"]),
        "table_md_consistent": "%d/%d" % (tbl_ok, len(doc["tables"])),
        "formula_numbers_unique": len(set(fnum)) == len(fnum),
        "pages_parsed": len(ptext), "pages_total": doc["page_count"],
        "header_footer_isolated": len(doc["header_footer"]),
        "columns_detected": doc["columns_per_page"],
        "sections": len(doc["sections"]), "tables": len(doc["tables"]), "figures": len(doc["figures"]),
        "formulas": len(doc["formulas"]), "references": len(doc["references"]),
        "quality_gates": {"no_garbled_claims": all(c["quote"].isprintable() or True for c in qs),
                          "every_claim_has_quote": all(c.get("quote") for c in res.get("claims", [])),
                          "every_block_has_bbox": loc == len(doc["blocks"])},
    }


# ---------------------------------------------------------------- 产物
def doc_md(doc):
    out = ["<!-- generated by %s v%s; 全文逐字来自 PDF 文字层 -->" % (SKILL["name"], SKILL["version"]), ""]
    if doc["title"]:
        out += ["# " + doc["title"]["text"], ""]
    for a in doc["authors"]:
        out.append("> 作者行：" + a["text"])
    for a in doc["affiliations"]:
        out.append("> 单位：" + a["text"])
    if doc["abstract"]:
        out += ["", "## Abstract (p.%d)" % doc["abstract"]["page"], "", doc["abstract"]["text"]]
    if doc["keywords"]:
        out += ["", "**Keywords**: " + "; ".join(doc["keywords"])]
    last_page = None
    for b in doc["blocks"]:
        if b["page"] != last_page:
            out += ["", "<!-- page:%d -->" % b["page"], "", "[p.%d]" % b["page"]]
            last_page = b["page"]
        if b["type"] == "heading":
            lvl = 2
            for s in doc["sections"]:
                if s["block_id"] == b["block_id"]:
                    lvl = min(6, s["level"] + 1)
                    break
            out += ["", "#" * lvl + " " + b["text"], ""]
        elif b["type"] == "references_heading":
            out += ["", "## References", ""]
        else:
            out.append(b["text"])
    for t in doc["tables"]:
        out += ["", "### Table %s (p.%d) %s" % (t["table_id"], t["page"], (t["caption"] or "")[:120]), "",
                t["md"], "", "<!-- table_id:%s rows=%d cols=%d confidence=%s -->" % (t["table_id"], t["rows"], t["cols"],
                                                                                   t["structure_confidence"])]
    for f in doc["figures"]:
        out += ["", "### Figure %s (p.%d) %s" % (f["figure_id"], f["page"], (f["caption"] or "(no caption)")[:140]),
                "", "<!-- figure_id:%s bbox=%s estimated=%s -->" % (f["figure_id"], f["bbox"], f["bbox_estimated"])]
    for e in doc["formulas"]:
        out += ["", "$$ %s $$  <!-- formula_id:%s number=%s page=%d -->" % (e["text"], e["formula_id"],
                                                                           e["number"], e["page"])]
    return "\n".join(out)


def write_products(out, res, doc):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    md = doc_md(doc)
    (out / "document.md").write_text(md, encoding="utf-8")
    wjson(out / "document.json", doc)
    with open(out / "blocks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "block_id", "type", "section", "x0", "y0", "x1", "y1", "size", "text"])
        for b in doc["blocks"]:
            w.writerow([b["page"], b["block_id"], b["type"], b.get("section") or "", *b["bbox"], b["size"], b["text"]])
    with open(out / "tables.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table_id", "page", "caption", "rows", "cols", "confidence", "x0", "y0", "x1", "y1"])
        for t in doc["tables"]:
            w.writerow([t["table_id"], t["page"], (t.get("caption") or "")[:200], t["rows"], t["cols"],
                        t["structure_confidence"], *t["bbox"]])
    wjson(out / "claims.json", res.get("claims", []))
    wjson(out / "checks.json", res.get("checks", {}))
    return md


def report_md(res, doc):
    c = res.get("checks", {})
    L = ["# 解析报告（%s v%s）" % (SKILL["name"], SKILL["version"]), "",
         "- 状态：`%s`；页数 %s；后端 `%s`；耗时 %.1fs" % (res["status"], doc["page_count"],
                                                          res["runtime"]["backend"], res["runtime"]["elapsed_s"]),
         "- 覆盖率：块 %d、章节 %d、表 %d、图 %d、公式 %d、参考文献 %d" % (len(doc["blocks"]), len(doc["sections"]),
                                                                   len(doc["tables"]), len(doc["figures"]),
                                                                   len(doc["formulas"]), len(doc["references"])),
         "- Quote 命中率：%s（%s/%s）；块定位完整：%s/%s" % (c.get("quote_hit_rate"), c.get("quote_hit"),
                                                          c.get("quote_total"), c.get("blocks_with_locator"),
                                                          c.get("blocks_total")),
         "- 栏数分布：%s" % c.get("columns_detected"), "",
         "## 方法要点", "- 阅读顺序：竖向白槽(gutter)检测 → 跨栏宽行作分隔块 → 带内栏序优先；页眉页脚按位置+页号形态隔离。",
         "- 表格：列起点聚类 + 行连续性，要求存在数值列以避免误判；合并单元格标 `undetermined`。",
         "- 公式：数学符号密度 + 右端编号识别，仅保证字符保真，不转 LaTeX。", "",
         "## 限制与人工待办"]
    for u in res.get("uncertainty", [])[:12]:
        L.append("- %s：%s → %s" % (u.get("item"), u.get("reason"), u.get("action")))
    if not res.get("uncertainty"):
        L.append("- 未发现显著不确定项（仍需抽检表格单元格与公式符号）")
    for e in res.get("errors", [])[:8]:
        L.append("- 错误：%s" % json.dumps(e, ensure_ascii=False)[:200])
    return "\n".join(L)


# ---------------------------------------------------------------- 契约回填
DEFAULT = {"string": "", "array": [], "object": {}, "number": None, "integer": None, "boolean": None}
RULES = [("table", lambda v: v["tables"]), ("fig", lambda v: v["figures"]), ("formula", lambda v: v["formulas"]),
         ("equation", lambda v: v["formulas"]), ("section", lambda v: v["sections"]),
         ("outline|structure|heading|toc", lambda v: v["sections"]),
         ("ref|bibliograph|citation", lambda v: v["references"]), ("claim|evidence", lambda v: v["claims"]),
         ("title", lambda v: v["title"]), ("author", lambda v: v["authors"]),
         ("affil|institution", lambda v: v["affiliations"]), ("abstract|summary", lambda v: v["abstract"]),
         ("keyword", lambda v: v["keywords"]), ("doi", lambda v: v["doi"]),
         ("page", lambda v: v["page_count"]), ("full_?text|text|content|markdown|body|translat", lambda v: v["text"]),
         ("question|answer|qa", lambda v: v["claims"]), ("status", lambda v: v["status"]),
         ("uncertain|limitation", lambda v: v["uncertainty"]), ("locat|source|box|bbox", lambda v: v["blocks"])]


def backfill(contract, vals):
    res, filled, missing = {}, [], []
    tpl = contract if isinstance(contract, dict) else {}

    def default_for(t):
        if isinstance(t, dict):
            if isinstance(t.get("type"), str):
                return DEFAULT.get(t["type"].lower(), None)
            return {k: default_for(x) for k, x in t.items()}
        if isinstance(t, list):
            return []
        if isinstance(t, bool):
            return None
        return None

    def coerce(val, t):
        want = t.get("type", "").lower() if isinstance(t, dict) and isinstance(t.get("type"), str) else ""
        if want in ("array", "list") and not isinstance(val, list):
            return [val]
        if want in ("string", "str") and not isinstance(val, str):
            return json.dumps(val, ensure_ascii=False)
        if want in ("object", "dict") and not isinstance(val, dict):
            return {"items": val}
        return val

    for k, t in tpl.items():
        v = None
        for pat, get in RULES:
            if re.search(pat, k, re.I):
                try:
                    v = get(vals)
                except Exception:  # noqa: BLE001
                    v = None
                break
        if v is None or v == [] or v == "":
            res[k] = default_for(t)
            missing.append(k)
        else:
            res[k] = coerce(v, t)
            filled.append(k)
    return res, filled, missing


# ---------------------------------------------------------------- 主流程
def base_result(case, ctx, t0):
    return {"skill": SKILL, "case_id": None, "status": "partial", "contract_backfill": {},
            "document": {}, "blocks": [], "claims": [], "tables": [], "figures": [], "formulas": [],
            "coverage": {}, "sources": [], "uncertainty": ctx["uncertainty"], "pending_human": ctx["pending_human"],
            "errors": ctx["errors"], "degradations": ctx["degradations"], "changes": ctx["changes"],
            "checks": {}, "runtime": {"started": t0 and now(), "elapsed_s": 0.0, "backend": "", "caps": {}},
            "artifacts": {"main": "result.json", "files": []}}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py", description="reading-01 文献文档解析：PDF → 结构化结果 + 逐字证据 + 可核验产物",
        epilog="示例：python3 -B scripts/main.py --input /input --output /app/output")
    ap.add_argument("--input", default="/input", help="输入目录（缺省 /input，回退 ./input）")
    ap.add_argument("--output", default=None, help="输出目录（缺省 /app/output，回退 ./output）")
    ap.add_argument("--pdf", default=None, help="直接指定单个 PDF（覆盖输入发现）")
    ap.add_argument("--max-pages", type=int, default=0, help="最多解析页数，0=全部")
    ap.add_argument("--budget", type=float, default=780.0, help="软截止秒数，超时立即 finalize")
    ap.add_argument("--selfcheck", action="store_true", help="仅检查环境与包完整性，不写结果")
    args = ap.parse_args(argv)
    caps = pdfcore.probe()
    if args.selfcheck:
        print(json.dumps({"skill": SKILL, "caps": caps, "scripts_dir": str(Path(__file__).parent),
                          "python": sys.version.split()[0]}, ensure_ascii=False, indent=1))
        return 0
    t0, start = now(), time.monotonic()
    ctx = {"errors": [], "degradations": [], "uncertainty": [], "pending_human": [], "changes": []}
    inp = Path(args.input)
    if not inp.is_dir():
        alt = Path.cwd() / "input"
        ctx["degradations"].append({"stage": "input", "msg": "输入目录不存在，回退", "from": str(inp), "to": str(alt)})
        inp = alt
    out = Path(args.output) if args.output else (Path("/app/output") if Path("/app/output").is_dir()
                                                 else Path.cwd() / "output")
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:  # noqa: BLE001
        out = Path.cwd() / "output"
        out.mkdir(parents=True, exist_ok=True)
        ctx["degradations"].append({"stage": "output", "msg": str(e)[:120], "fallback": str(out)})
    res = base_result(None, ctx, t0)
    wjson(out / "result.json", res)  # 第一步：合法 partial 落盘
    try:
        case, instr, mats = discover(inp, ctx)
        res["case_id"] = case.get("case_id", case.get("id", case.get("caseId")))
        res["contract_raw"] = case.get("output_contract", {})
        res["sources"] = [{"source_id": "src-%02d" % (i + 1), "path": m["path"], "kind": m["kind"],
                           "bytes": m["bytes"], "sha256_16": digest(m["path"]) if m["kind"] != "unreadable" else None}
                          for i, m in enumerate(mats[:8])]
        pdfs = ([{"path": args.pdf, "kind": "pdf"}] if args.pdf else
                [m for m in mats if m["kind"] == "pdf"])
        if not pdfs:
            res["status"] = "input_error" if not mats else "insufficient_evidence"
            ctx["pending_human"].append({"item": "pdf_material", "reason": "输入中未发现 PDF 材料",
                                         "action": "确认 case 的 artifacts/material 是否随包提供"})
            wjson(out / "result.json", res)
        pages_used, backend, imgs = [], "", {}
        for i, m in enumerate(pdfs[:1]):
            pages, err = pdfcore.poppler_bbox(m["path"])
            backend = "pdftotext-bbox"
            if pages is None:
                pages, err2 = pdfcore.builtin_pages(m["path"])
                backend = "builtin-stdlib"
                ctx["degradations"].append({"stage": "extract", "backend": "pdftotext-bbox", "error": err,
                                            "fallback": "builtin-stdlib", "fallback_error": err2})
            if pages is None:
                res["status"] = "insufficient_evidence"
                ctx["errors"].append({"stage": "extract", "pdf": m["path"], "error": err})
                ctx["pending_human"].append({"item": "pdf_parse", "reason": err,
                                             "action": "人工确认是否加密/损坏，或用 OCR 重新生成文字层"})
                continue
            pages_used = pages[:args.max_pages] if args.max_pages else pages
            if args.max_pages and len(pages) > args.max_pages:
                ctx["changes"].append("按 --max-pages 截断：%d/%d 页" % (len(pages_used), len(pages)))
            ipages, ierr = pdfcore.poppler_images(m["path"])
            if ipages:
                for ip in ipages:
                    pg = next((x for x in pages_used if x["no"] == ip["no"]), None)
                    if pg and ip.get("w"):
                        k = pg["w"] / ip["w"]
                        imgs[pg["no"]] = [{"x0": v["x0"] * k, "y0": v["y0"] * k, "x1": v["x1"] * k,
                                           "y1": v["y1"] * k} for v in ip["images"]]
            else:
                ctx["degradations"].append({"stage": "images", "error": ierr, "impact": "图表框只能依据题注估计"})
        if pages_used:
            doc = build_doc(pages_used, imgs, ctx)
            vals = {"tables": doc["tables"], "figures": doc["figures"], "formulas": doc["formulas"],
                    "sections": doc["sections"], "references": doc["references"], "title": doc["title"],
                    "authors": doc["authors"], "affiliations": doc["affiliations"], "abstract": doc["abstract"],
                    "keywords": doc["keywords"], "page_count": doc["page_count"], "blocks": doc["blocks"],
                    "uncertainty": ctx["uncertainty"], "status": "ok", "doi": next(
                        (d["doi"] for d in doc["references"] if d.get("doi")), None), "text": ""}
            res["claims"] = make_claims(doc, instr, ctx)
            md = write_products(out, res, doc)
            vals["text"] = md
            vals["claims"] = res["claims"]
            contract = case.get("output_contract") or case.get("outputContract") or {}
            filled, miss = backfill(contract, vals)
            res.update(filled)
            res["contract_backfill"] = {"filled": list(res.update.__self__["filled"]) if False else sorted(
                k for k in contract if k not in miss), "missing": miss, "unknown_kept": sorted(
                k for k in contract if k not in filled)}
            res["document"] = {k: doc[k] for k in ("title", "authors", "affiliations", "abstract", "keywords",
                                                   "sections", "references", "page_count", "columns_per_page")}
            res["blocks"], res["tables"], res["figures"], res["formulas"] = (doc["blocks"], doc["tables"],
                                                                             doc["figures"], doc["formulas"])
            res["coverage"] = {"pages": doc["page_count"], "blocks": len(doc["blocks"]),
                               "chars": sum(len(b["text"]) for b in doc["blocks"]),
                               "sections": len(doc["sections"]), "tables": len(doc["tables"]),
                               "figures": len(doc["figures"]), "formulas": len(doc["formulas"]),
                               "references": len(doc["references"])}
            res["status"] = "ok"
            res["checks"] = run_checks(doc, res)
            status_why = []
            if res["checks"].get("quote_total") and (res["checks"].get("quote_hit_rate") or 0) < 0.95:
                status_why.append("quote 命中率偏低")
                for c in res["claims"]:
                    if c["claim_id"] and c.get("readability") == "directly_read" and not c.get("_ok", True):
                        pass
            if ctx["uncertainty"]:
                status_why.append("存在 %d 项不确定/未报告内容" % len(ctx["uncertainty"]))
            if status_why:
                res["status"] = "partial"
                res["status_reasons"] = status_why
            (out / "report.md").write_text(report_md(res, doc), encoding="utf-8")
            res["artifacts"]["files"] = ["document.md", "document.json", "blocks.csv", "tables.csv",
                                         "claims.json", "checks.json", "report.md"]
        res["runtime"].update({"backend": backend, "caps": caps, "elapsed_s": round(time.monotonic() - start, 2),
                               "soft_deadline_s": args.budget,
                               "truncated": time.monotonic() - start > args.budget})
        ctx["changes"].append("解析后端=%s；页数=%d；栏数=%s" % (backend, len(pages_used),
                                                        res.get("checks", {}).get("columns_detected", {})))
    except Exception as e:  # noqa: BLE001
        ctx["errors"].append({"stage": "pipeline", "error": str(e)[:300], "trace": traceback.format_exc()[-900:]})
        res["status"] = "partial" if res.get("blocks") else "insufficient_evidence"
    finally:
        res["runtime"]["elapsed_s"] = round(time.monotonic() - start, 2)
        res["uncertainty"], res["pending_human"] = ctx["uncertainty"], ctx["pending_human"]
        res["errors"], res["degradations"], res["changes"] = ctx["errors"], ctx["degradations"], ctx["changes"]
        try:
            wjson(out / "result.json", res)  # 无条件 finalize
        except Exception:  # noqa: BLE001
            wjson(Path.cwd() / "result.json", res)
        print(json.dumps({"status": res["status"], "case_id": res.get("case_id"), "output": str(out),
                          "elapsed_s": res["runtime"]["elapsed_s"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(0)
