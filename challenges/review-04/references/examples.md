# 条目写法对照与报告片段

> **本文件全部内容为示例（示例，非正式案例结果），用来说明接口与写法，不是任何正式评测案例的答案，也不代表任何真实论文的审查结论。** 文中引用的"原文"为构造的演示句。

## 1. 一条好 finding 的六个必备件

1. 类别 + 严重度（含三判据）
2. 精确定位（句号 `S####` + 字符区间 + 章节/页）
3. 逐字 `quote`
4. `reason`：指出违反了什么，依赖的原文
5. `suggestion`：能落到句子/词/证据
6. 置信度与状态

## 2. 反例 → 正例

### 反例 A（无法复核）

```json
{"category": "argument", "severity": "major",
 "quote": "作者认为睡眠不足会影响成绩",
 "reason": "论证不够充分，逻辑存在问题",
 "suggestion": "建议加强论证"}
```

问题：quote 是概括而非原文；定位缺失；判断无法核对；建议提交后仍需人工重写。

### 正例 A（同样的问题，可交付的写法）

```json
{"category": "argument", "severity": "major", "sentence_id": "S0020",
 "title": "横断面设计支撑因果与普适结论",
 "reason": "方法段 S0011 写明 `This was a cross-sectional survey`，只支持关联；本句用 `causes` 并对 `all university students` 下结论，强度超出设计。",
 "suggestion": "把 `causes` 改为 `is associated with`；删除 `in all university students`，改为研究样本范围内的表述；若要保留因果与普适主张，需补纵向或随机干预证据。",
 "evidence": [{"sentence_id": "S0011", "kind": "design"}],
 "severity_basis": {"affects_main_conclusion": true, "fixable_by": "降强度（改词）或补纵向设计",
                    "affects_reproducibility": false},
 "confidence": "high", "status": "confirmed", "check_item": "argument:strength"}
```

发出的结果里会自动补齐：`locator_text`（如 `§Discussion ¶10 S0020 chars 1065-1167`）与逐字 `quote`。

### 反例 B（误报：把作者已声明的局限再报一次）

原句（Discussion 末段）：`A limitation of this cross-sectional design is that causal inference is not possible.`
报成"设计不支持因果" = 重复作者已声明的内容，属误报。

### 正例 B（同一稿件里真正的断点在哪）

若同一稿件的结果段写 `Sleep duration predicted exam performance (r = 0.31, p < 0.001).`，而讨论段写 `sleep deprivation causes poor performance`，则报**两句之间的强度不一致**：

```json
{"category": "argument", "severity": "major", "sentence_id": "S0021",
 "reason": "S0016 报告的是相关系数 r=0.31 的关联，S0022 又声明横断面设计无法推断因果；本句仍用 `causes`，三处口径不一致。",
 "suggestion": "改为 `is associated with`，或在补充纵向/干预数据后再使用因果表述。"}
```

### 反例 C（数值误报：把舍入当矛盾）

摘要 `12.3%`、正文 `12.34%` → 属舍入，不报。

### 正例 C（真正的数值矛盾）

摘要 `n = 240`、方法 `224 participants completed`、结果表 `N = 240` → 报 `factual`，quote 两处，`suggestion` 要求统一并按实际完成数报告流失。

### 反例 D（越界项）

报"参考文献格式未按 APA 排版""存在 3 处语法错误""查重率偏高" → 属题面排除项（格式规范/润色/查重），不产出条目，必要时在 `uncertainty` 记一行"超出范围，未审查"。

## 3. 严重度对照（同一稿件内拉开档位）

| 例子 | 档位 | 判据 |
|-|-|-|
| 横断面数据写 `causes … in all patients` 并作为主结论 | blocker | 主结论不成立，方法无法回答该问题 |
| 因果措辞但结论仅为"可能影响" | major | 强度越界，改词可修 |
| `p = 0.000` | minor | 局部报告问题，改阈值即可 |
| `±` 未说明 SD/SE | suggestion | 规范性，不改结论 |

## 4. 报告片段（示例，非正式案例结果）

```markdown
## 2 问题清单

| ID | 类别 | 严重度 | 位置 | 问题 |
|-|-|-|-|-|
| R01 | 论证链 | blocker | `§Discussion ¶10 S0020 p.6 chars 4120-4222` | 横断面设计支撑因果与普适结论 |
| R02 | 统计报告 | minor | `§Abstract ¶2 S0004 p.1 chars 168-237` | p 值报为 0.000 |

## 3 逐条意见

### R01 [blocker / 论证链] 横断面设计支撑因果与普适结论

- 位置: `§Discussion ¶10 S0020 p.6 chars 4120-4222`
- 检查项: `argument:strength`，置信度: high，状态: confirmed
- 原文:

> These results indicate that sleep deprivation causes poor exam performance in all university students.

- 判断依据: 方法段 S0011 写明 `This was a cross-sectional survey`，只支持关联；本句用 `causes` 并对 `all university students` 下结论。
- 修改建议: 把 `causes` 改为 `is associated with`；删除 `in all university students`；若要保留因果与普适主张，需补纵向或随机干预证据。
- 严重度判据: 影响主结论=true；可修正方式=降强度或补纵向设计；影响可复现=false
```

## 5. 写入 `issues_draft.json` 的最小可用片段

```json
{"case_id": "demo-000", "verdict": "设计与结论强度不匹配，主结论需降强度。",
 "issues": [{"category": "argument", "severity": "blocker", "sentence_id": "S0020",
   "title": "横断面设计支撑因果与普适结论",
   "reason": "S0011 为 cross-sectional survey；本句用 causes 且泛化到 all university students。",
   "suggestion": "改为 is associated with，删除 in all university students，或补纵向证据。"}],
 "checks": {"argument": {"status": "issues_found", "scope": "摘要/引言/讨论主张链"}}}
```

只给 `sentence_id` 即可：`verify.py` 会回填逐字 `quote`、章节、段号、页与字符区间；若 `sentence_id` 与 `quote` 不一致，以逐字匹配为准并记入 `review_records.locator_corrections`。
