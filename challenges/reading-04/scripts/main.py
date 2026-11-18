#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py - literature-qa (reading-03): answer supplied paper questions with verbatim evidence.

  python3 -B scripts/main.py --input /input --out /app/output
  python3 -B scripts/main.py --out /app/output --apply answers_patch.json
  python3 -B scripts/main.py --out /app/output --verify

A partial result.json is written before any parsing, then finalised together with
answers.json / evidence_map.csv / paragraph_index.json / verify_report.json.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core  # noqa: E402
from core import S  # noqa: E402
VERSION = "2.0.0"
T0 = time.time()
STOP = set("""a an the of and or in on for to with by from at as is are was were be been this that these
those we our it its their there than then such using used use can may might could should would will not
no also both each more most less between among during after before under over into within via vs which
what how why when where who do have has had if while about""".split())
SEC_PREF = {"NUM": ("result", "finding", "abstract", "table", "perform", "characteri"),
            "MECH": ("method", "experimental", "procedure", "synthesis", "material", "model", "architect"),
            "INT": ("method", "result", "abstract", "discussion"),
            "BND": ("discussion", "conclusion", "limitation", "outlook", "abstract"), "GEN": ()}
BN = ("未报告", "没有报告", "是否报告", "是否给出", "未给出", "没有给出", "未提供", "局限", "不足", "未涉及",
      "未说明", "没有说明", "未提及", "未开展", "没有测试", "未测试", "哪些信息", "缺少", "未披露")
MH = ("方法", "如何", "机制", "机理", "为什么", "为何", "原理", "作用", "贡献", "创新", "相比", "对比",
      "比较", "优于", "提升", "提高", "改进", "步骤", "流程", "策略", "设计")
NM = re.compile(r"多少|多大|多高|多重|数值|百分之|%|几|效率|浓度|温度|时间|速率|强度|精度|准确率|召回|"
                r"误差|容量|性能|范围|比例|提高|降低|提升|幅度|倍数")
ST = ("answered", "partial", "insufficient_evidence", "input_error")


def q_terms(q, gloss):
    terms = {}

    def add(t, w):
        t = core.norm(t)
        if (len(t) < 2 and not t.isdigit()) or t in STOP:
            return
        terms[t] = max(terms.get(t, 0), w)

    for zh, ens in gloss.items():
        if zh and zh in q:
            for e in ens:
                if len(core.norm(e)) < 4 and core.norm(e) not in ("uts", "toc", "cod", "gnn", "cnn", "f1", "ph"):
                    continue  # 2–3 letter aliases such as "Eg" match unrelated words
                add(e, 1.0 + 0.12 * min(len(zh), 6))
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", q):
        add(tok, 1.3)
    for num in re.findall(r"\d+(?:\.\d+)?", q):
        if len(num) >= 2:
            add(num, 1.1)  # single digits ("top-1") match almost every paragraph
    return terms


def detect(q):
    f = set()
    if any(c in q for c in BN):
        f.add("BND")
    if NM.search(q):
        f.add("NUM")
    if any(c in q for c in MH):
        f.add("MECH")
    return f


def qtype(f):
    if "BND" in f:
        return "BND"
    if "NUM" in f and "MECH" in f:
        return "INT"
    return "NUM" if "NUM" in f else ("MECH" if "MECH" in f else "GEN")


NEG = re.compile(r"not (?:evaluat|measur|perform|report|test|investigat|studied|assess|available|includ)|"
                 r"did not|were not|was not|no data|not available|future work|beyond the scope|not addressed", re.I)


def pscore(p, terms, typ):
    txt, sec, s, hits = core.norm(p["text"]), core.norm(p["section"]), 0.0, []
    toks = set(re.findall(r"[a-z0-9][a-z0-9\.\-/]*", txt))
    for t, w in terms.items():
        c = txt.count(t)
        if not c and len(t) >= 5:  # v2: prefix/stem tolerance so "degradation" hits "degraded"
            c = sum(1 for tok in toks if tok.startswith(t[:6]) or (len(tok) >= 5 and t.startswith(tok[:6])))
        if c:
            s += w * (1 + 0.25 * min(c - 1, 3))
            hits.append(t)
    if not hits:
        return 0.0, []
    s /= 1.0 + len(txt.split()) / 150.0
    if any(k in sec for k in SEC_PREF.get(typ, ())):
        s += 0.9
    if typ in ("NUM", "INT") and core.VALRE.search(p["text"]):
        s += 0.4
    if typ == "BND" and NEG.search(txt):  # boundary questions: explicit non-report sentences first
        s += 0.6
    return round(s, 4), hits


def retrieve(q, paras, gloss, typ, k=5):
    terms = q_terms(q, gloss)
    n = len(paras)
    if n >= 4 and len(terms) > 1:
        # v2: drop terms present in most paragraphs (e.g. "photocatalyst"), otherwise every
        # paragraph scores and a question about an absent property looks "answered"
        df = {t: sum(1 for p in paras if t in core.norm(p["text"])) for t in terms}
        keep = {t: w for t, w in terms.items() if df[t] <= max(1, int(0.6 * n))}
        terms = keep or terms
    scored = []
    for i, p in enumerate(paras):
        s, hits = pscore(p, terms, typ)
        if s > 0:
            scored.append((s, i, p, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:k], terms


def evidence_for(sub, paras, gloss, typ, limit):
    ranked, terms = retrieve(sub, paras, gloss, typ, k=limit + 3)
    evs, best = [], ranked[0][0] if ranked else 0
    for score, idx, p, hits in ranked:
        if len(evs) >= limit or score < max(0.7, 0.5 * best):
            continue
        if len(terms) > 2 and len(hits) < 2 and not any(len(h) >= 6 for h in hits):
            continue  # v2: one specific (long) term is enough; v1 dropped such paragraphs
        if any(e["paragraph_id"] == p["paragraph_id"] for e in evs):
            continue
        cand = sorted(((pscore({"text": s, "section": p["section"]}, terms, typ)[0], a, b)
                       for a, b, s in core.sents(p["text"])), reverse=True)[:1]  # v2: one sentence per paragraph
        for s2, a, b in cand:
            quote = core.clip(p["text"], a, b, hits)
            if len(quote.split()) < 5:
                continue
            evs.append({"paragraph_id": p["paragraph_id"], "section": p["section"], "quote": quote,
                        "values": core.values(quote), "condition": core.cond_frag(quote),
                        "negation": bool(NEG.search(quote)),
                        "locator": p["locator"], "char_start": p["text"].find(quote)})
            if len(evs) >= limit:
                break
    return evs, terms


mkclaim = core.mkclaim


UCUE = {"温度": ("C", "°C", "℃", "K"), "时间": ("h", "min", "s", "d"),
        "强度": ("MPa", "GPa", "kPa"), "粒径": ("nm", "um", "µm", "μm", "mm"),
        "尺寸": ("nm", "um", "µm", "μm", "mm"), "浓度": ("mg/L", "mol/L", "mmol/L", "g/L", "ppm"),
        "效率": ("%",), "百分比": ("%",), "波长": ("nm",), "电位": ("V", "mV"), "功率": ("W", "mW", "kW"),
        "比表面积": ("m2/g", "m²/g"), "孔容": ("cm3/g",), "孔径": ("nm",), "带隙": ("eV",)}


def cue_units(sub):
    out = set()
    for zh, us in UCUE.items():
        if zh in sub:
            out.update(us)
    return out


def fallback_ev(qt, sub, paras, gloss, typ, cited, limit=2):
    """A sub-question split out of one sentence can still be answered by that sentence:
    accept whole-question evidence only from a paragraph a sibling cited, or one that
    carries a value in the unit this sub-question asks for."""
    evs, _ = evidence_for(qt, paras, gloss, typ, limit + 1)
    want = cue_units(sub)
    return [ev for ev in evs
            if ev["paragraph_id"] in cited or any(v["unit"] in want for v in ev["values"])][:limit]


def docfreq(sub, paras, gloss):
    terms = q_terms(sub, gloss)
    return terms, {t: sum(1 for p in paras if t in core.norm(p["text"])) for t in terms}


def val_ok(v, sub, terms, flags):
    """Boundary questions often carry incidental numbers in the same sentence
    (e.g. the solvent's wt%); keep a number only if it targets what was asked."""
    if "BND" not in flags:
        return True
    return v["unit"] in cue_units(sub) or any(len(w) >= 5 and w in core.norm(v["label"]) for w in terms)


def answer_one(q, paras, gloss, maxev):
    """v2: one claim per reported number, explicit sub_questions[], and
    insufficient_evidence (not a silent 'answered') when nothing is retrievable."""
    qid, qt = q["question_id"], q["question"]
    flags = detect(qt)
    typ, subs = qtype(flags), core.split_subs(qt)
    first, terms = [], {}
    for si, sub in enumerate(subs, 1):
        evs, t = evidence_for(sub, paras, gloss, typ, maxev)
        terms.update(t)
        first.append((si, sub, evs))
    cited = {ev["paragraph_id"] for _, _, e in first for ev in e}
    for i, (si, sub, evs) in enumerate(first):
        want = cue_units(sub)
        if want and not any(v["unit"] in want for _, _, e in first for ev in e for v in ev["values"]
                            if _ == si):
            # a condition sub-question ("at what temperature") often lives in a sibling's
            # sentence; adopt that paragraph when it carries a value in the wanted unit
            extra = [ev for _, _, e in first if _ != si for ev in e
                     if any(v["unit"] in want for v in ev["values"])
                     and ev["quote"] not in [x["quote"] for x in evs]]
            if extra:
                first[i] = (si, sub, (evs + extra[:1]) if evs else extra[:2])
                S["changes"].append({"item": f"{qid}-S{si}", "change": "采用兄弟子问段落中带该单位数值的证据"})
                continue
        if evs:
            continue
        fb = fallback_ev(qt, sub, paras, gloss, typ, cited)
        if fb:
            first[i] = (si, sub, fb)
            S["changes"].append({"item": f"{qid}-S{si}", "change": "子问无独立命中，改用同句/同段共用证据"})
    if "BND" in flags:  # a boundary question needs evidence that actually mentions the feature
        for i, (si, sub, evs) in enumerate(first):
            if not evs:
                continue
            _, dfq = docfreq(sub, paras, gloss)
            feats = [x for x in dfq if dfq[x] <= 1 and len(x) >= 4]
            if feats and not any(x in core.norm(ev["quote"]) for ev in evs for x in feats):
                first[i] = (si, sub, [])
                S["changes"].append({"item": f"{qid}-S{si}",
                                     "change": "边界题：命中段落未涉及被问特征，按未报告处理"})
    for i, (si, sub, evs) in enumerate(first):  # unit gate: the answer's numbers must be in the asked unit
        want = cue_units(sub)
        if want and evs and "NUM" in flags and \
                not any(v["unit"] in want for ev in evs for v in ev["values"]):
            found = sorted({v["unit"] for ev in evs for v in ev["values"]})
            S["uncertainties"].append({"type": "unit_mismatch", "question_id": qid,
                                       "detail": f"子问询问单位 {'/'.join(want)}，命中段落只有 {'/'.join(found) or '无数值'}",
                                       "paragraphs_searched": len(paras)})
            first[i] = (si, sub, [])
            S["changes"].append({"item": f"{qid}-S{si}", "change": "命中段落数值单位与被问量不符，按未报告处理"})
    claims, unans, conds, subs_out, all_ev, subev, seen = [], [], [], [], [], {}, {}
    for si, sub, evs in first:
        cids, pids = [], []
        for ei, ev in enumerate(evs):
            c = ev["condition"]
            if c and f"{c}（{ev['paragraph_id']}）" not in conds:
                conds.append(f"{c}（{ev['paragraph_id']}）")
            if ev["quote"] not in [x["quote"] for x in all_ev]:
                all_ev.append(ev)
            pids.append(ev["paragraph_id"])
            n_before = len(claims)
            for v in ev["values"]:
                if not val_ok(v, sub, terms, flags):
                    continue
                if "NUM" not in flags and ei > 0:
                    continue  # non-numeric question: numbers only from the best-matching paragraph
                key = (v["value"], v["unit"], ev["paragraph_id"])
                if key in seen:
                    cids.append(seen[key])
                    continue
                cid = f"{qid}-S{si}-N{len(claims) + 1}"
                claims.append(mkclaim(qid, cid, f"{v['label']} = {v['value']} {v['unit']}".strip(),
                                      "reported", [ev], [c] if c else []))
                seen[key] = cid
                cids.append(cid)
            if len(claims) == n_before:  # no numeric claim taken from this quote -> cite the quote itself
                cid = f"{qid}-S{si}-C{len(claims) + 1}"
                claims.append(mkclaim(qid, cid, f"原文（{ev['section']}，{ev['paragraph_id']}）：{ev['quote']}",
                                      "reported", [ev], [c] if c else []))
                cids.append(cid)
        subev[si] = evs
        has_num = any(ev["values"] for ev in evs)
        if evs and "NUM" in flags and not has_num:
            unans.append({"part": sub, "question_id": qid, "reason": "numeric_value_not_reported",
                          "missing": "该子问只有定性表述，未给出问题所问的数值",
                          "needed": "结果表、带单位的数值句或摘要中的数字"})
        if not evs:
            unans.append({"part": sub, "question_id": qid, "reason": "not_reported_after_full_search",
                          "missing": "该子问在供给材料中无可用原文依据（已对全部段落检索）",
                          "needed": "对应章节/表格/图注原文；若论文确实未报告，需作者说明或补充材料"})
        st = "answered" if evs and not ("NUM" in flags and not has_num) else \
            ("partial" if evs else "insufficient_evidence")
        subs_out.append({"index": si, "question": sub, "status": st, "claim_ids": cids,
                         "evidence_paragraph_ids": list(dict.fromkeys(pids))})
    absence = not all_ev
    if absence:
        zero = [k for k in terms if not any(core.norm(p["text"]).count(k) for p in paras)]
        S["uncertainties"].append({"type": "not_reported" if zero else "low_recall", "question_id": qid,
                                   "detail": f"零命中检索词 {len(zero)}/{len(terms)}；不代表论文没有该内容",
                                   "zero_hit_terms": zero[:10], "paragraphs_searched": len(paras)})
        S["pending"].append(f"{qid}: 全篇无匹配证据，请人工确认「未报告」结论并核对检索词")
        claims.append(mkclaim(qid, f"{qid}-ABS1",
                              f"供给材料未报告该问题所询问的内容（全篇 {len(paras)} 段、{len(terms)} 个检索词无可用命中）",
                              "inferred", []))
    other = next((ev for ev in all_ev[1:] if ev["paragraph_id"] != all_ev[0]["paragraph_id"]), None)
    if typ in ("INT", "MECH") and other:
        claims.append(mkclaim(qid, f"{qid}-INT1",
                              f"跨段落整合：{all_ev[0]['paragraph_id']} 给方法/条件侧，"
                              f"{other['paragraph_id']} 给结果侧（两段合并推出，非单段直述）",
                              "inferred", [all_ev[0], other],
                              [c for c in (all_ev[0]["condition"], other["condition"]) if c]))
        S["changes"].append({"item": qid, "change": "生成跨段落 inferred claim"})
    L = []
    if absence:
        L.append(f"材料未报告该问题涉及的内容：已检索全部 {len(paras)} 段，无可用原文依据，"
                 "不补外部知识（缺口见 unanswered_parts）。")
    for so in subs_out:
        e = subev.get(so["index"], [])
        L.append(f"【子问{so['index']}】{so['question']}")
        if not e:
            L.append("该子问无匹配原文（见 unanswered_parts）。")
            continue
        vals = [x for ev in e for x in ev["values"] if val_ok(x, so["question"], terms, flags)]
        want = cue_units(so["question"])
        picked = [x for x in vals if x["unit"] in want] if want else []
        kv = list(dict.fromkeys(f"{x['label']} = {x['value']} {x['unit']}".strip()
                                for x in (picked or vals)))
        if kv:
            L.append("数值：" + "；".join(kv) + "。")
        L.append("原文依据：" + "；".join(f'"{ev["quote"]}"（{ev["paragraph_id"]}）' for ev in e))
        cs = list(dict.fromkeys(ev["condition"] for ev in e if ev["condition"]))
        if cs:
            L.append("成立条件：" + "；".join(cs) + "。")
        if any(ev.get("negation") and any(w in core.norm(ev["quote"]) for w in terms if len(w) >= 5)
               for ev in e):
            L.append("判定：材料明确写出该项未开展/未报告（见引文），属原文交代的边界，非遗漏。")
        elif typ == "BND":
            L.append("判定：材料仅相关提及，未给出问题要求的具体项；不得据此推断为「不存在」。")
    pids = list(dict.fromkeys(ev["paragraph_id"] for ev in all_ev))
    status = "insufficient_evidence" if absence else ("partial" if unans else "answered")
    return {"question_id": qid, "question": qt, "answer": "\n".join(L), "conditions": conds,
            "status": status, "question_type": typ, "flags": sorted(flags),
            "sub_questions": subs_out, "claims": claims, "unanswered_parts": unans,
            "evidence_paragraph_ids": pids}


def apply_patch(payload, path, paras):
    data, err = core.jload(path)
    ed = data.get("answers") if isinstance(data, dict) else None
    if not ed:
        S["degradations"].append({"item": "answers_patch.json", "reason": err, "impact": "保留原始回答"})
        return payload
    n = 0
    for a in payload["result"]["answers"]:
        pt = ed.get(a["question_id"])
        if not pt:
            continue
        pt = {"answer": pt} if isinstance(pt, str) else pt
        ev = " ".join(e["quote"] for c in a["claims"] for e in c.get("evidence") or [])
        if pt.get("answer") and all(x in ev for x in re.findall(r"\d+(?:\.\d+)?", str(pt["answer"]))):
            a["answer"], n = str(pt["answer"]).strip(), n + 1
            if isinstance(pt.get("conditions"), list):
                a["conditions"] = [str(x) for x in pt["conditions"]]
        else:
            S["pending"].append(f'{a["question_id"]}: patch 数字未见于引文，已拒收')
    S["changes"].append({"item": "answers_patch", "change": f"合并 {n} 条回答"})
    return payload


def run(inp, out, args):
    cpath = core.find_case(inp, args.case)
    case, err = (None, None)
    if cpath:
        case, err = core.jload(cpath)
    if case is None:
        S["errors"].append({"stage": "load_case", "error": err or "case.json not found", "looked_in": str(inp)})
        S["missing"].append("case.json（/input 下未找到可解析的案例文件）")
        case = {}
    meta = core.build_meta(case)
    paras = core.collect_paragraphs(case)
    questions, qwhere = core.find_questions(case)
    gloss = core.load_gloss()
    answers, all_unans = [], []
    if not questions:
        S["degradations"].append({"item": "questions", "reason": "无问题清单", "impact": "answers 为空，契约字段仍完整"})
    for q in questions:
        try:
            a = answer_one(q, paras, gloss, 3)
        except Exception as e:  # noqa: BLE001
            S["errors"].append({"stage": "answer", "question_id": q["question_id"],
                                "error": f"{type(e).__name__}: {e}"})
            a = {"question_id": q["question_id"], "question": q["question"], "conditions": [], "status": "partial",
                 "claims": [], "answer": "该题处理异常，未生成回答（见 errors）。",
                 "unanswered_parts": [{"part": q["question"], "reason": "internal_error", "needed": f"{e}"}],
                 "evidence_paragraph_ids": [], "sub_questions": [], "question_type": "GEN", "flags": []}
        answers.append(a)
        all_unans.extend(a["unanswered_parts"])
    claims = [c for a in answers for c in a["claims"]]
    for c in claims:
        c["source_id"] = meta["paper_id"]
        for e in c.get("evidence", []):
            e["paper_id"] = meta["paper_id"]
    st = [a["status"] for a in answers]
    overall = ("input_error" if not questions else "ok" if st and set(st) == {"answered"} else
               "insufficient_evidence" if st and set(st) == {"insufficient_evidence"} else "partial")
    cov = core.coverage(paras, answers)
    cn = core.counts(answers, claims)
    payload = {
        "case_id": meta["case_id"], "paper_id": meta["paper_id"],
        "material_version": meta["material_version"], "status": overall,
        "summary": (f"{cn['questions']} 题（{cn['sub_questions']} 个子问）：answered {cn['answered']}、"
                    f"partial {cn['partial']}、insufficient_evidence {cn['insufficient_evidence']}；"
                    f"claims {cn['claims']}（含数值 claim {cn['numeric_claims']}），"
                    f"引文命中 {cn['evidence_verified']}/{cn['evidence']}；阅读 {cov.get('paragraphs_indexed')} 段"
                    f"（{cov.get('read_status')}）"),
        "result": {"answers": answers, "unanswered_parts": all_unans, "coverage": cov},
        "answers": answers, "unanswered_parts": all_unans, "coverage": cov,
        "claims": claims, "uncertainties": S["uncertainties"], "uncertainty": S["uncertainties"],
        "sources": ([{"type": "input_case", "path": str(cpath), "sha256_16": core.sha(cpath),
                      "paragraphs": len(paras), "questions": len(questions)}] if cpath else []),
        "pending_human": S["pending"], "errors": S["errors"], "degradations": S["degradations"],
        "changes": S["changes"], "counts": cn,
        "primary_result": "/app/output/result.json",
        "evidence": list({(e.get("paragraph_id"), e.get("quote")): e for c in claims
                          for e in c.get("evidence") or []}.values()),
        "method_notes": {"pipeline": "parse > bilingual terms > paragraph score > sentence quote > claim > self-check",
                         "quote_policy": "quote 从原文字符区间切片并逐字校验（15–60 词，同段内延伸）；全篇命中 0 记为未报告",
                         "claim_policy": "每个报告数值单独一条 claim（label = value unit）；跨段合并另立 inferred claim"},
        "runtime": {"script_seconds": round(time.time() - T0, 2), "model_requests_by_script": 0,
                    "python": sys.version.split()[0], "version": VERSION, "truncated": False,
                    "budget": {"wall_limit_s": 900, "questions_processed": len(answers),
                               "paragraphs_scanned": len(paras), "max_evidence_per_subq": 3},
                    "budget_note": "脚本不发起模型请求；单次调用秒级完成，不截断"},
        "contract_keys": list(case["output_contract"]) if isinstance(case.get("output_contract"), dict) else [],
        "question_ids": [q["question_id"] for q in questions],
    }
    payload = core.apply_contract(payload, case.get("output_contract"))
    if args.apply:
        payload = apply_patch(payload, args.apply, paras)
        payload["claims"] = [c for a in payload["result"]["answers"] for c in a["claims"]]
        payload["counts"] = core.counts(payload["result"]["answers"], payload["claims"])
    return payload, paras, meta


def selfcheck(payload, paras, out):
    txt = {p["paragraph_id"]: p["text"] for p in paras}
    ans = (payload.get("result") or {}).get("answers") or []
    cl, keys = payload.get("claims") or [], payload.get("contract_keys") or []
    evs = [e for a in ans for c in a.get("claims") or [] for e in c.get("evidence") or []]
    bad = [e.get("paragraph_id") for e in evs if e.get("quote") not in txt.get(e.get("paragraph_id"), "")]
    off = [e.get("paragraph_id") for e in evs
           if e.get("quote") in txt.get(e.get("paragraph_id"), "")
           and txt[e["paragraph_id"]].find(e["quote"]) != e.get("char_start")]
    rc = core.counts(ans, cl)
    ck = {"result_json_parses": bool(payload),
          "contract_keys_echoed": all(k in payload for k in keys),
          "questions_covered": sorted(a.get("question_id") for a in ans) == sorted(payload.get("question_ids") or []),
          "enums_valid": all(a.get("status") in ST for a in ans) and
          all(c.get("kind") in ("reported", "inferred") for c in cl),
          "quotes_verbatim": not bad,
          "char_offsets_match": not off,
          "paragraph_ids_exist": all(e.get("paragraph_id") in txt for e in evs),
          "gaps_for_non_answered": all(a.get("unanswered_parts") for a in ans
                                       if a.get("status") in ("partial", "insufficient_evidence")),
          "sub_questions_numbered": all(a.get("sub_questions") and
                                        [s.get("index") for s in a["sub_questions"]] ==
                                        list(range(1, len(a["sub_questions"]) + 1)) for a in ans),
          "numeric_claims_for_numeric_q": all(
              any(" = " in str(c.get("text", "")) for c in a.get("claims") or []) or
              a.get("status") != "answered" for a in ans
              if "NUM" in (a.get("flags") or []) and "BND" not in (a.get("flags") or [])),
          "coverage_present": bool((payload.get("result") or {}).get("coverage")),
          "runtime_budget_present": bool((payload.get("runtime") or {}).get("budget"))}
    rep = {"ok": all(ck.values()), "checks": [{"check": k, "ok": v} for k, v in ck.items()],
           "fails": [k for k, v in ck.items() if not v], "unmatched_quotes": bad[:5],
           "offset_mismatch": off[:5], "stats": rc, "quote_hit_rate": rc["quote_hit_rate"],
           "quote_words": {"min": rc.get("quote_words_min"), "max": rc.get("quote_words_max"),
                           "below_15": rc.get("quotes_below_15_words"),
                           "note": "短句属自然句长，不强制截断；不影响逐字命中"}}
    core.jdump(out / "verify_report.json", rep)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="literature-qa: answer supplied paper questions with verbatim evidence.",
                                 epilog="exit code is always 0; a partial result.json is written before parsing.")
    ap.add_argument("--input", default=None, help="input dir (default /input, else <cwd>/input)")
    ap.add_argument("--out", default=None, help="output dir (default /app/output, else ./output)")
    ap.add_argument("--case", default=None, help="explicit case json path")
    ap.add_argument("--apply", default=None, help="merge an agent-written answer patch json")
    ap.add_argument("--quiet", action="store_true", help="suppress stdout summary")
    ap.add_argument("--version", action="version", version=f"literature-qa {VERSION}")
    args = ap.parse_args(argv)

    def pick(path):
        for p in ([Path(path)] if path else []) + [Path("/app/output"), Path.cwd() / "output"]:  # noqa: E501
            try:
                p.mkdir(parents=True, exist_ok=True)
                (p / ".w").write_text("x", encoding="utf-8")
                (p / ".w").unlink()
                return p
            except Exception:  # noqa: BLE001
                continue
        return Path.cwd()

    out = pick(args.out)
    inp = Path(args.input) if args.input else Path("/input")
    if not inp.is_dir():
        inp = Path.cwd() / "input"

    core.jdump(out / "result.json", core.empty_payload())  # partial-first
    payload, paras, meta = core.empty_payload(), [], {}
    try:
        payload, paras, meta = run(inp, out, args)
    except Exception as e:  # noqa: BLE001
        S["errors"].append({"stage": "run", "error": f"{type(e).__name__}: {e}"})
        payload = core.empty_payload()
        payload["status"], payload["errors"] = "input_error", S["errors"]
    try:
        core.jdump(out / "result.json", payload)
        answers = (payload.get("result") or {}).get("answers") or []
        core.jdump(out / "paragraph_index.json", {
            "case_id": meta.get("case_id"), "paper_id": meta.get("paper_id"), "not_supplied": S["missing"],
            "paragraphs": [{"paragraph_id": p["paragraph_id"], "section": p["section"],
                            "kind": p.get("kind"), "text": p["text"]} for p in paras]})
        core.jdump(out / "answers.json", {
            "case_id": meta.get("case_id"), "paper_id": meta.get("paper_id"),
            "material_version": meta.get("material_version"),
            "claims": payload.get("claims") or [], **payload["result"]})
        core.write_csv(out, meta, answers)
        if Path("/app").is_dir():
            try:
                core.jdump(Path("/app/answers.json"), {"case_id": meta.get("case_id"), "answers": answers,
                                                      "claims": payload.get("claims") or []})
            except Exception as e:  # noqa: BLE001
                S["degradations"].append({"item": "/app/answers.json", "reason": str(e), "impact": "未写出"})
    except Exception as e:  # noqa: BLE001
        S["errors"].append({"stage": "emit", "error": f"{type(e).__name__}: {e}"})
        try:
            core.jdump(out / "result.json", payload)
        except Exception:  # noqa: BLE001
            pass
    rep = {"ok": None, "fails": []}
    try:
        rep = selfcheck(payload, paras, out)
    except Exception as e:  # noqa: BLE001
        S["errors"].append({"stage": "selfcheck", "error": f"{type(e).__name__}: {e}"})
    try:  # finalize: full payload (incl. verification) is the last unconditional write
        payload["verification"] = rep
        payload["errors"], payload["degradations"] = S["errors"], S["degradations"]
        payload["pending_human"] = S["pending"]
        core.jdump(out / "result.json", payload)
    except Exception as e:  # noqa: BLE001
        S["errors"].append({"stage": "finalize", "error": f"{type(e).__name__}: {e}"})
    if not args.quiet:
        c = payload.get("counts", {})
        print(f"[literature-qa {VERSION}] case={payload.get('case_id')} status={payload.get('status')} "
              f"q={c.get('questions')} subq={c.get('sub_questions')} claims={c.get('claims')} "
              f"quote_hit={c.get('quote_hit_rate')} selfcheck={rep.get('ok')} fails={rep.get('fails')}")
    return 0


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
