---
name: science-db-query-analysis
description: >-
  面向科研数据库快照（SQLite，或可物化为 SQLite 的 CSV 材料）的可复核查询与分析技能：
  发现库表与数据字典，生成并执行只读 SQL，把题目中的字面筛选值绑定到真实列值，
  推断并实测跨表连接与一对多膨胀，标注缺失/重复/异常/编码型字段，最后把结果、SQL、
  行数与逐条定位证据写入 result.json，并原样回填全部 output_contract 字段。
  适用于"科研数据库查询与分析"类的字段解释、结果抽取与跨表结论任务；
  不适用于需要联网、写库、或没有可读数据材料的任务。
  本版本强调：脚本只是工具，最终交付物由 Harness Agent 亲自阅读材料、推导、撰写/制作，
  禁止把脚本骨架/模板直接当成品；必须先运行脚本生成基线，再在基线上进行真实性核验与增强。
version: 2.0.0
---

# 科研数据库查询与分析（science-db-query-analysis）

## 0. 最高优先级：完整性优先与真实推导原则

**脚本只是工具，不是成品。** 本 Skill 自带的 `scripts/` 用于快速发现材料、执行只读查询、生成基线交付物和回填契约。但最终 `result.json` 及所有交付文件必须由你（Harness Agent）亲自读材料、亲自核对关键数字与引用、亲自补充结论和不确定性说明。任何直接照搬脚本模板、未经验证的数字、没有来源定位的“结论”都会导致评审判为“不够完整、不像 Agent 真实推导出来的”。

执行原则：

1. **先跑基线，再改进**：进入任务后先运行本 Skill 自带的主脚本，产出全套基线交付物（所有 output_contract 字段、所有题面要求文件、所有 result.json 字段）。
2. **保留全部基线产物**：后续校验与改写只能在此基线上增强；不得删除、清空或遗漏任何基线与契约字段；若不确定，保留原产物并在 result.json 中标注 `reviewed_by_agent`。
3. **完整性自检（提交前必做）**：逐项核对 output_contract 字段列表 × 磁盘文件 × result.json 键三者一一对应；缺任何一项先补齐再收尾；partial 状态必须列出缺失项。
4. **可核验增强**：在基线产物之上，由 Agent 亲自核验关键论断、数字、引用的来源一致性，把核验结果写进 result.json（`verified` / `pending_human` / `conflicts`），这才是“真实推导”的证据。

## 1. 用途与边界

**用途**：给定一个案例目录（`/input/case.json` + 数据快照 + 可能的字段字典），完成一次可复跑的查询分析，产出结构化结果与可核验证据。

**适用**：
- 数据在本地 SQLite 文件（`.db/.sqlite/.sqlite3`）或 CSV/TSV 材料中，可以只读访问；
- 问题涉及计数、分组均值/极值、条件筛选、字段含义解释、跨表关联与行数膨胀判断；
- 需要留下“数字 → SQL → 快照版本 → 行数”的可复核链条。

**不适用**（遇到时如实降级，不要伪造）：
- 需要连接远程数据库、需要账号口令、需要写库或建表授权——本技能只做 `mode=ro` 只读访问；
- 需要联网检索或下载数据；
- 数据以扫描图片/无文本 PDF 形式给出且没有可解析表格（本技能不做 OCR）；
- 题目要求的指标在材料中无对应列，且无数据字典可推断（写入 `pending_human`）。

## 2. 运行契约与目录约定

| 项 | 约定 |
|-|-|
| 入口 | `python3 scripts/main.py`（`--help` 可用，退出码 0） |
| 输入 | `/input/case.json` 与 `/input/task.md`，材料在同目录或子目录 |
| 工作目录 | `/app/work`（CSV 物化快照、临时文件） |
| 产物 | `/app/output/result.json` 及 `queries.sql`、`query_log.json`、`schema_card.json`、聚合 CSV、`chart_*.svg` |
| 路径覆盖 | 依次取 `--input/--output/--work`，再取 `SKILL_INPUT_DIR/SKILL_OUTPUT_DIR/SKILL_WORK_DIR`，最后用默认值；脚本不依赖当前工作目录 |
| 依赖 | 仅 Python 标准库（`sqlite3`、`json`、`csv`、`re`…），不联网，不装包 |
| 退出码 | **恒为 0**（含空输入、坏 JSON、查询报错、超时） |
| 写盘顺序 | 先写 partial `result.json`（契约字段置 null），分析后无条件覆盖 finalize |
| 只读保证 | 输入库以 `file:...?mode=ro` 打开；CSV 物化只写 `/app/work` 下的新文件 |

最终产物必须落在 `/app/output`；必须有 `result.json`，且包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**。

## 3. 输入发现与材料盘点

1. `discover()` 递归扫描 `/input`；`case.json`（或任意 `case*.json`）为主控，缺失时继续运行并在 `errors` 记 `case.json not found`。
2. 数据库识别用**文件头魔数** `SQLite format 3\0`，不靠扩展名或材料标签；CSV/TSV 按扩展名识别；JSON/MD/TXT 作为字典与说明材料。
3. `case_id` 取 `case_id`/`id`，否则取 case 文件名。
4. 指令文本取语义键（`task_instruction`、`instruction`、`question*`、`requirement*`、`goal`、`scope`、`workorder`、`description`），键名不固定；`output_contract` 原样保留。
5. 子问题从 `questions`/`tasks`/`requirement*` 等任意嵌套位置收集（≤6 条）。
6. 材料清单不做内容假设：未在 `/input` 出现的对象在 `pending_human` 中列为缺口，不构造数据。

## 4. 输出契约字段

`result.json` 顶层 = **meta 字段 + `output_contract` 的全部字段（原样键名）**。完整定义见 `references/output-contract.md`。

| 分组 | 字段 |
|-|-|
| 标识 | `case_id`、`skill{name,version}`、`status` |
| 契约 | `output_contract`（原样）、`contract_fill{fields,filled_non_null,null_fields,note}`、以及每个契约字段同名字段 |
| 结果 | `main_result{primary_table,n_rows,aggregates,join_aggregates,filtered,summaries,sample_rows}`、`queries[]`、`schema[]`、`field_explanations[]`、`cross_table[]`、`data_quality{}`、`charts[]` |
| 证据 | `sources[]`（路径/字节/sha1）、`evidence[]`（claim/kind/source_path/locator/sql/quote） |
| 诚实性 | `status`、`assumptions[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime{}`、`question_attempts[]` |

契约回填规则：
- 契约字段**不改名、不删减**；无法生成的值写 `null` 并进入 `pending_human`，同时记入 `contract_fill.null_fields`。
- 字段名与语义表匹配（SQL/表结构/字段/连接/图表/质量/证据/结论/状态/问题…）；名字里含 `unmapped`、`unknown`、`custom`、`other`、`misc`、`extra`、`tbd` 的字段一律不猜，保留 `null`。
- 与 meta 同名的契约字段（`status`、`errors`…）沿用 meta 值，不覆盖结构。

## 5. 本题专属执行流程（编号步骤）

> 每一步都写清输入、动作、输出、失败分支。严禁跳过“真实解析材料”和“Agent 亲自核验”环节。

### 步骤 0：立即落盘 honest partial

**输入**：空输出目录，或仅有脚本默认输出。
**动作**：运行 `python3 scripts/main.py --input /input --output /app/output --work /app/work`。脚本会先写一份 partial `result.json`（契约字段置 `null`，`status="running"`），随后开始后续步骤。
**输出**：`/app/output/result.json`（初始 partial）、`queries.sql`、`query_log.json`、`schema_card.json`（可能尚未生成完整）。
**失败分支**：脚本崩溃或超时 → 手工创建一个最小合法 `result.json`：包含 `case_id`、`output_contract` 原始键（值为 `null`）、`status="error"`、`errors=[...]`、`pending_human=[...]`，退出码 0。**永远不要返回空文件或非 JSON。**

### 步骤 1：盘点输入与读取 case/output_contract

**输入**：`/input/case.json`、`/input/task.md`、材料文件。
**动作**：
- 调用脚本的 `discover` 函数/运行脚本获取扫描结果，或直接读取文件系统列出材料。
- 读取 `case.json` 的完整内容，特别记录 `output_contract` 所有字段键名；读取 `task.md` 中的任务说明、评分维度、Runtime contract。
- 将 `output_contract` 字段列表与 `map_contract_field()` 的结果存于工作记忆。
**输出**：更新 partial `result.json` 的 `case_id`、`output_contract`、`sources[]`；在 `changes[]` 记录“盘点完成”。
**失败分支**：
- 无 `case.json` → 仍继续分析材料，状态 `input_error`，`errors[].stage=discover`。
- `case.json` 非法 JSON → 状态 `input_error`，`errors[].stage=case_json`，但继续分析材料。
- `output_contract` 缺失 → 记入 `contract_fill.null_fields` 和 `pending_human`，仍继续。

### 步骤 2：用工具真实解析材料（不得依据文件名/标签猜测）

**输入**：`/input` 下的数据库、CSV/TSV、字典 JSON/MD/TXT、PDF/DOCX 等。
**动作**：
- 对数据库文件：调用 `scripts/dbcore.py` 或直接使用 `sqlite3` 以 `file:...?mode=ro` 打开；用 `PRAGMA table_info` 建立 schema 卡；执行 `COUNT(*)` 获取行数。
- 对 CSV/TSV：用 `scripts/dbcore.csv_table` 物化到 `/app/work/snapshot.sqlite`，记录字段类型与样例值。
- 对字典/说明书材料（PDF/DOCX/CSV/图片等）：**必须真实解析内容**。若有 PDF，用平台提供的 `pdf-text-tool` 提取文本；DOCX 用相应工具提取；CSV 用 `csv` 读取；图片若有 OCR 工具可用，否则在 `pending_human` 标注无法解析。解析到的文本段落按列名/字段名与真实 schema 对齐，形成`field_explanations.dictionary`。
- **禁止**根据文件名如“wine.docx”或领域标签直接编造字段含义、取值范围或结论。所有断言必须能在 `sources[]` 定位。
**输出**：`schema_card.json`（每库每表、列名、类型、空值数、不同值数、样例值）；`queries.sql`（基础单表查询）；`query_log.json`（查询与行数）。
**失败分支**：
- 库文件损坏/无法打开 → 跳过该库，记录 `errors[].stage=connect`，继续分析其余材料。
- PDF/DOCX 无法解析 → 记录到 `degradations[]`，在 `pending_human` 说明“无法从该材料提取内容，需要人工提供文本”。
- 无任何可分析数据 → 生成 `result.json` 时所有契约字段为 `null`，`status="insufficient_evidence"`，`pending_human` 说明缺失。

### 步骤 3：构建/核对证据（Agent 必须亲自读材料与查询结果）

**输入**：schema 卡、解析出的字典文本、查询日志原始结果。
**动作**：
- 将题目中的字面筛选值（引号串、标识符）与真实列值精确匹配；同一列多值用 `IN`，不拼成互相矛盾的 `=`。
- 对每个关键数字：从 `query_log.json` 中找出对应 SQL 的行数/聚合值；**亲自重新运行该 SQL**（或调用 `scripts/dbcore.run_query`）核对结果；若不一致，记录 `conflicts`。
- 对字段解释：凡引用字典原文，必须提供逐字 `quote` 和 `locator=文件名:line:N`；用 `verify.py` 子串校验，找不到即拒收，绝不改原文凑引用。
- 对跨表连接：检查外键、命名推断，实测父/子行数、可匹配子行数、孤儿行、每键最大子行数，给出膨胀结论和 `join_check`。
- 对数据质量：整行重复、忽略主键后的业务重复、空值率、1.5×IQR 离群、编码型字段（低基数字段不参与求均值）、类型混用。
**输出**：`evidence[]`、`field_explanations[]`、`cross_table[]`、`data_quality{}`，均写入 result.json 草稿。
**失败分支**：
- 不匹配或歧义 → 写入 `uncertainty[]`，若需要确认则 `pending_human[]`。
- SQL 报错 → 使用大小写不敏感匹配重试一次；仍失败则记录 `errors[]`，不静默。

### 步骤 4：Agent 亲自产出完整成品（在基线上增强）

**输入**：前序所有基线产物与证据。
**动作**：
- 检查 `result.json` 每个 output_contract 字段是否已有真实内容；空字段逐个补写或标 `null` + `pending_human`。
- 根据 `references/query-and-quality-rules.md` 和 `references/schema-and-fields.md`，检查查询逻辑、聚合粒度、连接键、编码字段处理是否合理；发现不合理处，亲自修正 SQL 并重跑。
- 补充结论性字段（例如 `main_result.summaries`、`answer` 等）：用自然语言总结“数据表明什么”，并明确指出依据哪条证据（`evidence.id`）。
- 如有图表需求，从聚合结果生成 SVG 柱图；可编辑 Office/幻灯片/图形产物额外渲染为 PDF/PNG 预览。
- 任何超出材料范围或无法由数据支持的结论，一律标注 `insufficient_evidence` 或 `partial`。
**输出**：完整 `result.json` 覆盖写入；所有要求的磁盘文件齐备。
**失败分支**：
- 时间不足 300 秒 → 立即停止新查询，保留已得结论，写入 `degradations[]` 说明“deadline reached during agent review”， `status` 设为 `partial` 并列出 limits。
- 部分字段无法推导 → 设为 `null`，加入 `pending_human`，不要伪造。

### 步骤 5：自检 rubric（提交前逐项检查）

**输入**：`/app/output` 全部产物。
**动作**：
- 运行 `python3 -B scripts/verify.py --result /app/output/result.json`。
- 逐项对照第 8 节“rubric 维度 → 交付要求 → 自证方式”表，检查结果可核验性、完整性、异常说明。
- 检查磁盘文件与 `result.json` 中字段是否一一对应；任何缺失先补齐。
**输出**：`verify.py` 的 `verdict`、修复后的产物。
**失败分支**：
- `verify.py` 任一失败 → 根据错误信息定位：契约字段缺失、引用不一致、SQL 不可复跑、产物缺失等，修复后重跑。若时间不够，保持 partial 并记录 `pending_human`。

### 步骤 6：回填 result.json 并正常退出

**输入**：步骤 5 确认的完整结果。
**动作**：
- 检查 `case_id`、`output_contract` 全部字段、`status`、`sources`、`evidence` 均已写入。
- 将 `runtime.end_time`、`runtime.deadline_reached` 等写入。
- 确保退出码为 0。
**输出**：最终合法 `result.json`，退出码 0。
**失败分支**：无；任何异常均在内部捕获，不输出 traceback 到 stdout。

## 6. 预算策略：64 次模型请求 / 900 秒内如何分配

**重要**：运行脚本、读文件、执行 SQL 不消耗模型请求，但需要 Agent 决策并调用。每次 Agent 生成动作（包括调用工具并等待结果）可能占用模型请求。建议按以下策略分配，总消耗控制在 50 次以内，留余量给修复与重试。

| 阶段 | 建议模型请求 | 动作 | 可跳过条件 |
|-|-|-|-|
| 步骤 0-1：跑脚本、读 case | 5-8 次 | 调用 main.py、读取 case.json、task.md、扫描文件 | 如已由脚本完成盘点，可减少到 3 次 |
| 步骤 2：真实解析材料 | 6-10 次 | 解析 PDF/DOCX/CSV、打开数据库、获取 schema 卡 | 若材料单一（仅 SQLite），可减到 4 次 |
| 步骤 3：构建证据与核验 | 12-18 次 | 运行关键 SQL、读查询日志、核对字典引用、跨表检查 | 不可跳过；重点放在高权重结果字段 |
| 步骤 4：Agent 增强与补齐 | 10-15 次 | 检查契约字段、修正逻辑、补充结论、生成图表 | 若时间紧张，优先完成高权重字段，低优先级图表可省略 |
| 步骤 5：自检与修复 | 5-8 次 | 运行 verify.py，修正不一致 | 不可完全跳过；至少运行一次 |
| 总计 | 38-59 次 | | 保留 5+ 次余量 |

**必须做的**：读取 `output_contract`、真实解析数据库/CSV、运行基线脚本、核对至少每个数值型结论的来源 SQL、运行 `verify.py`。
**可跳过**：无谓的重复查询、低权重可视化美化、非必要材料全文转储等。
**何时落盘 partial**：步骤 0 立即写 partial；步骤 3 开始前再覆盖一次部分证据；步骤 4 完成后覆盖完整；超时前 60 秒强制 finalize。

**单次响应 token 限制 16384（含推理）**：凡读取大量文本（如 DataFrame 转储）时，必须先截断或只取必要片段；不要一次性 dump 整个数据库内容到上下文。优先读 schema 和样例值，而非全量数据。

## 7. 隐藏案例鲁棒性与降级策略

任何情况下都必须产出合法 `result.json`（退出码 0）。平台可能提供未知案例，材料可能缺失、损坏、格式不支持、空输入或契约缺失。

| 情况 | 降级动作 | 记录位置 |
|-|-|-|
| `/input` 为空或无 case.json | 创建最小 result.json，status=`input_error`，所有契约字段 `null` | `errors[]`、`pending_human[]` |
| 数据库损坏/无法只读打开 | 跳过该库，继续分析其余文件；若无可分析数据，status=`insufficient_evidence` | `errors[].stage=connect`、`degradations[]` |
| 只有 CSV，无 SQLite | 物化到 `/app/work/snapshot.sqlite` 再分析 | `degradations[]`、`sources[]` |
| PDF/DOCX 无法解析或扫描图片无 OCR | 不猜测内容；将解析失败写入 pending_human；如有其他可分析数据继续 | `degradations[]`、`pending_human[]` |
| SQL 报错 no such column/table | 大小写不敏感匹配后重试一次；仍失败记录错误，不静默 | `queries[].sql` 替换 + `errors[]` |
| 查询返回 0 行 | 保留空结果并说明筛选条件 | `main_result.filtered[].n_rows=0` |
| 表为空（0 行） | 不做统计，status=`insufficient_evidence` | `schema[].rows=0` |
| 契约字段无生成器 | 置 `null` + 待确认 | `contract_fill.null_fields`、`pending_human` |
| 超时（900 秒） | 停止新查询，保留已得结果，写 `degradations[]` | `runtime.deadline_reached=true` |
| 空输入导致无 case_id | 使用 `"unknown_case"` 作为 case_id | `case_id` |
| 材料包含中文列名或非英文 schema | 直接使用原始列名，不要翻译；若无法推断角色，按基数与大类试探并标注 caveat | `uncertainty[]` |

## 8. Rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式（在 result.json / 磁盘文件中的落点） |
|-|-|-|-|
| **实际效果** | 40 | 真实连上授权数据源、写可执行查询、取回结果集、解释关键字段、给出跨表分析结论 | `queries[]` 中 SQL 实际执行且记录行数；`sources[]` 给出文件 sha1；`evidence[]` 的 `kind=sql_aggregation` 由 `verify.py` 重跑复现；`field_explanations[]` 有字典原文定位；`cross_table[]` 有实测膨胀 |
| └ 任务完成度 | 15 | 覆盖题面要求的表、字段、时间区间、筛选条件、跨表维度；不遗漏不偏题 | `question_attempts[]` 逐项状态；`contract_fill.filled_non_null` 数量；`pending_human[]` 列出未覆盖项 |
| └ 结果正确性 | 15 | 连接键用对、聚合粒度匹配、无因漏连接造成行数膨胀、编码字段与单位按字典解释、数值可独立复算 | `cross_table[].fanout_note` 说明膨胀；`data_quality.coded_fields` 标记不求均值；`queries[]` SQL 与行数；`verify.py` 重跑一致性 |
| └ 结果完整性 | 5 | 覆盖题面要求全部指标，未覆盖部分明确交代 | `contract_fill.null_fields` 列表；`pending_human[]`；`status` 为 `ok` 或 `partial` 并列出 limits |
| └ 结果可核验性 | 5 | 查询语句、连接对象、数据快照版本、执行日志和结果行数能独立复跑 | `sources[]` 含 sha1；`queries.sql` 文件；`query_log.json`；`evidence[].locator` 与 `sql` |
| **使用增益** | 25 | 相比基础 Agent，加载后查询正确率与结论质量提升，减少改写轮次与人工核对量 | 本 Skill 通过模式化 schema 发现、接地、SQL 生成、跨表膨胀实测、verify 复核实现。自证：`runtime.model_requests`、`queries[]` 数量与成功率、`errors[]` 长度、`changes[]` 记录改进步骤 |
| └ 质量增益 | 15 | 查询正确率、字段解释、连接路径、脏数据处理规则化 | `query-and-quality-rules.md` 的规则在 `queries[]`、`data_quality{}`、`cross_table[]` 中体现；`assumptions[]` 说明口径 |
| └ 效率增益 | 5 | 减少查询改写轮次与人工核对量 | `runtime.queries_executed` 与 `errors[]` 少；`changes[]` 显示自动修复一次成功；脚本现成 |
| └ 增益可验证性 | 5 | 公平对照证明改善（同一快照、权限、预算） | 本 Skill 不捏造对照数据；`runtime` 记录实际执行；`verify.py` 确定性复核通过 |
| **创新增益** | 15 | 新增能力：按数据字典做字段语义映射、自动规划跨表连接路径、SQL 报错自修复、脏数据处理规则化 | `field_explanations[]` 的 dictionary 映射；`cross_table[]` 的路径推断与实测；`errors[]` 记录自动修复；`data_quality{}` 离群/重复/编码字段；`references/schema-and-fields.md` |
| └ 新增能力 | 5 | 基础 Agent 不具备的 schema 检索、字段字典接地、连接计划、报错定位 | 代码与规则文件展示能力；`result.json` 的方法字段 `skill.name/version` |
| └ 方法改进 | 5 | 相比现有方案有实质改进，如膨胀检测、字典接地 | `cross_table[].fanout_note` 与 `field_explanations[].dictionary` 是新增证据 |
| └ 创新证据 | 5 | 证明创新点边界与价值 | `assumptions[]`、`uncertainty[]`、`pending_human[]` 说明限制；`verified` 核验记录 |
| **可靠体验** | 10 | 调用易用、运行稳定、异常处理 | 脚本退出码恒 0；契约清晰；`verify.py` 通过；`degradations[]` 完整 |
| └ 调用与易用性 | 3 | Agent 能正确触发，用户能按说明配好连接并跑完一次 | `SKILL.md` 提供最小调用示例；`main.py --help` 退出码 0 |
| └ 运行稳定性 | 4 | 不同库表规模、不同快照、重复运行下持续产出 | 脚本路径覆盖、只读保证、无外部依赖；`runtime` 记录稳定执行 |
| └ 异常处理 | 3 | 空结果、连接失败、权限不足、字段歧义、重复记录、类型不一致识别与处置 | `data_quality{}`、`errors[]`、`pending_human[]`、`degradations[]` 完整；降级表执行 |
| **生态贡献** | 10 | 文档完整、资源可复用、分享推广价值 | SKILL.md、references、scripts 全部齐备；SQL 模板、schema 卡片可复用 |
| └ 文档完整性 | 3 | 数据字典、连接说明、字段解释、示例、依赖、限制和维护信息齐全 | `references/output-contract.md`、`query-and-quality-rules.md`、`schema-and-fields.md`；本文件维护说明 |
| └ 资源可复用性 | 4 | SQL