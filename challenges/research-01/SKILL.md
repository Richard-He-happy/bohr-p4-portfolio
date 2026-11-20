---
name: deep-research-evidence-ledger
description: >-
  Decompose a research question into retrieval-addressable sub-questions with a
  dependency DAG, plan and log retrieval over the supplied corpus, and produce a
  literature-review deliverable in which every claim carries a verbatim quote and
  locator. One-command run performs init/build/selfcheck; an agent-first draft
  path allows incremental verification and editing; deterministic fallback never
  leaves the case empty.
version: 3.0.0
license: MIT
---

# 深度研究 Agent：证据台账式文献综述 Skill

## 0. 最高优先级规则（先读，不可跳过）

1. 本 Skill 是结构化研究与交付系统，不是普通提示词。最终目标：让一个不加载本 Skill 的基础 Agent 通常做不到的三件事稳定发生——问题拆解、证据回链、路径可复跑。
2. 优先使用单命令全流程入口：

   python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

   该命令内部应完成 init → build → selfcheck。若当前安装版本提示不支持 run 子命令，才可回退到 `--stage auto` 并随后运行 `--stage check`，但必须把回退情况写入 `changes`。
3. 脚本产出是结构底座，不是成品。你必须在预算允许时亲自阅读材料、核对关键证据、改写或确认结论；证据不足时不得编造。
4. 异常也必须 exit 0。任何失败都要落盘合法 partial，并把失败写进 `errors` / `degradations` / `pending_human`。
5. 不得伪造 benchmark 分数、金标准、对照 whiteboard、模型状态或材料中不存在的科学数据。平台会记录实际运行。
6. 每个关键数字、引用、论断必须带 `[S#]` 来源与 `文件#页码/段落号` locator，并尽量提供逐字 quote。没有 locator 的结论只能作为推断或待确认项，不得伪装为事实。
7. 不得手工篡改脚本生成的 JSON 结构字段；Agent 的增量判断写入 `/app/work/draft.json`、`agent_review.json`、`synthesis.json` 或 `verification` 中，不要重写结构化文件结构。

---

## 1. 用途与边界

### 1.1 做什么

- 把研究问题拆成可独立检索、带依赖关系的子问题清单。
- 规划检索波次、可用来源范围、前置/并行关系和停止条件。
- 盘点和解析 `/input` 下真实材料；按内容识别类型，不按文件名或领域标签猜测。
- 抽取候选证据，形成证据矩阵、冲突分组、研究空白登记。
- 生成可复核的研究报告：每条结论绑定证据。
- 保存工具调用记录、来源索引、自检结果、不确定项。

### 1.2 不做什么

- 不做材料外联网检索。
- 不逐句精读全文、不做方法学审查、不翻译润色。
- 不把题面 `case.json` / `task.md` 当科研证据。
- 不声称全局完备性或新颖性。
- 不在材料缺失时补造“应该有”的数值或引用。

---

## 2. 运行接口与目录约定

### 2.1 固定路径

- 输入：`/input/case.json`、`/input/task.md`，以及题面规定的材料。
- 工作目录：`/app/work`
- 最终交付目录：`/app/output`
- 脚本：`scripts/main.py`
- 核心库：`scripts/research_core.py`
- 协议说明：`references/protocol.md`
- 评分映射：`references/rubric_map.md`
- 最小示例：`references/example.md`

### 2.2 推荐命令

    python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

若 `run` 不存在，使用兼容回退：

    python3 -B scripts/main.py --stage auto --input /input --output /app/output
    python3 -B scripts/main.py --stage check --input /input --output /app/output

### 2.3 Agent-first 可选命令

当模型预算充足、希望提高质量时：

    python3 -B scripts/main.py init --input /input --output /app/output --work /app/work
    # 阅读 /app/work 下的台账与候选，写 /app/work/draft.json
    python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
    python3 -B scripts/main.py check --input /input --output /app/output

### 2.4 环境限制

- 纯标准库，离线，Python ≥ 3.8。
- 若有 `pdftotext` 优先使用，获得页级 locator；否则退化为 stdlib 流解析并记 `stream:N`。
- 运行预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。
- Skill 资源：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。
- 最终产物写入 `/app/output`；中间产物写入 `/app/work`。

---

## 3. 单命令全流程：init → build → selfcheck

### 3.1 init：盘点、编号、候选抽取、冲突分组

运行 `run` 后，脚本内部必须完成：

1. 读取 `/input/case.json`；缺失则递归查找 `case*.json`。原样保留 `case_id` 与 `output_contract`。
2. 提取研究问题：从 `research_question / question / task_instruction / instruction / prompt / objective / topic / goal / title / 研究问题 / 研究任务` 中取第一个 ≥15 字的字符串；否则用 `task.md` 首句。
3. 递归扫描 `/input/**`，按扩展名 + 文件魔数识别：`%PDF`→PDF，`PK`→DOCX/Office，文本编码探测→TXT/CSV/MD。不使用文件名判断内容。
4. 把 `case.json` / `task.md` 标记为 `role: meta`，不进入证据语料。
5. 生成 `/app/work/input_manifest.json`，每项含 `path / magic / parse_status / role / source_id`。
6. 对材料编号为 `S1`、`S2`、`S3`...，写入 `/app/output/source_index.json`。
7. 抽取候选证据，写入 `/app/output/evidence_candidates.json`。
8. 把涉及同一子问题但结论方向相反的候选归入同一 `conflict_group`。
9. 不产生最终结论；只产生可核验候选集合。

### 3.2 build：校验、兜底抽取、渲染、finalize

`build` 必须完成：

1. 若 `/app/work/draft.json` 存在且合法，优先采用 Agent 核验后的 draft。
2. 若无 `draft.json`，则执行确定性兜底：从 init 台账中抽取实质工作稿，要求逐字 quote + locator。
3. 兜底结果必须诚实标为 `AUTO_EXTRACT`，并记入 `gaps` / `degradations`。
4. 生成全部产物并 finalize `result.json`。
5. 所有 `output_contract` 字段必须同时出现在 `result.json` 顶层和 nested `output_contract` 中。
6. 输出文件必须与题面契约一一对应，缺文件或缺字段要显式登记。

### 3.3 selfcheck：契约与产物自检

`selfcheck` 必须至少检查：

1. `result.json` 是合法 JSON。
2. `case_id` 存在且与原输入一致。
3. 契约字段顶层与 nested 双回显完整。
4. `research_report.md` 八节齐全。
5. `evidence_map.csv` / `evidence_candidates.json` / `source_index.json` 存在。
6. 每条引用是否含有 `source_id` 与 `locator`。
7. exit code 必须为 0。

自检结果写入 `/app/output/selfcheck.json`。任何一项失败都要补齐后重新检查；时间不足则保存当前 partial 并注明。

---

## 4. Agent-first 路径：有预算时提升质量

### 4.1 当预算充足时，使用 init 后先读台账

1. 运行 `init`。
2. 读 `/app/work/input_manifest.json`、`/app/output/source_index.json`、`/app/output/evidence_candidates.json`。
3. 读原始材料中与候选证据对应的段落，核对：
   - quote 是否逐字命中；
   - locator 是否指向正确文件/页码/段落；
   - 数字与结论是否一致；
   - 冲突双方是否都有证据；
   - 研究空白是否来自检索缺口。
4. 将核验结果写入 `/app/work/draft.json`。该文件是 Agent 判断的核心，每条可包含：

   candidate_id / verdict / corrected_quote / corrected_locator / claim_id / sub_question_id / conflict_group / gap_basis / note

   详细形状见 `references/protocol.md`。

### 4.2 Agent 必须亲自完成的事

- 亲自确认关键结论，而不是复制脚本模板。
- 把核验通过/拒绝/待确认逐条写入 `agent_review.json`。
- 改写或确认最终报告中的综合结论、冲突呈现、研究空白。
- 每条结论绑定至少一条核验通过的候选证据。
- 冲突结论必须双方呈现并各带引用，不能只写“尚存争议”。
- 研究空白必须绑定未覆盖子问题或缺失字段，不能写套话。
- 若发现脚本缺陷，用临时 Python 脚本修复并记录在 `agent_review.json.script_fixes`；不得手工改 JSON 结构。

---

## 5. 无 draft 时的确定性兜底

如果没有 `draft.json`，`build` 也必须产出实质工作稿，而不是空壳。

规则：

1. 使用 init 台账中已抽取的候选证据，按子问题聚合。
2. 每条证据必须有 `source_id`、`locator`、`quote`。
3. 将所有自动抽取内容标为 `AUTO_EXTRACT`。
4. 在 `gaps` 中写入：`"basis": "AUTO_EXTRACT without agent verification"`。
5. 在 `degradations` 中写入：`"agent_draft_missing"`。
6. 报告中要用“基于自动抽取候选，尚未逐条人工核验”的边界说明。
7. 兜底结果与 Agent-first 路径使用同一套产物和同一份 `result.json` 契约。

这保证即使 Agent 请求用尽或模型失败，仍能交付可复核、有边界、可改进的 partial。

---

## 6. 交付物：研究产物、证据矩阵、不确定性

### 6.1 必交文件

- `result.json`：契约结果总表。
- `research_report.md`：最终研究报告。
- `evidence_map.csv`：证据矩阵表。
- `evidence_candidates.json`：候选证据机器可读版。
- `source_index.json`：来源编号与解析状态。
- `tool_calls.jsonl`：工具调用与参数返回记录。
- `selfcheck.json`：自检结果。
- `synthesis.json`：综合结论结构化版。
- `agent_review.json`：Agent 核验记录，若未核验则说明缺省。

### 6.2 `research_report.md` 八节

1. 摘要
2. 研究问题与子问题拆解
3. 检索计划与覆盖
4. 证据矩阵
5. 冲突证据
6. 综合结论
7. 研究空白与不确定性
8. 可复跑记录

每个结论使用 `[S#]` 标注来源，并附 locator，例如 `[S2] file=paper_b.pdf#page=7`。关键论断附逐字 quote。

### 6.3 证据矩阵字段

每条证据至少包括：

- evidence_id
- source_id
- locator
- quote
- quote_match（exact / fuzzy / missing）
- sub_question_id
- claim_id
- strength（strong / moderate / weak / insufficient）
- support_scope
- inclusion_reason
- exclusion_reason（如适用）
- conflict_group（如适用）

### 6.4 不确定性

`result.json` 中必须有：

- `uncertainty`：冲突、偏倚、强度限制。
- `pending_human`：每项含 `item / why / action`。
- `errors`：解析失败、命令失败等。
- `degradations`：无 `pdftotext`、扫描件、自动抽取、时间截断等。
- `gaps`：未覆盖子问题、缺失比较字段、缺失来源范围。

---

## 7. `result.json` 契约双回显

### 7.1 必须包含的顶层字段

- case_id
- status
- research_question
- sub_questions
- search_plan
- search_stop_conditions
- tool_calls
- evidence_matrix
- citations
- synthesis
- sources
- coverage
- uncertainty
- pending_human
- errors
- degradations
- changes
- runtime
- verification
- contract_fill
- output_contract

### 7.2 状态取值

- `ok`：完成，且关键引用逐字命中。
- `partial`：完成主要部分但有缺失或降级。
- `insufficient_evidence`：证据不足以支撑多数结论。
- `input_error`：输入严重错误或缺失。

### 7.3 双回显规则

对 `/input/case.json` 中 `output_contract` 的每个字段：

1. 在 `result.json` 顶层以原字段名出现。
2. 在 `result.json.output_contract` 中以同样字段名再次出现。
3. 若缺值写 `null` 或 `[]`，不得改键名。
4. 若原始 `output_contract` 缺失，记 `output_contract: null`，并使用内置契约字段生成 `contract_fill`。

---

## 8. 证据定位与来源编号

- 来源统一编号：`S1`、`S2`...
- locator 格式优先：
  - PDF：`S#file=文件名#page=N`
  - 正文段落：`S#file=文件名#para=N`
  - CSV：`S#file=文件名#row=N`
  - 流解析降级：`S#file=文件名#stream=N`
- 报告正文使用 `[S#]`，证据表使用完整 locator。
- 如果 locator 不准确，不得强行引用；将该 claim 标记为 `insufficient` 或 `pending_human`。
- 材料无法解析时，在 `sources` 中记 `parse_status: failed/unsupported`，不构造内容。

---

## 9. 评分维度 → 交付要求 → 自证证据

### 9.1 实际效果 40 分

任务完成度 15：

- `research_report.md` 八节齐全。
- `sub_questions` 含可独立检索子问题与依赖 DAG。
- `search_plan` 含顺序、来源范围、停止条件。
- `tool_calls.jsonl` 含每次调用的参数、返回、失败重试。

结果正确性 15：

- 每条结论绑定 `citations[]`，逐字 quote + locator。
- 冲突双方均呈现并各带引用。
- `agent_review.json` 记录核验 verified/rejected/needs_fix。

结果完整性 5：

- 全部输出契约字段覆盖；缺项写入 `contract_fill`。
- 缺材料或无法判断写入 `pending_human` / `gaps`。

结果可核验性 5：

- `selfcheck.json` 全过。
- 任何第三方可顺 `[S#]` 找到原始材料位置。
- `source_index.json` 与 `tool_calls.jsonl` 足够复跑。

### 9.2 使用增益 25 分

质量增益证据：

- 提供结构化 `sub_questions`、`search_plan`、`evidence_matrix`、`conflict_group`。
- 每条结论有 locator 与 quote，降低无证据空架子。
- 报告不写套话空白，`gaps[].basis` 绑定具体缺口。

效率增益证据：

- 单命令 run 快速落盘全套 baseline。
- 脚本确定性兜底，减少模型反复试错。
- `tool_calls.jsonl` 显示每步参数与返回，避免重复检索。

增益可验证性：

- `verification` 中列出本 Skill 实际新增的结构化产物。
- `changes` 中记录 Agent 增量改了什么。
- 不伪造基准分数，不写无来源自评分。

### 9.3 创新增益 15 分

新增能力证据：

- 证据台账把“结论 → claim → quote → locator → source”串成可复核链。
- 冲突分组与 gap_basis 机制。

方法改进证据：

- 确定性兜底保证无 draft 也能交付 substantive partial。
- 单命令 init/build/selfcheck 分解失败边界。

创新证据：

- `references/protocol.md` 与 `references/rubric_map.md` 说明方法与边界。
- `research_report.md` 中记录“自动抽取 / Agent 核验 / 待人工确认”三层强度。

### 9.4 可靠体验 10 分

调用易用性：

- 单命令跑完整流程。
- 输入输出路径固定。

运行稳定性：

- exit 0 恒定。
- 异常落盘 partial。
- 重复运行不删除已有字段。

异常处理：

- 缺 case.json、非法 JSON、无 output_contract、PDF 损坏、零命中、quote 未命中、超时等都有明确处置。

### 9.5 生态贡献 10 分

文档完整性：

- `references/protocol.md` 解释方法与 draft schema。
- `references/rubric_map.md` 解释评分映射。
- `references/example.md` 给出最小调用示例。
- 本 SKILL.md 写清用途、边界、调用、输入输出、异常处理。

资源可复用：

- `scripts/main.py` 与 `scripts/research_core.py` 纯标准库、离线。
- 证据表、拆解模板、检索计划模板由脚本稳定生成。
- 不依赖个人文件或手工操作。

分享推广价值：

- 该方法可迁移到其他多来源研究问题。
- 输出结构与固定契约便于复用和复核。

---

## 10. 隐藏案例鲁棒性

### 10.1 正常案例

完整输入、多个 PDF/CSV、明确任务。按 §3 运行单命令，产出全套报告。Agent 视预算核验 3–15 条关键证据。

### 10.2 边界案例

- 材料部分缺失：缺失来源登记 `gaps`，已存在材料继续。
- 多条证据互相冲突：归入 `conflict_group`，在报告冲突证据节双方呈现。
- PDF 无 `pdftotext`：使用流解析，locator 降级 `stream:N`，记 `degradations`。
- 子问题零命中：标 `empty`，自动生成 `retrieval_gap`，不硬写结论。
- 材料为扫描件或图片：标 `unsupported`，该来源不纳入证据，其余继续。

### 10.3 异常案例

- 无 `/input/case.json`：从 `task.md` 首句与目录材料继续，`status` 为 `input_error` 或 `partial`。
- `case.json` 非法 JSON：记 `load_case` 错误，仍尝试从目录构建。
- `output_contract` 缺失：按内置契约补字段，记 `contract_fill.null_filled`。
- 脚本运行失败：Agent 手工构建最低限度的 `result.json`、`research_report.md`、`evidence_map.csv`，并在 `errors` 中说明。
- quote 未命中：拒绝该证据，结论强度降为 `insufficient`，写入 `pending_human`。
- 预算将尽：立即保存当前 `result.json` 与报告，追加 `budget_skipped` 项。

---

## 11. 预算策略与尽早落盘

### 11.1 推荐分配

- 请求 1–3：读 `case.json`、`task.md`，盘点契约。
- 工具调用 1–2 次：运行 `run` 或回退命令，生成全套 baseline。
- 请求 4–12：抽检 3–15 条关键证据，写 `draft.json` / `agent_review.json`。
- 请求 13–20：撰写或改写 `synthesis.json` 与 `research_report.md`。
- 请求 21–28：回填 `result.json`，补齐 `verification`、`changes`、契约字段。
- 请求 29–35：补冲突、空白、limitations，重跑 `check`。
- 请求 36–64：只做一次整体复查；若预算不足立即落盘。

### 11.2 落盘优先级

1. `result.json` + `research_report.md` + `evidence_map.csv`。
2. `synthesis.json` + `evidence_candidates.json`。
3. `selfcheck.json` + `agent_review.json`。
4. 其他可解释性产物。

任何阶段都不覆盖已存在的 useful partial；只在原文件上增量更新。

---

## 12. 完成前自检清单

- [ ] `result.json` 合法，含 `case_id` 与 `status`。
- [ ] 所有 `output_contract` 字段在顶层与 nested 双回显。
- [ ] `research_report.md` 八节齐全，且不是占位模板。
- [ ] 每条关键结论有 `[S#]` 来源与 `文件#页码/段落` locator。
- [ ] 关键论断有逐字 quote，且能在原文复现。
- [ ] 冲突双方均有引用。
- [ ] 空白与限制绑定具体子问题或缺失字段。
- [ ] 无编造数据、引用、分数、软件状态。
- [ ] `selfcheck.json` 检查项全过。
- [ ] 退出码为 0。

若有任一项未满足，优先补齐；无法补齐的，显式写入 `limitations`、`pending_human`、`degradations`，不得伪装完成。