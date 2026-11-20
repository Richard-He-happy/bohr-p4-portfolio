---
name: deep-research-evidence-ledger
description: Decompose a research question into retrieval-addressable sub-questions with a dependency DAG, plan and log retrieval over the supplied corpus, and assemble a literature-review deliverable in which every claim carries a verbatim quote plus a locator. The bundled scripts produce an evidence-candidate baseline; the harness agent must review, derive and finalize all substantive conclusions itself.
version: 2.0.0
license: MIT
---

# 深度研究 Agent：证据台账式文献综述（完整性优先，Agent 亲自核验版）

## 0. 最高优先级：脚本只是工具，最终交付物由你亲自完成

本 Skill 自带 `scripts/main.py` 与 `scripts/research_core.py`，它们负责解析材料、生成候选证据、渲染基础报告草稿、回填契约字段。但**脚本不是成品**。  
提交前，你（Harness Agent）必须：

1. 亲自读 `/input` 下的材料，确认脚本解析结果与原文一致。
2. 亲自核对关键论断、数字、引用、冲突与空白。
3. 亲自撰写或改写最终的 `research_report.md` 与 `synthesis` 结论，**禁止把脚本模板/占位草稿直接当最终交付物**。
4. 保留脚本产出的全部基线产物；后续优化只能增量增强，不得删除、清空或遗漏任何基线字段与文件。
5. 不确定的内容写入 `pending_human` 和 `limitations`，不编造材料中不存在的数据、引用、分数或状态。

任何情况下都要产出合法 `result.json`，退出码恒为 0。

---

## 1. 用途与边界

把研究问题拆成**可独立检索的子问题**，规划检索波次与停止条件，在**已提供材料**上执行检索并留下可复跑的参数记录，产出「每条论断 → locator + 逐字 quote」的综述、证据矩阵与研究空白。

- 做：问题拆解、检索规划、多步工具调用记录、证据综合、冲突呈现、空白登记、可核验交付。
- 不做：逐句精读、方法学审查、翻译润色、材料外检索。不联网；检索式完整记录供有权者复跑，不据此声称领域完备性或新颖性。
- 适用：给定材料要求综述/证据表/选题评估，或多来源结论不一致需分清冲突与空白。
- 不适用：要求现场联网检索、单篇翻译润色、给出材料中不存在的数值或引用。

---

## 2. 运行契约与目录

- 输入：`/input/case.json`、`/input/task.md` 及题面规定材料（PDF/DOCX/CSV/图片等）。
- 工作目录：`/app/work`；最终产物目录：`/app/output`。
- 基线命令（脚本只负责工具性解析/候选/基础渲染）：

```bash
python3 -B scripts/main.py --stage plan     --input /input --output /app/output
#   读 /app/output/evidence_candidates.json，写 /app/work/synthesis.json
python3 -B scripts/main.py --stage finalize --input /input --output /app/output
python3 -B scripts/main.py --stage check    --input /input --output /app/output
# 一次跑完：--stage auto（默认）
```

- 脚本入口：`scripts/main.py`；依赖：`scripts/research_core.py`；资源定位不依赖 CWD。
- 仅标准库，无网络，Python ≥3.8。有 `pdftotext` 时优先调用以获得页级 locator；否则退化为 stdlib 流解析（`stream:N` 并记 `degradations`）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本软预算 `--budget-seconds 780`，超时先落盘 partial。
- **退出码恒为 0**；异常写入 `errors`，不阻断其他材料。
- Skill 资源限制：最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。

---

## 3. 完整执行流程（按序执行）

### 步骤 1：盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、`/input/**` 全部材料。  
**动作**：

1. 读 `/input/case.json`（缺失则递归找 `case*.json`），原样保留 `case_id` 与 `output_contract`。
2. 研究问题按语义取 `research_question / question / task_instruction / instruction / prompt / objective / topic / goal / title / 研究问题 / 研究任务` 中第一个 ≥15 字字符串；都没有则用 `task.md` 首句。
3. 递归扫描 `/input/**`，按扩展名 + **文件魔数**分类（%PDF→pdf，PK→docx，编码探测→text），不按文件名猜内容。
4. `case.json` / `task.md` 记 `parse_status: meta`，**不进证据语料**，避免把题面当证据。
5. 将材料清单写入 `/app/work/input_manifest.json`，每项含 `path / magic / parse_status / role`。

**输出**：`input_manifest.json`。  
**失败分支**：无 `case.json` 或非法 JSON → 写 `errors`，继续用 `task.md` 首句并扫描目录；`output_contract` 缺失时记 `output_contract: null` 并照常运行。

### 步骤 2：运行基线脚本产出全套候选

**输入**：`/input`，`/app/output`。  
**动作**：运行

```bash
python3 -B scripts/main.py --stage auto --input /input --output /app/output
```

脚本会真实解析材料，生成：

- `result.json`
- `research_report.md`
- `evidence_map.csv`
- `evidence_candidates.json`
- `source_index.json`
- `tool_calls.jsonl`
- `selfcheck.json`

同时把 `output_contract` 的所有字段名回填为 `result.json` 顶层键，键名不变，缺值写 `null`/`[]`。  
**输出**：全套基线交付物。  
**失败分支**：脚本若超时、报错或部分失败，仍应尝试生成合法 partial；若脚本完全无法运行，你（Agent）必须手工解析材料并构建 `result.json`、`research_report.md`、`evidence_map.csv` 等核心产物，并在 `errors`/`degradations` 中如实记录。**不得留空退出**。

### 步骤 3：亲自阅读关键材料与证据候选

**输入**：`evidence_candidates.json`、`source_index.json`、原始材料。  
**动作**：

1. 从 `evidence_candidates.json` 中选出与研究问题最相关的候选证据，通常 3–15 条。
2. 按每个候选的 `locator`（如 `p.7`、`doc~p4`、`row=14`）打开对应原始材料，逐字核对 quote 是否与原文一致。
3. 检查候选证据是否支持对应 claim；检查冲突双方是否都带引用；检查研究空白是否来自实际检索缺口而非套话。
4. 将核验结论写入 `/app/work/agent_review.json`，每条含 `candidate_id / verdict（verified / needs_fix / rejected / pending_human）/ note`。

**输出**：`agent_review.json`。  
**失败分支**：某材料无法打开或解析失败 → 在 `errors`/`degradations` 中记录，不编造核验结论；该候选标 `pending_human`，相应 claim 强度降为 `insufficient`。

### 步骤 4：亲自撰写或改写最终报告与综合结论

**输入**：核验后的候选证据、`/app/work/synthesis.json`（可写）。  
**动作**：

1. 基于核验通过的证据，由你亲自撰写 `/app/work/synthesis.json`，schema 见 `references/protocol.md` §3。
2. 至少包含以下八节内容的最终 `research_report.md`：

   - 摘要
   - 研究问题与子问题拆解
   - 检索计划与覆盖
   - 证据矩阵
   - 冲突证据
   - 综合结论
   - 研究空白与不确定性
   - 可复跑记录

3. 每个 claim 必须引用至少一条核验通过的 `candidate_id`，且包含 locator + 逐字 quote。
4. 冲突结论必须双方呈现并各带引用，不得只写「尚存争议」。
5. 研究空白必须在 `synthesis.gaps[].basis` 中绑定未覆盖子问题或缺失字段，禁止套话。
6. 若可编辑 Office/slide/diagram 是交付物，必须另生成真实渲染的 PDF/PNG 预览；无法渲染则不产出该格式，改用 PDF/PNG 或文本替代，并标注 limitation。

**输出**：`synthesis.json`、改写后的 `research_report.md`。  
**失败分支**：候选证据不足 → 可提高 `--top-k`，或改 `references/protocol.md` 中检索模板后重跑 `plan`；仍不足则 `status: insufficient_evidence`，如实写边界。

### 步骤 5：回填 result.json 并保留 agent 完成痕迹

**输入**：脚本生成的 `result.json`、`agent_review.json`、`synthesis.json`。  
**动作**：

1. 确认 `result.json` 包含 `case_id`、`status`、`research_question`、`sub_questions`、`search_plan`、`evidence_matrix`、`citations`、`synthesis`、`sources`、`coverage`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`tool_calls`、`output_contract_echo`、`contract_fill`、`verification`。
2. 确认 `output_contract` 的**每一个字段名都作为顶层键出现**，缺值写 `null`/`[]`，键名不改。
3. 在 `verification` 中加入 `agent_reviewed: true` 与逐条 `reviewed_claims` 记录；在 `changes` 追加一条 `{"stage":"agent_review","at":"...","detail":"核验并改写了哪些 claims/conflicts/gaps"}`。
4. 若材料不足或无法判断，把具体问题写进 `pending_human`，每条含 `item / why / action`。
5. 诚实设置 `status`：全部完成且引用逐字命中 → `ok`；完成主要部分但有不足 → `partial`；证据不足以支撑多数结论 → `insufficient_evidence`；输入严重错误 → `input_error`。

**输出**：最终 `result.json`。  
**失败分支**：字段缺失 → 补 `null` 并记录 `contract_fill.null_filled`，不得删除已有字段；如不确定是否应保留，保留原字段并追加说明。

### 步骤 6：自检与提交

**输入**：最终产物。  
**动作**：

1. 运行 `python3 -B scripts/main.py --stage check --input /input --output /app/output`。
2. 查看 `selfcheck.json` 七项是否全过（详见 §9）。
3. 人工复核：能否顺 `[n]` 找到 locator 处原文；`status` 与实际完成度一致；`pending_human` 逐条处置。
4. 检查是否有可编辑图形/Office 而缺预览；如有缺漏，补齐预览或删除该产物并标注。
5. 确认退出码 0、`result.json` 合法、全部产物落于 `/app/output`。

**输出**：可提交交付物。  
**失败分支**：任一自检不过 → 定位缺失项，补齐后重新过 check；若时间耗尽快落盘当前 partial 并保留所有已存在文件。

---

## 4. 预算策略（64 模型请求 / 900 秒 / 每响应 16384 tokens）

总原则：**先跑基线，再增量改进；关键交付物优先，尽早落盘 partial**。

| 请求区间 | 必做/可做 | 动作 | 目的 |
| --- | --- | --- | --- |
| 1–3 | 必做 | 读 `case.json`、`task.md`，盘点输入，提取契约 | 确定任务边界 |
| 1–2 次工具调用 | 必做 | 运行 `--stage auto` 产出基线全套 | 获得全套候选与字段骨架 |
| 4–12 | 必做 | 抽检 3–15 条关键证据，核实 quote/locator | 确保“真实推导”与正确性 |
| 13–20 | 必做 | 撰写/改写 synthesis 与 research_report 八节 | 形成完整成品 |
| 21–28 | 必做 | 回填 result.json、`verification`、`changes`、契约字段 | 契约完整 |
| 29–35 | 视情况 | 补冲突、空白、limitations，重跑 check | 增强完整性 |
| 36–64 | 余量 | 只做一次整体复查，不循环；若预算不足立即落盘 | 避免浪费 |

**随时落盘**：完成步骤 2 后立即保存基线；完成步骤 4 后立即写最终报告与 result.json 草稿；之后只做增量修改，不覆盖已成 useful partial。  
**避免**：重复读取同一材料、重复运行脚本、无意义重写；单次响应需紧凑，避免把所有材料一次性读入导致 token 超限。

---

## 5. 隐藏案例鲁棒性与降级

任何情况下都要产出合法 `result.json`，退出码 0。以下为常见异常及其处置：

| 情形 | 处置 | 可见位置 |
| --- | --- | --- |
| 无材料 / 无 `case.json` | 仍写合法 partial，`status: input_error` 或 `partial`，记录缺失 | `errors`、`pending_human` |
| `case.json` 非法 JSON | 记 `load_case` 错误，继续用 `task.md` 与目录材料 | `errors` |
| `output_contract` 缺失 | 记 `output_contract: null`，按内置契约字段回填 | `contract_fill`、`changes` |
| PDF 无 `pdftotext` | stdlib 流解析，locator 降级为 `stream:N` | `degradations` |
| PDF 损坏 / 扫描件 / 图片 | 标 `failed`/`unsupported`，登记缺口，其余材料继续；不构造内容 | `sources`、`pending_human` |
| 子问题零命中 | 标 `empty` 并自动生成 `retrieval_gap` | `coverage`、`gaps` |
| quote 未命中 | 拒收该证据，结论强度降为 `insufficient`，记入 `pending_human` | `errors`、`pending_human` |
| 缺 `synthesis.json` | 只交证据台账，报告写明「未生成结论」 | 报告相应节、`status` |
| 超时 / 请求用尽 | 立即保存当前 `result.json` 与报告，追加 `budget_skipped` 项 | `degradations`、`changes` |
| 脚本运行失败 | Agent 手工构建最低限度 `result.json` + `research_report.md` + `evidence_map.csv` | `errors`、报告 |

**诚实性规则**：所有 `status`、`sources`、`uncertainty`、`changes` 必须真实来自执行过程；不确定或材料不足标 `pending_human`/`limitations`；不编造数据、引用、分数、软件状态。

---

## 6. 评分维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式（具体文件/字段） |
| --- | --- | --- | --- |
| 实际效果：任务完成度 | 15 | 真正走完拆解、检索规划、调用记录、证据综合；六类要点齐全：问题拆解、检索覆盖、证据回链、冲突证据、综合结论、研究空白 | `research_report.md` 八节；`sub_questions`、`search_plan`、`synthesis`；`selfcheck.json` 全过 |
| 实际效果：结果正确性 | 15 | 每条结论与文献段落一一对应；文献真实存在；冲突如实呈现；quote 逐字命中 | `citations[]` 的 `source_id/locator/quote/quote_match`；`agent_review.json`；`evidence_map.csv` |
| 实际效果：结果完整性 | 5 | 覆盖全部 `output_contract` 字段；交付物齐全；partial 标注缺失项 | `result.json` 契约字段；`contract_fill`；`research_report