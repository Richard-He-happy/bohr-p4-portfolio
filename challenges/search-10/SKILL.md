---
name: cross-lingual-known-item-search
description: >-
  Cross-lingual known-item literature retrieval skill. Runs one-command full pipeline to inventory sources, parse multilingual materials, build term tables, generate per-language queries, retrieve candidates, align verbatim evidence, detect language/version, deduplicate translations, and emit auditable result.json plus editable artifacts. Use when research question language and paper body language may differ or when source/DOI/version/body-language attribution must be preserved. Offline; Python standard library only.
version: 2.0.0
license: MIT
---

# 跨语言文献检索 Skill（Harness Agent 执行版）

## 0. 执行优先级

本 Skill 的目标是在固定 hidden cases 上完成可复核的跨语言已知条目检索。最高优先级：

1. 先跑确定性脚本入口，产出完整基线。
2. Agent 再真实读取 `/input` 原文并核验，不依据文件名或领域标签补造。
3. 每一条候选命中都必须有逐字 quote、来源编号 `[S#]`、定位符 `文件#行号/段落号` 或 `文件#page.line`。
4. 材料缺失、语言不确定、解析失败、版本冲突等全部诚实登记；任何情况下最终退出码为 0。

## 1. 单命令全流程入口

从 Skill 根目录运行：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部按 `init -> build -> selfcheck` 执行：

- `init`：盘点 `/input` 全部材料；生成来源台账；分配 `[S#]`；抽取候选；对同一 work 的多语言/多版本/重复视图做冲突分组；生成 `/app/work/ledger.json`。
- `build`：校验候选；无 Agent draft 时执行确定性兜底抽取；生成候选集、查询日志、术语表、证据表、去重结果、正文交付物与最终 `result.json`。
- `selfcheck`：检查产物与输出契约一致性；把检查结果写入 `verification.json`；发现错误必须修复或诚实降级，不伪造通过。

若脚本版本没有 `run` 子命令，回退为：

`python3 scripts/main.py --input /input --out /app/output`

随后必须执行本文件第 9 节的自检，确保 `result.json` 合法、契约齐全、退出码 0。

## 2. 目录约定

- `/input`：只读。读取 `case.json`、`task.md` 与全部实际材料。PDF 必须真实解析，不能依赖预抽取答案或标签假设。
- `/app/work`：工作中转。解析文本、台账、draft、中间 JSON 放这里。
- `/app/output`：最终产物。必须包含合法 `result.json` 及题面要求的其他可复核文件。
- `/skills/weekly-skill`：Skill 包根目录。脚本与资源用包内相对路径：`scripts/main.py`、`scripts/engine.py`、`references/method.md`、`references/io_schema.md`、`references/glossary.tsv`。

## 3. 输入契约与产出契约

### 3.1 输入

每个 case 至少有：

- `/input/case.json`：`case_id`、研究问题、范围约束、已知条目、目标语种、`output_contract`。
- `/input/task.md`：任务说明、评分维度、运行时约束。
- `/input` 下其他材料：JSON/CSV/TSV/PDF/DOCX/XLSX/PNG/JPG 等，可能有实际论文原文、译文、摘要页、元数据表。

若 `case.json` 不存在或不可解析：

1. 递归查找 `/input` 第一个 `case*.json`。
2. 仍无则产出最小合法 `result.json`：`status=input_error`、`case_id=null`、`output_contract` 为可用空对象或数组，写入 `errors[]`，退出 0。

### 3.2 `result.json` 双回显

最终 `result.json` 必须同时存在：

- 顶层契约字段：`case_id`、`status`、`question`、`scope`、`candidates`、`evidence_table`、`queries`、`term_table`、`coverage`、`dedup`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`verification`。
- `output_contract`：嵌套对象，也必须包含 `case_id` 与题面要求的全部字段。

如果题面 `output_contract` 缺失或不明确，以 `/input/case.json` 实际存在的键为准；若仍无，则使用本文件第 3.2 节标准字段，并在 `sources.note` 说明。

## 4. Agent-first 双路径

### 4.1 路径 A：Agent 详细核验

预算允许时：

1. 先运行 `init`，查看 `/app/work/ledger.json`。
2. Agent 真实读取原文和译文，核对标题、DOI、语言、版本、术语命中、quote 和 locator。
3. 将判断写入 `/app/work/draft.json`。
4. 再运行 `check -> build`。
5. 将 Agent 补充或纠正写入 `agent_review.json` 和 `changes[]`。

`/app/work/draft.json` 最小形状：

- `case_id`：与输入一致。
- `source_inventory[]`：每项含 `source_id`、`file`、`kind`、`parse_status`、`notes`。
- `work_identity[]`：每项含 `work_id`、`canonical_title`、`canonical_doi`、`language_views[]`。
- `term_mapping[]`：含 `term_id`、`query_term`、`target_lang`、`normalized_text`、`mapping_type`、`confidence`、`basis`。
- `candidate_judgments[]`：含 `candidate_id`、`true_title`、`true_doi`、`body_language`、`version_label`、`matches`、`quote`、`locator`、`notes`。
- `unresolved[]`：待人工或保留不确定。

### 4.2 路径 B：无 draft 时确定性兜底

若 `/app/work/draft.json` 不存在：

- `build` 使用台账确定性抽取，逐字生成 quote 和 locator，生成与路径 A 完全同构的产物。
- 必须在 `gaps[]`/`degradations[]` 记录 `AUTO_EXTRACT`：说明本候选为脚本自动抽取，未经过 Agent 逐条复核。
- 两条路径输出同一套产物、同一份 `result.json` 契约，不因路径不同缺字段。

## 5. 完整执行阶段

### 阶段 1：盘点和来源编号

对 `/input` 下每个文件：

1. 列出全部文件，记录路径、类型、大小、编码。
2. 读取 `case.json` 与 `task.md`。
3. 为每份可识别材料分配 `[S#]`。
4. 建立来源台账：`source_id`、`file`、`kind`、`parse_status`、`language_hint`、`encoding`。
5. 如果某文件解析失败，不得跳过；写入 `errors[]` 和 `degradations[]`，并在 `pending_human[]` 保留条目。

### 阶段 2：真实解析

- JSON/CSV/TSV：用 `scripts/engine.py` 解析。
- PDF/DOCX/图片：调用平台解析工具或 `scripts/engine.py` 中可用能力，提取实际正文和元数据。
- 解析结果写入 `/app/work/parsed/`，每条至少含：
  `title`、`abstract`、`doi`、`year`、`venue`、`authors`、`language`、`body_language`、`version_label`、`source_file`、`locator`。
- 未知项置 `null`，不得猜填。

### 阶段 3：术语表构建

从研究问题、题面约束和 `/input/case.json` 构建术语表：

- 每个术语记录：`term_id`、`query_term`、`target_lang`、`normalized_text`、`mapping_type`、`confidence`、`basis`。
- `mapping_type` 可取值：`exact`、`synonym`、`abbreviation`、`hypernym`、`hyponym`、`transliteration`、`local_name`、`agent_supplied_from_source`。
- 优先使用 `references/glossary.tsv`；若材料原文出现词表未覆盖的关键词，从原文真实提取并补充，方法标 `agent_supplied_from_source`。
- 术语无对应译法时写入 `missing_concepts[]`，查询状态标 `no_term_mapping`，不静默丢弃。

### 阶段 4：逐语种查询与检索

为每个目标语言生成查询：

- 查询记录写入 `queries[]` 和 `query_log.json`。
- 每条查询含：`query_id`、`lang`、`query_type`、`expressions[]`、`matched_count`、`status`、`notes`。
- 查询在本 case 提供的材料语料内执行，不得声称实时联网或未见语言覆盖。
- 若某声明语言无有效结果，必须在 `coverage.languages_without_results[]` 说明，不得假装覆盖。

### 阶段 5：候选证据对齐

每个候选至少包含：

- `candidate_id`、`work_id`、`title`、`doi`、`year`、`authors`、`venue`。
- `source_id`：对应 `[S#]`。
- `locator`：`文件#行号/段落号` 或 `文件#page.line`。
- `quote`：必须逐字来自原文；不得改写。
- `matched_terms[]`：候命中命中的原文表面形式。
- `relevance_reason`：为什么相关。
- `strength`：`high`、`medium`、`low`、`unverified`。
- `support_scope`：`direct_evidence`、`indirect_evidence`、`metadata_only`、`unverified`。
- `language`、`body_language`、`version_label`、`version_basis`。
- `duplicate_of`：若与其他候选同 work，指向主候选。

### 阶段 6：语言与版本识别

语言判断优先依据正文实际内容，而非文件名或单一元数据标签：

- `language`：文献记录标注语言。
- `body_language`：正文实际语言。
- `version_label` 可取值：`original`、`publisher_full_translation`、`english_abstract_only`、`exact_duplicate`、`bilingual_publication`、`unknown`。
- `version_basis`：说明判定依据，如 DOI 匹配、标题一致、摘要语言、页数、语种正文证据。
- 若 `language` 与 `body_language` 冲突，写入 `conflicts[]` 和 `uncertainty[]`。

### 阶段 7：去重与版本归并

同一文献的多个语言版本/多个视图必须先归并再计数：

- 优先按 DOI 归并；无 DOI 时按规范化标题 + 年份 + 作者归并。
- `dedup.rules` 记录去重规则。
- 每个 work 只保留一个主候选，`view_records[]` 列出各组视图：原文、译文、摘要、重复记录。
- `coverage.duplicates_merged` 写实际合并数，不得虚报。

### 阶段 8：漏检与误译复核

对高风险命中或词面匹配但语义存疑的候选：

- 检查 `matched_terms.surface` 是否与原文用词一致。
- 若只是词面对应但语义漂移，标记为假阳性并写入 `screening[]`，证据确凿才可排除。
- 无结果、冲突、权限或接口异常分别写入 `status`、`errors[]`、`pending_human[]`。

### 阶段 9：渲染与最终 result.json

生成并落盘：

- `result.json`
- `candidates.csv`
- `candidates.json`
- `query_log.json`
- `term_table.json`
- `evidence_table.json`
- `verification.json`
- `agent_review.json`
- `pending_human.json`
- `deliverable.md`
- 题面额外要求的可编辑文件及真实 PDF/PNG 预览

将所有状态、来源、不确定性、变更记录写回 `result.json`。

## 6. 状态与异常处理

`status` 取值：

- `ok`：无 gaps、无 unresolved、证据全部可核验。
- `partial`：已有可用结果，但存在未决、低置信度或局部失败。
- `insufficient_evidence`：材料不足以支持候选或结论。
- `input_error`：输入缺失或不可解析。

异常处理表：

- `case.json` 缺失或不可解析：`input_error`，退出 0。
- 材料缺失：`insufficient_evidence` 或 `partial`，写入 `gaps[]`。
- PDF/DOCX/图片解析失败：`errors[]`/`degradations[]`，该材料写 `pending_human`。
- 格式不支持：标 `unsupported`，`status=partial`。
- 空输入/无候选：`insufficient_evidence`，保留空候选与查询日志。
- 目标语种无结果：写入 `coverage.languages_without_results[]`，不删语种。
- 术语无对应译文：写入 `missing_concepts[]`。
- 语言置信度低于 0.6：标 `language_low_confidence`，至少 `partial`。
- 证据摘录无法定位：`evidence_quote_match=failed`，写入 `pending_human`，不调整摘录以通过。
- 版本冲突：保留冲突记录，写入 `conflicts[]`，不强行消解。
- 超时或中断：保留最后合法 `result.json`，写入 `degradations[]`，退出 0。

## 7. Hidden case 鲁棒性

题面固定 3 个 case，覆盖真实 3 works / 6 views，典型形态：

- 原文葡萄牙语 / 英语 body。
- 出版社全文翻译。
- 英语摘要 only。
- 完全重复记录。

处理原则：

1. 先识别 `case_id` 与问题语言，再检查材料实际正文语言。
2. 不因某文件叫 `english_abstract` 就假设其正文语言；必须打开验证。
3. 同一 work 的多个 views 必须合并，但每个 view 的 `source_id`、`locator`、`language`、`version_label` 必须保留。
4. 若只找到摘要或译文，不声称找到原文；写清已完成和未完成部分。
5. 若 DOI 或标题在不同文件中不一致，保留冲突，不以多数票掩盖。

## 8. 预算策略

64 次模型请求 / 900 秒内：

1. 先运行脚本产出全套基线，脚本执行不消耗模型请求。
2. 再核查关键非英语候选、版本/重复标注、证据摘录精确性。
3. 每完成一轮核查就更新一次 `result.json`。
4. 剩余预算不足 15% 或时间不足 90 秒时停止新任务，保留合法 partial 并退出 0。
5. 不反复重跑脚本，不逐条复查低权重候选，不做无证据的格式美化。

## 9. 提交前自检

逐项核对：

- `result.json` 合法且 `case_id` 与输入完全一致。
- 顶层与 `output_contract` 中均出现契约字段，键名不变，缺失值为 `null` 或 `[]`。
- `status` 与 gaps/uncertainty/errors 完全一致。
- 每条候选有 `source_id`、`locator`、`quote`，且 quote 逐字可溯源。
- 每个声明语言都有查询和结果，或明确缺口说明。
- 重复版本已合并，`duplicates_merged` 可复核。
- `queries[]`、`term_table[]`、`sources[]`、`verification.json` 可供第三方追溯。
- 不包含虚构基准分数、金标准、预生成答案或不存在的数据。
- 无论任何异常，最终退出码 0。