# plan.json schema（Agent 工作稿，非交付物）

`/app/work/plan.json` 是 Agent 把材料读成"图"的中间表示。`check` 校验它，`build` 用它覆盖确定性兜底。
所有 `quote` **必须是材料某段中的连续逐字片段**；`locator` 用 `init` 打印的段落定位（`S1 ¶12`，多页 PDF 为 `S1 p3 ¶12`）。

## 1. 顶层

```json
{
  "title": "图 1 厌氧膜生物反应器装置与技术路线",
  "subtitle": "依据 S1 方法 2.1–2.3（可选）",
  "caption": "图注文字（可选）",
  "figure_kind": "apparatus|process|route|hybrid",
  "lang": "zh|en",
  "nodes": [], "edges": [], "steps": [], "stages": [],
  "global_params": ["37 °C", "HRT 20 d"]
}
```

## 2. nodes（装置 / 物料 / 测点）

| 字段 | 必填 | 说明 |
|-|-|-|
| `id` | 否 | 缺省按 `N1..Nn` 生成；被 edges 引用 |
| `label` | 是 | 器件名，逐字取自材料；≤16 字符最佳（超长自动换行两行） |
| `role` | 否 | `device`（默认）/`material`/`measurement`/`waste`；决定填充与描边色 |
| `params` | 否 | 数值＋单位，如 `["37 °C","HRT 20 d"]`；**必须逐字出现在本节点 quote 内** |
| `qty` | 否 | 数量或计数说明，如 `"2"`（图上显示 ×2） |
| `quote` | 是 | 逐字片段，≤200 字符 |
| `locator` | 是 | `S1 ¶12` |
| `step_no` | 否 | 需要编号徽标时给（用于"按步骤排列的装置图"） |
| `pending` | 否 | `true` 表示结构/参数待人工确认 → 琥珀虚线框 + 进 `pending_human` |

## 3. edges（连接 / 流向）

```json
{"id":"E1","from":"N1","to":"N2","flow":"material","label":"进料","quote":"…","locator":"S1 ¶13"}
```

- `flow` ∈ `material|energy|signal|recycle|waste`；线型与颜色由此决定（见 figure_spec）。
- 方向必须由原文句子支撑（"…经蠕动泵送入反应器" ⇒ from=泵, to=反应器）。看不到方向就不写 edge。
- `label` 省略时用 flow 的默认名（物料/能量/信号/回流/废液）。
- 端点必须是已定义 `nodes[].id`，否则 `check` 报 `edge_endpoint_unknown` 且该线不画。

## 4. steps（操作序列）与 stages（阶段）

| 字段 | 说明 |
|-|-|
| `steps[].no` | 编号；`build` 按数组顺序重排为 1..N，保证与正文顺序一致 |
| `steps[].text` | ≤80 字符，图上最多两行 |
| `steps[].stage` | 归属阶段 id（`G1`…），用于 B 面板分组 |
| `steps[].quote`/`locator` | 同 nodes |
| `stages[].label` | 阶段名（"阶段一 启动"），≤24 字符 |
| `stages[].quote`/`locator` | 阶段标题所在段落 |

## 5. 校验与计数（`check` → `work/check_report.json`）

| code | 含义 | 修法 |
|-|-|-|
| `quote_missing` | 图元无 quote | 补逐字片段或用 `pending:true` |
| `quote_missing`(实为 missing) | quote 在材料中找不到 | 回材料重取；不改编原文 |
| `quote_unverified` | 无 quote 且未标 pending | 同上 |
| `param_not_in_quote` | 参数不在本图元 quote 内 | 把含该数值的句子作为 quote，或删掉该参数 |
| `edge_endpoint_unknown` | 端点 id 不存在 | 改 id 或补节点 |
| `plan_json_invalid` | JSON 解析失败 | 修复后重跑 `check` |

计数（`result.json.counts`）：`nodes/edges/steps/stages/elements/with_quote/quote_rate/pending/checks_fail/plan_source`；
`plan_source = agent_plan|auto`，`auto` 必然伴随 `status=partial` 与 `uncertainty[extraction]`。

## 6. locator 语法

- 段落：`S1 ¶12`（第 1 个来源的第 12 段）
- PDF 多页：`S1 p3 ¶12`
- `S#` 与 `result.json.sources[].id` 一一对应；`init` 的 `work/index.json` 给出前 40 段预览，可用 `--grep` 搜索。
