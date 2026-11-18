#!/usr/bin/env python3
"""main.py - graphical abstract: init | show | check | build.
init indexes /input -> index.json + partial result.json; show prints paragraphs
with locators; check tests coverage/evidence/invented numbers; build renders
SVG+PDF(+PNG) + content_map + compliance + final result.json.
stdlib only, offline, CWD independent; exits 0 and writes result.json."""
import argparse, hashlib, json, re, shutil, subprocess, sys, time, traceback, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import draw
    DRAW_ERR = ""
except Exception as exc:
    draw, DRAW_ERR = None, str(exc)

IN, WORK, OUT = "/input", "/app/work", "/app/output"
ROLES = ("problem", "method", "results", "implication")
CKEY = ("output_contract", "outputcontract", "contract", "output_fields", "required_outputs")
FIELDS = [(a, b.split(",")) for a, b in (x.split("=") for x in (
    "content_map=content_map,element_map,mapping,provenance|compliance_checks=compliance,checks,export_check|"
    "exceptions=exception,deviation,issue,limitation|sources=sources,references|"
    "editable_source=editable,svg,vector,source|export_artifact=export,artifact,pdf,png,deliverable|"
    "figure_caption=caption,legend|problem=problem,question|method=method,approach|"
    "results=result,finding|implication=implication,conclusion,takeaway|uncertainty=uncertaint").split("|"))]


def norm(s):
    s = re.sub(r"[\u2018\u2019]", "'", str(s or ""))
    return re.sub(r"\s+", " ", re.sub(r"[\u201c\u201d]", '"', s).replace("\u00a0", " ")).strip()


def loose(s):
    return re.sub(r"\s+", "", re.sub(r"-\s*\n\s*", "", str(s or ""))).lower()


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def sem(o, names, d=0):
    if d > 4 or not isinstance(o, (dict, list)):
        return None
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower().replace("-", "_").strip() in names:
                return v
        o = list(o.values())
    return next((r for r in (sem(v, names, d + 1) for v in o[:25]) if r is not None), None)


def load_case(ind):
    ind, d = Path(ind), {"case": {}, "case_path": None, "task_text": "", "errors": []}
    for name in ("case.json", "task.md"):
        f = ind / name
        if not f.is_file():
            c = sorted(ind.rglob("*" + name[4:])) if ind.exists() else []
            f = c[0] if c else None
        if f is None:
            continue
        try:
            if name == "case.json":
                d["case"], d["case_path"] = rj(f), str(f)
            else:
                d["task_text"] = f.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            d["errors"].append(f"{name} unreadable: {e}")
    return d


def build_index(ind):
    """Walk /input; text and PDF become locator-tagged paragraphs."""
    ind, mats, paras = Path(ind), [], []
    for p in sorted(x for x in ind.rglob("*") if x.is_file()) if ind.exists() else []:
        low = p.name.lower()
        if low in ("case.json", "task.md") or (low.startswith("case") and low.endswith(".json")):
            continue
        rel, sid = str(p.relative_to(ind)), f"m{len(mats) + 1}"
        head = p.open("rb").read(512) if p.stat().st_size else b""
        kind = "pdf" if head[:4] == b"%PDF" else ("binary" if b"\x00" in head else "text")
        rec = {"sid": sid, "name": rel, "kind": kind, "bytes": p.stat().st_size,
               "sha1": hashlib.sha1(p.read_bytes()).hexdigest()[:16], "paras": 0, "method": "utf-8 text"}
        ps = []
        try:
            if kind == "text":
                txt = p.read_text(encoding="utf-8-sig", errors="replace")
                sep = r"\n" if p.suffix.lower() in (".csv", ".tsv") else r"\n\s*\n"
                ps = [{"sid": sid, "locator": f"para.{i + 1}", "text": b.strip()}
                      for i, b in enumerate(re.split(sep, txt)) if len(b.strip()) > 2]
            elif kind == "pdf":
                ps, rec["method"] = pdf_paras(p, sid)
            else:
                rec["method"] = f"{kind}: not parsed - convert to PDF/CSV, never invent content"
            for q in ps:
                q["source"] = rel
        except Exception as e:
            ps, rec["method"] = [], f"extraction failed: {e}"
        rec["paras"] = len(ps)
        mats.append(rec)
        paras += ps
    return {"materials": mats, "paragraphs": paras}


def pdf_paras(p, sid):
    exe = shutil.which("pdftotext")
    try:
        r = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, timeout=90) if exe else None
        txt = r.stdout.decode("utf-8", "replace") if r else ""
        if txt.strip():
            return [{"sid": sid, "source": p.name, "locator": f"p.{pi + 1} b{k + 1}", "text": b.strip()}
                    for pi, pg in enumerate(txt.split("\f")) for k, b in enumerate(re.split(r"\n\s*\n", pg))
                    if len(b.strip()) > 1], "pdftotext -layout; locator = p.<page> b.<block>"
    except Exception:
        pass
    return [], "PDF text not extracted: read the page and quote it, never invent text"


def match(ev, paras, full):
    ev = ev or {}
    q, dec = norm(ev.get("quote")), norm(ev.get("locator"))
    if len(q) < 4:
        return {"status": "no_quote", "locator": dec, "source": ev.get("source"), "note": "quote under 4 chars"}
    cands = [p for p in paras if loose(q) in loose(p["text"])]
    for p in cands:
        if dec and dec == p["locator"]:
            return {"status": "verified", "locator": p["locator"], "source": p["source"], "quote": q, "note": ""}
    if cands:
        p = cands[0]
        return {"status": "verified" if not dec else "relocated", "locator": p["locator"], "source": p["source"], "quote": q,
                "note": "" if not dec else f"'{dec}' did not hold it; corrected to '{p['locator']}'"}
    return {"status": "unverified", "locator": dec, "source": ev.get("source"), "quote": q,
            "note": "quote not found verbatim in any indexed paragraph"}


def evaluate(plan, paras):
    """Annotate every item with _m (evidence match) and _eid; return counts + problems."""
    full, probs, n, ok = {}, [], 0, 0
    for p in paras:
        full[p["source"]] = full.get(p["source"], "") + loose(p["text"])
    for pi, pn in enumerate(plan.get("panels") or []):
        pid = str(pn.get("id") or f"P{pi + 1}") if isinstance(pn, dict) else f"P{pi + 1}"
        for ii, it in enumerate((pn.get("items") if isinstance(pn, dict) else None) or []):
            if not isinstance(it, dict):
                continue
            n += 1
            eid = it["_eid"] = str(it.get("id") or f"{pid}-I{ii + 1}")
            m = it["_m"] = match(it.get("evidence"), paras, full)
            bad = sorted({x for x in re.findall(r"\d+(?:[.,]\d+)?", norm(" ".join(str(it.get(k) or "")
                        for k in ("label", "value", "detail")))) if x not in (m.get("quote") or "")})
            if bad:
                probs.append(f"{eid}: number(s) {bad} not in its quote")
            if m["status"] not in ("verified", "relocated"):
                probs.append(f"{eid}: {m['status']} - {m['note']}")
            ok += m["status"] in ("verified", "relocated")
    return n, ok, probs


def fallback_plan(index, case, task_text):
    sents = [(s, p) for p in index.get("paragraphs") or [] if not norm(p["text"]).startswith(("#", "|"))
             for s in re.split(r"(?<=[.!?])\s+", norm(p["text"])) if 60 <= len(s) <= 320]
    used, panels = set(), []
    for role in ROLES:
        pick = next(((j, s, p) for j, (s, p) in enumerate(sents) if j not in used), None)
        if pick:
            used.add(pick[0])
            panels.append({"id": f"P{len(panels) + 1}", "role": role, "heading": role.title(), "items": [
                {"id": f"P{len(panels) + 1}-I1", "kind": "text", "detail": pick[1],
                 "evidence": {"source": pick[2]["source"], "locator": pick[2]["locator"], "quote": pick[1]}}]})
    title = norm(sem(case, ("title", "case_title", "paper_title"))) or next(
        (l.strip("# ").strip() for l in (task_text or "").splitlines() if l.strip().startswith("#")), "")
    return {"title": title[:140] or "Graphical abstract", "panels": panels or [
        {"id": "P1", "role": "other", "heading": "Note", "items": [
            {"id": "P1-I1", "kind": "text", "label": "No usable text material",
             "detail": "No quotable sentence was supplied, so nothing was asserted."}]}],
            "subtitle": "Auto-extracted fallback figure - quotes are verbatim, curation is minimal.",
            "caption": "Fallback build: text is quoted from the supplied material; see content_map.json."}


def fill_contract(contract, payload):
    keys = list(contract.keys()) if isinstance(contract, dict) else [str(k) for k in (contract or [])]
    out, um = {}, []
    for k in keys:
        kl, best, score = str(k).lower(), None, 0
        for canon, words in FIELDS:
            s = sum(1 for w in words if w in kl)
            if s > score and payload.get(canon) is not None:
                best, score = canon, s
        out[k] = payload.get(best) if best else None
        if best is None:
            um.append(str(k))
    return out, um


def write_result(out, index, contract, payload, status, errors, degr, changes, t0=None):
    filled, um = fill_contract(contract, payload)
    res = dict(filled)
    for k in ("editable_source", "export_artifact", "content_map", "compliance_checks", "exceptions", "figure_caption"):
        res.setdefault(k, payload.get(k))
    res.update({"case_id": index.get("case_id"), "status": status, "sources": payload.get("sources") or [],
                "uncertainty": payload.get("uncertainty") or [], "pending_human": payload.get("pending_human") or [],
                "errors": errors, "degradations": degr, "changes": changes,
                "runtime": {"tool": "scripts/main.py", "python": sys.version.split()[0], "offline": True,
                            "cwd_independent": True, "elapsed_s": round(time.time() - t0, 2) if t0 else None,
                            "unmatched_contract_fields": um}})
    wj(Path(out) / "result.json", res)
    return res


def _index(ind, work, errs):
    if (Path(work) / "index.json").is_file():
        try:
            i = rj(Path(work) / "index.json")
            if i.get("paragraphs"):
                return i
        except Exception as e:
            errs.append(f"index.json unreadable: {e}")
    c = load_case(ind)
    errs.extend(c["errors"])
    i = build_index(ind)
    i["input_error"] = bool(c["errors"])
    cc = c["case"] if isinstance(c["case"], dict) else {}
    i["case_id"] = next((str(cc[k]) for k in ("case_id", "caseId", "case_name", "id") if k in cc), None) \
        or (Path(c["case_path"]).stem if c["case_path"] else None)
    i["contract"], i["case"] = sem(c["case"], CKEY) or {}, c
    wj(Path(work) / "index.json", i)
    return i


def cmd_init(a):
    t0, work, out = time.time(), Path(a.work), Path(a.output)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    errs = []
    idx = _index(a.input, work, errs)
    cc = idx["case"].get("case") or {}
    write_result(out, idx, idx["contract"], {"sources": []}, "partial", errs,
                 ["result.json written before any figure exists (init step)"],
                 [{"what": "indexed input", "detail": f"{len(idx['materials'])} material(s), {len(idx['paragraphs'])} paragraph(s)"}], t0)
    print(f"[init] case_id={idx['case_id']} contract_fields={len(idx['contract'])} work={work} out={out}")
    v = sem(cc, ("organizer_workorder", "organizer_edit_workorder", "task_instruction", "instruction", "scope"))
    if v:
        print("[init] workorder:", norm(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))[:700])
    for m in idx["materials"]:
        print(f"   {m['sid']:>3} {m['kind']:<9} {m['bytes']:>9}B paras={m['paras']:<4} {m['name']}  [{m['method']}]")
    for p in idx["paragraphs"][:8]:
        print(f"   [{p['sid']}] {p['source']} :: {p['locator']} :: {norm(p['text'])[:170]}")
    print(f"[init] paragraphs={len(idx['paragraphs'])}; NEXT: write work/plan.json (see SKILL.md 7), then check, build")
    return 0


def cmd_show(a):
    idx = rj(Path(a.work) / "index.json")
    ps = idx.get("paragraphs") or []
    if a.sid:
        ps = [p for p in ps if a.sid in (p["sid"], p["source"])]
    if a.grep:
        ps = [p for p in ps if loose(a.grep) in loose(p["text"])]
    print(f"[show] {len(ps)} para; " + ", ".join(f"{m['sid']}={m['name']}" for m in idx.get("materials") or []))
    for p in ps[:int(a.limit)]:
        print(f"--- [{p['sid']}] {p['source']} :: {p['locator']}\n{norm(p['text'])[:int(a.chars)]}")
    return 0


def cmd_check(a):
    work = Path(a.work)
    try:
        plan = rj(work / "plan.json")
        assert isinstance(plan, dict)
    except Exception as e:
        msg = f"work/plan.json missing or invalid: {e}"
        print("[check] FAIL", msg)
        wj(work / "check.json", {"ok": False, "problems": [msg]})
        return 0
    n, ok, probs = evaluate(plan, rj(work / "index.json").get("paragraphs") or [])
    if not norm(plan.get("title")):
        probs.append("title is empty")
    roles = {draw.norm_role(p.get("role") or p.get("heading")) for p in plan.get("panels") or [] if isinstance(p, dict)} if draw else set()
    probs += [f"missing panel role: {r} (problem -> method -> results -> implication)" for r in ROLES if r not in roles]
    if not n:
        probs.append("no items: each panel needs items[] with evidence")
    rep = {"ok": not probs, "problems": probs, "stats": {"panels": len(plan.get("panels") or []), "items": n,
           "verified": ok, "coverage": round(ok / n, 3) if n else 0.0, "roles": sorted(roles)}}
    wj(work / "check.json", rep)
    print(f"[check] panels={rep['stats']['panels']} items={n} verified={ok} coverage={rep['stats']['coverage']}"
          f" -> {'PASS' if not probs else 'NEEDS WORK'}")
    for x in probs:
        print("  FAIL", x)
    print("[check] next:", "main.py build" if not probs else "fix FAILs, re-run check")
    return 0


def _render(plan, out, errs, degr):
    if draw is None:
        errs.append(f"renderer import failed: {DRAW_ERR}")
        return None, {}, None
    try:
        model = draw.build_model(plan)
        svg, pdf, pngp = (out / "graphical_abstract.svg", out / "graphical_abstract.pdf", out / "graphical_abstract.png")
        svg.write_text(draw.to_svg(model), encoding="utf-8")
        pdf.write_bytes(draw.to_pdf(model))
    except Exception as e:
        errs.append(f"render failed: {e}")
        return None, {}, None
    files, png = {"svg": svg, "pdf": pdf}, None
    ok, method, note = draw.to_png(model, str(pngp))
    if not ok and shutil.which("pdftoppm"):
        try:
            subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", str(pdf), str(pngp.with_suffix(""))],
                           check=True, timeout=180)
            ok, method = True, "pdftoppm from the vector PDF"
        except Exception as e:
            note += f" | pdftoppm: {e}"
    if ok and pngp.is_file():
        files["png"] = pngp
        d = pngp.read_bytes()[16:24]
        png = {"path": "graphical_abstract.png", "method": method, "note": note,
               "px": [int.from_bytes(d[:4], "big"), int.from_bytes(d[4:], "big")]}
    else:
        degr.append(f"PNG preview unavailable ({note}); the vector PDF is the export artifact")
    return model, files, png


def _compliance(model, files, png, plan, ok, n):
    st, pal = (model or {}).get("stats") or {}, ["#D55E00", "#0072B2", "#009E73", "#CC79A7"]
    w, h = (draw.W, draw.H) if draw else (None, None)
    return {"canvas_px": [w, h], "min_font": st.get("min_font"), "inside_canvas": (st.get("max_y") or 0) <= (h or 760),
            "text_nodes": st.get("text_ops"), "overflow_dropped": len((model or {}).get("dropped") or []),
            "svg": {"path": "graphical_abstract.svg" if "svg" in files else None, "vector": True,
                    "editable_text": True, "layers": draw.LAYERS if draw else None},
            "pdf": {"path": "graphical_abstract.pdf" if "pdf" in files else None, "pages": 1, "vector": True,
                    "page_pt": [round(w * draw.PS, 1), round(h * draw.PS, 1)] if draw else None,
                    "fonts": "Helvetica base-14 + STSong-Light CID", "embedded": False},
            "png": png, "palette": {"scheme": "Okabe-Ito subset", "values": pal, "cvd_safe": True,
                                    "colour_redundant": "panel headers name each role"},
            "coverage": round(ok / n, 3) if n else 0.0,
            "bytes": {k: x.stat().st_size for k, x in files.items()}}


def cmd_build(a):
    t0, work, out = time.time(), Path(a.work), Path(a.output)
    for d in (work, out):
        d.mkdir(parents=True, exist_ok=True)
    errs, degr, exc, status = [], [], [], "ok"
    idx = _index(a.input, work, errs)
    contract, paras = idx.get("contract") or {}, idx.get("paragraphs") or []
    try:
        plan = rj(work / "plan.json")
        assert isinstance(plan, dict)
    except Exception as e:
        plan = fallback_plan(idx, idx["case"].get("case") or {}, idx["case"].get("task_text"))
        degr.append(f"plan.json missing/invalid ({e}): auto-extracted from verbatim sentences")
        exc.append({"code": "plan_missing", "detail": str(e), "action": "deterministic fallback"})
        status = "partial"
    n, ok, probs = evaluate(plan, paras)
    ev = {it["_eid"]: it["_m"] for pn in plan.get("panels") or [] if isinstance(pn, dict) for it in pn.get("items") or []}
    for pi, pn in enumerate(plan.get("panels") or []):
        if not isinstance(pn, dict):
            continue
        keep = [dict(it, id=it["_eid"]) for it in pn.get("items") or []
                if (it.get("_m") or {}).get("status") in ("verified", "relocated")]
        for it in pn.get("items") or []:
            m = it.get("_m") or {}
            if m.get("status") == "relocated":
                exc.append({"code": "locator_corrected", "detail": f"{it['_eid']}: {m['note']}", "action": f"cite {m['locator']}"})
            elif m.get("status") not in ("verified", "relocated"):
                exc.append({"code": "element_dropped", "detail": f"{it['_eid']}: {m.get('status')} {m.get('note')}",
                            "action": "removed; add a verbatim quote and rebuild"})
        if not keep:
            degr.append(f"panel {pn.get('id') or pi + 1}: no verified evidence (placeholder box)")
            status = "partial"
        pn["items"] = keep or [{"id": f"P{pi + 1}-note", "kind": "text", "label": "No verified evidence",
                                "detail": "Panel left empty: no supplied passage could be quoted verbatim."}]
    model, files, png = _render(plan, out, errs, degr)
    status = "partial" if not model else status
    if (model or {}).get("dropped"):
        degr.append(f"{len(model['dropped'])} item(s) dropped for vertical overflow")
        status = "partial" if status == "ok" else status
    cm = [{"element_id": el["id"], "panel": el["panel"], "role": el["role"], "text": el["text"], "svg_id": f"#{el['id']}",
           "bbox": el["bbox"], "evidence": {k: (ev.get(el["id"]) or {}).get(k)
           for k in ("source", "locator", "quote", "status")}} for el in (model or {}).get("elements") or []]
    checks = _compliance(model, files, png, plan, ok, n)
    wj(out / "content_map.json", cm)
    wj(out / "compliance_checks.json", checks)
    unc = []
    if n and ok < n:
        unc.append(f"{n - ok} of {n} element(s) dropped: quote not found in the material")
        status = "partial" if status == "ok" else status
    if not paras:
        status = "input_error" if idx.get("input_error") else "insufficient_evidence"
        unc.append("no parseable material under /input; nothing scientific was asserted")
    payload = {"sources": [{"id": m["sid"], "name": m["name"], "kind": m["kind"], "sha1": m["sha1"],
                            "paragraphs": m["paras"]} for m in idx.get("materials") or []],
               "editable_source": "graphical_abstract.svg" if model else None,
               "export_artifact": {"pdf": "graphical_abstract.pdf", "png": png["path"] if png else None,
                                   "pages": 1} if model else None,
               "content_map": cm, "compliance_checks": checks, "exceptions": exc,
               "figure_caption": plan.get("caption") or plan.get("subtitle") or plan.get("title"),
               "uncertainty": unc, "pending_human": [x["detail"] for x in exc if x["code"] == "element_dropped"]}
    write_result(out, idx, contract, payload, status, errs, degr,
                 [{"what": "figure built", "detail": f"{len(cm)} traced element(s), {len(plan.get('panels') or [])} panel(s)"},
                  {"what": "exports", "detail": ", ".join(sorted(files)) or "none"},
                  {"what": "evidence", "detail": "each element: source + locator + verbatim quote; drops listed in exceptions"}], t0)
    print(f"[build] status={status} elements={len(cm)} rejected={n - ok} "
          f"files={{{', '.join(f'{k}:{v.stat().st_size}B' for k, v in files.items())}}}")
    for x in errs + degr:
        print("  NOTE", x)
    return 0


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    for k in ("input", "work", "output"):
        common.add_argument("--" + k, default=None)
    ap = argparse.ArgumentParser(prog="main.py", description="graphical abstract: init/show/check/build")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init", parents=[common], help="index /input + partial result.json")
    sh = sub.add_parser("show", parents=[common], help="print material text with locators")
    for k, dv in (("sid", ""), ("grep", ""), ("limit", 40), ("chars", 600)):
        sh.add_argument("--" + k, default=dv)
    sub.add_parser("check", parents=[common], help="validate work/plan.json")
    sub.add_parser("build", parents=[common], help="render SVG/PDF/PNG + result.json")
    a = ap.parse_args(argv)
    a.input, a.work, a.output = a.input or IN, a.work or WORK, a.output or OUT
    cmd = a.cmd or "init"
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[cmd](a)
    except SystemExit:
        return 0
    except Exception:
        tb = traceback.format_exc()
        try:
            Path(a.output).mkdir(parents=True, exist_ok=True)
            idx = rj(Path(a.work) / "index.json") if (Path(a.work) / "index.json").is_file() else {"case_id": None}
            write_result(Path(a.output), idx, idx.get("contract") or {}, {"sources": []}, "partial",
                         [f"{cmd} crashed: {tb.splitlines()[-1]}"], [tb[-900:]], [], time.time())
        except Exception:
            pass
        print(f"[{cmd}] failed, result.json finalised:\n{tb}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
