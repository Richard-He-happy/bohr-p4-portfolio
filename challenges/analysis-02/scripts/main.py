#!/usr/bin/env python3
"""analysis-02 statistics skill: /input -> /app/output."""
import argparse,csv,io,json,re,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H))
from statsx import *
from statsx import VERSION as ENG
A,CF,NB,MG,MO=.05,.95,2000,12,8
def _l():
 for p in(H.parent/"references"/"messages.json",H/"messages.json"):
  try:return json.loads(p.read_text(encoding="utf-8"))
  except Exception:pass
 return {}
MSG=_l()
CFG=MSG["cfg"];KY=MSG["keys"];TK=KY["tests"];DK=KY["desc"];CK=KY["corr"]
WY=MSG["why"];IT=MSG["interp"];AC=MSG["act"];RP=MSG["rep"];UN=MSG["unc"];ST=MSG["st"];SR=MSG["src"];MAG=MSG["mag"];RU=MSG["rule"]
def f(v,n=3):
 if v is None or(isinstance(v,float) and v!=v):return "NA"
 if isinstance(v,(list,tuple)):return "["+", ".join(f(x,n) for x in v)+"]"
 if v==0:return "0"
 return "%.*f"%(n,v)
def fp(p):return "NA" if p is None else("<0.0001" if p<1e-4 else "%.4f"%p)
def nk(s):return re.sub(r"[^0-9a-z\u4e00-\u9fff]","",str(s).lower())
def js(o):
 if isinstance(o,float):return None if o!=o or o in(1e999,-1e999) else float("%.12g"%o)
 if isinstance(o,dict):return {str(k):js(v) for k,v in o.items()}
 if isinstance(o,list):return [js(v) for v in o]
 return o if isinstance(o,(bool,int,str)) or o is None else str(o)
def wj(p,o):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(js(o),ensure_ascii=False,indent=1),encoding="utf-8")
def wc(p,ks,rows):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("w",encoding="utf-8",newline="") as h:
  w=csv.writer(h);w.writerow(ks)
  for r in rows:w.writerow(["" if r.get(k) is None else r.get(k) for k in ks])
def gv(d,ks,dv=None):
 for k in ks:
  if isinstance(d,dict) and d.get(k) not in(None,"",[],{}):return d[k]
 return dv
def disc(root):
 o={"case":{},"cp":None,"tb":[],"ot":[]}
 r=Path(root);cs=[r/"case.json"] if (r/"case.json").is_file() else[]
 for q in cs:
  try:j=json.loads(q.read_text(encoding="utf-8-sig"))
  except Exception:continue
  if isinstance(j,dict) and j:o["case"],o["cp"]=j,str(q);break
 for q in sorted(r.rglob("*")):
  try:
   if not q.is_file() or q.stat().st_size>6.4e7:continue
   e,lo=q.suffix.lower(),q.name.lower()
   if e in(".csv",".tsv",".tab",".txt",".data",".db",".sqlite",".sqlite3")and"task"not in lo and"readme"not in lo:o["tb"].append(str(q))
   elif e in(".xlsx",".xlsm",".pdf",".png",".jpg",".docx",".pptx",".json",".md",".sql"):o["ot"].append(str(q))
  except Exception:continue
 return o
def sniff(p):
 b=Path(p).read_bytes()[:200000]
 od=("utf-8-sig","utf-8","gb18030","latin-1")
 e="latin-1"
 for c in od:
  try:b.decode(c);e=c;break
  except Exception:pass
 t=b.decode(e,errors="replace");h=t.splitlines()[0] if t else ""
 d=max([",",";","\t","|"],key=lambda c:h.count(c))
 return e,(d if h.count(d) else ","),t
def split(rows):
 rows=[r for r in rows if any(str(c).strip() for c in r)]
 if not rows:return [],[]
 h=[str(c).strip() for c in rows[0]]
 if h and not any(re.search("[A-Za-z\u4e00-\u9fff]",c) for c in h):return ["col%d"%(i+1) for i in range(len(h))],rows
 return h,rows[1:]
def rsql(p):
 c=sqlite3.connect("file:%s?mode=ro"%Path(p).as_posix(),uri=True)
 try:
  nm=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  if not nm:raise ValueError("no table")
  b,sz=nm[0],-1
  for n in nm:
   k=c.execute('SELECT COUNT(*) FROM "%s"'%n.replace('"','""')).fetchone()[0]
   b,sz=(n,k) if k>sz else(b,sz)
  cu=c.execute('SELECT * FROM "%s"'%b.replace('"','""'))
  return {"header":[d[0] for d in cu.description],"rows":[list(r) for r in cu],"enc":"sqlite","delim":"sql","rel":b,"note":""}
 finally:c.close()
def rtab(p):
 e=Path(p).suffix.lower()
 if e in(".db",".sqlite",".sqlite3"):return rsql(p)
 if e in(".xlsx",".xlsm"):raise ValueError(WY["xlsx"])
 en,d,t=sniff(p)
 h,b=split(list(csv.reader(io.StringIO(t),delimiter=d)))
 b=[[r[i] if i<len(r) else "" for i in range(len(h))] for r in b] if h else[]
 return {"header":h,"rows":b,"enc":en,"delim":d,"rel":"file","note":"" if h else WY["noheader"]}
def picktab(tb):
 best,dg=None,[]
 for p in tb:
  try:t=rtab(p)
  except Exception as e:dg.append("%s: %s"%(Path(p).name,e));continue
  if not t.get("header") or not t.get("rows"):continue
  t["src"]=p
  if best is None or len(t["rows"])>len(best["rows"]):best=t
 return(best or{"header":[],"rows":[],"src":None,"error":WY["notable"]}),dg
def prof(h,rows):
 c={}
 for i,n in enumerate(h):
  k=n if n not in c else "%s#%d"%(n,i)
  c[k]=profile(k,[r[i] if i<len(r) else "" for r in rows],{});c[k]["pos"]=i
 return c
def grpof(c,case):
 g=gv(case,["group","group_var","grouping","factor","group_column","class_column"])
 if isinstance(g,str) and g in c:return g,WY["g_decl"],.05
 for n,v in c.items():
  if v["kind"]=="categorical" and 2<=v.get("n_levels",0)<=MG and any(k in nk(n) for k in CFG["gkw"]):return n,WY["g_kw"],.1
 cd=[(1 if v.get("numeric_coded") else 0,n) for n,v in c.items() if v["kind"]=="categorical" and 2<=v.get("n_levels",0)<=MG and(v.get("missing_rate") or 0)<=.5]
 if cd:return sorted(cd)[0][1],WY["g_cat"],.35
 cd=[(v.get("n_levels") or MG,n) for n,v in c.items() if v["kind"]=="numeric" and v.get("int_coded") and not any(b in nk(n) for b in CFG["solo"]) and(v.get("missing_rate") or 0)<=.5]
 return(sorted(cd)[0][1],WY["g_int"]%sorted(cd)[0][0],.6) if cd else(None,WY["g_none"],1.)
def keyof(c,case):
 k=gv(case,["primary_key","primary_keys","keys","key","unique_key"])
 if isinstance(k,str):k=[k]
 if isinstance(k,list) and k and all(any(str(x)==n or str(x)==n.split("#")[0] for n in c) for x in k):return [str(x) for x in k],WY["k_decl"]
 for n,v in c.items():
  if v["kind"]!="empty" and re.search(r"(^id$|_id$|^no$|^key$|编号|序号)",str(n),re.I):return [n],WY["k_name"]
 return [],WY["k_none"]
def fen(vs):
 s=[v for v in vs if v is not None]
 if len(s)<8:return [],None
 q1,q3=quantile(s,.25),quantile(s,.75)
 if q3-q1<=0:return [],None
 lo,hi=q1-1.5*(q3-q1),q3+1.5*(q3-q1)
 return [i for i,v in enumerate(vs) if v is not None and(v<lo or v>hi)],[lo,hi]
def clean(tab,c,case):
 rows,raw=tab["rows"],len(tab["rows"]);iss=[]
 def nt(rule,fld,issue,cnt,rate,rr=None,ex=None):
  d={"rule":rule,"field":fld,"issue":issue,"count":cnt,"rate":rate,"action":RU[rule],"why":WY[rule]}
  if rr:d["rows"]=rr[:200]
  if ex:d.update(ex)
  iss.append(d)
 nc=sum(v["n_cells"] for v in c.values()) or 1;nm=sum(v["n_missing"] for v in c.values())
 nt("M-01","*","missing_cell",nm,nm/nc)
 un={}
 for n,v in c.items():
  if v.get("unit"):un[n]=v["unit"]
  if v["kind"]=="empty":nt("M-03",n,"empty_column",v["n_cells"],1.)
  elif v["n_missing"]:
   nt("M-01",n,"missing",v["n_missing"],v["missing_rate"])
   if(v["missing_rate"] or 0)>.5:nt("M-02",n,"missing_over_50pct",v["n_missing"],v["missing_rate"])
  if v.get("repaired"):nt("N-01",n,"numeric_format_repaired",v["repaired"],v["repaired"]/max(1,v["n_cells"]),[e["row"] for e in v.get("ex") or[]])
  su=v.get("unit_seen") or{}
  if len(su)>1:nt("N-02",n,"mixed_unit",len(su),None,ex={"units":su})
  if v.get("numeric_coded"):nt("C-01",n,"numeric_coded_category",v["n_levels"],None)
  if v["kind"]=="numeric":
   idx,fe=fen(v["values"])
   if idx:nt("O-01",n,"outlier_tukey_1.5iqr",len(idx),len(idx)/max(1,v["n_cells"]),[i+2 for i in idx[:200]],{"fences":fe})
 keys,kw=keyof(c,case);kp=[c[k]["pos"] for k in keys if k in c] if keys else[]
 seen,dup={},[]
 for i,r in enumerate(rows):
  k=tuple(str(r[p]) if p<len(r) else "" for p in kp) if kp else tuple(str(x) for x in r)
  if k in seen:dup.append(i)
  else:seen[k]=i
 if dup:nt("D-01","*","duplicate_key_row" if kp else "duplicate_row",len(dup),len(dup)/max(1,raw),[i+2 for i in dup[:200]])
 keep=[i for i in range(raw) if i not in set(dup)]
 return {"issues":iss,"raw":raw,"kept":len(keep),"dropped":raw-len(keep),"key":keys,"key_why":kw,"units":un,"keep":keep,"rows":[rows[i] for i in keep]}
def sub(c,k):
 v=c["values"];return [v[i] if i<len(v) else None for i in k]
def cmp2(x,y,var,g1,g2,c):
 r={"id":"%s:%s~%s"%(var,g1,g2),"variable":var,"group1":str(g1),"group2":str(g2),"n1":len(x),"n2":len(y),"design":"two_group","unit":c.get(var,{}).get("unit")}
 if len(x)<3 or len(y)<3:
  r.update({"decision":"insufficient","why":WY["n_lt3"]});return r
 k1,k2,lv=dagostino_k2(x),dagostino_k2(y),levene([x,y])
 tt,mw,g=ttest_ind(x,y,CF),mannwhitney(x,y),hedges_g(x,y)
 ok=all((k.get("p_value") if k.get("valid") else 1.)>=A for k in(k1,k2))
 eq=bool(lv.get("valid") and(lv.get("p_value") or 0)>=A)
 r["assumptions"]={"normality":{str(g1):k1.get("p_value"),str(g2):k2.get("p_value")},"levene_p":lv.get("p_value")}
 if not ok and min(len(x),len(y))<30:
  if not mw.get("valid"):
   r.update({"decision":"insufficient","why":mw.get("reason") or WY["no_test"]});return r
  med=lambda s,i:quantile(sorted([q[0] for q in s if q[1]==i]),.5)
  d={"method":mw["method"],"method_id":"mannwhitney","statistic_name":"U","statistic":mw.get("statistic"),"df":"-","p_value":mw.get("p_value"),"why":WY["mw"],"estimate_name":"median1 - median2","estimate":mw.get("estimate"),"estimate_ci":boot_ci([[v,1] for v in x]+[[v,0] for v in y],lambda s:med(s,1)-med(s,0),NB,CF),"effect_name":"rank-biserial r","effect_value":mw.get("rank_biserial"),"effect_ci":None}
 else:
  if not tt.get("valid"):
   r.update({"decision":"insufficient","why":tt.get("reason") or WY["no_test"]});return r
  t=(tt.get("student") if eq else tt.get("welch")) or tt.get("welch") or tt.get("student");g=g or{}
  d={"method":t["method"],"method_id":t["method_id"],"statistic_name":"t","statistic":t["statistic"],"df":t["df"],"p_value":t["p_value"],"why":WY["t_pool"] if eq else WY["t_welch"],"estimate_name":"mean1 - mean2","estimate":tt.get("diff"),"estimate_ci":t.get("estimate_ci"),"effect_name":"Hedges g","effect_value":g.get("value"),"effect_ci":g.get("ci")}
 r.update(d)
 v=r.get("effect_value")
 r["effect_magnitude"]="" if v is None else(MAG["s"] if abs(v)<.2 else MAG["m"] if abs(v)<.5 else MAG["l"] if abs(v)<.8 else MAG["xl"])
 r["decision"]="significant" if(r.get("p_value") is not None and r["p_value"]<A) else "not_significant"
 return r
def cmpk(g,var,c):
 ks=list(g);gs=[g[k] for k in ks];a,kw=anova(gs),kruskal(gs)
 om={"id":"%s|omnibus"%var,"variable":var,"group1":"*","group2":"%d groups"%len(ks),"design":"k_group(%d)"%len(ks),"n1":sum(len(x) for x in gs),"n2":len(gs)}
 if a.get("valid"):
  om.update({"method":a["method"],"method_id":"anova_oneway","statistic_name":"F","statistic":a["statistic"],"df":"%d,%d"%(a["df1"],a["df2"]),"p_value":a["p_value"],"effect_name":"eta^2","effect_value":a["eta_squared"],"why":WY["anova"],"posthoc":WY["ph_t"]})
 else:
  om.update({"method":kw["method"],"method_id":"kruskal","statistic_name":"H","statistic":kw.get("statistic"),"df":kw.get("df"),"p_value":kw.get("p_value"),"effect_name":"epsilon^2","effect_value":kw.get("epsilon_squared"),"why":WY["kw"],"posthoc":WY["ph_mw"]})
 om["decision"]="significant" if(om.get("p_value") is not None and om["p_value"]<A) else "not_significant"
 e=om.get("effect_value")
 om["effect_magnitude"]="" if e is None else(MAG["s"] if abs(e)<.06 else MAG["m"] if abs(e)<.14 else MAG["l"])
 ph=[cmp2(g[ks[0]],g[k],var,ks[0],k,c) for k in ks[1:]]
 for t,adj in zip(ph,adjust_p([t.get("p_value") for t in ph],"holm")):t.update({"p_adj":adj,"adjust_method":"holm","note":WY["ph_note"]%ks[0]})
 return [om]+ph
def ana(c,cl,g,err):
 keep,o=cl["keep"],{"desc":{},"tests":[],"corr":[]}
 nums=[n for n,v in c.items() if v["kind"]=="numeric"]
 for n in nums:
  vs=[v for v in sub(c[n],keep) if v is not None]
  if len(vs)<3:err.append({"stage":"describe","error":"n<3 for %s (%d)"%(n,len(vs))});continue
  d=describe(vs,CF);d.update({"variable":n,"unit":c[n].get("unit")});o["desc"][n]=d
 outs=[n for n in nums if(c[n].get("missing_rate") or 0)<=.5][:MO]
 if g:
  lv={}
  for i,v in enumerate(sub(c[g],keep) if g in c else[]):
   if v not in(None,""):lv.setdefault(str(v),[]).append(i)
  lv=dict(sorted(lv.items(),key=lambda kv:(-len(kv[1]),kv[0]))[:MG])
  if len(lv)<2:err.append({"stage":"group","error":"group %s has <2 usable levels"%g})
  for n in(outs if len(lv)>=2 else[]):
   vals=sub(c[n],keep);cell={}
   for k,idx in lv.items():
    v=[vals[i] for i in idx if i<len(vals) and vals[i] is not None]
    if v:cell[k]=v
   if len(cell)==2:
    p,q=list(cell);o["tests"].append(cmp2(cell[p],cell[q],n,p,q,c))
   elif len(cell)>2:o["tests"]+=cmpk(cell,n,c)
 pr=[]
 for i,x in enumerate(nums):
  for y in nums[i+1:]:
   pa=[(u,v) for u,v in zip(sub(c[x],keep),sub(c[y],keep)) if u is not None and v is not None]
   if len(pa)<5:continue
   r=correlate([q[0] for q in pa],[q[1] for q in pa],CF)
   if r.get("valid"):r.update({"x":x,"y":y,"n":len(pa)});pr.append(r)
 pr.sort(key=lambda r:-abs(r["pearson_r"]));o["corr"]=pr[:20]
 return o
def itp(t):
 tag="%s (%s vs %s)"%(t["variable"],t.get("group1"),t.get("group2"))
 if t.get("p_value") is None:return(IT["no_test"] or "{tag}").format(tag=tag)
 s=IT["head"].format(tag=tag,method=t.get("method"),stat=t.get("statistic_name") or "stat",sv=f(t.get("statistic")),df=t.get("df"),p=fp(t["p_value"]),dec=IT["dec_sig"] if t["p_value"]<A else IT["dec_ns"])
 if t.get("estimate") is not None and not isinstance(t.get("estimate"),list):s+=IT["est"].format(name=t.get("estimate_name"),v=f(t["estimate"]),ci=(IT["ci"].format(lo=f(t["estimate_ci"][0]),hi=f(t["estimate_ci"][1])) if t.get("estimate_ci") else IT["noci"]))
 if t.get("effect_value") is not None:s+=IT["eff"].format(name=t.get("effect_name"),v=f(t["effect_value"]),ci=(IT["ci"].format(lo=f(t["effect_ci"][0]),hi=f(t["effect_ci"][1])) if t.get("effect_ci") else ""),mag=t.get("effect_magnitude") or "")
 if t.get("p_adj") is not None:s+=" "+IT["adj"].format(p=fp(t["p_adj"]))
 return s
G={}
def rep():
 d,an,cl=G["ds"],G["an"],G["cl"];L=[];w=L.append
 w(RP["title"]);w("")
 w(RP["meta"].format(case=d["case_id"],status=d["status"],file=d["file"],rows=d["rows"],cols=d["cols"],enc=d["enc"],sep=d["delim"]))
 w(RP["meta2"].format(raw=cl["raw"],drop=cl["dropped"],kept=cl["kept"]))
 w(RP["meta3"].format(group=d.get("group") or RP["na"],conf=CF,alpha=A,outs=", ".join(d.get("outs") or[]) or RP["na"]))
 w("")
 w(RP["s1"])
 for t in an["tests"]:w("- "+itp(t))
 if not an["tests"] and not an["corr"]:w(RP["s1_empty"])
 w("");w(RP["s4"]);w(RP["s4_note"])
 for n,v in an["desc"].items():w("- "+RP["dline"].format(v=n,n_=v["n"],m=f(v["mean"]),sd=f(v["sd"]),md=f(v["median"]),q1=f(v["q1"]),q3=f(v["q3"]),ci=f(v.get("mean_ci")),u=v.get("unit") or ""))
 w("");w(RP["s3"])
 w("- 规则计数："+"; ".join("%s(%s)=%d"%(i["rule"],i["field"],i["count"]) for i in cl["issues"]))
 w("");w(RP["s5"]);w(RP["ptr"])
 w("");w(RP["s9"])
 for u in G["unc"]:w("- "+u)
 w("");w(RP["s10"])
 for p in G["pend"]:w("- "+p)
 w("");w(RP["s11"]);w(RP["s11_cmd"].format(seed=NB));w(RP["s11_env"].format(py="%d.%d.%d"%sys.version_info[:3],n=G["vf"],nf=G["vff"]))
 return "\n".join(L)+"\n"
CAN=MSG["canon"];DEFK=MSG["cfg"]["defkeys"]
def fil(ct,pay):
 if isinstance(ct,list):ct={str(k):None for k in ct if isinstance(k,str)}
 if not isinstance(ct,dict) or not ct:ct={k:None for k in DEFK}
 o={}
 for k,v in ct.items():
  t=CAN.get(nk(k))
  o[k]=pay[k] if k in pay else(pay[t] if t in pay else({} if isinstance(v,dict) else([] if isinstance(v,(list,tuple)) or v is None else None)))
 return o
def run(i,o):
 t0=datetime.now(timezone.utc);err=[];dg=[];pd=[]
 i,o=Path(i),Path(o)
 try:o.mkdir(parents=True,exist_ok=True)
 except Exception:pass
 wj(o/"result.json",{"case_id":"","status":"partial","status_reason":"partial result written before analysis"})
 ti=disc(i);case=ti["case"]
 ct=gv(case,["output_contract","outputcontract","contract","outputs"],{}) or{}
 cid=str(gv(case,["case_id","caseid","id"],"") or(Path(ti["cp"]).stem if ti.get("cp") else""))
 tab,dg=picktab(ti["tb"])
 ds={"case_id":cid,"file":tab.get("src"),"rows":len(tab.get("rows") or[]),"cols":len(tab.get("header") or[]),"enc":tab.get("enc"),"delim":tab.get("delim")}
 c=prof(tab["header"],tab["rows"]) if tab.get("header") else{}
 for n,v in c.items():
  dv=sorted({x for x in v["values"] if x is not None}) if v["kind"]=="numeric" else[]
  if dv and 2<=len(dv)<=MG and all(abs(x-round(x))<1e-9 for x in dv):v["int_coded"],v["n_levels"]=True,len(dv)
 g,wg,gc=(grpof(c,case) if c else(None,WY["g_none"],1.))
 cl=clean(tab,c,case) if c else{"issues":[],"raw":0,"kept":0,"dropped":0,"key":[],"key_why":"","units":{},"keep":[],"rows":[]}
 cl["cols"]=c
 ds.update({"group":g,"group_why":wg,"outs":[n for n,v in c.items() if v["kind"]=="numeric" and(v.get("missing_rate") or 0)<=.5][:MO]})
 an=ana(c,cl,g,err) if c else{"desc":{},"tests":[],"corr":[]}
 if c and not g:pd.append(AC["low_group"])
 if g and gc>=.35:pd.append((AC["conf_group"] or "%s")%wg)
 if not tab.get("header"):pd.append(AC["no_table"]);err.append({"stage":"read","error":tab.get("error") or "no table"})
 for k in cl["issues"]:
  for rl,kd in(("N-02","unit"),("M-02","highmiss"),("D-01","key")):
   if k["rule"]==rl:pd.append("%s: %s"%(AC[kd],k["field"]))
 if any(p.lower().endswith((".xlsx",".xlsm")) for p in ti["tb"]):dg.append(AC["xlsx"])
 unc=list(UN["list"])
 if cl.get("dropped"):unc.append(UN["dup"]%cl["dropped"])
 if not an["tests"] and not an["corr"]:unc.append(UN["no_inference"])
 src=[{"id":"data","file":ds["file"],"rows":ds["rows"],"columns":list(tab.get("header") or[]),"rules":sorted({k["rule"] for k in cl["issues"]})}]
 st=("ok" if(an["desc"] or an["corr"] or any(t.get("p_value")is not None for t in an["tests"])) else "insufficient_evidence") if tab.get("header") else "input_error"
 TB=CFG["tables"][:2]+CFG["tables"][2:3]*(bool(an["corr"]))+CFG["tables"][3:]
 pay={"case_id":cid,"status":st,"descriptive":an["desc"],"hypothesis_tests":an["tests"],"cleaning":{"issues":cl["issues"],"key":cl["key"],"key_why":cl["key_why"],"rows":{"raw":cl["raw"],"kept":cl["kept"],"dropped":cl["dropped"]},"units":cl["units"]},"interpretation":[itp(t) for t in an["tests"]],"effect_sizes":[{k:t.get(k) for k in("id","effect_name","effect_value","effect_ci","effect_magnitude")} for t in an["tests"]],"confidence_intervals":[{k:t.get(k) for k in("id","estimate_name","estimate","estimate_ci")} for t in an["tests"]],"correlations":an["corr"],"dataset":ds,"tables":TB,"sources":src,"uncertainty":unc,"pending_human":pd,"errors":err,"degradations":dg}
 res=dict(pay,case_id=cid,_ctk=list(ct if isinstance(ct,dict) else{}))
 res.update(fil(ct,pay))
 res.update(dict(errors=err,degradations=dg))
 G.update(ds=dict(ds,status=st),an=an,cl=cl,unc=unc,pend=pd)
 VF={}
 try:
  wc(o/"tables"/"descriptive.csv",["variable"]+DK,list(an["desc"].values()))
  wc(o/"tables"/"tests.csv",TK,an["tests"])
  if an["corr"]:wc(o/"tables"/"correlation.csv",CK,an["corr"])
  h=tab.get("header") or[]
  wc(o/"cleaned.csv",h,[dict(zip(h,r)) for r in cl["rows"]])
  bad=sum(1 for t in an["tests"] if t.get("method_id") in("t_student","t_welch") and len(t.get("estimate_ci") or[])==2 and(t["p_value"]<A)==(t["estimate_ci"][0]<=0<=t["estimate_ci"][1]))
  ck={"n_accounting":cl["kept"]+cl["dropped"]==cl["raw"],"ci_p_consistency":bad==0,"contract_keys_present":all(k in res for k in res["_ctk"])}
  G["vf"],G["vff"]=3,sum(1 for v in ck.values() if not v)
  VF=ck
  (o/"analysis.md").write_text(rep(),encoding="utf-8")
 except Exception as e:
  err.append({"stage":"outputs","error":repr(e)});dg.append("outputs partially written")
 log="case_id=%s status=%s file=%s raw=%d kept=%d dropped=%d errors=%d pending=%d\n"%(cid,st,ds["file"],cl["raw"],cl["kept"],cl["dropped"],len(err),len(pd))
 (o/"run.log").write_text(log,encoding="utf-8")
 res.update({"errors":err,"degradations":dg,"pending_human":pd,"runtime":{"checks":VF,"python":"%d.%d.%d"%sys.version_info[:3],"seed":NB,"finished_utc":datetime.now(timezone.utc).isoformat(timespec="seconds")}})
 wj(o/"result.json",res)
 return res
def main():
 ap=argparse.ArgumentParser(description="analysis-02 statistics skill: clean, describe, test, effect size, CI, interpret.")
 ap.add_argument("--input",default="/input")
 ap.add_argument("--output",default="/app/output")
 a=ap.parse_args()
 try:run(a.input,a.output)
 except Exception as e:
  try:wj(Path(a.output)/"result.json",{"case_id":"","status":"input_error","errors":[{"stage":"fatal","error":repr(e)}],"uncertainty":[UN["fatal"]],"pending_human":[AC["run"]],"sources":[]})
  except Exception:pass
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except SystemExit:raise
 except Exception:sys.exit(0)
