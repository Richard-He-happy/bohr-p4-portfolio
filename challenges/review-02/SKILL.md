---
name: review-fact-check
description: Evidence-bound review of manuscripts and research materials for citation/fact verification. Instructs the Harness Agent to run scripts as tools, then personally read and verify materials, derive findings, and produce complete deliverables (result.json, review_report.md, issues.csv, evidence_index.json, citation_pairs.json, previews as applicable). Never fabricates references, page numbers, statistics, or verdicts.
version: 1.1.0
---

# review-fact-check

把“引用与事实核验”做成可交付、可复核的审查结果：条目化问题清单（位置 / 原文 / 判定 / 严重度 / 修改建议）+ 引用支持矩阵 + 待复核与未检查项。**脚本只是工具；最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本骨架或模板输出直接当成品。**

不做论文润色、不代写综述、不替代作者对结论的判断。被引文献正文不在输入中时，“是否支持该句”只能进 `pending_human`，不得凭标题猜测。

## 1. 运行契约与目录约定

- 输入：`/input`（含 `case.json`、`task.md` 及题面规定的材料）；工作目录：`/app/work`；最终产物：`/app/output`。
- 必须真实解析材料内容（用 `pdf-text-tool` 等工具），不得依据文件名或领域标签猜测/补造内容。
- 必须产出 `/app/output/result.json`，包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。
- 可编辑 Office/幻灯片/图形产物必须额外给出真实渲染的 PDF/PNG 预览。
- 运行脚本（均为 Python 标准库，不联网，不依赖当前工作目录）：

```bash
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --input /input --output /app/output --findings /app/work/findings.json   # 可选第二遍
python3 scripts/verify.py --input /input --output /app/output                                   # 自检
```

- `scripts/main.py` 生成基线全套交付物；`scripts/verify.py` 校验 quote 与契约。两者只作工具，**不能替代 Agent 亲自核验与撰写**。
- 输出契约顶层字段固定：`skill`、`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`task_summary`、`issues`、`review_summary`、`citation_support_matrix`、`evidence_index`、`pending_human`、`uncertainty`、`sources`、`errors`、`degradations`、`changes`、`rejected_findings`、`output_contract`、`contract_unmapped_fields`、`verification`、`runtime`、`artifacts`。
- 同目录另出：`review_report.md`、`issues.csv`（UTF-8-SIG）、`evidence_index.json`、`citation_pairs.json`、`run.log`。
- 任何异常下退出码恒为 0，且必须存在合法 `result.json`。

## 2. 执行流程（必须按顺序，编号步骤）

### 步骤 0：盘点输入与输出契约

- **输入**：`/input/task.md`、`/input/case.json`、材料文件列表。
- **动作**：
  1. 读取 `task.md` 与 `case.json`，提取 `case_id`、`output_contract`、材料路径/说明、评分相关约束。
  2. 递归扫描 `/input` 下所有文件，记录真实存在的材料路径。
- **输出**：`/app/work/task_notes.json`（含 case_id、output_contract 键、材料清单、token/时间预算）。
- **失败分支**：`case.json` 缺失或坏 JSON → 继续，记 `errors[]`；`output_contract` 缺失 → 使用默认核心字段并在 `contract_unmapped_fields[]` 记录。

### 步骤 1：运行基线脚本，落盘 honest partial

- **输入**：步骤 0 的材料路径与契约。
- **动作**：运行 `python3 scripts/main.py --input /input --output /app/output`，生成全套基线交付物。
- **输出**：`/app/output/result.json`、`review_report.md`、`issues.csv`、`evidence_index.json`、`citation_pairs.json`、`run.log`。
- **失败分支**：脚本崩溃或异常 → 手动构造最小合法 `result.json`（包含所有顶层字段，`status="input_error"` 或 `partial`，`issues=[]`，`errors` 记录异常），并落盘其他文件为空模板。**此步骤完成后，partial 已可交付。**

### 步骤 2：真实解析材料，构建证据索引

- **输入**：`/input` 下所有材料文件。
- **动作**：
  1. 使用 `pdf-text-tool` 或平台提供的文档解析工具真实解析每个 PDF/DOCX/CSV/图片等；对于扫描件尝试 OCR。
  2. 对关键段落记录：文件名、页码、段落号、字符偏移、逐字原文。
  3. 抽查脚本已抽取文本是否与实际材料一致；发现不符即修正。
- **输出**：`/app/work/parsed_materials.json`（或 Markdown 笔记），包含 `locator`、`quote`、`section`。
- **失败分支**：某材料无法解析/损坏 → 跳过该材料，记 `degradations[]` 与 `uncertainty[]`，不编造内容；图片无 OCR → 跳过并声明。

### 步骤 3：Agent 亲自核验与推导

- **输入**：步骤 2 的解析文本 + 步骤 1 的基线 `issues` 与 `citation_support_matrix`。
- **动作**：
  1. 逐条检查基线 `issues` 的 `quote` 是否逐字存在、`locator` 是否指向正确位置、判定是否与引文语义一致。
  2. 补充脚本可能漏掉的、由六类检查覆盖的问题：引用支持、事实数值、统计报告、方法设计、论证链、学术规范。
  3. 对每条 finding 给出：`status`（`issue` 或 `pending_human`）、`severity`、`certainty`、`claim`、`suggested_fix`。
  4. 对无法确认或外部信息不足的条目，标 `pending_human` 并写明需要什么证据；不得编造数据、引用、分数。
- **输出**：`/app/work/agent_verification.json`（含 `verified_issues`, `updated_issues`, `rejected_findings`, `pending_human`, `conflicts`）。
- **失败分支**：无法核验 → 进入 `pending_human[]`；quote 不匹配 → 拒绝合并，进入 `rejected_findings[]`；不确定不写结论。

### 步骤 4：撰写完整报告并回填 result.json

- **输入**：步骤 3 的核验结果 + 基线交付物。
- **动作**：
  1. 基于核验结果更新 `issues`、`review_summary`、`citation_support_matrix`、`evidence_index`、`pending_human`、`changes`。
  2. 补全 `output_contract` 所有字段：键名原样保留，按语义映射填入；未识别字段保留 `null` 并记入 `contract_unmapped_fields`。
  3. 重写 `review_report.md`、`issues.csv`、`evidence_index.json`，确保与 `result.json` 一致。
  4. 将 `changes` 记录为真实修改过程（如“Agent 核验后修正引用支持判定 CP-003 为 partial”）。
- **输出**：最终 `/app/output` 全套文件。
- **失败分支**：时间不够 → 保留步骤 1 基线 `result.json`，仅补写 `changes[]` 与 `degradations[]`，确保不破坏既有字段。

### 步骤 5：自检 rubric 与契约

- **输入**：`/app/output` 全部文件。
- **动作**：
  1. 运行 `python3 scripts/verify.py --input /input --output /app/output`。
  2. 核对 `output_contract` 字段与 `result.json` 键一一对应；检查文件是否齐全；检查 `status` 与 `errors/degradations/pending_human` 一致。
- **输出**：`/app/output/validation.txt`（包含验证结果）。
- **失败分支**：`verify.py` 显示 failed>0 → 优先修复 quote 不匹配或字段缺失；无法修复则如实写入 `degradations[]` 与 `errors[]`，仍保持退出码 0。

## 3. 预算策略（64 次模型请求 / 900 秒）

- 本地脚本运行不计入模型请求；模型请求主要消耗在读取文件、核验和撰写。要避免无意义循环与冗余调用。
- 建议分配：
  - 步骤 0-1：0-5 次请求（读 `task.md`/`case.json`，运行脚本）。
  - 步骤 2：15-25 次请求（解析关键材料，优先正文、图表、参考文献；跳过附录和已有基线不需要的全文）。
  - 步骤 3：20-30 次请求（核验高严重度 `major` 和 `confirmed/likely` 的 issues，优先引用支持与数值一致性）。
  - 步骤 4：5-10 次请求（更新报告与 JSON）。
  - 步骤 5：2-5 次请求（自检与修复）。
- 当预算不足时：只跑步骤 0-1，保留基线 partial；或仅核验前 5-10 条 `major` 风险最高的 issues；跳过第二遍全量语义分析。
- **每完成一个步骤即落盘一次 `result.json`**；接近 900 秒时立即停止，确保合法 partial 存在。
- 避免重复读取同一文件：将解析内容写入 `/app/work/` 复用。

## 4. 隐藏案例鲁棒性与降级

| 情况 | 处理 | 记录位置 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续运行，用空 case | `errors[]` |
| `output_contract` 缺失或字段无法识别 | 使用默认核心字段，保留原键名并填 `null` | `contract_unmapped_fields[]` |
| PDF 无文本层/扫描件 | 先 `pdftotext`，再内置解析，再 OCR；均失败则跳过该材料 | `degradations[]` + `uncertainty[]` |
| 图片无 OCR | 跳过并声明 | `degradations[]` |
| 材料格式不支持或损坏 | 跳过该文件，不影响整体 | `degradations[]` |
| 空输入 | 输出合法 `result.json`：`status="input_error"`，`issues=[]`，`errors` 说明 | `errors[]` |
| 脚本崩溃 | 手动构造最小 `result.json`，退出 0 | `errors[]` |
| 第二遍 quote 不匹配 | 拒绝合并，标 `pending_human` | `rejected_findings[]` + `pending_human[]` |
| 规则文件缺失 | 仅跑代码级检查 | `degradations[]` |
| 时间耗尽 | 保留已落盘的 partial，补 `degradations[]`，退出 0 | `degradations[]` |

**任何情况下，最终退出码必须为 0，且 `/app/output/result.json` 存在且为合法 JSON。**

## 5. rubric 维度 → 交付要求 → 自证方式对照表

| rubric 维度 | 交付要求 | 自证方式 |
|---|---|---|
| 任务完成度（15 分） | 条目化问题清单，覆盖六类检查，给出位置、原文、判定、严重度、修改建议；不是一段总体评价 | `issues` 数组、`review_report.md` 中每条 issue 有 `locator`/`quote`/`suggested_fix` |
| 结果正确性（15 分） | 判定与引文语义一致，来源真实，证据定位准确；区分“引用存在”与“引用支持结论” | `citation_support_matrix` 各 pair 有 `verdict` 和 `reason`；`issues` 的 `quote` 逐字存在 |
| 结果完整性（5 分） | 覆盖事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类，以及方法、结果、讨论关键章节 | `review_summary.by_kind` 有各类计数；`evidence_index` 有对应证据 |
| 结果可核验性（5 分） | 每条结论能被按记录回查：定位串、原文摘录、来源链接或快照、判定依据与版本 | `evidence_index` 映射 issue_id → locator+quote；`sources` 记录材料版本 |
| 质量增益（15 分） | 相比基础 Agent，提升召回、定位精度、误报控制 | `verification` 字段记录 Agent 亲验过程中的 `verified`/`rejected` 数量；`changes` 记录修正 |
| 效率增益（5 分） | 减少逐条回查、重复检索、人工返工 | 基线脚本自动跑完六类；Agent 只核验高价值条目；记录运行时长 |
| 增益可验证性（5 分） | 同输入公平对照证明改进 | 保留基线产物与 Agent 增强后产物对照；`changes` 列出增强前后差异 |
| 新增能力（5 分） | 引文与结论语义对齐、段落级证据定位、来源版本与撤稿状态核验、严重度分级 | `citation_support_matrix` 的语义对齐判定；`locator` 到段落和字符；`pending_human` 标记外部状态 |
| 方法改进（5 分） | 判定规则、证据组织方式与分级策略带来实质改进 | `references/playbook.md` 定义支持程度；`references/checks.json` 的 regex+守卫规则；`rejected_findings` 体现误报控制 |
| 创新证据（5 分） | 证明创新点相对现有方案的边界与价值 | `SKILL.md` 中明确“脚本是工具，Agent 亲自推导”；`verification` 展示 Agent 实际核验过程 |
| 调用与易用性（3 分） | Agent 能正确触发和调用，用户能按说明独立完成审查 | `SKILL.md` 提供命令与示例；`scripts/main.py --help` 可运行 |
| 运行稳定性（4 分） | 不同材料形态、不同学科文本、重复运行下持续产出可复核结论 | 异常降级表；退出码 0；`verify.py` 校验 quote 与契约 |
| 异常处理（3 分） | 对原文取不到、PDF 无法解析、引文歧义、撤稿/版本不一致等识别与处置 | `uncertainty[]`、`pending_human[]`、`degradations[]` 记录具体处置 |
| 文档完整性（3 分） | 使用说明、依赖、配置、示例、适用范围、限制、维护信息齐全 | `SKILL.md` 文件清单、依赖说明、最小示例、边界章节 |
| 资源可复用性（4 分） | 作品本体、判定规则、定位模板、题集与金标准可复跑 | `references/checks.json`、`references/playbook.md`、`references/io_contract.md` 均为文本资源 |
| 分享推广价值（3 分） | 沉淀可分享的审查案例、判定经验、题集和真实应用价值 | 脚本产出结构化 CSV/JSON/Markdown；`evidence_index` 可扩展 |

## 6. 自检清单（提交前逐项检查）

1. 运行 `python3 scripts/main.py --help` 退出 0；脚本路径有效。
2. `/app/output` 下 `result.json`、`review_report.md`、`issues.csv`、`evidence_index.json`、`citation_pairs.json`、`run.log` 均存在。
3. `result.json` 包含全部顶层固定字段（见第 1 节），且 `case_id` 与实际输入一致。
4. `output_contract` 键与 `result.json` 键逐一对齐；未映射字段在 `contract_unmapped_fields` 中列出且值为 `null`。
5. `python3 scripts/verify.py --input /input --output /app/output` 显示 `failed=0` 或所有失败已被 `degradations` 说明。
6. 每个 `issue` 都有 `locator`、`quote`、`section`、`severity`、`certainty`、`status`、`claim`、`suggested_fix`；`quote` 为逐字原文。
7. `citation_support_matrix` 中每个 pair 要么有 `verdict`（supported/partial/unsupported/unverifiable），要么进入 `pending_human`。
8. `review_report.md` 与 `result.json` 内容一致；`issues.csv` 条数与 `review_summary.issues_total` 一致。
9. `status` 与 `errors/degradations/pending_human` 一致：`ok` 时无错误；有异常则降级为 `partial` 或 `input_error` 并写明。
10. 空输入/坏 JSON/材料缺失场景下也返回合法 partial 且退出码 0；`errors` 与 `uncertainty` 如实记录，不编造。

## 7. 六类检查与判定规则（摘要）

| 类别 | 关键检查 |
|---|---|
| 引用支持 citation_support | 编号/条目悬空、作者-年份不符、撤稿与预印本状态、综述支撑因果、无来源断言 |
| 事实与数值 fact_check | 百分比与分数不符、摘要与正文 N 不一致、样本量矛盾 |
| 统计报告 stats_report | `p=0.000`、显著无检验量、无效应量/CI、无样本量或功效、±未定义 SD/SEM、趋势性措辞、边界 p |
| 方法设计 method_design | 随机化未描述、比较性结论无对照、体外结论外推临床、缺纳入排除标准 |
| 论证链 argument_chain | 相关性当因果、综述当原始证据、首次性断言、结论绝对化 |
| 学术规范 academic_norm | 缺章节、缺伦理/利益冲突/数据可用性/资助/作者贡献、报告指南、重复 DOI、补充材料缺失 |

判定规则与严重度分级详见 `references/playbook.md`；正则与守卫规则见 `references/checks.json`。**判定必须与引文语义一致**；"引用存在"不等于"引用支持结论"。

## 8. 证据与定位规范

每条 issue 必带三项：

- `locator`：`<文件名>#<页>/para<段号>@char<字符偏移>`，例 `paper.pdf#p3/para2@char10412`（无分页文本省略 `#页`）。
- `quote`：**逐字原文**（脚本按规范化空白/大小写匹配校验；不通过即进 `pending_human`）。
- `section`：`abstract|introduction|methods|results|discussion|conclusion|references|funding|coi|data|ethics|author_contrib` 之一或 `-`。

外部事实（被引文献内容、出版状态、数据库权限）不得写成结论：只能记 `pending_human` 并写明需要什么证据。

## 9. 严重度与状态

- `major`（阻断）：结论不成立、引用不支持结论、数值自相矛盾、方法缺对照、伦理声明缺失。
- `minor`（建议）：报告不完整（无 CI/效应量）、表述过度、条目格式与年份不符。
- `info`：自引比例、参考文献数量等提示。
- `certainty`：`confirmed`（算术/字符串可判定）、`likely`（规则+上下文）、`needs_human`（需外部核验）。
- `status`：`issue` 或 `pending_human`（后者同时进 `pending_human[]`）。

## 10. 冲突与人工确认

- 规则命中但语义可能合理（如"综述"被用于背景陈述）→ 降 `minor`/`info` 或记 `pending_human`，不硬判。
- 同一句命中多条规则 → 保留最具体的一条，其余作为上下文写入 `claim`。
- 原文取不到（扫描件无 OCR）、引文严重歧义、来源撤稿/版本不一致、数据库权限不足 → 一律 `pending_human` + `uncertainty`，写明处置建议。

## 11. 文件清单、依赖与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（含执行流程、预算、鲁棒性、rubric 对照） |
| `scripts/main.py` | 抽取、编排、生成基线报告（入口） |
| `scripts/verify.py` | 规则引擎、引用/数值核验、契约回填、结果自检 |
| `references/checks.json` | 规则文案/严重度、正则规则、章节与契约映射、报告模板 |
| `references/playbook.md` | 判定规则、支持程度定义、证据标准、误报控制 |
| `references/io_contract.md` | 输入/输出 schema、第二遍 findings 格式、排查 |

依赖：Python ≥3.8 标准库。可选（缺失即降级，不报错）：`pdftotext`（PDF 版面文本，强烈建议）、`tesseract`（图片 OCR）。无第三方 Python 包、无网络、无凭证。

维护：新增检查只需在 `cheches.json` 增一条 pattern（regex + `section`/`not_near`/`require_near`/`absent_doc` 守卫 + `catalog` 文案），无需改代码；改动后跑 `verify.py` 与最小示例回归。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
# 输入：/tmp/demo/ 下 case.json + paper.md（1 篇短文）
python3 scripts/main.py --input /tmp/demo --output /tmp/demo_out
```

示意输出（**示例数据，非任何官方案例结果**）：

```json
{"case_id":"demo-001","status":"partial",
 "issues":[{"issue_id":"R-001","kind":"fact_check","severity":"major","certainty":"confirmed",
   "locator":"paper.md#para3@char412","quote":"12% (n=5/60) of samples responded",
   "claim":"百分比与分数不一致：12% 与 5/60（应为 8.3%）","suggested_fix":"按 5/60 重算并同步正文、表与图注"}],
 "review_summary":{"issues_total":1,"by_severity":{"major":1,"minor":0,"info":0}},
 "citation_support_matrix":[{"pair_id":"CP-001","claim_locator":"paper.md#para5@char880","verdict":null}]}
```

**重要**：以上示例仅说明接口与输出结构；正式运行时，必须由 Agent 真实解析材料、亲自核验并生成所有内容，不得将示例或脚本模板直接作为成品。