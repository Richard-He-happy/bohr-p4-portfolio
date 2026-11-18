#!/usr/bin/env python3
"""latex_doctor.py - LaTeX writing & compilation driver (skill: latex-writing-compile).
Stage, diagnose, repair, multi-pass build, deliverable + result.json, audit. Exits 0 always."""
import argparse, difflib, json, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try: import latex_lint as L
except Exception: L = None
T0 = time.time(); ME = 30
CE = {".tex", ".ltx", ".bib", ".cls", ".sty", ".bst", ".clo", ".def", ".cfg", ".eps", ".pdf", ".png",
      ".jpg", ".jpeg", ".bbl"}
TE = {".tex", ".ltx", ".bib", ".md", ".txt", ".csv", ".json", ".yml", ".yaml", ".cls", ".sty"}
EC = (L.RJ.get("error_classes", []) if L else [])

def rd(p):
    try: b = Path(p).read_bytes()
    except Exception: return ""
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
def wr(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8", newline="\n"); return str(p)
def jd(p, o): return wr(p, json.dumps(o, ensure_ascii=False, indent=1))
def wk(r, cap=600):
    o, r = [], Path(r)
    if not r.exists(): return o
    for p in sorted(r.rglob("*")):
        if len(o) >= cap: break
        try:
            if p.is_file() and not p.name.startswith(".") and p.stat().st_size <= 20e6: o.append(p)
        except Exception: pass
    return o
def rl(p, b):
    try: return str(Path(p).resolve().relative_to(Path(b).resolve())).replace(os.sep, "/")
    except Exception: return str(p)
def which(*n): return next((x for x in (shutil.which(y) for y in n) if x), None)
def pages(p):
    try: b = Path(p).read_bytes()
    except Exception: return 0
    n = len(re.findall(rb"/Type\s*/Page[^s]", b))
    if not n and which("pdfinfo"):
        m = re.search(r"Pages:\s+(\d+)", run([which("pdfinfo"), str(p)], ".", 30)["tail"])
        n = int(m.group(1)) if m else 0
    return n
def run(cmd, cwd, to, env=None):
    t = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=to, env=env)
        return {"cmd": " ".join(cmd), "exit": r.returncode, "sec": round(time.time() - t, 2),
                "tail": r.stdout.decode("utf-8", "replace")[-1200:]}
    except Exception as e:
        return {"cmd": " ".join(cmd), "sec": round(time.time() - t, 2),
                "exit": -9 if isinstance(e, subprocess.TimeoutExpired) else -1, "tail": str(e)[:120]}

def pick(cands, default):
    for c in cands:
        try:
            p = Path(c).expanduser(); p.mkdir(parents=True, exist_ok=True)
            if os.access(str(p), os.W_OK): return p.resolve()
        except Exception: pass
    return default
def pick(cs, dflt):
    for c in cs:
        try:
            p = Path(c).expanduser(); p.mkdir(parents=True, exist_ok=True)
            if os.access(str(p), os.W_OK): return p.resolve()
        except Exception: pass
    return dflt
def dirs(a):
    ind = next((Path(c).expanduser().resolve() for c in (a.input, "/input", "input")
                if c and Path(c).expanduser().is_dir()), Path("/input"))
    out = pick((a.out, os.environ.get("LATEX_DOCTOR_OUT"), "/app/output", "output"), Path.cwd() / "output")
    return ind, out, pick((a.work, "/app/work", str(out / "work")), out)

def load_case(ind, E):
    p = ind / "case.json"
    if not p.exists():
        c = sorted([x for x in wk(ind) if x.suffix.lower() == ".json"], key=lambda x: (len(x.parts), x.stat().st_size))
        p = c[0] if c else None
    if not p: E.append({"code": "case_missing", "message": "no case.json", "path": str(ind)}); return {}
    try:
        o = json.loads(rd(p))
        return o if isinstance(o, dict) else {}
    except Exception as e:
        E.append({"code": "case_json_invalid", "message": "%s: %s" % (type(e).__name__, e), "path": str(p)}); return {}

def cpaths(ind):
    f = set(wk(ind))
    return f

def clsf(m):
    for p, c, f in EC:
        if re.search(p, m, re.I): return c, f
    return "E99_UNKNOWN", "read the lines after the error in the .log"
def plog(log):
    A, err, seen = log.split("\n"), [], set()
    for i, l in enumerate(A):
        m = re.match(r"^(.+?\.(?:tex|sty|cls|bbl|aux|def|cfg)):(\d+):\s*(.*)$", l)
        if m: msg, fl, nl = m.group(3), m.group(1), int(m.group(2))
        elif l.startswith("! "):
            msg, fl, nl = l[2:].strip(), None, None
            for k in A[i + 1:i + 9]:
                m2 = re.match(r"^l\.(\d+)", k.strip())
                if m2: nl = int(m2.group(1)); break
        else: continue
        if (fl, nl) in seen: continue
        seen.add((fl, nl))
        c, f = clsf(msg)
        err.append({"file": fl, "line": nl, "message": msg.strip()[:300], "class": c, "fix": f})
    return err, [{"kind": "overfull_hbox", "detail": x}
                 for x in re.findall(r"Overfull \\hbox \\([\\d.]+)pt too wide", log)[:20]]

def engine_for(t, f):
    if f: return f
    pk = " ".join(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", t))
    uni = bool(L and L.CJK.search(t)) or "ctex" in t or "fontspec" in pk
    return next((e for e in ((["xelatex"] if uni else []) + ["pdflatex", "lualatex", "xelatex"]) if which(e)), "")
def build(bd, mn, eng, to, DG):
    env = dict(os.environ, HOME=str(bd), TEXMFVAR=str(bd / "texmf-var"), TEXMFCONFIG=str(bd / "texmf-config"),
               TEXMFHOME=str(bd / "texmf-home"), SOURCE_DATE_EPOCH="0", FORCE_SOURCE_DATE="1")
    base = [eng, "-interaction=nonstopmode", "-file-line-error", mn]; ps = [run(base, bd, to, env)]
    txt = "\n".join(rd(x) for x in bd.glob("*.tex"))
    if "\\bibliography" in txt or "\\addbibresource" in txt or "biblatex" in txt:
        tool = which("biber") if "biblatex" in txt else which("bibtex")
        if tool: ps.append(run([tool, Path(mn).stem], bd, to, env))
    ps += [run(base, bd, to, env), run(base, bd, to, env)]
    log = rd(bd / (Path(mn).stem + ".log")); err, wrn = plog(log) if log else ([], [])
    if not log: DG.append({"code": "no_log", "message": "no .log produced", "detail": ps[0]["tail"][-300:]})
    pdf = bd / (Path(mn).stem + ".pdf")
    return {"engine": Path(eng).name, "passes": ps, "log_present": bool(log), "errors": err[:ME],
            "warning_count": len(wrn), "warnings": wrn[:30], "pdf": str(pdf), "pdf_exists": pdf.exists(),
            "pdf_pages": pages(pdf) if pdf.exists() else 0}

def diff_changes(base, pd, CH):
    nz = lambda x: " ".join(str(x).split())[:80]
    aq = {nz(c["original_quote"]) for c in CH}
    for b in sorted(base.rglob("*")):
        cur = pd / rl(b, base) if b.is_file() and b.suffix.lower() in TE else None
        if not cur or not cur.exists(): continue
        old, new = rd(b).split("\n"), rd(cur).split("\n")
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal": continue
            oq, nq = "\n".join(old[i1:i2]).strip()[:320], "\n".join(new[j1:j2]).strip()[:320]
            if not oq or nz(oq) in aq: continue
            CH.append({"id": "CH-%03d" % (len(CH) + 1), "kind": "model_edit", "file": rl(cur, pd), "line": j1 + 1,
                       "original_quote": oq, "revised_quote": nq, "reason": "content edit",
                       "locator": "%s:%d" % (rl(cur, pd), j1 + 1)})
            if len(CH) >= 200: return CH
    return CH

def main(argv=None):
    ap = argparse.ArgumentParser(prog="latex_doctor.py", description="LaTeX writing & compilation driver: diagnose, "
                                 "repair, build, record (--no-build for static only); exits 0 always.")
    ap.add_argument("--no-build", action="store_true", help="static analysis only")
    ap.add_argument("--input"); ap.add_argument("--out"); ap.add_argument("--work")
    ap.add_argument("--engine", help="pdflatex|xelatex|lualatex")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--max-seconds", type=int, default=780)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    E, DG, NT, CH = [], [], [], []
    ind, out, work = dirs(a)
    jd(out / "result.json", {"skill": {"name": "latex-writing-compile", "version": "1.0.0"},
                             "status": "partial", "case_id": None, "phase": "initialised"})
    if not L:
        DG.append({"code": "lint_module_missing", "message": "latex_lint.py missing: analysis disabled"})
    case = load_case(ind, E)
    cid = next((case[k] for k in ("case_id", "caseId", "id", "task_id") if isinstance(case.get(k), (str, int))), None)
    con = next((v for k, v in case.items() if isinstance(v, dict)
                and k.lower() in ("output_contract", "outputcontract", "contract")), {})
    files = sorted(wk(ind))
    pd, base, dl = out / "tex_project", out / "baseline", out / "deliverable.tex"
    mains = sorted([p for p in files if p.suffix.lower() in (".tex", ".ltx") and "\\documentclass" in rd(p)],
                   key=lambda p: -len(rd(p)))
    if not (pd.exists() and list(pd.rglob("*.tex"))):
        if dl.exists() and "\\documentclass" in rd(dl):
            wr(pd / "main.tex", rd(dl)); NT.append("adopted deliverable.tex")
        elif mains:
            root = mains[0].parent
            for p in [q for q in files if (q.suffix.lower() in CE or q.suffix.lower() in TE)
                      and (root in q.parents or q.parent == root)]:
                try:
                    t = pd / rl(p, root); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, t)
                except Exception: pass
            NT.append("staged the project")
    for p in [q for q in wk(pd) if q.suffix.lower() in TE and not (base / rl(q, pd)).exists()]:
        try:
            t = base / rl(p, pd); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, t)
        except Exception: pass
    pm = sorted([p for p in pd.rglob("*.tex") if "\\documentclass" in rd(p)], key=lambda p: -len(rd(p))) if pd.exists() else []
    if not pm and case:
        cjk = any(L and L.CJK.search(rd(p)) for p in files if p.suffix.lower() in TE)
        ti = next((case[k] for k in ("title", "case_title", "topic") if isinstance(case.get(k), str)), "Draft")
        wr(pd / "main.tex", "%% SCAFFOLD by latex_doctor.py - replace with authored content; numbers must stay\n"
           "%% verbatim from supplied material (see result.json preserved_facts).\n"
           "\\documentclass%s{%s}\n\\usepackage{amsmath,booktabs,graphicx,hyperref}\n\\title{%s}\n\\author{}\n"
           "\\begin{document}\n\\maketitle\n\\section{Outline}\n\\begin{itemize}\n"
           "\\item TODO: author the requested content\n\\end{itemize}\n\\end{document}\n"
           % ("[UTF8]" if cjk else "", "ctexart" if cjk else "article", ti.replace("_", "\\_")))
        DG.append({"code": "scaffold_used", "path": str(pd / "main.tex"),
                   "message": "no .tex: wrote a scaffold; author the content"})
        pm = [pd / "main.tex"]
    if not pm:
        R0 = {"skill": {"name": "latex-writing-compile", "version": "1.0.0"}, "case_id": cid, "errors": E,
              "degradations": DG, "pending_human": [], "uncertainty": [], "changes": [], "change_log": [],
              "preserved_facts": [], "evidence_map": [], "compile": {"attempted": False}, "output_contract": con,
              "status": "input_error" if not files else "insufficient_evidence"}
        jd(out / "result.json", R0)
        if not a.quiet: print(json.dumps({"status": R0["status"], "errors": E}, ensure_ascii=False)[:800])
        return 0

    pj = L.P(pd, pm[0]) if L else None
    D = L.diag(pj) if L else []
    if L:
        for p in sorted(pd.rglob("*.tex")):
            t = rd(p); nt, ch = L.repair(t)
            if nt != t:
                wr(p, nt)
                for rule, ln_, oq, nq, why in ch:
                    CH.append({"id": "CH-%03d" % (len(CH) + 1), "kind": "auto_repair", "rule": rule,
                               "file": rl(p, pd), "line": ln_, "original_quote": oq, "revised_quote": nq,
                               "reason": why, "locator": "%s:%s" % (rl(p, pd), ln_)})
        if CH: NT.append("%d deterministic repairs applied" % len(CH))
        pj = L.P(pd, pm[0])
    D2 = L.diag(pj) if L else D
    mr = pj.mainrel if pj else rl(pm[0], pd)
    eng = engine_for(rd(pm[0]), a.engine); C = {"attempted": False}
    if not a.no_build and eng and time.time() - T0 < a.max_seconds - 45:
        try:
            bd = work / "latex-build"
            shutil.rmtree(bd, ignore_errors=True); bd.mkdir(parents=True, exist_ok=True)
            for p in [q for q in wk(pd) if q.suffix.lower() in CE or q.suffix.lower() in TE]:
                t = bd / rl(p, pd); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, t)
            C = build(bd / Path(mr).parent, Path(mr).name, eng,
                      min(a.timeout, max(30, int(a.max_seconds - (time.time() - T0) - 30))), DG)
            C.update({"attempted": True, "build_dir": str(bd), "main": mr})
            if C["pdf_exists"]:
                shutil.copy2(C["pdf"], out / "deliverable.pdf"); C["pdf_delivered"] = str(out / "deliverable.pdf")
        except Exception as e:
            E.append({"code": "build_failed", "message": "%s: %s" % (type(e).__name__, e)})
            C = {"attempted": True, "exception": str(e)}
    elif not eng: DG.append({"code": "no_latex_engine", "message": "no LaTeX engine"})

    wr(dl, rd(pm[0])); dt = rd(dl)
    T = {}
    for p in files:
        s = p.suffix.lower()
        if s in (".md", ".txt", ".csv", ".json", ".tsv") and rd(p).strip(): T[rl(p, ind)] = rd(p)
        elif s == ".pdf" and which("pdftotext"):
            t = run([which("pdftotext"), "-layout", str(p), "-"], ind, 60)["tail"]
            if len(t.strip()) > 40: T[rl(p, ind)] = t
    T[mr] = rd(base / mr) if (base / mr).exists() else rd(pm[0])
    F = L.guard(L.fx(T), dt) if L else []
    bq = []
    for p in pd.rglob("*.bib"):
        t = rd(p)
        bq += [{"key": m.group(1).strip(), "source_id": rl(p, ind), "quote": t.split("\n")[t.count("\n", 0, m.start())][:140],
                "locator": "%s:%d" % (rl(p, ind), t.count("\n", 0, m.start()) + 1)}
               for m in re.finditer(r"@\w+\s*\{\s*([^,]+),", t)]
    cites = [{"key": k, "used_at": pj.cite[k][0], "defined": k in pj.bib or any(k == b["key"] for b in bq)}
             for k in sorted(pj.cite)] if pj else []
    ev = [{"claim_id": "F%03d" % i, "claim": "supplied value " + f["token"], "kind": "number",
           "source_id": f["source_id"], "locator": f["locator"], "quote": f["quote"], "verified": f["present"]}
          for i, f in enumerate(F, 1)]
    for c in cites:
        b = next((x for x in bq if x["key"] == c["key"]), {})
        ev.append({"claim_id": "C-" + c["key"], "claim": "citation " + c["key"], "kind": "citation",
                   "source_id": b.get("source_id"), "locator": b.get("locator"), "quote": b.get("quote"),
                   "verified": c["defined"]})
    WR = L.receipt(L.wos(case), dt) if L else []
    diff_changes(base, pd, CH)
    miss = [f for f in F if not f["present"]]
    PND = [{"item": "fact missing from deliverable: " + f["token"], "source": f["locator"],
            "action": "restore or justify"} for f in miss[:20]]
    PND += [{"item": "%s %s" % (d["cls"], d["msg"]), "source": "%s:%s" % (d["file"], d["line"]), "action": d["fix"]}
            for d in D2 if d["sev"] == "error"]
    UNC = [{"item": "compilation " + ("succeeded" if C.get("pdf_exists") else
                                      "failed" if C.get("attempted") else "not attempted"),
            "confidence": "high" if C.get("pdf_exists") else "medium"}]
    if miss: UNC.append({"item": "%d/%d supplied facts not found verbatim" % (len(miss), len(F)), "confidence": "high"})
    if WR: UNC.append({"item": "%d work-order items need review" % sum(1 for w in WR if w["status"] != "done_verified"),
                       "confidence": "medium"})
    comp = bool(C.get("attempted") and C.get("pdf_exists"))
    unres = [e for e in C.get("errors", []) if e.get("class") in ("E09_REF", "E10_CITE")]
    blk = [d for d in D2 if d["sev"] == "error"]
    st = "insufficient_evidence" if not dt.strip() else ("ok" if (comp and not unres and not miss and not blk) else "partial")
    MET = {"diagnostics_total": len(D), "diagnostics_error": len(blk),
           "auto_repairs": sum(1 for c in CH if c["kind"] == "auto_repair"),
           "model_edits": sum(1 for c in CH if c["kind"] == "model_edit"), "facts_total": len(F),
           "facts_preserved": len(F) - len(miss),
           "fact_coverage": round((len(F) - len(miss)) / len(F), 3) if F else None, "citations_used": len(cites),
           "citations_defined": sum(1 for c in cites if c["defined"]), "compile_errors": len(C.get("errors", [])),
           "pdf_pages": C.get("pdf_pages", 0), "workorder_done": sum(1 for w in WR if w["status"] == "done_verified")}
    R = {"preserved_facts": F, "evidence_map": ev, "change_log": CH, "pending_human": PND, "compile": C, "errors": E,
         "degradations": DG, "uncertainty": UNC, "diagnostics": D, "diagnostics_residual": D2,
         "workorder_receipt": WR, "citations": cites, "case_id": cid, "status": st, "phase": "finalised",
         "summary": "%s; %d errors; facts %d/%d" % ("compiled" if comp else "static" if not C.get("attempted")
                                                   else "failed", len(blk), len(F) - len(miss), len(F)),
         "deliverable": {"path": "deliverable.tex", "editable": True, "format": "latex", "bytes": len(dt),
                         "main": mr, "pdf": "deliverable.pdf" if comp else None,
                         "pdf_pages": C.get("pdf_pages", 0)},
         "changes": [c["id"] for c in CH],
         "notes": NT, "metrics": MET, "verification": None,
         "runtime": {"elapsed_s": round(time.time() - T0, 2), "python": sys.version.split()[0],
                     "input_root": str(ind), "output_root": str(out), "engine": eng or None}}
    fl = []
    R["output_contract"] = L.fill(con, R, fl) if (L and con) else con
    R["contract_fill"] = fl
    jd(out / "result.json", R)
    wr(out / "build_report.md", "\n".join([
        "# LaTeX build report", "",
        "- `%s`: **%s**, main `%s`, %s, PDF %s p%s" % (
            cid, st, mr, C.get("engine"), C.get("pdf_delivered") or "none", C.get("pdf_pages")),
        "- %d diag (%d err), %d repair, %d edit, %d cerr, facts %d/%d" % (
            len(D), len(blk), MET["auto_repairs"], MET["model_edits"], len(C.get("errors", [])),
            len(F) - len(miss), len(F)),
        "- rerun: `python3 -B scripts/latex_doctor.py --input %s --out %s`" % (ind, out), ""]))
    if L:
        try:
            V = L.verify(ind, out, True)
            NT.append("verify %s/%d" % (V.get("status"), len(V.get("issues", []))))
            cur = json.loads(rd(out / "result.json")); cur["notes"], cur["degradations"] = NT, DG
            jd(out / "result.json", cur)
        except Exception as e: DG.append({"code": "verify_skipped", "message": str(e)[:120]})
    if not a.quiet:
        print(json.dumps({"status": st, "case_id": cid, "deliverable": str(dl), "diagnostics": len(D),
                          "facts": "%d/%d" % (MET["facts_preserved"], MET["facts_total"])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except SystemExit: raise
    except Exception as e:
        try:
            jd(Path(os.environ.get("LATEX_DOCTOR_OUT") or "/app/output") / "result.json",
               {"skill": {"name": "latex-writing-compile", "version": "1.0.0"}, "status": "partial", "case_id": None,
                "degradations": [], "pending_human": [], "uncertainty": [],
                "errors": [{"code": "fatal", "message": "%s: %s" % (type(e).__name__, e)}],
                "runtime": {"elapsed_s": round(time.time() - T0, 2)}})
        except Exception: pass
        sys.exit(0)
