"""library.py - extraction, naming, hashing, writers for research-library-qa (stdlib only).

Per-file problems return warning strings; one bad file never aborts a run.
"""
import csv
import difflib
import hashlib
import json
import os
import re
import shutil
import zipfile
import zlib
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".log", ".tex", ".bib", ".rst", ".html", ".htm", ".xml"}
MAX_TEXT, CHUNK = 3000000, 900
_ESC = {110: 10, 114: 13, 116: 9, 98: 8, 102: 12, 92: 92}
_CLS = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".xlsm": "xlsx", ".pptx": "pptx", ".csv": "table", ".tsv": "table",
        ".json": "json", ".jsonl": "json", ".md": "markdown", ".markdown": "markdown", ".rst": "markdown", ".bib": "bib",
        ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".bmp": "image", ".tif": "image", ".tiff": "image", ".webp": "image"}
OBJ_RE = re.compile(rb"(\d+)\s+\d+\s+obj(.*?)endobj", re.S)
STREAM_RE = re.compile(rb"stream\r?\n?(.*?)\r?\n?endstream", re.S)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sniff(p):
    try:
        h = open(p, "rb").read(8)
    except Exception:
        return "unreadable"
    for magic, kind in ((b"%PDF", "pdf"), (b"PK\x03\x04", "zip"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpeg"),
                        (b"RIFF", "image"), (b"GIF8", "image"), (b"BM", "image")):
        if h.startswith(magic):
            return kind
    return "unknown"


def decode(b):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return b.decode(enc), enc
        except Exception:
            continue
    return b.decode("latin-1", "replace"), "latin-1"


def _unesc(s):
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5c and i + 1 < len(s):
            n, i = s[i + 1], i + 2
            if n == 0x0a:
                continue
            if n in _ESC:
                out.append(_ESC[n])
            else:
                out.append(n)
        else:
            out.append(c)
            i += 1
    return bytes(out)


def _stream_text(data):
    parts = []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>|\bT[dD]\b|\bT\*\b", data):
        tok = m.group(0)
        if tok in (b"Td", b"TD", b"T*"):
            parts.append(b"\n")
        elif tok.startswith(b"("):
            parts.append(_unesc(tok[1:-1]))
        else:
            hx = re.sub(rb"[^0-9A-Fa-f]", b"", tok[1:-1])
            try:
                parts.append(bytes.fromhex(hx.decode()).decode("utf-16-be", "ignore").encode() if len(hx) % 4 == 0 and len(hx) >= 4
                             else bytes.fromhex(hx.decode()) if len(hx) % 2 == 0 else b"")
            except Exception:
                pass
    return decode(b"".join(parts))[0]


def extract_pdf(p):
    data, warns, meta = p.read_bytes(), [], {}
    for key in ("Title", "Author", "Producer"):
        m = re.search(rb"/" + key.encode() + rb"\s*\(((?:\\.|[^\\()])*)\)", data[:400000])
        meta[key.lower()] = _unesc(m.group(1)).decode("latin-1", "replace").strip() if m else ""
    meta = {k: v for k, v in meta.items() if v}
    m = re.search(rb"/CreationDate\s*\(D:(\d{4})", data[:400000])
    if m:
        meta["created"] = m.group(1).decode()
    objs = {}
    for m in OBJ_RE.finditer(data):
        objs.setdefault(int(m.group(1)), m.group(2))
    pages = [n for n, b in sorted(objs.items()) if re.search(rb"/Type\s*/Page[^s]", b)]
    paras = []
    if pages:
        for idx, num in enumerate(pages, 1):
            texts = []
            for r in re.findall(rb"/Contents\s*(?:\[\s*)?(\d+)\s+\d+\s+R", objs[num]):
                sm = STREAM_RE.search(objs.get(int(r), b""))
                if sm:
                    try:
                        raw = zlib.decompress(sm.group(1))
                    except Exception:
                        raw = sm.group(1)
                    texts.append(_stream_text(raw))
            paras += extract_plain("\n".join(texts), "p%d.l" % idx)
        if not paras:
            warns.append("pdf_no_text_layer")
    else:
        warns.append("pdf_pages_unresolved")
    if len(" ".join(t for _, t in paras)) < 40:
        warns.append("pdf_text_too_short")
    return paras, "pdf_streams", sorted(set(warns)), meta


def extract_docx(p):
    z = zipfile.ZipFile(p)
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    paras = [(("p.%d" % i), re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", c, re.S)))).strip()))
             for i, c in enumerate(re.findall(r"<w:p[ >].*?</w:p>", xml, re.S), 1)]
    paras = [x for x in paras if x[1]]
    meta = {}
    try:
        core = z.read("docProps/core.xml").decode("utf-8", "replace")
        meta = {k: unescape(re.search(r"<%s[^>]*>(.*?)</%s>" % (k, k), core, re.S).group(1)).strip()
                for k in ("title", "creator", "created", "modified") if re.search(r"<%s[^>]*>(.*?)</%s>" % (k, k), core, re.S)}
    except KeyError:
        pass
    return paras, "docx_xml", ([] if paras else ["docx_no_paragraph_text"]), meta


def extract_xlsx(p):
    z = zipfile.ZipFile(p)
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S):
            shared.append(unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    paras = []
    for name in sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        sh = name.split("/")[-1][:-4]
        for ri, row in enumerate(re.findall(r"<row[^>]*>(.*?)</row>", z.read(name).decode("utf-8", "replace"), re.S), 1):
            vals = []
            for c in re.findall(r"<c\b[^>]*?(?:/>|>.*?</c>)", row, re.S):
                cm, tm, vm = re.search(r'r="([A-Z]+)\d+"', c), re.search(r't="(\w+)"', c), re.search(r"<v>(.*?)</v>", c, re.S)
                idx = int(vm.group(1)) if vm and vm.group(1).isdigit() else -1
                val = shared[idx] if tm and tm.group(1) == "s" and 0 <= idx < len(shared) else (unescape(re.sub(r"<[^>]+>", "", vm.group(1))) if vm else "")
                if val.strip():
                    vals.append("%s=%s" % (cm.group(1) if cm else "?", val.strip()))
            if vals:
                paras.append(("%s!r%d" % (sh, ri), " | ".join(vals)))
    return paras, "xlsx_xml", ([] if paras else ["xlsx_no_cell_text"]), {}


def extract_plain(text, base="line"):
    out, buf = [], []
    for i, ln in enumerate(text.splitlines() + [""], 1):
        if ln.strip():
            buf.append((i, re.sub(r"[ \t]+", " ", ln.strip())))
        elif buf:
            out.append(("%s%d-%d" % (base, buf[0][0], buf[-1][0]), " ".join(x for _, x in buf)))
            buf = []
    return out


def document(path):
    doc = {"paras": [], "method": "none", "warnings": [], "meta": {}}
    ext, kind = path.suffix.lower(), sniff(path)
    try:
        if ext == ".pdf" or kind == "pdf":
            doc["paras"], doc["method"], doc["warnings"], doc["meta"] = extract_pdf(path)
        elif ext == ".docx":
            doc["paras"], doc["method"], doc["warnings"], doc["meta"] = extract_docx(path)
        elif ext in (".xlsx", ".xlsm"):
            doc["paras"], doc["method"], doc["warnings"], doc["meta"] = extract_xlsx(path)
        elif ext in TEXT_EXT or (kind == "unknown" and ext not in _CLS):
            text, enc = decode(path.read_bytes()[:MAX_TEXT])
            doc["paras"], doc["method"] = extract_plain(text), "text/%s" % enc
        else:
            doc["warnings"].append("no_text_extractor:%s" % (kind or ext))
    except PermissionError:
        doc["warnings"].append("permission_denied")
    except Exception:
        doc["warnings"].append("extract_error")
    doc["chars"] = sum(len(t) for _, t in doc["paras"])
    if not doc["chars"] and not doc["warnings"]:
        doc["warnings"].append("empty_text")

    return doc


CJK_RE = re.compile(r"[\u3400-\u9fff]+")
WORD_RE = re.compile(r"[a-z0-9][a-z0-9._/\-]*")


def toks(s):
    s = s.lower()
    out = {w for w in WORD_RE.findall(s) if len(w) >= 2}
    for run in CJK_RE.findall(s):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
    return out


def chunk_doc(paras):
    chunks, cur, locs = [], [], []
    for loc, text in paras:
        if cur and len(" ".join(cur)) + len(text) > CHUNK:
            chunks.append({"loc": locs[0] if len(locs) == 1 else "%s..%s" % (locs[0], locs[-1]), "text": " ".join(cur)})
            cur, locs = [], []
        cur.append(text)
        locs.append(loc)
    if cur:
        chunks.append({"loc": locs[0] if len(locs) == 1 else "%s..%s" % (locs[0], locs[-1]), "text": " ".join(cur)})
    return chunks


def pick_quote(text, qt, maxlen=300):
    if not text:
        return ""
    best, bs = None, -1
    for s in re.split(r"(?<=[。！？；!?;])|(?<=[.])\s+|\n", text):
        if s and s.strip():
            sc = len(toks(s) & qt)
            if sc > bs:
                best, bs = s, sc
    best = (best or text).strip()
    return best[:maxlen] if len(best) > maxlen else best


def norm_stem(name):
    s = re.sub(r"\.(pdf|docx?|xlsx?|pptx?|csv|tsv|md|txt|json)$", "", name, flags=re.I)
    s = re.sub(r"(?i)(copy\s*of|副本|final|draft|revised|修订|定稿|最新|备份)", " ", s)
    s = re.sub(r"[\(\[]\s*\d+\s*[\)\]]", " ", s)
    s = re.sub(r"(?i)[\s_\-.]*v(er)?\.?\s*\d+(?:[._]\d+)*", " ", s)
    s = re.sub(r"[\s_\-.]+(19|20)\d{2}[\s_\-.]*$", " ", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", s.lower())
    return s or re.sub(r"\W+", "", name.lower())


def ver_token(name):
    m = re.search(r"(?i)(?:^|[^a-z])v(?:er)?\.?\s*(\d+(?:[._]\d+)*)", name) or re.search(r"(?i)(final|定稿|最新|revised|修订|draft|草稿|copy|副本)", name)
    return m.group(1).replace("_", ".").lower() if m else None


def ver_rank(tok):
    if not tok:
        return -1.0
    if re.match(r"^\d", tok):
        return sum(int(x) / (100 ** i) for i, x in enumerate([y for y in tok.split(".") if y.isdigit()][:3]))
    return {"final": 0.9, "定稿": 0.9, "最新": 0.9, "revised": 0.4, "修订": 0.4, "copy": 0.05, "副本": 0.05}.get(tok, 0.1)


def classify(path, kind=None):
    ext = path.suffix.lower()
    if kind in ("png", "jpeg", "image"):
        return "image"
    return _CLS.get(ext) or ("text" if ext in TEXT_EXT else "other")


def role_of(rel):
    name, low = rel.split("/")[-1], rel.split("/")[-1].lower()
    if rel.count("/") == 0 and low in ("task.md", "case.json", "output_contract.md"):
        return "case_definition"
    if low in ("material.json", "manifest.json", "metadata.json", "metadata.csv", "index.csv"):
        return "sidecar"
    return "system_junk" if low in (".ds_store", "thumbs.db", "desktop.ini") or name.startswith("~$") or "__macosx" in rel.lower() else "material"


def file_record(path, rel):
    st = path.stat()
    rec = {"path": str(path), "rel": rel, "name": path.name, "ext": path.suffix.lower(), "size": st.st_size,
           "mtime": st.st_mtime, "mtime_iso": iso(st.st_mtime), "role": role_of(rel),
           "readable": os.access(path, os.R_OK), "sha256": None,
           "doc": {"paras": [], "method": "skipped", "warnings": [], "meta": {}, "chars": 0}}
    rec["kind"], rec["class"] = sniff(path), classify(path)
    meta = {"ext": (rec["ext"].lstrip(".") or "none", "filename"), "size_bytes": (rec["size"], "stat"), "mtime": (rec["mtime_iso"], "stat")}
    if rec["role"] == "system_junk":
        rec["doc"]["warnings"].append("system_junk_skipped")
        return rec, meta
    try:
        rec["sha256"] = sha256_file(path)
    except Exception as e:
        rec["readable"] = False if isinstance(e, PermissionError) else rec["readable"]
        rec["doc"]["warnings"].append("permission_denied" if isinstance(e, PermissionError) else "hash_error")
        return rec, meta
    if rec["size"] == 0:
        rec["doc"]["warnings"].append("zero_byte")
        return rec, meta
    rec["doc"] = document(path) if rec["readable"] else {"paras": [], "method": "denied", "warnings": ["permission_denied"], "meta": {}, "chars": 0}
    d = rec["doc"]
    meta["title"] = (d["meta"].get("title") or path.stem, "content:doc_props" if d["meta"].get("title") else "filename")
    for k in ("author", "created", "modified"):
        if d["meta"].get(k) or d["meta"].get("creator") and k == "author":
            meta[k] = (d["meta"].get(k) or d["meta"]["creator"], "content:doc_props")
    if ver_token(path.name):
        meta["version_token"] = (ver_token(path.name), "filename")
    y = re.search(r"(?:^|[^0-9])((?:19|20)\d{2})(?:[^0-9]|$)", path.name)
    if y:
        meta["year"] = (y.group(1), "filename")
    meta["text_chars"] = (d["chars"], "content:" + d["method"])
    return rec, meta


def scan(root, max_files=2000, skip_dirs=(".git", "__pycache__", "node_modules")):
    recs, metas, skipped, files = [], {}, [], []
    root = Path(root)
    if not root.is_dir():
        return recs, metas, [{"path": str(root), "reason": "input_dir_missing"}]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs and not d.startswith("."))
        files += [Path(dirpath) / f for f in sorted(filenames)]
    for p in files:
        if len(recs) >= max_files:
            skipped.append({"path": str(p), "reason": "max_files_reached", "detail": str(max_files)})
            continue
        rel = str(p.relative_to(root)).replace(os.sep, "/")
        try:
            rec, meta = file_record(p, rel)
            recs.append(rec)
            metas[rel] = meta
        except Exception as e:
            skipped.append({"path": rel, "reason": "record_error"})
    return recs, metas, skipped


def organize(recs, out, budget):
    plan, total, by_rel = [], 0, {r["rel"]: r for r in recs}
    for r in [x for x in recs if x["role"] == "material"]:
        act = "skip_duplicate" if r.get("duplicate_of") else "skip_unreadable" if not r["readable"] else "skip_empty" if not r["size"] else None
        tgt = ""
        if act is None:
            tgt = "library/%s/%s_%s" % (r["class"], r["sha256"][:8], re.sub(r'[\\/:*?"<>|]+', "_", r["name"])[:120])
            act = "copy_canonical"
        plan.append({"source": r["rel"], "target": tgt, "action": act, "sha256": r["sha256"], "size_bytes": r["size"]})
    for p in [x for x in plan if x["action"] == "copy_canonical"]:
        if total + p["size_bytes"] > budget:
            p["action"] = "deferred_size_budget"
            continue
        try:
            dst = out / p["target"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(by_rel[p["source"]]["path"], dst)
            p["copy_sha256_verified"] = sha256_file(dst) == p["sha256"]
            p["action"], total = ("copied_verified" if p["copy_sha256_verified"] else "copy_hash_mismatch"), total + p["size_bytes"]
        except Exception as e:
            p["action"] = "copy_failed:%s" % type(e).__name__
    return plan, total


def write_csv(path, cols, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in cols} for r in rows)


def write_inventory(path, recs, metas, chain_of):
    cols = ["rel", "role", "class", "size_bytes", "sha256", "mtime", "readable", "readability", "duplicate_of", "version_chain",
            "text_chars", "extract_method", "title", "version_token", "year", "author", "metadata_provenance"]
    rows = []
    for r in recs:
        m = metas.get(r["rel"], {})
        rows.append({"rel": r["rel"], "role": r["role"], "class": r["class"], "size_bytes": r["size"], "sha256": r["sha256"] or "",
                     "mtime": r["mtime_iso"], "readable": r["readable"], "duplicate_of": r.get("duplicate_of") or "", "version_chain": chain_of.get(r["rel"]) or "",
                     "text_chars": r["doc"]["chars"], "extract_method": r["doc"]["method"], "readability": "|".join(r["doc"]["warnings"]),
                     "metadata_provenance": json.dumps({k: src for k, (v, src) in m.items()}, ensure_ascii=False),
                     **{f: (str(m[f][0]) if f in m else "") for f in ("title", "version_token", "year", "author")}})
    write_csv(path, cols, rows)



def dup_and_versions(recs):
    mats = [r for r in recs if r["role"] == "material" and r.get("sha256")]
    groups = {}
    for r in mats:
        groups.setdefault(r["sha256"], []).append(r)
    dups = []
    for sha, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda r: (r["mtime"], len(r["rel"])))
        for r in items[1:]:
            r["duplicate_of"] = items[0]["rel"]
        dups.append({"group_id": "DG%02d" % (len(dups) + 1), "sha256": sha, "size_bytes": items[0]["size"], "count": len(items),
                     "canonical": items[0]["rel"], "members": [r["rel"] for r in items], "rule": "identical sha256; canonical=earliest mtime"})
    stems = {}
    for r in mats:
        st = norm_stem(r["name"]) if not r.get("duplicate_of") else ""
        if st:
            stems.setdefault(st, []).append(r)
    chains = []
    for stem, items in sorted(stems.items()):
        if len(items) < 2:
            continue
        items.sort(key=lambda r: (ver_rank(ver_token(r["name"])), r["mtime"]))
        sims = []
        for a, b in zip(items, items[1:]):
            ta, tb = " ".join(t for _, t in a["doc"]["paras"])[:4000], " ".join(t for _, t in b["doc"]["paras"])[:4000]
            sims.append(round(difflib.SequenceMatcher(None, ta, tb).quick_ratio(), 3) if ta and tb else None)
        ranks, times = [ver_rank(ver_token(r["name"])) for r in items], [r["mtime"] for r in items]
        agree = all(x <= y for x, y in zip(ranks, ranks[1:])) and all(x <= y for x, y in zip(times, times[1:]))
        chains.append({"chain_id": "VC%02d" % (len(chains) + 1), "stem": stem, "latest": items[-1]["rel"],
                       "confidence": "high" if agree and all(x is None or x >= 0.5 for x in sims) else ("medium" if agree else "low"),
                       "documents": [{"rel": r["rel"], "sha256": r["sha256"], "size_bytes": r["size"], "mtime": r["mtime_iso"],
                                      "version_token": ver_token(r["name"]), "text_chars": r["doc"]["chars"], "is_latest": r is items[-1]} for r in items],
                       "evidence": {"distinct_sha256": len({r["sha256"] for r in items}), "pairwise_text_similarity": sims, "name_rank_matches_time_order": agree,
                                    "rule": "same stem + distinct sha256; token then mtime"}})
    return dups, chains


def audit(res, out):
    root, inv = Path((res.get("library") or {}).get("root") or ""), res.get("inventory", [])
    miss = [k for k in res.get("output_contract_fields", []) if k not in res]
    gone = [e["rel"] for e in inv if not (root / e["rel"]).is_file()]
    mism = [e["rel"] for e in inv if (root / e["rel"]).is_file() and e.get("sha256") and sha256_file(root / e["rel"]) != e["sha256"]]
    cache, bad, n = {}, [], 0
    for e in [x for q in res.get("questions", []) for x in q.get("evidence", [])]:
        n += 1
        cache.setdefault(e["rel"], " ".join(t for _, t in document(root / e["rel"])["paras"]) if (root / e["rel"]).is_file() else "")
        bad += [e["rel"]] if e["quote"] not in cache[e["rel"]] else []
    chk = [{"check": "contract_fields", "n": len(res.get("output_contract_fields", [])), "missing": miss, "pass": not miss},
           {"check": "sha256_from_disk", "n": len(inv), "mismatch": mism, "missing_files": gone, "pass": not (mism or gone)},
           {"check": "quotes_verbatim", "n": n, "failures": bad, "pass": not bad},
           {"check": "artifacts", "pass": all((out / x).is_file() for x in ("inventory.csv", "version_chain.json", "answers.md"))}]
    return {"status": "pass" if all(c["pass"] for c in chk) else "fail", "checks": chk}
