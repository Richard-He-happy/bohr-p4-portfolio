# 使用清单、最小调用示例与自查表

## 1. 使用清单（照做即可跑完一份数据）

1. 把数据放进输入目录：`case.json` + `artifacts/`（CSV/TSV/XLSX 等）。
2. 运行：`python3 scripts/main.py --input <输入> --output <输出>`。
3. 先看 `result.json.status`：`ok` / `partial` / `insufficient_evidence` / `input_error`。
4. 读 `summary` 拿到一句话结论与计数，再按五段展开：`trend` → `anomalies` → `causes` → `recheck` → `next_experiment`。
5. 任一异常点用 `locator`（文件\|表\|row N\|col 列名）与 `quote` 回查原表。
6. 若 `status != ok`，读 `pending_human` 与 `feasibility.gaps` 补齐材料后重跑。
7. 把 `causes` 的 `supported_if` / `refuted_if` 当成实验判据；把 `recheck` 交给第二人执行。
8. 需要下一轮方案时直接交付 `protocol.md`。

## 2. 最小调用示例（示例，非正式案例结果）

输入 `input/case.json`：

```json
{
  "case_id": "DEMO-001",
  "topic": "三点弯曲载荷-位移",
  "goal": "判断趋势与异常试样",
  "equipment": [{"name": "万能试验机", "model": "UTM-5kN", "range": "0-5000 N"}],
  "output_contract": {"case_id": null, "status": null, "summary": null,
                      "trend": [], "anomalies": [], "causes": [], "recheck": [],
                      "next_experiment": [], "protocol": {}, "risks": [], "uncertainty": []}
}
```

输入 `input/artifacts/bending.csv`（节选）：

```csv
x_mm,load_N,batch,channel
0,0.021,B1,ch1
4,50.113,B1,ch1
8,99.870,B1,ch1
...
40,2500.000,B2,ch2
```

调用：

```bash
python3 scripts/main.py --input input --output out
```

示意输出（**示例，仅说明接口与结构，不是任何正式案例的真实结果**）：

```jsonc
{
  "case_id": "DEMO-001",
  "status": "ok",
  "summary": "DEMO-001：1 文件/1 表；异常 1、趋势 2、原因 2、复核 2、后续 3；状态 ok",
  "anomalies": [{
    "id": "A01", "type": "outlier", "verdict": "confirmed_outlier",
    "metric": "load_N", "value": 2500.0, "reference": 375.0, "dev_pct": 566.67,
    "robust_z": 9.8, "threshold": 3.5, "batch": "B2",
    "locator": "artifacts/bending.csv | - | row 60 | col load_N", "quote": "2500.000"
  }],
  "causes": [
    {"rank": 1, "candidate": "单点操作误差", "testability": 3,
     "test": "回查原始记录/操作日志", "supported_if": "日志显示该点有偏差",
     "refuted_if": "日志无异常且复测可复现"},
    {"rank": 2, "candidate": "缺对照，难分系统偏差与效应", "testability": 4}
  ],
  "recheck": [{"id": "R01", "priority": "P1", "action": "回查导出/单位/限度口径",
               "field": "artifacts/bending.csv | row 60 | col load_N",
               "condition": "导出值=表中值", "if_confirmed": "真实读数，转原因复核",
               "if_refuted": "录入错误，改正后重跑"}],
  "artifacts": ["result.json", "protocol.md", "anomaly_table.csv",
                "recheck_checklist.csv", "risk_table.csv"],
  "output_contract": { "case_id": "DEMO-001", "status": "ok", "summary": "…",
                       "trend": [/*…*/], "anomalies": [/*…*/], "causes": [/*…*/],
                       "recheck": [/*…*/], "next_experiment": [/*…*/],
                       "protocol": {/*…*/}, "risks": [/*…*/], "uncertainty": [/*…*/] }
}
```

## 3. 交付前自查表

| 检查 | 通过标准 |
|---|---|
| 契约完整 | `output_contract` 的每个键都存在；未知键保留；缺值 `null`/`[]`；`case_id` 原样 |
| 五段齐全 | `trend`/`anomalies`/`causes`/`recheck`/`next_experiment` 均存在且非空（无异常时给说明项） |
| 可回查 | 每条异常有 `locator` + `quote`；每个原因有 `test` + 成立/否定判据 |
| 状态诚实 | 无法判断时 `status` 不是 `ok`；缺口在 `pending_human` 与 `uncertainty` 里 |
| 不编造 | 无外部文献、无自造仪器参数、无自造限度值；未读数材料明确标注 `not-read` |
| 幂等 | 同一输入重跑，`trend`/`anomalies` 顺序与内容一致（无随机性） |
| 退出码 | 任何输入（含空目录、坏 JSON）均退出 0，且写出合法 `result.json` |
| 体积 | `scripts/*.py` 每个 ≤20KB；包内 ≤12 文件、≤150KB |

## 4. 评分维度自查（与题面 2 节对应）

| 评分维度 | 本 Skill 的落点 | 自查方式 |
|---|---|---|
| 实际效果·任务完成度 | 五段结论 + `protocol.md` | 五段是否都有非空内容 |
| 实际效果·正确性 | 趋势方向/R²/拐点来自拟合；异常按水平参照判 | 抽 1 个异常点按 `locator` 回查原值 |
| 实际效果·完整性 | 全部指标扫 10–12 列、全部 sheet、`pending_human` 记缺口 | 对比 `counts.tables` 与实际表数 |
| 实际效果·可核验 | `locator`(文件\|表\|行\|列) + `quote` + `thresholds` + `runtime` | 任取一条结论能否复算 |
| 使用增益·质量 | 三层参照避免梯度误报、曲线级比较定位试样 | 拿一张梯度表试跑，看是否误报 |
| 使用增益·效率 | 一条命令出五段 + 4 个可直接分发的产物 | 从运行到读完结果的时间 |
| 创新增益 | 批次/通道绑定、按可检验性排序原因、可执行复核清单 | 看 `binding` 与 `causes[].rank` |
| 可靠体验 | 退出码恒 0、坏 JSON 降级、逐文件错误隔离 | 空目录/坏 JSON 各跑一次 |
| 生态贡献 | SKILL.md + 3 份 references + 清单 + 示例 | 新读者能否照第 1 节独立跑通 |

## 5. 常见问题

- **结果全是「无显著趋势」**：先确认数据里有单调递增的自变量列；否则 `trend` 只能给代表曲线的 `k_init`。
- **异常报得太多**：多为无水平参照的长表梯度数据；补一列剂量/时间点后重跑，判定会自动按水平分组。
- **`status: insufficient_evidence`**：材料里没有可解析数值表（只给了 PDF/图片）；按 `pending_human` 补数值表。
- **想改阈值**：只改 `scripts/analysis.py` 顶部 `CFG`，不要散改各处。

## 6. 确认项与依据专项检查

- `protocol.confirmations` 四项齐全，且全部为 `unconfirmed`；没有任何「已获批准」的表述。
- `protocol.basis` 至少含 1 条数据侧 locator+quote（有异常时）与 1 条方法侧阈值原文。
- 仪器参数、试剂目录号、限度值若材料未给，`protocol` 中不得出现具体数字，缺口进 `pending_human`。
- 风险表逐项有 `mitigation`；与异常相关的风险能在 `recheck` 找到对应动作。
