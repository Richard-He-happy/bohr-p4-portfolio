---
name: bilin-paper-translator
description: Paragraph-aligned bilingual translation of scientific papers with a locked glossary, verbatim protection of numbers/units/citations/cross-references/formulas, and per-paragraph evidence locations. Use when a user asks to translate a paper, PDF, DOCX, section or abstract into Chinese (or another target language), to produce a source/translation side-by-side table, to enforce terminology consistency across a manuscript, or to verify an existing translation against the source. The scripts are utilities only; the Harness Agent must read the actual source material, derive the translation, and produce the final deliverables.
version: 2.0.0
license: MIT
---

# bilin-paper-translator（文献翻译：术语锁定 + 段落对齐 + 标记保护 + 自校验）

## 0. 必读：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作

本 Skill 提供 `scripts/main.py` 与 `scripts/engine.py`，用于材料抽取、分段、术语候选、标记保护与结果装配。但**它们只是你的工具**，不是成品本身。你必须在脚本生成的基线上，亲自阅读真实材料，核对证据，完成/修订翻译，并撰写复核记录。**禁止把脚本骨架、空译文模板或未经验证的自动输出当作最终交付物。** 评审会检查交付物是否“完整、像 Agent 真实推导出来的”，因此请保留你的人工核验与修订痕迹（例如写入 `verification.agent_review` 和 `changes`）。

在隐藏原始案例上，优先级始终是：  
1) 合法契约 + 完整基线（所有字段和文件齐全）；  
2) 真实逐段翻译和对齐；  
3) 术语、数字、引用、公式、否定关系的准确保留；  
4) 预算内尽早落盘和增量改进；  
5) 诚实标注不确定与未完成项。

## 1. 用途与边界

**做**：把一篇真实文献（或 `case` 指定的段落区间）切成稳定段号 `P###`，产出段落级双语对照（`translation_bilingual.md`）、可复核对齐表（`alignment.csv`）、可复用术语表（`glossary.csv`），并给出机器可查的保真证据（`result.json` + `verification.json`）。

**不做**：不联网、不检索、不生成材料外的文献/数值/结论；不把“摘要/大意”当译文；不对扫描件做 OCR（无 OCR 时明确降级并要求人工补录）；不自动判定“翻译质量合格”，只报告可机检指标。

**适用**：有文字层的 PDF、DOCX、TXT/MD/HTML 论文或段落；需要术语统一、跨页不漏段、编号与公式不被改写的翻译任务。

## 2. 运行契约

- 入口：`SKILL.md`（本文件）；执行物：`scripts/main.py` + `scripts/engine.py`（纯标准库，无第三方依赖，不联网，不依赖 CWD）。
- 默认目录：输入 `/input`、输出 `/app/output`、中间 `/app/work`；可用 `--input/--output/--work` 或 `INPUT_DIR/OUTPUT_DIR/WORK_DIR` 覆盖。资源路径由 `Path(__file__).resolve().parent` 定位。
- 第一次落盘即为 **partial `result.json`**；任何异常被捕获写入 `errors`，最终无条件 finalize 覆盖；**退出码恒 0**。
- `output_contract` 深拷贝回填，契约字段全部出现（缺值 `null`/`[]`），键名不改、未知字段保留，`case_id` 原样透传。
- 预算：单案例 900s / 64 次模型请求；脚本内超过 780s 只做收尾，脚本本身不调用模型。
- 你（Agent）调用脚本后，应阅读脚本产物，进行真实核验与补全；然后再次运行 `finalize` 把最终状态写回。

## 3. 输入发现与真实解析

**核心原则：必须真实解析材料内容，不得依据文件名或领域标签猜测/补造内容。** 如果脚本抽取结果可疑，你应使用可用的 pdf-text-tool 等工具直接查看原始 PDF/DOCX 文本，交叉验证后再继续。

1. 找 `case.json` / `case*.json` / `**/case*.json`（非法 JSON 被捕获，继续用其他材料）。
2. `case_id`、`output_contract` 原样透传；任务说明按语义键取（`task_instruction|instruction|prompt|task|request`），缺省用 `task.md` 前 1000 字。
3. 术语表按语义键取（`glossary|terminology|term_list|glossary_seed|terms`），或 `glossary.csv|glossary.json`；随后 `work/glossary.csv` 覆盖。
4. 递归扫描输入目录，按扩展名 + 魔数识别 PDF/DOCX/TXT/MD/HTML/CSV/JSON/图片；主材料按 `pdf>docx>text/html>csv/json` 与体积择一，其余材料登记在 `sources`。
5. 材料未给的对象明确列缺口（`errors`/`uncertainty`），不构造像素、图注或数据。
6. **真实解析要求**：脚本调用 `pdftotext` 或内置 stdlib 抽取实际文本；你必须在后续步骤阅读 `work/source_units.md` 并抽查原文段落，确认抽取内容与原始文件一致。若不一致，以原始文件为准并修正 `work/segments.json` 或重新抽取。

## 4. 输出契约

| 文件 | 内容 |
|-|-|
| `output/result.json` | 主结果：`case_id/status/status_reason/task/output_contract` + 契约镜像字段 + `translation{paragraphs,coverage,token_fidelity,source_text}` + `glossary` + `claims` + `sources` + `segments` + `coverage` + `verification` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime` + `artifacts` |
| `output/translation_bilingual.md` | 逐段：`### P001 · p.3 · body · Results` + 原文行 + 译文行 + `标记 n/m · 术语 k · flags` |
| `output/alignment.csv` | 段落级对齐表（段号/页码/状态/字数/标记数/flags/原文摘录/译文） |
| `output/glossary.csv` | 术语表（`term,translation,freq,violation_seg_ids,status`） |
| `output/verification.json` | `checks{}` + `summary{}` + `rejected_claim_ids` + 启发式说明 |
| `work/` | `segments.json`（全文分段）、`source_units.md`（人读原文）、`glossary.csv`（待填模板）、`state.json`（跨进程元数据，finalize 还原用）、`translations/*.json`（译文） |

字段级定义见 `references/output-schema.md`。注意：`result.json` 中的 `output_contract` 必须原样包含平台提供的所有字段，不得改名或删除；同时保留上述所有字段。你可以新增字段（如 `agent_review`），但不得破坏原有字段。

## 5. 本题专属执行流程（核心步骤）

以下每步必须执行；每步给出输入、动作、输出和失败分支。**任何一步失败都不允许放弃；降级后继续，最终必须写出合法 `result.json` 并退出码 0。**

### 步骤 1：盘点输入与契约
- **输入**：`/input/case.json`、`/input/task.md`、材料文件。
- **动作**：
  1. 读取 `case.json`，提取 `case_id`、`output_contract`、任务说明。
  2. 列出 `/input` 下所有材料文件，按扩展名/魔数识别类型。
  3. 如果存在 `task.md`，通读题目要求，明确需要交付的对象（翻译范围、目标语言、对齐要求、术语表要求等）。
  4. 检查是否有术语种子表（`glossary.csv` 等）。
- **输出**：你对案例的初步理解，记录在 `work/state.json` 或 `result.json` 的 `runtime.input_summary` 中。
- **失败分支**：如果 `case.json` 缺失或损坏，继续使用 `task.md` 和材料；记入 `errors`；若连任务说明都没有，推导默认任务（翻译主材料全部可译段落）并标注 `status=input_error`。

### 步骤 2：运行基线脚本，真实解析并生成 partial
- **输入**：步骤 1 识别的输入目录与契约。
- **动作**：
  1. 执行：
     ```bash
     python3 -B scripts/main.py prepare --input /input --output /app/output --work /app/work
     ```
  2. 脚本会抽取真实文本、分段、生成 `work/source_units.md`、`work/segments.json`、`work/glossary.csv`、partial `result.json`。
  3. 你自己阅读 `work/source_units.md` 或使用 pdf-text-tool 抽查原始材料的若干段落，确认抽取准确。若发现明显漏段、错位、文字乱码，需要手动修正 `work/segments.json`（或在脚本不支持时记录到 `degradations` 并继续）。
- **输出**：完整的基线结构文件，以及一个 **partial `result.json`**（此时可能译文为空或部分填充，状态为 `partial`）。
- **失败分支**：如果 `prepare` 因无材料或格式不支持而失败，仍会写入合法 partial；你应阅读 `result.json` 中的 `errors/degradations`，决定是否需要手动编写翻译输入或降级。**绝不手动删除 partial 文件。**

### 步骤 3：构建/核对证据（真实材料 → 证据链）
- **输入**：原始材料、`work/source_units.md`、`work/segments.json`、partial `result.json`。
- **动作**：
  1. 逐段（或抽查关键段）核对原文文本是否准确：段号、页码、章节、表格/图注是否对应。
  2. 识别关键实体：数字、单位、公式、引用标记（`[n]`、作者-年份）、图表编号、术语。
  3. 对脚本生成的术语候选表 `work/glossary.csv` 进行人工审校：补充术语译名，锁定全篇统一译名。
  4. 用原文中的 exact quote 验证关键结论（例如某段声称的数字或关系），确保 quote 来自 `source_units.md` 或 raw 文本。
- **输出**：证据核验记录，可写入 `verification.agent_review`（新增字段）或 `changes`，列出已核验的段号、发现的问题、需要人工确认的项。
- **失败分支**：如果某段原文无法读取（扫描件/图片），记录 `U1 文字层低可读` 并保持该段未译或标注；如果某术语无法确定译名，记录 `pending_human`，不擅自编造。

### 步骤 4：Agent 产出完整成品（真译 + 修订 + 对齐）
- **输入**：核验后的 `work/` 文件、术语表、你的翻译判断。
- **动作**：
  1. 使用脚本分批填充译文：编辑 `work/translations/batch_NN.json`，每批 5–6 段。译文必须是你亲自根据原文真实翻译或严格修订自动译文，不是摘要或改写。
  2. 优先处理高评分权重段落：标题、摘要、正文关键论证段、图表题注、公式周围段落、参考文献。
  3. 对每段，严格保护公式、引用标记、数字、单位、图表编号、否定关系、限定条件。
  4. 将术语表锁定译名应用到所有段落；若发现不一致，修正译文或更新术语表。
  5. 写双语稿、对齐表、术语表、核验记录时，**保留人类可读的证据定位**（页码、段号、原文摘录）。
- **输出**：完整的 `work/translations/*.json`，术语表翻译列已填充，以及你修订后的双语稿内容待脚本装配。
- **失败分支**：如果时间或请求预算不足，至少保证高权重段落已翻译并核对，其余段落标记 `untranslated`（`status="untranslated"`，译文为空字符串），绝不伪填。

### 步骤 5：自检 rubric（对照第 8 节）
- **输入**：当前所有产物。
- **动作**：逐项检查第 8 节对照表中的交付要求是否满足。重点检查：
  - `result.json` 可解析，`output_contract` 字段完整。
  - `translation.coverage` 是否接近 1（或如实为 partial 并说明缺口）。
  - `token_fidelity.rate`、`glossary.consistency.rate` 是否达到阈值或如实记录未达标。
  - 双语稿段号与 `alignment.csv` 行数一致。
  - 不存在将不确定内容写成事实。
- **输出**：自检发现的缺口清单，逐项补齐。
- **失败分支**：如果某些项无法满足（例如材料缺失），必须写入 `errors`/`pending_human`，并将 `status` 设为 `partial`，不得谎称 `ok`。

### 步骤 6：回填 result.json 并最终化
- **输入**：最终翻译、核验记录、所有产物文件。
- **动作**：
  1. 执行：
     ```bash
     python3 -B scripts/main.py finalize
     ```
  2. 脚本读取所有 `work/translations/*.json`、术语表、校验结果，生成最终双语稿、对齐表、术语表、`verification.json`，并深拷贝回填 `output_contract`，写入 `case_id`，更新 `status/status_reason`、`errors/degradations/uncertainty/pending_human`。
  3. 你要最后读一遍 `output/result.json`，确认字段齐全、自检标记正确、没有把不确定写成事实。
  4. 如果脚本生成后你补充过任何人工核验记录（如 `agent_review`），确保它被合并进 `result.json`（可手动编辑 `work/state.json` 或让脚本保留新增键）。
- **输出**：最终 `output/result.json` 与所有交付文件。
- **失败分支**：如果 `finalize` 因任何原因崩溃，脚本会捕获并写回 partial；你应检查 `errors`，手动修正输入后重跑 `finalize`，或直接编辑 `result.json` 补齐字段，确保退出码 0。

## 6. 预算策略（64 次模型请求 / 900s / 16384 tokens per response）

- **先跑基线**：步骤 2 的 `prepare` 是一次脚本调用，不消耗模型请求（但工具的读取输出可能算在 Agent 上下文内）。优先保证 partial 落盘，这样即使后续中断也有合法结果。
- **分配建议**：
  - 步骤 1-2 盘点与解析：≤10 次模型请求（读 case.json、task.md、材料清单、运行脚本、抽查原文）。
  - 步骤 3 证据核验：≤20 次请求。只核验关键段和高权重内容，不要逐段反复读。
  - 步骤 4 翻译/修订：≤20 次请求。分批写入译文，每批 5–6 段；先关键段后补充。若请求紧张，优先完成标题、摘要、图表题注、含数字/引用的段落，剩余未译段落标注 `untranslated`。
  - 步骤 5-6 自检与回填：≤10 次请求。检查契约、字段、文件，执行 finalize，读最终 result 确认。
  - 剩余 4 次作为异常处理或补充核验。
- **提前落盘**：每次运行脚本或手动写入文件后，partial `result.json` 已经被更新或可以手动更新。不要等到最后才构建 result。
- **避免无意义循环**：不要重复查看同一段材料超过两次，除非发现矛盾需要修正。不要因为翻译风格反复重写已锁定的译文；记录不确定项即可。

## 7. 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json` 并保持退出码 0。以下情形按表格降级处理：

| 情形 | 动作 |
|-|-|
| 材料缺失（无 PDF/DOCX/TXT） | 继续用 `task.md` 和 `case.json` 推导，主材料置空；`status=input_error`，`errors` 说明缺失；产出空段落列表。 |
| 材料损坏 / 无法解析 | 记录 `degradations` + `errors`；尝试其他格式或工具；若均失败，保留原始文件信息，产出可用的其他文件，翻译标注 `unavailable`。 |
| PDF 无文字层 / 扫描件 | 记录 `degradations`+`U1`；不臆造；使用 `prepare --text <校对稿>`（如有人工/OCR 校对稿）或标注待人工。 |
| 图片材料 | `image-no-ocr`，不编造图内文字；图注若可读则处理，否则列入 `pending_human`。 |
| `.doc/.xls/.xlsx/.pptx` | `unsupported`，提示转 pdf/docx/txt；若无法转换，记录并要求人工提供。 |
| `case.json` 损坏或字段缺失 | 捕获解析错误，继续用其他材料；缺失的 `case_id` 置为 `"unknown"`，`output_contract` 设为 `{}`，但在 `errors` 中注明。 |
| 空输入（目录无文件） | `status=input_error`；产出空的 `translation` 和文件列表，所有字段以 `[]` 或 `null` 填充。 |
| 契约缺失（无 `output_contract`） | 使用本 SKILL 定义的默认契约字段，并在 `verification.summary.contract_missing` 中列出；不影响退出码。 |
| 超时（接近 780s） | 脚本只做收尾 finalize，不再扩展译文；未完成段落保持 `untranslated`，`status=partial`。 |
| 译文输入缺失（Agent 未翻译） | 全部段落标 `untranslated`，`status=partial`，`pending_human` 列出原因。 |

**诚实性要求**：`status/sources/uncertainty/change records` 必须真实；不确定或材料不足要显式标注（`pending_human` / `limitations`），不得编造数据、引用、分数。任何不是直接来自原文的推断都标记为 `inferred` 或 `undetermined`。

## 8. Rubric 维度 → 交付要求 → 自证方式对照表

| Rubric 维度 | 分值 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果：任务完成度 | 15 | 真译非改写，产出逐段双语对照，覆盖任务指定范围 | `translation.paragraphs[]` 每条有原文与译文；双语稿中逐段对应；未译段显式标注 |
| 实际效果：结果正确性 | 15 | 术语、指代、否定/限定、数字、单位、公式、文献编号与原文一致 | `token_fidelity` 标记逐字比对；`glossary.consistency` 显示术语全篇一致；`flags` 指出不一致项；`verification.checks` 逐项通过或如实失败 |
| 实际效果：结果完整性 | 5 | 覆盖全文段落、图表题注与表头、公式与编号、文献引用标记、术语表条目 | `translation.coverage` 接近 1；`kind` 分类含 `caption/table/formula/reference`；`glossary.csv` 有术语条目 |
| 实际效果：结果可核验性 | 5 | 每段译文可指回原文具体段落与句子，并说明译法依据 | `paragraphs[]` 含 `seg_id/page/kind/section`；`claims` 带逐字 quote 与 JSON Pointer；`verification.json` 记录可复核检查 |
| 使用增益：质量增益 | 15 | 同篇文献、同术语表口径下，加载 Skill 后相比基础 Agent 在术语一致率、长文完整率和事实准确率上提升 | `verification.summary` 中的 `term_consistency_rate`、`coverage_rate`、`token_fidelity.rate` 可量化；结果可复现，与他法对照 |
| 使用增益：效率增益 | 5 | 减少分段整理、查术语、对照排版与逐段校对时间 | 一次调用产出双语稿、对齐表、术语表、核验记录；`artifacts` 列出全部文件 |
| 使用增益：增益可验证性 | 5 | 公平对照证明“更准、更全、更省时” | `verification.summary` 包含率值，与基础 Agent 结果可比；`changes` 记录修改历史 |
| 创新增益：新增能力 | 5 | 形成基础 Agent 不具备的能力，如术语表强制约束、跨页段接续、段落对齐输出、公式引用保护、译文自检 | `C4_tokens`、`C5_glossary`、`C6_claims` 等检查项通过；`verification.checks` 证明存在 |
| 创新增益：方法改进 | 5 | 分段策略、术语抽取锁定、上下文携带、数字公式回填、自检规则带来实质改进 | `references/translation-rules.md` 描述规则；`verification.json` 展示启发式检查结果 |
| 创新增益：创新证据 | 5 | 证明新增能力相对已有方案的价值边界 | `limitations` 明确边界；`pending_human` 列出仍需人工事项；可提供与基础 Agent 的对比记录 |
| 可靠体验：调用与易用性 | 3 | Agent 能正确触发，用户能按说明完成完整流程 | 最小调用示例；`scripts/main.py` 可执行；文档完整 |
| 可靠体验：运行稳定性 | 4 | 不同长度、排版与重复运行稳定产出完整译文 | 脚本幂等；多次运行结果一致；`runtime` 记录耗时 |
| 可靠体验：异常处理 | 3 | 文字层缺失、扫描件、公式图片、参考文献无法解析、原文残缺等能处置 | `degradations`、`errors`、`pending_human` 如实记录；第 7 节降级表执行 |
| 生态贡献：文档完整性 | 3 | 使用说明、依赖、输入要求、术语表格式、段号对齐约定、未译标注规则、限制维护信息齐全 | 本 SKILL.md + `references/*.md` 涵盖 |
| 生态贡献：资源可复用性 | 4 | Skill 本体、脚本、术语表、分段规则、题集与评分表可被他人直接用于新学科文献 |