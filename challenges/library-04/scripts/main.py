"""research-library-qa pipeline: inventory, version chains, grounded Q&A.

Reads <input>/case.json + materials; hashes and extracts every file; builds a provenance-labelled inventory;
groups duplicates by sha256; infers version chains; answers questions with verbatim quotes and locators; writes
result.json (partial first, finalized unconditionally), inventory.csv, version_chain.json, answers.md,
reorganize_plan.csv, operations.log. Exit 0 always; stdlib only; no network; no CWD reliance.
"""
import argparse, csv, difflib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library as L  # noqa: E402

NAME, VERSION = "research-library-qa", "1.0.0"
QKEY = re.compile(r"(questions?|quer(?:y|ies)|search[_ ]?tasks?|asks?|prompts?|qa|q)$", re.I)
QID = ("id", "qid", "question_id", "q_id", "key")
QTXT = ("question", "query", "q", "text", "prompt", "ask", "task", "instruction")
ALIAS = {a: k for k, v in {"inventory": "file_list files inventory", "library": "library tree dir_tree",
    "versions": "versions version_chain version_relations", "questions": "answers qa questions retrieval evidence citations",
    "operations": "operations log", "coverage_dimensions": "coverage"}.items() for a in v.split()} | {
    k: k for k in ("duplicates", "metadata", "skipped", "failures", "errors", "conflicts", "uncertainty", "status", "summary", "sources")}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dwrite(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_case(indir):
    case, src, errs = {}, None, []
    for cand in sorted(indir.glob("case*.json")):
        try:
            case, src = json.loads(cand.read_text(encoding="utf-8", errors="replace")), str(cand)
            break
        except Exception as e:
            errs.append({"stage": "case_load", "path": str(cand), "error": type(e).__name__}) if cand.is_file() else None
    if not isinstance(case, dict):
        case = {"_raw_case": case}
    task = next((t.read_text(encoding="utf-8", errors="replace") for t in (indir / "task.md", indir / "TASK.md") if t.is_file()), "")
    return case, task, src, errs


def harvest(node, out, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and QKEY.fullmatch(str(k)) and len(v.strip()) > 3:
                out.append({"text": v.strip(), "id": None, "from": path + "/" + str(k)})
            elif isinstance(v, (dict, list)):
                harvest(v, out, path + "/" + str(k))
    elif isinstance(node, list):
        tag = path.split("/")[-1] if path else ""
        for v in node:
            if isinstance(v, str) and QKEY.search(tag) and len(v.strip()) > 3:
                out.append({"text": v.strip(), "id": None, "from": path})
            elif isinstance(v, dict):
                txt = next((v[k] for k in QTXT if isinstance(v.get(k), str) and len(v[k]) > 3), None)
                if txt:
                    out.append({"text": txt.strip(), "from": path, "id": next((str(v[k]) for k in QID if v.get(k) not in (None, "")), None)})
                else:
                    harvest(v, out, path)


def questions_of(case):
    raw, seen, qs = [], set(), []
    harvest(case, raw)
    for q in raw:
        t = re.sub(r"\s+", " ", q["text"]).strip()
        if t.lower() not in seen:
            seen.add(t.lower())
            qs.append({"qid": q["id"] or "Q%d" % (len(qs) + 1), "question": t, "from": q["from"]})
    return qs


def echo_contract(contract, res):
    keys = [str(k) for k in contract] if isinstance(contract, dict) else \
        [str(it if isinstance(it, str) else (it.get("name") or it.get("field") or "")) for it in contract if isinstance(it, (str, dict))] if isinstance(contract, list) else []
    for k in keys:
        a = ALIAS.get(k.lower())
        if k and a in res and not res.get(k):
            res[k] = res[a]
        elif k and k not in res:
            res[k] = [] if k.lower().endswith("s") else None
    res["output_contract_fields"] = keys
    return keys


def sidecar_overrides(recs):
    ov = {}
    for r in [x for x in recs if x["role"] == "sidecar"]:
        try:
            p = Path(r["path"])
            if r["ext"] == ".json":
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                items = data if isinstance(data, list) else next((data[k] for k in ("files", "materials", "items", "entries") if isinstance(data.get(k), list)), [])
            elif r["ext"] in (".csv", ".tsv"):
                items = list(csv.DictReader(p.read_text(encoding="utf-8", errors="replace").splitlines()))
            else:
                continue
            for it in items:
                key = next((str(it[k]) for k in ("path", "rel", "file", "filename", "name") if isinstance(it.get(k), str)), None) if isinstance(it, dict) else None
                if key:
                    ov.setdefault(key.strip(), {}).update({f: (v, "sidecar:" + r["name"]) for f, v in it.items() if f not in ("path", "rel", "file", "filename", "name")})
        except Exception:
            pass
    return ov


def apply_overrides(recs, metas, ov):
    for r in recs:
        key = next((k for k in (r["rel"], r["name"]) if k in ov), None)
        if key:
            for f, (v, s) in ov[key].items():
                metas[r["rel"]].setdefault(f, (v, s))


def index(recs):
    chunks = []
    for r in recs:
        if r["role"] != "material":
            continue
        for ch in L.chunk_doc(r["doc"]["paras"]):
            ch["toks"] = L.toks(ch["text"])
            if ch["toks"]:
                ch["rel"], ch["sha256"], ch["class"] = r["rel"], r["sha256"], r["class"]
                chunks.append(ch)
    from math import log
    df = {}
    for ch in chunks:
        for t in ch["toks"]:
            df[t] = df.get(t, 0) + 1
    n = max(1, len(chunks))
    return chunks, {t: log((n + 1) / (d + 1)) + 1.0 for t, d in df.items()}, df


def answer(q, chunks, idf, df, chains, topk=3):
    qt, scored = L.toks(q["question"]), []
    for ch in chunks:
        hit = qt & ch["toks"]
        if hit:
            scored.append((len(hit) / len(qt), sum(idf.get(t, 1.0) for t in hit) / len(qt), ch))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    ev, used = [], set()
    for cov, sc, ch in scored:
        if len(ev) >= topk or cov < 0.34:
            break
        if ch["rel"] in used:
            continue
        quote = L.pick_quote(ch["text"], qt)
        if not quote or quote not in ch["text"]:
            continue
        used.add(ch["rel"])
        off = ch["text"].find(quote)
        ev.append({"source_id": "S%02d" % (len(ev) + 1), "rel": ch["rel"], "sha256": ch["sha256"], "kind": ch["class"],
                   "locator": "%s#%s" % (ch["rel"], ch["loc"]), "location": {"file": ch["rel"], "chunk": ch["loc"], "char_span": [off, off + len(quote)]},
                   "quote": quote, "coverage": round(cov, 3), "score": round(sc, 3), "quote_checked_in_chunk": True})
    best = scored[0][0] if scored else 0.0
    verdict = "no_question" if not qt else "supported" if best >= 0.6 else "partially_supported" if best >= 0.4 else "insufficient_evidence"
    conflicts = [{"type": "version_conflict", "question_id": q["qid"], "chain_id": chains[e["rel"]]["chain_id"], "cited_version": e["rel"],
                  "latest_version": chains[e["rel"]]["latest"], "confidence": "high", "detail": "not the latest version"}
                 for e in ev if e["rel"] in chains and chains[e["rel"]]["latest"] != e["rel"]]
    ans = " ; ".join('"%s" [%d]' % (e["quote"][:220], i + 1) for i, e in enumerate(ev[:2])) if ev and verdict in ("supported", "partially_supported") else None
    return {"qid": q["qid"], "question": q["question"], "verdict": verdict, "answer": ans, "answer_mode": "extractive", "evidence": ev, "best_coverage": round(best, 3), "missing_concepts": sorted(t for t in qt if df.get(t, 0) == 0)[:8], "conflicts": conflicts, "note": {"supported": "direct passage present; answer is extractive", "partially_supported": "partial coverage; see missing_concepts",
                     "insufficient_evidence": "no indexed passage covers >=34% of question terms", "no_question": "no question tokens"}[verdict]}


def build(args):
    t0, indir, out = time.time(), Path(args.input), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    res = {"case_id": None, "skill": {"name": NAME, "version": VERSION}, "status": "partial", "summary": "partial result written first",
           "errors": [], "degradations": [], "pending_human": [], "changes": [], "sources": [], "uncertainty": [], "failures": [],
           "skipped": [], "conflicts": [], "questions": [], "inventory": [], "duplicates": []}
    dwrite(out / "result.json", res)
    case, task, csrc, cerrs = load_case(indir)
    keys = echo_contract(case.get("output_contract") or case.get("outputContract") or case.get("required_outputs") or [], res)
    res["case_id"] = str(case.get("case_id") or case.get("caseId") or case.get("id") or "unknown")
    res["errors"] = cerrs
    res["input"] = {"dir": str(indir), "case": csrc, "task_chars": len(task)}
    dwrite(out / "result.json", res)
    recs, metas, skipped = L.scan(indir, max_files=args.max_files)
    apply_overrides(recs, metas, sidecar_overrides(recs))
    dups, chains = L.dup_and_versions(recs)
    chain_of = {d["rel"]: c["chain_id"] for c in chains for d in c["documents"]}
    mats = [r for r in recs if r["role"] == "material"]
    readable = [r for r in mats if r["doc"]["chars"] > 0]
    chunks, idf, df = index(recs)
    qa = [answer(q, chunks, idf, df, {d["rel"]: c for c in chains for d in c["documents"]}, args.top_k) for q in questions_of(case)]
    plan, copied = L.organize(recs, out, args.copy_budget_mb << 20)
    L.write_csv(out / "reorganize_plan.csv", ["source", "target", "action", "sha256", "size_bytes", "copy_sha256_verified"], plan)
    pend, degr, unc = res["pending_human"], res["degradations"], res["uncertainty"]
    for r in recs:
        for w in r["doc"]["warnings"]:
            res["failures"].append({"rel": r["rel"], "issue": w, "handled": True, "action": "excluded_from_index" if r["doc"]["chars"] == 0 else "degraded"})
            if w.startswith("no_text_extractor") or w in ("permission_denied", "pdf_no_text_layer", "pdf_text_too_short", "empty_text", "zero_byte"):
                pend.append({"item": r["rel"], "issue": w, "needed": "text or access", "impact": "not citable"})
    for c in chains:
        unc.append({"id": "U-" + c["chain_id"], "level": 2, "why": "no revision metadata stored", "statement": "order in %s inferred from version token + mtime" % c["chain_id"]})
        if c["confidence"] != "high":
            pend.append({"item": c["chain_id"], "issue": "chain_confidence_" + c["confidence"], "needed": "confirm authoritative file", "impact": "version order may be wrong"})
    for q in qa:
        if q["verdict"] != "supported":
            unc.append({"id": "U-" + q["qid"], "level": 3 if q["verdict"] == "insufficient_evidence" else 2, "statement": "%s: %s" % (q["qid"], q["verdict"]), "why": q["note"]})
        pend += [{"item": q["qid"], "issue": c["type"], "needed": "human adjudication", "impact": c["detail"]} for c in q["conflicts"]]
    if any(p["action"] == "deferred_size_budget" for p in plan):
        degr.append({"item": "organize_copy", "reason": "size budget exceeded", "effect": "remaining files only in reorganize_plan.csv"})
    degr += [{"item": "retrieval", "reason": "lexical scoring only, no embeddings", "effect": "paraphrases may fall back to insufficient evidence"},
             {"item": "ocr", "reason": "stdlib only, no OCR engine", "effect": "scanned pages never cited"}]
    if not qa:
        pend.append({"item": "questions", "issue": "no question in case.json", "needed": "question list", "impact": "Q&A not exercised"})
    cls, role, fields, vd = {}, {}, {}, {}
    for r in recs:
        cls[r["class"]] = cls.get(r["class"], 0) + 1
        role[r["role"]] = role.get(r["role"], 0) + 1
        for f, (v, src) in metas[r["rel"]].items():
            fe = fields.setdefault(f, {"files": 0, "sources": {}})
            fe["files"] += 1
            fe["sources"][src] = fe["sources"].get(src, 0) + 1
    for q in qa:
        vd[q["verdict"]] = vd.get(q["verdict"], 0) + 1
    depth = max([r["rel"].count("/") for r in recs] or [0]) + 1
    n_copied = sum(1 for p in plan if p["action"].startswith("copied"))
    status = "input_error" if not mats else "insufficient_evidence" if not readable else "partial" if any(e.get("stage") != "case_load" for e in res["errors"]) else "ok"
    inv = lambda r: {"rel": r["rel"], "class": r["class"], "size_bytes": r["size"], "sha256": r["sha256"], "readable": r["readable"],
                     "duplicate_of": r.get("duplicate_of"), "version_chain": chain_of.get(r["rel"]), "text_chars": r["doc"]["chars"],
                     "metadata": {k: {"value": v[0], "source": v[1]} for k, v in metas[r["rel"]].items()}}
    res.update({
        "status": status, "inventory": [inv(r) for r in recs],
        "summary": "%d files (%d materials, %d readable), %d dup groups, %d chains, %d questions %s" % (len(recs), len(mats), len(readable), len(dups), len(chains), len(qa), json.dumps(vd)),
        "library": {"root": str(indir), "file_count": len(recs), "material_count": len(mats), "total_bytes": sum(r["size"] for r in recs), "by_class": cls,
                    "by_role": role, "max_dir_depth": depth, "inventory_csv": "inventory.csv",
                    "dirs": sorted({r["rel"].rsplit("/", 1)[0] for r in recs if "/" in r["rel"]})[:50]},
        "metadata": {"fields": fields, "note": "each field records provenance: filename / stat / content / sidecar"},
        "duplicates": dups, "versions": {"chain_count": len(chains), "chains": chains, "path": "version_chain.json"},
        "questions": qa, "answers_path": "answers.md",
        "coverage_dimensions": {
            "file_types": {"count": len(cls), "classes": cls}, "metadata_fields": {"count": len(fields), "fields": sorted(fields)},
            "directory_depth": {"max_depth": depth, "root_files": sum(1 for r in recs if "/" not in r["rel"])},
            "duplicate_files": {"groups": len(dups), "redundant_files": sum(g["count"] - 1 for g in dups)},
            "version_differences": {"chains": len(chains), "stems": [c["stem"] for c in chains][:20]},
            "permission_and_source": {"readable": len(readable), "unreadable": len(mats) - len(readable),
                                      "permission_denied": sum(1 for r in recs if not r["readable"])}},
        "sources": [{"id": "F%03d" % i, "rel": r["rel"], "sha256": r["sha256"], "kind": r["class"]} for i, r in enumerate(recs, 1)],
        "changes": [{"op": "read_only", "target": str(indir), "detail": "read-only input; writes only to output"}] +
                   [{"op": "copy", "source": p["source"], "target": p["target"], "sha256": p["sha256"], "verified": p.get("copy_sha256_verified", False)} for p in plan if p["action"].startswith("copied")],
        "conflicts": [c for q in qa for c in q["conflicts"]],
        "skipped": skipped + [{"path": r["rel"], "reason": "system_junk"} for r in recs if r["role"] == "system_junk"]})
    L.write_inventory(out / "inventory.csv", recs, metas, chain_of)
    dwrite(out / "version_chain.json", {"generated": now(), "chain_count": len(chains), "chains": chains, "rule": "same stem, distinct sha256; token then mtime"})
    ans = ["# Grounded answers (extractive; verbatim quotes only)", "", "Status: `%s`; `[n]` maps to the evidence list." % status, ""]
    for q in qa:
        ans += ["## %s - %s" % (q["qid"], q["question"]), "", "- verdict: `%s` (coverage %.3f)" % (q["verdict"], q["best_coverage"])]
        ans += ["%s" % x for x in ["- answer: %s" % q["answer"] if q["answer"] else "",
                                   "- missing/absent: %s" % ", ".join(q["missing_concepts"]) if q["missing_concepts"] else ""] if x]
        ans += ["- [%d] `%s` sha256=%s.. locator=%s\n  > %s" % (i, e["rel"], (e["sha256"] or "")[:16], e["locator"], e["quote"]) for i, e in enumerate(q["evidence"], 1)]
        ans += ["- conflict: `%s` (%s) %s" % (c["type"], c["confidence"], c["detail"]) for c in q["conflicts"]] + ["- note: %s" % q["note"], ""]
    (out / "answers.md").write_text("\n".join(ans) + "\n", encoding="utf-8")
    ops = [("run_start", str(indir), VERSION), ("scan", str(indir), "files=%d" % len(recs)), ("hash_dedup", str(indir), "groups=%d" % len(dups)),
           ("version_chains", str(indir), "chains=%d" % len(chains)), ("qa", str(indir), "chunks=%d q=%d" % (len(chunks), len(qa))),
           ("organize", "library/", "copied=%d bytes=%d" % (n_copied, copied)), ("artifacts_written", str(out), "4 files")]
    with (out / "operations.log").open("w", encoding="utf-8") as f:
        for op, path, det in ops:
            f.write("%s\t%s\t%s\t%s\n" % (now(), op, path, det))
    res["operations"] = {"path": "operations.log", "count": len(ops), "counts": {"files": len(recs), "materials": len(mats), "hashed": sum(1 for r in recs if r["sha256"]),
                         "text_extracted": len(readable), "skipped": len(res["skipped"]), "failures": len(res["failures"]), "copied": n_copied}}
    echo_contract(keys, res)
    res["verification"] = L.audit(res, out)
    res["runtime"] = {"script": "scripts/main.py", "skill_version": VERSION, "finished": now(), "wall_seconds": round(time.time() - t0, 2),
                      "args": vars(args)}
    dwrite(out / "verify.json", res["verification"])
    dwrite(out / "result.json", res)
    print("status=%s files=%d mats=%d readable=%d dups=%d chains=%d q=%d -> %s" % (status, len(recs), len(mats), len(readable), len(dups), len(chains), len(qa), out / "result.json"))
    return res


def main(argv=None):
    p = argparse.ArgumentParser(prog="main.py", description="research-library-qa: research file library inventory, version chains and grounded Q&A with locators.",
                                epilog="main.py --mode verify --output /app/output")
    p.add_argument("--input", default="/input", help="input dir (default /input)")
    p.add_argument("--output", default="/app/output", help="output dir (default /app/output)")
    p.add_argument("--mode", choices=("build", "verify"), default="build", help="build | verify (re-hash, re-check quotes)")
    p.add_argument("--max-files", type=int, default=2000, help="max files")
    p.add_argument("--copy-budget-mb", type=int, default=32, help="max MB copied to library/")
    p.add_argument("--top-k", type=int, default=3, help="evidence chunks per question")
    p.add_argument("--version", action="version", version="%s %s" % (NAME, VERSION))
    a = p.parse_args(argv)
    if a.mode == "verify":
        try:
            out = Path(a.output)
            v = L.audit(json.loads((out / "result.json").read_text(encoding="utf-8")), out)
            dwrite(out / "verify.json", v)
            print(json.dumps({"overall": v["status"], "checks": {c["check"]: c["pass"] for c in v["checks"]}}, ensure_ascii=False))
        except Exception as e:
            print("verify failed: %s: %s" % (type(e).__name__, e))
        return 0
    try:
        build(a)
    except Exception as e:
        try:
            out = Path(a.output)
            out.mkdir(parents=True, exist_ok=True)
            fp = out / "result.json"
            try:
                res = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                res = {"case_id": None, "skill": {"name": NAME, "version": VERSION}}
            res.setdefault("errors", []).append({"stage": "fatal", "error": "%s:%s" % (type(e).__name__, str(e)[:200])})
            res["status"], res["runtime"] = "partial", {"script": "scripts/main.py", "skill_version": VERSION, "finished": now()}
            res["summary"] = "run aborted; kept deliverables"
            res.setdefault("pending_human", []).append({"item": "run", "issue": "fatal_error", "needed": "read errors[]", "impact": "incomplete"})
            dwrite(fp, res)
        except Exception:
            pass
        print("fatal: %s: %s" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
