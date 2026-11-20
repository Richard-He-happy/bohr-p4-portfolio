---
name: academic-slides-from-paper
description: Turn a research paper (PDF/DOCX/TXT/MD) plus an optional organizer PPTX template into an editable, template-inheriting academic deck (.pptx with real speaker notes), a PDF preview, and a page-level audit trail - page_golden.json, page_diff.md, run.log, export_check.json, template_check.json, version_history.md and a contract-complete result.json whose every slide carries verbatim evidence (quote + locator). Use for 论文转汇报 / academic slide generation / deck editing and adaptation / 模板套版 / evidence-mapped presentation build. Version 3.0.0 adds Agent-first hybrid strategy: run the full baseline first, keep all baseline artifacts, then have the Agent verify and enhance without deleting or falsifying anything.
version: 3.0.0
---

# Academic slides from a paper (slides-02) — Agent 驱动完整交付

## 0. 给 Harness Agent 的最高优先级指令（v6 混合策略）

1. **脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作**。禁止把 `scripts/main.py` 的骨架、模板或占位输出直接当作成品；你必须亲自核验论文证据、页级主张、数字、图表引用和备注逻辑。
2. **先跑基线，再改进**。进入任务后先运行本 Skill 自带的主脚本，产出**全套基线交付物**（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段）。不要跳过基线。
3. **保留全部基线产物**。后续的校验与改写只能在基线上增强；**不得删除、清空或遗漏任何基线与契约字段**。若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。
4. **完整性自检（提交前必做）**：逐项核对「`output_contract` 字段 list × 磁盘文件 × `result.json` 键」三者一一对应；缺任何一项先补齐再收尾；`partial` 状态必须列出缺失项。
5. **可核验增强**：在基线产物之上，由 Agent 亲自核验关键论断/数字/引用的来源一致性，把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`），这才是 genuinely-derived 的证据。

## 1. 用途与边界

构建一个可打开、可编辑、论证论文主线的学术演示稿：页角色、页顺序、每页主张、引用图表、演讲备注、模板继承和页级证据映射，并附带可复核审计文件。

适用：组会、答辩/中期、项目评审、开题等固定模板的学术汇报。

不适用：论文精读与文献综述、统计再分析、从原始像素设计图表、学术写作润色、PPT 软件本身开发。**不得编造数字**：每个正文 bullet 必须是源文本中一个句子的逐字子串。

## 2. 运行时契约（必读）

- **输入**：`/input/case.json`、`/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。**必须真实解析材料内容**（用 `pdf-text-tool` 或其他解析工具），不得依据文件名或领域标签猜测/补造内容。
- **工作目录**：`/app/work`；最终产物必须落在 `/app/output`；必须有 `result.json`，且包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。
- **可编辑 Office/幻灯片/图形产物**：必须额外给出**真实渲染的 PDF/PNG 预览**。
- **预算**：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。先明确 rubric 权重最高的交付物，优先完成并尽早落盘 honest partial，再增量改进；避免无意义循环与冗余调用。
- **诚实性**：`status`/`sources`/`uncertainty`/`changes` 必须真实；不确定或材料不足要显式标注 `pending_human` / `limitations`，不得编造数据、引用、分数。
- **资源限制**：Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。
- **退出码**：任何情况下都必须产出合法 `result.json` 并以退出码 0 结束。

## 3. 可用脚本与资源（只能引用包内真实存在文件）

- `scripts/main.py`：CLI + 编排 + 步骤日志
- `scripts/discover.py`：输入发现、输出目录、契约回显
- `scripts/build.py`：页面规划、计划回放、OOXML 打包
- `scripts/deckkit.py`：读取器、句子/章节分析、形状构建
- `scripts/gold.py`：金标准、diff、版本历史
- `scripts/checks.py`：导出/渲染与模板检查
- `references/deck-parts.json`：OOXML shell + 内置设计（可复用）
- `references/slide-planning.md`：角色分类、排序、预算、编辑策略
- `references/result-and-checks.md`：结果 schema、定位语法、异常代码
- `references/golden-and-checks.md`：`page_golden` / `page_diff` / `export_check` / `template_check` schema

**基线调用命令**：

`python3 -B scripts/main.py --input /input --output /app/output [--work /app/work] [--slides N] [--template X.pptx] [--no-pdf]`

可选 v2 开关：`--reuse-plan <plan_v0.json>` 回放骨架，`--no-golden` 只产出 v1 输出，`--legacy-sections` 恢复 v1 章节标注。

所有路径基于脚本自身位置解析，不依赖 CWD。

## 4. 本题专属执行流程（编号步骤）

### 步骤 1：盘点输入

**输入**：`/input/case.json`、`/input/task.md`、`/input/` 下所有材料文件。

**动作**：
1. 读取 `case.json`（解析失败继续，记录 `NO_CASE_JSON`）。
2. 读取 `task.md` 提取 `output_contract`、slide count、mode、source preservation、template inheritance、audience、time、slide count 等要求。
3. 列出 `/input` 及 `/input/artifacts` 下文件，识别 PDF/DOCX/TXT/MD/图片/PPTX/JSON。
4. 找到 `slide-workorder.json` 或任何含 `slide_count`/`total_slides`/`slide_spec` 的 JSON。
5. 识别模板：`template*.pptx`、`starting*.pptx`。

**输出**：在 `/app/work/input_manifest.md` 中记录文件清单、契约字段、任务要求摘要。

**失败分支**：任何读取失败都继续，把异常写入 `result.json` 的 `exceptions`，不要因此中断。

### 步骤 2：真实解析材料（构建证据底稿）

**输入**：步骤 1 识别的源材料。

**动作**：
1. 对 PDF 使用 `pdftotext -layout` 或脚本内建读取器获取文本和页码；DOCX 用 `word/document.xml` 解析；TXT/MD 直接读取。
2. 用脚本内建的句子切分与章节标注，或手动核对，提取研究问题、方法、结果、限制，形成主线。
3. 记录每个关键句子的 locator 格式：`<source file> p.<page> <section>`，确保引用可回查。
4. 将提取的关键证据写入 `/app/work/extracted_evidence.md`，作为后续核验依据。

**输出**：`/app/work/extracted_evidence.md`。

**失败分支**：
- PDF 无文本层：标注 `scanned_no_text_layer` / `LOW_SOURCE_TEXT`，继续但证据不足。
- 图片无法取数：标注 `figure_not_available_in_source`，不重绘不猜测。
- 任何材料缺失：写入 `pending_human`。

### 步骤 3：运行基线脚本（必做，产出全套基线）

**输入**：步骤 1、2 已确认的 `/input` 和 `/app/work` 信息。

**动作**：
1. 运行基线：
   `python3 -B scripts/main.py --input /input --output /app/output --work /app/work`
2. 检查输出目录是否生成了以下文件：
   `presentation.pptx`、`presentation.pdf`、`result.json`、`run.log`、`plan_v0.json`、`page_golden.json`、`page_diff.md`、`export_check.json`、`template_check.json`、`version_history.md`。

**输出**：全套基线交付物。

**失败分支**：
- 若脚本崩溃或不齐全，先不要放弃。将异常写入 `/app/work/agent_review.md`，然后按 §6 手动 fallback 生成合法 `result.json`。
- 若 `soffice` 缺失导致 PDF 失败，`export_artifact` 置 `null`，记录 `PDF_RENDER_UNAVAILABLE`。

### 步骤 4：审查与核验基线（Agent 亲自推导）

**输入**：基线产物 + 步骤 2 的 `extracted_evidence.md`。

**动作**：
1. 打开 `/app/output/result.json`，检查 `status`、`content_map`、`compliance_checks`、所有契约字段是否齐全。
2. 抽查 `content_map` 中的 quotes：与 `extracted_evidence.md` 或源文件对照，确认每个 bullet 的 `quote` 是逐字子串，`locator` 页节正确。
3. 核验关键数字、图注、引用编号：不得按印象取整，不得错位。
4. 检查 `page_golden.json` 与 `page_diff.md`：页角色、页序、主线逻辑、数字覆盖、硬缺口。
5. 检查 `export_check.json` 与 `template_check.json`：PDF 页数、字体替换、溢出、模板继承。
6. 把核验结果写入 `/app/work/agent_review.md`，明确 `verified`、`pending_human`、`conflicts`。

**输出**：`/app/work/agent_review.md`。

**失败分支**：
- 发现基线数据错误：在 `result.json` 的 `reviewed_by_agent` 和 `changes` 中记录，并把 `status` 改为 `partial`，把错误条目加入 `exceptions` 或 `uncertainty`。
- 不要删除基线错误内容，而是标注待人工复核，保留原样可回退。

### 步骤 5：增量改进（如预算允许，只做高置信度修正）

**输入**：步骤 4 的审查结论。

**动作**：
1. 仅当发现明确错误且你有足够证据时才修改：
   - 抄错数字/单位/引用：修正对应 `content_map` 中的 text/quote，或重跑脚本前修正源材料副本（若你保留在 `/app/work`）。
   - 页序严重不符合叙事逻辑：调整计划后重跑脚本，但先备份当前基线到 `/app/work/baseline_backup/`。
2. 优先增强审计文件而非重构全部：把核验结论、冲突、缺失项写入 `result.json` 的 `reviewed_by_agent`、`changes`、`uncertainty`。
3. 如果时间或证据不足，保留基线现状，只标注 `pending_human`。
4. **禁止因“美观”或“优化”而清空、覆盖或丢弃基线字段与文件**。

**输出**：增强后的 `result.json`（保留所有原字段），可选更新 `.pptx`/`.pdf` 或审计文件。

**失败分支**：若修改导致文件损坏，立即回滚到 `/app/work/baseline_backup/` 并记录回滚。

### 步骤 6：完整性自检与回填 result.json（提交前必做）

**输入**：当前 `/app/output` 全部内容 + 题目 `output_contract`。

**动作**：
1. 列出 `output_contract` 的每个字段，确认 `result.json` 中均有对应键且键名不改。
2. 确认 `case_id` 已填写。
3. 核对磁盘文件清单：至少包含上述基线文件；如果 `output_contract` 要求额外文件，必须补齐。
4. 若缺失任何字段或文件，立即补写：缺失文件生成最小合法占位（如无法 PDF 可置 null），缺失字段在 `compliance_checks.contract.unknown_keys` 或 `pending_human` 中说明。
5. 将步骤 4 的核验结果写入 `result.json` 新增键：
   - `reviewed_by_agent`: `{ verified: [...], pending_human: [...], conflicts: [...], notes: "..." }`
   - 保持原 `status` 真实：`ok`（全部通过）、`partial`（有缺失/冲突/待人工）、`insufficient_evidence`（材料不足）。
6. 更新 `changes` 和 `runtime`（记录 Agent 实际执行的增强步骤）。

**输出**：最终 `result.json`。

**失败分支**：若无法确定契约字段，保留脚本生成的所有字段，`status` 写 `partial`，在 `exceptions` 写 `CONTRACT_UNKNOWN`。

### 步骤 7：收尾

**动作**：
1. 最后扫描 `/app/output` 确保没有空文件或缺失关键产物。
2. 验证 `result.json` 可解析。
3. 以退出码 0 结束，不抛异常。

## 5. 预算策略（64 次模型请求 / 900 秒内分配）

总原则：**先交付，后增量**。

- **必须执行**：
  - 步骤 1 盘点输入（1-2 次模型请求）
  - 步骤 2 提取/核验关键证据（2-4 次）
  - 步骤 3 运行基线脚本（1 次工具调用，脚本内部无模型调用）
  - 步骤 4 审查基线（2-3 次）
  - 步骤 6 自检与回填（1-2 次）
- **可选执行**：
  - 步骤 5 增量改进：仅在发现高置信度错误时做，最多 2-3 次，避免反复重跑。
  - 不要无意义循环；不要在无材料时反复猜测。
- **尽早落盘 partial**：基线脚本已写 `partial` `result.json`；若运行失败，立即手动写最小 `result.json`（含 `case_id`, `status`, `output_contract` 要求的全部字段，缺失为 null）。
- **单次响应 tokens**：控制在 16384 以内；不要在单次请求中输出全量源文件，只输出关键引用和审查结论。

## 6. 隐藏案例鲁棒性与降级

| 情况 | 降级行为 |
|-|-|
| `case.json` 缺失/损坏 | `NO_CASE_JSON`，继续，契约字段默认可空，产出通知 deck |
| 无源文本或 <4 句 | `LOW_SOURCE_TEXT` + `INSUFFICIENT_INPUT`，3 页通知 deck，`status: insufficient_evidence` |
| 无模板 | 使用 `references/deck-parts.json` 内置 16:9 设计，`pending_human` 注明，`template_check` 标记 `n/a` |
| 模板不可读 | 记录 `degradations.template`，回退内置设计，`template_check.template_readable = warn` |
| mode=edit/adapt 但无 starting deck | `EDIT_WITHOUT_STARTING_DECK`，降级为 generate |
| `soffice` 缺失/失败 | `PDF_RENDER_UNAVAILABLE`，`export_artifact: null`，pptx 保留，`export_check.overall_pass = false` |
| PDF 无文本层 | 文本提取极少 → `LOW_SOURCE_TEXT`，不做 OCR |
| 无嵌入 JPEG 图 | `figures.embedded_from_source: 0`，文本补位，`figure_placement: not_available_in_source` |
| 句子池耗尽 | `POOL_EXHAUSTED`，丢页并报告在 `slide_count`/`uncertainty` |
| 文本溢出 | 字号自动缩至 12pt，残余溢出列入 `text_fit.overflow_slides` 和 `export_check.text_overflow` |
| 模板字体未安装 | `export_check.fonts.substituted` 列出替换字体，`fonts_inherited = warn`，`overall_pass` 不受影响 |
| Han 文本 | CJK 回退记为 `cjk_fallback`，非替换 |
| `--reuse-plan` 与旧计划不符 | `PLAN_REUSE_MISS` / `PLAN_REUSE_INVALID`，从匹配处重建 |
| 脚本异常退出 | 捕获异常，强制写 `result.json`（`status: partial`，包含 traceback），刷新 `run.log`，退出码 0 |
| 超时 | 保留已完成文件，写 partial 结果，注明未完成项 |

**任何情况下**：必须产出合法 `result.json`，包含 `case_id`，至少回显 `output_contract` 的全部键（值为 null 或说明），以退出码 0 结束。

## 7. 输出契约字段与基线产物（保留）

Root keys: `case_id`, `status`（`ok` | `partial` | `insufficient_evidence`）, `editable_source`, `export_artifact`, `content_map`, `compliance_checks`, `exceptions`, 加上 `errors`, `degradations`, `pending_human`, `uncertainty`, `sources`, `changes`, `runtime`, 以及 v2 字段 `page_golden`, `page_diff`, `version_history`, `export_check`, `template_check`, 还有 input `output_contract` 的每个原始键（键名不改）。

| 字段 | 内容 |
|-|-|
| `editable_source` | path, format, bytes, sha256, slides, slide_size_emu, mode, template_source (`template:<name>` / `starting-deck:<name>` / `builtin-default`) |
| `export_artifact` | path, format, pages, bytes, method, degraded |
| `content_map[i]` | slide_index, role, title, layout, notes, bullets[{text, quote, locator, verified, kind}] (`kind=source` 带 quote，`kind=front_matter` 为 workorder 元数据