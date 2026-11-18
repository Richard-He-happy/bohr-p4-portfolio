"""Engine: discovery, language ID, concepts, scoring, version merge, evidence."""
import csv, json, os, re, time, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

V = "1.0.0"
REF = Path(__file__).resolve().parent.parent / "references"
OKL = ("en", "pt", "es", "fr", "de", "it", "ja", "zh", "ru", "ko")
TK = ("title", "titulo", "titre", "titel", "paper_title", "article_title")
AK = ("abstract", "resumo", "resume", "summary", "zusammenfassung", "abstract_text")
DK = ("doi", "doi_url", "identifier")
LK = ("lang", "language", "body_language", "language_code", "idioma", "lingua")
YK = ("year", "publication_year", "pub_year", "ano")
SK = ("venue", "journal", "source_title", "publication", "container_title")
NK = ("authors", "author", "autores", "creator", "creators")
UK = ("url", "link", "fulltext_url", "landing_page")
RK = ("version", "view_type", "version_type", "version_role", "is_translation",
   "is_translation_of", "translation_of", "duplicate_of", "same_as")
LMAP = {"english": "en", "eng": "en", "portuguese": "pt", "portugues": "pt", "por": "pt",
    "spanish": "es", "espanol": "es", "spa": "es", "french": "fr", "fre": "fr",
    "german": "de", "ger": "de", "italian": "it"}
STOP = {
"en": set("the of and in for with that this from were was are study results patients "
     "using between among effect effects we our their has have been not which than "
     "into during after is be by as on at to or it can may more which what paper "
           "papers report reports review reviews evidence compared".split()),
"pt": set("de da do das dos e em para com que os as um uma no na nos nas ao aos pelo "
     "pela se por como mais entre durante apos sobre foi ser sua seu suas quais "
           "qual artigo artigos relata relatam avalia avaliar sendo tambem lesao "
           "evidencia efeito efeitos tratamento podem estudo estudos".split()),
"es": set("de la el los las y en para con que un una del al por se como mas entre "
     "durante fue su sus".split()),
"fr": set("de la le les des et en pour avec que un une du au par dans sur entre".split()),
"de": set("der die das und von mit fur den des im ist sind eine einer bei nach".split())}
SUF = {"pt": ("cao", "coes", "mento", "dade"), "en": ("tion", "ity", "ness"),
   "es": ("cion", "ciones", "dad"), "fr": ("tion", "ement"), "de": ("ung", "keit")}
DIA = {"pt": "ãõ", "es": "ñ", "fr": "êèàûœ", "de": "ßäöü"}
SCR = (("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"),
   ("zh", r"[\u4e00-\u9fff]"), ("ru", r"[\u0400-\u04ff]"))
PAIRS = (("cao", "tion"), ("coes", "tions"), ("dade", "ity"), ("mento", "ment"),
    ("ico", "ic"), ("oso", "ous"), ("encia", "ence"), ("logia", "logy"),
    ("ite", "itis"), ("ose", "osis"))


def now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def deacc(s):
  s = unicodedata.normalize("NFKD", str(s or ""))
  return "".join(c for c in s if not unicodedata.combining(c))


def nz(s):
  s = re.sub(r"[^0-9a-z\u0400-\u04ff\u3040-\u30ff\u4e00-\u9fff]+", " ", deacc(s).lower())
  return re.sub(r"\s+", " ", s).strip()


def toks(s):
  return [t for t in nz(s).split() if len(t) > 1]


def doi_n(d):
  if not d:
    return None
  d = re.sub(r"^(https?://)?(dx\.)?doi\.org/|^doi:\s*", "", str(d).lower().strip())
  return d.strip(" .,;:)]\"'") or None


def wj(p, o):
  p.parent.mkdir(parents=True, exist_ok=True)
  q = p.with_name(p.name + ".tmp")
  q.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
  os.replace(q, p)


def pick(d, ks):
  if not isinstance(d, dict):
    return None
  low = {str(k).lower(): v for k, v in d.items()}
  for k in ks:
    if low.get(k) not in (None, "", [], {}):
      return low[k]
  return None


def langid(t):
  """(code, confidence, evidence): script, then stopwords, diacritics, suffixes"""
  t = str(t or "")
  if not t.strip():
    return "unknown", 0.0, ["empty_text"]
  na = len(re.findall(r"[^\W\d_]", t))
  for c, p in SCR:
    if len(re.findall(p, t)) >= (1 if c in ("ja", "ko") else 0.15 * na):
      return c, 0.95, ["script:" + c]
  tl = toks(t)
  if not tl:
    return "unknown", 0.0, ["no_tokens"]
  low, sc = t.lower(), Counter()
  for c, ws in STOP.items():
    h = {w for w in tl if w in ws}
    sc[c] = len(h) + (0.5 if len(h) > 1 else 0)
  for c, ch in DIA.items():
    sc[c] += 1.5 * min(sum(low.count(x) for x in ch), 3)
  for w in set(tl):
    for c, sf in SUF.items():
      if len(w) > 5 and w.endswith(sf):
        sc[c] += 0.3
  b, bs = sc.most_common(1)[0]
  tot = sum(v for v in sc.values() if v > 0) or 1.0
  if bs < 2:
    return "unknown", round(min(bs / tot, 0.98), 2), ["weak_evidence"]
  return b, round(min(bs / tot, 0.98), 2), ["stopwords:" + b, "share:%.2f" % (bs / tot)]


def glossary():
  p = REF / "glossary.tsv"
  if not p.exists():
    return [], [], "glossary_missing"
  rows, hdr = [], []
  for ln in p.read_text(encoding="utf-8").splitlines():
    if not ln.strip() or ln.startswith("#"):
      continue
    q = [x.strip() for x in ln.split("\t")]
    if hdr:
      rows.append(dict(zip(hdr, q)))
    else:
      hdr = q
  return rows, hdr, None


def cognate(t, src, dst):
  """productive suffix rewrite, English <-> Portuguese/Spanish only"""
  if not t or " " in t:
    return None
  fwd = src == "en" and dst in ("pt", "es")
  if not fwd and not (src in ("pt", "es") and dst == "en"):
    return None
  for a, b in PAIRS:
    x, y = (b, a) if fwd else (a, b)
    if t.endswith(x) and len(t) - len(x) >= 3:
      return t[:-len(x)] + y
  return None


def concepts_of(q, ql, gl, gh):
  """concept table: glossary entries hit by the question + literal content terms"""
  langs = [h for h in gh if h not in ("concept_id", "note", "abbrev")]
  qn, qt, out, seen = " " + nz(q) + " ", set(toks(q)), [], set()
  for row in gl:
    cid, vs, hit = row.get("concept_id") or "?", [], False
    for lg in langs:
      term = (row.get(lg) or "").strip()
      if term:
        vs.append({"lang": lg, "surface": term, "norm": nz(term),
             "method": "glossary_exact", "weight": 1.0})
        hit = hit or (" " + nz(term) + " ") in qn
    if row.get("abbrev"):
      vs.append({"lang": "und", "surface": row["abbrev"], "norm": nz(row["abbrev"]),
           "method": "glossary_abbrev", "weight": 1.0})
      hit = hit or nz(row["abbrev"]) in qt
    if hit and cid not in seen:
      seen.add(cid)
      out.append({"id": cid, "weight": 1.5, "in_question": True, "variants": vs})
  known = {v["norm"] for c in out for v in c["variants"]}
  known |= {w for n in known for w in n.split()}
  st = STOP.get(ql, set()) | STOP["en"]
  for w in dict.fromkeys(toks(q)):
    if len(w) > 3 and not w.isdigit() and w not in st and w not in known:
      out.append({"id": "term:" + w, "weight": 1.0, "in_question": True,
            "variants": [{"lang": ql, "surface": w, "norm": w,
                   "method": "question_literal", "weight": 1.0}]})
  return out


def expand(cs, gh, ql, blob):
  """add rule-derived target-language variants where the glossary has none"""
  langs = [h for h in gh if h not in ("concept_id", "note", "abbrev")]
  got = []
  for c in cs:
    have = {v["lang"] for v in c["variants"]}
    base = next((v for v in c["variants"] if v["lang"] == ql), c["variants"][0])
    for lg in langs:
      if lg in have or lg == ql:
        continue
      g = cognate(base["norm"], base["lang"], lg)
      if not g:
        continue
      hit = (" " + g + " ") in blob
      if len(g) > 6 or hit:
        c["variants"].append({"lang": lg, "surface": g, "norm": g,
                   "method": "cognate_rule", "weight": 0.6})
        got.append({"concept": c["id"], "lang": lg, "term": g,
              "method": "cognate_rule", "found_in_corpus": hit})
  return got


def jload(p):
  t = p.read_text(encoding="utf-8", errors="replace")
  try:
    return json.loads(t), None
  except Exception as e:
    r = []
    for ln in t.splitlines()[:20000]:
      ln = ln.strip().rstrip(",")
      if ln and ln not in "[]{}":
        try:
          r.append(json.loads(ln))
        except Exception:
          pass
    return (r, "jsonl_fallback") if r else (None, type(e).__name__)


def authors(v):
  if not v:
    return []
  if isinstance(v, str):
    return [x.strip() for x in re.split(r";| and | & ", v) if x.strip()][:30]
  return [str(a.get("name") or a.get("family") or "") if isinstance(a, dict) else str(a)
      for a in (v if isinstance(v, list) else [v])][:30]


def recish(d):
  return isinstance(d, dict) and bool(pick(d, TK)) and any(
    pick(d, k) for k in (AK, DK, YK, NK, SK, LK))


def harvest(o, src, loc, out, dep=0):
  """any JSON shape: collect dicts that look like bibliographic records"""
  if dep > 12:
    return
  if isinstance(o, dict):
    if recish(o):
      d = dict(o)
      d["__s__"], d["__l__"] = str(src), loc
      out.append(d)
    else:
      for k, v in o.items():
        harvest(v, src, "%s/%s" % (loc, k), out, dep + 1)
  elif isinstance(o, list):
    for i, v in enumerate(o):
      harvest(v, src, "%s[%d]" % (loc, i), out, dep + 1)


def norm_rec(d, i):
  raw = str(pick(d, LK) or "").lower().strip()
  lf = LMAP.get(raw, raw)[:2]
  ti = str(pick(d, TK) or "").strip()
  ab = pick(d, AK)
  ab = " ".join(map(str, ab)) if isinstance(ab, list) else str(ab or "")
  y = pick(d, YK)
  if isinstance(y, dict):
    y = pick(y, ("year", "value", "date-parts"))
  ym = re.search(r"(1[6-9]\d\d|20\d\d)", str(y or ""))
  if lf in OKL:
    lg, cf, ev = lf, 0.95, ["declared_field"]
  else:
    lg, cf, ev = langid(ti + " " + ab[:400])
    ev = ev + ["inferred_from_text"]
  return {"rec_id": "r%03d" % i, "title": ti, "abstract": ab[:5000],
      "authors": authors(pick(d, NK)), "year": int(ym.group(1)) if ym else None,
      "venue": str(pick(d, SK) or ""), "doi": doi_n(pick(d, DK)),
      "url": str(pick(d, UK) or ""), "lang": lg, "lang_conf": cf, "lang_ev": ev,
      "ver": {k: pick(d, [k]) for k in RK if pick(d, [k]) is not None},
      "src": str(d.get("__s__") or ""), "loc": str(d.get("__l__") or "")}


def scan(root, extra):
  """semantic discovery: decode by content, never by file label"""
  recs, files, errs, unsup = [], [], [], []
  ps = sorted(p for p in root.rglob("*")
        if p.is_file() and not p.name.startswith(".")) if root.is_dir() else []
  ps += [Path(x) for x in extra if x and Path(x).exists()]
  for p in ps:
    s, n0 = p.suffix.lower(), len(recs)
    if s in (".json", ".jsonl", ".ndjson"):
      o, nt = jload(p)
      if o is None:
        errs.append({"stage": "parse", "file": str(p), "detail": nt, "handled": True})
        continue
      harvest(o, p, "$", recs)
      files.append({"path": str(p), "kind": "json", "records": len(recs) - n0, "note": nt})
    elif s in (".csv", ".tsv"):
      t = p.read_text(encoding="utf-8", errors="replace")
      try:
        for i, row in enumerate(csv.DictReader(
            t.splitlines(), delimiter="\t" if t.count("\t") > t.count(",") else ",")):
          if recish(row):
            row = dict(row)
            row["__s__"], row["__l__"] = str(p), "$/row[%d]" % i
            recs.append(row)
      except Exception as e:
        errs.append({"stage": "parse", "file": str(p), "detail": str(e), "handled": True})
      files.append({"path": str(p), "kind": "table", "records": len(recs) - n0})
    elif s in (".pdf", ".png", ".jpg", ".docx", ".xlsx", ".zip"):
      unsup.append({"path": str(p), "reason": "binary_or_pdf_not_text_parsed_offline"})
    else:
      files.append({"path": str(p), "kind": "text", "records": 0, "note": "context_only"})
  seen, out = set(), []
  for d in recs:
    r = norm_rec(d, len(out))
    k = (r["doi"] or "", nz(r["title"])[:120], r["lang"])
    if k not in seen:
      seen.add(k)
      out.append(r)
  return out, files, errs, unsup


def jac(a, b):
  x, y = set(toks(a)), set(toks(b))
  return len(x & y) / len(x | y) if x and y else 0.0


def cluster(recs):
  """union-find over DOI, declared work/translation links, near-identical titles"""
  par, rules = list(range(len(recs))), {}

  def f(x):
    while par[x] != x:
      par[x] = par[par[x]]
      x = par[x]
    return x

  def u(a, b, r):
    if f(a) != f(b):
      par[f(b)] = f(a)
      rules[r] = rules.get(r, 0) + 1

  byd = defaultdict(list)
  for i, r in enumerate(recs):
    if r["doi"]:
      byd[r["doi"]].append(i)
  for ix in byd.values():
    for j in ix[1:]:
      u(ix[0], j, "same_doi")
  for i, r in enumerate(recs):
    for k in ("work_id", "record_id", "openalex_id"):
      for j, o in enumerate(recs):
        if j != i and r["ver"].get(k) and o["ver"].get(k) == r["ver"][k]:
          u(i, j, "same_declared_work_id")
    for k in ("is_translation_of", "translation_of", "duplicate_of", "same_as"):
      v = r["ver"].get(k)
      if not v:
        continue
      t = doi_n(v) or str(v).lower()
      for j, o in enumerate(recs):
        if j != i and (o["doi"] == t or o["rec_id"] == t
               or nz(o["title"])[:80] == nz(t)[:80]):
          u(i, j, "declared_" + k)
  for i in range(len(recs)):
    for j in range(i + 1, len(recs)):
      a, b = recs[i], recs[j]
      if f(i) == f(j) or (a["year"] and b["year"] and a["year"] != b["year"]):
        continue
      if jac(a["title"], b["title"]) >= 0.9 and len(toks(a["title"])) >= 3:
        u(i, j, "title_jaccard>=0.9")
  g = defaultdict(list)
  for i in range(len(recs)):
    g[f(i)].append(i)
  return [{"wid": "w%02d" % (k + 1), "ix": v,
      "langs": sorted({recs[i]["lang"] for i in v}),
      "doi": next((recs[i]["doi"] for i in v if recs[i]["doi"]), None)}
      for k, v in enumerate(g.values())], rules


BAD = {"The", "This", "That", "Study", "Table", "Figure", "Find", "From", "With",
   "During", "After", "Which", "What", "Using", "We", "Our"}


def anchors(q):
  """citation anchors: DOI, years, author-like capitalised tokens"""
  return {"doi": [x for x in (doi_n(y) for y in
                re.findall(r"10\.\d{4,9}/[^\s,;)\]\"']+", q)) if x],
      "years": sorted({int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", q)}),
      "surnames": [c for c in re.findall(r"\b([A-ZÀ-Ý][a-zà-ÿ]{2,15})\b", q)
            if c not in BAD][:10],
      "method": "regex: DOI, 4-digit year, capitalised token minus stoplist"}


def score(r, cs, an):
  txt = {"title": " " + nz(r["title"]) + " ", "abstract": " " + nz(r["abstract"]) + " "}
  tot = sum(c["weight"] for c in cs) or 1.0
  got, mt = 0.0, []
  for c in cs:
    best, hit = 0.0, None
    for v in c["variants"]:
      t = v["norm"]
      if len(t) < 3:
        continue
      for fld, mult in (("title", 1.0), ("abstract", 0.75)):
        if (" " + t + " ") in txt[fld]:
          s = v["weight"] * mult
          if s > best:
            al = "native" if v["lang"] == r["lang"] else (
              "abbrev" if v["lang"] == "und"
              or "unknown" in (v["lang"], r["lang"])
              else "loanword")
            best, hit = s, {"concept": c["id"], "surface": v["surface"],
                    "field": fld, "variant_lang": v["lang"],
                    "method": v["method"], "alignment": al,
                    "score": round(s, 3)}
          break
    if hit:
      got += best
      mt.append(hit)
  bo, bl = 0.0, []
  if r["doi"] and r["doi"] in an["doi"]:
    bo, bl = bo + 0.5, bl + ["doi_exact"]
  if r["year"] and r["year"] in an["years"]:
    bo, bl = bo + 0.15, bl + ["year_match"]
  if r["authors"] and an["surnames"]:
    aj = " " + nz(" ".join(r["authors"])) + " "
    h = [x for x in an["surnames"] if (" " + nz(x) + " ") in aj]
    if h:
      bo, bl = bo + min(0.25, 0.12 * len(h)), bl + ["author_match:" + ",".join(h[:2])]
  return {"base": round(got / tot, 4), "bonus": round(bo, 3),
      "score": round(min(1.0, got / tot + bo), 4), "matched": mt, "bonus_evidence": bl}


def plan(cs, langs, an):
  """one AND-query per target language (OR within a concept) + a citation query"""
  qs = []
  for lg in langs:
    tg, miss = [], []
    for c in cs:
      vs = sorted({v["surface"] for v in c["variants"] if v["lang"] == lg})
      if vs:
        tg.append({"concept": c["id"], "terms": vs,
             "methods": sorted({v["method"] for v in c["variants"]
                       if v["lang"] == lg})})
      else:
        miss.append(c["id"])
    qs.append({"lang": lg, "status": "planned" if tg else "no_term_mapping",
         "term_groups": tg, "missing_concepts": miss,
         "raw": " AND ".join("(" + " OR ".join('"%s"' % t for t in g["terms"]) + ")"
                   for g in tg)})
  a = ['DOI:"%s"' % x for x in an["doi"][:3]] + \
    ['AU:"%s"' % x for x in an["surnames"][:3]] + ["PY:%d" % y for y in an["years"][:2]]
  if a:
    qs.append({"lang": "und", "status": "planned", "raw": " AND ".join(a),
         "missing_concepts": [],
         "term_groups": [{"concept": "citation_anchor", "terms": a,
                  "methods": ["regex_anchor"]}]})
  return qs


def retrieve(recs, cs, langs, an):
  """executes the plan on the local corpus; returns (query log, plan)"""
  qs, log = plan(cs, langs, an), []
  for i, q in enumerate(qs):
    e = {"query_id": "q%02d" % (i + 1), "lang": q["lang"], "raw": q.get("raw", ""),
      "db": "local_corpus", "retrieved_at": now(),
      "missing_concepts": q["missing_concepts"],
      "expanded": [g["terms"] for g in q["term_groups"]],
      "methods": sorted({m for g in q["term_groups"] for m in g["methods"]})}
    if q["status"] != "planned":
      e.update({"hits": 0, "status": "no_term_mapping", "filters": {},
           "error": "no glossary or cognate variant for this language"})
    else:
      keep = [c for c in cs if c["id"] in {g["concept"] for g in q["term_groups"]}]
      n = sum(1 for r in recs if score(r, keep, an)["score"] > 0)
      e.update({"hits": n, "filters": {"language": q["lang"]},
           "status": "ok" if n else "empty_result"})
    log.append(e)
  return log, qs


def evid(r, mt):
  """sentence carrying the most matched terms, plus a character-level locator"""
  sur = [m["surface"] for m in mt if m.get("surface")]
  for fld, txt in (("title", r["title"]), ("abstract", r["abstract"])):
    if not txt:
      continue
    off, best = 0, None
    for si, s in enumerate(re.split(r"(?<=[.!?。！？])\s+", txt)):
      ns = " " + nz(s) + " "
      cov = [x for x in sur if (" " + nz(x) + " ") in ns]
      if cov and (best is None or len(cov) > len(best[1])):
        best = (si, cov, s.strip()[:400], off)
      off += len(s) + 1
    if best:
      si, cov, qt, off = best
      ok = "exact" if qt in txt else (
        "deaccented_normalized" if nz(qt) in nz(txt) else "failed")
      return {"quote": qt, "quote_match": ok, "field": fld, "covered": cov,
          "locator": "%s#%s:%s[s%d]+%d" % (r["src"], r["loc"], fld, si, off)}
  return {"quote": None, "quote_match": "no_span", "field": None, "covered": [],
      "locator": "%s#%s" % (r["src"], r["loc"])}


def fill(res, con):
  """guarantee every output_contract field exists; key names and order untouched"""
  if isinstance(con, dict):
    items = list(con.items())
  elif isinstance(con, list):
    items = [(e, None) if isinstance(e, str) else
        (e.get("name") or e.get("field") or e.get("key"),
         e.get("type") or e.get("description"))
        for e in con if isinstance(e, (str, dict))]
  else:
    items = []
  for k, h in items:
    if k and k not in res:
      t = str(h).lower() if h is not None else ""
      res[k] = [] if isinstance(h, (list, tuple)) or "list" in t or "array" in t \
          else ({} if isinstance(h, dict) or "object" in t or "map" in t else None)
  return res
