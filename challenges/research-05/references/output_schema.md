# result.json 字段定义与 output_contract 回填规则

## 1. 顶层字段

| 字段 | 类型 | 含义 |
|---|---|---|
| `skill` / `skill_version` | str | 固定 `research-topic-novelty-appraisal` / 版本号 |
| `case_id` | str | 原样保留输入 `case_id`（缺失时 `unknown-case`） |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `topic` | str | 从 case 语义提取的研究主题 |
| `research_product` | obj | 四项交付，见 §2 |
| `sources` | list | 每个来源：`source_id, path, title, year, doi, sha256, included, inclusion_reason` |
| `evidence` | list | 证据：`evidence_id, source_id, locator, quote, stance, strength` |
| `evidence_matrix` | obj | `rows / included / excluded / reasons`（纳排计数与理由分布） |
| `comparison_matrix` | list | 与 `comparison_matrix.csv` 同源的行 |
| `search_protocol` | obj | `executed=false`、时间窗、检索式、筛选规则、术语面、可复现哈希 |
| `coverage_metrics` | obj | 本地术语覆盖、含证据来源数 |
| `claims` | list | 结论-证据映射：`id, kind, text, evidence_ids, strength` |
| `conflicts` | list | 冲突证据对：`topic_term, support{}, against{}, resolution, needs_human` |
| `gaps` | list | 研究空白：`type, description, basis` |
| `uncertainty` | obj | `items[]`：`type, detail` |
| `pending_human` | list | 必须人工确认的事项 |
| `errors` / `degradations` | list | 失败项 / 降级项（分开记录，不混写） |
| `changes` | list | 变更记录（partial → finalize） |
| `runtime` | obj | 版本、耗时、预算 |
| `tool_call_trace` | list | 读取/解析留痕：`target`、`sha256` |
| `artifacts` | obj | 四个产物的绝对路径 |
| `consistency_check` | obj | 契约键齐全、结论全部挂证据、四项交付、纳排加和 |

## 2. research_product

```
problem_definition   {statement, elements[5], decomposition_gaps[], weighted_tree[5], testable_statement, evidence_ids[], strength}
prior_work_comparison{n, items[]（task/method/data/evaluation/conclusion/comparability_note/inclusion_reason）, comparable_dims[], evidence_ids[]}
novelty_assessment   {items[]（claim/kind/overlap_score/coverage/closest_source/closest_locator/closest_quote/boundary）, covered_count, verdict, scope_note}
feasibility          {premises[5]（premise/label/status/source_id/locator/quote/action）, supported, verdict, blocking_premises[], failure_risks[], evidence_ids[], strength}
```

枚举值（不可自造）：
- `elements[].source`：`case_fields` / `derived_from_terms` / `not_in_materials`
- `novelty_assessment.items[].coverage`：`covered` / `partially_covered` / `not_covered_in_materials` / `undetermined`
- `novelty_assessment.items[].kind`：`method` / `data` / `context` / `conclusion` / `undetermined`
- `feasibility.premises[].status`：`material_supported` / `mentioned_not_confirmed` / `assumed_not_documented`
- `feasibility.verdict`：`feasible_with_conditions` / `conditionally_feasible_pending_premises` / `insufficient_information`
- `claims[].strength` / `evidence[].strength`：`directly_supported` / `inferred` / `insufficient`
- `evidence[].stance`：`supports` / `contradicts` / `neutral`

## 3. output_contract 回填规则

1. 输入 `case.json` 的 `output_contract`（或 `outputContract`）整体复制到 `output_contract` 字段，原样不改。
2. 其中**每个键**在 result.json 顶层同名出现：本 Skill 已有同名产物则用本产物，否则按类型补空值——list→`[]`，dict→`{}`，其余→`null`。
3. 嵌套 dict 契约的二级键同样补齐（`setdefault` 语义），不删除未知键。
4. 键名不改写、不合并；`case_id` 原样保留。
5. 若契约要求的对象在材料中不存在：字段保留为空，并把缺口写入 `pending_human` 与 `gaps`，不构造内容。

## 4. 定位符（locator）格式

| 材料 | locator | 例 |
|---|---|---|
| PDF | `p.<页序>` | `p.3` |
| Markdown/TXT/JSON/CSV | `para.<段序>` | `para.12` |
| RIS 记录 | `rec.<序>.<字段>` | `rec.2.AB` |
| DOCX/XLSX | `blk.<序>` | `blk.4` |

## 5. quote 铁律

- quote 为材料文本按「折叠空白」归一化后的**连续子串**，长度 ≥12 字符，不翻译、不改写、不拼接。
- `assess.py --check` 会重新解析材料并逐条比对；未命中进入 `misses`，该条不得作为结论依据。
- PDF 无文本层时 `degradations` 记 `low_quality:<file>`，`uncertainty` 记 `extraction`，不静默丢弃。
