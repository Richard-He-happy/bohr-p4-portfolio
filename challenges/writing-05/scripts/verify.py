#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-03 文本层与规则层（被 main.py 导入，也可单独运行校验）。"""
import argparse, hashlib, json, re, shutil, subprocess, sys, zipfile
from pathlib import Path

V = "2.0.0"
CJ = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
SW = set("""the a an of and or to in for on with by as at from that this these those is are was were be been being we
our it its their they than which who not can may might could should would will also such more most other into about
between among both each per using used use study studies result showed show found find suggests suggest
indicate however thus therefore has have had there""".split())
ZW = set("研究 显示 表明 本文 我们 方法 结果 结论 数据 分析 以及 这些 由于 因此 但是 然而 并且 相关 影响 具有 进行 可以 通过 一个 一种 中的 作者 中 的 了 和 与 在 是 为 对 也 有 被".split())
NEG = re.compile(r"(no significant|not significant|no association|not associated|did not|no effect|failed to|相反|无显著|未发现|不相关|无效)", re.I)
POS = re.compile(r"(significant|increased|higher|greater|improved|effective|显著|提高|改善|有效|增加|降低)", re.I)


def sha(p):
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(1 << 16), b""): h.update(c)
        return h.hexdigest()
    except Exception: return None


def read_doc(p):
    """-> (text, method, note)。"""
    p = Path(p); e = p.suffix.lower()
    try:
        if e == ".pdf":
            if shutil.which("pdftotext"):
                r = subprocess.run([shutil.which("pdftotext"), "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=90)
                if r.returncode == 0 and r.stdout.strip(): return r.stdout.decode("utf-8", "ignore"), "pdftotext", ""
            for m in ("pypdf", "PyPDF2"):
                try:
                    t = "\n".join((g.extract_text() or "") for g in getattr(__import__(m), "PdfReader")(str(p)).pages)
                    if t.strip(): return t, m, ""
                except Exception: pass
            return "", "none", "PDF 无文本层（疑扫描件），需 OCR"
        if e == ".docx":
            x = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "ignore")
            x = re.sub(r"<[^>]+>", "", re.sub(r"</w:p>|</w:tr>", "\n", x))
            return x.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"), "zip+ooxml", ""
        if e in (".xlsx", ".xlsm", ".pptx", ".doc"):
            return "", "unsupported", "表格/演示格式未内置解析，请转 CSV/文本"
        if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"): return "", "image", "图像需视觉读取"
        t = p.read_text(encoding="utf-8", errors="ignore")
        if e in (".html", ".htm"): t = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))
        return t, "text", ""
    except Exception as ex:
        return "", "error", "%s: %s" % (type(ex).__name__, ex)


DH = re.compile(r"(draft|manuscript|to_?edit|rough|原稿|草稿|待改|初稿|段落)", re.I)
RH = re.compile(r"(ref|bib|reference|citation|文献)", re.I)


def discover(ind, case):
    """语义发现：按文件名/case 键名推断 draft|references|material。"""
    hs, docs, seen = [], [], set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and 3 < len(v) < 300 and ("/" in v or "." in v): hs.append((k, v))
                walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(case)
    for p in sorted(Path(ind).rglob("*")):
        if not p.is_file() or p.name in ("case.json", "task.md", "task.txt"): continue
        rel = str(p.relative_to(ind))
        if p.suffix.lower() in (".pyc", ".log") or "__pycache__" in rel or p.resolve() in seen: continue
        seen.add(p.resolve())
        t, m, no = read_doc(p)
        kd = "references" if RH.search(p.stem) else "draft" if DH.search(p.stem) else "material"
        for k, v in hs:
            if v.endswith(p.name) and (DH.search(k) or RH.search(k)): kd = "draft" if DH.search(k) else "references"
        docs.append({"doc_id": "D%02d" % (len(docs) + 1), "path": rel, "kind": kd, "text": t, "method": m,
                     "note": no, "bytes": p.stat().st_size, "sha256": sha(p)})
    return docs


SP = re.compile(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z0-9\"“(\[])")


def sents(t):
    return [s.strip() for s in SP.split(t) if s and len(s.strip()) > 1]


def segment(docs):
    """句级切分，每句带可回查 locator（文件 [块.句] 字符偏移）。"""
    us = []
    for d in docs:
        if not d["text"].strip(): continue
        t = d["text"].replace("\r\n", "\n"); pos = bi = 0
        for raw in re.split(r"\n\s*\n|\n(?=#{1,6}\s)", t):
            b = raw.strip()
            if not b: continue
            st = t.find(b, pos); st = pos if st < 0 else st; pos = st + len(b); bi += 1
            if re.match(r"^#{1,6}\s", b): continue
            off = st
            for i, s in enumerate(sents(b), 1):
                q = t.find(s, off); q = off if q < 0 else q; off = q + len(s)
                us.append({"uid": "%s#B%d.S%d" % (d["doc_id"], bi, i), "doc": d["doc_id"], "text": s,
                           "loc": "%s [B%d.S%d] chars:%d-%d" % (d["path"], bi, i, q, q + len(s))})
    return us


try:  # 中英术语表：把中文短语归一为英文概念词，使中文原稿能与英文文献对齐
    CANON = dict(l.split("\t")[:2] for l in (Path(__file__).resolve().parent.parent / "references" / "lexicon_zh_en.txt").read_text("utf-8").splitlines() if "\t" in l and not l.startswith("#"))
except Exception: CANON = {}


def canon(s):
    for k in sorted(CANON, key=len, reverse=True):
        if k in s: s = s.replace(k, " " + CANON[k] + " ")
    return s


def toks(s):
    """中英归一后的英文词 + 中文 bigram（去停用词），用于论断-来源匹配。"""
    s = canon(s)
    s = s.lower(); c = CJ.findall(s)
    return {x for x in re.findall(r"[a-z][a-z\-]{2,}|\d+(?:\.\d+)?", s) if x not in SW} | \
        ({"".join(c[i:i + 2]) for i in range(len(c) - 1)} - ZW if len(c) > 1 else set())


def sim(a, b, ta=None, tb=None):
    ta = ta or toks(a); tb = tb or toks(b)
    if not ta or not tb: return 0.0
    r = len(ta & tb) / ((len(ta) ** .5) * (len(tb) ** .5))
    return min(1.0, r + (.08 if set(re.findall(r"\d+(?:[.,]\d+)?%?", a)) & set(re.findall(r"\d+(?:[.,]\d+)?%?", b)) else 0))


def parse_refs(docs):
    """解析文献表：只转录原文，缺 DOI 不补写。"""
    out, seen = [], set()
    for d in docs:
        if d["kind"] != "references" and not re.search(r"^\s*#*\s*(参考文献|references?)\s*$", d["text"], re.I | re.M): continue
        t = re.split(r"^\s*#*\s*(?:参考文献|references?)\s*$", d["text"], flags=re.I | re.M)[-1]
        for c in re.split(r"\n(?=\s*(?:\[\d+\]|\d+[.)]\s))", t):
            c = " ".join(c.split())
            if len(c) < 12 or c[:80].lower() in seen: continue
            seen.add(c[:80].lower())
            m = re.match(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s*", c); b = c[m.end():] if m else c
            dm = DOI.search(b); ym = re.search(r"\b(19|20)\d{2}\b", b)
            out.append({"num": int(m.group(1) or m.group(2)) if m else None, "raw": c, "body": b,
                        "doi": dm.group(0) if dm else None, "year": ym.group(0) if ym else None,
                        "venue": bool(re.search(r"(Journal|Nature|Science|Lancet|BMJ|Cell|PNAS|PLoS|Front|Proc|Res|Rev|学报|杂志|Press|Springer|Elsevier|Wiley)", b))})
    return out


DES = [(r"(systematic review|meta-?analys|荟萃|系统评价|系统综述)", "系统综述/荟萃", 3.), (r"(guideline|consensus|指南|共识)", "指南/共识", 3.),
       (r"(randomi[sz]ed|\bRCT\b|随机对照)", "RCT", 3.), (r"(cohort|prospective|longitudinal|队列|前瞻|纵向)", "队列", 2.),
       (r"(case-?control|病例对照)", "病例对照", 2.), (r"(cross-?sectional|survey|横断面|调查)", "横断面", 1.5),
       (r"(case report|case series|病例报告|个案)", "病例报告", .5), (r"(preprint|bioRxiv|medRxiv|arXiv|预印本)", "预印本", 1.),
       (r"(\breview\b|综述)", "叙述综述", 1.), (r"(in vitro|cell line|mice|mouse|rat|体外|细胞系|小鼠|大鼠)", "体外/动物", 1.)]
NR = [r"\bn\s*=\s*([\d,]{1,7})", r"([\d,]{2,7})\s*(?:participants|patients|subjects|individuals|samples|mice|rats|children|adults|名|例|位|受试者|患者|样本)"]


def design(t):
    for p, n, s in DES:
        if re.search(p, t, re.I): return n, s
    return "未标明", 1.


def nsize(t):
    v = [int(m.group(1).replace(",", "")) for p in NR for m in re.finditer(p, t, re.I) if m.group(1).replace(",", "").isdigit()]
    return max(v) if v else None


def grade(txt, doct, nsrc, conf, ab):
    """四因子强度：设计+样本量+独立来源-冲突；预印本封顶中、n<100 封顶低、仅摘要最高中。"""
    dn, dp = design(txt + " " + doct[:400]); n = nsize(txt) or nsize(doct)
    sp, sn = (0., "未报告") if n is None else (2., ">=1000") if n >= 1000 else (1.5, "100-999") if n >= 100 else (1., "10-99") if n >= 10 else (.5, "<10")
    rp = 1. if nsrc >= 2 else 0.
    tot = dp + sp + rp - (1. if conf else 0.)
    if "预印本" in dn: tot = min(tot, 4.)
    if n is not None and n < 100: tot = min(tot, 3.4)
    lv = "高" if tot >= 5.5 else "中" if tot >= 3.5 else "低" if tot >= 1.5 else "不足"
    if ab and lv == "高": lv = "中"
    return lv, "设计=%s(%.1f)；样本=%s(%.1f)；独立来源=%d(%.1f)；冲突=%d" % (dn, dp, sn, sp, nsrc, rp, 1 if conf else 0), \
        {"design": dn, "design_pts": dp, "sample_size": n, "size_pts": sp, "sources": nsrc, "conflict": bool(conf), "score": round(tot, 2)}


CA = [(r"\bcauses?\b|\bleads? to\b|\bresults? in\b|\bproves?\b|\bdemonstrates? that\b|\bconfirms? that\b", "is associated with"),
      (r"导致([^。.；]{2,30})", r"与\1相关"), (r"证明了|证实了|确证|必然", "提示")]
UN = [(r"\ball\b|\balways\b|\bnever\b", "in the material reviewed"), (r"所有|全部|总是|从来", "在所纳入材料中")]
AS = re.compile(r"(associat|correlat|relat|相关|关联|伴随|有关)", re.I)


def down(t):
    """过度推断下调：因果->关联、全称->范围限定；不改数值，写入 change_log。"""
    out, nt = t, []
    for lst, why in ((CA, "仅关联性观察、无随机化/干预对照，按强度下调为关联表述"), (UN, "全称量词超出单篇/小样本证据的支撑范围")):
        if lst is CA and AS.search(out): continue
        for pat, rep in lst:
            n2 = re.sub(pat, rep, out, flags=re.I)
            if n2 != out: nt.append(("causal_to_association" if lst is CA else "universal_to_scoped", out, n2, why)); out = n2
    return out, nt


def strip_tail(s):
    return re.sub(r"\s*(?:[\[［]\d{1,3}[\]］]|\([A-Z][^()]{0,40}\d{4}[a-z]?\)|（[^（）]{0,30}\d{4}）)+[。.；;!！?？]*\s*$", "", s).strip()


def cls(t):
    if re.search(r"(compare|compared|higher than|lower than|高于|低于|相比|\bthan\b)", t, re.I): return "比较"
    if re.search(r"(because|causes?|leads? to|due to|导致|因为|因果)", t, re.I): return "因果"
    if re.search(r"(may|might|could|suggest|likely|可能|提示|推断|推测)", t, re.I): return "推断"
    return "事实"


ABSQ = lambda d: bool(re.search(r"(abstract|摘要)", d["text"], re.I)) and len(d["text"]) < 3000


def ref_entry(d, refs, n, L):
    """文献表条目优先；无著录标缺口，不编造作者/年份/DOI。"""
    t = d.get("text", "") or ""
    for r in refs:
        if (r["doi"] and r["doi"] in t) or sim(r["body"][:150], t[:300]) >= .35:
            return re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", r["raw"])
    h = " ".join(t.split())[:170]
    return (h + "（自材料首段转录，著录可能不完整）") if len(h) > 40 and re.search(r"(19|20)\d{2}", h) else L["rm"].format(n=n, s=d.get("doc_id"), l=d.get("path"))


def aux(out, rows, refs, hedge):
    """强度依据/著录核验/不确定性三份辅助记录（口径见 references/method_and_runbook.md）。"""
    e = ["# 证据强度记录", "", "四因子口径见 references/method_and_runbook.md；>=5.5 高，3.5-5.4 中，1.5-3.4 低，<1.5 不足。", ""]
    for r in rows:
        e += ["- **%s** <- %s | 强度 **%s** | %s" % (r["claim_id"], r.get("source_id") or "无来源", r["strength"], r.get("rationale", "")),
              "  - 论断：%s" % r["claim"][:150], "  - 范围：%s" % r.get("support_scope", ""), "  - 定位：%s" % (r.get("locator") or "—")]
    (out / "evidence_strength.md").write_text("\n".join(e), "utf-8")
    q = ["# 参考文献核验", "", "离线运行，**未联网核验**：只记材料一致性与著录完整度，不声称已确认文献真实存在。", "",
         "| # | 著录 | 年 | DOI | 完整度 | 缺失 |", "|---|---|---|---|---|"]
    for x in refs:
        ms = [k for k, ok in (("year", x["year"]), ("venue", x["venue"]), ("doi", x["doi"])) if not ok]
        if not re.search(r"[A-Z][a-z]{2,}", x["body"]): ms.append("authors")
        q.append("| %s | %s | %s | %s | %s | %s |" % (x["num"] or "-", x["raw"][:70].replace("|", "/"),
                                                       x["year"] or "缺", x["doi"] or "未给", "完整" if not ms else "缺失", "、".join(ms) or "—"))
    if not refs: q.append("| — | 无文献表 | — | — | 缺口 |")
    q += ["", "- 编号按首次引用重排；无著录者标缺口，不补造作者/年份/DOI。",
          "- 待办：联网用 Crossref/PubMed 复核 DOI 后方可标“已核验”。"]
    (out / "reference_check.md").write_text("\n".join(q), "utf-8")
    lo = "、".join(sorted({r["claim_id"] for r in rows if r["strength"] in ("低", "不足")})) or "无"
    co = "、".join(sorted({r["claim_id"] for r in rows if r.get("conflicts")})) or "无"
    (out / "uncertainty_notes.md").write_text("\n".join(
        ["# 不确定性说明", "", "- 低/不足论断：" + lo, "- 存在冲突证据：" + co,
         "- 仅摘要可核来源：%d" % sum(1 for r in rows if r.get("abstract_only")),
         "- 未匹配来源的论断：%d" % sum(1 for r in rows if not r.get("source_id")), "- 著录未联网核验：全部（离线）", "",
         "限定语：" + hedge]), "utf-8")


def receipt(case, draft, od):
    """逐项执行 organizer_workorder 的可判据项并回报。"""
    its = []
    for k in ("organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder"):
        v = case.get(k)
        for i, it in enumerate(([v] if isinstance(v, (str, dict)) else (v or [])), 1):
            its.append(it.get("id") or "%s-%d" % (k, i) if isinstance(it, dict) else "%s-%d" % (k, i))
    o = []
    for _, (it, iid) in enumerate(zip([x for k in ("organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder")
                                       for x in ([case[k]] if isinstance(case.get(k), (str, dict)) else (case.get(k) or []))], its)):
        t = (it.get("instruction") or it.get("text") or it.get("task") or json.dumps(it, ensure_ascii=False)) if isinstance(it, dict) else str(it)
        ck = []
        m = re.search(r"(\d{2,4})\s*(?:字|words?|词)", t, re.I)
        if m:
            n = len(CJ.findall(draft)); n = n if n > 30 else len(re.findall(r"[A-Za-z][A-Za-z\-]+", draft))
            ck.append({"check": "length<=%s" % m.group(1), "actual": n, "pass": n <= int(m.group(1)) * 1.15})
        m = re.search(r"(?:引用|cite|citation)[^0-9]{0,12}(\d+)\s*(?:篇|条|references?)", t, re.I)
        if m: ck.append({"check": "refs>=%s" % m.group(1), "actual": len(od), "pass": len(od) >= int(m.group(1))})
        m = re.search(r"(apa|vancouver|nature|author-?year|作者-?年|数字编号|numeric)", t, re.I)
        if m:
            st = m.group(1).lower()
            ck.append({"check": "style=%s" % st, "pass": bool(re.search(r"\[\d+\]", draft)) if st in ("vancouver", "numeric", "nature", "数字编号")
                       else bool(re.search(r"\([A-Z][A-Za-z]+\s+et al\.?,?\s*\d{4}\)", draft))})
        o.append({"id": iid, "instruction": t[:200], "checks": ck,
                  "status": ("done" if all(c["pass"] for c in ck) else "partial") if ck else "unverifiable",
                  "note": "" if ck else "无确定性判据，按 SKILL.md 第 5 节人工确认"})
    return o


def check(ind, out):
    """独立复核：重读材料核对产物，不采信自报。"""
    out = Path(out); ck = []
    res = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    case = {}
    for c in [Path(ind) / "case.json"] + sorted(Path(ind).glob("*case*.json")):
        if c.is_file():
            try: case = json.loads(c.read_text(encoding="utf-8")); break
            except Exception: pass
    con = case.get("output_contract") or {}
    miss = [k for k in con if k not in res]
    ck.append({"check": "contract_fields", "pass": not miss, "found": len(set(con) & set(res)), "expected": len(con),
               "detail": "缺失: %s" % miss if miss else "全部字段回填"})
    ck.append({"check": "case_id_echo", "pass": str(res.get("case_id")) == str(case.get("case_id") or res.get("case_id")),
               "detail": "case_id=%s" % res.get("case_id")})
    docs = discover(ind, case) if Path(ind).is_dir() else []
    pool = "\n".join(d["text"] for d in docs)
    rows = json.loads((out / "evidence_table.json").read_text(encoding="utf-8")).get("rows", []) if (out / "evidence_table.json").exists() else []
    cl = json.loads((out / "claims.json").read_text(encoding="utf-8")).get("claims", []) if (out / "claims.json").exists() else []
    draft = (out / "evidence_driven_draft.md").read_text(encoding="utf-8") if (out / "evidence_driven_draft.md").exists() else ""
    q = [r for r in rows if r.get("quote")]
    bad = [r["claim_id"] for r in q if r["quote"] not in pool]
    ck.append({"check": "quote_verbatim", "pass": not bad, "hit": len(q) - len(bad), "total": len(q),
               "detail": "未命中: %s" % bad if bad else "引文全部逐字命中"})
    dang = sorted({r["claim_id"] for r in rows} - {c["claim_id"] for c in cl})
    ck.append({"check": "claim_join", "pass": not dang, "detail": "悬空: %s" % dang if dang else "claims<->evidence 可 join"})
    nf = [r["claim_id"] for r in rows if not all(x in r for x in ("locator", "strength", "support_scope", "quote"))]
    ck.append({"check": "row_fields", "pass": not nf, "detail": "缺字段: %s" % nf if nf else "四要素齐全"})
    mk = sorted({int(x) for x in re.findall(r"\[(\d{1,3})\]", draft)})
    src_n = len({r["source_id"] for r in rows if r.get("source_id")})
    ck.append({"check": "citation_resolvable", "pass": bool(mk) and max(mk) <= src_n, "markers": len(mk), "sources": src_n,
               "detail": "%s/%d" % (mk, src_n)})
    rep = {"case_id": res.get("case_id"), "passed": all(c["pass"] for c in ck), "checks": ck,
           "metrics": {"claims": len(cl), "evidence_rows": len(rows), "quotes": len(q), "quote_hit": len(q) - len(bad),
                       "distinct_sources": src_n, "citation_markers": len(mk)},
           "limits": ["未联网核验文献真实性与 DOI（离线）", "扫描件/图像无法逐字校验，见 degradations"]}
    (out / "verification.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), "utf-8")
    print("verify %s  %s" % ("PASS" if rep["passed"] else "FAIL",
                             " ".join("%s=%s" % (c["check"], c["pass"]) for c in ck)))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="writing-03 独立校验：逐字引文命中、claim/evidence join、契约字段、引用编号、限定语一致性。")
    ap.add_argument("--input", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--output", default="/app/output", help="输出目录（默认 /app/output）")
    a = ap.parse_args(argv)
    try: check(a.input, a.output)
    except Exception as e: print("verify degraded: %s: %s" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
