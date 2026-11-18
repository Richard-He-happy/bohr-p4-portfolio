# 实验参数优化方案 / Experiment Parameter Optimisation Protocol

- 目标 / Goal: {{goal}}
- 生成 / Generated: `experiment-parameter-optimizer` v{{ver}} · {{at}}
- 状态 / Status: **{{status}}**
- 数值口径 / Provenance: 所有数值来自输入材料或由输入算术导出；逐条定位见 `parameter_plan.csv` 的 `basis_source_ids` 与 `result.json:sources`（含 locator + 逐字 quote）。未确认项一律写在 §9，不当作可执行事实。

## 1. 假设与可检验问题 / Hypotheses

{{hyp}}

## 2. 变量与对照 / Variables and controls

{{vars}}

重复批次：每点 3 次（设计默认值，可调）；基线批次 = 输入给定原方案参数，用于扣除批间漂移。

## 3. 关键参数、建议值与可行区间 / Key parameters

{{params}}

区间 = 设备量程 ∩ 材料限制 ∩ 安全阈值 ∩ 输入显式域 的交集；`binding` 为实现该边界的最后一个收紧来源，详情见 `parameter_plan.csv`。

## 4. 材料与设备 / Materials and equipment

{{mat}}

## 5. 操作步骤 / Procedure

{{steps}}

## 6. 排期与成本 / Schedule and cost

{{sched}}

## 7. 判读标准与停止条件 / Acceptance and stopping rules

{{valid}}

## 8. 风险与替代方案 / Risks and fallbacks

{{risks}}

## 9. 确认项与缺口 / Confirmations and gaps

{{pending}}

## 10. 复跑记录 / Re-run record

- 调用 / Invocation: `python3 -B scripts/main.py --input /input --output /app/output`
- case_id: `{{cid}}` · skill v{{ver}} · 确定性重跑（无随机数、无网络）
- 校验 / Verify: `python3 -B scripts/verify.py --input /input --output /app/output`
