#!/usr/bin/env python3
"""main.py - reading-08: formula parsing & math reasoning (skill entry point).

Input : case.json + artifacts under --input (default /input).
Output: result.json, formulas.tex, symbol_table.csv, verification.md plus the v2 audit
        assets (golden_standard.json, diff_report.md, version_history.md, run.log,
        self_check.json).
A valid partial result.json is written before any parsing; exit code is always 0.

    python3 -B scripts/main.py --input /input --output /app/output
"""
import argparse
import csv
import json
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import formula_core as fc  # noqa: E402
try:                       # additive v2 module; its absence must not break the run
    import audit as ad
    LOG, VERSION, HAS_AUDIT = ad.Log, getattr(ad, "VERSION", "2.0.0"), True
except Exception:          # noqa: BLE001 - documented degradation
    ad, HAS_AUDIT, VERSION = None, False, "2.0.0"

    class LOG:             # minimal stand-in so logging calls stay valid
        def __init__(self, path, echo=False):
            self.path, self.n, self.echo, self.t0 = Path(path), 0, echo, time.time()

        def __call__(self, level, event, **kv):
            self.n += 1
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write("%s %s %s\n" % (level, event, kv))
            except OSError:
                pass

T0 = time.time()
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEX, TXT = {".tex", ".latex"}, {".txt", ".md", ".rst"}
XML = {".xml", ".mathml", ".nxml"}
GLOSS = {"T": "temperature", "p": "pressure", "V": "volume", "m": "mass", "t": "time",
         "x": "generic variable", "n": "amount", "R": "gas constant", "kB": "Boltzmann"}


def n(s):
    return fc.n(s)


def pl(sym):
    s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", sym or "")
    return re.sub(r"[{}^_$\\]", "", re.sub(r"\\[a-zA-Z]+", "", s)).strip()


def cl(cid, kind, read, stmt, sid, loc, q, cond="as provided", conf="high"):
    return {"claim_id": cid, "kind": kind, "readability": read, "statement": stmt,
            "source_id": sid, "location": loc, "quote": q, "condition": cond,
            "confidence": conf, "quote_verified": None,
            "evidence": {"quote": q, "location": loc}}


def odir(a, st):
    for c in ([Path(a)] if a else []) + [Path("/app/output"), Path.cwd() / "output"]:
        try:
            c.mkdir(parents=True, exist_ok=True)
            return c
        except OSError:
            continue
    st["errors"].append({"stage": "output", "message": "no writable output dir"})
    return Path.cwd()


def scan(root):
    try:
        return [p for p in sorted(root.rglob("*")) if p.is_file()]
    except OSError:
        return []


def file_text(M):
    """Plain text of every input file (markup stripped): the quote-verification reference."""
    out = []
    for rec in M.get("sources") or []:
        p = (M.get("paths") or {}).get(rec.get("source_id"))
        if not p:
            continue
        try:
            t = fc.read_text(Path(p))
        except OSError:
            continue
        if (rec.get("type") or "").lower() in ("xml", "mathml", "nxml", "html", "htm"):
            t = re.sub(r"<[^>]{0,4000}>", " ", t)
        out.append(t)
    return out


def load_case(inp, st):
    cands = [inp / x for x in ("case.json", "case_input.json", "input.json")
             if (inp / x).is_file()]
    cands += [p for p in sorted(inp.rglob("case*.json")) if p not in cands]
    for c in cands:
        try:
            obj = json.loads(c.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as e:
            st["errors"].append({"stage": "case_parse", "path": str(c), "message": str(e)[:200]})
            continue
        if not isinstance(obj, dict):
            st["errors"].append({"stage": "case_parse", "path": str(c), "message": "not object"})
            continue
        return obj, c
    return None, None


def add_blocks(M, name, text, sid):
    for i, para in enumerate(re.split(r"\n\s*\n|\f", text)):
        if len(n(para)) >= 8:
            M["blocks"].append({"path": "%s#p%d" % (name, i + 1), "text": n(para),
                                "source_id": sid})


def xml_material(p, sid, M, st, rec):
    txt = fc.read_text(p)
    try:
        root, note = fc.parse_xml(txt)
    except Exception as e:  # noqa: BLE001 - documented fallback
        ann = re.findall(r'<annotation[^>]*encoding="application/x-tex"[^>]*>(.*?)</annotation>',
                         txt, re.S | re.I)
        st["degradations"].append({"item": p.name, "stage": "xml_parse",
                                   "action": "regex fallback on TeX annotations (%s)" % type(e).__name__,
                                   "impact": "structure counts unavailable"})
        for k, a in enumerate(ann):
            M["formulas"].append({
                "latex": fc.tidy_latex(re.sub(r"<[^>]+>", "", a)), "latex_source": "regex_annotation",
                "parse_confidence": "low", "node": None, "fid": "", "eq": "",
                "path": "%s#annotation[%d]" % (p.name, k + 1), "raw": n(a)[:400],
                "source_id": sid, "flags": ["xml_unparsed"], "file": p.name})
        if not ann:
            st["uncertainties"].append({"id": "U-xml-%s" % sid, "type": "parse_failure",
                                        "object": p.name, "description": "XML unparsable, no annotation",
                                        "impact": "no formula recovered", "quote": txt[:160]})
        rec["notes"] = "xml_unparsed"
        return
    bs, fl = fc.iter_blocks(root), fc.collect_formulas(root)
    for b in bs:
        b["source_id"], b["file"] = sid, p.name
    for k, f in enumerate(fl):
        f["source_id"], f["file"] = (f["fid"] or "%s#%d" % (sid, k + 1)), p.name
    M["blocks"] += bs
    M["formulas"] += fl
    rec["notes"] = "%s; blocks=%d; math_nodes=%d" % (note, len(bs), len(fl))
    rec["role"] = "formula_source" if fl else "narrative_source"


def materials(files, st):
    M = {"formulas": [], "blocks": [], "sources": [], "tables": [], "paths": {}}
    for p in files:
        try:
            head = p.read_bytes()[:8]
        except OSError:
            head = b""
        suf, sid = p.suffix.lower(), (p.stem or p.name)
        rec = {"source_id": sid, "file": p.name, "type": suf.lstrip(".") or "bin"}
        if suf in XML or head[:5] == b"<?xml":
            xml_material(p, sid, M, st, rec)
        elif suf in TEX:
            txt = fc.read_text(p)
            for k, m in enumerate(re.finditer(r"\\begin\{(equation\*?|align\*?)\}(.*?)"
                                              r"\\end\{\1\}", txt, re.S)):
                M["formulas"].append({"latex": fc.tidy_latex(m.group(2)), "latex_source": "source_tex",
                                      "parse_confidence": "high", "node": None, "fid": "", "eq": "",
                                      "path": "%s#eq%d" % (p.name, k + 1), "raw": n(m.group(2))[:400],
                                      "source_id": sid, "flags": [], "file": p.name})
            rec["role"] = "formula_source"
        elif suf in TXT:
            add_blocks(M, p.name, fc.read_text(p), sid)
            rec["role"] = "narrative_source"
        else:
            st["degradations"].append({"item": p.name, "stage": "unparsed_material",
                                       "action": "kept, not interpreted"})
            if suf == ".pdf" or head[:5] == b"%PDF-":
                st["result"]["missing_objects"].append({"object": "text of %s" % p.name,
                                                        "reason": "no text layer decoded",
                                                        "needed": "vector PDF or MathML"})
            elif suf in IMG:
                st["result"]["missing_objects"].append({"object": "formula content in %s" % p.name,
                                                        "reason": "raster image",
                                                        "needed": "vector or MathML source"})
        M["sources"].append(rec)
        M["paths"][sid] = str(p)
    return M


def analyse(st, M):
    R, bs, U, C = st["result"], M["blocks"], st["uncertainties"], []
    D, V = fc.mine_defs(bs)
    corpus = n(" ".join(b["text"] for b in bs))
    P, var, checks = [], {}, []
    for f in M["formulas"][:40]:
        node, fl = f.get("node"), list(f.get("flags") or [])
        tex, src = f.get("latex"), f.get("latex_source", "given")
        cf = f.get("parse_confidence", "medium")
        if f.get("tex"):
            tex, src, cf = f["tex"], "mml_annotation", "high"
        if not tex and node is not None:
            tex, src, cf = fc.tidy_latex(fc.to_latex(node, fl)), "structural_mapping", "high"
        if not tex:
            continue
        stc = fc.structure_of(node) if node is not None else {}
        sm = fc.extract_symbols(node) if node is not None else []
        iss, fid = fc.lcheck(tex), "F%d" % (len(P) + 1)
        st.setdefault("_nodes", {})[fid] = node
        st.setdefault("_ffile", {})[fid] = f.get("file") or ""
        st.setdefault("_idfile", {})[f.get("source_id") or fid] = f.get("file") or ""
        P.append(({"formula_id": fid, "source_id": f.get("source_id") or fid,
                   "eq_number": f.get("eq") or None, "mathml_raw_path": f.get("path"),
                   "latex": tex, "latex_source": src, "parse_confidence": cf, "structure": stc,
                   "flags": sorted(set(fl + iss)),
                   "symbols": [x["symbol"] for x in sm if x["role"] == "variable"],
                   "status": "ok" if not iss else "needs_review"}, node, sm, tex))
        # quote must be literally in the material: label, else TeX body slice, else container id.
        lab = f.get("eq") or f.get("fid") or ""
        if not lab and src in ("source_tex", "regex_annotation") and f.get("raw"):
            lab = n(f["raw"])[:120]
        lab = lab or f.get("source_id") or ""
        st.setdefault("_qref", {})[fid] = lab
        c0 = cl("C-%s" % fid, "reported", "directly_read",
                "Formula %s from %s" % (fid, f.get("path")), f.get("source_id"), f.get("path"),
                lab, "as provided", cf)
        c0["evidence"]["mathml_excerpt"] = (f.get("raw") or tex)[:400]
        C.append(c0)
        for x in sm:
            if x["role"] == "variable":
                e = var.setdefault(x["symbol"], {"symbol": x["symbol"], "latex": x["latex"],
                                                 "plain": pl(x["symbol"]), "formula_ids": [],
                                                 "value_range": None})
                if fid not in e["formula_ids"]:
                    e["formula_ids"].append(fid)
    for e in var.values():
        p = e["plain"]
        d, v = D.get(p) or D.get(p.rstrip("0123456789")), V.get(p)
        e["value"] = v
        if d:
            e.update(definition=d["definition"], unit=d["unit"], definition_source="paper_defined",
                     locator=d["locator"], quote=d["quote"], source_id=d["source_id"], confidence="high")
            C.append(cl("S-%s" % p, "reported", "directly_read", "%s: %s" % (p, d["definition"][:150]),
                        d["source_id"], d["locator"], d["quote"], "definition as printed", "high"))
        elif corpus and re.search(r"(?<![\w])%s(?![\w])" % re.escape(p), corpus):
            e.update(definition=None, unit="", definition_source="context_inferred", locator=None,
                     quote="", source_id=None, confidence="low")
            U.append({"id": "U-def-%s" % p, "type": "definition_inferred", "object": e["symbol"],
                      "description": "used without explicit definition", "impact": "definition null",
                      "quote": ""})
        else:
            h = GLOSS.get(p.rstrip("0123456789"))
            e.update(definition=None, unit="", definition_source="common_knowledge", locator=None,
                     quote="", source_id=None, confidence="low", common_knowledge_hint=h, inferred=True)
            U.append({"id": "U-gloss-%s" % p, "type": "definition_absent", "object": e["symbol"],
                      "description": "not defined in material" + ("; hint: %s" % h if h else ""),
                      "impact": "common_knowledge/inferred", "quote": ""})
        if e["definition_source"] != "paper_defined":
            C.append(cl("S-%s" % p, "inferred", "inferred", "%s is used but not defined explicitly" % p,
                        None, None, "", "context only", "low"))
    steps, rows = fc.mine_steps(bs)
    for d in steps:
        C.append(cl("C-%s" % d["step_id"], "inferred", "directly_read",
                    "Text reports a %s step: %s" % (d["rule"], d["statement"][:180]), d["source_id"],
                    d["locator"], d["quote"], "sentence level", "medium"))
    st["_defs"], st["_vals"] = D, V
    for rec, node, sm, tex in P:
        vals, miss = {}, []
        for x in sm:
            if x["role"] != "variable":
                continue
            v = (var.get(x["symbol"]) or {}).get("value")
            if v:
                vals[x["symbol"]] = v["value"]
            elif pl(x["symbol"]) not in miss:
                miss.append(pl(x["symbol"]))
        c = {"formula_id": rec["formula_id"], "substituted": dict(vals), "computed": None,
             "is_example": False, "status": "not_computable", "missing_symbols": miss[:12],
             "unit_check": "not_evaluated", "order_of_magnitude_check": "not_evaluated"}
        if node is not None and not miss:
            val = fc.evaluate(node, vals)[0]
            if val is not None:
                c.update(status="computed", computed=val, unit_check="units from source definitions",
                         order_of_magnitude_check=("log10|v|=%.3f" % math.log10(abs(val))) if val else "n/a")
        elif node is not None and not vals:
            pv = {k: 1.0 for x in sm if x["role"] == "variable" for k in (x["symbol"], pl(x["symbol"]))}
            val = fc.evaluate(node, pv)[0]
            if val is not None:
                c.update(status="example_only", is_example=True, computed=val, substituted=pv,
                         unit_check="probe 1.0, not paper data", order_of_magnitude_check="example only",
                         note="\u793a\u4f8b\u4ee3\u5165\uff0c\u975e\u8bba\u6587\u590d\u73b0")
        checks.append(c)
        cn = cl("C-N-%s" % rec["formula_id"], "inferred" if c["is_example"] else "reported",
                "inferred" if c["is_example"] else "directly_read",
                "Numeric check %s: %s" % (rec["formula_id"], c["status"]), rec["source_id"],
                rec["mathml_raw_path"], (st.get("_qref") or {}).get(rec["formula_id"])
                or rec.get("eq_number") or rec["formula_id"],
                "flagged example" if c["is_example"] else "reported values", "medium")
        cn["evidence"]["expression"] = tex[:300]
        C.append(cn)
    if any(c["is_example"] for c in checks):
        U.append({"id": "U-example", "type": "synthetic_example", "object": "numeric_checks",
                  "description": "no reported values; 1.0 probe only shows evaluability",
                  "impact": "not a paper result", "quote": ""})
    vs = sorted(var.values(), key=lambda x: x["symbol"])
    cnt = {}
    for x in vs:
        cnt[x["definition_source"]] = cnt.get(x["definition_source"], 0) + 1
    R.update({"formulas": [p[0] for p in P], "variables": vs, "derivations": steps,
              "numeric_checks": checks, "indicator_checks": rows,
              "missing_objects": R.get("missing_objects", []),
              "coverage": {"formulas_total": len(P),
                           "formulas_ok": sum(p[0]["status"] == "ok" for p in P),
                           "variables_total": len(vs), "by_source": cnt,
                           "derivations_total": len(steps),
                           "numeric_computed": sum(c["status"] == "computed" for c in checks),
                           "numeric_example_only": sum(c["is_example"] for c in checks),
                           "claims_total": len(C), "uncertainties_total": len(U),
                           "symbol_coverage": round(sum(bool(x["definition"]) or x["definition_source"]
                                                        == "context_inferred"
                                                        for x in vs) / len(vs), 3) if vs else 0.0},
              "method_notes": "TeX annotation verbatim when present else structural MathML "
                              "mapping; definitions only from explicit sentences."})
    return C, U


def w_tex(p, fs):
    L = ["% restored from the provided material", "\\documentclass[11pt]{article}",
         "\\usepackage{amsmath,amssymb}", "\\begin{document}"]
    for f in fs:
        L.append("%% source_id: %s | eq: %s | from: %s | confidence: %s"
                 % (f["source_id"], f["eq_number"], f["latex_source"], f["parse_confidence"]))
        L += ["\\begin{equation*}", f["latex"] or "% (no latex restored)", "\\end{equation*}"]
    p.write_text("\n".join(L + ["\\end{document}", ""]), encoding="utf-8")


def w_csv(p, vs):
    cols = ["symbol", "latex", "plain", "definition", "unit", "value_range", "definition_source",
            "locator", "quote", "formula_ids", "confidence", "inferred"]
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for v in vs:
            w.writerow({**v, "formula_ids": ";".join(v.get("formula_ids") or [])})


def w_md(p, st):
    cov = st["result"].get("coverage") or {}
    lines = ["# Verification notes (auto-generated, not a prepared answer)", "",
             "- case_id: %s" % st.get("case_id"),
             "- status: %s" % st.get("status"),
             "- contract_fields_missing: %s" % len(st.get("contract_fields_missing", [])),
             "- files_scanned: %s" % (st["result"].get("input_summary") or {}).get("files_scanned"),
             "- formulas: total=%s ok=%s" % (cov.get("formulas_total"), cov.get("formulas_ok")),
             "- variables: total=%s by_source=%s" % (cov.get("variables_total"),
                                                     cov.get("by_source")),
             "- derivations: %s" % cov.get("derivations_total"),
             "- numeric_checks: computed=%s example_only=%s" % (cov.get("numeric_computed"),
                                                              cov.get("numeric_example_only")),
             "- symbol_coverage: %s" % cov.get("symbol_coverage"),
             "- claims: total=%s quote_verified=%s" % (cov.get("claims_total"),
                                                       cov.get("claims_quote_verified")),
             "- uncertainties: %s" % cov.get("uncertainties_total"),
             "- errors: %s, degradations: %s, pending_human: %s" % (
                 len(st.get("errors", [])), len(st.get("degradations", [])),
                 len(st.get("pending_human", []))),
             "", "Full machine-readable record: result.json."]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(a, st, out):
    lg = st.get("log") or LOG(out / "run.log")
    st["log"] = lg
    st["runtime"]["input_dir"] = str(a.input)
    lg("INFO", "stage", name="input_discovery", input=str(a.input))
    case = load_case(Path(a.input), st)[0]
    st["case_loaded"] = bool(case)
    if case:
        st["case_id"] = case.get("case_id") or case.get("id") or None
        con = case.get("output_contract") or case.get("output_spec") or case.get("contract") or {}
        st["contract"] = con if isinstance(con, dict) else {}
        lg("INFO", "case_loaded", case_id=st["case_id"], contract_fields=len(st["contract"]))
    else:
        st["errors"].append({"stage": "case_load", "message": "no case.json; artifacts only"})
        lg("WARN", "case_missing")
    files = scan(Path(a.input))
    M = materials(files, st)
    st["sources"] = M["sources"]
    st["_paths"] = M["paths"]
    lg("INFO", "material_scan", files=len(files), formulas=len(M["formulas"]), blocks=len(M["blocks"]),
       degradations=len(st["degradations"]))
    st["result"]["input_summary"] = {"files_scanned": len(files),
                                     "math_nodes_found": len(M["formulas"]),
                                     "text_blocks": len(M["blocks"]),
                                     "tabular_material": len(M["tables"])}
    st["claims"], st["uncertainties"] = analyse(st, M)
    lg("INFO", "analysis", claims=len(st["claims"]), variables=len(st["result"]["variables"]),
       steps=len(st["result"]["derivations"]))
    corpus = n(" ".join([b["text"] for b in M["blocks"]] + [f.get("raw") or "" for f in M["formulas"]]
                        + [x["latex"] for x in st["result"]["formulas"]] + file_text(M)))
    bad = 0
    for c in st["claims"]:
        q = n(c.get("quote") or "")[:120]
        c["quote_verified"] = None if not q else (q in corpus)
        if q and not c["quote_verified"]:
            bad += 1
            c["readability"] = "undetermined"
    cov, fs = st["result"]["coverage"], st["result"]["formulas"]
    cov["claims_quote_verified"] = sum(1 for c in st["claims"] if c.get("quote_verified"))
    if bad:
        st["pending_human"].append({"item": "quote_check", "why": "%d quotes not verbatim" % bad})
    if not fs:
        st["status"] = "input_error" if not files else "insufficient_evidence"
        if files:
            st["result"]["missing_objects"].append({"object": "formula representation",
                                                    "reason": "no MathML/TeX/text formula found",
                                                    "needed": "MathML, TeX or text formula"})
            st["pending_human"].append({"item": "formula_source_missing",
                                        "why": "no machine-readable formula object",
                                        "action": "supply publisher XML/TeX or read the page"})
    elif (all(f["status"] == "ok" for f in fs) and cov["symbol_coverage"] == 1.0
          and cov["derivations_total"] and cov["numeric_computed"]):
        st["status"] = "ok"
    else:
        st["status"] = "partial"
        st["result"]["status_reason"] = {k: cov[k] for k in ("symbol_coverage",
                                                             "numeric_computed")}
    w_tex(out / "formulas.tex", fs)
    w_csv(out / "symbol_table.csv", st["result"]["variables"])
    w_md(out / "verification.md", st)
    st["changes"].append({"item": "deliverables",
                          "action": "wrote formulas.tex, symbol_table.csv, verification.md",
                          "reason": "reviewable companions to result.json"})
    lg("INFO", "companions_written", status=st["status"],
       formulas=len(fs), variables=len(st["result"]["variables"]))
    audit(st, out, lg, M, Path(a.input))
    lg("INFO", "status_final", status=st["status"])


def audit(st, out, lg, M, indir):
    """v2 stage: golden standard, diff report, version history, self check."""
    if not HAS_AUDIT or st.get("no_audit"):
        for k in ("golden", "diff", "vhistory", "selfcheck"):
            st[k] = {"status": "skipped", "reason": "audit module unavailable or --no-audit"}
        lg("WARN", "audit_skipped", has_module=HAS_AUDIT)
        return
    st["contract_values"] = contract_values(st)
    for stage, fn in (("golden_standard", lambda: ad.write_assets(st, out, lg, M)),
                      ("self_check", lambda: ad.write_self_check(st, out, Path(__file__).resolve(),
                                                                 indir, lg))):
        lg("INFO", "stage", name=stage)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - never fatal
            st["errors"].append({"stage": "audit_" + stage, "message": str(e)[:200]})
            lg("ERROR", "audit_" + stage, error=str(e)[:200])
    st["changes"].append({"item": "audit_assets", "action": "golden_standard.json, diff_report.md, "
                          "version_history.md, self_check.json",
                          "reason": "make the delivery checkable against a material-derived golden standard"})


def contract_values(st):
    """Semantic values for output_contract keys that have no direct result mirror."""
    cov, cl = st["result"].get("coverage") or {}, st.get("claims") or []
    return {"evidence": [{"claim_id": c.get("claim_id"), "source_id": c.get("source_id"),
                          "locator": c.get("location"), "quote": (c.get("quote") or "")[:240],
                          "quote_verified": c.get("quote_verified")} for c in cl][:200],
            "evidence_map": {c.get("claim_id"): c.get("location") for c in cl},
            "summary": cov,
            "notes": ("reading-08 v%s: %s formulas, %s symbols, %s steps, %s numeric checks; status=%s"
                      % (VERSION, cov.get("formulas_total"), cov.get("variables_total"),
                         cov.get("derivations_total"), cov.get("numeric_computed"), st.get("status")))}


def new_state():
    return {"case_id": None, "case_loaded": False, "status": "partial", "contract": {}, "task": {},
            "sources": [], "claims": [], "uncertainties": [], "pending_human": [], "errors": [],
            "degradations": [], "changes": [], "contract_values": {},
            "golden": None, "diff": None, "vhistory": None, "selfcheck": None,
            "result": {"formulas": [], "variables": [], "derivations": [], "numeric_checks": [],
                       "indicator_checks": [], "missing_objects": [], "input_summary": {}},
            "runtime": {"skill": "reading-08-formula-structure", "version": VERSION,
                        "python": sys.version.split()[0]}}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="reading-08: formulas -> LaTeX, symbol table, derivations, numeric checks, "
                    "plus a v2 golden-standard/diff/self-check audit of the delivery.",
        epilog="Writes result.json, formulas.tex, symbol_table.csv, verification.md, "
               "golden_standard.json, diff_report.md, version_history.md, run.log, "
               "self_check.json; always exits 0.")
    ap.add_argument("--input", default="/input", help="input dir (case.json + artifacts)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output)")
    ap.add_argument("--no-audit", dest="audit", action="store_false",
                    help="optional: skip the v2 audit assets (result.json stays valid)")
    a = ap.parse_args(argv)
    st = new_state()
    st["no_audit"] = not a.audit
    out = odir(a.output, st)
    lg = LOG(out / "run.log")
    st["log"] = lg
    lg("INFO", "run_start", argv=list(argv) if argv else sys.argv[1:],
       python=sys.version.split()[0], output=str(out), audit=a.audit)
    try:
        (out / "result.json").write_text(
            json.dumps(fc.compose(st), ensure_ascii=False, indent=2), encoding="utf-8")
        lg("INFO", "partial_result_written", path=str(out / "result.json"),
           bytes=(out / "result.json").stat().st_size)
    except OSError as e:
        lg("ERROR", "partial_result_failed", error=str(e)[:160])
    try:
        run(a, st, out)
    except Exception as e:  # noqa: BLE001 - always finalise with a valid file
        st["errors"].append({"stage": "fatal", "message": ("%s: %s" % (type(e).__name__, e))[:300]})
        st["status"] = "partial" if st["result"].get("formulas") else "input_error"
        lg("ERROR", "fatal", error=str(e)[:200], status=st["status"])
    finally:
        st["runtime"].update({"elapsed_s": round(time.time() - T0, 2), "output_dir": str(out),
                              "version": VERSION, "stages": lg.n})
        for d in st["degradations"]:
            lg("WARN", "degradation", item=d.get("item"), stage=d.get("stage"), action=d.get("action"))
        for e in st["errors"]:
            lg("ERROR", "exception", stage=e.get("stage"), message=e.get("message"))
        try:
            (out / "result.json").write_text(json.dumps(fc.compose(st), ensure_ascii=False, indent=2),
                                             encoding="utf-8")
            lg("INFO", "finalize", status=st["status"], elapsed_s=st["runtime"]["elapsed_s"],
               bytes=(out / "result.json").stat().st_size, exit_code=0)
        except OSError:
            sys.stdout.write("ERROR: cannot write result.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
