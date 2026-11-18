#!/usr/bin/env python3
"""writing-07 reviewer-response-revision: controlled revision drill.

baseline + reviewer comments -> ledger -> edit plan -> verified revisions ->
manuscript, response letter, ledger, locator table, evidence, result.json.
Standard library only; no network; no CWD dependency; exit code always 0.
"""
import argparse, json, re, sys, time, traceback
from pathlib import Path

VERSION = "1.0.0"
T0 = time.time()
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "references"
TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".tex"}
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _res(name, default):
    try:
        return json.loads((RES / name).read_text(encoding="utf-8"))
    except Exception:
        return default


TAX = _res("taxonomy.json", {})
BANNED = TAX.get("banned_claims") or []
TONE = TAX.get("tone_map") or {"accept": "accept", "partial": "clarify",
                               "reject": "polite_rebuttal", "clarify": "clarify", "invalid": "appeal"}
try:
    sys.path.insert(0, str(HERE))
    import verify as V
except Exception:
    V = None
DEC = tuple(TONE)


def now(): return round(time.time() - T0, 3)
def tone_for(d): return TONE.get(d, "accept")


def read_text(p):
    try: return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception: return ""


def norm(s): return re.sub(r"\s+", " ", str(s or "")).strip()


def load_json(p):
    try: return json.loads(read_text(p)), None
    except Exception as e: return None, "%s: %s" % (type(e).__name__, e)


def write_text(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(str(s), encoding="utf-8")


def write_json(p, o): write_text(p, json.dumps(o, ensure_ascii=False, indent=2))


def lang_of(t):
    zh, en = len(re.findall(r"[\u4e00-\u9fff]", t)), len(re.findall(r"[A-Za-z]", t))
    return "zh" if zh >= 20 and zh * 3 >= en else "en"


def walk(root):
    out = []
    try:
        for p in sorted(Path(root).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts: out.append(p)
    except Exception: pass
    return out[:400]


def discover(inp):
    """Semantic discovery: no fixed key names, file-name + content scoring."""
    inp = Path(inp)
    info = {"case": {}, "files": [], "baseline": None, "comments": [], "errors": []}
    cands = [inp / "case.json"] if (inp / "case.json").is_file() else \
        [p for p in walk(inp) if p.suffix.lower() == ".json" and "case" in p.name.lower()][:3]
    for c in cands:
        d, e = load_json(c)
        if e:
            info["errors"].append({"where": str(c), "error": "invalid JSON (%s)" % e}); continue
        if isinstance(d, dict): info["case"] = d; break
    sc = []
    for p in walk(inp):
        if p.suffix.lower() not in TEXT_EXT:
            if p.name != "case.json": info["files"].append(str(p))
            continue
        t = read_text(p); info["files"].append(str(p))
        cn = 3.0 if re.search(r"comment|reviewer|referee|response|意见|审稿", p.name, re.I) else 0.0
        if re.search(r"manuscript|baseline|draft|paper|正文|稿件|论文", p.name, re.I): cn -= 2.0
        head = t[:4000]
        cn += 2.0 * len(re.findall(r"reviewer|referee|comment|审稿人|意见", head, re.I)) / max(1, len(head) / 500.0)
        bn = (3.0 if re.search(r"manuscript|baseline|draft|paper|article|正文|稿件|论文", p.name, re.I) else 0.0) \
            - (3.0 if re.search(r"comment|reviewer|意见|审稿", p.name, re.I) else 0.0) + min(3.0, len(t) / 4000.0)
        sc.append({"path": p, "text": t, "c": cn, "b": bn})
    cm = [x for x in sc if x["c"] > 1.0]
    rest = [x for x in sc if x["c"] <= 1.0] or ([max(sc, key=lambda x: len(x["text"]))] if sc else [])
    if rest: info["baseline"] = max(rest, key=lambda x: x["b"])
    info["comments"] = sorted(cm, key=lambda x: -x["c"])[:4]
    return info


def parse_blocks(text):
    blocks, buf = [], []
    for ln in str(text or "").splitlines():
        if ln.strip() == "":
            if buf: blocks.append("\n".join(buf)); buf = []
        else: buf.append(ln)
    if buf: blocks.append("\n".join(buf))
    out = []
    for i, b in enumerate(blocks, 1):
        m = re.match(r"^(#{1,6})\s", b)
        out.append({"label": "P%03d" % i, "text": b, "level": len(m.group(1)) if m else 0})
    return out


def parse_comments(text):
    units, cur = [], None
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if not s:
            if cur: cur["body"].append("")
            continue
        head, cand = ln.lstrip().startswith("#"), None
        if head and re.search(r"comment|reviewer|referee|point|item|remark|意见|审稿|问题", s, re.I) and re.search(r"\d", s):
            cand = re.sub(r"^#+\s*", "", s).strip(" *")
            if re.match(r"^(reviewer|审稿人)\s*\d+\s*$", cand, re.I): cur = None; continue
        elif not head and re.match(r"^(?:\*\*)?(?:comment|point|item|q|c|r|意见|问题)\s*[#]?\.?\s*\d{1,2}(?:\.\d{1,2})?\b", s, re.I):
            cand = s.strip(" *")
        elif not head and re.match(r"^(?:\*\*)?\d{1,2}[.)、)）]\s+\S", s) and len(s) > 12:
            cand = s.strip(" *")
        if cand is None and cur is None and head:
            continue
        if cand:
            units.append({"label": cand[:120], "body": []}); cur = units[-1]
            rest = re.sub(r"^.{0,40}?\d{1,2}(?:\.\d+)?\s*[:：.\-–)）]?\s*", "", cand)
            if rest and len(rest) > 12 and rest != cand: cur["body"].append(rest)
            continue
        if cur is None:
            units.append({"label": "Comment %d" % (len(units) + 1), "body": []}); cur = units[-1]
        cur["body"].append(s)
    out = []
    for i, u in enumerate(units, 1):
        body = "\n".join(u["body"]).strip()
        if body or u["label"]:
            out.append({"comment_id": "C%d" % i, "source_label": u["label"], "body": body})
    if not out and str(text).strip():
        out.append({"comment_id": "C1", "source_label": "Comment 1", "body": str(text).strip()})
    return out


def find_block(bs, anchor, oq):
    if anchor:
        for i, b in enumerate(bs):
            if b["label"] == anchor and (not oq or norm(oq) in norm(b["text"])): return i
    if oq:
        for i, b in enumerate(bs):
            if oq in b["text"]: return i
        for i, b in enumerate(bs):
            if norm(oq) in norm(b["text"]): return i
    if anchor:
        for i, b in enumerate(bs):
            if b["label"] == anchor: return i
    return None


def do_replace(text, oq, rq, count):
    if oq and oq in text: return text.replace(oq, rq, count), True
    m = re.compile(r"\s+".join(re.escape(t) for t in oq.split())).search(text) if oq else None
    if m: return text[:m.start()] + rq + text[m.end():], True
    return text, False


def apply_edits(bs, edits, issues):
    bs = [{"label": b["label"], "text": b["text"], "level": b["level"]} for b in bs]
    recs = []
    for i, e in enumerate(edits):
        e = e if isinstance(e, dict) else {}
        rec = {"id": str(e.get("id") or "E%02d" % (i + 1)), "applied": False, "why": "",
               "original_quote": str(e.get("original_quote") or "").strip(),
               "revised_quote": str(e.get("revised_quote") or "").strip()}
        op, oq, rq = str(e.get("op") or "replace").lower(), rec["original_quote"], rec["revised_quote"]
        anc = e.get("anchor") or e.get("locator")
        if not rq: rec["why"] = "empty revised_quote"
        elif op.startswith("replace"):
            if not oq: rec["why"] = "empty original_quote"
            else:
                idx = find_block(bs, anc, oq)
                if idx is None: rec["why"] = "original_quote not found in baseline"
                else:
                    bs[idx]["text"], ok = do_replace(bs[idx]["text"], oq, rq, -1 if op == "replace_all" else 1)
                    rec["applied"], rec["why"] = ok, "" if ok else "replace failed"
        elif op in ("append_after", "insert_after"):
            idx = find_block(bs, anc, oq) if (anc or oq) else len(bs) - 1
            if idx is None: rec["why"] = "anchor not found"
            else: bs.insert(idx + 1, {"label": "", "text": rq, "level": 0}); rec["applied"] = True
        elif op in ("append_end", "insert_section"):
            bs.append({"label": "", "text": rq, "level": 0}); rec["applied"] = True
        else: rec["why"] = "unknown op: %s" % op
        if not rec["applied"]:
            issues.append({"kind": "edit_not_applied", "id": rec["id"], "detail": rec["why"]})
        recs.append(rec)
    return [b["text"] for b in bs], recs


def locate(q, bs):
    q = norm(q)
    if not q: return None
    for b in bs:
        if q in norm(b["text"]): return b["label"]
    return None


def preserved_facts(blocks, changes, limit=80):
    rev = [norm(c.get("revised_quote")) for c in changes if c.get("revised_quote")]
    out = []
    for b in blocks:
        if b.get("level") or any(r and r in norm(b.get("text")) for r in rev):
            continue
        for s in re.split(r"(?<=[.!?。！？])(?!\d)\s*", str(b.get("text", "")).strip()):
            s = s.strip()
            if s and (re.search(r"\d", s) or re.search(r"\[\d+\]", s)):
                out.append({"locator": b.get("label"), "quote": s[:300], "changed": False,
                            "kind": "numeric" if re.search(r"\d", s) else "citation"})
            if len(out) >= limit:
                return out
    return out


def sanitize(t, issues):
    t, hits = str(t or ""), []
    for pat in BANNED:
        hs = [m.group(0) for m in re.finditer(pat, t, re.I)]
        for h in hs: t = re.sub(re.escape(h), "", t, flags=re.I)
        hits += hs
    if hits: issues.append({"kind": "overclaim_removed", "detail": hits[:5]})
    return t, hits


def run(a):
    out, work = Path(a.output), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    E, D, I, P, U = [], [], [], [], []
    info = discover(a.input)
    E += info["errors"]
    case = info["case"] if isinstance(info["case"], dict) else {}
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    cid, dn = str(case.get("case_id") or "UNKNOWN-CASE"), a.deliverable_name
    ctx = {"case_id": cid, "deliverable": dn, "preserved_facts": [], "evidence_map": [],
           "change_log": [], "status": "partial", "uncertainty": U}
    pre = {"status": "partial", "stage": "partial"}
    pre.update(V.echo(con, ctx) if V else {"case_id": cid})
    pre.update({"pending_human": [{"item": "pipeline", "reason": "partial placeholder written first"}],
                "errors": E, "degradations": [], "runtime": {"version": VERSION, "elapsed_s": now()}})
    write_json(out / "result.json", pre)
    base, cm = info.get("baseline"), info.get("comments") or []
    if not base or not str(base.get("text") or "").strip():
        E.append({"where": "input", "error": "no manuscript baseline found"})
        P.append({"item": "manuscript baseline", "reason": "not found; nothing to revise"})
        msg = "# No usable baseline\n\nNo manuscript baseline was found; no revision produced.\n"
        if V:
            return V.emit(out, cid, dn, con, ctx, "input_error", E, D, I, P, U, [], [],
                          msg, "input_error", "not supplied", "not supplied", "en", [], [],
                          case, [])
        write_text(out / dn, msg)
        return 0
    bstr, bn = base["text"], Path(base["path"]).name
    cstr = "\n\n".join(c["text"] for c in cm)
    cn = ", ".join(Path(c["path"]).name for c in cm) or "not supplied"
    if not cm:
        D.append({"kind": "comments_missing", "detail": "no comment file found"})
        P.append({"item": "reviewer comments", "reason": "comment summary not found"})
    lang = lang_of(cstr or bstr)
    bs = parse_blocks(bstr)
    led = V.build_ledger(parse_comments(cstr), bs, lang) if V else []
    if V is None:
        I.append({"kind": "helper_missing", "detail": "verify.py unavailable"})
    pp = Path(a.plan) if a.plan else work / "edit_plan.json"
    if not pp.is_file() and (out / "edit_plan.json").is_file():
        pp = out / "edit_plan.json"
    plan = {}
    if pp.is_file():
        plan, perr = load_json(pp)
        if perr or not isinstance(plan, dict):
            E.append({"where": str(pp), "error": "bad plan (%s)" % perr})
            plan = {}
    elif a.stage in ("finalize", "plan"):
        E.append({"where": "edit_plan", "error": "no edit plan found; run with --stage plan first"})
    stage = a.stage if a.stage != "auto" else (
        "finalize" if (plan.get("edits") or plan.get("sub_overrides")) else "draft")
    subs = V.recount(led) if V else {}
    for o in plan.get("sub_overrides") or []:
        o = o if isinstance(o, dict) else {}
        s = subs.get(str(o.get("sub_id")))
        if not s:
            I.append({"kind": "unknown_sub_id", "detail": str(o.get("sub_id"))})
            continue
        for k in ("decision", "response_note", "evidence_status", "evidence_note", "type"):
            if o.get(k):
                s[k] = o[k]
        s["decision"] = s["decision"] if s["decision"] in DEC else "accept"
        s["tone"] = tone_for(s["decision"])
    changes, rb, rtext = [], bs, bstr
    if stage == "finalize":
        ed = [e for e in (plan.get("edits") or []) if isinstance(e, dict)]
        raw, recs = apply_edits(bs, ed, I)
        rtext = "\n\n".join(raw)
        rb = parse_blocks(rtext)
        for i, r in enumerate(recs):
            e = ed[i] if i < len(ed) else {}
            sid = str(e.get("sub_id") or "")
            loc = locate(r["revised_quote"], rb) if r["applied"] else None
            if r["applied"] and not loc:
                I.append({"kind": "revised_quote_not_found", "detail": r["id"]})
                D.append({"kind": "unverifiable_claim",
                          "detail": "edit %s: revised text absent from deliverable" % r["id"]})
            nok = set(NUM.findall(r["original_quote"])) <= set(NUM.findall(r["revised_quote"]))
            if not nok:
                I.append({"kind": "number_changed", "detail": r["id"]})
                P.append({"item": "numeric change %s" % r["id"],
                          "reason": "numbers differ from the baseline value; human confirmation required"})
            changes.append({
                "id": str(e.get("id") or r["id"]),
                "comment_id": str(e.get("comment_id") or sid.split(".")[0]), "sub_id": sid,
                "original_quote": r["original_quote"], "revised_quote": r["revised_quote"],
                "reason": str(e.get("reason") or ""), "locator": loc,
                "baseline_anchor": str(e.get("anchor") or ""), "hit": bool(loc),
                "numbers_preserved": nok, "decision": str(e.get("decision") or "accept"),
                "evidence_status": str(e.get("evidence_status") or "")})
            s = subs.get(sid)
            if not s:
                I.append({"kind": "edit_without_sub", "detail": sid})
                continue
            if loc:
                s["change_ids"].append(changes[-1]["id"])
            if e.get("decision") in DEC:
                s["decision"] = e["decision"]
            s["tone"] = str(e.get("tone") or tone_for(s["decision"]))
            for k in ("response_note", "evidence_status", "evidence_note"):
                if e.get(k):
                    s[k] = str(e[k])
            if not loc and s["decision"] == "accept":
                s["decision"], s["tone"] = "partial", tone_for("partial")
    elif stage == "draft":
        D.append({"kind": "draft_only", "detail": "no edit plan: manuscript delivered unrevised; "
                                                  "substantive edits not applied"})
    for s in subs.values():
        s["response_note"], hs = sanitize(s.get("response_note", ""), I)
        if hs:
            P.append({"item": "overclaim in %s" % s["sub_id"],
                      "reason": "removed unsupported claim: " + "; ".join(hs[:3])})
    if V:
        V.recount(led, True)
    for s in subs.values():
        if s["decision"] in ("accept", "partial") and not s["change_ids"]:
            P.append({"item": s["sub_id"],
                      "reason": "decision recorded but no verified change locator; confirm or revise"})
        elif s["needs_human"] and not any(p.get("item") == s["sub_id"] for p in P):
            P.append({"item": s["sub_id"],
                      "reason": s.get("evidence_note") or "needs material beyond baseline"})
    allsub = [s for c in led for s in c["sub_requirements"]]
    applied = len([c for c in changes if c["hit"]])
    st = "insufficient_evidence" if (not cm or not led) else (
        "partial" if (stage != "finalize" or applied < len(changes) or P) else "ok")
    if V is None:
        write_text(out / dn, rtext)
        res = {"case_id": cid, "status": st, "deliverable": dn, "preserved_facts": [],
               "evidence_map": [], "change_log": changes, "errors": E, "degradations": D,
               "pending_human": P, "comment_ledger": led}
        res.update(con if isinstance(con, dict) else {})
        write_json(out / "result.json", res)
        return 0
    pres = preserved_facts(rb, changes)
    ev = [{"claim": c["revised_quote"][:300], "locator": c["locator"] or c["baseline_anchor"],
           "source_locator": c["baseline_anchor"], "source_quote": c["original_quote"][:300],
           "basis": "baseline_edit", "comment_id": c["comment_id"]} for c in changes]
    ev += [{"claim": s["text"][:200], "locator": s["anchor"], "source_locator": s["anchor"],
            "source_quote": "", "basis": "baseline_unchanged", "comment_id": c["comment_id"]}
           for c in led for s in c["sub_requirements"] if not s["change_ids"] and s["anchor"]]
    return V.emit(out, cid, dn, con, ctx, st, E, D, I, P, U, led, changes, rtext,
                  stage, bn, cn, lang, pres, ev, case, plan, allsub, applied)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main.py",
        description="writing-07: manuscript baseline + reviewer comment summary -> revised manuscript, "
                    "response letter, change locator table, evidence list, result.json (stdlib, exit 0).",
        epilog="run once (draft) -> fill <work>/edit_plan.json -> run again (finalize); "
               "plan schema: references/usage.md",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="/input", help="input dir (case.json + materials)")
    ap.add_argument("--output", default="/app/output", help="output dir for deliverables")
    ap.add_argument("--work", default="/app/work", help="work dir with edit_plan.json")
    ap.add_argument("--plan", default=None, help="explicit edit plan path")
    ap.add_argument("--stage", default="auto", choices=["auto", "plan", "draft", "finalize"],
                    help="auto: finalize if a plan exists, else draft")
    ap.add_argument("--deliverable-name", default="revised_manuscript.md", help="revised manuscript name")
    ap.add_argument("--version", action="version", version="reviewer-response-revision %s" % VERSION)
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Exception:
        err = traceback.format_exc(limit=6)
        try:
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=True)
            prev, _ = load_json(out / "result.json")
            prev = prev if isinstance(prev, dict) else {}
            prev.update({"case_id": prev.get("case_id", "UNKNOWN-CASE"), "status": "partial",
                         "errors": (prev.get("errors") or []) +
                                   [{"where": "main", "error": err[-600:]}],
                         "runtime": {"version": VERSION, "elapsed_s": now()}})
            write_json(out / "result.json", prev)
        except Exception:
            pass
        sys.stderr.write(err)
        return 0


if __name__ == "__main__":
    sys.exit(main())
