#!/usr/bin/env python3
"""appraise.py - 文献质量评价 CLI。见 SKILL.md。"""
import argparse, csv, hashlib, io, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E

HERE, SV, T0 = Path(__file__).resolve().parent, "1.0.0", time.time()
R = {k: [] for k in ("errors", "degradations", "pending_human", "uncertainty", "changes", "missing", "sources")}
CAND = ("rank candidate_id title authors year venue doi url source_db retrieved_at query_id relevance_score "
        "relevance_reason screening_decision exclusion_reason fulltext_available metadata_confidence flags").split()
ITEM = ("doc_id dimension item_id item_label judgment evidence_quote locator_page locator_section evidence_scope "
        "quote_verified char_start probe_hit confidence abstain_reason human_override override_reason "
        "adjudication").split()
KIND = {".json": "json", ".jsonl": "jsonl", ".csv": "csv", ".tsv": "csv", ".docx": "docx", ".pdf": "pdf",
        ".txt": "txt", ".md": "txt", ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image"}
GROUPS = [("status", "status state"), ("case_id", "caseid taskid"),
          ("citations", "citation cluster network graph"),
          ("grades", "grade overall verdict summary conclusion doclevel"),
          ("screening", "screen filter selection included excluded prisma"),
          ("coverage", "coverage gap omission recall completeness"),
          ("appraisal_items", "apprais quality evaluat critiq bias risk item dimension evidence"),
          ("candidates", "candidate paper record literature article item result bibliograph"),
          ("queries", "quer log trail trace history"), ("sources", "source provenance reference"),
          ("uncertainty", "uncertain note remark comment caveat limitation unknown")]

def iso(t=None):
    return datetime.fromtimestamp(t or time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def add(k, m):
    if m not in R[k]:
        R[k].append(m)

def w(p, o, cols=None):
    """原子写：cols 时写 CSV(UTF-8 BOM)，str 时写文本，否则写 JSON。"""
    p = Path(p)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if cols:
            b = io.StringIO()
            wr = csv.DictWriter(b, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            for r in o:
                wr.writerow({c: ("" if r.get(c) is None else json.dumps(r[c], ensure_ascii=False)
                                if isinstance(r.get(c), (list, dict)) else r[c]) for c in cols})
            p.write_text("\ufeff" + b.getvalue(), encoding="utf-8")
        elif isinstance(o, str):
            p.write_text(o, encoding="utf-8")
        else:
            t = Path(str(p) + ".tmp")
            t.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(t, p)
    except Exception as e:
        add("errors", "write_failed:%s:%s" % (p.name, type(e).__name__))

def tmpl(v):
    return {k: tmpl(x) for k, x in v.items()} if isinstance(v, dict) else ([] if isinstance(v, list) else None)

def gkey(k):
    n = E.nk(k)
    return next((g for g, ws in GROUPS if any(w in n for w in ws.split())), None)

def fill_contract(ct, vals):
    t, un = tmpl(ct if isinstance(ct, dict) else {}), []
    for k in t:
        g = gkey(k)
        un += [] if g in vals else [str(k)]
        t[k] = vals.get(g)
    return t, un

def kind_of(p):
    h = b""
    try:
        h = p.open("rb").read(8)
    except Exception:
        pass
    return ("pdf" if h[:4] == b"%PDF" else "image" if h[:2] in (b"\x89P", b"\xff\xd8")
            else KIND.get(p.suffix.lower(), "zip" if h[:2] == b"PK" else "other"))

def scan(ind):
    return [(p, 0) for p in sorted(ind.rglob("*"))
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() != ".tmp"][:400]

def read_case(ind):
    ps = ([ind / "case.json"] if (ind / "case.json").exists() else []) + \
         [p for p in sorted(ind.rglob("case*.json"))]
    for p in dict.fromkeys(ps):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            if isinstance(d, dict):
                return d, p
        except Exception as e:
            add("errors", "case_json_unparsable:%s:%s(其 output_contract 未回填)" % (p.name, type(e).__name__))
            m = re.search(r'"case_?id"\s*:\s*"([^"]+)"', p.read_text(encoding="utf-8", errors="replace"), re.I)
            if m:
                return {"case_id": m.group(1)}, p
    if (ind / "task.md").exists():
        add("missing", "case.json(task.md 兜底)")
        return {"task_instruction": (ind / "task.md").read_text("utf-8", "replace")[:4000]}, ind / "task.md"
    add("errors", "no_case_json:%s" % ind)
    return {}, None

def walkq(obj, depth=0, out=None):
    out = [] if out is None else out
    if depth > 12:
        return out
    if isinstance(obj, dict):
        if E.is_query(obj):
            out.append(obj)
        for v in obj.values():
            walkq(v, depth + 1, out)
    elif isinstance(obj, list):
        for v in obj:
            walkq(v, depth + 1, out)
    return out

def parse_inputs(ind, files):
    recs, qs, docs, meta = [], [], [], []
    for p, size in files:
        k, rel = kind_of(p), str(p.relative_to(ind))
        info = {"rel": rel, "kind": k, "status": "ok"}
        meta.append(info)
        try:
            if k in ("pdf", "docx", "txt"):
                pages, src = (E.pdf_pages(p) if k == "pdf" else
                              ([E.docx_text(p)], "docx:native") if k == "docx" else
                              ([p.read_text(encoding="utf-8", errors="replace")], "text:file"))
                info.update(pages=len(pages), text_source=src)
                if pages:
                    docs.append({"pages": pages, "text_source": src, "src": rel})
                else:
                    info["status"] = "no_text"
                    add("pending_human", "no_text:%s(需OCR)" % rel)
            elif k == "image":
                info["status"] = "image_only"
                add("pending_human", "image:%s(需人工核验)" % rel)
            elif k in ("json", "jsonl"):
                txt, objs = p.read_text(encoding="utf-8", errors="replace"), []
                if k == "json":
                    try:
                        objs = [json.loads(txt)]
                    except Exception:
                        add("degradations", "json_bad:%s" % rel)
                else:
                    for ln, line in enumerate(txt.splitlines(), 1):
                        if line.strip():
                            try:
                                objs.append(json.loads(line))
                            except Exception:
                                add("degradations", "jsonl_bad_line:%s:%d" % (rel, ln))
                for o in objs:
                    found = E.walk(o)
                    recs += [(d, ptr, rel) for d, ptr in found]
                    if found:
                        info["records"] = info.get("records", 0) + len(found)
                    qs += [(q, rel) for q in walkq(o)]
            else:
                add("degradations", "unsupported:%s" % rel)
        except Exception as e:
            info.update({"status": "error", "error": type(e).__name__})
            add("degradations", "parse_failed:%s" % rel)
    return recs, qs, docs, meta

def slug(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def catalog(recs, docs):
    C, O = {}, []
    for d, ptr, src in recs:
        r = E.mk_rec(d, ptr, src)
        if not (r["title"] or r["doi"]):
            continue
        key = "doi:" + r["doi"] if r["doi"] else "t:" + slug(r["title"])[:80]
        c = C.get(key)
        if not c:
            r.update(_key=key, flags=[], candidate_id=None, fulltext_available=False,
                     metadata_confidence="high" if (r["doi"] and r["year"] and r["title"]) else
                     ("medium" if (r["title"] and (r["year"] or r["doi"])) else "low"))
            C[key] = r
            O.append(key)
            continue
        for f in ("title", "year", "venue", "doi", "url", "abstract", "source_db", "retrieved_at", "query_id",
                  "authors"):
            c[f] = c.get(f) or r.get(f)
        c["provenance"] += r["provenance"]
        if "merged_duplicate" not in c["flags"]:
            c["flags"].append("merged_duplicate")
            add("changes", "merged:%s" % key[:40])
        if ((r["year"] and c["year"] and r["year"] != c["year"]) or (r["venue"] and c["venue"] and
            r["venue"].lower() != c["venue"].lower())) and "metadata_conflict" not in c["flags"]:
            c["flags"].append("metadata_conflict")
            add("uncertainty", "conflict:%s" % key[:40])
    for doc in docs:
        t = "\n".join(E.norm(x) for x in doc["pages"])
        if len(t.strip()) < 40 or sum(1 for ch in t if ch.isalnum() or
                                      ch in " .,;:()[]%/-") / max(len(t), 1) <= 0.80:
            add("pending_human", "garbled:%s" % doc["src"])
            continue
        m = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", t[:30000])
        key = ("doi:" + m.group(0).rstrip(".,;)").lower()) if m else None
        if key not in C:
            hs = slug(t[:3000])
            key = next((k for k in O if len(slug(C[k].get("title"))[:70]) > 12 and
                        slug(C[k].get("title"))[:70] in hs), None)
        if key is None:
            key = "f:" + hashlib.sha1(t[:200].encode()).hexdigest()[:10]
            first = next((ln.strip() for ln in doc["pages"][0].split("\n") if len(ln.strip()) > 25), None)
            C[key] = {"_key": key, "candidate_id": None, "title": E.norm(first)[:300] if first else None,
                      "authors": [], "year": None, "venue": None, "doi": None, "url": None, "abstract": None,
                      "source_db": "input_pdf", "retrieved_at": None, "query_id": None,
                      "flags": ["metadata_from_pdf_first_line"], "metadata_confidence": "low",
                      "provenance": [{"source_file": doc["src"], "json_pointer": "/"}]}
            O.append(key)
            add("uncertainty", "metadata_from_pdf:%s" % doc["src"])
        C[key].update(fulltext_available=True, _pages=doc["pages"], _tsrc=doc["text_source"])
    return C, O

def build_docs(C, O):
    out = []
    for i, k in enumerate(O, 1):
        c, d = C[k], {"doc_id": "d%03d" % i, "candidate_id": C[k]["candidate_id"], "title": C[k].get("title"),
                      "abstract": C[k].get("abstract"), "doi": C[k].get("doi"), "year": C[k].get("year"),
                      "text": "", "page_starts": [0], "pages": 0, "text_source": "none"}
        if c.get("_pages"):
            pg, st, off = [x for x in (E.norm(y) for y in c["_pages"]) if x], [], 0
            for x in pg:
                st.append(off)
                off += len(x) + 1
            d.update(text="\n".join(pg), page_starts=st, pages=len(pg),
                     text_source=c.get("_tsrc") or "text:unknown")
        elif c.get("abstract"):
            d["text_source"] = "abstract:metadata"
        out.append(d)
    return out

def run(cnt):
    recs, qs, docs, meta = parse_inputs(cnt["ind"], scan(cnt["ind"]))
    C, O = catalog(recs, docs)
    tms = E.terms(cnt["case"])
    for i, k in enumerate(O, 1):
        c = C[k]
        c["candidate_id"] = "c%03d" % i
        c["relevance_score"], c["relevance_reason"] = E.score(c, tms)
        c["screening_decision"], c["exclusion_reason"] = E.decide(c, cnt["case"], c["relevance_score"])
    rows, apprs, DL = [], [], build_docs(C, O)[:cnt["max_docs"]]
    for d in DL:
        if time.time() - T0 > cnt["deadline"]:
            add("pending_human", "deadline_reached:%s" % d["doc_id"])
            continue
        try:
            d.update(E.detect_design(d))
            rr = E.appraise(d, cnt["items"], cnt["ov"])
            g = E.grade_doc(rr, d["design"], d["text_source"].startswith(("pdf:", "docx:", "text:")))
            rows += rr
            apprs.append(dict({x: d.get(x) for x in ("doc_id", "candidate_id", "title", "doi", "design",
                                                    "design_confidence", "text_source", "pages")},
                              items=len(rr), coverage=g["grade_trace"]["coverage"], **g))
        except Exception as e:
            add("degradations", "appraise_failed:%s" % d["doc_id"])
    jud, ver = [r for r in rows if r["judgment"] in ("reported", "partially_reported", "not_reported")], \
               [r for r in rows if r["quote_verified"] == "verified"]
    full = sum(1 for d in DL if d["text_source"].startswith(("pdf:", "docx:", "text:")))
    abso = sum(1 for d in DL if d["text_source"] == "abstract:metadata")
    met = {"items_total": len(rows), "items_judged": len(jud), "items_verified": len(ver),
           "evidence_anchor_rate": round(len(ver) / len(jud), 3) if jud else 0.0,
           "abstain_rows": sum(1 for r in rows if r["judgment"] == "unappraisable"),
           "not_reported_rows": sum(1 for r in rows if r["judgment"] == "not_reported"),
           "dimension_coverage": round(len({r["dimension"] for r in jud} & {"D1", "D2", "D3", "D4", "T"}) / 5.0, 3),
           "naive_reference": {"dimension_coverage": 0.2, "evidence_anchor_rate": 0.0, "note": "内部对照"}}
    cs = [dict({k: (i if k == "rank" else C[x].get(k)) for k in CAND}, flags=C[x].get("flags", []))
          for i, x in enumerate(O, 1)]
    qs2 = E.qrecs(qs, meta)
    for q in qs2:
        q["retained"] = sum(1 for c in cs if c["query_id"] == q["query_id"] and c["screening_decision"] == "include")
    return {"candidates": cs, "queries": qs2, "appraisals": apprs, "items": rows, "grades": apprs,
            "meta": meta, "metrics": met,
            "coverage": {"documents_in_scope": len(DL), "appraised": len(apprs), "fulltext": full,
                         "abstract_only": abso, "no_text": len(DL) - full - abso, "recall_estimate": None,
                         "gaps": (["abstract_only:%d" % abso] if abso else []) +
                                 ([] if full else ["no_fulltext_in_input"]),
                         "recall_note": "离线材料无法估计召回；只报告输入内覆盖与缺口"}}

def emit(outd, out):
    outd = Path(outd)
    w(outd / "candidates.csv", out["candidates"], CAND)
    w(outd / "appraisal.csv", out["items"], ITEM)
    w(outd / "query_log.json", {"count": len(out["queries"]), "queries": out["queries"]})
    w(outd / "appraisal_report.md", "\n".join(
        ["# 文献质量评价表 (%s)" % iso(), "> 证据定位见 appraisal.csv。", ""] +
        ["- %s｜%s｜%s｜风险 %s｜置信 %s｜覆盖 %s" % (a["doc_id"], a.get("title") or "-", a["design"],
                                              a["overall_risk"], a["confidence"], a["coverage"])
         for a in out["appraisals"]]))
    return dict(candidates_csv=str(outd / "candidates.csv"), appraisal_csv=str(outd / "appraisal.csv"),
                query_log=str(outd / "query_log.json"), report=str(outd / "appraisal_report.md"))

def assemble(out, cnt, arts, rv, det):
    for k, v in E.NOTES.items():
        for m in v:
            add(k, m)
    case, rows = cnt["case"], out["items"]
    if not (case or out["meta"]):
        st = "input_error"
    elif not (out["candidates"] or rows):
        st = "insufficient_evidence"
    else:
        st = "partial" if (R["pending_human"] or R["errors"] or
                           any(r.get("abstain_reason") == "no_text" for r in rows)) else "ok"
    vals = dict(candidates=out["candidates"], queries=out["queries"], appraisal_items=rows, grades=out["appraisals"],
                coverage=out["coverage"], status=st, case_id=case.get("case_id"), uncertainty=R["uncertainty"],
                sources=R["sources"])
    ct, un = fill_contract(case.get("output_contract") or {}, vals)
    r = {"case_id": case.get("case_id"), "status": st, "artifacts": arts, "output_contract": ct,
         "output_contract_echo": case.get("output_contract"), "output_contract_unfilled": un,
         "candidates": out["candidates"], "queries": out["queries"],
         "appraisals": out["appraisals"], "appraisal_items": rows, "grades": out["appraisals"],
         "coverage": out["coverage"], "metrics": out["metrics"],
         "skill": {"name": "literature-quality-appraisal", "version": SV, "rubric_version": rv},
         "inputs": {"dir": str(cnt["ind"]), "case_json": str(cnt["case_path"] or ""), "files": out["meta"]},
         "task": {"instruction": (case.get("task_instruction") or "")[:2000],
                  "scope": case.get("organizer_supplied_scope") or {}},
         "selfcheck": {"contract_keys_resolved": not un,
                       "verified_rows_located": all(q.get("evidence_quote") and (q.get("locator_page") or 0) >= 1
                                                    for q in rows if q.get("quote_verified") == "verified"),
                       "unappraisable_reasoned": all(q.get("abstain_reason") for q in rows if q.get("judgment") == "unappraisable")},
         "runtime": {"started_at": iso(T0), "finished_at": iso(), "elapsed_s": round(time.time() - T0, 2),
                     "python": sys.version.split()[0], "determinism": det,
                     "budget": {"model_requests": 0, "network": False, "deadline_s": cnt["deadline"]}}}
    r.update({k: R[k] for k in ("sources", "uncertainty", "pending_human", "errors", "degradations", "changes",
                                "missing")})
    r["artifacts"] = arts
    return r

def main(argv=None):
    ap = argparse.ArgumentParser(description="文献质量评价：候选集+检索日志+证据锚定评价表+分级",
                                 epilog="退出码恒 0；先写 partial result.json，再 finalize。")
    ap.add_argument("--input", default=None, help="输入目录(默认 /input 或 ./input)")
    ap.add_argument("--output", default=None, help="输出目录(默认 /app/output 或 ./output)")
    a = ap.parse_args(argv)
    ind = Path(a.input) if a.input else (Path("/input") if Path("/input").exists() else Path("input"))
    outd = Path(a.output) if a.output else (Path("/app/output") if Path("/app").exists() else Path("output"))
    outd.mkdir(parents=True, exist_ok=True)
    case, cpath = (read_case(ind) if ind.exists() else ({}, None))
    case = case or {}
    w(outd / "result.json", {"case_id": case.get("case_id"), "status": "partial", "errors": [],
                             "skill": {"name": "literature-quality-appraisal", "version": SV},
                             "output_contract": tmpl(case.get("output_contract") or {})})
    if not ind.exists():
        add("errors", "no_input_dir:%s" % ind)
    items, rv = E.rubric(HERE.parent / "references" / "rubric.md")
    ov = {}
    if (outd / "appraisal.csv").exists():
        try:
            for row in csv.DictReader((outd / "appraisal.csv").open(encoding="utf-8-sig")):
                if row.get("human_override"):
                    ov[(row.get("doc_id"), row.get("item_id"))] = row["human_override"]
        except Exception:
            add("degradations", "override_read")
    cnt = {"ind": ind, "case": case, "items": items, "ov": ov, "case_path": cpath,
           "deadline": 780.0, "max_docs": 30}
    out = {"candidates": [], "queries": [], "appraisals": [], "items": [], "grades": [], "docs": [], "meta": [],
           "metrics": {}, "coverage": {}}
    try:
        out = run(cnt)
        det = {"sha1": hashlib.sha1(json.dumps([out["items"], out["candidates"]], sort_keys=True,
                                              ensure_ascii=False).encode()).hexdigest()[:16],
               "note": "重跑应得同一 sha1"}
    except Exception as e:
        add("errors", "pipeline_failed:%s:%s" % (type(e).__name__, str(e)[:120]))
        det = {"sha1": None}
    try:
        arts = emit(outd, out)
    except Exception as e:
        add("errors", "emit_failed")
        arts = {}
    res = assemble(out, cnt, arts, rv, det)
    w(outd / "result.json", res)
    print("status=%s candidates=%d items=%d errors=%d -> %s" % (
        res["status"], len(res["candidates"]), len(res["appraisal_items"]), len(res["errors"]), outd))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.exit(0)
