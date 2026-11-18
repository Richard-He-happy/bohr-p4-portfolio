import csv, json, sys
from pathlib import Path
import appraise as A
V = A.V
def dprob(c, tp, ida, ts, tf, ev):
    g = lambda k: A.fo(c, k)
    ob = g(["research_object", "object", "研究对象", "subject"]) or tf["object"] or "⟨研究对象待补⟩"
    va = g(["variables", "variable", "变量"]) or " ".join(ts[:3]) or "⟨关键变量待补⟩"
    ba = g(["baseline", "comparator", "control", "基线", "对照"]) or "⟨比较基线待补⟩"
    ep = g(["expected", "expectation", "预期", "hypothesis"]) or "⟨预期结论待补⟩"
    out = tf["outcome"] or "主要结局"
    fa = g(["falsif", "可证伪", "refut"]) or "若 %s 与 %s 在 %s 上无方向一致差异，则原设想被否证（需确认）" % (va, ba, out)
    el = [{"element": n, "value": None if "待补" in v else v,
           "source": "not_in_materials" if "待补" in v else ("derived_from_terms" if not A.fo(c, k) else "case_fields")}
          for n, v, k in (("object", ob, ["research_object", "object", "研究对象", "subject"]),
                          ("variables", va, ["variables", "variable", "变量"]),
                          ("baseline", ba, ["baseline", "comparator", "control", "基线", "对照"]),
                          ("expected", ep, ["expected", "expectation", "预期", "hypothesis"]),
                          ("falsifiable", fa, ["falsif", "可证伪", "refut"]))]
    st = "研究对象为 %s；关键变量为 %s；结局指标为 %s；对照为 %s；预期 %s；否证条件：%s（术语自动拼装，需作者改写为规范假设）" % (
        ob, va, out, ba, ep, fa)
    tree = [{"id": i, "weight": w, "question": q, "status": "ok" if (v is True or (isinstance(v, str) and "待补" not in v))
             else ("gap" if isinstance(v, str) else "partial")}
            for i, w, q, v in (("Q1", .25, "研究对象与边界可界定", ob), ("Q2", .25, "关键变量与结局可测量", va),
                               ("Q3", .20, "比较基线明确", ba), ("Q4", .15, "预期结论可否证", fa),
                               ("Q5", .15, "证据覆盖问题维度", len(ev) >= 5))]
    e = [x["evidence_id"] for x in ev[:2]]
    return {"statement": st, "elements": el, "decomposition_gaps": [x["element"] for x in el if not x["value"]],
            "weighted_tree": tree, "testable_statement": None if "待补" in st else st,
            "evidence_ids": e, "strength": "inferred" if e else "insufficient"}
def dcomp(ds, ev):
    rows = []
    for d in ds:
        r = {"source_id": d["sid"], "path": d["path"], "year": d["yr"], "doi": d["doi"],
             "included": "yes" if d["inc"] else "no", "inclusion_reason": d["why"]}
        seen = []
        for fn, cues in A.FLD:
            ss = [x for l, b in d["bl"] for x in A.sents(b) if len(x) >= 12 and x not in seen
                  and any(c in x.lower() for c in cues)]
            r[fn] = ss[0][:260] if ss else "材料未提供"
            seen += ss[:1]
        mt = [x for x in ("auc", "accuracy", "f1", "敏感性", "特异性", "p<", "95% ci", "rmse") if x in r["evaluation"].lower()]
        r["comparability_note"] = "指标:" + ("、".join(mt) if mt else "无")
        rows.append(r)
    return {"items": rows, "n": len(rows),
            "comparable_dims": [f for f, _ in A.FLD if sum(1 for r in rows if r[f] != "材料未提供") >= max(1, len(rows) // 2)],
            "evidence_ids": [e["evidence_id"] for e in ev[:3]]}
def dnov(c, ida, ds):
    raw = A.fo(c, ["innovation", "novelty", "创新点", "contribution", "增量"])
    cl = [A.nm(x) for x in A.re.split(r"[；;\n]|(?<=。)", raw) if len(A.nm(x)) >= 8] if raw else []
    if not cl and ida:
        cl = [A.nm(s) for s in A.re.split(r"[。；;]\s*", ida) if len(A.nm(s)) >= 10 and any(k in s.lower() for k in A.CC)]
    it = []
    for i, c0 in enumerate((cl or ["材料未提供显式创新陈述：需作者补写，无法判定覆盖"])[:6]):
        ct = set(A.tk(c0, 60))
        b_, bs = None, 0.0
        for d in ds:
            if d["inc"] and ct:
                w = sum(1.0 for t in ct if t in d["ts"]) / len(ct)
                if w > bs:
                    bs, b_ = w, d
        cov = "covered" if bs >= A.NH else ("partially_covered" if bs >= A.NL else
                                            ("not_covered_in_materials" if b_ else "undetermined"))
        bq = A.best(b_, list(ct)[:8]) if b_ else None
        it.append({"id": "N%d" % (i + 1), "claim": c0[:400],
                   "kind": next((k for k, cs in A.IK.items() if any(x in c0.lower() for x in cs)), "undetermined"),
                   "overlap_score": round(bs, 3), "coverage": cov, "closest_source": b_["sid"] if b_ else None,
                   "closest_locator": bq[0] if bq else None, "closest_quote": bq[1][:600] if bq else None,
                   "boundary": ("须在方法/数据/场景上与 %s 区分 %.2f" % (b_["sid"], bs)) if b_ else "材料不足以划界",
                   })
    cv = sum(1 for x in it if x["coverage"] == "covered")
    return {"items": it, "n": len(it), "covered_count": cv,
            "verdict": "创新空间受限：存在高度重叠" if cv else "材料内未见覆盖（非全球新颖）",
            "scope_note": "novelty relative to provided materials only"}
def dfea(ds, ev):
    ps = []
    for pid, lb, cues in A.PR:
        hit = None
        for d in ds:
            if not d["inc"]:
                continue
            for l, b in d["bl"]:
                for s in A.sents(b):
                    lo = s.lower()
                    if any(x in lo for x in cues):
                        a = any(x in lo for x in A.AC)
                        if hit is None or a:
                            hit = (d["sid"], l, s, a)
                        if a:
                            break
                if hit and hit[3]:
                    break
            if hit and hit[3]:
                break
        stt = "material_supported" if (hit and hit[3]) else ("mentioned_not_confirmed" if hit else "assumed_not_documented")
        ps.append({"premise": pid, "label": lb, "status": stt, "source_id": hit[0] if hit else None,
                   "locator": hit[1] if hit else None, "quote": hit[2][:600] if hit else None,
                   "action": "保留依据" if stt == "material_supported" else "补说明"})
    sup = sum(1 for p in ps if p["status"] == "material_supported")
    blk = [p["premise"] for p in ps if p["status"] != "material_supported"]
    return {"premises": ps, "supported": sup,
            "verdict": ("feasible_with_conditions" if sup >= 4 else
                        ("conditionally_feasible_pending_premises" if sup >= 2 else "insufficient_information")),
            "blocking_premises": blk,
            "failure_risks": [{"risk": "缺依据:%s" % p, "severity": "high"} for p in blk],
            "evidence_ids": [e["evidence_id"] for e in ev[:2]], "strength": "inferred" if sup >= 2 else "insufficient"}
def dcon(ev, ts):
    o, seen = [], set()
    for k in ts:
        g = [e for e in ev if k in e["quote"].lower()]
        st = {e["stance"] for e in g}
        if "supports" in st and "contradicts" in st:
            a = [e for e in g if e["stance"] == "supports"][0]
            b = [e for e in g if e["stance"] == "contradicts"][0]
            if (a["evidence_id"], b["evidence_id"]) in seen:
                continue
            seen.add((a["evidence_id"], b["evidence_id"]))
            mm = ("指标" in a["quote"] + b["quote"]) or ("不同" in a["quote"] + b["quote"])
            f = lambda x: {"evidence_id": x["evidence_id"], "source_id": x["source_id"], "locator": x["locator"],
                           "quote": x["quote"][:400]}
            o.append({"topic_term": k, "support": f(a), "against": f(b),
                      "resolution": "口径不同" if mm else "方向相反，无法裁定", "needs_human": not mm})
    return o[:8]


def dproto(c, ts, tf, ds):
    ys = [d["yr"] for d in ds if d["yr"]]
    tw = A.fo(c, ["time_window", "year_range", "时间窗", "period"]) or ("%s-%s" % (min(ys), max(ys)) if ys else "")
    q = lambda k: " OR ".join('"%s"' % x for x in tf[k].split()[:4])
    base = "(%s) AND (%s) AND (%s)" % (q("object") or "*", q("method") or "*", q("outcome") or "*")
    return {"executed": False, "execution_note": "离线：协议为待执行计划；覆盖证据只来自 /input 材料",
            "time_window": tw or None, "terms": ts[:18], "facets": tf,
            "queries": [{"db": d, "query": s, "executed": False} for d, s in
                        (("Web of Science", "TS=%s AND PY=%s" % (base, tw or "any")), ("PubMed", base),
                         ("CNKI", base.replace(" AND ", " * ")))],
            "screening_rules": {"include": ["主题与对象匹配", "时间窗内（元数据可得时）", "有方法与结果文本"],
                                "exclude": ["勘误/广告/无方法", "时间窗外", "重复条目"]},
            "reproduce": {"terms_sha256": A.hs(" ".join(ts)), "version": V}}
def dcov(ds, ts, ev):
    hit = [x for x in ts[:15] if any(x in d["tx"].lower() for d in ds)]
    return {"docs_total": len(ds), "docs_with_evidence": len({e["source_id"] for e in ev}),
            "recall_proxy_local": round(len(hit) / max(min(len(ts), 15), 1), 3)}


def dgap(ds, P, ts):
    o = [{"type": "材料规模", "description": "仅 %d 个来源，不足以支撑领域判断" % len(ds), "basis": "rows"}] if len(ds) < 3 else []
    ex = [d for d in ds if not d["inc"]]
    if ex:
        o.append({"type": "时间窗", "description": "%d 篇因年份越界排除" % len(ex), "basis": ex[0]["why"]})
    nod = [d["sid"] for d in ds if d["inc"] and not d["doi"]]
    if nod:
        o.append({"type": "元数据", "description": "%d 篇无 DOI" % len(nod), "basis": "、".join(nod[:5])})
    if P["problem_definition"]["decomposition_gaps"]:
        o.append({"type": "问题定义", "description": "未定义要素：%s" % "、".join(P["problem_definition"]["decomposition_gaps"]),
                  "basis": "elements"})
    miss = [f for f, _ in A.FLD if f not in P["prior_work_comparison"]["comparable_dims"]]
    if miss:
        o.append({"type": "比较维度", "description": "缺%s字段" % "、".join(miss), "basis": "comparison_matrix.csv"})
    u = [i for i in P["novelty_assessment"]["items"] if i["coverage"] == "undetermined"]
    if u:
        o.append({"type": "新颖性", "description": "%d 条陈述无最近工作" % len(u), "basis": "items"})
    if P["feasibility"]["blocking_premises"]:
        o.append({"type": "可行性前提", "description": "缺依据前提：%s" % "、".join(P["feasibility"]["blocking_premises"]),
                  "basis": "premises"})
    z = [x for x in ts[:10] if not any(x in d["tx"].lower() for d in ds if d["inc"])]
    if z:
        o.append({"type": "检索覆盖", "description": "零命中:%s" % "、".join(z[:6]), "basis": "coverage_metrics"})
    return o


def dclaim(P, ev):
    pd_, cm, f = P["problem_definition"], P["prior_work_comparison"], P["feasibility"]
    out = [{"id": "C1", "kind": "inference", "text": "问题表述：" + pd_["statement"][:200],
            "evidence_ids": pd_["evidence_ids"], "strength": "inferred"},
           {"id": "C2", "kind": "material_fact", "text": "可比工作 %d 项，维度 %s" % (cm["n"], "、".join(cm["comparable_dims"]) or "无"),
            "evidence_ids": cm["evidence_ids"], "strength": "directly_supported" if cm["evidence_ids"] else "insufficient"}]
    nv = P["novelty_assessment"]
    for i in nv["items"][:3]:
        m = [e["evidence_id"] for e in ev if e["source_id"] == i["closest_source"] and e["locator"] == i["closest_locator"]]
        out.append({"id": "C-" + i["id"], "kind": "judgement", "text": "创新陈述 %s → %s" % (i["id"], i["coverage"]),
                    "evidence_ids": m[:1], "strength": "inferred" if m else "insufficient"})
    out.append({"id": "C3", "kind": "judgement", "text": "可行性：%s（支持 %d/%d 前提）" % (f["verdict"], f["supported"], len(f["premises"])),
                "evidence_ids": f["evidence_ids"], "strength": f["strength"]})
    return out
def dunc(R, ds, ev):
    o = [{"type": "scope", "detail": "仅 %d 个本地来源，未外部检索" % len(ds)}]
    if any(d["q"] < 0.6 for d in ds):
        o.append({"type": "extraction", "detail": "PDF 文本层质量低"})
    m = [d["sid"] for d in ds if not d["yr"] or not d["doi"]]
    if m:
        o.append({"type": "metadata", "detail": "缺年份/DOI 来源数 %d" % len(m)})
    if len(ev) < 8:
        o.append({"type": "thin_evidence", "detail": "证据仅 %d 条" % len(ev)})
    return o


def decide(P):
    nv, fe = P["novelty_assessment"], P["feasibility"]
    if fe["verdict"] == "insufficient_information":
        return "暂缓立项：可行性前提证据不足"
    return ("有条件推进：需在方法/数据/场景上与最近工作区分" if nv["covered_count"] else
            "可推进：材料内未见完全覆盖且主要前提有依据（受材料范围限制）")
def md(rows):
    return "\n".join(["| " + " | ".join(str(x) for x in rows[0]) + " |", "|" + "---|" * len(rows[0])] +
                     ["| " + " | ".join(str(x) for x in r) + " |" for r in rows[1:]])
def tables(out, R):
    with (out / "evidence_map.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        k = ("evidence_id", "source_id", "locator", "quote", "stance", "strength")
        w.writerow(k)
        for e in R["evidence"]:
            w.writerow([e.get(x) or "" for x in k])
    k = ("source_id", "path", "year", "doi", "task", "method", "data", "evaluation", "conclusion", "included",
         "inclusion_reason", "comparability_note")
    with (out / "comparison_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(k)
        for r in R.get("comparison_matrix") or []:
            w.writerow([r.get(x) or "" for x in k])


TPL = Path(__file__).resolve().parent.parent / "references" / "report_template.md"


def render(R):
    P = R["research_product"]
    d, cm, n, f = P["problem_definition"], P["prior_work_comparison"], P["novelty_assessment"], P["feasibility"]
    md5 = lambda h, rows: md([h] + rows)
    q = "\n".join("- 待执行 `%s`：`%s`" % (x["db"], x["query"][:140]) for x in R["search_protocol"].get("queries", [])[:2])
    el = md5(["要素", "取值", "来源"], [[e["element"], (e["value"] or "⟨未给出⟩")[:110], e["source"]] for e in d["elements"]])
    tree = md5(["#", "权重", "子问题", "状态"], [[x["id"], "%.2f" % x["weight"], x["question"], x["status"]] for x in d["weighted_tree"]])
    cmp_ = md5(["来源", "年", "任务", "方法", "可比性"],
               [["%s %s" % (r["source_id"], Path(r["path"]).name[:20]), r["year"] or "—", r["task"][:55], r["method"][:55],
                 r["comparability_note"][:48]] for r in cm["items"]])
    nov = md5(["#", "陈述", "类型", "重叠", "判定", "最近来源"],
              [[i["id"], i["claim"][:70], i["kind"], "%.2f" % i["overlap_score"], i["coverage"],
                "%s %s" % (i["closest_source"] or "—", i["closest_locator"] or "")] for i in n["items"]])
    nq = "\n".join("> %s —— %s %s\n> 边界：%s\n" % (i["closest_quote"][:280], i["closest_source"], i["closest_locator"],
                                                 i["boundary"]) for i in n["items"] if i["closest_quote"])
    fea = md5(["前提", "状态", "依据", "动作"],
              [[p["label"], p["status"], "%s %s" % (p["source_id"] or "—", p["locator"] or ""), p["action"]] for p in f["premises"]])
    cf = "\n".join("%d. [%s] 支持 `%s` %s「%s」／反对 `%s` %s「%s」→ %s" % (
        i, x["topic_term"], x["support"]["evidence_id"], x["support"]["locator"], x["support"]["quote"][:100],
        x["against"]["evidence_id"], x["against"]["locator"], x["against"]["quote"][:100], x["resolution"])
        for i, x in enumerate(R["conflicts"], 1)) or "未检出极性相反的结论对；不等于不存在冲突，仅表示所给文本未出现。"
    gp = "\n".join("- **%s**：%s（%s）" % (g["type"], g["description"], g["basis"]) for g in R["gaps"]) or \
        "- 未检出结构性空白；但材料规模不足以支持“无空白”的判断。"
    cl = "\n".join("- **[%s]** %s（证据 %s；%s）" % (c["id"], c["text"], ", ".join(c["evidence_ids"]) or "无", c["strength"])
                   for c in R["claims"])
    uc = "\n".join("- %s：%s" % (u["type"], u["detail"]) for u in R["uncertainty"]["items"])
    pn = "\n".join("- 待人工：%s" % p for p in R["pending_human"])
    v = {"case_id": R["case_id"], "status": R["status"], "version": V, "n_src": len(R["sources"]),
         "n_inc": R["evidence_matrix"]["included"], "n_ev": len(R["evidence"]), "n_conf": len(R["conflicts"]),
         "n_gap": len(R["gaps"]), "secs": R["runtime"].get("seconds"), "executed": R["search_protocol"].get("executed"),
         "tw": R["search_protocol"].get("time_window") or "未提供",
         "queries": q, "statement": d["statement"], "elements": el, "tree": tree,
         "gaps_line": ("\n待补要素：%s（需作者确认，未代填）。" % "、".join(d["decomposition_gaps"])) if d["decomposition_gaps"] else "",
         "dims": "、".join(cm["comparable_dims"]) or "无", "cmp_table": cmp_,
         "inclusion": "；".join("%s %s" % (s["source_id"], s["inclusion_reason"][:30]) for s in R["sources"][:5]),
         "nov_verdict": n["verdict"], "nov_table": nov, "nov_quotes": nq, "fea_verdict": f["verdict"],
         "fea_sup": f["supported"], "fea_total": len(f["premises"]), "fea_strength": f["strength"], "fea_table": fea,
         "risks": "；".join("%s(%s)" % (r["risk"], r["severity"]) for r in f["failure_risks"]),
         "conflicts": cf, "gaps": gp, "claims": cl, "decision": R["review_summary"].get("decision", "-"),
         "unc": uc, "pending": pn}
    try:
        return TPL.read_text(encoding="utf-8").format(**v)
    except Exception:
        return "# 报告(模板缺失) %s｜%s｜证据 %d｜冲突 %d\n" % (R["case_id"], R["status"], len(R["evidence"]),
                                                              len(R["conflicts"]))


def check(out, inp):
    try:
        R = json.loads((out / "result.json").read_text(encoding="utf-8"))
    except Exception as e:
        return {"checks": {"result_json_loadable": False, "error": str(e)[:90]}, "misses": [], "pass": False}
    ct, ev = R.get("output_contract") or {}, R.get("evidence") or []
    ids = {e["evidence_id"] for e in ev}
    bad = [c["id"] for c in R.get("claims") or [] if not set(c.get("evidence_ids") or []) <= ids]
    tx = {}
    for s in R.get("sources") or []:
        p = (inp / s["path"]) if inp else None
        if p and p.exists():
            try:
                r0 = A.recs_of(p)[0]
                tx[s["source_id"]] = A.nm(" ".join(x for bl in (r0 if isinstance(r0[0], list) else [r0]) for _, x in bl))
            except Exception as e:
                tx[s["source_id"]] = ""
    ok = [e for e in ev if A.nm(e.get("quote")) and A.nm(e["quote"]) in tx.get(e["source_id"], "")]
    miss = [{"evidence_id": e["evidence_id"], "source_id": e["source_id"], "locator": e["locator"]} for e in ev if e not in ok]
    try:
        rows = len(list(csv.DictReader((out / "evidence_map.csv").open(encoding="utf-8"))))
    except Exception:
        rows = -1
    c = {"contract_missing": [k for k in ct if k not in R], "claims_unlinked": bad,
         "quote_hit": "%d/%d" % (len(ok), len(ev)), "csv_rows": rows}
    return {"checks": c, "misses": miss,
            "pass": bool(not c["contract_missing"] and not bad and not miss and rows == len(ev))}


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    g = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if not a or "-h" in a or "--help" in a or "--check" not in a:
        print("assess.py --check --output DIR [--input DIR]  复核结果输出为 JSON")
        return 0
    o, i = g("--output") or g("--out-dir") or ".", g("--input") or g("--in-dir")
    print(json.dumps(check(Path(o).resolve(), Path(i).resolve() if i else None), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print("unhandled:%s" % e, file=sys.stderr)
        sys.exit(0)
