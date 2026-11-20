---
name: paper-quality-review
description: 面向科研论文或研究材料的可溯源质量审查 Skill。单命令运行 scripts/review.py 完成 init→build 并产出 result.json、review_report.md、issues.csv、corpus.json；按事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类检查项给出可定位原句、可复核证据的问题清单。证据不足或材料缺失时显式降级，不编造数据。适用于投稿前自查、审稿准备、结题预审；不替代润色、翻译、查重或录用决定。
---

# 论文质量审查 Skill

## 0. 运行纪律（最高优先级）

你是 Harness Agent。你的任务不是复述论文，而是交付一份结构化、可交办、可复核的质量审查问题清单。所有事实性结论必须能回到原文位置。

- 先执行本包确定性入口生成完整基线；不要在基线前手写或复述全文。
- 脚本产出的结构化 JSON 字段不得手改；Agent 的判断必须通过 merge 文件写入。
- 材料、证据或字段缺失时，必须在 `result.json` 的 `pending_human`、`unchecked`、`errors`、`degradations` 中显式说明，不能假装完成。
- 不确定项标为 `pending_human` 或 `uncertainty`，不凭空补结论。
- 最终退出码必须始终为 `0`；即使失败也要交付合法 `result.json`。

## 1. 适用与不适用

适用：投稿前质量自查、审稿辅助、学位论文或项目材料预审、修订稿复核，以及需要逐条交办修改任务的质量审查。

不适用：语言润色、翻译、查重比对、投稿排版、格式代改、决定文章是否录用。本 Skill 只发现并记录可核查的问题和证据缺口。

## 2. 单命令全流程入口

以现有包为准，单命令基线条目为：

`python3 scripts/review.py --input /input --output /app/output`

该命令将输入解析、材料盘点、候选抽取、证据核验、报告渲染和契约回填串成一条完整工作流：

1. `init`：扫描 `/input` 全部材料，按后缀识别文件类型；解析 `/input/case.json`，取得 `case_id`、任务说明与 `output_contract`；生成源编号、候选抽取、冲突分组和材料台账。
2. `build`：校验候选 `quote` 是否能在提取文本中命中；对缺失或未命中的候选进行确定性兜底抽取；渲染全部产物并写 `result.json`。
3. 自检阶段：脚本完成后运行：

`python3 scripts/checks.py --result /app/output/result.json --corpus /app/output/corpus.json`

工作目录为 `/app/work`；最终实际结果和可编辑产物归 `/app/output`。

## 3. Agent-first 双路径

### 路径 A：确定性兜底（必须始终可用）

运行 `scripts/review.py` 后，即使没有任何 Agent 手工判断，也必须产出实质工作稿：

- 每条问题含 `id`、`facet`、`facet_label`、`severity`、`basis_type`、`quote`、`locator`、`rationale`、`suggestion`、`confidence`、`origin=rule`。
- 每个关键数字或论断需要 `source_id`、`quote` 和 `locator`（文件、页码或段落/句子、字符范围）。
- 在 `degradations` 中诚实记录 `AUTO_EXTRACT`，说明本路径为确定性抽取，未经 Agent 逐条复核。
- 该路径是合法 partial，不代表失败。

### 路径 B：Agent 增强（优先选择，预算不足可跳过）

当模型预算和 900 秒时间允许时：

1. 阅读 `/input/case.json`、`/input/task.md`、`/app/output/corpus.json` 及关键原文片段。
2. 重点核验脚本发现的 `major` 条目，并检查脚本可能漏掉的高价值缺陷。
3. 将新增或修正写入 `/app/work/agent_findings.json`，格式遵循 `references/checklist.md` 中的 agent findings schema。每条 `origin` 必须为 `agent`，并提供可逐字命中的 `quote`。
4. 合并：

`python3 scripts/review.py --input /input --output /app/output --merge /app/work/agent_findings.json`

5. 合并后再次运行 `scripts/checks.py` 自检。
6. 如果 Agent 未做增强，仍要在 `changes` 中写清：是否已由 Agent 核验、核验了哪些 facet、为什么未新增或未修改。不得伪装已完成。

两条路径必须生成同一套产物：`result.json`、`review_report.md`、`issues.csv`、`corpus.json`。

合并后必须在 `changes` 中记录至少以下增益证据字段：

- `baseline_issue_count`
- `agent_finding_count`
- `agent_added`
- `agent_removed_false_positives`
- `agent_corrected_quotes`
- `agent_reviewed_facets`
- `agent_review_completed`

这些字段只反映本轮真实脚本与 Agent 记录，不应虚构分数或外部标准。

## 4. 输入与输出

### 输入

| 项 | 位置 |
|---|---|
| 案件说明 | `/input/case.json` |
| 任务要求 | `/input/task.md` |
| 论文/科研材料 | `/input` 下全部实际文件；支持 PDF、DOCX、XLSX、CSV、JSON、MD、TXT、TeX、HTML 等 |
| 规则与清单 | `references/rules.json`、`references/checklist.md` |

必须读取实际材料内容，不得按文件名、领域标签或文件夹名称假设内容。

### 输出

必须写入 `/app/output`：

- `result.json`：唯一结构化主结果。
- `review_report.md`：供人阅读的审查报告，逐条列问题、位置、严重度、证据与建议。
- `issues.csv`：问题清单表，便于交办和复核。
- `corpus.json`：解析后用段落、句子、章节、页码、字符范围表示的语料，供证据定位。
- 若 `output_contract` 要求 Office、幻灯片或图，还需生成真实渲染 PDF/PNG 预览，并把路径写入 artifacts 或对应字段。

## 5. result.json 契约

`result.json` 必须同时满足两层结构：

1. 顶层字段：

- `case_id`
- `status`
- `issues[]`
- `review`
- `sources[]`
- `metrics`
- `pending_human[]`
- `unchecked[]`
- `uncertainty[]`
- `errors[]`
- `degradations[]`
- `changes[]`
- `runtime`
- `contract_fill`
- `output_contract`

2. 输入的 `output_contract` 必须原样复制到 `result.json.output_contract`，键名不变，值按语义填充；缺失、未完成或无法满足的字段显式设为 `defaulted` 或 `not_checked`，并在 `contract_fill` 中记录缘由。顶层 `case_id` 与 `output_contract` 中要求回显的字段必须一致。

`issues[]` 每条至少包含：

`id`、`facet`、`facet_label`、`check_item`、`severity`、`basis_type`、`title`、`quote`、`locator`、`rationale`、`suggestion`、`confidence`、`review_status`、`verifiable_by`、`evidence`、`quote_verified`、`origin`。

`locator` 至少包含：

`source_id`、`page`（无则 `null`）、`section`、`paragraph_id`、`sentence_id`、`char_start`、`char_end`。

`status` 取值：

- `ok`：无未复核、无未检查、无错误、无降级。
- `partial`：产出完整问题清单，但存在 Agent 未复核、材料未读、少数检查未覆盖、引用待人工复核等。
- `insufficient_evidence`：全文过短、缺少参考文献、无数据/方法/统计等信息，不足以做出正式判断。
- `input_error`：`/input` 缺失、为空、无材料或 `case.json` 损坏且无法恢复。

## 6. 六类审查 facet

| facet | 检查重点 |
|---|---|
| `fact_check` | 摘要/正文/图表/表格间样本量、数据、结果、术语、编号是否一致；占位符、明显数值错误、图表引用缺失 |
| `citation_support` | 正文引用文献是否超范围、有引无文、有文无引、引用格式、无年份、未来日期、外部关键主张无引用 |
| `method_design` | 对照、样本量、抽样、纳入排除、随机/盲法、重复、统计方法、实验设计是否说明或是否可接受 |
| `statistics_report` | p 值是否规范、检验方法、统计量、效应量、均值离散度、置信区间、缺失统计量 |
| `argument_chain` | 假设到结论的推理链、因果/相关混淆、结论外推是否超出数据、局限性讨论 |
| `academic_norms` | 必要章节、伦理/同意/数据可用性/利益冲突/基金声明、图表版权与来源、摘要/关键词/标题规范 |

相关 facet 与材料无关或前提不满足时，写入 `unchecked[]`，不得当作通过。

## 7. 严重度与 basis_type

- `major`：改变结论可信度、可重复性或投稿阻断性问题。
- `minor`：报告或合规缺陷，可在不改做实验情况下修复。
- `info`：改进建议或学科惯例提示，不作为正式缺陷。

`basis_type`：

- `error`：能与原文或学科常识直接冲突的可验证缺陷。
- `insufficient_evidence`：论述缺少必要证据，但尚不能判为事实错误。
- `suggestion`：建议性意见，不应与错误、证据不足混同。

`origin`：

- `rule`：确定性规则引擎触发。
- `agent`：Agent 阅读后新增或修正。

## 8. 证据与误报控制

- 每条正式问题必须有逐字 `quote`，必须能通过对提取文本做空白/标点归一化命中。无法命中的，不得进入 `issues`，只能进入 `pending_human`。
- 不得为了通过验证修改 `quote` 或原文。
- 页码若工具无法提取，以段落、句子、字符范围为权威定位，并把不确定性写入 `uncertainty`。
- 文档级缺陷必须引用最近的真实句子，且在 `evidence.doc_level` 中说明全文计数依据。
- 学科写作惯例、期刊格式差异、作者有意取舍默认不判缺陷；最多 `info` 并注明“核对目标期刊”。
- 相同 facet、相同引文的重复模式必须去重；每个规则设命中上限，防止单一模式灌满清单。
- 只有在前提成立时才触发上下文相关规则，例如：存在文献表、存在统计说明、章节数≥3、全文≥700 词、属于实证研究、使用人类/动物数据等。

## 9. 执行步骤

### 步骤 1：初始化与基线生成

立即执行：

`python3 scripts/review.py --input /input --output /app/output`

如果失败：

- 捕获 traceback，写入 `errors`。
- 若 `result.json` 未生成，写一个最小合法 `result.json`，字段见第 5 节；`status` 按实际填 `input_error` 或 `partial`。
- 保留已生成的中间文件，退出码仍为 `0`。

### 步骤 2：核对材料与契约

阅读 `/app/output/result.json`、`/input/case.json`、`/app/output/corpus.json`：

- `case_id` 正确。
- `output_contract` 全部字段被回显。
- `sources` 覆盖 `/input` 实际可解析材料。
- 若某材料无法解析，在 `degradations` 和 `pending_human` 记录，不把该材料当证据。

### 步骤 3：Agent 增量复核

若有预算：

- 优先核验所有 `severity=major` 规则条目；逐字核对 `quote` 和 `locator`。
- 检查 `fact_check`、`citation_support`、`method_design`、`statistics_report`、`argument_chain`、`academic_norms` 六类是否被错误跳过。
- Agent 新增条目写入 `/app/work/agent_findings.json`，然后合并。
- 没有预算时跳过，保留基线并在 `changes` 说明 `AUTO_EXTRACT`。

### 步骤 4：自检

运行：

`python3 scripts/checks.py --result /app/output/result.json --corpus /app/output/corpus.json`

核对：

- `quotes_verified + quotes_rejected == quotes_total`。
- 所有 rejected 项进入 `pending_human`。
- `review.facet_coverage` 对相关 facet 不是空集合；未覆盖的进 `unchecked`。
- `issues.csv` 与 `review_report.md` 的 issue id 与 `result.json.issues` 一致。
- 磁盘产物与 `output_contract` 字段一一对应。

### 步骤 5：最终回填与退出

- 更新 `status`：如仍有待人工、未检查、错误或降级，不得设 `ok`。
- 更新 `review.summary`、`verdict`、`metrics`、`runtime`、`changes`。
- 确认 `result.json` 顶层与 `output_contract` 双重回显完整。
- 写入所有产物路径。
- 以退出码 `0` 结束。

## 10. 隐藏案例鲁棒性

| 异常 | 处理 |
|---|---|
| `/input` 不存在、为空或无材料 | `status=input_error` 或 `insufficient_evidence`；写合法 result.json 并退出 `0` |
| `case.json` 损坏或缺少 `output_contract` | 错误记入 `errors`；继续解析其他材料；契约字段按语义默认并在 `contract_fill` 说明 |
| PDF 无文本层或解析失败 | 依次尝试 `pdftotext`、`mutool`、内置扫描器；仍失败记录 `engine=none`，该材料标 `material_unreadable` |
| 图片/扫描图/不可读图表 | 不 OCR；图表检查 `not_checked`，不猜测内容 |
| 全文少于 400 字符 | `status=insufficient_evidence`，不推断结论 |
| 引用无法逐字命中 | 降级到 `pending_human`，状态不能为 `ok` |
| 没有章节标题 | 章节结构检查标 `not_checked`，在 `unchecked` 说明 |
| 中途超时或预算不足 | 保存已有合法 `result.json`，`status=partial`，在 `changes` 说明未完成范围 |
| 合并文件格式错误 | 拒绝合并并记录 `pending_human`，保留基线 |
| 意外异常 | 捕获写入 `errors` 和 `degradations`，保留合法 `result.json`，退出 `0` |

## 11. 预算策略

总预算 64 次模型请求 / 900 秒 / 单次响应 16384 tokens。脚本运行不占模型请求。

建议顺序：

1. 步骤 1 脚本基线：0 次模型请求。
2. 步骤 2 契约核对：1–2 次模型请求，只读 `case.json`、`task.md` 摘要和 result 头部。
3. 步骤 3 Agent 复核：优先验证 `major` 条目和高风险 facet；单个案例不超过 10–15 次模型请求。
4. 步骤 4 自检与修复：2–4 次。
5. 剩余预算用于改进 `review_report.md` 的可读性和具体修改建议。

禁止重复通读整篇材料、禁止对同一问题反复生成发现、禁止用模型请求做无谓格式检查。

## 12. 生态复用与文档

本包可复用资源：

- `references/rules.json`：确定性规则集，可被复查、扩展或迁移。
- `references/checklist.md`：审查清单与 agent findings schema，可作为自检清单复用。
- `references/report_template.md`：报告模板。撰写 `review_report.md` 时遵循该结构，但必须用本案例真实内容和真实证据填充，不得把模板示例当真结果。

依赖和资源边界：纯 Python 3.8+ 标准库；离线运行；不调用外部 API；不依赖作者未说明的个人文件或服务。

## 13. 禁止事项

- 不提交预制答案、白板、golden_standard 或虚假 benchmark 分数。
- 不编造用例、数据、引用、DOI、页码、统计量、审稿意见或软件状态。
- 不手工篡改 `result.json`、`corpus.json` 等结构化产物；必须使用脚本命令或 merge 文件。
- 不删除、清空或遗漏基线契约字段与产物。
- 不把脚本生成的骨架、模板当成品。
- 不将学科惯例、格式差异、作者有意取舍判为正式缺陷。
- 不得在材料缺失时仍声称已覆盖检查项。
- 不得因某个脚本入口缺失或某文件无法解析而退出非 0 或放弃全部交付。