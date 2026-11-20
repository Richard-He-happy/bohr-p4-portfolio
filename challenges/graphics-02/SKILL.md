---
name: source-value-chart
description: Generate a real, editable, source-bound scientific data chart (layered SVG plus PDF/PNG preview) from the case's own table or statistics file, keeping a per-mark map so every bar, point, error bar, axis, unit and legend entry traces back to a source file, sheet, row, column and verbatim value. Use for source_value_chart workorders, grouped/bar/line/scatter figure generation or restyling, and whenever numeric fidelity, unit/legend/error-bar checks, CJK font fallback, editable vector output and honest gaps matter more than decorative styling.
version: 2.0.0
---

## ★ 最高优先级：真实、可核验、可回溯、可交付

本 Skill 用于科研图表生成与编辑。Harness Agent 必须实际读取 `/input` 下材料，不得依据文件名、目录名、领域标签或“应该长什么样”补造数据。每个关键数字、单位、科学实体、轴标签、图例项、误差棒、显著性标记必须能回溯到实际材料的具体位置。

- Agent 的角色：真实读材料、核验脚本抽取值、在 `draft.json` 中写判断、补充不确定性与缺口、改进文字型交付物。
- 脚本的角色：确定性盘点、抽取、渲染、检查、生成 `result.json`。结构化产物由脚本生成，Agent 不得手工改写脚本生成的结构化 JSON。
- 若没有可靠的 Agent draft，脚本必须确定性兜底，用 `AUTO_EXTRACT` 生成实质工作稿，并诚实记入 `degradations` / `gaps`。
- 任何情况下退出码必须为 0；运行失败也要落盘合法 `result.json`。

---

## 0. 运行契约

- 输入：`/input/case.json`、`/input/task.md`，以及题面给出的科研材料（CSV/TSV/XLSX/XLSM/PDF/DOCX/PNG 等）。实际文件是事实依据。
- 工作目录：`/app/work`。最终产物落盘 `/app/output`。
- 必须产出 `/app/output/result.json`，包含原 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- 可编辑办公/图形产物必须有可检查的真实渲染预览。本 Skill 核心可编辑产物为 `chart.svg`，并同时交付 `chart.pdf` 与 `chart.png`。
- 预算上限：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。必须先产生完整基线，尽早 honest partial，再增量增强。
- 资源限制：最多 50 个 UTF-8 文本文件，单文件 ≤500KB，总文本资源 ≤2MB；不依赖 symlink 或个人文件。脚本应使用 Python 标准库，离线可用，python3≥3.8。

---

## 1. 单命令全流程入口

优先使用：

```bash
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input \
  --output /app/output \
  --work /app/work \
  --style journal
```

也可使用短入口：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 内部依次执行：

1. `init`：盘点 `/input` 材料，分配来源编号 `S#`，抽取候选数据表/文本，建立 `/app/work/inventory.json` 与 `/app/work/ledger.json`，识别冲突或缺失。
2. `check`：若存在 `/app/work/draft.json`，校验 draft 与 ledger/schema；无 draft 则返回 `NEEDS_DRAFT` 状态。
3. `build`：若 draft 不可用或不完整，确定性生成 `AUTO_EXTRACT` 工作稿；随后渲染全套产物并写 `result.json`。
4. `selfcheck`：核对产物、契约字段、来源定位、导出件与检查结果。

阶段也可单独调用：

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

Agent 不得只调用一次脚本就结束；必须读 init 台账和实际材料，做核验或补充。若预算不足，优先保证脚本基线 right result.json。

---

## 2. Agent-first 双路径

### 2.1 Agent 路径（推荐）

1. 运行 `init`。
2. 读 `/app/work/inventory.json` 与 `/app/work/ledger.json`；读 `/input/case.json`、`/input/task.md` 和实际材料。
3. 逐项核验脚本抽取的 `quote`、`locator`、`file`、`sheet`、`row`、`col`、`header`、`unit`。
4. 将判断写入 `/app/work/draft.json`。
5. 运行 `check`。
6. 根据 check 结果修正 draft 或注明 conflict。
7. 运行 `build`。
8. 运行 `selfcheck`。
9. 写 `/app/work/agent_review.json` 与 `/app/work/pending_human.json` 补充项。

### 2.2 无 draft 时的确定性兜底

若 Agent 没有写 draft，或 draft 校验严重失败，`build` 必须：

- 使用 `init` 的 ledger/extracted 文件确定性抽取：逐列识别 x/y/group/error/significance；
- 不进行大模型猜测；不补造缺失数据；
- 自动生成工作稿和全套产物；
- 在 `degradations` 中写 `AUTO_EXTRACT`，并说明哪些判断未经过 Agent 核验；
- 若数据不足，状态为 `insufficient_evidence`，不产出假图。

两条路径最终必须产出同一套产物和同一份 `result.json` 契约。

---

## 3. 目录与交付物

### 3.1 输入扫描

`init` 扫描 `/input`：

- `case.json`：提取 `case_id`、`output_contract`、workorder。
- `task.md`：提取题目要求、图表类型、约束、预期产物。
- 数据文件：CSV/TSV/XLSX/XLSM 优先。多 sheet 文件必须逐个 sheet 解析。
- 材料文件：PDF/DOCX/PPTX/PNG 等。必须实际提取文本或表格；PDF 不依赖预提取答案层。
- 记录每个文件路径、来源编号 `S#`、sha256、行数/段落数、可解析性。

### 3.2 工作目录 `/app/work`

`init` 至少生成：

- `inventory.json`：输入文件、来源编号、类型、大小、sha256、可解析性、候选表格。
- `ledger.json`：每个数据表/文本块的位置、header、行/列候选、verbatim quote、locator。
- `extracted/`：提取出来的表格 CSV 或文本中间产物，来自真实材料。
- `draft.json`：Agent 写的图表计划与绑定（可选）。
- `agent_review.json`：Agent 核验记录（可选但推荐）。
- `pending_human.json`：需要人工确认项（可选但推荐）。
- `verification.json`：`selfcheck` 结果。

### 3.3 最终输出 `/app/output`

必须存在：

- `chart.svg`：分层可编辑矢量源文件。保留真实 `<text>` 元素，不转曲。
- `chart.pdf`：矢量导出，至少 1 页。
- `chart.png`：位图预览，默认 300 dpi，尺寸非零。
- `chart_model.json`：单一图表模型，驱动 SVG/PDF/PNG 和来源映射。
- `evidence_table.json`：逐图元证据表，每行一个 claim/point/axis/legend 等。
- `verification.json`：selfcheck 输出。
- `result.json`：最终契约结果。
- 如有文字成稿或图注，可输出 `deliverable.md`、`fig_caption.md`；不得与中间草稿复制同一文本。

若可编辑幻灯片/Office 图是题面要求，则还要输出对应可编辑源文件，并渲染真实 PDF/PNG 预览。

---

## 4. result.json 契约

### 4.1 顶层字段

`result.json` 必须合法 JSON，顶层字段至少包括：

```json
{
  "case_id": "来自输入的 case_id；缺失则为 unknown_case",
  "status": "ok | partial | insufficient_evidence | input_error",
  "editable_source": {},
  "export_artifact": {},
  "content_map": {},
  "compliance_checks": {},
  "exceptions": [],
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "changes": [],
  "runtime": {},
  "task": {},
  "output_contract": {}
}
```

### 4.2 双回显

- 原 `output_contract` 中的所有字段必须原样出现在 result 根级。
- `case_id` 和这些契约字段也必须出现在嵌套的 `output_contract` 中一次，值一致。
- 未知契约键保留，无值用 `null` 或 `[]`。

### 4.3 关键字段说明

`status`：

- `ok`：成图且关键核验通过，缺失项为空或已解释。
- `partial`：已产出可交付图，但存在未解决缺口、降级或部分字段缺失。
- `insufficient_evidence`：无法从材料获得足够源数据。
- `input_error`：输入不可解析且无法继续。

`editable_source`：

```json
{
  "path": "chart.svg",
  "format": "svg",
  "editable": true,
  "layers": [],
  "text_count": 0,
  "element_count": 0,
  "sha256": "",
  "viewBox": "",
  "model": "chart_model.json"
}
```

`export_artifact`：

```json
{
  "svg": {},
  "pdf": { "engine": "", "pages": 0, "vector": true, "mediabox_pt": [], "bytes": 0 },
  "png": { "engine": "", "width": 0, "height": 0, "dpi": 0, "color_type": "", "bytes": 0 }
}
```

无 PDF 引擎或 PNG 光栅化器时，对应字段为 `null` 或对象中写明 `unavailable`，并在 `degradations` 记录。

`content_map`：

```json
{
  "chart": "source_value_chart",
  "series": [
    {
      "series_id": "series_1",
      "label": "",
      "mark": "bar | point | line | errorbar",
      "points": [
        {
          "x": "",
          "y": 0,
          "y_raw": "",
          "geometry": {},
          "source": {
            "file": "",
            "sheet": "",
            "row": 0,
            "col": 0,
            "col_index": 0,
            "header": "",
            "x_header": "",
            "x_col": 0,
            "quote": "",
            "locator": "file#L12"
          },
          "error_raw": "",
          "error": 0,
          "error_mode": "sd | sem | ci | none",
          "error_source": {},
          "significance": ""
        }
      ]
    }
  ],
  "axes": [],
  "legend": [],
  "coverage": { "required": 0, "mapped": 0, "missing": [], "ratio": 0 }
}
```

每个 `point.source` 必须含：

- `file`：实际文件名。
- `sheet`：sheet 名，无则 null。
- `row` / `col` / `col_index`：源位置。
- `header`：数值列名。
- `x_header` / `x_col`：x 分组列。
- `quote`：原来源行/格原文，不得改写。
- `locator`：`文件#行号/段落号` 或 `file#sheet!R5C3` 形式。

`compliance_checks` 必须含：

- `canvas`
- `fonts`
- `line_widths`
- `colors`
- `legend_consistency`
- `geometry_roundtrip`
- `content_coverage`
- `canvas_overflow`
- `png`
- `pdf`
- `pass`
- `failures`

其中：

- `geometry_roundtrip`：将视觉坐标反查回数据值，容差 ≤2%；`mismatch_count` 必须记录。
- `legend_consistency`：图例与系列一一对应，mismatch 必须记录。
- `content_coverage`：required/mapped/missing/ratio。
- `canvas_overflow`：标签过长时记录是否旋转、是否溢出。
- `fonts`：字体缺失或 CJK 方框风险必须记录。

`sources` 数组：

```json
{
  "source_id": "S1",
  "file": "",
  "sheet": "",
  "row": 0,
  "col": 0,
  "header": "",
  "quote": "",
  "locator": "file#L12"
}
```

`uncertainty`：每条用 `{code, detail, severity, affected_marks}` 记录推断/不明确项。

`pending_human`：不能自动解决的冲突、缺单位、缺误差列、OCR 失败等。

`errors`：运行错误。

`degradations`：降级项，例如 `AUTO_EXTRACT`、`log_axis_no_positive`、`chart_type_unsupported`、`png_export_failed`。

`changes`：相对基线产品的人工或 Agent 修改；无修改写 `[]` 或说明 `reviewed_by_agent`。

`runtime`：

```json
{
  "started": "",
  "finished": "",
  "seconds": 0,
  "model_requests_used": 0,
  "repetition": 1
}
```

---

## 5. draft.json 最小形状

Agent 写 draft 时使用以下形状；`check` 只校验可解析性和引用一致性，不要求所有可选字段：

```json
{
  "case_id": "",
  "chart_type": "source_value_chart",
  "style_preset": "journal",
  "title": "",
  "data_bindings": [
    {
      "series_id": "bar_1",
      "label": "",
      "mark": "bar",
      "x": "",
      "x_source": { "file": "", "sheet": "", "row": 0, "col": 0, "header": "", "quote": "", "locator": "" },
      "y": 0,
      "y_raw": "",
      "y_source": { "file": "", "sheet": "", "row": 0, "col": 0, "header": "", "quote": "", "locator": "" },
      "error_raw": "",
      "error": 0,
      "error_mode": "sd",
      "error_source": {},
      "significance": "",
      "uncertainty": []
    }
  ],
  "axes": [],
  "legend_entries": [],
  "exclusions": [],
  "pending_human": []
}
```

无 draft 时，`build` 用 ledger 确定性生成 `AUTO_EXTRACT` draft；该 draft 必须出现在工作目录或内存记录中，并在 `degradations` 标注 `AUTO_EXTRACT`。

---

## 6. 数据抽取与来源规则

- 逐字 quote：任何数值/单位/实体名/图例项必须保存原文。数值清洗后的 `y` 可与 `y_raw` 不同，但不得伪造。
- 空值、`NA`、`n.d.`、`-`、`<0.01` 等：跳过该点或按原始字符串记录，不得画为 0。
- 多 sheet：逐个 sheet 抽取并标注 `sheet`。
- PDF/DOCX/PNG：必须实际提取，不依赖文件名。扫描版 PDF 无法有效 OCR 时，标 `pending_human`，不猜测。
- 源数据版本：记录文件 sha256 或来源版本，若材料提供版本号则写入 `sources`。

---

## 7. 图表渲染与导出规范

- 样式预设：`journal`（默认）、`nature`、`thesis`、`presentation`、`default`。
- 字体栈：`Helvetica → Arial → Noto Sans CJK SC → DejaVu Sans`。SVG 保留 `<text>` 元素，不转曲。
- 线宽、配色、面板布局、留白按 `references/style-presets.md`。
- 导出件：
  - SVG：可编辑矢量。
  - PDF：矢量，真实页数 ≥1。
  - PNG：默认 300 dpi；颜色类型正常；尺寸非零。
- 长标签：旋转 −35°；记录 `canvas_overflow.x_labels_rotated=true`。
- 轴与单位：轴标签与单位必须来自来源。无单位写 `unit not reported`。
- 图例：自动与系列绑定；不一致时 `legend_consistency` 失败并记录。

---

## 8. 隐藏案例鲁棒性

### 8.1 正常案例

- 有 `case.json`、`task.md`、一个或多个表；workorder 指定 x/y/error/group/significance。
- 行动：`init` 解析，Agent 核验，`build` 渲染，`selfcheck` 通过。状态 `ok`。

### 8.2 边界案例

| 情况 | 必须行为 |
|---|---|
| y 列不存在 | `column_not_found`；跳过该列，仍绘制存在的列，`status=partial` |
| 请求误差棒但无误差列 | `error_column_missing`；不画误差棒；记 `exceptions` |
| log 轴含非正值 | `log_axis_no_positive` 或 `value_off_log_axis`；轴降级 linear；记录 |
| 空值 / `NA` / `n.d.` / `-` / `<0.01` | 跳过该点或保留原串；不得画为 0 |
| 标签过长 | 旋转 −35°；`canvas_overflow.x_labels_rotated=true` |
| 多 sheet / 多表 | 逐个解析，source 中注明 sheet |
| CJK 字体缺失 | SVG 保留 `<text>`，字体栈回退；`fonts` 检查记录风险 |
| 不支持 heatmap/box 等图型 | `chart_type_unsupported`；降级为 bar marks 并记录 |
| 数值量级异常 | 基于源值范围检查；标 `value_range_suspicious`，不擅自改值 |
| 无 PDF 引擎 | `degradations` 记录；`export_artifact.pdf` 置 null；SVG 仍交付 |
| 无 PNG 光栅化器 | `errors: png_export_failed`；SVG+PDF 仍交付 |

### 8.3 异常案例

| 情况 | 必须行为 |
|---|---|
| `case.json` 缺失或损坏 | 扫描 `/input` 下最近 `case*.json`；仍无继续用目录扫描；`status=partial` |
| 无数据表 | `insufficient_evidence`；`coverage.required=0`；`pending_human` 记录 `no_source_table` |
| PDF/DOCX/图片不可提取 | `pending_human` + `degradations`；不猜数据 |
| 扫描版 PDF 且 OCR 失败 | `pending_human` + `ocr_failed`；不补造 |
| workorder 缺字段 | 使用脚本默认绑定规则；不确定性写入 `uncertainty` |
| 预算耗尽 | 立即落盘当前 result.json，`status=partial`，列 limits |

---

## 9. 预算策略

优先级：

1. 单命令跑 `run`，产出完整基线，约 1–3 次 shell/python 调用，几秒到十几秒。
2. Agent 读 inventory/ledger 和关键材料原文，约 5–10 次模型请求。
3. 核验高分值项：数值图元映射、轴单位、图例、科学实体拼写、误差线与显著性，约 10–18 次请求。
4. 写 draft / agent_review / pending_human，约 3–6 次请求。
5. selfcheck 和收尾，约 3–5 次请求。
6. 预留异常兜底，约 5–8 次请求。

当时间超过 800 秒或请求超过 60 次时，立即结束：保证 `result.json` 合法、产物路径正确、状态诚实。

---

## 10. 自检清单

1. `result.json` 可解析，`case_id` 与输入一致。
2. 原 `output_contract` 全部字段在 `result.json` 根级和 `output_contract` 嵌套中各出现一次，值一致。
3. `chart.svg`、`chart.pdf`、`chart.png`、`chart_model.json`、`evidence_table.json`、`verification.json` 存在且路径正确。
4. SVG 可打开，PDF 页数 ≥1，PNG 尺寸非零。
5. `content_map.coverage.required == mapped`，missing 为空或已解释。
6. 每个柱/点/误差棒/图例/轴/单位项都有 `source` 定位，`quote` 来自材料原文。
7. 轴标签、单位、量级与材料一致；无单位显式记录 `unit not reported`。
8. 科学实体名称与材料一致，无文件名/领域标签补造。
9. `geometry_roundtrip.mismatch_count == 0`；`legend_consistency` 通过或有解释。
10. `status` 与 `errors`、`degradations`、`pending_human`、`changes` 一致。
11. 无 draft 时 `degradations` 含 `AUTO_EXTRACT`。
12. 退出码 0；无未捕获异常。

---

## 11. rubric 维度 → 直接动作

### 实际效果 40

- 真走通「读源数据—出图—规范样式—校验标注—交付可编辑文件」全链路。
- 每点保存在 `content_map.series[].points[].source`，逐字 `quote` + locator。
- 六类检查点：科学实体、空间关系、数据编码、图例标注、可编辑源文件、导出格式。必须在 `content_map` 和 `compliance_checks` 中可核验。
- 交付 `chart.svg`、`chart.pdf`、`chart.png`、`chart_model.json`、`evidence_table.json`、`verification.json`、`result.json`。

### 使用增益 25

- 质量增益：自动图例绑定、单位标注、字体回退、标签旋转、误差棒绑定、`geometry_roundtrip` 和 `legend_consistency`。
- 效率增益：一条 `run` 命令从表到 SVG+PDF+PNG；记录 `runtime` 阶段。
- 增益可验证性：同输入重跑后 `editable_source.sha256` 可复现；`compliance_checks` 含可复现断言。

### 创新增益 15

- 图元到源数据双向映射：`geometry_roundtrip`。
- 图例与系列自动对齐：`legend_consistency`。
- CJK 字体回退与 SVG 保留 `<text>`：`fonts` 检查。
- 可编辑矢量源文件：`chart.svg` 分层、真实文本元素。
- 期刊模板适配：`journal/nature/thesis/presentation/default`。
- 创新证据：`coverage.ratio`、`degradations` 中真实降级链。

### 可靠体验 10

- 触发容易：`--help`、`run`、默认输出目录。
- 运行稳定：纯标准库、离线、幂等、退出码 0。
- 异常处理：显式 `exceptions`、`degradations`、`pending_human`，见第 8 节。

### 生态贡献 10

- 文档：`SKILL.md`、`references/chart-workorder-schema.md`、`references/style-presets.md`、`references/validation-checklist.md`。
- 可复用脚本：`scripts/main.py` 与 `scripts/toolkit.py` 模块化函数。
- 可复用资源：workorder schema、style presets、validation checklist、导出预设。

---

## 12. 包内文件

- `SKILL.md`：本文件。
- `scripts/main.py`：`run/init/check/build/selfcheck` 入口。
- `scripts/toolkit.py`：读写器、抽取器、workorder 解析、SVG 原语、检查函数、result 写入器。
- `references/chart-workorder-schema.md`：workorder 键名、默认值、绑定规则。
- `references/style-presets.md`：字体栈、期刊预设、导出预设、布局限制、颜色与线宽规则。
- `references/validation-checklist.md`：检查项、阈值、失败处理。

---

## 13. 维护说明

- 新图表类型：在 `scripts/main.py` render 分支添加 mark 类型，并同步 `scripts/toolkit.py` 的图例与 mapping 检查。
- 新 workorder 键：在 `scripts/toolkit.py` spec 中添加，并在 `references/chart-workorder-schema.md` 更新。
- 新检查项：在 `scripts/toolkit.py` 实现并暴露到 `compliance_checks`；不得静默丢弃失败检查。
- 修改样式/调色板视为版本变更：更新 frontmatter `version`，并在 `changes` 记录。