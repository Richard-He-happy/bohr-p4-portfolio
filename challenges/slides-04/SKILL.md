---
name: academic-slide-template-adapter
description: Turn a paper plus a real .pptx template into a genuinely template-inherited, editable academic deck (pptx + rendered PDF/PNG) with per-slide claim-to-source evidence mapping, an extracted template specification, per-item format compliance evidence read back from the emitted XML, a page-by-page diff, a version record with a rollback path, a run log, and an export/render check. Use when a case asks to fit paper content into a given slide master/layout, adapt a starting deck, or audit slide-template conformance. This skill first runs its deterministic baseline scripts to produce a complete set of deliverables, then requires the Harness Agent to personally read the source material, verify claims/citations/numbers, and enhance the output honestly.
version: 3.0.0
---

# Academic Slide Template Adapter (slides-04)

一句话用途：把 `/input` 里的论文/研究材料装进组织方给的真实 `.pptx` 模板，生成可编辑演示文件、真实渲染的 PDF/PNG 预览、逐页证据映射、模板规格、格式合规、页级差异、版本与回退记录，并且所有关键论断由 Harness Agent 亲自复核、推导、撰写，不把脚本骨架直接当成品。

**铁律**：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止只跑脚本后原样提交，禁止把脚本生成的骨架、模板、中间产物当作成品。必须在本文件要求的执行流程中，真实读取源材料内容，核验页级主张、数字、图号、引用是否与原文一致，并在 `result.json` 中留下 `verified` / `pending_human` / `conflicts` 等真实核验痕迹。

**完整性优先（v6 混合策略，最高优先级）**：先运行本 Skill 自带主脚本/流程，产出全套基线交付物；任何后续校验与改写只能在基线上增强，不得删除、清空或遗漏任何基线与契约字段；若不确定，保留原产物并标注 `reviewed_by_agent`。提交前必须逐项核对「output_contract 字段 list × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐再收尾；partial 状态必须列出缺失项。

## 1. Runtime contract（逐条强制落实）

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、题面规定的材料（`.pptx/.pdf/.docx/.md/.txt/.png/.jpg/.jpeg` 等） |
| 工作目录 | `/app/work`（所有临时文件、解包、中间产物放这里） |
| 最终产物目录 | `/app/output`（最终 `presentation.pptx`、`presentation.pdf`、`preview/*.png`、`result.json`、`template_spec.json`、`format_compliance.json`、`export_check.json`、`page_diff.md`、`version_history.md`、`run.log` 必须全部落在该目录） |
| 入口脚本 | `python3 -B scripts/main.py --input /input --output /app/output [--template X] [--deck Y] [--slides N] [--no-pdf]` |
| 脚本模块 | `scripts/main.py`（装配/编排）、`scripts/verify.py`（解析/计划/XML发射/兼容检查）、`scripts/spec.py`（模板规格/合规/导出/回退/合成骨架）、`scripts/reports.py`（run.log/page_diff/version_history）、`scripts/selfcheck.py`（自检） |
| 依赖 | 仅 Python 标准库；`soffice`、`pdftoppm`、`pdftotext`、`pdffonts`、`fc-match` 探测后使用，缺失即降级 |
| 退出码 | 任何情况下脚本必须退出 0；若脚本异常崩溃，Agent 必须手动补齐最小合法 `result.json` 并确保退出码 0 |
| 首步 | 脚本启动后先落盘 partial `result.json` 空骨架，再干活；崩溃也有合法结果 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行时间计入 900 秒，模型请求按响应计。 |
| 资源限制 | 最终提交的 Skill 包 ≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。运行产物二进制可保留。 |
| 诚实性 | `status`、`sources`、`uncertainty`、`pending_human`、`changes`、`degradations`、`errors` 必须真实；不确定或材料不足要显式标注，不得编造数据、引用、分数。 |

所有实际输入文件和原论文是事实依据；不依据错误的领域标签、文件名或目录名猜测/补造数据。必须真实解析材料内容（用 `pdftotext -layout`、docx 文本抽取、图片魔数读宽高等）后使用。

## 2. 本题专属执行流程（编号步骤）

以下步骤由 Harness Agent 执行。每步写清输入、动作、输出、失败分支。

### 步骤 0：盘点输入与确认契约
- **输入**：`/input/case.json`、`/input/task.md`、列出的材料文件。
- **动作**：
  1. 读取 `/input/case.json`，提取 `case_id`、`output_contract`（全部字段，键名原样）、`organizer_workorder`、`total_slide_count`、`footer_text`、`page_number_required`、`min_font_pt`、`audience`、`task_instruction` 等语义键。
  2. 读取 `/input/task.md`，确认题面要求、评分关注点、输出要求与本节 Runtime contract 有无额外字段。
  3. 用 `find /input -maxdepth 1 -type f` 或 `ls -la /input` 列出实际材料文件；记录文件名、大小、类型（由魔数/扩展名判断）。**不得仅凭文件名或领域标签假设内容**。
  4. 将 `output_contract` 原始字段清单保存到内存/工作笔记（可写临时文件 `/app/work/contract_fields.txt` 但不作为最终交付）。
- **输出**：一份对输入材料、契约字段、约束条件的清晰认知；脚本调用参数（模板路径、deck 路径、页数等）。
- **失败分支**：若 `/input/case.json` 缺失或不可解析，直接进入步骤 5 手动兜底：构造最小 `result.json`，`status=input_error`，`errors` 记录缺失，退出码 0。

### 步骤 1：运行基线主脚本
- **输入**：步骤 0 确定的参数。
- **动作**：执行 `python3 -B scripts/main.py --input /input --output /app/output [--template <模板路径>] [--deck <起始deck路径>] [--slides <页数>] [--no-pdf]`。不要省略 `--no-pdf` 除非确定需要 PDF；如果需要节省时间可加。
- **输出**：全套基线交付物（见下表），包括 `result.json`（先落 partial 后回填完整）和所有要求文件。
- **失败分支**：若脚本报错且未退出 0（极少，因为设计恒 0），立即查看 `/app/output/run.log` 和 `/app/output/result.json`；若 `result.json` 不存在或非法，按步骤 5 手动兜底。脚本正常退出后继续。

### 步骤 2：审查基线完整性与契约字段
- **输入**：`/app/output/result.json`、磁盘文件列表、步骤 0 记录的 `output_contract` 字段。
- **动作**：
  1. `ls -la /app/output` 列出所有文件；对照下表中的预期文件（若有 `--no-pdf`，PDF/PNG 可能缺失但脚本会标注）。
  2. 用 Python（或直接读）解析 `/app/output/result.json`，检查：
     - 包含 `output_contract` 的全部原字段（键名不改，缺失值 null/[]）与 `case_id`；
     - 包含 v1/v2 字段：`status`、`editable_source`、`export_artifact`、`content_map`、`compliance_checks`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`workorder_echo`、`template_spec`、`format_compliance`、`page_diff`、`version_history`、`run_log`、`export_check`、`rollback` 内联；
     - `status` 值合法（`ok|partial|insufficient_evidence|input_error`）。
  3. 检查 `editable_source` 指向的 `presentation.pptx` 是否可由 `python3 -m zipfile -l` 打开且包含 `ppt/presentation.xml`；`template_spec.template.kind` 是否非 `synthetic`（若为 synthetic 记录降级）。
- **输出**：完整性清单，标注缺失项或异常。
- **失败分支**：若缺字段或文件，先尝试重跑一次脚本（不消耗过多预算）；仍缺失则由 Agent 手动补写最小结构（见步骤 5），并在 `errors`/`degradations` 中说明。

### 步骤 3：Agent 亲自核验与增强
- **输入**：`/input` 下的源材料、`/app/output/result.json`、`/app/output/content_map`（内嵌）、`/app/output/page_diff.md`。
- **动作**（**必须执行，这是“genuinely-derived”的关键**）：
  1. 选择至少 3 处核心论断页（如研究问题、方法、结果、限制），打开对应源材料（`.md/.txt/.docx/.pdf` 已由脚本抽取文本，若 PDF 可 `pdftotext -layout /input/xxx.pdf -` 直接读）验证 `content_map[].evidence[].quote` 是否逐字命中；若脚本抽取有误（如小数被切、编号错位），在 `result.json` 的 `reviewed_by_agent` 段记录实际正确原文和修正后的 locator。
  2. 随机抽查 2 个图表引用：核对图片文件是否与内容匹配，图注是否逐字引用，图号与正文引用是否一致；不一致或不清楚时在 `pending_human` 标注。
  3. 阅读 `format_compliance` 中 2-3 个关键项（如 CI-03 母版 sha256、CI-07 占位符继承、CI-11 零硬编码字体）的 `evidence.snippet`，确认其确实来自模板/幻灯片 XML，而非脚本伪造；若发现伪造迹象，在 `uncertainty` 记录。
  4. 若 `content_map[].notes` 存在明显不通顺、未表达“讲解逻辑”的，Agent 基于已核验的页级主张与原文，**亲自重写**该页 notes（≤150 字/页），保持客观、可追溯，注明 `notes_written_by_agent=true`。
  5. 将上述核验结果写入 `result.json` 的新字段 `agent_review`：包含 `verified_count`、`conflicts[].slide_index`、`conflicts[].description`、`pending_human[]`、`reviewed_locs[]`、`review_timestamp`。不得删除原有字段。
- **输出**：增强后的 `result.json`，包含真实核验痕迹。
- **失败分支**：若材料无法打开或内容确实无法读取，不得猜测，在 `pending_human` 写明“材料无法读取：<文件名>”，`status` 置为 `insufficient_evidence`，然后继续。

### 步骤 4：rubric 自检与格式补全
- **输入**：本 SKILL.md 第 6 节的 rubrics 对照表、`/app/output` 全部产物。
- **动作**：逐项对照本文件第 6 节和自检清单（第 7 节），检查交付物是否满足各评分点要求。特别注意：
  - `format_compliance` 是否 16 项齐全且每项有 `actual` 与非空 `evidence`；
  - `page_diff.md` 的 miss 计数与 `pending_human` 一致；
  - PDF/PNG 预览存在且 PDF 头为 `%PDF-`、页数等于幻灯片数（若 `export_check` 说 pass）；
  - 可编辑文件确实可打开编辑，`ppt/theme/theme1.xml` 存在，母版/版式/主题 sha256 未被篡改；
  - `output_contract` 字段全部回填。
- **输出**：自检记录（可写在 `run.log` 追加或 `result.json.agent_selfcheck`）。
- **失败分支**：若某项不满足且无法自动修复，在 `result.json.degradations` 或 `pending_human` 记录，`status` 降级为 `partial`，但仍保留所有产物。

### 步骤 5：回填 result.json 与收尾
- **输入**：所有上述产物。
- **动作**：
  1. 确保 `result.json` 合法 JSON，缩进 2 空格；`case_id` 来自 `/input/case.json`；`status` 反映真实状态；`sources` 列表包含每个输入文件的字节数与 sha256；`changes` 记录本次 Agent 介入的修改（如“agent_review added: 3 quotes verified, 1 conflict corrected”）。
  2. 若存在 `output_contract` 中的字段未覆盖（例如额外要求），以 `null` 或 `[]` 补齐但键名保留。
  3. 最终确认 `/app/output` 下所有文件可读、JSON 可解析、`result.json` 不在临时目录。
  4. 写退出码 0（脚本/Agent 不因失败中断）。
- **输出**：最终交付目录 `/app/output`，包含全套可复核产物。
- **失败分支**：即使部分产物缺失（如 PDF 导出失败），也要产出合法 `result.json`，状态为 `partial` 并在 `errors`/`degradations` 列出缺失项，退出码 0。

## 3. 预算策略（64 次模型请求 / 900 秒 / 16384 tokens）

**核心原则**：脚本是确定性的，一次运行通常能在 100-300 秒内完成大部分机械工作。Agent 应把模型请求花在只有人类（Agent）能做的核验、判断、修正上，不要反复运行脚本或重复读取大文件。

建议分配：

| 阶段 | 建议请求数 | 动作 | 可跳过情形 |
|---|---|---|---|
| 步骤 0 盘点 | 1-3 | 读 `case.json`、`task.md`、列出输入文件 | 若脚本能自动发现大部分信息，只读 `case.json` 一次 |
| 步骤 1 运行脚本 | 1 | 调用 `scripts/main.py` | 不可跳过 |
| 步骤 2 审查基线 | 1-2 | 读 `result.json` 关键字段、`ls` 输出 | 若脚本无报错且字段齐全，可简化 |
| 步骤 3 Agent 核验 | 5-10 | 读源材料关键页/段、核对 `content_map` 引文、抽查图片与 compliance evidence | 如果时间紧，至少核验 2 处核心论断和 1 个图表 |
| 步骤 4 rubric 自检 | 2-4 | 读 `format_compliance`、`export_check`、`page_diff` 少量关键项 | 脚本自身会进行大部分检查 |
| 步骤 5 回填收尾 | 1-2 | 写 `result.json` 增强字段、最终确认 | 不可跳过 |

**最早落盘 partial**：脚本启动后立即写 partial `result.json`；Agent 若发现时间不足，应在完成步骤 2 后立即保存当前 `result.json` 并标注 `partial`，绝不空手结束。

**优先级**（在 64 次请求内按此顺序）：
1. 合法 `result.json` 且包含 `output_contract` 全部字段和 `case_id`；
2. 可编辑 `presentation.pptx` 真实存在且可打开；
3. 真实渲染的 PDF/PNG 预览（若 `soffice` 可用）；
4. 页级证据映射 `content_map` 与来源定位；
5. 格式合规、导出检查、页级差异等 v2 资产；
6. Agent 亲自核验的 `agent_review` 与 notes 增强。

**禁止**：无意义循环、重复运行脚本超过 2 次、反复读取大文件全文、为了完美不断重试。如果某项拿不到，标注 `pending_human` 后进入下一步。

## 4. 隐藏案例鲁棒性：材料缺失/损坏/格式不支持/超时/空输入/契约缺失

以下场景必须诚实降级，并最终产出合法 `result.json` 且退出码 0。脚本已内置大部分处理，Agent 只需确保兜底。

| 场景 | 降级处理 | 证据/字段 |
|---|---|---|
| 无模板/模板损坏/不是 zip | 使用内置合成骨架包（16:9，1 母版 4 版式 1 主题），`template_spec.template.kind="synthetic"`，状态 `partial` | `degradations[stage=template]`、`template_spec.template.kind` |
| 论文无文本层（如扫描 PDF） | 只出封面/结论骨架，`status=partial` | `exceptions[no_source_text]`、`pending_human` |
| 材料缺失（`/input` 无文件或 `case.json` 空） | `status=input_error`，`errors` 列出缺失，`editable_source` 仍生成最小 pptx（合成），其余字段 null/[] | `errors`、`sources=[]` |
| 版式缺 body/图片占位符 | 该页不写正文或自由文本框回退，记 `deviation` | `content_map[].deviation`、`format_compliance.CI-07` |
| 字体缺失/被替换 | 记录缺失字体，`export_check` 字体表标记替换，不静默修复 | `degradations`、`export_check.fonts` |
| 图片读不出/损坏 | 跳过该图，记 `figure_unreadable`，图片引用处写“图缺失” | `degradations`、`content_map[].figure_status` |
| `soffice` 缺失/转换超时 | 保留 pptx，`export_check.status=no_pdf`，`status=partial` | `export_check.consistency.note` |
| `pdffonts`/`pdftotext` 缺失 | 用 XML 几何估算，记录估算不确定性 | `export_check.degradations` |
| 脚本崩溃/未运行 | Agent 手动创建最小 `result.json`：回填 `output_contract` 原字段（null/[]）、`case_id`、`status=input_error`、`errors[脚本崩溃]`、`editable_source` 可为 null，退出码 0 | 手写 `result.json` |
| 超时（900 秒用完） | 立即保存已有 partial，状态写明超时，agent 不再执行额外动作，退出码 0 | `runtime.timeout=true`、`pending_human` |
| 空输入（无任何材料） | 合成骨架包 + 空内容 + 状态 `insufficient_evidence` | `errors[no_input]` |
| 契约缺失（`output_contract` 不存在） | 按本文件规定的默认字段生成 `result.json`，并在 `workorder_echo` 注明 | `workorder_echo.missing_contract=true` |

无论哪种情况，最终 `/app/output/result.json` 必须是合法 JSON，包含 `case_id` 与所有可得字段；退出码必须为 0。

## 5. Rubric 维度 → 交付要求 → 自证方式对照表（逐条）

| 评分维度 | 分值 | 评分点 | 交付要求 | 自证方式 |
|---|---|---|---|---|
| **实际效果** | 40 | 任务完成度 15 | 把源论文与图表真正套进指定模板，交付可打开、可继续编辑的 pptx 及导出件。**要求**：模板母版/版式/主题未被破坏，每页使用 `slideLayout` 关系，占位符继承率 ≥80%（除合成模板外）。 | `template_spec.layout_map`、`format_compliance.CI-03/CI-05/CI-06/CI-07`、磁盘 `presentation.pptx` 可被 `zipfile` 打开 |
|  |  | 结果正确性 15 | 页内文字、数字、图号与源材料一致，图表与数据对应，母版与版式继承关系真实发生，导出件与 pptx 渲染一致。 | `content_map[].evidence[].quote` 逐字命中；`page_diff.md §3` miss 计数为 0 或已标记；`format_compliance` 各项 `actual` 与 `evidence.snippet`；`export_check.rules`（PDF 页数=幻灯片数、尺寸一致、字体嵌入） |
|  |  | 结果完整性 5 | 覆盖从封面到结论的主要页类型，包含论文主线、页结构、图表引用、讲解逻辑、模板约束、导出渲染六类要素。 | `content_map` 页类型涵盖封面/大纲/方法/结果/讨论/结论；`notes` 讲解逻辑；`template_spec` 模板约束；`export_check` 导出渲染 |
|  |  | 结果可核验性 5 | 源文件、模板、导出件与逐页偏差记录能支撑他人独立复跑。 | `sources[].sha256`、`template_spec.protected_parts`、`version_history.md`、`run.log`、`page_diff.md` |
| **使用增益** | 25 | 质量增益 15 | 相比基础 Agent，标题/字号/色板/页脚页码/图表适配/版式继承显著更规范，无整段粘贴、无溢出、无变形。 | `format_compliance` CI-08..CI-15 全部 pass；`export_check.overflow` 无越界；`page_diff` 显示偏差极少 |
|  |  | 效率增益 5 | 减少单册排版耗时、批量返工页数、人工核对工作量。 | 运行日志 `run.log` 中阶段耗时；`main.py` 一次运行完成装配+导出+检查；Agent 核验只花少量请求 |
|  |  | 增益可验证性 5 | 通过公平对照证明质量/效率改善。 | 本 Skill 未提供对照实验，但在 `result.json.runtime` 记录本案例耗时、`agent_review` 记录核验过程，作为可复核的增益证据；若平台提供基础 Agent 结果，可对比 `format_compliance` 和 `export_check` 的差异 |
| **创新增益** | 15 | 新增能力 5 | 基础 Agent 或现成模板工具不具备的能力：真实提取模板母版/版式/主题规格并回填布局映射；逐项 XML 证据；页级差异重比。 | `template_spec.json`、`format_compliance.json` 的 16 项 `evidence[].snippet`、`page_diff.md §3` |
|  |  | 方法改进 5 | 内容与版式映射、字号与间距规则、图表缩放策略、批量一致性校验等方法有实质改进。 | `template_spec` 中的字号/行距/色板规则；`format_compliance.CI-10/CI-12`；`export_check.overflow` 模型；`spec.py` 中 `fit_rect` 等比缩放逻辑（可由 Agent 阅读 `scripts/spec.py` 验证，但不直接引用为产物证据） |
|  |  | 创新证据 5 | 证明创新点相对已有方案的边界与价值。 | `SKILL.md` 中的维护说明、`version_history.md` 中的变更记录、`result.json` 的 `agent_review` 中记录的创新点有效性 |
| **可靠体验** | 10 | 调用与易用性 3 | Agent 能正确触发，用户能按说明完成一次“论文+模板→pptx+PDF”流程。 | `scripts/main.py --help` 可运行；SKILL.md 步骤清晰；CLI 示例在 `## 12. 最小调用示例`（原文档保留） |
|  |  | 运行稳定性 4 | 在不同模板、页数、字体环境、重复运行下持续产出可用结果。 | 脚本纯标准库；`soffice` 缺失降级；`selfcheck.py` 一键回归 `SELF-CHECK PASSED` |
|  |  | 异常处理 3 | 对模板缺版式、占位符缺失、文本框溢出、字体缺失、图表源失效、导出失败的识别与处置。 | `degradations` 表格每项有 `stage`、`detail`；`template_spec.template.kind`；`export_check.degradations`；`page_diff` 偏差列 |
| **生态贡献** | 10 | 文档完整性 3 | 模板准备规范、参数含义、导出设置、字体要求、限制与维护信息齐全。 | 本 SKILL.md 及 `references/artifact_schema.md` 提供字段契约与维护说明；`version_history.md` 记录变更 |
|  |  | 资源可复用性 4 | 作品本体、模板适配层、页级金标准、检查脚本等资源可被他人复用。 | 脚本