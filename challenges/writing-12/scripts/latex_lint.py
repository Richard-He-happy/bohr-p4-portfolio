#!/usr/bin/env python3
"""latex_lint.py - LaTeX analysis/repair/evidence/audit library for latex_doctor.py."""
import argparse, json, re, sys
from pathlib import Path

CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff]")
UN = (r"%|‰|wt%|at%|mg|kg|ng|mL|L|min|ms|ns|nm|μm|µm|mm|cm|km|m|K|°C|MPa|GPa|kPa|Pa|keV|MeV|GeV|"
      r"eV|GHz|MHz|kHz|Hz|mM|μM|nM|mmol|mol|IU|rpm|kDa|Da|bp|kb|pg|g|h|s")
FR = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(" + UN + r")(?![\w%])")
VERB = ("verbatim", "verbatim*", "lstlisting", "minted", "comment")
AL = ("tabular", "tabular*", "tabularx", "longtable", "tabulary", "align", "align*", "aligned",
      "matrix", "pmatrix", "array", "cases")
CMT = re.compile(r"(?<!\\)%[^\n]*")
VBM = re.compile(r"\\verb\*?(.)[^\n]*?\1")
def load_rules():
    try:
        return json.loads((Path(__file__).resolve().parent.parent / "references" / "rules.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
RJ = load_rules()

ARG = re.compile(RJ.get("rx_arg") or r"\\[A-Za-z]+")
MTH = [re.compile(r"\$\$[\s\S]*?\$\$"), re.compile(r"(?<!\\)\$(?:\\.|[^$\\])*\$"),
       re.compile(r"\\\[[\s\S]*?\\\]"), re.compile(r"\\\([\s\S]*?\\\)")]
TE = {".tex", ".ltx", ".bib", ".md", ".txt", ".csv", ".json", ".cls", ".sty"}
PKG, CREQ = RJ.get("pkg", {}), RJ.get("creq", {})
RULES = [(a, b) for a, b in RJ.get("contract_rules", [])]

def sp(m): return re.sub(r"[^\n]", " ", m.group(0))
def rd(p):
    try: b = Path(p).read_bytes()
    except Exception: return ""
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try: return b.decode(e)
        except Exception: pass
    return b.decode("utf-8", "replace")
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
    try: return str(Path(p).resolve().relative_to(Path(b).resolve())).replace("\\", "/")
    except Exception: return str(p)
def ln(t, p): return t.count("\n", 0, p) + 1
def cm(t): return CMT.sub("", t)
def mm(t, math=True, args=True):
    s = VBM.sub(sp, cm(t))
    if args: s = ARG.sub(sp, ARG.sub(sp, s))
    if math:
        for r in MTH: s = r.sub(sp, s)
    return s
def bs(t):
    d, op, bad, k = 0, [], [], 1
    for ch in re.sub(r"\\[\s\S]", "  ", cm(t)):
        if ch == "\n": k += 1
        elif ch == "{": d += 1; op.append(k)
        elif ch == "}":
            d -= 1
            if d < 0: bad.append(k); d = 0
            elif op: op.pop()
    return d, op[:5], bad[:5]
def es(t):
    st, iss = [], []
    for m in re.finditer(r"\\(begin|end)\s*\{([A-Za-z@*]+)\}", t):
        k, nm, l = m.group(1), m.group(2), ln(t, m.start())
        if nm == "document": continue
        if k == "begin": st.append((nm, l))
        elif st and st[-1][0] == nm: st.pop()
        elif any(x[0] == nm for x in st):
            while st and st[-1][0] != nm: iss.append((st.pop()[0], st[-1][1] if st else l, "unclosed"))
            if st: st.pop()
        else: iss.append((nm, l, "stray end"))
    return st, iss
def vst(l, st, v):
    for m in re.finditer(r"\\begin\{([A-Za-z@*]+)\}|\\end\{([A-Za-z@*]+)\}", l):
        nm = m.group(1) or m.group(2)
        if m.group(1): st.append(nm); v += nm in VERB
        else:
            if nm in st: st.reverse(); st.remove(nm); st.reverse()
            if nm in VERB and v: v -= 1
    return st, v

class P:
    def __init__(s, root, main):
        s.root, s.main = Path(root), Path(main)
        s.text = {rl(p, s.root): rd(p) for p in wk(s.root) if p.suffix.lower() in TE}
        s.maintext, s.mainrel = rd(s.main), rl(s.main, s.root)
        s.lab, s.ref, s.cite, s.bib, s.pkg, s.cls = {}, {}, {}, {}, [], []
        for f, t in s.text.items():
            c = cm(t)
            if f.endswith(".bib"):
                for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)", t): s.bib[m.group(1)] = "%s:%d" % (f, ln(t, m.start()))
            if not f.endswith((".tex", ".ltx")): continue
            for m in re.finditer(r"\\label\{([^}]+)\}", c):
                s.lab.setdefault(m.group(1).strip(), []).append("%s:%d" % (f, ln(c, m.start())))
            for m in re.finditer(r"\\(?:ref|eqref|autoref|pageref|cref|Cref|nameref)\{([^}]+)\}", c):
                [s.ref.setdefault(k.strip(), []).append("%s:%d" % (f, ln(c, m.start())))
                 for k in m.group(1).split(",") if k.strip()]
            for m in re.finditer(r"\\(?:cite|citep|citet|citealp|citeauthor|parencite|textcite|autocite|"
                                 r"supercite|upcite|nocite)\*?(?:\[[^\]]*\])*\{([^}]+)\}", c):
                [s.cite.setdefault(k.strip(), []).append("%s:%d" % (f, ln(c, m.start())))
                 for k in m.group(1).split(",") if k.strip()]
            for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\{([^}]+)\}", c):
                s.pkg += [x.strip() for x in m.group(1).split(",") if x.strip()]
            s.cls += re.findall(r"\\documentclass\s*(?:\[[^\]]*\])?\{([^}]+)\}", c)

def diag(pj):
    D = []
    def a(c, s, f, l, m, x): D.append({"cls": c, "sev": s, "file": f, "line": l, "msg": m, "fix": x})
    for f, t in pj.text.items():
        if not f.endswith((".tex", ".ltx")): continue
        for i2, l2 in enumerate(t.split("\n"), 1):
            if re.search(r"(?<=[\d)])(\s*)%", re.sub(r"\\%", "", l2)):
                a("E19_PERCENT", "error", f, i2, "bare `%` after a number",
                  "write \\%")
        c = cm(t); d, op, bad = bs(c)
        if bad: a("E05_BRACE", "error", f, bad[0], "stray `}`", "delete it")
        if d > 0: a("E05_BRACE", "error", f, op[0] if op else ln(c, len(c)), "%d unclosed `{` at EOF" % d,
                    "close group line %s" % (op[0] if op else "?"))
        st, iss = es(c)
        for nm, l, k in iss: a("E04_ENV", "error", f, l, "environment %r %s" % (nm, k),
                               "add \\end{%s} or drop it" % nm)
        for nm, l in st[:4]: a("E04_ENV", "error", f, l, "\\begin{%s} never closed" % nm, "insert \\end{%s}" % nm)
        if len(re.findall(r"(?<!\\)\$", VBM.sub(sp, c))) % 2:
            a("E06_MATH", "error", f, ln(c, c.rfind("$")), "odd number of `$`", "add or remove the missing `$`")
        msk = mm(c); L, ML, ST, vb = c.split("\n"), msk.split("\n"), [], 0
        for i, l in enumerate(L):
            ST, vb = vst(l, ST, vb)
            if vb: continue
            tab = any(e in AL for e in ST); ml = ML[i] if i < len(ML) else ""
            for j, ch in enumerate(l):
                if j < len(ml) and ml[j] == ch and ch in "&_^#" and not (j and l[j - 1] == "\\") and not (ch == "&" and tab):
                    a("E07_ALIGN_TAB" if ch == "&" else "E18_MATH_MODE", "error", f, i + 1,
                      "bare %r" % ch, "escape as \\%s" % ch); break
        for m in re.finditer(r"\\begin\{(tabular\*?|longtable)\}\s*\{([^{}]*)\}", c):
            k = len([x for x in m.group(2) if x in "lcrpmbXSY"])
            b0 = m.end(); e0 = re.search(r"\\end\{%s\}" % m.group(1), c[b0:])
            rows = c[b0:b0 + (e0.start() if e0 else 4000)].split("\\\\")
            bad = [r for r in rows if r.strip() and len(re.split(r"(?<!\\)&", r)) - 2 * r.count("\\multicolumn") != k]
            if k and bad:
                a("E08_TABLE_CELLS", "warning", f, ln(c, b0), "row %d, spec %d"
                  % (len(re.split(r"(?<!\\)&", bad[0])) - 2 * bad[0].count("\\multicolumn"), k),
                  "fix `&`/spec")
            if k >= 6: a("H_WIDE_TABLE", "hazard", f, ln(c, m.start()), "table with %d columns" % k,
                         "use tabularx or split rows")
    for k, lo in pj.ref.items():
        if k not in pj.lab: a("E09_REF", "error", lo[0].split(":")[0], int(lo[0].split(":")[1]),
                              "label %r missing" % k, "add \\label{%s}" % k)
    bit = set()
    for t in pj.text.values(): bit |= {m.group(1) for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", t)}
    for k, lo in pj.cite.items():
        if k not in pj.bib and k not in bit:
            a("E10_CITE", "error", lo[0].split(":")[0], int(lo[0].split(":")[1]), "cite %r missing" % k,
              "add from material; never invent references")
    if not pj.cls: a("E15_CLASS", "error", pj.mainrel, 1, "no \\documentclass", "wrap the fragment in the template class")
    used = set(re.findall(r"\\([A-Za-z]+)", mm(pj.maintext))) | set(re.findall(r"\\begin\{([A-Za-z*]+)\}", pj.maintext))
    miss = {}
    for cmd, pk in PKG.items():
        if cmd in used and pk not in pj.pkg: miss.setdefault(pk, []).append(cmd)
    for pk, cs in miss.items():
        a("E03_PACKAGE", "warning", pj.mainrel, 1, "%s need %r" % (",".join(sorted(cs)[:4]), pk),
          "\\usepackage{%s} in the preamble" % pk)
    cl = (pj.cls[0] if pj.cls else "").lower()
    for x in next((v for k, v in CREQ.items() if k in cl), "").split():
        ok = ("\\begin{abstract}" in pj.maintext or "\\abstract{" in pj.maintext) if x == "abstract" else \
             ("\\begin{keyword}" in pj.maintext or "\\keywords" in pj.maintext) if x in ("keyword", "keywords") \
             else ("\\" + x) in pj.maintext
        if not ok: a("T_TEMPLATE_FIELD", "warning", pj.mainrel, 1, "field %r missing" % x,
                     "add %s" % x)
    if CJK.search(pj.maintext) and not any(x in pj.pkg for x in ("ctex", "xeCJK", "CJK")):
        a("E14_ENCODING", "error", pj.mainrel, 1, "CJK text without ctex", "use ctexart + xelatex")
    return D

def _mk(l):
    s = re.sub(r"(?<!\\)%.*$", lambda m: " " * len(m.group(0)), l)
    s = VBM.sub(sp, s)
    s = ARG.sub(sp, s)
    for r in MTH: s = r.sub(sp, s)
    return s
def repair(t):
    ch = []
    if t.startswith("\ufeff") or "\r" in t:
        t = t.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
        ch.append(("R01_normalize", 1, "(BOM/CRLF)", "(UTF-8 LF)", "normalise to UTF-8/LF"))
    if "\\begin{document}" not in t: return t, ch
    need = sorted({pk for cmd, pk in PKG.items() if re.search(r"\\%s\b" % re.escape(cmd), cm(t))
                   and not re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b%s\b" % re.escape(pk), t)})
    if need:
        L, an = t.split("\n"), 0
        for i, l in enumerate(L):
            if "\\begin{document}" in l: break
            if re.match(r"\s*\\(usepackage|RequirePackage|documentclass)\b", l): an = i
        blk = ["\\usepackage{%s}" % x for x in need]
        t = "\n".join(L[:an + 1] + blk + L[an + 1:])
        ch.append(("R02_package", an + 1, L[an].strip(), "\n".join(blk), "load the package"))
    out, es, vb, body = [], [], 0, False
    for i, l in enumerate(t.split("\n")):
        if "\\begin{document}" in l: body = True
        es, vb = vst(l, es, vb)
        if body and not vb:
            o = l
            for mm in reversed(list(re.finditer(r"(?<=[\d)])\s*%(?!\s*$)", l))):
                if mm.start() and l[mm.start() - 1] != "\\":
                    l = l[:mm.start()] + "\\%" + l[mm.end():]
            if l != o:
                ch.append(("R06_percent", i + 1, o.strip()[:200], l.strip()[:200], "escape literal percent"))
            ml = _mk(l)
            tab = any(e in AL for e in es)
            nl, hit = [], 0
            for j2, c in enumerate(l):
                if j2 < len(ml) and ml[j2] == c and c in "&_^#" and not (j2 and l[j2 - 1] == "\\") \
                        and not (c == "&" and tab):
                    nl.append("\\" + c); hit += 1
                else: nl.append(c)
            s2 = "".join(nl)
            if hit: ch.append(("R04_escape", i + 1, l.strip()[:200], s2.strip()[:200],
                               "escape text-mode specials that break the build"))
            l = s2
        out.append(l)
    t = "\n".join(out)
    if "\\end{document}" not in t:
        t = t.rstrip("\n") + "\n\\end{document}\n"
        ch.append(("R03_end_document", len(t.split("\n")), "(end of file)", "\\end{document}",
                   "TeX needs a closing \\end{document}"))
    d, op, _ = bs(t)
    if d > 0:
        t = t.rstrip("\n") + "\n" + "}" * d + "\n"
        ch.append(("R05_close_braces", op[0] if op else 0, "(open group)", "}" * d, "close the open brace(s)"))
    return t, ch
def fx(T, cap=120):
    F, seen = [], set()
    for nm, t in T.items():
        for i, l in enumerate(t.split("\n"), 1):
            for m in FR.finditer(l):
                k = (m.group(0).replace(" ", ""), nm)
                if k in seen: continue
                seen.add(k)
                F.append({"token": m.group(0).strip(), "value": m.group(1), "unit": m.group(2), "source_id": nm,
                          "locator": "%s:%d" % (nm, i), "quote": l.strip()[:180]})
            if len(F) >= cap: return F
    return F
def guard(F, d):
    L = d.split("\n")
    for f in F:
        h = next((i for i, l in enumerate(L, 1) if re.search(r"(?<![\w.])" + re.escape(f["value"]) + r"(?![\w])", l)
                  and (not f["unit"] or f["unit"] in l)), None)
        f["present"] = bool(h); f["deliverable_locator"] = ("deliverable.tex:%d" % h) if h else None
        f["status"] = "preserved" if h else "missing"
    return F

def wos(c):
    out = []
    for k, v in c.items():
        if not re.search(r"work.?order|edit.?task|revision|checklist|requirement", str(k).lower()): continue
        for i, it in enumerate(v if isinstance(v, list) else [v]):
            t = " | ".join(map(str, it.values())) if isinstance(it, dict) else str(it)
            oid = (it.get("id") or it.get("index") or "WO-%d" % (i + 1)) if isinstance(it, dict) else "WO-%d" % (i + 1)
            out.append({"id": str(oid), "text": t[:600], "locator": "case.json#/%s/%d" % (k, i)})
    return out

def receipt(items, d):
    o = []
    for it in items:
        an = re.findall(r"\\[A-Za-z]+|\b(booktabs|amsmath|siunitx|tabularx|longtable|hyperref|cleveref|biblatex|"
                        r"natbib|graphicx|ctex|equation|table|figure)\b", it["text"], re.I)
        f = [x for x in an if x.strip() in d]; m = [x for x in an if x.strip() not in d]
        o.append({"id": it["id"], "requirement": it["text"], "locator": it["locator"],
                  "status": "done_verified" if (an and not m) else "partial_anchor_match" if f else
                  "not_found" if an else "manual_review_required",
                  "anchors_found": sorted(set(f))[:8], "anchors_missing": sorted(set(m))[:8]})
    return o

def fill(con, P_, log):
    def rec(n, path):
        if isinstance(n, dict): return {k: rec(v, path + [str(k)]) for k, v in n.items()}
        key = path[-1] if path else ""
        nm = next((x for p, x in RULES if re.search(p, key.lower())), None)
        if nm and P_.get(nm) is not None:
            log.append({"key": "/".join(path), "mapped_to": nm, "filled": True}); return P_[nm]
        log.append({"key": "/".join(path), "mapped_to": None, "filled": n not in (None, "", [], {})})
        return n if n not in (None, "", [], {}) else None
    return rec(con, [])

def norm(s): return " ".join(str(s).split())
def miss_keys(con, got, pre=""):
    out = []
    for k, v in con.items():
        g = got.get(k) if isinstance(got, dict) else None
        if g is None: out.append(pre + "/" + k)
        elif isinstance(v, dict) and isinstance(g, dict): out += miss_keys(v, g, pre + "/" + k)
    return out

def verify(ind, out, patch=True):
    ind, out, iss = Path(ind), Path(out), []
    try: R = json.loads(rd(out / "result.json"))
    except Exception as e:
        R = {}; iss.append({"check": "result_json", "status": "fail", "detail": "%s: %s" % (type(e).__name__, e)})
    con = {}
    cp = ind / "case.json"
    if cp.exists():
        try:
            con = next((v for k, v in json.loads(rd(cp)).items() if isinstance(v, dict)
                        and k.lower() in ("output_contract", "outputcontract", "contract")), {})
        except Exception as e: iss.append({"check": "case_json", "status": "warn", "detail": str(e)})
    if con and R:
        mk = miss_keys(con, R.get("output_contract") or {})
        if mk: iss.append({"check": "contract_keys", "status": "fail", "detail": mk[:20]})
    if not R: return {"status": "fail", "issues": iss, "checks": {}}
    iss += [{"check": "field:" + k, "status": "fail", "detail": "missing field"}
            for k in ("case_id", "status", "errors", "degradations", "pending_human", "uncertainty", "runtime") if k not in R]

    def find(name, post=False):
        for b in ((out / "tex_project", out / "baseline", ind) if post else (out / "baseline", ind, out / "tex_project")):
            p = b / str(name)
            if p.is_file(): return rd(p)
        return ""
    cl = R.get("change_log") or []; bad = []
    for c in cl[:120]:
        oq, nq = norm(c.get("original_quote", "")), norm(c.get("revised_quote", ""))
        if not oq or not nq: continue
        if oq not in norm(find(c.get("file"))): bad.append([c.get("id"), "original"])
        elif nq not in norm(find(c.get("file"), True)): bad.append([c.get("id"), "revised"])
    if bad: iss.append({"check": "change_log_quotes", "status": "fail", "detail": bad[:10]})
    ev = R.get("evidence_map") or []
    bad = [e.get("claim_id") for e in ev[:150]
           if norm(e.get("quote") or "") and norm(e["quote"]) not in norm(find(str(e.get("source_id") or "")))]
    if bad: iss.append({"check": "evidence_quotes", "status": "fail", "detail": bad[:10]})
    dt = rd(out / "deliverable.tex")
    if not dt.strip(): iss.append({"check": "deliverable", "status": "fail", "detail": "deliverable.tex missing"})
    else:
        for k, msg in (("\\documentclass", "no \\documentclass"), ("\\end{document}", "no \\end{document}")):
            if k not in dt: iss.append({"check": "deliverable", "status": "fail", "detail": msg})
        d, op, b2 = bs(dt)
        if d or b2: iss.append({"check": "deliverable_braces", "status": "fail", "detail": [d, b2[:3]]})
    F = R.get("preserved_facts") or []
    bad = [f.get("token") for f in F if f.get("present") and f.get("value")
           and not re.search(r"(?<![\w.])" + re.escape(str(f["value"])) + r"(?![\w])", dt)]
    if bad: iss.append({"check": "facts_presence", "status": "fail", "detail": bad[:10]})
    c = R.get("compile") or {}
    if c.get("pdf_delivered") and not Path(c["pdf_delivered"]).exists():
        iss.append({"check": "pdf", "status": "fail", "detail": "pdf_delivered path missing"})
    m = R.get("metrics") or {}
    if m.get("facts_total") is not None and m["facts_total"] != len(F):
        iss.append({"check": "counts", "status": "warn", "detail": "facts_total mismatch"})
    if m.get("compile_errors") is not None and m["compile_errors"] != len(c.get("errors") or []):
        iss.append({"check": "counts", "status": "warn", "detail": "metrics.compile_errors mismatch"})
    fails = [i for i in iss if i["status"] == "fail"]
    V = {"status": "ok" if not fails else ("warn" if len(fails) <= 1 else "fail"), "issues": iss,
         }
    if patch:
        R["verification"] = V
        if fails and R.get("status") == "ok":
            R["status"] = "partial"
            R.setdefault("degradations", []).append({"code": "verify_downgrade",
                                                     "message": "-> partial: %d failures" % len(fails)})
        for nm, obj in (("result.json", R), ("verification.json", V)):
            try: (out / nm).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception as e: V["patch_error"] = str(e)
    return V

if __name__ == "__main__":
    pos = [x for x in sys.argv[1:] if not x.startswith("-")]
    try: print(json.dumps(verify(pos[0] if pos else "/input", pos[1] if len(pos) > 1 else "/app/output", True),
                          ensure_ascii=False)[:2500])
    except Exception as e: print(json.dumps({"status": "fail", "error": str(e)}))
    sys.exit(0)
