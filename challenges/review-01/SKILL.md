---
name: paper-quality-review
description: 面向科研论文或研究材料的可溯源质量审查 Skill。真实解析 PDF/DOCX/XLSX/CSV/JSON/MD/TXT 等材料，按事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类检查项产出固定结构、可定位到原句的问题清单与可复核证据，并在证据不足或材料缺失时诚实降级。脚本只是工具，最终交付物由 Harness Agent 亲自读材料、推导、撰写与制作。
version: 2.0.0
---

# 论文质量审查 Skill

本 Skill 交付固定结构、可交办的问题清单，而不是整篇评语或内容复述。每条问题必须包含检查项、严重度、原文位置、逐字引用、判断依据和修改建议。引用无法在提取文本中逐字命中时，不得作为正式问题输出，只能降级为 `pending_human`。

脚本、规则、模板只负责基线提取、规则命中和格式化。最终交付物由你（Harness Agent）亲自阅读材料、核对证据、修正误报与漏报、撰写结论并回填 `result.json`。禁止把脚本骨架或模板直接当成品，禁止删除、清空或遗漏任何基线契约字段。

## 1. 适用与不适用

适用：投稿前自查、审稿准备、学位论文或项目成果预审、修订稿复核，以及需要按事实证据逐条交办修改任务的质量审查。

不适用：语言润色、翻译、查重比对、期刊排版、决定文章是否录用。本 Skill 只寻找可记录、可复核的缺陷和证据缺口，不评判新颖性或科学重要性。

## 2. 运行时契约

| 项 | 要求 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 及 `/input` 下全部材料 |
| 工作目录 | `/app/work` |
| 最终输出 | `/app/output` |
| 必交文件 | `result.json`、`review_report.md`、`issues.csv`、`corpus.json` |
| 退出码 | 始终为 `0`；失败写入 `result.json` 的 `errors` 与 `degradations` |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 脚本入口 | `scripts/review.py`；规则引擎和报告渲染为 `scripts/checks.py` |
| 资源边界 | 只引用包内真实存在文件；不联网；不依赖未说明的个人文件 |

基线命令：

python3 scripts/review.py --input /input --output /app/output

合并代理核验发现的命令：

python3 scripts/review.py --input /input --output /app/output --merge /app/work/agent_findings.json

自检命令：

python3 scripts/checks.py --result /app/output/result.json --corpus /app/output/corpus.json

## 3. 输出契约

`result.json` 必须始终包含：

- `case_id`
- `status`：`ok` / `partial` / `insufficient_evidence` / `input_error`
- `issues[]`：每条含 `id`、`facet`、`facet_label`、`check_item`、`severity`、`basis_type`、`title`、`quote`、`locator`、`rationale`、`suggestion`、`confidence`、`review_status`、`verifiable_by`、`evidence`、`quote_verified`、`origin`
- `review`：`summary`、`verdict`、`facet_coverage`、`issues_by_severity`
- `sources[]`：`source_id`、`name`、`path`、`kind`、`engine`、`chars`、`pages`、`sha256`、`note`
- `metrics`：按严重度、facet、basis、引用命中情况、规则触发数等统计
- `pending_human[]`
- `unchecked[]`
- `uncertainty[]`
- `errors[]`
- `degradations[]`
- `changes[]`
- `runtime{}`
- `contract_fill`

同时必须原样回填输入 `output_contract` 的全部字段，键名不变、不得遗漏。即使某个字段缺省，也要按字段语义填充或显式标为 `defaulted`，并在 `contract_fill` 中记录。

若 `output_contract` 要求可编辑 Office、幻灯片、图形产物，则除源文件外还必须额外生成真实渲染的 PDF/PNG 预览，并把路径写入 `result.json` 的 artifacts 或对应字段。

## 4. 本题专属执行流程

### 步骤 1：盘点输入与确认契约

输入：`/input/case.json`、`/input/task.md`、`/input` 下全部材料、本 Skill 的 `references/rules.json`、`references/checklist.md`。

动作：
- 列出 `/input` 树中全部文件，按后缀识别类型，不按文件名或领域标签猜测内容。
- 解析 `case.json`，提取 `case_id`、`task_instruction`、`output_contract` 的全部键；若 JSON 损坏，把错误记入 `errors`，继续处理其余材料。
- 识别材料文件与格式：PDF、DOCX/DOC、XLSX/XLS、CSV/TSV、JSON、MD、TXT、TeX、HTML、图片等。
- 把材料清单与契约键保存到 `/app/work/input_inventory.json`，便于后续核对。

输出：材料清单、契约键列表、待解析文件队列。

失败分支：
- `/input` 不存在、为空或没有任何材料：`status` 设为 `input_error` 或 `insufficient_evidence`，仍写合法 `result.json`，退出码 `0`。
- `case.json` 损坏或缺少 `output_contract`：记录错误，继续解析其他文件；`contract_fill` 中标记缺失字段为默认或待定。

### 步骤 2：真实解析材料

输入：步骤 1 的待解析文件队列。

动作：
- 对 PDF 使用 `pdftotext`，不可用则 `mutool`，再不可用则内置流扫描器；提取文本、段落、句子、章节、页码（若可提取）和字符偏移。
- 对 DOCX/XLSX 使用 `zipfile` 与 XML 剥离读取文本；对 CSV/TSV、JSON、MD、TXT、TeX、HTML 按相应方式读取。
- 生成 `/app/output/corpus.json`，包含段落、句子、章节、来源文件、页码和字符范围，保证后续每条引用可回到提取文本。
- 同时记录每个材料的 SHA-256、字符数、页数、解析引擎和状态。

输出：`corpus.json`、`sources[]` 基础信息、解析状态。

失败分支：
- 文件不可读、损坏或格式不支持：在 `degradations` 中记录，在 `pending_human` 中增加 `material_unreadable` 条目，并将依赖该材料的检查项标为 `not_checked`。
- 图片不进行 OCR：列为未读材料，相关图表检查标 `not_checked`，绝不猜测内容。
- 全文少于 400 字符：`status` 设为 `insufficient_evidence`，不再推断任何结论。

### 步骤 3：运行基线脚本，产出全套交付物

输入：`/input`、`/app/output`。

动作：立即执行：

python3 scripts/review.py --input /input --output /app/output

该脚本会产出基线版 `result.json`、`review_report.md`、`issues.csv`、`corpus.json`，并完成规则命中、引用验证、报告渲染和契约回填。

输出：完整基线文件。

失败分支：
- 脚本异常：把 traceback 写入 `errors`，若 `result.json` 未生成则手工构造一个合法 `result.json`，至少包含 `case_id`、`status`、`issues`、`review`、`sources`、`metrics`、`pending_human`、`unchecked`、`uncertainty`、`errors`、`degradations`、`changes`、`runtime`、`contract_fill`，并保留已生成的任何中间文件。退出码仍为 `0`。

重要：该基线是后续增强的基础，任何情况下都不得删除、清空或遗漏这些文件和契约字段。即使后续发现基线存在误报或漏报，也只能在基线之上增补 `origin=agent` 的条目或在 `changes` 中记录修正，不能用新文件替代基线。

### 步骤 4：Agent 亲自复核与增量增强

输入：`/app/output/corpus.json`、基线 `result.json`、原始提取文本或可读原文。

动作：
- 随机或按风险排序抽查规则发现：逐字核对 `quote` 与提取文本是否一致；检查 `locator` 是否指向正确段落/句子/字符范围；检查 `severity` 是否与定义一致。
- 对六大类检查项中脚本可能漏掉的高价值缺陷进行语义审查：事实/数字一致性、引用支持、方法设计、统计报告、论证链、学术规范。
- 对脚本可能产生的误报进行修正：如果某条规则命中是学科写作惯例或作者有意取舍，应在 `changes` 中记录并降级为 `info` 或剔除，同时说明理由。
- 将新增或修正写为 `/app/work/agent_findings.json`，格式遵循 `references/checklist.md` 中的 agent findings schema。
- 执行合并：

python3 scripts/review.py --input /input --output /app/output --merge /app/work/agent_findings.json

合并后，脚本会再次进行引用验证、去重、合并与重排序；无法逐字命中的发现会被拒绝并进入 `pending_human`。

输出：包含 `origin=agent` 条目的更新版 `result.json`、`review_report.md`、`issues.csv`。

失败分支：
- `agent_findings.json` 格式错误：脚本拒绝该文件并记录到 `pending_human`，基线产物不受影响。
- Agent 因预算不足未能完成语义审查：必须保留基线，并在 `changes` 中如实说明 agent review 未完成或只核验了部分条目；不得伪装成已完成。

如果 Agent 核验后没有新增或修正，也必须至少记录一条 `changes`，说明核验范围、核验时间、基于 `corpus.json` 的检查项和结论，例如：`agent_reviewed=true`、核验了哪些 facet、未发现需修改的规则发现。

### 步骤 5：自检 rubric 与覆盖度

输入：更新版 `result.json`、`corpus.json`、`review_report.md`、`issues.csv`。

动作：
- 执行：

python3 scripts/checks.py --result /app/output/result.json --corpus /app/output/corpus.json

- 核对 `review.facet_coverage`：事实核验、引用支持、方法设计、统计报告、论证链、学术规范等与当前材料相关的 facet 是否都已被覆盖；未覆盖的必须出现在 `unchecked[]`，不能静默视为通过。
- 核对 `metrics` 中 `quotes_verified + quotes_rejected == quotes_total`；所有 rejected 条目都出现在 `pending_human`。
- 核对 `issues.csv` 与 `review_report.md` 是否与 `result.json` 的 issue id 一致且都存在。
- 核实磁盘文件与 `output_contract` 字段一一对应：每个要求的产物都有对应路径或字段，缺失项立即补齐。

输出：自检结果、缺失项清单。

失败分支：
- 自检发现字段或文件缺失：优先补齐，再更新 `contract_fill`、`unchecked`、`changes` 后重新检查。
- 某个 facet 因材料限制无法检查：在 `unchecked[]` 中说明原因，如“无参考列表”“无统计说明”“无章节结构”等；绝不虚假覆盖。

### 步骤 6：最终回填并退出

输入：自检通过或可接受的 `result.json`。

动作：
- 确保 `result.json` 包含 `case_id` 与 `output_contract` 的全部键。
- 更新 `status`：当且仅当没有 `pending_human`、没有 `unchecked`、没有错误或降级时才能设为 `ok`；否则使用 `partial` 或 `insufficient_evidence`。
- 更新 `review.summary`、`verdict`、`metrics`、`changes`、`runtime` 等，反映真实运行过程。
- 记录所有关键文件路径到 artifacts 字段；若 contract 要求 Office/幻灯片/图形产物，确认真实渲染的 PDF/PNG 预览已生成并记录路径。
- 最后以退出码 `0` 结束。

失败分支：
- 遇到任何未预期的异常：捕获并写入 `errors`，保留已生成的合法 `result.json`，退出码仍为 `0`。

## 5. 预算策略

总额：64 次模型请求 / 900 秒。模型请求只用于需要语义理解或判断的步骤，脚本运行不占模型请求。

建议分配：

- 步骤 1 盘点输入、确认契约：1–2 次模型请求，只需阅读 `case.json` 与 `task.md` 摘要，不逐字阅读全文。
- 步骤 2 材料解析：0 次模型请求，全部由脚本执行。
- 步骤 3 基线运行：0 次模型请求，脚本执行。
- 步骤 4 Agent 复核与增强：每个材料最多 3 次请求，每次聚焦一个高价值 facet 或一类关键证据；单个案例最多 10–15 次。优先复核规则命中数量最多的 facet，并核验任何可能影响结论的 `major` 条目。
- 步骤 5–6 自检与回填：2–4 次模型请求，用于处理自检发现和写最终结论。

优先级：

1. 必须先产出完整基线：`result.json` + `issues.csv` + `review_report.md` + `corpus.json`，一旦生成即视为诚实 partial。
2. 再选择高价值增强：数字/引用/方法/统计中风险最高的条目进行 Agent 核验。
3. 预算不足时跳过低价值增强，但要保留基线并如实记录未完成部分。

禁止：

- 重复通读同一完整材料；
- 为同一问题反复生成新发现；
- 消耗模型请求进行无意义格式检查或简单文本替换。

## 6. 六类审查 facet

| facet | 典型检查项 |
|---|---|
| `fact_check` | 摘要/方法/结果间样本量冲突、图/表编号引用但缺失、数据前后不一致、占位符、明显数据错误 |
| `citation_support` | 引文编号超出文献表、有引用却无文献、未引用条目、引用格式错误、无年份、未来日期引用、外部主张无引用 |
| `method_design` | 缺对照组、缺样本量、未说明随机化/盲法、体外实验无重复、统计分析方法缺失、纳入排除标准缺失、样本量无理由 |
| `statistics_report` | `p = 0.000`、p 未说明检验方法、无统计量、无效应量、均值无离散度、p 未给置信区间 |
| `argument_chain` | 观察性数据使用因果措辞、无统计支持却写“证明/证明性”、无局限性讨论、未与先前文献比较 |
| `academic_norms` | 缺方法/结果/讨论/结论、伦理/同意/数据可用/利益冲突/基金声明缺失、摘要过长、关键词数量不符、标题过长 |

完整规则、阈值、触发条件见 `references/rules.json` 和 `references/checklist.md`。严重度定义：

- `major`：改变可信度/可重复性/结论，或属于投稿阻断性缺失。
- `minor`：报告或合规缺陷，可在不改做实验的情况下修复。
- `info`：改进建议。

`basis_type`：`error` 为可验证缺陷，`insufficient_evidence` 为证据不足，`suggestion` 为建议。`origin`：`rule` 为确定性规则命中，`agent` 为 Agent 语义阅读后新增或修正。

## 7. 证据与误报控制

- 每条 problem 必须有 `quote`，且该 quote 必须能在 `corpus.json` 或提取文本中经过空白/标点归一化后逐字命中。不能命中则自动降级为 `pending_human`，不能修改原文使其通过。
- `locator` 必须包含 `source_id`、`page`（若无则为 `null`）、`section`、`paragraph_id`、`sentence_id`、`char_start`、`char_end`。
- 页码来自解析工具，缺省时以段落/句子/字符范围为权威定位，并在 `uncertainty` 中说明。
- 不编造页码、图号、统计量、DOI、参考文献或审稿意见。文档级缺陷必须引用最近的真实句子，并在 `evidence.doc_level` 记录全文计数。
- 上下文相关规则只在满足前提条件时触发（如实证研究、使用人类/动物数据、存在文献表、存在图表标题、章节数≥3、全文≥700 词）。前提不满足时标记 `not_checked` 而非通过。
- 如果无法识别任何章节标题（如扫描版或摘要片段），章节和声明类检查应抑制并记录为未执行。
- 学科写作惯例、格式差异或期刊特有要求默认不作为缺陷；最多作为 `info` 建议，并注明“核对目标期刊”。
- 相同引文和相同 facet 的条目应去重；每条规则设上限（例如 4 条命中），防止单一模式灌满清单。

## 8. 隐藏案例鲁棒性

任何情况下都要产出合法 `result.json` 且退出码 `0`。

| 异常情况 | 处理方式 |
|---|---|
| `/input` 不存在、为空或无材料 | `status=input_error` 或 `insufficient_evidence`；写错误，仍在 `/app/output` 生成合法文件，退出 `0` |
| `case.json` 损坏或缺少 `output_contract` | 错误记入 `errors`，继续解析其他材料；契约字段按语义默认或标记默认 |
| 材料损坏或格式不支持 | `degradations` 记录，材料不用于证据；依赖该材料的检查标 `not_checked` |
| PDF 无文本层 | 尝试 `pdftotext`、`mutool`、内置扫描器；仍失败则 `engine=none`，加 `pending_human`，文本检查跳过该文件 |
| 图片或不可读图表 | 不 OCR；标记 `material_unreadable`，图表相关检查 `not_checked` |
| 全文少于 400 字符 | `status=insufficient_evidence`；不推断结论 |
| 无章节标题 | 章节结构检查 `not_checked`；在 `unchecked` 中说明 |
| 超时或预算不足 | 立即保存已有的合法 `result.json`，状态设为 `partial`，在 `changes` 和 `unchecked` 中说明未完成部分 |
| 引用无法逐字命中 | 条目降级到 `pending_human`，状态为非 `ok` |
| Agent findings 格式错误 | 拒绝并记入 `pending_human`，基线不受影响 |
| 意外异常 | 捕获全部异常，写入 `errors` 和 `degradations`，保留合法 `result.json`，退出 `0` |

诚实性要求：`status`、`sources`、`uncertainty`、`changes`、`pending_human`、`unchecked` 必须反映真实运行状态。不确定或材料不足要显式标注，不得编造数据、引用、分数或软件状态。可为空数组，但不得假装不存在。

## 9. 评分维度与交付自证对照

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果：任务完成度 | 固定结构、可交办