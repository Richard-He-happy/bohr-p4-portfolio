#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-10 开题报告 Skill：init/show/check/build（标准库、离线）。"""
import argparse, json, os, re, shutil, subprocess, sys, time, traceback, zipfile, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal as P  # noqa: E402
import assets as A  # noqa: E402

V = "2.1.0"
EL = [("background", "一、研究背景与缺口"), ("problem", "二、研究问题与可证伪性"), ("objectives", "三、研究目标"),
      ("methods", "四、技术路线与方法"), ("plan", "五、阶段计划与里程碑"), ("risks", "六、风险与备选方案"),
      ("outcomes", "七、预期成果与验证方式")]
T0 = time.time()
norm, al, period, paras = P.norm, P.al, P.period, P.paras
NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|mg|g|mL|mM|h|天|周|个月|月|年|例|人|次|万元|元)")
IMG = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def dump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(t, p)


def load(path):
    p = Path(path)
    if not p.is_file():
        return None, "not_found"
    err = "unreadable"
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return json.loads(p.read_text(encoding=enc).lstrip("\ufeff")), None
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
    return None, err


def dec(raw):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def pdf_plain(raw):
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        b = m.group(1)
        try:
            b = zlib.decompress(b)
        except Exception:
            pass
        if b"Tj" in b or b"TJ" in b:
            t = " ".join(x.decode("latin-1", "replace") for x in re.findall(rb"\(((?:\\.|[^\\()]){1,500})\)", b))
            if norm(t):
                out.append(t)
    return "\n".join(out)


def pdf_text(p):
    for exe in ("pdftotext", "pdf-text-tool"):
        w = shutil.which(exe)
        if w:
            try:
                cmd = [w, str(p)] if exe == "pdf-text-tool" else [w, "-layout", str(p), "-"]
                t = dec(subprocess.run(cmd, capture_output=True, timeout=120).stdout)
                if len(norm(t)) > 200:
                    return t, "ext:" + exe
            except Exception:
                pass
    try:
        import fitz  # type: ignore
        t = "\n".join(g.get_text() for g in fitz.open(str(p)))
    except Exception:
        try:
            t = __import__("pdfminer.high_level", fromlist=["x"]).extract_text(str(p))
        except Exception:
            t = ""
    if len(norm(t)) > 50:
        return t, "optional-lib"
    return pdf_plain(Path(p).read_bytes()), "stdlib-crude"


ENT = {"amp": "&", "lt": "<", "gt": ">"}


def zip_text(p):
    with zipfile.ZipFile(p) as z:
        n = z.namelist()
        if any(x.startswith("word/") for x in n):
            s = "\n".join(z.read(f).decode("utf-8", "replace")
                          for f in sorted(x for x in n if re.match(r"word/(document|header|footer)", x)))
            s = re.sub(r"<[^>]+>", "", re.sub(r"<w:tab[^>]*/>", "\t", re.sub(r"</w:p>", "\n", s)))
            return re.sub(r"&(amp|lt|gt);", lambda m: ENT[m.group(1)], s)
        sh = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)) for si in
              re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.S)] \
            if "xl/sharedStrings.xml" in n else []
        out = []
        for f in sorted(x for x in n if x.startswith("xl/worksheets/")):
            for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read(f).decode("utf-8", "replace"), re.S):
                vals = []
                for a, body in re.findall(r"<c\b([^>]*)>(.*?)</c>", row, re.S):
                    v = (re.search(r"<v>(.*?)</v>", body, re.S) or [None, ""])[1]
                    vals.append(sh[int(v)] if 't="s"' in a and v.isdigit() and int(v) < len(sh) else v)
                if any(norm(x) for x in vals):
                    out.append("\t".join(vals))
        return "\n".join(out)


def read_mat(p):
    p = Path(p)
    e = p.suffix.lower()
    try:
        raw = p.read_bytes()
        if e == ".pdf" or raw[:4] == b"%PDF":
            return ("pdf",) + pdf_text(p)
        if e in (".docx", ".xlsx", ".xlsm") or raw[:2] == b"PK":
            return e[1:] or "zip", zip_text(p), "zip-openxml"
        if e in IMG:
            return "image", "", "no_ocr"
        t = dec(raw)
        if t and sum(c.isprintable() or c in "\n\t" for c in t[:3000]) > 0.9 * len(t[:3000]):
            return "text", t, "plain"
        return "binary", "", "unsupported"
    except Exception as x:
        return "error", "", "%s: %s" % (type(x).__name__, x)


def alltext(idx):
    return "\n".join(pa["text"] for m in idx.get("materials", []) for pa in m["paras"])


def scan(root):
    root = Path(root)
    return [p for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")
            and "__pycache__" not in p.parts] if root.exists() else []


def find_case(indir):
    bad = None
    for p in [Path(indir) / x for x in ("case.json", "input.json", "case/case.json")] + \
            [x for x in scan(indir) if re.match(r"(case|input)[^/]*\.json$", x.name, re.I)]:
        if p.is_file():
            o, e = load(p)
            if isinstance(o, dict):
                return o, str(p), None
            bad = "%s: %s" % (p.name, e)
    return {}, None, bad or "未找到 case.json（%s）" % indir


def gk(case, *names, default=None):
    for n in names:
        for k, v in (case or {}).items():
            if str(k).lower() == n.lower() and v not in (None, "", [], {}):
                return v
    return default


def build_index(indir, cpath=None):
    skip = {str(Path(cpath).resolve())} if cpath else set()
    mats, notes = [], []
    for i, p in enumerate([x for x in scan(indir) if str(x.resolve()) not in skip], 1):
        kind, text, how = read_mat(p)
        rel = str(p.relative_to(Path(indir))) if Path(indir) in p.parents else p.name
        if kind in ("image", "binary", "error") or not norm(text):
            notes.append({"material": rel, "note": how})
        mats.append({"id": "M%d" % i, "rel": rel, "kind": kind, "chars": len(text or ""), "extract": how,
                     "size": p.stat().st_size, "text": (text or "")[:400000],
                     "paras": [{"loc": "p%d" % j, "text": t} for j, t in enumerate(paras(text), 1)]})
    return {"input_dir": str(indir), "built_at": now(), "materials": mats, "extract_notes": notes,
            "total_chars": sum(m["chars"] for m in mats)}


# ---- 输出契约：原样回填 output_contract 全部字段
KM = [tuple(x.split(":")) for x in (
    "deliverable:deliverable artifact:deliverable preserved:preserved_facts fact:preserved_facts "
    "evidence:evidence_map cite:evidence_map source:evidence_map change:change_log revision:change_log "
    "diff:change_log uncertain:uncertainty pending:pending_human risk:risks milestone:milestones "
    "plan:milestones question:research_questions objective:objectives outcome:outcomes method:methods "
    "route:methods coverage:coverage matrix:coverage").split()]
KEYS = ("preserved_facts evidence_map change_log changes research_questions objectives methods milestones "
        "risks outcomes sources uncertainty pending_human errors degradations").split()


def fill_contract(contract, p):
    return {k: (p[str(k).lower()] if (p.get(str(k).lower()) is not None or str(k).lower() in p)
                else next((p[c] for kw, c in KM if kw in str(k).lower()), None)) for k in (contract or {})}


def base(case, status):
    r = {k: [] for k in KEYS}
    r.update(case_id=gk(case, "case_id", "id"), status=status, skill="writing-10-proposal", note="",
             deliverable=None, output_contract={}, coverage={}, runtime={})
    return r


def finalize(outdir, res):
    try:
        f = fill_contract(res.pop("_contract", {}) or {}, res)
        res["output_contract"] = f
        for k, v in f.items():
            res.setdefault(k, v)
        res["changes"] = res.get("change_log") or []
        res["runtime"] = dict(res.get("runtime") or {}, elapsed_s=round(time.time() - T0, 2),
                              python=sys.version.split()[0], finished_at=now(), skill_version=V)
        out = {k: res[k] for k in ["case_id", "status", "note", "deliverable", "output_contract"] if k in res}
        out.update({k: v for k, v in res.items() if k not in out})
        dump(Path(outdir) / "result.json", out)
        A.hook(outdir, out)
    except Exception as e:
        try:
            dump(Path(outdir) / "result.json", {"status": "input_error", "errors": ["finalize: %s" % e]})
        except Exception:
            pass


def cmd_init(a):
    outdir, work = Path(a.output).resolve(), Path(a.work).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, cpath, cerr = find_case(a.input)
    res = base(case, "partial")
    res["note"] = "init: 索引已建"
    res["_contract"] = gk(case, "output_contract", default={}) or {}
    if cerr:
        res["errors"].append(cerr)
    finalize(outdir, res)
    try:
        idx = build_index(a.input, cpath)
        dump(work / "index.json", idx)
        A.note(outdir, "INIT", "index materials=%d chars=%d" % (len(idx["materials"]), idx["total_chars"]))
        tm = next((p for p in [Path(a.input) / "task.md"] + [x for x in scan(a.input) if x.name.lower() == "task.md"] if p.is_file()), None)
        print("== init v%s == %s | task.md %s" % (V, cpath, tm or "-"))
        print("contract %s | materials %d | period %s" % (
            ", ".join(map(str, gk(case, "output_contract", default={}) or {})) or "-", len(idx["materials"]),
            period(alltext(idx))))
        for m in idx["materials"]:
            print("  %-3s %-34s %-6s %6d字 %3d段 %s" % (m["id"], m["rel"][:34], m["kind"], m["chars"], len(m["paras"]), m["extract"]))
        for k in ("organizer_workorder", "organizer_edit_workorder", "task_instruction"):
            if gk(case, k):
                print("%s %s" % (k, json.dumps(gk(case, k), ensure_ascii=False)[:400]))
        print("NEXT: %s/draft.json" % work)
    except Exception as e:
        print("init degraded: %s" % e)
    return 0


def cmd_show(a):
    idx, err = load(Path(a.work).resolve() / "index.json")
    if not isinstance(idx, dict):
        print("no index (%s); run init" % err)
        return 0
    m = [x for x in idx.get("materials", []) if x["id"] == (a.id or "").upper()]
    if not m:
        print("unknown %s; have %s" % (a.id, [x["id"] + "=" + x["rel"] for x in idx.get("materials", [])]))
        return 0
    m, pat, n = m[0], (re.compile(a.grep, re.I) if a.grep else None), 0
    print("== %s | %s ==" % (m["id"], m["rel"]))
    for pa in m["paras"]:
        if not pat or pat.search(pa["text"]):
            print("\n[%s/%s]\n%s" % (m["id"], pa["loc"], pa["text"][:1200]))
        n += 1
        if n >= 400:
            print("\n... truncated")
            break
    return 0


def cmd_check(a):
    work = Path(a.work).resolve()
    idx, _ = load(work / "index.json")
    if not isinstance(idx, dict):
        idx = build_index(a.input)
        dump(work / "index.json", idx)
    draft, dpath, derr = P.load_draft(work)
    rep = P.check(draft, idx)
    dump(work / "check_report.json", {"draft_path": dpath, "draft_error": derr, "report": rep})
    c = rep["counts"]
    A.note(a.output, "CHECK", "要素 %d/%d 证据 %d/%d 错误 %d" % (
        c["sections_present"], c["sections_total"], c["evidence_verified"], c["evidence_total"], len(rep["errors"])))
    print("== check == draft %s %s" % (dpath or "none", derr or ""))
    print("要素 %d/%d | rq %d | 里程碑 %d | 风险 %d/%d类 | 成果 %d | 证据 %d/%d | %s" % (
        c["sections_present"], c["sections_total"], c["rqs"], c["milestones"], c["risks"], c["risk_types"],
        c["outcomes"], c["evidence_verified"], c["evidence_total"],
        "PASS" if not rep["errors"] else "FIX %d" % len(rep["errors"])))
    print("\n".join(["ERROR " + e for e in rep["errors"]] + ["WARN  " + w for w in rep["warnings"][:20]]))
    return 0


def cmd_build(a):
    indir, outdir, work = (Path(x).resolve() for x in (a.input, a.output, a.work))
    outdir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case, cpath, cerr = find_case(indir)
    contract = gk(case, "output_contract", default={}) or {}
    res = base(case, "partial")
    res["note"] = "build"
    res["_contract"] = contract
    finalize(outdir, dict(res))
    try:
        tpl = P.load_tpl()
        idx, ierr = load(work / "index.json")
        if not isinstance(idx, dict) or not isinstance(idx.get("materials"), list):
            idx = build_index(indir, cpath)
            dump(work / "index.json", idx)
            if ierr != "not_found":
                res["degradations"].append("索引重建")
        if cerr:
            res["errors"].append(cerr)
        mo, pq = period(alltext(idx))
        ctx = {"case_id": gk(case, "case_id"), "title": norm(gk(case, "title", "case_title", default="")),
               "months": mo or 12, "period_quote": pq, "seeds": P.seed_sentences(idx), "facts": P.auto_facts(idx, NUM),
               "n_materials": len(idx.get("materials", [])), "version": V, "now": now(), "titles": dict(EL)}
        gaps = [] if mo else [{"item": "研究周期未识别", "why": "按 12 个月占位", "needed_by": "开题前"}]
        draft, dpath, derr = P.load_draft(work)
        src = "agent" if (dpath and not derr) else ("agent_md" if dpath else "fallback")
        if derr:
            res["degradations"].append(derr)
        fb = P.fallback_draft(ctx, tpl)
        if not draft or not al(draft.get("sections")):
            draft, src = fb, "fallback"
        else:
            have = {str(s.get("id")).lower() for s in al(draft.get("sections")) if isinstance(s, dict)}
            miss = [s for s in fb["sections"] if s["id"] not in have]
            draft["sections"] = al(draft.get("sections")) + miss
            gone = [k for k in ("rqs", "objectives", "steps", "milestones", "risks", "outcomes", "period", "resources")
                    if not al(draft.get(k))]
            draft.update({k: fb.get(k) for k in gone})
            res["degradations"] += ["要素 %s 补齐" % s["id"] for s in miss] + ["%s 用兜底" % k for k in gone]
            if miss or [k for k in gone if k not in ("period", "resources")]:
                src = "agent+template"
        dump(work / "draft.effective.json", draft)
        rep = P.check(draft, idx)
        c = rep["counts"]
        ratio = c["evidence_verified"] / c["evidence_total"] if c["evidence_total"] else 0.0
        status = "ok"
        if not idx.get("materials"):
            status = "input_error"
        elif not any(m.get("chars") for m in idx["materials"]):
            status = "insufficient_evidence"
            res["uncertainty"].append({"item": "材料无可解析文本", "why": "图片/二进制/解析失败", "effect": "只能交付骨架"})
        elif src != "agent" or rep["errors"] or ratio < 0.9:
            status = "partial"
        ctx.update(status=status, draft_source=src)
        md = P.render_proposal(draft, ctx, rep, tpl)
        (outdir / "proposal.md").write_text(md, encoding="utf-8")
        res["errors"] += rep["errors"] + (["未找到输入材料"] if not idx.get("materials") else [])
        res.update({"status": status, "coverage": rep["coverage"],
                    "deliverable": {"path": "proposal.md", "format": "markdown", "editable": True, "chars": len(md),
                                    "sections": [t for _, t in EL], "draft_source": src},
                    "preserved_facts": [f for f in al(draft.get("preserved_facts")) if isinstance(f, dict)] or ctx["facts"],
                    "change_log": [x for x in al(draft.get("change_log")) if isinstance(x, dict)] or
                                  [{"action": "起草", "target": "proposal.md", "reason": "依据材料生成初稿", "before": "—", "after": "v1"}],
                    "evidence_map": [{"claim_ref": e.get("ref"), "source_id": e.get("source_id"),
                                      "locator": e.get("found_locator") or e.get("locator"), "quote": e.get("quote"),
                                      "match": e.get("match"), "status": e.get("status")} for e in rep["evidence"]],
                    "sources": [{"id": m["id"], "file": m["rel"], "kind": m["kind"], "chars": m["chars"],
                                 "extraction": m["extract"]} for m in idx.get("materials", [])],
                    "note": "build: %s | 要素 %d/%d | 证据 %d/%d" % (src, c["sections_present"], c["sections_total"],
                                                                c["evidence_verified"], c["evidence_total"])})
        for key, sk in (("research_questions", "rqs"), ("objectives", "objectives"), ("methods", "steps"),
                        ("milestones", "milestones"), ("risks", "risks"), ("outcomes", "outcomes")):
            res[key] = [x for x in al(draft.get(sk)) if isinstance(x, dict)]
        res["pending_human"] += gaps + [p for p in al(draft.get("pending_human")) if isinstance(p, dict)] + rep["gaps"]
        res["uncertainty"] += [{"item": "研究问题依据", "why": "RQ 为模板/阈值待确认" if src != "agent" else "阈值依据须导师确认",
                                "effect": "结论为可执行草案，非已获结果"},
                               {"item": "引文命中率 %.0f%%" % (ratio * 100), "why": "部分 quote 未逐字命中或跨段",
                                "effect": "仅命中条目可作证据"}]
        print("== build == %s | %s | %.1f KB | 要素 %d/%d | 证据 %d/%d" % (
            status, src, len(md) / 1024.0, c["sections_present"], c["sections_total"], c["evidence_verified"], c["evidence_total"]))
        print("\n".join(["DEGRADE " + d for d in res["degradations"][:8]] + ["ERROR " + e for e in res["errors"][:8]]))
    except Exception as e:
        res["errors"].append("build: %s: %s" % (type(e).__name__, e))
        print("build degraded: %s" % e)
    finally:
        res["_contract"] = contract
        try:
            if not (outdir / "proposal.md").is_file():
                (outdir / "proposal.md").write_text("# 开题报告（兜底骨架）\n\n" + "\n\n".join(
                    "## %s\n\n待补充，见 result.json。" % t for _, t in EL), encoding="utf-8")
                res["degradations"].append("proposal.md 为占位骨架")
        except Exception:
            pass
        A.emit(outdir, work, res, locals().get("rep"), locals().get("draft"), locals().get("idx"), V)
        finalize(outdir, res)
        A.post(outdir, work, res)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="writing-10 开题报告 Skill：init/show/check/build")
    sub = ap.add_subparsers(dest="cmd")
    for name, hlp in (("init", "扫描材料建索引并写 partial result.json"), ("show", "打印带 locator 的原文"),
                      ("check", "校验工作稿的要素/证据/数字一致性"), ("build", "生成 proposal.md 与 result.json"),
                      ("audit", "重算 5 件套与结构化产物（不重渲染）")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"))
        p.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "/app/output"))
        p.add_argument("--work", default=os.environ.get("WORK_DIR", "/app/work"))
        if name == "show":
            p.add_argument("--id", required=True, help="材料编号，如 M1")
            p.add_argument("--grep", default=None)
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 0
    return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
            "audit": A.cmd_audit}[a.cmd](a) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(limit=2)
        sys.exit(0)
