"""core.py 1.0.0 - parsing / normalizing / dedup / scoring / validation library (stdlib,offline).
Imported by main.py; standalone validation: python3 core.py --input /input --output /app/output
"""
import csv,json,math,re,hashlib
from datetime import datetime,timezone
from pathlib import Path
IDXK=("first_index_date","index_date","indexed_date","created","deposited","imported_at",
    "import_date","entry_date","db_date","added_at","ingested_at","updated")
PUBK=("published","published_print","published_online","issued","publication_date",
    "date_of_publication","pub_date","first_publication_date","electronic_publication_date",
    "year","date","pubyear")
GOLD=re.compile(r"(gold|qrels|must_include|key_papers|expected_dois|relevant_dois|seed_dois|seed_papers)")
STOP=set("a an the of and or in on for to with by from at as is are was were be been this that these those "
     "using use used study studies paper papers article articles we our review results method methods "
     "new novel based via between among into than then also not no such can may more most other others "
     "its their it two three one".split())
EPOCH=datetime(1900,1,1,tzinfo=timezone.utc)
REQ=("title","source_db","retrieved_at","query_id","relevance_reason","evidence_locator")
ALIAS=(("candidate","candidates"),("new","new_items"),("alert","alerts"),("quer","queries"),
    ("snapshot","snapshot"),("cover","coverage"),("uncertain","uncertainty"),("source","sources"),
    ("delta","deltas"),("window","windows"),("screen","screening"),("cluster","clusters"),
    ("citation","citations"),("error","errors"))
def sval(v):
  if isinstance(v,(list,tuple)):
    return next((x for x in (sval(y) for y in v) if x),"")
  if isinstance(v,dict):
    return next((x for x in (sval(v[k]) for k in ("value","text","title","name","full_name","doi")
                if k in v) if x),"")
  return "" if v is None or isinstance(v,bool) else str(v).strip()
def ms(o):
  d={}
  for k,v in o.items():
    k=str(k)
    d.setdefault(k.lower().replace("-","_").replace(" ","_"),v)
    d.setdefault(re.sub(r"(?<=[a-z0-9])(?=[A-Z])","_",k).lower().replace("-","_"),v)
  return d
def pick(m,*ns):
  return next((m[n] for n in ns if m.get(n) not in (None,"",[],{})),None)
def D(y,m,d):
  try:
    return datetime(int(y),int(m),int(d),tzinfo=timezone.utc)
  except Exception:
    return None
def iso(d):
  return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(d,datetime) else None
def nt(t):
  t=re.sub(r"<[^>]{0,400}>"," ",t if isinstance(t,str) else sval(t))
  return re.sub(r"\s+"," ",re.sub(r"[^0-9A-Za-z]+"," ",t).lower()).strip()
def tk(s):
  return {w for w in nt(s).split() if len(w) > 2 and w not in STOP and not w.isdigit()}
def ndoi(d):
  d=re.sub(r"^(https?://)?(dx\.|www\.)?doi\.org/","",str(d or "").strip().lower())
  return re.sub(r"^doi:\s*","",d).strip(" .,;")
def okdoi(d):
  return bool(re.match(r"^10\.\d{4,9}/\S+$",d or ""))
def arx(*b):
  s=" ".join(str(x or "") for x in b).lower()
  m=re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})",s) or \
    re.search(r"arxiv[:\s/]*(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})",s)
  return m.group(1) if m else ""
def pd_(v):
  if isinstance(v,dict):
    dp=v.get("date-parts") or v.get("date_parts") or v.get("dateParts")
    if dp:
      return pd_(dp[0] if isinstance(dp,list) and dp else dp)
    for k in ("value","date","dateTime","date-time","date_time","timestamp","published","created","iso","start"):
      if k in v and pd_(v[k])[0]:
        return pd_(v[k])
    return (None,0)
  if isinstance(v,(list,tuple)):
    if v and isinstance(v[0],(list,tuple)):
      return pd_(v[0])
    try:
      n=[int(str(x).strip()[:4]) if len(str(x).strip()) > 4 else int(x) for x in v if str(x).strip()]
    except Exception:
      n=[]
    if n and 1000 < n[0] < 3000:
      return (D(n[0],n[1] if len(n) > 1 and 1 <= n[1] <= 12 else 1,
           n[2] if len(n) > 2 and 1 <= n[2] <= 31 else 1),min(3,len(n)))
    return (None,0)
  if isinstance(v,(int,float)) and not isinstance(v,bool):
    n=int(v)
    if n > 10 ** 11:
      return (datetime.fromtimestamp(n / 1000,timezone.utc),3)
    if n > 10 ** 8:
      return (datetime.fromtimestamp(n,timezone.utc),3)
    return (D(n,1,1),1) if 1000 < n < 3000 else (None,0)
  s=re.sub(r"[/T ]","-" if not re.search(r"\d{2}:\d{2}",str(v or "")) else " ",str(v or "").strip())
  for pat,px in ((r"^(\d{4})-(\d{1,2})-(\d{1,2})",3),(r"^(\d{4})-(\d{1,2})$",2),(r"^(\d{4})$",1)):
    m=re.match(pat,s)
    if m:
      g=m.groups()
      return (D(g[0],g[1] if len(g) > 1 else 1,g[2] if len(g) > 2 else 1),px)
  return (None,0)
def read_text(p):
  try:
    b=p.read_bytes()
  except Exception:
    return ""
  return "" if b[:4] == b"%PDF" else b.decode("utf-8","replace")
def jload(p):
  t=read_text(p).strip()
  if not t:
    return None
  try:
    return json.loads(t)
  except Exception:
    pass
  rows=[]
  for ln in t.splitlines():
    ln=ln.strip().rstrip(",")
    if ln and ln not in ("[","]"):
      try:
        rows.append(json.loads(ln))
      except Exception:
        continue
  return rows or None
def walk(node,path,out,d=0):
  if d > 14:
    return
  if isinstance(node,dict):
    out.append((node,path))
    for k,v in node.items():
      if isinstance(v,(dict,list)):
        walk(v,path + "." + str(k),out,d + 1)
  elif isinstance(node,list):
    for i,v in enumerate(node):
      if isinstance(v,(dict,list)):
        walk(v,path + "[%d]" % i,out,d + 1)
def authors_of(m):
  a=pick(m,"author","authors","authorlist","author_list","creators")
  if isinstance(a,str):
    return [x.strip() for x in re.split(r";|\|",a) if x.strip()][:40]
  if isinstance(a,dict):
    a=a.get("author") or a.get("person") or a.get("authors") or []
  out=[]
  for x in (a if isinstance(a,list) else []):
    if isinstance(x,dict):
      xm=ms(x)
      out.append(sval(pick(xm,"fullname","full_name","name")) or " ".join(
        [sval(pick(xm,"family","lastname","surname")),sval(pick(xm,"given","firstname"))]).strip())
    else:
      out.append(sval(x))
  return [x for x in out if x][:40]
def as_doc(o,path,src,retr):
  if "author" in path.rsplit(".",1)[-1].lower():
    return None
  m=ms(o)
  title=sval(pick(m,"title","titles","article_title","article_title_display","display_name",
           "primary_title","title_text"))
  if not title or len(nt(title)) < 10:
    return None
  blob=json.dumps(o,ensure_ascii=False)[:5000]
  doi=ndoi(sval(pick(m,"doi","dois")))
  doi=doi if okdoi(doi) else ""
  pmcid=((re.search(r"(PMC\d{5,8})",blob,re.I) or [None,""])[1] or "").lower()
  pmid=(re.search(r'"pmid"\s*:\s*"?(\d{6,9})',blob,re.I) or [None,""])[1] or ""
  ar=arx(doi,blob)
  dates={k: pd_(m[k]) for k in IDXK + PUBK if k in m and pd_(m[k])[0]}
  if not (doi or pmcid or pmid or ar or dates):
    return None
  ik,pk=next((k for k in IDXK if k in dates),None),next((k for k in PUBK if k in dates),None)
  tp=sval(pick(m,"type","publication_type","pub_type","subtype","article_type","genre",
         "pubtypelist","pub_type_list"))
  d={"title": re.sub(r"\s+"," ",title)[:400],"doi": doi,"pmid": pmid,"pmcid": pmcid,"arxiv": ar,
    "authors": authors_of(m),
    "venue": sval(pick(m,"container_title","journal_title","journaltitle","journal","venue",
              "source_title","publication","book_title"))[:200],
    "type": tp[:120],"url": sval(pick(m,"url","urls","link","fulltext_url","landing_page"))[:400],
    "abstract": re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",
                        sval(pick(m,"abstract","summary","description"))))[:2000],
    "pub_dt": dates[pk][0] if pk else None,"idx_dt": dates[ik][0] if ik else None,
    "idx_src": ik or "","retrieved_at": retr,"src": str(src),"loc": path}
  d["tkey"]=nt(d["title"])
  d["year"]=(d["pub_dt"] or d["idx_dt"]).year if (d["pub_dt"] or d["idx_dt"]) else None
  d["keys"]={p + ":" + v for p,v in (("doi",doi),("arxiv",ar),("pmid",pmid),("pmcid",pmcid),
                     ("title",d["tkey"])) if v}
  d["doc_id"]=doi or ("arxiv:" + ar if ar else "pmid:" + pmid if pmid else "pmcid:" + pmcid if pmcid
             else "t:" + hashlib.sha1(d["tkey"].encode()).hexdigest()[:12])
  return d
def collect(inp,extra):
  docs,files,errs,texts=[],[],[],{}
  for root in [Path(inp)] + [Path(x) for x in extra if Path(x).is_dir()]:
    try:
      entries=sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))
    except Exception as e:
      errs.append("scan_failed:%s" % e)
      continue
    for p in entries:
      files.append(p)
      rel=p.name if p.parent == Path(inp) else str(p)[len(str(root)) + 1:]
      retr=iso(datetime.fromtimestamp(p.stat().st_mtime,timezone.utc))
      suf=p.suffix.lower()
      if suf in (".json",".jsonl",".ndjson",".jsonld"):
        data=jload(p)
        if data is None:
          errs.append("unparsable_json:" + rel)
          continue
        rows=[]
        walk(data,"$",rows)
        docs += [x for x in (as_doc(o,loc,rel,retr) for o,loc in rows) if x]
        texts[rel]=read_text(p)[:150000]
      elif suf in (".csv",".tsv"):
        try:
          with p.open("r",encoding="utf-8",errors="replace",newline="") as fh:
            for i,row in enumerate(csv.DictReader(fh,delimiter="\t" if suf == ".tsv" else ",")):
              x=as_doc({k: v for k,v in row.items() if k and v},"row%d" % (i + 2),rel,retr)
              if x:
                docs.append(x)
        except Exception as e:
          errs.append("csv_failed:%s:%s" % (rel,e))
      else:
        texts[rel]=read_text(p)[:150000]
  return docs,files,errs,texts
def cluster(docs):
  par=list(range(len(docs)))
  def f(x):
    while par[x] != x:
      par[x]=par[par[x]]
      x=par[x]
    return x
  first={}
  for i,d in enumerate(docs):
    for k in d["keys"]:
      if k in first:
        a,b=f(first[k]),f(i)
        if a != b:
          par[b]=a
      else:
        first[k]=i
  grp={}
  for i in range(len(docs)):
    grp.setdefault(f(i),[]).append(docs[i])
  return list(grp.values())
def sig(ks):
  s={k for k in ks if not k.startswith("title:")}
  return s or set(ks)


def preprint(d):
  b=" ".join([d["venue"],d["type"],d["doi"],d["url"],d["title"]]).lower()
  return any(k in b for k in ("arxiv","biorxiv","medrxiv","10.1101","10.48550","10.21203",
                "research square","ssrn","preprint")) and \
    not any(k in b for k in ("nature","science","lancet","nejm","springer","wiley","elsevier"))
def notice(d):
  return any(k in (d["type"] + " " + d["title"]).lower() for k in (
    "retract","withdraw","expression of concern","erratum","correction","corrigendum","editorial note"))
def vrank(d):
  if notice(d):
    return 6
  if preprint(d):
    return 1
  m=re.search(r"\bv(?:ersion)?\s?(\d+)\b",d["title"] + " " + d["venue"] + " " + d["type"],re.I)
  return 3 + (int(m.group(1)) if m else 0)
def work_of(ds):
  order=sorted(ds,key=lambda d: (-vrank(d),-(d["pub_dt"] or d["idx_dt"] or EPOCH).timestamp()))
  c=order[0]
  keys=set()
  for d in ds:
    keys |=d["keys"]
  idx=[d["idx_dt"] for d in ds if d["idx_dt"]]
  pdt=[d["pub_dt"] for d in ds if d["pub_dt"]]
  filled=sum(1 for x in (c["doi"],c["authors"],c["venue"],c["idx_dt"] or c["pub_dt"]) if x)
  return {"work_id": c["doc_id"],"title": c["title"],"authors": c["authors"],"year": c["year"],
      "venue": c["venue"],"doi": c["doi"] or next((d["doi"] for d in ds if d["doi"]),""),
      "url": next((d["url"] for d in ds if d["url"]),""),"abstract": c["abstract"],
      "type": c["type"],"idx_dt": max(idx) if idx else None,"pub_dt": max(pdt) if pdt else None,
      "keys": keys,"docs": ds,"n_items": len(ds),
      "confidence": "high" if filled >= 4 else ("medium" if filled >= 2 else "low"),
      "is_notice": any(notice(d) for d in ds),
      "version_chain": [{"doi": d["doi"],"arxiv": d["arxiv"],"type": d["type"][:70],
               "index_date": iso(d["idx_dt"]),"version_rank": vrank(d),
               "source": d["src"]} for d in order]}
def src_db(s):
  s=s.lower()
  return ("crossref" if "crossref" in s else "europepmc" if "pmc" in s else
      "publisher" if "publish" in s or "elsevier" in s or "springer" in s else "artifact")
def fill_contract(res,c):
  if isinstance(c,dict):
    for k,v in c.items():
      if k not in res:
        b={} if isinstance(v,dict) else [] if isinstance(v,list) or (
          isinstance(v,str) and re.search(r"(list|array|\[\]|candidates|items)",v,re.I)) else None
        for pat,s in ALIAS:
          if pat in str(k).lower() and isinstance(res.get(s),list) and isinstance(b,list):
            b=res[s]
            break
        res[k]=b
    res["_output_contract"]=c
  elif isinstance(c,list):
    for k in c:
      res.setdefault(str(k),[])
    res["_output_contract"]=c
  return res
def write_result(out,res):
  try:
    Path(out).mkdir(parents=True,exist_ok=True)
    t=Path(out) / "result.json.tmp"
    t.write_text(json.dumps(res,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    t.replace(Path(out) / "result.json")
  except Exception as e:
    print("write_result failed: %s" % e)
def find_windows(obj,out,path="case"):
  if isinstance(obj,dict):
    m=ms(obj)
    s=pick(m,"window_start","period_start","start","since","begin","date_from")
    e=pick(m,"window_end","period_end","end","until","as_of","date_to")
    if s is not None and e is not None:
      a,b=pd_(s)[0],pd_(e)[0]
      if a and b and a < b:
        out.append({"start": a,"end": b,"origin": path})
    for k,v in obj.items():
      find_windows(v,out,path)
  elif isinstance(obj,list):
    for v in obj:
      find_windows(v,out,path)
  return out
def find_gold(obj,out):
  if isinstance(obj,dict):
    for k,v in obj.items():
      if GOLD.search(str(k).lower()) and isinstance(v,(list,dict)):
        for x in (v if isinstance(v,list) else [v]):
          s=sval(pick(ms(x),"doi","title","id","pmid","value")) if isinstance(x,dict) else sval(x)
          if s:
            out.append(s)
      if isinstance(v,(dict,list)):
        find_gold(v,out)
  elif isinstance(obj,list):
    for v in obj:
      find_gold(v,out)
  return out
def variants(vals):
  ks=set()
  for v in vals:
    v=sval(v)
    d=ndoi(v)
    if okdoi(d):
      ks.add("doi:" + d)
    elif re.match(r"^PMC\d+$",v,re.I):
      ks.add("pmcid:" + v.lower())
    elif re.match(r"^\d{6,9}$",v):
      ks.add("pmid:" + v)
    elif len(nt(v)) > 10:
      ks.add("title:" + nt(v))
  return ks
def metrics(ranked,gold,k):
  if not gold:
    return {"precision_at_k": None,"recall_at_k": None,"ndcg_at_k": None,"k": k,
        "note": "no organizer relevance/gold list in /input; metrics not computed"}
  top=ranked[:k]
  hit=[1 if set(x) & gold else 0 for x in top]
  got={g for x in top for g in (set(x) & gold)}
  dcg=sum(h / math.log2(i + 2) for i,h in enumerate(hit))
  idcg=sum(1 / math.log2(i + 2) for i in range(min(len(gold),len(top))))
  return {"precision_at_k": round(sum(hit) / float(len(top)),4) if top else 0.0,
      "recall_at_k": round(len(got) / float(len(gold)),4),
      "ndcg_at_k": round(dcg / idcg,4) if idcg else None,"k": k,"gold_size": len(gold)}
def terms_of(text,lim=28):
  c={}
  for w in nt(text).split():
    if len(w) > 2 and w not in STOP and not w.isdigit():
      c[w]=c.get(w,0) + 1
  return [w for w,_ in sorted(c.items(),key=lambda kv: (-kv[1],kv[0]))[:lim]]
def cover(w,terms):
  if not terms:
    return 0.0
  a,b=tk(w["title"]),tk(w.get("abstract","") + " " + w.get("venue",""))
  return min(1.0,sum(1.0 if t in a else 0.6 if t in b else 0.0 for t in terms) / float(len(terms)))
def corpus(inp):
  buf=[]
  for p in sorted(Path(inp).rglob("*")):
    if p.is_file() and p.suffix.lower() in (".json",".jsonl",".csv",".tsv",".md",".txt"):
      try:
        buf.append(p.read_text("utf-8","replace").lower())
      except Exception:
        continue
  return "\n".join(buf)
def run_checks(inp,out,case_id=None):
  """Deterministic validation of result.json and its sidecar artifacts."""
  out,inp,R=Path(out),Path(inp),{"checks": [],"passed": 0,"failed": 0}
  def ck(name,ok,detail=""):
    R["checks"].append({"check": name,"status": "pass" if ok else "fail","detail": str(detail)[:240]})
    R["passed" if ok else "failed"] += 1
  try:
    res=json.loads((out / "result.json").read_text("utf-8"))
  except Exception as e:
    ck("result_json_valid",False,e)
    return R
  ck("result_json_valid",True,"parsed")
  ck("case_id_preserved",case_id is None or res.get("case_id") == case_id,res.get("case_id"))
  ck("status_enum",res.get("status") in ("ok","partial","insufficient_evidence","input_error"),res.get("status"))
  con=res.get("_output_contract") or {}
  miss=[k for k in (con if isinstance(con,dict) else {}) if k not in res]
  ck("output_contract_complete",not miss,f"missing={miss}")
  cands=res.get("candidates") or []
  ck("candidates_present",bool(cands),f"{len(cands)} candidates")
  ck("candidate_fields_complete",all(all(c.get(f) for f in REQ) for c in cands),
   [c.get("candidate_id") for c in cands if not all(c.get(f) for f in REQ)][:8])
  ck("doi_syntax",all(not c.get("doi") or okdoi(c["doi"]) for c in cands),
   [c.get("candidate_id") for c in cands if c.get("doi") and not okdoi(c["doi"])][:8])
  txt=corpus(inp)
  ck("doi_traceable_to_input",all(not c.get("doi") or c["doi"] in txt for c in cands),
   [c.get("candidate_id") for c in cands if c.get("doi") and c["doi"] not in txt][:8])
  alive={c.get("work_id") for c in cands}
  ck("new_items_in_candidates",all(t.get("work_id") in alive for t in (res.get("new_items") or [])),"orphans")
  ck("works_unique",len(cands) == len(alive),f"duplicate rows={len(cands) - len(alive)}")
  alerts=res.get("alerts") or []
  ck("alerts_delivery_recorded",all((a.get("delivery") or {}).get("status") for a in alerts),f"{len(alerts)}")
  need=["candidates.csv","query_log.json","alerts.json","alerts.md","snapshot.json"]
  ck("sidecar_artifacts_present",all((out / f).is_file() for f in need),
   [f for f in need if not (out / f).is_file()])
  try:
    snap=json.loads((out / "snapshot.json").read_text("utf-8"))
  except Exception:
    snap={}
  ck("snapshot_advanced",bool(snap.get("window_end")),snap.get("window_end"))
  ck("query_log_present",bool(res.get("queries")),f"{len(res.get('queries') or [])} queries")
  R["ok"]=R["failed"] == 0
  return R
if __name__ == "__main__":
  import argparse
  ap=argparse.ArgumentParser(description="Validate literature-delta-tracker output (result.json + sidecars).")
  ap.add_argument("--input",default="/input")
  ap.add_argument("--output",default="/app/output")
  a=ap.parse_args()
  rep=run_checks(a.input,a.output)
  print(json.dumps({"passed": rep.get("passed"),"failed": rep.get("failed"),
           "failed_checks": [c for c in rep["checks"] if c["status"] != "pass"]},ensure_ascii=False))
