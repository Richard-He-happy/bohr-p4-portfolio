#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review-05 academic-compliance review: scaffold -> adjudicate -> finalize."""
import argparse, csv, hashlib, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import extract as X
    IMP = ""
except Exception as e:
    X, IMP = None, str(e)
V = "1.0.0"
SEP = chr(10)
SEV = {"blocker": "阻断", "major": "重要", "minor": "次要", "suggestion": "建议"}
FAC = {"F": "fact_verification", "C": "citation_support", "M": "method_design", "S": "statistical_reporting",
       "A": "argument_chain", "N": "academic_norms"}
FPAT = r"""eth=ethic[sa]?\s+(?:approval|committee|review);;institutional review board;;\bIRB\b;;伦理(?:委员会|审查);;informed consent;;知情同意
apno=\bIRB[\s\-_]*[A-Z]{0,4}[\s\-_]*\d{2,};;审批[^\n]{0,12}(?:编号|号)[^\n]{0,8}\w{3,}
hum=\bparticipants?\b;;\bpatients?\b;;\bvolunteers?\b;;human subjects?;;受试者;;患者
ani=\bmice\b;;\brats?\b;;animal experiment;;小鼠;;大鼠;;动物实验
coi=conflicts?\s+of\s+interest;;competing interests?;;利益冲突
fund=\bfunding\b;;supported by;;grant (?:no|number|#);;基金;;资助
da=data availability;;availability of (?:data|code);;数据(?:可用性|可获取)
tp=reproduced (?:from|with);;adapted (?:from|with);;courtesy of;;转载;;改编自;;©;;creative commons;;\bCC[- ]BY\b
perm=with permission;;permission (?:was )?(?:obtained|granted);;许可;;授权
test=\bt[\s-]?test\b;;\bANOVA\b;;chi-?squared?;;Mann[\s-]Whitney;;Wilcoxon;;regression;;log[\s-]?rank;;Fisher;;检验;;卡方
sd=\bSEM?\b;;\bSD\b;;standard deviation;;standard error;;标准差;;标准误
rand=random(?:ly)?\s+(?:assign|allocat|divid|select);;随机(?:分为|分组|分配|抽取)
blind=\bblind;;盲法;;双盲
soft=(?:version|v)\s?\d+\.\d+;;software;;python;;SPSS;;GraphPad"""

def wjson(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding="utf-8")



def rjson(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))



def cwords(s):
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9\-'./%]*", s)) + len(re.findall(r"[\u4e00-\u9fff]", s))


def features(C):
    t = C["full"]
    f = {"chars": len(t), "words": cwords(t), "pv": re.findall(r"[pP]\s*[<>=≤≥]\s*0?\.\d+", t), "pm": "±" in t}
    for line in FPAT.strip().split(SEP):
        k, pats = line.split("=", 1)
        f[k] = any(re.search(p, t, re.I | re.M) for p in pats.split(";;"))
    f["ns"] = re.findall(r"\bn\s*=\s*\d+", t, re.I) + re.findall(r"(\d+)\s*(?:名|例|位)\s*(?:受试者|患者|参与者)", t)
    f["mail"] = re.findall(r"[\w.+-]{2,}@[\w-]+\.[\w.]{2,}", t)
    f["tel"] = re.findall(r"(?<!\d)1[3-9]\d{9}(?!\d)", t)
    f["pid"] = re.findall(r"(?:身份证|ID\s*(?:no\.?|number))[^\d\n]{0,6}\d{6}[0-9Xx]{0,12}", t, re.I)
    return f

def find_contract(o, d=0):
    if d > 10 or not isinstance(o, (dict, list)):
        return None
    if isinstance(o, dict):
        hit = [(k, v) for k, v in o.items()
               if re.sub(r"[^a-z]", "", str(k).lower()) in ("outputcontract", "resultcontract", "contract")]
        if hit:
            return hit[0]
        o = list(o.values())
    for v in o:
        r = find_contract(v, d + 1)
        if r:
            return r
    return None



def fill_contract(r, keys):
    out, un, a = {}, [], r["artifacts"]
    mp = (("issue", "issues"), ("finding", "issues"), ("check", "checks"), ("facet", "checks"), ("source", "sources"),
          ("material", "sources"), ("uncertain", "uncertainty"), ("pending", "pending_human"), ("human", "pending_human"),
          ("status", "status"), ("caseid", "case_id"), ("runtime", "runtime"), ("error", "errors"),
          ("summary", "summary"), ("count", "summary"), ("stat", "summary"))
    for k in keys:
        n = re.sub(r"[^a-z]", "", k.lower())
        v = next((r[v2] for t, v2 in mp if t in n), None)
        if "csv" in n:
            v = a.get("issues_csv")
        elif "report" in n or "md" in n:
            v = a.get("review_report_md")
        if v is None:
            un.append(k)
        out[k] = v
    return out, un

def ckeys(cv):
    if isinstance(cv, dict):
        return [str(k) for k in cv]
    return [x if isinstance(x, str) else str(x.get("field") or x.get("name") or next(iter(x.values()), ""))
            for x in cv or []]


def base():
    return {"skill_version": V, "case_id": None, "status": "partial",
            "summary": {}, "issues": [], "checks": {}, "pending_human": [], "sources": [],
            "uncertainty": [], "review_records": {}, "errors": [], "degradations": [], "changes": [],
            "artifacts": {}, "runtime": {}, "contract_fields": {"requested": [], "filled": [], "unfilled": []}}


def blank(note):
    return dict((k, {"status": "not_checked", "scope": "", "notes": note, "findings": 0,
                     "unresolved": []}) for k in X.FKEYS)


def add_source(C, sid, name, path, kind, txt):
    C["sources"].append(dict(sid=sid, name=name, path=path, kind=kind, chars=len(txt),
                             sha256_12=hashlib.sha256(txt.encode()).hexdigest()[:12],
                             status="parsed" if txt else "unreadable"))
    if txt:
        C["docs"][sid] = {"text": txt}
        X.build_units(C, sid, txt, kind)


def uniq_sid(b, used):
    sid, i = b, 2
    while sid in used or sid in ("REF",):
        sid, i = "%s%d" % (b, i), i + 1
    used.add(sid)
    return sid


def scaffold(args, work, res):
    t0, inp, errs, degr = time.time(), Path(args.input), [], []
    files = [p for p in sorted(inp.rglob("*")) if p.is_file() and not p.name.startswith(".")][:X.CAP_FILES] \
        if inp.is_dir() else ([inp] if inp.is_file() else [])
    if not files:
        errs.append("input_missing: %s" % inp)
    C = {"units": [], "sents": [], "docs": {}, "sources": [], "cands": [], "refs": {}, "cites": {}, "full": ""}
    case, cp = {}, next((c for c in [inp / "case.json"] + (sorted(inp.rglob("case*.json")) if inp.is_dir() else [])
                         if c.exists()), None)
    if cp:
        try:
            case = rjson(cp)
        except Exception as e:
            errs.append("case_json_invalid: %s: %s" % (cp.name, e))
    ck = find_contract(case)
    res["contract_fields"]["requested"] = ckeys(ck[1]) if ck else []
    if ck:
        res[ck[0]] = ck[1]
    for k in ("case_id", "caseId", "id", "case", "name"):
        if isinstance(case.get(k), (str, int)):
            res["case_id"] = str(case[k])
            break
    used = set()
    for f in files:
        if f.name in ("task.md", "case.json"):
            continue
        b = "MS" if re.search(r"manuscript|paper|draft|main|article|正文|稿件|论文", f.stem, re.I) else \
            (re.sub(r"[^A-Za-z0-9_]", "", f.stem)[:12] or "MAT")
        txt, kind = X.read_material(f, errs, degr)
        add_source(C, uniq_sid(b, used), f.name, str(f), kind, txt)
    for ptr, s in X.json_strings(case)[:20]:  # 稿件可能内联在 case.json
        b = "CASE" + (re.sub(r"[^A-Za-z0-9]", "", "/".join([q for q in ptr.split("/") if q][:2]))[:10].upper() or "X")
        add_source(C, uniq_sid(b, used), "case.json" + ptr, str(cp), "json_inline", s)
    C["full"] = (SEP * 2).join(d["text"] for d in C["docs"].values())
    C["f"] = features(C)
    C["refs"] = X.parse_refs(C["docs"].get("MS", {}).get("text") or C["full"])
    C["cites"] = X.parse_cites(C)
    try:
        C["cands"] = X.detect(C)
    except Exception as e:
        errs.append("detector_failed: %s" % e)
    C["cands"].sort(key=lambda x: (x["priority"], X.FKEYS.index(x["facet"])))
    C["cands"] = C["cands"][:X.CAP_CANDS]
    for i, x in enumerate(C["cands"]):
        x["cid"] = "C%03d" % (i + 1)
    res["sources"] = C["sources"] + [dict(sid="REF", name="reference_detector", path="", kind="derived",
                                          bytes=0, chars=0, sha256_12="", status=C["refs"]["mode"])]
    res["checks"], res["errors"], res["degradations"] = blank("未裁定"), errs, degr
    res["review_records"] = {"stage": "scaffold", "candidate_count": len(C["cands"]),
                             "reference_mode": C["refs"]["mode"], "reference_count": len(C["refs"]["items"]),
                             "citation_numbers": len(C["cites"]["numbers"]), "units": len(C["units"]),
                             "chars": C["f"]["chars"], "words": C["f"]["words"]}
    if not C["docs"]:
        res["status"] = "input_error"
        res["uncertainty"].append(dict(item="无任何可解析材料", impact="无法执行审查，仅登记输入"))
    elif C["f"]["chars"] < 400:
        res["status"] = "insufficient_evidence"
        res["uncertainty"].append({"item": "可解析文本仅 %d 字符" % C["f"]["chars"], "impact": "疑为扫描件或抽取失败。"})
    X.write_packets(C, work / "review")
    res["artifacts"].update({"candidates_json": str(work / "review" / "candidates.json"),
                             "packets_md": str(work / "review" / "packets.md")})
    res["changes"].append("scaffold")  # 确定性
    return C, res

def nfacet(v):
    v = str(v or "").strip()
    if v in X.ZH2F:
        return X.ZH2F[v]
    low = v.lower().replace("-", "_").replace(" ", "_")
    hit = [k for k in X.FKEYS if low and (k.startswith(low) or low in k)]
    return hit[0] if hit else FAC.get((re.match(r"^([FCMSAN])", v.upper()) or [None, ""])[1])


def finalize(C, res, plan):
    plan = plan or {}
    iss, rej, pend = [], [], []
    dis = [dict(cid=str(d["cid"]), reason=str(d.get("reason") or ""))
           for d in plan.get("dismissed") or [] if isinstance(d, dict) and d.get("cid")]
    for r in plan.get("issues") or []:
        if not isinstance(r, dict):
            continue
        fac, sev = nfacet(r.get("facet") or r.get("item")), str(r.get("severity") or "").strip().lower()
        q = str(r.get("quote") or "")
        bad = [x for ok, x in ((fac, "facet"), (sev in X.SEVS, "severity"), (len(X.norm(q)) >= 8, "quote")) if not ok]
        u, how = (None, "") if bad else X.find_quote(q, C)
        if not u:
            why = ",".join(bad) or "quote 未逐字命中"
            rej.append(dict(quote=X.snip(q, 140), reason=why))
            pend.append(dict(item="被拒收：%s" % X.snip(str(r.get("title") or q), 40), why=why))
            continue
        vt, cf = str(r.get("verdict_type") or ""), str(r.get("confidence") or "medium").lower()
        iss.append({"facet": fac, "item": (str(r.get("item") or "")[:16] or "GEN"), "severity": sev,
                    "verdict_type": vt if vt in X.VTYPES else ("error" if fac == "fact_verification" else "norm_violation"),
                    "title": str(r.get("title") or "")[:160], "source_id": u["sid"],
                    "locator": str(r.get("locator") or u["locator"]), "quote": q.strip(), "quote_verification": how,
                    "evidence": [e for e in (r.get("evidence") or []) if isinstance(e, dict)][:8],
                    "reason": str(r.get("reason") or "")[:1200], "suggestion": str(r.get("suggestion") or "")[:1200],
                    "confidence": cf, "status": "confirmed" if cf == "high" else "needs_human",
                    "related_candidates": [str(x) for x in r.get("related_candidates") or []][:8]})
    seen, uniq = set(), []
    for i in iss:
        k = (i["source_id"], X.squash(i["quote"])[:200])
        if k in seen:
            rej.append(dict(quote=X.snip(i["quote"], 100), reason="duplicate"))
        else:
            seen.add(k)
            uniq.append(i)
    uniq.sort(key=lambda x: (X.SEVS.index(x["severity"]), X.FKEYS.index(x["facet"])))
    for n, i in enumerate(uniq):
        i["id"] = "R-%02d" % (n + 1)
    checks, pc = blank(""), plan.get("checks") or {}
    cov = set(x for i in uniq for x in i["related_candidates"]) | set(d["cid"] for d in dis)
    for k in X.FKEYS:  # 覆盖 + 漏项守卫：仍有未裁定候选时不得判 pass
        c, raw = checks[k], pc.get(k) or pc.get(X.FZH[k]) or {}
        st = str(raw.get("status") or "").lower()
        if st in X.CSTAT:
            c["status"], c["scope"], c["notes"] = st, str(raw.get("scope") or "")[:400], str(raw.get("notes") or "")[:600]
            if st == "not_applicable":
                c["notes"] += " | 不适用：" + str(raw.get("not_applicable_reason") or "未填")
        c["findings"] = sum(1 for i in uniq if i["facet"] == k)
        c["unresolved"] = [x["cid"] for x in C.get("cands", []) if x["facet"] == k and x["cid"] not in cov]
        if c["unresolved"] and c["status"] == "pass":
            c["status"] = "incomplete"
            c["notes"] += " | %d 候选未裁定（%s）" % (len(c["unresolved"]), ", ".join(c["unresolved"][:5]))
        if not plan and c["status"] == "not_checked":
            c["notes"] = "无裁定计划"
    done = sum(1 for k in X.FKEYS if checks[k]["status"] in ("pass", "issues_found", "not_applicable"))
    res["issues"], res["checks"] = uniq, checks
    res["summary"] = {"issue_total": len(uniq), "facet_coverage": "%d/6" % done,
                      "by_severity": dict((s, sum(1 for i in uniq if i["severity"] == s)) for s in X.SEVS),
                      "needs_human": sum(1 for i in uniq if i["status"] == "needs_human"), "rejected": len(rej),
                      "unaddressed": sum(len(checks[k]["unresolved"]) for k in X.FKEYS)}
    res["pending_human"] = (plan.get("pending_human") or []) + pend
    res["uncertainty"] += [u for u in plan.get("uncertainty") or [] if isinstance(u, dict)]
    res["review_records"].update(dict(stage="finalize", rejected_issues=rej, dismissed_candidates=dis))
    res["status"] = "input_error" if (res.get("status") == "input_error" or not C.get("docs")) else \
        "insufficient_evidence" if C.get("f", {}).get("chars", 0) < 400 else \
        "partial" if (not plan or done < 6 or any(checks[k]["status"] == "incomplete" for k in X.FKEYS)) else "ok"
    res["changes"].append("finalized_" + res["status"])
    return res

def render(res, out):
    s, rd = res["summary"], res["review_records"]
    L = ["# 学术规范与合规审查报告", "",
         "- case `%s`｜%s｜问题 %d（%s）｜覆盖 %s｜待复核 %d｜拒收 %d｜未裁定 %d"
         % (res.get("case_id"), res["status"], s["issue_total"],
            "/".join("%s%d" % (SEV[k], s["by_severity"][k]) for k in X.SEVS), s["facet_coverage"],
            s["needs_human"], s["rejected"], s["unaddressed"]), ""]
    L += ["- 【%s】%s｜%d 条｜%s" % (k, res["checks"][k]["status"], res["checks"][k]["findings"],
                                   res["checks"][k]["notes"] or res["checks"][k]["scope"] or "-") for k in X.FKEYS]
    L += ["", "## 2. 问题清单（quote 均逐字校验；未命中者列入第 3 节）", ""]
    for i in res["issues"]:
        ev = "; ".join("[%s] %s" % (e.get("source", "?"), e.get("quote") or e.get("note") or "") for e in i["evidence"])
        L += ["### %s [%s｜%s] %s" % (i["id"], SEV[i["severity"]], X.FZH[i["facet"]], i["title"]),
              "- 位置 `%s` %s｜`%s`｜%s｜置信 %s" % (i["source_id"], i["locator"], i["item"], i["verdict_type"],
                                                 i["confidence"]),
              "- 原文：「%s」" % i["quote"].replace(SEP, " "),
              "- 依据 %s｜理由 %s｜建议 %s" % (ev or "仅稿件内部一致性", i["reason"] or "-", i["suggestion"] or "-"), ""]
    L += ["## 3. 待复核 / 拒收", ""] + ["- %s：%s" % (p.get("item", "?"), p.get("why", "?"))
                                       for p in res["pending_human"]]
    L += ["", "## 4. 不确定性与材料", ""] + ["- %s → %s" % (u.get("item", "?"), u.get("impact", "?"))
                                             for u in res["uncertainty"]]
    L += ["材料%d：%s" % (len(res["sources"]), "; ".join("%s(%s 字符)" % (x.get("sid"), x.get("chars"))
                                                      for x in res["sources"])),
          "运行 %s｜候选 %s｜引用 %s｜文献表 %s｜错误 %s｜降级 %s"
          % (rd.get("stage"), rd.get("candidate_count"), rd.get("citation_numbers"), rd.get("reference_mode"),
             res["errors"] or "无", res["degradations"] or "无")]
    (Path(out) / "review_report.md").write_text(SEP.join(L), encoding="utf-8")
    cols = ["id", "facet", "facet_zh", "item", "severity", "verdict_type", "source_id", "locator", "quote",
            "reason", "suggestion", "confidence", "status", "related_candidates"]
    with open(Path(out) / "issues.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for i in res["issues"]:
            w.writerow(dict(i, facet_zh=X.FZH[i["facet"]], related_candidates=";".join(i["related_candidates"])))
    res["artifacts"].update({"result_json": str(Path(out) / "result.json"),
                             "review_report_md": str(Path(out) / "review_report.md"),
                             "issues_csv": str(Path(out) / "issues.csv")})
    return res

def run(args):
    t0, out = time.time(), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if X is None:
        res = base()
        res["errors"] = ["import_failed: %s" % IMP]
        wjson(out / "result.json", res)
        print("[review-05] import failed")
        return 0
    work = Path(args.work) if args.work else out.parent / "work"
    res = base()
    wjson(out / "result.json", res)  # 1) partial first
    C, res = scaffold(args, work, res)
    plan, pp = None, Path(args.plan) if args.plan else work / "review" / "issues_plan.json"
    if pp.exists() and args.stage != "scaffold":
        try:
            plan = rjson(pp)
            if not isinstance(plan, dict):
                raise ValueError("plan must be an object")
        except Exception as e:
            res["errors"].append("plan_json_invalid: %s" % e)
    elif args.stage != "scaffold":
        res["degradations"].append("plan_missing")
    res = finalize(C, res, plan)
    res["runtime"] = dict(python=sys.version.split()[0], elapsed_s=round(time.time() - t0, 2),
                          argv=sys.argv[1:], skill_version=V, stage=args.stage)
    res = render(res, out)
    keys = res["contract_fields"]["requested"]
    filled, un = fill_contract(res, keys)
    res.update(filled)
    res["contract_fields"]["filled"] = [k for k in keys if k not in un]
    res["contract_fields"]["unfilled"] = un
    wjson(out / "result.json", res)  # 2) unconditional finalize
    print("[review-05] %s issues=%d" % (res["status"], len(res["issues"])))
    return 0

def safe_partial(outdir, err, t0):
    try:
        p, res = Path(outdir) / "result.json", base()
        res["errors"] = ["fatal: %s: %s" % (type(err).__name__, err)]
        res["uncertainty"] = [{"item": "流水线异常终止", "impact": "结果不可作为审查结论"}]
        res["runtime"] = dict(elapsed_s=round(time.time() - t0, 2), skill_version=V)
        res["checks"] = blank("因异常未执行") if X else {}
        try:
            old = rjson(p)
            res["case_id"], res["contract_fields"] = old.get("case_id"), old.get("contract_fields") or res["contract_fields"]
            res.update(dict((k, None) for k in res["contract_fields"].get("requested") or [] if k not in res))
        except Exception:
            pass
        wjson(p, res)
        print("[review-05] FATAL partial: %s" % err)
    except Exception as e2:
        print("[review-05] FATAL no-json: %s / %s" % (err, e2))

def build_parser():
    ap = argparse.ArgumentParser(prog="main.py", description="review-05 学术规范与合规审查（scaffold→裁定→finalize）："
        "输出 result.json／review_report.md／issues.csv；标准库、离线、不依赖 CWD、退出码恒 0。")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="")
    ap.add_argument("--stage", default="auto", choices=["auto", "scaffold", "finalize"])
    ap.add_argument("--plan", default="")
    return ap

def main(argv=None):
    a, _ = build_parser().parse_known_args(argv)
    t0 = time.time()
    try:
        return run(a)
    except SystemExit:
        raise
    except Exception as e:
        safe_partial(a.output, e, t0)
        return 0


if __name__ == "__main__":
    sys.exit(main())
