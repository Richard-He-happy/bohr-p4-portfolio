---
name: scientific-graphical-abstract
description: "Build a single-page, editable, evidence-traced graphical abstract or source-bound scientific figure from real input materials, delivering layered SVG + vector PDF + PNG preview + content_map + compliance checks. Use for graphical abstract, TOC figure, mechanism/pipeline summary figure, or a figure edit that must stay editable and traceable to source text. The Harness Agent must personally parse, derive and verify all scientific content; scripts are only layout, validation and render tools."
version: 2.0.0
---

# Scientific Graphical Abstract（Agent 主导型）

## 0. 一句话用途与铁律

本 Skill 让 Harness Agent 从 `/input` 的真实科研材料中提取实体、关系、数据与图面约束，亲自完成一张单页、可编辑、可复核的图形摘要或指定科研图编辑，交付分层 SVG、真实矢量 PDF、PNG 预览、来源映射、合规检查与 `result.json`。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写和制作。** 不能把脚本骨架、空模板、fallback 结果或未经你核验的自动排版直接当成品。你必须核对每个关键实体、关系、数字、单位、引用和输出契约字段；不确定的要进入 `pending_human`；缺失或矛盾要显式标出，不得编造。

## 1. 适用范围与边界

做：
- 从材料中抽取研究问题、方法路线、核心结果、结论/意义，形成 `problem → method → results → implication` 的单页图形摘要。
- 按组织方 `organizer_workorder` 的具体要求，完成 source-bound drawing workorder；若题目要求编辑某个已有 figure/chart（如 figure03 或真实图表），必须在默认图形摘要流程上加入对应来源图、需要保留的原始结构、需要改变的数据映射或图元。
- 输出可继续编辑的 SVG/PDF 源文件，并提供 PNG/PDF 渲染预览。
- 建立 `element_id → panel/role/text/svg_id/bbox → evidence{source, locator, quote, status}` 的逐元素证据映射。
- 处理 CSVs、表格型真实数据，并保留图例、单位、条件标签。

不做：
- 不写论文正文、不新做统计分析、不设计实验。
- 不按文件名、领域标签或题目摘要猜测材料内容。
- 不补造材料里没有的基因名、数值、时间点、单位、引用、分数或结论。
- 不提交无法追溯的来源引用，不把示例当正式结果。

## 2. 硬性运行时契约

- 输入目录：`/input`。必须读取 `/input/case.json`（可能缺失）与 `/input/task.md`，以及题面指定的实际材料。
- 工作目录：`/app/work`。最终产物必须落在 `/app/output`。
- Skill 安装目录：`/skills/weekly-skill`。脚本用绝对路径调用。
- 产出 `result.json`，必须包含原 `case.json` 中 `output_contract` 的全部字段，键名不改，且包含 `case_id`。
- 可编辑图稿（SVG）必须额外给出真实渲染的 PDF 与 PNG 预览；PDF 为单页、文字可选中。
- 预算：64 次模型请求、900 秒、单次响应 16384 tokens 含推理。必须优先完成最高权重交付物，尽早落盘 honest partial，再增量改进。
- 不联网，不依赖当前目录，使用标准库与平台预装工具；只引用包内真实存在的 `scripts/main.py`、`scripts/draw.py`、`references/plan-schema.md`、`references/rubric-map.md`。
- 任何失败或异常都不得以非零退出码结束；捕获失败、写入 `result.json`，最终以退出码 0 完成。

## 3. 输入发现与真实材料解析

### 3.1 脚本已完成的解析

`scripts/main.py` 的 `init` 会：
- 用 `utf-8-sig` 读 `case.json`，防 BOM。
- 键名不固定时按语义取 `output_contract`、`task_instruction`、`organizer_workorder`、`formal_inputs`。
- 按魔数 + 扩展名识别材料：`%PDF` 用 `pdftotext -layout` 解析，locator 为 `p.<页> b.<块>`；可打印文本记录为 `para.<n>`；CSV 按行。
- 打印材料清单、段落/页码 locator、workorder 摘要、contract 字段数；写出 `/app/work/index.json` 与 partial `result.json`。

你必须先运行 `init`，阅读其摘要，不要凭文件名或标题猜内容。

### 3.2 Agent 必须亲自做的真实性解析

即使 `init` 已抽取文本，你仍要亲自读出要使用的句子：
- 用 `show --grep "<关键词>"` 检索关键机制、实体、数值、方向。
- 用 `show --sid <材料ID> --limit 10` 查看上下文。
- 逐字复制要作为证据的原文到 `quote`，不允许改写、跨段拼接、翻译后回译。
- 对图表数据，优先读 CSV 中真实行列值；没有逐字句子但有结构化数据时，`quote` 可以写具体行列定位与数值，但必须在 `source`/`locator` 标明 CSV 行或列。

### 3.3 非 PDF/DOCX/CSV/图片的处理

- DOCX/PPTX：如果环境可用标准库 zipfile + xml 提取文本，就提取并记录；否则标 `not_parsed`。
- 图片：如果模型上下文能直接查看图片，就实际识别文字、图元、比例尺、图例；否则标 `not_parsed`，不得根据文件名猜测或补造。
- PDF 抽取不出文本：该材料标 `not_parsed`，并在 `degradations` 中提示需人工读页面；不得用标题或领域标签推断内容填入正式 quote。
- 若材料缺失或损坏：明确写 `input_error` 或 `partial`，列出缺失项。

## 4. 输出契约

`/app/output/` 下必须包含：

| 文件 | 作用 |
|-|-|
| `graphical_abstract.svg` | 分层可编辑源文件；文字是 `<text>` 节点；每个关键图元有 `id`；图层命名清晰 |
| `graphical_abstract.pdf` | 真实矢量 PDF，1 页，尺寸约 12×7.6 in，字体与文字可检查 |
| `graphical_abstract.png` | 预览位图；若渲染失败可缺失但必须记录降级原因 |
| `content_map.json` | `element_id → panel/role/text/svg_id/bbox + evidence{source,locator,quote,status}` |
| `compliance_checks.json` | 画布、字号、图层、字体、色彩、覆盖率等检查结果 |
| `result.json` | 主结果：`output_contract` 全部字段 + `case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime/reviewed_by_agent` |

`result.json` 规则：
- `output_contract` 的每个键原样保留，语义匹配到对应产物；无对应则 `null`，不删键、不改名。
- `status ∈ {ok, partial, insufficient_evidence, input_error}`。
- `sources` 记录实际材料路径、版本、可用 SHA1 或文件属性。
- `changes` 记录 baseline → final 的修改。
- `reviewed_by_agent` 记录你亲自核验了哪些内容、哪些是自动生成后保留、哪些进入 `pending_human`。

## 5. 本题专属执行流程

### 步骤 0：盘点输入与读取评分要求

- 输入：`/input/case.json`、`/input/task.md`、`/input` 下材料。
- 动作：
  - 读 `task.md`，标出 rubric 中权重最高的交付物：任务完成度、结果正确性、结果完整性、结果可核验性。
  - 读 `case.json`，提取 `output_contract` 字段清单和 `case_id`。
  - 运行：
    `python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output`
  - 阅读 `init` 输出中的材料清单、文本抽取状态、workorder 摘要、contract 字段数。
- 输出：`/app/work/index.json`、partial `result.json`，以及你脑内的“本案例最高优先级交付物清单”。
- 失败分支：若 `case.json` 缺失，递归找 `case*.json`；仍无则只用 `task.md + /input` 材料，并把缺失 contract 写入 `errors`。若 `init` 命令异常，记录异常，继续用可读文件设计最小可交付方案，绝不直接放弃。

### 步骤 1：真实解析并建立证据清单

- 输入：`init` 摘要、材料文件。
- 动作：
  - 先明确文本材料中谁是研究对象、方法、核心结果、结论。
  - 用 `show --grep` 查找关键句子：机制方向、数值、基因/蛋白名、样本、条件、单位、统计口径。
  - 抄下至少 8–20 条可引用原文片段，优先覆盖四段结构。
  - 如果材料是 CSV，打开并读取真实数据，记录行/列与数值映射。
  - 如果题目给出具体来源图 figure03 或图表编辑要求，定位“原图描述或来源数据”、“需要修改的数据映射”、“保留的结构”。
- 输出：证据候选列表；可直接先写入 `/app/work/evidence_notes.md`。
- 失败分支：找不到足够证据时，不要硬画；先进入 partial 路线：用确有的证据生成最少四段图，并标 `insufficient_evidence`。PDF 文本不可抽时，不凭标题补造，标 `degradations`。

### 步骤 2：先落盘 baseline，保留全套基线交付物

- 输入：`/app/work`、`/app/output`。
- 动作：
  - 若 `/app/work/plan.json` 不存在，为了让全套交付物尽早存在，运行：
    `python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --output /app/output`
    这会使用确定性 fallback 生成 baseline。
  - 若 `/app/work/plan.json` 已存在，先运行 `check` 再运行 `build`，产出 baseline。
  - 将 baseline 产物复制到 `/app/work/baseline/`：至少复制 `graphical_abstract.svg`、`graphical_abstract.pdf`、`graphical_abstract.png`（如生成）、`content_map.json`、`compliance_checks.json`、`result.json`。
- 输出：`/app/output` 下已有完整契约文件；`/app/work/baseline` 保留原始基线。
- 失败分支：若 `build` 异常，记录 traceback 到 `errors`，尝试修复 `work/plan.json` 后重跑一次；仍失败则保留 partial `result.json`，并尽可能用手工构建最小 SVG + PDF 作为 honest partial。

### 步骤 3：Agent 亲自审查 baseline，构建真实可验证的 plan

- 输入：`/app/output` 的 baseline 图稿、`content_map.json`、证据清单、`references/plan-schema.md`、`references/rubric-map.md`。
- 动作：
  - 打开 baseline SVG 的文本/PDF 预览，逐项核对：四段是否齐全；实体关系是否对；数值是否在 quote 中；图例、单位、条件是否覆盖。
  - 依据证据与材料，写 `/app/work/plan.json`。每项必须是你能负责的 scientific judgement。
  - 使用 `role`：`problem`、`method`、`results`、`implication`；2–4 个 panel，通常 4 个。
  - `kind` 用 `text` 或 `value`；`value` 用于大字号数字或量，并写 detail 说明条件。
  - 每个 item 必须有 `evidence`，且 `quote` 是逐字引用。
  - 若有指定图表编辑工作，扩展 plan：在 relevant panel 中写清原图结构、数据映射变化、图例与单位要求。
- 输出：`/app/work/plan.json`。
- 失败分支：若时间不够或证据不足，宁可保留 fallback baseline 并标注 `reviewed_by_agent=false`/`pending_human`，也不要伪造完整来源。

### 步骤 4：校验与终渲

- 输入：`/app/work/plan.json`。
- 动作：
  - 运行：
    `python3 /skills/weekly-skill/scripts/main.py check --input /