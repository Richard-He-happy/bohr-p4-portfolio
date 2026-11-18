#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intro-related-work-writer v1.0.0 — 把论文材料写成「背景+相关工作+空白+贡献」的证据绑定稿。
用法: python3 -B main.py --input /input --output /app/output [--manuscript PATH] [--max-refs N]
纯标准库；不联网；不依赖 CWD；退出码恒 0。"""
import argparse
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as V

SK = {"name": "intro-related-work-writer", "version": "1.0.0", "task_key": "writing-07"}
E, D, U, P, SRC = [], [], [], [], []
FB = {"t": "Introduction and Related Work", "n": "",
      "h": ["Background", "Related Work", "Gaps", "Contributions", "References"],
      "bg": ["", "", ""], "cd": "conditions", "lm": "limitation", "gp": "{route}: {q} [{k}].",
      "gn": "No gap basis found in supplied literature.", "rw": "", "rf": "", "td": "TO-VERIFY"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def disc(inp):
    """发现 case.json 与全部可读材料：按扩展名+可读性，不按标签猜内容。"""
    cands = []
    if inp.is_dir():
        cands = sorted({p for p in inp.rglob("case*.json") if p.is_file()})
    case, cp = {}, None
    for c in cands:
        try:
            o = json.loads(c.read_text(encoding="utf-8"))
            if isinstance(o, dict):
                case, cp = o, c
                break
        except Exception as exc:
            cp = cp or c
            E.append({"stage": "discover", "file": str(c), "error": f"{type(exc).__name__}: {exc}"})
    files = []
    if inp.is_dir():
        for p in sorted(inp.rglob("*")):
            if not p.is_file() or p.stat().st_size > 6000000:
                continue
            if p.name == "case.json":
                continue
            if p.suffix.lower() in V.TEXT_EXT | {".docx", ".xlsx", ".pdf"}:
                files.append(p)
    return case, cp, files


def frames():
    """读 references/frames.json（中英框架）；失败降级为内置最小框架并记 degradations。"""
    p = Path(__file__).resolve().parent.parent / "references" / "frames.json"
    try:
        f = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(f.get("zh"), dict) and isinstance(f.get("en"), dict):
            return f
        raise ValueError("frames.json 缺 zh/en")
    except Exception as exc:
        D.append({"stage": "frames", "file": str(p), "note": f"fallback_builtin ({type(exc).__name__})"})
        return {"zh": FB, "en": FB}


def echo(res, ct):
    """原样回填 output_contract 全部字段：键名不改，缺值 null/[]，未知字段保留。"""
    if isinstance(ct, dict):
        for k, spec in ct.items():
            if k not in res:
                res[k] = [] if isinstance(spec, (list, dict)) else None
    elif isinstance(ct, list):
        for it in ct:
            names = [it] if isinstance(it, str) else (
                [it[k] for k in ("name", "field", "key", "id") if isinstance(it.get(k), str)][:1]
                if isinstance(it, dict) else [])
            for k in names:
                res.setdefault(k, None)
    _fill_paths(res, ct)
    res["output_contract"] = ct
    return res


def _fill_paths(res, ct):
    """契约值显式要"路径/文件"型产物时，映射到实际产物路径而非 null。"""
    if not isinstance(ct, dict):
        return
    hints = ("path", "file", "filepath", "filename", "output_path", "output_file",
             "deliverable", "artifact", "md", "markdown", "json", "csv")
    dlv = res.get("deliverables") or {}
    for k, spec in ct.items():
        if not (isinstance(spec, str) and spec.strip().lower() in hints):
            continue
        kk = (k or "").lower()
        for name, path in dlv.items():
            if (name in kk or name.replace("_", "") in kk.replace("_", "")) and res.get(k) is None:
                res[k] = path
                break


def base(cid, ct, st):
    return {"case_id": cid, "skill": SK, "status": "partial", "stage": "init", "deliverables": {},
            "sections_present": {}, "citations": [], "evidence_map": [], "preserved_facts": [], "groups": [],
            "gap_derivation": [], "contribution_alignment": [], "coverage": {}, "workorder_receipts": [],
            "manuscript_text": "", "changes": [], "sources": [], "uncertainty": [], "pending_human": [],
            "errors": [], "degradations": [], "verification": {},
            "runtime": {"skill_version": SK["version"], "started_at": st, "python": sys.version.split()[0]},
            "output_contract": ct}


def main(argv=None):
    ap = argparse.ArgumentParser(description="引言与相关工作写作：材料→证据绑定稿+分组矩阵+result.json（先落 partial，末 finalize）",
                                 epilog="纯标准库；退出码恒 0；异常写入 errors/degradations。")
    ap.add_argument("--input", default="/input", help="输入目录（case.json + 材料），默认 /input")
    ap.add_argument("--output", default="/app/output", help="输出目录，默认 /app/output")
    ap.add_argument("--manuscript", default="", help="可选：作者改写稿路径，用于复查与重建证据表")
    ap.add_argument("--max-refs", type=int, default=40, help="参与分组的文献上限，默认 40")
    a, _ = ap.parse_known_args(argv)
    st = now()
    inp, out = Path(a.input), Path(a.output)
    if not inp.is_absolute():
        inp = (Path.cwd() / inp).resolve()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        out = Path(__file__).resolve().parent.parent / "out"
        out.mkdir(parents=True, exist_ok=True)
    ct, cid, files, case = {}, "", [], {}
    res = base(cid, ct, st)
    try:
        wj(out / "result.json", res)          # 第一步：合法 partial 先落盘
    except Exception:
        pass
    try:
        case, cp, files = disc(inp)
        cid = str(case.get("case_id") or case.get("id") or "")
        if not cid and cp:
            m = re.search(r'"case_id"\s*:\s*"([^"]{1,80})"', cp.read_text(encoding="utf-8", errors="replace"))
            cid = m.group(1) if m else cp.stem
        ct = case.get("output_contract") or case.get("outputContract") or case.get("contract") or {}
        if not ct and cp:  # case.json 坏掉时按正则抢救契约键名，保证键不回填丢失
            raw = cp.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'"output_contract"\s*:\s*\{([^{}]{2,4000})\}', raw)
            if m:
                ct = {k: None for k in re.findall(r'"([\w\-]{1,60})"\s*:', m.group(1))}
                E.append({"stage": "contract", "note": "output_contract 由坏 JSON 正则抢救，值置 null"})
        res.update(case_id=cid, stage="discover", output_contract=ct)
        if not case:
            E.append({"stage": "discover", "error": "case.json missing or unparsable"})
        if not files:
            P.append({"item": "materials", "detail": "输入目录无可读材料（md/txt/json/csv/docx/pdf/xlsx）"})
        chunks, sources = [], {}
        for p in files:
            text, kind = V.read_any(p, E)
            if kind == "unsupported" or len(V.norm(text)) < 40:
                if kind == "unsupported":
                    D.append({"stage": "extract", "file": str(p), "note": "unsupported_type_skipped"})
                continue
            sid = str(p.relative_to(inp)) if (inp in p.parents or p.parent == inp) else p.name
            if kind == "pdf":
                D.append({"stage": "extract", "file": sid, "note": "pdf_text_heuristic: stdlib streams, no page map"})
            sources[sid] = text
            chunks += V.chunkify(sid, kind, text)
            SRC.append({"source_id": sid, "path": str(p), "kind": kind, "chars": len(text)})
        wj(out / "sources_index.json", {k: {"text": v[:400000]} for k, v in sources.items()})
        res["stage"] = "extract"
        refs = []
        for sid, text in sources.items():
            if sid.endswith((".json", ".yaml", ".yml")):
                try:
                    refs += [V.to_ref(d, sid, loc) for loc, d in V.walk_refs(json.loads(text)) if d.get("title")]
                except Exception as exc:
                    E.append({"stage": "refs", "file": sid, "error": f"{type(exc).__name__}: {exc}"})
        refs += V.refs_from_text(chunks, set())
        seen, uq = set(), []
        for r in refs:
            k = V.norm(r["title"]).lower()[:60]
            if k and k not in seen:
                seen.add(k)
                uq.append(r)
        refs = uq[:max(0, a.max_refs)]
        for i, r in enumerate(refs, 1):
            r["id"] = f"R{i:02d}"
            if r["metadata_status"] != "complete":
                P.append({"item": r["id"], "detail": "引用元数据不全",
                          "missing": [k for k in ("authors", "year", "title", "venue") if not r[k]]})
        res["stage"] = "refs"
        ref_sids = {r["source_id"] for r in refs if r["origin"] == "structured"}
        own = [c for c in chunks
               if c["source_id"] not in ref_sids and not c["text"].lstrip().startswith(("{", "[", "<"))
               and not any(c["source_id"] == r["source_id"] and c["locator"] == r["locator"] for r in refs)]
        own = own or chunks
        plain = [c for c in own if not any(k in c["text"].lower() for k in V.KC)]
        anchors = V.pick(plain or own, V.OC, 3)
        contribs = [c for c in V.pick([c for c in own if any(k in c["text"].lower() for k in V.KC)] or own,
                                      V.KC + ("table", "fig", "表", "图"), 4) if c["text"] not in {a["text"] for a in anchors}]
        groups = {}
        for r in refs:
            lab, sc = V.route(r["title"], r["abstract"] or r["venue"])
            r["route"], r["route_score"] = lab or "unclassified", sc
            groups.setdefault(r["route"], []).append(r)
        if groups.get("unclassified"):
            P.append({"item": "routing", "detail": "文献未命中路线词表，需人工归组",
                      "ids": [r["id"] for r in groups["unclassified"]]})
            U.append({"item": "routing", "detail": "存在未分组文献，比较维度可能不完整"})
        order = sorted(groups, key=lambda k: (-len(groups[k]), k))
        lang = "zh" if _zh(str(case.get("task_instruction") or ""), " ".join(c["text"][:400] for c in own[:4])) else "en"
        L = frames().get(lang) or FB
        gaps = []
        for lab in order:
            for kind, pat in (("shared_limitation", None),
                              ("uncovered_scenario", r"only|limited to|restrict|narrow|仅|只|局限"),
                              ("conflict", r"whereas|in contrast|conflict|differ|相反")):
                for r in groups[lab]:
                    hit = [s for s in V.lim(r) if not (pat and not re.search(pat, s, re.I))]
                    if hit and not any(g["basis_quote"] == hit[0] for g in gaps):
                        gaps.append({"gap_id": f"G{len(gaps) + 1:02d}", "gap_type": kind, "route": lab,
                                     "basis_quote": hit[0], "supports": [r["id"]],
                                     "source_id": r["source_id"], "locator": r["locator"]})
                if len(gaps) >= 6:
                    break
            if len(gaps) >= 6:
                break
        num = {r["id"]: i for i, r in enumerate(refs, 1)}
        cite = lambda rid: f"[{num[rid]}]" if rid in num else "[?]"
        md = V.compose(L, anchors, order, groups, gaps, contribs, refs, num, cite)
        if a.manuscript and Path(a.manuscript).is_file():
            md = Path(a.manuscript).read_text(encoding="utf-8", errors="replace")
            U.append({"item": "manuscript", "detail": "使用作者提供稿复查，未重新生成正文"})
            miss = [r["id"] for r in refs if V.sents(r["abstract"]) and V.sents(r["abstract"])[0] not in md]
            if miss:
                P.append({"item": "rewrite", "detail": f"{len(miss)} 条文献原摘要句未逐字见于改写稿，需确认转述一致",
                          "ids": miss[:10]})
        (out / "manuscript.md").write_text(md, encoding="utf-8")
        mx = ["# Related-work matrix (route x dimension)", "",
              "| id | route | authors/year | problem setting | data & evaluation | stated limitation | locator |",
              "|-|-|-|-|-|-|-|"]
        f = lambda s: V.norm(s or "—").replace("|", "/")[:170]
        for r in sorted(refs, key=lambda x: (x["route"], x["year"])):
            mx.append("| {} | {} | {} {} | {} | {} | {} | `{}#{}` |".format(
                r["id"], r["route"], f(r["authors"]), f(r["year"]),
                f(V.claim_of(r)), f(V.dim(r)),
                f((V.lim(r) or ["—"])[0]), r["source_id"], r["locator"]))
        (out / "related_work_matrix.md").write_text("\n".join(mx) + "\n", encoding="utf-8")
        ev, facts, changes = [], [], []

        def add(sec, who, q, sid, loc):
            ev.append({"claim_id": f"E{len(ev) + 1:03d}", "section": sec, "citation": who, "claim": q,
                       "source_id": sid, "locator": loc, "quote": q,
                       "quote_verified": V.find_quote(q, sources.get(sid, ""))})

        for r in refs:
            q = V.claim_of(r)
            add("related_work", r["id"], q, r["source_id"], r["locator"])
            for g in gaps:
                if r["id"] in g["supports"]:
                    add("research_gap", r["id"], g["basis_quote"], g["source_id"], g["locator"])
                    break
            facts += [{"fact": x, "source_id": r["source_id"], "locator": r["locator"], "quote": q}
                      for x in V.numbers(q)]
        for x in anchors + contribs:
            add("background" if x in anchors else "contributions", "own", x["text"], x["source_id"], x["locator"])
            facts += [{"fact": y, "source_id": x["source_id"], "locator": x["locator"], "quote": x["text"]}
                      for y in V.numbers(x["text"])]
        for e in ev:
            if not e["quote_verified"]:
                P.append({"item": e["claim_id"], "detail": "quote 未在原文命中，稿中需标注待核实",
                          "locator": f"{e['source_id']}#{e['locator']}"})
            changes.append({"change_id": f"C{len(changes) + 1:03d}", "section": e["section"],
                            "original_quote": e["quote"], "revised_quote": e["quote"],
                            "reason": "背景句直接取材" if e["section"] == "background" else "引用绑定/转述，未改事实",
                            "locator": f"{e['source_id']}#{e['locator']}"})
        rows, rate = V.verify_evidence(ev, sources)
        sec = {"background": bool(anchors), "related_work": bool(refs), "research_gap": bool(gaps),
               "contributions": bool(contribs)}
        wo = case.get("organizer_workorder") or case.get("organizer_edit_workorder") or []
        receipts = []
        for i, it in enumerate(wo if isinstance(wo, list) else [wo], 1):
            t = it if isinstance(it, str) else str(it.get("instruction") or it.get("task") or it.get("text")
                                                 or json.dumps(it, ensure_ascii=False))
            lo = t.lower()
            ok = (("引言" in t or "introduction" in lo) and sec["background"]) or \
                 (("相关工作" in t or "related work" in lo) and sec["related_work"]) or \
                 (("空白" in t or "gap" in lo) and sec["research_gap"]) or \
                 (("贡献" in t or "contribution" in lo) and sec["contributions"])
            receipts.append({"item": i, "instruction": t[:300], "status": "done" if ok else "pending_human",
                             "evidence": "section_present" if ok else "需人工确认该工单项落点"})
            if not ok:
                P.append({"item": f"workorder#{i}", "detail": t[:200]})
        if not sources:
            U.append({"item": "extraction", "detail": "无可抽取文本，引用均未核验"})
        U.append({"item": "citation_style", "detail": "目标期刊格式未给定，按 author-year 编号 + References 输出"})
        res.update({
            "case_id": cid, "stage": "done", "sections_present": sec, "citations": refs,
            "evidence_map": ev, "preserved_facts": facts, "gap_derivation": gaps, "changes": changes,
            "status": ("ok" if (refs and gaps and contribs and all(sec.values()) and rate >= 0.8)
                       else "insufficient_evidence" if not refs else "partial"),
            "deliverables": {k: f"{k}.md" for k in ("manuscript", "related_work_matrix")} | {
                k: f"{k}.json" for k in ("evidence_map", "preserved_facts", "change_log", "sources_index")},
            "groups": [{"route": g, "count": len(groups[g]), "members": [r["id"] for r in groups[g]]} for g in order],
            "contribution_alignment": [{"contribution_id": f"K{i:02d}", "text": c["text"],
                                        "aligned": V.find_quote(c["text"], sources.get(c["source_id"], "")),
                                        "locator": f"{c['source_id']}#{c['locator']}"}
                                       for i, c in enumerate(contribs, 1)],
            "coverage": {"references": len(refs), "routes": len([g for g in order if g != "unclassified"]),
                         "unclassified": len(groups.get("unclassified", [])),
                         "with_abstract": sum(1 for r in refs if r["abstract"]),
                         "metadata_complete": sum(1 for r in refs if r["metadata_status"] == "complete"),
                         "recent_3y": sum(1 for r in refs if r["year"].isdigit() and int(r["year"]) >= 2022),
                         "evidence_items": len(ev), "quote_verified_rate": rate,
                         "citation_markers_in_manuscript": len(re.findall(r"\[\d+\]", md)),
                         "manuscript_words": len(md.split()),
                         "preserved_facts": len(facts)},
            "workorder_receipts": receipts, "manuscript_text": md, "language": lang,
            "task_instruction": case.get("task_instruction") or case.get("instruction"),
            "verification": {"engine": "scripts/verify.py", "checked": len(rows), "quote_verified_rate": rate,
                             "failures": [r["claim_id"] for r in rows if not r["quote_verified"]][:20]}})
        for nm, ob in (("evidence_map", ev), ("preserved_facts", facts), ("change_log", changes)):
            wj(out / f"{nm}.json", ob)
    except Exception:
        E.append({"stage": "pipeline", "error": traceback.format_exc(limit=3)[-600:]})
    finally:
        res.update(errors=E, degradations=D, uncertainty=U, pending_human=P, sources=SRC)
        res.setdefault("manuscript_text", "")
        if not res.get("citations"):
            res["status"] = "input_error" if (E or not files) else "insufficient_evidence"
        res.setdefault("status", "partial")
        res = echo(res, ct)
        res.setdefault("case_id", cid)
        res.setdefault("runtime", {"skill_version": SK["version"], "started_at": st}).update(
            {"finished_at": now(), "output_dir": str(out),
             "contract_source": "case.json" if res.get("output_contract") else "default"})
        try:
            wj(out / "result.json", res)
        except Exception as exc:
            print(json.dumps({"fatal": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
    return 0


def _zh(*texts):
    t = " ".join(x for x in texts if x)
    if not t:
        return True
    return len(V.CJK.findall(t)) >= 0.12 * max(1, len(re.sub(r"\s", "", t)))


if __name__ == "__main__":
    sys.exit(main())
