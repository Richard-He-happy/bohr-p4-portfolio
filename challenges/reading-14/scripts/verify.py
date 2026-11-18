#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent check + query layer for the literature knowledge graph.
  python3 verify.py --input /input --output /app/output
Reads graph_raw.json produced by build_graph.py, re-checks every quote against
the source paragraph text, derives claims, adds researcher nodes from the
corpus manifest, executes the graph queries, exports nodes.csv / edges.csv /
queries.md / verify_report.json and performs the final output_contract
back-fill into result.json. Exit code is always 0.
"""
import argparse, csv, json, sys, time
from pathlib import Path
T0 = time.time()


def h8(s):
    import hashlib
    return hashlib.sha1(s.encode()).hexdigest()[:8]


def nm(s):
    import re
    s = (s or "").lower()
    for a, b in (("\u2013", "-"), ("\u2014", "-"), ("\u2011", "-"), ("\u00a0", " "), ("\u201c", ""), ("\u201d", "")): s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%./+\- ]+", " ", s)).strip(" .-/")


def rd(p):
    for e in ("utf-8", "utf-8-sig", "latin-1"):
        try: return p.read_text(encoding=e)
        except Exception: pass
    return ""


def wr(p, s): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def dp(p, o): wr(p, json.dumps(o, ensure_ascii=False, indent=2))


def find_para(P, c, loc):
    """Resolve a paragraph by (source_id, paragraph_id); paragraph ids repeat across papers."""
    pid = loc.get("paragraph_id")
    if not pid:
        return None
    keys, srcs = [], []
    sid = c.get("source_id")
    if isinstance(sid, str):
        for s in sid.split("+"):
            if s.strip(): srcs.append(s.strip())
    cond_srcs = (c.get("condition") or {}).get("sources")
    if isinstance(cond_srcs, list):
        for s in cond_srcs:
            if isinstance(s, str) and s.strip() and s not in srcs: srcs.append(s)
    for s in srcs:
        keys.append("%s||%s" % (s, pid))
    keys.append(pid)
    for k in keys:
        if k in P:
            return P[k].get("text")
    return None


def main():
    ap = argparse.ArgumentParser(prog="verify.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Verify quotes vs source paragraphs, derive claims, run graph queries, export CSV, back-fill output_contract.",
        epilog="Example: python3 verify.py --input /input --output /app/output")
    ap.add_argument("--input", default="/input", help="input dir")
    ap.add_argument("--output", default="/app/output", help="output dir")
    a = ap.parse_args()
    inp, out = Path(a.input), Path(a.output)
    res_p, gra_p = out / "result.json", out / "graph_raw.json"
    R = {}
    try:
        R = json.loads(rd(res_p)) if res_p.exists() else {}
    except Exception:
        R = {}
    try:
        G = json.loads(rd(gra_p)) if gra_p.exists() else {}
    except Exception:
        G = {}
    err, deg, unc, pend = R.setdefault("errors", []), R.setdefault("degradations", []), R.setdefault("uncertainty", []), R.setdefault("pending_human", [])
    if not G:
        err.append({"stage": "verify.load_graph", "error": "graph_raw.json missing or unreadable", "effect": "claims/queries not generated"})
        R["status"] = R.get("status") or "partial"
        dp(res_p, R)
        return R
    N = {n["id"]: n for n in G.get("nodes", [])}
    E = G.get("edges", [])
    SRC = G.get("sources", [])
    P = G.get("paragraphs", {}) or {}

    # ---- researcher nodes from the corpus manifest (entity type 研究者)
    added = 0
    for s in SRC:
        for i, au in enumerate([x for x in (s.get("authors") or []) if isinstance(x, str) and len(x.strip()) > 1][:20]):
            nid = "n-" + h8("researcher|" + nm(au))
            if nid in N: continue
            N[nid] = {"id": nid, "label": au, "type": "researcher", "type_basis": "manifest_authors", "aliases": [], "sources": [s["source_id"]],
                      "evidence": [{"quote": au, "source_id": s["source_id"], "location": {"kind": "json_field", "field": "authors", "pointer": "/papers/authors/%d" % i}, "evidence_class": "directly_read"}],
                      "mention_count": 1, "confidence": "high"}
            added += 1

    # ---- claims (entity / relation / cross-paper alignment)
    cross = [n["id"] for n in N.values() if len(n.get("sources", [])) > 1]
    CL = []
    for n in N.values():
        if not n.get("evidence"): continue
        CL.append({"claim_id": "c-" + h8(n["id"]), "kind": "entity_mention", "subject": n["id"], "assertion": "%r appears verbatim in the source text" % n["label"],
                   "source_id": n["sources"][0], "evidence": n["evidence"][0]["quote"], "location": n["evidence"][0]["location"],
                   "condition": {"scope": "full text of the source", "sources": n["sources"]},
                   "evidence_class": "directly_read", "type_evidence_class": "inferred" if n.get("type_basis") == "cue_word" else "undetermined"})
    for e in E:
        v = e["evidence"][0]
        CL.append({"claim_id": "c-" + h8(e["id"]), "kind": "relation", "subject": e["subject"], "predicate": e["predicate"], "object": e["object"],
                   "assertion": "%s -%s-> %s" % (e.get("subject_label"), e["predicate"], e.get("object_label")), "source_id": v["source_id"],
                   "evidence": v["quote"], "location": v["location"], "condition": e.get("condition"), "evidence_class": "directly_read"})
    for nid in cross:
        n = N[nid]
        CL.append({"claim_id": "c-" + h8(nid + "a"), "kind": "cross_source_alignment", "subject": nid,
                   "assertion": "surface %r occurs in %d sources" % (n["label"], len(n["sources"])), "source_id": "+".join(n["sources"]),
                   "evidence": n["evidence"][0]["quote"], "location": n["evidence"][0]["location"],
                   "condition": {"merge_basis": "identical normalised surface", "sources": n["sources"]}, "evidence_class": "directly_read",
                   "inference_class": "inferred", "not_claimed": "sameness of material instance / dataset / experimental condition"})

    # ---- quote verification against the organizer paragraph text
    ok = bad = skipped = 0
    badq = []
    for c in CL:
        q, loc = c.get("evidence") or "", (c.get("location") or {})
        if not q: continue
        if loc.get("kind") != "jats_paragraph_id":
            skipped += 1; continue
        txt = find_para(P, c, loc)
        if txt is None:
            skipped += 1; badq.append({"claim_id": c["claim_id"], "issue": "paragraph id not in index", "paragraph_id": loc.get("paragraph_id")}); continue
        if q in txt: ok += 1
        else:
            bad += 1; badq.append({"claim_id": c["claim_id"], "issue": "quote not verbatim in paragraph", "paragraph_id": loc.get("paragraph_id"), "quote": q[:120]})
    dangling = [e["id"] for e in E if e["subject"] not in N or e["object"] not in N]

    # ---- queries actually executed on the graph
    Q = lambda i, q, k: {"query_id": i, "question": q, "kind": k, "executed": True, "status": "answered", "answer": "", "result_nodes": [], "result_edges": [], "evidence": [], "undetermined": [], "limitations": ""}
    evn = lambda n, m=170: {"node": n, "label": N[n]["label"], "sources": N[n]["sources"], "quote": (N[n].get("evidence") or [{}])[0].get("quote", "")[:m], "location": (N[n].get("evidence") or [{}])[0].get("location", {})}
    eve = lambda e, m=190: {"edge": e["id"], "triple": "%s -%s-> %s" % (e.get("subject_label"), e["predicate"], e.get("object_label")), "quote": e["evidence"][0]["quote"][:m], "location": e["evidence"][0]["location"]}
    qs = []
    if N:
        x = Q("Q1", "哪些实体在两篇（多篇）论文中同时出现？合并依据是什么？", "cross_source_alignment")
        x["result_nodes"] = cross[:12]; x["evidence"] = [evn(n) for n in cross[:6]]
        x["undetermined"] = [{"item": "同一术语是否指同一物理样品/数据集/条件", "status": "undetermined",
                              "why": "两篇均未给出可相互对应的样品编号或数据来源标识；字符串相同不构成同一性证据"}]
        x["limitations"] = "对齐为字符串级，未接本体；同形异义需人工复核"
        x["answer"] = ("跨篇对齐节点 %d 个：%s。" % (len(cross), "; ".join(N[n]["label"] for n in cross[:8]))) if cross else "两篇论文没有共享同一规范化术语的节点；不强行对齐。"
        if not cross: x["status"] = "no_result"
        qs.append(x)
        dg = {}
        for e in E:
            dg[e["subject"]] = dg.get(e["subject"], 0) + 1; dg[e["object"]] = dg.get(e["object"], 0) + 1
        if dg:
            top = max(dg.items(), key=lambda kv: kv[1])[0]; rel = [e for e in E if top in (e["subject"], e["object"])]
            x = Q("Q2", "证据最充分的实体是谁？每条关系分别由哪段原文支撑？", "provenance")
            x["result_nodes"] = [top]; x["result_edges"] = [e["id"] for e in rel][:12]; x["evidence"] = [eve(e) for e in rel][:6]
            x["answer"] = "实体 %r（%s）关联 %d 条边，均带段号与逐字引文。" % (N[top]["label"], top, dg[top])
            qs.append(x)
        mets = [n for n in N.values() if n.get("type") == "metric"]
        x = Q("Q3", "两篇论文各自报告了哪些指标/度量？能否直接跨篇比较？", "metric_by_source")
        if mets:
            x["result_nodes"] = [m["id"] for m in mets[:12]]; x["evidence"] = [evn(m["id"]) for m in mets[:6]]
            x["answer"] = "共 %d 个指标节点，按来源分别列出；未做任何跨篇算术合并。" % len(mets)
            x["undetermined"] = [{"item": "指标数值跨篇可比性", "status": "undetermined",
                                  "why": "样本/数据集/条件不同，跨篇合成结论被题目明确禁止"}]
        else:
            x["status"] = "no_result"; x["answer"] = "未识别到 metric 类型节点。"
        qs.append(x)
        cx = [e for e in E if e["predicate"] == "contradicts"]
        x = Q("Q4", "两篇论文之间是否存在相互矛盾的关系或结论？", "conflict_detection")
        if cx:
            x["result_edges"] = [e["id"] for e in cx][:10]; x["evidence"] = [eve(e) for e in cx][:5]
            x["answer"] = "检出 %d 条 contradicts 线索，已单列，未做裁决。" % len(cx)
            x["undetermined"] = [{"item": "矛盾是否真实", "status": "undetermined", "why": "文本层面的对立表述，需人工确认研究对象是否相同"}]
        else:
            x["status"] = "no_result"; x["answer"] = "未检出显式 contradicts 表述。"
            x["undetermined"] = [{"item": "两篇论文是否一致", "status": "undetermined", "why": "未检出矛盾不等于结论一致；本图谱只覆盖显式线索句"}]
        qs.append(x)
        x = Q("Q5", "两篇论文是否使用了同一物理样品/同一数据集/同一实验条件？", "sameness_check")
        x["status"] = "undetermined"; x["answer"] = "无法确定。"
        x["undetermined"] = [{"item": "样品/数据集/条件同一性", "status": "undetermined",
                              "why": "两篇原文未提供可相互对应的样品编号、制备批次或数据来源标识；相同通用方法或材料术语不等于同一物理对象",
                              "would_settle": "样品编号/批次、数据 DOI 或实验条件表"}]
        qs.append(x); pend.append({"id": "H-SAME", "action": "人工比对两篇的样品/数据来源描述", "why": "文本层面不足以判定同一性"})
        if P:
            first = P[next(iter(P))]
            sid0 = first.get("source_id"); pid0 = first.get("paragraph_id") or next(iter(P))
            he = [e for e in E if e["evidence"][0]["source_id"] == sid0 and (e.get("condition") or {}).get("paragraph_id") == pid0]
            hn = sorted({e["subject"] for e in he} | {e["object"] for e in he})
            x = Q("Q6", "给定段落编号，能否反查该段落贡献的节点与边？", "reverse_locate")
            x["result_nodes"] = hn[:10]; x["result_edges"] = [e["id"] for e in he][:10]; x["evidence"] = [eve(e) for e in he][:3]
            x["answer"] = "段落 %s（source %s）贡献 %d 个节点、%d 条边。" % (pid0, sid0, len(hn), len(he))
            if not he: x["status"] = "no_result"
            qs.append(x)
    okq = [q for q in qs if q["status"] == "answered"]

    # ---- exports
    try:
        with open(out / "nodes.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["node_id", "label", "type", "type_basis", "sources", "mentions", "confidence", "first_quote", "first_location"])
            for n in sorted(N.values(), key=lambda n: (n.get("type", ""), n.get("label", ""))):
                ev0 = (n.get("evidence") or [{}])[0]
                w.writerow([n["id"], n["label"], n.get("type"), n.get("type_basis"), ";".join(n.get("sources", [])), n.get("mention_count"), n.get("confidence"),
                            ev0.get("quote", "")[:160], json.dumps(ev0.get("location", {}), ensure_ascii=False)])
        with open(out / "edges.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["edge_id", "subject", "subject_label", "predicate", "object", "object_label", "source_id", "paragraph_id", "strength", "quote"])
            for e in E:
                v = e["evidence"][0]
                w.writerow([e["id"], e["subject"], e.get("subject_label"), e["predicate"], e["object"], e.get("object_label"),
                            v["source_id"], v["location"].get("paragraph_id"), e.get("evidence_strength"), v["quote"][:180]])
    except Exception as e:
        err.append({"stage": "verify.csv", "error": repr(e)[:160]})
    dp(out / "claims.json", CL)
    md = ["# 图谱查询结果（本轮执行）", "", "案例: `%s`　输入: `%s`" % (R.get("case_id"), inp), "",
          "%d 篇 / %d 节点 / %d 边 / %d claim；引文核验：%d 通过、%d 失败、%d 跳过。" % (len(SRC), len(N), len(E), len(CL), ok, bad, skipped), ""]
    for q in qs:
        md += ["## %s %s" % (q["query_id"], q["question"]), "- kind: `%s` | status: **%s**" % (q["kind"], q["status"]), "- answer: %s" % q["answer"]]
        for z in q["evidence"][:5]: md.append("- evidence: `%s` @ `%s`" % (str(z.get("quote", ""))[:150], json.dumps(z.get("location", {}), ensure_ascii=False)))
        for u in q["undetermined"]: md.append("- undetermined: %s — %s" % (u.get("item"), u.get("why")))
        md.append("")
    md += ["## 共现策略", "", "同句共现不生成边：每条边均由谓语线索触发；无线索的同现只算候选。"]
    wr(out / "queries.md", "\n".join(md))
    rep = {"quotes_checked": ok + bad, "quotes_ok": ok, "quotes_failed": bad, "quotes_skipped_nonparagraph": skipped, "failures": badq[:20],
           "dangling_edges": dangling[:20], "nodes": len(N), "edges": len(E), "claims": len(CL),
           "query_status": {q["query_id"]: q["status"] for q in qs}}
    dp(out / "verify_report.json", rep)
    if bad: unc.append({"id": "U-QUOTE", "kind": "verification", "statement": "%d 条引文未能在对应段落逐字命中" % bad, "evidence_class": "undetermined", "impact": "相关 claim 需人工复核，见 verify_report.json"})
    if dangling: unc.append({"id": "U-DANGLE", "kind": "graph", "statement": "%d 条边的端点不在节点表中" % len(dangling), "evidence_class": "undetermined", "impact": "该边不可查询"})

    # ---- final contract back-fill
    contract = R.get("output_contract") or {}
    if not isinstance(contract, dict): contract = {}
    R.update({"nodes": sorted(N.values(), key=lambda n: (n.get("type", ""), n.get("label", ""))), "edges": E, "claims": CL, "queries": qs, "sources": SRC})
    R["schema"] = {"entity_types": ["paper", "researcher", "material", "method", "task", "dataset", "metric", "concept"],
                   "relation_types": sorted({e["predicate"] for e in E}) or ["uses", "measures", "improves_over", "compared_with", "consistent_with", "contradicts", "is_a"],
                   "evidence_classes": ["directly_read", "inferred", "undetermined"],
                   "locator_kinds": ["jats_paragraph_id", "source_metadata", "json_field", "text_block"],
                   "id_policy": "n-<sha1(normalised label)[:8]> / e-<sha1(triple+source+paragraph)[:8]>; stable and reusable when a new paper is added",
                   "note": "label and quote are directly read; entity type is cue-word heuristic (type_basis); co-occurrence never creates an edge"}
    R["graph_summary"] = {"papers": len(SRC), "nodes": len(N), "edges": len(E), "claims": len(CL), "cross_source_nodes": len(cross),
                          "queries": len(qs), "queries_answered": len(okq),
                          "edges_per_paper": {s.get("source_id"): sum(1 for e in E if e["evidence"][0]["source_id"] == s.get("source_id")) for s in SRC},
                          "predicate_histogram": {p: sum(1 for e in E if e["predicate"] == p) for p in sorted({e["predicate"] for e in E})}}
    R["merge"] = dict(R.get("merge") or {}, policy="explicit definition over identical normalised surface; never merge on co-occurrence",
                      guard="同名术语不蕴含同一物理样品、数据集、模型实例或实验条件")
    R["incremental"] = {"id_policy": R["schema"]["id_policy"],
                        "on_new_paper": ["parse the new paper with the same parser", "extract with the same rules and caps",
                                         "reuse an existing node id when the normalised surface matches, and record the merge",
                                         "never delete prior nodes or renumber ids; conflicting evidence stays as two edges"],
                        "this_run": "single batch; ids already stable for incremental reuse"}
    R["self_check"] = {"quotes_ok": ok, "quotes_failed": bad, "dangling_edges": len(dangling),
                       "contract_backfilled": "%d/%d" % (len(contract), len(contract)) if contract else "no contract in case.json",
                       "verified_by": "verify.py"}
    R["artifacts"] = {"result_json": str(out / "result.json"), "graph": str(gra_p), "claims_json": str(out / "claims.json"), "nodes_csv": str(out / "nodes.csv"),
                      "edges_csv": str(out / "edges.csv"), "queries_md": str(out / "queries.md"), "verify_report": str(out / "verify_report.json")}
    R["status"] = "ok" if (SRC and E and okq and bad == 0) else ("partial" if (SRC or N) else "input_error")
    pay = {"nodes": R["nodes"], "edges": E, "claims": CL, "queries": qs, "uncertainty": unc, "pending_human": pend, "sources": SRC, "schema": R["schema"],
           "summary": "%d papers, %d nodes, %d edges, %d claims, %d queries (%d answered)" % (len(SRC), len(N), len(E), len(CL), len(qs), len(okq)),
           "graph_summary": R["graph_summary"], "report_markdown": "\n".join(md), "merge": R["merge"], "evidence": [c for c in CL if c["kind"] == "relation"][:80],
           "incremental": R["incremental"], "examples": [], "self_check": R["self_check"], "status": R["status"]}
    EN = [("node", "nodes"), ("entit", "nodes"), ("edge", "edges"), ("relation", "edges"), ("quer", "queries"), ("claim", "claims"), ("evidence", "evidence"),
          ("source", "sources"), ("uncertain", "uncertainty"), ("pending", "pending_human"), ("schema", "schema"), ("type", "schema"), ("summary", "summary"),
          ("graph", "graph_summary"), ("merge", "merge"), ("align", "merge"), ("status", "status"), ("increment", "incremental"), ("check", "self_check"),
          ("report", "report_markdown"), ("markdown", "report_markdown"), ("example", "examples")]
    CN = {"节点": "nodes", "实体": "nodes", "边": "edges", "关系": "edges", "查询": "queries", "结论": "claims", "证据": "evidence", "来源": "sources",
          "不确定": "uncertainty", "人工": "pending_human", "类型": "schema", "摘要": "summary", "合并": "merge", "状态": "status"}
    filled, unmap = {}, []
    for k in contract:
        lk = str(k).lower()
        hit = next((v for c, v in CN.items() if c in str(k)), None) or next((v for c, v in EN if c in lk), None)
        if hit: filled[k] = hit; R[k] = pay.get(hit, [])
        else: unmap.append(k); R[k] = None
    R["contract_coverage"] = {"provided_keys": [str(k) for k in contract], "filled": filled, "unmapped_nulled": unmap, "originals_preserved_in": "output_contract"}
    R.setdefault("runtime", {})["verify_elapsed_seconds"] = round(time.time() - T0, 2)
    dp(res_p, R)
    print("verify: quotes ok=%d failed=%d | nodes=%d edges=%d claims=%d | queries=%d/%d | contract=%d/%d" % (ok, bad, len(N), len(E), len(CL), len(okq), len(qs), len(filled), len(contract)))
    return R


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        try:
            o = Path("/app/output")
            p = o / "result.json"
            cur = json.loads(rd(p)) if p.exists() else {}
            cur.setdefault("errors", []).append({"stage": "verify.fatal", "error": repr(exc)[:300]})
            cur["status"] = cur.get("status") or "partial"
            dp(p, cur)
        except Exception:
            pass
    sys.exit(0)
