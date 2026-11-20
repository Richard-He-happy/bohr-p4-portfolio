---
name: sci-mindmap-builder
description: >-
  从科研材料真实解析出发，由 Harness Agent 亲自提炼、核验并制作的可编辑、可追溯思维导图 Skill。输出 mindmap.svg、mindmap.json、content_map、PNG 预览与完整 result.json，保留逐字证据、变更记录、不确定项与自检资产。
version: 1.2.0
---

# 材料 → 可核验思维导图（sci-mindmap-builder）

## 0. 最高优先级声明

**一句话用途**：把 `/input` 中的科研材料真实解析后，由 Agent 亲自提炼中心主题、层级节点、证据定位与跨分支关系，产出可编辑、可复核的思维导图（SVG + JSON + PNG + content_map + result.json）。

**脚本只是工具，不是成品**：`scripts/main.py`、`scripts/verify.py`、`scripts/report.py` 负责索引、逐字证据校验、结构校验、渲染、兜底成稿与核验资产生成。**最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写与制作**。禁止把脚本生成的骨架、兜底导图或模板直接当最终成品；只能把它们作为完整性基线和辅助校验工具，最终工作稿必须体现 Agent 对材料的真实理解、逐节点证据核验与必要的人工确认。

**完整性优先（v1.2 混合策略，最高优先级）**：
1. 进入任务后先运行脚本产出**全套基线交付物**，落盘所有题面要求文件与 `result.json` 字段。
2. 保留全部基线产物；后续 Agent 的校验与改写只能在其基础上增强，不得删除、清空或遗漏任何文件与字段。
3. 提交前逐项核对「`output_contract` 字段 list × 磁盘产物 × `result.json` 键」三者一一对应。
4. 最终交付必须体现 Agent 的真实核验与增强，不能只交基线；若时间不足，保留基线并诚实标为 `partial`，列出 limitations。

## 1. 用途与边界

**做**：把论文/材料整理成分层思维导图——中心主题、3–6 个主分支、分支下的要点节点；节点带材料 locator 与逐字 quote；输出可编辑 SVG、结构 JSON、PNG 预览、来源映射与 `result.json`。适用于论文结构梳理、研究方案、概念关系、会议纪要等“材料 → 导图”任务。

**不做**：不新增材料里没有的事实、数值、文献或结论；不做 OCR（图片材料只登记存在性，不臆造内容）；不把“看起来像结论”的句子升格为结论——无 quote 支撑的节点必须标 `status: "inference"` 并列入 `pending_human`。

## 2. 运行时契约与目录

- 输入：`/input/case.json`、`/input/task.md` 与 `/input/**` 材料（PDF/DOCX/MD/TXT/JSON/CSV/图片等）。
- 工作区：`/app/work`，存放 `index.json`、`mindmap.json` 工作稿、`check.json` 等中间文件。
- 产物目录：`/app/output`，必须包含：
  - 可编辑思维导图：`mindmap.svg`
  - 结构化数据：`mindmap.json`
  - 内容映射：`content_map.json`
  - 预览：`mindmap.png`（若 SVG 渲染器缺失则保留 SVG 并在 result.json 中说明）
  - 总结果：`result.json`
  - 五项可核验资产：`golden_standard.json`、`diff_report.md`、`version_history.md`、`self_check.json`、`run.log`
- 命令：`python3 /skills/weekly-skill/scripts/main.py {init|show|check|build}`，退出码恒为 0。
  - `init` / `build` 可加 `--no-probe` 跳过空输入/坏输入子进程探针，赶时间时用；`self_check.json` 会显式标注未探测。
- 依赖：仅 Python 3 标准库；`pdftotext`、`rsvg-convert`、`convert` 存在则优先使用，缺失即降级并记录。

## 3. 输入盘点与真实解析

### 3.1 输入盘点
`init` 会递归扫描 `/input`，按扩展名 + 魔数双识别（PDF `%PDF`、PNG `\x89PNG`、ZIP 系按 `word/document.xml` 等内部路径判定 DOCX/XLSX/PPTX），读取 JSON 用 `utf-8-sig` 防 BOM。键名按语义匹配：`case_id`、`output_contract`、`task_instruction`、`workorder` 等。任何单一材料解析失败只降级该材料，其余继续。

### 3.2 真实解析材料内容
**必须真实解析材料内容**，不得依据文件名或领域标签猜测/补造内容。PDF 使用 `pdftotext` 或脚本内置正则解流提取文本；DOCX 解包读取 `word/document.xml`；CSV/JSON 读取结构化内容；Markdown/文本读取原文；图片材料无文本层则仅登记存在性并标注“未 OCR”。Agent 必须使用 `show` 命令阅读实际提取出的文本片段并引用原文。

**禁止**：跳过解析、只读摘要或文件名、用领域标签补造节点内容。如果材料没有预提取 answer layer，也必须读原始文件文本。

## 4. 输出契约与 result.json

`result.json` 必须：
1. **原样回填 `output_contract` 的全部字段**（键名不改，缺值用 `null` / `[]`），并包含 `case_id`。
2. 附加字段：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`coverage`。
3. 契约字段按语义映射：
   - `deliverable` → 产物摘要：列出 `mindmap.svg`、`mindmap.json`、`content_map.json`、`mindmap.png` 等相对路径、大小、格式、可编辑性。
   - `preserved_facts` → 数字、术语、引用、关键论断的事实表，带来源与验证状态。
   - `evidence_map` → 节点到材料来源（material、locator、quote、status）的映射。
   - `change_log` → 修改动作、原因、人工确认项和未解决问题。
   - 若契约出现 `mindmap` / `structure` / `content_map` 等字段，映射为相应结构摘要。
4. v1.2 追加四个核验资产字段（不动原契约）：`golden_standard`、`diff_report`、`version_history`、`self_check`，各含 `path` 与可判读摘要计数。**契约字段优先级更高**：若契约里出现同名键，保留契约回填值，新字段降级为 `self_check.json` 里的说明。

## 5. 本题专属执行流程

### 步骤 0：完整性基线（最高优先级，不跳过）
**输入**：`/input/case.json`、`/input/task.md`、材料文件。
**动作**：
1. 执行 `python3 /skills/weekly-skill/scripts/main.py init` 生成 `/app/work/mindmap.json` 骨架与 partial `result.json`。
2. 如果当前工作稿可 build，立即执行 `python3 /skills/weekly-skill/scripts/main.py build` 产出全套基线文件，包括 SVG/JSON/PNG/result.json 与核验资产。这是为了尽早落盘 honest partial。
3. 保留全套基线产物，后续增强只能在基线上覆盖/增加。
**输出**：`/app/output` 全套基线文件 + `/app/work` 工作稿与索引。
**失败分支**：若 `init` 或 `build` 失败，记录 `errors` / `degradations`，继续按步骤 1–2 收集材料；稍后重试。不得返回非 0 或空 result。

### 步骤 1：盘点输入
**输入**：`/input/case.json`、`/input/task.md`。
**动作**：
- 读取任务说明，明确目标受众、输出格式、评分重点、是否要求学术写作准备或导图结构。
- 读取 `output_contract`，确认全部字段名。
- 运行 `python3 /skills/weekly-skill/scripts/main.py init` 或查看已有索引，列出材料 id、类型、字节数、单元数、首段。
**输出**：任务摘要、契约字段清单、材料清单（M1、M2…）。
**失败分支**：`case.json` 缺失或坏 JSON：仍跑 `init`，从 `task.md` 提取可用的任务信息与空契约；在 `errors` / `degradations` 如实记录。

### 步骤 2：用工具真实解析