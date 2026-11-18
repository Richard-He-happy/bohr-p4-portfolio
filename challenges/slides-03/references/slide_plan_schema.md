# slide_plan.json：字段、校验与示例

工作稿路径：`work/slide_plan.json`（`build --plan <path>` 可指定其它路径）。这是 Agent 的**判断载体**，脚本只校验不代写。

## 1. 顶层字段

| 字段 | 必填 | 类型 | 说明 |
|-|-|-|-|
| `deck_title` | 是 | str | 封面主标题，可含方法名/结论方向 |
| `subtitle` | 否 | str | 会议/场合/日期 |
| `audience` | 是 | str | 听众类型；决定背景比例与术语解释范围 |
| `duration_min` | 是 | num | 与页数一致：1 页 ≈ 1.2–1.5 分钟 |
| `target_slides` | 是 | int | 与任务要求一致；不一致会被记为 `page_match: false` |
| `goal` | 否 | str | 本次汇报的可检查目标（让听众认可什么/理解什么） |
| `narrative` | 否 | list | `{act, slides, purpose}`，说明取舍顺序 |
| `slides` | 是 | list | 页对象，见下 |
| `qa` | 否 | list | `{q, a, backup}`，问答准备 |

## 2. 页对象

| 字段 | 必填 | 说明 |
|-|-|-|
| `n` | 是 | 页码，从 1 连续 |
| `title` | 是 | **写结论**，不写章名（"Top-1 提升 15.4 个百分点"） |
| `layout` | 否 | `"title"` 仅首页；其余省略或 `"content"` |
| `claim` | 是（内容页） | 本页唯一主张，一句话 |
| `bullets` | 是（内容页） | 3–5 条；`{text, locator, quote}` |
| `visual` | 否 | 用哪张图表；材料无图写 `"无（材料未提供）"` |
| `evidence_strength` | 否 | `strong` / `moderate` / `weak` / `unrated` / `none` |
| `notes` | 是（内容页） | 讲稿：先讲什么、条件、被追问先答什么；**不得复述页面文字** |

## 3. 证据字段

- `locator`：`M<材料号>#p<段号>`，由 `main.py show` 打印，形如 `M1#p12`。
- `quote`：源材料中**逐字**出现的片段（任意长度，脚本去空白后做包含匹配）。可跨行，不可改写/翻译/拼接。
- 未通过校验的 `quote` 会让 `check` FAIL；`build` 时若计划不可用，脚本改用兜底计划并降低 `status`。

## 4. 校验输出（`work/check_report.json`）

```json
{"slides": 6, "bullets": 18, "quotes_checked": 18, "quotes_verified": 18,
 "slides_with_evidence": 6, "target_slides": 8, "page_match": false,
 "usable": true, "passed": false,
 "errors": [], "warnings": [{"slide": 4, "msg": "no speaker notes"}]}
```

- `usable`：没有硬错误且 ≥80% 页面带证据 → `build` 采用你的计划。
- `passed`：`usable` 且页数等于 `target_slides`。
- 硬错误：空标题、要点数不在 3–5、要点缺文本、`quote` 找不到。
- 软警告：缺 `notes`、缺 `quote`/`locator`、locator 与解析位置不一致。

## 5. 完整示例（**示例，非正式案例结果**）

```json
{"deck_title": "低数据逆合成预测的轻量适配器", "audience": "课题组组会",
 "duration_min": 12, "target_slides": 5, "goal": "认可适配器收益并接受其边界",
 "narrative": [{"act": "动机", "slides": "2", "purpose": "说明低数据失效"},
               {"act": "方法", "slides": "3", "purpose": "讲清适配器与训练代价"},
               {"act": "结果", "slides": "4", "purpose": "给数字并标强度"},
               {"act": "边界", "slides": "5", "purpose": "主动交代限制"}],
 "slides": [
  {"n": 1, "title": "低数据逆合成预测的轻量适配器", "layout": "title", "subtitle": "组会进展汇报",
   "bullets": [], "notes": "开场 30 秒：说明本次要回答的问题。"},
  {"n": 2, "title": "问题：少样本时模型失效", "claim": "数据不足时现有方法性能大幅下降",
   "bullets": [
     {"text": "Transformer 依赖大规模反应语料", "locator": "M1#p5",
      "quote": "Existing transformer models require large reaction corpora and fail in low-data regimes."},
     {"text": "我们问 5% 数据能否恢复大部分性能", "locator": "M1#p6",
      "quote": "We ask whether a small adapter can recover most of the performance with 5% of the data."},
     {"text": "参数增量目标控制在百万级", "locator": "M1#p8",
      "quote": "We propose a bottleneck adapter inserted after every encoder block, adding 1.2M parameters."}],
   "visual": "问题示意（自绘）", "evidence_strength": "strong",
   "notes": "先立共同前提：瓶颈在数据量，不在结构。"}
 ],
 "qa": [{"q": "为什么只测一个骨干？", "a": "预算限制，已在限制节说明，下一步补 GNN 骨干。", "backup": "第 5 页"}]}
```

该示例的数值与结论全部取自示例材料，用于说明字段用法，不代表任何正式案例。
