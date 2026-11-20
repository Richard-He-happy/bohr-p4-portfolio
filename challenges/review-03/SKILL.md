---
name: methods-stats-review
description: 让 Harness Agent 对科研稿件完成可复核的研究方法与统计审查。一键生成证据定位、逐字引用、缺陷类型、严重度、修改建议、待复核项和 honest result.json；Agent 可在确定性基线之上真实阅读材料并增量改进。覆盖研究设计、变量定义、统计方法、样本量、结果报告与六类审查面。
version: 2.2.0
---

# 研究方法与统计审查 Skill

## 0. 最高原则：分数来自可核验，不来自意见数量

本 Skill 用于把 `/input` 中的科研材料变成一份可交给作者逐条回复的审查单。平台评分最看重四件事：

1. 每条审查意见能不能回到原文的具体位置。
2. 严重度是否与缺陷性质相称，而不是一律写“重大缺陷”。
3. 是否区分“作者没有报告”和“作者做错了”。
4. 复核人能否按记录独立重跑得到同一条结论。

因此，本 Skill 设计为：先用脚本生成确定性、带定位、带逐字引用的完整基线；再由 Agent 阅读原文、核实并增量改进。即使 Agent 不改进，也必须得到一份可用的、诚实的审查交付物。

## 1. 单命令全流程入口

首先执行：

`cd /skills/weekly-skill && python3 scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部依次完成：

- init：盘点 `/input` 全部材料，建立 source_id；抽取文本；生成候选 finding；做冲突分组。
- build：如果 `/app/work/draft.json` 存在，则采用 Agent 草稿；否则使用 init 台账中的确定性抽取结果生成实质工作稿。随后渲染全部产物，包括 `review_report.md`、`evidence_table.json`、`claims.json`、`pending_human.json`、`verification.json`、`result.json`。
- selfcheck：对产物与契约进行自检，更新 `verification.json`。异常也必须以 exit 0 结束。

执行后读 `/app/output/result.json`。若 `status` 为 `partial` 或存在 `errors`，不要隐藏，要如实保留并继续补救。

## 2. Agent 路径：真实阅读与增量改进

`run` 可以直接完成全流程。若预算允许，Agent 应采用以下双路径改进：

### 2.1 Agent 先 init

`cd /skills/weekly-skill && python3 scripts/main.py init --input /input --output /app/output --work /app/work`

然后读取：

- `/app/work/ledger.json` 或 init 台账，确认 source_id 与文件名对应。
- `/app/output/extracted/` 下抽取出的文本。
- `/input` 原始材料。必须读实际文件，不能只看文件名或领域标签。

Agent 将真实判断写进 `/app/work/draft.json`。`draft.json` 是草稿，可以编辑；结构化最终 JSON 由脚本生成，不能手工篡改。

每个 finding 至少包含：

- `finding_id`
- `domain`：research_design / variable_definition / statistical_method / sample_size_power / result_reporting
- `facet`：fact_check / citation_support / method_design / statistical_report / argumentation / academic_norm
- `severity`：critical / major / minor / advisory
- `finding_type`：factual_error / evidence_insufficient / normative_issue / suggestion
- `locator`：如 `file#page/para`、`file#table/figure`
- `quote`：原文逐字引用
- `evidence`：判断依据
- `revision`：可执行的修改建议
- `confidence`：high / medium / low
- `needs_human`：true / false

写完后执行：

`cd /skills/weekly-skill && python3 scripts/main.py build --input /input --output /app/output --work /app/work`

再执行：

`cd /skills/weekly-skill && python3 scripts/verify.py --input /input --output /app/output --work /app/work`

### 2.2 无 draft 的确定性兜底

如果 `/app/work/draft.json` 不存在，`build` 会使用 init 台账中的确定性抽取生成工作稿。该模式必须：

- 保留逐字 quote 与 locator。
- 只基于可识别文本生成结论。
- 在 `degradations` 中记录 `AUTO_EXTRACT`。
- 对不能判断的项写入 `pending_human`，不得补造结论。

## 3. 证据与定位规则

每条意见必须：

- 有 `[S#]` 来源编号。
- 有文件内定位：章节、页码、段落号或表号/图号。
- 有原文逐字引用。只有确有逐字文本时才标记为 exact quote；否则标记为 paraphrase 或 `quote_unavailable`，并说明原因。
- 涉及数字、p 值、置信区间、样本量、自由度、效应量时，必须同时给出原文表达和判断依据。

来源编号示例：`[S1]` 表示第一种材料。`locator` 要尽量精确，例如 `paper.pdf#section3.2/para4` 或 `supplement.docx#Table2`。

禁止：

- 使用不存在的章节、表号或页码。
- 把“未报告”写成“错误”。
- 把方法学上可接受的做法写成硬伤。
- 用材料标签或外界常识代替材料原文证据。

## 4. 审查覆盖与判定口径

必须覆盖五个检查面：

1. research_design：研究设计、对照、分组、盲法、偏倚控制、主要终点与假设。
2. variable_definition：暴露、结局、协变量、分组变量、测量方式、编码、分类切点、缺失值处理。
3. statistical_method：检验方法与数据结构、分布假设、样本独立性、多重比较、重复测量、交互项、敏感性分析。
4. sample_size_power：样本量估算依据、效应量来源、α、把握度、实际入组、失访、剔除。
5. result_reporting：效应量与置信区间、精确 p 值、统计量与自由度、图表与正文一致性、报告规范。

同时覆盖六类审查面：

- fact_check：事实与数字是否真实、一致。
- citation_support：引用是否能支持该论断。
- method_design：方法与设计是否匹配。
- statistical_report：统计报告是否完整、准确。
- argumentation：论证链是否成立。
- academic_norm：学术规范问题。

不必为每个组合伪造问题。若某检查面无问题，在对应领域总结或 finding 中写明 `no_finding_in_this_scope`，并给出用于核查的原文位置。对于无法判断的事项，写入 `pending_human`。

严重度定义以 `references/review_checklist.md` 为准，统计规则以 `references/stat_rules.md` 为准。输出 schema 以 `references/schema.md` 为准。若三者与本文冲突，以 `references/schema.md` 和 `/input/case.json` 中的 output_contract 为准。

## 5. 交付物与 result.json 双契约

最终产物必须放在 `/app/output/`，至少包括：

- `result.json`：主结果。
- `review_report.md`：干净、可读的审查单正文。
- `evidence_table.json`：每条 finding 的证据、quote、locator、来源。
- `claims.json`：结构化 finding 条目。
- `pending_human.json`：无法确认、需要人工复核的条目。
- `verification.json`：自检结果。
- `runlog.md`：运行过程、命令、重要判断、改进记录。

`result.json` 必须采用双契约：

- 所有 `output_contract` 字段在 `result.json` 顶层出现一次。
- 在 `result.json` 的 `nested output_contract` 字段中再出现一次。
- 两处必须包含相同 `case_id`。

顶层至少包含：

- `case_id`
- `status`：pass / issues / review / partial
- `created_at`
- `input_files`
- `sources`
- `counts`
- `coverage`
- `findings`
- `pending_human`
- `uncertainty`
- `errors`
- `degradations`
- `changes`
- `output_contract`

如果 `/input/case.json` 中存在原题定义的 `output_contract` 字段，必须原样并入顶层和 `output_contract`。不要发明不存在的字段；若题目未明确，字段名以 `references/schema.md` 和脚本产物为准。

`result.json` 只记录可观察证据。不得自造金标准、rubric 自评分、benchmark 分数或“预计得分”。改进记录只写可观察差异，例如 `baseline_auto_extraction` → `agent_reviewed`。

## 6. 异常处理与预算

必须对以下情况诚实处理：

- 材料缺失、缺页、扫描件无法 OCR。
- 图表无法解析。
- 统计输出缺失。
- 中英文混杂但可读。
- 材料不足以判断。
- PDF/DOCX 解析失败。
- `case_id` 缺失。

处理方式：

- 可解析则继续做部分审查。
- 不可解析则在 `errors` 中记录文件、原因和影响范围。
- 不能判断的进入 `pending_human`。
- 绝不编造缺失的软件状态、科学数据、方法或统计结果。
- 部分结果也必须写 `status=partial`，并说明边界。

如果脚本失败，Agent 必须手写合法 `result.json` 到 `/app/output`，写明错误、限制、缺失项。不要只保留 traceback。

预算限制：总预算约 64 次模型请求、900 秒。推荐先执行一次单命令基线。剩余请求用于读关键原文、核验 quote/locator、补充 draft。不要在模型侧重新抽取全文。接近 80% 预算时停止改进，确保 `result.json` 合法、`status` 诚实、交付物完整。

## 7. 结束前自检清单

逐项确认：

- `/app/output/result.json` 可解析且包含 case_id。
- `result.json` 顶层和 `output_contract` 中都有契约字段。
- `review_report.md`、`evidence_table.json`、`claims.json`、`pending_human.json`、`verification.json` 存在且非空。
- 每个 finding 都有 domain、facet、severity、finding_type、locator、quote 或 quote_unavailable、evidence、revision。
- 每个数字或统计判断都有 `[S#]` 来源和 locator。
- 没有把“未报告”写成“错误”。
- 没有编造章节、表号、页码、统计数据或软件状态。
- `status` 与 `errors`、`degradations`、`pending_human` 一致。
- `changes` 记录了 Agent 是否实际复核、是否使用 AUTO_EXTRACT。
- 所有异常均已 exit 0 或已写入 `result.json`。

若任一文件缺失或字段不完整，先修复再提交。修复结构化 JSON 应通过调用脚本完成；正文型 Markdown 可由 Agent 直接编辑。

## 8. 禁止项

- 不提交预制答案、正式测试输出或藏好的三个案例结果。
- 不手工编辑 `result.json`、`claims.json`、`evidence_table.json` 的键结构。
- 不删除脚本生成的基线文件。
- 不声称未执行的命令已成功。
- 不自造 rubric 分数、白板或金标准。
- 不做文献检索、全文翻译、语言润色或代写投稿决策。
- 不依赖外部网络、未声明的个人文件或远程服务。
- 不使用模糊意见代替可定位、可核验的审查条目。

运行语言：材料为中文时用中文输出；材料为英文时用英文输出；混杂材料可双语，但 finding 的 quote 必须保留原文语言。