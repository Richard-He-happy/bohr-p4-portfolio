#!/usr/bin/env python3
"""analyze.py - multistep scientific table analysis (analysis-05).

discover -> import -> field align -> clean -> statistics -> figures -> report
-> output_contract backfill -> self-check. Stdlib only, no network, deterministic,
always exits 0. Methods, formulas and limits: references/rules.md.
"""
import argparse, csv, hashlib, io, json, math, re, sqlite3, sys, time, zipfile, zlib
from pathlib import Path
from xml.etree import ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parent))
import statslib as S

VER = "1.1.0"
T0 = time.time()
MISS = {"", "na", "n/a", "n.a.", "nan", "null", "none", "nil", "-", "--", "?", ".",
        "missing", "nd", "unknown", "not available", "not determined"}
UNITS = {"mm": 1e-3, "cm": 1e-2, "m": 1.0, "um": 1e-6, "nm": 1e-9, "mg": 1e-3, "g": 1.0,
         "kg": 1e3, "ug": 1e-6, "ms": 1e-3, "s": 1.0, "sec": 1.0, "min": 60.0, "h": 3600.0,
         "pa": 1.0, "kpa": 1e3, "mpa": 1e6, "gpa": 1e9, "bar": 1e5, "%": 1e-2, "pct": 1e-2}
META = ("case_id", "status", "sources", "uncertainty", "pending_human", "errors",
        "degradations", "changes", "runtime", "artifacts", "selfcheck", "contract", "skill")


class Run:
 "Run state: errors, degradations, pending items, sources, change log."

 def __init__(s):
  s.err, s.deg, s.pend, s.src, s.chg, s.log = [], [], [], [], [], []

 def e(s, a, b, c=""):
  s.err.append({"stage": a, "message": str(b)[:280], "detail": str(c)[:400]})
  s.log.append("ERROR [%s] %s | %s" % (a, b, str(c)[:160]))

 def d(s, a, b=""):
  s.deg.append({"code": a, "detail": str(b)[:280]})
  s.log.append("DEGRADED [%s] %s" % (a, b))

 def p(s, a, b, c=""):
  s.pend.append({"item": str(a)[:180], "needs": str(b)[:180], "detail": str(c)[:280]})
  s.log.append("PENDING %s -> %s" % (a, b))

 def s_(s, i, p, loc, note, sha="", nb=None):
  s.src.append({"id": i, "path": str(p), "locator": loc, "note": note, "sha256": sha, "bytes": nb})

 def c_(s, i, f, t, w):
  s.chg.append({"item": i, "from": f, "to": t, "reason": str(w)[:250]})
  s.log.append("CHANGE %s %s -> %s" % (i, f, t))


def fin(o):
 "JSON-safe copy: non-finite floats -> null, keys -> str, 6 significant digits."
 if isinstance(o, bool) or o is None:
  return o
 if isinstance(o, float):
  return None if (o != o or o in (float("inf"), float("-inf"))) else float("%.6g" % o)
 if isinstance(o, dict):
  return {str(k): fin(v) for k, v in o.items()}
 if isinstance(o, (list, tuple)):
  return [fin(v) for v in o]
 return o


def wj(p, o):
 p.parent.mkdir(parents=True, exist_ok=True)
 p.write_text(json.dumps(fin(o), indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
 return p


def wcv(p, rows, head=None):
 p.parent.mkdir(parents=True, exist_ok=True)
 b = io.StringIO()
 w = csv.writer(b, lineterminator="\n")
 if head:
  w.writerow(head)
 for r in rows:
  w.writerow(["" if v is None else (S.fmt(v) if isinstance(v, float) else v) for v in r])
 p.write_text(b.getvalue(), encoding="utf-8")
 return p


def sh16(p):
 try:
  return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
 except Exception:
  return ""


def dec(b):
 for e in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
  try:
   return b.decode(e), e
  except Exception:
   pass
 return b.decode("utf-8", "replace"), "utf-8(replace)"


def txt(p):
 try:
  return dec(p.read_bytes())[0]
 except Exception:
  return ""


def lcsv(p, R):
 b = p.read_bytes()
 t, enc = dec(b)
 if enc not in ("utf-8", "utf-8-sig"):
  R.c_("encoding", "non-utf8", enc, "%s decoded as %s" % (p.name, enc))
 s = t.strip()
 if not s:
  R.d("empty_file", p.name)
  return {"name": p.stem, "cols": [], "rows": [], "source": str(p)}
 h = s.splitlines()[0]
 try:
  dl = csv.Sniffer().sniff(h, delimiters=",;\t|").delimiter
 except Exception:
  dl = max([",", ";", "\t", "|"], key=h.count)
 rows = list(csv.reader(io.StringIO(t), delimiter=dl))
 if not rows:
  R.d("empty_table", p.name)
  return {"name": p.stem, "cols": [], "rows": [], "source": str(p)}
 cols = [(c or "").strip().strip('"') or "col%d" % i for i, c in enumerate(rows[0])]
 body = [(r + [""] * len(cols))[:len(cols)] for r in rows[1:] if any(str(x).strip() for x in r)]
 if not body:
  R.d("no_data_rows", p.name)
 R.s_(p.name, p, "header + %d data rows" % len(body), "delimiter=%r enc=%s" % (dl, enc), sh16(p), len(b))
 return {"name": p.stem, "cols": cols, "rows": body, "source": str(p)}


def lxlsx(p, R):
 z = zipfile.ZipFile(p)
 nm = set(z.namelist())
 sh = []
 if "xl/sharedStrings.xml" in nm:
  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter():
   if si.tag.endswith("}si"):
    sh.append("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")))
 sheets = sorted(n for n in nm if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
 if not sheets:
  raise ValueError("no worksheet part")
 grid = []
 for row in ET.fromstring(z.read(sheets[0])).iter():
  if not row.tag.endswith("}row"):
   continue
  cells = {}
  for c in row:
   if not c.tag.endswith("}c"):
    continue
   m = re.match(r"([A-Z]+)", c.get("r") or "A")
   ci = 0
   for ch in (m.group(1) if m else "A"):
    ci = ci * 26 + (ord(ch) - 64)
   ci = max(ci - 1, 0)
   v, ins = c.find("{*}v"), c.find("{*}is")
   if c.get("t") == "s" and v is not None and v.text:
    k = int(float(v.text))
    val = sh[k] if 0 <= k < len(sh) else ""
   elif ins is not None:
    val = "".join(t.text or "" for t in ins.iter() if t.tag.endswith("}t"))
   else:
    val = (v.text or "") if v is not None else ""
   cells[ci] = val
  if cells:
   grid.append([cells.get(i, "") for i in range(max(cells) + 1)])
 grid = [r for r in grid if any(str(x).strip() for x in r)]
 if not grid:
  R.d("empty_table", p.name)
  return {"name": p.stem, "cols": [], "rows": [], "source": str(p)}
 cols = [str(c).strip() or "col%d" % i for i, c in enumerate(grid[0])]
 body = [(r + [""] * len(cols))[:len(cols)] for r in grid[1:]]
 R.s_(p.name, p, "%s rows=%d cols=%d" % (sheets[0], len(body), len(cols)), "xlsx first sheet",
      sh16(p), p.stat().st_size)
 return {"name": p.stem, "cols": cols, "rows": body, "source": str(p)}


def ldb(p, R):
 try:
  con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
 except Exception as ex:
  R.e("db_open", p.name, ex)
  R.p("database %s" % p.name, "provide an accessible sqlite copy")
  return {"name": p.stem, "cols": [], "rows": [], "source": str(p)}
 try:
  tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
  best = None
  for t in tabs:
   try:
    n = con.execute('select count(*) from "%s"' % t.replace('"', '""')).fetchone()[0]
   except Exception:
    continue
   if best is None or n > best[1]:
    best = (t, n)
  if not best:
   R.d("db_no_table", p.name)
   return {"name": p.stem, "cols": [], "rows": [], "source": str(p), "tables": tabs}
  cur = con.execute('select * from "%s"' % best[0].replace('"', '""'))
  cols = [d[0] for d in cur.description]
  rows = [["" if v is None else v for v in r] for r in cur.fetchall()]
  R.s_(p.name, p, "sqlite table %s (%d rows)" % best[0], "tables=%s" % ",".join(tabs), sh16(p),
       p.stat().st_size)
  return {"name": best[0], "cols": cols, "rows": rows, "source": str(p), "tables": tabs}
 finally:
  con.close()


def ldocx(p, R):
 root = ET.fromstring(zipfile.ZipFile(p).read("word/document.xml"))
 ps = []
 for par in root.iter():
  if par.tag.endswith("}p"):
   s = "".join(t.text or "" for t in par.iter() if t.tag.endswith("}t")).strip()
   if s:
    ps.append(s)
 R.s_(p.name, p, "%d paragraphs" % len(ps), "docx text", sh16(p), p.stat().st_size)
 return "\n".join(ps)


def lpdf(p, R):
 raw = p.read_bytes()
 out = []
 for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
  blob = m.group(1)
  try:
   blob = zlib.decompress(blob)
  except Exception:
   pass
  for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", blob):
   s = re.sub(rb"\\([()\\])", rb"\1", t.group(0)[1:-1]).decode("latin-1", "replace")
   if len(s) > 1:
    out.append(s)
 pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
 R.s_(p.name, p, "pages=%d" % pages, "raw stream text extraction (stdlib)", sh16(p), len(raw))
 if not out:
  R.d("pdf_no_text_layer", p.name)
  R.p("pdf %s" % p.name, "supply a text layer or the underlying table")
  return ""
 return " ".join(out)


def jgrid(o, name):
 tabs = []
 if isinstance(o, list) and o and all(isinstance(r, dict) for r in o):
  cols = []
  for r in o:
   for k in r:
    if k not in cols:
     cols.append(k)
  tabs.append({"name": name, "cols": cols, "source": name,
               "rows": [["" if r.get(c) is None else r.get(c) for c in cols] for r in o]})
 elif isinstance(o, dict) and o and all(isinstance(v, list) for v in o.values()):
  cols = list(o.keys())
  n = max(len(v) for v in o.values())
  tabs.append({"name": name, "cols": cols, "source": name,
               "rows": [["" if i >= len(o[c]) or o[c][i] is None else o[c][i] for c in cols] for i in range(n)]})
 elif isinstance(o, dict):
  for k, v in o.items():
   if isinstance(v, (list, dict)):
    tabs.extend(jgrid(v, name + "." + k))
 return tabs


def disc(ind, R):
 files = [p for p in sorted(ind.rglob("*")) if p.is_file() and not p.name.startswith(".")]
 case, task = {}, ""
 for p in files:
  if p.name.lower() == "case.json":
   try:
    case = json.loads(txt(p))
    R.s_(p.name, p, "case json", "authoritative case description", sh16(p), p.stat().st_size)
   except Exception as ex:
    R.e("case_json", p.name, ex)
    R.p("case.json", "provide a valid JSON case file")
    case = {"_broken": p.name}
   break
 if not case:
  for p in files:
   if p.suffix.lower() == ".json" and "case" in p.name.lower():
    try:
     case = json.loads(txt(p))
     R.d("case_renamed", p.name)
     break
    except Exception:
     pass
 if not case:
  R.d("case_absent", "no case.json under input")
  case = {}
 for p in files:
  if p.name.lower() in ("task.md", "task.txt"):
   task = txt(p)
   R.s_(p.name, p, "task text", "instruction", sh16(p), p.stat().st_size)
   break
 return case, task, files


def loadall(files, R):
 tabs, docs, dic = [], {}, []
 for p in files:
  e, n = p.suffix.lower(), p.name.lower()
  if n in ("case.json", "task.md", "task.txt"):
   continue
  try:
   if p.stat().st_size == 0:
    R.d("empty_file", p.name)
    continue
   if e in (".csv", ".tsv"):
    t = lcsv(p, R)
    if t["cols"]:
     tabs.append(t)
    else:
     docs[p.name] = txt(p)
   elif e in (".xlsx", ".xlsm"):
    t = lxlsx(p, R)
    if t["cols"]:
     tabs.append(t)
   elif e in (".db", ".sqlite", ".sqlite3"):
    t = ldb(p, R)
    if t["cols"]:
     tabs.append(t)
   elif e == ".json":
    o = json.loads(txt(p))
    if isinstance(o, dict) and ("output_contract" in o or "case_id" in o):
     continue
    ts = jgrid(o, p.stem)
    if ts:
     tabs.extend(ts)
     R.s_(p.name, p, "json tables=%d" % len(ts), "structured table", sh16(p), p.stat().st_size)
    else:
     docs[p.name] = txt(p)
     dic.append((p.name, o))
   elif e == ".xls":
    R.p("file %s" % p.name, "convert legacy .xls to .xlsx")
   elif e == ".docx":
    docs[p.name] = ldocx(p, R)
   elif e == ".pdf":
    t = lpdf(p, R)
    if t:
     docs[p.name] = t
   elif e in (".md", ".txt", ".sql", ".yaml", ".yml"):
    t = txt(p)
    docs[p.name] = t
    if e in (".md", ".txt"):
     dic.append((p.name, t))
  except Exception as ex:
   R.e("load", p.name, ex)
   R.p("material %s" % p.name, "supply a readable copy", repr(ex)[:120])
 return tabs, docs, dic


def usplit(n,D):
 d=D.get(n.strip().lower()) or {};u=(d.get("unit") or "").strip();b=n
 if not u:
  m=re.search(r"^(.*?)[\s_\[(]+([A-Za-z%]{1,5})[\])]?\s*$",n.strip())
  if m and m.group(2).lower().replace("\u00b5","u").replace("\u03bc","u") in UNITS:b,u=m.group(1),m.group(2)
 u=u.replace("\u00b5","u").replace("\u03bc","u").lower()
 return (b or n),(u if u in UNITS else "")


def dmap(dic):
 D={}
 for nm,o in dic:
  rows=[]
  if isinstance(o,dict):
   for k in ("fields","columns","variables","schema","data_dictionary"):
    if isinstance(o.get(k),(dict,list)):o=o[k];break
   if isinstance(o,dict):
    rows=[[k,(v.get("type") or v.get("dtype") or "") if isinstance(v,dict) else "",
      (v.get("unit") or "") if isinstance(v,dict) else ""] for k,v in o.items()]
   else:rows=[[str(r[0]),(r[1] if len(r)>1 else ""),(r[2] if len(r)>2 else "")] for r in o if isinstance(r,(list,tuple)) and r]
  elif isinstance(o,str):
   for ln in o.splitlines():
    s=ln.strip().strip("|").strip()
    if not s or s.startswith("#") or set(s)<=set("-|: "):continue
    q=[x.strip() for x in s.split("|")] if "|" in s else s.split(None,3)
    if len(q)>=2:rows.append(q[:4])
  for r in rows:
   k=str(r[0]).strip("*` ").lower()
   if k and k not in ("field","name","column","variable","fieldname"):
    D[k]={"type":str(r[1]).lower() if len(r)>1 else "","unit":str(r[2]) if len(r)>2 else "","src":nm}
 return D


def clean(t,D,R):
 nm=list(t["cols"]);rw=[list(x) for x in t["rows"]];n0=len(rw);miss={k:0 for k in nm}
 for x in rw:
  for j,k in enumerate(nm):
   if str(x[j]).strip().lower() in MISS:x[j]="";miss[k]+=1
 ty={}
 for j,k in enumerate(nm):
  v=[x[j] for x in rw if str(x[j]).strip()!=""]
  ok=sum(1 for u in v if S.num(u) is not None)
  ty[k]="numeric" if (v and ok>=.9*len(v)) else ("categorical" if (v and len({str(u).strip() for u in v})<=max(12,len(v)//2)) else "text")
 un={};bad={}
 for j,k in enumerate(nm):
  if ty[k]!="numeric":continue
  b,u=usplit(k,D);f=UNITS[u] if u else 1.0
  un[k]={"unit":u or "as_given","base":b,"factor":f,"to_base":"value*%r"%f,"back":"value/%r"%f}
  c=0
  for x in rw:
   s=str(x[j]).strip()
   if s=="":continue
   v=S.num(s)
   if v is None:c+=1;x[j]=""
   else:x[j]=v*f
  bad[k]=c
 seen={};dup=[];keep=[]
 for i,x in enumerate(rw):
  kk=tuple("" if str(x[j]).strip()=="" else (S.fmt(x[j],12) if ty[nm[j]]=="numeric" else str(x[j]).strip()) for j in range(len(nm)))
  if kk in seen:dup.append({"row":i+2,"dup_of":seen[kk]})
  else:seen[kk]=i+2;keep.append(x)
 out={}
 for j,k in enumerate(nm):
  if ty[k]!="numeric":continue
  c2=[x[j] if str(x[j])!="" else None for x in keep]
  fl,me=S.outlier_scan(c2,"iqr")
  out[k]={"n":sum(fl),"rule":me,"rows":[i+2 for i,v in enumerate(fl) if v][:30]}
 R.c_("rows",n0,len(keep),"exact duplicate rows removed: %d, first occurrence kept"%len(dup))
 return {"names":nm,"rows":keep,"ty":ty,"units":un,"miss":miss,"bad":bad,"dup":dup,"out":out,
  "n_in":n0,"n_out":len(keep),"table":t.get("name",""),"src":t.get("source","")}


def qual(cl):
 q={"table":cl["table"],"source":cl["src"],"rows_in":cl["n_in"],"rows_out":cl["n_out"],
  "rows_removed":cl["n_in"]-cl["n_out"],"duplicates_removed":len(cl["dup"]),"duplicate_rows":cl["dup"][:100],
  "missing_by_field":cl["miss"],"missing_total":sum(cl["miss"].values()),
  "coerced_to_null":cl["bad"],"units":cl["units"],"outliers":cl["out"],"types":cl["ty"],
  "rules":[{"rule":"missing tokens -> null","policy":"blank kept in cleaned.csv, never imputed"},
   {"rule":"type inference","policy":"numeric if >=90% parse; categorical if <=max(12,n/2) levels"},
   {"rule":"numeric coercion","policy":"unparseable -> null, counted per field"},
   {"rule":"duplicates","policy":"full-row key after type/unit normalisation; keep first"},
   {"rule":"outliers","policy":"Tukey 1.5*IQR flag only; rows retained, never dropped"},
   {"rule":"units","policy":"converted to base unit with reversible factor per field"},
   {"rule":"encoding","policy":"utf-8 -> gb18030 -> gbk -> latin-1 detection, logged"}]}
 q["field_issues"]=[{"field":k,"missing":v,"coerced":cl["bad"].get(k,0),
  "outliers":(cl["out"].get(k) or {}).get("n",0)} for k,v in cl["miss"].items()
  if v or cl["bad"].get(k) or (cl["out"].get(k) or {}).get("n")]
 return q
