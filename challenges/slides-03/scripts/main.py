#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - academic talk organisation (slides-03).
init  -> index /input, write a legal partial result.json
show  -> print source paragraphs with locators (evidence the Agent quotes)
check -> validate work/slide_plan.json (verbatim quotes, 3-5 bullets, page count)
build -> presentation.pptx + preview.pdf + content_map + compliance + result.json
Stdlib only, no network, exit 0 always, result.json always written first.
"""
import argparse, json, os, re, sys, time, traceback, zipfile, zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import makeppt
import audit

T0 = time.time()
SUF = {".pdf", ".docx", ".txt", ".md", ".csv", ".tsv", ".json", ".xlsx", ".pptx",
       ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".html", ".tex"}
SKIP = {"task.md", "guide.md", "readme.md"}


def el():
    return round(time.time() - T0, 1)


def _dir(env, dflt):
    for c in (os.environ.get(env), dflt, "."):
        if c:
            try:
                p = Path(c)
                p.mkdir(parents=True, exist_ok=True)
                if os.access(p, os.W_OK):
                    return p
            except Exception:
                pass
    return Path.cwd()


IN = Path(os.environ.get("IN_DIR") or next((c for c in ("/input", str(Path.cwd() / "input"), str(HERE.parent / "input"))
                                            if Path(c).is_dir()), "/input"))
WORK = _dir("WORK_DIR", "/app/work")
OUT = _dir("OUT_DIR", "/app/output")


def rj(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return d


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- discovery
def sniff(p):
    try:
        h = Path(p).read_bytes()[:8]
    except Exception:
        return ""
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK\x03\x04"):
        return {".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx"}.get(p.suffix.lower(), "zip")
    if h.startswith(b"\x89PNG") or h[:2] in (b"\xff\xd8", b"II", b"MM"):
        return "image"
    return ""


def find_case():
    for c in [IN / "case.json"] + sorted(IN.rglob("case*.json")):
        d = rj(c)
        if isinstance(d, dict) and d:
            return c, d
    for c in sorted(IN.rglob("*.json")):
        d = rj(c)
        if isinstance(d, dict) and re.search(r"instruction|output_contract|case_id|task", json.dumps(d)[:4000], re.I):
            return c, d
    bad = sorted(IN.rglob("case*.json")) if IN.is_dir() else []
    return (bad[0] if bad else None), {}


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, "%s.%s" % (pre, k) if pre else str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, "%s[%d]" % (pre, i))
    else:
        yield pre, o


def hint(case, pats, num=False):
    for k, v in flat(case):
        if v in (None, "", [], {}) or not any(re.search(p, k.lower()) for p in pats):
            continue
        if not num:
            return v
        m = re.search(r"\d+(?:\.\d+)?", str(v))
        return float(m.group(0)) if m else None
    return None


def materials():
    return [p for p in sorted(IN.rglob("*")) if IN.is_dir() and p.is_file() and not p.name.startswith(".")
            and p.name.lower() not in SKIP and not re.match(r"case.*\.json$", p.name, re.I)
            and (p.suffix.lower() in SUF or sniff(p))] if IN.is_dir() else []


# ---------------------------------------------------------------- extraction
def paras(text, mid):
    out = [re.sub(r"\s+", " ", s).strip() for s in re.split(r"\n\s*\n|\n|\f", text or "") if s.strip()]
    if len(out) < 2 and len((text or "").strip()) > 200:  # single blob -> sentence split
        out = [s.strip() for s in re.split(r"(?<=[。！？.!?])\s+", text) if len(s.strip()) > 2]
    return [{"loc": "%s#p%d" % (mid, i + 1), "text": s} for i, s in enumerate(out)]


def _pdf(p):
    tx = ""
    try:
        import subprocess
        r = subprocess.run(["pdftotext", "-layout", str(p), "-"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=120)
        tx = r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
    except Exception:
        tx = ""
    if len(tx.strip()) >= 40:
        return "pdf", tx
    try:  # crude: inflate streams, keep literal strings (no geometry)
        ch = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", Path(p).read_bytes(), re.S):
            try:
                s = zlib.decompress(m.group(1))
            except Exception:
                continue
            ch += [t[1:-1] for t in re.findall(rb"\((?:[^()\\\\]|\\\\.)*\)", s)]
        return "pdf-crude", b" ".join(ch).decode("latin-1", "replace")
    except Exception:
        return "pdf-crude", ""


def extract(p):
    k = sniff(p) or {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx"}.get(p.suffix.lower(), "text")
    try:
        if k == "pdf":
            return _pdf(p)
        if k == "image":
            return k, ""
        if k in ("docx", "pptx", "xlsx"):
            with zipfile.ZipFile(p) as z:
                nm = z.namelist()
                if k == "docx":
                    x = z.read("word/document.xml").decode("utf-8", "replace")
                    return k, re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n\n", x))
                if k == "pptx":
                    return k, "\n\n".join(" ".join(t for t in re.findall(r"<a:t>(.*?)</a:t>", z.read(n).decode("utf-8", "replace"), re.S) if t.strip())
                                          for n in sorted(x for x in nm if re.match(r"ppt/slides/slide\d+\.xml$", x)))
                sh = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)] if "xl/sharedStrings.xml" in nm else []
                rows = [" | ".join(sh[int(v)] if v.isdigit() and int(v) < len(sh) else v for v in re.findall(r"<v>(.*?)</v>", r))
                        for s in sorted(n for n in nm if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
                        for r in re.findall(r"<row[^>]*>(.*?)</row>", z.read(s).decode("utf-8", "replace"), re.S)]
                return k, "\n".join(rows)
        return k, p.read_text(encoding="utf-8-sig")
    except Exception:
        try:
            return k, p.read_text(encoding="latin-1", errors="replace")
        except Exception:
            return "error", ""


def build_index():
    cp, case = find_case()
    task = next((c.read_text(encoding="utf-8-sig", errors="replace") for c in (IN / "task.md", IN / "TASK.md") if c.is_file()), "")
    idx = {"input_root": str(IN), "case_path": str(cp) if cp else None, "case": case,
           "task_excerpt": task[:3000], "materials": [], "errors": [], "template": None}
    if cp and not case:
        idx["errors"].append("%s exists but is not parseable JSON: treated as absent contract" % cp.name)
    for i, p in enumerate(materials(), 1):
        mid = "M%d" % i
        try:
            kind, tx = extract(p)
            ps = paras(tx.replace(",", " | ") if p.suffix.lower() in (".csv", ".tsv") else tx, mid)
        except Exception as e:
            idx["errors"].append("%s extract failed: %r" % (mid, e))
            kind, tx, ps = "error", "", []
        if kind == "image":
            idx["errors"].append("%s is an image: not read as text, listed as evidence gap" % mid)
        idx["materials"].append({"id": mid, "path": str(p), "name": p.name, "kind": kind,
                                 "bytes": p.stat().st_size if p.exists() else 0, "chars": len(tx), "paras": ps})
        if kind == "pptx" and not idx["template"]:
            idx["template"] = str(p)
            idx["materials"][-1]["role"] = "template"
    return idx


# ---------------------------------------------------------------- result.json
MAP = [(r"quotes?_checked|quotes?_verified|with_evidence|slide_count|^count$|pages?$", "coverage"),
       (r"slide_plan|plan|outline|storyboard|page", "slide_plan"),
       (r"content_map|evidence|mapping|trace|locator", "content_map"),
       (r"compliance|check|validat|render", "compliance"),
       (r"presentation|pptx|deck|editable|deliverable|file", "pptx"),
       (r"preview|pdf|png|image", "preview"), (r"notes|speaker|script", "notes"),
       (r"case_id", "case_id"), (r"status", "status"), (r"sources?|evidence", "sources"),
       (r"summary|conclusion|main_result|result", "summary"), (r"qa|question", "qa"),
       (r"coverage|metric|count", "coverage")]


def _map(k):
    k = (k or "").lower()
    return next((nm for pat, nm in MAP if re.search(pat, k)), k)


def backfill(tpl, vals, key="", parent=""):
    """Keep the contract shape; fill only null/empty leaves (nested keys fall back to parent dict)."""
    if isinstance(tpl, dict):
        return {k: backfill(v, vals, k, key) for k, v in tpl.items()}
    if isinstance(tpl, list):
        if tpl and all(isinstance(x, dict) for x in tpl):
            return [backfill(x, vals, key, parent) for x in tpl]
        if tpl:
            return tpl
        v = vals.get(_map(key))
        return v if isinstance(v, list) else []
    if tpl in (None, ""):
        pv = vals.get(parent)
        if isinstance(pv, dict) and key in pv and not isinstance(pv[key], (dict, list)):
            return pv[key]
        v = vals.get(_map(key))
        return tpl if v is None else v
    return tpl


CONTRACT_MAP = {"editable_source": "pptx", "export_artifact": "preview", "export": "preview",
                "content_map": "content_map", "compliance_checks": "compliance", "compliance": "compliance",
                "exceptions": None, "deliverable": "summary", "result": "summary", "claims": "coverage",
                "uncertainties": "uncertainty", "preserved_facts": None, "evidence_map": "content_map",
                "change_log": None, "slide_plan": "slide_plan", "presentation": "pptx", "preview": "preview"}


def result_doc(case, idx, vals, status, errors, degr, changes, extra=None):
    case = case if isinstance(case, dict) else {}
    c = case.get("output_contract")
    if isinstance(c, dict):
        doc = backfill(c, vals)
    elif isinstance(c, list):
        doc = {}
        for name in c:
            if not isinstance(name, str):
                continue
            if name == "exceptions":
                doc[name] = list(degr or [])
                continue
            key = CONTRACT_MAP.get(name, _map(name))
            v = vals.get(key) if key else None
            if v is None:
                v = vals.get(_map(name))
            doc[name] = v
        doc["output_contract"] = c
    else:
        doc = {}
    if not isinstance(doc, dict):
        doc = {"output_contract": doc}
    doc.update({"case_id": case.get("case_id") or (Path(idx["case_path"]).stem if idx.get("case_path") else "unknown_case"),
                "status": status,
                "sources": [{k: m.get(k) for k in ("id", "path", "name", "kind", "chars")} for m in idx.get("materials", [])],
                "uncertainty": vals.get("uncertainty") or [], "pending_human": vals.get("pending_human") or [],
                "errors": errors, "degradations": degr, "changes": changes,
                "runtime": {"seconds": el(), "python": sys.version.split()[0], "skill": "slides-03",
                            "generated_at": datetime.now().isoformat(timespec="seconds")}})
    for k, v in audit.fields().items():
        if doc.get(k) in (None, "", [], {}):
            doc[k] = v
    doc.update(extra or {})
    return doc


def contract_keys(case):
    c = (case or {}).get("output_contract") if isinstance(case, dict) else None
    if isinstance(c, dict):
        return [k for k in c]
    return [x for x in c if isinstance(x, str)] if isinstance(c, list) else []


def partial(vals=None, idx=None, case=None):
    try:
        audit.ensure_min(OUT, (case or {}).get("case_id") or "unknown_case", "partial",
                         (idx or {}).get("errors"), tag="partial")
        audit.log("partial", "legal partial result.json written")
    except Exception:
        pass
    wj(OUT / "result.json", result_doc(case or {}, idx or {"materials": []}, vals or {}, "partial", [],
                                       ["run started; deliverables pending"], []))
    return True


# ---------------------------------------------------------------- validation
def norm(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def verify(q, idx):
    n = norm(q)
    if not n:
        return None
    for m in idx.get("materials", []):
        if m.get("role") == "template":
            continue
        for p in m["paras"]:
            if n in norm(p["text"]):
                return p["loc"]
        if n in norm("".join(p["text"] for p in m["paras"])):
            return m["paras"][0]["loc"] if m["paras"] else m["id"]
    return None


def validate(plan, idx, target=None):
    rep = {"errors": [], "warnings": [], "slides": 0, "bullets": 0, "quotes_checked": 0,
           "quotes_verified": 0, "slides_with_evidence": 0, "target_slides": target, "passed": False, "usable": False,
           "page_match": target is None}
    sl = plan.get("slides") if isinstance(plan, dict) else None
    if not isinstance(sl, list) or not sl:
        rep["errors"].append({"field": "slides", "msg": "no slides[] (plan missing or malformed)"})
        return rep
    rep["slides"] = len(sl)
    for i, s in enumerate(sl, 1):
        if not isinstance(s, dict):
            rep["errors"].append({"slide": i, "msg": "slide is not an object"})
            continue
        bl = [b for b in (s.get("bullets") or []) if isinstance(b, dict)]
        ts = s.get("layout") == "title" or (i == 1 and not bl)
        if not str(s.get("title") or "").strip():
            rep["errors"].append({"slide": i, "field": "title", "msg": "empty title"})
        if not ts and not 3 <= len(bl) <= 5:
            rep["errors"].append({"slide": i, "field": "bullets", "msg": "%d bullets (need 3-5)" % len(bl)})
        if not ts and not str(s.get("notes") or "").strip():
            rep["warnings"].append({"slide": i, "msg": "no speaker notes"})
        ev = False
        for j, b in enumerate(bl, 1):
            rep["bullets"] += 1
            if not str(b.get("text") or "").strip():
                rep["errors"].append({"slide": i, "field": "bullets[%d].text" % j, "msg": "empty bullet"})
            if b.get("quote"):
                rep["quotes_checked"] += 1
                f = verify(b["quote"], idx)
                if f:
                    rep["quotes_verified"] += 1
                    ev = True
                    if b.get("locator") and norm(b["locator"]) not in norm(f):
                        rep["warnings"].append({"slide": i, "msg": "locator %s resolved %s" % (b["locator"], f)})
                else:
                    rep["errors"].append({"slide": i, "field": "bullets[%d].quote" % j,
                                          "msg": "quote not found verbatim: %s" % str(b["quote"])[:50]})
            elif b.get("locator"):
                ev = True
            else:
                rep["warnings"].append({"slide": i, "field": "bullets[%d]" % j, "msg": "no quote/locator"})
        if ev:
            rep["slides_with_evidence"] += 1
    rep["page_match"] = target is None or len(sl) == target
    rep["usable"] = (not rep["errors"] and rep["slides_with_evidence"] >= max(1, int(0.8 * rep["slides"])))
    rep["passed"] = rep["usable"] and rep["page_match"]
    return rep


def fallback_plan(idx, h):
    """Deterministic minimum deck: every bullet is a verbatim source sentence + locator.
    Page count is bounded by available evidence so each page keeps 3-5 bullets."""
    sents = [{"text": p["text"], "loc": p["loc"]} for m in idx.get("materials", []) if m.get("role") != "template" for p in m["paras"]
             if 25 <= len(p["text"]) <= 320 and not re.match(r"^(references|acknowledg|bibliograph)", p["text"], re.I)]
    if not sents:
        return {"slides": [], "_fallback": "no extractable source text"}
    want = max(4, min(15, int(h.get("slides") or 8)))
    pages = max(1, min(want - 1, len(sents) // 3))              # every page keeps >=3 bullets
    pages = max(pages, -(-len(sents) // 5))                     # and at most 5
    sents = sents[:5 * pages]                                  # drop overflow rather than overload a page
    q, r = divmod(len(sents), pages)
    out = [{"n": 1, "title": h.get("title") or "汇报提纲", "layout": "title", "bullets": [],
            "subtitle": h.get("subtitle") or "由所给材料组织的内容主线",
            "notes": "开场：说明听众、时长与结论强度，再进入主线。"}]
    k = 0
    for i in range(pages):
        ch = sents[k:k + q + (1 if i < r else 0)]
        k += len(ch)
        bl = [{"text": c["text"][:110], "locator": c["loc"], "quote": c["text"][:160]} for c in ch]
        while len(bl) < 3:                                      # sparse material: state the gap, never invent
            bl.append({"text": "材料在此处证据不足，需作者补充（已记入 pending_human）。", "locator": "", "quote": ""})
        out.append({"n": len(out) + 1, "title": "要点组 %d（源材料顺序）" % len(out), "bullets": bl,
                    "notes": "本页只讲一件事，证据来自 %s。报数字时同时说条件。"
                             % "、".join(b["locator"] for b in bl),
                    "evidence_strength": "unrated"})
    return {"deck_title": h.get("title") or "学术汇报", "slides": out,
            "_fallback": "deterministic plan from source paragraphs (%d pages; %d requested)" % (len(out), want)}


def tpl_of(h, idx):
    """Resolve a template reference (name/path/hint) to a real file, else first pptx material."""
    t = h.get("template")
    for c in ([Path(str(t))] if t else []) + [Path(str(t)) if t else None, IN / str(t) if t else None]:
        try:
            if c and c.is_file():
                return str(c)
        except Exception:
            pass
    if t:
        for m in idx.get("materials", []):
            if Path(m["path"]).name == Path(str(t)).name:
                return m["path"]
    return idx.get("template")


def deck_from(plan, h):
    sl = []
    for i, s in enumerate(plan.get("slides") or [], 1):
        bl = [{"text": b.get("text", ""), "locator": b.get("locator") or ""}
              for b in (s.get("bullets") or []) if isinstance(b, dict)]
        sl.append({"title": s.get("title") or "Slide %d" % i, "bullets": bl, "subtitle": s.get("subtitle") or "",
                   "layout": s.get("layout") or ("title" if i == 1 else "content"), "notes": s.get("notes") or "",
                   "source": "; ".join(sorted({b["locator"] for b in bl if b["locator"]}))})
    return {"title": plan.get("deck_title") or h.get("title") or "学术汇报", "subtitle": plan.get("subtitle") or "",
            "meta": h.get("meta") or "", "slides": sl}


def pdf_stdlib(deck, out):
    """Fallback PDF preview without external tools (text-only, one page per slide)."""
    W, H, st = 960, 540, []
    for s in deck["slides"]:
        y, o = H - 70, []
        blocks = [(s["title"], 28 if s.get("layout") == "title" else 21, 30)] + \
                 [(b["text"], 14, 21) for b in s["bullets"]]
        for txt, sz, step in blocks:
            for l in makeppt._wrap(txt, sz, W - 120):
                o.append("BT /F1 %d Tf 1 0 0 1 60 %d Tm <%s> Tj ET\n" % (sz, y, l.encode("utf-16-be").hex().upper()))
                y -= step
            y -= 8
        st.append("".join(o))
    st = st or [""]
    n, fid = len(st), 3 * len(st) + 3
    objs = ["<</Type/Catalog/Pages 2 0 R>>",
            "<</Type/Pages/Kids[%s]/Count %d>>" % (" ".join("%d 0 R" % (3 * n + 1 + i) for i in range(n)), n)]
    objs += ["<</Type/Page/Parent 2 0 R/MediaBox[0 0 %d %d]/Resources<</Font<</F1 %d 0 R>>>>/Contents %d 0 R>>" % (W, H, fid, 3 * n + 1 + i) for i in range(n)]
    objs += ["<</Length %d>>stream\n%s\nendstream" % (len(c.encode("latin-1", "replace")), c) for c in st]
    objs += ["<</Type/Font/Subtype/Type0/BaseFont/STSong-Light/Encoding/UniGB-UCS2-H/DescendantFonts[%d 0 R]>>" % (fid + 1),
             "<</Type/Font/Subtype/CIDFontType0/BaseFont/STSong-Light/CIDSystemInfo<</Registry(Adobe)/Ordering(GB1)/Supplement 4>>/FontDescriptor %d 0 R/DW 1000/W[1 95 500]>>" % (fid + 2),
             "<</Type/FontDescriptor/FontName/STSong-Light/Flags 4/FontBBox[-25 -254 1000 880]/ItalicAngle 0/Ascent 880/Descent -120/CapHeight 880/StemV 93>>"]
    buf, offs, pos = ["%PDF-1.4\n"], [], 9
    for i, ob in enumerate(objs):
        offs.append(pos)
        buf.append("%d 0 obj\n%s\nendobj\n" % (i + 1, ob))
        pos += len(buf[-1].encode("latin-1", "replace"))
    tail = "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + "".join("%010d 00000 n \n" % o for o in offs)
    tail += "trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, pos)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(("".join(buf) + tail).encode("latin-1", "replace"))
    return True


def pdf_pages(p):
    """Page count that survives compressed PDFs: pdftotext form feeds, then pdfinfo, then raw scan."""
    try:
        import subprocess
        r = subprocess.run(["pdftotext", "-layout", str(p), "-"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=90)
        if r.returncode == 0 and r.stdout:
            return max(1, r.stdout.count(b"\f") + (0 if r.stdout.endswith(b"\f") else 1))
    except Exception:
        pass
    try:
        d = Path(p).read_bytes()
        return len(re.findall(rb"/Type\s*/Page\b", d)) or d.count(b"/Type/Page")
    except Exception:
        return 0


def plan_md(plan, h):
    L = ["# 演示内容规划", "", "- 听众：%s" % (plan.get("audience") or h.get("audience") or "未指定"),
         "- 时长：%s 分钟" % (plan.get("duration_min") or h.get("duration") or "未指定"),
         "- 页数：%s" % (plan.get("target_slides") or h.get("slides") or len(plan.get("slides") or [])),
         "- 汇报目标：%s" % (plan.get("goal") or "按材料主线组织"), ""]
    L += ["## 叙事顺序", ""] + ["- **%s**（%s）：%s" % (a.get("act", ""), a.get("slides", ""), a.get("purpose", ""))
                                 for a in plan.get("narrative") or [] if isinstance(a, dict)] + [""] if plan.get("narrative") else []
    L += ["## 逐页计划", ""]
    for i, s in enumerate(plan.get("slides") or [], 1):
        L.append("### %d. %s" % (i, s.get("title", "")))
        L += ["- 主张：%s" % s["claim"]] if s.get("claim") else []
        L += ["- 要点：%s  `[%s]`" % (b.get("text", ""), b.get("locator") or "-") for b in s.get("bullets") or [] if isinstance(b, dict)]
        L += ["- %s：%s" % (lab, s[k]) for k, lab in (("visual", "图表"), ("evidence_strength", "证据强度"), ("notes", "讲解备注")) if s.get(k)]
        L.append("")
    L += ["## 问答准备", ""] + ["- **Q：%s** → %s（备用：%s）" % (q.get("q", ""), q.get("a", ""), q.get("backup", "-"))
                                for q in plan.get("qa") or [] if isinstance(q, dict)] + [""] if plan.get("qa") else []
    return "\n".join(L)


def hints_from(case, task, idx):
    first = next((p["text"] for m in idx.get("materials", []) for p in m["paras"] if len(p["text"]) > 12), "")
    h = {"audience": hint(case, [r"audience|听众|target_group"]),
         "duration": hint(case, [r"duration|minutes|时长|time_limit"], True),
         "slides": hint(case, [r"slide_count|num_slides|n_slides|页数"], True),
         "title": hint(case, [r"^title$|case_title|deck_title|paper_title|研究题目"]),
         "template": hint(case, [r"template|母版|master|starting_deck"])}
    for k, pat, cast in (("duration", r"(\d{1,3})\s*(?:分钟|min\b)", float),
                         ("slides", r"(\d{1,3})\s*(?:页|slides?\b)", float),
                         ("audience", r"听众[：:]\s*([^\n。|]{2,24})", str)):
        if not h.get(k):
            m = re.search(pat, task or "")
            h[k] = cast(m.group(1)) if m else h.get(k)
    h["title"] = h["title"] or (re.sub(r"^[#>*\s]+", "", first)[:60] or None)
    if not h["slides"] and h["duration"]:
        h["slides"] = max(4, round(h["duration"] * 0.8))
    h["meta"] = " | ".join(x for x in [str(h["audience"] or ""), ("%g 分钟" % h["duration"]) if h["duration"] else "",
                                       datetime.now().strftime("%Y-%m-%d")] if x)
    return h


# ---------------------------------------------------------------- commands
def cmd_init(a):
    cp, case = find_case()
    partial({}, {"materials": [], "case_path": str(cp) if cp else None}, case)
    idx = build_index()
    idx["hints"] = hints_from(case, idx["task_excerpt"], idx)
    audit.log("init", "index built", materials=len(idx["materials"]), hints={k: idx["hints"].get(k) for k in ("audience", "duration", "slides")}, errors=len(idx["errors"]))
    audit.ensure_min(OUT, case.get("case_id") if isinstance(case, dict) else None, "partial", idx["errors"], tag="init")
    wj(WORK / "materials.json", idx)
    md = ["# 材料索引", "", "- 输入根：`%s`" % IN, "- case.json：`%s`" % (idx["case_path"] or "未找到"),
          "- 线索：%s" % json.dumps({k: idx["hints"].get(k) for k in ("audience", "duration", "slides")}, ensure_ascii=False),
          "", "| id | 文件 | 类型 | 字节 | 段落 |", "|-|-|-|-|-|"] + \
         ["| %s | %s | %s | %d | %d |" % (m["id"], m["name"], m["kind"], m["bytes"], len(m["paras"])) for m in idx["materials"]] + \
         [["| %s | %s | %s | %d | %d |" % (m["id"], m["name"], m["kind"], m["bytes"], len(m["paras"])) for m in idx["materials"]]][0]
    md += ["", "## 异常"] + ["- " + e for e in idx["errors"]] if idx["errors"] else []
    (WORK / "index.md").write_text("\n".join(md), encoding="utf-8")
    wj(OUT / "result.json", result_doc(case, idx, {
        "slide_plan": {"path": "output/slide_plan.md", "status": "pending"},
        "uncertainty": ["演示计划尚未编写：先 `show` 读原文，再由 Agent 手写 work/slide_plan.json"],
        "pending_human": ["逐页计划待编写，之后运行 build"]}, "partial", idx["errors"], ["init only: no deck built yet"], []))
    print(json.dumps({"materials": len(idx["materials"]), "chars": sum(m["chars"] for m in idx["materials"]),
                      "hints": idx["hints"], "index": "work/index.md"}, ensure_ascii=False, indent=2))
    print("\nNEXT: python3 main.py show --grep '<keyword>'  ->  write work/slide_plan.json  ->  python3 main.py build")
    return 0


def cmd_show(a):
    idx = rj(WORK / "materials.json") or build_index()
    n = 0
    for m in idx.get("materials", []):
        ps = [p for p in m["paras"] if (not a.material or m["id"] == a.material)
              and (not a.grep or re.search(a.grep, p["text"], re.I))]
        ps = ps[:a.limit] if a.limit else ps
        if ps:
            print("\n== %s  %s (%s, %d paras)" % (m["id"], m["name"], m["kind"], len(m["paras"])))
            for p in ps:
                print("[%s] %s" % (p["loc"], p["text"]))
                n += 1
    print("\n-- %d paragraphs; locator = M<id>#p<n> --" % n)
    return 0


def cmd_check(a):
    idx = rj(WORK / "materials.json") or build_index()
    h = idx.get("hints") or {}
    path = a.plan or WORK / "slide_plan.json"
    plan = rj(path)
    rep = validate(plan, idx, int(h["slides"]) if h.get("slides") else None)
    rep.update({"plan_path": str(path), "plan_found": bool(plan)})
    wj(WORK / "check_report.json", rep)
    audit.log("check", "plan validated", usable=rep["usable"], passed=rep["passed"],
              quotes=[rep["quotes_verified"], rep["quotes_checked"]], errors=len(rep["errors"]))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print("\n%s — quotes must appear verbatim in a source paragraph (main.py show --grep '<fragment>')"
          % ("PASS" if rep["usable"] else "FAIL"))
    return 0


def cmd_build(a):
    idx = rj(WORK / "materials.json") or build_index()
    case = idx.get("case") or {}
    h = idx.get("hints") or hints_from(case, idx.get("task_excerpt", ""), idx)
    errors, degr, changes = list(idx.get("errors") or []), [], []
    audit.log("build", "start", input=str(IN), materials=len(idx.get("materials") or []),
              chars=sum(m.get("chars") or 0 for m in idx.get("materials") or []))
    partial({}, idx, case)
    target = int(h["slides"]) if h.get("slides") else None
    v0 = audit.skeleton(idx, h, target)
    audit.log("skeleton", "v0 written", pages=len(v0["pages"]), seconds=v0["total_seconds"], target=target)
    plan = rj(a.plan or WORK / "slide_plan.json")
    rep = validate(plan, idx, target)
    if rep["usable"]:
        changes.append({"what": "slide_plan", "from": "agent draft", "to": "used as-is",
                        "why": "%d/%d quotes verified, %d slides" % (rep["quotes_verified"], rep["quotes_checked"], rep["slides"])})
    else:
        n_bad = len(rep["errors"])
        plan = fallback_plan(idx, h)
        plan["narrative"] = [{"act": "背景与问题", "slides": "2-%d" % max(2, len(plan["slides"]) // 2), "purpose": "建立动机"},
                             {"act": "证据与结论", "slides": "%d-%d" % (max(3, len(plan["slides"]) // 2 + 1), len(plan["slides"])),
                              "purpose": "给结果并标注证据强度"}]
        degr.append("agent plan missing/failed (%d errors) -> deterministic fallback from source paragraphs" % n_bad)
        changes.append({"what": "slide_plan", "from": "agent plan (%d errors)" % n_bad, "to": "fallback plan",
                        "why": "no verified plan; fallback keeps every page traceable"})
        rep = validate(plan, idx, target)
    deck = deck_from(plan, h)
    if not deck["slides"]:
        deck["slides"] = [{"title": h.get("title") or "学术汇报", "bullets": [], "layout": "title",
                           "notes": "无可用材料：请补充输入。", "source": ""}]
        degr.append("no usable source text -> single title slide placeholder")
    pptx = OUT / "presentation.pptx"
    info = {}
    try:
        info = makeppt.build_pptx(deck, pptx, tpl_of(h, idx))
        if not info.get("template_used") and (h.get("template") or idx.get("template")):
            degr.append("template inherit failed -> built-in master used: %s"
                        % "; ".join(info.get("errors") or ["unknown"]))
    except Exception as e:
        errors.append("pptx build failed: %r" % (e,))
    pdf = OUT / "preview.pdf"
    got = makeppt.office_pdf(pptx, OUT) if pptx.exists() and pptx.stat().st_size > 2000 else None
    if got and got.name != "preview.pdf":
        got.replace(pdf)
    if got:
        changes.append({"what": "preview", "from": "-", "to": "preview.pdf", "why": "LibreOffice export (fidelity 1:1)"})
    else:
        pdf_stdlib(deck, pdf)
        degr.append("LibreOffice unavailable/failed -> preview.pdf from stdlib writer (text layout only); "
                    "re-export on a desktop for the final visual check")
    (OUT / "slide_plan.md").write_text(plan_md(plan, h), encoding="utf-8")
    cmap = [{"slide": i, "title": s.get("title"), "claim": s.get("claim"), "evidence_strength": s.get("evidence_strength"),
             "visual": s.get("visual"), "notes": s.get("notes"),
             "bullets": [{"text": b.get("text"), "locator": b.get("locator"), "quote": b.get("quote"),
                          "verified": verify(b.get("quote"), idx) if b.get("quote") else (b.get("locator") or None)}
                         for b in (s.get("bullets") or []) if isinstance(b, dict)]}
            for i, s in enumerate(plan.get("slides") or [], 1)]
    zok, zmsg = False, ""
    try:
        with zipfile.ZipFile(pptx) as z:
            nm = z.namelist()
            zok = z.testzip() is None and any(re.match(r"ppt/slides/slide\d+\.xml$", x) for x in nm)
            zmsg = "%d parts, %d slides, %d notes" % (len(nm), len([x for x in nm if "/slides/slide" in x]),
                                                     len([x for x in nm if "notesSlide" in x]))
    except Exception as e:
        zmsg = repr(e)
    n = len(deck["slides"])
    try:
        pages = pdf_pages(pdf)
    except Exception:
        pages = 0
    dup = [i for i, s in enumerate(plan.get("slides") or [], 1)
           if s.get("notes") and any(b.get("text") and norm(b["text"])[:40] in norm(s["notes"])
                                     for b in (s.get("bullets") or []) if isinstance(b, dict))]
    chk = {"slide_count": {"value": n, "target": target, "pass": target is None or n == target},
           "bullets_3_5": {"pass": all(3 <= len([b for b in (s.get("bullets") or []) if isinstance(b, dict)]) <= 5
                                       or s.get("layout") == "title" or i == 1
                                       for i, s in enumerate(plan.get("slides") or [], 1))},
           "notes_present": {"pass": all(str(s.get("notes") or "").strip() or s.get("layout") == "title" for s in plan.get("slides") or [])},
           "notes_not_repeating": {"duplicated_slides": dup, "pass": not dup},
           "evidence": {"checked": rep["quotes_checked"], "verified": rep["quotes_verified"],
                        "slides_with_evidence": rep["slides_with_evidence"], "slides": rep["slides"],
                        "pass": rep["quotes_checked"] > 0 and rep["quotes_verified"] == rep["quotes_checked"]},
           "pptx_editable": {"pass": zok, "detail": zmsg},
           "template": {"used": info.get("template_used"), "mode": info.get("mode"), "errors": info.get("errors")},
           "preview": {"pdf": "output/preview.pdf", "pages": pages, "pass": pages == n},
           "aspect": {"pass": True, "note": "sldSz 12192000x6858000 EMU (16:9)"},
           "fonts": {"theme": "Arial / Microsoft YaHei"}}
    wj(OUT / "compliance_checks.json", chk)
    wj(OUT / "content_map.json", cmap)
    vals = {"slide_plan": {"md": "output/slide_plan.md", "json": "work/slide_plan.json", "slides": n,
                           "audience": h.get("audience"), "duration_min": h.get("duration"), "target": target,
                           "narrative": plan.get("narrative")},
            "pptx": "output/presentation.pptx", "preview": "output/preview.pdf", "content_map": cmap,
            "compliance": chk,
            "notes": [{"slide": i, "notes": s.get("notes")} for i, s in enumerate(plan.get("slides") or [], 1)],
            "qa": plan.get("qa") or [],
            "coverage": {"slides": n, "with_evidence": rep["slides_with_evidence"],
                         "quotes_verified": rep["quotes_verified"], "quotes_checked": rep["quotes_checked"]},
            "summary": "%d 页可编辑演示稿（%s）+ 逐页证据映射；%d/%d 条引用在源材料逐字命中。"
                       % (n, info.get("mode", "-"), rep["quotes_verified"], rep["quotes_checked"]),
            "uncertainty": [], "pending_human": []}
    if rep["quotes_checked"] == 0:
        vals["uncertainty"].append("无逐字引用被校验：页面与源材料的对应关系未经机器确认。")
    vals["pending_human"] += ["校验未通过：%s" % json.dumps(e, ensure_ascii=False) for e in rep["errors"][:6]]
    if not rep["page_match"]:
        vals["pending_human"].append("计划页数 %d 与要求 %d 不一致：直接上台前需增减页面。"
                                     % (n, target))
    if not got:
        vals["pending_human"].append("在桌面端用 PowerPoint/LibreOffice 复核 pptx 版式（预览为降级渲染）。")
    ok = rep["passed"] and zok and pages == n and not errors and (target is None or n == target)
    status = "ok" if ok else ("insufficient_evidence" if rep["quotes_checked"] == 0 and n > 1 else "partial")
    if not idx.get("materials") and not case:
        status = "input_error"
    ckeys = contract_keys(case)
    cmiss = [k for k in ckeys if k not in result_doc(case, idx, vals, status, errors, degr, changes)]
    af = audit.finalize(OUT, WORK, case, idx, h, plan, chk, rep, target, vals, status,
                        errors, degr, changes, v0, contract_missing=cmiss, ckeys=ckeys)
    audit.log("finalize", "assets done", self_check=(af.get("self_check") or {}).get("overall"),
              diff_pass=(af.get("diff_report") or {}).get("pass_items"))
    if (af.get("self_check") or {}).get("stage") != "full" and status == "ok":
        status = "partial"
    wj(OUT / "result.json", result_doc(case, idx, vals, status, errors, degr, changes, extra={
        "deliverables": {"presentation": "output/presentation.pptx", "preview_pdf": "output/preview.pdf",
                         "slide_plan_md": "output/slide_plan.md", "slide_plan_json": str(WORK / "slide_plan.json"),
                         "content_map": "output/content_map.json", "compliance": "output/compliance_checks.json"},
        "check_report": rep}))
    print(json.dumps({"status": status, "slides": n, "mode": info.get("mode"),
                      "quotes": [rep["quotes_verified"], rep["quotes_checked"]], "pdf_pages": pages,
                      "checks": {k: v.get("pass") for k, v in chk.items() if isinstance(v, dict) and "pass" in v and v.get("pass") is not None},
                      "degradations": degr, "seconds": el()}, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="slides-03 academic talk organiser (init|show|check|build)")
    ap.add_argument("cmd", nargs="?", default="init", choices=["init", "show", "check", "build"])
    ap.add_argument("--grep", help="show: regex filter over paragraphs")
    ap.add_argument("--material", help="show: material id, e.g. M1")
    ap.add_argument("--limit", type=int, help="show: max paragraphs per material")
    ap.add_argument("--plan", help="check/build: path to slide_plan.json")
    a = ap.parse_args()
    audit.log("start", "cmd=%s" % a.cmd, python=sys.version.split()[0])
    try:
        rc = {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[a.cmd](a)
        audit.log("exit", "rc=%s" % rc, seconds=el())
        return rc
    except SystemExit:
        raise
    except Exception as e:
        try:
            audit.log("fatal", repr(e)[:300], tb=traceback.format_exc()[-600:])
            partial({"uncertainty": ["fatal: %r" % (e,)]})
        except Exception:
            pass
        print("error: %r (legal partial result.json written)" % (e,))
        return 0
    finally:
        try:
            audit.flush_log(OUT)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

