# 检查表 / Checklist（experiment-parameter-optimizer v1.0.0）

本文件是 `SKILL.md` 第 6、10、11 节的展开，供评审复核与维护者回归。

## 1. rubric → 字段 → 检查

| 评分点 | result.json 落点 | 可执行检查 |
|---|---|---|
| 任务完成度 15 | `parameters[]`、`summary.recommended`、`protocol.md` §3/§5 | 每个参数有 `recommended`+`lower`+`upper`+`unit`；protocol.md 步骤可照做 |
| 结果正确性 15 | `feasibility`、`cost.items[].formula`、`parameters[].binding` | `recommended` 落在 `[lower, upper]`；成本 = Σ 单价×用量，单位可换算；绑定约束能指回 `sources` |
| 结果完整性 5 | `hypotheses`/`variables`/`groups`/`materials`/`equipment`/`schedule`/`risks`/`validation` | 八项均非空或显式 null 且有缺口说明 |
| 结果可核验性 5 | `sources[]`、`search.rounds`、`contract_backfill` | 每条数值有 `locator`+`quote`；每轮候选数/最优点/理由可复算；契约逐字段记录 slot/default |
| 质量增益 15 | `parameters[].basis`、`risks[]`、`feasibility.margins` | 相比「读输入直接给经验值」，建议值可指回设备/材料行 |
| 效率增益 5 | `search.rounds`、`steps` | 候选数、轮次有界（内置上限 600 点）；无需人工二次筛点 |
| 增益可验证性 5 | `verify_report.json`、`runtime` | 无随机数、无网络，重跑同输入得到同结构结果 |
| 新增能力 5 | 约束感知可行域 + 成本-响应联合权衡 | 每个边界带 `kind`（equipment/material/safety/declared）与来源 |
| 方法改进 5 | `search.rounds[].method`、`validation.stop` | 有收敛依据与停止判据数值 |
| 创新证据 5 | `degradations`/`pending_human` 的边界披露 | 无数据时转 screening 而非伪造响应面 |
| 调用与易用性 3 | `--help`、`references/example.md` | 一条命令产出全部产物 |
| 运行稳定性 4 | `status`、`errors` | 四类输入（正常/缺项/空/坏 JSON）均退出码 0 |
| 异常处理 3 | `feasibility.conflicts`、`pending_human[].blocking` | 冲突给 gap 数值 + 三选项 |
| 文档完整性 3 | `SKILL.md` 全节 + 本文件 | 依赖、路径、限制、维护齐全 |
| 资源可复用性 4 | `references/protocol_template.md`、CSV 表头 | 模板与表头可被他人直接复用 |
| 分享推广价值 3 | 示例 + 失败分支表 | 他人可按 example.md 独立跑通 |

## 2. 可行域构造规则

`lower = max(所有下界)`，`upper = min(所有上界)`，来源四类：

1. `equipment_limit`：设备量程（`range` 字段）。
2. `material_limit`：材料/试剂规格中的耐温、耐压、浓度上限。
3. `safety_limit`：约束、阈值、安全限。
4. `declared_domain`：输入显式给的离散域或步长。

`binding` 记录实现该边界的来源 `source_id`；`lower > upper` 即冲突，输出 `gap = lower - upper`。

## 3. 数值纪律

- 任何数值必须来自输入材料，或由输入算术导出（`formula` 字段写清算式）。
- 缺失的单价、用量、精度、批件 → `pending_human` / `cost.unknown_cost`，**不填默认值冒充事实**。
- 无历史数据时不拟合响应面：`response_model[].ok=false`，`uncertainty.level=high`，建议值标注为设计选择。
- 拟合需 ≥3 点；`r2`、`sigma`、`n` 一并披露，判据用 `±2σ`。

## 4. 失败分支（对应 `status`）

| 输入情形 | status | 处置 |
|---|---|---|
| 无 `/input` 或空目录 | `input_error` | 写合法 result.json 与三件产物骨架 |
| case.json 坏 JSON | `input_error` | `errors` 记解析失败，仍尝试材料文本 |
| 无参数定义 | `insufficient_evidence` | `pending_human` 要求补参数与域 |
| 约束交集为空 | `partial` | `feasibility.conflicts` + 三选项 + blocking |
| 缺价目/用量 | `partial` | `cost_per_run=null`，`unknown_cost` 列表 |
| PDF/图片未解析 | 保持原 status | `degradations` + `input_files[].note` |
| 正常 | `ok` | 全字段齐备 |

## 5. 交付前自检

1. `python3 -B scripts/main.py --input <in> --output <out>` 退出码 0，`out/result.json` 可 `json.load`。
2. `python3 -B scripts/verify.py --input <in> --output <out>` 的 `checks` 全为 true。
3. `result.json` 含输入 `output_contract` 的每个键（`contract_missing` 为空）。
4. `protocol.md`/`parameter_plan.csv`/`risk_table.csv` 非空且字节数 > 0。
5. 无 `__pycache__`、无 `.pyc`、无临时文件。
