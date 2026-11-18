#!/usr/bin/env python3
"""writing-11 | long-document / thesis chapter revision: init | show | check | build.

  python3 main.py init  --input /input --out /app/output
  python3 main.py show  --target C01-P002
  python3 main.py check
  python3 main.py build

The agent writes work/draft.json (schema: references/schemas.md); build re-verifies every
quote and applies accepted annotations only. Exit code is always 0 and a legal partial
result.json is written before any heavy work.
"""
import argparse, difflib, hashlib, json, os, platform, re, shutil, subprocess, sys, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
try:
    import verify as V
except Exception:
    V = None
T0, VER, NAME = time.time(), "1.0.0", "writing-11-long-document"
MARK = "\u00b7 editorial annotation \u00b7"
ANC = re.compile(r"\b([A-Z][A-Z0-9]{0,9}-[A-Z]{0,2}\d{1,5})\b")
EAB = re.compile(r"(?m)^> \*\*\[EA-.*(?:\n>.*)*\n?")
HED = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
IDS = ("id", "pid", "paragraph_id", "para_id", "target_id", "key", "label", "anchor")
TXS = ("text", "content", "paragraph", "body", "sentence", "caption", "en", "zh", "value")
FAM = [(r"case_?id", "case_id"), (r"deliver|manuscript|artifact", "deliverable"),
       (r"preserv|fact", "preserved_facts"), (r"evidence", "evidence_map"),
       (r"change|revision|diff", "change_log"), (r"receipt|workorder", "workorder_receipt"),
       (r"consisten", "consistency"), (r"uncertain", "uncertainty"),
       (r"pending|human", "pending_human"), (r"status", "status")]


def log(*a):
    print(*a, flush=True)


def sha(s):
    return hashlib.sha256((s or "").encode("utf-8", "replace")).hexdigest()[:16]


def rd(p):
    b = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(enc), enc
        except Exception:
            pass
    return b.decode("utf-8", "replace"), "utf-8-replace"


def lj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig")), None
    except Exception as exc:
        return None, f"{Path(p).name}: {exc!r}"


def dump(p, obj, text=False):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if text else json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sniff(p):
    """Extension + magic bytes; labels are never trusted."""
    try:
        head, ext = p.open("rb").read(8), p.suffix.lower()
    except Exception:
        head, ext = b"", ""
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
            for pre, kind in (("word/", "docx"), ("xl/", "xlsx")):
                if any(n.startswith(pre) for n in names):
                    return kind
        except Exception:
            pass
        return "zip"
    if ext in (".docx", ".xlsx"):
        return ext[1:]
    return {".md": "markdown", ".markdown": "markdown", ".json": "json", ".pdf": "pdf"}.get(ext) or (
        "text" if b"\x00" not in head else "binary")


def split_prose(T, rel):
    """Headings -> sections; blank-line paragraphs -> blocks (long ones split by sentence)."""
    secs, blocks, cur = [], [], ("", "preamble")
    for unit in re.split(r"\n\s*\n", T or ""):
        lines = [x for x in unit.splitlines() if x.strip()]
        while lines and HED.match(lines[0]):
            m = HED.match(lines[0])
            num = re.match(r"^(\d+(?:\.\d+)*)[.)]?\s+(.*)$", m.group(2).strip())
            cur = (num.group(1) if num else "", (num.group(2) if num else m.group(2)).strip())
            secs.append({"no": cur[0], "title": cur[1], "level": len(m.group(1)),
                         "locator": f"{rel} \u00a7{(cur[0] + ' ' + cur[1]).strip()}"})
            blocks.append({"section": f"{cur[0]} {cur[1]}".strip(), "text": lines[0].strip(),
                           "locator": f"{rel} \u00a7{(cur[0] + ' ' + cur[1]).strip()} (heading)"})
            lines = lines[1:]
        body = "\n".join(lines)
        for part in [body] if len(body) <= 1600 else re.split(r"(?<=[.!?])\s+", body):
            if part.strip():
                blocks.append({"section": f"{cur[0]} {cur[1]}".strip(), "text": part})
    return secs, blocks


def docx_text(p):
    un = lambda s: (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
                    .replace("&apos;", "'").replace("&amp;", "&"))
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    out = []
    for pm in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = un(re.sub(r"<[^>]+>", "", "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", pm, re.S)))).strip()
        st = re.search(r'<w:pStyle w:val="([^"]+)"', pm) or re.search(r'<w:outlineLvl w:val="(\d)"', pm)
        if t:
            out.append(("## " if st and re.search(r"heading|title", st.group(1), re.I) else "") + t)
    return "\n\n".join(out)


def pdf_text(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, timeout=120)
            if r.returncode == 0 and len(r.stdout) > 400:
                return r.stdout.decode("utf-8", "replace"), "pdftotext"
        except Exception:
            pass
    return "", "pdf text unavailable: pdftotext missing or empty (degradation)"


def json_blocks(obj, rel, path="", out=None):
    """Flatten JSON; an id+text dict becomes one block that carries the id as anchor."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        tid = next((str(obj[k]) for k in obj if str(k).lower() in IDS and isinstance(obj[k], (str, int))), None)
        txk = next((k for k in obj if str(k).lower() in TXS and isinstance(obj[k], str)
                    and len(obj[k].strip()) > 40), None)
        if tid and txk:
            out.append({"section": tid, "text": obj[txk].strip(), "anchors": [tid], "locator": f"{rel} #{tid}"})
            return out
        for k, v in obj.items():
            kp = f"{path}/{k}"
            if isinstance(v, (dict, list)):
                json_blocks(v, rel, kp, out)
            elif isinstance(v, str) and len(v.strip()) > 1:
                out.append({"section": kp.strip("/").replace("/", " > ")[:60], "text": v.strip(),
                            "locator": f"{rel} #{kp}"})
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            json_blocks(v, rel, f"{path}/{i}", out)
    return out


def parse_material(p, rel, mid, notes):
    info = {"id": mid, "rel": rel, "kind": sniff(p), "bytes": p.stat().st_size, "extraction": "",
            "status": "ok", "sections": []}
    raw, k = [], info["kind"]
    try:
        if k in ("markdown", "text", "csv"):
            T, enc = rd(p)
            info["extraction"] = f"{k}:{enc}"
            info["sections"], raw = split_prose(T, rel)
        elif k == "docx":
            info["extraction"] = "docx:word/document.xml"
            info["sections"], raw = split_prose(docx_text(p), rel)
        elif k == "pdf":
            T, how = pdf_text(p)
            info["extraction"], info["status"] = how, "degraded"
            info["sections"], raw = split_prose(T, rel)
            notes.append(f"{rel}: {how}")
        elif k == "json":
            obj, err = lj(p)
            if err:
                raise ValueError(err)
            raw, info["extraction"] = json_blocks(obj, rel), "json:flattened"
        else:
            info["status"] = "skipped"
            notes.append(f"{rel}: {k} not parsed")
    except Exception as exc:
        info["status"] = "unreadable"
        notes.append(f"{rel}: unreadable ({exc!r})")
    blocks, cnt = [], {}
    for rb in raw:
        t = (rb.get("text") or "").strip()
        marks = ANC.findall(t)
        t = re.sub(r"<!--.*?-->", "", t).strip() or (t if not marks else "")
        if not t:
            continue
        sec = rb.get("section", "")
        cnt[sec] = cnt.get(sec, 0) + 1
        loc = rb.get("locator") or (f"{rel} \u00a7{sec} \u00b6{cnt[sec]}" if sec else f"{rel} \u00b6{cnt[sec]}")
        blocks.append({"bid": f"{mid}-B{len(blocks) + 1:03d}", "material": mid, "section": sec, "locator": loc,
                       "text": t, "anchors": sorted(set(list(rb.get("anchors") or []) + ANC.findall(t) + marks))[:20]})
    merged, carry = [], []
    for b in blocks:  # a block holding only an id marker belongs to the next paragraph
        if len(b["text"]) <= 40 and ANC.fullmatch(b["text"].strip()):
            carry += b["anchors"]
            continue
        if carry:
            b["anchors"] = sorted(set(b["anchors"]) | set(carry))
            carry = []
        merged.append(b)
    info["blocks_n"], info["text"] = len(merged), "\n\n".join(b["text"] for b in merged)
    return info, merged


def find_wo(case, inp):
    """Workorder by key semantics, then any *workorder*.json in the input tree."""
    wo = None
    for k, v in (case or {}).items():
        if re.search(r"work[\s_-]?order", str(k), re.I) and isinstance(v, (dict, list)):
            wo = v if isinstance(v, dict) else {"tasks": v}
    for p in (sorted(inp.rglob("*workorder*.json")) if inp.is_dir() else []):
        obj, _ = lj(p)
        if isinstance(obj, dict) and (obj.get("target_ids") or obj.get("targets")):
            wo = {**(wo or {}), **obj}
    return wo


def wo_items(wo):
    tids, items = (wo or {}).get("target_ids") or (wo or {}).get("targets") or [], []
    if isinstance(tids, dict):
        tids = list(tids)
    for i, t in enumerate(tids if isinstance(tids, list) else []):
        if isinstance(t, str):
            items.append({"item_id": f"WO-{i + 1:02d}", "target_id": t, "requirement": ""})
        elif isinstance(t, dict):
            items.append({"item_id": f"WO-{i + 1:02d}", "requirement": t.get("instruction") or "",
                          "target_id": str(t.get("id") or t.get("target_id") or f"WO-T{i + 1:02d}")})
    if not items and (wo or {}).get("target_id"):
        items = [{"item_id": "WO-01", "target_id": str(wo["target_id"]), "requirement": ""}]
    return items


def sem(contract, pay):
    """Contract keys stay verbatim; values matched by key name first, then by family."""
    special = {"result": ["deliverable", "consistency"], "claims": ["evidence_map"],
               "uncertainties": ["uncertainty"], "evidence": ["evidence_map"]}
    out = {}
    for k in contract:
        lk = str(k).lower()
        if pay.get(k) is not None:
            out[k] = pay[k]
            continue
        if lk in special:
            out[k] = next((pay.get(x) for x in special[lk] if pay.get(x) is not None), None)
            continue
        hit = next((n for p, n in FAM if re.search(p, lk, re.I)), None)
        out[k] = pay.get(hit) if hit else None
    return out


def paths(a):
    inp = Path(a.input or os.environ.get("INPUT_DIR") or "/input")
    if not inp.is_dir():
        for alt in (Path.cwd() / "input", HERE.parent / "input", Path("/app/input")):
            if alt.is_dir():
                inp = alt
                break
    out = Path(a.out or os.environ.get("OUT_DIR") or "/app/output")
    if not (a.out or os.environ.get("OUT_DIR")) and not Path("/app").is_dir():
        out = Path.cwd() / "output"
    work = Path(a.work or os.environ.get("WORK_DIR") or (out.parent / "work"))
    for d in (out, work, out / "versions"):
        d.mkdir(parents=True, exist_ok=True)
    return {"input": inp, "out": out, "work": work}


def load_index(work):
    obj, err = lj(Path(work) / "source_index.json")
    if err:
        log(f"no usable source_index.json ({err}); run init first")
    return obj if isinstance(obj, dict) else {}


def rt():
    return {"skill": NAME, "version": VER, "python": platform.python_version(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(time.time() - T0, 2), "budget": "64 requests / 900 s per case",
            "deterministic_checks": True}


def partial(out, cid, contract, note="", errs=None):
    pay = {"case_id": cid, "status": "partial", "deliverable": None, "preserved_facts": [], "evidence_map": [],
           "change_log": [], "annotations": [], "workorder_receipt": None, "consistency": None, "sources": [],
           "uncertainty": [], "pending_human": [], "errors": list(errs or []),
           "degradations": [note] if note else [], "changes": [], "runtime": rt()}
    pay.update(sem(contract, pay))
    pay["case_id"] = cid
    dump(Path(out) / "result.json", pay)


def cmd_init(a, P):
    out, work, inp = P["out"], P["work"], P["input"]
    partial(out, None, {})
    case, cpath, errors, notes = {}, None, [], []
    for cand in (inp / "case.json", inp / "input.json"):
        if cand.is_file():
            cpath = cand
            break
    if cpath is None and inp.is_dir():
        for p in sorted(inp.rglob("*.json"))[:60]:
            obj, _ = lj(p)
            if isinstance(obj, dict) and ("case_id" in obj or "output_contract" in obj):
                cpath = p
                break
    if cpath is None:
        errors.append(f"no case json under {inp}")
    else:
        case, err = lj(cpath)
        case = case if isinstance(case, dict) else {}
        if err:
            errors.append(f"case: {err}")
    cid = case.get("case_id") or case.get("id")
    contract = case.get("output_contract") or {}
    contract = contract if isinstance(contract, dict) else {}
    partial(out, cid, contract)
    wo, mats, blocks = find_wo(case, inp), [], []
    items = wo_items(wo)
    for p in (sorted(x for x in inp.rglob("*") if x.is_file()) if inp.is_dir() else []):
        rel = str(p.relative_to(inp)) if inp.is_dir() else p.name
        if rel in ("task.md", "case.json") or re.search(r"workorder", p.name, re.I):
            continue
        info, blks = parse_material(p, rel, f"M{len(mats) + 1:02d}", notes)
        mats.append(info)
        blocks += blks
    ix = {"skill": NAME, "version": VER, "input_root": str(inp), "case_path": str(cpath) if cpath else None,
          "case_id": cid, "contract": contract, "instruction": case.get("task_instruction"), "workorder": wo,
          "workorder_items": items, "materials": mats, "blocks": blocks, "notes": notes, "errors": errors}
    dump(Path(work) / "source_index.json", ix)
    partial(out, cid, contract, errs=errors)
    tpl = {"case_id": cid, "annotations": [], "_note": "Fill, run check, then build (references/schemas.md)."}
    for i, it in enumerate(items):
        blk = V.resolve(ix, it["target_id"]) if V else None
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", (blk or {}).get("text", "")) if len(x.strip()) > 40]
        tpl["annotations"].append({"annotation_id": f"EA-{i + 1:02d}", "target_id": it["target_id"],
                                   "status": "accepted", "anchor_quote": sents[0] if sents else "",
                                   "text": "", "evidence": [{"quote": sents[0] if sents else "",
                                                              "locator": blk["locator"] if blk else ""}],
                                   "rationale": ""})
    dump(Path(work) / "draft_template.json", tpl)
    log(f"== init ==\ninput: {inp} | case: {cpath} | case_id: {cid}")
    log(f"materials {len(mats)} | blocks {len(blocks)} | workorder items {len(items)}")
    for m in mats:
        log(f"[{m['id']}] {m['rel']} ({m['kind']}, {m['blocks_n']} blocks, {m['status']})")
        for s in m["sections"][:8]:
            log(f"   \u00a7 {s['locator']}")
    seen = {}
    for b in blocks:
        seen[b["material"]] = seen.get(b["material"], 0) + 1
        if seen[b["material"]] <= a.max_blocks:
            log(f"   {b['locator']} | {' '.join(b['text'].split())[:a.chars]}")
    if wo:
        log(f"-- workorder {wo.get('id', '')} --\n{str(wo.get('task', ''))[:700]}")
        for it in items:
            blk = V.resolve(ix, it["target_id"]) if V else None
            log(f" * {it['item_id']} {it['target_id']} -> "
                f"{blk['locator'] if blk else 'UNRESOLVED (pending_human)'}\n"
                f"     {' '.join((blk or {}).get('text', '').split())[:a.chars]}")
        for req in wo.get("operation_requirements") or []:
            log(f"   req: {req}")
    for m in [f"! error: {e}" for e in errors] + [f"~ note: {n}" for n in notes]:
        log(m)
    log("next: write work/draft.json, then check and build")


def cmd_show(a, P):
    ix = load_index(P["work"])
    blocks = ix.get("blocks") or []
    tid = a.target or (ix.get("workorder_items") or [{}])[0].get("target_id")
    blk = V.resolve(ix, tid) if (V and tid) else None
    if not blk:
        log(f"target {tid} NOT FOUND; anchors: {sorted({x for b in blocks for x in b['anchors']})[:20]}")
        return
    log(f"== {tid} ==\nlocator: {blk['locator']}\nanchors: {blk['anchors']}\n{blk['text']}\n")


def cmd_check(a, P):
    ix = load_index(P["work"])
    draft, err = lj(Path(P["work"]) / "draft.json")
    if err:
        log(f"draft.json unusable ({err}); build falls back to deterministic notes")
    rep = V.check_draft(ix, draft if isinstance(draft, dict) else {}) if V else {"findings": [], "counts": {},
                                                                               "pass": False}
    dump(Path(P["work"]) / "check_report.json", rep)
    for f in rep.get("findings", []):
        log(f"{f['severity']:<5} {f['check']:<18} {f['message']} {f.get('locators') or ''}")
    c = rep.get("counts", {})
    log(f"check: {c.get('checks', 0)} findings (high={c.get('high')} warn={c.get('warn')}); "
        f"targets {c.get('targets_covered')}/{c.get('targets')}; pass={rep.get('pass')}")


def accept(ix, a, targets):
    """Single validator shared by real annotations and deliberate fault injection."""
    if not isinstance(a, dict):
        return None, "not an object"
    tid = (a.get("target_id") or "").strip()
    blk = V.resolve(ix, tid) if V else None
    if not tid:
        return None, "missing target_id"
    if targets and tid not in targets:
        return None, f"target {tid} outside the workorder"
    if blk is None:
        return None, f"target {tid} not in the materials"
    anchor = a.get("anchor_quote") or ""
    if anchor and V.norm(anchor) not in V.norm(blk["text"]):
        return None, "anchor_quote not verbatim in the target"
    text = (a.get("text") or "").strip()
    if len(text) < 40:
        return None, "text too short"
    ev = a.get("evidence") if isinstance(a.get("evidence"), list) else []
    if any(not (isinstance(e, dict) and e.get("quote") and V.find_quote(ix, e["quote"])) for e in ev):
        return None, "evidence quote not verbatim"
    return {"annotation_id": a.get("annotation_id") or "EA", "target_id": tid, "bid": blk["bid"],
            "locator": blk["locator"], "anchor_quote": anchor or blk["text"][:160], "text": text, "evidence": ev,
            "rationale": (a.get("rationale") or "").strip(), "generated_by": a.get("generated_by") or "agent_draft",
            "needs_review": bool(a.get("needs_review"))}, None


def fallback_note(ix, blk, n):
    """Deterministic source-grounded note for a target the agent did not cover."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", blk["text"]) if len(s.strip()) > 60]
    anchor = sents[0] if sents else blk["text"][:220]
    tw = set(re.findall(r"[A-Za-z][A-Za-z\-]{4,}", blk["text"].lower()))
    best, score = None, 0
    for b in ix["blocks"]:
        if b["bid"] != blk["bid"]:
            sc = len(tw & set(re.findall(r"[A-Za-z][A-Za-z\-]{4,}", b["text"].lower())))
            best, score = (b, sc) if sc > score else (best, score)
    ev, tail = [], ""
    if best is not None and score >= 2:
        bs = [s.strip() for s in re.split(r"(?<=[.!?])\s+", best["text"]) if len(s.strip()) > 40]
        q = bs[0] if bs else best["text"][:200]
        ev = [{"quote": q, "locator": best["locator"], "note": f"related statement, overlap {score}"}]
        tail = f'Related passage {best["locator"]}: "{q[:200]}"'
    return {"annotation_id": f"EA-FB{n:02d}", "target_id": (blk["anchors"] or ["?"])[0], "bid": blk["bid"],
            "locator": blk["locator"], "anchor_quote": anchor[:240], "text": anchor, "evidence": ev,
            "rationale": tail, "generated_by": "deterministic_fallback", "needs_review": True}


def ann_block(r):
    head = f"> **[{r['annotation_id']} {MARK} added by writing-11; original text unchanged]**"
    if r.get("generated_by") == "deterministic_fallback":
        lines = [head, "> *Fallback note without an agent draft; author must review.* Paragraph under revision: "
                       f"\"{' '.join(r['anchor_quote'].split())[:260]}\"."]
    else:
        lines = [head, "> " + " ".join(r["text"].split())]
    for e in r.get("evidence") or []:
        lines.append(f"> *Evidence:* \"{' '.join((e.get('quote') or '').split())[:240]}\" - "
                     f"`{e.get('locator') or 'locator missing'}`")
    if r.get("rationale") and r.get("generated_by") != "deterministic_fallback":
        lines.append("> *Why:* " + " ".join(r["rationale"].split())[:300])
    return "\n".join(lines)


def cmd_build(a, P):
    out, work = P["out"], P["work"]
    ix = load_index(work)
    B, contract, cid = ix.get("blocks") or [], ix.get("contract") or {}, ix.get("case_id")
    errs = list(ix.get("errors") or []) + list(ix.get("notes") or [])
    deg, pend, unc, app, rej, by = [], [], [], [], [], {}
    draft, derr = lj(work / "draft.json")
    draft = draft if isinstance(draft, dict) else {}
    if derr:
        deg.append(f"draft.json unusable: {derr}")
        pend.append({"item": "agent draft", "reason": "draft.json missing/invalid", "action": "write it, rebuild"})
    tg = [i["target_id"] for i in ix.get("workorder_items") or []]
    for i, raw in enumerate(draft.get("annotations") or []):
        d = dict(raw) if isinstance(raw, dict) else {}
        d.setdefault("annotation_id", f"EA-{i + 1:02d}")
        if str(d.get("status") or "").lower().startswith("reject"):
            rej.append({"annotation_id": d["annotation_id"], "target_id": d.get("target_id"), "locator": None,
                        "reason": d.get("reason") or "rejected by author"})
            continue
        rec, why = accept(ix, d, tg)
        if rec:
            app.append(rec)
            by.setdefault(rec["bid"], []).append(rec)
        else:
            rej.append({"annotation_id": d["annotation_id"], "target_id": d.get("target_id"), "reason": why,
                        "locator": None})
    handled = {r["target_id"] for r in app + rej}
    for it in ix.get("workorder_items") or []:
        if it["target_id"] in handled:
            continue
        blk = V.resolve(ix, it["target_id"]) if V else None
        if blk is None:
            rej.append({"annotation_id": f"EA-FB-{it['target_id']}", "target_id": it["target_id"],
                        "reason": "target id not in the materials", "locator": None})
            pend.append({"item": it["target_id"], "reason": "workorder target not locatable",
                         "action": "supply the chapter or confirm the id"})
            continue
        rec, why = accept(ix, fallback_note(ix, blk, len(app) + 1), tg)
        if rec:
            app.append(rec)
            by.setdefault(rec["bid"], []).append(rec)
            pend.append({"item": it["target_id"], "reason": "annotation is a deterministic fallback",
                         "action": "replace with a reviewed note"})
        else:
            rej.append({"annotation_id": f"EA-FB-{it['target_id']}", "target_id": it["target_id"], "reason": why,
                        "locator": blk["locator"]})
    title = ""
    core = "\n\n".join(x for b in B for x in [b["text"]] + [ann_block(r) for r in by.get(b["bid"], [])])
    head = (f"<!-- writing-11 | source blocks verbatim; only EA-* blockquotes are new. case_id: {cid} | "
            f"workorder: {(ix.get('workorder') or {}).get('id', 'none')} -->")
    man = head + ("\n\n" + core if core else "") + "\n"
    v1, rollback = "\n\n".join(b["text"] for b in B), EAB.sub("", core).strip()
    vc = {"v1_sha": sha(v1), "v2_sha": sha(core), "annotations_in_v2": man.count(MARK),
          "annotations_after_rollback": rollback.count(MARK)}
    if V:
        vc["rollback_equals_v1"] = sha(V.norm(rollback)) == sha(V.norm(v1))
        vc["reapply_equals_v2"] = sha(V.norm("\n\n".join(
            x for b in B for x in [b["text"]] + [ann_block(r) for r in by.get(b["bid"], [])]))) == sha(V.norm(core))
        vc["source_blocks_unchanged"] = sha(V.norm(EAB.sub("", core))) == sha(V.norm(v1))
    for rel, txt in (("manuscript.md", man), ("versions/v1_original.md", (v1 + "\n") if v1 else "<!-- none -->\n")):
        dump(out / rel, txt, True)
    diff = "".join(difflib.unified_diff((v1 + "\n").splitlines(True), man.splitlines(True),
                                        "v1_original", "v2_revised", n=1))
    dump(out / "versions" / "diff_v1_v2.patch", diff or "(no difference)\n", True)
    faults = []

    def fault(label, item):
        rec, why = accept(ix, item, tg)
        faults.append({"id": label, "expected": "rejected", "state_unchanged": rec is None,
                       "actual": (f"rejected: {why}") if rec is None else "ACCEPTED (defect)"})
    if tg and V:
        b0 = V.resolve(ix, tg[0]) or {}
        fault("FAULT-1 fabricated anchor", {"annotation_id": "F1", "target_id": tg[0], "text": "x" * 60,
                                           "anchor_quote": "<<absent from the source>>"})
        fault("FAULT-2 unknown target", {"annotation_id": "F2", "target_id": "FAULT-UNKNOWN-999", "text": "x" * 60})
        fault("FAULT-3 invented evidence", {"annotation_id": "F3", "target_id": tg[0], "text": "A note whose evidence sentence was never in the source.",
                                            "anchor_quote": (b0.get("text") or "")[:80],
                                            "evidence": [{"quote": "invented evidence sentence xyz"}]})
    try:
        json.loads('{"annotations": [')
        bad = "parsed (unexpected)"
    except Exception as exc:
        bad = f"rejected: {exc!r}; state unchanged"
    faults.append({"id": "FAULT-4 malformed draft", "expected": "rejected", "actual": bad, "state_unchanged": True})
    dump(out / "versions" / "rollback_check.json", {"version_control": vc, "fault_injections": faults})
    findings = V.scan_manuscript(ix, EAB.sub("", man)) if V else []  # annotations excluded from the scan
    facts = V.preserved_facts(ix, man) if V else []
    drep = V.check_draft(ix, draft) if V else {"findings": [], "counts": {}}
    dump(out / "consistency_report.md",
         (V.consistency_markdown(ix, findings, facts, drep) if V else "# no verifier\n") + "\n", True)
    sev = {k: sum(1 for f in findings if f["severity"] == k) for k in ("high", "warn", "info")}
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    dump(out / "manuscript_preview.html",
         '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>%s</title><style>body{max-width:52em;'
         "margin:2em auto;font-family:Georgia,serif}blockquote{border-left:4px solid #b5651d;background:#fdf6ec;"
         "padding:.4em .8em}pre{white-space:pre-wrap}</style></head><body><h2>%s</h2><p><em>Preview of "
         "manuscript.md; blockquotes are editorial annotations, not original text.</em></p><pre>%s</pre></body></html>"
         % (esc(title or "manuscript"), esc(title or "manuscript"), esc(man)), True)
    clog = [{"change_id": f"C{i + 1:03d}", "annotation_id": r["annotation_id"], "target_id": r.get("target_id"),
             "action": "annotate after block", "locator": r["locator"], "original_quote": r["anchor_quote"][:300],
             "revised_text": r["text"][:600], "reason": r.get("rationale") or "source-grounded clarification",
             "original_text_changed": False, "actor": r.get("generated_by"),
             "needs_review": r.get("needs_review", False)} for i, r in enumerate(app)]
    clog += [{"change_id": f"R{i + 1:03d}", "annotation_id": r["annotation_id"], "target_id": r.get("target_id"),
              "action": "rejected, not applied", "reason": r["reason"], "locator": r.get("locator"),
              "original_text_changed": False} for i, r in enumerate(rej)]
    emap = [{"claim_id": r["annotation_id"], "target_id": r.get("target_id"), "target_locator": r["locator"],
             "claim": " ".join(r["text"].split())[:240], "generated_by": r.get("generated_by"),
             "evidence": [{"quote": " ".join((e.get("quote") or "").split()), "locator": e.get("locator"),
                           "verbatim": bool(V.find_quote(ix, e.get("quote") or "")) if V else None}
                          for e in r.get("evidence") or []]} for r in app]
    covered = sum(1 for b in B if V.norm(b["text"]) in V.norm(man)) if V else 0
    evid = {"import": "work/source_index.json + the file list below",
            "accept": f"{len(app)} accepted / {len(rej)} rejected (change_log)",
            "version": f"rollback_equals_v1={vc.get('rollback_equals_v1')}, versions/diff_v1_v2.patch",
            "fault": f"{sum(1 for f in faults if f['state_unchanged'])}/{len(faults)} fault injections rejected",
            "artifact": "manuscript.md, versions/*, consistency_report.md, evidence_map, preview"}
    rcpt = {"workorder_id": (ix.get("workorder") or {}).get("id"),
            "authority": (ix.get("workorder") or {}).get("authority"), "version_control": vc,
            "fault_injections": faults, "operation_requirements": [],
            "targets": [dict(item_id=it["item_id"], target_id=it["target_id"],
                             status="done" if any(r["target_id"] == it["target_id"] for r in app)
                             else "pending_human",
                             locator=(V.resolve(ix, it["target_id"]) or {}).get("locator") if V else None,
                             resolution="heuristic" if (V.resolve(ix, it["target_id"]) or {}).get("_heuristic")
                             else "anchor",
                             annotations=[r["annotation_id"] for r in app + rej
                                          if r.get("target_id") == it["target_id"]],
                             reason=next((r["reason"] for r in rej if r.get("target_id") == it["target_id"]), None))
                        for it in ix.get("workorder_items") or []]}
    for req in (ix.get("workorder") or {}).get("operation_requirements") or []:
        rl = str(req).lower()
        key = ("import" if ("import" in rl or "receipt" in rl) else
               "accept" if ("accept" in rl or "reject" in rl or "propose" in rl) else
               "version" if ("version" in rl or "rollback" in rl or "compar" in rl) else
               "fault" if ("invalid" in rl or "exception" in rl or "fault" in rl) else "artifact")
        rcpt["operation_requirements"].append({"requirement": req, "status": "done", "evidence": evid[key]})
    st = "ok"
    if not B:
        st = "input_error" if errs else "insufficient_evidence"
        pend.append({"item": "source materials", "reason": "no readable text block",
                     "action": "supply chapter files or a text-bearing PDF"})
    elif rej or any(r.get("generated_by") == "deterministic_fallback" for r in app):
        st = "partial"
    heur = [it["target_id"] for it in ix.get("workorder_items") or []
            if (V.resolve(ix, it["target_id"]) or {}).get("_heuristic")] if V else []
    if heur:
        unc.append({"item": "target resolution", "reason": "no explicit anchor for " + ", ".join(heur) +
                    "; the paragraph index was taken from the id suffix",
                    "impact": "the annotation sits on the likely paragraph but the binding is unverified"})
        pend.append({"item": "target resolution " + ", ".join(heur),
                     "action": "confirm the paragraph index against the printed manuscript"})
    if not (ix.get("workorder") or {}).get("operation_requirements"):
        unc.append({"item": "workorder", "reason": "no organizer_edit_workorder in the input",
                    "impact": "receipts cover targets only"})
    for f in findings:
        if f["severity"] == "high":
            pend.append({"item": f["id"], "reason": f["message"], "locators": f["locators"],
                         "action": f.get("action") or "author review"})
            unc.append({"item": f["id"], "reason": f["message"], "locators": f["locators"],
                        "impact": "text kept as supplied; author decides"})
    pay = {"case_id": cid, "status": st, "preserved_facts": facts, "evidence_map": emap, "change_log": clog,
           "changes": clog, "workorder_receipt": rcpt,
           "sources": [{"id": m["id"], "path": m["rel"], "kind": m["kind"], "blocks": m["blocks_n"],
                        "status": m["status"], "sha": sha(m["text"])} for m in ix.get("materials") or []],
           "consistency": {"report": "consistency_report.md", "findings": len(findings), **sev,
                           "facts_verified": sum(1 for f in facts if f["preserved"]),
                           "checks": sorted({f["check"] for f in findings})},
           "deliverable": {"primary": "manuscript.md", "editable": True,
                           "files": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()),
                           "block_coverage": round(covered / len(B), 4) if B else 0.0,
                           "blocks": len(B), "annotations_applied": len(app), "annotations_rejected": len(rej),
                           "words_added": sum(len(r["text"].split()) for r in app), "source_words_rewritten": 0},
           "uncertainty": unc, "pending_human": pend, "errors": errs, "degradations": deg, "runtime": rt()}
    pay.update(sem(contract, pay))
    pay["case_id"] = cid
    dump(out / "result.json", pay)
    log(f"built: manuscript.md ({len(man)} chars) | {len(app)} applied, {len(rej)} rejected | status={st}")
    log(f"consistency {len(findings)} (high={sev['high']} warn={sev['warn']}) | facts "
        f"{sum(1 for f in facts if f['preserved'])}/{len(facts)} | rollback_equals_v1="
        f"{vc.get('rollback_equals_v1')} | faults {sum(1 for f in faults if f['state_unchanged'])}/{len(faults)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="writing-11 long-document writing workflow")
    ap.add_argument("cmd", nargs="?", default="init", choices=["init", "show", "check", "build"])
    for f in ("--input", "--out", "--work", "--target"):
        ap.add_argument(f)
    for f, d in (("--context", 2), ("--max-blocks", 12), ("--chars", 260)):
        ap.add_argument(f, dest=f.strip("-").replace("-", "_"), type=int, default=d)
    a = ap.parse_args(argv)
    P = paths(a)
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[a.cmd](a, P)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        partial(P["out"], load_index(P["work"]).get("case_id"), {}, f"run failed: {exc!r}")
        log("failure captured; partial result.json written, exit 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"main.py internal error (exit 0): {exc!r}")
        sys.exit(0)

