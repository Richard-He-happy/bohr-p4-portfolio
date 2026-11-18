# 结构问题分类表与规则索引（taxonomy）

本文件是 `scripts/verify.py` 的说明书：每个规则 ID 对应 `references/messages.json` 的
`<ID>`（诊断）/ `<ID>_b`（判定依据）/ `<ID>_e`（动作效果）/ `<ID>_r`（风险）四条文案模板。
改阈值只改代码常量，改措辞只改 JSON，两者互不影响。

## 1. 六维度定义（固定枚举，缺项必须给证据）

| key | 定义 | 不属于本维度 |
|---|---|---|
| `research_question_alignment` | 研究问题是否被清楚提出、是否贯穿到方法与结果；贡献主张是否与实际完成的工作一致 | 研究问题本身是否有趣 |
| `section_structure` | 章节是否完备、顺序是否服务于论证、篇幅分配是否合理、参考文献章是否可用 | 章节标题的措辞美感 |
| `argument_chain` | 每条判断性论断是否有可指认的论据（引用、数值、图表）；引用与图表是否可回溯 | 论据是否足以改变学界共识 |
| `paragraph_relations` | 相邻段落之间关系是否显式（过渡/对比/递进）、单段是否混装多种功能 | 句子长短、单句成段等风格 |
| `duplication` | 同一内容在段内/跨章节重复表述，读者无法判断主论述位置 | 术语的必要回指 |
| `conclusion_boundary` | 结论是否越过数据与设计允许的范围（因果化、绝对化、数值越界） | 结论是否新颖 |

## 2. 规则表

| ID | 维度 | 触发条件（可在原文复核） | 默认严重度 | 动作 |
|---|---|---|---|---|
| s1 | section_structure | 解析到的章节块 ≤1（无任何标题行） | high | insert |
| s2 | section_structure | 缺 introduction/method/result/conclusion 之一（有 discussion 时 conclusion 可豁免） | high | insert |
| s3 | section_structure | 章节角色序列中 method 晚于 result，或 result 晚于 discussion/conclusion | high | move |
| s5 | section_structure | 有 references 章但无 `^\[?N[].)]` 条目 | medium | insert |
| r1 | research_question_alignment | 前 8 段无研究问题句式（we ask / this study examines / aim of / hypothes / 本研究） | high | insert |
| r2 | research_question_alignment | 研究问题关键项 ≥50%（且 ≥3 项）未出现在结果/讨论/结论 | high | narrow |
| r3 | research_question_alignment | 贡献句关键项 ≥60%（且 ≥3 项）未出现在结果章 | medium | narrow |
| a1 | argument_chain | 段落 ≥30 词，含主张标记句，且段内 0 处引用/数值/图表指向 | high（结果/讨论/结论） | insert |
| a2 | argument_chain | 正文引用编号在参考文献列表中缺号 | high | insert |
| a3 | argument_chain | 正文引用 Figure/Table N，但全文无对应图题/表题 | medium | insert |
| p1 | paragraph_relations | 同章相邻段均 ≥55 词，词项 Jaccard <0.05，且后段段首无过渡词 | low | insert |
| p2 | paragraph_relations | 单段 ≥120 词，含 ≥2 个数值句且 ≥1 个主张句（结果与解释混层） | medium | split |
| d1 | duplication | 段落 ≥45 词，10 词 shingle Jaccard ≥0.30 | medium（跨章且≥0.5 为 high） | merge |
| d2 | duplication | 同一句（归一化后 ≥55 字符）在两个位置逐字出现 | medium | delete |
| c1 | conclusion_boundary | 方法/结果只有相关性表述、无干预/对照设计，而结论句用因果动词且无限定 | high | narrow |
| c2 | conclusion_boundary | 结论/讨论/摘要句含绝对化表述（prove/always/never/guarantee/所有…）且无限定 | medium | narrow |
| c3 | conclusion_boundary | 结论句出现带单位的数值，且该数值未在方法/结果/摘要出现 | low | narrow |

阈值常量：`0.30`（段落重复）、`0.05`（段落衔接）、`55/45/120/30`（词数门槛）、`6`（单维结论类发现上限）。
任一规则命中 0 次 → 该维度输出 `no_issue_with_evidence` 并写明检查了对象数量（见 `cov_*` 文案）。

## 3. 结构问题四大类（与五类突破方向的对应）

| 问题类 | 典型表现 | 主要规则 |
|---|---|---|
| 断裂 | 论断无据、引用缺号、图表无出处、研究问题与结果脱节 | a1, a2, a3, r2, r3 |
| 重复 | 同段复述、跨章节复述、整句重复 | d1, d2 |
| 跳跃 | 章节顺序倒置、段落无过渡、段内混层、缺章 | s1, s2, s3, p1, p2 |
| 越界 | 相关说成因果、绝对化、结论数值越出结果范围 | c1, c2, c3 |

## 4. finding / action 字段定义

| 字段 | 含义 | 约束 |
|---|---|---|
| `finding_id` | F01… | 全局唯一，action 通过它 join |
| `dimension` | 六类之一 | 固定枚举 |
| `severity` | high/medium/low | 决定 priority P1/P2/P3 |
| `locator` | `C03` / `C03-P002` / `C03-P002-S01` | 必须能在稿件中定位 |
| `quote` | 原文片段 | 逐字子串，未命中即丢弃 |
| `diagnosis` | 结构问题判断 | 只描述结构，不评价科学正确性 |
| `evidence_for_judgment` | 判定依据与计数 | 可复算 |
| `confidence` | high/medium/low-medium | 与 severity 分离 |
| `operation` | move/merge/split/narrow/delete/insert | 固定枚举 |
| `from_locator` / `to_locator` | 动作起止 | merge/move 必给 to |
| `expected_effect` / `risk` | 动作预期与副作用 | 非空 |

## 5. 论点—论据映射表模板（argument_map.json）

```json
{"research_question": {"quote": "<研究问题原句>", "locator": "C02-P001-S03"},
 "chains": [{"chapter": "C04", "paragraph": "C04-P002",
             "claim": {"locator": "C04-P002-S01", "quote": "<论断原句>"},
             "evidence": [{"locator": "C04-P002-S02", "quote": "<论据原句>", "kind": "number"}],
             "status": "supported"}],
 "unsupported_chains": 0,
 "method": "逐句抽取主张标记句与论据句（引用/数值/图表指向），按段落配对"}
```

`status=unsupported` 的链即 a1 规则的证据来源；评审可据此复核"论断是否都有论据"。

## 6. 使用建议

1. 先看 `dimension_coverage`：`no_issue_with_evidence` 表示该维度检查过但无发现，不是漏项。
2. 再按 `edit_plan.md` 的 P1→P3 执行；每条动作的 `from_locator` 可直接在稿件中定位。
3. 对 `confidence=low-medium` 的条目（p1、r3、c3）建议人工确认后再采纳，这符合题面
   "作者复核后能判断该采纳、部分采纳还是驳回"。
