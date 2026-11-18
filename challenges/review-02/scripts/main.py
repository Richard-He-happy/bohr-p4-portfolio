#!/usr/bin/env python3
"""review-fact-check :: pipeline entry — extraction, orchestration, report. stdlib only, no network.
  python3 scripts/main.py --input /input --output /app/output [--findings F]
Evidence engine, checks and contract echo: verify.py. Rules/templates: ../references/checks.json.
Writes result.json (partial first, finalized last), review_report.md, issues.csv,
evidence_index.json, citation_pairs.json, run.log. Exit code is always 0."""
import argparse, csv, json, os, re, shutil, subprocess, sys, time, zipfile, zlib
from pathlib import Path
H = Path(__file__).resolve().parent
RS = H.parent / "references"
sys.path.insert(0, str(H))
from verify import X, pats, crefs, cnums, pairs, merge, vcheck, fill, ws  # noqa: E402
NM, VR, T0 = "review-fact-check", "1.0.0", time.time()
KD = ["fact_check", "citation_support", "method_design", "stats_report", "argument_chain", "academic_norm"]
SV = ["major", "minor", "info"]
SKIP = {"case.json", "task.md", "material.json"}
TX = {".md", ".txt", ".tex", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".bib", ".yaml", ".yml", ".rst"}
IM = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
try:
    CAT = json.loads((RS / "checks.json").read_text(encoding="utf-8"))
except Exception:
    CAT = {}
SC, TPL = CAT.get("sections") or [], CAT.get("report") or {}
CSVF = CAT.get("csv_fields") or ["issue_id", "kind", "severity", "certainty", "status", "locator", "quote",
                                 "claim", "rule_id", "suggested_fix"]


def cl(t):
    t = (t or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()


def ue(s):
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        s = s.replace(a, b)
    return s


def wj(p, o):
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def r_ooxml(p, word):
    with zipfile.ZipFile(p) as z:
        names = [n for n in z.namelist() if n.endswith(".xml") and (
            ("word/document" in n) if word else ("sharedStrings" in n or "worksheets/sheet" in n))]
        raw = [z.read(n).decode("utf-8", "replace") for n in names]
    if not word:
        return ue(re.sub(r"<[^>]+>", " ", " ".join(raw)))
    x = " ".join(raw)
    return "\n\n".join(ue("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", q, re.S)))
                       for q in x.split("</w:p>") if "<w:t" in q)


def raw_pdf(p):
    d, o = p.read_bytes(), []
    for m in re.finditer(rb"stream\r?\n", d):
        try:
            x = zlib.decompress(d[m.end():d.find(b"endstream", m.end())])
        except Exception:
            continue
        if b"Tj" not in x and b"TJ" not in x:
            continue
        b = []
        for g in re.finditer(rb"\((?:\\.|[^\\()])*\)|[A-Za-z*']{1,3}\s", x):
            t = g.group(0)
            if t[:1] == b"(":
                b.append(re.sub(rb"\\([()\\])", rb"\1", t[1:-1]).replace(b"\\n", b" ").decode("utf-8", "replace"))
            elif t.strip() in (b"Td", b"TD", b"T*", b"ET", b"TJ", b"Tj"):
                b.append(" ")
        o.append("".join(b))
    return "\n".join(o)


def r_pdf(p):
    ex = shutil.which("pdftotext")
    for fl in ("-layout", "-raw") if ex else ():
        try:
            r = subprocess.run([ex, fl, "-enc", "UTF-8", str(p), "-"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=180)
            if r.returncode == 0 and len(r.stdout.strip()) > 40:
                return r.stdout.decode("utf-8", "replace"), "pdftotext" + fl
        except Exception:
            pass
    return raw_pdf(p), "stdlib-zlib"


def r_img(p):
    ex = shutil.which("tesseract")
    if not ex:
        return None, "ocr-unavailable"
    try:
        r = subprocess.run([ex, str(p), "stdout"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace"), "tesseract"
    except Exception:
        pass
    return None, "ocr-failed"


def mkdoc(i, rel, t, how, ext):
    t = cl(t)
    ch, pgs, p = t.split("\f"), [], 0
    for k, c in enumerate(ch):
        pgs.append({"l": ("p%d" % (k + 1)) if len(ch) > 1 else None, "s": p, "e": p + len(c)})
        p += len(c) + 1
    d = {"id": "D%d" % i, "name": rel, "ext": ext, "text": t, "extractor": how, "pages": pgs, "secs": [], "paras": []}
    for m in re.finditer(r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?([^\n:：]{2,58})[ \t]*$", t):
        h = ws(m.group(1)).lower()
        for k, pat in SC:
            if re.search(pat, h):
                d["secs"].append((k, m.start()))
                break
    q = 0
    for b in re.split(r"\n\s*\n", t):
        if b.strip():
            s = max(t.find(b, q), q)
            d["paras"].append({"s": s, "e": s + len(b), "t": b})
            q = s + len(b)
    return d


def corpus(inp, err, deg, src):
    out = []
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or p.name.lower() in SKIP:
            continue
        rel, ext, t, how = str(p.relative_to(inp)), p.suffix.lower(), None, "unsupported"
        try:
            if ext == ".pdf":
                t, how = r_pdf(p)
            elif ext == ".docx":
                t, how = r_ooxml(p, True), "docx-xml"
            elif ext in (".xlsx", ".xlsm"):
                t, how = r_ooxml(p, False), "xlsx-xml"
            elif ext in IM:
                t, how = r_img(p)
            elif ext in TX:
                t, how = p.read_text(encoding="utf-8", errors="replace"), "text"
        except Exception as e:
            err.append({"stage": "extract", "file": rel, "error": "%s: %s" % (type(e).__name__, str(e)[:140])})
            t, how = None, "error"
        if t and len(t.strip()) > 20:
            d = mkdoc(len(out) + 1, rel, t, how, ext)
            out.append(d)
            src.append({"id": d["id"], "name": rel, "extractor": how, "chars": len(d["text"])})
            if ext == ".pdf" and len(t.strip()) < 300:
                deg.append({"stage": "extract", "file": rel, "note": "little text: possible scanned PDF"})
        elif ext in IM:
            deg.append({"stage": "extract", "file": rel, "note": "image without OCR text (%s)" % how})
        elif ext not in TX:
            deg.append({"stage": "extract", "file": rel, "note": "unreadable (%s)" % how})
    return out


def reps(r, lang):
    """Render review_report.md from the template in references/checks.json."""
    s, b = r["review_summary"], r["review_summary"]["by_severity"]
    it = TPL.get("issue_" + lang) or TPL.get("issue_zh") or "{issue_id} {locator} {quote} {claim}"
    j = lambda xs: "\n".join(xs) if xs else "- none"
    parts = {
        "summary": "- %s docs, %s chars, %s findings: major %s / minor %s / info %s; pending %s." % (
            s["documents"], s["characters"], s["issues_total"], b["major"], b["minor"], b["info"], s["pending_human"]),
        "coverage": j("| %s | %s | %s |" % (k, ", ".join(s["coverage"][k]["rules"]) or "-",
                                            s["coverage"][k]["findings"]) for k in KD),
        "sources": j("- `%s` (%s, %d chars)" % (i["name"], i["extractor"], i["chars"]) for i in r["sources"]),
        "findings": j(it.format(**f) for f in r["issues"]),
        "matrix": j("| %s | `%s` | %s | %s |" % (p["pair_id"], p["claim_locator"], p["citation"], p["verdict"] or "-")
                    for p in r["citation_support_matrix"][:60]),
        "numeric": j("- `%s`: %s" % (k, v) for k, v in s["numeric_checks"].items()),
        "pending": j("- %s: %s (need: %s)" % (p.get("issue_id") or p.get("pair_id") or "-", p.get("why", ""),
                                              p.get("need", "")) for p in r["pending_human"]),
        "unchecked": j("- %s (%s): %s" % (u.get("item"), u.get("doc"), u.get("reason")) for u in r["uncertainty"]),
        "errors": j("- error `%s`: %s" % (e.get("file") or e.get("stage"), str(e.get("error"))[:160])
                    for e in r["errors"]),
        "degradations": j("- degradation `%s`: %s" % (e.get("file"), e.get("note")) for e in r["degradations"]),
        "runtime": "elapsed %.2fs / python %s / %d errors / %d degradations / verified=%s" % (
            r["runtime"]["elapsed_sec"], r["runtime"]["python"], len(r["errors"]), len(r["degradations"]),
            (r.get("verification") or {}).get("ok")),
        "case": r["case_id"], "status": r["status"], "generated": r["runtime"]["generated_at"],
        "skill": "%s v%s" % (NM, VR), "pairs": len(r["citation_support_matrix"]), "issues": len(r["issues"]),
    }
    try:
        return (TPL.get(lang) or TPL.get("zh") or "# {case}\n\n{findings}\n").format(
            **{k: (v if v else "- none") for k, v in parts.items()})
    except Exception as e:
        return "# %s\n\n_template error: %s\n\n%s\n" % (r["case_id"], e, parts["findings"])


def wcsv(p, it):
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, extrasaction="ignore", fieldnames=CSVF)
        w.writeheader()
        [w.writerow(f) for f in it]


def pickdir(p, env, cands, make=False):
    for c in ([Path(p)] if p else []) + ([Path(os.environ[env])] if os.environ.get(env) else []) + cands:
        if c.is_dir():
            return c
        if make:
            try:
                c.mkdir(parents=True, exist_ok=True)
                return c
            except Exception:
                pass
    return Path.cwd() if make else Path("/input")


def lcase(inp, err):
    f = inp / "case.json"
    if not f.is_file():
        h = sorted(inp.glob("**/case*.json"))
        f = h[0] if h else None
    if not f:
        err.append({"stage": "case", "file": "case.json", "error": "not found; empty case"})
        return {}
    try:
        case = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        return case if isinstance(case, dict) else (err.append({"stage": "case", "file": str(f),
                                                                "error": "not a JSON object"}) or {})
    except Exception as e:
        err.append({"stage": "case", "file": str(f), "error": "%s: %s" % (type(e).__name__, str(e)[:160])})
        return {}


def mats(case, inp):
    """Inline material text from case.json, plus objects named in it but missing under input."""
    inl, gaps = [], []

    def walk(n):
        if isinstance(n, list):
            for v in n:
                walk(v)
        elif isinstance(n, dict):
            t = n.get("text") or n.get("content")
            if isinstance(t, str) and len(t) > 120:
                inl.append({"name": str(n.get("name") or n.get("id") or "inline"), "text": t})
            for v in (n.get(k) for k in ("path", "file", "filename", "file_path", "uri", "artifact")):
                if isinstance(v, str) and 0 < len(v) < 200 and not v.startswith("http") and not (inp / v).is_file():
                    gaps.append({"item": v, "reason": "listed in case.json but missing under input"})
            for v in n.values():
                walk(v)
    walk(case)
    return inl, gaps


def shell(st, case, inp, src, err, deg, notes):
    """Minimal honest result: contract keys echoed, every list empty, stage recorded."""
    c = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid = case.get("case_id") or case.get("id") or "unknown_case"
    unm = []
    data = {"case_id": cid, "status": st, "issues": [], "review_summary": {}, "sources": src,
            "citation_support_matrix": [], "evidence_index": {}, "pending_human": [], "uncertainty": [],
            "errors": err, "degradations": deg, "changes": [], "runtime": {}}
    return {"skill": {"name": NM, "version": VR}, "case_id": cid, "status": st,
            "output_contract": fill(c, data, unm) if c else {}, "issues": [], "review_summary": {},
            "citation_support_matrix": [], "evidence_index": {}, "pending_human": [], "uncertainty": [],
            "sources": src, "errors": err, "degradations": deg, "changes": [], "contract_unmapped_fields": unm,
            "runtime": {"stage": st, "input_dir": str(inp), "notes": notes,
                        "elapsed_sec": round(time.time() - T0, 2), "python": sys.version.split()[0]}}


def main(av=None):
    ap = argparse.ArgumentParser(
        prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Evidence-bound review + citation/fact verification (stdlib, no network, exit 0).",
        epilog="example: python3 scripts/main.py --input /input --output /app/output")
    ap.add_argument("--input", default=None, help="input dir (default /input, then $REVIEW_INPUT)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output)")
    ap.add_argument("--findings", default=None, help="agent findings JSON to merge; quotes verified verbatim")
    a = ap.parse_args(av)
    out = pickdir(a.output, "REVIEW_OUTPUT", [Path("/app/output"), H.parent / "output"], True)
    inp = pickdir(a.input, "REVIEW_INPUT", [Path("/input"), H.parent / "input"])
    err, deg, src, notes, case = [], [], [], [], {}
    try:
        wj(out / "result.json", shell("partial", case, inp, src, err, deg, notes))
    except Exception as e:
        sys.stderr.write("cannot write partial result.json: %s\n" % e)
    if not CAT:
        deg.append({"stage": "rules", "file": "references/checks.json",
                    "note": "rule catalog missing: only code-level checks ran"})
    try:
        case = lcase(inp, err)
        cid = case.get("case_id") or case.get("id") or case.get("caseId") or "unknown_case"
        docs = corpus(inp, err, deg, src)
        inl, gaps = mats(case, inp)
        for i in inl:
            docs.append(mkdoc(len(docs) + 1, "case.json:" + i["name"], i["text"], "case-inline", ".txt"))
        lang = "zh" if len(re.findall(r"[\u4e00-\u9fff]", "".join(d["text"] for d in docs))) > 200 else "en"
        x = X(docs, lang)
        x.un += [{"doc": g["item"], "item": "material", "reason": g["reason"]} for g in gaps]
        if not docs:
            x.un.append({"doc": "-", "item": "materials", "reason": "no readable material under input"})
        pats(x)
        crefs(x)
        cnums(x)
        pr = pairs(x)
        merged, rej = merge(x, a.findings, err, pr) if a.findings else (0, [])
        if a.findings and not Path(a.findings).is_file():
            err.append({"stage": "merge", "file": a.findings, "error": "findings file missing; deterministic pass only"})
        for p in pr:
            if not p["verdict"]:
                x.pend.append({"issue_id": None, "pair_id": p["pair_id"],
                               "why": "support verdict undetermined: %s" % p["claim_quote"][:100],
                               "need": "read the cited source; record full/partial/none/undetermined with evidence"})
        rules = {k: set() for k in KD}
        for f in x.it:
            rules.setdefault(f["kind"], set()).add(f["rule_id"])
        by = {s: sum(1 for f in x.it if f["severity"] == s) for s in SV}
        joined = " ".join(d["text"] for d in docs)
        pend_n = len([f for f in x.it if f["status"] == "pending_human"]) + len(
            [p for p in x.pend if not p.get("issue_id")])
        summary = {"documents": len(docs), "characters": len(joined), "issues_total": len(x.it), "by_severity": by,
                   "by_kind": {k: sum(1 for f in x.it if f["kind"] == k) for k in KD},
                   "pending_human": pend_n, "citation_pairs": len(pr), "language": lang,
                   "coverage": {k: {"rules": sorted(rules[k]),
                                    "findings": sum(1 for f in x.it if f["kind"] == k)} for k in KD},
                   "numeric_checks": {"fraction_pairs": len(re.findall(r"\d+\s*/\s*\d+", joined)),
                                      "p_values": len(re.findall(r"(?i)\bp\s*[=<>≤≥]", joined)),
                                      "n_mentions": len(re.findall(r"(?i)\bN\s*=\s*\d+", joined)),
                                      "percent_mentions": len(re.findall(r"\d+(?:\.\d+)?\s*%", joined))},
                   "sections_found": {d["name"]: sorted({s[0] for s in d["secs"]}) for d in docs},
                   "agent_findings_merged": merged, "agent_findings_rejected": len(rej)}
        unc = x.un + [{"doc": d["name"], "item": "coverage",
                       "reason": "short text (%d chars): full-text checks limited" % len(d["text"])}
                      for d in docs if len(d["text"]) < 1200]
        status = "input_error" if not docs else ("partial" if (x.un or deg or err or rej or pend_n) else "ok")
        res = {"skill": {"name": NM, "version": VR}, "case_id": cid, "status": status,
               "task_summary": {"input_dir": str(inp), "output_dir": str(out), "notes": notes},
               "issues": x.it, "review_summary": summary, "citation_support_matrix": pr,
               "evidence_index": {f["issue_id"]: {"doc": f["doc"], "locator": f["locator"], "quote": f["quote"],
                                                  "rule_id": f["rule_id"]} for f in x.it},
               "pending_human": x.pend, "uncertainty": unc, "sources": src, "errors": err, "degradations": deg,
               "changes": [{"what": "deterministic pass", "detail": "%d patterns + code checks" % len(SC)},
                           {"what": "semantic merge", "detail": "merged=%d rejected=%d" % (merged, len(rej))}],
               "rejected_findings": rej, "report_path": "review_report.md", "issues_csv_path": "issues.csv",
               "runtime": {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "elapsed_sec": round(time.time() - T0, 2), "python": sys.version.split()[0],
                           "script": Path(__file__).name, "input_dir": str(inp), "output_dir": str(out)}}
        data = dict(res)
        data["report_markdown"] = reps(res, lang)
        contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
        unm = []
        res["output_contract"] = fill(contract, data, unm) if contract else {}
        res["contract_unmapped_fields"] = unm
        res["verification"] = vcheck(res, docs, contract)
        Path(out / "review_report.md").write_text(data["report_markdown"], encoding="utf-8")
        wcsv(out / "issues.csv", x.it)
        wj(out / "evidence_index.json", res["evidence_index"])
        wj(out / "citation_pairs.json", pr)
        res["artifacts"] = {"review_report": "review_report.md", "issues_csv": "issues.csv",
                            "evidence_index": "evidence_index.json", "citation_pairs": "citation_pairs.json"}
        wj(out / "result.json.tmp", res)
        os.replace(out / "result.json.tmp", out / "result.json")
    except Exception as e:
        import traceback
        err.append({"stage": "pipeline", "error": "%s: %s" % (type(e).__name__, str(e)[:300]),
                    "trace": traceback.format_exc()[-900:]})
        try:
            part = shell("partial", case if isinstance(case, dict) else {}, inp, src, err, deg, notes)
            part["uncertainty"] = [{"item": "pipeline", "doc": "-", "reason": "incomplete run; see errors[]"}]
            wj(out / "result.json", part)
        except Exception as e2:
            sys.stderr.write("cannot write fallback result.json: %s\n" % e2)
    try:
        wj(out / "run.log", {"skill": NM, "version": VR, "elapsed": round(time.time() - T0, 2),
                             "argv": sys.argv[1:], "errors": err, "degradations": deg, "notes": notes})
    except Exception:
        pass
    print("%s v%s finished in %.2fs -> %s (exit 0)" % (NM, VR, time.time() - T0, out))
    return 0


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("unexpected: %s\n" % e)
    sys.exit(0)
