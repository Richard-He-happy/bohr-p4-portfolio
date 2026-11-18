"""Extraction, segmentation, checks, artifact emission (stdlib only, offline)."""
import csv, json, re, shutil, subprocess, zipfile, zlib
from pathlib import Path

CITE = re.compile(r"\[\s*\d+(?:\s*[,;–—-]\s*\d+)*\s*\]"
                  r"|\(\s*[A-Z][A-Za-z'’-]+(?:\s+(?:et al|and|&)[^)]{0,40})?,?\s*(?:19|20)\d{2}[a-z]?\s*\)"
                  r"")
XREF = re.compile(r"\b(?:Figs?|Figures?|Tables?|Schemes?|Eqs?|Equations?|Sections?|Secs?|"
                  r"Supplementary\s+(?:Fig|Table|Data|Information)|SD)\s*\.?\s*S?\d+[A-Za-z]?")
NUM = re.compile(r"(?<![\w.])[-+−]?\d+(?:[.,]\d+)*(?:\s*[%‰])?")
UNIT = re.compile(r"\b(?:mg|kg|ng|g|mL|ml|L|µL|μL|nm|µm|μm|mm|cm|mM|µM|μM|nM|mol|mmol|nmol|"
                  r"Da|kDa|bp|kb|Hz|kHz|MHz|eV|keV|mV|mA|rpm|°C|min|ms|ns|h|d|yr|IU|CFU|OD)\b")
FORM = re.compile(r"\$[^$\n]{1,200}\$|\\\([^)\n]{1,120}\\\)"
                  r"|[A-Za-z][A-Za-z0-9]*[_^]\{[^}\n]{1,40}\}|(?<![\w.])[A-Za-z]\s*=\s*[^,;.\n]{1,50}")
NEG_EN = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot|fail(?:ed|s|ure)?|"
                    r"lack(?:s|ed)?|absent|excluded?|unable|unlikely|insignificant)\b|n't\b", re.I)
NEG_ZH = re.compile(r"未|不|无|非|没有|无法|并非|缺乏|排除|阴性|不能|不会|不是|尚未")
CAP = re.compile(r"^(?:Fig(?:ure)?|Table|Scheme|Box|Chart|Extended Data Fig(?:ure)?)\s*\.?\s*S?\d+", re.I)
HEADW = (r"^(abstract|introduction|background|materials? and methods?|methods?|results?|discussion|"
         r"conclusions?|references|bibliography|literature cited|acknowledg\w*|supplementary\w*|"
         r"appendix|摘要|引言|方法|结果|讨论|结论|参考文献)$")
_STOK = re.compile(rb"\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]{2,}>|\bT[dD]\b|\bT\*|\bET\b")
KINDS = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".doc": "doc_legacy", ".xls": "xls",
         ".pptx": "pptx", ".csv": "csv", ".json": "json", ".md": "text", ".txt": "text",
         ".tex": "text", ".html": "html", ".png": "image", ".jpg": "image", ".tif": "image"}
STOPA = {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "NOT", "ARE", "WAS", "ALL", "ET", "AL"}
STOPW = {"the", "a", "an", "of", "in", "and", "or", "with", "for", "to", "on", "by", "as", "at",
         "is", "are", "was", "were", "be", "this", "these", "we", "our", "it", "its", "from", "that",
         "which", "such", "can", "may", "not", "no", "also", "both", "per", "using"}
ABBR = {"et al", "e.g", "i.e", "fig", "figs", "eq", "eqs", "vs", "no", "nos", "approx", "cf", "ref",
        "refs", "dr", "prof", "resp", "suppl", "tab", "sec", "al", "min", "max"}


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def squash(s):
    s = (s or "").replace("\u00a0", " ")
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s)
    s = s.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", "", s)


def toks(text):
    """受保护标记：公式/引用/图表编号/数字/单位"""
    t = text or ""
    form = list(dict.fromkeys(FORM.findall(t)))
    t = FORM.sub(" ", t)
    cite = list(dict.fromkeys(CITE.findall(t)))
    t = CITE.sub(" ", t)
    xref = list(dict.fromkeys(XREF.findall(t)))
    t = XREF.sub(" ", t)
    return {"formulas": form, "citations": cite, "xrefs": xref,
            "numbers": list(dict.fromkeys(NUM.findall(t))), "units": list(dict.fromkeys(UNIT.findall(t)))}


def term_hit(term, text):
    if not term:
        return False
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text or "", re.I) is not None


def sentences(text):
    text, out, start = text or "", [], 0
    for m in re.finditer(r"([.!?])[\"'\u201d\u2019)]*\s+(?=[\"'(\[]?[A-Z0-9\u4e00-\u9fff])", text):
        tail = (re.split(r"[^A-Za-z.]", text[start:m.start()])[-1] or "").lower().strip(".")
        if tail in ABBR or len(tail) <= 1:
            continue
        out.append((start, m.end(1)))
        start = m.end(1)
    out += [(start, len(text))] if start < len(text) else []
    return [sp for sp in out if sp[1] > sp[0]]


def sent(text, needle=None):
    ss = [text[a:b].strip() for a, b in sentences(text)] or [text.strip()]
    return next((s for s in ss if needle and squash(needle) in squash(s)), ss[0])


def check_seg(src, tr, locked=None):
    """单段机械校验：标记保真 + 术语一致 + 否定线索"""
    locked, trs = locked or {}, squash(tr)
    detail, exp, kept = {}, 0, 0
    for kind, vals in toks(src).items():
        bad = [v for v in vals if squash(v) not in trs]
        exp += len(vals)
        kept += len(vals) - len(bad)
        if bad:
            detail[kind] = bad
    opp = [t for t in locked if term_hit(t, src)]
    viol = [t for t in opp if squash(locked[t]) not in trs]
    ns = len(NEG_EN.findall(src)) + len(NEG_ZH.findall(src))
    nt = len(NEG_ZH.findall(tr)) + len(NEG_EN.findall(tr))
    flags = (["token_missing"] if exp - kept else []) + (["glossary_inconsistent"] if viol else []) \
        + (["negation_dropped"] if ns and not nt else [])
    return {"exp": exp, "kept": kept, "miss": detail, "rate": round(kept / exp, 4) if exp else 1.0,
            "gopp": len(opp), "gviol": viol, "flags": flags}


def quote_status(q, src_norm):
    q = norm(q)
    if len(q) < 8:
        return "too_short"
    if q in src_norm:
        return "exact"
    return "casefold" if q.lower() in src_norm.lower() else "not_found"


def read_text(path):
    try:
        b = Path(path).read_bytes()
    except Exception:
        return ""
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", "ignore")


def jload(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def jsave(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path, header, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def read_csv(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def usable(t):
    good = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", t or ""))
    return good >= 200 and good / max(1, len(t or "")) > 0.5


def _pdfstr(b):
    b = b.replace(b"\\n", b"\n").replace(b"\\r", b"\r").replace(b"\\t", b"\t")
    b = re.sub(rb"\\([()\\])", rb"\1", b)
    b = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), b)
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "ignore")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("latin-1", "ignore")


def _streams(data):
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        e = data.find(b"endstream", m.end())
        if e > 0:
            for f in (zlib.decompress, lambda x: zlib.decompressobj(-15).decompress(x)):
                try:
                    out.append(f(data[m.end():e]))
                    break
                except Exception:
                    pass
    return out


def _stext(dec):
    parts = []
    for m in _STOK.finditer(dec):
        s = m.group(0)
        if s.startswith(b"("):
            parts.append(_pdfstr(s[1:-1]))
        elif s.startswith(b"<"):
            h = re.sub(rb"\s", b"", s[1:-1])
            try:
                parts.append(bytes.fromhex(h.decode()).decode(
                    "utf-16-be" if len(h) % 4 == 0 else "latin-1", "ignore"))
            except Exception:
                pass
        else:
            parts.append("\n" if s in (b"T*", b"ET", b"Td", b"TD") else " ")
    return "".join(parts)


def pdf_text(p, warns):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, timeout=180)
            t = r.stdout.decode("utf-8", "ignore")
            if usable(t):
                return t, "pdftotext -layout"
            warns.append("pdftotext 输出过少")
        except Exception as e:
            warns.append("pdftotext 失败: %s" % e)
    else:
        warns.append("无 pdftotext，用内置扫描")
    try:
        t = "".join(_stext(d) for d in _streams(Path(p).read_bytes()))
    except Exception as e:
        warns.append("内置解析失败: %s" % e)
        t = ""
    if not usable(t):
        warns.append("文字层不可用（疑扫描件）：未编造原文，需人工/OCR 补录")
    return t, "stdlib-pdf-scan"


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore").replace("<w:tab/>", " ")
    out = [re.sub(r"<[^>]+>", "", "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S))).strip()
           for para in re.split(r"</w:p>", xml)]
    return "\n".join(x.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                     .replace("&quot;", '"').replace("&apos;", "'") for x in out if x)


def text_blocks(t):
    pages = [pg for pg in (t or "").split("\f") if pg.strip()]
    return [{"page": i, "text": pg} for i, pg in enumerate(pages, 1)] or [{"page": None, "text": t}]


def extract(path, kind, warns):
    path = Path(path)
    if kind == "pdf":
        t, m = pdf_text(path, warns)
        return text_blocks(t), m
    if kind == "docx":
        return [{"page": None, "text": docx_text(path)}], "zipfile-docx"
    if kind == "image":
        warns.append("图片无文字层：未 OCR")
        return [{"page": None, "text": ""}], "image-no-ocr"
    if kind in ("doc_legacy", "xls", "xlsx", "pptx"):
        warns.append("%s 需人工转换为 pdf/docx/txt" % kind)
        return [{"page": None, "text": ""}], "unsupported"
    t = read_text(path)
    if kind == "html":
        t = re.sub(r"<[^>]+>", " ", t)
    return [{"page": None, "text": t}], "text-read"


def join_lines(lines):
    out = ""
    for ln in [x.strip() for x in lines if x.strip()]:
        if not out:
            out = ln
        elif out.endswith("-") and len(out) > 2 and not out.endswith(" -") and ln[:1].islower():
            out = out[:-1] + ln
        else:
            out += " " + ln
    return re.sub(r"[ \t\u00a0]+", " ", out).strip()


def heading(s):
    if not s or len(s) > 110:
        return False
    core = re.sub(r"^#+\s*", "", s).strip()
    if re.match(r"#{1,4}\s+\S", s) or (re.match(HEADW, core.rstrip(":： "), re.I) and len(core) < 60):
        return True
    if re.match(r"^\d+(\.\d+){0,2}\.?\s+[A-Z\u4e00-\u9fff]", s) and len(s) < 90 \
            and len(s.split()) <= 10 and not s.endswith("."):
        return not re.match(r"^\d+(\.\d+)?\s*(mg|g|kg|mL|L|nm|mm|cm|mM|nM|%|°C|h|min|s)\b", s)
    return bool(s.isupper() and 4 <= len(s) <= 70 and re.search(r"[A-Z]{4}", s) and len(s.split()) <= 9)





def segment(blocks):
    """语义分段：标题/题注/公式/参考文献/正文；段号 P###"""
    items = [(b.get("page"), ln.rstrip()) for b in blocks for ln in (b.get("text") or "").split("\n")]
    units, buf, sec, refs, kind = [], [], None, False, "body"

    def flush():
        nonlocal buf, kind
        if buf:
            t = join_lines([x for _, x in buf])
            if t:
                units.append({"page": next((p for p, _ in buf if p is not None), None), "text": t,
                              "kind": kind, "section": sec})
        buf, kind = [], "body"

    for pg, ln in items:
        s = ln.strip()
        if not s:
            flush()
        elif heading(s):
            flush()
            sec = re.sub(r"^#+\s*", "", s).strip()
            units.append({"page": pg, "text": sec, "kind": "heading", "section": sec})
            refs = bool(re.match(r"^(references|bibliography|literature cited|参考文献)", sec, re.I))
        elif refs:
            flush()
            units.append({"page": pg, "text": s, "kind": "reference", "section": sec})
        elif CAP.match(s) and not buf:
            kind = "caption"
            buf.append((pg, s))
        elif len(s) < 120 and (re.match(r"^[(\[]?\d{1,3}[)\]]?$", s)
                               or (re.search(r"[=≈≤≥∑∫±√]", s) and len(s.split()) <= 10)):
            flush()
            buf, kind = [(pg, s)], "equation"
            flush()
        else:
            buf.append((pg, s))
    flush()
    out = []
    for u in units:
        tx = re.sub(r"[ \t\u00a0]+", " ", u["text"]).strip()
        if tx:
            u["text"] = tx
            out.append(u)
    for i, u in enumerate(out, 1):
        u["id"] = "P%03d" % i
        u["sents"] = [u["text"][a:b].strip() for a, b in sentences(u["text"])]
    return out


def build_glossary(text, segs, limit=60):
    """术语候选：缩写 + 高频二元组 + 全称(缩写)配对"""
    cnt = {}

    def bump(k):
        cnt[k] = cnt.get(k, 0) + 1

    for m in re.finditer(r"\b[A-Z][A-Za-z+/\-]{0,9}[A-Z]\b", text or ""):
        if 2 <= len(m.group(0)) <= 14 and m.group(0) not in STOPA:
            bump(m.group(0))
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text or "")
    for i in range(len(words) - 1):
        if words[i].lower() not in STOPW and words[i + 1].lower() not in STOPW:
            bump(words[i] + " " + words[i + 1])
    pairs = {}
    for m in re.finditer(r"([A-Z][a-z]+(?:[ \-][a-z]{2,}){0,4})\s*\(([A-Z]{2,8})\)", text or ""):
        pairs.setdefault(m.group(2), m.group(1).strip())
    cand = sorted([(t, c) for t, c in cnt.items() if (c >= 3 if " " in t else (c >= 2 or t in pairs))],
                  key=lambda x: (-x[1], x[0]))
    rows = []
    for t, c in cand[:limit]:
        loc = next(((s["id"], s["page"]) for s in segs if term_hit(t, s["text"])), ("", None))
        rows.append({"term": t, "translation": "", "category": "acronym" if " " not in t else "phrase",
                     "expansion": pairs.get(t, ""), "freq": c, "first_seg": loc[0],
                     "first_page": "" if loc[1] is None else loc[1], "status": "candidate"})
    return rows


def shp(n):
    """output_contract -> 同形空壳（保留全部键名）"""
    if isinstance(n, dict):
        return {str(k): shp(v) for k, v in n.items()}
    if isinstance(n, list):
        if n and all(isinstance(x, str) for x in n):
            return dict.fromkeys(n)
        return {(it.get("name") or it.get("field") or it.get("key")): shp(it.get("fields") or {})
                for it in n if isinstance(it, dict) and (it.get("name") or it.get("field") or it.get("key"))}
    return None


GM = [("translat", "translation"), ("译文", "translation"), ("glossar", "glossary"), ("术语", "glossary"),
      ("claim", "claims"), ("结论", "claims"), ("evidence", "evidence"), ("source", "sources"),
      ("cover", "coverage"), ("覆盖", "coverage"), ("uncertain", "uncertainty"), ("pending", "pending_human"),
      ("人工", "pending_human"), ("degrad", "degradations"), ("error", "errors"), ("change", "changes"),
      ("runtime", "runtime")]
def fillc(res):
    """契约字段名映射到已有结果；未知字段留空值，不删键不改名"""
    c = res.get("output_contract")
    if isinstance(c, dict):
        for k, dv in shp(c).items():
            if k not in res:
                v = next((res[s] for pat, s in GM if pat in k.lower() and s in res), None)
                res[k] = dv if v is None else v


def emit(c, res):
    """写双语稿/alignment.csv/glossary.csv；生成 claims 与 pending_human"""
    segs, tr = c["segs"], res["translation"]
    ps, cov = tr["paragraphs"], tr["coverage"]
    rate = tr["token_fidelity"].get("rate")
    lock = {r["term"]: r["translation"] for r in res["glossary"]["rows"]}
    sm = {s["id"]: s["text"] for s in segs}
    done = [p for p in ps if p["status"] == "translated"]
    md = ["# 双语对照译文",
          "- case `%s` | `%s`(%s) | 段 %d/译 %d/%.1f%% | 标记 %s | 术语 %d" % (
              res.get("case_id"), c["doc"].get("rel", "?"), c["doc"].get("method", "?"),
              cov["paragraphs"], cov["translated"], 100 * cov["coverage_rate"],
              "%.1f%%" % (100 * rate) if rate is not None else "NA", res["glossary"]["locked"]), "",
          "> P### 对应 work/segments.json；p.N 页码；未译段显式标注，不以摘要替代。", ""]
    for p in ps:
        md += ["### %s · %s · %s · %s" % (p["seg_id"], "none" if p["page"] is None else "p." + str(p["page"]),
                                          p["kind"], p["section"] or "-"),
               "原文: " + sm[p["seg_id"]],
               "译文: " + (p["translation"].replace("\n", " ") or
                          "【未译 untranslated】需按术语表与原文补译，不得以摘要替代。")
               + "  `标记 %d/%d · 术语 %d · %s`" % (p["kept"], p["expected"], p["terms"],
                                                  ";".join(p["flags"]) or "ok"), ""]
    (c["output"] / "translation_bilingual.md").write_text("\n".join(md), encoding="utf-8")
    write_csv(c["output"] / "alignment.csv",
              ["seg_id", "page", "kind", "status", "src_chars", "tr_chars", "ratio", "kept", "expected",
               "terms", "flags", "src_excerpt", "translation"],
              [[p["seg_id"], "" if p["page"] is None else p["page"], p["kind"], p["status"], p["src_chars"],
                len(p["translation"]), "" if p["ratio"] is None else p["ratio"], p["kept"], p["expected"],
                p["terms"], ";".join(p["flags"]) + (";" + ";".join(p["gviol"]) if p["gviol"] else ""),
                norm(p["src_excerpt"]),
                norm(p["translation"])] for p in ps])
    write_csv(c["output"] / "glossary.csv", ["term", "translation", "freq", "violation_seg_ids", "status"],
              [[r["term"], r["translation"], r["freq"], ";".join(r["violation_seg_ids"]), r["status"]]
               for r in res["glossary"]["rows"]])
    cl = []

    def add(kind, stmt, q, seg, page, cond):
        cl.append({"id": "C%03d" % (len(cl) + 1), "kind": kind, "statement": stmt, "condition": cond,
                   "readability": "directly_read", "source_id": "S1", "produced_by": "script",
                   "evidence": [{"quote": q, "source_id": "S1",
                                 "location": {"seg_id": seg, "page": page, "anchor": "paragraph",
                                              "pointer": "/translation/paragraphs/" + seg}}]})

    for p in [x for x in done if x["expected"]][:5]:
        add("translation_fidelity", "%s 译文保留 %d/%d 处数字·单位·公式·文献标记" % (
            p["seg_id"], p["kept"], p["expected"]), sent(sm[p["seg_id"]]), p["seg_id"], p["page"],
            "译文来自本次 translations 输入；去空白后逐字包含比对")
    for t, v in list(lock.items())[:4]:
        hits = [s for s in segs if term_hit(t, s["text"])]
        if hits:
            viol = [p["seg_id"] for p in done if t in p["gviol"]]
            add("terminology_consistency", "术语 %s→%s：原文 %d 段出现，违反 %d 段" % (t, v, len(hits), len(viol)),
                sent(hits[0]["text"], t), hits[0]["id"], hits[0]["page"],
                "译名取自 work/glossary.csv；违反=原文出现而译文未含该译名")
            cl[-1].update({"term": t, "target": v, "violation_seg_ids": viol})
    res["claims"] = cl
    un = [p["seg_id"] for p in ps if p["status"] == "untranslated"]
    if un:
        res["pending_human"].append({"id": "H1", "item": "%d 段未译：%s%s" % (
            len(un), ", ".join(un[:30]), " …" if len(un) > 30 else ""), "reason": "translations 缺这些段号",
            "action": "补译后重跑 finalize，或确认属不翻译内容"})
    for p in [x for x in ps if x["missing"]][:8]:
        res["pending_human"].append({"id": "H_tok_" + p["seg_id"], "item": "%s 缺 %s" % (p["seg_id"], p["missing"]),
                                     "reason": "译文未逐字保留原文标记", "action": "回填后重跑"})
    if not lock:
        res["pending_human"].append({"id": "H_gloss", "item": "术语表无锁定译名",
                                     "reason": "work/glossary.csv 的 translation 列为空",
                                     "action": "补译名后重跑（影响术语一致率）"})
