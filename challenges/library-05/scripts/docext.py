"""docext.py - stdlib-only extraction: PDF text/annotations with char-offset anchors, DOCX comments."""
import csv,re,zipfile,zlib
from pathlib import Path
CT={".pdf":"pdf",".docx":"docx",".doc":"doc_legacy",".xlsx":"xlsx",".xls":"xls_legacy",".csv":"csv",".tsv":"csv",".json":"json",".md":"text",".txt":"text",".html":"html",".htm":"html",".png":"image",".jpg":"image",".jpeg":"image",".tif":"image",".tiff":"image",".bib":"text",".ris":"text",".rtf":"rtf"}
MAG=[(b"%PDF","pdf"),(b"PK\x03\x04","zip"),(b"\x89PNG","image"),(b"\xff\xd8\xff","image"),(b"{\\rtf","rtf"),(b"\xd0\xcf\x11\xe0","ole")]
def sniff(p):
    k=CT.get(Path(p).suffix.lower(),"unknown")
    try: h=open(p,"rb").read(8)
    except OSError: return k,"unreadable"
    m=next((v for a,v in MAG if h.startswith(a)),None)
    if m=="pdf": return "pdf","magic"
    if m=="zip": return (k if k in("docx","xlsx") else "zip"),"magic"
    if m=="image": return "image","magic"
    if m=="ole": return (k if k!="unknown" else "ole"),"magic"
    return (k,"empty") if not h else (k,"ext")
def fnum(v,d=0.0):
    try: return float(v)
    except (TypeError,ValueError): return d
def unesc(b):
    o=bytearray();i=0
    while i<len(b):
        c=b[i:i+1]
        if c==b"\\" and i+1<len(b):
            n=b[i+1:i+2];mp={b"n":b"\n",b"r":b"\r",b"t":b"\t",b"b":b"\b",b"f":b"\f",b"(":b"(",b")":b")",b"\\":b"\\"}
            if n in mp: o+=mp[n];i+=2;continue
            m=re.match(rb"[0-7]{1,3}",b[i+1:i+4])
            if m: o.append(int(m.group(0),8)&255);i+=1+len(m.group(0));continue
            i+=2;continue
        o+=c;i+=1
    return bytes(o)
class Ref:
    __slots__=("n",)
    def __init__(s,n): s.n=n
def lex(b):
    o=[];i=0;n=len(b)
    while i<n:
        c=b[i:i+1]
        if c in b" \t\r\n\f\x00": i+=1;continue
        if c==b"%":
            j=b.find(b"\n",i);i=n if j<0 else j+1;continue
        if c==b"(":
            j=i+1;d=1;buf=bytearray()
            while j<n:
                ch=b[j:j+1]
                if ch==b"\\": buf+=b[j:j+2];j+=2;continue
                if ch==b"(": d+=1
                elif ch==b")":
                    d-=1
                    if not d: break
                buf+=ch;j+=1
            o.append(("str",unesc(bytes(buf))));i=j+1;continue
        if c==b"<":
            if b[i:i+2]==b"<<": o.append(("kw","<<"));i+=2;continue
            j=b.find(b">",i);j=n if j<0 else j
            h=re.sub(rb"[^0-9A-Fa-f]",b"",b[i+1:j])
            if len(h)%2: h+=b"0"
            try: o.append(("str",bytes.fromhex(h.decode())))
            except ValueError: o.append(("str",b""))
            i=j+1;continue
        if c==b">":
            if b[i:i+2]==b">>": o.append(("kw",">>"));i+=2;continue
            i+=1;continue
        if c in b"[]": o.append(("kw",c.decode()));i+=1;continue
        if c==b"/":
            m=re.match(rb"/([^\s()<>\[\]{}/%]*)",b[i:]);o.append(("name",m.group(1).decode("latin-1")));i+=m.end();continue
        m=re.match(rb"[-+]?(?:\d+\.\d*|\.\d+|\d+)",b[i:])
        if m:
            s=m.group(0);o.append(("num",float(s) if b"." in s else int(s)));i+=m.end();continue
        m=re.match(rb"[A-Za-z*'\"]+",b[i:])
        if m: o.append(("kw",m.group(0).decode("latin-1")));i+=m.end();continue
        i+=1
    return o
def pval(tk,i):
    if i>=len(tk): return None,i
    k,v=tk[i]
    if k=="kw" and v=="<<":
        d={};i+=1
        while i<len(tk):
            if tk[i]==("kw",">>"): return d,i+1
            if tk[i][0]=="name":
                key=tk[i][1];val,i=pval(tk,i+1);d[key]=val
            else: i+=1
        return d,i
    if k=="kw" and v=="[":
        a=[];i+=1
        while i<len(tk):
            if tk[i]==("kw","]"): return a,i+1
            val,i=pval(tk,i);a.append(val)
        return a,i
    if k=="num" and i+2<len(tk) and tk[i+1][0]=="num" and tk[i+2]==("kw","R"): return Ref(int(v)),i+3
    return v,i+1
def pdict(b):
    v,_=pval(lex(b),0);return v if isinstance(v,dict) else {}
def inflate(s):
    for w in (15,-15):
        try: return zlib.decompress(s,w)
        except zlib.error: pass
    try: return zlib.decompressobj().decompress(s)
    except zlib.error: return b""
def dstream(f,data):
    for x in (f if isinstance(f,list) else ([f] if f else [])):
        if isinstance(x,dict):
            x=x.get("Filter");x=x[0] if isinstance(x,list) and x else x
        if x=="FlateDecode": data=inflate(data)
        elif x=="ASCIIHexDecode":
            h=re.sub(rb"[^0-9A-Fa-f]",b"",data.split(b">")[0]);h+=b"0" if len(h)%2 else b""
            try: data=bytes.fromhex(h.decode())
            except ValueError: return b""
        else: return b""
    return data
def txtof(v):
    return v.decode("latin-1").replace("\x00","").strip() if isinstance(v,bytes) else None
def hexcol(c):
    if not isinstance(c,list) or not c: return None
    v=[fnum(x) for x in c]
    if len(v)==1: v=v*3
    if len(v)==4:
        y,m,yy,k=[max(0,min(1,t)) for t in v];v=[(1-y)*(1-k),(1-m)*(1-k),(1-yy)*(1-k)]
    if len(v)<3: return None
    return "#"+"".join("%02X"%int(round(max(0,min(1,t))*255)) for t in v[:3])
class PDF:
    """Parsed PDF: objects, ordered pages, text runs, annotations, anchor alignment."""
    def __init__(s,path,max_pages=60,max_stream=6000000):
        s.path=str(path);s.errors=[];s.encrypted=False;s.meta={};s.pages=[];s.objs={};s.size=0
        try: data=Path(path).read_bytes()
        except OSError as e: s.errors.append({"stage":"read","error":str(e)});return
        s.size=len(data)
        if b"%PDF" not in data[:2048]: s.errors.append({"stage":"header","error":"no %PDF header"})
        s.encrypted=bool(re.search(rb"/Encrypt\s*(\d+\s+\d+\s+R|<<)",data))
        for m in re.finditer(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b",data):
            e=data.find(b"endobj",m.end());e=len(data) if e<0 else e
            body=data[m.end():e];sm=re.search(rb"\bstream\r?\n",body);dp,sd=body,None
            if sm:
                dp=body[:sm.start()];raw=body[sm.end():];c=raw.rfind(b"endstream");raw=raw[:c] if c>=0 else raw
                ln=pdict(dp).get("Length")
                sd=raw[:int(ln)] if isinstance(ln,(int,float)) and 0<int(ln)<=len(raw) else raw
            try: s.objs[int(m.group(1))]=(pdict(dp),sd)
            except Exception: continue
        s._objstm();s.meta=s._info()
        try: s.pages=s._pages(max_pages,max_stream)
        except Exception as e: s.errors.append({"stage":"pages","error":repr(e)})
    def res(s,x,d=0):
        while isinstance(x,Ref) and d<8: x=s.objs.get(x.n,(None,None))[0];d+=1
        return x
    def stream(s,x):
        if not isinstance(x,Ref): return b""
        d,sd=s.objs.get(x.n,(None,None))
        return dstream((d or {}).get("Filter"),sd) if sd is not None else b""
    def _objstm(s):
        add={}
        for num,(d,sd) in list(s.objs.items()):
            if (d or {}).get("Type")!="ObjStm" or sd is None: continue
            raw=dstream(d.get("Filter"),sd);first=d.get("First");cnt=d.get("N")
            if not raw or not isinstance(first,int) or not isinstance(cnt,int): continue
            head=raw[:first].split()
            for k in range(0,min(len(head),2*cnt)-1,2):
                try: onum,off=int(head[k]),int(head[k+1])
                except ValueError: continue
                end=first+int(head[k+3]) if k+3<len(head) and head[k+3].isdigit() else None
                add[onum]=(pdict(raw[first+off:end] if end else raw[first+off:]),None)
        for k,v in add.items(): s.objs.setdefault(k,v)
    def _info(s):
        for d,_ in s.objs.values():
            if not isinstance(d,dict): continue
            if any(k in d for k in("Title","Producer","CreationDate")):
                return {k:d[k].decode("latin-1") for k in("Title","Author","Subject","Keywords","Creator","Producer","CreationDate","ModDate") if isinstance(d.get(k),bytes)}
        return {}
    def _pages(s,max_pages,max_stream):
        cat=next((d for _,(d,_s) in sorted(s.objs.items()) if isinstance(d,dict) and d.get("Type")=="Catalog"),None)
        order=[];stack=[cat.get("Pages")] if cat else []
        while stack and len(order)<2000:
            node=stack.pop(0);ref=node.n if isinstance(node,Ref) else None;d=s.res(node)
            if not isinstance(d,dict): continue
            kids=s.res(d.get("Kids"))
            if d.get("Type")=="Page" or (kids is None and "Contents" in d): order.append((ref,d))
            elif isinstance(kids,list): stack=kids+stack
        if not order: order=[(n,d) for n,(d,_s) in sorted(s.objs.items()) if isinstance(d,dict) and d.get("Type")=="Page"]
        out=[]
        for idx,(ref,d) in enumerate(order[:max_pages]):
            pg={"index":idx+1,"obj":ref,"annots":[],"text":"","runs":[],"lines":[],"layer":False}
            try: pg["annots"]=s._annots(d)
            except Exception as e: s.errors.append({"stage":"annots","page":idx+1,"error":repr(e)})
            try: pg.update(s._text(d,max_stream))
            except Exception as e: s.errors.append({"stage":"text","page":idx+1,"error":repr(e)})
            out.append(pg)
        return out
    def _cmap(s,fd):
        raw=s.stream(fd.get("ToUnicode"))
        if not raw: return {},1
        m={};two=False
        for blk in re.findall(rb"beginbfchar(.*?)endbfchar",raw,re.S):
            for a,b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",blk):
                try: m[int(a,16)]=bytes.fromhex(b.decode()).decode("utf-16-be","replace");two=two or len(a)>=4
                except ValueError: continue
        for blk in re.findall(rb"beginbfrange(.*?)endbfrange",raw,re.S):
            for lo,hi,dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",blk):
                try: a,b,base=int(lo,16),int(hi,16),int(dst,16)
                except ValueError: continue
                two=two or len(lo)>=4
                for k in range(min(b-a,65535)+1):
                    try: m[a+k]=chr(base+k)
                    except ValueError: break
        return m,(2 if two else 1)
    @staticmethod
    def dec(bs,cm,nb):
        if not cm: return bs.decode("cp1252","replace")
        o=[]
        for i in range(0,len(bs),nb):
            seg=bs[i:i+nb];code=int.from_bytes(seg,"big")
            o.append(cm[code] if code in cm else ("\ufffd" if nb==2 and len(seg)==2 else seg.decode("cp1252","replace")))
        return "".join(o)
    def _text(s,d,max_stream):
        res=s.res(d.get("Resources")) or {};fonts={}
        fd=s.res(res.get("Font"))
        if isinstance(fd,dict):
            for name,fr in fd.items():
                fo=s.res(fr)
                if isinstance(fo,dict):
                    try: fonts[name]=s._cmap(fo)
                    except Exception: fonts[name]=({},1)
        c=d.get("Contents");ch=[];tot=0
        for r in (c if isinstance(c,list) else [c]):
            b=s.stream(r);tot+=len(b)
            if tot>max_stream: s.errors.append({"stage":"content","page":d.get("index"),"error":"content_stream_cap"});break
            ch.append(b)
        tk=lex(b"".join(ch));runs=[];st=[];x=y=0.0;size=12.0;tl=0.0;font=None;i=0;n=len(tk)
        while i<n:
            k,v=tk[i];i+=1
            if k!="kw": st.append((k,v));continue
            if v=="[":
                a=[]
                while i<n and tk[i]!=("kw","]"): a.append(tk[i][1]);i+=1
                i+=1;st.append(("arr",a));continue
            if v=="<<":
                dp=1
                while i<n and dp:
                    if tk[i]==("kw","<<"): dp+=1
                    elif tk[i]==("kw",">>"): dp-=1
                    i+=1
                st=[];continue
            if v=="BT": x=y=0.0
            elif v=="Tf" and len(st)>=2: font=st[-2][1];size=fnum(st[-1][1],12.0)
            elif v=="TL" and st: tl=fnum(st[-1][1])
            elif v in("Td","TD") and len(st)>=2:
                x+=fnum(st[-2][1]);y+=fnum(st[-1][1])
                if v=="TD": tl=-fnum(st[-1][1])
            elif v=="Tm" and len(st)>=6: x,y=fnum(st[-2][1]),fnum(st[-1][1])
            elif v=="T*": y-=tl or size*1.2
            elif v in("Tj","'",'"'):
                if v!="Tj": y-=tl or size*1.2
                raw=next((val for kk,val in reversed(st) if kk=="str"),None)
                if isinstance(raw,bytes):
                    t=s.dec(raw,*fonts.get(font,({},1)))
                    if t.strip(): runs.append({"x":round(x,2),"y":round(y,2),"size":round(size,2),"text":t})
                    x+=len(t)*size*0.5
            elif v=="TJ" and st and st[-1][0]=="arr":
                cm,nb=fonts.get(font,({},1));acc=""
                for el in st[-1][1]:
                    if isinstance(el,bytes): acc+=s.dec(el,cm,nb)
                    elif isinstance(el,(int,float)): x-=float(el)/1000.0*size
                if acc.strip(): runs.append({"x":round(x,2),"y":round(y,2),"size":round(size,2),"text":acc})
                x+=len(acc)*size*0.5
            st=[]
        text,lines=s.layout(runs)
        return {"text":text,"runs":runs,"lines":lines,"layer":len(text.strip())>20}
    @staticmethod
    def layout(runs):
        runs=sorted(runs,key=lambda r:(-r["y"],r["x"]));lines=[];cur=[]
        for r in runs:
            if cur and abs(cur[-1]["y"]-r["y"])>max(2.5,0.35*r["size"]): lines.append(cur);cur=[]
            cur.append(r)
        if cur: lines.append(cur)
        text=""
        for li,line in enumerate(lines):
            line.sort(key=lambda r:r["x"])
            if li: text+="\n"
            for j,r in enumerate(line):
                if j: text+=" "
                r["s"]=len(text);r["line"]=li;text+=r["text"];r["e"]=len(text)
        return text,lines
    def _box(s,x):
        if not isinstance(x,list) or len(x)<4: return None
        v=[fnum(t) for t in x[:4]]
        return [min(v[0],v[2]),min(v[1],v[3]),max(v[0],v[2]),max(v[1],v[3])]
    def _annots(s,pg):
        arr=s.res(pg.get("Annots")) or []
        if isinstance(arr,dict): arr=[arr]
        out=[]
        for a in arr:
            d=s.res(a)
            if not isinstance(d,dict) or (d.get("Subtype") or "") in("Popup","Link","Widget","Screen"): continue
            q=s.res(d.get("QuadPoints"));quads=[]
            if isinstance(q,list) and len(q)>=8:
                v=[fnum(t) for t in q]
                for i in range(0,len(v)-7,8):
                    xs,ys=v[i:i+8:2],v[i+1:i+8:2];quads.append([min(xs),min(ys),max(xs),max(ys)])
            ink=s.res(d.get("InkList"))
            out.append({"subtype":d.get("Subtype") or "unknown","rect":s._box(s.res(d.get("Rect"))),"quads":quads,
                "color":hexcol(s.res(d.get("C"))),"author":txtof(d.get("T")),"created":txtof(d.get("M")),
                "contents":txtof(d.get("Contents")),"nm":txtof(d.get("NM")),"subject":txtof(d.get("Subj")),
                "in_reply_to":("obj:%s"%d["IRT"].n) if isinstance(d.get("IRT"),Ref) else txtof(d.get("IRT")),
                "ink_strokes":len(ink) if isinstance(ink,list) else None})
        return out
    def anchor(s,pg,an):
        """Map annotation geometry to verbatim page text [char_start,char_end)."""
        text,runs=pg.get("text",""),pg.get("runs",[])
        boxes=an.get("quads") or ([an["rect"]] if an.get("rect") else [])
        miss={"quote":None,"char_start":None,"char_end":None,"precision":"none"}
        if not text.strip(): return dict(miss,method="no_text_layer")
        if not boxes: return dict(miss,method="no_geometry")
        sel=[];trim=False
        for x0,y0,x1,y1 in boxes:
            for r in runs:
                ry0,ry1=r["y"]-0.28*r["size"],r["y"]+0.82*r["size"]
                if min(ry1,y1)-max(ry0,y0)<=0.30*(ry1-ry0): continue
                chw=max(0.5*r["size"],0.1);rex=r["x"]+len(r["text"])*chw
                if min(rex,x1)-max(r["x"],x0)<=0.6*chw: continue
                a,b=r["s"],r["e"]
                if r["x"]+1.0<x0: k=int((min(x0,rex)-r["x"])/chw);a=min(b,r["s"]+max(k,0));trim=True
                if rex-1.0>x1: k=int((x1-r["x"])/chw);b=max(a,r["s"]+max(k,1));trim=True
                if b>a: sel.append((a,b,r))
        if not sel: return dict(miss,method="geometry_miss")
        sel.sort();a=max(0,min(sel[0][0],len(text)));b=max(a,min(max(t[1] for t in sel),len(text)))
        full=all(r["x"]>=bx[0]-3 and r["x"]+len(r["text"])*0.5*r["size"]<=bx[2]+3 for bx in boxes for _a,_b,r in sel)
        return {"quote":text[a:b],"char_start":a,"char_end":b,
                "method":"quad_overlap" if an.get("quads") else "rect_overlap",
                "precision":"exact_run" if not trim else ("trimmed" if full else "approx_char"),
                "n_runs":len(sel),"multiline":len({t[2]["line"] for t in sel})>1}
    def near_line(s,pg,rect):
        """Fallback anchor for point-like annotations (sticky note, ink, stamp)."""
        miss={"quote":None,"char_start":None,"char_end":None,"precision":"none"}
        if not rect: return dict(miss,method="no_geometry")
        if not pg.get("lines"): return dict(miss,method="no_text_layer")
        px,py=(rect[0]+rect[2])/2.0,(rect[1]+rect[3])/2.0;best=None;bd=1e18
        for line in pg["lines"]:
            for r in line:
                dd=abs(r["y"]-py)+0.02*abs(r["x"]-px)
                if dd<bd: best,bd=r,dd
        if not best: return dict(miss,method="no_text_layer")
        return {"quote":best["text"],"char_start":best["s"],"char_end":best["e"],"method":"nearest_line",
                "precision":"adjacent_line","distance_pt":round(bd,1)}
def xmltext(s):
    return re.sub(r"<[^>]+>","",s).replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"').replace("&apos;","'")
def docx(path,max_chars=2000000):
    """Word comments anchored by commentRange offsets + highlighted runs."""
    out={"text":"","comments":[],"highlights":[],"errors":[]}
    try: zf=zipfile.ZipFile(path)
    except Exception as e: out["errors"].append({"stage":"zip","error":repr(e)});return out
    try: doc=zf.read("word/document.xml").decode("utf-8","replace")
    except KeyError: out["errors"].append({"stage":"document.xml","error":"missing"});return out
    pos=0;starts={};ends={};hl=[];buf=[]
    for m in re.finditer(r"<w:r(?:\s[^>]*)?>(.*?)</w:r>|<w:commentRange(Start|End)[^>]*w:id=\"(\d+)\"",doc,re.S):
        if m.group(2): (starts if m.group(2)=="Start" else ends)[int(m.group(3))]=pos;continue
        body=m.group(1);hm=re.search(r"<w:highlight[^>]*w:val=\"([^\"]+)\"",body)
        t=xmltext("".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>",body,re.S)))
        if not t: continue
        if hm: hl.append({"text":t,"offset":pos,"color":hm.group(1)})
        buf.append(t);pos+=len(t)
        if pos>max_chars: out["errors"].append({"stage":"text","error":"char_cap"});break
    text="".join(buf);out["text"]=text;out["highlights"]=hl
    if "word/comments.xml" in zf.namelist():
        try:
            for m in re.finditer(r"<w:comment\s([^>]*)>(.*?)</w:comment>",zf.read("word/comments.xml").decode("utf-8","replace"),re.S):
                at,bd=m.group(1),m.group(2)
                ci=re.search(r"w:id=\"(\d+)\"",at);ci=int(ci.group(1)) if ci else -1
                au=re.search(r"w:author=\"([^\"]*)\"",at);dt=re.search(r"w:date=\"([^\"]*)\"",at)
                a,b=starts.get(ci),ends.get(ci);q=text[a:b] if a is not None and b is not None and b>a else None
                out["comments"].append({"id":ci,"author":au.group(1) if au else None,"created":dt.group(1) if dt else None,
                    "contents":xmltext(" ".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>",bd,re.S))).strip(),
                    "anchor":{"quote":q,"char_start":a,"char_end":b,"method":"commentRange" if q else "range_missing",
                              "precision":"exact_range" if q else "none"}})
        except Exception as e: out["errors"].append({"stage":"comments","error":repr(e)})
    return out
def csvrows(path,max_rows=5000):
    try:
        with open(path,"r",encoding="utf-8-sig",errors="replace",newline="") as fh:
            return [{(k or "").strip():(v or "").strip() for k,v in row.items()} for i,row in enumerate(csv.DictReader(fh)) if i<max_rows]
    except Exception: return []
def plain(path,max_chars=1500000):
    try: return Path(path).read_text(encoding="utf-8",errors="replace")[:max_chars]
    except OSError: return ""
def walk(root):
    root=Path(root)
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                yield p
def html(path,max_chars=1000000):
    return {"text":xmltext(plain(path,max_chars)),"errors":[]}
def xlsx(path,max_chars=200000):
    out={"text":"","errors":[]}
    try: zf=zipfile.ZipFile(path)
    except Exception as e: out["errors"].append({"stage":"zip","error":repr(e)});return out
    try:
        parts=[]
        for n in zf.namelist():
            if n.startswith("xl/") and n.endswith(".xml"):
                raw=zf.read(n).decode("utf-8","replace")
                for m in re.finditer(r"<t(?:\s[^>]*)?>(.*?)</t>",raw,re.S):
                    parts.append(xmltext(m.group(1)))
        out["text"]=" ".join(parts)[:max_chars]
    except Exception as e: out["errors"].append({"stage":"parse","error":repr(e)})
    return out
