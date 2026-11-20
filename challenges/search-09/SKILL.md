---
name: literature-quality-appraisal
description: Evidence-anchored literature quality appraisal and search traceability. Reads actual /input files (PDF/DOCX/CSV/JSON/metadata), builds a traceable candidate set with query log, and returns a dimension -> judgment -> verbatim evidence + locator -> grade appraisal table. Use for literature quality evaluation, critical appraisal, risk-of-bias, reporting completeness, or review-ready evidence tables.
version: 1.1.0
license: MIT
---

# 文献研究质量评价与科研检索（literature-quality-appraisal）

**一句话用途**：对给定文献/检索案例产出一套可复核的「候选集 + 检索/筛选日志 + 质量评价表」，每条判断绑定“维度 → 条目 → 判定 → 原文逐字证据 + 定位 → 等级”。

## 最高优先级：Harness Agent 必须亲自推导，脚本只是工具

你是 Harness Agent。**最终交付物必须由你亲自读 `/input` 实际材料、推导、撰写/制作。** `scripts/appraise.py` 是基线工具，可以且应当先运行，以快速获得全套字段与文件骨架，但**绝不能把脚本骨架、空模板或未核验的流水线结果当作最终成品**。你必须：

1. 先运行脚本，得到全套**基线交付物**。
2. 实际打开/解析关键材料，逐条核验判断与原文证据。
3. 补足脚本未覆盖的议题、遗漏说明、冲突与人工确认入口。
4. 把所有核验结果、变更与不确定性如实写入 `result.json`。
5. 若时间或预算不足，先保存 honest partial，再增量增强；不得删除、清空或遗漏任何基线与契约字段。

---

## 1. 用途与边界

对给定科研问题与文献材料，产出：

1. **候选集与检索日志**：`candidates.csv` + `query_log.json`，每条候选带 `source_db`、`retrieved_at`、`query_id`、`provenance.source_file/json_pointer`。
2. **评价表**：`appraisal.csv`（行级：维度-条目-判定-逐字证据-页码-章节）+ `result.json.appraisals`（文档级：维度等级 + 汇总风险 + 置信度 + 分级轨迹）。
3. **`result.json`**：原样回填输入 `output_contract` 全部字段，并带 `case_id` / `status` / `sources` / `uncertainty` / `pending_human` / `errors` / `degradations` / `changes` / `runtime`。

**不做**：不替代同行评审、不做事实核验或临床/政策决策、不联网检索、不生成未见于输入材料的文献/DOI/数值/统计量、不把“未检出”说成“原文没有”。本 Skill 的等级阈值是本 Skill 自己的可复核判据，不是任何外部量表的官方评分。

---

## 2. 适用条件与触发

- 案例要求对给定论文做质量评价、批判性评价、偏倚风险、报告完整性、证据表、系统评价数据提取。
- 案例要求检索并筛选与科研问题相关的文献，输出可追溯候选集与筛选依据。
- 输入含 1 篇以上文献（PDF 全文 / 仅摘要 / 题录 JSON / 检索响应导出）。
- 反向条件：要求做文献综述写作、单纯题录补全、或要求上网找“最新进展”——超出边界，降级并如实说明。

---

## 3. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json` + `/input/task.md` + `/input/artifacts/**`（PDF/图片/表格/JSON/DOCX） |
| 工作目录 | `/app/work` |
| 输出 | `/app/output/`：`result.json`、`candidates.csv`、`appraisal.csv`、`query_log.json`、`appraisal_report.md` |
| 只读/只写 | 只读 `/input`；只写 `/app/output`（与 `/app/work`） |
| 退出码 | **恒 0**（含空输入、坏 JSON、全失败） |
| 断点 | 启动即写 partial `result.json`；任何分支结束前 finalize 覆盖 |
| 预算 | 64 模型请求 / 900 s / 16384 tokens / 单次响应；脚本是纯 CPU，不消耗模型请求 |
| 依赖 | 仅 Python 3 标准库；`pdftotext`/`pypdf`/`fitz` 若存在则优先，缺失自动降级到内置抽取器 |

**基线脚本调用**（脚本用 `Path(__file__).resolve().parent` 定位资源，不依赖 CWD）：

```bash
python3 -B /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output
python3 -B /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output --help
```

脚本会自动写盘 `/app/output` 下的基线文件。你应在脚本运行后检查文件完整性，再进行 Agent 级核验与增强。

---

## 4. 本题专属执行流程（必须逐步执行）

### 第 1 步：盘点输入与读取契约
- **输入**：`/input/case.json`、`/input/task.md`、`/input/artifacts/**`。
- **动作**：
  - 亲自读取 `/input/case.json`，确认 `case_id` 与 `output_contract` 全部字段及类型（若缺失，按 §隐藏鲁棒性降级）。
  - 扫描 `/input` 下所有文件，按**扩展名 + 魔数**识别实际材料（PDF `%PDF`、DOCX/ZIP、PNG/JPG、CSV、XLSX、JSON、JSONL、TXT/MD）。
  - 提取任务指令、organizer_supplied_scope、formal_inputs、artifact 清单。
- **输出**：在 `/app/work/plan.md` 记录：契约字段清单、artifact 清单、需要优先完成的高权重交付物、缺失材料。
- **失败分支**：`case.json` 缺失/非法 → 降级查找 `case*.json`、`task.md`、`*manifest*.json`，仍失败则写最小合法 `result.json`，退出 0。

### 第 2 步：先运行基线脚本，生成全套基线交付物
- **输入**：上述盘点结果。
- **动作**：运行 `python3 -B /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output`。
- **输出**：`/app/output` 下基线 `result.json`、`candidates.csv`、`appraisal.csv`、`query_log.json`、`appraisal_report.md`。
- **失败分支**：若脚本崩溃或未生成某些文件，作为 Agent 必须手工补齐所有 output_contract 字段和 result.json 标准键；把异常记入 `errors`，不得留空。

### 第 3 步：真实解析材料并核对证据
- **输入**：`/input/artifacts/**` 中实际 PDF/DOCX/CSV/JSON 等，以及脚本已抽取文本。
- **动作**：
  - 对每一份文献，实际解析（脚本内置 `pdftotext`/`pypdf`/`fitz` 三路探测；也可使用平台提供的 `pdf-text-tool`）。
  - 亲自阅读关键段落（方法与结果、局限性、偏倚相关内容）。
  - 对脚本产出的每一条 `appraisal_items`，核对 `evidence_quote` 是否为原文逐字、`locator_page`/`locator_section` 是否真实存在且对应、`judgment` 是否与证据一致。
  - 对 `not_reported`/`unappraisable` 条目，反向搜索探针词，确认确实缺证据；仅摘要或文本不可得则标 `unappraisable` 并记录 `abstain_reason`。
- **输出**：在 `result.json.agent_review` 中写入核验结果：每条 `verified` / `conflicting` / `pending_human`，以及你发现但脚本漏掉的维度或证据。
- **失败分支**：某文档全文不可得、扫描件无文本、图不可解析 → 该文档相关条目全部 `unappraisable`，`pending_human` 标 OCR/全文需求，不猜内容。

### 第 4 步：构建/核对候选集、检索日志与遗漏说明
- **输入**：题录 JSON/XML/CSV、检索响应导出、scope 约束。
- **动作**：
  - 核对每个 `candidate` 是否含有 `source_db`、`retrieved_at`、`query_id`、`provenance.source_file/json_pointer`。
  - 检查是否按 year/lang/topic 应用筛选；重复记录合并为一并保留多来源。
  - 记录元数据冲突（年份/期刊/作者不一致），不要静默取其一。
- **输出**：增强后的 `candidates.csv` 与 `query_log.json`，保证每条结果可被第三人复核；`coverage` 中写明遗漏项（如无全文、无 DOI、无检索权限）。
- **失败分支**：检索响应为 `error`/`status!=ok`/限流 → 保留该 query 记录 `status:"error"`，不重试不编造结果；空结果记录 `status:"empty"`。

### 第 5 步：Agent 产出完整成品（亲自撰写/改写）
- **输入**：基线文件 + 证据核验结果。
- **动作**：
  - 亲自撰写或改写 `appraisal_report.md` 的核心分析段落：对每篇文献给出“设计—证据—偏倚—报告完整性”的可读总结，引用原文句子和位置。
  - 将脚本生成的泛化总结替换为具体、可复核判断。
  - 保留 `appraisal.csv` 的行级证据定位，并在报告开头说明哪些行经过你本人核验。
- **输出**：最终 `/app/output` 下所有文件，内容完整、可直接被第三人复核。
- **失败分支**：时间/预算不足先落盘当前 best-effort partial，后续再增强；不删除已完成的基线产物。

### 第 6 步：自检 rubric 与完整性
- **输入**：`references/rubric.md`、`references/io_contract.md`、`references/playbook.md`、题面评分维度。
- **动作**：
  - 逐项对照 §Rubric 对照表检查。
  - 核对 `output_contract` 每个键是否已在 `result.json` 中存在且非默认空。
  - 核对磁盘产物是否齐全（`result.json`、`candidates.csv`、`appraisal.csv`、`query_log.json`、`appraisal_report.md`）。
  - 检查 `selfcheck` 三项断言是否满足。
- **输出**：更新 `result.json.selfcheck`，记录断言结果与未满足项；发现缺项立即补齐。
- **失败分支**：不可恢复的缺失 → 显式写入 `pending_human`，但 `result.json` 仍然合法。

### 第 7 步：回填 result.json 并最终化
- **输入**：所有中间产物。
- **动作**：
  - 确保 `result.json` 顶层 = 原 `output_contract` 全部字段（键名不改）+ 标准键。
  - 填写 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
  - 所有对基线的增强和核验写入 `changes`（例如 “agent_verified D2.3 quote, fixed locator_page from 3 to 4”）。
  - 最终原子写：先写 `tmp` 再 `os.replace`。
- **输出**：合法 `/app/output/result.json`，退出码 0。
- **失败分支**：任何异常也写到 `result.json` 后退出 0；若无法写 JSON，至少写最小合法 `{"case_id":null,"status":"input_error","errors":[...]}`。

---

## 5. 预算策略（64 模型请求 / 900 秒）

脚本运行不消耗模型请求，但你的推理、读取、核验、撰写会消耗。建议按以下优先级分配：

| 阶段 | 建议请求数 | 必须完成的工作 | 可跳过/缩减 |
|---|---|---|---|
| 盘点与脚本运行 | 2-4 | 读 `case.json`/`task.md`，确认 output_contract，运行脚本，检查产出文件 | 细读全部 artifact |
| 契约与完整性