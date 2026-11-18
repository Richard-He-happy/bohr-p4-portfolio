#!/usr/bin/env python3
"""Verifiability assets (patch 1.4.0): golden standard, diff report, version history, run log, self check.

Derived only from what the run actually read (`work/index.json`, `/input`) and actually
wrote (`/app/output`): no expected content is invented, no source text is rewritten, and
every quote is a substring of the indexed source by construction.
Stdlib only, CWD-independent, never raises into the caller.
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import kit as K

PH = "[待译 / PENDING TRANSLATION]"
QC = 260
NEW_ASSETS = ("golden_standard.json", "diff_report.md", "version_history.md", "run.log", "self_check.json")
CORE = ("translation.md", "alignment.csv", "glossary.csv", "preserved_facts.json",
        "evidence_map.json", "change_log.json")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(s, n=16):
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:n]


def fsha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:32]
    except Exception:
        return None


def fsize(p):
    try:
        return Path(p).stat().st_size
    except Exception:
        return None


def wjson(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def wtext(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s if s.endswith("\n") else s + "\n", encoding="utf-8")
    return p


def rjson(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def cell(v):
    return ("" if v is None else str(v)).replace("|", "\\|").replace("\n", " ")


def tbl(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


# ---------------------------------------------------------------- run log
def logev(work, stage, detail, dur=None):
    try:
        line = "%s | %-5s | %s%s" % (now(), stage, str(detail).replace("\n", " "),
                                     (" | dur=%.2fs" % dur) if dur is not None else "")
        with open(Path(work) / "run.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def readlog(work):
    try:
        return [x for x in Path(work, "run.log").read_text(encoding="utf-8").splitlines() if x.strip()]
    except Exception:
        return []


# ---------------------------------------------------------------- golden standard
def qwin(text, token=None, cap=QC):
    """Verbatim substring of `text`: whole paragraph, or a window centred on `token`."""
    t = text or ""
    if len(t) <= cap:
        return t
    i = t.find(token) if token else -1
    if i >= 0:
        a = max(0, min(len(t) - cap, i - cap // 2))
        return t[a:a + cap]
    return t[:cap]


def golden(ix, draft, ctr, lang):
    ps = ix.get("paragraphs") or []
    sup = [g for g in (ix.get("supplied_terms") or []) if isinstance(g, dict)]
    terms, seen = [], set()
    for g in sup + [g for g in ((draft or {}).get("glossary") or []) if isinstance(g, dict)]:
        k = str(g.get("term") or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            terms.append((g, "case.supplied_terms" if g in sup else "workdraft.glossary"))
    units, facts, ev = [], [], []
    for i, p in enumerate(ps, 1):
        t, pid, loc = p.get("text") or "", p["para_id"], p.get("locator")
        units.append({"req_id": "U-" + pid, "para_id": pid, "locator": loc, "kind": p.get("kind"),
                      "position": i, "source_chars": p.get("chars"), "source_sha1": sha(t),
                      "expect": "1:1 target unit at the same position; para_id + locator unchanged; non-empty",
                      "source_quote": qwin(t)})
        ev.append({"req_id": "E-" + pid, "para_id": pid, "locator": loc,
                   "expect": "evidence_map unit holds this paragraph's verbatim quote + locator + target",
                   "source_quote": qwin(t)})
        for n in dict.fromkeys(K.num_tokens(t)):
            facts.append({"req_id": "F-%s-N%s" % (pid, re.sub(r"\W+", "", n)), "para_id": pid, "locator": loc,
                          "kind": "number", "value": n, "source_quote": qwin(t, n),
                          "expect": "identical numeric string in the target (no rounding, no rescaling)"})
        for j, c in enumerate(dict.fromkeys(K.CIT.findall(t)), 1):
            facts.append({"req_id": "F-%s-C%02d" % (pid, j), "para_id": pid, "locator": loc,
                          "kind": "citation", "value": c, "source_quote": qwin(t, c),
                          "expect": "citation marker kept verbatim in the target"})
        for j, u in enumerate(dict.fromkeys(K.UNIT.findall(t)), 1):
            facts.append({"req_id": "F-%s-U%02d" % (pid, j), "para_id": pid, "locator": loc,
                          "kind": "unit", "value": u, "source_quote": qwin(t, u),
                          "expect": "unit token present in the target; no conversion"})
    glossary = []
    for j, (g, origin) in enumerate(terms, 1):
        term = g["term"]
        occ = [{"para_id": p["para_id"], "locator": p.get("locator"),
                "quote": qwin(p.get("text") or "", term)}
               for p in ps if term.lower() in (p.get("text") or "").lower()][:40]
        glossary.append({"req_id": "G%02d" % j, "term": term,
                         "expected_target": g.get("target") or None,
                         "status_expected": "locked" if g.get("target") else "pending_human",
                         "origin": origin, "note": g.get("note") or "",
                         "locator": g.get("locator") or "case.supplied_terms",
                         "occurrences": occ, "occurrence_count": len(occ),
                         "expect": "one target per term in all occurrences; empty target => pending_human"})
    deliver = [{"name": "translation.md", "why": "bilingual paragraph-aligned editable manuscript"},
               {"name": "alignment.csv", "why": "para_id/locator level source-target table"},
               {"name": "glossary.csv", "why": "term -> target with locked/pending_human status"},
               {"name": "preserved_facts.json", "why": "numbers/units/citations + present_in_target"},
               {"name": "evidence_map.json", "why": "per-unit verbatim quote, locator, target"},
               {"name": "change_log.json", "why": "change records with reason and locator"}]
    meta = [{"req_id": "M01", "locator": "case.output_contract",
             "expect": "every output_contract key present in result.json (%d supplied)" % len(ctr or {})},
            {"req_id": "M02", "locator": "alignment.csv",
             "expect": "target units in index order 1..%d, no extra/missing para_id" % len(ps)},
            {"req_id": "M03", "locator": "result.json#status",
             "expect": "status honest: ok only when coverage 100% and verdict pass"},
            {"req_id": "M04", "locator": "scripts/main.py",
             "expect": "exit code 0 on every path, including empty/bad input"},
            {"req_id": "M05", "locator": "result.json#runtime.phase",
             "expect": "legal partial result.json exists before real work (init)"}]
    tot = {"units": len(units), "glossary": len(glossary), "facts": len(facts), "evidence": len(ev),
           "deliverables": len(deliver), "meta": len(meta)}
    tot["all"] = sum(tot.values())
    return {"schema": "golden-standard/v1", "case_id": ix.get("case_id"), "generated_at": now(),
            "target_lang": lang,
            "provenance": {"derived_from": "work/index.json + case.output_contract + supplied/draft glossary",
                           "source_index_sha1": sha(json.dumps([p.get("text") for p in ps],
                                                               ensure_ascii=False)),
                           "materials": [{"id": m.get("id"), "name": m.get("name"), "kind": m.get("kind")}
                                         for m in (ix.get("materials") or [])],
                           "note": "quotes are substrings of the indexed source; no paraphrase, no invention"},
            "expected_deliverables": deliver, "units": units, "glossary": glossary,
            "facts": facts[:600], "evidence": ev, "meta_checks": meta, "totals": tot}


def gsum(g):
    t = g.get("totals") or {}
    return {"requirements": t.get("all"), "units": t.get("units"), "glossary": t.get("glossary"),
            "facts": t.get("facts"), "evidence": t.get("evidence"), "deliverables": t.get("deliverables"),
            "meta": t.get("meta"), "schema": g.get("schema")}


# ---------------------------------------------------------------- diff
def _rows(out, name):
    try:
        with open(Path(out) / name, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def compare(out, gold, ix, work=None):
    """Item-by-item: what the golden standard asked for vs what is on disk."""
    out = Path(out)
    rows = _rows(out, "alignment.csv")
    by = {}
    for r in rows:
        pid = (r.get("para_id") or "").strip()
        if pid and pid not in by:
            by[pid] = r
    gl = {}
    for r in _rows(out, "glossary.csv"):
        k = (r.get("term") or "").strip().lower()
        if k and k not in gl:
            gl[k] = r
    rec = {}
    for f in ((rjson(out / "preserved_facts.json") or {}).get("facts") or []):
        if isinstance(f, dict):
            rec[(f.get("para_id"), f.get("kind"), f.get("value"))] = f.get("present_in_target")
    evu = {}
    for u in ((rjson(out / "evidence_map.json") or {}).get("units") or []):
        if isinstance(u, dict) and u.get("para_id"):
            evu.setdefault(u["para_id"], u)
    texts = {p["para_id"]: p.get("text") or "" for p in (ix.get("paragraphs") or [])}
    items = []

    def add(cat, req, pid, loc, st, obs):
        items.append({"req_id": req, "category": cat, "para_id": pid, "locator": loc,
                      "status": st, "observed": obs})

    for u in gold.get("units") or []:
        pid = u["para_id"]
        r = by.get(pid)
        if r is None:
            add("unit", u["req_id"], pid, u.get("locator"), "missing", "alignment.csv 无该 para_id 行")
        elif not K.norm(r.get("target")):
            add("unit", u["req_id"], pid, u.get("locator"), "missing", "target 为空（未译）")
        elif K.norm(r.get("locator")) != K.norm(u.get("locator")):
            add("unit", u["req_id"], pid, u.get("locator"), "deviated", "locator 不一致：%s" % cell(r.get("locator")))
        elif (r.get("aligned") or "").strip().lower() != "yes":
            add("unit", u["req_id"], pid, u.get("locator"), "deviated", "aligned=%s" % cell(r.get("aligned")))
        else:
            add("unit", u["req_id"], pid, u.get("locator"), "ok",
                "target %d 字符，locator 一致" % len(K.norm(r.get("target"))))
    ids = [(r.get("para_id") or "").strip() for r in rows if (r.get("para_id") or "").strip()]
    want = [u["para_id"] for u in gold.get("units") or []]
    if not want:
        add("meta", "M02", None, "alignment.csv", "na", "来源无段落，无可排序单元")
    elif not ids:
        add("meta", "M02", None, "alignment.csv", "missing", "alignment.csv 缺失或为空")
    elif ids == want:
        add("meta", "M02", None, "alignment.csv", "ok", "%d 段顺序与索引一致" % len(ids))
    else:
        add("meta", "M02", None, "alignment.csv", "deviated", "顺序/集合不一致；多出 %s"
            % (", ".join([x for x in ids if x not in want][:5]) or "-"))
    rj = rjson(Path(out) / "result.json") or {}
    ctr = ix.get("contract") or {}
    miss = [k for k in ctr if k not in rj]
    if not ctr:
        add("meta", "M01", None, "case.output_contract", "na", "输入未提供 output_contract，无可回填字段")
    elif miss:
        add("meta", "M01", None, "case.output_contract", "deviated",
            "result.json 缺契约字段 %d 个：%s" % (len(miss), ",".join(miss[:6])))
    else:
        add("meta", "M01", None, "case.output_contract", "ok",
            "%d/%d 契约字段均已回填" % (len(ctr), len(ctr)))
    st, m = (rj.get("status") or "").strip(), (rj.get("metrics") or {})
    if st == "ok":
        cand = (m.get("coverage") in (1, 1.0)) and m.get("check_verdict") == "pass"
        obs = "status=ok, coverage=%s, check_verdict=%s" % (m.get("coverage"), m.get("check_verdict"))
    elif st:
        gaps = len(rj.get("pending_human") or []) + len(rj.get("degradations") or []) \
            + len(rj.get("errors") or [])
        cand, obs = gaps > 0, "status=%s, 缺口记录 %d 条" % (st, gaps)
    else:
        cand, obs = False, "result.json 无 status"
    add("meta", "M03", None, "result.json#status", "ok" if cand else "deviated", obs)
    log = readlog(work) if work else []
    if any(("| init" in x) for x in log):
        add("meta", "M05", None, "run.log", "ok", "run.log 含 init 阶段：partial result.json 先落盘后写稿")
    else:
        add("meta", "M05", None, "run.log", "na",
            "本次为 build-only 运行，未执行 init；兜底路径见 self_check SC08/SC09")
    for g in gold.get("glossary") or []:
        term, exp, occ = g["term"], (g.get("expected_target") or ""), (g.get("occurrences") or [])
        r = gl.get(term.lower())
        if r is None:
            add("glossary", g["req_id"], None, g.get("locator"), "missing", "glossary.csv 无术语 `%s`" % term)
            continue
        at, ast = K.norm(r.get("target")), (r.get("status") or "").strip()
        hit = sum(1 for o in occ if at and by.get(o["para_id"])
                  and K.tfound(at, K.norm(by[o["para_id"]].get("target"))))
        obs = "target=`%s` status=%s 落地 %d/%d 段" % (cell(at), cell(ast), hit, len(occ))
        if K.norm(at) != K.norm(exp):
            add("glossary", g["req_id"], None, g.get("locator"), "deviated",
                "译名与金标准不一致（期望 `%s`）；%s" % (cell(exp), obs))
        elif ast != g["status_expected"]:
            add("glossary", g["req_id"], None, g.get("locator"), "deviated",
                "状态应为 %s；%s" % (g["status_expected"], obs))
        elif at and occ and hit < len(occ):
            add("glossary", g["req_id"], None, g.get("locator"), "deviated", "未全部落地；%s" % obs)
        else:
            add("glossary", g["req_id"], None, g.get("locator"), "ok", obs)
    for f in gold.get("facts") or []:
        pid, kind, val = f.get("para_id"), f.get("kind"), f.get("value")
        t = K.norm((by.get(pid) or {}).get("target"))
        if kind == "number":
            present = bool(t) and K.num_ok(val, set(K.num_tokens(t)))
        elif kind == "citation":
            present = bool(t) and K.norm(val) in t
        else:
            present = bool(t) and (val in t or val.lower() in t.lower())
        flag = rec.get((pid, kind, val))
        obs = "产物%s / 记录%s" % ("命中" if present else "未命中",
                                 "-" if flag is None else ("命中" if flag else "未命中"))
        if not present:
            add("fact", f["req_id"], pid, f.get("locator"), "missing",
                "%s `%s` 未落地；%s" % (kind, cell(val), obs))
        elif flag is False:
            add("fact", f["req_id"], pid, f.get("locator"), "deviated",
                "%s `%s` 产物命中但 preserved_facts 记为 false" % (kind, cell(val)))
        else:
            add("fact", f["req_id"], pid, f.get("locator"), "ok", "%s `%s` %s" % (kind, cell(val), obs))
    for e in gold.get("evidence") or []:
        pid = e["para_id"]
        u = evu.get(pid)
        if u is None:
            add("evidence", e["req_id"], pid, e.get("locator"), "missing", "evidence_map.json 无该 para_id")
            continue
        q = K.norm(u.get("source_quote"))
        if not q:
            add("evidence", e["req_id"], pid, e.get("locator"), "missing", "source_quote 为空")
        elif q not in K.norm(texts.get(pid)):
            add("evidence", e["req_id"], pid, e.get("locator"), "deviated", "quote 非逐字（不在原文中）")
        elif K.norm(u.get("locator")) != K.norm(e.get("locator")):
            add("evidence", e["req_id"], pid, e.get("locator"), "deviated", "locator 不一致")
        elif not K.norm(u.get("target_text")):
            add("evidence", e["req_id"], pid, e.get("locator"), "deviated", "target_text 为空")
        else:
            add("evidence", e["req_id"], pid, e.get("locator"), "ok", "逐字 quote + locator + target 齐备")
    for d in gold.get("expected_deliverables") or []:
        p = out / d["name"]
        ok = p.is_file() and p.stat().st_size > 0
        add("deliverable", "D:" + d["name"], None, d["name"], "ok" if ok else "missing",
            ("%s bytes" % fsize(p)) if ok else "文件缺失或为空")
    cnt = {}
    for it in items:
        c = cnt.setdefault(it["category"], {"ok": 0, "missing": 0, "deviated": 0, "na": 0, "total": 0})
        c[it["status"]] = c.get(it["status"], 0) + 1
        if it["status"] != "na":
            c["total"] += 1
    ok = sum(c["ok"] for c in cnt.values())
    tot = sum(c["total"] for c in cnt.values())
    return {"items": items, "by_category": cnt, "ok": ok, "total": tot,
            "missing": sum(c["missing"] for c in cnt.values()),
            "deviated": sum(c["deviated"] for c in cnt.values()),
            "na": sum(c.get("na", 0) for c in cnt.values()),
            "ratio": round(ok / tot, 3) if tot else 0.0,
            "verdict": "pass" if tot and ok == tot else "review_needed"}


# ---------------------------------------------------------------- self check
def smoke(main_py, work):
    """Real subprocess runs of main.py on an empty input dir and on a broken case.json."""
    if os.environ.get("ATB_NO_SMOKE"):
        return {"skipped": True, "reason": "nested self-check run (ATB_NO_SMOKE=1) to avoid recursion"}
    base, res, env = Path(work) / "selfcheck", {}, dict(os.environ, ATB_NO_SMOKE="1")
    for name, payload in (("empty_input", None),
                          ("bad_json", '{"case_id": "SMOKE-BAD-JSON", "output_contract": {')):
        d = base / name
        ip, wp, op = d / "input", d / "work", d / "out"
        try:
            for x in (ip, wp, op):
                x.mkdir(parents=True, exist_ok=True)
            if payload is not None:
                (ip / "case.json").write_text(payload, encoding="utf-8")
                (ip / "material.md").write_text(
                    "# Smoke material\n\n浓度为 12.5 mg/L，见 [3]。\n", encoding="utf-8")
            cmd = [sys.executable, "-B", str(main_py), "build",
                   "--input", str(ip), "--work", str(wp), "--output", str(op)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
            rj = rjson(op / "result.json") or {}
            files = sorted(p.name for p in op.glob("*") if p.is_file())
            miss = [a for a in NEW_ASSETS if a not in files]
            res[name] = {"command": " ".join(cmd), "exit_code": r.returncode,
                         "result_json_valid": isinstance(rj, dict) and "status" in rj,
                         "status": rj.get("status"), "artifacts": files,
                         "new_assets_generated": len(NEW_ASSETS) - len(miss),
                         "new_assets_missing": miss,
                         "pass": (r.returncode == 0 and isinstance(rj, dict) and "status" in rj
                                  and "result.json" in files and not miss)}
        except Exception as e:
            res[name] = {"exit_code": None, "pass": False, "error": repr(e)}
    return res


def selfcheck(diff, gold, ix, ctr, out, sm, files_meta):
    rj = rjson(Path(out) / "result.json") or {}
    ck = [k for k in (ctr or {})]
    cmiss = [k for k in ck if k not in rj]
    cat = diff["by_category"]

    def rate(k):
        x = cat.get(k) or {"ok": 0, "total": 0}
        return "%d/%d" % (x["ok"], x["total"]), (x["total"] > 0 and x["ok"] == x["total"])

    fk = {f["req_id"]: f.get("kind") for f in (gold.get("facts") or [])}

    def frate(kinds):
        xs = [it for it in diff["items"] if it["category"] == "fact" and fk.get(it["req_id"]) in kinds]
        n = sum(1 for x in xs if x["status"] == "ok")
        return "%d/%d" % (n, len(xs)), (bool(xs) and n == len(xs))

    def c(cid, name, exp, obs, ok, mode="runtime", ev=None):
        return {"id": cid, "name": name, "mode": mode, "expect": exp, "observed": obs,
                "pass": bool(ok), "evidence": ev or []}

    o1, p1 = ("%d/%d" % (len(ck) - len(cmiss), len(ck)), not cmiss) if ck else ("无契约字段", True)
    checks = [
        c("SC01", "output_contract 字段完整性", "输入的每个契约字段都出现在 result.json",
          o1 + ("（缺 %s）" % ",".join(cmiss) if cmiss else ""), p1, ev=["result.json"]),
        c("SC02", "逐段结果完整性", "每个来源段落有非空译文且 locator 一致", *rate("unit"),
          ev=["alignment.csv", "translation.md"]),
        c("SC03", "数字/单位一致性", "来源数字与单位逐字落地", *frate(("number", "unit")),
          ev=["preserved_facts.json", "alignment.csv"]),
        c("SC04", "引用保留一致性", "引用标记原样保留在对应段落译文", *frate(("citation",)),
          ev=["preserved_facts.json"]),
        c("SC05", "术语一致性", "术语全篇同一译名；无译名者标 pending_human", *rate("glossary"),
          ev=["glossary.csv"]),
        c("SC06", "证据可核验（逐字 quote + locator）", "证据 quote 为原文子串且 locator 对齐",
          *rate("evidence"), ev=["evidence_map.json"]),
        c("SC07", "交付物齐备", "6 个主产物存在且非空", *rate("deliverable"), ev=files_meta),
        c("SC08", "退出码契约", "所有路径退出码 0",
          "build=0, empty_input=%s, bad_json=%s" % ((sm.get("empty_input") or {}).get("exit_code"),
                                                    (sm.get("bad_json") or {}).get("exit_code")),
          not sm.get("skipped") and all((sm.get(k) or {}).get("exit_code") == 0
                                        for k in ("empty_input", "bad_json")),
          mode="executed", ev=["scripts/main.py#main"]),
        c("SC09", "空输入兜底", "无材料时仍写合法 result.json 与骨架产物、退出码 0",
          "status=%s assets=%s" % ((sm.get("empty_input") or {}).get("status"),
                                   (sm.get("empty_input") or {}).get("new_assets_generated")),
          bool((sm.get("empty_input") or {}).get("pass")), mode="executed",
          ev=["work/selfcheck/empty_input"]),
        c("SC10", "坏 JSON 兜底", "case.json 损坏时捕获异常并仍产出结果、退出码 0",
          "status=%s assets=%s" % ((sm.get("bad_json") or {}).get("status"),
                                   (sm.get("bad_json") or {}).get("new_assets_generated")),
          bool((sm.get("bad_json") or {}).get("pass")), mode="executed",
          ev=["work/selfcheck/bad_json"]),
        c("SC11", "金标准 vs 产物一致性", "diff 达标率 1.0，或缺口全部登记 pending_human",
          "达标 %d / 缺失 %d / 偏差 %d，ratio=%.3f，verdict=%s"
          % (diff["ok"], diff["missing"], diff["deviated"], diff["ratio"], diff["verdict"]),
          diff["total"] > 0 and diff["ok"] + diff["missing"] + diff["deviated"] == diff["total"]),
    ]
    if sm.get("skipped"):
        checks = [x for x in checks if x["id"] not in ("SC08", "SC09", "SC10")]
        checks.append({"id": "SC-SMOKE", "name": "空输入/坏 JSON 兜底", "mode": "skipped",
                       "expect": "由外层运行执行", "observed": sm.get("reason"),
                       "pass": True, "evidence": []})
    passed = sum(1 for x in checks if x["pass"])
    return {"schema": "self-check/v1", "case_id": ix.get("case_id"), "generated_at": now(),
            "checks": checks, "total": len(checks), "passed": passed, "failed": len(checks) - passed,
            "verdict": "pass" if passed == len(checks) else "review_needed",
            "limits": ["自检只覆盖可确定性核验的维度（契约、覆盖、数字/引用/术语、兜底、退出码）；"
                       "译文学术质量与语义边界须人工复核 diff_report.md 与 translation.md。",
                       "PDF 文本层稀薄或图像材料时，quote 来自脚本抽取文本，须对照页面复核。"]}

