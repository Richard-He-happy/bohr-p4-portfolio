# 比较口径定义（plan-compare v1.0.0）

本文件是 `scripts/*.py` 中所有字段、单位、公式的说明版本。口径改动必须同步改代码与本文件。

## 1. 七类必填字段

| 字段 | 含义 | 命中键名（不区分大小写，忽略符号） |
|---|---|---|
| `hypothesis` | 可检验的假设与预期 | hypothesis / 假设 / 假说 |
| `variables` | 自变量与因变量 | variable / factor / 变量 / 因子 |
| `controls` | 对照与空白 | control / 对照 / blank / sham |
| `steps` | 可执行步骤顺序 | step / procedure / protocol / workflow / 流程 / 步骤 |
| `parameters` | 参数取值与窗口 | param / setting / 参数 / 窗口 / domain |
| `resources` | 设备、耗材、预算 | resource / equipment / instrument / consumable / material / budget / 设备 / 耗材 / 资源 |
| `acceptance` | 判读标准与接受阈值 | accept / criteria / threshold / tolerance / 判读 / 验收 / 标准 |

命中即记 `present` 与其 JSON Pointer；未命中记 `absent` 并进入 `uncertainty`，不推断补齐。
`completeness = 命中字段数 / 7`。

## 2. 成本模型

```
per_run  = Σ(qty_i × unit_price_i)          # scaling=per_run 的行
fixed    = Σ(subtotal | scaling=one_off) + one_off
machine  = machine_hours × machine_rate
labor    = labor_hours   × labor_rate
total    = runs × per_run + machine + labor + fixed
```

- 单位：金额随 `currency`（默认 CNY），机时/人工为 h，周期为 day。
- `machine_hours` / `labor_hours` 为**全程总量**（与 §3 时间模型一致，`total_days=(machine+labor)/8`），故 `machine`/`labor` 不随 `runs` 翻倍；只有 `per_run`（耗材）随 `runs` 翻倍。
- `one_off`：键名含 oneoff / fixed / setup / 一次性 的行或标量。
- 费率来源必须是契约字段；键名含 `hours` 的值视为工时量，**不**当作费率。
- `declared_check`：若方案自报 `total_cost/total_budget/cost_estimate`，与核算值比较，偏差 >1% 记 `mismatch`，以核算值为准。
- 缺任一输入不臆补：`missing` 列出缺口，`total_cost` 按已知项求和并注明为下界。

## 3. 时间模型

阶段：`prep`（制样）、`run`（实验/采集）、`queue`（排期/排队/等待）、`analysis`（表征/测试）、`rework`（返工）。
`total_hours = Σ阶段`；`total_days = total_hours / 8`（8 h 工作制）。
方案未给阶段工时时，用 `(machine_hours + labor_hours)/8` 估算，`days_basis` 标 `derived`，并写入 `assumptions`。
一次性排队与返工必须计入，否则周期被系统性低估。

## 4. 硬门（先淘汰，再排序）

| 门 | 判定 | 失败含义 |
|---|---|---|
| `budget` | `total_cost ≤ budget` | 超预算，需追加预算或压缩重复次数 |
| `time_window` | `total_days ≤ deadline_days` | 赶不上窗口，需并行或降规格 |
| `machine_hours` | `machine_hours ≤ available_hours` | 机时排不进去 |
| `param_window` | `min ≤ value ≤ max` | 参数越出设备/材料窗口，物理上做不了 |

单门状态：`pass` / `fail` / `unknown`（输入缺一侧）。任一 `fail` 即淘汰，`unknown` 只降低置信度，不淘汰。

## 5. 评分与排序

默认权重：`completeness 0.30`、`feasibility 0.20`、`cost 0.20`、`time 0.15`、`risk 0.15`。

| 分量 | 归一方式 |
|---|---|
| completeness | 命中字段数 / 7 |
| feasibility | 已判定门通过率（无门时为 0.5） |
| cost | 可行集最低成本 / 本方案成本（≤1） |
| time | 可行集最短周期 / 本方案周期（≤1） |
| risk | `1 − 罚分/(罚分+2)`，罚分 = Σ(critical 4 / high 3 / medium 2 / low 1) |

未声明风险的方案不给满分：按已声明方案罚分中位数中性计入，并在 `uncertainty` 标注。
同分取成本低者；`margin = top1 − top2`。

## 6. 敏感性

用五组权重重排：`default`、`equal`（各 0.20）、`cost_led`（成本 0.40）、`time_led`（周期 0.40）、`risk_led`（风险 0.40）。
`stability = 与基准冠军一致的组数 / 5`；`flip` 列出会翻盘的方案。
`stability=1` 且硬门齐全 → `confidence=high`；≥0.6 → `medium`；否则 `low`。

## 7. 淘汰与回退

- 硬门失败：给出超限量、回退算术（需追加预算额、在预算内可保留的重复次数）。
- 评分落后：给出可比数字（成本差与百分比、周期差、风险罚分、字段完整度）与主因分量。
- 全部不可行：`choice.selected=null`，`status=partial`，`pending_human` 追加"放宽预算/周期或增加机时后重跑"。

## 8. 状态

| 状态 | 触发 |
|---|---|
| `ok` | 方案齐全、七字段齐全、成本与周期可算、存在可行方案 |
| `partial` | 有缺口（字段/费率/机时/周期）、或全方案不可行、或未读到 case |
| `insufficient_evidence` | 读到 case 但没有可识别的候选方案集合 |
