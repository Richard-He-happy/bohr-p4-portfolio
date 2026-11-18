#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""core.py - input discovery, case parsing and output helpers for literature-qa.

Shared by main.py (question answering) and main.py --verify (deterministic checks).
Stdlib only; all paths resolved from __file__, never from the current directory.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"

QID = ("question_id", "qid", "questionid", "q_id", "id", "no", "序号", "编号")
QTXT = ("question", "question_text", "text", "q", "query", "stem", "content", "prompt", "问题", "题目")
PID = ("paragraph_id", "para_id", "paraid", "pid", "block_id", "id", "label", "段落编号")
PTXT = ("text", "content", "body", "paragraph", "txt", "value", "sentence", "原文")
SEC = ("section", "section_name", "heading", "part", "chapter", "章节")
CASE_KEYS = ("case_id", "caseid", "case_key", "case")
PAPER_KEYS = ("paper_id", "paperid", "document_id", "doc_id", "doi", "paper")
VER_KEYS = ("material_version", "materialversion", "version", "material_rev")
PLIST = ("paragraphs", "paragraph_list", "paras", "segments", "blocks", "text_blocks",
         "corpus", "sentences", "paragraph_texts", "段落")
QLIST = ("questions", "question_list", "question_set", "qas", "queries", "problems", "tasks", "问题清单")
SEC_KEYS = ("sections", "materials", "manuscript", "paper_sections", "body_sections")
TBL_KEYS = ("tables", "table_texts", "table")
FIG_KEYS = ("figures", "figure_captions", "captions", "figure_legends", "legends")
REF_KEYS = ("references", "bibliography", "refs", "citations")
FILL = {"case_id", "status", "result", "claims", "uncertainties", "answers", "unanswered_parts",
        "coverage", "sources", "pending_human", "errors", "degradations", "changes", "runtime",
        "counts", "method_notes", "question_ids", "contract_keys", "summary", "verification",
        "primary_result", "evidence"}

FALLBACK_GLOSS = {
    "强度": ["strength"], "抗拉": ["tensile"], "硬度": ["hardness"], "热处理": ["heat treatment"],
    "合金": ["alloy"], "温度": ["temperature"], "应变": ["strain"], "应力": ["stress"],
    "晶粒": ["grain"], "缺陷": ["defect"], "疲劳": ["fatigue"], "磨损": ["wear"],
    "方法": ["method"], "模型": ["model"], "数据集": ["dataset"], "准确率": ["accuracy"],
    "误差": ["error"], "基线": ["baseline"], "光催化": ["photocataly"], "降解": ["degradation"],
    "催化剂": ["catalyst"], "光源": ["light source"], "波长": ["wavelength"], "自由基": ["radical"],
    "稳定性": ["stability"], "去除率": ["removal efficiency"], "浓度": ["concentration"],
    # v2: paraphrases/aliases the v1 word list missed (kept inside the script so no extra file)
    "退火": ["anneal"], "固溶": ["solution treatment", "solutionized"], "时效": ["aging"],
    "屈服": ["yield"], "塑性": ["ductility", "elongation"], "延伸率": ["elongation"],
    "断裂": ["fracture"], "韧性": ["toughness"], "腐蚀": ["corrosion"], "阻抗": ["impedance"],
    "盐雾": ["salt spray"], "涂层": ["coating"], "孔隙": ["porosity"], "密度": ["density"],
    "显微组织": ["microstructure"], "再结晶": ["recrystallization"], "残余应力": ["residual stress"],
    "寿命": ["life", "cycles"], "循环": ["cycle", "cycling"], "转速": ["rpm", "speed"],
    "载荷": ["load"], "变形": ["deformation"], "焊": ["weld"], "烧结": ["sinter"],
    "比表面积": ["surface area", "BET"], "带隙": ["band gap"], "矿化": ["mineralization"],
    "动力学": ["kinetics"], "速率常数": ["rate constant"], "投加量": ["dosage", "loading"],
    "染料": ["dye", "methylene blue", "rhodamine"], "抗生素": ["antibiotic", "tetracycline"],
    "可见光": ["visible light"], "紫外": ["UV", "ultraviolet"], "光强": ["irradiance"],
    "空穴": ["hole"], "电子": ["electron"], "复合": ["recombination"], "毒性": ["toxicity"],
    "训练": ["training"], "推理": ["inference"], "参数量": ["parameters"], "时延": ["latency"],
    "吞吐": ["throughput"], "泛化": ["generalization"], "消融": ["ablation"], "鲁棒性": ["robust"],
    "召回率": ["recall"], "精确率": ["precision"], "损失": ["loss"], "学习率": ["learning rate"],
    "数据增强": ["augmentation"], "注意力": ["attention"], "微调": ["fine-tun", "fine tun"],
    # v2: question-side nouns that v1 mapped to nothing, so the right paragraph was never scored
    "模块": ["module", "component", "block"], "贡献": ["contribut"], "移除": ["removing", "removal", "without"],
    "去掉": ["removing", "without"], "原因": ["because", "attribut", "due to"], "机制": ["mechanism", "attribut", "origin"],
    "解释": ["attribut", "explain", "ascribed"], "表明": ["indicat", "suggest", "show"], "归因": ["attribut", "ascribed"],
    "下降": ["decrease", "lower", "reduc", "drop"], "上升": ["increase", "higher", "rise"], "幅度": ["by", "margin"],
    "最佳": ["best", "optimal", "highest"], "主要": ["main", "dominant", "primary"], "贡献最大": ["main contributor", "dominant"],
    "准确率": ["accuracy", "top-1", "top-5"], "时延": ["latency", "inference time"], "移动端": ["mobile", "edge device"],
    "参数量": ["parameters", "params"], "轮次": ["epoch"], "批大小": ["batch size"], "数据集": ["dataset", "ImageNet", "benchmark"],
    "温度": ["temperature", "annealing temperature"], "时间": ["time", "duration"], "速率": ["rate", "kinetics"],
    "初始浓度": ["initial concentration"], "去除": ["removal", "degradation"], "效率": ["efficiency"],
}

S = {"errors": [], "degradations": [], "pending": [], "changes": [], "uncertainties": [], "missing": []}


def norm(s):
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"[\u2010-\u2015\-]", " ", s)
    s = s.replace("\u00b5", "u").replace("\u03bc", "u")
    return re.sub(r"\s+", " ", s).strip().lower()


def lk(d, keys):
    """case-insensitive first non-empty value for any key in keys."""
    if not isinstance(d, dict):
        return None
    low = {}
    for k in d:
        low.setdefault(str(k).strip().lower(), k)
    for want in keys:
        k = low.get(want.lower())
        if k is not None and d[k] not in (None, "", [], {}):
            return d[k]
    return None


def pairs(obj, depth=0):
    if depth > 6:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (list, dict)):
                yield str(k), v
            yield from pairs(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from pairs(v, depth + 1)


def jload(p):
    err = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return json.loads(Path(p).read_text(encoding=enc, errors="replace")), None
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
    return None, err


def jdump(p, obj):
    p = Path(p)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        return None


def load_gloss():
    g = dict(FALLBACK_GLOSS)
    try:
        for line in (REF / "glossary.md").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            zh, rest = line.split("|", 1)
            ens = [x.strip() for x in re.split(r"[,，;；]", rest) if x.strip()]
            if zh.strip() and ens:
                g[zh.strip()] = ens
    except Exception as e:  # noqa: BLE001
        S["degradations"].append({"item": "references/glossary.md", "reason": str(e),
                                  "impact": "仅使用脚本内置词表"})
    return g


def find_case(inp, case_arg=None):
    cands = [Path(case_arg)] if case_arg else []
    cands += [Path(inp) / n for n in ("case.json", "case_v3.json", "case-3.json")]
    for p in cands:
        if p.is_file():
            return p
    bad = re.compile(r"(score|gold|rubric|verifier|grading|expected|ground.?truth)", re.I)
    for p in sorted(Path(inp).glob("**/*.json")):
        if bad.search(p.name) or bad.search(str(p.parent)):
            continue
        return p
    return None


def build_meta(case):
    m = {"case_id": None, "paper_id": None, "material_version": None}
    if isinstance(case, dict):
        m["case_id"] = lk(case, CASE_KEYS)
        m["paper_id"] = lk(case, PAPER_KEYS)
        m["material_version"] = lk(case, VER_KEYS)
        if None in (m["paper_id"], m["material_version"]):
            for _, v in pairs(case):
                if isinstance(v, dict):
                    m["paper_id"] = m["paper_id"] or lk(v, PAPER_KEYS)
                    m["material_version"] = m["material_version"] or lk(v, VER_KEYS)
    for k in m:
        if m[k] is not None:
            m[k] = m[k] if isinstance(m[k], str) else json.dumps(m[k], ensure_ascii=False)
    return m


def _para(d, idx, section, origin, key):
    pid, text = None, None
    if isinstance(d, str):
        text = d
    elif isinstance(d, dict):
        pid, text = lk(d, PID), lk(d, PTXT)
        section = section or lk(d, SEC)
        if not isinstance(text, str):
            text = " ".join(str(v) for k, v in d.items()
                            if isinstance(v, str) and str(k).lower() not in {x.lower() for x in PID})
    if not isinstance(text, str):
        return None
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()
    if len(text) < 3:
        return None
    pid = re.sub(r"^[\[\(]|[\]\)]$", "", str(pid)).strip() if pid else f"P{idx + 1}"
    return {"paragraph_id": pid, "section": str(section).strip() if section else "unknown",
            "text": text, "origin": origin, "locator": f"/{origin}/{key}"}


def split_numbered(text):
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r"(?m)^\s*\[?(P\d{1,3}|S\d{1,3})\]?\s*[:.\-)]?\s+", text)]
    if len(marks) < 2:
        return []
    out = []
    for i, (pos, pid) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = re.sub(r"^\s*\[?(P\d{1,3}|S\d{1,3})\]?\s*[:.\-)]?\s*", "", text[pos:end])
        out.append({"paragraph_id": pid, "text": seg.strip()})
    return out


def guess_section(text):
    head = norm(text[:160])
    for pat, sec in ((r"^abstract", "abstract"), (r"^(keywords|introduction)", "introduction"),
                     (r"^(experimental|method|materials and method)", "methods"),
                     (r"^(results?|findings)", "results"), (r"^discussion", "discussion"),
                     (r"^conclusions?", "conclusion"), (r"^(references|bibliography)", "references")):
        if re.search(pat, head):
            return sec
    return "unknown"


def collect_paragraphs(case):
    paras, seen = [], set()

    def push(item):
        if not item:
            return
        if item["paragraph_id"] in seen:
            item["paragraph_id"] = f'{item["paragraph_id"]}_{len(paras) + 1}'
        seen.add(item["paragraph_id"])
        paras.append(item)

    def from_bag(bag, sec, key):
        if isinstance(bag, str):
            bag = split_numbered(bag) or [{"text": bag}]
        if not isinstance(bag, list):
            bag = [bag]
        for i, it in enumerate(bag):
            push(_para(it, i, sec, key, i))

    def walk(obj, sec=None, depth=0):
        if depth > 7 or not isinstance(obj, (dict, list)):
            return
        if isinstance(obj, list):
            for v in obj:
                walk(v, sec, depth + 1)
            return
        for k, v in obj.items():
            kl = str(k).lower()
            bag = isinstance(v, list) and v and isinstance(v[0], dict) and lk(v[0], PTXT)
            if isinstance(v, (list, str)) and v and (kl in PLIST or bag):
                # v2: a named section holding paragraphs ({"results": [...]}) keeps its own name
                from_bag(v, sec if kl in PLIST else str(k), str(k))
            elif kl in SEC_KEYS and isinstance(v, (dict, list)):
                for sk, sv in (v.items() if isinstance(v, dict) else enumerate(v)):
                    skl = str(sk).lower()
                    if skl in PLIST and isinstance(sv, (list, str)):
                        from_bag(sv, sec or str(sk), str(sk))  # v2: keep the real section name
                    elif isinstance(sv, (dict, list)):
                        walk(sv, sec if skl in PLIST else str(sk), depth + 1)
            elif isinstance(v, (dict, list)):
                walk(v, sec, depth + 1)

    walk(case)
    for names, kind in ((TBL_KEYS, "table"), (FIG_KEYS, "figure_caption"), (REF_KEYS, "references")):
        bag = []
        for k, v in pairs(case):
            if k.lower() in names and isinstance(v, list):
                bag = v
                break
        for i, it in enumerate(bag):
            txt, pid = "", None
            if isinstance(it, dict):
                pid = lk(it, PID)
                txt = lk(it, PTXT) or ""
                cap = lk(it, ("caption", "title", "label", "legend"))
                rows = lk(it, ("rows", "data", "table", "matrix"))
                if rows and not txt:
                    rr = [list(r) if isinstance(r, (list, tuple)) else [r] for r in rows]
                    head = rr[0] if len(rr) > 1 else []
                    txt = " ; ".join("; ".join(f"{head[i]}: {c}" if i < len(head) else str(c)
                                               for i, c in enumerate(r)) for r in (rr[1:] or rr))
                txt = (f"{str(cap).rstrip('. ')}. {txt}" if cap else txt).strip()
            else:
                txt = str(it)
            if len(txt) < 3:
                continue
            item = _para({"paragraph_id": pid or f"{kind[0].upper()}{i + 1}", "text": txt}, i, kind, names[0], i)
            if item:
                item["kind"] = kind
                push(item)
    if not paras:  # v2: fall back to a single long text blob (full_text/article/body/…)
        blob = ""
        stack = [case]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
                cand = [v for v in o.values() if isinstance(v, str) and len(v) > 200]
            elif isinstance(o, list):
                stack.extend(o)
                cand = []
            else:
                cand = []
            if cand:
                blob = max(cand + [blob], key=len)
        if blob:
            items = split_numbered(blob)
            if not items:
                chunks = [c.strip() for c in re.split(r"\n\s*\n", blob) if len(c.strip()) > 80]
                items = [{"text": c} for c in chunks] or [{"text": blob}]
            for i, it in enumerate(items):
                push(_para({"paragraph_id": it.get("paragraph_id") or f"P{i + 1}",
                            "text": it["text"]}, i, "unknown", "raw_text", i))
            if paras:
                S["changes"].append({"item": "paragraphs", "change": f"由整篇文本回退切分 {len(paras)} 段"})
    if not paras:
        S["missing"].append("论文段落文本（未找到可解析的 paragraphs/sections/正文）")
        S["errors"].append({"stage": "collect_paragraphs", "error": "no parseable paragraph text"})
    for p in paras:
        p.setdefault("kind", "paragraph")
        if p["section"] in ("", "unknown"):
            p["section"] = guess_section(p["text"])
    return paras


def find_questions(case):
    raw, where = None, None
    for name in QLIST:
        for k, v in pairs(case):
            if k.lower() == name.lower() and isinstance(v, (list, dict)) and v:
                raw, where = v, name
                break
        if raw is not None:
            break
    if raw is None:
        mat = PLIST + SEC_KEYS + TBL_KEYS + FIG_KEYS + REF_KEYS
        for k, v in pairs(case):
            if (isinstance(v, list) and v and len(v) <= 30 and all(isinstance(x, dict) for x in v)
                    and str(k).lower() not in mat and all(lk(x, QTXT) for x in v)
                    and not any(lk(x, PID[:5]) for x in v)):
                raw, where = v, k
                break
    out = []
    if isinstance(raw, dict):
        raw = [{"question_id": k, "question": v} for k, v in raw.items()]
    for i, it in enumerate(raw or []):
        qid = qtext = None
        if isinstance(it, str):
            qtext = it
        elif isinstance(it, dict):
            qid, qtext = lk(it, QID), lk(it, QTXT)
            if qtext is None:
                for k, v in it.items():
                    if isinstance(v, str) and len(v.strip()) > 6:
                        qtext, qid = v, qid or k
                        break
        if not qtext:
            continue
        out.append({"question_id": str(qid).strip() if qid else f"Q{i + 1}",
                    "question": str(qtext).strip()})
    ids = [q["question_id"] for q in out]
    for i, q in enumerate(out):
        if ids.count(q["question_id"]) > 1:
            q["question_id"] = f"Q{i + 1}"
    if not out:
        S["missing"].append("问题清单（未找到 questions 列表）")
    return out, where


def empty_payload():
    return {"case_id": None, "paper_id": None, "material_version": None, "status": "partial",
            "summary": "partial placeholder written before parsing",
            "result": {"answers": [], "unanswered_parts": [], "coverage": {}},
            "answers": [], "claims": [], "uncertainties": [], "uncertainty": [], "sources": [],
            "pending_human": [], "errors": [], "degradations": [], "changes": [],
            "counts": {}, "verification": {"ok": None}, "runtime": {"truncated": False}}


def apply_contract(payload, contract):
    """echo every contract key verbatim; unknown keys preserved; known keys filled."""
    merged = {}
    if isinstance(contract, dict):
        merged.update(contract)
        r = merged.get("result")
        if isinstance(r, dict) and isinstance(payload.get("result"), dict):
            nr = dict(r)
            for k, v in payload["result"].items():
                if nr.get(k) in (None, "", [], {}):
                    nr[k] = v
            payload["result"] = nr
    for k, v in payload.items():
        if k not in merged or k in FILL:
            merged[k] = v
    # v2: business mirrors stay authoritative even when the contract pre-declares them empty
    res = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    for k in ("answers", "unanswered_parts", "coverage"):
        if merged.get(k) in (None, "", [], {}) and res.get(k) not in (None, "", [], {}):
            merged[k] = res[k]
    return merged


def counts(answers, claims):
    ev = [e for c in claims for e in c.get("evidence", [])]
    hit = sum(1 for e in ev if e.get("quote_verified"))
    wc = [e.get("quote_words") or len(str(e.get("quote", "")).split()) for e in ev]
    sq = [s for a in answers for s in a.get("sub_questions") or []]
    return {"questions": len(answers), "sub_questions": len(sq),
            "sub_questions_answered": sum(1 for s in sq if s.get("status") == "answered"),
            "numeric_claims": sum(1 for c in claims if " = " in str(c.get("text", ""))),
            "quotes_below_15_words": sum(1 for w in wc if w < 15),
            "quote_words_min": min(wc) if wc else None, "quote_words_max": max(wc) if wc else None,
            "answered": sum(1 for a in answers if a["status"] == "answered"),
            "partial": sum(1 for a in answers if a["status"] == "partial"),
            "insufficient_evidence": sum(1 for a in answers if a["status"] == "insufficient_evidence"),
            "input_error": sum(1 for a in answers if a["status"] == "input_error"),
            "claims": len(claims), "evidence": len(ev), "evidence_verified": hit,
            "quote_hit_rate": round(hit / len(ev), 4) if ev else None,
            "claims_without_evidence": sum(1 for c in claims if not c.get("evidence"))}


CHAP = (("abstract", r"abstract|summary"), ("introduction", r"introduct|background"),
        ("methods", r"method|experimental|material|procedure|synthes"),
        ("results", r"result|finding"), ("discussion", r"discussion"),
        ("conclusion", r"conclusion|summary|outlook"), ("references", r"reference|bibliograph"))


def coverage(paras, answers):
    secs = {}
    for p in paras:
        secs[p["section"]] = secs.get(p["section"], 0) + 1
    cited = sorted({pid for a in answers for pid in a.get("evidence_paragraph_ids", [])})
    cited_sec = {p["section"] for p in paras if p["paragraph_id"] in cited}
    have = set()
    for s in secs:
        low = s.lower()
        for name, pat in CHAP:
            if re.search(pat, low):
                have.add(name)
    missing = [n for n, _ in CHAP if n not in have]
    only_abs = have and have <= {"abstract"}
    kinds = {p.get("kind", "paragraph") for p in paras}
    absent = [k for k in ("table", "figure_caption", "references") if k not in kinds]
    return {"paragraphs_supplied": len(paras), "paragraphs_indexed": len(paras),
            "paragraphs_cited": len(cited), "cited_paragraph_ids": cited,
            "sections_read": [{"section": k, "paragraphs": v} for k, v in sorted(secs.items())],
            "sections_cited": sorted(cited_sec),
            "sections_unread": missing if have else [],
            "unread_reason": ([] if not have else
                              [{"section": n, "reason": "only_abstract_supplied"} for n in missing]
                              if only_abs else
                              [{"section": n, "reason": "section_not_supplied"} for n in missing]),
            "read_status": ("section_labels_not_supplied" if not have else
                            "only_abstract_supplied" if only_abs else "full_text_sections_indexed"),
            "chars_supplied": sum(len(p["text"]) for p in paras),
            "not_supplied": S["missing"] + [f"材料未提供{k}（仅按提供的正文段作答）" for k in absent],
            "method": "全部供给段落解析为检索索引并逐题打分；引用集中于每题 top-k 段落",
            "note": "材料为已抽取文本，无 PDF 页图/像素，故无页码与图元读数；未做 OCR 与联网检索"}


# ------------------------------------------------------- text / value helpers
# v2: ASCII micro/degree spellings (um, 850 C) were missing in v1, so values such as
# "18 um" were treated as "not reported"; longest-first ordering keeps MPa before Pa etc.
U_LIT = ("Pa MPa GPa kPa hPa N kN mN J kJ MJ W mW kW mV kV V mA A Hz kHz MHz GHz dB ppm ppb rpm "
         "nm um µm μm mm cm mL uL µL μL L mg ug µg μg ng g kg mol/L mmol/L µmol/L mg/L g/L mg/g "
         "m2/g m²/g m2·g-1 mAh/g Wh/kg F/g C/g mS/cm S/cm h min ms s d K °C ℃ C eV keV"
         " vol% mol% wt% at%").split()
UNIT = "(?:" + "|".join(re.escape(u) for u in sorted(set(U_LIT), key=len, reverse=True)) \
    + r"|wt\.?\s?%|at\.?\s?%|vol\.?\s?%|mol\.?\s?%|%)"
VALRE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>" + UNIT + r")(?![A-Za-z])")
LABSTOP = frozenset("at in for with under after before during by of and or to from the a an was were is are "
                    "reached showed show observed observe than about approximately around vs on as which that "
                    "this respectively value values measured obtained gave give up down below above "
                    "decreased increased reduced rose dropped rose improved enhanced fell grew remains remained"
                    .split())
PREPS = frozenset("at under for in with during after before within between on over".split())
COND = re.compile(r"\b(at|under|during|in the presence of|after|before|for|with|when|while|using|"
                  r"vs\.?|compared (?:with|to)|pH|humidity|irradiat\w*|light|temperature|strain rate|"
                  r"heating|anneal\w*)\b", re.I)


def sents(text):
    spans, start = [], 0
    for m in re.finditer(r"(?<=[.!?;])\s+(?=[A-Z0-9(\[])", text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    out = []
    for a, b in spans:
        if not text[a:b].strip():
            continue
        if out and len(text[a:b].strip()) < 25:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return [(a, b, text[a:b].strip()) for a, b in out]


def widen(text, a, b, lo=15, hi=60):
    """Grow a short verbatim window to >= lo words (same paragraph, sentence-aware, <= hi)."""
    while len(text[a:b].split()) < lo:
        nxt = re.search(r"[.!?;]\s+", text[b:])
        prev = re.search(r"[.!?;]\s+(?=\S)", text[:a].rstrip())
        if nxt and len(text[a:b + nxt.end()].split()) <= hi:
            b += nxt.end()
        elif prev:
            a = prev.start() + 1
        else:
            break
    return text[a:b]


def clip(text, a, b, terms, hi=60, lo=15):
    """verbatim substring of text[a:b], lo..hi words, centred on the first term hit."""
    seg = text[a:b]
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", seg)]
    if len(words) <= hi:
        return widen(text, a, b, lo, hi).strip()
    low, pos = seg.lower(), 0
    for t in terms:
        p = low.find(t)
        if p >= 0:
            pos = p
            break
    idx = sum(1 for s, e in words if e <= pos)
    st = max(0, min(idx - 10, len(words) - hi))
    return text[a + words[st][0]:a + words[st + hi - 1][1]].strip()


def numfix(s):
    """1,250 -> 1250 (thousands separator); 2,4 -> 2.4 (decimal comma)."""
    s = str(s).strip()
    return s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")


UCLASS = (("温度", ("C", "°C", "℃", "K")), ("时间", ("h", "min", "s", "ms", "d")),
          ("尺寸/粒径", ("nm", "um", "µm", "μm", "mm", "cm", "m2/g", "m²/g")),
          ("浓度", ("mg/L", "mol/L", "mmol/L", "µmol/L", "g/L", "mg/g", "ppm", "ppb")),
          ("应力/强度/压力", ("MPa", "GPa", "kPa", "hPa", "Pa", "N", "kN")),
          ("百分比", ("%", "wt%", "at%", "vol%", "mol%")),
          ("质量", ("mg", "g", "kg", "µg", "μg", "ng")), ("体积", ("mL", "µL", "μL", "L")),
          ("电位", ("mV", "V", "kV")), ("功率", ("W", "mW", "kW")),
          ("能量", ("eV", "keV", "J", "kJ", "MJ")), ("频率", ("Hz", "kHz", "MHz", "GHz")))
FWD = {"to", "and", "or", "versus", "vs", "by", "respectively", "~", "-"}


def uclass(unit):
    for zh, us in UCLASS:
        if unit in us:
            return zh
    return "value"


def label(pre, prev=None, unit=""):
    """Label for a value (v2). Words after the previous value's unit only, so a
    following condition (at 850 C / for 1 h) never inherits the earlier quantity name."""
    last = None
    for m in VALRE.finditer(pre):
        last = m
    tail = pre[last.end():] if last else pre
    keep = [t for t in re.findall(r"[A-Za-z][A-Za-z0-9\-\./]*", tail)
            if t.lower().strip(".-") not in LABSTOP and not re.fullmatch(UNIT, t)
            and not t.lower().strip(".-").isdigit()]
    head = re.sub(r"[^A-Za-z]", " ", tail).lower().split()
    if any(w in head for w in ("higher", "lower", "more", "less", "increase", "decrease", "reduction",
                               "improvement", "than", "gain", "relative")) or \
            re.match(r"\s*(?:%\s*)?(higher|lower|more|less|greater|increase|decrease|reduction|improvement|than)",
                     sentence[sentence.find(m.group("num")) + len(m.group(0)) - len(unit):][:24] if False else
                     ""):
        return "相对变化"
    if keep and not (last is not None and head and head[-1] in PREPS):
        return " ".join(keep[-3:]).strip()
    if keep and last is not None and head and head[-1] in PREPS:
        return uclass(unit)  # "after annealing at 850 C": the value is the annealing temperature
    if last is not None and head and all(h in FWD for h in head) and prev:
        return prev  # "from 18 um to 2.4 um": same quantity, reuse the label
    return uclass(unit) if last is not None else (prev or uclass(unit))


def values(sentence, cap=4):
    """Numbers with units plus a clean label; one dict per distinct (value, unit)."""
    out, seen = [], set()
    for m in VALRE.finditer(sentence):
        pre = sentence[:m.start()].strip()
        if re.search(r"\b(table|tabletext|fig|figure|section|ref|page|eq|no)\.?\s*$|\[", pre[-20:], re.I):
            continue
        unit = (m.group("unit") or "").strip()
        prev_ch = sentence[m.start() - 1] if m.start() else " "
        if len(unit) == 1 and (prev_ch.isalnum() or prev_ch in "-_") :
            continue  # "ImageNet-1K" / "A100" are names, not measurements
        if len(unit) == 1 and sentence[m.end():m.end() + 1].isdigit():
            continue
        ex = re.match(r"(?:\^?-\d|[\u00b7\^]-\d)", sentence[m.end():])  # min-1, m^2 style exponents
        if ex and not unit.endswith(ex.group(0)):
            unit += ex.group(0)
        val = numfix(m.group("num"))
        if not unit and not re.search(r"(reached|=|of|about|≈|~|:)", pre[-18:], re.I):
            continue
        if (val, unit) in seen:
            continue
        seen.add((val, unit))
        lab = label(pre, out[-1]["label"] if out else None, unit) or "value"
        if re.match(r"\s*(?:%\s*)?(higher|lower|more|less|greater|increase|decrease|reduction|improvement|than|up to)",
                    sentence[m.end():m.end() + 20], re.I):
            lab = "相对变化"  # "18% higher than the T6 condition" is a delta, not a level
        out.append({"label": lab, "value": val, "unit": unit, "label_class": uclass(unit)})
        if len(out) >= cap:
            break
    return out


def cond_frag(sentence):
    for m in COND.finditer(sentence):  # v2: skip "for automotive body panels"-style phrases
        if m.group(1).lower() == "for" and not re.search(r"\d", sentence[m.end():m.end() + 12]):
            continue
        frag = sentence[m.start():]
        words = [(x.start(), x.end()) for x in re.finditer(r"\S+", frag)]
        return (frag[:words[13][1]] if len(words) > 14 else frag).strip(" ,.;:(")
    return None


CUE = re.compile(r"多少|多大|多高|多长|多强|几|什么|哪些|哪个|如何|为什么|为何|是否|有没有|能否|占比|比例|多少倍")


def split_subs(q):
    parts = re.split(r"[？?；;。\n]+|（\d）|\(\d\)", q)
    parts = [p.strip(" ，,、：:") for p in parts if len(p.strip(" ，,、：:")) >= 4]
    if len(parts) <= 1:  # v2: one sentence with two question foci -> split on the comma
        chunks = [c.strip(" ，,、：:") for c in re.split(r"[，,]", q) if c.strip(" ，,、：:")]
        if len(chunks) > 1 and sum(1 for c in chunks if CUE.search(c)) >= 2:
            parts = chunks
    return parts[:4] or [q.strip()]


def write_csv(out, meta, answers):
    import csv
    with (Path(out) / "evidence_map.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "paper_id", "question_id", "answer_status", "claim_id", "claim_kind",
                    "readability", "claim_text", "source_id", "paragraph_id", "section", "locator",
                    "char_start", "quote_words", "quote_verified", "quote"])
        for a in answers:
            for c in a["claims"]:
                for e in (c.get("evidence") or [{}]):
                    w.writerow([meta.get("case_id"), meta.get("paper_id"), a["question_id"], a["status"],
                                c["claim_id"], c["kind"], c.get("readability"), c["text"][:300],
                                meta.get("paper_id"), e.get("paragraph_id"), e.get("section"),
                                e.get("locator"), e.get("char_start"), e.get("quote_words"),
                                e.get("quote_verified"), e.get("quote")])


def mkclaim(qid, cid, text, kind, evs, conds=None):
    return {"claim_id": cid, "question_id": qid, "text": text, "kind": kind,
            "readability": "directly_read" if kind == "reported" else ("inferred" if evs else "undetermined"),
            "source_id": None, "conditions": conds or [],
            "evidence": [{"paper_id": None, "paragraph_id": e["paragraph_id"], "section": e["section"],
                          "locator": e["locator"], "quote": e["quote"], "char_start": e["char_start"],
                          "quote_verified": e["char_start"] >= 0,
                          "quote_words": len(e["quote"].split())} for e in evs]}
