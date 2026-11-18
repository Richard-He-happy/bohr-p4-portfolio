#!/usr/bin/env python3
"""bilin-paper-translator: prepare -> (translate) -> finalize（标准库/离线/退出码0/异常入 result.json）。"""
import argparse, hashlib, json, os, sys, time, traceback
from pathlib import Path

H = Path(__file__).resolve().parent
PKG = H.parent
sys.path.insert(0, str(H))
try:
    import engine as E
    PE = ""
except Exception as _e:
    E, PE = None, str(_e)
SK, SV = "bilin-paper-translator", "1.0.0"
TS = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
SKEL = ('{"skill":{"name":"%s","version":"%s"},"case_id":null,"status":"partial","status_reason":"占位",'
        '"task":{"instruction":"","scope":"","target_language":"zh-CN"},"output_contract":null,'
        '"translation":{"target_language":"zh-CN","source_document":null,"extraction_method":null,'
        '"segmentation":{},"paragraphs":[],"coverage":{},"token_fidelity":{},"source_text":""},'
        '"glossary":{"rows":[],"locked":0,"consistency":{}},"claims":[],"sources":[],"segments":[],'
        '"artifacts":[],"coverage":{},"verification":{},"uncertainty":[],"pending_human":[],"errors":[],'
        '"degradations":[],"changes":[],"runtime":{}}')


def pdir(cands, mk=False):
    for x in cands:
        if x:
            p = Path(x).expanduser()
            try:
                if mk:
                    p.mkdir(parents=True, exist_ok=True)
                if p.is_dir():
                    return p.resolve()
            except Exception:
                pass
    fb = (PKG / ("output" if mk else "input")).resolve()
    fb.mkdir(parents=True, exist_ok=True)
    return fb


def dfind(n, keys, d=0):
    if d > 4 or n is None:
        return None
    if isinstance(n, dict):
        for k, v in n.items():
            if any(x in str(k).lower() for x in keys) and not isinstance(v, (dict, list)) and v not in (None, ""):
                return v
        n = list(n.values())
    if isinstance(n, list):
        for v in n:
            r = dfind(v, keys, d + 1)
            if r is not None:
                return r
    return None


def crawl(ip):
    out, rk = [], {"pdf": 4, "docx": 3, "text": 2, "html": 2, "csv": 1, "json": 1}
    for p in sorted(ip.rglob("*")):
        rel = str(p.relative_to(ip)).replace("\\", "/")
        if not p.is_file() or rel.lower() in ("case.json", "task.md") or "/output/" in rel or "/work/" in rel:
            continue
        out.append({"path": str(p), "rel": rel, "bytes": p.stat().st_size,
                    "kind": E.KINDS.get(p.suffix.lower()) or "unknown"})
    good = sorted([x for x in out if rk.get(x["kind"])], key=lambda x: (-rk[x["kind"]], -x["bytes"]))
    return out, (good[0] if good else None)


def save(c, res, t0):
    if E is not None:
        E.fillc(res)
    res["errors"], res["degradations"] = c["err"], c["deg"]
    res["runtime"] = {"started": c["start"], "updated": TS(), "elapsed_s": round(time.time() - t0, 2),
                      "python": sys.version.split()[0], "argv": c["argv"], "network": "disabled",
                      "input_dir": str(c["input"]), "output_dir": str(c["output"]), "work_dir": str(c["work"])}
    res["artifacts"] = [{"file": p.name, "bytes": p.stat().st_size,
                         "sha1": hashlib.sha1(p.read_bytes()).hexdigest()[:16]}
                        for p in sorted(c["output"].glob("*")) if p.is_file() and p.name != "result.json"]
    try:
        E.jsave(res, c["output"] / "result.json")
    except Exception:
        (c["output"] / "result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")


def gload(c):
    """term->译名：case 表 → 输入目录表 → work/glossary.csv"""
    g, case = {}, c["case"]
    raw = next((case[k] for k in ("glossary", "terminology", "term_list", "glossary_seed", "terms")
                if isinstance(case.get(k), (dict, list))), None)
    for p in ((c["input"] / "glossary.csv", c["input"] / "glossary.json") if raw is None else ()):
        if p.is_file():
            raw = E.read_text(p) if p.suffix == ".csv" else E.jload(p, None)
    pairs = list(raw.items()) if isinstance(raw, dict) else [
        (x.get("term") or x.get("source"), x.get("translation") or x.get("target") or "")
        for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []
    for k, v in pairs:
        if isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip():
            g[k.strip()] = v.strip()
    for r in E.read_csv(c["work"] / "glossary.csv"):
        if (r.get("term") or "").strip() and (r.get("translation") or "").strip():
            g[r["term"].strip()] = r["translation"].strip()
    return g


def prep(c, res):
    ip, tr = c["input"], res["translation"]
    cp = None
    for pat in ("case.json", "case*.json", "**/case*.json"):
        cp = next((p for p in sorted(ip.glob(pat)) if p.is_file() and isinstance(E.jload(p, None), dict)), None)
        if cp:
            break
    case = c["case"] = E.jload(cp, {}) if cp else {}
    if not cp:
        bad = [p for pat in ("case.json", "case*.json", "**/case*.json")
               for p in sorted(ip.glob(pat)) if p.is_file()]
        if bad:
            c["err"].append({"stage": "discover", "error": "case.json 非法 JSON，已忽略并继续用其他材料",
                             "file": str(bad[0])})
    res["case_id"] = case.get("case_id") or dfind(case, ["case_id", "case"])
    task = next((E.read_text(p) for p in (ip / "task.md",) if p.is_file()), "")
    res["task"]["instruction"] = dfind(case, ["task_instruction", "instruction", "prompt", "task", "request"]) or task[:1000]
    res["task"]["scope"] = dfind(case, ["scope", "range", "boundary"]) or ""
    res["output_contract"] = case.get("output_contract")
    mat, prim = crawl(ip)
    res["sources"] = [dict(x, source_id="S%d" % (i + 1)) for i, x in enumerate(mat)]
    if not prim:
        c["err"].append({"stage": "discover", "error": "无可解析材料" if mat else "未发现材料",
                         "kinds": sorted({x["kind"] for x in mat})})
        res["status"], res["status_reason"] = "input_error", "输入缺失/不可解析"
        return
    c["doc"], w = prim, []
    if c["txt"]:
        bl, how = [{"page": None, "text": E.read_text(c["txt"])}], "agent-supplied-text"
    else:
        try:
            bl, how = E.extract(prim["path"], prim["kind"], w)
        except Exception as e:
            c["err"].append({"stage": "extract", "error": str(e), "file": prim["rel"]})
            bl, how = [{"page": None, "text": ""}], "failed"
    prim["method"] = how
    c["deg"] += [{"stage": "extract", "file": prim["rel"], "note": x} for x in w]
    segs = c["segs"] = E.segment(bl)
    txt = "\n\n".join(s["text"] for s in segs)
    tr.update(source_text=txt, extraction_method=how, source_document=prim["rel"],
              segmentation={"rule": "空行/标题/题注/公式/参考文献切分；段内软换行合并；段号 P### 稳定",
                            "anchor": "seg_id + page + kind + section", "paragraphs": len(segs),
                            "sentences": sum(len(s["sents"]) for s in segs)})
    E.jsave(segs, c["work"] / "segments.json")
    res["segments"] = [{"seg_id": s["id"], "page": s["page"], "kind": s["kind"]} for s in segs]
    L = ["# 原文分段（P### 稳定，勿重排）| %s | %s" % (prim["rel"], how), ""]
    for s in segs:
        L += ["### %s · %s · %s · %s" % (s["id"], "none" if s["page"] is None else "p.%s" % s["page"],
                                         s["kind"], s["section"] or "-"), s["text"], ""]
    (c["work"] / "source_units.md").write_text("\n".join(L), encoding="utf-8")
    rows = {r["term"]: r for r in E.build_glossary(txt, segs, 60)}
    for t, v in gload(c).items():
        rows.setdefault(t, {"term": t, "translation": "", "category": "supplied", "expansion": "",
                            "freq": txt.count(t), "first_seg": "", "first_page": "", "status": ""}
                     ).update({"translation": v, "status": "locked"})
    rows = sorted(rows.values(), key=lambda r: (-r["freq"], r["term"]))
    keys = ["term", "translation", "category", "expansion", "freq", "first_seg", "first_page", "status"]
    E.write_csv(c["work"] / "glossary.csv", keys, [[r[k] for k in keys] for r in rows])
    res["glossary"] = {"rows": [{"term": r["term"], "translation": r["translation"], "freq": r["freq"],
                                 "status": r["status"]} for r in rows],
                       "locked": sum(1 for r in rows if r["translation"]),
                       "counts": {"candidates": len(rows)}, "template": "work/glossary.csv"}
    if not E.usable(txt):
        c["deg"].append({"stage": "extract", "note": "抽取文本可读字符不足，疑文字层缺失"})
        res["uncertainty"].append({"id": "U1", "type": "text_layer",
                                   "detail": "抽取 %d 字符，可读性低，段界可能不可靠" % len(txt),
                                   "affected": "全部段落", "action": "人工/OCR 校对后 prepare --text 重建"})
    build(c, res, {})
    res["status"], res["status_reason"] = "partial", "已分段"
    res["changes"].append({"ts": TS(), "stage": "prepare", "action": "extract+segment",
                           "detail": "材料 %d；主材料 %s(%s)；段落 %d" % (len(mat), prim["rel"], how, len(segs))})
    E.jsave(dict(cid=res["case_id"], task=res["task"], oc=res["output_contract"], src=res["sources"],
                 doc=c["doc"], segi=res["segments"], sd=tr["source_document"], em=tr["extraction_method"],
                 sg=tr["segmentation"], gc=res["glossary"].get("counts"), gt=res["glossary"].get("template"),
                 err=c["err"], deg=c["deg"], unc=res["uncertainty"], chg=res["changes"]),
            c["work"] / "state.json")


def tobj(d):
    if isinstance(d, dict) and isinstance(d.get("translations"), (dict, list)):
        d = d["translations"]
    src = list(d.items()) if isinstance(d, dict) else [(x.get("id"), x) for x in d if isinstance(x, dict)] \
        if isinstance(d, list) else []
    out = {}
    for k, v in src:
        val = v if isinstance(v, str) else (v.get("translation") or v.get("译文") or "" if isinstance(v, dict) else "")
        if k and isinstance(val, str) and val.strip():
            out[str(k).strip()] = val.strip()
    return out


def tload(c):
    cands = [Path(x) for x in c["trs"]]
    for b in (c["output"], c["work"]):
        for pat in ("translations*.json", "translation_*.json", "translations/*.json"):
            cands += sorted(b.rglob(pat))
    tr, used, seen = {}, [], set()
    for p in cands:
        if p.is_file() and str(p) not in seen:
            seen.add(str(p))
            got = tobj(E.jload(p, {}) or {})
            tr.update(got)
            used += [str(p)] if got else []
    return tr, used


def build(c, res, trs):
    segs, tr = c["segs"], res["translation"]
    lock = {k: v for k, v in gload(c).items() if v}
    sm = {s["id"]: s["text"] for s in segs}
    ps, exp, kept, gopp, gv, flag = [], 0, 0, 0, 0, 0
    for s in segs:
        tx = (trs.get(s["id"]) or "").strip()
        p = {"seg_id": s["id"], "page": s["page"], "kind": s["kind"], "section": s["section"],
             "status": "translated" if tx else "untranslated", "translation": tx,
             "src_chars": len(s["text"]), "src_excerpt": s["text"][:160]}
        if tx:
            k = E.check_seg(s["text"], tx, lock)
            exp, kept, gopp, gv = exp + k["exp"], kept + k["kept"], gopp + k["gopp"], gv + len(k["gviol"])
            flag += bool(k["flags"])
            p.update(kept=k["kept"], expected=k["exp"], terms=k["gopp"], gviol=k["gviol"], flags=k["flags"],
                     missing=k["miss"], ratio=round(len(tx) / max(1, len(s["text"])), 3))
        else:
            p.update(kept=0, expected=0, terms=0, gviol=[], flags=["untranslated"], missing={}, ratio=None)
        ps.append(p)
    refs = sum(1 for p in ps if p["kind"] == "reference")
    done = [p for p in ps if p["status"] == "translated" and p["kind"] != "reference"]
    cov = {"paragraphs": len(ps) - refs, "translated": len(done), "references_preserved": refs,
           "coverage_rate": round(len(done) / (len(ps) - refs), 4) if ps else 0.0,
           "translated_chars": sum(len(p["translation"]) for p in done)}
    rate = round(kept / exp, 4) if exp else None
    tr.update(paragraphs=ps, coverage=cov,
              token_fidelity={"expected": exp, "kept": kept, "missing": exp - kept, "rate": rate})
    res["coverage"] = {"coverage_rate": cov["coverage_rate"], "paragraphs": len(ps), "translated": len(done),
                       "token_rate": rate, "segments_with_flags": flag}
    cons = round(1 - gv / gopp, 4) if gopp else None
    res["glossary"].update({"locked": len(lock),
                            "consistency": {"opportunities": gopp, "violations": gv, "rate": cons,
                                            "method": "锁定术语在原文出现时译文须含该译名（忽略空白/连字符）"},
                            "rows": [{"term": t, "translation": lock[t],
                                      "freq": sum(1 for s in segs if E.term_hit(t, s["text"])),
                                      "violation_seg_ids": [p["seg_id"] for p in ps if t in p["gviol"]],
                                      "status": "locked"} for t in sorted(lock)]})
    E.emit(c, res)


def fin(c, res):
    if not c["segs"]:
        c["segs"] = E.jload(c["work"] / "segments.json", []) or []
    if not c["segs"]:
        c["err"].append({"stage": "finalize", "error": "无 segments（prepare 未成功）"})
        if any(e.get("stage") == "discover" for e in c["err"]):
            res["status"], res["status_reason"] = "input_error", "输入缺失/不可解析"
        else:
            res["status"], res["status_reason"] = "partial", "缺分段结果"
        return
    st = E.jload(c["work"] / "state.json", None)
    if isinstance(st, dict):
        res["case_id"] = res["case_id"] or st.get("cid")
        if res["output_contract"] is None:
            res["output_contract"] = st.get("oc")
        res["task"] = st.get("task") or res["task"]
        res["sources"] = res["sources"] or st.get("src") or []
        res["segments"] = res["segments"] or st.get("segi") or []
        c["doc"] = c["doc"] or st.get("doc") or {}
        if not res["translation"].get("source_document"):
            res["translation"]["source_document"] = st.get("sd")
        if not res["translation"].get("extraction_method"):
            res["translation"]["extraction_method"] = st.get("em")
        if not res["translation"].get("segmentation"):
            res["translation"]["segmentation"] = st.get("sg") or {}
        res["glossary"].setdefault("counts", st.get("gc"))
        res["glossary"].setdefault("template", st.get("gt"))
        c["err"] = c["err"] or st.get("err") or []
        c["deg"] = c["deg"] or st.get("deg") or []
        res["uncertainty"] = res["uncertainty"] or st.get("unc") or []
        res["changes"] = res["changes"] or st.get("chg") or []
    if not res["translation"]["source_text"]:
        res["translation"]["source_text"] = "\n\n".join(s["text"] for s in c["segs"])
    if res["case_id"] is None or res["output_contract"] is None:
        cp = next((p for pat in ("case.json", "case*.json", "**/case*.json")
                   for p in sorted(c["input"].glob(pat)) if p.is_file()
                   and isinstance(E.jload(p, None), dict)), None)
        case = c["case"] = E.jload(cp, {}) if cp else {}
        res["case_id"] = case.get("case_id") or dfind(case, ["case_id", "case"])
        res["output_contract"] = case.get("output_contract")
    trs, used = tload(c)
    res["translation"]["translation_inputs"] = used
    if not used:
        res["uncertainty"].append({"id": "U2", "type": "no_translation_input",
                                   "detail": "未找到 translations*.json（键 P###）", "affected": "全部段落",
                                   "action": "按 work/source_units.md 产出译文后重跑 finalize"})
    E.fillc(res)
    build(c, res, trs)
    cov, tf = res["translation"]["coverage"], res["translation"]["token_fidelity"]
    cons, pgs = res["glossary"]["consistency"], res["translation"]["paragraphs"]
    rej = sorted({k["id"] for k in res["claims"] for e in k["evidence"]
                  if E.quote_status(e["quote"], E.norm(res["translation"]["source_text"]))
                  not in ("exact", "casefold")})
    miss = [k for k in E.shp(res.get("output_contract") or {}) if k not in res]
    dup = len(pgs) - len({p["seg_id"] for p in pgs})
    ok = {"C1_contract": not miss, "C2_anchor": all(p["seg_id"] for p in pgs),
          "C3_coverage": cov["coverage_rate"] >= 0.999 and not dup,
          "C4_tokens": tf["rate"] is None or tf["rate"] >= 0.9,
          "C5_glossary": res["glossary"]["locked"] > 0 and (cons["rate"] is None or cons["rate"] >= 0.8),
          "C6_claims": not rej,
          "C7_artifacts": all((c["output"] / f).is_file() for f in
                              ("translation_bilingual.md", "alignment.csv", "glossary.csv"))}
    res["verification"] = {"passed": all(ok.values()), "checks": ok,
                           "summary": {"segments": cov["paragraphs"], "translated": cov["translated"],
                                       "coverage_rate": cov["coverage_rate"], "token_rate": tf["rate"],
                                       "glossary_locked": res["glossary"]["locked"],
                                       "glossary_rate": cons["rate"], "claims": len(res["claims"]),
                                       "claims_rejected": len(rej), "contract_missing": miss,
                                       "segments_with_flags": res["coverage"]["segments_with_flags"]},
                           "rejected_claim_ids": rej,
                           "heuristics": ["否定/限定计数比对为启发式，可能误报，仅进 pending_human",
                                          "长度比 <0.12 或 >1.6 提示可能漏译/扩写"]}
    E.jsave(res["verification"], c["output"] / "verification.json")
    if not cov["translated"]:
        res["status"], res["status_reason"] = "partial", "无译文输入"
    elif cov["coverage_rate"] < 0.999 or (tf["rate"] or 1.0) < 0.9:
        res["status"], res["status_reason"] = "partial", "覆盖 %d/%d 标记保真 %s" % (
            cov["translated"], cov["paragraphs"], "NA" if tf["rate"] is None else "%.1f%%" % (100 * tf["rate"]))
    else:
        res["status"], res["status_reason"] = "ok", "全段落已译，标记保真与术语一致率达标"
    if not E.usable(res["translation"]["source_text"]):
        res["status"] = res["status"] if cov["translated"] else "insufficient_evidence"
        res["status_reason"] += "；文字层可读性低，段界需人工复核"
    res["changes"].append({"ts": TS(), "stage": "finalize", "action": "ingest+verify",
                           "detail": "译文源 %d 覆盖 %d/%d status=%s" % (len(used), cov["translated"],
                                                                   cov["paragraphs"], res["status"])})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                description="文献段落对齐双语翻译：术语锁定 + 标记保护 + 自校验（标准库/离线/退出码0）",
                                epilog='示例（示例，非正式案例结果）：main.py prepare → 填 work/glossary.csv '
                                       '的 translation 列 → 写 work/translations/p1.json '
                                       '={"P001":"译文"} → main.py finalize')
    ap.add_argument("cmd", nargs="?", default="run", choices=["prepare", "finalize", "run"], help="默认 run")
    ap.add_argument("--input", help="输入目录（默认 /input）")
    ap.add_argument("--output", help="输出目录（默认 /app/output）")
    ap.add_argument("--work", help="中间目录（默认 /app/work）")
    ap.add_argument("--text", help="人工/OCR 校对后的全文")
    ap.add_argument("--translations", nargs="*", default=[], help="译文 JSON")
    a = ap.parse_args(argv)
    t0 = time.time()
    try:
        c = {"argv": " ".join(sys.argv[1:]), "start": TS(), "err": [], "deg": [], "case": {}, "segs": [],
             "doc": {}, "txt": Path(a.text).resolve() if a.text else None,
             "trs": [str(Path(x).resolve()) for x in a.translations],
             "input": pdir([a.input, os.environ.get("INPUT_DIR"), "/input", str(PKG / "input")]),
             "output": pdir([a.output, os.environ.get("OUTPUT_DIR"), "/app/output", str(PKG / "output")], True),
             "work": pdir([a.work, os.environ.get("WORK_DIR"), "/app/work", str(PKG / "work")], True)}
    except Exception as e:
        try:
            fb = PKG / "output"
            fb.mkdir(parents=True, exist_ok=True)
            (fb / "result.json").write_text(json.dumps(
                {"status": "partial", "status_reason": "初始化失败", "case_id": None,
                 "errors": [{"stage": "init", "error": str(e)}]}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return 0
    res = json.loads(SKEL % (SK, SV))
    if E is None:
        c["err"].append({"stage": "import", "error": "engine.py 加载失败: %s" % PE})
        res["status"], res["status_reason"] = "partial", "依赖模块不可用"
        save(c, res, t0)
        return 0
    save(c, res, t0)
    for stage, fn in (("prepare", prep), ("finalize", fin)):
        if a.cmd in (stage, "run"):
            try:
                fn(c, res)
            except Exception as e:
                c["err"].append({"stage": stage, "error": str(e), "trace": traceback.format_exc(limit=3)})
                res["status"], res["status_reason"] = "partial", "%s 异常，保留已达产物" % stage
            save(c, res, t0)
    if time.time() - t0 > 780:
        c["deg"].append({"stage": "run", "note": "接近时间预算，提前收尾"})
    save(c, res, t0)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(0)
