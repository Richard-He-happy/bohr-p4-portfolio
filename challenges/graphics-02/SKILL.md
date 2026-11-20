---
name: source-value-chart
description: Generate a real, editable, source-bound scientific data chart (layered SVG plus PDF/PNG export) from the case's own table or statistics file, keeping a per-mark map so every bar, point, error bar and legend entry traces back to a source file, sheet, row, column and verbatim value. Use for chart generation or restyling workorders (bar, grouped bar, long-format series, line, scatter), for figure reproduction from published source data, and whenever numeric fidelity plus a checkable data-to-mark mapping matters more than decorative styling.
version: 1.1.0
---

# source-value-chart

## 0. 最高优先级：完整、真实、可核验

本 Skill 是给 Harness Agent 使用的科研图表生成与编辑工作流。包内脚本 `scripts/main.py` 与 `scripts/toolkit.py` 只是工具：它们负责解析表格、生成基线 SVG/PDF/PNG、写初始 result.json。**最终交付物必须由 Agent 亲自读材料、核对源数据、判断关键映射、补充科学实体与不确定性，并写入 result.json。**

禁止把脚本骨架、模板或未核验的中间产物直接当成品；禁止依据文件名、目录名或领域标签猜测/补造数据；每个关键数字、单位、实体名、图元都必须能回到实际材料中的具体位置。

完整性优先：进入任务后先运行本 Skill 的主脚本/流程，产出全套基线交付物；后续 Agent 校验与改写只能在此基线上增强，**不得删除、清空或遗漏任何基线产物与 output_contract 字段**；若不确定，保留原产物并在 result.json 中标注 `reviewed_by_agent`。提交前必须逐项核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一致；缺任何一项先补齐再收尾；partial 状态必须列出缺失项。

## 1. 运行契约与目录

- 输入：`/input/case.json`、`/input/task.md`，以及题面规定的材料（CSV/TSV/XLSX/PDF/DOCX/图片等）。材料必须实际解析，不得依据文件名或领域标签补造内容。
- 工作目录：`/app/work`。最终产物必须落在 `/app/output`。
- 必须产出 `result.json`，包含原 `output_contract` 的全部字段（键名不改）与 `case_id`。
- 可编辑 Office/幻灯片/图形产物必须额外给出真实渲染的 PDF/PNG 预览。本 Skill 的图形产物为 `chart.svg`（可编辑矢量源文件）、`chart.pdf`（矢量预览）、`chart.png`（位图预览）、`chart_model.json`（图表模型）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。必须预算感知，先完成 rubric 权重最高的交付物，尽早落盘 honest partial，再增量改进。
- 退出码始终为 0。任何异常都捕获，写回 result.json；不得因异常而空手退出。

## 2. 脚本调用命令

脚本是基线生成器，典型运行小于 15 秒，不依赖 CWD。

    python3 /skills/weekly-skill/scripts/main.py
    python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --style journal
    python3 /skills/weekly-skill/scripts/main.py --help
    python3 /skills/weekly-skill/scripts/main.py --version

参数说明：

- `--input DIR`：案例目录，默认 `/input` 若存在，否则 `./input`。
- `--output DIR`：产物目录，默认 `/app/output` 若存在，否则 `./output`。
- `--style NAME`：`journal`（默认）、`nature`、`thesis`、`presentation`、`default`。
- `--version`：打印版本。

脚本只做基线：解析输入、生成图表、导出 PDF/PNG、写 result.json。Agent 必须在其上做真实核验与增强。

## 3. 交付物与输出契约字段

`result.json` 始终包含以下字段；原 `output_contract` 中的每个键必须原样出现在 result 根级，未知键保留（无值时用 null 或 []）。

- `case_id`：来自案例原文。
- `status`：`ok` / `partial` / `insufficient_evidence` / `input_error`。
- `editable_source`：`path`, `format:svg`, `editable`, `layers`, `text_count`, `element_count`, `sha256`, `viewBox`, `model`。
- `export_artifact`：`svg`, `pdf{engine,pages,vector,mediabox_pt,bytes}`, `png{engine,width,height,dpi,color_type,bytes}`。
- `content_map`：`chart`, `series[].points[]`（value, raw string, source locator, geometry），`axes[]`, `legend[]`, `coverage{required,mapped,missing,ratio}`。
- `compliance_checks`：`canvas`, `fonts`, `line_widths`, `colors`, `legend_consistency`, `geometry_roundtrip`, `content_coverage`, `canvas_overflow`, `png`, `pdf`, `pass`, `failures`。
- `exceptions`：每个跳过/阻断项的 `{code, detail, severity, action}`。
- 其他：`sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `task`。

每个图元的 `content_map.series[i].points[j].source` 必须包含：
`file, sheet, row, col, col_index, header, x_header, x_col, quote`，其中 `quote` 是原始来源行原文。误差棒额外包含 `error_raw, error, error_mode, error_source`。

## 4. 本题专属执行流程

Agent 在每个案例中按以下步骤执行。每一步都要写清输入、动作、输出、失败分支。

### 步骤 1：盘点输入与契约

输入：`/input/case.json`、`/input/task.md`、`/input` 下所有材料文件。

动作：

1. 读取 `case.json`；若缺失或不可解析，扫描 `/input` 下最近的 `case*.json`；仍无则继续用目录扫描，失败记录到 `errors` + `degradations`。
2. 提取 `case_id`、`output_contract`、`task_instruction`、workorder 信息。
3. 列出 `/input` 下全部文件，识别数据文件、材料文件、任务说明。
4. 建立 `/app/work` 和 `/app/output` 目录。

输出：输入清单、case_id、output_contract 字段列表、workorder 摘要。

失败分支：缺 `case.json` 不阻断；缺 `output_contract` 时从题面通用要求推导字段：`case_id`, `status`, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`，并写入 result.json 作为兜底。

### 步骤 2：真实解析材料

输入：步骤 1 的文件清单。

动作：

1. 对 CSV/TSV/XLSX/XLSM：交给 `scripts/main.py` 解析。
2. 对 PDF/DOCX/图片：使用平台预装工具（如 `pdf-text-tool`、`pdftotext`、`python-docx`、OCR 等）提取文本和表格，保存到 `/app/work` 下作为中间证据；提取结果必须来自真实材料内容。
3. 若材料为扫描版 PDF 且无法有效 OCR：记录 `pending_human` 与 `degradations`，不要猜测数据。
4. 将提取到的数据文件写入 `/app/work`，供脚本或 Agent 后续使用。

输出：可解析的数据表、材料文本、来源引用。

失败分支：无可用表格时，后续状态为 `insufficient_evidence`，`content_map.coverage.required=0`，`pending_human` 记录 `no_source_table`。

### 步骤 3：构建证据与生成基线

输入：步骤 2 的解析结果与 workorder。

动作：

1. 调用脚本生成全套基线产物：
   `python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --style journal`
2. 脚本会读取表格，绑定 workorder 字段，构建中间模型 `chart_model.json`，渲染 `chart.svg`，导出 `chart.pdf` 和 `chart.png`，写初始 `result.json`。
3. Agent 亲自读取脚本生成的 `chart_model.json` 与 `result.json`，将其中的数值、列名、单位与步骤 2 提取的材料原文逐项比对。
4. 记录脚本的状态、运行时间、错误。

输出：基线产品与初始 result.json。

失败分支：若脚本异常，Agent 不得直接失败。根据已解析材料手工生成最小合法 SVG/PNG/PDF（或仅 SVG），并手工构造 `chart_model.json` 与 `result.json`；状态标 `partial`，异常写入 `errors`。若完全无数据，标 `insufficient_evidence`。

### 步骤 4：Agent 完成真实成品与增强

输入：基线产品、材料原文、workorder。

动作：

1. 逐项核验每个图元的源定位：柱高、点位置、误差线长度、图例条目是否能回到源文件、sheet、行、列与原文引用。
2. 核验科学实体名称（基因/蛋白/物种/化合物）是否与材料一致；不得改写或美化。
3. 核验轴标签、单位、刻度范围、图例与系列对应；若缺失单位，按 source header 或 workorder 保留，否则写 `unit not reported`。
4. 将核验结果写入 result.json：`sources`、`uncertainty`、`changes`、`verified` / `pending_human` / `conflicts`。
5. 若发现冲突或缺失，写到 `pending_human` 与 `exceptions`，不得隐藏。

输出：增强后的 result.json；必要时重新导出产品。

失败分支：核验中发现数据不一致但无法确认正确值，保留脚本基线值，标注 `conflicts`，状态 `partial`；绝不编造修正值。

### 步骤 5：自检 rubric

输入：步骤 4 的产物。

动作：按第 7 节「rubric 维度 → 交付要求 → 自证方式」逐条自检；根据第 8 节自检清单核对文件与字段。

输出：自检结论；如有缺口，回到对应步骤补齐。

失败分支：时间不足时优先保证 `result.json` 合法、output_contract 字段完整，并保留已有可交付图。

### 步骤 6：回填 result.json 并收尾

输入：步骤 5 的产物。

动作：

1. 确保 `result.json` 可解析，`case_id` 匹配，`output_contract` 全部字段存在且类型合理。
2. 确保所有产物路径指向实际存在的文件。
3. 确保 `status`、`errors`、`degradations`、`pending_human` 与真实过程一致。
4. 设置退出码 0。

输出：最终 `/app/output/result.json` 与交付物。

失败分支：任何最后时刻异常都捕获并追加到 `errors`，保持退出码 0。

## 5. 预算策略

总预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。按以下优先级分配：

1. 必做：步骤 1 输入盘点 + 脚本基线运行（约 5-8 次请求，10-30 秒）。必须产出基线 `chart.svg/PDF/PNG/result.json`。
2. 必做：步骤 2 材料真实解析（约 5-12 次请求，取决于 PDF/DOCX/图片复杂度）。花在提取表格和文本上的请求不能省，否则无法核验。
3. 必做：步骤 3-4 读取产物、核验关键源值、补写来源与不确定性（约 12-20 次请求，100-300 秒）。优先核验高分值项：数值与图元映射、单位、图例、实体拼写。
4. 建议：步骤 5 自检（约 3-5 次请求）。若预算紧张，至少检查 output_contract 字段完整性和关键源映射。
5. 保留：异常处理与兜底（约 5-8 次请求，50-100 秒）。

当运行时间接近 800 秒或模型请求接近 60 次时，立即落盘现有产品为 honest partial，确保 result.json 合法。不要做无意义的重试和冗余调用；脚本已完成的基线不要重跑。

## 6. 隐藏案例鲁棒性与降级

任何情况下都产出合法 result.json，退出码为 0。下表为常见异常处理：

| 情况 | 行为 |
|---|---|
| `case.json` 缺失或不可解析 | 扫描目录；记录 `errors` + `degradations`；继续执行；`status=partial` |
| 无数据表 | `status=insufficient_evidence`，`coverage.required=0`，`failures=[no_source_table]`，`pending_human` 记录缺口 |
| PDF/DOCX/图片不可提取或扫描版 | 记录 `pending_human` 与 `degradations`；不猜数据；可交付 SVG/PDF/PNG 时标 `partial`，否则 `insufficient_evidence` |
| workorder 的 y 列不存在 | `column_not_found`；跳过该列，仍绘制存在的列；状态 `partial` |
| 空值 / `NA` / `n.d.` / `-` / 审查值 `<0.01` | 跳过该点，列入 `coverage.missing`；绝不画为 0 |
| 请求误差棒但无误差列 | `error_column_missing`；不画误差棒；记录异常 |
| log 轴含非正值 | `log_axis_no_positive` 或 `value_off_log_axis`；轴降级为 linear；记录异常 |
| 标签过长 | 旋转 −35°，设置 `canvas_overflow.x_labels_rotated=true` |
| 不支持图表类型（heatmap/box） | `chart_type_unsupported`；降级为 bar marks；记录 degradation |
| 无 PDF 引擎 | `degradations` 记录；`export_artifact.pdf` 保持 null；SVG 仍交付 |
| 无光栅化器 | `errors: png_export_failed`；SVG + PDF 仍可交付 |
| 字体缺失中文显示为方框 | SVG 保留 `<text>`，字体栈 `Helvetica → Arial → Noto Sans CJK SC → DejaVu Sans`；记录 `fonts` 检查结果 |
| 超时或预算耗尽 | 立即写当前 result.json，状态 `partial`，列出 limits |
| 任何未捕获异常 | 捕获后写入 `errors`，保留已有 partial result.json，退出码 0 |

若 `output_contract` 缺失，按步骤 1 兜底字段生成；若工作目录 `/app/work` 不存在则创建；若输出目录不存在则创建。

## 7. rubric 维度 → 交付要求 → 自证方式

| rubric 维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果 · 任务完成度 15 分 | 真正走通「读源数据—出图—调样式—校验标注—交付可编辑文件」链路；产出 `chart.svg`, `chart.pdf`, `chart.png`, `chart_model.json`, `result.json` | 磁盘文件齐全；`status` 为 `ok` 或可解释的 `partial`；`task` 字段记录步骤 |
| 实际效果 · 结果正确性 15 分 | 数值、图元高度/位置、轴刻度/单位、误差线、显著性标记、图例与系列、科学实体名与源材料一致 | `content_map.series[].points[].source.quote` 逐点引用；`geometry_roundtrip` 通过 2% 容差；`legend_consistency` 通过；`axes[]` 记录单位与量级；`y_raw` 为源值原文 |
| 实际效果 · 结果完整性 5 分 | 题面要求的图表要素与六类检查点齐备：科学实体、空间关系、数据编码、图例标注、可编辑源文件、导出格式 | workorder 的每个 series 和误差列已渲染或列入 `exceptions`；`coverage.required == mapped` 或缺失已记录 |
| 实际效果 · 结果可核验性 5 分 | 源数据版本、字段映射、操作步骤、导出参数、修改记录能让他人重跑得到同一张图 | 每点 `source{file,sheet,row,col,header,quote}`；`editable_source.sha256`；`changes`；`runtime`；`export_artifact.pdf/png` 参数 |
| 使用增益 · 质量增益 15 分 | 相比基础 Agent 提升科学正确性、标注完整性与可编辑性 | 自动图例绑定、单位标注、标签旋转、字体栈、`compliance_checks`；与脚本基线对照的核验记录 |
| 使用增益 · 效率增益 5 分 | 从输入到成图耗时短、人工改图条目减少 | `runtime` 阶段计时；一条命令从表到 SVG+PDF+PNG；`changes` 中记录人工修改项 |
| 使用增益 · 增益可验证性 5 分 | 同输入同参数产出可复现 | 重跑后 `editable_source.sha256` 相同；`compliance_checks` 含可复现断言 |
| 创新增益 · 新增能力 5 分 | 图元到源数据双向映射校验、图例自动对齐、中文标注与字体回退、可编辑矢量导出、期刊模板适配 | `geometry_roundtrip`（px→value 反查）、`legend_consistency`、CJK 字体栈、`chart.svg` 保留 `<text>`、style presets |
| 创新增益 · 方法改进 5 分 | 数据到图元映射建模、样式规则化、标注校验策略带来实质改进 | `chart_model.json` 单一中间模型驱动 SVG/PDF/PNG 与 `content_map`；`references/style-presets.md` 提供规则 |
| 创新增益 · 创新证据 5 分 | 证明能力相对已有方案的边界与价值 | `geometry_roundtrip`、`legend_consistency`、`coverage.ratio`、`degradations` 显示降级链真实发生 |
| 可靠体验 · 调用与易用性 3 分 | 用户/Agent 能按说明从数据走到成图 | `--help`、默认目录、`--style`、`REFERENCES` 文档 |
| 可靠体验 · 运行稳定性 4 分 | 不同数据规模、图型、字体环境稳定运行 | 标准库 only；CSV/TSV/XLSX 解析；重复运行幂等；退出码 0 |
| 可靠体验 · 异常处理 3 分 | 对数据缺列、空值、量级异常、标签过长、字体缺失、导出失败、标注遮挡有识别与处置 | `exceptions` + `pending_human` 记录每个异常代码与行动；`compliance_checks.canvas_overflow`、`fonts` |
| 生态贡献 · 文档完整性 3 分 | 使用说明、依赖、字体来源、配置、局限齐全 | 本文件 + `references/validation-checklist.md` + `references/chart-workorder-schema.md` + `references/style-presets.md` |
| 生态贡献 · 资源可复用性 4 分 | 题集、脚本、样式模板、校验清单、导出预设可复用 | `scripts/toolkit.py` 的模块化函数；`style presets`；`workorder schema`；`validation checklist` |
| 生态贡献 · 分享推广价值 3 分 | 沉淀可分享图表案例、样式规范、校验经验 | 一条命令可复现；内容映射可回溯；本文件记录适用范围和限制 |

## 8. 自检清单（提交前逐项检查）

1. `result.json` 可解析，`case_id` 与输入一致；
2. `output_contract` 的每个字段均在 result.json 根级出现，且类型合理；
3. `chart.svg`、`chart.pdf`、`chart.png`、`chart_model.json` 存在且路径正确（如可成图）；
4. 每个图形产出都可打开；PDF 页数 ≥1，PNG 尺寸非零；
5. `content_map.coverage.required == mapped`，`missing` 为空或已解释；
6. 每个柱/点/误差棒/图例项都有 `source` 定位，`quote` 来自材料原文；
7. 轴标签、单位、量级与材料一致；无单位时写 `unit not reported`；
8. 科学实体名称与材料一致；没有用文件名或领域标签补造；
9. `geometry_roundtrip.mismatch_count == 0`，`legend_consistency` 通过；
10. `status` 与 `errors`/`degradations`/`pending_human`/`changes` 一致；
11. 基线产物未被删除或清空；`reviewed_by_agent` 已标注；
12. 退出码为 0；无未捕获异常。

## 9. 包内文件

- `SKILL.md`：本文件。
- `scripts/main.py`：基线流程入口；发现输入、构建模型、渲染 SVG、导出 PDF/PNG、写 result.json。
- `scripts/toolkit.py`：读写器、workorder 解析、SVG 原语、检查函数。
- `references/chart-workorder-schema.md`：workorder 键名、默认值、绑定规则。
- `references/style-presets.md`：字体栈、期刊预设、导出预设、布局限制。
- `references/validation-checklist.md`：检查项、阈值、失败处理。

## 10. 证据规则

- 每个图元只可携带源材料中真实存在的值，并引用其 `source.quote`。
- 轴标签/单位/刻度范围记录其来源：`source.header` 或 workorder 键。
- 衍生数值（像素几何）标为 derived，绝不当作源数据。
- 不确定性写入 `uncertainty`：图表类型是推断还是声明、单位是否复制、统计量是否仅传输未计算。
- 冲突与人工确认写入 `pending_human`，每条包含 code 与具体缺口，便于人工补齐。
- `changes` 记录对基线产物的修改；不修改时写 `[]` 或 `reviewed_by_agent`。

## 11. 失败与降级后的最低交付

即使无法生成完整图形，也必须输出合法 `result.json`。最低字段：

- `case_id`：从输入提取，缺失则 `"unknown_case"`。
- `status`：`partial` 或 `insufficient_evidence`。
- `editable_source`：可空对象，注明不可用原因。
- `export_artifact`：可空对象，注明不可用原因。
- `content_map`：`coverage.required=0`，`mapped=0`，`ratio=0`。
- `compliance_checks.failures`：列出失败代码。
- `exceptions`：列出所有异常。
- `pending_human`：列出需人工补充的信息。
- 退出码 0。

## 12. 维护说明

- 新图表类型：在 `scripts/main.py` 的 render 分支添加 mark 类型，并在 `scripts/toolkit.py` 补充对应图例编码和检查。
- 新 workorder 键：在 `scripts/toolkit.py` 的 spec 中添加，并在 `references/chart-workorder-schema.md` 更新文档。
- 新检查项：在 `scripts/toolkit.py` 中实现，并暴露至 `compliance_checks`；不得静默丢弃失败检查。
- 修改样式或调色板视为版本变更：升级本文件与 frontmatter `version`，并记录在 `changes`。