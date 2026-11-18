"""academic-format-template-adapter - apply a journal/thesis format template to a
manuscript and deliver an editable docx + evidence.

Commands: init (index + requirements checklist + partial result.json) ->
          [Agent writes work/spec_table.json] -> check -> build (always finalizes).
Standard library only. Exit code is always 0; state lives in result.json.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docxlib as D

VER = "3.0.0"
DEFD = ("/input", "/app/work", "/app/output")
SKIP = {"output", "work", "__MACOSX", ".git"}
TITLE = "格式适配产物 / format adaptation product"

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def jd(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")

def jl(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return None

def br(x, n=420):
    s = D.nm(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))
    return s[:n] + ("..." if len(s) > n else "")

def paths(a):
    g = lambda k, d: Path(getattr(a, k, None) or os.environ.get(
        "SKILL_" + k.upper() + "_DIR") or d)
    return g("input", DEFD[0]), g("work", DEFD[1]), g("out", DEFD[2])

def discover(indir):
    indir = Path(indir)
    if not indir.exists():
        return []
    out = []
    for p in sorted(indir.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(indir)
        if set(rel.parts) & SKIP:
            continue
        out.append(p)
    return out[:80]

BAD_CASE = []

def load_case(indir):
    for c in [Path(indir) / "case.json"] + sorted(Path(indir).rglob("case*.json")) + \
            sorted(Path(indir).rglob("task.md")):
        if not c.is_file():
            continue
        if c.suffix.lower() == ".json":
            o = jl(c)
            if isinstance(o, dict):
                return o, c
            BAD_CASE.append({"stage": "case", "file": str(c), "reason":
                             "invalid JSON; continuing with directory scan and task.md"})
        else:
            return {"_task_md": D.rt(c)}, c
    return {}, None

def get(case, *keys):
    for k, v in case.items():
        l = k.lower()
        if any(s in l for s in keys) and v not in (None, "", [], {}):
            return v
    return None

def build_index(indir):
    mats, seeds, txt_cache = [], [], {}
    for i, p in enumerate(discover(indir), 1):
        mid = "m%02d" % i
        t, blocks, note = D.load(p)
        text = "\n".join(b.get("text") or "" for b in blocks) if t != "text" else \
            D.rt(p)
        if t == "tex":
            text = D.tex(D.rt(p))
        items = D.mine(text, mid, p.name) if text.strip() else []
        if t == "docx":
            items += D.tpl(p, mid, p.name)
        chars = sum(len(b.get("text") or "") for b in blocks) + \
            sum(len(" ".join(r)) for b in blocks for r in (b.get("rows") or []))
        mats.append({"id": mid, "name": p.name, "path": str(p), "type": t,
                     "n_blocks": len(blocks), "chars": chars, "note": note,
                     "blocks": blocks[:600], "items": items[:80],
                     "n_items": len(items),
                     "hint": bool(re.search(r"templ|模板|requir|format|spec|规定|要求|须知|"
                                            r"guide|author", p.name.lower()))})
    cand = [m for m in mats if m["type"] in ("docx", "text", "tex", "pdf")
            and m["chars"] > 30]
    for m in cand:
        m["_s"] = m["chars"] * (1.3 if m["type"] == "docx" else 1.0) * \
            (0.05 if m["hint"] else 1.0) * (0.3 if m["n_items"] >= 3 else 1.0)
    man = max(cand, key=lambda m: m["_s"]) if cand else None
    for m in mats:
        m.pop("_s", None)
    reqs = sorted([m for m in mats if m["items"] and m is not man],
                  key=lambda m: -m["n_items"])
    for m in mats:
        m["role"] = ("manuscript" if m is man else
                     "format_source" if m in reqs else "material")
    return {"case_id": "unknown", "materials": mats, "manuscript": man["id"] if man else None,
            "spec_sources": [m["id"] for m in reqs], "seeds": [],
            "conflicts": [], "created": now(), "version": VER,
            "dirs": {"input": str(indir)}}

def resolve_seeds(idx):
    """Order candidates: format sources by item count, then first-wins per field."""
    mats = {m["id"]: m for m in idx["materials"]}
    srcs = [mats[i] for i in idx.get("spec_sources") or [] if i in mats]
    seeds, conflicts, seen = [], [], {}
    for m in srcs:
        for it in m["items"]:
            f, v = it["field"], it["value"]
            if f in seen:
                if seen[f]["value"] != v:
                    conflicts.append({"field": f, "kept": {"value": seen[f]["value"],
                                                           "locator": seen[f]["locator"]},
                                      "other": {"value": v, "locator": it["locator"]},
                                      "rule": "first format source wins; both recorded"})
                continue
            seen[f] = it
            seeds.append(it)
    return seeds, conflicts[:40]

def qhit(mats, quote, mid=None, cache=None):
    q = D.sq(quote)
    if len(q) < 4:
        return None
    for m in mats:
        if mid and m["id"] != mid:
            continue
        k = m["path"]
        if cache is not None and k not in cache:
            cache[k] = D.sq(D.rawq(m["path"]))
        hay = cache[k] if cache is not None else D.sq(D.rawq(m["path"]))
        if q in hay:
            return m["id"]
    return None

def reconcile(idx, plan, cache=None, degr=None, pend=None, errs=None):
    """Agent spec table first, then mined seeds, then documented defaults."""
    degr = degr if degr is not None else []
    pend = pend if pend is not None else []
    mats, chosen = idx["materials"], {}
    items = (plan or {}).get("spec") or (plan or {}).get("format_spec") or \
        (plan or {}).get("items") or []
    rej = 0
    for it in (items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            continue
        f = str(it.get("field") or it.get("id") or it.get("key") or "").strip()
        if f not in D.ORDER:
            degr.append({"stage": "spec", "field": f, "reason": "unknown field; ignored"})
            continue
        v = it.get("value", it.get("val"))
        if v in (None, ""):
            continue
        q = str(it.get("quote") or it.get("evidence_quote") or "").strip()
        mid = str(it.get("source") or it.get("material") or "").strip() or None
        if q:
            hit = qhit(mats, q, mid, cache)
            if not hit:
                rej += 1
                degr.append({"stage": "spec", "field": f, "quote": q[:120],
                             "reason": "quote not verbatim in source; agent item rejected"})
                continue
            chosen[f] = {"field": f, "value": D.canon(f, v), "source": hit,
                         "locator": str(it.get("locator") or "%s#quote" % hit),
                         "quote": q[:200], "status": "explicit", "by": "agent"}
        else:
            chosen[f] = {"field": f, "value": D.canon(f, v), "source": mid,
                         "locator": str(it.get("locator") or ""), "quote": "",
                         "status": "inferred", "by": "agent"}
    seeds, conflicts = resolve_seeds(idx)
    for s in seeds:
        if s["field"] not in chosen:
            chosen[s["field"]] = dict(s, status="explicit", by="script")
            chosen[s["field"]].setdefault("source", None)
    add_default = 0
    for f in D.ORDER:
        if f not in chosen:
            chosen[f] = {"field": f, "value": D.DEF[f], "source": None, "locator": "",
                         "quote": "", "status": "inferred", "by": "default"}
            add_default += 1
    if add_default:
        degr.append({"stage": "spec", "reason": "%d of %d fields had no source; "
                     "documented defaults applied" % (add_default, len(D.ORDER))})
    spec = [chosen[f] for f in D.ORDER]
    smap = {s["field"]: s["value"] for s in spec}
    return spec, smap, {"conflicts": conflicts, "rejected_agent_items": rej, 
                        "agent_items": len(items if isinstance(items, list) else [])}

SEC = re.compile(r"(?i)^(abstract|摘要|introduction|引言|绪论|background|related work|" \
                 r"methods?|materials and methods|methodology|方法|实验|results?|结果|" \
                 r"discussion|讨论|conclusions?|结论|references|bibliography|参考文献|" \
                 r"acknowledg\w*|致谢|appendix|附录|keywords?|关键词|supplementary)\b")

def reflow(man_blocks, smap):
    """Deterministic structural pass; text is copied verbatim, never rewritten."""
    out, in_ref = [], False
    cap_prev = None
    for b in man_blocks:
        k, t = b.get("kind"), (b.get("text") or "")
        if not t.strip() and k != "table":
            continue
        if k == "table":
            cap = None
            if cap_prev and re.match(r"(?i)^\s*(table|表)\s*\d+", cap_prev["text"]):
                cap = cap_prev["text"]
                out.remove(cap_prev)
                cap_prev = None
            out.append({"kind": "table", "text": "", "src": b.get("loc"),
                        "rows": b.get("rows") or [], "caption": cap,
                        "cap_pos": smap.get("caption.table.position", "above")})
            continue
        if k in ("figure", "equation"):
            out.append({"kind": k, "text": t, "src": b.get("loc"),
                        "image": b.get("image"),
                        "caption": t if k == "figure" else None})
            cap_prev = None
            continue
        if k == "heading":
            out.append({"kind": "heading", "text": t, "src": b.get("loc"),
                        "level": max(1, min(3, int(b.get("level") or 1)))})
            cap_prev = None
            continue
        num = re.match(r"^\s*(\d+(?:\.\d+){0,2})[.)]?\s+\S", t)
        if num and len(t) < 180:
            out.append({"kind": "heading", "text": t, "src": b.get("loc"),
                        "level": min(3, num.group(1).count(".") + 1)})
            cap_prev = None
            continue
        if SEC.match(t.strip()) and len(t) < 90:
            name = t.strip().rstrip(":：")
            in_ref = bool(re.match(r"(?i)^(references|bibliography|参考文献)$", name))
            out.append({"kind": "heading", "text": t, "src": b.get("loc"),
                        "level": 2 if in_ref else 1})
            cap_prev = None
            continue
        if re.match(r"(?i)^\s*(figure|fig\.?|table|图|表)\s*\d+", t):
            blk = {"kind": "caption", "text": t, "src": b.get("loc")}
            out.append(blk)
            cap_prev = blk
            continue
        if re.match(r"^\s*\[\d+\]", t) or (in_ref and len(t) > 25):
            out.append({"kind": "reference", "text": t, "src": b.get("loc")})
            cap_prev = None
            continue
        if not out:
            out.append({"kind": "title", "text": t, "src": b.get("loc")})
            cap_prev = None
            continue
        out.append({"kind": "para", "text": t, "src": b.get("loc")})
        cap_prev = None
    if out and out[0]["kind"] == "title" and len(out) > 1 and \
            len(out[0]["text"]) < 8:
        out[0]["kind"] = "para"
    return out

def ctx_contract(case, res, extra):
    ctx = {"status": res.get("status"), "case_id": res.get("case_id"),
           "coverage": res.get("coverage"), "sources": res.get("sources"),
           "changes": res.get("changes"), "uncertainty": res.get("uncertainty"),
           "pending_human": res.get("pending_human"), "errors": res.get("errors"),
           "degradations": res.get("degradations"),
           "summary": res.get("summary"), "title": res.get("title")}
    ctx.update(extra)
    return ctx

RULES = (("pdf", "preview"), ("preview", "preview"), ("export", "preview"),
         ("render", "preview"), ("markdown", "md"), ("docx", "docx"),
         ("document", "docx"), ("editable", "docx"), ("deliverable", "docx"),
         ("manuscript", "docx"), ("primary", "docx"), ("artifact", "docx"),
         ("产物", "docx"), ("file", "docx"), ("spec", "format_spec"),
         ("规格", "format_spec"), ("fidelity", "fidelity"), ("保真", "fidelity"),
         ("coverage", "coverage"), ("覆盖", "coverage"), ("source", "sources"),
         ("来源", "sources"), ("change", "changes"), ("diff", "changes"),
         ("修改", "changes"), ("uncertain", "uncertainty"), ("pending", "pending_human"),
         ("human", "pending_human"), ("人工", "pending_human"), ("error", "errors"),
         ("degrad", "degradations"), ("status", "status"), ("case_id", "case_id"),
         ("summary", "summary"), ("摘要", "summary"), ("title", "title"))

def val(k, ctx):
    l = str(k).lower()
    if "case" in l and "id" in l:
        return ctx.get("case_id")
    for frag, key in RULES:
        if frag in l:
            v = ctx.get(key)
            return v if v not in ([], {}, "") else None
    return None

def fill(contract, ctx, out=None):
    out = {} if out is None else out
    if isinstance(contract, dict):
        for k, v in contract.items():
            got = val(k, ctx)
            if isinstance(v, dict) and not isinstance(got, dict):
                out[k] = fill(v, ctx, {})
            else:
                out[k] = got
    elif isinstance(contract, list):
        for k in contract:
            out[str(k)] = val(k, ctx)
    return out

def find_man(idx):
    for m in idx["materials"]:
        if m["id"] == idx.get("manuscript"):
            return m
    return None

def write_partial(out, case, stage):
    res = {"case_id": (case or {}).get("case_id") or (case or {}).get("id") or "unknown",
           "status": "partial", "stage": stage, "artifacts": {},
           "uncertainty": [{"item": "run", "why": "stage %s in progress" % stage,
                            "impact": "values may still change"}],
           "pending_human": [], "errors": [], "degradations": [], "changes": [],
           "sources": [],
           "runtime": {"skill": "academic-format-template-adapter", "version": VER,
                       "generated_at": now(), "python": sys.version.split()[0]}}
    res.update(fill((case or {}).get("output_contract"), ctx_contract(case, res, {})))
    res["status"] = "partial"
    res["case_id"] = (case or {}).get("case_id") or (case or {}).get("id") or "unknown"
    jd(Path(out) / "result.json", res)
    return res

def cmd_init(a):
    indir, work, out = paths(a)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    case, cpath = load_case(indir) if indir.exists() else ({}, None)
    write_partial(out, case, "init")
    idx = build_index(indir) if indir.exists() else build_index(Path("/nonexistent"))
    idx.update({"case_id": (case or {}).get("case_id") or (case or {}).get("id") or "unknown",
                "case_path": str(cpath) if cpath else None,
                "task_instruction": br(get(case, "task_instruction", "instruction", "task",
                                           "prompt") or (case or {}).get("_task_md") or "", 3000),
                "workorder": get(case, "workorder", "工单", "edit"),
                "output_contract": (case or {}).get("output_contract"),
                "dirs": {"input": str(indir), "work": str(work), "output": str(out)}})
    seeds, conflicts = resolve_seeds(idx)
    idx["seeds"], idx["conflicts"] = seeds, conflicts
    jd(work / "index.json", idx)
    man = find_man(idx) or {}
    oc = idx.get("output_contract")
    print("== case ==", idx["case_id"], "|", cpath or "case file NOT FOUND")
    print("task:", br(idx.get("task_instruction") or "(none)", 500))
    if idx.get("workorder"):
        print("workorder:", br(idx["workorder"], 600))
    print("output_contract (%s keys): %s" % (
        len(oc) if isinstance(oc, (dict, list)) else 0,
        list(oc) if isinstance(oc, dict) else oc))
    print("\n== materials ==")
    for m in idx["materials"]:
        print("%-4s %-32s %-5s blk=%-4d chars=%-6d spec=%-3d %-14s %s" % (
            m["id"], m["name"][:32], m["type"], m["n_blocks"], m["chars"],
            m["n_items"], m["role"], m["note"] or ""))
    if not idx["materials"]:
        print("(no readable material under %s)" % indir)
    print("\n== format requirements checklist (candidate values, verify with quote) ==")
    cur = dict((s["field"], s) for s in seeds)
    for f in D.ORDER:
        s = cur.get(f)
        if s:
            print("%-24s %-18s %-8s %-16s %s" % (f, str(s["value"])[:18], s["source"] or "-",
                                                 s["locator"][-18:], (s["quote"] or "")[:70]))
        else:
            print("%-24s %-18s %-8s %-16s %s" % (f, D.DEF[f] + " (default)", "-", "-",
                                                 "NOT STATED in the input"))
    for c in conflicts[:8]:
        print("CONFLICT %-22s kept=%r (%s) vs %r (%s)" % (
            c["field"], c["kept"]["value"], c["kept"]["locator"],
            c["other"]["value"], c["other"]["locator"]))
    print("\n== manuscript ==", man.get("id"), man.get("name"), "(%s blocks, %s chars)" % (
        man.get("n_blocks"), man.get("chars")))
    for b in (man.get("blocks") or [])[:36]:
        print("  %-7s %-8s %s" % (b.get("loc"), b.get("kind"), (b.get("text") or "")[:76]))
    draft = {"case_id": idx["case_id"], "_note": "SAMPLE skeleton - confirm every value, keep "
             "quote verbatim, delete items you cannot source", "spec": [
                 {"field": f, "value": (cur.get(f) or {}).get("value", D.DEF[f]),
                  "source": (cur.get(f) or {}).get("source"),
                  "locator": (cur.get(f) or {}).get("locator", ""),
                  "quote": (cur.get(f) or {}).get("quote", "")} for f in D.ORDER]}
    jd(work / "spec_table.draft.json", draft)
    print("\n== next ==")
    print("1) verify the checklist: python3 scripts/main.py show --input %s --work %s "
          "--material %s" % (indir, work, man.get("id") or "m01"))
    print("2) copy work/spec_table.draft.json -> work/spec_table.json and correct every row")
    print("3) python3 scripts/main.py check --input %s --work %s --out %s" % (indir, work, out))
    print("4) python3 scripts/main.py build --input %s --work %s --out %s" % (indir, work, out))
    return 0

def cmd_show(a):
    work = paths(a)[1]
    idx = jl(work / "index.json") or {}
    mats = idx.get("materials") or []
    sel = [m for m in mats if m["id"] == a.material] or mats
    if not sel:
        print("nothing indexed - run init first")
        return 0
    lo, hi = a.from_ or 1, a.to or 10 ** 9
    for m in sel[:4]:
        print("### %s %s (%s, %s blocks) %s" % (m["id"], m["name"], m["type"],
                                                m["n_blocks"], m["note"] or ""))
        for i, b in enumerate(m["blocks"], 1):
            t = b.get("text") or " | ".join(" | ".join(r) for r in b.get("rows") or [])
            if lo <= i <= hi and (not a.grep or re.search(a.grep, t, re.I)):
                print("%-8s %s" % (b.get("loc"), t[:400]))
        if a.items:
            print("-- mined spec candidates --")
            for it in m.get("items") or []:
                print("%-24s %-16s %-18s %s" % (it["field"], it["value"], it["locator"],
                                                (it["quote"] or "")[:70]))
    return 0

def load_plan(work):
    """-> (plan, name). Only spec_table.json counts as agent-confirmed; the script
    skeleton (spec_table.draft.json) is accepted but must not earn an ok status."""
    for n in ("spec_table.json", "spec_table.draft.json", "workplan.json", "spec.json"):
        p = Path(work) / n
        if p.exists():
            o = jl(p)
            if isinstance(o, dict):
                return o, n
            return None, "spec table is not valid JSON: %s" % p
    return None, "no spec table in %s" % work

def prep(a, need_index=True):
    indir, work, out = paths(a)
    for d in (work, out):
        d.mkdir(parents=True, exist_ok=True)
    case, _ = load_case(indir) if indir.exists() else ({}, None)
    idx = jl(work / "index.json")
    if not isinstance(idx, dict) or (need_index and not idx.get("materials")):
        idx = build_index(indir) if indir.exists() else build_index(Path("/nonexistent"))
        idx.update({"case_id": (case or {}).get("case_id") or (case or {}).get("id")
                    or "unknown", "output_contract": (case or {}).get("output_contract"),
                    "task_instruction": br(get(case, "task_instruction", "instruction",
                                               "task", "prompt") or "", 3000)})
        seeds, cf = resolve_seeds(idx)
        idx["seeds"], idx["conflicts"] = seeds, cf
        jd(work / "index.json", idx)
    if (case or {}).get("output_contract") and not idx.get("output_contract"):
        idx["output_contract"] = case["output_contract"]
    return case, idx, work, out, indir

def plan_and_blocks(idx, work, degr, pend):
    cache = {}
    plan, pname = load_plan(work)
    if plan is None:
        degr.append({"stage": "spec", "reason": pname + "; deterministic fallback used"})
    spec, smap, meta = reconcile(idx, plan, cache, degr, pend)
    man = find_man(idx) or {}
    blocks = reflow(man.get("blocks") or [], smap)
    if not blocks:
        blocks = [{"kind": "title", "text": TITLE, "generated": True},
                  {"kind": "para", "generated": True, "text":
                   "No readable manuscript text was found under %s. This document exists so "
                   "that the export path stays inspectable; the format specification below "
                   "was still extracted from the input." % idx.get("dirs", {}).get("input")}]
        degr.append({"stage": "manuscript", "reason": "no source text; notice document "
                     "written instead of failing"})
    n_exp = sum(1 for s in spec if s["status"] == "explicit")
    meta.update({"plan": pname, "explicit": n_exp, "total": len(spec),
                 "inferred": len(spec) - n_exp,
                 "confirmed": pname == "spec_table.json" and
                 sum(1 for s in spec if s.get("by") == "agent") >= 8})
    return plan, spec, smap, blocks, meta, man

def tx_units(blocks):
    return D.units(blocks)

def compliance(smap, pr, fid, blocks, man_blocks):
    C = []

    def add(cid, name, exp, act, ok, note=""):
        C.append({"id": cid, "check": name, "expected": exp, "actual": act,
                  "status": "pass" if ok else "fail", "note": note})

    add("C1", "paper size", smap["page.size"], pr["page_size"],
        str(smap["page.size"]) == str(pr["page_size"]))
    ok = True
    for k in ("top", "bottom", "left", "right"):
        e, g = D.cmv(smap["page.margin." + k]), pr["margins_cm"].get(k)
        ok = ok and g is not None and abs((e or 0) - g) < 0.06
    add("C2", "page margins (cm)", dict((k, smap["page.margin." + k]) for k in
                                        ("top", "bottom", "left", "right")),
        pr["margins_cm"], ok)
    add("C3", "columns", smap["page.columns"], pr["columns"],
        str(int(D.nu(smap["page.columns"], 1))) == str(pr["columns"]))
    add("C4", "body font", smap["body.font"], pr["normal"].get("font") or "-",
        (pr["normal"].get("font") or "").lower() == str(smap["body.font"]).lower(),
        "font written on every run: %d/%d" % (pr["runs_with_font"], pr["runs"]))
    add("C5", "body size (pt)", smap["body.size"], pr["normal"].get("sz_pt"),
        D.nu(smap["body.size"], 12) == pr["normal"].get("sz_pt"))
    exp_ls = smap["body.line_spacing"]
    act_ls = pr["body_line_multiple"] if "pt" not in str(exp_ls) else (
        (pr["normal"].get("line") or 0) / 20.0)
    add("C6", "line spacing", exp_ls, act_ls,
        abs((D.nu(exp_ls, 1.5)) - (act_ls or 0)) < 0.02)
    ok = all(pr["headings"][i].get("sz_pt") == D.nu(smap["heading.%d.size" % i], 12)
             and pr["headings"][i].get("outline") == i - 1 for i in (1, 2, 3))
    add("C7", "heading levels 1-3 (size + outline level)",
        [smap["heading.%d.size" % i] for i in (1, 2, 3)],
        [[pr["headings"][i].get("sz_pt"), pr["headings"][i].get("outline")] for i in (1, 2, 3)],
        ok, "headings in output: %d" % sum(1 for b in blocks if b.get("kind") == "heading"))
    cn = sum(1 for b in blocks if b.get("kind") == "caption")
    add("C8", "captions (position per spec + size)", {
        "figure": smap["caption.figure.position"], "table": smap["caption.table.position"],
        "size_pt": smap["caption.size"]},
        {"captions_written": cn, "style_size_pt": pr["caption"].get("sz_pt")},
        pr["caption"].get("sz_pt") == D.nu(smap["caption.size"], 10))
    add("C9", "footer PAGE field", smap["footer.page_number"],
        {"page_field": pr["footer_page_field"], "align": pr["footer_align"]},
        pr["footer_page_field"] and pr["footer_align"] == str(smap["footer.page_number"]))
    add("C10", "three-line tables", smap["table.style"],
        {"tables": pr["table_count"], "three_line": pr["tables_three_line"]},
        pr["table_count"] == 0 or (smap["table.style"] != "three-line" or
                                   pr["tables_three_line"]))
    add("C11", "content fidelity (verbatim units)", "1.0", fid["verbatim_ratio"],
        fid["verbatim_ratio"] >= 1.0, "%d source units" % fid["source_units"])
    add("C12", "numbers and citation markers preserved", "no loss",
        {"numbers": fid["numbers_output"], "citations": fid["citations_output"]},
        fid["numbers_preserved"] and fid["citations_preserved"])
    return C

def cmd_check(a):
    case, idx, work, out, indir = prep(a)
    degr, pend, errs = [], [], []
    plan, spec, smap, blocks, meta, man = plan_and_blocks(idx, work, degr, pend)
    fid = D.fid(man.get("blocks") or [], blocks)
    cache = {}
    verified = sum(1 for s in spec if s["quote"] and
                   qhit(idx["materials"], s["quote"], s.get("source"), cache))
    nq = sum(1 for s in spec if s["quote"])
    ck = [("index_and_materials", bool(idx.get("materials")),
           "%d materials" % len(idx.get("materials") or [])),
          ("manuscript_found", bool(man), "%s %s" % (man.get("id"), man.get("name"))),
          ("spec_table_present", plan is not None, meta.get("plan") or "none"),
          ("spec_fields_complete", len(spec) == len(D.ORDER), "%d/%d" % (
              len(spec), len(D.ORDER))),
          ("spec_explicit_enough", meta["explicit"] >= 8, "%d explicit" % meta["explicit"]),
          ("quotes_verbatim", nq and verified == nq, "%d/%d verified" % (verified, nq)),
          ("blocks_rebuilt", len(blocks) >= 3, "%d blocks" % len(blocks)),
          ("headings_found", sum(1 for b in blocks if b.get("kind") == "heading") >= 1,
           "%d headings" % sum(1 for b in blocks if b.get("kind") == "heading")),
          ("verbatim_ratio", fid["verbatim_ratio"] >= 1.0, str(fid["verbatim_ratio"])),
          ("numbers_preserved", fid["numbers_preserved"], str(fid["numbers_output"])),
          ("citations_preserved", fid["citations_preserved"], str(fid["citations_output"]))]
    ok = all(c[1] for c in ck)
    rep = {"verdict": "ok" if ok else "partial",
           "checks": [{"name": c[0], "ok": c[1], "detail": c[2]} for c in ck],
           "spec": {"total": len(spec), "explicit": meta["explicit"],
                    "inferred": meta["inferred"], "quotes_verified": verified},
           "fidelity": fid, "conflicts": meta["conflicts"],
           "degradations": degr, "generated_at": now()}
    jd(work / "check_report.json", rep)
    print("== check ==")
    for c in ck:
        print("%-6s %-22s %s" % ("PASS" if c[1] else "FAIL", c[0], c[2]))
    print("verdict %s | explicit %d/%d | verbatim %s | blocks %d" % (
        rep["verdict"], meta["explicit"], len(spec), fid["verbatim_ratio"], len(blocks)))
    for d in degr[:6]:
        print("DEGRADED:", br(d, 160))
    if not ok:
        print("fix the FAIL rows before build (build still produces a valid partial result)")
    return 0

def cmd_build(a):
    t0 = time.time()
    case, idx, work, out, indir = prep(a)
    write_partial(out, case, "build")
    degr, pend, errs, unc, chg = [], [], [], [], []
    plan, spec, smap, blocks, meta, man = plan_and_blocks(idx, work, degr, pend)
    title = next((b["text"] for b in blocks if b.get("kind") == "title"), "") or \
        str(idx.get("case_id") or "")
    md = out / "deliverable.md"
    md.write_text(D.md_render(blocks, ""), encoding="utf-8")
    dpath = out / "deliverable.docx"
    info = {}
    try:
        info = D.build_docx(dpath, blocks, smap, title)
    except Exception as e:
        errs.append({"stage": "docx", "error": "%s: %s" % (type(e).__name__, e)})
        try:
            D.build_docx(dpath, [{"kind": "title", "text": TITLE},
                                 {"kind": "para", "text": "docx writer recovered from an "
                                  "internal error; see result.json errors"}], D.DEF, TITLE)
            info = {"recovered": True}
        except Exception as e2:
            errs.append({"stage": "docx2", "error": str(e2)})
    src_units = man.get("blocks") or []
    fid = D.fid(src_units, blocks)
    rt = {}
    try:
        back = D.dxb(dpath)[0]
        rt = {"blocks": len(back), "chars": sum(len(b.get("text") or "") for b in back),
              "verbatim_ratio": D.fid(blocks, back)["verbatim_ratio"]}
        if rt["verbatim_ratio"] < 1.0:
            degr.append({"stage": "roundtrip", "detail": rt,
                         "reason": "re-read text differs from what was written"})
    except Exception as e:
        errs.append({"stage": "roundtrip", "error": "%s: %s" % (type(e).__name__, e)})
    pv = {"path": None, "pages": None, "fonts": [], "engine": None, "note": "skipped"}
    if dpath.exists():
        try:
            pv = D.preview(dpath, out, work)
        except Exception as e:
            pv["note"] = "preview crashed: %s" % e
    if not pv.get("path"):
        txtpv = out / "preview.txt"
        try:
            txtpv.write_text("TEXT-ONLY PREVIEW (no PDF renderer available)\n"
                             "reason: %s\n\n" % pv.get("note") + md.read_text(
                                 encoding="utf-8"), encoding="utf-8")
            pv["text_fallback"] = "preview.txt"
        except Exception:
            pass
        degr.append({"stage": "preview", "reason": pv.get("note") or "no PDF",
                     "fallback": pv.get("text_fallback")})
    try:
        pr = D.probe(dpath)
    except Exception as e:
        errs.append({"stage": "probe", "error": str(e)})
        pr = {"page_size": None, "margins_cm": {}, "columns": None,
              "normal": {}, "headings": {i: {} for i in (1, 2, 3)}, "caption": {},
              "runs": 0, "runs_with_font": 0, "table_count": 0,
              "tables_three_line": False, "footer_page_field": False,
              "footer_align": None, "toc_field": False, "styles_used": [], "bytes": 0}
    qcache = {}
    checks = compliance(smap, pr, fid, blocks, src_units)
    jd(out / "format_spec.json", {
        "case_id": idx.get("case_id"), "generated_at": now(), "counts": {
            "total": len(spec), "explicit": meta["explicit"], "inferred": meta["inferred"]},
        "conflicts": meta["conflicts"],
        "fields": [{"field": s["field"], "value": s["value"], "status": s["status"],
                    "source": s.get("source"), "locator": s.get("locator"),
                    "quote": s.get("quote"), "decided_by": s.get("by")} for s in spec]})
    bmap, si, ti = [], 0, {}
    for b in blocks:
        key = D.sq(b.get("text") or "")
        bmap.append({"index": len(bmap) + 1, "role": b.get("kind"),
                     "source_locator": b.get("src"),
                     "verbatim": bool(key and key in set(
                         D.sq(t) for _, t in D.units(src_units))) if key else
                     b.get("kind") == "table"})
    jd(out / "fidelity_report.json", {
        "case_id": idx.get("case_id"), "generated_at": now(),
        "method": "Block-level comparison: every source paragraph, caption and table row must "
                  "reappear verbatim (whitespace-insensitive) in the output; numbers and "
                  "citation markers are counted before and after.",
        "summary": fid, "docx_roundtrip": rt,
        "block_map": bmap[:400],
        "not_preserved": fid["missing_units"],
        "changes_outside_text": [
            "styles bound (Title/Heading1-3/Normal/Caption/Bibliography/TableText)",
            "page geometry, columns, line spacing and margins written to sectPr/styles",
            "table borders reduced to three-line; footer PAGE field added"],
        "limits": ["Text, numbers and citation markers are copied verbatim; nothing is "
                   "rewritten, merged or renumbered.",
                   "Figures are referenced by their source path text only (no raster is "
                   "generated), so image content is not carried into the docx."]})
    if not fid["numbers_preserved"]:
        unc.append({"item": "numbers", "why": "count differs", "impact": str(
            fid["numbers_lost"])[:300]})
    if not fid["citations_preserved"]:
        unc.append({"item": "citation markers", "why": "count differs", "impact": str(
            fid["citations_lost"])[:300]})
    for s in spec:
        if s["status"] != "explicit":
            unc.append({"item": s["field"], "why": "no explicit statement in the input",
                        "impact": "documented default %r applied" % s["value"]})
    for c in meta["conflicts"]:
        unc.append({"item": c["field"], "why": "conflicting statements in the input",
                    "impact": "kept %r, other value recorded" % c["kept"]["value"]})
    if plan is None or not meta["confirmed"]:
        pend.append({"item": "spec_table.json", "action": "write work/spec_table.json with the "
                     "confirmed spec rows (draft is only a skeleton) and rerun check+build",
                     "detail": meta.get("plan")})
    if not pv.get("path"):
        pend.append({"item": "PDF preview", "action": "open deliverable.docx and export PDF "
                     "on a machine with LibreOffice", "detail": pv.get("note")})
    status = "ok"
    status = "ok"
    if not man:
        status = "insufficient_evidence"
    elif (errs or not dpath.exists() or fid["verbatim_ratio"] < 1.0
          or not fid["numbers_preserved"] or not fid["citations_preserved"]
          or plan is None or not meta["confirmed"] or
          meta["explicit"] < 0.5 * len(spec)):
        status = "partial"
    if (case or {}) and not (case or {}).get("output_contract") and idx.get("materials"):
        unc.append({"item": "output_contract", "why": "no output_contract in case.json",
                    "impact": "skill-native fields only"})
    errs = BAD_CASE[:] + errs
    chg = [{"type": "layout", "summary": "page %s, %s column(s), margins %s, body %s %s pt, "
            "line spacing %s" % (smap["page.size"], smap["page.columns"],
                                 pr.get("margins_cm"), smap["body.font"],
                                 smap["body.size"], smap["body.line_spacing"])},
           {"type": "style", "summary": "every paragraph bound to a named Word style; "
            "outline levels 0-2 on headings; captions use the Caption style"},
           {"type": "text", "summary": "no wording, number or citation changed; verbatim "
            "ratio %s over %d units" % (fid["verbatim_ratio"], fid["source_units"])}]
    arts = {}
    for p in sorted(Path(out).iterdir()):
        if p.is_file() and p.name != "result.json":
            arts[p.name] = p.stat().st_size
    res = {"case_id": idx.get("case_id"), "status": status, "title": title,
           "artifacts": arts,
           "deliverable": "deliverable.docx" if dpath.exists() else None,
           "editable_source": "deliverable.docx" if dpath.exists() else None,
           "export_artifact": pv.get("path"), "preview_pages": pv.get("pages"),
           "preview_fonts": pv.get("fonts"), "preview_engine": pv.get("engine"),
           "preview_text_fallback": pv.get("text_fallback"),
           "markdown": "deliverable.md", "format_spec": "format_spec.json",
           "fidelity_report": "fidelity_report.json",
           "coverage": {"spec_total": len(spec), "spec_explicit": meta["explicit"],
                        "spec_inferred": meta["inferred"],
                        "spec_quotes_verified": sum(
                            1 for x in spec if x["quote"] and qhit(idx["materials"], x["quote"],
                                                                   x.get("source"), qcache)),
                        "checks_pass": sum(1 for c in checks if c["status"] == "pass"),
                        "checks_total": len(checks),
                        "blocks": len(blocks),
                        "headings": sum(1 for b in blocks if b.get("kind") == "heading"),
                        "tables": pr.get("table_count"),
                        "verbatim_ratio": fid["verbatim_ratio"],
                        "numbers_preserved": fid["numbers_preserved"],
                        "citations_preserved": fid["citations_preserved"]},
           "fidelity": {k: fid[k] for k in ("source_units", "output_units", "matched_units",
                                            "verbatim_ratio", "missing_count", "numbers_source",
                                            "numbers_output", "citations_source",
                                            "citations_output")},
           "compliance_checks": checks,
           "sources": [{"id": m["id"], "name": m["name"], "path": m["path"], "type": m["type"],
                        "role": m["role"], "blocks": m["n_blocks"], "chars": m["chars"],
                        "spec_items_mined": m["n_items"], "read_note": m["note"]}
                       for m in idx["materials"]], 
           "uncertainty": unc[:40], "pending_human": pend[:20], "errors": errs,
           "degradations": degr[:30], "changes": chg,
           "runtime": {"skill": "academic-format-template-adapter", "version": VER,
                       "generated_at": now(), "duration_s": round(time.time() - t0, 2),
                       "python": sys.version.split()[0],
                       "tools": [t for t in ("soffice", "libreoffice", "pdftotext",
                                             "pdffonts") if __import__("shutil").which(t)],
                       "spec_table": meta.get("plan"), "status_basis": status}}
    res["summary"] = br("status %s; %d/%d spec fields explicit; %d/%d compliance checks "
                        "pass; verbatim %s; %d blocks; preview %s" % (
                            status, meta["explicit"], len(spec),
                            sum(1 for c in checks if c["status"] == "pass"), len(checks),
                            fid["verbatim_ratio"], len(blocks), pv.get("path") or "none"), 400)
    ctx = ctx_contract(case, res, {"docx": res["deliverable"], "md": "deliverable.md",
                                   "preview": res["export_artifact"],
                                   "format_spec": "format_spec.json",
                                   "fidelity": "fidelity_report.json"})
    filled = fill((case or {}).get("output_contract"), ctx)
    for k, v in filled.items():
        if k not in res:
            res[k] = v
        elif res[k] is None and v is not None:
            res[k] = v
    oc = (case or {}).get("output_contract")
    if isinstance(oc, dict):
        missing = [k for k in oc if k not in res]
        if missing:
            res["degradations"].append({"stage": "contract", "fields": missing,
                                        "reason": "keys added with null: no matching artifact"})
            for k in missing:
                res[k] = None
        flat = [k for k in oc if k in res and res[k] is None]
        if flat:
            res["uncertainty"].append({"item": "output_contract fields", "why":
                                       "no matching value", "impact": str(flat)[:300]})
    res["status"] = status
    res["case_id"] = idx.get("case_id")
    jd(out / "result.json", res)
    print("== build ==\nstatus %s | artifacts %s" % (status, br(sorted(arts), 300)))
    print("spec %d/%d explicit | compliance %d/%d | verbatim %s | blocks %d | errors %d | "
          "degraded %d" % (meta["explicit"], len(spec),
                           sum(1 for c in checks if c["status"] == "pass"), len(checks),
                           fid["verbatim_ratio"], len(blocks), len(errs), len(degr)))
    if pend:
        print("pending_human:", br(pend, 240))
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py", description="Apply a format template to a manuscript: init -> "
        "(Agent writes work/spec_table.json) -> check -> build. Always exits 0; every run "
        "leaves a valid result.json.",
        epilog="EXAMPLE (not an official case result): python3 scripts/main.py init "
        "--input ./sample/input --work ./sample/work --out ./sample/output")
    ap.add_argument("--input", help="input dir (default /input; env SKILL_INPUT_DIR)")
    ap.add_argument("--work", help="work dir (default /app/work; env SKILL_WORK_DIR)")
    ap.add_argument("--out", help="output dir (default /app/output; env SKILL_OUT_DIR)")
    ap.add_argument("--version", action="version", version="academic-format-template-adapter "
                    + VER)
    sub = ap.add_subparsers(dest="cmd")
    for name, fn, h in (("init", cmd_init, "index inputs, print the requirement checklist, "
                         "write a partial result.json"),
                        ("check", cmd_check, "validate the spec table and the reflow"),
                        ("build", cmd_build, "write deliverable.docx/md + spec/fidelity + "
                         "result.json")):
        sp = sub.add_parser(name, help=h)
        for f in ("input", "work", "out"):
            sp.add_argument("--" + f)
        sp.set_defaults(func=fn)
    sh = sub.add_parser("show", help="print material text and mined spec candidates")
    sh.add_argument("--material")
    sh.add_argument("--from", dest="from_", type=int)
    sh.add_argument("--to", type=int)
    sh.add_argument("--grep")
    sh.add_argument("--items", action="store_true")
    sh.add_argument("--work")
    sh.add_argument("--input")
    sh.set_defaults(func=cmd_show)
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    try:
        args.func(args)
    except Exception as exc:
        try:
            indir, work, out = paths(args)
            work.mkdir(parents=True, exist_ok=True)
            out.mkdir(parents=True, exist_ok=True)
            case, _ = load_case(indir) if indir.exists() else ({}, None)
            res = jl(Path(out) / "result.json") or write_partial(out, case, "recover")
            res["status"] = "partial"
            res.setdefault("errors", []).append({
                "stage": str(getattr(args, "cmd", "cli")),
                "error": "%s: %s" % (type(exc).__name__, exc)})
            jd(Path(out) / "result.json", res)
            print("ERROR %s: %s (partial result.json kept)" % (type(exc).__name__, exc),
                  file=sys.stderr)
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
