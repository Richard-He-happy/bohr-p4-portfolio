#!/usr/bin/env python3
"""methods-experiments-writer: build a traceable Methods/Experiments section from
scattered materials. Stdlib only, offline, exit 0, always writes result.json."""
import argparse, csv, hashlib, json, os, re, sys, tempfile, time, zipfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import kit as K
    KERR = None
except Exception as _e:
    K, KERR = None, "%s: %s" % (type(_e).__name__, _e)
V, T0, SKILL = "1.8.0", time.time(), "methods-experiments-writer"
BASE = {"case_id": None, "status": "partial", "sources": [], "uncertainty": [], "pending_human": [],
        "errors": [], "degradations": [], "changes": [], "outputs": [], "checks": {}}

def el():
    return round(time.time() - T0, 1)
def jd(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(t, p)

def wt(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def sh1(p):
    try:
        return hashlib.sha1(Path(p).read_bytes()).hexdigest()
    except Exception:
        return ""

SKIP = {"__pycache__", ".git", "node_modules", ".ipynb_checkpoints"}
CODE = {".py", ".m", ".r", ".sh", ".jl", ".go", ".js", ".ts", ".java", ".cpp", ".c"}
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
EXT = {".json": "json", ".csv": "csv", ".tsv": "csv", ".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx",
       ".xlsm": "xlsx", ".md": "md", ".markdown": "md", ".rst": "md", ".tex": "md"}
for _e in (".yaml", ".yml", ".cfg", ".ini", ".conf", ".toml", ".env"):
    EXT[_e] = "yaml"
for _e in CODE:
    EXT[_e] = "code"
for _e in IMG:
    EXT[_e] = "image"
LOGW = re.compile(r"(log|train|run|exp|out|stdout)", re.I)

def sniff(p):
    try:
        h = p.open("rb").read(6)
    except Exception:
        h = b""
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK"):
        try:
            return "docx" if "word/" in " ".join(zipfile.ZipFile(p).namelist()[:60]) else "xlsx"
        except Exception:
            return "zip"
    return EXT.get(p.suffix.lower()) or ("log" if LOGW.search(p.name) else "text")

def findcase(a, deg):
    bs = ([Path(a.input_dir)] if a.input_dir else []) + [Path("/input"), Path("/app/input")]
    c = ([Path(a.case)] if a.case else []) + [b / n for b in bs if b.is_dir() for n in ("case.json", "input.json")]
    for x in c:
        if x.is_file():
            return x
    for b in bs:
        h = sorted(b.rglob("case*.json"), key=lambda p: -p.stat().st_size) if b.is_dir() else []
        if h:
            return h[0]
    deg.append({"stage": "discover", "what": "case.json", "detail": "not found"})
    return None

def discover(root, case, deg):
    fs, seen = [], set()

    def add(p):
        try:
            r = str(p.resolve())
            if r not in seen and p.is_file() and p.stat().st_size <= 24 * 1024 * 1024:
                seen.add(r)
                fs.append(p)
        except Exception:
            pass

    if root and root.is_dir():
        for p in sorted(root.rglob("*")):
            if not any(s in p.parts for s in SKIP) and p.name not in ("case.json", "input.json"):
                add(p)
    fs.sort(key=lambda p: (p.suffix.lower() not in (".yaml", ".yml", ".json", ".cfg", ".ini", ".toml"), str(p).lower()))
    return fs[:40]

def ls(t, cap=600):
    o = []
    for i, l in enumerate(t.splitlines(), 1):
        if len(l.strip()) > 1:
            o.append({"loc": "L%d" % i, "text": l.strip()[:4000]})
            if len(o) >= cap:
                break
    return o

def paras(t, cap=600):
    o, b, s = [], [], 1
    for i, l in enumerate(t.splitlines(), 1):
        if l.strip():
            if not b:
                s = i
            b.append(l.strip())
        elif b:
            o.append({"loc": "para %d" % s, "text": " ".join(b)[:4000]})
            b = []
            if len(o) >= cap:
                return o
    if b:
        o.append({"loc": "para %d" % s, "text": " ".join(b)[:4000]})
    return o

def pdftxt(d):
    o, b = [], []
    esc = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"", b"f": b"", b"(": b"(", b")": b")", b"\\": b"\\"}
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|\bT[dD]\b|\bT\*\b|\bTJ\b|\bTj\b|\bET\b", d):
        t = m.group(0)
        if t[:1] == b"(":
            s = re.sub(rb"\\([nrtbf()\\])", lambda x: esc.get(x.group(1), b""), t[1:-1])
            s = re.sub(rb"\\([0-7]{1,3})", lambda x: bytes([int(x.group(1), 8) & 255]), s)
            try:
                b.append(s.decode("utf-8"))
            except Exception:
                b.append(s.decode("latin-1", "ignore"))
        elif t in (b"Td", b"TD", b"T*", b"ET") and b:
            o.append("".join(b))
            b = []
    if b:
        o.append("".join(b))
    return "\n".join(x for x in o if x.strip())

def p_pdf(p):
    d, o = p.read_bytes(), []
    for m in re.finditer(rb"stream\r?\n?", d):
        e = d.find(b"endstream", m.end())
        if e < 0 or len(o) >= 200:
            break
        try:
            dec = zlib.decompress(d[m.end():e])
        except Exception:
            continue
        if b"Tj" in dec or b"TJ" in dec:
            t = pdftxt(dec)
            if t.strip():
                o.append({"loc": "p.%d" % (len(o) + 1), "text": t[:4000]})
    return o

def p_docx(p):
    try:
        x = zipfile.ZipFile(p).read("word/document.xml").decode("utf8", "replace")
    except Exception:
        return []
    o = [{"loc": "para %d" % i, "text": t[:4000]} for i, t in enumerate(
        (re.sub(r"<[^>]+>", "", "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", m, re.S))).strip()
         for m in re.findall(r"<w:p[ >].*?</w:p>", x, re.S)), 1) if len(t) > 1]
    return o[:600]

def p_csv(p):
    try:
        rws = list(csv.reader(p.read_text(encoding="utf-8", errors="replace").splitlines(),
                               delimiter="\t" if p.suffix.lower() == ".tsv" else ","))
    except Exception:
        return []
    if not rws:
        return []
    hd = [c.strip() or "c%d" % (i + 1) for i, c in enumerate(rws[0])]
    return [{"loc": "row %d" % i, "text": "; ".join("%s=%s" % (hd[j], c.strip()[:100])
                                                    for j, c in enumerate(r[:len(hd)]))}
            for i, r in enumerate(rws[1:601], 2) if any(c.strip() for c in r)]

def p_json(p):
    raw = p.read_text(encoding="utf-8", errors="replace")
    try:
        o = json.loads(raw)
    except Exception:
        return ls(raw)
    out = []

    def w(x, ptr, d=0):
        if d > 8 or len(out) >= 600:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                w(v, ptr + "/" + str(k), d + 1)
        elif isinstance(x, list):
            for i, v in enumerate(x[:60]):
                w(v, ptr + "/%d" % i, d + 1)
        else:
            k = ptr.rsplit("/", 1)[-1]
            m = re.search(r'"%s"\s*:\s*[^,}\]]{1,80}' % re.escape(k), raw)
            out.append({"loc": ptr or "/", "text": (m.group(0) if m else "%s: %s" % (k, x))[:300]})

    w(o, "")
    return out

DISPATCH = {"docx": p_docx, "csv": p_csv, "json": p_json}

def parse(p, deg):
    k, st = sniff(p), "ok"
    try:
        if k == "pdf":
            s = p_pdf(p)
            if not s:
                st = "degraded"
                deg.append({"stage": "parse", "what": p.name, "detail": "PDF text layer not decodable (CID/scanned); author text needed"})
            else:
                j = "".join(x["text"] for x in s)
                g = sum(1 for c in j if c.isalnum() or c.isspace())
                if len(j) > 40 and g / len(j) < 0.62:
                    st = "degraded"
                    deg.append({"stage": "parse", "what": p.name, "detail": "PDF text layer low quality %.2f; quotes need author check" % (g / len(j))})
        elif k in DISPATCH:
            s = DISPATCH[k](p)
        elif k in ("image", "zip", "xlsx"):
            s = []
            st = "skipped"
            deg.append({"stage": "parse", "what": p.name, "detail": "%s material without an extraction path; unmet need" % k})
        else:
            t = p.read_text(encoding="utf-8", errors="replace")
            s = paras(t) if k == "md" else ls(t)
    except Exception as e:
        s, st = [], "error"
        deg.append({"stage": "parse", "what": p.name, "detail": "%s: %s" % (type(e).__name__, e)})
    return k, s, (st if s or st != "ok" else "empty")

def rows(xs, key="name", unit=False, quote=False):
    o = []
    for x in xs:
        d = {key: x["name"], "value": x["value"], "source_id": x["source"], "locator": "%s#%s" % (x["source"], x["loc"])}
        if unit:
            d["unit"] = x["unit"]
        if quote:
            d["quote"] = x["quote"]

        o.append(d)
    return o


def changes(cf, fs, zh):
    cl = [{"change_id": "C%d" % i, "type": "corrected", "element": x["element"], "original_quote": x["draft_quote"],
           "revised_quote": "%s = %s" % (x["canon"], x["source_value"]),
           "reason": "草稿值与配置/日志不一致，改用配置值" if zh else "draft value disagrees with config/log; config value used",
           "locator": x["source_loc"], "source_id": x["source"]} for i, x in enumerate(cf, 1)]
    for i, e in enumerate(sorted({x["element"] for x in fs} - {"limits"}), 1):
        y = [z for z in fs if z["element"] == e][:3]
        cl.append({"change_id": "A%d" % i, "type": "added", "element": e, "original_quote": "",
                   "revised_quote": " / ".join("%s=%s" % (z["name"], z["value"]) for z in y),
                   "reason": "按材料补写该要素" if zh else "element written from materials",
                   "locator": "%s#%s" % (y[0]["source"], y[0]["loc"]) if y else "n/a",
                   "source_id": y[0]["source"] if y else None})
    return cl

def ap():
    a = argparse.ArgumentParser(
        prog="main.py",
        description="Assemble a traceable Methods/Experiments section from materials (config, log, code, data notes, tables, drafts): six element classes, evidence ids, config reconciliation, author gaps. Stdlib only, offline; exit 0, writes result.json.")
    a.add_argument("--input-dir", default=None, help="case root (default /input)")
    a.add_argument("--case", default=None, help="path to case.json")
    a.add_argument("--out", default=None, help="output dir (default /app/output)")
    a.add_argument("--lang", default="auto", choices=["auto", "zh", "en"], help="section language")
    return a

def outdir(a):
    for c in (a.out, os.environ.get("OUT_DIR"), "/app/output"):
        if c:
            try:
                p = Path(c)
                p.mkdir(parents=True, exist_ok=True)
                if os.access(str(p), os.W_OK):
                    return p
            except Exception:
                pass
    p = Path(tempfile.gettempdir()) / "methods_out"
    p.mkdir(parents=True, exist_ok=True)
    return p

def main(argv=None):
    a = ap().parse_args(argv)
    out, err, deg = outdir(a), [], []
    rp = out / "result.json"
    jd(rp, K.skel({}, None, "partial") if K else dict(BASE))
    if KERR:
        err.append({"stage": "import", "detail": "kit.py unavailable: " + KERR})
    case, cp = {}, findcase(a, deg)
    inp = Path(a.input_dir) if a.input_dir else (cp.parent if cp else Path("/input"))
    if cp:
        try:
            case = json.loads(cp.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(case, dict):
                err.append({"stage": "case", "detail": "case.json root is not an object"})
                case = {}
        except Exception as e:
            err.append({"stage": "case", "detail": "%s: %s" % (type(e).__name__, e)})
    cid = next((case[k] for k in ("case_id", "caseId", "id", "case") if isinstance(case.get(k), (str, int))), None)
    if cid is None and cp:
        cid = cp.stem
    con = case.get("output_contract")
    if isinstance(con, dict) and K:
        jd(rp, K.skel(con, cid, "partial"))
    ms = []
    if not inp.exists():
        deg.append({"stage": "discover", "what": "input-dir", "detail": "input directory missing"})
    for i, p in enumerate(discover(inp if inp.exists() else None, case, deg), 1):
        k, s, st = parse(p, deg)
        ms.append({"id": "M%d" % i, "name": p.name, "path": str(p), "kind": k, "segments": s,
                   "bytes": p.stat().st_size, "sha1": sh1(p), "status": st})
        if time.time() - T0 > 600:
            deg.append({"stage": "parse", "what": "budget", "detail": "time budget reached"})
            break
    if not K:
        jd(rp, dict(BASE, case_id=cid, errors=err, degradations=deg, pending_human=[
                {"id": "Q1", "element": "all", "basis": str(KERR), "blocking": True,
                                   "question": "kit.py or vocab.json missing; section not assembled",
                                   "action": "restore packaged files"}]))
        return 0
    blob = json.dumps(case, ensure_ascii=False)[:3000] + " ".join(s["text"] for m in ms[:6] for s in m["segments"][:40])
    lg = a.lang if a.lang != "auto" else ("zh" if sum(1 for c in blob if "\u4e00" <= c <= "\u9fff")
                                          > max(20, 0.12 * sum(1 for c in blob if c.isascii() and c.isalpha())) else "en")
    zh = lg == "zh"
    fs, seen, st, dr = [], set(), [], None
    for m in ms:
        try:
            K.ex(m, fs, seen)
        except Exception as e:
            deg.append({"stage": "extract", "what": m["name"], "detail": "%s: %s" % (type(e).__name__, e)})
    try:
        st, dr = K.steps_of(ms), K.draft_of(ms)
        cf = K.reconcile(dr, fs)
    except Exception as e:
        cf = []
        err.append({"stage": "extract", "detail": "%s: %s" % (type(e).__name__, e)})
    g, pend = K.gaps_of(lg, fs, st, cf)
    eid = {id(x): i for i, x in enumerate(fs, 1)}
    try:
        md = K.compose(lg, fs, st, g, cf, eid, len(ms))
    except Exception as e:
        err.append({"stage": "compose", "detail": "%s: %s" % (type(e).__name__, e)})
        md = "# Methods and Experimental Setup\n\n- composition failed: %s\n" % type(e).__name__
    ev = [{"evidence_id": "E%d" % eid[id(x)], "element": x["element"], "field": x["name"], "value": x["value"],
           "source_id": x["source"], "locator": "%s#%s" % (x["source"], x["loc"]), "quote": x["quote"],
           "method": x["via"]} for x in fs]
    cl = changes(cf, fs, zh)
    try:
        wo = K.apply_wo(K.workorder(case))
    except Exception as e:
        wo = []
        err.append({"stage": "workorder", "detail": "%s: %s" % (type(e).__name__, e)})
    pr = [x for x in fs if x["element"] == "parameters"]
    sc = lambda n: n.split(".")[0] if "." in n else "global"
    tbl = ["name,value,unit,scope,source,locator,quote"] + [
        ",".join('"%s"' % str(y).replace('"', "'")
                 for y in (x["name"], x["value"], x["unit"], sc(x["name"]), x["source"], x["loc"], x["quote"][:120]))
        for x in pr]
    outs = []
    docs = (("manuscript.md", "section", md),
            ("parameter_table.csv", "parameters", "\n".join(tbl) + "\n"),
            ("evidence_map.json", "evidence map", json.dumps(ev, ensure_ascii=False, indent=1)),
            ("change_log.md", "edits", "# change log\n\n" + "\n".join(
                "- %s [%s] %s: %r -> %r (%s; %s)" % (c["change_id"], c["type"], c["element"], c["original_quote"][:90],
                                                     c["revised_quote"][:90], c["locator"], c["reason"]) for c in cl) + "\n"),
            ("pending_human.md", "gaps", "# 待确认 / to confirm\n\n" + "\n".join(
                "- %s [%s] %s" % (x["id"], x["element"], x["question"]) for x in pend) + "\n"))
    for nm_, role, content in docs:
        try:
            wt(out / nm_, content)
            outs.append({"path": nm_, "role": role, "bytes": (out / nm_).stat().st_size})
        except Exception as e:
            err.append({"stage": "artifacts", "detail": "%s: %s: %s" % (nm_, type(e).__name__, e)})
    L_ = len([x for x in fs if x["element"] == "limits"])
    cov = {e: {"items": len(st) if e == "procedure" else len([x for x in fs if x["element"] == e]) + (L_ if e == "repro" else 0)}
           for e in K.ELEMENTS}
    for k in cov:
        cov[k]["status"] = "covered" if cov[k]["items"] else "gap"
    corpus = "\n".join(s["text"] for m in ms for s in m["segments"])
    p = {"case_id": cid, "manuscript": md, "manuscript_path": "manuscript.md", "language": lg,
         "word_count": len(re.findall(r"[A-Za-z\u4e00-\u9fff]+", md)),
         "preserved_facts": rows(fs, "field", unit=True), "evidence_map": ev, "change_log": cl,
         "parameter_table": [dict(r, scope=sc(r["name"])) for r in rows(pr, unit=True)],
         "dataset_summary": {c: [z["value"] for z in fs if z["canon"] == c] for c in ("dataset", "version", "samples", "split", "preprocess")},
         "procedure": [{"index": i, "step": s["text"], "source_id": s["source"], "locator": s["loc"], "method": s["via"]}
                       for i, s in enumerate(st, 1)],
         "reproducibility_checklist": [{"item": c, "status": "present" if any(x["canon"] == c for x in fs) else "missing"} for c in ("seed", "command", "commit", "hardware", "repeats")],
         "limitations": [x["value"] for x in fs if x["element"] == "limits"],
         "element_coverage": cov, "workorder_report": wo,
         "sources": [{"source_id": m["id"], "path": m["path"], "kind": m["kind"], "bytes": m["bytes"], "sha1": m["sha1"],
                      "parse_status": m["status"], "segments": len(m["segments"])} for m in ms],
         "uncertainty": [{"kind": "gap", "id": q, "item": K.QF.get(k, [k, k])[0 if zh else 1]} for k, q in g.items()]
                        + [{"kind": "parser", "source": d["what"], "item": d["detail"]} for d in deg]
                        + [{"kind": "derived", "values": [len(ms), len(fs), len(g)],
                            "item": "counts here are computed, not measured"}],
         "pending_human": pend, "errors": err, "degradations": deg,
         "changes": cl + [{"to": "manuscript.md", "from": ("draft:" + dr["id"]) if dr else None}],
         "checks": {}, "outputs": outs, "derived_counts": {
             "materials": len(ms), "records": len(fs), "gaps": len(g), "conflicts": len(cf),
             "corrections": len(cf), "classes": sum(1 for v in cov.values() if v["items"])},
         "runtime": {"skill": SKILL, "version": V, "python": sys.version.split()[0], "elapsed_s": el(),
                     "materials": len(ms), "facts": len(fs), "steps": len(st), "case_file": str(cp) if cp else None}}
    status = "input_error" if (not case and not ms) else "insufficient_evidence" if (not ms or (len(fs) < 3 and not st)) else (
        "partial" if (err or g or cf or any(m["status"] != "ok" for m in ms)) else "ok")
    p["status"] = status
    final = K.fill(con, p) if isinstance(con, dict) else K.skel({}, cid, status)
    for k, v in p.items():
        if k in K.REQ or final.get(k) in (None, "", [], {}):
            final[k] = v
    final["case_id"], final["status"] = cid, status
    try:
        final["checks"] = K.check_all(final, corpus, con, out)
    except Exception as e:
        final["checks"] = {"ok": False, "why": "%s: %s" % (type(e).__name__, e)}
        deg.append({"stage": "checks", "detail": "check suite failed"})
        final["degradations"] = deg
    for k in list(final):
        if K.FM.get(K.nm(k)) == "checks" and not final[k]:
            final[k] = final["checks"]
    dc, ck_ = final.setdefault("derived_counts", {}), final.get("checks") or {}
    dc["checks_passed"], dc["checks_failed"] = ck_.get("passed", 0), ck_.get("failed", 0)
    dc["coverage_rate"] = round(dc.get("classes", 0) / 6, 3)
    dc["rejected_quotes"] = dict((c["check"], c.get("count")) for c in ck_.get("checks", [])).get(
        "quotes_verbatim_in_materials", 0)
    jd(rp, final)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        try:
            o = Path(os.environ.get("OUT_DIR") or "/app/output")
            o.mkdir(parents=True, exist_ok=True)
            if not (o / "result.json").exists():
                jd(o / "result.json", dict(BASE, status="input_error", errors=[{"stage": "fatal"}]))
        except Exception:
            pass
        sys.exit(0)
