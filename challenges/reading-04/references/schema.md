# 输出契约与判定规则（schema）

本文件是 `result.json` 的字段字典，也是评审核对「字段是否齐全、状态是否诚实」的依据。
脚本 `scripts/main.py` 按本文件生成字段；字段名被平台适配时，层级与含义保持不变。

## 1. 顶层

| 字段 | 类型 | 含义 |
|-|-|-|
| `case_id` / `paper_id` / `material_version` | string / null | 原样取自输入；缺失为 `null`，不自造 |
| `status` | enum | 整体状态：`ok` / `partial` / `insufficient_evidence` / `input_error` |
| `result` | object | 业务主体：`answers[]` + `unanswered_parts[]` + `coverage` |
| `answers`（兼容镜像） | array | 与 `result.answers` 相同，便于按题目序读取 |
| `claims` | array | 全部论断展平列表（每题 `claims[]` 的并集，去重前） |
| `uncertainties` | array | 未报告 / 低召回 / 证据冲突等，不得写成事实 |
| `pending_human` | array[string] | 需要人工确认的具体动作 |
| `errors` | array[object] | 运行异常（`stage`、`question_id`、`error`） |
| `degradations` | array[object] | 降级（缺词表、缺 patch、兼容件写失败等）与影响 |
| `changes` | array[object] | 本次运行产生的结构化变更（如生成跨段推断 claim、合并 patch） |
| `sources` | array[object] | 输入来源与 `sha256_16`，供回溯 |
| `counts` | object | 计数证据：题数、各状态数、claim 数、quote 命中率 |
| `method_notes` | object | 流程与引用策略说明（不替代结果） |
| `runtime` | object | 脚本耗时、Python 版本、版本号、预算说明 |
| `contract_keys` / `question_ids` | array | 输入 `output_contract` 的键名、输入问题 id（自检用） |

**契约回填**：输入 `output_contract` 的每个键都出现在顶层；已知键用真实内容填充，未知键原样保留，
缺值为 `null` 或 `[]`，键名不改。

## 2. `result.answers[]`

| 字段 | 类型 | 要求 |
|-|-|-|
| `question_id` | string | 与输入一致；输入只给字符串题干时脚本生成稳定 `Q1..Qn` 并写入 `question_ids` |
| `question` | string | 原题干（便于核对） |
| `answer` | string | 中文回答，逐题分块（多子问用 `【子问N】`），数值/单位/条件取自引文 |
| `conditions` | array[string] | 成立条件（条件片段 + 段落号）；无则为 `[]` |
| `status` | enum | `answered` / `partial` / `insufficient_evidence` / `input_error` |
| `claims` | array | 本题论断 |
| `unanswered_parts` | array | 未答部分；`answered` 时为 `[]` |
| `evidence_paragraph_ids` | array[string] | 本题引用到的段落号（`coverage` 计数来源） |

`status` 判定：

- `answered`：题干所有子问都有原文依据；数值题必须取到带单位的数值；「材料未报告」经检索证实也可为 `answered`。
- `partial`：有部分依据但缺子问/缺数值，或跨章节只补到一侧。
- `insufficient_evidence`：全篇检索无可用依据。
- `input_error`：案例包读不出（缺文件、坏 JSON、无问题清单）。
- 四个值之外不得出现 `ok`、`unknown`、`N/A` 等。

## 3. `claims[]`

| 字段 | 类型 | 要求 |
|-|-|-|
| `claim_id` | string | 稳定且唯一，如 `Q1-S2-C3`、`Q1-INT1`（跨段推断）、`Q1-ABS1`（未报告） |
| `question_id` | string | 归属题目 |
| `text` | string | 论断文本；数值论断写成 `label = value unit` |
| `kind` | enum | `reported`（原文报告）/ `inferred`（由两段以上合并或由缺席推出） |
| `readability` | enum | `directly_read`（可直接读出）/ `inferred`（合理推断）/ `undetermined`（无法确定，含未报告） |
| `conditions` | array[string] | 该论断成立的条件片段 |
| `source_id` | string / null | 论文标识（与 `paper_id` 一致），多条证据时仍定位到同一篇 |
| `evidence[]` | array | 见下 |

`kind` 只有两个值，`readability` 是同一论断的细分级：`reported → directly_read`，
`inferred → inferred`（可推断）或 `undetermined`（未报告/无法确定）。未报告类 claim 允许 `evidence` 为空，
但必须在 `uncertainties` 里附检索统计（检索词、零命中数、已检索段数）。

## 4. `evidence[]`

| 字段 | 类型 | 要求 |
|-|-|-|
| `paper_id` | string / null | 与顶层一致 |
| `paragraph_id` | string | 必须存在于输入段落清单 |
| `section` | string | 段落所属章节（缺省 `unknown`） |
| `locator` | string | 定位串，如 `/paragraphs/12`、`/tables/1`、`/text#P7` |
| `quote` | string | **逐字原文**，不得翻译、改写、拼接两段；通常 15–60 词 |
| `char_start` | int | 引文在段落文本中的起始字符偏移（`-1` 表示未命中） |
| `quote_verified` | bool | `char_start >= 0` 的机器校验结果 |
| `quote_words` | int | 引文词数 |

校验口径：`paragraph.text[char_start:char_start+len(quote)] == quote`，且 `quote in paragraph.text`。
脚本从原文按字符区间切片，天然满足；人工或 Agent 补充的引文必须重跑 `--apply` 或自检才会被接收。

## 5. `result.unanswered_parts[]`

```json
{"part": "未答的子问原文", "question_id": "Q2", "reason": "no_matching_paragraph | numeric_value_not_reported | internal_error",
 "missing": "缺什么", "needed": "需要什么材料才能补"}
```

`answered` 题必须为空；`partial` / `insufficient_evidence` 题必须有条目。

## 6. `result.coverage`

| 字段 | 含义 |
|-|-|
| `paragraphs_supplied` / `paragraphs_indexed` | 输入段落数 / 实际建索引数（本题为全量） |
| `paragraphs_cited` / `cited_paragraph_ids` | 被引段落数 / 列表 |
| `sections_read` / `sections_unread` / `unread_reason` | 已读章节（含段数）/ 未读章节 / 原因 |
| `chars_supplied` | 索引字符数 |
| `not_supplied` | 材料未提供的对象（如未给表格、未给图注） |
| `method` / `note` | 阅读方式与边界说明（本题为已抽取文本，无页图/像素，故无页码与图元读数） |

## 7. `uncertainties[]` 与 `pending_human[]`

`uncertainties` 条目：`{"type": "not_reported|low_recall|conflict|missing_meta", "question_id", "detail", "zero_hit_terms", "paragraphs_searched"}`。
`pending_human` 为自然语言动作，例如「Q3 未见直接证据，请人工确认『未报告』结论」。

原文互相矛盾时（同一量给出两个值）：两条都保留为 `reported`，并在 `uncertainties` 记 `conflict` 与两处段落号，
不得选一个当唯一事实。

## 8. 与评分维度的对应

| 评分点 | 落点 |
|-|-|
| 任务完成度 | `answers[]` 每题一项（含无法回答的），`status` 齐全 |
| 结果正确性 | `claims[].text` 的数值/单位 + `evidence[].quote` 逐字原文 + `conditions` |
| 结果完整性 | 子问拆块 `【子问N】` + `unanswered_parts` |
| 结果可核验性 | `paragraph_id` + `locator` + `char_start` + `quote_verified` + `evidence_map.csv` |
| 质量/效率增益 | `counts`（题数、claim 数、quote 命中率）、`method_notes`、`verify_report.json` |
| 创新（跨章节/条件/拒答） | `INT1` 跨段推断、`conditions`、`ABS1` 未报告判定与检索统计 |
| 可靠体验 | `errors` / `degradations` / `status=input_error` 分支 |
| 生态贡献 | 本文件 + `glossary.md` + `example.md` + SKILL.md 调用步骤 |
