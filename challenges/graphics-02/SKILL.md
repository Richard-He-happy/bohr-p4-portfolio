---
name: source-value-chart
description: Generate a real, editable, source-bound scientific data chart (layered SVG plus PDF/PNG export) from the case's own table or statistics file, keeping a per-mark map so every bar, point, error bar and legend entry traces back to a source file, sheet, row, column and verbatim value. Use for chart generation or restyling workorders (bar, grouped bar, long-format series, line, scatter), for figure reproduction from published source data, and whenever numeric fidelity plus a checkable data-to-mark mapping matters more than decorative styling.
version: 1.0.0
---

# source-value-chart

## 1. Purpose and boundary

Turn the case's **own** data table into a publication-shaped figure and prove the mapping:
source cell → value → mark geometry → exported pixel/vector.

In scope: reading the supplied table, binding workorder fields to columns, computing bar
heights / point positions / error-bar lengths, typographic and layout styling, axis label and
unit handling, legend-to-series alignment, editable SVG authoring, PDF/PNG export, and a
point-level provenance map (`content_map`).

Out of scope (never fabricated): statistical method choice, significance testing, error-bar
*calculation*, experimental design, and any number, unit, gene/protein/species/compound name
that does not appear in the case material. Error bars and significance marks are only
**transmitted** from the source columns; if the column is missing the skill says so instead of
inventing one.

## 2. Runtime contract

* Entry point: `scripts/main.py`; helper module: `scripts/toolkit.py` (Python 3.8+, standard
  library only; `matplotlib`/`Pillow` are **not** required and never imported).
* Evaluated run: input `/input/case.json` + `/input/task.md` + material files under `/input/`;
  products go to `/app/output/`.
* Defaults when the flags are omitted: `--input` = `/input` if it exists else `./input`;
  `--output` = `/app/output` if `/app` exists else `./output`. Nothing depends on the CWD;
  the scripts also locate themselves with `Path(__file__).resolve().parent`.
* Exit code is always 0. A legal partial `result.json` is written **before** any risky work and
  rewritten at the end; an unexpected exception is caught and appended to `errors`.
* Budget-aware: no network, no package installation, no long-running jobs. Typical run
  < 15 s (table parse < 0.2 s, SVG < 0.1 s, PDF+PNG export 2–6 s).

## 3. Invocation

```bash
python3 /skills/weekly-skill/scripts/main.py                # /input -> /app/output
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --style journal
python3 /skills/weekly-skill/scripts/main.py --help         # usage, exits 0
```

| flag | meaning |
|---|---|
| `--input DIR` | case directory (case.json, data tables, task.md) |
| `--output DIR` | product directory (`result.json`, `chart.svg`, `chart.png`, `chart.pdf`, `chart_model.json`) |
| `--style NAME` | `journal` (default), `nature`, `thesis`, `presentation`, `default` |
| `--version` | print version |

## 4. Input discovery (semantic, no assumed key names)

1. Read `case.json`; if absent or unparsable, fall back to any `case*.json`, then keep going
   with what the directory offers (the failure is recorded in `errors` + `degradations`).
2. `case_id` and `output_contract` are passed through verbatim; `task_instruction` is quoted
   into `task.instruction`.
3. Any key whose value is a dict and whose name contains `workorder` is merged as the drawing
   workorder; any file whose name contains `workorder`/`figure` is parsed as JSON and merged
   as well. Key names inside it are matched semantically (`chart_type`/`figure_type`,
   `y`/`y_fields`/`value_column`, `error_bar`/`error_bars`, …), see
   `references/chart-workorder-schema.md`.
4. Every `.csv`, `.tsv`, `.tab`, `.xlsx`, `.xlsm` under the input tree is read; the table
   named by `source_table_ref` wins, otherwise the table with the most numeric cells.
5. If no table can be parsed, no chart is invented: `status=insufficient_evidence`, the gap is
   written to `pending_human`, and `compliance_checks.failures=[no_source_table]` is returned.

## 5. Pipeline (deterministic)

```
table  ->  cols()   field binding, unit split, error-column match, null reporting
       ->  build()  one intermediate representation: series x points, each with a locator
       ->  chart_model.json   axes, ticks, colours, plot box
       ->  render()  ->  chart.svg   layered, text kept as <text>, ids = content_map ids
       ->  export_pdf()  (soffice / rsvg-convert)      ->  chart.pdf
       ->  pdf_png()     (pdftoppm / gs)               ->  chart.png
       ->  checks: legend alignment, geometry round-trip, coverage, PNG/PDF structure
       ->  result.json
```

Rules that make the figure checkable:

* **Numbers are copied, not recomputed.** `y_raw` keeps the exact cell string (`"1.00"`,
  `"<0.01"`); the plotted value is parsed from that same string; nothing is rounded back.
* **Null is null.** Empty cells, `NA`, `n.d.`, `-` and censored values (`<0.01`) are skipped
  and listed as `missing_value`; they are never drawn as 0. A skipped point stays in
  `content_map.coverage.missing`.
* **Units come from the header or workorder only** (`OD600 (a.u.)` → label `OD600`, unit
  `a.u.`). Without a unit the axis literally says `unit not reported` and an `unit_unknown`
  exception is raised.
* **Colour is bound per series**, in table order, from a colour-blind-safe 8-colour palette;
  the legend is generated from the same list, so legend order cannot drift from bar order.
* **Every mark has a deterministic id** (`bar-s1-p3`, `pt-s2-p5`, `errt-s1-p3`, `xtick-2`,
  `legend-s1-text`), stable across runs, present both in the SVG and in `content_map`.

## 6. Output contract

`result.json` (in `--output`) always contains:

| field | content |
|---|---|
| `case_id` | verbatim from the case |
| `status` | `ok` \| `partial` \| `insufficient_evidence` \| `input_error` |
| `editable_source` | `path`, `format:svg`, `editable`, `layers`, `text_count`, `element_count`, `sha256`, `viewBox`, `model` |
| `export_artifact` | `svg`, `pdf{engine,pages,vector,mediabox_pt,bytes}`, `png{engine,width,height,dpi,color_type,bytes}` |
| `content_map` | `chart`, `series[].points[]` (value, raw string, source locator, geometry), `axes[]`, `legend[]`, `coverage{required,mapped,missing,ratio}` |
| `compliance_checks` | `canvas`, `fonts`, `line_widths`, `colors`, `legend_consistency`, `geometry_roundtrip`, `content_coverage`, `canvas_overflow`, `png`, `pdf`, `pass`, `failures` |
| `exceptions` | `{code, detail, severity, action}` for every skipped or blocked item |
| plus | `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `task` |

Every key of the input `output_contract` is echoed at the root with the same name; unknown keys
are kept (null/[] when there is no value).

Per-mark provenance (`content_map.series[i].points[j].source`) carries
`file, sheet, row, col, col_index, header, x_header, x_col, quote`, where `quote` is the raw
source line (CSV row / tab-joined XLSX row). Error bars add
`error_raw, error, error_mode, error_source`.

## 7. Rubric → field / check / artifact

| rubric item | where it is evidenced |
|---|---|
| 任务完成度 (15) | `chart.svg` + `chart.pdf` + `chart.png` + `chart_model.json` all present; `status` |
| 结果正确性 (15) | `geometry_roundtrip` (bar height px → value vs cell, 2 % tol), `legend_consistency`, axis `unit`/`scale` in `content_map.axes`, `y_raw` verbatim |
| 结果完整性 (5) | every workorder series and error column rendered, or listed in `exceptions`; `coverage.required == mapped` |
| 结果可核验性 (5) | per-point `source{file,sheet,row,col,header,quote}` + `editable_source.sha256` + `changes` + `runtime` |
| 质量增益 (15) | style preset (type scale, line widths, bar gaps), automatic legend binding, unit annotation, label rotation, `compliance_checks` |
| 效率增益 (5) | one command from table to SVG+PDF+PNG; `runtime` stage timings |
| 增益可验证性 (5) | same input twice ⇒ identical SVG (`sha256` in `editable_source`); assertions written into `compliance_checks` |
| 新增能力 (5) | px→value reverse check, legend/series auto-alignment, CJK-aware font stack, live text layer, journal presets |
| 方法改进 (5) | one intermediate model (`chart_model.json`) drives SVG, PDF, PNG and `content_map` |
| 创新证据 (5) | `geometry_roundtrip`, `legend_consistency`, `coverage.ratio`, `degradations` (fallback chain actually taken) |
| 调用与易用性 (3) | `--help`, defaults, `--style` |
| 运行稳定性 (4) | stdlib-only; CSV/TSV/XLSX; repeated runs; exit 0 |
| 异常处理 (3) | `exceptions` + `pending_human` for missing column/unit/null/log-axis/overflow/export failure |
| 文档完整性 (3) | this file + `references/*` |
| 资源可复用性 (4) | style presets, workorder schema, validation checklist, reusable on any table |
| 分享推广价值 (3) | one-command reproducible figure with a traceable data-to-mark map |

## 8. Evidence rules

* A mark may only carry a value that exists in the table cell quoted in its `source.quote`.
* Axis label / unit / scale are recorded with their origin (`source.header`, workorder key).
* Derived numbers (px geometry) are labelled as derived and never presented as source data.
* Uncertainty is declared in `uncertainty`: chart type inferred vs stated, units copied,
  statistics transmitted not computed.

## 9. Conflict and human confirmation

Ambiguity is never resolved by invention. `pending_human` collects: missing y column, missing
error column while the workorder asks for error bars, unknown unit, unparsable table,
unresolved column binding. Each entry names the code and the concrete gap, so a human can
supply one value instead of redoing the figure.

## 10. Failure / degradation table

| situation | behaviour |
|---|---|
| `case.json` unparsable | `errors` + `degradations`; continue from the directory scan; `status=partial` |
| no parsable table | `status=insufficient_evidence`, empty `content_map`, `failures=[no_source_table]` |
| workorder y column absent | `column_not_found`; that column skipped, table columns still plotted |
| empty / `NA` / censored cell | `missing_value`; point skipped and listed in `coverage.missing` |
| error bars requested, no error column | `error_column_missing`; no bars drawn |
| log scale with non-positive values | `log_axis_no_positive` or per-point `value_off_log_axis`; axis degrades to linear |
| long tick labels | rotated −35°; `canvas_overflow.x_labels_rotated=true` |
| unsupported chart type (heatmap/box) | `chart_type_unsupported`; bar marks used, recorded as a degradation |
| no PDF engine | `degradations` entry, `export_artifact.pdf` stays null, SVG still delivered |
| no rasteriser | `errors: png_export_failed`, SVG + PDF still delivered |
| check routine itself fails | `check_failed` exception, geometry kept in `chart_model.json`, `status=partial` |
| any unexpected exception | caught, `status=partial`, partial `result.json` retained, exit 0 |

## 11. Verification checklist (run before trusting a figure)

1. `result.json` parses; `case_id` matches; every `output_contract` key exists.
2. `compliance_checks.pass == true` with an empty `failures` list.
3. `content_map.coverage.required == mapped`; `missing` empty or explained.
4. `geometry_roundtrip.checked` equals the number of bars and `mismatch_count == 0`.
5. `legend_consistency.legend_items == series == distinct_colors`.
6. Axis unit is either the source unit or the literal `unit not reported`.
7. `export_artifact.pdf.pages ≥ 1` and `vector: true`; `png.width/height` non-zero, `dpi` as
   requested.
8. Open `chart.svg`: `<g id="layer-...">` present, labels are `<text>` (selectable), ids match
   `content_map`.
9. Re-run with the same input: `editable_source.sha256` unchanged.

Thresholds and the manual pass: `references/validation-checklist.md`.

## 12. Minimal call example (示意，非正式案例结果)

Input `case.json`:

```json
{"case_id": "demo-001",
 "output_contract": {"case_id": null, "status": null, "editable_source": null,
   "export_artifact": null, "content_map": null, "compliance_checks": null, "exceptions": []},
 "organizer_workorder": {"workorder_type": "source_value_chart", "chart_type": "grouped_bar",
   "x": "Treatment", "y": ["p-Actin"], "error_bar": {"mode": "sd"},
   "axis": {"y": {"label": "Normalized intensity", "unit": "a.u."}},
   "export": {"width_mm": 170, "dpi": 300}}}
```

`data.csv`:

```
Treatment,Replicate,p-Actin,p-Actin SD
Control,1,1.00,0.08
EGF,1,2.31,0.21
```

Call and (illustrative) result:

```bash
python3 scripts/main.py --input /input --output /app/output
# chart.svg chart.pdf chart.png chart_model.json result.json
# status "ok"; content_map.coverage {"required":2,"mapped":2,"ratio":1.0}
# series[0].points[1].source = {file:"data.csv",row:3,col:"C",header:"p-Actin",
#                               quote:"EGF,1,2.31,0.21"}
```

The numbers above are **示例（illustrative only）**, not results of any official case.

## 13. Files and versions

```
SKILL.md                              this document
scripts/main.py                       pipeline: discovery -> model -> SVG -> export -> result
scripts/toolkit.py                    readers, workorder spec, SVG primitives, probes, checks
references/chart-workorder-schema.md  workorder keys, defaults, binding rules
references/validation-checklist.md    checks, thresholds, failure handling
references/style-presets.md           presets, font stack, export presets, limits
```

Python ≥ 3.8, standard library only. Optional external renderers are probed at runtime:
`soffice`/`libreoffice`, `rsvg-convert`, `pdftoppm`, `gs`. Fonts: text is written with the
fallback stack `Helvetica → Arial → Noto Sans CJK SC → DejaVu Sans`, so Chinese labels survive
when a CJK font is installed and stay editable in the SVG either way.

## 14. Maintenance

* New chart type → add the mark branch in `main.render()` and a matching legend encoding; keep
  the ids `bar-*` / `pt-*` so `content_map` stays compatible.
* New workorder key → add it to `toolkit.spec()` and document it in
  `references/chart-workorder-schema.md`.
* New check → compute it in `toolkit` (`gcheck` / `lcheck` style) and surface it under
  `compliance_checks`; never silently drop a failing check.
* Changing the palette or presets is a versioned change: bump `version` and note it here.
