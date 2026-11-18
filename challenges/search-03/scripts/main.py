#!/usr/bin/env python3
"""search-screen-rank 1.0.0: literature screening, tiering, ranking (stdlib, offline)."""
import argparse,csv,json,math,os,re,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path

V="1.0.0";T0=time.monotonic()
NOW=lambda:datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TO={"core":0,"method":1,"background":2,"pending":3,"exclude":4}
REL={"core":"direct","method":"indirect","background":"indirect","pending":"undetermined","exclude":"unrelated"}
PRE=("10.1101/","10.21203/","10.48550/","10.31219/","10.20944/")
STOP=set("a an the of and or for to in on with by from as at is are was were be this that these our their which no not can may should would than then also using used use between among into over under more most study paper results method approach".split())
DS={k:re.compile(v,re.I) for k,v in {"sr":r"systematic (rev|literature)|meta-?analys|prisma","rev":r"\breview\b|\bsurvey\b|overview","rct":r"randomi[sz]ed|\brct\b|placebo|double[- ]blind|controlled trial","coh":r"cohort|longitudinal|prospective","cc":r"case[- ]control","cs":r"cross[- ]sectional","ql":r"qualitative|interview","iv":r"in vitro|cell line|culture|organoid","an":r"\bmice\b|\bmouse\b|\brats?\b|murine"}.items()}
AL={k:v.split() for k,v in {"title":"title paper_title display_name","abstract":"abstract summary","kw":"keywords keyword terms","au":"authors author","yr":"year publication_year issued","ven":"venue journal","doi":"doi","url":"url link landing_page","db":"source_db database provider","qid":"query_id","q":"query","rat":"retrieved_at","lab":"label relevance gold grade","rid":"id record_id paper_id doc_id"}.items()}
RW={"relevant","include","included","yes","true","1","core","direct","keep","retain","high","2","3"}
IW={"irrelevant","exclude","excluded","no","false","0","unrelated","drop","out","low"}
CJK=re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+")
def lex():
 m={}
 try:
  for ln in (Path(__file__).resolve().parent.parent/"references"/"label_taxonomy.md").read_text(encoding="utf-8").splitlines():
   if re.match(r"^[a-z0-9][a-z0-9\-]*\|",ln,re.I):
    k,v=ln.split("|",1);m[k.strip().lower()]=[x.strip().lower() for x in v.split(",") if x.strip()]
 except Exception:pass
 return m


def g(d,ns,dv=None):
 if not isinstance(d,dict):return dv
 lo={str(k).lower():k for k in d}
 for n in ns:
  k=n if n in d else lo.get(n.lower())
  if k is not None and d.get(k) not in (None,"",[],{}):return d[k]
 return dv


def ft(v):
 if isinstance(v,str):return v
 if isinstance(v,(int,float)):return str(v)
 if isinstance(v,dict):return " ; ".join(x for x in (ft(y) for y in v.values()) if x)
 if isinstance(v,list):return " ; ".join(x for x in (ft(y) for y in v) if x)
 return ""


def tk(t):
 s=str(t or "").lower()
 o=[w for w in re.findall(r"[a-z][a-z0-9\-]{1,}",s) if len(w)>2 and w not in STOP]
 for r in CJK.findall(s):o+=[r[i:i+2] if i+1<len(r) else r[i] for i in range(len(r))]
 return o


def nd(v):
 if not v:return ""
 s=re.sub(r"\.v\d+$","",re.sub(r"\s+","",re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)","",str(v).strip().lower())).rstrip(".,;"))
 return s if re.match(r"^10\.\d{4,9}/\S+$",s) else ""


def nt(v):return re.sub(r"[^a-z0-9\u3400-\u9fff]+","",str(v or "").lower())


def py(v):
 if isinstance(v,(int,float)) and 1500<float(v)<2200:return int(v)
 m=re.search(r"(1[5-9]\d{2}|2[01]\d{2})",str(v or ""))
 return int(m.group(1)) if m else None


def intv(v):
 if isinstance(v,bool):return None
 if isinstance(v,(int,float)):return int(v)
 m=re.search(r"\d+",str(v or ""))
 return int(m.group()) if m else None


def lj(p):return json.loads(Path(p).read_text(encoding="utf-8",errors="replace"))


def ljs(p):
 o=[]
 for ln in Path(p).read_text(encoding="utf-8",errors="replace").splitlines():
  if ln.strip()[:1] in ("{","["):
   try:o.append(json.loads(ln))
   except Exception:pass
 return o


def lc(p):
 with open(p,encoding="utf-8",errors="replace",newline="") as f:
  try:return [dict(r) for r in csv.DictReader(f)]
  except Exception:
   f.seek(0);return [{"title":x.strip()} for x in f if x.strip()]


def isrec(d):
 t=g(d,AL["title"])
 return isinstance(d,dict) and isinstance(t,str) and len(t.strip())>=4 and any(g(d,AL[k]) for k in ("doi","abstract","kw","yr","au","ven","url"))


def harv(o,f,ptr,out,dp=0):
 if dp>8:return
 if isinstance(o,dict) and isrec(o):
  out.append((o,f,ptr))
  for k in ("versions","duplicates","records","hits"):
   if isinstance(o.get(k),(dict,list)):harv(o[k],f,ptr+"/"+k,out,dp+1)
  return
 for k,v in (o.items() if isinstance(o,dict) else enumerate(o) if isinstance(o,list) else []):
  if isinstance(v,(dict,list)):harv(v,f,ptr+"/"+str(k),out,dp+1)


def ev(txt,terms,lim=200):
 t=str(txt or "");tl=set(terms)
 S=[x.strip() for x in re.split(r"(?<=[.!?;:])\s+|\n+",t)]
 b=max(S,key=lambda x:(len(tl&set(tk(x))),len(x)>14),default="")
 return (b or t.strip())[:lim]


def vd(v):
 if isinstance(v,bool):return int(v)
 if isinstance(v,(int,float)):return int(float(v)>=1)
 s=str(v).strip().lower()
 return 1 if s in RW else (0 if s in IW else None)


def rec(d,i,f,ptr,qm):
 raw=g(d,AL["lab"]);lb=[]
 for x in (raw if isinstance(raw,list) else [] if raw is None else [raw]):
  v=g(x,["label","value","relevance","decision","gold","grade"]) if isinstance(x,dict) else x
  if isinstance(v,(str,int,float,bool)):lb.append(v)
 A=g(d,AL["au"])
 r={"record_id":str(g(d,AL["rid"]) or "r%04d"%i),"title":re.sub(r"\s+"," ",str(g(d,AL["title"]))).strip(),
  "abstract":re.sub(r"\s+"," ",ft(g(d,AL["abstract"]))).strip(),"keywords":ft(g(d,AL["kw"]))[:400],
  "authors":"; ".join(str(g(a,["name","full_name","family"],"") if isinstance(a,dict) else a).strip() for a in (A if isinstance(A,list) else [A]) if a)[:400] if A else "",
  "year":py(g(d,AL["yr"])),"venue":str(g(d,AL["ven"],"") or "")[:150],"doi":nd(g(d,AL["doi"])),
  "url":str(g(d,AL["url"],"") or "")[:400],"source_db":str(g(d,AL["db"],"") or ""),
  "query_id":str(g(d,AL["qid"],"") or ""),"retrieved_at":str(g(d,AL["rat"],"") or ""),"labels":lb,
  "flags":[],"provenance":{"file":f,"json_pointer":ptr or "/"}}
 if not r["doi"]:
  for n in ("ids","externalIds"):
   if isinstance(d.get(n),dict) and nd(g(d[n],["doi"])):r["doi"]=nd(g(d[n],["doi"]));break
 for k in ("abstract","year","doi"):
  if not r[k]:r["flags"].append(k+"_missing")
 if not r["retrieved_at"]:r["retrieved_at"]="not_provided";r["flags"].append("retrieved_at_missing")
 if not r["query_id"]:r["query_id"]="not_provided";r["flags"].append("query_id_missing")
 r["source_db"]=r["source_db"] or "input_material:"+(f.split("/")[0] or "case")
 return r


def group(rs):
 gs=[];bd={};bt={}
 for r in rs:
  i=bd.get(r["doi"]) if r["doi"] else None
  if i is None:i=bt.get(nt(r["title"]))
  if i is None:
   i=len(gs);gs.append([])
   if r["doi"]:bd[r["doi"]]=i
   bt.setdefault(nt(r["title"]),i)
  gs[i].append(r)
 out=[];cfs=[]
 for m in gs:
  m.sort(key=lambda r:(any(r["doi"].startswith(p) for p in PRE),-len(r["abstract"]),str(r["record_id"])))
  c=dict(m[0]);c["group_ids"]=[r["record_id"] for r in m];c["version_count"]=len(m)
  c["labels"]=[x for r in m for x in r["labels"]]
  if len(m)>1:
   pre=[r for r in m if any(r["doi"].startswith(p) for p in PRE)]
   pub=[r for r in m if r["doi"] and not any(r["doi"].startswith(p) for p in PRE)]
   c["flags"].append("preprint_published_pair" if pre and pub else "merged_duplicate")
  ys=sorted({r["year"] for r in m if r["year"]});op=[vd(x) for r in m for x in r["labels"] if vd(x) is not None]
  if len(ys)>1 or len(set(op))>1:
   cfs.append({"type":"year_disagreement" if len(ys)>1 else "label_disagreement","ids":c["group_ids"],"years":ys,"opinions":op})
  out.append(c)
 return out,cfs


def judge(rs,q,qe,txt,inc,exc,yr):
 D=[(set(tk(r["title"])),set(tk(r["keywords"])),set(tk(r["abstract"]))) for r in rs]
 df={}
 for t,k,a in D:
  for w in t|k|a:df[w]=df.get(w,0)+1
 n=max(1,len(D));idf={w:math.log((n+1.0)/(1.0+df[w]))+1.0 for w in df}
 req={k for k,p in DS.items() if p.search(txt)}
 it=tk(inc);et=tk(exc);tot=sum(idf.get(w,1.0) for w in q) or 1.0
 xtot=sum(idf.get(w,1.0) for w in qe) or 1.0;y0,y1=yr;out=[]
 CV=[min(1.0,sum(idf.get(w,1.0)*min(1.0,(w in t)+0.7*(w in k)+0.6*(w in a)) for w in q)/tot) for t,k,a in D]
 mx=(max(CV) if CV else 1.0) or 1.0
 for r,(t,k,a),cv in zip(rs,D,CV):
  cov=min(1.0,(cv/mx)**0.5)
  fd={x for x,p in DS.items() if p.search(r["title"]+" "+r["keywords"]+" "+r["abstract"])}
  des=(1.0 if fd&req else 0.45 if fd else 0.15) if req else (1.0 if fd else 0.6)
  ex=min(1.0,sum(idf.get(w,1.0)*min(1.0,(w in t)+0.7*(w in k)+0.6*(w in a)) for w in qe)/xtot) if qe else 0.0
  sc=0.42*cov+0.22*ex+0.18*des+0.12*min(1.0,len(r["abstract"])/700.0);vio=[]
  if r["year"] and y0 and y1 and not (y0<=r["year"]<=y1):sc*=0.45;vio.append("year_out_of_range")
  if et:
   e=[w for w in et if w in t|k|a]
   if e:sc*=0.30;vio.append("exclude_term:"+",".join(sorted(e)[:3]))
  if it and not [w for w in it if w in t|k|a]:sc*=0.78;vio.append("no_include_term")
  sc=round(min(0.99,sc),3)
  if "year_out_of_range" in vio:tier,why="exclude","年份超出时间窗"
  elif any(x.startswith("exclude_term") for x in vio):tier,why="exclude","命中排除条件:"+[x for x in vio if x.startswith("exclude")][0][12:]
  elif not r["abstract"]:tier,why="pending","缺摘要"
  elif len({vd(x) for x in r["labels"]}-{None})>1:tier,why="pending","标注冲突"
  elif sc>=0.62 and des>=0.45 and not vio:tier,why="core","命中术语%.2f，设计一致"%cov
  elif sc>=0.50 and des>=0.45:tier,why="method","方法学表述重合"
  elif sc>=0.40:tier,why="background","对象/设计不匹配"
  else:tier,why="exclude","覆盖%.2f/设计%.2f 低于线"%(cov,des)
  out.append(dict(r,coverage=round(cov,3),design_fit=round(des,3),relevance_score=sc,violations=vio,
   tier=tier,relevance=REL[tier],relevance_reason=why,id=r["record_id"],
   decision="include" if tier in ("core","method","background") else tier,
   evidence=[{"quote":ev(r["abstract"] or r["title"],q[:60]),"locator":"abstract" if r["abstract"] else "title"}],
   flags="|".join(sorted(set(r["flags"]+vio)))))
 return out


def met(rank,ks,gf):
 o={};allr=sorted([gf(c) for c in rank],reverse=True)
 for k in ks:
  kk=min(k,len(rank)) or 1;rel=[gf(c) for c in rank[:kk]]
  dcg=sum((2**max(0,x)-1)/math.log2(i+2) for i,x in enumerate(rel))
  idcg=sum((2**max(0,x)-1)/math.log2(i+2) for i,x in enumerate(allr[:kk])) or 1e-9
  o["P@%d"%k]=round(sum(1 for x in rel if x>=1)/float(kk),3);o["nDCG@%d"%k]=round(dcg/idcg,3)
 return o


def gold(c):
 v=[vd(x) for x in c["labels"]];v=[x for x in v if x is not None]
 return (1 if 1 in v else 0) if v else None


def wj(p,o):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_suffix(p.suffix+".tmp");t.write_text(json.dumps(o,ensure_ascii=False,indent=1),encoding="utf-8");os.replace(t,p)


def cfld(o):
 if isinstance(o,dict):return [(str(k),v) for k,v in o.items()]
 return [(str(x),None) if isinstance(x,str) else (str(g(x,["name","field","key","id"])),x) for x in (o if isinstance(o,list) else []) if isinstance(x,str) or g(x,["name","field","key","id"])]


def fill(cf,r):
 nk=lambda s:re.sub(r"[^a-z0-9]","",str(s).lower()).rstrip("s")
 ix={}
 for k,v in r.items():ix.setdefault(nk(k),v)
 ex={"candidatelist":r.get("candidates"),"rankedlist":r.get("candidates"),"topk":r.get("top_k")}
 rep={}
 for n,sp in cf:
  k=nk(n)
  if k in ix or k in ex:
   if r.get(n) in (None,"",[],{}):r[n]=ix.get(k) if k in ix else ex[k]
   rep[n]="filled:"+("same_named_field" if k in ix else "alias")
  else:
   t=str(g(sp,["type","dtype","kind"],"") or "").lower() if isinstance(sp,dict) else ""
   if n not in r:r[n]=[] if ("array" in t or "list" in t) else {} if ("dict" in t or "object" in t) else "" if ("str" in t or "text" in t) else None
   rep[n]="null_no_source"
 return rep


def run(a,out):
 I=Path(a.input).resolve();E=[];DG=[];R={"case_id":None,"status":"partial"};C={};cp=None;con={}
 for f in [I/"case.json"]+sorted(I.glob("case*.json")):
  if f.is_file():
   try:
    C=lj(f);cp=f;con=g(C,["output_contract","output_schema","required_output","output_fields"],{}) or {}
    R["case_id"]=g(C,["case_id","caseId","task_id","id"]);break
   except Exception as ex:E.append({"stage":"read_case","file":str(f),"error":repr(ex)})
 if cp is None:E.append({"stage":"read_case","error":"case.json missing or unparsable"})
 cf=cfld(con);R.update(contract_echo=con,contract_fields=[n for n,_ in cf]);wj(out/"result.json",R)
 sc={}
 for k in ("organizer_supplied_scope","scope","search_scope","constraints","criteria"):
  v=g(C,[k])
  if isinstance(v,dict):sc.update(v)
  elif v:sc.setdefault("notes",ft(v))
 ins=ft(g(C,["task_instruction","instruction","task","prompt","question","objective","research_question"],""))
 top=ft(g(sc,["topic","research_question","question","objective","title","pico"],""))
 txt=" ".join(x for x in (ins,top,ft(sc)) if x)
 inc=ft(g(sc,["include","inclusion","include_terms","must_have"]));exc=ft(g(sc,["exclude","exclusion","exclude_terms","must_not_have"]))
 yr=(py(g(sc,["year_start","from_year","start_year","since"])),py(g(sc,["year_end","to_year","end_year","until"])))
 m=re.search(r"((?:19|20)\d{2})\s*[-–—~]\s*((?:19|20)\d{2})",txt)
 if not any(yr) and m:yr=(int(m.group(1)),int(m.group(2)))
 mk=intv(g(sc,["max_k","top_k","k"])) or 10
 raw=[];qr=[]
 files=[p for p in sorted(I.rglob("*")) if p.is_file() and p!=cp]
 for p in files:
  rel=str(p.relative_to(I));ext=p.suffix.lower()
  try:
   if ext==".json":
    o=lj(p)
    if isinstance(o,dict) and ("queries" in o or "query_log" in o):qr+=(o.get("queries") or [])+(o.get("query_log") or [])
    harv(o,rel,"",raw)
   elif ext in (".jsonl",".ndjson"):
    rw=ljs(p);qr+=rw if "quer" in p.name.lower() else [];harv(rw,rel,"",raw)
   elif ext==".csv":
    rw=lc(p);qr+=rw if "quer" in p.name.lower() else [];harv(rw,rel,"",raw)
   elif ext==".pdf":raw.append(({"title":re.sub(r"[_\-]+"," ",p.stem),"source_db":"input_attachment"},rel,"/filename"))
   elif ext in (".xlsx",".docx"):DG.append({"stage":"parse","file":rel,"action":"binary office file not parsed (stdlib only); export CSV/JSON"})
  except Exception as ex:DG.append({"stage":"parse","file":rel,"error":repr(ex)})
 if not raw:E.append({"stage":"discover_records","error":"no candidate records found"})
 qm={};qs=[]
 for i,q in enumerate([x for x in qr if isinstance(x,dict)]):
  qid=str(g(q,["query_id","qid","id"],"q%02d"%(i+1)));rw=ft(g(q,["query","raw","query_text","text","q"],""));qm[qid]=rw
  qs.append({"query_id":qid,"db":ft(g(q,["db","database","source","provider"])),"raw":rw[:500],"hits_reported":g(q,["hits","total","count","num_results"]),"status":ft(g(q,["status","state"])),"error":ft(g(q,["error"])),"retrieved_at":ft(g(q,["retrieved_at"]))})
 if not qs:qs.append({"query_id":"q_derived","db":"n/a","raw":(top or ins)[:300],"hits_reported":len(raw),"status":"derived_from_input","error":"","retrieved_at":""})
 q=[];qe=[];seen=set();LM=lex()
 for w in tk(exc):
  for k,vs in LM.items():
   if w==k or w in vs:exc+=" "+" ".join([k]+vs)
 for w in tk(txt):
  if w not in seen:seen.add(w);q.append(w)
 for w in list(q):
  for k,vs in LM.items():
   if w==k or w in vs:
    for x in [k]+vs:
     if x and x not in seen:seen.add(x);qe.append(x)
 rs=[];sig=set()
 for i,(d,f,ptr) in enumerate(raw):
  r=rec(d,i+1,f,ptr,qm)
  if (nt(r["title"]),r["doi"]) not in sig:sig.add((nt(r["title"]),r["doi"]));rs.append(r)
 mg,cfs=group(rs);cand=judge(mg,q,qe,txt,inc,exc,yr)
 cand.sort(key=lambda c:(TO[c["tier"]],-c["relevance_score"],-(c["year"] or 0),nt(c["title"]),str(c["id"])))
 for i,c in enumerate(cand):c.update(rank=i+1,tie_group=sum(1 for x in cand if x["relevance_score"]==c["relevance_score"]))
 for x in qs:
  li=[c for c in cand if c["query_id"]==x["query_id"]] or (cand if x["query_id"]=="q_derived" else [])
  TI=[c["tier"] for c in li];x.update(records_linked=len(li),kept=sum(1 for c in li if c["decision"]=="include"),pending=TI.count("pending"),excluded=TI.count("exclude"))
 lab=[c for c in cand if gold(c) is not None]
 mt={"gold_source":"none","labelled_records":len(lab),"note":"少于3条标注"}
 if len(lab)>=3:
  ks=sorted({k for k in a.k if k<=len(lab)}|{min(mk,len(lab))});sk=met(cand,ks,gold)
  bm=met(sorted(cand,key=lambda c:(-c["coverage"],-c["relevance_score"])),ks,gold)
  mt={"gold_source":"input labels","labelled_records":len(lab),"k":ks,"skill":sk,"baseline":bm,"baseline_definition":"coverage-only","delta":{k:round(sk[k]-bm[k],3) for k in ks}}
 cnt={t:sum(1 for c in cand if c["tier"]==t) for t in TO}
 ids=[c["record_id"] for c in cand if not c["abstract"]][:100]
 u=[]
 if not rs:u.append("空候选集")
 if ids:u.append("缺摘要%d条"%len(ids))
 if any(yr):u.append("时间窗%s-%s"%(yr[0] or "?",yr[1] or "?"))
 u.append("基于题录+摘要，不含全文")
 if inc and exc and set(tk(inc))&set(tk(exc)):
  bo=sorted(set(tk(inc))&set(tk(exc)));cfs.append({"type":"criteria_overlap","terms":bo[:8]});u.append("纳排重叠词%s按exclude优先"%"/".join(bo[:4]))
 R.update(status="ok" if cand else "insufficient_evidence",
  scope={"topic":top[:800],"include_text":inc[:800],"exclude_text":exc[:800],"years":list(yr),"max_k":mk},
  method={"name":"search-screen-rank","version":V,"tie_break":"tier>score>year>title>id","scoring":"0.42cov+0.22exp+0.18design+0.12evidence; pen .45/.30/.78"},
  candidates=cand,candidate_count=len(cand),input_record_count=len(rs),tiers=cnt,top_k=[c["id"] for c in cand[:mk]],
  screening={"input_records":len(rs),"groups":len(cand),"merged":sum(1 for c in cand if c["version_count"]>1),"with_abstract":len(rs)-len(ids),"missing_abstract_ids":ids},
  queries=qs,query_log_path="query_log.json",
  metrics=mt,conflicts=cfs,errors=E,degradations=DG,uncertainty=u,
  pending_human=[{"record_id":c["record_id"],"title":c["title"][:160],"reason":c["relevance_reason"]} for c in cand if c["tier"]=="pending"],
  runtime={"version":V,"model_requests":0,"elapsed_sec":round(time.monotonic()-T0,2)})
 cols="rank record_id tier decision relevance score title authors year venue doi url source_db query_id retrieved_at design_fit relevance_reason flags".split()
 with open(out/"candidates.csv","w",encoding="utf-8-sig",newline="") as f:
  w=csv.writer(f);w.writerow(cols+["evidence_quote"])
  for c in cand:w.writerow([dict(c,score=c["relevance_score"]).get(k,"") for k in cols]+[c["evidence"][0]["quote"][:200]])
 wj(out/"query_log.json",{"case_id":R["case_id"],"generated_at":NOW(),"queries":qs})
 rep=fill(cf,R);R.update(contract_fill=rep,contract_missing=[n for n,v in rep.items() if v=="null_no_source"])
 if R["status"]=="ok" and (not cand or not cf):R["status"]="partial"
 return R


def main(argv=None):
 ap=argparse.ArgumentParser(prog="main.py",description="Screen, tier and rank a candidate set (stdlib, offline, exit 0).")
 ap.add_argument("--input",default="/input")
 ap.add_argument("--out",default="/app/output")
 ap.add_argument("--k",default="5,10")
 a,un=ap.parse_known_args(argv)
 try:a.k=sorted({int(x) for x in str(a.k).replace(" ","").split(",") if x.isdigit()}) or [5,10]
 except Exception:a.k=[5,10]
 out=Path(a.out)
 try:out.mkdir(parents=True,exist_ok=True)
 except Exception:out=Path.cwd()
 R={"case_id":None,"status":"partial","candidates":[],"errors":[],"degradations":[],"uncertainty":[],"pending_human":[],"sources":[]}
 try:
  R=run(a,out)
 except Exception:
  R.setdefault("errors",[]).append({"stage":"run","error":traceback.format_exc(limit=6)})
  R["status"]="partial" if R.get("candidates") else "input_error"
  R.setdefault("uncertainty",[]).append("运行中断，保留中断前可用部分")
  try:fill(cfld(R.get("contract_echo") if isinstance(R.get("contract_echo"),dict) else {}),R)
  except Exception:pass
 finally:
  R["finalized_at"]=NOW();R["runtime"]=dict(R.get("runtime") or {},elapsed_sec=round(time.monotonic()-T0,2),exit_code=0)
  for k,dv in dict(case_id=None,status="partial",candidates=[],sources=[],uncertainty=[],pending_human=[],errors=[],degradations=[],changes=[]).items():R.setdefault(k,dv)
  try:wj(out/"result.json",R)
  except Exception:Path("/tmp/result.json").write_text(json.dumps(R,ensure_ascii=False,indent=1),encoding="utf-8")
 return 0


if __name__=="__main__":
 try:sys.exit(main())
 except SystemExit:sys.exit(0)
 except Exception:sys.exit(0)
