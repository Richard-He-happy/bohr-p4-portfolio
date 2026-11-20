---
name: plan-compare
description: 把 2–5 个候选实验方案放到同一张可比矩阵上并给出可辩护的选择：统一七类字段（假设/变量/对照/步骤/参数/资源/判读标准），核算耗材+机时+人工成本与含制样/排队/表征/返工的总周期，按预算/周期/机时/参数窗口做硬门可行性判定，做权重敏感性排序，输出选择结论、逐条舍弃理由、风险与异常处置、逐字证据定位，并原样回填输入 output_contract 的全部字段。Use when comparing, selecting or defending among candidate experimental protocols, 实验方案比较与选择, 方案选型, 机时与耗材预算核算, protocol down-selection.
version: 2.0.0
---

# plan-compare — 实验方案比较与选择

脚本只是工具，最终交付物必须由 Harness Agent 亲自读材料、推导、撰写/制作；禁止把脚本骨架、模板或未核验的中间结果直接当成品。先运行自带脚本产出完整基线，再在基线之上做真实证据核验与增量改进，不得删除、清空或遗漏任何基线产物和 output_contract 字段。

## 0. Harness Agent 执行总则（必读）

1. 你面对的是一道真实执行题：必须读取 `/input/case.json`、`/input/task.md` 以及题面给出的实际材料（PDF/DOCX/CSV/图片等），用工具解析真实内容；不得依据文件名或领域标签猜测/补造内容。
2. 本 Skill 的脚本是确定性计算工具，用于字段抽取、成本/周期核算、硬门判定、敏感性排序、矩阵生成、契约回填与自检。它们只保证骨架和计算，不保证研究判断、证据选择、结论文字的学术质量。最终交付物由你本人逐字撰写、逐项复核。
3. 先跑基线：进入任务后立即运行 `python3 -B scripts/main.py --input /input --output /app/output`，得到全套基线交付物。无论后续如何改进，基线中所有 output_contract 字段、所有题面要求文件、所有 result.json 业务字段都必须保留；不确定时保留原产物，并在 `result.json.self_check.agent_review` 中标注 `reviewed_by_agent`。
4. 后做真实核验：把关键数字、引用、约束条件、方案选择理由逐条与材料原文比对；核验结果写进 `result.json.self_check.agent_review`（`verified` / `pending_human` / `conflicts`）和 `result.json.changes`。不要用“应该”“可能”掩盖未核对项。
5. 诚实性高于完成度：不确定或材料不足必须显式标注 `pending_human` / `limitations`；不得编造数据、引用、报价、机时、审批状态或评分。退出码恒为 0，成败看 `result.json.status`。

## 1. 用途与边界

用于“同一目标下有多条可行路线、需横向比较并给出可辩护选择”的任务：把候选方案填进同一套可比字段，算清成本与周期，用硬约束淘汰不可行项，再按加权口径排序，并说明每条被舍弃方案差在哪里。

做：字段归一、成本/周期核算、硬门可行性、权重敏感性、选择与舍弃理由、风险登记、证据定位、缺口与人工确认项。不做：原创实验设计、文献综述、数据统计分析、替组织方编造案例。输入未给出的数值不构造，写入缺口。

## 2. 运行契约

- 输入只读：`/input/case.json`（必需）与 `/input/task.md`、材料文件（可选）。也可用 `--case` 指定路径。
- 输出目录 `--output`（默认 `/app/output`）：`result.json`（必需）、`comparison_matrix.csv`、`decision_record.md`；单独运行 `verify.py` 另写 `self_check.json`。
- 依赖：仅 Python 标准库，无网络；路径基于 `Path(__file__).resolve().parent`，与 CWD 无关。
- 入口：`python3 -B scripts/main.py --input /input --output /app/output`；`--help`、`--version` 可用。
- **退出码恒为 0**（含空输入、坏 JSON、全方案不可行）；成败一律看 `result.json.status`、`errors`、`degradations`。
- 单案例为纯计算，通常 < 1 s；无外部调用，故无中途断点风险，但仍先写 partial 再 finalize。
- 若你（Agent）额外生成可编辑 Office/幻灯片/图形产物（xlsx/docx/pptx/diagram 等），必须同时生成真实渲染的 PDF/PNG 预览到 `/app/output`，并在 `result.json.artifacts` 标注预览文件路径。纯文本产物（CSV/MD/JSON）不需要额外预览，但必须能在磁盘中找到。

## 3. 输入发现（语义识别，不假设键名）

1. 依次找 `case.json` → `input.json` → `case_data.json` → 递归 `case*.json`；解析失败不中断，记 `errors`。
2. 候选方案：先找键名含 `plan / candidate / option / alternativ / proposal / arm / scheme / 方案 / 候选` 的列表；退化为“列表中每个字典至少命中七类字段中的两类”；再退化为“值为字典、键名含方案词”的映射（键名记为 `plan_key`）。
3. 组织方契约（预算、机时费率、人工费率、可预约机时、截止周期）从全树按键名语义抓取，命中位置写入 `cost_model.contract_locators`。含 `hours` 的键视为工时量而非费率。
4. 参数窗口：同时含 `min`/`max`（或 `range`/`allowed`/`domain` 二元组）的字典按父键名登记，与方案参数名做包含匹配。
5. 材料文件全部登记进 `sources`，不按文件名猜内容。对所有 PDF/DOCX/CSV/图片材料，必须用实际解析工具（如 `pdf-text-tool`、CSV 读取器、文档解析器）读取正文或结构化内容；解析失败的材料记录到 `sources[].parse_error`，不得用文件名补造内容。

## 4. 输出契约

`result.json` 顶层固定回填：`case_id`、`status`(`ok`|`partial`|`insufficient_evidence`)、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`；业务字段：`candidate_plans`、`comparison_matrix`、`cost_model`、`time_model`、`feasibility_gates`、`risk_register`、`scoring`、`choice`、`eliminations`、`sensitivity`、`evidence`、`assumptions`、`parameter_table`、`artifacts`、`self_check`。

上述所有字段必须存在，不得因 baseline 或 Agent 改写而丢失。`self_check` 内建议增加 `agent_review` 对象，包含 `{status: verified|pending_human|conflicts, notes, checked_sources, unresolved_items}`；`changes` 用数组逐条记录 Agent 对基线结果的修改、补充或冲突发现。

**契约回填**：读取输入 `output_contract`（字典 / 列表 / `{fields|required|properties:…}` 三种形态均可），把每个字段名**原样**作为键写进 `result.json`，值按语义映射到上表；无对应内容写 `null` 或 `[]`，不改名、不丢字段；`output_contract_map` 记录“契约字段 → 结果字段”。

## 5. 核心流程

1. 写 partial `result.json`（只有 state），随后写入契约骨架（所有字段置 `null`）。
2. `planmodel.find_plans` 定位方案；`build_metrics` 逐方案抽取七字段、成本、周期、风险、参数。
3. `extract_cost`：`total = runs×Σ(qty×unit_price) + fixed + machine_h×rate_m + labor_h×rate_l`（机时/人工为全程总量，耗材按重复次数翻倍）；方案自报总成本存在时做一致性核对（>1% 记为 mismatch）。
4. `extract_time`：分别累计 prep / run / queue / analysis / rework；无阶段数据时用 `(machine_h+labor_h)/8` 估算并标注 `derived`。
5. `scoring.gate_rows`：budget、time_window、machine_hours、param_window 四类硬门，逐项记 `pass/fail/unknown` 与超限量。
6. `scores_for` + `rank`：六分量加权；未声明风险的方案按已声明方案罚分中位数中性计入，不因“没写风险”得满分。
7. `sensitivity_block`：default / equal / cost_led / time_led / risk_led 五组权重重排，算一致率与翻转集合。
8. 生成 CSV 矩阵、决策记录 MD、证据清单；回填契约；`verify.check` 自检后 finalize。

Agent 增强流程必须在步骤 8 生成基线后执行，不得先改脚本再跑基线。增强包括：核对材料原文、补充选择理由、修正证据 quote、标注 pending_human、确认风险处置、补齐人工确认项。

## 6. 口径与评分规则（rubric → 字段/检查/产物）

| 评分关注 | 落点 |
|---|---|
| 可比矩阵 | `comparison_matrix`（21 行固定指标 × N 方案）+ 同名 CSV |
| 数字站得住 | `cost_model`（逐行 qty×单价、机时/人工拆分、自报成本核对）、`feasibility_gates`（超限量） |
| 七字段覆盖 | `candidate_plans[*].fields` 与“字段:x = present/absent”行，缺项进 `uncertainty` |
| 可独立复核 | `evidence`（逐字 quote + locator）+ `self_check` |
| 异常处置 | 硬门 fail→淘汰+回退算术；全不可行→`partial` + 升级项 |
| 增益可验证 | `comparison_basis` 固定公式与权重，换人重跑同分 |

默认权重：完整度 0.30、可行性 0.20、成本 0.20、周期 0.15、风险 0.15。分量归一：成本/周期取“可行集内最小值 / 本方案值”，风险取 `1 − 罚分/(罚分+2)`，罚分按 critical4/high3/medium2/low1 累加。

## 7. 证据与定位

每条证据：`{id, claim, value, source, locator, quote, kind}`，`kind ∈ {measured, pointer, narrative, limit}`。
`locator` 形如 `case.json#/candidate_plans/0/materials/0/unit_price`；`quote` 必须逐字出现在源文件中（数字按原文写法）。
凑不出就降级为 `unknown` 并记入 `uncertainty`，**绝不改写原文**。Agent 核验时若发现脚本抽取的 quote 与源文件不符，必须更正 `evidence` 并在 `changes` 记录冲突。

## 8. 冲突、缺口与人工确认

- 同一量纲出现两个值（契约预算 vs 自报预算）：以契约值判硬门，冲突记入 `uncertainty`。
- 方案间字段不对等：保留不对称，矩阵原样呈现 `present/absent`，不猜测补齐。
- 恒入 `pending_human`：安全与合规审批、设备/耗材可得性、判读阈值冻结；全不可行时追加升级项。

## 9. 中断与预算

先落盘后优化：任何异常都在 `finally` 中 finalize，已算出的部分一律保留；`status=partial` 且 `status_reason` 说明缺口。计算量随方案数与成本行数线性增长，无需分批。

在 64 次模型请求 / 900 秒 / 16384 tokens 预算下，Agent 应优先保证基线落盘，再做关键证据核验。不要在读取全部材料或重写全部文字上浪费请求；每个 PDF 最多解析一次，无法解析立即降级并标注，不重复尝试。

## 10. 异常降级分支表

| 情形 | 处置 | 状态 |
|---|---|---|
| 无 `case.json` / JSON 损坏 | 写契约骨架 + `errors`，`status_reason` 说明 | `partial` |
| 有 case 但无方案列表 | 记缺口，提示确认键名 | `insufficient_evidence` |
| 缺费率/预算/机时 | 对应硬门 `unknown`、成本按已知项求和并标 `missing` | `partial` |
| 方案缺七字段 | 矩阵标 `absent`，`uncertainty` 记缺项 | `partial` |
| 全部方案硬门 fail | 不选方案；给每条的超限量与回退算术（追加预算额、可压缩重复次数） | `partial` |
| 证据 quote 未命中 | `verify` 记 warning，不伪造通过 | 不变，`self_check` 标红 |
| 单方案解析失败 | 仅该方案降级，其余照常比较 | 不变 |

## 11. 自检清单

`python3 -B scripts/verify.py --output … --input …` 全部 PASS：结果可解析、必需键齐全、状态合法、契约字段 100% 回填、成本算术可重算、矩阵列数一致、证据逐字命中率 ≥70%、非选中方案都有舍弃说明、产物存在。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

输入片段（示例）：

```json
{"case_id": "demo", "output_contract": {"comparison_matrix": "…", "choice_summary": "…"},
 "organizer_workorder": {"budget_cny": 80000, "machine_rate_cny_per_h": 320, "labor_rate_cny_per_h": 150},
 "candidate_plans": [{"plan_id": "A", "hypothesis": "…", "steps": ["…"], "parameters": {"T_C": 120},
   "materials": [{"item": "基片", "qty": 12, "unit_price": 450}], "machine_hours": 28, "labor_hours": 46, "runs": 3}]}
```

示意输出（示例）：`status=partial`、`choice={"selected":"A"}`、`cost_model.plans.A.total_cost=32060`、
`feasibility_gates` 中 `budget=pass`、契约字段全部非空。真实数值取决于实际输入。

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `scripts/main.py` | 入口、编排、结果组装、契约回填、落盘 |
| `scripts/planmodel.py` | 语义抽取与成本/周期/风险/参数计算 |
| `scripts/scoring.py` | 硬门、分量归一、排序、差距归因 |
| `scripts/fields.py` | 矩阵、证据、敏感性、契约映射 |
| `scripts/report.py` | 决策记录 MD 与矩阵 CSV |
| `scripts/verify.py` | 确定性自检 |
| `references/comparison_schema.md` | 字段口径、比较矩阵与评分说明 |
| `references/evidence_locators.md` | 证据定位与逐字 quote 规范 |
| `references/checklist_examples.md` | 自检清单与示例 |

版本 2.0.0；标准库 Python ≥3.8。

## 14. 维护

改口径时同步改 `scoring.py`（权重/门限）、`references/comparison_schema.md`（说明）与 `report.py`（表述），改完跑 `verify.py` 确认自检全绿；新增字段优先扩 `planmodel.REQ` 与 `fields.build_matrix`。

## 15. 本题专属执行流程（Agent 必做）

按以下编号步骤执行，每步先做“必须”，再视预算做“可选”。目标优先级：完整基线 > 契约回填 > 结果正确性 > 可核验性 > 可读性。

1. **盘点输入**
   - 输入：`/input/case.json`、`/input/task.md`、`/input` 下全部材料文件、`/app/submission` 下的 SKILL.md 与脚本。
   - 动作：列出 `/input` 目录；读取 `case.json` 和 `task.md`；识别材料文件类型与数量；确认 `output_contract` 形态。
   - 输出：`input_inventory`（可写入 `result.json.sources` 或工作笔记）。
   - 失败分支：若 `case.json` 不存在或损坏，立即运行脚本产出合法 `result.json`（`status=partial`），并在 `errors` 说明缺失路径；不得为了“完整”而编造输入。

2. **先跑基线脚本**
   - 动作：运行 `python3 -B scripts/main.py --input /input --output /app/output`。
   - 输出：`result.json`、`comparison_matrix.csv`、`decision_record.md`；若有可编辑产物，同时检查预览是否生成。
   - 失败分支：脚本若因任何原因未能生成全部文件，手工补齐缺失文件的最小组件；若不能补齐，在 `result.json` 中记录 `degradations`，保持退出码 0。

3. **用工具真实解析材料**
   - 输入：`/input` 下所有 PDF/DOCX/CSV/图片。
   - 动作：对每个材料调用对应解析工具（如 `pdf-text-tool`）；CSV 用标准读取器；DOCX 提取正文；图片 OCR 或标注不可解析。提取关键段落、数字、报价单、参数窗口、设备能力、历史记录。
   - 输出：解析后的关键证据条目（候选表、报价、契约、风险来源），写入 `evidence` 或工作笔记。
   - 失败分支：某材料损坏/格式不支持/OCR 失败，保留该文件路径，标注 `parse_error`，相关字段降为 `unknown`；不得用文件名补造内容。

4. **构建/核对证据**
   - 输入：脚本生成的 `evidence` 与步骤 3 解析结果。
   - 动作：逐条核对 `evidence` 中的 `quote` 是否逐字出现在源文件；核对 `cost_model` 关键单价、机时、人工费率是否来自材料；核对 `feasibility_gates` 的硬门判断是否用对契约值；核对 `choice` 是否与矩阵排序一致。
   - 输出：更新后的 `evidence`；`self_check.agent_review` 写入 `verified` / `pending_human` / `conflicts`；`changes` 记录修正。
   - 失败分支：发现冲突或无法核实，保持原值，标注 `conflicts` 或 `pending_human`；不删改无依据的数值。

5. **Agent 产出完整成品**
   - 输入：基线结果与核验后的证据。
   - 动作：由 Agent 亲自撰写或改写以下内容：`choice` 的选择理由与舍弃理由、`eliminations` 的逐条差距归因、`assumptions` 的边界条件、`pending_human` 的确认项、`decision_record.md` 的可读摘要。不要照搬脚本默认措辞。
   - 输出：完整的 `result.json` 与 `decision_record.md`。
   - 失败分支：若时间或请求不足，至少保留基线文字，标注 `reviewed_by_agent` 未完成项，不得删除基线内容。

6. **自检 rubric**
   - 动作：运行 `python3 -B scripts/verify.py --output /app/output --input /input`；再按本文件第 17 章 rubric 对照表逐项人工自检。
   - 输出：`self_check.json`（可选）与 `result.json.self_check`。
   - 失败分支：若 verify 未全 PASS，优先修复契约字段与必需文件；若无法修复，保留 `partial` 并说明原因。

7. **回填 result.json 并最终落盘**
   - 动作：确保 `result.json` 顶层包含所有原 `output_contract` 字段和本 Skill 约定字段；确保 `case_id` 取自输入；确保所有文件在 `/app/output`；确保退出码 0。
   - 失败分支：任何未完成项写入 `degradations` / `errors` / `pending_human`，不得删字段、不改名、不伪造通过。

## 16. 预算分配与隐藏案例鲁棒性

### 预算分配建议（64 次模型请求 / 900 秒 / 16384 tokens）

- 步骤 1 盘点输入：1–2 次读取 `/input` 目录与关键 JSON。
- 步骤 2 基线上跑：1 次脚本运行调用；若脚本很快，可再跑一次 verify。
- 步骤 3 材料解析：按材料数量分配，每个 PDF/DOCX 最多一次解析；通常 2–5 次。
- 步骤 4–5 证据核验与成品撰写：3–8 次；优先核对影响选择结论的硬门、成本、参数窗口和证据 quote，不逐段重写所有文字。
- 步骤 6–7 自检与回填：2–3 次；只补缺口，不做美学润色。
- 可跳过低价值调用：不重复读同一个大文件、不重复运行 main.py、不逐个检查没有选择影响的字段。
- 触发条件：脚本已生成完整基线后，若时间或请求紧张，立即 finalize，保留基线并标注 `reviewed_by_agent` 范围。

### 隐藏案例鲁棒性

- **材料缺失**：缺少 PDF/CSV/图片时，相关来源标 `missing`，对应数值若脚本已可从 case.json 抽取则继续；否则 `unknown`，`status=partial`。
- **材料损坏**：解析工具报错时，不重复解析超过一次；记录 `parse_error` 和文件路径，证据降为 `limit`，不得补造。
- **格式不支持**：将材料视为不可解析，写入 `degradations`，提示需要人工提供可读版本。
- **超时**：900 秒内至少先落盘 `result.json` 和基线产物；脚本本身 <1s，若 Agent 后续操作接近超时，立即 finalize。
- **空输入**：若 `/input/case.json` 为空或 `{}`，脚本应产出 `status=insufficient_evidence`，契约骨架回填为 `null`，`errors` 说明空输入。
- **契约缺失**：输入没有 `output_contract` 时，不要求回填任何外部字段，但仍输出本文件第 4 章的所有业务字段；`output_contract_map` 标注 `not_provided`。
- **任何情况下**：必须产出合法 `result.json`，退出码 0；状态可 `partial` / `insufficient_evidence`，但不能崩溃或输出空 JSON。

## 17. rubric 维度 → 交付要求 → 自证方式（逐条）

| rubric 维度/分值 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果 40：任务完成度 15 | 把多个候选方案放到同一张可比矩阵上，完成比较并给出可辩护的选择 | `comparison_matrix` 列数等于候选方案数，`choice.selected` 有明确 ID；`eliminations` 逐条说明舍弃理由 |
| 实际效果 40：结果正确性 15 | 方案比较中的数字、来源与最终选择站得住 | `cost_model` 算术可重算；`feasibility_gates` 使用契约值；`evidence` 逐字命中源文件；`self_check.agent_review` 显示 verified/conflicts |
| 实际效果 40：结果完整性 5 | 覆盖七类字段与关键比较维度 | `candidate_plans[*].fields` 七字段 present/absent 行；`comparison_matrix` 覆盖假设/变量/对照/步骤/参数/资源/判读标准 |
| 实际效果 40：结果可核验性 5 | 方案版本、字段取值与选择结论可独立复核 | `evidence` 有 locator + quote；`self_check` 可重跑；`result.json` 含 `case_id` 与所有契约字段 |
| 使用增益 25：质量增益 15 | 相比基础 Agent 提升比较质量 | `comparison_basis` 固定字段与权重；`sensitivity` 一致率；`decision_record.md` 展示可比矩阵和淘汰逻辑 |
| 使用增益 25：效率增益 5 | 减少对齐字段、查单价、核算机时与人工修改量 | `cost_model` 自动汇总 qty×unit_price、机时/人工；CSV 可直接复核；`artifacts` 列出自动生成文件 |
| 使用增益 25：增益可验证性 5 | 通过公平对照证明质量或效率改善 | `scripts/verify.py` 与 `references/checklist_examples.md` 给出确定性复跑路径；`result.json.changes` 记录 Agent 增量 |
| 创新增益 15：新增能力 5 | 形成基础 Agent 不具备的稳定比较能力 | `scripts/planmodel.py` 语义抽取、`scripts/scoring.py` 硬门与敏感性；`references/comparison_schema.md` 说明方法 |
| 创新增益 15：方法改进 5 | 比较字段设计、评分矩阵、淘汰规则与证据挂载有实质改进 | `comparison_matrix` 21 行固定指标；`feasibility_gates` 四类硬门；`evidence` 逐字定位；`sensitivity` 多权重重排 |
| 创新增益 15：创新证据 5 | 证明创新点相对已有做法的边界和价值 | `references/comparison_schema.md` 与 SKILL.md 说明“为什么不是各自描述而是可比矩阵”；`self_check` 记录重跑一致性 |
| 可靠体验 10：调用与易用性 3 | Agent 能正确触发和调用，用户能按说明完成一次完整比较 | `SKILL.md` 第 12 章最小调用示例；`scripts/main.py --help` 可用；frontmatter description 清晰 |
| 可靠体验 10：运行稳定性 4 | 不同方案数量、资源约束和重复运行下持续产出可比结果 | `scripts/main.py` 退出码恒 0；`finally` 落盘；`verify.py` 确定性检查；异常降级表覆盖 |
| 可靠体验 10：异常处理 3 | 识别设备不可得、耗材超预算、参数窗口冲突、候选方案全部不可行 | `feasibility_gates` 逐项 pass/fail/unknown；全不可行时 `choice=null` + 回退算术 + 升级项；异常分支表完整 |
| 生态贡献 10：文档完整性 3 | 比较流程、字段定义、口径说明、依赖、示例与边界信息齐全 | `SKILL.md` 第 1、4、5、6、7、10、12、13、14 章；`references/*.md` 三份文件 |
| 生态贡献 10：资源可复用性 4 | 题集、方案模板、评分矩阵、参数表结构可被他人直接复用 | `scripts/fields.py` 矩阵结构；`references/comparison_schema.md` 模板；`scripts/scoring.py` 评分矩阵可配置 |
| 生态贡献 10：分享推广价值 3 | 沉淀可分享的比较方法、典型案例与真实选型经验 | `decision_record.md` 记录当次案例；`SKILL.md` 说明适用边界与失败处理；`GITHUB_URL.txt` 按要求放置（如本题要求） |
| GitHub 链接附加 5 | 提交公开 GitHub 链接，未登录可查看 | 在提交目录根路径放置 `GITHUB_URL.txt`，第一行写链接；评审无需登录即可打开 |

## 18. 提交前完整性自检清单（增强）

- [ ] 已运行 `python3 -B scripts/main.py --input /input --output /app/output` 并生成基线产物。
- [ ] `result.json` 存在且可解析；包含 `case_id` 与 `output_contract` 全部字段，键名原样保留。
- [ ] `comparison_matrix.csv`、`decision_record.md` 存在；若生成 Office/图形产物，PDF/PNG 预览存在且路径写入 `artifacts`。
- [ ] `result.json.status` 取值合法；`errors`、`degradations`、`uncertainty`、`pending_human` 均为数组或对象，无空值掩盖真实缺口。
- [ ] 对每条关键证据已核验：`quote` 逐字命中源文件；未命中项已标 warning 或降级 `limit`。
- [ ] 候选方案全部参与比较；非选中方案都有舍弃理由；全部不可行时给出超限量与回退算术。
- [ ] 硬门判定使用组织方契约值；成本/周期算术可重算；参数窗口冲突被识别。
- [ ] Agent 亲自撰写的选择理由、舍弃理由、假设、确认项在 `result.json` 与 `decision_record.md` 中，不是脚本模板原样。
- [ ] `self_check.agent_review` 写入 `verified` / `pending_human` / `conflicts`；`changes` 记录所有 Agent 修改。
- [ ] 已运行 `python3 -B scripts/verify.py --output /app/output --input /input`，结果全 PASS 或已知条目在 `degradations` 中说明。
- [ ] 材料解析失败项、格式不支持项、缺失文件已在 `sources` / `errors` 中显式标注，无编造。
- [ ] 最终仍保留全部基线产物和全部契约字段；未因 Agent 改写删除或清空任何基线字段。
- [ ] 确认退出码为 0，`/app/output` 下所有要求文件已落盘。
- [ ] 如本题要求在提交目录根路径放置 `GITHUB_URL.txt`，已放置且未登录可打开。