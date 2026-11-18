---
name: scifig-editable
description: Turn case materials (task.md, workorder, prose/PDF/CSV sources, an existing figure) into a scientifically source-bound, layered, still-editable scientific schematic — mechanism/relationship diagram, workflow, or data panel — and return real PNG/PDF exports plus a 7-field result.json (editable_source, export_artifact, content_map, compliance_checks, exceptions). Use when the deliverable is a research figure that must stay editable, traceable to its sources, and export-ready.
version: 1.0.0
license: MIT
---

# scifig-editable

## 1. 用途与边界

**做什么**：把“来源材料 → 实体—关系中间表示 → 分层可编辑 SVG → 真实 PNG/PDF → 可核验记录”这条链路走完。

- 输入：`/input/case.json`、`task.md`、workorder、`material.json`、artifacts（md/txt/csv/tsv/json/yaml/tex/xml/pdf）、既有 `*.svg`。
- 输出：`figure.svg`（分层、文字可选、id 可追）、`figure.png`、`figure.pdf`、`figure_model.json`、`edit_record.json`（编辑案例）、`result.json`。
- 不做什么：不做统计方法选择与数值计算、不做海报版式/艺术插画/美化、不写正文。图中每个名称、数值、单位都必须来自材料；材料没有的对象**不补造**，只进 `exceptions` / `pending_human`。

## 2. 何时触发

用户在科研语境里要求“画/改一张示意图、机制图、通路图、流程/装置图、Graphical Abstract 或图表”，且要求可编辑或可投稿；或给定材料要“据此做图并说明每个元素的来源”。只要文字摘要、只讨论配色审美时不适用。

## 3. 运行契约

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

- 无第三方硬依赖：只用 Python 标准库；matplotlib / rsvg-convert / cairosvg / inkscape / LibreOffice / poppler / ImageMagick 皆按需探测，缺失即降级并记录。
- 不联网、不依赖 CWD（资源以 `Path(__file__).resolve().parent` 定位）。
- **退出码恒为 0**；分析开始前先写 partial `result.json`，结束无条件 finalize 覆盖。
- 默认路径：`--input` 依次尝试 `/input`、`/app/input`、`./input`；`--output` 为 `/app/output` 或 `./output`。

## 4. 输入发现（语义识别，不假设键名）

1. `case.json`（或在输入树里找任意 `case*.json`）；即使 JSON 损坏也继续，`case_id` 原样保留。
2. `output_contract` 原样透传：`list[str]` / `list[dict]`（取 `name|field|key|id`）/ `dict` 三种形态都支持，键名不改，缺值 `null`，未知字段保留。
3. workorder 依次取 `organizer_workorder`、`organizer_edit_workorder`、`*workorder*` 文件、`material.json`；键名按语义匹配（`figure_title|title`、`required_entities|entities|nodes`、`required_relations|relations|edges`、`source_artifact|baseline`、`edit_operations|edits`）。
4. 材料按真实内容读取：md/txt/csv/tsv/json/yaml/tex/xml 直接读；pdf 用 `pdftotext` 取文本层（无则记 `no_text_layer`，绝不臆造内容）；既有 `*.svg` 作为编辑基线。
5. 未给的对象明确列缺口，写入 `exceptions` 与 `pending_human`。

## 5. 核心流程

1. **抽取**：优先用 workorder 的实体/关系；缺失时从句子按关系词表（`references/relation-vocab.md`）解析 `头实体—关系—尾实体`，被动语态（`is inhibited by` / `被…`）自动翻转方向。
2. **校核**：每个 label 在材料里做规范化逐字查找（NFKC、小写、空白归一），命中即存 `{kind, source_id, locator, quote}`；未命中的实体保留但标 `verified=false`，未命中的关系**不入图**。
3. **建模**：写出一份 `figure_model.json`：`canvas / style / entities[box] / relations[path,marker] / legend / panels / chart / layers`。
4. **成图**：仅由该 model 生成 SVG——`<g id="layer-…">` 分层（background/panels/edges/entities/labels/legend/title）、`<text>` 保留为活文字（不转曲）、`<marker>` 区分激活(箭头)/抑制(T 形)/结合(菱形)、元素 `id` 与 `content_map` 一一对应。
5. **导出**：PNG/PDF 走可用引擎链，逐个探测并记录 `engines`；没有引擎就报 `missing` + `exceptions`，**绝不把文本改名成图片**。
6. **自检**：解析 PNG 真实 IHDR 与非白像素比例、PDF 头与页数，跑机器校验，写 `compliance_checks`。
7. **收尾**：`status` = `ok`（三件齐 + 校验通过 + 全部 label 可溯源）/ `partial`（有缺口，已记录）/ `input_error`（无可读材料）。

编辑案例：读既有 SVG，保留其 id、图层、坐标与样式，只替换 workorder 指定的文字，写 `edit_record.json`（原文件 sha256、改动前后、locator）；无匹配操作时原图原样保留并记 `no_edit_applied`。

## 6. 输出契约（`result.json`）

| 字段 | 内容 |
|-|-|
| `case_id` | 原样回填 |
| `status` | `ok` / `partial` / `input_error` |
| `editable_source` | `{path, format:svg, editable:true, text_live, layers[], text_count, element_count, marker_types[], sha256, coordinate_system, mode}` |
| `export_artifact` | `{png:{path,engine,width,height,dpi,bytes,probe}, pdf:{path,engine,pages,bytes,probe}}`，缺失则 `{path:null,status:"missing"}` |
| `content_map` | `{entities[], relations[], legend[], data_points[], coverage{}, svg_ids_expected[], svg_sha256, svg_sha256_recheck}` |
| `compliance_checks` | `canvas / svg_wellformed / id_map / labels_verbatim / style / markers / legend_consistency / overlap / overflow / determinism / pass / failures` |
| `exceptions` | `[{type, object, reason, action, locator}]` |
| 另附 | `sources[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime{}`、`output_contract_echo`，以及 `output_contract` 的全部键 |

`content_map` 每条都带来源与逐字 `quote`：实体 → 材料行（`file#L12`、`pdf#p3+L12`）或 `workorder#required_entities`；关系 → 关系依据来源；图表数值 → `table#row=3,col=Expression` 且 `quote` 为该单元格原文。

## 7. 评分要点 → 字段/检查/产物

| 评分维度 | 落点 |
|-|-|
| 任务完成度 | `editable_source` + `export_artifact.png/pdf` 真实存在（PNG 有 IHDR、PDF 有 `%PDF-`/`%%EOF`） |
| 结果正确性 | 关系类型→marker/颜色映射；被动语态翻转；`labels_verbatim` 检查 |
| 结果完整性 | `content_map.coverage`（实体/关系/图例计数）、panel 字母、图例、单位 |
| 可核验性 | 每元素 `locator`+`quote`；`id_map` 机器比对 SVG id ↔ content_map id |
| 质量/效率增益 | 内置字号阶梯(11/8.5/7)、线宽、避让、自动画布 fit；一条命令完成全链，`runtime.elapsed_s` |
| 增益可验证性 | `determinism`：同输入两次生成 SVG 字节一致（`svg_sha256`==`svg_sha256_recheck`） |
| 创新 | 实体—关系中间表示单向驱动 SVG/PNG/PDF/content_map；关系类型→端点语义；表驱动图例重绘；导出前合规检查 |
| 可靠体验 | 恒 0 退出、partial 先行、引擎降级表、`exceptions` 结构化 |
| 生态贡献 | 本文件 + 3 份 references（词表/预设/自检）+ 最小示例 |

## 8. 异常与降级

| 情况 | 处置 |
|-|-|
| 无 case.json / 无材料 | `status=input_error`，`exceptions[0].type=no_result`，仍写合法 result.json |
| case.json 损坏 | 继续，`case_id=null`，错误记入 `errors` |
| workorder 缺失 | 由材料句子抽取实体与关系（`extraction_mode=extracted`），不确定项写 `uncertainty` |
| label 不在材料中 | 保留但 `verified=false`，进 `exceptions` + `pending_human`；不参与 `ok` 判定 |
| 关系端点不可核验 | 该关系不入图，`relation_unverified` |
| 无 PDF 文本层 | `errors` 记 `no_text_layer`，不猜内容 |
| 无 matplotlib | 依次尝试 rsvg-convert/cairosvg/inkscape → LibreOffice+poppler → ImageMagick；引擎名写入 `export_artifact.*.engine` |
| 完全无导出引擎 | 保留 SVG，PNG/PDF 标 `missing`，`degradations` 说明原因 |
| xlsx/docx 材料 | 当前不解析，记 `unsupported_source:<file>`，需先导出为 CSV/TXT |
| 编辑基线不可解析 | 退回生成新图，`exceptions.baseline_unparsable` |

## 9. 自检（提交/排障）

```bash
python3 -B scripts/main.py --help                       # 退出码 0
python3 -B scripts/main.py --input /input --output /tmp/o
python3 -c "import json;d=json.load(open('/tmp/o/result.json'));print(d['status'],d['compliance_checks']['pass'],d['compliance_checks']['failures'],d['content_map']['coverage'])"
```

逐项清单见 `references/checklist.md`。

## 10. 最小调用示例（示例，非正式案例结果）

`/input/case.json`：

```json
{"case_id":"demo-001","output_contract":["editable_source","export_artifact","content_map","compliance_checks","exceptions"],
 "organizer_workorder":{"workorder_type":"editable_relationship_schematic","figure_title":"Demo mechanism",
  "required_entities":["IL-6","JAK2","STAT3","SOCS3"],
  "required_relations":[{"from":"IL-6","to":"JAK2","type":"activation"},
                        {"from":"JAK2","to":"STAT3","type":"activation"},
                        {"from":"SOCS3","to":"STAT3","type":"inhibition"}]}}
```

`/input/artifacts/notes.md`（来源）：`IL-6 activates JAK2 at the membrane.` / `JAK2 activates STAT3 by phosphorylation.` / `SOCS3 inhibits STAT3 in a negative feedback loop.`

示意输出（**示例，非正式案例结果**）：`figure.svg` 四实体三列、2 条激活箭头 + 1 条 T 形抑制端、图例 2 项；`figure.png` 3754×2379、非白像素比例 > 0；`figure.pdf` 1 页；`result.json` 中 `status=ok`、`coverage.entity_coverage=1.0`、`id_map.ok=true`、`pass=true`。

## 11. 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明 |
| `scripts/main.py` | 发现、抽取、建模、核算、结果写出 |
| `scripts/render.py` | 布局、分层 SVG、PNG/PDF 引擎链 |
| `references/relation-vocab.md` | 中英关系词表与端点语义 |
| `references/style-export-presets.md` | 画布/字号/配色/导出预设 |
| `references/checklist.md` | 自检清单与故障排查 |

## 12. 依赖与版本

Python ≥3.8（已在 3.12 验证），仅标准库。可选外部程序（任一即可出 PNG/PDF）：`pdftotext`（读 PDF）、`soffice`、`pdftoppm`、`rsvg-convert`/`cairosvg`/`inkscape`、`convert`、`matplotlib`。字体：SVG 只写回退栈 `Arial, Helvetica, 'DejaVu Sans', sans-serif`，不嵌外部字体、不转曲。

## 13. 已知限制

- 关系抽取是句法启发式，不建模时序、剂量、条件与可能性；复杂句可能抽错端点，逐条 `quote` 供人工复核。
- 布局是确定性的分列启发式，不是期刊级手工排版；元素多于 ~16 个时建议提供 workorder。
- xlsx/docx 不解析；PDF 依赖 `pdftotext` 文本层。
- 编辑模式只替换文字，不新增或删除图元。

## 14. 维护

改词表 → `references/relation-vocab.md` 与 `scripts/main.py` 的 `REL` 同步（类型名即 marker/颜色键）；改画布/字号/配色 → `render.py` 的 `STY` 与 `references/style-export-presets.md` 同步；新增导出引擎 → 在 `render._convert` 加一条探测分支，并在 `degradations` 里说明。
