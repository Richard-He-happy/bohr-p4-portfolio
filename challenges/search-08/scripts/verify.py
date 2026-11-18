#!/usr/bin/env python3
"""Shared deterministic core of the screening skill plus a re-checker: normalization, record
discovery, criteria operationalization, dedup, screening, arbitration and check(). main.py imports
this module. Exit codes are always 0."""
import csv, hashlib, io, json, re, sys, unicodedata, zipfile, zlib
from pathlib import Path

V = "1.0.0"
STOP = set(("a an the and or of for with from to in on at by as is are was were be been this that these those its their "
            "our your we they them us not no non only rather than then when which while who into over about among within "
            "without such other others each more most less least also may might must can could should would has have had "
            "do does did both same all very per using use based study studies paper papers article articles report "
            "research evidence data result results including include excluded exclusion criteria criterion review "
            "population participants patient patients").split())
A = {}
for g in ("title=title,article_title,titles,标题;abstract=abstract,abstract_text,abstracts,summary,摘要;"
          "authors=authors,author,author_names;year=year,pub_year,publication_year,year_published,pubyear;"
          "venue=venue,journal,journal_title,source_title;doi=doi,digital_object_id;url=url,link,source_url;"
          "source_db=source_db,database,db,provider;language=language,lang;pubtype=publication_type,pubtype,study_type;"
          "id=id,record_id,key,uid;query_id=query_id,query,search_id;"
          "retrieved_at=retrieved_at,retrieval_date,date_retrieved").split(";"):
    k, _, vs = g.partition("=")
    for x in vs.split(","):
        A[x] = k
CS = STOP | set(("language english chinese 语种 语言 英文 中文 conference abstract editorial letter comment protocol "
                 "thesis preprint year years 年份 年限").split())


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def rt(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return b.decode(e)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def ct(s):
    """Strip markup, unescape entities, repair UTF-8-as-Latin-1 mojibake, collapse whitespace."""
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<[^>]{1,200}>", " ", s)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        s = s.replace(a, b)
    if re.search(r"[ÃÂâ€]", s):
        c = s.encode("cp1252", "ignore").decode("utf-8", "ignore")
        if (c.count("\ufffd"), c.count("Ã")) < (s.count("\ufffd"), s.count("Ã")):
            s = c
    return ws(s)


def nd(d):
    return re.sub(r"^(doi:|(https?://)?(dx\.)?doi\.org/)", "", (d or "").strip().lower()).strip(" .;")


def nt(t):
    return ws(re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", unicodedata.normalize("NFKD", (t or "").lower())))


def tk(s):
    return [w for w in nt(s).split() if len(w) > 2 and w not in STOP]


def jac(a, b):
    x, y = set(a), set(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def pick(d, f):
    if not isinstance(d, dict):
        return None
    for k, v in d.items():
        if A.get(str(k).lower().strip()) == f and v not in (None, "", [], {}):
            return v
    return None


def isrec(d):
    return isinstance(d, dict) and bool(pick(d, "title") or pick(d, "abstract") or pick(d, "doi"))


def walk(o, out, d=0):
    if d > 6:
        return
    if isinstance(o, dict):
        if isrec(o) and (pick(o, "title") or pick(o, "doi")):
            out.append(o)
            return
        for v in o.values():
            walk(v, out, d + 1)
    elif isinstance(o, list):
        for v in o:
            walk(v, out, d + 1)


def crows(p):
    t = rt(p)
    d = max(";,\t|", key=lambda c: t[:4096].count(c))
    try:
        return list(csv.DictReader(io.StringIO(t), delimiter=d))
    except Exception:
        return []


def collect(root):
    out = []
    if not root or not root.exists():
        return out
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel, e, sub = str(p.relative_to(root)), p.suffix.lower(), []
        try:
            if e == ".json":
                walk(json.loads(rt(p)), sub)
            elif e in (".jsonl", ".ndjson"):
                for ln in rt(p).splitlines():
                    if ln.strip():
                        try:
                            walk(json.loads(ln), sub)
                        except Exception:
                            pass
            elif e in (".csv", ".tsv"):
                sub = [r for r in crows(p) if isrec(r)]
        except Exception:
            pass
        out += [(r, rel) for r in sub]
    return out


def nrec(raw, src, i, db):
    r = {"id": ct(pick(raw, "id")) or f"R{i:04d}", "t": ct(pick(raw, "title")), "ab": ct(pick(raw, "abstract")),
         "au": pick(raw, "authors") or [], "y": None, "v": ct(pick(raw, "venue")), "doi": nd(str(pick(raw, "doi") or "")),
         "u": ct(pick(raw, "url")), "db": ct(pick(raw, "source_db")) or db, "lg": ct(pick(raw, "language")),
         "pt": ct(pick(raw, "pubtype")), "qid": ct(pick(raw, "query_id")), "rat": ct(pick(raw, "retrieved_at")),
         "src": src}
    m = re.search(r"(19|20)\d{2}", str(pick(raw, "year") or ""))
    r["y"] = int(m.group(0)) if m else None
    a = r["au"]
    if isinstance(a, str):
        a = re.split(r"[;,]| and ", a)
    r["au"] = [x.strip() for x in (ct(v if isinstance(v, str) else (v or {}).get("name") or
                                    (v or {}).get("family") or "") for v in (a or [])) if x.strip()][:30]
    low = {str(k).lower(): v for k, v in raw.items()}
    r["gold"] = next((low[g] for g in ("label", "gold", "gold_label", "expected", "included", "is_relevant")
                      if g in low), None)
    return r


def clsc(t):
    s = t.lower()
    if re.search(r"language|语种|语言|english|chinese|英文|中文", s):
        return "language"
    if re.search(r"\b(19|20)\d{2}\b|year|年份|年限|published|before|after|since", s):
        return "year"
    if re.search(r"conference|abstract only|editorial|letter|comment|case report|preprint|thesis|dissertation|"
                 r"protocol|会议|社论|预印本", s):
        return "pubtype"
    return "text"


def cues(t, keep=False):
    w = nt(t).split()
    if keep:
        return list(dict.fromkeys([x for x in w if len(x) > 3]))[:40]
    o = [f"{w[i]} {w[i+1]}" for i in range(len(w) - 1) if len(w[i]) > 2 and w[i] not in CS and w[i + 1] not in CS]
    return list(dict.fromkeys(o + [x for x in w if len(x) > 2 and x not in CS]))[:40]


def bcr(inc, exc):

    c = {"version": "v1", "raw_include": inc, "raw_exclude": exc,
         "include": [{"id": f"INC-{i:02d}", "text": t, "kind": "text", "cues": cues(t)} for i, t in enumerate(inc, 1)],
         "exclude": [{"id": f"EXC-{i:02d}", "text": t, "kind": clsc(t),
                    "cues": cues(t, clsc(t) != "text")} for i, t in enumerate(exc, 1)]}
    c["fingerprint"] = hashlib.sha256(json.dumps([inc, exc], ensure_ascii=False).encode()).hexdigest()[:16]
    return c


def ywin(sc, cr):
    y = sorted({int(x) for x in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)",
                                           json.dumps([sc, cr["raw_include"], cr["raw_exclude"]], default=str))})
    y = [v for v in y if 1900 <= v <= 2100]
    return (y[0], y[-1]) if len(y) > 1 else ((y[0], None) if y else (None, None))


def ddp(rs):

    n = len(rs)
    par, why, near = list(range(n)), {}, []

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def pre(r):
        return bool(re.search(r"arxiv|biorxiv|medrxiv|ssrn|research square|preprint", r["v"].lower() + r["doi"]))

    def comp(r):
        return (len(r["ab"]) > 80) * 3 + bool(r["doi"]) * 2 + bool(r["au"]) + bool(r["v"]) + (not pre(r))

    def sur(r):
        for a in r["au"]:
            p = [x for x in re.split(r"[\s,]+", a.strip()) if x]
            if p:
                return nt(p[-1])[:20]
        return ""

    for i in range(n):
        for j in range(i + 1, n):
            a, b = rs[i], rs[j]
            ta, tb, w = nt(a["t"]), nt(b["t"]), None
            if a["doi"] and a["doi"] == b["doi"] and len(a["doi"]) > 7:
                w = "identical DOI " + a["doi"]
            elif ta and ta == tb and len(ta) > 29:
                w = "identical normalized title"
            elif len(ta) > 24 and len(tb) > 24:
                jt = jac(tk(ta), tk(tb))
                if jt > 0.919 and sur(a) and sur(a) == sur(b) and abs((a["y"] or 0) - (b["y"] or 0)) < 2:
                    w = f"fuzzy title Jaccard {jt:.3f} + same first author + year within 1"
                elif 0.80 <= jt < 0.92:
                    near.append({"a": a["id"], "b": b["id"], "title_jaccard": round(jt, 3), "decision": "not merged",
                                 "why": "below merge threshold or author/year mismatch"})
            if w:
                par[f(j)] = f(i)
                why[(i, j)] = w
    g = {}
    for i in range(n):
        g.setdefault(f(i), []).append(i)
    cl, dup, keep = [], [], set(range(n))
    for idx in g.values():
        if len(idx) < 2:
            continue
        idx = sorted(idx, key=lambda k: -comp(rs[k]))
        bas = sorted({why[(min(i, j), max(i, j))] for i in idx for j in idx if i < j and (min(i, j), max(i, j)) in why})
        cl.append({"cluster_id": f"D{len(cl)+1:03d}", "keeper": rs[idx[0]]["id"], "members": [rs[k]["id"] for k in idx],
                   "basis": bas, "preprint_published_mix": len({pre(rs[k]) for k in idx}) > 1,
                   "source_files": sorted({rs[k]["src"] for k in idx}),
                   "reason_codes": ["DUP-DOI" if any(x.startswith("identical DOI") for x in bas) else "DUP-TITLE"]})
        for k in idx[1:]:
            keep.discard(k)
            dup.append({"removed": rs[k]["id"], "kept": rs[idx[0]]["id"],
                        "basis": next((why[(min(k, j), max(k, j))] for j in idx if j != k and
                                       (min(k, j), max(k, j)) in why), "")})
    return {"clusters": cl, "duplicates_removed": dup, "near_misses_not_merged": near[:40], "keep": sorted(keep)}


def hit(r, cu):

    for f in ("t", "ab"):
        low = ws(r[f]).lower()
        c = next((x for x in cu if x in low), None)
        if not c:
            continue
        t = ws(r[f])
        p = t.lower().find(c)
        s = max(t.rfind(". ", 0, p), t.rfind("; ", 0, p))
        s = 0 if s < 0 else s + 2
        e = [x for x in (t.find(". ", p), t.find("; ", p)) if x > 0]
        e = min(e) + 1 if e else min(len(t), p + 220)
        q = t[s:e].strip()
        qs, qe = s, e
        if c.lower() not in q.lower():
            qs, qe = max(0, p - 90), min(len(t), p + 150)
            q = t[qs:qe].strip()
        return {"field": "title" if f == "t" else "abstract", "cue": c, "quote": q,
                "locator": ("title:" if f == "t" else "abstract:") + f"chars[{qs}:{qe}]"}
    return None


def excs(r, cr, lo, hi):
    o = []
    for c in cr["exclude"]:
        k = c["kind"]
        if k == "year" and lo and r["y"] and (r["y"] < lo or (hi and r["y"] > hi)):
            o.append({"criterion": c["id"], "code": "EXC-YEAR", "field": "metadata", "cue": str(r["y"]),
                      "quote": f"year={r['y']}", "locator": f"metadata:year={r['y']}"})
        elif k == "pubtype":
            b = (r["pt"] + " " + r["v"]).lower()
            cu = next((x for x in c["cues"] if len(x) > 4 and x in b), None)
            if cu:
                o.append({"criterion": c["id"], "code": "EXC-PUBTYPE", "field": "metadata", "cue": cu,
                          "quote": ws((r["pt"] or r["v"])[:120]), "locator": "metadata:publication_type"})
        elif k == "language" and r["lg"] and r["lg"].lower()[:2] not in ("en", "zh"):
            o.append({"criterion": c["id"], "code": "EXC-LANG", "field": "metadata", "cue": r["lg"],
                      "quote": f"language={r['lg']}", "locator": "metadata:language"})
        elif k == "text":
            h = hit(r, c["cues"])
            if h:
                o.append(dict(h, criterion=c["id"], code="EXC-TEXT"))
    return o


def scr(r, cr, lo, hi):
    """A strict (full inclusion coverage) and B lenient (>=50%): rule configurations, not humans."""
    hits, matched = [], []
    for c in cr["include"]:
        h = hit(r, c["cues"]) if c["kind"] == "text" else None
        if h:
            hits.append(dict(h, criterion=c["id"]))
            matched.append(c["id"])
    tot = sum(1 for c in cr["include"] if c["kind"] == "text")
    cov = len(matched) / tot if tot else 0.0
    ex = excs(r, cr, lo, hi)
    he = [e["code"] for e in ex if e["field"] == "metadata"]
    fl = [x for x, cnd in (("NO_TITLE", not r["t"]), ("NO_ABSTRACT", not r["ab"]), ("NO_DOI", not r["doi"]),
                           ("NO_YEAR", not r["y"]), ("LANG_UNKNOWN", not r["lg"])) if cnd]
    sc = round(max(0.0, min(1.0, cov * (0.9 if r["ab"] else 0.55) - 0.35 * len(he) - 0.25 * (len(ex) - len(he)))), 4)
    if ex:
        da = db = "exclude"
        codes = [ex[0]["code"]]
    elif not r["t"]:
        da, db, codes = "uncertain", "uncertain", ["SYS-NO-TITLE"]
    elif not tot:
        da, db, codes = "uncertain", "uncertain", ["SYS-NO-CRIT"]
    elif cov < 0.34:
        da = db = "exclude"
        codes = ["SYS-NO-CRIT-MATCH"]
    else:
        da = "include" if cov > 0.999 else ("exclude" if cov == 0 else "uncertain")
        db = "include" if (cov > 0.499 and matched) else ("exclude" if cov == 0 else "uncertain")
        codes = [("INC-MATCH:" + "+".join(matched)) if da == "include"
                 else ("SYS-NO-CRIT-MATCH" if da == "exclude" else "UNC-PARTIAL-MATCH")]
    conf = round(min(0.95, 0.45 + 0.1 * len(matched) - 0.1 * len(ex)), 2) if (r["ab"] and r["t"]) else 0.35 * bool(r["t"])
    return {"record_id": r["id"], "decision_A": da, "decision_B": db, "include_coverage": round(cov, 3),
            "matched_criteria": matched, "reason_codes": codes, "evidence": hits[:4] + ex[:3], "score": sc,
            "confidence": conf, "flags": fl, "hard_exclusions": he}


def arb(c):
    a, b = c["decision_A"], c["decision_B"]
    if a == b == "uncertain":
        return "pending_human", "unresolved_uncertainty", "both configs uncertain; needs researcher"
    if a == b:
        return a, "agreement", "identical rule configs"
    if c["hard_exclusions"]:
        return "exclude", "hard_exclusion_precedence", "structured exclusion " + c["hard_exclusions"][0]
    if c["include_coverage"] > 0.999 and any(e["field"] != "metadata" for e in c["evidence"]):
        return "include", "full_coverage_with_verbatim_evidence", "all inclusion criteria matched in title/abstract"
    if c["include_coverage"] == 0.0:
        return "exclude", "no_inclusion_criterion_matched", "zero inclusion-criteria coverage"
    return "pending_human", "borderline_unresolved", "partial coverage; needs researcher judgement"


def check(inp, outp):
    """Re-verify a run: contract, case_id, artifacts, verbatim evidence, traceability, counts,
    dedup/label consistency. Returns a report dict; never raises."""
    rep = {"skill_version": V, "checks": [], "status": "ok"}

    def add(n, ok, d=""):
        rep["checks"].append({"check": n, "pass": bool(ok), "detail": str(d)[:300]})
        rep["status"] = rep["status"] if ok else "fail"

    od, rp = Path(outp), Path(outp) / "result.json"
    try:
        res = json.loads(rp.read_text("utf-8"))
    except Exception as e:
        add("result.json parses", False, f"{rp}: {e}")
        return rep
    add("result.json parses", True, f"{rp.stat().st_size} bytes")
    case = {}
    try:
        case = json.loads((Path(inp) / "case.json").read_text("utf-8"))
    except Exception:
        add("case.json readable", False, "absent or unparsable")
    add("case_id preserved", res.get("case_id") == (case.get("case_id") or case.get("caseId") or case.get("id")), res.get("case_id"))
    add("status in enum", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"), res.get("status"))
    for f in ("sources", "uncertainty", "errors", "audit", "counts", "screening"):
        add("has " + f, f in res)
    c = case.get("output_contract") or case.get("outputContract") or {}
    keys = [k if isinstance(k, str) else (k.get("name") or k.get("field")) for k in (c if isinstance(c, list) else list(c))]
    keys = [k for k in keys if k]
    miss = [k for k in keys if k not in res]
    add("output_contract keys backfilled", not miss, f"{len(keys)-len(miss)}/{len(keys)} missing={miss[:8]}")
    src = collect(Path(inp))
    st = {nt(ct(pick(r, "title"))) for r, _ in src}
    sd = {nd(str(pick(r, "doi") or "")) for r, _ in src}
    txt = {ct(pick(r, "id")): (ct(pick(r, "title")), ct(pick(r, "abstract"))) for r, _ in src}
    cands, bad, untr = res.get("candidates") or [], [], []
    for x in cands:
        d = nd(x.get("doi") or "")
        if d and not re.match(r"^10\.\d{4,9}/\S+$", d):
            bad.append(d)
        if src and ((d and d not in sd) or (not d and nt(x.get("title") or "") not in st)):
            untr.append((d or x.get("title") or "")[:60])
    add("candidate DOI well formed", not bad, bad[:4])
    add("candidates traceable to sources", not untr, untr[:4])
    n, fail = 0, []
    for row in res.get("screening") or []:
        for e in (row.get("evidence") or []):
            q, fld = e.get("quote") or "", e.get("field")
            if q and fld in ("title", "abstract"):
                n += 1
                t, ab = txt.get(row.get("record_id"), ("", ""))
                if q not in ((t if fld == "title" else ab) or "") and q not in (t + " " + ab):
                    fail.append(row.get("record_id"))
    add("evidence quotes verbatim in source text", not fail, f"{n-len(fail)}/{n}; {fail[:3]}")
    c2 = res.get("counts") or {}
    add("dedup closure", c2.get("retrieved_total") == c2.get("unique_after_dedup", 0) + c2.get("duplicates_removed", 0), c2)
    add("screening closure", c2.get("screened_total") == c2.get("include", 0) + c2.get("exclude", 0) + c2.get("pending_human", 0), c2)
    fin = {r.get("record_id"): r.get("final") for r in (res.get("screening") or [])}
    inc = {x.get("id") for x in cands}
    add("candidates == included labels", all(fin.get(i) == "include" for i in inc) and
        len(inc) == sum(1 for v in fin.values() if v == "include"), f"{len(inc)} vs {sum(1 for v in fin.values() if v == 'include')}")
    ded = res.get("dedup") or {}
    add("dedup clusters well formed", not [x for x in (ded.get("clusters") or [])
                                           if len(x.get("members") or []) < 2 or x.get("keeper") not in (x.get("members") or [])])
    rem = {d.get("removed") for d in (ded.get("duplicates_removed") or [])}
    add("no removed record in candidates", not (rem & inc), list(rem & inc)[:4])
    add("arbitration rows valid", not [a for a in (res.get("arbitration") or []) if a.get("decision_A") == a.get("decision_B")
                                       or a.get("final") not in ("include", "exclude", "pending_human")])
    art = res.get("artifacts") or {}
    missa = [k for k in art if not (od / str(art[k])).exists()]
    add("declared artifacts exist", not missa, f"{len(art)-len(missa)}/{len(art)} missing={missa}")
    try:
        with open(od / "candidates.csv", encoding="utf-8") as fh:
            nrow = max(0, sum(1 for _ in fh) - 1)
        add("candidates.csv rows == candidates", nrow == len(cands), f"csv={nrow} json={len(cands)}")
    except Exception as e:
        add("candidates.csv readable", False, e)
    rep["summary"] = {"checks": len(rep["checks"]), "passed": sum(1 for x in rep["checks"] if x["pass"]),
                      "failed": [x["check"] for x in rep["checks"] if not x["pass"]]}
    return rep
