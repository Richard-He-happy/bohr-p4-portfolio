---
name: experiment-result-anomaly-explainer
description: Interpret measured experimental result data (instrument CSV/TSV traces, replicate worksheets, multi-batch tables, multi-sheet XLSX workbooks) into five verifiable sections — trend with turning points, anomalies bound to batch/channel, cause candidates ranked by evidence and testability, an executable recheck checklist, and a next-round protocol — then write result.json with every case output_contract field backfilled, plus protocol.md, anomaly_table.csv, recheck_checklist.csv and risk_table.csv. Use when a case supplies readings, curves, spectra, assay sheets or device logs and asks what the data shows, which point is abnormal, why it happened, what to recheck, and what to run next.
version: 1.0.0
license: MIT
---

# experiment-result-anomaly-explainer

把一份实测实验数据解释成五段可检查结论（趋势 / 异常点 / 可能原因 / 复核步骤 / 后续实验建议），
并把案例给定的 `output_contract` 全字段回填进 `result.json`。全流程确定性、离线、只用 Python 标准库。

## 1. 何时使用

满足任一条件即可加载：

- 输入含**实测读数**：仪器导出 CSV/TSV、重复测量表、多批次/多通道工作表、XLSX 多 sheet、设备日志；
- 用户问「这批数据说明了什么」「哪个点异常」「为什么异常」「怎么复核」「下一步做什么实验」；
- 案例带有 `output_contract`（需逐字段回填）或 `case_id`（需原样保留）。

不适用：只有实验设计需求、没有数据的「方案生成」题；纯文献综述；纯统计建模。

## 2. 调用方式

```bash
python3 scripts/main.py --input <输入目录> --output <输出目录>
```

- 输入默认 `/input`，输出默认 `/app/output`；也接受 `--input/--output`、`$INPUT_DIR/$OUTPUT_DIR`、
  `/bohr-workspace/input|output`、或 CWD 下的 `input/`。
- 脚本用 `Path(__file__).resolve().parent` 定位同目录 `analysis.py`，**与当前工作目录无关**。
- `--help` 打印用法，`--version` 打印版本。
- **退出码恒为 0**：异常只写入 `errors`/`degradations`/`pending_human`，不中断运行。
- 启动即写合法 partial `result.json`（`status: partial`），分析完成后无条件覆盖为 finalize 版本。

## 3. 输入发现（按语义，不假设固定键名）

| 来源 | 处理 |
|---|---|
| `case.json` | 取 `case_id`、`topic`、`domain`、`goal`、`equipment`、`reagents`、`time/budget/personnel`、`output_contract`；键名归一化匹配（大小写/下划线/空格无关），也接受 `outputContract` |
| `task.md`、`material.json` | 跳过（题面与清单，不是数据） |
| `*.csv/.tsv/.txt/.dat/.prn` | 按首行计数最多的分隔符切分（`,` `\t` `;` `\|`），无分隔符时按 2+ 空格或制表符切 |
| `*.xlsx/.xlsm` | 纯标准库解析 sharedStrings + worksheet XML，逐 sheet 读取 |
| 其他 `*.json` | 仅登记为材料，不当表解析 |
| `*.pdf / *.png / *.jpg / *.docx` | **不做数值读取**，记 `sources[].parsed = not-read` 与 `pending_human`，写入 `uncertainty` |

`case.json` 缺失或损坏：先扫描同级 `case*.json`；仍失败则继续分析材料表，`case_id` 记 `UNKNOWN`，
`status` 记 `partial` 或 `insufficient_evidence`，错误写入 `errors`。

## 4. 五段输出（主结果）

| 段落 | `result.json` 字段 | 内容 |
|---|---|---|
| 趋势 | `trend[]` | 每个「自变量 × 指标」给斜率、R²、方向、幅度%、拐点 x、`locator` |
| 异常点 | `anomalies[]` | 稳健 z、参照中枢、偏离%、阈值、批次、`locator`（文件\|表\|行\|列）、`quote` |
| 可能原因 | `causes[]` | 候选原因、支持证据、可检验性(1–5)、验证动作、成立/否定判据、`rank` |
| 复核步骤 | `recheck[]` | 动作、目标字段、判据、成立/否定分支、工时 |
| 后续实验 | `next_experiment[]` | 变更项、理由、**判别性结果**、关闭的缺口、相对成本 |

配套主产物：`protocol.md`（假设/变量/对照/步骤/判据/资源/风险/缺口）、`anomaly_table.csv`、
`recheck_checklist.csv`、`risk_table.csv`；五段同时汇总在 `five_sections`。

## 5. 输出契约回填规则

- **键名不改、层级不改**：`output_contract` 每个键原样保留，未知字段留在原位，缺值写 `null` 或 `[]`。
- 按**语义别名**回填（`summary/conclusion/结论`、`trend/趋势`、`anomalies/异常`、`causes/原因`、
  `recheck/复核`、`next/后续`、`protocol/方案`、`risks/风险`、`sources`、`uncertainty`…），
  并把已回填字段提升到顶层；未匹配的契约键保持 `null`。
- `case_id` 原样保留，不重写、不改大小写。
- `result.json` 必含：`case_id`、`status`、`summary`、`sources[]`、`uncertainty[]`、`counts`、`runtime`。

## 6. 方案 / 依据 / 确认项（题面 3 节要求的三块内容）

| 内容 | 字段 | 完成标准 |
|---|---|---|
| 实验方案 | `protocol.{hypotheses,variables,controls,steps,parameters,materials,equipment,schedule,reading_criteria}` + `protocol.md` | 实验人员可据此执行；缺什么写在 `pending_human` |
| 依据与风险 | `protocol.basis[]`（choice/source/locator/quote）、`protocol.risks[]`、`risk_table.csv` | 每条设计选择可回指来源，假设与边界可复核 |
| 确认项 | `protocol.confirmations[]`：设备可用性 / 安全 / 伦理 / 专家确认，`status` 恒为 `unconfirmed` | **不把未确认建议写成可执行事实**；未经确认即显式标未确认 |

`protocol.basis` 的两类来源：数据侧取 `anomalies[].locator` + `quote`（原表行/列逐字值）；
方法侧取 `scripts/analysis.py#CFG` 的阈值原文。材料未给的仪器参数、试剂目录号、限度值一律不填。

## 7. 异常与降级处置

| 情形 | 处置 |
|---|---|
| 输入目录不存在 | `errors` 记 `input`；仍写结果，`status: input_error`，退出 0 |
| `case.json` 坏 JSON | `errors` 记 `case`；继续分析材料，`status: partial` |
| 无可解析数值表 | `status: insufficient_evidence`，`feasibility.blocking` 说明，仍输出 protocol.md 与空表 |
| 单表解析异常 | 该文件记 `sources[].parsed = error`，其余表继续，不影响退出码 |
| PDF/图片/未支持格式 | 记 `not-read` + `pending_human`，不猜内容、不编数值 |
| 重复不足 / 缺对照 / 读数封顶 / 单位不一 | 打标签 `short_reps`/`no_control`/`clipping`/`magnitude`，进入原因表与复核表 |
| 结论冲突（某点既像饱和又像录入错误） | 两个候选都保留、按支持证据与可检验性排序，各写成立/否定判据，不强行合一 |

## 8. 资源与依赖

- `scripts/main.py` — 输入发现、表解析、契约回填、产物写出、主流程。
- `scripts/analysis.py` — 数值内核（稳健统计、拐点、曲线比较、批次绑定、原因排序）。
- `references/input-formats.md` — 输入格式、字段含义、产物结构。
- `references/method-and-thresholds.md` — 判定方法、阈值、排序规则、适用条件与限制。
- `references/checklists.md` — 使用清单、最小调用示例（标明为示例）、评分自查表。

依赖：Python 3.8+ 标准库（`argparse csv json os re sys time zipfile xml.etree math collections pathlib`）。
无第三方依赖、无网络、无外部数据文件。

## 9. 预算与断点

- 平台预算 64 次请求 / 900 秒；`runtime.within_budget` 记录是否 <780s，`runtime.elapsed_s` 记实际耗时。
- 单次运行不重试、不联网，正常 3 秒内完成；先写 partial 再分析，任何中断都留有合法结果。
- 解析上限：≤200 文件、24 sheet、4000 行/表、每表 10–12 个数值列；超出截断但不报错。
- 靠近 780 秒或遇异常立即 finalize（`except` 分支只打印，不改变退出码 0）。

## 10. 版本与维护

- 版本 `1.0.0`：SKILL.md frontmatter、`main.py` 的 `VERSION`、`runtime` 三处一致。
- 文件清单：`SKILL.md` + `scripts/main.py` + `scripts/analysis.py` + `references/`（3 份）+ `GITHUB_URL.txt`。
- 改阈值只改 `analysis.py` 顶部 `CFG`；改输出结构需同时改 `main()` 的 `res.update` 与 `references/input-formats.md`。
- 每次变更同步 `changes[]` 与本文件版本号；文档与提交版本不一致视为交付缺陷。

## 11. 边界（必须向用户说明）

1. 阈值（`|robust z| ≥ 3.5`、`CV < 30%`、`n ≥ 3`）是**数据驱动默认值**，未经方法验证文件校准。
2. 分组键/设计因子由脚本按语义自动选择，可能与真实分层不一致，需核对 `groups[].key`。
3. 原因为**候选**并附否定判据，未做排除实验前不得当作因果结论。
4. 图像、图谱与 PDF 不做数值读取，这类材料只登记为缺口。
