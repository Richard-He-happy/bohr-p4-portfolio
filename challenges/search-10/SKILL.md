---
name: cross-lingual-known-item-search
description: >-
  Cross-lingual literature retrieval for academic search tasks. Builds a
  concept table from the research question, plans one query per target
  language, retrieves over the record corpus supplied by the case (or a file
  collected with a search tool), identifies the language, version and
  attribution of every hit, merges the language versions of one work so that
  duplicates are counted once, and aligns each candidate to a verbatim source
  quote with a locator. Use when a question is asked in one language but the
  relevant papers may be written in another (Portuguese, English, Spanish,
  French, German, Japanese, Chinese, Russian), or when language and version
  attribution must be auditable. Offline, standard library only.
version: 1.0.0
license: MIT
---

# Cross-lingual known-item literature search

## 1. Purpose and boundary

Answer a research question whose target papers may be written in a language other
than the question's, and make the answer checkable: which languages were queried,
which term was used in each language, which paper each hit is, which version of it
was seen, and where the supporting sentence sits in the source file.

In scope: cross-lingual query construction, term expansion and provenance,
language identification, version attribution, duplicate merging across language
versions, ranking with stated reasons, verbatim evidence alignment, honest
reporting of gaps.

Out of scope: translating whole papers, polishing prose, live web crawling, and
any claim about literature that is not present in the supplied corpus. When the
case supplies no corpus, this skill produces a query plan and says so; it does not
invent records.

Typical trigger: a question such as "which paper reports <concept> in
<language>" where hits may be Portuguese, English, Japanese or Chinese, or a case
that explicitly asks for language/version labels and de-duplication.

## 2. Runtime contract

- Input `/input` (read only): `case.json`, `task.md`, and any material under
  `artifacts/` or the case root. Work dir `/app/work`. Output `/app/output`.
- Entry point: `python3 scripts/main.py --input /input --out /app/output`.
- Write a legal partial `result.json` first, then finalise over it. Every
  exception is caught and recorded; the exit code is always 0.
- Standard library only, no network, no dependency on the current directory
  (resources are located from `__file__`).
- `case_id` is copied unchanged. Every field of `output_contract` exists in
  `result.json` with its original key, missing values as `null` or `[]`; unknown
  contract fields are kept, unknown case fields are not dropped.

## 3. Input discovery

1. Read `case.json`; if absent, the first `case*.json` found recursively.
2. Question text from `task_instruction`, `research_question`, `question`,
   `user_query`, `query`, `request`, `task`, `instruction`, `known_item`,
   `citation`, then a scope `topic`, then the head of `task.md`.
3. Every JSON/JSONL/CSV/TSV file under `/input` is decoded by content: any dict
   with a title-like key plus one bibliographic key becomes a record, whatever the
   file is called. Aliases for title/abstract/DOI/language/year/venue/authors are
   listed in `references/io_schema.md` §2.
4. PDF/PNG/DOCX/XLSX/ZIP are listed as unparsed material, never used as evidence.
5. Scope (`organizer_supplied_scope` or any `*scope*` object) supplies
   `topic`, `languages`, `max_k`/`top_k`.
6. Objects the case does not provide are named in `coverage.gaps` and
   `pending_human`; nothing is constructed to fill them.

## 4. Output contract

`result.json` (+ `candidates.csv`, `candidates.json`, `query_log.json`,
`term_table.json`, `verification.json`):

- identity: `case_id`, `status` (`ok|partial|insufficient_evidence|input_error`),
  `stage`, `skill_version`, `output_contract`
- question: `question.language`, `.confidence`, `.evidence`, `anchor_extraction`
- retrieval: `queries[]` (query id, language, raw query, expanded terms, methods,
  hits, status, timestamp), `query_plan[]`
- results: `candidates[]` (bibliographic fields, `language*`, `version*`,
  `n_views`, `view_records`, `source_file`, `retrieved_at`, `query_id`,
  `relevance_score`, `matched_terms`, `relevance_reason`, `evidence_snippet`,
  `evidence_locator`, `evidence_quote_match`, `flags`)
- process: `screening[]` (include + reason + criteria), `dedup.rules`,
  `coverage`, `term_table[]`, `term_expansion`, `gain_analysis`
- honesty: `sources[]`, `uncertainty[]`, `pending_human[]`, `errors[]`,
  `degradations[]`, `changes[]`, `runtime`

Field-by-field detail: `references/io_schema.md` §3.

## 5. Core pipeline

1. `concepts_of` — concept table: glossary rows hit by the question, weighted 1.5,
   plus literal content terms weighted 1.0. Every variant carries `method` and
   `weight`.
2. `langid` — script, then declared field, then stopword/diacritic/suffix scoring;
   below 2 points the language is `unknown`.
3. `expand` — rule-derived variants (EN↔PT/ES suffix rewriting) for languages the
   glossary lacks, weight 0.6, flagged `cognate_rule`.
4. `plan` — one AND-of-ORs query per target language, plus one citation-anchor
   query (DOI, year, author-like tokens). Languages with no variant are reported
   as `no_term_mapping`, never dropped silently.
5. `retrieve` — runs the plan over the corpus; per-query hits, status and
   timestamp go to the query log.
6. `build` (main) — score, sort, screen, label version, attach evidence; every
   excluded work keeps a reason.
7. `cluster` — union-find on DOI, declared work/translation links and
   near-identical titles; the best view represents the work, one candidate per
   work.
8. `checks` (main) — audit contradicts nothing: contract fields, quotes still in
   source, query ids link, one candidate per work.

Scoring, thresholds, dedup rules and version-label rules are spelled out in
`references/method.md` §3–§8.

## 6. Task quality rules (rubric → field → check)

| requirement | field | check |
|---|---|---|
| cross-lingual task actually run | `queries[]`, `term_table[]` | every declared language has a query with terms, `missing_concepts` empty or explained |
| hits are real | `doi`, `title`, `source_file`, `retrieved_at` | record exists in the corpus; no record without a source file |
| language and version correct | `language`, `language_evidence`, `version_label`, `version_basis` | declared field or ID evidence present; inferred labels carry confidence 0.45 |
| terms match the paper's own wording | `matched_terms.surface`, `.method`, `.alignment` | quote contains the surface form; `native` vs `loanword` stated |
| every declared language has a result | `coverage.languages_with_results`, `gaps` | gap listed per empty language |
| key non-English works covered | `coverage.non_source_language_works` | count plus per-work languages |
| versions deduplicated | `n_views`, `view_records`, `coverage.duplicates_merged`, `screening[duplicate_view_merged]` | one candidate per work; merged views counted |
| term table and queries auditable | `term_table`, `query_log` | each variant shows method + weight; each query shows hits + time |
| translation/version provenance | `version_basis`, `anchor_extraction.method`, `degradations` | no translation service is claimed when none ran |
| quality/efficiency gain | `gain_analysis.baseline` vs `.skill` | same corpus, same threshold, delta shown with caveat |
| stability and exception handling | `errors`, `degradations`, `pending_human` | status matches the issues raised |
| reusable documentation | this file, `method.md`, `io_schema.md` | files exist and match the code |

## 7. Evidence and locator rules

- `evidence_snippet` is copied verbatim from the record's title or abstract —
  never edited, never translated, truncated at 400 characters with the locator
  pointing at the full sentence.
- `evidence_locator` = `<source file>#<json pointer or row index>:<field>[s<sentence
  index>]+<char offset>`.
- `evidence_quote_match`: `exact` | `deaccented_normalized` | `failed`. `failed`
  sets `quote_unverified`, adds `pending_human`, and makes the run `partial`. A
  quote is never adjusted to pass the check.
- If a number or term is not in the source text, it is not reported. Ranking
  reasons quote the matched surface form, not a paraphrase.

## 8. Conflict and human confirmation

Escalated to `pending_human` with the action required: unverified quote, no
corpus supplied, candidate whose only identity is a title (no DOI), version
conflict between declared and inferred labels. Escalated to `uncertainty` with
impact and action: unknown language, heuristic term expansion, loanword matches,
empty result, missing DOI. When the case itself contradicts the corpus (for
example `task.md` describes work absent from the records), the run stays
`partial` and the conflict is written down; no side is invented.

## 9. Budget and breakpoints

Execution budget: 900 s, 64 model requests, 16384 tokens per reply. The script
itself runs in seconds and makes zero model requests and zero network calls. If a
run is interrupted, the last `result.json` on disk is already valid; partial
results identify their own limits via `stage`, `status` and `uncertainty`.

## 10. Degradation branches

| trigger | behaviour |
|---|---|
| no corpus | `insufficient_evidence` (or `input_error` when no case.json exists), queries marked `not_executed_no_backend`, `degradations` entry, no candidates |
| malformed JSON | parse error in `errors`, file skipped, run continues |
| JSONL fallback | accepted, noted in `sources.note` |
| PDF/DOCX/XLSX only | listed as unparsed, excluded from evidence |
| glossary missing | literal-term table only, `degradations` entry |
| term has no target-language form | `missing_concepts` + `no_term_mapping` query status |
| language below confidence 0.6 | `language_low_confidence` flag, `partial` |
| empty result | `insufficient_evidence` with threshold and record count |
| contract field absent from data | key present with `null`/`[]`, never renamed |

## 11. Self-check before reporting

1. `python3 scripts/main.py --help` exits 0.
2. Every `output_contract` key present (`verification.json.contract_missing == []`).
3. Every candidate has `query_id` in the query log, a `source_file` that exists,
   and a quote found in that file.
4. `coverage.duplicates_merged` equals the number of `duplicate_view_merged`
   screening rows.
5. `status` matches the recorded issues: no `ok` while `gaps` is non-empty.
6. No fabricated record: every candidate title appears in a source file.

## 12. Minimal invocation example (示例 — synthetic, not a case result)

```bash
python3 scripts/main.py --input ./input --out ./output
```

`./input/case.json` (illustrative): `case_id: "EXAMPLE-CASE-001"`,
`task_instruction: "Which paper reports piroptose in macrophages?"`,
`output_contract: {"query": "string", "candidates": "list", "notes": "string"}`.

Result shape: `status: partial`, one candidate with `language: pt`,
`n_views: 2`, `languages_in_work: ["en","pt"]`,
`version_label: translation_view`, `evidence_quote_match: exact`, and
`query: null`, `notes: null` because the contract fields have no computed value.
All ids and titles in this example are invented placeholders; see
`references/io_schema.md` §4 for the complete transcript.

## 13. File manifest and versions

| file | bytes | role |
|---|---|---|
| `SKILL.md` | this file | instructions, rubric map, contract |
| `scripts/main.py` | 19.2 KB | CLI, screening, outputs, audit |
| `scripts/engine.py` | 19.1 KB | discovery, language ID, concepts, scoring, dedup, evidence |
| `references/glossary.tsv` | 7.0 KB | 65-concept table, 8 languages, CC0-1.0 |
| `references/method.md` | 12.2 KB | method specification, thresholds, degradation matrix |
| `references/io_schema.md` | 9.0 KB | interface, field schema, test recipe |

Python 3.8+ (developed on 3.12.4), standard library only, no installation step.
Version 1.0.0.

## 14. Maintenance

- Concept table: append rows to `glossary.tsv`, keep `concept_id` stable.
- Thresholds and weights live in `engine.score` and `main.build`; change them
  together with `method.md` §6 and re-run the minimal case.
- New dedup rule: add to `cluster()` and to `method.md` §7 so the rule name in
  `coverage.dedup_rules_applied` stays explainable.
- After any change, compare `verification.json` and `candidates[].evidence_quote_match`
  on the same case; a drop means the change made evidence weaker.
