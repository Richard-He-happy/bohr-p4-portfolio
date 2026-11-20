---
name: writing-01-academic-writing
description: 学术论文写作完整可核验 Skill：Harness Agent 必须亲自读取并解析科研材料、逐句核验证据、撰写可编辑章节稿并生成证据映射与差异报告；脚本 main.py 与 audit.py 只是辅助工具，不得将脚本骨架或模板输出直接当作最终成品。适用于从固定科研案例材料生成结构完整、事实可回溯、引用可复核的学术写作产物。
version: 6.0.0
---

# writing-01 学术论文写作（v6 完整可核验版）

## 0. 最高执行原则（必读）
- **脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把 `scripts/main.py` 的骨架、模板、占位文本或自动拼装结果直接当作成品；你必须审阅脚本输出，补全内容，核验事实与引用，最终产出一份真正可进入修改环节的章节稿。
- **完整交付优先于过度优化。** 先运行本 Skill 自带脚本得到全套基线交付物，再在此基础上由 Agent 亲自增强；不得删除、清空或遗漏任何基线产物与契约字段。
- **真实性优先。** 不编造数字、单位、样本量、p 值、作者、年份、期刊、DOI、图注或结论；材料不足、冲突、无法确认的内容必须显式标注 `pending_human` 或 `limitations`。
- **任何情况下都要产出合法 `/app/output/result.json`，退出码 0。** 即使材料缺失、损坏、解析失败或任务无法完成，也要诚实记录状态并给出可核验的交付物。

## 1. 用途与边界
本 Skill 面向学术论文写作任务：从给定科研材料（文本、PDF、DOCX、CSV、图片等）出发，完成指定的学术写作、修改、格式、引用、双语或结构化写作产物。核心目标是“写得实、引得对、全得起来、改得动”：
- 写得实：稿件中的数值、单位、样本量、图注和结论来自给定材料，不新增材料外事实。
- 引得对：每条引用真正支撑所在论断，作者、年份、期刊、DOI 准确可查。
- 全得起来：章节、图表、参考文献、声明字段齐备，缺失项显式标注。
- 改得动：成稿保留章节层级、图注编号和引用格式，作者可继续在 Word/Markdown 中修改并逐条复核。

边界：不生成材料外数值、文献条目或实验数据；不依赖互联网；不解析 PDF 二进制（但必须使用平台提供的 PDF 文本提取工具真实解析）；不调用外部程序（平台显式提供的工具除外）。

## 2. 运行时契约
- 输入：`/input/case.json` 与 `/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。**必须真实解析材料内容**，不得依据文件名或领域标签猜测/补造。
- 工作目录：`/app/work`；最终产物：`/app/output`。
- 必须有 `result.json`，包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。
- 可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。优先完成 rubric 权重最高的交付物，尽早落盘 honest partial，再增量改进。
- 诚实性：`status`、`sources`、`uncertainty`、`change records` 必须真实；不确定或材料不足要显式标注，不得编造数据、引用、分数。
- 资源限制：Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。

## 3. 输入发现与材料盘点
### 3.1 动作
1. 读取 `/input/case.json`（`utf-8-sig`；缺失则寻找 `case*.json`；仍无记录 `case_json_missing` 并按材料继续）。
2. 读取 `/input/task.md`，提取任务要求：目标体裁、受众、文体、格式约束、章节要求、字数范围、引用格式等。
3. 递归扫描 `/input` 下所有材料文件，按扩展名和魔数识别类型。
4. 为每个材料生成索引：`source_id`（简短唯一名）、路径、类型、字节大小、可读性状态。
5. 将索引写入 `/app/work/material_index.json`（手工记录即可，脚本 `init` 可辅助生成）。

### 3.2 失败分支
- `case_json_missing`：记录状态，从 `task.md` 和材料推断任务；`output_contract` 缺失字段置 `null`。
- 材料目录为空：记录 `no_material_files`，仍生成 `result.json`，`deliverable` 为“无法完成，缺少材料”，`status=input_error`。
- 某文件损坏或无法读取：记录具体错误（如 `file_error`），跳过该文件，继续处理其他材料。

## 4. 材料真实解析（核心步骤）
### 4.1 文本类材料
- 直接读取（`utf-8-sig`，失败尝试 `latin-1`/`cp1252`）。获取每行号。
- 参考文献条目（`[n]` 起始或含 `DOI`/`doi:`）整行保留，不拆句。

### 4.2 DOCX
- 使用平台可用工具或脚本提取 `word/document.xml` 文本。
- 若脚本 `python3 -B "$S/scripts/main.py" show` 可以提取文本，使用它；同时 Agent 必须亲自阅读提取出的文本，确保提取完整。
- 无法提取时记录 `docx_unparsed`，并尝试其他方法（如解压后读取 XML）。

### 4.3 PDF
- **优先使用平台提供的 `pdf-text-tool` 或系统已安装的 `pdftotext`/`PyMuPDF` 等工具真实提取全文。**
- 提取后检查文本是否为空或乱码；若仅提取到标题或乱码，记录 `pdf_text_extraction_poor`，并尝试其他提取工具。
- **不得仅识别 `%PDF` 头就跳过**；必须尝试真实解析。只有所有提取手段都失败时，才降级为 `pdf_unparsed`，并明确记录尝试过的工具和失败原因。
- 从 PDF 提取的文本保存到 `/app/work/extracted/` 下（如 `pdf_<source_id>.txt`），供后续证据定位使用。
- 若题目材料包含扫描版 PDF 且无文本层，可用 OCR 工具（如 `tesseract`）尝试识别；失败则标注 `ocr_failed`。

### 4.4 CSV / XLSX / PPTX / 图片
- CSV：直接读取。
- XLSX：使用 `openpyxl` 或脚本提取共享字符串与数值；若不可用，记录 `xlsx_unparsed`。
- PPTX：提取幻灯片文本；不可用则记录 `pptx_unparsed`。
- 图片：若图片包含关键数据（图表、图注），尝试 OCR（如 `tesseract`）或视觉理解（如果模型支持图像输入）；否则记录 `image_unavailable` 并标注“图注/数据缺失”，进入 `pending_human`。
- 所有二进制文件解析失败时记录 `binary_skipped`，并在 `result.json` 中说明缺口。

### 4.5 证据提取与定位符
- 定位符格式：`文件名:L行号`（对于提取文本使用提取文件的行号；原始二进制使用提取后的文本文件行号）。
- 对每个关键事实（含数字、单位、样本量、p 值、引用条目、图注）创建记录：`quote`（逐字原文）、`locator`、`source_id`。
- 脚本 `init`/`show` 可辅助生成基础证据句，但 Agent 必须亲自核验这些句子确实来自材料原文，并增补遗漏。

## 5. Agent 亲自产出完整成品
### 5.1 可编辑主产物 `manuscript.md`（或题目指定格式）
- 按任务要求撰写完整章节稿（通常包括摘要、引言、方法、结果、讨论、结论、参考文献、数据可得性声明等；若题目指定学科模板，按模板组织）。
- 每条事实性论断必须附引用 locator：`[^1]` 或 `（来源：文件:L行号）`，确保可逐条回溯。
- 正文只改变表达方式，不改变数值、单位、样本量、统计显著性、术语、引用编号；缺少的章节用占位标题并显式标注“待补充/材料未覆盖”。
- 保留章节层级（H2/H3 等）、图注编号和引用格式；可编辑性优先于视觉美观。

### 5.2 可编辑 Office/幻灯片/图形产物
- 如果 output_contract 要求 `.docx`、`.pptx` 或图形文件，必须生成该可编辑文件，并额外生成**真实渲染的 PDF/PNG 预览**放入 `/app/output`。
- 预览可用 LibreOffice 等平台提供的转换工具生成；若转换失败，记录 `preview_render_failed`，但可编辑文件仍需交付。

### 5.3 辅助审计资产（脚本可生成，Agent 必须核验）
- `golden_standard.json`：期望交付的金标准，每一章节锚句逐字引用自材料，事实/数字保全清单，引用条目。
- `diff_report.md`：实际稿件 vs 金标准逐项对照（达标/偏差/缺失 + 判定方法 + 复核步骤）。
- `version_history.md`：v0 骨架 → v1 成稿的修改记录（改了什么/为什么/如何回退），含 sha256。
- `run.log`：步骤、耗时、逐文件扫描、降级、异常、收尾状态。
- `self_check.json`：契约字段、证据覆盖率、数字/引用一致性、空输入与坏 JSON 探测、退出码、文件预算。

这些资产由脚本 `build`/`audit` 生成；**Agent 必须逐个打开检查，确认内容真实、无占位、无编造**，若发现脚本输出为占位或缺失，必须亲自补全。

## 6. 脚本命令与调用方式（保留原有效命令）
包内脚本位于 `/skills/weekly-skill/scripts/`，默认命令如下（在 `/app/work` 下执行）：

```bash
S=/skills/weekly-skill
python3 -B "$S/scripts/main.py" init       # 材料索引：id/类型/字节/可读性
python3 -B "$S/scripts/main.py" show       # 带 locator 的证据句
# （可选）写 /app/work/draft.json，schema 见 references/schema.md
python3 -B "$S/scripts/main.py" check      # 校验草稿：引用逐字命中？缺哪些章节？
python3 -B "$S/scripts/main.py" build      # 成稿 + 5 个资产 + result.json
python3 -B "$S/scripts/main.py" audit      # 只读复核：由 golden + manuscript 重算 diff_report
```

关键说明：
- `build` 首行会先写 partial `result.json`，然后增量补齐；Agent 必须在 `build` 之后进行人工核验和增强。
- 可选参数 `--no-audit`、`--draft`、`--input/--output/--work` 保留。
- 若脚本失败或不可用，Agent 必须手工完成等效动作，并记录 `script_failed` 或 `script_unavailable`。

## 7. 预算策略（64 次模型请求 / 900 秒 / 单响应 16384 tokens）
### 7.1 分配建议
- **步骤 1-2 输入盘点与材料解析**：约 8-12 次请求。优先处理与任务最相关的材料；PDF 提取最耗时，尽早开始。
- **步骤 3 证据索引构建**：约 6-10 次请求。聚焦关键数字、样本量、p 值、引用条目。
- **步骤 4 撰写成品**：约 15-25 次请求。按章节分块写，先写事实密集的章节（结果、方法），再写摘要/引言/讨论；确保内容完整后再优化语言。
- **步骤 5 自检与 result.json 回填**：约 8-12 次请求。逐项核对契约字段与 rubric。
- **预留 5-8 次请求处理异常或补充材料。**

### 7.2 必须做 / 可跳过
- **必须做**：真实解析材料；构建证据索引；撰写完整可编辑稿件；生成所有 output_contract 字段；生成 PDF/PNG 预览；自检并回填 result.json。
- **可跳过**：过度润色非核心段落；处理与任务无关的次要材料；重复运行审计脚本；生成可选的额外报告。
- **尽早落盘**：在完成材料解析后立即保存 `result.json`（partial）和初步 `manuscript.md`；每完成一个章节或一次核验后更新磁盘文件。即使超时，已有 partial 仍可评分。

## 8. 隐藏案例鲁棒性与异常处理
### 8.1 降级规则（任何情况下退出码 0）
| 情况 | 处置 | 记录 |
|-|-|-|
| PDF 无法提取文本 | 尝试多种工具；仍失败则用 OCR；仍不行则降级，使用其他文本材料 | `pdf_unparsed` / `ocr_failed` / `pdf_no_text` |
| 二进制/图片/xlsx/pptx 无法解析 | 尝试专用工具；失败则跳过，明确标注所缺信息 | `binary_unparsed` / `image_unavailable` / `xlsx_unparsed` |
| JSON 坏了 | 按纯文本行读取，提取可用字段；记录解析失败 | `json_parse_failed` |
| 单文件 >2MB | 读前 2MB，记录截断 | `file_truncated` |
| 读超时/异常 | 跳过该文件，记录错误 | `file_timeout` / `file_error` |
| 累计超限或输出不可写 | 截断扫描或回退到 work 目录 | `file_capped` / `output_dir_fallback` |
| `scripts/audit.py` 缺失或报错 | 主稿照常，缺的资产置 `unavailable` 并手工补最简版 | `audit_module_missing` / `audit_failed` |
| 空输入 | 记录 `case_json_missing`，以 `task.md` 为准，材料为空则 `status=input_error` | `no_material_files` |
| 契约字段缺失 | 缺失字段置 `null`，状态 `partial`，`change_log` 说明 | `output_contract_field_missing` |

### 8.2 材料冲突与人工确认
- 摘要/结果数值不一致、方法步骤可疑、文献信息不全、图注缺数值、材料未覆盖的章节：**不修改数字，不编造**，记入 `pending_human`（`item/reason/action`）与稿件附录，标注“待作者确认”。

## 9. Rubric 维度 → 交付要求 → 自证方式对照表
| 评分维度（分值） | 评分点 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果（40） | 任务完成度 15 | 产出一份结构完整、可进入修改环节的章节稿，不是提纲或素材堆叠 | `manuscript.md` 或指定的可编辑文件存在且字数/章节达标；`diff_report.md` 显示各节达标 |
| 实际效果（40） | 结果正确性 15 | 数值、单位、样本量、p 值、图注、作者、年份、期刊、DOI 与原始材料一致 | `evidence_map` 每条关键论断有 locator，`preserved_facts` 列出数字原句；`self_check.json` 显示一致性 |
| 实际效果（40） | 结果完整性 5 | 覆盖学科模板与任务要求的关键章节、图表、参考文献、声明字段 | `golden_standard.json` 章节六要素全覆盖；`diff_report.md` 无重大缺失 |
| 实际效果（40） | 结果可核验性 5 | 每条事实性论断可指回具体材料位置和文献条目，改动留痕 | `evidence_map` 提供 `claim_id/section/quote/source_id/locator/verified`；`change_log` 记录修改 |
| 使用增益（25） | 质量增益 15 | 相同材料下稿件可用程度提升 | `diff_report.md` 显示引用命中、章节完整、事实保全；`result.json` 记录 `coverage` 提升 |
| 使用增益（25） | 效率增益 5 | 从材料到可修改初稿时间下降、人工返工下降 | `run.log` 记录各步骤耗时；`result.json` 含 `runtime`；`change_log` 说明减少返工的机制 |
| 使用增益（25） | 增益可验证性 5 | 对照公平，材料、章节模板、工具权限一致 | `result.json` 包含 `sources` 列表与 `runtime` 信息；说明未改动材料与模板 |
| 创新增益（15） | 新增能力 5 | 材料、图表与正文三向对齐；论断与引用绑定；章节缺项检测 | `evidence_map` + `golden_standard.json` 证明三向对齐；`diff_report` 标注缺项 |
| 创新增益（15） | 方法改进 5 | 材料索引、证据映射表、章节约束、引用核验回路等带来实质改进 | `self_check.json` 记录核验回路方法与结果；`version_history` 说明改进 |
| 创新增益（15） | 创新证据 5 | 相对通用模型直接写作、模板填充有新增价值 | `diff_report` 中对比基线（脚本自动组装 vs Agent 亲自核验） |
| 可靠体验（10） | 调用与易用性 3 | Agent 能被正确触发，用户能按说明喂入 docx/pdf/csv/图片并拿到可编辑稿件 | SKILL.md 提供明确调用步骤；`README` 或本文件示例 |
| 可靠体验（10） | 运行稳定性 4 | 换学科、换篇幅、换材料完整度、重复运行稳定 | `run.log` 无致命错误；`self_check` 显示多场景测试；退出码 0 |
| 可靠体验（10） | 异常处理 3 | 材料缺图注、图表正文冲突、文献取不到全文、超长、格式不认识等识别与处置 | `pending_human` 列表、`degradations` 记录异常；`result.json` 状态真实 |
| 生态贡献（10） | 文档完整性 3 | SKILL.md、章节模板、输入材料格式、依赖、示例、适用范围与维护信息齐全 | 本文件各节完整；`references/schema.md` 提供字段说明 |
| 生态贡献（10） | 资源可复用性 4 | 题集、材料包、章节模板、评分表、一致性检查脚本可被他人直接复用 | `scripts/main.py`、`scripts/audit.py`、`references/schema.md` 均可复用 |
| 生态贡献（10） | 分享推广价值 3 | 沉淀可分享案例、题集、学科适配经验和真实应用价值 | 本文件“最小调用示例”与“维护说明”明确适用范围 |

## 10. 自检清单（提交前逐项检查）
1. `/app/output/result.json` 合法 JSON，包含 `case_id` 和原 `output_contract` 全部字段（键名不改，未知字段置 null）。
2. `manuscript.md`（或指定可编辑产物）存在且完整，章节数符合任务要求（通常 `grep -c '^## '` ≥ 5）。
3. 每条关键事实（数字、样本量、p 值、引用）在 `evidence_map` 中有 locator；`preserved_facts` 列出含数字原句。
4. 若产出 Office/幻灯片/图形，`/app/output` 下存在真实渲染的 PDF/PNG 预览。
5. `golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json` 全部存在且内容非空（脚本生成的可接受，但须经 Agent 检查）。
6. 无编造数据、引用、分数；不确定项已写入 `pending_human` 或 `limitations`。
7. `status` 字段真实（`complete`/`partial`/`input_error`），`sources` 列表与 `runtime` 信息准确。
8. 运行 `python3 -B scripts/main.py --help`（或类似命令）退出码 0（若脚本存在）。
9. 空输入/坏 JSON 测试：应退出码 0，`result.json` 合法，`self_check.json` 记录已测。
10. 最终退出码为 0，所有降级情况已记录在 `degradations`。

## 11. 最小调用示例（示例，非正式案例结果）
```bash
S=/skills/weekly-skill
python3 -B "$S/scripts/main.py" init
python3 -B "$S/scripts/main.py" show
# Agent 亲自阅读提取文本，撰写 /app/work/draft.json（可选）
python3 -B "$S/scripts/main.py" check
python3 -B "$S/scripts/main.py" build
python3 -B "$S/scripts/main.py" audit
# Agent 核验并增强 /app/output 下的所有产物
```
示意输出：
- `/app/output/manuscript.md`：完整章节稿，每条事实带 locator。
- `/app/output/golden_standard.json`：章节六要素 + 每节锚句 + 事实保全清单。
- `/app/output/diff_report.md`：实际 vs 金标准逐项对照。
- `/app/output/result.json`：契约回填 + 状态/证据/降级/运行信息。

## 12. 文件清单与维护
- `SKILL.md`（本文件）
- `scripts/main.py`（主流程：init/show/check/build/audit 子命令）
- `scripts/audit.py`（审计资产生成）
- `references/schema.md`（字段与定位规则）

版本 6.0.0；Python ≥3.8；无额外依赖。维护时请回归第 10 节清单 + 空目录/坏 JSON/带假数字草稿三种坏输入，均应退出码 0，且 `self_check.json` 对假数字报 `untraceable`、对未命中引用报 `quotes_rejected`。