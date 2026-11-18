# 最小调用示例（示例，非正式案例结果）

> 本文件是**接口演示**，不是平台固定案例，也不是任何正式案例的答案。示例中的数值、设备与材料均为虚构占位，仅用于说明输入形状与输出字段。实际运行时一切数值只来自 `/input`。

## 1. 输入目录（示例）

```
/input/case.json
/input/task.md          # 可选
/input/artifacts/*.csv  # 可选：历史实验数据
```

`/input/case.json`（示例）：

```json
{
  "case_id": "EXAMPLE-001",
  "goal": "在给定反应器与材料耐热限制下，最大化目标产物收率，并控制单批材料成本",
  "parameters": [
    {"name": "temperature", "unit": "°C", "domain": [60, 70, 80, 90]},
    {"name": "time", "unit": "min", "domain": [30, 60, 90]},
    {"name": "agitation", "unit": "rpm", "range": "200-1200"}
  ],
  "equipment": [
    {"name": "jacketed reactor", "range": "20-120 °C"},
    {"name": "overhead stirrer", "range": "200-1200 rpm"}
  ],
  "reagents": [
    {"name": "catalyst A", "spec": "purity 99%, service temperature ≤90 °C", "unit_price": 3.2, "price_unit": "g", "amount": 1.5, "amount_unit": "g"}
  ],
  "constraints": ["catalyst A service temperature ≤ 90 °C"],
  "budget": 1200,
  "existing_results": [
    {"temperature": 60, "yield": 42.0}, {"temperature": 70, "yield": 51.5},
    {"temperature": 80, "yield": 58.0}, {"temperature": 90, "yield": 47.0}
  ],
  "output_contract": {
    "summary": {"type": "object"},
    "parameters": {"type": "array"},
    "cost": {"type": "object"},
    "validation": {"type": "object"},
    "risks": {"type": "array"},
    "sources": {"type": "array"},
    "uncertainty": {"type": "array"}
  }
}
```

## 2. 调用

```
python3 -B scripts/main.py   --input /input --output /app/output
python3 -B scripts/verify.py --input /input --output /app/output
```

## 3. 示意输出（节选，示例数值，非正式结果）

`/app/output/parameter_plan.csv`：

| parameter | unit | recommended | lower | upper | binding | basis_ids |
|---|---|---|---|---|---|---|
| temperature | C | 80 | 60 | 90 | declared_domain | S01,S02 |
| time | min | 60 | 30 | 90 | declared_domain | S03 |
| agitation | rpm | 1200 | 200 | 1200 | equipment_limit | S04 |

`/app/output/result.json`（节选）：

```json
{
  "case_id": "EXAMPLE-001",
  "status": "ok",
  "summary": {"goal": "…最大化目标产物收率…", "recommended": ["temperature=80C", "time=60min"], "cost_per_run": 4.8, "confidence": "medium"},
  "feasibility": {"feasible": true, "conflicts": [], "evaluated": 12},
  "search": [{"round": 1, "method": "full_factorial", "evaluated": 12, "best_score": 1.0}],
  "response_model": [{"metric": "yield", "param": "temperature", "deg": 2, "r2": 0.98, "sigma": 1.1, "n": 4, "ok": true}],
  "sources": [{"source_id": "S02", "path": "case.json", "locator": "/reagents/0/spec", "quote": "service temperature ≤90 °C", "quote_verified": true}],
  "uncertainty": [{"item": "响应-参数关系", "level": "medium", "reason": "基于 4 个数据点的二次拟合", "how_to_reduce": "补 ≥5 点预实验后重跑"}]
}
```

要点：`80 °C` 来自显式域，`90 °C` 的上界同时受催化剂耐热约束；建议值 `80` 落在两个约束的交集内，且 `binding` 字段写明是哪条约束生效。若把域改成 `[60, 80, 100, 120]`，`100/120` 会被材料耐热上限剔除，`feasibility.conflicts` 会给出 `gap` 与三个处置选项，`status` 降为 `partial`。

## 4. 这不是什么

- 不是平台固定案例的运行结果，不能作为评分证据。
- 数值未经任何真实实验验证；示例历史数据仅用于说明拟合字段的形状。
