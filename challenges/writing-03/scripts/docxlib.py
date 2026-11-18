"""docxlib - material parsing, spec mining, fidelity metrics, minimal OOXML writer/probe. stdlib only."""
import re, shutil, subprocess, zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
HDR = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CTM = "application/vnd.openxmlformats-officedocument.wordprocessingml"
BD = ('<w:top w:val="single" w:sz="12"/><w:bottom w:val="single" w:sz="12"/>'
      '<w:left w:val="none"/><w:right w:val="none"/><w:insideH w:val="none"/>'
      '<w:insideV w:val="none"/>')
ORDER = ("page.size page.margin.top page.margin.bottom page.margin.left page.margin.right "
         "page.columns body.font body.font.eastasia body.size body.line_spacing body.align "
         "body.first_line_indent title.size heading.1.size heading.1.emphasis heading.2.size "
         "heading.2.emphasis heading.3.size heading.3.emphasis heading.1.font heading.2.font "
         "heading.3.font heading.numbering caption.size "
         "caption.figure.position caption.table.position table.style reference.style "
         "reference.hanging footer.page_number page.header toc.levels").split()
_DF = """page.size|A4
page.margin.top|2.54cm
page.margin.bottom|2.54cm
page.margin.left|2.54cm
page.margin.right|2.54cm
page.columns|1
body.font|Liberation Serif
body.font.eastasia|SimSun
body.size|12
body.line_spacing|1.5
body.align|both
body.first_line_indent|0cm
title.size|16
heading.1.size|14
heading.1.emphasis|bold
heading.2.size|12
heading.2.emphasis|bold italic
heading.3.size|12
heading.3.emphasis|italic
heading.1.font|inherit
heading.2.font|inherit
heading.3.font|inherit
heading.numbering|decimal
caption.size|10
caption.figure.position|below
caption.table.position|above
table.style|three-line
reference.style|author-year
reference.hanging|0.5cm
footer.page_number|center
page.header|none
toc.levels|0"""
DEF = dict((a, b) for a, b in (z.split("|") for z in _DF.split("\n")))
CNPT = {"初号": 42, "一号": 26, "小二": 18, "二号": 22, "三号": 16, "小三": 15,
        "四号": 14, "小四": 12, "五号": 10.5, "小五": 9}
FAMS = [("Liberation Serif", 0), ("Times New Roman", 0), ("Arial", 0), ("Calibri", 0),
        ("Cambria", 0), ("Georgia", 0), ("Garamond", 0), ("DejaVu Serif", 0),
        ("宋体", 1), ("SimSun", 1), ("黑体", 1), ("SimHei", 1), ("楷体", 1),
        ("KaiTi", 1), ("仿宋", 1), ("微软雅黑", 1), ("Microsoft YaHei", 1)]
CLS = re.compile(r"[,;，；。]|\.\s|\.\"|\"\s+[A-Z]")
REFS = [("GB/T 7714", "numeric"), ("IEEE", "numeric"), ("Vancouver", "numeric"),
        ("AMA", "numeric"), ("Nature", "numeric"), ("APA", "author-year"),
        ("Harvard", "author-year"), ("Chicago", "author-year"), ("MLA", "author-year"),
        ("著者-出版年", "author-year"), ("顺序编码", "numeric")]

def rt(p):
    d = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return d.decode(e)
        except (UnicodeDecodeError, LookupError):
            pass
    return d.decode("utf-8", "replace")

def nm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def sq(s):
    return re.sub(r"\s+", "", str(s or ""))

def nu(s, d=None):
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else d

def cmv(s):
    v = nu(s)
    if v is None:
        return None
    t = str(s).lower()
    return round(v / 10.0 if ("mm" in t or "毫米" in t) else v * 2.54 if "in" in t else v, 2)

def typ(p):
    p, e = Path(p), Path(p).suffix.lower()
    try:
        h = p.open("rb").read(8)
    except OSError:
        h = b""
    if h[:4] == b"%PDF":
        return "pdf"
    if h[:2] == b"PK":
        try:
            n = set(zipfile.ZipFile(p).namelist())
        except Exception:
            return "zip"
        return ("docx" if "word/document.xml" in n else "xlsx"
                if any(i.startswith("xl/") for i in n) else "zip")
    if h[:2] == b"\x89P":
        return "image"
    return {"md": "text", "markdown": "text", "txt": "text", "xml": "text", "bib": "text", 
            "csv": "csv", "tex": "tex", "cls": "tex", "sty": "tex", "json": "json",
            "png": "image", "jpg": "image", "jpeg": "image", "svg": "image",
            "tif": "image"}.get(e.lstrip("."), "other")

def pdft(p):
    ex = shutil.which("pdftotext")
    if not ex:
        return "", "pdftotext absent"
    o = Path(str(p) + ".txt")
    try:
        subprocess.run([ex, "-layout", str(p), str(o)], timeout=90,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if o.exists():
            return rt(o), ""
    except Exception as e:
        return "", "pdftotext failed: %s" % e
    return "", "no text layer (scanned?)"

def tex(t):
    b = t.split("\\begin{document}")[-1].split("\\end{document}")[0]
    b = re.sub(r"(?m)(?<!\\)%.*$", "", b)
    b = re.sub(r"\\(section|subsection|subsubsection)\*?\{([^}]*)\}",
               lambda m: "\n%s %s\n" % ("#" * {"section": 1, "subsection": 2,
                                               "subsubsection": 3}[m.group(1)], m.group(2)), b)
    b = re.sub(r"\\\[(.*?)\\\]", r"\n$$ \1 $$", b, flags=re.S)
    b = re.sub(r"\\begin\{(equation|align)\*?\}(.*?)\\end\{\1\*?\}", r"\n$$ \2 $$", b, flags=re.S)
    b = re.sub(r"\\(?:textbf|textit|emph|cite[pt]?|ref|label|text)\{([^}]*)\}", r"\1", b)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub( 
        r"\\(?:noindent|newpage|centering|small|large|bfseries|itshape)\b", "", b))

def mdb(t):
    B, L, i = [], t.splitlines(), 0
    while i < len(L):
        s = L[i].strip()
        if not s:
            i += 1
            continue
        loc, m = "L%04d" % (i + 1), None
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            B.append({"loc": loc, "kind": "heading", "level": len(m.group(1)),
                      "text": m.group(2).strip()})
            i += 1
            continue
        m = re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", s)
        if m:
            B.append({"loc": loc, "kind": "figure", "text": m.group(1).strip(),
                      "image": m.group(2).strip()})
            i += 1
            continue
        if s.startswith("$$") or s.startswith("\\["):
            e = "$$" if s.startswith("$$") else "\\]"
            buf, j = [], i
            while True:
                buf.append(L[j].strip().strip("$").strip("\\[]").strip())
                j += 1
                if j >= len(L) or L[j - 1].strip().endswith(e) and j > i:
                    break
            B.append({"loc": loc, "kind": "equation", "text": " ".join(x for x in buf if x)})
            i = j
            continue
        if s.startswith("|") and s.count("|") >= 2:
            rows, j = [], i
            while j < len(L) and L[j].strip().startswith("|"):
                v = L[j].strip()
                if not re.match(r"^[\s:\-|]+$", v):
                    rows.append([c.strip() for c in v.strip("|").split("|")])
                j += 1
            B.append({"loc": loc, "kind": "table", "text": "", "rows": rows})
            i = j
            continue
        m = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", s)
        if m:
            B.append({"loc": loc, "kind": "bullet", "text": m.group(1).strip()})
            i += 1
            continue
        buf, j = [s], i + 1
        while j < len(L) and L[j].strip() and not re.match( r"^(#|\||!\[|\$\$|\[|[-*+] |\d+[.)] )", L[j].strip()):
            buf.append(L[j].strip())
            j += 1
        B.append({"loc": loc, "kind": "para", "text": " ".join(buf)})
        i = j
    return B

def dxb(path):
    z = zipfile.ZipFile(path)
    b = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    B, ip, it = [], 0, 0
    for el in (list(b) if b is not None else []):
        if el.tag == W + "tbl":
            it += 1
            B.append({"loc": "t%04d" % it, "kind": "table", "text": "", "rows": [
                [nm("".join(t.text or "" for t in c.iter(W + "t"))) for c in r.findall(W + "tc")]
                for r in el.findall(W + "tr")]})
            continue
        if el.tag != W + "p":
            continue
        ip += 1
        t = nm("".join(a.text or "" for a in el.iter(W + "t")))
        if not t:
            continue
        st, lv, pp = "", 0, el.find(W + "pPr")
        if pp is not None:
            ps, ol = pp.find(W + "pStyle"), pp.find(W + "outlineLvl")
            st = (ps.get(W + "val") or "") if ps is not None else ""
            if ol is not None:
                try:
                    lv = int(ol.get(W + "val")) + 1
                except (TypeError, ValueError):
                    lv = 0
        k = st.lower()
        if re.search(r"heading|标题|head\d", k):
            kind, d = "heading", re.search(r"(\d)", k)
            lv = lv or (max(1, min(4, int(d.group(1)))) if d else 1)
        elif re.search(r"caption|题注", k) or re.match(r"^\s*(图|表|Figure|Fig\.?|Table)\s*\d+", t):
            kind = "caption"
        elif re.search(r"bibliograph|reference|参考文献", k) or re.match(r"^\[\d+\]", t):
            kind = "reference"
        elif "title" in k and len(t) < 300:
            kind = "title"
        else:
            kind = "para"
        r = {"loc": "p%04d" % ip, "kind": kind, "text": t}
        if kind == "heading":
            r["level"] = lv or 1
        B.append(r)
    d = z.read("word/document.xml").decode("utf-8", "replace")
    m = re.search(r"<w:sectPr.*?</w:sectPr>", d, re.S)
    return B, (m.group(0) if m else "")

def load(p):
    k = typ(p)
    if k == "docx":
        try:
            return k, dxb(p)[0], ""
        except Exception as e:
            return k, [], "docx parse error: %s" % e
    if k in ("text", "tex", "json", "csv", "other"):
        try:
            t = rt(p)
        except Exception as e:
            return k, [], "read error: %s" % e
        return k, mdb(tex(t) if k == "tex" else t), ""
    if k == "pdf":
        t, n = pdft(p)
        return k, mdb(t), n
    return k, [], "unsupported (%s)" % k

def rawq(path):
    k = typ(path)
    try:
        if k == "docx":
            z = zipfile.ZipFile(path)
            B, sec = dxb(path)
            return "\n".join([b.get("text") or "" for b in B] + 
                             [" | ".join(r) for b in B for r in b.get("rows") or []] + [sec] +
                             [z.read(n).decode("utf-8", "replace")
                              for n in z.namelist() if n.endswith(".xml")][:8])
        if k == "pdf":
            return pdft(path)[0]
        t = rt(path)
        return t + "\n" + tex(t) if k == "tex" else t
    except Exception:
        return ""

def canon(f, v):
    v = str(v).strip()
    if f == "page.size":
        m = re.search(r"(A4|A3|A5|B5|Letter|Legal)", v, re.I)
        return (m.group(1)[:1].upper() + m.group(1)[1:].lower()) if m else v
    if f.startswith("page.margin.") or f == "reference.hanging":
        c = cmv(v)
        return "%.2fcm" % c if c is not None else v
    if f == "body.first_line_indent":
        return "%gchars" % nu(v, 0) if re.search(r"char|字符", v) else ( "%.2fcm" % cmv(v) if cmv(v) is not None else v)
    if f in ("body.size", "title.size", "caption.size") or re.match(r"heading\.\d\.size", f):
        for a, b in CNPT.items():
            if a in v:
                return "%g" % b
        return "%g" % nu(v) if nu(v) is not None else v
    if f == "body.line_spacing":
        l = v.lower()
        if re.search(r"double|两倍|2倍", l):
            return "2"
        if re.search(r"one[- ]and[- ]a[- ]half|1\.5", l):
            return "1.5"
        if re.search(r"single|单倍", l):
            return "1"
        m = re.search(r"([\d.]+)\s*pt", l)
        return ("%gpt" % float(m.group(1))) if m else "%g" % nu(v, 1.5)
    if f in ("page.columns", "toc.levels"):
        return "%g" % nu(v, 0)
    if f == "body.align":
        for b, r in (("both", r"justif|两端|both"), ("center", r"cent|居中"), ("right", r"right|右"), ("left", r"left|左")):
            if re.search(r, v.lower()):
                return b
        return v
    if f in ("caption.figure.position", "caption.table.position"):
        return ("above" if re.search(r"above|over|上", v) else
                "below" if re.search(r"below|under|下", v) else v)
    if f == "footer.page_number":
        return ("center" if re.search(r"cent|居中|中间", v) else
                "right" if re.search(r"right|右", v) else
                "left" if re.search(r"left|左", v) else
                "none" if re.search(r"none|无", v) else v)
    if f == "page.header":
        return "none" if re.search(r"none|no header|无页眉|不要页眉", v) else v
    if f == "reference.style":
        for a, b in REFS:
            if a.lower() in v.lower():
                return a
        return v
    if f == "table.style":
        return "three-line" if re.search(r"three|三线", v, re.I) else v
    if f == "heading.numbering":
        return "decimal" if re.search(r"decimal|arabic|1\.1|阿拉伯|数字", v, re.I) else v
    return v

def _pos(s, a, b):
    for seg in (re.split(r"[,;，；。]| and (?=[A-Z])", s[b:b + 40])[0].lower(), re.split(CLS, s[:a])[-1].lower()):
        o = set(k for r, k in ((r"top|上", "top"), (r"bottom|下", "bottom"),
                               (r"left|左", "left"), (r"right|右", "right"))
                if re.search(r, seg))
        if re.search(r"top\s*(?:and|&|,)\s*bottom|上下|top/bottom", seg):
            o |= {"top", "bottom"}
        if re.search(r"left\s*(?:and|&|,)\s*right|左右|left/right", seg):
            o |= {"left", "right"}
        if o:
            return o
    return set()

def mine(text, src, name):
    out, q = [], ""

    def add(f, v):
        if v not in (None, ""):
            out.append({"field": f, "value": canon(f, v), "source": src,
                        "locator": "%s#L%04d" % (name, ln), "quote": q[:200]})

    for ln, raw in enumerate(text.splitlines(), 1):
        s = q = raw.strip()
        if len(s) < 4 or s.startswith(("<!--", "```")):
            continue
        l = s.lower()
        m = re.search(r"\b(A4|A3|A5|B5|Letter|Legal)\b", s)
        if m and re.search(r"paper|size|page|幅面|纸张|开本|版面", l):
            add("page.size", m.group(1))
        if re.search(r"two[- ]column|双栏|两栏", l):
            add("page.columns", 2)
        elif re.search(r"single[- ]column|one[- ]column|单栏", l):
            add("page.columns", 1)
        elif re.search(r"three[- ]column|三栏", l):
            add("page.columns", 3)
        if re.search(r"margin|边距|页边|白边", l):
            for mm in re.finditer(r"(\d+(?:\.\d+)?)\s*(cm|mm|in|厘米|毫米|英寸)\b", s, re.I):
                ps = _pos(s, mm.start(), mm.end())
                if not ps:
                    continue
                u, v = mm.group(2).lower(), float(mm.group(1))
                val = "%.2fcm" % (v if u in ("cm", "厘米") else
                                  v / 10.0 if u in ("mm", "毫米") else v * 2.54)
                for p in sorted(ps):
                    add("page.margin." + p, val)
        fam = next(((a, b) for a, b in sorted(FAMS, key=lambda z: -len(z[0]))
                    if re.search(re.escape(a), s, re.I)), None)
        if fam and re.search(r"font|typeface|字体|字形|body text|正文", l):
            add("body.font.eastasia" if fam[1] else "body.font", fam[0])
        if re.search(r"justif|两端对齐|\baligned\b|对齐", l) and \
                re.search(r"body|text|正文|paragraph|alignment", l):
            add("body.align", "both" if re.search(r"justif|两端", l) else
                "center" if re.search(r"cent|居中", l) else
                "right" if re.search(r"right|右", l) else "left")
        if re.search(r"line spac|行距|spacing|倍行", l):
            m = (re.search(r"(?:line spacing|行距|spacing)[^\d\n]{0,12}([\d.]+)", l) or 
                 re.search(r"([\d.]+)\s*(?:-?\s*line spac|倍行距|倍|lines?\b)", l))
            if m:
                add("body.line_spacing", m.group(1))
            elif re.search(r"double[- ]spac|两倍行距", l):
                add("body.line_spacing", "2")
            elif re.search(r"one[- ]and[- ]a[- ]half", l):
                add("body.line_spacing", "1.5")
            elif re.search(r"single[- ]spac|单倍行距", l):
                add("body.line_spacing", "1")
        for c in [z.strip().lower() for z in re.split(CLS, s)]:
            if not re.search(r"heading|标题|section|章节|level\s*[123]|级标题", c):
                continue
            lm = re.search(r"(?:level\s*([123])|([一二三123])\s*级标题|标题\s*([123])|h([123])\b)", c)
            lvl = None
            if lm:
                t = next(g for g in lm.groups() if g)
                lvl = {"一": 1, "二": 2, "三": 3}.get(t) or int(t)
            sz = re.search(r"([\d.]+)\s*(?:pt|磅)", c) or next(
                (re.search(r"(%s)" % re.escape(k), c) for k in CNPT if k in c), None)
            fam2 = next((a for a, b in sorted(FAMS, key=lambda z: -len(z[0]))
                         if re.search(re.escape(a), c, re.I)), None)
            if lvl and fam2:
                add("heading.%d.font" % lvl, fam2)
            if lvl and sz:
                add("heading.%d.size" % lvl, sz.group(1))
                e = [k for k, r in (("bold", r"bold|黑体|加粗|粗体"), ("italic", r"italic|斜体"))
                     if re.search(r, c)]
                add("heading.%d.emphasis" % lvl, " ".join(e) or "none")
            elif sz and re.search(r"section heading|一级标题", c):
                add("heading.1.size", sz.group(1))
        if re.search(r"caption|题注|图注|表注|图题|表题", l):
            zs = set(re.findall(r"([\d.]+)\s*(?:pt|磅)", l))
            cn = [k for k in CNPT if k in l]
            if len(zs) == 1:
                add("caption.size", zs.pop())
            elif cn:
                add("caption.size", CNPT[cn[0]])
            for c in [z.strip().lower() for z in re.split(CLS, s)]:
                if not re.search(r"caption|题注|图注|表注|图题|表题", c):
                    continue
                pos = ("below" if re.search(r"below|under|beneath|下方|下面|之下|下", c) else
                       "above" if re.search(r"above|over|上方|上面|之上|上", c) else None)
                if pos:
                    if re.search(r"fig|图", c):
                        add("caption.figure.position", pos)
                    if re.search(r"table|表", c):
                        add("caption.table.position", pos)
        if re.search(r"\btitle\b|题名|篇名|论文题目|文章标题", l):
            m = re.search(r"([\d.]+)\s*(?:pt|磅)", l)
            if m:
                add("title.size", m.group(1))
        if re.search(r"body|正文|text size|字号|font size", l):
            cn = [k for k in CNPT if k in l]
            zs = re.findall(r"([\d.]+)\s*(?:pt|磅)", l)
            if cn:
                add("body.size", CNPT[cn[0]])
            elif zs and not re.search(r"heading|标题|caption|题注|reference|参考文献", l):
                add("body.size", zs[0])
        if re.search(r"three[- ]line|三线表|no vertical", l):
            add("table.style", "three-line")
        m = re.search(r"(GB/T\s*7714|IEEE|Vancouver|AMA|Nature|APA|Harvard|Chicago|MLA|"
                      r"著者-出版年|顺序编码)", s, re.I)
        if m and re.search(r"reference|参考文献|引用|citation|文献", l):
            add("reference.style", m.group(1))
        m = (re.search(r"hanging indent[^\d]{0,12}([\d.]+)\s*(cm|mm|in|字符)?", l) or 
             re.search(r"悬挂缩进[^\d]{0,8}([\d.]+)\s*(cm|mm|字符)?", l))
        if m:
            add("reference.hanging", m.group(1) + (m.group(2) or "cm"))
        if re.search(r"page number|页码|footer|页脚", l):
            pos = ("center" if re.search(r"cent|居中|中间", l) else
                   "right" if re.search(r"right|右", l) else
                   "left" if re.search(r"left|左", l) else None)
            if pos:
                add("footer.page_number", pos)
        if re.search(r"no header|without header|无页眉|不设页眉", l):
            add("page.header", "none")
        if re.search(r"first[- ]line indent|首行缩进", l):
            m = re.search(r"([\d.]+)\s*(cm|mm|char|字符)", l)
            if m:
                add("body.first_line_indent", m.group(1) + m.group(2))
        if re.search(r"table of contents|\btoc\b|目录", l):
            m = re.search(r"(\d|three|two|one|一|二|三)\s*(?:levels?|级)", l)
            if m:
                add("toc.levels", {"three": 3, "two": 2, "一": 1, "二": 2, "三": 3}.get(
                    m.group(1), m.group(1)))
    return out

def tpl(path, src, name):
    """Spec items read straight from a docx template's sectPr/styles.xml."""
    out = []

    def add(f, v, loc, qt):
        out.append({"field": f, "value": canon(f, v), "source": src,
                    "locator": "%s#%s" % (name, loc), "quote": qt[:200]})

    try:
        z = zipfile.ZipFile(path)
        n = set(z.namelist())
        dx = z.read("word/document.xml").decode("utf-8", "replace")
        sx = z.read("word/styles.xml").decode("utf-8", "replace") if "word/styles.xml" in n else ""
    except Exception:
        return out
    sec = dx[dx.rfind("<w:sectPr"):] if "<w:sectPr" in dx else ""
    m = re.search(r"<w:pgSz[^>]*>", sec)
    if m:
        a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0)))
        w, h = int(a.get("w", 11906)), int(a.get("h", 16838))
        add("page.size", "A4" if abs(w - 11906) < 80 and abs(h - 16838) < 80 else
            "Letter" if abs(w - 12240) < 80 else "%dx%d" % (w, h), "sectPr/pgSz", m.group(0))
    m = re.search(r"<w:pgMar[^>]*>", sec)
    if m:
        a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0)))
        for k in ("top", "bottom", "left", "right"):
            if a.get(k, "").lstrip("-").isdigit():
                add("page.margin." + k, "%.2fcm" % (int(a[k]) / 1440 * 2.54),
                    "sectPr/pgMar@" + k, 'w:%s="%s"' % (k, a[k]))
    m = re.search(r"<w:cols[^>]*>", sec)
    if m:
        a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0)))
        if a.get("num"):
            add("page.columns", a["num"], "sectPr/cols", m.group(0))
    S = {}
    for mm in re.finditer(r"<w:style [^>]*>(.*?)</w:style>", sx, re.S):
        k = re.search(r'<w:name w:val="([^"]+)"', mm.group(1))
        if not k:
            continue
        d = {}
        for a, p in (("font", r'<w:rFonts[^>]*w:ascii="([^"]+)"'), ("ea", r'w:eastAsia="([^"]+)"'), 
                     ("sz", r'<w:sz w:val="(\d+)"'), ("line", r'<w:spacing[^>]*w:line="(\d+)"'),
                     ("hang", r'<w:ind[^>]*w:hanging="(\d+)"'), ("rule", r'w:lineRule="(\w+)"')):
            v = re.search(p, mm.group(1))
            if v:
                d[a] = v.group(1)
        S[k.group(1).strip().lower()] = d
    N = S.get("normal") or {}
    if N.get("font"):
        add("body.font", N["font"], "styles.xml[Normal]/rFonts", 'w:ascii="%s"' % N["font"])
    if N.get("ea"):
        add("body.font.eastasia", N["ea"], "styles.xml[Normal]/rFonts",
            'w:eastAsia="%s"' % N["ea"])
    if N.get("sz"):
        add("body.size", int(N["sz"]) / 2, "styles.xml[Normal]/sz", '<w:sz w:val="%s"/>' % N["sz"])
    if N.get("line"):
        add("body.line_spacing", round(float(N["line"]) / 240, 3) if
            N.get("rule", "auto") == "auto" else "%gpt" % (float(N["line"]) / 20),
            "styles.xml[Normal]/spacing", '<w:spacing w:line="%s"/>' % N["line"])
    for i in (1, 2, 3):
        h = S.get("heading %d" % i) or {}
        if h.get("sz"):
            add("heading.%d.size" % i, int(h["sz"]) / 2, "styles.xml[heading %d]/sz" % i,
                '<w:sz w:val="%s"/>' % h["sz"])
    c = S.get("caption") or {}
    if c.get("sz"):
        add("caption.size", int(c["sz"]) / 2, "styles.xml[caption]/sz", '<w:sz w:val="%s"/>' % c["sz"])
    b = S.get("bibliography") or {}
    if b.get("hang"):
        add("reference.hanging", "%.2fcm" % (int(b["hang"]) / 1440 * 2.54),
            "styles.xml[Bibliography]/ind", 'w:hanging="%s"' % b["hang"])
    return out

def units(bl):
    U = []
    for b in bl:
        if b.get("kind") == "table":
            if (b.get("caption") or "").strip():
                U.append((b.get("loc"), b["caption"]))
            for r in b.get("rows") or []:
                t = nm(" | ".join(r))
                if t.replace("|", "").strip():
                    U.append((b.get("loc"), t))
        elif (b.get("text") or "").strip():
            U.append((b.get("loc"), b["text"]))
    return U

NRX = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[%‰])?")
CRX = re.compile(r"\[\d+(?:\s*[-,–]\s*\d+)*\]|\(\s*[A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?,?\s*"
                 r"\d{4}[a-z]?\s*\)|(?:Figure|Fig\.?|Table|图|表)\s*\d+(?:[.\-]\d+)?"
                 r"|\bdoi:\S+|https?://\S+")

def nums(t):
    return [m.group(0).replace(" ", "") for m in NRX.finditer(t or "")]

def cites(t):
    return [nm(m.group(0)) for m in CRX.finditer(t or "")]

def fid(S, T):
    su, ou = units(S), units(T)
    blob = sq(" ".join(t for _, t in ou))
    have = set(sq(t) for _, t in ou)
    miss = [(l, t) for l, t in su if sq(t) not in have and sq(t) not in blob]
    a, b = Counter(nums(" ".join(t for _, t in su))), Counter(nums(" ".join(t for _, t in ou)))
    c, d = Counter(cites(" ".join(t for _, t in su))), Counter(cites(" ".join(t for _, t in ou)))
    ln = {k: v - b.get(k, 0) for k, v in a.items() if b.get(k, 0) < v}
    lc = {k: v - d.get(k, 0) for k, v in c.items() if d.get(k, 0) < v}
    return {"source_units": len(su), "output_units": len(ou), "matched_units": len(su) - len(miss), 
            "verbatim_ratio": round((len(su) - len(miss)) / len(su), 4) if su else 1.0,
            "missing_count": len(miss),
            "missing_units": [{"locator": l, "text": t[:160]} for l, t in miss[:20]],
            "source_chars": sum(len(t) for _, t in su), "output_chars": sum(len(t) for _, t in ou),
            "numbers_source": sum(a.values()), "numbers_output": sum(b.values()),
            "numbers_preserved": not ln, "numbers_lost": dict(list(ln.items())[:20]),
            "citations_source": sum(c.values()), "citations_output": sum(d.values()),
            "citations_preserved": not lc, "citations_lost": dict(list(lc.items())[:20])}

def x(s):
    return (str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def GM(sm):
    tw = lambda c: int(round((c or 0) / 2.54 * 1440))
    sz = lambda p: max(2, int(round(float(nu(p, 12)) * 2)))
    lb, fi = str(sm.get("body.line_spacing") or "1.5"), str(
        sm.get("body.first_line_indent") or "0cm")
    pg = {"A4": (11906, 16838), "A3": (16838, 23811), "A5": (8391, 11906),
          "Letter": (12240, 15840)}.get(str(sm.get("page.size")), (11906, 16838))
    g = {"font": sm.get("body.font") or "Liberation Serif",
         "ea": sm.get("body.font.eastasia") or "SimSun", "sz": sz(sm.get("body.size")),
         "title": sz(sm.get("title.size") or 16),
         "h": {i: sz(sm.get("heading.%d.size" % i) or (16 if i == 1 else 12)) for i in (1, 2, 3)},
         "cap": sz(sm.get("caption.size") or 10),
         "line": int(round(nu(lb, 1.5) * (20 if "pt" in lb else 240))),
         "rule": "exact" if "pt" in lb else "auto",
         "ind": int(round(nu(fi, 0) * float(nu(sm.get("body.size"), 12)) * 20)) if "char" in fi
         else tw(cmv(fi) or 0), "hang": tw(cmv(sm.get("reference.hanging")) or 0.5),
         "align": sm.get("body.align") or "both", "pgW": pg[0], "pgH": pg[1],
         "mt": tw(cmv(sm.get("page.margin.top"))), "mb": tw(cmv(sm.get("page.margin.bottom"))),
         "ml": tw(cmv(sm.get("page.margin.left"))), "mr": tw(cmv(sm.get("page.margin.right"))),
         "cols": max(1, int(nu(sm.get("page.columns"), 1) or 1)),
         "pgpos": sm.get("footer.page_number") or "center",
         "toc": int(nu(sm.get("toc.levels"), 0) or 0),
         "emph": {i: str(sm.get("heading.%d.emphasis" % i) or "") for i in (1, 2, 3)},
         "hf": {i: str(sm.get("heading.%d.font" % i) or "inherit") for i in (1, 2, 3)}}
    return g

def R(g, sz, b=False, i=False, ea=None):
    ea = ea or g["ea"]
    return ('<w:rPr><w:rFonts w:ascii="%s" w:hAnsi="%s" w:eastAsia="%s" w:cs="%s"/>%s%s'
            '<w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>'
            % (x(g["font"]), x(g["font"]), x(ea), x(g["font"]),
               "<w:b/><w:bCs/>" if b else "", "<w:i/><w:iCs/>" if i else "", sz, sz))

def SP(b, a, ln, r):
    return '<w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="%s"/>' % (b, a, ln, r)

def ST(sid, name, ppr, rpr, d=False):
    return ('<w:style w:type="paragraph" w:styleId="%s"%s><w:name w:val="%s"/>'
            '<w:basedOn w:val="Normal"/><w:qFormat/>%s%s</w:style>'
            % (sid, ' w:default="1"' if d else "", x(name), ppr, rpr))

def styles(g):
    bp = SP(0, 120, g["line"], g["rule"]) + '<w:jc w:val="%s"/>' % g["align"] + \
        ('<w:ind w:firstLine="%d"/>' % g["ind"] if g["ind"] else "")
    o = [XD + '<w:styles %s><w:docDefaults><w:rPrDefault>%s</w:rPrDefault><w:pPrDefault>'
         '<w:pPr>%s</w:pPr></w:pPrDefault></w:docDefaults>' % (HDR, R(g, g["sz"]), bp),
         ST("Normal", "Normal", bp, R(g, g["sz"]), True)]
    for i in (1, 2, 3):
        e = g["emph"][i].lower()
        o.append(ST("Heading%d" % i, "heading %d" % i, SP(240, 120, g["line"], g["rule"]) +
                    '<w:keepNext/><w:jc w:val="left"/><w:outlineLvl w:val="%d"/>' % (i - 1),
                    R(g, g["h"][i], "bold" in e, "italic" in e,
                      None if g["hf"][i] == "inherit" else g["hf"][i])))
    o += [ST("Title", "Title", SP(240, 240, g["line"], g["rule"]) + '<w:jc w:val="center"/>',
             R(g, g["title"], True)),
          ST("Caption", "caption", SP(60, 120, 240, "auto") + '<w:jc w:val="center"/>',
             R(g, g["cap"])),
          ST("Bibliography", "Bibliography", SP(0, 60, 240, "auto") +
             '<w:ind w:left="%d" w:hanging="%d"/>' % (g["hang"], g["hang"]), R(g, g["sz"])),
          ST("TableText", "Table Text", SP(0, 0, 240, "auto"), R(g, max(16, g["sz"] - 2))),
          ST("TOCHeading", "TOC Heading", SP(240, 120, g["line"], g["rule"]), R(g, g["h"][1], True)),
          '<w:style w:type="table" w:styleId="ThreeLine"><w:name w:val="Three Line"/>'
          '<w:tblPr><w:tblBorders>%s</w:tblBorders></w:tblPr></w:style></w:styles>' % BD]
    return "".join(o)

def P(style, text, g, jc=None, bm=None, keep=False):
    ppr = ('<w:pStyle w:val="%s"/>' % style if style else "") + ("<w:keepNext/>" if keep else "") \
        + ('<w:jc w:val="%s"/>' % jc if jc else "")
    h = '<w:bookmarkStart w:id="%d" w:name="_Toc9%05d"/>' % (bm, bm) if bm is not None else ""
    e = '<w:bookmarkEnd w:id="%d"/>' % bm if bm is not None else ""
    return ('<w:p><w:pPr>%s</w:pPr>%s<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>%s</w:p>'
            % (ppr, h, R(g, g["sz"]), x(text), e))

def TBL(rows, g):
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return ""
    nc, w = max(len(r) for r in rows) or 1, int(9600 / max(1, max(len(r) for r in rows) or 1))
    o = ['<w:tbl><w:tblPr><w:tblStyle w:val="ThreeLine"/><w:tblW w:w="5000" w:type="pct"/>'
         '<w:jc w:val="center"/><w:tblBorders>%s</w:tblBorders></w:tblPr><w:tblGrid>' % BD
         + '<w:gridCol w:w="%d"/>' % w * nc + '</w:tblGrid>']
    for ri, r in enumerate(rows):
        o.append("<w:tr>%s" % ("<w:trPr><w:tblHeader/></w:trPr>" if ri == 0 else ""))
        for ci in range(nc):
            bd = ('<w:tcBorders><w:bottom w:val="single" w:sz="8"/></w:tcBorders>'
                  if ri == 0 and len(rows) > 1 else "")
            o.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr><w:p><w:pPr>'
                     '<w:pStyle w:val="TableText"/><w:jc w:val="%s"/></w:pPr><w:r>%s'
                     '<w:t xml:space="preserve">%s</w:t></w:r></w:p></w:tc>'
                     % (w, bd, "center" if (ri == 0 or ci == 0) else "left",
                        R(g, max(16, g["sz"] - 2)), x(r[ci] if ci < len(r) else "")))
        o.append("</w:tr>")
    return "".join(o) + "</w:tbl>"

def build_docx(path, blocks, sm, title=""):
    g, body, bm = GM(sm), [], 0
    toc = g["toc"] > 0 and any(b.get("kind") == "heading" for b in blocks)
    if toc:
        body.append('<w:p><w:pPr><w:pStyle w:val="TOCHeading"/></w:pPr><w:r>%s'
                    '<w:t>Contents</w:t></w:r></w:p>' % R(g, g["h"][1], True))
        body.append('<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:fldChar '
                    'w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText '
                    'xml:space="preserve"> TOC \\o "1-%d" \\h \\z \\u </w:instrText></w:r>'
                    '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>%s</w:t></w:r>'
                    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
                    % (min(3, g["toc"]), "Right-click and update the field."))
    for b in blocks:
        k, t = b.get("kind"), (b.get("text") or "")
        if k == "heading":
            body.append(P("Heading%d" % max(1, min(3, int(b.get("level") or 1))), t, g, bm=bm))
            bm += 1
        elif k == "table":
            cap, up = b.get("caption"), (sm.get("caption.table.position") or "above") == "above"
            if cap and up:
                body.append(P("Caption", cap, g, jc="center", keep=True))
            body.append(TBL(b.get("rows") or [], g))
            if cap and not up:
                body.append(P("Caption", cap, g, jc="center"))
        elif k == "figure":
            up = (sm.get("caption.figure.position") or "below") == "above"
            if t and up:
                body.append(P("Caption", t, g, jc="center", keep=True))
            if b.get("image"):
                body.append(P("Normal", b["image"], g, jc="center"))
            if t and not up:
                body.append(P("Caption", t, g, jc="center"))
        elif k == "equation":
            body.append(P("Normal", t, g, jc="center"))
        elif k == "caption":
            body.append(P("Caption", t, g, jc="center"))
        elif k == "reference":
            body.append(P("Bibliography", t, g))
        elif k == "title":
            body.append(P("Title", t, g))
        else:
            body.append(P("Normal", t, g))
    if not body:
        body.append(P("Normal", title or "", g))
    pos = {"center": "center", "right": "right", "left": "left"}.get(g["pgpos"], "center")
    ftr = (XD + '<w:ftr %s><w:p><w:pPr><w:jc w:val="%s"/></w:pPr><w:r><w:fldChar '
           'w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve">'
           ' PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
           '<w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>'
           % (HDR, pos))
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter1"/><w:pgSz w:w="%d" '
            'w:h="%d"/><w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" w:header="850" '
            'w:footer="992" w:gutter="0"/><w:cols w:num="%d" w:space="425"%s/></w:sectPr>'
            % (g["pgW"], g["pgH"], g["mt"], g["mr"], g["mb"], g["ml"], g["cols"],
               ' w:sep="1"' if g["cols"] > 1 else ""))
    ct = (XD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
          'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' +
          "".join('<Override PartName="/word/%s.xml" ContentType="%s.%s+xml"/>'
                  % (a, CTM, b) for a, b in (("document", "document.main"), ("styles", "styles"),
                                             ("footer1", "footer"))) + "</Types>")
    rels = (XD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships"><Relationship Id="rId1" Type="%s/officeDocument" Target="word/'
            'document.xml"/></Relationships>' % RNS)
    drels = (XD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
             'relationships"><Relationship Id="rIdStyles" Type="%s/styles" Target="styles.xml"/>'
             '<Relationship Id="rIdFooter1" Type="%s/footer" Target="footer1.xml"/>'
             '</Relationships>' % (RNS, RNS))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", XD + '<w:document %s><w:body>%s%s</w:body></w:document>'
                   % (HDR, "".join(body), sect))
        z.writestr("word/styles.xml", styles(g))
        z.writestr("word/footer1.xml", ftr)
        z.writestr("word/_rels/document.xml.rels", drels)
    return {"paragraphs": len(body), "headings": bm, "toc": bool(toc), 
            "tables": sum(1 for b in blocks if b.get("kind") == "table"),
            "fonts": [g["font"], g["ea"]]}

def probe(path):
    z = zipfile.ZipFile(path)
    n = set(z.namelist())
    dx = z.read("word/document.xml").decode("utf-8", "replace")
    sx = z.read("word/styles.xml").decode("utf-8", "replace") if "word/styles.xml" in n else ""
    ft = z.read("word/footer1.xml").decode("utf-8", "replace") if "word/footer1.xml" in n else ""
    o = {"parts": sorted(n), "has_document": "word/document.xml" in n,
         "has_styles": "word/styles.xml" in n}
    m = re.search(r"<w:pgSz[^>]*>", dx)
    a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0))) if m else {}
    w, h = int(a.get("w", 0)), int(a.get("h", 0))
    o["page_size"] = ("A4" if abs(w - 11906) < 80 and abs(h - 16838) < 80 else
                      "Letter" if abs(w - 12240) < 80 else "%dx%d" % (w, h))
    m = re.search(r"<w:pgMar[^>]*>", dx)
    a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0))) if m else {}
    o["margins_cm"] = {k: round(int(a[k]) / 1440 * 2.54, 2) for k in
                       ("top", "bottom", "left", "right") if k in a}
    m = re.search(r"<w:cols[^>]*>", dx)
    a = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0))) if m else {}
    o["columns"] = int(a.get("num", 1))

    def st(sid):
        mm = re.search(r'<w:style [^>]*w:styleId="%s".*?</w:style>' % sid, sx, re.S)
        s, d = (mm.group(0) if mm else ""), {}
        for k, p in (("sz", r'<w:sz w:val="(\d+)"'), ("font", r'w:ascii="([^"]+)"'), 
                     ("line", r'<w:spacing[^>]*w:line="(\d+)"'), ("rule", r'w:lineRule="(\w+)"'),
                     ("outline", r'<w:outlineLvl w:val="(\d)"')):
            v = re.search(p, s)
            d[k] = v.group(1) if v else None
        d["sz_pt"] = int(d["sz"]) / 2 if d["sz"] else None
        d["line"] = int(d["line"]) if d["line"] else None
        d["outline"] = int(d["outline"]) if d["outline"] else None
        d["bold"], d["italic"] = "<w:b/>" in s, "<w:i/>" in s
        return d

    o["normal"] = st("Normal")
    o["body_line_multiple"] = (round(o["normal"]["line"] / 240.0, 2)
                               if o["normal"]["line"] and o["normal"]["rule"] == "auto" else None)
    o["headings"] = {i: st("Heading%d" % i) for i in (1, 2, 3)}
    o["caption"] = st("Caption")
    o["styles_used"] = sorted(set(re.findall(r'w:pStyle w:val="([^"]+)"', dx)))
    o["runs"], o["runs_with_font"] = len(re.findall(r"<w:r>", dx)), len(re.findall(r"<w:rFonts ", dx))
    o["para_count"], o["table_count"] = len(re.findall(r"<w:p>", dx)), len(re.findall(r"<w:tbl>", dx))
    o["tables_three_line"] = '<w:insideV w:val="none"' in dx and '<w:top w:val="single"' in dx
    o["footer_page_field"] = bool(re.search(r">\s*PAGE\s*<", ft))
    o["footer_align"] = (re.search(r'<w:jc w:val="(\w+)"', ft).group(1)
                         if re.search(r'<w:jc w:val="(\w+)"', ft) else None)
    o["toc_field"] = "TOC \\o" in dx
    o["bytes"] = Path(path).stat().st_size
    return o

def md_render(blocks, title=""):
    L = ["# " + title, ""] if title else []
    for b in blocks:
        k, t = b.get("kind"), b.get("text") or ""
        if k == "heading":
            L += ["#" * (max(1, min(6, int(b.get("level") or 1))) + (1 if title else 0)) + " " + t, ""]
        elif k == "table":
            rows = [r for r in b.get("rows") or [] if any(r)]
            if not rows:
                continue
            n = max(len(r) for r in rows)
            rows = [list(r) + [""] * (n - len(r)) for r in rows]
            if b.get("caption") and (b.get("cap_pos") or "above") == "above":
                L += ["*" + b["caption"] + "*", ""]
            L += ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
            L += ["| " + " | ".join(r) + " |" for r in rows[1:]] + [""]
            if b.get("caption") and b.get("cap_pos") == "below":
                L += ["*" + b["caption"] + "*", ""]
        elif k == "figure":
            L += (["[" + b["image"] + "]", ""] if b.get("image") else []) + \
                 (["*" + t + "*", ""] if t else [])
        elif k == "equation":
            L += ["$$ " + t + " $$", ""]
        elif k == "caption":
            L += ["*" + t + "*", ""]
        elif k == "title":
            L += (["# " + t, ""] if not title else [t, ""])
        else:
            L += [t, ""]
    return "\n".join(L).rstrip() + "\n"

def preview(docx_path, outdir, workdir):
    """Real PDF when a converter exists; None otherwise (caller records the fallback)."""
    outdir, ex = Path(outdir).resolve(), shutil.which("soffice") or shutil.which("libreoffice")
    docx_path, prof = Path(docx_path).resolve(), (Path(workdir).resolve() / "lo_prof")
    note = ""
    if ex:
        try:
            subprocess.run([ex, "-env:UserInstallation=file://%s" % prof, "--headless",
                            "--norestore", "--convert-to", "pdf", "--outdir", str(outdir),
                            str(docx_path)], timeout=150, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            note = "soffice failed: %s" % e
        made, tgt = outdir / (Path(docx_path).stem + ".pdf"), outdir / "preview.pdf"
        if made.exists() and made.read_bytes()[:5] == b"%PDF-":
            if made != tgt:
                try:
                    made.replace(tgt)
                except OSError:
                    pass
            fonts, pf = [], shutil.which("pdffonts")
            if pf:
                try:
                    r = subprocess.run([pf, str(tgt)], capture_output=True, timeout=60)
                    fonts = [l.split()[0] for l in r.stdout.decode("utf-8", "replace")
                             .splitlines()[2:] if l.strip()][:8]
                except Exception:
                    pass
            return {"path": "preview.pdf", "pages": len(re.findall( 
                rb"/Type\s*/Page[^s]", tgt.read_bytes())), "fonts": fonts,
                "engine": Path(ex).name, "note": note}
        note = note or "converter produced no PDF"
    else:
        note = "no soffice/libreoffice in PATH"
    return {"path": None, "pages": None, "fonts": [], "engine": None, "note": note}
