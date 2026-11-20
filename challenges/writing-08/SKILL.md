---
name: methods-experiments-writer
description: Assemble a traceable, reproducible Methods and Experiments section from scattered research materials. Extracts the six required element classes (procedure, setup, parameters, datasets, controls, reproducibility and limitations), attaches evidence tags with source locators, reconciles reported values against config/log/code, and reports missing or conflicting facts for author confirmation. Use when writing, completing, revising, or auditing methods, experimental setup, hyperparameter, dataset split, baseline comparison, or reproducibility sections.
version: 2.0.0
---

# Methods & Experiments Writer

## 0. Agent modification boundary

This Skill is a **structured extraction and drafting system**, not a fixed answer generator.

You, the Harness Agent, must:

1. Read the actual files under `/input`; do not infer scientific facts from file names or case labels.
2. Preserve script-generated structured JSON schema fields: `result.json`, `evidence_table.json`, `claims`, `locator`, `quote`, `source_id`, `support_scope`, `parameter_table`, `output_contract`. Do not hand-edit these structures into invalid states.
3. Write or improve substantive editorial content through `/app/work/draft.json` and the editable prose artifact. Never paste a template as the final answer.
4. Keep every numeric value, dataset version, split ratio, training/evaluation condition, baseline name, and reproducibility claim tied to an evidence entry with a verbatim quote and locator.
5. Put missing, unsupported, or conflicting facts into `pending_human` instead of inventing them.
6. Exit with code `0` even when the case is only partially completed.

---

## 1. Single-command entry point

Primary command:

```text
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

This one command internally performs:

| Stage | Action |
|-|-|
| `init` | Inventory all materials; assign stable source IDs (`S1`, `S2`, ...); extract candidate textual and numeric facts; group conflicts by normalized key; write `/app/work/ledger.json`. |
| `build` | If `/app/work/draft.json` exists, validate and use it. If no draft exists, run deterministic extraction from the init ledger. Render all required artifacts and finalize `/app/output/result.json`. |
| `selfcheck` | Verify that output files match the original `output_contract`; verify evidence locators and quotes; report pass/fail into `checks`. |

The command is intended to be safe to run repeatedly. Running `run` after an Agent improves the draft should not destroy structured outputs; it should rebuild from the best available draft.

If the `run` subcommand is unavailable in an installed script version, use the equivalent legacy command:

```text
python3 -B scripts/main.py --input-dir /input --out /app/output
```

Then run the equivalent build/selfcheck steps that the available script exposes.

---

## 2. Agent-first dual path

### Path A: Agent path

1. Run `init` or the full `run` command once to create a baseline.
2. Inspect `/app/work/ledger.json` or `/app/work/parsed_corpus.json`.
3. Actually open the material files and verify source text.
4. Write `/app/work/draft.json` containing the best possible evidence-backed chapter.
5. Run `build` and `selfcheck`.
6. Improve the editable prose and rerun until budget is exhausted or checks pass.

### Path B: Deterministic fallback when no `draft.json` exists

`build` must produce a substantive work product from the init ledger, not an empty placeholder:

- Generate text from verbatim source snippets.
- Attach `[S#]` source labels and locators such as `config.yaml#L12`, `train.log#L95`, `paper.pdf#p.3`.
- Produce a parameter table, dataset summary, procedure, controls, reproducibility checklist, and limitations where possible.
- Record `AUTO_EXTRACT` honestly in `degradations` and/or `gaps`.
- All automatic statements must be traceable and conservatively worded; unsupported elements become `missing` in `pending_human`.

Both paths must produce **the same output file set and the same `result.json` contract**. The difference is only whether the prose is Agent-refined or deterministic baseline.

---

## 3. Runtime contract

| Item | Requirement |
|-|-|
| Input | Read `/input/case.json`, `/input/task.md`, and all material files. |
| Work | Use `/app/work` for ledger, draft, temporary parses, and baseline files. |
| Final output | Write all final artifacts under `/app/output`. |
| Required JSON | `/app/output/result.json` must exist and be valid JSON. |
| `case_id` | Always present at top level of `result.json`. |
| Original contract | Preserve all original `output_contract` fields unchanged inside `result.json.output_contract`. |
| Dual echo | Every original `output_contract` field should also appear at the top level of `result.json` with the same final value, unless the key collides with a standard runtime field; then keep the standard runtime field at top level and preserve the contract field inside `output_contract`. |
| Exit code | Always exit `0`. |
| Budget | 64 model requests, 900 seconds, 16384 tokens per response including reasoning. |
| Preview | Editable Office/slide/diagram artifacts must also have rendered PDF/PNG previews listed in `outputs`. |

---

## 4. Output file set

Produce the following files under `/app/output`, unless the original `output_contract` explicitly requires different file names:

| File | Purpose |
|-|-|
| `manuscript.md` | Editable Methods/Experiments chapter. Use the contract-required name if specified. |
| `parameter_table.csv` | Parameters with name, value, units, applies-to, source IDs, locators. |
| `evidence_table.json` | All evidence entries: claim ID, source ID, locator, verbatim quote, support scope. |
| `dataset_summary.md` | Dataset names, versions, sizes, preprocessing, splits, random splitting method, uses. |
| `control_table.md` or `controls.csv` | Baselines, versions, compute budget, evaluation metrics, statistical method. |
| `reproducibility_checklist.md` | Code version, environment, commands, data access, seeds, repeats. |
| `change_log.md` | Modifications, conflicts, corrections against source values. |
| `pending_human.md` | Missing facts, unsupported values, conflict questions for author confirmation. |
| `workorder_report.md` | Item-by-item response to the task work order. |
| `result.json` | Machine-readable contract, status, sources, uncertainty, outputs, checks, coverage. |
| preview files | PDF/PNG when editable Office/slide/diagram outputs are required. |

If the contract requires a different primary artifact name, use that name in the output directory and record it in `result.json.outputs`.

---

## 5. Six required coverage elements

The methods/experiments chapter must cover:

1. **Procedure**: ordered, executable steps; each step has input, operation, output, and decision condition.
2. **Experimental setup**: training/validation/test flow separated; hardware, software version, environment, random seed, repeat count.
3. **Parameters**: name, value, unit, object of application, source locator.
4. **Dataset and splits**: dataset name, version, size, preprocessing, split ratio, random method, use of each subset.
5. **Controls**: baseline object and version, comparable budget/condition, evaluation metrics, statistical method.
6. **Reproducibility and limitations**: code version, environment, commands, data access, seeds/repeats, and limitations tied to concrete failure scenarios or scope boundaries.

Every element has a dedicated section/table. If any element cannot be supported by materials, do not delete it from the structure; mark it explicitly as `missing` in `pending_human` and in `element_coverage`.

---

## 6. Evidence and source rules

- Source IDs are stable strings: `S1`, `S2`, ...
- Locators use the most specific available form:
  - PDF: `paper.pdf#p.3`
  - DOCX/MD/TXT: `file.md#para 12`
  - YAML/JSON/XML: `config.yaml#/training/learning_rate`
  - INI/TOML: `config.ini#L40`
  - Code: `train.py#L88`
  - Log: `train.log#L95`
  - CSV/TSV: `results.csv#row 7`
- Every factual claim, number, dataset version, baseline, metric, and key statement must be marked with an evidence tag in the prose: `[E1]`, `[E2]`, ...
- Each `[E#]` tag must resolve to an entry in `evidence_table.json`.
- Every `quote` field must be a verbatim substring of the parsed material. Do not paraphrase inside `quote`.
- Unsupported numbers must not appear in the main prose. They may appear only in `pending_human` or `derived_counts` with `kind: derived` when they are simple counts or calculations based on material facts.

---

## 7. `draft.json` shape for Agent use

Write `/app/work/draft.json` with the following fields when using the Agent path:

- `case_id`
- `draft_text`: full manuscript text using `[E#]` tags.
- `claims`: array of `{claim_id, source_id, locator, quote, strength, support_scope}`.
- `parameter_table`: array of `{parameter, value, units, applies_to, source_ids, locators}`.
- `dataset_summary`: object with dataset records and source IDs.
- `procedure`: ordered step objects with `input`, `operation`, `output`, `condition`, `source_ids`.
- `setup`: training/validation/test setup details.
- `controls`: baseline comparison details.
- `reproducibility_checklist`: checklist entries.
- `limitations`: specific limitations with `failure_scope`.
- `conflicts`: array of `{id, description, left_source, left_value, right_source, right_value, chosen, reason}`.
- `pending_human`: array of `{id, severity, blocking, question, source_ids}`.
- `change_log`: array of `{from, to, reason, source_ids}`.
- `workorder_report`: array of `{item, status, artifact_refs}`.

The build step validates that all `[E#]` references exist and that quotes are verbatim. Invalid claims are rejected into `verification.json` and not silently included.

---

## 8. Execution protocol

### Step 1: Read task and contract

1. Parse `/input/case.json`.
2. Extract `case_id`, `output_contract`, task instructions, material paths, audience, style, and format constraints.
3. Read `/input/task.md` for scoring dimensions and any explicit work order.
4. Scan all `/input` files and classify by extension and magic bytes.

Failure handling:
- If `case.json` is missing or malformed, infer the task from `task.md` and materials, record `errors[].stage = case`, and continue.
- Always produce a valid final `result.json`.

### Step 2: Run baseline init/build immediately

Run:

```text
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

This should immediately create a baseline result and partial artifacts. If the script fails, manually create the minimum legal `result.json` and all required standard files.

Minimum result must contain:

- `case_id`
- `status`
- `sources`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `changes`
- `runtime`
- `outputs`
- `output_contract`
- all original `output_contract` fields at top level and nested

### Step 3: Actually parse materials

Use available parsers for:

- PDF: extract text; if no text layer or printable-character ratio is low, mark `degraded` and request OCR/author text.
- DOCX: extract paragraphs and tables.
- CSV/TSV: read headers and rows.
- YAML/JSON/CFG/INI/TOML: parse as key-value structures with line numbers.
- Code/log files: extract important parameters, commands, seeds, versions, metrics.
- Images: if no OCR is available, mark `skipped` and list the unmet need.

Store parsed material under `/app/work/parsed_corpus.json` or equivalent.

### Step 4: Construct or improve evidence-backed draft

Use the parsed corpus to:

1. Extract all six element classes.
2. Normalize candidate keys such as `learning_rate`, `lr`, `batch_size`, `epochs`, `seed`, `weight_decay`, `optimizer`, `train_split`, `valid_split`, `test_split`, `dataset_version`, `baseline`, `metric`, `gpu`, `precision`.
3. Attach source IDs and locators to every candidate fact.
4. Compare draft values with config/log/code values.
5. When values conflict, keep both locators, choose the config/log code value as the primary written value, and create a blocking `C#` question.
6. Put unsupported values into `pending_human`.

### Step 5: Write or improve prose

Write `manuscript.md` as a clean, editable methods/experiments chapter:

- Overview from materials only.
- Dataset description.
- Ordered procedure.
- Experimental setup.
- Parameter table aligned with prose.
- Controls and evaluation.
- Reproducibility checklist.
- Limitations tied to concrete failure scope.
- Appendix A: Evidence index from `[E#]` to source and locator.
- Appendix B: Pending human questions and conflict items.

Do not invent references, DOIs, arXiv IDs, or benchmark baselines. If a citation-like string appears, it must be found verbatim in the source material.

### Step 6: Run build and selfcheck

Run:

```text
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

Or rerun the full `run` command.

Selfcheck must verify:

- `output_contract` completeness.
- File existence and non-emptiness.
- Evidence tag resolvability.
- Verbatim quote property.
- Six-element coverage.
- Missing/conflict registration.
- PDF/PNG preview existence when required.

### Step 7: Finalize

Ensure `/app/output/result.json` exists, is valid JSON, and contains:

| Field group | Content |
|-|-|
| Case identity | `case_id` |
| Runtime status | `status`, `runtime`, `errors`, `degradations` |
| Source map | `sources` |
| Uncertainty | `uncertainty` |
| Human questions | `pending_human` |
| Change record | `changes`, `change_log` |
| Evidence | `evidence_map`, `evidence_table`, `preserved_facts` |
| Tables | `parameter_table`, `dataset_summary`, `control_table` |
| Written artifact | `manuscript` |
| Reproducibility | `procedure`, `reproducibility_checklist`, `limitations` |
| Coverage | `element_coverage`, `derived_counts` |
| Work order | `workorder_report` |
| Contract | `output_contract` nested object plus top-level contract field echo |
| Output files | `outputs` |
| Verification | `checks`, `verification` |

Set exit code `0`.

---

## 9. Budget-aware execution strategy

| Phase | Estimated model requests | Action |
|-|-|-|
| Read input/contract | 1–2 | Extract case ID and output contract. |
| Run baseline `run` | 1 | Save early honest partial artifacts. |
| Parse materials | 6–12 | Read actual files; do not trust labels. |
| Build evidence table | 6–10 | Align facts with source locators and quotes. |
| Write final prose | 12–20 | Cover all six elements; mark `[E#]`. |
| Rerun build/selfcheck | 2–6 | Verify contract and evidence. |
| Finalize result | 1–3 | Merge all fields and write outputs. |

Budget rules:

- Always run baseline first, so a later timeout still leaves a partial result.
- If time drops below 200 seconds, skip deep secondary improvement and finalize the current best artifact as `status: partial` if needed.
- If time drops below 60 seconds, stop editing and write the current partial result immediately.
- Near 64 requests or 900 seconds, do not start new parsing; close with honest limitations.

---

## 10. Hidden-case robustness

| Case type | Expected risk | Behavior |
|-|-|-|
| Normal case with full materials | Satisfy complete six-element chapter | Full Agent extraction, evidence table, parameter/table alignment, previews. |
| Boundary case with partial materials | Some elements missing | Leave missing elements in `pending_human`; do not fabricate; set `status: partial` if any key element missing. |
| Anomalous case | Corrupt/unsupported files, no text-layer PDF, missing contract, empty input | Mark `degraded` or `skipped`; create legal `result.json`; exit `0`; record real errors. |
| Conflicting values | Config vs log vs draft | Keep both locators, choose source-backed value, create `C#` blocking question. |
| No `draft.json` | Agent did not supply draft | Deterministic fallback builds conservative evidence-backed draft from ledger. |
| Script failure | `main.py` missing or broken | Agent constructs minimal legal result and artifacts manually, records package resource failure. |
| Editable Office/slide requirement | Preview missing | Generate rendered PDF/PNG previews and list them in `outputs`. |
| Output contract contains custom file names | Fixed file set mismatch | Use contract-required file names and record all outputs in `result.json.outputs`. |

---

## 11. Rubric-evidence mapping

| Rubric dimension | Required deliverable evidence |
|-|-|
| Actual effect: task completion | Complete manuscript sections; workorder item-by-item report; element coverage counts. |
| Actual effect: correctness | Parameters/dataset versions/baselines match source; conflicts corrected; no unsourced numerals. |
| Actual effect: completeness | Six elements all present or explicitly pending; missing items are not deleted. |
| Actual effect: verifiability | `[E#]` markers; evidence table; verbatim quotes; source locators. |
| Use gain: quality | Evidence tags, conflict reconciliation, pending questions, changed values. |
| Use gain: efficiency | Single `run` command; generated tables and checklists; short runtime. |
| Use gain: verifiability of gain | Baseline artifact preserved under `/app/work`; final artifacts under `/app/output`; `changes` and `change_log` list concrete improvements. |
| Innovation: new capability | Extract–align–gap–ask loop realized in pipeline; not a blank template. |
| Innovation: method improvement | Normalized key extraction, conflict grouping, quote validation, deterministic fallback. |
| Innovation: evidence | Actual run artifacts show extraction, alignment, gaps, and pending questions. |
| Reliability: usability | Clear entry command and stepwise protocol. |
| Reliability: stability | Deterministic ordering, standard-library parsing, idempotent reruns, exit `0`. |
| Reliability: exception handling | `errors`, `degradations`, `pending_human`, `status` used correctly. |
| Ecosystem: documentation | This SKILL plus `references/templates.md` and `references/examples.md`. |
| Ecosystem: reusability | `scripts/main.py`, `scripts/kit.py`, `references/vocab.json`, parameter/checklist templates. |
| Ecosystem: share/promote | Worked examples and failure modes in `references/examples.md`. |

---

## 12. Self-check checklist before finalizing

- [ ] `/app/output/result.json` exists and is valid JSON.
- [ ] `case_id` is present at top level.
- [ ] `result.json.output_contract` contains all original output contract fields unchanged.
- [ ] All original contract fields are echoed at top level or preserved in nested contract.
- [ ] `status`, `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `outputs` are present.
- [ ] Six elements are covered in `manuscript.md` or explicitly pending.
- [ ] Every numeric value and key claim has `[E#]` or table source locator.
- [ ] Every `[E#]` resolves in `evidence_table.json`.
- [ ] Every `quote` is a verbatim substring of parsed material.
- [ ] Conflicts are recorded with both locators and `C#` IDs.
- [ ] Missing facts are in `pending_human` with severity and blocking flag.
- [ ] Editable Office/slide outputs have PDF/PNG previews.
- [ ] No fabricated DOI/arXiv/reference/benchmark score is present.
- [ ] Final exit code is `0`.

---

## 13. Avoid these high-cost mistakes

1. Do not exit nonzero; always finalize a legal `result.json`.
2. Do not omit the nested `output_contract` object.
3. Do not hand-edit script-generated structured JSON into an invalid state.
4. Do not invent unsourced numbers, dataset versions, software packages, DOIs, arXiv IDs, or benchmark scores.
5. Do not rely on file names or domain labels instead of reading actual content.
6. Do not submit the raw script/template output as the final Agent answer; use it as baseline.
7. Do not consume the entire budget before saving a partial result.
8. Do not leave missing six-element sections unmarked; always register them as pending/gap.
9. Do not paste `draft.json` as a final artifact; render it into the requested editable chapter and tables.
10. Do not claim comparison gains without preserving baseline artifacts and listing concrete changes.

---

## 14. Package resources

Use these existing package resources:

- `scripts/main.py`: entry point for `run`, `init`, `build`, `selfcheck`; parsing, rendering, finalization.
- `scripts/kit.py`: deterministic extraction, normalization, source numbering, quote validation, table rendering.
- `references/vocab.json`: aliases and canonical keys for the six element classes, parameter names, dataset terms, evaluation terms.
- `references/templates.md`: schema templates for `draft.json`, `evidence_table`, `parameter_table`, `pending_human`, and output files.
- `references/examples.md`: worked example and failure patterns; mark example output as illustrative.

All extraction must be offline-capable and use only the Python standard library unless the pinned environment already includes a specific parser. If a parser is unavailable, degrade honestly. The Skill must not depend on network access, private files, pre-extracted answer layers, or author-provided hidden state.