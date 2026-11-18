#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parsing + retrieval core for search-01: records -> provenance -> dedupe -> rank -> screen."""
import difflib, json, math, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path

REF_DIR = Path(__file__).resolve().parent.parent / "references"
TITLE = ("title", "Title", "display_name", "article-title", "article_title", "document-title")
DOI = ("DOI", "doi", "Doi", "doi_url")
YEAR = ("year", "publication_year", "pub_year", "pubYear", "publication-date", "published", "issued",
        "publication_date", "date", "pub_date", "firstPublicationDate", "electronicPublicationDate")
ABS = ("abstract", "Abstract", "summary_abstract", "abstractText")
AUTH = ("author", "authors", "authorString", "author_list", "creators", "AU")
VENUE = ("container-title", "journal", "journal_title", "journalTitle", "venue", "book_title",
         "publisher", "source")
URLK = ("URL", "url", "link", "links")
CITE = ("is-referenced-by-count", "cited_by_count", "citedByCount", "citation_count", "times_cited")
KW = ("subject", "keywords", "concepts")
DBK = ("source_db", "database", "source", "provider", "db")
TSK = ("retrieved_at", "retrieved", "fetched_at", "access_date", "date_retrieved", "ts", "timestamp")
EDGE = re.compile(r'"(?:from|source|citing)"\s*:\s*"([^"]{3,120})"\s*,\s*"(?:to|target|cited)"\s*:\s*"([^"]{3,120})"')
DOIRE = re.compile(r"10\.\d{4,9}/[^\s\"'<>),;]+")
STOP = set("a an the of in on for with and or to from by via using based study studies research review "
           "analysis we this that these those is are was were as at into between not its their such can may "
           "also more most than then there which who approach method methods result results effect role new".split())
def nw(x):
    return re.sub(r"\s+", " ", "" if x is None else str(x)).strip()


def norm_doi(d):
    if not isinstance(d, str):
        return None
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d.strip().lower()).strip().rstrip(".,;])") or None


def ascii_fold(t):
    return unicodedata.normalize("NFKD", nw(t)).encode("ascii", "ignore").decode("ascii")


def key_norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", ascii_fold(t).lower())).strip()


def tokens(t):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", ascii_fold(t).lower()) if w not in STOP]


def pick(d, keys):
    if not isinstance(d, dict):
        return None
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        for v in (d.get(k), low.get(str(k).lower())):
            if v not in (None, "", [], {}):
                return v
    return None


def fs(v, lim=4000):
    if v is None:
        return ""
    if isinstance(v, str):
        return nw(v)[:lim]
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return nw(" ; ".join(fs(x, 400) for x in v if fs(x, 60)))[:lim]
    if isinstance(v, dict):
        for k in ("value", "name", "text", "#text", "family", "URL"):
            if k in v:
                return fs(v[k], lim)
        return nw(json.dumps(v, ensure_ascii=False))[:lim]
    return nw(str(v))[:lim]


def has(text, term):
    if not term:
        return False
    if " " in term or "-" in term or "\u4e00" <= term[0] <= "\u9fff":
        return term in text
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def tmatch(text, term):
    """A facet term matches when its content tokens all occur (order-insensitive)."""
    toks = tokens(term)
    if not toks:
        return False
    if len(toks) <= 6:
        return all(has(text, x) for x in toks)
    return sum(1 for x in toks if has(text, x)) >= max(2, int(0.8 * len(toks)))


def _yr(v):
    if isinstance(v, (int, float)):
        return int(v) if 1500 < int(v) < 2200 else None
    if isinstance(v, str):
        m = re.search(r"(1[5-9]\d{2}|20\d{2}|21\d{2})", v)
        return int(m.group(1)) if m else None
    if isinstance(v, list):
        return _yr(v[0]) if v else None
    if isinstance(v, dict):
        for k in ("date-parts", "date_parts", "published", "issued"):
            dp = v.get(k)
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                y = _yr(dp[0][0])
                if y:
                    return y
    return None


def authors_of(rec):
    v, out = pick(rec, AUTH), []
    if isinstance(v, str):
        return [nw(x) for x in re.split(r"[;,]", v) if nw(x)][:40]
    for a in (v if isinstance(v, list) else [])[:60]:
        nm = nw(a) if isinstance(a, str) else ""
        if isinstance(a, dict):
            fam = fs(a.get("family") or a.get("last_name") or a.get("name"), 120)
            giv = fs(a.get("given") or a.get("first_name"), 80)
            nm = nw((fam + " " + giv) if fam else giv)
        if nm:
            out.append(nm)
    return out[:40]


def url_of(rec):
    v = pick(rec, URLK)
    cs = [v] if isinstance(v, str) else (
        [(x.get("URL") or x.get("url")) if isinstance(x, dict) else x for x in v] if isinstance(v, list)
        else ([v.get("URL") or v.get("url")] if isinstance(v, dict) else []))
    for c in cs:
        if isinstance(c, str) and c.startswith("http"):
            return c
    d = norm_doi(pick(rec, DOI))
    return ("https://doi.org/" + d) if d else None


def is_work(d):
    if not isinstance(d, dict):
        return False
    t = pick(d, TITLE)
    if isinstance(t, (list, dict)):
        t = fs(t, 300)
    if not isinstance(t, str) or len(nw(t)) < 4 or re.fullmatch(r"(untitled|unknown|n/?a|null|-+)", nw(t).lower()):
        return False
    low = {str(k).lower() for k in d}
    if not (low & {"doi", "year", "issued", "author", "authors", "container-title", "journal", "venue",
                   "abstract", "pmid", "publication_date", "published"}):
        return False
    return not (low & {"query", "search_terms", "q"} and not (low & {"doi", "authors", "author"}))


def db_from_text(t):
    tl = nw(t).lower()
    for k, v in (("europepmc", "EuropePMC"), ("europe pmc", "EuropePMC"), ("crossref", "Crossref"),
                 ("pubmed", "PubMed"), ("openalex", "OpenAlex"), ("semantic", "SemanticScholar"),
                 ("scopus", "Scopus"), ("arxiv", "arXiv")):
        if k in tl:
            return v
    return None


def env_db_ts(obj):
    if not isinstance(obj, dict):
        return None, None
    db = "Crossref" if isinstance(obj.get("message"), dict) else ("EuropePMC" if "resultList" in obj else None)
    ts = pick(obj, TSK)
    return db or (nw(pick(obj, DBK))[:40] or None), (nw(ts)[:40] if isinstance(ts, (str, int, float)) else None)


def new_corpus():
    return {"works": [], "queries": [], "edges": [], "inventory": [], "unparsed": [],
            "errors": [], "seeds": [], "materials": []}


def add_work(c, rec, ctx):
    try:
        gv = lambda ks, lim=200: nw(fs(pick(rec, ks), lim))
        title = gv(TITLE, 500)
        if len(title) < 4:
            return
        doi = norm_doi(pick(rec, DOI))
        if not doi:
            m = DOIRE.search(fs(rec, 3000))
            doi = norm_doi(m.group(0)) if m else None
        try:
            cb = pick(rec, CITE)
            cb = int(cb) if cb is not None and not isinstance(cb, (list, dict)) else None
        except Exception:
            cb = None
        c["works"].append({
            "title": title, "authors": authors_of(rec),
            "year": next((y for y in (_yr(rec.get(k)) for k in YEAR) if y), None),
            "venue": gv(VENUE) or ((rec.get("primary_location") or {}).get("source") or {}).get("display_name"),
            "doi": doi, "url": url_of(rec), "abstract": gv(ABS, 8000),
            "keywords": gv(KW, 600), "language": gv(("language", "lang"), 20), "cited_by": cb,
            "source_db": gv(DBK, 40) or ctx.get("db") or "provided_corpus",
            "retrieved_at": gv(TSK, 40) or ctx.get("retrieved_at") or ctx.get("mtime"),
            "retrieved_at_source": "record" if gv(TSK, 40) or ctx.get("retrieved_at") else "file_mtime",
            "query_id": ctx.get("query_id"), "query_raw": ctx.get("query_raw"),
            "locator": ctx.get("ptr") or "", "source_file": ctx.get("file") or ""})
    except Exception as exc:
        c["errors"].append({"stage": "record_normalize", "locator": ctx.get("ptr"),
                            "error": "%s: %s" % (type(exc).__name__, str(exc)[:150])})


def walk(obj, ctx, c, depth=0, ptr=""):
    if depth > 14:
        return
    if isinstance(obj, dict):
        if is_work(obj):
            add_work(c, obj, dict(ctx, ptr=(ctx.get("ptr") or "") + ptr))
        if len(obj) <= 8 and (obj.get("from") or obj.get("source")) and (obj.get("to") or obj.get("target")):
            a, b = fs(obj.get("from") or obj.get("source"), 120), fs(obj.get("to") or obj.get("target"), 120)
            c["edges"].append({"from": norm_doi(a) or a, "to": norm_doi(b) or b, "source_file": ctx.get("file")})
        q = pick(obj, ("query", "search_terms", "q", "query_string", "searchString"))
        if isinstance(q, str) and 1 < len(q) < 300:
            h = pick(obj, ("hits", "hitCount", "totalResults", "total", "count"))
            try:
                h = int(h) if h is not None and not isinstance(h, (list, dict)) else None
            except Exception:
                h = None
            qid = "src_" + (re.sub(r"[^a-z0-9]+", "", q.lower())[:24] or "q")
            c["queries"].append({"query_id": qid, "db": ctx.get("db") or db_from_text(ctx.get("file"))
                                 or "provided_corpus", "raw": nw(q), "hits": h,
                                 "source_file": ctx.get("file"), "retrieved_at": ctx.get("retrieved_at"),
                                 "origin": "source_response"})
            ctx = dict(ctx, query_id=qid, query_raw=nw(q))
        for k, v in list(obj.items())[:400]:
            if isinstance(v, (dict, list)):
                walk(v, ctx, c, depth + 1, ptr + "/" + nw(k)[:50])
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3000]):
            if isinstance(v, (dict, list)):
                walk(v, ctx, c, depth + 1, ptr + "/" + str(i))


def _jl(lines):
    out = []
    for line in lines:
        if line.strip()[:1] in ("{", "["):
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def scan(inp, c):
    inp = Path(inp)
    if not inp.exists():
        c["errors"].append({"stage": "scan", "error": "input dir not found: %s" % inp})
        return
    for p in [x for x in sorted(inp.rglob("*")) if x.is_file()][:400]:
        ext, rel = p.suffix.lower(), str(p)
        try:
            st = p.stat()
            size, mtime = st.st_size, datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(
                microsecond=0).isoformat()
        except Exception:
            size, mtime = -1, None
        ctx = {"db": db_from_text(rel), "retrieved_at": None, "query_id": None, "query_raw": None,
               "file": rel, "ptr": "", "mtime": mtime}
        kind = ("json" if ext in (".json", ".jsonl", ".ndjson") else "table" if ext in (".csv", ".tsv")
                else "pdf" if ext == ".pdf" else "text" if ext in (".md", ".txt", ".yaml", ".yml") else "other")
        try:
            if size > 30 * 1024 * 1024:
                c["unparsed"].append({"file": rel, "reason": ">30MB, skipped"})
            elif kind == "json":
                txt = p.read_text(encoding="utf-8", errors="replace")
                objs = []
                if ext == ".json":
                    try:
                        objs = [json.loads(txt)]
                    except Exception:
                        objs = _jl(txt.splitlines())
                else:
                    objs = _jl(txt.splitlines())
                if not objs:
                    c["unparsed"].append({"file": rel, "reason": "json/jsonl not parseable"})
                for i, obj in enumerate(objs[:3000]):
                    db, ts = env_db_ts(obj)
                    walk(obj, dict(ctx, db=ctx["db"] or db, retrieved_at=ts), c, 0,
                         ("/%d" % i) if ext == ".json" else "")
            elif kind == "table":
                c["unparsed"].append({"file": rel, "reason": "tabular file listed but not ingested; "
                                                             "JSON/JSONL record files are the supported "
                                                             "record source"})
            elif kind == "pdf":
                c["unparsed"].append({"file": rel, "reason": "PDF kept as material; full text not parsed "
                                                             "offline, not used as a record source"})
            elif kind == "text":
                t = p.read_text(encoding="utf-8", errors="replace")[:400000]
                for m in EDGE.finditer(t):
                    c["edges"].append({"from": norm_doi(m.group(1)) or m.group(1),
                                       "to": norm_doi(m.group(2)) or m.group(2), "source_file": rel})
                if re.search(r"seed|known[-_ ]?item|must[-_ ]?cite|key[-_ ]?paper", rel, re.I):
                    c["seeds"] += [{"file": rel, "doi": norm_doi(m.group(0))} for m in DOIRE.finditer(t)]
            else:
                c["unparsed"].append({"file": rel, "reason": "unsupported extension %s" % (ext or "none")})
        except Exception as exc:
            c["errors"].append({"stage": "scan", "file": rel,
                                "error": "%s: %s" % (type(exc).__name__, str(exc)[:150])})
            c["unparsed"].append({"file": rel, "reason": "parse error"})
        c["inventory"].append({"file": rel, "ext": ext, "kind": kind, "bytes": size,
                               "mtime": mtime, "db_guess": ctx["db"]})


def dedupe(works):
    """Union-find merge on DOI equality + near-identical normalized titles."""
    par = list(range(len(works)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def uni(a, b):
        if find(a) != find(b):
            par[find(b)] = find(a)

    bd = {}
    for i, w in enumerate(works):
        d = w.get("doi")
        if d and d in bd:
            uni(bd[d], i)
        elif d:
            bd[d] = i
    ks, bl = [key_norm(w["title"]) for w in works], {}
    for i, k in enumerate(ks):
        if k:
            for j in bl.get(k[:24], ()):
                if abs(len(k) - len(ks[j])) <= max(8, int(0.3 * len(k))) and \
                        difflib.SequenceMatcher(None, ks[j], k).ratio() >= 0.93:
                    uni(j, i)
            bl.setdefault(k[:24], []).append(i)
    gs = {}
    for i in range(len(works)):
        gs.setdefault(find(i), []).append(i)
    merged = []
    for g in gs.values():
        ms = [works[i] for i in g]
        m = dict(max(ms, key=lambda w: (len(w["title"]) + len(w["abstract"][:2000]), w.get("year") or 0)))
        for f in ("authors", "year", "venue", "doi", "url", "abstract", "keywords"):
            if not m.get(f):
                m[f] = next((w[f] for w in ms if w.get(f)), None)
        for f in ("title", "abstract", "keywords", "venue"):
            m[f] = m.get(f) or ""
        m["sources"] = sorted({w["source_db"] for w in ms if w.get("source_db")})
        m["n_records"], m["query_ids"] = len(ms), sorted({w["query_id"] for w in ms if w.get("query_id")})
        m["provenance"] = [{k: w[k] for k in ("source_db", "query_id", "retrieved_at")} |
                           {"file": w["source_file"], "locator": w["locator"]} for w in ms][:6]
        yrs = sorted({w["year"] for w in ms if w.get("year")})
        if len(yrs) > 1:
            m["conflict_year"] = yrs
        merged.append(m)
    return merged, len(works) - len(merged)


def rank(merged, facets):
    """IDF-weighted facet coverage; score=.55 facet+.20 recency+.10 cites+.15 title (see schema.md)."""
    N = len(merged) or 1
    df = {}
    for w in merged:
        for tok in set(tokens(w["title"] + " " + w["keywords"] + " " + w["abstract"][:4000])):
            df[tok] = df.get(tok, 0) + 1
    idf = lambda x: math.log(1 + (N + 0.5) / (df.get(x, 0) + 0.5))
    fw = [sum(idf(t) for t in f["terms"]) / max(1, len(f["terms"])) for f in facets]
    tw = sum(fw) or 1.0
    yrs = [w["year"] for w in merged if w.get("year")]
    ymax, maxc = (max(yrs) if yrs else None), max([w.get("cited_by") or 0 for w in merged] + [0])
    out = []
    for w in merged:
        text = (w["title"] + " " + w["keywords"] + " " + w["abstract"]).lower()
        title = w["title"].lower()
        mt, miss, ht, fsc, in_title = [], [], [], 0.0, 0
        for f, weight in zip(facets, fw):
            hit = [x for x in f["terms"] if has(text, x)]
            if hit:
                mt.append(f["label"])
                ht.extend(hit[:3])
                fsc += weight * (0.7 + 0.3 * min(1.0, len(hit) / 3.0))
                in_title += 1 if any(has(title, x) for x in hit) else 0
            else:
                miss.append(f["label"])
        cov = len(mt) / max(1, len(facets))
        rec = max(0.0, min(1.0, (w["year"] - (ymax - 12)) / 12.0)) if (ymax and w.get("year")) else 0.0
        cit = (math.log1p(w.get("cited_by") or 0) / math.log1p(maxc)) if maxc else 0.0
        sc = (0.55 * fsc / tw + 0.20 * rec + 0.10 * cit + 0.15 * in_title / max(1, len(facets))
              - (0.0 if w.get("doi") else 0.03))
        w = dict(w)
        w.update({"matched_facets": mt, "missing_facets": miss, "coverage": round(cov, 3),
                  "matched_terms": sorted({x for x in ht})[:10],
                  "relevance_score": round(100 * max(0.0, sc), 1)})
        out.append(w)
    out.sort(key=lambda w: (-w["relevance_score"], -(w.get("year") or 0), w["title"].lower()))
    return out


def screen(ranked, scope, k):
    kept, excl = [], []
    for w in ranked:
        r, y = [], w.get("year")
        blob = (w["title"] + " " + w["abstract"]).lower()
        if scope["year_from"] and y and y < scope["year_from"]:
            r.append("year %s < %s" % (y, scope["year_from"]))
        if scope["year_to"] and y and y > scope["year_to"]:
            r.append("year %s > %s" % (y, scope["year_to"]))
        r += ["exclude term '%s'" % x for x in scope["exclude_terms"] if has(blob, x.lower())]
        if scope["languages"] and w.get("language") and \
                w["language"].lower()[:2] not in {x.lower()[:2] for x in scope["languages"]}:
            r.append("language %s outside scope" % w["language"])
        if scope["databases"] and w.get("sources") and \
                not ({x.lower() for x in w["sources"]} & {x.lower() for x in scope["databases"]}):
            r.append("source outside scope db")
        if w["coverage"] <= 0.0:
            r.append("no facet term match")
        if r:
            excl.append({"title": w["title"], "doi": w.get("doi"),
                         "relevance_score": w.get("relevance_score"), "reason": "; ".join(r)})
        else:
            kept.append(w)
    return kept[:k], excl


def load_lexicon():
    """references/terms.md -> (facet groups, cn->en map)."""
    groups, cn = [], {}
    try:
        for line in (REF_DIR / "terms.md").read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            lab, rhs = line.split("|", 1)
            terms = [t.strip() for t in re.split(r"[;,]", rhs) if t.strip()]
            if lab.strip().lower() in ("cn2en", "zh2en"):
                cn.update({t.split("=", 1)[0].strip(): t.split("=", 1)[1].strip()
                           for t in terms if "=" in t})
            else:
                groups.append({"label": lab.strip().lower(), "terms": [t.lower() for t in terms]})
    except Exception:
        pass
    return groups, cn
