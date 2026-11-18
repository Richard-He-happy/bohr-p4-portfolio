# result.json 字段字典

所有字段都来自本 Skill 的实现，键名与 `scripts/main.py` / `scripts/citelib.py` 一致。缺值一律 `null`（标量）或 `[]`（列表），不省略键。

## 0 顶层

| 字段 | 类型 | 说明 |
|-|-|-|
| `skill` | obj | `{name, version}` |
| `case_id` | str | 输入 `case_id` 原样；缺失时 `case-unknown` |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `summary` | str | 一行计数摘要 |
| `seeds` | list | 见 §1 |
| `candidates` | list | 见 §2 |
| `edges` | list | 见 §3 |
| `screening` | list | 见 §4 |
| `missing` | list | 见 §4 |
| `coverage` | obj | 见 §5 |
| `metrics` | obj | 见 §6 |
| `baseline` | obj | 见 §7 |
| `queries` | list | 见 §8 |
| `sources` | list | 见 §9 |
| `counts` | obj | `input_files / records_raw / edges_raw / works_after_merge / edges_kept / edges_unresolved / identity_merges / queries / candidates` |
| `uncertainty` | list | `{kind, detail, affected}` |
| `pending_human` | list | `{action, why}` |
| `errors` | list | `{stage, error, impact}` |
| `degradations` | list | `{what, fallback, count?}` |
| `changes` | list | `{step, at, detail?}`，含 `partial_scaffold` 与 `finalized` |
| `runtime` | obj | `started_at / finished_at / duration_s / deadline_s / python / skill_version / network_used / pdf_tool` |
| `checks` | list | `{id, passed, detail}` |
| `self_check_pass` | bool | `checks` 全通过 |
| `contract_missing` | list | 回填后仍为空的契约字段名 |
| `artifacts` | obj | 产物文件名映射 |
| 契约字段 | any | 输入 `output_contract` 的每个键都出现在顶层 |

## 1 seeds[]

| 字段 | 说明 |
|-|-|
| `work_id` | 合并后的规范 id：`doi:` / `pmid:` / `openalex:` / `arxiv:` / `s2:` / `ttl:<sha1前10位>` |
| `title` / `doi` / `year` / `venue` | 主值（多来源时取置信度最高者） |
| `metadata_confidence` | `high`（DOI+题名+年）/ `medium`（题名+年或作者）/ `low`（仅标识或仅题名） |
| `backward_edges` / `forward_edges` | 该种子在保留图内的出边、入边条数；0 表示该方向不可用 |
| `provenance[]` | `{file, json_pointer, retrieved_at}`，最多 2 条 |
| `missing` | 缺失字段名列表 |

## 2 candidates[]

| 字段 | 说明 |
|-|-|
| `candidate_id` | `c001` 起，按分数降序 |
| `work_id` | 同 §1，已去重 |
| `title` / `authors[]` / `year` / `venue` / `doi` | 题录主值 |
| `url` | 由 DOI 推导：`https://doi.org/<doi>`；**不是抓取结果** |
| `source_db` | `crossref` / `europepmc` / `openalex` / `semanticscholar` / `pubmed` / `arxiv` / `retained_input`（按来源文件名推断） |
| `source_locator` | `{file, json_pointer, retrieved_at}` |
| `retrieved_at` | 记录自带优先，否则文件 mtime |
| `hop` | 距种子的层数（种子 0；parallel 记 2） |
| `channel` | `forward` / `backward` / `parallel` / `seed`。**语义为「最后一跳的方向」，不是「相对种子的方向」**：`forward hop2` 表示经某邻居的施引边在第 2 层到达，该候选与种子可能无直接引用关系（此时看 `related_evidence.basis` 与 `path`）。仅有 `hop1` 可比拟为直接引用/被引用 |
| `relevance_score` | 0–1，见 `workflow.md` §3 |
| `relevance_breakdown` | `{relation, proximity, topical, centrality, recency}` 分项 |
| `relevance_reason` | 人类可读：命中关系 + 关联依据 + 五个分项 |
| `citation_relation` | `{direction, edge_ids[], hop_count}`；`direction` 恒有值，取值与 `channel` 一致（末跳方向），不声明「直接引用种子」 |
| `related_evidence` | 仅 parallel 或存在耦合/共被引时：`{basis, shared_references[], co_citing_works[]}`，否则 `null` |
| `evidence[]` | 最多 6 条 `{edge_id, file, json_pointer, field, retrieved_at, direction}` |
| `evidence_snippet` | 摘要前 220 字，否则题名 |
| `metadata_confidence` | 同 §1 |
| `path` | 从种子到该候选的逐跳来路字符串（`A > B > C`），与 `edge_ids` 互补 |
| `flags` | `preprint` / `conference_version` / `retraction_marker` / `correction_marker` / `homonym_suspect` / `patent` / `non_english_title` |

## 3 edges[]

```json
{"edge_id":"e00012","citing":"doi:10.1/a","cited":"doi:10.1/b","relation":"cites",
 "source_file":"artifacts/records.jsonl",
 "evidence":[{"file":"artifacts/records.jsonl","json_pointer":"/reference/0",
              "field":"reference","item_index":0,"retrieved_at":"2026-01-02T00:00:00Z"}]}
```

单向语义：`citing` 引用了 `cited`。某文献的 forward 邻居 = `dst` 等于它的边；backward 邻居 = `src` 等于它的边。

## 4 screening[] 与 missing[]

`screening[]`：`{candidate_id, include, criteria, reason}`。`include=true` 的行覆盖每条候选；`include=false` 的行是保留图内未进入候选集的对照作品（最多 10 条，`candidate_id` 缺省）。

`missing[]`：`{item, why, action}`。逐条来自 `coverage.gaps` 与未解析种子，写明缺口、成因与建议动作。

关联依据不单列 `related[]`：它落在候选的 `related_evidence{basis, shared_references[], co_citing_works[]}` 与 `via_work` 上，总量见 `coverage.related_works`。

## 5 coverage

| 字段 | 说明 |
|-|-|
| `seeds` / `seeds_with_forward_citations` | 种子数与前向可用数 |
| `retained_works` / `retained_edges` | 去重后作品数、可用边数 |
| `returned_candidates` | 返回候选数 |
| `seed_neighbourhood_edges` / `seed_neighbourhood_coverage` | 与种子相连的保留边数，以及其中被返回集覆盖的比例 |
| `doi_rate` | 候选中有 DOI 的比例 |
| `related_works` / `excluded_works` | 有耦合/共被引依据的候选数；保留图内未进入候选集的作品数 |
| `import_states[]` | 组织方本地增量导入状态（`state/status/imported_count/pending_count/iteration/file`），仅当输入给出时存在 |
| `recall_estimate` | **恒为 `null`**，理由见相邻说明字段 |
| `gaps[]` | 缺口清单（无前向引用的种子数、未解析边、仅标识候选、撤稿/更正/预印本/专利/非英文标记、未解析种子） |

## 6 metrics（同一套指标用于候选集与基线，才能比较）

`n_items / n_unique_works / duplicate_rate / doi_rate / direction_labeled_rate / locator_rate / related_basis_rate`。

## 7 baseline

| 字段 | 说明 |
|-|-|
| `protocol` | 基线定义：保留记录上的朴素关键词匹配，不合并、不标方向、按输入顺序取前 k |
| `metrics` | 与 §6 同一函数计算 |
| `delta` | 候选集减基线，逐指标 |
| `note` | 明示"仅为运行内对照，不是组织方白板" |

## 8 queries[]

```json
{"query_id":"q003","db":"crossref","raw":"scan:artifacts/records.jsonl",
 "kind":"retained_cache_scan","hits":4,"retained":4,"status":"ok",
 "retrieved_at":"2026-01-02T00:00:00Z","note":"..."}
```

`kind`：`retained_cache_scan` / `local_index_lookup` / `planned_query`。
`status`：`ok` / `no_match` / `partial` / `not_executed`。

## 9 sources[]

`{name, kind, retrieved_at?, records?, edges?, db?, doi_candidates?}`。
`kind`：`records`（已解析记录/边）/ `pdf`（种子线索扫描，附 `text_chars` 与 `doi_candidates`；无文本时 `parsed:false`）。

## 10 去重与身份合并规则

| 顺序 | 规则 | 记录位置 |
|-|-|-|
| 1 | DOI 规范形相同（小写、去前缀、去尾标点） | `identity_merges.rule = exact_doi` |
| 2 | PMID / arXiv / OpenAlex / S2 id 相同 | `exact_pmid` 等 |
| 3 | 规范化标题（小写、去标点、压空白）完全相同，且年份差 ≤3 | `title_exact` |
| 4 | 标题相似度 ≥0.93、长度差 ≤35%、年份差 ≤1、共享作者姓氏 | `title_fuzzy` |
| — | 标题相同但年份差 >3 | **不合并**，双方打 `homonym_suspect` |

标题规范化后短于 15 字符的标题不参与键匹配（避免 "Editorial" 之类误并）。

## 11 status 取值语义

| 值 | 含义 |
|-|-|
| `ok` | 种子已解析，产出候选，无未决缺口 |
| `partial` | 有产出但存在 `uncertainty` 或 `degradations`（如部分种子无前向引用、部分行损坏） |
| `insufficient_evidence` | 无记录 / 无种子 / 种子有但无边可扩展 |
| `input_error` | 输入目录不可读 |
