#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py — 思维导图 Skill 主流程：init / show / check / build。

Agent 负责写工作稿（theme + nodes + edges + 逐字证据），脚本负责材料索引、证据校验、
SVG/PNG 渲染与 result.json 回填；工作稿缺失时用确定性要点抽取兜底，保证永远有可打开的完整产物。
纯标准库、不联网、不依赖 CWD；所有子命令退出码恒为 0。
"""
from __future__ import annotations

import argparse, hashlib, html, importlib.util, json, os, re, shutil, subprocess, sys, time, zipfile, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN = Path(os.environ.get("BOHR_INPUT_DIR") or "/input")
WK = Path(os.environ.get("BOHR_WORK_DIR") or "/app/work")
OUT = Path(os.environ.get("BOHR_OUTPUT_DIR") or "/app/output")
SKILL, T0, MAXT = "mindmap-skill/1.1", time.time(), 600_000
EXT = {".pdf": "pdf", ".docx": "docx", ".md": "text", ".txt": "text", ".tex": "text", ".json": "json",
       ".csv": "csv", ".tsv": "tsv", ".yaml": "text", ".yml": "text", ".xml": "text", ".html": "text",
       ".htm": "text", ".bib": "text", ".rtf": "text", ".xlsx": "sheet", ".pptx": "slides",
       ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".bmp": "image", ".tif": "image",
       ".tiff": "image", ".webp": "image", ".svg": "svg"}
SKIP = {".py", ".pyc", ".zip", ".gz", ".tar", ".so", ".exe", ".sh", ".js", ".css"}
ROLE = {"mindmap.svg": "主产物：可编辑导图", "mindmap.json": "结构与证据",
        "content_map.json": "来源映射", "mindmap.png": "预览图"}


def _V():
    try:
        sp = importlib.util.spec_from_file_location("mmverify", HERE / "verify.py")
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m
    except Exception:
        return None


V = _V()


def _R():
    try:
        sp = importlib.util.spec_from_file_location("mmreport", HERE / "report.py")
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m
    except Exception:
        return None


def _finalize_safe(res, contract, ctx, out_path, closes=None, extra=None):
    """verify.py 不可用或抛错时仍写出合法 result.json。"""
    try:
        return V.finalize(res, contract, ctx, out_path, closes, extra)
    except Exception:
        out = dict(res)
        out.update(extra or {})
        dump(out_path, out)
        return out


def assets(stage, case, con, ix, model=None, svg=None, contract_values=None, cid=None,
           errors=None, degradations=None, do_probe=True, changed=None, artifacts=None, checkpoint=None):
    """写五项可核验资产；report.py 缺失/抛错只降级，不影响主产物与退出码。"""
    R = _R()
    if R is None:
        return {"error": "report.py 不可用：跳过 golden/diff/version/self_check"}
    try:
        return R.emit(stage, cid=cid or ix.get("case_id"), case=case or {}, contract=con or {}, index=ix,
                      model=model, svg=svg, out=OUT, work=WK, contract_values=contract_values,
                      errors=errors, degradations=degradations, do_probe=do_probe,
                      changed=changed, artifacts=artifacts, checkpoint=checkpoint)
    except Exception as exc:
        try:
            R.log(WK, OUT, stage, "资产层异常：%s" % exc, "ERROR")
        except Exception:
            pass
        return {"error": str(exc)[:200]}


def extra_of(a):
    """整理成 result.json 的追加字段；失败时也留可判读结构。"""
    e = {}
    for k in ("golden_standard", "diff_report", "version_history", "self_check"):
        if isinstance((a or {}).get(k), dict):
            e[k] = a[k]
    if (a or {}).get("error"):
        e.setdefault("self_check", {"path": None, "pass": False, "checks": 0,
                                    "failed": ["assets_unavailable"], "error": a["error"]})
    return e


def ensure(p):
    try:
        p.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def dump(p, obj):
    try:
        ensure(p.parent)
        p.write_bytes(json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))
        return True
    except Exception:
        return False


def load(p):
    try:
        return json.loads(Path(p).read_bytes().decode("utf-8-sig"))
    except Exception:
        return None


def dec(raw):
    for e in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(e)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def paras(t):
    out = []
    for p in re.split(r"\n\s*\n", t.replace("\r\n", "\n").replace("\r", "\n")):
        p = re.sub(r"[ \t]+", " ", p).strip()
        if len(p) >= 2:
            out.append(p)
    return out


def sniff(p, guess):
    try:
        head = p.open("rb").read(16)
    except Exception:
        head = b""
    if head.startswith(b"%PDF"):
        return "pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or head[:4] in (b"GIF8", b"II*\x00"):
        return "image"
    if head[:4] == b"PK\x03\x04":
        try:
            names = zipfile.ZipFile(p).namelist()
            for k, v in (("word/document.xml", "docx"), ("xl/workbook.xml", "sheet"), ("ppt/presentation.xml", "slides")):
                if k in names:
                    return v
        except Exception:
            pass
        return "zip"
    if head[:1] in (b"{", b"["):
        return "json"
    return "text" if guess in ("pdf", "docx", "sheet", "slides", "json") else (guess or "text")


def find_case():
    c = []
    if IN.is_dir():
        if (IN / "case.json").is_file():
            c.append(IN / "case.json")
        c += [p for p in sorted(IN.rglob("*.json")) if p.name.lower().startswith("case") and p not in c]
    for p in c:
        o = load(p)
        if isinstance(o, dict):
            return o, p
    return {}, (c[0] if c else None)


def sem(case, pat, default=None):
    for k, v in (case or {}).items():
        if isinstance(v, (dict, list, str)) and re.search(pat, str(k), re.I):
            return v
    return default


def mats_of(case):
    out = []
    if not IN.is_dir():
        return out
    for p in sorted(IN.rglob("*")):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() not in SKIP:
            out.append(p)
    return out


def pdf_units(p):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            txt = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(p), "-"],
                                 capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        except Exception:
            txt = ""
        if txt.strip():
            return ([{"locator": "p.%d¶%d" % (i, j), "text": q} for i, pg in enumerate(txt.split("\f"), 1)
                     for j, q in enumerate(paras(pg), 1)], "pdftotext")
    units = []
    try:
        raw = p.read_bytes()
    except Exception:
        return units, "读取失败"
    for i, m in enumerate(re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S), 1):
        try:
            d = zlib.decompress(m.group(1))
        except Exception:
            continue
        if b"Tj" in d or b"TJ" in d:
            parts = [re.sub(rb"\\([()\\])", rb"\1", t.group(0)[1:-1]).decode("latin-1", "replace")
                     for t in re.finditer(rb"\((?:\\.|[^\\()])*\)", d)]
            txt = " ".join(parts).strip()
            if len(txt) > 20:
                units.append({"locator": "stream%d" % i, "text": txt[:4000]})
    return units, "raw-stream(页码为估计值)"


def docx_units(p):
    try:
        x = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return []
    t = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n\n", x)))
    return [{"locator": "¶%d" % i, "text": q} for i, q in enumerate(paras(t), 1)]


def json_units(obj):
    out = []

    def walk(o, ptr, d=0):
        if len(out) >= 300 or d > 8:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, ptr + "/" + str(k).replace("~", "~0").replace("/", "~1"), d + 1)
        elif isinstance(o, list):
            for i, v in enumerate(o[:80]):
                walk(v, ptr + "/%d" % i, d + 1)
        else:
            s = str(o).strip()
            if s and s.lower() not in ("none", "null", "nan"):
                out.append({"locator": "json:" + (ptr or "/"), "text": s[:500]})

    walk(obj, "", 0)
    return out


def extract(p, kind):
    try:
        if kind == "pdf":
            return pdf_units(p)
        if kind == "docx":
            return docx_units(p), "zip-xml"
        if kind == "json":
            return json_units(load(p) or {}), "json-pointer"
        if kind in ("csv", "tsv"):
            raw = dec(p.read_bytes()) if p.stat().st_size < 4_000_000 else ""
            sep = "\t" if kind == "tsv" else ","
            return ([{"locator": "row%d" % i, "text": " | ".join(c.strip() for c in ln.split(sep))}
                     for i, ln in enumerate([x for x in raw.splitlines() if x.strip()][:800], 1)], "lines")
        if kind in ("text", "svg"):
            raw = dec(p.read_bytes()) if p.stat().st_size < 4_000_000 else ""
            return [{"locator": "¶%d" % i, "text": q} for i, q in enumerate(paras(raw), 1)], "text"
    except Exception as e:
        return [], "failed: %s" % e
    return [], "未支持格式(%s)" % kind


def title_of(units, stem):
    for u in units[:3]:
        t = u["text"].strip()
        m = re.search(r"^#{1,4}\s*(.{3,90})", t)
        if m:
            return m.group(1).strip()
        line = t.split("\n")[0].strip()
        if 4 <= len(line) <= 100:
            return line
    return stem


def build_index(case, contract, cpath):
    ms, total = [], 0
    for i, p in enumerate([x for x in mats_of(case) if not cpath or x.resolve() != Path(cpath).resolve()], 1):
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        kind = sniff(p, EXT.get(p.suffix.lower(), ""))
        try:
            sha = hashlib.sha1(p.read_bytes()[:2_000_000]).hexdigest()[:12]
        except Exception:
            sha = None
        units, ex = ([], "skipped(%s)" % kind)
        if kind in ("pdf", "docx", "json", "csv", "tsv", "text", "svg"):
            units, ex = extract(p, kind)
        kept, n = [], 0
        for u in units:
            t = u.get("text") or ""
            if total + n + len(t) > MAXT:
                break
            kept.append(u)
            n += len(t)
        total += n
        ms.append({"id": "M%d" % i, "name": p.name, "path": str(p), "kind": kind, "bytes": size, "sha1": sha,
                   "extractor": ex, "units": kept, "chars": n, "title": title_of(kept, p.stem),
                   "text_available": bool(kept), "note": None if kept else "无可用文本（图片/未支持格式/解析失败）"})
    wo = sem(case, r"workorder|requirement|deliverable_spec", None)
    order = ([x for x in json.dumps(wo, ensure_ascii=False, indent=1).splitlines() if x.strip()]
             if isinstance(wo, (dict, list)) else ([x for x in wo.splitlines() if x.strip()] if isinstance(wo, str) else []))
    return {"skill": SKILL, "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "input_dir": str(IN),
            "case_path": str(cpath) if cpath else None,
            "case_id": case.get("case_id") or case.get("id") or sem(case, r"case_?id|^id$"),
            "contract": contract, "instruction": sem(case, r"task_?instruction|instruction|prompt", ""),
            "workorder": order[:60], "materials": ms, "total_chars": total}


# ------------------------------------------------------------------ result.json
def case_contract(case):
    c = sem(case, r"output_contract|^contract$", {})
    return c if isinstance(c, dict) else {}


def base_result(cid, status="partial"):
    return {"case_id": cid, "status": status, "sources": [], "uncertainty": [], "pending_human": [],
            "errors": [], "degradations": [], "changes": [], "runtime": {}, "artifacts": [], "coverage": {}}


def closes():
    return {"skill": SKILL, "seconds": round(time.time() - T0, 1), "python": sys.version.split()[0]}


def src_list(ix):
    return [{"id": m["id"], "name": m["name"], "kind": m["kind"], "path": m["path"], "bytes": m["bytes"],
             "sha1": m["sha1"], "units": len(m["units"]), "extractor": m["extractor"]}
            for m in ix.get("materials") or []]


# ------------------------------------------------------------------ init
def cmd_init(args):
    ensure(WK)
    ensure(OUT)
    case, cp = find_case()
    con = case_contract(case)
    cid = case.get("case_id") or case.get("id") or sem(case, r"case_?id|^id$")
    r = base_result(cid)
    V.finalize(r, con, {"case_id": cid, "files": [], "note": "init：索引完成，产物待 build",
                        "deliverable": {"summary": "索引完成，导图待 build", "files": []},
                        "evidence_map": [], "preserved_facts": [], "change_log": [], "content_map": {},
                        "mindmap": {"file": None}, "preview": None, "coverage": {}}, OUT / "result.json", closes())
    ix = build_index(case, con, cp)
    dump(WK / "index.json", ix)
    sk = WK / "mindmap.json"
    if not (load(sk) or {}).get("nodes"):
        dump(sk, {"schema": "mindmap/1.0", "case_id": cid,
                  "_instructions": "填 theme.label、nodes[]、edges[]。每节点至少一条 evidence{material,locator,quote}，"
                                   "quote 须逐字来自材料；层级用 parent；edges 只写跨分支关系，无证据不画。详见 SKILL.md。",
                  "theme": {"id": "root", "label": "", "evidence": []}, "nodes": [], "edges": [],
                  "_materials": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "units": len(m["units"])}
                                 for m in ix["materials"]]})
    r["sources"] = src_list(ix)
    for m in ix["materials"]:
        if not m["text_available"]:
            r["uncertainty"].append("%s（%s）无可抽取文本" % (m["name"], m["kind"]))
        elif "raw-stream" in str(m["extractor"]):
            r["uncertainty"].append("%s 页码为估计值" % m["name"])
    r["changes"] = [{"action": "init", "detail": "索引 %d 份材料" % len(ix["materials"])}]
    ctx0 = {"case_id": cid, "files": [], "note": "init：索引完成，产物待 build",
            "deliverable": {"summary": "索引完成，导图待 build", "files": []},
            "evidence_map": [], "preserved_facts": [], "change_log": [], "content_map": {},
            "mindmap": {"file": None}, "preview": None, "coverage": {}}
    asst = assets("init", case, con, ix, cid=cid, contract_values=V.contract_values(con, ctx0),
                  errors=r["errors"], degradations=r["degradations"], do_probe=not args.no_probe,
                  changed=[{"action": "init", "detail": "建索引并落盘 v0 骨架与五项可核验资产"}])
    V.finalize(r, con, ctx0, OUT / "result.json", closes(), extra_of(asst))
    print("== init | case_id=%s | 材料 %d 份 | 文本 %d 字 | work=%s"
          % (ix.get("case_id"), len(ix["materials"]), ix.get("total_chars"), WK))
    if ix.get("instruction"):
        print("[任务] " + str(ix["instruction"])[:600])
    print("[契约] " + ", ".join(ix.get("contract") or {}) + "（共 %d 项，须全部回填）" % len(ix.get("contract") or {}))
    for m in ix["materials"]:
        print("%-4s %-6s %6dB u=%-3d %s%s" % (m["id"], m["kind"], m["bytes"], len(m["units"]), m["name"],
                                              "" if m["units"] else "  (无文本)"))
        if m["units"]:
            print("     [%s] %s" % (m["units"][0]["locator"], re.sub(r"\s+", " ", m["units"][0]["text"])[:100]))
    print("[下一步] show --material M1 → 写 %s → check → build" % sk)
    return 0


# ------------------------------------------------------------------ show / check
def cmd_show(a):
    ix = load(WK / "index.json")
    if not isinstance(ix, dict):
        print("缺 index.json，请先 init")
        return 0
    ms = ix.get("materials") or []
    sel = [m for m in ms if a.material in (m["id"], m["name"], m.get("path"))] if a.material else ms
    if not sel:
        print("未找到 %s；可选：%s" % (a.material, ", ".join(m["id"] for m in ms)))
        return 0
    budget = a.max_chars
    for m in sel:
        print("### %s · %s · %s · %d units" % (m["id"], m["name"], m["kind"], len(m["units"])))
        us = [u for u in m["units"] if not a.grep or a.grep.lower() in u["text"].lower()][a.start - 1:a.start - 1 + a.limit]
        if not us:
            print("  (无匹配单元)")
        for u in us:
            if budget <= 0:
                print("  ... 达 --max-chars 上限，用 --start 继续")
                return 0
            t = (u["text"] or "")[:min(1200, budget)]
            budget -= len(t)
            print("\n[%s] %s" % (u["locator"], t))
    return 0


def cmd_check(a):
    rep = V.validate(load(Path(a.work) if a.work else WK / "mindmap.json"), load(WK / "index.json") or {})
    dump(WK / "check.json", {k: v for k, v in rep.items() if k != "model"})
    st = rep["stats"]
    try:
        R = _R()
        if R:
            R.log(WK, OUT, "check", "校验 nodes=%d errors=%d warnings=%d depth=%d"
                  % (st["nodes"], rep["errors"], rep["warnings"], st["depth"]),
                  "INFO" if rep["ok"] else "WARN")
    except Exception:
        pass
    print("== 校验：%s（errors=%d warnings=%d）" % ("通过" if rep["ok"] else "未通过", rep["errors"], rep["warnings"]))
    for it in rep["issues"][:30]:
        print("  [%s] %s" % (it["severity"], it["message"]))
    print("节点 %d，带证据 %d（%.0f%%），证据命中 %d，未命中 %d，层级 %d"
          % (st["nodes"], st["verified_nodes"], 100 * st["verified_ratio"], st["verified_quotes"],
             st["rejected_quotes"], st["depth"]))
    print("结论：%s" % ("可 build" if rep["ok"] else "先修 error 再 build（否则 status=partial）"))
    return 0


# ------------------------------------------------------------------ build
def cmd_build(a):
    ensure(WK)
    ensure(OUT)
    # 版本检查点：覆盖前快照，便于按 version_history.md 回退
    ckpt = None
    try:
        hist = WK / "history"
        hist.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        for f in ("mindmap.json", "result.json"):
            if (OUT / f).is_file():
                shutil.copy2(OUT / f, hist / ("%s.%s" % (f, ts)))
                if f == "mindmap.json":
                    ckpt = str(hist / ("%s.%s" % (f, ts)))
    except Exception:
        pass
    ix = load(WK / "index.json")
    if not isinstance(ix, dict) or "materials" not in ix:
        c0, cp = find_case()
        ix = build_index(c0, case_contract(c0), cp)
        dump(WK / "index.json", ix)
    con, deg = ix.get("contract") or {}, []
    wp = Path(a.work) if a.work else WK / "mindmap.json"
    work, src = load(wp), "agent"
    if not isinstance(work, dict) or not work.get("nodes"):
        work, src = V.fallback_model(ix), "fallback"
        deg.append("工作稿缺失/为空：兜底生成最小完整导图")
    model = V.normalize_model(work, ix)
    if not model["nodes"]:
        model, src = V.normalize_model(V.fallback_model(ix), ix), "fallback"
        deg.append("工作稿节点无效：改用兜底抽取")
    if model["dropped"]:
        deg.append("未绘制 %d 条无证据/非法关系" % len(model["dropped"]))
    if model["unverified"]:
        deg.append("%d 个节点缺逐字证据：%s" % (len(model["unverified"]), ", ".join(model["unverified"][:8])))
    nev = sum(1 for n in model["nodes"] for e in n["evidence"] if e["verified"])
    nd, kids, pos, W, H = V.layout(model)
    meta = "%s | 节点 %d | 跨分支关系 %d | 已核验证据 %d 条 | 材料 %d 份 | %s" % (
        SKILL, len(model["nodes"]), len(model["edges"]), nev, len(ix.get("materials") or []),
        "Agent 工作稿" if src == "agent" else "脚本兜底")
    svg = V.render_svg(model, nd, pos, W, H, meta)
    (OUT / "mindmap.svg").write_bytes(svg.encode("utf-8"))
    how = V.png_export(OUT / "mindmap.svg", OUT / "mindmap.png")
    if not how:
        deg.append("无 SVG 渲染器/导出失败：PNG 未生成（保留可编辑 SVG）")
    else:
        try:                                  # 产物总体积预算：预览图过大时只保留 SVG
            if (OUT / "mindmap.png").stat().st_size > 45000:
                (OUT / "mindmap.png").unlink()
                how = None
                deg.append("PNG 超出体积预算(45KB)：删除预览，保留可编辑 SVG")
        except Exception:
            pass
    depth = max([n["level"] for n in model["nodes"]] or [0])
    mm = {"schema": "mindmap/1.0", "case_id": ix.get("case_id"), "generator": SKILL, "source_mode": src,
          "generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "theme": model["theme"],
          "nodes": model["nodes"], "edges": model["edges"], "dropped_edges": model["dropped"],
          "stats": {"nodes": len(model["nodes"]), "edges": len(model["edges"]),
                    "verified_evidence": nev, "depth": depth}}
    dump(OUT / "mindmap.json", mm)
    dump(OUT / "content_map.json", {"generated_from": src_list(ix), "nodes": mm["nodes"], "edges": mm["edges"],
                                   "dropped_edges": model["dropped"], "relation_legend": V.REL})
    probs = [f for f in ("mindmap.svg", "mindmap.json", "content_map.json")
             if not (OUT / f).is_file() or not (OUT / f).stat().st_size]
    probs += ["SVG 缺节点 %s" % i for i in [n["id"] for n in model["nodes"] if 'id="node-%s"' % n["id"] not in svg][:3]]
    if "<text" not in svg:
        probs.append("SVG 无 <text>")
    if probs:
        deg.append("自检：%s" % "; ".join(probs))
    png = "mindmap.png" if (OUT / "mindmap.png").is_file() else None
    files = [f for f in ("mindmap.svg", "mindmap.json", "content_map.json", png) if f]
    ratio = sum(1 for n in model["nodes"] if any(e["verified"] for e in n["evidence"])) / max(1, len(model["nodes"]))
    status = ("insufficient_evidence" if not [m for m in ix.get("materials") or [] if m["units"]] else
              "partial" if (src == "fallback" or len(model["nodes"]) < 6 or ratio < 0.6 or probs) else "ok")
    r = base_result(ix.get("case_id"), status)
    r["sources"] = src_list(ix)
    r["artifacts"] = [{"path": f, "bytes": (OUT / f).stat().st_size, "role": ROLE.get(f, f)} for f in files]
    r["coverage"] = {"materials": len(ix.get("materials") or []), "nodes": len(model["nodes"]),
                     "edges": len(model["edges"]), "depth": depth, "verified_ratio": round(ratio, 3),
                     "verified_quotes": nev, "source_mode": src}
    r["degradations"] = deg
    r["uncertainty"] = ["层级由 Agent 依据材料归纳（概括，非原文结构）" if src == "agent"
                        else "结构来自兜底抽取，未表达论证层级"]
    r["uncertainty"] += ["%s（%s）无可抽取文本" % (m["name"], m["kind"]) for m in ix.get("materials") or [] if not m["units"]]
    r["pending_human"] = [] if src == "agent" else ["复核兜底导图：确认主题、合并同级、补证据"]
    if model["unverified"]:
        r["pending_human"].append("补证据或删除节点：%s" % ", ".join(model["unverified"][:8]))
    if model["dropped"]:
        r["pending_human"].append("未绘制关系待确认（无证据/非法类型）：%s"
                                  % "; ".join("%s→%s(%s, %s)" % (d["from"], d["to"], d["type"], d["reason"])
                                              for d in model["dropped"][:6]))
    r["changes"] = [{"action": "build", "detail": "工作稿=%s；%d 节点/%d 关系；PNG=%s"
                     % (src, len(model["nodes"]), len(model["edges"]), how or "无")}]
    ev = [{"node": n["id"], "material": e["material"], "locator": e["locator"], "quote": e["quote"][:140],
           "verified": e["verified"]} for n in model["nodes"] for e in n["evidence"]]
    ctx = {"case_id": ix.get("case_id"), "files": files,
           "deliverable": {"summary": "%d 节点 / %d 跨分支关系 / %d 条逐字证据；主题「%s」"
                                      % (len(model["nodes"]), len(model["edges"]), nev, model["theme"]["label"]),
                           "primary": "mindmap.svg", "structure": "mindmap.json", "preview": png, "editable": True},
           "preview": png, "evidence_map": ev, "preserved_facts": ev, "content_map": ev,
           "mindmap": {"file": "mindmap.json", "theme": model["theme"]["label"], "nodes": len(model["nodes"]),
                       "edges": len(model["edges"]), "depth": depth},
           "note": "build 完成：%d 节点 / %d 关系 / 证据 %d 条；可控验资产已随产物落盘" % (
               len(model["nodes"]), len(model["edges"]), nev),
           "change_log": r["changes"], "uncertainty": r["uncertainty"], "coverage": r["coverage"]}
    model["source_mode"] = src
    asst = assets("build", None, con, ix, model=model, svg=svg, contract_values=V.contract_values(con, ctx),
                  cid=ix.get("case_id"), errors=r["errors"], degradations=deg, do_probe=not a.no_probe,
                  changed=r["changes"], artifacts=files, checkpoint=ckpt)
    sc = (asst or {}).get("self_check") or {}
    if "golden_standard" in (asst or {}):
        r["degradations"] = deg
        r["changes"].append({"action": "assets", "detail": "golden_standard/diff_report/version_history/self_check/run.log 已落盘"})
        r["uncertainty"].append("金标准覆盖判定按 locator/角色做确定性匹配，等价表述可能被低估（见 diff_report 第 5 节）")
    if sc.get("pass") is False:
        deg.append("自检未通过：%s（详见 self_check.json）" % (", ".join(sc.get("failed") or []) or "unknown"))
        r["degradations"] = deg
        if status == "ok":
            status = "partial"
        r["status"] = status
    V.finalize(r, con, ctx, OUT / "result.json", closes(), extra_of(asst))
    print("== build | status=%s mode=%s nodes=%d edges=%d evidence=%d depth=%d"
          % (status, src, len(model["nodes"]), len(model["edges"]), nev, depth))
    print("== 自检 | pass=%s checks=%s failed=%s" % (sc.get("pass"), sc.get("checks"), sc.get("failed")))
    print("== 金标准 | %s" % ((asst or {}).get("golden_standard") or {}))
    print("__END__")
    for f in files:
        print("  %-17s %7d B" % (f, (OUT / f).stat().st_size))
    for d in deg:
        print("  [降级] " + d[:160])
    return 0


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="思维导图 Skill：init 建索引 → Agent 写工作稿 → check → build。",
                                 epilog="示例：python3 main.py init && python3 main.py check && python3 main.py build")
    sub = ap.add_subparsers(dest="cmd")
    si = sub.add_parser("init", help="扫描 /input、建索引、落 partial result.json（默认）")
    si.add_argument("--no-probe", dest="no_probe", action="store_true",
                    help="跳过空输入/坏输入子进程探针（更快，self_check 会标注未探测）")
    sp = sub.add_parser("show", help="打印带 locator 的原文")
    sp.add_argument("--material", default=None, help="材料 id（M1）或文件名")
    sp.add_argument("--start", type=int, default=1, help="起始单元序号")
    sp.add_argument("--limit", type=int, default=12, help="单元数上限")
    sp.add_argument("--grep", default=None, help="只打印含关键词的单元")
    sp.add_argument("--max-chars", dest="max_chars", type=int, default=6000, help="字符预算")
    sc = sub.add_parser("check", help="校验证据/字段/覆盖")
    sc.add_argument("--work", default=None, help="工作稿路径（默认 /app/work/mindmap.json）")
    sb = sub.add_parser("build", help="渲染 SVG/PNG + content_map + result.json")
    sb.add_argument("--work", default=None, help="工作稿路径（默认 /app/work/mindmap.json）")
    sb.add_argument("--no-probe", dest="no_probe", action="store_true",
                    help="跳过空输入/坏输入子进程探针（更快，self_check 会标注未探测）")
    args = ap.parse_args(argv)
    return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build}[args.cmd or "init"](args)


if __name__ == "__main__":
    code = 0
    try:
        code = main(sys.argv[1:])
    except SystemExit:
        code = 0
    except Exception as exc:
        print("main.py 内部异常（已捕获，退出码 0）：%s" % exc)
        try:
            ensure(OUT)
            case, _ = find_case()
            case = case if isinstance(case, dict) else {}
            r = base_result(case.get("case_id"), "input_error")
            r["errors"] = [str(exc)]
            r["degradations"] = ["主流程异常：已写最小合法 result.json，退出码仍为 0"]
            asst = assets("crash", case, case_contract(case), {"materials": [], "case_id": r["case_id"]},
                          cid=r["case_id"], errors=r["errors"], degradations=r["degradations"], do_probe=False)
            _finalize_safe(r, case_contract(case),
                           {"case_id": r["case_id"], "files": [], "note": "运行时异常，已最小落盘"},
                           OUT / "result.json", closes(), extra_of(asst))
        except Exception:
            pass
        code = 0
    sys.exit(code if isinstance(code, int) else 0)
