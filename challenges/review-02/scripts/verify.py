#!/usr/bin/env python3
"""review-fact-check :: deterministic evidence engine + result verifier (stdlib, no network).
Imported by main.py (checks, pattern runner, merge, contract echo); also runnable alone:
  python3 scripts/verify.py --input /input --output /app/output [--json]
Re-checks a finished result.json: fields, contract echo, enums, issue-id sequence, verbatim
quotes, count consistency, DOI fabrication guard. Exit 0; failures are reported, never raised."""
import argparse, json, re, sys
from pathlib import Path
RS = Path(__file__).resolve().parent.parent / "references"
KD = ["fact_check", "citation_support", "method_design", "stats_report", "argument_chain", "academic_norm"]
SV = ["major", "minor", "info"]
VD = ["full", "partial", "none", "undetermined"]
LF = {"type", "description", "required", "items", "enum", "example", "default", "format"}
DEF = {"kind": "fact_check", "severity": "minor", "certainty": "likely", "status": "issue",
       "zh": "{rule}", "en": "{rule}", "fix_zh": "", "fix_en": ""}
try:
    CAT = json.loads((RS / "checks.json").read_text(encoding="utf-8"))
except Exception:
    CAT = {}
CATA, PAT = CAT.get("catalog", {}), CAT.get("patterns", [])
RKR = CAT.get("contract_rules") or []


def ws(t):
    return re.sub(r"\s+", " ", t or "").strip()


def sr(d, k):
    for i, s in enumerate(d["secs"]):
        if s[0] == k:
            return s[1], (d["secs"][i + 1][1] if i + 1 < len(d["secs"]) else len(d["text"]))
    return 0, 0


def stext(d, k):
    a, b = sr(d, k)
    return d["text"][a:b] if b > a else ""


def sat(d, p):
    c = None
    for s in d["secs"]:
        if s[1] <= p:
            c = s[0]
    return c


def wh(d, p):
    pg = pa = None
    for x in d["pages"]:
        if x["l"] and x["s"] <= p <= x["e"]:
            pg = x["l"]
    for i, b in enumerate(d["paras"], 1):
        if b["s"] - 2 <= p <= b["e"] + 2:
            pa = i
    return pg, pa


def lc(d, p):
    if not d:
        return "?"
    pg, pa = wh(d, p)
    return d["name"] + ("#" + pg if pg else "") + ("/para%d" % pa if pa else "") + "@char%d" % p


def sent(d, p):
    t = d["text"]
    a = max(t.rfind("\n", 0, p), t.rfind(". ", 0, p), t.rfind("。", 0, p))
    a = 0 if a < 0 else a + 1
    e = [x for x in (t.find("\n", p), t.find(". ", p), t.find("。", p)) if x >= 0]
    return ws(t[a:(min(e) + 1 if e else min(len(t), p + 400))])[:500]


class X:
    """Issue collector: formats a rule from the catalog into a finding with locator + verbatim quote."""

    def __init__(self, docs, lang):
        self.d, self.zh, self.it, self.seen = docs, lang == "zh", [], set()
        self.pend, self.un = [], []

    def add(self, rule, d, p, q, status=None, **kw):
        c, q = CATA.get(rule) or DEF, ws(q)[:500]
        k = (rule, d["id"], q[:70])
        if len(self.it) >= 150 or k in self.seen:
            return None
        self.seen.add(k)
        v = dict(kw, q=q[:90], rule=rule)
        try:
            cm = ((c.get("zh") if self.zh else c.get("en")) or c.get("en") or rule).format(**v)
            fx = ((c.get("fix_zh") if self.zh else c.get("fix_en")) or c.get("fix_en") or "").format(**v)
        except Exception:
            cm, fx = rule, ""
        pg, pa = wh(d, p)
        st = status or c.get("status", "issue")
        f = {"issue_id": "R-%03d" % (len(self.it) + 1), "kind": c.get("kind", "fact_check"),
             "severity": c.get("severity", "minor"), "certainty": c.get("certainty", "likely"), "status": st,
             "rule_id": rule, "doc": d["name"], "page": pg, "paragraph": pa, "locator": lc(d, p), "quote": q,
             "claim": cm, "reason": cm, "suggested_fix": fx, "section": sat(d, p) or "-",
             "lang": "zh" if self.zh else "en"}
        self.it.append(f)
        if st == "pending_human":
            self.pend.append({"issue_id": f["issue_id"], "why": cm, "need": fx})
        return f


def fq(x, q):
    """Locate a verbatim quote: exact match first, then whitespace/case tolerant match."""
    q = ws(q)
    if len(q) < 8:
        return None
    for d in x.d:
        i = d["text"].find(q)
        if i >= 0:
            return d, i, q
    rx = re.compile(r"\s*".join(re.escape(w) for w in q.split(" ")), re.I)
    for d in x.d:
        m = rx.search(d["text"])
        if m:
            return d, m.start(), m.group(0)
    return None


def pats(x):
    for d in x.d:
        t = d["text"]
        for p in PAT:
            if (p.get("require_doc") and not re.search(p["require_doc"], t)) or \
                    (p.get("absent_doc") and re.search(p["absent_doc"], t)):
                continue
            if p.get("doc_level"):
                x.add(p["rule"], d, 0, t[:150])
                continue
            a, b = sr(d, p["section"]) if p.get("section") else (0, len(t))
            ai = p.get("absent_in_section")
            if b <= a or (ai and re.search(ai["regex"], stext(d, ai["section"]))):
                continue
            for m in re.finditer(p["regex"], t[a:b]):
                pos, w = a + m.start(), p.get("window", 200)
                near = t[max(0, pos - w):pos + w]
                if (p.get("require_near") and not re.search(p["require_near"], near)) or \
                        (p.get("not_near") and re.search(p["not_near"], near)):
                    continue
                x.add(p["rule"], d, pos, sent(d, pos) or m.group(0))
                if p.get("first_only"):
                    break


def refs(d):
    a, b = sr(d, "references")
    if b <= a:
        return []
    body = d["text"][a:b]
    body = body.split("\n", 1)[1] if "\n" in body else body
    mk = list(re.finditer(r"(?m)^\s*\[?(\d{1,3})[\]\(\)\.]\s+", body))
    o = ([{"n": int(m.group(1)), "raw": ws(body[m.start():(mk[i + 1].start() if i + 1 < len(mk) else len(body))])}
          for i, m in enumerate(mk)] if len(mk) >= 3 else
         [{"n": None, "raw": ws(y)} for y in re.split(r"\n\s*\n", body) if len(ws(y)) > 25])
    for r in o:
        y = re.findall(r"\b(?:19|20)\d{2}\b", r["raw"])
        dm = re.search(r"(10\.\d{4,9}/[^\s,;\)]+)", r["raw"])
        r["year"] = y[-1] if y else None
        r["doi"] = dm.group(1).rstrip(".").lower() if dm else None
        r["pre"] = bool(re.search(r"rxiv|arxiv|research square|ssrn|preprint", r["raw"], re.I))
        r["ret"] = bool(re.search(r"retract|expression of concern|withdrawn|corrigend|erratum", r["raw"], re.I))
        r["rev"] = bool(re.search(r"\breview\b|meta-analysis|systematic review|综述", r["raw"], re.I))
    return list(o)


def cites(d):
    o = []
    for m in re.finditer(r"\[(\d{1,3}(?:\s*[,\-–]\s*\d{1,3})*)\]", d["text"]):
        ns = []
        for part in re.split(r"\s*,\s*", m.group(1)):
            mm = re.match(r"(\d+)\s*[–-]\s*(\d+)", part)
            if mm and int(mm.group(2)) >= int(mm.group(1)):
                ns += list(range(int(mm.group(1)), min(int(mm.group(2)), int(mm.group(1)) + 40) + 1))
            elif part.strip().isdigit():
                ns.append(int(part.strip()))
        if ns:
            o.append({"p": m.start(), "raw": m.group(0), "n": ns, "st": "n"})
    for m in re.finditer(r"\(([A-Z][A-Za-z\-']{1,22}(?:\s+(?:et\s+al\.?|and|&)\s*[A-Z][A-Za-z\-']{1,22})?)"
                         r"[^()]{0,30}?((?:19|20)\d{2})[a-z]?\)", d["text"]):
        o.append({"p": m.start(), "raw": m.group(0), "a": m.group(1), "y": m.group(2), "st": "ay"})
    return o


def crefs(x):
    """Citation structure checks: numbering, uncited entries, author-year, duplicate DOI, source status."""
    for d in x.d:
        R = refs(d)
        if not R:
            continue
        C, rn = cites(d), {r["n"] for r in R if r["n"]}
        N = [c for c in C if c["st"] == "n"]
        if N and rn:
            hi, ct, bad = max(rn), set(), []
            for c in N:
                ct.update(c["n"])
                bad += [(c, k) for k in c["n"] if k not in rn and (k > hi or k < 1)]
            for c, k in bad[:5]:
                x.add("citation.number_out_of_range", d, c["p"], sent(d, c["p"]), k=k, n=len(rn))
            if rn - ct:
                r0 = next(r for r in R if r["n"] == min(rn - ct))
                x.add("citation.uncited_reference", d, max(d["text"].find(r0["raw"][:50]), 0),
                      r0["raw"][:200], k=", ".join(str(i) for i in sorted(rn - ct)[:8]))
        for c in [c for c in C if c["st"] == "ay"][:40]:
            hit = [r for r in R if c["a"].split()[0].lower() in r["raw"].lower()]
            if not hit:
                x.add("citation.entry_missing", d, c["p"], sent(d, c["p"]), a=c["a"])
            elif c["y"] and all(r["year"] != c["y"] for r in hit):
                x.add("citation.year_mismatch", d, c["p"], sent(d, c["p"]), y=c["y"],
                      ry=", ".join(str(r["year"]) for r in hit[:3]))
        for r in R:
            p = max(d["text"].find(r["raw"][:50]), 0)
            if r["ret"]:
                x.add("citation.retracted_or_corrected", d, p, r["raw"][:200])
            elif r["pre"]:
                x.add("citation.preprint_status", d, p, r["raw"][:200])
        for doi in {r["doi"] for r in R if r["doi"]}:
            sm = [r for r in R if r["doi"] == doi]
            if len(sm) > 1:
                x.add("citation.duplicate_doi", d, max(d["text"].find(sm[0]["raw"][:50]), 0),
                      sm[0]["raw"][:200], doi=doi, n=len(sm))


def cnums(x):
    for d in x.d:
        t = d["text"]
        for pat, k in ((r"(\d+(?:\.\d+)?)\s*%\s*[\(\[]\s*n\s*=\s*(\d+)\s*/\s*(\d+)\s*[\)\]]", 1),
                       (r"(\d+)\s*/\s*(\d+)\s*[\(\[]\s*(\d+(?:\.\d+)?)\s*%\s*[\)\]]", 2)):
            for m in re.finditer(pat, t, re.I):
                pc, a, b = ((float(m.group(1)), int(m.group(2)), int(m.group(3))) if k == 1 else
                            (float(m.group(3)), int(m.group(1)), int(m.group(2))))
                real = 100.0 * a / b if 0 < a <= b else -1
                if real > 0 and abs(real - pc) > max(0.6, 0.02 * real):
                    x.add("fact.percent_fraction_mismatch", d, m.start(), sent(d, m.start()),
                          pct="%g" % pc, a=a, b=b, real="%.1f" % real)
        at = stext(d, "abstract")
        if at:
            body = t.replace(at, " ", 1)
            an = {int(i) for i in re.findall(r"(?i)\bN\s*=\s*(\d{1,6})\b", at)}
            bn = {int(i) for i in re.findall(r"(?i)\bN\s*=\s*(\d{1,6})\b", body)}
            if an and bn and not (an & bn):
                x.add("fact.sample_size_mismatch", d, max(t.lower().find("n ="), 0), ws(at)[:200],
                      a=sorted(an)[:4], b=sorted(bn)[:4])
        if len(t) > 800:
            have = {s[0] for s in d["secs"]}
            for k in ("methods", "results", "references"):
                if k not in have:
                    x.add("norm.missing_section", d, 0, t[:120], a=k.title())
                    x.un.append({"doc": d["name"], "item": k + " section",
                                 "reason": "heading not detected; section-scoped checks skipped"})


def pairs(x):
    o = []
    for d in x.d:
        R = refs(d)
        if not R:
            continue
        bn = {r["n"]: r for r in R if r["n"]}
        for c in cites(d)[:120]:
            s = sent(d, c["p"])
            if len(s) < 25:
                continue
            for k in (c["n"][:3] if c["st"] == "n" else [None]):
                r = bn.get(k)
                o.append({"pair_id": "CP-%03d" % (len(o) + 1), "doc": d["id"], "claim_quote": s,
                          "claim_locator": lc(d, c["p"]), "citation": c["raw"], "ref_number": k,
                          "ref_raw": r["raw"][:300] if r else None, "ref_year": r["year"] if r else c.get("y"),
                          "ref_is_review": r["rev"] if r else None, "verdict": None, "verdict_reason": None,
                          "requires_semantic_judgment": True,
                          "needs": "read the cited source; decide full/partial/none/undetermined with evidence"})
    return o


def merge(x, path, err, pr=None):
    """Merge agent findings; a non-verbatim quote is rejected into pending_human, never asserted."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        err.append({"stage": "merge", "file": str(path), "error": "%s: %s" % (type(e).__name__, str(e)[:140])})
        return 0, []
    n, rej = 0, []
    for i, f in enumerate(data.get("findings") or []):
        h = fq(x, f.get("quote")) if isinstance(f, dict) and f.get("quote") else None
        if not h:
            q = str((f or {}).get("quote") or "")[:200]
            rej.append({"source": "agent_findings", "index": i, "quote": q,
                        "why": "quote_not_found_in_source_text",
                        "action": "moved to pending_human; never asserted as a finding"})
            x.pend.append({"issue_id": None, "why": "quote not verbatim: %s" % q[:100],
                           "need": "confirm exact wording and locator; do not rewrite the source to match"})
            continue
        d, p, vq = h
        r = x.add("agent." + str(f.get("rule_id") or "semantic"), d, p, vq,
                  status="pending_human" if f.get("status") == "pending_human" else None)
        if r:
            for k in ("kind", "severity", "certainty", "claim", "suggested_fix"):
                v = f.get(k)
                if v and (k != "kind" or v in KD) and (k != "severity" or v in SV):
                    r[k] = ws(str(v))[:300]
            n += 1
    if pr is not None:
        for v in data.get("citation_verdicts") or []:
            for p in pr:
                if p["pair_id"] == v.get("pair_id") and v.get("verdict") in VD:
                    p.update({"verdict": v["verdict"],
                              "verdict_reason": ws(str(v.get("reason", "")))[:400],
                              "requires_semantic_judgment": False})
    return n, rej


def rk(k, data):
    """Map a contract field name to a result field by semantics (never renames the key)."""
    for p, t in RKR:
        if re.search(p, k.lower()):
            if t:
                return t, (t in data)
            return ("report_path" if re.search(r"path|file|url|link", k.lower()) else "report_markdown"), True
    return None, False


def fill(spec, data, unm, pre=""):
    """Echo every output_contract key unchanged; unknown keys keep null and are listed in unmapped."""
    if not isinstance(spec, dict):
        return spec if isinstance(spec, list) else None
    if spec and set(spec) <= LF:
        return None
    o = {}
    for k, v in spec.items():
        t, ok = rk(k, data)
        if ok:
            o[k] = data.get(t)
            if data.get(t) is None:
                unm.append({"field": pre + k, "reason": "matched '%s', value unavailable" % t})
        elif isinstance(v, dict) and v and not set(v) <= LF:
            o[k] = fill(v, data, unm, pre + k + ".")
        elif isinstance(v, list) and v and all(isinstance(i, str) for i in v):
            o[k] = [{i: (data.get(rk(i, data)[0]) if rk(i, data)[1] else None) for i in v}]
            unm += [{"field": pre + k + "." + i, "reason": "no semantic match; kept null"}
                    for i in v if not rk(i, data)[1]]
        else:
            o[k] = None
            unm.append({"field": pre + k, "reason": "no semantic match; kept null"})
    return o


def vcheck(res, docs, contract=None):
    """Re-verify a finished result against the source text. Never raises; returns a report dict."""
    x, fail, chk = X(docs, "en"), [], 0
    src = " ".join(d["text"] for d in docs)
    for k in ("skill", "case_id", "status", "issues", "review_summary", "citation_support_matrix",
              "pending_human", "uncertainty", "sources", "errors", "degradations", "changes", "runtime",
              "output_contract"):
        chk += 1
        if k not in res:
            fail.append({"check": "field:" + k, "detail": "missing top-level field"})
    oc = res.get("output_contract") or {}
    for k in (contract or {}):
        chk += 1
        if k not in oc:
            fail.append({"check": "contract:" + k, "detail": "contract key not echoed"})
    ids, sev = [], {}
    for f in res.get("issues") or []:
        chk += 1
        i = f.get("issue_id")
        ids.append(i)
        sev[f.get("severity")] = sev.get(f.get("severity"), 0) + 1
        if f.get("kind") not in KD or f.get("severity") not in SV:
            fail.append({"check": "enum", "detail": i})
        if not (f.get("locator") and f.get("quote")):
            fail.append({"check": "evidence_fields", "detail": i})
        elif not fq(x, f.get("quote")):
            fail.append({"check": "quote_resolution", "detail": i, "quote": str(f.get("quote"))[:120]})
        for k in ("claim", "suggested_fix", "quote"):
            for doi in re.findall(r"10\.\d{4,9}/\S+", str(f.get(k) or "")):
                chk += 1
                if doi.rstrip(".,;)") not in src:
                    fail.append({"check": "doi_not_in_source", "detail": i, "value": doi})
    chk += 3
    s = res.get("review_summary") or {}
    if s.get("issues_total") != len(ids):
        fail.append({"check": "count_issues_total", "detail": "%s != %s" % (s.get("issues_total"), len(ids))})
    if (s.get("by_severity") or {}).get("major") != sev.get("major", 0):
        fail.append({"check": "count_by_severity", "detail": "major mismatch"})
    if ids != ["R-%03d" % i for i in range(1, len(ids) + 1)]:
        fail.append({"check": "issue_id_sequence", "detail": "ids not sequential"})
    chk += 1
    if (res.get("errors") or []) and res.get("status") == "ok":
        fail.append({"check": "status_honesty", "detail": "status=ok but errors[] is not empty"})
    return {"checked": chk, "failed": len(fail), "passed": chk - len(fail), "ok": not fail,
            "failures": fail[:40]}


def cli(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify.py", description="Re-verify result.json against the source text (stdlib, exit 0).",
        epilog="python3 scripts/verify.py --input /input --output /app/output [--json]")
    ap.add_argument("--input", default=None, help="input dir (default /input)")
    ap.add_argument("--output", default=None, help="output dir holding result.json (default /app/output)")
    ap.add_argument("--json", action="store_true", help="print the full verification report as JSON")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    rep = {"checked": 0, "passed": 0, "failed": 0, "ok": False, "failures": []}
    try:
        import main as M
        out = Path(a.output or "/app/output")
        res = json.loads((out / "result.json").read_text(encoding="utf-8"))
        inp = M.pickdir(a.input, "REVIEW_INPUT", [Path("/input"), M.H.parent / "input"])
        docs = M.corpus(inp, [], [], [])
        contract = {}
        try:
            contract = json.loads((inp / "case.json").read_text(encoding="utf-8")).get("output_contract") or {}
        except Exception:
            pass
        rep = vcheck(res, docs, contract)
    except Exception as e:
        rep["failures"] = [{"check": "verify_runtime", "detail": "%s: %s" % (type(e).__name__, str(e)[:200])}]
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("verify: checked=%d passed=%d failed=%d ok=%s" % (rep["checked"], rep["passed"], rep["failed"], rep["ok"]))
        for f in rep["failures"][:20]:
            print("  FAIL %s %s %s" % (f.get("check"), f.get("detail"), str(f.get("value") or f.get("quote") or "")[:80]))
    return 0


if __name__ == "__main__":
    try:
        cli()
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("verify failed softly: %s\n" % e)
    sys.exit(0)
