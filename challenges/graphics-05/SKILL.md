---
name: scientific-graphical-abstract
description: "Build a single-page, editable, evidence-traced scientific graphical abstract or source-bound figure/chart edit from actual /input materials. Delivers layered SVG, vector PDF, PNG preview, content map, compliance checks, source records and a contract-complete result.json. Use for graphical abstract, TOC figure, mechanism diagram, pipeline summary, or source-preserving figure/chart editing that requires real scientific judgement and reproducible rendering."
version: 3.0.0
---

# Scientific Graphical Abstract

## 0. 最高优先级：评委真正看重什么

本 Skill 不是“画一张好看的图”，而是稳定交付：

1. 一张单页、可编辑、可复核的图形摘要或来源图编辑。
2. 图中每个实体、关系、数值、颜色/长度/面积映射都能追到原始材料的具体位置。
3. 同一输入能稳定复现结构一致的图稿，而不是每次重排。
4. 交付可分层的可编辑源文件，并同时给出真实矢量 PDF 和 PNG 预览。
5. 所有运行、异常、证据、不确定性、修改记录都进入 `result.json`，且不破坏原 `output_contract` 字段。

评分权重排序：实际效果 > 使用增益 > 创新 > 可靠 > 生态。因此先保证内容正确、来源可核、产物完整；再用脚本化确定性布局和增量 review 证明增益；最后用文档、模板和自检说明生态价值。

## 1. 运行时契约

硬性要求：

- 输入目录：`/input`。必须真实读取：
  - `/input/case.json`
  - `/input/task.md`
  - `/input` 下所有题面指定材料，包括 PDF、CSV/TSV、DOCX/PPTX、图片等。
- 工作目录：`/app/work`。中间产物写入这里。
- 最终目录：`/app/output`。最终交付物写入这里。
- Skill 路径：`/skills/weekly-skill`。脚本用绝对路径调用：
  - `/skills/weekly-skill/scripts/main.py`
  - `/skills/weekly-skill/scripts/draw.py`
- 最终必须写 `/app/output/result.json`。
- `result.json` 必须包含原 `case.json` 中 `output_contract` 的全部字段，键名不改；缺失时写 `null`，不得删键。
- `result.json` 顶层与 `output_contract` 嵌套对象中要各回显一次契约字段；同时包含 `case_id`。
- 可编辑图稿必须至少有 SVG；SVG 之外必须有真实渲染的 PDF 和 PNG 预览。PDF 为单页、文字可选中。
- 运行失败、材料缺失、导出失败、字体缺失等，全部记录为降级或 partial；进程始终以退出码 0 结束。
- 不得联网；不依赖未声明的个人文件；优先使用 Python 标准库与平台预装工具。
- 不生成或引用虚假基准分、golden_standard、自评高分；只记录平台真实可验证的运行证据。

## 2. Skill 的单一入口

### 2.1 首选单命令全流程

Harness Agent 应优先执行：

`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部必须完成：

- `init`：盘点材料、分配 `source_id`、抽取候选实体/关系/数值/图面约束、生成初步台账。
- `build`：
  - 若 `/app/work/draft.json` 存在，按 Agent draft 渲染。
  - 若不存在，使用 init 台账做确定性抽取与排版，生成 auto draft。
- `selfcheck`：校验产物文件、SVG/PDF/PNG、`result.json` 合法性、契约字段回显、来源映射可读性。

如果 `run` 在当前版本不可用，Agent 必须立即切换为下面的分步 fallback，不得因此失败退出。

### 2.2 分步 fallback

按顺序执行：

`python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --output /app/output`

阅读 init 输出与 `/app/work/index.json`。

需要检索材料时：

`python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --grep "<关键词>"`
`python3 /skills/weekly-skill/scripts/main.py show --input /input --work /app/work --sid <source_id> --limit 10`

随后人工核验并写入 draft，再执行：

`python3 /skills/weekly-skill/scripts/main.py check --draft /app/work/draft.json --input /input --work /app/work --output /app/output`
`python3 /skills/weekly-skill/scripts/main.py build --draft /app/work/draft.json --input /input --work /app/work --output /app/output`
`python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --output /app/output`

若脚本 flag 有差异，以 `python3 /skills/weekly-skill/scripts/main.py --help` 为准，但不得放弃 check/build/selfcheck 对应的能力。

## 3. 输入发现与真实材料解析

### 3.1 必须真实读取

不得依据文件名、领域标签、题面摘要猜测材料内容。所有关键引用必须来自实际读取：

- PDF：用 `pdftotext -layout` 抽取；locator 写 `p.<页> b.<块>` 或 `p.<页> para.<n>`。
- CSV/TSV：真实读取行列；locator 写 `CSV:<文件名> rows <起>-<止> col <列名/列号>`。
- DOCX/PPTX：若可用标准库 `zipfile + xml` 提取，提取文本；否则标记 `not_parsed`。
- 图片：若模型上下文可查看，逐项识别文字、箭头、颜色、图例、比例尺；否则标记 `not_parsed`，不得补造。
- PDF 文本抽取失败或显示为扫描件：该材料标 `not_parsed`，写入 `degradations`。

### 3.2 材料清单台账

`init` 后，`/app/work/index.json` 应至少包含：

`case_id`、`input_files`、`source_id`、`file_type`、`parse_status`、`locator_prefix`、`contract_fields`、`workorder_summary`、`candidate_elements`。

Agent 必须在脑内或 notes 中建立：

- 研究对象实体：基因/蛋白/细胞/材料/器件/样本等。
- 关系：激活/抑制/结合/转化/流程顺序/空间位置。
- 数据：真实数值、单位、条件、样本量或统计口径。
- 图面约束：面板要求、来源图、目标尺寸、颜色或编码要求。

## 4. Agent-first 双路径

### 4.1 有 draft 的 Agent 路径

Agent 应亲自读材料，产出 `/app/work/draft.json`。draft 是科学判断的核心，不是对 init 文本的复制。

`draft.json` 推荐结构：

`{"case_id":"...", "layout":{"canvas":"12x7.6in","panel_order":["problem","method","results","implication"]}, "panels":[{"role":"problem","title":"...","items":[{"element_id":"P1","kind":"text","text":"...","value":null,"visual":{"x":0,"y":0,"w":0,"h":0},"evidence":{"source_id":"S1","locator":"p.3 b.2","quote":"逐字原文","status":"verified"}}]}], "visual_mapping":{"numeric":"length","nominal":"hue","colorblind_safe":true}, "uncertainty":[], "pending_human":[]}`

每个 item 必须满足：

- `role` 属于 `problem`、`method`、`results`、`implication`。
- `kind` 为 `text` 或 `value`。
- `value` 用于大字号数字或数量，必须有单位、条件、比较基准。
- `evidence.quote` 必须是逐字引用；结构化数据可写具体行列定位与真实数值，但需标明 `locator`。
- 不确定的实体、方向、数值、单位进入 `uncertainty` 或 `pending_human`。

Agent 写完 draft 后，必须运行 `check`，检查 schema、证据字段、缺失来源、面板顺序和数值单位。

### 4.2 无 draft 的确定性兜底

如果 Agent 未写 `/app/work/draft.json`，`build` 必须使用 init 台账生成确定性 auto draft，并完成同一套产物。

自动兜底必须：

- 仅使用 init 已抽取的候选实体、关系、数值和约束。
- 使用稳定顺序：source_id 升序、面板 role 固定顺序、候选置信度稳定排序。
- 为每个自动生成的关键元素写逐字 `quote` 与 `locator`。
- 在 `result.json` 中记录：
  - `"build_mode": "deterministic_auto"`
  - `"reviewed_by_agent": false`
  - `"degradations": ["AUTO_EXTRACT: 未经过 Agent 科学审核"]`
- 若某 panel 证据不足，必须写 `"status": "partial"` 或 `"insufficient_evidence"`，不得伪装完整。

两条路径产出同一套文件与同一份 `result.json` 契约结构。

## 5. 本题专属流程

### 5.1 步骤 0：盘点与先落 baseline

先运行 `run` 或 `init`。

若 `/app/output` 还没有完整产物，立即执行 build 生成一份 baseline，即使它可能是 auto fallback。把 baseline 复制到：

`/app/work/baseline/`

至少保留：
`graphical_abstract.svg`
`graphical_abstract.pdf`
`graphical_abstract.png`（若生成）
`content_map.json`
`compliance_checks.json`
`result.json`

之后所有改进都是 baseline → final 的增量变化，并写入 `result.json.changes`。

### 5.2 步骤 1：提取四段科学内容

必须覆盖：

- Research problem / gap / question
- Method / approach / design
- Core results / data
- Implication / conclusion / meaning

每段至少 2 个可核验点。缺失时不得编造：

- 找不到核心结果数据：`status = partial`
- 结论无法从材料读出：写 `pending_human`
- 结果与结论冲突：记录冲突，不强行统一

### 5.3 步骤 2：图面与视觉映射

布局顺序固定：`problem → method → results → implication`。

视觉通道规则：

- 数值优先用长度、面积、位置；颜色仅作为辅助编码。
- 名义类别用颜色加形状或纹理，保证黑白打印可区分。
- 避免红绿单独编码；色觉安全。
- 图例必须显示单位、条件、分组含义。
- 有比例尺、时间点、统计显著性、样本量等，能写就写。

SVG 要求：

- 所有文字为 `<text>` 节点，不转曲线。
- 每个关键图元有 `id`，格式建议：`<panel>_<role>_<element>`，如 `P1_problem_gap`。
- 每个关键图元带 `data-evidence`，格式：`S1|p.3 b.2`。
- 图层命名清晰，如 `background`、`panels`、`arrows`、`text`、`legend`、`annotations`。
- 关键数字必须有来源；不可溯源数字不得出现在主图中，只能进 `pending_human` 或删除。

### 5.4 步骤 3：来源图或图表编辑

若题面要求编辑已有 figure/chart，例如 figure03 或真实数据图表，必须在普通图形摘要流程上增加：

1. 定位原图/原表/来源描述。
2. 保留原图拓扑结构、面板顺序、图例位置，除非任务要求改变。
3. 找出需要修改的数据映射或图元：
   - 旧值、新值、变化理由、来源引用。
4. 记录 delta：
   - 文件 `figure_edit_delta.json`
   - 内容包含 `element_id`、`change_type`、`old_value`、`new_value`、`evidence`、`status`。
5. 输出仍采用同一套 SVG/PDF/PNG 和 `content_map.json`。

图表类材料必须读真实行列值，不按 chart title 或颜色猜测。

## 6. 输出契约

`/app/output` 下必须包含：

| 文件 | 要求 |
|-|-|
| `graphical_abstract.svg` | 分层可编辑源文件；文字为 `<text>`；关键图元有 id 与 evidence 标注 |
| `graphical_abstract.pdf` | 真实矢量 PDF，单页，约 12×7.6 in，文字可选中 |
| `graphical_abstract.png` | PNG 预览；若渲染失败可缺失但必须记录降级 |
| `content_map.json` | 逐元素映射：`element_id → panel/role/text/svg_id + evidence{source,locator,quote,status}` |
| `compliance_checks.json` | 画布、字号、图层、字体、色彩、覆盖率、导出检查 |
| `result.json` | 主结果，见下 |
| 可选 `figure_edit_delta.json` | 来源图或图表编辑的变更记录 |

若原 `output_contract` 要求不同文件名，必须按语义映射到实际文件名，并在 `result.json` 中写清：

`"derived_artifacts": {"<contract_field>": "<relative or absolute output path>"}`

### 6.1 `result.json` 规则

必须包含：

- `case_id`
- `status`：`ok`、`partial`、`insufficient_evidence`、`input_error`
- `output_contract`：原契约字段全部键，嵌套对象
- 每个原契约字段也在顶层回显一次
- `sources`：实际材料路径、类型、SHA1 或文件属性、解析状态、版本
- `uncertainty`：低/中/高置信度项
- `pending_human`：需要人工判断项
- `errors`：运行或解析错误
- `degradations`：降级项，如字体缺失、PDF 溢出、auto draft、not_parsed
- `changes`：baseline → final 的具体修改
- `runtime`：本次运行耗时、请求次数、构建模式、是否 agent reviewed
- `reviewed_by_agent`：true/false；若 true，写清核验了哪些内容
- `build_mode`：`agent_draft` 或 `deterministic_auto`
- `derived_artifacts`：契约字段到实际文件路径的映射

`result.json` 顶层不要用非契约字段覆盖契约字段；如契约字段名与状态字段冲突，以契约字段写入 `output_contract`，顶层保留状态字段，并在 `derived_artifacts` 说明。

### 6.2 契约字段双回显示例

若原契约有 `editable_source`、`exported_image`、`source_records`，则 `result.json` 中应有：

`"editable_source":"/app/output/graphical_abstract.svg"`  
`"exported_image":"/app/output/graphical_abstract.png"`  
`"source_records":"/app/output/content_map.json"`  
`"output_contract":{"editable_source":"/app/output/graphical_abstract.svg","exported_image":"/app/output/graphical_abstract.png","source_records":"/app/output/content_map.json"}`

不要只放嵌套或缺顶层。

## 7. 可靠性与异常处理

### 7.1 常见异常策略

- `case.json` 缺失：递归找 `/input/case*.json`；仍无则只用 `task.md + /input` 材料，并把缺失契约写入 `errors`。
- PDF 无文本：标 `not_parsed`，不凭标题补造；若图片可见可人工识别，否则 `input_error` 或 `partial`。
- 材料矛盾：记录矛盾双方引用，`uncertainty=high`；不擅自选一个。
- 字体缺失：使用系统可用的 sans-serif fallback；SVG 保留 text；PDF 若必须可检查文字，优先嵌字体，失败则记录。
- 画布溢出：减少面板 padding、缩小字号但不得低于 7pt；仍溢出则拆为图注，并记录。
- PNG 渲染失败：保留 SVG 和 PDF，PNG 可缺失但必须在 `degradations` 说明。
- PDF 导出失败：保留 SVG，记录导出错误；状态不应无证据标 ok。
- 脚本异常：捕获 traceback，写入 `errors`，尝试一次修复；无法修复则交付 partial；永不非零退出。

### 7.2 自检清单

`selfcheck` 必须核验：

- `/app/output/result.json` 是否合法 JSON。
- `case_id` 是否与输入一致。
- 原 `output_contract` 字段是否全部存在，且顶层与嵌套都有。
- SVG 是否存在且含 `<svg>` 与多个 `<text>`。
- PDF 是否存在且单页。
- PNG 是否存在且非空。
- `content_map.json` 中关键元素是否有 `source`、`locator`、`quote`、`status`。
- 所有关键数值是否都有来源。
- `compliance_checks.json` 是否包含画布、字号、颜色、字体、图层检查。
- 若 `build_mode=deterministic_auto`，是否已标记 AUTO_EXTRACT 与 `reviewed_by_agent=false`。

任何一项不过，修到过或写入降级，不得假装通过。

## 8. 使用增益与创新证据

### 8.1 使用增益证据

- 始终保留 `/app/work/baseline`。
- `result.json.changes` 写清 baseline → final 的改动，避免“全盘重画”。
- `runtime` 写实际耗时与请求数，不写虚构对比。
- `content_map.json` 的可用性使复核者无需重跑即可查证元素来源。
- 同样输入重复运行应产生相同 panel 顺序、相同视觉编码、相同文件结构；布局可微调但不得产生另一套科学内容。

### 8.2 创新证据

- `source-bound drawing`：每个图元绑定来源引用，不是“看起来合理”。
- `deterministic auto fallback`：无 Agent draft 时也能产出实质 baseline，再增量改进。
- `delta editing`：来源图只改必要元素，记录旧值→新值，保留其他结构。
- `visual mapping rules`：数值、单位、条件、色盲安全、灰度打印均可检查。
- `compliance_checks.json`：把“图面可复核”从主观说法变成可检查项。

## 9. 文档、生态与最小调用示例

### 9.1 包内资源

Skill 包应包含：

- `SKILL.md`：本文件。
- `references/plan-schema.md`：draft/plan schema。
- `references/rubric-map.md`：rubric 到产物/字段的映射。
- `references/guide.md`：draft.json 形状、工作流与增量改进说明。
- `SELFTEST.md`：自检清单与预期输出示例。
- `environment/resources.yaml`：预装依赖和资源声明。
- `scripts/main.py`、`scripts/draw.py`：实际运行脚本。

若缺少上述可选文档，Skill 仍应能运行，但 Agent 不得因此降低产出标准。

### 9.2 最小调用示例

输入 `/input/case.json` 与材料后，Harness Agent 调用：

`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`

或分步 init → 写 draft → check → build → selfcheck。

示意输出不是正式答案，应标注为示例。正式输出必须来自真实 `/input`。

## 10. 预算控制

- 模型请求预算：64 次，900 秒，单次响应含推理 16384 tokens。
- 优先使用单命令 `run`，1 次完成 baseline。
- 再用 3–8 次 `show --grep` 和材料阅读核验关键实体与数值。
- 剩余请求用于写 `draft.json`、`agent_review.json` 和修复 check 问题。
- 接近预算时立即收尾：保证 `result.json` 合法、契约字段齐全、状态诚实。
- 宁可交付 `partial` 也不编造科学数据或来源。

## 11. 禁止事项

1. 不手改 `content_map.json`、`compliance_checks.json`、`result.json` 的结构字段；如需修复，用脚本函数重算并记录。
2. 不凭文件名、领域标签、标题或摘要补造来源内容。
3. 不生成伪造的 `golden_standard`、自评分数、平台对比分数或 benchmark 分数。
4. 不把 auto fallback 标为 Agent 已审核。
5. 不把示例产物当正式结果。
6. 不在材料缺失时仍标 `ok`。
7. 不让任何异常以非零退出码结束。
8. 不输出纯位图作为唯一可编辑源文件。
9. 不删除 `output_contract` 字段。
10. 不给无法追踪的数值或实体上正式图面；无法判断则写 pending。