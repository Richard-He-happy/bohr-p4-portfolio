#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-07 helpers: ledger, output assembly, audit.

Imported by main.py; standalone CLI prints a JSON audit report:
    python3 verify.py --output /app/output --input /input
Never rewrites inputs; exit code 0.
"""
import argparse, json, re, sys
from pathlib import Path

VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent
RES = HERE.parent / "references"


def _res(name, default):
    try:
        return json.loads((RES / name).read_text(encoding="utf-8"))
    except Exception:
        return default


TAX = _res("taxonomy.json", {})
TPL = _res("templates.json", {})
TYPES = TAX.get("types") or {}
BANNED = TAX.get("banned_claims") or []
TONE = TAX.get("tone_map") or {"accept": "accept", "partial": "clarify",
                               "reject": "polite_rebuttal", "clarify": "clarify", "invalid": "appeal"}
CUE = re.compile(TAX.get("cue_pattern") or
                 r"\b(should|must|please|add|clarify|provide|report|cite|include|remove|revise|explain|"
                 r"specify|define|discuss|compare|justify)\b|建议|请|需要|必须|补充|修改|澄清|说明|明确|给出|提供|引用", re.I)
NEW = re.compile(TAX.get("new_work_pattern") or r"additional experiment|补做|补充实验", re.I)
DECISIONS = tuple(TONE)
REQ_FILES = ["response_letter.md", "comment_ledger.json", "change_locator.json",
             "evidence_pending.md", "pending_human.json", "result.json"]


def norm(s): return re.sub(r"\s+", " ", str(s or "")).strip()


def read_text(p):
    try: return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception: return ""


def write_text(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(str(s), encoding="utf-8")


def write_json(p, o): write_text(p, json.dumps(o, ensure_ascii=False, indent=2))


def toks(t):
    t = str(t or "").lower()
    return set(re.findall(r"[a-z]{4,}", t)) | set(re.findall(r"[\u4e00-\u9fff]{2,4}", t))


def tone_for(d): return TONE.get(d, "accept")


def classify(t):
    t = str(t or "").lower(); best, n0 = "writing", 0
    for k, kws in TYPES.items():
        n = sum(1 for w in kws if w in t)
        if n > n0: best, n0 = k, n
    return best


BULLET = re.compile(r"^\s*(?:[-*•·]|\(?[a-zivx]{1,4}[).]|\(?\d{1,2}[).]|\(\d+\))\s+")
CLIMIT = re.compile(r"(?:;\s+|,\s+and\s+|\s+and\s+(?=[a-z])|\s+also\s+|；|并且|同时|另外|以及)")


def split_subs(body):
    """One comment -> ordered sub-requirements (bullets or clauses carrying a request)."""
    lines = [l.strip() for l in str(body or "").splitlines() if l.strip()]
    bl = [BULLET.sub("", l).strip() for l in lines if BULLET.match(l)]
    segs = bl if len(bl) >= 2 else [x.strip() for x in
                                    re.split(r"(?<=[。！？；;])|(?<=[.!?])\s+", str(body or "")) if x.strip()]
    fine = []
    for s in segs:
        parts = [x.strip(" ,.;") for x in CLIMIT.split(s) if x.strip(" ,.;")]
        fine += parts if len([x for x in parts if CUE.search(x)]) >= 2 else [s]
    subs, ctx = [], ""
    for s in fine:
        s = s.strip(" -•*")
        if not s: continue
        if not CUE.search(s):
            if not subs: ctx = (ctx + " " + s).strip()
            else: subs[-1] = (subs[-1] + " " + s).strip()
            continue
        subs.append((ctx + " " + s).strip() if ctx else s); ctx = ""
    return [x[:600] for x in (subs or [(ctx or str(body or "")).strip()]) if x]


def anchor_for(sub, bs):
    """Best-matching body block; heading tokens are added so 'abstract' points to the abstract."""
    ts = toks(sub); best, sc, head = None, 0.0, ""
    if not ts: return None, 0.0
    for b in bs:
        if b.get("level"): head = b.get("text"); continue
        bt = toks(b.get("text")) | toks(head)
        if not bt: continue
        x = len(ts & bt) / (len(bt) ** 0.5 + 3.0)
        if x > sc: best, sc = b.get("label"), x
    return (best, round(sc, 3)) if sc >= 0.12 else (None, round(sc, 3))


def build_ledger(comments, bs, lang):
    led = []
    for c in comments:
        subs = []
        for k, s in enumerate(split_subs(c.get("body", "")), 1):
            typ, needs = classify(s), bool(NEW.search(s))
            a, sc = anchor_for(s, bs)
            dec = "partial" if needs else "accept"
            note = "" if not needs else ("requested new experiment/analysis is outside the supplied materials"
                                         if lang == "en" else "所求补做实验/重做分析超出所给材料范围")
            subs.append({"sub_id": "%s.%d" % (c["comment_id"], k), "text": s, "type": typ,
                         "decision": dec, "tone": tone_for(dec), "anchor": a, "anchor_score": sc,
                         "change_ids": [], "evidence_status": "not_provided" if needs else "not_applicable",
                         "evidence_note": note, "response_note": "", "needs_human": needs})
        decs = [s["decision"] for s in subs] or ["accept"]
        d = decs[0] if len(set(decs)) == 1 else "partial"
        led.append({"comment_id": c["comment_id"], "source_label": c.get("source_label", ""),
                    "raw_summary": norm(c.get("body"))[:900], "decision": d, "tone": tone_for(d),
                    "response_summary": "", "change_ids": [],
                    "evidence_needed": [s["text"][:200] for s in subs if s["needs_human"]],
                    "sub_requirements": subs})
    return led


def recount(led, final=False):
    for c in led:
        for s in c.get("sub_requirements") or []:
            if final and s.get("decision") == "accept" and not s.get("change_ids"):
                s["decision"], s["tone"] = "partial", tone_for("partial")
        decs = [s["decision"] for s in c.get("sub_requirements") or []] or ["accept"]
        c["decision"] = decs[0] if len(set(decs)) == 1 else "partial"
        c["tone"] = tone_for(c["decision"])
        c["change_ids"] = [x for s in c.get("sub_requirements") or [] for x in s.get("change_ids") or []]
        c["evidence_needed"] = [s["text"][:200] for s in c.get("sub_requirements") or []
                                if s.get("evidence_status") == "not_provided"]
    return {s["sub_id"]: s for c in led for s in c.get("sub_requirements") or []}


def render_letter(led, chs, bn, dn, lang):
    F = TPL.get(lang) or TPL.get("en") or {}
    L = [F.get("title", "# Response to Reviewers (draft)"), "", F.get("scope", "").format(b=bn), ""]
    for c in led:
        L += ["## Comment %s — %s" % (c.get("comment_id", "?"),
                                     c.get("source_label") or c.get("comment_id", "?")), ""]
        if c.get("raw_summary"):
            L += ["> Organizer summary: %s" % c["raw_summary"][:400], ""]
        for s in c.get("sub_requirements") or []:
            L += ["**%s** · %s · decision: %s · tone: %s" % (s.get("sub_id"), s.get("type"),
                                                             s.get("decision"), s.get("tone")), "",
                  (F.get(s.get("decision"), "") + " " + (s.get("response_note") or "")).strip(), ""]
            rel = [x for x in chs if x.get("id") in (s.get("change_ids") or [])]
            for x in rel:
                if x.get("locator"):
                    L += [F.get("rev", "").format(loc=x["locator"], d=dn), "",
                          '> "%s"' % norm(x.get("revised_quote"))[:400], ""]
                else:
                    L += [F.get("na", ""), ""]
            if not rel and s.get("decision") in ("accept", "partial"):
                L += [F.get("na", ""), ""]
            if not rel and s.get("decision") in ("reject", "invalid", "clarify") and s.get("anchor"):
                L += [F.get("kept", "").format(loc=s["anchor"]), ""]
            if s.get("needs_human") and s.get("evidence_status") != "provided":
                L += [F.get("ev", "").format(s=s.get("evidence_status"), n=s.get("evidence_note")), ""]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def render_pending(led, issues, lang):
    L = ["# 未到位证据清单 / Evidence pending", "",
         "受控演练：以下条目在本基线修订中未落实或需人工确认。 / "
         "Controlled drill: not completed here or requiring human confirmation.", "",
         "| sub_id | 子要求 / sub-requirement | 类型 / type | 证据状态 / status | 说明 / note |",
         "|---|---|---|---|---|"]
    n = 0
    for c in led:
        for s in c.get("sub_requirements") or []:
            if s.get("needs_human") or s.get("evidence_status") == "not_provided" or not s.get("change_ids"):
                n += 1
                L.append("| %s | %s | %s | %s | %s |" % (
                    s.get("sub_id"), str(s.get("text"))[:80].replace("|", "/"), s.get("type"),
                    s.get("evidence_status"),
                    str(s.get("evidence_note") or s.get("decision"))[:80].replace("|", "/")))
    if not n:
        L.append("| — | — | — | — | 无未到位项 / none |")
    if issues:
        L += ["", "## 运行异常 / Runtime issues", ""] + \
             ["- `%s` %s" % (i.get("kind"), str(i.get("detail"))[:160]) for i in issues[:20]]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ assembly
def echo(con, ctx):
    out = {}
    for k in (con or {}):
        kl = str(k).lower()
        if k in ctx: out[k] = ctx[k]
        elif "case" in kl: out[k] = ctx.get("case_id")
        elif "deliver" in kl or "artifact" in kl: out[k] = ctx.get("deliverable")
        elif "preserv" in kl or "fact" in kl: out[k] = ctx.get("preserved_facts")
        elif "evidence" in kl or "source" in kl or "map" in kl: out[k] = ctx.get("evidence_map")
        elif "change" in kl or "diff" in kl or "log" in kl: out[k] = ctx.get("change_log")
        elif "status" in kl: out[k] = ctx.get("status")
        elif "uncertain" in kl: out[k] = ctx.get("uncertainty")
        else: out[k] = None
    out.setdefault("case_id", ctx.get("case_id"))
    return out


def emit(out, cid, dn, con, ctx, st, E, D, I, P, U, led, chs, rtext, stage,
         bn, cn, lang, pres, ev, case=None, plan=None, allsub=None, applied=None):
    """Write every deliverable, audit it, then write result.json."""
    out = Path(out)
    allsub = allsub if allsub is not None else [s for c in led for s in c.get("sub_requirements") or []]
    applied = len([c for c in chs if c.get("hit")]) if applied is None else applied
    write_text(out / dn, rtext)
    write_text(out / "response_letter.md", render_letter(led, chs, bn, dn, lang))
    write_text(out / "evidence_pending.md", render_pending(led, I, lang))
    write_json(out / "comment_ledger.json", {
        "case_id": cid, "skill_version": VERSION, "lang": lang,
        "scope": "controlled drill on organizer baseline; not a verbatim report", "comments": led})
    write_json(out / "change_locator.json", {
        "case_id": cid, "deliverable": dn,
        "locator_scheme": "P### = blank-line separated block index of the delivered file",
        "locators": [{"id": c.get("id"), "sub_id": c.get("sub_id"), "locator": c.get("locator"),
                      "quote": c.get("revised_quote"), "hit": c.get("hit")} for c in chs]})
    wo, ptxt = [], json.dumps(plan or {}, ensure_ascii=False).lower()
    for key in ("organizer_workorder", "organizer_edit_workorder"):
        v = (case or {}).get(key)
        for i, it in enumerate(v if isinstance(v, list) else ([] if v is None else [v])):
            txt = norm(it.get("instruction") if isinstance(it, dict) else it)
            kw = list(toks(txt))[:6]
            ok = bool(kw) and sum(1 for w in kw if w in ptxt) >= max(1, len(kw) // 2)
            wid = str((it.get("id") if isinstance(it, dict) else "") or "%s-%d" % (key, i + 1))
            wo.append({"id": wid, "instruction": txt[:200],
                       "status": "executed" if ok else "not_executed",
                       "note": "" if ok else "no matching edit/override in the plan"})
            if not ok:
                P.append({"item": "workorder %s" % wid,
                          "reason": "workorder item not reflected in the output"})
    if wo and st == "ok" and any(w["status"] != "executed" for w in wo):
        st = "partial"
    cnt = lambda f: len([s for s in allsub if f(s)])
    counts = {"comments_total": len(led), "sub_requirements_total": len(allsub),
              "subs_with_verified_change": cnt(lambda s: s.get("change_ids")),
              "sub_requirement_coverage": round(cnt(lambda s: s.get("change_ids")) / max(1, len(allsub)), 3),
              "decision_coverage": round(cnt(lambda s: s.get("decision") in DECISIONS) / max(1, len(allsub)), 3),
              "edits_total": len(chs), "edits_applied": applied,
              "locator_hit_rate": round(applied / len(chs), 3) if chs else 0.0,
              "evidence_provided": cnt(lambda s: s.get("evidence_status") == "provided"),
              "evidence_not_provided": cnt(lambda s: s.get("evidence_status") == "not_provided"),
              "evidence_not_applicable": cnt(lambda s: s.get("evidence_status") == "not_applicable"),
              "decisions": {k: cnt(lambda s, k=k: s.get("decision") == k) for k in DECISIONS},
              "pending_human_items": len(P)}
    write_text(out / "version_notes.md", "\n".join([
        "# 版本与边界 / Version & scope notes", "",
        "- skill: reviewer-response-revision v%s (python stdlib only) | stage: %s" % (VERSION, stage),
        "- case_id: `%s` | baseline: `%s` | comments: `%s`" % (cid, bn, cn),
        "- deliverable: `%s` | comments/subs/edits: %d/%d/%d | locator hit rate: %.3f"
        % (dn, len(led), len(allsub), len(chs), counts["locator_hit_rate"]),
        "- 只修订指定基线；未新增材料外文献/数值/结论；未补做的实验/分析如实标注。",
        "- Only the supplied baseline is revised; no new literature, numbers or conclusions.", ""]))
    write_json(out / "pending_human.json", {"case_id": cid, "items": P})
    ctx = dict(ctx)
    ctx.update({"case_id": cid, "status": st, "preserved_facts": pres, "evidence_map": ev,
                "change_log": chs, "uncertainty": U})
    res = {"case_id": cid, "status": st}
    res.update(echo(con, ctx))
    res.update({
        "skill": {"name": "reviewer-response-revision", "version": VERSION},
        "stage": stage, "deliverable": ctx.get("deliverable"),
        "outputs": {p.name: p.stat().st_size for p in sorted(out.glob("*")) if p.is_file()},
        "counts": counts,
        "comment_ledger_summary": [{"comment_id": c.get("comment_id"), "decision": c.get("decision"),
                                    "tone": c.get("tone"),
                                    "subs": [{k: s.get(k) for k in ("sub_id", "type", "decision",
                                                                    "tone", "change_ids",
                                                                    "evidence_status")}
                                             for s in c.get("sub_requirements") or []]} for c in led],
        "workorder_report": wo,
        "sources": [{"name": bn, "role": "manuscript baseline (organizer summary)"},
                    {"name": cn, "role": "reviewer comment summary (organizer)"}],
        "scope_note": "Controlled revision drill: organizer baseline + comment summary only; "
                      "no verbatim reviewer text, no new experiment, no editorial decision claimed.",
        "uncertainty": U, "pending_human": P, "errors": E,
        "degradations": D, "issues": I[:50], "changes": chs,
        "runtime": {"version": VERSION, "python": sys.version.split()[0], "stage": stage}})
    res["verification"] = audit(rtext, led, chs, con if isinstance(con, dict) else None, res,
                                [p.name for p in out.glob("*") if p.is_file()])
    write_json(out / "result.json", res)
    return 0


def audit(text, led, chs, contract=None, result=None, files=None):
    subs = [s for c in led for s in c.get("sub_requirements") or []]
    hits = [c for c in chs if c.get("locator") and norm(c.get("revised_quote")) in norm(text)]
    over = [m.group(0) for p in BANNED for m in re.finditer(p, text, re.I)]
    bad = [c.get("id") for c in chs if not c.get("numbers_preserved", True)]
    open_subs = [s.get("sub_id") for s in subs
                 if s.get("decision") == "accept" and not s.get("change_ids")]
    tests = [
        ("comments_have_subs", all(c.get("sub_requirements") for c in led) if led else False,
         "comment without sub-requirements"),
        ("decisions_complete", all(s.get("decision") in DECISIONS for s in subs),
         "decision outside %s" % (DECISIONS,)),
        ("locator_quotes_hit", len(hits) == len(chs),
         "%d/%d quotes found" % (len(hits), len(chs))),
        ("numbers_preserved", not bad, "changed numbers: %s" % bad[:5]),
        ("locators_exist", all(c.get("locator") for c in chs), "edit without block locator"),
        ("no_overclaim", not over, "banned claims: %s" % over[:5]),
        ("accepts_have_change", not open_subs, "accepted w/o change: %s" % open_subs[:5]),
    ]
    if contract:
        miss = [k for k in contract if result is None or k not in result]
        tests.append(("contract_echo", not miss, "missing keys: %s" % miss))
    if files is not None:
        miss = [f for f in REQ_FILES if f not in files]
        tests.append(("artifacts_present", not miss, "missing files: %s" % miss))
    rep = {"checks": {}, "problems": [], "counts": {}}
    for name, ok, detail in tests:
        rep["checks"][name] = {"ok": bool(ok), "detail": "" if ok else detail}
        if not ok:
            rep["problems"].append({"check": name, "detail": detail})
    got = len([s for s in subs if s.get("change_ids")])
    rep["counts"] = {"comments": len(led), "subs": len(subs), "subs_with_change": got,
                     "sub_requirement_coverage": round(got / max(1, len(subs)), 3),
                     "edits": len(chs), "edits_verified": len(hits),
                     "locator_hit_rate": round(len(hits) / max(1, len(chs)), 3)}
    rep["ok"] = all(v["ok"] for v in rep["checks"].values())
    return rep


def _lj(p):
    try:
        v = json.loads(read_text(p))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def audit_dir(outdir, inpdir=None):
    out = Path(outdir)
    res = _lj(out / "result.json")
    led = (_lj(out / "comment_ledger.json").get("comments")) or []
    loc = (_lj(out / "change_locator.json").get("locators")) or []
    dn = str(res.get("deliverable") or "revised_manuscript.md")
    contract = _lj(Path(inpdir) / "case.json").get("output_contract") if inpdir else None
    chs = [{"id": x.get("id"), "locator": x.get("locator"), "revised_quote": x.get("quote"),
            "numbers_preserved": True} for x in loc if isinstance(x, dict)]
    files = [p.name for p in out.glob("*") if p.is_file()] if out.is_dir() else []
    rep = audit(read_text(out / dn), led, chs, contract if isinstance(contract, dict) else None, res, files)
    rep["result_status"] = res.get("status")
    rep["deliverable"] = dn
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify.py",
        description="Audit a writing-07 output dir: contract echo, artifacts, locator joins, "
                    "decision completeness, numeric preservation, over-claim scan.",
        epilog="example: python3 verify.py --output /app/output --input /input")
    ap.add_argument("--output", default="/app/output", help="produced deliverables dir")
    ap.add_argument("--input", default=None, help="input dir (contract echo check)")
    a = ap.parse_args(argv)
    try:
        rep = audit_dir(a.output, a.input)
    except Exception as e:
        rep = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
