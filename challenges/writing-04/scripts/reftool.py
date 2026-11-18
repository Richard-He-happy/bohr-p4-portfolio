#!/usr/bin/env python3
"""文献工具层：BibTeX/RIS/CSL-JSON/GB-T 解析、规范化、去重、GB/T 7714 与 APA 渲染、校验、workorder 回执。仅标准库。"""
import difflib
import json
import re
import unicodedata
import zipfile
from pathlib import Path

UNITS = re.compile(r"[-+]?\d+(?:\.\d+)?(?:\s?(?:%|‰|℃|°C|[a-zA-Zμ]{1,6}))?")
NUMR = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.、)])\s*(\S.*)$")
GC = re.compile(r"\[\s*(EB/OL|J/OL|M/OL|C/OL|DB/OL|J|M|C|D|R|S|P|N|Z|A|G)\s*\]")
DOIR = re.compile(r"10\.\d{4,9}/[^\s\"'<>,;，。；]+")
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
NUMB = re.compile(r"\[(\d+)\]")
TY = {"j": "J", "m": "M", "c": "C", "d": "D", "r": "R", "s": "S", "p": "P", "n": "N",
      "z": "Z", "eb/ol": "EB/OL", "db/ol": "DB/OL", "a": "A", "g": "G", "article": "J", "journal": "J", "jour": "J", "jfull": "J", "book": "M", "monograph": "M", "chapter": "M",
      "chap": "M", "incollection": "M", "inproceedings": "C", "proceedings": "C", "conference": "C", "conf": "C",
      "cpaper": "C", "thesis": "D", "thes": "D", "dissertation": "D", "phdthesis": "D", "mastersthesis": "D",
      "report": "R", "rprt": "R", "techreport": "R", "patent": "P", "pat": "P", "standard": "S", "stand": "S",
      "webpage": "EB/OL", "online": "EB/OL", "elec": "EB/OL", "dataset": "DS", "newspaper": "N", "preprint": "Z",
      "prep": "Z", "misc": "Z", "gen": "Z", "paper-conference": "C", "article-journal": "J"}
RF = {"AU": "au", "A1": "au", "TI": "ti", "T1": "ti", "T2": "t2", "JO": "jo", "JF": "jo", "PY": "py", "Y1": "py",
      "DO": "do", "VL": "vl", "IS": "is", "SP": "sp", "EP": "ep", "PB": "pb", "UR": "ur", "AB": "ab", "ID": "id"}


def rd(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return b.decode(e)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def nz(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s or "").lower())


def nt(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", unicodedata.normalize("NFKC", s).lower()).strip()


def nd(s):
    return re.sub(r"(?i)^(https?://(dx\.)?doi\.org/|doi\s*:\s*)", "", (s or "").strip()).strip(" .;，。、").lower()


def yr(s):
    m = re.search(r"(1[89]\d{2}|20\d{2})", s or "")
    return m.group(1) if m else ""


def zh(s):
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def df(s):
    s = (s or "").strip().strip(".")
    if not s:
        return ""
    if "," in s:
        return s.split(",")[0].strip()
    p = s.split()
    return p[-1] if len(p) > 1 and re.search(r"[A-Za-z]", s) else s


def dg(s):
    s = (s or "").strip()
    if "," in s:
        return s.split(",", 1)[1].strip()
    p = s.split()
    return " ".join(p[:-1]) if len(p) > 1 and re.search(r"[A-Za-z]", s) else ""


def rec(f, src="", ln=0):
    """短键 dict（t,a,y,j,v,i,p,d,pb,u,ab,id,ty）→ 统一条目字段。"""
    t = re.sub(r"\s+", " ", f.get("t") or "").strip()
    return {"key": str(f.get("id") or ""), "title": t, "authors": [a for a in (f.get("a") or []) if a],
            "year": str(f.get("y") or ""), "container": (f.get("j") or "").strip(), "volume": str(f.get("v") or ""),
            "issue": str(f.get("i") or ""), "pages": (f.get("p") or "").replace("--", "-").strip(),
            "doi": f.get("d") or "", "publisher": (f.get("pb") or "").strip(), "url": f.get("u") or "",
            "abstract": f.get("ab") or "", "type_code": TY.get(str(f.get("ty") or "").lower(), "Z"),
            "lang": "", "source": src, "line": ln, "raw": t}


def fin(r, n):
    r["year"] = r["year"] or yr(r["raw"])
    r["lang"] = "zh" if zh(r["title"]) else "en"
    r["key"] = r["key"] or "r%03d" % n
    return r


def blk(s, i):
    d, j = 0, i
    while j < len(s):
        if s[j] == "{":
            d += 1
        elif s[j] == "}":
            d -= 1
            if d == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


FRE = re.compile(r"([A-Za-z][\w-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)")


def pbib(t, src):
    o = []
    for m in re.finditer(r"@(\w+)\s*\{", t):
        body, _ = blk(t, m.end() - 1)
        f = {fm.group(1).lower(): re.sub(r"\s+", " ", fm.group(2).strip().strip("{}").strip('"')).strip()
             for fm in FRE.finditer(body)}
        w = re.split(r"[\s,]", body.strip(), 1)
        o.append(rec({"id": w[0].strip() if "=" not in w[0] else "", "ty": m.group(1), "t": f.get("title"),
                      "y": f.get("year") or f.get("date"),
                      "a": [a.strip() for a in re.split(r"\s+and\s+|;", f.get("author", "")) if a.strip()],
                      "j": f.get("journal") or f.get("booktitle"), "v": f.get("volume"), "i": f.get("number"),
                      "p": f.get("pages"), "d": f.get("doi"), "pb": f.get("publisher") or f.get("school") or f.get("institution"), "u": f.get("url")},
                     src, t[:m.start()].count("\n") + 1))
    return o


def pris(t, src):
    o, c = [], None
    for ln, raw in enumerate(t.splitlines(), 1):
        m = re.match(r"^([A-Z][A-Z0-9])\s{0,2}-\s?(.*)$", raw.strip())
        if not m:
            continue
        g, v = m.group(1), m.group(2).strip()
        if g == "TY":
            c = {"ty": v, "au": [], "ln": ln}
        elif c is None:
            continue
        elif g == "ER":
            o.append(rec({"id": c.get("id"), "ty": c.get("ty"), "t": c.get("ti"), "a": c["au"], "y": c.get("py"),
                          "j": c.get("jo") or c.get("t2"), "v": c.get("vl"), "i": c.get("is"), "d": c.get("do"),
                          "pb": c.get("pb"), "u": c.get("ur"), "ab": c.get("ab"),
                          "p": ("%s-%s" % (c.get("sp", ""), c.get("ep", ""))).strip("-")}, src, c["ln"]))
            c = None
        elif RF.get(g) == "au":
            c["au"].append(v)
        elif RF.get(g):
            c[RF[g]] = v
    return o


def pjson(t, src):
    try:
        d = json.loads(t)
    except Exception:
        return []
    if isinstance(d, dict):
        lst = [d[k] for k in ("items", "references", "data", "records", "refs") if isinstance(d.get(k), list)]
        d = lst[0] if lst else ([d] if ("title" in d or "DOI" in d) else [])
    o = []
    for it in d if isinstance(d, list) else []:
        if not isinstance(it, dict):
            continue
        ti = it.get("title", "")
        ti = (ti[0] if ti else "") if isinstance(ti, list) else ti
        iss = it.get("issued") if isinstance(it.get("issued"), dict) else {}
        dp = iss.get("date-parts") or []
        au = [a if isinstance(a, str) else (a.get("literal") or ", ".join(
            x for x in (a.get("family", ""), a.get("given", "")) if x)) for a in (it.get("author") or [])
            if isinstance(a, (str, dict))]
        o.append(rec({"id": it.get("id"), "ty": it.get("type"), "t": ti, "a": au,
                      "y": str(dp[0][0]) if dp and dp[0] and dp[0][0] else (it.get("year") or it.get("date")),
                      "j": it.get("container-title") or it.get("journal") or it.get("booktitle"),
                      "v": it.get("volume"), "i": it.get("issue"), "p": it.get("page"),
                      "d": it.get("DOI") or it.get("doi"), "pb": it.get("publisher"),
                      "u": it.get("URL") or it.get("url"), "ab": it.get("abstract")}, src))
    return o


def pg1(s, src="", ln=0):
    """解析一条 GB/T 7714 风格参考文献行（含 [J]/[M]/[J/OL] 等类型标识）。"""
    s = (s or "").strip().strip("*").strip()
    m0 = NUMR.match(s)
    if m0:
        s = m0.group(3).strip()
    m = GC.search(s)
    head, tail = (s[:m.start()], s[m.end():]) if m else (s, "")
    pt = re.split(r"[.．]\s+", head.rstrip(" .．"), 1)
    au_s, title = (pt[0], pt[1]) if len(pt) == 2 else ("", head)
    au = [a.strip() for a in re.split(r"[,，;；]\s*|\s+and\s+", au_s)
          if a.strip() and not re.fullmatch(r"(等|et al\.?)", a.strip())]
    tail = tail.strip().lstrip(".．").strip()
    ct, vo, isu, pg, pb, y = "", "", "", "", "", ""
    mj = re.match(r"^([^,，.]+)[,，]\s*(\d{4})\s*(?:[,，]\s*([^(:：,，]*))?\s*(?:\(([^)]*)\))?\s*(?:[:：]\s*([0-9\-–—]+))?", tail)
    if mj:
        ct, y, vo, isu, pg = mj.group(1).strip(), mj.group(2), (mj.group(3) or "").strip(), (mj.group(4) or "").strip(), (mj.group(5) or "").strip()
    else:
        y, pb = yr(tail), re.sub(r"[.,，]?\s*\d{4}.*$", "", tail).strip(" ,，.:：")
    dm, um = DOIR.search(s), re.search(r"https?://\S+", tail)
    return rec({"ty": (m.group(1).split("/")[0] if m else "Z"), "t": title, "a": au, "y": y, "j": ct, "v": vo,
                "i": isu, "p": pg.replace("–", "-"), "pb": pb, "d": dm.group(0) if dm else "",
                "u": um.group(0) if um else ""}, src, ln)


def pgbt(t, src):
    o = []
    for ln, raw in enumerate(t.splitlines(), 1):
        s = raw.strip()
        if len(s) > 11 and not s.startswith("#") and (NUMR.match(s) or GC.search(s)):
            r = pg1(s, src, ln)
            if r["title"] or r["authors"]:
                o.append(r)
    return o


def dxt(p):
    try:
        with zipfile.ZipFile(p) as z:
            x = re.sub(r"</w:p>", "\n\n", re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode("utf-8", "replace")))
        return re.sub(r"\n{3,}", "\n\n", x)
    except Exception:
        return ""


def sniff(p, t=""):
    e, h = Path(p).suffix.lower(), (t or "")[:40000]
    if e in (".docx", ".doc"):
        return "docx"
    if e in (".bib", ".ris", ".enw", ".nbib", ".csv", ".json", ".txt", ".md", ".markdown", ".tex", ".pdf"):
        return e[1:]
    if re.search(r"(?m)^TY\s{0,2}-", h):
        return "ris"
    if re.search(r"(?m)^%[A-Z0-9]\s", h):
        return "enw"
    if re.search(r"(?m)^@\w+\s*\{", h):
        return "bib"
    if GC.search(h) and len(pgbt(h, str(p))) >= 2:
        return "gbt"
    return "unknown"


PARSER = {"bib": pbib, "ris": pris, "json": pjson, "gbt": pgbt}


def parse_library(pairs):
    """pairs: [(path, kind, text)] → (records, notes)。单文件失败只降级该文件，不影响全局。"""
    raw, notes = [], []
    for p, k, t in pairs:
        fn = PARSER.get(k)
        if not fn:
            notes.append({"stage": "library:" + k, "file": p.name, "note": "unsupported_or_unrecognized_format"})
            continue
        try:
            got = fn(t, p.name)
            raw += got
            if not got:
                notes.append({"stage": "library:" + k, "file": p.name, "note": "no_records_parsed"})
        except Exception as e:
            notes.append({"stage": "library:" + k, "file": p.name, "note": str(e)[:140]})
    for i, r in enumerate(raw, 1):
        fin(r, i)
    seen = {}
    for r in raw:
        kk, i = r["key"], 2
        while kk in seen:
            kk = "%s_%d" % (r["key"], i)
            i += 1
        r["key"] = kk
        seen[kk] = r
    return raw, notes


def tsim(a, b):
    ta, tb = nt(a), nt(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta.split()), set(tb.split())
    return max(difflib.SequenceMatcher(None, ta, tb).ratio(), len(sa & sb) / len(sa | sb) if sa and sb else 0.0)


def dec(a, b):
    """可解释合并判据 → (置信度, 理由列表)：DOI 精确 > 规范化题名相等 > 题名相似+作者+年份。"""
    da, db = nd(a["doi"]), nd(b["doi"])
    if da and da == db:
        return 0.99, ["doi_exact"]
    ta, tb = nt(a["title"]), nt(b["title"])
    ya, yb = a["year"], b["year"]
    dy = abs(int(ya) - int(yb)) if (ya.isdigit() and yb.isdigit()) else None
    same = bool(a["authors"] and b["authors"]) and nz(df(a["authors"][0])) == nz(df(b["authors"][0]))
    if ta and ta == tb:
        if dy is not None and dy >= 3:
            return 0.0, ["title_equal_year_gap_%d" % dy]
        return (0.95, ["title_normalized_equal"]) if (same or not (a["authors"] and b["authors"])) else \
            (0.80, ["title_equal_author_differs"])
    s = tsim(a["title"], b["title"])
    if s >= 0.93 and same and (dy is None or dy <= 2):
        return 0.88, ["title_sim_%.2f" % s, "same_first_author"]
    if s >= 0.85 and same and dy == 0 and nz(a["container"]) and nz(a["container"]) == nz(b["container"]):
        return 0.80, ["title_sim_%.2f" % s, "same_author_year_container"]
    return (0.0, ["ambiguous_sim_%.2f" % s]) if s >= 0.85 else (0.0, [])


def dedup(rs):
    n = len(rs)
    par = list(range(n))

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    de, amb = [], []
    for i in range(n):
        for j in range(i + 1, n):
            ok, why = dec(rs[i], rs[j])
            p = {"a": rs[i]["key"], "b": rs[j]["key"], "score": round(ok, 3), "reasons": why,
                 "source_a": rs[i]["source"], "source_b": rs[j]["source"]}
            if ok >= 0.80:
                de.append(dict(p, action="merge"))
                if f(i) != f(j):
                    par[f(j)] = f(i)
            elif why:
                amb.append(dict(p, action="keep_separate"))
    gp = {}
    for i in range(n):
        gp.setdefault(f(i), []).append(i)
    out, grp = [], []
    for g in gp.values():
        if len(g) == 1:
            out.append(rs[g[0]])
            continue
        mem = sorted(g, key=lambda i: (-sum(1 for k in ("title", "authors", "year", "container", "volume", "pages", "doi") if rs[i].get(k)), rs[i]["key"]))
        b, fills = dict(rs[mem[0]]), []
        for i in mem[1:]:
            for k in ("title", "year", "container", "volume", "issue", "pages", "doi", "publisher", "url"):
                if not b.get(k) and rs[i].get(k):
                    b[k] = rs[i][k]
                    fills.append({"field": k, "from": rs[i]["key"]})
            if len(rs[i]["authors"]) > len(b["authors"]):
                b["authors"] = rs[i]["authors"]
                fills.append({"field": "authors", "from": rs[i]["key"]})
        b["merged_from"] = [rs[i]["key"] for i in mem]
        out.append(b)
        grp.append({"keep": b["key"], "members": b["merged_from"], "fills": fills})
    return out, de, amb, grp


def ini(g):
    return "".join(p[0].upper() for p in re.split(r"[ .\-]+", g or "") if p)


def au(mode, r):
    a = r.get("authors") or []
    if not a:
        return "[待补]"
    if mode == "apa":
        s = [df(x) + ((", " + " ".join(p[0].upper() + "." for p in re.split(r"[ .\-]+", dg(x)) if p)) if dg(x) else "")
             for x in a]
        return s[0] if len(s) == 1 else (", ".join(s[:-1]) + ", & " + s[-1] if len(s) <= 20 else
                                         ", ".join(s[:19]) + ", ... " + s[-1])
    if zh(a[0]):
        return ", ".join(a) if len(a) <= 3 else ", ".join(a[:3]) + ", 等"
    s = [(df(x).upper() + " " + ini(dg(x))).strip() for x in a]
    return ", ".join(s) if len(s) <= 3 else ", ".join(s[:3]) + ", et al"


def render(r, n, style="gbt7714"):
    """GB/T 7714—2015（顺序编码制）或 APA 7th 单条渲染；缺字段写 [待补]，绝不补造。"""
    t, y, cd = r.get("title") or "[待补题名]", r.get("year") or "", r.get("type_code") or "Z"
    ct, vo, isu, pg = r.get("container") or "", r.get("volume") or "", r.get("issue") or "", r.get("pages") or ""
    doi = nd(r.get("doi"))
    if style == "apa":
        b = [au("apa", r) + (" (%s)." % y if y else " (n.d.)."), t + "."]
        if ct:
            b.append("*%s*" % ct + (", %s" % vo if vo else "") + ("(%s)" % isu if isu else "") +
                     (", %s" % pg.replace("-", "–") if pg else "") + ".")
        elif r.get("publisher"):
            b.append(r["publisher"] + ".")
        b.append("https://doi.org/" + doi if doi else (r.get("url") or ""))
        return re.sub(r"\.\.", ".", " ".join(x for x in b if x))
    s = "[%d] %s. %s[%s]" % (n, au("gbt", r), t, cd)
    if cd in ("J", "N", "DS"):
        s += ". %s, %s" % (ct or "[待补刊名]", y or "[待补年]") + (", %s" % vo if vo else "") + \
             ("(%s)" % isu if isu else "") + (": %s" % pg if pg else "") + "."
    elif cd in ("M", "D", "R", "S", "P"):
        s += ". %s, %s." % (r.get("publisher") or "[待补出版者]", y or "[待补年]")
    elif cd == "C":
        s += "//%s. %s, %s%s." % (ct or "[待补会议]", r.get("publisher") or "[待补出版者]", y or "[待补年]",
                                  (": " + pg) if pg else "")
    else:
        s += ". %s, %s." % (ct or r.get("publisher") or "[待补来源]", y or "[待补年]") + \
             (" %s." % r["url"] if r.get("url") else "")
    return s + (" DOI: %s." % doi if doi else "")


def checks(R, ms, ent, lib):
    body = ms.split("## 参考文献")[0].split("## References")[0]
    bn = sorted({int(x) for x in NUMB.findall(body)})
    lib = lib or {}
    ds = [nd(r.get("doi")) for r in lib.values() if r.get("doi")]
    ev, pf = R.get("evidence_map") or [], R.get("preserved_facts") or []
    t = [("numbering_continuous", bn == list(range(1, len(bn) + 1)), str(bn)[:70]),
         ("ref_list_covers_body", len(ent or []) >= (max(bn) if bn else 0), "%d/%s" % (len(ent or []), max(bn) if bn else 0)),
         ("no_orphan_citation", not any(not x.get("key") for x in (R.get("citation_map") or [])),
          "unresolved=%s" % R.get("counts", {}).get("unresolved_markers")),
         ("doi_syntax", all(DOI.match(x) for x in ds), "bad=%d" % len([x for x in ds if not DOI.match(x)])),
         ("no_duplicate_doi", len(ds) == len(set(ds)), "dup=%d" % (len(ds) - len(set(ds)))),
         ("entries_have_title", all(r.get("title") for r in lib.values()),
          "miss=%d" % len([r for r in lib.values() if not r.get("title")])),
         ("evidence_has_locator", bool(ev) and all(x.get("locator") for x in ev), "n=%d" % len(ev)),
         ("facts_preserved", all(x.get("kept") for x in pf),
          "lost=%d/%d" % (len([x for x in pf if not x.get("kept")]), len(pf))),
         ("dedup_explained", all(d.get("reasons") for d in (R.get("dedup_decisions") or [])),
          "merge=%d/amb=%d" % (len(R.get("dedup_decisions") or []), len(R.get("ambiguous_pairs") or [])))]
    c = [{"id": a, "pass": bool(b), "detail": d} for a, b, d in t]
    p = sum(1 for x in c if x["pass"])
    return {"checks": c, "passed": p, "total": len(c), "pass_rate": round(p / len(c), 3) if c else 0.0,
            "weak_claim_matches": len([x for x in (R.get("citation_map") or []) if x.get("verdict") == "weak_match"]),
            "unresolved_markers": R.get("counts", {}).get("unresolved_markers", 0)}


RULE = ((r"编号|renumber|number", "citation_points"), (r"去重|合并|dedup|merge", "merged_groups"),
        (r"格式|style|gbt|apa|转换", "render_entries"), (r"插入|insert|补引|cite", "inserted_citations"),
        (r"核验|检查|verif|一致性", "citation_points"))


def receipt(R, case):
    """按 organizer_workorder / organizer_edit_workorder 逐项回执（done/unmet + 计数证据）。"""
    wo = None
    for k in ("organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder"):
        if isinstance(case, dict) and case.get(k):
            wo = case[k]
            break
    if not wo:
        return []
    items = wo if isinstance(wo, list) else (wo.get("items") or wo.get("tasks") or [wo])
    cnt, out = R.get("counts", {}), []
    for i, it in enumerate(items if isinstance(items, list) else [items], 1):
        t = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)
        st, ev = "unmet", []
        for pat, key in RULE:
            if re.search(pat, t.lower()) and cnt.get(key) is not None:
                st, ev = "done", ["%s=%s" % (key, cnt.get(key))]
                break
        out.append({"index": i, "item": t[:300], "status": st, "evidence": ev})
    return out


def run(R, ms, ent, lib, style="gbt7714", case=None):
    v = checks(R, ms, ent, lib)
    v["style"] = style
    v["workorder_receipt"] = receipt(R, case)
    return v
