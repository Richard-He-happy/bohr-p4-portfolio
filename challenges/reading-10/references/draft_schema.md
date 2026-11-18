# `draft.json` 字段规范（Agent 工作稿）

工作稿写在 `/app/work/draft.json`（`init` 会生成同名骨架 `draft_skeleton.json`）。
`build` 是唯一消费者；`check` 用它做结构校验。字段缺失不会让流程崩溃，但会降级为 `partial` 并写入缺口。

## 1. 顶层结构

```json
{
  "case_id": "repro-demo-001",
  "paper":   {"title": "...", "doi": null, "repo": "...", "commit": "a1b2c3d", "data_version": "..."},
  "plan":    [{"step": 1, "goal": "locate method", "command": "...", "expected": "...", "status": "done"}],
  "environment": {"python": "3.12.4", "platform": "Linux-...", "packages": {"numpy": "1.26.4"}, "seed": 0},
  "params":  [ ... ],
  "paper_values": [ ... ],
  "tolerance": [ ... ],
  "claims":  [ ... ],
  "attribution": [ ... ],
  "conclusion": {"verdict": "reproduced", "reason": "..."},
  "pending_human": []
}
```

## 2. `params[]` —— 参数复原

```json
{"name": "momentum", "value": 0.9, "class": "paper", "source": "§3.2",
 "evidence": {"source_id": "paper", "locator": "paper:§3.2 Training setup/p1", "quote": "momentum 0.9"}}
```

| `class` | 判定 | 要求 |
|---|---|---|
| `paper` | 正文/表/附录明确写出 | 必须有逐字 `quote`，否则 `check` 报 `paper_param_without_quote` |
| `code_inferred` | 只能从代码默认值/配置推断 | `source` 写文件与行号；计入 `uncertainty` |
| `chosen` | 两边都没有、由 Agent 设定 | 必须说明理由；计入归因 `parameter_restoration` |

冲突处理（正文与代码默认值不一致）时：以论文为准并保留代码值，两者都写进
`uncertainty`，例如 `"正文 lr=0.1，repo 默认 0.01，按论文取 0.1"`。

## 3. `paper_values[]` —— 报告值（比较基准）

```json
{"metric": "top1_accuracy", "value": 0.765, "unit": "fraction",
 "evidence": {"source_id": "paper", "locator": "paper:§4.1 Main results/p1", "quote": "Top-1 accuracy 76.5%"}}
```

- `metric` 必须与候选实现**实际输出的键名**（或可归一化匹配，如 `top-1 accuracy` ↔ `top1_accuracy`）一致，否则会多出一行 `no_reported_value`。
- 百分数写成小数（76.5% → 0.765）或保留 `unit`，但候选输出与报告值必须同口径；口径不一致时在 `uncertainty` 说明，不要改数字。

## 4. `tolerance[]` —— 只能更严

```json
{"metric": "top1_accuracy", "abs_tol": 0.003, "rel_tol": 0.01,
 "basis": "论文报告三位小数，取半个末位", "declared_step": "plan"}
```

`init` 已把默认容差写入 `tolerance_plan.json`；这里只能取等或更小，
任何更宽的取值都会被 `check` 判为 `tolerance_widened_after_run`（事后凑容差）。

## 5. `claims[]` —— 带证据的结论

```json
{"id": "c1", "kind": "paper_result", "text": "Top-1 accuracy reported as 76.5%",
 "confidence": "direct",
 "evidence": [{"source_id": "paper", "locator": "paper:§4.1 Main results/p1", "quote": "Top-1 accuracy 76.5%"}]}
```

`kind` ∈ `paper_result` / `method` / `param` / `environment` / `attribution`。
`confidence` ∈ `direct`（原文直读）/ `inferred`（合理推断）/ `undetermined`（无法判断）。
`quote` 会被规范化后在索引正文中**逐字查找**：找不到即拒收，绝不改写原文。

## 6. `conclusion`

```json
{"verdict": "partially_reproduced", "reason": "top1 在容差内，macro_f1 超差 1.2%，归因参数复原"}
```

允许值：`reproduced` / `partially_reproduced` / `not_reproduced` / `insufficient_evidence`。
与脚本按容差算出的判定不一致时，脚本保留自己的判定并记 `verdict_conflict`，你的 `reason` 会并列保留。

## 7. 常见错误

| 报错 | 原因 | 修法 |
|---|---|---|
| `claim_without_evidence` | claim 没有 `evidence[]` | 补逐字 quote，或降级 `confidence` |
| `evidence_rejected:*:quote_not_found` | quote 与原文不符 | 用 `show --grep` 取原文原句 |
| `param_class_invalid` | `class` 拼错 | 只用 `paper`/`code_inferred`/`chosen` |
| `tolerance_not_predeclared` | 指标名不在 `tolerance_plan.json` | 用与 `init` 相同的指标名 |
| `locator_mismatch` | 段号不同但 quote 命中 | 可接受；建议改用脚本给出的 locator |
