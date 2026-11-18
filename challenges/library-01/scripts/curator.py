#!/usr/bin/env python3
"""Ingest core: scan/hash/sniff/text, metadata provenance, hash dedup, version chains, curated copies.
No CLI, no result.json; problems go to ERR/DEG/PH/OPS."""
import csv, difflib, hashlib, json, os, re, shutil, time, unicodedata, zipfile, zlib
from datetime import datetime, timezone
from pathlib import Path

VER, SK, T0, CH, MX, MF = "1.0.0", "research-library-curator", time.time(), 1 << 20, 2_000_000, 4000
BUD = [32_000_000]
CG = {}
for _c, _s in (("02_documents", ".pdf .doc .docx .odt .rtf .md .txt .tex"), ("03_tables", ".csv .tsv .xlsx .xls .ods"),
               ("04_figures", ".png .jpg .jpeg .tif .tiff .svg .eps .gif"), ("05_code", ".py .r .m .ipynb .do"),
               ("06_archives", ".zip .tar .gz .tgz .7z .rar .bz2")):
    CG.update({e: _c for e in _s.split()})
INSTR = ["LC-MS", "GC-MS", "ICP-MS", "HPLC", "XRD", "SEM", "TEM", "NMR", "FTIR", "Raman", "MicroCT", "PCR"]
VW = ["final", "draft", "revised", "copy", "backup", "定稿", "最终", "修订", "草稿", "副本", "备份"]
VN = {"final": 900.0, "定稿": 900.0, "最终": 900.0, "revised": 500.0, "修订": 500.0, "draft": 100.0, "草稿": 100.0}
FA = {"title": ["title", "标题", "题名"], "authors": ["authors", "author", "作者"], "year": ["year", "年份"],
      "project": ["project", "项目", "项目名"], "project_code": ["project_code", "project_id", "项目号", "项目编号"],
      "instrument": ["instrument", "device", "仪器", "设备"], "doi": ["doi"], "version_label": ["version", "版本"],
      "notes": ["note", "notes", "remark", "备注"], "data_type": ["data_type", "type", "类型", "数据类型"]}
SIG = [(b"%PDF", "pdf"), (b"PK\x03\x04", "zip"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpeg"), (b"II*\x00", "tiff"),
       (b"MM\x00*", "tiff"), (b"GIF8", "gif"), (b"\x1f\x8b", "gzip"), (b"7z\xbc\xaf", "7z"),
       (b"\xd0\xcf\x11\xe0", "ole")]
EXT = {".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".tif": "tiff", ".tiff": "tiff", ".gif": "gif",
       ".zip": "zip", ".docx": "zip", ".xlsx": "zip", ".pptx": "zip", ".odt": "zip", ".doc": "ole", ".xls": "ole"}
TXT = set(".pdf .docx .xlsx .pptx .odt .csv .tsv .txt .md .json .tex .py .r .m .do .ipynb".split())
ERR, DEG, PH, OPS = [], [], [], []


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(lst, k, m, r=None):
    lst.append(dict(kind=k, message=str(m)[:300], **({"ref": str(r)[:280]} if r is not None else {})))


def err(k, m, r=None):
    rec(ERR, k, m, r)


def deg(k, m, r=None):
    rec(DEG, k, m, r)


def ph(k, m, r=None):
    rec(PH, k, m, r)


def op(o, iid=None, **k):
    d = {"ts": now(), "op": o}
    if iid:
        d["item_id"] = iid
    d.update(k)
    OPS.append(d)


def mk(v, s, l, c="medium"):
    return {"value": v, "source": s, "locator": l, "confidence": c}


def sha(p, cap=None):
    h, n = hashlib.sha256(), 0
    with open(p, "rb") as f:
        while True:
            b = f.read(CH)
            if not b:
                break
            h.update(b)
            n += len(b)
            if cap and n >= cap:
                break
    return h.hexdigest()


def mg(p):
    try:
        h = Path(p).read_bytes()[:16]
    except OSError:
        return None
    for s, n in SIG:
        if h.startswith(s):
            return n
    return "empty" if not h else ("text" if all((9 <= c <= 13) or (32 <= c < 127) or c > 127 for c in h[:12]) else "binary")


def dec(raw):
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(e), e
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace"), "utf-8-replace"


def pt(raw):
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        b = m.group(1)[:4 << 20]
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        out += [x.group(0)[1:-1].decode("latin-1", "replace") for x in re.finditer(rb"\((?:\\.|[^()\\]){1,400}\)", b)]
        if len(out) > 3000:
            break
    return " ".join(out)[:40000]


def xt(raw):
    s = re.sub(r"<w:p[ >]", "\n<w:p ", raw)
    s = re.sub(r"<[^>]{1,400}>", " ", s)
    return re.sub(r"[ \t]+", " ", s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def rd(p, ext):
    if BUD[0] <= 0:
        return "", "bounded_read"
    try:
        raw = Path(p).read_bytes()[:min(MX, BUD[0])]
    except OSError as e:
        err("read_failed", e, p)
        return "", "unreadable"
    BUD[0] -= len(raw)
    if not raw:
        return "", "empty"
    if ext == ".pdf":
        t = pt(raw)
        return t, "ok" if t.strip() else "no_text_layer"
    if ext in (".docx", ".xlsx", ".pptx", ".odt"):
        try:
            with zipfile.ZipFile(p) as z:
                b = [xt(z.read(n).decode("utf-8", "replace")) for n in z.namelist()
                     if re.search(r"(document|sharedStrings)\.xml", n) and z.getinfo(n).file_size <= 4 << 20]
            return " ".join(b), "ok" if any(s.strip() for s in b) else "no_text"
        except Exception as e:
            err("archive_read_failed", e, p)
            return "", "corrupt"
    return dec(raw)[0], "ok"


def nk(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(s).lower())


def bk(n):
    s = re.sub(r"\(\d+\)", " ", unicodedata.normalize("NFKC", Path(n).stem).lower())
    for w in [r"(?:^|[_\-\s.])(?:v|ver|rev|r)\.?\d+(?:\.\d+)?", *[r"(?:^|[_\-\s.])" + re.escape(x) for x in VW]]:
        s = re.sub(w + r"(?=$|[_\-\s.)])", " ", s)
    return Path(n).suffix.lower() + "|" + re.sub(r"[\s_\-.]+", " ", s).strip()


def vp(st):
    s = unicodedata.normalize("NFKC", st)
    m = re.search(r"(?i)(?:^|[_\-\s.])v(\d+(?:\.\d+)?)(?=$|[_\-\s.)])", s)
    if m:
        try:
            return "v" + m.group(1), float(m.group(1))
        except ValueError:
            return "v" + m.group(1), 1.0
    for w in VW:
        if re.search(r"(?:^|[_\-\s.])" + re.escape(w) + r"(?=$|[_\-\s.)])", s, re.I):
            return w, VN.get(w.lower(), 50.0)
    return ("copy", 10.0) if re.search(r"\(\d+\)$", s) else (None, 0.0)


def fp(n):
    f, st = {}, unicodedata.normalize("NFC", Path(n).stem)
    c = re.search(r"(?<![A-Z])([A-Z]{2,6})[-_ ]?(\d{2,5}(?:[-_]\d{2,5})?)", st)
    if c:
        f["project_code"] = ((c.group(1) + "-" + c.group(2).replace("_", "-")).upper(), "filename",
                             "filename#regex:project_code")
    ys = [m for m in re.finditer(r"(?<!\d)((?:19|20)\d{2})(?!\d)", st) if not (c and m.start() < c.end())]
    if ys:
        f["year"] = (ys[0].group(1), "filename", "filename#regex:year")
    for i in INSTR:
        if i.upper() in st.upper():
            f["instrument"] = (i, "filename", "filename#regex:instrument")
            break
    vl, vn = vp(st)
    if vl:
        f["version_label"] = (vl, "filename", "filename#regex:version_label")
    return f, vn


def mfld(r):
    lo = {str(k).lower().strip(): v for k, v in r.items()}
    return {c: lo[a] for c, al in FA.items() for a in al if lo.get(a) not in (None, "")}

def lj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))
    except Exception as e:
        err("json_parse_failed", e, p)
        return None


def wk(o, p="$", d=0):
    if d > 6:
        return
    yield p, o
    if isinstance(o, dict):
        for k, v in o.items():
            yield from wk(v, p + "." + str(k), d + 1)
    elif isinstance(o, list):
        for i, v in enumerate(o[:400]):
            yield from wk(v, "%s[%d]" % (p, i), d + 1)


def pk(case, pat, mx=9):
    return [(p, v) for p, v in wk(case) if p.count(".") <= mx and re.search(pat, p.rsplit(".", 1)[-1].lower())]

def sc(inp, out):
    fs, dn = [], []
    if not Path(inp).is_dir():
        err("input_missing", "input dir not found", inp)
        return fs, dn
    ores = str(Path(out).resolve()) + os.sep
    for root, dirs, names in os.walk(inp, onerror=lambda e: dn.append(
            {"path": getattr(e, "filename", "?"), "reason": "walk:" + str(getattr(e, "strerror", e))[:60]})):
        dirs[:] = sorted(d for d in dirs if d not in (".git", "__pycache__"))
        for n in sorted(names):
            p = Path(root) / n
            try:
                if str(p.resolve()).startswith(ores):
                    continue
                s = p.stat()
            except OSError as e:
                dn.append({"path": str(p), "reason": "stat:" + str(e)[:70]})
                continue
            if len(fs) >= MF:
                deg("bounded_scan", "file cap")
                break
            fs.append({"p": p, "rel": str(p.relative_to(inp)).replace(os.sep, "/"), "size": s.st_size,
                       "mtime": s.st_mtime})
    return fs, dn


def cm(fs):
    rows, tb = [], {}
    for f in fs:
        e, nm = Path(f["rel"]).suffix.lower(), Path(f["rel"]).name
        if e == ".json" and not re.match(r"(?i)case.*\.json$", nm):
            o = lj(f["p"])
            for i, v in enumerate([x for _, x in wk(o, nm) if isinstance(x, list) and x and isinstance(x[0], dict)]):
                rows += [(r, "%s#list[%d].item[%d]" % (f["rel"], i, k)) for k, r in enumerate(v[:500])]
        elif e in (".csv", ".tsv"):
            if f["size"] > 2_000_000:
                deg("bounded_read", "table too large", f["rel"])
                continue
            try:
                rw = list(csv.DictReader(f["p"].read_text(encoding="utf-8-sig", errors="replace").splitlines(),
                                         delimiter="\t" if e == ".tsv" else ","))
            except Exception as x:
                err("csv_parse_failed", x, f["rel"])
                continue
            rows += [(r, "%s:row=%d" % (f["rel"], i + 2)) for i, r in enumerate(rw[:2000]) if r]
    for r, l in rows:
        for k, v in r.items():
            if isinstance(v, str) and v.strip() and re.search(r"(?i)file|name|path|文件名", str(k)):
                tb.setdefault(nk(Path(v.strip()).name), (r, l))
                tb.setdefault(nk(v), (r, l))
    return tb

def ds(a, b, ta, tb):
    if ta and tb:
        la, lb = ta.splitlines()[:400], tb.splitlines()[:400]
        o = [x for x in difflib.SequenceMatcher(None, la, lb).get_opcodes() if x[0] != "equal"]
        return {"basis": "text_lines", "lines_before": len(la), "lines_after": len(lb),
                "lines_added": sum(x[4] - x[3] for x in o if x[0] in ("insert", "replace")),
                "lines_removed": sum(x[2] - x[1] for x in o if x[0] in ("delete", "replace"))}
    return {"basis": "size_only", "bytes_delta": b - a}


def ingest(inp, out, case, ok_disk=True):
    inp, out = Path(inp), Path(out)
    fs, dn = sc(inp, out)
    tb = cm(fs)
    its, ex, dg, chs = [], [], [], []
    for i, f in enumerate(fs, 1):
        nm, rel = f["p"].name, f["rel"]
        if re.match(r"(?i)^(case.*\.json|task\.md)$", nm):
            ex.append({"path": rel, "reason": "control"})
            continue
        e, g = Path(nm).suffix.lower(), mg(f["p"])
        it = {"item_id": "IT%04d" % i, "path_source": rel, "path_library": None, "filename": nm, "ext": e,
              "size_bytes": f["size"], "mime_guess": g, "metadata": {}, "text": "", "read_status": "ok",
              "integrity_flag": None, "action": None, "dup_of": None, "chain_id": None,
              "mtime": datetime.fromtimestamp(f["mtime"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if f["size"] == 0:
            it["integrity_flag"], it["read_status"] = "empty_file", "empty"
            deg("empty_file", "zero-byte", rel)
        try:
            it["sha256"] = sha(f["p"])
        except OSError as x:
            it.update(sha256=None, read_status="permission_denied", integrity_flag="unreadable")
            err("hash_failed", x, rel)
            its.append(it)
            continue
        if EXT.get(e) and g not in (EXT[e], "text") and not (e in (".docx", ".xlsx", ".pptx", ".odt") and g == "zip"):
            it["integrity_flag"] = "ext_magic_mismatch(%s!=%s)" % (e, g)
        t, st = (rd(f["p"], e) if f["size"] <= MX * 4 else ("", "bounded_read")) if e in TXT else ("", "not_attempted")
        if st == "bounded_read":
            deg("bounded_read", "file >8MB skipped", rel)
        if it["read_status"] == "ok":
            it["read_status"] = st
        it["text"] = t[:20000]
        fn, vn = fp(nm)
        m = {k: mk(v, s, l) for k, (v, s, l) in fn.items()}
        row = tb.get(nk(nm)) or tb.get(nk(Path(nm).stem))
        if row:
            m.update({k: mk(v, "companion_table", row[1], "high") for k, v in mfld(row[0]).items()})
        if t:
            x = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]{4,}", t)
            if x and "doi" not in m:
                m["doi"] = mk(x.group(0), "content", "content:offset=%d" % x.start(), "high")
            for s2 in INSTR:
                if s2.upper() in t[:6000].upper() and "instrument" not in m:
                    m["instrument"] = mk(s2, "content", "content:offset=%d" % t[:6000].upper().find(s2.upper()))
                    break
            f1 = next((l.strip() for l in t.splitlines() if len(l.strip()) > 12), "")
            if f1 and "title" not in m:
                m["title"] = mk(f1[:200], "content", "content:line=1", "low")
        if "year" not in m:
            m["mtime_year"] = mk(datetime.fromtimestamp(f["mtime"], timezone.utc).year, "derived",
                                  "filesystem:mtime", "low")
        it["metadata"] = m
        it["category"] = "01_literature" if e == ".pdf" and ("doi" in m or re.search(r"(?i)journal|article|abstract",
                                                                                   t[:2000])) else CG.get(e, "07_other")
        it["project"] = str(m.get("project_code", {}).get("value") or m.get("project", {}).get("value")
                            or "_unassigned")
        y = str(m.get("year", {}).get("value"))
        it["year"] = y if re.fullmatch(r"(19|20)\d{2}", y) else "_undated"
        it["version_no"], it["base_key"] = vn, bk(nm)
        its.append(it)
    by = {}
    for it in its:
        if it.get("sha256"):
            by.setdefault(it["sha256"], []).append(it)
    for h, g in by.items():
        g.sort(key=lambda x: (any(w in x["filename"].lower() for w in ("copy", "副本", "(1)", "备份", "backup")),
                              len(x["filename"]), x["path_source"]))
        for x in g[1:]:
            x["action"], x["dup_of"] = "exact_duplicate", g[0]["item_id"]
        g[0]["action"] = "keep_canonical"
        if len(g) > 1:
            dg.append({"sha256": h, "size_bytes": g[0]["size_bytes"], "keep": g[0]["item_id"],
                       "members": [{k: x[k] for k in ("item_id", "path_source", "filename")} for x in g],
                       "basis": "sha256"})
    gp = {}
    for it in its:
        if it["action"] != "exact_duplicate":
            gp.setdefault(it["base_key"], []).append(it)
    for b, g in sorted(gp.items()):
        if len(g) < 2 or len({x.get("sha256") for x in g if x.get("sha256")}) < 2:
            continue
        g.sort(key=lambda x: (x["mtime"] or "", x["version_no"], x["filename"]))
        c = {"chain_id": "VC%03d" % (len(chs) + 1), "base_key": b, "basis": ["sha256", "mtime", "version_label"],
             "members": []}
        for k, it in enumerate(g):
            it["chain_id"] = c["chain_id"]
            d = dict({x: it.get(x) for x in ("item_id", "filename", "path_source", "sha256", "size_bytes", "mtime")},
                     version_label=it["metadata"].get("version_label", {}).get("value"), order=k + 1,
                     supersedes=g[k - 1]["item_id"] if k else None)
            if k:
                d["diff_vs_previous"] = ds(g[k - 1]["size_bytes"], it["size_bytes"], g[k - 1]["text"], it["text"])
                c["members"][-1]["superseded_by"] = it["item_id"]
            c["members"].append(d)
        c["head"] = g[-1]["item_id"]
        chs.append(c)
    als = []
    for pat in (r"alias|别名|rename|曾用名", r"note|admin|supersed|replace|批注|版本说明|说明"):
        for p, v in (pk(case, pat, 3) if case else []):
            if re.search(r"\.(output_contract|contract|output_spec)\b", p):
                continue
            for r in (v if isinstance(v, list) else [v])[:50]:
                s = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
                hit = next((x for x in its if x["filename"] in s or (nk(x["filename"]) and nk(x["filename"]) in nk(s))), None)
                if hit and isinstance(r, dict):
                    hit["metadata"].setdefault("notes", mk(s[:280], "admin_note", p, "high"))
                    if "alias" in pat:
                        als.append({"alias_record": s[:220], "resolved_item_id": hit["item_id"],
                                    "resolved_filename": hit["filename"], "locator": p})
                elif not hit:
                    ph("admin_or_alias_unresolved", "no match", s[:200])
    lib = out / "library"
    lib.mkdir(parents=True, exist_ok=True)
    for it in its:
        if it["action"] == "exact_duplicate":
            op("skip_duplicate", it["item_id"], src=it["path_source"], sha256=it["sha256"], dup_of=it["dup_of"],
               result="not_copied")
            continue
        if not it.get("sha256") or it["read_status"] == "permission_denied":
            op("skip_unreadable", it["item_id"], src=it["path_source"], result=it["read_status"])
            continue
        cn = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "-",
                                       unicodedata.normalize("NFC", it["filename"]))).strip()[:120] or "unnamed"
        b, sfx = os.path.splitext(cn)
        cn = b[:100] + sfx[:20]
        d = lib / re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", it["project"])[:60] / it["year"] / it["category"]
        tgt, n = d / cn, 0
        while tgt.exists():
            try:
                if tgt.is_file() and sha(tgt) == it["sha256"]:
                    it.update(action="reuse", path_library=str(tgt.relative_to(out)).replace(os.sep, "/"))
                    op("reuse", it["item_id"], src=it["path_source"], dst=it["path_library"], sha256=it["sha256"],
                       result="identical_target_exists")
                    break
            except OSError:
                pass
            n += 1
            tgt = d / ("%s__alt%d%s" % (b, n, sfx))
            it["integrity_flag"] = "name_conflict"
        if it["action"] == "reuse":
            continue
        if not ok_disk:
            it["action"] = "skipped_no_space"
            op("skip_disk_space", it["item_id"], src=it["path_source"], result="skipped")
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(inp / it["path_source"], tgt)
            h2 = sha(tgt)
            if h2 != it["sha256"]:
                tgt.unlink()
                it["action"] = "failed_hash_mismatch"
                err("hash_mismatch_after_copy", "copied bytes differ", it["path_source"])
                op("copy_rollback", it["item_id"], src=it["path_source"], sha256_expected=it["sha256"], sha256_got=h2,
                   result="rolled_back")
                continue
            it["action"] = it["action"] or "copied"
            it["path_library"] = str(tgt.relative_to(out)).replace(os.sep, "/")
            it["sha256_library"] = h2
            op("copy", it["item_id"], src=it["path_source"], dst=it["path_library"], sha256_before=it["sha256"],
               sha256_after=h2, result="verified")
        except OSError as x:
            it["action"] = "failed_copy"
            err("copy_failed", x, it["path_source"])
            op("copy_failed", it["item_id"], src=it["path_source"], result=str(x)[:120])
    return {"items": its, "dupgroups": dg, "chains": chs, "excluded": ex, "denied": dn, "aliases": als,
            "files_seen": len(fs) + len(dn), "paths": sorted({it["path_library"] for it in its if it["path_library"]})}
