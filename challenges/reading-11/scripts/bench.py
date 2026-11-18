#!/usr/bin/env python3
"""sci-reading-bench core library: indexing, anchor verification, item validation,
result.json shell. Subcommands live in scripts/main.py."""
import hashlib, json, os, re, shutil, subprocess, sys, time, traceback, zipfile, zlib
from html import unescape
from pathlib import Path

V, NM, T0 = "1.5.0", "sci-reading-bench", time.time()
TY = ("extraction", "numeric", "method", "definition", "conflict", "coverage", "table", "other")
TEXT = {".md", ".txt", ".text", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm", ".xml", ".tex",
        ".yaml", ".yml", ".rst", ".log", ".py", ".bib"}
STOP = set(("a an the of and or to in for on with by from this that these is are was were be been it its as at "
           "not but can may such using used study paper result results than then there their they has have had "
           "which who what when where how also more most both each into during show").split())
IDK = ("case_id", "caseId", "case", "id", "task_id", "taskId", "sample_id")
CONK = ("output_contract", "outputContract", "contract", "required_outputs", "result_contract", "output_schema")
CK = ("candidate_output", "candidate_answer", "baseline_output", "model_output", "response_text", "checker_log")
KW = [("scoring", "scor grade rubric"), ("anchors", "anchor evidence citation locator"),
      ("items", "bench item question test"), ("stats", "count metric stat coverage"),
      ("report", "report summary finding"), ("status", "status state"),
      ("sources", "source input material"), ("uncertainty", "uncertain limitation risk gap"),
      ("outputs", "path file output artifact deliverable"), ("changes", "change log revision")]


def PK():
    return Path(__file__).resolve().parent.parent


def _home(env, cands):
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    for c in cands:
        try:
            if Path(c).is_dir():
                return Path(c)
        except OSError:
            pass
    return Path(cands[0])


INPUT = _home("SCIBENCH_INPUT", ["/input", str(PK().parent / "input"), "input"])
OUTPUT = _home("SCIBENCH_OUTPUT", ["/app/output", str(PK().parent / "output"), "output"])
WORK = _home("SCIBENCH_WORK", ["/app/work", str(PK().parent / "work"), "work"])


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def rd(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(e), e
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "ignore"), "utf-8-ignore"


def rj(p):
    t = rd(p)[0].replace("\ufeff", "").strip()
    if not t:
        raise ValueError("empty json")
    return json.loads(t)


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\ufeff", "")).strip()


def sq(s):
    return re.sub(r"\s+", "", s or "")


def pick(d, *names, default=None):
    for n in names:
        v = d.get(n) if isinstance(d, dict) else None
        if v not in (None, "", [], {}):
            return v
    return default


def kind(p):
    e, h = p.suffix.lower(), b""
    try:
        h = p.read_bytes()[:8]
    except OSError:
        pass
    if h.startswith(b"%PDF") or e == ".pdf":
        return "pdf"
    if h.startswith(b"PK") or e in (".docx", ".doc", ".xlsx", ".xls"):
        return "xlsx" if e in (".xlsx", ".xls") else "docx"
    if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"):
        return "image"
    return "text" if e in TEXT else "binary"


def unxml(x):
    x = re.sub(r"</(w:p|w:tr|a:p|text:p)>", "\n\n", re.sub(r"<(w:br|w:cr)\s*/>", "\n", x))
    return unescape(re.sub(r"<[^>]+>", "", x))


def zpart(p, part, pref):
    with zipfile.ZipFile(p) as z:
        n = z.namelist()
        if part not in n:
            c = [x for x in n if x.startswith(pref) and x.endswith(".xml")]
            if not c:
                raise ValueError("missing " + part)
            part = c[0]
        return z.read(part).decode("utf-8", "ignore")


def pdfq(t):
    if len(t.strip()) < 40:
        return 0.0
    s = t[:4000]
    return round(min(sum(c.isprintable() or c in "\n\t" for c in s) / len(s),
                     sum(c.isalpha() or c.isspace() for c in s) / len(s)), 3)


def pdf_raw(p):
    """Stdlib fallback: inflate content streams, lift literal strings."""
    d, out = Path(p).read_bytes(), []
    for m in re.finditer(rb"stream\r?\n", d):
        end = d.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            raw = zlib.decompressobj().decompress(d[m.end():end])
        except Exception:
            continue
        s = " ".join(re.sub(rb"\\([nrtbf()\\])", lambda x: b" " if x.group(1) in b"nrtbf" else x.group(1),
                            t.group()[1:-1]).decode("latin-1")
                     for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", raw))
        if s.strip():
            out.append(s)
    return "\f".join(out)


def ext_pdf(p):
    if shutil.which("pdftotext"):
        try:
            t = subprocess.run([shutil.which("pdftotext"), "-layout", str(p), "-"], capture_output=True,
                               timeout=120).stdout.decode("utf-8", "ignore")
            if pdfq(t) >= 0.55:
                return t, "pdftotext", pdfq(t)
        except Exception:
            pass
    for name, fn in (("pymupdf", lambda: "\f".join(g.get_text() for g in __import__("fitz").open(str(p)))),
                     ("pdfminer", lambda: __import__("pdfminer.high_level", fromlist=["x"]).extract_text(str(p)))):
        try:
            t = fn()
            if pdfq(t) >= 0.55:
                return t, name, pdfq(t)
        except Exception:
            pass
    try:
        return pdf_raw(p), "stdlib-zlib", 0.6
    except Exception:
        return "", "failed", 0.0


def extract(p, k):
    if k == "text":
        t, e = rd(p)
        return t, "plain/" + e, ""
    if k == "docx":
        return unxml(zpart(p, "word/document.xml", "word/")), "docx-xml", ""
    if k == "xlsx":
        try:
            return unxml(zpart(p, "xl/sharedStrings.xml", "xl/")), "xlsx-xml", "cell strings only"
        except Exception as e:
            return "", "failed", str(e)
    if k == "pdf":
        t, m, q = ext_pdf(p)
        return t, "pdf/" + m, "" if q >= 0.55 else "low_text_quality=%.2f" % q
    if k == "image":
        return "", "none", "image material: no stdlib OCR, read it visually"
    return "", "none", "unsupported binary"


def blocks(t):
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    raw = [b.strip() for b in re.split(r"\n\s*\n", t) if b.strip()]
    if len(raw) < 3:
        raw = [b.strip() for b in t.split("\n") if b.strip()]
    out = [re.sub(r"[ \t]+", " ", b).strip() for b in raw]
    return [b for b in out if len(b) >= 25] or ([nm(t)] if t.strip() else [])


def units(t):
    if "\f" in t:
        return [(i + 1, b) for i, pg in enumerate(t.split("\f")) for b in blocks(pg)]
    return [(None, b) for b in blocks(t)]


def scan(ip):
    """Recursive material scan -> index dict. Never raises."""
    try:
        files = [p for p in sorted(Path(ip).rglob("*")) if p.is_file() and not p.name.startswith(".")
                 and not any(s in p.parts for s in ("__pycache__", ".git", "node_modules"))
                 and not (p.parent == Path(ip) and p.name in ("case.json", "task.md", "result.json"))]
    except OSError as e:
        return {"materials": [], "n_paragraphs": 0, "degradations": [], "input_root": str(ip),
                "errors": [{"stage": "scan", "error": str(e)}]}
    mats, deg, errs = [], [], []
    for n, p in enumerate(files, 1):
        mid, k = "M%02d" % n, kind(p)
        rec = {"mid": mid, "name": p.name, "path": str(p), "kind": k, "status": "ok", "method": "none",
               "note": "", "bytes": -1, "sha1": None, "paragraphs": [], "chars": 0}
        try:
            b = p.read_bytes()
            rec["bytes"], rec["sha1"] = len(b), hashlib.sha1(b).hexdigest()[:16]
        except OSError:
            pass
        try:
            t, m, note = extract(p, k)
            rec.update(method=m, note=note)
            if note:
                deg.append({"material": mid, "file": p.name, "issue": note})
            if not t.strip():
                rec["status"] = "no_text"
                errs.append({"stage": "material", "material": mid, "error": "no extractable text"})
            for i, (pg, b) in enumerate(units(t), 1):
                par = {"pid": "%s#p%d" % (mid, i), "n": i, "text": b}
                if pg:
                    par["page"] = pg
                rec["paragraphs"].append(par)
            rec["chars"] = sum(len(x["text"]) for x in rec["paragraphs"])
        except Exception as e:
            rec.update(status="error", note="extract_failed: %s" % e)
            errs.append({"stage": "material", "material": mid, "error": str(e)})
            deg.append({"material": mid, "file": p.name, "issue": "extract_failed: %s" % e})
        mats.append(rec)
    return {"schema": "sci-reading-bench/index@1", "generated_at": now(), "input_root": str(ip),
            "materials": mats, "n_paragraphs": sum(len(m["paragraphs"]) for m in mats),
            "degradations": deg, "errors": errs}


def cache(idx):
    c = {}
    for m in idx.get("materials", []):
        buf, spans = "", []
        for par in m.get("paragraphs", []):
            t = nm(par["text"])
            if t:
                buf += (" " if buf else "") + t
                spans.append((len(buf) - len(t), len(buf), par))
        if spans:
            c[m["mid"]] = {"t": buf, "cf": buf.casefold(), "spans": spans}
    return c


def verify(c, mid, q):
    """exact -> casefold -> whitespace-insensitive; the locator comes from the hit."""
    q = nm(q)
    if not q:
        return {"verified": False, "reason": "empty_quote"}
    if mid not in c:
        return {"verified": False, "reason": "material_not_indexed"}
    for mode, needle, hay in (("exact", q, c[mid]["t"]), ("casefold", q.casefold(), c[mid]["cf"])):
        pos = hay.find(needle)
        if pos >= 0:
            pid = page = None
            for s, e, par in c[mid]["spans"]:
                if s <= pos < e or pos < s < pos + len(needle):
                    pid, page = par["pid"], par.get("page")
                    break
            return {"verified": True, "match": mode, "pid": pid, "page": page}
    if sq(q) in sq(c[mid]["t"]):
        return {"verified": True, "match": "no_whitespace", "pid": None, "page": None}
    return {"verified": False, "reason": "quote_not_found"}


def dget(o, keys, d=0):
    if d > 4:
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower().replace("-", "_") in [x.lower() for x in keys]:
                return v
        vals = list(o.values())
    elif isinstance(o, list):
        vals = o[:5]
    else:
        return None
    for v in vals:
        r = dget(v, keys, d + 1)
        if r is not None:
            return r
    return None


def load_case(ip):
    ip = Path(ip)
    for p in ([ip / "case.json"] + sorted(ip.glob("case*.json"))) if ip.is_dir() else []:
        if p.is_file():
            try:
                o = rj(p)
                return (o if isinstance(o, dict) else {"_raw": o}), p
            except Exception:
                return {"_bad_json": str(p)}, p
    return {}, None


def srcs(idx):
    return [{"id": m["mid"], "name": m["name"], "path": m["path"], "kind": m["kind"], "bytes": m["bytes"],
             "sha1": m["sha1"], "paragraphs": len(m["paragraphs"]), "status": m["status"],
             "method": m["method"]} for m in idx.get("materials", [])]


def ckeys(c):
    if isinstance(c, dict):
        return [str(k) for k in c]
    out = []
    for x in c if isinstance(c, list) else []:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            out += [x[k] for k in ("name", "field", "key", "id", "path") if isinstance(x.get(k), str)][:1]
    return out


def mirror(s):
    return {k: mirror(v) for k, v in s.items()} if isinstance(s, dict) else ([] if isinstance(s, list) else None)


def fill_contract(con, ctx):
    """Echo every output_contract field: real value when known, else null/[]."""
    out = {}
    for k in ckeys(con):
        lk, v = k.lower(), None
        # exact / near-exact names first (avoid loose substring matches such as status->stats)
        if lk in ctx:
            v = ctx.get(lk)
        if v is None:
            for name, words in KW:
                if lk == name or any(re.search(r"(^|[_\-\s])" + re.escape(w), lk) for w in words.split()):
                    v = ctx.get(name)
                    break
        if v is None and isinstance(con, dict):
            v = mirror(con[k])
        out[k] = v
    return out


def shell(cid, con, status, stage):
    return {"case_id": cid, "status": status, "stage": stage, "skill": {"name": NM, "version": V},
            "outputs": {}, "benchmark": None, "anchors": None,
            "scoring": None, "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
            "degradations": [], "changes": [], "technical_synthetic": {"present": False, "not_a_dsh_score": True},
            "runtime": {"skill_version": V, "python": sys.version.split()[0], "started_at": now(),
                        "elapsed_s": 0.0, "input_root": str(INPUT), "output_root": str(OUTPUT)},
            "contract_fields_present": ckeys(con), "contract_echo": con or {}}


def save(res, stage):
    res["runtime"].update({"stage": stage, "written_at": now(), "elapsed_s": round(time.time() - T0, 2),
                           "argv": sys.argv[1:]})
    wj(OUTPUT / "result.json", res)


def prep(stage, case):
    """Write a legal partial result.json first."""
    for d in (OUTPUT, WORK):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    con = dget(case, CONK) if isinstance(case, dict) else None
    con = con if isinstance(con, (dict, list)) else {}
    cid = dget(case, IDK) if isinstance(case, dict) else None
    res = shell(str(cid) if cid else None, con, "partial", stage)
    res["pending_human"] = ["run build to finalise benchmark/anchors/scoring/report"]
    save(res, stage)
    return res, con


def get_index(res):
    p = WORK / "index.json"
    if p.is_file():
        try:
            return rj(p)
        except Exception as e:
            res["errors"].append({"stage": "index", "error": str(e)})
    idx = scan(INPUT)
    wj(p, idx)
    return idx


# --- items ----------------------------------------------------------------------
def terms(t, k=8):
    out = []
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", t or ""):
        L = min(4, len(run))
        for i in range(len(run) - L + 1):
            out.append(run[i:i + L])
            if len(out) >= k:
                return out[:k]
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", t or ""):
        if w.lower() not in STOP:
            out.append(w.lower())
            if len(out) >= k:
                break
    return out[:k]


def cov(ts, text):
    cf = (text or "").casefold()
    return round(sum(t.casefold() in cf for t in ts) / len(ts), 3) if ts else 0.0


def ploc(loc):
    m = re.match(r"^\s*([A-Za-z0-9_\-]+)\s*#\s*p(\d+)\s*$", str(loc or ""))
    return (m.group(1), int(m.group(2))) if m else (None, None)


def norm_item(raw, i):
    """Coerce one draft item to the canonical shape (never raises)."""
    if not isinstance(raw, dict):
        return None, ["item %d is not an object" % i]
    it = {"id": str(pick(raw, "id", "qid", default="Q%02d" % i)).strip(),
          "type": str(pick(raw, "type", "task_type", default="other")).lower(),
          "difficulty": str(pick(raw, "difficulty", "level", default="medium")).lower(),
          "question": str(pick(raw, "question", "prompt", default="")).strip(),
          "rubric": [], "reference_answer": [], "evidence": []}
    it["type"] = it["type"] if it["type"] in TY else "other"
    ra = pick(raw, "reference_answer", "answer", default=[])
    it["reference_answer"] = [str(x).strip() for x in ([ra] if isinstance(ra, str) else ra) if str(x).strip()]
    rub = pick(raw, "rubric", "rubric_points", default=[])
    for j, rp in enumerate([rub] if isinstance(rub, dict) else rub, 1):
        rp = {"text": rp} if isinstance(rp, str) else rp
        if not isinstance(rp, dict):
            continue
        try:
            w = float(pick(rp, "weight", default=1.0 / max(1, len(rub))))
        except (TypeError, ValueError):
            w = 0.0
        it["rubric"].append({"id": str(pick(rp, "id", default="R%d" % j)),
                             "text": str(pick(rp, "text", "point", default="")).strip(),
                             "weight": round(w, 4),
                             "key_terms": [str(x) for x in (rp.get("key_terms") or []) if str(x).strip()]})
    for e in pick(raw, "evidence", "anchors", default=[]):
        if isinstance(e, dict):
            loc = str(pick(e, "locator", "loc", default="")).strip()
            it["evidence"].append({"material": str(pick(e, "material", "mid", default="")).strip()
                                   or (ploc(loc)[0] or ""), "locator": loc,
                                   "quote": str(pick(e, "quote", "text", default="")).strip()})
    errs = ["%s: %s" % (it["id"], m) for bad, m in
            ((len(it["question"]) < 10, "question missing or <10 chars"), (not it["rubric"], "no rubric points"),
             (not it["reference_answer"], "no reference_answer"),
             (not it["evidence"], "no evidence (locator + verbatim quote)")) if bad]
    return it, errs


def validate(draft, c):
    """Schema + verbatim quote + locator consistency. Never raises."""
    if not isinstance(draft, dict):
        return {"ok": False, "items": [], "rejected": [], "n_raw": 0, "warnings": [],
                "issues": [{"level": "error", "msg": "draft is not a JSON object"}]}
    raws = pick(draft, "items", "questions", default=[])
    raws = (raws.get("items") or []) if isinstance(raws, dict) else (raws if isinstance(raws, list) else [])
    iss, warns, items, rej, seen = [], [], [], [], set()
    for i, raw in enumerate(raws, 1):
        it, errs = norm_item(raw, i)
        if not it:
            iss += [{"level": "error", "msg": e} for e in errs]
            continue
        iss += [{"level": "error", "item": it["id"], "msg": e} for e in errs]
        if it["id"] in seen:
            it["id"] += "b"
            iss.append({"level": "error", "item": it["id"], "msg": "duplicate id renamed"})
        seen.add(it["id"])
        tot = sum(p["weight"] for p in it["rubric"])
        if it["rubric"] and abs(tot - 1.0) > 0.02:
            warns.append({"item": it["id"], "msg": "weights sum %.2f (want 1.0)" % tot})
        good = 0
        for ev in it["evidence"]:
            if len(nm(ev["quote"])) < 12:
                iss.append({"level": "error", "item": it["id"], "msg": "quote <12 chars"})
            v = ev["_v"] = verify(c, ev["material"], ev["quote"])
            if not v.get("verified"):
                iss.append({"level": "error", "item": it["id"],
                            "msg": "quote not found in %s (%s) - copy a paragraph verbatim from `show`"
                                   % (ev["material"], v.get("reason"))})
                continue
            good += 1
            pid = v.get("pid")
            if pid and ev["locator"] and pid != ev["locator"]:
                iss.append({"level": "error", "item": it["id"], "msg": "locator_mismatch: %s vs %s"
                            % (ev["locator"], pid)})
            elif not ev["locator"] and pid:
                ev["locator"] = pid
                warns.append({"item": it["id"], "msg": "locator filled from quote (%s)" % pid})
        (items if good else rej).append(it)
        if not any(p["key_terms"] for p in it["rubric"]):
            warns.append({"item": it["id"], "msg": "no key_terms (derived from answer)"})
    return {"ok": not any(x["level"] == "error" for x in iss), "items": items, "issues": iss,
            "warnings": warns, "rejected": rej, "n_raw": len(raws)}


if __name__ == "__main__":
    try:
        print("sci-reading-bench %s | core library (no CLI subcommands here)" % V)
        print("use: python3 -B scripts/main.py --help   (init | show | check | build)")
        print("paths: input=%s output=%s work=%s" % (INPUT, OUTPUT, WORK))
    except Exception:
        print(traceback.format_exc(limit=3))
    sys.exit(0)

