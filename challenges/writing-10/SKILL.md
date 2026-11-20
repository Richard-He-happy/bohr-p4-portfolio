---
name: reviewer-response-revision
description: 对指定版本稿件完成受控返修：把审稿意见（含一条意见内的多个子要求）拆成可执行条目，逐条给出决策与语气档，把实质性修改真实落到指定基线稿件，产出可编辑修订稿、逐条回复信、修改定位表、证据清单与结构化 result.json。用于投稿返修、rebuttal/response letter 起草，以及核对“回复信声称的修改是否真的在稿子里”。Use when asked to answer reviewer comments, revise a manuscript against them, draft a point-by-point response letter, or verify that claimed revisions match the manuscript version.
version: 2.0.0
---

# 审稿回复与论文修改（writing-07）

## 1. 用途与最高优先级原则

输入「指定版本稿件基线 + 审稿意见摘要」，输出可直接提交编辑部的返修包：修订稿、逐条回复信、修改定位表、未到位证据清单。本 Skill 解决四个核心问题：**答得全、改得准、证得住、对得上**。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本生成的骨架、模板、默认台账或初步输出直接当作成品。你必须真实读取 `/input` 下的所有材料，理解审稿意见与基线稿件，亲自决定每条意见的处理方式、修改文本、回复措辞和证据定位，然后利用脚本进行定位校验、格式渲染与审计。任何“已修改”声明都必须由你亲自核验其在修订稿中的真实存在。

**受控演练边界（最高优先级，任何输出不得越过）**

- `materials/manuscript-baseline.md` 是组织方基线摘要，`materials/reviewer-comments.md` 是组织方整理的意见摘要，**不是完整原稿，也不是审稿报告逐字全文**。
- 只修订指定基线；只处理实际给出的意见；不补写不存在章节；不臆造数据、文献或统计量。
- 不得声称：“审稿人逐字要求”、“已补做实验/重做分析”、“原作者已改稿”、“编辑部已接收”、“整篇全文返修完成”、“已联网核验原评审”。
- **不得以“材料缺失”为由跳过可执行的实质修改**：基线内能改的必须改；改不了的进 `pending_human`，并在回复信中说明为什么改不了。
- **完整性优先**：先运行本 Skill 自带脚本产出全套基线交付物（所有 output_contract 字段、所有题面要求文件、所有 result.json 字段），然后由你亲自在基线上增强，不得删除、清空或遗漏任何基线与契约字段。若不确定，保留原产物并在 result.json 中标注 `reviewed_by_agent`。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 入口 | `python3 scripts/main.py --input /input --output /app/output --work /app/work` |
| 校验 | `python3 scripts/verify.py --output /app/output --input /input` |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | 恒为 0；失败写入 `result.json` 的 `errors`/`degradations` |
| 第一落盘 | 任何处理前先写 partial `result.json`，结束时无条件覆盖为 final |
| 工作目录 | `/app/work` |
| 最终产物目录 | `/app/output` |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）；接近 780 秒直接 finalize 当前结果 |
| 资源限制 | ≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink |

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则递归找 `/input/**/*case*.json`；JSON 坏掉时记 `errors` 并继续扫描材料。
2. 保留 `case_id` 与 `output_contract` 原样；再读 `task_instruction`、`organizer_workorder`、`organizer_edit_workorder` 等（键名不固定，按语义取）。
3. 递归扫描 `/input/**` 的 `.md/.txt/.rst/.tex`，用语料打分判定基线 vs 意见：文件名含 `manuscript|baseline|draft|paper|稿件` → 基线；含 `comment|reviewer|referee|意见|审稿` 或正文高频出现 reviewer/comment → 意见。
4. 其他附件（PDF/图片/CSV/XLSX/DOCX/JSON）**必须真实解析**：能解析的用 `pdf-text-tool` 等工具提取文本，记录解析结果；无法解析的只登记路径，并在 `pending_human` 里列缺口，不猜内容。**禁止根据文件名或领域标签猜测材料内容。**

## 4. 真实解析与证据构建（必须执行，禁止跳过）

在运行任何修改流程之前，你必须亲自完成以下工作：

1. **读取全部 `.md/.txt` 文本材料**，逐段阅读基线稿件和审稿意见，不得只依赖脚本自动分类结果。
2. **解析 PDF/DOCX/CSV/图片**：使用可用工具（如 `pdf-text-tool`）提取文本；如果工具失败或格式不支持，记录 `degradations`，并在 `pending_human` 中标注“未能解析的材料路径”和原因，不得猜测内容。
3. **提取所有关键事实**：数字、条件、术语、引用、图表编号、统计量、作者声明等，建立事实清单。记录每个事实的来源位置（文件名、段落号、行号或锚点）。
4. **核对审稿意见与基线**：确认意见中每条要求和子要求是否能在基线中找到对应内容；缺失或模糊的内容如实记录。
5. **构建证据基线**：将上述结果写入 `/app/work/evidence_baseline.json`（Agent 亲自撰写，不要直接使用脚本自动生成的空模板），内容包括：`facts`、`sources`、`unresolved_missing`、`parsing_errors`。

## 5. 本题专属执行流程（编号步骤）

### 步骤 0：初始化与盘点输入（预算内 ≤2 次模型请求）

- **输入**：`/input/case.json`、`/input/task.md`、材料文件。
- **动作**：运行 `python3 scripts/main.py --input /input --output /app/output --work /app/work` 生成骨架和初步台账；同时读取 `case.json` 获取 `case_id`、`output_contract`、任务指令。
- **输出**：`/app/work/comment_ledger.json`（脚本初步生成）、`/app/output/result.json`（partial 占位）。
- **失败分支**：若脚本失败或输入缺失，立即手写最小 `result.json` 并落盘，记录 `input_error` 或 `degradations`，继续后续材料扫描。

### 步骤 1：真实解析材料（预算内 ≤6 次模型请求）

- **输入**：`/input/**` 所有文件。
- **动作**：
  - 按 §3 和 §4 要求，用工具解析 PDF/DOCX/CSV/图片，读取全部文本材料。
  - 识别基线与意见文件，提取段落编号 `P###`。
  - 提取事实与来源，写出 `/app/work/evidence_baseline.json`。
  - 检查意见内部是否有多个子要求，逐个编号 `C1.1, C1.2...`。
- **输出**：`evidence_baseline.json`、更新后的 `/app/work/comment_ledger.json`（由你亲自补充决策所需的信息，不要只复制脚本默认值）。
- **失败分支**：材料无法解析或缺失，记录 `pending_human` 和 `degradations`；若无法找到基线或意见，设置 status=`insufficient_evidence` 或 `input_error`，但继续生成合法 result.json。

### 步骤 2：构建/核对证据与意见台账（预算内 ≤8 次模型请求）

- **输入**：`evidence_baseline.json`、审稿意见全文、基线稿件。
- **动作**：
  - 对每条意见及其子要求，确定 `type`（method/data/format/ethics/writing）、`decision`（accept/partial/reject/clarify/invalid）、`tone`（accept/clarify/polite_rebuttal/appeal）、锚点 `anchor`（段落号）。
  - 判断每条子要求是否能在基线内完成修改；不能完成的写明原因。
  - 列出每条修改需要的证据状态 `evidence_status`。
  - 亲自撰写 `comment_ledger.json` 的实质内容，可参考脚本生成的骨架，但全部决策和理由必须是你的真实分析。
- **输出**：最终 `/app/work/comment_ledger.json`（含全部字段）。
- **失败分支**：意见冲突或无法判断，逐条记录 `conflicts` 和 `pending_human`，继续处理其余条目。

### 步骤 3：Agent 亲自产出完整成品（预算内 ≤20 次模型请求）

- **输入**：`comment_ledger.json`、`evidence_baseline.json`。
- **动作**：
  - 对每个 `sub_id`，写出**修订后的原文级文本**。原文必须能逐字在基线中找到，修订文本必须完整替换或插入，数字集合保持原句数字集合超集。
  - 撰写 `/app/work/edit_plan.json`（schema 见 §6）。每个真正可执行的子要求都要有 edit；只有确实超出材料的条目才允许无 edit，并在 `sub_overrides` 中写清 `evidence_status=not_provided` 与理由。
  - 同时亲自撰写以下内容（先写在 `/app/work/`，脚本第二步会合并）：
    - `response_letter_draft.md`：每条子要求一段，包含决策、语气、定位、逐字改后原文、回复说明。须由你亲自遣词造句，不直接粘贴模板。
    - `evidence_pending_draft.md`：未到位证据清单与运行异常。
    - `version_notes_draft.md`：版本、基线名、覆盖率与边界说明。
  - **禁止把脚本生成的空白模板或占位符当成品；必须亲自填充实质内容。**
- **输出**：`/app/work/edit_plan.json`、`response_letter_draft.md`、`evidence_pending_draft.md`、`version_notes_draft.md`。
- **失败分支**：若无法确定某条修改，将其放入 `pending_human`，并在回复信中如实说明；不要跳过或编造。

### 步骤 4：运行脚本应用修改并生成产物（预算内 ≤3 次模型请求）

- **输入**：`/app/work/edit_plan.json`、`/app/work/comment_ledger.json`。
- **动作**：再次运行 `python3 scripts/main.py --input /input --output /app/output --work /app/work`。
- **输出**：脚本根据 `edit_plan.json` 应用修改，生成 `revised_manuscript.md`、`response_letter.md`、`change_locator.json`、`comment_ledger.json`（最终）、`evidence_pending.md`、`version_notes.md`、`pending_human.json`、`result.json`（初版 final）。
- **失败分支**：脚本报告定位失败或无法应用修改，`edit_not_applied` 被记录，对应子要求降为 partial；不得修改原文凑通过，转入步骤 5 修正 `edit_plan.json` 并重跑，或如实保留 partial。

### 步骤 5：自检与增强（预算内 ≤15 次模型请求）

- **输入**：`/app/output` 全部产物、`/input` 材料、`edit_plan.json`。
- **动作**：
  - 运行 `python3 scripts/verify.py --output /app/output --input /input`。
  - **亲自阅读 `revised_manuscript.md` 和 `response_letter.md`**，逐段检查是否每处声称修改都真实存在、定位是否准确、语气是否合适、有无越界声明。
  - 检查 `result.json` 是否回填了原 `output_contract` 的全部键，并且键名不变；缺失则补齐。
  - 检查数字保持：每条改动的数字集合必须是原句数字集合的超集；数字被改动即进 `pending_human`。
  - 若发现脚本生成的产物有模板痕迹或空洞，直接编辑 `/app/output` 下的对应文件进行增强（例如把回复信中的占位文字替换为你亲自撰写的具体说明）。
  - 将增强后的内容同步到 `result.json` 的 `verification`、`evidence_map`、`change_log` 中，标记 `reviewed_by_agent: true`。
- **输出**：更新后的 `/app/output` 全部文件。
- **失败分支**：若时间不足（接近 780 秒）或模型请求用完，立即将当前状态 finalize，保留 partial 并列出未完成项；绝不丢下不合法 JSON。

### 步骤 6：回填 result.json 并最终校验（预算内 ≤2 次模型请求）

- **输入**：`/input/case.json`、`output_contract`、`/app/output` 全部产物。
- **动作**：
  - 确保 `result.json` 包含原 `output_contract` 的全部字段且键名不改；`case_id` 原样保留。
  - 补全 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`issues`、`changes`、`runtime`、`counts`、`comment_ledger_summary`、`workorder_report`、`verification`。
  - 所有 `sources`、`uncertainty`、`change records`、`status` 必须真实，不得编造。
  - 运行最终 `verify.py` 确认无 `ok:false` 或如实保留 partial 并说明。
- **输出**：最终 `/app/output/result.json` 和全部交付物，退出码 0。
- **失败分支**：任何异常都不会导致非零退出；错误全部写入 `errors`，状态设为 `partial` 或 `input_error`。

## 6. edit_plan.json 最小形状

```json
{"edits": [{"id": "E1", "comment_id": "C1", "sub_id": "C1.1", "op": "replace",
            "anchor": "P005",
            "original_quote": "基线中逐字存在的一句",
            "revised_quote": "修改后的完整句子",
            "reason": "为什么改", "decision": "accept",
            "evidence_status": "provided", "response_note": "回复信中的补充说明"}],
 "sub_overrides": [{"sub_id": "C3.1", "decision": "partial",
                    "evidence_status": "not_provided",
                    "evidence_note": "为什么材料内无法完成",
                    "response_note": "回复信中的说明"}],
 "pending_human": [{"item": "C1.2", "reason": "需人工补的输入"}]}
```

`op` 取值：`replace`（默认，按 `original_quote` 定位并替换）、`replace_all`、`append_after`（在锚点段之后插入新段）、`append_end`。

**重要**：`edit_plan.json` 必须由你亲自撰写，不可直接使用脚本生成的空白模板。其中的 `revised_quote` 和 `response_note` 必须是你在真实理解材料后推导出的内容。

## 7. comment_ledger 字段

| 层级 | 字段 |
|---|---|
| 意见 | `comment_id`、`source_label`（原文标题，用于编号对齐）、`raw_summary`、`decision`、`tone`、`change_ids`、`evidence_needed` |
| 子要求 | `sub_id`、`text`、`type`、`decision`、`tone`、`anchor`、`change_ids`、`evidence_status`、`evidence_note`、`needs_human` |

`decision ∈ {accept, partial, reject, clarify, invalid}`；`tone ∈ {accept, clarify, polite_rebuttal, appeal}`，由 `decision` 映射，回复信措辞由模板强制，但必须由你亲自填入具体内容，不得直接复制模板占位符。

## 8. 输出文件

| 文件 | 内容 |
|---|---|
| `revised_manuscript.md` | 唯一主产物：只在基线上做改动，章节层级与编号保持 |
| `response_letter.md` | 逐条回复：每条子要求一段，带 `decision/tone`、`P###` 定位、逐字改后原文 |
| `comment_ledger.json` | 意见→子要求→决策→改动→证据的中枢台账 |
| `change_locator.json` | 每处改动的 `P###` 定位与逐字 quote（可被独立核验） |
| `evidence_pending.md` | 未到位证据清单与运行异常 |
| `version_notes.md` | 版本、基线名、覆盖率与边界说明 |
| `pending_human.json` | 需人工确认的条目与原因 |
| `result.json` | 契约回填 + 计数 + 核验报告 |

`locator` 语义：`P###` = 交付文件中以空行分段的第 ### 个块（标题也计入），因此可在任意 Markdown 编辑器中独立复核。

## 9. result.json 字段

- 原样回填输入 `output_contract` 的**全部键**（键名不改、缺值 `null`/`[]`、未知键保留）；`case_id` 原样。
- 必有：`status`（ok/partial/insufficient_evidence/input_error）、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`counts`、`comment_ledger_summary`、`workorder_report`、`verification`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`issues`、`changes`、`runtime`。
- `counts` 至少含：意见数、子要求数、已落实数、未到位数、`locator_hit_rate`、各类 decision 计数。
- `verification` 中必须包含 `reviewed_by_agent` 布尔值，并列出你亲自核验的关键论断、数字、引用及结果（verified/pending_human/conflicts）。

## 10. 质量规则（对应评分点）

1. **答得全**：意见数 = ledger 条目数；一条意见内的每个子要求各占一行、各有 `decision`；禁止“已按意见修改”式笼统回复。
2. **改得准**：`revised_quote` 必须能逐字出现在修订稿中（脚本用 `locate()` 校验并写 `hit`）；命中失败即降级为 partial 并进 `pending_human`，绝不改原文凑通过。
3. **证得住**：`evidence_status ∈ {provided, not_provided, not_applicable}`；未补做的写 `not_provided` + 原因，禁止写“已补做”。
4. **对得上**：回复信中的定位直接取自 `change_log.locator`，同一来源生成，天然 join 一致。
5. **不漂移**：每条改动的数字集合必须是原句数字集合的超集（`numbers_preserved`）；数字被改动即进 `pending_human`。
6. **语气**：四档模板化；`reject/invalid` 必须给出复核依据，不得人身或情绪化表达。
7. **完整性**：`result.json` 必须包含 `output_contract` 全部键；任何缺失都必须在 `issues` 中列出并保持 partial。

## 11. 预算策略（64 次模型请求分配）

| 步骤 | 模型请求预算 | 必须/可跳过 | 说明 |
|---|---|---|---|
| 步骤 0 初始化 | ≤2 | 必须 | 先落盘 partial |
| 步骤 1 真实解析材料 | ≤6 | 必须 | 不得偷工减料 |
| 步骤 2 构建台账 | ≤8 | 必须 | 核心决策 |
| 步骤 3 Agent 亲自撰写 edit_plan 与草稿 | ≤20 | 必须 | 高权重交付物，投入最大 |
| 步骤 4 运行脚本 | ≤3 | 必须 | 自动化应用与校验 |
| 步骤 5 自检与增强 | ≤15 | 必须 | 确保质量与真实推导 |
| 步骤 6 最终 result 与校验 | ≤2 | 必须 | 合法 final |

- **优先级**：`result.json`（契约）> `revised_manuscript.md` > `response_letter.md` > `comment_ledger.json` > `change_locator.json` > 其他说明文件。
- **尽早落盘**：步骤 0 后必须存在 partial result.json；步骤 4 后必须存在初版 final；步骤 5 增量改进。
- **避免浪费**：不重复读取同一大文件；如果脚本已提取清晰文本，直接使用；不要无意义循环重试已经成功的解析。
- **超时处理**：接近 780 秒，立即执行步骤 6，将当前所有产物打包 finalize，保留 partial 并列出未完成项。

## 12. 隐藏案例鲁棒性

| 情形 | 处置 |
|---|---|
| 材料缺失 / 损坏 | 记录 `degradations` 和 `pending_human`；如果基线或意见完全缺失，设置 status=`insufficient_evidence` 或 `input_error`；输出占位产物并说明边界，绝不编造内容。 |
| 格式不支持 / 解析失败 | 尝试可用工具；失败则登记路径和错误，不影响其他可用材料的处理。 |
| 空输入 / 契约缺失 | 读取 `case.json`，若缺失 `output_contract`，则创建一个最小合法契约（包含 `case_id` 和常见字段），并标记 `errors`；产出合法 result.json。 |
| 意见冲突 / 意见有误 | 各自独立给 `decision`，在回复信说明取舍规则或引用基线说明出入；冲突项进 `pending_human`。 |
| 基线缺章节 / 无法补实验 | 不新增整章；在现有段落内说明或进 `pending_human`；无法补实验的理由如实写。 |
| 版本不匹配 | 以本次输入的基线为唯一版本；在 `version_notes.md` 记录基线文件名。 |
| 权限/文件不可读 | 记 `errors`，其余流程继续，输出 partial。 |
| edit 定位失败 | `edit_not_applied` + 该子要求降为 partial；绝不强行修改原文凑通过。 |
| 越界声明 | 自动删除该句并记 `overclaim_removed`。 |
| 超时 / 预算耗尽 | 立即 finalize 当前结果，状态设为 `partial`，列出 `issues`。 |
| 任何情况 | 都必须产出合法 `result.json`，退出码 0，不得抛异常导致 evaluator 报错。 |

## 13. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| **实际效果（40）** | 完整返修包：修订稿、回复信、定位表、证据清单；每条意见每个子要求都有明确处理结论；实质修改真实落在修订稿；事实、数据、引用准确；定位可独立核对 | `revised_manuscript.md` 与 `response_letter.md` 逐条对应；`change_locator.json` 中 `P###` 可被检索；`result.json` 的 `verification` 含命中率和核对结果 |
| **使用增益（25）** | 减少人工逐条比对意见、查找行号、重写语气、补齐证据清单的时间 | 清晰台账 `comment_ledger.json` 和 `edit_plan.json`；自动化脚本可重复运行；`response_letter.md` 直接可用 |
| **创新增益（15）** | 意见拆解、定位方式、证据组织与语气控制形成方法改进 | `comment_ledger.json` 的结构化拆解、`change_locator.json` 的锚点定位、`references/taxonomy.json` 的分类法、`templates.json` 的语气模板 |
| **可靠体验（10）** | 正确触发、稳定运行、异常处理完善；长稿件/多意见/冲突/权限不足等能识别并降级 | 退出码恒 0；`result.json` 的 `errors`/`degradations` 完整记录；`pending_human.json` 列出需人工确认项；本 SKILL 的异常处理章节 |
| **生态贡献（10）** | 文档完整、资源可复用、分享价值 | `references/usage.md` 提供完整 schema 和复用指引；`references/taxonomy.json` 和 `templates.json` 可独立使用；SKILL 说明清晰 |

## 14. 自检清单（提交前逐项检查）

- [ ] 已真实读取 `/input/case.json` 和所有材料文件，没有猜测内容。
- [ ] 已运行 `python3 scripts/main.py` 至少两次（第一遍骨架，第二遍应用修改）。
- [ ] 已亲自撰写 `edit_plan.json` 中所有实质内容，没有直接使用脚本空白模板。
- [ ] `revised_manuscript.md` 和 `response_letter.md` 不是脚本生成的占位符，包含具体修改和回复语言。
- [ ] 已运行 `python3 scripts/verify.py` 并处理所有 `ok:false` 或如实保留 partial。
- [ ] `result.json` 包含原 `output_contract` 的全部键且键名不变；`case_id` 原样保留。
- [ ] `result.json` 的 `status`、`sources`、`uncertainty`、`change_log`、`errors` 等真实可信，无编造数据或引用。
- [ ] 每条 `accept` 的修改都有对应的真实 edit 且 `locator_hit` 为 true；`partial` 和 `reject` 有明确理由。
- [ ] 数字保持规则已检查：每条改动的数字集合为原句数字集合超集，否则已进 `pending_human`。
- [ ] 越界声明已扫描并删除，`overclaim_removed` 已记录。
- [ ] 可编辑 Office/幻灯片/图形产物（如有）已额外提供真实渲染的 PDF/PNG 预览。
- [ ] 所有文件位于 `/app/output`；无 symlink；文件数 ≤50、单文件 ≤500KB、总大小 ≤2MB。
- [ ] 明确标注 `reviewed_by_agent`，表示你已亲自核验关键论断和来源一致性。

## 15. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work   # 步骤 0 和 4 各运行一次
# 步骤 1-3 由 Agent 亲自解析材料、构建台账、撰写 edit_plan.json 和草稿
python3 scripts/verify.py  --output /app/output --input /input
```

示意输出（示例）：`counts = {comments_total: 3, sub_requirements_total: 6, subs_with_verified_change: 3, locator_hit_rate: 1.0}`，`status = partial`（因 2 条证据未到位）。此数字来自自造夹具，仅演示接口，不代表正式案例结果。

## 16. 文件清单

```
SKILL.md                 元数据 + 本文档
scripts/main.py          输入发现、段落/意见解析、改稿应用、定位校验
scripts/verify.py        台账构建、回复信渲染、产物审计（可独立运行）
references/taxonomy.json 意见类型词表、语气映射、越界声明词表
references/templates.json 中英文回复信语气模板
references/usage.md      edit_plan 完整 schema、字段说明、自查与复用指引
```

以上文件均为包内真实存在，调用时使用相对路径 `scripts/main.py`、`scripts/verify.py` 等。不得引用其他不存在的文件。

## 17. 维护

- 新增类型/词表只改 `references/taxonomy.json`，不动脚本。
- 调整语气措辞只改 `references/templates.json`。
- 修改脚本后必跑 §14 自检与一次最小夹具回归。
- 本 SKILL 版本 2.0.0，强化了 Agent 亲自推导、完整性优先和预算感知原则。