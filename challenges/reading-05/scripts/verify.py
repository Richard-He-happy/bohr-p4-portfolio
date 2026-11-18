#!/usr/bin/env python3
"""verify.py -- extraction core + deterministic validators (stdlib only).

Each material becomes locator-bearing paragraphs; a quote is accepted only when literally
present in that document's text. Exit code always 0.
  verify.py quote --index I --doc D1 --quote "..."  |  verify.py draft --index I --draft D
"""
import argparse
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

WS = re.compile(r"\s+")
TR = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2013": "-", "\u2014": "-",
      "\u2212": "-", "\u00a0": " ", "\u200b": "", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl"}


def norm(s, sq=False):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    for k, v in TR.items():
        s = s.replace(k, v)
    return WS.sub("" if sq else " ", s).strip()


def slug(s, fb="f"):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", norm(s).lower()).strip("_") or fb


def find_quote(text, quote):
    q, t = norm(quote), norm(text or "")
    if len(q) < 3 or not t:
        return {"found": False, "mode": "short", "index": -1}
    i = t.find(q)
    if i >= 0:
        return {"found": True, "mode": "exact", "index": i}
    j, t2 = norm(text, True).find(norm(quote, True)), norm(quote, True)
    if t2 and j >= 0:
        return {"found": True, "mode": "loose", "index": j}
    return {"found": False, "mode": "miss", "index": -1}


# ---------------------------------------------------------------- extraction
def kind_of(p):
    try:
        h = Path(p).read_bytes()[:8]
    except Exception:
        return "unreadable"
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK"):
        try:
            with zipfile.ZipFile(p) as z:
                n = " ".join(z.namelist()[:60])
        except Exception:
            return "zip"
        for k, v in (("word/document", "docx"), ("xl/workbook", "xlsx"), ("ppt/presentation", "pptx")):
            if k in n:
                return v
        return "zip"
    return "text"


DELIM = b" \t\r\n\x00\x0c()<>[]{}/%"


def _lit(cs, i):
    i, buf, n = i + 1, bytearray(), len(cs)
    while i < n:
        c = cs[i]
        if c == 0x5C and i + 1 < n:
            nx = cs[i + 1]
            if nx in (0x6E, 0x72, 0x74, 0x62, 0x66):
                buf.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[nx]); i += 2; continue
            if 0x30 <= nx <= 0x37:
                k = 0
                while k < 3 and i + 1 + k < n and 0x30 <= cs[i + 1 + k] <= 0x37:
                    k += 1
                buf.append(int(cs[i + 1:i + 1 + k], 8) & 0xFF); i += 1 + k; continue
            if nx not in (10, 13):
                buf.append(nx)
            i += 2; continue
        if c == 0x28:
            d, i = 1, i + 1
            while i < n and d:
                if cs[i] == 0x5C:
                    buf.extend(cs[i:i + 2]); i += 2; continue
                d += 1 if cs[i] == 0x28 else (-1 if cs[i] == 0x29 else 0)
                i += 1
                if d:
                    buf.append(cs[i - 1])
            continue
        if c == 0x29:
            return bytes(buf), i + 1
        buf.append(c); i += 1
    return bytes(buf), i


def _dec(b):
    if b[:2] == b"\xfe\xff":
        return b[2:].decode("utf-16-be", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("cp1252", "replace")


def _ctext(cs):
    i, n, out, args = 0, len(cs), [], []

    def emit(v):
        if v and out and out[-1] and out[-1][-1].isalnum() and v[:1].isalnum():
            out.append(" ")
        out.append(v)

    while i < n:
        c = cs[i:i + 1]
        if c in b" \t\r\n\x00\x0c":
            i += 1; continue
        if c == b"%":
            k = cs.find(b"\n", i); i = n if k < 0 else k + 1; continue
        if c == b"(":
            s, i = _lit(cs, i); args.append(("s", _dec(s))); continue
        if c == b"<":
            if cs[i + 1:i + 2] == b"<<":
                k = cs.find(b">>", i); i = n if k < 0 else k + 2; continue
            e = cs.find(b">", i)
            h = re.sub(rb"[^0-9A-Fa-f]", b"", cs[i + 1:e if e >= 0 else i + 1])
            i = e + 1 if e >= 0 else n
            try:
                args.append(("s", _dec(bytes.fromhex(h.decode()))))
            except Exception:
                pass
            continue
        if c in b"[]{}":
            i += 1; continue
        k = i
        while k < n and cs[k:k + 1] not in DELIM:
            k += 1
        tok, i = (cs[i:k], k) if k > i else (cs[i:i + 1], i + 1)
        if re.fullmatch(rb"[-+]?[\d.]+", tok):
            args.append(("n", tok.decode())); continue
        op = tok.decode("latin-1", "replace")
        if op == "TJ":
            for t, v in args:
                if t == "s":
                    out.append(v)
                else:
                    try:
                        if abs(float(v)) >= 100:
                            out.append(" ")
                    except Exception:
                        pass
        elif op == "Tj":
            for t, v in args:
                if t == "s":
                    emit(v)
        elif op in ("'", '"'):
            out.append("\n")
            out += [v for t, v in args if t == "s"]
        elif op in ("Td", "TD", "Tm", "T*", "BT", "ET"):
            out.append("\n")
        args = []
    return "".join(out)


def _streams(d):
    out, pos = [], 0
    while True:
        i = d.find(b"stream", pos)
        if i < 0:
            return out
        j = i + 6
        j += 2 if d[j:j + 2] == b"\r\n" else (1 if d[j:j + 1] in (b"\n", b"\r") else 0)
        e = d.find(b"endstream", j)
        if e < 0:
            return out
        out.append((d[max(0, i - 600):i], d[j:e]))
        pos = e + 9


def _builtin_pdf(d):
    pages = []
    for head, raw in _streams(d):
        if any(k in head for k in (b"Image", b"DCTDecode", b"JPXDecode")):
            continue
        body = raw
        if b"FlateDecode" in head:
            import zlib
            for dec in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x)):
                try:
                    body = dec(raw)
                    break
                except Exception:
                    body = raw
        try:
            if b"Tj" in body or b"TJ" in body:
                t = _ctext(body)
                if t.strip():
                    pages.append(("s%d" % (len(pages) + 1), t))
        except Exception:
            continue
    return pages, "builtin-zlib", [] if pages else ["no text layer (scan?); OCR unavailable"]


def pdf_pages(raw):
    if shutil.which("pdftotext"):
        try:
            td = Path(tempfile.mkdtemp(prefix="cmp_"))
            (td / "d.pdf").write_bytes(raw)
            subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(td / "d.pdf"), str(td / "d.txt")],
                           timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pages = [("p%d" % (i + 1), t) for i, t in
                     enumerate((td / "d.txt").read_text(encoding="utf-8", errors="replace").split("\f")) if t.strip()]
            if pages:
                return pages, "pdftotext", []
        except Exception:
            pass
    return _builtin_pdf(raw)


def docx_text(p):
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines = ["".join(x.text or "" for x in para.iter(ns + "t")) for para in root.iter(ns + "p")]
    return [("p1", "\n\n".join(x for x in lines if x.strip()))]


def text_pages(p):
    b = Path(p).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return [("p1", b.decode(enc))], enc
        except Exception:
            pass
    return [("p1", b.decode("utf-8", "replace"))], "replace"


def paragraphize(pages):
    paras = []
    for label, text in pages:
        t = re.sub(r"[ \t]+", " ", text or "")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
        if len(blocks) <= 1 and len(t) > 1500:
            blocks, cur = [], []
            for ln in [x.strip() for x in t.splitlines() if x.strip()]:
                cur.append(ln)
                if len(" ".join(cur)) > 600:
                    blocks.append(" ".join(cur)); cur = []
            if cur:
                blocks.append(" ".join(cur))
        k = 0
        for b in blocks:
            b = re.sub(r"-\n(?=[a-z])", "", b)
            b = re.sub(r"\s+", " ", b).strip()
            if len(b) < 3:
                continue
            if len(b) < 40 and paras and paras[-1]["locator"].split("#")[0] == label:
                paras[-1]["text"] += " " + b
                continue
            k += 1
            paras.append({"pid": "p%d" % (len(paras) + 1), "locator": "%s#para%d" % (label, k),
                          "page": label, "text": b})
    return paras or [{"pid": "p1", "locator": "p1#para1", "page": "p1", "text": ""}]


def extract_doc(p):
    k, notes = kind_of(p), []
    if k == "pdf":
        pages, eng, notes = pdf_pages(Path(p).read_bytes())
        if eng != "pdftotext":
            notes.append("page numbers not authoritative; locators use %s blocks" % eng)
    elif k == "docx":
        pages, eng = docx_text(p), "docx-xml"
    elif k == "text":
        pages, eng = text_pages(p)
    else:
        pages, eng = [], "unsupported"
        notes.append("%s container not parsed" % k)
    paras = paragraphize(pages)
    text = " ".join(x["text"] for x in paras)
    q = sum(ch.isalnum() for ch in text) / max(len(text), 1)
    if text and q < 0.5:
        notes.append("low text quality (alnum %.2f): CID font or scan likely" % q)
    return {"kind": k, "engine": eng, "paras": paras, "text": text, "n_pages": len(pages),
            "quality": round(q, 3), "notes": notes}


# ---------------------------------------------------------------- draft checks
def cells_of(d):
    return [r for r in (d.get("matrix") or d.get("cells") or d.get("rows") or []) if isinstance(r, dict)]


def fields_of(d):
    src = d.get("fields") or d.get("field_definitions") or d.get("common_fields") or []
    out = []
    for i, f in enumerate(src if isinstance(src, list) else []):
        if isinstance(f, str):
            out.append({"field_id": slug(f, "f%d" % (i + 1)), "name": f})
        elif isinstance(f, dict):
            nm = f.get("name") or f.get("label") or f.get("field") or ""
            out.append({"field_id": str(f.get("field_id") or f.get("id") or f.get("key") or
                                        slug(nm, "f%d" % (i + 1))),
                        "name": nm or "?", "definition": f.get("definition") or f.get("desc") or "",
                        "unit": f.get("unit") or "",
                        "value_rule": f.get("value_rule") or f.get("rule") or ""})
    return out


def papers_of(d):
    src = d.get("papers") or d.get("documents") or d.get("corpus") or []
    out = []
    for i, p in enumerate(src if isinstance(src, list) else []):
        if isinstance(p, str):
            out.append({"doc_id": p, "citation": ""})
        elif isinstance(p, dict):
            out.append(dict(p, doc_id=str(p.get("doc_id") or p.get("id") or p.get("source_document_id")
                                          or "D%d" % (i + 1))))
    return out


def validate(draft, index):
    texts, paras = index.get("texts") or {}, index.get("paras") or {}
    rep = {"errors": [], "warnings": [], "counts": {}}
    err = lambda c, d, w="": rep["errors"].append({"code": c, "detail": d, "where": w})
    warn = lambda c, d, w="": rep["warnings"].append({"code": c, "detail": d, "where": w})
    papers, fields, cells = papers_of(draft), fields_of(draft), cells_of(draft)
    dids, fids = [p["doc_id"] for p in papers], [f["field_id"] for f in fields]
    if not fields:
        err("no_fields", "no field definitions", "fields")
    if not cells:
        err("no_matrix", "no matrix cells", "matrix")
    if len(set(fids)) != len(fids):
        err("duplicate_field_id", "field_id not unique", "fields")
    for f in fields:
        if not f.get("definition"):
            warn("field_no_definition", "%s lacks definition" % f["field_id"], "fields")
        if not f.get("value_rule"):
            warn("field_no_value_rule", "%s lacks value rule" % f["field_id"], "fields")
    for d in [x for x in dids if x not in texts] + [x for x in texts if x not in dids]:
        warn("doc_set_mismatch", "document %s not in both draft and corpus" % d, "papers")

    seen, n = {}, dict(rep=0, unrep=0, qmiss=0, qbad=0, locmiss=0, auto=0)
    for c in cells:
        did = str(c.get("doc_id") or c.get("source_document_id") or "")
        fid = str(c.get("field_id") or c.get("field") or "")
        w = "%s/%s" % (did or "?", fid or "?")
        if not did or did not in texts:
            err("cell_unknown_doc", "cell cites unknown document %r" % did, w); continue
        if fid not in fids:
            err("cell_unknown_field", "cell cites undeclared field %r" % fid, w)
        if (did, fid) in seen:
            err("duplicate_cell", "duplicate cell", w)
        seen[(did, fid)] = c
        st = norm(c.get("status")).lower() or ("reported" if c.get("value") not in (None, "") else "unreported")
        val = c.get("value")
        if st == "reported" and val in (None, ""):
            err("reported_without_value", "value empty", w); continue
        if st in ("unreported", "not_applicable"):
            n["unrep"] += 1
            if st == "unreported" and not (c.get("note") or c.get("reason")):
                warn("unreported_no_reason", "no reason given", w)
            continue
        n["rep"] += 1
        n["auto"] += str(c.get("confidence") or "").lower() == "auto"
        q = c.get("quote") or c.get("evidence_quote")
        if not q:
            n["qmiss"] += 1; err("quote_missing", "no verbatim quote", w); continue
        if not find_quote(texts.get(did, ""), q)["found"]:
            n["qbad"] += 1; err("quote_not_found", "quote absent from %s: %r" % (did, norm(q)[:90]), w); continue
        if not (c.get("locator") or c.get("paragraph_id") or c.get("page")):
            n["locmiss"] += 1; err("locator_missing", "no locator", w)

    total = max(len(fields) * max(len(dids), 1), 1)
    rep["counts"].update({"documents": len(dids), "fields": len(fields), "cells": len(cells),
                          "cells_reported": n["rep"], "cells_unreported": n["unrep"], "cells_auto": n["auto"],
                          "quote_missing": n["qmiss"], "quote_not_found": n["qbad"],
                          "locator_missing": n["locmiss"], "coverage": round(n["rep"] / total, 3),
                          "quote_pass_rate": round((n["rep"] - n["qmiss"] - n["qbad"]) / max(n["rep"], 1), 3)})
    comp = [x for x in (draft.get("comparability") or draft.get("comparability_checks") or []) if isinstance(x, dict)]
    for i, c in enumerate(comp):
        w = "comparability[%d]" % i
        if not (c.get("dimension") or c.get("axis")):
            err("comparability_no_dimension", "item lacks dimension", w)
        if "comparable" not in c and "verdict" not in c:
            err("comparability_no_verdict", "item lacks comparable flag", w)
        did = str(c.get("doc_id") or (c.get("doc_ids") or [""])[0])
        if c.get("quote") and did in texts and not find_quote(texts[did], c["quote"])["found"]:
            err("comparability_quote_not_found", "quote absent from %s" % did, w)
    rep["counts"]["comparability_items"] = len(comp)

    concl = [x for x in (draft.get("conclusions") or []) if isinstance(x, dict)]
    for i, c in enumerate(concl):
        w, did, q = "conclusions[%d]" % i, str(c.get("doc_id") or ""), c.get("quote")
        if q and did in texts and not find_quote(texts[did], q)["found"]:
            err("conclusion_quote_not_found", "quote absent from %s" % did, w)
    agr = draft.get("agreement") or draft.get("synthesis") or {}
    items = [x for x in ((agr.get("items") if isinstance(agr, dict) else agr) or []) if isinstance(x, dict)]
    for i, it in enumerate(items):
        w = "agreement[%d]" % i
        vd, att = norm(it.get("verdict") or it.get("status")).lower(), norm(it.get("cause") or it.get("attribution")).lower()
        if vd == "conflicting" and att in ("", "unresolved"):
            err("conflict_without_attribution", "conflict not attributed to sample/method/metric/condition", w)
    rep["counts"]["conclusion_items"] = len(concl)
    rep["counts"]["agreement_items"] = len(items)
    rep["ok"] = not rep["errors"]
    return rep


def _tbl(head, rows):
    e = lambda s: str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(e(h) for h in head) + " |", "|" + "|".join(["---"] * len(head)) + "|"] +
                     ["| " + " | ".join(e(c) for c in r) + " |" for r in rows])


def table_md(M, gen="multi-document-comparison v2"):
    c, by = M["coverage"], {(x["doc_id"], x["field_id"]): x for x in M["matrix"]}
    rows = []
    for f in M["fields"]:
        r = ["%s (%s)" % (f["field_id"], f["name"])]
        for p in M["papers"]:
            x = by.get((p["doc_id"], f["field_id"]))
            r.append("— 未报告" if not x or x.get("status") != "reported" else "%s%s  \n<sub>%s</sub>" % (
                x.get("value"), (" " + str(x["unit"])) if x.get("unit") else "", x.get("locator") or ""))
        rows.append(r)
    L = ["# 多文档比较表 · 共同字段矩阵", "", "> case `%s` ｜ status **%s** ｜ %s" % (M["case_id"], M["status"], gen), ""]
    if M.get("question"):
        L += ["## 0. 比较问题", "", M["question"], ""]
    L += ["## 1. 逐格比较矩阵（口径见 result.json.fields；带 locator，未报告不填）", "",
          _tbl(["field_id (name)"] + [p["doc_id"] for p in M["papers"]], rows), "", "## 2. 可比性判定", ""] + [
          "- **%s** ｜ %s → %s：%s" % (x.get("dimension"), ", ".join(x.get("doc_ids") or []),
                                      "可比" if x.get("comparable") else "不可比", x.get("basis")) for x in M["comparability"]] + [
          "", "## 3. 结论一致性与冲突归因（详见 result.json.agreement）", ""] + [
          "- **%s** ｜ %s ｜ 归因：%s ｜ %s" % (i.get("topic"), i.get("verdict"), i.get("attribution"), i.get("explanation"))
          for i in (M["agreement"] or {}).get("items") or []] + [
          "", "## 4. 覆盖、缺口与核对", "",
          "- 单元格 %s；已报告 %s；未报告 %s；覆盖率 %s；引文命中率 %s" % (c.get("cells"), c.get("cells_reported"),
                                                              c.get("cells_unreported"), c.get("coverage"), c.get("quote_pass_rate")),
          "- 降级：%s" % ("; ".join(M.get("degradations") or []) or "无"),
          "- 复跑：main.py init → show --doc <id> → verify.py quote → check。", ""]
    return "\n".join(L)


def contract_keys(contract):
    if isinstance(contract, dict):
        return [str(k) for k in contract]
    if isinstance(contract, list):
        return [f if isinstance(f, str) else str(f.get("name") or f.get("key") or "field_%d" % (i + 1))
                for i, f in enumerate(contract) if isinstance(f, (str, dict))]
    return []


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))
def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="quote/draft checks")
    sub = ap.add_subparsers(dest="cmd")
    q = sub.add_parser("quote")
    for x in ("--index", "--doc", "--quote"):
        q.add_argument(x, required=True)
    d = sub.add_parser("draft")
    for x in ("--index", "--draft"):
        d.add_argument(x, required=True)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return
    try:
        if a.cmd == "quote":
            idx = _load(a.index)
            out = dict(find_quote((idx.get("texts") or {}).get(a.doc, ""), a.quote), doc=a.doc)
        else:
            out = validate(_load(a.draft), _load(a.index))
    except Exception as ex:
        out = {"ok": False, "errors": [{"code": "verify_failure", "detail": repr(ex)}]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _cli(sys.argv[1:])
