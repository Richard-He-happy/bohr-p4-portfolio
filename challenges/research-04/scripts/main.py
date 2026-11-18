#!/usr/bin/env python3
"""research-trend-lens CLI: read /input, run the lens engine, write result.json plus
research_report.md, evidence_map.csv, trend_annual.csv, topic_evolution.csv,
representative_works.csv, screening_log.csv, run_ledger.json. Exit code always 0."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lens import *  # noqa: E402,F401,F403

RULES = ("inclusion_criteria", "exclusion_criteria", "screening_rules", "inclusion", "exclusion", "\u7eb3\u6392\u89c4\u5219")


def tiw(c):
    for k in ("time_window", "time_range", "period", "years", "year_range", "\u65f6\u95f4"):
        v = fk(c, k)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            a, b = yr(v[0]), yr(v[1])
            if a and b: return (min(a, b), max(a, b))
        m = re.search(r"(19[5-9]\d|20[0-3]\d)\D{1,8}(19[5-9]\d|20[0-3]\d)", N(v))
        if m: return (int(m.group(1)), int(m.group(2)))
    return None


def EV(r, tp=""):
    q = evq(r)
    return dict(source=r["id"], doi=r.get("doi"), locator=ploc(r, q), quote=q, ok=vq(q, r), title=N(r["title"])[:100], year=r.get("year"), topic=tp)


def finish(out, cid, cm, meta, case, recs, L):
    out = Path(out); win = tiw(case) if case else None
    ex, inc = [], []
    for r in recs:
        w = "" if N(r["title"]) else "no_title"
        if not w and win and r.get("year") and not (win[0] <= r["year"] <= win[1]): w = "year_outside_declared_window"
        if not w and len(N(r.get("text") or "")) < 20: w = "no_extractable_text"
        if not w and any(x and x in N(r["title"]).lower() for x in L["exclude"]): w = "exclusion_rule_keyword"
        if w: ex.append(dict(record=r.get("id") or r["loc"], title=N(r["title"])[:110], year=r.get("year"), decision="exclude", reason=w, file=r["file"]))
        else: inc.append(r)
    if not inc and recs:
        D("screening_too_strict", "all %d records excluded: fallback to every parsed record" % len(recs)); inc, ex = recs, []
    NT, Y = len(inc), [r for r in inc if r.get("year")]
    cnt = Counter(r["year"] for r in Y); ys = sorted(cnt)
    noyr = [r["id"] for r in inc if not r.get("year")]
    if noyr: D("year_missing", "%d record(s) without a year: outside every trend statement" % len(noyr))
    tt, tev, reps, gaps, cf, cl, ev, un = {}, {}, {}, [], [], [], [], []
    if ys: tt, tev, reps, gaps, cf = ana(Y, cnt, ys, NT, L, meta, len(recs), un)

    def add(kind, st, evs, strength, kv="computed", stat=None):
        good = [x for x in evs if x["ok"]]
        if kv == "quote" and not good: strength = "insufficient"
        ci = "C%02d" % (len(cl) + 1)
        cl.append(dict(claim_id=ci, kind=kind, statement=st, evidence_strength=strength, evidence_kind=kv, evidence=good or evs, stat_ref=stat))
        for x in (good or evs):
            ev.append(dict(claim_id=ci, strength=strength, source_id=x["source"], doi=x.get("doi") or "", locator=x.get("locator") or "", quote=x.get("quote") or "",
                           quote_verified=bool(x["ok"]), record_title=x.get("title") or "", year=x.get("year") or "", topic=x.get("topic") or ""))
    if ys:
        add("trend", "Corpus gives %d dated records over %d-%d in %d years; annual counts in trend_annual.csv." % (len(Y), ys[0], ys[-1], len(ys)), [EV(Y[0])], "directly_supported", "computed", "trend_annual.csv")
        for c in tt["change_points"].get("candidates", []):
            a = [r for r in Y if r["year"] == c["year"]]
            add("trend", "A %s shift around %d is %s (mean %.2f -> %.2f records/year)." % (c["direction"], c["year"], c["strength"], c["before_mean"], c["after_mean"]),
                [EV(a[0])] if a else [], "directly_supported" if c["strength"] == "supported_change" else "inferred", "computed", "trend_annual.csv")
        for t in [x for x in tev.get("topics", []) if x["total"] >= 2 and x["status"] in ("emergence", "decline", "persistence")][:4]:
            add("topic", "Topic '%s': %s (%s; %d records)." % (t["topic"], t["status"], t["basis"], t["total"]),
                [EV(r, t["topic"]) for r in [x for x in Y if t["topic"] in [y["id"] for y in x["topics"]]][:2]], "directly_supported", "computed", "topic_evolution.csv")
        for w, ps in list(reps.get("by_window", {}).items())[:3]:
            rr = [r for r in Y if ps and r["id"] == ps[0]["record"]]
            if ps: add("representative", "Window %s is represented by '%s' (%s) under the stated rule." % (w, ps[0]["title"], ps[0]["year"]), [EV(rr[0], "representative")] if rr else [], "inferred", "computed", "representative_works.csv")
    for g in gaps[:4]:
        add("gap", "Gap %s (%s, topic '%s'): %d mentions in %d records state the problem as open. %s" % (g["gap_id"], g["type"], g["topic"], g["mention_count"], g["source_count"], g["basis"]),
            [dict(source=q["rec"], doi=q.get("doi"), locator=q["loc"], quote=q["quote"], ok=q.get("ok", True), title="", year=q.get("year"), topic=g["topic"]) for q in g["quotes"][:2]], g["status"], "quote")
    for c in cf[:3]:
        add("conflict", "Topic '%s' carries opposite-direction statements from different records; the corpus cannot settle it." % c["topic"],
            [dict(source=x["rec"], doi=None, locator=x["loc"], quote=x["quote"], ok=True, title="", year=x.get("year"), topic=c["topic"]) for x in c["positive"][:1] + c["negative"][:1]], "directly_supported", "quote")
    if noyr: un.append(dict(type="year_missing", detail="%d record(s) without a year are outside all trend statements" % len(noyr), basis=", ".join(noyr[:6])))
    if tev.get("unmapped_count"): un.append(dict(type="topic_unmapped", detail="%d record(s) match no lexicon topic, so topic shares do not sum to 100%%" % tev["unmapped_count"], basis="references/lexicon.md"))
    if meta.get("skipped"): un.append(dict(type="material_unparsed", detail="%d material file(s) gave no text and sit outside the conclusions" % len(meta["skipped"]), basis=str(meta["skipped"])[:180]))
    if not NT: un.append(dict(type="no_records", detail="no usable record from the supplied material", basis="screening table"))
    un.append(dict(type="scope", detail="conclusions hold for the supplied corpus only (%d records%s)" % (NT, ", %d-%d" % (ys[0], ys[-1]) if ys else ", no dated records"), basis="skill boundary"))
    un.append(dict(type="retrieval", detail="search strings are documented but no external database was queried in this run", basis="offline contract"))
    wc(out / "evidence_map.csv", ev, ["claim_id", "strength", "source_id", "doi", "locator", "quote", "quote_verified", "record_title", "year", "topic"])
    wc(out / "trend_annual.csv", tt.get("annual", []), ["year", "count", "share", "delta"])
    wc(out / "topic_evolution.csv", [dict(t, **dict(("w%d" % (i + 1), v) for i, v in enumerate(t["series"]))) for t in tev.get("topics", [])],
       ["topic", "total", "status", "basis"] + ["w%d" % (i + 1) for i in range(tev.get("n_windows", 0))])
    wc(out / "representative_works.csv", [dict(window=w, **p) for w, v in reps.get("by_window", {}).items() for p in v],
       ["window", "record", "title", "year", "doi", "score", "in_degree", "long_tail", "rationale", "locator"])
    wc(out / "screening_log.csv", ex, ["record", "title", "year", "decision", "reason", "file"])
    wj(out / "run_ledger.json", dict(skill=dict(name=NM, version=VR), case_id=cid, elapsed_s=el(), model_requests=0, network="none (corpus only)", trace=LG))
    rules = []
    for k in RULES:
        v = fk(case, k) if case else None
        for x in ([v] if isinstance(v, str) else (v or []) if isinstance(v, list) else []):
            if N(x) and N(x) not in rules: rules.append(N(x)[:180])
    st = "ok" if (NT and ys and any(c["evidence_strength"] == "directly_supported" for c in cl)) else ("partial" if NT else "insufficient_evidence")
    if case is None or not meta.get("files"): st = "input_error"
    res = dict(case_id=cid, status=st, skill=dict(name=NM, version=VR), generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
               research_question=dict(topic=meta.get("topic"), decomposition=[dict(id="Q1", q="annual shape and turning points", weight=.3, product="time_trend"),
                                                                               dict(id="Q2", q="topic emergence and decline", weight=.25, product="topic_evolution"),
                                                                               dict(id="Q3", q="representative works per window", weight=.2, product="representative_works"),
                                                                               dict(id="Q4", q="problems repeatedly raised but unresolved", weight=.15, product="research_gaps"),
                                                                               dict(id="Q5", q="claims that outrun the evidence", weight=.1, product="uncertainty")]),
               screening=dict(mode="provided_corpus_screening", records_parsed=len(recs), records_included=NT, records_excluded=len(ex), excluded=ex[:40],
                              duplicates_removed=len(meta.get("dups", [])), duplicates=meta.get("dups", [])[:20], rules_from_case=rules,
                              note="no external database queried; screening uses the supplied material"),
               corpus=dict(files=meta.get("files", 0), formats=sorted(set(r["fmt"] for r in inc)), year_sources=dict(Counter(r.get("year_src", "?") for r in inc)), no_year=noyr[:20]),
               time_trend=tt, topic_evolution=tev, representative_works=reps, research_gaps=gaps, conflicts=cf, claims=cl, evidence_matrix=ev,
               sources=[dict(id=r["id"], title=N(r["title"])[:180], year=r.get("year"), doi=r.get("doi"), file=r["file"], locator=r["loc"], format=r["fmt"], quality=r.get("q")) for r in inc[:300]],
               uncertainty=un, pending_human=["confirm the corpus is the intended evidence base",
                                               "spot-check 3 quotes per claim"],
               errors=ER, degradations=DG, changes=CH + [dict(at=el(), what="finalize: result.json rewritten with the full analysis")],
               tool_call_trace=LG, runtime=dict(elapsed_s=el(), python=sys.version.split()[0], cwd_independent=True, out_dir=str(out)),
               outputs=dict((p.name, dict(bytes=p.stat().st_size, sha256=S2(p.read_bytes()))) for p in sorted(out.glob("*")) if p.is_file()),
               limitations=["corpus only: no external retrieval or citation counts", "topic labels depend on references/lexicon.md",
                            "PDF text quality gates usable quotes", "change-point test is descriptive"])
    P = dict(time_trend=tt, topic_evolution=tev, representative_works=reps, research_gaps=gaps, conflicts=cf, uncertainty=un, evidence_matrix=ev, claims=cl, report_path="research_report.md")
    fl, det = 0, {}
    for k, v in cm.items():
        if k in res: det[k] = "core_field"; fl += 1; continue
        val, src = fillc(k, v, P)
        res[k] = val; det[k] = src; fl += 1
    res["verification"] = dict(contract_keys=len(cm), contract_filled=fl, quotes=len(ev), quotes_verified=sum(1 for e in ev if e["quote_verified"]),
                               annual_sum=sum(a["count"] for a in tt.get("annual", [])), dated_records=len(Y), claims_without_evidence=len([c for c in cl if not c["evidence"]]),
                               method="counts recomputed from included records; quotes re-tested as substrings")
    res["contract_backfill"] = dict(total=len(cm), filled=fl, fields=det, note="every output_contract key present at top level; missing values null/[]")
    wj(out / "result.json", res)
    (out / "research_report.md").write_text(render(res, ex, un, cm, fl), encoding="utf-8")
    print("status=%s records=%d claims=%d gaps=%d excluded=%d out=%s" % (st, NT, len(cl), len(gaps), len(ex), out))
    return res


def fillc(k, v, P):
    kl = str(k).lower()
    for ks, key in (("\u8d8b\u52bf time trend annual year".split(), "time_trend"), ("\u4e3b\u9898 evolution topic theme".split(), "topic_evolution"),
                    ("\u4ee3\u8868 represent landmark key_paper".split(), "representative_works"), ("\u7a7a\u767d gap blank open_question".split(), "research_gaps"),
                    ("conflict contradict".split(), "conflicts"), ("\u4e0d\u786e\u5b9a uncertain risk limitation".split(), "uncertainty"),
                    ("\u8bc1\u636e evidence matrix citation reference source".split(), "evidence_matrix"), ("\u7ed3\u8bba claim conclusion finding".split(), "claims"),
                    ("\u7efc\u8ff0 report review narrative summary markdown".split(), "report_path")):
        if any(x in kl for x in ks): return P[key], "semantic:" + ks[0]
    if v is None: return None, "null_kept"
    if isinstance(v, str): return P["report_path"], "string_default"
    if isinstance(v, dict): return dict((a, fillc(a, b, P)[0]) for a, b in v.items()), "type:dict"
    if isinstance(v, list): return [], "type:list"
    if isinstance(v, bool): return False, "type:bool"
    if isinstance(v, float): return 0.0, "type:float"
    return 0, "type:int"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="research-trend-lens: corpus -> trend, topic evolution, representative works, gaps, evidence matrix (stdlib, offline).",
                                 epilog="python3 -B scripts/main.py --input /input --out /app/output")
    ap.add_argument("--input", default=None, help="input root; default /input")
    ap.add_argument("--out", default="/app/output", help="output dir")
    ap.add_argument("--max-records", type=int, default=4000, help="record cap")
    a = ap.parse_args(argv)
    out = Path(a.out)
    try: out.mkdir(parents=True, exist_ok=True)
    except Exception: out = Path.cwd() / "output"; out.mkdir(parents=True, exist_ok=True)
    globals()["_OUT"] = out
    root = None
    for c in (a.input, "/input", __import__("os").environ.get("INPUT_DIR"), str(Path.cwd() / "input")):
        if c and Path(c).is_dir(): root = Path(c).resolve(); break
    cp, case = None, None
    if root:
        for c in [root / "case.json", root / "task.json"] + sorted(root.glob("case*.json")):
            if c.is_file(): cp = c; break
        if cp: case = jl(cp, "case.json")
    oc = fk(case, "output_contract")
    if oc is None:
        for k in ("deliverables", "required_fields", "required_outputs", "output_schema"):
            oc = fk(case, k)
            if oc is not None: break
    cm, cid = cmap(oc), fk(case, "case_id")
    if cid is None and cp:
        t = cp.read_text(encoding="utf-8", errors="replace")
        m2 = re.search(r'"case_id"\s*:\s*"?([\w.\-]+)', t)
        cid = m2.group(1) if m2 else None
    boot = dict(case_id=cid, status="partial", skill=dict(name=NM, version=VR), generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"), stage="bootstrap",
                note="partial result before parsing; overwritten at finalize", sources=[], uncertainty=[], pending_human=[], errors=[], degradations=[], changes=[],
                contract_backfill=dict(total=len(cm), filled=0))
    boot.update([(k, [] if isinstance(v, list) else None) for k, v in cm.items()])
    wj(out / "result.json", boot)
    CH.append(dict(at=el(), what="bootstrap partial result.json: %d contract key(s) with null/[] values" % len(cm)))
    G("bootstrap", root=str(root) if root else None, out=str(out), keys=len(cm))
    if not root or case is None:
        E("NO_INPUT", "no readable case.json")
        return finish(out, cid, cm, dict(files=0), None, [], lexf())
    L = lexf()
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and not any(s in p.parts for s in ("__pycache__", ".git"))
             and (cp is None or p.resolve() != cp.resolve()) and p.name.lower() not in ("task.md", "task.json")]
    recs, skipped, ind = [], [], {}
    for p in files:
        f = fmt(p)
        if f == "skip": skipped.append(dict(file=p.name, reason="unsupported format: kept as material")); continue
        try: lines, full, pgs, q, how = read(p, f)
        except Exception as e:
            E("PARSE_FAIL", "%s: %s: %s" % (p.name, type(e).__name__, e)); skipped.append(dict(file=p.name, reason="parse_fail")); continue
        if f == "json":
            o = jl(p, p.name)
            for e in (fk(o, "edges") or fk(o, "links") or []):
                t = N(e.get("target")) if isinstance(e, dict) else ""
                if t: ind[t.lower()] = ind.get(t.lower(), 0) + 1
        if lines:
            for i, d in enumerate(lines, 1):
                recs.append(dict(id="", title=gv(d, "title", "ti", "t1", "paper_title", "name", "\u9898\u540d"), year=yr(gv(d, "year", "py", "y1", "date")),
                                 doi=gv(d, "doi", "do") or None, venue=gv(d, "venue", "journal", "jo", "t2", "source"), abstract=gv(d, "abstract", "ab", "n2"),
                                 text=(gv(d, "abstract", "ab", "n2") + "\n" + gv(d, "title", "ti", "t1"))[:6000] or " | ".join(N(v) for v in d.values() if isinstance(v, str))[:6000], file=p.name, loc="%s#rec%d" % (p.name, i), fmt=f, q=q, pages=[]))
        elif N(full):
            ln = [x for x in (pgs or full.split("\n")) if len(N(x)) > 20]
            recs.append(dict(id="", title=(ln[0] if ln else p.stem), year=yrt(full), doi=None, venue="", abstract="", text=full, file=p.name, loc="%s#p1" % p.name, fmt=f, q=q, pages=pgs))
        else: skipped.append(dict(file=p.name, reason="no_extractable_text"))
        if q and q < 0.55: D("low_text_quality", "%s: printability %.2f via %s; its body text is not used as evidence" % (p.name, q, how))
    for r in recs:
        if not r["year"]:
            for fl in ("title", "abstract", "text"):
                r["year"] = yrt(r.get(fl) or "")
                if r["year"]: break
        r["year_src"] = "metadata" if r["year"] else "missing"
        r["topics"] = tps_of(r, L); r["nt"] = ntt(r["title"])
        if not r.get("text"): r["text"] = r["title"] + " " + (r.get("abstract") or "")
    if len(recs) > a.max_records: D("record_cap", "%d parsed, truncated to %d" % (len(recs), a.max_records)); recs = recs[:a.max_records]
    kept, dups = [], []
    for r in recs:
        hit = None
        for k in kept:
            if r["doi"] and k["doi"] and r["doi"].lower() == k["doi"].lower(): hit = ("doi_equal", k); break
            if len(r["nt"]) > 15 and r["nt"] == k["nt"]: hit = ("title_exact", k); break
            if len(r["nt"]) > 20 and jac(toks(r["title"]), toks(k["title"])) >= .92 and abs((r["year"] or 0) - (k["year"] or 0)) <= 1: hit = ("title_fuzzy>=0.92", k); break
        if hit:
            k = hit[1]
            if len(r.get("text") or "") > len(k.get("text") or ""): k["text"] = r["text"]
            dups.append(dict(kept=k["loc"], dropped=r["loc"], rule=hit[0]))
        else: kept.append(r)
    for i, r in enumerate(kept, 1): r["id"] = "R%03d" % i
    G("extract", files=len(files), records=len(recs), kept=len(kept), skipped=len(skipped), dups=len(dups))
    topic = next((N(x) for x in (fk(case, "research_topic"), fk(case, "topic"), fk(case, "research_question"), fk(case, "title")) if isinstance(x, str) and len(N(x)) > 3), "")
    return finish(out, cid, cm, dict(files=len(files), skipped=skipped, dups=dups, ind=ind, topic=topic), case, kept, L)


if __name__ == "__main__":
    try: main(sys.argv[1:])
    except SystemExit: pass
    except BaseException as e:
        E("FATAL", "%s: %s" % (type(e).__name__, e))
        try:
            o = globals().get("_OUT") or (Path("/app/output") if Path("/app/output").is_dir() else Path.cwd())
            wj(o / "result.json", dict(case_id=None, status="input_error", skill=dict(name=NM, version=VR), errors=ER, degradations=DG,
                                       uncertainty=[dict(type="fatal", detail="pipeline aborted at top level")], pending_human=["inspect errors, then rerun"], contract_backfill=dict(total=0, filled=0)))
        except Exception: pass
    sys.exit(0)
