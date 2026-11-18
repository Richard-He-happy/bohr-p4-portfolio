# Templates and schema (methods-experiments-writer)

Reusable pieces of the skill: the section skeleton, the parameter-table schema, the
result field schema, locator conventions and the gap-question pattern. Copy them into
other writing skills or into an author checklist without modification.

## 1. Section skeleton

The rendered section always follows the same nine-part order, in the language detected
from the case (`zh` or `en`):

| # | Section | Filled from | Empty behaviour |
|-|-|-|-|
| 1 | Overview | counts of materials, records, element classes, gaps | always written |
| 2 | Datasets and splits | `dataset`, `version`, `samples`, `split`, `train/val/test size`, `preprocess` | "not present; see Appendix B" |
| 3 | Procedure | explicit step markers, else code function order | gap question `steps` |
| 4 | Experimental setup | `device`, `hardware`, `ngpu`, `precision`, `framework`, `pkg` | "not present; see Appendix B" |
| 5 | Hyperparameters | parameter table (Table 1) | "not present; see Appendix B" |
| 6 | Baselines and controls | `baseline`, `budget`, metric rows | no same-budget claim is written |
| 7 | Metrics and statistics | metric rows (`via=metric`) | "not present; see Appendix B" |
| 8 | Reproducibility checklist | `seed`, `repeats`, `commit`, `version`, `pkg`, `command` | "not present; see Appendix B" |
| 9 | Limitations and scope | `limit` sentences from drafts, else a reporting-level statement | never invented |
| A | Evidence index | every cited fact: id, file, locator, verbatim quote | table of all cited facts |
| B | Items to confirm | every gap and every draft/config conflict | `Q#` / `C#` rows |

Rules that hold in every language:

1. Every factual bullet or step carries `[E<k>]`; the appendix resolves `E<k>` to a file,
   a locator and a verbatim quote.
2. A missing element produces a `Q#` row and a `pending_human` entry, never a placeholder
   that looks like data.
3. A number that is not present in a parsed material never appears in the section.

## 2. Parameter table schema

`parameter_table.csv` columns (also `parameter_table` in `result.json`):

| Column | Meaning | Example |
|-|-|-|
| `name` | canonical parameter name, `scope.name` when the material nests it | `train.lr`, `batch`, `epochs` |
| `value` | value exactly as written in the material, units kept | `0.001`, `4`, `bf16` |
| `unit` | trailing unit if present, else empty | `%`, `GB`, `ms` |
| `scope` | dotted prefix of the key, or `-` / `global` | `train` |
| `source_id` | material id assigned by discovery | `M1` |
| `locator` | in-file position | `L15`, `p.2`, `row 4`, `/train/lr` |
| `quote` | verbatim source line, truncated to 120 chars | `lr: 0.001` |

Duplicate `(name, value)` pairs are collapsed; two different values for the same name are
kept as separate rows and reported as a conflict when one of them comes from a draft.

## 3. result.json field schema

Required in every run:

| Field | Type | Meaning |
|-|-|-|
| `case_id` | string / null | copied verbatim from the case |
| `status` | enum | `ok`, `partial`, `insufficient_evidence`, `input_error` |
| `sources` | list | per material: id, path, kind, bytes, sha1, parse_status, segments |
| `uncertainty` | list | `gap`, `parser` and `derived` entries |
| `pending_human` | list | `Q#` gaps and `C#` conflicts, each with question, basis, blocking flag, action |
| `errors` | list | stage + detail, never swallowed silently |
| `degradations` | list | per-file parse limits (PDF text layer, image without OCR, oversize file, time budget) |
| `changes` | list | change ids plus the draft→deliverable relation |
| `runtime` | object | skill name, version, python, elapsed seconds, counts |
| `outputs` | list | artifact path, role, bytes |

Content fields: `manuscript`, `manuscript_path`, `language`, `word_count`, `preserved_facts`,
`evidence_map`, `change_log`, `parameter_table`, `dataset_summary`, `procedure`,
`reproducibility_checklist`, `limitations`, `element_coverage`, `workorder_report`,
`checks`, `derived_counts`.

`derived_counts` holds every computed count: `materials`, `records`, `classes`,
`coverage_rate`, `gaps`, `checks_passed`, `checks_failed`, `rejected_quotes` (claims whose
quote did not match the materials, i.e. rejected), `conflicts`, `corrections`.

`element_coverage` always carries the six classes:
`procedure`, `setup`, `parameters`, `datasets`, `controls`, `repro` — each
`{"items": <n>, "status": "covered"|"gap"}`.

## 4. Locator conventions

| Material | Locator | Note |
|-|-|-|
| PDF | `p.<n>` | stream order, not printed page number; state this when citing |
| DOCX | `para <n>` | paragraph index in `word/document.xml` |
| Markdown / text | `para <n>` / `L<n>` | paragraph start line / physical line |
| YAML / INI / log / code | `L<n>` | physical line |
| CSV / TSV | `row <n>` | 1-based, header is row 1 |
| JSON | `/a/b/0` | JSON pointer of the leaf |
| XLSX | — | not parsed by this version (see SKILL.md §9) |

A quote is a substring of the parsed segment, never a paraphrase. Whitespace is
normalised only when comparing, never when writing.

## 5. Gap-question pattern

Each gap has four parts, so that the author can answer without re-reading the code:

```
id        Q<n> | C<n>
element   parameters | setup | datasets | controls | repro | procedure
item      canonical key (lr, split, seed, budget, command, commit, ...)
question  one sentence naming the value and where it should live
basis     "absent from materials" or the conflicting locator
blocking  true when the section cannot be reviewed without it
action    who supplies it and from where
```

Typical questions: learning rate, batch size, epochs/steps, seed, hardware model and
count, framework/CUDA versions, dataset name and version, split ratios and randomisation,
preprocessing, baselines and their versions, metrics and aggregation, same-budget status,
repetition count, full command line, code version, failure scenarios.

## 6. Conflict record pattern

```
C<n>: <key> is <draft value> in the draft but <config value> in <source id>
      -> text uses the config value; both locators kept; blocking question raised
```

Never silently overwrite the draft, and never keep the draft value when the config or log
contradicts it: the section states the config value and the author decides.
