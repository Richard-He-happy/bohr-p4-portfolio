#!/usr/bin/env python3
"""main.py -- literature-review-evidence-mapper collect stage: materials -> corpus(locators) + dedup + themes + candidate quotes + screening + partial result.json. Stdlib only, offline, CWD independent. Run assemble via verify.py."""
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, time, traceback, unicodedata, zipfile
from collections import Counter
from pathlib import Path

N, V = "literature-review-evidence-mapper", "1.0.0"
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
try:
    import verify as VF
except Exception:
    VF = None
sources = (lambda c: VF.sources(c.docs)) if VF else (lambda c: [])
backfill = (lambda res, con: VF.backfill(res, con)) if VF else (lambda res, con: res)
try:
    T = json.loads((H.parent / "references" / "templates.json").read_text("utf-8"))
except Exception:
    T = {}
STOP, MK, CRIT = set(T.get("stop") or []), T.get("markers") or [], T.get("criteria") or {}
TEXTY = (".md", ".txt", ".rst", ".tex", ".bib", ".html", ".xml", ".yml")
DOI, YR = re.compile(r"10\.\d{4,9}/[-._;()/:\w]+", re.I), re.compile(r"(?:19|20)\d{2}")
TR = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
                    "\u2212": "-", "\u00ad": "", "\ufb01": "fi", "\ufb02": "fl", "\u00a0": " ", "\u2026": "..."})

def iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(s or "")).translate(TR)).strip().lower()

def sq(s):
    return re.sub(r"[\s\-]+", "", norm(s))

def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")

def wc(p, rows, cols):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in cols} for r in rows)

def rd(p):
    b = Path(p).read_bytes()
    for e in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "replace")

class C:
    def __init__(s, i, o, w):
        s.i, s.o, s.w = i, o, w
        s.case, s.docs, s.files, s.rq, s.themes, s.contract = {}, [], [], {}, [], {}
        s.err, s.deg, s.pend, s.t0 = [], [], [], time.time()

    def E(s, m):
        s.err.append({"at": iso(), "msg": str(m)[:400]})

    def D(s, m):
        len(s.deg) < 50 and s.deg.append({"at": iso(), "msg": str(m)[:300]})

    def P(s, i, w, a):
        i = str(i)[:200]
        any(p["item"] == i for p in s.pend) or s.pend.append({"item": i, "why": str(w)[:200], "action": str(a)[:200]})

def kind(p):
    x = p.suffix.lower()
    if x in (".pdf", ".docx", ".xlsx", ".csv", ".tsv", ".json", ".jsonl") + TEXTY:
        return x
    h = p.open("rb").read(4) if p.exists() else b""
    return ".pdf" if h.startswith(b"%PDF") else "?"

def pdf_blocks(p, c):
    tool = shutil.which("pdftotext") or shutil.which("pdf-text-tool")
    if not tool:
        c.D(f"{p.name}: no pdftotext")
        c.P(f"PDF unparsed: {p.name}", "no pdftotext", "install poppler-utils")
        return [], "none"
    try:
        t = subprocess.run([tool, str(p), "-"], capture_output=True, timeout=90).stdout.decode("utf-8", "replace")
        bl = [{"locator": f"p.{i+1}", "text": x.strip()} for i, x in enumerate(t.split("\f")) if x.strip()]
        if bl and len(t.strip()) > 40:
            return bl, "pdftotext"
        c.D(f"{p.name}: no text layer")
    except Exception as e:
        c.D(f"pdftotext failed {p.name}: {e}")
    return [], "none"

def tab_blocks(p, c):
    if p.suffix.lower() in (".json", ".jsonl"):
        o = json.loads(rd(p))
        recs = o if isinstance(o, list) else next((v for v in o.values() if isinstance(v, list) and v and isinstance(v[0], dict)), [])
        return [{"locator": f"rec.{i}", "text": json.dumps(r, ensure_ascii=False)[:3000],
                 "fields": {k: v for k, v in r.items() if isinstance(v, str)}}
                for i, r in enumerate([x for x in recs if isinstance(x, dict)], 1)], "json"
    with open(p, newline="", encoding="utf-8-sig", errors="replace") as fh:
        rows = list(csv.reader(fh, delimiter="\t" if p.suffix.lower() == ".tsv" else ","))
    head = [h.strip() for h in rows[0]] if rows else []
    return [{"locator": f"row.{i}", "text": " | ".join(r)[:3000],
             "fields": {head[j]: r[j] for j in range(min(len(head), len(r))) if head[j]}}
            for i, r in enumerate(rows[1:], 2) if any(y.strip() for y in r)], "csv"

FKEYS = (("title", ("title", "题名", "标题", "name")), ("doi", ("doi",)), ("year", ("year", "年", "年份", "pub_year")),
         ("authors", ("author", "作者")), ("venue", ("journal", "venue", "期刊", "source")))

def meta_of(p, bl, f):
    m = dict.fromkeys(("title", "year", "doi", "authors", "venue"))
    for k, v in (f or {}).items():
        kl, vs = str(k).lower(), v.strip() if isinstance(v, str) else ""
        fld = ("doi" if "doi" in kl else "authors" if ("author" in kl or "作者" in kl) else
               "venue" if any(t in kl for t in ("journal", "venue", "期刊")) else
               "year" if kl.startswith("year") or kl in ("年", "年份") else
               "title" if any(t in kl for t in ("title", "题名", "标题")) else None)
        if vs and fld and not m[fld]:
            m[fld] = vs[:300]
    m["year"] = (lambda y: int(y.group(0)) if y else None)(YR.search(str(m["year"] or "")))
    head = " ".join(b["text"][:3000] for b in bl[:2])
    d = DOI.search(head)
    m["doi"] = m["doi"] or (d.group(0).rstrip(".,;)") if d else None)
    m["title"] = m["title"] or next((x.strip() for b in bl[:4] for x in b["text"].split("\n")[:6]
                                    if 18 <= len(x.strip()) <= 260 and not re.match(r"^(abstract|摘要|keywords|关键词|doi|http|www|\d)", x.strip(), re.I)), None) \
        or re.sub(r"[_\-]+", " ", p.stem)[:200]
    y = YR.search(p.name) or YR.search(head[:1200])
    m["year"] = m["year"] or (int(y.group(0)) if y else None)
    return m

def abs_of(bl):
    for b in bl:
        h = re.search(r"(?:^|\n)\s*(abstract|摘要)\b[.:：\s]*", b["text"], re.I)
        if h:
            seg = b["text"][h.end():h.end() + 2400].strip()
            if len(seg) > 40:
                return seg, b["locator"]
    return None, None

def txt_blocks(t):
    bl = []
    for s in (x.strip() for x in re.split(r"\n\s*\n", t) if x.strip()):
        for i in range(0, len(s), 3500):
            bl.append({"locator": f"para.{len(bl)+1}", "text": s[i:i + 3500]})
    return bl

def discover(c):
    if not c.i.exists():
        c.E("input dir missing")
        return []
    fs = []
    for root, ds, names in os.walk(c.i):
        ds[:] = [d for d in ds if not d.startswith(".") and d != "__pycache__"]
        for n in sorted(names):
            not n.startswith(".") and not n.endswith(".py") and fs.append(Path(root) / n)
            if len(fs) >= 300:
                c.D("cap 300")
                return fs
    return fs

def load_case(c):
    for p in [c.i / "case.json"] + sorted(c.i.glob("case*.json")) + sorted(c.i.glob("**/case*.json")):
        if p.is_file():
            try:
                o = json.loads(rd(p))
                isinstance(o, dict) and c.case.update(o)
                if c.case:
                    return c.case
            except Exception as e:
                c.E(f"case JSON parse failed {p.name}: {e}")
    c.E("no case.json; empty case")
    return {}

RQK = ("research_question", "question", "research_goal", "task_instruction", "task", "objective", "topic", "aim")

def derive_rq(c):
    rq = {"primary": "", "source": "missing", "sub_questions": [], "scope": c.case.get("organizer_supplied_scope"),
          "pico": dict.fromkeys(("population", "intervention", "comparison", "outcome"))}
    for k in RQK:
        v = c.case.get(k)
        cand = ([(k, v)] if isinstance(v, str) else [(f"{k}.{kk}", v[kk]) for kk in RQK if isinstance(v, dict) and isinstance(v.get(kk), str)])
        hit = next(((path, txt) for path, txt in cand if len(txt.strip()) > 12), None)
        if hit:
            rq["primary"], rq["source"] = hit[1].strip()[:2000], "case." + hit[0]
            break
    if not rq["primary"]:
        t = next((f for f in c.files if f.name.lower() in ("task.md", "task.txt")), None)
        rq["primary"], rq["source"] = (rd(t)[:2000].strip() if t else ""), (f"file:{t.name}" if t else "missing")
    rq["primary"] or c.P("research question missing", "no research_question / task_instruction", "supply RQ text")
    return rq

def terms(t):
    t = norm(t)
    out = {w for w in re.findall(r"[a-z][a-z\-]{3,}", t) if w not in STOP}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        out |= {run[i:i + 2] for i in range(len(run) - 1) if run[i:i + 2] not in STOP}
    return out

def jac(a, b):
    return len(a & b) / float(len(a | b)) if a and b else 0.0

def rel(d, rq):
    return round(len(terms((d.get("title") or "") + " " + (d.get("abstract") or "") + " " + d["text"][:4000]) & rq)
                 / float(max(4, len(rq))), 3) if rq else 0.0

def build(c):
    docs = []
    for p in c.files:
        if p.name.lower() in ("case.json", "task.md"):
            continue
        k = kind(p)
        if k == ".xlsx":
            c.D(f"{p.name}: xlsx unparsed, export to CSV")
            c.P(f"xlsx unparsed: {p.name}", "no sheet reader", "export CSV")
            continue
        try:
            if k == ".pdf":
                bl, ex = pdf_blocks(p, c)
            elif k == ".docx":
                c.D(f"{p.name}: docx unparsed, convert to txt/md")
                c.P(f"docx unparsed: {p.name}", "no docx reader", "convert to md/txt")
                continue
            elif k in (".csv", ".tsv", ".json", ".jsonl"):
                bl, ex = tab_blocks(p, c)
            elif k in TEXTY:
                bl, ex = txt_blocks(rd(p)), "text"
            else:
                c.D(f"skipped: {p.name}")
                continue
        except Exception as e:
            c.D(f"{p.name}: extraction failed: {e}")
            continue
        txt = "\n\n".join(b["text"] for b in bl)[:320000]
        txt.strip() or c.D(f"{p.name}: no text extracted")
        m = meta_of(p, bl, next((b["fields"] for b in bl if b.get("fields")), None))
        ab, al = abs_of(bl)
        docs.append(dict(path=str(p), rel=p.name, kind=k, extractor=ex, blocks=bl, text=txt, chars=len(txt),
                         sha1=hashlib.sha1(txt.encode("utf-8", "replace")).hexdigest()[:16], title=m["title"],
                         year=m["year"], doi=m["doi"], authors=m["authors"], venue=m["venue"], abstract=ab,
                         abstract_locator=al, fulltext=len(txt) > 1200,
                         metadata_estimated=not any(b.get("fields") for b in bl)))
    prim = {}
    for i, d in enumerate(docs, 1):
        d["source_id"] = f"S{i:02d}"
        key = "d:" + norm(d["doi"]) if d.get("doi") else "t:" + norm(d.get("title")) + "|" + str(d.get("year"))
        if key in prim:
            d["duplicate_of"] = prim[key]["source_id"]
        else:
            prim[key] = d
    c.docs = docs
    return docs

def cluster(c, rq):
    pool = [d for d in c.docs if not d.get("duplicate_of")]
    bags = {d["source_id"]: terms((d.get("title") or "") + " " + (d.get("abstract") or "") + " " + d["text"][:2500]) for d in pool}
    cl = []
    for d in sorted(pool, key=lambda x: -rel(x, rq)):
        k, bj = max(((k, jac(bags[d["source_id"]], k["bag"])) for k in cl), key=lambda kj: kj[1], default=(None, 0.0))
        if k and bj >= 0.12:
            k["docs"].append(d["source_id"])
            k["bag"] |= bags[d["source_id"]]
        else:
            cl.append({"docs": [d["source_id"]], "bag": set(bags[d["source_id"]])})
    cl.sort(key=lambda x: -len(x["docs"]))
    while len(cl) > 7:
        max(cl[:6], key=lambda k: jac(cl[-1]["bag"], k["bag"]))["docs"] += cl.pop()["docs"]
    out = []
    for i, k in enumerate(cl, 1):
        top = [t for t, _ in Counter(t for s in k["docs"] for t in bags.get(s, ())).most_common(5)]
        out.append({"theme_id": f"T{i}", "label": " / ".join(top[:2]) or f"T{i}", "sources": sorted(k["docs"]),
                    "n_sources": len(k["docs"]), "derived_from": "corpus_cluster", "boundary": None,
                    "basis": "shared terms: " + (", ".join(top[:4]) or "n/a")})
    return out

def cands(docs, rq, per=6):
    rows = []
    for d in docs:
        if d.get("duplicate_of"):
            continue
        sc = []
        for b in d.get("blocks", []):
            for s in re.split(r"(?<=[.!?。！？])\s+", re.sub(r"\s+", " ", b.get("text", ""))):
                s = s.strip()
                if 48 <= len(s) <= 460 and not re.match(r"^(figure|table|fig\.|图|表|references|参考文献)\b", s, re.I):
                    v = 2 * len(terms(s) & rq) + 2 * sum(1 for m in MK if m in norm(s)) + bool(re.search(r"\d", s))
                    v >= 3 and sc.append((v, b["locator"], s))
        sc.sort(key=lambda x: -x[0])
        seen = set()
        for v, loc, s in sc:
            if sq(s)[:80] not in seen and len(seen) < per:
                seen.add(sq(s)[:80])
                rows.append({"source_id": d["source_id"], "locator": loc, "quote": s, "score": v, "topic": None})
    return rows

def screens(c, rq):
    rows = []
    for d in c.docs:
        r, dup = rel(d, rq), bool(d.get("duplicate_of"))
        dec = "exclude" if dup or r < 0.06 else "include"
        code = "E5" if dup else "E1" if r < 0.06 else "I1" if d.get("fulltext") else "I2"
        rows.append({"source_id": d["source_id"], "title": (d.get("title") or "")[:160], "year": d.get("year"),
                     "doi": d.get("doi"), "kind": d["kind"], "fulltext": bool(d.get("fulltext")), "relevance": r,
                     "decision": dec, "reason_code": code, "criterion": None,
                     "note": f"duplicate of {d['duplicate_of']}" if dup else f"overlap {r}"})
    return rows

def proto(c):
    key = "、".join(sorted(terms(c.rq.get("primary") or ""))[:6]) or "the research question"
    return {"research_question": {"primary": c.rq.get("primary"), "sub_questions": [], "pico": c.rq.get("pico") or {}},
            "criteria": json.loads(json.dumps(CRIT).replace("{KEY}", key)),
            "dedup_rule": "DOI first else norm title+year", "strength_rule": "references/evidence_schema.md",
            "written_before_screening": False, "criteria_source": "auto_template_unconfirmed"}

def base(c):
    return {"case_id": c.case.get("case_id"), "skill": {"name": N, "version": V}, "status": "partial", "mode": "collect_only",
            "research_question": c.rq, "counts": {}, "coverage": {}, "screening": {}, "themes": [], "evidence_rows": [],
            "evidence_summary": {}, "conflicts": [], "gaps": [], "uncertainty": [], "sources": [], "references": [],
            "review": {}, "artifacts": {}, "contract_backfill": {}, "pending_human": [], "errors": [], "degradations": [],
            "changes": [], "output_contract_echo": c.contract or None,
            "pipeline_steps": {k: False for k in ("discover", "extract", "protocol", "screen", "theme", "evidence", "draft")},
            "runtime": {"skill_version": V, "python": sys.version.split()[0], "started": iso(), "elapsed_s": 0}}

def do_collect(c):
    [d.mkdir(parents=True, exist_ok=True) for d in (c.i, c.w, c.o)]
    load_case(c)
    c.contract = c.case.get("output_contract") or c.case.get("output_schema") or c.case.get("result_contract") or {}
    res = base(c)
    wj(c.o / "result.json", res)
    c.rq = derive_rq(c)
    c.files = discover(c)
    build(c)
    rq = terms(c.rq.get("primary") or "")
    c.themes = cluster(c, rq)
    cd, scr, pr = cands(c.docs, rq), screens(c, rq), proto(c)
    c.contract and wj(c.w / "case.json", {"case_id": c.case.get("case_id"), "output_contract": c.contract})
    wj(c.w / "corpus.json", {"documents": c.docs, "generated": iso()})
    wj(c.w / "themes.json", c.themes)
    wj(c.w / "next_steps.json", {"order": ["protocol.json", "screening.csv", "evidence_map.csv", "review.md"],
                                 "protocol_template": pr})
    wc(c.w / "candidates.csv", cd, ["source_id", "locator", "quote", "score", "topic"])
    wc(c.w / "screening.csv", scr, ["source_id", "title", "year", "doi", "kind", "fulltext", "relevance", "decision",
                                    "reason_code", "criterion", "note"])
    dec = Counter(r["decision"] for r in scr)
    res.update({"themes": c.themes, "research_question": c.rq, "sources": sources(c), "pending_human": list(c.pend), "errors": list(c.err),
                "degradations": list(c.deg), "screening": {"counts": dict(dec), "protocol": pr, "log_path": "screening.csv"},
                "counts": {"files": len(c.files), "documents": len(c.docs), "included": dec["include"], "excluded": dec["exclude"], "duplicates": sum(1 for d in c.docs if d.get("duplicate_of")),
                           "fulltext": sum(1 for d in c.docs if d.get("fulltext")),
                           "blocks": sum(len(d.get("blocks", [])) for d in c.docs), "candidate_sentences": len(cd)},
                "mode": "collect_only"})
    res["pipeline_steps"].update({"discover": True, "extract": bool(c.docs), "theme": bool(c.themes)})
    if not c.docs:
        res["status"] = "insufficient_evidence"
        c.P("no usable material", "no parsable literature", "supply PDF/CSV/JSON")
    backfill(res, c.contract)
    res["runtime"]["elapsed_s"] = round(time.time() - c.t0, 2)
    res["pending_human"] = list(c.pend)
    wj(c.o / "result.json", res)
    return res

def do_assemble(c):
    if not (c.w / "corpus.json").exists():
        c.D("corpus.json absent; collect first")
        do_collect(c)
    if VF is None:
        c.E("verify.py unavailable; assemble skipped")
        return None
    return VF.assemble(c.o, c.w)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="collect: materials->corpus+themes+candidates+screening+partial result.json; "
                    "assemble: merge agent artifacts, quote gate, final result.json",
        epilog="main.py [collect|assemble|all] [--input D] [--output D] [--work D]; exit 0 always")
    ap.add_argument("stage", nargs="?", default="all", choices=["collect", "assemble", "all"], help="stage")
    [ap.add_argument(f"--{d}", help=f"{d} dir") for d in ("input", "output", "work")]
    ap.add_argument("--version", action="version", version=f"{N} {V}")
    a = ap.parse_args(argv)
    env = {"input": "INPUT_DIR", "output": "OUTPUT_DIR", "work": "WORK_DIR"}
    dflt = {"input": ["/input", str(Path.cwd() / "input")], "output": ["/app/output", str(Path.cwd() / "output")],
            "work": ["/app/work", str(Path.cwd() / "work")]}
    pick = lambda k: next((Path(x).resolve() for x in [getattr(a, k), os.environ.get(env[k])] + dflt[k] if x and Path(x).exists()),
                          Path(getattr(a, k) or dflt[k][0]).resolve())
    c = C(pick("input"), pick("output"), pick("work"))
    try:
        if a.stage != "assemble":
            do_collect(c)
        if a.stage != "collect":
            do_assemble(c)
    except Exception as e:
        c.E(f"{type(e).__name__}: {e} | {traceback.format_exc()[-400:]}")
        try:
            r = base(c)
            r.update({"status": "partial", "mode": f"{a.stage}_failed", "errors": list(c.err),
                      "degradations": list(c.deg), "pending_human": list(c.pend), "sources": sources(c) if c.docs else []})
            backfill(r, c.contract)
            wj(c.o / "result.json", r)
        except Exception:
            pass
    print(f"[{N} {V}] stage={a.stage} input={c.i} output={c.o} work={c.w}")
    print(f"  docs={len(c.docs)} errors={len(c.err)} pending={len(c.pend)} degradations={len(c.deg)} "
          f"elapsed={round(time.time()-c.t0,1)}s -> {c.o / 'result.json'}")
    [print(f"  ! {e['msg'][:150]}") for e in c.err[:5]]
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print("fatal (suppressed, exit 0):", traceback.format_exc()[-400:])
        sys.exit(0)
