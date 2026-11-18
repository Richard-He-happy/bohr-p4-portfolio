---
name: literature-delta-tracker
description: >-
  Incremental literature discovery and tracking. Resolves a topic subscription and fixed
  time windows, replays organizer-supplied source snapshots (Crossref / EuropePMC /
  publisher JSON, records.jsonl, CSV, queries.jsonl), rebuilds records, normalizes
  identity keys, deduplicates and merges preprint -> published -> version -> correction
  chains, diffs each window against the previous snapshot, and emits only genuinely new
  or changed works with merged and suppressed alerts. Use it when a task asks for
  "latest / new / weekly literature tracking", a topic subscription, a new-item list
  between two dates, or a delta against an earlier snapshot. It writes result.json with
  every output_contract field echoed, plus candidates.csv, query_log.json, alerts.json,
  alerts.md, snapshot.json and deltas/window_NN.json.
version: 1.0.0
license: MIT
---

# literature-delta-tracker

## 1. Purpose and boundaries

The kernel is a **delta**: given a subscription, a fixed window `[start, end)` and a
previous snapshot, return the works that are genuinely new or changed in this window,
with the evidence needed to replay that judgement. A one-shot topic search is not a
tracking result; the tracked object here is the per-window change list plus the state
that makes the next window computable.

In scope: subscription configuration, window definition, incremental retrieval over
organizer-provided source snapshots, identity normalization, deduplication, version and
retraction handling, snapshot diffing, alert merge/suppression, replay records.

Out of scope: full-text reading, writing reviews, live crawling the skill itself (no
network), and treating any alert as a scientific conclusion. Alerts are bibliographic
delta signals only.

## 2. When to use / not use

Use when the input contains bibliographic records plus (optionally) a previous snapshot,
queries log, reference graph, or a window/as-of definition, and the deliverable is a
new-item list or a re-checkable candidate set.

Do not use when there is no record-like material at all: the skill then reports
`input_error`/`insufficient_evidence` with `missing[]` instead of inventing papers.

## 3. Runtime contract

- Input `/input` (read-only): `case.json`, `task.md`, `artifacts/**`, materials.
- Work `/app/work` (state): `state.json` (advances between runs; delete or run with a
  fresh work dir to force a first-run baseline).
- Output `/app/output`: `result.json` + sidecars (below).
- `result.json` always echoes every `output_contract` field verbatim in name, keeps
  `case_id`, and adds `status`, `sources`, `uncertainty`, `pending_human`, `errors`,
  `degradations`, `changes`, `missing`, `runtime`.
- A **partial `result.json` is written before heavy work**; the final file overwrites it.
- Exit code is always 0, including on empty input, bad JSON, or internal failure.
- Deterministic and offline: no network, no model calls (`runtime.model_requests = 0`),
  stdlib only, paths resolved from arguments, never from CWD.

## 4. Quick start

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/core.py --input /input --output /app/output   # re-validate output
```

Useful flags: `--now 2024-03-01` (freeze the clock for reproducible runs),
`--window-start 2024-02-01 --window-end 2024-03-01` (override the window),
`--max-k 20` (cap candidates). Normally run once per window; each run advances
`output/snapshot.json` and `work/state.json`.

## 5. Input discovery (semantic, no fixed key names)

1. Read `case.json` (fallback: any `case*.json`). Keep `case_id` and
   `output_contract` untouched. Also read `task_instruction`, `organizer_supplied_scope`,
   `scope`, `constraints` (topic, include/exclude terms, lang, max_k) if present.
2. Recursively scan `/input/**` and parse by extension + content, not by label:
   `.json/.jsonl/.ndjson` (Crossref `message.items`, EuropePMC `resultList.result`,
   record lists, snapshots, graphs, queries), `.csv/.tsv` (record tables), `.md/.txt/
   .yaml/.xml` (briefs, configs, query logs).
3. Any dict carrying a title plus (DOI | arXiv | PMID | PMCID | any date) is a record;
   container/author/affiliation sub-objects are skipped. Metadata is read from aliased
   keys (`DOI/doi`, `title/titles/article_title`, `author/authorList`, `created/
   deposited/published/issued/firstIndexDate/firstPublicationDate`, `container-title/
   journalTitle`), including camelCase and kebab-case spellings.
4. Files whose names match `snapshot|previous|baseline|state` are **history**, not
   candidates: their identity keys seed the previous snapshot and they are excluded from
   the candidate list.
5. Anything the case implies but the input lacks (gold list, seed PDFs, patents) is
   listed in `missing[]`; it is never synthesized.

## 6. Core flow

1. **Records** — rebuild observations with `src` file + JSON pointer locator,
   `retrieved_at` (record field, else file mtime), index date and publication date.
2. **Identity + dedup** — keys: normalized DOI, arXiv id (version stripped), PMID,
   PMCID, normalized title; union-find merge on shared keys.
3. **Version merge** — per work, rank items (preprint 1 < published 3+ < notice 6) and
   keep the full `version_chain` (doi, arxiv, type, index_date, rank, source).
4. **Subscription + scoring** — topic terms from scope/instruction/material; score =
   `0.60*topic_term_coverage + 0.25*seed_similarity + 0.15*recency`; include/exclude
   filters, then `top-k`.
5. **Windows** — windows from CLI, then the case (`window/period/range/as_of`), then
   artifacts, else derived from the previous snapshot end or the latest index date;
   membership is `[start, end)` on index/import date in UTC.
6. **Delta** — per window, per work: `new`, `version_update`, `correction_or_retraction`,
   `recovered_late` (delayed indexing before the window start), `duplicate_noise`
   (suppressed), `out_of_window`. State advances after each window.
7. **Alerts** — one alert per merged work, dedup by alert id, cap per window, suppress
   already-alerted/low-confidence items; delivery record written per alert.

## 7. Outputs

`result.json` keys: `case_id`, `status`, `skill`, `subscriptions`, `windows`,
`new_items`, `candidates`, `queries`, `alerts`, `coverage`, `snapshot`, `sources`,
`uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `missing`,
`runtime`, `checks`, plus all contract fields and `_output_contract` (the echoed
contract itself).

Sidecars: `candidates.csv` (one row per candidate, locator columns included),
`query_log.json`, `alerts.json`, `alerts.md` (human digest), `snapshot.json`
(item keys, work ids, alert ids, window end), `deltas/window_NN.json`.

Field-level detail: `references/02-output-schema.md`.

## 8. Rules that decide correctness

Window, dedup, version, retraction and alert rules (with the exact normalization steps
and tie-break rules) are in `references/01-methods-rules.md`. Read it before changing
any threshold; the defaults there are the ones the self-checks expect.

## 9. Evidence and locators

Every candidate carries `source_db`, `retrieved_at`, `query_id` and
`evidence_locator{source_file, pointer, index_date_field}`; `evidence_snippet` is a verbatim
prefix of the record abstract/title. `query_id` resolves to a row in `queries[]` or is
explicitly `q_unmapped` and flagged. A DOI that is not found verbatim in the input text
fails `checks` (`doi_traceable_to_input`), which is the anti-fabrication guard.

## 10. Exceptions and degradations

| Situation | Handling |
|---|---|
| `case.json` missing/unparsable | scan other JSON; `errors[]`, `status=input_error` if nothing usable |
| no record objects | `status=insufficient_evidence`, `missing[]`, empty candidates, exit 0 |
| one artifact unparsable | `degradations[]` entry; other files still processed |
| empty window | empty delta lists, counts zeroed, digest says "no new items" |
| missing index date | publication date used as proxy; flagged `index_date_proxy` |
| DOI/title conflicts (same title, different DOI) | kept as one work with a multi-node `version_chain`, both DOIs preserved |
| retraction/correction/erratum | `correction_or_retraction`, still alerted once |
| delayed indexing | `recovered_late`, alerted as backfill |
| no previous snapshot | first-run baseline; every in-window item is new; `uncertainty[]` notes it |
| no gold list | `coverage.skill_metrics.recall_at_k=null` with a stated reason, never a guessed number |

## 11. Status semantics

`ok` — candidates produced, no errors, contract complete.
`partial` — produced but limited (few candidates, error entries, missing inputs).
`insufficient_evidence` — no usable records; limitations stated.
`input_error` — case input unusable; nothing invented.

## 12. Budget and interruption

Deterministic replay only: no request budget is consumed. Typical runtime on organizer
snapshots is a few seconds. Because the partial `result.json` is written first and every
section is wrapped, an interruption leaves a valid file with `status=partial` and the
completed sections.

## 13. Self-check before returning

1. `result.json` parses; `case_id` equals the input; `status` in the enum.
2. Every `output_contract` key exists.
3. Candidates have title/source_db/retrieved_at/query_id/reason/locator; DOI syntax OK
   and each DOI occurs verbatim in the input.
4. `new_items` reference existing candidates; work ids unique.
5. Alerts have delivery records and resolvable work ids.
6. `candidates.csv`, `query_log.json`, `alerts.json`, `alerts.md`, `snapshot.json` exist.
7. Re-running on the same window yields zero new items (idempotent).

`checks` in `result.json` runs items 1-6 automatically; `core.py --output` re-runs them.

## 14. Minimal example (illustrative, NOT a formal case result)

Input: `case.json` with `case_id="demo"`, `windows=[{2024-01-01,2024-02-01}]`, and one
Crossref response containing a 2024-01-10 bioRxiv preprint plus one 2024-02-20 journal
version of the same title.

```bash
python3 scripts/main.py --input ./in --output ./out --work ./work --now 2024-03-01
```

Illustrative output shape (values below are a schematic example, not measured results):

```json
{"windows":[{"index":0,"counts":{"new":1,"updated":0,"alerts":1}}],
 "candidates":[{"candidate_id":"c001","doi":"10.1101/2024.01.09.555001","delta_class":"new",
                "version_chain":[{"doi":"10.1101/...","version_rank":1}]}],
 "alerts":[{"alert_id":"al_0_…","class":"new","delivery":{"status":"written"}}]}
```

## 15. Files, version and maintenance

- `SKILL.md` (this file) — contract, flow, exceptions, self-check.
- `scripts/main.py` (1.0.0) — pipeline entry point (`--help`).
- `scripts/core.py` (1.0.0) — parsing/normalization/dedup/scoring/validation library;
  also the standalone validator (`--input/--output`).
- `references/01-methods-rules.md` — window, dedup, version, alert rules.
- `references/02-output-schema.md` — result.json and sidecar field dictionary.
- `references/03-checks-and-example.md` — rubric map, exception table, replay recipe.

Thresholds live in two places only: `ALERT_CAP`/scoring weights in `main.py`, identity
constants in `core.py`. Change them together with the references, bump `version`, and
re-run both listed self-checks.
