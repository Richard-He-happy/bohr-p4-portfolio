---
name: experiment-result-anomaly-explainer
description: >-
  把实测实验数据（仪器 CSV/TSV、重复测量表、多批次/多通道工作表、多 sheet XLSX 工作簿）解释成五段可检查结论：
  趋势与拐点、异常点绑定到批次/通道、按证据强度与可检验性排序的原因候选、可执行复核清单、下一轮实验方案；
  并把案例给定的 output_contract 全字段回填进 result.json，同时产出 protocol.md、anomaly_table.csv、
  recheck_checklist.csv、risk_table.csv。Harness Agent 必须亲自读取材料、推导并撰写/制作成品；
  脚本只是基线工具和证据计算器，不得把脚本骨架直接当成品。适用于提供了实测读数、曲线、图谱、检测板或设备日志，
  并问“数据说明什么、哪个点异常、为什么异常、怎么复核、下一步做什么”的案例。
version: 2.0.0
license: MIT
---

# experiment-result-anomaly-explainer

把一份实测实验数据解释成五段可检查结论（趋势 / 异常点 / 可能原因 / 复核步骤 / 后续实验建议），并把案例给定的 `output_contract` 全字段回填进 `result.json`。全流程确定性、离线、只用 Python 标准库；但最终成品必须由 Harness Agent 亲自读材料、推导、撰写/制作。

## 0. 最高优先级：Agent 亲自完成，脚本只是工具

脚本 `scripts/main.py` 是基线工具，用于快速解析结构化表并生成 initial `result.json`、CSV 和 `protocol.md` 骨架。但最终交付物必须由你（Harness Agent）真实阅读 `/input` 下的原始材料，用模型推导、撰写/制作，不得把脚本输出或模板直接当成品。

- 先运行脚本产出**全套基线交付物**，保证契约字段齐全；后续校验与改写只能在基线上增强，不得删除、清空或遗漏任何基线字段。
- 对关键数值、异常定位、原因候选、复核步骤，必须亲自回指到材料的具体文件、sheet、表、行、列、引文；脚本给出的任何数字都要验证或修正。
- 最终结果必须体现“genuinely-derived”：在 `result.json` 中给出 `verified`、`pending_human`、`conflicts` 和 `changes[]`，记录 Agent 实际读过什么、改了什么。
- 先落盘 honest partial，再增量改进；完整交付优先。

## 1. 何时使用

满足任一条件即可加载：

- 输入含**实测读数**：仪器导出 CSV/TSV、重复测量表、多批次/多通道工作表、XLSX 多 sheet、设备日志；
- 用户问「这批数据说明了什么」「哪个点异常」「为什么异常」「怎么复核」「下一步做什么实验」；
- 案例带有 `output_contract`（需逐字段回填）或 `case_id`（需原样保留）。

不适用：只有实验设计需求、没有数据的「方案生成」题；纯文献综述；纯统计建模。

## 2. 调用方式与目录约定

```bash
python3 scripts/main.py --input <输入目录> --output <输出目录>
```

- 输入默认 `/input`，输出默认 `/app/output`；工作目录 `/app/work`（脚本会自动创建）。
- 也接受 `--input/--output`、`$INPUT_DIR/$OUTPUT_DIR`、`/bohr-workspace/input|output`、或 CWD 下的 `input/`。
- 脚本用 `Path(__file__).resolve().parent` 定位同目录 `analysis.py`，**与当前工作目录无关**。
- `--help` 打印用法，`--version` 打印版本。
- **退出码恒为 0**：异常只写入 `errors`/`degradations`/`pending_human`，不中断运行。
- 启动即写合法 partial `result.json`（`status: partial`），分析完成后无条件覆盖为 finalize 版本。
- Agent 可以多次运行脚本，但最终产物必须位于 `/app/output`，不得把 `/app/work` 中间文件当最终交付。

## 3. 专属执行流程（编号步骤）

### 步骤 1：盘点输入与契约

输入：`/input/case.json`、`/input/task.md`、题面规定的全部材料文件。

动作：

- 读取 `case.json` 与 `task.md`，提取 `case_id`、`topic`、`domain`、`goal`、`equipment`、`reagents`、`time/budget/personnel`、`output_contract`。
- 列出 `/input` 下所有材料文件及其类型（PDF/DOCX/CSV/XLSX/图片等），**不要跳过任何类型**。
- 建立 `output_contract` 字段清单，键名原样保留，作为最终回填依据。

输出：材料文件清单、契约字段清单、基础元数据。

失败分支：

- `case.json` 缺失或损坏：先扫描同级 `case*.json`；仍失败则继续分析材料，`case_id` 记 `UNKNOWN`，`status` 记 `partial` 或 `insufficient_evidence`，错误写入 `errors`。
- 材料清单为空：直接进入降级流程（第 9 节），仍产出合法 `result.json`，退出码 0。

### 步骤 2：真实解析所有可读材料

输入：步骤 1 清单。

动作：

- 对结构化表格（CSV/TSV/XLSX/XLSM）先运行主脚本，或直接调用 `analysis.py` 解析，提取数值行列。
- 对 PDF：调用环境可用文本提取工具（如 `pdf-text-tool` / `pdftotext` / 等效工具）读取全文；若 PDF 包含表格，提取文本后你亲自识别行列。**不得依据文件名或领域标签猜测内容**。
- 对 DOCX：用环境可用工具读取段落和表格。
- 对图片：若环境有 OCR 能力或题目要求曲线读数，用工具提取；否则明确标注 `not-read` 和 `pending_human`。
- 把解析结果写入 `/app/work/parsed_material.md`（证据页），附来源路径、页码、表名、行/列位置、逐字引用。

输出：`/app/work/parsed_material.md`、结构化表数据、PDF/DOCX 文本、图片描述、每个材料的来源定位。

失败分支：

- 单个文件解析失败：该文件在 `sources[].parsed = error`，其余文件继续。
- 关键材料（例如唯一实验数据）无法解析：`status` 降级为 `insufficient_evidence`，仍产出基线，并用 `pending_human` 说明缺什么。

### 步骤 3：构建与核对证据

输入：解析证据 + 脚本计算的趋势/异常候选。

动作：

- 用 `analysis.py` 读取结构化表，计算趋势指标（斜率、R²、拐点）、稳健 z、异常候选。
- 对脚本输出逐项核对：找到对应原始数据行/列，确认数值一致；检查单位、重复数、对照设置。
- 对 PDF/DOCX 中的方法、仪器参数、批次、阈值，提取为 `protocol.basis` 证据，并记录 `locator`/`quote`。
- 标记数据质量问题：重复不足、缺对照、读数封顶、单位不一致、结论冲突。

输出：证据核对表写入 `/app/work/evidence_map.md`，记录每项结论的证据路径。

失败分支：

- 脚本计算失败或无结构化表：使用你从 PDF/DOCX 中人工提取的数值，手动进行稳健统计或至少描述性统计；仍产出。
- 证据不足：在 `result.json` 中列 `limitations`，不要把推测当事实。

### 步骤 4：Agent 产出/增强完整成品

输入：核对后的证据、契约字段清单。

动作：

- 撰写五段主结果：`trend[]`、`anomalies[]`、`causes[]`、`recheck[]`、`next_experiment[]`（字段定义见第 5 节）。
- 编写 `protocol.md`（假设/变量/对照/步骤/参数/资源/判读标准/风险/确认项），基于真实材料；未给的仪器参数、试剂目录号、限度值一律不填，写 `pending_human`。
- 生成 `anomaly_table.csv`、`recheck_checklist.csv`、`risk_table.csv`。
- 回填 `output_contract` 中所有字段，键名不改，层级不改；未知字段保留 `null` 或 `[]`。
- 若 `output_contract` 要求可编辑 Office/幻灯片/图形产物：制作真实文档，并导出 PDF/PNG 预览到 `/app/output`。
- 写 `summary`、不确定性、`changes[]`。

输出：`/app/output/result.json` + 所有配套文件（`protocol.md`、CSV、预览如有）。

失败分支：

- 时间不够或模型请求接近上限：先确保 `result.json` 合法且所有 `output_contract` 字段存在（可为 `null`），再补配套；有 partial 就落盘。
- 任何一条撰写不了：写 `limitations` 和 `pending_human`，不编造。

### 步骤 5：自检 rubric 与契约完整性

输入：`/app/output` 成品。

动作：

- 逐项对照 `output_contract` 字段：`result.json` 中每个键都存在；磁盘文件与字段对应；缺失立即补齐或标 `null`。
- 按第 11 节自检清单逐项检查完整性和可核验性。
- 验证关键数字与来源一致；不一致修正结果和源 `locator`。
- 记录 `changes[]`，注明本次 Agent 修改内容。

输出：最终 `result.json` 状态 `finalize`（或 `partial` 带缺失项），无误。

失败分支：

- 发现缺项：回到步骤 4 补齐；若模型请求/时间不足，保留 honest partial 并列出缺失项，不伪装完成。

### 步骤 6：回填并最终落盘

输入：步骤 5 结果。

动作：

- 确保所有文件在 `/app/output`；`result.json` 含 `case_id`、`status`、`summary`、`sources[]`、`uncertainty[]`、`counts`、`runtime`、`changes[]` 和 `output_contract` 全字段。
- 可清理 `/app/work` 中间文件，但不要影响输出。
- 退出码 0。

输出：最终交付。

失败分支：任何异常都 `try/except` 后写合法 `result.json`，退出码 0。

## 4. 输入发现（按语义，不假设固定键名）

| 来源 | 处理 |
|---|---|
| `case.json` | 取 `case_id`、`topic`、`domain`、`goal`、`equipment`、`reagents`、`time/budget/personnel`、`output_contract`；键名归一化匹配（大小写/下划线/空格无关），也接受 `outputContract` |
| `task.md` | 读题面要求、评分维度和 Runtime contract，作为预算与降级的依据 |
| `*.csv/.tsv/.txt/.dat/.prn` | 按首行计数最多的分隔符切分（`,` `\t` `;` `\|`），无分隔符时按 2+ 空格或制表符切 |
| `*.xlsx/.xlsm` | 纯标准库解析 sharedStrings + worksheet XML，逐