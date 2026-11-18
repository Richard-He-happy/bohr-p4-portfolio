# 判定规则：容差、比较、归因、结论、复核

## 1. 事前容差（默认先验）

`init` 在任何运行之前写 `/app/work/tolerance_plan.json`，字段 `before_any_run: true`、
`declared_step: "init"`。取值顺序：

1. **case 明确给出** → 记为 `case_declared`（识别 `{metric|name, abs_tol|abs|atol, rel_tol|rel|rtol}` 形态）。
2. 否则**先验默认**：`rel_tol = 0.02`，`abs_tol = 0.005 × |报告值|`（吸收报告位数与随机波动）。
3. 报告值缺失 → `abs_tol = 0`、`rel_tol = 0.02`，且该指标判定为 `no_reported_value`。

比较公式（`verify.compare_values`）：

```
abs_dev = |observed - reported|
rel_dev = abs_dev / |reported|          (reported ≠ 0)
within  = abs_dev <= abs_tol  or  rel_dev <= rel_tol
```

两条满足其一即视为在容差内（任一维度足够宽松即通过），与 `reproduction.md` 第 6 节一致。

**为什么容差必须事前定**：事后按观察值反推容差会让"对不上"变成"对得上"，
复现结论失去判别力。`check` 因此拒收任何比计划更宽的取值（`tolerance_widened_after_run`）。

## 2. 差异归因的判定与解释

脚本用**候选间一致性**这把尺子区分"实现差异"与"上游差异"：

| cause | 条件 | 人话 |
|---|---|---|
| `none` | 全部观测在容差内 | 无差异需归因 |
| `shared_upstream_factor` | 候选间极差 ≤ 容差，但都偏离报告值 | 两个实现互相印证，偏差更可能来自数据版本/切分、关键参数或环境 |
| `implementation` | 候选间极差 > 容差，且至少一方超差 | 实现细节（算法变体、默认值、随机性）导致 |
| `unverified_single_implementation` | 只有一份候选产出数值 | 信息不足，不能二分 |
| `paper_value_unavailable` | 材料里没有报告值 | 只能记缺口，不能判"一致" |
| `parameter_restoration` | 含 `chosen`/`code_inferred` 参数 | 参数复原不确定性 |
| `environment_underspecified` | 环境快照缺 `python/platform/packages/seed` | 跨机重建受限 |

`confidence`: `determined`（脚本按数值直接判定）/ `inferred`（启发式归因，需人工复核）。
Agent 的 `draft.attribution` 条目会并列保留（`source: agent_draft`），不覆盖脚本判定。

## 3. 结论分级

| verdict | 条件 |
|---|---|
| `reproduced` | 全部有报告值的观测都在容差内 |
| `partially_reproduced` | 部分在容差内 |
| `not_reproduced` | 全部超差 |
| `insufficient_evidence` | 没有候选成功运行，或没有任何可比报告值 |

`status` 与 `verdict` 独立：`status` 描述交付完整性（`ok/partial/insufficient_evidence/input_error`），
`verdict` 描述科学结论。只要有缺口（`pending_human` 或 `degradations` 非空），`status` 至少为 `partial`。

## 4. 复核步骤（他人如何重跑）

1. 读 `result.json.reproduction.tolerance_plan`，确认 `declared_step=init`、`before_any_run=true`。
2. 打开 `result.json.reproduction.runs[*]`，按 `command` 与 `workdir` 重跑；
   逐项核对 `exit_code`、`metrics` 与 `stdout_tail`。
3. 用 `reproduction.md` 第 6 节对比表复算 `abs_dev/rel_dev`，与 `abs_tol/rel_tol` 比较。
4. 对第 7 节每个 `inferred` 归因，回到候选间极差与参数表独立判断是否成立。
5. 检查第 8 节缺口是否被当成结论使用——若是，结论应降级。

## 5. 常见坑

- **口径不一致**：论文报 76.5（百分数），候选输出 0.766（小数）→ 先统一口径，不要改数字。
- **切分不同**：val 与 test 混用会让偏差看起来像实现问题；在 `uncertainty` 标注。
- **单 seed**：只跑一次就下 `reproduced` 结论风险高；候选间一致可以缓解，但不能替代多 seed。
- **把缺失当一致**：材料没写指标 ≠ 复现成功；必须 `no_reported_value`。
- **环境快照缺失**：没有 `python/packages/seed` 时，跨机差异无法排除，归因应止于"未验证"。
