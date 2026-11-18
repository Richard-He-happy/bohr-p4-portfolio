#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extraction, document model, verbatim-quote verification and rendering (library for main.py).

stdlib only, no network, CWD-independent, no side effects on import.
"""
from __future__ import annotations
import csv
import html
import io
import json
import re
import shutil
import subprocess
import zipfile
import zlib
from pathlib import Path

VERSION = "1.0.0"
WS = re.compile(r"\s+")
INV = dict.fromkeys(map(ord, "\u00ad\u200b\ufeff\u2060"), None)
SEV_ORDER = {"blocker": 0, "major": 1, "minor": 2, "suggestion": 3}
CATS = ["fact", "citation", "design", "statistics", "logic", "norms"]
FACETS = ["design", "variables", "statistics", "sample_size", "reporting"]
CN = {"fact": "事实核验", "citation": "引用支持", "design": "方法设计", "statistics": "统计报告",
      "logic": "论证链", "norms": "学术规范"}
FCN = {"design": "研究设计", "variables": "变量定义", "statistics": "统计方法",
       "sample_size": "样本量", "reporting": "结果报告"}
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}


def norm(s):
    return WS.sub(" ", str(s or "").translate(INV).replace("\u3000", " ").replace("\xa0", " ")).strip()


def dec(b):
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def load_json(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def write_json(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + ".tmp")
    with open(t, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    t.replace(p)
    return p


def pdf_text(p, w):
    """pdftotext when available; stdlib zlib/Tj fallback otherwise (low fidelity, no page numbers)."""
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, timeout=90)
            if r.returncode == 0 and len(r.stdout) > 200:
                return dec(r.stdout), "pdftotext", ""
        except Exception as e:
            w.append("pdftotext_failed:%s" % e)
    try:
        out = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", p.read_bytes(), re.S):
            try:
                b = zlib.decompress(m.group(1))
            except Exception:
                continue
            if b"Tj" in b or b"TJ" in b:
                out.append(" ".join(dec(re.sub(rb"\\([()\\])", rb"\1", t[1:-1]))
                                    for t in re.findall(rb"\((?:\\.|[^()\\])*\)", b)))
        t = "\n".join(out)
        if len(t.strip()) > 100:
            w.append("pdf_fallback:no page numbers; quotes matched on whole text")
            return t, "zlib-fallback", "pdf_text_low_fidelity"
    except Exception as e:
        w.append("pdf_parse_error:%s" % e)
    return "", "", "pdf_text_unavailable"


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        x = "\n".join(dec(z.read(n)) for n in z.namelist()
                      if re.match(r"word/(document|footnotes|endnotes)\d*\.xml", n))
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<w:(tab|br)\s*/>", " ", x.replace("</w:p>", "\n"))))


def xlsx_text(p):
    """Flat cell text: shared strings then rows, cells joined by ' | '."""
    with zipfile.ZipFile(p) as z:
        nm, out = z.namelist(), []
        if "xl/sharedStrings.xml" in nm:
            out.append(" ".join(html.unescape(re.sub(r"<[^>]+>", "", x)) for x in
                                re.findall(r"<si>(.*?)</si>", dec(z.read("xl/sharedStrings.xml")), re.S)))
        for n in sorted(x for x in nm if x.startswith("xl/worksheets/sheet")):
            x = dec(z.read(n)).replace("</c>", " | ")
            out.append(re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))))
    return "\n".join(out)

def extract(p, w):
    """Return (text, parser, kind, degradation). Filenames never decide content."""
    s = p.suffix.lower()
    try:
        if s == ".pdf":
            t, a, b = pdf_text(p, w)
            return t, a, "pdf", b
        if s == ".docx":
            return docx_text(p), "docx-xml", "docx", ""
        if s in (".xlsx", ".xlsm"):
            return xlsx_text(p), "xlsx-xml", "table", ""
        if s in IMG:
            w.append("image_not_parsed:%s" % p.name)
            return "", "", "image", "image_not_parsed"
        return dec(p.read_bytes()), "text", "text", ""
    except Exception as e:
        w.append("extract_error:%s:%s" % (p.name, e))
        return "", "", "text", "extract_error"


SEC = [(k, re.compile(r"^\s*#*\s*.{0,4}?(?:%s)\b" % v, re.I)) for k, v in [
    ("abstract", "\u6458\u8981|abstract|summary"),
    ("methods", "\u6750\u6599\u4e0e\u65b9\u6cd5|\u5bf9\u8c61\u4e0e\u65b9\u6cd5|\u65b9\u6cd5|methods?|methodology|"
                "materials and methods|study design|statistical analysis"),
    ("results", "\u7ed3\u679c|results?|findings"), ("discussion", "\u8ba8\u8bba|discussion"),
    ("conclusion", "\u7ed3\u8bba|conclusions?"),
    ("refs", "\u53c2\u8003\u6587\u732e|references?|bibliography|literature cited")]]


def paras(text, refs=False):
    out, buf = [], []

    def fl():
        s = " ".join(buf).strip()
        if s:
            out.append(s)
        buf.clear()
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            fl()
        elif refs or len(s) <= 90:
            fl()
            out.append(s)
        else:
            buf.append(s)
            if len(" ".join(buf)) > 600:
                fl()
    fl()
    return out


def build_doc(did, path, kind, text, parser):
    ps, sec = [], ""
    for pi, page in enumerate(text.split("\f") if kind == "pdf" else [text], 1):
        for ch in paras(page, refs=(sec == "refs")):
            new = next((k for k, rx in SEC if rx.search(ch)), sec)
            if new != sec and len(ch) <= 90:
                sec = new
                continue
            sec = new
            n = len(ps) + 1
            loc = ("p.%d/\u00b6%d" % (pi, n) if kind == "pdf" else
                   "inline:%s:\u00b6%d" % (path, n) if kind == "inline" else
                   "\u00a7%s:\u00b6%d" % (sec, n) if sec else "\u00b6%d" % n)
            ps.append({"n": n, "section": sec, "text": ch, "locator": loc, "doc_id": did})
    return {"id": did, "path": str(path), "kind": kind, "parser": parser, "text": text,
            "ntext": norm(text), "chars": len(text), "paras": ps}


class Ctx:
    """Body paragraphs (refs excluded) plus whole-text views."""

    def __init__(self, docs):
        self.docs = docs
        self.body = [p for d in docs for p in d["paras"] if p["section"] != "refs"]
        self.refs = [p for d in docs for p in d["paras"] if p["section"] == "refs"]
        self.nf = norm("\n".join(p["text"] for p in self.body))
        self.reftext = norm("\n".join(p["text"] for p in self.refs))
        self.chars = len(norm("\n".join(d["text"] for d in docs)))
        self.short = self.chars < 800
        self.primary = max(docs, key=lambda d: d["chars"])["id"]

    def has(self, pat):
        return bool(pat) and re.search(pat, self.nf, re.I) is not None

    def find(self, pat, lim=60):
        rx, out = re.compile(pat, re.I), []
        for p in self.body:
            for m in rx.finditer(p["text"]):
                out.append((p, m))
                if len(out) >= lim:
                    return out
        return out

    def tail(self):
        return self.body[-1] if self.body else None


def verify_quote(q, docs):
    """True only if q is a verbatim substring (whitespace-normalised) of a source doc."""
    n = norm(q)
    if len(n) < 8:
        return {"ok": False, "why": "quote_too_short"}
    n = n.rstrip("\u2026").rstrip(".")
    for d in docs:
        hay = d.get("ntext") or norm(d.get("text"))
        if not hay or n not in hay:
            continue
        loc = d.get("id", "doc")
        for p in d.get("paras", []):
            if norm(n[:30]) in norm(p.get("text")):
                loc = p["locator"]
                break
        return {"ok": True, "source_id": d.get("id"), "locator": loc, "why": ""}
    return {"ok": False, "why": "quote_not_found_in_source"}


def confidence_cap(it):
    cap = {"error": .97, "gap": .75, "judgment": .8}.get(it.get("evidence_strength"), .75)
    try:
        c = float(it.get("confidence", .6))
    except (TypeError, ValueError):
        c = .6
    it["confidence"] = round(max(.05, min(c, cap)), 2)
    return it


def dedupe(issues):
    seen, out = {}, []
    for it in issues:
        k1, k2 = (it.get("rule_id"), norm(it.get("quote"))[:60]), (it.get("rule_id"), it.get("locator"))
        if k1 in seen or k2 in seen:
            h = seen.get(k1) or seen.get(k2)
            h.setdefault("merged_locators", [])
            if it.get("locator") not in h["merged_locators"]:
                h["merged_locators"].append(it.get("locator"))
            continue
        seen[k1] = seen[k2] = it
        out.append(it)
    return out


def backfill(contract, res):
    keys = list(contract.keys()) if isinstance(contract, dict) else [k for k in contract or [] if isinstance(k, str)]
    add = []
    for k in keys:
        if k not in res:
            hint = contract.get(k) if isinstance(contract, dict) else None
            res[k] = [] if isinstance(hint, (list, tuple)) else None
            add.append(k)
    res["_contract_keys"], res["_contract_backfilled"] = keys, add
    return res


def renumba(issues):
    issues.sort(key=lambda i: (SEV_ORDER.get(i.get("severity"), 9),
                               CATS.index(i["category"]) if i.get("category") in CATS else 9,
                               str(i.get("locator"))))
    for n, it in enumerate(issues, 1):
        it["id"] = "I%02d" % n
    return issues


def checks(c, issues, errs, rules):
    ch = {}
    for cat in CATS:
        items, seen = [], set()
        for r in [x for x in rules if x["cat"] == cat and x["id"] not in seen]:
            seen.add(r["id"])
            st = "fail" if any(i["rule_id"] == r["id"] for i in issues) else ("manual" if r["kind"] == "manual" else "pass")
            if st == "pass" and not c.refs and r["id"][:1] == "C" and r["id"] != "C-05":
                st = "skipped"
            items.append({"rule_id": r["id"], "status": st, "note": r["title"]})
        man = [i["rule_id"] for i in items if i["status"] == "manual"]
        ch[cat] = {"status": "not_checked" if not c.body else ("partially_checked" if man else "checked"),
                   "scope": "body %d 段 / %d 字符；参考文献 %d 段"
                            % (len(c.body), c.chars, len(c.refs)),
                   "items": items, "findings": [i["id"] for i in issues if i.get("category") == cat],
                   "open": man + (["detector_error:" + e for e in errs[:3]] if errs else [])}
    return ch


def merge_model(c, issues, path, pend):
    """Stage 2: merge judged findings whose quote is verbatim in the source; others go to pending_human."""
    try:
        data = load_json(path)
    except Exception as e:
        return issues, 0, "merge_read_error:%s" % e
    n = 0
    for k, e in enumerate(data if isinstance(data, list) else (data.get("issues") or []), 1):
        if not isinstance(e, dict):
            continue
        q = str(e.get("quote") or "")
        hit = verify_quote(q, c.docs)
        it = {"rule_id": str(e.get("rule_id") or "M-%02d" % k),
              "category": e.get("category") if e.get("category") in CATS else "logic",
              "facet": e.get("facet") if e.get("facet") in FACETS else "reporting",
              "defect_type": str(e.get("defect_type") or "consistency_cross_section"),
              "severity": e.get("severity") if e.get("severity") in SEV_ORDER else "minor",
              "evidence_strength": e.get("evidence_strength") if e.get("evidence_strength") in
              ("error", "gap", "judgment") else "judgment",
              "title": str(e.get("title") or "stage 2 judged finding")[:80],
              "locator": hit.get("locator") or str(e.get("locator") or ""), "quote": q,
              "reason": str(e.get("reason") or ""), "suggestion": str(e.get("suggestion") or ""),
              "evidence": e.get("evidence") if isinstance(e.get("evidence"), dict) else
              {"kind": "contrast", "support": "stage 2 judgement"},
              "confidence": e.get("confidence", .65), "source_id": hit.get("source_id") or c.primary}
        if hit.get("ok"):
            issues.append(it)
            n += 1
        else:
            pend.append({"item": "stage2 %s %s" % (it["rule_id"], it["title"]),
                         "why": "quote not found verbatim in source", "action": "re-quote it verbatim"})
    return issues, n, ""


def summarize(res):
    iss = res.get("issues", [])
    res["summary"] = {"total_issues": len(iss),
                      "by_severity": {k: sum(1 for i in iss if i.get("severity") == k) for k in SEV_ORDER},
                      "by_category": {k: sum(1 for i in iss if i.get("category") == k) for k in CATS},
                      "facet_coverage": {f: "covered" if any(i.get("facet") == f for i in iss) else "partial" for f in FACETS},
                      "blockers": [i["id"] for i in iss if i.get("severity") == "blocker"],
                      "quote_verified": sum(1 for i in iss if i.get("_quote_ok")),
                      "quote_failed": sum(1 for i in iss if i.get("_quote_ok") is False),
                      "reproducibility": "每条 issue 带 locator 与逐字 quote，可按报告 §7 独立复核"}

def render_csv(res):
    b = io.StringIO()
    cols = ["id", "rule_id", "category", "facet", "defect_type", "severity", "evidence_strength", "title",
            "locator", "quote", "reason", "suggestion", "confidence", "source_id"]
    w = csv.writer(b, lineterminator="\n")
    w.writerow(cols)
    for i in res.get("issues", []):
        w.writerow(["; ".join(map(str, i.get(c))) if isinstance(i.get(c), (list, tuple))
                    else ("" if i.get(c) is None else str(i.get(c))) for c in cols])
    return b.getvalue()


def render_md(res):
    s, chk, iss = res.get("summary", {}), res.get("checks") or {}, res.get("issues", [])
    bs, fc = s.get("by_severity", {}), s.get("facet_coverage", {})
    L = ["# 研究方法与统计审查报告\n",
         "| case_id | 状态 | 问题数 | blocker/major/minor/suggestion | quote 核验 |", "|-|-|-|-|-|",
         "| `%s` | `%s` | %d | %d/%d/%d/%d | 通过 %d、失败 %d |"
         % (res.get("case_id"), res.get("status"), s.get("total_issues", 0), bs.get("blocker", 0), bs.get("major", 0),
            bs.get("minor", 0), bs.get("suggestion", 0), s.get("quote_verified", 0), s.get("quote_failed", 0)),
         "\n> methods-stats-review %s。每条意见带 locator 与逐字 quote；quote 未能在原文逐字命中的意见不进入正文。\n" % VERSION,
         "## 1 检查面覆盖\n",
         "五面：%s\n" % "；".join("%s=%s" % (FCN[f], fc.get(f, "-")) for f in FACETS),
         "| 六类 | 状态 | 条目 | 范围 |", "|-|-|-|-|"]
    for cat in CATS:
        e = chk.get(cat) or {}
        L.append("| %s `%s` | %s | %d | %s |" % (CN[cat], cat, e.get("status", "-"),
                                                 len(e.get("items") or []), str(e.get("scope", ""))[:58]))
    L.append("\n## 2 阻断性与重大问题\n")
    hi = [i for i in iss if i.get("severity") in ("blocker", "major")]
    if not hi:
        L.append("_未发现阻断性/重大问题。_\n")
    for i in hi:
        ev = i.get("evidence") or {}
        L += ["### %s [%s] %s\n" % (i.get("id"), i.get("severity"), i.get("title")),
              "- 归类 `%s`（%s）｜面 `%s`｜类型 `%s`｜证据强度 `%s`｜置信度 %s"
              % (i.get("category"), CN.get(i.get("category"), ""), i.get("facet"), i.get("defect_type"),
                 i.get("evidence_strength"), i.get("confidence")),
              "- 定位：`%s`" % i.get("locator"),
              "- 原文：\n\n  > %s\n" % str(i.get("quote", "")).replace("\n", " "),
              "- 依据：%s" % i.get("reason"),
              "- 证据（%s）：%s" % (ev.get("kind", "-"), ev.get("support", "")),
              "- 修改建议：%s" % i.get("suggestion")]
        if i.get("merged_locators"):
            L.append("- 同类其他位置：%s" % ", ".join(i["merged_locators"]))
        L.append("")
    L.append("## 3 次要问题与建议\n")
    lo = [i for i in iss if i.get("severity") in ("minor", "suggestion")]
    for i in lo:
        L.append("- `%s`［%s／%s］`%s` %s（%s）→ 建议：%s"
                 % (i.get("id"), i.get("severity"), i.get("category"), i.get("locator"), i.get("title"),
                    i.get("evidence_strength"), i.get("suggestion")))
    if not lo:
        L.append("_无。_")
    L.append("\n## 4 六类检查记录\n")
    for cat in CATS:
        e = chk.get(cat) or {}
        L.append("- %s：%s；发现 %s；未决 %s" % (CN[cat], e.get("status", "-"),
                 ", ".join(e.get("findings") or []) or "—", ", ".join(e.get("open") or []) or "—"))
    man = [x["rule_id"] for cat in CATS for x in (chk.get(cat) or {}).get("items") or [] if x.get("status") == "manual"]
    if man:
        L.append("\n待阶段 2 人工判定的条目：%s" % ", ".join("`%s`" % m for m in man))
    L.append("\n## 5 待复核与不确定性\n")
    ph, unc = res.get("pending_human") or [], res.get("uncertainty") or []
    for p in ph:
        L.append("- 待复核：%s（原因：%s；动作：%s）" % (p.get("item"), p.get("why"), p.get("action")))
    for u in unc:
        L.append("- 不确定性：%s（原因：%s；影响：%s；解除：%s）"
                 % (u.get("what"), u.get("why"), u.get("impact"), u.get("resolved_by")))
    if not ph and not unc:
        L.append("_无未决项。_")
    L.append("\n## 6 限制与降级\n")
    for d in (res.get("degradations") or []) + (res.get("errors") or []) or ["无"]:
        L.append("- %s" % (d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)))
    L += ["\n## 7 第三方复核步骤\n", "1. 取 `issues.csv` 任一 `id`，按 `locator` 定位源文档。",
          "2. 逐字检索 `quote`（空白归一化）确认原句存在；`absence` 类用 `evidence.support` 的检索词复核全文无命中。",
          "3. `numerical`/`contrast` 类核对并列的两处原文或数值；重跑 `main.py --run` 后编号应一致。"]
    return "\n".join(L)

def extras(outdir, docs, man):
    """Per-document text with locator markers (stage 2 reading) plus the manual checklist."""
    out = Path(outdir)
    ex = out / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    for d in docs:
        (ex / (d["id"] + ".md")).write_text("\n".join(
            ["# %s (%s, %s)" % (d["path"], d["kind"], d["parser"]), ""] +
            ["%s\t[%s]\t%s" % (p["locator"], p["section"] or "-", p["text"]) for p in d["paras"]]), encoding="utf-8")
    if man:
        (out / "manual_checks_template.md").write_text("\n".join(
            ["# stage 2 manual checklist (workflow aid, not a case result)", "",
             "读 output/extracted/*.md 逐条判定；quote 须逐字复制，勿改写或跨句拼接。", ""] +
            ["- [ ] `%s` %s" % (i["rule_id"], i["note"]) for i in man] +
            ["", "然后：`python3 main.py --merge output/issues_model.json --run`"]),
            encoding="utf-8")


def finalize(res, docs, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    res.pop("_facet_records", None)
    summarize(res)
    for i in res.get("issues", []):
        i.pop("_quote_ok", None)
    res.setdefault("review_records", {})
    res["review_records"]["documents"] = [{"id": d.get("id"), "path": d.get("path"), "kind": d.get("kind"),
                                           "parser": d.get("parser"), "chars": d.get("chars", 0),
                                           "paragraphs": len(d.get("paras", []))} for d in docs]
    res["artifacts"] = {"result": "result.json", "review_report": "review_report.md", "issues_csv": "issues.csv"}
    write_json(outdir / "result.json", res)
    (outdir / "review_report.md").write_text(render_md(res), encoding="utf-8")
    (outdir / "issues.csv").write_text(render_csv(res), encoding="utf-8")
    return res


