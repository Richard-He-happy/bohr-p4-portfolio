---
name: section-anchored-paper-notes
description: 将真实科研论文转化为按论文自身章节对齐、字段齐备、每条关键结论可回链原文的结构化阅读笔记。Harness Agent 必须先运行包内脚本获取基线解析与候选证据，再亲自阅读解析文本，逐章撰写/核验论文卡片、章节笔记、图表锚点与 claims 表；脚本只是工具，最终交付物不得直接使用脚本自动生成的骨架或模板。适用场景：总结论文、构建结构化笔记、提取研究问题/数据/方法/结果/局限、核验结论与原文一致性。处理 PDF、DOCX、XLSX、CSV、HTML、JSON、TXT 等离线材料；对扫描件、加密、无标题、低文本或缺失材料诚实降级，不编造引用、数据或分数。
version: 1.1.0
---

# Section-Anchored Paper Notes (reading-09)

## 0. 最高优先级：完整性优先与真实推导

1. **脚本只是工具**。`scripts/main.py`、`scripts/doctext.py` 负责把材料解析为可用文本、候选章节、候选 claims 与基线 `result.json`。**最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作**，不能把脚本骨架、自动模板或候选输出直接当成品提交。
2. **先跑基线，再增强**。进入任务后，先把包内主脚本产出的一套完整基线落盘到 `/app/work/baseline`，包括 `result.json`、`notes.md`、`claims.csv`、`verify_report.json`。后续所有 Agent 改写只在该基线之上增量增强，**不得删除、清空或遗漏任何基线字段**。若不确定某些字段，保留原值并在 `changes[]` 中标注 `reviewed_by_agent`。
3. **诚实 partial 优先**。任何时候预算或时间紧张，优先保证合法 `result.json` 和主产物存在，并显式标注 `status: partial`、`limits[]` 与待人工接管项。
4. **禁止编造**。题目没有提供的事实、数字、引用、分数、对比结果，一律不写。材料不足写 `not_found_in_extracted_text`、`pending_human` 或 `limitations`，不能把“提取不到”改写成“原文未报告”。

---

## 1. 用途与边界

**做**：真实解析论文并按其自身标题切分章节；生成论文卡片 9 字段；逐章写证据笔记；提取图表/表格题注锚点；构建可核验 claims 表；每条关键结论带逐字引用、页码/章节/句级定位、条件与可读性等级。

**不做**：不补全原文未报告的数据、样本量、统计量、DOI、引用；不读取图形像素；不把“提取不到”写成“原文未报告”或反之；不使用通用摘要模板替代论文章节结构。

---

## 2. 运行契约

在 Skill 根目录 `/skills/weekly-skill` 下执行：

```bash
python3 scripts/main.py --input /input --output /app/work/baseline          # 生成基线
python3 scripts/main.py --check --input /input --output /app/work/baseline  # 复现性检查
python3 scripts/doctext.py --help                                            # 单文件抽取器帮助
```

输入：`/input/case.json` + `/input/task.md` + `/input/**` 材料。  
工作目录：`/app/work`。最终产物：`/app/output/`。  
仅使用标准库（Python ≥3.8），不联网，不依赖当前工作目录。  
**先写 partial `result.json`**，之后无条件 finalize；异常进入 `errors[]`、`degradations[]`、`pending_human[]`；**退出码恒 0**。

---

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；缺失则找 `case*.json`。坏 JSON 记录错误后继续。
2. `output_contract|outputContract|contract|result_contract` 任一命中即输出契约；`case_id|id|caseId` 任一命中即案例标识，原样透传。
3. 递归扫描 `/input/**`，跳过 `case.json`、`task.md`、空文件、隐藏文件；按扩展名 + 文件头（`%PDF`、`PK`）识别 PDF/DOCX/XLSX/CSV/TSV/HTML/JSON/TXT/MD/XML/TEX 与图片。
4. 主来源 = 可解析文本最长的文档，其余记 `secondary`；图片记 `role: image_not_pixel_read` 并加入 `pending_human[]`。
5. 材料缺失、无 case、无材料或仅图片时，记 `input_error` 与缺口清单，不构造内容。

---

## 4. 输出契约

最终 `result.json`（主结果）、`notes.md`（主产物）、`claims.csv`（证据表）、`verify_report.json`（自检）必须全部落在 `/app/output/`。

| 字段 | 内容 |
|---|---|
| `case_id` / `status` | 原样回填 / `ok`·`partial`·`insufficient_evidence`·`input_error` |
| `claims[]` | `claim_id, kind, quote(逐字), statement, source_id, location{page,page_end,section_id,section_title,section_kind,sentence_index,char_start,char_end,anchor,pointer}, conditions[], numbers[], readability, confidence, verified_quote_hit` |
| `paper_card` | 9 字段：`research_question, hypothesis, data_sample, methods, key_results, conclusions, limitations, funding_coi, availability` → `{value, claim_ids, status, readability, pages}` |
| `section_notes[]` | `{section_id, title, kind, pages, sentences, claim_ids, readability:"inferred"}` |
| `figures[]` | 图表题注锚点 `{label, caption, page, anchor, elements:"not_parsed"}` |
| `gaps[]` | 无证据字段（`not_found_in_extracted_text`，≠原文未报告） |
| `uncertainty[]` / `pending_human[]` | 不确定项 / 人工动作，均带 `pointer` |
| `errors[]` / `degradations[]` / `changes[]` | 异常、降级、运行轨迹 |
| `coverage` | 章节/证据/命中率/卡片覆盖/图表/缺口计数 + `page_map`（每页 `char_start`、字符数） |
| `sources[]` | `{source_id, name, path, kind, pages, chars, quality, role}` |
| `output_contract_echo` | 输入契约完整键结构回填：未知键保留，缺值 `null`/`[]`，按语义填入真实值 |
| `runtime` | 版本、Python、起始时间、耗时、实际模型请求（不要编造为 0，须真实记录） |

契约回填：先按输入结构生成骨架，再依据 `references/rules.json` 的 `syn` 映射写入 `claims/sources/uncertainty/...` 真实值；键名不改不删。

---

## 5. 本题专属执行流程（编号步骤）

### 步骤 1：盘点输入与预算
- **输入**：`/input/case.json`、`/input/task.md`、`/input/**`。
- **动作**：读取 `case.json` 与 `task.md`；识别 `case_id`、`output_contract` 全部字段；扫描材料清单；确认 64 次模型请求、900 秒、单次响应 16384 tokens 的预算。
- **输出**：在 `/app/work/inventory.json` 中记录 case_id、材料路径、契约字段清单、主材料类型。
- **失败分支**：缺 `case.json` 或材料时，记 `input_error` 并继续，不中断最终产出。

### 步骤 2：真实解析材料并生成基线
- **输入**：`/app/work/inventory.json` 中的材料路径。
- **动作**：
  1. 运行 `python3 scripts/main.py --input /input --output /app/work/baseline`，得到基线 `result.json`、`notes.md`、`claims.csv`、`verify_report.json`。
  2. 若主材料为 PDF/DOCX 等，可用 `pdf-text-tool` 或包内 `scripts/doctext.py` 提取全文到 `/app/work/extracted/<source_id>.txt`；若提取失败，保留 `degradations[]`。
  3. 复制基线文件到 `/app/output/` 作为初始 honest partial，并在 `status` 中标注 `partial`，`changes[]` 注明 `baseline_generated`。
- **失败分支**：解析失败、加密、扫描件等，按 §7 降级，仍写入合法 `result.json`。

### 步骤 3：阅读任务要求与评分权重
- **输入**：`/input/task.md`、`/app/work/baseline/result.json`。
- **动作**：阅读题目对材料结构、笔记类型、交付物的具体命令；识别 rubric 中权重最高的任务完成度（40 分）和使用增益（25 分）相关要求；确定哪些字段必须重点补强。
- **输出**：在 `/app/work/plan.md` 中列出优先顺序：主产物完整性 > 逐条证据正确性 > 章节对齐与可核验性 > 创新字段 > 异常说明。
- **失败分支**：若 `task.md` 缺要求，默认按本文件 §4 输出契约执行。

### 步骤 4：逐章阅读抽取文本并亲自撰写章节笔记
- **输入**：`/app/work/extracted/` 中的解析文本或脚本基线中的逐字 `quote` 与 `page_map`。
- **动作**：按脚本切分的章节顺序，逐章阅读原文文本；每章撰写 `purpose`、`methods`、`results`、`conclusions`、`limitations` 等小节，并标注 `section_id`、页码、句级锚点。**不得直接复制脚本 `notes.md` 作为最终内容**，必须由 Agent 在阅读后重写/确认。
- **输出**：临时章节笔记写入 `/app/work/section_notes/`，每个章节一个文件；最终合并进 `/app/output/notes.md`。
- **失败分支**：某章无标题或文本低质量，退化单章 `S1 Full text`，加 `headings_not_detected` 与 `uncertainty[]`。

### 步骤 5：抽取论文卡片、图表锚点与核验 claims
- **输入**：抽取文本、基线 `result.json` 中的候选 claims。
- **动作**：
  1. 从章节笔记中选取最高置信度逐字引用，填写 `paper_card` 9 字段；无证据字段写 `not_found_in_extracted_text`。
  2. 从题注中提取 `figures[]` 的 `label/caption/page/anchor`；不读取图表内部像素。
  3. 逐条核验 claims 的 `quote` 是否能在原文定位到；能定位则 `verified_quote_hit=true`，不能则进 `pending_human[]`。
  4. 检查数字、单位、条件是否与原文一致；只保留原文字符串，不改写、不换算。
- **输出**：更新 `/app/output/result.json` 中的 `paper_card`、`figures[]`、`claims[]`，并写 `coverage`。
- **失败分支**：有冲突时保留所有冲突 claims，选最高 `confidence` 作为 `value`，其余留在 `claim_ids` 并在 `notes.md` 列出。

### 步骤 6：整理最终 notes.md 与 claims.csv
- **输入**：`/app/work/section_notes/`、更新后的 `claims[]`。
- **动作**：按论文原有章节顺序生成最终 `notes.md`，包含运行摘要、论文卡片表、章节地图、逐章笔记、图表锚点、缺口与人工动作。`claims.csv` 与最终 `claims[]` 对齐。
- **输出**：覆盖 `/app/output/notes.md` 与 `/app/output/claims.csv`。
- **失败分支**：时间不足时，保留当前 partial 的 `notes.md` 并标注 `pending_review`，但不得缺失主结果。

### 步骤 7：回填 result.json 所有 output_contract 字段
- **输入**：`/input/case.json` 中的 `output_contract`、更新后的所有真实结果。
- **动作**：逐一核对输出契约键，缺值填 `null`/`[]`；把最终 `claims[]`、`sources[]`、`uncertainty[]`、`limited`、`changes[]` 等映射回 `output_contract_echo`。`case_id` 原样回填。`status` 取 `ok` 或 `partial` 等真实状态。
- **输出**：最终 `/app/output/result.json`，包含全部契约字段。
- **失败分支**：契约缺失时，按本文件 §4 字段生成合法 result，并注明 `contract_missing`。

### 步骤 8：渲染预览与最终自检
- **输入**：`/app/output/` 当前产物。
- **动作**：若产出可编辑 Office/幻灯片/图形，先生成真实 PDF/PNG 预览放入 `/app/output`。运行 `python3 scripts/main.py --check --input /input --output /app/output`，检查可复现性与 quote 命中率。运行自检清单 §9。
- **输出**：`verify_report.json`，其中 `pass` 应为 true；若 false，修复对应项或诚实降级。
- **失败分支**：无法修复时，在 `errors[]`、`degradations[]` 写清原因和人工接管位置。

### 步骤 9：收尾与退出码 0
- **动作**：确认 `/app/output/result.json`、`notes.md`、`claims.csv`、`verify_report.json` 存在且合法；确认 `status` 真实；确认退出码 0。写 `changes[]` 记录所有嵌改。

---

## 6. 预算策略（64 次模型请求 / 900 秒）

| 步骤 | 建议请求数 | 说明 |
|---|---|---|
| 盘点输入 + 任务要求 | 2-3 | 读 case、task、扫描材料清单，识别契约 |
| 运行脚本/提取工具 | 0 | 脚本运行不消耗模型请求，但有时间成本 |
| 逐章阅读与撰写 | 15-25 | 每章 1-2 次读取/撰写；优先高信息量章节 |
| 论文卡片 + 图表 + claims 核验 | 6-10 | 对关键数字、方法、结果逐条回原文核验 |
| 整合 notes.md + result.json | 4-6 | 合并、回填、自检 |
| 自检修复 | 2-4 | 查漏补缺，确认契约字段 |
| 合计 | 约 30-50 | 保留 64 以内的安全余量 |

**必须优先**：`result.json` 合法落盘 > `notes.md` 主产物 > `claims.csv` 证据表 > `verify_report.json` 自检。  
**可跳过**：若时间不足，可跳过低权重美化；不得跳过契约字段回填与诚实状态标注。  
**尽早 partial**：步骤 2 完成后立即复制基线到 `/app/output`；每完成一章更新一次 `result.json` 和 `notes.md`。

---

## 7. 隐藏案例鲁棒性

| 情况 | 检测 | 处置 | 状态 |
|---|---|---|---|
| 扫描/图片 PDF | 字符少、质量 `low_text`/`garbled` | 保留空页文本，写 `degradations[]`，建议 OCR；不编造内容 | `partial`/`insufficient_evidence` |
| 加密 PDF | `/Encrypt` | `PdfError`，跳过该文件，记 `errors[]` | `partial` |
| 双栏错序 | 文本量正常但句序异常 | 不猜测重排，`uncertainty[]` 提示人工核对 | `partial` |
| 无标题 | `headings_found < 2` | 退化单章 `S1 Full text`，加 `headings_not_detected` | `partial` |
| 图表为主 | 页字符 <120 | `uncertainty[]` 列低文本页；图元素不读取 | 不影响全局 |
| 材料缺失/坏 JSON | 无 case、无材料、JSON 解析失败 | 记 `input_error`、缺口清单，继续生成合法空 result | `input_error` |
| 格式不支持 | 未识别扩展名/文件头 | 标记 `unsupported_format`，不强行解析 | `partial` |
| 超时/预算耗尽 | 时间将尽 | 保留当前 partial，写 `limits[]`，退出码 0 | `partial` |
| 契约缺失 | `output_contract` 不存在 | 按本文件 §4 生成默认 result，注明 `contract_missing` | `partial` |

任何情况下都要产出合法 `result.json`（含 `case_id` 若可得、`status`、`errors[]`、`degradations[]`、`pending_human[]`），退出码 0。

---

## 8. Rubric 维度 → 交付要求 → 自证方式

| 评分维度/分值 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果 40：任务完成度 15 | 按论文自身章节对齐的逐章笔记，非通篇摘要；覆盖研究问题、数据、方法、结果、结论、局限 | `section_notes[]` 与 `notes.md` 中逐章标注 `section_id`、标题、