#!/usr/bin/env python3
"""paper->slides: plan, pptx, pdf, evidence map, result.json."""
import argparse, hashlib, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckbuild as DB
DC = ["case_id", "status", "editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions"]
NUM = re.compile(r"\d+(?:[.,]\d+)*\s*(?:%|‰)?")
FIG = re.compile(r"(figure|fig\.?|table|tab\.?|图|表)\s*\.?\s*(\d+[a-z]?)", re.I)
TOK = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")
STOP = set("a an the of in on for to and or with by as is are was were be this that these those we our it from than which they not but".split())
KNOWN = {"abstract", "introduction", "background", "related work", "methods", "method", "materials and methods", "results", "results and discussion", "discussion", "conclusion", "conclusions", "limitations", "future work", "acknowledgements", "references", "experiments"}
KW = {"motivation": ("challenge", "problem", "however", "remain", "difficult", "limited", "lack", "gap", "need", "unclear"),
      "approach": ("we propose", "we present", "we introduce", "we develop", "here we", "this work", "our approach", "we design", "we show"),
      "method": ("we use", "dataset", "we train", "we collect", "we measure", "pipeline", "model", "participants", "experiment"),
      "result": ("we find", "results", "outperform", "achiev", "increase", "improv", "compared", "significant", "higher", "lower"),
      "discussion": ("suggest", "indicat", "impl", "consistent", "in contrast", "interpret", "explain"),
      "limitation": ("limitation", "future work", "caveat", "remains", "not general", "small sample"),
      "conclusion": ("in conclusion", "we conclude", "in summary", "overall", "taken together", "these results")}
LBL = {"motivation": "Why this matters", "approach": "Our approach", "method": "How the work was done", "discussion": "What it means", "limitation": "Limits and open questions",
       "conclusion": "Takeaways", "thanks": "Thank you", "evidence": "Key evidence"}
SEC = {"motivation": ("introduction", "background", "abstract"), "approach": ("abstract", "introduction", "method"), "method": ("method", "experiment"),
       "discussion": ("discussion", "result"), "limitation": ("discussion", "limitation"), "conclusion": ("conclusion",)}
def nm(s):
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s or "")).strip()
def fl(s):
    return re.sub(r"[^0-9a-z%\u4e00-\u9fff]", "", (s or "").lower())
def tk(s):
    return {t for t in TOK.findall((s or "").lower()) if t not in STOP and len(t) > 1}
def ns(s):
    return {m.group(0).replace(" ", "") for m in NUM.finditer(s or "")}
def rf(s):
    return {("table " if k.lower().startswith(("tab", "表")) else "figure ") + n for k, n in FIG.findall(s or "")}
def hit(q, c, fc):
    q = nm(q).lower()
    return len(q) >= 8 and (q in c or (len(fl(q)) > 8 and fl(q) in fc))
def cut(s, m):
    s = nm(s)
    if len(s) <= m:
        return s
    g = s[:m]
    for sep in (". ", "; ", ", ", " and ", " — "):
        i = g.rfind(sep)
        if i > m * .45:
            return g[:i].rstrip(" ,;:") + "…"
    return g.rsplit(" ", 1)[0] + "…"
def parse(pages, cap=400):
    """Sentences with page/section locators + figure/table captions, from page text."""
    ss, sec, F, T = [], "", [], []
    for p, pt in enumerate(pages or [], 1):
        L = [l.strip() for l in (pt or "").split("\n") if l.strip()]
        for i, t in enumerate(L):
            a = re.match(r"^(Figure|Fig\.?|FIGURE)\s*(\d+[a-z]?)\s*[.:|]?\s*(.{12,240})$", t)
            b = re.match(r"^(Table|TABLE)\s*(\d+[a-z]?)\s*[.:|]?\s*(.{8,240})$", t)
            if a or b:
                cont = L[i + 1] if i + 1 < len(L) and len(L[i + 1]) < 160 and not re.match(r"^(Figure|Table|Fig\.)", L[i + 1]) else ""
                (F if a else T).append({"id": ("Figure " if a else "Table ") + (a or b).group(2), "cap": nm((a or b).group(3) + " " + cont), "p": p})
                continue
            m = re.match(r"^(?:(\d+(?:\.\d+)*)[.)]?\s+)?([A-Z][A-Za-z][A-Za-z \-/]{2,48})$", t)
            if m and len(t) < 60 and not t.endswith(".") and (m.group(1) or t.lower() in KNOWN):
                sec = t
                continue
            for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", t):
                x = nm(x)
                if 25 <= len(x) <= 400 and (not x[:1].isascii() or not x[:1].islower()):
                    ss.append({"t": x, "p": p, "sec": sec})
                if len(ss) >= cap:
                    return ss, F, T
    return ss, F, T
def plan(n):
    r = ["title"] + (["motivation"] if n >= 3 else []) + (["approach"] if n >= 4 else []) + (["method"] if n >= 6 else []) + (["discussion", "limitation"] if n >= 10 else [])
    tail = ["conclusion"] + (["thanks"] if n >= 14 else [])
    ev = n - len(r) - len(tail)
    for d in ("limitation", "discussion", "method", "approach", "motivation"):
        if ev >= 1:
            break
        if d in r:
            r.remove(d)
            ev = n - len(r) - len(tail)
    if ev < 1:
        r, tail = (["title"] if n == 1 else ["title", "motivation"]), (["conclusion"] if n > 1 else [])
        ev = max(0, n - len(r) - len(tail))
    out = r + ["evidence"] * ev + tail
    while len(out) < n:
        out.insert(len(out) - len(tail), "evidence")
    return out[:n]
def pick(ss, role, used, k=3, secs=None):
    kws = KW.get(role, ())
    pool = [s for s in ss if id(s) not in used and len(s["t"]) < 320] or [s for s in ss if len(s["t"]) < 320]
    if secs:
        pr = [s for s in pool if any(w in s["sec"].lower() for w in secs)]
        pool = pr + [s for s in pool if s not in pr]
    out = []
    for i in sorted(range(len(pool)), key=lambda i: (-sum(1 for w in kws if w in pool[i]["t"].lower()), i)):
        if len(out) >= k:
            break
        s = pool[i]
        if any(fl(s["t"])[:50] == fl(o["t"])[:50] for o in out):
            continue
        out.append(s)
        used.add(id(s))
    return out
def ev(s):
    return {"type": "section" if s["sec"] else "page", "id": s["sec"] or "p.%d" % s["p"], "locator": "p.%d%s" % (s["p"], (" / " + s["sec"]) if s["sec"] else ""), "quote": s["t"]}
def model(doc, wc):
    ss, used, F, T = doc["sents"], set(), doc["figs"], doc["tabs"]
    roles, sl = plan(wc["total"]), []
    title, sub = doc["meta"].get("title") or doc["meta"].get("stem", ""), doc["meta"].get("byline", [])[:2]
    for i, role in enumerate(roles):
        s = {"n": i + 1, "role": role, "bullets": [], "evidence": [], "notes": ""}
        if role == "title":
            s["title"], s["claim"], s["bullets"] = title, title[:110] or LBL["evidence"], sub or [doc["meta"].get("stem", "")]
            s["evidence"] = [ev(ss[0])] if ss else [{"type": "page", "id": "p.1", "locator": "p.1", "quote": title}]
        elif role == "evidence":
            k, pool = sum(1 for x in sl if x["role"] == "evidence"), F + T
            if k < len(pool):
                f, cap = pool[k], cut(pool[k]["cap"], 95)
                res = pick([x for x in ss if abs(x["p"] - f["p"]) <= 1] or ss, "result", used, 2) or pick(ss, "result", used, 2)
                s["title"], s["claim"] = "%s: %s" % (f["id"], cut(f["cap"], 60)), cap
                s["bullets"] = [cap] + [cut(x["t"], 105) for x in res[:2]]
                s["evidence"] = [{"type": "figure" if "Figure" in f["id"] else "table", "id": f["id"], "locator": "%s, p.%d" % (f["id"], f["p"]), "quote": f["cap"]}] + [ev(x) for x in res]
            else:
                sel = pick(ss, "result", used, 3) or pick(ss, "result", set(), 3)[(k - len(pool)) % 3:]
                s["title"] = "%s %d" % (LBL["evidence"], k - len(pool) + 1)
                s["claim"] = cut(sel[0]["t"], 100) if sel else LBL["evidence"]
                s["bullets"], s["evidence"] = [cut(x["t"], 110) for x in sel], [ev(x) for x in sel]
        elif role == "thanks":
            ack = [x for x in ss if "acknowledg" in x["sec"].lower()]
            s["title"] = s["claim"] = LBL["thanks"]
            s["bullets"], s["evidence"] = ([cut(x["t"], 100) for x in ack[:2]] or sub), [ev(x) for x in ack[:1]]
        else:
            sel = pick(ss, role, used, 3, SEC.get(role)) or pick(ss, role, used, 3)
            s["title"], s["claim"] = LBL.get(role, role), (cut(sel[0]["t"], 105) if sel else LBL.get(role, role))
            s["bullets"], s["evidence"] = [cut(x["t"], 110) for x in sel], [ev(x) for x in sel]
        ls = [e["locator"] for e in s["evidence"][:2]]
        nt = ("If asked, cite %s." % "; ".join(ls)) if ls else ""
        if i + 1 < len(roles):
            nt += " Next: %s." % LBL.get(roles[i + 1], roles[i + 1])
        s["notes"] = nt.strip()[:400] or "Emphasis: one claim per page; detail is in the paper."
        sl.append(s)
    return sl
def checks(sl, c, fc, wc, info):
    f, qm, nu, fj, ovs, ps = [], 0, 0, 0, [], rf(c)
    for s in sl:
        body = " ".join(map(str, s["bullets"])) + " " + s.get("claim", "")
        for e in s["evidence"]:
            if not hit(e.get("quote", ""), c, fc):
                qm += 1
                f.append("s%d quote-not-in-paper %s" % (s["n"], e.get("locator")))
        for v in ns(body):
            if v not in c and v.rstrip("%‰") not in c:
                nu += 1
                f.append("s%d number-not-in-paper %s" % (s["n"], v))
        for r in rf(s.get("title", "") + body):
            if ps and r not in ps:
                fj += 1
                f.append("s%d ref-not-in-paper %s" % (s["n"], r))
        o = round(len(tk(s["notes"]) & tk(body + s.get("title", ""))) / max(1, len(tk(s["notes"]))), 3) if s.get("notes") else 0.0
        if o > .6:
            f.append("s%d notes-restate-text %.2f" % (s["n"], o))
        ovs.append(o)
    dense = [s["n"] for s in sl if len(s["bullets"]) > 5 or max([len(str(b)) for b in s["bullets"]] or [0]) > 190]
    return {"slide_count": {"expected": wc["total"], "actual": len(sl), "ok": len(sl) == wc["total"]},
            "template_inheritance": {"declared": wc["template_inheritance"], "engine": info.get("engine"), "theme_unchanged": info.get("theme_unchanged"),
                                     "master_unchanged": info.get("master_unchanged"), "layouts_used": info.get("layouts_used"), "ok": info.get("theme_unchanged") is not False},
            "overflow": {"dense_slides": dense, "ok": not dense},
            "notes_coverage": {"n": sum(1 for s in sl if s.get("notes")), "total": len(sl), "ok": all(s.get("notes") for s in sl)},
            "notes_overlap": {"max": max(ovs or [0]), "threshold": .6, "ok": max(ovs or [0]) <= .6},
            "figure_refs": {"paper_count": len(ps), "mismatch": fj, "ok": fj == 0},
            "number_whitelist": {"misses": nu, "ok": nu == 0},
            "fonts": {"theme": "template" if info.get("template") else "builtin", "embedded": False},
            "evidence_coverage": {"n": sum(1 for s in sl if s["evidence"]), "total": len(sl), "quotes_missing": qm},
            "pass": not f, "failures": f[:30]}
def wj(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
def disc(inp):
    inp = Path(inp)
    fs = sorted([p for p in inp.rglob("*") if p.is_file()]) if inp.exists() else []
    for p in [inp / "case.json"] + [q for q in fs if re.match(r"case.*\.json$", q.name, re.I)]:
        if p.is_file():
            try:
                d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(d, dict):
                    return d, p, fs
            except Exception:
                pass
    return {}, None, fs
def worder(case, fs):
    wo = {}
    for k, v in case.items():
        if isinstance(v, dict) and ("slide" in str(k).lower() or any(("slide" in str(x).lower() or "count" in str(x).lower()) for x in v)):
            wo.update({str(a).lower().replace(" ", "_"): b for a, b in v.items()})
    for p in fs:
        if re.search(r"workorder.*\.json$|slide[-_]?spec.*\.json$", p.name, re.I):
            try:
                d = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(d, dict):
                    wo.update({str(a).lower().replace(" ", "_"): b for a, b in d.items()})
            except Exception:
                pass
    g = lambda *ks: next((wo[k] for k in ks if wo.get(k) not in (None, "")), None)
    n = re.sub(r"[^0-9]", "", str(g("total_slide_count", "slide_count", "total_slides", "n_slides", "max_slides") or ""))
    return {"mode": str(g("mode", "requested_mode") or "generate"), "total": int(n) if n else 12, "source_preservation": g("source_preservation"),
            "template_inheritance": g("template_inheritance"), "audience": g("audience"), "duration": g("duration_minutes", "duration"), "raw": wo}
def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper -> academic slides: plan, editable pptx, PDF, evidence map, result.json. Exit code is always 0.")
    ap.add_argument("--input", default="/input", help="case input dir")
    ap.add_argument("--output", default="/app/output", help="deliverable dir")
    ap.add_argument("--work", default="/app/work", help="intermediate dir")
    a = ap.parse_args(argv)
    t0, out, work = time.time(), Path(a.output), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, cp, fs = disc(a.input)
    ct = case.get("output_contract")
    ct = [str(k) for k in ct] if isinstance(ct, list) and ct else list(DC)
    ct = ct if "case_id" in ct else ["case_id"] + ct
    cid = case.get("case_id") or case.get("id")
    r = {k: None for k in ct}
    r.update({"case_id": cid, "status": "partial"})
    r.update({"exceptions": [], "errors": [], "degradations": [], "pending_human": [], "uncertainty": [], "changes": {}, "sources": {},
              "runtime": {"started": time.strftime("%Y-%m-%dT%H:%M:%S")}})
    wj(out / "result.json", r)
    exc, deg, ph = [], [], []
    E = lambda k, d: exc.append({"kind": k, "detail": d})
    try:
        wc = worder(case, fs)
        papers = [p for p in fs if p.suffix.lower() in (".pdf", ".docx", ".md", ".txt") and p.stat().st_size > 1500 and not re.search(r"^task\.md$|readme", p.name, re.I)]
        decks = [p for p in fs if p.suffix.lower() == ".pptx"]
        paper = papers[0] if papers else None
        tpl = next((p for p in decks if re.search(r"template|master|layout|style|brand", p.name, re.I)), None) or (decks[0] if decks else None)
        if not cp:
            E("input", "no case.json; contract defaulted")
        if tpl is None:
            deg.append({"what": "template", "detail": "no template; builtin master/layout/theme"})
        if not paper:
            r.update({"status": "input_error", "exceptions": exc + [{"kind": "input", "detail": "no paper file under %s" % a.input}],
                      "runtime": dict(r["runtime"], seconds=round(time.time() - t0, 1))})
            wj(out / "result.json", r)
            return 0
        doc = DB.extract(paper)
        doc["sents"], doc["figs"], doc["tabs"] = parse(doc["pages"])
        if len(doc["text"]) < 200:
            E("extraction", "text layer empty (engine=%s); nothing invented" % doc["engine"])
            r.update({"status": "partial", "exceptions": exc, "sources": {"file": str(paper), "engine": doc["engine"], "chars": len(doc["text"])},
                      "runtime": dict(r["runtime"], seconds=round(time.time() - t0, 1))})
            wj(out / "result.json", r)
            return 0
        if doc["engine"] == "stdlib-inflate":
            deg.append({"what": "text extraction", "detail": "python-only PDF parsing; captions may be incomplete"})
        if not doc["figs"] and not doc["tabs"]:
            ph.append({"action": "confirm figure list", "detail": "no captions matched; locators only"})
        sl = model(doc, wc)
        wj(out / "deck_model.json", {"case_id": cid, "workorder": wc, "paper": str(paper), "template": str(tpl), "slides": sl})
        wj(out / "plan.json", {"case_id": cid, "mode": wc["mode"], "total_slide_count": wc["total"],
                               "source_preservation": wc["source_preservation"], "template_inheritance": wc["template_inheritance"],
                               "slides": [{"n": s["n"], "role": s["role"], "title": s["title"], "claim": s["claim"], "locators": [e["locator"] for e in s["evidence"]]} for s in sl]})
        r["sources"] = {"file": str(paper), "engine": doc["engine"], "chars": len(doc["text"]), "pages": len(doc["pages"]),
                        "figures": len(doc["figs"]), "tables": len(doc["tabs"]), "template": str(tpl) if tpl else None}
        pptx = out / "presentation.pptx"
        info = DB.build(sl, pptx, template=str(tpl) if tpl else None)
        ep = DB.export_pdf(pptx, out, work=work)
        if ep["degraded"]:
            deg.append({"what": "pdf", "detail": "no office renderer; no PDF preview"})
        v = {"pptx": DB.validate_pptx(pptx, wc["total"]), "pdf": DB.pdf_info(out / "presentation.pdf"), "png": {"count": 0}}
        v["pass"] = bool(v["pptx"]["ok"] and v["pdf"]["ok"])
        wj(work / "verification.json", v)
        c, fc = doc["text"].lower(), fl(doc["text"])
        ck = checks(sl, c, fc, wc, info)
        ck["files"] = {"pptx_ok": v["pptx"]["ok"], "pdf_ok": v["pdf"]["ok"], "png": v["png"]["count"], "pptx_slides": v["pptx"]["slides"],
                       "pdf_pages": v["pdf"]["pages"], "pptx_notes": v["pptx"]["notes"]}
        if not v["pptx"]["ok"]:
            E("pptx", "; ".join(v["pptx"]["issues"])[:300])
        if not v["pdf"]["ok"]:
            E("render", "PDF preview invalid/absent")
        hm = lambda e: hit(e["quote"], c, fc)
        cs = lambda s: {"n": s["n"], "title": s["title"], "role": s["role"], "claim": s["claim"], "bullets": s["bullets"],
                        "evidence": [dict(e, matched=hm(e)) for e in s["evidence"]], "notes": s.get("notes"),
                        "assets": [{"path": None, "note": "caption+locator only"}]}
        r.update({"status": "ok" if (ck["pass"] and v["pass"] and not exc) else "partial",
                  "editable_source": {"path": str(pptx), "format": "pptx", "slides": v["pptx"]["slides"], "bytes": pptx.stat().st_size,
                                      "sha256": hashlib.sha256(pptx.read_bytes()).hexdigest(), "engine": info.get("engine"),
                                      "notes_slides": v["pptx"]["notes"],
                                      "template": {"path": info.get("template"), "master": info.get("master"),
                                                   "layouts_used": info.get("layouts_used"), "inherited": info.get("theme_unchanged") is not False}},
                  "export_artifact": {"pdf": {"path": ep.get("pdf"), "pages": v["pdf"]["pages"], "engine": ep.get("engine"), "valid": v["pdf"]["ok"]},
                                      "png": {"dir": None, "count": 0}},
                  "content_map": {"unit": "slide", "slides": [cs(s) for s in sl],
                                  "coverage": {"slides": len(sl), "with_evidence": sum(1 for s in sl if s["evidence"]),
                                               "evidence_items": sum(len(s["evidence"]) for s in sl),
                                               "quotes_matched": sum(1 for s in sl for e in s["evidence"] if hm(e))}},
                  "compliance_checks": ck, "exceptions": exc, "degradations": deg, "pending_human": ph,
                  "changes": {"artifact": "presentation.pptx", "engine": info.get("engine"), "slides": len(sl), "action": "modify" if tpl else "add"},
                  "runtime": dict(r["runtime"], seconds=round(time.time() - t0, 1), model_requests=0)})
        wj(out / "result.json", r)
        print(json.dumps({"status": r["status"], "slides": len(sl), "pptx": str(pptx), "pdf": ep.get("pdf"), "checks_pass": ck["pass"], "seconds": r["runtime"]["seconds"]}))
    except Exception as e:
        r["errors"] = (r.get("errors") or []) + [{"kind": "runtime", "detail": "%s: %s" % (type(e).__name__, str(e)[:300])}]
        r["runtime"] = dict(r.get("runtime") or {}, seconds=round(time.time() - t0, 1))
        wj(out / "result.json", r)
        print(json.dumps({"status": r.get("status", "partial"), "error": str(e)[:200]}))
    return 0
if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
