# `result.json` 字段字典与契约回填语义

本文件与 `main.result()` / `main.reflect()` / `main.audit()` 的实际输出一致（版本 1.1.0）。
字段名不改写、不缩写；缺失即为 `null`/`[]`，**不补造**。

## 1. 根级

| 字段 | 类型 | 含义 |
|---|---|---|
| `case_id` | str | 输入 `case_id` 原样（无则用文件名，再退 `unknown-case`） |
| `status` | str | `ok` / `partial` / `insufficient_evidence` |
| `skill` | obj | `{name, version}` |
| `generated_at` | str | UTC，`YYYY-MM-DDTHH:MM:SSZ` |
| `input_case` | str | 实际读取的 case 路径 |
| `<contract key>` | 任意 | `output_contract` 的每个键，键名不变 |
| `contract_fill` | obj | `contract_echo`（原契约）、`filled_from_payload`（真实填充的键）、`placeholder_only`（空占位键） |
| `sources` | list | 每个来源文件：`path, sha256, retrieved_at, type, extractor, provenance, license_note` |
| `uncertainty` | list | `{id, statement, meaning?, action?}` |
| `errors` | list | `{stage, error, action?, trace?}`（`trace` 限 3 层） |
| `degradations` | list | `{stage, action?, keys?, file?, http_status?, path?, tool?, error?, impact?}` |
| `pending_human` | list | `{item, reason, how}` |
| `changes` | list | `{at, what, why}` |
| `runtime` | obj | `{skill_version, seconds, python, offline}` |
| `candidates/queries/screening/coverage/families/clusters/legal_status/claims/citations/metrics/gaps/summary/gain` | 见下 | 主结果 |
| `artefacts` | list | 写出的文件名 |
| `self_check` | obj | `contract_keys, candidates, all_candidates_have_source, all_candidates_have_quote, exit_code, quotes_verified_in_source` |
| `verification` | obj | `{report, passed, failed[], checks[]}` — 来自 `audit()` |
| `note` / `payload_state` | str | 仅首次 partial 快照存在 |

`status` 规则：有候选且 `errors` 为空 → `ok`；有材料/候选但有 error → `partial`；无任何可检索内容或输入缺失 → `insufficient_evidence`。
输入缺失不单设 `input_error`，而是 `insufficient_evidence` + `errors[stage=input]`。

## 2. `candidates[]`（主产物）

| 字段 | 含义 |
|---|---|
| `id` | `C01…`（按 `relevance_score` 降序编号） |
| `doc_id` | 内部文档号 `D01…` |
| `kind` | `primary` / `duplicate` |
| `duplicate_of` | 重复时指向先出现的 `id`（判据：归一化公开号/授权号相同） |
| `type` | `patent` / `npl` |
| `title, authors, year, venue, doi, url` | 题录；源材料没有则 `null`/`[]` |
| `source_db` | `provided_corpus` / `cached_response` |
| `source_file` | 相对输入根的路径 |
| `source_sha256` | 读取时的完整哈希（版本锚点） |
| `locator` | 记录级定位：`/0`、`row:7`、`char:0` |
| `query_id` | 命中的检索式 |
| `retrieved_at` | 读取时刻（UTC） |
| `relevance_score` | 0–1，公式见 `search_and_evidence.md` §3 |
| `relevance_reason` | 分量的可读解释（可据此复算） |
| `score_components` | `{number_exact, term_overlap, classification, assignee}` |
| `numbers` | 归一化号码列表（`canonical`） |
| `legal_status` | 归一化状态或 `unknown` |
| `legal_status_verification` | `sourced_official_register` / `secondary_or_unknown_provenance` / `not_in_corpus` |
| `family_id` | 所属观测族（无则 `null`） |
| `evidence` | `{quote, locator, quote_field, quote_is_verbatim, quote_verified, verified_at}` |
| `metadata_confidence` | `high`（题名+号码/DOI）/ `medium`（仅题名）/ `low` |
| `flags` | `ocr_page_merged`、`duplicate`、`no_doi_in_source`、`legal_status_unverified` |
| `include` | 是否进入交付集（`screening` 的结果） |
| `exclude_reason` | 被排除时的理由，否则 `null` |

`evidence.quote` 只取**单一字段**的逐字文本：`quote_field` 标明取自 `abstract|summary|description|claims|title`。

## 3. `queries[]`（查询日志）

`query_id, raw, type(explicit|number|topic), db(local_corpus), source, expanded[], hits, kept, status(ok|no_hit|pending), error, retrieved_at`。
`kept` 是"命中且通过筛选"的数量；`error` 在空命中时写明"覆盖限制，不是不存在证据"。

## 4. `screening[]`

`candidate_id, include(bool), reason, criteria{years, lang, max_k, doc_type}`。
排除项**保留在 `candidates` 中**，只置 `include=false`。

## 5. `families[]` / `clusters[]`（同内容，保留两键以兼容契约别名）

`family_id, basis[](共享的 `priority:`/`application:` 号码), members[{doc_id, locator, numbers}], caliber(observed_links_only), exhaustiveness, claim_scope_note, caveat`。

## 6. `legal_status[]`

`doc_id, numbers[], status_raw, status_normalised, source_url, verification, confidence, note, action, kind_code_hint`。
`confidence` ∈ `medium`（官方 URL）/`low`（二手）/`none`（缺失）。

## 7. `claims[]`

`doc_id, claim_no, independent(bool), quote, locator, provenance, quote_is_verbatim, scope_statement`。
`independent` 由是否含 "according to claim / 如权利要求" 等从属语判定；`scope_statement` 固定为"quoted as found"。

## 8. `coverage{}`

`corpus_documents, patents, npl, queries, queries_no_hit, kept_after_screening, recall_estimate, surfaces{target_patent, family, topic_literature, claim_scope, legal_status_registry_sourced}, gaps[]`。
`recall_estimate` 在无 gold set 且未查外部库时写"not estimable"，**不给数字**。

## 9. `metrics{}`

`candidates, candidates_kept, with_source_file, with_locator, with_retrieved_at, with_query_id, with_quote, locator_coverage, quote_coverage, numbers_normalised, number_warnings, families_reported, families_caliber, claims_extracted, claims_independent, claims_with_locator, legal_status_entries, legal_status_unknown, legal_status_official, unsourced_status_claims(恒为 0), queries, queries_no_hit, duplicates_marked, precision_at_k`。
`precision_at_k` 在无相关性标注集时写"not computable"，不编造数值。

## 10. `gain{}`（自对照，非组织方白板）

`protocol, is_official_whiteboard(false), baseline{protocol, hits, with_locator, with_quote, numbers_normalised, families_reported, unsourced_status_claims}, delta{...}`。
用途：证明同一输入、同一语料、同一预算下，朴素关键词臂在"可定位/可引用/族/状态"上的缺口；**不主张**排名或 nDCG。

## 11. `verification{}`（`verify_report.json` 摘要）

`report, passed, failed[], checks[]`，检查项：

| check | 判据 |
|---|---|
| `contract_keys_present` | 契约每个键都在根级 |
| `quote_found_in_source` | 引文（空白归一后前 120 字符）能在源文件中找到 |
| `number_shape` | 号码符合 `^[A-Z]{2}\d{4,13}[A-Z]{0,2}\d?$` |
| `csv_vs_json_count` | `candidates.csv` 行数 == `candidates` 条目数 |
| `status_never_inferred` | 无"状态明确但来源为 not_in_corpus"的候选 |
| `artefacts_present` | 4 个核心文件均存在 |

## 12. 最小示意（**示例，非正式案例结果**）

```json
{"case_id": "EXAMPLE-CASE-000", "status": "ok",
 "candidates": [{"id": "C02", "kind": "duplicate", "duplicate_of": "C01",
   "title": "…", "numbers": ["US99000000B2", "US99123456", "US62990000"],
   "source_file": "records.jsonl", "locator": "/0", "source_sha256": "…",
   "query_id": "Q03", "retrieved_at": "…", "relevance_score": 0.57,
   "relevance_reason": "number_exact(US99000000B2); terms=0.35(7/20)",
   "legal_status": "unknown", "legal_status_verification": "not_in_corpus",
   "family_id": "F02", "include": false, "exclude_reason": "duplicate of C01 …",
   "evidence": {"quote": "…", "quote_field": "abstract", "quote_verified": true}}],
 "metrics": {"locator_coverage": 1.0, "quote_coverage": 1.0, "precision_at_k": "not computable: …"},
 "verification": {"passed": true, "failed": []}}
```
