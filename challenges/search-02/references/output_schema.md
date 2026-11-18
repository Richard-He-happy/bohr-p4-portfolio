# Output schema and exception branches

Read this with `scripts/main.py`. Every field below is produced by the shipped code; nothing
here describes behaviour the code does not have. Outputs go to `--output` (default `/app/output`).

## 1. Files written per run

| File | When | Content |
|-|-|-|
| `result.json` | always (partial first, then final) | structured result; all `output_contract` fields echoed |
| `candidates.csv` | after ranking | one row per candidate: title, authors, year, venue, DOI, URL, source_db, retrieved_at, query_id, relevance_score/reason, snippet, locator, confidence, flags |
| `query_log.json` | after retrieval | `{case_id, queries:[…]}` |
| `query_log.jsonl` | after retrieval | one query object per line, append-safe for downstream tooling |
| `screening_log.csv` | after screening | record_id, cluster_id, decision, title, source_db, reasons |
| `selfcheck.json` | only with `--self-check` | deterministic post-run checks (see §4) |

Any write failure is caught per file; the error is appended to `errors[]` and other files still
get written. A failed artifact never aborts the run.

## 2. `result.json` top-level fields

| Field | Type | Meaning |
|-|-|-|
| `case_id` | str/null | echoed verbatim from input; never regenerated |
| `skill` | obj | `{name, version, track, lexicon_loaded}` |
| `status` | str | `ok` \| `partial` \| `insufficient_evidence` \| `input_error` |
| `question` | str/null | research question as read from input |
| `sub_questions` | list | decomposition, see §3 |
| `candidates` | list | ranked candidates, see §3 |
| `queries` | list | query log, also mirrored to `query_log.json` |
| `screening` | obj | `{criteria_used, decisions[], counts{}}` |
| `coverage` | obj | `{per_sub_question[], gaps[], n_records_in_snapshot, n_clusters, recall_estimate, scope_note}` |
| `citations` | obj | `{graph_available:false, edges:[]}` when no citation input exists |
| `conflicts` | list | heuristic polarity conflicts, each `unresolved` |
| `missing` | list | screened-in records with no sub-question match (defer) |
| `metrics` | obj | counts and rates, see §3 |
| `baseline` | obj | internal baseline control, see §3 |
| `stopping` | obj | `{rule, waves{}, reason, queries_executed, budget{}}` |
| `sources` | list | every input file read, with bytes, plus lexicon load state |
| `uncertainty` | list | `{topic, detail, impact}` |
| `pending_human` | list | items a human must resolve |
| `errors` | list | `{stage, detail}` |
| `degradations` | list | `{what, effect, count?}` |
| `changes` | list | `{step, what}` applied steps |
| `logs` | list | scan notes and non-fatal harvest messages |
| `output_contract_echo` | obj | the input `output_contract` object, unmodified |
| `runtime` | obj | version, timings, python version, `network: disabled`, `model_requests: 0` |
| `scope_used` | obj | year window, language, max_k, include/exclude, dbs, and where it was inferred from |
| `contract_report` | obj | `{mapped_fields[], n_fields}` — which contract keys got real data |

`status` is computed, not asserted: no records or no candidates → `insufficient_evidence`;
open coverage gaps or any error → `partial`; otherwise `ok`.

## 3. Nested object fields

`sub_questions[]`: `sub_question_id` (`sq01…`, max 6), `facet`
(`core|method|mechanism|outcome|comparison|gap`), `question`, `groups[]`
(`{role: anchor|facet, label, terms[], min_hits}`), `wave` (1–3), `derived_from`,
`evidence_target`, `status` (`pending|covered|empty|uncovered`), `evidence_ids[]`, `query_ids[]`.

`candidates[]`: `candidate_id` (`c001…`), `title`, `authors[]`, `year`, `venue`, `doi`, `url`,
`source_db`, `retrieved_at` (ISO-8601 UTC of the winning query), `query_id`,
`sub_question_ids[]`, `relevance_score` (0–1), `relevance_reason`,
`evidence_snippet`, `evidence_locator`, `metadata_confidence` (`high|medium`), `screening`
(`{decision, flags[]}`), `provenance[]` (member records: record_id, source_db, doi, title, year, file),
`flags[]`.

Ranking is explicit: `0.55 * BM25_normalised + 0.30 * facet_groups_matched + 0.15 * recency`.
BM25 uses field weights title 3.0, abstract 1.0, keywords 2.0, venue 0.5, authors 0.3.

`queries[]`: `query_id`, `sub_question_id`, `wave`, `db`, `raw`, `expanded_terms[]`,
`filters{year_from, year_to, lang}`, `hits`, `returned_ids[]`, `mode`, `status`
(`ok|empty`), `error`, `retrieved_at`. A sub-question field with no hit yields `status: "empty"`,
which is recorded rather than filled.

`metrics`: `n_candidates`, `n_sub_questions`, `n_sq_with_evidence`, `sub_question_coverage`,
`n_queries`, `n_queries_empty`, `n_raw_records`, `n_clusters`, `n_dup_merged`,
`doi_wellformed_rate`, `snippet_rate`, `comparison_vs_baseline{}`.

`baseline` (internal control, not the organizer whiteboard): one flat `OR` query over the same
snapshot and same `max_k`, with no decomposition, expansion, dedupe or screening. It reports
`hits`, `returned`, `candidate_ids[]`, `in_scope_share`, `duplicate_exports_in_returned`,
`facets`, and a `note` stating the comparison is internal.

`complexity` note: `skill_in_scope_share_by_construction` is labelled that way on purpose —
screening is applied by the skill, so that number is not independent evidence of quality.

## 4. `--self-check` (`selfcheck.json`)

Deterministic, no network, no model. Per candidate it flags `missing_<field>` for title,
source_db, retrieved_at, query_id, relevance_reason, evidence_snippet; `query_id_not_in_log`;
`malformed_doi` (must match `^10\.\d{4,9}/\S+$`); and
`snippet_not_found_in_source_record` when the stored snippet is not a substring of the
candidate's own provenance records. Result: `{status: pass|warn, n_issues, issues[], candidates,
queries, contract_fields, run_status, screening_records}`.

## 5. Exception branches

| Condition | Detection | Handling | Where it is reported |
|-|-|-|-|
| No `/input/case.json` | path checks, then `case*.json` glob | continue; question from `task.md` or record titles | `errors[]`, `sources[]` |
| Malformed JSON | `lj()` returns error string | case stays `{}`; run continues on materials | `errors[]` |
| Empty `/input` | `scan()` finds no records | status `insufficient_evidence`, no candidates invented | `status`, `coverage.scope_note` |
| No research question | `q_of()` returns nothing | decomposition skipped, records only | `uncertainty[]` (topic `research_question`) |
| Query returns nothing | `hits == 0` | query logged `status: "empty"`, sub-question `empty` | `queries[]`, `coverage.gaps[]` |
| No DOI in record | field absent | `doi: null`, confidence `medium` | `degradations[]` |
| No key-paper labels | never present in this track | P/R/nDCG not reported as numbers | `uncertainty[]` (topic `gold_labels`) |
| No citation input | no graph file | `citations.graph_available: false` | `citations` |
| Missing lexicon | file unreadable | built-in minimal facet table | `degradations[]` + `skill.lexicon_loaded` |
| Output dir not writable | `mkdir` raises | fall back to `$TMPDIR/search02-out` | `runtime.output_dir` |
| Any uncaught exception | top-level handler | existing/partial `result.json` re-written with `status: partial` and traceback | `errors[]`; exit code stays 0 |

Duplicate exports are merged, never dropped: the cluster keeps one row and lists every source
record under `provenance[]` with the flag `duplicate_export_merged`.
