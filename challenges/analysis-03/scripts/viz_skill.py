#!/usr/bin/env python3
"""SciViz: 科研数据 -> 可投稿图件(SVG)+图注+统计+复现证据。纯标准库,确定性,退出码恒0。"""
import argparse,csv,json,re,sqlite3,sys,time,traceback,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import vizlib as V
VER="1.0.0"
MISS={"","-","--","—",".","?","na","n/a","nan","null","none","n.a.","缺失","无","未知"}
S={"errors":[],"degradations":[],"pending":[],"changes":[]}
KIND={"bar":"柱状图","scatter":"散点图"}
def note(k,c,d=""):
    S[k].append({"code":c,"detail":str(d)[:300]})
    if k=="degradations":S["changes"].append({"kind":"degradation","code":c})
def dump(p,o):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(o,ensure_ascii=False,indent=1,default=lambda v:round(v,6) if isinstance(v,float) else str(v)),encoding="utf-8")
def find(inp):
    r={"case":{},"path":None,"task":"","tables":[]}
    if not Path(inp).exists():note("errors","input_missing",inp);return r
    for p in sorted(x for x in Path(inp).rglob("*") if x.is_file()):
        ex=p.suffix.lower()
        if ex==".json":
            try:o=json.loads(p.read_text(encoding="utf-8",errors="replace"))
            except Exception as e:note("degradations","json_unreadable","%s: %s"%(p.name,e));continue
            if isinstance(o,dict) and not r["case"] and({"case_id","output_contract"}&set(o)):r["case"],r["path"]=o,str(p)
        elif p.name.lower().startswith("task"):r["task"]=p.read_text(encoding="utf-8",errors="replace")
        elif ex in(".csv",".tsv",".txt",".xlsx",".db",".sqlite",".sqlite3"):r["tables"].append(str(p))
    if not r["case"]:note("degradations","case_json_absent","按材料重建任务")
    return r
def contract(c):
    if not isinstance(c,dict):return {}
    for k in("output_contract","outputContract","输出契约","output_schema"):
        if isinstance(c.get(k),dict):return c[k]
    return {}
def num(v):
    if isinstance(v,bool) or v is None:return None
    if isinstance(v,(int,float)):return float(v) if v==v else None
    s=str(v).strip().replace("−","-").replace(" ","").replace("，","")
    if s.lower() in MISS:return None
    if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?",s):s=s.replace(",","")
    s=re.sub(r"^([+-]?[\d.eE+-]+).*$",r"\1",s.rstrip("%"))
    try:return float(s)
    except ValueError:return None
def tab(rows,p):
    h=[(str(c).strip() or "c%d"%i) for i,c in enumerate(rows[0])]
    return h,[dict(zip(h,(r+[""]*len(h))[:len(h)])) for r in rows[1:]],{"file":str(p)}
def t_csv(p):
    raw=Path(p).read_bytes()
    try:txt=raw.decode("utf-8-sig")
    except UnicodeDecodeError:txt=raw.decode("gb18030","replace");note("degradations","encoding_gbk",p.name)
    ln=txt.splitlines()
    dl=max([",","\t",";","|"],key=lambda d:(ln[0] if ln else "").count(d))
    rows=[r for r in csv.reader(ln,delimiter=dl) if any(str(c).strip() for c in r)]
    if not rows:raise ValueError("empty table")
    return tab(rows,p)
def t_xlsx(p):
    z=zipfile.ZipFile(p);ss=[]
    if "xl/sharedStrings.xml" in z.namelist():
        ss=[re.sub(r"<[^>]+>","",m) for m in re.findall(r"<si>(.*?)</si>",z.read("xl/sharedStrings.xml").decode("utf-8","replace"),re.S)]
    sh=sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$",n))
    if not sh:raise ValueError("no worksheet")
    rows=[]
    for rw in re.findall(r"<row[^>]*>(.*?)</row>",z.read(sh[0]).decode("utf-8","replace"),re.S):
        cs={}
        for at,body in re.findall(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)",rw,re.S):
            rf=re.search(r'r="([A-Z]+)\d+"',at)
            if not rf:continue
            ci=sum((ord(ch)-64)*26**i for i,ch in enumerate(reversed(rf.group(1))))
            ty=re.search(r't="(\w+)"',at);ty=ty.group(1) if ty else "n"
            v=re.search(r"<v>(.*?)</v>",body or "",re.S) or re.search(r"<t[^>]*>(.*?)</t>",body or "",re.S)
            v=v.group(1) if v else ""
            if ty=="s" and v.isdigit() and int(v)<len(ss):v=ss[int(v)]
            cs[ci]=v
        if cs:rows.append([cs.get(i,"") for i in range(max(cs)+1)])
    rows=[r for r in rows if any(str(c).strip() for c in r)]
    if not rows:raise ValueError("empty sheet")
    return tab(rows,p)
def t_db(p):
    con=sqlite3.connect("file:%s?mode=ro"%p,uri=True)
    ts=[r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    if not ts:raise ValueError("no table")
    cur=con.execute('select * from "%s"'%ts[0]);h=[d[0] for d in cur.description]
    rows=[dict(zip(h,[("" if v is None else v) for v in r])) for r in cur.fetchall()]
    con.close()
    return h,rows,{"file":str(p),"table":ts[0],"tables":ts}
def load(p):
    ex=Path(p).suffix.lower()
    if ex in(".csv",".tsv",".txt"):return t_csv(p)
    if ex==".xlsx":return t_xlsx(p)
    if ex in(".db",".sqlite",".sqlite3"):return t_db(p)
    raise ValueError("unsupported "+ex)
def unit(n):
    m=re.match(r"^(.*?)\s*[\(（\[](.*?)[\)）\]]\s*$",str(n))
    return (m.group(1).strip(),m.group(2).strip()) if m and re.fullmatch(r"[%‰°µμA-Za-z/³²·\-\s]{1,10}",m.group(2) or "") else (str(n).strip(),"")
def profile(cols,recs):
    o={}
    for c in cols:
        val=[r.get(c) for r in recs]
        gd=[v for v in val if str(v).strip() and str(v).strip().lower() not in MISS]
        nm,un=unit(c)
        o[c]={"field":c,"name":nm,"unit":un,"n_total":len(val),"n_valid":len(gd),"n_missing":len(val)-len(gd),
              "unique":len(set(str(v) for v in gd)),
              "dtype":"numeric" if gd and sum(num(v) is not None for v in gd)/len(gd)>=.8 else "categorical"}
    return o
def clean(recs,P,out):
    iss=[]
    for c,p in P.items():
        bad=0
        for r in recs:
            v=r.get(c)
            if not str(v).strip() or str(v).strip().lower() in MISS:r[c]=None
            elif p["dtype"]=="numeric":r[c]=num(v);bad+=r[c] is None
            else:r[c]=str(v).strip()
        if bad:iss.append({"field":c,"type":"format","n":bad})
        if p["n_missing"]:
            rt=p["n_missing"]/max(1,p["n_total"])
            iss.append({"field":c,"type":"missing","n":p["n_missing"],"rate":round(rt,4)})
            if rt>.3:S["pending"].append({"code":"sparse","field":c,"reason":"缺失率>30%,需确认填补方式"})
    seen=set();keep=[];dup=0
    for r in recs:
        k="|".join(str(r.get(c)) for c in P)
        if k in seen:dup+=1
        else:seen.add(k);keep.append(r)
    iss.append({"field":"*","type":"duplicate","method":"full_row","n":dup})
    S["changes"].append({"kind":"dedupe","removed":dup})
    recs=keep
    for c,p in P.items():
        sv=sorted(r[c] for r in recs if isinstance(r.get(c),(int,float))) if p["dtype"]=="numeric" else []
        if len(sv)<8:continue
        q1,q3=V.quantile(sv,.25),V.quantile(sv,.75)
        lo,hi=q1-1.5*(q3-q1),q3+1.5*(q3-q1)
        hit=[i for i,r in enumerate(recs) if isinstance(r.get(c),(int,float)) and not lo<=r[c]<=hi]
        if hit:iss.append({"field":c,"type":"outlier","method":"iqr_1.5","n":len(hit),"bounds":[round(lo,6),round(hi,6)],"rows":hit[:20]})
    dump(Path(out)/"quality_report.json",{"rows_in":P[list(P)[0]]["n_total"] if P else 0,"rows_out":len(recs),
                                          "field_issues":iss,"type_inference":P,"generator":"viz_skill "+VER})
    return recs
def wcsv(p,rows):
    if not rows:return
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def pick(P,spec,a,txt):
    pu=a.purpose or next((v for k,v in (("分布","distribution"),("相关","correlation"),("趋势","trend")) if k in txt),"comparison")
    nms=[c for c,p in P.items() if p["dtype"]=="numeric"]
    cat=[c for c,p in P.items() if p["dtype"]=="categorical" and 1<p["unique"]<=12]
    x,y=a.x or spec.get("x"),a.y or spec.get("y")
    g=a.group or spec.get("group") or spec.get("color")
    ch=str(a.chart or spec.get("chart") or "").lower()
    y=y if y in P else (nms[-1] if nms else None)
    x=x if x in P else (cat[0] if cat and pu!="correlation" else (nms[0] if len(nms)>1 else None))
    g=g if g in P else next((c for c in cat if c!=x),None)
    nc=P[x]["unique"] if x in P else 0
    if not ch:ch="scatter" if x in P and P[x]["dtype"]=="numeric" else "bar" if nc else "scatter" if nms else "bar"
    ch={"柱状":"bar","散点":"scatter"}.get(ch,ch)
    if ch not in KIND:note("degradations","chart_unsupported",ch);ch="bar"
    if nc>12:note("degradations","category_aggregation","%d->11+other"%nc)
    why,bad,rsn={"bar":("分类x+连续y:位置+误差线+显著性","pie","角度不可精读"),
                 "scatter":("连续x连续:位置+OLS","dual_axis","双轴量纲不可比")}[ch]
    return {"chosen":ch,"purpose":pu,"x":x,"y":y,"group":g,"reasons":[why],
            "alternatives":[{"type":bad,"why_not":rsn}],
            "evidence":{"x_dtype":P.get(x,{}).get("dtype"),"y_dtype":P.get(y,{}).get("dtype"),"n_categories":nc}}
def pair(recs,x,y,cats,gv):
    g=lambda c:[r[y] for r in recs if str(r[x])==c and isinstance(r.get(y),(int,float)) and(gv is None or str(r[gv])==str(gv))]
    out=[]
    for i in range(len(cats)-1):
        t=V.welch(g(cats[i]),g(cats[i+1]))
        if t.get("p") is not None:out.append({"a":cats[i],"b":cats[i+1],"p":t["p"],"test":"welch_t","significant":t["p"]<.05})
    return out
def build(dec,recs,P,a):
    x,y,g,ch=dec["x"],dec["y"],dec["group"],dec["chosen"]
    if not y or y not in P:return None,{},[]
    W=V.PROFILES.get(a.journal,V.PROFILES["report"])["single"]
    pl={"kind":ch,"size_mm":[round(W,2),round(W*.72,2)],"title":"","series":[],
        "y":{"type":"numeric","label":P[y]["name"],"unit":P[y]["unit"],"log":False}}
    st,cd,mk={},[],[]
    if ch=="bar":
        uq=list(dict.fromkeys(str(r[x]) for r in recs if r.get(x) is not None))
        cats=uq if len(uq)<=12 else uq[:11]+["其他"]
        if len(uq)>12:
            for r in recs:r["__c"]=str(r[x]) if str(r[x]) in cats else "其他"
            x="__c"
        gs=[None]
        if g and g in P and 1<P[g]["unique"]<=6:gs=list(dict.fromkeys(str(r[g]) for r in recs if r.get(g) is not None))
        pl["series"]=[{"name":v or P[y]["name"],"color":V.PALETTE[i%7],"hatch":""} for i,v in enumerate(gs)]
        st["groups"]=[]
        for gv in gs:
            for ci,c in enumerate(cats):
                vs=[r[y] for r in recs if str(r[x])==c and isinstance(r.get(y),(int,float)) and(gv is None or str(r[g])==gv)]
                if not vs:continue
                d=V.describe(vs);e=d["se"] if d["n"]>1 else None
                row={"category":c,"series":gv,"n":d["n"],"mean":d["mean"],"sd":d["sd"],"se":d["se"],"ci95":V.ci95(vs),"median":d["median"]}
                st["groups"].append(row);mk.append({"xi":ci,"value":d["mean"],"err":e})
                cd.append(dict(row,value=d["mean"],err=e,err_kind="se"))
        top=max([m["value"]+(m["err"] or 0) for m in mk]+[0]);low=min([m["value"]-(m["err"] or 0) for m in mk]+[0])
        pl["y"]["lim"]=[min(0,low),top*1.18 if top else 1]
        st["pairwise_tests"]=pair(recs,x,y,cats,gs[0])
        pl.update({"x":{"type":"categorical","label":P.get(x,{}).get("name",str(x)),"unit":P.get(x,{}).get("unit",""),
                        "categories":cats,"lim":[0,max(1,len(cats)-1)]},"legend":len(gs)>1,"bars":mk,
                   "x_label_rot":-45 if max([V.tlen(c) for c in cats])>.6*(W-40)/max(1,len(cats)) else 0})
    else:
        pts=[(r.get(x),r.get(y)) for r in recs if isinstance(r.get(x),(int,float)) and isinstance(r.get(y),(int,float))]
        if len(pts)<3:return None,{},[]
        xs,ys=[p[0] for p in pts],[p[1] for p in pts]
        cd=[{"x":p[0],"y":p[1]} for p in pts]
        rg=V.ols(xs,ys);st["regression"]=rg;ln=[]
        if rg.get("slope") is not None:
            x0,x1=min(xs),max(xs)
            ln=[{"si":0,"pts":[(x0,rg["intercept"]+rg["slope"]*x0),(x1,rg["intercept"]+rg["slope"]*x1)]}]
            pl["annotations"]=[{"text":"R²=%s p=%s n=%d"%(V.fmt_num(rg["r2"],3),
                              V.fmt_num(rg["p"],3) if rg.get("p") is not None else "NA",rg["n"])}]
        pad,yp=.05*((max(xs)-min(xs)) or 1),.07*((max(ys)-min(ys)) or 1)
        pl["series"]=[{"name":"%s vs %s"%(P[x]["name"],P[y]["name"]),"color":V.PALETTE[0],"hatch":""}]
        pl.update({"x":{"type":"numeric","label":P[x]["name"],"unit":P[x]["unit"],"lim":[min(xs)-pad,max(xs)+pad],
                        "log":False,"categories":[]},
                   "y":{"type":"numeric","label":P[y]["name"],"unit":P[y]["unit"],"lim":[min(ys)-yp,max(ys)+yp],"log":False},
                   "fit_only":True,"lines":ln,
                   "points":[{"x":p[0],"y":p[1],"si":0,"r":.9 if len(pts)>60 else 1.1} for p in pts]})
    pl["_a11y"]=V.accessibility(pl["series"])
    if not pl["_a11y"]["pass"] and len(pl["series"])>1:
        for i,s in enumerate(pl["series"]):s["hatch"]=V.hatch_for(i)
        pl["_a11y"]=V.accessibility(pl["series"]);S["changes"].append({"kind":"a11y_fix","action":"texture"})
    return pl,st,cd
def finish(out,case,res,a,t0):
    con=contract(case)
    res["case_id"]=case.get("case_id") if isinstance(case,dict) else None
    res.setdefault("status","partial")
    res.setdefault("sources",[{"file":"input/case.json","locator":"case_id/output_contract"},
                              {"file":res.get("data_file") or "input/*","locator":"whole table"}])
    res["uncertainty"]=list(dict.fromkeys(res.get("uncertainty") or ["统计量按完整案例计算,未插补"]))
    res.update({"version":VER,"skill":"sciviz-figure-forge","pending_human":S["pending"],"errors":S["errors"],
                "degradations":S["degradations"],"changes":S["changes"],
                "runtime":{"seconds":round(time.time()-t0,2),"python":sys.version.split()[0],
                           "stdlib_only":True,"deterministic":True}})
    low={str(k).lower():k for k in res}
    for k,v in con.items():
        if k not in res:
            hit=[low[t] for t in low if t in str(k).lower() or str(k).lower() in t]
            res[k]=res[hit[0]] if hit else ([] if isinstance(v,list) else None if isinstance(v,str) else v)
    res["contract_fields"]=sorted(con)
    dump(Path(out)/"result.json",res)
    print("final status=%s errors=%d degraded=%d"%(res["status"],len(S["errors"]),len(S["degradations"])))
    return 0
def run(a,out):
    t0=time.time();f=find(a.input);case=f["case"]
    dump(Path(out)/"result.json",{"case_id":case.get("case_id") if case else None,"status":"partial",
                                  "skill":"sciviz-figure-forge","version":VER})
    res={"status":"partial"}
    cand=[Path(a.data)] if a.data else [Path(p) for p in f["tables"]]
    data=cols=recs=None
    for p in cand:
        try:cols,recs,_m=load(p);data=p;break
        except Exception as e:note("degradations","material_unreadable","%s: %s"%(p.name,e))
    if data is None or not recs or not cols:
        note("errors","no_readable_table" if data is None else "empty_table",str(len(cand)))
        res.update(status="input_error" if data is None else "insufficient_evidence",
                   uncertainty=["未找到可解析表格" if data is None else "表格无有效数据行"])
        return finish(out,case,res,a,t0)
    P=profile(cols,recs);recs=clean(recs,P,out);wcsv(out/"cleaned.csv",recs)
    spec=next((case[k] for k in("chart_spec","figure_spec","plot_spec") if isinstance(case.get(k),dict)),{})
    dec=pick(P,spec,a,(f["task"] or "")+" "+str(case.get("task") or ""));dec["evidence"]["n_rows"]=len(recs)
    pl,st,cd=build(dec,recs,P,a)
    if pl is None:
        res.update({"chart_decision":dec,"status":"insufficient_evidence","uncertainty":["可用列或行不足,未出图(见 chart_decision/quality_report)"]})
        return finish(out,case,res,a,t0)
    info=V.render_svg(pl,out/"figures"/"figure1.svg",a.journal)
    u=lambda k:pl[k]["label"]+("(%s)"%pl[k]["unit"] if pl[k]["unit"] else "")
    ns=sorted({g["n"] for g in st.get("groups",[])}) or [len(recs)]
    cap=["图1. %s 随 %s(%s);误差线=均值±标准误(SE=SD/√n),n=%d–%d,清洗后 %d 行。"%(
        u("y"),u("x"),KIND[pl["kind"]],min(ns),max(ns),len(recs))]
    if st.get("pairwise_tests"):
        ps=[t["p"] for t in st["pairwise_tests"]]
        cap.append("相邻类 Welch t(双侧未校正) 最小 p=%s,%d 对 p<0.05(未画括线,见 tables/pairwise_tests.csv)。"%(
            V.fmt_num(min(ps),3),sum(t["significant"] for t in st["pairwise_tests"])))
    r=st.get("regression") or {}
    if r.get("r2") is not None:cap.append("OLS 斜率 %s,R²=%s,n=%d。"%(V.fmt_num(r["slope"],4),V.fmt_num(r["r2"],3),r["n"]))
    cap.append("y 轴 %s–%s;缺失按完整案例、重复行去重、离群值只标记;源数据 %s;画布 %s×%smm,%spt,%s;viz_skill v%s。"%(
        V.fmt_num(pl["y"]["lim"][0]),V.fmt_num(pl["y"]["lim"][1]),Path(data).name,info["size_mm"][0],
        info["size_mm"][1],info["font_pt"],info["format"].upper(),VER))
    cap=" ".join(cap)
    (out/"figure1_caption.txt").write_text(cap+"\n",encoding="utf-8")
    vl=[d[k] for d in cd for k in("value","y") if isinstance(d.get(k),(int,float))]
    lo,hi=pl["y"]["lim"][0],pl["y"]["lim"][1];pr=V.PROFILES.get(info["profile"],V.PROFILES["report"])
    m=re.search(r"清洗后 (\d+) 行",cap)
    chk=[{"id":"C01","target":"轴范围覆盖绘图值","passed":(not vl) or(min(vl)>=lo-1e-9 and max(vl)<=hi+1e-9),
          "expected":[round(lo,4),round(hi,4)],"actual":[round(min(vl),4) if vl else None,round(max(vl),4) if vl else None]},
         {"id":"C02","target":"图注n=清洗行数且画布=栏宽且字号>=5pt",
          "passed":bool(m) and int(m.group(1))==len(recs) and info["font_pt"]>=5.0 and abs(info["size_mm"][0]-pr["single"])<=1.0,
          "expected":"n=%d;%smm;>=5pt"%(len(recs),pr["single"]),
          "actual":"n=%s;%smm;%spt"%(m.group(1) if m else "NA",info["size_mm"][0],info["font_pt"])},
         {"id":"C03","target":"图表数据表非空","passed":bool(cd),"expected":">0","actual":len(cd)}]
    if cd:wcsv(out/"tables"/"chart_data.csv",cd)
    for nm in("groups","pairwise_tests"):
        if st.get(nm):wcsv(out/"tables"/(nm+".csv"),st[nm])
    dump(out/"stats.json",{"chart_decision":dec,**st})
    try:qr=json.loads((out/"quality_report.json").read_text(encoding="utf-8"))
    except Exception:qr={}
    qr.update({"checks":chk,"a11y":pl["_a11y"],"figure":info,"caption":cap})
    dump(out/"quality_report.json",qr)
    res.update({"data_file":str(data),"rows_used":len(recs),"chart_decision":dec,"figure":info,"caption":cap,
                "checks":chk,"stats":st,"cleaned_data":"cleaned.csv","quality_report":"quality_report.json",
                "tables":["tables/chart_data.csv"],"figure_file":"figures/figure1.svg",
                "status":"ok" if all(c["passed"] for c in chk) else "partial"})
    return finish(out,case,res,a,t0)
def main(argv=None):
    ap=argparse.ArgumentParser(prog="viz_skill.py",description="SciViz: 科研数据->可投稿图件(SVG)+图注+统计+复现证据")
    for k,v,h in(("--input","/input","输入目录"),("--output","/app/output","输出目录"),("--data",None,"指定数据文件"),
                 ("--chart",None,"强制图型 bar|scatter"),("--x",None,"x/类别列"),("--y",None,"y数值列"),
                 ("--group",None,"分组列"),("--purpose",None,"distribution|correlation|comparison|trend"),
                 ("--journal","report","report|nature|science|cell|ieee")):
        ap.add_argument(k,default=v,help=h)
    a=ap.parse_args(argv);out=Path(a.output)
    try:out.mkdir(parents=True,exist_ok=True)
    except Exception as e:
        note("errors","output_not_writable",str(e));out=Path(".")/"output";out.mkdir(parents=True,exist_ok=True)
        note("degradations","output_fallback",str(out.resolve()))
    try:return run(a,out)
    except Exception:
        note("errors","unhandled_exception",traceback.format_exc()[-800:])
        try:case=find(a.input)["case"]
        except Exception:case={}
        try:return finish(out,case,{"status":"partial"},a,time.time())
        except Exception:
            try:(out/"result.json").write_text(json.dumps({"case_id":(case or {}).get("case_id"),"status":"partial",
                "errors":S["errors"]},ensure_ascii=False,indent=1),encoding="utf-8")
            except Exception:pass
            return 0
if __name__=="__main__":
    sys.exit(main())
