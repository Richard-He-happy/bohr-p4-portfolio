#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Methods & statistics review engine (see --help for usage)."""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
import verify as V

VER = "1.0.0"
T0 = time.time()
CATS = V.CATS
SKIP = {"__pycache__", ".git", "node_modules", ".venv", "output"}

D = "\u3002\uff01\uff1f!?;\n"
CAP = {"error": .97, "gap": .75, "judgment": .8}
NP = r"(?<![A-Za-z])[nN]\s*=\s*(\d{2,6})"


def snip(t, m, w=190):
    """Verbatim sentence window around a match; truncation is marked with an ellipsis."""
    a, b = m.start(), m.end()
    s = max([t.rfind(d, 0, a) for d in D] + [-1])
    s = s + 1 if s >= 0 else 0
    e = min([x for x in (t.find(d, b) for d in D) if x >= 0] + [len(t)])
    seg = t[s:e].strip()
    if len(seg) > w:
        seg = t[max(0, a - 60):min(len(t), b + 110)].strip() + "\u2026"
    if len(seg) < 12:
        seg = t[max(0, a - 20):min(len(t), b + 45)].strip()
    return re.sub(r"\s+", " ", seg)


def neg(t, i):
    """A negated/conditional trigger is discussion, not a defect (guard 3)."""
    return re.search(r"(\u4e0d|\u672a|\u65e0\u9700|not |no |without|if |\u662f\u5426)\s*$",
                     t[max(0, i - 12):i], re.I) is not None


def mk(r, c, p, q, add="", sev=None, reason=None, ev=None, conf=None):
    return {"rule_id": r["id"], "category": r["cat"], "facet": r["facet"], "defect_type": r["dt"],
            "severity": sev or r["sev"], "evidence_strength": r["es"], "title": r["title"],
            "locator": p["locator"] if p else "", "quote": q,
            "reason": (reason or r["reason"]) + ("\uff08" + add + "\uff09" if add else ""),
            "suggestion": r["sug"], "evidence": ev or {"kind": "contrast", "support": r.get("terms", "")},
            "confidence": min(r["cf"] if conf is None else conf, CAP[r["es"]]),
            "source_id": p["doc_id"] if p else c.primary}


def d_xref(c, r):
    """F-01: a referenced table/figure number that no caption defines."""
    dt, df = set(), set()
    for p in c.body:
        s = p["text"].strip()
        if re.search(r"\u663e\u793a|\u53ef\u89c1|\u5217\u51fa|shows?|summari", s, re.I):
            continue
        m = re.match(r"(\u8868|Table)\s*(\d+)", s, re.I)
        if m:
            dt.add(m.group(2))
        m = re.match(r"(\u56fe|Figure|Fig\.?)\s*(\d+)", s, re.I)
        if m:
            df.add(m.group(2))
    out = []
    for lb, ds, rx in (("\u8868", dt, r"(\u8868|Table)\s*(\d+)"), ("\u56fe", df, r"(\u56fe|Figure|Fig\.?)\s*(\d+)")):
        for p in c.body:
            if not ds or re.match(r"(\u8868|Table|\u56fe|Figure|Fig)", p["text"].strip(), re.I):
                continue
            m = next((m for m in re.finditer(rx, p["text"], re.I) if m.group(2) not in ds), None)
            if m:
                out.append(mk(r, c, p, snip(p["text"], m), "defined %s=%s" % (lb, sorted(ds, key=int)), conf=.8,
                              ev={"kind": "absence", "support": "%s captions: %s" % (lb, sorted(ds, key=int))}))
    return out[:6]


def d_sample(c, r):
    """F-02: one manuscript reporting two different sample sizes."""
    v = [(int(m.group(1)), p, snip(p["text"], m)) for p in c.body for m in re.finditer(NP, p["text"])]
    if len(v) < 2:
        return []
    ns = sorted(x[0] for x in v)
    if ns[-1] - ns[0] <= max(3, .05 * ns[-1]) or c.has(
            r"\u5931\u8bbf|\u8131\u843d|\u6392\u9664|excluded|flow|\u6d41\u7a0b\u56fe|\u5254\u9664"):
        return []
    a, b = v[0], max(v, key=lambda x: x[0])
    return [mk(r, c, a[1], a[2], "also n=%d at %s" % (b[0], b[1]["locator"]), conf=.8,
               reason="n=%d and n=%d appear with no attrition note, so neither the analysed sample nor the degrees of "
                      "freedom can be checked." % (a[0], b[0]),
               ev={"kind": "contrast", "support": "n=%d at %s" % (b[0], b[1]["locator"])})]


def d_sig(c, r):
    """S-02: significance claim contradicting the p value in the same paragraph."""
    for p in c.body:
        hi = re.search(r"[Pp]\s*=\s*0?\.(?:0[5-9]|[1-9]\d*)|[Pp]\s*>\s*0\.05", p["text"])
        sg = re.search(r"\u663e\u8457(?:\u5347\u9ad8|\u964d\u4f4e|\u589e\u52a0|\u51cf\u5c11|\u6539\u5584|\u5dee\u5f02|"
                       r"\u4f18\u4e8e|\u76f8\u5173)|significant(?:ly)? (?:increase|decrease|higher|lower|improve)",
                       p["text"], re.I)
        ng = re.search(r"\u65e0(?:\u7edf\u8ba1\u5b66)?\u663e\u8457|\u4e0d\u663e\u8457|no significant|not significant",
                       p["text"], re.I)
        lo = re.search(r"[Pp]\s*[<=\u2264]\s*0?\.0[0-4]\b", p["text"])
        if hi and sg and not ng:
            return [mk(r, c, p, snip(p["text"], sg), "p in paragraph: " + hi.group(0).strip(), conf=.75,
                       reason="The paragraph claims a significant effect but its p value is %s (>=0.05)."
                              % hi.group(0).strip(),
                       ev={"kind": "contrast", "support": hi.group(0).strip()})]
        if ng and lo and not re.search(r"\u4f46|however|\u7136\u800c", p["text"], re.I):
            return [mk(r, c, p, snip(p["text"], ng), "p in paragraph: " + lo.group(0).strip(), conf=.7,
                       reason="The paragraph states no significant difference while reporting p=%s (<0.05)."
                              % lo.group(0).strip(), ev={"kind": "contrast", "support": lo.group(0).strip()})]
    return []


def d_multi(c, r):
    """S-04: 3+ between-group comparisons with no multiplicity control."""
    pv = r"[Pp]\s*[=\u2264<>]\s*0?\.\d"
    hits = [p for p in c.body if re.search(pv, p["text"]) and re.search(
        r"\bvs\.?\b|\u4e0e.{0,12}\u7ec4(?:\u6bd4\u8f83|\u76f8\u6bd4)|compared (?:with|to)|\u7ec4\u95f4\u6bd4\u8f83",
        p["text"], re.I)]
    if len(hits) < 3:
        return []
    n = len(hits)
    disc = c.has(r"\u591a\u91cd\u6bd4\u8f83|Bonferroni|Holm|Tukey|Benjamini|\bFDR\b|\u6821\u6b63\u540e")
    return [mk(r, c, hits[0], snip(hits[0]["text"], re.search(pv, hits[0]["text"])),
               sev="suggestion" if disc else r["sev"], conf=.7,
               reason=("%d comparisons with p values; correction language exists, verify its coverage." % n if disc else
                       "%d comparisons with p values and no multiplicity correction anywhere; at alpha=0.05 the chance of "
                       "at least one false positive is about %.0f%%." % (n, (1 - .95 ** n) * 100)),
               ev={"kind": "absence", "support": "searched: multiplicity|Bonferroni|Holm|Tukey|FDR"})]


def d_refs(c, rules):
    """C-01 (number beyond the list) and C-02 (numbering gap)."""
    rs = sorted([r for r in rules if r["id"] in ("C-01", "C-02")], key=lambda r: r["id"])
    if not c.refs or len(rs) != 2:
        return []
    ns = [int(m.group(1)) for p in c.refs
          if (m := re.match(r"\s*\[?(\d{1,3})\]?[\.\)\u3001]?\s", p["text"]))]
    mx = max(ns) if ns else len(c.refs)
    bm, bp = 0, None
    for p in c.body:
        for m in re.finditer(r"\[(\d{1,3})(?:\s*[-\u2013,\uff0c]\s*(\d{1,3}))?\]", p["text"]):
            v = max(int(m.group(1)), int(m.group(2) or 0))
            if v > bm:
                bm, bp = v, (p, m)
    out = []
    if bp and bm > mx:
        out.append(mk(rs[0], c, bp[0], snip(bp[0]["text"], bp[1]), "list max=%d entries=%d" % (mx, len(c.refs)),
                      conf=.85, ev={"kind": "contrast", "support": "max entry=%d; entries=%d" % (mx, len(c.refs))},
                      reason="In-text citation [%d] exceeds the reference list (largest entry %d of %d), so that claim "
                             "has no retrievable source." % (bm, mx, len(c.refs))))
    miss = sorted(set(range(1, mx + 1)) - set(ns)) if ns else []
    if miss:
        p = c.refs[0]
        out.append(mk(rs[1], c, p, snip(p["text"], re.search(r"\S", p["text"])), conf=.8,
                      reason="Reference numbering has gaps (%s missing of 1..%d), so in-text numbers can point at the "
                             "wrong entry." % (", ".join(map(str, miss[:8])), mx),
                      ev={"kind": "numerical", "support": "present=%s missing=%s" % (ns[:12], miss[:12])}))
    return out


CUSTOM = {"xref": d_xref, "sample": d_sample, "sigconf": d_sig, "multi": d_multi}


def run_p(c, r):
    out, rx = [], re.compile(r["pat"], re.I)
    for p in c.body:
        for m in rx.finditer(p["text"]):
            if neg(p["text"], m.start()) or (r.get("guard_para") and re.search(r["guard_para"], p["text"], re.I)):
                continue
            out.append(mk(r, c, p, snip(p["text"], m)))
            break
        if len(out) >= r.get("cap", 2):
            break
    return out


def run_a(c, r):
    if (c.short and r.get("skip_short")) or c.has(r.get("guard_global")) or not c.has(r["need"]):
        return []
    if r["absent"] and re.search(r["absent"], ALLT, re.I):      # headings/end matter count as present
        return []
    m = c.find(r["need"], 1)
    if not m:
        return []
    sev = r["sev_if"]["sev"] if r.get("sev_if") and c.has(r["sev_if"]["re"]) else r["sev"]
    return [mk(r, c, m[0][0], snip(m[0][0]["text"], m[0][1]), sev=sev,
               add="searched %s; no hit in %d paragraphs" % (r["terms"], len(c.body)),
               ev={"kind": "absence", "support": "searched: " + r["terms"]})]


def run_t(c, r):
    if c.short or c.has(r["absent"]) or not c.body:
        return []
    p = c.tail()
    return [mk(r, c, p, snip(p["text"], re.search(r"\S", p["text"])),
               add="searched: %s over the whole text; the closing paragraph is only the locator" % r["terms"], ev={"kind": "absence", "support": "searched: " + r["terms"]})]


def detect(c, rules):
    out, errs = [], []
    for r in rules:
        try:
            k = r["kind"]
            if k == "manual":
                continue
            if k in CUSTOM:
                out += CUSTOM[k](c, r) or []
            elif k in ("refmax", "refgap"):
                out += d_refs(c, rules)
            elif k == "presence":
                if not (r.get("guard_global") and c.has(r["guard_global"])):
                    out += run_p(c, r)
            elif k == "tail":
                out += run_t(c, r)
            elif k == "absence":
                out += run_a(c, r)
        except Exception as e:
            errs.append("%s:%s" % (r.get("id"), str(e)[:70]))
    return out, errs


def load():
    try:
        t = (H.parent / "references" / "stat_rules.md").read_text("utf-8")
        b = re.search(r"<!--RULES-JSON(.*?)END-RULES-JSON-->", t, re.S).group(1)
        rs = [json.loads(x) for x in b.splitlines() if x.strip().startswith("{")]
        return (rs, "") if rs else ([], "rule_catalog_empty")
    except Exception as e:
        return [], "rule_catalog_load_failed:%s" % e


def discover(inp):
    cj, w, case = inp / "case.json", [], {}
    if not cj.is_file():
        cs = sorted(list(inp.rglob("case*.json"))[:12], key=lambda p: p.stat().st_mtime, reverse=True)
        cj = cs[0] if cs else None
    if cj:
        try:
            case = json.loads(V.dec(cj.read_bytes()))
        except Exception as e:
            w.append("case_json_parse_error:%s" % e)
    return (case if isinstance(case, dict) else {}), cj, w


def collect(inp, case, w):
    found, docs = [], []
    files = [p for p in sorted(inp.rglob("*")) if p.is_file() and p.name != "case.json"
             and not any(s in p.parts for s in SKIP)] if inp.is_dir() else []
    for p in files[:300]:
        t, parser, kind, deg = V.extract(p, w)
        found.append({"path": str(p), "bytes": p.stat().st_size, "kind": kind, "parser": parser,
                      "chars": len(t), "degradation": deg})
        if t.strip():
            docs.append(V.build_doc("doc-%03d" % (len(docs) + 1), p.name, kind, t, parser))
    for k, v in case.items():
        if isinstance(v, str) and len(v) > 400 and re.search(
                r"method|\u65b9\u6cd5|result|\u7ed3\u679c|abstract|\u6458\u8981|statist", v, re.I):
            docs.append(V.build_doc("doc-%03d" % (len(docs) + 1), k, "inline", v, "case-json-inline"))
            w.append("inline_text_used:%s" % k)
    return found, docs


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Methods & statistics review: extract text, run the 6-category / 5-facet checklist, emit result.json.",
        epilog="exit code is always 0; failures are reported inside result.json")
    ap.add_argument("--run", action="store_true", help="stage 1: extract + checklist + partial result")
    ap.add_argument("--input", default="", help="input dir (default /input, else ./input)")
    ap.add_argument("--output", default="", help="output dir (default /app/output)")
    ap.add_argument("--merge", default="", help="issues_model.json from stage 2")
    a = ap.parse_args(argv)
    if not (a.run or a.merge):
        ap.print_help()
        return 0
    out = Path(a.output) if a.output else (Path("/app/output") if Path("/app/output").is_dir() else Path("output"))
    inp = Path(a.input) if a.input else (Path("/input") if Path("/input").is_dir() else Path("input"))
    res = {"case_id": "unknown", "status": "partial", "topic": "methods-and-statistics-review", "skill_version": VER,
           "sources": [], "uncertainty": [], "pending_human": [], "errors": [], "degradations": [], "changes": [],
           "issues": [], "checks": {}, "review_records": {}, "input_inventory": {}}
    V.write_json(out / "result.json", res)              # legal partial result before anything risky
    case, cj, warns = discover(inp)
    res["case_id"] = str(case.get("case_id") or case.get("id") or "unknown")
    if not case:
        pe = next((w for w in warns if w.startswith("case_json_parse_error")), "")
        if pe:
            res["degradations"].append({"capability": "case_json", "code": "case_json_parse_error", "detail": pe})
        else:
            res["errors"].append({"stage": "discover", "code": "case_json_unavailable",
                                  "detail": "no case.json under %s" % inp})
    if ERR0:
        res["errors"].append({"stage": "rules", "code": "rule_catalog_load_failed", "detail": ERR0})
    found, docs = collect(inp, case, warns)
    res["input_inventory"] = {"input_dir": str(inp), "case_json": str(cj) if cj else None, "discovered": found,
                              "missing": [] if found else ["no material under the input dir"]}
    contract = case.get("output_contract")
    if not docs:
        res["status"] = "insufficient_evidence" if case else "input_error"
        res["uncertainty"].append({"what": "no parsable manuscript text",
                                   "why": "no text material, or the material is a scan/image and this skill has no OCR",
                                   "impact": "all six review categories were not executed",
                                   "resolved_by": "provide a text-based PDF/DOCX/MD or OCR output"})
        res["degradations"].append({"capability": "text_extraction", "fallback": "none",
                                    "detail": "; ".join(map(str, warns[:6])) or "no material"})
        res["checks"] = {k: {"status": "not_checked", "scope": "no text", "items": [], "findings": []}
                         for k in CATS}
        V.backfill(contract, res)
        V.finalize(res, [], out)
        print("status=%s issues=0 docs=0" % res["status"])
        return 0
    global ALLT
    ALLT = V.norm("\n".join(d["text"] for d in docs))       # raw text incl. headings and end matter
    c = V.Ctx(docs)
    issues, derr = detect(c, RULES)
    merged = 0
    if a.merge:
        issues, merged, merr = V.merge_model(c, issues, Path(a.merge), res["pending_human"])
        if merr:
            res["degradations"].append({"capability": "merge", "detail": merr})
    keep = []
    for it in V.dedupe(issues):
        V.confidence_cap(it)
        if V.verify_quote(it.get("quote", ""), docs).get("ok"):
            it["_quote_ok"] = True
            keep.append(it)
        else:
            res["pending_human"].append({"item": "%s %s" % (it["rule_id"], it["title"]),
                                         "why": "quote not verbatim", "action": "re-quote verbatim"})
    res["issues"] = V.renumba(keep)
    res["checks"] = V.checks(c, res["issues"], derr, RULES)
    res["sources"] = [{"id": d["id"], "path": d["path"], "kind": d["kind"], "parser": d["parser"],
                       "chars": d["chars"]} for d in docs]
    man = [i for k in CATS for i in res["checks"][k]["items"] if i["status"] == "manual"]
    if man:
        res["uncertainty"].append({
            "what": "%d judged items not covered in stage 1 (%s)" % (len(man), ", ".join(i["rule_id"] for i in man[:8])),
            "why": "they need semantic judgement (conclusion strength, cross-section consistency, design fit)",
            "impact": "argument-chain defects may be under-reported",
            "resolved_by": "stage 2: read output/extracted/*.md, write issues_model.json, run --merge"})
    if c.short:
        res["uncertainty"].append({"what": "material is short (%d chars)" % c.chars,
                                   "why": "absence-type checks are unreliable on short text",
                                   "impact": "S-03/S-05/S-08/D-01/D-04/E-01 suppressed", "resolved_by": "full text"})
    for d in found:
        if d["kind"] == "image" or d["degradation"] == "pdf_text_unavailable":
            res["pending_human"].append({"item": d["path"], "why": "image/scan has no extractable text (no OCR)",
                                         "action": "read it manually; the skill never guesses figure content"})
            res["uncertainty"].append({"what": "%s not read" % Path(d["path"]).name, "why": "no OCR/vision",
                                       "impact": "that figure content is unreviewed", "resolved_by": "text or OCR"})
    res["review_records"]["parser_warnings"] = [str(w)[:180] for w in warns if w][:30]
    res["review_records"]["checklist"] = {"rules_loaded": len({r["id"] for r in RULES}), "detector_errors": derr[:8],
                                          "manual_rule_ids": [i["rule_id"] for i in man]}
    res["review_records"]["limits"] = ["no OCR: images/scans unreviewed",
                                       "page numbers follow pdftotext paging; stdlib fallback has none",
                                       "absence checks use keywords and can miss synonyms"]
    if derr:
        res["degradations"].append({"capability": "detector", "detail": "; ".join(derr[:5])})
    res["status"] = ("insufficient_evidence" if c.short else
                     "ok" if (not man or merged) and not res["pending_human"] else "partial")
    try:
        V.extras(out, docs, man)
    except Exception as e:
        res["degradations"].append({"capability": "extracted_md", "detail": str(e)})
    res["changes"].append({"stage": "stage1", "issues": len(res["issues"]), "merged": merged})
    res["runtime"] = {"engine": "python-stdlib", "elapsed_s": round(time.time() - T0, 1), "docs": len(docs),
                      "chars": c.chars, "rules": len({r["id"] for r in RULES}), "version": VER}
    V.backfill(contract, res)
    V.finalize(res, docs, out)
    print("status=%s issues=%d docs=%d chars=%d -> %s"
          % (res["status"], len(res["issues"]), len(docs), c.chars, out / "result.json"))
    return 0


RULES, ERR0 = load()
ALLT = ""

def fatal():
    """Last resort: a legal partial result instead of a crash."""
    try:
        V.write_json((Path("/app/output") if Path("/app/output").is_dir() else Path("output")) / "result.json",
                     {"case_id": "unknown", "status": "partial", "skill_version": VER, "issues": [], "checks": {},
                      "sources": [], "pending_human": [], "degradations": [], "changes": [], "uncertainty": [
                          {"what": "run interrupted", "why": "unhandled exception", "impact": "no valid review sheet",
                           "resolved_by": "inspect errors[]"}],
                      "errors": [{"stage": "fatal", "code": "unhandled_exception", "detail": traceback.format_exc()[-700:]}]})
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        traceback.print_exc()
        fatal()
    sys.exit(0)
