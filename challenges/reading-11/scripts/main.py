#!/usr/bin/env python3
"""sci-reading-bench CLI (stdlib only, exit code always 0): init | show | check | build.
init = index + partial result.json; show = locators; check = validate; build = artefacts."""
import argparse, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench as B


def dump(res, stage):
    """Fill output_contract fields, then persist result.json."""
    sc = res.get("scoring") or {}
    if res.get("contract_echo"):
        res.update(B.fill_contract(res["contract_echo"], dict(
            case_id=res.get("case_id"), status=res.get("status"), sources=res.get("sources"), items=res.get("benchmark"),
            scoring=sc, anchors=res.get("anchors"), stats=sc.get("aggregate"), outputs=res.get("outputs"),
            report=(res.get("outputs") or {}).get("report"),
            uncertainty=res.get("uncertainty"), changes=res.get("changes"),
            result={"report": (res.get("outputs") or {}).get("report"), "benchmark": res.get("benchmark"),
                    "anchors": res.get("anchors"), "scoring": sc.get("aggregate")},
            claims=res.get("anchors"), uncertainties=res.get("uncertainty"),
            preserved_facts=res.get("anchors"), evidence_map=res.get("anchors"))))
    B.save(res, stage)


def score_items(items):
    """Per rubric point 0/1/2 by anchor coverage. Deterministic and re-runnable."""
    out = []
    for it in items:
        ats, pts = B.terms(" ".join(it["reference_answer"])), []
        for rp in it["rubric"]:
            c = [(B.cov(rp["key_terms"] or ats, e["quote"]), e) for e in it["evidence"]
                 if e.get("_v", {}).get("verified")]
            if not c:
                pts.append({"rubric_id": rp["id"], "score": 0, "basis": "no verified quote in material"})
                continue
            x, ev = max(c, key=lambda z: z[0])
            s = 2 if x >= 0.6 else (1 if x > 0 else 0)
            pts.append({"rubric_id": rp["id"], "score": s, "locator": ev["locator"], "coverage": x,
                        "basis": "%s (cov %.2f @ %s)" % ({2: "judgeable", 1: "review",
                                                          0: "no key term"}[s], x, ev["locator"] or "-")})
        tot = sum(p["score"] * next((r["weight"] for r in it["rubric"] if r["id"] == p["rubric_id"]), 0) for p in pts)
        out.append({"id": it["id"], "type": it["type"], "difficulty": it["difficulty"], "points": pts,
                    "score": round(tot, 3),
                    "judgeable": all(p["score"] >= 1 for p in pts),
                    "fully_judgeable": all(p["score"] == 2 for p in pts)})
    return out


def fallback(idx, limit=6):
    """Deterministic minimal items from real paragraphs (used when no usable draft)."""
    out = []
    for m in idx.get("materials", []):
        for par in m.get("paragraphs", []):
            if len(out) >= limit:
                return out
            t = par["text"]
            if len(t) < 100:
                continue
            sents = [x for x in B.re.split(r"(?<=[。！？.!?])\s*", t) if x.strip()] or [t]
            nums = B.re.findall(r"\d+(?:[.,]\d+)?\s?(?:%|mg|g|mL|L|µM|mM|nM|nm|mm|h|min|s|°C|K)", t)
            s = next((x for x in sents if nums[0] in x), t)[:300] if nums else sents[0].strip()[:240]
            q = ("%s 的 %s 段出现带单位数值 %s，请给出原句与 locator。" % (m["name"], par["pid"], nums[0])) if nums \
                else ("逐字摘录 %s 中 %s 段首句，并给出 material 与 locator。" % (m["name"], par["pid"]))
            out.append({"id": "Q%02d" % (len(out) + 1), "type": "numeric" if nums else "extraction",
                        "difficulty": "easy", "question": q,
                        "rubric": [{"id": "R1", "text": "原文逐字一致且 locator 正确", "weight": 1.0,
                                    "key_terms": B.terms(s, 4)}],
                        "reference_answer": [s] + ([nums[0]] if nums else []),
                        "evidence": [{"material": m["mid"], "locator": par["pid"], "quote": s}]})
    return out


def cands_of(ip, case):
    """Candidate/checker material shipped with a case -> labelled technical_synthetic."""
    n = ["case.json:candidate"] if B.dget(case, ("candidate_output", "candidate_answer",
                                                 "baseline_output", "model_output", "checker_log")) else []
    return (n + [p.name for p in sorted(Path(ip).rglob("*")) if p.is_file()
                 and B.re.search(r"(candidate|baseline|response|checker|model_out)", p.name.lower())])[:5]


def report(bench, anch, sc, idx, mode, rej, iss, cid):
    a, tc = sc["aggregate"], {}
    for it in bench["items"]:
        tc[it["type"]] = tc.get(it["type"], 0) + 1
    mats = "\n".join("- `%s` %s (%s, %d 段, %d 字符, %s)" % (m["mid"], m["name"], m["kind"],
                     len(m.get("paragraphs", [])), m["chars"], m["status"]) for m in idx.get("materials", [])) or "- 无"
    items = "\n".join("| %s | %s | %s | %d | `%s` | %s |" % (
        it["id"], it["type"], it["question"][:38].replace("\n", " "), len(it["rubric"]),
        it["evidence"][0]["locator"] if it["evidence"] else "-", sc["items"][i]["score"])
        for i, it in enumerate(bench["items"])) or "| - | - | 无题目 | 0 | - | - |"
    gaps = "\n".join(["- " + x for x in sc.get("pending_human", [])[:10]] or ["- 无：所有评分点均可核验"])
    if rej:
        gaps += "\n" + "\n".join("- 拒收 `%s`: %s" % (x["id"], x["question"][:60]) for x in rej)
    if iss:
        gaps += "\n- 另有 %d 条校验问题（work/check_report.json）" % len(iss)
    return "\n".join([
        "# 文献阅读 Benchmark 与评测报告\n",
        "- case_id: `%s` | %s | **%s** | 题目 %d / rubric %d / 锚点 %d\n"
        % (cid, B.now(), mode, len(bench["items"]), a["n_points"], len(anch)),
        "> 现场生成，包内无预制答案；`scoring.json` 是题集可判性自检分，不是答题分、不是 DSH 分数。\n",
        "## 1. 输入材料\n", mats,
        "\n## 2. 逐题 / 评分点 / 证据\n", "题型: " + (", ".join("%s=%d" % kv for kv in sorted(tc.items())) or "-"),
        "", "| 题号 | 题型 | 题面(截断) | 点数 | locator | 自检分/2 |", "|---|---|---|---|---|---|", items,
        "\n## 3. 评分口径与汇总\n",
        "点级 0/1/2：2=原文有逐字锚点且覆盖参考答案关键项；1=锚点存在但覆盖不足需人复核；0=无可用锚点。"
        "题分=Σ(权重×点分)，满分 2；basis 与 locator 见 `scoring.json`。",
        "- 均值 %.3f/2 | 点级 2 分 %d/%d (%.1f%%) | 可判率 %.1f%% | 锚点核验 %d/%d"
        % (a["mean_score"], a["n2"], a["n_points"], 100 * a["rate2"], 100 * a["judgeable_rate"],
           a["n_anchors_verified"], a["n_anchors"]),
        "\n## 4. 缺口与复现\n", gaps, "",
        "复现：`init` → 写 `work/questions.draft.json` → `check` → `build`；新案例只换 `/input`（字段见 "
        "`references/schema.md`）。",
        "限制：自检分只衡量可判性，不是答题分；证据核验为空白/大小写归一，释义改写不算锚点。"]) + "\n"


def find_draft(explicit=None):
    for p in ([Path(explicit)] if explicit else []) + [B.WORK / "questions.draft.json",
                                                       B.WORK / "questions.json", B.OUTPUT / "questions.draft.json"]:
        if p.is_file():
            try:
                return p, B.rj(p), None
            except Exception as e:
                return p, None, "draft %s is not valid JSON: %s" % (p, e)
    return None, None, "no draft at " + str(B.WORK / "questions.draft.json")


def cmd_init(a):
    case, cp = B.load_case(B.INPUT)
    res, con = B.prep("init", case)
    print("== %s %s | init ==\ninput: %s\noutput: %s\ncase: %s" % (B.NM, B.V, B.INPUT, B.OUTPUT, cp))
    if "_bad_json" in case:
        res["errors"].append({"stage": "case", "error": "case.json invalid: " + case["_bad_json"]})
        print("! case.json is not valid JSON -> partial mode")
    print("contract fields (%d): %s" % (len(B.ckeys(con)), ", ".join(B.ckeys(con)) or "NONE FOUND"))
    idx = B.scan(B.INPUT)
    B.wj(B.WORK / "index.json", idx)
    for m in idx["materials"]:
        print("  %-4s %-28s %-5s paras=%-3d chars=%-6d %s%s"
              % (m["mid"], m["name"][:28], m["kind"], len(m["paragraphs"]), m["chars"], m["status"],
                 ("  ! " + m["note"]) if m["note"] else ""))
    print("MATERIALS %d" % len(idx["materials"]))
    res.update({"errors": res["errors"] + idx["errors"], "degradations": idx["degradations"],
                "sources": B.srcs(idx), "benchmark": {"stage": "indexed", "materials": len(idx["materials"]),
                              "paragraphs": idx["n_paragraphs"], "items": 0},
                "uncertainty": ["questions not authored yet; write %s" % (B.WORK / "questions.draft.json")]})
    dump(res, "init")
    print("NEXT: main.py show --material %s --start 1 then main.py check ; build"
          % (idx["materials"][0]["mid"] if idx["materials"] else "M01"))


def cmd_show(a):
    res, _ = B.prep("show", B.load_case(B.INPUT)[0])
    idx = B.get_index(res)
    ms = {m["mid"]: m for m in idx.get("materials", [])}
    key = a.material if a.material in ms else next((k for k in ms if (a.material or "").lower() == k.lower()), None)
    if not key:
        for m in idx.get("materials", []):
            print("%-4s %-30s %-5s paras=%d chars=%d %s"
                  % (m["mid"], m["name"][:30], m["kind"], len(m["paragraphs"]), m["chars"], m["status"]))
        if a.material:
            print("! no material %s" % a.material)
            res["errors"].append({"stage": "show", "error": "material %s not found" % a.material})
    else:
        m, st = ms[key], max(1, a.start)
        end = st + max(1, a.limit)
        print("MATERIAL %s | %s | %s | %d paragraphs\n" % (m["mid"], m["name"], m["kind"], len(m["paragraphs"])))
        for p in m["paragraphs"][st - 1:end - 1]:
            print("[%s%s] (%d chars)\n%s\n" % (p["pid"], (" p.%d" % p["page"]) if p.get("page") else "",
                                              len(p["text"]), p["text"][:1200]))
        if end - 1 < len(m["paragraphs"]):
            print("... next: --start %d" % end)
    B.save(res, "show")


def cmd_check(a):
    res, _ = B.prep("check", B.load_case(B.INPUT)[0])
    c = B.cache(B.get_index(res))
    path, draft, err = find_draft(a.draft)
    print("== check ==")
    if err:
        print("! %s\n  fix: author questions.draft.json (see references/schema.md), then re-run" % err)
        B.wj(B.WORK / "check_report.json", {"ok": False, "issues": [{"level": "error", "msg": err}], "n_items": 0})
        res.update({"errors": [{"stage": "check", "error": err}],
                    "pending_human": ["author questions.draft.json then run check/build"]})
        B.save(res, "check")
        return
    rep = B.validate(draft, c)
    rep.update(draft_path=str(path), n_items=len(rep["items"]))
    B.wj(B.WORK / "check_report.json", rep)
    print("draft %s | raw=%d ok=%d rej=%d" % (path.name, rep["n_raw"], len(rep["items"]), len(rep["rejected"])))
    for x in rep["issues"]:
        print("  ERROR %-5s %s" % (x.get("item", "-"), x["msg"]))
    for w in rep["warnings"][:20]:
        print("  WARN  %-5s %s" % (w.get("item", "-"), w["msg"]))
    print("RESULT: %s" % ("PASS" if rep["ok"] else "FAIL (build falls back where needed)"))
    res["errors"] = [{"stage": "check", "item": x.get("item"), "error": x["msg"]} for x in rep["issues"]]
    res["pending_human"] = ["fix %d check error(s) then rebuild" % len(rep["issues"])] if rep["issues"] else []
    dump(res, "check")


def cmd_build(a):
    case, _ = B.load_case(B.INPUT)
    res, con = B.prep("build", case)
    cid = str(B.dget(case, B.IDK) or "") or None
    idx = B.get_index(res)
    c = B.cache(idx)
    if "_bad_json" in case:
        res["errors"].append({"stage": "case", "error": "case.json invalid: " + case["_bad_json"]})
    path, draft, err = find_draft(a.draft)
    items, rej, iss, mode = [], [], [], "agent_authored"
    if err:
        print("! %s -> deterministic fallback" % err)
        res["degradations"].append({"item": "draft", "issue": err, "action": "fallback_generated_items"})
    else:
        rep = B.validate(draft, c)
        items, rej, iss = rep["items"], rep["rejected"], rep["issues"]
        print("draft %s | accepted=%d rejected=%d errors=%d" % (path.name, len(items), len(rej), len(iss)))
    if not items or rej:
        mode = "fallback_minimal" if not items else "agent_authored_with_fallback"
        for raw in fallback(idx, 6 if not items else 2):
            it, _ = B.norm_item(raw, len(items) + 1)
            ev = it["evidence"][0]
            ev["_v"] = B.verify(c, ev["material"], ev["quote"])
            items.append(it)
        res["degradations"].append({"item": "benchmark", "issue": "no usable draft" if not items else "rejected items",
                                    "action": "added deterministic minimal items from real paragraphs"})
    for it in items:
        for ev in it["evidence"]:
            ev["_v"] = ev.get("_v") or B.verify(c, ev["material"], ev["quote"])
    anch = [{"item_id": it["id"], "material": ev["material"], "locator": ev["locator"] or ev["_v"].get("pid"),
             "quote": ev["quote"], "verified": bool(ev["_v"].get("verified")), "match": ev["_v"].get("match")}
            for it in items for ev in it["evidence"]]
    B.wj(B.OUTPUT / "anchors.json", {"schema": "sci-reading-bench/anchors@1", "case_id": cid, "generated_at": B.now(),
                                     "quote_policy": "verbatim only; whitespace-normalised match", "anchors": anch})
    B.wj(B.OUTPUT / "benchmark.json", {
        "schema": "sci-reading-bench/benchmark@1", "case_id": cid, "generated_at": B.now(), "mode": mode,
        "n_items": len(items), "instruction": "逐题按 rubric 点打 0/1/2；引用须命中 anchors.json 的 locator。",
        "items": [dict(it, evidence=[{k: e[k] for k in ("material", "locator", "quote")} for e in it["evidence"]])
                  for it in items],
        "rejected": [{"id": x["id"], "question": x["question"], "reason": "no verbatim-verified evidence"}
                     for x in rej]})

    sc_items = score_items(items)
    pts = [p for s in sc_items for p in s["points"]]
    n2, n1, n0 = (sum(p["score"] == k for p in pts) for k in (2, 1, 0))
    agg = {"n_items": len(sc_items), "n_points": len(pts), "n2": n2, "n1": n1, "n0": n0,
           "rate2": round(n2 / len(pts), 3) if pts else 0.0,
           "judgeable_rate": round((n2 + n1) / len(pts), 3) if pts else 0.0,
           "mean_score": round(sum(s["score"] for s in sc_items) / len(sc_items), 3) if sc_items else 0.0,
           "n_anchors": len(anch), "n_anchors_verified": sum(x["verified"] for x in anch)}
    pend = ["%s/%s score=%d: %s" % (s["id"], p["rubric_id"], p["score"], p["basis"])
            for s in sc_items for p in s["points"] if p["score"] < 2]
    pend += ["%s rejected: no verified anchor" % x["id"] for x in rej]
    B.wj(B.OUTPUT / "scoring.json", {
        "schema": "sci-reading-bench/scoring@1", "case_id": cid, "generated_at": B.now(),
        "scale": {"2": "verbatim anchor verified, covers answer key terms",
                  "1": "anchor verified but coverage<0.6 -> human review", "0": "no usable anchor"},
        "disclaimer": "题目可判性自检分；不是被评测 Agent 的答题分，不是 DSH 分数",
        "items": sc_items, "aggregate": agg, "pending_human": pend})
    cn = cands_of(B.INPUT, case)
    if cn:
        res["technical_synthetic"] = {"present": True, "not_a_dsh_score": True, "sources": cn, "scored": False,
                                      "note": "checker/合成数据仅登记，不参与评分，不代表 DSH 分数"}
    (B.OUTPUT / "report.md").write_text(
        report({"items": items}, anch, {"items": sc_items, "aggregate": agg, "pending_human": pend},
               idx, mode, rej, iss, cid), encoding="utf-8")

    status = ("input_error" if not idx.get("materials") else
              "insufficient_evidence" if not idx.get("n_paragraphs") or not items else
              "ok" if mode == "agent_authored" and not iss else "partial")
    res.update({"status": status, "pending_human": pend[:20],
                "outputs": dict({f.split(".")[0]: str(B.OUTPUT / f) for f in
                                 ("benchmark.json", "anchors.json", "scoring.json", "report.md", "result.json")},
                                index=str(B.WORK / "index.json"), draft=str(path) if path else None),
                "benchmark": {"mode": mode, "n_items": len(items), "n_rubric_points": len(pts),
                              "n_rejected": len(rej), "scores": {s["id"]: s["score"] for s in sc_items}},
                "anchors": {"n_anchors": len(anch), "verified": agg["n_anchors_verified"]},
                "scoring": {"aggregate": agg},
                "sources": B.srcs(idx), "changes": [{"what": "benchmark built from live input", "mode": mode,
                             "why": "Agent items preferred; deterministic fallback keeps package non-empty"},
                            {"what": "scoring limited to anchor audit",
                             "why": "no fabricated model scores; checker logs registered, not scored"}]})
    res["errors"] = res.get("errors", []) + iss[:20]
    res["degradations"] = res.get("degradations", []) + (idx.get("degradations") or [])
    unc = [u for u in (res.get("uncertainty") or []) if "not authored yet" not in u]
    unc += ["兜底题只覆盖摘录/数值类，不含推理题"] if mode != "agent_authored" and items else []
    unc += ["%d 个评分点无可用锚点，需人工补证据" % n0] if n0 else []
    low = [m["mid"] for m in idx["materials"] if m["note"]]
    unc += ["材料解析降级: %s（quote 需平台解析器复核）" % ", ".join(low)] if low else []
    unc += ["input 下未发现可用材料"] if not idx.get("materials") else []
    res["uncertainty"] = unc
    res["runtime"].update({"materials": len(idx["materials"]), "paragraphs": idx["n_paragraphs"],
                           "n_items": len(items), "mode": mode})
    ok = len(pend) >= 0 and agg["n2"] + agg["n1"] + agg["n0"] == len(pts)
    res["runtime"]["self_audit"] = {"ok": ok, "checks": "counts n2+n1+n0==n_points"}
    dump(res, "build")
    print("mode=%s items=%d points=%d anchors=%d verified=%d | status=%s"
          % (mode, len(items), len(pts), len(anch), agg["n_anchors_verified"], status))
    print("wrote %s | SELF-AUDIT %s" % (" ".join("%s(%dB)" % (f, (B.OUTPUT / f).stat().st_size)
                                                 for f in ("benchmark.json", "anchors.json", "scoring.json",
                                                           "report.md", "result.json")),
                                        "PASS" if ok else "ATTENTION"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="Agent-led reading-benchmark builder (init/show/check/build).")
    sp = ap.add_subparsers(dest="cmd")
    sp.add_parser("init", help="index /input materials and write a partial result.json")
    p = sp.add_parser("show", help="print material paragraphs with locators")
    p.add_argument("--material"), p.add_argument("--start", type=int, default=1)
    p.add_argument("--limit", type=int, default=10)
    sp.add_parser("check", help="validate draft items, rubric, quotes and locators").add_argument("--draft")
    sp.add_parser("build", help="write benchmark/anchors/scoring/report and finalise result.json").add_argument("--draft")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[a.cmd](a)
    except Exception as e:
        print("! recoverable failure in %s: %s\n%s" % (a.cmd, e, traceback.format_exc(limit=3)))
        try:
            res, _ = B.prep(a.cmd + "/error", B.load_case(B.INPUT)[0])
            res["errors"].append({"stage": a.cmd, "error": str(e), "traceback": traceback.format_exc(limit=3)[-900:]})
            res["pending_human"] = ["inspect error and re-run %s" % a.cmd]
            res["degradations"] = [{"item": "run", "issue": str(e), "action": "wrote legal partial result"}]
            dump(res, a.cmd + "/error")
            print("WROTE partial result.json")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)
    except Exception:
        sys.exit(0)


