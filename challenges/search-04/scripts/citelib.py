"""offline citation core (stdlib only)."""
import csv, difflib, hashlib, json, re, unicodedata

MAX_RAW = 30000
GOOD = ("paper", "work", "record", "result", "item", "article", "node", "seed", "reference", "citation",
    "candidate", "entry", "doc", "hit", "publication", "study", "output", "linked", "graph")
BACK = ("reference", "references", "reference_list", "referenceList", "bibliography", "referenced_works", "cites")
FWD = ("citations", "cited_by", "citedby", "citation_list", "citationList", "citing", "inbound", "is_referenced_by")
PAIRS = (("citing", "cited"), ("citing_id", "cited_id"), ("from", "to"), ("src", "dst"), ("source_id", "target_id"),
     ("from_id", "to_id"), ("citing_doi", "cited_doi"), ("parent", "child"))
CONFR = {"high":0, "medium":1, "low":2}
_W = re.compile(r"\s+")
_P = re.compile(r"[^0-9a-z\u4e00-\u9fff ]+")
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_RT = re.compile(r"\b(retract(ed|ion)?|withdrawn?)\b")
_CR = re.compile(r"\b(erratum|corrigendum|correction to|expression of concern)\b")


def nsp(s):
 return _W.sub(" ", str(s)).strip()


def ndoi(v):
 if not v:
  return ""
 s = str(v).strip().lower()
 for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:", "doi "):
  if s.startswith(p):
   s = s[len(p):]
 s = s.strip().strip(".,;:)]}")
 return s if re.fullmatch(r"10\.\d{4,9}/\S+", s) else ""


def noa(v):
 m = re.search(r"(W\d+)", str(v or ""), re.I)
 return m.group(1).upper() if m else ""


def narx(v):
 s = str(v or "").strip()
 s = re.sub(r"^.*arxiv\.org/(?:abs|pdf)/|\.pdf$|^arxiv[:\s]*", "", s, flags=re.I).strip()
 return s if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$|^[a-z\-]+/\d{7}(v\d+)?$", s, re.I) else ""


def nttl(t):
 s = unicodedata.normalize("NFKD", nsp(t)).lower()
 return nsp(_P.sub(" ", re.sub(r"<[^>]+>", " ", s)))


def tkey(t):
 n = nttl(t)
 return n if len(n) >= 15 else ""


def nyear(v):
 if isinstance(v, (list, tuple)) and v:
  v = v[0]
 m = re.search(r"(1[89]\d{2}|20\d{2})", json.dumps(v)[:200] if isinstance(v, dict) else str(v or ""))
 return int(m.group(1)) if m else None


def sk(k):
 return re.sub(r"[^a-z0-9]", "", str(k).lower())


def getf(d, *names):
 if not isinstance(d, dict):
  return None
 ix = {sk(k): k for k in d}
 for n in names:
  k = ix.get(sk(n))
  if k is not None and d[k] not in (None, "", [], {}):
   return d[k]
 return None


def as_text(v, mx=600):
 if v is None:
  return ""
 if isinstance(v, (str, int, float)):
  return nsp(v)[:mx]
 if isinstance(v, dict):
  for k in ("value", "title", "name", "display_name", "article-title", "text", "label"):
   t = getf(v, k)
   if isinstance(t, str) and t.strip():
    return nsp(t)[:mx]
  return ""
 if isinstance(v, list):
  for it in v:
   t = as_text(it, mx)
   if t:
    return t
 return ""


def as_list(v):
 return [] if v is None else (v if isinstance(v, list) else [v])


def items_of(v):
 if isinstance(v, dict):
  for k in ("reference", "references", "citation", "citations", "item", "items", "list", "entry", "entries"):
   w = getf(v, k)
   if w is not None:
    return as_list(w)
  return []
 return as_list(v)


def authors_of(d):
 raw = getf(d, "author", "authors", "creators", "authorList", "authorships", "contributors")
 if isinstance(raw, dict):
  raw = getf(raw, "author", "authors", "items", "list") or []
 out = []
 for a in as_list(raw):
  if isinstance(a, dict) and isinstance(getf(a, "author"), dict):
   a = getf(a, "author")
  if isinstance(a, str):
   nm = a
  elif isinstance(a, dict):
   fam = as_text(getf(a, "family", "lastName", "surname"), 80)
   giv = as_text(getf(a, "given", "firstName"), 80)
   nm = (fam + ", " + giv) if (fam and giv) else (fam or as_text(getf(a, "name", "display_name", "literal"), 120))
  else:
   nm = ""
  nm = nsp(nm)
  if len(nm) > 1 and nm not in out:
   out.append(nm)
 if not out:
  s = as_text(getf(d, "authorString", "author_string"), 500)
  if s:
   out = [nsp(x) for x in re.split(r";|\band\b", s) if nsp(x)][:40]
 return out[:40]


def venue_of(d):
 v = getf(d, "container-title", "journal", "journalTitle", "venue", "source_title", "publication",
      "primary_location", "host_venue")
 while isinstance(v, dict):
  v = getf(v, "source", "display_name", "title", "name")
 return as_text(v, 240)


def ids_of(d):
 out = {}
 doi = ndoi(getf(d, "DOI", "doi"))
 ext = getf(d, "externalIds", "external_ids")
 if not doi and isinstance(ext, dict):
  doi = ndoi(getf(ext, "DOI", "doi"))
 if doi:
  out["doi"] = doi
 for k, ns in (("pmid", ("pmid", "pubmed_id")), ("arxiv", ("arxiv", "arxiv_id", "ArXiv"))):
  v = as_text(getf(d, *ns), 120)
  if v:
   out[k] = v
 v = as_text(getf(d, "openalex_id", "openalex", "work_id"), 200)
 if noa(v):
  out["openalex"] = noa(v)
 rid = as_text(getf(d, "id", "ID"), 200)
 if rid:
  if "openalex.org" in rid.lower():
   out.setdefault("openalex", noa(rid))
  elif re.fullmatch(r"\d{6,9}", rid):
   out.setdefault("pmid", rid)
 s2 = as_text(getf(d, "paperId", "paper_id"), 80)
 if len(s2) > 8:
  out["s2"] = s2
 if doi.startswith("10.48550/arxiv."):
  out.setdefault("arxiv", narx(doi.split(".", 2)[-1]))
 if out.get("arxiv"):
  out["arxiv"] = narx(out["arxiv"]) or out["arxiv"]
 return out


def pkey(d):
 ids = ids_of(d)
 for k in ("doi", "pmid", "openalex", "arxiv", "s2"):
  if ids.get(k):
   return (k, ids[k])
 tk = tkey(as_text(getf(d, "title", "article-title", "article_title", "paper_title", "display_name",
             "primary_title", "short_title"), 400))
 return ("title", tk) if tk else None


def key_of_item(it):
 if isinstance(it, str):
  s = it.strip()
  if ndoi(s):
   return ("doi", ndoi(s))
  m = re.search(r"openalex\.org/(W\d+)", s, re.I)
  if m:
   return ("openalex", m.group(1).upper())
  if re.fullmatch(r"W\d+", s, re.I):
   return ("openalex", s.upper())
  m = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+)", s, re.I)
  if m and narx(m.group(1)):
   return ("arxiv", narx(m.group(1)))
  if re.fullmatch(r"\d{6,9}", s):
   return ("pmid", s)
  tk = tkey(s)
  return ("title", tk) if tk else None
 if isinstance(it, dict):
  return pkey(it) or key_of_item(as_text(it.get("id"), 300))
 return None


def keys_of(rec):
 return [(k, rec["ids"][k]) for k in ("doi", "pmid", "arxiv", "openalex", "s2") if rec["ids"].get(k)] + \
   ([("title", rec["title_key"])] if rec["title_key"] else [])


def _ra(d):
 for k in ("retrieved_at", "fetched_at", "retrieved", "timestamp"):
  v = getf(d, k)
  if v:
   return as_text(v, 40)
 return ""


def flags_of(t, ab, typ, ids):
 low = (t + " " + ab).lower()
 f = []
 if _RT.search(low):
  f.append("retraction_marker")
 if _CR.search(low):
  f.append("correction_marker")
 if typ in ("posted-content", "preprint") or ids.get("doi", "").startswith("10.48550/"):
  f.append("preprint")
 elif typ in ("proceedings-article", "conference"):
  f.append("conference_version")
 if "patent" in typ:
  f.append("patent")
 if _CJK.search(t):
  f.append("non_english_title")
 return f


def record_from(d, src, ra, ptr, hint=""):
 if not isinstance(d, dict) or not d:
  return None
 t = as_text(getf(d, "title", "article-title", "display_name", "orig_title"), 400)
 ids = ids_of(d)
 yr = nyear(getf(d, "year", "pubYear", "publication_year", "issued", "published-print", "published-online",
         "published", "publication_date", "date", "created"))
 au = authors_of(d)
 tk = tkey(t)
 strong = bool(ids.get("doi") or ids.get("pmid") or ids.get("openalex") or ids.get("arxiv") or ids.get("s2"))
 if not strong and not tk:
  return None
 friendly = any(h in str(hint).lower() for h in GOOD)
 if not strong and not (friendly and (yr or au or len(t) > 12)) and not ((yr or au) and len(t) > 12):
  return None
 ab = as_text(getf(d, "abstract", "abstractText", "abstract_text", "summary"), 1500)
 typ = as_text(getf(d, "type", "publication_type", "doc_type", "genre"), 80).lower()
 conf = "high" if (ids.get("doi") and t and yr) else ("medium" if (t and (yr or au)) else "low")
 return {"title":t, "title_key":tk, "ids":ids, "doi":ids.get("doi", ""), "year":yr, "authors":au,
     "venue":venue_of(d), "abstract":ab, "type":typ, "confidence":conf,
     "flags":flags_of(t, ab, typ, ids), "src":src, "ptr":ptr, "retrieved_at":_ra(d) or ra}


def edges_from(d, self_key, src, ptr, fname):
 if not self_key:
  return []
 out = []
 for k, fwd in [(k, 0) for k in BACK] + [(k, 1) for k in FWD]:
  v = getf(d, k)
  if v is None:
   continue
  for i, it in enumerate(items_of(v)):
   kk = key_of_item(it)
   if not kk:
    continue
   out.append({"src_key":kk if fwd else self_key, "dst_key":self_key if fwd else kk, "field":str(k),
         "idx":i, "src_file":src, "ptr":ptr, "ra":_ra(d)})
 if len(d) <= 14 and (re.search(r"cit|ref|edge|graph|link", fname, re.I) or
            getf(d, "relation", "direction", "edge", "database", "source_db")):
  for a, b in PAIRS:
   va, vb = getf(d, a), getf(d, b)
   if isinstance(va, str) and isinstance(vb, str) and len(va) > 2 and len(vb) > 2:
    ka, kb = key_of_item(va), key_of_item(vb)
    if ka and kb and ka != kb:
     out.append({"src_key":ka, "dst_key":kb, "field":a + "->" + b, "idx":0, "src_file":src, "ptr":ptr,
           "ra":_ra(d)})
    break
 return out


def harvest(node, src, ra, hint, ptr, recs, edges, depth=0):
 if depth > 40 or len(recs) >= MAX_RAW:
  return
 if isinstance(node, dict):
  rec = record_from(node, src, ra, ptr, hint)
  if rec:
   recs.append(rec)
   edges.extend(edges_from(node, pkey(node), src, ptr, src))
  for k, v in node.items():
   if isinstance(v, (dict, list)):
    harvest(v, src, ra, str(k), ptr + "/" + str(k), recs, edges, depth + 1)
   elif isinstance(v, str) and len(v) > 60 and v.lstrip()[:1] in "[{":
    try:
     harvest(json.loads(v), src, ra, str(k), ptr + "/" + str(k), recs, edges, depth + 1)
    except Exception:
     pass
 elif isinstance(node, list):
  for i, v in enumerate(node):
   harvest(v, src, ra, hint, ptr + "/" + str(i), recs, edges, depth + 1)


class UF(object):
 def __init__(self, n):
  self.p = list(range(n))

 def find(self, x):
  p = self.p
  while p[x] != x:
   p[x] = p[p[x]]
   x = p[x]
  return x

 def union(self, a, b):
  ra, rb = self.find(a), self.find(b)
  if ra != rb:
   self.p[rb] = ra
  return ra != rb


def build_index(recs, merges):
 n = len(recs)
 uf = UF(n)
 by = {}
 for i, r in enumerate(recs):
  for k in keys_of(r):
   by.setdefault(k, []).append(i)
 for k, ix in by.items():
  if len(ix) < 2 or k[0] == "title":
   continue
  for j in ix[1:]:
   if uf.union(ix[0], j):
    merges.append({"rule":"exact_" + k[0], "key":k[0] + ":" + k[1][:80]})
 tm = {}
 for i, r in enumerate(recs):
  if len(r["title_key"]) >= 20:
   tm.setdefault(r["title_key"], []).append(i)
 for tk, ix in tm.items():
  if len(ix) < 2:
   continue
  ys = [recs[i]["year"] for i in ix if recs[i]["year"]]
  if ys and (max(ys) - min(ys)) > 3:
   for i in ix:
    if "homonym_suspect" not in recs[i]["flags"]:
     recs[i]["flags"].append("homonym_suspect")
   continue
  for j in ix[1:]:
   if uf.union(ix[0], j):
    merges.append({"rule":"title_exact", "key":"title:" + tk[:70]})
 bl = {}
 for i, r in enumerate(recs):
  if len(r["title_key"]) >= 25:
   bl.setdefault(r["title_key"][:32], []).append(i)
 for ix in bl.values():
  if len(ix) < 2 or len(ix) > 40:
   continue
  for a in range(len(ix)):
   for b in range(a + 1, len(ix)):
    i, j = ix[a], ix[b]
    if uf.find(i) == uf.find(j):
     continue
    ti, tj = recs[i]["title_key"], recs[j]["title_key"]
    if abs(len(ti) - len(tj)) > max(len(ti), len(tj)) * 0.35:
     continue
    if difflib.SequenceMatcher(None, ti, tj).ratio() < 0.93:
     continue
    yi, yj = recs[i]["year"], recs[j]["year"]
    if yi and yj and abs(yi - yj) > 1:
     continue
    ai = set(x.split()[-1].lower() for x in recs[i]["authors"])
    aj = set(x.split()[-1].lower() for x in recs[j]["authors"])
    if ai and aj and not (ai & aj):
     continue
    if uf.union(i, j):
     merges.append({"rule":"title_fuzzy", "key":"title:fuzzy:" + ti[:60]})
 groups = {}
 for i in range(n):
  groups.setdefault(uf.find(i), []).append(i)
 works, k2w = {}, {}
 for ix in groups.values():
  parts = sorted([recs[i] for i in ix], key=lambda r: (CONFR[r["confidence"]], -len(r["abstract"])))
  ids = {}
  for p in parts:
   for k, v in p["ids"].items():
    ids.setdefault(k, v)
  title = next((p["title"] for p in parts if len(p["title"]) > 6), parts[0]["title"])
  wid = ""
  for k in ("doi", "pmid", "openalex", "arxiv", "s2"):
   if ids.get(k):
    wid = k + ":" + ids[k]
    break
  if not wid:
   wid = "ttl:" + hashlib.sha1((tkey(title) or title).encode("utf-8")).hexdigest()[:10]
  works[wid] = {"id":wid, "doi":ids.get("doi", ""), "ids":ids, "title":title, "title_key":tkey(title),
         "authors":next((p["authors"] for p in parts if p["authors"]), []),
         "year":next((p["year"] for p in parts if p["year"]), None),
         "venue":next((p["venue"] for p in parts if p["venue"]), ""),
         "abstract":next((p["abstract"] for p in parts if len(p["abstract"]) > 40), ""),
         "flags":sorted(set(f for p in parts for f in p["flags"])),
         "metadata_confidence":min((p["confidence"] for p in parts), key=lambda c: CONFR[c]),
         "retrieved_at":next((p["retrieved_at"] for p in parts if p["retrieved_at"]), ""),
         "provenance":[{"file":p["src"], "json_pointer":p["ptr"],
                 "retrieved_at":p["retrieved_at"] or ""} for p in parts][:4]}
  for p in parts:
   for k in keys_of(p):
    k2w.setdefault(k, wid)
 return works, k2w


def resolve_edges(raw, works, k2w, st):
 out, seen, bp = [], set(), {}
 for e in raw:
  a, b = k2w.get(e["src_key"]), k2w.get(e["dst_key"])
  if not a or not b or a == b:
   st["edges_unresolved"] = st.get("edges_unresolved", 0) + (0 if (a and b) else 1)
   continue
  ev = {"file":e["src_file"], "json_pointer":e["ptr"], "field":e["field"], "item_index":e["idx"],
     "retrieved_at":e["ra"]}
  if (a, b) in seen:
   if len(bp[(a, b)]["evidence"]) < 5:
    bp[(a, b)]["evidence"].append(ev)
   continue
  seen.add((a, b))
  ed = {"src":a, "dst":b, "rel":"cites", "id":"e%05d" % len(out), "src_file":e["src_file"], "evidence":[ev]}
  out.append(ed)
  bp[(a, b)] = ed
 st["edges_raw"] = len(raw)
 st["edges_kept"] = len(out)
 return out


def adjacency(edges):
 o, i = {}, {}
 for e in edges:
  o.setdefault(e["src"], []).append(e)
  i.setdefault(e["dst"], []).append(e)
 return o, i


def degree_map(edges):
 d = {}
 for e in edges:
  d[e["src"]] = d.get(e["src"], 0) + 1
  d[e["dst"]] = d.get(e["dst"], 0) + 1
 return d


def overlap(toks, text):
 if not toks:
  return 0.0
 t = set(toks)
 hit = len(t & set(w for w in nttl(text).split() if len(w) > 2))
 return round(min(1.0, hit / float(max(1, min(len(t), 4)))), 3)


def set_metrics(items):
 n = len(items)
 if not n:
  return {"n_items":0, "n_unique_works":0, "duplicate_rate":None, "doi_rate":None,
      "direction_labeled_rate":None, "locator_rate":None, "related_basis_rate":None}
 u = len(set(i["uniq"] for i in items))
 r = lambda f: round(sum(1 for i in items if i.get(f)) / float(n), 3)
 return {"n_items":n, "n_unique_works":u, "duplicate_rate":round(1 - u / float(n), 3), "doi_rate":r("doi"),
     "direction_labeled_rate":r("direction"), "locator_rate":r("locator"), "related_basis_rate":r("basis")}


def self_check(R, cands, edges):
 loc = sum(1 for c in cands if (c.get("source_locator") or {}).get("file"))
 bad = sum(1 for c in cands if c.get("doi") and not re.fullmatch(r"10\.\d{4,9}/\S+", c["doi"]))
 out = [{"id":"contract_complete", "passed":not R.get("contract_missing"),
     "detail":str(R.get("contract_missing") or "none")},
     {"id":"case_id_present", "passed":bool(R.get("case_id")), "detail":str(R.get("case_id"))},
     {"id":"locator_present", "passed":loc == len(cands), "detail":"%d/%d" % (loc, len(cands))},
     {"id":"doi_well_formed", "passed":bad == 0, "detail":"%d bad" % bad},
     {"id":"direction_labeled", "passed":all(c["citation_relation"]["direction"] for c in cands)},
     {"id":"no_fabricated_recall", "passed":R.get("coverage", {}).get("recall_estimate") is None},
     {"id":"screening_complete", "passed":R.get("screening") is None or
     len(R["screening"]) >= len(cands), "detail":"%d rows" % len(R.get("screening") or [])}]
 return out, all(c["passed"] for c in out)


def assemble(pairs, works, rel, db_of):
 out = []
 for i, (wid, c) in enumerate(pairs, 1):
  w = works.get(wid, {})
  d = c["channel"] if c["channel"] in ("forward", "backward", "parallel") else "seed"
  ev = [{"edge_id":e.get("id"), "file":x.get("file"), "json_pointer":x.get("json_pointer"),
      "field":x.get("field"), "retrieved_at":x.get("retrieved_at"),
      "direction":"cites" if e["src"] == wid else "cited_by"}
     for e in c.get("edges", [])[:3] for x in e.get("evidence", [])[:2]]
  rr = [r for r in rel if r["work_id"] == wid]
  via = works.get(c.get("via") or "", {})
  why = ["seed"] if d == "seed" else ["%s %s hop%d" % ({"forward":"cited by", "backward":"cites",
      "parallel":"parallel to"}[d], (via.get("title") or c.get("via") or "seed")[:60], c["hop"])]
  if rr:
   why.append(rr[0]["basis"])
  b = c["bd"]
  why.append("relation %.2f proximity %.2f topical %.2f centrality %.2f recency %.2f"
        % (b["relation"], b["proximity"], b["topical"], b["centrality"], b["recency"]))
  pv = (w.get("provenance") or [{}])[0]
  out.append({"candidate_id":"c%03d" % i, "work_id":wid, "title":w.get("title", ""),
        "authors":w.get("authors", []), "year":w.get("year"), "venue":w.get("venue", ""),
        "doi":w.get("doi", ""), "url":("https://doi.org/" + w["doi"]) if w.get("doi") else "",
        "source_db":db_of(pv.get("file", "")), "source_locator":pv,
        "retrieved_at":pv.get("retrieved_at") or w.get("retrieved_at") or "", "hop":c["hop"],
        "channel":d, "via_work":c.get("via"), "relevance_score":c["score"], "relevance_breakdown":b,
        "relevance_reason":"; ".join(why), "metadata_confidence":w.get("metadata_confidence"),
        "flags":w.get("flags", []), "evidence":ev,
        "evidence_snippet":(w.get("abstract") or w.get("title") or "")[:220],
        "citation_relation":{"direction":d, "edge_ids":[e.get("id") for e in c.get("edges", [])][:5],
                   "hop_count":c["hop"]},
        "path":"seed" if d == "seed" else "%s > %s" % ((via.get("title") or c.get("via") or "seed")[:38],
                                 (w.get("title") or "")[:38]),
        "related_evidence":({"basis":rr[0]["basis"], "shared_references":rr[0].get("shared_references", []),
                   "co_citing_works":rr[0].get("co_citing_works", [])} if rr else None)})
 return out

def seed_specs(case):
 """Seed hints: keys named *seed*/*start_paper*/*focal*, skipping the output_contract subtree.
 Only identifier-like or title-like values are accepted, so schema prose is never treated as a seed."""
 out = []

 def add(v):
  v = (v or "").strip()
  if len(v) < 5 or v in out:
   return
  if ndoi(v) or noa(v) or re.fullmatch(r"\d{6,9}", v) or len(tkey(v)) >= 15:
   out.append(v)

 def walk(n, d=0):
  if d > 8:
   return
  if isinstance(n, list):
   for v in n:
    walk(v, d + 1)
   return
  if not isinstance(n, dict):
   return
  for k, v in n.items():
   kn = re.sub(r"[^a-z]", "", str(k).lower())
   if kn.startswith(("outputcontract", "requiredoutput")):
    continue
   if any(x in kn for x in ("seed", "startpaper", "focal")):
    for it in (v if isinstance(v, list) else [v]):
     if isinstance(it, str):
      add(it)
     elif isinstance(it, dict):
      for x in ("doi", "title", "pmid", "openalex_id", "id"):
       val = as_text(getf(it, x), 300)
       if val:
        add(val)
        break
   walk(v, d + 1)

 walk(case)
 return out


def trs(t):
 o = [{"doi": m.group(1).rstrip(".")} for m in re.finditer(r"(10\.\d{4,9}/[^\s,;\"'()\]}<>]+)", t)]
 return o[:MAX_RAW]


def tbl(t):
 rs = list(csv.reader(t.splitlines()))
 if not rs:
  return []
 o, h = [], [re.sub(r"[^a-z]", "", str(x).lower()) for x in rs[0]]
 for r in rs[1:]:
  g, c = {}, {}
  for k, v in zip(h, r):
   v = str(v).strip()
   if not v or len(v) > 400:
    continue
   d = c if "citing" in k else (g if "cited" in k else None)
   if d is None:
    d = g
   if "doi" in k or "id" in k:
    d["doi"] = v
   elif "title" in k:
    d["title"] = v
  if g.get("doi") and c.get("doi") and g["doi"] != c["doi"]:
   g["citing"] = c["doi"]
   o += [g, c]
  elif g.get("doi") or g.get("title"):
   o.append(g)
 return o[:MAX_RAW]
