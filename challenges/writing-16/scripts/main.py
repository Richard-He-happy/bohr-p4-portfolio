#!/usr/bin/env python3
"""main.py -- 科研成果转化写作脚手架: init / show / check / build. 标准库；离线；退出码恒 0。"""
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, time, traceback, zipfile, zlib
from datetime import datetime, timezone
from pathlib import Path

H = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(H))
try:
    import verify as vf
except Exception:
    vf = None
SK, VER, T0 = "research-translation-writing", "1.0.0", time.time()


def paths(a):
    i, o, w = (Path(a.input or os.environ.get("SKILL_INPUT") or "/input"),
               Path(a.output or os.environ.get("SKILL_OUTPUT") or "/app/output"),
               Path(a.work or os.environ.get("SKILL_WORK") or "/app/work"))
    n = []
    if not i.exists():
        for c in (H.parent / "input", Path.cwd() / "input"):
            if c.exists():
                n.append("输入 %s 不存在，改用 %s" % (i, c))
                i = c
                break
    for d, t in ((w, "work"), (o, "output")):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            alt = H.parent / t
            alt.mkdir(parents=True, exist_ok=True)
            n.append("%s 不可写→%s" % (d, alt))
            w, o = (alt, o) if t == "work" else (w, alt)
    return i, o, w, n


def wj(p, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def dec(b):
    for e in ("utf-8-sig", "gb18030", "utf-16", "latin-1"):
        try:
            return b.decode(e)
        except Exception:
            pass
    return b.decode("utf-8", "replace")


def pdf_text(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=90)
            if r.returncode == 0 and len(r.stdout.strip()) > 40:
                return dec(r.stdout), "pdftotext"
        except Exception:
            pass
    try:
        data = p.read_bytes()
    except Exception:
        return "", "unreadable"
    parts = []
    for m in re.finditer(rb"stream\r?\n", data):
        e = data.find(b"endstream", m.end())
        if e <= 0:
            continue
        b = data[m.end():e]
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        if b"Tj" in b or b"TJ" in b:
            parts.append(" ".join(x.decode("latin-1") for x in re.findall(rb"\(([^()\\]{2,})\)", b)))
    t = re.sub(r"[ \t]{2,}", " ", "\n".join(parts)).strip()
    return t, ("builtin-pdf" if len(re.sub(r"\s", "", t)) > 200 else "builtin-pdf-lowconf")


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        x = z.read("word/document.xml").decode("utf-8", "replace")
    x = re.sub(r"</w:p>", "\n\n", re.sub(r"<w:(tab|br)[^>]*/>", "\t", x))
    return html.unescape(re.sub(r"<[^>]+>", "", x))


def xlsx_text(p):
    out = []
    with zipfile.ZipFile(p) as z:
        sh = []
        if "xl/sharedStrings.xml" in z.namelist():
            sh = [html.unescape(re.sub(r"<[^>]+>", "", si)) for si in
                  re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)]
        for n in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
            for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(n).decode("utf-8", "replace"), re.S):
                cs = []
                for c in re.findall(r"<c[^>]*?(?:/>|>.*?</c>)", row, re.S):
                    v, ty = re.search(r"<v>(.*?)</v>", c, re.S), re.search(r't="(\w+)"', c)
                    val = v.group(1) if v else ""
                    if val.isdigit() and ty and ty.group(1) == "s" and int(val) < len(sh):
                        val = sh[int(val)]
                    cs.append(val)
                out.append("\t".join(cs))
    return "\n".join(r for r in out if r.strip())


def kind_of(p):
    e = p.suffix.lower().lstrip(".")
    try:
        h = p.open("rb").read(8)
    except Exception:
        h = b""
    if h.startswith(b"%PDF"):
        return "pdf"
    if h.startswith(b"PK\x03\x04"):
        return e if e in ("docx", "xlsx") else "zip"
    if h[:3] == b"\xff\xd8\xff" or h[:4] == b"\x89PNG":
        return "image"
    return {"md": "text", "txt": "text", "csv": "text", "tsv": "text", "json": "json",
            "tex": "text", "html": "text", "htm": "text", "xml": "text"}.get(e, e or "unknown")


def extract(p):
    k = kind_of(p)
    try:
        if k == "pdf":
            return pdf_text(p)
        if k == "docx":
            return docx_text(p), "docx-xml"
        if k == "xlsx":
            return xlsx_text(p), "xlsx-xml"
        if k == "json":
            o = rj(p)
            return "\n".join(x.strip('"') for x in re.findall(r'"([^"]{3,})"', json.dumps(o, ensure_ascii=False))), "json-leaves"
        if k == "image":
            return "", "image-no-ocr"
        if k in ("pptx", "zip"):
            return "", "unsupported:" + k
        t = dec(p.read_bytes())
        head = t[:2000]
        if head and sum(c.isprintable() or c in "\n\t " for c in head) / len(head) < .85:
            return "", "binary-skip"
        return t, ("text" if k in ("text", "csv") else "raw-bytes")
    except Exception as e:
        return "", "failed:%s" % type(e).__name__


def split_paras(t):
    out = []
    for b in [x.strip() for x in re.split(r"\n\s*\n", (t or "").replace("\r\n", "\n").replace("\r", "\n")) if x.strip()]:
        for s in ([x.strip() for x in re.split(r"\n(?=\S)", b) if x.strip()] if len(b) > 1400 else [b]):
            if len(s) <= 1400:
                out.append(s)
                continue
            cur = ""
            for piece in re.split(r"(?<=[。！？；.!?])\s*", s):
                cur += piece
                if len(cur) >= 700:
                    out.append(cur.strip())
                    cur = ""
            if cur.strip():
                out.append(cur.strip())
    return [re.sub(r"[ \t]+", " ", x) for x in out]


def scan(inp):
    mats, degr = [], []
    files = [p for p in sorted(inp.rglob("*")) if p.is_file() and not p.name.startswith(".")]
    case = cpath = None
    if (inp / "case.json").is_file():
        try:
            case, cpath = rj(inp / "case.json"), inp / "case.json"
        except Exception as e:
            degr.append("case.json 解析失败：%s" % type(e).__name__)
    if case is None:
        for p in files:
            if p.suffix.lower() == ".json":
                try:
                    o = rj(p)
                except Exception:
                    continue
                if isinstance(o, dict) and "output_contract" in o:
                    case, cpath = o, p
                    break
    for p in files:
        if (cpath and p == cpath) or p.name == "case.json":
            continue
        text, how = extract(p)
        mats.append({"name": p.name, "path": str(p), "kind": kind_of(p), "method": how, "text": text,
                     "chars": len(text), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
                     "role": "instruction" if re.match(r"task.*\.md$", p.name, re.I) else "material"})
        if how.startswith("failed") or how == "unreadable":
            degr.append("%s 解析失败(%s)，未入索引" % (p.name, how))
        elif how == "image-no-ocr":
            degr.append("%s 为图片，未 OCR" % p.name)
        elif how.startswith("unsupported") or how == "binary-skip":
            degr.append("%s 类型不支持（%s），未入索引，需人工提供文本" % (p.name, how))
        elif how.startswith("builtin-pdf"):
            degr.append("%s 用内置 PDF 解析（无 pdftotext），多栏可能错序" % p.name)
    return case, cpath, mats, degr


def fkeys(o, out=None):
    out = {} if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            out.setdefault(str(k).lower(), v)
            fkeys(v, out)
    elif isinstance(o, list):
        for v in o:
            fkeys(v, out)
    return out


def pick(f, *names):
    for n in names:
        v = f.get(n)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
        if isinstance(v, dict):
            for k in ("label", "name", "value", "text"):
                if isinstance(v.get(k), str) and v[k].strip():
                    return v[k].strip()
        if isinstance(v, list) and v and isinstance(v[0], str):
            return "; ".join(v)[:300]
    return None


AUD = (("产业界", r"产业界|企业|公司|工业|投资|商业化|licens|industry|合作方"),
       ("基金/项目评审", r"基金|资助|评审|申报|立项|funder|grant|panel"),
       ("政策部门", r"政策|监管|政府|决策|policy"),
       ("非专业公众", r"公众|大众|科普|媒体|新闻|public|lay"))
GEN = (("技术转化简报", r"简报|白皮书|技术报告|一页纸|brief|whitepaper"),
       ("项目申报摘要", r"申报|提案|proposal|立项"),
       ("科普文章", r"科普|新闻稿|通稿|博客|press|popular"),
       ("论文摘要", r"abstract|论文摘要"))


def workorder(case, instr):
    f = fkeys(case or {})
    wo = {"audience": pick(f, "audience", "target_audience", "readers", "reader", "受众"),
          "genre": pick(f, "genre", "format", "text_type", "文体", "体裁"),
          "length": pick(f, "length", "word_limit", "max_words", "word_count", "max_length", "篇幅"),
          "instruction": pick(f, "task_instruction", "instruction", "task", "prompt") or instr,
          "caller_note": pick(f, "organizer_workorder", "organizer_edit_workorder", "workorder", "requirements"),
          "basis": {}}
    t = "%s\n%s" % (instr or "", wo["instruction"] or "")
    for key, rules in (("audience", AUD), ("genre", GEN)):
        for label, pat in (() if wo[key] else rules):
            m = re.search(pat, t, re.I)
            if m:
                wo[key], wo["basis"][key] = label, m.group(0)
                break
    if not wo["length"]:
        m = re.search(r"(\d{2,5})\s*(?:字|词|words?)", t, re.I)
        if m:
            wo["length"], wo["basis"]["length"] = m.group(1) + " 字", m.group(0)
    return wo


def build_index(case, cpath, mats, instr):
    ps, ms = [], []
    for i, m in enumerate(mats, 1):
        mid, pp = "M%d" % i, split_paras(m["text"])
        ms.append({k: m[k] for k in ("name", "path", "kind", "method", "role", "chars", "sha256")})
        ms[-1].update({"id": mid, "paragraphs": len(pp)})
        ps += [{"loc": "%s:P%d" % (mid, j), "mat": mid, "text": t, "role": m["role"], "chars": len(t)}
               for j, t in enumerate(pp, 1)]
    body = "\n".join(p["text"] for p in ps if p["role"] != "instruction")
    vals, prs = vf.extract_numbers(body) if vf else (set(), set())
    allt = "\n".join(p["text"] for p in ps)
    return {"case_id": (case or {}).get("case_id") or (case or {}).get("id") or "UNKNOWN-CASE",
            "output_contract": (case or {}).get("output_contract") or {},
            "case_path": str(cpath) if cpath else None, "workorder": workorder(case, instr),
            "materials": ms, "paragraphs": ps,
            "norm_exact": vf.normalize(allt) if vf else allt,
            "norm_loose": vf.normalize(allt, True) if vf else allt,
            "numbers": sorted(vals), "pairs": sorted(prs),
            "acronyms": sorted(vf.extract_acronyms(body)) if vf else [],
            "key_numbers": sorted(p for p in prs if re.search(r"[%‰]|mg|kg|mL|mol|M|h|min|d|nM|mM|μ|µ", p))[:80],
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


STUB = {"_readme": "init 生成，由 Agent 填写，勿直接提交：sections 写完整正文（非提纲）；preserved 填必保留项；"
                   "map 做逐段来源对照；changes 记删改与理由。",
        "audience": {"label": "", "profile": "", "reading_goal": "", "knowledge": "", "depth": "",
                     "term_policy": "", "strength_policy": ""},
        "genre": {"label": "", "conventions": [], "length_target": 0, "length_unit": "字"},
        "headline": "", "deck": "", "sections": [], "preserved": [], "map": [], "changes": [],
        "removed": [], "glossary": [], "pending": [], "uncertainty": []}


def stub(idx):
    d = json.loads(json.dumps(STUB))
    wo = idx.get("workorder") or {}
    d["audience"]["label"], d["genre"]["label"] = wo.get("audience") or "", wo.get("genre") or ""
    m = re.search(r"(\d{2,5})", wo.get("length") or "")
    d["genre"]["length_target"] = int(m.group(1)) if m else 0
    return d


def load_draft(w):
    p = Path(w) / "draft.json"
    if not p.is_file():
        return None, "draft.json 不存在"
    try:
        return rj(p), None
    except Exception as e:
        return None, "draft.json 解析失败：%s" % type(e).__name__


def tb(head, rows):
    o = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    o += ["| " + " | ".join(str(c or "").replace("|", "/").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(o)


def render(c, d, rep):
    a, g, st = d.get("audience") or {}, d.get("genre") or {}, rep.get("stats") or {}
    n, tgt = st.get("body_words", 0), c["target"]
    spec = "\n".join("- **%s**：%s" % (k, v) for k, v in (
        ("读者画像", a.get("profile") or "未填写（需人工补充）"),
        ("阅读目的", a.get("reading_goal") or "未填写"),
        ("知识假设", a.get("knowledge") or "未填写"),
        ("解释深度", a.get("depth") or "未填写"),
        ("术语策略", a.get("term_policy") or "未填写"),
        ("论断强度", a.get("strength_policy") or "未填写"),
        ("体裁惯例", "；".join(g.get("conventions") or []) or "未填写"),
        ("篇幅", "目标 %s / 实际 %s 字（%s）" % (tgt or g.get("length_target") or "未指定", n,
                                          "符合" if c["ok_len"] else "偏离，见自检")),
        ("取舍原则", "必保留结论/数字与单位/条件与样本/图表引用/不确定性；可压缩方法细节与文献罗列；"
                    "可删重复表述与无关推导")))
    smap, secs, rows = {}, [], []
    for m in d.get("map") or []:
        smap.setdefault(str(m.get("section_id")), []).append(m)
    for i, s in enumerate(d.get("sections") or [], 1):
        sid = str(s.get("id") or "S%d" % i)
        ct = s.get("cites")
        secs.append("### %d. %s\n\n%s\n\n〔来源：%s ｜ 强度：%s〕\n" % (
            i, s.get("title") or "", (s.get("text") or "").strip(),
            "、".join(ct) if isinstance(ct, list) else (ct or "见对照表"), s.get("strength") or "未标注"))
        for m in smap.get(sid) or [{}]:
            rows.append([sid, m.get("source_locator") or "未标注", (m.get("source_quote") or "")[:110],
                         m.get("relation") or "缺对照", m.get("note") or ""])
    cmp_t = tb(["段落", "源文位置", "源文要旨（逐字）", "处理", "说明"], rows or [["—"] * 5])
    pres_t = tb(["编号", "类型", "值", "源位置", "原文", "处理"],
                [[x.get("id") or "", x.get("kind") or "", x.get("value") or "", x.get("locator") or "",
                  (x.get("quote") or "")[:100], x.get("treatment") or "kept"] for x in d.get("preserved") or []]
                or [["—"] * 6])
    chg_t = tb(["编号", "动作", "源位置", "原文", "改后/删除", "理由"],
               [["C%d" % i, x.get("action") or "", x.get("locator") or "", (x.get("original_quote") or "")[:90],
                 (x.get("revised_quote") or "")[:90], x.get("reason") or ""]
                for i, x in enumerate(d.get("changes") or [], 1)] or [["—", "verbatim", "—", "—", "—", "未记录"]])
    rem = "\n".join("- `%s` %s：%s（%s）" % (x.get("locator") or "-", x.get("item") or "", x.get("why") or "",
                                           x.get("action") or "删除") for x in d.get("removed") or []) or "- 无"
    glo = "\n".join("- **%s**：%s；统一用「%s」（%s）" % (
        x.get("term") or "", x.get("expansion") or "—", x.get("usage") or x.get("term") or "",
        x.get("locator") or "—") for x in d.get("glossary") or []) or "- 无"
    pl = "\n".join("- **待确认**：%s（原因：%s；动作：%s）" % (
        p.get("issue") or "—", p.get("why") or "—", p.get("action") or p.get("owner") or "作者确认")
        for p in list(d.get("pending") or []) + list(rep.get("pending") or [])) or "- 无"
    ul = "\n".join("- " + (u if isinstance(u, str) else json.dumps(u, ensure_ascii=False))
                   for u in list(d.get("uncertainty") or []) + c["unc"]) or "- 无"
    fb = ("> ⚠ **兜底稿**：工作稿缺失或不可用，本文件由脚本从源材料确定性抽取，**未完成受众改写**，"
          "仅供在此基础上继续写。\n") if c["fallback"] else ""
    basis = "；".join("`%s`→%s" % kv for kv in (c["basis"] or {}).items()) or "题面未给显式依据，按体裁常规"
    return f"""# {d.get('headline') or '科研成果转化稿'}

{f'> {d["deck"]}' if d.get('deck') else ''}

> 状态 **{c['status']}** ｜ 受众 **{a.get('label') or '未指定'}** ｜ 体裁 **{g.get('label') or '未指定'}** ｜ 目标 {tgt or '未指定'} 字 / 实际 {n} 字

{fb}
## 一、适配说明（受众 / 体裁 / 篇幅）

{spec}

判定依据：{basis}

## 二、转化稿正文

{chr(10).join(secs) if secs else '（无正文：材料或工作稿缺失）'}

## 三、改编前后对照（逐段）

{cmp_t}

## 四、必保留项清单（事实 / 数字 / 术语）

{pres_t}

## 五、删改清单（含 Change log）

{chg_t}

未进入成稿的内容：
{rem}

## 六、术语与缩写表

{glo}

## 七、待确认与不确定性

{pl}

{ul}

## 八、自检结果

- 段落 {st.get('sections')}；正文 {n} 字；引文命中 {st.get('quote_hit')}/{st.get('quote_total')}；段落对照 {st.get('paragraphs_used')}/{st.get('material_paragraphs')}
- 数字：成稿 {st.get('numbers_in_body')} 个 / 源文 {st.get('numbers_in_source')} 个 / 不匹配 {len(st.get('number_errors') or [])} 个
- 校验错误 {len(rep.get('errors') or [])} 条、提示 {len(rep.get('warnings') or [])} 条（详见 result.json）
"""


def fallback_draft(idx, wo):
    pool = [(p["loc"], s.strip()) for p in idx.get("paragraphs", []) if p.get("role") != "instruction"
            for s in re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+", p.get("text") or "") if len(s.strip()) >= 12]
    if not pool:
        return None
    m = re.search(r"(\d{2,5})", wo.get("length") or "")
    cap, used = (int(m.group(1)) if m else 900), 0
    secs, pres, mp, seen = [], [], [], set()
    for i, (name, pat, lim) in enumerate([
            ("要点摘录（原文句子，未改写）", r"[\s\S]", 4),
            ("关键数字与结果（原文句子，未改写）", r"[%‰]|\d", 8),
            ("条件与局限（原文句子，未改写）",
             r"局限|限制|尚需|有待|初步|提示|可能|未能|不足|limit|caveat|preliminary|suggest", 5)], 1):
        items = []
        for loc, s in pool:
            if len(items) >= lim or used + len(s) > cap:
                break
            if re.search(pat, s, re.I) and s not in seen:
                items.append((loc, s))
                seen.add(s)
                used += len(s)
        if not items:
            continue
        secs.append({"id": "F%d" % i, "title": name, "text": "\n\n".join(x[1] for x in items),
                     "cites": [x[0] for x in items], "strength": "source-verbatim"})
        mp.append({"section_id": "F%d" % i, "source_locator": items[0][0], "source_quote": items[0][1],
                   "relation": "quoted", "note": "兜底：逐字摘录，未做受众改写"})
        for loc, s in items:
            for v in sorted((vf.extract_numbers(s)[1] if vf else set()))[:4]:
                pres.append({"id": "F%d" % (len(pres) + 1), "kind": "number", "value": v, "locator": loc,
                             "quote": s, "treatment": "kept"})
    if not secs:
        return None
    return {"audience": {"label": wo.get("audience") or "未指定"},
            "genre": {"label": wo.get("genre") or "未指定", "length_target": cap, "length_unit": "字"},
            "headline": "源材料要点抽取（兜底稿）", "deck": "脚本兜底：未完成受众改写，仅保留原文句子与定位",
            "sections": secs, "preserved": pres, "map": mp, "removed": [], "glossary": [],
            "changes": [{"action": "verbatim-extract", "locator": secs[0]["cites"][0],
                         "original_quote": secs[0]["text"].split("\n\n")[0],
                         "revised_quote": secs[0]["text"].split("\n\n")[0],
                         "reason": "工作稿缺失，仅抽取以保证有可核对产物"}],
            "pending": [{"issue": "未按目标受众/体裁改写", "why": "draft.json 缺失或不可用",
                         "action": "按 references/genre-playbook.md 改写后重跑 build"}],
            "uncertainty": ["兜底稿为原文抽取，可读性与篇幅未满足目标体裁"]}


def finalize(out, idx, d, rep, c, errs):
    contract, st = (idx or {}).get("output_contract") or {}, rep.get("stats") or {}
    cid = (idx or {}).get("case_id") or "UNKNOWN-CASE"
    res = {"case_id": cid, "status": c["status"], "self_check": st,
           "deliverable": {"file": "deliverable.md", "format": "markdown",
                           "audience": (d.get("audience") or {}).get("label"),
                           "genre": (d.get("genre") or {}).get("label"),
                           "length": {"target": c["target"], "unit": "字", "actual": st.get("body_words")},
                           "sections": [x.get("title") for x in (d.get("sections") or [])],
                           "fallback": c["fallback"]},
           "preserved_facts": d.get("preserved") or [], "evidence_map": d.get("map") or [],
           "change_log": d.get("changes") or [], "changes": d.get("changes") or [],
           "glossary": d.get("glossary") or [], "removed": d.get("removed") or [],
           "transformation_spec": {"audience": d.get("audience") or {}, "genre": d.get("genre") or {},
                                   "note": "适配说明见 deliverable.md 第一节"},
           "uncertainty": list(d.get("uncertainty") or []) + c["unc"],
           "pending_human": list(d.get("pending") or []) + list(rep.get("pending") or []),
           "errors": list(errs) + [e.get("msg") for e in (rep.get("errors") or [])],
           "degradations": c["degr"], "workorder": (idx or {}).get("workorder") or {},
           "sources": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "role": m["role"],
                        "method": m["method"], "paragraphs": m["paragraphs"], "chars": m["chars"],
                        "sha256_16": m["sha256"], "path": m["path"]} for m in (idx or {}).get("materials", [])]}
    for f in contract:
        res.setdefault(f, [] if any(h in f.lower() for h in ("list", "map", "log", "facts")) else None)
    if vf:
        filled, crep = vf.fill_contract(contract, {
            "case_id": cid, "deliverable": res["deliverable"], "preserved_facts": res["preserved_facts"],
            "evidence_map": res["evidence_map"], "change_log": res["change_log"], "glossary": res["glossary"],
            "removed": res["removed"], "uncertainty": res["uncertainty"], "pending_human": res["pending_human"],
            "status": res["status"], "audience": d.get("audience") or {}, "genre": d.get("genre") or {},
            "length": res["deliverable"]["length"]})
        res.update(filled)
        res["contract_fill"] = crep
        if crep["null_fields"]:
            res["degradations"].append("契约字段无法匹配产出，置空：%s" % ", ".join(crep["null_fields"]))
    res["runtime"] = {"skill": SK, "version": VER, "python": sys.version.split()[0],
                      "started_at": datetime.fromtimestamp(T0, timezone.utc).isoformat(timespec="seconds"),
                      "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "elapsed_s": round(time.time() - T0, 1), "input_dir": str(c["inp"]),
                      "output_dir": str(out), "work_dir": str(c["wrk"]),
                      "files": {p.name: p.stat().st_size for p in sorted(out.glob("*")) if p.is_file()},
                      "counts": {"materials": len(idx.get("materials", [])),
                                 "paragraphs": len(idx.get("paragraphs", [])),
                                 "sections": len(d.get("sections") or []),
                                 "errors": len(res["errors"]), "pending": len(res["pending_human"])}}
    wj(out / "result.json", res)
    res["runtime"]["files"] = {p.name: p.stat().st_size for p in sorted(out.glob("*")) if p.is_file()}
    wj(out / "result.json", res)
    return res


def cmd_init(a):
    inp, out, wrk, notes = paths(a)
    wj(out / "result.json", {"case_id": "UNKNOWN-CASE", "status": "partial", "sources": [],
                             "degradations": ["init 启动"], "errors": [], "runtime": {}})
    case, cpath, mats, degr = scan(inp)
    instr = dec((inp / "task.md").read_bytes()) if (inp / "task.md").is_file() else ""
    idx = build_index(case, cpath, mats, instr)
    wj(wrk / "index.json", idx)
    fresh = not (wrk / "draft.json").is_file()
    if fresh:
        wj(wrk / "draft.json", stub(idx))
    res = {"case_id": idx["case_id"], "status": "partial", "degradations": degr + notes + ["索引完成，待工作稿"],
           "sources": [{k: m[k] for k in ("id", "name", "kind", "role", "method", "paragraphs")}
                       for m in idx["materials"]],
           "pending_human": ["工作稿未完成，deliverable.md 未生成"], "errors": [], "uncertainty": [],
           "preserved_facts": [], "evidence_map": [], "change_log": [], "deliverable": None,
           "runtime": {"skill": SK, "version": VER, "elapsed_s": round(time.time() - T0, 1)}}
    for f in idx["output_contract"]:
        res.setdefault(f, [] if any(h in f.lower() for h in ("list", "map", "log", "facts")) else None)
    wj(out / "result.json", res)
    wo = idx["workorder"]
    L = ["== 材料索引 =="] + ["%-4s %-24s %-5s %-17s %6d字/%3d段 [%s]" % (
        m["id"], m["name"][:24], m["kind"], m["method"], m["chars"], m["paragraphs"], m["role"])
        for m in idx["materials"]] or ["(无材料)"]
    L += ["", "== 工作单 ==", "case_id: %s" % idx["case_id"],
          "受众: %s%s" % (wo.get("audience") or "未识别（按题面确认）",
                         "  <- `%s`" % wo["basis"]["audience"] if wo["basis"].get("audience") else ""),
          "体裁: %s" % (wo.get("genre") or "未识别"), "篇幅: %s" % (wo.get("length") or "未限定"),
          "契约: %s（%d 字段）" % (", ".join(idx["output_contract"]) or "无", len(idx["output_contract"])),
          "", "== 段落（前 40；共 %d） ==" % len(idx["paragraphs"])]
    L += ["%-10s %5d字  %s" % (p["loc"], p["chars"], p["text"][:54].replace("\n", " ")) for p in idx["paragraphs"][:40]]
    L += ["", "== 关键数字 =="] + ["  " + k for k in idx["key_numbers"][:15]]
    L += ["", "== 缩写 ==", "  " + (", ".join(idx["acronyms"][:25]) or "未检出"), "",
          "下一步：按 references/draft-schema.md 写 %s，再 check → build。" % (wrk / "draft.json")]
    print("\n".join(L))
    return 0


def load_index(w):
    p = Path(w) / "index.json"
    if not p.is_file():
        return None, "index.json 不存在（先 init）"
    try:
        return rj(p), None
    except Exception as e:
        return None, "index.json 解析失败：%s" % type(e).__name__


def cmd_show(a):
    _, _, wrk, _ = paths(a)
    idx, err = load_index(wrk)
    if err:
        print("无法显示：%s" % err)
        return 0
    sel = [p for p in idx["paragraphs"] if not a.mat or p["mat"] == a.mat]
    if a.ids:
        want = set()
        for part in re.split(r"[,\s]+", a.ids.strip()):
            m = re.match(r"(M\d+):P(\d+)-(?:M\d+:)?P?(\d+)$", part)
            if m:
                want |= {"%s:P%d" % (m.group(1), i) for i in range(int(m.group(2)), int(m.group(3)) + 1)}
            elif part:
                want.add(part)
        sel = [p for p in sel if p["loc"] in want]
    if a.grep:
        try:
            rx = re.compile(a.grep, re.I)
        except re.error:
            rx = re.compile(re.escape(a.grep), re.I)
        sel = [p for p in sel if rx.search(p["text"])]
    n = max(1, a.limit)
    for p in sel[:n]:
        print("[%s] (%d字)\n%s\n" % (p["loc"], p["chars"], p["text"]))
    print("-- 匹配 %d 段，显示 %d；材料 %s" % (len(sel), min(len(sel), n), ", ".join(
        "%s=%s(%s)" % (m["id"], m["name"], m["method"]) for m in idx["materials"])))
    return 0


def cmd_check(a):
    _, out, wrk, _ = paths(a)
    idx, err = load_index(wrk)
    rep = {"status": "partial", "errors": [], "warnings": [], "pending": [], "stats": {}}
    if err:
        rep["errors"].append({"code": "no_index", "msg": err})
    else:
        d, derr = load_draft(wrk)
        if derr:
            rep["errors"].append({"code": "no_draft", "msg": derr})
        elif vf:
            rep = vf.check_draft(d, idx)
            try:
                miss = vf.contract_missing(rj(out / "result.json"), idx.get("output_contract") or {})
                if miss:
                    rep["warnings"].append({"code": "contract_missing", "msg": "result.json 缺契约字段：" + ", ".join(miss)})
            except Exception:
                pass
    wj(wrk / "check.json", rep)
    st = rep["stats"]
    print("== check ==\n状态 %s | 段落 %s | 正文 %s 字 | 引文 %s/%s | 数字 %s（不匹配 %s）" % (
        rep["status"], st.get("sections"), st.get("body_words"), st.get("quote_hit"), st.get("quote_total"),
        st.get("numbers_in_body"), len(st.get("number_errors") or [])))
    for e in rep["errors"]:
        print("  [错误] " + str(e.get("msg")))
    for w in rep["warnings"]:
        print("  [提示] " + str(w.get("msg")))
    print("报告 %s" % (wrk / "check.json"))
    return 0


def cmd_build(a):
    inp, out, wrk, notes = paths(a)
    degr, errs = list(notes), []
    idx, err = load_index(wrk)
    if idx is None:
        case, cpath, mats, d2 = scan(inp)
        instr = dec((inp / "task.md").read_bytes()) if (inp / "task.md").is_file() else ""
        idx, degr = build_index(case, cpath, mats, instr), degr + d2 + ["index.json 缺失，build 内重建"]
    d, derr = load_draft(wrk)
    rep = {"status": "partial", "errors": [], "warnings": [], "pending": [], "stats": {}}
    fb = bool(derr)
    if derr:
        errs.append(derr)
    else:
        rep = vf.check_draft(d, idx) if vf else rep
        fb = not any(str(x.get("text") or "").strip() for x in d.get("sections") or [] if isinstance(x, dict))
    if fb:
        alt = fallback_draft(idx, idx.get("workorder") or {})
        if alt:
            d, fb = alt, True
            degr.append("工作稿缺失或不可用 → 确定性抽取兜底（未做受众改写）")
            if vf:
                rep = vf.check_draft(d, idx)
        elif not d:
            d = stub(idx)
            d["headline"] = "无可用材料：未生成转化稿"
            degr.append("无材料或无工作稿，deliverable 仅含占位说明")
    tgt = 0
    for src in ((idx.get("workorder") or {}).get("length"), (d.get("genre") or {}).get("length_target")):
        m = re.search(r"(\d{2,5})", str(src or ""))
        if m:
            tgt = m.group(1)
            tgt = int(tgt)
            break
    st = rep.get("stats") or {}
    n = st.get("body_words") or 0
    c = {"status": "partial", "fallback": fb, "inp": inp, "wrk": wrk, "target": tgt,
         "ok_len": bool(tgt and 0.7 <= n / tgt <= 1.5), "degr": degr, "unc": [],
         "basis": (idx.get("workorder") or {}).get("basis") or {}}
    if not [p for p in idx["paragraphs"] if p["role"] != "instruction"]:
        c["status"] = "insufficient_evidence"
        c["unc"].append("输入无可解析事实材料，仅生成占位稿")
    elif not fb and rep["status"] == "ok":
        c["status"] = "ok"
    if not (idx.get("output_contract") or {}):
        degr.append("输入无 output_contract，result.json 仅含内置字段")
    if not (idx.get("workorder") or {}).get("audience"):
        c["unc"].append("受众按默认推断，需作者确认")
    if not tgt:
        c["unc"].append("篇幅无明确上限，按体裁常规处理")
    (out / "deliverable.md").write_text(render(c, d, rep), encoding="utf-8")
    res = finalize(out, idx, d, rep, c, errs)
    print("== build ==\nstatus=%s fallback=%s 字数=%s 目标=%s 文件=%s" % (
        res["status"], fb, n, tgt or "-", sorted(res["runtime"]["files"])))
    print("errors %d | pending %d | degradations %d" % (
        len(res["errors"]), len(res["pending_human"]), len(res["degradations"])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="科研成果转化写作（%s v%s）：索引→校验→成稿" % (SK, VER))
    ap.add_argument("--input", default="", help="输入目录，默认 /input")
    ap.add_argument("--output", default="", help="产物目录，默认 /app/output")
    ap.add_argument("--work", default="", help="工作目录，默认 /app/work")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init", help="扫描输入、建索引、写 partial result.json 与 draft 模板")
    sp = sub.add_parser("show", help="按 locator/关键词打印原文")
    sp.add_argument("--ids", default="", help="如 M1:P1-M1:P6")
    sp.add_argument("--grep", default="", help="正则或关键词")
    sp.add_argument("--mat", default="", help="只看某材料，如 M1")
    sp.add_argument("--limit", type=int, default=40)
    sub.add_parser("check", help="校验工作稿：引文/数字/结构/覆盖")
    sub.add_parser("build", help="生成 deliverable.md 并 finalize result.json")
    a = ap.parse_args(argv)
    cmd = a.cmd or "init"
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[cmd](a)
    except Exception as e:
        try:
            _, out, _, _ = paths(a)
            wj(out / "result.json", {
                "case_id": "UNKNOWN-CASE", "status": "partial", "sources": [], "uncertainty": [],
                "preserved_facts": [], "evidence_map": [], "change_log": [], "degradations": [],
                "errors": ["%s: %s" % (type(e).__name__, e), traceback.format_exc()[-600:]],
                "pending_human": ["需人工重跑"],
                "runtime": {"skill": SK, "version": VER, "elapsed_s": round(time.time() - T0, 1)}})
            if cmd != "show":
                (out / "deliverable.md").write_text(
                    "# 交付说明\n\n运行在 `%s` 阶段异常：%s\n\n兜底记录见 result.json 的 errors。\n" % (cmd, e),
                    encoding="utf-8")
        except Exception:
            pass
        print("异常已兜底：%s: %s" % (type(e).__name__, e))
        return 0


if __name__ == "__main__":
    sys.exit(main())
