---
name: scifig-editable
description: 将案例材料（task.md、workorder、prose/PDF/CSV/数据源、既有图稿）真实解析为可溯源、分层可编辑的科研示意图或机制/流程/数据图，交付真实 PNG/PDF 预览与完整 result.json。脚本 main.py/render.py 只是工具，最终图稿、推导与核验必须由 Harness Agent 亲自完成。
version: 1.1.0
license: MIT
---

# scifig-editable

## 1. 用途与执行原则

**做什么**：把“来源材料 → 实体—关系中间表示 → 分层可编辑 SVG → 真实 PNG/PDF → 可核验结果”这条链路走完。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作**。  
`scripts/main.py` 与 `scripts/render.py` 生成的骨架、模板、默认 `figure_model.json` 和 `result.json` 只是基线。你必须在此基础上：

- 亲自读取并理解 `case.json`、`task.md`、workorder 与真实材料内容；
- 亲自核对实体、关系方向、层级、数值、单位与来源引用是否一致；
- 亲自补全、修正或确认图面元素与 `content_map` 的逐条证据；
- 不得把脚本骨架/模板直接当成品提交；
- 不得依据文件名、领域标签或案例编号猜测材料内容。

**触发条件**：科研语境下要求“画/改一张示意图、机制图、通路图、流程/装置图、Graphical Abstract 或图表”，且要求可编辑、可溯源或可投稿；或给定材料要求“据此做图并说明每个元素来源”。仅摘要改写、只讨论配色审美时不适用。

**边界**：不做统计方法选择与数值计算，不做海报版式/艺术插画/美化，不写论文正文。图中每个名称、数值、单位必须来自材料；材料没有的对象**不补造**，只进 `exceptions` / `pending_human`。

## 2. 运行时契约与目录

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

- 输入根目录固定为 `/input`，内含 `case.json`、`task.md` 以及题面提供的材料（PDF/DOCX/CSV/PNG/SVG 等）与 workorder。
- 工作目录为 `/app/work`；最终产物必须落在 `/app/output`。
- 最终必须生成 `result.json`，且包含：
  - `case_id`（原样回填）；
  - `output_contract` 中的**全部字段**（键名不改，缺值 `null`）；
  - 题面要求的可编辑源文件与真实渲染的 PDF/PNG 预览。
- 可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**：本题可编辑源通常为 SVG，则 PNG/PDF 既是导出也是预览；若可编辑源是 PPTX/ODP/DOCX，需用可用引擎渲染为 PDF/PNG，并将引擎写入 `export_artifact`。
- 退出码恒为 0；分析开始前先写 partial `result.json`，结束无条件 finalize 覆盖。
- 默认 `--input` 依次尝试 `/input`、`/app/input`、`./input`；`--output` 为 `/app/output` 或 `./output`。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。优先完成高权重交付物，尽早落盘 honest partial。

## 3. 输入发现与真实解析

### 3.1 语义识别输入

1. 读取 `/input/case.json`（或输入树内任意 `case*.json`）；即使 JSON 损坏也继续，`case_id` 原样保留。
2. 提取 `output_contract` 原样透传：支持 `list[str]` / `list[dict]`（取 `name|field|key|id`）/ `dict` 三种形态，键名不改，缺值 `null`，未知字段保留。
3. workorder 依次取 `organizer_workorder`、`organizer_edit_workorder`、`*workorder*` 文件、`material.json`；键名按语义匹配（`figure_title|title`、`required_entities|entities|nodes`、`required_relations|relations|edges`、`source_artifact|baseline`、`edit_operations|edits`）。
4. 材料按真实内容读取：
   - `md/txt/csv/tsv/json/yaml/tex/xml` 直接读；
   - `pdf` 用 `pdftotext`（或平台提供的 `pdf-text-tool`）提取文本层，无文本层记 `no_text_layer`，绝不臆造内容；
   - 既有 `*.svg` 作为编辑基线；
   - `docx/xlsx/pptx` 若环境有 LibreOffice headless 可先转 PDF/TXT 再读；否则记 `unsupported_source:<file>`。
5. 未给的对象明确列缺口，写入 `exceptions` 与 `pending_human`。

### 3.2 真实解析要求

- **必须真实解析材料内容**，不能依据文件名、目录名或领域标签猜测/补造数据。
- 每个实体、关系、数值、单位都要有来源定位（如 `file#L12`、`pdf#p3+L12`、`table#row=3,col=Expression`）和逐字 `quote`。
- 如果材料为空或不可读，必须记录 `input_error` 或 `partial`，并保持合法 `result.json`。

## 4. 专属执行流程（按顺序执行，不得跳步）

### 步骤 0：预算与契约初始化（1 次模型请求）

**输入**：`/input/case.json`、`/input/task.md`、文件列表。  
**动作**：  
- 读取 case.json，确认 `case_id`、`output_contract`、workorder 键名。  
- 核对预算：总请求 ≤64，总时长 ≤900s。  
- 确定 rubric 权重最高的交付物：可编辑 SVG + 真实 PNG/PDF + 逐条来源映射。  
**输出**：内部计划（契约字段清单、材料清单、优先级）。  
**失败分支**：若无 `case.json`，尝试输入树内 `case*.json`；仍无则 `status=input_error`，写入合法 result.json 并退出码 0。

### 步骤 1：盘点输入与材料清单（1-2 次请求）

**输入**：`/input` 目录。  
**动作**：  
- 列出所有材料文件及其类型。  
- 区分 workorder、来源材料、既有图稿、模板/白板。  
- 对 PDF/DOCX 等二进制文件，记录可用的解析工具（`pdftotext`、`soffice` 等）。  
**输出**：材料清单 + 可解析性初判。  
**失败分支**：材料为空 → `status=input_error`；部分材料不可解析 → 记录 `degradations`，继续处理可读部分。

### 步骤 2：用工具真实解析材料并提取证据（3-8 次请求，视材料复杂度）

**输入**：步骤 1 清单中的每个来源文件。  
**动作**：  
- 对文本类文件直接读取关键段落；  
- 对 PDF 调用 `pdftotext` 提取文本层，定位段落与行号；  
- 对 CSV/TSV 读取表头、行号、关键数据列；  
- 对 DOCX/XLSX/PPTX，若有 LibreOffice headless 转为 PDF/TXT 再解析，否则记 unsupported；  
- 解析 workorder 中的 `required_entities`、`required_relations`、图表数据要求。  
**输出**：来源内容摘录、实体-关系候选表、数据点候选表、每项带 locator 与 quote。  
**失败分支**：  
- 无文本层 → `errors` 记 `no_text_layer`，不猜内容；  
- 解析工具缺失 → 记 `degradations`，尝试其他工具或标 unsupported；  
- 材料与 workorder 冲突 → 记录冲突，优先以材料为准并在 `uncertainty` 说明。

### 步骤 3：运行基线脚本，产出全套交付物（0-2 次模型请求 + 工具执行）

**输入**：`/input` 目录。  
**动作**：  
- 执行 `python3 -B scripts/main.py --input /input --output /app/output`。  
- 脚本生成基线：`figure.svg`、`figure.png`、`figure.pdf`、`figure_model.json`、`edit_record.json`（编辑案例）、`result.json`。  
- **保留全部基线产物**，后续任何改进只能在基线上增强，不得删除、清空或遗漏。  
**输出**：完整基线文件集 + 初始 result.json。  
**失败分支**：  
- 若脚本无输出或部分文件缺失，执行步骤 5 手工补全；  
- 若脚本崩溃，检查错误日志，仍要写合法 result.json（退出码 0），并记录 errors。

### 步骤 4：Agent 亲自核验与推导（4-10 次模型请求，关键步骤）

**输入**：基线 `result.json`、`figure_model.json`、来源材料摘录、生成的 SVG/PNG/PDF。  
**动作**：  
1. 逐条核对 `content_map` 中每个实体、关系、数据点的 `source_id`、`locator`、`quote` 是否真实存在。  
2. 核对关系方向：激活→箭头、抑制→T 形、结合→菱形；被动语态（“被…抑制”“is inhibited by”）是否翻转。  
3. 核对图面元素与 `content_map` 的 id 一一对应；无对应 id 说明缺漏。  
4. 核对数值与单位是否与材料/数据表逐项一致；图例、颜色映射与分类数目一致。  
5. 核对可编辑源文件是否为分层 SVG、文字是否活文字、图层是否可拆。  
6. 把核验结果写入 `reviewed_by_agent` 对象（额外字段，不覆盖 output_contract 键）：  
   - `critical_labels_checked`: 已核验的标签列表；  
   - `source_quote_matches`: `{label: true/false}`；  
   - `conflicts`: 不一致项；  
   - `conclusion`: `verified` / `partial` / `conflict`。  
**输出**：核验记录，标记 verified / pending_human / conflicts。  
**失败分支**：  
- 发现错误或冲突 → 进入步骤 5 修复；  
- 来源缺失无法核验 → 标 `pending_human`，不伪造。

### 步骤 5：增量改进与重新生成（按需，2-8 次模型请求）

**输入**：核验发现的错误、冲突或缺口。  
**动作**：  
- 优先修正 workorder 或材料缺失/错误，重新执行 `python3 -B scripts/main.py --input /input --output /app/output` 生成全套；  
- 若仅需修改个别标签或布局，可编辑 `figure.svg` 与 `figure_model.json`，保持中间表示与最终图一致；  
- 对修改后的 SVG 重新导出 PNG/PDF（使用渲染引擎，如 `rsvg-convert`/`cairosvg`/`inkscape`/`matplotlib`），并记录引擎与时间戳；  
- 更新 `content_map`、`compliance_checks`、`changes`，保留修改前记录。  
**输出**：修正后的完整交付物与更新后的 result.json。  
**失败分支**：  
- 无法修复 → 保留原基线，将问题写入 `exceptions`/`pending_human`，status 降为 `partial`；  
- 渲染失败 → 保留 SVG，PNG/PDF