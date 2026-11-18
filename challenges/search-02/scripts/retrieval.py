#!/usr/bin/env python3
"""search-02 retrieval engine: scan, normalise, decompose, BM25 retrieve, dedupe, screen."""
import csv, json, math, os, re, time
from pathlib import Path

V, T0, MAXR, H = "1.0.0", time.time(), 4000, Path(__file__).resolve().parent
AL = {"t": ("title", "paper_title", "name", "标题"), "a": ("authors", "author", "作者"),
      "y": ("year", "pub_year", "publication_year", "date"), "v": ("venue", "journal", "conference", "期刊"),
      "d": ("doi", "dois"), "u": ("url", "link", "href"), "ab": ("abstract", "summary", "摘要"),
      "k": ("keywords", "terms", "mesh"), "s": ("source_db", "database", "db", "provider"),
      "r": ("id", "paper_id", "record_id", "doc_id")}
STOP = set("""a an the of and or for in on at to with without by from as is are was were been this that
these those we our it its into between among across via use can may might should not no than then thus
also more most less such other both each any all some new novel study studies paper papers result results
approach approaches method methods based data analysis analyses report reports show shows find found
work works""".split())
CJK = re.compile(r"[\u4e00-\u9fff]")
TOK = re.compile(r"[0-9a-zA-Z]+(?:[-'\u2019][0-9a-zA-Z]+)*|[\u4e00-\u9fff]+")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def cl(s, n=300):
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()[:n].rstrip()

def wj(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(t, p)

def wt(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")

def lj(p):
    try:
        t = Path(p).read_text("utf-8", "replace").lstrip("\ufeff")
    except Exception:
        return None, "unreadable"
    try:
        return json.loads(t), None
    except Exception as e:
        err = str(e)[:70]
    r = []
    for l in t.splitlines():
        try:
            r.append(json.loads(l.strip().rstrip(",")))
        except Exception:
            pass
    return (r, "jsonl") if len(r) > 1 else (None, err)

def pk(d, ns):
    if not isinstance(d, dict):
        return None
    lo = {str(k).lower(): k for k in d}
    for n in ns:
        if lo.get(n) and d[lo[n]] not in (None, "", [], {}):
            return d[lo[n]]
    return None

def lex():
    L = {"f": {}, "s": {}, "p": [], "n": []}
    try:
        txt = (H.parent / "references" / "lexicon.md").read_text(encoding="utf-8")
    except Exception:
        return L, False
    k = v = ""
    for s in txt.splitlines():
        s = s.strip()
        if s.startswith("##"):
            h = [x.strip().lower() for x in s[2:].split(":", 1)]; k, v = h[0], (h[1] if len(h) > 1 else "")
        elif s and k == "facet" and v:
            L["f"][v] = [c.strip() for c in s.split("|") if c.strip()]
        elif s and k == "syn" and "=>" in s:
            x, y = s.split("=>", 1); L["s"][x.strip().lower()] = [c.strip() for c in y.split("|") if c.strip()]
        elif s and k == "polarity" and v in ("pos", "neg"):
            L["p" if v == "pos" else "n"] = [c.strip() for c in s.split("|") if c.strip()]
    return L, bool(L["f"])

def ndoi(s):
    m = re.search(r"10\.\d{4,9}/[^\s\"'<>]+", str(s or ""))
    return m.group(0).lower().rstrip(".,;)/") if m else None

def tyear(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return v if 1500 <= v <= 2100 else None
    m = re.search(r"(1[5-9]\d\d|20\d\d|2100)", str(v or ""))
    return int(m.group(1)) if m else None

def tk(s):
    o = []
    for m in TOK.finditer(str(s or "").lower()):
        w = m.group(0)
        if CJK.match(w):
            o += [w] if len(w) == 1 else [w[i:i + 2] for i in range(len(w) - 1)]
            continue
        for p in w.split("-") if "-" in w else [w]:
            if len(p) > 1 and p not in STOP and not p.isdigit():
                o.append(p[:-1] if len(p) > 3 and p.endswith("s") and not p.endswith(("ss", "us")) else p)
    return o

def auth(v):
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"\s*[;\u3001]|\band\b", v) if x.strip()][:30]
    return [str(a if isinstance(a, str) else pk(a, ("name", "full_name")) or "").strip()
            for a in (v if isinstance(v, list) else []) if a][:30]


def to_rec(raw, f, ptr, n, src=None):
    if not isinstance(raw, dict):
        return None
    d = raw
    for w in ("paper", "metadata", "work"):
        if isinstance(d.get(w), dict):
            b = dict(d[w]); [b.setdefault(k, v) for k, v in d.items()]; d = b
    doi = ndoi(pk(d, AL["d"]))
    if not pk(d, AL["t"]) and not doi:
        return None
    kw = pk(d, AL["k"])
    kw = [x.strip() for x in re.split(r"[;,]", kw) if x.strip()] if isinstance(kw, str) else kw
    rid = pk(d, AL["r"])
    return {"rid": str(rid) if isinstance(rid, (str, int)) and str(rid).strip() else "r%04d" % n,
            "title": cl(pk(d, AL["t"]), 400) or None, "authors": auth(pk(d, AL["a"])),
            "year": tyear(pk(d, AL["y"])), "venue": cl(pk(d, AL["v"]), 200) or None, "doi": doi,
            "url": cl(pk(d, AL["u"]), 300) or None, "abstract": cl(pk(d, AL["ab"]), 4000) or None,
            "keywords": [str(x) for x in kw][:20] if isinstance(kw, list) else [],
            "src": cl(pk(d, AL["s"]) or src or "", 60) or None, "file": f, "ptr": ptr}

def harvest(o, f, ptr, h, dep=0):
    if dep > 10 or len(h["r"]) > MAXR:
        return
    if isinstance(o, list):
        for i, it in enumerate(o[:MAXR]):
            harvest(it, f, "%s/%d" % (ptr, i), h, dep + 1)
        return
    if not isinstance(o, dict):
        return
    if (pk(o, AL["t"]) or pk(o, AL["d"])) and not isinstance(o.get("results"), list):
        r = to_rec(o, f, ptr, len(h["r"]) + 1)
        if r:
            h["r"].append(r)
        return
    for k, v in o.items():
        if isinstance(v, (dict, list)) and "contract" not in str(k).lower():
            harvest(v, f, "%s/%s" % (ptr, k), h, dep + 1)


def scan(inp):
    h = {"r": [], "files": [], "notes": []}
    if not inp.exists():
        h["notes"].append("input directory missing: %s" % inp)
        return h
    for p in sorted(inp.rglob("*")):
        rel = str(p.relative_to(inp))
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in (".json", ".jsonl", ".csv") \
                or re.search(r"(case|config|schema|contract)", p.name, re.I):
            continue
        h["files"].append({"path": rel, "bytes": p.stat().st_size})
        try:
            if p.suffix.lower() == ".csv":
                with p.open(encoding="utf-8", errors="replace", newline="") as fh:
                    for i, row in enumerate(list(csv.DictReader(fh))[:MAXR]):
                        r = to_rec(row, rel, "/%d" % i, len(h["r"]) + 1)
                        if r:
                            h["r"].append(r)
            else:
                o, err = lj(p)
                if err and err != "jsonl":
                    h["notes"].append("parse issue %s: %s" % (rel, err))
                if o is not None:
                    harvest(o, rel, "", h)
        except Exception as e:
            h["notes"].append("harvest failed %s: %s" % (rel, str(e)[:70]))
    return h


def q_of(case, md):
    for k in ("task_instruction", "research_question", "question", "task", "instruction"):
        if isinstance(case.get(k), str) and len(case[k].strip()) > 10:
            return case[k].strip(), k
    sc = case.get("organizer_supplied_scope") or case.get("scope") or {}
    for k in ("research_question", "question", "topic", "objective"):
        if isinstance(sc.get(k), str) and len(sc[k].strip()) > 5:
            return sc[k].strip(), "scope." + k
    m = re.search(r"(?:^|\n)#+\s*(?:研究问题|Research question)[^\n]*\n+(.+?)(?=\n#|\Z)", md or "", re.S | re.I)
    return (cl(m.group(1), 800), "task.md") if m else ("", None)

def scope_of(case, q, years):
    """Year window / language / max_k / include-exclude from any scope block or the question."""
    sc = {}
    for k in ("organizer_supplied_scope", "scope", "constraints", "search_scope"):
        if isinstance(case.get(k), dict):
            sc.update(case[k])
    o = {"y0": None, "y1": None, "lang": str(sc.get("lang") or "").lower() or None, "max_k": None,
         "inc": [], "exc": [], "dbs": [], "src": []}
    y = sc.get("years") or sc.get("year_range")
    nums = [int(x) for x in re.findall(r"(1[5-9]\d\d|20\d\d)", y)] if isinstance(y, str) else []
    if isinstance(y, (list, tuple)) and len(y) > 1:
        o["y0"], o["y1"] = tyear(y[0]), tyear(y[1])
    elif len(nums) > 1:
        o["y0"], o["y1"] = nums[0], nums[1]
    if o["y0"]:
        o["src"].append("scope.years")
    else:
        g = re.search(r"(1[89]\d\d|20\d\d)\s*(?:-|\u2013|to)\s*(1[89]\d\d|20\d\d)", q or "")
        if g:
            o["y0"], o["y1"] = int(g.group(1)), int(g.group(2))
            o["src"].append("question_text")
    for k in ("max_k", "top_k", "max_results"):
        if str(sc.get(k, "")).isdigit():
            o["max_k"] = int(sc[k])
            break
    for key, tgt in (("include", "inc"), ("exclude", "exc")):
        v = sc.get(key)
        o[tgt] = [v] if isinstance(v, str) else [str(x) for x in v] if isinstance(v, list) else []
    v = sc.get("dbs") or sc.get("databases")
    o["dbs"] = [v] if isinstance(v, str) else [str(x) for x in v] if isinstance(v, list) else []
    return o


def facets(q):
    ql, g = (q or "").lower(), {}
    for name, cues in FAC.items():
        hit = [c for c in cues if c.lower() in ql]
        if hit:
            alt = set()
            for c in hit:
                for e in [c] + SYN.get(c.lower(), []):
                    alt |= {x for x in tk(e) if len(x) > 2}
            g[name] = {"cues": hit[:6], "terms": sorted(alt)[:14]}
    return g

def anchors(q, fg):
    cand = re.findall(r"[\"'\u201c]([^\"'\u201d]{3,60})[\"'\u201d]", q or "") + re.findall(
        r"[A-Za-z][A-Za-z0-9\-]{2,}(?:[ ][A-Za-z][A-Za-z0-9\-]{2,}){0,3}", q or "")
    ban = {x for g in fg.values() for c in g["cues"] for x in tk(c)}
    out, seen = [], set()
    for c in cand:
        ts = [x for x in tk(c) if x not in STOP]
        key = " ".join(ts)
        if 2 <= len(ts) <= 5 and len(key) >= 4 and key not in seen:
            seen.add(key); out.append({"phrase": cl(c, 80), "terms": ts, "f": all(x in ban for x in ts)})
    out.sort(key=lambda x: (x["f"], -len(x["terms"])))
    return [x for x in out if not x["f"]][:4] or out[:2]

def expand(terms, lim=12):
    alt = set()
    for t in terms:
        alt.add(t); alt |= set(tk(t))
        for k, vs in SYN.items():
            if t in tk(k) or any(t in tk(v) for v in vs):
                alt |= set(tk(k))
                for v in vs:
                    alt |= set(tk(v))
    return sorted({a for a in alt if len(a) > 1})[:lim]

def decompose(q, fg, anc):
    subs, lab = [], {"method": "methods/design", "mechanism": "mechanism or pathway",
                     "outcome": "outcome/efficacy", "comparison": "comparative performance",
                     "gap": "limitations or conflicting results"}

    def add(f, why, wave):
        gs = [{"role": "anchor", "label": "topic", "min_hits": 1,
               "terms": expand([x for a in anc[:3] for x in a["terms"]], 16)}] if anc else []
        if f in fg:
            gs.append({"role": "facet", "label": f, "terms": expand(fg[f]["terms"]), "min_hits": 1})
        subs.append({"sub_question_id": "sq%02d" % (len(subs) + 1), "facet": f or "core",
                     "question": "Which records cover %s for: %s?" % (
                         lab.get(f, "the core topic"), "; ".join(a["phrase"] for a in anc[:2]) or cl(q, 80)),
                     "groups": gs, "wave": wave, "derived_from": cl(why, 180), "evidence_target": 1,
                     "status": "pending", "evidence_ids": [], "query_ids": []})
    add(None, q, 1)
    for f in [x for x in ("method", "mechanism", "outcome", "comparison", "gap") if x in fg]:
        add(f, fg[f]["cues"][0], 2 if f in ("method", "mechanism") else 3)
    if CJK.search(q or "") and anc:
        add(None, "cross-language variant", 1)
    return subs[:6]

def build_index(cls_):
    docs = []
    for c in cls_:
        r, tf = c["cand"], {}
        for seq, w in ((tk(r.get("title")), 3.0), (tk(r.get("abstract")), 1.0),
                       (tk(" ".join(r.get("keywords") or [])), 2.0), (tk(r.get("venue")), .5),
                       (tk(" ".join(r.get("authors") or [])), .3)):
            for x in seq:
                tf[x] = tf.get(x, 0.0) + w
        docs.append({"cid": c["cid"], "tf": tf, "len": sum(tf.values()) or 1.0})
    df = {}
    for d in docs:
        for t in d["tf"]:
            df[t] = df.get(t, 0) + 1
    n = max(len(docs), 1)
    return {"docs": {d["cid"]: d for d in docs}, "avg": sum(d["len"] for d in docs) / n if docs else 1.0,
            "idf": {t: math.log(1 + (n - c + .5) / (c + .5)) for t, c in df.items()}}

def score(ix, doc, groups):
    tot, mt, ok = 0.0, [], True
    for g in groups:
        best, bw = 0.0, None
        for t in g["terms"]:
            tf = doc["tf"].get(t)
            if tf:
                v = ix["idf"].get(t, .5) * tf * 2.2 / (tf + 1.2 * (.25 + .75 * doc["len"] / ix["avg"]))
                if v > best:
                    best, bw = v, t
        if bw:
            mt.append({"group": g["label"], "term": bw}); tot += best
        else:
            ok = False
    return {"score": tot, "matched": mt, "ok": ok}

def execute(ix, subs, cls_, sc, budget, qlog, seen):
    wst = {}
    for s in sorted(subs, key=lambda x: (x["wave"], x["sub_question_id"]))[:budget]:
        qid, ts, hits, kept = "q%02d" % (len(qlog) + 1), now(), 0, []
        mh = max([g["min_hits"] for g in s["groups"] if g["role"] == "anchor"] or [1])
        for c in cls_:
            r, doc = c["cand"], ix["docs"][c["cid"]]
            if (sc["y0"] and r.get("year") and r["year"] < sc["y0"]) or \
                    (sc["y1"] and r.get("year") and r["year"] > sc["y1"]):
                continue
            res = score(ix, doc, s["groups"])
            if res["ok"] and res["score"] > 0 and len([m for m in res["matched"] if m["group"] == "topic"]) >= mh:
                hits += 1; kept.append((res["score"], c["cid"]))
                pr = seen.setdefault(c["cid"], {"sqs": []})
                pr["sqs"].append(s["sub_question_id"])
                if res["score"] > pr.get("score", 0):
                    pr.update({"score": res["score"], "sq": s["sub_question_id"], "q": qid,
                               "matched": res["matched"], "ts": ts})
        kept.sort(reverse=True)
        qlog.append({"query_id": qid, "sub_question_id": s["sub_question_id"], "wave": s["wave"],
                     "db": (sc["dbs"] or ["local_snapshot"])[0],
                     "raw": cl(" AND ".join("(%s)" % " OR ".join(g["terms"][:6]) for g in s["groups"]), 600),
                     "expanded_terms": sorted({t for g in s["groups"] for t in g["terms"]})[:40],
                     "filters": {"year_from": sc["y0"], "year_to": sc["y1"], "lang": sc["lang"]},
                     "hits": hits, "returned_ids": [k[1] for k in kept[:40]], "mode": "snapshot_lexical",
                     "status": "ok" if hits else "empty", "error": None, "retrieved_at": ts})
        s["status"], s["evidence_ids"] = ("covered" if hits else "empty"), [k[1] for k in kept[:5]]
        s["query_ids"].append(qid)
        w = wst.setdefault(str(s["wave"]), {"queries": 0, "hits": 0})
        w["queries"] += 1; w["hits"] += hits
    return wst

def ntitle(t):
    return " ".join(re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", (t or "").lower()).split())

def dedupe(rec):
    """Merge records sharing a DOI, an identical normalised title, or >90% title tokens."""
    par = list(range(len(rec)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x

    def uni(a, b):
        if find(a) != find(b):
            par[max(find(a), find(b))] = min(find(a), find(b))
    bd, bt, bb = {}, {}, {}
    for i, r in enumerate(rec):
        if r.get("doi"):
            bd.setdefault(r["doi"], []).append(i)
        t = ntitle(r.get("title"))
        if t:
            bt.setdefault(t, []).append(i); bb.setdefault(t.split()[0], []).append(i)
    for mp in (bd, bt):
        for ids in mp.values():
            for j in ids[1:]:
                uni(ids[0], j)
    for ids in bb.values():
        for a, i in enumerate(ids[:60]):
            for j in ids[a + 1:]:
                ti, tj = set(ntitle(rec[i]["title"]).split()), set(ntitle(rec[j]["title"]).split())
                if find(i) != find(j) and ti and tj and len(ti & tj) / len(ti | tj) >= .9:
                    uni(i, j)
    gp = {}
    for i in range(len(rec)):
        gp.setdefault(find(i), []).append(i)
    out = []
    for k, (_, ids) in enumerate(sorted(gp.items(), key=lambda kv: min(kv[1]))):
        mem = [rec[i] for i in ids]
        cand = dict(max(mem, key=lambda r: sum(1 for f in ("doi", "abstract", "authors", "venue", "year") if r.get(f))
                        * 100 + len(r.get("abstract") or "")))
        for m in mem:
            for f in ("title", "abstract", "year", "venue", "doi", "url"):
                if not cand.get(f) and m.get(f):
                    cand[f] = m[f]
        out.append({"cid": "c%03d" % (k + 1), "cand": cand, "dup": len(mem) - 1,
                    "members": [{"record_id": m["rid"], "source_db": m.get("src"), "doi": m.get("doi"),
                                 "title": cl(m.get("title"), 140), "year": m.get("year"), "file": m.get("file"),
                                 "pointer": m.get("ptr")} for m in mem],
                    "sources": sorted({str(m.get("src")) for m in mem if m.get("src")})})
    return out

def screen(r, sc):
    why, flags, keep = [], [], True
    y = r.get("year")
    if sc["y0"] and y and y < sc["y0"]:
        keep = False; why.append("year %s < %s" % (y, sc["y0"]))
    if sc["y1"] and y and y > sc["y1"]:
        keep = False; why.append("year %s > %s" % (y, sc["y1"]))
    if y is None:
        flags.append("year_unknown")
    blob = ("%s %s %s" % (r.get("title") or "", r.get("venue") or "", r.get("abstract") or "")).lower()
    for t in sc["exc"]:
        if t and str(t).lower() in blob:
            keep = False; why.append("excluded term: %s" % cl(t, 40))
    for p in ("corrigendum", "erratum", "retraction", "retracted", "comment on", "editorial"):
        if p in (r.get("title") or "").lower():
            keep = False; why.append("non-research item (%s)" % p); flags.append("non_research_item"); break
    if sc["inc"]:
        if any(str(t).lower() in blob for t in sc["inc"] if t):
            why.append("include criterion matched")
        else:
            keep = False; why.append("no include criterion matched")
    if not r.get("abstract"):
        flags.append("no_abstract")
    if not r.get("doi"):
        flags.append("no_doi")
    return {"keep": keep, "reasons": why or ["within scope; no exclusion triggered"], "flags": flags}

def snip(r, terms):
    ab = r.get("abstract")
    if not ab:
        return (cl(r.get("title"), 280), "title") if r.get("title") else (None, None)
    ss = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", ab)
    for i, s in enumerate(ss):
        if any(t in s.lower() for t in terms):
            return cl(s, 280), "abstract:sent%d" % (i + 1)
    return cl(ss[0], 280), "abstract:sent1"

LX, LEX_OK = lex()
FAC = LX["f"] or {"method": ["randomized", "cohort"], "outcome": ["efficacy", "accuracy"]}
SYN, POS, NEG = LX["s"], LX["p"] or ["improve", "effective"], LX["n"] or ["no significant", "failed"]
