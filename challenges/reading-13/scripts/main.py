#!/usr/bin/env python3
"""nanopub-forge: atomic assertions + verbatim evidence (stdlib only).
result.json: partial first, always finalized; exit code always 0."""
import argparse, json, re, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import (VERSION, canon_of, discover, extract, load_case, np_id_of,
                    pick_case_id, pick_contract, read_task, walk_first, write_json)

SCHEMA, T0 = "np-assertion/1", time.time()
WS = re.compile(r"\s+")
REL = [
 (r"\b(?:increas\w*|rais\w*|elevat\w*|enhanc\w*|upregulat\w*|higher|greater)\b", "increases", "quantitative"),
 (r"\b(?:decreas\w*|reduc\w*|lower|diminish\w*|downregulat\w*|impair\w*)\b", "decreases", "quantitative"),
 (r"\b(?:inhibit\w*|suppress\w*|block\w*|abolish\w*)\b", "inhibits", "mechanistic"),
 (r"\b(?:activat\w*|induc\w*|stimulat\w*|promot\w*|trigger\w*)\b", "activates", "mechanistic"),
 (r"\b(?:associated\s+with|associat\w+|correlat\w+|linked\s+to|related\s+to)\b", "associated_with", "associational"),
 (r"\b(?:binds?|bound|interact\w*\s+with|targets?)\b", "binds", "mechanistic"),
 (r"\b(?:encod\w*|express\w*|detect\w*|observ\w*|localiz\w*)\b", "expressed_in", "descriptive"),
 (r"\b(?:mediat\w*|regulat\w*|modulat\w*)\b", "mediates", "mechanistic"),
 (r"\b(?:caus\w*|leads?\s+to|led\s+to|results?\s+in|due\s+to)\b", "causes", "mechanistic"),
 (r"\b(?:differ\w*|compared?\s+with|versus|vs\.)\b", "differs_between", "comparative"),
 (r"(增加|升高|上调|增强|降低|减少|下调|抑制|阻断|激活|诱导|促进|相关|关联)", "increases", "quantitative"),
 (r"\b(?:is|are|was|were|remains?|becomes?)\b", "is_a", "descriptive"),
]
SURF = dict((r[1], r[1].replace("_", " ")) for r in REL)
SURF.update({"associated_with": "associates with", "expressed_in": "detected in", "is_a": "is",
             "other_relation": "relates to", "differs_between": "differs from"})
PASS = re.compile(r"^(?P<s>.{1,140}?)\s+(?:was|were|is|are|has been|have been)\s+(?:significantly\s+|markedly\s+)?"
                  r"(?P<v>inhibited|reduced|decreased|increased|activated|induced|mediated|suppressed|blocked|enhanced|attenuated)\s+by\s+(?P<o>.{2,90})$", re.I)
REL.append((r"\baffect\w*\b", "other_relation", "descriptive"))
CONDM = re.compile(r"\b(?:in|among|at|after|before|during|under|versus)\s+[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9 \-/.,µ%]{1,44}[A-Za-z0-9µ%]", re.I)
MAG = re.compile(r"(\d+(?:[.,]\d+)?)\s?(%|fold|mg|kg|µg|ng|mL|mM|µM|nM|h|days|weeks|months|years|°C)\b")
PSTAT = re.compile(r"\bp\s?[<>=≤≥]\s?0?\.\d+", re.I)
HEDGE = re.compile(r"\b(?:may|might|could|possibly|probably|likely|appears?|suggests?|suggested|consistent\s+with|potentially|seems?)\b", re.I)
SECOND = re.compile(r"\b(?:previously|earlier\s+stud\w+|reported\s+by|et\s+al\.|according\s+to|has\s+been\s+(?:shown|reported)|prior\s+work)\b", re.I)
NEG = re.compile(r"\b(?:not|no|never|neither|nor|without|fail(?:ed|s)?\s+to|unable\s+to|absence\s+of)\b", re.I)
PRON = re.compile(r"^(?:it|this|these|those|they|such|the\s+latter|the\s+former|该|此|这)\b", re.I)
ABBR = set("e.g i.e al fig figs no dr eq ref cf resp st vs min max".split())
CHART = dict.fromkeys("axis_x_type axis_x_scale axis_y_type axis_y_scale units legend_entries series_count error_bars scale_bar subpanel_labels".split())
CHART.update(status="not_read", reason="no vision")
FIGR = re.compile(r"\b(Fig(?:ure)?\.?\s*\d+[A-Za-z]?|Table\s*\d+[A-Za-z]?)\b[.:]?\s*([A-Z][^.]{10,200})")
CO = re.compile(r"(?<=[;；])\s*|(?<=,)\s+(?=(?:and|but|whereas|while|yet|which|thereby|thus|therefore|although|because)\b)", re.I)
UNSET = object()
ALIAS = {"caseid": "case_id", "id": "case_id", "assertion": "assertions",
         "claims": "assertions", "source": "sources", "sources": "sources", "counts": "counts",
         "sum": "status_reason"}

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def collapse(s):
    return WS.sub(" ", s or "").strip()

def semantic(k, R):
    f = ALIAS.get(re.sub(r"[^a-z0-9]", "", str(k).lower()))
    if f == "evidence":
        return [e for a in R["assertions"] for e in a["evidence"]]
    return R.get(f, UNSET) if f else UNSET

def ptrs(node, prefix=""):
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in ptrs(v, prefix + "/" + str(k))]
    if isinstance(node, list) and node and not all(isinstance(x, str) for x in node):
        return [p for i, v in enumerate(node) for p in ptrs(v, prefix + "/%d" % i)]
    return [prefix or "/"]

def echo(node, R, d=0):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            f = semantic(k, R)
            out[k] = echo(v, R, d + 1) if isinstance(v, (dict, list)) else (None if f is UNSET else f)
        return out
    if isinstance(node, list):
        return node if (node and all(isinstance(x, str) for x in node)) else [echo(x, R, d + 1) for x in node]
    return None

def sents(t):
    out, n, i, st = [], len(t), 0, 0
    while i < n:
        if t[i] not in ".!?。！？":
            i += 1
            continue
        k = i + 1
        while k < n and t[k] in "\"'”’)）] \t\n":
            k += 1
        w = re.findall(r"[A-Za-z.]+$", t[max(0, i - 14):i])
        word = w[0].lower().strip(".") if w else ""
        nxt = t[k] if k < n else ""
        if (t[i] in "。！？") or ((not nxt or nxt.isupper() or nxt in "([\"“" or ord(nxt) > 0x2E80)
                                 and len(word) != 1 and word not in ABBR):
            out.append((st, k))
            st = k
        i = k
    if st < n and t[st:].strip():
        out.append((st, n))
    return [(a, b) for a, b in out if len(collapse(t[a:b])) > 12]

def claus(s):
    out = []
    for p in CO.split(s):
        p = (p or "").strip(" ,;；")
        if p:
            out.append(p)
    return out or [s]

def tri(cl):
    c = collapse(cl).strip(" .;,")
    m = PASS.match(c)
    if m:
        hit = next((x for x in REL if re.search(x[0], m.group("v"), re.I)), (None, "other_relation", "descriptive"))
        return {"s": m.group("o"), "o": m.group("s"), "v": m.group("v"), "r": hit[1], "k": hit[2], "sw": True}
    for pat, canon, kind in REL:
        mm = re.search(pat, c, re.I)
        if not mm or mm.start() < 2:
            continue
        s, o = c[:mm.start()].strip(" ,;:[]()"), c[mm.end():].strip(" ,;:[]().")
        if s and o and len(s.split()) < 15 and len(o.split()) < 23:
            return {"s": s, "o": o, "v": mm.group(0), "r": canon, "k": kind, "sw": False}
    return None

def mk(sid, sidx, pno, para, sni, cl, q, tr, cond, a, b):
    s, o, rel = collapse(tr["s"]), collapse(tr["o"]), tr["r"] or "other_relation"
    pos = q.lower().find(tr["v"].lower())
    neg = bool(NEG.search(q[max(0, pos - 28):pos + len(tr["v"]) + 22] if pos >= 0 else q))
    basis = ["quote_bound", "relation_mapped" if rel != "other_relation" else "predicate_unmapped"]
    flags = []
    if tr["sw"]:
        basis.append("passive_swapped")
    if PRON.match(s):
        basis.append("pronoun_resolved")
        flags.append("pronoun_subject")
    if PRON.match(o):
        flags.append("pronoun_object")
    if SECOND.search(q):
        basis.append("secondhand_citation")
    if re.match(r"^(which|that|where|whose)\b", cl, re.I):
        basis.append("subject_inherited")
    hedged = bool(HEDGE.search(q))
    if hedged:
        basis.append("hedged_language")
    if len(s.split()) > 9 or len(o.split()) > 14:
        basis.append("span_heuristic")
    mag = MAG.search(o) or MAG.search(q)
    magd = {"value": mag.group(1).replace(",", "."), "unit": mag.group(2), "raw": mag.group(0)} if mag else None
    sc = (0.5 + (0.12 if rel != "other_relation" else 0) + (0.10 if PSTAT.search(q) else 0) - (0.12 if hedged else 0)
          - (0.08 if flags else 0) - (0.10 if "secondhand_citation" in basis else 0) - (0.07 if "span_heuristic" in basis else 0))
    sc = max(0.05, min(0.95, round(sc, 2)))
    weak = bool(flags or hedged or {"secondhand_citation", "subject_inherited", "span_heuristic"} & set(basis))
    tier = "low" if (rel == "other_relation" or sc < 0.5) else ("medium" if (sc < 0.72 or weak) else "high")
    rd = "undetermined" if ("pronoun_subject" in flags and sni == 1) else ("inferred" if weak else "directly_read")
    cond = [c for c in cond if tr["v"].lower() not in c.lower() and c.lower() not in o.lower()][:3]
    s = re.sub(r"\s+(?:was|were|is|are|been|be)$", "", s)
    o = re.sub(r"^(?:in|than)\s+", "", o, flags=re.I)
    o = re.sub(r"\s*\([^()]*$", "", o)
    txt = "%s %s %s" % (s, SURF[rel], o) + (" [negated]" if neg else "") + (" [" + "; ".join(cond) + "]" if cond else "")
    return {"assertion_id": None, "np_id": None, "kind": tr["k"], "assertion_text": txt[:300],
            "subject": {"text": s, "type": None}, "relation": rel,
            "object": {"text": o, "type": None}, "polarity": "negated" if neg else "affirm", "magnitude": magd,
            "condition": cond, "readability": rd,
            "evidence": [{"quote": q, "source_id": sid, "locator": "%s#p%d/s%d" % (sid, pno, sni), "match": "verbatim",
                          "location": {"page": pno, "paragraph": para, "sentence_index": sni, "char_start": a,
                                       "char_end": b, "locator_type": "page+para+sent+char",
                                       "json_pointer": "/sources/%d/pages/%d/text" % (sidx, pno - 1)}}],
            "confidence": {"score": sc, "basis": basis, "tier": tier}, "needs_review": tier != "high",
            "relation_raw": tr["v"], "review_reason": None if tier == "high" else (flags[0] if flags else tier),
            "source_ids": [sid]}

def build(S):
    A = S["assertions"]
    qc = {"checked": 0, "passed": 0, "failed": 0, "failures": []}
    for a in A:
        for e in a["evidence"]:
            q, pg = collapse(e["quote"]), (e["location"] or {}).get("page")
            pool = S["pages"].get(e["source_id"]) or []
            t = pool[pg - 1] if isinstance(pg, int) and 0 < pg <= len(pool) else None
            qc["checked"] += 1
            if t is not None and q and q in collapse(t):
                qc["passed"] += 1
            else:
                qc["failed"] += 1
                qc["failures"].append({"assertion_id": a["assertion_id"], "quote": q[:80]})
    S["qc"] = qc
    T = [a["confidence"]["tier"] for a in A]
    R = {"skill": {"name": "nanopub-forge", "version": VERSION, "schema": SCHEMA}, "case_id": S["case_id"],
         "status": S["status"], "status_reason": S["status_reason"], "task_understanding": S["tu"],
         "inputs": S["sources"], "sources": S["sources"], "assertions": A, "figures": S["fig"], "input_gaps": S["gaps"],
         "artifacts": ["result.json", "assertions.jsonl","extracted_text.json"],
         "uncertainty": S["unc"], "pending_human": S["pend"], "errors": S["err"],
         "degradations": S["deg"], "changes": S["chg"], "runtime": S["rt"],
         "verification": {"quote_checks": qc, "contract": {}},
         "counts": dict(sources_total=len(S["sources"]), pages_total=sum(x["pages"] for x in S["sources"]),
                        sentences_scanned=S["n_sent"], assertions_emitted=S["n_emit"],
                        assertions_after_dedup=len(A), duplicates_merged=S["n_dup"],
                        assertions_quote_bound=qc["passed"], assertions_quote_failed=qc["failed"],
                        quote_hit_rate=round(qc["passed"] / max(1, qc["checked"]), 4))}
    if S["tpl"] is None:
        R.update(output_contract_keys=[], output_contract_echo=None, contract_fields_present=[])
        return R
    e = echo(S["tpl"], R)
    S["cff"] = sorted(set(ptrs(e)))
    R.update(output_contract_echo=e, output_contract_keys=S["cff"], contract_fields_present=S["cff"])
    R["counts"]["contract_keys_total"] = len(S["cff"])
    R["verification"]["contract"] = {"keys": len(S["cff"]), "echo_ok": isinstance(e, (dict, list))}
    if isinstance(e, dict):
        for k, v in e.items():
            R.setdefault(k, v)
    return R

def side(S, out):
    (out / "assertions.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in S["assertions"]), encoding="utf-8")
    write_json(out / "extracted_text.json",
               {"sources": [{"source_id": s["source_id"], "path": s["path"], "extractor": s["extractor"],
                             "pages": [{"page": i + 1, "text": t} for i, t in enumerate(S["pages"].get(s["source_id"]) or [])]}
                            for s in S["sources"]]})

def flush(S, outdir):
    try:
        out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
        R = build(S)
        write_json(out / "result.json", R)
        side(S, out)
        return R
    except Exception:
        S["err"].append({"stage": "flush", "message": traceback.format_exc()[-300:], "type": "export"})

def new_state(a):
    return {"case_id": None, "status": "partial", "status_reason": "bootstrap partial",
            "tu": {"question": None, "assumed_contract": True}, "sources": [], "assertions": [],
            "pages": {}, "fig": [], "gaps": [], "unc": [], "pend": [], "err": [], "deg": [], "chg": [], "cff": [], "seen": {},
            "n_sent": 0, "n_clause": 0, "n_emit": 0, "n_dup": 0, "tpl": None,
            "rt": {"skill_version": VERSION, "schema": SCHEMA, "python": sys.version.split()[0], "started_utc": now(),
                   "finished_utc": None, "elapsed_s": None, "input_dir": None, "output_dir": None, "extractors": {},
                   "limits": {"max_assertions": a.max_assertions, "time_budget_s": a.time_budget}}}

def finalize(S, outdir):
    for i, a in enumerate(S["assertions"], 1):
        a["assertion_id"] = "A%04d" % i
        a["np_id"] = np_id_of(a)
    flush(S, outdir)
    n, qc = len(S["assertions"]), S["qc"]
    bad = S["err"] or qc["failed"] or any("no_text_layer" in f for s in S["sources"] for f in s["flags"])
    if S["status"] != "input_error":
        if n == 0:
            S["status"], S["status_reason"] = "insufficient_evidence", "no assertion from readable text"
        elif bad:
            S["status"] = "partial"
            S["status_reason"] = "%d assertions; %d quote failure(s); %d source flag(s)" % (
                n, qc["failed"], sum(len(s["flags"]) for s in S["sources"]))
        else:
            S["status"], S["status_reason"] = "ok", "%d assertions, all quotes verified verbatim" % n
    S["rt"].update(finished_utc=now(), elapsed_s=round(time.time() - T0, 1))
    S["chg"].append({"action": "finalize", "detail": "%d assertions" % n})
    flush(S, outdir)

def run(S, indir, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    S["rt"].update(input_dir=str(indir))
    flush(S, outdir)
    case, cpath, cerr = load_case(indir)
    if cerr:
        S["err"].append({"stage": "case_json", "message": cerr, "type": "json_decode"})
    S["case_id"] = pick_case_id(case, indir)
    S["tpl"] = tpl = pick_contract(case)
    S["tu"] = {"question": (walk_first(case, {"taskinstruction", "instruction", "question", "task"})
                            or read_task(indir))[:400] or None, "assumed_contract": tpl is None}
    if tpl is None:
        S["deg"].append({"capability": "contract", "cause": "none", "fallback": "defaults"})
    files, S["gaps"] = discover(indir, case)
    if not files:
        S.update(status="input_error", status_reason="no material: %s" % indir)
        S["pend"].append({"id": "P001", "target": "input", "reason": "no_material", "blocking": True,
                          "required_action": "add"})
        return
    for i, (path, _how) in enumerate(files[:24], 1):
        sid = "S%d" % i
        try:
            info = extract(path)
        except Exception:
            info = {"extractor": "none", "pages": [], "flags": ["extract_failed"], "meta": {}}
            S["err"].append({"stage": "extract", "message": traceback.format_exc()[-300:], "type": path.name})
        pages = info["pages"] or [""]
        txt = "".join(pages)
        S["pages"][sid] = pages
        m = info["meta"]
        S["sources"].append({"source_id": sid, "path": str(path), "kind": path.suffix.lower().lstrip(".") or "bin",
                             "bytes": path.stat().st_size, "extractor": info["extractor"], "pages": len(pages),
                             "text_chars": len(txt), "title": m.get("title"),
                             "authors": m.get("authors") or [], "year": m.get("year"), "doi": m.get("doi"),
                             "journal": None, "version": None, "flags": info["flags"]})
        S["rt"]["extractors"][sid] = info["extractor"]
        if "image_no_ocr" in info["flags"] or not txt.strip():
            S["pend"].append({"id": "P%03d" % (len(S["pend"]) + 1), "target": sid,
                              "reason": "image_no_ocr" if "image_no_ocr" in info["flags"] else "none",
                    "required_action": "vision"})
    for si, src in enumerate(S["sources"]):
        sid = src["source_id"]
        for pno, ptext in enumerate(S["pages"][sid], 1):
            for fm in list(FIGR.finditer(ptext))[:8]:
                S["fig"].append({"label": collapse(fm.group(1)), "page": pno, "status": "not_read",
                                 "caption_quote": collapse(fm.group(0))[:120],
                                 "locator": "%s#p%d/%s" % (sid, pno, collapse(fm.group(1))),
                                 "chart_meta": dict(CHART, pixel_readings=[])})
            for sni, (a, b) in enumerate(sents(ptext), 1):
                if len(S["assertions"]) >= S["rt"]["limits"]["max_assertions"] or time.time() - T0 > S["rt"]["limits"]["time_budget_s"]:
                    S["deg"].append({"capability": "scan", "cause": "budget", "fallback": "prefix"})
                    return
                q = collapse(ptext[a:b])
                S["n_sent"] += 1
                for cl in claus(q):
                    tr = tri(cl)
                    if not tr:
                        continue
                    S["n_clause"] += 1
                    rec = mk(sid, si, pno, 1 + ptext[:a].count("\n\n"), sni, cl, q, tr,
                             sorted({collapse(x) for x in CONDM.findall(cl)})[:4], a, b)
                    key = canon_of(rec)
                    if key in S["seen"]:
                        if len(S["assertions"][S["seen"][key]]["evidence"]) < 3:
                            S["assertions"][S["seen"][key]]["evidence"].append(rec["evidence"][0])
                        S["n_dup"] += 1
                    else:
                        S["seen"][key] = len(S["assertions"])
                        S["assertions"].append(rec)
                        S["n_emit"] += 1

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="nanopub-forge: atomic assertions + verbatim evidence + page/char locators")
    ap.add_argument("--input", default="/input", help="input dir, default /input")
    ap.add_argument("--output", default="/app/output", help="output dir, default /app/output")
    ap.add_argument("--max-assertions", type=int, default=400)
    ap.add_argument("--time-budget", type=float, default=760.0)
    a = ap.parse_args(argv)
    S = new_state(a)
    try:
        run(S, Path(a.input), Path(a.output))
    except Exception:
        S["err"].append({"stage": "run", "message": traceback.format_exc()[-700:], "type": "unhandled"})
        S["status"] = "partial"
    finally:
        try:
            finalize(S, Path(a.output))
        except Exception:
            try:
                write_json(Path(a.output) / "result.json", {"skill": {"name": "nanopub-forge", "version": VERSION},
                                                            "case_id": S.get("case_id"), "status": "partial"})
            except Exception:
                pass
    print(json.dumps({"status": S["status"], "assertions": len(S["assertions"])}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
