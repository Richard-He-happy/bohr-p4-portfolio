# 02 — result.json and sidecar field dictionary

`result.json` is the contract surface. Every top-level key of the input `output_contract`
is present under its own name (missing values are `null`/`[]`/`{}`, never renamed or
dropped); the contract itself is echoed under `_output_contract`.

## Top-level

| Key | Type | Meaning |
|---|---|---|
| `case_id` | string\|null | copied verbatim from the input case |
| `status` | enum | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `skill` | string | name + version, e.g. `literature-delta-tracker 1.0.0` |
| `subscriptions` | array | resolved subscription: id, topic, terms, databases, include/exclude, lang, dedup keys, window rule, alert policy, schedule |
| `windows` | array | per window: index, start, end, definition source, counts |
| `new_items` | array | flattened new/changed items, each with `window_index` |
| `candidates` | array | ranked candidates (see below) |
| `queries` | array | replay log: query_id, db, raw, hits, retrieved_at, source_file, status |
| `alerts` | array | emitted alerts with delivery record |
| `coverage` | object | continuity, sources, counts, screening, metrics |
| `snapshot` | object | window end, key/work/alert counts, previous state origin |
| `sources` | array | per database: type, records, status |
| `uncertainty` | array | `{issue, impact, action}` |
| `pending_human` | array | `{item, reason, action}` for unresolved query mapping or multi-DOI merges |
| `errors` | array of strings | hard failures (still exit 0) |
| `degradations` | array of strings | partial losses, e.g. one unparsable artifact |
| `changes` | array | change records: one `window_delta` per window (with `counts`) and one `snapshot_advanced` record |
| `missing` | array | `{item, reason, needed_from, impact}` for absent inputs |
| `runtime` | object | started_at, finished_at, elapsed_s, input/output dirs, file/record/work/window counts, `model_requests: 0`, `now` |
| `checks` | object | `{checks[], passed, failed}` from `run_checks` |

## candidates[]

| Field | Meaning |
|---|---|
| `rank`, `candidate_id`, `work_id` | ordering and stable work identity (canonical DOI or hashed title) |
| `title`, `authors[]`, `year`, `venue`, `doi`, `url` | bibliographic metadata, verbatim from the source record |
| `source_db` | `crossref` / `europepmc` / `publisher` / `artifact` |
| `retrieved_at` | record timestamp when present, else the source file mtime |
| `query_id` | artifact query id or `q_unmapped` (then flagged) |
| `relevance_score`, `relevance_reason` | score and its components (`topic_coverage`, `seed_similarity`, `recency`) |
| `evidence_snippet` | verbatim prefix of abstract/title |
| `evidence_locator` | `{source_file, pointer, index_date_field}` — JSON pointer into the source artifact |
| `metadata_confidence` | `high` (DOI+authors+venue+date), `medium`, `low` |
| `delta_class` | `new` / `version_update` / `correction_or_retraction` / `recovered_late` / `duplicate_noise` / `out_of_window` |
| `version_chain` | all versions of the work with rank, dates and source file |
| `flags` | `no_doi`, `low_confidence`, `query_unmapped`, `preprint`, `notice` |

## coverage

`windows[]`, `continuity_ok`, `gap_count`, `boundary_rule`, `sources_present`,
`records_scanned`, `works_after_dedup`, `duplicates_merged`, `screening`
(`exclude_term_hit`, `include_term_miss`, `below_top_k`), `recovered_late_entries`,
`undated_works`, `problem_files[]`, `skill_metrics`, `baseline_metrics`,
`repeated_push_without_snapshot`, `metric_note`.

`skill_metrics` / `baseline_metrics` hold `precision_at_k`, `recall_at_k`, `ndcg_at_k`,
`k`, `gold_size` **only when the organizer supplied a relevance/gold list**; otherwise all
three are `null` with a `note` explaining why. `baseline_metrics` is a deliberately naive
one-shot keyword ranking over the same artifacts (no normalization, no version merge, no
snapshot diff) and is labelled as an internal comparison, never an official score.

## deltas/window_NN.json

`window_index`, `window_start`, `window_end`, `definition_source`,
`new[]` / `updated[]` / `recovered_late[]` (each item: class, work_id, title, doi, score,
index_date), `suppressed` (reason → count), `counts`.

## Sidecars

| File | Content |
|---|---|
| `candidates.csv` | one row per candidate; authors joined with `; `, flags joined with `|` |
| `query_log.json` | the `queries` array (query → db → hits → retrieved_at → source_file) |
| `alerts.json` | the `alerts` array |
| `alerts.md` | per-window digest with counts and one line per new/changed item |
| `snapshot.json` | `window_end`, `item_keys` (strong identity keys), `work_ids`, `alert_ids`, `created_at`, `skill_version` — input to the next run |

## checks (published in result.json)

`result_json_valid`, `case_id_preserved`, `status_enum`, `output_contract_complete`,
`candidates_present`, `candidate_fields_complete`, `doi_syntax`,
`doi_traceable_to_input`, `new_items_in_candidates`, `works_unique`,
`alerts_delivery_recorded`, `sidecar_artifacts_present`, `snapshot_advanced`,
`query_log_present`.

`doi_traceable_to_input` fails when a candidate DOI does not occur verbatim in the input
text: that is the guard against invented identifiers. A failing check is reported as is;
it is never masked by editing the claim.
