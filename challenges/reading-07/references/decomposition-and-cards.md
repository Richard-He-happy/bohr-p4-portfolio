# 论断拆解、证据卡与双人标注规范

## 1. 为什么必须拆

一条复合论断里的不同子判断可能一个成立、一个不成立。整句给一个 verdict 会同时制造**误支持**
（把成立的部分扩大成整句成立）和**漏检**（不成立的部分被掩盖）。因此每条输入 claim 至少拆出 1 个子判断，
含并列/因果/比较/限定的句子至少拆 2 个。

## 2. 拆分规则（脚本 `decompose()` 实现，人工复核按同一规则）

1. 先按 `；;。\n` 切句。
2. 再按并列连接词切子句：`并且 而且 同时 此外 另外 以及 但是 然而 不过 但 且`（英文 `and also`, `, and`, `, but`, `, while`）。
3. 若仍未拆分，但逗号两侧各含一个方向词（如"提高 20%，降低 10%"），按逗号拆成两条比较判断。
4. 因果句不拆成两半：保留为**一条** `causal` 子判断，并要求证据句同时出现原因侧与结果侧（只给相关性不行）。
5. 去重：文本归一化后前 60 字符相同者只保留一条（避免同一判断重复核验）。
6. 上限 7 条，超出部分合并进最后一条并在 `limitations` 记 `merged_tail`。

## 3. 子判断类型与所需证据

| type | 触发线索 | `required_evidence_type` |
|---|---|---|
| `fact` | 无数值比较、无因果、无限定 | 明确陈述同一发现的句子（含对象与数值） |
| `comparison` | 高于/低于/优于/劣于/大于/小于/相比/higher than/than | 同时给出两个对象、同一指标、同一方向 |
| `causal` | 导致/因为/因此/使得/引起/cause/lead to/due to | 明说因果链或干预结果的句子，不是相关 |
| `scope` | 所有/全部/仅/只/均/always/only/all | 给出样本域或边界条件的句子 |

## 4. 必须保留的四个要素

`comparator`（比较对象）、`negation`（否定）、`significance`（显著性）、`conditions`（条件）在子判断对象上
逐一给出，任一缺失都会让判定无法复核。脚本自动抽取；人工复核时对照原文确认：

- comparator 抽取：`A 高于 B` → `A vs B`；`compared with X`/`相比 X` → `X`。
- negation：不/未/没有/无法/并非/not/without，排除"不同、不断、不仅、不少"。
- significance：显著/极显著/significant/p<0.05/95% CI。
- conditions：`在……条件下`、`当……时`、`under ... conditions`、`for ... samples`。

## 5. 证据卡 schema（`evidence_cards.jsonl`，一行一张卡）

```json
{
  "card_id": "EV-C2-S1", "claim_id": "C2", "claim_text": "AA5052 在 300 °C 退火后的疲劳寿命高于 200 °C 退火试样。",
  "sub_id": "S1", "sub_text": "AA5052 在 300 °C 退火后的疲劳寿命高于 200 °C 退火试样。",
  "type": "comparison", "required_evidence_type": "both entities, same metric, same direction",
  "verdict": "contradicted", "verdict_confidence": "medium",
  "comparator": "AA5052 vs 200 °C", "negation": false, "significance": false, "conditions": null,
  "evidence": [{"source_id": "paper", "unit_id": "P3", "label": "paper | sec:Results | p.5 | unit:P3",
                "locator": {"type": "json", "json_pointer": "/paragraphs/2", "unit_id": "P3", "section": "Results", "page": 5},
                "quote": "在 300 °C 条件下退火 4 h 后，AA5052 试样的疲劳寿命下降至 0.74×10^5 循环，说明过热退火会缩短疲劳寿命。",
                "supports": false, "role": "counter"}],
  "rationale": "原文方向与论断相反（up/down）；覆盖度 0.71；证据句：……",
  "limitations": [], "counter_evidence_searched": true,
  "search_scope": {"units_scanned": 4, "sentence_windows": 4, "candidates_kept": 3},
  "conflict": false
}
```
（以上为**示例**，非正式案例结果。）

### 定位（locator）要求

- JSON 材料：`json_pointer`（如 `/paragraphs/2`）或 `paragraph_id` + `section` + `page`。
- 文本/MD：`block` 序号；PDF：页序 + 提取方式（写入 `sources[].format`）。
- 禁止只给"篇名 + 作者"。跨段证据给两条 quote，各自带 locator。
- `quote` 必须与原文逐字一致（脚本 `verify_quote` 会归一化空白后比对，不命中即拒收）。

## 6. 双人标注与仲裁流程（无需额外脚本）

1. **标注者 A** 运行 `verify_claims.py`，得到 `evidence_cards.jsonl`（机器初判，`evidence_path=rule_engine`）。
2. **标注者 B** 另建 `review.csv`，列：`card_id, verdict_A, verdict_B, reason_B, quote_B`；
   只对 A 的 `supported` 与 `contradicted` 卡片逐张回原文核对（这两类错判代价最高）。
3. **仲裁规则**：
   - 双方一致 → 保留。
   - B 给出**逐字 quote 且支持相反判定** → 采纳 B，卡片 `verdict_confidence` 降为 `low`，并把两段 quote 写入 `conflict.both_sides`。
   - B 只有意见、无 quote → 不采纳，卡片保留 A 的判定，`pending_human` 记一条待核。
   - 分歧集中在 `partially_supported` 与 `supported` 之间时，按 rubric 第 2 节第 5 步逐项对齐要素，不投票。
4. **一致性指标**：`agreement = 一致卡片数 / 复核卡片数`，写入运行说明；低于 0.8 时先修 rubric 再扩案例。
5. 仲裁产生的最终 `verdict` 必须能回溯到某条 quote；不能回溯的判定一律回退到 `insufficient_evidence`。

## 7. 复核自查（他人可独立完成）

- 每张卡的 quote 能否在 `sources[].path` 指的文件中检索到？
- 卡片的 `verdict` 是否在四级集合内？`partially_supported` 是否写清了哪一项未对齐？
- `contradicted` 是否给出了明确的相反表述，而不是"未提及"？
- 冲突卡是否两侧都有 locator 与 quote？
- `coverage` 的四类计数之和是否等于 `claims_verified`，`sub_claim_verdicts` 之和是否等于 `split_subclaims`？
