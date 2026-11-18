#!/usr/bin/env python3
"""verify.py -- deterministic checks + output_contract filling.

CLI: python3 verify.py --draft D.json --index I.json [--result R.json] [--json]
"""
import argparse, json, re, sys, unicodedata
from pathlib import Path

U = ("%|‰|mg|kg|μg|µg|ng|pg|g|mL|ml|μL|µL|L|nM|µM|μM|mM|mol|mmol|μmol|µmol|nm|µm|μm|"
     "mm|cm|km|m|kDa|Da|bp|kb|°C|℃|K|kPa|MPa|Pa|GPa|Hz|kHz|MHz|V|mV|mA|A|W|kW|J|kJ|"
     "kcal|cal|rpm|h|hr|min|s|ms|d|wk|yr|fold|×|倍|例|名|人|份|次|天|小时|分钟|秒|年|月|日|个|项|组")
PAIR = re.compile(r"(?<![A-Za-z0-9.])(\d[\d,]*(?:\.\d+)?)\s*(" + U + r")(?![A-Za-z])")
ANY = re.compile(r"(?<![A-Za-z0-9.])(\d[\d,]*(?:\.\d+)?)(?![A-Za-z])")
ACRO = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z]{0,8}[A-Z][A-Za-z0-9\-]{0,10})(?![A-Za-z0-9])")
LOC = re.compile(r"M\d+:P\d+")
REQ = ("audience", "genre", "sections", "preserved", "map", "changes")
STOP = {"PDF", "DOI", "URL", "JSON", "CSV", "XML", "HTML", "DOCX", "PPTX", "FIG", "TAB",
        "AND", "THE", "FOR", "WITH", "FROM", "NOT", "ALL", "ANY", "OK", "NA", "VS", "ET",
        "AL", "II", "III", "IV", "ID", "NOTE"}
SLOTS = ((("case_id", "caseid", "案例"), "case_id"),
         (("deliver", "manuscript", "artifact", "transformed", "产物", "稿", "article"), "deliverable"),
         (("preserv", "retain", "保留", "fact", "事实", "must_keep"), "preserved_facts"),
         (("evidence", "source_map", "mapping", "对照", "来源", "映射", "citation", "trace", "locator"), "evidence_map"),
         (("change", "revision", "diff", "改动", "修改", "log"), "change_log"),
         (("glossar", "termin", "术语", "abbrev"), "glossary"),
         (("removed", "deleted", "删除", "omit", "reject"), "removed"),
         (("pending", "human", "确认", "待定"), "pending_human"),
         (("uncertain", "不确定"), "uncertainty"),
         (("audience", "受众", "reader"), "audience"),
         (("genre", "format", "体裁", "文体"), "genre"),
         (("length", "篇幅", "word"), "length"),
         (("status", "状态"), "status"))


def canon(s):
    s = str(s).replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f == int(f) and abs(f) < 1e15 else "%.10g" % f


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def normalize(s, loose=False):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s) if loose else s
    s = s.replace("\u3000", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", "", s.casefold() if loose else s)


def extract_numbers(t):
    """(values, pairs): pairs are value+unit e.g. {'12.5%'}."""
    t = LOC.sub(" ", t or "")
    vals, prs = set(), set()
    for m in PAIR.finditer(t):
        v, u = canon(m.group(1)), m.group(2).replace("μ", "u").replace("µ", "u")
        vals.add(v)
        prs.add(v + u)
    for m in ANY.finditer(t):
        vals.add(canon(m.group(1)))
    return vals, prs


def extract_acronyms(t):
    return {m.group(1) for m in ACRO.finditer(t or "")
            if len(m.group(1)) > 1 and m.group(1).upper() not in STOP}


def locs(s):
    return set(LOC.findall(str(s or "")))


def words(t):
    return len(re.findall(r"[\u3400-\u9fff]", t or "")) + len(re.findall(r"[A-Za-z][A-Za-z0-9\-']*", t or ""))


def qhit(q, he, hl):
    """Quote fidelity: exact -> loose -> miss."""
    if not normalize(q):
        return "empty"
    if normalize(q) in he:
        return "exact"
    return "loose" if normalize(q, True) in hl else "miss"


def check_draft(d, idx):
    E, W, P, S = [], [], [], {}
    e = lambda c, m, **k: E.append(dict(code=c, msg=m, **k))
    w = lambda c, m, **k: W.append(dict(code=c, msg=m, **k))
    if not isinstance(d, dict):
        e("draft_not_object", "draft.json 顶层须为 JSON 对象")
        return {"status": "partial", "errors": E, "warnings": W, "pending": P, "stats": S}
    for k in REQ:
        if k not in d:
            e("missing_field", "draft 缺字段 %s" % k)
        elif d[k] in (None, "", [], {}):
            e("empty_field", "draft 字段 %s 为空，无法成稿" % k)
    paras = {p["loc"]: p for p in idx.get("paragraphs", [])}
    he, hl = idx.get("norm_exact", ""), idx.get("norm_loose", "")
    a, g = d.get("audience") or {}, d.get("genre") or {}
    if not (isinstance(a, dict) and a.get("label")):
        w("audience_label_missing", "audience.label 为空：适配说明缺依据")
    if not (isinstance(g, dict) and g.get("label")):
        w("genre_label_missing", "genre.label 为空：适配说明缺依据")

    secs = d.get("sections") or []
    secs = secs if isinstance(secs, list) else []
    ids, buf, tq, hq = [], [], 0, 0
    for i, s in enumerate(secs, 1):
        if not isinstance(s, dict):
            e("section_not_object", "sections[%d] 不是对象" % i)
            continue
        sid = str(s.get("id") or "S%d" % i)
        ids.append(sid)
        title, text = str(s.get("title") or ""), str(s.get("text") or "")
        if not text.strip():
            e("section_empty", "section %s 正文为空" % sid)
        elif len(text) < 40 and len(secs) > 3:
            w("section_too_short", "section %s 短于 40 字符，疑似提纲" % sid)
        if not title.strip():
            w("section_title_empty", "section %s 缺标题" % sid)
        buf.append(text)
        if s.get("quote"):
            tq += 1
            r = qhit(s["quote"], he, hl)
            if r == "miss":
                e("section_quote_miss", "section %s 标注的引文在源文中找不到" % sid)
            elif r != "empty":
                hq += 1
    body = "\n".join(buf)
    S["sections"] = len(ids)
    S["body_chars"] = len(re.sub(r"\s+", "", body))
    S["body_words"] = words(body)

    tgt = None
    for c in ((g.get("length_target") if isinstance(g, dict) else None), d.get("length_target"),
              (d.get("length") or {}).get("target") if isinstance(d.get("length"), dict) else None):
        if num(c):
            tgt = num(c)
            break
    S["length_target"] = tgt
    if tgt:
        r = words(body) / tgt
        S["length_ratio"] = round(r, 3)
        if r < 0.45:
            e("too_short", "成稿 %d 字，不足目标 %d 字的 45%%：属提纲/片段" % (words(body), int(tgt)))
        elif r < 0.7:
            w("short", "成稿 %d 字，仅为目标 %d 字的 %d%%" % (words(body), int(tgt), int(r * 100)))
        elif r > 1.5:
            w("long", "成稿 %d 字，明显超出目标 %d 字" % (words(body), int(tgt)))

    pres = [x for x in (d.get("preserved") or []) if isinstance(x, dict)] if isinstance(d.get("preserved"), list) else []
    ok = 0
    miss_in_body = []
    for i, it in enumerate(pres, 1):
        v, lc = str(it.get("value") or "").strip(), str(it.get("locator") or "").strip()
        if not v:
            e("preserved_value_missing", "preserved[%d] 缺 value" % i)
        if not lc:
            e("preserved_locator_missing", "preserved[%d] 缺 locator" % i)
        elif locs(lc) - set(paras):
            e("locator_not_found", "preserved[%d] 定位 %s 不存在" % (i, lc))
        q = it.get("quote")
        if not q:
            w("preserved_quote_missing", "preserved[%d] 无 quote，无法逐字核验" % i)
        else:
            tq += 1
            if qhit(q, he, hl) == "miss":
                e("preserved_quote_miss", "preserved[%d] quote 源文中找不到（禁止改原文凑通过）" % i)
            else:
                hq += 1
                ok += 1
        if v and str(it.get("kind") or "").lower() in ("number", "unit", "term", "figure", "citation") \
                and normalize(v) not in normalize(body):
            miss_in_body.append(v)
    S["preserved"], S["preserved_quote_ok"] = len(pres), ok
    if miss_in_body:
        w("preserved_not_in_body", "必保留项未进正文：%s" % ", ".join(miss_in_body[:8]))

    mp = [x for x in (d.get("map") or []) if isinstance(x, dict)] if isinstance(d.get("map"), list) else []
    used = set()
    for i, it in enumerate(mp, 1):
        sid = str(it.get("section_id") or "")
        if sid and ids and sid not in ids:
            e("map_section_unknown", "map[%d] 指向不存在的 section_id=%s" % (i, sid))
        ls = locs(it.get("source_locator"))
        if not ls:
            e("map_locator_missing", "map[%d] 缺可解析的 source_locator（形如 M1:P3）" % i)
        elif ls - set(paras):
            e("locator_not_found", "map[%d] 定位不存在：%s" % (i, ",".join(sorted(ls - set(paras)))))
        used |= (ls & set(paras))
        if it.get("source_quote"):
            tq += 1
            if qhit(it["source_quote"], he, hl) == "miss":
                e("map_quote_miss", "map[%d] source_quote 源文中找不到" % i)
            else:
                hq += 1

    ch = [x for x in (d.get("changes") or []) if isinstance(x, dict)] if isinstance(d.get("changes"), list) else []
    for i, it in enumerate(ch, 1):
        if not str(it.get("action") or "").strip():
            e("change_action_missing", "changes[%d] 缺 action" % i)
        if not str(it.get("reason") or "").strip():
            e("change_reason_missing", "changes[%d] 缺 reason（原作者复核依据）" % i)
        if it.get("original_quote"):
            tq += 1
            if qhit(it["original_quote"], he, hl) == "miss":
                e("change_quote_miss", "changes[%d] original_quote 源文中找不到" % i)
            else:
                hq += 1
    S["changes"] = len(ch)

    sv, sp = set(idx.get("numbers", [])), set(idx.get("pairs", []))
    dv, dp = extract_numbers(body)
    bad, unitv = [], []
    for v in sorted(dv - sv):
        f = num(v)
        if f is not None and canon("%.10g" % (f / 100.0)) in sv:
            continue  # fraction restated as percent
        bad.append(v)
    for p in sorted(dp - sp):
        if re.search(r"\d", p) and any(p.startswith(v) for v in sv):
            unitv.append(p)
    if bad:
        e("number_not_in_source", "成稿含源文没有的数字：%s" % ", ".join(bad[:10]))
    if unitv:
        w("unit_variant", "单位写法与原文不一致：%s" % ", ".join(unitv[:8]))
    S["numbers_in_body"], S["numbers_in_source"] = len(dv), len(sv)
    S["number_errors"] = bad[:10]

    mloc = {p["loc"] for p in idx.get("paragraphs", []) if p.get("role") != "instruction"}
    S["material_paragraphs"], S["paragraphs_used"] = len(mloc), len(used & mloc)
    S["paragraph_coverage"] = round(len(used & mloc) / len(mloc), 3) if mloc else None
    if mloc and S["paragraph_coverage"] < 0.15:
        w("low_paragraph_coverage", "仅 %d/%d 段落进入逐段对照，确认未漏关键证据" % (S["paragraphs_used"], len(mloc)))

    terms = [t for t in idx.get("acronyms", []) if isinstance(t, str)]
    kept = [t for t in terms if t in body or t.lower() in body.lower()]
    S["acronyms_in_source"], S["acronyms_in_body"] = len(terms), len(kept)
    S["terms_lost"] = [t for t in terms if t not in kept][:10]
    if terms and len(kept) / len(terms) < 0.35:
        w("terms_lost", "源文缩写多未出现在成稿（公众稿应在术语表给全称）：%s" % ", ".join(S["terms_lost"]))

    key = set(idx.get("key_numbers", []))
    kept_key = key & (dv | dp)
    S["key_numbers_source"], S["key_numbers_kept"] = len(key), len(kept_key)
    if key and not kept_key:
        e("key_numbers_missing", "源文关键数字（含单位）无一进入成稿")

    S["quote_total"], S["quote_hit"] = tq, hq
    S["quote_hit_rate"] = round(hq / tq, 3) if tq else None
    if bad:
        P.append({"issue": "数字与源文不一致：%s" % ", ".join(bad[:6]),
                  "why": "成稿数字须可在源文找到；换算/改写需作者确认", "owner": "author"})
    if miss_in_body:
        P.append({"issue": "必保留项未进正文：%s" % ", ".join(miss_in_body[:6]),
                  "why": "被删或改写，需确认仍可核对", "owner": "author"})
    return {"status": "ok" if not E else "partial", "errors": E, "warnings": W, "pending": P, "stats": S}


def fill_contract(contract, ctx):
    """Map each original output_contract field onto produced content."""
    out, rep = {}, {"total": 0, "filled": 0, "null_fields": []}
    if not isinstance(contract, dict):
        return out, rep
    for f in contract:
        rep["total"] += 1
        k = f.lower()
        slot = next((s for h, s in SLOTS if any(x in k for x in h)), None)
        v = ctx.get(slot) if slot and slot in ctx else None
        empty = v is None or (isinstance(v, (list, dict)) and not v) or v == ""
        out[f] = None if empty else v
        if empty:
            rep["null_fields"].append(f)
        else:
            rep["filled"] += 1
    return out, rep


def contract_missing(res, contract):
    return [f for f in (contract or {}) if f not in (res or {})]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="校验工作稿：结构/引文/数字/覆盖/契约字段")
    ap.add_argument("--draft", default="", help="draft.json")
    ap.add_argument("--index", default="", help="index.json（init 生成）")
    ap.add_argument("--result", default="", help="可选：检查 result.json 契约字段")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args(argv)
    rep = {"status": "partial", "errors": [], "warnings": [], "pending": [], "stats": {}}
    try:
        if not (a.draft and a.index):
            rep["errors"].append({"code": "args", "msg": "需要 --draft 与 --index"})
        else:
            d = json.loads(Path(a.draft).read_text(encoding="utf-8-sig"))
            idx = json.loads(Path(a.index).read_text(encoding="utf-8-sig"))
            rep = check_draft(d, idx)
            if a.result:
                miss = contract_missing(json.loads(Path(a.result).read_text(encoding="utf-8-sig")),
                                        idx.get("output_contract") or {})
                if miss:
                    rep["errors"].append({"code": "contract_missing", "msg": "result.json 缺契约字段：" + ", ".join(miss)})
                    rep["status"] = "partial"
    except Exception as exc:
        rep["errors"].append({"code": "exception", "msg": "%s: %s" % (type(exc).__name__, exc)})
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        s = rep["stats"]
        print("状态 %s | 段落 %s | 正文 %s 字 | 引文 %s/%s | 数字 %s" % (
            rep["status"], s.get("sections"), s.get("body_words"), s.get("quote_hit"),
            s.get("quote_total"), s.get("numbers_in_body")))
        for x in rep["errors"]:
            print("  [错误] " + str(x.get("msg")))
        for x in rep["warnings"]:
            print("  [提示] " + str(x.get("msg")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
