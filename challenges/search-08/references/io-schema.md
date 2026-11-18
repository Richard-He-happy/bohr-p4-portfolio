# Input discovery, output contract and audit identities

## 1. Input discovery (semantic, never by fixed key name)

The engine never assumes where a value lives; it identifies it by field alias and structure.

| Object | How it is found |
|---|---|
| case | `/input/case.json`; if absent or unparsable, the first `**/case*.json` under `/input` (a note is added to `uncertainty`) |
| `case_id` | `case_id` / `caseId` / `id` at the case root — copied through unchanged |
| `output_contract` | `output_contract` / `outputContract`; dict of field→spec or list of field names |
| criteria | any dict whose key contains `include`/`inclusion` (value = list) and any key containing `exclude`/`exclusion`; searched to depth ≤ 6 over the whole case |
| scope | any dict under `scope`, `search_scope`, `organizer_supplied_scope`, `constraints` (gives `db`, `lang`, `years`, `max_k`) |
| research question | first of `research_question`/`question`/`topic`/`task_instruction`/`objective`/`aim`/`instruction` with the longest string value |
| records | every record-bearing file under `/input`: `*.json` / `*.jsonl` / `*.ndjson` (any nesting, dicts that carry a title, abstract or DOI), `*.csv` / `*.tsv` (delimiter sniffed among `, ; \t |`) |
| material text | `*.docx` (only when no records were found), used as one local-material record |

Aliases accepted per field (case-insensitive): `title` (title, article_title, titles, 标题),
`abstract` (abstract, abstract_text, summary, 摘要), `authors`, `year` (pub_year, publication_year,
year_published, pubyear), `venue` (journal, journal_title, source_title), `doi`, `url`, `source_db`
(database, db, provider), `language`, `pubtype` (publication_type, study_type), `id` (record_id,
key, uid), `query_id`, `retrieved_at`.

**Explicit gaps:** PDF and XLSX *records* are not parsed. If the snapshot contains only those, the
run reports `insufficient_evidence`/`uncertainty` rather than inventing records. Convert the export
to CSV/JSON first.

## 2. result.json

Top level: every `output_contract` key (names unchanged, unknown keys kept, missing values
`null`/`[]`/`{}`) plus `contract_fields_filled` / `contract_fields_missing`, then:

| Field | Content |
|---|---|
| `case_id`, `status` | unchanged id; `ok` \| `partial` \| `insufficient_evidence` \| `input_error` |
| `research_question` | discovered question text |
| `criteria_*` | version + fingerprint of the operative criteria, full `criteria` rows |
| `candidates[]` | ranked included records: `rank,id,title,authors,year,venue,doi,url,source_db,query_id,retrieved_at,source_file,relevance_score,relevance_reason,matched_criteria,evidence_snippet,evidence_locator,metadata_confidence,flags` |
| `queries[]` | `query_id,db,raw,hits,record_ids,filters,status,error,retrieved_at` |
| `screening[]` | one row per record screened (including removed duplicates): A/B labels, `final`, `reason_codes`, `matched_criteria`, `include_coverage`, `score`, `confidence`, `flags`, `arbitration_rule`, `evidence`, plus `evidence_quote` |
| `dedup` | `clusters[]` (keeper, members, basis, preprint_published_mix), `duplicates_removed[]`, `near_misses_not_merged[]` |
| `arbitration[]` | `conflict_id,record_id,annotator_A/B,conflict_type,rule,basis,final,requires_human,arbiter` |
| `counts` | stage counts (see §4) |
| `audit` | pipeline order, closure booleans, per-query hits, input files, criteria fingerprint, start time |
| `coverage` | files scanned, records lacking abstract/DOI/year/language, near misses, `recall_estimate: null` + `recall_basis` |
| `metrics` | process metrics (throughput, human-review load, criteria traceability, verbatim evidence rate, Cohen's κ A/B) |
| `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `method_disclosure`, `artifacts` | provenance and honesty fields |

## 3. Artifacts written next to result.json

`candidates.csv`, `screening_labels.csv`, `arbitration.csv`, `query_log.json`, `dedup_log.json`,
`audit.json` (+ `verification_report.json` after `--check`). CSV columns follow the JSON field
names; list values are joined with `|` (authors with `; `).

## 4. Audit identities (checked by `--check`, never assumed)

```
retrieved_total = unique_after_dedup + duplicates_removed
screened_total  = include + exclude + pending_human
Σ per_query_hits ≤ retrieved_total          (a record may carry no query_id)
candidates      = screening rows with final == "include"   (same ids, same count)
```

A violation is written to `errors` and the run reports `partial` — the numbers stay as computed
rather than being adjusted to look consistent.

## 5. status semantics

| status | When |
|---|---|
| `ok` | records parsed, screening completed, counts closed |
| `partial` | completed but with a recorded defect (unparsable file, failed closure, unreadable artifact) |
| `insufficient_evidence` | no candidate records could be parsed from the snapshot |
| `input_error` | no parsable case (missing `case.json` or invalid JSON) — contract cannot be known |

`uncertainty` states what is not established (no live database, no global recall estimate, no
full-text screening, rule-based rather than human annotation). `pending_human` lists every record
whose final label needs a researcher.
