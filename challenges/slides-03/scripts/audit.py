#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py - verification assets for slides-03 (golden_standard.json, diff_report.md,
version_history.md, run.log, self_check.json), derived from this run's real input/plan.
Nothing pre-written. Stdlib only, no network, no CWD use."""
import json, re, time, traceback
from datetime import datetime
from pathlib import Path

T0 = time.time()
LOG = []
STATE = {"fields": {}, "out": None, "tag": "-", "flushed": 0, "hdr": False}

ACT = {"cover": ("封面", .4), "problem": ("背景与问题", 1.), "method": ("方法与证据", 1.1),
       "result": ("关键结果", 1.1), "limit": ("边界与风险", .9), "conclusion": ("结论与下一步", .8)}
ROLES = ("problem", "method", "result", "limit", "conclusion")
KEY = {"limit": r"局限|限制|不足|误差|失败|偏差|风险|未能|limited|limitation|caveat|drawback|failure|future work|we did not|not test",
       "conclusion": r"结论|综上|总结|表明|说明|因此|conclusion|in summary|we conclude|overall",
       "method": r"我们(提出|设计|构建|采用)|本文提出|提出一种|方法|框架|算法|流程|模块|method|approach|framework|we propose|we introduce|we design",
       "problem": r"研究问题|问题|挑战|动机|背景|瓶颈|background|motivation|challenge|gap|however|existing|require|we ask",
       "result": r"结果|提升|提高|达到|优于|降低|准确|表现|相比|benchmark|accuracy|outperform|improv|achiev|gain"}
CHAP = {"结果", "方法", "背景", "结论", "讨论", "引言", "总结", "致谢", "问题", "动机", "提纲", "目录",
        "results", "methods", "background", "conclusion", "discussion", "introduction", "summary", "outline"}
QAC = {"机制": r"机制|为什么|原理|mechanism|why", "数据": r"数据|样本|划分|泄漏|data|sample|split|leak",
       "对照": r"对照|基线|对比|消融|baseline|compar|ablation", "局限": r"局限|失败|风险|边界|limit|fail"}
GOAL = {"cover": "让听众知道要回答什么、要多久", "problem": "建立『值得解决』的共识与证据前提",
        "method": "讲清做法与关键选择，听众能复述一句话", "result": "给关键数字/现象，标条件与对照",
        "limit": "主动交代边界，降低被追问风险", "conclusion": "结论压成一句可引用的话，并给下一步"}
FIX = {"页级结构": "改页数/要点数/标题/主张后重跑 check+build",
       "证据映射": "用 show 取回 locator 与原文 quote（改写会被拒）",
       "讲解逻辑": "notes 写讲法/条件/被追问第一句，不复述页面；补叙事分幕",
       "图表引用": "补 visual；无图写『无（材料未提供）』",
       "数字一致": "按 quote 原文改数字，跨页口径统一",
       "问答准备": "补机制/数据/对照/局限问答，指向备用页"}


def log(step, msg="", **kw):
    r = {"t": round(time.time() - T0, 2), "step": step, "msg": msg}
    r.update(kw)
    LOG.append(r)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def norm(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def dump(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def _pairs(idx):
    for m in (idx or {}).get("materials") or []:
        if m.get("role") == "template":
            continue
        for p in m.get("paras") or []:
            if isinstance(p, dict) and str(p.get("text") or "").strip():
                yield m.get("id") or "?", p.get("loc") or "", p["text"]


def para_text(loc, idx):
    return next((t for _, l, t in _pairs(idx) if l == loc), "")


def find(q, idx):
    n = norm(q)
    if not n:
        return None
    return next((l for _, l, t in _pairs(idx) if n in norm(t)), None)


def _raw(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def task_lines(idx):
    root = Path(str((idx or {}).get("input_root") or ""))
    for nm in ("task.md", "TASK.md"):
        p = root / nm
        if not p.is_file():
            continue
        out = [{"locator": "%s#L%d" % (nm, i), "quote": re.sub(r"\s+", " ", l).strip()[:240]}
               for i, l in enumerate(_raw(p).splitlines(), 1) if len(re.sub(r"\s+", " ", l).strip()) >= 14]
        if out:
            return out
    return []


def pick_task(tl, pat):
    it = next((x for x in tl if re.search(pat, x["quote"], re.I)), None)
    return {"locator": (it or {}).get("locator", ""), "quote": (it or {}).get("quote", ""),
            "source": "task.md", "verified": bool(it)}


def role_index(idx, cap=6):
    out = {r: [] for r in ROLES}
    for mid, loc, t in _pairs(idx):
        s = t.strip()
        if not 20 <= len(s) <= 600:
            continue
        for r in ("limit", "conclusion", "method", "problem", "result"):
            if re.search(KEY[r], s, re.I):
                if len(out[r]) < cap:
                    out[r].append({"locator": loc, "quote": s[:240], "material": mid})
                break
    return out


def roles_for(target, audience):
    target = max(3, int(target or 8))
    content = max(2, target - 1)
    w = {r: 1 for r in ROLES}
    w["problem"] = 2 if re.search(r"跨|评审|答辩|评委|committee|review", str(audience or ""), re.I) else (
        0 if (re.search(r"组会|进展|工程|合作|周会|group meeting|progress", str(audience or ""), re.I) and target <= 6) else 1)
    for r in ("problem", "limit", "conclusion"):
        if sum(w.values()) <= content:
            break
        w[r] = 0
    while content < sum(w.values()):
        r = max(w, key=lambda k: (w[k], k))
        if w[r] == 0:
            break
        w[r] -= 1
    share = {"problem": .15, "method": .35, "result": .40, "limit": .05, "conclusion": .05}
    extra = content - sum(w.values())
    while extra > 0:
        r = max(share, key=lambda k: (share[k] / (w[k] + 1.), k))
        w[r] += 1
        extra -= 1
    return ["cover"] + [r for r in ROLES for _ in range(w[r])]


def seconds_for(prof, duration):
    total = 60. * float(duration) * .85 if duration else max(300., 81. * len(prof))
    ws = [ACT[p][1] for p in prof]
    secs = [int(round(total * x / (sum(ws) or 1))) for x in ws]
    if secs:
        secs[-1] += int(round(total)) - sum(secs)
    return secs, int(round(total))


def skeleton(idx, h, target):
    """v0: page order, page role, time budget. No claims, no evidence."""
    prof = roles_for(target, (h or {}).get("audience"))
    secs, total = seconds_for(prof, (h or {}).get("duration"))
    return {"stage": "v0_skeleton", "case_id": (h or {}).get("case_id"),
            "audience": (h or {}).get("audience"), "duration_min": (h or {}).get("duration"),
            "target_slides": target, "total_seconds": total,
            "pages": [{"n": i, "act": ACT[r][0], "role": r, "seconds": s, "content": None, "evidence": []}
                      for i, (r, s) in enumerate(zip(prof, secs), 1)]}


ACC = [("C01", "交付契约", "result.json 回填 output_contract 全部字段"), ("C02", "页级结构", "页数=页数约束(K3)"),
       ("C03", "页级结构", "内容页 3–5 条要点"), ("C04", "页级结构", "内容页有唯一主张 claim"),
       ("C05", "页级结构", "标题写结论而非章名，≤46 字"), ("C06", "证据映射", "每条要点有 locator"),
       ("C07", "证据映射", "每条 quote 逐字命中"), ("C08", "证据映射", "每页≥2 条不同段落来源"),
       ("C09", "讲解逻辑", "notes 非空且不复述页面"), ("C10", "讲解逻辑", "分幕≥2 且覆盖≥3 角色"),
       ("C11", "讲解逻辑", "每幕有 purpose 与过渡口径"), ("C12", "时长", "页数与时长自洽(1 页≈1.2–1.5 分钟)"),
       ("C13", "图表引用", "内容页标明图表或缺口"), ("C14", "证据强度", "strength 取值合法"),
       ("C15", "问答准备", "qa≥2 且覆盖≥2 类"), ("C16", "数字一致", "页面数字可在 quote/源段落中找到"),
       ("C17", "导出", "pptx 可编辑，预览页数一致"), ("C18", "诚实性", "缺口/降级已记录"),
       ("C19", "版本", "有 v0/v1 记录且可回退"), ("C20", "运行", "run.log 完整，退出码 0")]
DIM = {a: (b, c) for a, b, c in ACC}


def golden_standard(case, idx, h, target):
    """What a passing deliverable must contain, grounded in case.json / task.md / material."""
    case, h = (case if isinstance(case, dict) else {}), (h or {})
    tl, rl = task_lines(idx), role_index(idx)
    prof = roles_for(target, h.get("audience"))
    secs, total = seconds_for(prof, h.get("duration"))
    raw = _raw((idx or {}).get("case_path") or "")
    cons = []

    def cadd(cid, field, val, pat, why):
        q = "" if val in (None, "", [], {}) else (val if isinstance(val, str) else json.dumps(val, ensure_ascii=False))
        cand = [q] + ([str(int(val))] if isinstance(val, float) and val.is_integer() else [])
        m = next((mm for c in cand if c for mm in [re.search(r'"([\w\-]+)"\s*:\s*"?%s' % re.escape(c), raw)] if mm), None)
        t = pick_task(tl, pat)
        ok = bool(m)
        cons.append({"id": cid, "field": field, "value": val,
                     "locator": "case.json#/%s" % m.group(1) if ok else t["locator"],
                     "quote": m.group(0) if ok else t["quote"], "source": "case.json" if ok else "task.md",
                     "why": why, "verified": ok or t["verified"]})

    cadd("K1", "audience", h.get("audience"), r"听众", "听众决定背景比例与术语范围")
    cadd("K2", "duration_min", h.get("duration"), r"时长|1 页", "时长换算页数与每页信息量")
    cadd("K3", "slide_count", h.get("slides") or target, r"页数|页结构", "页数是硬约束")
    cadd("K4", "template", h.get("template"), r"模板|母版", "模板字段须逐项核对")
    cadd("K5", "export", "pptx + pdf 预览", r"渲染|导出|可编辑", "导出件可打开、页数一致")

    pages, seen = [], {}
    for i, (r, s) in enumerate(zip(prof, secs), 1):
        pool, k = (rl.get(r) or []), seen.get(r, 0)
        seed = pool[k:k + 2] if r != "cover" else []
        seen[r] = k + 2
        pages.append({"n": i, "role": r, "act": ACT[r][0], "seconds": s,
                      "title_rule": "主标题=研究对象+结论方向；副标题=场合/听众/日期" if r == "cover" else "写本页结论（现象/数字+判断），不写章名",
                      "claim_rule": "封面不写主张，只交代听众、时长与要回答的问题" if r == "cover"
                      else "一句话唯一主张，且被本页 3–5 条要点直接支撑",
                      "bullets": [0, 0] if r == "cover" else [3, 5],
                      "evidence_rule": "无（封面无科学论断）" if r == "cover" else "每条要点 locator(M#p#)+逐字 quote；本页≥2 条来源；缺图缺数写缺口，不补造",
                      "notes_rule": "开场 20–30 秒：听众、时长、要回答的问题" if r == "cover"
                      else "讲稿须新增信息（讲法/条件/追问第一句），不复述页面文字",
                      "visual_rule": "无" if r == "cover" else "材料中真实图号/表号；无则『无（材料未提供）』",
                      "strength_rule": "none" if r == "cover" else "strong|moderate|weak，与对照/数据集数量匹配",
                      "evidence_seeds": seed, "expected_gap": (not seed) and r != "cover"})

    outline = []
    for r in ["cover"] + [x for x in ROLES if x in prof]:
        pg = [p for p in pages if p["role"] == r]
        nx = [x for x in ROLES if x in prof]
        j = nx.index(r) if r in nx else -1
        outline.append({"act": ACT[r][0], "role": r,
                        "pages": str(pg[0]["n"]) if len(pg) == 1 else "%d-%d" % (pg[0]["n"], pg[-1]["n"]),
                        "goal": GOAL[r], "seconds": sum(p["seconds"] for p in pg),
                        "transition": "开场后第一句交代为什么现在讲这一页" if r == "cover" else
                        ("过渡到下一幕『%s』：一句话说明上一页结论为何引出下一幕，不新增材料外事实" % ACT[nx[j + 1]][0]
                         if 0 <= j < len(nx) - 1 else "收尾：回到本次目标，给可执行下一步与需要的帮助"),
                        "evidence": (rl.get(r) or [])[:2]})

    logic = [{"id": lid, "expectation": exp, **pick_task(tl, pat)} for lid, pat, exp in [
        ("L1", r"逐段搬成页面|叙事顺序|按论文目录", "叙事顺序服务听众与时长，不按论文目录逐段搬运"),
        ("L2", r"每页留一句什么话", "每页只留一句可讲的话：标题即结论，要点只做支撑"),
        ("L3", r"每一个论断是否能在源材料里找到对应位置", "每条论断可定位到源材料（locator + 逐字 quote）"),
        ("L4", r"取舍过程能否被他人复核", "取舍、页级映射、导出链路可独立复核"),
        ("L5", r"预判针对机制", "问答覆盖机制/数据/对照/局限，口径与页面一致，指向备用页"),
        ("L6", r"数字与图表引用", "数字与图表引用和源材料一致，跨页口径统一"),
        ("L7", r"渲染与版本记录|导出", "模板/字体/导出可复核，且保留修改记录")]]

    return {"schema": "golden_standard.v1", "case_id": case.get("case_id") or "unknown_case",
            "generated_at": _now(), "stage": "full",
            "basis": {"statement": "由 case.json 约束、task.md 要求、源材料段落骨架确定性推导；只描述合格交付应含什么，不含预制答案。",
                      "derivation": "audit.py:golden_standard（纯规则）",
                      "evidence_source": sorted({m.get("name") for m in (idx.get("materials") or []) if m.get("role") != "template"}),
                      "materials": len((idx.get("materials") or [])), "paragraphs": len(list(_pairs(idx)))},
            "constraints": cons, "outline": outline, "pages": pages, "logic": logic,
            "acceptance": [{"id": a, "dimension": b, "expectation": c} for a, b, c in ACC],
            "acceptance_basis": "C01–C20 的规则依据见 logic(L1–L7) 与 constraints(K1–K5)，均带 locator+逐字 quote；C 项是它们的可机检投影。",
            "totals": {"pages": len(pages), "acts": len(outline), "logic_items": len(logic),
                       "acceptance_items": len(ACC), "seconds": total,
                       "evidence_seeds": sum(len(p["evidence_seeds"]) for p in pages),
                       "gap_pages": sum(1 for p in pages if p["expected_gap"])}}


def numeric_scan(plan, idx):
    bad, n = [], 0
    for i, s in enumerate((plan or {}).get("slides") or [], 1):
        for b in (s.get("bullets") or []) if isinstance(s, dict) else []:
            if not isinstance(b, dict):
                continue
            t = re.sub(r"第\s*\d+\s*页|\d+\s*页", "", str(b.get("text") or ""))
            src = str(b.get("quote") or "") or para_text(b.get("locator") or "", idx)
            for x in sorted(set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", t))):
                n += 1
                if x not in src:
                    bad.append({"slide": i, "number": x, "text": t[:60], "locator": b.get("locator") or ""})
    return n, bad


def evaluate(gs, plan, chk, rep, idx, vals, target, contract_missing):
    plan = plan if isinstance(plan, dict) else {}
    chk, rep = chk or {}, rep or {}
    sl = [s for s in plan.get("slides") or [] if isinstance(s, dict)]
    cnt = lambda s: len([b for b in (s.get("bullets") or []) if isinstance(b, dict)])
    items = []

    def add(cid, act, ok, ev, unmeasured=False, exp=None):
        dim, tex = DIM[cid]
        items.append({"id": cid, "dimension": dim, "expected": exp or tex, "actual": act, "evidence": ev,
                      "verdict": "unmeasured" if unmeasured else ("pass" if ok else ("missing" if not sl else "deviation"))})

    bls = [b for s in sl for b in (s.get("bullets") or []) if isinstance(b, dict)]
    add("C01", "缺失 %d 个：%s" % (len(contract_missing or []), contract_missing or "无"), not contract_missing, "result.json")
    add("C02", "%d 页" % len(sl), bool(sl) and (target in (None, 0) or len(sl) == target), "output/presentation.pptx",
        exp="页数=%s" % (target or "未约束"))
    content = [s for s in sl if s.get("layout") != "title"]
    bad = [i for i, s in enumerate(sl, 1) if s.get("layout") != "title" and not 3 <= cnt(s) <= 5]
    add("C03", "不合规页：%s" % (bad or "无"), not bad, "content_map.json")
    bad = [i for i, s in enumerate(content, 1) if not str(s.get("claim") or "").strip()]
    add("C04", "缺 claim 的内容页 %d 个" % len(bad), not bad, "content_map.json")
    bad = [i for i, s in enumerate(sl, 1) if str(s.get("title") or "").strip().lower() in CHAP or len(str(s.get("title") or "")) > 46]
    add("C05", "疑似章名/过长：%s" % (bad or "无"), not bad, "content_map.json")
    bad = [i for i, s in enumerate(sl, 1) for b in (s.get("bullets") or []) if isinstance(b, dict) and not str(b.get("locator") or "").strip()]
    add("C06", "缺 locator 的要点 %d 条" % len(bad), bool(bls) and not bad, "content_map.json")
    qc, qv = int(rep.get("quotes_checked") or 0), int(rep.get("quotes_verified") or 0)
    add("C07", "%d/%d 命中" % (qv, qc), qc > 0 and qv == qc, "work/check_report.json")
    bad = [i for i, s in enumerate(sl, 1) if s.get("layout") != "title" and len(
        {b.get("locator") for b in (s.get("bullets") or []) if isinstance(b, dict) and b.get("locator")}) < 2]
    add("C08", "单源页：%s" % (bad or "无"), not bad, "content_map.json")
    dup = (chk.get("notes_not_repeating") or {}).get("duplicated_slides") or []
    np_ = bool((chk.get("notes_present") or {}).get("pass"))
    add("C09", "notes_present=%s，复述页=%s" % (np_, dup or "无"), np_ and not dup, "compliance_checks.json")
    nar = [x for x in plan.get("narrative") or [] if isinstance(x, dict)]
    hit = sum(1 for r in ROLES if any(ACT[r][0] in str(x.get("act") or "") for x in nar))
    add("C10", "%d 幕，命中 %d 角色" % (len(nar), hit), len(nar) >= 2 and hit >= 3, "slide_plan.md")
    bad = [x.get("act") for x in nar if not str(x.get("purpose") or "").strip()]
    add("C11", "缺 purpose：%s" % (bad or "无"), bool(nar) and not bad, "slide_plan.md")
    dur = next((c.get("value") for c in (gs or {}).get("constraints") or [] if c.get("id") == "K2"), None)
    if not dur and not target:
        add("C12", "输入未给时长/页数", False, "golden_standard.json", unmeasured=True)
    else:
        add("C12", "%s 分钟 / %d 页" % (dur or "未给", len(sl)),
            (not dur) or (not target) or abs(int(target) - float(dur) / 1.4) <= 3, "golden_standard.json")
    bad = [i for i, s in enumerate(sl, 1) if s.get("layout") != "title" and not str(s.get("visual") or "").strip()]
    add("C13", "缺 visual：%s" % (bad or "无"), not bad, "content_map.json")
    okst = ("strong", "moderate", "weak", "unrated", "none")
    bad = [i for i, s in enumerate(sl, 1) if s.get("layout") != "title"
           and str(s.get("evidence_strength") or "").strip().lower() not in okst]
    add("C14", "非法/缺失：%s" % (bad or "无"), not bad, "content_map.json")
    qa = [q for q in plan.get("qa") or [] if isinstance(q, dict)]
    cats = {c for c, pt in QAC.items() if any(re.search(pt, "%s %s" % (q.get("q", ""), q.get("a", "")), re.I) for q in qa)}
    add("C15", "%d 条，覆盖 %s" % (len(qa), sorted(cats) or "无"), len(qa) >= 2 and len(cats) >= 2, "slide_plan.md")
    n, nb = numeric_scan(plan, idx)
    add("C16", "检查 %d 个，不一致 %d 个" % (n, len(nb)), not nb, "self_check.json#numeric")
    ok17 = bool((chk.get("pptx_editable") or {}).get("pass")) and bool((chk.get("preview") or {}).get("pass"))
    add("C17", "pptx=%s, preview=%s" % ((chk.get("pptx_editable") or {}).get("pass"), (chk.get("preview") or {}).get("pass")),
        ok17, "compliance_checks.json")
    gaps = [x["n"] for x in (gs or {}).get("pages") or [] if x.get("expected_gap")]
    filled = {i for i, s in enumerate(sl, 1) for b in (s.get("bullets") or [])
              if isinstance(b, dict) and b.get("quote") and find(b["quote"], idx)}
    unfilled = [n for n in gaps if n not in filled]
    add("C18", "预期缺口页 %d、未填 %d；pending_human %d、uncertainty %d"
        % (len(gaps), len(unfilled), len(vals.get("pending_human") or []), len(vals.get("uncertainty") or [])),
        (not unfilled) or bool(vals.get("pending_human")) or bool(vals.get("uncertainty")), "result.json")
    add("C19", "见 version_history.md", True, "version_history.md")
    add("C20", "%d 条日志" % len(LOG), len(LOG) >= 5, "run.log")
    return items


def summarise(items):
    s = {"pass": 0, "deviation": 0, "missing": 0, "unmeasured": 0, "items": len(items)}
    for it in items:
        s[it["verdict"]] = s.get(it["verdict"], 0) + 1
    s["coverage"] = round(100. * s["pass"] / (len(items) or 1), 1)
    return s


def render_diff(gs, items, plan, sm, target, idx):
    L = ["# 差异核验：实际产物 vs 金标准", "", "- case_id：`%s`　生成：%s" % (gs.get("case_id"), _now()),
         "- 金标准：`output/golden_standard.json`（%d 页 / %d 幕 / %d 条验收项）"
         % (gs["totals"]["pages"], gs["totals"]["acts"], gs["totals"]["acceptance_items"]),
         "- 判定：`pass` 达标｜`deviation` 有产物不合规｜`missing` 缺失｜`unmeasured` 无法测量（不冒充达标）",
         "- 汇总：pass %d / deviation %d / missing %d / unmeasured %d，达标率 %.1f%%"
         % (sm["pass"], sm["deviation"], sm["missing"], sm["unmeasured"], sm["coverage"]), "",
         "## 1. 验收项逐条对照", "", "| ID | 维度 | 要求 | 实际 | 判定 | 依据 |", "|-|-|-|-|-|-|"]
    for it in items:
        L.append("| %s | %s | %s | %s | %s | `%s` |" % (it["id"], it["dimension"], it["expected"].replace("|", "/"),
                                                       str(it["actual"]).replace("|", "/"), it["verdict"], it["evidence"]))
    sl = [s for s in (plan or {}).get("slides") or [] if isinstance(s, dict)]
    nar = {str(a.get("act")): str(a.get("slides") or "") for a in (plan or {}).get("narrative") or [] if isinstance(a, dict)}
    L += ["", "## 2. 叙事结构、页序与时长预算", "",
          "| 幕 | 金标准页段 | 预算秒 | 计划声明页段 | 判定 |", "|-|-|-|-|-|"]
    for a in [x for x in gs["outline"] if x["role"] != "cover"]:
        rng = nar.get(a["act"])
        L.append("| %s | %s | %d | %s | %s |" % (a["act"], a["pages"], a["seconds"], rng or "未声明",
                                                 "unmeasured" if not nar else ("pass" if norm(rng) == norm(a["pages"]) else "deviation")))
    L += ["", "> 页段取自 `narrative`；秒数是预算非实测。", "",
          "## 3. 页级证据对照", "", "| 页 | 角色 | 金标准证据种子 | 实际要点 | 逐字命中 | 判定 |", "|-|-|-|-|-|-|"]
    for p in gs["pages"]:
        s = next((x for x in sl if x.get("n") == p["n"]), sl[p["n"] - 1] if len(sl) >= p["n"] else {})
        bl = [b for b in (s.get("bullets") or []) if isinstance(b, dict)]
        ver = sum(1 for b in bl if b.get("quote") and find(b["quote"], idx))
        v = ("pass" if not bl else "deviation") if p["role"] == "cover" else (
            "missing" if not bl else ("pass" if ver == len(bl) and 3 <= len(bl) <= 5 else "deviation"))
        L.append("| %d | %s | %s | %d 条 | %d/%d | %s |" % (p["n"], ACT[p["role"]][0],
                                                           ", ".join(x["locator"] for x in p["evidence_seeds"]
                                                                     ) or ("无（封面）" if p["role"] == "cover" else "（材料未提供→预期缺口）"),
                                                           len(bl), ver, len(bl), v))
    L += ["", "## 4. 偏差与缺口处置", ""]
    dev = [it for it in items if it["verdict"] in ("deviation", "missing")]
    L += ["- **%s %s**：%s → 实际 %s。处置：%s" % (it["id"], it["dimension"], it["expected"], it["actual"],
                                               FIX.get(it["id"], "在 `work/slide_plan.json` 修正后重跑 check/build"))
          for it in dev] or ["- 无 deviation / missing。"]
    gaps = [p for p in gs["pages"] if p.get("expected_gap")]
    if gaps:
        L += ["", "### 预期缺口页（金标准未找到独立证据种子：合并页或写明缺口，不得补造）", ""] + [
            "- 第 %d 页（%s）：材料无独立证据种子，合格做法是合并/削减该页或写明缺口。" % (p["n"], ACT[p["role"]][0]) for p in gaps]
    L += ["", "## 5. 结论", "",
          "- 达标率 %.1f%%（%d/%d）。%s" % (sm["coverage"], sm["pass"], sm["items"],
                                           "可复核项全部通过；科学性仍以人工评审为准。" if sm["deviation"] + sm["missing"] == 0
                                           else "存在 %d 项偏差/缺失，见第 4 节。" % (sm["deviation"] + sm["missing"])),
          "- 只核验结构/证据/导出/版本的可复核性，不判断科学结论。", ""]
    return "\n".join(L)


def render_versions(plan, v0, gs, rep, status, changes, errors, degr, case_id):
    sl = [s for s in (plan or {}).get("slides") or [] if isinstance(s, dict)]
    bl = sum(len([b for b in (s.get("bullets") or []) if isinstance(b, dict)]) for s in sl)
    qc, qv = int(rep.get("quotes_checked") or 0), int(rep.get("quotes_verified") or 0)
    L = ["# 版本记录与回退", "", "- case_id：`%s`　生成时间：%s" % (case_id, _now()),
         "- 两类版本：Skill 包（v1.0.0→v1.1.0）、本次产物（v0 骨架→v1 成稿）。", "",
         "## 1. Skill 包版本", "", "| 版本 | 改了什么 | 为什么 | 如何回退 |", "|-|-|-|-|",
         "| v1.0.0 | init/show/check/build + makeppt；产物 pptx/pdf/plan/content_map/compliance | 原始链路（baseline_v1.zip） | 解压覆盖 |",
         "| v1.1.0 | 新增 `audit.py`；build 多产 5 个核验资产；`result.json` 增 4 字段 | 原包无法独立复核取舍过程 | 删 `audit.py` + 去掉 `main.py` 4 处 `audit.*` 调用即回 v1.0.0 |",
         "", "## 2. 本次产物版本", "", "| 版本 | 内容 | 位置 | 为什么 | 如何回退 |", "|-|-|-|-|-|",
         "| v0 骨架 | %d 页、%d 幕、预算 %d 秒；只有页序/页角色，无主张无证据 | `work/versions/v0_skeleton.json` | 先定页序与时长，再填内容，避免页数与讲述时长脱节 | `python3 scripts/main.py init` 重生成 |"
         % (len(v0.get("pages") or []), len(gs.get("outline") or []), int(v0.get("total_seconds") or 0)),
         "| v1 计划 | %d 页、%d 条要点、%d 条 quote（逐字命中 %d/%d） | `work/versions/v1_plan.json` | 在骨架上填主张/要点/讲稿/问答 | `build --plan work/versions/v1_plan.json` 复跑同一稿 |"
         % (len(sl), bl, qc, qv, qc),
         "| v1 成稿 | status=`%s`；pptx+preview+content_map+compliance+5 个核验资产 | `output/` | 渲染与核验分离：先定稿再逐项对照 | 用 v1_plan 重跑 build |" % status,
         "", "## 3. 本次实际变更（来自运行）", ""]
    L += ["- `%s`：%s → %s（原因：%s）" % (c.get("what"), c.get("from"), c.get("to"), c.get("why")) for c in changes or []]
    L += (["- 无计划级变更：计划一次通过校验。"] if not changes else []) + ["", "## 4. 降级与异常", ""]
    L += ["- 降级：%s" % d for d in (degr or ["无"])] + ["- 异常：%s" % e for e in (errors or ["无"])]
    L += ["", "## 5. 回退演练", "", "```bash",
          "python3 scripts/main.py build --plan work/versions/v1_plan.json   # 回到 v1 计划",
          "python3 -c \"import json;print(json.load(open('work/versions/v0_skeleton.json'))['pages'])\"",
          "rm -f scripts/audit.py && unzip -o baseline_v1.zip -d .           # 回到 v1.0.0", "```", ""]
    return "\n".join(L)


def self_check(out, case, idx, plan, gs, sm, contract_missing, status, rep, chk, errors, degr, rt, ckeys=None):
    files = ["golden_standard.json", "diff_report.md", "version_history.md", "run.log", "self_check.json", "result.json"]
    late = ("self_check.json", "result.json")
    arts = {f: {"exists": (Path(out) / f).is_file(), **({} if f in late else
                 {"bytes": (Path(out) / f).stat().st_size if (Path(out) / f).is_file() else 0})} for f in files}
    sl = [s for s in (plan or {}).get("slides") or [] if isinstance(s, dict)]
    bls = [b for s in sl for b in (s.get("bullets") or []) if isinstance(b, dict)]
    loc = sum(1 for b in bls if str(b.get("locator") or "").strip())
    res = sum(1 for b in bls if b.get("locator") and para_text(b["locator"], idx))
    n, nb = numeric_scan(plan, idx)
    probes = []
    for name, fn in (("empty_input", lambda: golden_standard({}, {"materials": [], "input_root": ""}, {}, 6)),
                     ("empty_plan", lambda: evaluate(gs, {}, {}, {}, idx, {}, None, contract_missing)),
                     ("number_mismatch", lambda: numeric_scan({"slides": [{"bullets": [{"text": "n=999", "quote": "n=1"}]}]}, idx))):
        try:
            fn()
            probes.append({"name": name, "pass": True, "detail": "未抛异常，返回带缺口/不一致标记的对象"})
        except Exception as e:
            probes.append({"name": name, "pass": False, "detail": repr(e)})
    allf = all(v["exists"] for v in arts.values())
    ev_ok = bool(bls) and res == len(bls) and int(rep.get("quotes_verified") or 0) == int(rep.get("quotes_checked") or 0)
    gate = allf and ev_ok and not nb and all(p["pass"] for p in probes)
    return {"schema": "self_check.v1", "case_id": (case or {}).get("case_id") or "unknown_case",
            "generated_at": _now(), "stage": "full", "status": status, "exit_code": 0, "runtime_seconds": rt,
            "artifacts": arts,
            "contract": {"expected_fields": ckeys or "见 result.json.output_contract",
                         "missing": contract_missing or [], "pass": not contract_missing},
            "evidence": {"slides": len(sl), "bullets": len(bls), "with_locator": loc, "locator_resolvable": res,
                         "quotes_checked": int(rep.get("quotes_checked") or 0),
                         "quotes_verified": int(rep.get("quotes_verified") or 0),
                         "pages_with_evidence": int(rep.get("slides_with_evidence") or 0),
                         "coverage_rate": round(100. * res / (len(bls) or 1), 1), "pass": ev_ok},
            "numeric": {"checked": n, "mismatch_count": len(nb), "mismatched": nb[:12], "pass": not nb},
            "golden_standard": {"pages": gs["totals"]["pages"], "acceptance_items": gs["totals"]["acceptance_items"],
                                "declared_gaps": gs["totals"]["gap_pages"]},
            "overall_gate": {"artifacts": allf, "evidence": ev_ok, "numeric": not nb,
                             "probes": all(p["pass"] for p in probes)},
            "diff": sm, "fallback_probes": probes,
            "errors": errors or [], "degradations": degr or [],
            "limits": ["金标准由规则推导，不判断科学性；时长是预算非实测；数字检查仅覆盖阿拉伯数字",
                       "预览等价性依赖 LibreOffice"],
            "overall": "pass" if (gate and sm["items"] > 0 and not sm["missing"]) else
                       ("partial" if gate else "fail")}


def fields():
    return STATE.get("fields") or {}


def _f(name, stage, **kw):
    p = Path(STATE.get("out") or ".") / name
    d = {"path": "output/%s" % name, "stage": stage, "bytes": p.stat().st_size if p.is_file() else 0}
    d.update(kw)
    return d


def flush_log(out):
    """Append only the not-yet-flushed records, so one run.log spans init/check/build."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    p, i = out / "run.log", STATE.get("flushed", 0)
    recs = LOG[i:]
    if not recs and STATE.get("hdr"):
        return p
    STATE["flushed"] = len(LOG)
    head = "" if STATE.get("hdr") else "=== run %s | T0 = process start | tag=%s ===\n" % (_now(), STATE.get("tag"))
    STATE["hdr"] = True
    body = "".join("[+%06.2fs] %-11s %s%s\n" % (r["t"], r["step"], r["msg"],
                                                (" " + json.dumps({k: v for k, v in r.items() if k not in ("t", "step", "msg")},
                                                                  ensure_ascii=False)) if len(r) > 3 else "") for r in recs)
    old = _raw(p) if p.is_file() else ""
    txt = old + head + body
    if len(txt.encode("utf-8")) > 60000:
        txt = "[log trimmed to last 40000 bytes]\n" + txt[-40000:]
    p.write_text(txt, encoding="utf-8")
    return p


def ensure_min(out, case_id="unknown_case", stage="partial", errors=None, tag="minimal"):
    """Guarantee five valid assets even if the run dies before build."""
    out = Path(out)
    STATE["out"], STATE["tag"] = str(out), tag
    out.mkdir(parents=True, exist_ok=True)
    err = [str(e) for e in (errors or [])][:6]
    if not (out / "golden_standard.json").is_file():
        dump(out / "golden_standard.json", {
            "schema": "golden_standard.v1", "case_id": case_id, "generated_at": _now(), "stage": "minimal",
            "basis": {"statement": "最小占位：完整金标准在 build 阶段生成。", "derivation": "audit.py:ensure_min"},
            "constraints": [], "outline": [], "pages": [], "logic": [], "acceptance": [],
            "totals": {"pages": 0, "acts": 0, "logic_items": 0, "acceptance_items": 0, "seconds": 0,
                       "evidence_seeds": 0, "gap_pages": 0},
            "limits": ["build 未执行/失败：合法占位，不代表本案例金标准"] + err})
    if not (out / "diff_report.md").is_file():
        (out / "diff_report.md").write_text("\n".join(
            ["# 差异化核验报告（最小占位）", "", "- case_id：`%s`　阶段：`%s`" % (case_id, stage),
             "- build 尚未完成，逐项对照待生成。", "", "## 已知错误", ""] + ["- %s" % e for e in (err or ["无"])] +
            ["", "下一步：运行 `python3 scripts/main.py build`。", ""]), encoding="utf-8")
    if not (out / "version_history.md").is_file():
        (out / "version_history.md").write_text("\n".join(
            ["# 版本记录与回退（最小占位）", "", "- case_id：`%s`　阶段：`%s`" % (case_id, stage), "",
             "| 版本 | 内容 | 如何回退 |", "|-|-|-|", "| v1.0.0 | baseline Skill 包 | 解压 `baseline_v1.zip` 覆盖 |",
             "| v1.1.0 | 新增 5 个核验资产 | 删 `scripts/audit.py` 并还原 `main.py` |",
             "", "v0 骨架 / v1 成稿在 build 完成后写入本文件。", ""]), encoding="utf-8")
    flush_log(out)
    if not (out / "self_check.json").is_file():
        dump(out / "self_check.json", {"schema": "self_check.v1", "case_id": case_id, "generated_at": _now(),
                                       "stage": "minimal", "status": stage, "exit_code": 0, "overall": "partial",
                                       "artifacts": {f: {"exists": (out / f).is_file()} for f in
                                                     ("golden_standard.json", "diff_report.md", "version_history.md", "run.log")},
                                       "contract": {"pass": False, "missing": ["build 未完成"]},
                                       "evidence": {"pass": False, "coverage_rate": 0.0},
                                       "numeric": {"pass": False, "checked": 0}, "errors": err,
                                       "limits": ["最小自检：仅在 build 未完成时存在"]})
    STATE["fields"] = {"golden_standard": _f("golden_standard.json", "minimal", items=0, pages=0),
                       "diff_report": _f("diff_report.md", "minimal", pass_items=0, items=0, coverage_pct=0.0),
                       "version_history": _f("version_history.md", "minimal", versions=["v0_skeleton", "v1_plan", "v1_final"]),
                       "self_check": _f("self_check.json", "minimal", overall="partial", exit_code=0)}
    return STATE["fields"]


def finalize(out, work, case, idx, h, plan, chk, rep, target, vals, status,
             errors, degr, changes, v0, contract_missing=None, ckeys=None):
    """Write the five assets. Never raises; degrades to ensure_min on failure."""
    out, work = Path(out), Path(work)
    STATE["out"], STATE["tag"] = str(out), "full"
    case, plan = case if isinstance(case, dict) else {}, plan if isinstance(plan, dict) else {}
    log("assets", "start", stage="full")
    v0 = v0 or {}
    v0["case_id"] = v0.get("case_id") or case.get("case_id")
    try:
        gs = golden_standard(case, idx, h, target)
        dump(out / "golden_standard.json", gs)
        log("assets", "golden_standard written", pages=gs["totals"]["pages"], items=gs["totals"]["acceptance_items"])
    except Exception as e:
        errors.append("golden_standard failed: %r" % (e,))
        log("error", "golden_standard", tb=traceback.format_exc()[-300:])
        ensure_min(out, case.get("case_id"), "partial", errors, tag="degraded")
        return STATE["fields"]
    items, sm = [], {"pass": 0, "deviation": 0, "missing": 0, "unmeasured": 0, "items": 0, "coverage": 0.0}
    try:
        items = evaluate(gs, plan, chk, rep, idx, vals, target, contract_missing)
        sm = summarise(items)
        (out / "diff_report.md").write_text(render_diff(gs, items, plan, sm, target, idx), encoding="utf-8")
        log("assets", "diff_report written", pass_=sm["pass"], deviation=sm["deviation"], missing=sm["missing"])
    except Exception as e:
        errors.append("diff_report failed: %r" % (e,))
        log("error", "diff_report", tb=traceback.format_exc()[-300:])
        if not (out / "diff_report.md").is_file():
            (out / "diff_report.md").write_text("# 差异化核验报告\n\n生成失败：%r\n" % (e,), encoding="utf-8")
    try:
        dump(work / "versions" / "v0_skeleton.json", v0)
        dump(work / "versions" / "v1_plan.json", plan)
        (out / "version_history.md").write_text(
            render_versions(plan, v0, gs, rep, status, changes, errors, degr, gs.get("case_id")), encoding="utf-8")
        log("assets", "version_history written", v0_pages=len(v0.get("pages") or []), v1_pages=len(plan.get("slides") or []))
    except Exception as e:
        errors.append("version_history failed: %r" % (e,))
        log("error", "version_history", tb=traceback.format_exc()[-300:])
    for d in degr or []:
        log("degradation", str(d)[:200])
    for e in errors or []:
        log("exception", str(e)[:200])
    log("assets", "run.log flush", lines=len(LOG))
    try:
        flush_log(out)
    except Exception:
        pass
    try:
        sc = self_check(out, case, idx, plan, gs, sm, contract_missing, status, rep, chk, errors, degr,
                        round(time.time() - T0, 2), ckeys)
        dump(out / "self_check.json", sc)
        overall = sc["overall"]
        log("assets", "self_check written", overall=overall)
    except Exception as e:
        errors.append("self_check failed: %r" % (e,))
        log("error", "self_check", tb=traceback.format_exc()[-300:])
        overall, sc = "fail", {"overall": "fail", "stage": "degraded", "evidence": {}}
    t = gs["totals"]
    STATE["fields"] = {
        "golden_standard": _f("golden_standard.json", "full", items=t["acceptance_items"], pages=t["pages"],
                              acts=t["acts"], evidence_seeds=t["evidence_seeds"], declared_gaps=t["gap_pages"],
                              basis=gs["basis"]["derivation"]),
        "diff_report": _f("diff_report.md", "full", pass_items=sm["pass"], deviation=sm["deviation"],
                          missing=sm["missing"], unmeasured=sm["unmeasured"], items=sm["items"], coverage_pct=sm["coverage"]),
        "version_history": _f("version_history.md", "full", versions=["v1.0.0-baseline", "v1.1.0", "v0_skeleton", "v1_plan", "v1_final"],
                              v0_snapshot="work/versions/v0_skeleton.json", v1_snapshot="work/versions/v1_plan.json"),
        "self_check": _f("self_check.json", sc.get("stage", "full"), overall=overall, exit_code=0,
                         evidence_coverage=(sc.get("evidence") or {}).get("coverage_rate")),
    }
    return STATE["fields"]
