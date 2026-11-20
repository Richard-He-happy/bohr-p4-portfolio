---
name: scifig-editable
description: 将案例材料（task.md、workorder、prose/PDF/CSV/数据源、既有 SVG/图稿）真实解析为可溯源、分层可编辑的科研示意图、机制/流程/数据图或图表，交付真实 SVG/PNG/PDF 与完整 result.json。脚本提供 init/build/check/selfcheck/run 单命令全流程；Agent 可先写 draft.json 进行判断增强，无 draft 时脚本确定性兜底抽取，绝不编造来源。
version: 2.0.0
license: MIT
---

# scifig-editable：科研示意图生成与编辑

## 0. 最高优先级

本 Skill 的目标不是“画得漂亮”，而是走通 **材料 → 实体/关系/数据中间表示 → 分层可编辑源文件 → 合规导出件 → 可复核 result.json**。

必须做到：

1. 每个科学实体、关系、数值、单位、图例项都能追溯到来源材料或既有图稿；无法追溯的内容不补造，写入 `pending_human` / `gaps` / `uncertainty`。
2. 交付可编辑源文件，通常为分层 SVG；同时交付真实 PNG/PDF 预览。若题面要求 PPTX/ODP/DOCX 可编辑件，也必须同时交付真实渲染的 PDF/PNG 预览。
3. 所有产物最终服从 `/input/case.json` 的 `output_contract`；`result.json` 中契约字段必须双回显。
4. 任何情况都要落一个合法 `result.json`，退出码为 0；失败时写诚实 partial/error，不伪造。

你是执行本 Skill 的 Agent。先读取真实材料，优先走 Agent 判断路径；若时间或请求预算不足，必须让脚本走确定性兜底路径，完成交付。

---

## 1. 运行时契约

### 1.1 固定路径

- 输入目录：`/input`
- 工作目录：`/app/work`
- 输出目录：`/app/output`
- Skill 根目录：`/skills/weekly-skill`

### 1.2 单命令全流程入口

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部应依次完成：

1. `init`：盘点输入文件、解析 `case.json` 与 workorder、建立来源编号 `S1...Sn`、抽取实体/关系候选、识别冲突与缺口。
2. `build`：校验或读取 `${WORK}/draft.json`；若没有 draft，则基于 init 台账做确定性抽取；生成图稿中间模型、SVG、PNG/PDF、来源映射、导出检查、result.json。
3. `selfcheck`：核对 `output_contract` 字段、磁盘文件、result.json 键、SVG 文字可编辑性、来源 locator、导出检查项。

如果脚本不支持 `run` 子命令，降级为：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

如果仍失败，按本文件第 9 节手工兜底，但退出码必须为 0。

### 1.3 预算

- 官方预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。
- 优先把预算花在高权重交付物：可编辑 SVG、真实 PNG/PDF、完整 result.json、来源映射。
- 开始后先让脚本产出基线 partial；接近预算上限时立即收尾，不要因过度优化导致无结果。

---

## 2. 双路径工作流

### 2.1 Agent 路径

当你有足够预算阅读材料并判断时：

1. 运行：

```bash
python3 -B scripts/main.py init --input /input --output /app/output --work /app/work
```

2. 阅读 `${WORK}` 下的台账，如 `ledger.json`、`sources.json`、`candidates.json`、`conflicts.json`。
3. 真实读取 `/input` 内材料，不依据文件名或领域标签猜测内容。
4. 将你确认或修正后的判断写入：

```text
/app/work/draft.json
```

5. 运行：

```bash
python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

6. 检查 result.json 与产物是否齐全、来源是否可复核；必要时写 `agent_review.json` 记录逐条核验结论。

### 2.2 确定性兜底路径

如果未提供 `${WORK}/draft.json`，或预算不足：

```bash
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
```

脚本必须仍然：

- 生成一套实质工作稿，不能只给空模板；
- 从 init 台账中确定性抽取实体、关系、数值、图例项；
- 每个关键对象带逐字 `quote` 与 locator；
- 在 result.json 中诚实记录：

```json
{
  "extraction_mode": "AUTO_EXTRACT",
  "degradations": [
    {
      "type": "deterministic_fallback_used",
      "detail": "No agent draft.json was provided; source-bound extraction produced from init ledger."
    }
  ]
}
```

两条路径最终必须产出**同一套产物与同一份 result.json 契约**。

---

## 3. 输入发现与真实解析

### 3.1 先读 case

1. 读取 `/input/case.json`，若不存在则查找输入树内 `case*.json`。
2. 保留 `case_id` 原样。
3. 提取 `output_contract`，不要改键名。支持：
   - `list[str]`；
   - `list[dict]`，取 `name|field|key|id`；
   - `dict`。
4. workorder 依次查找：
   - `organizer_workorder`
   - `organizer_edit_workorder`
   - 文件名含 `workorder` 的文件
   - `material.json`
   关键字段语义匹配：
   - `figure_title|title`
   - `required_entities|entities|nodes`
   - `required_relations|relations|edges`
   - `source_artifact|baseline`
   - `edit_operations|edits`
   - `export_requirements|export`
   - `data_mapping|legend|legend_mapping`

### 3.2 材料解析

按真实内容读取：

- `md/txt/csv/tsv/json/yaml/tex/xml`：直接读。
- `pdf`：用 `pdftotext` 或平台提供的 PDF 解析工具提取文本层；无文本层记 `no_text_layer`，不得臆造。题面若提供既有 PDF 但“实际 PDF 无预提取答案层”，以实际可提取内容为准。
- `svg`：作为可编辑基线解析；读取 `<text>`、`<g>`、`<path>`、`id`、图层结构。
- `png/tiff`：只能作为图面参考或图形基线，不从中虚构科学实体；若无可提取文本，记入 `gaps`。
- `docx/xlsx/pptx`：如环境有 LibreOffice headless，先转 PDF/TXT 再解析；否则记 `unsupported_source:<file>`。

### 3.3 来源编号与 locator

所有来源在 init 阶段分配 `S1...Sn`。每条证据使用：

- `source_id`：如 `S1`
- `file`：实际相对文件名，如 `materials/figure03_source.pdf`
- `locator`：如：
  - `file#L12`
  - `pdf#p3+L5`
  - `csv#row=3,col=Group`
  - `svg#id=layer7`
  - `table#row=2,col=Expression`
- `quote`：逐字引用；无法逐字时用 `paraphrase`，不得伪造逐字引用。
- `strength`：`exact | paraphrase | inferred`

---

## 4. 科学判断：实体、关系、图面约束

### 4.1 从材料到图稿

对每张图建立中间模型，至少包含：

- `entities`：科学对象、基因/蛋白/复合物/过程/疾病/处理/时间点/浓度/样本组等。
- `relations`：方向、类型、层级。
- `data_mapping`：图例、颜色、形状与数据表分类逐项对应。
- `layout_constraints`：分组、包含、并列、上下游、时序、分区。
- `export_requirements`：格式、尺寸、dpi、色彩、字体、线宽。

### 4.2 关系方向与被动语态

优先阅读 `references/relation-vocab.md`。

- `激活/促进/诱导`：箭头指向下游。
- `抑制/阻断`：T 形终点指向被抑制方。
- `结合`：菱形或无箭头连接。
- `激活 A 被 B 抑制`：B 为上游，A 为下游，不要画反。
- 被动语态必须翻转判断：如“X was inhibited by Y”应理解为 Y → 抑制 → X。
- 包含关系用嵌套或分组边界，不要画成并列。

### 4.3 图例与数据映射

- 图例项数量必须与数据表分类一致。
- 颜色、形状、线型必须与 `data_mapping` 一一对应。
- 数值、单位、时间点必须来自材料；材料没有的数字不得出现在图中。
- 若数据表与文字描述冲突，以实际数据表为准，并在 `uncertainty` 或 `conflicts` 中说明。

### 4.4 不确定性

材料缺失、描述矛盾、关系方向不明、图例不完整时：

- 不编造；
- 写入 `uncertainty`；
- 若影响最终交付，写入 `pending_human`；
- `status` 可为 `partial`，但不能为空。

---

## 5. 交付物规范

最终必须在 `/app/output` 下交付，至少包括：

### 5.1 核心图稿

- `figure.svg`：分层可编辑 SVG。
  - 文字必须是活文字，不能全部转路径；
  - 图层/分组 `id` 清晰；
  - 标签可选中、可修改；
  - 不得把机制图当成装饰插画。
- `figure.png`：真实渲染预览。
- `figure.pdf`：真实 PDF 预览。

如果输出契约要求 EPS/TIFF/PNG/PDF 等，则按 `references/style-export-presets.md` 导出并检查。

### 5.2 结构与证据文件

- `figure_model.json`：实体/关系/布局/图例/数据映射的中间表示。
- `sources.json`：来源清单。
- `content_map.json`：图面元素 id → 来源 id / locator / quote。
- `evidence_table.json` 或等价物：每条关键论断 / 数字 / 标签的证据表。
- `export_checks.json`：导出检查结果。
- `edit_record.json`：若为编辑任务，记录 before/after、编辑操作、版本、来源依据。
- `selfcheck_report.json`：自检结果。

### 5.3 result.json

必须存在，内容见第 8 节。

### 5.4 可编辑 Office/slide/diagram 输出

若 output_contract 要求可编辑 PPTX/ODP/DOCX 等：

- 必须交付可编辑原件；
- 同时交付真实 PDF/PNG 预览；
- 在 `export_artifact` 或 `export_checks.json` 中记录渲染引擎与版本。

---

## 6. draft.json 形状

Agent 可以写 `${WORK}/draft.json`。最小结构：

```json
{
  "case_id": "原样 case_id",
  "figure_title": "题面或材料中的图题",
  "figure_type": "mechanism|flow|structure|data_figure|edit",
  "source_artifact": "既有 SVG 或基线文件，没有则为 null",
  "entities": [
    {
      "id": "E1",
      "label": "图面标签",
      "kind": "protein|gene|complex|process|condition|timepoint|group",
      "group": "分组名",
      "source": {
        "id": "S1",
        "locator": "file#L12",
        "quote": "逐字原文"
      }
    }
  ],
  "relations": [
    {
      "id": "R1",
      "from": "E1",
      "to": "E2",
      "type": "activates|inhibits|binds|converts_to|contains|precedes",
      "directed": true,
      "marker_end": "arrow|tee|diamond",
      "source": { "id": "S1", "locator": "file#L14", "quote": "..." }
    }
  ],
  "legend_mapping": [
    {
      "legend_id": "L1",
      "label": "Group A",
      "color": "#1F77B4",
      "shape": "circle",
      "data_source": {
        "id": "S2",
        "locator": "csv#row=2,col=Group",
        "quote": "Group A"
      }
    }
  ],
  "export_requirements": {},
  "uncertainty": [],
  "gaps": []
}
```

保留脚本生成的键名和结构；不要手改 `result.json`、`content_map.json`、`figure_model.json` 的结构。若发现脚本抽取错误，写 `agent_review.json` 指出，并通过重新执行 check/build 修正；若时间不足，保留脚本基线并记录问题。

---

## 7. 冲突、缺口与编辑任务

### 7.1 冲突处理

如果 workorder 与真实材料不一致：

- 以真实材料为科学事实来源；
- 保留 workorder 要求作为任务约束；
- 写入 `conflicts` / `uncertainty`；
- 不硬造一个材料中不存在的实体去满足 workorder。

### 7.2 缺口处理

材料缺失的对象、关系、数值、图例：

- 不进图；
- 写入 `gaps` 与 `pending_human`；
- 在 `result.json` 中明确 `missing_items` 或等价字段。

### 7.3 编辑任务

若输入提供既有 SVG/图稿：

1. 解析原图结构；
2. 找到需要修改的 `id` 或图层；
3. 将修改操作记录为 `edit_operations`；
4. 生成新 `figure.svg`；
5. 记录 `before` 与 `after`；
6. 重新导出 PNG/PDF。

---

## 8. result.json 合同

### 8.1 双回显

`case.json` 中的 `output_contract` 字段必须原样保留，并在 result.json 中出现两次：

- 顶层：将 output_contract 中每个字段映射到顶层值；
- `output_contract` 嵌套对象：保持原结构。

示例：

```json
{
  "case_id": "case-001",
  "editable_source_file": "figure.svg",
  "export_files": ["figure.png", "figure.pdf"],
  "output_contract": {
    "case_id": "case-001",
    "editable_source_file": "figure.svg",
    "export_files": ["figure.png", "figure.pdf"]
  }
}
```

### 8.2 必含字段

```json
{
  "case_id": "...",
  "status": "success|partial|input_error|conflict",
  "output_contract": {},
  "extraction_mode": "AGENT_DRAFT|AUTO_EXTRACT",
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "artifacts": [],
  "changes": []
}
```

`status` 取值：

- `success`：核心交付完整，来源可复核，导出检查基本通过。
- `partial`：有缺口或部分无法验证，但已交付可用的部分而不编造。
- `input_error`：输入缺失或无法读取。
- `conflict`：材料与 workorder 冲突明显，无法只靠抽取解决。

---

## 9. 自检与兜底 finalize

### 9.1 自检命令

```bash
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

同时阅读 `references/checklist.md`，逐项核对：

- `result.json` 是否合法 JSON；
- `case_id` 是否原样；
- `output_contract` 字段是否齐全且顶层/嵌套双回显；
- 每个文件是否真的存在且非空；
- SVG 是否包含活文字文字节点；
- 每个实体/关系/数值是否有 source_id / locator / quote；
- 图例项是否与数据表分类一致；
- 导出检查是否记录 dpi、色彩、字体嵌入等；
- 缺失项是否写入 gaps / pending_human / uncertainty。

### 9.2 自检报告

在 `/app/output/selfcheck_report.json` 中记录：

```json
{
  "contract_checked": true,
  "files_checked": true,
  "source_checked": true,
  "export_checked": true,
  "unresolved": []
}
```

### 9.3 手工兜底

若脚本最终失败：

1. 用 Python 读取 `/input/case.json` 提取 `case_id` 与 `output_contract`；
2. 保留已有文件；
3. 写最小合法 `result.json`，包含第 8 节字段；
4. 将失败原因写入 `errors` / `degradations`；
5. 退出码 0。

---

## 10. 隐藏案例鲁棒性

三类最可能输入及应对：

### 10.1 正常案例

- 有明确 workorder、来源材料、数据表或既有图。
- 必须全链路交付；不能因为脚本默认模板而省略来源映射与导出检查。

### 10.2 边界案例

- 材料部分缺失、语言含糊、图例与数据表不完全一致、既有 SVG 结构混乱。
- 策略：可读部分照常交付，缺失部分标 partial；不补造。优先保证来源可复核，而不是强行画满一张图。

### 10.3 异常案例

- `/input/case.json` 不存在、PDF 无文本层、材料空、渲染失败。
- 策略：写 `input_error` 或 `partial`；保留可交付文件；记录工具缺失或解析失败原因；`result.json` 仍需合法，退出码 0。

---

## 11. 来源与修改记录

每次运行应维护：

- `sources.json`：所有来源文件、类型、可解析性、页码/行号范围。
- `content_map.json`：图中元素 id → 来源 id。
- `evidence_table.json`：每条关键对象 / 数值 / 关系 / 图例项的 quote 与 locator。
- `changes.json` 或等价字段：记录 Agent 或脚本做的关键修改、版本、时间。
- `export_checks.json`：每种导出格式的检查结果与警告。

这些文件是“实际效果”和“增益可验证性”的证据，不要省略。

---

## 12. 常见扣分项，必须避免

1. 只输出位图，没有可编辑 SVG 或可编辑源文件。
2. 实体、关系、数值来自文件名或领域标签，而不是真实材料。
3. 把机制图当装饰插画，关系方向画反、层级错误。
4. 图例与数据表分类数量或颜色映射不一致。
5. 生成材料中不存在的基因名、浓度、时间点或单位。
6. 伪造 `golden_standard`、白板分、benchmark 分数。
7. 修改 `output_contract` 键名、漏掉契约字段、result.json 不合法。
8. 异常时退出码非 0，或最终没有 result.json。
9. 只交付模板骨架，没有实质 source-bound 内容。
10. 让失败直接停止，不保存 early partial deliverables。

---

## 13. 生态与复用

本 Skill 复用的资源：

- `references/checklist.md`：自检清单与预期输出。运行结束前逐项对照。
- `references/relation-vocab.md`：关系方向与图形语法词表。判断激活/抑制/结合/包含时查阅。
- `references/style-export-presets.md`：期刊常见导出参数与 SVG/PNG/PDF 检查项。
- `scripts/main.py`：init/build/check/selfcheck/run 流程。
- `scripts/render.py`：SVG 到 PNG/PDF 的真实渲染。

渲染依赖：

- 优先使用环境已安装的 `rsvg-convert`、`cairosvg`、`inkscape`、`libreoffice` 或 `matplotlib`；
- 如果用 `scripts/render.py`，执行：

```bash
python3 -B scripts/render.py --svg /app/output/figure.svg --out /app/output
```

- 如果环境缺渲染器，保留可编辑 SVG，并在 `export_checks.json` 中记 `renderer_missing`，同时尝试生成 PNG/PDF；不得假称已渲染成功。

---

## 14. 结束前最终检查

在结束前必须确认：

1. `/app/output/result.json` 存在且可被 JSON 解析。
2. `case_id` 原样保留。
3. `output_contract` 字段顶层与嵌套各出现一次。
4. 所有承诺的 artifact 文件真实存在。
5. 每个关键对象有来源 locator 与 quote；缺失项在 `gaps` / `pending_human`。
6. 可编辑源文件是真实可编辑的，不只位图。
7. PNG/PDF 是真实渲染，不是伪文件。
8. 错误、降级、不确定性均已诚实记录。
9. 退出码为 0。