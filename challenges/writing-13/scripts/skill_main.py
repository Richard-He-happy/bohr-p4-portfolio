#!/usr/bin/env python3
"""Grant-proposal seven-section skill: init -> agent writes -> finalize.

  skill_main.py [init|finalize|all] --input /input --output /app/output
  verify.py --output /app/output      # standalone audit
Stdlib only, no network, CWD independent, exit code 0.
"""
import argparse, json, re, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import verify as V
except Exception:
    V = None
CK = ("case_id", "deliverable", "preserved_facts", "evidence_map", "change_log")


def rj(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return d


def wj(p, o):
    try:
        Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def wt(p, t, over=True):
    p = Path(p)
    if p.exists() and not over:
        return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(t, encoding="utf-8")
        return True
    except Exception:
        return False


def T(name, dflt=""):
    try:
        s = (HERE.parent / "references" / "consistency-checklist.md").read_text(encoding="utf-8")
        m = re.search(r"<!--BEGIN:%s-->(.*?)<!--END:%s-->" % (name, name), s, re.S)
        return (m.group(1).strip() + "\n") if m else dflt
    except Exception:
        return dflt


def d_out(x):
    if x:
        return Path(x).expanduser().resolve()
    for c in (Path("/app/output"), HERE.parent.parent / "output"):
        try:
            c.mkdir(parents=True, exist_ok=True)
            return c.resolve()
        except Exception:
            pass
    return Path("/app/output")


def wo_find(o, d=0):
    # locate the work order by structure, not a fixed key name
    if d > 6 or not isinstance(o, (dict, list)):
        return None
    if isinstance(o, dict) and "sections" in o and ("draft_size" in o or "planning_months" in o
                                                   or "consistency" in o):
        return o
    for _, v in (o.items() if isinstance(o, dict) else enumerate(o)):
        g = wo_find(v, d + 1)
        if g:
            return g
    return None


def load(inp, out):
    c = {"case_id": None, "contract": {}, "workorder": {}, "errors": [], "degradations": [],
         "changes": [], "sources": [], "out": str(out)}
    cp = inp / "case.json"
    if not cp.exists() and inp.exists():
        cp = next(iter(sorted(inp.rglob("case*.json"))), None)
    case = rj(cp) if cp else None
    if not isinstance(case, dict):
        c["errors"].append({"code": "case_json_unreadable", "message": "case.json 缺失或非法"})
        c["degradations"].append("case_json_unreadable")
        case = {}
    c["case_id"] = case.get("case_id")
    c["contract"] = case.get("output_contract") or {}
    wo = wo_find(case)
    if wo is None:
        c["degradations"].append("workorder_absent_defaults_applied")
    c["workorder"] = wo or {}
    return c


def plan(c):
    wo = c["workorder"] or {}
    m = re.search(r"(\d{3,4})\s*[–\-—~至到]\s*(\d{3,4})", str(wo.get("draft_size") or ""))
    lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1600, 2600)
    secs = [s for s in (wo.get("sections") or []) if isinstance(s, dict)]
    out = []
    for meta in (V.SEVEN if V else []):
        h = next((s for s in secs if any(a in str(s.get("title", "")) for a in meta["aliases"])), {}) or {}
        out.append({"id": h.get("id", meta["id"]), "title": h.get("title", meta["title"]),
                    "minimum": h.get("minimum", ""), "budget": meta["budget"]})
    return {"sections": out, "lo": lo, "hi": hi, "months": int(wo.get("planning_months") or 12),
            "cap": int(wo.get("planning_unit_cap") or 100),
            "um": wo.get("planning_unit_meaning") or "规划单位：非货币、非已获资金、非真实预算。",
            "auth": wo.get("authority") or "organizer-workorder-not-funder-policy"}


def auth_of(wo):
    sb = (wo or {}).get("source_basis") or {}
    n, p = sb.get("external_authors") or [], sb.get("published_paper") or ""
    return "（%s%s）" % ("、".join(n), "，" + p if p else "") if n else "（外部作者）"


def ph_seed(wo):
    sb = (wo or {}).get("source_basis") or {}
    it = [{"id": "PH1", "topic": "真实申请人证据", "need": "申请人自有前期成果、数据与平台条件证明",
           "why": "既有结果归外部作者，不能作申请人基础（applicant_owned=%s）"
                  % sb.get("applicant_owned_preliminary_results_supplied"),
           "evidence_needed": "申请人已完成实验/论文记录",
           "affected_sections": ["foundation", "background"], "status": "open", "blocking": True},
          {"id": "PH2", "topic": "真实资助要求", "need": "真实资助指南、申报口径与政策条款",
           "why": "authority=%s，仅评测写作要求（funder_notice=%s）"
                  % ((wo or {}).get("authority"), sb.get("actual_funder_notice_supplied")),
           "evidence_needed": "当年度申报指南原文与评审要点",
           "affected_sections": ["background", "goals"], "status": "open", "blocking": True}]
    if sb.get("resource_availability_evidence_supplied") is not True:
        it.append({"id": "PH3", "topic": "资源可用性证据", "need": "设备、材料、算力与人员投入证明",
                   "why": "resource_availability=%s，不得写“设备已具备”"
                          % sb.get("resource_availability_evidence_supplied"),
                   "evidence_needed": "设备清单与可用时段、协作分工",
                   "affected_sections": ["foundation", "route"], "status": "open", "blocking": False})
    return it


def units(p):
    return {"cap": p["cap"], "unit_meaning": p["um"], "total": None,
            "note": "分项之和 = total 且 ≤ cap；非货币、非已获资金、非真实预算。",
            "items": [{"id": "WP%d" % i, "goal": "G%d" % i, "units": None,
                       "name": "（WP%d↔G%d）" % (i, i)} for i in (1, 2, 3)]}


def handoff(out, c, p, facts):
    h = T("skel", "> 字数 {lo}–{hi} 汉字；周期 {m} 月；规划单位上限 {cap}。")
    L = ["# 基金申请书章节草稿（骨架，待改写；不可直接提交）", "",
         h.format(lo=p["lo"], hi=p["hi"], m=p["months"], cap=p["cap"]).strip(),
         "> 结果归外部作者%s；先读 quote_bank.md 取逐字事实。" % auth_of(c["workorder"]), ""]
    for i, s in enumerate(p["sections"], 1):
        L += ["## %d. %s" % (i, s["title"]), "",
              "> 目标≈%d 字；%s 须实质正文+依据 locator+与邻节编号衔接。" % (s["budget"], s["minimum"]),
              "", "（在此写正文）", ""]
    wt(out / "proposal_skeleton.md", "\n".join(L))
    Q = ["# 候选逐字引文与执行约束（未改写）", "", "| source_id | 文件 | 类型 | 单元 |", "|-|-|-|-|"]
    Q += ["| %s | %s | %s | %d |" % (s["source_id"], s["name"], s["kind"], len(s["units"])) for s in c["sources"]]
    Q += ["", "## 带数值/单位的事实", ""]
    for f in facts:
        Q += ["- `%s` %s · %s · `%s`" % (f["fact_id"], f["source_id"], f["locator"], f["value"]),
              "  > %s" % f["quote"].replace("\n", " ")]
    Q += ["- authority=%s，不作为真实资助政策。" % p["auth"],
          "- 字数 %d–%d；周期 %d 月内；规划单位 ≤%d，非货币。" % (p["lo"], p["hi"], p["months"], p["cap"]),
          "- 目标恰 3 个 G1–G3，各对应工作包+里程碑+指标。"]
    wt(out / "quote_bank.md", "\n".join(Q) + "\n")


def _items(out, n):
    v = rj(out / n, None)
    return list(v) if isinstance(v, list) else (list((v or {}).get("items") or []) if isinstance(v, dict) else [])


def res(c, out, p, au, status=None):
    a, K = auth_of(c["workorder"]), (c["contract"] if isinstance(c["contract"], dict) else {})
    md = ""
    try:
        md = (out / "proposal.md").read_text(encoding="utf-8", errors="ignore") if (out / "proposal.md").exists() else ""
    except Exception:
        pass
    F, I = _items(out, "preserved_facts.json"), _items(out, "evidence_map.json")
    L, H = _items(out, "change_log.json"), _items(out, "pending_human.json")
    pu, tot = rj(out / "planning_units.json", {}) or {}, None
    if isinstance(pu.get("items"), list):
        ns = [i.get("units") for i in pu["items"] if isinstance(i, dict)]
        tot = sum(ns) if ns and all(isinstance(n, (int, float)) for n in ns) else None
    m = au.get("metrics", {})
    n = m.get("char_total", 0)
    seen = {str(x.get("original_quote", ""))[:40] for x in L if isinstance(x, dict)}
    for f in F:
        v = str((f or {}).get("value") or "")
        if not isinstance(f, dict) or not v or v not in md or str(f.get("quote", ""))[:40] in seen:
            continue
        s = sorted([x.strip() for x in re.split(r"(?<=[。\n])", md) if v in x], key=len)
        if not s:
            continue
        L.append({"id": "CLA%02d" % (len(L) + 1), "kind": "fact_carryover",
                  "original_quote": f.get("quote", ""), "revised_quote": s[0][:220],
                  "reason": "数值/条件逐字保留，改为拟开展语态；结果归外部作者%s" % a,
                  "locator": f.get("locator"), "source_id": f.get("source_id"),
                  "attribution": "external_author"})
        q = str(f.get("quote", ""))[:40]
        seen.add(q)
        if q not in {str(x.get("quote", ""))[:40] for x in I if isinstance(x, dict)}:
            I.append({"claim_id": "CE%02d" % (len(I) + 1), "section": None, "kind": "fact", "verified": True,
                      "claim": "沿用源材料事实 %s" % v, "source_id": f.get("source_id"),
                      "locator": f.get("locator"), "quote": f.get("quote", ""), "auto": True})
    secs = [{"id": k, "title": v["title"], "found": v["found"], "char_count": v["chars"]}
            for k, v in (V.section_spans(md).items() if (V and md) else [])]
    sup = [f for f in ("proposal.md", "evidence_map.json", "goal_matrix.md", "planning_units.json",
                       "risks.md", "pending_human.json", "draft_boundary.md") if (out / f).exists()]
    r = {"case_id": c["case_id"], "preserved_facts": F, "evidence_map": I, "change_log": L,
         "pending_human": H, "errors": list(c.get("errors", [])),
         "degradations": sorted(set(c.get("degradations", []))), "changes": c.get("changes", []),
         "status": status or au.get("status", "partial")}
    r["deliverable"] = {"file": "proposal.md", "path": str(out / "proposal.md"), "format": "markdown",
                        "editable": True, "char_count": n, "char_range": [p["lo"], p["hi"]],
                        "sections": secs, "supporting_files": sup,
                        "title": "基金申请书七要素章节草稿（源材料限定）"}
    for k, v in K.items():
        if k not in CK and k not in r:
            r[k] = v
    if K:
        r["output_contract_echo"] = K
    r["sources"] = [{"source_id": s["source_id"], "name": s["name"], "kind": s["kind"], "role": s["role"],
                     "units": len(s["units"]), "path": s.get("path")} for s in c.get("sources", [])]
    r["uncertainty"] = [
        {"id": "U1", "topic": "申请人自有证据缺失", "detail": "前期成果全部来自外部作者论文。", "impact": "foundation"},
        {"id": "U2", "topic": "真实资助要求缺失", "detail": "写作要求来自 organizer_workorder，非指南。", "impact": "background"},
        {"id": "U3", "topic": "资源可用性未证实", "detail": "设备/材料投入未证明，只作拟开展。", "impact": "route"}]
    r["runtime"] = {"tool": "skill_main.py", "version": "1.0.0", "network": False,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "seconds": round(time.time() - c.get("t0", time.time()), 2)}
    r["workorder_execution"] = {
        "workorder_id": (c["workorder"] or {}).get("id"), "authority": p["auth"], "authority_honored": True,
        "sections_expected": len(p["sections"]), "sections_satisfied": len(m.get("sections_found", [])),
        "char_count": n, "char_range": [p["lo"], p["hi"]],
        "char_count_in_range": p["lo"] <= n <= p["hi"], "planning_months": p["months"],
        "max_month_found": m.get("max_month"), "planning_units_total": tot, "planning_unit_cap": p["cap"],
        "planning_units_in_cap": isinstance(tot, (int, float)) and tot <= p["cap"],
        "goals_count": m.get("goals_count"), "matrix_rows": m.get("matrix_rows"),
        "risks_count": m.get("risks_count"), "pending_human_count": len(H),
        "limits_checks": {"attribution_flagged": m.get("attribution_flagged", 0),
                          "external_author_marked": m.get("external_author_marked", False),
                          "banned_phrases_unverified": m.get("banned_unverified", 0),
                          "currency_free": "万元" not in md and "￥" not in md}}
    r["checks"] = {"status": au.get("status"), "counts": au.get("counts"), "metrics": m,
                   "issues": au.get("issues", [])}
    return r


def fixunits(out, p, c):
    pu = rj(out / "planning_units.json", None)
    if not isinstance(pu, dict) or not isinstance(pu.get("items"), list):
        return
    its = [i for i in pu["items"] if isinstance(i, dict)]
    ns = [i.get("units") for i in its]
    if not its or not all(isinstance(x, (int, float)) for x in ns):
        return
    s = sum(ns)
    if s > p["cap"]:
        sc = [round(x * p["cap"] / s, 1) for x in ns]
        for i, x in zip(its, sc):
            i["units"] = x
        pu["total"] = round(sum(sc), 1)
        pu["repair_note"] = "合计 %.1f 超上限 %d，按比例缩放（不改结构），需人工复核。" % (s, p["cap"])
        c["changes"].append({"id": "CH-units", "file": "planning_units.json", "action": "rescale",
                             "original": "total=%.1f" % s, "revised": "total=%.1f" % pu["total"],
                             "reason": "planning_unit_cap=%d" % p["cap"], "human_confirm": True})
    elif pu.get("total") != s:
        pu["total"] = s
    wj(out / "planning_units.json", pu)


def boot(inp, out):
    out.mkdir(parents=True, exist_ok=True)
    c = load(inp, out)
    c["t0"] = time.time()
    c["sources"] = V.build_sources(inp) if V else []
    return c, plan(c), (V.fact_candidates(c["sources"]) if V else [])


def cmd_init(inp, out):
    c, p, facts = boot(inp, out)
    wj(out / "workorder.json", c["workorder"] or {"absent": True,
                                                 "defaults": {"planning_months": 12, "planning_unit_cap": 100}})
    handoff(out, c, p, facts)
    for name, text in (("planning_units.json", json.dumps(units(p), ensure_ascii=False, indent=2) + "\n"),
                       ("goal_matrix.md", T("matrix", "# 目标—工作包—里程碑—指标矩阵\n")),
                       ("risks.md", T("risks", "# 风险与备选方案\n")),
                       ("draft_boundary.md", T("boundary", "# 已完成 / 拟开展 边界表\n"))):
        wt(out / name, text, False)
    seeds = {"pending_human.json": ph_seed(c["workorder"]),
             "preserved_facts.json": {"note": "只保留用到的条目；quote 须逐字。", "items": facts[:25]},
             "evidence_map.json": {"note": "claim/section/kind/source_id/locator/quote", "items": []},
             "change_log.json": {"note": "original_quote->revised_quote+reason+locator", "items": []}}
    for k, v in seeds.items():
        if not (out / k).exists():
            wj(out / k, v)
    au = V.check_output(out, p)
    r = res(c, out, p, au, status="partial")
    r["stage"] = "init"
    r["limits"] = "仅骨架与证据抽取"
    wj(out / "result.json", r)
    print(json.dumps({"stage": "init", "case_id": c["case_id"], "output": str(out), "sources": len(c["sources"]),
                      "sections": [s["title"] for s in p["sections"]], "chars_range": [p["lo"], p["hi"]],
                      "next": "编辑 proposal.md 后 finalize"}, ensure_ascii=False, indent=2))
    return 0


def cmd_finalize(inp, out):
    c, p, facts = boot(inp, out)
    idx = V.build_quote_index(c["sources"])
    if not (out / "proposal.md").exists():
        sk = out / "proposal_skeleton.md"
        wt(out / "proposal.md", sk.read_text(encoding="utf-8") if sk.exists() else "# 降级保底稿，需人工补写\n")
        c["degradations"].append("proposal_absent_fallback_generated")
        c["errors"].append({"code": "proposal_absent", "message": "未找到 proposal.md，已生成降级保底稿"})
    fixunits(out, p, c)
    raw = rj(out / "evidence_map.json", None)
    em = raw if isinstance(raw, list) else (raw or {}).get("items") if isinstance(raw, dict) else []
    em, bad = [e for e in (em or []) if isinstance(e, dict)], 0
    for e in em:
        if not (e.get("quote") or "").strip():
            e["verified"], e["match"] = None, "no_quote_needed"
            continue
        h = V.find_quote(idx, e.get("quote") or "")
        e["verified"], e["match"] = h["match"] in ("normalized", "partial"), h["match"]
        if not e["verified"]:
            bad += 1
            e["locator"] = e.get("locator") or h.get("locator")
            e["note"] = "未定位，需核对原文"
    if raw is not None:
        wj(out / "evidence_map.json", em if isinstance(raw, list) else {"note": (raw or {}).get("note", ""), "items": em})
    if bad:
        c["degradations"].append("evidence_quotes_unverified:%d" % bad)
        ph = rj(out / "pending_human.json", []) or []
        ph = list((ph.get("items") if isinstance(ph, dict) else ph) or [])
        ph.append({"id": "PHQ", "topic": "引文未能定位", "need": "%d 条引文未定位" % bad,
                   "why": "PDF 无文本层或引文被改写", "status": "open", "blocking": False})
        wj(out / "pending_human.json", ph)
    au = V.check_output(out, p)
    st = "partial" if c["errors"] else au.get("status", "partial")
    r = res(c, out, p, au, status=st)
    r["stage"] = "final"
    wj(out / "result.json", r)
    print(json.dumps({"stage": "final", "case_id": c["case_id"], "status": st,
                      "char_count": au.get("metrics", {}).get("char_total"),
                      "planning_units_total": au.get("metrics", {}).get("planning_units_total"),
                      "issues": au.get("counts"), "result": str(out / "result.json")}, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="七要素基金申请书 Skill：init 建骨架；finalize 回检与契约回填。")
    ap.add_argument("command", nargs="?", default="init", choices=["init", "finalize", "all"],
                    help="init(默认) / finalize / all")
    ap.add_argument("--input", default="", help="输入目录，默认 /input")
    ap.add_argument("--output", default="", help="输出目录，默认 /app/output")
    ap.add_argument("--version", action="version", version="1.0.0")
    a = ap.parse_args(argv)
    inp = Path(a.input).expanduser().resolve() if a.input else Path("/input")
    out = d_out(a.output)
    try:
        if a.command == "finalize":
            return cmd_finalize(inp, out)
        if a.command == "all":
            cmd_init(inp, out)
            return cmd_finalize(inp, out)
        return cmd_init(inp, out)
    except Exception:
        tb = traceback.format_exc(limit=4)
        try:
            r = rj(out / "result.json", {}) or {}
            r.update(status="partial", degradations=sorted(set(list(r.get("degradations") or [])
                                                              + ["unhandled_exception"])),
                     errors=list(r.get("errors") or []) + [{"code": "unhandled_exception", "traceback": tb}])
            for k in ("case_id", "preserved_facts", "evidence_map", "change_log", "pending_human"):
                r.setdefault(k, [] if k != "case_id" else None)
            r.setdefault("deliverable", {"file": "proposal.md", "present": (out / "proposal.md").exists()})
            wj(out / "result.json", r)
        except Exception:
            pass
        print(json.dumps({"status": "partial", "error": tb.splitlines()[-1]}, ensure_ascii=False))
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
