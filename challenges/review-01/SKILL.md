---
name: paper-quality-review
description: Source-bound quality review of a manuscript or research material. Extracts the real file (PDF/DOCX/XLSX/CSV/JSON/MD/text), segments it into addressable sentences, runs six review facets (fact & numeric consistency, citation support, method design, statistics reporting, argument chain, academic norms), verifies every quote verbatim against the extracted text, grades severity, and emits result.json + review_report.md + issues.csv. Use when asked to review, audit, referee or pre-submission check a paper, draft, thesis chapter or report and to deliver an actionable, locatable issue list.
version: 1.0.0
---

# Paper Quality Review

Delivers a **fixed-structure, assignable issue list** instead of a prose review: every item has a
check item, severity, locator (source / page / paragraph / sentence / character range), verbatim
quote, rationale, suggested fix, and an evidence trail. Quotes that cannot be found verbatim in the
extracted text are never reported as findings — they are demoted to `pending_human`.

## 1. When to use / when not

Use for: pre-submission self-check, peer-review preparation, thesis/project deliverable review,
re-checking a revised version, and building a to-do list for authors.

Do not use for: language polishing, translation, plagiarism/similarity detection, journal
typesetting, or deciding acceptance. This skill finds *documented defects and gaps*; it does not
judge novelty or scientific importance.

## 2. Runtime contract

| Item | Value |
|---|---|
| Entry | `scripts/review.py` (Python ≥3.8, standard library only, no network) |
| Input | `/input/case.json`, `/input/task.md`, materials anywhere under `/input/` |
| Output | `/app/output/result.json`, `review_report.md`, `issues.csv`, `corpus.json` |
| Exit code | always `0`; failures are reported inside `result.json` |
| Partial first | `result.json` is written before any parsing and finalised unconditionally |
| Budget | designed for ≤900 s / 64 model calls; rules pass takes seconds |

```bash
python3 scripts/review.py --input /input --output /app/output          # full run
python3 scripts/review.py --input /input --output /app/output --merge my_findings.json
python3 scripts/checks.py --result /app/output/result.json --corpus /app/output/corpus.json
```

## 3. Input discovery (semantic, not key-based)

1. `case.json` (or any `*.json` containing `output_contract` / `case_id`) is parsed; malformed JSON is
   recorded in `errors` and the run continues with the remaining materials.
2. `case_id` and **every** `output_contract` key are echoed verbatim; unknown keys are preserved, empty
   values are filled by field semantics (see §5), never renamed.
3. Materials are found by walking the input tree and classified by **suffix**, not by label: pdf,
   docx/doc, xlsx/xls, csv/tsv, json, md, txt, tex, html, images. PDF text comes from `pdftotext`,
   else `mutool`, else the built-in stream scanner; OOXML is read with `zipfile` + XML strip.
4. Declared-but-absent material is listed in `input.material_gaps`; unreadable material produces a
   degradation **and** a `pending_human` entry instead of silent skipping.
5. Images are not OCR'd: they are listed as unread material and the dependent checks are marked
   `not_checked` rather than guessed.

## 4. Output contract

`result.json` always contains:

| Block | Content |
|---|---|
| `case_id`, `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `issues[]` | id, facet, facet_label, check_item, severity, basis_type, title, quote, locator, rationale, suggestion, confidence, review_status, verifiable_by, evidence, quote_verified, origin |
| `review` | `summary`, `verdict`, `facet_coverage` (per check item: checked / not_checked + reason + findings), `issues_by_severity` |
| `sources[]` | source_id, name, path, kind, engine, chars, pages, sha256 (manuscript version fingerprint), note |
| `metrics` | issue counts by severity/facet/basis, quote totals, verified, rejected, chars, rules_fired |
| `pending_human[]` | reason, detail, action (unverified quote, unreadable material, rejected agent finding) |
| `unchecked[]` | check items not executed and why (never silently "passed") |
| `uncertainty[]`, `errors[]`, `degradations[]`, `changes[]`, `runtime{}` | honest run record |
| `contract_fill` | which contract keys were filled / defaulted / preserved |

`severity`: `major` (blocks acceptance / changes the conclusion), `minor` (must be fixed, does not
change the conclusion), `info` (suggestion). `basis_type`: `error` (verifiable defect),
`insufficient_evidence` (needs author material), `suggestion`. `origin`: `rule` (deterministic) or
`agent` (semantic reading).

## 5. Workflow

1. **Extract** → `corpus.json` (paragraphs, sentences, sections) is written; every later quote is cut
   from this text, so evidence offsets are always reproducible.
2. **Rule pass** → `scripts/checks.py` applies `references/rules.json`:
   sentence rules (p-values, ±, correlation, causal wording, placeholders …) and document specs
   (missing control / n / ethics / data availability / limitations / sections, reference-numbering
   conflicts, exhibit numbers, sample-size conflicts, abstract-vs-body numbers).
3. **Semantic pass (agent)** → read `corpus.json` (or the PDF), write `agent_findings.json` (schema in
   `references/checklist.md`), rerun the script; findings are quote-verified, deduplicated, and merged
   with `origin=agent`. Findings whose quote is not verbatim are rejected into `pending_human`.
4. **Verify** → every quote is matched against the whitespace/punctuation-insensitive full text.
5. **Render** → `issues.csv` + `review_report.md` (template: `references/report_template.md`).

## 6. Six facets and their check items

| Facet | Typical checks |
|---|---|
| `fact_check` | sample-size conflicts across abstract/methods/results, figure/table numbers cited but absent, abstract values missing from body, placeholders, percentages >100 |
| `citation_support` | citation number beyond the reference list, citations without any reference list, uncited entries, duplicate/malformed entries, entries without year, external claims without a citation, future-dated citations |
| `method_design` | missing control group, missing n, unstated randomisation/blinding, no replicates for in-vitro work, no statistical-analysis statement, missing inclusion/exclusion criteria, no sample-size justification |
| `statistics_report` | `p = 0.000`, p without test name, significance claims without statistics, `±` without SD/SEM, correlation without effect size, means without dispersion, p-values without intervals |
| `argument_chain` | causal wording on observational data, “proves/demonstrates” without statistics, no limitations, no comparison with prior literature |
| `academic_norms` | missing methods/results/discussion/conclusion chapters, ethics/consent/data-availability/COI/funding/contribution statements, abstract length, keyword count, over-long title |

Full item list, rationale text and thresholds: `references/rules.json` (data, editable).

## 7. Evidence and locator rules (non-negotiable)

- Every issue carries a `quote` cut from the extracted text plus `locator`: `source_id`, `page`
  (null when the extractor exposes none), `section`, `paragraph_id` (`P0007`), `sentence_id`
  (`P0007S02`), `char_start`/`char_end` (offsets in the normalised text).
- A quote that does not match after normalisation is demoted to `pending_human`; wording is never
  adjusted to make a quote pass.
- Page numbers come from the extractor; when absent the field is `null` and the paragraph/character
  range is the authoritative pointer (stated in `uncertainty`).
- No page, figure, statistic, DOI, reference or reviewer statement is ever invented. Doc-level
  findings quote the closest real sentence and record the full-text count in `evidence.doc_level`.

## 8. Severity anchors and false-positive control

- `major`: changes credibility/reproducibility/conclusion, or a submission-blocking omission.
- `minor`: reporting or compliance gap that is fixable without new experiments.
- `info`: improvement suggestion.
- **Gating**: context-dependent checks fire only when their precondition holds (empirical study,
  human/animal data, reference list present, captions present, ≥3 sections, ≥700 words). When the
  precondition fails the item is recorded as `not_checked` with a reason instead of firing.
- **No mass-missing when structure is unknown**: if no section headings are detectable (excerpt,
  scanned text), chapter/statement checks are suppressed and reported as not executed.
- Discipline conventions (formatting, style, journal-specific layout) are not defects by default;
  they appear only as `info` suggestions with an explicit “check against target journal” note.
- Identical quotes with the same facet are de-duplicated; each rule is capped (4 hits) to prevent a
  single pattern from flooding the list.

## 9. Exceptions and degradation branches

| Situation | Behaviour |
|---|---|
| missing input dir / no materials | `status=input_error` or `insufficient_evidence`, error recorded, artifacts still written |
| malformed `case.json` | error recorded, other files still reviewed, contract echoed if present |
| PDF unreadable / no text tool | `engine=none`, degradation + `pending_human`, text checks skipped for that file |
| DOCX/XLSX unreadable | `engine=failed`, degradation recorded, other materials unaffected |
| images / figures | not OCR'd → `pending_human` (`material_unreadable`) + dependent checks `not_checked` |
| text < 400 characters | `status=insufficient_evidence`, no conclusions extrapolated |
| no section headings | degradation + chapter checks `not_checked` |
| quote not found | issue demoted to `pending_human` (`quote_not_found`) |
| agent findings malformed | rejected into `pending_human` with reason, run continues |
| unexpected exception anywhere | captured in `errors` with traceback, `result.json` finalised, exit 0 |

## 10. Minimal invocation example (示例，非正式案例结果)

Input `/input/case.json`:

```json
{"case_id": "demo-001",
 "task_instruction": "review this manuscript",
 "output_contract": {"issues": null, "issue_count": null, "verdict": null},
 "artifacts": ["manuscript.md"]}
```

`/input/manuscript.md` contains: “Mean glucose decreased … (p = 0.000), a significant improvement.
… TODO: add mechanism paragraph. … (Figure 5)” with no figure caption.

```bash
python3 scripts/review.py --input /input --output /app/output
```

Illustrative excerpt of the shape of the output (values are illustrative only):

```json
{"case_id": "demo-001", "status": "partial",
 "issues": [{"id": "MJ-001", "facet": "statistics_report", "severity": "major", "basis_type": "error",
             "check_item": "p 值被报告为 0", "quote": "… (p = 0.000), a significant improvement.",
             "locator": {"source_id": "S1234", "page": 1, "section": "abstract",
                         "paragraph_id": "P0002", "sentence_id": "P0002S03",
                         "char_start": 126, "char_end": 211},
             "rationale": "p 值不可能精确等于 0 …", "suggestion": "改报精确值或 p < 0.001 …",
             "quote_verified": true, "origin": "rule"}],
 "issue_count": 10, "verdict": "major_issues_present",
 "review": {"facet_coverage": {"statistics_report": {"status": "checked", "checked_items": 8, "total_items": 8}}},
 "artifacts": {"result_json": "/app/output/result.json", "review_report_md": "/app/output/review_report.md",
               "issues_csv": "/app/output/issues.csv", "corpus_json": "/app/output/corpus.json"}}
```

## 11. Self-check before delivery

1. `result.json` parses; every `output_contract` key present (`contract_fill.keys` equals the input count).
2. `metrics.quotes_verified + quotes_rejected == quotes_total`; `quotes_rejected` items appear in `pending_human`.
3. `status` matches reality: `ok` only when nothing is pending/unchecked.
4. `unchecked[]` lists the checks that were skipped and why; no facet is silently empty.
5. `review_report.md` and `issues.csv` exist and carry the same issue ids.
6. Re-running on the same input yields the same ids/order (deterministic).

## 12. Files

| File | Role |
|---|---|
| `SKILL.md` | this contract |
| `scripts/review.py` | extraction, corpus, merge, contract echo, artifact writing (≤20 KB) |
| `scripts/checks.py` | rule engine, coverage, quote verification, report renderer (≤20 KB) |
| `references/rules.json` | rule table, severity anchors, section vocabulary, profile regexes |
| `references/report_template.md` | report skeleton (`{{placeholders}}` filled at run time) |
| `references/checklist.md` | the six facets, item definitions, agent-findings schema, FP rules |

## 13. Maintenance

- Rules are data: edit `references/rules.json` (`rules[]`, `specs[]`, `computed{}`), no code change.
- Add a check: append a spec with `applies` + `fire` (`absent` / `absent_section` / `stat_true` /
  `stat_false` / `none_stat` / `count_not_between` / `list_count`) and a `quote` pattern.
- Keep both scripts ≤20 KB, standard library only, no CWD assumptions (paths derive from `__file__`).
- Version bumps: update `version` here and in `rules.json`; result.json records `skill.version`.
