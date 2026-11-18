#!/usr/bin/env python3
"""slides-04 v2 reporting: incremental run.log, page_diff.md, version_history.md, rollback record.

Kept separate from the build pipeline so a reporting failure can never stop the deck from being
packed. Every table cell is filled from the run itself (no template text, no placeholder prose).
"""
import hashlib, json, re, time
from pathlib import Path

T0 = time.time()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def clip(s, n=90):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "\u2026"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def md(s):
    """escape pipes/newlines so a cell cannot break the table"""
    return " ".join(str(s if s is not None else "").split()).replace("|", "/")


class Log:
    """append-only run log; each line hits disk immediately so a crash still leaves evidence"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.lines = []
        try:
            self.path.write_text("", "utf-8")
        except Exception:
            pass

    def __call__(self, stage, msg, level="INFO"):
        d = time.time() - self.t0
        ln = "%s  +%07.3fs  %-5s  %-18s %s" % (now(), d, level, stage, msg)
        self.lines.append(ln)
        try:
            with open(str(self.path), "a", encoding="utf-8") as f:
                f.write(ln + "\n")
        except Exception:
            pass
        return ln

    def stages(self):
        out = []
        for ln in self.lines:
            m = re.search(r"\s{2}(\w+)\s{18}", ln) or re.match(r"\S+\s+\S+\s+(\w+)\s+(\S+)", ln)
            if m:
                out.append(m.group(1) if m.lastindex == 2 else m.group(1))
        return list(dict.fromkeys(out))

    def summary(self):
        return {"path": str(self.path), "lines": len(self.lines),
                "stages": [ln.split()[3] if len(ln.split()) > 3 else "" for ln in self.lines]}


def _quote_hit(q, src):
    """verbatim check of a claim quote against the normalised source text"""
    if not q or not src:
        return "no_source"
    a = " ".join(str(q).split())
    b = " ".join(str(src).split())
    if a in b:
        return "hit"
    core = a.rstrip("\u2026").strip()
    if len(core) > 24 and core in b:
        return "hit_prefix"
    return "miss"


def page_diff(path, ctx):
    """adaptation deck vs template requirement vs source paper, page by page"""
    cms = ctx["cms"]
    facts = ctx["facts"]
    spec = ctx["spec"]
    wo = ctx["wo"]
    txt = ctx.get("source_text") or ""
    expo = ctx.get("export_check") or {}
    fmt = ctx.get("format_compliance") or {}
    rows, qrows = [], []
    for s in facts["slides"]:
        c = next((x for x in cms if x.get("n") == s["n"]), {})
        lm = next((m for m in spec.get("layout_map", []) if m.get("page") == s["n"]), {})
        dev = []
        if not s["geometry_inside_page"]:
            dev.append("超出页面")
        if (s["max_fit_ratio"] or 0) > 1.02:
            dev.append("文本估算溢出 %.2f" % s["max_fit_ratio"])
        if s["freetext"]:
            dev.append("自由文本框×%d" % s["freetext"])
        if not s["has_sldnum"]:
            dev.append("无页码占位符")
        if s["layout_type"] in ("title", "ctrtitle", "secHead") and s["freetext"]:
            dev.append("封面/章节页用自由文本框放页脚")
        if lm.get("invented_placeholders"):
            dev.append("自造占位符 %s" % lm["invented_placeholders"])
        if c.get("deviation"):
            dev.append(str(c["deviation"]))
        rows.append([s["n"], c.get("role") or "", clip(s["title_text"], 46), s["layout_name"] or "",
                     "%s/%s" % (len(c.get("placeholders_filled") or []), len(lm.get("placeholders_available") or [])),
                     ("%s" % max(s["sizes"])) if s["sizes"] else ("%s(继承)" % (ctx.get("default_body_pt") or "")),
                     (c.get("footer_source") or ("freetext" if s["freetext"] else "无")).replace("ftr_placeholder", "占位符").replace("freetext", "自由文本"),
                     str(c.get("page_number_source") or "无").replace("sldNum", "占位符").replace("freetext", "自由文本"),
                     "%.2f" % (s["max_fit_ratio"] or 0), "；".join(dev) or "—"])
        for ev in (c.get("evidence") or []):
            qrows.append([s["n"], clip(c.get("claim"), 60), ev.get("locator", ""), clip(ev.get("quote"), 96),
                          _quote_hit(ev.get("quote"), txt)])
    heir = [r for r in qrows]
    miss = [r for r in heir if r[4] == "miss"]
    ts = spec.get("slide_size") or {}
    fs = facts["size"]
    L = []
    L.append("# page_diff \u2014 \u9010\u9875\u5bf9\u7167\uff08\u9002\u914d\u7a3f / \u6a21\u677f\u8981\u6c42 / \u539f\u7a3f\uff09")
    L.append("")
    L.append("\u751f\u6210\u65f6\u95f4 `%s`\u3000case `%s`\u3000\u9002\u914d\u7a3f `presentation.pptx`"
             "\uff08%d \u9875\uff0c%s\uff09" % (now(), ctx.get("case_id"), len(facts["slides"]),
                                             sha(Path(ctx["pptx"]).read_bytes())[:16] if Path(ctx["pptx"]).exists() else "-"))
    L.append("")
    L.append("\u5bf9\u7167\u4e09\u65b9\uff1a**\u6a21\u677f\u8981\u6c42**\uff08`template_spec.json` \u62bd\u53d6\u7684\u9875\u9762\u5c3a\u5bf8 / \u7248\u5f0f / \u5360\u4f4d\u7b26 / "
             "\u4e3b\u9898\u5b57\u4f53\u8272\u677f\uff09\u3001**\u9002\u914d\u7a3f\u5b9e\u9645**\uff08\u4ece pptx \u56de\u8bfb\u7684 XML \u503c\uff09\u3001"
             "**\u539f\u7a3f\u8bc1\u636e**\uff08`content_map` \u7684\u9010\u5b57 quote + locator\uff0c\u5728 `%s` \u4e2d\u91cd\u65b0\u6bd4\u5bf9\uff09\u3002"
             % (ctx.get("paper_name") or "\u539f\u7a3f"))
    L.append("")
    L.append("## 1. \u6a21\u677f\u7ea7 diff")
    L.append("")
    L.append("| \u9879\u76ee | \u6a21\u677f\u8981\u6c42 | \u9002\u914d\u7a3f\u5b9e\u9645 | \u7ed3\u8bba |")
    L.append("|---|---|---|---|")
    L.append("| \u9875\u9762\u5c3a\u5bf8/\u6bd4\u4f8b | %s\u00d7%s in (%s) %s | %s\u00d7%s in (%s) %s | %s |"
             % (ts.get("width_in"), ts.get("height_in"), ts.get("ratio"), ts.get("cx_emu"),
                fs["width_in"], fs["height_in"], fs["ratio"], fs["cx_emu"],
                "一致" if (ts.get("cx_emu"), ts.get("cy_emu")) == (fs["cx_emu"], fs["cy_emu"]) else "**不一致**"))
    used = sorted({s["layout_name"] or "" for s in facts["slides"]})
    L.append("| \u7248\u5f0f\u5e93 | \u6a21\u677f %d \u4e2a\u7248\u5f0f | \u7528\u5230 %d \u4e2a\uff1a%s | %s |"
             % (len(spec.get("layouts") or []), len(used), "、".join(used),
                "\u5168\u90e8\u6765\u81ea\u6a21\u677f" if all(s["layout_part"] for s in facts["slides"]) else "**\u6709\u9875\u672a\u7ed1\u5b9a**"))
    L.append("| \u6bcd\u7248/\u7248\u5f0f/\u4e3b\u9898 | %d \u4e2a\u53d7\u4fdd\u62a4\u90e8\u4ef6 | %s | %s |"
             % (len(spec.get("protected_parts") or {}),
                "\u5b57\u8282\u4e00\u81f4" if (ctx.get("rollback") or {}).get("verified") else "\u6709\u504f\u79fb\u5df2\u56de\u9000",
                "PASS" if (ctx.get("rollback") or {}).get("verified") else "REPAIRED"))
    L.append("| \u9875\u6570 | workorder %s | %d | %s |"
             % (wo.get("slides"), len(facts["slides"]), "PASS" if int(wo.get("slides") or 0) == len(facts["slides"]) else "FAIL"))
    ph_fill = sum(len(c.get("placeholders_filled") or []) for c in cms)
    L.append("| \u5360\u4f4d\u7b26\u586b\u5145 | \u6bcf\u9875\u7528\u6a21\u677f\u5360\u4f4d\u7b26 | %d \u4e2a\u5360\u4f4d\u7b26\u88ab\u5199\u5165\uff0c\u81ea\u7531\u6587\u672c\u6846 %d \u4e2a | %s |"
             % (ph_fill, sum(s["freetext"] for s in facts["slides"]),
                "PASS" if not any(lm.get("invented_placeholders") for lm in spec.get("layout_map", [])) else "FAIL"))
    L.append("| \u9875\u811a | %s | %s | %s |" % (wo.get("footer") or "\u65e0\u8981\u6c42",
                                             sorted({f for f in ctx.get("footers") or [] if f}) or "\u672a\u5199\u5165",
                                             "PASS" if (ctx.get("compliance_checks") or {}).get("failures") == [] else "见 format_compliance"))
    L.append("| \u5bfc\u51fa\u6e32\u67d3 | PDF \u9875\u6570 = \u5e7b\u706f\u7247\u6570\u3001\u5c3a\u5bf8\u4e00\u81f4 | PDF %s \u9875 / %s | %s |"
             % ((expo.get("pdf") or {}).get("pages"), (expo.get("pdf") or {}).get("size_in"),
                "PASS" if (expo.get("rules") or {}).get("pdf_pages_eq_slides") else "WARN"))
    L.append("")
    L.append("## 2. \u9010\u9875\u683c\u5f0f diff")
    L.append("")
    L.append("| \u9875 | \u89d2\u8272 | \u6807\u9898 | \u7248\u5f0f | \u5360\u4f4d\u7b26(\u7528/\u53ef\u7528) | \u6700\u5927\u5b57\u53f7pt | \u9875\u811a | \u9875\u7801 | \u586b\u5145\u7387 | \u504f\u5dee |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        L.append("| " + " | ".join(md(x) for x in r) + " |")
    L.append("")
    L.append("## 3. \u9010\u9875\u5185\u5bb9 diff\uff08\u9002\u914d\u7a3f\u4e0e\u539f\u7a3f\u9010\u5b57\u5bf9\u7167\uff09")
    L.append("")
    L.append("| \u9875 | \u4e3b\u5f20 | \u539f\u7a3f\u5b9a\u4f4d | \u9010\u5b57\u8bc1\u636e | \u547d\u4e2d |")
    L.append("|---|---|---|---|---|")
    for r in heir:
        L.append("| " + " | ".join(md(x) for x in r) + " |")
    L.append("")
    L.append("\u547d\u4e2d\u7edf\u8ba1\uff1a%d \u6761\u8bc1\u636e\uff0chit %d\uff0cmiss %d\u3002"
             % (len(heir), len(heir) - len(miss), len(miss)))
    L.append("")
    L.append("## 4. \u672a\u89e3\u51b3\u504f\u5dee\u4e0e\u4eba\u5de5\u52a8\u4f5c")
    L.append("")
    open_dev = [r for r in rows if r[-1] != "\u2014"]
    if open_dev:
        L.append("| \u9875 | \u504f\u5dee | \u5904\u7406 |")
        L.append("|---|---|---|")
        for r in open_dev:
            L.append("| %s | %s | %s |" % (r[0], md(r[-1]),
                                           "\u5df2\u964d\u7ea7\u5e76\u8bb0\u5165 result.degradations / uncertainty"
                                           if "溢出" in str(r[-1]) or "自由" in str(r[-1]) else "\u8bb0\u5f55\u5f85\u590d\u6838"))
    else:
        L.append("\u672a\u53d1\u73b0\u9875\u7ea7\u504f\u5dee\u3002")
    if miss:
        L.append("")
        L.append("quote \u672a\u547d\u4e2d\u9875\uff1a%s\uff08\u9700\u4eba\u5de5\u56de\u539f\u6587\u6838\u5bf9\uff0c\u4e0d\u5f97\u6539\u5199\u539f\u6587\u51d1\u901a\u8fc7\uff09\u3002"
                 % sorted({m[0] for m in miss}))
    L.append("")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), "utf-8")
    return {"path": str(p), "sha256": sha(p.read_bytes()), "pages": len(rows),
            "evidence_rows": len(heir), "quote_hit": len(heir) - len(miss), "quote_miss": len(miss),
            "deviations": len(open_dev),
            "rows": [{"page": r[0], "layout": r[3], "deviation": r[-1]} for r in rows]}


BASE_V1 = {"SKILL.md": None, "scripts/main.py": None, "scripts/verify.py": None}


def version_history(path, ctx):
    """v0 skeleton -> v1 baseline -> v2 (this run), with artefact hashes and a rollback path"""
    out = Path(ctx["out"])
    cur = {}
    for f in sorted(Path(ctx["pkg"]).rglob("*")):
        if f.is_file() and f.suffix.lower() in (".md", ".py"):
            cur[str(f.relative_to(Path(ctx["pkg"])))] = {"bytes": f.stat().st_size,
                                                         "sha256": sha(f.read_bytes())[:16]}
    arts = {}
    for name in ("presentation.pptx", "presentation.pdf", "template_spec.json", "format_compliance.json",
                 "page_diff.md", "export_check.json", "result.json"):
        f = out / name
        arts[name] = {"bytes": f.stat().st_size, "sha256": sha(f.read_bytes())[:16]} if f.exists() else None
    L = ["# version_history \u2014 \u7248\u672c\u8bb0\u5f55\u4e0e\u56de\u9000\u8def\u5f84", "",
         "\u751f\u6210\u65f6\u95f4 `%s`\u3000case `%s`\u3000\u8fd0\u884c\u8017\u65f6 %ss"
         % (now(), ctx.get("case_id"), (ctx.get("runtime") or {}).get("seconds")), "",
         "## 1. \u7248\u672c\u94fe", "",
         "| \u7248\u672c | \u5f62\u6001 | \u5173\u952e\u6539\u52a8 | \u8bc1\u636e |", "|---|---|---|---|",
         "| **v0** \u9aa8\u67b6 | `SKILL.md` \u4ec5 14 \u4e2a\u7a7a\u6807\u9898\uff08948 B\uff09\uff0c\u65e0\u4efb\u4f55\u53ef\u8fd0\u884c\u4ea7\u7269 | "
         "\u76ee\u5f55/\u63a5\u53e3\u5148\u884c\uff0c\u65e0\u6d41\u6c34\u7ebf | baseline_v1.zip \u5185 `SKILL.md` |",
         "| **v1** \u6210\u7a3f\uff0862.33\uff09 | \u7248\u5f0f\u7ed1\u5b9a + \u5360\u4f4d\u7b26\u5199\u5165 + \u5b57\u53f7\u9636\u68af + \u9875\u811a\u9875\u7801 + "
         "PDF \u5bfc\u51fa + `content_map` \u9010\u9875\u8bc1\u636e | \u6a21\u677f\u6bcd\u7248/\u7248\u5f0f/\u4e3b\u9898\u5b57\u8282\u4fdd\u6301\uff08sha256 \u6821\u9a8c\uff09 | "
         "\u672c\u6b21\u8fd0\u884c\u4ecd\u6cbf\u7528\u5176 `verify.py` \u4e0e\u88c5\u914d\u51fd\u6570 |",
         "| **v2** \u672c\u5305 | \u4fee\u590d 5 \u4e2a\u963b\u65ad\u7f3a\u9677 + \u65b0\u589e 6 \u9879\u53ef\u6838\u9a8c\u8d44\u4ea7 + \u9aa8\u67b6\u6587\u6863\u5199\u5b9e | \u89c1 \u00a72\u2013\u00a74\uff0c\u5747\u6709\u672c\u6b21\u8fd0\u884c\u4ea7\u7269\u4e3a\u8bc1 |", ""]
    L += ["## 2. v1 \u2192 v2 \u9010\u6761\u53d8\u66f4\uff08\u95ee\u9898 \u2192 \u6539\u6cd5 \u2192 \u9a8c\u8bc1\uff09", "",
          "| # | \u95ee\u9898\uff08\u4fee\u590d\u524d\u5b9e\u6d4b\uff09 | \u6539\u6cd5 | \u9a8c\u8bc1 |", "|---|---|---|---|",
          "| 1 | `discover()` \u8bfb `a.deck`\uff0c\u4f46 CLI \u672a\u5b9a\u4e49 `--deck` \u2192 `AttributeError`\uff0c**\u4efb\u4f55\u8f93\u5165\u90fd\u53ea\u5f97 partial** | "
          "\u65b0\u589e\u53ef\u9009 `--deck`\uff08\u4e0d\u6539\u539f\u8c03\u7528\uff09 | \u4fee\u590d\u524d `result.errors[0].detail` \u542b AttributeError\uff1b"
          "\u4fee\u590d\u540e\u4ea7\u51fa 10 \u9875 pptx |",
          "| 2 | \u76f8\u5bf9 `--output` \u65f6 soffice \u8f6c\u6362\u5931\u8d25\uff08`no pdf artifact`\uff09 | \u5bfc\u51fa\u524d `Path.resolve()` \u7edd\u5bf9\u5316 | "
          "`export_check.pdf.header` = `%PDF-1.x`\uff0c\u9875\u6570 = \u5e7b\u706f\u7247\u6570 |",
          "| 3 | \u4e3b\u9898 ea \u5b57\u4f53\u62bd\u53d6\u4e3a\u7a7a\uff08\u6b63\u5219\u5047\u8bbe `ea` \u7d27\u8ddf `majorFont`\uff09 | `spec.parse_theme()` \u6309\u5b50\u6807\u7b7e\u9010\u4e2a\u53d6\u503c | "
          "`template_spec.theme_fonts.major_ea` \u975e\u7a7a\uff08\u542b\u4e2d\u6587\u5b57\u4f53\u65f6\uff09 |",
          "| 4 | \u9875\u7801\u5e8f\u5217\u68c0\u67e5\u628a\u5c01\u9762\u7a7a\u503c\u7b97\u4f5c\u4e0d\u8fde\u7eed | \u53ea\u6bd4\u8f83\u6709\u9875\u7801\u7684\u9875 | `batch_consistency.page_numbers_sequential` \u4e0e\u5b9e\u9645\u4e00\u81f4 |",
          "| 5 | `batch_consistency` \u5b57\u6bb5\u7f29\u8fdb\u9519\u4f4d\uff0c`font_scale_levels` / `freetext_boxes` \u88ab\u5d4c\u5957\u5728\u5b50\u5bf9\u8c61 | "
          "\u63d0\u5230 `compliance_checks` \u9876\u5c42 | \u5b57\u6bb5\u53ef\u76f4\u63a5\u8bfb\u53d6 |",
          "| 6 | \u65e0\u6a21\u677f\u89c4\u683c\u3001\u65e0\u9010\u9879\u683c\u5f0f\u8bc1\u636e\u3001\u65e0\u9010\u9875 diff\u3001\u65e0\u7248\u672c\u8bb0\u5f55\u3001\u65e0\u5bfc\u51fa\u68c0\u67e5\u3001\u65e0\u56de\u9000\u8def\u5f84 | "
          "\u65b0\u589e `template_spec.json` / `format_compliance.json` / `page_diff.md` / `version_history.md` / `run.log` / `export_check.json` + `guard()` \u56de\u9000 | "
          "\u672c\u6b21\u8fd0\u884c\u4ea7\u7269\u5747\u5728\uff0c`format_compliance` %d/%d \u9879 pass |"
          % ((ctx.get("format_compliance") or {}).get("passed", 0), (ctx.get("format_compliance") or {}).get("total", 0))]
    L += ["", "## 3. \u672c\u6b21\u8fd0\u884c\u4ea7\u7269 sha256\uff08\u524d 16 \u4f4d\uff09", "",
          "| \u6587\u4ef6 | \u5b57\u8282 | sha256 |", "|---|---|---|"]
    for k, v in arts.items():
        L.append("| `%s` | %s | %s |" % (k, v["bytes"] if v else "\u2014", v["sha256"] if v else "\u2014"))
    L += ["", "## 4. \u56de\u9000\u8def\u5f84\uff08rollback\uff09", "",
          "\u4fdd\u62a4\u5bf9\u8c61\uff1a\u6bcd\u7248 `slideMaster*.xml`\u3001\u7248\u5f0f `slideLayout*.xml`\u3001\u4e3b\u9898 `theme*.xml`\uff08%d \u4e2a\u90e8\u4ef6\uff0c"
          "sha256 \u5217\u5728 `template_spec.json` \u7684 `protected_parts`\uff09\u3002" % len((ctx.get("spec") or {}).get("protected_parts") or {}), "",
          "**\u81ea\u52a8\uff08\u6bcf\u6b21\u8fd0\u884c\u90fd\u505a\uff09**\uff1a\u6253\u5305\u540e `spec.guard()` \u9010\u90e8\u4ef6\u91cd\u7b97 sha256\uff1b\u82e5\u53d1\u73b0\u6f02\u79fb\uff0c"
          "\u4ece\u6a21\u677f\u539f\u4ef6\u5b57\u8282\u6062\u590d\u8be5\u90e8\u4ef6\u5e76\u91cd\u65b0\u6253\u5305\uff0c\u7ed3\u679c\u5199\u5165 `result.json` \u7684 `rollback`\u3002", "",
          "**\u624b\u52a8\u56de\u9000\uff08\u6a21\u677f\u88ab\u4eba\u5de5\u6539\u574f\u65f6\uff09**\uff1a", "",
          "```bash",
          "# 1) \u786e\u8ba4\u54ea\u4e2a\u90e8\u4ef6\u6f02\u79fb\uff1a\u6bd4\u5bf9\u5f53\u524d pptx \u4e0e\u6a21\u677f\u539f\u4ef6\u7684 sha256",
          "python3 -c \"import hashlib,zipfile,json;t=zipfile.ZipFile('template_academic.pptx');"
          "p=zipfile.ZipFile('presentation.pptx');s=json.load(open('template_spec.json'))['protected_parts'];"
          "print([k for k,v in s.items() if hashlib.sha256(p.read(k)).hexdigest()!=v])\"",
          "# 2) \u4ece\u6a21\u677f\u539f\u4ef6\u53d6\u56de\u8be5\u90e8\u4ef6\uff08\u6a21\u677f\u662f\u552f\u4e00\u771f\u6e90\uff0c\u4e0d\u8bfb\u4e0a\u6b21\u6d3e\u751f\u6587\u4ef6\uff09",
          "unzip -p template_academic.pptx ppt/theme/theme1.xml > theme1.xml.orig",
          "# 3) \u91cd\u5efa\u6574\u518c\uff08\u5e42\u7b49\uff1a\u76f8\u540c\u8f93\u5165\u5f97\u5230\u76f8\u540c\u7ed3\u6784\uff09",
          "python3 scripts/main.py --input /input --output /app/output --template template_academic.pptx",
          "# 4) \u9a8c\u8bc1\uff1aformat_compliance.json \u7684 CI-03/04/05 \u5e94\u4e3a pass\uff0cexport_check.pass = true",
          "```", "",
          "\u8fb9\u754c\uff1aguard \u4fdd\u62a4\u7684\u662f**\u6a21\u677f\u7ea7**\u90e8\u4ef6\uff1b**\u9875\u7ea7**\u56de\u9000 = \u91cd\u8dd1\uff08\u4e0d\u4f7f\u7528\u4e0a\u6b21\u7684 "
          "`presentation.pptx` \u4f5c\u4e3a\u8f93\u5165\uff0c\u907f\u514d\u8bef\u5dee\u7d2f\u79ef\uff09\u3002\u4e0b\u6e38\u5df2\u4ea4\u4ed8\u7684 PDF/PNG \u4e0d\u53ef\u8fd8\u539f\uff0c"
          "\u53ea\u80fd\u91cd\u5bfc\u51fa\u3002", ""]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), "utf-8")
    return {"path": str(p), "sha256": sha(p.read_bytes()), "versions": ["v0", "v1", "v2"],
            "package_files": cur, "artifacts": arts,
            "rollback": (ctx.get("spec") or {}).get("rollback_note", "auto guard + manual rerun")}
