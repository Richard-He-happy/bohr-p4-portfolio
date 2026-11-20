---
name: search-coverage-gap-auditor
description: Audit literature-search coverage against a frozen reference set and diagnose every miss. Use when a case supplies known-relevant papers (review reference list, guideline, seed set, citation graph) together with retrieved records and/or query logs, and the task is 检索覆盖率、遗漏率、漏检归因、补充检索 (coverage, recall, missed studies, gap analysis, search audit). Produces a per-record hit matrix, coverage on an explicit auditable denominator, one attributed cause per miss bound to a concrete query/field/year-window/source, and directed supplementary rounds with measured marginal gain. The agent must read and extract source materials directly, use the deterministic scripts only as accelerators, and personally verify or correct all substantive outputs before finalizing.
version: 2.0.0
---

# search-coverage-gap-auditor

## 1 用途与核心定位

本 Skill 用于审计科研文献检索的覆盖率、遗漏率与漏检原因：拿到冻结参考集、检索记录池和查询日志后，输出可核验的逐条命中矩阵、覆盖率、漏检归因和定向补充检索方案。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 不得把 `scripts/main.py` 生成的骨架或模板直接当作成品；你必须阅读 `/input` 中的真实材料，逐条核对参考集、检索记录、查询日志中的证据，并将你的核验结果写入 `result.json`。任何关键数字、命中状态、归因、补检结论都必须来自材料中的实际内容或由你明确标注为推断/预测；不确定就标 `pending_human`，材料不足就标 `limitations`，严禁补造数据、引用、分数或来源。

本 Skill 的任务边界：不做正式全文阅读，不判断论文质量，不联网接入外部数据库，不声称全球最新/查全。如果案例提供已知相关文献集合（reference set），则覆盖率严格以该集合为分母；否则最多只能做候选池覆盖或输入覆盖，并明确说明这不是真实召回率。

## 2 触发条件与适用场景

以下情况使用本 Skill：

- 任务要求覆盖率 / 召回率 / 漏检 / 遗漏分析 / 检索审计 / 参考集比对 / 补充检索 / recall estimate against a known set；
- 输入包含一份可识别的已知相关文献清单（参考集），以及至少一部分检索记录、查询日志或候选池；
- 需要输出每条文献的命中/漏检状态，并对漏检原因进行可操作的归因。

不适用：普通文献列表生成、只需排序/筛选、全文阅读与正式系统综述纳排流程。

## 3 运行时契约

- 输入目录 `/input` 只读：包含 `case.json`、`task.md` 和题面规定的材料（PDF/DOCX/CSV/图片等）。必须真实解析材料内容，不得依据文件名或领域标签猜测内容。
- 工作目录 `/app/work`：可写。将解析后的文本、中间证据表、草稿放这里。
- 输出目录 `/app/output`：最终交付物必须落在这里。
- 必须存在 `/app/output/result.json`，且包含原 `output_contract` 的全部字段（键名不改）与 `case_id`。
- 可编辑 Office/幻灯片/图形产物必须额外生成真实渲染的 PDF/PNG 预览。若任务未要求此类产物，本 Skill 核心产物为 JSON、CSV、Markdown，不额外生成。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。必须预算感知，尽早落盘 honest partial。
- 退出码恒为 0；任何异常写入 `errors`/`degradations`/`pending_human`，绝不静默失败。

## 4 完整性优先（最高优先级）

此前有同类包因交付不完整、像预制答案而被扣分。为避免重蹈覆辙，本 Skill 采用“先基线、后增强”策略：

1. 进入任务后，先运行 `python3 -B scripts/main.py --input /input --output /app/output`，产出全套基线交付物。即使脚本只能给出部分结果，也先保留。
2. 基线交付物包括：`result.json`、`hit_matrix.csv`、`candidates.csv`、`query_log.json`、`supplement_plan.json`、`coverage_report.md`，以及运行 `verify.py` 后生成的 `verify_report.json`。这些文件一个都不能少。
3. 后续你的核验、修正、补充只能在基线之上进行。**不得删除、清空或遗漏任何基线文件与 `result.json` 契约字段。** 如果你发现基线某处不准确，在 `result.json.changes` 中记录原始值与修正值，并在相应字段中更新为更准确内容；旧值可存入 `baseline_comparison` 或 `changes.previous_value`，而不是删除。
4. 若基线未生成某些字段或文件，你先补齐再继续；若不确定是否该保留，就保留并标注 `reviewed_by_agent`。
5. 完整性自检必须在提交前完成：逐项核对 `output_contract` 字段列表、磁盘文件、`result.json` 键三者一一对应。缺任何一项先补齐再收尾；`status=partial` 时必须列出所有缺失项和原因。

## 5 输入发现与真实材料解析

只依据包内真实存在的文件与 `/input` 中的真实材料，不引用不存在的文件，不根据文件名猜测内容。

### 5.1 扫描与识别

递归扫描 `/input/**`，按扩展名和内容语义识别以下角色：

| 角色 | 识别要点 |
|-|-|
| 参考集 | 列表项含 title/doi/year，或路径/键名含 reference、refs、seed、included、known、gold、relevant、must_find，或项含 include/relevant 决策字段 |
| 检索记录池 | 项含 title/doi 且路径/键名含 response、result、hit、record、retriev、pool、candidate、crossref、europepmc、publisher，或项含 query_id/retrieved_at/source_db |
| 查询日志 | 项含 query/query_string + hits/count/total，或位于 queries/strategy/log 文件 |
| 引文图 | 项含 citing/cited/from/to/source/target |

支持 `.json .jsonl .csv .tsv .pdf .docx` 以及题面指定的图片材料。`case.json` 缺失时退回任意 `case*.json`，并在 `degradations` 记录。

### 5.2 真实解析要求

- 对于 PDF：必须调用 Harness 提供的 PDF 解析工具（如 pdf-text-tool）或等价实际解析器提取文本。禁止只看文件名或标签。若 PDF 无文本层或工具失败，保留失败证据，记入 `degradations` 和 `pending_human`。
- 对于 DOCX：用可用的 DOCX 文本提取工具读取正文和表格内容。
- 对于图片：如果图片含有表格或文字，使用 OCR 工具（若平台提供）尽量提取；无法可靠提取时，标 `pending_human`，不构造数据。
- 对于 CSV/TSV/JSON：直接读取内容，保留原始行号、记录号、字段名，作为 `evidence_locator` 的一部分。

提取后的文本建议存入 `/app/work/parsed/`，供你后续逐条核对使用。脚本可能不使用 `/app/work/parsed/`，但这不妨碍你将其作为证据源。

任何材料未提供、无法解析、字段缺失的对象，一律写入 `limits`/`errors`/`pending_human`，不得用默认值或推测值填补成事实数据。

## 6 编号执行流程

每一步都注明输入、动作、输出和失败分支。严格按照此顺序执行；你可以并行读取多个文件以节省请求，但不要跳过关键核验步骤。

### 步骤 1：盘点输入与契约

- 输入：`/input/case.json`、`/input/task.md`、`/input` 下所有材料文件。
- 动作：
  1. 读取 `case.json`，确认 `case_id`、`output_contract`、`organizer_supplied_scope` 等字段。
  2. 列出 `/input` 下所有文件，按类型和大小预判解析策略。
  3. 读取 `task.md` 中关于输出、约束、评分要点的部分。
- 输出：`/app/work/input_inventory.json`（可选，但建议），包含文件清单、发现的契约字段、缺失项。
- 失败分支：若 `case.json` 缺失或 JSON 损坏，尝试 `case*.json`；仍失败则继续，`status=input_error`，但必须产出合法 `result.json` 并退出码 0。

### 步骤 2：真实解析材料

- 输入：`/input` 下材料文件。
- 动作：
  1. 对每个 PDF/DOCX/图片，调用可用解析工具提取文本，保存到 `/app/work/parsed/`。
  2. 对结构化文件（JSON/CSV/TSV），直接读取并记录原始键名与关键内容。
  3. 从解析结果中识别参考集、检索记录池、查询日志、引文图。
  4. 将识别结果整理成 `/app/work/extracted_evidence.json`（可用脚本辅助，但最终由你核对）。
- 输出：`/app/work/extracted_evidence.json`，内含 `reference_set_candidates`、`pool_candidates`、`query_log_candidates`、`graph_candidates`，每项带 `source_file`、`record_index`、`raw_fields`。
- 失败分支：某文件无法解析时，不中断；记录该文件路径、解析工具、错误信息到 `degradations`。若所有参考集证据都缺失，转入降级流程（见 §8）。

### 步骤 3：运行基线脚本

- 输入：`/input`（脚本自行扫描）。
- 动作：
  1. 执行 `python3 -B scripts/main.py --input /input --output /app/output`
  2. 执行 `python3 -B scripts/verify.py --input /input --output /app/output`
- 输出：`/app/output` 下的基线交付物，包括 `result.json` 及 CSV/MD/JSON 文件。
- 失败分支：脚本异常退出但会写 `result.json`（本包已保证退出码 0）；若脚本未生成 `result.json`，你可基于 `/app/work/extracted_evidence.json` 手工构建最小 `result.json`，但必须先保留其他基线产物。

### 步骤 4：Agent 亲自核对与修复

- 输入：脚本基线输出、`/app/work/extracted_evidence.json`、`/app/work/parsed/` 及原始材料。
- 动作：
  1. 逐条核对 `result.json.reference_set` 与 `extracted_evidence.json` 中的参考集。确保每条文献的 too（DOI/title/year）准确；若脚本解析错或漏，你在 `result.json` 中修正，并在 `changes` 记录原值与新值。
  2. 逐条核对 `result.json.retrieval_pool` 与真实记录池，确认每条记录来自哪个文件、哪个 query_id、哪个 retrieved_at。
  3. 检查 `hit_matrix.csv` 的命中状态：对每个 `exact_doi/exact_title/fuzzy_title` 命中，亲自打开对应原始记录验证相似度是否合理；对 `miss`，检查是否脚本遗漏了池内已有但阈值不够的记录（C01）。
  4. 检查覆盖率分母是否在匹配前冻结、是否排除了撤稿/不可得记录；如果脚本的分母口径有误，修正 `coverage` 与 `coverage_over_all_refs`，但保留原值至 `changes`。
  5. 检查漏检归因是否具体到 query_id、字段、时间窗、来源库；如果归因泛泛如“数据库覆盖不足”，改为更具体的 C 类代码并补证据。
  6. 检查补充检索是否真的带来新增：如果脚本的 R1 对齐修复命中数确实增加，则接受；若只是同义词重跑且无新增，应降级为“空转”，在 `supplement` 中标注。
- 输出：更新后的 `/app/output/result.json`、`hit_matrix.csv`、`supplement_plan.json` 等。新写入 `reviewed_by_agent: true`、`agent_review_notes`、`changes`。
- 失败分支：任何一条核对无法完成，保留基线值，在 `pending_human` 中写明缺失证据；不要为了完成而编造。

### 步骤 5：产出完整成品（Agent 亲自撰写/制作）

- 输入：步骤 4 修复后的数据。
- 动作：
  1. 确保 `coverage_report.md` 包含：研究问题、参考集描述、检索范围、覆盖率结果（含 Wilson 95%）、逐条命中/漏检表、漏检分类统计、补充检索的查询式与边际收益、残余遗漏与停止理由。
  2. 确保 `candidates.csv` 的每条候选都有相关性依据和来源定位。
  3. 确保 `query_log.json` 记录每个 query 的实际命中数、保留记录数、时间窗、字段限制、来源库。
  4. 若任务要求可编辑 Office/幻灯片/图形产物，则实际制作并调用相应渲染工具生成真实 PDF/PNG 预览，放入 `/app/output`；预览必须真实渲染，不得伪造。
- 输出：完整交付物，且与 `result.json` 一致。
- 失败分支：某部分数据不足以支持撰写，保留 partial 内容，在 `coverage_report.md` 及 `result.json` 中明确“未完成部分”。

### 步骤 6：回填 result.json 与自检

- 输入：最终交付物。
- 动作：
  1. 回填 `result.json` 所有顶层字段：`case_id`、`status`、`sources`、`scope`、`reference_set`、`retrieval_pool`、`coverage`、`miss_taxonomy`、`hit_matrix`、`candidates`、`queries`、`supplement`、`baseline_comparison`、`metrics`、`limits`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`contract_fill`。
  2. 提取输入 `output_contract` 所有键，原样回填到 `result.json` 顶层，键名不改。若某契约值缺失，填 `null`/`[]`/`""` 并在 `contract_fill` 注明来源与转换。
  3. 运行 `python3 -B scripts/verify.py --input /input --output /app/output`，确认 14 项检查通过。
  4. 逐项完成 §11 自检清单。
- 输出：最终 `/app/output`，退出码 0。
- 失败分支：若 verify 未通过，优先修复；无法立即修复则保留错误并把 `status` 设为 `partial`，同时列出 `errors`。

## 7 预算策略（64 次模型请求内）

原则：优先完成 rubric 权重最高的交付物，尽早落盘 honest partial，避免无意义循环与冗余调用。

| 阶段 | 分配请求数 | 说明 |
|-|-|-|
| 输入盘点与契约识别 | 5-8 | 批量读取 `case.json`、`task.md` 与文件清单，不要逐文件单独调用 |
| 材料解析与提取证据 | 12-15 | 将多个 PDF/DOCX 合并为批量解析调用；结构化文件一次读取多个 |
| 运行脚本与生成基线 | 2-4 | `main.py` 一次，`verify.py` 一次；脚本失败时不要重复多次，先保留 partial |
| Agent 核验与修复 | 20-25 | 按参考集、记录池、命中状态、归因、补检分块核验，每块一次请求；优先覆盖率和高权重错误 |
| 回填与自检 | 8-12 | 目标：所有契约字段齐全、verify 通过、自检清单逐项打勾 |
| 预留 | 4 | 处理意外材料损坏、契约复杂、额外产出 |

必须做：步骤 1、2、3、4、6。可以跳过：仅在材料不含引文图时跳过 R2 引文路由；仅在无要求时跳过可编辑 Office/图形渲染。落盘 partial 的时机：步骤 3 跑完脚本后立即落盘；任何核验子阶段完成一次，更新一次 `result.json`。

## 8 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json` 并退出码 0；`result.json` 必须真实反映已完成和未完成部分。

| 情况 | 降级策略 | 标注 |
|-|-|-|
| 材料缺失/损坏 | 尝试其他候选文件；无法恢复则 `status=input_error` 或 `partial`，其余字段尽量保留 | `errors` 注明文件路径和错误；`pending_human` 列出所需材料 |
| 格式不支持 / PDF 无文本层 | 使用可用工具尝试提取；失败则跳过该文件，不构造内容 | `degradations` 记录工具名和失败原因；`limits` 说明未纳入的文件 |
| 空输入或空参考集 | 只交输入清单，`coverage=null`，`status=insufficient_evidence` | `reference_set` 为空，`limits` 说明无分母 |
| 超时临近 | 立即落盘当前 `result.json` 并附带 current partial 文件；后续不再启动大解析 | `status=partial`，`runtime.timeout_near=true` |
| `case.json` 缺失或输出契约缺失 | 尝试 `case*.json`；若无契约，按本 Skill 标准字段输出，字段缺失用空值 | `degradations` 记录契约缺失；`contract_fill` 标注“不可用” |
| 同一记录多源重复 | 合并为主记录，保留出处数组；`metrics.dedupe_removed` 报告 | `reference_set.dedupe` 或 `retrieval_pool.dedupe` |
| 撤稿/无法获取全文 | 从分母中排除，写入 `reference_set.excluded`，不算漏检 | `excluded.reason` 注明撤稿或不可得 |
| 材料过大/不可解析 | 跳过文件，不中断整体流程 | `degradations` 列出文件、大小、错误 |

## 9 覆盖率口径与命中判定

### 9.1 覆盖率口径

- 主口径：`coverage = n_hit / n_eligible`，分母 `n_eligible` 为冻结后参考集（排除撤稿、无法获取全文、重复记录）在匹配前锁定的数量。
- `coverage_over_all_refs`：用全部去重后的参考集记录（含排除项）做分母，供保守解读。
- 禁止：以检索结果集自身为分母（循环）；把“没找到”当作“不相关”；把撤稿记录算作漏检。
- 报告 Wilson 95% 置信区间；参考集很小时必须给出不确定性。

### 9.2 命中判定分级

| 层级 | 规则 | 取值 |
|-|-|-|
| `exact_doi` | 归一化 DOI 相等 | 1.00 |
| `identifier` | PMID/PMCID/arXiv/ISBN/OpenAlex 任一相等 | 0.97 |
| `exact_title` | 归一化标题完全相同 | 0