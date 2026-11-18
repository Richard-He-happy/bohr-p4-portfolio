# Drawing workorder schema (`workorder_type: source_value_chart`)

The skill never assumes key names. Each field below is resolved by exact key match first, then
by substring match over the whole workorder dict (`toolkit.spec`). Unmatched fields stay `None`
and are reported in `uncertainty` / `exceptions`.

## Field binding

| spec key | accepted workorder keys | meaning / default |
|---|---|---|
| `t` | `chart_type`, `figure_type`, `chart` | `bar` \| `column` \| `line` \| `scatter`; empty ⇒ inferred from table shape |
| `x` | `x`, `x_field`, `x_column`, `category` | x column (text or numeric) |
| `y` | `y`, `y_fields`, `y_columns`, `value_column`, `data_columns` | one name or a list; empty ⇒ all numeric columns except `x` |
| `sc` | `series_field`, `series_column`, `grouping` | long-format grouping column (each value becomes a series) |
| `ec` | `error_bar.source_column`, `column`, `field` | error column; otherwise matched by header stem (`p-Actin SD` → `p-Actin`) |
| `em` | `error_bar.mode` (`sd`, `sem`, `ci95`) | transmitted verbatim into `error_mode`, never recomputed |
| `xl`,`yl` | `x_label`/`xlabel`, `y_label`/`ylabel`, `axis.x.label`, `axis.y.label` | axis titles; fall back to the header label |
| `xu`,`yu` | `x_unit`, `y_unit`, `axis.y.unit` | units; fall back to the unit inside the header |
| `ysc` | `axis.y.scale` | `linear` (default) \| `log` |
| `ylim` | `axis.y.limits`, `y_limits` | `[min, max]` override |
| `wm`,`hm` | `export.width_mm`, `height_mm` | figure size; default 170 mm × 62 % |
| `dpi` | `export.dpi` | PNG resolution, default 300 |
| `st` | `style`, `style_preset`, `template` | preset name (see `style-presets.md`); default `journal` |
| `tb` | `source_table_ref`, `source_table` | file name (or fragment) to use as the data table |

## Unit handling

`split_header("Concentration (mg/L)")` → `("Concentration", "mg/L")`. Also recognises `[...]`.
If no unit exists in header or workorder the axis is labelled `… (unit not reported)` and an
`unit_unknown` exception is raised — no unit is ever guessed, converted or appended.

## Error bars and significance

* Error values are read from the matched error column row-by-row; `error_raw` keeps the source
  string. A failed parse drops only that bar (`error_value_unparsable`).
* `significance_marks` are **not drawn** by this skill: they carry statistical claims the skill
  cannot verify (see `annotations_not_drawn` in older versions / out-of-scope statement in
  `SKILL.md §1`). They are kept in the model only if a source locator is supplied.

## Multi-panel and other types

`panels` / `panel_layout` is parsed but rendered as a single axes; all series are kept and the
flattening is recorded (`panels_flattened`). Heatmap / box / violin / pie requests degrade to
bars with `chart_type_unsupported`, never to fabricated geometry.

## Example

```json
{"workorder_type": "source_value_chart",
 "chart_type": "grouped_bar",
 "x": "Treatment", "y": ["p-Actin", "p-ERK1/2"],
 "error_bar": {"mode": "sd"},
 "axis": {"y": {"label": "Normalized intensity", "unit": "a.u.", "scale": "linear"}},
 "legend_title": null,
 "export": {"width_mm": 170, "dpi": 300, "formats": ["svg", "pdf", "png"]},
 "style": "journal",
 "source_table_ref": "figure3_source.csv"}
```
