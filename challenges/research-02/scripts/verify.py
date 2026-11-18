#!/usr/bin/env python3
"""verify.py -- assemble + verify: agent artifacts + work/corpus.json -> verbatim quote gate -> counts/coverage/gaps/conflicts -> result.json, evidence_map.csv, screening_log.csv. Stdlib only, offline."""
import argparse, csv, json, re, sys, unicodedata
from collections import Counter
from pathlib import Path

H = Path(__file__).resolve().parent
V = "1.0.0"
try:
    T = json.loads((H.parent / "references" / "templates.json").read_text("utf-8"))
except Exception:
    T = {}
ALIAS, LAB, OPP = T.get("aliases") or {}, T.get("labels") or {}, [tuple(x) for x in (T.get("oppose") or [])]
CITE = re.compile(r"\[([^\[\]]{1,160})\](?!\()")
EVID = re.compile(r"\{([^{}]{1,160})\}")
TR = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                    "\u2212": "-", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl", "\u00a0": " ", "\u2026": "..."})
LISTY = ("array", "list", "source", "item", "row", "claim", "theme", "gap", "conflict", "uncertaint", "error",
         "pending", "degradation", "evidence", "reference")
DESCK = {"type", "description", "required", "default", "example", "items"}
ECOLS = ["evidence_id", "claim", "source_id", "locator", "quote", "strength", "claim_type", "topic", "verification"]
SCOLS = ["source_id", "title", "year", "doi", "kind", "fulltext", "relevance", "decision", "reason_code", "criterion",
         "note", "verification"]

def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or "")).translate(TR)).strip().lower()

def squash(s):
    return re.sub(r"[\s\-]+", "", norm(s))

def ra(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return d

def wa(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")

def rcsv(p):
    try:
        with open(p, newline="", encoding="utf-8-sig") as fh:
            return [dict(r) for r in csv.DictReader(fh)]
    except Exception:
        return []

def wcsv(p, rows, cols):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in cols} for r in rows)

def verify_quote(doc, quote, locator=None):
    """(status, matched_locator). Quote must exist verbatim in the cited block; lenient = whitespace-free match."""
    q = norm(quote)
    if not doc or len(q) < 12:
        return ("rejected_no_source" if not doc else "rejected_too_short"), None
    full = doc.get("text", "")
    body = next((b.get("text") or "" for b in (doc.get("blocks") or []) if locator and str(b.get("locator")) == str(locator)), None)
    if body is not None:
        if q in norm(body):
            return "verified", locator
        if squash(q) and squash(q) in squash(body):
            return "verified_lenient", locator
        if q in norm(full) or (squash(q) and squash(q) in squash(full)):
            return "rejected_locator_mismatch", locator
        return "rejected_quote_not_found", locator
    if q in norm(full):
        return "verified", None
    return ("verified_lenient", None) if squash(q) and squash(q) in squash(full) else ("rejected_quote_not_found", None)

def audit_review(md, ids, eids):
    cited, bad, ev, bad_ev = set(), set(), set(), set()
    for rx, ok, bads, pat, pool in ((CITE, cited, bad, r"S\d{1,3}", ids), (EVID, ev, bad_ev, r"E\d{1,4}", eids)):
        for m in rx.finditer(md):
            for t in (x.strip() for x in re.split(r"[,;、/\s]+", m.group(1))):
                if re.fullmatch(pat, t):
                    (ok if t in pool else bads).add(t)
    body = re.sub(r"^\s*[|#].*$", " ", re.sub(r"^```.*?^```", " ", md, flags=re.S | re.M), flags=re.M)
    cut = [i for i in (body.find("## 参考文献"), body.find("## References")) if i > 0]
    body = body[:min(cut)] if cut else body
    subst, unc = 0, []
    for x in (y.strip() for y in re.split(r"(?<=[.!?。！？])\s+", body) if y.strip()):
        if len(re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]", x)) >= 12:
            subst += 1
            not (CITE.search(x) or EVID.search(x)) and unc.append(x[:150])
    return {"substantive_sentences": subst, "uncited_sentences": len(unc), "uncited_examples": unc[:6],
            "citation_coverage": round(1 - len(unc) / subst, 3) if subst else None,
            "dangling_source_ids": sorted(bad), "dangling_evidence_ids": sorted(bad_ev)}

def backfill(res, con, node=None, pre=""):
    """Every output_contract key exists at every level; unknown input keys preserved; null/[] defaults."""
    node = res if node is None else node
    acc = []
    for k, v in (con or {}).items():
        if k in DESCK:
            continue
        path = f"{pre}.{k}" if pre else k
        sub = [x for x in v if x not in DESCK] if isinstance(v, dict) else []
        if sub:
            isinstance(node.get(k), dict) or node.__setitem__(k, {})
            acc += backfill(node[k], v, node[k], path)
        elif k not in node:
            node[k] = [] if any(x in (str(v) + k).lower() for x in LISTY) else None
            acc.append(path)
    if pre:
        return acc
    ks = [k for k in (con or {}) if k not in DESCK]
    return {"keys": len(ks), "filled_defaults": acc[:40], "filled_defaults_count": len(acc),
            "missing": [k for k in ks if k not in res]}

def sources(docs):
    return [{"source_id": d.get("source_id"), "path": d.get("path"), "kind": d.get("kind"), "title": d.get("title"),
             "year": d.get("year"), "doi": d.get("doi"), "authors": d.get("authors"),
             "chars": d.get("chars"), "fulltext": bool(d.get("fulltext")), "sha1_text": d.get("sha1"),
             "duplicate_of": d.get("duplicate_of"),
             "locators": [b.get("locator") for b in d.get("blocks", [])][:30]} for d in docs]

def conflicts(themes, docs):
    by = {d.get("source_id"): d for d in docs}
    out = []
    for th in themes:
        src = [s for s in th.get("sources", []) if s in by]
        txt = {s: norm(by[s].get("abstract") or by[s].get("text", "")[:1200]) for s in src}
        for pa, pb in OPP:
            a = [s for s in src if pa in txt[s] and pb not in txt[s]]
            b = [s for s in src if pb in txt[s] and pa not in txt[s]]
            if a and b:
                out.append({"topic": th.get("label"), "side_a": a[:1], "side_b": b[:1], "marker_pair": [pa, pb],
                            "resolution": "unresolved", "status": "candidate_unadjudicated",
                            "basis_of_conflict": "opposite markers in one theme"})
    return out[:8]

def gaps(docs, themes, conf, ev):
    g = [{"type": "no_fulltext", "linked_sources": [d.get("source_id")], "strength": "insufficient",
          "statement": f"{d.get('source_id')}: abstract/short text only ({d.get('chars', 0)} chars); methods unverifiable"}
         for d in docs if not d.get("duplicate_of") and not d.get("fulltext")]
    g += [{"type": "single_source", "linked_sources": t.get("sources"), "strength": "insufficient",
           "statement": f"theme '{t.get('label')}' rests on a single source"} for t in themes if t.get("n_sources", 0) == 1]
    g += [{"type": "unresolved_conflict", "linked_sources": x["side_a"] + x["side_b"], "strength": "insufficient",
           "statement": f"{x['side_a'][0]} vs {x['side_b'][0]}: direction disagrees, condition unresolved"}
          for x in conf if x.get("resolution") == "unresolved"]
    if ev and not any(re.search(r"\d", r.get("quote", "")) for r in ev):
        g.append({"type": "missing_outcome", "linked_sources": sorted({r.get("source_id") for r in ev})[:6],
                  "strength": "insufficient", "statement": "no quantitative excerpt; effect-size comparison impossible"})
    for i, x in enumerate(g, 1):
        x["gap_id"] = f"G{i:02d}"
    return g

def assemble(out_dir, work_dir):
    out, work = Path(out_dir), Path(work_dir)
    res = ra(out / "result.json", {}) or {}
    docs = (ra(work / "corpus.json", {}) or {}).get("documents") or []
    by = {d.get("source_id"): d for d in docs}
    case = ra(work / "case.json", {}) or {}
    ct = case.get("output_contract") or res.get("output_contract_echo") or {}
    rq = res.get("research_question") or {}
    themes = ra(work / "themes.json", None) or res.get("themes") or []
    pr = dict(ra(work / "protocol.json", None) or (res.get("screening") or {}).get("protocol") or {})
    pr["order_ok"] = bool(pr.get("written_before_screening")) and pr.get("criteria_source") == "agent_authored"
    pend, degs = list(res.get("pending_human") or []), list(res.get("degradations") or [])
    pr["order_ok"] or pend.append({"item": "protocol not agent-authored first", "why": "protocol.order_ok=false",
                                  "action": "write work/protocol.json (written_before_screening=true) before screening.csv"})
    scr = rcsv(work / "screening.csv") or rcsv(out / "screening_log.csv")
    for r in scr:
        dec = r["decision"] = str(r.get("decision") or "").strip().lower() or "pending"
        cod = str(r.get("reason_code") or "").strip().upper()
        r["reason_code"] = cod or None
        r["verification"] = "ok" if (dec[:3] == "inc" and cod[:1] == "I") or (dec[:3] == "exc" and cod[:1] == "E") \
            else ("undecided" if dec == "pending" else "needs_review")
    inc = [r for r in scr if r["decision"][:3] == "inc"]
    exc = [r for r in scr if r["decision"][:3] == "exc"]
    und = [r for r in scr if r not in inc and r not in exc]
    und and pend.append({"item": f"{len(und)} sources undecided", "why": "decision empty", "action": "fill decision+reason_code"})
    ev = rcsv(out / "evidence_map.csv") or rcsv(work / "evidence_map.csv")
    if not ev:
        per = Counter()
        for c in rcsv(work / "candidates.csv"):
            if per[c["source_id"]] < 2:
                per[c["source_id"]] += 1
                ev.append({"evidence_id": f"E{len(ev)+1:03d}", "claim": c["quote"][:180], "source_id": c["source_id"],
                           "locator": c["locator"], "quote": c["quote"], "strength": "unassessed", "claim_type": "excerpt_only"})
        degs.append("no agent evidence_map.csv: candidate excerpts used (strength=unassessed)")
    st = Counter()
    for i, r in enumerate(ev, 1):
        r.update(evidence_id=str(r.get("evidence_id") or f"E{i:03d}").strip(),
                 strength=str(r.get("strength") or "unassessed").strip().lower(),
                 claim_type=str(r.get("claim_type") or "claim").strip())
        s_, m_ = verify_quote(by.get(str(r.get("source_id") or "").strip()), r.get("quote") or "",
                              str(r.get("locator") or "").strip() or None)
        r["verification"], r["matched_locator"] = s_, m_
        st[s_] += 1
        s_.startswith("rejected") and pend.append({"item": f"{r['evidence_id']} quote rejected", "why": s_,
                                                   "action": "cite a verbatim span or drop the row"})
        r.get("topic") or r.update(topic=next((t.get("theme_id") for t in themes if r.get("source_id") in t.get("sources", [])), None))
    cf = ra(work / "conflicts.json", None) or conflicts(themes, docs)
    gp = gaps(docs, themes, cf, ev)
    rp = out / "review.md"
    md = rp.read_text(encoding="utf-8", errors="replace") if rp.exists() else ""
    mode = "agent_authored"
    if len(md.strip()) < 200:
        L = LAB["zh" if len(re.findall(r"[\u4e00-\u9fff]", (rq.get("primary") or "") + str(case.get("task_instruction") or ""))) > 30 else "en"]
        md = "\n".join([L.get("t", "# Literature review"), "", L.get("note", ""), "", L.get("rq", "## 1 Research question"), "",
                         rq.get("primary") or "-", "", L.get("cov", "## 2 Coverage"), "",
                         f"{len(docs)} sources / {len(inc)} included / {len([d for d in docs if d.get('fulltext')])} full-text", "",
                         L.get("syn", "## 3 Synthesis"), ""]
                        + [f"- **{t.get('label')}**: " + ", ".join(t.get("sources", [])) for t in themes]
                        + ["", L.get("gap", "## 4 Gaps"), ""] + [f"- {g['statement']} [{g['type']}]" for g in gp]
                        + ["", L.get("ref", "## 5 References"), ""]
                        + [f"[{d.get('source_id')}] {d.get('title') or d.get('rel') or ''}" for d in docs if not d.get("duplicate_of")])
        mode = "deterministic_baseline"
        rp.write_text(md, encoding="utf-8")
        degs.append("no agent review.md: structural baseline written")
    aud = audit_review(md, set(by), {r["evidence_id"] for r in ev})
    nrej = sum(v for k, v in st.items() if k.startswith("rejected"))
    aud["dangling_source_ids"] and pend.append({"item": "review cites unknown ids", "why": str(aud["dangling_source_ids"]),
                                                "action": "fix or remove"})
    cov, cnt = aud.get("citation_coverage"), Counter(r["decision"] for r in scr)
    ids = {r["source_id"] for r in inc}
    cited = {t for m in CITE.finditer(md) for t in re.split(r"[,;、\s]+", m.group(1)) if re.fullmatch(r"S\d{1,3}", t.strip())}
    unc = [{"type": "no_included_sources", "impact": "no synthesis possible", "detail": "none"}] if not inc else []
    unc += [{"type": "abstract_only", "impact": f"{d.get('source_id')} abstract-level only", "detail": f"{d.get('chars', 0)} chars"}
            for d in docs if not d.get("fulltext") and not d.get("duplicate_of")]
    unc += [{"type": "single_source_theme", "impact": f"theme '{t.get('label')}' not robust", "detail": t.get("sources")}
            for t in themes if t.get("n_sources", 0) == 1]
    nrej and unc.append({"type": "quote_gate_rejected", "impact": f"{nrej} rows unverifiable",
                         "detail": [r["evidence_id"] for r in ev if str(r.get("verification", "")).startswith("rejected")][:12]})
    mode != "agent_authored" and unc.append({"type": "baseline_draft", "impact": "structural draft", "detail": mode})
    cov is not None and cov < 0.8 and unc.append({"type": "low_citation_coverage", "impact": "untraceable sentences",
                                                  "detail": aud["uncited_examples"][:4]})
    n = len(docs)
    res.update({
        "status": "ok" if bool(inc) and not nrej and mode == "agent_authored" and not und and cov is not None and cov >= 0.8
        else ("insufficient_evidence" if not inc else "partial"),
        "case_id": case.get("case_id") or res.get("case_id") or (ct.get("case_id") if isinstance(ct, dict) else None),
        "mode": "assembled", "skill": {"name": "literature-review-evidence-mapper", "version": V},
        "research_question": rq,
        "pipeline_steps": {"discover": True, "extract": bool(n), "protocol": pr["order_ok"], "screen": bool(inc or exc),
                           "theme": bool(themes), "evidence": bool(ev), "draft": True},
        "counts": {"files": (res.get("counts") or {}).get("files", 0), "documents": n, "included": cnt["include"],
                   "excluded": cnt["exclude"], "undecided": len(und), "duplicates": sum(1 for d in docs if d.get("duplicate_of")),
                   "fulltext": sum(1 for d in docs if d.get("fulltext")), "themes": len(themes), "evidence_rows": len(ev),
                   "evidence_verified": st["verified"], "evidence_verified_lenient": st["verified_lenient"],
                   "evidence_rejected": nrej, "gaps": len(gp), "conflicts": len(cf)},
        "coverage": {"included": len(inc), "cited_included": len(cited & ids),
                     "included_cited_ratio": round(len(cited & ids) / len(ids), 3) if ids else None,
                     "uncited_included": sorted(ids - cited)[:20]},
        "screening": {"protocol": pr, "counts": dict(cnt)},
        "themes": themes, "evidence_rows": [{k: r.get(k) for k in ECOLS} for r in ev],
        "evidence_summary": {"rows": len(ev), "verified": st["verified"], "verified_lenient": st["verified_lenient"],
                             "rejected": nrej},
        "conflicts": cf, "gaps": gp, "uncertainty": unc,
        "review": {"path": "review.md", "chars": len(md), "draft_mode": mode, "substantive_sentences": aud["substantive_sentences"],
                   "uncited_sentences": aud["uncited_sentences"], "citation_coverage": cov},
        "sources": sources(docs), "pending_human": pend, "degradations": degs,
        "runtime": dict(res.get("runtime") or {}, skill_version=V, python=sys.version.split()[0])})
    wcsv(out / "evidence_map.csv", ev, ECOLS)
    wcsv(out / "screening_log.csv", scr, SCOLS)
    res["contract_backfill"] = backfill(res, ct)
    pay = {"md": md, "ev": res["evidence_rows"], "scr": res["screening"], "scrrows": scr, "themes": themes, "gaps": gp,
           "conf": cf, "unc": unc, "srcs": res["sources"], "sum": md[:1200], "cov": res["coverage"],
           "counts": res["counts"], "log": case.get("search_log")}
    for k in (ct if isinstance(ct, dict) else []):
        cn = ALIAS.get(str(k).lower())
        if cn and cn in pay and res.get(k) in (None, [], {}, ""):
            res[k] = pay[cn] if not isinstance(res.get(k), list) or isinstance(pay[cn], list) else [pay[cn]]
    wa(out / "result.json", res)
    return res

def run(out_dir, work_dir, write_report=True):
    out, work = Path(out_dir), Path(work_dir)
    docs = {d.get("source_id"): d for d in ((ra(work / "corpus.json", {}) or {}).get("documents") or [])}
    res = ra(out / "result.json", {}) or {}
    ct = (ra(work / "case.json", {}) or {}).get("output_contract") or res.get("output_contract_echo") or {}
    rows = rcsv(out / "evidence_map.csv")
    st = Counter(verify_quote(docs.get((r.get("source_id") or "").strip()), r.get("quote") or "",
                              (r.get("locator") or "").strip() or None)[0] for r in rows)
    md = (out / "review.md").read_text(encoding="utf-8", errors="replace") if (out / "review.md").exists() else ""
    aud = audit_review(md, set(docs), {r.get("evidence_id", "") for r in rows}) if md else {}
    miss = [k for k in (ct if isinstance(ct, dict) else {}) if k not in res]
    c = res.get("counts") or {}
    bad = [f"counts.{k} missing" for k in ("documents", "included", "excluded") if k not in c]
    bad += ["included+excluded > documents"] if not bad and c["included"] + c["excluded"] > c["documents"] else []
    bad += [f"rejected {r.get('evidence_id')}" for r in rows if str(r.get("verification", "")).startswith("rejected")]
    verdict = "PASS" if (not miss and md and not bad) else "WARN"
    rep = "\n".join(["# Verification report", "", f"- evidence rows {len(rows)} status {dict(st) or '{}'}",
                      f"- contract missing {miss or 'none'}",
                      f"- review chars {len(md)} substantive {aud.get('substantive_sentences')} coverage {aud.get('citation_coverage')}",
                      "", f"## verdict: {verdict}"] + [f"- FAIL {x}" for x in bad]) + "\n"
    try:
        write_report and (out / "verification_report.md").write_text(rep, encoding="utf-8")
    except Exception:
        pass
    return {"verdict": verdict, "quote_statuses": dict(st), "contract_missing": miss, "audit": aud, "report": rep}

def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="assemble: quote gate -> result.json; verify: contract, quotes, coverage, counts.",
                                 epilog="verify.py [--output D] [--work D] [--assemble]")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--assemble", action="store_true", help="run assemble first")
    a = ap.parse_args(argv)
    if not Path(a.output).exists() or not Path(a.work).exists():
        a.output, a.work = str(Path.cwd() / "output"), str(Path.cwd() / "work")
    try:
        a.assemble and assemble(a.output, a.work)
        print(run(a.output, a.work)["report"])
    except Exception as exc:
        print(f"verify: internal error (reported, exit 0): {exc}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print("fatal (suppressed, exit 0)")
        sys.exit(0)
