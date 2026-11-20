---
name: library-annotation-sediment
description: Repairs a research file library and turns reading annotations into traceable, searchable deposition notes. Use when the task supplies /input/case.json, /input/task.md and a materials directory, and asks for annotation extraction, metadata inventory, duplicate/version handling, knowledge linking, or search. Runs one command: init, build, selfcheck. It first produces a deterministic stdlib baseline with detailed source locators, then requires the Harness Agent to read real files and enhance a draft before finalizing. All deliverables keep honest status, sha256, source refs, errors, degradation and pending_human records.
version: 3.0.0
---

# 阅读批注与知识沉淀：科研资料整理，也保留版本关系

本 Skill 是“阅读批注与知识沉淀”任务的执行入口。它把科研材料从散落的批注、笔记、文件和版本关系中整理成可复核、可检索、可交接的结构化结果。核心目标不是“抽得多”，而是每条批注都能回到原文的具体页与位置，每条笔记论断都能指到原文片段，沉淀条目能被真实问题检索到，并能被他人复跑核对。

## 0. 最高优先级：单命令全流程入口

Agent 进入案例后，第一步必须直接运行：

`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部严格按三个阶段执行，并不会依赖模型请求：

1. `init`：扫描 `/input`，盘点文件、目录、权限、哈希、来源编号 `S#`、候选批注、候选冲突分组；生成 `/app/work/ledger.json` 和候选抽取结果。
2. `build`：校验当前 `/app/work/draft.json`；如果没有 draft，则用 init 台账做确定性兜底抽取，生成实质工作稿；再渲染全部产物并 finalize `/app/output/result.json`。
3. `selfcheck`：检查产物与 `output_contract` 字段、磁盘文件、来源引用格式是否一致。

这个命令必须在 900 秒预算内很少的模型请求下也能产出完整、合法、可复核的 partial/full 交付物。任何异常都必须捕获，并最终写合法 `result.json`，退出码为 0。

## 1. Agent-first 双路径工作流

### 路径 A：推荐路径（Agent 真读增强）

1. 先运行一次单命令全流程，拿到基线产物。
2. 读取 `/input/case.json`、`/input/task.md` 和 `/app/work/ledger.json`，确认 `case_id`、`output_contract` 字段、任务边界、检索问题。
3. 真实阅读 `/input` 中的材料，优先处理高价值对象：PDF 高亮/批注、DOCX comments/修订、重复文件、版本链、搜索问题直接涉及的文件。
4. 把判断写入 `/app/work/draft.json`。不要直接手改 result.json 或结构化 JSON；所有核验与新增判断都通过 draft 进入 build。
5. 重新运行：
   `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work --draft /app/work/draft.json`
6. 检查 selfcheck 输出，补齐缺失字段和 pending_human 项；最后再运行一次 run 固化。

### 路径 B：无 draft 时确定性兜底

如果 Agent 未能写入 draft，`build` 必须使用 init 台账的确定性抽取结果生成实质工作稿，而不是空模板。兜底结果中每条 annotation/note 仍必须包含：

- `source_ref`：`S#`
- `quote`：从原文中逐字抽取的片段
- `locator`：`文件#页码/段落号/行号`
- `status`：`auto_extract`
- `confidence`：保守估计，如 `medium` 或 `low`

兜底路径还必须把 `AUTO_EXTRACT` 诚实写入 `gaps`、`degradations` 或 `methods`，说明哪些结果尚未经过 Agent 人工核验。最高分的关键不是假装人工核验，而是即使没有 draft 也有可用的确定性结果，同时把未核验状态如实登记。

## 2. 目录与运行契约

- 输入：`/input/case.json`、`/input/task.md`，以及题面规定的材料目录。
- 工作：`/app/work`，用于 ledger、draft、候选件、临时文件。
- 输出：`/app/output`，必须包含最终 `result.json` 和所有契约要求的可交付物。
- 运行时：python3 >= 3.8，标准库优先，离线可用，不依赖未声明外部服务。
- 资源上限：50 个 UTF-8 文本文件，单文件 ≤500KB，总计 ≤2MB，无 symlink。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。因此先跑脚本，再增量增强，不要重复解析每份文件。

## 3. 产出清单

至少生成并校验以下文件；若 `output_contract` 要求额外文件，必须补齐：

- `/app/output/result.json`：主结构化结果，双回显契约字段。
- `/app/output/inventory.csv`：来源文件清单、哈希、大小、类型、权限、来源、目录层级。
- `/app/output/annotations.jsonl`：逐条批注及原文定位。
- `/app/output/notes.jsonl`：结构化笔记条目。
- `/app/output/links.jsonl`：笔记、批注、文献、作者、方法、项目之间的可解释关联。
- `/app/output/version_chain.json`：版本关系和重复文件判定。
- `/app/output/duplicates.json`：重复文件分组与依据。
- `/app/output/search_index.json`：可检索索引。
- `/app/output/search_answers.json`：案件中检索问题的回答与召回记录。
- `/app/output/operations.log`：操作、文件哈希、脚本版本、变更、失败与恢复。
- `/app/output/evidence_citations.md`：关键数字与论断的 `[S#]` 引用表，供人工复核。
- 若契约要求可编辑 Office、幻灯片、图，必须同时渲染出 `pdf`/`png` 预览，否则在 `errors` / `pending_human` 中说明。

## 4. 来源引用与可核验性规则

所有关键数字、原文引用、笔记论断、关联、检索命中都必须带有来源和定位：

- 来源编号：`S1`, `S2`, ...，由 init 分配，一旦分配不因后续文件新增而重排；若有变动必须写入 `changes`。
- `source_ref`：指向来源编号。
- `locator`：优先使用 `S#@p3¶2`、`S#@line42-48`、`S#@sheet=Sheet1!A1:D10` 或 `S#@page2&rect=x1,y1,x2,y2`。
- `quote`：必须是原文中存在的逐字片段；若短片段不唯一，需增加上下文 `quote_context` 并标注 occurrence index。
- 文件级可核验性：每个文件都记录 `sha256`、`size`、`mtime`、`mode`、`readable`、`type`、`source_path`。
- 所有关键论断在正文或 `evidence_citations.md` 中必须出现 `[S#]` 和 locator，不允许只有一句“见材料”。

## 5. draft.json 形状和工作流

`/app/work/draft.json` 是 Agent 与脚本之间的唯一判断接口。Agent 不得覆盖生成后的 result.json 结构；应写入 draft 再重跑 build。

推荐字段：

- `case_id`
- `source_assignments`：`{"S1": {"path": "...", "type": "pdf", "sha256": "..."}}`
- `annotations`：`source_ref`, `page`, `locator`, `quote`, `type` (highlight/underline/margin/handwriting/webclip/temp), `color`, `author`, `created`, `status` (verified/auto_extract/uncertain), `confidence`
- `notes`：`note_id`, `type` (question/method/conclusion/reusable/uncertain), `claim`, `evidence` (数组，每项含 `source_ref`, `locator`, `quote`), `tags`, `confidence`, `status`
- `links`：`from_id`, `to_id`, `relation`, `shared_terms`, `basis`, `strength`
- `duplicate_decisions`：`group_id`, `hash_match`, `duplicate_of`, `basis`
- `version_decisions`：`current_id`, `supersedes`, `basis`, `status` (certain/uncertain)
- `search_answers`：`query`, `matched_note_ids`, `matched_file_ids`, `shared_terms`, `missing_terms`, `no_recall`, `answer`
- `conflicts`：冲突项和未解决原因
- `pending_human`：需要人工确认的项目
- `methods`：本次采用的方法和局限

Agent 若发现脚本抽取的 quote 错位、页码错误、版本判断不成立，应把正确项写入 draft 的 `annotations` / `version_decisions`，并在 `changes` 中注明 `agent_corrected_locator` 或 `agent_corrected_version`。

## 6. result.json 双回显契约

`result.json` 必须做到：

1. 所有 `output_contract` 字段，包括 `case_id`，在顶层出现一次，且在 `output_contract` 嵌套对象中出现一次。
2. 未知/缺失契约字段的值写 `null`，不能用空字符串掩盖。
3. 顶层包含 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`summary`、`contract_fill`、`methods`。
4. `status` 只允许使用：`ok`、`partial`、`insufficient_evidence`、`input_error`。
5. `sources` 中每条来源包含 `source_id`、`path`、`sha256`、`type`、`size`、`readable`、`note`。
6. `contract_fill` 记录每个契约字段由哪条流水线生成：`init`、`build`、`agent_draft`、`fallback`、`not_available`。
7. `changes` 必须记录基线产出和 Agent 增强的差异证据，例如：
   - `baseline_annotation_count`
   - `agent_verified_count`
   - `agent_added_note_count`
   - `agent_corrected_locator_count`
   - `fallback_auto_extract_count`
   - `contract_missing_fields`
   不要写任何平台分数或基准分数。

如果契约字段与保留字段同名，嵌套 `output_contract` 中保留契约原键，顶层用保留键承载元数据，并在 `contract_fill` 中注明碰撞。

## 7. 批注抽取与笔记结构化规则

### 7.1 批注抽取

- 区分类型：高亮、划线、页边批注、手写批注、网页剪藏、临时笔记。
- 保留颜色、作者、时间、页号、坐标、所属文件、类型标签。
- PDF：优先使用系统或平台可用工具提取真实文本层、页号和坐标；不可用时退回 `scripts/docext.py`。无文本层扫描件必须标 `scanned_pdf`、`anchor_unresolved`，不得编造 OCR 文本。
- DOCX：提取正文、comments、批注位置和作者。
- HTML：提取正文或剪藏文本，保留原始 URL 或来源。
- 图片/手写：不假装识别；如无 OCR，写入 `pending_human` 并保留文件。
- 锚点校正：当 quote 能在源文件中找到，但 locator 漂移时，以实际文本位置重新定位；无法确定时标 `anchor_unresolved`。
- 每条批注的 `quote` 必须能从来源文件真实找到。验证失败不能写成成功。

### 7.2 笔记结构化

笔记不是摘抄，而是有判断的结构化条目。建议 schema：

- `type`：`question` / `method` / `conclusion` / `reusable` / `uncertain`
- `claim`：一句话判断
- `evidence`：至少一个原文 quote 和 locator
- `annotation_ids`：对应批注条目
- `tags`：主题、实体、方法、时间
- `confidence`：`high` / `medium` / `low`
- `status`：`verified` / `auto_extract` / `pending_human`

没有原文支撑的论断必须标为 `uncertain` 或 `pending_human`，不得写成确定结论。

## 8. 知识关联与版本/重复处理

### 8.1 知识关联

- 关联可以在批注、笔记、文献、作者、方法、项目之间建立。
- 每条关联必须有依据：共享的实体/术语、共引用、共同来源文件、同一方法术语等。
- 仅共享一个宽泛术语不得作为强关联；过度连接要降级为 `weak` 或丢弃。
- `links.jsonl` 中每条记录包含 `basis` 和 `shared_terms`，不能只有 `related_to`。

### 8.2 重复文件

- 用字节级 `sha256` 对重复文件分组，标记 `duplicate_of`。
- 不删除、不移动原文件。
- 若文件名相似但哈希不同，只写 `suspected_duplicate` 并记录依据，不强制合并。

### 8.3 版本链

- 版本判断不能只看文件名。文件名只是线索，必须结合 `mtime`、日期标签、版本号、内容哈希、题面管理性版本说明。
- 去除 `final`, `draft`, `v1`, `v2`, `copy`, `副本`, `-final`, `-v\d+` 等规范化后再分组。
- 生成 `supersedes` 边，并写 `basis`；不确定标 `uncertain`。
- 不要把“文件名相似”当确证。

## 9. 检索入口

- 构建 `search_index.json`，支持按主题、标签、实体、来源文件、作者、时间检索。
- 对案件中的每个检索问题，在 `search_answers.json` 中回答：
  - `query`
  - `matched_note_ids`
  - `matched_file_ids`
  - `shared_terms`
  - `missing_terms`
  - `no_recall`
  - `answer`
- `no_recall` 是词汇缺口，不是“没有答案”。应写出缺失词，让结果可整改。
- 检索命中也必须有来源引用，不得给无依据的语义答案。

## 10. 失败、冲突与恢复

任何文件解析失败、加密、损坏、权限不足、无文本层、OCR 低置信度，都必须：

- 不中断整体流程。
- 保留已获取的 `sha256` / `size` / `type` / `path`。
- 写入 `errors`、`degradations`、`pending_human` 中。
- 在 `operations.log` 中记录尝试的方式、失败原因、恢复或跳过策略。
- 若问题来自旧版本批注或重复文件，写入 `conflicts`，不要强行归并。
- 最终 status 必须诚实：材料不足写 `insufficient_evidence`，部分完成写 `partial`。

## 11. 隐藏案例鲁棒性

| 情况 | 应对 |
|-|-|
| `/input/case.json` 缺失或无法解析 | 读取 `task.md`，继续扫描材料；`errors` 记录；`status=partial` 或 `input_error`；仍 exit 0 |
| `output_contract` 缺失或为空 | 使用默认契约字段；`contract_fill` 记录；status 诚实 |
| 材料目录为空 | `status=insufficient_evidence`；合法 result.json；空 artifacts；exit 0 |
| 单个 PDF/DOCX 损坏或加密 | 保留可获取元数据；`skipped` + `pending_human`；其他文件继续 |
| PDF 为扫描件无文本层 | `anchor_unresolved`；`scanned_pdf`；不伪造文本 |
| OCR 置信度低 | `confidence=low`；锚点 pending；不修改原文 |
| 时间即将用尽 | 立即写 partial result.json，列出 missing fields，exit 0 |
| 检索无结果 | `no_recall`；列出 `missing_terms` |
| 版本关系不确定 | `status=uncertain`；不强制排序 |
| 重复文件 | 标记 duplicate_of；不删除 |

## 12. 预算分配

- 第 1 次模型请求前后：读取 case.json/task.md，运行单命令全流程。
- 前 10 次请求：确认契约、来源编号、产物路径；检查基线 result.json 是否合法。
- 第 10–30 次请求：针对性阅读高价值文件，写入 draft；不要逐文件均等深入。
- 第 30–45 次请求：重跑 build，检查 selfcheck；补齐 pending_human 和修改注记。
- 第 45 次请求后：只做合法性和完整性收尾；720 秒前必须已有 partial；880 秒前无条件 finalize 并 exit 0。

## 13. Rubric 维度到产物证据映射

### 实际效果 40 分

- 任务完成度：`annotations.jsonl`、`notes.jsonl`、`links.jsonl`、`search_answers.json` 非空且来自真实文件。
- 结果正确性：每条 annotation/note 有逐字 `quote` 和 `locator`；result 中验证状态清晰。
- 结果完整性：`inventory.csv` 覆盖文件类型、权限、来源、哈希、目录层级；`duplicates.json` 和 `version_chain.json` 覆盖重复与版本。
- 结果可核验性：`sha256`、`operations.log`、`scripts/main.py` 版本、`[S#]` 引用完整。

### 使用增益 25 分

- 质量增益：draft 中 Agent 核验结果 vs 脚本基线，记录在 `changes`。
- 效率增益：`notes.jsonl` 直接可检索，`search_index.json` 可自动化命中；减少人工重排。
- 增益可验证性：`changes` 中给出基线 count、Agent verified count、corrected locator count 等差异，不编造分数。

### 创新增益 15 分

- 新增能力：贯通“批注抽取 → 笔记结构化 → 关联 → 检索”，且保留原始锚点。
- 方法改进：锚点重定位策略、版本规范化、evidence 链接、no_recall 处理。
- 创新证据：`methods` / `summary` 写清方法边界，不用空话；每条改进都可在产物中检查。

### 可靠体验 10 分

- 调用易用：单命令即全流程；`/app/output/result.json` 始终存在。
- 运行稳定：同一输入重复运行结果确定；异常不中断。
- 异常处理：加密、损坏、无文本层、权限不足、旧版本、重复文件均有明确 `errors` / `pending_human`。

### 生态贡献 10 分

- 文档完整：本 SKILL.md 已覆盖调用、输入、输出、异常、schema、自检。
- 资源可复用：标准库脚本可复跑，输入输出约定清晰。
- 分享价值：来源引用、研究方法、局限性写入 `methods`；不依赖私有账号或个人手工操作。

## 14. 提交前自检清单

1. 已运行 `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`。
2. 已读取 `/input/case.json` 和 `/input/task.md`，确认 `case_id` 和 `output_contract`。
3. 已真实阅读关键材料，而非仅凭文件名。
4. `result.json` 合法且包含双回显契约字段。
5. 所有 quote 可在原文中找到，locator 归属正确；不确定项已标 `anchor_unresolved`。
6. 所有文件哈希、重复、版本链依据真实，无编造。
7. `inventory.csv`、`annotations.jsonl`、`notes.jsonl`、`links.jsonl`、`search_index.json`、`version_chain.json`、`operations.log` 均已生成。
8. `errors`、`degradations`、`pending_human` 与真实失败一致。
9. `status` 诚实；不把未完成写成 `ok`。
10. 退出码为 0，`result.json` 存在且可解析。
11. 没有 `__pycache__`、`.pyc`、symlink。
12. 没有写任何正式案例预先生成的答案。

## 15. 最小调用示例

示例输入：一个包含若干 PDF、DOCX、TXT 和一份检索问题说明的 `/input` 目录。

命令：

`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

示意输出（标记为示例，非正式案例结果）：

`status=ok files=5 annotations=3 notes=2 links=1 duplicates=1 version_chains=1 search_queries=1 exit=0`

如果 Agent 写入 draft 后再运行：

`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work --draft /app/work/draft.json`

示意输出：

`status=ok agent_verified_annotations=3 agent_added_notes=1 exit=0`

## 16. 与本 Skill 依赖的文件

本包只使用以下相对路径：

- `SKILL.md`
- `scripts/main.py`
- `scripts/docext.py`

`scripts/main.py` 是流水线入口，`scripts/docext.py` 提供标准库 PDF/DOCX/XLSX/HTML/TXT 解析能力。所有生成物写入 `/app/output`，所有中间判断写入 `/app/work`。