---
name: apparatus-technical-route-figure
description: 将实验装置、工艺流程、材料流向、技术路线材料转化为可追溯、可编辑、可复核的分层 SVG、矢量 PDF、PNG 预览与结构化证据映射。采用 init → draft.json → check → build → selfcheck 全流程，单命令入口 python3 -B scripts/main.py run；无 draft 时使用确定性兜底抽取，所有异常仍 exit 0，不编造科学数据。适用于装置图、流程图、技术路线图、材料流向图。
version: 5.0.0
---

# Apparatus & Technical Route Figure Skill

## 0. 最高优先级规则

1. **先跑基线，永不丢基线。** 进入任务后立即运行：
   `python3 -B scripts/main.py run --input /input --work /app/work --output /app/output`
   该命令内部完成 `init → build → selfcheck → finalize`。任何异常都必须写入 `result.json.errors`，进程仍必须以退出码 `0` 结束。
2. **真实读材料，不按文件名或领域标签猜内容。** 每个关键实体、连接、箭头方向、步骤编号、数值、图例，都必须来自 `/input` 中真实材料，并带逐字 quote 与 locator。材料缺失、歧义、冲突一律登记为 gap/pending/uncertainty，不编造。
3. **交付物必须是图，不是文字描述或示意截图。** 必须生成真实可编辑源文件、真实矢量导出件、可核验的内容映射，并覆盖：科学实体、空间关系、数据编码、图例标注、可编辑源文件、导出格式。
4. **不手改结构化 JSON。** `result.json`、`content_map.json` 的结构字段必须由脚本生成或由脚本覆盖。Agent 只能写 `${WORK}/draft.json`、`${WORK}/agent_review.json`，不得手工篡改脚本结构化产物。
5. **预算内先完整，再增强。** 64 次请求 / 900 秒；确定性基线通常 1–3 次命令即可完成。达到约 50 次请求或 720 秒时立即 finalize。

## 1. 输入、输出与运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 材料文件 |
| 工作目录 | `/app/work`：`index.json`、`ledger.json`、`draft.json`、`agent_review.json`、`check_report.json` 等 |
| 最终输出 | `/app/output`：`figure.svg`、`figure.pdf`、`figure.png`、`content_map.json`、`result.json`；可加 `layers.json`、`legend.json`、`figure_preview_*.png` |
| 单命令入口 | `python3 -B scripts/main.py run --input /input --work /app/work --output /app/output` |
| 兼容子命令 | `python3 -B scripts/main.py init --input /input --work /app/work --out /app/output` |
| 兼容子命令 | `python3 -B scripts/main.py check --input /input --work /app/work --out /app/output` |
| 兼容子命令 | `python3 -B scripts/main.py build --input /input --work /app/work --out /app/output` |
| 自检命令 | 若存在：`python3 -B scripts/main.py selfcheck --input /input --work /app/work --output /app/output` |
| 退出码 | 恒为 `0`。异常只写 `result.json.errors` 或 `degradations`，不得因异常退出非零 |
| 依赖 | 仅 Python 3.8+ 标准库，离线，不依赖 CWD；可选外部工具缺失即降级 |

## 2. 单命令全流程：内部应完成什么

脚本 `run` 必须依次完成：

1. **init / 盘点**
   - 扫描 `/input`，识别 `case_id` 与 `output_contract`。
   - 用扩展名 + 魔数识别材料类型，不按文件名猜内容。
   - 生成 `${WORK}/index.json` 与 `${WORK}/ledger.json`：材料来源 `S1, S2, ...`、段落 locator、可抽取文本、候选实体/连接/步骤/阶段/图表数据。
   - 立即落盘 partial `result.json`。

2. **draft 检测与确定性兜底**
   - 若 `${WORK}/draft.json` 已存在且合法，则使用 Agent draft。
   - 若无 draft，使用 init 台账执行确定性抽取，生成 substantive draft：逐字 quote、locator、节点、边、步骤、阶段、参数、图例映射，并在 `gaps`/`degradations` 中记录 `AUTO_EXTRACT`。
   - 两条路径必须输出**同一套产物与同一套 result.json 契约**。

3. **check / 校验**
   - quote 是否能在源文件定位；
   - 边端点是否存在于节点集合；
   - 连接方向是否与原文一致；
   - 步骤编号是否可逐条对照；
   - 图例颜色/线型/箭头是否与实际编码一致；
   - 字体、画布、导出路径是否可执行。

4. **build / 渲染**
   - 生成分层可编辑 SVG、矢量 PDF、PNG 预览；
   - 每个关键图元在 SVG 中带 `data-source="S#"` 与 locator；
   - 写 `content_map.json`；
   - 双回显写入 `result.json`。

5. **selfcheck / finalize**
   - 自检产物完整性、契约字段、文件魔数、证据链；
   - 写 `result.json.self_check`；
   - 无条件 finalize。

## 3. Agent-first 双路径

### 路径 A：Agent 增强路径（预算允许时使用）

1. 运行 `init` 或 `run` 获得基线。
2. 读 `${WORK}/index.json` 与 `${WORK}/ledger.json`。
3. 亲自阅读 `/input` 关键材料，尤其是 `task.md` 指定的 PDF/图表/数据段。
4. 把判断写入 `${WORK}/draft.json`。使用 `references/plan_schema.md` 规定的形状，至少包含：
   - `nodes`：实体、部件、物料、阶段、关键参数；
   - `edges`：连接、流向、顺序、循环、回流、终止；
   - `steps`：编号、主序列、并行支路、循环、终止条件；
   - `stages`：阶段目标、输入、输出、方法手段、里程碑；
   - `legend`：颜色、线型、箭头、符号与实际编码映射；
   - 每个 node/edge/step/param 必须有 `quote`、`locator`、`source`、`resolution`；
   - `resolution` 只能为 `exact` / `inferred` / `pending` / `unverified`。
5. 运行 `check`，修正后运行 `build`。
6. 写 `${WORK}/agent_review.json`：逐条记录 `claim_id → verified/rejected/reason`，以及 `script_fixes`、`differences_from_baseline`、`corrections`。
7. 重跑 `python3 -B scripts/main.py run --input /input --work /app/work --output /app/output`，让脚本把 Agent draft 合并进正式产物。

### 路径 B：确定性兜底路径（无 draft 或预算不够）

- 直接运行：
  `python3 -B scripts/main.py run --input /input --work /app/work --output /app/output`
- 脚本使用 init 台账做确定性抽取，生成实质工作稿，而不是空骨架。
- 在 `result.json.gaps` / `result.json.degradations` 中诚实记录 `AUTO_EXTRACT`，不得伪装为 Agent 核验。
- 产物仍是完整 SVG/PDF/PNG/content_map/result.json。

### 两条路径的共同要求

- 禁止生成空图充数；即使材料很少，也要生成能反映已识别实体和限制的空/最小图，并把缺失写清楚。
- 禁止因 Agent 未核验就不生成兜底产物。
- 禁止移除脚本自动抽取的 evidence；只有当 Agent 提供了 verified 替换时才可覆盖。

## 4. 证据链与 locator 规范

- source_id：`S1, S2, ...`，按输入材料清单编号。
- locator 示例：`S1 p3 ¶12` 或 `S2#row7` 或 `S3 §Methods`。
- 每个关键数字/论断必须带 `[S#]` 来源与 `文件#行号/段落号` locator。
- 任何数值必须逐字出现在其 quote 中；不得从图表标签或文件名推断。
- 无法解析的扫描件/图片：登记 `material_no_text`，不 OCR，不猜内容。
- PDF 解析优先使用 `pdftotext`；若运行时约定指定 `pdf-text-tool`，则使用该工具。
- 中英文自适应：中文图元保留原文中文，英文材料保留原文术语，不擅自翻译关键名词。

## 5. 图稿构建规则

### 5.1 图类型判断

根据 task 与材料自动选择一种或混合：
- 装置结构图：部件、接口、装配关系；
- 流程图：主序列、并行、循环、回流、终止；
- 材料流向图：物料/能量/信息流向、分流、合流、废料出口；
- 技术路线图：阶段、里程碑、输入输出、依赖顺序。

### 5.2 布局与编码

- 流向默认左→右或上→下；回流/循环用清晰回路，避免交叉。
- 分流/合流必须标注节点，不画断头箭头。
- 同类部件区分：用编号、位置、接口标签，不只写“泵”“阀”。
- 图例必须与图中实际颜色、线型、箭头形状一致。
- 画布溢出时降级：缩小比例、分块，或记录 `overflow`，不能静默裁剪关键元素。
- 字体：优先嵌入 TrueType 中文字体；不可用则记录降级，不得让中文静默变成方框。

### 5.3 可编辑源文件与导出件

- `figure.svg`：分层，文本元素应可编辑；关键图元带 `data-source`/`data-locator`。
- `figure.pdf`：原生矢量，内嵌字体；内容可提取、可缩放。
- `figure.png`：真实渲染预览；工具缺失时记录 `export_artifact.png=null`，仍保留 SVG/PDF。
- `content_map.json`：映射每个图元到 source/quote/locator/type/claim_id。
- 可选 `layers.json`、`legend.json` 提升可复用性。

## 6. result.json 双回显契约

必须满足以下结构：

1. **顶层字段**：
   - `case_id`
   - 原文 `output_contract` 中的每个字段，**必须原样保留键名**，缺值填 `null`
   - `status`：`ok` / `partial` / `insufficient_evidence` / `input_error`
   - `editable_source`
   - `export_artifact`
   - `content_map`
   - `compliance_checks`
   - `sources`
   - `uncertainty`
   - `pending_human`
   - `gaps`
   - `degradations`
   - `errors`
   - `changes`
   - `self_check`
   - `agent_review`
   - `limitations`
   - `runtime`
2. **嵌套字段**：
   - `output_contract` 对象中再次包含 `case_id` 和所有原契约字段；
   - 即契约字段在顶层与 `output_contract` 中各出现一次。

`status` 判定：
- 无实体可用：`insufficient_evidence`
- 有 pending/inferred/降级/异常但已交付：`partial`
- 全部关键实体可回溯、检查通过：`ok`
- 输入损坏：`input_error`

## 7. 自检清单

脚本应执行，Agent 也应最终核对：

- [ ] `figure.svg`、`figure.pdf`、`figure.png` 存在且非空；
- [ ] PDF 魔数为 `%PDF-`；SVG 可解析并含 `<text>`；
- [ ] 每个关键节点/边/步骤/数字有 quote 与 locator；
- [ ] 边端点存在，方向与原文一致；
- [ ] 步骤编号可逐条对照原文；
- [ ] 图例与图面实际编码一致；
- [ ] `result.json` 顶层与 `output_contract` 双回显；
- [ ] `case_id` 正确；
- [ ] gaps / pending_human / uncertainty / degradations 非空问题已诚实登记；
- [ ] 未生成伪评分、伪金标准、伪 benchmark；
- [ ] 退出码为 0。

自检结果写入 `result.json.self_check`。不得用自评分数冒充平台评分。

## 8. 异常处理与预算

- 所有异常：捕获后写入 `errors` 或 `degradations`，继续保存 partial 产物，finalize。
- `case.json` 缺失：记录 `case_json_invalid`，继续扫描材料。
- 无任何材料：`status=input_error`，仍写最小合法 `result.json`。
- PDF 无文本层：记录 `pdf_no_text_tool`，继续其他材料。
- 字体缺失：矢量 PDF 降级，记录 `font_missing`。
- PNG/PDF 渲染工具不可用：导出件缺失项置 `null`，记录 `export_failed`，SVG 仍保留。
- 时间/请求预算：基线完成后逐步增强；约 50 次请求或 720 秒时 finalize。
- 最终无法写出 JSON 时，至少写出：
  `{"case_id":"unknown","status":"input_error"}`

## 9. 生态与复用

必须依赖以下资源，且路径相对 `/skills/weekly-skill` 有效：

- `scripts/main.py`：流程编排、dedupe、双回显、finalize、selfcheck；
- `scripts/extract.py`：确定性抽取、quote/locator、候选实体/连接/步骤；
- `scripts/render.py`：SVG/PDF/PNG 渲染、字体嵌入、导出检查；
- `references/plan_schema.md`：`draft.json` 数据结构与字段说明；
- `references/figure_spec.md`：图层、图元、配色、线型、布局、导出参数；
- `SELFTEST.md`：自检清单、预期输出、失败示例；
- `environment/resources.yaml`：预装依赖与运行时说明；
- `references/guide.md`：`draft.json` 形状与 Agent 工作流说明。

所有资源应为 UTF-8 文本文件，总量不超过 2 MB，单文件不超过 500 KB，文件数不超过 50。运行时不联网，不依赖未说明个人文件。

## 10. 禁止事项

1. 禁止只输出文字描述或把截图当图稿。
2. 禁止编造设备、连接、数值、引用、字体、导出结果。
3. 禁止为了通过 check 修改 quote，使原文不匹配。
4. 禁止手改结构化 JSON。
5. 禁止生成自评分数/假装平台基准成绩。
6. 禁止删除 baseline 产物或遗漏契约字段。
7. 禁止在缺材料时补充“看起来合理”的连接。
8. 禁止在预算未结束时提前退化为空图，除非材料确无可用实体。