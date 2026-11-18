#!/usr/bin/env python3
"""verify_claims.py - literature evidence verification (reading-07). Stdlib only.
Claims are QUESTIONS: split into sub-claims, locate minimal sufficient passages,
assign one of four support levels, write result.json + cards. Exit code always 0.
"""

import argparse, json, re, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lit_core as L  # noqa: E402

VERSION = "1.0.0"
FOUR = ("supported", "partially_supported", "contradicted", "insufficient_evidence")
START = time.time()
TYPE_OF = (("causal", "causal"), ("compar", "comparison"), ("scope", "scope"))
REQ = {"fact": "same finding stated explicitly", "comparison": "both entities, same metric, same direction",
       "causal": "causal link or intervention result", "scope": "sampled domain or condition"}
NOTES = {"levels": "四级定义见 references/verdict-rubric.md", "conflict": "相反证据并列，判定带保留",
         "gate": "覆盖度>=0.72 且无未对齐要素才 supported；<0.40 判 insufficient_evidence"}
AGG = ("contradicted 且无冲突→contradicted；有冲突→partially_supported；全 supported→supported；"
       "全 insufficient→insufficient_evidence；其余→partially_supported")
CONNECT = re.compile(r"(?:[，,]\s*)?(?:并且|而且|同时|此外|另外|以及|但是|然而|不过|但|且|"
                     r"and\s+also|,\s*(?:and|but|while|whereas|although)\s+)")


def build_sub(text, idx):
    t = L.norm_ws(text)
    ty = next((n for c, n in TYPE_OF if L.cue(c, t)), "fact")
    m = re.search(r"([A-Za-z0-9\u4e00-\u9fff%\.\-]{1,24})\s*(?:高于|低于|优于|劣于|大于|小于)\s*([A-Za-z0-9\u4e00-\u9fff%\.\-]{1,24})", t)
    comp = "%s vs %s" % (m.group(1), m.group(2)) if m else None
    if not comp:
        m = re.search(r"(?:compared (?:with|to)|than|versus|vs\.?|相比|比)\s*([A-Za-z0-9\u4e00-\u9fff%\.\- ]{1,30})", t, re.I)
        comp = m.group(1).strip(" ,，。.") if m else None
    m = re.search(r"(?:在[^，。；]{2,40}?条件下|当[^，。；]{2,30}?时|在[^，。；]{2,30}?范围内|"
                  r"under [^,.;]{3,50}? conditions?|for [^,.;]{3,40}? samples?|in [^,.;]{3,40}? (?:group|cohort|setting))", t, re.I)
    return {"sub_id": "S%d" % idx, "text": t, "type": ty, "required_evidence_type": REQ[ty], "comparator": comp,
            "negation": L.has_neg(t), "significance": bool(L.cue("sig", t)), "conditions": m.group(0) if m else None,
            "quantifier": ";".join(L.cue("scope", t)[:2]) or None, "numbers": L.numbers(t), "terms": L.terms(t)}


def decompose(text, cap=7):
    raw = L.norm_ws(text)
    pieces = []
    for ch in re.split(r"[；;。\n]+", raw):
        pieces += [p.strip(" ，,、") for p in CONNECT.split(ch.strip(" ，,、")) if len(p.strip(" ，,、")) >= 4]
    if len(pieces) <= 1:
        cl = [c.strip() for c in re.split(r"[，,]", raw) if len(c.strip()) >= 6]
        pieces = cl if (len(cl) == 2 and L.direction(cl[0]) != "none" and L.direction(cl[1]) != "none") else ([raw] if raw else [])
    seen, subs = set(), []
    for p in pieces:
        k = re.sub(r"\s+", "", p)[:60]
        if k not in seen:
            seen.add(k)
            subs.append(build_sub(p, len(subs) + 1))
    return (subs or [build_sub(raw or "(empty claim)", 1)])[:cap]


def judge_sub(sub, units, keep=6):
    cands, scanned, terms = [], 0, sub["terms"]
    anc = L.anchors(sub["text"])
    df = {a: sum(1 for u in units if a in u["text"].lower().replace(" ", "")) for a in set(anc)}
    for u in units:
        scanned += 1
        for win in L.windows(u):
            low = win["text"].lower()
            flat_low = low.replace(" ", "")
            hit = [t for t in terms if t.lower() in low]
            cov = len(hit) / float(len(terms)) if terms else 0.0
            if cov <= 0.05:
                continue
            ah = [a for a in anc if a in flat_low]
            if anc and not ah:
                cov *= 0.35                      # off-target: different condition or entity
            cands.append({"win": win, "cov": cov, "hit": hit, "ah": len(ah),
                          "asc": round(sum(1.0 / max(1, df.get(a, 1)) for a in ah), 3),
                          "num": [n for n in sub["numbers"] if n in flat_low]})
    cands.sort(key=lambda c: (c["asc"], c["ah"], round(c["cov"], 3), 1 if c["num"] else 0,
                              -len(c["win"]["text"])), reverse=True)
    top = cands[:keep]
    scope = {"units_scanned": scanned, "sentence_windows": sum(len(u["sentences"]) for u in units),
             "candidates_kept": len(top)}
    if not top:
        return {"verdict": "insufficient_evidence", "verdict_confidence": "high", "evidence": [], "alternative": None,
                "rationale": "无共享实质内容词，至多主题相关。", "limitations": [], "search_scope": scope,
                "counter_evidence_searched": True}
    best, bt = top[0], top[0]["win"]["text"]
    cd, ed = L.direction(sub["text"]), L.direction(bt)
    lim = []
    if sub["significance"] and not L.cue("sig", bt):
        lim.append("significance_not_reported: 原文未报告 P 值")
    if sub["numbers"] and not set(sub["numbers"]) & set(L.numbers(bt)):
        pool = L.numbers(bt)
        lim.append("reported_value_differs: 原文 %s / 论断 %s" % ("/".join(pool[:3]), "/".join(sub["numbers"][:3]))
                   if pool else "quantity_not_reported: 原文未给出数值")
    if sub["quantifier"] and not L.cue("scope", bt):
        lim.append("scope_not_established: 全称限定（%s）缺适用域" % sub["quantifier"])
    if sub["conditions"]:
        ct = L.terms(sub["conditions"], cap=8)
        if ct and not any(t.lower() in bt.lower() for t in ct):
            lim.append("condition_not_matched: 条件「%s」未出现" % sub["conditions"])
    u = best["win"]["unit"]
    if anc and best["ah"] < len(set(anc)):
        lim.append("anchor_not_matched: 论断数值/型号 %s 未全部出现" % "/".join(sorted(set(anc))[:3]))
    ev = {"source_id": u["source_id"], "unit_id": u["unit_id"], "locator": dict(u["locator"]),
          "label": L.unit_label(u), "quote": bt, "supports": True, "role": "minimal_sufficient",
          "coverage": round(best["cov"], 3)}

    def out(v, conf, why, evid=None, alt=None, extra=()):
        return {"verdict": v, "verdict_confidence": conf, "evidence": evid if evid is not None else [ev],
                "alternative": alt, "rationale": why, "limitations": lim + list(extra),
                "search_scope": scope, "counter_evidence_searched": True}

    contra = ("原文方向与论断相反（%s/%s）" % (cd, ed)
              if (cd in ("up", "down") and ed in ("up", "down") and cd != ed) else None)
    if not contra and L.has_neg(sub["text"]) != L.has_neg(bt) and best["cov"] >= 0.80:
        contra = "否定极性相反"
    if contra:
        ev.update({"supports": False, "role": "counter"})
        return out("contradicted", "medium", "%s；覆盖度 %.2f；证据句：%s" % (contra, best["cov"], bt[:180]))
    alt, ref = None, (ed if ed in ("up", "down") else cd)
    if ref in ("up", "down") or sub["type"] in ("comparison", "causal"):
        for c in top[1:]:
            u1, u2, d = c["win"]["unit"], best["win"]["unit"], L.direction(c["win"]["text"])
            if c["cov"] >= max(0.42, best["cov"] - 0.55) and ref in ("up", "down") and d in ("up", "down") \
                    and d != ref and all(a in c["win"]["text"].lower().replace(" ", "") for a in anc) \
                    and not (u1["source_id"] == u2["source_id"] and u1.get("section") == u2.get("section")):
                alt = c
                break
    if best["cov"] < L.PARTIAL_C:
        return out("insufficient_evidence", "medium", "最佳证据仅覆盖 %.0f%% 内容词（%s），属主题相关。"
                   % (best["cov"] * 100, "、".join(best["hit"][:6])))
    if alt is not None:
        a = alt["win"]
        eva = {"source_id": a["unit"]["source_id"], "unit_id": a["unit"]["unit_id"], "locator": dict(a["unit"]["locator"]),
               "label": L.unit_label(a["unit"]), "quote": a["text"], "supports": False, "role": "counter",
               "coverage": round(alt["cov"], 3)}
        return out("partially_supported", "low", "不同位置方向相反，判定保留：%s vs %s（%s/%s）"
                   % (ev["label"], ed, eva["label"], L.direction(a["text"])), alt=eva, extra=["conflicting_sources"])
    if best["cov"] >= L.SUPPORT_C and not lim:
        return out("supported", "high", "覆盖度 %.2f，方向/否定/数值/限定一致：%s" % (best["cov"], bt[:180]))
    if best["cov"] >= L.SUPPORT_C:
        return out("partially_supported", "medium", "覆盖主要内容词但要素未对齐：%s" % "；".join(lim)[:220])
    return out("partially_supported", "medium", "仅部分要素被支持（覆盖度 %.2f）：%s" % (best["cov"], bt[:180]))


def verify_claim(claim, units):
    subs = decompose(claim["claim_text"])
    for s in subs:
        if "verdict" not in s:
            s.update(judge_sub(s, units))
    v = L.aggregate(subs)
    return {"claim_id": claim["claim_id"], "claim_text": claim["claim_text"], "claim_kind": subs[0]["type"],
            "sub_claims": subs, "verdict": v,
            "verdict_confidence": "high" if all(s["verdict_confidence"] == "high" for s in subs)
            else ("low" if any(s["verdict_confidence"] == "low" for s in subs) else "medium"),
            "aggregation_rule": AGG, "evidence_path": "rule_engine",
            "conflict": L.conflict_of(subs), "limitations": list(dict.fromkeys(x for s in subs for x in s["limitations"])),
            "comparator": next((s["comparator"] for s in subs if s["comparator"]), None),
            "negation": any(s["negation"] for s in subs), "significance": any(s["significance"] for s in subs),
            "conditions": next((s["conditions"] for s in subs if s["conditions"]), None),
            "status": "verified" if v != "insufficient_evidence" else "insufficient_evidence"}


def write_report(out, res):
    o = ["# 证据核验 %s (%s)" % (res["case_id"], res["status"])]
    for v in res["result"].get("verifications", []):
        o.append("- %s %s → %s" % (v["claim_id"], v["claim_text"][:80], v["verdict"]))
        o += ["    - %s [%s] %s" % (s["sub_id"], s["type"], s["verdict"]) for s in v["sub_claims"]]
        o += ["      > %s" % e.get("quote") for s in v["sub_claims"] for e in s["evidence"]]
    (out / "verification_report.md").write_text("\n".join(o) + "\n", encoding="utf-8")


def shell(cid, st, contract=None):
    cov = dict({"claims_requested": 0, "claims_verified": 0, "split_subclaims": 0, "corpus_units": 0},
               **{k: 0 for k in FOUR})
    res = {"case_id": cid, "status": st,
           "result": {"task": "literature_evidence_verification", "verifications": [], "coverage": cov,
                      "aggregation_rule": AGG, "method_notes": NOTES, "artifacts": {}},
           "claims": [], "uncertainties": [], "sources": [], "pending_human": [], "errors": [],
           "degradations": [], "changes": [], "gaps": [],
           "runtime": {"version": VERSION, "python": sys.version.split()[0],
                       "elapsed_sec": 0.0}}
    res["uncertainty"] = res["uncertainties"]
    for k, spec in (contract or {}).items():
        if k not in res:
            lv = spec.lower() if isinstance(spec, str) else ""
            res[k] = [] if ("list" in lv or "array" in lv) else ({} if ("dict" in lv or "object" in lv) else None)
            res["degradations"].append({"issue": "contract_field_filled_empty", "field": k})
        elif k == "result" and isinstance(spec, dict):
            res["result"].update({kk: res["result"].get(kk) for kk in spec})
            res["degradations"] += [{"issue": "contract_subfield_filled_empty", "field": "result." + kk}
                                    for kk in spec if kk not in res["result"]]
    return res


def finalize(out, res):
    res["runtime"].update({"elapsed_sec": round(time.time() - START, 2), "finished": True})
    res["uncertainty"] = res["uncertainties"]
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


def load_case(inp):
    for p in [inp / "case.json"] + sorted(inp.glob("case*.json")):
        if p.exists():
            try:
                obj = json.loads(L.read_text_file(p) or "null")
                return (obj if isinstance(obj, dict) else {}), str(p)
            except Exception:
                return {"_parse_error": "case json is not valid JSON"}, str(p)
    return {}, None


def row(v):
    subs = v.get("sub_claims", [])
    evs = [(x["sub_id"], e) for x in subs for e in x.get("evidence", [])]
    first = evs[0][1] if evs else {}
    return {"claim_id": "V-" + str(v["claim_id"]), "input_claim_id": v["claim_id"],
            "kind": v.get("claim_kind") or "fact", "text": v["claim_text"], "verdict": v["verdict"],
            "evidence": [dict(sub_id=i, source_id=e.get("source_id"), quote=e.get("quote"),
                              location=e.get("locator"), supports=e.get("supports"), role=e.get("role")) for i, e in evs],
            "source_id": first.get("source_id"), "location": first.get("locator"),
            "conditions": next((x.get("conditions") for x in subs if x.get("conditions")), None),
            "readability": {"supported": "directly_read", "contradicted": "directly_read",
                            "partially_supported": "inferred"}.get(v["verdict"], "undetermined"),
            "sub_claim_verdicts": {x["sub_id"]: x["verdict"] for x in subs}}


def stub(c, lim, why, st):
    return {"claim_id": c["claim_id"], "claim_text": c["claim_text"], "sub_claims": [], "limitations": [lim],
            "verdict": "insufficient_evidence", "verdict_confidence": "low", "status": st, "rationale": why,
            "conflict": {"conflict": False, "both_sides": []}}


def run(args):
    inp = next((c.resolve() for c in ([Path(args.input)] if args.input else []) +
                [Path("/input"), Path("/app/input"), Path.cwd() / "input", HERE.parent / "input"] if c.exists()),
               Path(args.input or "/input"))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    res = shell("unknown", "partial")
    finalize(out, res)                                            # partial lands first
    try:
        case, cpath = load_case(inp)
        inner = case.get("input") if isinstance(case.get("input"), dict) else {}
        res = shell("%s" % (case.get("case_id") or case.get("id") or inner.get("case_id")
                            or Path(cpath or "unknown").stem), "partial", case.get("output_contract"))
        res["runtime"].update({"input_dir": str(inp), "case_file": cpath})
        if case.get("_parse_error"):
            res["errors"].append({"stage": "input", "issue": case["_parse_error"], "action": "continue"})
        finalize(out, res)

        claims, corigin, cgaps = L.load_claims(inp, case)
        units, sources, degr, gaps = L.load_corpus(inp, skip=[p for p in (corigin, cpath) if p])
        for u in units:
            u["sentences"] = L.split_sentences(u["text"])
        res["runtime"]["claims_file"] = corigin
        res["sources"], res["gaps"] = sources, cgaps + gaps
        res["degradations"] = res["degradations"] + degr
        res["result"]["corpus_units"] = len(units)
        if not units:
            res["pending_human"].append({"action": "提供可读原文", "reason": "input 下无可解析的原文段落"})
        if not claims:
            res["status"] = "input_error"
            res["errors"].append({"stage": "claims", "issue": "no claims_to_verify found",
                                  "detail": "looked for claims-to-verify.json and case.json claims keys"})
            res["pending_human"].append({"action": "补充待核验论断清单", "reason": "缺少 claims，无法核验"})
            finalize(out, res)
            return res

        vers, hit = [], False
        for claim in claims:
            if time.time() - START > max(30.0, float(args.max_seconds)):
                hit = True
                res["degradations"].append({"stage": "budget", "issue": "time_budget_reached",
                                            "detail": "remaining claims -> insufficient_evidence"})
                break
            try:
                vers.append(verify_claim(claim, units))
            except Exception as exc:
                res["errors"].append({"stage": "claim", "claim_id": claim["claim_id"], "issue": "verification_failed",
                                      "detail": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc(limit=2)})
                vers.append(stub(claim, "runtime_error", "核验异常，需人工复核", "error"))
        done = {v["claim_id"] for v in vers}
        vers += [stub(c, "not_processed_budget", "未及处理（时间预算），需重跑", "pending")
                 for c in claims if c["claim_id"] not in done]

        subs = [x for v in vers for x in v.get("sub_claims", [])]
        cov = dict({k: sum(1 for v in vers if v["verdict"] == k) for k in FOUR},
                   claims_requested=len(claims), claims_verified=len(vers), split_subclaims=len(subs),
                   corpus_units=len(units),
                   sub_claim_verdicts={k: sum(1 for x in subs if x["verdict"] == k) for k in FOUR})
        res["result"].update({"verifications": vers, "claims_requested": len(claims), "coverage": cov,
                              "artifacts": {"result_json": "result.json", "evidence_cards": "evidence_cards.jsonl",
                                            "report": "verification_report.md"}})
        res["claims"] = [row(v) for v in vers]
        for v in vers:
            for s in v.get("sub_claims", []):
                u = {"claim_id": v["claim_id"], "sub_id": s["sub_id"]}
                if s["verdict"] == "insufficient_evidence":
                    res["uncertainties"].append(dict(u, issue="原文未提供可判定证据（不足≠证伪）",
                                                     searched=s.get("search_scope", {}), action="人工复核或补充材料"))
                res["uncertainties"] += [dict(u, issue=x, action="核对条件差异" if x.startswith("conflicting") else "")
                                         for x in s.get("limitations", [])]
        (out / "evidence_cards.jsonl").write_text("\n".join(L.card_lines(vers)) + ("\n" if vers else ""), encoding="utf-8")
        res["status"] = ("input_error" if not vers else "partial" if (res["errors"] or hit) else
                         "insufficient_evidence" if all(v["verdict"] == "insufficient_evidence" for v in vers) else "ok")
        finalize(out, res)
        write_report(out, res)
        return res
    except Exception as exc:
        res["status"] = "partial" if res.get("errors") else "input_error"
        res["errors"].append({"stage": "run", "issue": "unhandled",
                              "detail": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc(limit=3)})
        finalize(out, res)
        return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Verify literature claims: decompose, locate verbatim evidence, assign supported/"
                    "partially_supported/contradicted/insufficient_evidence. Exit code 0.",
        epilog="python3 -B verify_claims.py --input /input --output /app/output")
    ap.add_argument("--input", default="/input", help="input dir (case.json, claims, materials)")
    ap.add_argument("--output", default="/app/output", help="output dir (result.json, cards, report)")
    ap.add_argument("--max-seconds", dest="max_seconds", type=float, default=780.0, help="budget")
    args = ap.parse_args(argv)
    try:
        res = run(args)
    except Exception as exc:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        res = shell("unknown", "input_error")
        res["errors"].append({"stage": "main", "issue": "fatal", "detail": str(exc)})
        finalize(out, res)
    c = res.get("result", {}).get("coverage", {})
    print("status=%s claims=%s subclaims=%s -> %s" % (res.get("status"), c.get("claims_requested"),
                                                      c.get("split_subclaims"), Path(args.output) / "result.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
