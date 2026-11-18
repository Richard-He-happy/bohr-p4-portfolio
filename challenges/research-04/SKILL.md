---
name: research-trend-lens
description: >-
  Turn a supplied literature corpus into four checkable research-frontier products:
  annual output trend with a change-point test, topic evolution by time window,
  per-window representative works under a stated selection rule, and research gaps
  backed by exclusion evidence. Every statement is bound to a source locator and a
  verbatim quote; unsupported statements are downgraded instead of asserted.
  Use for 研究前沿与趋势分析, 时间趋势, 主题演化, 代表作选取, 研究空白识别,
  literature trend analysis, research frontier mapping, bibliometric trend review,
  or "where does this field stand and where is it going" questions over a document set.
version: 1.0.0
---

# research-trend-lens

## 1. Use and boundaries

This skill answers four questions over **the supplied material only**: how output changes by year, which topics appear/persist/decline by window, which works represent each stage under a stated rule, and which problems are repeatedly raised but unresolved. It does **not** search external databases, does not report citation counts from any index, and does not claim field-wide completeness. It refuses to infer a "trend" from search hits alone.

Use it when the case supplies a research question plus material (PDF / RIS / CSV / JSON bibliography / TXT) and asks for a trend, evolution, representative-work, or gap judgement. Do not use it for single-paper reading (use a reading skill), for meta-analysis of effect sizes, or when the expected answer needs citation data you were not given.

## 2. Run contract

```bash
python3 -B scripts/main.py --input /input --out /app/output
```

- Package root = directory containing this file. `main.py` resolves `lens.py` from its own directory (`Path(__file__).resolve().parent`), so CWD never matters.
- Reads `/input` (fallbacks: `--input`, `$INPUT_DIR`, `./input`). Writes only under `--out` (default `/app/output`).
- Stdlib only, no network, no third-party imports. `pdftotext` is used **if present**; the builtin stream extractor is the fallback.
- **Exit code is always 0.** A valid partial `result.json` is written before any parsing; the final `result.json` overwrites it and `changes[]` records both writes.
- Runtime: ~1 s for 60 records; 4000-record cap via `--max-records`.

## 3. Input discovery (semantic, no fixed key names)

1. `case.json` / `task.json` / any `case*.json` in the input root; parse leniently (BOM, trailing comma, leading-object recovery, `case_id` regex salvage).
2. `case_id` and `output_contract` are copied verbatim. Fields are found by **search**, not by a fixed path: `topic` / `research_topic` / `research_question`, `time_window` / `time_range` / `period` / `时间`, and anything matching `inclusion|exclusion|screen|纳|排|筛` for rules.
3. Every other file is scanned recursively and classified by extension **and** magic bytes (`%PDF`, `PK`), never by filename labels. Supported: PDF, RIS, CSV/TSV, JSON/JSONL (bibliography records and `nodes`/`edges` reference graphs), TXT/MD. **Not parsed:** `.docx` / `.xlsx` / images / archives and any other `PK`-container file — each is listed in `uncertainty[material_unparsed]` together with `degradations`, never OCR-ed, guessed, or invented. Measured behaviour when such a file is the only material: `status="insufficient_evidence"`, `screening.records_included=0`, an empty trend table and `uncertainty[no_records]` — never a fabricated one.
4. Material not supplied is listed as a gap (`uncertainty[material_unparsed]`, `screening.excluded`), never filled in.

## 4. Output contract

`result.json` carries `case_id`, `status`, then the products: `research_question`, `screening`, `corpus`, `time_trend`, `topic_evolution`, `representative_works`, `research_gaps`, `conflicts`, `claims`, `evidence_matrix`, `sources`, `uncertainty`, plus `pending_human`, `errors`, `degradations`, `changes`, `tool_call_trace`, `runtime`, `outputs`, `verification`, `limitations`, `contract_backfill`.

**Backfill rule:** every key of the input `output_contract` appears at the top level under the same name. Dicts are filled recursively; lists become `[]`; unknown scalars stay `null`; nothing is renamed or dropped. `contract_backfill.fields[key]` records `core_field` / `semantic:<word>` / `type:<T>` / `null_kept`.

Product files: `research_report.md` (main human deliverable), `evidence_map.csv`, `trend_annual.csv`, `topic_evolution.csv`, `representative_works.csv`, `screening_log.csv`, `run_ledger.json`.

## 5. Workflow

1. Bootstrap: write partial `result.json` with all contract keys (null/[]).
2. Extract: per file → records (title, year, doi, venue, abstract, body text, locator, quality). PDF → page list; bibliography → one record per entry.
3. Normalise: year from metadata, else title/abstract/body (source recorded per record); topic labels from `references/lexicon.md`; dedupe by DOI → exact title → title Jaccard ≥ 0.92 within ±1 year.
4. Screen: year window from case, no-title/no-text, exclusion keywords; each exclusion keeps its reason.
5. Analyse: annual counts → windows (width 1/2/3-5 by span) → change point; topic series → status; per-window representative ranking; gap sentences by cue group; opposite-direction pairs.
6. Write claims + evidence matrix, CSVs, report, ledger, final `result.json`.

## 6. Quality rules (rubric → field / check / product)

| Requirement | Field / check / product |
|-|-|
| four product types, not one list | `time_trend`, `topic_evolution`, `representative_works`, `research_gaps` all non-empty when the corpus allows |
| trend supported by own statistics | `trend_annual.csv` + `time_trend.change_points` (1.5× threshold, else `candidate_only`) |
| evolution explains when/why | per-window series + `status` + `basis` + `merge_split_candidates` |
| representatives per stage, rule stated | `representative_works.rule` + `long_tail` flag; total citations alone never used |
| gap ≠ search miss | `research_gaps[].basis` names screened/included counts; `status` = `insufficient` when only one source |
| every conclusion traceable | `claims[].evidence[]` ↔ `evidence_map.csv` rows, 1:1, with locator + verbatim quote |
| honesty | `status` ∈ ok/partial/insufficient_evidence/input_error; unverified quotes downgrade the claim |

## 7. Evidence and locator rules

- Locator format: `file.pdf#p<page>` (page-accurate when pages are known), `file.ris#rec<n>`, `file.csv#rec<n>`, `file.txt#p1`.
- Quote: NFKC-normalised, whitespace-collapsed, **case-sensitive** substring of the record text, ≥ 10 characters. A quote that cannot be found is marked `quote_verified=false`, the claim drops to `insufficient`, and the item is listed in `pending_human`.
- `quality < 0.55` (typical for scanned or CID-encoded PDFs) → body quotes are not used; the title serves as the quote and the degradation is recorded.
- Strength labels: `directly_supported` (verified quote, or a statistic whose full table ships), `inferred` (causal wording, `candidate_only` change point, rule-based pick), `insufficient` (kept in `uncertainty`, never asserted).

## 8. Conflicts and human confirmation

Opposite-direction sentences on one topic from ≥ 2 records are both kept in `conflicts`; no winner is declared and no meta-analysis is performed. `pending_human` always contains: confirm the corpus is the intended evidence base, and spot-check three quotes per claim. Records without a year, unmapped topics, and unparsed material are surfaced as `uncertainty` entries instead of being silently dropped.

## 9. Budget and breakpoints

Model requests 0 (deterministic pipeline; the agent may call `WebSearch`/`PaperSearch` outside the skill if the case asks for retrieval, and must then record it). Wall clock < 5 s for 1000 records. If the deadline approaches, the already-written partial `result.json` remains valid; re-running the same command is idempotent and only appends to `changes`.

## 10. Failure branches (all exit 0)

| Trigger | Handling |
|-|-|
| missing/unreadable case | `status=input_error`, `errors[NO_INPUT]`, report still written |
| malformed JSON | comma repair → leading-object recovery → `errors[JSON_FAIL]`, other files continue |
| unsupported material / parse exception / empty text | listed in `screening.excluded` + `degradations`, run continues |
| no year | excluded from trend, `uncertainty[year_missing]`, never imputed |
| everything filtered out | `degradations[screening_too_strict]`, fall back to all parsed records |
| < 5 years or < 8 records | no turning point claimed (`change_points.note`) |
| > 4000 records | `degradations[record_cap]`, truncation logged |
| no reference graph | in-degree term = 0, stated in `representative_works.ind_source` |
| lexicon missing | `degradations[lexicon_missing]`, `unmapped_count` = all dated records |
| fatal exception | minimal `result.json` with `errors[FATAL]` |

## 11. Self-check

```bash
python3 -B scripts/main.py --input /input --out /app/output
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['status'],r['verification'])"
```

Pass when: `contract_backfill.filled == total`; `verification.quotes == len(evidence_map.csv)`; `sum(trend_annual.count) == verification.dated_records`; every `research_gaps[]` has ≥ 1 quote; `status == ok` only if ≥ 1 claim is `directly_supported`.

## 12. Minimal call example (example only, not a case result)

Input `/input/case.json`:

```json
{"case_id": "DEMO-1", "research_topic": "battery ageing prediction",
 "time_window": [2015, 2024],
 "output_contract": {"trend_analysis": null, "research_gaps": null, "report": null}}
```

plus `/input/bib.csv` with columns `title,year,doi,abstract` (illustrative rows with placeholder values).

Run: `python3 -B scripts/main.py --input /input --out /app/output`.

Illustrative output shape (**示意，非正式案例结果；数值为占位**)：

```
status=ok records=<N> claims=<K> gaps=<G> excluded=0 out=/app/output
result.json       -> time_trend.span=[<y0>,<y1>], change_points.candidates[0].strength="candidate_only"
evidence_map.csv  -> C01,R001,<file#p1>,"<verbatim quote>",True
research_report.md-> 10 sections rendered from the template
```

## 13. Files and version

| file | bytes | role |
|-|-|-|
| `SKILL.md` | see listing | this contract |
| `scripts/main.py` | ≤20 KB | CLI, contract backfill, products |
| `scripts/lens.py` | ≤20 KB | extraction + statistics + report rendering |
| `references/lexicon.md` | editable | topic / gap / method / exclusion term lists |
| `references/method.md` | — | schema, strength rules, failure table, rubric map |
| `references/report_template.md` | — | report skeleton with `{{SLOT}}` markers |

Version 1.0.0. Python ≥ 3.7, stdlib only. Optional: poppler `pdftotext` for accurate page locators.

## 14. Maintenance

Adapt a domain by editing `references/lexicon.md` only (keep ids stable, add parents). Re-run and read `topic_evolution.unmapped_count` before trusting topic shares. Bump `version` in this file and in `lens.py` when a rule changes; note the change in the report. Sample values anywhere in the docs are placeholders — never paste them as case results.
