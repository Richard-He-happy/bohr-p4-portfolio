# method.md — schema, strength rules, failure branches, self-check

## 1. Package layout (v1.0.0)

| path | role | notes |
|-|-|-|
| `SKILL.md` | contract, workflow, rubric map | entry point |
| `scripts/main.py` | CLI: input discovery → engine → products | stdlib only, always exit 0 |
| `scripts/lens.py` | engine: extraction, normalisation, statistics, report rendering | imported by `main.py` via `__file__`, CWD-independent |
| `references/lexicon.md` | editable topic / gap / method / exclusion term lists | the only file you normally edit to adapt a domain |
| `references/report_template.md` | report skeleton with `{{SLOT}}` markers | rendered by `lens.render` |
| `references/method.md` | this file | schema + rules + self-check |

No network, no third-party packages, no absolute paths. `pdftotext` (poppler) is used when present and is **not** required.

## 2. result.json fields

| field | type | meaning |
|-|-|-|
| `case_id` | any | copied verbatim from the input case; never regenerated |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` | honest run state |
| `research_question` | object | topic from case + fixed 5-way decomposition with weights |
| `screening` | object | parsed / included / excluded counts, exclusion reasons, duplicates, case rules |
| `corpus` | object | file count, formats, year-source histogram, records without a year |
| `time_trend` | object | `span`, `annual[]`, `window_width`, `windows[]`, `change_points`, `caveats[]` |
| `topic_evolution` | object | per-topic `series` by window, `status`, `basis`, `merge_split_candidates`, `unmapped_count`, `rule` |
| `representative_works` | object | `by_window{label:[{record,title,year,doi,score,in_degree,long_tail,rationale,locator}]}`, `rule`, `ind_source` |
| `research_gaps` | array | `gap_id`, `type`, `topic`, `mention_count`, `source_count`, `sources[]`, `quotes[]`, `basis`, `status` |
| `conflicts` | array | `topic`, `positive[]`, `negative[]`, `basis` |
| `claims` | array | `claim_id`, `kind`, `statement`, `evidence_strength`, `evidence_kind`, `evidence[]`, `stat_ref` |
| `evidence_matrix` | array | one row per claim↔source pair: `claim_id`, `strength`, `source_id`, `doi`, `locator`, `quote`, `quote_verified` |
| `sources` | array | id, title, year, doi, file, locator, format, quality per included record |
| `uncertainty` | array | `type`, `detail`, `basis` |
| `pending_human` | array | actions a human must still take |
| `errors` / `degradations` / `changes` | array | exceptions, graceful degradations, and the partial→final write record |
| `tool_call_trace` | array | ordered steps with parameters and timestamps |
| `runtime`, `outputs`, `verification` | object | timing, product hashes, recomputation counters |
| `contract_backfill` | object | `total`, `filled`, per-key `fields`, and the rule used |

**Contract rule.** Every key of the input `output_contract` is written to the top level of `result.json` under the same name. Missing values are `null` or `[]`, never dropped, never renamed. `contract_backfill.fields[key]` records whether the value came from a core field (`core_field`) or from a semantic match (`semantic:*`), followed by type defaults (`type:list`, `type:int`, `null_kept`, ...).

## 3. Evidence strength

| label | when it is allowed |
|-|-|
| `directly_supported` | a verbatim quote that passes the substring test against the source text, or a statistic computed over the full included record table whose rows are shipped (`stat_ref` points at the CSV) |
| `inferred` | interpretation built on verified evidence: causal wording, a `candidate_only` change point, a rule-based representative pick |
| `insufficient` | the claim needs evidence the corpus does not contain; it is kept in `uncertainty` / `pending_human`, never phrased as fact |

`evidence_kind` records how the support was produced: `quote`, `computed`, or `quote` with `quote_verified=false` (downgraded automatically, and the affected claim is marked `insufficient`).

Quote rule: NFKC-normalised, whitespace-collapsed, case-sensitive substring of the record text, ≥ 10 characters. Truncation keeps a prefix, so a shortened quote still passes only if it really occurs. When body text is unusable (`quality < 0.55`, typical for scanned or CID-encoded PDFs) the title is used as the quote and this is recorded as a degradation.

## 4. Failure branches (all exit 0)

| trigger | detection | handling |
|-|-|-|
| empty input / no `case.json` | directory missing or unreadable | `status=input_error`-grade partial, `errors[NO_INPUT]`, report still written, `contract_backfill.total=0` |
| malformed JSON | `json.loads` fails | trailing-comma repair, then leading-object recovery, then `errors[JSON_FAIL]` and continue with other files |
| unparsable material | extension/signature unsupported, parse exception, < 80 chars extracted | record enters `screening.excluded` with the real reason and `degradations[low_text_quality]`, whole run continues |
| no year | metadata and text both fail | excluded from every trend statement, counted in `uncertainty[year_missing]`; never imputed |
| empty screening | every record filtered | `degradations[screening_too_strict]`, fallback to all parsed records so the trend table is not silently empty |
| corpus too small | < 5 years or < 8 records | `change_points.note` says no turning point is claimed |
| record explosion | > `--max-records` (default 4000) | truncation recorded in `degradations[record_cap]` |
| missing reference graph | no edges found | in-degree term becomes 0, `representative_works.ind_source` says so |
| lexicon missing | `references/lexicon.md` absent | `degradations[lexicon_missing]`; trend and gaps still produced, `unmapped_count` = all dated records |
| conflicting evidence | opposite-direction sentences on one topic from ≥ 2 records | both sides kept in `conflicts`, no winner declared |
| fatal exception | top-level `except` | minimal `result.json` with `status=input_error`, `errors[FATAL]`, exit 0 |

## 5. Rubric → field map

| rubric point | field / check / product |
|-|-|
| task completion (4 product types) | `time_trend`, `topic_evolution`, `representative_works`, `research_gaps` all non-empty when the corpus allows |
| correctness of year / topic / representative / conclusion | `corpus.year_sources`, `screening.excluded`, `claims[].evidence_strength`, quote verification counters |
| completeness (span, hierarchy, per-stage picks, gap types) | `time_trend.windows`, `topic_evolution.topics[].status`, `representative_works.by_window`, `research_gaps[].type` |
| verifiability | `evidence_matrix`, `trend_annual.csv`, `topic_evolution.csv`, `screening_log.csv`, `run_ledger.json`, `verification` |
| gain vs base agent | four products + fixed thresholds + `claims` bound 1:1 to `evidence_matrix` rows, produced in one deterministic run |
| efficiency gain | one command produces 7 artifacts; no manual year filling, no re-counting |
| verifiability of gain | `verification` block + product hashes in `outputs` |
| new capability | `time_trend.change_points`, `topic_evolution` statuses, rule-based representatives incl. long-tail flag, gap exclusion basis |
| methodological improvement | explicit window width rule, year-source trace, lexicon-based merge candidates, gap status thresholds |
| innovation evidence | `references/method.md` documents the rule boundaries; report states what is *not* claimed |
| reliability | 11 failure branches above, idempotent reruns, exit 0 |
| ecosystem | this package: editable lexicon, template, schema, self-check, and the runbook in `SKILL.md` |

## 6. Self-check after a run

```bash
python3 -B scripts/main.py --input /input --out /app/output
python3 - <<'EOF'
import json;r=json.load(open('/app/output/result.json'))
print(r['status'], r['verification'])
print(sorted(set(r['contract_backfill']['fields'].values())))
EOF
```

Checklist: `status` is not `ok` unless at least one claim is `directly_supported`; `evidence_map.csv` rows equal `verification.quotes`; `sum(count in trend_annual.csv) == verification.dated_records`; every `research_gaps[]` entry has ≥ 1 quote and a `basis` that names the screened count; `contract_backfill.filled == contract_backfill.total`.

## 7. Version and maintenance

- v1.0.0 — first release. Changes that break comparability: editing topic ids, changing window width rule, changing representative weights. Record such edits in the report and bump `version` in both `SKILL.md` and `lens.py`.
- Adding a domain: append `[topics]` lines (keep ids lowercase, add a parent id) and optionally extend `[gap]`. Re-run and compare `topic_evolution.unmapped_count` before trusting shares.
- Sample values anywhere in the docs are placeholders, never case results.
