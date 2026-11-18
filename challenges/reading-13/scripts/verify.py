#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nanopub-forge source layer: discovery, readers, checks. Stdlib only.

Imported by main.py; standalone: python3 -B scripts/verify.py --output DIR [--patch]
"""
import argparse, csv, hashlib, html, json, re, shutil, subprocess, sys, zipfile, zlib
from pathlib import Path

VERSION, SCHEMA = "1.0.0", "np-assertion/1"
WS = re.compile(r"\s+")
GOOD = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
IMG = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg"}
TEXT_EXT = (".md", ".txt", ".pdf", ".docx", ".csv", ".tsv", ".xlsx", ".json", ".jsonl", ".html", ".htm", ".tex") + tuple(IMG)
TR = str.maketrans({"\u00ad": "", "\u00a0": " ", "\ufb01": "fi", "\ufb02": "fl", "\u2018": "'", "\u2019": "'",
                    "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2022": " ",
                    "\ufeff": "", "\u2044": "/"})
REL_OK = {"increases", "decreases", "inhibits", "activates", "associated_with", "binds", "encodes",
          "expressed_in", "mediates", "causes", "differs_between", "has_part", "uses_method", "is_a", "other_relation"}
READ_OK = {"directly_read", "inferred", "undetermined"}
UNSET = object()

def collapse(s):
    return WS.sub(" ", s or "").strip()

def normkey(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())

def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)

def quality(t):
    return len(GOOD.findall(t or "")) / (len(WS.sub("", t or "")) or 1)

# -------------------------------------------------------------- discovery
def load_case(indir):
    for c in [indir / "case.json"] + sorted(p for p in indir.glob("**/*case*.json") if p.is_file()):
        if c.is_file():
            try:
                return json.loads(c.read_text(encoding="utf-8", errors="replace")), c, None
            except Exception as e:
                return {}, c, str(e)[:300]
    return {}, None, None

def read_task(indir):
    for p in [indir / "task.md", indir / "TASK.md"] + sorted(indir.glob("*.md")):
        if p.is_file():
            try:
                return read_plain(p)
            except Exception:
                continue
    return ""

def walk_first(node, keys, depth=0):
    if depth > 4:
        return ""
    if isinstance(node, dict):
        for k, v in node.items():
            if normkey(k) in keys and isinstance(v, str) and v.strip():
                return collapse(v)
        vals = list(node.values())
    elif isinstance(node, list):
        vals = node
    else:
        return ""
    for v in vals:
        r = walk_first(v, keys, depth + 1)
        if r:
            return r
    return ""

def as_paths(node, acc=None, depth=0):
    acc = [] if acc is None else acc
    if depth > 6:
        return acc
    if isinstance(node, str):
        if len(node) < 300 and "\n" not in node and re.search(r"\.[A-Za-z0-9]{1,5}$", node):
            acc.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            as_paths(v, acc, depth + 1)
    elif isinstance(node, list):
        for v in node:
            as_paths(v, acc, depth + 1)
    return acc

def discover(indir, case):
    files, gaps, seen = [], [], set()
    for decl in as_paths(case):
        rel = decl[7:] if decl.startswith("/input/") else (decl[6:] if decl.startswith("input/") else decl)
        hit = next((c for c in (indir / rel, indir / Path(rel).name, indir / "artifacts" / Path(rel).name) if c.is_file()), None)
        if not hit:
            gaps.append({"what": decl, "why_needed": "declared in case metadata but absent under input dir",
                         "impact": "cannot be read; see pending_human"})
        elif hit.resolve() not in seen:
            seen.add(hit.resolve())
            files.append((hit, "case_field"))
    for p in sorted(indir.rglob("*")):
        try:
            if (not p.is_file() or p.name.startswith(".") or p.name.lower() in ("case.json", "task.md")
                    or p.stat().st_size > 60 * 1024 * 1024 or p.resolve() in seen):
                continue
        except Exception:
            continue
        if p.suffix.lower() in TEXT_EXT:
            seen.add(p.resolve())
            files.append((p, "scan"))
    return files, gaps

def pick_contract(case):
    def walk(n, d=0):
        if d > 4 or not isinstance(n, (dict, list)):
            return UNSET
        if isinstance(n, dict):
            for k, v in n.items():
                if normkey(k) in ("outputcontract", "contract", "outputschema", "requiredoutput", "outputfields"):
                    return v
            vals = list(n.values())
        else:
            vals = n
        for v in vals:
            r = walk(v, d + 1)
            if r is not UNSET:
                return r
        return UNSET
    r = walk(case)
    return None if r is UNSET else r

def pick_case_id(case, indir):
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "name"):
            if isinstance(case.get(k), str) and case[k].strip():
                return case[k]
        for holder in (case.get("case"), case.get("task"), case.get("meta"), case.get("input")):
            if isinstance(holder, dict):
                for kk in ("case_id", "id", "name"):
                    if isinstance(holder.get(kk), str) and holder[kk].strip():
                        return holder[kk]
    return indir.name or None

# ---------------------------------------------------------------- readers
def read_plain(p):
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            return Path(p).read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return Path(p).read_bytes().decode("utf-8", "replace")

def norm_page(raw):
    t = (raw or "").replace("\r\n", "\n").replace("\r", "\n").translate(TR)
    t = re.sub(r"-\s*\n\s*(?=[a-z])", "", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    t = re.sub(r"\n{2,}", "\n\n", t)
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()

def read_office(p, ext):
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if ext == ".docx":
            out = []
            for n in sorted(x for x in names if re.match(r"word/(document|footnotes|endnotes)\.xml$", x)):
                for blk in re.findall(r"<w:p[\s>].*?</w:p>", z.read(n).decode("utf-8", "replace"), re.S):
                    t = html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", blk, re.S)))
                    if t.strip():
                        out.append(t)
            out = out or [""]
            return ["\n\n".join(out[i:i + 40]) for i in range(0, len(out), 40)], []
        shared = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
                  for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)] \
            if "xl/sharedStrings.xml" in names else []
        pages = []
        for n in sorted(x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
            rows = []
            for rm in re.finditer(r"<row[^>]*>(.*?)</row>", z.read(n).decode("utf-8", "replace"), re.S):
                cells = []
                for attrs, body in re.findall(r"<c([^>]*)>(.*?)</c>", rm.group(1), re.S):
                    v = re.search(r"<v>(.*?)</v>", body, re.S) or re.search(r"<t[^>]*>(.*?)</t>", body, re.S)
                    if not v:
                        continue
                    x = html.unescape(v.group(1))
                    cells.append(shared[int(x)] if ('t="s"' in attrs and x.isdigit() and int(x) < len(shared)) else x)
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            if rows:
                pages.append("\n".join(rows))
        return pages or [""], ["table_like:positional cells"]

def read_csv_like(p):
    txt = read_plain(p)
    first = (txt.splitlines() or [""])[0]
    d = "\t" if (Path(p).suffix.lower() == ".tsv" or ("\t" in first and "," not in first)) else (";" if first.count(";") > first.count(",") else ",")
    rows = [r for r in csv.reader(txt.splitlines(), delimiter=d) if any(x.strip() for x in r)] or [[""]]
    hdr = [collapse(c) for c in rows[0]]
    lines = ["; ".join("%s=%s" % (hdr[i] if i < len(hdr) and hdr[i] else "c%d" % (i + 1), collapse(v))
                       for i, v in enumerate(r) if collapse(v)) for r in (rows[1:] or [rows[0]])]
    return ["\n".join(x for x in lines if x)], ["table_like:%d cols" % len(hdr)]

def _unescape(b):
    out, i, esc = [], 0, {110: 10, 114: 13, 116: 9, 98: 8, 102: 12}
    while i < len(b):
        c = b[i]
        if c == 92 and i + 1 < len(b):
            n, i = b[i + 1], i + 2
            if n in esc:
                out.append(esc[n])
            elif n in (40, 41, 92):
                out.append(n)
            elif 48 <= n <= 55:
                d = bytes([n])
                while i < len(b) and len(d) < 3 and 48 <= b[i] <= 55:
                    d += bytes([b[i]])
                    i += 1
                out.append(int(d, 8) & 255)
            elif n not in (10, 13):
                out.append(n)
        else:
            out.append(c)
            i += 1
    return bytes(bytearray(out)).decode("latin-1")

_TOK = re.compile(rb"\((?:[^()\\]|\\.|\([^()\\]*\))*\)|<[0-9A-Fa-f\s]{2,}>|\bBT\b|\bET\b|\bTj\b|\bTJ\b|\bTd\b|\bTD\b|\bT\*\b|\bTm\b|\bTf\b|\bTL\b")

def _content_text(c):
    seg, pend = [], []
    for m in _TOK.finditer(c):
        s = m.group(0)
        if s[:1] == b"(":
            pend.append(_unescape(s[1:-1]))
        elif s[:1] == b"<":
            h = re.sub(rb"\s", b"", s[1:-1])
            try:
                pend.append(bytes.fromhex((h + b"0" * (len(h) % 2)).decode()).decode("latin-1"))
            except Exception:
                pass
        elif s in (b"Tj", b"TJ"):
            seg.append("".join(pend))
            pend = []
        elif s in (b"Td", b"TD", b"T*", b"Tm", b"ET"):
            seg += ["".join(pend), "\n"] if pend else ["\n"]
            pend = []
    if pend:
        seg.append("".join(pend))
    return re.sub(r"\n{3,}", "\n\n", "".join(seg))

def _objects(data):
    return {int(m.group(1)): m.group(2) for m in re.finditer(rb"(\d+)\s+0\s+obj\b(.*?)endobj", data, re.S)}

def _stream(data, num, objs):
    b = objs.get(num) or b""
    m = re.search(rb"stream\r?\n", b)
    e = b.rfind(b"endstream") if m else -1
    if not m or e < 0:
        return b""
    raw, head = b[m.end():e], b[:m.start() + 240]
    if b"FlateDecode" in head:
        for f in (zlib.decompress, lambda x: zlib.decompressobj().decompress(x)):
            try:
                return f(raw)
            except Exception:
                continue
        return b""
    return b"" if b"/Filter" in head else raw

def _page_ids(objs):
    def kids(n, d=0):
        if d > 8:
            return []
        m = re.search(rb"/Kids\s*\[(.*?)\]", objs.get(n) or b"", re.S)
        return [n] if not m else [x for r in re.findall(rb"(\d+)\s+0\s+R", m.group(1)) for x in kids(int(r), d + 1)]

    roots = [n for n, b in objs.items() if re.search(rb"/Type\s*/Pages", b) and b"/Kids" in b]
    kid = {int(x) for n in roots for x in re.findall(rb"(\d+)\s+0\s+R", (re.search(rb"/Kids\s*\[(.*?)\]", objs[n], re.S) or [None, b""])[1])}
    order = [x for t in sorted(n for n in roots if n not in kid) for x in kids(t)]
    return [n for n in order if re.search(rb"/Type\s*/Page[^s]", objs.get(n) or b"")]

def pdf_internal(data):
    objs, pages = _objects(data), []
    ids = _page_ids(objs)
    if not ids:
        parts = [_content_text(s) for s in (_stream(data, n, objs) for n in objs) if s and b"BT" in s]
        return ([norm_page("\n\n".join(parts))], ["page_number_unavailable"]) if parts else ([], [])
    for n in ids:
        b = objs.get(n) or b""
        m = re.search(rb"/Contents\s*\[(.*?)\]", b, re.S)
        ref = re.search(rb"/Contents\s+(\d+)\s+0\s+R", b)
        nums = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", m.group(1))] if m else ([int(ref.group(1))] if ref else [])
        pages.append(norm_page("".join(_content_text(_stream(data, x, objs)) for x in nums)))
    return pages, []

def pdf_external(path):
    out = {}
    exe = shutil.which("pdftotext")
    try:
        r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=150)
        if r.returncode == 0 and r.stdout:
            out["pdftotext"] = r.stdout.decode("utf-8", "replace").split("\f")
    except Exception:
        pass
    for mod in ("pypdf", "PyPDF2"):
        try:
            out["pypdf"] = [(pg.extract_text() or "") for pg in __import__(mod).PdfReader(str(path)).pages]
            break
        except Exception:
            continue
    return out

def pdf_meta(data):
    meta = {"title": None, "authors": [], "year": None, "doi": None}
    m = re.search(rb"/Title\s*\(([^)]{3,240})\)", data[:200000])
    if m:
        meta["title"] = collapse(_unescape(m.group(1)))
    m = re.search(rb"/CreationDate\s*\(D:(\d{4})", data[:200000])
    meta["year"] = int(m.group(1)) if m else None
    return meta

def extract(path):
    path = Path(path)
    ext = path.suffix.lower()
    info = {"extractor": "none", "pages": [], "flags": [], "meta": {}}
    try:
        head = path.open("rb").read(8)
    except Exception:
        head = b""
    if head[:4] == b"%PDF" or ext == ".pdf":
        data = path.read_bytes()
        try:
            cand = {"pdf-internal": pdf_internal(data)}
        except Exception:
            cand = {"pdf-internal": ([], ["pdf_internal_failed"])}
        cand.update({k: ([norm_page(p) for p in v], []) for k, v in pdf_external(path).items()})
        best, sc0, flags, name = [], -1.0, [], "none"
        for k, (pgs, fl) in cand.items():
            sc = sum(len(GOOD.findall(p)) for p in pgs if quality(p) >= 0.55) + {"pdftotext": 3, "pypdf": 2}.get(k, 0)
            if sc > sc0:
                best, sc0, flags, name = pgs, sc, list(fl), k
        while len(best) > 1 and not best[-1].strip(): best.pop()
        flags += ["page_%d_no_text_layer" % (i + 1) for i, p in enumerate(best) if len(GOOD.findall(p)) < 50 or quality(p) < 0.55]
        if not best or sc0 <= 3:
            flags.append("no_text_layer_detected")
        meta = pdf_meta(data)
        meta["doi"] = next((m.group(0).rstrip(".,;)") for p in best[:3] for m in [re.search(r"\b10\.\d{4,9}/[^\s\"<>]{3,60}", p)] if m), None)
        info.update(extractor=name, pages=best or [""], flags=flags, meta=meta)
    elif ext in (".docx", ".xlsx"):
        pg, fl = read_office(path, ext)
        info.update(extractor="zip-xml", pages=pg, flags=fl)
    elif ext in (".csv", ".tsv"):
        pg, fl = read_csv_like(path)
        info.update(extractor="python-csv", pages=pg, flags=fl)
    elif ext in (".html", ".htm"):
        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", read_plain(path))
        info.update(extractor="stdlib-html", pages=[norm_page(html.unescape(re.sub(r"<[^>]+>", " ", t)))])
    elif ext in (".json", ".jsonl"):
        info.update(extractor="plain-json", pages=[norm_page(read_plain(path))])
    elif ext in IMG:
        info.update(flags=["image_no_ocr"])
    elif ext in (".doc", ".ppt", ".pptx", ".xls"):
        info.update(flags=["legacy_or_unsupported_office_format"])
    else:
        info.update(extractor="plain", pages=[norm_page(read_plain(path))])
    return info

# ---------------------------------------------------------------- checks
def canon_of(a):
    return "|".join([collapse((a.get("subject") or {}).get("text")).lower(), a.get("relation") or "",
                     a.get("polarity") or "", collapse((a.get("object") or {}).get("text")).lower(),
                     ";".join(sorted(collapse(c).lower() for c in (a.get("condition") or [])))])

def np_id_of(a):
    return "urn:nanopub:" + hashlib.sha256(canon_of(a).encode("utf-8")).hexdigest()[:32]

def poke(node, ptr):
    cur = node
    for part in [p for p in str(ptr).split("/") if p]:
        if isinstance(cur, dict):
            cur = cur.get(part, UNSET)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return UNSET
    return cur

def check(outdir, patch=False):
    out = Path(outdir)
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    dump = json.loads((out / "extracted_text.json").read_text(encoding="utf-8")) if (out / "extracted_text.json").is_file() else {"sources": []}
    pages, fresh = {}, {}
    for s in dump.get("sources") or []:
        pages[s.get("source_id")] = [p.get("text") or "" for p in (s.get("pages") or [])]
        f = Path(str(s.get("path") or ""))
        if f.is_file() and f.suffix.lower() in TEXT_EXT:
            try:
                fresh[s.get("source_id")] = extract(f)["pages"]
            except Exception:
                pass
    rep = {"assertions": len(res.get("assertions") or []), "status": res.get("status"),
           "quote_vs_dump": {"checked": 0, "ok": 0}, "quote_vs_original": {"checked": 0, "ok": 0},
           "failures": [], "vocabulary": [], "ids_mismatched": [], "fields_missing": [],
           "contract_missing": [], "pass": False}
    for a in res.get("assertions") or []:
        aid = a.get("assertion_id")
        for e in a.get("evidence") or []:
            q, sid, pg = collapse(e.get("quote")), e.get("source_id"), (e.get("location") or {}).get("page")
            for kind, pool in (("dump", pages.get(sid) or []), ("original", fresh.get(sid) or [])):
                if kind == "original" and not pool:
                    continue
                t = pool[pg - 1] if isinstance(pg, int) and 0 < pg <= len(pool) else None
                ok = bool(t is not None and q and q in collapse(t))
                rep["quote_vs_" + kind]["checked"] += 1
                rep["quote_vs_" + kind]["ok"] += ok
                if not ok:
                    rep["failures"].append({"assertion_id": aid, "source_id": sid, "page": pg, "quote": q[:100], "where": kind})
        if a.get("relation") not in REL_OK or a.get("readability") not in READ_OK:
            rep["vocabulary"].append(aid)
        rep["fields_missing"] += [f for f in ("assertion_text", "subject", "relation", "evidence", "confidence") if not a.get(f)]
        if a.get("np_id") and np_id_of(a) != a["np_id"]:
            rep["ids_mismatched"].append(aid)
    echo = res.get("output_contract_echo")
    rep["contract_missing"] = [p for p in res.get("output_contract_keys") or [] if poke(echo, p) is UNSET]
    rep["pass"] = not (rep["failures"] or rep["contract_missing"] or rep["vocabulary"] or rep["ids_mismatched"])
    write_json(out / "verification.json", rep)
    if patch:
        res.setdefault("verification", {})["external"] = rep
        write_json(out / "result.json", res)
    return rep

def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="Re-check result.json: every evidence quote against "
                                 "extracted_text.json and the original file, plus contract and id checks.")
    ap.add_argument("--output", default="/app/output", help="dir with result.json")
    ap.add_argument("--patch", action="store_true", help="also update result.json")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args(argv)
    try:
        rep = check(a.output, a.patch)
        print(json.dumps({k: rep[k] for k in ("assertions", "status", "quote_vs_dump", "quote_vs_original", "contract_missing", "pass")}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)[:300], "hint": "run scripts/main.py first"}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
