---
name: multistep-data-analysis
description: Turn raw scientific data (CSV/TSV/XLSX/JSON/SQLite + data dictionary + task) into a reproducible, evidence-backed analysis package. Covers import, field alignment, cleaning, descriptive/inferential statistics, visualization, code execution, and report generation with source locators, uncertainty records, and contract-compliant result.json. Use for multi-step research data analysis tasks requiring traceable computation and editable outputs.
version: 1.2.0
license: MIT
---

# Multistep Data Analysis Skill

## 0. Global Priorities and Hard Constraints

1. **Always exit 0.** Even on total failure, write an honest `/app/output/result.json`, record the error, and exit 0. Never crash.
2. **Do not fabricate.** Never invent data, benchmark scores, source quotes, or analysis results. All conclusions must come from real parsed material or real computation.
3. **Complete the contract first.** Cover every field in `/input/case.json` `output_contract`. Missing fields must be recorded in `limitations` and `pending_human`, never silently omitted.
4. **Preserve evidence.** Every numeric result, cleaning rule, statistical choice, and figure must have a source locator: `[S#]` plus `file#line/paragraph`.
5. **Single-entry workflow.** Prefer one deterministic command that runs init → build → selfcheck. Use Agent time to verify and improve, not to re-run fragile manual steps.
6. **Budget awareness.** You have at most 64 model requests and 900 seconds. Produce a full baseline in 1–3 requests, then incrementally improve. Save early; save often.

---

## 1. Single-Command Entry and Execution Stages

### Preferred entry point

Run:

```
python3 /skills/weekly-skill/scripts/analyze.py run --input /input --output /app/output --work /app/work
```

This command must internally execute three stages:

- **init**: inventory all input materials, assign source IDs `[S#]`, extract candidates, build field mappings, conflict groups, and a work ledger under `/app/work`.
- **build**: validate extracted facts, run deterministic fallback extraction if no Agent draft exists, compute statistics, generate tables and figures, render all editable artifacts, write all deliverables, and finalize `/app/output/result.json`.
- **selfcheck**: verify that every `output_contract` field has a corresponding file or result entry, validate JSON schema, verify locators exist, and append a `selfcheck` record to `result.json`.

### If `run` is unavailable or fails

First inspect the real interface:

```
python3 /skills/weekly-skill/scripts/analyze.py --help
python3 -c "import sys; sys.path.insert(0, '/skills/weekly-skill'); import scripts.statslib as s; print([n for n in dir(s) if not n.startswith('_')])"
```

Then run the equivalent stages explicitly (e.g., `init`, `build`, `selfcheck` subcommands) or, if the script only supports a different interface, use it as documented. If the script cannot run at all, implement the same stages with plain Python and the `statslib` functions. Regardless of path, the final `/app/output/result.json` must be valid and exit code 0.

---

## 2. Agent-First Dual Path

### Path A — Agent path (preferred when budget allows)

1. Run `run` or `init` to produce the work ledger.
2. Read the ledger, `/input/task.md`, `/input/case.json`, and the actual source files.
3. Write Agent judgments into `/app/work/draft.json`. The draft contains: selected claims, exact quotes, locators, statistical method choices, cleaning decisions, and notes on uncertain or missing data.
4. Run `check` (or `build --check`) to validate the draft against the ledger and source files.
5. Run `build` to render the final deliverables.
6. The `result.json` then marks the run as `agent_draft_path` and records `reviewed_by_agent: true`.

### Path B — Deterministic fallback

If no valid `/app/work/draft.json` is present:

1. `build` uses the init ledger to deterministically extract quotes, locators, field mappings, cleaning rules, and statistical results from the actual source content.
2. It writes a substantive working artifact with verbatim quotes and exact locators.
3. The run is marked `AUTO_EXTRACT` in `gaps` and `degradations`.
4. The output structure and `result.json` contract are **identical** to Path A. Path B is a complete honest result, not an empty skeleton.

Both paths must produce the same deliverable set and the same `result.json` contract fields.

---

## 3. Input Inventory and Contract Discovery

1. Read `/input/task.md` and `/input/case.json` if present.
2. Record `case_id` from `/input/case.json`.
3. Extract `output_contract` from `case.json`. If missing, infer a minimal contract: `case_id`, `status`, `results`, `sources`, `uncertainty`, `change_records`, plus `limitations` and `output_contract_missing: true`.
4. List the full `/input` directory tree. Do not assume file existence.
5. Identify all required deliverables: cleaned tables, statistical results, figures, code, report, logs, rule tables, version records, and any Office/slide/diagram artifacts.
6. Write `/app/work/plan.md` with priorities based on rubric weight: actual effect > usage gain > innovation > reliability/ecosystem.

---

## 4. Real Material Parsing and Source Numbering

Assign each unique input file a source ID `[S#]` in the order encountered. Use relative paths under `/input` as canonical identifiers.

Parse by extension:

- **CSV/TSV**: try `utf-8-sig`, `utf-8`, `latin-1`, `gbk`, `cp1252`; record final encoding.
- **XLSX/XLS**: use `pandas.read_excel` or `openpyxl`; record sheet names and ranges.
- **JSON**: load with `json`; summarize nested structure.
- **SQLite**: connect with `sqlite3`, list tables, examine schemas, read rows.
- **PDF**: use the platform-provided PDF text tool; extract real text and tables. Never use file names as content.
- **DOCX**: use `python-docx` or equivalent to extract paragraphs, tables, headers.
- **Images**: if OCR is available, use it; otherwise mark as `pending_human`.

For each material, write a parsed summary to `/app/work/parsed_summary.md`: source ID, path, parse status, row/column counts, field names, missing value overview, data types, and key excerpts relevant to the task.

---

## 5. Analysis Execution and Deliverable Generation

### 5.1 Cleaning and anomaly handling

- Define explicit rules for missing value treatment, outlier detection, duplicate merging, and field alignment.
- Apply rules in code; record before/after row counts and distributions.
- Never silently drop data. Record every deleted row, imputed value, or merged record with rule and source locator.

### 5.2 Statistical analysis

- Choose methods based on data structure, sample size, independence, and distribution assumptions.
- Verify test assumptions; if violated, switch to alternative methods (e.g., nonparametric) and explain why.
- Include descriptive statistics, effect sizes, confidence intervals, and multiplicity correction where applicable.
- Save all computed statistics in a structured table (CSV/JSON) with source locators.

### 5.3 Visualization

- Use real computed data after cleaning and aggregation.
- Ensure axes, aggregation level, error bars, and labels match the underlying table.
- Save figures as PNG/PDF in `/app/output` and reference them in the report.

### 5.4 Report generation

- Write a clean narrative report (`deliverable.md` or `manuscript.md`) suitable for a group meeting.
- Every number, table, and figure must be traceable to a result table or source file.
- Include sections: data sources, field mappings, cleaning rules and impacts, statistical methods and assumptions, results, figure interpretation, applicability boundaries, and limitations.

### 5.5 Code and logs

- Save all analysis code to `/app/output/code/`.
- Save a run log with commands, timestamps, environment summary, and change records.
- If code is Agent-generated outside the script, mark it `agent_generated` in `change_records`.

### 5.6 Editable artifacts and previews

- For Office/slide/diagram outputs, generate real rendered PDF or PNG previews using available tools like `libreoffice --headless`.
- Place editable files and previews side by side in `/app/output`.

---

## 6. result.json Contract and Dual Echo

Write final `/app/output/result.json` such that:

- All `output_contract` fields appear **twice**: once at the top level and once inside a nested object named `output_contract`.
- Include `case_id` in both locations.
- Include honest `status` (`completed`, `partial`, `failed`, or `pending_human`), `sources`, `uncertainty`, `pending_human`, `errors`, and `degradations`.
- Include `change_records` with chronological entries, including baseline vs. Agent-corrected differences.
- Every numeric result or key claim has a `[S#]` source and a `file#line/paragraph` locator.
- If no valid draft was used, include `AUTO_EXTRACT: true` in `degradations`.
- Missing data, parse failures, and unverifiable results must be listed in `limitations` and `pending_human`.

Example field section (not a template, shape only):

```
results: {
  "cleaning_table": "/app/output/cleaning_table.csv",
  "stats_table": "/app/output/stats_table.csv",
  "figures": ["/app/output/fig1.png"],
  "report": "/app/output/deliverable.md"
}
sources: [
  {"id": "S1", "path": "/input/data.csv", "status": "parsed", "records": 1030}
]
uncertainty: ["Column X has 3 missing values treated as NaN"]
pending_human: ["Outlier in row 42 may need domain review"]
errors: []
degradations: ["AUTO_EXTRACT"]
```

Do not include fabricated `golden_standard`, `diff_report`, or weighted self-scores.

---

## 7. Self-Check and Rubric Alignment

After output generation, run selfcheck or manually verify:

### Actual effect (40)
- Import → cleaning → analysis → visualization → report are all present and linked.
- Numbers in report match statistics tables; figures match cleaned data.
- All required fields and checkpoints covered.

### Usage gain (25)
- Record automation savings: fewer manual steps, consistent structure, one-command reproduction.
- If baseline without Agent draft exists, compare the two runs in `change_records`.
- Do not fabricate comparisons; use actual script output.

### Innovation gain (15)
- Document orchestration, checkpoint design, deterministic fallback, and contract validation as new capabilities.
- Record where the Skill avoids silent failure or increases reproducibility.

### Reliability (10)
- Handle empty tables, missing columns, type mismatches, division by zero, encoding errors, database failures, and rendering failures.
- Always record the issue and continue.

### Ecosystem (10)
- Reference `SELFTEST.md`, `environment/resources.yaml`, and `references/guide.md` (see §10).
- Provide reusable scripts and clear paths.

---

## 8. Anomaly and Degradation Strategy

For any failure:

1. Catch the exception.
2. Record type, message, and affected step.
3. Attempt one alternative method.
4. If still failing, mark the relevant output as `pending_human` or `limitations`.
5. Continue producing remaining outputs.
6. Write `status` honestly: `partial` or `failed` if necessary.
7. Exit 0.

Specific cases:

- Empty input/table → `status: partial`, results explain empty data.
- Missing columns/types → record actual vs expected; do not silently coerce.
- Encoding errors → try fallback encodings; record final encoding.
- SQLite/DB failure → attempt read-only mode; if unrecoverable, mark source unreadable.
- Rendering failure → keep editable file, mark `preview_pending`.
- Timeout → immediately write current result, status `partial`, limitation mentioning timeout point.

---

## 9. Budget Strategy

Recommended request allocation:

- Initial run + inventory + baseline: 3–8 requests.
- Parse materials once, then reuse `/app/work/parsed_summary.md`: 5–10 requests.
- Agent review and draft creation: 10–20 requests.
- Report enhancement and manual checks: 5–15 requests.
- Final selfcheck and result.json validation: 3–8 requests.
- Reserve 3–6 requests for retries.

If fewer than 8 requests remain, stop new analysis, finalize `result.json`, and exit 0. Always prefer honest partial over incomplete crash.

---

## 10. Ecosystem Resources

The Skill package should include, and Agent should consult:

- **SELFTEST.md**: self-check checklist, expected outputs for a sample input, and common failure examples.
- **environment/resources.yaml**: required Python version (>=3.8), standard library only, no external dependencies, offline mode.
- **references/guide.md**: shape of `/app/work/draft.json`, workflow diagrams, field naming conventions, and locator syntax.

Do not depend on personal files, network access, or non-declared tools.

---

## 11. Pre-Submission Checklist

- [ ] `/app/output/result.json` exists and is valid JSON.
- [ ] `case_id` matches `/input/case.json`.
- [ ] All `output_contract` fields appear top-level and nested in `output_contract`.
- [ ] `status`, `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `change_records` present.
- [ ] Every numeric claim has `[S#]` and `file#line/paragraph`.
- [ ] All materials parsed or marked as failed; no invention from file names.
- [ ] Cleaning rules, anomaly handling, duplicate merging recorded and actually executed.
- [ ] Statistical method assumptions and choice rationale in report.
- [ ] Figures match data; axes and error bars correct.
- [ ] Editable Office/slide/diagram files have rendered PDF/PNG previews.
- [ ] Report numbers can be traced to result tables; no contradictions.
- [ ] If Path B used, `AUTO_EXTRACT` recorded in `degradations`.
- [ ] Exit code 0.
- [ ] Output files are under `/app/output`; work files under `/app/work`.

---

## 12. Quick Command Reference

```
# Preferred one-shot entry
python3 /skills/weekly-skill/scripts/analyze.py run --input /input --output /app/output --work /app/work

# Inspect real script interface
python3 /skills/weekly-skill/scripts/analyze.py --help

# Check statslib functions
python3 -c "import sys; sys.path.insert(0, '/skills/weekly-skill'); import scripts.statslib as s; print([n for n in dir(s) if not n.startswith('_')])"
```

Always read `/input/task.md` and `/input/case.json` before analysis. Never modify `/input`. Place all final artifacts in `/app/output`. Treat the script as the deterministic engine; treat yourself as the verifier and report writer.