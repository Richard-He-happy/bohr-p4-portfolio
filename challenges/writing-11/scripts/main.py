#!/usr/bin/env python3
"""Academic translation / bilingual-writing toolkit. Stdlib only, CWD-independent, always exit 0.

  init   scan input, index source paragraphs with locators, write partial result.json
  show   print source paragraphs with locators so the Agent reads the real text
  check  validate the Agent work draft (coverage, verbatim quotes, numbers, terms)
  build  assemble deliverables + finalize result.json (deterministic fallback)
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit as K
import audit as AU
import reports as RP

V = "1.4.0"
PH = "[待译 / PENDING TRANSLATION]"
T0 = time.time()


def pair_of(ix, draft, f):
    s = "\n".join(p["text"] for p in ix.get("paragraphs", [])[:20])
    r = K.cjk_ratio(s)
    src = "zh" if r > 0.2 else ("en" if r < 0.02 else "mixed")
    ins = str(f.get("instruction") or "") + " " + json.dumps(f.get("scope") or "", ensure_ascii=False)
    t = (draft or {}).get("target_lang") or ("zh" if re.search(r"中文|chinese", ins, re.I) else
                                            ("en" if re.search(r"英文|english", ins, re.I) else None))
    t = t or ("en" if src == "zh" else "zh")
    return src, (t if t != src else ("en" if src == "zh" else "zh"))


def emit(ix, items, gl, pr, st, notes, out, name):
    """translation.md + alignment.csv + glossary.csv + preserved_facts.json + evidence_map.json."""
    s, t = pr
    ps = ix.get("paragraphs", [])
    L = ["# 双语对照译文 / Bilingual translation", "",
         "- case `%s` | %s -> %s | status **%s** | units %d | glossary %d" % (ix.get("case_id"), s, t, st, len(ps), len(gl)),
         "- 逐段以 para_id / locator 对齐；数字、单位、引用标记与专名逐字保留；Source 为逐字摘录。", "",
         "## 术语表 / Glossary", "", "| term | target | locator | note |", "|---|---|---|---|"]
    L += ["| %s | %s | %s | %s |" % tuple((g.get(k) or "").replace("|", "\\|")
                                          for k in ("term", "target", "locator", "note")) for g in gl] \
        or ["| - | - | - | 未提供术语表（见 pending_human） |"]
    L += ["", "## 逐段对照 / Alignment", ""]
    rows, facts, ev = [], [], []
    for p in ps:
        it = items.get(p["para_id"], {})
        tr = (it.get("translation") or "").strip()
        L += ["### %s · %s · `%s`" % (p["para_id"], p.get("kind"), p.get("locator")), "",
              "**Source [%s]**" % p.get("material_name"), ""] + ["> " + x for x in (p.get("text") or "").split("\n")]
        L += ["", "**Target [%s]**" % t, "", tr or PH]
        L += ["", "_note: %s_" % it["note"]] if it.get("note") else []
        L.append("")
        nums = list(dict.fromkeys(K.num_tokens(p.get("text", ""))))
        tnum = set(K.num_tokens(tr))
        okn = {n: K.num_ok(n, tnum) for n in nums}
        cits = list(dict.fromkeys(K.CIT.findall(p.get("text", ""))))
        rows.append({"para_id": p["para_id"], "material": p.get("material_name"), "locator": p.get("locator"),
                     "kind": p.get("kind"), "source": p.get("text", ""), "target": tr,
                     "aligned": "yes" if tr else "missing_target",
                     "numbers_missing": ";".join(n for n in nums if not okn[n]),
                     "terms": ";".join(g["term"] for g in gl if g.get("term")
                                       and g["term"].lower() in (p.get("text") or "").lower())})
        facts += [{"fact_id": "F-%s-%s" % (p["para_id"], n.replace(".", "_")), "para_id": p["para_id"],
                   "kind": "number", "value": n, "present_in_target": okn[n], "locator": p.get("locator"),
                   "source_quote": p.get("text", "")[:200]} for n in nums]
        facts += [{"fact_id": "F-%s-cite-%s" % (p["para_id"], re.sub(r"\W+", "", c)[:12]), "para_id": p["para_id"],
                   "kind": "citation", "value": c, "present_in_target": c in tr, "locator": p.get("locator"),
                   "source_quote": p.get("text", "")[:200]} for c in cits]
        ev.append({"id": "E-%s" % p["para_id"], "kind": "translation_unit", "para_id": p["para_id"],
                   "locator": p.get("locator"), "source_quote": p.get("text", ""), "target_text": tr,
                   "terms": [g["term"] for g in gl if g.get("term")
                             and g["term"].lower() in (p.get("text") or "").lower()],
                   "derivation": "Agent read this verbatim source paragraph and wrote the target unit"})
    if notes:
        L += ["## 交付备注 / Notes", ""] + ["- " + n for n in notes] + [""]
    K.wtext(out / name, "\n".join(L))
    with open(Path(out) / "alignment.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["para_id", "material", "locator", "kind", "source", "target",
                                           "aligned", "numbers_missing", "terms"])
        w.writeheader()
        w.writerows(rows)
    with open(Path(out) / "glossary.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["term", "target", "locator", "note", "status"])
        w.writeheader()
        for g in gl:
            w.writerow({"term": g.get("term", ""), "target": g.get("target", ""), "locator": g.get("locator", ""),
                        "note": g.get("note", ""), "status": "locked" if g.get("target") else "pending_human"})
    K.wjson(Path(out) / "preserved_facts.json", {"case_id": ix.get("case_id"), "count": len(facts), "facts": facts})
    K.wjson(Path(out) / "evidence_map.json", {"case_id": ix.get("case_id"), "count": len(ev), "units": ev})
    return {"deliverable": name, "alignment": "alignment.csv", "glossary": "glossary.csv",
            "preserved_facts": "preserved_facts.json", "evidence_map": "evidence_map.json"}, facts


def changelog(draft, ix, out, auto):
    ent = []
    for i, c in enumerate((draft or {}).get("change_log") or (draft or {}).get("changes") or [], 1):
        if isinstance(c, dict):
            ent.append({"id": c.get("id") or "C%03d" % i, "para_id": c.get("para_id"),
                        "action": c.get("action") or "translate",
                        "original_quote": c.get("original_quote") or c.get("source_quote"),
                        "revised_quote": c.get("revised_quote") or c.get("translation"),
                        "reason": c.get("reason") or "", "locator": c.get("locator"),
                        "actor": c.get("actor") or "agent"})
        elif isinstance(c, str):
            ent.append({"id": "C%03d" % i, "para_id": None, "action": "note", "original_quote": None,
                        "revised_quote": None, "reason": c, "locator": None, "actor": "agent"})
    ent += [{"id": "A%03d" % i, "para_id": None, "action": "auto_fill", "original_quote": None,
             "revised_quote": None, "reason": n, "locator": None, "actor": "script"} for i, n in enumerate(auto, 1)]
    K.wjson(Path(out) / "change_log.json", {"case_id": ix.get("case_id"), "count": len(ent), "entries": ent})
    return ent


def cmd_init(a):
    d, work, out = K.dirs(a)
    for x in (work, out):
        x.mkdir(parents=True, exist_ok=True)
    case, cpath = K.find_case(d)
    f = K.fields(case or {})
    cid, ctr, errs = str(f.get("case_id") or "unknown"), f.get("contract") or {}, []
    if cpath and not case:
        errs.append("case json unreadable: %s" % cpath)
    r = K.blank(cid, ctr, "partial", V)  # legal partial result lands before any real work
    r["note"] = "index not built yet"
    r["runtime"] = {"skill_version": V, "python": sys.version.split()[0], "started": K.now()}
    K.save_result(out, r, errs)
    AU.logev(work, "init", "start: input=%s work=%s output=%s" % (d, work, out))
    ix = K.index_input(d, case or {}, f)
    ix["case_id"] = cid
    K.wjson(work / "index.json", ix)
    if not ix["paragraphs"]:
        errs.append("no readable material paragraphs found under %s" % d)
    K.wjson(work / "workdraft.template.json", {"case_id": cid, "target_lang": None, "glossary": [], "change_log": [],
             "paragraphs": [{"para_id": p["para_id"], "kind": p["kind"], "locator": p["locator"],
                             "source_quote": p["text"][:400], "translation": "", "note": ""} for p in ix["paragraphs"]]})
    r.update({"sources": [{k: m.get(k) for k in ("id", "name", "path", "kind", "quality")} for m in ix["materials"]],
              "errors": errs, "degradations": ix["warnings"],
              "pending_human": [{"item": m["name"], "reason": m.get("note")} for m in ix["materials"]
                                if m.get("quality") in ("low", "unreadable")],
              "runtime": {"skill_version": V, "python": sys.version.split()[0], "started": K.now(), "phase": "init",
                          "materials": len(ix["materials"]), "paragraphs": len(ix["paragraphs"])},
              "note": "index built; Agent writes workdraft.json next"})
    K.save_result(out, r, errs)
    AU.logev(work, "init", "index built: materials=%d paragraphs=%d contract_fields=%d terms=%d partial result.json written"
             % (len(ix["materials"]), len(ix["paragraphs"]), len(ctr or {}), len(ix["supplied_terms"])),
             dur=time.time() - T0)
    print("case_id:", cid, "| input:", d, "| work:", work, "| output:", out)
    for m in ix["materials"]:
        print("  %-3s %-30s kind=%-7s quality=%-10s chars=%-7s paras=%-4s %s" % (
            m.get("id") or "-", m.get("name"), m.get("kind"), m.get("quality"), m.get("chars"), m.get("paras"),
            m.get("note") or ""))
    print("paragraphs:", len(ix["paragraphs"]), "| contract fields:", ", ".join(ix["contract_keys"]) or "(none)",
          "| supplied terms:", len(ix["supplied_terms"]))
    print("acronym candidates:", ", ".join(t["term"] for t in ix["term_candidates"][:12]) or "(none)")
    if ix["warnings"]:
        print("warnings:", "; ".join(ix["warnings"][:5]))
    print("\nNEXT: read the real source (show --para ... or open the files), then write %s/workdraft.json" % work)
    print('  {"case_id":"...","target_lang":"zh|en","glossary":[{"term","target","locator"}],'
          '"paragraphs":[{"para_id","source_quote","translation","note"}],"change_log":[...]}')
    print("  then: check -> build")
    return 0


def cmd_show(a):
    _, work, _ = K.dirs(a)
    ix = K.rjson(work / "index.json") or {}
    sel = ix.get("paragraphs") or []
    if a.para:
        w = {x.upper() for x in " ".join(a.para).replace(",", " ").split()}
        sel = [p for p in sel if p["para_id"].upper() in w]
    if a.material:
        sel = [p for p in sel if (p.get("material") or "").upper() == a.material.upper()]
    if a.grep:
        pat = re.compile(a.grep, re.I)
        sel = [p for p in sel if pat.search(p.get("text", ""))]
    if not (a.para or a.material or a.grep or a.all):
        print("materials:", ", ".join("%s=%s" % (m.get("id"), m.get("name")) for m in ix.get("materials", [])) or "(none)")
        print("paragraphs:", len(ix.get("paragraphs") or []))
        print("usage: show --para M1-P001 | --material M1 | --grep PATTERN | --all [--max-chars N]")
        return 0
    AU.logev(work, "show", "selected %d/%d paragraphs" % (len(sel), len(ix.get("paragraphs") or [])))
    used = 0
    for i, p in enumerate(sel):
        blk = "[%s] %s (%s, %d chars)\n%s\n" % (p["para_id"], p.get("locator"), p.get("kind"), p.get("chars"), p.get("text"))
        if used + len(blk) > a.max_chars:
            print("... %d more paragraphs truncated; use --para/--material" % (len(sel) - i))
            break
        print(blk)
        used += len(blk)
    return 0


def summarize(rep):
    c = rep.get("coverage") or {}
    L = ["verdict: %s | coverage %s/%s (%s)" % (rep.get("verdict"), c.get("covered"), c.get("expected"),
                                                c.get("ratio")),
         "empty %d | quotes %d | numbers %d | cites %d | terms %d | glossary %s" % (
             len(rep.get("empty_translations") or []), len(rep.get("quote_issues") or []),
             len(rep.get("number_issues") or []), len(rep.get("citation_issues") or []),
             len(rep.get("term_issues") or []), rep.get("glossary_size"))]
    if c.get("missing_para_ids"):
        L.append("missing: " + ", ".join(c["missing_para_ids"][:20]))
    for k in ("quote_issues", "number_issues", "citation_issues", "term_issues", "unknown_para_ids"):
        for it in (rep.get(k) or [])[:6]:
            L.append("  [%s] %s" % (k[:-1], json.dumps(it, ensure_ascii=False)))
    return "\n".join(L)


def cmd_check(a):
    _, work, _ = K.dirs(a)
    ix = K.rjson(work / "index.json") or {}
    draft, used, seen = K.load_draft(work, a.draft)
    rep = K.validate(ix, draft)
    if draft is None:
        rep["notes"] = ["no draft with non-empty 'paragraphs' in %s (seen: %s)"
                        % (work, ", ".join(Path(x).name for x in seen) or "none")]
    rep["draft_path"] = used
    K.wjson(work / "check_report.json", rep)
    AU.logev(work, "check", "verdict=%s coverage=%s/%s quotes=%d numbers=%d cites=%d terms=%d glossary=%s"
             % (rep.get("verdict"), (rep.get("coverage") or {}).get("covered"),
                (rep.get("coverage") or {}).get("expected"), len(rep.get("quote_issues") or []),
                len(rep.get("number_issues") or []), len(rep.get("citation_issues") or []),
                len(rep.get("term_issues") or []), rep.get("glossary_size")))
    print(summarize(rep))
    if rep.get("verdict") != "pass":
        print("\nFix these in the draft, re-run check. `build` still runs and emits an honest partial result.")
    return 0


def cmd_build(a):
    d, work, out = K.dirs(a)
    for x in (out, work):
        x.mkdir(parents=True, exist_ok=True)
    errs, degr, auto = [], [], []
    AU.logev(work, "build", "start: input=%s work=%s output=%s" % (d, work, out))
    case, cpath = K.find_case(d)
    f = K.fields(case or {})
    if cpath and not case:
        errs.append("case json unreadable: %s" % cpath)
        AU.logev(work, "build", "degraded: case json unreadable (%s)" % cpath)
    ix = K.rjson(work / "index.json")
    if not (isinstance(ix, dict) and ix.get("paragraphs")):
        ix = K.index_input(d, case or {}, f)
        AU.logev(work, "build", "index not reused: rebuilt from input (%d paragraphs)"
                 % len(ix.get("paragraphs") or []))
    cid = str(ix.get("case_id") or f.get("case_id") or "unknown")
    ctr = f.get("contract") or ix.get("contract") or {}
    draft, used, _ = K.load_draft(work, a.draft)
    rep = K.validate(ix, draft)
    if draft is None:
        degr.append("no Agent work draft found; deterministic scaffold delivered (translation slots marked)")
        AU.logev(work, "build", "degraded: no Agent work draft -> deterministic scaffold")
    items = {it["para_id"]: it for it in (draft or {}).get("paragraphs") or []
             if isinstance(it, dict) and it.get("para_id")}
    for p in ix["paragraphs"]:
        if not K.norm((items.get(p["para_id"]) or {}).get("translation")):
            items[p["para_id"]] = {"para_id": p["para_id"], "translation": "",
                                   "note": "translation slot empty at build time"}
            auto.append("paragraph %s has no Agent translation; placeholder emitted" % p["para_id"])
    gl, seen_t = [], set()
    draft_gl = (draft or {}).get("glossary") or []
    for g in list(draft_gl) + list(ix.get("supplied_terms") or []):
        if isinstance(g, dict) and g.get("term") and g["term"].lower() not in seen_t:
            seen_t.add(g["term"].lower())
            gl.append({"term": g["term"], "target": g.get("target") or "", "note": g.get("note") or "",
                       "locator": g.get("locator") or ("" if g in draft_gl else "case.supplied_terms")})
    pr, total = pair_of(ix, draft, f), len(ix["paragraphs"])
    open_n = sum(1 for p in ix["paragraphs"] if not K.norm((items.get(p["para_id"]) or {}).get("translation")))
    status = "insufficient_evidence" if not total else (
        "partial" if (open_n or (rep.get("verdict") or "fail") == "fail") else "ok")
    notes = ["未完成单元 %d/%d；缺口见 pending_human 与 alignment.csv 的 aligned 列" % (open_n, total)] \
        if status != "ok" else []
    if not total:
        notes = ["未发现可读材料：请核对 /input 下材料路径与格式；本文件仅为结构骨架，不含译文"]
        errs.append("no readable material paragraphs under %s" % d)
    if rep.get("number_issues"):
        notes.append("数字/单位未全部落地 %d 段（preserved_facts.json present_in_target=false）"
                     % len(rep["number_issues"]))
    if rep.get("term_issues"):
        notes.append("术语不一致 %d 处（见 result.json term_issues）" % len(rep["term_issues"]))
    files, facts, ent = {}, [], []
    t_st = time.time()
    try:
        files, facts = emit(ix, items, gl, pr, status, notes, out, a.deliverable_name)
        AU.logev(work, "build", "deliverables written: %s" % ",".join(sorted(files)), dur=time.time() - t_st)
    except Exception as e:
        errs.append("deliverable build failed: %s" % e)
        degr.append("deliverable emitted as skeleton after error")
        AU.logev(work, "build", "EXCEPTION emit: %r" % (e,), dur=time.time() - t_st)
        K.wtext(out / a.deliverable_name, "# 译文 / Translation\n\n" + PH)
        files["deliverable"] = a.deliverable_name
    try:
        ent = changelog(draft, ix, out, auto)
        files["change_log"] = "change_log.json"
    except Exception as e:
        errs.append("change log build failed: %s" % e)
        AU.logev(work, "build", "EXCEPTION change_log: %r" % (e,))
    files["_facts"] = len(facts)
    files["_miss"] = sum(1 for x in facts if not x.get("present_in_target"))
    # --- verifiability patch (v1.4.0): golden standard is derived from the index/contract only
    gold = None
    t_g = time.time()
    try:
        gold = AU.golden(ix, draft, ctr, pr[1])
        AU.wjson(out / "golden_standard.json", gold)
        files.update({"golden_standard": "golden_standard.json", "diff_report": "diff_report.md",
                      "version_history": "version_history.md", "self_check": "self_check.json",
                      "run_log": "run.log"})
        AU.logev(work, "build", "golden_standard.json: %d requirements (units=%d glossary=%d facts=%d evidence=%d)"
                 % (gold["totals"]["all"], gold["totals"]["units"], gold["totals"]["glossary"],
                    gold["totals"]["facts"], gold["totals"]["evidence"]), dur=time.time() - t_g)
    except Exception as e:
        errs.append("golden standard build failed: %s" % e)
        degr.append("golden_standard.json missing; diff report degraded to file-level checks only")
        AU.logev(work, "build", "EXCEPTION golden: %r" % (e,), dur=time.time() - t_g)
    r = K.assemble(ix, rep, gl, open_n, status, files, errs, degr, ent, used, ctr, cid, V, time.time() - T0)
    for k in ("golden_standard", "diff_report", "version_history", "self_check"):
        if not isinstance(r.get(k), dict):
            r[k] = {"file": files.get(k), "status": "pending_finalize"}
    saved = K.save_result(out, r, errs)
    if gold:
        t_f = time.time()
        try:
            fin = RP.finalize(out, work, ix, gold, ctr, status, r.get("metrics") or {}, V,
                              Path(__file__).resolve(), used, time.time() - T0)
            r.update(fin)
            saved = K.save_result(out, r, errs)
            AU.logev(work, "build", "verifiability assets: diff=%s (%d/%d) self_check=%s (%d checks)"
                     % (fin["diff_report"]["verdict"], fin["diff_report"]["ok"], fin["diff_report"]["total"],
                        fin["self_check"]["verdict"], fin["self_check"]["checks"]), dur=time.time() - t_f)
        except Exception as e:
            errs.append("verifiability finalize failed: %s" % e)
            degr.append("diff_report/version_history/self_check degraded after exception")
            AU.logev(work, "build", "EXCEPTION finalize: %r" % (e,), dur=time.time() - t_f)
            for k, body in (("diff_report", "# 差异报告 / Diff report\n\n生成失败：%r\n\n"
                                            "主产物与 `golden_standard.json` 仍可用于人工比对。\n" % (e,)),
                            ("version_history", "# 版本记录 / Version history\n\n生成失败：%r\n" % (e,))):
                try:
                    K.wtext(out / (k + ".md"), body)
                    r[k] = {"file": k + ".md", "status": "degraded", "error": str(e)}
                except Exception:
                    pass
            try:
                K.wjson(out / "self_check.json", {"schema": "self-check/v1", "case_id": cid,
                                                  "verdict": "review_needed", "error": str(e), "checks": []})
                r["self_check"] = {"file": "self_check.json", "status": "degraded", "error": str(e)}
            except Exception:
                pass
            saved = K.save_result(out, r, errs)
    # deliver-then-verify: read the delivered result.json back
    try:
        chk = K.rjson(out / "result.json") or {}
        miss = [k for k in (ctr or {}) if k not in chk]
        AU.logev(work, "build", "final result.json verified on disk: contract %d/%d, keys=%d, status=%s"
                 % (len(ctr or {}) - len(miss), len(ctr or {}), len(chk), chk.get("status")))
        if miss:
            errs.append("contract keys missing after write: %s" % ",".join(miss))
            r["errors"] = errs
            saved = K.save_result(out, r, errs)
    except Exception as e:
        AU.logev(work, "build", "EXCEPTION verify: %r" % (e,))
    try:
        RP.flush_log(out, work)          # pick up the verification line written above
    except Exception as e:
        AU.logev(work, "build", "EXCEPTION run.log flush: %r" % (e,))
    print("status:", status, "| paragraphs:", total, "| translated:", total - open_n,
          "| glossary:", len(gl), "| verdict:", rep.get("verdict"))
    print("outputs:", json.dumps({k: v for k, v in files.items() if not k.startswith("_")}, ensure_ascii=False))
    if isinstance(r.get("diff_report"), dict):
        print("diff:", r["diff_report"].get("verdict"), "%s/%s" % (r["diff_report"].get("ok"),
                                                                  r["diff_report"].get("total")),
              "| self_check:", (r.get("self_check") or {}).get("verdict"))
    print("result:", str(saved) if saved else "FAILED")
    return 0


def cmd_audit(a):
    """Re-verify an existing output dir without rewriting the main deliverables."""
    d, work, out = K.dirs(a)
    for x in (out, work):
        x.mkdir(parents=True, exist_ok=True)
    case, _ = K.find_case(d)
    f = K.fields(case or {})
    ix = K.rjson(work / "index.json")
    if not (isinstance(ix, dict) and ix.get("paragraphs")):
        ix = K.index_input(d, case or {}, f)
        ix["case_id"] = str(f.get("case_id") or "unknown")
    ctr = f.get("contract") or ix.get("contract") or {}
    draft, used, _ = K.load_draft(work, a.draft)
    lang = a.target_lang or pair_of(ix, draft, f)[1]
    gold = AU.golden(ix, draft, ctr, lang)
    AU.wjson(out / "golden_standard.json", gold)
    rj = K.rjson(out / "result.json")
    if not isinstance(rj, dict):
        rj = K.blank(str(ix.get("case_id") or "unknown"), ctr, "partial", V)
    fin = RP.finalize(out, work, ix, gold, ctr, rj.get("status") or "partial",
                      rj.get("metrics") or {}, V, Path(__file__).resolve(), used, time.time() - T0)
    rj.update(fin)
    K.save_result(out, rj, rj.get("errors") or [])
    AU.logev(work, "audit", "re-verified: golden=%d diff=%s (%d/%d) self_check=%s"
             % (gold["totals"]["all"], fin["diff_report"]["verdict"], fin["diff_report"]["ok"],
                fin["diff_report"]["total"], fin["self_check"]["verdict"]), dur=time.time() - T0)
    print("audit: status", rj.get("status"), "| golden", gold["totals"]["all"], "reqs | diff",
          fin["diff_report"]["verdict"], "%s/%s" % (fin["diff_report"]["ok"], fin["diff_report"]["total"]),
          "| self_check", fin["self_check"]["verdict"])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="main.py", description="Academic translation & bilingual writing toolkit: "
                                 "init -> show -> (Agent writes workdraft.json) -> check -> build. Always exits 0.")
    ap.add_argument("--input", help="input dir (default /input)")
    ap.add_argument("--work", help="work dir (default /app/work)")
    ap.add_argument("--output", help="output dir (default /app/output)")
    common = argparse.ArgumentParser(add_help=False)
    for opt, hlp in (("--input", "input dir (default /input)"), ("--work", "work dir (default /app/work)"),
                     ("--output", "output dir (default /app/output)")):
        # SUPPRESS keeps a value given before the subcommand; the documented form
        # `main.py init --input ...` keeps working too (baseline rejected it).
        common.add_argument(opt, default=argparse.SUPPRESS, help=hlp)
    sp = ap.add_subparsers(dest="cmd")
    sp.add_parser("init", parents=[common],
                  help="scan input, index paragraphs, write partial result.json").set_defaults(func=cmd_init)
    p = sp.add_parser("show", parents=[common], help="print source paragraphs with locators")
    p.add_argument("--para", action="append", help="para_id (repeatable)")
    p.add_argument("--material", help="material id, e.g. M1")
    p.add_argument("--grep", help="regex over paragraph text")
    p.add_argument("--all", action="store_true")
    p.add_argument("--max-chars", type=int, default=24000)
    p.set_defaults(func=cmd_show)
    p = sp.add_parser("check", parents=[common], help="validate the Agent work draft")
    p.add_argument("--draft", help="explicit draft json path")
    p.set_defaults(func=cmd_check)
    p = sp.add_parser("build", parents=[common], help="assemble deliverables and finalize result.json")
    p.add_argument("--draft", help="explicit draft json path")
    p.add_argument("--deliverable-name", default="translation.md")
    p.set_defaults(func=cmd_build)
    p = sp.add_parser("audit", parents=[common], help="re-verify: rebuild golden_standard/diff_report/version_history/run.log/self_check")
    p.add_argument("--draft", help="explicit draft json path")
    p.add_argument("--target-lang", help="en|zh (default: inferred from source and instruction)")
    p.set_defaults(func=cmd_audit)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        # argparse already printed help/usage; the contract keeps the process exit code at 0
        return 0
    if not getattr(a, "func", None):
        ap.print_help()
        print("\nQuick start: init -> show -> write workdraft.json -> check -> build")
        return 0
    try:
        return a.func(a)
    except SystemExit:
        raise
    except Exception as e:
        try:
            _, _, out = K.dirs(a)
            K.wjson(out / "result.json", {"case_id": "unknown", "status": "input_error",
                                          "skill": "academic-translation-bilingual", "skill_version": V,
                                          "errors": ["unhandled: %r" % (e,)], "sources": [], "uncertainty": [],
                                          "pending_human": [], "degradations": ["command aborted"],
                                          "deliverable": None, "preserved_facts": None, "evidence_map": None,
                                          "change_log": None, "glossary": None, "alignment": None,
                                          "golden_standard": None, "diff_report": None,
                                          "version_history": None, "self_check": None,
                                          "runtime": {"finished": K.now()}})
        except Exception:
            pass
        print("ERROR (handled, exit 0): %r" % (e,))
        return 0


if __name__ == "__main__":
    sys.exit(main())
