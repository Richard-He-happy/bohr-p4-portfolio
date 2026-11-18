#!/usr/bin/env python3
"""library-annotation-sediment: inventory + version chains + annotation anchors + notes + index. Exit 0."""
import argparse,csv,hashlib,json,os,re,sys,time
from pathlib import Path
import docext as D
V="1.0.0";T="library-annotation-sediment"
HIL={"Highlight","Underline","Squiggly","StrikeOut"}
TM={"Ink":"ink","Text":"margin_note","FreeText":"margin_text"}
CUE=re.compile(r"(?i)(\?|\bwhether\b)|(\bwe (?:propose|present)\b|\bmethod\b)|(\bwe (?:find|show|observe)\b|\bresults?\b)|(\blimitation|\bcaveat\b)|(\bcode\b|\bdataset\b|\bavailable\b)")
VT=re.compile(r"(?i)(?:^|[_\-.\s])(?:v|ver|version|rev)\.?\s*([0-9]{1,3})(?![0-9])")
ZH=[("最终版","final"),("修订版","revised")]
STOP=set("the and for with that this from are was has not but its their our we can also into than then such more using used use".split())
DOI=re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]{4,}")
REF=re.compile(r"[\w ./\\-]{3,120}\.(?:pdf|docx?|xlsx?|csv|md|txt|bib|ris)",re.I)
CUEV=re.compile(r"(?i)supersed|obsolet|replac|older|newer|取代|替换|作废")
KEYS="case_id status inputs summary inventory duplicates version_chain annotations notes links search recovery sources artifacts uncertainty pending_human errors degradations changes skipped runtime contract_fill".split()
def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as fh:
  for b in iter(lambda:fh.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def jl(p):
 try: return json.loads(Path(p).read_text(encoding="utf-8",errors="replace"))
 except Exception: return None
def wj(p,o): Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=1,default=str),encoding="utf-8")
def rel(p,r):
 try: return str(Path(p).resolve().relative_to(Path(r).resolve()))
 except Exception: return str(p)
def toks(s): return [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}",(s or "").lower()) if w not in STOP]
def log(c,op,t,st,d=""): c["log"].append({"ts":now(),"op":op,"target":t,"status":st,"detail":d})
def err(c,st,p,e): c["errors"].append({"stage":st,"path":p,"error":e})
def pend(c,i,r,w=""): c["pending_human"].append({"item":i,"reason":r,"action":w})
def skp(c,p,r): c["skipped"].append({"path":p,"reason":r})
def mv(m,k):
 v=m.get(k)
 return v.get("value") if isinstance(v,dict) else v
def txt(p,n=400000):
 try: return Path(p).read_text(encoding="utf-8",errors="replace")[:n]
 except OSError: return ""
def fam(s):
 s=VT.sub(" ",s.lower());s=re.sub(r"\b(draft|preprint|accepted|published|final|copy)\b"," ",s)
 for zh,_ in ZH: s=s.replace(zh," ")
 return re.sub(r"[\s_\-.]+"," ",re.sub(r"\((?:[0-9]{1,2}|copy)\)"," ",s)).strip()
def vrank(s):
 s=s.lower();r,tags=None,[]
 for m in VT.finditer(s): tags.append(m.group(0).strip());r=max(r or 0,100+int(m.group(1)))
 for zh,en in ZH:
  if zh in s: tags.append(en);r=max(r or 0,7)
 d=re.findall(r"(20\d{2})[-_.]?([01]\d)[-_.]?([0-3]\d)",s)
 if d: tags.append("-".join(d[0]));r=max(r or 0,1000+int("".join(d[0])))
 return tags,r
def spec(case):
 for k,v in (case or {}).items():
  if re.sub(r"[^a-z]","",k.lower()) in("outputcontract","contract","outputschema"): return v
def pick(k,c):
 k=re.sub(r"[^a-z0-9]","",(k or "").lower())
 if "schema" in k: return "1.0"
 if "duplicategroup" in k: return c["duplicates"].get("groups",[])
 if "versionchain" in k: return c["version_chain"].get("chains",[])
 if "link" in k or "relat" in k: return c["links"]
 if "case" in k: return c["case_id"]
 if "status" in k: return c["status"]
 cn=any(t in k for t in("count","total","num"))
 for t,n in (("dup","duplicates"),("annot","annotations"),("note","notes"),("search","search"),("kow","search"),("invent","inventory"),("file","inventory"),("summ","summary"),("artif","artifacts"),("pend","pending_human"),("error","errors")):
  if t in k:
   v=c.get(n)
   if n=="inventory": return len(v) if cn else [f["path"] for f in v]
   if n=="duplicates": return len(v.get("groups",[])) if cn else v
   return len(v) if cn and isinstance(v,list) else v
 return c["artifacts"] if("path" in k or "dir" in k) else None
def fill(s,c,p="",rep=None):
 rep={} if rep is None else rep
 lp=p.split(".")[-1]
 if isinstance(s,dict):
  if s and all(not isinstance(v,(dict,list)) for v in s.values()) and any(x in s for x in("type","description","required","value")):
   v=pick(lp,c);rep[p]=v is not None;return dict(s,value=v)
  return {k:fill(v,c,(p+"."+k).strip("."),rep) for k,v in s.items()}
 v=pick(lp,c);rep[p]=v is not None
 if isinstance(s,list): return v if isinstance(v,list) and v else s
 return v if v is not None else s
def result(c):
 c["runtime"].update(finished=now(),seconds=round(time.time()-c["_t0"],2),python=sys.version.split()[0],script_version=V)
 c["status"]="input_error" if(c["_fatal"] and not c["inventory"]) else "insufficient_evidence" if not c["inventory"] else "partial" if(c["errors"] or c["pending_human"]) else "ok"
 r={"tool":T,"version":V}
 r.update(c["contract"] or {});r.update({k:c[k] for k in KEYS})
 if c["contract_raw"] is not None: r["output_contract"]=c["contract_raw"]
 return r
def annots(f,d,leg):
 out=[]
 for pg in (d["pdf"].pages if d.get("pdf") else []):
  for i,an in enumerate(pg["annots"]):
   st=an["subtype"];a=d["pdf"].anchor(pg,an) if st in HIL else d["pdf"].near_line(pg,an["rect"])
   out.append({"annotation_id":"%s-p%d-a%d"%(f["id"],pg["index"],i+1),"file":f["path"],"page":pg["index"],"type":TM.get(st,(st or "unknown").lower()),
    "color":an["color"],"color_semantics":leg.get((an["color"] or "").upper()),"author":an["author"],"created":an["created"],
    "comment":an["contents"],"quote":a["quote"],"precision":a.get("precision"),
    "locator":{"page":pg["index"],"char_start":a.get("char_start"),"char_end":a.get("char_end"),"rect":an["rect"]},
    "flags":[] if a["quote"] else ["anchor_unresolved"]})
 for cd in (d["docx"]["comments"] if d.get("docx") else []):
  out.append({"annotation_id":"%s-c%d"%(f["id"],cd["id"]),"file":f["path"],"page":None,"type":"word_comment","color":None,"color_semantics":None,
   "author":cd["author"],"created":cd["created"],"comment":cd["contents"],"quote":cd["anchor"]["quote"],"precision":cd["anchor"]["precision"],
   "locator":{"char_start":cd["anchor"]["char_start"],"char_end":cd["anchor"]["char_end"]},
   "flags":[] if cd["anchor"]["quote"] else ["anchor_unresolved"]})
 return out
def mknotes(anns):
 out,seen=[],{}
 for a in anns:
  b=(a.get("quote") or "")+"|"+(a.get("comment") or "")
  if not b.strip("|"): continue
  if b in seen: seen[b].append(a["annotation_id"]);continue
  seen[b]=[a["annotation_id"]];k="unspecified";src=a.get("quote") or a.get("comment") or ""
  for i,n in enumerate(("question","method","result","limitation","reusable")):
   m=CUE.search(src)
   if m and m.group(i+1): k=n;break
  out.append({"note_id":"N%04d"%(len(out)+1),"kind":k,"claim":a.get("comment") or a.get("quote"),
   "evidence":{"file":a["file"],"page":a.get("page"),"quote":a.get("quote"),"precision":a.get("precision"),"locator":a.get("locator"),"annotation_id":a["annotation_id"]},
   "annotation_ids":[a["annotation_id"]],"type":a["type"],"color":a.get("color"),"color_semantics":a.get("color_semantics"),
   "verification":{"quote_in_source":None},"flags":list(a.get("flags") or [])})
 return out
def hit(ix,terms,cap=5):
 sc={}
 for t in set(terms):
  for nid in ix.get(t,[]): sc[nid]=sc.get(nid,0)+1
 return sorted(sc.items(),key=lambda x:(-x[1],x[0]))[:cap]
def scan(c,inp):
 files,docs,admin=[],{},[]
 for f in D.walk(inp):
  rp=rel(f,inp)
  if rp.startswith("."): continue
  e={"id":"F%03d"%(len(files)+1),"path":rp,"sha256":None,"size":None,"status":"ok","notes":[],"meta":{}}
  try:
   st=f.stat();e["size"]=st.st_size;e["mtime"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime(st.st_mtime))
   e["mode"]=oct(st.st_mode&0o777);e["readable"]=os.access(f,os.R_OK)
  except OSError as ex: e["status"]="stat_error";e["readable"]=False;e["notes"].append("stat");err(c,"stat",rp,type(ex).__name__)
  if not e.get("readable",True): e["notes"].append("not_readable")
  try: e["sha256"]=sha(f)
  except OSError: e["notes"].append("hash_failed")
  files.append(e)
  kind=D.sniff(f)[0];e["type"]=kind
  if not e["readable"]:
   skp(c,rp,"permission_denied");pend(c,rp,"permission_denied","read permission needed; size+hash only")
   e["meta"]["title"]={"value":Path(rp).stem,"source":"filename"};continue
  try:
   if kind=="pdf":
    p=D.PDF(f);docs[rp]={"pdf":p};e["pages"]=len(p.pages)
    e["text_layer"]=any(x["text"].strip() for x in p.pages) if p.pages else False
    if p.encrypted: e["notes"].append("encrypted");skp(c,rp,"encrypted_pdf")
    if p.pages and not e["text_layer"]:
     e["notes"].append("scanned_no_text_layer");pend(c,rp,"scan_without_text_layer","OCR layer needed; anchors unresolved")
    for k,v in (p.meta or {}).items():
     kk=str(k).lower()
     if kk in("title","author","subject","keywords","creationdate","moddate"): e["meta"][kk]={"value":str(v),"source":"pdf_info"}
     if kk=="creationdate":
      m=re.search(r"(19|20)\d{2}",str(v))
      if m: e["meta"]["year"]={"value":m.group(0),"source":"pdf_info_creationdate"}
    for er in p.errors: err(c,"pdf",rp,er)
   elif kind=="docx":
    d=D.docx(f);docs[rp]={"docx":d};e["text_layer"]=bool(d["text"].strip())
    for k in("title","author","created","modified"):
     if (d.get("core") or {}).get(k): e["meta"][k]={"value":d["core"][k],"source":"docx_core"}
   elif kind=="xlsx": docs[rp]={"xlsx":D.xlsx(f)};e["text_layer"]=True
   elif kind=="html": docs[rp]={"html":D.html(f)};e["text_layer"]=True
   elif kind in("csv","text"): docs[rp]={"text":txt(f)};e["text_layer"]=True
   else: docs[rp]={}
  except Exception as ex:
   e["status"]="parse_error";e["notes"].append("parse");err(c,"parse",rp,"%s: %s"%(type(ex).__name__,ex))
  if not e["meta"]: e["meta"]["title"]={"value":Path(rp).stem,"source":"filename"}
  if not(e["meta"].get("doi") or {}).get("value"):
   m=DOI.search(json.dumps(docs.get(rp,{}),ensure_ascii=False,default=str)[:200000])
   if m: e["meta"]["doi"]={"value":m.group(0),"source":"content_doi_regex"}
  if not(e["meta"].get("year") or {}).get("value"):
   m=re.search(r"\b(19|20)\d{2}\b",Path(rp).stem)
   if m: e["meta"]["year"]={"value":m.group(0),"source":"filename_regex"}
  if re.search(r"(?i)admin|version|meta|readme|log|manifest|index",rp):
   t=txt(f) if Path(rp).suffix.lower() in(".md",".txt",".csv",".json","") else ""
   if t: admin.append({"file":rp,"chars":len(t),"quote":t[:1500]})
 return files,docs,admin
def pipeline(c,inp):
 files,docs,admin=scan(c,inp);c["inventory"]=files
 leg={}
 for a in admin:
  for m in re.finditer(r"(?i)(#[0-9A-F]{6})\s*[=:：]?\s*([^\n,;]{2,40})",a["quote"]): leg[m.group(1).upper()]=m.group(2).strip()
 c["color_legend"]=leg
 dg={}
 for f in files:
  if f.get("sha256"): dg.setdefault(f["sha256"],[]).append(f)
 groups=[]
 for h,fs in dg.items():
  if len(fs)>1:
   can=sorted(fs,key=lambda x:(len(re.sub(r"\(1\)|copy","",x["path"])),x["path"]))[0]
   for f in fs: f["duplicate_of"]=None if f is can else can["path"]
   groups.append({"sha256":h,"files":sorted(x["path"] for x in fs),"kind":"byte_identical","canonical":can["path"],"basis":"sha256","note":"nothing deleted; others flagged duplicate_of"})
 c["duplicates"]={"groups":groups,"n_groups":len(groups),"method":"sha256_byte_identical"}
 fams={}
 for f in files:
  if f["type"]=="pdf": fams.setdefault(fam(Path(f["path"]).stem),[]).append(f)
 chains,edges=[],[]
 for fk,fs in sorted(fams.items()):
  if len(fs)<2: continue
  cid="VC%03d"%(len(chains)+1);nodes=[]
  for f in fs:
   tags,rk=vrank(Path(f["path"]).stem);nodes.append({"file":f["path"],"sha256":f["sha256"],"tags":tags,"rank":rk,"mtime":f.get("mtime")});f["chain_id"]=cid
  nodes.sort(key=lambda n:((n["rank"] if n["rank"] is not None else -1),n["mtime"] or ""))
  for a,b in zip(nodes,nodes[1:]): edges.append({"chain_id":cid,"from":a["file"],"to":b["file"],"relation":"supersedes","basis":"version_tag_or_date_order","from_tags":a["tags"],"to_tags":b["tags"]})
  chains.append({"chain_id":cid,"family_key":fk,"n_files":len(nodes),"nodes":nodes,"latest":nodes[-1]["file"],"basis":"family_key+tags+mtime; name alone is not proof"})
 c["version_chain"]={"chains":chains,"edges":edges,"admin_notes":[],"summary":{"chains":len(chains),"edges":len(edges)}}
 for a in admin:
  for m in CUEV.finditer(a["quote"]):
   seg=a["quote"][max(0,m.start()-160):m.start()+160]
   c["version_chain"]["admin_notes"].append({"file":a["file"],"quote":seg,"referenced":sorted(set(x.group(0) for x in REF.finditer(seg)))[:6]})
 anns=[]
 for f in files:
  d=docs.get(f["path"],{})
  if d.get("pdf") or d.get("docx"):
   try: anns+=annots(f,d,leg)
   except Exception as ex: err(c,"annot",f["path"],"%s: %s"%(type(ex).__name__,ex))
 c["annotations"]=anns;notes=mknotes(anns);c["notes"]=notes
 ix={n["note_id"]:set(toks((n["claim"] or "")+" "+(n["evidence"].get("quote") or ""))) for n in notes}
 links=[]
 for i,a in enumerate(notes):
  for b in notes[i+1:]:
   k=ix[a["note_id"]]&ix[b["note_id"]]
   if len(k)>=3: links.append({"from":a["note_id"],"to":b["note_id"],"relation":"shared_concept","basis":"shared_terms>=3","evidence":sorted(k)[:8]})
 c["links"]=links
 nix,fix={},{}
 for n in notes:
  for t in ix[n["note_id"]]: nix.setdefault(t,[]).append(n["note_id"])
 for f in files:
  for t in set(toks(Path(f["path"]).stem)): fix.setdefault(t,[]).append(f["path"])
 c["index"]={"note_terms":nix,"file_terms":fix,"n_terms":len(nix)}
 qs=[]
 def walk(o,d=0):
  if isinstance(o,dict):
   for k,v in o.items():
    if isinstance(v,str) and k.lower().replace("_","") in("query","question","searchquery","ask"): qs.append({"q":v,"origin":"case:"+k})
    elif d<6: walk(v,d+1)
  elif isinstance(o,list) and d<6:
   for i in o: walk(i,d+1)
 walk(c["_case"])
 for a in admin:
  for x in [y.strip() for z in a["quote"].splitlines()[1:] for y in z.split(",")]:
   if "?" in x and len(x)>6: qs.append({"q":x,"origin":"file:"+a["file"]})
 res=[]
 for i,q in enumerate(qs[:12]):
  tr=toks(q["q"]);h=hit(nix,tr)
  res.append({"qid":"Q%02d"%(i+1),"query":q["q"],"origin":q["origin"],"terms":tr[:12],"note_hits":[{"id":a,"score":b} for a,b in h],
   "file_hits":[{"id":a,"score":b} for a,b in hit(fix,tr)],"status":"answered" if h else "no_recall",
   "recall_caveat":"lexical only: no stems/synonyms; no_recall = vocabulary gap, not absence"})
 c["search"]={"queries":res,"n":len(res),"no_recall":sum(1 for r in res if r["status"]=="no_recall")}
 ver={"notes_total":len(notes),"quote_checked":0,"quote_found":0,"rejected":[]}
 for n in notes:
  q=n["evidence"].get("quote");d=docs.get(n["evidence"]["file"],{});pg=n["evidence"].get("page");src=None
  if d.get("pdf") and pg and 0<pg<=len(d["pdf"].pages): src=d["pdf"].pages[pg-1]["text"]
  elif d.get("docx"): src=d["docx"]["text"]
  elif d.get("text"): src=d["text"]
  if not q or src is None: continue
  ver["quote_checked"]+=1;ok=q in src;n["verification"]["quote_in_source"]=ok
  if ok: ver["quote_found"]+=1
  else: ver["rejected"].append(n["note_id"])
 c["verification"]=ver
 names={f["path"] for f in files};rec=[];gone=set()
 for a in admin:
  for m in REF.finditer(a["quote"]):
   t=m.group(0).strip()
   if t.lower() in("pdf","docx","csv") or len(t)<5: continue
   g=[x for x in names if x.endswith("/"+t) or Path(x).name==t]
   rec.append({"reference":t,"source":a["file"],"resolved":g[0] if g else None,"action":"relink" if g else "missing","basis":"basename_match"})
   if not g: gone.add(t)
 c["recovery"]=rec
 for t in sorted(gone): pend(c,t,"missing_referenced_file","absent; not fabricated")
 return files,docs
def flog(c,out):
 with open(out/"operations.log","w",encoding="utf-8") as fh:
  fh.write("# operations.log %s v%s\n"%(T,V))
  for r in c["log"]: fh.write("\t".join(str(r[k]) for k in("ts","op","status","target","detail"))+"\n")
def dump(c,out):
 K=["path","ext","type","size","sha256","mtime","mode","readable","pages","text_layer","title","author","year","doi","companion_source","duplicate_of","chain_id","status","notes"]
 with open(out/"inventory.csv","w",newline="",encoding="utf-8") as fh:
  w=csv.writer(fh);w.writerow(K)
  for f in c["inventory"]:
   m=f.get("meta",{});f["ext"]=Path(f.get("path","")).suffix.lower()
   for k in("title","author","year","doi"): f[k]=mv(m,k)
   f["notes"]=";".join(f.get("notes") or []);w.writerow([f.get(k) for k in K])
 wj(out/"version_chain.json",c["version_chain"]);wj(out/"annotations.json",{"annotations":c["annotations"],"n":len(c["annotations"])})
 wj(out/"notes.json",{"notes":c["notes"],"links":c["links"],"n":len(c["notes"])});wj(out/"index.json",c["index"]);flog(c,out)
 c["artifacts"]=[str(out/x) for x in("result.json","inventory.csv","operations.log","version_chain.json","annotations.json","notes.json","index.json")]
def main(argv=None):
 ap=argparse.ArgumentParser(prog="main.py",description="Library inventory + version chains + annotation anchors + notes + index (stdlib only).")
 ap.add_argument("--input",default="/input");ap.add_argument("--output",default="/app/output");ap.add_argument("--work",default="/app/work")
 a=ap.parse_args(argv)
 t0=time.time();inp=Path(a.input);out=Path(a.output)
 if not inp.exists() and Path("input").exists(): inp=Path("input")
 out.mkdir(parents=True,exist_ok=True)
 c={"case_id":None,"status":"partial","inventory":[],"annotations":[],"notes":[],"links":[],"duplicates":{"groups":[],"n_groups":0},
  "version_chain":{"chains":[],"edges":[],"admin_notes":[],"summary":{}},"search":{"queries":[],"n":0,"no_recall":0},"recovery":[],"artifacts":[],
  "sources":[],"uncertainty":[],"pending_human":[],"errors":[],"degradations":[],"changes":[],"skipped":[],"log":[],"summary":{},
  "inputs":{},"color_legend":{},"verification":{},"contract":{},"contract_raw":None,"contract_fill":{},
  "runtime":{"started":now()},"_t0":t0,"_fatal":False,"_case":{},"index":{"note_terms":{},"file_terms":{}}}
 wj(out/"result.json",result(c))
 try:
  cand=[p for p in([inp/"case.json"]+sorted(inp.glob("**/case*.json"))) if p.exists()]
  case=jl(cand[0]) if cand else None
  if not isinstance(case,dict): err(c,"input","case.json","missing_or_invalid_case_json");pend(c,"case.json","no parsable case.json","scan files only")
  else:
   c["_case"]=case;c["case_id"]=case.get("case_id")
   c["inputs"]["task_instruction"]=str(case.get("task_instruction") or "")[:600]
   c["inputs"]["case_json"]=rel(cand[0],inp)
  sp=spec(case)
  if sp is not None: c["contract_raw"]=json.loads(json.dumps(sp,default=str))
  log(c,"discover","input","ok",str(inp))
  files,docs=pipeline(c,inp);log(c,"scan","files","ok","%d files"%len(files))
  try: c["contract"]=fill(c["contract_raw"],c,rep=c["contract_fill"]) if c["contract_raw"] is not None else {}
  except Exception as ex: err(c,"contract","","%s: %s"%(type(ex).__name__,ex))
  c["sources"]=[{"id":f["id"],"path":f["path"],"sha256":f["sha256"],"type":f["type"],"status":f["status"]} for f in files]
  for f in files:
   if f["status"]!="ok" or f.get("notes"): c["degradations"].append({"path":f["path"],"notes":f.get("notes"),"status":f["status"]})
  for g in c["duplicates"]["groups"]: c["changes"].append({"op":"dedupe_flag","group":g["sha256"][:16],"canonical":g["canonical"],"files":g["files"]})
  c["summary"]={"files":len(files),"annotations":len(c["annotations"]),"anchors_resolved":sum(1 for x in c["annotations"] if x.get("quote")),
   "notes":len(c["notes"]),"links":len(c["links"]),"duplicate_groups":len(c["duplicates"]["groups"]),"version_chains":len(c["version_chain"]["chains"]),
   "queries":c["search"]["n"],"quote_verified":c["verification"].get("quote_found"),"skipped":len(c["skipped"]),"pending_human":len(c["pending_human"]),"errors":len(c["errors"])}
  for n in c["notes"]:
   if n["verification"].get("quote_in_source") is False: pend(c,n["note_id"],"quote_not_in_source","review anchor; note kept but flagged")
  ntl=[f["path"] for f in files if f.get("text_layer") is False]
  if ntl: c["uncertainty"].append({"item":"anchors","reason":"no text layer","files":ntl,"impact":"anchors unresolved until OCR supplied"})
  if c["search"]["no_recall"]: c["uncertainty"].append({"item":"retrieval","reason":"lexical index","no_recall":c["search"]["no_recall"],"impact":"recall may be understated"})
  c["uncertainty"].append({"item":"version_order","reason":"filename tags+mtime","impact":"confirm vs publisher record"})
 except Exception as ex:
  c["_fatal"]=True;err(c,"pipeline","","%s: %s"%(type(ex).__name__,ex));c["changes"].append({"op":"finalize_fallback"})
 try: dump(c,out)
 except Exception as ex: c["artifacts"]=[];err(c,"dump","",type(ex).__name__)
 r=result(c);wj(out/"result.json",r)
 try:
  log(c,"finalize",r["status"],"result.json","%d files, %d notes"%(len(c["inventory"]),len(c["notes"])));flog(c,out)
 except Exception: pass
 print("status=%s files=%d annotations=%d notes=%d links=%d dup=%d chains=%d"%(r["status"],len(c["inventory"]),len(c["annotations"]),len(c["notes"]),len(c["links"]),len(c["duplicates"]["groups"]),len(c["version_chain"]["chains"])))
 return 0
if __name__=="__main__":
 try: sys.exit(main())
 except SystemExit: raise
 except Exception as ex:
  try:
   o=Path("/app/output");o.mkdir(parents=True,exist_ok=True)
   wj(o/"result.json",{"tool":T,"version":V,"status":"input_error","errors":[{"stage":"fatal","error":"%s: %s"%(type(ex).__name__,ex)}]})
  except Exception: pass
  print("fatal: %s"%type(ex).__name__);sys.exit(0)
