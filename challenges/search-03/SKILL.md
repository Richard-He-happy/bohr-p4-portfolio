---
name: search-screen-rank
description: Screen a supplied candidate set of scholarly records against a research question, assign auditable relevance tiers (core/method/background/pending/exclude), merge preprint-published duplicates, escalate conflicting annotations, and produce a deterministic explainable ranking with per-item evidence quotes, query log, coverage accounting and baseline-vs-skill metrics. Use for literature relevance judging, screening, prioritisation and review-sheet generation on an already-collected candidate set.
version: 1.0.0
---

# search-screen-rank — 文献筛选与智能排序

## 1. 用途与边界

对**已收集好的候选文献集**逐条判断相关性、分层（保留/方法参考/背景/待定/排除）、去重合并版本变体、给出可解释的确定性排序，并留下可逐条复核的证据与状态。

做：相关性判据、分层标签、排序与平局处理、重复/版本合并、冲突裁定与人工升级、逐条理由与证据引用、查询与筛选日志、覆盖与遗漏说明、基线与指标对照。

不做：数据库接入、全文阅读、系统综述纳排全流程、写作。不联网，不宣称数据库级召回。

**触发**：用户给出（或案例提供）一批候选文献/检索结果，要求"筛选、判相关、分层、排序、保留筛选依据"。输入里有 `case.json` + 候选记录即可运行。

## 2. 调用方式

```bash
python3 scripts/main.py --input /input --out /app/output        # 默认即 /input、/app/output
python3 scripts/main.py --input /input --out /app/output --k 5,10
python3 scripts/verify.py --input /input --out /app/output      # 独立复核，写 verify_report.json
```

依赖：Python ≥3.8 标准库（`json/csv/re/math/pathlib/difflib`）。无第三方包、无网络、0 次模型请求。脚本用 `Path(__file__).resolve().parent.parent` 定位 `references/`，与当前工作目录无关。

## 3. 运行契约

- 只读 `/input`；只写 `--out`（默认 `/app/output`）。
- 启动即写一份 partial `result.json`（含 `case_id`、`contract_echo`、`contract_fields`），此后任何中断都保留合法 JSON。
- `result.json` 原样回填输入 `output_contract` 全部字段：键名不改、未知字段保留、缺值 `null`/`[]`，并用 `contract_fill` / `contract_missing` 记账。
- 退出码恒为 0；异常写入 `errors`，部分完成写 `degradations`，结论不确定写 `uncertainty`，需人工定档写 `pending_human`。
- 预算：900 s / 64 次模型请求（本 Skill 消耗 0 次模型请求）；无长耗时循环，耗时随候选集规模线性增长，典型 9–50 条 < 1 s；超大输入（>5000 条）按文件顺序处理，中断时保留已落盘的 partial 结果。

## 4. 输入发现（语义识别，不假设键名）

1. `case.json`（缺失则 `case*.json`）：取 `case_id`、`output_contract`、任务说明与范围。
2. 范围字段：`organizer_supplied_scope|scope|search_scope|constraints|criteria` 内的 `topic|research_question|objective|pico`、`include*`、`exclude*`、`year_start/end`（或文本中的 `2015-2024`）、`max_k|top_k|k`、`seed_papers`。
3. 递归扫描材料：`.json`（整份解析，含 `queries`/`query_log` 即查询日志）、`.jsonl/.ndjson`、`.csv`（文件名含 `quer` 兼作查询日志）、`.pdf`（仅用文件名生成低置信记录）、`.xlsx/.docx`（不解析二进制，写入 `degradations`）。
4. 记录识别：具备类题名字段 +（DOI/摘要/关键词/年份/作者/出处/URL 任一）；兼容 ES `_source`、`results/hits/items`、`versions/duplicates` 嵌套。
5. 每条记录保留 `provenance.file` + `provenance.json_pointer`。

详见 `references/io_contract.md`。

## 5. 输出

| 文件 | 内容 |
|---|---|
| `result.json` | 契约字段 + 候选（分层/分数/理由/证据）+ 计数（`tiers`、`screening`：输入记录/候选组/合并组/有摘要数）+ `tiers/screening/metrics/conflicts` + `uncertainty/pending_human/errors/degradations` + `sources/runtime/changes` |
| `candidates.csv` | 一候选一行：rank、id、tier、decision、relevance、score、题录、DOI/URL、source_db、query_id、retrieved_at、design_fit、reason、flags、evidence_quote |
| `query_log.json` | 查询→来源→报告命中数→关联记录数→保留/待定/排除 |

`status` ∈ `ok | partial | insufficient_evidence | input_error`。

## 6. 核心流程

1. 读 case 与契约 → 立刻落盘 partial。
2. 解析范围（问题文本、纳排、年份窗、max_k、种子）与查询日志。
3. 扫描材料 → 归一化记录（题名/摘要/作者/年份/出处/DOI/URL/来源/查询/时间/标注 + 溯源）。
4. 按 DOI、归一化题名合并重复与预印本-正式版本；组内标注或年份冲突记 `conflicts`。
5. 逐条打分（见 §7）→ 分档 → 排序（平局键）→ 生成 `evidence` 逐字证据。
6. 关联查询计数、计算覆盖与（有标注时）指标与基线差值。
7. 汇总不确定性/人工项/错误/降级 → 写 `candidates.csv`、`query_log.json` → 回填契约 → 最终 `result.json`。

## 7. 相关性判据、打分与分档

分量：`coverage`（IDF 加权词项覆盖，标题 1.0/关键词 0.7/摘要 0.6 折扣，按候选集内最高覆盖做平方根归一）、`exp`（术语扩展命中，词表见 `references/label_taxonomy.md` §7）、`design_fit`（目标研究设计是否匹配）、`evidence`（摘要信息量）。

```
score = 0.42*coverage + 0.22*exp + 0.18*design_fit + 0.12*evidence
penalty: 年份越界 ×0.45 | 命中排除词 ×0.30 | 无任一纳入词 ×0.78      (≤0.99，三位小数)
```

分档（按序命中）：年份越界/排除词 → `exclude`；缺摘要或标注冲突 → `pending`；`score≥0.62 且 design_fit≥0.45` → `core`；`score≥0.50 且 design_fit≥0.45` → `method`；`score≥0.40` → `background`；其余 `exclude`。

**平局**（必须可复核）：`tier → score↓ → year↓ → 归一化题名↑ → record_id↑`；每条写 `tie_group`。
**k 值**：`k` 默认 5、10；短名单长度 = `scope.max_k`（缺省 10）；指标只用不超过带标注记录数的 k。

## 8. 证据与定位规范

- 每条候选必须带 `evidence[0].quote`：取自该记录**摘要原文**的逐字片段（缺摘要时取题名），`locator` 为 `abstract`/`title`；不润色、不改写、不拼接。
- `provenance.file` + `json_pointer` 指向原始记录；`source_db`、`query_id`、`retrieved_at` 必须能回查；输入未给抓取时间时写 `not_provided` 并打 `retrieved_at_missing`，不推断。
- 不编造文献、DOI、年份、引用或"最新进展"。`scripts/verify.py` 会把 `quote` 与重新解析的原文逐字比对。

## 9. 去重、版本与冲突

- DOI 归一（去 URL 前缀、去 `.vN`）一致即同组；否则归一化题名一致即同组。
- 组内优先取正式发表版本（预印本前缀 `10.1101/ 10.21203/ 10.48550/ 10.31219/ 10.20944/`），记 `version_resolved=published_version_preferred`，`group_ids` 保留全部成员。
- 组内标注不一致：不取多数票 → `pending` + `pending_human` + `conflicts[type=label_disagreement]`。
- 纳排词表重叠：记 `criteria_overlap`，按排除优先并在 `uncertainty` 说明。

## 10. 异常与降级

| 情形 | 处理 | 落点 |
|---|---|---|
| case.json 缺失/坏 JSON | 继续扫描材料；无记录则 `insufficient_evidence` | `errors[stage=read_case]` |
| 候选集为空 | 输出空 `candidates`，不补造 | `errors` + `uncertainty` |
| 摘要/年份/DOI 缺失 | 缺摘要→`pending`；缺年份不参与年份排除；缺 DOI 打标 | `flags`、`uncertainty` |
| 查询 429/权限/接口错误 | 保留原始 status/error | `queries[].status/error` |
| 单个文件解析失败 | 只跳过该文件 | `degradations[stage=parse]` |
| 二进制材料（xlsx/docx） | 不解析，提示导出 CSV/JSON | `degradations` |
| 大量同分 | 记录 `tie_group`，排序键兜底 | 每条 `tie_group` |
| 超大输入或运行中断 | 已处理部分保留在 partial `result.json`，异常写 `errors[stage=run]` | `errors` + `changes` |
| 内部异常 | 捕获、写 `errors`、保留 partial、退出 0 | `errors[stage=run]` |

## 11. 自检清单（交付/复跑前）

1. `python3 -B scripts/main.py --help` 退出码 0。
2. `result.json` 存在、`case_id` 与输入一致、`output_contract` 字段齐全（`contract_missing` 应为空或已解释）。
3. `candidates` 的 `rank` 连续、顺序符合 §7 平局键、`tiers` 计数与逐条一致。
4. 每条有 `evidence.quote`，且能在摘要/题名中逐字找到（`verify.py` 的 `evidence_verbatim`）。
5. `input_record_count - Σ(version_count-1) == len(candidates)`。
6. 空输入 / 坏 JSON 仍生成合法 `result.json` 且退出码 0。
7. 重复运行输出顺序一致。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py --input /input --out /app/output
```

输入（示例）：`case.json` 含 `case_id: EXAMPLE-001`、范围 `include=["heart failure"]`、`max_k=3`；`records.jsonl` 含 2 条记录（1 条 RCT 有摘要，1 条缺摘要）。
示意输出：`A1` → `core`，`relevance_score≈0.71`，`evidence.quote` 为摘要中"…reduced hospitalization for heart failure (hazard ratio 0.65…)"；`A2` → `pending`（缺摘要）并进入 `pending_human`；`metrics.note` 说明标注不足未算 P@k。完整示例见 `references/example_walkthrough.md`。

## 13. 文件清单

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（接口、规则、边界、自检） |
| `scripts/main.py` | 主流程：发现→归一→去重→打分分档→排序→输出 |
| `scripts/verify.py` | 独立复核：契约/排序/证据逐字/计数/DOI/指标，写 `verify_report.json` |
| `references/label_taxonomy.md` | 五档规则、打分公式、平局、冲突、**可编辑术语扩展词表** |
| `references/io_contract.md` | 输入发现、输出字段字典、契约回填、状态约定 |
| `references/example_walkthrough.md` | 最小输入/调用/示意输出（标注示例） |

## 14. 适用范围、限制与维护

- 适用：固定候选集（数十到数百条）的相关性筛选与排序；中英文题录摘要。
- 限制：只据题录+摘要，不读全文；不评估数据库召回；术语扩展只覆盖 `label_taxonomy.md` §7 的词族，未覆盖领域需自行追加行；二分类指标依赖输入自带标注。
- 维护：改判据改 `label_taxonomy.md`（规则与词表同一处），改代码同步 §7 公式与 `result.json.method.scoring`；版本变更追加 `changes`。
- 版本：1.0.0（2026-11-18）。契约变更时保持字段名向后兼容，未知字段一律透传。
