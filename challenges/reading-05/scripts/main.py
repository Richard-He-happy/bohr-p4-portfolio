#!/usr/bin/env python3
"""main.py -- Agent-led multi-document comparison driver (stdlib only).

init  extract corpus -> work/index.json + partial result.json (written first)
show  print paragraphs with locators (--doc D1 --paras 1:20)
check validate work/draft.json: verbatim quotes, provenance, coverage
build comparison_matrix.csv + comparison_table.md + evidence_cards.jsonl + result.json
Defaults --input /input --output /app/output --work /app/work. Exit code always 0.
"""
import argparse, csv, json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as V

GEN = "multi-document-comparison v2"
DIMS = "task dataset sample material method metric unit budget".split()
CK = "source_document_id field_id field_name value unit dataset metric_scope status confidence quote locator note".split()
FILL = [("case", "case_id"), ("status", "status"), ("paper|document|corpus", "papers"), ("field|schema|definition", "fields"),
        ("comparab", "comparability"), ("conflict", "conflicts"), ("agree|consisten|conclusion|finding", "agreement"),
        ("matrix|table|cells|rows", "matrix"), ("evidence|quote|card", "evidence_cards"),
        ("summary|answer|report|synthesis", "summary"), ("limit|uncertain|gap", "limitations"),
        ("coverage|stat|count|quality", "coverage"), ("method|repro", "method"), ("artifact|output_file", "artifacts"),
        ("pending|human", "pending_human"), ("source|provenance", "sources")]


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))


def jwrite(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def twrite(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(s, encoding="utf-8")


def paths(a):
    return (Path(a.input or os.environ.get("SKILL_INPUT", "/input")),
            Path(a.output or os.environ.get("SKILL_OUTPUT", "/app/output")),
            Path(a.work or os.environ.get("SKILL_WORK", "/app/work")))


def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k), v
            yield from walk(v)
    elif isinstance(o, list):
        for v in o[:40]:
            yield from walk(v)


def find_case(inp, errs):
    if not inp.exists():
        errs.append({"code": "input_missing", "detail": "input dir not found: %s" % inp})
        return {}, None
    for p in sorted(inp.rglob("case.json")) or sorted(inp.rglob("*.json")):
        try:
            return jread(p), p
        except Exception as e:
            errs.append({"code": "case_json_invalid", "detail": "%s: %r" % (p.name, e)})
    return {}, None


def find_wo(case, files):
    for f in files:
        if "workorder" in f.name.lower() and f.suffix.lower() == ".json":
            try:
                return jread(f), f.name
            except Exception:
                pass
    return next(((v, "case:" + k) for k, v in walk(case) if "workorder" in k.lower() and isinstance(v, dict)), ({}, ""))


def wo_fields(wo):
    raw = None
    for k, v in walk(wo):
        if k.lower() in ("fields", "field_definitions", "common_fields", "comparison_fields", "columns", "schema", "dimensions") \
                and isinstance(v, (list, dict)) and (raw is None or len(str(v)) > len(str(raw))):
            raw = v
    if isinstance(raw, dict):
        raw = [{"name": k, "definition": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)} for k, v in raw.items()]
    f = V.fields_of({"fields": raw or []}) or [{"field_id": d, "name": d} for d in DIMS]
    return [dict({"definition": "", "unit": "", "value_rule": ""}, **x) for x in f]


def wo_papers(wo):
    raw = next((v for k, v in walk(wo) if k.lower() in ("papers", "documents", "corpus", "sources", "source_documents",
                                                        "paper_list") and isinstance(v, list) and v), [])
    g = lambda it, *ks: next((str(it[k]) for k in ks if isinstance(it, dict) and it.get(k)), "")
    return [{"doc_id": g(it, "doc_id", "id", "source_document_id") or "D%d" % (i + 1),
             "title": it if isinstance(it, str) else g(it, "title", "name"), "file": g(it, "file", "filename", "path")}
            for i, it in enumerate(raw)]


def map_ids(wps, docs):
    use = {}
    for wp in wps:
        b = os.path.basename(wp.get("file") or "").lower()
        t = next((d for d, v in docs.items() if b and (b in v["filename"].lower() or v["filename"].lower() in b)), None)
        if t and t not in use:
            use[t] = wp["doc_id"]
    for k, d in docs.items():
        d["doc_id"], d["workorder_id"] = use.get(k, k), use.get(k)
    return docs


def empty_like(spec):
    t = json.dumps(spec, ensure_ascii=False).lower() if spec is not None else ""
    return [] if ('"array"' in t or '"list"' in t or t == "array" or t.startswith("[")) else ({} if '"object"' in t else None)


def partial(case, cid, errs):
    ct = case.get("output_contract")
    res = {k: empty_like(ct.get(k) if isinstance(ct, dict) else None) for k in V.contract_keys(ct)}
    res.update(case_id=cid, status="partial", sources=[], uncertainty=[], pending_human=[], errors=errs,
               degradations=[], changes=[], runtime=dict(skill=GEN, stage="partial"))
    return res


def fill_contract(case, base):
    ct, res, miss = case.get("output_contract"), {}, []
    for k in V.contract_keys(ct):
        v = base.get(k) if base.get(k) not in (None, "", [], {}) else next(
            (base[x] for pat, x in FILL if re.search(pat, k.lower()) and base.get(x) not in (None, "", [], {})), None)
        if v is None:
            v = base.get(k, empty_like(ct.get(k) if isinstance(ct, dict) else None))
            miss += [k] if v in (None, "", [], {}) else []
        if base.get("summary") and not isinstance(v, str) and "table" in k.lower():
            v = base["summary"]
        res[k] = v
    return res, miss


def cells_for(docs, fields, cells, degr):
    seen, n0 = {(c.get("doc_id"), c.get("field_id")) for c in cells}, len(cells)
    for d, doc in docs.items():
        for f in fields:
            if (d, f["field_id"]) not in seen:
                cells.append({"doc_id": d, "field_id": f["field_id"], "field_name": f["name"], "unit": f.get("unit") or "",
                              "dataset": "", "metric_scope": "", "confidence": "fallback", "value": None, "quote": None,
                              "locator": None, "status": "unreported", "note": "read this paper and fill by hand"})
    if len(cells) > n0:
        degr.append("%d cell(s) missing from the draft were added as unreported placeholders" % (len(cells) - n0))
    return cells


def auto_sections(fields, cells):
    comp = []
    for d in DIMS:
        ids = [f["field_id"] for f in fields if d in (f["field_id"] + str(f["name"])).lower()]
        v = {c["doc_id"]: V.norm(str(c.get("value")), True) for c in cells if c.get("field_id") in ids and c.get("status") == "reported"}
        if v:
            comp.append(dict(dimension=d, doc_ids=sorted(v), comparable=len(set(v.values())) == 1,
                             basis="%d distinct value(s) over %d document(s); pool only within strata" % (len(set(v.values())), len(v))))
    ok = sum(c.get("status") == "reported" for c in cells)
    return comp, {"overall": "insufficient" if not ok else "partially_consistent",
                  "items": [dict(topic="overall effect direction", verdict="insufficient" if not ok else "partially_consistent",
                                 attribution="unresolved", explanation="auto: %d reported cell(s); read the papers to assign direction" % ok)]}


def load_draft(wk):
    p = wk / "draft.json"
    if not p.exists():
        return {}, ""
    try:
        return jread(p), str(p)
    except Exception as e:
        return {"_err": repr(e)}, str(p)


def cmd_init(a):
    t0, (inp, out, wk) = time.time(), paths(a)
    wk.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs, degr = [], []
    case, cp = find_case(inp, errs)
    cid = str(case.get("case_id") or case.get("id") or (cp.parent.name if cp else "unknown"))
    jwrite(out / "result.json", partial(case, cid, errs))
    files = [p for p in sorted(inp.rglob("*")) if p.is_file()] if inp.exists() else []
    ext = (".pdf", ".docx", ".txt", ".md", ".csv", ".tsv", ".json", ".html", ".xlsx", ".pptx")
    mat = [p for p in files if p.suffix.lower() in ext and p.name.lower() != "task.md"
           and "case" not in p.name.lower() and "workorder" not in p.name.lower()]
    wo, wsrc = find_wo(case, files)
    fields, docs = wo_fields(wo), {}
    for i, p in enumerate(mat):
        try:
            d = V.extract_doc(p)
        except Exception as e:
            errs.append({"code": "extract_failed", "detail": "%s: %r" % (p.name, e)})
            d = {"kind": V.kind_of(p), "engine": "failed", "paras": [], "text": "", "notes": ["extraction failed"]}
        d.update(filename=p.name, path=str(p))
        docs["D%d" % (i + 1)] = d
        degr += ["%s: %s" % (p.name, n) for n in d.get("notes") or []]
    wps = wo_papers(wo)
    map_ids(wps, docs)
    jwrite(wk / "index.json", dict(
        case_id=cid, case_path=str(cp or ""), workorder_source=wsrc, generated=time.strftime("%FT%T"),
        docs={d["doc_id"]: dict({k: d.get(k) for k in ("filename", "kind", "engine", "n_pages", "quality", "notes", "path")},
                                n_paras=len(d["paras"]), text_chars=len(d["text"])) for d in docs.values()},
        paras={d["doc_id"]: d["paras"] for d in docs.values()},
        texts={d["doc_id"]: d["text"] for d in docs.values()},
        workorder=dict(question=str(wo.get("question") or wo.get("research_question") or ""), fields=fields,
                       papers=wps, source=wsrc)))
    res = partial(case, cid, errs)
    res.update(sources=[dict(source_document_id=d["doc_id"], file=d["filename"], kind=d["kind"], engine=d["engine"],
                             locator_scheme="<page>#para<n>") for d in docs.values()],
               degradations=degr, pending_human=["read the corpus, author %s, then run check and build" % (wk / "draft.json")],
               runtime=dict(skill=GEN, stage="init", seconds=round(time.time() - t0, 2), docs=len(docs)))
    jwrite(out / "result.json", res)
    print("== corpus ==")
    for d in docs.values():
        print("%s | %s | %s | %d paras | %s | wo=%s" % (d["doc_id"], d["filename"], d["kind"], len(d["paras"]), d["engine"], d.get("workorder_id")))
    print("== workorder (%s) == %s | fields: %s | papers: %s" % (
        wsrc or "none", wo.get("question") or "(no question)", ", ".join(f["field_id"] for f in fields),
        ", ".join(p["doc_id"] for p in wps) or "(none)"))
    print("== next == 1) show --doc <id> 2) write %s 3) check 4) build" % (wk / "draft.json"))
    return 0


def cmd_show(a):
    _, _, wk = paths(a)
    idx = jread(wk / "index.json")
    docs, paras = idx.get("docs") or {}, idx.get("paras") or {}
    if a.doc and a.doc in paras:
        ps = paras[a.doc]
        m = re.match(r"^(\d+)\s*[:\-]\s*(\d+)$", str(a.paras or ""))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, len(ps))
        for p in ps[lo - 1:hi]:
            print("[%s %s] %s" % (a.doc, p["locator"], p["text"][:1200]))
        print("-- %s: %d paragraphs, showed %d..%d" % (a.doc, len(ps), lo, min(hi, len(ps))))
    else:
        print("\n".join("%s | %s | %s | %s paras" % (k, v["filename"], v["kind"], v.get("n_paras")) for k, v in docs.items())
              or "(empty corpus)")
    return 0


def cmd_check(a):
    _, _, wk = paths(a)
    dr, _ = load_draft(wk)
    if "_err" in dr:
        print(json.dumps({"ok": False, "errors": [{"code": "draft_unreadable", "detail": dr["_err"]}]}, ensure_ascii=False))
        return 0
    rep = V.validate(dr, jread(wk / "index.json"))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    for e in rep["errors"][:10]:
        print("FIX [%s] %s :: %s" % (e["code"], e["where"], e["detail"]))
    cn = rep["counts"]
    print("coverage=%s quote_pass=%s reported=%s errors=%d" % (cn["coverage"], cn["quote_pass_rate"], cn["cells_reported"], len(rep["errors"])))
    return 0


def cmd_build(a):
    t0, (inp, out, wk) = time.time(), paths(a)
    out.mkdir(parents=True, exist_ok=True)
    errs, pend, degr = [], [], []
    case, _ = find_case(inp, errs)
    jwrite(out / "result.json", partial(case, str(case.get("case_id") or "unknown"), errs))
    idx = {}
    try:
        idx = jread(wk / "index.json") if (wk / "index.json").exists() else {}
    except Exception as e:
        errs.append({"code": "index_unreadable", "detail": repr(e)})
    if not idx.get("docs"):
        try:
            cmd_init(a)
            idx = jread(wk / "index.json")
        except Exception as e:
            errs.append({"code": "init_failed", "detail": repr(e)})
    docs, wo = idx.get("docs") or {}, idx.get("workorder") or {}
    cid = idx.get("case_id") or str(case.get("case_id") or "unknown")
    dr, dsrc = load_draft(wk)
    if "_err" in dr:
        errs.append({"code": "draft_unreadable", "detail": dr["_err"]})
        dr = {}
    if not dr:
        degr.append("no usable draft.json: cells kept as unreported placeholders (no values invented)")
        pend.append("Agent must read the papers and fill every cell by hand")
    fields = V.fields_of(dr) or wo.get("fields") or [dict(field_id=d, name=d, definition="", unit="", value_rule="") for d in DIMS]
    papers = [{**dict(filename=docs[p["doc_id"]].get("filename"), kind=docs[p["doc_id"]].get("kind"),
                       n_paras=docs[p["doc_id"]].get("n_paras"), engine=docs[p["doc_id"]].get("engine")), **p}
              for p in (V.papers_of(dr) or [{"doc_id": d} for d in docs]) if p.get("doc_id") in docs]
    cells = [c for c in V.cells_of(dr) if c.get("doc_id") in docs]
    if len(V.cells_of(dr)) != len(cells):
        degr.append("%d draft cell(s) cited absent documents and were dropped" % (len(V.cells_of(dr)) - len(cells)))
    for c in cells:
        c.setdefault("field_name", next((f["name"] for f in fields if f["field_id"] == c.get("field_id")), ""))
        c.setdefault("status", "reported" if c.get("value") not in (None, "") else "unreported")
        c.setdefault("confidence", "draft")
    cells = cells_for(docs, fields, cells, degr)
    comp = [c for c in (dr.get("comparability") or dr.get("comparability_checks") or []) if isinstance(c, dict)]
    agr = dr.get("agreement") or dr.get("synthesis") or {}
    if not comp or not (isinstance(agr, dict) and agr.get("overall") and agr.get("items")):
        c2, a2 = auto_sections(fields, cells)
        comp, agr = comp or c2, (agr if isinstance(agr, dict) and agr.get("items") else a2)
        degr.append("comparability/agreement partly derived from field values; condition judgement pending")
    M = dict(case_id=cid, question=dr.get("question") or wo.get("question") or "", papers=papers, fields=fields, matrix=cells,
             comparability=comp, agreement=agr, limitations=dr.get("limitations") or [], uncertainty=dr.get("uncertainty") or [],
             degradations=degr, artifacts=["comparison_matrix.csv", "comparison_table.md", "evidence_cards.jsonl", "result.json"],
             sources=[dict(source_document_id=d, file=docs[d].get("filename"), kind=docs[d].get("kind"),
                           engine=docs[d].get("engine"), n_paras=docs[d].get("n_paras")) for d in docs],
             evidence_cards=[dict(card_id="C%03d" % (i + 1), source_document_id=c["doc_id"], field_id=c["field_id"],
                                  value=c.get("value"), unit=c.get("unit"), dataset=c.get("dataset"),
                                  metric_scope=c.get("metric_scope"), quote=c.get("quote"), locator=c.get("locator"))
                             for i, c in enumerate(x for x in cells if x.get("status") == "reported")])
    rep = V.validate({"fields": fields, "papers": papers, "matrix": cells, "comparability": comp,
                      "conclusions": [c for c in (dr.get("conclusions") or []) if isinstance(c, dict)], "agreement": agr}, idx)
    cn, ok = rep["counts"], rep["counts"]["cells_reported"] > 0
    M.update(coverage=cn, pending_human=pend, status="ok" if (ok and not rep["errors"] and not degr) else
             "partial" if ok else "insufficient_evidence",
             conflicts=[i for i in (agr.get("items") if isinstance(agr, dict) else agr) if i.get("verdict") == "conflicting"],
             method="init extracts locator-bearing paragraphs; the Agent maps every document onto one field schema and records "
                    "value+unit+dataset+metric_scope+quote+locator per cell; comparability is tested per condition before pooling; "
                    "conflicts are attributed to sample/method/metric/condition.")
    if not docs:
        M["status"] = "input_error"
        pend.append("no readable corpus document found under the input directory")
    M["summary"] = V.table_md(M, GEN)
    twrite(out / "comparison_table.md", M["summary"])
    with (out / "comparison_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CK)
        for c in cells:
            w.writerow([c.get("doc_id" if k == "source_document_id" else k, "") for k in CK])
    with (out / "evidence_cards.jsonl").open("w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(c, ensure_ascii=False) for c in M["evidence_cards"]) + "\n")
    res, miss = fill_contract(case, M)
    res.update(case_id=cid, status=M["status"], sources=M["sources"],
               uncertainty=M["uncertainty"] or ["cells with confidence=fallback have no value: read the paper"],
               pending_human=pend + ([] if not rep["errors"] else ["check errors: " + ", ".join(e["code"] for e in rep["errors"][:5])]),
               errors=errs + rep["errors"], degradations=degr,
               changes=[dict(step="build", source=dsrc or "(none)", to=M["artifacts"]),
                        dict(step="contract", resolved=len(V.contract_keys(case.get("output_contract"))) - len(miss))],
               runtime=dict(skill=GEN, stage="build", seconds=round(time.time() - t0, 2), docs=len(docs), fields=len(fields),
                            cells=len(cells), reported=cn["cells_reported"], coverage=cn["coverage"],
                            quote_pass_rate=cn["quote_pass_rate"]))
    if miss:
        res["pending_human"].append("output_contract fields with no matching content: %s" % ", ".join(miss))
    jwrite(out / "result.json", res)
    print("status=%s docs=%d fields=%d cells=%d reported=%d coverage=%s quote_pass=%s" % (
        M["status"], len(docs), len(fields), len(cells), cn["cells_reported"], cn["coverage"], cn["quote_pass_rate"]))
    print("artifacts:", ", ".join(M["artifacts"]), "| unfilled contract:", miss or "none")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="Agent-led multi-document comparison (%s)" % GEN)
    sub = ap.add_subparsers(dest="cmd")
    for n, h in (("init", "extract corpus + partial result.json"), ("show", "print paragraphs with locators"),
                 ("check", "validate the Agent draft"), ("build", "render CSV/MD/cards + result.json")):
        q = sub.add_parser(n, help=h)
        for f in ("--input", "--output", "--work"):
            q.add_argument(f)
        if n == "show":
            q.add_argument("--doc")
            q.add_argument("--paras")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[a.cmd](a)
    except Exception as e:
        import traceback
        try:
            inp, out, _ = paths(a)
            out.mkdir(parents=True, exist_ok=True)
            jwrite(out / "result.json", partial(find_case(inp, [])[0], "unknown",
                                                [{"code": "unhandled_exception", "detail": "%s: %s" % (type(e).__name__, e),
                                                  "trace": traceback.format_exc()[-900:]}]))
        except Exception:
            pass
        print("ERROR %s: %s" % (type(e).__name__, e), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
