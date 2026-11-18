#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-03 文献证据驱动写作：claims -> evidence_table -> draft（stdlib、离线、退出码恒 0）。"""
import argparse, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import discover, segment, parse_refs, toks, sim, grade, sents, down, cls, strip_tail, ABSQ, ref_entry, aux, receipt, V
import gold  # v2 资产层：金标准 / 差分 / 版本记录 / 运行日志 / 自检（失败只降级，不影响主产物）

F5 = ["case_id", "deliverable", "preserved_facts", "evidence_map", "change_log"]
Z = {"zh": {"t": "证据驱动成稿（案例 {c}）", "lim": "证据边界", "ref": "参考文献",
            "h": {"高": "多项证据一致表明", "中": "现有研究提示", "低": "初步证据提示", "不足": "材料尚不足以判断"},
            "cf": "然而，材料存在不一致结果：", "uc": "（待核）",
            "lm": "低/不足论断只作线索（%s）|材料内有冲突结果，未合并（%s）|仅摘要可核来源未回原文确认|著录未联网核验",
            "rm": "（无著录；来源 {s}，定位 {l}）", "rs": "材料内文献表（原样转录）", "rt": "按首次引用编号；未给 DOI 不补写"},
     "en": {"t": "Evidence-driven draft (case {c})", "lim": "Boundaries", "ref": "References",
            "h": {"高": "Evidence indicates that", "中": "Studies suggest that", "低": "Preliminary evidence suggests that",
                  "不足": "The material cannot determine whether"},
            "cf": "However, inconsistent results are reported: ", "uc": " (to be checked)",
            "lm": "Weak claims are leads only (%s)|Conflicts kept (%s)|Abstract-only unchecked|References unverified",
            "rm": "(no record; source {s})", "rs": "Material reference list (verbatim)", "rt": "Numbered by first citation"}}

def jd(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + ".t"); t.write_text(json.dumps(o, ensure_ascii=False, indent=2), "utf-8"); t.replace(p)

def wt(p, s):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, "utf-8")

NEG = re.compile(r"(no significant|not significant|no association|not associated|did not|no effect|failed to|相反|无显著|未发现|不相关|无效)", re.I)
POS = re.compile(r"(significant|increased|higher|greater|improved|effective|显著|提高|改善|有效|增加|降低)", re.I)

def build_claims(docs, us, case, instr):
    cl = []
    dr = [d for d in docs if d["kind"] == "draft" and d["text"].strip()]
    if dr:
        d = dr[0]
        for u in us:
            t = u["text"].strip()
            if u["doc"] == d["doc_id"] and len(t) >= 8 and not re.match(r"^(\||-{3,}|\[\d+\]\s)", t):
                cl.append({"claim_id": "C%03d" % (len(cl) + 1), "text": t, "core": strip_tail(t), "type": cls(t),
                           "location": "draft:%s %s" % (d["path"], u["loc"]), "uid": u["uid"], "doc": u["doc"],})
        return cl, "revise", d
    topic = (instr + " " + json.dumps(case.get("source") or {}, ensure_ascii=False))[:6000]
    tt = toks(topic); rid = {d["doc_id"] for d in docs if d["kind"] == "references"}
    cs = sorted(((sim(topic, u["text"], tt) + (.04 if re.search(r"\d", u["text"]) else 0), u) for u in us
                 if u["doc"] not in rid and len(u["text"]) >= 20 and not re.match(r"^(参考文献|references?|doi|https?)", u["text"], re.I)),
                key=lambda x: -x[0])
    m = re.search(r"(\d{2,4})\s*(?:字|words?|词|characters?)", topic, re.I)
    need = max(3, min(12, int(round((int(m.group(1)) if m else 240) / 30.0))))
    pick, per = [], {}
    for s, u in cs:
        if len(pick) >= need: break
        if per.get(u["doc"], 0) >= 2 or any(sim(u["text"], p["text"]) > .8 for p in pick): continue
        per[u["doc"]] = per.get(u["doc"], 0) + 1; pick.append(u)
    for u in pick:
        cl.append({"claim_id": "C%03d" % (len(cl) + 1), "text": u["text"], "core": strip_tail(u["text"]), "type": cls(u["text"]),
                   "location": u["loc"], "uid": u["uid"], "doc": u["doc"],})
    return cl, "synthesize", None

def build_ev(cl, us, docs, refs):
    """论断->来源：池只含 material；引用锚点定向匹配；冲突显式记录。"""
    dm = {d["doc_id"]: d for d in docs}
    pool = [u for u in us if dm[u["doc"]]["kind"] == "material"]
    r2d = {}
    for r in refs:
        c = [(1.0 if (r["doi"] and r["doi"] in d["text"]) else sim(r["body"][:150], d["text"][:400]), d["doc_id"]) for d in docs if d["kind"] != "references"]
        c = [x for x in c if x[0] >= .45]
        if c: r2d[r["num"]] = max(c)[1]
    rows = []
    for c in cl:
        tc = toks(c["core"])
        anch = {r2d[int(x)] for x in re.findall(r"[\[［](\d{1,3})[\]］]", c["text"]) if int(x) in r2d}
        sc = sorted(((sim(c["core"], u["text"], tc), u) for u in pool), key=lambda x: -x[0])
        pin = [u for s, u in sc if u["doc"] in anch]
        b = (1., pin[0]) if pin else (sc[0] if sc else (0., None))
        thr = .05 if pin else .16
        if b[1] is None or b[0] < thr:
            rows.append({"claim_id": c["claim_id"], "claim": c["core"], "source_id": None, "locator": None, "quote": None, "source_type": None,
                         "strength": "不足", "strength_basis": {"reason": "无>=%.2f 重叠段落" % thr}, "support_scope": "无直接支撑",
                         "conflicts": [], "verified": False, "rationale": "未匹配到来源，需补证或改写"})
            continue
        ch = [b[1]]
        for s, u in sc:
            if u["uid"] in {x["uid"] for x in ch}: continue
            if (u["doc"] in anch or s >= max(thr, b[0] * .72)) and u["doc"] not in {x["doc"] for x in ch}:
                ch.append(u)
                if len(ch) >= 3: break
        cf = [{"source_id": u["doc"], "locator": u["loc"], "quote": u["text"], "similarity": round(s, 2), "why": "主题重叠但结论方向相反"}
              for s, u in sc if s >= .40 and u["uid"] not in {x["uid"] for x in ch}
              and bool(NEG.search(u["text"])) != bool(NEG.search(c["core"])) and (POS.search(u["text"]) or NEG.search(u["text"]))]
        for u in ch:
            d = dm[u["doc"]]; lv, why, bb = grade(u["text"], d["text"], len(ch), bool(cf), ABSQ(d))
            s = sim(c["core"], u["text"], tc)
            rows.append({"claim_id": c["claim_id"], "claim": c["core"], "source_id": u["doc"], "source_path": d["path"], "locator": u["loc"],
                         "quote": u["text"], "source_type": bb["design"], "strength": lv, "strength_basis": bb,
                         "rationale": why + ("；冲突下调" if cf else ""), "conflicts": cf[:3], "verified": True, "abstract_only": ABSQ(d),
                         "support_scope": ("直接支撑" if s >= .3 else "部分支撑（范围不一致）") + ("；n~%d" % bb["sample_size"] if bb["sample_size"] else "") +
                         ("；仅限该研究条件" if lv in ("低", "不足") else "")})
    return rows

def render(docs, cl, rows, mode, draft, cid, lg, case, refs):
    """成稿：实质句带引用编号、语气与强度相称、冲突句保留。"""
    L = Z[lg]; dm = {d["doc_id"]: d for d in docs}; od = {}; ch = []; byc = {}
    for r in rows: byc.setdefault(r["claim_id"], []).append(r)
    ix = {"不足": 0, "低": 1, "中": 2, "高": 3}
    cits = lambda ids: "".join("[%d]" % k for k in sorted({od.setdefault(i, len(od) + 1) for i in ids}))
    rs_of = lambda c: [r for r in byc.get(c["claim_id"], []) if r.get("quote")]
    lv_of = lambda c: min((r["strength"] for r in rs_of(c)), key=lambda x: ix[x]) if rs_of(c) else "不足"
    for c in cl:
        c["_t"], nt = down(c["core"])
        for k, a1, a2, why in nt:
            ch.append({"change_id": "CH%03d" % (len(ch) + 1), "claim_id": c["claim_id"], "action": k, "original_quote": a1,
                       "revised_quote": a2, "reason": why, "locator": c["location"], "human_confirm": True})

    def emit(c):
        rs, lv = rs_of(c), lv_of(c)
        t = re.sub(r"\s*(?:\[\d{1,3}\]|［\d{1,3}］|[。.；;])+\s*$", "", c["_t"]).rstrip()
        if not rs: return re.sub(r"[。.]$", "", t) + L["uc"]
        if lv in ("低", "不足") and not re.search(r"(可能|提示|初步|尚|may|suggest|prelim)", t, re.I):
            t = L["h"][lv] + ("，" if lg == "zh" else " ") + t
        t += cits(r["source_id"] for r in rs) + ("。" if lg == "zh" else ".")
        cf = [x for r in rs for x in (r.get("conflicts") or [])]
        if cf and " " not in t[-3:]:
            t += " " + L["cf"] + re.sub(r"[。.]$", "", cf[0]["quote"][:150]) + cits(x["source_id"] for x in cf[:2]) + ("。" if lg == "zh" else ".")
        return t

    J = "" if lg == "zh" else " "
    o = ["# " + L["t"].format(c=cid), ""]
    src = case.get("source")
    if isinstance(src, dict) and any(src.values()): o += ["> " + "；".join("%s=%s" % (k, v) for k, v in src.items() if v), ""]
    if mode == "revise" and draft:
        cm = {c["text"]: c for c in cl}
        o += ["<!-- 修订稿：保留原块结构；逐句补证、按强度调语气、过度推断已下调 -->", ""]
        for blk in re.split(r"\n\s*\n", draft["text"]):
            b = blk.strip()
            if b: o += [(b if re.match(r"^#{1,6}\s", b) else J.join([emit(cm[s]) if s in cm else s for s in sents(b)])), ""]
    else:
        pa = []
        for c in cl:
            pa.append(emit(c))
            if len(pa) >= 3: o += [J.join(pa), ""]; pa = []
        if pa: o += [J.join(pa), ""]
    lm = L["lm"].split("|")
    low = [c["claim_id"] for c in cl if not [r for r in byc.get(c["claim_id"], []) if r.get("strength") in ("高", "中")]]
    co = sorted({r["claim_id"] for r in rows if r.get("conflicts")})
    o += ["## " + L["lim"], ""]
    if low: o.append("- " + lm[0] % "、".join(low[:8]))
    if co: o.append("- " + lm[1] % "、".join(co))
    if any(r.get("abstract_only") for r in rows): o.append("- " + lm[2])
    o += ["- " + lm[3], "", "## " + L["ref"], "", "<!-- %s -->" % L["rt"]]
    for d, k in sorted(od.items(), key=lambda x: x[1]): o += ["[%d] %s" % (k, ref_entry(dm.get(d, {}), refs, k, L)), ""]
    if refs: o += ["## " + L["rs"], ""] + ["- " + x["raw"] for x in refs]
    return "\n".join(o).rstrip() + "\n", ch, od

def run(a):
    t0 = time.time(); er = []; dg = []; ph = []; sr = []; case = {}; con = {}; cid = "UNKNOWN"; instr = ""

    def P(i, d, n, s=None):
        ph.append({"id": "P%03d" % (len(ph) + 1), "issue": i, "detail": d, "needed": n, "source_id": s})

    def S(st, fn, dflt):
        try: return fn()
        except Exception as e:
            er.append({"stage": st, "type": type(e).__name__, "detail": str(e)[:200]}); return dflt

    ind = next((Path(c) for c in ([a.input] if a.input else []) + ["/input", "input"] if c and Path(c).is_dir()), None)
    out = Path(a.output or "/app/output")
    try:
        out.mkdir(parents=True, exist_ok=True); (out / ".probe").write_text("x", "utf-8"); (out / ".probe").unlink()
    except Exception: out = Path.cwd() / "output"; out.mkdir(parents=True, exist_ok=True)

    LOG = gold.Log(out / "run.log")
    LOG.w("start", "argv=%s input=%s output=%s py=%s" % (sys.argv[1:], ind, out, sys.version.split()[0]))

    def partial():
        r = {"case_id": cid, "status": "partial", "skill_version": V, "sources": sr}
        for k in con: r[k] = None if k in F5 else con[k]
        for k in F5: r.setdefault(k, [] if k != "deliverable" else None)
        r["case_id"] = cid
        jd(out / "result.json", r)

    partial()
    if ind is None: er.append({"stage": "input", "type": "no_input_dir", "detail": "无 input"})
    else:
        for c in [ind / "case.json"] + sorted(ind.glob("*case*.json")):
            if c.is_file() and not case:
                case = S("input", lambda: json.loads(c.read_text(encoding="utf-8", errors="ignore")), {})
        if not case: er.append({"stage": "input", "type": "no_case_json", "detail": "无 case"})
        if isinstance(case.get("output_contract"), dict): con = dict(case["output_contract"])
        cid = str(case.get("case_id") or case.get("id") or "UNKNOWN")
        instr = " ".join(str(case.get(k) or "") for k in ("task_instruction", "task", "instruction", "prompt", "goal"))
        for tm in ("task.md", "task.txt"):
            if (ind / tm).is_file(): instr += " " + (ind / tm).read_text(encoding="utf-8", errors="ignore")[:4000]; break
    if not con:
        con = {k: None for k in F5}; er.append({"stage": "contract", "type": "missing_output_contract", "detail": "兜底 5 字段"})
    partial()

    docs = S("discover", lambda: discover(ind, case) if ind else [], [])
    for d in docs:
        sr.append({"source_id": d["doc_id"], "path": d["path"], "bytes": d["bytes"], "sha256": d["sha256"], "kind": d["kind"], "read_method": d["method"]})
        if d["note"]: dg.append({"stage": "extract", "source_id": d["doc_id"], "type": "extraction_partial", "detail": d["note"]})
        if not d["text"].strip(): P("无可抽文本", "%s(%s)" % (d["path"], d["method"]), "OCR 或人工转录", d["doc_id"])
    if not docs: P("无材料", "只有 case.json", "确认 artifacts")
    LOG.w("discover", "docs=%d degradations=%d" % (len(docs), len(dg)))
    units = S("segment", lambda: segment(docs), [])
    refs = S("refs", lambda: parse_refs(docs), [])
    if not refs: P("无文献表", "不能核对著录", "补文献表")
    lg = "zh" if len(re.findall(r"[\u4e00-\u9fff]", " ".join(d["text"][:800] for d in docs) + instr)) > 20 else "en"
    cl, mode, draft = S("claims", lambda: build_claims(docs, units, case, instr), ([], "synthesize", None))
    if not cl: P("无论断", "文本过短", "提供正文/摘要")
    LOG.w("claims", "mode=%s claims=%d units=%d refs=%d" % (mode, len(cl), len(units), len(refs)))
    rows = S("evidence", lambda: build_ev(cl, units, docs, refs), [])
    doc, ch, od = S("render", lambda: render(docs, cl, rows, mode, draft, cid, lg, case, refs),
                    ("# %s\n\n（成稿渲染失败，claims/evidence_table 仍可用）\n" % cid, [], {}))
    wt(out / "evidence_driven_draft.md", doc); wt(out / "deliverable.md", doc)
    pool = "\n".join(d["text"] for d in docs)
    for r in rows:
        if r.get("quote") and r["quote"] not in pool:
            r["verified"] = False
            dg.append({"stage": "verify", "source_id": r.get("source_id"), "type": "quote_not_verbatim", "detail": "%s 引文未逐字命中" % r["claim_id"]})
            P("引文未命中", r["claim_id"], "回原文核对", r.get("source_id"))
    unsup = [c["claim_id"] for c in cl if not [r for r in rows if r["claim_id"] == c["claim_id"] and r.get("source_id")]]
    for x in unsup: P("论断无支撑", x, "补证或删句")

    facts = []
    for u in units:
        for mm in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(%|‰|mg|g|kg|mL|L|μL|µm|nm|mm|cm|h|min|s|岁|例|名|倍|℃|个月|年|周|天)", u["text"]):
            facts.append({"fact_id": "F%03d" % (len(facts) + 1), "value": mm.group(0),
                          "quote": u["text"][:180], "locator": u["loc"], "source_id": u["doc"], "in_draft": mm.group(0) in doc})
    facts = facts[:200]
    ev = [r for r in rows if r.get("source_id")]
    LOG.w("evidence", "rows=%d with_source=%d quote_fail=%d" % (len(rows), len(ev), sum(1 for r in ev if not r.get("verified"))))
    cst = {}
    for r in rows: cst[r["strength"]] = cst.get(r["strength"], 0) + 1
    met = dict(claims_total=len(cl), claims_with_source=len(cl) - len(unsup), claims_unsupported=len(unsup), evidence_rows=len(rows),
               quotes_verified=sum(1 for r in ev if r.get("verified")), quotes_failed=sum(1 for r in ev if not r.get("verified")),
               strength_counts=cst, claims_with_conflict=len({r["claim_id"] for r in rows if r.get("conflicts")}),
               overclaim_downgrades=len(ch), distinct_sources_cited=len(od), citation_markers=len(re.findall(r"\[\d+\]", doc)),
               preserved_facts=len(facts), pending_human=len(ph),
               support_rate=round((len(cl) - len(unsup)) / len(cl), 3) if cl else 0.0,
               strength_label_rate=round(sum(1 for r in rows if r.get("strength")) / len(rows), 3) if rows else 0.0)
    hedge = "高→“%s”；中→“%s”；低→“%s”；不足→“%s”" % tuple(Z[lg]["h"][k] for k in ("高", "中", "低", "不足"))
    S("aux", lambda: aux(out, rows, refs, hedge), None)
    jd(out / "claims.json", {"case_id": cid, "language": lg, "count": len(cl),
                             "claims": [{k: v for k, v in c.items() if not k.startswith("_") and k != "uid"} for c in cl]})
    jd(out / "evidence_table.json", {"case_id": cid, "count": len(rows),
                                     "schema": "claim_id,source_id,locator,quote,strength,support_scope,conflicts,rationale,verified", "rows": rows})
    jd(out / "pending_human.json", {"case_id": cid, "items": ph})
    st = "input_error" if (not docs or not units) else "insufficient_evidence" if (not cl or not ev) else \
        "partial" if (er or unsup or met["quotes_failed"]) else "ok"
    if time.time() - t0 > 780: dg.append({"stage": "budget", "type": "time_budget", "detail": "预算，提前 finalize"})
    emap = [{"claim_id": c["claim_id"], "claim": c["core"], "claim_type": c["type"], "claim_location": c["location"],
             "strength": min((r["strength"] for r in rows if r["claim_id"] == c["claim_id"]),
                             key=lambda x: ["不足", "低", "中", "高"].index(x), default="不足"),
             "evidence": [r for r in rows if r["claim_id"] == c["claim_id"]], "unsupported": c["claim_id"] in unsup} for c in cl]
    unc = ["著录与真实性未联网核验（离线），DOI/期刊/年份按材料转录"]
    if met["claims_with_conflict"]: unc.append("冲突证据 %d 条，已在 conflicts 与成稿表述中保留" % met["claims_with_conflict"])
    if unsup: unc.append("未匹配来源：" + "、".join(unsup[:6]))
    if any(r.get("abstract_only") for r in rows): unc.append("含仅摘要可核来源，强度最高记中")
    res = {"case_id": cid, "status": st, "skill": "writing-03-evidence", "skill_version": V,
           "deliverable": doc, "deliverable_path": str(out / "evidence_driven_draft.md"),
           "preserved_facts": facts, "evidence_map": emap, "change_log": ch,
           "claims": {"path": str(out / "claims.json"), "count": len(cl)},
           "evidence_table": {"path": str(out / "evidence_table.json"), "count": len(rows)},
           "workorder_receipt": receipt(case, doc, od), "sources": sr, "metrics": met,
           "uncertainty": unc, "pending_human": ph, "errors": er, "degradations": dg, "changes": ch,
           "runtime": {"script": "main.py", "version": V, "python": sys.version.split()[0], "seconds": round(time.time() - t0, 2),
                       "argv": sys.argv[1:], "network": "disabled"}}
    merged = {}
    for k, v in con.items(): merged[k] = res[k] if k in F5 else res.get(k, v)
    for k in F5: merged.setdefault(k, res[k])
    for k, v in res.items(): merged.setdefault(k, v)
    jd(out / "result.json", merged)
    LOG.w("finalize", "status=%s claims=%d rows=%d pending=%d errors=%d" % (st, len(cl), len(rows), len(ph), len(er)))
    g = S("assets", lambda: gold.run(ind, out, case, LOG), {}) or {}
    for k, v in g.items(): merged[k] = v
    for k in ("golden_standard", "diff_report", "version_history", "self_check"): merged.setdefault(k, None)
    S("assets", lambda: jd(out / "result.json", merged), None)
    print("done %s claims=%d rows=%d quote=%d/%d pending=%d assets=%d" % (st, len(cl), len(rows), met["quotes_verified"],
          len(ev), len(ph), len(g)))

def _fail(path, e):
    """致命异常兜底：仍写合法 partial result.json。"""
    try:
        o = Path(path); o.mkdir(parents=True, exist_ok=True); p = o / "result.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        cur["case_id"] = cur.get("case_id") or "UNKNOWN"; cur["status"] = "partial"
        for k in ("preserved_facts", "evidence_map", "change_log", "sources", "errors", "pending_human", "changes"): cur.setdefault(k, [])
        cur.setdefault("deliverable", None); cur.setdefault("uncertainty", ["未完成"])
        cur["errors"] = cur["errors"] + [{"stage": "fatal", "type": type(e).__name__, "detail": str(e)[:400]}]
        jd(p, cur)
    except Exception: pass

def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="writing-03 文献证据驱动写作：claims -> evidence_table -> draft；"
                                 "纯标准库、离线、先写 partial 再 finalize、退出码恒 0。",
                                 epilog="输入默认 /input（回退 ./input），输出默认 /app/output。")
    ap.add_argument("--input", help="输入目录（默认 /input）"); ap.add_argument("--output", help="输出目录（默认 /app/output）")
    ap.add_argument("--version", action="version", version="writing-03 " + V)
    a = ap.parse_args(argv)
    try: run(a)
    except Exception as e:
        _fail(a.output or "/app/output", e)
        import traceback; traceback.print_exc()
    return 0

if __name__ == "__main__":
    sys.exit(main())
