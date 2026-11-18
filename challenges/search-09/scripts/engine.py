#!/usr/bin/env python3
"""engine.py - 解析与评价引擎（纯函数，仅 Python 标准库）。被 appraise.py 导入。"""
import json, re, shutil, subprocess, zipfile, zlib
from pathlib import Path

NOTES = {k: [] for k in ("errors", "degradations", "uncertainty", "pending_human")}
STOP = set("the a an of and or in on for to with by from as at is are was were be been this that these those "
           "study studies paper article results we our its their between among used".split())
TITLE_K = {"title", "papertitle", "documenttitle", "articletitle", "题名", "标题"}
DOI_K = {"doi", "digitalobjectidentifier"}
AB_K = {"abstract", "abstracttext", "summary", "摘要"}
AU_K = {"author", "authors", "authorstring", "creator", "作者"}
YR_K = {"year", "pubyear", "publicationyear", "issued", "published", "date", "firstpublicationdate", "年份"}
VN_K = {"venue", "journal", "journaltitle", "containertitle", "期刊", "source"}
URL_K = {"url", "link", "linkurl", "fulltexturl", "href"}
TS_K = {"retrievedat", "retrieved", "timestamp", "ts", "accessed", "dateaccessed", "created", "inserted"}
QID_K = {"queryid", "qid", "query"}
DB_K = {"db", "database", "sourcedb", "provider", "index", "source"}
PTS = {"明确存在": 2.0, "可能存在": 1.0, "未见迹象": 0.0, "证据不足": 0.5}
DOMAINS = [("selection", ["D1.3", "D1.4", "D1.5", "D1.6"], {"systematic_review": ["T.sr.1"]}),
           ("confounding", ["D2.4", "D1.6"], {}),
           ("performance", ["T.rct.1", "T.rct.2", "T.rct.3"], {}),
           ("detection", ["D2.1", "T.rct.3", "T.dta.1"], {}),
           ("attrition", ["D1.7", "D4.1"], {}),
           ("reporting", ["D2.6", "D4.3"], {"systematic_review": ["T.sr.4", "T.sr.3"]})]
DESIGN_PAT = [("systematic_review", ["systematic review", "meta-analysis", "meta analysis", "pooled analysis",
                                     "we searched pubmed", "prisma", "prospero"]),
              ("rct", ["randomized controlled trial", "randomised controlled trial", "randomly assigned",
                       "double-blind", "placebo-controlled"]),
              ("diagnostic", ["sensitivity and specificity", "diagnostic accuracy", "index test",
                              "reference standard"]),
              ("prediction", ["prediction model", "predictive model", "risk score", "nomogram",
                              "c-statistic", "calibration"]),
              ("qualitative", ["qualitative study", "semi-structured interviews", "thematic analysis"]),
              ("cohort", ["cohort study", "prospective cohort", "retrospective cohort", "person-years"]),
              ("case_control", ["case-control", "case control", "matched controls", "nested case"]),
              ("cross_sectional", ["cross-sectional", "cross sectional", "survey", "prevalence"])]
SECRE = re.compile(r"(?i)^\s*(abstract|introduction|background|methods|materials and methods|patients and "
                   r"methods|subjects and methods|results|discussion|"
                   r"conclusions?|limitations?|funding|conflicts? of interest|competing interests|"
                   r"data availability|references)\s*[:.]?\s*$")
PAGED = re.compile(r"[^.!?\n]{20,600}[.!?](?=\s|$)|^[^\n]{20,300}$", re.M)


def note(k, m):
    if m not in NOTES.setdefault(k, []):
        NOTES[k].append(m)


def nk(k):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(k).lower())


def norm(s):
    s = str(s).replace("\u00a0", " ").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"[ \t]+", " ", re.sub(r"[\u2010-\u2014]", "-", s)).strip()


def flat(v):
    if isinstance(v, list):
        return "; ".join(x for x in (flat(i) for i in v) if x)
    if isinstance(v, dict):
        return next((str(v[k]) for k in ("family", "value", "name", "text") if k in v), "")
    return "" if v is None else str(v)


def num(v, lo=1800, hi=2100):
    return next((int(x) for x in re.findall(r"\d{4}", str(v)) if lo <= int(x) <= hi), None)


def pick(d, keys):
    for k, v in d.items():
        if nk(k) in keys and v not in (None, "", [], {}):
            return v
    return None


# ------------------------------------------------------------------ file -> text
def unesc(s):
    def r(m):
        c = m.group(1)
        return {"n": "\n", "r": "", "t": "\t", "b": "", "f": ""}.get(c, chr(int(c, 8)) if c[0] in "01234567" else c)
    return re.sub(r"\\([0-7]{1,3}|.)", r, s)


def content_text(b):
    out = []
    for m in re.finditer(r"\((?:[^()\\]|\\.)*\)|T\*|Td|TD|'|\"|TJ|Tj", b.decode("latin-1", "replace")):
        t = m.group(0)
        if t.startswith("("):
            out.append(unesc(t[1:-1]))
        elif t in ("T*", "Td", "TD", "'"):
            out.append(" ")
    return "".join(out)


def builtin_pdf(path):
    data, pages = Path(path).read_bytes(), []
    for m in re.finditer(rb"stream\r?\n", data):
        e = data.find(b"endstream", m.end())
        if e < 0:
            continue
        raw = data[m.end():e].rstrip(b"\r\n")
        try:
            dec = zlib.decompress(raw)
        except Exception:
            try:
                dec = zlib.decompressobj().decompress(raw)
            except Exception:
                continue
        if b"BT" in dec:
            t = content_text(dec)
            if t.strip():
                pages.append(t)
    return pages


def pdf_pages(path):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True,
                               timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace").split("\f"), "pdf:pdftotext"
            note("degradations", "pdftotext_rc%d:%s" % (r.returncode, Path(path).name))
        except Exception as e:
            note("degradations", "pdftotext_failed:%s:%s" % (Path(path).name, type(e).__name__))
    try:
        pages = builtin_pdf(path)
        if pages:
            note("uncertainty", "page_numbering_estimated:builtin_extractor:%s" % Path(path).name)
            return pages, "pdf:builtin"
    except Exception as e:
        note("degradations", "builtin_pdf_failed:%s:%s" % (Path(path).name, type(e).__name__))
    return [], "none"


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))


# ------------------------------------------------------------------ records
def is_record(d):
    ks = {nk(k) for k in d}
    return bool(ks & TITLE_K) and bool(ks & (DOI_K | YR_K | AU_K | AB_K))


def walk(obj, ptr="", depth=0, out=None):
    out = [] if out is None else out
    if depth > 12:
        return out
    if isinstance(obj, dict):
        if is_record(obj):
            out.append((obj, ptr or "/"))
        for k, v in obj.items():
            walk(v, "%s/%s" % (ptr, k), depth + 1, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, "%s/%d" % (ptr, i), depth + 1, out)
    return out


def mk_rec(d, ptr, src):
    t = pick(d, TITLE_K)
    t = t[0] if isinstance(t, list) and t else t
    au = pick(d, AU_K)
    au = au if isinstance(au, list) else ([au] if au else [])
    yr = pick(d, YR_K)
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)\s*", "", flat(pick(d, DOI_K)), flags=re.I)
    return {"title": norm(flat(t))[:400] or None, "authors": [a for a in (flat(x) for x in au) if a][:20],
            "year": num(yr) if yr is not None else None, "venue": flat(pick(d, VN_K)) or None,
            "doi": doi.strip().lower() or None, "url": flat(pick(d, URL_K)) or None,
            "source_db": flat(pick(d, DB_K)) or None, "retrieved_at": flat(pick(d, TS_K)) or None,
            "query_id": flat(pick(d, QID_K)) or None, "abstract": norm(flat(pick(d, AB_K)))[:6000] or None,
            "provenance": [{"source_file": src, "json_pointer": ptr}]}


def is_query(d):
    ks = {nk(k) for k in d}
    return bool(ks & {"query", "querystring", "searchquery", "raw"}) and bool(
        ks & {"hits", "hitcount", "count", "total", "nresults", "status", "error", "retrievedat"})


# ------------------------------------------------------------------ sentence layer
def sections(text):
    out, off = [], 0
    for line in text.split("\n"):
        m = SECRE.match(line.strip())
        if m:
            out.append((off, m.group(1).lower()))
        off += len(line) + 1
    return out


def secgrp(name):
    n = (name or "").lower()
    if "abstract" in n:
        return "abstract"
    if "method" in n:
        return "methods"
    if "result" in n:
        return "results"
    return "discussion" if ("discuss" in n or "conclusion" in n or "limitation" in n) else "other"


def best_sent(item, text, smap):
    """返回 (score, sentence, offset, section, hits)；句级匹配 + 区域加权。"""
    best, w, req = None, item.get("w", 1) or 1, item.get("req", "any")
    alls = [a.lower() for a in (item.get("all") or [])]
    for m in PAGED.finditer(text):
        s, low = m.group(0), m.group(0).lower()
        hits = [t for t in item.get("any", []) if t in low]
        if not hits or (alls and not all(a in low for a in alls)):
            continue
        sec, off = "unknown", m.start()
        for o, n in smap:
            if o <= off:
                sec = n
            else:
                break
        if "reference" in sec:
            continue
        g = secgrp(sec)
        sc = len(hits) * w + (1.0 if (req == "any" or g == req) else 0.0) + (0.5 if re.search(r"\d", s) else 0.0)
        if best is None or sc > best[0]:
            best = (sc, " ".join(s.split()), off, sec, hits)
    return best


# ------------------------------------------------------------------ rubric
FALLBACK = [{"id": "D1.1", "dim": "D1", "label": "研究设计明确表述", "types": ["*"], "req": "any",
             "any": ["cohort", "randomized", "cross-sectional", "case-control", "systematic review"]},
]


def rubric(path):
    try:
        d = json.loads(re.search(r"```json\s*(\{.*?\})\s*```",
                                 Path(path).read_text(encoding="utf-8"), re.S).group(1))
        if d.get("items"):
            return d["items"], d.get("rubric_version", "unknown")
        raise ValueError("empty")
    except Exception as e:
        note("degradations", "rubric_unavailable:%s;fallback_bank" % type(e).__name__)
        return FALLBACK, "fallback"


# ------------------------------------------------------------------ appraisal
def _row(did, it):
    return {"doc_id": did, "dimension": it.get("dim"), "item_id": it.get("id"), "item_label": it.get("label"),
            "judgment": "unappraisable", "evidence_quote": None, "locator_page": None, "locator_section": None,
            "evidence_scope": None, "quote_verified": "not_applicable", "char_start": None, "probe_hit": [],
            "confidence": "low", "abstain_reason": None, "human_override": None, "override_reason": None,
            "adjudication": None}


def appraise(doc, items, overrides=None):
    overrides = overrides or {}
    text, abstract = doc.get("text") or "", doc.get("abstract") or ""
    full = (doc.get("text_source") or "none").startswith(("pdf:", "docx:", "text:", "html:"))
    design, starts = doc.get("design", "other"), doc.get("page_starts") or [0]
    appl = [it for it in items if "*" in (it.get("types") or []) or design in (it.get("types") or [])]
    if design == "other":
        appl = [it for it in items if (it.get("dim") or "").startswith("D")]
    smap, rows, use = (sections(text) if full else []), [], (text if full else abstract)
    for it in appl:
        r = _row(doc["doc_id"], it)
        if not use.strip():
            r["abstain_reason"] = "no_text"
        else:
            b = best_sent(it, use, smap)
            if b:
                _, s, off, sec, hits = b
                q, g, req = s[:320], secgrp(sec), it.get("req", "any")
                pno = max(1, sum(1 for o in starts if o <= off))
                win = [use[starts[k]:starts[k + 1] if k + 1 < len(starts) else len(use)]
                       for k in (pno - 2, pno - 1) if 0 <= k < len(starts)]
                r.update({"evidence_quote": q, "char_start": off, "locator_page": pno, "locator_section": sec,
                          "evidence_scope": g, "probe_hit": hits[:6]})
                if len(q) >= 20 and q in use and any(q in w for w in win):
                    r["quote_verified"] = "verified"
                    if not full:
                        r.update({"judgment": "partially_reported", "abstain_reason": "abstract_only"})
                    elif g == "abstract" and req in ("methods", "results"):
                        r["judgment"] = "partially_reported"
                    elif req in ("methods", "results") and g != req:
                        r["judgment"] = "partially_reported"
                    else:
                        r["judgment"] = "reported"
                    r["confidence"] = "high" if (r["judgment"] == "reported" and full) else (
                        "medium" if full else "low")
                else:
                    r.update({"judgment": "unappraisable", "abstain_reason": "quote_not_found",
                              "quote_verified": "unverified", "evidence_quote": None})
                    note("pending_human", {"doc_id": doc["doc_id"], "item_id": it.get("id"),
                                           "reason": "quote_not_found",
                                           "action": "人工回到该页确认原文是否确有此表述"})
            elif full:
                r.update({"judgment": "not_reported", "searched_chars": len(text),
                          "probe_count": len(it.get("any") or [])})
            else:
                r.update({"judgment": "unappraisable",
                          "abstain_reason": "abstract_only" if abstract else "no_text"})
        if overrides.get((doc["doc_id"], it.get("id"))):
            r["human_override"] = overrides[(doc["doc_id"], it.get("id"))]
        rows.append(r)
    return rows


def grade_doc(rows, design, full):
    by, per, pts, formula = {r["item_id"]: r for r in rows}, [], 0.0, []
    for name, base, extra in DOMAINS:
        ids = [i for i in base + extra.get(design, []) if i in by]
        if not ids or (name == "performance" and design != "rct") or (name == "confounding" and design == "rct"):
            per.append({"domain": name, "grade": "not_applicable", "points": 0.0, "basis_item_ids": ids,
                        "applicable": False})
            continue
        js = [by[i]["judgment"] for i in ids]
        rep, part = js.count("reported"), js.count("partially_reported")
        nr, un = js.count("not_reported"), js.count("unappraisable")
        g = "证据不足" if rep + part + nr == 0 else ("明确存在" if (rep == 0 and nr > 0) else
                                          ("可能存在" if (nr > 0 or part > 0) else "未见迹象"))
        pts += PTS[g]
        formula.append("%s=%.1f" % (name, PTS[g]))
        per.append({"domain": name, "grade": g, "points": PTS[g], "basis_item_ids": ids,
                    "applicable": True})
    appl = len(rows)
    judged = sum(1 for r in rows if r["judgment"] in ("reported", "partially_reported", "not_reported"))
    cov = round(judged / appl, 3) if appl else 0.0
    key = any(d["grade"] == "明确存在" and d["domain"] in ("selection", "confounding", "reporting") for d in per)
    if cov < 0.40 or appl == 0:
        risk, rule = "unappraisable", "R1: coverage<0.40"
    elif key or pts >= 4.0:
        risk, rule = "high", "R2: key domain 明确存在 or bias_points>=2.0"
    elif pts >= 1.0:
        risk, rule = "some_concerns", "R3: bias_points>=1.0"
    elif cov >= 0.60:
        risk, rule = "low", "R4: coverage>=0.60"
    else:
        risk, rule = "some_concerns", "R5: coverage<0.60"
    return {"overall_risk": risk,
            "confidence": "high" if (full and cov >= 0.70) else ("moderate" if (full and cov >= 0.40) else "low"),
            "per_domain": per,
            "grade_trace": {"applicable": appl, "judged": judged, "coverage": cov, "bias_points": round(pts, 2),
                            "rule_fired": rule,
                            "formula": "bias_points = sum(%s) = %.1f" % (", ".join(formula) or "none", pts)}}


def detect_design(doc):
    title = (doc.get("title") or "").lower()
    ab = (doc.get("abstract") or "").lower()[:4000]
    body = (doc.get("text") or "").lower()[:20000]
    scored = sorted(((sum(5 for p in pats if p in title) + sum(2 for p in pats if p in ab) +
                      sum(1 for p in pats if p in body), n) for n, pats in DESIGN_PAT), reverse=True)
    if not scored or scored[0][0] <= 0:
        return {"design": "other", "design_confidence": "low"}
    c = "high" if scored[0][0] >= 5 else ("medium" if scored[0][0] >= 3 else "low")
    return {"design": scored[0][1],
            "design_confidence": "low" if (len(scored) > 1 and scored[1][0] == scored[0][0]) else c}


# ------------------------------------------------------------------ relevance
def terms(case):
    sc = case.get("organizer_supplied_scope")
    sc = sc if isinstance(sc, dict) else {}
    toks = re.findall(r"[a-z][a-z\-]{2,}", " ".join(str(x) for x in (
        case.get("topic"), sc.get("topic"), case.get("task_instruction"), sc.get("keywords")) if x).lower())
    out = []
    for t in toks:
        if t not in STOP and t not in out:
            out.append(t)
    return out[:40]


def score(rec, tms):
    t, a = (rec.get("title") or "").lower(), (rec.get("abstract") or "").lower()
    th = [x for x in tms if x in t]
    ah = [x for x in tms if x in a and x not in th]
    why = (["title:" + ",".join(th[:6])] if th else []) + (["abstract:" + ",".join(ah[:6])] if ah else [])
    return round(len(th) * 2.0 + len(ah) * 0.5, 2), "; ".join(why) or "no_term_hit"


def decide(c, case, s):
    sc = case.get("organizer_supplied_scope")
    yr = sc.get("years") if isinstance(sc, dict) else None
    if isinstance(yr, (list, tuple)) and len(yr) == 2 and c.get("year"):
        try:
            if not (float(yr[0]) <= float(c["year"]) <= float(yr[1])):
                return "exclude", "out_of_scope_year"
        except Exception:
            pass
    return ("exclude", "off_topic_no_term_hit") if (s <= 0 and not c.get("fulltext_available")) else \
        ("include", None)


def qrecs(qs, meta):
    out = []
    for i, (q, src) in enumerate(qs, 1):
        hits = pick(q, {"hits", "hitcount", "count", "total", "nresults"})
        st = (flat(pick(q, {"status", "state"})) or "ok").lower()
        err = flat(pick(q, {"error", "errormessage", "errordetail"})) or None
        out.append({"query_id": flat(pick(q, {"queryid", "qid"})) or "q%d" % i,
                    "db": flat(pick(q, {"db", "database", "source"})) or None,
                    "raw": flat(pick(q, {"query", "querystring", "searchquery", "raw"})) or None,
                    "filters": {}, "hits": int(hits) if str(hits).isdigit() else None, "retained": None,
                    "status": st if st in ("ok", "empty", "partial", "error") else "unknown", "error": err,
                    "retrieved_at": flat(pick(q, TS_K)) or None, "source_file": src, "origin": "artifact"})
        if err:
            note("errors", "%s:query_error:%s" % (src, err[:120]))
    if not out:
        out = [{"query_id": "q_scan_%d" % (i + 1), "db": None, "raw": None, "filters": {}, "hits": m["records"],
                "retained": None, "status": "ok", "error": None, "retrieved_at": None, "source_file": m["rel"],
                "origin": "record_scan"} for i, m in enumerate([x for x in meta if x.get("records")])]
        if out:
            note("missing", "query_log(artifact)；按题录文件生成 record_scan 日志")
    return out
