---
name: methods-experiments-writer
description: Assemble a traceable Methods and Experiments section from scattered research materials (config files, training logs, source code, dataset notes, result tables, author drafts). Extracts the six element classes (procedure, setup, parameters, datasets, controls, reproducibility and limitations), tags every clause with an evidence id, reconciles draft numbers against config and log values, and reports material gaps for author confirmation. Use when writing, completing or auditing a methods / experimental-setup / hyperparameter / dataset-split / reproducibility section, or when checking that reported values match the code and logs.
version: 1.8.0
---

# Methods & Experiments Writer

Turn scattered experimental material into a **methods + experimental-setup section**
in which every step, parameter, dataset version, control and limitation is traceable
to a file, a locator and a verbatim quote — and in which anything the material does not
contain is handed back to the author instead of being filled in.

## 1. Use it when / do not use it when

**Use** when the case ships research materials and asks for a methods, experimental-setup,
hyperparameter, dataset-split or reproducibility section — including the case where an
author draft must be completed or corrected against a config or log.

**Do not use** for abstract/introduction/discussion prose, pure language polishing without
materials, citation formatting alone, or any target artifact that is not a
methods/experiments-type section.

Deliverable: an editable Markdown section plus machine-readable evidence, parameter and
change records, with the gaps named.

## 2. Runtime contract

| Item | Value |
|-|-|
| Entry | `python3 -B scripts/main.py --input-dir /input --out /app/output` |
| Case file | `/input/case.json` (falls back to any `case*.json`, then materials only) |
| Materials | everything under the input root: pdf, docx, csv/tsv, json, yaml/cfg/ini/toml, code, log, md/txt |
| Exit code | always `0` |
| result.json | written **first as a valid partial**, overwritten by the finalized run |
| Dependencies | Python ≥3.9 standard library only; no network; no CWD assumption |

Options: `--input-dir`, `--case`, `--out`, `--lang {auto,zh,en}`.
`--help` prints the same contract. Resource paths are resolved from
`Path(__file__).resolve().parent`, never from the working directory.

## 3. Input discovery

1. Load the case file; keep `case_id` and `output_contract` verbatim.
2. Read instruction-like keys by meaning, not by fixed name: `task_instruction`,
   `instruction`, `prompt`, `question`, `organizer_workorder`, `organizer_edit_workorder`,
   `workorder`, `formal_inputs`, `artifacts`, `materials`.
3. Recursively scan the input root, classify by extension **and** magic bytes
   (`%PDF`, `PK` + `word/`), skip `__pycache__`, `.git`, `node_modules`; files >24 MB are
   skipped with a recorded degradation.
4. Files are parsed into segments `{loc, text}`; locators: `p.<n>` (pdf, stream order),
   `para <n>` (docx/md), `L<n>` (yaml/ini/log/code/text), `row <n>` (csv/tsv),
   `/a/b/0` (json pointer).
5. A material named in the case but absent on disk, or of an unsupported type, becomes an
   explicit gap — never a silent skip.

## 4. Six element classes

| Class | Derived from | Examples |
|-|-|-|
| procedure | explicit step markers, else code function order | numbered steps, `Step 3`, `然后…` |
| setup | device, hardware, GPU count, precision, framework, pinned versions | `gpu_model`, `torch==2.1.0` |
| parameters | learning rate, batch, epochs, weight decay, optimizer, scheduler, … | `lr: 0.001` |
| datasets | name, version, size, split, preprocessing | `split: 0.8/0.1/0.1` |
| controls | baselines, budget statements, metric rows | `baseline ResNet-18`, `test_acc=0.871` |
| repro | seeds, repetitions, commit, command line, data version, limitations | `seed: 42`, `repeats: 3` |

## 5. Outputs

| File | Content |
|-|-|
| `manuscript.md` | the section: overview, datasets, procedure, setup, hyperparameter table, baselines, metrics, reproducibility, limitations, Appendix A evidence index, Appendix B items to confirm |
| `parameter_table.csv` | name, value, unit, scope, source, locator, quote |
| `evidence_map.json` | one entry per cited fact: `evidence_id → source_id + locator + verbatim quote` |
| `change_log.md` | every correction and every added element with original → revised, reason, locator |
| `pending_human.md` | `Q#` gaps and `C#` conflicts the author must resolve |
| `result.json` | contract-filled structured result (below) |

`result.json` always carries `case_id`, `status`, `sources`, `uncertainty`,
`pending_human`, `errors`, `degradations`, `changes`, `runtime`, `outputs`, plus
`manuscript`, `preserved_facts`, `evidence_map`, `change_log`, `parameter_table`,
`dataset_summary`, `procedure`, `reproducibility_checklist`, `limitations`,
`element_coverage`, `workorder_report`, `checks`, `derived_counts`.

`derived_counts` collects every computed count, as the guide requires: `materials`, `records`,
`classes` + `coverage_rate` (element coverage), `gaps` (missing items), `checks_passed` /
`checks_failed` (pass rate), `rejected_quotes` (claims dropped because the quote did not match
the materials), `conflicts`, `corrections`.

**Contract filling**: the whole `output_contract` object is deep-copied; keys are never
renamed and unknown keys are preserved. Leaves are filled when the key matches a known
field (semantic alias table in `references/vocab.json`), otherwise left as given
(`null` / `[]`). Nested objects up to depth 3 are handled.

## 6. Traceability rules

- Every factual clause in the section carries `[E<k>]`; Appendix A resolves it.
- A quote is a verbatim substring of a parsed segment. If a value cannot be quoted, it
  is not written: it becomes a gap.
- No numeral appears in the section unless it occurs in the materials — the only
  exception is the run's own counts (materials, records, gaps), which are declared in
  `derived_counts` and marked `kind: derived` in `uncertainty`.
- Draft numbers that contradict a config or log are **corrected to the source value**,
  both locators are kept, and a blocking `C#` question is raised. The draft value is
  never silently retained.
- No literature identifiers, DOIs or statistics are invented; the check suite fails if a
  DOI/arXiv id appears in the manuscript that is not present in the materials.

## 7. Conflicts and author confirmation

Two different values for the same parameter across materials → both are recorded, the
section uses the config/log value, and the question names both locators. A whole element
missing → `Q#` with `element`, `item`, `question`, `basis`, `blocking`, `action`.
`blocking` is true for dataset, split, learning rate, batch size and epochs, because the
section cannot be reviewed without them.

## 8. Self-check (run in every case, results in `result.json.checks`)

| Check | Pass condition |
|-|-|
| `output_contract_fields` | every contract key path exists in the result |
| `quotes_verbatim_in_materials` | every evidence quote is a substring of the parsed corpus |
| `numerals_supported_by_materials` | every numeral in the manuscript is backed by the materials or by `derived_counts` |
| `evidence_markers_resolve` | every `[E<k>]` has an entry in the evidence map |
| `six_element_coverage` | at most two element classes empty, or every empty class declared in `pending_human` (thin materials are reported, not hidden) |
| `gaps_sent_to_pending_human` | any uncovered class has a pending question |
| `artifacts_written` | every declared output exists and is non-trivial |
| `no_invented_identifiers` | no DOI / arXiv id outside the materials |
| `status_consistent` | `ok` only when there are no gaps, conflicts or errors |

## 9. Exceptions and degradation

| Condition | Handling |
|-|-|
| case file missing / malformed JSON | continue with materials, `errors[].stage = case`, status degrades honestly |
| no parseable material | `status = insufficient_evidence` (or `input_error` when there is no case either) |
| PDF without a decodable text layer | file marked `degraded`, author-supplied text requested, run continues |
| PDF text layer below 62 % printable characters | same, with the measured ratio recorded |
| image or archive material | `skipped`, recorded as an unmet need (no OCR) |
| `.xlsx` material | not parsed by this version; recorded as a degradation — export the table to CSV |
| one file raises during parsing | that file only is marked `error`, extraction continues |
| draft/config conflict | both kept, source value used, blocking question raised |
| `kit.py` or `references/vocab.json` missing | honest partial result listing the missing packaged resource |

## 10. Workorders

`organizer_workorder` / `organizer_edit_workorder` items are read whatever their key name
and executed item by item: each item is mapped to the element class it mentions
(parameters, procedure, datasets, controls, reproducibility, setup, limitations), the
corresponding section is guaranteed present and evidence-marked, tables are emitted, and
the "do not add facts outside the materials" style constraint is honoured. The per-item
report lands in `result.json.workorder_report` with `status` `done` / `noted`.

## 11. Minimal call example (示例，非正式案例结果)

```bash
python3 -B scripts/main.py --input-dir ./demo --out ./demo_out
# stderr: [methods-writer] status=partial materials=3 facts=12 steps=2 gaps=6 (0.4s)
```

Input `demo/case.json` carries `case_id: DEMO-01` and
`output_contract: {manuscript: null, preserved_facts: [], evidence_map: [], change_log: []}`,
plus `config.yaml` (`lr: 0.001`) and a draft saying `学习率 0.01`. Output: `manuscript.md`
with `lr 0.001 [E2]`, a `change_log` entry correcting the draft, a blocking `C1` question,
and `status: partial`. This is an interface illustration, not a platform case result;
`references/examples.md` holds the full walkthrough.

## 12. Rubric mapping

| Rubric item | Field / check / artifact |
|-|-|
| task completion (steps, setup, params, data, controls, limits) | nine-section `manuscript.md`, `element_coverage`, `procedure` |
| correctness of values | `parameter_table.csv`, `evidence_map.json`, `change_log` corrections, `numerals_supported_by_materials` |
| completeness of the six elements | `element_coverage`, `checks.six_element_coverage` |
| verifiability | `[E<k>]` markers + Appendix A, `quotes_verbatim_in_materials`, `sources[].sha1` |
| quality gain over a bare agent | every value carries a locator; conflicts are corrected instead of smoothed over |
| efficiency gain | one command yields section + tables + change log + question list |
| new capability | extraction → alignment → gap interrogation, driven by `references/vocab.json`, not a fill-in-the-blank template |
| stability | partial-first write, exit 0, per-file error isolation, deterministic ordering |
| exception handling | `errors`, `degradations`, `pending_human`, `status` enum |
| reusability | `vocab.json` (aliases, question texts, section templates), `templates.md` (schema), `examples.md` |

## 13. Files

| Path | Role |
|-|-|
| `SKILL.md` | this contract |
| `scripts/main.py` (20 473 B) | discovery, parsers, orchestration, artifacts, counters, checks |
| `scripts/kit.py` (20 461 B) | vocabulary, extraction, gaps, composition, contract fill, checks |
| `references/vocab.json` | alias table, question texts, labels, section templates, contract field map |
| `references/templates.md` | section skeleton, table/field schema, locator and conflict patterns |
| `references/examples.md` | synthetic walkthrough and failure-mode examples (all marked 示例) |

Total 6 files; nothing else is required at run time.

## 14. Maintenance

- Wording, section templates and alias tables live in `references/vocab.json` — edit there,
  not in the code; keep `spec` lines in `canonical|element|aliases` form.
- New material types: add a parser function to `scripts/main.py`, register its extension in
  `EXT` (used by `sniff`) and its dispatcher entry in `DISPATCH`; keep the `{loc, text}`
  segment contract.
- Any behaviour change bumps `version` here and in `kit.V`; the running version is reported
  in `result.json.runtime.version`.
- Re-run the three checks that guard honesty after every change: contract fill, quote
  match, numeral support.
