# Validation checklist

Run after every generated figure; each item maps to a field of `result.json`.

## Machine checks (written by `toolkit`)

| check | field | pass condition |
|---|---|---|
| geometry round-trip | `compliance_checks.geometry_roundtrip` | for each bar: `h_px/span*(hi-lo)+base` returns the source value within 2 % of `|value|`; `mismatch_count == 0` |
| legend alignment | `legend_consistency` | `legend_items == series == distinct_colors`, plus the label→colour→series map |
| coverage | `content_coverage` | `required == mapped`, `missing == []` or each id explained by an exception |
| canvas | `canvas` | `width_mm/height_mm` as requested, `width_px = mm*96/25.4`, `dpi` recorded |
| fonts | `fonts` | family stack recorded, `text_elements > 0`, `text_kept_as_text: true`, `cjk_in_figure` flags CJK labels |
| line widths | `line_widths` | preset values (data / axis / grid) actually used |
| colours | `colors` | palette list, distinct count, colour-blind-safe palette |
| overflow | `canvas_overflow` | `x_labels_rotated` set when labels exceed 46 px; layers enumerated |
| PNG | `png` | magic bytes `89 50 4E 47`, IHDR geometry, `ink_present` when ImageMagick is available |
| PDF | `pdf` | `%PDF-` header, `pages ≥ 1`, embedded font, `text_preserved` |

`compliance_checks.pass` is the AND of these; `failures` lists the failing slugs
(`legend_series_mismatch`, `geometry_mismatch`, `coverage_incomplete`, `png_blank`, `pdf_missing`).

## Manual checks

1. Open `chart.svg` in a browser or vector editor: each `<g id="layer-…">` is a separate layer
   (background, title, axes, data, error, legend, labels) and every label is selectable text.
2. Compare two or three bars by eye against their `content_map` values and `source.quote`.
3. Check the axis unit against the source header; if `unit not reported` is printed, that is the
   intended honest state.
4. Confirm the legend order equals the table column order.
5. Open `chart.pdf` at print size (170 mm wide by default) and confirm nothing is clipped and the
   text is not converted to outlines.
6. Read `exceptions`; nothing should be silently missing.

## Failure handling priority

1. Wrong or invented numbers → stop, fix the binding; the figure is unusable.
2. Legend/series mismatch → stop, fix colour assignment.
3. Missing unit → keep the figure, keep the `unit not reported` label and the exception.
4. Skipped null points → keep, they must appear in `coverage.missing`.
5. Missing PDF/PNG → keep SVG, record the degradation; never rename a placeholder.

## Reproducibility

Same input, same flags ⇒ same `editable_source.sha256`. Changing only `--style` changes the
hash; changing the data table changes it as well. `runtime` records stage timings and the log of
the export engines that were actually tried.

## Geometry key glossary (`content_map.series[].points[].geometry`)

| key | meaning |
|---|---|
| `id` | mark id, identical to the SVG element id (`bar-s1-p3`, `pt-s2-p5`) |
| `kind` | `bar` \| `line` \| `scatter` |
| `x_px`, `y_px` | mark anchor in canvas px (96 dpi space, origin top-left) |
| `w_px`, `top`, `h` | bar width, top edge and height in px |
| `base`, `bv` | baseline position in px and the baseline *value* it corresponds to (0, or the axis minimum) |
| `pt`, `pb` | plot-box top and bottom in px (used by the reverse check) |
| `et`, `eb` | error-bar top and bottom in px |

Convert any px back to a value with `value = bv + h/(pb-pt)*(ymax-ymin)` (linear axis) — this is
exactly the expression `gcheck()` uses, so the figure can be re-verified by hand.
