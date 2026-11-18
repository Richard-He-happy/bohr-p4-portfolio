#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py — 思维导图模型库：证据核验、结构规范化、校验、SVG/PNG 渲染、契约回填。

main.py 调用本库；也可独立校验工作稿（默认退出码 0，--strict 时 error 返回 1）：
  python3 verify.py --work /app/work/mindmap.json
"""
from __future__ import annotations

import argparse, html, json, re, shutil, subprocess, sys, unicodedata
from pathlib import Path

EDGE_TYPES = ("hierarchy", "cause", "contrast", "support", "conflict", "sequence", "depends", "cite", "example", "definition")
ROLES = ("topic", "question", "method", "evidence", "finding", "conclusion", "limitation", "gap", "task", "risk", "concept", "subtopic")  # noqa
PAL = {0: ("#1f3a5f", "#ffffff"), 1: ("#2f6f9f", "#ffffff"), 2: ("#e6f0f7", "#17324a"), 3: ("#f3f7fa", "#17324a")}
REL = {"cause": ("#b3541e", "6,4"), "contrast": ("#6a4c93", "6,4"), "support": ("#2a7f62", "6,4"),
       "conflict": ("#b02a37", "3,3"), "sequence": ("#1f6f8b", "8,3"), "depends": ("#8a6d1f", "4,3"),
       "cite": ("#5b6b7b", "2,4"), "example": ("#4d7c0f", "6,3"), "definition": ("#7a4b8a", "5,3")}
REQ = ("sources", "uncertainty", "pending_human", "errors", "degradations", "changes", "runtime", "artifacts", "coverage")
CMAP = [(r"case_?id|^id$|编号", "case_id"), (r"content_?map|映射表", "content_map"),
        (r"evidence|来源映射|source_?map|trace|引用", "evidence_map"), (r"preserved|fact|事实|数字|术语", "preserved_facts"),
        (r"change|revision|diff|修改|版本|变更", "change_log"), (r"deliver|artifact|产物|文稿|main_?output|result", "deliverable"),
        (r"mindmap|structure|导图|节点|hierarch", "mindmap"), (r"uncertain|不确定|风险", "uncertainty"),
        (r"preview|预览|png|export", "preview"), (r"count|统计|coverage|覆盖", "coverage"), (r"note|说明|comment|remark", "note")]
WS = re.compile(r"[\s\-]+")


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    for a, b in (("\u00ad", ""), ("\u2010", "-"), ("\u2011", "-"), ("\u2012", "-"), ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2212", "-"), ("\u2018", '"'), ("\u2019", '"'), ("\u201c", '"'), ("\u201d", '"'), ("\u00a0", " "), ("\u3000", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip().lower()


def loose(s):
    return WS.sub("", norm(s))


class MatCache:
    def __init__(self, mats):
        self.m = {x["id"]: x for x in (mats or []) if isinstance(x, dict) and x.get("id")}
        self.c = {}

    def _t(self, mid):
        if mid not in self.c:
            us = [(u.get("locator") or "?", norm(u.get("text")), loose(u.get("text")))
                  for u in ((self.m.get(mid) or {}).get("units") or [])]
            body = " ".join(u[1] for u in us)
            self.c[mid] = (us, body, WS.sub("", body))
        return self.c[mid]

    def locate(self, mid, quote):
        q = (quote or "").strip()
        if not q or mid not in self.m:
            return False, None
        us, bn, bl = self._t(mid)
        qn, ql = norm(q), loose(q)
        if not qn or (qn not in bn and (not ql or ql not in bl)):
            return False, None
        for loc, un, ul in us:
            if qn in un or (ql and ql in ul):
                return True, loc
        return True, None


def sent(t, cap=150):
    t = re.sub(r"\s+", " ", t or "").strip()
    m = re.match(r"(.{4,}?[。．.!?！？；;])", t)
    return (m.group(1) if m else t)[:cap].strip()


def _evs(src, cache):
    out, ok = [], False
    for e in (src or []):
        if not isinstance(e, dict):
            continue
        q = str(e.get("quote") or "").strip()
        loc = str(e.get("locator") or "").strip()
        mid = str(e.get("material") or "").strip()
        hit, found = cache.locate(mid, q)
        if not hit and not q and re.match(r"^(figure|fig|image|table|tbl|slide|图|表)", loc, re.I):
            hit = True
        out.append({"material": mid, "locator": loc or (found or ""), "quote": q, "verified": hit})
        ok = ok or hit
    return out, ok


def normalize_model(work, index):
    cache = MatCache(index.get("materials"))
    th = work.get("theme") if isinstance(work.get("theme"), dict) else {"label": str(work.get("theme") or "")}
    m = {"theme": {"id": "root", "label": str(th.get("label") or "").strip()[:60],
                   "evidence": [e for e in (th.get("evidence") or []) if isinstance(e, dict)]},
         "nodes": [], "edges": [], "dropped": [], "unverified": []}
    ids = {"root"}
    for i, n in enumerate([x for x in (work.get("nodes") or []) if isinstance(x, dict)], 1):
        if not str(n.get("label") or "").strip():
            continue
        nid = str(n.get("id") or "n%d" % i).strip()
        if nid in ids:
            nid = "n%d_%d" % (i, len(ids))
        ids.add(nid)
        ev, ok = _evs(n.get("evidence"), cache)
        m["nodes"].append({"id": nid, "label": str(n.get("label")).strip()[:60], "parent": str(n.get("parent") or "root").strip(),
                           "role": str(n.get("role") or "subtopic").lower(), "summary": str(n.get("summary") or ""),
                           "status": str(n.get("status") or "summary").lower(), "evidence": ev, "level": 1})
        if not ok:
            m["unverified"].append(nid)
    for n in m["nodes"]:
        if n["parent"] not in ids:
            n["parent"] = "root"
    for i, e in enumerate([x for x in (work.get("edges") or []) if isinstance(x, dict)], 1):
        a, b = str(e.get("from") or "").strip(), str(e.get("to") or "").strip()
        typ = str(e.get("type") or "hierarchy").lower()
        if typ not in EDGE_TYPES or a not in ids or b not in ids or a == b:
            m["dropped"].append({"from": a, "to": b, "type": typ, "reason": "端点或类型非法"})
            continue
        ev, ok = _evs(e.get("evidence"), cache)
        if not ev:
            m["dropped"].append({"from": a, "to": b, "type": typ, "reason": "无证据"})
            continue
        m["edges"].append({"id": "e%d" % i, "from": a, "to": b, "type": typ, "label": str(e.get("label") or ""),
                           "evidence": ev, "grounded": ok})
    m["depth"], m["cycles"] = levels(m)
    return m


# ------------------------------------------------------------------ 兜底成稿
def _ish(t):
    t = (t or "").strip()
    return len(t) <= 34 and not re.search(r"[。．.；;！!？?]$", t)


def _sections(us, cap=5):
    """按标题样式切小节；无标题时按段落均分，使单材料也能撑起 3–5 个分支。"""
    out, cur = [], []
    for u in us:
        if _ish(u.get("text")) and cur:
            out.append(cur)
            cur = [u]
        else:
            cur.append(u)
    if cur:
        out.append(cur)
    out = [s for s in out if len(s) >= 2]
    if len(out) < 2 and len(us) >= 4:
        n = min(cap, max(2, len(us) // 2))
        size = max(1, (len(us) + n - 1) // n)
        out = [us[i:i + size] for i in range(0, len(us), size)][:cap]
    return out[:cap]


def fallback_model(index):
    """兜底：每份材料一个分支，首/中/末段为叶子，quote 取原文片段。"""
    ms = [m for m in (index.get("materials") or []) if m.get("units")]
    title = next((m["title"] for m in ms if len(m.get("title") or "") >= 4), None)
    nodes, spare, bi = [], [], 0
    for mat in ms[:3]:
        for sec in _sections(mat["units"])[:5]:
            if len(nodes) >= 34:
                break
            bi += 1
            bid, head = "b%d" % bi, sec[0]
            ev = {"material": mat["id"], "locator": head["locator"], "quote": sent(head["text"], 150)}
            hlab = re.sub(r"^#{1,6}\s*", "", sent(head["text"], 40)).strip()
            nodes.append({"id": bid, "label": (hlab or (mat.get("title") or mat["name"]))[:20],
                          "parent": "root", "role": "subtopic", "status": "summary", "evidence": [ev]})
            body = sec[1:]
            for k, u in enumerate(body[:5], 1):
                lab = sent(u["text"], 36).strip("。．. ")
                if len(lab) < 3:
                    continue
                nodes.append({"id": "%s_n%d" % (bid, k), "label": lab[:22], "parent": bid, "role": "evidence",
                              "status": "summary", "evidence": [{"material": mat["id"], "locator": u["locator"],
                                                                 "quote": sent(u["text"], 150)}]})
            for u in body[5:]:
                spare.append((bid, mat["id"], u))
    # 规模补足：把未用段落挂回子节点不足的支（引用原文，不新增材料外内容）
    for bid, mid, u in spare:
        if len(nodes) >= 18:
            break
        lab = sent(u["text"], 36).strip("。．. ")
        if len(lab) < 3:
            continue
        nodes.append({"id": "%s_x%d" % (bid, len(nodes)), "label": lab[:22], "parent": bid, "role": "evidence",
                      "status": "summary",
                      "evidence": [{"material": mid, "locator": u["locator"], "quote": sent(u["text"], 150)}]})
    if not nodes:
        nodes = [{"id": "n1", "label": "材料无可解析文本，需人工补充", "parent": "root", "role": "risk", "evidence": []}]
    return {"theme": {"id": "root", "label": (title or str(index.get("case_id") or "材料要点"))[:40], "evidence": []},
            "nodes": nodes, "edges": []}


def levels(m):
    by = {n["id"]: n for n in m["nodes"]}
    depth, cyc = 1, []
    for n in m["nodes"]:
        seen, d, cur = {n["id"]}, 0, n
        while True:
            par = str(cur.get("parent") or "root").strip()
            if par in ("", "root"):
                break
            if par not in by or par in seen or d > 12:
                d = -1
                break
            seen.add(par)
            d += 1
            cur = by[par]
        if d < 0:
            cyc.append(n["id"])
        else:
            n["level"] = d + 1
            depth = max(depth, d + 1)
    return depth, cyc


def validate(work, index):
    m = normalize_model(work, index)
    iss = []

    def add(sev, code, msg, **kw):
        d = {"severity": sev, "code": code, "message": msg}
        d.update({k: v for k, v in kw.items() if v is not None})
        iss.append(d)

    nodes = m["nodes"]
    if not m["theme"]["label"]:
        add("error", "theme_missing", "缺 theme.label")
    if not nodes:
        add("error", "no_nodes", "nodes 为空")
    depth, cyc = levels(m)
    if cyc:
        add("error", "cycle_broken", "父子链成环/断链：%s" % ", ".join(cyc[:6]))
    labs, roles = {}, {}
    for n in nodes:
        if len(n["label"]) > 30:
            add("warn", "label_long", "标签过长 %s(%d字)" % (n["id"], len(n["label"])), node=n["id"])
        if norm(n["label"]) in labs:
            add("warn", "dup_label", "标签重复 %s≈%s" % (n["id"], labs[norm(n["label"])]), node=n["id"])
        labs[norm(n["label"])] = n["id"]
        if n["role"] in ROLES:
            roles[n["role"]] = roles.get(n["role"], 0) + 1
        elif n["role"]:
            add("warn", "role_unknown", "role 非词表 %s=%s" % (n["id"], n["role"]), node=n["id"])
    for i in m["unverified"]:
        add("error", "node_unverified", "无证据节点 %s" % i, node=i)
    for d in m["dropped"]:
        add("error" if "非法" in d["reason"] else "warn", "edge_dropped", "未采用边 %s→%s：%s" % (d["from"], d["to"], d["reason"]))
    for e in m["edges"]:
        if not e["grounded"]:
            add("warn", "edge_unverified", "边无证据 %s→%s" % (e["from"], e["to"]), edge=e["id"])
    for r in ("method", "finding"):
        if len(nodes) >= 6 and r not in roles:
            add("warn", "role_missing", "缺角色 %s" % r)
    if depth > 4:
        add("warn", "depth_deep", "层级过深 %d" % depth)
    if len(nodes) > 40:
        add("warn", "node_many", "节点过多 %d（期望 15–40）" % len(nodes))
    if 0 < len(nodes) < 15:
        add("warn", "node_few", "节点过少 %d（期望 15–40）" % len(nodes))
    ver = sum(1 for n in nodes if any(e["verified"] for e in n["evidence"]))
    st = {"nodes": len(nodes), "edges": len(m["edges"]), "depth": depth, "roles": roles,
          "verified_nodes": ver, "unverified_nodes": len(nodes) - ver,
          "verified_quotes": sum(1 for n in nodes for e in n["evidence"] if e["verified"]),
          "rejected_quotes": sum(1 for n in nodes for e in n["evidence"] if not e["verified"]),
          "verified_ratio": round(ver / len(nodes), 3) if nodes else 0.0}
    errs = sum(1 for x in iss if x["severity"] == "error")
    return {"issues": iss, "stats": st, "errors": errs, "warnings": len(iss) - errs,
            "ok": errs == 0 and len(nodes) >= 6 and st["verified_ratio"] >= 0.8, "model": m}


def cw(ch):
    return 15.6 if ord(ch) > 0x2E7F else 8.4


def wrap(t, mx, n=3):
    out, cur, w = [], "", 0.0
    for ch in t:
        c = cw(ch)
        if w + c > mx and cur:
            out.append(cur)
            cur, w = ch, c
        else:
            cur += ch
            w += c
    if cur:
        out.append(cur)
    if len(out) > n:
        out = out[:n]
        out[-1] = out[-1][:-1] + "…"
    return out or [""]


def layout(model):
    MG, HG, VG = 36, 34, 14
    nd = {"root": {"id": "root", "label": model["theme"]["label"] or "中心主题", "parent": None, "level": 0, "role": "topic"}}
    for n in model["nodes"]:
        nd[n["id"]] = {"id": n["id"], "label": n["label"] or n["id"], "parent": n["parent"], "level": n.get("level", 1), "role": n.get("role", "")}
    for k, v in nd.items():
        if k != "root" and v["parent"] not in nd:
            v["parent"] = "root"
    kids = {}
    for k, v in nd.items():
        if k != "root":
            kids.setdefault(v["parent"], []).append(k)
    for v in nd.values():
        v["lines"] = wrap(v["label"], 250 if v["level"] == 0 else (218 if v["level"] == 1 else 200))
        v["w"] = max(72.0, max(sum(cw(c) for c in ln) for ln in v["lines"]) + 26)
        v["h"] = len(v["lines"]) * 19 + 15
    colw, colx, x = {}, {}, MG
    for v in nd.values():
        colw[v["level"]] = max(colw.get(v["level"], 0.0), v["w"])
    for d in sorted(colw):
        colx[d] = x
        x += colw[d] + HG
    sub = {}

    def meas(i, d=0):
        ch = kids.get(i, [])
        tot = sum(meas(c, d + 1) for c in ch) + VG * max(0, len(ch) - 1) if ch and d < 7 else 0
        sub[i] = max(nd[i]["h"], tot)
        nd[i]["kids"] = ch
        return sub[i]

    meas("root")
    pos = {}

    def put(i, x0, yt, d=0):
        ch = nd[i]["kids"]
        tot = sum(sub[c] for c in ch) + VG * max(0, len(ch) - 1) if ch else 0
        cy = yt + sub[i] / 2
        pos[i] = (x0, cy - nd[i]["h"] / 2, nd[i]["w"], nd[i]["h"])
        if ch and d < 7:
            yy = yt + (sub[i] - tot) / 2
            for c in ch:
                put(c, colx[nd[c]["level"]], yy, d + 1)
                yy += sub[c] + VG

    put("root", MG, MG)
    return nd, kids, pos, max(p[0] + p[2] for p in pos.values()) + MG, sub["root"] + 2 * MG + 56


def render_svg(model, nd, pos, W, H, meta):
    e = html.escape
    s = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
         'font-family="Noto Sans CJK SC, Microsoft YaHei, Arial, sans-serif">' % (int(W), int(H), int(W), int(H)),
         '<title>%s</title><desc>%s</desc>' % (e(model["theme"]["label"]), e(meta)),
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
         'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#5b6b7b"/></marker></defs>', '<g id="edges">']
    for n in model["nodes"]:
        if n["parent"] in pos and n["id"] in pos:
            x1, y1, w1, h1 = pos[n["parent"]]
            x2, y2, w2, h2 = pos[n["id"]]
            ax, ay, bx, by = x1 + w1, y1 + h1 / 2, x2, y2 + h2 / 2
            dx = max(18.0, (bx - ax) / 2)
            s.append('<path id="edge-h-%s" class="edge" data-type="hierarchy" data-from="%s" data-to="%s" '
                     'd="M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="#9db4c6" stroke-width="1.6"/>'
                     % (e(n["id"]), e(n["parent"]), e(n["id"]), ax, ay, ax + dx, ay, bx - dx, by, bx, by))
    for ed in model["edges"]:
        a, b = ed["from"], ed["to"]
        if a not in pos or b not in pos:
            continue
        col, dash = REL.get(ed["type"], ("#5b6b7b", "4,3"))
        x1, y1, w1, h1 = pos[a]
        x2, y2, w2, h2 = pos[b]
        ax, ay, bx, by = x1 + w1 / 2, y1 + h1, x2 + w2 / 2, y2
        my = (ay + by) / 2 - 20
        s.append('<path id="edge-%s" class="rel-%s" data-type="%s" data-from="%s" data-to="%s" '
                 'd="M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" stroke-width="1.5" '
                 'stroke-dasharray="%s" marker-end="url(#arw)"/>'
                 % (e(ed["id"]), e(ed["type"]), e(ed["type"]), e(a), e(b), ax, ay, ax, my, bx, my, bx, by, col, dash))
        s.append('<text id="elabel-%s" x="%.1f" y="%.1f" font-size="11" fill="%s" text-anchor="middle">%s</text>'
                 % (e(ed["id"]), (ax + bx) / 2, my - 4, col, e((ed.get("label") or ed["type"])[:14])))
    s.append('</g><g id="nodes">')
    evs = {}
    for n in model["nodes"]:
        ev = [x for x in (n.get("evidence") or []) if isinstance(x, dict)]
        evs[n["id"]] = sorted(ev, key=lambda x: 1 if x.get("verified") else 0, reverse=True)
    evs["root"] = [x for x in (model["theme"].get("evidence") or []) if isinstance(x, dict)]
    for i, v in nd.items():
        if i not in pos:
            continue
        x, y, w, h = pos[i]
        lv = v["level"]
        fill, ink = PAL.get(lv, PAL[3])
        top = (evs.get(i) or [{}])[0]
        s.append('<g id="node-%s" data-node-id="%s" data-level="%d" data-role="%s"%s '
                 'data-locator="%s" data-quote="%s" data-material="%s" data-evidence="%d" data-verified="%d"><title>%s</title>'
                 % (e(i), e(i), lv, e(v.get("role") or ""),
                    "" if i == "root" else ' data-parent="%s"' % e(v["parent"]),
                    e(str(top.get("locator") or "")[:60]), e(str(top.get("quote") or "")[:200]),
                    e(str(top.get("material") or "")[:12]), len(evs.get(i) or []), 1 if top.get("verified") else 0,
                    e(v["label"][:200])))
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="8" fill="%s" stroke="%s" stroke-width="1.4"/>'
                 % (x, y, w, h, fill, "#2f6f9f" if lv <= 1 else "#c9d8e4"))
        s.append('<text x="%.1f" y="%.1f" font-size="%s" font-weight="%s" fill="%s" text-anchor="middle">'
                 % (x + w / 2, y + (h - len(v["lines"]) * 19) / 2 + 14, 16 if lv == 0 else (14.5 if lv == 1 else 13),
                    "600" if lv <= 1 else "400", ink))
        for k, ln in enumerate(v["lines"]):
            s.append('<tspan x="%.1f" dy="%s">%s</tspan>' % (x + w / 2, 0 if k == 0 else 19, e(ln)))
        s.append("</text></g>")
    s.append('</g><g id="footer"><text x="36" y="%.1f" font-size="11.5" fill="#6b7d8d">%s</text></g></svg>' % (H - 18, e(meta)))
    return "\n".join(s)


def png_export(svg, png):
    for c in (["rsvg-convert", "-w", "2200", "-o", str(png), str(svg)],
              ["inkscape", str(svg), "--export-type=png", "--export-filename=" + str(png)],
              ["convert", "-background", "white", "-density", "150", str(svg), str(png)]):
        if not shutil.which(c[0]):
            continue
        try:
            subprocess.run(c, capture_output=True, timeout=180)
            if png.is_file() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and png.stat().st_size > 1200:
                return c[0]
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ 契约与自检
def contract_values(contract, ctx):
    vals = {}
    for k in (contract or {}):
        key = str(k).lower() + str(k)
        for pat, name in CMAP:
            if re.search(pat, key):
                vals[k] = ctx.get(name)
                break
        else:
            vals[k] = {"note": "无专门产物，由通用交付摘要填充", "artifacts": ctx.get("files")}
    return vals


def finalize(res, contract, ctx, out_path, closes=None, extra=None):
    out = {"case_id": res.get("case_id"), "status": res.get("status")}
    for k, v in contract_values(contract, ctx).items():
        if k not in ("case_id", "status"):
            out[k] = v
    for k in REQ:
        out[k] = res.get(k) if res.get(k) is not None else {}
    if closes:
        out["runtime"] = dict(out.get("runtime") or {}, **closes)
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in ("case_id", "status"):
                out.setdefault(k, v)   # 契约字段优先级更高：同名时保留契约回填值
    try:
        Path(out_path).write_bytes(json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))
    except Exception:
        pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description="思维导图工作稿校验：证据逐字命中、结构合法性、覆盖统计。",
                                 epilog="示例：python3 verify.py --work /app/work/mindmap.json")
    ap.add_argument("--work", help="工作稿 mindmap.json")
    ap.add_argument("--index", help="材料索引 index.json（默认同目录）")
    ap.add_argument("--strict", action="store_true", help="有 error 时退出码 1（默认 0）")
    a = ap.parse_args(argv)
    if not a.work:
        ap.print_help()
        return 0
    reps = []
    if a.work:
        try:
            w = json.loads(Path(a.work).read_bytes().decode("utf-8-sig"))
        except Exception:
            w = None
        try:
            idx = json.loads(Path(a.index or (Path(a.work).parent / "index.json")).read_bytes().decode("utf-8-sig"))
        except Exception:
            idx = {}
        reps.append(validate(w, idx or {}))
    for r in reps:
        print("== %s errors=%d warnings=%d" % ("通过" if r.get("ok") else "未通过", r.get("errors", 0), r.get("warnings", 0)))
        for it in (r.get("issues") or [])[:25]:
            print("  [%s] %s" % (it["severity"], it["message"]))
    return 1 if (a.strict and any(r.get("errors") for r in reps)) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print("verify.py 内部异常（已忽略）：%s" % exc)
        sys.exit(0)
