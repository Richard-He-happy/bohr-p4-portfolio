---
name: literature-qa
description: 文献智能问答。读取带段落编号的英文论文文本与中文问题清单，由 Agent 亲自逐题阅读原文、整合证据并撰写完整回答；每条论断绑定段落编号与逐字引文，材料未报告时明确说“未报告”。先运行脚本生成完整基线，再由 Agent 核验增强，确保完整、可核验、真实推导，适用于论文精读问答、数值与条件核验、跨章节整合与“论文是否报告 X”类边界判断。
version: 3.0.0
---

# literature-qa（文献智能问答）

## 1. 用途与关键声明

本 Skill 用于完成“提供带段落编号论文文本 + 中文问题清单 → 产出结构化逐题问答与证据”的任务。输出写入 `/app/output/result.json`，包含逐题回答、论断、证据定位、覆盖范围与异常记录。

**关键声明**：`scripts/main.py` 与 `scripts/core.py` 只是工具。它们负责输入发现、初步检索、基线字段生成与自检，但**最终交付物必须由你（Harness Agent）亲自阅读材料、推导、撰写/制作**。严禁把脚本生成的骨架、模板答案直接当作成品。正确做法是：先运行脚本获得完整基线（保证字段与文件齐全），然后 Agent 逐题核验证据、重写答案、补全不足，并留下 `reviewed_by_agent`、`verification`、`changes` 等真实工作痕迹。

所有材料内容必须从 `/input` 实际解析；不得依据文件名或领域标签猜测，不得使用外部知识，不得编造数据、引用或章节。

## 2. 运行契约与目录约定

- 输入：`/input/case.json`、`/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。
- 工作目录：`/app/work`（可写）。最终主产物必须落在 `/app/output`。
- 主产物：`/app/output/result.json`。可额外写 `/app/output/answers.json`、`paragraph_index.json`、`evidence_map.csv`、`verify_report.json`；`/app` 可写时另写兼容件 `/app/answers.json`。
- 脚本调用（仅使用 Python 标准库，无第三方依赖）：
  - 完整基线：`python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output`
  - 补丁应用：`python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output --apply /app/work/answers_patch.json`
  - 查看参数：`python3 -B /skills/literature-qa/scripts/main.py --help`
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行秒级完成，不占模型请求。
- 退出码：任何情况下都必须为 0，并产出合法 `result.json`。脚本第一步先写 partial `result.json`，异常时写入 `errors`，最后无条件 finalize 覆盖。

## 3. 输出契约（必须完整回填）

`result.json` 顶层必须包含：
`case_id`、`paper_id`、`material_version`、`status`、`summary`、`result{answers,unanswered_parts,coverage}`、`answers`（= `result.answers` 镜像）、`claims`、`uncertainties`/`uncertainty`、`sources`、`pending_human`、`errors`、`degradations`、`changes`、`counts`、`verification`、`primary_result`、`method_notes`、`runtime`、`contract_keys`、`question_ids`。
并**原样回填**输入 `output_contract` 的每个键，未知键保留，缺值用 `null` 或 `[]` 补足，键名不改。

逐题 `answers[]` 字段：
`question_id`、`question`、`answer`、`conditions`、`status`、`question_type`、`flags`、`sub_questions[{index,question,status,claim_ids,evidence_paragraph_ids}]`、`claims`、`unanswered_parts`、`evidence_paragraph_ids`。

状态枚举：
- 整体 `status`：`ok` / `partial` / `insufficient_evidence` / `input_error`
- 逐题与逐子问 `status`：`answered` / `partial` / `insufficient_evidence` / `input_error`
- `claims[].kind`：`reported` / `inferred`

`evidence[]` 每条必须包含：`paragraph_id`、`quote`（原文逐字子串）、`char_start`、`locator`、`paper_id`。
`claims[]` 每条必须包含：`claim_id`、`text`、`kind`、`evidence[]`、`source_id`。
`coverage` 必须说明已读章节、未读章节及原因、`not_supplied`、`read_status`。
`unanswered_parts[]` 列明未回答部分及原因；没有则为空列表。
`status`/`sources`/`uncertainty`/`pending_human`/`changes` 必须真实，不得掩盖失败。

## 4. 执行流程（编号步骤）

### 步骤 1：盘点输入（预算 2-3 次请求）
**输入**：`/input` 目录、`/input/task.md`。
**动作**：
- 列出 `/input` 下所有文件，读取 `task.md` 确认本题 Runtime contract；
- 读取 `/input/case.json`，提取 `case_id`、`paper_id`、`material_version`、`output_contract`，识别段落结构、问题清单和材料文件路径；
- 若 `case.json` 不存在或坏 JSON，在 `/input/**` 递归找非评测类 JSON（跳过含 `score/gold/rubric/verifier/expected` 的文件）。
**输出**：输入摘要记忆，记录 `sources` 中实际读取的文件与工具。
**失败分支**：输入完全不可读 → 写 `status=input_error`、`answers=[]`、`errors[stage=load_case]` 的合法 `result.json`，退出 0。

### 步骤 2：运行基线脚本（预算 1-2 次请求，脚本不占模型请求）
**输入**：脚本路径。
**动作**：执行 `python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output`，产出完整基线 `result.json`、`paragraph_index.json`、`evidence_map.csv`、`verify_report.json`，保证所有 output_contract 字段存在。
**输出**：基线产物落盘 `/app/output`。
**失败分支**：脚本异常但退出 0 时，检查 `/app/output/result.json` 是否存在；若不存在，手动写最小合法 `result.json`（含空业务字段、`errors`、`degradations`），然后继续。

### 步骤 3：真实解析材料（预算 3-8 次请求）
**输入**：`/input` 中材料文件、步骤 1 摘要、`paragraph_index.json`。
**动作**：
- 若材料为 PDF/DOCX/CSV/图片，用平台提供的解析工具（如 pdf-text-tool）真实读取文本；如果是 JSON 内嵌段落，逐段读取摘要、正文、表格文字、图注、参考文献；
- 核对段落编号、章节标签；识别数值、单位、比较对象、实验条件；
- 将表格行展开为“表头: 值”序列，图注作为伪段落纳入；
- 确定材料未提供的对象，写入 `coverage.not_supplied`。
**输出**：可用于检索的段落索引与材料结构记忆。
**失败分支**：某文件损坏或不支持格式 → 记录 `errors`/`degradations`，跳过该内容，列出 `coverage.sections_unread` 与原因；不得编造内容。

### 步骤 4：构建/核对证据（预算 10-20 次请求）
**输入**：问题清单、段落索引、基线 `evidence_map.csv`。
**动作**：
- 对每个问题（含子问）进行中英同义词检索（可复用基线检索结果），定位原文段落；
- 核对关键数值、单位、条件、比较对象；摘录逐字短引文（15-60 词）并记录段落编号、字符偏移；
- 区分 `reported` 与 `inferred`；条件绑定到 `conditions`；
- 若基线已有 claims，逐条验证引文逐字性、数值单位匹配、段落编号有效性，修正错误；
- 找不到依据的问题，标 `insufficient_evidence`，记录 `zero_hit_terms`，不再反复搜索。
**输出**：每个问题的证据包（段落、引文、claim 草稿），可存 `/app/work/evidence_draft.json`。
**失败分支**：某子问证据不足 → 保留 partial，写入 `unanswered_parts`；避免在单一问题上消耗过多预算。

### 步骤 5：Agent 产出完整成品（预算 20-30 次请求）
**输入**：证据包、基线 `result.json`。
**动作**：
- 由 Agent 亲自为每个问题撰写中文 `answer`，覆盖所有子问，语言自然但严谨；数值、单位、条件与原文一致；
- 每个关键数值建立独立 claim；非数值题也可为每条证据建立原文摘录 claim；
- 更新 `answers[]`、`claims[]`、`unanswered_parts[]`、`coverage` 等字段到 `/app/output/result.json`；
- 若不便直接编辑 JSON，可写 `/app/work/answers_patch.json`，运行 `--apply` 应用补丁；补丁被拒时保留基线回答并记录 `pending_human`。
**输出**：更新后的 `/app/output/result.json`，包含 Agent 撰写的完整回答和核验后的 claims。
**失败分支**：时间不足无法完成全部改写 → 保留基线答案，相关题标 `partial`，记录 `pending_human`，仍为合法产物。

### 步骤