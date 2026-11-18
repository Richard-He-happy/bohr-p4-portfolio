---
name: apparatus-technical-route-figure
description: 把实验材料（PDF/DOCX/Markdown/JSON/表格）中的装置单元、连接方向、工艺步骤、阶段划分与关键参数抽成"实体—连接—步骤—阶段—参数"结构化中间表示，再由同一布局导出分层可编辑 SVG 与原生矢量 PDF（内嵌 TrueType 字体、中文可提取），并为每个图元给出逐字 quote + locator、几何与导出自检。适用于实验装置图、工艺流程图、材料流向图、技术路线图。采用 init → (Agent 写 plan.json) → check → build 四步，带确定性兜底。
version: 3.0.0
---

# 实验装置与技术路线图 · Skill

## 1. 用途与边界

**做**：把材料里的设备、接口、步骤、阶段、参数变成一张别人能看懂、能改、能复核的图。
判据三条：**每个图元可追溯到材料原文**、**连接方向与先后顺序成立**、**别人能复跑出同一张图**。

**不做**：数据分析与数值拟合；实验方案科学合理性判断；论文排版；**材料里没有的设备、管路、数值一律不补**。

## 2. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`（可缺）、`/input/**` 材料（PDF/DOCX/MD/TXT/CSV/JSON） |
| 工作目录 | `/app/work`（`index.json`、`plan.json`、`check_report.json`） |
| 产物 | `/app/output`：`figure.svg`、`figure.pdf`、`figure.png`、`content_map.json`、`result.json` |
| 调用 | `python3 -B scripts/main.py <init\|check\|build> --input /input --work /app/work --out /app/output` |
| 依赖 | 仅标准库；不联网；不依赖 CWD（`Path(__file__).resolve().parent`） |
| 退出码 | 恒 0；任何异常写入 `result.json.errors` |
| 断点 | 进入流程先写 partial `result.json`，结束时无条件 finalize 覆盖；脚本 1–4 s（含 PDF 写盘），无外部转换器依赖 |

可选外部工具（缺失即降级，不报错）：`pdftotext`（PDF 取文本）、`pdftoppm`/`mutool`（PDF→PNG 预览）。

## 3. 四步工作流（Agent 亲自判读，脚本只做索引 / 渲染 / 校验）

```bash
python3 -B scripts/main.py init  --input /input --work /app/work --out /app/output
#   读材料，写 /app/work/plan.json（字段见 references/plan_schema.md）
python3 -B scripts/main.py check --input /input --work /app/work --out /app/output
python3 -B scripts/main.py build --input /input --work /app/work --out /app/output
```

1. `init` 只做机械工作：输入发现、文本抽取、段落 locator 索引、workorder 摘要、写 partial 结果。
2. **Agent 自己写 `plan.json`**：设备名、连接、步骤、阶段、参数必须来自读到的句子，`quote` 为逐字片段。
3. `check` 报的问题都可修：`quote` 未命中就回材料重取；无法核实保留 `pending: true`（画琥珀虚线框）。
4. `build` 无 plan 也能跑（兜底：词表抽设备、流向动词抽连接、编号抽步骤），关系弱于 plan，`status` 如实降为 `partial`。

## 4. 输入发现（不假设键名）

1. `case.json` 优先，取首个 `case*.json`；JSON 损坏不中断，记 `case_json_invalid` 并继续扫材料。
2. `case_id` / `output_contract` 语义识别（忽略大小写与 `_`、`-`），`output_contract` 的每个键原样出现在 `result.json` 根级（缺值 `null`）。
3. 材料按**扩展名 + 魔数**识别（`%PDF`、`PK\x03\x04`→OOXML、纯文本），不看标签猜内容；`case.json` 本身不计作材料。
4. 段落切分：标题/编号项/项目符号各自成段，其余按空行与连续行合并（应对折行）。
   locator 形如 `S1 ¶12`；多页 PDF 为 `S1 p3 ¶12`，`S#` 与 `result.json.sources` 一一对应。
5. 抽不出文本的材料（纯图片、扫描件、无 `pdftotext` 的 PDF）只登记来源，不猜内容，记 `material_no_text`。

## 5. 图面规范（详见 `references/figure_spec.md`）

- 画布 1200×800（组件 >10 或步骤 >8 时升至 1200×900）；A 面板＝装置与物料流向（按流向分列），B 面板＝技术路线与操作序列（编号 1..N + 阶段分组）。
- 分层（SVG `<g id>`）：`layer-background/-panels/-edges/-nodes/-steps/-legend/-annotations`；文字全为 `<text>`（可编辑），无 `<image>`。
- 图元 id：`node-N1`、`edge-E1`、`step-P1`、`stage-G1`、`legend-L1`；每个 `<g>` 带 `data-kind`、`data-quote`、`data-locator`、`data-source`、`data-resolution`。
- 线型编码流向：物料蓝实线/能量橙虚线/信号紫点线/回流绿虚线/废液暗红虚线/推断灰虚线；图例只列用到的类型＋「待确认」。
- 参数只从材料抄录，写在图元下方（如 `37 °C · HRT 20 d`），不改写法、不换算、不补单位。

## 6. 证据规则（最关键）

1. `quote` 必须是某段落中的**连续逐字片段**（匹配忽略空白差异），`locator` 指向该段。
2. 校验四态：`exact`（命中）/ `missing`（找不到 → 该图元 `pending`，画虚线框，不改原文凑通过）/ `unverified`（无 quote）/ `inferred`（无原文声明的连接，灰虚线并标「顺序」）。
3. `params` 必须逐字出现在自己图元的 `quote` 里，否则报 `param_not_in_quote`。
4. 连接端点必须存在于节点集合，否则 `edge_endpoint_unknown`，该连接不画。
5. 无法核实不虚构：进 `exceptions` / `pending_human`，`result.json.status` 至少 `partial`。

## 7. 输出与 result.json

| 字段 | 内容 |
|-|-|
| `editable_source` | `figure.svg`：path/format/editable/text_editable/layers/bytes/sha256/viewBox |
| `export_artifact` | `pdf`（magic `%PDF-`、bytes、pages、vector、embedded_font、text_layer、cjk_extractable、宽高）；`png`（尽力：ok/bytes/engine/dpi，缺失则 null + 降级记录） |
| `content_map` | 路径 + 元素数 + coverage；逐元素（含 quote/locator/bbox）写在 `content_map.json` |
| `compliance_checks` | 画布、图层数、文字可编辑、id 唯一与 data-quote 数、证据覆盖率、箭头与悬空连接、PDF 容器/文本层/内嵌字体、PNG、确定性；`pass`/`failures` |
| `exceptions`/`pending_human` | 待确认图元与人工动作 |
| `counts` | nodes/edges/steps/stages/elements/with_quote/quote_rate/checks_fail/plan_source |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `errors`/`degradations`/`changes`/`uncertainty`/`runtime`/`sources` | 异常、降级、plan 覆盖记录、不确定性、耗时、来源清单 |

状态判定：无任何实体 → `insufficient_evidence`（仍出空画布与合法结果）；有 pending / 推断连接 / 检查失败 / 走兜底 → `partial`；全部命中且检查通过才 `ok`。

## 8. 异常与降级

| 情况 | 处置 |
|-|-|
| `case.json` 缺失/损坏 | 记 `case_json_invalid`，继续扫材料；无材料且无 case → `input_error` |
| PDF 无 `pdftotext` | 该来源 `pdf_no_text_tool`，只登记来源 |
| 纯图片材料 | `material_no_text`，提示需视觉/OCR |
| `plan.json` 缺失/坏/空 | 确定性兜底，`status=partial`，`uncertainty` 说明 |
| quote 找不到 | 该图元 `pending`（虚线框），进 `pending_human` |
| 无可用 TrueType 字体 | PDF 仍出矢量图形，ASCII 用 Helvetica，记降级 |
| 无 `pdftoppm`/`mutool` | 跳过 PNG（`export_artifact.png=null`），SVG/PDF 仍有效 |
| 任一步抛异常 | 捕获写 `errors`（含 trace 尾部），退出码 0 |

## 9. 自检清单

1. `python3 -B scripts/main.py --help` 退出码 0。
2. `init → check → build` 后 `/app/output` 有 SVG/PDF/PNG/content_map/result；PDF 头为 `%PDF-`。
3. SVG 可被 XML 解析器解析；`<text>` 数 > 20；无 `<image>`；`g id` 唯一且带 `data-quote`。
4. `output_contract` 键 100% 出现在 `result.json` 根级。
5. `compliance_checks.pass == true`（否则 `failures` 有说明）。
6. 同一 plan 跑两次 `figure.svg` 字节一致（确定性）。
7. 空输入 / 坏 JSON 仍写合法 partial 结果，退出码 0。

## 10. 最小调用示例（示例，非正式案例结果）

```bash
mkdir -p /tmp/demo/in
printf '## 2.1 装置\n进料储罐经蠕动泵送入厌氧膜生物反应器，恒温水浴维持 37 °C。\n\n1. 接种污泥并静置 24 h。\n' > /tmp/demo/in/method.md
python3 -B scripts/main.py init  --input /tmp/demo/in --work /tmp/demo/w --out /tmp/demo/o
python3 -B scripts/main.py build --input /tmp/demo/in --work /tmp/demo/w --out /tmp/demo/o
```

示意输出（示例，非正式案例结果）：`o/figure.svg`（1200×800、7 图层）、`o/figure.pdf`（1 页矢量、内嵌字体）、`o/content_map.json`（节点/连线/步骤各带 locator）、`o/result.json`（`status=partial`，因无 Agent plan）。

## 11. 文件清单与版本

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明：契约、工作流、证据规则、图面规范、自检 |
| `scripts/main.py` | CLI、结果契约、校验、content_map、PNG 预览、finalize |
| `scripts/extract.py` | 材料读取与"实体—连接—步骤—阶段—参数"确定性抽取 |
| `scripts/render.py` | 布局引擎、分层 SVG、原生矢量 PDF（内嵌 TrueType）、逐图元元数据 |
| `references/plan_schema.md` | `plan.json` 字段、locator 语法、校验与计数定义 |
| `references/figure_spec.md` | 版式/配色/线型/导出参数、检查项判据、失败清单 |

版本 3.0.0；三个脚本各 ≤20KB，全部标准库，无联网，不依赖 CWD。

## 12. 维护说明

- 新增图元类型：`render.py` 的 display list 加 item kind，并同步 `_svg`/`pdf` 分支与图层。
- 改字段：同步 `main.py` 的 `base()`、`checks()`、`cmap()` 与本文件第 7 节。
- 回归：同一 plan 连跑两次比对 `figure.svg` 的 sha256 与 `compliance_checks.determinism`。


## 13. 提交前自查清单（run this after every build）

| # | 检查项 | 判据 | 失败处理 |
|---:|---|---|---|
| 1 | 科学实体覆盖 | `content_map.json` 中每个实体都能在 `references` 或输入材料里找到 locator | 缺 locator 的实体标 `pending_human`，不画入图 |
| 2 | 空间/连接关系 | 每条连线两端在 `content_map.json` 有对应图元，方向与材料描述一致 | 方向不明时不画，记入 `uncertainty` |
| 3 | 数据编码 | 图中出现的关键参数/数值在 `content_map.json` 有逐字 quote | 无 quote 的数值不标注 |
| 4 | 图例标注 | `figure.svg` 的 `g#legend` 说明颜色/线型/箭头含义 | 缺图例即视为未完成，重新 build |
| 5 | 可编辑源文件 | `figure.svg` 文本为 `<text>`（非路径化），分层 `g#` 结构完整 | 路径化文本需回退到文本层 |
| 6 | 导出格式 | `figure.pdf` 以 `%PDF-` 开头、页数=1、可被 pdftotext 提取 | 导出失败时保留最小合法 PDF 并记 `degradations` |
| 7 | 可核验性 | `result.json` 含 `content_map`/`golden_standard`/`diff_report`/`version_history`/`self_check` 且 `status` 与自检一致 | 缺任一资产则重跑 finalize |
| 8 | 可复跑 | 同一输入连续两次运行，`figure.svg` 的 sha256 一致 | 不一致视为不确定布局，固定随机种子后重跑 |

自查全部通过后再提交；任何一项失败都要在 `run.log` 中写原因与回退动作。
