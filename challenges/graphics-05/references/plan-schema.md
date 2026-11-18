# plan.json / content_map / result.json — 字段速查

## 1. `work/plan.json`（Agent 写的工作稿）

```jsonc
{
  "title": "≤ 140 字符，一句话说清研究对象 + 结论",
  "subtitle": "可选，一句话方法/意义",
  "caption": "图注：材料来源 + 可核对方式",
  "panels": [                       // 2–4 个，建议恰好 4 个
    {
      "id": "P1",
      "role": "problem",            // problem | method | results | implication
      "heading": "Problem",         // panel 标题（≤ 6 词）
      "flow": "how?",               // 可选：画在指向本 panel 的箭头上
      "items": [
        {
          "id": "E1",               // 建议 E1..En，content_map 用它做 element_id
          "kind": "text",           // text | value
          "label": "≤ 8 词粗体短语",
          "detail": "≤ 25 词，说明条件/方向/限定",
          "value": "2.4-fold",      // 仅 kind=value：大字号数字/量
          "evidence": {
            "source": "paper.pdf",  // 材料名（与 init 列表一致）
            "locator": "p.4 b2",    // 从 show 复制的 locator
            "quote": "逐字原文片段"  // 关键：不改写、不跨段
          }
        }
      ]
    }
  ],
  "legend": [{"label": "E145Q", "meaning": "relay mutant"}]   // 可选
}
```

规则：`role` 决定顺序与颜色，缺任一段 check 报 `missing panel role`；`value` 的每个数字必须在同一图元的 `quote` 里；不写坐标尺寸（`build_model()` 固定栅格，≤4 panel 一排、>4 两排）；每 panel 1–3 个 item，总计 6–10 个。

## 2. `output/content_map.json`（脚本产出）

```jsonc
[{"element_id": "E1", "panel": "P1", "role": "problem", "text": "label + detail",
  "svg_id": "#E1", "bbox": [x, y, w, h],
  "evidence": {"source": "paper.pdf", "locator": "p.1 b3", "quote": "…", "status": "verified"}}]
```

`status`：`verified`（locator 与 quote 一致）/ `relocated`（句子对、位置被脚本改正）/ `placeholder`（panel 无证据时的占位框）。

## 3. `output/result.json`

固定键（永远存在）：

| 键 | 说明 |
|-|-|
| `<output_contract 的每个键>` | 原样回填；语义匹配到产物，无对应则 `null`（不删键、不改名） |
| `case_id` | 取自 case.json（`case_id`/`id`/文件名） |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `sources` | `[{id,name,kind,sha1,paragraphs}]` |
| `uncertainty` | 字符串数组：被剔除图元、缺失材料等 |
| `pending_human` | 需要人确认的条目 |
| `errors` | 异常文本（有则 status 通常为 partial） |
| `degradations` | 降级：PNG 缺失、计划缺失、panel 占位等 |
| `changes` | `[{what, detail}]` 变更/构建记录 |
| `runtime` | 工具、python 版本、耗时、`unmatched_contract_fields` |

contract 匹配按语义打分（如 `editable_source` → `editable/svg/vector/source`，`export_artifact` → `export/pdf/png`）；键名不标准也能命中，命中不了的写进 `runtime.unmatched_contract_fields`。

## 4. locator 语法

| 材料类型 | locator | 例 |
|-|-|-|
| PDF（pdftotext 可用） | `p.<页> b.<块>` | `p.3 b2` |
| 文本 / md / csv | `para.<段号>`（空行分段） | `para.5` |
| PDF 无法抽文本 | 不产出段落；人工读页面后在 quote 里保持逐字，locator 写 `p.<页>` |

`show --grep "proton relay"`、`show --sid m2 --limit 10` 用于定位并复制原文。
