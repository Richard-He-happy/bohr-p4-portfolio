---
name: reading-08-formula-structure
description: 用于公式解析与数学推理科研阅读任务：确定性还原 MathML/TeX/XML 公式为可校验 LaTeX 与结构统计，产出符号变量表、带假设与边界条件的推导步骤、数值与量纲核验，并生成 result.json、formulas.tex、symbol_table.csv、verification.md；脚本只是解析与兜底工具，最终交付物由 Harness Agent 亲自读材料、核验、补全并撰写。材料无公式表示时如实报 insufficient_evidence，不反推、不填 0。
version: 4.0.0
license: MIT
---

# ★ Agent 修改边界（最高优先级，先读）

本 Skill 的结构化基线由 `scripts/main.py` 生成；你（Harness Agent）的职责是真实阅读材料、核验、补全文本型交付物，不是手工重写结构化 JSON 的结构。必须遵守：

1. 禁止手改脚本生成的结构化字段：`claims.json`、`evidence_table.json`、`result.json` 的键名、`claim_id`、`source_id`、`locator`、`quote`、`strength`、`support_scope`、`counts` 必须保持脚本输出。不得用文本编辑覆盖这些文件。
2. 允许 Agent 做的事：
   - 真实阅读 `/input` 材料，核验脚本抽取的 quote、locator、数字、公式是否符合原文；
   - 把核验结论写入 `/app/work/agent_review.json`，逐条列出 claim_id、核验结果 verified/rejected/reason；
   - 把需要人工判断的项写入 `/app/work/pending_human.json` 或 `result.json` 的 `pending_human`；
   - 亲自撰写或改写正文型交付物，如 `verification.md`、`deliverable.md`，但每个数字、引用、论断必须能在证据表或原文中找到依据；
   - 若发现脚本缺陷，可写临时 Python 调用 `scripts/formula_core.py`、`scripts/audit.py` 中已有函数重算并覆盖，完成后在 `agent_review.json` 的 `script_fixes` 记录，不得手工篡改 JSON。
3. 禁止生成无依据的评分、金标准、基准分数或与官方白板的虚假比较。不创建 `golden_standard`、`diff_report`、加权自评分；核验只引用脚本真实输出 `verification.json` 或 `self_check.json`。若脚本已生成这类自设资产，不要引用、不要美化，在 `agent_review.json` 说明其局限。
4. 完整性自检：结束前核对 `output_contract 字段 × 磁盘文件 × result.json 键` 三者一一对应；只要存在 `deliverable.md` 与 `evidence_driven_draft.md`，两者必须内容不同，前者是干净成稿，后者是带证据标记草稿，不得复制同一文本。
5. 预算：先让脚本产出全套基线，通常 1–2 次调用即可；再把剩余模型请求用于逐条核验与成稿改进。接近 64 次请求或 900 秒时立即收尾，保证 `result.json` 合法、status 诚实。

# 0. 角色与铁律（最高优先级）

本 Skill 用于科研阅读中的公式解析与数学推理：认得准、讲得清、推得顺、算得回。

脚本只是解析、兜底和产物生成工具，最终交付物由你亲自读材料、推导、撰写或确认。禁止把脚本模板、空骨架或未经验证的输出直接当成品。你必须：

1. 真实解析 `/input` 下材料内容，不得依据文件名、领域标签或案例号猜测或补造。
2. 先运行入口脚本产出基线交付物；后续所有校验与改写只能叠加增强，不得删除、清空或遗漏契约字段。
3. 对每个关键结论——公式、变量定义、推导步骤、数值代入——亲自回看材料，确认 `quote` 与 `locator` 可追溯。
4. 不确定、缺失、冲突必须显式标注 `pending_human` / `limitations` / `uncertainties`，不得编造数据、引用、分数或科学事实。
5. 任何情况下都必须写出合法 `result.json`，退出码为 0，即使 status 为 `partial` 或 `insufficient_evidence`。

# 1. 用途与边界

做：

- 解析 `artifacts/*.xml`、MathML、TeX、文本中的公式，确定性映射为可校验 LaTeX 与结构统计，包括 `fracs`、`subsups`、`radicals`、`matrices`、`cases`。
- 建立符号变量表，每个符号区分来源：`paper_defined`（原文定义）、`context_inferred`（上下文推断）、`common_knowledge`（常识补充）。
- 抽取带 `rule`、`assumptions`、`approximations`、`boundary_conditions` 的分步推导线索。
- 只使用材料中字面给出的数值做代入核验；缺值标注 `not_computable`，全无赋值时给出明确标注的 `example_only` 探针。
- 对无公式表示但有材料的快照型案例，如实报 `partial` 或 `insufficient_evidence`，并尽可能完成明确指标、条件或文字的核验。

不做：

- 不把公式目录 XML 当答案输出；formula catalog 不是 linearized answer。
- 不反推缺失公式、不把未知填 0、不臆造符号定义、单位、取值范围或数值。
- 不做超出材料证据的符号代数证明；推导只到“原文这么说”，并附依据。
- 不对位图做 OCR 猜测，除非环境提供 OCR 工具且已将结果回原文核验。

# 2. 运行契约

| 项 | 约定 |
|---|---|
| 单命令全流程入口 | `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work` |
| 分阶段入口 | 若 `main.py` 支持子命令，可用 `init`、`build`、`selfcheck` 三个阶段；不支持时直接使用上述 `run` |
| 内部阶段 | `init`：盘点材料、来源编号、候选公式、冲突分组；`build`：校验、兜底抽取、渲染全部产物并 finalize `result.json`；`selfcheck`：产物与契约自检 |
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 实际材料；`--input` 可覆盖 |
| 工作目录 | `/app/work`，存台账、中间提取、草稿、核验记录、备份 |
| 输出 | `/app/output/`，`--output` 可覆盖；不可写时退到 `./output` 并在 `errors` 记录 |
| 主产物 | `result.json`、`formulas.tex`、`symbol_table.csv`、`verification.md` |
| 审计产物 | `self_check.json`、`version_history.md`、`run.log`；若脚本生成则保留，不伪造 |
| 退出码 | 恒 0；先写 partial `result.json`，`finally` 无条件 finalize |
| 依赖 | 仅 Python 标准库，无网络，不依赖 CWD；Python >= 3.8 |
| 资源限制 | Skill 最多 50 个 UTF-8 文本文件、单文件 ≤ 500KB、总 ≤ 2MB、无 symlink |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens 含推理 |

若 `run` 子命令不可用，回退命令为：`python3 -B scripts/main.py --input /input --output /app/output`，并在 `degradations` 记录 `main_run_subcommand_unavailable`。无论哪种入口，都不得因脚本异常导致非零退出。

# 3. 输入发现与材料解析规则

1. 优先读 `/input/case.json`；若不存在，依次尝试 `case_input.json`、`input.json`，再递归查找 `case*.json`。
2. 读 `case_id`，常见别名 `id`；读取 `output_contract`、`output_spec`、`contract` 任一存在即原样保留，用于回填 `result.json`。
3. 递归扫描 `/input/**`，按扩展名与魔数分类：`.xml/.mathml/.nxml` 或 `<?xml` 头、`.tex`、`.txt/.md/.rst`、`.json`、`.pdf` 的 `%PDF-`、图片、docx/xlsx/pptx。
4. 脚本可直接解析 XML/MathML、TeX、文本、JSON 内嵌 `<math>`。
5. 若材料含 PDF、图片、Office 文档，必须调用环境提供的解析或提取工具，按 `environment/resources.yaml` 提供的命令进行。提取后的中间文件放入 `/app/work/`，不污染 `/input`。
6. 材料没给的对象写进 `result.missing_objects`，不构造内容。

支持的公式来源优先级：

- `<annotation encoding="application/x-tex">`：原文 TeX，来源于 MathML annotation，记为 `latex_source=mml_annotation`；
- MathML 结构映射：记为 `structural_mapping`；
- `.tex` 的 equation 环境：记为 `source_tex`；
- JSON 内嵌 `<math>`：记为 `structural_mapping`。

XML 解析失败时退化到正则抽 TeX annotation，记为 `regex_annotation`，`parse_confidence=low`。所有退化必须写入 `degradations`。

# 4. 本题专属执行流程

每步标注输入 → 动作 → 输出 → 失败分支。按顺序执行，尽早落盘 partial。

## 步骤 1：init 盘点与契约

输入：`/input/case.json`、`/input/task.md`、递归列出 `/input`。

动作：

- 读取 `case_id`、`output_contract` 或等价契约；
- 记录所有输入文件路径、扩展名、魔数、大小；
- 运行 `init` 阶段，或直接运行入口 `run` 让脚本先建台账。

输出：`/app/work/input_inventory.json` 与脚本 ledger，至少包含 `case_id`、`contract_raw`、`files[]`（路径、类型、大小）、`sources[]`。

失败分支：

- 无 `case.json` 或无 `output_contract`：记录 `contract_missing`，从 `task.md` 推断最小交付物集合，继续执行；
- 无法读取输入：仍写出合法 `result.json`，`status=input_error`，退出码 0。

## 步骤 2：Agent 路径写入 draft.json

输入：台账、全部材料、脚本初步候选。

动作：

- 真实阅读原文，针对公式、符号定义、推导前提、数值赋值四类对象形成判断；
- 写入 `/app/work/draft.json`，建议字段包含 `case_id`、`formulas`、`symbol_table`、`derivation_steps`、`verification`、`missing_objects`、`pending_human`、`changes`；
- 每个判断必须带 `source_id`、`locator`、`quote`；
- 对未报告、无法判断、材料冲突分别写清；
- 若预算不足，跳过本步，记 `draft_status=omitted_budget`，进入确定性兜底。

输出：`/app/work/draft.json`。

失败分支：

- 材料缺失、损坏或格式不支持：在 `missing_objects` 与 `pending_human` 写明原因，不猜内容；
- 时间不足：不阻塞，直接进入步骤 3。

## 步骤 3：build 构建或兜底

输入：台账、可选 `draft.json`、材料。

动作：

- 运行 `build` 阶段，或运行入口 `run` 完成构建；
- 脚本有 `draft.json` 时使用 Agent 判断；无 draft 时使用 init 台账确定性抽取生成实质工作稿，逐字 quote 与 locator；
- 若确定走无 draft 的确定性兜底，在 `gaps` 或 `degradations` 中诚实写入 `AUTO_EXTRACT`，说明哪些结论由脚本抽取、哪些待人工复核；
- 渲染全部契约产物：`formulas.tex`、`symbol_table.csv`、`verification.md`，并 finalize `result.json`。

输出：完整基线产物与合法 `result.json`。

失败分支：

- 脚本异常：记录 `errors.fatal`，尝试调用 `scripts/formula_core.py` 可用函数或手工构造最小合法 `result.json`；
- 脚本无法解析部分材料：记录 `degradations`，不影响其他部分；
- 任意失败都必须 exit 0。

## 步骤 4：selfcheck 与契约自检

输入：当前 `/app/output`。

动作：

- 运行 `selfcheck` 阶段，或手动逐项检查；
- 核对 `result.json` 是否包含 `case_id` 与 `output_contract` 全部键；
- 核对契约字段是否在 `result.json` 顶层与 `output_contract` 嵌套对象中各出现一次；
- 检查每条 claim 的 `quote` 是否能回原文；未逐字找到的降级为 `quote_verified=false` 并标 `undetermined`；
- 检查 `status` 诚实：有缺失写 `partial`；无公式表示写 `insufficient_evidence`；全部满足才写 `success`；
- 检查 `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 是否都存在。

输出：`self_check.json`、`result.json` 更新。

失败分支：

- 契约字段难以满足：设置空列表或空对象，并在 `contract_fields_missing` 记录原因；
- 自检发现错误：在 `changes` 记录修正，不删除既有内容。

## 步骤 5：成稿与增强

输入：基线产物、核验笔记、草稿。

动作：

- 亲自撰写或改写 `verification.md`，包含“Agent 核验结论”：哪些可读、哪些是推断、哪些缺失；
- 对关键公式、变量、推导、数值给出 `quote + locator`；
- 如题面要求正文交付物，将干净成稿写入 `deliverable.md`，不允许与证据草稿相同；
- 将核验结果回写 `result.json`：新增或更新 `claims`、`uncertainties`、`pending_human`，并在 `changes` 记录原因。

输出：最终 `verification.md`、`deliverable.md`、`result.json`。

失败分支：

- 时间不足：立即执行步骤 6，保证 `result.json` 合法；
- 缺乏证据：不得补写；把缺失写入 `missing_objects` 或 `pending_human`。

## 步骤 6：最终落盘

动作：

- 确保 `/app/output/result.json` 为合法 JSON，顶层含 `case_id` 与全部 `output_contract` 字段；
- 确保 `result.json` 含 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`；
- 确保所有关键结论可追溯，无法追溯的不写成事实；
- 确保脚本审计产物不被误删；
- 最终退出 0。

# 5. result.json 双回显与证据规范

`result.json` 必须同时满足：

1. 顶层包含 `case_id` 与 `output_contract` 中每个字段；
2. 顶层包含 `output_contract` 嵌套对象，其中再次包含同样的字段；
3. 顶层包含运行状态类字段：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`；
4. 每个关键结论尽量使用证据对象：`source_id`、`locator`、`quote`、`strength`、`support_scope`；
5. `case_id` 从输入读取，不自行编号。

`status` 取值至少覆盖：

- `success`：覆盖任务要求且关键结论可回原文；
- `partial`：部分完成、材料缺失、数值不可计算或推导不可核验；
- `insufficient_evidence`：材料无公式表示、缺少可复算原始数据、推导对象缺失；
- `input_error`：输入不可读但已尽力产出合法结果；
- `incomplete` 或 `undetermined`：按规定如实使用。

`missing_objects` 至少包含对象名、缺失原因、人工接管位置。不得把未知填 0，不得将 `not_computable` 写成 `0`。

# 6. Rubric 对齐自检清单

## 实际效果 40 分

- `formulas.tex` 是否包含可校验 LaTeX，不只是贴一段公式文本；
- LaTeX 上下标、括号层级、希腊字母、单位、公式编号是否与原文一致；
- `symbol_table.csv` 是否覆盖声明公式的变量，并区分 `paper_defined`、`context_inferred`、`common_knowledge`；
- `verification.md` 是否包含推导步骤、假设、近似、边界条件、数值代入复算；
- 每个符号定义、推导步骤、数值结论是否具备 `source_id + locator + quote`。

## 使用增益 25 分

- 是否用同一条命令生成全套产物，降低 Agent 重复回原文定义和手工整理成本；
- 是否保留确定性脚本兜底，材料明确时无需大量模型请求；
- 是否在 `verification.md` 或 `changes` 中记录加载 Skill 后的可核验增量：由脚本稳定完成 structural mapping、由 Agent 完成证据核验，不声称未测量的基准分数。

## 创新增益 15 分

- 是否体现基础 Agent 不易稳定完成的 MathML → LaTeX 结构映射与来源标注；
- `references/mathml-latex-mapping.md` 与 `scripts/formula_core.py` 是否描述映射规则、退化路线；
- `references/result-schema.md` 是否给出变量表、推导步骤、证据对象的结构约束；
- 是否证明边界：仅处理结构可识别公式；缺失时报告 partial/insufficient_evidence，不越界。

## 可靠体验 10 分

- 单命令入口、秒级基线、无网络、纯标准库；
- 任意异常退出码 0；
- 对 PDF/Office/图片、材料缺失、公式截断、符号歧义、单位缺失、代入无解等有显式降级路径；
- 重复运行产物可复现，`version_history.md` 与 `changes` 记录变更。

## 生态贡献 10 分

- 说明文件齐全：本 SKILL.md、`references/examples.md`、`references/mathml-latex-mapping.md`、`references/result-schema.md`；
- 脚本可复用：`scripts/main.py`、`scripts/formula_core.py`、`scripts/audit.py`；
- 提供最小调用示例，示意输出标为示例；
- 提交根目录放入 `GITHUB_URL.txt`，第一行写公开链接，第二行可写本次提交相对路径。

# 7. 异常处理与降级路线

| 情况 | 处置 |
|---|---|
| 缺少 `case.json` | 从其它 json 推断 `case_id`；记 `input_error`；继续产出 result.json |
| 缺少 `output_contract` | 从 `task.md` 推断最小字段；记 `contract_missing` |
| PDF 无文本层 | 提取文本到 `/app/work`；若只有公式图像，标记 `missing_objects`，不 OCR 猜测 |
| 公式截断或符号歧义 | 保留原始片段，记 `undetermined`，写入 `pending_human` |
| 单位缺失或数值不足 | 单位记 `unknown`；数值记 `not_computable`；不填入假值 |
| 材料冲突 | 双方证据都保留，`status=partial`，写入 `conflicts` 或 `pending_human` |
| C02 类真实缺失分支 | 只核验明确指标与条件；缺失推导/复算报 `partial` 或 `insufficient_evidence`，不反推公式，不填 0 |
| 脚本异常 | 错误写入 `errors`，尝试最小构造 result.json，最终 exit 0 |
| 时间预算不足 | 先写 partial result.json，再增量改进；不得因超时无输出 |

# 8. 最小调用示例

示例输入目录 `/input` 含 `case.json`、`task.md`、`artifacts/publisher-source.xml` 或 `source-formulas.xml`。

调用：

`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

示意输出：

`/app/output/result.json` 包含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`，顶层与 `output_contract` 双回显契约字段；`/app/output/formulas.tex` 给出可校验 LaTeX；`/app/output/symbol_table.csv` 给出变量表；`/app/output/verification.md` 给出推导假设、边界条件与数值核验说明。此示意输出仅供接口说明，不冒充正式案例结果。

# 9. 必须避免的扣分项

1. 只输出一段 LaTeX 或只给首行公式，没有变量表、推导步骤、核验结论。
2. 变量定义用常识猜写而不指回原文，或把推断写成原文定义。
3. 对缺失公式、数值、原始数据反推或填 0。
4. 手工篡改脚本结构化 JSON，导致 evidence、claims、result 结构损坏。
5. 把公式目录 XML 线性化后当最终答案。
6. 虚构基准分数、白板对比、金标准或评分结论。
7. 出现非零退出、空 result.json、缺 `case_id`、缺 `output_contract` 字段。
8. 关键结论无 `locator + quote`，把无法判断写成事实。

# 10. 最终检查

提交前确认：

- `result.json` 合法，顶层与 `output_contract` 双回显；
- `case_id` 正确；
- `status` 诚实；
- `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 齐备；
- `formulas.tex`、`symbol_table.csv`、`verification.md` 存在且非空；
- `agent_review.json`、`pending_human.json` 若有则与 result 一致；
- 所有结论可回材料，不造假；
- 包内文件不超过 50 个，单文件 ≤ 500KB，总 ≤ 2MB，无 symlink；
- 根目录已放 `GITHUB_URL.txt`。