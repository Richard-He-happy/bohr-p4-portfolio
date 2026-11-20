---
name: reading-02-scientific-figure-parser
description: 科研图表与表格解析 Skill：从原图、原表、PDF 与 material.json 提取轴类型/刻度/单位、图例系列、数据点、趋势、误差线、显著性、比例尺与子图编号，输出可复核的 JSON/CSV/交付稿，逐条保留证据定位与不确定性；支持 Agent 判读与确定性兜底双路径。
version: 2.0.0
license: MIT
---

# 科研图表解析：从原图/原表到可复核结构化结果

本 Skill 的任务是把给定科研材料中的**真实图片、原表、PDF/JSON/CSV**读成可复核的结构化结果，不是写一段“看起来合理”的总结。每个关键数字、单位、趋势和结论必须能回到具体来源位置。

## 0. 最高优先级：单命令全流程 + 诚实交付

进入任务后，先运行：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

如果相对路径不可用，则尝试：

`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`

这个命令内部依次执行 `init → build → selfcheck`，会先生成全套基线交付物。即使异常也要保证最终 `result.json` 合法生成并以 `exit 0` 结束；不能崩溃后无输出。

必须遵守：

1. 只依据 `/input` 下**实际文件内容**完成任务，不依据文件名、旧领域标签、论文标题或外部知识补造数据。
2. 没有读取依据的数值、轴、单位、序列、误差线、显著性、比例尺，一律标记为缺失或不确定。
3. 先保存基线，再增量改进。脚本生成的结构化结果可以核验、补全、追加，但不能删除契约字段。
4. 不提交预制答案，不伪造 benchmark/golden/自评分。平台负责实际对照；本 Skill 只提交可复现流程与真实产物。
5. 所有命令尽量少调用：单命令跑通基线，Agent 路径只用于真实读图、核验和文本成稿；接近预算时立即收尾。

## 1. 工作流：init → Agent 判读/确定性兜底 → build → selfcheck

### 1.1 init：材料盘点与任务边界

`scripts/main.py init` 必须完成：

- 读取 `/input/case.json`、`/input/task.md`，保留 `output_contract` 原字段和 `case_id`。
- 扫描 `/input` 下全部材料：图片、PDF、CSV、XLSX、DOCX、JSON、文本。
- 给每个实际材料分配唯一 `source_id`，统一使用 `S1`、`S2`、`S3` 等。
- 读取 `organizer_supplied_scope`，明确：
  - `required_actual_image_files`：这些是必须逐一解析的真实图片。
  - `required_literal_source_table_ids`：这些是必须逐一提取的字面表格。
  - `unprovided_objects`：只出现在论文文字/图注但未给像素的对象，不是必做任务；登记为缺口，不构造数据。
- 生成 `/app/work/ledger.json`，记录来源清单、文件路径、材料版本、候选对象、对象类型、是否必需、冲突分组。
- 生成 `/app/work/extraction_plan.json`，列出每个必需对象的解析目标、可用证据、缺口和疑点。

### 1.2 Agent 路径：先读原文，再写判断

Agent 必须真实查看材料：

- 图片：打开实际 PNG/JPG/PDF 页面，观察坐标轴、刻度、单位、图例、系列、误差线、显著性标记、比例尺、子图编号。
- 表格：读取实际 PDF/JSON/CSV/XLSX 中的字面表头、行、列、单位、分组、条件、脚注。
- 文字：读取任务卡要求、图注、表注、正文引用。

随后把判断写入：

`/app/work/draft.json`

`draft.json` 的形状应遵循 `references/schema.md`。核心内容包括每个 `source_id` 的对象类型、必需范围、轴解析、图例系列、数据点、表格行、证据引用与不确定性。

对图片，优先记录：

- 面板/子图编号：如 `A`、`B`、`C` 或 `single`。
- 坐标轴类型：线性/对数/双轴；刻度起点、终点、间隔；单位；量纲；轴标题原文。
- 图例与系列映射：标签、颜色、线型、标记符号、对应关系。
- 数据点/趋势：只记录图中能直接读出或可合理近似的点；不能把曲线轨迹当作精确数据。
- 误差线：类型、方向、长度、对应序列；图中未报告则写 `not_reported`。
- 显著性标记：`*`、`**`、`ns`、字母组标记等，保留原文位置。
- 比例尺：数字、单位、像素/物理长度；用于显微图像或照片。
- 非定量对象：照片、示意图没有数量轴时，明确 `quantitative_axes: NA`，不要强行造数值。
- 像素读数：凡是基于像素估计的值，都要标 `approximate: true`、误差范围和方法。

对表格，优先记录：

- 表头逐字原文。
- 行标签、列标签、分组条件、单位、注释、脚注。
- 数值逐字保留，不因物理直觉交换列、改单位或补单位。
- 表中未报告的单位写 `unit: null`，并说明“不得视为无量纲”。

如果 Agent 未写 `draft.json`，build 会走确定性兜底路径。

### 1.3 确定性兜底路径

如果没有 `draft.json`，`scripts/main.py build` 必须基于 `/app/work/ledger.json` 和 `/app/work/extraction_plan.json` 做确定性提取：

- 对表格：逐字提取表格内容，保留原文 quote 和定位。
- 对图片：只提取图片元数据、文件名、可机读的面板信息；无法视觉判读的轴、点、图例一律不硬造。
- 每条自动提取结论必须带 `quote` 和 `locator`。
- 必须把 `extraction_mode: AUTO_EXTRACT` 写入 `result.json`，并在 `degradations` 中诚实说明“未经过 Agent 视觉核验，图片像素级读数可能缺失”。
- 自动提取不能把图片文件名、领域标签或图注当作图中的真实数据。

两条路径最终必须产出**同一套交付物和同一份 `result.json` 契约**。

### 1.4 build：校验、合并、渲染全部产物

`scripts/main.py build` 必须：

- 若存在 `/app/work/draft.json`，校验其结构，并与确定性提取合并。
- 若 Agent 判断与脚本提取冲突，不静默覆盖；写入 `conflicts.json`，在 `result.json` 中登记。
- 渲染至少以下产物：
  - `/app/output/result.json`
  - `/app/output/figure_structure.json`
  - `/app/output/digitized_series.csv`
  - `/app/output/tables.json`
  - `/app/output/tables/<id>.csv`（每个必需表一个）
  - `/app/output/claims.json`
  - `/app/output/evidence_table.json`
  - `/app/output/deliverable.md`
  - `/app/output/pending_human.json`
  - `/app/output/conflicts.json`
  - `/app/output/agent_review.json`
  - `/app/output/SELFTEST.md`
- `deliverable.md` 是干净交付稿；若同时存在 `evidence_driven_draft.md`，两者内容必须不同。

### 1.5 selfcheck：契约自检与收尾

`scripts/main.py selfcheck` 必须检查：

- `/app/output/result.json` 合法。
- `result.json` 顶层与 `output_contract` 嵌套对象中，`case_id`、`status`、`result`、`claims`、`uncertainties` 都完整出现。
- `output_contract` 原字段不丢键、不改名；未知键原样保留。
- 所有 `claims` 都有 `source_id` 和 `location`。
- 所有关键数字/单位/结论在 `deliverable.md` 中有 `[S#]` 证据标记。
- 所有必需表、必需图片都有对应解析对象。
- 所有未提供对象、无法读出的量、冲突、人工复核项都进入 `gaps`/`uncertainties`/`pending_human`。
- 失败或材料异常时也必须输出 `result.json`，状态可为 `partial`、`insufficient_evidence` 或 `input_error`，并在 `errors` 中说明原因。

## 2. 输入与输出契约

### 2.1 输入

输入根目录为 `/input`。至少包含：

- `/input/case.json`
- `/input/task.md`
- `/input/` 下的实际材料，如 `artifacts/*.png`、PDF、`material.json`、CSV、XLSX、DOCX 等。

`case.json` 中的 `output_contract` 是回填基准，不能丢弃。

### 2.2 result.json 必须满足双回显

`result.json` 顶层必须包含：

- `case_id`: 原样保留输入 `output_contract.case_id`。
- `status`: `answered | partial | insufficient_evidence | input_error`。
- `result`: 结构化主结果；按任务要求保留字段。
- `claims`: 每条关键结论及其证据定位。
- `uncertainties`: 未报告、无法判断、冲突、人工复核项。
- `sources`: 来源清单，至少包含 `source_id`、`file`、`object_type`、`scope`。
- `errors`: 运行错误与可接管位置。
- `degradations`: 自动提取、像素近似、材料缺失、无法核验等降级说明。
- `pending_human`: 需要人工复核的项。
- `extraction_mode`: `AGENT_ASSISTED` 或 `AUTO_EXTRACT`。
- `method_evidence`: 记录本流程使用了哪些方法：如 `ledger_inventory`、`deterministic_table_extraction`、`agent_visual_review`、`contract_selfcheck`。

同时，`result.json` 中必须含有：

`"output_contract": { "case_id": ..., "status": ..., "result": ..., "claims": ..., "uncertainties": ... }`

其中 `output_contract` 的 `case_id`、`status`、`result`、`claims`、`uncertainties` 与顶层对应字段一致。

### 2.3 claims 字段

每条 claim 建议包含：

- `claim_id`: 如 `C001`、`C002`。
- `kind`: 如 `axis_type`、`unit`、`tick`、`legend_series`、`data_point`、`trend`、`error_bar`、`significance`、`scale_bar`、`subfigure`、`table_cell`、`omission`、`conflict`。
- `text`: 结论原文。
- `source_id`: 如 `S1`。
- `location`: 定位，格式尽量统一：
  - 图片：`S1#panel=A#x_axis=bottom#tick=0,2,4,6`
  - 表格：`S2#page=3#table=C01-P003#row=2#column=Tensile_Strength`
  - PDF：`S3#page=4#paragraph=2`
- `quote`: 原文短引文；无法引用时说明原因。
- `strength`: `direct_read | inferred | approximate | unknown`。
- `support_scope`: `single_source | cross_source_confirmed | unresolved_conflict`。

### 2.4 uncertainties 字段

每条 uncertainty 建议包含：

- `item`: 不确定项名称。
- `status`: `not_reported | cannot_determine | conflict | pending_human | approximate`。
- `reason`: 原因。
- `source_id`/`location`: 相关位置。
- `recommended_action`: 建议人工复核方式。

## 3. 实际任务边界：organizer_supplied_scope v2

组织方已明确：必做对象是每例给出的**1张实际图片**及**全部原表**。处理时必须：

1. 只把 `required_actual_image_files` 中的图片作为像素解析对象。
2. 只把 `required_literal_source_table_ids` 中的表作为字面表解析对象。
3. `unprovided_objects` 中只出现在论文文字/图注但未给像素的对象，记入 `gaps` 和 `unprovided_objects`；不要构造点、轴、误差线或原数据。
4. `answered` 表示已完成所有实际给到的图片与原表的有边界解析；不要因为原论文其他未给图而把状态写成 `partial`。
5. 实际已给对象中不可读的量、未报告的误差依然要明确列出，不编数值。
6. 数字和表头逐字保留；来源冲突、无法解释的单位明确记录。
7. 不能以“没有标注单位”当作“无量纲”；不能以物理直觉擅自改原表或交换列。
8. 像素读数必须标 `approximate` 和误差；图中字形不等同实际峰形。

## 4. 科研图表解析的质量标准

### 4.1 读得准

- 轴类型：线性、对数、双轴，必须写清依据。
- 刻度：起点、终点、间隔、子刻度；图中的刻度原文保留。
- 单位：区分 `mV` 与 `V`、`μm` 与 `mm`、`%` 与绝对量；没看到单位就写 `null`。
- 量级：不得把对数轴当线性轴；不得自行变更数量级。

### 4.2 提得全

必须尽量覆盖任务要求的元素：

- 坐标轴与刻度。
- 图例、系列与对应关系。
- 数据点、曲线、趋势。
- 误差线。
- 显著性标记。
- 比例尺。
- 图注与子图编号。
- 表格表头、分组、条件、单位、脚注。

不把箭头、插图、非数据元素当成数据。

### 4.3 讲得清

每条结论要明确属于：

- `direct_read`：图中直接可读。
- `inferred`：有依据的合理推断。
- `unknown`：无法确定。
- `conflict`：材料间冲突。

### 4.4 交得出

- 结构化数据必须带单位、精度和误差范围。
- 曲线提取输出 CSV；表格提取输出 JSON 和 CSV。
- 保留可复核的读取路径：来源编号 + 面板/行/列/段落定位 + 原文引用。
- 如果只能做定性描述，不要伪装成精确数值。

## 5. 常见场景与异常处理

### 5.1 正常场景

- 给定清晰图片和原表：Agent 应逐一解析，写入 `draft.json`，脚本 merge 后输出完整产品。
- 表格含单位、分组、脚注：逐字提取并保留表头层级。

### 5.2 边界场景

- 对数轴/双轴：单独标 `axis_type`，不要按线性估计点。
- 单位缺标：`unit: null`，`unit_inferred: false`；不写无量纲。
- 图例缺失或颜色难辨：记录 `legend_missing` 或 `legend_ambiguous`，不强行匹配系列。
- 曲线重叠：只提取可分辨点；重叠区域注明 `overlap` 和不确定性。
- 子图多面板：逐面板编号 `A/B/C`，不跨面板错配。

### 5.3 异常场景

- 图片截图不全/裁剪：仅解析可见部分；裁剪区域写入 `gaps`。
- 图片过曝/模糊/分辨率不足：标注 `insufficient_evidence`，不硬读。
- 无坐标刻度：不估计坐标数据；只描述可见图形元素。
- PDF 无预提取文本：脚本仍要基于 PDF 原文提取；提取失败则记录 `pdf_extraction_failed`。
- 表格 ID 找不到：在 `gaps` 中登记缺表，不伪造。
- 输入文件缺失：`status: input_error`，列出缺失路径。

## 6. 预算意识与早期保存

- 第一次 `main.py run` 应快速生成基线：`result.json`、表格、CSV、claims 等。
- Agent 增量工作只做：读图写 `draft.json` → 核验关键 claim → 改善 `deliverable.md` → 补 `pending_human.json`。
- 如果接近 `64` 次请求或 `900` 秒，立即运行 selfcheck，确保 `result.json` 合法。
- 不允许为了更漂亮而重跑完整流程导致预算耗尽。
- 不要用模型请求做脚本能做的事；提取表格和自检交给脚本。

## 7. Agent 修改边界

- 结构化 JSON 的键结构由脚本管理；Agent 不手工改写 `claims.json`、`evidence_table.json`、`result.json`。
- Agent 的核验结论写入 `/app/output/agent_review.json`，逐条记录：
  - `claim_id`
  - `review`: `verified | rejected | corrected`
  - `reason`
  - `corrected_value`
  - `source_id`
  - `location`
- 若脚本抽取错误，写临时 Python 调用 `scripts/main.py` 中的函数重新计算并覆盖；不要在最终 JSON 中手改键。
- 不删除脚本基线产物；如需修正，覆盖前先备份到 `/app/work`。

## 8. 交付物清单

| 文件 | 说明 |
|-|-|
| `/app/output/result.json` | 最终契约文件，顶层 + `output_contract` 双回显 |
| `/app/output/figure_structure.json` | 每张必需图片的轴/单位/图例/子图/误差线/比例尺等结构 |
| `/app/output/digitized_series.csv` | 曲线/散点数据：`source_id, panel, series, x, y, x_unit, y_unit, error_type, error_value, locator, quote` |
| `/app/output/tables.json` | 所有必需表的字面表头、行、单位、条件、脚注与定位 |
| `/app/output/tables/<id>.csv` | 每张必需表的单表 CSV |
| `/app/output/claims.json` | 所有关键结论及其证据定位 |
| `/app/output/evidence_table.json` | claim 与 source/locator/quote 的可核验映射 |
| `/app/output/deliverable.md` | 人可读成稿；每个关键数字/论断带 `[S#]` |
| `/app/output/pending_human.json` | 人工复核项 |
| `/app/output/conflicts.json` | 来源冲突、图与表冲突、Agent/脚本冲突 |
| `/app/output/agent_review.json` | Agent 核验记录与脚本修正记录 |
| `/app/output/SELFTEST.md` | 自检清单、通过项、预期输出说明 |

## 9. 生态与复用

- 脚本只依赖 Python 标准库；目标运行环境为 `python3 >= 3.8`，离线可用。
- 所有包内文件均为 UTF-8 文本；脚本路径从 SKILL 目录或 `/skills/weekly-skill` 相对解析。
- `references/schema.md` 定义 `draft.json`、`ledger.json`、`claims.json`、`result.json` 的结构。
- `references/playbook.md` 是具体场景处置流。
- `references/checklist.md` 是提交前检查清单。
- `SELFTEST.md` 由 selfcheck 生成，记录本次运行的实际自检结论，不能写为空模板。

## 10. 提交前最终自检

运行：

`python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work`

逐项确认：

- `result.json` 合法。
- `case_id` 与 `output_contract` 双回显完整。
- 所有原始 `output_contract` 字段存在。
- 所有必需图片和必需表都有解析对象。
- 未提供对象进入 `gaps`。
- 所有 claim 有 `source_id` 和 `location`。
- 所有关键数值有单位；没有单位时写 `null`。
- `deliverable.md` 不是纯总结，而是带证据的结构化交付稿。
- `status` 诚实：完成全部实际给到对象才写 `answered`。
- 不包含任何预制答案、假 benchmark 或外部网络得来的补写内容。

如果任何一项未满足，先补产物，再结束。即使无法完成，也要输出合法的 `result.json`，并在 `errors` 中说明。