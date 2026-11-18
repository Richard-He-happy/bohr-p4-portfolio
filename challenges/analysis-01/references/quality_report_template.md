# Data quality report — {{FILE}}

- status: **{{STATUS}}** · rows {{ROWS_IN}} → {{ROWS_OUT}} · columns {{COLS}} · dictionary columns matched {{DICT_COLS}}
- primary key used for de-duplication: `{{KEY}}`
- case task: {{TASK}}

## 1. The five required processes

| process | result | where to check it |
|---|---|---|
| missing values | {{MISSING}} cells classified (blank / not-detected / below-LOQ / sentinel), none imputed | `field_issues.csv` → `n_missing`, `missing_reasons` |
| outliers | {{OUTLIERS}} columns flagged against dictionary bounds and a robust distribution rule | `field_issues.csv` → `n_out_of_range`, `n_dist_outlier` |
| duplicate records | {{DUPS}} rows removed, {{NEAR}} near-duplicate groups left for a human decision | `duplicates.csv` |
| format / unit / encoding | {{REWRITTEN}} cells rewritten, every rewrite logged with its fault code | `transform_log.csv` |
| quality report | this file and `quality_report.json`, whose numbers are re-derived in `assertions.json` | `assertions.json` |

No value is imputed. Every cell in `cleaned.csv` is either the source value or the result of a
recorded, reversible transform (unit factor, encoding repair, format canonicalisation).

## 2. Field-level issues

| column | role | unit | rows | missing | % | reasons | range | dist |
|---|---|---|---|---|---|---|---|---|
{{FIELD_TABLE}}

## 3. Units, encodings and reversible mappings

Units declared in the data dictionary:

{{UNITS}}

Workorder canonical-unit overrides: {{OVERRIDES}}

Every conversion records its factor in `transform_log.csv` (`reversible` column), so
`cleaned_value × factor` returns the source value within 1e-12 relative tolerance.

## 4. Descriptive statistics available downstream

Computed on duplicate-resolved rows, excluding missing, censored and invalid cells; sample standard
deviation (n−1); linear-interpolation quantiles. Full record in `stats.json`.

{{STATS}}

## 5. Gaps, assumptions and human decisions

{{PENDING}}

## 6. Reproduction

```bash
python3 scripts/main.py --input <case dir> --output <out dir>
```

Deterministic: rows stay in source order, floats are written as `%.12g`, no random seed and no
network. Re-running on the same input must reproduce `cleaned.csv` byte for byte. `verify.py`
re-derives every number in this report from the emitted tables.
