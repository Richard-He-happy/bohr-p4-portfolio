# -*- coding: utf-8 -*-
import csv, json, math, os, re, shutil, subprocess, time, zlib
from hashlib import sha256
from collections import Counter
from pathlib import Path

V = "1.0.0"
CC = ("US WO EP CN JP KR DE GB FR TW RU CA AU IN BR MX SE NL CH AT ES IT PL CZ IL SG MY TH VN PH ID NZ ZA EA "
    "AP OA HK MO PT GR NO TR UA CL CO").split()
NR = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(CC) + r")\s*[-/.]?\s*(\d[\d\s,./\-]{2,22}\d)\s*(-?[A-Z]\d?)?", re.I)
KD = {"A": "application published, NOT a grant", "B": "grant, stage only",
    "B1": "US grant, no prior pre-grant pub", "B2": "US grant after pre-grant pub", "C": "EP grant, opposition closed",
    }
ST = ("granted|grant|issued|in force|授权|有效;pending|审查中|审中;published|公开;withdrawn|撤回;refused|驳回|rejected;"
      "expired|期限届满|失效;lapsed|未缴费;revoked|无效|撤销;abandoned|放弃")
OFF = ("uspto.gov", "epo.org", "wipo.int", "cnipa.gov.cn", "j-platpat", "jpo.go.jp", "kipris.or.kr")
CH = re.compile(r"(what is claimed is|we claim|i claim|claims?\s*:|^\s*CLAIMS\s*$|权利要求书)", re.I | re.M)
CLN = re.compile(r"^\s*(\d{1,3})\s*[.)]\s+", re.M)
DEP = re.compile(r"(according to claim|as claimed in|of claim|as in claim|claimed in claim|according to any|如权利要求|根据权利要求)", re.I)
TKR = re.compile(r"[a-z][a-z0-9\-]{2,}|[\u4e00-\u9fff]{2,}")
SW = set("the and for with from that this are was were has have not but its can may use used using method system device "
     "apparatus said claim claims patent figure according present invention".split())

def now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def nz(s):
  return re.sub(r"[^a-z0-9]", "", str(s).lower())

def kg(d, *n):
  if not isinstance(d, dict):
   return None
  m = {}
  for k, v in d.items():
   m.setdefault(nz(k), v)
  for x in n:
   if m.get(nz(x)) not in (None, "", [], {}):
    return m[nz(x)]
  return None

def J(o, p, ctx=None):   # (obj, path): atomic JSON write
  try:
   p.parent.mkdir(parents=True, exist_ok=True)
   t = p.with_suffix(p.suffix + ".tmp")
   t.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
   os.replace(t, p)
   return True
  except Exception as e:
   ctx and ctx["errors"].append({"stage": "write:" + p.name, "error": str(e)})
   return False

def rb(p, cap=2_000_000):
  try:
   return Path(p).read_bytes()[:cap]
  except Exception:
   return b""

def rt(p, cap=400_000):
  b = rb(p, cap)
  for e in ("utf-8", "latin-1"):
   try:
    return b.decode(e)
   except Exception:
    pass
  return b.decode("utf-8", "replace")

def tk(s):
  return set(t.lower() for t in TKR.findall(str(s or "")) if t.lower() not in SW)

def nn(raw, hint=""):
  s, h = str(raw if raw is not None else "").strip(), str(hint).lower()
  o = dict(input=s, country=None, number_kind="unknown", kind_code=None, digits=None, year=None, canonical=None,
      stem=None, valid_format=False, stage_hint=None, warnings=[],
      role="priority" if "prior" in h else "application" if "app" in h else "grant" if "grant" in h else
      "publication" if "pub" in h or "doc" in h else None)
  if not s:
   o["warnings"].append("empty")
   return o
  p = re.match(r"(?i)^pct\s*/([a-z]{2})(\d{4})/(\d{3,7})", s)
  if p:
   o.update(country=p.group(1).upper(), number_kind="pct_application", digits=p.group(3), valid_format=True,
       canonical="PCT/%s%s/%s" % (p.group(1).upper(), p.group(2), p.group(3)),
       stem="PCT" + p.group(2) + p.group(3), warnings=["pct_not_a_publication"])
   return o
  m = NR.search(s)
  if not m:
   d = re.sub(r"\D", "", s)
   o.update(digits=d or None, canonical=re.sub(r"\s", "", s).upper() or None, valid_format=len(d) >= 4,
       warnings=["no_prefix"])
   o["stem"] = o["canonical"]
   return o
  c, seg = m.group(1).upper(), re.sub(r"\s", "", m.group(2))
  kc = re.sub(r"[^A-Z0-9]", "", (m.group(3) or "").upper())
  ps = [p for p in re.split(r"[/.\-]", seg) if p]
  dg = "".join(re.sub(r"\D", "", p) for p in ps)
  k, yr = "unknown", None
  if c == "US" and len(ps) == 2 and len(ps[0]) <= 2:
   k = "application"
  elif len(ps) >= 2 and len(ps[0]) == 4 and ps[0].isdigit() and 1900 <= int(ps[0]) <= 2035:
   k, yr = "publication", int(ps[0])
  L = len(dg)
  if k == "unknown":
   if c == "US":
    if L == 11 and 2001 <= int(dg[:4] or 0) <= 2035:
     k, yr = "publication", int(dg[:4])
    elif L in (6, 7, 8):
     k = "grant"
   elif c == "WO":
    k = "publication" if L >= 10 else "unknown"
    yr = int(dg[:4]) if L >= 10 and dg[:4].isdigit() else None
   elif c == "EP":
    k = "publication" if L in (7, 8) else "unknown"
   elif c == "CN":
    k = "publication" if L == 9 else ("application" if L in (12, 13) else "unknown")
   elif c == "JP":
    k = "grant" if L == 7 else ("publication" if L in (9, 10, 11) else "unknown")
   elif c in ("KR", "DE"):
    k = "publication" if 9 <= L <= 13 else "unknown"
   else:
    k = "publication" if L in (7, 8, 9, 10) else "unknown"
  o.update(country=c, number_kind=k, kind_code=kc or None, digits=dg or None, year=yr,
      canonical=(c + dg + kc) if dg else None, stem=(c + dg) if dg else None, valid_format=4 <= L <= 13,
      stage_hint=KD.get(kc) if kc else None)
  if not kc:
   o["warnings"].append("no_kind")
  if o["role"] in ("grant", "application", "publication") and k not in ("unknown", o["role"]):
   o["warnings"].append("field_role_%s_vs_parsed_%s" % (o["role"], k))
  return o

def ns(raw):
  s = str(raw or "").strip().lower()
  for g in ST.split(";"):
   v = g.split("|")
   if any(x in s for x in v):
    return v[0]
  return "unknown"

def pdf(p, ctx):
  if shutil.which("pdftotext"):
   try:
    r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=60)
    if r.returncode == 0 and len(r.stdout.strip()) > 200:
     return r.stdout.decode("utf-8", "replace"), "pdftotext"
   except Exception:
    pass
  b, o = rb(p, 18_000_000), []
  for m in re.finditer(rb"stream\r?\n", b):
   raw = b[m.end():b.find(b"endstream", m.end())]
   try:
    raw = zlib.decompress(raw)
   except Exception:
    pass
   o += [x[1:-1].decode("latin-1", "replace") for x in re.findall(rb"\([^()]*\)", raw)]
  t = "".join(o).replace("\\(", "(").replace("\\)", ")")
  return t, "stdlib_streams"

def outdir(p, ctx):
  for c in (Path(p), Path("/tmp") / "patent-search-output"):
   try:
    c.mkdir(parents=True, exist_ok=True)
    return c
   except Exception as e:
    ctx["degradations"].append({"stage": "output", "path": str(c), "action": "fallback"})
  return Path(".")

def load_case(inp, ctx):
  for c in [inp / "case.json"] + sorted(inp.glob("**/case*.json"))[:3]:
   if c.is_file():
    try:
     return json.loads(rt(c)), c, None
    except Exception as e:
     ctx["errors"].append({"stage": "case_load", "file": str(c), "error": "invalid JSON: %s" % e, "action": "semantic scan fallback"})
     return {}, c, "bad_json"
  t = inp / "task.md"
  if t.is_file():
   ctx["degradations"].append({"stage": "case_load", "action": "no case.json; task.md text only"})
   return {"task_instruction": rt(t, 20000)}, t, "no_case_json"
  ctx["errors"].append({"stage": "case_load", "error": "no case.json / task.md"})
  return {}, inp, "empty_input"

def doc(r, pth, loc):
  if not isinstance(r, dict):
   return None
  g = lambda *a: kg(r, *a)
  nums, seen = {"publication": [], "application": [], "grant": [], "priority": []}, set()
  for k, v in r.items():
   kn = nz(k)
   role = ("priority" if "prior" in kn else "application" if re.search(r"(applic|filing|serial)", kn) else
       "grant" if re.search(r"(grant|issue|patentnumber)", kn) else
       "publication" if re.search(r"(public|docnumber|number|no$)", kn) else None)
   if role and isinstance(v, (str, int, float)) and re.search(r"\d{3}", str(v)):
    n = nn(v, role)
    if n["digits"] and n["stem"] not in seen:
     seen.add(n["stem"])
     nums[role].append(n)
  sp = lambda x: [y.strip() for y in re.split(r"[;,|]", x) if y.strip()] if isinstance(x, str) else (x or [])
  ym = re.search(r"(19|20)\d{2}", str(g("year", "publication_date", "date") or ""))
  return dict(type="patent" if any(nums.values()) else "npl", path=pth, locator=loc, nums=nums,
        title=str(g("title", "name") or "").strip(), authors=sp(g("authors", "inventors", "author")),
        ipc=sp(g("ipc", "cpc", "classifications")), year=int(ym.group(0)) if ym else None,
        venue=str(g("venue", "journal") or ""), doi=str(g("doi") or ""), url=str(g("url", "link") or ""),
        assignee=str(g("assignee", "applicant", "owner") or ""), status_raw=g("legal_status", "status", "state"),
        status_url=g("status_url", "register_url", "source_url"),
        qsrc=str(g("abstract", "summary", "description", "claims") or g("title", "name") or "").strip(),
        text="\n".join(str(x) for x in (g("title", "name"), g("abstract", "summary", "description"), g("claims")) if x))

def hdr(t):
 o = {"publication": [], "application": [], "grant": [], "priority": []}
 for m in NR.finditer(t):
  n = nn(m.group(0), "prior" if "prior" in t[max(0, m.start() - 30):m.start()].lower() else "")
  role = "priority" if n["role"] == "priority" else "grant" if n["number_kind"] == "grant" else "publication"
  n["digits"] and o[role].append(n)
 return o

def ingest(inp, ctx):
  docs, exq, resp, gaps = [], [], [], []
  fs = [f for f in sorted(inp.rglob("*")) if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith(".")
     and f.name.lower() not in ("case.json", "task.md", "guide.md")][:400]
  for p in fs:
   ext = p.suffix.lower()
   rp = str(p.relative_to(inp)) if str(p).startswith(str(inp)) else str(p)
   try:
    if ext in (".json", ".jsonl"):
     try:
      dat = ([json.loads(l) for l in rt(p).splitlines() if l.strip()] if ext == ".jsonl" else json.loads(rt(p)))
     except Exception as e:
      ctx["errors"].append({"stage": "parse", "file": rp, "error": str(e)[:120], "action": "file skipped"})
      continue
     for i, o in enumerate(dat if isinstance(dat, list) else [dat]):
      if not isinstance(o, dict):
       continue
      q = kg(o, "query", "raw_query", "q", "terms")
      res = kg(o, "results", "hits", "items", "data")
      if re.search(r"quer", p.name, re.I) and q:
       exq.append({"raw": q, "locator": "%s#/%d" % (rp, i)})
      elif isinstance(res, list):
       resp.append({"file": rp, "status": kg(o, "http_status", "status_code", "code"), "results": res})
      else:
       docs.append(doc(o, rp, "/%d" % i))
    elif ext == ".csv":
     with open(p, newline="", encoding="utf-8", errors="replace") as fh:
      docs += [doc(dict(row), rp, "row:%d" % i) for i, row in enumerate(csv.DictReader(fh), 2)]
    elif ext in (".pdf", ".md", ".txt"):
     t, how = pdf(p, ctx) if ext == ".pdf" else (rt(p), "text")
     d = doc({"title": p.stem, "description": t[:200000]}, rp, "char:0")
     d.update(text=t[:200000], extractor=how,
         provenance=("page_merged_ocr" if "\f" in t else "text_layer") if ext == ".pdf" else "plain_text")
     d["nums"].update(hdr(t[:3000]))
     d["type"] = "patent" if re.search(r"\bclaims?\b|patent", t[:6000], re.I) else "npl"
     docs.append(d)
    elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
     gaps.append({"item": rp, "reason": "image: OCR not run", "action": "pending_human"})
   except Exception as e:
    ctx["errors"].append({"stage": "ingest", "file": rp, "error": "%s: %s" % (type(e).__name__, e)})
  uniq, seen = [], set()
  for r in resp:
   for o in r["results"]:
    d = doc(o, r["file"], "results")
    d and docs.append(dict(d, cached_status=r["status"]))
  for d in [x for x in docs if x]:
   k = (d["nums"]["publication"][0]["stem"] if d["nums"]["publication"] else None, (d["title"] or "")[:80].lower())
   if not (k[0] and k in seen):
    seen.add(k)
    uniq.append(d)
  for i, d in enumerate(uniq, 1):
   d["doc_id"] = "D%02d" % i
   d["stems"] = set(n["stem"] for g in d["nums"].values() for n in g if n["stem"])
   d["tokens"] = tk(" ".join([d["title"], str(d.get("text", ""))[:20000], d["assignee"]]))
   d["sha256"] = sha256(rb(inp / d["path"], 6_000_000) or str(d["path"]).encode()).hexdigest()
   d["retrieved_at"] = now()
  return uniq, exq, resp, gaps

def scope(case):
  s = kg(case, "organizer_supplied_scope", "scope", "search_scope", "constraints") or {}
  s = s if isinstance(s, dict) else {"topic": str(s)}
  g = lambda *a: kg(s, *a)
  sd, kw = g("seeds", "seed_numbers", "target_numbers", "patent_numbers", "numbers"), g("keywords", "terms")
  kw = [x.strip() for x in re.split(r"[,;]", kw) if x.strip()] if isinstance(kw, str) else (kw or [])
  return {"topic": str(g("topic", "research_question", "technical_topic", "subject")
            or kg(case, "task_instruction", "instruction") or ""),
      "seeds": sd if isinstance(sd, list) else ([sd] if sd else []), "keywords": kw,
      "years": g("years", "year_range"), "lang": g("lang", "language"), "max_k": g("max_k", "top_k") or 20}

def qplan(sc, docs, exq, ctx):
  qs, seen = [], set()

  def add(raw, typ, src="planner", exp=None):
   raw = str(raw if raw is not None else "").strip()
   if not raw or (raw[:150].lower(), typ) in seen:
    return
   seen.add((raw[:150].lower(), typ))
   qs.append({"query_id": "Q%02d" % (len(qs) + 1), "raw": raw, "type": typ, "db": "local_corpus", "source": src,
        "expanded": exp or [], "hits": 0, "kept": 0, "status": "pending", "error": None, "retrieved_at": now()})

  for e in exq[:40]:
   add(e.get("raw"), "explicit", "input:" + str(e.get("locator")))
  for s in sc["seeds"][:20]:
   n = nn(s)
   add(n["canonical"] or s, "number", "scope.seeds", [n["stem"], n["input"]])
  kw = sc["keywords"][:8] if sc["keywords"] else sorted(tk(sc["topic"]))[:8]
  if sc["topic"]:
   add(" ".join(kw) or sc["topic"], "topic", "scope.topic", kw)
   ipc = sorted({c for d in docs for c in d["ipc"]})[:4]
   ipc and add(" ".join(kw + ipc), "topic", "planner:classification", kw + ipc)
  if not qs:
   add(sc["topic"] or "(no query derivable)", "topic", "fallback")
   ctx["degradations"].append({"stage": "query_build", "action": "no query derivable; placeholder"})
  return qs[:24]

def retrieve(qs, docs, ctx):
  hits = {}
  for q in qs:
   qt = tk(q["raw"]) | set(t for t in q["expanded"] if isinstance(t, str) and " " not in t)
   qn = [nn(x) for x in [q["raw"]] + list(q["expanded"]) if x]
   got = []
   for d in docs:
    c, why = {}, []
    nh = [n for n in qn if n["digits"] and n["stem"] in d["stems"]]
    nh and (c.__setitem__("number_exact", 1.0), why.append("number_exact(%s)" % nh[0]["canonical"]))
    ov = len(qt & d["tokens"]) / len(qt) if qt else 0.0
    if ov > 0.02:
     c["term_overlap"] = round(min(ov, 1.0), 3)
     why.append("terms=%.2f(%d/%d)" % (ov, len(qt & d["tokens"]), len(qt)))
    ip = [x for x in q["expanded"] if isinstance(x, str) and re.match(r"^[A-H]\d\d[A-Z]", x) and x in d["ipc"]]
    ip and (c.__setitem__("classification", 1.0), why.append("ipc:" + ip[0]))
    any(a.lower() in d["assignee"].lower() for a in q["expanded"] if isinstance(a, str) and " " in a) and c.__setitem__("assignee", 1.0)
    if not c:
     continue
    got.append({"doc": d, "components": c, "reason": "; ".join(why),
          "score": round(min(0.55 * c.get("number_exact", 0) + 0.30 * c.get("term_overlap", 0)
                   + 0.08 * c.get("classification", 0) + 0.05 * c.get("assignee", 0) + 0.02, 1.0), 4)})
   got.sort(key=lambda x: (-x["score"], x["doc"]["doc_id"]))
   q["hits"], q["status"] = len(got), "ok" if got else "no_hit"
   if not got:
    q["error"] = "no hit: coverage limit, not proof of absence"
    ctx["uncertainty"].append({"id": "empty:" + q["query_id"], "statement": "query %r had no local hit" % q["raw"][:80],
                 "meaning": "coverage limit, NOT evidence the art does not exist",
                 "action": "check an external DB first"})
   hits[q["query_id"]] = got[:40]
  return hits

def fams(docs, ctx):
  par = list(range(len(docs)))

  def F(i):
   while par[i] != i:
    par[i] = par[par[i]]
    i = par[i]
   return i

  keys = {}
  for i, d in enumerate(docs):
   for role in ("priority", "application"):
    for n in d["nums"][role]:
     k = (role, n["digits"])
     if k in keys:
      a, b = F(i), F(keys[k])
      a != b and par.__setitem__(max(a, b), min(a, b))
     else:
      keys[k] = i
  grp = {}
  for i in range(len(docs)):
   grp.setdefault(F(i), []).append(i)
  out = []
  for j, (root, ix) in enumerate(sorted(grp.items()), 1):
   if len(ix) < 2:
    continue
   out.append({"family_id": "F%02d" % j, "basis": sorted("%s:%s" % k for k, i in keys.items() if F(i) == root),
         "members": [{"doc_id": docs[i]["doc_id"], "locator": docs[i]["path"] + "#" + docs[i]["locator"],
               "numbers": [n["canonical"] for g in docs[i]["nums"].values() for n in g][:2]} for i in ix],
         "caliber": "observed_links_only", "exhaustiveness": "NOT exhaustive offline (no INPADOC/DOCDB)",
         "claim_scope_note": "links only; NOT equal claim scope", "caveat": "absence != proof"})
  if not out:
   ctx["uncertainty"].append({"id": "family:none", "statement": "no two records shared a priority/application number",
                "meaning": "not inferable from the corpus",
                "action": "use the register family view"})
  return out

def legal(docs, ctx):
  out = []
  for d in docs:
   raw, url = d.get("status_raw"), str(d.get("status_url") or "")
   r = {"doc_id": d["doc_id"], "numbers": [n["canonical"] for g in d["nums"].values() for n in g][:6],
     "status_raw": raw, "status_normalised": ns(raw) if raw else "unknown",
     "source_url": url or None}
   if raw and url and any(o in url.lower() for o in OFF):
    r.update(verification="sourced_official_register", confidence="medium", note="official register URL; status date governs")
   elif raw:
    r.update(verification="secondary_or_unknown_provenance", confidence="low", note="no official locator; lead only",
        action="confirm on the official register")
    ctx["uncertainty"].append({"id": "status:" + d["doc_id"], "statement": "status %r has no official locator" % str(raw)[:60],
                 "action": "not a register fact"})
   else:
    r.update(verification="not_in_corpus", confidence="none", action="query the register per number",
        note="no status field; kind code = document type only")
    ctx["pending_human"].append({"item": "legal_status:" + d["doc_id"], "reason": r["note"],
                  "how": "register: status, status date, query date"})
   kc = d["nums"]["publication"][0]["kind_code"] if d["nums"]["publication"] else None
   if kc:
    r["kind_code_hint"] = "%s -> %s (stage, not validity)" % (kc, KD.get(kc, "unknown code"))
   out.append(r)
  byn = {}
  for r in out:
   for n in r["numbers"]:
    byn.setdefault(n, []).append(r["status_normalised"])
  for n, v in byn.items():
   len(set(v)) > 1 and ctx["uncertainty"].append({"id": "status_conflict:" + n,
                          "statement": "conflict %s" % sorted(set(v)),
                          "action": "order by register date"})
  return out

def claims(docs, ctx):
  out = []
  for d in docs:
   t = d.get("text") or ""
   m = CH.search(t)
   if not m:
    continue
   body = t[m.end():m.end() + 60000]
   mk = list(CLN.finditer(body))
   for i, mm in enumerate(mk[:9]):
    seg = body[mm.start():(mk[i + 1].start() if i + 1 < len(mk) else min(len(body), mm.start() + 2500))].strip()
    if len(seg) < 20:
     continue
    q = seg[:600]
    out.append({"doc_id": d["doc_id"], "claim_no": int(mm.group(1)), "independent": not bool(DEP.search(q)), "quote": q,
          "locator": "%s#%s+char:%d" % (d["path"], d["locator"], m.end() + mm.start()), "quote_is_verbatim": True,
          "provenance": d.get("provenance"), "scope_statement": "quoted as found"})
  if not out:
   ctx["degradations"].append({"stage": "claims", "action": "no claim section found in text",
                 "impact": "claim scope goes to pending_human"})
  return out
