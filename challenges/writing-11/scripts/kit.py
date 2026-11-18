#!/usr/bin/env python3
"""Material extraction, paragraph index, draft checks, result assembly.

Imported by main.py. Stdlib only, no network, CWD-independent; one bad file
degrades that item only, never the run.
"""

import json
import re
import sys
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
UNIT = re.compile(r"(?:%|‰|°C|mg|kg|mL|mM|µM|μM|nM|min|kPa|MPa|nm|µm|μm|kDa|Da|Hz|Gy|Sv)\b")
CIT = re.compile(r"\[\s*\d+(?:\s*[-,–]\s*\d+)*\s*\]|\(\s*[A-Z][^()]{0,80}?\b(?:19|20)\d{2}[a-z]?\s*\)")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CAP = re.compile(r"^(?:fig(?:ure)?\.?|tab(?:le)?\.?|scheme|chart|图|表|附表|附图)\s*[\dIVXivx]")
REF = re.compile(r"^(?:\[\d+\]|\d+\.\s+[A-Z])")
ACR = re.compile(r"\b[A-Z][A-Z0-9]{1,7}\b")
ENCS = ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ")).strip()


def norm_key(s):
    return norm(s).lower()


def tfound(tgt, tr):
    """Term present in a translation, tolerating inflection (photocatalysis/photocatalytic)."""
    t, s = norm_key(tgt), norm_key(tr)
    if t and t in s:
        return True
    w = [x for x in re.findall(r"[a-z]+|[\u4e00-\u9fff]+", t) if len(x) > 3]
    return bool(w) and all(x[:6] in s for x in w)


def num_tokens(t):
    t = CIT.sub(" ", t or "")
    return [m.group(0).replace(",", "") for m in NUM.finditer(t)
            if not t[m.start() - 1:m.start()].isalpha()]


def num_ok(n, toks):
    """True when a source number lands in the target, allowing 10^4/10^8 rescaling."""
    if n in toks:
        return True
    try:
        v = float(n)
    except Exception:
        return False
    return any("%g" % (v * m) in toks for m in (1e4, 1e8, 1e-4, 1e-8))


def cjk_ratio(t):
    t = re.sub(r"\s", "", t or "")
    return len(CJK.findall(t)) / len(t) if t else 0.0


def rtext(p):
    try:
        raw = Path(p).read_bytes()
    except Exception:
        return ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except Exception:
            pass
    for e in ENCS:
        try:
            return raw.decode(e)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def rjson(p):
    t = rtext(p)
    try:
        return json.loads(t) if t.strip() else None
    except Exception:
        return None


def wjson(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def wtext(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s if s.endswith("\n") else s + "\n", encoding="utf-8")
    return p


# extractors
def _unesc(b):
    o, i = [], 0
    while i < len(b):
        if b[i] == 0x5C and i + 1 < len(b):
            n = b[i + 1]
            if n in (0x6E, 0x72, 0x74):
                o.append({0x6E: 10, 0x72: 13, 0x74: 9}[n])
                i += 2
                continue
            if 0x30 <= n <= 0x37:
                m = re.match(rb"[0-7]{1,3}", b[i + 1:i + 4])
                o.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            o.append(n)
            i += 2
            continue
        o.append(b[i])
        i += 1
    return bytes(o)


def _pdfops(d):
    o = []
    for m in re.finditer(rb"\((?:\\.|[^()\\])*\)|\bT[dDJj*]\b|\bET\b|\bBT\b", d):
        t = m.group(0)
        if t.startswith(b"("):
            o.append(_unesc(t[1:-1]).decode("latin-1"))
        elif t in (b"BT", b"Tj", b"TJ"):
            o.append(" ")
        else:
            o.append("\n")
    return "".join(o)


def pdftext(p):
    try:
        data = Path(p).read_bytes()
    except Exception:
        return ""
    ch = []
    for m in re.finditer(rb"stream\r?\n", data):
        e = data.find(b"endstream", m.end())
        if e < 0:
            continue
        raw = data[m.end():e]
        out = b""
        for a in (raw, raw.strip(b"\r\n")):
            try:
                out = zlib.decompress(a)
                break
            except Exception:
                try:
                    out = zlib.decompressobj().decompress(a)
                    break
                except Exception:
                    out = b""
        if out and (b"Tj" in out or b"TJ" in out):
            t = _pdfops(out)
            if t.strip():
                ch.append(t)
    return "\n\n".join(ch)


def docxtext(p):
    try:
        with zipfile.ZipFile(p) as z:
            x = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return ""
    from html import unescape
    return unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n\n", re.sub(r"<w:(?:tab|br)[^>]*/>", " ", x))))


def extract(p):
    """-> (text, kind, quality, note); never raises."""
    p = Path(p)
    try:
        h = p.read_bytes()[:8]
    except Exception:
        return "", "unreadable", "unreadable", "cannot open file"
    if h[:4] == b"%PDF":
        t = pdftext(p)
        ok = len(t.strip()) > 200
        return t, "pdf", "ok" if ok else "low", "" if ok else "thin/CID text layer; check the page"
    if h[:2] == b"PK":
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
        except Exception:
            names = []
        if any(n.startswith("word/") for n in names):
            return docxtext(p), "docx", "ok", ""
        return "", "office", "low", "office package not text-extracted; open directly"
    if h[:8] == b"\x89PNG\r\n\x1a\n" or h[:2] == b"\xff\xd8":
        return "", "image", "unreadable", "raster image: read visually, do not guess"
    t = rtext(p)
    if p.suffix.lower() in (".html", ".htm"):
        from html import unescape
        t = unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", t)))
        return t, "html", "ok", ""
    return t, "text", "ok" if t.strip() else "low", ""


# discovery
def dirs(a):
    def pick(g, d1, d2):
        return Path(g) if g else (Path(d1) if Path(d1).exists() else Path(d2))
    return pick(a.input, "/input", "input"), pick(a.work, "/app/work", "work"), pick(a.output, "/app/output", "output")


def find_case(d):
    c = [d / n for n in ("case.json", "input.json", "task.json") if (d / n).is_file()] if d.is_dir() else []
    if d.is_dir():
        c += [p for p in sorted(d.rglob("case*.json")) if p not in c]
    for p in c:
        o = rjson(p)
        if isinstance(o, dict):
            return o, p
    return {}, (c[0] if c else None)


def fields(case):
    def find(*pat, d=None):
        for k, v in (case or {}).items():
            if any(x in str(k).lower() for x in pat) and v not in (None, "", [], {}):
                return v
        return d
    oc = case.get("output_contract")
    return {"case_id": case.get("case_id") or case.get("id") or find("case_id"),
            "instruction": find("instruction", "brief", "request", "task_desc", "prompt", "workorder"),
            "contract": oc if isinstance(oc, dict) else (find("contract", d={}) or {}),
            "scope": find("scope", "constraint", "requirement", "audience", "style"),
            "terms": find("glossary", "locked_term", "terminolog", "termbase", d=[])}


def mats(d, case):
    seen, out = set(), []
    roots = [d] + ([d / x for x in ("artifacts", "materials", "resources", "files")] if d.is_dir() else [])
    for r in roots:
        if r.is_dir():
            for p in sorted(r.rglob("*")):
                if p.is_file() and not p.name.startswith(".") and "__pycache__" not in p.parts \
                    and p.name not in ("case.json", "input.json", "task.json") and p not in seen:
                    seen.add(p)
                    out.append(p)
    for k in ("formal_inputs", "artifacts", "materials", "runtime_files"):
        v = (case or {}).get(k)
        for it in (v if isinstance(v, list) else ([v] if v else [])):
            q = it if isinstance(it, str) else (it.get("path") if isinstance(it, dict) else "")
            c = (d / q) if q else None
            if c and c.is_file() and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def paras(text, mx=1200):
    out = []
    for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        b = b.strip().lstrip("#").strip()
        if not b or re.fullmatch(r"!\[[^\]]*\]\([^)]*\)", b):
            continue
        if len(b) <= mx:
            out.append(b)
            continue
        buf = ""
        for s in re.split(r"(?<=[.!?。！？；;])\s*|(?<=。)", b):
            if not s.strip():
                continue
            if len(buf) + len(s) > mx and buf:
                out.append(buf.strip())
                buf = s
            else:
                buf += s
        if buf.strip():
            out.append(buf.strip())
    return out


def pkind(t):
    t = t.strip().lstrip("#").strip()
    if CAP.match(t):
        return "caption"
    if t.lower().startswith(("reference", "references", "bibliography", "参考文献")):
        return "heading"
    if REF.match(t) and len(t) < 600:
        return "reference"
    if len(t) < 120 and not t.endswith(("。", ".", ";", "；", ":")):
        return "heading"
    return "formula" if ("$" in t or (len(t) < 60 and not t.endswith("。") and re.search(r"[=≈≤≥]\s*\S", t))) else "body"


def index_input(d, case, f):
    ms, ps, wn, ac, n = [], [], [], {}, 0
    for path in mats(d, case):
        t, k, q, note = extract(path)
        if not t.strip():
            ms.append({"id": None, "path": str(path), "name": path.name, "kind": k, "quality": q,
                       "chars": 0, "paras": 0, "note": note})
            if note:
                wn.append("%s: %s" % (path.name, note))
            continue
        n += 1
        mid, pp = "M%d" % n, paras(t)
        ms.append({"id": mid, "path": str(path), "name": path.name, "kind": k, "quality": q,
                   "chars": len(t), "paras": len(pp), "note": note})
        for i, x in enumerate(pp, 1):
            ps.append({"para_id": "%s-P%03d" % (mid, i), "material": mid, "material_name": path.name,
                       "material_path": str(path), "locator": "%s:%s#P%03d" % (mid, path.name, i),
                       "kind": pkind(x), "chars": len(x), "text": x})
            for a in ACR.findall(x):
                ac[a] = ac.get(a, 0) + 1
    lt = f.get("terms") or []
    if isinstance(lt, dict):
        lt = [{"term": k, "target": v} for k, v in lt.items()]
    return {"case_id": str(f.get("case_id") or "unknown"), "created": now(), "instruction": f.get("instruction"),
            "contract_keys": list((f.get("contract") or {}).keys()), "contract": f.get("contract") or {},
            "materials": ms, "paragraphs": ps,
            "supplied_terms": lt, "warnings": wn,
            "term_candidates": [{"term": k, "count": v} for k, v in
                                sorted(ac.items(), key=lambda kv: (-kv[1], kv[0]))[:40]]}


# draft check
def load_draft(work, explicit=None):
    """-> (draft, path, seen). Never raises; ignores templates and system files."""
    seen, order = [], []
    if explicit:
        order.append(Path(explicit))
    for n in ("workdraft.json", "draft.json", "translation_draft.json"):
        order.append(Path(work) / n)
    w = Path(work)
    if w.is_dir():
        order += [p for p in sorted(w.rglob("*.json"))
                  if p.name not in ("index.json", "check_report.json", "result.json")
                  and "template" not in p.name.lower()]
    for p in order:
        if p in seen or not p.is_file():
            continue
        seen.append(p)
        o = rjson(p)
        if isinstance(o, dict) and isinstance(o.get("paragraphs"), list) and o["paragraphs"]:
            return o, str(p), [str(x) for x in seen]
    return None, None, [str(x) for x in seen]


def validate(index, draft):
    """Compare the Agent draft with the paragraph index. Never raises."""
    rep = {"checked": False, "verdict": "fail", "glossary_size": 0,
           "coverage": {"expected": 0, "covered": 0, "ratio": 0.0, "missing_para_ids": []},  # set below
           "quote_issues": [], "number_issues": [], "citation_issues": [], "term_issues": [],
           "empty_translations": [], "duplicate_para_ids": [], "unknown_para_ids": [], "notes": []}
    if not isinstance(index, dict):
        rep["notes"].append("no index")
        return rep
    if not isinstance(draft, dict):
        rep["notes"].append("no draft")
        return rep
    rep["checked"] = True
    ps = index.get("paragraphs") or []
    by_id = {p.get("para_id"): p for p in ps if p.get("para_id")}
    items = [it for it in draft.get("paragraphs") or [] if isinstance(it, dict) and it.get("para_id")]
    ids = [it["para_id"] for it in items]
    rep["duplicate_para_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    rep["unknown_para_ids"] = sorted({i for i in ids if i not in by_id})
    trs = {it["para_id"]: it.get("translation") for it in items}
    missing = [p["para_id"] for p in ps if p["para_id"] not in trs]
    ok = {i for i, v in trs.items() if norm(v)}
    rep["coverage"] = {"expected": len(ps), "covered": len(ok),
                       "ratio": round(len(ok) / len(ps), 3) if ps else 0.0,
                       "missing_para_ids": missing[:50]}
    gl = [g for g in (draft.get("glossary") or []) if isinstance(g, dict) and g.get("term")]
    rep["glossary_size"] = len(gl)
    for it in items:
        pid, ix = it.get("para_id"), by_id.get(it.get("para_id"))
        if not ix:
            continue
        q, src = it.get("source_quote"), ix.get("text", "")
        tr = it.get("translation") if isinstance(it.get("translation"), str) else ""
        if not norm(tr):
            rep["empty_translations"].append(pid)
        if isinstance(q, str) and norm(q) and norm_key(q) not in norm_key(ix.get("text", "")):
            rep["quote_issues"].append({"para_id": pid, "issue": "quote not verbatim",
                                        "locator": ix.get("locator")})
        tnum = set(num_tokens(tr))
        miss = [n for n in dict.fromkeys(num_tokens(src)) if not num_ok(n, tnum)]
        if miss:
            rep["number_issues"].append({"para_id": pid, "missing": miss[:20], "locator": ix.get("locator")})
        elif UNIT.search(src) and not UNIT.search(tr):
            rep["number_issues"].append({"para_id": pid, "missing": ["unit:" + UNIT.search(src).group(0)],
                                         "locator": ix.get("locator"), "source": norm(src)[:160]})
        for c in dict.fromkeys(CIT.findall(src or "")):
            if norm(c) not in norm(tr):
                rep["citation_issues"].append({"para_id": pid, "marker": norm(c), "locator": ix.get("locator")})
        for g in gl:
            term, tgt = g.get("term") or "", g.get("target") or ""
            if term and tgt and norm_key(term) in norm_key(src) and not tfound(tgt, tr):
                rep["term_issues"].append({"para_id": pid, "term": term, "expected": tgt,
                                           "locator": ix.get("locator")})
    hard = (rep["quote_issues"] or rep["number_issues"] or rep["citation_issues"] or rep["term_issues"]
            or rep["empty_translations"] or rep["duplicate_para_ids"] or rep["coverage"]["ratio"] < 0.999)
    rep["verdict"] = "fail" if hard else "pass"
    return rep


# result
def cval(k, fl):
    lk = str(k).lower()
    for keys, role in (("golden", "golden_standard"), ("diff", "diff_report"), ("version", "version_history"),
                       ("self_check", "self_check"), ("selfcheck", "self_check"), ("run_log", "run_log"),
                       ("glossar", "glossary"), ("术语", "glossary"), ("align", "alignment"), ("对照", "alignment"),
                       ("preserv", "preserved_facts"), ("fact", "preserved_facts"), ("number", "preserved_facts"),
                       ("evidence", "evidence_map"), ("source_map", "evidence_map"), ("locator", "evidence_map"),
                       ("change", "change_log"), ("log", "change_log"), ("revision", "change_log"),
                       ("deliver", "deliverable"), ("translat", "deliverable"), ("manuscript", "deliverable"),
                       ("译文", "deliverable")):
        if keys in lk:
            return fl.get(role)
    for stem in fl:
        if stem in lk or lk in stem:
            return fl[stem]
    return None


def blank(cid, ctr, st, ver):
    r = {"case_id": cid, "status": st, "skill": "academic-translation-bilingual", "skill_version": ver,
         "deliverable": None, "preserved_facts": None, "evidence_map": None, "change_log": None,
         "glossary": None, "alignment": None, "sources": [], "uncertainty": [], "pending_human": [],
         "errors": [], "degradations": [], "changes": [], "runtime": {}}
    for k in (ctr if isinstance(ctr, dict) else {}):
        r.setdefault(k, None)
    return r


def assemble(ix, rep, gl, open_n, status, files, errs, degr, ent, used, ctr, cid, ver, elapsed):
    total = len(ix.get("paragraphs", []))
    unc = [{"item": "coverage", "detail": "translated units %d/%d" % (total - open_n, total)},
           {"item": "numbers", "detail": "%d paragraph(s) with digits/units not carried over"
            % len(rep.get("number_issues") or [])},
           {"item": "terms", "detail": "%d glossary term(s) missing from their paragraph target"
            % len(rep.get("term_issues") or [])},
           {"item": "quotes", "detail": "%d draft quote(s) not verbatim in source"
            % len(rep.get("quote_issues") or [])}]
    ph = [{"item": g["term"], "reason": "术语译名待确认（target 为空）", "locator": g.get("locator")}
          for g in gl if not g.get("target")]
    ph += [{"item": m.get("name"), "reason": m.get("note")} for m in ix.get("materials", [])
           if m.get("quality") in ("low", "unreadable")]
    if open_n:
        ph.append({"item": "untranslated_paragraphs", "reason": "%d 段无译文" % open_n,
                   "para_ids": (rep.get("coverage") or {}).get("missing_para_ids", [])})
    ph += [{"item": t.get("term"), "reason": "术语译名未在该段落地", "locator": t.get("locator")}
           for t in rep.get("term_issues") or []]
    ph += [{"item": "number:" + ",".join(x.get("missing", [])[:5]), "reason": "数字/单位未在译文出现，需核对",
            "locator": x.get("locator")} for x in rep.get("number_issues") or []]
    r = blank(cid, ctr, status, ver)
    r.update({"sources": [{k: m.get(k) for k in ("id", "name", "path", "kind", "quality", "note")}
                          for m in ix.get("materials", [])],
              "uncertainty": unc, "pending_human": ph, "errors": errs,
              "degradations": degr + (ix.get("warnings") or []), "changes": ent[:200],
              "term_issues": (rep.get("term_issues") or [])[:50],
              "number_issues": (rep.get("number_issues") or [])[:50],
              "quote_issues": (rep.get("quote_issues") or [])[:50],
              "metrics": {"materials": len(ix.get("materials", [])), "paragraphs_total": total,
                          "paragraphs_translated": total - open_n,
                          "coverage": (rep.get("coverage") or {}).get("ratio"),
                          "glossary_terms": len(gl),
                          "facts_checked": files.pop("_facts", 0), "facts_missing_in_target": files.pop("_miss", 0),
                          "check_verdict": rep.get("verdict")},
              "runtime": {"skill_version": ver, "python": sys.version.split()[0], "finished": now(),
                          "elapsed_sec": round(elapsed, 2), "phase": "build"}})
    for k, v in files.items():
        if k in r:
            r[k] = v
    for k in (ctr if isinstance(ctr, dict) else {}):
        if k not in ("case_id", "status"):
            r[k] = cval(k, files)
    lk = {}
    if isinstance(ctr, dict):
        lk = {str(k).lower(): k for k in ctr}
    if "result" in lk:
        r[lk["result"]] = {"deliverable": files.get("deliverable"), "metrics": r.get("metrics"),
                           "scaffold": "deterministic fallback kept the package non-empty; Agent draft improves units"}
    if "claims" in lk:
        r[lk["claims"]] = {"evidence_map": "evidence_map.json", "units": r["metrics"].get("paragraphs_total"),
                           "facts_checked": r["metrics"].get("facts_checked")}
    if "uncertainties" in lk:
        r[lk["uncertainties"]] = unc
    if "preserved_facts" in lk:
        r[lk["preserved_facts"]] = {"file": "preserved_facts.json", "count": r["metrics"].get("facts_checked")}
    if "evidence_map" in lk:
        r[lk["evidence_map"]] = {"file": "evidence_map.json", "units": r["metrics"].get("paragraphs_total")}
    if "change_log" in lk:
        r[lk["change_log"]] = {"file": "change_log.json", "entries": len(ent)}
    return r


def save_result(out, r, errs):
    for t in (Path(out) / "result.json", Path(out) / "result.partial.json"):
        try:
            wjson(t, r)
            return t
        except Exception as e:
            errs.append("result.json write failed (%s): %s" % (t, e))
    return None


if __name__ == "__main__":
    print("kit.py is the library behind scripts/main.py; run `python3 main.py --help` for commands.")
    print("public helpers: extract, index_input, load_draft, validate, assemble")
