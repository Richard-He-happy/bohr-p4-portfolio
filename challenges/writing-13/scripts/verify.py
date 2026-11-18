#!/usr/bin/env python3
"""Deterministic extraction and audit helpers for the grant-proposal skill.

Pure standard library. No network, no CWD assumptions.
Every public helper is defensive: on failure it returns an empty/degraded
result instead of raising, so the caller can always finish with exit code 0.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
import zipfile
import zlib
from pathlib import Path

# ---------------------------------------------------------------- constants
SEVEN = [
    {"id": "background", "title": "立项依据",
     "aliases": ["立项依据", "研究背景", "背景与意义", "立论依据"], "budget": 420},
    {"id": "question", "title": "科学问题",
     "aliases": ["科学问题", "关键科学问题", "拟解决的关键科学问题"], "budget": 260},
    {"id": "goals", "title": "研究目标",
     "aliases": ["研究目标", "研究目的", "总体目标"], "budget": 220},
    {"id": "content", "title": "研究内容",
     "aliases": ["研究内容", "研究任务"], "budget": 380},
    {"id": "innovation", "title": "创新点",
     "aliases": ["创新点", "特色与创新", "创新之处", "主要创新"], "budget": 260},
    {"id": "route", "title": "技术路线",
     "aliases": ["技术路线", "研究方案", "技术方案", "研究路线"], "budget": 320},
    {"id": "foundation", "title": "研究基础与可行性",
     "aliases": ["研究基础", "可行性", "工作基础", "研究基础与可行性"], "budget": 260},
]

BANNED = ["首次", "国际领先", "填补空白", "重大突破", "国内外首创", "世界首创",
          "尚无先例", "领跑全球", "开创性突破"]

SUPPORTED = {".txt": "text", ".md": "markdown", ".json": "json", ".csv": "csv",
             ".tsv": "csv", ".docx": "docx", ".pdf": "pdf"}
META_NAMES = {"task.md", "case.json", "output-contract.md", "public-manifest.json",
              "example-input.json", "skill.md", "guide.md"}
ZH_RANGE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
NUM_UNIT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|‰|mm|cm|MPa|kPa|GPa|℃|°C|K|N·m|N|kg|g|mg|μm|um|nm|"
    r"mL|ml|L|h|min|s|倍|次|个|组|层|周期|篇)")
MAX_UNITS_PER_SOURCE = 400
MAX_INDEX_CHARS = 160


def zh_count(text: str) -> int:
    return len(ZH_RANGE.findall(text or ""))


SENT_SPLIT = re.compile(r"(?<=[。；！？!?;])|(?<=\.)\s+(?=[A-Z(\[\"“])|\n")


def sentences(text: str):
    """Split CJK and Latin prose; never splits decimals such as 0.4 mm."""
    out = [s.strip() for s in SENT_SPLIT.split(text or "") if s and s.strip()]
    return out


def norm(text: str) -> str:
    """Aggressive normalisation used for quote location (not for display)."""
    t = unicodedata.normalize("NFKC", text or "")
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
                 ("—", "-"), ("–", "-"), ("−", "-")):
        t = t.replace(a, b)
    t = re.sub(r"[\s\u3000\u00a0]+", "", t)
    return re.sub(r"[，。、；：！？（）()\[\]【】,.;:!?\"'_…·<>《》]", "", t).lower()


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "ignore")


# ---------------------------------------------------------------- extractors
def line_blocks(text: str, max_chars: int = 1200):
    lines = text.splitlines()
    out, buf, start, cur = [], [], None, 0
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        if start is None:
            start = i
        buf.append(ln)
        cur += len(ln)
        if cur >= max_chars:
            out.append({"locator": "L%d-L%d" % (start, i), "text": "\n".join(buf)})
            buf, start, cur = [], None, 0
    if buf:
        out.append({"locator": "L%d-L%d" % (start, len(lines)), "text": "\n".join(buf)})
    return out[:MAX_UNITS_PER_SOURCE]


def json_units(obj, pointer="", out=None, depth=0):
    if out is None:
        out = []
    if len(out) >= MAX_UNITS_PER_SOURCE or depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            json_units(v, pointer + "/" + str(k).replace("~", "~0").replace("/", "~1"), out, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            json_units(v, pointer + "/" + str(i), out, depth + 1)
    elif isinstance(obj, str) and len(obj.strip()) > 40:
        out.append({"locator": "JSON-Pointer" + (pointer or "/"), "text": obj})
    return out


def csv_units(text: str):
    out = []
    rows = text.splitlines()
    for i in range(0, max(1, len(rows)), 20):
        chunk = "\n".join(rows[i:i + 20])
        if chunk.strip():
            out.append({"locator": "row-%d-%d" % (i + 1, min(i + 20, len(rows))), "text": chunk})
    return out[:MAX_UNITS_PER_SOURCE]


def docx_units(path: Path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return []
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    out = []
    for i, p in enumerate(paras, 1):
        txt = html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))).strip()
        if txt:
            out.append({"locator": "para-%d" % i, "text": txt})
    return out[:MAX_UNITS_PER_SOURCE]


def _pdf_stream_text(data: bytes) -> str:
    parts = []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)", data):
        s = m.group(0)[1:-1]
        s = re.sub(rb"\\([nrtbf()\\])", lambda x: {b"n": b"\n", b"r": b"", b"t": b" ",
                                                    b"b": b"", b"f": b""}.get(x.group(1), x.group(1)), s)
        s = re.sub(rb"\\([0-7]{1,3})", lambda x: bytes([int(x.group(1), 8) & 0xFF]), s)
        parts.append(decode(s))
    raw = " ".join(parts)
    return re.sub(r"[ \t]{2,}", " ", raw).strip()


def pdf_units(path: Path):
    try:
        raw = path.read_bytes()
    except Exception:
        return []
    out, idx = [], 0
    for m in re.finditer(rb"stream\r?\n", raw):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        blob = raw[start:end]
        try:
            data = zlib.decompress(blob)
        except Exception:
            data = blob
        if b"BT" not in data and b"Tj" not in data and b"TJ" not in data:
            continue
        txt = _pdf_stream_text(data)
        if len(txt) > 60:
            out.append({"locator": "pdf-stream-%d" % idx, "text": txt})
            idx += 1
        if len(out) >= MAX_UNITS_PER_SOURCE:
            break
    return out


def source_units(path: Path):
    kind = SUPPORTED.get(path.suffix.lower())
    if kind in ("text", "markdown"):
        return line_blocks(decode(path.read_bytes()))
    if kind == "json":
        try:
            return json_units(json.loads(decode(path.read_bytes())))
        except Exception:
            return line_blocks(decode(path.read_bytes()))
    if kind == "csv":
        return csv_units(decode(path.read_bytes()))
    if kind == "docx":
        return docx_units(path)
    if kind == "pdf":
        return pdf_units(path)
    return []


def build_sources(input_dir: Path, limit_files: int = 40):
    """Return [{source_id,name,kind,role,units:[{locator,text}]}]."""
    sources = []
    if not input_dir or not Path(input_dir).exists():
        return sources
    files = []
    for p in sorted(Path(input_dir).rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in SUPPORTED:
            continue
        files.append(p)
    for p in files[:limit_files]:
        role = "meta" if p.name.lower() in META_NAMES else "source"
        units = source_units(p)
        sources.append({
            "source_id": "S%02d" % (len(sources) + 1),
            "name": p.name,
            "path": str(p),
            "kind": SUPPORTED.get(p.suffix.lower(), "binary"),
            "role": role,
            "units": units,
        })
    return sources


# ---------------------------------------------------------------- quoting
def build_quote_index(sources):
    idx = []
    for s in sources:
        if s.get("role") == "meta":
            continue
        for u in s.get("units", []):
            nt = norm(u.get("text", ""))
            if len(nt) >= 30:
                idx.append((s["source_id"], s["name"], u["locator"], nt, u.get("text", "")))
    return idx


def find_quote(index, quote: str):
    """Return dict(match, source_id, locator, ratio)."""
    nq = norm(quote)
    if not nq:
        return {"match": "empty", "source_id": None, "locator": None, "ratio": 0.0}
    if not index:
        return {"match": "no_source", "source_id": None, "locator": None, "ratio": 0.0}
    for sid, name, loc, nt, _ in index:
        if nq in nt:
            return {"match": "normalized", "source_id": sid, "locator": loc,
                    "source": name, "ratio": 1.0}
    if len(nq) >= 24:
        head, tail = nq[:16], nq[-16:]
        for sid, name, loc, nt, _ in index:
            if head in nt and tail in nt:
                return {"match": "partial", "source_id": sid, "locator": loc,
                        "source": name, "ratio": 0.9}
    return {"match": "unmatched", "source_id": None, "locator": None, "ratio": 0.0}


def fact_candidates(sources, limit: int = 40):
    """Numeric / unit-bearing sentences, verbatim, with locator."""
    out, seen = [], set()
    for s in sources:
        if s.get("role") == "meta":
            continue
        for u in s.get("units", []):
            for sent in sentences(u.get("text", "")):
                m = NUM_UNIT.search(sent)
                if not m:
                    continue
                q = sent.strip()
                if not (8 <= len(q) <= 260):
                    continue
                key = norm(q)[:60]
                if key in seen:
                    continue
                seen.add(key)
                out.append({"fact_id": "F%02d" % (len(out) + 1), "value": m.group(0).strip(),
                            "quote": q, "source_id": s["source_id"],
                            "source": s["name"], "locator": u["locator"]})
                if len(out) >= limit:
                    return out
    return out


# ---------------------------------------------------------------- audit
def _headings(md: str):
    out = []
    for m in re.finditer(r"^[ \t]{0,3}(#{1,6})[ \t]*(.+?)[ \t]*$", md, re.M):
        out.append((m.start(), m.end(), len(m.group(1)), m.group(2).strip()))
    return out


def section_spans(md: str):
    heads = _headings(md)
    res = {}
    for meta in SEVEN:
        hit = None
        for pos, endpos, lvl, title in heads:
            if any(a in title for a in meta["aliases"]):
                hit = (pos, endpos, lvl)
                break
        if not hit:
            res[meta["id"]] = {"title": meta["title"], "found": False, "heading": None,
                               "chars": 0, "body": ""}
            continue
        pos, endpos, lvl = hit
        stop = len(md)
        for p2, e2, l2, _ in heads:
            if p2 > pos and l2 <= lvl:
                stop = p2
                break
        body = md[endpos:stop]
        res[meta["id"]] = {"title": meta["title"], "found": True, "heading": md[pos:endpos].strip(),
                           "chars": zh_count(re.sub(r"^[ \t]*[-*>].*$", "", body, flags=re.M)),
                           "body": body}
    return res


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def check_output(out: Path, plan: dict | None = None):
    """Deterministic audit of everything in `out`. Never raises."""
    plan = plan or {}
    rep = {"issues": [], "metrics": {}, "notes": []}

    def issue(level, code, msg):
        rep["issues"].append({"level": level, "code": code, "message": msg})

    prop = Path(out) / "proposal.md"
    md = ""
    if prop.exists():
        md = decode(prop.read_bytes())
    else:
        issue("critical", "proposal_missing", "proposal.md 不存在")

    spans = section_spans(md)
    found = [k for k, v in spans.items() if v["found"]]
    thin = [k for k, v in spans.items() if v["found"] and v["chars"] < 60]
    for k in spans:
        if not spans[k]["found"]:
            issue("critical", "section_missing", "缺少要素章节：%s" % spans[k]["title"])
    for k in thin:
        issue("major", "section_thin", "章节正文过短（<%d 汉字）：%s" % (60, spans[k]["title"]))

    total = sum(v["chars"] for v in spans.values()) if found else zh_count(md)
    lo = int(plan.get("chars_min") or plan.get("lo") or 1600)
    hi = int(plan.get("chars_max") or plan.get("hi") or 2600)
    if total < lo:
        issue("major", "chars_below", "正文字数 %d < 下限 %d" % (total, lo))
    elif total > hi:
        issue("minor", "chars_above", "正文字数 %d > 上限 %d" % (total, hi))

    goals = sorted(set(re.findall(r"G\s*([1-9])", md)))
    goal_cnt = len([g for g in goals if int(g) <= 5])
    if goal_cnt != 3:
        issue("major", "goals_count", "检出目标数 %d（要求 3：G1/G2/G3）" % goal_cnt)

    month_cap = int(plan.get("planning_months") or plan.get("months") or 12)
    months = []
    for m in re.finditer(r"(?:第\s*(\d{1,2})\s*个?月|M\s*(\d{1,2})(?!\d)|(\d{1,2})\s*个月)", md):
        v = next((int(g) for g in m.groups() if g), 0)
        if 0 < v <= 60:
            months.append(v)
    max_month = max(months) if months else 0
    if max_month > month_cap:
        issue("major", "months_over", "计划时间出现 %d 月 > 上限 %d" % (max_month, month_cap))

    unit_cap = int(plan.get("planning_unit_cap") or plan.get("cap") or 100)
    pu = _load(Path(out) / "planning_units.json", None)
    pu_total = None
    if not pu:
        issue("major", "planning_units_missing", "planning_units.json 缺失或不可解析")
    else:
        items = pu.get("items") or []
        nums = [it.get("units") for it in items if isinstance(it, dict)]
        if items and all(isinstance(n, (int, float)) for n in nums):
            pu_total = sum(nums)
            if pu.get("total") is not None and abs(float(pu.get("total")) - pu_total) > 1e-6:
                issue("major", "units_total_mismatch",
                      "分项之和 %.1f 与 total %s 不一致" % (pu_total, pu.get("total")))
            if pu_total > unit_cap:
                issue("major", "units_over_cap", "规划单位合计 %.1f > 上限 %d" % (pu_total, unit_cap))
        else:
            issue("major", "units_unfilled", "planning_units.json 存在未填分项")
        if not (pu.get("unit_meaning") or "").strip():
            issue("minor", "unit_meaning_missing", "planning_units.json 未声明规划单位含义")

    if re.search(r"\d+\s*万?元|￥|RMB|人民币", md):
        issue("critical", "currency_leak", "正文出现货币/经费表述（规划单位非货币）")

    risks = _load(Path(out) / "risks.json", None)
    rtxt = ""
    rp = Path(out) / "risks.md"
    if rp.exists():
        rtxt = decode(rp.read_bytes())
    risk_ids = sorted(set(re.findall(r"R\s?([1-9])", rtxt + (json.dumps(risks, ensure_ascii=False) if risks else ""))))
    risk_cnt = len([r for r in risk_ids if int(r) <= 9])
    if risk_cnt < 3:
        issue("major", "risks_count", "风险数 %d < 3" % risk_cnt)
    for kw in ("触发", "备选"):
        if kw not in rtxt and kw not in json.dumps(risks or {}, ensure_ascii=False):
            issue("minor", "risk_field_missing", "风险未含“%s”字段" % kw)

    ph = _load(Path(out) / "pending_human.json", None)
    ph = ph if isinstance(ph, list) else (ph or {}).get("items") if isinstance(ph, dict) else None
    ph = ph or []
    if len(ph) < 2:
        issue("major", "pending_human_count", "人工确认项 %d < 2" % len(ph))
    phtext = json.dumps(ph, ensure_ascii=False)
    if not re.search(r"申请人", phtext):
        issue("major", "pending_human_applicant", "人工确认项未覆盖“真实申请人证据”")
    if not re.search(r"资助|指南|funder|notice", phtext):
        issue("major", "pending_human_funder", "人工确认项未覆盖“真实资助要求”")

    gm = Path(out) / "goal_matrix.md"
    gm_rows = 0
    if gm.exists():
        gtxt = decode(gm.read_bytes())
        gm_rows = len([ln for ln in gtxt.splitlines()
                       if ln.strip().startswith("|") and re.search(r"G\s?[1-3]", ln)])
        if gm_rows < 3:
            issue("major", "matrix_rows", "目标矩阵可 join 行数 %d < 3" % gm_rows)
    else:
        issue("major", "matrix_missing", "goal_matrix.md 缺失")

    em = _load(Path(out) / "evidence_map.json", None)
    em = em if isinstance(em, list) else (em or {}).get("items") if isinstance(em, dict) else []
    em = em or []

    hits = 0
    for b in BANNED:
        for sent in re.split(r"(?<=[。；！？\n])", md):
            if b in sent and not re.search(r"（[^）]{0,80}(来源|locator|evidence|S\d\d)[^）]{0,80}）|et al|等\（\d{4}", sent):
                issue("major", "banned_phrase", "无据修饰“%s”：%s" % (b, sent.strip()[:60]))
                hits += 1
                break

    attr_bad = []
    for m in re.finditer(r"(申请人|本课题组|我方|本人)([^。；\n]{0,24})(已完成|已实现|已发表|已建成|已掌握)", md):
        window = md[max(0, m.start() - 16):m.end()]
        if re.search(r"不能|不作|未|非|尚|待|不构成|外部作者", window):
            continue
        attr_bad.append(m.groups()[:1] + m.groups()[2:])
    for a in attr_bad:
        issue("minor", "attribution_risk", "疑似把既有成果写成申请人已完成：%s…%s" % a)
    has_ext = bool(re.search(r"外部作者|该文作者|原作者|Belter|Dollar", md))

    plan_marks = len(re.findall(r"拟|计划|将|预计", md))
    if plan_marks < 5:
        issue("minor", "plan_markers_few", "拟开展标记仅 %d 处" % plan_marks)

    rep["metrics"] = {
        "char_total": total, "char_range": [lo, hi],
        "sections_found": found, "sections_total": len(SEVEN),
        "section_chars": {k: v["chars"] for k, v in spans.items()},
        "goals_count": goal_cnt, "max_month": max_month, "month_cap": month_cap,
        "planning_units_total": pu_total, "unit_cap": unit_cap,
        "risks_count": risk_cnt, "pending_human_count": len(ph),
        "matrix_rows": gm_rows, "evidence_entries": len(em),
        "banned_unverified": hits, "plan_markers": plan_marks,
        "attribution_flagged": len(attr_bad), "external_author_marked": has_ext,
    }
    crit = [i for i in rep["issues"] if i["level"] == "critical"]
    major = [i for i in rep["issues"] if i["level"] == "major"]
    rep["counts"] = {"critical": len(crit), "major": len(major),
                     "minor": len(rep["issues"]) - len(crit) - len(major)}
    rep["status"] = "ok" if not crit and not major else "partial"
    return rep


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Audit a grant-proposal output directory.")
    ap.add_argument("--output", default="", help="directory holding proposal.md etc.")
    ap.add_argument("--input", default="", help="case input directory (optional)")
    args = ap.parse_args(argv)
    out = Path(args.output or ".").resolve()
    print(json.dumps(check_output(out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
