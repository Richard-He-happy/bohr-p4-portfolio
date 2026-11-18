# Output schema, exception taxonomy and a labelled example

## 1. Files written to `--output`

| file | role | contract |
|---|---|---|
| `result.json` | single machine result: every `output_contract` field, `case_id`, status, sources, coverage, uncertainty, `errors`/`degradations`/`pending_human`/`changes`/`runtime`, `verification` | always written; a partial version exists before analysis starts and is finalised unconditionally |
| `review.md` | human report: summary, question, search protocol, screening, appraisal, per-theme claims with verbatim quotes + locators, conflicts, gaps, uncertainty, reproducibility | generated from the run, no prepared text |
| `evidence_map.csv` | one row per claim-evidence pair | `claim_id, theme_id, claim_kind, record_id, appraisal_grade, direction, source_file, extract_file, char_start, char_end, quote, locator, doi, title` |
| `screening_log.csv` | one row per record per round | `record_id, round, clause_id, verdict, verdict_lenient, reason_code, reason_text, evidence_quote, criteria_version, screener, ts, title, year` |
| `appraisal.csv` | one row per included record | `record_id, D1..D6, score, grade, abstract_only` |

`extract_file` + `char_start`/`char_end` point into `work/extracted/<record>.txt`,
so any quote can be re-sliced and compared byte for byte without re-parsing the
original PDF/DOCX.

## 2. `result.json` top-level keys

`skill`, `case_id`, `status`, `stage`, `language`, `output_contract`,
`contract_check`, `research_question`, `search`, `criteria`, `screening`,
`appraisal`, `synthesis`, `sources`, `coverage`, `summary`, `uncertainty`,
`pending_human`, `errors`, `degradations`, `changes`, `runtime`, `artifacts`,
`materials`, `case_path`, `input` (stage 1), `verification` (stage 2).

`status` values: `ok` (claims produced), `partial` (chain ran, some product
missing — see `pending_human`), `insufficient_evidence` (no record parsed, or no
quotable result sentence), `input_error` (no case file / unreadable contract).

`output_contract` is echoed key-for-key. Values are filled from the run by
normalised key matching (aliases such as `review`/`report`/`path` → `review.md`,
`included_studies` → included record ids). Unmapped keys keep the contract's own
value; placeholder strings (`string`, `path`, `[]`, `<...>`, `tbd`) become `null`.
`contract_check.fields_null` counts the leaves still empty — quoted in the reply.

## 3. Locator grammar

`<file>#chars=<start>-<end>` — half-open character span in the extracted text,
`0 <= start < end <= len(text)`. `sources[].locator` uses the record's
title+abstract span; an evidence locator always satisfies
`extract_text[start:end] == quote`. Page numbers are **not** produced from the
stdlib PDF fallback and are therefore never written; `degradations` records the
limited layout fidelity instead.

## 4. Exception taxonomy (what the pipeline does)

| situation | handling | where it shows |
|---|---|---|
| search/corpus empty | no records, `insufficient_evidence`, `pending_human.supply_literature_records` | status, pending_human |
| case.json missing/broken | `errors[].stage=discover`, contract empty, exit 0, partial result written first | errors |
| PDF unreadable | degradation `failed:<Type>`, other materials still processed | degradations |
| PDF text degraded | extractor recorded (`stdlib_flate` vs `pdftotext`) | materials[].extractor |
| full text unavailable | soft exclusion `EC7`, abstract-only evidence, grade capped | screening_log, appraisal |
| ambiguous term / synonym drift | per-block expansion list + core-term threshold; uncertain records queued | search.blocks, manual_queue |
| clause conflict | priority order; equal-rank conflict → `uncertain` + human queue | criteria.priority_order |
| contradictory evidence | conflict entry with both quotes, claim capped at `insufficient_evidence` | synthesis.conflicts |
| permission/IO failure | caught per file or per stage; `status=partial` | errors, degradations |
| duplicate record | merged on DOI or normalised title, kept id logged | degradations |

## 5. Labelled example (EXAMPLE — not a formal case result)

Illustrative only; the strings are invented for interface demonstration and are
**not** outputs of any platform case.

```json
{
  "case_id": "example-000",
  "status": "partial",
  "output_contract": {"review": "review.md", "included_studies": ["E01"], "quality": "appraisal", "gaps": ["G1"]},
  "contract_check": {"fields_requested": 4, "fields_null": 0, "unmapped": []},
  "research_question": {"raw": "example question", "derivation": {"method": "heuristic_from_wording", "confidence": "low"}},
  "synthesis": {"claims": [{"claim_id": "C1", "kind": "inferred",
    "evidence": [{"record_id": "E01", "locator": "example.json#chars=0-40", "quote": "example quote"}]}]},
  "verification": {"quotes_checked": 1, "quotes_verified": 1, "result": "pass"},
  "pending_human": [{"action": "confirm_structured_question", "why": "PICO derived heuristically from wording"}]
}
```

Field-level meaning of the example: one claim, one evidence item, one quote
re-checked, and one open human action — the smallest honest `partial` result.
