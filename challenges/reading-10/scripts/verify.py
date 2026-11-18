#!/usr/bin/env python3
"""verify.py - 确定性工具库：材料抽取、证据 quote 匹配、容差比较、契约回填。

  python3 -B verify.py --help       # 本帮助
  python3 -B verify.py --selftest   # 内置自检，退出码 0=通过
被 main.py 同目录 import 使用；仅标准库、不联网、不依赖 CWD。
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import re
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

UNKNOWN = object()


# ---------------------------------------------------------------- 基础 IO
def load_json(path):
    """读 JSON，容忍 BOM/GB18030/latin-1 回退。返回 (obj, err)。"""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except Exception as exc:
        return None, "read_failed:%s" % exc
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(raw.decode(enc)), None
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            return None, "parse_failed:%s" % exc
    return None, "decode_failed"


def dump_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return str(p)


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, p)
    return str(p)


# ---------------------------------------------------------------- 文本规范化
def norm(s):
    """匹配用规范化：NFKC、去零宽、空白折叠、转小写。"""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s)
    for ch in ("\u200b", "\ufeff", "\u00a0", "\u3000"):
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def snip(s, n=200):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- 材料抽取
def sniff_kind(path):
    """扩展名 + 魔数识别，不依赖标签。"""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        head = p.open("rb").read(1024)
    except Exception:
        return "unreadable"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8") or head[:4] == b"GIF8":
        return "image"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(p) as z:
                names = set(z.namelist())
        except Exception:
            return "zip"
        if "word/document.xml" in names:
            return "docx"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        if any(n.startswith("ppt/") for n in names):
            return "pptx"
        return "zip"
    if ext in (".pdf",):
        return "pdf"
    if ext in (".json",):
        return "json"
    if ext in (".csv",):
        return "csv"
    if ext in (".tsv",):
        return "tsv"
    if ext in (".md", ".markdown"):
        return "md"
    if ext in (".txt", ".log", ".py", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".r", ".jl", ".m"):
        return "text"
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"):
        return "image"
    if ext in (".xlsx", ".xls"):
        return "xlsx"
    if ext in (".docx",):
        return "docx"
    if ext in (".ipynb",):
        return "ipynb"
    try:
        head.decode("utf-8")
        return "text"
    except Exception:
        return "binary"


def _pdf_unescape(b):
    try:
        s = b.decode("latin-1")
    except Exception:
        return ""
    s = s.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    s = re.sub(r"\\([nrtbf])", lambda m: {"n": "\n", "r": "\r", "t": "\t", "b": "", "f": ""}[m.group(1)], s)
    s = re.sub(r"\\[0-7]{1,3}", " ", s)
    return s


def pdf_text(path):
    """优先 pdftotext；否则解 FlateDecode 流做尽力抽取。返回 (text, mode, pages)。"""
    p = Path(path)
    txt, mode, pages = "", "none", 0
    import shutil as _sh
    exe = _sh.which("pdftotext")
    if exe:
        try:
            import subprocess
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                               capture_output=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                txt = r.stdout.decode("utf-8", "ignore")
                mode = "pdftotext"
                pages = txt.count("\f") + 1
                return txt, mode, pages
        except Exception:
            pass
    try:
        data = p.read_bytes()
    except Exception:
        return "", "unreadable", 0
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    chunks = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        raw = data[start:end].rstrip(b"\r\n")
        try:
            raw = zlib.decompress(raw)
        except Exception:
            try:
                raw = zlib.decompress(raw, -15)
            except Exception:
                continue
        if b"Tj" not in raw and b"TJ" not in raw:
            continue
        buf = []
        for tok in re.finditer(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\[\]]|\\.)*\]\s*TJ|T\*|TD|Td|ET", raw):
            g = tok.group(0)
            if g.endswith(b"Tj"):
                buf.append(_pdf_unescape(g[g.find(b"(") + 1:g.rfind(b")")]))
            elif g.endswith(b"TJ"):
                parts = re.findall(rb"\((?:\\.|[^\\()])*\)", g)
                buf.append("".join(_pdf_unescape(x[1:-1]) for x in parts))
            else:
                buf.append("\n")
        seg = "".join(buf)
        if seg.strip():
            chunks.append(seg)
    txt = "\n\n".join(chunks)
    mode = "raw_stream" if txt.strip() else "failed"
    return txt, mode, pages


def _split_paragraphs(text, loc_prefix):
    """按空行/换行切段，返回 [(locator, text)]。"""
    out = []
    blocks = re.split(r"\n\s*\n", text)
    n = 0
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        # 长块按行再切，避免单段过长难以逐字核对
        if len(b) > 1200:
            parts = [x.strip() for x in b.splitlines() if x.strip()]
            for x in parts:
                n += 1
                out.append(("%s:p%d" % (loc_prefix, n), x))
        else:
            n += 1
            out.append(("%s:p%d" % (loc_prefix, n), b))
    return out


def _md_units(text, prefix):
    units = []
    heading = "root"
    n = 0
    buf = []

    def flush():
        nonlocal buf, n
        body = "\n".join(buf).strip()
        if body:
            n += 1
            units.append(("%s:§%s/p%d" % (prefix, heading, n), body))
        buf = []

    for line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s", line):
            flush()
            heading = re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip() or "untitled"
            heading = heading.replace("/", "-")[:40]
            n = 0
            buf.append(line)
        elif not line.strip():
            flush()
        else:
            buf.append(line)
    flush()
    return units


def _json_units(obj, prefix, max_units=4000):
    units = []

    def walk(node, ptr):
        if len(units) >= max_units:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, ptr + "/" + str(k).replace("~", "~0").replace("/", "~1"))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, ptr + "/" + str(i))
        else:
            if node is None:
                return
            key = ptr.rsplit("/", 1)[-1]
            units.append(("%s#%s" % (prefix, ptr or "#"), "%s: %s" % (key, node)))

    walk(obj, "")
    return units


def _csv_units(path, prefix, delim=","):
    units = []
    try:
        raw = Path(path).read_bytes().decode("utf-8-sig", "replace")
    except Exception:
        return units, None
    try:
        rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
    except Exception:
        return units, None
    if not rows:
        return units, None
    header = rows[0]
    units.append(("%s:header" % prefix, " | ".join(header)))
    for i, row in enumerate(rows[1:], start=1):
        if not any(c.strip() for c in row):
            continue
        units.append(("%s:r%d" % (prefix, i), " | ".join(row)))
    return units, header


def _docx_units(path, prefix):
    units = []
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return units
    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", " ", xml)
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    return _split_paragraphs(text, prefix)


def _xlsx_units(path, prefix, limit=3000):
    units = []
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                sx = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
                shared = [html.unescape(re.sub(r"<[^>]+>", "", m))
                          for m in re.findall(r"<si>([\s\S]*?)</si>", sx)]
            sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
            if not sheets:
                return units
            sx = z.read(sheets[0]).decode("utf-8", "ignore")
    except Exception:
        return units
    for ri, row in enumerate(re.finditer(r"<row\b[^>]*>([\s\S]*?)</row>", sx), start=1):
        cells = []
        for m in re.finditer(r"<c\b([^>]*)>([\s\S]*?)</c>", row.group(1)):
            attrs, body = m.group(1), m.group(2)
            v = re.search(r"<v>([\s\S]*?)</v>", body)
            val = v.group(1) if v else ""
            if 't="s"' in attrs and val.isdigit():
                idx = int(val)
                val = shared[idx] if 0 <= idx < len(shared) else val
            else:
                t = re.search(r"<is>[\s\S]*?<t[^>]*>([\s\S]*?)</t>", body)
                if t:
                    val = html.unescape(re.sub(r"<[^>]+>", "", t.group(1)))
            cells.append(html.unescape(re.sub(r"<[^>]+>", "", str(val))))
        if any(c.strip() for c in cells):
            units.append(("%s:r%d" % (prefix, ri), " | ".join(cells)))
        if len(units) >= limit:
            break
    return units


def extract_material(path, rel, prefix):
    """返回材料字典：kind/units/quality/notes。"""
    p = Path(path)
    kind = sniff_kind(p)
    rec = {"path": str(p), "rel": rel, "prefix": prefix, "kind": kind,
           "bytes": 0, "units": [], "quality": "ok", "notes": []}
    try:
        rec["bytes"] = p.stat().st_size
    except Exception:
        pass
    if kind == "pdf":
        txt, mode, pages = pdf_text(p)
        rec["pages"] = pages
        rec["notes"].append("pdf_text:%s" % mode)
        if mode in ("raw_stream", "failed") and len(txt.strip()) < 200:
            rec["quality"] = "low_text"
            rec["notes"].append("PDF 文本层不可用；需要渲染/OCR 才能引用页面文字")
        if mode == "pdftotext":
            for pi, page in enumerate(txt.split("\f"), start=1):
                if page.strip():
                    for loc, body in _split_paragraphs(page, "%s:p%d" % (prefix, pi)):
                        rec["units"].append((loc.replace(":p%d:" % pi, ":pg%d/" % pi), body))
        else:
            rec["units"] = _split_paragraphs(txt, prefix)
    elif kind == "docx":
        rec["units"] = _docx_units(p, prefix)
    elif kind == "xlsx":
        rec["units"] = _xlsx_units(p, prefix)
        rec["notes"].append("xlsx 仅读取首个工作表的单元格文本，公式按缓存值")
    elif kind == "csv":
        units, header = _csv_units(p, prefix, ",")
        rec["units"] = units
        rec["columns"] = header or []
    elif kind == "tsv":
        units, header = _csv_units(p, prefix, "\t")
        rec["units"] = units
        rec["columns"] = header or []
    elif kind in ("json", "ipynb"):
        obj, err = load_json(p)
        if obj is None:
            rec["quality"] = "unparsed"
            rec["notes"].append(err or "json 解析失败")
        else:
            rec["units"] = _json_units(obj, prefix)
    elif kind == "md":
        try:
            rec["units"] = _md_units(p.read_text(encoding="utf-8-sig", errors="replace"), prefix)
        except Exception as exc:
            rec["quality"] = "unparsed"
            rec["notes"].append(str(exc))
    elif kind == "text":
        try:
            rec["units"] = _split_paragraphs(p.read_text(encoding="utf-8-sig", errors="replace"), prefix)
        except Exception as exc:
            rec["quality"] = "unparsed"
            rec["notes"].append(str(exc))
    elif kind == "image":
        rec["quality"] = "no_ocr"
        rec["notes"].append("图片材料：本 Skill 不读取像素；如需数值请在 draft 中引用人工/外部 OCR 结果并标注")
    else:
        rec["quality"] = "unsupported"
        rec["notes"].append("未识别类型 %s" % kind)
    if len(rec["units"]) > 4000:
        rec["units"] = rec["units"][:4000]
        rec["notes"].append("段落数截断至 4000")
    return rec


# ---------------------------------------------------------------- 证据匹配
def flat_units(index):
    out = []
    for m in index.get("materials", []):
        for loc, text in m.get("units", []):
            out.append({"source_id": m["id"], "locator": loc, "text": text,
                        "tn": norm(text), "kind": m["kind"]})
    return out


def find_quote(units, quote, source_id=None):
    """逐字（规范化后）查 quote，返回命中列表。"""
    q = norm(quote)
    if len(q) < 4:
        return []
    hits = []
    for u in units:
        if source_id and u["source_id"] != source_id:
            continue
        if q and q in u["tn"]:
            hits.append({"source_id": u["source_id"], "locator": u["locator"],
                         "method": "normalized_exact"})
    return hits


def check_evidence(units, ev):
    """返回 (ok, hits, reason)。"""
    if not isinstance(ev, dict):
        return False, [], "evidence_not_object"
    quote = ev.get("quote") or ""
    if not str(quote).strip():
        return False, [], "missing_quote"
    hits = find_quote(units, str(quote), ev.get("source_id") or None)
    if not hits:
        return False, [], "quote_not_found"
    if ev.get("source_id") and not any(h["source_id"] == ev["source_id"] for h in hits):
        return False, hits, "source_mismatch"
    if ev.get("locator"):
        declared = norm(str(ev["locator"]))
        exact = [h for h in hits if norm(h["locator"]) == declared]
        if exact:
            return True, exact, "ok"
        # locator 与 quote 同文件但段号不同：接受但标注
        return True, hits, "locator_differs_from_index"
    return True, hits[:3], "ok"


# ---------------------------------------------------------------- 容差与比较
def prior_tolerance(metric, reported):
    """事前默认规则：相对 2%，绝对值为报告值 0.5%（覆盖四舍五入）。"""
    abs_tol = 0.0
    if isinstance(reported, (int, float)) and reported != 0:
        abs_tol = round(abs(reported) * 0.005, 12)
    return {"abs_tol": abs_tol, "rel_tol": 0.02,
            "basis": "prior default: rel 2% (typical run-to-run reproducibility for reported metrics), "
                     "abs = 0.5% of reported value to absorb rounding"}


def compare_values(observed, reported, abs_tol, rel_tol):
    if not isinstance(observed, (int, float)) or not isinstance(reported, (int, float)):
        return {"within_tolerance": None, "abs_dev": None, "rel_dev": None,
                "note": "non_numeric"}
    ad = abs(float(observed) - float(reported))
    rd = (ad / abs(float(reported))) if reported else None
    ok = (abs_tol is not None and ad <= float(abs_tol) + 1e-15) or \
         (rd is not None and rel_tol is not None and rd <= float(rel_tol) + 1e-15)
    return {"within_tolerance": bool(ok), "abs_dev": round(ad, 12),
            "rel_dev": None if rd is None else round(rd, 8)}


# ---------------------------------------------------------------- 契约回填
RULES = [
    (("repro", "复现"), "reproduction"),
    (("compar", "diff", "对比", "差异"), "comparison"),
    (("attribut", "归因", "cause"), "attribution"),
    (("toler", "容差"), "tolerance"),
    (("run", "exec", "运行", "command"), "runs"),
    (("param", "参数", "hyper", "超参"), "params"),
    (("environ", "环境"), "environment"),
    (("evid", "证据", "quote", "citation", "locator"), "evidence"),
    (("conclusion", "verdict", "结论", "判定"), "conclusion"),
    (("uncert", "不确定"), "uncertainty"),
    (("pending", "human", "人工", "接管"), "pending_human"),
    (("gap", "missing", "缺口", "缺失"), "gaps"),
    (("plan", "step", "checklist", "流程", "清单"), "plan"),
    (("claim", "结论点"), "claims"),
    (("summary", "摘要", "answer", "答案", "abstract"), "summary"),
    (("source", "来源", "material", "材料"), "sources"),
    (("status", "状态"), "status"),
    (("result", "结果"), "reproduction"),
]


def semantic(key, values):
    k = (key or "").lower()
    for pats, slot in RULES:
        if any(p in k for p in pats):
            if slot in values:
                return values[slot]
    return UNKNOWN


def fill_contract(tmpl, values, unmapped, key=""):
    """按语义回填 output_contract，字段名不变。"""
    if isinstance(tmpl, dict):
        if tmpl:
            return {k: fill_contract(v, values, unmapped, k) for k, v in tmpl.items()}
        val = semantic(key, values)
        return {} if val is UNKNOWN else val
    val = semantic(key, values)
    if isinstance(tmpl, list):
        if val is UNKNOWN:
            if key:
                unmapped.append(key)
            return []
        if isinstance(val, list):
            return val
        return [val]
    if val is UNKNOWN:
        if key:
            unmapped.append(key)
        return None
    return val


# --------------------------------------------------------- 自检
def selftest():
    fails = []
    assert norm("A  b\n c") == "a b c"
    u = [{"source_id": "m1", "locator": "m1:p2", "text": "Top-1 accuracy 76.5% on ImageNet", "tn": norm("Top-1 accuracy 76.5% on ImageNet"), "kind": "text"}]
    ok, hits, why = check_evidence(u, {"quote": "accuracy 76.5%", "source_id": "m1"})
    fails += [] if ok and hits and why == "ok" else ["quote_hit"]
    ok2, _, why2 = check_evidence(u, {"quote": "accuracy 99.9%"})
    fails += [] if (not ok2 and why2 == "quote_not_found") else ["quote_miss"]
    c = compare_values(76.8, 76.5, 0.38, 0.02)
    fails += [] if c["within_tolerance"] else ["compare_pass"]
    c2 = compare_values(80.0, 76.5, 0.38, 0.02)
    fails += [] if c2["within_tolerance"] is False else ["compare_fail"]
    vals = {"status": "ok", "summary": "s", "runs": [1], "evidence": [{"x": 1}], "reproduction": {"v": 1}}
    un = []
    filled = fill_contract({"status": None, "reproduction_record": None,
                            "run_log": [], "evidence": [], "zzz_unknown": None}, vals, un)
    fails += [] if filled["status"] == "ok" and filled["reproduction_record"] == {"v": 1} else ["contract"]
    fails += [] if filled["run_log"] == [1] and "zzz_unknown" in un else ["contract_unknown"]
    fails += [] if isinstance(filled["evidence"], list) and filled["evidence"] else ["contract_evidence"]
    print("selftest: %s" % ("PASS" if not fails else "FAIL " + ", ".join(fails)))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(
        description="确定性校验库：材料抽取/证据匹配/容差/契约（main.py 的支撑模块）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自检")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    ap.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
