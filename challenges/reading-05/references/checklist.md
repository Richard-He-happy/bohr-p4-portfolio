# 质检清单与最小工作稿示例（v2.0）

## 1. 交付前 8 项检查

| # | 检查 | 通过判据 | 失败处置 |
|---|---|---|---|
| 1 | 契约完整 | `result.json` 含 `output_contract` 全部键，`unfilled contract: none` | 置 null 并写 `pending_human` |
| 2 | 矩阵完整 | CSV 行数 = 论文数 × 字段数 | 重跑 `build`（自动补占位） |
| 3 | 引文真实 | `reported` 行 quote 全部命中，`quote_pass_rate = 1.0` | 重新复制原文或改判 `unreported` |
| 4 | 定位可回 | 每格有 locator，`show` 能回到原句 | 用 `show` 重新取 locator |
| 5 | 口径随值 | 数值格有 `unit`；跨数据集/指标有 `dataset`/`metric_scope` | 补齐元数据 |
| 6 | 可比性成对 | 每个 workorder 维度都有判定与 basis | 补 `comparability` |
| 7 | 冲突有归因 | `conflicting` 都有 sample/method/metric/condition | 补归因或改 `unresolved`+`pending_human` |
| 8 | 诚实降级 | 扫描件/解析失败/未报告项记入 `degradations`/`pending_human` | 补记，不写成事实 |

命令：`main.py check` 看 `coverage`/`quote_pass_rate`/`errors`；`build` 看 `status`/`unfilled contract`。

## 2. 状态判定

- `ok`：契约齐全、无 check 错误、无降级、覆盖率 >0；`partial`：有降级或缺格但核心表可读（最常见）；
  `insufficient_evidence`：无可用文本或全部未报告；`input_error`：`/input` 缺失或无材料。

## 3. 最小工作稿（示例，非正式案例结果）

```json
{
  "question": "某染料在某材料上的去除率是否随 pH 升高而下降？",
  "papers": [{"doc_id": "D1", "citation": "Example 2021"}, {"doc_id": "D2", "citation": "Example 2023"}],
  "fields": [
    {"field_id": "material", "name": "材料", "definition": "吸附剂/催化剂类型", "unit": "", "value_rule": "原文命名"},
    {"field_id": "pollutant", "name": "染料", "definition": "目标污染物", "unit": "", "value_rule": "原文命名"},
    {"field_id": "ph", "name": "pH", "definition": "实验 pH", "unit": "pH", "value_rule": "取最优条件对应值"},
    {"field_id": "removal", "name": "去除率", "definition": "平衡去除率", "unit": "%", "value_rule": "取报告的最大去除率"}
  ],
  "matrix": [
    {"doc_id": "D1", "field_id": "pollutant", "value": "methylene blue", "unit": "",
     "status": "reported", "quote": "Methylene blue was used as the target dye.",
     "locator": "p2#para3", "note": ""},
    {"doc_id": "D2", "field_id": "ph", "value": "7", "unit": "pH", "status": "unreported",
     "quote": null, "locator": null, "note": "pH not reported in text"}
  ],
  "comparability": [{"dimension": "pollutant", "doc_ids": ["D1", "D2"], "comparable": false,
                     "basis": "D1 亚甲基蓝，D2 罗丹明 B；不同染料不合并", "doc_id": "D1"}],
  "conclusions": [{"doc_id": "D1", "direction": "decrease", "strength": "significant",
                   "claim": "pH 升高去除率下降", "quote": "Removal decreased from 95% to 61% as pH rose.",
                   "locator": "p5#para2"}],
  "agreement": {"overall": "conflicting", "items": [{"topic": "pH 效应", "verdict": "conflicting",
                "attribution": "condition", "explanation": "D2 在 pH 3–5 区间升高；缓冲体系不同",
                "evidence": [{"doc_id": "D2", "locator": "p4#para6"}]}]},
  "limitations": ["仅 2 篇材料，无法做亚组统计"], "uncertainty": ["D2 的 pH 由图表读取，精度约 ±0.5"]
}
```

## 4. 常见失败模式

| 现象 | 根因 | 修法 |
|---|---|---|
| `quote_not_found` | 引文被改写/跨段拼接/全半角混用 | 从 `show` 原文重取，或缩到单句 |
| `cell_unknown_doc` | `doc_id` 与索引不一致 | 先 `show`（不带 `--doc`）看 id |
| `duplicate_cell` | 同一 doc×field 两行 | 合并为一行，把差异写进 `note` |
| `reported_without_value` | reported 但值为空 | 补值或改 `unreported` |
| `conflict_without_attribution` | 冲突未归因 | 补 attribution，或改 `partially_consistent` |

## 5. 抽样复核（3 分钟）

```bash
python3 -B scripts/verify.py quote --index /app/work/index.json --doc D1 --quote "<某格引文>"
```
抽 3 格（数值格、未报告格、冲突项各一）：值→引文→locator→原句闭环，单位/数据集/口径随值，冲突归因能在原文找到条件差异。
