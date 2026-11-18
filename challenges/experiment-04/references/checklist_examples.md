# 自检清单、最小示例与已知限制（plan-compare v1.0.0）

## 1. 交付前自检

1. `python3 -B scripts/main.py --help` 退出码 0，参数与默认路径正确。
2. 空目录 / 坏 JSON：仍写出合法 `result.json`，退出码 0，`status=partial` 且 `errors` 有说明。
3. 正常案例：`status` 为 `ok` 或 `partial`，`choice.selected` 有值（除非全方案不可行）。
4. `output_contract_fields` 全部非空，`output_contract_map` 记录映射来源。
5. `verify.py` 全 PASS：算术、契约、矩阵列数、证据命中、舍弃说明、产物存在。
6. 每个非选中方案都有一条带数字的舍弃理由（成本差、周期差、风险罚分、字段完整度）。
7. 每条硬门都有 `pass/fail/unknown` 与超限量，`unknown` 有 `missing` 说明。
8. 未声明风险的方案被中性计分，而不是拿满分。
9. `assumptions` 里写明周期折算口径；`pending_human` 含安全、设备、判读阈值三项。
10. 包里没有 `__pycache__`、`.pyc`、示例大二进制、预制答案。

## 2. 最小调用示例（示例，非正式案例结果）

目录：

```
/input/case.json
/app/output/          # 运行前可为空
```

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --output /app/output --input /input
```

`case.json` 片段（示例）：

```json
{"case_id": "demo-001",
 "output_contract": {"comparison_matrix": "…", "choice_summary": "…", "cost_model": "…"},
 "organizer_workorder": {"budget_cny": 80000, "deadline_days": 45,
                          "machine_rate_cny_per_h": 320, "labor_rate_cny_per_h": 150,
                          "available_machine_hours": 60},
 "candidate_plans": [
   {"plan_id": "A", "hypothesis": "…", "variables": ["…"], "controls": ["…"],
    "steps": ["…"], "parameters": {"T_C": 120}, "acceptance_criteria": "…",
    "materials": [{"item": "基片", "qty": 12, "unit_price": 450}],
    "machine_hours": 28, "labor_hours": 46, "runs": 3,
    "risks": [{"risk": "开裂", "severity": "high", "mitigation": "分段降温"}]}]}
```

示意输出（示例，数值仅用于说明字段形态）：

```json
{"case_id": "demo-001", "status": "partial",
 "choice": {"selected": "A", "score": 0.88, "confidence": "medium"},
 "cost_model": {"plans": {"A": {"per_run_cost": 5400.0, "machine_cost": 8960.0,
                                 "labor_cost": 6900.0, "total_cost": 32060.0}}},
 "output_contract_fields": ["comparison_matrix", "choice_summary", "cost_model"]}
```

算术核对：`total = 3×5400 + 8960 + 6900 = 32060`（机时/人工为全程总量，不随重复次数翻倍）；若另有一次性夹具 3800 则 `total = 3×5400 + 3800 + 8960 + 6900 = 35860`。
示意值不保证与任何正式案例一致，实际结果一律由脚本按输入重算。

## 3. 已知限制

- 语义抽取依赖键名，命名完全偏离常见词表时可能漏检；此时会以"字段 absent"或"无方案"显式暴露，不会静默猜测。
- 一份方案内若同时存在多套结构不同的采购清单，可能重复计入；`verify` 的算术只能校验内部一致，不能校验语义重复。
- 周期按 8 h/工作日折算，未建模跨周等待与设备检修窗口；相关结论在 `assumptions` 中标注。
- 风险罚分是排序用的相对量，不是事故概率；不得在对外材料中解释为定量风险估计。
- 权重为默认口径，组织方若有指定权重，应在 `comparison_basis.weights` 中替换后重跑。
