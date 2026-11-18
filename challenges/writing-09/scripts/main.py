#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-06 CLI: init | check | build (index, audit, finalize). Exit 0 always."""
import argparse, csv, json, io, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C
from core import CAP, MAXB, IMG
read_text, load_json, kind_of = C.read_text, C.load_json, C.kind_of
VER = "3.0.0"
DEFC = ["deliverable", "preserved_facts", "evidence_map", "change_log"]
SKIP = {"task.md", "index.json", "result.json", "draft.json"}

L = {"results": {"zh": "\u7ed3\u679c", "en": "Results"}, "discussion": {"zh": "\u8ba8\u8bba", "en": "Discussion"},
     "limits": {"zh": "\u5c40\u9650", "en": "Limitations"}, "ttl": {"zh": "\u7ed3\u679c\u4e0e\u8ba8\u8bba", "en": "Results and Discussion"}}
CMAP = [(r"limit|\u5c40\u9650", "limitations"), (r"result.?map|readout|\u8bfb\u6570", "results_map"),
        (r"preserv|fact|\u4e8b\u5b9e", "preserved_facts"), (r"evidence|source|\u8bc1\u636e|\u6765\u6e90", "evidence_map"),
        (r"change|log|\u4fee\u6539", "change_log"), (r"uncertain|pending|\u4eba\u5de5", "uncertainty"),
        (r"deliver|manuscript|draft|\u6b63\u6587", "deliverable")]
BAN = "\u5bfc\u81f4 \u9020\u6210 \u56e0\u4e3a \u7531\u4e8e \u673a\u5236 \u8bc1\u660e \u8bc1\u5b9e \u8c03\u63a7 cause because mechanism prove demonstrat".split()
OVER = "\u8bc1\u660e \u8bc1\u5b9e \u786e\u8bc1 \u9996\u6b21 prove proven confirm definitiv establish".split()
BOUND = "\u5c40\u9650 \u4e0d\u80fd\u6392\u9664 \u76f8\u5173\u4e0d\u7b49\u4e8e\u56e0\u679c \u4e0d\u80fd\u8bc1\u660e \u4e0d\u63a8\u65ad\u56e0\u679c limitation association".split()
LAYERS = {"method": "\u65b9\u6cd5 method assay \u68c0\u6d4b endpoint", "sample": "n= \u91cd\u590d replicat sample line",
          "measure": "\u8bef\u5dee\u68d2 error sem sd precision \u7cbe\u5ea6 approx",
          "stat": "\u68c0\u9a8c test p= p< significan statistic multiplicity correction \u663e\u8457"}
NEG = "\u4e0d \u672a \u975e \u65e0 \u65e0\u6cd5 \u4e0d\u80fd not no cannot".split()

def now():
    return datetime.now(timezone.utc).isoformat()[:19]+"Z"  

def dump(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")

def blocks_for(p, rel):
    k, rows, meta = kind_of(p), [], {}
    if k == "text":
        tx = read_text(p).replace("\r\n", "\n")
        if Path(p).suffix.lower() == ".json":
            o, err = load_json(p)
            rows = [("p", x) for x in (json.dumps(o, ensure_ascii=False, indent=1) if o is not None else tx).splitlines() if x.strip()]
            if err:
                meta["error"] = err
        else:
            rows = [("p", x.strip()) for x in re.split(r"\n\s*\n", tx) if x.strip()]
    elif k in ("csv", "tsv"):
        tx, dl = read_text(p), ("," if k == "csv" else "\t")
        try:
            tab = list(csv.reader(io.StringIO(tx), delimiter=dl))
        except Exception:
            tab = [ln.split(dl) for ln in tx.splitlines()]
        tab = [r for r in tab if any(str(c).strip() for c in r)]
        if tab:
            hd = [str(c).strip() for c in tab[0]]
            for i, r in enumerate(tab[1:], 2):
                cs = ["%s=%s" % (hd[j] if j < len(hd) and hd[j] else "c%d" % (j + 1), str(v).strip()) for j, v in enumerate(r) if str(v).strip()]
                if cs: rows.append(("r", "row %d: %s" % (i, " | ".join(cs))))
            meta["header"], meta["rows"] = hd, [["" if c is None else str(c).strip() for c in r] for r in tab[1:]]

    elif k == "pdf":
        rows = [("pg", "PDF text layer not parsed; export text/CSV or paste the caption.")]
    elif k == "image":
        rows = [("fig", IMG + ": no OCR; read axes/units/legend/error bars visually.")]
    out, cnt = [], {}
    for tag, t in rows:
        t = (t or "").strip()
        if not t:
            continue
        cnt[tag] = cnt.get(tag, 0) + 1
        out.append({"loc": "%s#%s%d" % (rel, tag, cnt[tag]), "file": rel, "text": t[:CAP], "tag": tag})
        if len(out) >= MAXB:
            break
    return out, k, meta

def pick(d, names, default=None):
    low = {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    return next((low[n] for n in names if n in low), default)

def find_case(inp):
    if (inp / "case.json").is_file():
        return inp / "case.json"
    c = sorted(x for x in inp.rglob("case*.json") if x.is_file())
    return c[0] if c else None

def find_contract(case):
    c = pick(case, ["output_contract", "contract", "output_fields"]) or {}
    keys = list(c) if isinstance(c, dict) else [str(x.get("field") or x.get("name") or x) if isinstance(x, dict) else str(x) for x in c]
    return [str(k) for k in keys if str(k).lower() != "case_id"] or list(DEFC)

def build_index(inp, contract):
    mats, blocks, tables, errs, seen = [], [], [], [], set()
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or any(x.startswith(".") for x in p.relative_to(inp).parts):
            continue
        if p.name.lower() in SKIP or p.suffix.lower() == ".pyc" or (p.name, p.stat().st_size) in seen:
            continue
        seen.add((p.name, p.stat().st_size))
        rel = p.relative_to(inp).as_posix()
        try:
            bl, kind, meta = blocks_for(p, rel)
        except Exception as e:
            bl, kind, meta, _ = [], kind_of(p), {}, errs.append("%s: %s" % (rel, e))
        q = "visual_only" if kind == "image" else ("unreadable" if not bl else "ok")
        mats.append({"rel": rel, "kind": kind, "bytes": p.stat().st_size, "blocks": len(bl), "quality": q})
        blocks.extend(bl)
        if meta.get("header") and meta.get("rows"):
            tables.append({"rel": rel, "header": meta["header"], "rows": meta["rows"], "locs": [b["loc"] for b in bl]})
    return {"input_root": str(inp), "built_at": now(), "contract": contract, "materials": mats,
            "blocks": blocks, "tables": tables, "errors": errs}

def need_index(a):
    idx, _ = load_json(Path(a.work) / "index.json")
    if idx is None:
        inp = Path(a.input)
        cp = find_case(inp) if inp.is_dir() else None
        case, cerr = load_json(cp) if cp else (None, "no case file")
        idx = build_index(inp, find_contract(case)) if inp.is_dir() else \
            {"blocks": [], "materials": [], "tables": [], "contract": list(DEFC)}
        idx["case_error"] = cerr
        dump(Path(a.work) / "index.json", idx)
    return idx

def hits(words, text):
    out = []
    for w in words:
        i = text.find(w)
        if i >= 0 and not any(x in text[max(0, i - 12):i] for x in NEG):
            out.append(w)
    return out

def run_checks(idx, d, path):
    iss = []
    def A(lv, cd, msg, loc=None, sug=None):
        iss.append({"level": lv, "code": cd, "message": msg, "locator": loc, "suggest": sug})
    if not isinstance(d, dict):
        A("error", "draft_missing", "draft missing: %s" % path)
        return {"draft": str(path), "issues": iss, "counters": {"errors": 1}}
    N, Q = C.numbers, C.quote_status
    R = [s for s in (d.get("results") or []) if isinstance(s, dict)]
    D = [s for s in (d.get("discussion") or []) if isinstance(s, dict)]
    if not R: A("error", "schema", "results: non-empty list required")
    if not D: A("error", "schema", "discussion: non-empty list required")
    ev, vals, aps, cnt = [e for e in (d.get("evidence") or []) if isinstance(e, dict)], set(), set(), [0, 0, 0]
    for i, e in enumerate(ev):
        q, loc = e.get("quote"), e.get("locator")
        if not q or not loc:
            cnt[2] += 1; A("error", "evidence_bad", "evidence[%d]: need quote+locator" % i, loc); continue
        st, found = Q(idx, q, loc)
        if st in ("exact", "span", "misplaced"):
            cnt[0] += 1; vals |= {n["value"] for n in N(q)}
        elif e.get("approx"):
            cnt[1] += 1; aps |= {n["value"] for n in N(q)}
        else:
            cnt[2] += 1; v = N(q)
            A("error", "evidence_bad", "evidence[%d] not verbatim" % i, loc, C.cand_quote(idx, v[0]["value"] if v else None))
    cov = lambda v: v in vals or v in aps
    rtx, dtx, alln = [], [], []
    for i, s in enumerate(R):
        for j, p in enumerate([x for x in (s.get("paragraphs") or []) if isinstance(x, str) and x.strip()]):
            rtx.append(p); low = p.lower()
            for t in N(p):
                alln.append(t)
                if not cov(t["value"]):
                    A("error", "number_unverified", "results[%d].p[%d] %r: no source" % (i, j, t["raw"]), None, [b["loc"] for b in idx["blocks"] if any(abs(n["value"] - t["value"]) < 1e-9 for n in C.numbers(b["text"]))][:2])
            for w in hits(BAN, low):
                A("error", "results_causal", "results[%d].p[%d] %r -> Discussion" % (i, j, w))
            if re.search(r"\u663e\u8457|significan", low) and not re.search(r"p\s*[<>=]\s*0?\.\d+|ANOVA|t-?test|Mann|Kruskal", low):
                A("error", "sig_without_stat", "results[%d].p[%d]: no test/p" % (i, j))
    rset = {n["value"] for n in N(" ".join(rtx))}
    for i, s in enumerate(D):
        for j, p in enumerate([x for x in (s.get("paragraphs") or []) if isinstance(x, str) and x.strip()]):
            dtx.append(p); low = p.lower()
            for w in hits(OVER, low):
                A("error", "overclaim", "discussion[%d].p[%d] %r: hedge it" % (i, j, w))
    dt = " ".join(dtx).lower()
    if dtx and not any(b.lower() in dt for b in BOUND):
        A("warn", "discussion_no_boundary", "Discussion: no boundary sentence")
    wc = lambda ps: sum(len(re.findall(r"[\u4e00-\u9fff]", x)) if C.cjk(x) > 0.3 else len(x.split()) for x in ps)
    rw, dw = wc(rtx), wc(dtx)
    lims = [str(x).strip() for x in (d.get("limitations") or []) if str(x).strip()]
    miss = [k for k, ws in LAYERS.items() if not any(w in " ".join(lims).lower() for w in ws.split())]
    if not lims: A("error", "no_limitations", "limitations empty")
    elif len(lims) < 2 or miss:
        A("warn", "limitations_weak", "%d lim; missing %s" % (len(lims), ", ".join(miss) or "none"))
    for i, f in enumerate([x for x in (d.get("preserved_facts") or []) if isinstance(x, dict)]):
        if not f.get("quote") or not f.get("locator"):
            A("warn", "fact_no_source", "preserved_facts[%d]: need quote+locator" % i)
        elif Q(idx, f["quote"], f["locator"])[0] in ("notfound", "empty"):
            A("error", "fact_bad", "preserved_facts[%d] not verbatim" % i, f["locator"])
    lv = [i["level"] for i in iss]
    return {"draft": str(path), "issues": iss[:120],
            "counters": {"errors": lv.count("error"), "warnings": lv.count("warn"),
                         "evidence_total": len(ev), "evidence_ok": cnt[0], "evidence_failed": cnt[2],  
                         "numbers_total": len(alln), "numbers_verified": sum(1 for t in alln if cov(t["value"])),
                         "numbers_unverified": sum(1 for t in alln if not cov(t["value"])), "results_sections": len(R),
                         "discussion_sections": len(D), "results_words": rw, "discussion_words": dw, "limitations": len(lims)}}

def mapc(key, art):
    hit = next((nm for rx, nm in CMAP if re.search(rx, (key or "").lower())), None)
    return art[hit] if hit else {"status": "not_separately_produced", "see": ["manuscript.md", "results_map.json"]}

def cmd_init(a):
    inp, out, work = Path(a.input), Path(a.out), Path(a.work)
    work.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
    cp = find_case(inp) if inp.is_dir() else None
    case, cerr = load_json(cp) if cp else (None, "no case file")
    ct, cid = find_contract(case), (pick(case, ["case_id", "caseid"]) if isinstance(case, dict) else None)
    r = {"case_id": cid, "status": "partial"}
    r.update({k: None for k in ct if k.lower() != "case_id"})
    r.update({"sources": [], "uncertainty": [], "pending_human": [], "errors": [], "changes": [],
              "degradations": ["init placeholder: run build"], "runtime": {"stage": "init", "wrote_at": now()}})
    dump(out / "result.json", r)
    if not inp.is_dir():
        r.update(status="input_error", errors=["input_error %s" % inp]); dump(out / "result.json", r)
        print("INPUT ERROR: %s" % inp); return
    idx = build_index(inp, ct)
    idx.update({"case_id": cid, "case_error": cerr,
                "instruction": pick(case, ["task_instruction", "instruction", "task"]),
                "contract_raw": pick(case, ["output_contract", "contract"])})
    dump(work / "index.json", idx)
    C.digest(idx, cid, cerr)
    r.update({"sources": idx["materials"], "errors": list(idx["errors"])})
    if not idx["blocks"]: r.update(status="insufficient_evidence", pending_human=["no readable text: %s" % inp])
    dump(out / "result.json", r)

def cmd_check(a):
    idx = need_index(a); dp = Path(a.draft) if a.draft else Path(a.work) / "draft.json"
    d, err = load_json(dp)
    rep = run_checks(idx, d, dp)
    dump(Path(a.work) / "check_report.json", rep)
    c = rep["counters"]
    print("CHECK %s errors=%d warnings=%d | evidence %d ok/%d bad | numbers %d/%d"
          % (dp, c.get("errors", 0), c.get("warnings", 0), c.get("evidence_ok", 0), c.get("evidence_failed", 0),
             c.get("numbers_verified", 0), c.get("numbers_total", 0)))
    for it in rep["issues"][:8]:
        print("  %-4s %-15s %s%s" % (it["level"][:4], it["code"], it["message"][:110], " @" + it["locator"] if it["locator"] else ""))
    print("NEXT:", "fix errors" if c.get("errors") else "build")

def cmd_build(a):
    out, work = Path(a.out), Path(a.work)
    for x in (out, work): x.mkdir(parents=True, exist_ok=True)
    idx = need_index(a); ct, cid = idx.get("contract") or list(DEFC), idx.get("case_id")
    dp = Path(a.draft) if a.draft else work / "draft.json"
    d, derr = load_json(dp); deg = []
    nar = C.narrative(idx)[0]
    if isinstance(d, dict):
        mode = "agent-draft"
        for k in ("results", "discussion"):
            if not [s for s in (d.get(k) or []) if isinstance(s, dict)]:
                d[k] = nar[k]; deg.append(k + " filled")
        if not [x for x in (d.get("limitations") or []) if str(x).strip()]:
            d["limitations"] = nar["limitations"]; deg.append("limitations from gap scan")
    else:
        d, mode = dict(nar), "fallback"; deg.append("no draft: %s" % derr)
    rep = run_checks(idx, d, dp); c = rep["counters"]
    ms, lang = C.assemble(d, L)
    (out / "manuscript.md").write_text(ms, encoding="utf-8")
    rm = [{"section": "1.%d" % i, "paragraph": j, "text": p,
           "readouts": [{"token": t["raw"], "unit": t["unit"], "sources": [b["loc"] for b in idx["blocks"] if any(abs(n["value"] - t["value"]) < 1e-9 for n in C.numbers(b["text"]))][:2]} for t in C.numbers(p)]}
          for i, s in enumerate([x for x in d.get("results") or [] if isinstance(x, dict)], 1)
          for j, p in enumerate([x for x in (s.get("paragraphs") or []) if isinstance(x, str) and x.strip()], 1)]
    em = []
    for i, e in enumerate([x for x in (d.get("evidence") or []) if isinstance(x, dict)]):
        st, found = C.quote_status(idx, e.get("quote"), e.get("locator"))
        em.append({"id": e.get("id") or "e%d" % (i + 1), "quote": e.get("quote"), "locator": found, "verified": st})
    facts = [{"fact": f.get("fact"), "quote": f.get("quote"), "locator": f.get("locator"),
              "verified": C.quote_status(idx, f.get("quote"), f.get("locator"))[0]}
             for f in (d.get("preserved_facts") or []) if isinstance(f, dict)]
    changes = [x for x in (d.get("changes") or []) if isinstance(x, dict)] + [{"action": "assembled manuscript.md", "mode": mode}]
    pend = [x for x in (d.get("pending_human") or []) if isinstance(x, str)] + [x["message"] for x in rep["issues"] if x["level"] == "error"][:5]
    lims = [str(x).strip() for x in (d.get("limitations") or []) if str(x).strip()]
    miss = [k for k, ws in LAYERS.items() if not any(w in " ".join(lims).lower() for w in ws.split())]
    gaps = C.gaps(idx)
    dump(out / "results_map.json", {"case_id": cid, "sections": rm,
        "coverage": {"numbers": c.get("numbers_total", 0), "verified": c.get("numbers_verified", 0)},
        "unverified": [{"token": x["message"], "suggest": x.get("suggest")} for x in rep["issues"] if x["code"] == "number_unverified"]})
    dump(out / "evidence_map.json", {"case_id": cid, "entries": em})
    dump(out / "preserved_facts.json", {"case_id": cid, "facts": facts})
    dump(out / "change_log.json", {"case_id": cid, "changes": changes, "pending_human": pend, "degradations": deg})
    art = {"deliverable": {"path": "manuscript.md", "format": "markdown", "bytes": len(ms.encode("utf-8")), "language": lang, "mode": mode, "text": ms[:12000]},
           "results_map": {"path": "results_map.json", "sections": len(rm), "verified": c.get("numbers_verified", 0)},
           "evidence_map": {"path": "evidence_map.json", "entries": len(em)}, "preserved_facts": facts,
           "limitations": {"items": lims, "layers_missing": miss, "material_gaps": gaps},
           "change_log": {"changes": changes, "pending_human": pend}}
    status = "insufficient_evidence" if not idx.get("blocks") else ("partial" if mode == "fallback" or c.get("errors") else "ok")
    res, filled = {"case_id": cid, "status": status}, 0
    for k in ct:
        res[k] = mapc(k, art); filled += 0 if res[k] in (None, "", [], {}) else 1
    met = dict(c); met.update({"materials": len(idx.get("materials", [])), "tables": len(idx.get("tables", [])), "mode": mode,
                               "traceability_rate": round(c.get("numbers_verified", 0) / c["numbers_total"], 3) if c.get("numbers_total") else 0.0})
    res.update({"output_contract": idx.get("contract_raw") or {k: "" for k in ct},
                "contract_fields": {"total": len(ct), "filled": filled, "keys": ct}, "sources": idx.get("materials", []),
                "uncertainty": [x for x in (d.get("uncertainty") or []) if isinstance(x, str)], "pending_human": pend,
                "errors": list(idx.get("errors") or []),
                "degradations": deg, "changes": changes, "metrics": met,
                "runtime": {"version": VER, "stage": "build", "wrote_at": now()}})
    dump(out / "result.json", res)
    print("BUILD %s status=%s mode=%s contract=%d/%d | %dB | results %d/%d | lim %d | numbers %d/%d | %s"
          % (out, status, mode, filled, len(ct), len(ms.encode("utf-8")), c.get("results_sections", 0),
             c.get("discussion_sections", 0), len(lims), c.get("numbers_verified", 0), c.get("numbers_total", 0),
             "; ".join(deg)[:100] if deg else "none"))

def safe_fail(a, e):
    try:
        r = dict({"case_id": None, "status": "partial"}, **{k: None for k in DEFC})
        r.update({"sources": [], "uncertainty": [str(e)], "pending_human": [], "errors": ["%s: %s" % (type(e).__name__, e)],
                  "degradations": [], "changes": [], "runtime": {"stage": "safefail", "wrote_at": now()}})
        dump(Path(getattr(a, "out", "/app/output")) / "result.json", r)
    except Exception:
        pass
    print("ERROR %s: %s " % (type(e).__name__, e))

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="writing-06 Results+Discussion: init | check | build")
    sub = ap.add_subparsers(dest="cmd", help="index / audit / finalize")
    for nm in ("init", "check", "build"):
        p = sub.add_parser(nm)
        for a_, d_ in (("input", "/input"), ("work", "/app/work"), ("out", "/app/output")):
            p.add_argument("--" + a_, default=os.environ.get("SKILL_" + a_.upper(), d_))
        if nm != "init": p.add_argument("--draft", default=None)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(); return 0
    try:
        {"init": cmd_init, "check": cmd_check, "build": cmd_build}[a.cmd](a)
    except SystemExit:
        raise
    except Exception as e:
        safe_fail(a, e)
    return 0

if __name__ == "__main__":
    sys.exit(main())
