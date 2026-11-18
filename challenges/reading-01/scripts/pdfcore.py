"""PDF 词/坐标抽取后端。仅标准库；poppler 为可选增强，缺失自动降级到内置解析器。
API: probe() / poppler_bbox() / poppler_images() / builtin_pages()。原点=页面左上，y 向下。
"""
import html, re, shutil, subprocess, zlib
from pathlib import Path

TOOLS = ("pdftotext", "pdfinfo", "pdftoppm", "pdfimages", "mutool", "tesseract")
_WS = b" \t\r\n\f\x00"
_OBJ = re.compile(rb"(?<![0-9])(\d{1,9})\s+(\d{1,5})\s+obj\b")
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
        b"(": b"(", b")": b")", b"\\": b"\\"}


def probe():
    return {t: (shutil.which(t) or "") for t in TOOLS}


def _run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001
        return -1, b"", str(e).encode("utf-8", "replace")


_PG = re.compile(rb'<page width="(-?[\d.]+)" height="(-?[\d.]+)">')
_WD = re.compile(rb'<word xMin="(-?[\d.]+)" yMin="(-?[\d.]+)" xMax="(-?[\d.]+)" '
                 rb'yMax="(-?[\d.]+)">(.*?)</word>', re.S)


def poppler_bbox(path, timeout=240):
    """poppler -bbox-layout：词级 bbox（首选后端）。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext 不存在"
    rc, out, err = _run([exe, "-bbox-layout", "-q", "-enc", "UTF-8", str(path), "-"], timeout)
    if rc != 0 or b"<page" not in out:
        return None, "bbox-layout rc=%s %s" % (rc, err[:120].decode("utf-8", "replace"))
    marks, pages = list(_PG.finditer(out)), []
    for i, m in enumerate(marks):
        s, e = m.end(), (marks[i + 1].start() if i + 1 < len(marks) else len(out))
        ws = []
        for w in _WD.findall(out[s:e]):
            t = html.unescape(w[4].decode("utf-8", "replace")).strip()
            if t:
                x0, x1 = sorted((float(w[0]), float(w[2])))
                y0, y1 = sorted((float(w[1]), float(w[3])))
                ws.append({"t": t, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                           "sz": round(max(y1 - y0, 1.0), 2)})
        pages.append({"no": i + 1, "w": float(m.group(1)), "h": float(m.group(2)),
                      "words": ws, "images": [], "geometry": "bbox"})
    return pages, ""


def _tok(s, i):
    """PDF 词法：-> (value, next)。value ∈ dict/list/bytes/number/('R',num,gen)。"""
    n = len(s)
    while i < n and s[i] in _WS:
        i += 1
    if i >= n:
        return None, i
    c = s[i:i + 1]
    if c == b"%":
        while i < n and s[i] not in b"\r\n":
            i += 1
        return _tok(s, i)
    if s[i:i + 2] == b"<<":
        i += 2
        d = {}
        for _ in range(4000):
            while i < n and s[i] in _WS:
                i += 1
            if i >= n or s[i:i + 2] == b">>":
                return d, min(i + 2, n)
            k, i = _tok(s, i)
            v, i = _tok(s, i)
            if isinstance(k, bytes):
                d[k.decode("latin-1").lstrip("/")] = v
        return d, i
    if c == b"[":
        i += 1
        a = []
        for _ in range(20000):
            while i < n and s[i] in _WS:
                i += 1
            if i >= n or s[i:i + 1] == b"]":
                return a, min(i + 1, n)
            v, i = _tok(s, i)
            a.append(v)
        return a, i
    if c == b"/":
        j = i + 1
        while j < n and s[j] not in _WS and s[j:j + 1] not in b"()<>[]{}/%":
            j += 1
        return s[i:j], j
    if c == b"(":
        j, out, depth = i + 1, bytearray(), 1
        while j < n:
            ch = s[j:j + 1]
            if ch == b"\\":
                nx = s[j + 1:j + 2]
                if nx in _ESC:
                    out += _ESC[nx]
                    j += 2
                    continue
                m2 = re.match(rb"[0-7]{1,3}", s[j + 1:j + 4])
                if m2:
                    out.append(int(m2.group(0), 8) & 0xFF)
                    j += 1 + len(m2.group(0))
                    continue
                j += 2
                continue
            if ch == b"(":
                depth += 1
            elif ch == b")":
                depth -= 1
                if depth == 0:
                    return bytes(out), j + 1
            out += ch
            j += 1
        return bytes(out), j
    if c == b"<":
        j = s.find(b">", i)
        if j < 0:
            return b"", n
        hx = re.sub(rb"[^0-9A-Fa-f]", b"", s[i + 1:j])
        try:
            return bytes.fromhex((hx + (b"0" if len(hx) % 2 else b"")).decode()), j + 1
        except ValueError:
            return b"", j + 1
    m = re.match(rb"[+-]?\d*\.?\d+", s[i:i + 40])
    if m and m.group(0) not in (b".", b"-", b"+"):
        txt, j = m.group(0), i + len(m.group(0))
        if b"." in txt:
            try:
                return float(txt), j
            except ValueError:
                return 0.0, j
        m2 = re.match(rb"\s+(\d{1,5})\s+R\b", s[j:j + 20])
        if m2:
            return ("R", int(txt), int(m2.group(1))), j + m2.end()
        return int(txt), j
    m = re.match(rb"[A-Za-z*'\"]+", s[i:i + 40])
    return ((m.group(0), i + len(m.group(0))) if m else (None, i + 1))


def _flate(b):
    for fn in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x),
               lambda x: zlib.decompress(x, -15)):
        try:
            return fn(b)
        except Exception:  # noqa: BLE001
            continue
    return b""


class MiniPDF:
    """对象扫描式读取器：不依赖 xref，支持 ObjStm 与常见过滤器；遇坏对象跳过。"""

    def __init__(self, data):
        self.d, self.o = data, {}
        self.encrypted = b"/Encrypt" in data
        self._scan()

    def _scan(self):
        d = self.d
        for m in _OBJ.finditer(d):
            num, st = int(m.group(1)), m.end()
            si, eo = d.find(b"stream", st), d.find(b"endobj", st)
            if si >= 0 and (eo < 0 or si < eo):  # 跳过 stream 二进制区，避免误切对象
                es = d.find(b"endstream", si)
                eo = d.find(b"endobj", len(d) if es < 0 else es)
            self.o[num] = d[st:eo if eo > 0 else len(d)]
        for body in list(self.o.values()):
            if b"/ObjStm" in body[:600]:
                try:
                    self._objstm(body)
                except Exception:  # noqa: BLE001
                    pass

    def _objstm(self, body):
        i = body.find(b"stream")
        if i < 0:
            return
        dct = _tok(body, max(body.find(b"<<"), 0))[0]
        if not isinstance(dct, dict):
            return
        raw = self._stream_from(body, dct)
        first = int(dct.get("First") or 0)
        head = raw[:first].split()
        for k in range(int(dct.get("N") or 0)):
            try:
                onum, off = int(head[2 * k]), int(head[2 * k + 1])
            except (IndexError, ValueError):
                return
            end = int(head[2 * k + 3]) + first if 2 * k + 3 < len(head) else len(raw)
            self.o.setdefault(onum, raw[first + off:end])

    def resolve(self, v, depth=0):
        while isinstance(v, tuple) and v[0] == "R" and depth < 10:
            if self.o.get(v[1]) is None:
                return None
            v, depth = _tok(self.o[v[1]], 0)[0], depth + 1
        return v

    def _filter(self, dct, raw):
        filters = self.resolve(dct.get("Filter")) or []
        for f in (filters if isinstance(filters, list) else [filters]):
            if (f[1:] if isinstance(f, bytes) else b"") in (b"FlateDecode", b"Fl"):
                raw = _flate(raw)
            else:
                return b""  # 图像编码（DCT/JPX/CCITT）等非文本流
        return raw

    def _stream_from(self, body, dct):
        i = body.find(b"stream")
        if i < 0:
            return b""
        j = i + 6
        while j < len(body) and body[j:j + 1] in b"\r\n":
            j += 1
        ln = dct.get("Length")
        if isinstance(ln, tuple) and ln[0] == "R":
            try:
                ln = int(_tok(self.o.get(ln[1], b""), 0)[0])
            except (TypeError, ValueError):
                ln = None
        if isinstance(ln, int) and 0 < ln <= len(body) - j:
            return self._filter(dct, body[j:j + ln])
        e = body.find(b"endstream", j)
        return self._filter(dct, body[j:e if e > 0 else len(body)])

    def stream(self, num):
        body = self.o.get(num)
        if not isinstance(body, bytes):
            return b""
        dct = _tok(body, max(body.find(b"<<"), 0))[0]
        return self._stream_from(body, dct if isinstance(dct, dict) else {})

    def page_dicts(self):
        pages, root = [], None
        for m in re.finditer(rb"/Root\s+(\d{1,9})\s+(\d{1,5})\s+R", self.d):
            root = int(m.group(1))
        cat = self.resolve(("R", root, 0)) if root is not None else None
        if isinstance(cat, dict):
            stack, seen = [cat.get("Pages")], set()
            while stack:
                node = self.resolve(stack.pop(0))
                if not isinstance(node, dict) or id(node) in seen:
                    continue
                seen.add(id(node))
                kids = self.resolve(node.get("Kids"))
                if node.get("Type") == b"/Page" or kids is None:
                    pages.append(node)
                elif isinstance(kids, list):
                    stack = list(kids) + stack
        if not pages:  # 回退：按对象号顺序取 /Type /Page
            for num in sorted(self.o):
                body = self.o[num]
                if re.search(rb"/Type\s*/Page(?![s\w])", body[:800]):
                    dct = _tok(body, max(body.find(b"<<"), 0))[0]
                    if isinstance(dct, dict):
                        pages.append(dct)
        return pages


def _mmul(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F)


def _uni(hx):
    h = hx.decode().strip()
    try:
        return bytes.fromhex(h if len(h) % 2 == 0 else "0" + h).decode("utf-16-be", "ignore")
    except ValueError:
        return ""


def _cmap(s):
    """ToUnicode CMap -> {code: text}（bfchar + 标量 bfrange）。"""
    m = {}
    for blk in re.findall(rb"beginbfchar(.*?)endbfchar", s, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            m[int(a, 16)] = _uni(b)
    for blk in re.findall(rb"beginbfrange(.*?)endbfrange", s, re.S):
        for a, b, c in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            lo, hi, base = int(a, 16), int(b, 16), int(c, 16)
            m.update({lo + k: chr(base + k) for k in range(min(hi - lo, 4096) + 1)})
    return m


def _font(pdf, fobj):
    d = pdf.resolve(fobj)
    if not isinstance(d, dict):
        return None
    tu = None
    ref = d.get("ToUnicode")
    if isinstance(ref, tuple) and ref[0] == "R":
        try:
            tu = _cmap(pdf.stream(ref[1]))
        except Exception:  # noqa: BLE001
            tu = None
    wid, fc, two = {}, 0, d.get("Subtype") == b"/Type0"
    if not two:
        fc = pdf.resolve(d.get("FirstChar"))
        fc = fc if isinstance(fc, int) else 0
        for k, v in enumerate(pdf.resolve(d.get("Widths")) or []):
            if isinstance(v, (int, float)):
                wid[fc + k] = float(v)
    return {"two": two, "tu": tu, "w": wid, "dw": 1000.0 if wid else 500.0}


def _decode(bs, f):
    if f is None:
        return bs.decode("latin-1")
    tu, out = f["tu"], []
    codes = [((bs[i] << 8) | bs[i + 1]) for i in range(0, len(bs) - 1, 2)] if f["two"] else list(bs)
    for c in codes:
        u = tu.get(c) if tu else None
        out.append(u if u is not None else (chr(c) if c < 0x110000 else ""))
    return "".join(out)


def _walk(pdf, content, res, fonts, ctm, depth, words, want_text):
    """解释内容流：维护 tm/ctm、字号与字距，累计带坐标的词。"""
    st = {"fs": 12.0, "tc": 0.0, "tw": 0.0, "tz": 100.0, "tl": 0.0, "f": None}
    tm = tlm = (1, 0, 0, 1, 0, 0)
    stack, cache, cur, ops = [], {}, [], []
    cur_y = cur_x0 = cur_x1 = 0.0

    def flush():
        nonlocal cur
        t = "".join(cur).strip()
        if t:
            words.append({"t": t, "_y": cur_y, "_x": cur_x0, "_x1": cur_x1, "_sz": st["fs"]})
        cur = []
    i, n = 0, len(content)
    while i < n:
        v, j = _tok(content, i)
        if j <= i:
            i += 1
            continue
        i = j
        if v is None:
            continue
        if not isinstance(v, bytes) or v.startswith(b"/"):
            ops.append(v)
            continue
        op = v
        try:
            if op == b"q":
                stack.append(ctm)
            elif op == b"Q":
                ctm = stack.pop() if stack else ctm
            elif op == b"cm" and len(ops) >= 6:
                ctm = _mmul(tuple(float(x) for x in ops[-6:]), ctm)
            elif op == b"BT":
                tm = tlm = (1, 0, 0, 1, 0, 0)
            elif op == b"Tf" and len(ops) >= 2:
                if not isinstance(ops[-1], bytes):
                    st["fs"] = float(ops[-1])
                kk = ops[-2].decode("latin-1").lstrip("/") if isinstance(ops[-2], bytes) else str(ops[-2])
                if kk not in cache:
                    cache[kk] = _font(pdf, fonts.get(kk))
                st["f"] = cache[kk]
            elif op in (b"TL", b"Tc", b"Tw", b"Tz") and ops:
                st[{b"TL": "tl", b"Tc": "tc", b"Tw": "tw", b"Tz": "tz"}[op]] = float(ops[-1])
            elif op in (b"Td", b"TD") and len(ops) >= 2:
                if op == b"TD":
                    st["tl"] = -float(ops[-1])
                tm = tlm = _mmul((1, 0, 0, 1, float(ops[-2]), float(ops[-1])), tlm)
            elif op == b"Tm" and len(ops) >= 6:
                tm = tlm = tuple(float(x) for x in ops[-6:])
            elif op == b"T*":
                tm = tlm = _mmul((1, 0, 0, 1, 0, -st["tl"]), tlm)
            elif op in (b"Tj", b"'", b'"', b"TJ"):
                if op in (b"'", b'"'):
                    if op == b'"' and len(ops) >= 3:
                        st["tw"], st["tc"] = float(ops[-3]), float(ops[-2])
                    tm = tlm = _mmul((1, 0, 0, 1, 0, -st["tl"]), tlm)
                items = ops[-1] if op == b"TJ" else [ops[-1]]
                for it in (items if isinstance(items, list) else [items]):
                    if isinstance(it, (int, float)):
                        tm = _mmul((1, 0, 0, 1, -it / 1000.0 * st["fs"] * st["tz"] / 100.0, 0), tm)
                        if -it > 180:
                            flush()
                        continue
                    if not isinstance(it, bytes) or not want_text:
                        continue
                    f, nw = st["f"], (2 if (st["f"] and st["f"]["two"]) else 1)
                    codes = [((it[i] << 8) | it[i + 1]) if nw == 2 else it[i]
                             for i in range(0, len(it) - nw + 1, nw)]
                    adv = sum((f["w"].get(c, f["dw"]) if f else 500.0) / 1000.0 * st["fs"] + st["tc"]
                              + (st["tw"] if nw == 1 and c == 32 else 0.0) for c in codes) * st["tz"] / 100.0
                    m = _mmul(tm, ctm)
                    x0, y0 = m[4], m[5]
                    x1 = m[0] * adv + m[4]
                    sz = abs(st["fs"] * (m[3] or 1)) or st["fs"]
                    if cur and (abs(y0 - cur_y) > max(2.0, 0.35 * sz) or x0 - cur_x1 > max(1.6, 0.28 * sz)):
                        flush()
                    if not cur:
                        cur_x0, cur_y = x0, y0
                    cur.append(_decode(it, st["f"]))
                    cur_x1 = x1
                    if len(cur) > 40:
                        flush()
                    tm = _mmul((1, 0, 0, 1, adv, 0), tm)
            elif op == b"Do" and ops and depth < 3:
                name = ops[-1]
                xo = pdf.resolve((res or {}).get("XObject")) or {}
                ref = xo.get(name.decode("latin-1")) if isinstance(name, bytes) else None
                od = pdf.resolve(ref)
                if isinstance(od, dict) and od.get("Subtype") == b"/Form" and isinstance(ref, tuple):
                    sub = pdf.resolve(od.get("Resources")) or res
                    mtx = pdf.resolve(od.get("Matrix")) or [1, 0, 0, 1, 0, 0]
                    _walk(pdf, pdf.stream(ref[1]), sub, pdf.resolve((sub or {}).get("Font")) or fonts,
                          _mmul(tuple(float(x) for x in mtx[:6]), ctm), depth + 1, words, want_text)
            elif op == b"BI":
                e = content.find(b"EI", i)
                i = e + 2 if e > 0 else n
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            pass
        ops = []
    flush()
    return words


def builtin_pages(path):
    """纯标准库 PDF 解析（无 poppler 时的兜底后端）。"""
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        return None, "读取失败: %s" % e
    if not data.startswith(b"%PDF"):
        return None, "非 PDF(无 %PDF 头)"
    try:
        pdf = MiniPDF(data)
        pds = pdf.page_dicts()
    except Exception as e:  # noqa: BLE001
        return None, "解析失败: %s" % e
    if not pds:
        return None, "无页面对象(损坏/加密)"
    pages = []
    for idx, dct in enumerate(pds):
        try:
            mb = pdf.resolve(dct.get("MediaBox")) or [0, 0, 612, 792]
            vals = [float(pdf.resolve(v) or 0) for v in mb[:4]]
            w, h = abs(vals[2] - vals[0]) or 612.0, abs(vals[3] - vals[1]) or 792.0
            res = pdf.resolve(dct.get("Resources")) or {}
            fonts = pdf.resolve(res.get("Font")) or {}
            cont = dct.get("Contents")
            refs = cont if isinstance(cont, list) else [cont]
            content = b"".join(pdf.stream(r[1]) for r in refs if isinstance(r, tuple) and r[0] == "R")
            words = []
            _walk(pdf, content, res, fonts, (1, 0, 0, 1, 0, 0), 0, words, True)
            out = [{"t": wd["t"], "x0": round(wd["_x"], 2),
                    "y0": round(h - wd["_y"] - 0.78 * max(wd["_sz"], 1.0), 2),
                    "x1": round(max(wd["_x1"], wd["_x"] + 0.5), 2),
                    "y1": round(h - wd["_y"] + 0.22 * max(wd["_sz"], 1.0), 2),
                    "sz": round(max(wd["_sz"], 1.0), 2)} for wd in words]
            pages.append({"no": idx + 1, "w": w, "h": h, "words": out, "images": [], "geometry": "bbox"})
        except Exception as e:  # noqa: BLE001
            pages.append({"no": idx + 1, "w": 612.0, "h": 792.0, "words": [], "images": [],
                          "geometry": "bbox", "error": str(e)})
    return pages, ""


_IMGTAG = re.compile(rb"<image[^>]*>")


def poppler_images(path, timeout=180):
    """pdftohtml -xml：图片放置框（XML 坐标系，调用方按页宽归一化）。"""
    exe = shutil.which("pdftohtml")
    if not exe:
        return None, "pdftohtml 不存在"
    rc, out, _ = _run([exe, "-xml", "-stdout", "-q", "-i", str(path)], timeout)
    if rc != 0 or b"<page" not in out:
        return None, "pdftohtml rc=%s" % rc
    pages = []
    for i, chunk in enumerate(out.split(b"<page")[1:]):
        dim = dict(re.findall(rb'(height|width)="(\d+)"', chunk[:300]))
        imgs = []
        for tag in _IMGTAG.findall(chunk):
            g = dict(re.findall(rb'(top|left|width|height)="(-?\d+)"', tag))
            if len(g) == 4:
                l, t = float(g["left"]), float(g["top"])
                imgs.append({"x0": l, "y0": t, "x1": l + float(g["width"]), "y1": t + float(g["height"])})
        pages.append({"no": i + 1, "w": float(dim.get(b"width", 0)), "h": float(dim.get(b"height", 0)),
                      "images": imgs})
    return pages, ""
