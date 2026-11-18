---
name: plan-compare
description: 把 2–5 个候选实验方案放到同一张可比矩阵上并给出可辩护的选择：统一七类字段（假设/变量/对照/步骤/参数/资源/判读标准），核算耗材+机时+人工成本与含制样/排队/表征/返工的总周期，按预算/周期/机时/参数窗口做硬门可行性判定，做权重敏感性排序，输出选择结论、逐条舍弃理由、风险与异常处置、逐字证据定位，并原样回填输入 output_contract 的全部字段。Use when comparing, selecting or defending among candidate experimental protocols, 实验方案比较与选择, 方案选型, 机时与耗材预算核算, protocol down-selection.
version: 1.0.0
---

# plan-compare — 实验方案比较与选择

## 1. 用途与边界

用于"同一目标下有多条可行路线、需横向比较并给出可辩护选择"的任务：把候选方案填进同一套可比字段，算清成本与周期，用硬约束淘汰不可行项，再按加权口径排序，并说明每条被舍弃方案差在哪里。

做：字段归一、成本/周期核算、硬门可行性、权重敏感性、选择与舍弃理由、风险登记、证据定位、缺口与人工确认项。不做：原创实验设计、文献综述、数据统计分析、替组织方编造案例。输入未给出的数值不构造，写入缺口。

## 2. 运行契约

- 输入只读：`/input/case.json`（必需）与 `/input/task.md`、材料文件（可选）。也可用 `--case` 指定路径。
- 输出目录 `--output`（默认 `/app/output`）：`result.json`（必需）、`comparison_matrix.csv`、`decision_record.md`；单独运行 `verify.py` 另写 `self_check.json`。
- 依赖：仅 Python 标准库，无网络；路径基于 `Path(__file__).resolve().parent`，与 CWD 无关。
- 入口：`python3 -B scripts/main.py --input /input --output /app/output`；`--help`、`--version` 可用。
- **退出码恒为 0**（含空输入、坏 JSON、全方案不可行）；成败一律看 `result.json.status`、`errors`、`degradations`。
- 单案例为纯计算，通常 < 1 s；无外部调用，故无中途断点风险，但仍先写 partial 再 finalize。

## 3. 输入发现（语义识别，不假设键名）

1. 依次找 `case.json` → `input.json` → `case_data.json` → 递归 `case*.json`；解析失败不中断，记 `errors`。
2. 候选方案：先找键名含 `plan / candidate / option / alternativ / proposal / arm / scheme / 方案 / 候选` 的列表；退化为"列表中每个字典至少命中七类字段中的两类"；再退化为"值为字典、键名含方案词"的映射（键名记为 `plan_key`）。
3. 组织方契约（预算、机时费率、人工费率、可预约机时、截止周期）从全树按键名语义抓取，命中位置写入 `cost_model.contract_locators`。含 `hours` 的键视为工时量而非费率。
4. 参数窗口：同时含 `min`/`max`（或 `range`/`allowed`/`domain` 二元组）的字典按父键名登记，与方案参数名做包含匹配。
5. 材料文件全部登记进 `sources`，不按文件名猜内容。

## 4. 输出契约

`result.json` 顶层固定回填：`case_id`、`status`(`ok`|`partial`|`insufficient_evidence`)、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`；业务字段：`candidate_plans`、`comparison_matrix`、`cost_model`、`time_model`、`feasibility_gates`、`risk_register`、`scoring`、`choice`、`eliminations`、`sensitivity`、`evidence`、`assumptions`、`parameter_table`、`artifacts`、`self_check`。

**契约回填**：读取输入 `output_contract`（字典 / 列表 / `{fields|required|properties:…}` 三种形态均可），把每个字段名**原样**作为键写进 `result.json`，值按语义映射到上表；无对应内容写 `null` 或 `[]`，不改名、不丢字段；`output_contract_map` 记录"契约字段 → 结果字段"。

## 5. 核心流程

1. 写 partial `result.json`（只有 state），随后写入契约骨架（所有字段置 `null`）。
2. `planmodel.find_plans` 定位方案；`build_metrics` 逐方案抽取七字段、成本、周期、风险、参数。
3. `extract_cost`：`total = runs×Σ(qty×unit_price) + fixed + machine_h×rate_m + labor_h×rate_l`（机时/人工为全程总量，耗材按重复次数翻倍）；方案自报总成本存在时做一致性核对（>1% 记为 mismatch）。
4. `extract_time`：分别累计 prep / run / queue / analysis / rework；无阶段数据时用 `(machine_h+labor_h)/8` 估算并标注 `derived`。
5. `scoring.gate_rows`：budget、time_window、machine_hours、param_window 四类硬门，逐项记 `pass/fail/unknown` 与超限量。
6. `scores_for` + `rank`：六分量加权；未声明风险的方案按已声明方案罚分中位数中性计入，不因"没写风险"得满分。
7. `sensitivity_block`：default / equal / cost_led / time_led / risk_led 五组权重重排，算一致率与翻转集合。
8. 生成 CSV 矩阵、决策记录 MD、证据清单；回填契约；`verify.check` 自检后 finalize。

## 6. 口径与评分规则（rubric → 字段/检查/产物）

| 评分关注 | 落点 |
|---|---|
| 可比矩阵 | `comparison_matrix`（21 行固定指标 × N 方案）+ 同名 CSV |
| 数字站得住 | `cost_model`（逐行 qty×单价、机时/人工拆分、自报成本核对）、`feasibility_gates`（超限量） |
| 七字段覆盖 | `candidate_plans[*].fields` 与"字段:x = present/absent"行，缺项进 `uncertainty` |
| 可独立复核 | `evidence`（逐字 quote + locator）+ `self_check` |
| 异常处置 | 硬门 fail→淘汰+回退算术；全不可行→`partial` + 升级项 |
| 增益可验证 | `comparison_basis` 固定公式与权重，换人重跑同分 |

默认权重：完整度 0.30、可行性 0.20、成本 0.20、周期 0.15、风险 0.15。分量归一：成本/周期取"可行集内最小值 / 本方案值"，风险取 `1 − 罚分/(罚分+2)`，罚分按 critical4/high3/medium2/low1 累加。

## 7. 证据与定位

每条证据：`{id, claim, value, source, locator, quote, kind}`，`kind ∈ {measured, pointer, narrative, limit}`。
`locator` 形如 `case.json#/candidate_plans/0/materials/0/unit_price`；`quote` 必须逐字出现在源文件中（数字按原文写法）。
凑不出就降级为 `unknown` 并记入 `uncertainty`，**绝不改写原文**。

## 8. 冲突、缺口与人工确认

- 同一量纲出现两个值（契约预算 vs 自报预算）：以契约值判硬门，冲突记入 `uncertainty`。
- 方案间字段不对等：保留不对称，矩阵原样呈现 `present/absent`，不猜测补齐。
- 恒入 `pending_human`：安全与合规审批、设备/耗材可得性、判读阈值冻结；全不可行时追加升级项。

## 9. 中断与预算

先落盘后优化：任何异常都在 `finally` 中 finalize，已算出的部分一律保留；`status=partial` 且 `status_reason` 说明缺口。计算量随方案数与成本行数线性增长，无需分批。

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
| `references/*.md` | 字段口径、证据规范、自检清单与示例 |

版本 1.0.0；标准库 Python ≥3.8。

## 14. 维护

改口径时同步改 `scoring.py`（权重/门限）、`references/comparison_schema.md`（说明）与 `report.py`（表述），改完跑 `verify.py` 确认自检全绿；新增字段优先扩 `planmodel.REQ` 与 `fields.build_matrix`。
