#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multidb-literature-search -- offline multi-database literature search engine.

Pipeline: discover -> contract -> query plan -> harvest -> cross-DB field map ->
dedup (identifier / title / fuzzy+guards) -> merge (field authority) ->
relevance + screening -> coverage & baseline -> evidence -> contract fill ->
self check -> finalize.

Guarantees: writes a valid partial result.json first, always finalizes, always
exits 0, stdlib only, no network, no dependence on the working directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

VER = "1.0.0"
T0 = time.time()
HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"

CFIELDS = ["title", "authors", "year", "venue", "volume", "issue", "pages", "doi",
           "pmid", "pmcid", "arxiv", "url", "type", "publisher", "abstract",
           "language", "citation_count", "is_retracted"]
CANON = {
    "candidates": ["candidate", "candidates", "results", "result", "papers", "paper",
                   "records", "record", "documents", "literature", "corpus", "articles",
                   "items", "candidate_list", "retrieved_papers", "bibliography"],
    "queries": ["queries", "query", "query_log", "search_log", "searches", "requests",
                "query_plan", "search_strategy"],
    "screening": ["screening", "filter", "filters", "inclusion", "selection", "decisions",
                  "screening_log", "relevance_screening"],
    "coverage": ["coverage", "gap", "gaps", "coverage_report", "recall", "completeness"],
    "sources": ["sources", "source", "databases", "dbs", "sources_used", "provenance_sources"],
    "uncertainty": ["uncertainty", "uncertainties", "limitations", "risks", "caveats"],
    "errors": ["errors", "error", "issues", "failures"],
    "pending_human": ["pending_human", "human_review", "needs_review", "pending", "arbitration"],
    "degradations": ["degradations", "degraded", "fallbacks", "degradation"],
    "changes": ["changes", "change_log", "changelog", "log"],
    "runtime": ["runtime", "meta", "metrics_run", "run_info", "execution"],
    "evidence": ["evidence", "evidence_log", "provenance", "trace", "audit"],
    "status": ["status", "run_status"],
    "metrics": ["metrics", "scores", "evaluation", "benchmark"],
    "clusters": ["clusters", "cluster", "merge", "merges", "dedup", "deduplication", "groups"],
    "conflicts": ["conflicts", "conflict"],
    "citations": ["citations", "citation_list", "references"],
}
SYN = {
    "title": ["title", "display_name", "displayname", "article_title", "articletitle",
              "titles", "primary_title", "paper_title", "document_title", "heading", "name"],
    "abstract": ["abstract", "abstracttext", "abstract_text", "summary", "description"],
    "doi": ["doi", "DOI", "digital_object_identifier", "doi_url"],
    "year": ["year", "publication_year", "publicationyear", "pubyear", "pub_year", "issued",
             "published", "published_year", "date", "publication_date", "firstpublicationdate"],
    "venue": ["venue", "journal", "journaltitle", "journal_title", "container_title",
              "containertitle", "publicationtitle", "journal_name", "fulljournalname",
              "source_title", "publication"],
    "authors": ["authors", "author", "authorname", "authorstring", "authorships", "creators",
                "contributors", "authorlist"],
    "volume": ["volume", "journalvolume", "journal_volume"],
    "issue": ["issue", "journalissue", "journal_issue"],
    "pages": ["pages", "page", "pageinfo", "page_info", "pagination", "first_page"],
    "type": ["type", "publicationtype", "publication_type", "pubtype", "doctype",
             "document_type", "genre", "publicationtypes"],
    "publisher": ["publisher", "publisher_name", "institution"],
    "url": ["url", "link", "links", "fulltexturl", "full_text_url", "landing_page_url", "href"],
    "pmid": ["pmid", "pubmed_id", "pubmedid"],
    "pmcid": ["pmcid", "pmc_id", "pmcid_full"],
    "arxiv": ["arxiv", "arxiv_id", "arxivid"],
    "language": ["language", "lang"],
    "citation_count": ["citation_count", "citedbycount", "cited_by_count", "citationcount",
                       "is_referenced_by_count"],
    "is_retracted": ["is_retracted", "isretracted", "retracted", "retraction"],
}
CONTAINERS = {"externalids", "external_ids", "ids", "identifiers", "identifier", "articleids",
              "article_ids", "metadata", "bib", "bibliographic", "item", "record", "attributes",
              "properties", "primary_location", "location", "journalinfo", "journal"}
STOP = set("the a an of and or in on for to with by from at as is are be been being this that "
           "these those we our us study studies result results using used based via under "
           "between among into not no than then which whose what how can could may might will "
           "would should all any each more most other some such only also its their there here "
           "was were has have had do does did but if when where while about over out up down "
           "new novel approach method methods paper article review analysis".split())


# ----------------------------------------------------------------- utilities
def iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t if t else time.time()))


def esc(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def read_text(p):
    try:
        b = Path(p).read_bytes()
    except OSError:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", "replace")


def jread(p):
    t = read_text(p).lstrip("\ufeff")
    if not t.strip():
        return None
    try:
        return json.loads(t)
    except ValueError:
        recs = []
        for line in t.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except ValueError:
                pass
        return {"__records__": recs, "__jsonl__": True} if recs else None


def fix_text(s):
    """Strip markup/entities, repair mojibake, collapse whitespace."""
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    s = re.sub(r"<[^<>]{0,600}>", " ", s)
    s = html.unescape(s)
    if any(m in s for m in ("\u00c3", "\u00e2\u0080", "\u00ef\u00bf\u00bd")):
        try:
            alt = s.encode("latin-1", "strict").decode("utf-8", "strict")
            if alt and alt != s:
                s = alt
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    s = s.replace("\ufffd", " ")
    return re.sub(r"\s+", " ", s).strip()


def scalar(v, depth=0):
    if depth > 6:
        return None
    if isinstance(v, (list, tuple)):
        for x in v:
            r = scalar(x, depth + 1)
            if r not in (None, ""):
                return r
        return None
    if isinstance(v, dict):
        for k in ("value", "name", "text", "@value", "date-parts", "display_name", "title"):
            if k in v:
                r = scalar(v[k], depth + 1)
                if r not in (None, ""):
                    return r
        if len(v) == 1:
            return scalar(list(v.values())[0], depth + 1)
        return None
    if isinstance(v, bool):
        return v
    return v


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")


def ndoi(v):
    s = fix_text(str(v)) if v else ""
    if not s:
        return None
    s = re.sub(r"^(https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s.strip().lower())
    m = DOI_RE.search(s)
    return m.group(0).rstrip(".,;:)]}\u3002") if m else None


def nid(v, kind):
    s = scalar(v)
    if s in (None, ""):
        return None
    s = str(s).strip()
    if kind == "pmid":
        m = re.search(r"\b(\d{4,9})\b", s)
        return m.group(1) if m else None
    if kind == "pmcid":
        m = re.search(r"(PMC\s?\d{4,9})", s, re.I)
        return re.sub(r"\s", "", m.group(1)).upper() if m else None
    if kind == "arxiv":
        m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s) or re.search(r"([a-z\-]+/\d{7})(v\d+)?", s)
        return m.group(1) if m else None
    return s or None


def nyear(v):
    if isinstance(v, (int, float)) and 1500 < float(v) < 2200:
        return int(v)
    s = str(v or "")
    m = re.search(r"(1[6-9]\d{2}|20\d{2}|21\d{2})", s)
    return int(m.group(1)) if m else None


def ntitle(s):
    s = unicodedata.normalize("NFKD", fix_text(s) or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def nauthors(v):
    out = []

    def add(x):
        if isinstance(x, dict) and isinstance(x.get("author"), dict) and len(x) < 4:
            add(x["author"])
            return
        if isinstance(x, dict):
            fam = scalar(x.get("family") or x.get("familyName") or x.get("last_name")
                         or x.get("surname") or x.get("lastname"))
            giv = scalar(x.get("given") or x.get("givenName") or x.get("first_name")
                         or x.get("forename") or x.get("firstname"))
            nm = scalar(x.get("name") or x.get("display_name") or x.get("literal")
                        or x.get("full_name") or x.get("author_name"))
            if fam or giv:
                fam = fix_text(fam) if fam else None
                giv = fix_text(giv) if giv else None
                out.append({"family": fam, "given": giv,
                            "name": fix_text(" ".join([p for p in (giv, fam) if p]))})
            elif nm:
                nm = fix_text(str(nm))
                m = re.match(r"^(.*\S)\s+([A-Z][A-Za-z]?\.?)$", nm)
                if m:
                    out.append({"family": m.group(1), "given": m.group(2), "name": nm})
                else:
                    out.append({"family": None, "given": None, "name": nm})
        elif isinstance(x, str):
            for part in re.split(r"\s*[;|]\s*|\s+and\s+", fix_text(x) or ""):
                part = part.strip(" .,")
                if not part:
                    continue
                if "," in part:
                    fam, giv = part.split(",", 1)
                    out.append({"family": fam.strip(), "given": giv.strip() or None,
                                "name": part})
                else:
                    toks = part.split()
                    if len(toks) >= 2 and re.fullmatch(r"[A-Z]{1,3}\.?", toks[-1]):
                        out.append({"family": " ".join(toks[:-1]), "given": toks[-1],
                                    "name": part})
                    else:
                        out.append({"family": None, "given": None, "name": part})

    if isinstance(v, list):
        for x in v[:80]:
            add(x)
    elif v not in (None, ""):
        add(v)
    seen, res = set(), []
    for a in out:
        key = (a.get("family") or "", a.get("name") or "")
        if key in seen or not (a.get("name") or ""):
            continue
        seen.add(key)
        res.append(a)
    return res


def inv2text(d):
    slots = {}
    if isinstance(d, dict):
        for w, ps in d.items():
            if isinstance(ps, list):
                for p in ps:
                    if isinstance(p, int):
                        slots[p] = w
    return " ".join(slots[k] for k in sorted(slots))


def dig(o, path):
    cur = [o]
    for tok in path.split("."):
        m = re.match(r"^(.*?)((?:\[\d+\])*)$", tok)
        name, idxs = m.group(1), [int(x) for x in re.findall(r"\[(\d+)\]", m.group(2))]
        nxt = []
        for c in cur:
            if name in ("*", ""):
                vals = c if isinstance(c, list) else [c]
            elif isinstance(c, dict):
                vals = [c.get(name)]
            else:
                vals = [None]
            for v in vals:
                for i in idxs:
                    v = v[i] if isinstance(v, list) and len(v) > i else None
                if v not in (None, ""):
                    nxt.append(v)
        cur = nxt
        if not cur:
            return None
    return cur[0]


def generic_get(rec, field, depth=0):
    if depth > 3:
        return None
    names = SYN.get(field, [field])
    if isinstance(rec, dict):
        low = {str(k).lower(): v for k, v in rec.items()}
        for n in names:
            v = low.get(n.lower())
            if v not in (None, "", [], {}):
                return v
        for k, v in low.items():
            if k in CONTAINERS and isinstance(v, (dict, list)):
                r = generic_get(v, field, depth + 1)
                if r not in (None, "", [], {}):
                    return r
    elif isinstance(rec, list):
        for v in rec[:15]:
            r = generic_get(v, field, depth + 1)
            if r not in (None, "", [], {}):
                return r
    return None


def nfield(f, v, db):
    if v in (None, "", [], {}):
        return None
    if f == "authors":
        return nauthors(v) or None
    if f == "year":
        return nyear(scalar(v))
    if f in ("doi",):
        return ndoi(v)
    if f in ("pmid", "pmcid", "arxiv"):
        return nid(v, f)
    if f == "abstract":
        if isinstance(v, dict) and any(isinstance(x, list) for x in v.values()):
            return fix_text(inv2text(v)) or None
        s = scalar(v)
        if isinstance(v, list):
            s = " ".join(str(scalar(x) or "") for x in v) or s
        return fix_text(str(s)) if s not in (None, "") else None
    if f == "is_retracted":
        if isinstance(v, bool):
            return v
        s = str(scalar(v) or v).lower()
        if any(t in s for t in ("true", "yes", "y", "retracted", "retraction")):
            return True
        return None
    if f == "citation_count":
        s = scalar(v)
        try:
            return int(s)
        except (TypeError, ValueError):
            return None
    if f == "language":
        s = scalar(v)
        s = fix_text(str(s)) if s else ""
        return (s[:8].lower() if s else None)
    if f == "type":
        s = scalar(v)
        if isinstance(s, list):
            s = s[0]
        s = fix_text(str(s)) if s else ""
        return s.lower().replace("_", "-")[:60] if s else None
    s = scalar(v)
    if isinstance(v, list) and f in ("url",):
        s = s or (v[0] if isinstance(v[0], str) else None)
    if s in (None, "") and isinstance(v, dict):
        s = None
    s = fix_text(str(s)) if s not in (None, "") else None
    return s or None


# --------------------------------------------------------------- profiles
def load_profiles():
    try:
        d = json.loads(read_text(REF / "db-profiles.json"))
        if isinstance(d, dict) and isinstance(d.get("databases"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"databases": {}, "authority": {}, "dedup": {}}


def authority(prof, field, db):
    return float((prof.get("authority") or {}).get(field, {}).get(db, 1))


# ---------------------------------------------------------------- discovery
def looks_like_record(d):
    if not isinstance(d, dict) or len(d) < 2:
        return False
    sig = 0
    low = {str(k).lower(): v for k, v in d.items()}
    for k in low:
        if any(t in k for t in ("title", "display_name", "article_title")):
            sig += 2
        elif any(t in k for t in ("doi", "pmid", "pmcid", "arxiv")):
            sig += 2
        elif any(t in k for t in ("author", "creator", "contributor")):
            sig += 1
        elif any(t in k for t in ("year", "date", "venue", "journal", "container")):
            sig += 1
    for v in low.values():
        if isinstance(v, str) and DOI_RE.search(v):
            sig += 1
            break
    for v in low.values():
        if isinstance(v, (int, str)) and nyear(v) and 1900 < (nyear(v) or 0) < 2100:
            sig += 1
            break
    return sig >= 3


def walk_lists(o, ptr=""):
    if isinstance(o, dict):
        for k, v in o.items():
            p = ptr + "/" + esc(k)
            if isinstance(v, list) and v and all(isinstance(x, str) for x in v) \
                    and str(k).lower() in ("uids", "ids", "keys", "idlist", "id_list"):
                for uid in v[:500]:
                    r = o.get(uid)
                    if isinstance(r, dict):
                        yield ("%s[%s]" % (p, esc(uid)), [r])
            yield from walk_lists(v, p)
    elif isinstance(o, list):
        yield (ptr, o)
        for i, v in enumerate(o[:5000]):
            yield from walk_lists(v, ptr + "/" + str(i))


def pick_record_lists(obj):
    cands = []
    for ptr, lst in walk_lists(obj):
        if not isinstance(lst, list) or not lst:
            continue
        good = sum(1 for x in lst[:200] if looks_like_record(x))
        if good and good >= max(1, int(0.5 * min(len(lst), 200))):
            cands.append((ptr, lst, good))
    cands.sort(key=lambda c: (len(c[0]), -c[2]))
    kept = []
    for ptr, lst, good in cands:
        if any(ptr == k[0] or ptr.startswith(k[0] + "/") for k in kept):
            continue
        kept.append((ptr, lst, good))
    return kept


def detect_db(obj, name):
    n = (name or "").lower()
    hints = {"crossref": ("crossref", "cr_"), "europepmc": ("europepmc", "epmc", "europe-pmc", "pmc_"),
             "pubmed": ("pubmed", "ncbi", "esummary", "efetch"),
             "openalex": ("openalex", "oa_"), "semanticscholar": ("semantic", "s2"),
             "arxiv": ("arxiv",), "publisher": ("publisher", "elsevier", "springer", "wiley")}
    for db, hs in hints.items():
        if any(h in n for h in hs):
            return db
    blob = ""
    try:
        blob = json.dumps(obj)[:200000]
    except (TypeError, ValueError):
        blob = str(obj)[:200000]
    if '"message"' in blob and '"items"' in blob and "DOI" in blob:
        return "crossref"
    if "resultList" in blob or ("authorString" in blob and "pubYear" in blob):
        return "europepmc"
    if "esearchresult" in blob or "MedlineCitation" in blob or '"uids"' in blob:
        return "pubmed"
    dbs = (load_profiles().get("databases") or {})
    for db, prof in dbs.items():
        if db in ("generic", "publisher"):
            continue
        if any(sig in blob for sig in prof.get("signatures", [])):
            return db
    return "generic"


def collect_ids(o, out, depth=0):
    if depth > 8:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            kl = str(k).lower()
            if isinstance(v, str):
                if kl in ("doi", "doi_url") or DOI_RE.search(v):
                    d = ndoi(v)
                    if d:
                        out.add("doi:" + d)
                if kl in ("pmid", "pubmed_id") and v.strip().isdigit():
                    out.add("pmid:" + v.strip())
            else:
                collect_ids(v, out, depth + 1)
    elif isinstance(o, list):
        for v in o[:2000]:
            collect_ids(v, out, depth + 1)
    return out


def discover(root, ctx, res):
    root = Path(root)
    files = []
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                try:
                    files.append({"path": p, "rel": str(p.relative_to(root)),
                                  "ext": p.suffix.lower(), "size": p.stat().st_size})
                except OSError:
                    continue
    ctx["files"] = files
    res["runtime"]["input_files"] = len(files)
    if not files:
        res["errors"].append({"stage": "discover", "type": "empty_input",
                              "message": "no readable file under input root %s" % root})
        return
    # case file
    order = sorted(files, key=lambda f: (0 if f["path"].name.lower() == "case.json" else
                                         1 if f["path"].stem.lower().startswith("case") else
                                         2 if f["ext"] == ".json" else 9, len(f["rel"])))
    for f in order:
        if f["ext"] not in (".json", ".jsonl") or f["size"] > 12_000_000:
            continue
        o = jread(f["path"])
        if isinstance(o, dict) and any(k in o for k in ("case_id", "task_instruction",
                                                        "output_contract", "scope",
                                                        "organizer_supplied_scope")):
            ctx["case"], ctx["case_path"] = o, f["rel"]
            f["role"] = "case"
            break
    if ctx["case"] is None:
        res["errors"].append({"stage": "discover", "type": "case_file_missing",
                              "message": "no case*.json with case_id/task_instruction/output_contract found"})
    task_md = None
    for cand in ("task.md", "TASK.md", "prompt.md"):
        p = root / cand
        if p.exists():
            task_md = read_text(p)
            break
    if task_md is None:
        for f in files:
            if f["ext"] in (".md", ".txt") and f["size"] < 400_000:
                task_md = read_text(f["path"])
                f["role"] = f.get("role") or "task_text"
                break
    ctx["task_md"] = task_md or ""
    # contract
    contract = None
    if isinstance(ctx["case"], dict):
        contract = find_key(ctx["case"], ("output_contract", "outputcontract", "contract", "output_format"))
    if contract is None:
        for f in files:
            if "contract" in f["path"].name.lower() and f["ext"] == ".json":
                contract = jread(f["path"])
                if isinstance(contract, dict):
                    contract = contract.get("output_contract", contract)
                break
    ctx["contract"] = contract
    res["contract_echo"] = contract
    if contract is None:
        res["degradations"].append({"stage": "discover", "type": "no_output_contract",
                                    "action": "emit canonical blocks only"})
    ctx["case_id"] = (ctx["case"] or {}).get("case_id")
    res["case_id"] = ctx["case_id"]


def find_key(o, names, depth=0):
    if depth > 5 or not isinstance(o, (dict, list)):
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower() in names and v not in (None, "", [], {}):
                return v
        for v in o.values():
            r = find_key(v, names, depth + 1)
            if r is not None:
                return r
    else:
        for v in o[:50]:
            r = find_key(v, names, depth + 1)
            if r is not None:
                return r
    return None


def first_key(d, names):
    if not isinstance(d, dict):
        return None
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n in low and low[n] not in (None, "", [], {}):
            return low[n]
    for n in names:
        for k, v in low.items():
            if n in k and v not in (None, "", [], {}):
                return v
    return None


def collect_meta(case):
    meta = {}
    if not isinstance(case, dict):
        return meta
    for k, v in case.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                meta.setdefault(str(k2), v2)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            for it in v[:20]:
                if isinstance(it, dict):
                    for k2, v2 in it.items():
                        meta.setdefault(str(k2), v2)
        else:
            meta.setdefault(str(k), v)
    return meta


def scope_of(case, task_md):
    meta = collect_meta(case)
    topic = first_key(meta, ["research_question", "topic", "question", "objective", "subject",
                             "title", "query", "goal"])
    instr = first_key(meta, ["task_instruction", "instruction", "task", "prompt"])
    if isinstance(topic, list):
        topic = " ".join(str(x) for x in topic)
    if not topic:
        topic = str(instr or "")[:400]
    dbs = first_key(meta, ["databases", "dbs", "data_sources", "sources", "database_list",
                           "target_databases"])
    if isinstance(dbs, str):
        dbs = [d.strip() for d in re.split(r"[,;/]", dbs) if d.strip()]
    dbs = [str(d).lower().replace(" ", "") for d in (dbs or []) if isinstance(d, str)]
    dbs = [{"europe pmc": "europepmc", "epmc": "europepmc", "semantic scholar": "semanticscholar",
            "semantic_scholar": "semanticscholar", "semanticscholar": "semanticscholar",
            "webofscience": "webofscience", "scopus": "scopus"}.get(d, d) for d in dbs]
    years = first_key(meta, ["years", "year_range", "publication_years", "time_range", "date_range"])
    yf = first_key(meta, ["year_from", "start_year", "from_year"])
    yt = first_key(meta, ["year_to", "end_year", "to_year"])
    if isinstance(years, dict):
        yf = yf or years.get("from") or years.get("start")
        yt = yt or years.get("to") or years.get("end")
    elif isinstance(years, list) and len(years) >= 2:
        yf, yt = yf or years[0], yt or years[-1]
    elif isinstance(years, str):
        ys = re.findall(r"(1[6-9]\d{2}|20\d{2})", years)
        if len(ys) >= 2:
            yf, yt = yf or ys[0], yt or ys[-1]
    lang = first_key(meta, ["language", "languages", "lang"])
    if isinstance(lang, str):
        lang = [x.strip() for x in re.split(r"[,;/]", lang) if x.strip()]
    kw = first_key(meta, ["keywords", "key_terms", "search_terms", "concepts", "terms"])
    if isinstance(kw, str):
        kw = [x.strip() for x in re.split(r"[,;]", kw) if x.strip()]
    seeds = first_key(meta, ["seeds", "seed_papers", "seed_dois", "known_relevant", "gold",
                             "reference_seeds", "gold_set", "included_seeds"])
    mk = first_key(meta, ["max_k", "top_k", "max_results", "limit"])
    return {"topic": topic, "task_instruction": instr, "databases": dbs,
            "year_from": nyear(yf), "year_to": nyear(yt),
            "languages": [str(x).lower() for x in (lang or [])],
            "keywords": kw if isinstance(kw, list) else ([kw] if kw else []),
            "seeds": seeds, "max_k": mk, "task_md_chars": len(task_md or "")}


# ------------------------------------------------------------ query planning
QTMPL = {
    "crossref": 'query.bibliographic="{t}"; filter=from-pub-date:{y0}-01-01,until-pub-date:{y1}-12-31[,type:journal-article]',
    "europepmc": '((TITLE_ABS:"{t}") OR (TITLE_ABS:"{k}")) AND (FIRST_PDATE:[{y0}-01-01 TO {y1}-12-31])',
    "pubmed": '("{t}"[Title/Abstract] OR "{k}"[Title/Abstract]) AND ("{y0}"[dp] : "{y1}"[dp])',
    "openalex": 'search={t} {k}; filter=from_publication_date:{y0}-01-01,to_publication_date:{y1}-12-31',
    "semanticscholar": 'query={t} {k}; year={y0}-{y1}; fields=title,abstract,year,venue,authors,externalIds,citationCount',
    "arxiv": 'search_query=all:"{t}" AND all:"{k}"; start=0; max_results=100',
    "publisher": "local material records; no query issued",
    "generic": '{t} (free text; source dialect unknown)',
}


def plan_queries(ctx, res):
    scope = ctx["scope"]
    topic = (scope.get("topic") or "")[:180].strip()
    kws = [str(k) for k in (scope.get("keywords") or [])][:3]
    y0, y1 = scope.get("year_from"), scope.get("year_to")
    dbs = []
    for d in scope.get("databases") or []:
        if d and d not in dbs:
            dbs.append(d)
    for d in ctx["observed_dbs"]:
        if d not in dbs:
            dbs.append(d)
    queries = []
    for i, db in enumerate(dbs, 1):
        prof = (ctx["profiles"].get("databases") or {}).get(db, {})
        tmpl = QTMPL.get(db, QTMPL["generic"])
        try:
            expanded = tmpl.format(t=topic or "<topic>", k=kws[0] if kws else (topic or "<term>"),
                                   y0=y0 or "<from>", y1=y1 or "<to>")
        except (KeyError, IndexError, ValueError):
            expanded = tmpl
        q = {"query_id": "q%03d" % i, "db": db, "raw": topic or None, "expanded": expanded,
             "fields_targeted": (prof.get("query") or {}).get("fields", []),
             "dialect_strength": (prof.get("query") or {}).get("strength"),
             "caps": (prof.get("query") or {}).get("caps"),
             "filters": {"year_from": y0, "year_to": y1,
                         "languages": scope.get("languages") or []},
             "hits": None, "kept": None,
             "status": "planned_not_executed_offline", "retrieved_at": None,
             "source_file": None, "error": None}
        if db in ctx["executed"]:
            src = ctx["executed"][db]
            q["status"] = "executed_offline_recorded"
            q["source_file"] = src["file"]
            q["retrieved_at"] = src["retrieved_at"]
            q["hits"] = src["hits"]
            if src.get("echo"):
                q["expanded"] = src["echo"]
                q["raw"] = src.get("echo_raw") or topic
            ctx["query_by_db"][db] = "q%03d" % i
        else:
            q["error"] = "no recorded response supplied for this database (offline execution)"
            res["degradations"].append({"stage": "plan", "db": db,
                                        "type": "not_executed_offline",
                                        "action": "query plan emitted, marked planned_not_executed_offline"})
        queries.append(q)
    ctx["queries"] = queries
    res["queries"] = queries


# ------------------------------------------------------------------ harvest
def harvest(ctx, res):
    prof = ctx["profiles"]
    recs, seeds, responses = [], set(), []
    for f in ctx["files"]:
        if f.get("role") == "case" or f["size"] > 12_000_000:
            continue
        name = f["path"].name.lower()
        if f["ext"] not in (".json", ".jsonl", ".csv", ".tsv"):
            continue
        is_seedfile = any(t in name for t in ("reference", "citation", "seed", "gold",
                                              "known_relevant", "bibliograph"))
        obj = None
        if f["ext"] in (".csv", ".tsv"):
            try:
                with open(f["path"], "r", encoding="utf-8", errors="replace", newline="") as fh:
                    rows = list(csv.DictReader(fh, delimiter="\t" if f["ext"] == ".tsv" else ","))
                obj = {"__records__": [r for r in rows[:5000] if any(v for v in r.values())]}
            except (OSError, csv.Error):
                res["errors"].append({"stage": "harvest", "type": "csv_read_failed",
                                      "file": f["rel"]})
                continue
        else:
            obj = jread(f["path"])
            if obj is None:
                res["errors"].append({"stage": "harvest", "type": "json_parse_failed",
                                      "file": f["rel"],
                                      "message": "not valid JSON/JSONL; skipped"})
                f["role"] = "unparsed"
                continue
        if is_seedfile:
            collect_ids(obj, seeds)
            f["role"] = "seed_or_graph"
            res["sources"].append({"id": "src-%02d" % (len(res["sources"]) + 1),
                                   "file": f["rel"], "kind": "seed_or_reference_graph",
                                   "records": None})
            continue
        db = detect_db(obj, name)
        lists = pick_record_lists(obj)
        if not lists and isinstance(obj, dict) and looks_like_record(obj):
            lists = [("", [obj], 1)]
        if not lists:
            f["role"] = f.get("role") or "other"
            continue
        when = None
        for k in ("retrieved_at", "retrievedAt", "timestamp", "generated", "created", "date",
                  "requested_at"):
            v = obj.get(k) if isinstance(obj, dict) else None
            if isinstance(v, str) and v.strip():
                when = v.strip()[:32]
                break
        ts_src = "response_metadata"
        if not when:
            try:
                when = iso(f["path"].stat().st_mtime)
                ts_src = "artifact_mtime"
                f["degradation"] = "retrieved_at from file mtime"
            except OSError:
                when, ts_src = iso(), "run_time"
        echo = find_key(obj, ("query", "searchterms", "query_bibliographic", "q", "search_request"))
        if isinstance(echo, (dict, list)):
            echo = json.dumps(echo, ensure_ascii=False)[:300]
        nrec = 0
        for ptr, lst, _g in lists:
            for i, r in enumerate(lst):
                if not isinstance(r, dict):
                    continue
                mapped, prov = map_record(r, db, prof)
                if not (mapped.get("title") or mapped.get("doi")):
                    continue
                nrec += 1
                mapped["_db"] = db
                mapped["_file"] = f["rel"]
                mapped["_ptr"] = "%s/%d" % (ptr, i) if ptr else "/%d" % i
                mapped["_when"] = when
                mapped["_ts_src"] = ts_src
                mapped["_prov"] = prov
                recs.append(mapped)
        f["role"] = "response"
        if db not in ctx["executed"] or nrec > ctx["executed"][db]["hits"]:
            ctx["executed"][db] = {"file": f["rel"], "hits": nrec, "retrieved_at": when,
                                   "echo": echo, "ts_src": ts_src}
        responses.append({"db": db, "file": f["rel"], "records": nrec, "retrieved_at": when,
                          "retrieved_at_source": ts_src, "query_echo": echo})
        if ts_src == "artifact_mtime":
            res["degradations"].append({"stage": "harvest", "file": f["rel"],
                                        "type": "retrieved_at_from_mtime",
                                        "action": "response carried no timestamp; file mtime recorded"})
    ctx["recs"], ctx["seeds"] = recs, seeds
    ctx["observed_dbs"] = sorted({r["_db"] for r in recs})
    res["sources"] = [s for s in res["sources"] if s.get("kind") != "seed_or_reference_graph"] + [
        {"id": "src-r%02d" % i, "db": r["db"], "file": r["file"], "kind": "database_response",
         "records": r["records"], "retrieved_at": r["retrieved_at"],
         "retrieved_at_source": r["retrieved_at_source"], "query_echo": r["query_echo"]}
        for i, r in enumerate(responses, 1)]
    return recs


def map_record(rec, db, prof):
    paths = ((prof.get("databases") or {}).get(db, {}) or {}).get("record_paths", {}) or {}
    out, prov = {}, {}
    for f in CFIELDS:
        val, used = None, None
        for p in paths.get(f, []):
            try:
                val = dig(rec, p)
            except (TypeError, IndexError, KeyError):
                val = None
            if val not in (None, "", [], {}):
                used = p
                break
        if val in (None, "", [], {}):
            val = generic_get(rec, f)
            used = ("synonym:" + f) if val not in (None, "", [], {}) else None
        if f in ("doi", "pmcid", "pmid") and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    t = str(item.get("idtype", "")).lower()
                    if (f == "doi" and t == "doi") or (f == "pmcid" and t in ("pmc", "pmcid")) \
                            or (f == "pmid" and t in ("pubmed", "pmid")):
                        val = item.get("value")
                        break
        nv = nfield(f, val, db)
        if nv in (None, "", [], {}):
            continue
        out[f] = nv
        prov[f] = {"db": db, "path": used, "raw_value": str(scalar(val) if not isinstance(val, list) else val)[:300]}
    out["_rawtitle"] = str(scalar(rec.__getitem__(list(rec.keys())[0]) if False else ""))
    raw_t = None
    for p in (paths.get("title") or []) + ["title"]:
        raw_t = dig(rec, p)
        if raw_t not in (None, "", [], {}):
            break
    out["_raw_title"] = str(scalar(raw_t))[:400] if raw_t not in (None, "", [], {}) else ""
    return out, prov


# ---------------------------------------------------------------- dedup/merge
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if rb < ra:
            ra, rb = rb, ra
        self.p[rb] = ra
        return True


def surname(r):
    au = r.get("authors") or []
    if au and isinstance(au[0], dict):
        s = au[0].get("family") or ((au[0].get("name") or "").split(" ")[0] if au[0].get("name") else None)
        return ntitle(s or "").split(" ")[0] if s else ""
    return ""


def dedup(ctx, res):
    recs = ctx["recs"]
    cfg = (ctx["profiles"].get("dedup") or {})
    ytol = int(cfg.get("year_tolerance", 1))
    auto = float(cfg.get("fuzzy_auto", 0.90))
    arb = float(cfg.get("fuzzy_arbitrate", 0.82))
    jpre = float(cfg.get("token_jaccard_prefilter", 0.55))
    uf = UF(len(recs))
    decisions, pending = [], []
    for key in ("doi", "pmid", "pmcid", "arxiv"):
        idx = {}
        for i, r in enumerate(recs):
            v = r.get(key)
            if not v:
                continue
            if v in idx:
                if uf.union(idx[v], i):
                    decisions.append({"rule": "identifier:" + key, "value": v, "a": idx[v],
                                      "b": i, "confidence": "high", "accepted": True})
            else:
                idx[v] = i
    for i, r in enumerate(recs):
        r["_nt"] = ntitle(r.get("title") or "")
    bytitle = {}
    for i, r in enumerate(recs):
        t = r["_nt"]
        if len(t) < int(cfg.get("title_exact_min_len", 15)):
            continue
        if t in bytitle:
            j = bytitle[t]
            ya, yb = recs[j].get("year"), r.get("year")
            if ya is None or yb is None or abs(ya - yb) <= ytol:
                if uf.union(j, i):
                    decisions.append({"rule": "title_exact", "a": j, "b": i,
                                      "title": t[:120], "confidence": "high", "accepted": True})
            else:
                decisions.append({"rule": "title_exact_year_conflict", "a": j, "b": i,
                                  "title": t[:120], "confidence": "low", "accepted": False,
                                  "reason": "identical title but |year delta|>%d" % ytol})
                pending.append({"type": "duplicate_candidate", "a": j, "b": i,
                                "reason": "same title, years %s vs %s" % (ya, yb)})
        else:
            bytitle[t] = i
    if not ctx["args"].no_fuzzy and len(recs) <= 1500:
        toks = [set(r["_nt"].split()) for r in recs]
        for a in range(len(recs)):
            if not recs[a]["_nt"]:
                continue
            for b in range(a + 1, len(recs)):
                if uf.find(a) == uf.find(b) or not recs[b]["_nt"]:
                    continue
                sa, sb = toks[a], toks[b]
                if not sa or not sb:
                    continue
                jac = len(sa & sb) / float(len(sa | sb))
                if jac < jpre:
                    continue
                ratio = SequenceMatcher(None, recs[a]["_nt"], recs[b]["_nt"]).ratio()
                ya, yb = recs[a].get("year"), recs[b].get("year")
                yok = ya is None or yb is None or abs(ya - yb) <= ytol
                fa, fb = surname(recs[a]), surname(recs[b])
                aok = (not fa) or (not fb) or fa == fb
                if ratio >= auto and yok and aok:
                    if uf.union(a, b):
                        decisions.append({"rule": "title_fuzzy", "a": a, "b": b,
                                          "ratio": round(ratio, 3), "jaccard": round(jac, 3),
                                          "confidence": "high", "accepted": True})
                elif arb <= ratio < auto and yok and aok:
                    if uf.union(a, b):
                        decisions.append({"rule": "title_fuzzy_arbitrate", "a": a, "b": b,
                                          "ratio": round(ratio, 3), "confidence": "medium",
                                          "accepted": True})
                        pending.append({"type": "merge_arbitration", "a": a, "b": b,
                                        "ratio": round(ratio, 3),
                                        "reason": "fuzzy merge below auto threshold"})
                elif ratio >= auto and not (yok and aok):
                    decisions.append({"rule": "title_fuzzy_guard_reject", "a": a, "b": b,
                                      "ratio": round(ratio, 3), "confidence": "low",
                                      "accepted": False,
                                      "reason": "high title similarity but year/author guard failed"})
                    pending.append({"type": "possible_duplicate", "a": a, "b": b,
                                    "ratio": round(ratio, 3),
                                    "reason": "year or first-author guard failed"})
    elif len(recs) > 1500:
        res["degradations"].append({"stage": "dedup", "type": "fuzzy_skipped_too_many_records",
                                    "records": len(recs),
                                    "action": "identifier + exact-title dedup only"})
    groups = {}
    for i in range(len(recs)):
        groups.setdefault(uf.find(i), []).append(i)
    ctx["groups"] = groups
    ctx["decisions"] = decisions
    ctx["pending_dup"] = pending
    return groups


def merge_clusters(ctx, res):
    recs, groups = ctx["recs"], ctx["groups"]
    prof = ctx["profiles"]
    cands, clusters, conflicts = [], [], []
    for k, members in sorted(groups.items(), key=lambda kv: kv[0]):
        ms = [recs[i] for i in members]
        out = {}
        for f in CFIELDS:
            opts = []
            for m in ms:
                v = m.get(f)
                if v in (None, "", [], {}):
                    continue
                opts.append((-authority(prof, f, m["_db"]), -len(json.dumps(v, ensure_ascii=False)),
                             m["_db"], v))
            if not opts:
                out[f] = None if f not in ("authors",) else []
                continue
            opts.sort(key=lambda o: (o[0], o[1], o[2]))
            out[f] = opts[0][3]
            if len(opts) > 1:
                losers = []
                for o in opts[1:]:
                    same = json.dumps(o[3], ensure_ascii=False).lower().replace(" ", "") == \
                        json.dumps(opts[0][3], ensure_ascii=False).lower().replace(" ", "")
                    if not same:
                        losers.append({"db": o[2], "value": o[3]})
                if losers:
                    conflicts.append({"cluster": "k%02d" % (len(clusters) + 1), "field": f,
                                      "chosen": {"db": opts[0][2], "value": opts[0][3]},
                                      "alternatives": losers,
                                      "rule": "highest field authority, then longer value, then db name"})
        dbs = sorted({m["_db"] for m in ms})
        qids = sorted({ctx["query_by_db"].get(m["_db"]) for m in ms if ctx["query_by_db"].get(m["_db"])})
        prov = {}
        for f in CFIELDS:
            for m in ms:
                if f in m.get("_prov", {}) and m.get(f) is not None and \
                        json.dumps(m.get(f), ensure_ascii=False) == json.dumps(out.get(f), ensure_ascii=False):
                    prov[f] = dict(m["_prov"][f], **{"cluster": "k%02d" % (len(clusters) + 1)})
                    break
        first = ms[0]
        ev = {"field": "title", "quote": (first.get("_raw_title") or first.get("title") or "")[:300],
              "locator": first["_ptr"], "raw_file": first["_file"], "db": first["_db"],
              "match": "verbatim"}
        cand = dict(out)
        cand.update({"cluster_id": "k%02d" % (len(clusters) + 1),
                     "source_dbs": dbs, "query_ids": qids,
                     "retrieved_at": max([m["_when"] for m in ms] or [None]) if any(m.get("_when") for m in ms) else None,
                     "retrieved_at_source": first.get("_ts_src"),
                     "field_provenance": prov, "evidence": ev,
                     "merged_from": len(ms), "flags": [],
                     "provenance_chain": [{"db": m["_db"], "raw_file": m["_file"],
                                           "raw_pointer": m["_ptr"],
                                           "query_id": ctx["query_by_db"].get(m["_db"])}
                                          for m in ms]})
        if any(m.get("is_retracted") for m in ms):
            cand["flags"].append("retraction_signal")
            res["pending_human"].append({"type": "retraction_check", "cluster_id": cand["cluster_id"],
                                         "doi": cand.get("doi"),
                                         "reason": "at least one response carries a retraction signal"})
        filled = sum(1 for f in ("title", "authors", "year", "venue", "doi") if cand.get(f))
        cand["metadata_confidence"] = round(filled / 5.0, 2)
        cands.append(cand)
        clusters.append({"cluster_id": cand["cluster_id"], "size": len(ms), "dbs": dbs,
                         "members": [{"db": m["_db"], "file": m["_file"], "ptr": m["_ptr"]} for m in ms],
                         "rule": [d["rule"] for d in ctx["decisions"]
                                  if d.get("accepted") and d.get("rule") and
                                  (("a" in d and recs[d["a"]] is not None) and
                                   d.get("a") in members and d.get("b") in members)][:6] or
                                 (["singleton"] if len(ms) == 1 else ["identifier_chain"])})
    ctx["candidates"] = cands
    res["clusters"] = clusters
    res["conflicts"] = conflicts[:400]
    res["merge_decisions"] = [{"rule": d.get("rule"), "a": d.get("a"), "b": d.get("b"),
                               "confidence": d.get("confidence"), "accepted": d.get("accepted"),
                               "ratio": d.get("ratio"), "value": d.get("value"),
                               "reason": d.get("reason")} for d in ctx["decisions"]][:800]
    res["merge_summary"] = {"raw_records": len(ctx["recs"]),
                            "clusters": len(cands),
                            "merged_clusters": sum(1 for c in clusters if c["size"] > 1),
                            "records_removed": len(ctx["recs"]) - len(cands),
                            "decisions": len(ctx["decisions"]),
                            "rejected_pairs": sum(1 for d in ctx["decisions"] if not d.get("accepted"))}
    return cands


# ------------------------------------------------------------- score/screen
def terms_of(text):
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text or ""):
        t = tok.lower().strip("-")
        if t and t not in STOP and len(t) > 2:
            out.append(t)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        for i in range(len(run) - 1):
            out.append(run[i:i + 2])
    return out


def score_all(ctx, res):
    scope = ctx["scope"]
    blob = " ".join([str(scope.get("topic") or ""), str(scope.get("task_instruction") or ""),
                     " ".join(str(k) for k in scope.get("keywords") or []),
                     " ".join(str(q.get("raw") or "") for q in ctx["queries"])])
    terms = set(terms_of(blob))
    seeds = ctx["seeds"]
    y0, y1 = scope.get("year_from"), scope.get("year_to")
    thr = ctx["args"].min_score
    crit = ["relevance_score >= %.2f" % thr,
            "year within [%s, %s] when scope declares it" % (y0 or "*", y1 or "*"),
            "language filter when scope declares it",
            "retraction flagged but never silently dropped"]
    inc = exc = 0
    excluded = []
    for c in ctx["candidates"]:
        tset = set(terms_of(c.get("title") or ""))
        aset = set(terms_of(c.get("abstract") or ""))
        ht, ha = tset & terms, aset & terms
        y = c.get("year")
        inscope = 1.0 if (y0 is None or y1 is None or (y and y0 <= y <= y1)) else 0.0
        if y is None:
            inscope = 0.5
        if not terms:
            c["relevance_score"] = None
            c["relevance_reason"] = "no topic/query terms recoverable from input; keyword relevance not computable"
        else:
            cov_t = min(1.0, len(ht) / float(max(1, min(len(terms), 10))))
            cov_a = min(1.0, 2.0 * len(ha) / float(max(1, len(terms))))
            seed_hit = 1.0 if ({"doi:" + c["doi"]} & seeds if c.get("doi") else False) or \
                ({"pmid:" + c["pmid"]} & seeds if c.get("pmid") else False) else 0.0
            sc = 0.55 * cov_t + 0.30 * cov_a + 0.15 * inscope + 0.10 * seed_hit
            c["relevance_score"] = round(min(1.0, sc), 3)
            c["relevance_reason"] = ("title matched %d/%d topic terms %s; abstract matched %d; "
                                     "year %s %s scope; seed-set match %s"
                                     % (len(ht), len(terms), sorted(ht)[:8], len(ha),
                                        y if y else "unknown",
                                        "in" if inscope >= 1 else ("unknown for" if inscope == 0.5 else "outside"),
                                        bool(seed_hit)))
        reasons = []
        if c["relevance_score"] is not None and c["relevance_score"] < thr:
            reasons.append("below relevance threshold %.2f" % thr)
        if y0 and y1 and y and not (y0 <= y <= y1):
            reasons.append("outside declared year window %s-%s" % (y0, y1))
        if scope.get("languages") and c.get("language") and \
                c["language"][:2] not in [l[:2] for l in scope["languages"]]:
            reasons.append("language %s not in requested %s" % (c["language"], scope["languages"]))
        if reasons:
            c["included"] = False
            c["screen_reason"] = "; ".join(reasons)
            exc += 1
            if len(excluded) < 200:
                excluded.append({"cluster_id": c["cluster_id"], "title": (c.get("title") or "")[:160],
                                 "year": y, "doi": c.get("doi"), "score": c["relevance_score"],
                                 "reason": c["screen_reason"]})
        else:
            c["included"] = True
            c["screen_reason"] = "included: relevance %s, within declared scope" % c["relevance_score"]
            inc += 1
    cands = sorted(ctx["candidates"], key=lambda c: (-(c["relevance_score"] or 0),
                                                     -(c.get("year") or 0),
                                                     ntitle(c.get("title") or ""),
                                                     c.get("cluster_id") or ""))
    mk = scope.get("max_k")
    if isinstance(mk, int) and 0 < mk < len(cands) and not ctx["args"].max_candidates:
        res["degradations"].append({"stage": "screen", "type": "max_k_applied", "max_k": mk,
                                    "action": "candidate list truncated to scope max_k"})
        cands = cands[:mk]
    for i, c in enumerate(cands, 1):
        c["id"] = "c%03d" % i
        c["rank"] = i
    ctx["candidates"] = cands
    res["candidates"] = cands
    res["candidate_count"] = len(cands)
    res["screening"] = {"include": inc, "exclude": exc, "threshold": thr,
                        "criteria": crit, "excluded": excluded}
    return cands


# ----------------------------------------------------------------- coverage
def coverage(ctx, res):
    recs, cands = ctx["recs"], ctx["candidates"]
    scope = ctx["scope"]
    per_db, fill = {}, {}
    for db in ctx["observed_dbs"]:
        mine = [r for r in recs if r["_db"] == db]
        per_db[db] = {"raw_records": len(mine),
                      "candidates": sum(1 for c in cands if db in c["source_dbs"]),
                      "unique_to_db": sum(1 for c in cands if c["source_dbs"] == [db])}
        fill[db] = {}
        for f in CFIELDS:
            if not mine:
                continue
            fill[db][f] = round(sum(1 for r in mine if r.get(f) not in (None, "", [], {}))
                                / float(len(mine)), 3)
    merged_fill = {}
    for f in CFIELDS:
        merged_fill[f] = round(sum(1 for c in cands if c.get(f) not in (None, "", [], {}))
                               / float(max(1, len(cands))), 3)
    required = scope.get("databases") or []
    missing = [d for d in required if d not in ctx["observed_dbs"]]
    gaps = []
    for d in missing:
        gaps.append({"type": "database_not_covered", "database": d,
                     "detail": "no recorded response for this database under input; query planned only"})
    for f in CFIELDS:
        if cands and merged_fill.get(f, 0) == 0:
            gaps.append({"type": "field_systematically_missing", "field": f,
                         "detail": "no database supplied this field for any candidate"})
    unknown_dbs = [d for d in ctx["observed_dbs"]
                   if d not in (ctx["profiles"].get("databases") or {})]
    for d in unknown_dbs:
        gaps.append({"type": "unknown_database_profile", "database": d,
                     "detail": "recognised files but no field-mapping profile; synonym fallback used"})
    seeds = ctx["seeds"]
    if seeds:
        matched = set()
        for c in cands:
            for k in ("doi", "pmid"):
                if c.get(k) and ("%s:%s" % (k, c[k])) in seeds:
                    matched.add("%s:%s" % (k, c[k]))
        recall = {"available": True, "method": "seed-set recall (lower bound)",
                  "seed_identifiers": len(seeds), "matched": len(matched),
                  "recall": round(len(matched) / float(len(seeds)), 3),
                  "note": "lower bound only: seeds may be incomplete and not all seeds are in scope"}
    else:
        recall = {"available": False, "recall": None,
                  "note": "no seed/gold identifiers supplied; recall cannot be estimated without fabricating it"}
    res["coverage"] = {"required_databases": required, "observed_databases": ctx["observed_dbs"],
                       "per_db": per_db, "field_fill": fill, "field_fill_merged": merged_fill,
                       "unique_to_db": {d: v["unique_to_db"] for d, v in per_db.items()},
                       "gaps": gaps, "recall_estimate": recall,
                       "seed_pool_size": len(seeds)}
    res["databases"] = {"required": required, "observed": ctx["observed_dbs"], "missing": missing,
                        "profiles_used": ctx["observed_dbs"]}
    return res["coverage"]


def baseline(ctx, res):
    cands, recs = ctx["candidates"], ctx["recs"]
    best, uplift = {}, {}
    for f in CFIELDS:
        vals = [res["coverage"]["field_fill"].get(db, {}).get(f, 0) for db in ctx["observed_dbs"]]
        best[f] = max(vals) if vals else 0.0
        uplift[f] = round(res["coverage"]["field_fill_merged"].get(f, 0) - best[f], 3)
    two_plus = sum(1 for c in cands if len(c["source_dbs"]) > 1)
    hash_src = json.dumps([[c.get("doi"), ntitle(c.get("title") or ""), c.get("year")]
                           for c in sorted(cands, key=lambda c: c.get("id") or "")],
                          ensure_ascii=False, sort_keys=True)
    res["baseline_comparison"] = {
        "naive_concat_records": len(recs),
        "merged_candidates": len(cands),
        "duplicate_records_removed": len(recs) - len(cands),
        "duplicate_rate": round((len(recs) - len(cands)) / float(max(1, len(recs))), 3),
        "cross_db_corroborated": two_plus,
        "field_fill_best_single_db": best,
        "field_fill_merged": res["coverage"]["field_fill_merged"],
        "field_fill_uplift": uplift,
        "reproducibility_hash": hashlib.sha256(hash_src.encode("utf-8")).hexdigest()[:32],
        "method": "all figures computed from this run's inputs; no external benchmark used",
        "note": ("naive_concat_records is what a copy-paste-and-append workflow would report; "
                 "field_fill_uplift is the share of candidates gaining a field over the best single database")
    }
    res["metrics"] = {"precision_at_k": None, "ndcg_at_k": None, "recall_at_k": None,
                      "note": ("ranking metrics require a labelled gold set; not computed because "
                               "none was supplied" if not ctx["seeds"] else
                               "seed set available but without graded relevance labels; only recall is reported")}
    if ctx["seeds"]:
        res["metrics"]["recall_at_k"] = res["coverage"]["recall_estimate"].get("recall")
        res["metrics"]["k"] = ctx["scope"].get("max_k")


def evidence_block(ctx, res):
    ev = []
    for c in ctx["candidates"]:
        e = dict(c.get("evidence") or {})
        e["candidate_id"] = c.get("id")
        ev.append(e)
    res["evidence"] = ev
    seen = set()
    for c in ctx["candidates"]:
        for f, p in (c.get("field_provenance") or {}).items():
            key = (c.get("id"), f)
            if key in seen:
                continue
            seen.add(key)
    return ev


# -------------------------------------------------------------- contract fill
def canon_of(name):
    n = re.sub(r"[^a-z0-9]+", "", str(name).lower())
    if not n:
        return None
    best = None
    for key, aliases in CANON.items():
        for a in aliases:
            if n == a:
                return key
            if len(a) >= 4 and a in n:
                sc = (len(a), -list(CANON).keys().__len__() + list(CANON).keys().__iter__().__length_hint__()
                      if False else len(a))
                if best is None or sc > best[0]:
                    best = (sc, key)
    return best[1] if best else None


ITEM_ALIAS = {"id": "id", "title": "title", "authors": "authors", "author": "authors",
              "year": "year", "venue": "venue", "journal": "venue", "doi": "doi", "url": "url",
              "sourceurl": "url", "link": "url", "source": "source_dbs", "sourcedb": "source_dbs",
              "sourcedbs": "source_dbs", "database": "source_dbs", "databases": "source_dbs",
              "query": "query_ids", "queryid": "query_ids", "queryids": "query_ids",
              "retrievedat": "retrieved_at", "relevance": "relevance_score",
              "relevancescore": "relevance_score", "score": "relevance_score",
              "reason": "relevance_reason", "relevancereason": "relevance_reason",
              "evidence": "evidence", "evidencesnippet": "evidence", "abstract": "abstract",
              "pmid": "pmid", "type": "type", "language": "language", "flags": "flags",
              "confidence": "metadata_confidence", "metadataconfidence": "metadata_confidence",
              "clusterid": "cluster_id", "included": "included", "rank": "rank"}


def contract_fields(c):
    out = {}

    def add(name, spec):
        name = str(name)
        if name and name not in out:
            out[name] = spec

    if isinstance(c, list):
        for it in c:
            if isinstance(it, str):
                add(it, None)
            elif isinstance(it, dict):
                nm = it.get("name") or it.get("key") or it.get("field") or it.get("id") \
                    or it.get("title")
                if nm:
                    add(nm, it)
    elif isinstance(c, dict):
        props = c.get("properties")
        if not isinstance(props, dict):
            sch = c.get("schema")
            props = sch.get("properties") if isinstance(sch, dict) else None
        if isinstance(props, dict) and props:
            for k, v in props.items():
                add(k, v)
        elif isinstance(c.get("fields"), (list, dict)):
            inner = contract_fields(c["fields"])
            for k, v in inner.items():
                add(k, v)
        elif isinstance(c.get("output_contract"), (list, dict)):
            for k, v in contract_fields(c["output_contract"]).items():
                add(k, v)
        else:
            skip = {"name", "description", "version", "type", "required", "title", "schema",
                    "$schema", "notes", "comment", "id"}
            for k, v in c.items():
                if str(k).lower() in skip:
                    continue
                add(k, v if isinstance(v, (dict, list)) else None)
    return out


def item_fields(spec):
    names = []
    if isinstance(spec, dict):
        for key in ("item_fields", "fields", "properties", "columns", "keys"):
            v = spec.get(key)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, str):
                        names.append(x)
                    elif isinstance(x, dict):
                        nm = x.get("name") or x.get("key") or x.get("field")
                        if nm:
                            names.append(str(nm))
            elif isinstance(v, dict):
                names.extend([str(k) for k in v])
        for key in ("items", "schema", "of"):
            v = spec.get(key)
            if isinstance(v, dict):
                names.extend(item_fields(v))
    elif isinstance(spec, list) and spec and isinstance(spec[0], str):
        names.extend([str(x) for x in spec])
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


def fill_item(x, names):
    if not isinstance(x, dict):
        return x
    y = dict(x)
    low = {re.sub(r"[^a-z0-9]+", "", k.lower()): k for k in x}
    for n in names:
        if n in y:
            continue
        key = ITEM_ALIAS.get(re.sub(r"[^a-z0-9]+", "", n.lower()))
        if key and key in y:
            y[n] = y[key]
        elif key and key in low and low[key] in y:
            y[n] = y[low[key]]
        else:
            k2 = canon_of(n)
            y[n] = [] if n.lower().endswith("s") and k2 in ("candidates", "queries") else None
    return y


def fill_contract(res, contract):
    if contract is None:
        res["contract_fill"] = {}
        return
    fields = contract_fields(contract)
    blocks = {k: res.get(k) for k in CANON}
    fill = {}
    for name, spec in fields.items():
        key = canon_of(name)
        if key and blocks.get(key) not in (None, [], {}):
            res[name] = blocks[key]
            fill[name] = "filled:" + key
            if isinstance(res[name], list):
                names = item_fields(spec)
                if names:
                    res[name] = [fill_item(x, names) for x in res[name]]
                    fill[name] += "+item_fields"
        else:
            is_list = (isinstance(spec, dict) and str(spec.get("type", "")).lower() in
                       ("array", "list")) or (isinstance(spec, list))
            if key == "candidates" or key == "queries" or key == "sources" or key == "clusters":
                res[name] = []
            else:
                res[name] = [] if is_list else None
            fill[name] = "empty:unmapped" if not key else "empty:no_data"
    res["contract_fill"] = fill


# ------------------------------------------------------------------- outputs
def write_json(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1, default=str)
    tmp.replace(p)


def write_csv(p, cands):
    cols = ["id", "rank", "title", "authors", "year", "venue", "doi", "pmid", "url",
            "type", "source_dbs", "query_ids", "retrieved_at", "relevance_score",
            "included", "metadata_confidence", "cluster_id", "evidence_locator", "flags"]
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in cands:
            row = dict(c)
            row["authors"] = "; ".join((a.get("name") or "") for a in (c.get("authors") or []))
            row["source_dbs"] = "|".join(c.get("source_dbs") or [])
            row["query_ids"] = "|".join([q for q in (c.get("query_ids") or []) if q])
            row["evidence_locator"] = (c.get("evidence") or {}).get("locator")
            row["flags"] = "|".join(c.get("flags") or [])
            w.writerow(row)


def write_coverage_md(p, res):
    cov = res.get("coverage") or {}
    lines = ["# Coverage and gaps", "",
             "case_id: `%s`  status: `%s`" % (res.get("case_id"), res.get("status")), "",
             "## Per database", "", "| db | raw records | candidates | unique to this db |",
             "|-|-|-|-|"]
    for db, v in (cov.get("per_db") or {}).items():
        lines.append("| %s | %s | %s | %s |" % (db, v.get("raw_records"), v.get("candidates"),
                                                v.get("unique_to_db")))
    lines += ["", "## Field fill (share of records with a non-null value)", "",
              "| field | merged | " + " | ".join(cov.get("observed_databases") or []) + " |",
              "|-|-" + "-|-" * len(cov.get("observed_databases") or []) + "|"]
    for f, v in (cov.get("field_fill_merged") or {}).items():
        lines.append("| %s | %s | %s |" % (f, v, " | ".join(
            str((cov.get("field_fill") or {}).get(db, {}).get(f)) for db in
            (cov.get("observed_databases") or []))))
    lines += ["", "## Gaps", ""]
    if cov.get("gaps"):
        for g in cov["gaps"]:
            lines.append("- **%s** %s: %s" % (g.get("type"), g.get("database") or g.get("field"),
                                              g.get("detail")))
    else:
        lines.append("- none detected")
    lines += ["", "## Recall", "", "- %s" % json.dumps(cov.get("recall_estimate"), ensure_ascii=False)]
    lines += ["", "## Uncertainty", ""] + ["- %s" % u for u in (res.get("uncertainty") or ["none"])]
    lines += ["", "## Errors", ""] + (["- %s" % json.dumps(e, ensure_ascii=False)
                                       for e in (res.get("errors") or [])] or ["- none"])
    Path(p).write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_check(res, ctx):
    cands = res.get("candidates") or []
    checks = []
    flds = contract_fields(ctx.get("contract")) if ctx.get("contract") is not None else {}
    missing = [n for n in flds if n not in res]
    checks.append({"name": "contract_fields_present", "ok": not missing,
                   "detail": "%d/%d present" % (len(flds) - len(missing), len(flds)),
                   "missing": missing[:20]})
    ids_ok = all(c.get("source_dbs") and c.get("retrieved_at") is not None for c in cands)
    checks.append({"name": "candidate_traceability", "ok": ids_ok,
                   "detail": "%d/%d candidates carry source_dbs + retrieved_at"
                             % (sum(1 for c in cands if c.get("source_dbs") and c.get("retrieved_at") is not None),
                                len(cands))})
    loc = sum(1 for c in cands if (c.get("evidence") or {}).get("locator"))
    checks.append({"name": "evidence_locators", "ok": loc == len(cands),
                   "detail": "%d/%d" % (loc, len(cands))})
    dois = [c.get("doi") for c in cands if c.get("doi")]
    dupes = len(dois) - len(set(dois))
    checks.append({"name": "dedup_invariant_no_duplicate_doi", "ok": dupes == 0,
                   "detail": "%d duplicated DOIs across clusters" % dupes})
    checks.append({"name": "counts_consistent",
                   "ok": res.get("candidate_count") == len(cands),
                   "detail": "candidate_count=%s len=%s" % (res.get("candidate_count"), len(cands))})
    valid = sum(1 for d in dois if re.match(r"^10\.\d{4,9}/\S+$", d))
    checks.append({"name": "doi_syntax", "ok": (not dois) or valid == len(dois),
                   "detail": "%d/%d DOIs match 10.NNNN/... syntax" % (valid, len(dois))})
    q_ok = all(q.get("query_id") and q.get("db") and q.get("status") for q in res.get("queries") or [])
    checks.append({"name": "query_log_complete", "ok": q_ok,
                   "detail": "%d queries logged" % len(res.get("queries") or [])})
    res["self_check"] = {"checks": checks, "all_ok": all(c["ok"] for c in checks),
                         "candidates": len(cands), "queries": len(res.get("queries") or []),
                         "dbs_observed": len(res.get("databases", {}).get("observed") or [])}
    return res["self_check"]


def status_of(res):
    if res["errors"] and not res.get("candidates"):
        if any(e.get("type") in ("case_file_missing", "empty_input") for e in res["errors"]):
            return "input_error"
        return "insufficient_evidence"
    if not res.get("candidates"):
        return "insufficient_evidence"
    if (res.get("databases", {}).get("missing")) or res["errors"] or res["pending_human"]:
        return "partial"
    return "ok"


# --------------------------------------------------------------------- main
def blank():
    return {"skill": "multidb-literature-search", "skill_version": VER,
            "case_id": None, "status": "partial", "generated_at": iso(),
            "databases": {"required": [], "observed": [], "missing": []},
            "queries": [], "candidates": [], "candidate_count": 0,
            "clusters": [], "conflicts": [], "merge_decisions": [], "merge_summary": {},
            "screening": {"include": 0, "exclude": 0, "excluded": [], "criteria": [],
                          "threshold": None},
            "coverage": {}, "baseline_comparison": {}, "metrics": {},
            "sources": [], "evidence": [], "citations": [],
            "uncertainty": [], "pending_human": [], "errors": [], "degradations": [],
            "changes": [], "runtime": {}, "self_check": {},
            "contract_fill": {}, "contract_echo": None,
            "artifacts": {}, "results": [], "notes": []}


def run(args, res):
    inp = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    ctx = {"args": args, "profiles": load_profiles(), "executed": {}, "query_by_db": {},
           "case": None, "case_path": None, "contract": None, "recs": [], "seeds": set(),
           "observed_dbs": [], "groups": {}, "decisions": [], "candidates": [], "queries": []}
    res["runtime"] = {"started_at": iso(T0), "python": sys.version.split()[0],
                      "skill_version": VER, "network": "none",
                      "input_root": str(inp), "output_root": str(out),
                      "budget": {"model_requests": 64, "seconds": 900},
                      "cwd_independent": True}
    discover(inp, ctx, res)
    if ctx["case"] is None and not (ctx["files"]):
        return res
    ctx["scope"] = scope_of(ctx["case"] or {}, ctx["task_md"])
    res["task_instruction"] = (ctx["scope"].get("task_instruction")
                               if isinstance(ctx["scope"].get("task_instruction"), str)
                               else str(ctx["scope"].get("task_instruction") or "")[:2000]) or None
    res["scope"] = ctx["scope"]
    harvest(ctx, res)
    plan_queries(ctx, res)
    if not ctx["recs"]:
        res["uncertainty"].append("No bibliographic record could be harvested from the supplied input; "
                                 "queries are logged as plans only.")
        res["errors"].append({"stage": "harvest", "type": "no_records",
                              "message": "no record-like structure found in any parseable file"})
    else:
        dedup(ctx, res)
        merge_clusters(ctx, res)
        score_all(ctx, res)
        coverage(ctx, res)
        baseline(ctx, res)
        if ctx["pending_dup"]:
            for p in ctx["pending_dup"][:60]:
                p["cluster_a"] = (res["clusters"][p["a"]]["cluster_id"] if p.get("a") is not None
                                  and p["a"] < len(res["clusters"]) else None)
                p.pop("a", None)
                res["pending_human"].append(p)
        evidence_block(ctx, res)
    res["uncertainty"].extend([
        "Offline execution: no database was queried in real time; every record comes from a supplied "
        "response file and is traceable to it.",
        "Relevance scores are lexical overlap + scope priors computed from the input; they are not "
        "human relevance judgements.",
        "Field completeness differs per database; null means 'not supplied by any retrieved response', "
        "not 'does not exist'."])
    if (res.get("databases") or {}).get("missing"):
        res["uncertainty"].append("Required databases without a recorded response: %s. Coverage for "
                                  "these is not claimed."
                                  % ", ".join(res["databases"]["missing"]))
    res["changes"].append({"stage": "run", "action": "pipeline",
                           "detail": "harvested %d raw records -> %d merged candidates"
                                     % (len(ctx["recs"]), len(res.get("candidates") or []))})
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="Multidatabase literature search: per-database query planning, cross-database "
                    "field mapping, explainable deduplication, provenance-preserving merge, coverage "
                    "and gap reporting. Offline (no network), stdlib only.",
        epilog="Example: python3 scripts/main.py --input /input --output /app/output. "
               "Always writes a valid partial result.json first and always exits 0.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="/input", help="input root (default /input)")
    ap.add_argument("--output", default="/app/output", help="output root (default /app/output)")
    ap.add_argument("--work", default="/app/work", help="scratch root (default /app/work, optional)")
    ap.add_argument("--min-score", type=float, default=0.25,
                    help="relevance threshold for screening (default 0.25)")
    ap.add_argument("--max-candidates", type=int, default=0,
                    help="hard cap on emitted candidates (0 = no cap)")
    ap.add_argument("--no-fuzzy", action="store_true",
                    help="disable fuzzy title matching (identifier + exact title only)")
    ap.add_argument("--quiet", action="store_true", help="suppress the summary line")
    args = ap.parse_args(argv)
    out = Path(args.output)
    try:
        out.mkdir(parents=True, exist_ok=True)
        partial = blank()
        write_json(out / "result.json", partial)
    except OSError as e:
        print("warn: cannot write output dir: %s" % e, file=sys.stderr)
    res = blank()
    try:
        run(args, res)
    except Exception as e:  # noqa: BLE001 - contract requires exit 0
        res["errors"].append({"stage": "main", "type": type(e).__name__,
                              "message": str(e)[:500]})
        res["uncertainty"].append("Pipeline raised an exception; results saved up to that point "
                                  "are partial.")
    finally:
        try:
            fill_contract(res, res.get("contract_echo"))
            res["status"] = status_of(res)
            res["runtime"]["elapsed_s"] = round(time.time() - T0, 3)
            res["runtime"]["finished_at"] = iso()
            self_check(res, {"contract": res.get("contract_echo")})
            cands = res.get("candidates") or []
            if args.max_candidates and len(cands) > args.max_candidates:
                cands = cands[:args.max_candidates]
                res["candidates"] = cands
                res["candidate_count"] = len(cands)
            write_json(out / "result.json", res)
            write_json(out / "candidates.json", cands)
            write_csv(out / "candidates.csv", cands)
            write_json(out / "query_log.json", res.get("queries") or [])
            write_json(out / "merge_log.json",
                       {"clusters": res.get("clusters") or [],
                        "decisions": res.get("merge_decisions") or [],
                        "conflicts": res.get("conflicts") or [],
                        "summary": res.get("merge_summary") or {}})
            write_coverage_md(out / "coverage.md", res)
            res["artifacts"] = {k: str(out / v) for k, v in (
                ("result", "result.json"), ("candidates_json", "candidates.json"),
                ("candidates_csv", "candidates.csv"), ("query_log", "query_log.json"),
                ("merge_log", "merge_log.json"), ("coverage", "coverage.md"))}
        except Exception as e:  # noqa: BLE001
            try:
                emergency = {"case_id": res.get("case_id"), "status": "partial",
                             "errors": (res.get("errors") or []) + [
                                 {"stage": "finalize", "type": type(e).__name__,
                                  "message": str(e)[:400]}],
                             "candidates": [], "uncertainty": ["finalize failed; partial output only"]}
                write_json(out / "result.json", emergency)
            except Exception:  # noqa: BLE001
                pass
    if not args.quiet:
        print("[multidb] case=%s status=%s candidates=%s queries=%s dbs=%s"
              % (res.get("case_id"), res.get("status"),
                 res.get("candidate_count"), len(res.get("queries") or []),
                 len((res.get("databases") or {}).get("observed") or [])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        sys.exit(0)
