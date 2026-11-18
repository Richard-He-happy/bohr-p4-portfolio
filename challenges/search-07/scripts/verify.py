#!/usr/bin/env python3
"""Deterministic core + self-check for search-coverage-gap-auditor.
Library + CLI verifier:
    python3 -B scripts/verify.py --input /input --output /app/output
stdlib only, offline, always exit 0."""
import argparse,csv,hashlib,json,math,re,shutil,subprocess,sys,time,traceback,unicodedata
from pathlib import Path
H=Path(__file__).resolve().parent;RD=H.parent/"references";SK="search-coverage-gap-auditor";V="1.1.0";LG=[]
def log(*a):
 s=" ".join(map(str,a));LG.append(s)
 try:print(s,flush=True)
 except Exception:pass
LX={}
try:LX=json.loads((RD/"lexicon.json").read_text(encoding="utf-8"))
except Exception:pass
SW=set((LX.get("stopwords") or "a an and the of for on in to with by from et al is are as at this that".split()))
TX=LX.get("miss_taxonomy") or {}
PR=LX.get("cause_priority") or ["C01","C02","C03","C04","C05","C06","C07","C08","C09","C10","C11","C12"]
def tx(c,k="label"):return (TX.get(c) or {}).get(k) or c
def nt(s):
 s=re.sub(r"[^0-9a-z\u4e00-\u9fff]+"," ",re.sub(r"<[^>]+>"," ",unicodedata.normalize("NFKD",str(s or "")).lower()))
 return re.sub(r"\s+"," ",s).strip()
def nk(k):return re.sub(r"[^a-z0-9]+","",str(k).lower())
def nd(s):
 t=re.sub(r"^https?://(dx\.)?doi\.org/|^doi:\s*","",str(s or "").strip().lower())
 m=re.search(r"10\.\d{4,9}/[^\s\"<>]+",t)
 return (m.group(0) if m else t).rstrip(" .,;)]}")
DX=re.compile(r"^10\.\d{4,9}/\S+$");WD=re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}");DR=re.compile(r"10\.\d{4,9}/[^\s\"'<>,;]+")
def tk(*v):return {t for x in v for t in WD.findall(nt(x)) if len(t)>2 and t not in SW and not t.isdigit()}
def jc(a,b):return 0.0 if not a or not b else len(a&b)/float(len(a|b))
def rt(a,b):
 import difflib
 a,b=nt(a),nt(b)
 return 0.0 if not a or not b else 1.0 if a==b else difflib.SequenceMatcher(None,a,b).ratio()
def yr(v):
 if isinstance(v,bool):return None
 if isinstance(v,(int,float)) and 1400<v<2100:return int(v)
 if isinstance(v,dict):
  d=v.get("date-parts") or v.get("date_parts")
  if isinstance(d,list) and d:return yr(d[0])
  for k in ("year","value","date"):
   if k in v:return yr(v[k])
  return None
 if isinstance(v,(list,tuple)) and v:return yr(v[0])
 if isinstance(v,str):
  m=re.search(r"(1[6-9]\d{2}|20\d{2})",v)
  return int(m.group(1)) if m else None
 return None
def g(d,names,dd=None):
 if not isinstance(d,dict):return dd
 lo={nk(k):k for k in d}
 for n in names:
  k=lo.get(nk(n))
  if k is not None and d[k] not in (None,"",[],{}):return d[k]
 return dd
T=["title","article_title","paper_title","display_name","name"]
D=["doi","doi_url"];Y=["year","pub_year","publication_year","issued","published","date"]
A=["authors","author","authorships","author_list"];VN=["venue","journal","journal_title","container_title","booktitle"]
AB=["abstract","summary"];LA=["language","lang"];SRC=["source_db","database","provider","db","index"]
QI=["query_id","qid","queryid","search_id"];RA=["retrieved_at","retrieved","fetched_at","timestamp","ts"]
UR=["url","link","landing_page","fulltext_url"];ST=["publication_status","record_status","status","is_retracted"]
QT=["query","query_string","query_text","q","raw","strategy","search_string"];HT=["hits","hit_count","count","total","n_results"]
FL=["fields","field","search_fields"];DC=["include","included","relevant","relevance","selected","decision"]
def au(v):
 if isinstance(v,str):return [x.strip() for x in re.split(r"[;,]| and ",v) if x.strip()][:30]
 if isinstance(v,dict):v=[v]
 o=[]
 for a in (v or [])[:30]:
  if isinstance(a,str):o.append(a.strip())
  elif isinstance(a,dict):o.append(("%s %s"%(g(a,["given","first"]) or "",g(a,["family","last","surname","name"]) or "")).strip())
 return o
def rec(o,cx):
 t=g(o,T)
 if isinstance(t,list):t=t[0] if t else None
 if isinstance(t,dict):t=g(t,["title","value","text"])
 r={"title":str(t).strip() if t else "","doi":nd(g(o,D)),"year":yr(g(o,Y)),"authors":au(g(o,A)),
  "venue":str(g(o,VN) or ""),"abstract":str(g(o,AB) or ""),"lang":str(g(o,LA) or ""),
  "source_db":str(g(o,SRC) or cx.get("source_db") or ""),"query_id":str(g(o,QI) or cx.get("query_id") or ""),
  "retrieved_at":str(g(o,RA) or cx.get("retrieved_at") or ""),"url":str(g(o,UR) or ""),
  "status":str(g(o,ST) or ""),"ids":{},"raw_path":cx.get("path","")}
 for k in ("pmid","pmcid","arxiv","isbn","openalex"):
  x=g(o,[k])
  if x:r["ids"][k]=str(x)
 for k in DC:
  x=g(o,[k])
  if x is not None:r["relevance"]=x;break
 r["tok"]=tk(r["title"],r["abstract"][:400]);return r
def walk(o,p,out,par=None,dp=0):
 if dp>9:return
 if isinstance(o,dict):
  for k,v in o.items():walk(v,"%s/%s"%(p,k),out,o,dp+1)
 elif isinstance(o,list):
  ds=[x for x in o if isinstance(x,dict)]
  ks=[{nk(k) for k in x} for x in ds[:40]]
  if ds and (sum(1 for x in ds if g(x,T))>=max(1,int(.5*len(ds))) or any(k&{"citing","cited","from","to","source","target"} for k in ks) or any(k&{"query","q"} and k&{"hits","count","total"} for k in ks)):
   out.append({"path":p,"items":ds,"parent":par or {}})
  for x in ds[:300]:walk(x,p+"[]",out,par,dp+1)
def rcsv(p):
 try:t=p.read_text(encoding="utf-8-sig",errors="replace")
 except Exception:return []
 if not t.strip():return []
 try:d=csv.Sniffer().sniff(t[:4096],delimiters=",;\t|").delimiter
 except Exception:d=","
 try:return [{k:(v or "") for k,v in r.items()} for r in csv.DictReader(t.splitlines(),delimiter=d) if any((v or "").strip() for v in r.values())]
 except Exception:return []
def rpdf(p):
 try:
  r=subprocess.run(["pdftotext","-layout",str(p),"-"],capture_output=True,timeout=90) if shutil.which("pdftotext") else None
  if r and r.returncode==0 and r.stdout:return r.stdout.decode("utf-8","replace")
 except Exception:pass
def load(p):
 s=p.suffix.lower()
 try:
  if s in (".json",".jsonl",".ndjson",".jl"):
   t=p.read_text(encoding="utf-8",errors="replace");o=[]
   if s==".json":
    try:walk(json.loads(t),str(p),o);return o
    except Exception:pass
   rw=[]
   for l in t.splitlines():
    if l.strip().startswith("{"):
     try:rw.append(json.loads(l))
     except Exception:pass
   return [{"path":str(p),"items":rw,"parent":{}}] if rw else []
  if s in (".csv",".tsv"):
   rw=rcsv(p);return [{"path":str(p),"items":rw,"parent":{}}] if rw else []
  if s==".pdf":
   o,s2=[],set()
   for m in DR.finditer(rpdf(p)):
    d=nd(m.group(0).rstrip("."))
    if d and d not in s2 and len(o)<300:s2.add(d);o.append({"title":"","doi":d,"raw_path":str(p)})
   return [{"path":str(p),"items":o,"parent":{"derived":"pdf_doi_scan"}}] if o else []
 except Exception as e:log("  ! read %s: %s"%(p.name,e))
 return []
_H=LX.get("path_hints") or {}
RH=_H.get("reference") or ["reference","refs","seed","included","known","gold","relevant"]
PH=_H.get("pool") or ["response","result","hit","record","retriev","pool","candidate","import"]
def sc(st):
 p=st["path"].lower().replace("\\","/");tl=p.rsplit("/",1)[-1];r=q=pl=0
 for h in RH:r+=4 if h in tl else 2 if h in p else 0
 for h in PH:pl+=4 if h in tl else 1 if h in p else 0
 q+=3 if ("quer" in p or "strateg" in p or "log" in p) else 0
 ks=set()
 for it in st["items"][:40]:
  if isinstance(it,dict):ks|=set(nk(k) for k in it)
 if ks&set(nk(k) for k in DC):r+=3
 if ks&set(nk(k) for k in ("queryid","retrievedat","sourcedb","database")):pl+=3
 if ks&set(nk(k) for k in QT) and ks&set(nk(k) for k in HT):q+=4
 st["sr"],st["sp"],st["sq"]=r,pl,q;return st
def rset(sts):
 c=[sc(s) for s in sts]
 R=sorted([s for s in c if s["sr"]>=4 and s["sr"]>=s["sp"]],key=lambda s:-s["sr"])
 P=sorted([s for s in c if s["sp"]>=3 and s["sp"]>s["sr"] and any(g(i,T) or g(i,D) for i in s["items"][:20])],key=lambda s:-s["sp"])
 Qs=sorted([s for s in c if s["sq"]>=4],key=lambda s:-s["sq"])
 if not R:
  for s in c:
   d=[i for i in s["items"] if isinstance(i,dict) and str(g(i,DC) or "").lower() in ("true","1","yes","include","included","relevant")]
   if d:R.append({"path":s["path"]+"#included","items":d,"parent":s["parent"],"sr":5});break
 return R,P,Qs
def nrefs(it0):
 o=[rec(i,{}) for i in it0 if isinstance(i,dict)]
 o=[r for r in o if r["title"] or r["doi"]]
 for i,r in enumerate(o):r["ref_id"]="R%03d"%(i+1);r["dups"]=[]
 u,seen,dl=[],{},[]
 for r in o:
  k=r["doi"] or nt(r["title"])+"|"+str(r["year"])
  if k in seen:
   seen[k]["dups"].append(r["ref_id"]);dl.append({"kept":seen[k]["ref_id"],"dropped":r["ref_id"]})
   if not seen[k]["doi"] and r["doi"]:seen[k]["doi"]=r["doi"]
   continue
  seen[k]=r;u.append(r)
 return u,dl
def excl(r):
 s=(r.get("status") or "").lower();t=(r.get("title") or "").lower()
 if "retract" in s or t.startswith("retracted") or "retraction" in s or "withdraw" in s:return "retracted"
 if any(x in s for x in ("unavailable","no_fulltext","cannot","closed","denied")):return "fulltext_unavailable"
 return None
def bq(st,qid):
 p0=st["parent"] if st.get("parent") else (st["items"][0] if st.get("items") else {})
 q={"query_id":g(p0,QI) or qid,"db":str(g(p0,SRC) or ""),"raw":str(g(p0,QT) or ""),
  "fields":g(p0,FL),"hits":g(p0,HT),
  "year_from":yr(g(p0,["year_from","from_year","start_year","since"])),
  "year_to":yr(g(p0,["year_to","to_year","end_year","until"])),
  "status":str(g(p0,["status","state"]) or "reported"),"error":g(p0,["error","message"]),
  "records":len(st["items"]),"path":st["path"],
  "tokens":sorted(tk(str(g(p0,QT) or ""),str(g(p0,["expanded","expansion"]) or "")))}
 if q["year_from"] is None and q["year_to"] is None:
  ys=[y for y in (yr(g(i,Y)) for i in st["items"]) if y]
  if ys:q["year_from"],q["year_to"]=min(ys),max(ys)
 return q
def qid_of(p,i):
 m=re.search(r"(q\d{1,3}|query[_-]?\d{1,3}|s\d{1,3})",p.lower())
 return m.group(1) if m else "q%d"%i
def am(a,b):
 if not a or not b:return False
 f=lambda s:nt(s.split()[-1] if len(s.split())>1 else s)
 return len(f(a[0]))>2 and f(a[0])==f(b[0])
def cmp(a,b):
 if a["doi"] and b["doi"] and a["doi"]==b["doi"]:return "exact_doi",1.0
 for k in a["ids"]:
  if k in b["ids"] and a["ids"][k]==b["ids"][k]:return "identifier:"+k,0.97
 if a["title"] and b["title"] and nt(a["title"])==nt(b["title"]):return "exact_title",0.98
 if not a["tok"] or not b["tok"]:return None
 s=.6*jc(a["tok"],b["tok"])+.4*rt(a["title"],b["title"])
 ok=not(a["year"] and b["year"]) or abs(a["year"]-b["year"])<=1
 if s>=.90 and ok:return "fuzzy_title",round(s,3)
 if s>=.86 and ok and am(a["authors"],b["authors"]):return "fuzzy_author_year",round(s,3)
 if s>=.62 and ok:return "soft_candidate",round(s,3)
 return None
def match(refs,pool):
 inv={}
 for i,r in enumerate(pool):
  for t in r["tok"]:inv.setdefault(t,[]).append(i)
 np_=max(1,len(pool));res={}
 for ri,rf in enumerate(refs):
  c={}
  for t in rf["tok"]:
   l=inv.get(t)
   if not l or len(l)>.6*np_:continue
   for i in l:c[i]=c.get(i,0)+1
  need=1 if len(rf["tok"])<=3 else 2;best=None
  for i in sorted([i for i,v in c.items() if v>=need],key=lambda i:-c[i])[:300]:
   z=cmp(rf,pool[i])
   if z and (best is None or z[1]>best[2]):best=(i,z[0],z[1])
  res[ri]=best
 return res
def yadm(q,y):
 if not y:return True
 if q.get("year_from") and y<q["year_from"]:return False
 if q.get("year_to") and y>q["year_to"]:return False
 return True
def flds(q):
 f=q.get("fields")
 if not f:return None
 if isinstance(f,str):return set(x.lower() for x in re.split(r"[,;| ]+",f) if x.strip())
 return set(str(x).lower() for x in f)
def attr(rf,sp,pool,qs,scope,edges,srcs):
 C=[]
 if sp is not None:C.append(("C01",{"pool_record":pool[sp]["rid"],"title_similarity":round(rt(rf["title"],pool[sp]["title"]),3),"ref_doi":rf["doi"] or None,"pool_doi":pool[sp]["doi"] or None}))
 best,bo=None,0.0
 for q in qs:
  ov=jc(rf["tok"],set(q["tokens"])) if q["tokens"] else 0.0
  if ov>bo:best,bo=q,ov
 if best and bo>=.34:
  q=best;fs=flds(q)
  if not yadm(q,rf["year"]):C.append(("C04",{"query_id":q["query_id"],"query":q["raw"],"window":[q.get("year_from"),q.get("year_to")],"ref_year":rf["year"]}))
  elif fs and "title" not in fs and bo>=.5:C.append(("C05",{"query_id":q["query_id"],"fields":sorted(fs),"matched_in":"title"}))
  elif q.get("hits") and int(q["hits"])>int(q["records"]):C.append(("C02",{"query_id":q["query_id"],"reported_hits":q["hits"],"records_retained":q["records"],"query":q["raw"]}))
  else:C.append(("C03",{"query_id":q["query_id"],"query":q["raw"],"db":q.get("db"),"term_overlap":round(bo,3)}))
 else:
  sy=scope.get("years")
  if sy and rf["year"] and len(sy)==2 and not(sy[0]<=rf["year"]<=sy[1]):C.append(("C04",{"window":sy,"ref_year":rf["year"],"scope":"organizer_supplied_scope"}))
  if rf["source_db"] and srcs and rf["source_db"].lower() not in srcs:C.append(("C07",{"ref_source":rf["source_db"],"queried_sources":sorted(srcs)}))
  qv=set()
  for q in qs:qv|=set(q["tokens"])
  ms=sorted(t for t in tk(rf["title"],rf["abstract"][:200]) if t not in qv)[:6]
  if ms:C.append(("C06",{"uncovered_terms":ms,"nearest_query":(best or {}).get("query_id"),"query_vocabulary":len(qv)}))
  if rf["lang"] and rf["lang"].lower() not in ("en","eng","english"):C.append(("C08",{"ref_lang":rf["lang"],"query_lang":scope.get("language") or "en"}))
 if edges and rf.get("citable"):
  e=edges.get(rf["citable"],[])
  if e:C.append(("C09",{"edge":e[0]["edge"],"graph":e[0]["path"]}))
 if rf.get("anomaly"):C.append(("C10",{"anomaly":rf["anomaly"]}))
 if not C:C.append(("C12",{"needed":["venue response log","query strings with field/year filters","identity check"]}))
 return C
def jd(p,o):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+".tmp")
 t.write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding="utf-8");t.replace(p)
def wc(p,rows,cols):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+".tmp")
 with t.open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore");w.writeheader()
  for r in rows:w.writerow({k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in r.items()})
 t.replace(p)
def ck(oc):
 if isinstance(oc,dict):return [(k,v) for k,v in oc.items()]
 o=[]
 for it in (oc if isinstance(oc,list) else []):
  if isinstance(it,dict):
   k=g(it,["name","field","key","id"])
   if k:o.append((str(k),it))
  elif isinstance(it,str):o.append((it,"unspecified"))
 return o
def sty(s):
 t=(json.dumps(s,ensure_ascii=False) if not isinstance(s,str) else s).lower()
 for k,v in (("array","array"),("list","array"),("object","object"),("dict","object"),("number","number"),("float","number"),("int","number"),("bool","bool"),("string","string"),("text","string")):
  if k in t:return v
 return "any"
def sca(v):
 if isinstance(v,bool):return None
 if isinstance(v,(int,float)):return v
 if isinstance(v,list):return len(v)
 if isinstance(v,dict):
  for k in ("coverage","value","rate","count","n_hit","score","total"):
   x=v.get(k)
   if isinstance(x,(int,float)) and not isinstance(x,bool):return x
 return None
def co(v,t):
 if v is None:return {"array":[],"object":{},"string":""}.get(t)
 if t=="array":return v if isinstance(v,list) else [v]
 if t=="object":return v if isinstance(v,dict) else {"value":v}
 s=sca(v)
 if t=="number":return (int(s) if isinstance(s,float) and s==int(s) else s) if s is not None else None
 if t=="string":return v if isinstance(v,str) else str(s) if s is not None else json.dumps(v,ensure_ascii=False)[:400]
 return v
def fin(res,out,oc,t0):
 res["runtime"]={"seconds":round(time.time()-t0,3),"skill":SK,"version":V,"python":sys.version.split()[0],"network":False}
 def pick(k):
  w=set(re.findall(r"[a-z]+",str(k).lower()))
  if w&{"miss","missed","misses","gap","omitted","unfound"}:return [m for m in (res.get("hit_matrix") or []) if m.get("status")=="miss"],"hit_matrix[miss]"
  if w&{"candidate","candidates","retained"}:return res.get("candidates"),"candidates"
  if w&{"query","queries","strategy"}:return res.get("queries"),"queries"
  if w&{"coverage","recall","rate"}:return res.get("coverage"),"coverage"
  if w&{"matrix","table","evidence","rows"}:return res.get("hit_matrix"),"hit_matrix"
  if w&{"note","notes","summary","comment"}:return (res.get("coverage") or {}).get("formula"),"coverage.formula"
  return None,None
 fl,fm={},{}
 for k,s in ck(oc):
  kk=nk(k);v,c0=res.get(kk),None
  for c in res:
   if kk==nk(c):v,c0=res.get(c),c;break
  if v is None:
   v,c0=pick(k)
  if v is None:
   for c in res:
    if kk in nk(c) or nk(c) in kk:v,c0=res.get(c),c;break
  fl[k]=co(v,sty(s));fm[k]={"from":c0 or "unfilled","type":sty(s)}
 b=dict(fl)
 for k in res:
  if k not in b:b[k]=res.get(k)
 b["contract_fill"]=fm
 for k in ("errors","degradations","pending_human","changes","uncertainty"):b[k]=res.get(k) or []
 if not b.get("case_id"):b["case_id"]=res.get("case_id")
 jd(out/"result.json",b)
def disc(inp):
 fs,st=[],[]
 if not inp.exists():return fs,st
 for p in sorted(inp.rglob("*")):
  if not p.is_file() or p.name.startswith("."):continue
  s=load(p)
  try:fs.append({"path":str(p),"bytes":p.stat().st_size,"structures":len(s)})
  except Exception:fs.append({"path":str(p),"structures":len(s)})
  st.extend(s)
 return fs,st

def run_checks(inp,out):
 """recompute auditable parts of result.json from artifacts on disk."""
 chk=[]
 def add(n,ok,d):chk.append({"check":n,"ok":bool(ok),"detail":d})
 try:R=json.loads((out/"result.json").read_text(encoding="utf-8"))
 except Exception as e:
  return {"ok":False,"n_checks":1,"failed":[{"check":"result_json_readable","ok":False,"detail":str(e)}]}
 case={}
 try:case=json.loads((inp/"case.json").read_text(encoding="utf-8"))
 except Exception:pass
 oc=g(case,["output_contract","outputcontract","contract","output_schema"]) or {}
 keys=[k for k,_ in ck(oc)]
 mk=[k for k in keys if k not in R];add("contract_fields",not mk,mk[:10])
 add("case_id_echo",(not keys) or R.get("case_id")==g(case,["case_id","caseid","id","task_id"]),R.get("case_id"))
 hm=[]
 try:
  with (out/"hit_matrix.csv").open(encoding="utf-8") as f:hm=list(csv.DictReader(f))
 except Exception:pass
 add("hit_matrix",bool(hm),len(hm))
 if hm:
  nh=sum(1 for r in hm if r.get("status") in ("hit","hit_recovered"))
  nx=sum(1 for r in hm if r.get("status")=="excluded");nm=sum(1 for r in hm if r.get("status")=="miss")
  cov=R.get("coverage") or {};n_el=cov.get("n_eligible")
  add("row_partition",len(hm)==nh+nm+nx,[len(hm),nh,nm,nx])
  add("denominator",n_el==nh+nm,[n_el,nh+nm])
  exp=round(nh/float(n_el),4) if n_el else None
  add("coverage",cov.get("n_hit")==nh and exp is not None and abs(float(cov.get("coverage") or 0)-exp)<=0.0002,[cov.get("coverage"),exp])
  b1=[r.get("ref_id") for r in hm if r.get("status")=="miss" and not r.get("cause_primary")];add("cause",not b1,b1[:10])
  b2=[r.get("ref_id") for r in hm if r.get("status")=="miss" and not (r.get("repair") or "").strip()];add("repair",not b2,b2[:10])
  b3=[r.get("ref_id") for r in hm if r.get("status") in ("hit","hit_recovered") and not (r.get("evidence_locator") or "").strip()];add("hit_has_locator",not b3,b3[:10])
  b4=[r.get("cause_primary") for r in hm if r.get("cause_primary") and r["cause_primary"] not in PR];add("cause_in_taxonomy",not b4,b4[:10])
 cand=R.get("candidates") or []
 b5=[c.get("rid") for c in cand if not (c.get("title") or "").strip() or not (c.get("source_db") or c.get("query_id") or c.get("retrieved_at"))];add("candidate_trace",not b5,b5[:10])
 b6=[c.get("rid") for c in cand if c.get("doi") and not DX.match(str(c["doi"]))];add("doi_format",not b6,b6[:10])
 nr=len((R.get("supplement") or {}).get("rounds") or []);add("supplement_rounds",nr>=1,nr)
 add("offline",(R.get("runtime") or {}).get("network") is False,(R.get("runtime") or {}).get("network"))
 rep={"ok":all(c["ok"] for c in chk),"n_checks":len(chk),"failed":[c for c in chk if not c["ok"]],"checks":chk}
 try:jd(out/"verify_report.json",rep)
 except Exception:pass
 return rep


if __name__=="__main__":
 try:
  ap=argparse.ArgumentParser(prog="verify.py",description="Recompute the auditable parts of result.json: contract fields, coverage arithmetic, cause/repair completeness, candidate traceability, DOI format",
   epilog="example: verify.py --input /input --output /app/output")
  ap.add_argument("--input",default="/input",help="case input root (default /input)")
  ap.add_argument("--output",default="/app/output",help="result root holding result.json (default /app/output)")
  a=ap.parse_args()
  r=run_checks(Path(a.input),Path(a.output))
  print(json.dumps({"ok":r["ok"],"n_checks":r.get("n_checks"),"failed":[c["check"] for c in r.get("failed",[])]},ensure_ascii=False))
 except SystemExit:pass
 except Exception:
  print(json.dumps({"ok":False,"error":traceback.format_exc()[-600:]},ensure_ascii=False))
 sys.exit(0)
