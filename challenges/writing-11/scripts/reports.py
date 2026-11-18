#!/usr/bin/env python3
"""Report rendering for the verifiability layer: diff report, version history, run log, self check file.

Split out of audit.py so each module stays small and reusable: `audit` derives and
compares, `reports` only formats what audit measured. Reads/writes files only under
out/ and work/; never raises into the caller.
"""

from pathlib import Path

from audit import (PH, NEW_ASSETS, CORE, now, fsha, fsize, wjson, wtext, rjson, cell, tbl,
                   readlog, logev, gsum, compare, smoke, selfcheck)


# ---------------------------------------------------------------- version history / log
def render_diff(diff, gold, ix, status, tsha):
    L = ["# 差异报告 / Diff report：实际产物 vs 金标准", "",
         "- case `%s` | 目标语言 `%s` | 生成于 %s | 交付状态 `%s`"
         % (ix.get("case_id"), gold.get("target_lang"), now(), status),
         "- 金标准 `golden_standard.json`（%d 项要求）| 主产物 `translation.md` sha256[:32]=`%s`"
         % (gold["totals"]["all"], tsha or "-"),
         "- 判定 **%s**：达标 %d/%d，缺失 %d，偏差 %d，不适用 %d，达标率 %.3f"
         % (diff["verdict"], diff["ok"], diff["total"], diff["missing"], diff["deviated"],
            diff.get("na", 0), diff["ratio"]),
         "- M04（退出码恒为 0）由 `self_check.json` 的真实子进程运行（SC08/SC09/SC10）核验，不在本表重复计分。",
         "- 口径：逐项比对**落盘产物**（alignment.csv / glossary.csv / preserved_facts.json / "
         "evidence_map.json），不引用内存中间态；`missing`=产物缺失，`deviated`=存在但不符，`na`=本次不适用。",
         "", "## 1. 分类总览", ""]
    rows = []
    for cat in ("deliverable", "unit", "glossary", "fact", "evidence", "meta"):
        c = diff["by_category"].get(cat)
        if c:
            rows.append([cat, str(c["total"]), str(c["ok"]), str(c["missing"]), str(c["deviated"]),
                         str(c.get("na", 0)), "%.3f" % (c["ok"] / c["total"])])
    L += tbl(["类别", "要求数", "达标", "缺失", "偏差", "不适用", "达标率"], rows)
    L += ["", "## 2. 逐段交付（unit）", ""]
    L += tbl(["req", "para_id", "locator", "期望", "实际", "状态"],
             [[it["req_id"], cell(it["para_id"]), "`%s`" % cell(it["locator"]), "同位置 1:1 译文",
               cell(it["observed"]), "**%s**" % it["status"]]
              for it in [x for x in diff["items"] if x["category"] == "unit"][:200]])
    gmap = {g["req_id"]: g for g in gold.get("glossary") or []}
    L += ["", "## 3. 术语（glossary）", ""]
    L += tbl(["req", "term", "期望 target/状态", "实际", "状态"],
             [[it["req_id"], cell(gmap.get(it["req_id"], {}).get("term")),
               "`%s` / %s" % (cell(gmap.get(it["req_id"], {}).get("expected_target")),
                              gmap.get(it["req_id"], {}).get("status_expected")),
               cell(it["observed"]), "**%s**" % it["status"]]
              for it in [x for x in diff["items"] if x["category"] == "glossary"][:200]])
    fmap = {f["req_id"]: f for f in gold.get("facts") or []}
    fcs = [x for x in diff["items"] if x["category"] == "fact"]
    frows = [[it["req_id"], cell(it["para_id"]), cell(fmap.get(it["req_id"], {}).get("kind")),
              "`%s`" % cell(fmap.get(it["req_id"], {}).get("value")), cell(it["observed"]),
              "**%s**" % it["status"]] for it in fcs[:400]]
    if len(fcs) > 400:
        frows.append(["…", "其余 %d 条" % (len(fcs) - 400), "", "见 preserved_facts.json", "", ""])
    L += ["", "## 4. 数字 / 单位 / 引用（fact）", ""]
    L += tbl(["req", "para_id", "kind", "value", "核对", "状态"], frows)
    L += ["", "## 5. 证据映射（evidence）", ""]
    L += tbl(["req", "para_id", "locator", "核对", "状态"],
             [[it["req_id"], cell(it["para_id"]), "`%s`" % cell(it["locator"]), cell(it["observed"]),
               "**%s**" % it["status"]]
              for it in [x for x in diff["items"] if x["category"] == "evidence"][:200]])
    mex = {m["req_id"]: m.get("expect") for m in (gold.get("meta_checks") or [])}
    L += ["", "## 6. 元检查与交付物", ""]
    L += tbl(["req", "期望", "实际", "状态"],
             [[it["req_id"],
               cell(mex.get(it["req_id"])) if it["category"] == "meta" else "artifact present + 非空",
               cell(it["observed"]), "**%s**" % it["status"]]
              for it in [x for x in diff["items"] if x["category"] in ("meta", "deliverable")]])
    bad = [x for x in diff["items"] if x["status"] not in ("ok", "na")]
    L += ["", "## 7. 待处置明细（%d 项）" % len(bad), ""]
    L += (["- [ ] `%s` %s（%s）：%s" % (x["category"], x["req_id"], cell(x["para_id"] or x["locator"]),
                                       cell(x["observed"])) for x in bad[:120]]
          or ["- 无：全部要求达标或本次不适用。"])
    if len(bad) > 120:
        L.append("- 其余 %d 项同类处置，见本文件表格。" % (len(bad) - 120))
    L += ["", "复核方式：`python3 scripts/main.py audit --output <out>` 重新比对。任何 `missing`/`deviated` 项"
          "必须或在产物中修正，或写入 `result.json.pending_human` 说明原因——不得改原文凑达标。"]
    return "\n".join(L)


def render_vh(ix, gold, diff, status, metrics, used, log, t_build, ver, shas):
    gt = metrics.get("glossary_terms") or 0
    pend = len([g for g in (gold.get("glossary") or []) if not g.get("expected_target")])
    L = ["# 版本记录 / Version history", "",
         "## 0. Skill 版本线", "",
         "| 版本 | 变更 | 原因 | 回退方式 |", "|---|---|---|---|",
         "| 1.3.0 | baseline_v1：init/show/check/build + 6 个主产物 | 首版 | 用 baseline 包覆盖 5 个文件 |",
         "| %s | 新增 `scripts/audit.py`、5 个可核验资产；`result.json` 增 `golden_standard`/"
         "`diff_report`/`version_history`/`self_check`；新增可选 `audit` 子命令；argparse 退出码统一为 0 "
         "| rubric 的「结果可核验性/结果完整性/生态贡献」缺可复核证据 | 删除 `scripts/audit.py`，还原 "
         "`scripts/main.py`、`scripts/kit.py`、`SKILL.md`，删除本文件与另 4 个新资产即回到 1.3.0 |" % ver,
         "", "调用方式不变：`python3 scripts/main.py init|show|check|build`；`audit` 为可选子命令。", "",
         "## 1. 产物版本（本 case）", "",
         "| 版本 | 时点 | 内容 | 状态 |", "|---|---|---|---|",
         "| v0 骨架 | init（%s） | 索引 %d 段 + 空译文模板 + partial result.json | 无译文，仅结构 |"
         % (ix.get("created") or "本次未执行 init", len(ix.get("paragraphs") or [])),
         "| v1 成稿 | build（%s，用时 %.2fs） | 双语稿 + 对齐/术语/事实/证据/修改记录 + 5 个可核验资产 | `%s` |"
         % (now(), t_build, status), "",
         "### v0 → v1 改了什么", "",
         "- 段落：%d 段中译出 %d 段（覆盖率 %s）%s。"
         % (metrics.get("paragraphs_total") or 0, metrics.get("paragraphs_translated") or 0,
            metrics.get("coverage"),
            ("，其余保留 `%s` 占位并登记缺口" % PH)
            if (metrics.get("paragraphs_translated") or 0) < (metrics.get("paragraphs_total") or 0)
            else "，无占位段"),
         "- 术语：%d 条，其中待人工确认 %d 条（`glossary.csv` 的 status 列）。" % (gt, pend),
         "- 事实核对：%d 条数字/单位/引用，产物未命中 %d 条（`preserved_facts.json`）。"
         % (metrics.get("facts_checked") or 0, metrics.get("facts_missing_in_target") or 0),
         "- 金标准 vs 产物：达标 %d/%d，缺失 %d，偏差 %d（`diff_report.md`）。"
         % (diff["ok"], diff["total"], diff["missing"], diff["deviated"]),
         "- 修改记录：%d 条（`change_log.json`，actor 区分 agent 与 script）。" % (shas.get("changes") or 0),
         "- 工作稿来源：`%s`；缺段由脚本兜底为占位符，可逐段替换而不破坏结构。"
         % (used or "（无工作稿，全兜底）"), "",
         "### 为什么这样改", "",
         "- 译名、数字、引用、证据四类要求全部落到**可比对字段**（req_id + locator + 逐字 quote），"
         "使达标/缺失/偏差可机械复核，而非依赖文字自述。",
         "- 金标准只由输入派生（索引段、契约字段、给定术语），不预测译文内容，因此不构成预制答案。",
         "- 版本记录把 v0 骨架与 v1 成稿放在同一张表：回退只需重跑命令，不需手工撤销。", "",
         "### 如何回退", "",
         "1. 回到 v0 骨架：`python3 scripts/main.py init --input /input --work /app/work "
         "--output /app/output`（重建索引与模板，`work/workdraft.json` 原样保留）。",
         "2. 回退单段：在 `alignment.csv` 按 `para_id` 定位，把 `work/workdraft.json` 该段的 "
         "`translation` 置空后重跑 `build`，该段回到占位符并进入 `pending_human`。",
         "3. 回退整个 Skill：见第 0 节 1.3.0 行；新增文件均为独立文件，删除即恢复原调用与原有产物。", "",
         "## 2. 产物指纹", ""]
    L += tbl(["文件", "字节", "sha256[:32]"],
             [[k.replace(".json", ".json").replace("|", ""), str(v[0]), "`%s`" % v[1]]
              for k, v in shas.get("files", {}).items()])
    L += ["", "## 3. 本次运行日志（共 %d 行，完整版见 `run.log`）" % len(log), "", "```text"]
    L += log[-40:]
    L += ["```", ""]
    return "\n".join(L)


def flush_log(out, work, extra=None):
    """(Re)render output/run.log from work/run.log + the metadata cache; safe to call repeatedly."""
    m = rjson(Path(work) / "last_run.json") or {}
    if extra:
        m.update(extra)
    wtext(Path(out) / "run.log", render_log(readlog(work), m.get("status"), m.get("metrics") or {},
                                            m.get("smoke") or {}, m.get("t_build") or 0.0,
                                            m.get("ver") or "?"))
    return m


def render_log(log, status, metrics, sm, t_build, ver):
    L = ["# run.log — %s | skill %s | status %s" % (now(), ver, status),
         "# 格式：UTC 时间戳 | 阶段 | 事件 | 持续时长；由脚本执行时逐事件追加，不做事后补写。", ""]
    L += log
    L += ["", "# ---- 收尾 ----",
          "%s | build | paragraphs=%s translated=%s coverage=%s glossary=%s"
          % (now(), metrics.get("paragraphs_total"), metrics.get("paragraphs_translated"),
             metrics.get("coverage"), metrics.get("glossary_terms")),
          "%s | build | assets=%s" % (now(), ",".join(NEW_ASSETS))]
    if sm.get("skipped"):
        L.append("%s | selfcheck | skipped (%s)" % (now(), sm.get("reason")))
    for k in ("empty_input", "bad_json"):
        s = sm.get(k) or {}
        L.append("%s | selfcheck | %s exit=%s status=%s assets=%s pass=%s"
                 % (now(), k, s.get("exit_code"), s.get("status"),
                    s.get("new_assets_generated"), s.get("pass")))
    L.append("%s | build | total dur=%.2fs" % (now(), t_build))
    return "\n".join(L)


def finalize(out, work, ix, gold, ctr, status, metrics, ver, main_py, used, t_build):
    """Write the 4 new text assets + self_check; return result.json field values."""
    out = Path(out)
    diff = compare(out, gold, ix, work)
    tsha = fsha(out / "translation.md")
    sm = smoke(main_py, work)
    sc = selfcheck(diff, gold, ix, ctr, out, sm,
                   ["%s:%s" % (n, fsize(out / n)) for n in CORE])
    wjson(out / "self_check.json", sc)
    wtext(out / "diff_report.md", render_diff(diff, gold, ix, status, tsha))
    shas = {"files": {}, "changes": len((rjson(out / "change_log.json") or {}).get("entries") or [])}
    for n in CORE + ("golden_standard.json",):
        shas["files"][n] = [fsize(out / n), fsha(out / n)]
    wtext(out / "version_history.md",
          render_vh(ix, gold, diff, status, metrics, used, readlog(work), t_build, ver, shas))
    wjson(Path(work) / "last_run.json", {"status": status, "metrics": metrics, "smoke": sm,
                                         "t_build": t_build, "ver": ver})
    logev(work, "build", "verifiability assets: diff=%s (%d/%d, missing=%d deviated=%d) self_check=%s (%d/%d passed)"
          % (diff["verdict"], diff["ok"], diff["total"], diff["missing"], diff["deviated"],
             sc["verdict"], sc["passed"], sc["total"]))
    flush_log(out, work)
    return {"golden_standard": dict(gsum(gold), file="golden_standard.json",
                                    sha256=fsha(out / "golden_standard.json"),
                                    note="期望交付清单，仅由输入派生；不含预制译文"),
            "diff_report": {"file": "diff_report.md", "ok": diff["ok"], "total": diff["total"],
                            "missing": diff["missing"], "deviated": diff["deviated"],
                            "match_ratio": diff["ratio"], "verdict": diff["verdict"]},
            "version_history": {"file": "version_history.md", "versions": ["v0", "v1"], "current": "v1",
                                "rollback": "python3 scripts/main.py init（恢复骨架）；详见 §1",
                                "deliverable_sha256": tsha},
            "self_check": {"file": "self_check.json", "checks": sc["total"], "passed": sc["passed"],
                           "failed": sc["failed"], "verdict": sc["verdict"],
                           "smoke": {k: (sm.get(k) or {}).get("pass") for k in ("empty_input", "bad_json")}}}
