---
name: data-analysis-runner
description: 面向科研数据清洗、统计、可视化、代码执行、SQLite 查询与可复核交付的 Agent Skill。真实解析 /input 材料，生成基线、Agent 增强结果、质量证据、异常说明与 /app/output/result.json 双回显契约。支持单命令全流程、无 draft 确定性兜底、预算感知与诚实降级。
version: 1.2.0
---

# data-analysis-runner：科研数据分析 Skill

## 0. 最高优先级：真实、完整、可复核、退出 0

本 Skill 的目标不是“看起来完成”，而是在给定材料上真实跑通从材料解析到结果可复算的完整链路，并在任何情况下都能让 Agent 拿到合法、可检查的产物。Agent 必须遵守四条铁律：

1. 真实读取 `/input` 下实际文件，不依赖文件名、领域标签或数据集名称猜测内容。
2. 不编造数据、引用、字段、金标准、评分、软件状态、白板或对比分数。
3. 缺失、异常、失败查询、不确定项必须显式写进 gaps、degradations、anomalies、pending_human，不静默修补。
4. 无论成功、部分成功还是失败，最终必须写出合法 `/app/output/result.json`，并以退出码 0 结束。

## 1. 运行时契约

- 输入：`/input/case.json`、`/input/task.md` 以及题目提供的实际材料（CSV、XLSX、JSON、SQLite、PDF、DOCX、图片等）。
- 工作目录：`/app/work`。
- 最终输出目录：`/app/output`。
- 必须产物：`/app/output/result.json`。
- Skill 安装位置：`/skills/weekly-skill`。
- 执行预算：64 次模型请求，900 秒，单次响应 16384 tokens（含推理）。
- 资源限制：Skill 提交包最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。
- 运行环境：优先使用纯 Python 标准库；若平台声明了 `environment/resources.yaml`，先读该文件确认可用的预装依赖和工具。

## 2. 单命令全流程入口

Agent 首选只执行一次主命令完成 init、build、selfcheck 三个阶段：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py run --input /input --output /app/output --work /app/work
```

字段含义：

- `--input`：原始案例输入目录。
- `--output`：最终交付目录。
- `--work`：工作目录，保存中间产物、解析结果、证据、日志、draft 和自检记录。

若该命令因参数拼写或子命令不存在而失败，Agent 必须先执行：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py --help
```

按实际帮助补齐参数。若 `run_skill.py` 不提供稳定单命令入口，改用 `analysis_core.py` 分阶段执行：

```bash
python3 /skills/weekly-skill/scripts/analysis_core.py init --input /input --work /app/work
python3 /skills/weekly-skill/scripts/analysis_core.py build --input /input --work /app/work --output /app/output
python3 /skills/weekly-skill/scripts/analysis_core.py selfcheck --input /input --work /app/work --output /app/output
```

如果脚本帮助展示了不同子命令名，以帮助为准，但必须按顺序完成 init → build → selfcheck，并且不能只做 init 就结束。最终产物始终交付到 `/app/output`。

## 3. Agent-first 双路径

Agent 有两个身份：判断拥有者和最终文本审核者。脚本负责确定性抽取、执行、渲染和最终 JSON 生成，Agent 负责从真实材料中形成科研判断。

### 3.1 Agent 路径

1. 先运行 init 得到材料台账、来源编号、候选抽取、冲突分组。
2. Agent 真实读取原文、原始表、数据库 schema、PDF 文本等材料。
3. Agent 把字段映射、清洗规则、统计口径、查询条件、可视化映射、关键 claim 的判断写入 `/app/work/draft.json`。
4. Agent 基于草稿执行 check 后再 build。
5. 生成产物后，Agent 逐项核验数字、来源和 locator，再决定是否改进 draft 并重新 build。

`/app/work/draft.json` 至少应表达以下内容：

- `case_id`：当前案例标识。
- `field_mapping`：数据字典字段与原始列名/表字段的映射。
- `cleaning`：缺失值策略、重复行策略、异常值判定、单位转换、有效数字。
- `statistics`：分组变量、目标变量、统计方法、前提检验方法、随机种子。
- `queries`：SQL 目标表、显式字段、过滤条件、排序方式。
- `visualization`：图表类型、x/y 轴字段、单位、图例、标题来源。
- `claims`：包含 `claim_id`、`source_id`、`locator`、`quote`、`strength`。

### 3.2 无 draft 时的确定性兜底

若 Agent 没有写出 `/app/work/draft.json`，或时间/预算不足，build 阶段必须使用 init 阶段台账中的确定性抽取结果生成实质工作稿，而不是空模板。兜底必须满足：

- 每个关键数字、字段映射、统计结果、查询结果带来源号 `[S#]`。
- 每个 claim 带 `quote` 和 `locator`，例如 `data.csv#row 12`、`db.sqlite#table_name.rowid=14`、`paper.pdf#page 2, para 3`。
- 在 `/app/output/result.json` 的 `gaps`、`degradations` 中诚实记录 `AUTO_EXTRACT`：说明该版来自确定性兜底抽取，Agent 未完全逐条复核。
- 两条路径产出同一套结果文件与同一份 `result.json` 契约，差异只体现在 `draft_path`、`reviewed_by_agent`、`uncertainty`、`pending_human`、`degradations` 等元数据中。

## 4. init：材料盘点与真实解析

Agent 或脚本执行 init 时必须完成如下事项：

### 4.1 盘点

读取 `/input/case.json`，提取：

- `case_id`。
- 材料路径。
- 输出契约 `output_contract`。
- 平台运行时约束。

读取 `/input/task.md`，提取任务要求、完成标准、需要交付的字段、评分证据范围、Runtime contract 中与本次运行相关的约束。

枚举 `/input` 下所有文件，记录：

- 文件名。
- 扩展名。
- 字节大小。
- 文件哈希（SHA-256，可用则记）。
- 材料类型。

将材料清单写入 `/app/work/inventory.json`。

若 `case.json` 缺失或不可读：

- 从 `task.md` 和 `/input` 目录内容推断。
- 仍无法判断 `case_id` 时，使用 `UNKNOWN_CASE_ID`，并在 result.json 的 `limitations` 和 `uncertainty` 中说明。

若 `task.md` 缺失：

- 以 `case.json` 和本 SKILL 的默认契约兜底，不能因此不执行。

### 4.2 解析

不同文件类型必须按真实内容解析：

- CSV：优先 `utf-8-sig`，失败再尝试 `latin-1` 或平台常用中文编码。记录列名、行数、缺失值数、重复行数、前几行样例。
- XLSX：用可用库读取真实单元格，记录 sheet 名、表头行、合并单元格、有效行数。
- JSON：加载后记录顶层类型、顶层键、嵌套结构、记录数。
- SQLite：连接数据库，读取 schema、表名、行数、字段名、字段类型、主键、外键。对每张表执行有限行探查查询，不假设表名。
- PDF：先尝试平台提供的 PDF 文本工具；不可用则使用可用 Python PDF 库提取页面文本。若 PDF 是扫描图片且无文本，明确标记 `pdf_no_text_layer`。
- DOCX：读取段落和表格，另存为纯文本和 CSV，不清空原有内容。
- 图片：若任务要求从图片读取数据，使用可用 OCR 工具；若仅作展示，记录图片路径和元数据。

每个来源分配 `source_id`，格式为 `S1`、`S2`、...，并在 `/app/work/inventory.json` 中记录与真实路径的映射。

解析结果写入 `/app/work/parsed/`，原始快照必须保留：

- CSV/XLSX：保存原始快照副本或标准化快照，记录原始列名、原始行数、解析编码。
- SQLite：保存 schema 文本和抽样结果。
- PDF/DOCX：保存提取文本和页码映射。
- JSON：保存原文件副本。

单个材料损坏、空文件或不支持：

- 尝试至少一种备用解析器。
- 仍失败则标记 `unparsable`、`empty_material`，写入 anomalies。
- 继续处理其余材料，不阻断全局。

## 5. build：确定性生成完整产物

build 阶段必须生成覆盖题目输出契约全部字段的产物。典型产物包括但不限于：

- `/app/output/data_summary.csv` 或 `.json`：数据概况，行数、列数、缺失值、重复数、字段类型、基本统计量。
- `/app/output/data_cleaned.csv` 或 `.xlsx`：清洗后表格；若使用 XLSX，同时保留 CSV 以便独立检查。
- `/app/output/statistics.csv` 或 `.json`：统计结果，每组统计量、检验方法、p 值、效应量、自由度等。
- `/app/output/figures/`：图表的 PNG/PDF/SVG；每个图必须有源数据依据。
- `/app/output/code/analysis_code.py` 或 notebook：可复跑代码，不能只是伪代码。
- `/app/output/query_results.csv` 或 `.json`：数据库查询结果、行数、执行状态。
- `/app/output/quality_report.md`：数据字典对照、规则表、运行命令、环境版本、随机种子、质量检查。
- `/app/output/anomalies.md` 或 `.json`：缺失、异常、失败查询、无法解释结果、待人工确认项。
- `/app/output/result.json`：最终结构化结果。

没有明确字段的契约至少也应包含上述 main deliverables；题面给出的 `output_contract` 必须全部覆盖，不得因为模板中没有就跳过。

### 5.1 数据清洗规则

必须明确写出：

- 哪些列被保留、重命名或删除，依据是什么。
- 缺失值处理策略：删除、插补、成对删除、标记不参与；绝不能把缺失值静默当作 0 参与均值。
- 重复行判定键：是全行重复还是业务主键重复；重复行保留策略和去重前后行数。
- 异常值判定：IQR、z-score 或数据字典阈值；异常值如何处理，是否剔除，是否报告。
- 单位转换和有效数字：数值是否统一单位，保留几位有效数字，依据数据字典或任务要求。
- 类型转换：字符串转数值、日期解析失败时的处理。

每个处理规则都要在 `quality_report.md` 中与数据字典对照，并在 `result.json` 中写入 `cleaning_rules` 或 `output_contract` 对应字段。

### 5.2 统计口径

做任何推断统计前，先检查前提条件：

- t 检验：检查正态性、方差齐性。若前提不满足，改用 Welch 校正或 Mann-Whitney U，并在结果中写明原因。
- 相关分析：连续正态可选 Pearson，否则 Spearman。
- 分组统计：明确分组变量、目标变量、聚合方式。
- 随机过程：固定随机种子，写入环境证据。

每个统计数字必须能追溯到：

- 原始数据行数。
- 清洗后行数。
- 分组后各组样本数。
- 公式或用到的代码函数。
- 来源 locator。

### 5.3 代码生成与执行

生成的代码必须真实执行，并保存执行证据：

- 运行命令。
- stdout。
- stderr。
- 退出状态。
- 运行时间。
- Python 版本和关键依赖版本。

代码不得硬编码作者本机路径；输入输出路径从参数或配置读取。

### 5.4 数据库查询

对 SQLite 数据库：

- 先读取 schema，不猜表名。
- 查询必须写明确 SELECT 字段、JOIN 条件、过滤条件、GROUP BY、排序和 LIMIT。
- 记录 SQL 原文、执行状态、返回行数。
- 空结果不得当作错误掩盖；保留 `row_count=0` 和查询条件。
- 若数据库损坏或锁定，复制到工作目录以只读方式打开，重试一次；失败则记录数据库错误，不使用虚构查询结果。

### 5.5 可视化

图表不是装饰。必须：

- x/y 轴标清楚变量名和单位。
- 图例与数据列一致。
- 标题或标注说明数据来源。
- 保留生成图形的代码。
- 同时保留 PDF/PNG 预览，便于检查。
- 不生成与数据字典无关的“漂亮图”。

### 5.6 质量与复现证据

至少写入：

- 数据版本或文件哈希。
- 输入文件路径。
- 解析器名称与版本。
- Python 版本。
- 关键依赖名称和版本，缺失依赖显式标注。
- 随机种子。
- 运行命令。
- 日志路径。
- 清洗规则。
- 统计口径。
- 查询 SQL。
- 变更记录。

## 6. result.json 双回显契约

`/app/output/result.json` 必须是合法 JSON，并满足以下结构：

顶层字段应包括：

- `case_id`
- `status`：`success`、`partial`、`failed`
- `message`
- `sources`
- `output_contract`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `change_records`
- `gaps`
- `anomalies`
- `seed`
- `python`
- `packages`
- `commands`
- `started_at`
- `ended_at`
- `runtime_seconds`
- `reviewed_by_agent`
- `draft_path`

原题给出的所有 `output_contract` 字段，包括 `case_id`，必须在 `result.json` 顶层和 `output_contract` 嵌套对象中各出现一次。两层不能改名、不能只放一边。顶层值用于快速校验；嵌套值用于保留原始契约结构。

示例结构：

```json
{
  "case_id": "case_001",
  "status": "success",
  "sources": [
    {
      "source_id": "S1",
      "path": "/input/data.csv",
      "type": "csv",
      "sha256": "abc123...",
      "rows": 150,
      "columns": 5
    }
  ],
  "data_summary": "outputs/data_summary.csv",
  "data_cleaned": "outputs/data_cleaned.csv",
  "statistics": "outputs/statistics.csv",
  "figures": ["outputs/figures/boxplot.png"],
  "code": "outputs/code/analysis_code.py",
  "query_results": "outputs/query_results.csv",
  "quality_report": "outputs/quality_report.md",
  "anomalies": "outputs/anomalies.md",
  "output_contract": {
    "case_id": "case_001",
    "data_summary": "outputs/data_summary.csv",
    "data_cleaned": "outputs/data_cleaned.csv",
    "statistics": "outputs/statistics.csv",
    "figures": ["outputs/figures/boxplot.png"],
    "code": "outputs/code/analysis_code.py",
    "query_results": "outputs/query_results.csv",
    "quality_report": "outputs/quality_report.md",
    "anomalies": "outputs/anomalies.md"
  }
}
```

实际字段按题面 `output_contract` 调整，但双回显和不丢字段的规则不变。

`status` 定义：

- `success`：全部契约产物存在，数字和来源已核验，无未报告的关键缺陷。
- `partial`：有确定性兜底、未复核项、缺失文件、不确定性或部分失败。
- `failed`：主结果无法生成，但仍然写出合法 result.json，列明失败原因。

## 7. 来源定位与可核验性

每个关键数字、截断、统计结果、SQL 结果、图表数据映射必须带证据：

- `source_id`：指向 `sources` 中的 `S#`。
- `locator`：定位格式应可被他人核对，例如：
  - CSV：`S1#row 12`。
  - XLSX：`S2#Sheet1!row 15`。
  - PDF：`S3#page 2, paragraph 3`。
  - SQLite：`S4#table_name.rowid=22` 或 `S4#table_name(pk=7)`。
  - JSON：`S5#array[3].field_name`。

报告中的数字必须与 `evidence_table` 或 `claims` 文件一一对应。没有来源的数字不得进入 final deliverable。若任务允许推断，推断的基础必须写明，并标记 `inferred`。

## 8. 异常处理与鲁棒性

### 8.1 常见异常

| 异常 | 要求 |
| --- | --- |
| 缺少列 | 不静默补列；写明缺列、影响，使用可选的映射或标记 `pending_human`。 |
| 类型不符 | 记录实际类型，尝试安全转换；失败则不强行转换。 |
| 依赖缺失 | 优先标准库和平台已有工具；缺依赖写清楚替代方案，不伪装已安装。 |
| 查询为空 | 保留空结果和查询条件，不算失败，除非空结果与任务冲突。 |
| 数值溢出 | 捕获异常，记录输入范围，不做静默截断。 |
| 权限不足 | 记录路径和错误，尝试可写目录，不重复尝试同一失败操作。 |
| PDF 无文本层 | 标记 `pdf_no_text_layer`，不做虚假文字提取。 |
| SQLite 锁定 | 复制到工作目录只读打开，重试一次；仍然失败则记录。 |
| 编码错误 | 按 UTF-8-SIG → 系统中文编码 → Latin-1 顺序尝试，记录最终编码。 |
| 超时或预算不足 | 立即保存 partial 结果，优先保证 result.json 合法。 |

### 8.2 隐藏案例鲁棒性

隐藏案例大概率会覆盖三类：

1. 正常案例：材料完整、格式标准、任务明确。目标是结果正确、完整、可复算。
2. 边界案例：列名有空格、大小写不一致、重复列、缺失值、单位不同、SQLite 表名与字段名偏离、PDF 扫描件、空查询结果。必须通过真实解析、列名清洗映射、显式规则、空结果说明来应对。
3. 异常案例：缺 `case.json`、缺列、数据库损坏、无 text layer、任务说明不完整、执行环境缺依赖。必须通过 fallback、异常记录、诚实 partial、标准库兜底、合法 result.json 和退出码 0 来应对。

不要因为案例叫 Iris、Wine、Concrete 就假设字段名、行数或结论，必须读取实际文件。

## 9. 预算策略

推荐预算：

- 首次单命令运行：0-2 次模型请求。
- init 和材料抽查：2-6 次请求。
- draft 判断与关键核验：10-20 次请求。
- 成稿撰写与补全预览：6-12 次请求。
- selfcheck 与 result.json 收尾：4-8 次请求。
- 重试余量：至少保留 10 次请求和 120 秒。

硬性规则：

- 第一次运行脚本后，先检查 `/app/output` 是否已有全套基线；如果有，先保存完整基线，不要重复计算。
- 模型请求接近 50 次，或剩余时间少于 180 秒，立即进入收尾。
- 收尾优先级：合法 result.json > 主结果文件 > 质量报告 > 图表预览 > 精美成稿。
- 任何情况下都不要为了追求“更多分析”而牺牲 result.json 和退出码 0。

## 10. selfcheck 自检清单

build 完成后，必须核对：

1. `/app/output/result.json` 存在且 JSON 合法。
2. `case_id` 在顶层和 `output_contract` 中一致且非空。
3. `status` 是 `success`、`partial` 或 `failed` 之一。
4. 题面 `output_contract` 每个字段都有对应文件或值。
5. 每个关键数字在报告中有来源 `[S#]` 和 locator。
6. 清洗前后行数、缺失值、重复值说明一致。
7. 统计方法和前提检验已写明。
8. 图表有 PNG/PDF，坐标轴和单位与数据一致。
9. 代码文件真实存在，不包含本机硬编码路径。
10. SQL 查询有结果文件或空结果说明。
11. `sources` 中有真实读取的文件路径和哈希。
12. `uncertainty`、`pending_human`、`errors`、`degradations`、`gaps` 非空则必须诚实填写。
13. 有 `change_records`，记录 Agent 或脚本的关键修改。
14. 可编辑 Office/slide/diagram 若出现，必须有 PDF/PNG/CSV 预览。
15. 最终退出码为 0。

自检记录写入 `/app/work/selfcheck.json`，并在 `quality_report.md` 中给出自检结论。

## 11. 明确禁止

- 禁止根据文件名或数据集名称猜测内容。
- 禁止把缺失值直接当 0。
- 禁止不去重就做分组统计。
- 禁止跳过统计前提直接报 p 值。
- 禁止生成没有来源的数字或直接复制模板文案当最终结论。
- 禁止伪造 `golden_standard`、白板、基础 Agent 分数、benchmark 分数。
- 禁止只交付 result.json 而没有实际分析产物。
- 禁止以非 0 退出码结束。
- 禁止在最终答案里声称“平台打分”“预测试结果”等未经平台给出的信息。

## 12. 最小调用示例

输入示例：

- `/input/case.json`：包含 `case_id: "case_demo_001"`，材料列表，输出契约。
- `/input/task.md`：说明需要完成清洗、统计、可视化、SQLite 查询和可复算证据。
- `/input/records.csv`：实际数据。
- `/input/records.sqlite`：实际数据库。

调用示例：

```bash
python3 /skills/weekly-skill/scripts/run_skill.py run --input /input --output /app/output --work /app/work
```

预期输出示例（必须在文件中标明为示例，不冒充正式案例结果）：

- `/app/output/data_cleaned.csv`
- `/app/output/statistics.csv`
- `/app/output/figures/distribution.png`
- `/app/output/code/analysis_code.py`
- `/app/output/query_results.csv`
- `/app/output/quality_report.md`
- `/app/output/anomalies.md`
- `/app/output/result.json`

result.json 示意片段：

```json
{
  "case_id": "case_demo_001",
  "status": "success",
  "output_contract": {
    "case_id": "case_demo_001",
    "data_cleaned": "outputs/data_cleaned.csv"
  }
}
```

## 13. 收尾要求

每次运行最后必须做三件事：

1. 确认 `/app/output/result.json` 为合法 JSON。
2. 确认 result.json 中 status、sources、uncertainty、pending_human、errors、degradations、output_contract 均存在且诚实。
3. 以退出码 0 结束，即使 status 是 `partial` 或 `failed`。

只要做到以上流程，Skill 就能稳定输出可复核科研数据结果，并在实际效果、使用增益、创新证据、可靠体验和生态贡献上形成可检查的证据链。