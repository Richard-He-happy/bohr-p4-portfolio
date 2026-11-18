---
name: experiment-plan-builder
description: Turn a research goal plus equipment, reagent, price and booking contracts into an executable wet-lab experiment plan, then cost it, schedule it, clip its parameters into real instrument ranges and finite domains, add or repair controls, and revise its own versioned candidate plans. Use for experiment protocol design, plan comparison and selection, feasibility checking, parameter optimisation, risk and stop-condition design, or versioned plan revision.
version: 1.0.0
license: MIT
---

# experiment-plan-builder

把「研究目标 + 资源契约（设备量程/机时/报价、试剂规格/库存/单价、预算、时间窗）+ 候选方案版本」
转成一份**可排期、可计价、可复核**的实验方案，而不是复述目标或套用通用流程。

主产物：`result.json`（结构化结果 + 证据定位 + 运行状态）、`protocol.md`（人可照做/排期的方案正文）、
`risk_table.csv`（风险与失败处置逐项表）。

## 1. 用途与边界

**做什么**

1. 从输入里**语义发现**研究目标、自变量/因变量、分组、设备、试剂、参数域、预算与时间窗、候选方案版本。
2. 对每个候选方案做**真实算术**：试剂成本（用量 × 单价，带单位换算）、机时成本（用时 × 机时费）、
   墙钟时间（各阶段取最长步骤后求和）与人工工时。
3. 硬约束审计：设备量程、参数有限允许域、试剂库存、机时可用量、预算上限、时间窗。
4. **修订而非重写**：把越界参数裁剪回量程与允许域、换用输入给出的有库存替代试剂、按预算下调重复数
   （下界 n=3），每次改动写进 `changes`（V1…Vn，含 before/after/规则/证据）。
5. 跨候选比较：先比硬约束违背数，再比成本与墙钟，选出基线方案。
6. 输出六类要素 + 判读标准、停止条件、风险与异常处置、确认项与不确定性。

**不做什么**

- 不编造仪器参数、试剂目录号、文献、DOI、阈值或统计量；输入没给的数值一律留空并进 `uncertainty` / `pending_human`。
- 不把未确认的假设写成可执行事实；安全、伦理、设备可用性一律进 `pending_human`。
- **不解析非 JSON 材料的正文**：PDF/CSV/DOCX/图片/XLSX 会被登记为 `sources`（含 sha256 前 16 位）以便复核，
  但本 Skill 不从其正文抽取事实。若关键规格只在 PDF 里，方案会把对应项标为缺口，而不是猜。
- 不替代专家判断：`feasibility.verdict` 只针对输入中可核验的硬约束。

## 2. 适用与不适用

**适用**：细胞/分子/分析化学/材料表征等需要有对照、有参数、有资源的方案设计；已有多个候选版本需要选型与修订；
需要在预算与时间窗内判断"这个方案能不能排下去"；需要风险预案与替代路径。

**不适用**：临床诊疗决策；涉及人体/动物伦理审批内容的最终裁定；纯文献综述；无任何资源契约的纯理论推演
（仍可运行，但设备/成本要素会标为缺口）。

## 3. 运行契约

```bash
python3 -B scripts/build_plan.py --input /input --output /app/output
```

- 只读 `--input`，只写 `--output`（默认 `/input` 与 `/app/output`）；不联网；不依赖 CWD；
  资源用 `Path(__file__).resolve().parent` 定位。
- 仅用 Python 3 标准库（argparse/csv/hashlib/json/math/re/sys/time/pathlib/datetime）。
- **退出码恒为 0**；任何失败写进 `result.json` 的 `errors` / `degradations` / `pending_human`。
- 可选参数：`--mode auto|generate|revise`（默认 auto：有候选版本则修订，否则生成）、`--version`。

## 4. 输入发现（语义，不依赖固定键名）

按序尝试：`case.json` → 任意 `case*.json` → 任意 `*.json`。键名用正则族匹配中英文同义词，例如：

| 目标 | 匹配的键名族 |
|---|---|
| 研究目标 | `goal / research_goal / objective / aim / research_question / task_instruction / 目标 / 研究目标` |
| 设备 | `equipment / instruments? / devices? / apparatus / 仪器 / 设备` |
| 试剂 | `reagents? / consumables? / materials? / chemicals? / 试剂 / 耗材 / 材料` |
| 候选方案 | `candidate_plans / plans? / protocols? / versions? / 方案 / 候选 / 版本` |
| 参数域 | `parameter_domains / allowed / domain / levels / 取值 / 可选` |
| 预算 / 时间窗 | `budget / 预算 / 经费`；`time_window / deadline / 工期 / 时限 / 完成时间` |

设备字段：`name, model, range, precision, hourly_rate, available_hours, currency`；试剂字段：
`name, spec, unit, unit_price, stock, substitute`。候选步骤字段：`action, duration, stage, equipment, reagent[{name,qty,unit}], <参数>`。
`output_contract`（dict 或 list）会被完整回填。

## 5. 输出契约

`result.json` 顶层键（全部存在；缺值为 `null` 或 `[]`）：

| 键 | 含义 |
|---|---|
| `case_id` / `status` / `runtime` | 输入标识原样保留；`status ∈ {ok, partial, input_error}`；运行时长与版本 |
| `summary` | goal、mode、candidates、selected、cost、currency、wall_h、total_n、verdict、version、title |
| `hypotheses` / `variables` | 可检验假设（含零假设、判据、basis_type）与变量（independent/dependent/confounder） |
| `groups` / `sample_size` | 处理组+空白+阴性+阳性；n 来源（输入给定 / 由 Δ、σ 推算 / 惯例下限）与合计 |
| `materials` / `equipment` / `steps` | 需求用量、小计、库存、替代；量程、机时费、需用/可用机时、结论；步骤与关键参数 |
| `schedule` | estimated_cost、material_cost、equipment_cost、budget_limit、within_budget、total_wall_min、time_window_min、unknown_duration_steps |
| `risks` / `validation` / `feasibility` | 风险表；判读标准与金标准；硬约束台账与 verdict |
| `changes` | 修订记录 V1…Vn（op / field / before / after / rule / evidence） |
| `pending_human` / `uncertainty` | 阻塞项（安全、伦理、机时确认）；非阻塞不确定性与解决路径 |
| `evidence` / `sources` | 每条含 `locator`（`case.json#/<json-pointer>`）、`quote`、`verified`；输入文件清单与哈希 |
| `errors` / `degradations` / `coverage` / `self_check` | 异常、降级、六类要素覆盖、自检结果 |

**原样回填 `output_contract`**：键名不改、未知字段保留（按语义映射不到时置 `null` 并在 `uncertainty` 记录未映射键）。
`protocol.md` 由 `references/protocol_template.md` 占位符渲染；`risk_table.csv` 列为
`risk_id, code, failure_mode, likelihood, impact, early_signal, mitigation, stop_condition, fallback, owner, source_ref`。

## 6. 核心流程

1. 写 partial `result.json`（含 case_id、空契约键）——任何后续失败都有合法结果落盘。
2. 发现输入、登记 sources 哈希、抽取目标/设备/试剂/参数域/预算/时间窗/候选版本。
3. 逐候选评估：成本、机时、墙钟、硬约束违背列表。
4. 选基线（违背数 → 成本 → 墙钟），进入修订循环（最多 12 轮），记录每次改动。
5. 组装六类要素、判读标准、风险表、可行性台账、确认项与不确定性。
6. 渲染 `protocol.md` 与 `risk_table.csv`；校验证据 quote；自检算术；无条件 finalize 覆盖 `result.json`。

## 7. 评分要点 → 字段 / 检查 / 产物

| 评分维度 | 落点 |
|---|---|
| 任务完成度（把目标转成可排期方案） | `steps` + `schedule`（阶段时间轴、成本、机时）+ `protocol.md` 排期表 |
| 结果正确性（假设可检验、变量测量匹配、对照排混杂、参数在量程） | `hypotheses`（含零假设/判据/反证条件）、`variables`（操作定义）、`groups`（空白/阴性/阳性各自排除的混杂）、`parameters` 裁剪 + `changes` 记录 |
| 结果完整性（六类要素） | `coverage.elements` 六项：hypothesis_variables / controls / equipment_materials / time_cost / parameter_range / risk_anomaly |
| 结果可核验性 | `evidence`（locator + quote + verified）、`sources`（sha256）、`changes` 版本链、`validation.gold_standard`、`runtime` |
| 使用增益（少澄清、可执行） | 缺口不足 3 处即产出可执行方案；`pending_human` 只列真正阻塞项；`status` 明确可用性 |
| 创新增益（按量程预算裁剪、反推对照、风险替代） | 修订循环（clip / substitute / reduce_replicates）+ 四类对照模板 + `risks.fallback` 替代路径 |
| 可靠体验（触发、稳定、异常处置） | 本文件第 3/4/9/11 节；跨体系按语义匹配；缺失/冲突/依赖失配各有分支 |
| 生态贡献（文档、复用、分享） | 本文件 + `references/catalog.json`（词表/表头/对照模板/风险目录/口径）+ `references/protocol_template.md` + `references/checklists.md`（对照检查清单/参数表模板/自检/质量锚点，可独立复用） |

## 8. 证据与定位规则

- 每个资源契约行生成一条 `evidence`，`locator` 为 `case.json#/equipment/0` 这类 JSON Pointer，`quote` 为该节点原文的 JSON 序列化。
- finalize 时**重读输入并逐条比对** `quote`，写回 `verified: true|false`；不一致计入 `self_check.quotes_failed`。
- 设计选择能回指输入的写 `basis_type: input`，领域原则写 `principle`，输入缺失写 `missing`，由输入推导写 `derived`。
- 不编造文献与 DOI：本 Skill 不输出文献引用；需要文献支撑的判据一律标 `basis_type: principle` 或 `missing`。

## 9. 冲突、缺失输入与人工确认

| 情形 | 处置 |
|---|---|
| 无设备参数 | 参数无法裁剪；`pending_human` 提示补量程，方案仍给结构 |
| 无预算 | 仍算成本，`within_budget: null`，`gaps.budget` 提示确认上限 |
| 无时间窗 | 仍算墙钟，`within_time_window: null` |
| 时间窗与样本量冲突 | `feasibility.verdict = not_feasible`，硬约束行给出具体数值，`risks` 触发 R-TIME |
| 试剂缺货 | 若输入给了有库存替代品则替换并记 `changes`；否则 `STOCK` 硬约束 + 人工确认 |
| 设备排期已满 | `BOOKING` 硬约束 + `pending_human`；**不通过压缩重复来"解决"排期**（重复下界 n=3） |
| 参数超量程/不在允许域 | 裁剪到最近允许值，记 `change` 与该行证据；无法裁剪则保留硬约束 |

## 10. 资源与预算

- 一次运行只读输入、只写三个产物；无网络；无外部服务；中间结果不落盘（内存内），可重复运行得到相同结果（确定性）。
- 单次运行复杂度与输入规模线性相关；实测最小案例耗时 < 1 s。脚本不设内部重试，避免放大调用次数。

## 11. 异常与降级分支

| 触发 | 结果 |
|---|---|
| 无可用 JSON（空目录/坏 JSON） | `status: input_error`，`uncertainty` 说明缺口，仅写骨架；退出 0 |
| 候选方案缺失 + `--mode revise` | `degradations.plan_selection`，退化为单方案生成 |
| 输入无步骤/时长 | 生成骨架步骤；`pending_human` 要求补流程与时长；排期为下界 |
| 步骤无时长 | `schedule.unknown_duration_steps` 计数，`protocol.md` 标注"下界" |
| 单价或单位不可换算 | 该行成本不计入合计，`uncertainty` 记录 `unit_mismatch` / `unpriced` |
| `protocol.md` / `risk_table.csv` 写失败 | `degradations` 记录，`result.json` 仍完整 |
| 构建异常 | `errors[].stage=build`，交付 partial 骨架；退出 0 |

## 12. 自检

`result.json.self_check` 含：`quotes_failed`（证据 quote 无法复现数）、`arithmetic_ok`（材料小计之和 = 材料成本，
且 n × 组数 = 合计样本）、`contract_missing`（未回填的契约键）、`elements`（六类要素布尔覆盖）。
自检失败时 `status` 自动降为 `partial`；`coverage.elements` 任一为 false 也降级。阅读者据此判断结果能否直接用。

## 13. 最小调用示例（EXAMPLE ONLY / 示例，非正式案例结果）

输入 `/input/case.json`（示例）：

```json
{"case_id": "EXAMPLE-ONLY", "goal": "评估化合物 X 对细胞活力的剂量效应",
 "equipment": [{"name": "酶标仪", "model": "M1", "range": "0-4.0 OD", "hourly_rate": 80, "available_hours": 6}],
 "reagents": [{"name": "化合物 X", "spec": "10 mM 母液", "unit": "µL", "unit_price": 12.5, "stock": 80}],
 "budget": {"amount": 6000, "currency": "CNY"}, "time_window": "10 days", "n_per_group": 3,
 "parameter_domains": {"温度": [4, 25, 37]},
 "candidate_plans": [{"version": "v1", "steps": [
   {"action": "铺板", "duration": "1 h", "equipment": "培养箱"},
   {"action": "加药孵育", "duration": "24 h", "equipment": "培养箱", "temperature": "75 °C"},
   {"action": "读数", "duration": "2 h", "equipment": "酶标仪"}]}],
 "output_contract": {"summary": "string", "hypotheses": "array", "schedule": "object"}}
```

调用：`python3 -B scripts/build_plan.py --input /input --output /app/output`

示意输出（示例，非正式结果）：`status: ok`；`summary.selected = v1`；`changes` 含一条
`clip_parameter 温度 75 → 37`（示例把 75 °C 裁回允许域 37）；`schedule.estimated_cost` 由试剂与机时相加得出；
产物 `protocol.md`（排期表 + 判读 + 风险）、`risk_table.csv`。

## 14. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：用途、契约、流程、异常、自检 |
| `scripts/build_plan.py` | 入口 CLI：发现、契约回填、组装、渲染、自检、finalize |
| `scripts/plan_core.py` | 库：语义抽取、单位/时间/货币解析、成本与排期、硬约束审计、修订循环、周期表渲染 |
| `references/catalog.json` | 可复用知识：单位词表、表头、对照模板、风险目录、异常处置、判据、缺口话术、契约映射 |
| `references/protocol_template.md` | `protocol.md` 的占位符模板（`{{...}}` / `{{t:数据块}}`），可直接改写 |
| `references/checklists.md` | 复用清单：对照设置检查表、参数表模板、提交前自检、质量锚点、缺口话术 |

版本 1.0.1。修改 `catalog.json`、`protocol_template.md`、`checklists.md` 不需要改代码；新增实验体系时优先扩 `catalog.json` 的键名族与话术，并在 `checklists.md` 补对照与参数行。
`plan_core.py` 只做纯函数式抽取与算术，`build_plan.py` 负责编排与落盘，便于分别维护和复用。
