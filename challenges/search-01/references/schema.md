# Result contract and data flow (version 1.0.0)

## 1. Input discovery (semantic, no fixed key names)

| Source | How it is found | What is taken |
|-|-|-|
| `case.json` | `<input>/case.json`, then `case*.json`, then any `*.json` carrying `output_contract` | `case_id`, `output_contract`, scope fields |
| `task.md` | `<input>/task.md` / `TASK.md` (first 60 000 chars) | topic fallback text, acronym seeds |
| scope object | any nested object containing `topic` / `research_question` / `years` / `max_k` / `seeds` (depth ≤ 3) | topic, keywords, include/exclude, year window, languages, databases, `max_k`, seed DOIs |
| `artifacts/*.json` | recursive scan of `<input>` (≤ 400 files, ≤ 30 MB each) | bibliographic records, response envelopes, query strings, reference edges |
| `artifacts/*.jsonl` | same | one record or one query per line |
| `*.md` / `*.txt` / `*.yaml` | same | reference edges (`{"from":..,"to":..}`), seed DOIs when the filename mentions seed/known-item/must-cite/key-paper |
| `*.csv` / `*.tsv` | same | listed only (`missing[]`: not ingested) |
| `*.pdf` | same | listed only (`missing[]`: text not extracted offline) |

A record is recognised when a dict carries a title-like key plus at least one
DOI/year/author/venue/abstract/type signal (`engine.is_work`). Envelopes are detected by
shape: `{"message": {...}}` → Crossref, `{"resultList": {...}}` → Europe PMC.

## 2. Provenance carried by every candidate

`source_db` (from record field → file path → envelope → `provided_corpus`),
`query_id` (from the enclosing response's `query` field, else `null`),
`retrieved_at` (record timestamp → envelope timestamp → file mtime, with
`retrieved_at_source` = `record` | `file_mtime`), `provenance[]` (per source record:
database, query id, retrieved_at, file, JSON pointer), `sources[]` after de-duplication.

## 3. Ranking rule (deterministic, documented)

    score = 0.55 * IDF-weighted facet coverage
          + 0.20 * recency   (linear over the most recent 12 years in the corpus)
          + 0.10 * citation impact (log1p(cited_by) normalised)
          + 0.15 * title hit share (facets matched inside the title)
          - 0.03 if the DOI is missing

Facet coverage = sum over facets of `idf(facet) * (0.7 + 0.3*min(1, hits/3)) / sum(idf)`.
A facet term matches when all of its content tokens occur in title+keywords+abstract
(order-insensitive, `engine.tmatch`). Each `matched_facets` / `matched_terms` list is
written into the candidate so the ordering can be recomputed by hand.

`url` = the record's own URL field; when the record has none it is the canonical DOI resolver
`https://doi.org/<doi>` built from that same record's DOI, and `null` when the record has no DOI.
No other URL is ever constructed.

A term containing Han characters (topics/patents in Chinese) is matched by substring, not by `\b`
word boundaries, because `\b` never fires inside a Han run; Han runs of 2+ characters count as
content units. A patent record without a DOI is kept and flagged `missing_doi`, never given a
patent number in the `doi` field.

A facet defined by a multi-word phrase also carries that phrase's content words (length > 4,
stopwords removed), so a topic such as `perovskite solar cell stability degradation` matches
records that use only some of its words. Venue is read from `container-title`/`journal`/
`journalTitle`/`venue` and, for OpenAlex-style records, from `primary_location.source.display_name`.

## 4. result.json fields

| Field | Meaning |
|-|-|
| `case_id` | verbatim from the case |
| `output_contract` | the raw contract echoed verbatim |
| every contract key | backfilled: known names map to Skill fields, nested dicts recurse, unknown scalars → `null`, unknown lists → `[]` |
| `candidates[]` | `id, rank, title, authors, year, venue, doi, url, source_db, sources, retrieved_at, query_id, route, relevance_score, matched_facets, relevance_reason, evidence_snippet, flags, provenance` |
| `queries[]` (`= query_log.json`) | 计划步骤与源端重放查询：`query_id, stage, raw, facets, hits, status, db, filters, retrieved_at`；重放查询另带 `target_db, source_file` |
| `screening` | `included`, `excluded`, `excluded_items[]` (title/doi/score/reason)；筛选条件只记一处，即 `queries[].filters` |
| `coverage` | `k_returned, n_records_read, n_unique, n_duplicates_merged, facet_coverage, uncovered_facets, metadata_gaps, seed_coverage, recall_estimate, sources_used` |
| `evaluation` | self-reported P@k / nDCG@k / known-item recall + label rule |
| `citation_chaining` | seed hits, missing seeds, reference edges used |
| `sources`, `uncertainty`, `missing`, `errors`, `degradations`, `pending_human`, `changes` | status and honesty fields |
| `runtime`, `artifacts`, `self_check` | timing, file paths, deterministic checks |

`status`: `ok` (records found, contract present, no gaps) · `partial` (gaps, errors or empty
candidate list) · `insufficient_evidence` (case readable but no records) · `input_error`
(no readable input at all). Exit code is always 0.

Candidate `flags[]` values: `missing_doi, missing_year, missing_venue, missing_abstract,
missing_retrieved_at, missing_query_id, single_source, year_conflict, seed_document`.

## 5. Companion files

`candidates.csv` (same rows, 16 columns, list fields JSON-encoded), `candidates.json` (full
candidate objects), `query_log.json` (the `queries` array: every query with `db`, `filters`, `hits`, `status`,
`retrieved_at` and facet groups, so a reviewer can re-run each step).
