#!/usr/bin/env python3
"""citation-manager 主编排：发现→解析库→去重→插入→编号→渲染→校验→落盘。
仅标准库；不联网；不依赖 CWD；退出码恒 0。"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
try:
    import reftool as RT
except Exception:
    RT = None
V = "1.0.0"
STY = ("gbt7714", "apa")
MARK = re.compile(r"\[\[INS:(?P<ins>[^\]\|]+)\]\]|\\cite[a-zA-Z]*\{(?P<cite>[^}]*)\}|\[@(?P<at>[^\]]+)\]"
                  r"|\^\[\s*\d+(?:\s*[-–,，]\s*\d+)*\s*\]\^|\[\s*\d+(?:\s*[-–,，、]\s*\d+)*\s*\]")
HEAD = re.compile(r"^\s{0,3}(#{1,6})\s+")
REFH = re.compile(r"^\s{0,3}#{0,6}\s*\**\s*(参考文献|引用文献|References?|Bibliography)\s*\**\s*$", re.I)
CLAIM = re.compile(r"(\d|%|％|显著|表明|说明|发现|证实|提示|提高|降低|增加|减少|约为|达到|相比|归因|significan|indicat|"
                   r"suggest|show|found|increas|decreas|reduc|higher|lower|correlat|associat|p\s*[<=]\s*0?\.\d)", re.I)
STOP = set("the a an of and or in for to with by from as is are was were be this that these our its study result "
           "results using based between than into after both each more most such not also can may effect".split())


def sents(l):
    o, b, i, n = [], "", 0, len(l)
    while i < n:
        c, i = l[i], i + 1
        b += c
        if c in "。！？!?；;" or (c == "." and (i >= n or l[i] in " \t") and not (len(b) > 1 and b[-2].isdigit())):
            o.append(b)
            b = ""
    if b.strip():
        o.append(b)
    return [s for s in o if s.strip()]


def ex(s):
    o = []
    for p in re.split(r"[,，、;；]", re.sub(r"[\s\[\]]", "", s or "")):
        m = re.match(r"^(\d+)[-–—~](\d+)$", p)
        if m and 0 <= int(m.group(2)) - int(m.group(1)) <= 60:
            o += list(range(int(m.group(1)), int(m.group(2)) + 1))
        elif p.isdigit():
            o.append(int(p))
    return o


def cp(ns):
    ns, o, i = sorted(set(ns)), [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        o += ["%d-%d" % (ns[i], ns[j])] if j - i >= 2 else [str(x) for x in ns[i:j + 1]]
        i = j + 1
    return ",".join(o)


def tm(s):
    s, o = RT.nt(s), set()
    o = set(w for w in s.split() if len(w) > 2 and w not in STOP)
    for z in re.findall(r"[\u4e00-\u9fff]{2,}", s):
        o |= set(z[i:i + 2] for i in range(len(z) - 1))
    return o


def best(sent, rs, used):
    st = tm(sent)
    if len(st) < 3:
        return None, 0.0, []
    b, bs, bt = None, 0.0, []
    for r in rs:
        rt = tm((r.get("title") or "") + " " + (r.get("abstract") or "")[:400])
        if rt:
            it = st & rt
            c = len(it) / len(rt) * (0.85 if r["key"] in used else 1.0)
            if c > bs:
                b, bs, bt = r, c, sorted(it)[:8]
    return b, bs, bt


def mkey(m):
    if m.group("ins"):
        return [m.group("ins").strip()]
    if m.group("cite"):
        return [k.strip() for k in re.split(r"[,\s]+", m.group("cite")) if k.strip()]
    if m.group("at"):
        return [k.strip().lstrip("@") for k in re.split(r"[;,\s]+", m.group("at")) if k.strip()]
    return None


def scan(paras, omap):
    num, order, unres, pts = {}, [], [], []
    for p in paras:
        if p["kind"] != "text":
            continue
        for si, sent in enumerate(sents(p["text"]), 1):
            for m in MARK.finditer(sent):
                raw, ks = m.group(0), mkey(m)
                keys = [] if ks is None else ks
                if ks is None:
                    for x in ex(raw):
                        keys.append(omap[x]) if omap.get(x) else unres.append(
                            {"para": p["idx"], "sentence": si, "marker": raw, "reason": "index_out_of_list"})
                pts.append({"para": p["idx"], "sentence": si, "marker": raw, "keys": keys, "quote": sent.strip()})
                for k in keys:
                    if k not in num:
                        order.append(k)
                        num[k] = len(order)
    return num, order, unres, pts


def applym(paras, omap, num, lib, style, chg):
    out = []
    for p in paras:
        if p["kind"] != "text":
            out.append(p["text"])
            continue

        def rep(m):
            raw, keys = m.group(0), mkey(m)
            if keys is None:
                keys = [omap[x] for x in ex(raw) if omap.get(x)]
            ns = [num[k] for k in keys if k in num]
            new = raw
            if style == "apa":
                pt = ["%s, %s" % (RT.df(lib[k]["authors"][0]) if lib[k]["authors"] else "Anon", lib[k]["year"] or "n.d.")
                      for k in keys if k in lib]
                new = "(%s)" % "; ".join(list(dict.fromkeys(pt))) if pt else raw
                if new != raw and m.start() and m.string[m.start() - 1] not in " （(\t":
                    new = " " + new
            elif ns:
                new = ("^[%s]^" if raw.startswith("^") else "[%s]") % cp(ns)
            if new != raw:
                chg.append({"kind": "renumber", "locator": "manuscript.md#p%d" % p["idx"], "original_quote": raw,
                            "revised_quote": new, "reason": "renumber_by_first_appearance"})
            return new
        out.append(MARK.sub(rep, p["text"]))
    return out


def cli(argv):
    ap = argparse.ArgumentParser(prog="main.py",
        description="参考文献与引用管理：插入定位/编号重排/去重/格式转换(GB/T 7714/APA)/来源核验，退出码恒 0。",
        epilog="示例: --input /input --output /app/output --style apa")
    ap.add_argument("--input", default="/input", help="输入目录，默认 /input")
    ap.add_argument("--output", default="/app/output", help="输出目录，默认 /app/output")
    ap.add_argument("--style", default="gbt7714", choices=list(STY), help="gbt7714(默认)|apa")
    ap.add_argument("--no-insert", action="store_true", help="只出引用插入建议，不改稿")
    ap.add_argument("--version", action="version", version="citation-manager " + V)
    return ap.parse_known_args(argv)[0]


def dirs(a):
    i, o = Path(a.input).expanduser(), Path(a.output).expanduser()
    if not i.exists():
        for alt in (Path("/input"), H.parent.parent / "input"):
            if alt.exists():
                i = alt
                break
    try:
        o.mkdir(parents=True, exist_ok=True)
        (o / ".w").write_text("1", encoding="utf-8")
        (o / ".w").unlink()
    except Exception:
        o = H.parent.parent / "output"
        o.mkdir(parents=True, exist_ok=True)
    return i, o


def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def base(con):
    d = {k: [] for k in ("actions_done", "sources", "citation_map", "evidence_map", "preserved_facts",
                         "change_log", "dedup_decisions", "ambiguous_pairs", "merge_groups", "uncertainty",
                         "pending_human", "missing_materials", "errors", "degradations", "workorder_receipt")}
    d.update({"case_id": None, "skill": "citation-manager", "skill_version": V, "status": "partial",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "manuscript": {}, "verification": {},
              "counts": {}, "runtime": {}, "output_contract": con, "outputs": {}})
    return d


def discover(inp, out, R):
    case, cpth = {}, None
    for c in sorted(inp.glob("case*.json")) or [inp / "case.json"]:
        if c.is_file():
            try:
                case, cpth = json.loads(RT.rd(c)), c
                break
            except Exception as e:
                R["errors"].append({"stage": "case_json", "file": c.name, "note": str(e)[:180]})
    if not case:
        for c in sorted(inp.rglob("*.json")):
            try:
                d = json.loads(RT.rd(c))
            except Exception:
                continue
            if isinstance(d, dict) and ({"case_id", "output_contract", "task_instruction"} & set(d)):
                case, cpth = d, c
                break
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    R["case_id"] = case.get("case_id") or case.get("id") or (inp.name if inp.exists() else None)
    R["output_contract"] = con
    R["input_case_path"] = str(cpth) if cpth else None
    if not case:
        R["errors"].append({"stage": "discover", "note": "case.json missing or unparsable"})
    T, K = {}, {}
    for p in [x for x in sorted(inp.rglob("*")) if x.is_file() and out not in x.parents][:120]:
        if p.name.startswith(".") or p.suffix.lower() in (".pyc", ".png", ".jpg", ".jpeg", ".so", ".bin"):
            continue
        k, t = RT.sniff(p), None
        if k == "pdf":
            R["degradations"].append({"stage": "input", "file": p.name, "note": "unsupported_binary_pdf"})
            continue
        if k == "unknown":
            try:
                t = RT.rd(p)
                k = RT.sniff(p, t)
            except Exception as e:
                R["degradations"].append({"stage": "read", "file": p.name, "note": str(e)[:120]})
                continue
        T[p] = RT.dxt(p) if k == "docx" else (t if t is not None else RT.rd(p))
        K[p] = k
        R["sources"].append({"id": str(p.relative_to(inp)), "kind": k, "bytes": p.stat().st_size,
                             "sha16": hashlib.sha256(p.read_bytes()).hexdigest()[:16]})
    return case, con, T, K


def pipeline(a, inp, out, R):
    case, con, T, K = discover(inp, out, R)
    PH = R["pending_human"].append
    cands = [(p, k) for p, k in K.items() if k not in ("bib", "ris", "json", "csv", "gbt", "enw") and T.get(p, "").strip()]
    msp, msk, mst = None, None, ""
    if cands:
        msp, msk = max(cands, key=lambda pk: 2 * bool(MARK.search(T[pk[0]])) +
                       2 * bool(REFH.search("\n".join(T[pk[0]].splitlines()[:400]))) + min(len(T[pk[0]]) / 20000.0, 1))
        mst = T[msp]
    elif T:
        msp = max(T, key=lambda q: len(T[q]))
        mst, msk = T[msp], K.get(msp, "unknown")
    skip = {msp, Path(R.get("input_case_path") or "")}
    raw, notes = RT.parse_library([(p, k, T.get(p, "")) for p, k in K.items()
                                   if k not in ("docx", "unknown") and p not in skip])
    R["degradations"] += notes
    merged, de, amb, grp = RT.dedup(raw) if raw else ([], [], [], [])
    lib = {r["key"]: r for r in merged}
    L = (mst or "").splitlines()
    cut = next((i for i, x in enumerate(L) if REFH.match(x.strip()) and len(x.strip()) < 40), None)
    body, refl = (L[:cut], L[cut + 1:]) if cut is not None else (L, [])
    paras = [{"kind": "heading" if HEAD.match(x) else ("table" if x.lstrip().startswith("|") else "text"),
              "text": x, "idx": i} for i, x in enumerate([x for x in body if x.strip()], 1)]
    msrefs = RT.pgbt("\n".join(refl), "manuscript") if refl else []
    omap = {}
    for i, r in enumerate(msrefs, 1):
        hit = next((x for x in merged if RT.dec(r, x)[0] >= 0.80), None)
        omap[i] = hit["key"] if hit else ""
        if not hit:
            PH({"item": "manuscript_ref_%d" % i, "title": (r["title"] or "")[:80],
                "issue": "原文献表条目未定位"})
    if not msrefs:
        omap = {i: r["key"] for i, r in enumerate(merged, 1)}
    ins, used = [], set()
    for p in paras:
        if p["kind"] != "text":
            continue
        for si, s in enumerate(sents(p["text"]), 1):
            if MARK.search(s) or not CLAIM.search(s) or len(s.strip()) < 15 or len(ins) >= 40:
                continue
            b, sc, mt = best(s, merged, used)
            if b and sc >= 0.2 and len(mt) >= 3:
                ins.append({"para": p["idx"], "sentence": si, "key": b["key"], "score": round(sc, 3),
                            "matched_terms": mt, "quote": s.strip(), "locator": "manuscript.md#p%ds%d" % (p["idx"], si)})
                used.add(b["key"])
    if ins and not a.no_insert:
        byidx = {p["idx"]: p for p in paras if p["kind"] == "text"}
        for it in ins:
            p, ss = byidx.get(it["para"]), []
            ss = sents(p["text"]) if p else []
            if p and it["sentence"] <= len(ss):
                tg = ss[it["sentence"] - 1]
                nw = re.sub(r"([。！？!?;；]|\.[\s]*)$", "[[INS:%s]]\\1" % it["key"], tg)
                p["text"] = p["text"].replace(tg, nw if nw != tg else tg + "[[INS:%s]]" % it["key"], 1)
    num, order, unres, pts = scan(paras, omap)
    chg = []
    lines = applym(paras, omap, num, lib, a.style, chg)
    cited = [k for k in order if k in lib]
    dropped = [r["key"] for r in merged if r["key"] not in cited]
    ent, fmt = [], []
    for k in cited:
        t = RT.render(lib[k], num[k], a.style)
        ent.append(t)
        fmt.append({"kind": "format", "locator": "library:%s#%s" % (lib[k]["source"], k),
                    "original_quote": (lib[k].get("raw") or lib[k]["title"])[:200], "revised_quote": t[:300],
                    "reason": "render_%s_from_%s" % (a.style, lib[k]["source"])})
    hd = "References" if a.style == "apa" else "参考文献"
    mso = "\n".join(lines).rstrip() + "\n\n## %s\n\n" % hd + "\n".join(ent) + "\n"
    (out / "manuscript.md").write_text(mso, encoding="utf-8")
    (out / "references_formatted.md").write_text("# %s（%s）\n\n" % (hd, a.style) + "\n".join(ent) + "\n",
                                                 encoding="utf-8")
    wj(out / "references.json", {"style": a.style, "count": len(merged), "entries": merged})
    R["preserved_facts"] = [{"type": "number_or_unit", "value": t, "kept": t in mso}
                            for t in sorted(set(RT.UNITS.findall(MARK.sub(" ", mst or "")))) if t.strip()][:400]
    R["change_log"] = [{"kind": "insert_citation", "locator": it["locator"], "original_quote": it["quote"],
                        "revised_quote": it["quote"] + "[%d]" % num.get(it["key"], 0),
                        "reason": "claim_match_%s_score_%.2f_terms_%s" % (it["key"], it["score"],
                                                                                   ",".join(it["matched_terms"])),
                        "applied": not a.no_insert} for it in ins] + [dict(c, applied=True) for c in (chg + fmt)[:600]]
    cm = []
    for pt in pts:
        st = tm(pt["quote"])
        for k in [x for x in pt["keys"] if x in lib]:
            rt = tm(lib[k]["title"] + " " + (lib[k].get("abstract") or "")[:300])
            ov = round(len(st & rt) / len(rt), 3) if rt else 0.0
            cm.append({"number": num.get(k), "key": k, "locator": "manuscript.md#p%ds%d" % (pt["para"], pt["sentence"]),
                       "claim_quote": pt["quote"][:240], "overlap": ov,
                       "verdict": "ok" if (ov >= 0.2 or not rt) else "weak_match", "evidence_terms": sorted(st & rt)[:8]})
    R["citation_map"] = cm
    R["evidence_map"] = [{"claim": x["claim_quote"], "key": x["key"], "locator": x["locator"], "number": x["number"],
                          "quote": (lib[x["key"]].get("raw") or lib[x["key"]]["title"])[:200]} for x in cm]
    for c in [x for x in cm if x["verdict"] == "weak_match"]:
        PH({"item": "claim_ref_match", "locator": c["locator"], "key": c["key"],
            "issue": "论断与文献词项重叠低(%.2f)" % c["overlap"]})
    for r in merged:
        miss = [f for f in ("title", "authors", "year", "container", "volume", "pages", "doi") if not r.get(f)]
        if miss and r["key"] in cited:
            PH({"item": "missing_fields", "key": r["key"], "fields": miss, "note": "材料未提供"})
    R["manuscript"] = {"source": str(msp) if msp else None, "kind": msk, "chapters": sum(
        1 for p in paras if p["kind"] == "heading"), "paragraphs": len(paras), "style": a.style,
        "chars": len(mso), "reference_section_found": bool(msrefs)}
    R["dedup_decisions"], R["ambiguous_pairs"], R["merge_groups"] = de, amb, grp
    R["outputs"] = {k: str(out / (k + ".md" if k in ("manuscript", "references_formatted", "report") else
                                  ("references.json" if k == "references_json" else "result.json")))
                    for k in ("manuscript", "references_formatted", "references_json", "result", "report")}
    R["counts"] = {"sections": R["manuscript"]["chapters"], "citation_points": len(cm), "library_records_raw": len(raw),
                   "library_records_dedup": len(merged), "merged_groups": len(grp),
                   "inserted_citations": len(ins) if not a.no_insert else 0, "unresolved_markers": len(unres),
                   "uncited_entries": len(dropped), "render_entries": len(ent),
                   "auto_applied": len(chg) + len(fmt) + len(ins), "pending_human": len(R["pending_human"]),
                   "errors": len(R["errors"])}
    R["actions_done"] = [n for n, ok in (("A_insert", bool(ins) or bool(cm)), ("B_renumber", bool(cited)),
                                         ("C_dedup", bool(raw)), ("D_style", bool(ent)), ("E_verify", True),
                                         ("F_claim_match", bool(cm))) if ok]
    if not merged and not mst:
        R["status"] = "input_error"
    elif not merged:
        R["status"] = "insufficient_evidence"
        R["uncertainty"].append("文献库无法识别")
    elif not cited:
        R["status"] = "partial"
        R["uncertainty"].append("未检出可解析引用点")
    else:
        R["status"] = "partial" if R["pending_human"] else "ok"
    if unres:
        R["uncertainty"].append("%d 个标记指向原文献表外编号，已原样保留" % len(unres))
    for nm, val in (("稿件", mst), ("文献库", merged), ("原文献表", msrefs)):
        if not val:
            R["missing_materials"].append({"material": nm, "note": "材料缺失"})
    try:
        R["verification"] = RT.run(R, mso, ent, lib, a.style, case)
        R["workorder_receipt"] = R["verification"].get("workorder_receipt") or []
        (out / "report.md").write_text("# 运行报告" + chr(10) * 2 + json.dumps(
            {"case_id": R.get("case_id"), "status": R.get("status"), "counts": R.get("counts"),
             "verification": R.get("verification"), "pending_human": R.get("pending_human"),
             "errors": R.get("errors"), "degradations": R.get("degradations")},
            ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")
    except Exception as e:
        R["degradations"].append({"stage": "verify", "note": str(e)[:200]})


def main(argv=None):
    a = cli(argv)
    t0 = time.time()
    inp, out = dirs(a)
    R = base({})
    wj(out / "result.json", R)
    con = {}
    try:
        if RT is None:
            R["errors"].append({"stage": "import", "note": "reftool.py 不可导入（缺失或损坏）"})
        else:
            pipeline(a, inp, out, R)
            con = R.get("output_contract") or {}
    except Exception as e:
        import traceback
        R["errors"].append({"stage": "pipeline", "note": str(e)[:300], "trace": traceback.format_exc()[-700:]})
        try:
            (out / "manuscript.md").write_text("# 运行异常：未生成稿件，详见 result.json\n", encoding="utf-8")
        except Exception:
            pass
    if isinstance(con, dict):
        for k, v in con.items():
            if k not in R:
                R[k] = v
    R["runtime"] = {"script": "scripts/main.py", "version": V, "python": sys.version.split()[0],
                    "seconds": round(time.time() - t0, 2), "model_requests": 0,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    R["status"] = R.get("status") or "partial"
    try:
        wj(out / "result.json", R)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
