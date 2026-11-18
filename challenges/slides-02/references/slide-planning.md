# Slide planning rules (roles, order, budgets, edit policy)

Companion to `SKILL.md`; used by `dk.roles`, `RULES` in `scripts/main.py`, and `dk.slide_shapes`.

## 1. Role taxonomy
| role | narrative job | source preference | bullets |
|-|-|-|-|
| `title` | paper identity + audience framing | case/workorder metadata, else first PDF line | subtitle lines only |
| `outline` | navigation, no data | role names of the deck | one line per section |
| `background` | why the problem matters | abstract, intro (gap/need/challenge keywords) | 3 |
| `question` | the single question answered | abstract, intro (`we ask/aim/investigate`) | 2 |
| `methods` | design, data, analysis window | methods/experimental | 3 |
| `results` (×k) | one claim per page, numbers included | results, abstract (digit boost) | 3 |
| `discussion` | what the results mean | discussion/results (`suggest/indicate/consistent`) | 3 |
| `limitations` | scope and boundary | limitations/discussion (`only/further/warrant`) | 3 |
| `conclusion` | what to remember | conclusion/abstract (`overall/in summary`) | 3 |
| `thanks` | close | fixed credit line | 1 |

Order is fixed: title → (outline if ≥8 slides) → background → question → methods → results×k → discussion → limitations → conclusion → thanks. Trimming order when the requested count is small: limitations → outline → question → discussion → background.

### 1.1 Sentence selection (v2)

`dk.pick` combines four guards, each of which the page diff can check:

1. **strict** — while the page's own sections still hold enough unused sentences, candidates are
   restricted to them, so a "methods" page cannot be filled with results sentences.
2. **anchor** — the page named after a section carries at least one line from it.
3. **reserve** — a section that a later role names in its contract (`results`, `discussion`,
   `limits`, `conclusion`, `methods`, `abstract`, `intro`) is withheld from earlier pages, so one
   results page cannot swallow the only conclusion sentence.
4. **must** — a results page swaps in the sentence that names its figure/table when none of the picks
   cite one, so the numbers on the slide and the figure number agree.

If every guard still leaves the page short, the whole pool is used and the shortfall is visible in the
diff as a `sections` or `numbers` gap rather than being hidden.

## 2. Count and time budget
- Requested count comes from the workorder (`slide_count`/`total_slides`), else `--slides`, else 10–12 by source length.
- Clamp 3–30. A 15-minute talk is 10–14 slides; a 5-minute pitch is 6–8.
- If the sentence pool cannot fill the count, slides are dropped and the shortfall is reported in `uncertainty` and `compliance_checks.slide_count`, never padded with invented text.

## 3. Text budget per slide
- Title ≤ 92 characters (clipped at word boundary with `…`); a markdown `#` prefix and a trailing rule are stripped, and the title block before the first section heading never becomes a bullet.
- Body: 3 bullets by default; ≤ 118 characters per bullet; verbatim prefix of the source sentence. `page_golden.json` fixes the allowed range per role (title 1–3, outline 3–12, content pages 1–4, closing 0–2).
- Sentence threshold: ≥45 Latin characters, or ≥18 Han characters for Chinese sources.
- Font ladder 20/18/16 pt shrinks by 1 pt steps to 12 pt while the line-fit model reports > 1.0 utilization; residual overflow is listed, not hidden, and the rendered word boxes are measured again in `export_check.json`.
- Footer carries the source credit line; it uses the template `ftr` slot when the layout provides one.

## 4. Figure policy
- Only figures already embedded in the PDF (JPEG/DCTDecode) are placed, on the first results page, labelled `embedded original figure (not redrawn)`.
- No curve, chart, or caption is synthesised. If the paper only has vector figures, the deck stays text-only and `figures.embedded_from_source = 0` records it.
- Images that are bitmaps of data are never re-digitised; that is a separate task.

## 5. Template policy
- Template master, layouts, theme, media and notesMaster are copied; slide size (16:9 or 4:3) is inherited.
- Each slide picks a layout whose placeholders match its role (`ctrTitle` for the cover, `title`+`obj|body|tx` for content).
- The script writes explicit geometry inside the safe area so a template with sparse placeholders still yields a non-collapsing page; theme fonts and colours are inherited, not overridden.

## 6. Edit / adaptation mode
When a starting deck is supplied (`starting*.pptx`) or the workorder mentions edit/adapt:
1. Design (master, layouts, theme, footer slot) is inherited from the starting deck.
2. Slide bodies are rebuilt from the source under the same role plan; the old text is not pasted through.
3. `changes[0].diff_vs_starting_deck` states `design inherited, bodies rebuilt`, and `editable_source.template_source` records `starting-deck:<name>`.
4. Deletions or reordering that the workorder does not authorise are reported in `pending_human` before execution.

## 7. Notes policy
Every slide gets 1–3 note lines: role, locator of the quoted sentences, the opening claim, and a bridge to the next slide. Notes are explicitly labelled as speaking prompts — they are not paper text and must not be quoted as evidence.

## 8. Rejection rules (never do)
- Do not copy abstract paragraphs into a text box; select sentences per role instead.
- Do not round or reformat numbers (`27 percent` stays `27 percent`).
- Do not place a placeholder rectangle or generated curve where a paper figure belongs.
- Do not change template colours, fonts, or footer style; do not edit master/layout parts.
- Do not exceed the requested slide count to "fit everything".
