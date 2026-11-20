---
name: sci-data-cleaning
description: >-
  Audit-grade cleaning of scientific tabular data. Reads actual /input case files and actual source tables without a pre-extracted answer layer, classifies missing/censored/sentinel values without statistical imputation, canonicalises numeric/date/unit/encoding faults with reversible source-linked transforms, resolves duplicate records under dictionary-derived keys, and emits analysis-ready tables plus field-level quality reports and result.json under the official runtime contract. Use when a case provides dirty CSV/TSV/PDF/DOCX table transcriptions, a data dictionary, and a cleaning workorder.
version: 1.4.0
---

# 科研数据清洗与处理：可复核清洗流水线

## 0. 铁律（最高优先级，先读）

1. 以 /input 实际文件为唯一事实依据。不要按文件名、领域标签或记忆补造数据；不得生成金标准、白板或 benchmark 分数。
2. 禁止统计填补：不推断总体统计量，不填补缺失或无效源值。缺失、低于检出限、未检测、真值 0 必须分开标记。
3. 所有输出中的关键数字、判断、规则必须有来源：`[S#]` 来源编号 + `文件#行号/段落号` locator。不能核验的数字不得写进结论。
4. 结构化 JSON 由脚本生成或被脚本校验。不得手工篡改脚本输出的 `result.json`、`evidence_table.json` 结构；需要更正时用脚本或把修订写入 changes/pending_human。
5. 不依赖 quality-gold.md 或任何未提供的金标准文件；隐藏来源与故障 provenance 只能从实际材料中读取。
6. 退出必须成功：无论失败或部分完成，必须落盘合法 result.json 并确保命令退出 0。部分结果要标明 limits。
7. 只处理题面五类：缺失值、异常值、重复记录、格式/单位/编码转换、数据质量报告。不做统计建模、不做出版级图表，除非 task.md 明确要求。

## 1. 单命令入口与双路径

### 1.1 首选单命令

    python3 /skills/weekly-skill/scripts/main.py run \
      --input /input \
      --output /app/output \
      --work /app/work

该命令内部顺序完成 init → build → selfcheck：

- init：盘点 /input，建立来源台账、候选表、字典、workorder、冲突分组，写 /app/work/ledger.json；
- build：校验/兜底抽取，生成全套结构化产物与初步 result.json；
- selfcheck：按 output_contract 和一致性断言检查产物，写 verification.json/assertions.json。

如果实际安装版本的 `main.py` 不支持 run 子命令，使用兼容命令：

    python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output

但首选 run，因为它体现 init→build→selfcheck 并显式写 /app/work。

### 1.2 Agent-first 增量路径（预算允许时）

如果能够读到 /app/work/ledger.json：

1. 读台账和原始材料，逐字段判断角色、单位、缺失哨兵、异常阈值、主键、重复保留规则；
2. 将决策写入 `/app/work/draft.json`。`draft.json` 只许引用实际文件中的词典/workorder/表格证据；每个字段必须带 locator；
3. 运行：

       python3 /skills/weekly-skill/scripts/main.py check --work /app/work --output /app/output
       python3 /skills/weekly-skill/scripts/main.py build --work /app/work --output /app/output

`check` 校验 draft 与 ledger 冲突；`build` 将 draft 与确定性抽取结果合并。若脚本不支持子命令，回退到完整 run 命令，并把人工判断写入 `agent_review.json` 而不是 draft。

### 1.3 无 draft 时

`build` 不得等待 draft。它必须用 ledger 中的确定性规则完成实质抽取：逐字 quote + locator，并在 `degradations` 中诚实记录 `AUTO_EXTRACT`。因此预算紧张时可直接单命令交付。

## 2. 目录与最小交付物

输入：

- `/input/case.json`
- `/input/task.md`
- `/input/**` 其他材料（CSV/TSV/TXT/PDF/DOCX/图片等）

工作区：

- `/app/work/ledger.json`
- `/app/work/extracted/`
- `/app/work/draft.json`（Agent 可选）
- `/app/work/sources.json`

最终输出必须至少包含：

- `result.json`
- `cleaned.csv`
- `field_issues.csv`
- `duplicates.csv`
- `transform_log.csv`
- `cleaning_rules.json`
- `quality_report.md`
- `evidence_table.json`
- `report_consistency.json` 或 `assertions.json`
- `sources.json`
- `run.log`
- `pending_human.json`
- `agent_review.json`（Agent 核验，可选但推荐）

若 task.md 要求图片/Office/图表：

- 可编辑原件放 /app/output；
- 同时渲染 PDF/PNG 预览供检查；
- 图表代码/数据放 /app/output，不得以截图冒充可复核文件。

## 3. 执行流程

### 步骤 1：读 case 与盘点

- 读 `/input/case.json`（不存在则找 `case*.json`）。
- 提取 `case_id`、`output_contract`、`files`、`data_dictionary`/`fields`/`columns`/`schema`、`workorder`。
- 键名按去分隔符小写匹配，不假设固定键。
- 递归扫描 /input，列出所有文件、大小、sha256、可识别格式。
- 输出：来源台账。

失败处理：

- case.json 缺失/坏 JSON：尝试其他 case*.json；仍失败记 `input_error`，继续扫描其余材料。

### 步骤 2：解析实际材料

- CSV/TSV/TXT：读取并保存未加工副本；检测编码、分隔符、BOM 等。
- PDF：用平台 pdf-text-tool 提取文本/表格，保存到 /app/work/extracted/；不得按文件名假设内容。
- DOCX/图片：用平台可用工具提取；无法提取则写 pending_human 和 degradations，不猜测。
- 主表选择：case.json 中指定文件优先；否则取可解析行数最多的表；将其他表作为来源或 lookup 表，计入 sources。
- 字典优先级：独立字典文件 > case.json 内联 data_dictionary。字段名大小写/标点/单位分隔符归一后匹配。

### 步骤 3：运行 init / ledger

- 执行 run 或 init 子命令。
- 检查 /app/work/ledger.json 是否包含：
  - source inventory：id、文件、locator、sha256、parser；
  - 候选表/列；
  - 字典字段语义、单位、QC 规则；
  - workorder 指令；
  - 冲突/歧义分组。
- 若 ledger 缺项，补写 /app/work/draft.json 或 agent_review.json，不手工改脚本结构化文件。

### 步骤 4：制定字段级规则

按五类给每列生成规则，写入 draft（或让 build 确定性生成）。规则必须包含：

- `rule_id`
- `field`
- `action`
- `source_id`
- `locator`
- `missing_reason_code`（缺失类型映射）
- `unit`、`conversion_factor`、`conversion_reversible`
- `anomaly_lower`、`anomaly_upper`、`method`
- `duplicate_key`
- `keep_rule`

缺失值处置原则：

| 情况 | 处理 |
|---|---|
| 空格/空字符串 | 标记 `missing_reason_code=blank`，原值保留 |
| "ND"/"未检出" | 标记 `not_detected`，不填 0 |
| "<LOD"/"低于检出限" | 标记 `below_LOQ`，保留符号与检出限 |
| -999 / -99 / sentinel | 标记 `sentinel`，不参与统计 |
| 真值 0 | 标记 `zero`，不得归为缺失 |

异常值处理：

- 硬越界来自字典物理上下限；
- 软异常用 MAD-z（退化 IQR）判定；
- 只标记不删除，除非 task.md 明确要求剔除。

重复记录处理：

- 主键由字典/workorder 指定；缺失时用整行，只去完全重复；
- 归一：大小写、空格、分隔符、前导零、单位写法；
- 保留最完整记录，其余进 duplicates.csv，并注明保留依据。

格式与单位处理：

- 处理千分位、小数逗号、科学计数、脚注符、尾随单位、日期格式、编码乱码；
- 每个转换必须记录前后值、规则和 locator，保持可逆或保留原始映射表。

### 步骤 5：build 生成全套产物

必须生成：

1. `cleaned.csv`：包含 `__source_id`、`__locator`、`__row_id`、清洗字段、缺失/异常标记列；保留原值或引用 transform_log；
2. `field_issues.csv`：每字段每类问题计数与来源；
3. `duplicates.csv`：重复组、保留行、删去行、归因；
4. `transform_log.csv`：每个单元格转换前后、规则、来源、是否可逆；
5. `cleaning_rules.json`：字段级规则外置；
6. `quality_report.md`：字段级问题清单、动作、影响范围；每个数字从上面表中反算；
7. `evidence_table.json`：每个关键 claim 含 `claim_id, source_id, locator, quote, strength, support_scope`；
8. `report_consistency.json`/`assertions.json`：机器校验断言；
9. `run.log`、`sources.json`、`pending_human.json`。

### 步骤 6：Agent 核验与成稿

- 抽查每列角色、单位、哨兵、异常阈值；
- 随机抽 3-5 组原值→清洗值，核对 quote/locator；
- 检查质量报告数字是否由 field_issues.csv/cleaned.csv/duplicates.csv 反算；
- 写 `agent_review.json`：claim_id → verified/rejected/reason，script_fixes；
- 若报告与表不一致：必须修正。优先改脚本/规则重跑；不能修则写 pending_human 和 errors，不得静默；
- 正文型交付物（如 task 要求结论）只引用 evidence_table 中已有 claim，不得新造数字。

### 步骤 7：selfcheck 与 result.json

- 验证 `output_contract` 所有原始字段都有对应文件和 result.json 键；
- result.json 双回显：契约字段（含 case_id）在顶层与 nested `output_contract` 各出现一次；
- result.json 必须含：
  `case_id`, `status`, `sources`, `summary`, `artifacts`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `reviewed_by_agent`, `output_contract`。

status 取值：

- `success`：所有契约字段完整且自检通过；
- `partial`：有交付但不完整/存在未解决问题；
- `input_error`：输入缺失/损坏无法完整执行；
- `insufficient_evidence`：无数据表或无法处理。

- 失败把错误写入 `errors` 和 `degradations`，不得抛栈；
- 最终退出码 0。

## 4. result.json 契约示例

    {
      "case_id": "case-001",
      "status": "success",
      "sources": [
        {"id": "S1", "file": "table1.csv", "locator": "table1.csv#L1-L50", "sha256": "...", "parser": "python_csv"}
      ],
      "summary": {
        "n_source_rows": 100,
        "n_cleaned_rows": 98,
        "n_missing_cells": 10,
        "n_anomalies": 3,
        "n_duplicate_groups": 2
      },
      "artifacts": {"cleaned_table": "cleaned.csv"},
      "uncertainty": [],
      "pending_human": [],
      "errors": [],
      "degradations": [],
      "changes": [],
      "reviewed_by_agent": true,
      "cleaned_table": "cleaned.csv",
      "field_issues": "field_issues.csv",
      "quality_report": "quality_report.md",
      "output_contract": {
        "case_id": "case-001",
        "cleaned_table": "cleaned.csv",
        "field_issues": "field_issues.csv",
        "quality_report": "quality_report.md"
      }
    }

注：示例仅为接口说明；实际受 case.json 的 output_contract 驱动，不得用示例冒充正式结果。

## 5. 隐藏案例鲁棒性

任何情况下都必须生成 `result.json` 并退出 0。

| 情形 | 必要响应 |
|---|---|
| case.json 缺失/坏 JSON | 扫描 case*.json；仍失败记 input_error，继续目录扫描 |
| 无数据表 | status=insufficient_evidence，pending_human=[NO_TABLE] |
| 空表/仅表头 | 正常产出空 cleaned.csv/field_issues.csv，n=0 |
| 无字典/主键/workorder | 整行去重，只去完全重复；写 KEY_NOT_FOUND；不猜主键 |
| 全列缺失 | 列 missing_pct=100，仍在 field_issues.csv 中 |
| PDF/DOCX/图片无法解析 | 记 UNSUPPORTED_FORMAT 或提取错误，写 pending_human；不猜测内容 |
| 编码乱码 | 多编码打分，GB18030 回退；写 degradations |
| 单位不明 | 保留原值 + U2，写 uncertainty |
| 主键冲突且值冲突；日期 d/m 与 m/d 均合法；千分位/小数歧义 | 保留原值、打标记、写 pending_human/uncertainty；不擅自选边 |
| 输出目录不可写 | 退到 ./output、系统临时目录，并在 run.log 说明 |
| 超时 | 留 60 秒收尾；到 840 秒停止改进，finalize result.json |
| 行数超限 | 截断并写 ROW_LIMIT 到 degradations |

## 6. 预算策略

模型请求预算 64 次、900 秒。单案例目标 ≤20 次。

优先级：

1. 单命令端到端脚本产出全套基线（1-2 次调用）；
2. 保存 honest partial result.json；
3. 只对关键字段/随机样本核验（3-6 次）；
4. 修补明显不一致（2-4 次）；
5. 最后自检回填（1-2 次）。

禁止无意义循环、重复读取同一文件、逐行人工全部复核。接近预算先落盘。

## 7. 评分证据映射

- 实际效果：cleaned.csv、field_issues.csv、quality_report.md、duplicates.csv、transform_log.csv、evidence_table.json；
- 结果正确性：rules 带 locator；报告数字机器反算；单位可逆；重复主键可回溯；
- 可核验性：sources.sha256、run.log、原值→新值、locator；
- 使用增益：单命令、确定性、无人工干预、报告与表一致；
- 创新增益：字段级规则推断、跨表主键对齐、可逆单位映射、一致性自检；
- 可靠体验：纯标准库、离线、退出 0、空表/乱码/单位不明枚举处理；
- 生态贡献：SKILL.md、references/skill_guide.md、quality_report_template.md、cleaning_rules.json；如需补充环境声明，写入 environment/resources.yaml 并在 SKILL.md 说明。

## 8. 限制

- 不做统计建模、假设检验、图表美化；如 task 要求统计图表，仅做描述性统计或直接基于清洗后数据运行题面指定代码，并注明假设；
- 不推断总体统计量，不填补无效源值；
- 脚本只稳定处理文本表；PDF/DOCX 等须先解析；
- 对主观判断保留参考答案区间与不确定性，不强行单一值；
- 不生成预训练答案、正式测试案例、白板或 benchmark 分数。

## 9. 最小调用示例

    mkdir -p /app/work /app/output
    python3 /skills/weekly-skill/scripts/main.py run \
      --input /input \
      --output /app/output \
      --work /app/work

说明：示例仅为接口调用，不包含任何正式案例答案。若平台安装路径不同，以实际 /skills/weekly-skill 路径为准。