#!/usr/bin/env python3
"""search-07 coverage & gap auditor (pipeline).
Freezes the reference set, measures coverage on an explicit denominator,
attributes each miss to a query/field/year-window/source, then runs directed
supplementary rounds. The deterministic core is imported from verify.py.
    python3 -B scripts/main.py --input /input --output /app/output
"""
import argparse,csv,json,math,re,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify import *   # shared deterministic core
SK="search-coverage-gap-auditor";V="1.1.0";LG=[]
def wil(k,n,z=1.96):
 if not n:return [None,None]
 p=k/float(n);d=1+z*z/n;c=(p+z*z/(2*n))/d
 h=z*math.sqrt(max(0.,p*(1-p)/n+z*z/(4.*n*n)))/d
 return [round(max(0.,c-h),4),round(min(1.,c+h),4)]
def log(*a):
 s=" ".join(map(str,a));LG.append(s)
 try:print(s,flush=True)
 except Exception:pass

def md(res):
 c=res.get("coverage") or {};r=res.get("reference_set") or {};s=res.get("supplement") or {};b=res.get("baseline_comparison") or {}
 L=["# 检索覆盖率与遗漏分析报告","","- case_id `%s` · status `%s`"%(res.get("case_id"),res.get("status")),
  "- coverage **%s** (%s/%s eligible) · Wilson95 %s"%(c.get("coverage"),c.get("n_hit"),c.get("n_eligible"),c.get("wilson95")),
  "- 口径 %s"%c.get("formula"),"","## 1 参考集（冻结分母）","- 来源 %s"%", ".join(str(x.get("path")) for x in (r.get("sources") or [])[:4]),
  "- 原始 %s → 去重 %s → 分母 %s · 排除 %s"%(r.get("n_items_raw"),r.get("n_unique"),r.get("n_eligible"),r.get("n_excluded"))]
 for e in (r.get("excluded") or [])[:8]:L.append("  - 排除 %s (%s) %s"%(e["ref_id"],e["reason"],e["title"][:70]))
 L+=["","## 2 覆盖（逐条状态/命中记录/归因/证据见 hit_matrix.csv）"]
 for k in ("n_eligible","n_hit","n_miss","coverage","miss_rate","coverage_over_all_refs"):L.append("- %s = %s"%(k,c.get(k)))
 L+=["","## 3 漏检分类"]
 for x in (res.get("miss_taxonomy") or {}).get("classes",[]):
  if x["n"]:L.append("- %s %s: %s (%s) → %s"%(x["code"],x["label"],x["n"],x["share_of_miss"],(x["repair"] or "")[:60]))
 L+=["","## 4 补充检索与边际收益"]
 for x in s.get("rounds",[]):L.append("- 第 %s 轮 `%s` 新增 %s"%(x.get("round"),x.get("execution"),x.get("new_hits")))
 L+=["- 覆盖率 %s → %s；残余遗漏 %s %s"%(s.get("coverage_before"),s.get("coverage_after_offline"),s.get("residual_misses"),json.dumps(s.get("residual_by_cause"),ensure_ascii=False)),
  "- 停止规则 %s"%s.get("stop_rule"),"","## 5 对照（同参考集同池复算）",
  "- 精确匹配 %s · 结果集为分母 %s · 本 Skill %s"%(b.get("baseline_exact_title_doi_only"),b.get("baseline_circular_denominator"),b.get("skill_coverage")),"","## 6 限制与待确认"]
 for x in (res.get("limits") or [])+(res.get("uncertainty") or []):L.append("- %s"%x)
 for x in (res.get("pending_human") or [])[:8]:L.append("- 待确认 %s: %s"%(x.get("item"),x.get("question")))
 return "\n".join(L)+"\n"
def main(av=None):
 t0=time.time()
 ap=argparse.ArgumentParser(prog="main.py",description="Freeze a reference set, measure auditable coverage, attribute each miss to a query/field/window/source, run supplementary rounds.",
  epilog="example (illustrative, not a case result): main.py --input /input --output /app/output")
 ap.add_argument("--input",default="/input",help="case input root, read only (default /input)")
 ap.add_argument("--output",default="/app/output",help="result root (default /app/output)")
 ap.add_argument("--accept",type=float,default=0.86,help="fuzzy accept for adjudication")
 ap.add_argument("--topk",type=int,default=50,help="candidates kept")
 a=ap.parse_args(av)
 inp,out=Path(a.input),Path(a.output)
 try:out.mkdir(parents=True,exist_ok=True)
 except Exception:out=Path("/app/output");out.mkdir(parents=True,exist_ok=True)
 res={"case_id":None,"status":"partial","errors":[],"degradations":[],"pending_human":[],"uncertainty":[],"changes":[],"sources":[],"limits":[],"task_type":"search_coverage_audit","skill":SK}
 jd(out/"result.json",{"case_id":None,"status":"partial","skill":SK,"note":"partial skeleton written before analysis"})
 res["changes"].append({"stage":"init","action":"partial result.json written"})
 case={}
 try:
  cp=inp/"case.json"
  if not cp.exists():
   f=sorted(inp.rglob("case*.json")) if inp.exists() else []
   cp=f[0] if f else None
   if cp:res["degradations"].append({"stage":"case","note":"case.json absent, used %s"%cp.name})
  if cp and cp.exists():
   case=json.loads(cp.read_text(encoding="utf-8",errors="replace"))
   if not isinstance(case,dict):case={"payload":case}
  else:res["errors"].append({"stage":"case","error":"no case.json under %s"%inp})
 except Exception as e:
  res["errors"].append({"stage":"case","error":"case.json unreadable: %s"%e});case={}
 oc=g(case,["output_contract","outputcontract","contract","output_schema"]) or {}
 res["case_id"]=g(case,["case_id","caseid","id","task_id"])
 ins=str(g(case,["task_instruction","instruction","task","question","prompt"]) or "")
 sr=g(case,["organizer_supplied_scope","scope","search_scope","constraints"]) or {}
 scope={"topic":str(g(sr,["topic","question","research_question","subject"]) or ins)[:400],
  "databases":g(sr,["databases","db","sources","indexes"]) or [],"years":g(sr,["years","year_range","window"]),
  "language":g(sr,["language","lang"]),"max_k":g(sr,["max_k","topk","k","max_results"]),
  "include":g(sr,["include","inclusion","criteria"]),"exclude":g(sr,["exclude","exclusion"]),"seeds":g(sr,["seeds","seed_papers"]) or []}
 if isinstance(scope["years"],str):
  ys=[int(x) for x in re.findall(r"(1[6-9]\d{2}|20\d{2})",scope["years"])][:2];scope["years"]=ys or None
 if isinstance(scope["years"],list):
  ys=[y for y in (yr(x) for x in scope["years"]) if y];scope["years"]=[min(ys),max(ys)] if ys else None
 res["scope"]=scope
 fs,sts=disc(inp)
 res["sources"]=[f["path"] for f in fs]
 res["input_manifest"]={"root":str(inp),"n_files":len(fs),"files":fs[:60],"n_structures":len(sts)}
 if not fs:res["errors"].append({"stage":"discover","error":"input tree empty or missing"})
 R,P,Qs=rset(sts)
 items=[]
 for s in R[:6]:items.extend(s["items"])
 refs,dl=nrefs(items)
 exl=[]
 for r in refs:
  e=excl(r);r["anomaly"]=None
  if not r["doi"]:r["anomaly"]="missing_doi"
  elif not DX.match(r["doi"]):r["anomaly"]="malformed_doi"
  if not r["year"]:r["anomaly"]=(r["anomaly"]+"+missing_year") if r["anomaly"] else "missing_year"
  if e:exl.append({"ref_id":r["ref_id"],"title":r["title"][:150],"reason":e,"status":r["status"]})
 elig=[r for r in refs if excl(r) is None]
 RIDX={r["ref_id"]:i for i,r in enumerate(refs)}
 res["reference_set"]={"sources":[{"path":s["path"],"n_items":len(s["items"]),"derived":(s.get("parent") or {}).get("derived")} for s in R[:6]],
  "n_items_raw":len(items),"n_unique":len(refs),"n_eligible":len(elig),"n_excluded":len(exl),"excluded":exl,"dedupe":dl[:50],
  "dedupe_rule":"DOI exact else normalised title+year; first kept",
  "frozen_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
  "reporting_policy":"main coverage on the eligible denominator; coverage_over_all_refs also reported"}
 pool,qm=[],{}
 for i,s in enumerate(P):
  qid=g(s["parent"],QI) or qid_of(s["path"],i+1);qm.setdefault(qid,[]).append(s)
  for it in s["items"]:
   if not isinstance(it,dict):continue
   r=rec(it,{"path":s["path"],"query_id":g(it,QI) or qid,"source_db":g(it,SRC)})
   if not r["title"] and not r["doi"]:continue
   r["rid"]="P%04d"%(len(pool)+1);pool.append(r)
 qs=[]
 for i,s in enumerate(Qs):
  ids={g(it,QI) for it in s["items"] if isinstance(it,dict)}-{None}
  if len(ids)>1:qs.extend(bq({"parent":it,"items":[],"path":s["path"]},g(it,QI)) for it in s["items"])
  else:qs.append(bq(s,qid_of(s["path"],i+1)))
 for qid in qm:
  if not any(q["query_id"]==qid for q in qs):
   s=qm[qid][0];q=bq({"parent":s["parent"],"items":s["items"],"path":s["path"]},qid)
   if q["raw"] or q["hits"] is not None:qs.append(q)
 if not qs and pool:
  s=P[0];qs.append(bq({"parent":{"query_id":"q1"},"items":s["items"],"path":s["path"]},"q1"))
  res["degradations"].append({"stage":"queries","note":"no query log; one synthetic entry, query null"})
 for q in qs:q["records"]=sum(1 for r in pool if r["query_id"]==q["query_id"]) or q["records"]
 up,ps=[],{}
 for r in pool:
  k=r["doi"] or nt(r["title"])+"|"+str(r["year"])
  pr={"query_id":r["query_id"],"source_db":r["source_db"],"retrieved_at":r["retrieved_at"],"path":r["raw_path"]}
  if k in ps:ps[k]["provenance"].append(pr);continue
  r["provenance"]=[pr];ps[k]=r;up.append(r)
 nraw=len(pool);pool=up
 edges={}
 for s in sts:
  if not s["items"] or not isinstance(s["items"][0],dict):continue
  if not any(nk(k) in ("citing","cited","source","target","from","to") for k in s["items"][0]):continue
  for it in s["items"][:4000]:
   x,y=g(it,["citing","source","from"]),g(it,["cited","target","to"])
   if x is None or y is None:continue
   for u,v in ((x,y),(y,x)):
    ku=nd(u) or nt(u)
    if ku:edges.setdefault(ku,[]).append({"edge":[str(u)[:80],str(v)[:80]],"path":s["path"]})
 for r in refs:r["citable"]=r["doi"] or nt(r["title"])
 srcs=set((r["source_db"] or "").lower() for r in pool if r["source_db"])
 res["retrieval_pool"]={"n_records_raw":nraw,"n_records":len(pool),"n_queries":len(qs),"sources":sorted(srcs),
  "missing_retrieved_at":sum(1 for r in pool if not r["retrieved_at"]),"n_citation_edges":len(edges)}
 if not pool:res["errors"].append({"stage":"pool","error":"no retrieved records: all references reported as C11"})
 M=match(refs,pool) if pool else {i:None for i in range(len(refs))}
 hm,miss=[],[]
 for i,r in enumerate(refs):
  e=excl(r);m=M.get(i)
  row={"ref_id":r["ref_id"],"title":r["title"][:200],"year":r["year"],"doi":r["doi"] or None,"status":"miss","match_tier":None,
   "match_score":None,"matched_rid":None,"matched_source":None,"matched_query_id":None,"cause_primary":None,"causes_all":[],
   "evidence_locator":None,"repair":None}
  if e:
   row.update(status="excluded",cause_primary="C10",causes_all=["C10"],repair="excluded:"+e,evidence_locator="reference_set.excluded[%s]"%r["ref_id"])
   hm.append(row);continue
  sp=m[0] if (m and m[1]=="soft_candidate") else None
  if m and m[1]!="soft_candidate":
   p=pool[m[0]]
   row.update(status="hit",match_tier=m[1],match_score=round(m[2],3),matched_rid=p["rid"],matched_source=p["source_db"] or p["raw_path"],
    matched_query_id=p["query_id"],evidence_locator="%s#%s q=%s retrieved_at=%s"%(p["raw_path"],p["rid"],p["query_id"] or "n/a",p["retrieved_at"] or "n/a"))
   hm.append(row);continue
  C=attr(r,sp,pool,qs,scope,edges,srcs);codes=[c[0] for c in C]
  pr_=sorted(codes,key=lambda c:PR.index(c) if c in PR else 99)[0];ev=dict(C[codes.index(pr_)][1])
  row.update(cause_primary=pr_,causes_all=codes,repair=tx(pr_,"repair"),cause_evidence=ev,
   evidence_locator="hit_matrix %s cause=%s %s"%(r["ref_id"],pr_,json.dumps(ev,ensure_ascii=False)[:380]))
  hm.append(row);miss.append(row)
 res["hit_matrix"]=hm
 nh=sum(1 for x in hm if x["status"]=="hit");nm=len(miss)
 c=round(nh/float(len(elig)),4) if elig else None
 res["coverage"]={"denominator":"reference_set.n_eligible","n_eligible":len(elig),"n_hit":nh,"n_miss":nm,"coverage":c,
  "miss_rate":round(nm/float(len(elig)),4) if elig else None,"coverage_over_all_refs":round(nh/float(len(refs)),4) if refs else None,
  "wilson95":wil(nh,len(elig)),
  "formula":"matched eligible refs / frozen eligible ref set; denominator fixed before matching, never derived from results",
}
 tl={}
 for m in miss:
  for k in m["causes_all"]:tl.setdefault(k,[]).append(m["ref_id"])
 res["miss_taxonomy"]={"order":PR,"classes":[{"code":k,"label":tx(k),"n":len(tl.get(k,[])),
  "share_of_miss":round(len(tl.get(k,[]))/float(max(1,nm)),4),"example_ref_ids":tl.get(k,[])[:6],"repair":tx(k,"repair"),
  "definition":tx(k,"definition"),"evidence_required":tx(k,"evidence")} for k in PR],
  "primary_counts":{k:sum(1 for m in miss if m["cause_primary"]==k) for k in PR},
  "note":"causes_all lists every supported cause; cause_primary is the highest-priority attributable one"}
 rnds=[];new=[]
 r1=[m for m in miss if "C01" in m["causes_all"]]
 for m in r1:
  rf=refs[RIDX[m["ref_id"]]];mm=M.get(refs.index(rf));pi=mm[0] if mm else None
  if pi is None:continue
  p=pool[pi];st=rt(rf["title"],p["title"])
  if st>=a.accept and (not rf["year"] or not p["year"] or abs(rf["year"]-p["year"])<=1):
   m.update(status="hit_recovered",match_tier="adjudicated_auto",match_score=round(st,3),matched_rid=p["rid"],
    matched_source=p["source_db"] or p["raw_path"],matched_query_id=p["query_id"],
    evidence_locator="round1 alignment %s~%s title_ratio=%.3f"%(m["ref_id"],p["rid"],st));new.append(m["ref_id"])
  else:res["pending_human"].append({"item":m["ref_id"],"question":"confirm identity vs %s (title ratio %.3f)"%(p["rid"],st),"threshold":a.accept})
 rnds.append({"round":1,"action":"alignment repair (tiered matcher + adjudication)","targets":[m["ref_id"] for m in r1],
  "execution":"offline_recomputable","new_hits":len(new),"new_ref_ids":new,
  "rule":"accept ratio >= %.2f and |dyear|<=1; 0.62-%.2f queued"%(a.accept,a.accept)})
 reach=[]
 if edges:
  for m in miss:
   if m["status"]!="miss":continue
   rf=refs[RIDX[m["ref_id"]]];ee=edges.get(rf["citable"],[])
   if ee:m["citation_route"]=ee[0]["edge"];reach.append(m["ref_id"])
  rnds.append({"round":2,"action":"citation routing (snowball on the retained graph)","execution":"route_proposed_live_required","new_hits":0,
   "reachable_ref_ids":reach[:20],"rule":"an edge proves the route exists, but the record still needs a fetch, so it is not counted in coverage"})
 else:rnds.append({"round":2,"action":"citation routing","execution":"not_available","new_hits":0,"note":"no citation graph in input"})
 specs=[];byc={}
 for m in miss:
  if m["status"]=="miss":byc.setdefault(m["cause_primary"],[]).append(m)
 qv=set()
 for q in qs:qv|=set(q["tokens"])
 for k in [x for x in PR if x in byc]:
  gr=byc[k];ev=gr[0].get("cause_evidence") or {}
  sp={"cause":k,"label":tx(k),"query_id":ev.get("query_id"),"repair":tx(k,"repair"),"added_terms":ev.get("uncovered_terms") or [],"window":ev.get("window")}
  pred=[m["ref_id"] for m in gr if tk(refs[RIDX[m["ref_id"]]]["title"])&(qv|set(sp["added_terms"]))]
  sp.update(executable_offline=False,requires_live_source=True,predicted_catch=len(pred),predicted_ref_ids=pred[:20],
   prediction_basis="term-set test on reference titles; the proposed query covers >=1 distinctive term of each listed reference, not executed")
  specs.append(sp)
 rnds.append({"round":3,"action":"query repair (term/window/field/source)","execution":"spec_generated_live_required","new_hits":0,"specs":specs,
  "note":"no network: specs and predicted catch only; a corpus-limited re-run adds 0 because every retained record is already in the pool"})
 nha=nh+len(new);ca=round(nha/float(len(elig)),4) if elig else None
 resid=[m for m in miss if m["status"]=="miss"]
 res["supplement"]={"rounds":rnds,"coverage_before":c,"coverage_after_offline":ca,"measured_gain_hits":len(new),
  "measured_gain_rate":None if c is None else round(ca-c,4),"reachable_not_counted":len(reach),
  "predicted_catch_total":sum(x["predicted_catch"] for x in specs),
  "stop_rule":"stop when a round adds 0 offline hits and every residual class needs external access; max 3 rounds, 64 req / 900 s",
  "residual_misses":len(resid),
  "residual_by_cause":{k:sum(1 for m in resid if m["cause_primary"]==k) for k in PR if any(m["cause_primary"]==k for m in resid)},
  "residual_note":"residual causes are source-side; they close only by executing the specs"}
 stk=tk(scope["topic"]);cnd=[]
 for p in pool:
  link=None
  for i,m in M.items():
   if m and m[1]!="soft_candidate" and pool[m[0]]["rid"]==p["rid"]:link=refs[i]["ref_id"];break
  ct=len(p["tok"]&stk)/float(len(stk)) if stk else 0.0;pv=len(p.get("provenance") or [])
  cnd.append({"rank":0,"title":p["title"][:200],"authors":"; ".join(p["authors"][:6]),"year":p["year"],"venue":p["venue"],
   "doi":p["doi"] or None,"url":p["url"] or None,"source_db":p["source_db"] or None,"retrieved_at":p["retrieved_at"] or None,
   "query_id":p["query_id"] or None,"rid":p["rid"],"ref_link":link,
   "relevance_score":round(.5*(1. if link else 0.)+.3*min(1.,ct)+.2*min(1.,pv/3.),4),
   "relevance_reason":"reference_match=%s; scope_term_coverage=%.2f; distinct_provenance=%d"%(link or "none",ct,pv),"provenance":p.get("provenance")})
 cnd.sort(key=lambda x:(-x["relevance_score"],x["title"]))
 for i,x in enumerate(cnd):x["rank"]=i+1
 res["candidates"]=cnd[:max(a.topk,50)]
 res["queries"]=[{"query_id":q["query_id"],"db":q["db"],"raw":q["raw"],"fields":q["fields"],"hits":q["hits"],
  "records_retained":q["records"],"year_from":q["year_from"],"year_to":q["year_to"],"status":q["status"],"error":q["error"],
  "path":q["path"],"n_tokens":len(q["tokens"])} for q in qs]
 mt={"n_pool":len(pool),"n_query":len(qs),"dedupe_removed":nraw-len(pool),"missing_retrieved_at":sum(1 for p in pool if not p["retrieved_at"]),
  "doi_in_pool":sum(1 for p in pool if p["doi"]),
  "doi_format_ok_rate":round(sum(1 for p in pool if p["doi"] and DX.match(p["doi"]))/float(max(1,sum(1 for p in pool if p["doi"]))),4)}
 for k in (10,20,50):
  top=cnd[:k]
  if top:mt["P@%d"%k]=round(sum(1 for x in top if x["ref_link"])/float(len(top)),4)
 mt["note"]="P@k uses reference-set linkage as a screening proxy, not a human relevance judgement"
 res["metrics"]=mt
 exm=sum(1 for r in elig if (r["doi"] and any(r["doi"]==p["doi"] for p in pool)) or (r["title"] and any(nt(r["title"])==nt(p["title"]) for p in pool)))
 be=round(exm/float(len(elig)),4) if elig else None
 res["baseline_comparison"]={"same_reference_set":True,"same_pool":True,"baseline_exact_title_doi_only":be,
  "baseline_circular_denominator":1.0 if (pool and elig) else None,"skill_coverage":c,"skill_coverage_after_offline":ca,
  "delta_vs_exact_only":None if (be is None or c is None) else round(c-be,4),
  "misses_baseline":None if not elig else int(round(len(elig)*(1-be))),"misses_skill":nm,
  "note":"recomputed from this case's own data; not the platform whiteboard"}
 wc(out/"hit_matrix.csv",hm,["ref_id","title","year","doi","status","match_tier","match_score","matched_rid","matched_source",
  "matched_query_id","cause_primary","causes_all","evidence_locator","repair"])
 wc(out/"candidates.csv",res["candidates"],["rank","rid","title","authors","year","venue","doi","url","source_db","retrieved_at","query_id","ref_link","relevance_score","relevance_reason"])
 jd(out/"query_log.json",{"queries":res["queries"],"note":"query -> records -> hits as retained in input; no network calls made"})
 jd(out/"supplement_plan.json",res["supplement"])
 (out/"coverage_report.md").write_text(md(res),encoding="utf-8")
 ft=any("unreadable" in str(e.get("error","")) for e in res["errors"])
 s="input_error" if (ft and not case) else "insufficient_evidence" if not refs else "partial" if (not pool or res["errors"]) else "ok"
 res["status"]=s
 if not refs:res["limits"].append("no reference set identified: coverage undefined, only an input inventory is produced")
 if not pool:res["limits"].append("no retrieved records: every eligible reference is a miss with cause C11")
 res["limits"].append("no network: repair specs are not executed, catches are predictions")
 res["uncertainty"].append("coverage is exact only w.r.t. the reference set found in the input; it bounds, not equals, true coverage")
 res["uncertainty"].append("fuzzy 0.62-%.2f items are queued; if all confirmed coverage rises by <=%d"%(a.accept,len(r1)-len(new)))
 res["changes"].append({"stage":"finalize","action":"final result.json written over the partial skeleton","t":round(time.time()-t0,3)})
 fin(res,out,oc,t0)
 log("[skill] status=%s coverage=%s hits=%d/%d misses=%d rounds=%d"%(s,c,nh,len(elig),nm,len(rnds)))
 log("[skill] artifacts -> %s"%out)
 return 0
if __name__=="__main__":
 try:main()
 except SystemExit:pass
 except Exception:
  try:
   p=Path("/app/output");p.mkdir(parents=True,exist_ok=True)
   jd(p/"result.json",{"case_id":None,"status":"partial","skill":SK,"skill_version":V,"errors":[{"stage":"fatal","error":traceback.format_exc()[-1200:]}],
    "degradations":["fatal handler wrote this partial result"],"pending_human":[],"uncertainty":[],"changes":[],"sources":[]})
  except Exception:pass
 sys.exit(0)