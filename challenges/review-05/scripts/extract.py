# -*- coding: utf-8 -*-
"""review-05 解析/定位/检出库：材料解析、行号级定位索引、引用结构、确定性候选检出。仅标准库。"""
import html
import json
import re
import unicodedata
import zipfile
import zlib
from pathlib import Path

VERSION = "1.0.0"
FACETS = [("fact_verification", "事实核验"), ("citation_support", "引用支持"), ("method_design", "方法设计"),
          ("statistical_reporting", "统计报告"), ("argument_chain", "论证链"), ("academic_norms", "学术规范")]
FKEYS = [k for k, _ in FACETS]
FZH = dict(FACETS)
ZH2F = dict((v, k) for k, v in FACETS)
SEVS = ("blocker", "major", "minor", "suggestion")
VTYPES = ("error", "insufficient_evidence", "norm_violation", "suggestion")
CSTAT = ("pass", "issues_found", "not_applicable", "not_checked", "incomplete")
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif", ".eps", ".svg"}
CAP_FILES, CAP_BYTES, CAP_CANDS = 50, 8 << 20, 120


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    for a, b in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u00a0", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def squash(s):
    return re.sub(r"\s+", "", norm(s))


def snip(s, n=260):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- 文档解析
ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "", "f": "", "(": "(", ")": ")", "\\": "\\"}


def _lit(b):
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "ignore")
    s = b.decode("latin-1", "ignore")
    s = re.sub(r"\\([nrtbf()\\])", lambda m: ESC[m.group(1)], s)
    return re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), s)


def _ops(s):
    buf, out = [], []
    for m in re.finditer(rb"\((?:\\.|[^\\()])*\)|\[[^\]]*\]|T[dD*]|Tj|TJ|ET", s):
        t = m.group(0)
        if t[:1] == b"(":
            buf.append(_lit(t[1:-1]))
        elif t[:1] == b"[":
            buf += [_lit(x[1:-1]) for x in re.findall(rb"\((?:\\.|[^\\()])*\)", t)]
        elif buf:
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return "\n".join(x for x in out if x.strip())


def pdf_text(data, errs):
    out = []
    for m in re.finditer(rb"(?<![A-Za-z])stream\r?\n?", data):
        e = data.find(b"endstream", m.end())
        if e < 0:
            continue
        try:
            dec = zlib.decompress(data[m.end():e])
        except Exception:
            dec = data[m.end():e]
        if b"Tj" in dec or b"TJ" in dec:
            t = _ops(dec)
            if t.strip():
                out.append(t)
    if not out:
        errs.append("pdf_no_text_layer: 需 OCR 或改交可读文本")
    return "\n\n".join(out)


def xml_text(raw):
    raw = re.sub(r"</w:p>|</a:p>", "\n\n", raw)
    raw = re.sub(r"<w:tab[^>]*/>", "\t", raw)
    raw = re.sub(r"<w:br[^>]*/>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", "", raw))


def docx_text(p, errs):
    try:
        with zipfile.ZipFile(p) as z:
            return xml_text(z.read("word/document.xml").decode("utf-8", "ignore"))
    except Exception as e:
        errs.append("docx_parse_failed: %s: %s" % (p.name, e))
        return ""


def xlsx_text(p, errs):
    out, sh = [], []
    try:
        with zipfile.ZipFile(p) as z:
            try:
                sh = [html.unescape(re.sub(r"<[^>]+>", "", x)) for x in re.findall(
                    r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"), re.S)]
            except KeyError:
                pass
            for w in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
                out.append("## " + w.split("/")[-1])
                for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(w).decode("utf-8", "ignore"), re.S):
                    cs = []
                    for tag, body in re.findall(r"(<c\b[^>]*>)(.*?)</c>", row, re.S):
                        m = re.search(r"<(v|is)>(.*?)</\1>", body, re.S)
                        val = re.sub(r"<[^>]+>", "", m.group(2)) if m else ""
                        if m and m.group(1) == "v" and 't="s"' in tag:
                            try:
                                val = sh[int(val)]
                            except Exception:
                                pass
                        cs.append(html.unescape(val))
                    out.append("\t".join(cs))
    except Exception as e:
        errs.append("xlsx_parse_failed: %s: %s" % (p.name, e))
    return "\n".join(out)


def read_material(p, errs, degr):
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            return pdf_text(p.read_bytes(), errs), "pdf"
        if ext == ".docx":
            return docx_text(p, errs), "docx"
        if ext == ".xlsx":
            return xlsx_text(p, errs), "xlsx"
        if ext in IMG:
            degr.append("image_not_read: %s" % p.name)
            return "", "image"
        raw = p.read_bytes()[:CAP_BYTES]
        for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(enc), "text"
            except Exception:
                pass
        degr.append("decode_failed: %s" % p.name)
    except Exception as e:
        errs.append("read_failed: %s: %s" % (p.name, e))
    return "", "binary"


# ---------------------------------------------------------------- 定位索引
def split_pages(t):
    segs, cur, pos = [], 1, 0
    for m in re.finditer(r"\[\[\s*p(?:age)?\s*(\d+)\s*\]\]|<<<\s*PAGE\s*(\d+)\s*>>>|\f", t, re.I):
        segs.append((cur, t[pos:m.start()]))
        num = m.group(1) or m.group(2)
        cur = int(num) if num else cur + 1
        pos = m.end()
    segs.append((cur, t[pos:]))
    return segs


def split_sents(t):
    t = re.sub(r"-\n(?=[a-z])", "", t).replace("\n", " ")
    parts = re.split(r"(?<=[。！？；])|(?<=[!?;])\s+|(?<=\.)\s+(?=[A-Z0-9(\[\"'])", t)
    return [x.strip() for x in parts if len(x.strip()) >= 10]


def build_units(C, sid, text, kind):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paged = kind in ("pdf", "docx", "xlsx")
    ln, step = 1, (6 if paged else 14)
    for page, block in (split_pages(text) if paged else [(None, text)]):
        runs, cur = [], []
        raw = block.split("\n")
        for i, l in enumerate(raw):
            if l.strip():
                cur.append((ln + i, l))
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for run in runs:
            for j in range(0, len(run), step):
                ch = run[j:j + step]
                loc = "%s:P%d" % (sid, len(C["units"]) + 1)
                C["units"].append({"sid": sid, "page": page, "locator": loc,
                                   "line": "L%d-L%d" % (ch[0][0], ch[-1][0]),
                                   "text": "\n".join(x for _, x in ch)})
                for k, s in enumerate(split_sents(C["units"][-1]["text"])):
                    C["sents"].append({"sid": sid, "locator": "%s.S%d" % (loc, k + 1),
                                       "line": C["units"][-1]["line"], "page": page, "text": s})
        ln += len(raw)


def find_quote(q, C):
    if not q or len(norm(q)) < 8:
        return None, "quote_too_short"
    nq, sq = norm(q), squash(q)
    for u in C["units"]:
        if nq in norm(u["text"]):
            return u, "verbatim"
    for u in C["units"]:
        if sq and sq in squash(u["text"]):
            return u, "verbatim_ws_insensitive"
    for sid, d in C["docs"].items():
        if nq in norm(d["text"]):
            return {"sid": sid, "locator": sid + ":DOC", "line": "", "page": None}, "verbatim_doc_level"
    return None, "quote_not_found_in_material"


def json_strings(obj, ptr="", out=None, deep=0):
    out = [] if out is None else out
    if deep > 10:
        return out
    if isinstance(obj, str):
        if len(obj) >= 60:
            out.append((ptr, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            json_strings(v, "%s/%s" % (ptr, str(k).replace("~", "~0").replace("/", "~1")), out, deep + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            json_strings(v, "%s/%d" % (ptr, i), out, deep + 1)
    return out


# ---------------------------------------------------------------- 引用结构
REFH = re.compile(r"(?im)^[ \t]*(?:#+[ \t]*)?(?:\d+\.?[ \t]*)?(references?|bibliography|literature cited|"
                  r"works cited|参考文献|引用文献)[ \t]*[:：]?[ \t]*$")


def parse_refs(text):
    m = REFH.search(text) or re.search(r"(?im)^[ \t]*(references?|参考文献)\b", text)
    if not m:
        return {"mode": "none", "items": []}
    body = re.split(r"(?im)^[ \t]*(?:appendix|supplementary|附录|supplement)", text[m.end():])[0]
    items = []
    if len(re.findall(r"(?m)^[ \t]*\[?(\d{1,3})[\]\).]?[ \t]+\S", body)) >= 2:
        mode = "numbered"
        for l in body.split("\n"):
            mm = re.match(r"[ \t]*\[?(\d{1,3})[\]\).]?[ \t]+(\S.*)", l)
            if mm:
                items.append({"n": int(mm.group(1)), "text": mm.group(2).strip()})
            elif items and l.strip():
                items[-1]["text"] += " " + l.strip()
    else:
        mode, buf = "author_year", []
        for l in body.split("\n"):
            if l.strip():
                buf.append(l.strip())
            elif buf:
                items.append({"n": None, "text": " ".join(buf)})
                buf = []
        if buf:
            items.append({"n": None, "text": " ".join(buf)})
    for it in items:
        y = re.search(r"\b(19|20)\d{2}[a-z]?\b", it["text"])
        it["year"] = int(y.group(0)[:4]) if y else None
        a = re.match(r"([A-Z][A-Za-z\-']{1,20})", it["text"])
        it["author"] = a.group(1) if a else None
    return {"mode": mode, "items": [i for i in items if len(i["text"]) > 12]}


def expand_nums(inner):
    out = set()
    for p in re.split(r"[,，]", inner):
        r = re.match(r"^(\d{1,3})\s*[-–]\s*(\d{1,3})$", p.strip())
        if r and 0 < int(r.group(2)) - int(r.group(1)) <= 30:
            out.update(range(int(r.group(1)), int(r.group(2)) + 1))
        elif p.strip().isdigit():
            out.add(int(p))
    return out


def parse_cites(C):
    nums, ay = set(), []
    for s in C["sents"]:
        for m in re.finditer(r"(?<![\w\[])\[([\d\s,，\-–]{1,60})\]", s["text"]):
            g = expand_nums(m.group(1))
            if g and max(g) <= 400:
                nums |= g
        for m in re.finditer(r"\(([A-Z][A-Za-z\-']+(?:\s+(?:et al\.?|and|&|等))?[^()]{0,40}?,\s*(?:19|20)\d{2}[a-z]?)\)", s["text"]):
            ay.append({"author": re.match(r"([A-Z][A-Za-z\-']+)", m.group(1)).group(1),
                       "year": int(re.search(r"((?:19|20)\d{2})", m.group(1)).group(1)),
                       "locator": s["locator"], "line": s["line"], "quote": m.group(0)})
    return {"numbers": sorted(nums), "author_year": ay}


# ---------------------------------------------------------------- 确定性检出（候选，非结论）
def detect(C):
    S, F, out = C["sents"], C["f"], []

    def mk(fac, item, sev, q, s, trig, det, safe=False, prio=3):
        if len(out) >= CAP_CANDS * 3:
            return
        s = s if isinstance(s, dict) else {}
        out.append({"cid": "", "facet": fac, "item": item, "sev_hint": sev, "source_id": s.get("sid"),
                    "locator": s.get("locator"), "line": s.get("line"), "page": s.get("page"),
                    "quote": snip(q), "trigger": trig, "detail": det, "safe": safe, "priority": prio})

    def first(rx):
        return next((s for s in S if re.search(rx, s["text"], re.I)), S[0] if S else {})

    refs, cites = C["refs"], C["cites"]
    cited, listed = set(cites["numbers"]), set(i["n"] for i in refs["items"] if i["n"])
    for n in sorted(cited - listed)[:12]:
        h = next((s for s in S if re.search(r"\[\s*%d\b" % n, s["text"])), None)
        if h:
            mk("citation_support", "CIT-01", "major", h["text"], h, "cited_but_absent_in_reference_list",
               "正文引用 [%d]，文献表无此编号。" % n, True, 1)
    for n in sorted(listed - cited)[:6]:
        it = next((i for i in refs["items"] if i["n"] == n), {})
        mk("citation_support", "CIT-01b", "minor", it.get("text", ""), {"sid": "REF", "locator": "REF:n%d" % n},
           "ref_never_cited", "文献表第 %d 条未引用。" % n, False, 6)
    if refs["mode"] == "none" and cited:
        mk("citation_support", "CIT-01", "blocker", (S[0]["text"] if S else ""), S[0] if S else {},
           "no_reference_section", "有编号引用但无文献表，无法核对被引文献是否存在。", True, 1)
    for a in cites["author_year"][:40]:
        yrs = sorted(set(i["year"] for i in refs["items"] if i.get("author") == a["author"] and i["year"]))
        if yrs and a["year"] not in yrs:
            mk("citation_support", "CIT-02", "major", a["quote"], a, "intext_year_mismatch",
               "正文 %s %d，文献表为 %s。" % (a["author"], a["year"], yrs), False, 2)
    for s in S:
        if re.search(r"[pP]\s*[<>=≤≥]\s*0?\.\d+", s["text"]) and not re.search(
                r"t[\s-]?test|ANOVA|chi|Mann|Wilcoxon|Kruskal|regression|Cox|log[\s-]?rank|Fisher|mixed|"
                r"检验|方差分析|卡方|df\s*=|F\s*\(", s["text"], re.I):
            mk("statistical_reporting", "STA-01", "major", s["text"], s, "p_value_without_test_name",
               "报 p 值未指明检验方法与自由度。", False, 3)
    if F["pv"] and not F["test"]:
        s0 = first(r"[pP]\s*[<>=≤≥]")
        mk("statistical_reporting", "STA-01", "blocker", s0.get("text"), s0, "no_statistical_method_anywhere",
           "全文 %d 处 p 值但无检验方法，推断结论不可复现。" % len(F["pv"]), True, 1)
    if F["pm"] and not F["sd"]:
        s0 = first(r"±")
        mk("statistical_reporting", "STA-02", "major", s0.get("text"), s0, "pm_without_dispersion_label",
           "有“±”但无 SD/SEM/标准差标注。", False, 4)
    if (F["pv"] or re.search(r"显著|significan", C["full"], re.I)) and not F["ns"]:
        s0 = first(r"显著|significan")
        mk("statistical_reporting", "STA-03", "major", s0.get("text"), s0, "no_sample_size_reported",
           "有显著性表述但无样本量（n=…）。", False, 4)
    if F["hum"] and not F["eth"]:
        s0 = first(r"participants?|patients?|volunteers?|受试者|患者|被试")
        mk("academic_norms", "NRM-04", "blocker", s0.get("text"), s0, "human_subjects_without_ethics",
           "涉及人类受试者但无伦理审批/知情同意声明。", True, 1)
    elif F["hum"] and not F["apno"]:
        s0 = first(r"ethic|IRB|伦理|知情同意")
        mk("academic_norms", "NRM-04", "major", s0.get("text"), s0, "ethics_without_approval_number",
           "有伦理表述但无批件编号/审批机构。", False, 3)
    if F["ani"] and not F["eth"]:
        s0 = first(r"mice|rats?|animals?|小鼠|大鼠|动物")
        mk("academic_norms", "NRM-04", "major", s0.get("text"), s0, "animal_study_without_ethics",
           "动物实验无伦理/福利审批声明。", False, 3)
    for item, flag, sev, txt in (("NRM-02", F["coi"], "major", "无利益冲突（COI）声明。"),
                                 ("NRM-03", F["fund"], "minor", "无基金/资助信息（确无应明写“无”）。"),
                                 ("NRM-07", F["da"], "minor", "无数据可用性声明。")):
        if not flag:
            mk("academic_norms", item, sev, (S[0]["text"] if S else ""), S[0] if S else {},
               "required_statement_absent", txt, False, 4)
    for hits, kind in ((F["mail"][:3], "email"), (F["tel"][:3], "phone"), (F["pid"][:2], "id_number")):
        for h in hits:
            s0 = next((s for s in S if h in s["text"]), S[0] if S else {})
            mk("academic_norms", "NRM-05", "blocker", s0.get("text", h), s0, "pii_" + kind,
               "疑似可识别个人信息（%s）。发表前须脱敏或证明已授权。" % kind, True, 1)
    if F["tp"] and not F["perm"]:
        s0 = first(r"reproduced|adapted|©|creative commons|CC[- ]BY|转载|改编")
        mk("academic_norms", "NRM-06", "major", s0.get("text"), s0, "third_party_material_no_permission",
           "有第三方材料复用表述但无许可/授权说明。", False, 3)
    for rxp, cap, kind in ((r"(?:图|Fig(?:ure)?\.?)\s*(\d{1,2})", r"(?im)^[ \t]*(?:图|Fig(?:ure)?\.?)\s*(\d{1,2})\b", "图"),
                           (r"(?:表|Table)\s*(\d{1,2})", r"(?im)^[ \t]*(?:表|Table)\s*(\d{1,2})\b", "表")):
        refd = set(int(x) for x in re.findall(rxp, C["full"], re.I))
        caps = set(int(x) for x in re.findall(cap, C["full"], re.I))
        for n in sorted(refd - caps)[:4]:
            s0 = first(r"%s\s*%d\b" % (kind, n))
            mk("fact_verification", "FCT-02", "major", s0.get("text"), s0, "fig_or_table_ref_without_caption",
               "正文引%s %d，未见题注（已见 %s）。" % (kind, n, sorted(caps) or "无"), True, 1)
    OC = re.compile(r"\b(?:prove[sd]?|proven|confirms? that|definitely|unprecedented|for the first time|"
                    r"首次|填补了?空白|充分证明|毫无疑问|确凿)", re.I)
    for s in S:
        if OC.search(s["text"]) and not re.search(r"\[\d|\(\s*[A-Z][a-z]+.*\d{4}|\d+\s*%|p\s*[<>=]", s["text"]):
            mk("argument_chain", "ARG-01", "major", s["text"], s, "overclaim_without_evidence",
               "强断言同句无引用、无数据、无统计量。", False, 3)
    STR = re.compile(r"(?:已被?证实|研究表明|已有研究|previous studies|it is (?:well )?known|"
                     r"has been (?:shown|demonstrated))", re.I)
    k = 0
    for s in S:
        if k >= 6:
            break
        if STR.search(s["text"]) and not re.search(r"\[\d|\(\s*[A-Z][a-z]+.*\d{4}", s["text"]):
            k += 1
            mk("argument_chain", "ARG-02", "major", s["text"], s, "literature_claim_without_citation",
               "以“已有研究”引他人结论但无引用，属引而不证。", False, 4)
    if F["rand"] and not F["blind"] and re.search(r"\btrial\b|intervention|试验|干预|分组", C["full"], re.I):
        s0 = first(r"random|随机")
        mk("method_design", "MET-02", "major", s0.get("text"), s0, "randomization_without_blinding",
           "声称随机分组但无盲法/分配隐藏细节。", False, 3)
    if not F["soft"]:
        s0 = first(r"analy[sz]|统计|分析")
        mk("method_design", "MET-04", "minor", s0.get("text"), s0, "analysis_software_not_reported",
           "未见分析软件与版本。", False, 6)
    out.sort(key=lambda x: (x["priority"], FKEYS.index(x["facet"])))
    out = out[:CAP_CANDS]
    for i, x in enumerate(out):
        x["cid"] = "C%03d" % (i + 1)
    return out


def write_packets(C, d):
    """Write the adjudication packet (candidates.json + packets.md) consumed by the reviewing agent."""
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    (d / "candidates.json").write_text(json.dumps({"candidates": C["cands"]}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    L = ["# 候选证据包（自动检出，均为待裁定，不是最终意见）", "",
         "裁定：成立→写 issues（quote 逐字复制原文）；不成立→写 dismissed 并给理由；计划 schema 见 references/schema.md。", ""]
    for k in FKEYS:
        sub = [c for c in C["cands"] if c["facet"] == k]
        L.append("## %s（%s）— %d 条" % (FZH[k], k, len(sub)))
        if not sub:
            L.append("- 无自动候选；仍须按 references/checklist.md 人工过该面并给出 status。")
        L += ["- `%s` [%s/%s] %s｜%s %s｜原文「%s」｜%s" % (c["cid"], c["item"], c["sev_hint"], c["trigger"],
              c["source_id"], c["locator"], c["quote"], c["detail"]) for c in sub]
        L.append("")
    (d / "packets.md").write_text(chr(10).join(L), encoding="utf-8")
