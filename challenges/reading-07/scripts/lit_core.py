"""lit_core.py - I/O and text primitives for literature evidence verification.

Stdlib only: reads the input tree (JSON/CSV/TXT/MD/DOCX/PDF/HTML), builds paragraph
units with locators, discovers claims, verifies quotes verbatim, renders cards.
"""

from __future__ import annotations

import csv, html, io, json, re, zipfile, zlib
from pathlib import Path

MAX_UNITS = 6000
SUPPORT_C, PARTIAL_C = 0.72, 0.40
TEXT_KEYS = ("text", "content", "paragraph", "para", "sentence", "body", "abstract",
             "caption", "quote", "chunk", "passage", "value")
ID_KEYS = ("paragraph_id", "para_id", "pid", "para", "id", "chunk_id", "unit_id")
SEC_KEYS = ("section", "section_title", "heading", "sec", "chapter")
PAGE_KEYS = ("page", "page_number", "p", "page_no", "pdf_page")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
EN_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\s?(?:%|‰|mg|kg|g|mm|cm|km|nm|μm|µm|ml|l|ms|min|h|s|k|pa|kpa|mpa|gpa|hz|khz|ghz|ev|kj|mol|mmol|°c|℃))?", re.I)
STOP_CHARS = set("的了和与及或在是对为把被而并且也等就都还又很更最则其之该此是我方可将能会从对向于以但与或如若虽因由于这那些个中上下")
EN_STOP = {"the", "and", "for", "with", "that", "this", "these", "those", "was", "were", "are",
           "have", "has", "had", "from", "not", "but", "than", "into", "there", "which", "while",
           "also", "such", "can", "may", "been", "being", "its", "they", "them", "however", "used"}
NEG_EXCL = ("不同", "不断", "不仅", "不少", "不但", "非但")
CUE = {
    "up": r"高于|更高|增大|增加|上升|提高|增强|促进|多于|超过|优于|higher|greater|larger|increas|enhanc|improve|promot|superior|more than|exceed",
    "down": r"低于|更低|减小|降低|降至|下降至|缩短|减弱|抑制|少于|劣于|lower|smaller|decreas|reduc|inhibit|less than|inferior|suppress|declin",
    "neg": r"不|未|没有|无法|并非|不能|not\b|no\b|did not|was not|were not|without|none\b|fail",
    "sig": r"显著|极显著|显著性|significant|significantly|p\s*[<=]\s*0?\.\d+|95%\s*ci|置信区间|confidence interval",
    "scope": r"所有|全部|任何|均|仅|只|总是|从不|普遍|every|all\b|only\b|always|never|exclusively|solely|universally",
    "compar": r"高于|低于|优于|劣于|大于|小于|相比|更高|更低|多于|少于|higher than|lower than|greater than|less than|compared (?:with|to)|versus|vs\.?|than\b|比",
    "causal": r"导致|引起|造成|因为|由于|因此|从而|使得|归因|驱动|决定|caus|lead(?:s|ing)? to|due to|result(?:s|ed)? in|because|attribut|driven by|responsible for|induced",
}
CUE_RE = {k: re.compile(v, re.I) for k, v in CUE.items()}
_WS = re.compile(r"[ \t\u3000\xa0]+")


def norm_ws(s):
    return _WS.sub(" ", str(s or "").replace("\r\n", "\n").replace("\r", "\n")).strip()


def flat(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def terms(text, cap=48):
    out, seen = [], set()
    for run in CJK_RUN.findall(str(text or "")):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg[0] in STOP_CHARS or bg[1] in STOP_CHARS or bg in seen:
                continue
            seen.add(bg)
            out.append(bg)
    for w in EN_WORD.findall(str(text or "")):
        lw = w.lower()
        if lw not in EN_STOP and lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:cap]


def numbers(text):
    out, seen = [], set()
    for m in NUM_RE.finditer(str(text or "")):
        v = m.group(0).replace(" ", "").lower()
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


ANCHOR = re.compile(r"[a-z]{1,2}\d{3,4}(?!\d)|\b\d{4}(?!\d)|\d+(?:[.,]\d+)?\s?(?:°c|℃|%|mpa|gpa|mm|nm|μm|kg|g|h)\b", re.I)


def anchors(text):
    """Discriminative anchors: model codes (6061, AA5052) and quoted quantity+unit."""
    return [a.replace(" ", "").lower() for a in ANCHOR.findall(str(text or ""))]


def cue(kind, text):
    return [m.group(0) for m in CUE_RE[kind].finditer(str(text or ""))]


def has_neg(text):
    t = str(text or "")
    for ex in NEG_EXCL:
        t = t.replace(ex, "  ")
    return bool(cue("neg", t))


def direction(text):
    up, down = cue("up", text), cue("down", text)
    return "mixed" if (up and down) else ("up" if up else ("down" if down else "none"))


# ------------------------------------------------------------------ document readers
def read_text_file(path):
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return Path(path).read_text(encoding=enc)
        except Exception:
            continue
    return ""


def read_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            chunks = []
            for n in z.namelist():
                if re.match(r"word/(document|footnotes|endnotes)\d*\.xml$", n):
                    raw = z.read(n).decode("utf-8", "ignore")
                    raw = re.sub(r"<w:tab[^>]*/>", "\t", re.sub(r"</w:p>", "\n\n", raw))
                    chunks.append(html.unescape(re.sub(r"<[^>]+>", "", raw)))
            return "\n".join(chunks)
    except Exception:
        return ""


def _pdf_strings(blob):
    out = []
    esc = {b"n": b" ", b"r": b" ", b"t": b" ", b"b": b"", b"f": b"", b"(": b"(", b")": b")", b"\\": b"\\"}
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|\bTJ\b|\bTj\b|\bTd\b|\bTD\b|\bT\*", blob, re.S):
        tok = m.group(0)
        if tok in (b"Td", b"TD", b"T*"):
            out.append("\n")
        elif tok.startswith(b"("):
            s = re.sub(rb"\\([nrtbf()\\])", lambda x: esc.get(x.group(1), x.group(1)), tok[1:-1])
            out.append(s.decode("latin-1", "ignore"))
    return "".join(out)


def read_pdf(path):
    """Return (text, note). Prefer pdftotext / pypdf / PyPDF2, else scan content streams."""
    import shutil
    import subprocess
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, timeout=120)
            if r.returncode == 0 and len(r.stdout) > 200:
                return r.stdout.decode("utf-8", "ignore"), ""
        except Exception:
            pass
    for mod in ("pypdf", "PyPDF2"):
        try:
            m = __import__(mod)
            txt = "\n".join((pg.extract_text() or "") for pg in m.PdfReader(str(path)).pages)
            if len(txt) > 200:
                return txt, ""
        except Exception:
            continue
    try:
        data, parts = Path(path).read_bytes(), []
        for m in re.finditer(rb"stream\r?\n", data):
            end = data.find(b"endstream", m.end())
            if end < 0:
                continue
            raw = data[m.end():end]
            try:
                dec = zlib.decompress(raw)
            except Exception:
                dec = raw
            if b"Tj" in dec or b"TJ" in dec:
                parts.append(_pdf_strings(dec))
        txt = "\n".join(parts)
        bad = txt.count("\ufffd") > 40 or (len(txt) > 400 and not CJK_RUN.search(txt) and txt.count(" ") > len(txt) * .25)
        return txt, ("low_quality_text_layer: CID encoding, quotes need re-check" if bad else "")
    except Exception:
        return "", "pdf_read_failed"


# ------------------------------------------------------------------ corpus units
def make_unit(source_id, text, unit_id, section, page, locator):
    loc = dict(locator)
    loc["unit_id"] = str(unit_id)
    if section:
        loc["section"] = str(section)
    if page not in (None, ""):
        try:
            loc["page"] = int(page)
        except Exception:
            loc["page_label"] = str(page)
    return {"source_id": str(source_id), "unit_id": str(unit_id), "text": norm_ws(text),
            "section": str(section) if section else None, "page": loc.get("page"), "locator": loc}


def unit_label(u):
    bits = [u["source_id"]]
    if u.get("section"):
        bits.append("sec:" + str(u["section"])[:40])
    if u.get("page") is not None:
        bits.append("p.%s" % u["page"])
    return " | ".join(bits + ["unit:" + str(u["unit_id"])])


def json_units(obj, source_id, pointer="", out=None, page=None, section=None):
    out = [] if out is None else out
    if len(out) >= MAX_UNITS:
        return out
    if isinstance(obj, dict):
        txt = next((obj[k] for k in TEXT_KEYS if isinstance(obj.get(k), str) and len(obj[k].strip()) >= 25), None)
        pg = next((obj[k] for k in PAGE_KEYS if obj.get(k) not in (None, "")), page)
        sec = next((obj[k] for k in SEC_KEYS if isinstance(obj.get(k), str) and obj[k].strip()), section)
        if txt:
            uid = next((str(obj[k]) for k in ID_KEYS if isinstance(obj.get(k), (str, int))), None)
            ptr = pointer + "/" + (uid or str(len(out)))
            out.append(make_unit(source_id, txt, uid or ptr.strip("/").replace("/", "."), sec, pg,
                                 {"type": "json", "json_pointer": ptr}))
            return out
        for k, v in obj.items():
            json_units(v, source_id, pointer + "/" + str(k), out, pg, sec)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            json_units(v, source_id, pointer + "/" + str(i), out, page, section)
    elif isinstance(obj, str) and len(obj) >= 400:
        out.append(make_unit(source_id, obj, pointer.strip("/").replace("/", ".") or "text",
                             section, page, {"type": "json", "json_pointer": pointer}))
    return out


def text_to_units(text, source_id, kind="text"):
    units = []
    for b in (norm_ws(x) for x in re.split(r"\n\s*\n", text or "")):
        if not b:
            continue
        if len(b) > 1600:                      # long block -> sentence-group chunks
            sents, step = split_sentences(b), 6
            for i in range(0, len(sents), step):
                chunk = b[sents[i][0]: sents[min(i + step, len(sents)) - 1][1]]
                if chunk.strip():
                    n = len(units) + 1
                    units.append(make_unit(source_id, chunk, "B%02d" % n, None, None, {"type": kind, "block": n}))
        else:
            n = len(units) + 1
            units.append(make_unit(source_id, b, "B%02d" % n, None, None, {"type": kind, "block": n}))
        if len(units) >= MAX_UNITS:
            break
    return units


def load_corpus(input_dir, skip=()):
    """Walk the input tree; one unreadable file degrades only itself."""
    units, sources, degr, gaps = [], [], [], []
    root = Path(input_dir)
    skip = {str(Path(s).resolve()) for s in skip}
    files = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")) if root.exists() else []
    for p in files:
        if str(p.resolve()) in skip:
            continue
        ext, sid = p.suffix.lower(), p.stem
        try:
            if ext == ".json":
                try:
                    got = json_units(json.loads(read_text_file(p) or "null"), sid)
                except Exception:
                    degr.append({"stage": "corpus", "file": p.name, "issue": "json_parse_failed"})
                    continue
                if got:
                    units += got
                    sources.append({"source_id": sid, "path": str(p), "format": "json", "units": len(got)})
                else:
                    gaps.append({"gap": "json_without_text_fields", "file": p.name})
                continue
            if ext == ".csv":
                rows = list(csv.reader(io.StringIO(read_text_file(p))))[:MAX_UNITS]
                got = [make_unit(sid, " | ".join(c.strip() for c in row if c.strip()), "R%03d" % (i + 1),
                                 None, None, {"type": "csv", "row": i + 1})
                       for i, row in enumerate(rows) if len(" | ".join(row)) >= 25]
                if got:
                    units += got
                    sources.append({"source_id": sid, "path": str(p), "format": "csv", "units": len(got)})
                continue
            if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"):
                sources.append({"source_id": sid, "path": str(p), "format": "image", "units": 0,
                                "note": "figure pixels not machine-readable here"})
                gaps.append({"gap": "figure_pixels_not_read", "file": p.name})
                continue
            if ext in (".xlsx", ".xlsm"):
                degr.append({"stage": "corpus", "file": p.name, "issue": "xlsx_not_parsed_stdlib"})
                gaps.append({"gap": "xlsx_not_parsed", "file": p.name})
                continue
            note, fmt = "", {".docx": "docx", ".pdf": "pdf", ".html": "html", ".htm": "html"}.get(ext, "text")
            if fmt == "docx":
                txt = read_docx(p)
            elif fmt == "pdf":
                txt, note = read_pdf(p)
            elif fmt == "html":
                t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", read_text_file(p), flags=re.S | re.I)
                txt = html.unescape(re.sub(r"<[^>]+>", "\n", t))
            elif ext in (".txt", ".md", ".markdown", ".rst", ".tex", ".srt", ".log", ""):
                txt = read_text_file(p)
            else:
                gaps.append({"gap": "unsupported_file_type", "file": p.name})
                continue
            if note == "pdf_read_failed" or len(txt.strip()) < 20:
                issue = "pdf_no_text_layer" if fmt == "pdf" else "no_extractable_text"
                degr.append({"stage": "corpus", "file": p.name, "issue": issue,
                             "detail": "no readable text; needs OCR or manual page reading"})
                gaps.append({"gap": issue, "file": p.name})
                continue
            if note:
                degr.append({"stage": "corpus", "file": p.name, "issue": note})
            got = text_to_units(txt, sid, fmt)
            units += got
            sources.append({"source_id": sid, "path": str(p), "format": fmt, "units": len(got)})
        except Exception as exc:
            degr.append({"stage": "corpus", "file": p.name, "issue": "unhandled",
                         "detail": "%s: %s" % (type(exc).__name__, exc)})
    return units[:MAX_UNITS], sources, degr, gaps


# ------------------------------------------------------------------ sentences
_SENT = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def split_sentences(text):
    text, out = text or "", []
    for m in _SENT.finditer(text):
        s, e = m.start(), m.end()
        while s < e and text[s] in " \t，,":
            s += 1
        if e - s >= 2:
            out.append((s, e))
    return out or [(0, len(text))]


def windows(unit, spans=(1, 2)):
    sents = unit["sentences"]
    for span in spans:
        if span > len(sents):
            continue
        for i in range(0, len(sents) - span + 1):
            yield {"unit": unit, "text": unit["text"][sents[i][0]: sents[i + span - 1][1]]}


def verify_quote(quote, units, min_len=8):
    q = flat(quote)
    if len(q) < min_len:
        return None
    for u in units:
        if q in flat(u["text"]):
            return u
    return None


# ------------------------------------------------------------------ claims discovery
def load_claims(input_dir, case=None):
    """Discover claims. Every claim is a QUESTION to verify, never a fact to copy."""
    root, found, origin, gaps = Path(input_dir), None, None, []
    for name in ("claims-to-verify.json", "claims_to_verify.json", "claims.json"):
        p = root / name
        if p.exists():
            try:
                found, origin = json.loads(read_text_file(p) or "null"), str(p)
                break
            except Exception:
                gaps.append({"gap": "claims_json_parse_failed", "file": name})
    if not found and isinstance(case, dict):
        for k in ("claims", "claims_to_verify", "statements", "claims_to_check", "claim_list", "audit_claims"):
            if isinstance(case.get(k), (list, dict)):
                found, origin = case[k], "case.json::%s" % k
                break
    if not found and isinstance(case, dict):
        sub = case.get("input") if isinstance(case.get("input"), dict) else {}
        for k in ("claims", "claims_to_verify", "statements"):
            if isinstance(sub.get(k), (list, dict)):
                found, origin = sub[k], "case.json::input.%s" % k
                break
    if isinstance(found, dict):
        inner = next((found[k] for k in ("claims", "items", "records", "data") if isinstance(found.get(k), list)), None)
        found = inner if inner is not None else ([found] if found else [])
    out = []
    for i, item in enumerate(found or []):
        cid, text, extra = None, None, {}
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            cid = next((str(item[k]) for k in ("claim_id", "cid", "id", "claim_no", "no") if item.get(k) not in (None, "")), None)
            text = next((item[k] for k in ("claim_text", "text", "statement", "claim", "sentence", "quote", "content")
                         if isinstance(item.get(k), str) and item[k].strip()), None)
            extra = {k: v for k, v in item.items() if k not in ("claim_text", "text", "statement", "claim", "sentence")}
        if text and str(text).strip():
            out.append({"claim_id": cid or "C%d" % (i + 1), "claim_text": norm_ws(text),
                        "meta": extra, "input_index": i})
    return out, origin, gaps


# ------------------------------------------------------------------ aggregation / renderers
def aggregate(subs):
    vs = [s["verdict"] for s in subs]
    if not vs:
        return "insufficient_evidence"
    if any(s.get("alternative") for s in subs):
        return "partially_supported"
    if "contradicted" in vs:
        return "contradicted" if "supported" not in vs else "partially_supported"
    if all(v == "supported" for v in vs):
        return "supported"
    return "insufficient_evidence" if all(v == "insufficient_evidence" for v in vs) else "partially_supported"


def conflict_of(subs):
    for s in subs:
        a = s.get("alternative")
        if not a:
            continue
        m, w = (s["evidence"][0] if s["evidence"] else {}), a.get("win") or {}
        u = w.get("unit") or {}
        return {"conflict": True, "sub_id": s["sub_id"], "qualified_verdict": s["verdict"],
                "both_sides": [{"side": "A", "source_id": m.get("source_id"), "location": m.get("locator"),
                                "quote": m.get("quote")},
                               {"side": "B", "source_id": u.get("source_id") or a.get("source_id"),
                                "location": dict(u["locator"]) if u else a.get("locator"),
                                "quote": w.get("text") or a.get("quote")}],
                "note": "两侧定位并列，未折中；条件差异需人工确认"}
    return {"conflict": False, "both_sides": []}


def card_lines(vers):
    keys = ("source_id", "unit_id", "locator", "label", "quote", "supports", "role")
    return [json.dumps(dict({
        "card_id": "EV-%s-%s" % (v["claim_id"], s["sub_id"]), "claim_id": v["claim_id"], "claim_text": v["claim_text"],
        "sub_text": s["text"], "type": s["type"], "required_evidence_type": s["required_evidence_type"],
        "verdict": s["verdict"], "verdict_confidence": s["verdict_confidence"], "comparator": s["comparator"],
        "negation": s["negation"], "significance": s["significance"], "conditions": s["conditions"],
        "evidence": [{k: e.get(k) for k in keys} for e in s["evidence"]], "rationale": s["rationale"],
        "limitations": s["limitations"], "counter_evidence_searched": s["counter_evidence_searched"],
        "search_scope": s["search_scope"], "conflict": bool(s.get("alternative"))}, sub_id=s["sub_id"]), ensure_ascii=False)
        for v in vers for s in v["sub_claims"]]
