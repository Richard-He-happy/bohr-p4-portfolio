# 四级支持度判定规范（verdict rubric）

本文件是 `scripts/verify_claims.py` 的判定口径来源，也是人工复核与仲裁的唯一依据。
所有产物的 `verdict` 只能取以下四个值，不得自造档位（`needs_review`、`mostly_supported` 等一律非法）。

## 1. 四个等级

| verdict | 含义 | 必要证据 | 典型反例（不算该档） |
|---|---|---|---|
| `supported` | 论断的**全部要素**（对象、比较方向、数值、条件下、限定范围）在原文同一处被明确陈述，且无相反表述 | 逐字 quote + 段落/页码定位 | 只说同一主题、结论方向不同、数值不同 |
| `partially_supported` | 部分要素被支持：方向对但显著性/数值/条件/范围未报告或未对齐；或存在方向相反的来源 | 支持片段 + 未对齐要素的说明 | 只对上了一个关键词 |
| `contradicted` | 原文**明确陈述**相反的内容：方向相反，或否定极性相反，且对象与条件对齐 | 相反片段（role=counter） | 原文只是**没有提到**、只做了不同条件下的实验 |
| `insufficient_evidence` | 只有主题相关证据，或原文未报告该要素，无法判定支持或否定 | 检索范围 `search_scope` + 最佳候选片段 | 把"没找到"写成 contradicted |

**铁律**：未报告 ≠ 被证伪。原文没有支持的推断（例如换材料、换温区、外推到未做实验的工况）只能判
`insufficient_evidence`，并在 `uncertainties` 写明"原文未报告"。只有原文出现相反表述才可判 `contradicted`。

## 2. 判定顺序（先找反证，再定支持）

1. **检索**：以为子判断抽取的内容词 + 数值/型号锚点（`200°C`、`6061`、`35%`）在语料中打分，取最佳 6 个句子窗口。
2. **锚点门控**：论断含数值或型号时，证据窗口必须命中这些锚点；一个都不命中的窗口按 0.35 系数折减，
   视为"同主题、不同条件/不同样品"，不能作为支持证据。
3. **反证检查**：先看最佳窗口是否有相反方向（`提高/高于` vs `降低/低于/降至/缩短`）或相反否定极性。
   命中 → `contradicted`。
4. **冲突检查**：同一子判断在其他 source 或 section 出现方向相反、覆盖度可比、且论断锚点一致的片段 →
   `partially_supported` + `conflict.both_sides` 双方并列 + `verdict_confidence=low`。
5. **要素对齐**：显著性、数值、全称限定、条件四项逐一比对；任一未对齐 → 最高只能给 `partially_supported`，
   并把未对齐项写入 `limitations`（机器可读标签见第 4 节）。
6. **定级**：内容词覆盖度 ≥ 0.72 且无未对齐 → `supported`；0.40–0.72 → `partially_supported`；
   < 0.40 → `insufficient_evidence`。

## 3. 最容易误判的三类情况

**(a) 主题相关当支持。** 论断与段落共享"退火/疲劳寿命/AA5052"等词，但段落讲的是另一组比较
（300 °C vs 200 °C），此时不是支持。处理：锚点门控 + 比较对象核对；宁可 `insufficient_evidence`，
不要 `supported`。误支持比漏检扣分更重。

**(b) 未证伪当证伪。** 论断说"该机理也适用于 6061 铝合金"，原文只研究了 AA5052。
这是超出研究范围的推断，不是被实验否定 → `insufficient_evidence`，并在 `limitations` 写
`anchor_not_matched` 或 `scope_not_established`。

**(c) 摘要与结果不一致。** 摘要写"提高 35%"，结果表写"提高约 33%"，讨论段给出相反趋势。
处理：`partially_supported`（数值未对齐）+ 若方向相反则 `conflict` 双方并列；不得只取摘要或只取讨论。

## 4. limitations 机器标签（保留英文 key，便于统计与复跑）

| 标签 | 触发条件 | 对判定的影响 |
|---|---|---|
| `significance_not_reported` | 论断含"显著/显著高于/significant/p<"，证据句无显著性表述 | 封顶 partially_supported |
| `quantity_not_reported` | 论断含具体数值，证据句无任何数值 | 封顶 partially_supported |
| `reported_value_differs` | 证据句给出同类量但数值不同（原文 33% / 论断 35%） | 封顶 partially_supported |
| `scope_not_established` | 论断含全称/唯一限定（所有、仅、only、all），证据无样本域 | 封顶 partially_supported |
| `condition_not_matched` | 论断条件（如"在 200 °C 条件下"）未出现在证据句 | 封顶 partially_supported |
| `anchor_not_matched` | 论断的数值/型号锚点未全部出现在证据句 | 封顶 partially_supported |
| `conflicting_sources` | 存在方向相反的可比来源 | partially_supported + conflict |

## 5. comparator / negation / significance / conditions 的保真要求

判定前必须把这四项从论断中抽出来并在产物字段里原样保留（脚本自动抽取，人工复核时逐项对齐）：

- `comparator`：被比较的两个对象，例如 `300 °C 退火 vs 200 °C 退火`。原文比较的是别的对象即视为未对齐。
- `negation`：论断是否含否定（不、未、没有、并非、not、without）。
  **极性相反且覆盖度高** → `contradicted`；极性不同但覆盖度中等 → 不得给 `supported`。
- `significance`：论断是否声称统计显著。原文只给均值差、未报告检验 → 不构成显著支持。
- `conditions`：温度、时间、样本、剂量等限定。条件不同即"不同问题"，不能互相支持。

## 6. 冲突并列的写法

```json
"conflict": {
  "conflict": true,
  "sub_id": "S1",
  "qualified_verdict": "partially_supported",
  "both_sides": [
    {"side": "A", "source_id": "paper", "location": {"unit_id": "P2", "section": "Results", "page": 4},
     "quote": "提高约 33%"},
    {"side": "B", "source_id": "paper", "location": {"unit_id": "P3", "section": "Results", "page": 5},
     "quote": "疲劳寿命下降至 0.74×10^5 循环"}
  ],
  "note": "两侧定位并列，未折中；条件差异需人工确认"
}
```

禁止：只报一方；把两侧平均成一句"基本支持"；把冲突写成"文献有争议"而不给定位。

## 7. 示例（示例数据，非正式案例结果）

假设原文 `P4`："在 200 °C 退火 2 h 后，AA5052 的疲劳寿命由 0.9×10^5 提高到 1.2×10^5 循环（+33%，p = 0.04）。"

| 论断 | 判定 | 说明 |
|---|---|---|
| "200 °C 退火使 AA5052 疲劳寿命显著提高 33%" | `supported` | 对象、方向、数值、显著性（p=0.04）齐备 |
| "200 °C 退火使疲劳寿命提高 45%" | `partially_supported` | 方向对，`reported_value_differs`（33% vs 45%） |
| "200 °C 退火使 6061 疲劳寿命提高" | `insufficient_evidence` | 锚点不符（6061），属跨材料外推，非证伪 |
| "200 °C 退火使疲劳寿命下降" | `contradicted` | 原文明确"提高"，方向相反 |
