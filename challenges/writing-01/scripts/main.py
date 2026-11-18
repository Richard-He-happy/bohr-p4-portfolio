#!/usr/bin/env python3
"""writing-01 v4: fail-safe academic writing skill (init|show|check|build). Stdlib only."""
import argparse, json, os, re, signal, sys, time, zipfile
from pathlib import Path


def _load_audit():
    """Optional audit layer (scripts/audit.py). Its absence must not break build."""
    try:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import audit
        return audit
    except Exception:
        return None


AU = _load_audit()


def _L(lv, ev, **kv):
    """Best-effort structured run-log line; never raises."""
    if AU is None:
        return
    try:
        AU.LOG.add(lv, ev, **kv)
    except Exception:
        pass

V = "5.0.0"
T0 = time.time()
MF, MT, MB, FT, DL = 200, 20 << 20, 2 << 20, 5.0, 45.0
BI = ("png jpg jpeg gif bmp tif tiff webp zip gz xlsx xls pptx ppt doc bin exe so pkl npy "
      "npz h5 db mp4 mp3 wav").split()
SE = [("ab", "摘要", ""), ("in", "1 引言", "背景 目的 研究 intro background aim"),
      ("me", "2 方法", "方法 材料 样本 实验 测量 统计 method materials participants"),
      ("re", "3 结果", "结果 发现 显著 降低 提高 result significant figure"),
      ("di", "4 讨论", "讨论 机制 解释 局限 discussion suggest limitation consistent"),
      ("co", "5 结论", "结论 综上 conclusion summary"),
      ("rf", "参考文献", "doi references journal"),
      ("da", "数据可得性声明", "availability 数据可得")]
AL = {"ab": "摘要 abstract", "in": "引言 intro 背景 目的 aim",
      "me": "方法 method 材料 样本 实验 测量 统计 分组 处理 participants",
      "re": "结果 result 发现 显著 finding",
      "di": "讨论 discussion 机制 解释 局限 limitation",
      "co": "结论 conclusion 总结 summary",
      "rf": "参考文献 refer references doi",
      "da": "数据可得 availab availability"}
CN = ("case_id", "deliverable", "preserved_facts", "evidence_map", "change_log")
SP = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+(?=[A-Z0-9\"“(\[])")
RF = re.compile(r"(?:10\.\d{4,9}/)|(?:doi:\s*10\.)|(?:^\[\d{1,3}\])|(?:^\d{1,3}\.\s[A-Z])")
AB = ("本稿依据 %d 份材料（可读 %d 份）组装，覆盖 %d 章、%d 条证据句；"
      "摘要锚定材料原句，可改写表述但不改事实。")
PH = "材料未覆盖本节，见附录。"


class TO(Exception):
    pass


def _a(*_):
    raise TO()


def sig(t):
    if hasattr(signal, "SIGALRM"):
        try:
            signal.signal(signal.SIGALRM, _a); signal.setitimer(signal.ITIMER_REAL, t)
        except Exception:
            pass


def cp(s, n):
    s = re.sub(r"\s+", " ", "" if s is None else str(s)).strip()
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def wj(p, o):
    try:
        p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1
    except Exception:
        try:
            Path(p).write_text('{"status":"input_error"}', encoding="utf-8")
        except Exception:
            pass
        return 0


def rd(p):
    ex = p.suffix.lower()
    if ex in (".docx", ".docm"):
        with zipfile.ZipFile(p) as z:
            if "word/document.xml" not in z.namelist():
                return "docx", "", "no_document_xml"
            x = z.read("word/document.xml")[:MB].decode("utf-8", "replace")
        return "docx", re.sub(r"<[^>]{0,4000}>", "", re.sub(r"</w:p>", "\n", x)), ""
    with open(p, "rb") as f:
        h = f.read(8)
        if ex == ".pdf" or h.startswith(b"%PDF"):
            return "pdf", "", "pdf_unparsed"
        if ex.lstrip(".") in BI or b"\x00" in h:
            return "binary", "", "binary_unparsed"
        b = h + f.read(MB + 1 - 8)
    t, bad = b[:MB].decode("utf-8-sig", "replace"), len(b) > MB
    note = "file_truncated" if bad else ""
    if ex in (".json", ".jsonl") or h.lstrip().startswith(b"{"):
        try:
            t = json.dumps(json.loads(t), ensure_ascii=False, indent=1); ex = ".json"
        except Exception:
            note = note or "json_parse_failed"
    return ("json" if ex == ".json" else "text"), t, note


def scan(inp, st):
    out, fs = [], []
    if not Path(inp).is_dir():
        st["errors"].append("input_dir_missing"); return out
    for r, ds, ns in os.walk(inp, followlinks=False):
        if len(ns) > 400:
            ns = ns[:400]; st["degradations"].append({"code": "dir_capped", "path": str(r)})
        fs += [Path(r) / n for n in sorted(ns)][:max(0, MF + 1 - len(fs))]
        if len(fs) > MF or time.time() - T0 > DL:
            break
    fs.sort(key=lambda x: str(x).lower()); tot = 0
    for p in fs:
        if len(out) >= MF:
            st["degradations"].append({"code": "file_capped", "path": str(inp)}); break
        if time.time() - T0 > DL:
            st["degradations"].append({"code": "deadline_scan", "path": str(inp)}); break
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if tot + min(sz, MB) > MT:
            st["degradations"].append({"code": "bytes_capped", "path": str(p)}); break
        tot += min(sz, MB)
        rel = str(p.relative_to(inp)).replace(os.sep, "/")
        if rel.lower() == "case.json":
            continue
        it = {"id": "M%02d" % (len(out) + 1), "path": rel, "bytes": sz, "kind": "unknown",
              "chars": 0, "readable": False, "text": "", "note": ""}
        sig(FT)
        try:
            k, t, note = rd(p)
            it.update(kind=k, text=t, chars=len(t), readable=bool(t.strip()), note=note)
            if note:
                st["degradations"].append({"code": note, "path": rel})
            if k == "pdf":
                st["pending_human"].append({"item": rel, "reason": "PDF 未解析（跳过二进制）",
                                            "action": "提供文本材料或人工粘贴需引段落"})
            elif k == "binary":
                st["pending_human"].append({"item": rel, "reason": "二进制/图像未读取",
                                            "action": "提供文本等价材料"})
        except TO:
            it["note"] = "timeout"; st["degradations"].append({"code": "file_timeout", "path": rel})
        except Exception as e:
            it["note"] = "err:" + type(e).__name__
            st["degradations"].append({"code": "file_error", "path": rel, "detail": cp(e, 100)})
        finally:
            sig(0)
        out.append(it)
        _L("FILE", "scanned", id=it["id"], kind=it["kind"], bytes=it["bytes"],
           chars=it["chars"], readable=it["readable"], note=it["note"] or "-", path=it["path"])
    return out


def lcase(inp, st):
    if not Path(inp).is_dir():
        st["errors"].append("case_json_missing"); return {}
    cands = [Path(inp) / "case.json"]
    try:
        cands += [c for c in sorted(Path(inp).rglob("case*.json")) if c not in cands][:3]
    except Exception:
        pass
    for c in cands:
        try:
            o = json.loads(c.read_bytes()[:4 << 20].decode("utf-8-sig", "replace"))
            if isinstance(o, dict):
                st["case_path"] = str(c); return o
        except Exception as e:
            st["errors"].append("case_json_unreadable:" + cp(e, 80))
    st["errors"].append("case_json_missing"); return {}


def title(c, ms):
    s = c.get("source") if isinstance(c.get("source"), dict) else {}
    for v in (s.get("title"), c.get("title")):
        if isinstance(v, str) and v.strip():
            return cp(v, 160)
    for m in ms:
        for ln in (m.get("text") or "").splitlines():
            if ln.strip().startswith("# "):
                return cp(ln.strip()[2:], 160)
    return "学术论文写作产物（标题待定）"


def sents(ms, cap=6000):
    o = []
    for m in ms:
        t = m.get("text") or ""
        if not (m.get("readable") and t):
            continue
        hd = ""
        for i, ln in enumerate(t.splitlines(), 1):
            s = ln.strip()
            if not s:
                continue
            if s.startswith("#") and len(s) < 120:
                hd = s.lstrip("#").strip(); continue
            if RF.search(s):
                # 参考文献条目整体保留：拆句会拆断作者/卷期/DOI，导致引用无法逐字核验
                if len(s) >= 24:
                    o.append({"quote": cp(s, 480), "source_id": m["id"], "heading": hd,
                              "locator": "%s:L%d" % (m["path"], i)})
                if len(o) >= cap:
                    return o
                continue
            for q in SP.split(s):
                q = q.strip(" -*\t")
                if len(q) >= 24:
                    o.append({"quote": cp(q, 480), "source_id": m["id"], "heading": hd,
                              "locator": "%s:L%d" % (m["path"], i)})
                if len(o) >= cap:
                    return o
    return o


def hs(ms):
    return [(m["id"], re.sub(r"\s+", "", m["text"])) for m in ms
            if m.get("readable") and m.get("text")]


def vq(q, H, sid=None):
    n = re.sub(r"\s+", "", q or "")
    for i, h in sorted(H, key=lambda x: 0 if (sid and x[0] == sid) else 1):
        if len(n) >= 8 and n in h:
            return 1, i
    return 0, None


def ah(h, k):
    h = (h or "").lower()
    return any(a in h for a in AL.get(k, "").split())


def fb(ss, lim=4):
    u, o = set(), []
    for k, h, kw in SE:
        it = []
        for i, s in enumerate(ss):
            if i not in u and any(a in (s.get("heading") or "").lower()
                                  for a in AL.get(k, "").split()):
                it.append(ss[i]); u.add(i)
            if len(it) >= lim:
                break
        w = kw.split()
        for neg, i in sorted((-sum(x in s["quote"].lower() for x in w), i)
                             for i, s in enumerate(ss) if i not in u and w):
            if neg >= 0 or len(it) >= lim:
                break
            it.append(ss[i]); u.add(i)
        o.append({"key": k, "heading": h, "items": it, "auto": True, "paras": []})
    return o


def isec(d):
    o = []
    for s in (d.get("sections") if isinstance(d, dict) else None) or []:
        if isinstance(s, str):
            o.append({"heading": "", "paragraphs": [{"text": s, "quotes": []}]}); continue
        if not isinstance(s, dict):
            continue
        ps = s.get("paragraphs") or []
        ps = [ps] if isinstance(ps, str) else (ps if isinstance(ps, list) else [])
        n = []
        for p in ps:
            if isinstance(p, str):
                n.append({"text": p, "quotes": []})
            elif isinstance(p, dict):
                qs = p.get("quotes") or []
                n.append({"text": str(p.get("text") or ""), "quotes": [
                    x if isinstance(x, dict) else {"quote": str(x)}
                    for x in (qs if isinstance(qs, list) else [qs])]})
        o.append({"heading": str(s.get("heading") or s.get("title") or ""), "paragraphs": n})
    return o


def ldraft(p):
    try:
        p = Path(p)
        if p.is_file() and p.stat().st_size <= 8 << 20:
            o = json.loads(p.read_bytes().decode("utf-8-sig", "replace"))
            return o if isinstance(o, dict) else None
    except Exception:
        return None
    return None


def assemble(secs, sen, H):
    bl, ch, IT, RJ = [], [], [], []
    for s in secs:
        it = []
        for p in s["paragraphs"]:
            for x in p.get("quotes") or []:
                ok, mid = vq(x.get("quote"), H, x.get("source_id"))
                if ok:
                    it.append({"quote": cp(x.get("quote"), 480), "source_id": mid,
                               "locator": x.get("locator") or ""})
                else:
                    RJ.append({"quote": cp(x.get("quote"), 140),
                               "locator": x.get("locator") or ""})
        IT.append(it)
        hd = s["heading"] or "(未命名章节)"
        bl.append({"key": None, "heading": hd, "items": it, "auto": False,
                   "paras": [p["text"] for p in s["paragraphs"] if p["text"].strip()]})
        ch.append({"action": "use_agent_draft", "section": cp(hd, 80), "verified": len(it)})
    for b in fb(sen):
        if not any(ah(x["heading"], b["key"]) for x in bl):
            bl.append(b)
            ch.append({"action": "assemble_from_source", "section": b["heading"],
                       "evidence": len(b["items"])})
    return bl, ch, IT, RJ


def render(t, bl, fa, st, status, du, nm, nr):
    nq = sum(len(b["items"]) for b in bl)
    L = ["# " + t, "", "> writing-01 v%s｜status: %s｜materials %d (readable %d)｜evidence %d"
         % (V, status, nm, nr, nq), ""]
    if not du:
        L += ["> 未收到 Agent 草稿：各节按材料可定位语句组装，`文件:行号` 为来源定位。", ""]
    for b in bl:
        L += ["## " + b["heading"], ""]
        if b["key"] == "ab":
            L += [AB % (nm, nr, len(bl), nq), ""]
        for p in b.get("paras") or []:
            L += [cp(p, 4000), ""]
        for i in b["items"]:
            L += ["> " + i["quote"], ">", "> — `%s`" % i["locator"], ""]
        if b["auto"] and not b["items"] and b["key"] != "ab":
            L += [PH, ""]
    L += ["## 附录 缺口与待确认", ""]
    gaps = [b["heading"] for b in bl if not b["items"]]
    it = (["缺口章节：%s" % ", ".join(cp(g, 40) for g in gaps)] if gaps else [])
    it += ["待确认：%s｜%s" % (cp(p.get("item"), 60), cp(p.get("reason"), 90))
           for p in (st.get("pending_human") or [])[:12]]
    it += ["引用拒收：%s（%s）" % (cp(r.get("quote"), 100), r.get("locator") or "无定位")
           for r in (st.get("rejected") or [])[:8]]
    dg = st.get("degradations") or []
    if dg:
        it.append("降级 %d 项：%s" % (len(dg), "; ".join(sorted({str(d.get("code")) for d in dg}))))
    L += ["- " + x for x in (it or ["无待确认项。"])] + [""]
    st["stats"] = {"materials": nm, "readable": nr, "evidence_sentences": st.get("n_sents", 0),
                   "facts": len(fa), "quotes_verified": nq,
                   "quotes_rejected": len(st.get("rejected") or []),
                   "h2_headings": sum(1 for x in L if x.startswith("## ")),
                   "chars": sum(len(x) for x in L)}
    return "\n".join(L).strip() + "\n"




def mres(ctx, ms, stats, status, ml, ex):
    st = ctx.get("state") or {}; ct = st.get("contract")
    pl = {"case_id": st.get("case_id", ""), "deliverable": ml,
          "preserved_facts": ex.get("preserved_facts") or [],
          "evidence_map": st.get("evidence_map") or ex.get("evidence_map") or [],
          "change_log": st.get("change_log") or ex.get("change_log") or []}
    r = {}
    if isinstance(ct, dict):
        for k in ct:
            r[k] = pl.get(re.sub(r"[\s\-]+", "_", str(k).strip().lower()))
    elif isinstance(ct, list):
        r["output_contract_fields"] = [pl.get(re.sub(r"[\s\-]+", "_", k.strip().lower()))
                                      if isinstance(k, str) else None for k in ct]
        for k in ct:
            if isinstance(k, str) and re.sub(r"[\s\-]+", "_", k.strip().lower()) in pl:
                r[k] = pl.get(re.sub(r"[\s\-]+", "_", k.strip().lower()))
    for k in CN:
        r.setdefault(k, pl.get(k))
    unc = ["材料锚定初稿（摘录组装），论证与措辞需作者补全；locator 为 `文件:L行号`。",
           "材料外数值/文献/图注未生成；缺口见 pending_human。"]
    if not ex.get("draft_used"):
        unc.append("未提供 Agent 草稿 draft.json，章节由 build 兜底组装。")
    if any(d.get("code") == "pdf_unparsed" for d in (st.get("degradations") or [])):
        unc.append("PDF 未解析，PDF 内数字可能缺失。")
    r.update({"status": status,
              "sources": [{"id": m.get("id"), "path": m.get("path"), "kind": m.get("kind"),
                           "bytes": m.get("bytes"), "chars": m.get("chars"),
                           "readable": m.get("readable"), "note": m.get("note")}
                          for m in (ms or [])],
              "uncertainty": unc, "pending_human": st.get("pending_human") or [],
              "errors": st.get("errors") or [], "degradations": st.get("degradations") or [],
              "changes": pl["change_log"], "coverage": stats,
              "runtime": {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T0)),
                          "elapsed_s": round(time.time() - T0, 2),
                          "python": sys.version.split()[0], "version": V,
                          "input_root": str(ctx.get("inp")),
                          "output_root": str(ctx.get("out"))}})
    return r


def prep(a):
    inp = Path(a.input or os.environ.get("SKILL_INPUT") or "/input").expanduser()
    if not inp.is_dir() and (Path.cwd() / "input").is_dir():
        inp = Path.cwd() / "input"
    out = Path(a.output or os.environ.get("SKILL_OUTPUT") or "/app/output").expanduser()
    wk = Path(a.work or os.environ.get("SKILL_WORK") or "/app/work").expanduser()
    st = {"errors": [], "degradations": [], "pending_human": [], "rejected": [], "contract": {},
          "case_id": "", "instruction": "", "exceptions": []}
    ctx = {"inp": inp, "out": out, "work": wk, "state": st}
    _L("START", "run", version=V, input=str(inp), output=str(out), work=str(wk))
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        st["degradations"].append({"code": "output_dir_fallback", "path": str(out)})
        ctx["out"] = out = wk
    try:
        wk.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    c = lcase(inp, st)
    st["contract"] = c.get("output_contract")
    st["case_id"] = str(c.get("case_id") or c.get("id") or "")
    vs = [v if isinstance(v, str) else (json.dumps(v, ensure_ascii=False) if
          isinstance(v, (dict, list)) else "") for v in (
          c.get("task_instruction"), c.get("organizer_workorder"),
          c.get("organizer_edit_workorder"), c.get("requirements"))]
    st["instruction"] = cp(" | ".join(x for x in vs if x.strip()), 900)
    st["case"] = c
    _L("STEP", "case_loaded", path=st.get("case_path", "-"), case_id=st.get("case_id", ""),
       contract_keys=(len(st["contract"]) if isinstance(st["contract"], (dict, list)) else 0),
       errors=len(st["errors"]))
    return ctx


def c_init(ctx):
    st = ctx["state"]; ms = scan(ctx["inp"], st); ss = sents(ms); st["n_sents"] = len(ss)
    print("init | case=%s case_id=%s" % (st.get("case_path", "-"), st.get("case_id", "-")))
    print("materials=%d readable=%d sentences=%d degradations=%d pending=%d"
          % (len(ms), sum(1 for m in ms if m["readable"]), len(ss),
             len(st["degradations"]), len(st["pending_human"])))
    for m in ms:
        print("%s %-6s %8dB %7dch %-4s %s" % (m["id"], m["kind"], m["bytes"], m["chars"],
                                              "READ" if m["readable"] else "SKIP", m["path"]))


def c_show(ctx, lim):
    ss = sents(scan(ctx["inp"], ctx["state"]))
    for s in ss[:lim]:
        print("[%s] %s" % (s["source_id"], s["locator"]))
        print("    " + cp(s["quote"], 300))
    print("-- shown %d/%d" % (min(lim, len(ss)), len(ss)))


def c_check(ctx, a):
    H = hs(scan(ctx["inp"], ctx["state"]))
    dp = Path(a.draft) if a.draft else Path(ctx["work"]) / "draft.json"
    d = ldraft(dp); secs = isec(d) if d else []
    bl, ch, IT, RJ = assemble(secs, [], H); hd = [s["heading"] for s in secs]
    n_it = sum(len(i) for i in IT)
    r = {"draft_found": bool(secs), "sections": len(secs),
         "paragraphs": sum(len(s["paragraphs"]) for s in secs),
         "quotes_total": n_it + len(RJ), "quotes_verified": n_it, "quotes_rejected": len(RJ),
         "rejected": RJ, "draft_path": str(dp), "materials_readable": len(H),
         "missing_required_sections": [h for k, h, _ in SE if not any(ah(x, k) for x in hd)],
         "ok": not RJ and bool(secs)}
    if not d:
        r["note"] = "no draft; build will assemble from materials (partial)"
    wj(Path(ctx["work"]) / "check.json", r)
    print(json.dumps(r, ensure_ascii=False, indent=1))


def c_build(ctx, a):
    st, out = ctx["state"], Path(ctx["out"])
    wj(out / "result.json", mres(ctx, [], {}, "partial", None, {}))
    _L("STEP", "partial_result_written", path=str(out / "result.json"))
    ms = scan(ctx["inp"], st); ss = sents(ms); st["n_sents"] = len(ss)
    _L("STEP", "scan_done", materials=len(ms),
       readable=sum(1 for m in ms if m.get("readable")), sentences=len(ss),
       degradations=len(st["degradations"]), pending=len(st["pending_human"]))
    fa = [{"fact_id": "F%02d" % i, "value_text": cp(s["quote"], 240),
           "source_id": s["source_id"], "locator": s["locator"]}
          for i, s in enumerate([x for x in ss if re.search(r"\d", x["quote"])], 1)][:30]
    H = hs(ms)
    d = ldraft(Path(a.draft) if a.draft else Path(ctx["work"]) / "draft.json")
    secs = isec(d) if d else []
    bl, ch, IT, RJ = assemble(secs, ss, H)
    for r in RJ:
        st["pending_human"].append({"item": r["locator"] or "draft quote",
                                    "reason": "引用句未在材料逐字命中",
                                    "action": "改为逐字引用或删除该引用"})
    st["rejected"] += RJ
    ev = [{"claim_id": "C%03d" % (i + 1), "section": cp(h, 80), "quote": x["quote"],
           "source_id": x.get("source_id") or "", "locator": x["locator"], "verified": True}
          for i, (h, x) in enumerate([(b["heading"], y) for b in bl for y in b["items"]])][:150]
    status = ("input_error" if (not ms and not Path(ctx["inp"]).is_dir()) else
              "insufficient_evidence" if (not secs and not ev) else
              "ok" if (secs and not RJ and len(ev) >= 5) else "partial")
    md = render(title(st.get("case") or {}, ms), bl, fa, st, status, bool(secs), len(ms),
                sum(1 for m in ms if m.get("readable")))
    (out / "manuscript.md").write_text(md, encoding="utf-8")
    _L("STEP", "manuscript_written", chars=len(md), sections=len(bl), evidence=len(ev),
       status=status)
    # ---- v2 audit assets: golden standard / diff / version history / run.log / self-check
    ast = {}
    if AU is None:
        st["degradations"].append({"code": "audit_module_missing",
                                   "path": "scripts/audit.py"})
    elif not getattr(a, "no_audit", False):
        try:
            ast = AU.assets(ctx, blocks=bl, ms=ms, md=md, facts=fa, evidence=ev, changes=ch,
                            status=status, al=AL, script=Path(__file__).resolve(),
                            out=out, work=Path(ctx["work"]))
        except BaseException as e:
            st["degradations"].append({"code": "audit_failed", "path": "audit",
                                       "detail": cp(e, 120)})
            st["exceptions"].append("audit_failed:%s" % type(e).__name__)
            _L("EXC", "audit_failed", err=type(e).__name__, detail=cp(e, 160))
    ch = ch[:59] + [{"action": "finalize", "status": status, "deliverable": "manuscript.md",
                     "sections": len(bl), "evidence": len(ev)}]
    st["change_log"], st["evidence_map"] = ch, ev
    r = mres(ctx, ms, st.get("stats") or {}, status, "manuscript.md",
             {"preserved_facts": fa, "evidence_map": ev, "change_log": ch,
              "draft_used": bool(secs)})
    r.update(ast)
    for k in ("golden_standard", "diff_report", "version_history"):
        if k not in r:
            r[k] = {"unavailable": True,
                    "reason": "audit skipped (--no-audit) or scripts/audit.py unavailable"}
    r["self_check"] = {"unavailable": True, "reason": "pending self-check"}
    r["exceptions"] = st.get("exceptions") or []
    wj(out / "result.json", r)
    if AU is not None and ast:
        try:
            r["self_check"] = AU.finalize_selfcheck(
                ctx, r, ast.get("golden_standard") or {}, md, ms, out,
                Path(ctx["work"]), Path(__file__).resolve(), status,
                (ast.get("diff_report") or {}).get("summary") or {},
                items=(ast.get("diff_report") or {}).get("items") or [])
        except BaseException as e:
            st["exceptions"].append("selfcheck_failed:%s" % type(e).__name__)
            r["exceptions"] = st["exceptions"]
        try:
            r["runtime"]["elapsed_s"] = round(time.time() - T0, 2)
        except Exception:
            pass
        wj(out / "result.json", r)
    _L("END", "finalized", status=status, sections=len(bl), evidence=len(ev),
       pending=len(st.get("pending_human") or []), elapsed="%.2f" % (time.time() - T0),
       exit=0)
    if AU is not None:
        try:
            AU.LOG.flush(out)
        except Exception:
            pass
    print("built %s | status=%s sections=%d evidence=%d h2=%d chars=%d"
          % (out / "manuscript.md", status, len(bl), len(ev),
             (st.get("stats") or {}).get("h2_headings", 0), len(md)))


def c_audit(ctx, a):
    """Recompute diff_report.md from the existing output (read-only for the manuscript)."""
    out = Path(ctx["out"])
    if AU is None:
        print("audit | scripts/audit.py unavailable; manuscript untouched")
        return
    try:
        r = AU.recheck(out, ctx["work"])
        s = r["summary"]
        print("audit | met=%d deviated=%d missing=%d total=%d verdict=%s"
              % (s["met"], s["deviated"], s["missing"], s["total"], s["verdict"]))
        for x in [y for y in r["items"] if y["status"] != "达标"][:10]:
            print("  %s %s %s | %s" % (x["item_id"], x["status"],
                                       cp(x["target"], 40), cp(x["observed"], 80)))
    except Exception as e:
        print("audit failed: %s (manuscript untouched, exit 0)" % type(e).__name__)
        _L("EXC", "audit_recheck_failed", err=type(e).__name__)



def parser():
    ap = argparse.ArgumentParser(prog="main.py", description="writing-01 v%s" % V)
    ap.add_argument("cmd", nargs="?", default="build",
                    choices=["init", "show", "check", "build", "audit"])
    ap.add_argument("--input", default=None, help="input dir (default /input)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output)")
    ap.add_argument("--work", default=None, help="work dir (default /app/work)")
    ap.add_argument("--draft", default=None, help="draft json (default <work>/draft.json)")
    ap.add_argument("--no-audit", dest="no_audit", action="store_true",
                    help="skip golden_standard/diff_report/version_history/self_check assets")
    return ap


def emergency(ctx, e):
    st = ctx.get("state") or {}
    st.setdefault("errors", []).append("fatal:%s" % type(e).__name__)
    for k in ("degradations", "pending_human", "rejected", "exceptions"):
        st.setdefault(k, [])
    st["exceptions"].append("fatal:%s" % type(e).__name__)
    st.setdefault("contract", {})
    _L("EXC", "fatal", err=type(e).__name__, detail=cp(e, 200))
    out = Path(ctx.get("out") or "/app/output")
    try:
        r = mres(ctx, [], {}, "input_error", None, {})
        for k in ("golden_standard", "diff_report", "version_history"):
            r[k] = {"unavailable": True, "reason": "fatal:%s" % type(e).__name__}
        r["self_check"] = {"unavailable": True, "reason": "fatal:%s" % type(e).__name__}
        r["exceptions"] = st["exceptions"]
        wj(out / "result.json", r)
    except Exception:
        wj(out / "result.json", mres(ctx, [], {}, "input_error", None, {}))
    try:
        (out / "manuscript.md").write_text(
            "# 学术论文写作产物\n\n## 摘要\n\n运行异常降级：%s（见 result.json）。\n\n"
            "## 参考文献\n\n材料未提供。" % type(e).__name__, encoding="utf-8")
    except Exception:
        pass
    _L("END", "emergency_finalized", status="input_error", exit=0)
    if AU is not None:
        try:
            AU.LOG.flush(out)
        except Exception:
            pass


def main(argv=None):
    try:
        a = parser().parse_args(argv)
    except SystemExit:
        return 0
    ctx = None
    try:
        ctx = prep(a)
        [lambda: c_init(ctx), lambda: c_show(ctx, 25), lambda: c_check(ctx, a),
         lambda: c_build(ctx, a), lambda: c_audit(ctx, a)][
            ["init", "show", "check", "build", "audit"].index(a.cmd)]()
    except SystemExit:
        return 0
    except BaseException as e:
        try:
            if ctx:
                emergency(ctx, e)
        except Exception:
            pass
        sys.stderr.write("recovered from %s (exit 0)\n" % type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
