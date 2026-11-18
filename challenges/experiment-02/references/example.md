# example.md — 最小调用示例（示例数据，非正式案例结果）

> 下面的输入是**为本说明自造的最小示例**，不是平台固定案例；输出片段标注「示例」。正式案例结果由平台运行生成。

## 1. 输入

目录（`/tmp/demo/in/`）：

```
case.json
material.md
```

`case.json`（节选，完整可运行）：

```json
{
  "case_id": "demo-001",
  "goal": "在现有酶标仪与预算内评估三版 MTT 方案的可行性",
  "output_contract": {"summary": {}, "feasibility": [], "risks": [], "other_field": []},
  "equipment": [
    {"name": "酶标仪", "model": "SpectraMax iD3", "range": "400-700 nm", "status": "已具备"},
    {"name": "离心机", "model": "5424R", "range": "100-21130 rcf", "status": "需预约",
     "lead_time_days": 2}
  ],
  "reagents": [
    {"name": "MTT", "spec": ">=98%", "stock": "5 g", "unit_price": 320, "lead_time_days": 7},
    {"name": "DMSO", "spec": "分析纯", "stock": "500 mL", "unit_price": 45}
  ],
  "budget": 2000,
  "time_window": "4 weeks",
  "personnel": 2,
  "plans": [
    {"id": "v1", "hypothesis": "高糖组细胞活力高于低糖组",
     "steps": ["接种 96 孔板，37 °C 培养 24 h", "加 MTT 20 uL，孵育 4 h"],
     "parameters": [{"name": "检测波长", "value": "570 nm"},
                    {"name": "孵育温度", "value": "37 °C"},
                    {"name": "样品体积", "value": "200 uL"}],
     "groups": ["高糖组", "低糖组", "空白对照"],
     "text": "每组 n=3 复孔，设阴性对照与阳性对照，判读 OD570>=0.5 为阳性。"},
    {"id": "v2", "hypothesis": "高糖组细胞活力高于低糖组",
     "steps": ["接种 96 孔板，37 °C 培养 24 h"],
     "parameters": [{"name": "检测波长", "value": "750 nm"},
                    {"name": "离心力", "value": "15000 rcf"}],
     "groups": ["高糖组", "低糖组"]},
    {"id": "v3", "steps": ["接种 96 孔板，37 °C 培养 48 h"],
     "parameters": [{"name": "样品体积", "value": "250 uL"}]}
  ]
}
```

`material.md`：`人源细胞株为商业购买，不涉及人体样本；MTT 为有毒试剂，需在通风柜操作并收集废液。`

## 2. 调用

```bash
python3 -B scripts/main.py --input /tmp/demo/in --output /tmp/demo/out
```

退出码 0，stdout 一行摘要（示例）：

```
case_id=demo-001 status=ok checks=105 elapsed=0.4s
```

## 3. 输出（示例片段）

`/tmp/demo/out/` 下：`result.json`、`protocol.md`、`risk_table.csv`、`check_matrix.csv`。

`result.json` 关键字段（示例值）：

```json
{
  "case_id": "demo-001",
  "status": "ok",
  "summary": {"recommended": "v1", "verdict": "feasible_with_conditions",
              "counts": {"met": 30, "gap": 64, "blocked": 2, "na": 9},
              "checks_total": 105},
  "plans": [
    {"plan": "v1", "verdict": "feasible_with_conditions", "score": 46.9, "coverage": 0.469,
     "blocking": [], "conditions": ["单列\"变量定义\"段：自变量、因变量、控制变量各是什么、怎么测", "…"]},
    {"plan": "v2", "verdict": "infeasible", "score": 28.1, "blocking": [
      {"check_id": "R-02", "item": "设备量程/精度覆盖所设参数", "note": "参数越出全部可用设备量程"},
      {"check_id": "P-02", "item": "参数落在设备量程内", "note": "参数越出全部可用设备量程"}]},
    {"plan": "v3", "verdict": "feasible_with_conditions", "score": 18.8}
  ],
  "recommended": "v1",
  "checks": [
    {"check_id": "H-01", "plan": "v1", "class": "HYPOTHESIS", "item": "可检验假设（对象+比较+方向）",
     "verdict": "met", "basis": "R-H1",
     "evidence": [{"source_id": "case.json", "locator": "case.json#/plans/0/hypothesis",
                   "quote": "hypothesis: 高糖组细胞活力高于低糖组"}]},
    {"check_id": "T-04", "plan": "v1", "class": "TIME", "item": "费用汇总与预算上限比较",
     "verdict": "met", "arithmetic": {"formula": "Σ单价×用量 vs 预算", "inputs": {"预算": 2000},
                                      "left": 320.0, "right": 2000, "delta": -1680.0}},
    {"check_id": "E-03", "plan": "v1", "class": "ETHICS", "item": "危险试剂/生物安全与废弃物",
     "verdict": "gap", "note": "涉及危险试剂或生物材料但未见对应措施",
     "action": "补 SDS、防护等级、废弃物处置路径与生物安全备案"}
  ],
  "gaps": [{"class": "RISK", "check_id": "K-01", "item": "设备故障/停机预案",
            "supply": "为关键设备写故障触发器与替代路径（备用机/外协/改期）", "severity": "major"}],
  "contract_backfill": {"summary": "filled", "feasibility": "filled",
                        "risks": "filled", "other_field": "default"},
  "artifacts": {"protocol.md": "/tmp/demo/out/protocol.md",
                "risk_table.csv": "/tmp/demo/out/risk_table.csv",
                "check_matrix.csv": "/tmp/demo/out/check_matrix.csv"}
}
```

`protocol.md` 开头（示例）：

```markdown
# 实验方案与可行性审查：demo-001
> 结论 **feasible_with_conditions**（基准版本 v1）。…
## 0. 一页结论
| 项 | 值 |
| 结论 | feasible_with_conditions |
| 推荐版本 | v1 |
| 阻断项 | 无 |
### 执行条件（满足后才能开工）
1. 单列"变量定义"段：…
```

## 4. 这段示例演示了什么

1. **三版本同批比较**：v2 的 750 nm 检测波长与 15000 rcf 超出设备量程 → `blocked` → `infeasible`；v1 全部落在量程内 → 推荐 v1。
2. **未写≠满足**：v3 缺假设/对照/参数单位 → 大量 `gap`，而不是"通过"。
3. **算术可复算**：T-04 用输入单价与预算算出 `320 / 2000`，`delta=-1680`。
4. **契约回填**：主结果类键（`feasibility`/`comparison`/`validation`/`variables`）用真实内容回填标 `filled`；`other_field` 保留但标 `default`，不冒充已实现。
5. **跨文件伦理触发**：`material.md` 提到 MTT 有毒 → E-03 记 `gap`（方案未写防护与废液处置）。

> 复现：把上面的 `case.json` 与 `material.md` 存到任意目录，按 §2 调用即可；数值会随输入变化，本页数字仅为示例。
