# 03 — Rubric map, exception handling, replay and illustrative example

## 1. Rubric → artifact/field map

| Scoring point | Where it is answered |
|---|---|
| 任务完成度（订阅—窗口—比对—新增—提醒闭环） | `subscriptions[]`, `windows[]`, `deltas[]`, `new_items[]`, `alerts[]` (each alert has a delivery record) |
| 结果正确性（条目真实、本窗口新入库、元数据准确、版本合并正确） | `candidates[].doi/authors/venue/year`, `evidence_locator`, `version_chain`, `delta_class`, `checks.doi_traceable_to_input` |
| 结果完整性（窗口连续、来源覆盖、边界与延迟入库补回） | `coverage.continuity_ok/gap_count/sources_present/recovered_late_entries`, `deltas[].recovered_late` |
| 结果可核验性（配置、窗口、查询式、快照、去重键、投递记录可回放） | `snapshot.json`, `work/state.json`, `query_log.json`, `subscriptions[].dedup_keys`, `alerts[].delivery`, per-window files |
| 质量增益（同窗口同来源下新增发现质量） | `coverage.skill_metrics` vs `coverage.baseline_metrics` when a gold list exists; otherwise `null` with an explicit note |
| 效率增益（人工核对条数、重复抓取、通知噪声） | `coverage.duplicates_merged`, `coverage.repeated_push_without_snapshot`, `deltas[].suppressed` counts |
| 增益可验证性（同窗口/同快照/同调度对照） | both metric blocks are computed on the same artifacts and snapshot; `metric_note` states the comparison basis |
| 创新（增量状态、去重归一、版本链合并、提醒抑制） | `sig()` identity rule, `version_chain`, `delta_class`, `suppressed` reasons, snapshot advance |
| 可靠体验（触发、幂等、异常处置） | `--input/--output/--work` CLI, `work/state.json` idempotent rerun, `errors/degradations/uncertainty/missing`, §3 table |
| 生态贡献（文档、模板、可复用资源） | `SKILL.md` + three references + reusable snapshot/query-log formats + `core.py` standalone validator |

## 2. Exception handling table

| Input condition | Observable behaviour |
|---|---|
| `case.json` unparsable | `errors[]` entry, artifacts still parsed, `status=input_error` when no usable case |
| one artifact truncated/invalid JSON | `degradations[]` entry `artifact_issue:unparsable_json:<file>`; other files unaffected |
| no records at all | `status=insufficient_evidence`, `missing[]` names what is needed, candidates `[]` |
| record without DOI | kept, `flags: ["no_doi"]`, `metadata_confidence` drops, alert suppressed when confidence is low |
| record without any date | `undated_works` count, excluded from window decisions |
| no index/import date | publication date as proxy, `index_date_proxy` flag, `uncertainty[]` note |
| same work from two databases | merged into one work, `records_scanned > works_after_dedup`, `duplicates_merged` |
| preprint then published | one work, `version_chain` of two nodes, window 2 reports `version_update` |
| retraction/correction notice | `correction_or_retraction`, alerted once, never merged away |
| delayed indexing before window | `recovered_late`, reported as backfill instead of dropped |
| no previous snapshot | first-run baseline; `uncertainty[]` says every in-window item is new |
| rerun of the same window | `new: 0`, `alerts: 0`, duplicates counted under `suppressed` |

## 3. Commands used for verification

```bash
python3 -B scripts/main.py --help
python3 -B scripts/main.py --input ./in --output ./out --work ./work --now 2024-03-01
python3 -B scripts/core.py --input ./in --output ./out      # prints passed/failed + failing checks
```

Expected on a healthy run: `status: ok`, `checks.failed: 0`, `snapshot.json` present with
the last window end, and a second run producing zero new items.

## 4. Illustrative minimal example (示例，非正式案例结果)

A synthetic two-window fixture (not an organizer case, not a measured score):

- `case.json`: `case_id: demo-windows-002`, `windows: [{2024-01-01, 2024-02-01},
  {2024-02-01, 2024-03-01}]`, scope topic `CRISPR base editing liver delivery`.
- `artifacts/responses/w1.json`: one bioRxiv preprint, index date 2024-01-10.
- `artifacts/responses/w2.json`: the journal version of the same title (index 2024-02-20)
  plus one unrelated new paper (index 2024-02-05).

Illustrative shape of the outcome (schematic, values are the fixture's, not a benchmark):

```json
{"windows": [{"index": 0, "counts": {"new": 1, "updated": 0, "alerts": 1}},
             {"index": 1, "counts": {"new": 1, "updated": 1, "alerts": 2}}],
 "alerts": [{"window_index": 0, "class": "new", "doi": "10.1101/…"},
            {"window_index": 1, "class": "new", "doi": "10.1016/…"},
            {"window_index": 1, "class": "version_update", "doi": "10.1038/…"}],
 "coverage": {"continuity_ok": true, "gap_count": 0, "duplicates_merged": 1}}
```

What the example demonstrates: the preprint and its published version collapse into one
work with a two-node `version_chain`; window 1 reports a version update rather than a
second "new paper"; the rerun of either window produces no new items.

## 5. Known limits

- No live network: coverage equals the organizer-supplied snapshots. A missing database in
  the input is reported in `coverage.sources_present`/`missing[]`, never filled in.
- PDF binaries are not text-extracted (record metadata is expected in JSON/JSONL/CSV). A
  PDF-only seed set therefore contributes nothing and is listed under `problem_files`.
- Recall/precision are reported only when the organizer supplies a relevance list; a
  guessed recall is never emitted.
- Fuzzy title matching is limited to the `title:` key plus a shared-key union-find; two
  papers with genuinely different titles but the same work (e.g. translated titles) are not
  merged, and are surfaced as separate works with distinct DOIs.
