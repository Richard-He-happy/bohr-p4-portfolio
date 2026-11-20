---
name: literature-data-cleaner
description: Clean and standardize a batch of literature extraction records into a statistically usable table, with a rule-numbered change log, a pending-human review list and a traceable duplicate/conflict report. The Skill instructs the Harness Agent to genuinely read the original materials, run the included baseline scripts as tools, verify and enhance their outputs, and then write the final deliverables. Use when the task supplies paper-extracted rows (values, units, material/indicator names, condition columns) plus unit/number/region rules or a target field dictionary, and asks for unified field names, unit conversion with formulas, synonym normalization, missing/outlier handling, duplicate handling and source traceability. Trigger phrases include "文献数据清洗", "抽取记录标准化", "单位换算并保留原值", "去重并给变更记录", "clean extracted literature values into a table".
version: 2.0.0
---

# 文献数据清洗与标准化（literature-data-cleaner）

## 0. 最高优先级声明（Agent 必读）

**本包内的脚本（scripts/main.py、scripts/clean_core.py）只是工具和基线生成器，不是最终成品。最终交付物必须由你（Harness Agent）亲自读取输入材料、运行脚本、抽样核验、撰写/修正关键结论后产出。禁止把脚本骨架、模板或未核验的基线直接当作成品提交。** 若预算或材料不足，优先保留完整且诚实的 partial 交付，而不是残缺、伪造或经不起复核的“自创”结果。

一句话用途：把真实文献抽取记录端到端清洗成可统计宽表，并交付规则编号的变更记录、待人工确认清单与来源可追溯的去重/冲突报告。

## 1. 用途与边界

**做什么**：把一批真实文献抽取记录端到端清洗成可统计的宽表，并同时交出**行级变更记录**、**待人工确认清单**、**去重/冲突报告**、**规则库**、**字段映射**与**单位表**。每个改动值都带 `rule_id` 与 `formula`，可沿 `row_id → original_value → rule_id → formula` 回到输入行与原始文献位置。

**不做什么**：
- 不做领域判断式纠错。单位能算但科学上矛盾时（同来源同条件两个差异很大的值），标 `source_conflict` 并保留原值，**不用换算抹平**。
- 不猜单位。`a.u.`、`arb. units`、无法解析的 token、缺失单位一律不换算，交人工。
- 不把缺失写成 0，不把区间压成中值，不丢掉 `±` 误差。
- 不合并不同来源或不同条件的行；条件列（温度、时间、pH…）不做单位换算，只原样保留在 `condition_summary`。

## 2. 运行时契约与脚本调用

工作目录：`/app/work`（Agent 的实际工作目录）；最终产物必须落在 `/app/output`；输入在 `/input`。脚本不依赖 CWD，使用 `Path(__file__).resolve().parent` 定位资源。

```
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --input /input --output /app/output --determinism   # 两次运行逐字节比对
```

- 输入默认 `/input`（不存在则用包上级的 `input/`），输出默认 `/app/output`（无 `/app` 时用包上级的 `output/`）。
- 只使用 Python 标准库，不联网；脚本是基线工具，Agent 必须在基线之上进行核验与增强。
- 退出码恒为 0。任何异常写入 `result.json.errors`，流程继续或降级，绝不以非零码结束。
- `result.json` 在流程最开始先写一份 partial（`case_id` + 空骨架），结束时无条件 finalize 覆盖。
- 若 `output_contract` 要求可编辑 Office/幻灯片/图形产物，Agent 必须额外生成真实渲染的 PDF/PNG 预览，并记录 `preview_path`；若只要求 CSV/JSON 报告，则无需额外预览。

## 3. 输入盘点与真实解析

1. 读 `/input/case.json`（或任意含 `case_id`/`output_contract` 的 JSON）：保留 `case_id`、`output_contract` 原样；`task_instruction`、`organizer_*`、`formal_inputs`、`runtime_files` 只记录出现情况，不臆造。
2. 读 `/input/task.md`：提取题面要求、评分重点和 Runtime contract 中与本次输入有关的约束。
3. 递归扫描 `/input/**`，按扩展名与内容分类：
   - `.csv` → 抽取记录；
   - `.json` 含 `rule_id` 或文件名含 rule → 规则文件；
   - `.json` 含 `fields`/schema/dictionary → 目标 schema 或字段字典；
   - 其余 `.json` → 抽取记录（列表，或 `records/rows/data/items/measurements/…` 下一层列表，逐层向下找第一个「dict 列表」）；
   - `.pdf` → 科研材料原文；
   - `.docx`/`.doc` → 科研材料原文；
   - `.png`/`.jpg`/`.tiff` → 图片材料，可能需要 OCR 或视觉读取。
4. 对 PDF/DOCX/图片必须使用平台预装解析工具（例如 pdf-text-tool、pdftotext、python-docx、OCR/图像描述工具）真实提取内容，保存到 `/app/work/evidence/`；不得依据文件名或领域标签猜测内容。若某个文件无法解析，记录 `degradations` 并继续。
5. 抽取记录里按角色同义词识别列：`row_id`、`source_document_id`、`source_locator`、`value`、`unit`、`indicator`、`material`；其余非注释列作为条件列。
6. 明确列缺口：找不到记录表 → `status=insufficient_evidence` 且 `degradations` 写明；找不到 `case.json` → `degradations` 记一条，`output_contract` 视为空。

## 4. 本题专属执行流程（编号步骤）

### 步骤 0：预算初始化与 early partial 落盘
- **输入**：无。
- **动作**：在 `/app/work` 创建进度文件，尽最大努力先写入最小合法 `/app/output/result.json`（`case_id` 未知可先填 `null`，`output_contract` 字段空骨架，`status=partial`，`errors=[]`）。
- **输出**：`/app/output/result.json` 初版 partial。
- **失败分支**：若无法立即写出，继续后续步骤；必须在最终退出前补齐。

### 步骤 1：盘点输入并读取任务要求
- **输入**：`/input/case.json`、`/input/task.md`、`/input/**`。
- **动作**：读取 case.json 获取 `case_id` 与 `output_contract`；阅读 task.md 提取要求与评分关注点；扫描材料清单。
- **输出**：`/app/work/input_inventory.json` 草稿（记录文件路径、角色、可用性）。
- **失败分支**：`case.json` 缺失或损坏 → 降级，`output_contract` 视为空，记录 `degradations`；`task.md` 缺失 → 记录 `limitations`，继续执行。

### 步骤 2：真实解析所有材料
- **输入**：`/input/**` 材料文件。
- **动作**：调用可用解析工具真实读取 PDF/DOCX/CSV/JSON/图片，提取文字、表格和关键数字；将提取结果写入 `/app/work/evidence/`。对每个材料记录解析摘要（页数、表格数、行数、是否成功）。
- **输出**：`/app/work/evidence/` 下的真实提取文本/数据，以及解析状态记录。
- **失败分支**：某个 PDF/DOCX/图片无法解析（损坏/加密/格式不支持）→