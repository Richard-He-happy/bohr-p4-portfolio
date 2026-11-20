---
name: statistical-analysis-interpretation
description: 科研数据统计分析 Skill：解析 CSV/TSV/TXT/SQLite/PDF/DOCX 等原始材料，完成清洗、描述统计、推断统计、效应量、置信区间、图表与可核验报告；支持 Agent 先核验写 draft.json，或脚本确定性兜底生成同一套 result.json 契约。适用于统计分析与结果解读 Benchmark。
version: 3.0.0
---

# 统计分析与结果解读 Skill

## 0. P0 修改边界与铁律

本 Skill 最终结构化产物由 `scripts/main.py` 与 `scripts/statsx.py` 生成；Agent 的职责是真实读取原始材料、核验证据、补强判断与撰写成稿，不是手工重写最终 JSON。

必须遵守：

1. Agent 不得手工编辑 `result.json`、`evidence_table.json`、`cleaning_rules.json`、`sources.json` 等脚本产出的结构化文件。
2. Agent 可以：
   - 真实读取 `/input` 原始文件与数据字典；
   - 写 `${WORK}/draft.json`，把判断、清洗规则、检验选择、效应量口径和 claims 写入该工作稿；
   - 写 `${WORK}/agent_review.json`，记录逐条核验结论；
   - 改写 `analysis.md` / `interpretation.md` 等正文型成稿，但关键数字与论断必须可在 `evidence_table.json` 中找到出处；
   - 调用脚本命令修复或重算，不得用文本编辑覆盖脚本输出。
3. 禁止编造科学数据、缺失软件状态、golden_standard、平台评分或 benchmark 分数。平台会记录真实运行。官方基线未提供时，不得自造对照评分。
4. 任何情况下脚本必须 exit 0；分析失败、材料缺失、解析失败都要写入 `errors` / `degradations` / `pending_human` 后返回 0。
5. 所有分析开始前先写 partial `result.json`；分析结束后必须 finalize 覆盖。

## 1. 单命令全流程入口

首选命令：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部顺序执行：

1. `init`：盘点输入、生成来源台账、抽取候选数据集、识别冲突分组。
2. `check`：若存在 `${WORK}/draft.json`，校验其 claims、locator、quote、契约覆盖；若不存在，进入确定性兜底。
3. `build`：使用 Agent draft 或脚本自动抽取的工作稿，执行清洗、统计、检验、效应量、置信区间、图表、报告，生成全部 `/app/output` 交付物，并 finalize `result.json`。
4. `selfcheck`：核对产物、契约、证据、来源和磁盘文件，写 `selfcheck_report.json`。

也可以分步执行：

`python3 scripts/main.py init --input /input --output /app/output --work /app/work`

`python3 scripts/main.py check --input /input --output /app/output --work /app/work`

`python3 scripts/main.py build --input /input --output /app/output --work /app/work`

`python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work`

所有命令均不依赖当前工作目录；`--help` 可查看参数。优先用标准库，离线运行，Python >= 3.8。

## 2. 目录与运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md` 以及题面提供的原始材料。必须真实解析内容，不得依据文件名、领域标签或已知数据集名称补造数据 |
| 工作目录 | `/app/work`：存放 `ledger.json`、`draft.json`、`draft.auto.json`、`check_report.json`、`parsed/`、`raw_snapshot/`、`agent_review.json` 等 |
| 输出目录 | `/app/output`：所有最终交付物与 `result.json` |
| 退出码 | 恒为 0；错误不得让进程崩溃 |
| 写入限制 | 不写 `/input`；不依赖网络；不依赖未在 `environment/resources.yaml` 声明的工具 |
| 确定性 | 分组排序固定；bootstrap/permutation 种子由 `zlib.crc32(case_id + source_id + method + salt)` 派生；浮点按可复现精度序列化 |

## 3. 阶段 1：init 盘点与台账

`init` 必须真实完成以下工作：

1. 读取 `/input/case.json` 与 `/input/task.md`，提取 `case_id` 与 `output_contract`。若 `case.json` 缺失或损坏，使用标准契约字段并标记 `contract_missing=true`。
2. 递归列出 `/input` 文件；记录路径、扩展名、大小、SHA-256、可读状态、文本编码探测结果。
3. 识别材料类型：CSV、TSV、TXT、SQLite、PDF、DOCX、图片、数据字典、JSON、Markdown。
4. 生成来源台账 `sources`，每条来源分配 `source_id`：`S1`、`S2`、`S3`……
5. 真实解析候选数据：
   - CSV/TSV/TXT：按内容检测分隔符；首行纯数值时命名 `col1..colN`；保留原值。
   - SQLite：读取所有业务表，记录 schema、行数、字段类型；按数据字典或主表选择实际分析表。
   - PDF：使用 `environment/resources.yaml` 中列出的解析工具提取文本/表格到 `/app/work/parsed/`。
   - DOCX：使用可用工具提取段落与表格；无法解析则记 `pending_human`。
   - 图片：需要 OCR；不可用则记 `unsupported_material`。
6. 读取数据字典：字段名、单位、类型、取值约束、说明。字典单位优先于列名推断；单位不明不得静默换算。
7. 候选抽取与冲突分组：
   - 识别主分析表；
   - 比较数据字典与数据表字段；
   - 将单位不一致、重复记录冲突、数据库与平面文件冲突、同一字段不同来源冲突分组记录。

产物：`${WORK}/ledger.json`、`${WORK}/parsed/`、`${WORK}/raw_snapshot/` 或材料哈希清单，以及 `/app/output/result.json` 首个 partial 版本。

`result.json` 首写内容至少包含：

`case_id`、`status="partial"`、`sources`、`output_contract`、空 array 的 `errors`、`degradations`、`pending_human`、`uncertainty`。

## 4. 阶段 2：Agent-first 路径与 draft.json

若预算允许，Agent 应采用 Agent-first 路径：

1. 先执行 `init`，阅读 `${WORK}/ledger.json`。
2. 真实打开原始数据、数据字典与 `task.md`。
3. 判断：
   - 主分析表是哪一个；
   - 字段单位与类型；
   - 清洗规则：缺失、异常、重复如何认定；
   - 研究设计：两独立组、配对、多组、分类关联、相关等；
   - 检验方法选择；
   - 效应量与置信区间口径；
   - 哪些结论可写，哪些只能标 pending_human。
4. 将判断写入 `${WORK}/draft.json`。

`draft.json` 建议形状：

`case_id`、`primary_data`、`cleaning_decisions`、`analysis_decisions`、`claims`、`conflicts`。

每个 claim 至少含：

`claim_id`、`kind`、`statement`、`source_id`、`locator`、`quote`、`confidence`、`support_scope`。

其中 `kind` 取值可为 `cleaning`、`descriptive`、`test`、`effect_size`、`confidence_interval`、`interpretation`。`confidence` 取值 `high`、`medium`、`low`、`unverifiable`。

若 Agent 预算不足，可跳过写 draft.json，直接使用 `run` 的确定性兜底。

## 5. 阶段 3：check 校验

`check` 对 `${WORK}/draft.json` 进行机器校验：

1. `source_id` 必须存在于 ledger。
2. `locator` 必须能定位到实际文件、行号或段落号。
3. `quote` 必须能在来源中找到，或标记 `quote_normalized=true`。
4. 关键数字、检验方法、效应量必须与输出契约对应。
5. 不得出现无来源数字、与原文冲突的数值、空 claim。
6. 未覆盖契约字段时报告 warning，不阻断后续。

产物：`${WORK}/check_report.json`。

若 `check` 失败或 draft 缺失，`build` 不得空输出，必须走确定性兜底。

## 6. 阶段 4：build 与确定性兜底

`build` 必须确保两条路径产出同一套产物与同一份 `result.json` 契约。

### 6.1 无 draft 时的确定性兜底

若 `${WORK}/draft.json` 不存在、非法或 `check` 未通过：

1. `build` 使用 ledger 中的主表与数据字典，确定性生成实质性工作稿。
2. 工作稿写入 `${WORK}/draft.auto.json`。
3. 每个关键数字和规则必须带 `verbatim quote` 与 `locator`。
4. 在 `result.json.degradations` 中记录 `AUTO_EXTRACT`，说明“无 Agent draft，使用脚本确定性抽取”。在 `gaps` 中也保留同样信息。
5. 该兜底不得生产无来源数字；拿不到依据时写入 `pending_human`。

### 6.2 数据清洗

必须覆盖七类关键情形：缺失值、异常值、重复记录、统计假设、图表选择、代码运行、数据库字段。

清洗规则：

- 缺失值：识别空白、`NA`、`N/A`、`null`、`.`、`NaN`、`?` 等；不得把缺失当 0；不得无说明整行删除。记录删除/填补前后样本量。
- 异常值：默认用 Tukey IQR 栅栏或 MAD 稳健 z 检测，只标记，不自动删除。若任务或数据字典明确允许删除，才删除，并保留规则、阈值与前后样本量。
- 重复记录：完全重复行默认去重并保留 `duplicate_id`；部分重复只在数据字典给出主键时判断。记录删除条数与理由。
- 单位与类型：数据字典优先；未明单位不换算；日期字段不进入推断统计；数据库字段记录 schema、表名、查询来源。
- 每次清洗动作必须有 `rule_id`、`before_count`、`after_count`、`source_id`、`locator`。

产物：`cleaned.csv`、`cleaning_rules.json`、`cleaning_report.md`。

### 6.3 描述统计

对连续变量报告：有效样本量 n、组样本量、均值、标准差、中位数、IQR、最小值、最大值、分位数、偏度、峰度。对分类变量报告水平频数与比例。关键数字须带 `[S#]` 与 locator。

产物：`descriptive_stats.json`、`descriptive_stats.csv`。

### 6.4 推断统计选择

不得把多组问题塞进两样本 t 检验；必须先做假设检查；多重比较必须校正。

方法选择：

| 研究设计 | 条件 | 方法 |
|-|-|-|
| 两独立组 | 正态且方差齐 | Student t |
| 两独立组 | 正态但方差不齐 | Welch t |
| 两独立组 | 非正态或小样本 | Mann-Whitney U |
| 配对两组 | 差值正态 | paired t |
| 配对两组 | 差值非正态 | Wilcoxon signed-rank |
| 多独立组 | 正态且方差齐 | one-way ANOVA |
| 多独立组 | 正态但方差不齐 | Welch ANOVA |
| 多独立组 | 非正态 | K