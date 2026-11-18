#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py - 抽取/引用解析/组稿模板 + 确定性核对（intro-related-work-writer v1.0.0）
抽取: 文本直读, docx/xlsx 走 zipfile+XML, pdf 走 stdlib 流解码(启发式)
用法: python3 -B verify.py --result out/result.json --sources out/sources_index.json
纯标准库, 不联网, 不依赖 CWD, 退出码恒 0。
"""
import argparse
import json
import re
import sys
import zipfile
import zlib
from pathlib import Path

TEXT_EXT = {".md", ".markdown", ".txt", ".tex", ".csv", ".tsv", ".json", ".html", ".htm", ".yaml", ".yml", ".rst"}
_WS = re.compile(r"\s+")
SPLIT = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+")
CITE = re.compile(r"\[(\d+|[A-Za-z][\w\-]*)\]")
REFLINE = re.compile(r"^\s*(\[\d+\]|\d+[.)])\s+\S")
RK = {"authors", "author", "year", "title", "venue", "journal", "doi", "abstract", "key"}
RL = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+(\S.{24,})$")
YR = re.compile(r"\b(19|20)\d{2}\b")
NUM = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|mg|kg|µg|ug|ng|mL|L|µL|uL|mM|µM|nM|mol|min|ms|h|s|°C|K|nm|µm|um|"
                 r"mm|cm|km|MPa|GPa|kPa|Pa|eV|keV|MeV|GeV|Hz|kHz|MHz|GB|MB|TB|wt%|at%|ppm|bp|倍|小时)|"
                 r"\d+\.\d+")


def norm(s):
    """空白归一化：只折叠空白，不改字符。"""
    return _WS.sub(" ", s or "").strip()


def sents(t):
    """句子切分，仅保留 ≥25 字符的句子。"""
    return [x.strip() for x in SPLIT.split(t or "") if len(x.strip()) >= 25]


def numbers(t):
    return [m.group(0) for m in NUM.finditer(t or "")]


def pdf_text(p):
    raw = Path(p).read_bytes()
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        data = m.group(1)
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        if b"Tj" not in data and b"TJ" not in data:
            continue
        for tm in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]{4,}>", data):
            s = tm.group(0)
            if s.startswith(b"("):
                body = re.sub(rb"\\([nrt()\\])", lambda g: {b"n": b" ", b"r": b" ", b"t": b" ", b"(": b"(",
                                                             b")": b")", b"\\": b"\\"}[g.group(1)], s[1:-1])
                out.append(body.decode("latin-1", "replace"))
            else:
                try:
                    out.append(bytes.fromhex(re.sub(rb"\s", b"", s[1:-1]).decode()).decode("utf-16-be", "replace"))
                except Exception:
                    pass
    return re.sub(r"(?<=[.!?。])(?=[A-Z\u4e00-\u9fff])", " ", norm(" ".join(out)))


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t").replace("<w:br/>", "\n")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", "", xml))


def xlsx_text(p):
    out = []
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n.startswith("xl/") and n.endswith(".xml"):
                out += re.findall(r"<t[^>]*>([^<]{1,400})</t>", z.read(n).decode("utf-8", "replace"))
    return "\n".join(out)


def read_any(p, errs=None):
    """返回 (text, kind)；失败只记录。"""
    p = Path(p)
    try:
        if p.suffix.lower() == ".docx":
            return docx_text(p), "docx"
        if p.suffix.lower() == ".xlsx":
            return xlsx_text(p), "xlsx"
        if p.suffix.lower() == ".pdf":
            return pdf_text(p), "pdf"
        if p.suffix.lower() in TEXT_EXT or p.suffix == "":
            return p.read_text(encoding="utf-8", errors="replace"), "text"
    except Exception as exc:
        if errs is not None:
            errs.append({"stage": "extract", "file": str(p), "error": f"{type(exc).__name__}: {exc}"})
    return "", "unsupported"


def chunkify(sid, kind, text):
    """pdf 按句给 c<a>-<b>；其余按段给 L<a>-<b>。"""
    if kind == "pdf":
        out, pos = [], 0
        for s in sents(text):
            i = text.find(s, pos)
            i = pos if i < 0 else i
            out.append({"source_id": sid, "locator": f"c{i}-{i + len(s)}", "text": s})
            pos = i + len(s)
        return out
    out, buf, start, lines = [], [], None, (text or "").splitlines()
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("#") or set(s) <= set("-=*_ "):
            s = ""
        if not s:
            if buf:
                out.append({"source_id": sid, "locator": f"L{start}-{i - 1}", "text": " ".join(buf)})
                buf, start = [], None
            continue
        if start is None:
            start = i
        buf.append(s)
    if buf:
        out.append({"source_id": sid, "locator": f"L{start}-{len(lines)}", "text": " ".join(buf)})
    return out


def walk_refs(o, path="$", d=0, acc=None):
    """递归找文献记录 dict（≥3 个文献键且含 title）。"""
    acc = [] if acc is None else acc
    if d > 12:
        return acc
    if isinstance(o, dict):
        ks = {str(k).lower() for k in o}
        if len(ks & RK) >= 3 and "title" in ks:
            acc.append((path, o))
            return acc
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                walk_refs(v, f"{path}.{k}", d + 1, acc)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk_refs(v, f"{path}[{i}]", d + 1, acc)
    return acc


def to_ref(d, sid, loc):
    a = d.get("authors") or d.get("author") or ""
    if isinstance(a, list):
        a = "; ".join(str(x) for x in a)
    elif isinstance(a, dict):
        a = "; ".join(str(v) for v in a.values())
    r = {"key": str(d.get("key") or d.get("id") or ""), "authors": norm(str(a)),
         "year": norm(str(d.get("year") or d.get("date") or ""))[:4],
         "title": norm(str(d.get("title") or "")),
         "venue": norm(str(d.get("venue") or d.get("journal") or "")),
         "doi": norm(str(d.get("doi") or "")), "abstract": norm(str(d.get("abstract") or "")),
         "source_id": sid, "locator": loc, "origin": "structured"}
    r["metadata_status"] = ("complete" if r["authors"] and r["year"] and r["title"]
                            else "partial" if r["title"] else "missing")
    return r


def refs_from_text(chunks, used):
    """解析 "[1] Author. Title. Venue, Year. Note"；以含年份片段为锚点切作者/标题/出处。"""
    out = []
    for ch in chunks:
        m = RL.match(ch["text"])
        if not m or not YR.search(ch["text"]) or (ch["source_id"], ch["locator"]) in used:
            continue
        parts = [x.strip() for x in re.split(r"\.\s+", m.group(3)) if x.strip()]
        yi = next((j for j in range(len(parts) - 1, -1, -1) if YR.search(parts[j])), None)
        if yi is None:
            continue
        # 把被缩写句点切碎的出处片段（单字母，如 "J" + "Sched., 2021"）并回年份片段
        while yi > 0 and re.fullmatch(r"[A-Za-z]\.?", parts[yi - 1]):
            parts[yi - 1] = parts[yi - 1] + ". " + parts.pop(yi)
            yi -= 1
        yr = YR.search(parts[yi]).group(0)
        authors = norm(". ".join(parts[:max(0, yi - 1)]))[:140] if yi > 0 else ""
        title = norm(parts[yi - 1])[:220] if yi > 0 else ""
        venue = norm(re.sub(r",?\s*" + re.escape(yr) + r"\s*$", "", parts[yi])).strip(" ,;.")[:120]
        abstract = norm(" ".join(parts[yi + 1:]) or "")[:600]
        r = {"key": m.group(1) or m.group(2) or "", "authors": authors, "year": yr,
             "title": title, "venue": venue, "doi": "", "abstract": abstract,
             "source_id": ch["source_id"], "locator": ch["locator"], "origin": "text_list"}
        r["metadata_status"] = ("complete" if r["authors"] and r["year"] and r["title"] and r["venue"]
                                else "partial" if r["title"] else "missing")
        out.append(r)
        used.add((ch["source_id"], ch["locator"]))
    return out


ROUTES = [
    ("transformer/LLM", ("transformer", "attention", "large language model", "llm", "pretrain", "foundation model")),
    ("deep learning", ("neural network", "deep learning", "convolutional", "cnn", "lstm", "recurrent", "image prior")),
    ("graph-based", ("graph neural", "gnn", "message passing", "knowledge graph", "molecular graph")),
    ("generative", ("diffusion", "generative adversarial", "gan", "variational autoencoder")),
    ("reinforcement learning", ("reinforcement learning", "policy gradient", "reward")),
    ("rule/heuristic", ("rule-based", "heuristic", "greedy", "priority queue", "queueing", "scheduling policy")),
    ("classical ML", ("support vector", "svm", "random forest", "gradient boosting", "feature engineering")),
    ("statistical modelling", ("bayesian", "regression", "likelihood", "statistical model")),
    ("mechanistic/experimental", ("mechanism", "kinetic", "in vitro", "in vivo", "assay", "spectroscop", "passivation", "ligand")),
    ("simulation/numerical", ("simulation", "density functional", "dft", "finite element", "molecular dynamics")),
    ("physics-based reconstruction", ("total-variation", "computed tomography", "forward model", "inverse problem")),
    ("benchmark/dataset", ("benchmark", "dataset", "corpus", "evaluation protocol", "annotation")),
    ("multimodal", ("multimodal", "cross-modal", "image-text", "vision-language")),
    ("review/survey", ("survey", "systematic review", "meta-analysis", "tutorial")),
]
LC = ("however", "but ", "limitation", "limited", "cannot", "can not", "fail", "suffer", "remains", "lack",
      "restricted", "struggle", "slow", "costly", "expensive", "难以", "无法", "仅", "局限", "尚未", "缺乏", "不足", "受限于")
OC = ("challenge", "bottleneck", "difficult", "problem", "issue", "existing", "current", "prior",
      "state-of-the-art", "本文", "我们", "现有", "瓶颈", "挑战", "难以")
KC = ("we propose", "we present", "we introduce", "we develop", "we show", "we report", "results show",
      "our method", "we evaluate", "本文提出", "我们提出", "我们设计", "结果表明", "实验在")
DC = ("dataset", "benchmark", "evaluat", "accuracy", "f1", "auc", "rmse", "mae", "数据集", "指标", "评价")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _hit(kw, text):
    """短英文关键词按词边界匹配（避免 "gan" 命中 "ligand"），中文与长词用子串。"""
    if kw.isascii() and len(kw) <= 4:
        return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None
    return kw in text


def route(title, body):
    """路线词表打分：标题命中权重 3，摘要/文本权重 1；无命中返回 ("",0)。"""
    t, b = (title or "").lower(), (body or "").lower()
    best, sc = "", 0
    for lab, kws in ROUTES:
        s = sum(3 if _hit(k, t) else 0 for k in kws) + sum(1 if _hit(k, b) else 0 for k in kws)
        if s > sc:
            best, sc = lab, s
    return best, sc


def pick(chunks, cues, n):
    """按线索取 n 条代表性原文句（不足则用段首句补齐），句句可回溯。"""
    out, seen = [], set()
    for ch in chunks:
        for s in [ch["text"]] + sents(ch["text"]):
            if len(s) >= 25 and s.lower()[:60] not in seen and any(k in s.lower() for k in cues):
                seen.add(s.lower()[:60])
                out.append({"text": s, "source_id": ch["source_id"], "locator": ch["locator"]})
                break
        if len(out) >= n:
            return out
    for ch in chunks:
        if len(out) >= n:
            break
        if ch["text"].lower()[:60] in seen or len(ch["text"]) < 40:
            continue
        seen.add(ch["text"].lower()[:60])
        ss = sents(ch["text"])
        out.append({"text": ss[0] if ss else ch["text"], "source_id": ch["source_id"], "locator": ch["locator"]})
    return out[:n]


def claim_of(r):
    """取该文献的主张句：优先非局限句，其次任一句，最后退到标题。"""
    ss = sents(r.get("abstract", ""))
    good = [x for x in ss if not any(c in x.lower() for c in LC)]
    cand = good or ([r["title"]] if r.get("title") else ss)
    return cand[0] if cand else ""


def lim(r):
    """抽取作者自陈局限句（逐字，不改写）。"""
    return [s for s in sents(r.get("abstract", "")) if any(c in s.lower() for c in LC)]


def dim(r):
    """抽取数据与评价维度句（与首句重复时返回空，避免同句充当两个维度）。"""
    ss = sents(r.get("abstract", ""))
    for s in (ss[1:] if len(ss) > 1 else []):
        if any(c in s.lower() for c in DC):
            return s
    return ""


def compose(L, anchors, order, groups, gaps, contribs, refs, num, cite):
    """组稿：四段式 + References；每句带 source_id#locator 与待核实注释。"""
    m = [f"# {L['t']}", "", L["n"], "", f"## 1. {L['h'][0]}", ""]
    for i, a in enumerate(anchors):
        m += [f"{L['bg'][min(i, 2)]}{a['text']}  [{a['source_id']}#{a['locator']}]", ""]
    if not anchors:
        m += [f"<!-- {L['td']}: 材料未提供可引用的背景陈述 -->", ""]
    m += [f"## 2. {L['h'][1]}", ""]
    for gi, g in enumerate(order, 1):
        ms = groups[g]
        m += [f"### 2.{gi} {g} ({len(ms)}; {''.join(cite(r['id']) for r in ms)})", ""]
        for r in ms:
            cl = claim_of(r)
            cd, lm = dim(r), lim(r)
            tail = ([f"{L['cd']}: {cd}"] if cd and cd != cl else []) + ([f"{L['lm']}: {lm[0]}"] if lm and lm[0] != cl else [])
            line = f"- {cl} {cite(r['id'])}" + ("  — " + "; ".join(tail) if tail else "")
            if not r["abstract"]:
                line += f"  <!-- {L['td']}: 无摘要，转述仅达标题层面 -->"
            m += [line, f"  [{r['source_id']}#{r['locator']}]"]
        m += ["", f"<!-- {L['rw']} -->", ""]
    m += [f"## 3. {L['h'][2]}", ""]
    if gaps:
        for gt in ("shared_limitation", "uncovered_scenario", "conflict"):
            sub = [g for g in gaps if g["gap_type"] == gt]
            if not sub:
                continue
            m += [f"**{gt}**", ""]
            for g in sub:
                m += ["- " + L["gp"].format(route=g["route"], q=g["basis_quote"],
                                            k=", ".join(cite(x)[1:-1] for x in g["supports"])),
                      f"  [{g['source_id']}#{g['locator']}]"]
            m.append("")
    else:
        m += ["- " + L["gn"], ""]
    m += [f"## 4. {L['h'][3]}", ""]
    for c in contribs:
        m.append(f"- {c['text']}  [{c['source_id']}#{c['locator']}]")
    if not contribs:
        m += [f"- <!-- {L['td']}: 材料未给出可对账的方法/结果陈述 -->"]
    m += ["", f"## {L['h'][4]}", "", L["rf"], ""]
    for r in refs:
        b = [f"[{num[r['id']]}]", r["authors"] or f"[{L['td']}: authors]", f"({r['year'] or L['td']})",
             r["title"] or f"[{L['td']}: title]", (r["venue"] + ".") if r["venue"] else f"[{L['td']}: venue]"]
        if r["doi"]:
            b.append("doi:" + r["doi"])
        m.append(" ".join(b))
    return "\n".join(m) + "\n"


def find_quote(quote, text):
    """归一化后逐字包含判定（<4 字符视为未命中）。"""
    q, t = norm(quote), norm(text)
    return len(q) >= 4 and q in t


def verify_evidence(evidence_map, sources):
    rows = []
    for ev in evidence_map or []:
        sid = ev.get("source_id")
        ok = find_quote(ev.get("quote", ""), sources.get(sid, "")) if sid in sources else False
        rows.append({"claim_id": ev.get("claim_id"), "source_id": sid, "locator": ev.get("locator"),
                     "quote_verified": bool(ok),
                     "reason": "hit" if ok else ("unknown_source" if sid not in sources else "quote_not_found")})
    rate = (sum(1 for r in rows if r["quote_verified"]) / len(rows)) if rows else 0.0
    return rows, round(rate, 4)


def check_contract(result, contract):
    names = []
    if isinstance(contract, dict):
        names = [str(k) for k in contract]
    elif isinstance(contract, list):
        for it in contract:
            if isinstance(it, str):
                names.append(it)
            elif isinstance(it, dict):
                names += [it[k] for k in ("name", "field", "key", "id") if isinstance(it.get(k), str)][:1]
    return [n for n in names if n not in (result or {})]


def count_metrics(manuscript):
    text = manuscript or ""
    heads = [l.lower() for l in text.splitlines() if l.startswith("#")]
    sec = {"background": any(("background" in h or "背景" in h) for h in heads),
           "related_work": any(("related work" in h or "相关工作" in h) for h in heads),
           "research_gap": any(("gap" in h or "空白" in h or "不足" in h) for h in heads),
           "contributions": any(("contribution" in h or "贡献" in h) for h in heads)}
    return {"chars": len(text), "words": len(text.split()),
            "cjk_chars": len(re.findall(r"[\u4e00-\u9fff]", text)),
            "citation_markers": len(CITE.findall(text)),
            "unique_citation_markers": len(set(CITE.findall(text))),
            "reference_lines": sum(1 for l in text.splitlines() if REFLINE.match(l)),
            "sections": sec, "sections_complete": all(sec.values())}


def metadata_stats(citations):
    t = len(citations or [])
    c = sum(1 for x in citations or [] if x.get("metadata_status") == "complete")
    p = sum(1 for x in citations or [] if x.get("metadata_status") == "partial")
    return {"total": t, "complete": c, "partial": p, "missing": t - c - p}


def run(result_path, sources_path="", quiet=False):
    res = json.loads(Path(result_path).read_text(encoding="utf-8"))
    sources = {}
    if sources_path and Path(sources_path).exists():
        raw = json.loads(Path(sources_path).read_text(encoding="utf-8"))
        sources = {k: (v.get("text", "") if isinstance(v, dict) else str(v)) for k, v in raw.items()}
    rows, rate = verify_evidence(res.get("evidence_map"), sources)
    missing = check_contract(res, res.get("output_contract") or {})
    rep = {"status": res.get("status"), "case_id": res.get("case_id"),
           "evidence_checked": len(rows), "quote_verified_rate": rate,
           "quote_failures": [r for r in rows if not r["quote_verified"]][:20],
           "contract_missing_fields": missing, "contract_ok": not missing,
           "counts": count_metrics(res.get("manuscript_text", "")),
           "citation_metadata": metadata_stats(res.get("citations")),
           "gap_items": len(res.get("gap_derivation") or []),
           "gap_without_support": [g.get("gap_id") for g in res.get("gap_derivation") or [] if not g.get("supports")],
           "contributions": len(res.get("contribution_alignment") or []),
           "contributions_unaligned": [c.get("contribution_id") for c in res.get("contribution_alignment") or []
                                       if not c.get("aligned")],
           "pending_human": len(res.get("pending_human") or []),
           "verdict": "pass" if (rate >= 0.8 and not missing) else "needs_attention"}
    if not quiet:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="核对 result.json：quote 命中、契约、计数、元数据",
                                epilog="退出码恒 0。")
    ap.add_argument("--result", default="result.json", help="result.json 路径")
    ap.add_argument("--sources", default="", help="sources_index.json 路径")
    ap.add_argument("--quiet", action="store_true", help="不打印")
    a = ap.parse_args(argv)
    try:
        run(a.result, a.sources, a.quiet)
    except Exception as exc:
        print(json.dumps({"verdict": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
