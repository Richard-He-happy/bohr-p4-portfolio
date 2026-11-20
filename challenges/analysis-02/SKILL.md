---
name: statistical-analysis-interpretation
description: 真实科研数据表统计 Skill：解析原始材料（CSV/TSV/TXT/SQLite/PDF/DOCX 等），完成清洗、描述统计、假设检验、效应量、置信区间与可核验报告；先生成基线全套交付物，再由 Harness Agent 亲自核对材料与数字并补强。适用于统计分析与结果解读 Benchmark。
version: 2.0.0
---

# 统计分析与结果解读（analysis-02）

**用途**：读真实科研数据材料，清洗到可统计状态，按研究设计与假设检验结果选择检验方法，给出效应量与置信区间，并把结论翻译成科研人员可判断的表述。  
**铁律**：脚本（`scripts/main.py`、`scripts/statsx.py`）只是工具，负责生成基线数字与全套中间表。最终交付物必须由你（Harness Agent）亲自读取 `/input` 原始材料、核对证据、推导结论、撰写/制作。禁止把脚本骨架、模板输出或任何未经过真实验证的中间产物直接当作最终成品。

## 1. 运行时契约与目录约定

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`，以及题面规定的材料（CSV/TSV/TXT/SQLite/PDF/DOCX/图片等）。必须真实解析内容，不得按文件名或领域标签猜测/补造 |
| 工作目录 | `/app/work`：中间解析、临时表、核验草稿；不污染原始 `/input` |
| 输出目录 | `/app/output`：所有最终交付物与 `result.json` |
| 调用 | `python3 scripts/main.py --input /input --output /app/output`；`--help` 可用；不依赖 CWD |
| 依赖 | 仅 Python 标准库（≥3.8）；无网络；不写 `/input` |
| 退出码 | 恒为 0；异常写入 `errors`/`degradations` 后仍返回 0 |
| 首写 | 任何分析开始前先写 partial `result.json`；末尾无条件 finalize 覆盖 |
| 确定性 | 分组排序固定（n 降序、值升序）；bootstrap 种子由 `zlib.crc32(标签+盐)` 派生；浮点按 `%.12g` 序列化 |

## 2. 执行流程：从盘点输入到最终 result.json

### 步骤 0：先落盘 partial 并初始化
**输入**：`/input/case.json`（可能不存在或损坏）。  
**动作**：读取或容错发现 `case_id`；读取 `output_contract` 原样透传；若契约缺失，使用标准契约字段：`descriptive`、`hypothesis_tests`、`effect_sizes`、`confidence_intervals`、`cleaning`、`interpretation`、`sources`、`uncertainty`、`pending_human`，并标记 `contract_missing=true`。立刻在 `/app/output/result.json` 写 partial：`status="partial"`，所有契约字段空值/空数组，`errors`/`degradations`/`pending_human` 初始。  
**输出**：首个 honest partial `result.json`。  
**失败分支**：`/app/output` 不可写则写 `/app/work/result.json` 并记录；继续。

### 步骤 1：盘点输入
**输入**：`/input` 目录树。  
**动作**：递归列出文件大小、类型；读取 `case.json` 与 `task.md` 原文；识别材料类别（表格、数据库、PDF、DOCX、图片、字典）；编码探测 UTF-8/BOM/GB18030/Latin-1；记录哪些文件可读。**不依据文件名/领域标签推断内容**。  
**输出**：`sources` 初始清单（路径、大小、类型、可读状态）。  
**失败分支**：文件不可读 -> 写 `errors`/`degradations`，不中断。

### 步骤 2：用工具真实解析材料
**输入**：步骤 1 清单中的材料文件。  
**动作**：
- CSV/TSV/TXT：真实读取单元格；分隔符按首行投票；首行纯数值时命名 `col1..colN`；原值保留。
- SQLite：读取所有业务表，按行数最多选表，记录 `sources.relation`。
- PDF：使用 `pdf-text-tool` 或 `environment/resources.yaml` 提供的等价工具提取文本/表格到 `/app/work/parsed/`；若为扫描图片且无 OCR，标注不支持。**禁止从文件名补造表格**。
- DOCX：使用可用解析工具提取段落和表格；无法解析则标 `pending_human`。
- 图片：需要 OCR；不可用则记录 `degradations`。
- 数据字典：从 JSON/MD 真实读取字段名、单位、说明；字典单位优先于列名推断。
- 字段类型：日期形如 `YYYY-MM-DD` / `YYYY/MM/DD` 判为非数值，只作分类描述，不进推断与相关。  
**输出**：解析后的材料快照、标准 CSV/TSV（如需交给脚本）。  
**失败分支**：无法解析 -> 保留原始限制说明，`status=input_error` 或 `insufficient_evidence`，仍继续写出合法 result.json。

### 步骤 3：运行基线脚本，生成全套基线交付物
**输入**：`/input` 与 `/app/work/parsed` 中可被脚本识别的主数据表。  
**动作**：运行 `python3 scripts/main.py --input /input --output /app/output`；若主数据表来自 PDF/DOCX 解析，将解析后的 CSV 放在 `/app/work` 并确保脚本能读取，但其 `sources` 仍指向原始材料与解析中间文件。脚本生成清洗、描述统计、检验、效应量、CI、报告、图表数据。**如果脚本崩溃**，用已读取的真实材料手工生成最小完整交付物。  
**输出**：`/app/output/result.json`（基线 finalize）、`analysis.md`、`cleaned.csv`、`tables/*.csv`、`run.log`。  
**失败分支**：脚本失败 -> 保留错误，Agent 用解析材料写出最小合法结果；绝不因脚本失败而空输出。

### 步骤 4：Agent 亲自核对与推导成品
**输入**：基线全套 + 原始材料 + task.md 评分点。  
**动作**：你必须亲自打开并核对关键数字与材料：n、缺失/异常/重复计数、单位、检验方法是否与设计/分布假设匹配、p/效应量/CI 是否一致、结论是否恰当。对照 rubric 和 output_contract 逐项检查。若基线有误或与材料冲突，在 `analysis.md` 中修订，并把修订依据写 `changes`/`conflicts`。无法确认或口径不明标 `pending_human`/`limitations`，不得编造。把本次 Agent 核验证据写入 result.json：`reviewed_by_agent`、`agent_checks`、`conflicts`、`pending_human`、`uncertainty`。  
**输出**：增强后的完整交付物。  
**失败分支**：预算不足或 Agent 无法完成核验 -> 保留基线全部产物，标注 `reviewed_by_agent=false` 与原因；仍要求契约字段完整。

### 步骤 5：可编辑产物预览
**输入**：`/app/output` 下可编辑 Office/幻灯片/图形产物（如有）。  
**动作**：使用环境提供的渲染工具生成 PDF/PNG；真实渲染，不得用占位图。如果本题无此类产物，跳过。  
**输出**：PDF/PNG 预览。  
**失败分支**：渲染失败 -> 写 `degradations`，保留可编辑文件，不伪造。

### 步骤 6：自检 rubric 并回填最终 result.json
**输入**：`/app/output` 所有文件与结果草稿。  
**动作**：逐项执行第 7 节自检清单；核对 `output_