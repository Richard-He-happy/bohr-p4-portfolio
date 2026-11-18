# schema.md — 输入/输出契约（Skill v1.0.0）

本文件描述 `scripts/main.py` 实际读取什么、写出什么。字段名与 `result.json` 一一对应，改代码前先改本文件。

## 1. 输入

### 1.1 文件发现

运行时代码只读 `--input`（默认 `/input`）目录：

| 优先 | 文件 | 用途 | 缺失时 |
|-|-|-|-|
| 1 | `case.json`（或任意 `case*.json`） | 任务、约束、设备、试剂、方案版本、`output_contract` | `status=input_error`，仍扫描其余文件 |
| 2 | `task.md` 及其它 `.md/.txt` | 任务说明、材料说明 | 记入 `degradations` |
| 3 | `.csv/.tsv/.json/.xlsx/.docx/.pptx` | 设备清单、采购记录、SOP、历史结果 | 同上 |
| 4 | `.pdf` | 方案文档、手册 | 需 `pypdf`；未安装则抽不到文本，记 `degradations` |
| 5 | `.png/.jpg/…` | 图片材料 | 不做 OCR，记 `degradations` |

文件上限：单文件 ≤4 MB、最多 80 个；超限跳过并记录。不联网、不写 `/input`。

### 1.2 语义识别（不假设键名）

`feas.collect_lists()` 递归遍历 `case.json`，按键名子串匹配以下语义组（大小写不敏感、中英混用）：

| 语义组 | 键名匹配（示例） | 提取内容 |
|-|-|-|
| 方案 | plan / candidate / version / protocol / design / 方案 / 候选 / 版本 | 多版本方案列表（取内容最长的一组，最多 6 版） |
| 设备 | equipment / instrument / device / apparatus / asset / 设备 / 仪器 | 名称、型号、量程、精度、状态、货期、单价 |
| 材料 | reagent / material / consumable / supply / kit / 试剂 / 材料 / 耗材 | 名称、规格、库存、货期、单价 |
| 参数 | parameter / param / factor / setting / domain / 参数 / 取值 | 名称、数值、单位、取值域/容差 |

预算、时间窗、人力按**键名 + 指针路径**识别（`budget/预算/经费`、`deadline/horizon/window/周期/期限`、`personnel/staff/人员/fte`），值可为数字或带单位字符串（如 `"4 weeks"`）。

### 1.3 量纲与单位

基座单位：质量 `mg`、体积 `uL`、时间 `min`、浓度 `mM`、温度 `°C`。支持 `ng/ug/mg/g/kg`、`nl/ul/ml/l`、`s/min/h/d/wk`、`weeks/week/days/day/hours/hour`、`pm/nm/um/mm`、`rcf/rpm/°c/%`。

特殊规则：`nm` 的数值 ≥100 视为**波长（长度）**，否则按浓度 nM 处理，避免把 570 nm 与 10 nM 混为一谈。

## 2. 输出

`--output`（默认 `/app/output`）下写：

| 文件 | 内容 |
|-|-|
| `result.json` | 唯一机器可读结果：契约回填 + 检查表 + 缺口 + 产物索引 |
| `protocol.md` | 可执行方案（0–10 节，见 §2.2） |
| `risk_table.csv` | 风险/异常处置表：`risk_id,mode,status,trigger,mitigation,fallback,escalation,locator` |
| `check_matrix.csv` | 逐条检查：`check_id,plan,class,item,severity,verdict,basis,needs_human,locator,quote,arithmetic,action,note` |

### 2.1 result.json 字段

| 字段 | 类型 | 含义 |
|-|-|-|
| `case_id` | str | 原样取自输入 `case_id`/`id`，缺失为 `unknown` |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `task` | obj | `{goal}`（取自 goal/objective/研究目标） |
| `summary` | obj | `plans, recommended, verdict, coverage, counts{met,partial,gap,blocked,na}, blocking, conditions, gaps, checks_total, lib_source, status` |
| `plans` | list | 每版本 `{plan, verdict, score, coverage, counts, blocking[], conditions[], n_checks, n_blocked, n_major_gap}` |
| `recommended` | str | 推荐版本 id |
| `checks` | list | 每条 `{check_id, plan, class, item, basis, severity, verdict, evidence[], arithmetic, action, needs_human, note}` |
| `evidence` | list | `{source_id, locator, quote}`；`locator` 为 JSON Pointer 或行号 |
| `arithmetic` | obj | `{formula, inputs, left, right, unit, delta}`，`inputs` 全为输入原值 |
| `gaps` | list | `{class, check_id, item, supply, severity, plan}` —— 方案未写的要素与需补内容 |
| `pending_human` | list | `{check_id, plan, item, why, action}` —— 需专家/机构确认项 |
| `uncertainty` | list | `{check_id, note, basis}` + `{issue, impact}` |
| `resource_rows` | list | 设备/材料表行：`名称,类型,规格,状态,库存,货期,单价` |
| `param_rows` | list | 参数表行：`参数,值,单位,输入范围` |
| `risks` | list | `{mode, status, trigger, mitigation, escalation, locator}` |
| `sources` | list | `{source_id, kind, chars, locator_scheme}` |
| `errors` / `degradations` / `changes` | list | 失败项、降级项、变更记录 |
| `runtime` | obj | `skill_version, lib_source, plans, sources, deadline_src, budget_src, finished_at, elapsed_sec` |
| `selftest` | obj | `{checks, contract_missing[], artifacts_missing[], classes[]}` |
| `artifacts` | obj | 各产物绝对路径 |
| `feasibility` | obj | 主结果：推荐版本的 `verdict/score/coverage/blocking/conditions/counts` |
| `comparison` | obj | 版本比选：`recommended` + `ranking` |
| `variables` | obj | `iv`/`dv`，取自 H-02/H-03 的证据句 |
| `validation` | obj | `criteria`（H-04 判读标准）/`stopping`（K-06 停止条件）证据句 |
| `anomaly` | list | 同 `uncertainty`：口径不明与缺基准项 |
| `contract_backfill` | obj | 每个契约字段 `filled`（有实值）/`default`（空值占位） |

**语义键说明**：上表 `feasibility`/`comparison`/`variables`/`validation`/`anomaly` 无论契约是否列名都会输出；契约含同名键时直接复用真实内容，`contract_backfill` 记 `filled`；契约里的其它未知键按原类型填空并记 `default`。

**契约回填规则**：输入 `output_contract` 的每个键都出现在顶层；脚本自身产出的同名字段（如 `summary`、`risks`）直接复用；其余按契约原类型填空（list→`[]`、dict→`{}`、标量→`null`），并在 `contract_backfill` 标记 `default`。未知键一律保留。

### 2.2 protocol.md 结构

`0 一页结论（含执行条件）· 1 目标与假设 · 2 变量与判读 · 3 分组与对照 · 4 材料与仪器 · 5 参数表 · 6 步骤与时间 · 7 判读与停止条件 · 8 风险与异常处置 · 9 伦理与安全 · 10 缺失信息`

缺失项写 `〔待补〕`，不虚构；逐条证据在 `check_matrix.csv`。

## 3. 判定口径

| verdict | 触发条件 |
|-|-|
| `met` | 探针组全部命中，或算术满足（左值 ≤ 右值） |
| `partial` | 部分要素具备（如部分设备/试剂有状态、库存字段） |
| `gap` | 任一探针组未命中 / 缺基准（窗口/预算/货期/单价）/ 输入无对应清单 |
| `blocked` | 算术硬冲突：参数越出全部设备量程、货期或总历时超时间窗、材料费超预算 |
| `na` | 不适用（未涉及人体/动物/危险试剂/个人数据、输入无取值域） |

版本结论：有 `blocked` → `infeasible`；否则有 major/minor `gap` → `feasible_with_conditions`；全 `met`/`na` → `feasible`。

评分（仅用于同批版本互比，不跨案例比较）：

```
score = 100 × (met + 0.5 × partial) / (总检查数 − na)
```

推荐顺序：`blocking 数 ↑ → score ↓ → 条件数 ↑ → 版本序`。

## 4. 算术公式表

| 检查 | 公式 | 说明 |
|-|-|-|
| R-02 / P-02 | 参数基值 vs 同量纲设备量程并集 `[min lo, max hi]` | 越界记 `blocked`，`delta` 为超出量 |
| R-04 | `max(货期)` ≤ 时间窗 | 只用输入给出的天数 |
| T-02 | `Σ 步骤时长 / 1440` ≤ 时间窗（无步骤表时取文本最大时长，标"保守"） | 天 |
| T-04 | `Σ 单价 × 用量` ≤ 预算 | 用量只取与库存同量纲的数量，避免单位错配 |
| P-05 | 参数值 ∈ 输入给定取值域 | 无域时 `na` |

所有 `inputs` 均为输入原值，评审可独立复算。

## 5. 降级与状态

| 情形 | 处置 | status |
|-|-|-|
| `case.json` 缺失或坏 JSON | 记 `errors`，用其余文件继续 | `input_error` |
| 无方案文本 | 七类全 `gap` | `insufficient_evidence` |
| 无设备/材料清单 | R-01/R-02/R-03 记 `gap` + `pending_human`，不补量程 | `partial` |
| 无预算/时间窗 | R-04/T-02/T-04 记 `gap`，写入 `uncertainty` | `partial` |
| PDF 抽不到文本 / 位图 | 记 `degradations`，不阻断 | 不变 |
| `checks.md` 缺失 | 内置 7 条兜底项，`lib_source=builtin-fallback` | `partial` |
| 任一异常 | 捕获进 `errors`，仍写合法 `result.json`，退出码 0 | 视剩余证据 |
