# Style presets and export presets

## Typographic presets (`toolkit.STY`)

All values are in canvas px on a 96 dpi layout; the canvas is declared in millimetres in the SVG
(`width="170mm"`), so 1 px ≈ 0.265 mm (fonts ≈ 6.5–7.5 pt at print size).

| preset | font | small | line | axis | grid | bar gap | group gap | title |
|---|---|---|---|---|---|---|---|---|
| `default` | 9.0 | 7.0 | 1.0 | 0.9 | 0.4 | 0.18 | 0.12 | 11.0 |
| `journal` | 8.0 | 6.5 | 0.9 | 0.8 | 0.35 | 0.15 | 0.10 | 9.0 |
| `nature` | 7.0 | 6.0 | 0.8 | 0.7 | 0.30 | 0.12 | 0.08 | 8.0 |
| `thesis` | 10.5 | 8.5 | 1.1 | 1.0 | 0.5 | 0.22 | 0.15 | 12.0 |
| `presentation` | 13.0 | 10.0 | 1.4 | 1.2 | 0.6 | 0.26 | 0.18 | 16.0 |

`--style` accepts any of these names (substring match, case-insensitive); unknown names fall back
to `default` and the chosen name is echoed in `compliance_checks.line_widths` context and
`changes`.

## Palette

Colour-blind-safe Okabe–Ito derived set, bound to series in table order:

`#0072B2` · `#D55E00` · `#009E73` · `#CC79A7` · `#E69F00` · `#56B4E9` · `#8C6D1F` · `#333333`

Series beyond eight reuse the palette cyclically; the marker shape list (`o s ^ D v P X *`) keeps
them distinguishable. Legend swatches are rectangles for bars and circles for line/scatter, from
the same colour list, so legend and marks cannot drift apart.

## Fonts

```
Helvetica, Arial, 'Noto Sans CJK SC', 'DejaVu Sans', sans-serif
```

Text stays as `<text>` in the SVG and is rendered by the PDF engine with the same stack, so CJK
labels remain editable and are never converted to outlines. If no CJK font exists on the machine,
the SVG still holds the correct code points (`cjk_in_figure: true` records the intent) — install
`fonts-noto-cjk` for pixel-identical previews.

## Export presets

| output | route (in order) | parameters |
|---|---|---|
| `chart.svg` | written directly | `width/height` in mm, `viewBox` in px, UTF-8, no external references |
| `chart.pdf` | `soffice --convert-to pdf` → `rsvg-convert` | one page, vector, embedded font, `MediaBox` = figure size |
| `chart.png` | `pdftoppm -r <dpi>` → `gs -sDEVICE=png16m -r<dpi>` | 8-bit RGB, `dpi` from the workorder (default 300), true raster of the vector figure |

Degradations are recorded per engine in `degradations` and in `runtime.log`
(`pdf_engine=…`, `png_from_pdf=…`, `pdf_fail=…`). A missing renderer never produces a renamed
placeholder file.

## Limits

* One axes per figure; multi-panel workorders are flattened and flagged.
* Bar / grouped bar (wide and long format), line, scatter. Heatmap, box, violin, pie degrade to
  bars with `chart_type_unsupported`.
* Bar charts start at 0 unless the workorder gives `axis.y.limits`; negative values are drawn
  below the zero baseline.
* Log axes skip non-positive values (recorded), and fall back to linear when no positive value
  exists.
