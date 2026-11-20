---
name: apparatus-technical-route-figure
description: 把实验材料（PDF/DOCX/Markdown/JSON/表格）中的装置单元、连接方向、工艺步骤、阶段划分与关键参数抽成"实体—连接—步骤—阶段—参数"结构化中间表示，再由同一布局导出分层可编辑 SVG 与原生矢量 PDF（内嵌 TrueType 字体、中文可提取），并为每个图元给出逐字 quote + locator、几何与导出自检。适用于实验装置图、工艺流程图、材料流向图、技术路线图。采用 init → (Agent 写 plan.json) → check → build 四步，带确定性兜底。
version: 4.0.0
---

# 实验装置与技术路线图 · Skill（v4 完整性优先 + 真实推导）

## 0. 最高优先级：完整性优先 + 真实推导（必读）

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、模板、占位文本直接当成品。`scripts/main.py` 的 `init/check/build` 只做输入发现、文本抽取、索引、渲染、导出和机械校验，不能替代对材料内容的科学理解和判断。

**先跑基线，再增量增强，绝不丢基线。** 进入任务后立即运行 `init` 生成全套基线骨架、partial `result.json` 和可落盘产物；后续所有 Agent 操作只能在此基线上增强，不得删除、清空或遗漏任何基线产物、契约字段或导出文件。若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent` 或 `agent_review`。

**真实解析，不猜不补。** 必须实际读取 `/input` 下给定材料（PDF/DOCX/MD/TXT/CSV/JSON/图片等），用真实抽取工具或 Agent 亲自读取原文，不得依据文件名、领域标签或题目提示补造设备、连接、数值、引用或分数。材料无法解析时如实降级并标注 `pending_human` / `limitations`，不得虚构。

**本题固定案例可能包含真实生物来源图表、实际图表数据和装置路线图；科学判断由方 LLM Judge 评估，不要只满足于字面 quote 或导出格式通过。** 最终交付必须体现：实体可追溯、连接方向正确、先后顺序成立、可编辑源文件真实可改、导出件真实可用、所有限制诚实标注。

---

## 1. 用途与边界

**做**：把材料里的设备、接口、步骤、阶段、参数变成一张别人能看懂、能改、能复核的图。判据三条：**每个图元可追溯到材料原文**、**连接方向与先后顺序成立**、**别人能复跑出同一张图**。

**不做**：数据分析与数值拟合；实验方案科学合理性判断；论文排版；**材料里没有的设备、管路、数值一律不补**。

**输出必须覆盖六类要素**：科学实体、空间关系、数据编码、图例标注、可编辑源文件、导出格式。任一要素缺失都不算完整交付。

---

## 2. 运行契约（目录、输入、输出、调用、退出码）

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`（可缺）、`/input/task.md`、`/input/**` 材料（PDF/DOCX/MD/TXT/CSV/JSON/图片） |
| 工作目录 | `/app/work`（`index.json`、`plan.json`、`check_report.json` 等中间件） |
| 最终产物 | `/app/output`：`figure.svg`、`figure.pdf`、`figure.png`、`content_map.json`、`result.json`；可选 `figure_preview_*.png` 或其他真实预览件 |
| 调用入口 | `python3 -B scripts/main.py <init\|check\|build> --input /input --work /app/work --out /app/output` |
| 帮助 | `python3 -B scripts/main.py --help`，退出码必须为 0 |
| 依赖 | 仅标准库；不联网；不依赖 CWD（脚本内部使用 `Path(__file__).resolve().parent`） |
| 退出码 | 恒 0；任何异常写入 `result.json.errors`，不因异常导致非零退出 |
| 断点 | 进入流程先写 partial `result.json`；每次重大步骤后更新；结束时无条件 finalize 覆盖 |

可选外部工具（缺失即降级，不报错）：`pdftotext`（PDF 取文本）、`pdftoppm` 或 `mutool`（PDF→PNG 预览）。**若题面指定 `pdf-text-tool`，则优先使用该工具抽取 PDF 文本，但仍需 Agent 亲自核对关键段落。**

---

## 3. 本题专属执行流程（编号步骤，每步含输入、动作、输出、失败分支）

### 步骤 1：盘点输入与契约，运行 `init` 生成基线
- **输入**：`/input/case.json`、`/input/task.md`、`/input/**` 材料。
- **动作**：
  1. 读取 `case.json`（若存在）。解析 `case_id` 和 `output_contract`（忽略大小写与 `_`、`-`）。若 `output_contract` 存在，记下其全部键名，后续必须原样保留。
  2. 扫描 `/input` 下所有材料文件，按扩展名 + 魔数识别（`%PDF` → PDF，`PK\x03\x04` → OOXML/zip，纯文本 → MD/TXT/CSV/JSON），**不看文件名猜内容**。
  3. 运行 `python3 -B scripts/main.py init --input /input --work /app/work --out /app/output`。
- **输出**：`/app/work/index.json`（材料清单与段落 locator 索引）、`/app/work/plan.json` 骨架、`/app/output/result.json`（partial）。
- **失败分支**：`case.json` 缺失或损坏 → 记 `case_json_invalid`，继续扫描材料；无任何材料且无 case → `status=input_error`，仍生成空画布与合法 result.json；`init` 抛异常 → 捕获写 `errors`，继续手动盘点。

### 步骤 2：真实解析材料内容
- **输入**：步骤 1 生成的材料清单、原文文件、`index.json`（如果有）。
- **动作**：
  1. 对每个文本可抽取的材料，用脚本或 `pdftotext` 抽取全文；`scripts/extract.py` 提供确定性抽取（词表、流向动词、编号）。
  2. **Agent 本人必须阅读关键段落**：摘要、方法、装置描述、步骤编号、图表图注、结果数据段落。优先读 `task.md` 中指定的重点材料。
  3. 将段落编号为 `S1, S2, ...`；多页 PDF 段落 locator 形如 `S1 p3 ¶12`。每个事实片段记录来源。
- **输出**：`/app/work/material_notes.md`（Agent 可用内部文件记录，但最终不强制输出）或直接写入 `plan.json` 的 `sources` 和 `quotes`。
- **失败分支**：纯图片/扫描件/无 `pdftotext` → 记 `material_no_text`，只登记来源，不猜内容；PDF 文本抽取失败 → 记 `pdf_no_text_tool`，继续处理其他材料；材料为空 → `status=insufficient_evidence`，生成空画布并 finalize。

### 步骤 3：构建/核对证据，Agent 亲自写 `plan.json`
- **输入**：步骤 2 的原文段落与 locator、`references/plan_schema.md`。
- **动作**：
  1. Agent 从材料中抽取**科学实体**（设备、部件、物料、产物、阶段、关键参数）、**连接关系**（管路、流向、信号、能量、顺序）、**步骤编号**（主序列、并行、回流、终止）、**阶段划分**。
  2. 每个实体、连接、步骤、参数写在 `/app/work/plan.json` 中，必须包含：
     - `quote`：材料中连续逐字片段（忽略空白差异）
     - `locator`：指向段落
     - `source`：来源文件
     - `resolution`：`exact` / `inferred` / `pending` / `unverified`
     - 参数必须逐字出现在自己的 `quote` 里
  3. 检查连接端点是否存在于节点集合；方向是否与材料描述一致。
  4. 对任何不确定、歧义或冲突，标 `pending: true`，不凭猜测补齐。
- **输出**：`/app/work/plan.json`，完整结构化中间表示。
- **失败分支**：材料不足无法抽取任何实体 → `status=insufficient_evidence`，plan 可为空，但继续生成空图基线；quote 找不到 → 该图元 `pending`；endpoint 未知 → 连接不画并记 exception。

### 步骤 4：生成/增强完整成品（运行 `check` 与 `build`）
- **输入**：`plan.json`、材料 sources。
- **动作**：
  1. 运行 `python3 -B scripts/main.py check --input /input --work /app/work --out /app/output`。检查 quote 命中、端点、参数、图例、图层等。
  2. 若 check 报错，Agent 返回材料修正 `plan.json`，不要改原文凑通过。
  3. 运行 `python3 -B scripts/main.py build --input /input --work /app/work --out /app/output`，生成 `/app/output/figure.svg`、`figure.pdf`、`figure.png`、`content_map.json`、最终 `result.json`。
  4. **Agent 必须审阅生成的 SVG/PDF 渲染预览**，确认图面实体、方向、编号、图例、参数与材料一致；不一致则修改 plan 后重新 build。
- **输出**：完整成品。`figure.svg` 分层可编辑；`figure.pdf` 原生矢量、内嵌 TrueType 字体、中文可提取；`figure.png` 真实渲染预览（若工具可用，否则 null + 降级记录）；`content_map.json` 逐图元证据。
- **失败分支**：无可用 TrueType 字体 → PDF 仍出矢量图形，ASCII 用 Helvetica，记降级；PNG 工具缺失 → `export_artifact.png=null`，SVG/PDF 仍有效；build 异常 → 捕获写 `errors`，保留已生成的临时产物，并 finalize。

### 步骤 5：自检 rubric 与完整性
- **输入**：步骤 4 成品、原 `output_contract` 字段、自检清单（见第 11 节）。
- **动作**：
  1. 逐项核对 `output_contract` 字段是否全部出现在 `result.json` 根级，键名不改。
  2. 核对磁盘文件：`figure.svg/pdf/png/content_map.json/result.json` 是否齐全，PDF 魔数 `%PDF-`，SVG 可解析且 `<text>` 可编辑。
  3. 核对每个关键图元有 quote/locator，连接方向与步骤顺序正确。
  4. 若任一失败，补齐或降级标注后重新 finalize。
- **输出**：更新后的 `result.json`（含 `self_check`、`agent_review`、`limitations`）。
- **失败分支**：若时间或预算不足，保留当前 base 产物，标记 `partial`，在 `limitations` 中说明缺失项，finalize。

### 步骤 6：回填 result.json 并 finalize
- **输入**：所有产物、自检结果、变更记录。
- **动作**：
  1. 确保 `result.json` 根级包含：`case_id`、原 `output_contract` 全部字段、`editable_source`、`export_artifact`、`content_map`、`compliance_checks`、`exceptions`、`pending_human`、`counts`、`status`、`errors`、`degradations`、`changes`、`uncertainty`、`runtime`、`sources`、`self_check`、`agent_review`、`limitations`。
  2. `status` 如实判定：无实体 → `insufficient_evidence`；有 pending / 推断连接 / 检查失败 / 走兜底 → `partial`；全部命中且检查通过才 `ok`；输入错误 → `input_error`。
  3. 运行脚本 finalize（若有）或手动写入最终 JSON；退出码 0。
- **输出**：最终合法 `result.json`。
- **失败分支**：finalize 本身异常 → 捕获并写入 `errors`，仍返回 0；若无法写入 JSON，至少输出最小合法 JSON `{"case_id":"unknown","status":"input_error"}`。

---

## 4. 预算策略（64 次模型请求 / 900 秒 / 单次响应 16384 tokens）

**目标**：在预算内先完成完整基线，再增量增强；优先保证高权重交付物（图面正确性、完整性、可核验性）。

| 阶段 | 必须/可选 | 预估请求次数 | 动作 |
|-|-|-|-|
| 盘点输入 + 运行 init | 必须 | 1-2 次 | 读取 case.json、扫描文件、生成基线和 partial result |
| 真实解析材料 | 必须 | 3-8 次 | 按优先级读关键段落：方法、装置描述、步骤、图注、结果数据；优先读 `task.md` 指定材料 |
| Agent 写 `plan.json` | 必须 | 1-2 次 | 从材料提取实体、连接、步骤、阶段、参数；不猜不补 |
| 运行 `check` + `build` | 必须 | 2 次 | 生成 SVG/PDF/PNG/content_map/result |
| 审阅渲染与修正 | 必须 | 2-5 次 | 对照材料检查图面，修改 plan 后重 build（如有必要） |
| 自检 rubric + 回填结果 | 必须 | 1-2 次 | 逐项核对字段、文件、证据；写 `self_check` |
| 增强（可选） | 可选 | 剩余预算内 | 逐条复核 quote、改进布局、补内容映射细节 |

**尽早落盘 partial**：`init` 运行后立即写 partial `result.json`；之后每次重大步骤后更新；当时间达到约 80%（720 秒）或请求达到约 50 次时，停止可选增强，finalize 当前产物，标记限制。

**可跳过的冗余工作**：重复全文解析（除非关键段落缺失）、重复生成相同 PNG、对非关键段落逐字核对、无意义循环改 plan。**不做**：为通过检查而修改 quote 或参数、伪造源文件、虚构评分。

---

## 5. 输入发现与真实解析（不假设键名，不按标签猜）

1. `case.json` 优先，取首个 `case*.json`；JSON 损坏不中断，记 `case_json_invalid` 并继续扫材料。
2. `case_id` / `output_contract` 语义识别（忽略大小写与 `_`、`-`）。`output_contract` 的每个键必须原样出现在 `result.json` 根级（缺值 `null`）。
3. 材料按**扩展名 + 魔