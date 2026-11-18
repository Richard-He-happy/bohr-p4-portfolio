# page_golden / page_diff / export_check / template_check — schema and semantics

Companion to `SKILL.md` §5–§6. Everything here is produced by `scripts/gold.py` and
`scripts/checks.py` at run time; no value in these files is typed in from memory.

## 1. `page_golden.json` — the page-level golden standard

Built from the page plan **before** any slide XML exists, so the diff compares a pre-registered
expectation with the delivered deck rather than with itself.

```json
{
 "rules_version": "goldenv1",
 "generated_at": "<UTC stamp>",
 "case_id": "<from case.json>",
 "source": {"label": "paper.pdf", "fingerprint": "<sha256 of the sentence pool>", "sentences": 31},
 "deck":  {"headline_numbers": [{"token": "<token>", "kind": "percent", "locator": "paper.pdf p.1 abstract"}],
           "figure_numbers": [2], "table_numbers": [1],
           "sections_available": {"abstract": 6, "methods": 5, "results": 5},
           "pages": 10, "requested": 10, "roles": ["title", "..."], "extraction": "pdftotext -layout"},
 "pages": [
   {"page": 6, "role": "results", "title": "Results 1",
    "narrative_job": "one measured claim per page, with its number",
    "expected_sections": ["results", "abstract"], "declared_sections": ["results", "abstract"],
    "section_contract_available": true, "labels_collapsed": false,
    "bullet_range": [1, 4],
    "numbers_required": [{"token": "<token>", "kind": "percent", "locator": "paper.pdf p.1 results"}],
    "min_numbers": 1,
    "citations_required": [{"kind": "figure", "n": 2, "locator": "paper.pdf p.1 results"}],
    "figure_placement": "required", "citation_duty": "results",
    "claim_expectation": "each results page carries at least one verbatim number",
    "planned_quotes": ["..."]}
 ]
}
```

`rules_version` names the rule table below; `source.fingerprint` proves which text the golden standard
was built from, so a stale `page_golden.json` is visible immediately.

### 1.1 Role contracts (`gold.ROLE_SPEC`)

| role | narrative job | sections it must draw from | bullets | verbatim numbers | figure/table |
|-|-|-|-|-|-|
| `title` | paper identity + audience framing | – | 1–3 | 0 | – |
| `notice` | input incomplete, name what is missing | – | 1–4 | 0 | – |
| `outline` | navigation only | – | 3–12 | 0 | – |
| `background` | why the problem matters | abstract, intro, related | 1–4 | 0 | optional |
| `question` | the single question answered | abstract, intro | 1–3 | 0 | – |
| `methods` | design, data, analysis window | methods | 1–4 | at least 1 | optional |
| `results` | one measured claim per page | results, abstract | 1–4 | at least 1 | duty of the first results page |
| `discussion` | what the results mean | discussion, results | 1–4 | 0 | optional |
| `limitations` | scope and boundary | limits, discussion | 1–4 | 0 | – |
| `conclusion` | what to remember | conclusion, abstract | 1–4 | at least 1 | – |
| `thanks` | close | – | 0–2 | 0 | – |

Numbers are harvested from the source with six patterns (`pvalue`, `ci`, `percent`, `temperature`,
`quantity`, `decimal`) and ranked by weight; the per-page list holds at most three distinct tokens from
that role's sections. A figure/table number is owed by **one** page: the first page whose primary
section mentions it (`citation_duty`), so two results pages are not both asked to cite Figure 2.

### 1.2 What can make a page fail

- `sections` — no body bullet's locator lands in the declared section. If the source exposes at most
  one section label while the role declares some (`labels_collapsed`), the check fails instead of
  silently reporting `n/a`: that is how a broken heading parser becomes visible.
- `numbers` — fewer than `min_numbers` of `numbers_required` appear in the page text (quote + display).
- `citations` — the page that owes a figure/table number does not name it.
- `bullets` — the recorded bullet/subtitle count is outside `bullet_range`.
- `evidence` — a quote is not a verbatim substring of the extracted source.
- `overflow` — the line-fit model reports more than 1.0 utilization.

`role`, `bullets`, `evidence`, `overflow` are **hard** (page verdict `FAIL`); `sections`, `numbers`,
`citations` are **soft** (page verdict `PARTIAL`). Page `PASS` = no gap at all.

## 2. `page_diff.md` — the per-page comparison

Sections: summary (pass/partial/fail, gap counts, headline-number coverage, figure/table coverage),
one row per page, one table per page (check | expected | actual | verdict | evidence), a numbered gap
index, and a reproduction block. It is written from `page_golden.json` + `result.json.content_map`
only, so anyone can recompute it; timestamps are the only non-deterministic fields.

`result.json.page_diff` carries the machine-readable summary (verdicts, gap list, headline coverage).

## 3. `export_check.json` — what the rendered PDF really contains

| check id | item | how it is measured |
|-|-|-|
| `pdf_header` | file starts with the PDF signature | first bytes + sha256 |
| `page_count` | PDF pages = slide count | `pdfinfo Pages` (fallback: `/Type /Page` count) |
| `fonts_embedded` | every font is embedded | `pdffonts` `emb` column |
| `fonts_inherited` | PDF families match the template theme | `pdffonts` names vs theme typefaces, through a metric-alias table (Arial with Liberation Sans/Arimo, Calibri with Carlito, …) and a CJK-fallback table (Noto, Source Han, SimSun, …); a real substitute is `warn`, a CJK glyph fallback is informational |
| `text_overflow` | no word crosses the page box | `pdftotext -bbox-layout` per word: `xMax > width-1` or `yMax > height-1` or a negative origin; also reports the modelled utilization |
| `figures_rendered` | every placed picture reaches the PDF | `/Subtype /Image` XObject count vs `figures.placed` |

`overall_pass` is true only when no check is `fail`; a font substitution is a `warn` (recorded, with
the offending font names, but the deck is still deliverable).

## 4. `template_check.json` — did the deck inherit the organizer template

| check id | item | evidence |
|-|-|-|
| `template_readable` | supplied template opens as an OPC package | warn when unreadable, inheritance not verified |
| `slide_size` | `p:sldSz` equals the template | EMU pair |
| `master` | master part byte-identical to the template | sha256 pair |
| `layouts_resolved` | every slide points at an existing layout part | per-slide layout list |
| `layouts_inherited` | layouts used are the template's, unmodified | sha256 match count |
| `theme_part` | theme part byte-identical | sha256 pair |
| `theme_fonts` | theme font scheme unchanged | typeface lists |
| `theme_colours` | colour scheme unchanged | srgbClr value sets |
| `no_local_colour_override` | slide bodies carry no hard-coded colour | literal colour list |
| `placeholder_binding` | every slide placeholder exists in its layout | bound/unbound count |
| `footer_slot` | footer uses the template `ftr` placeholder | per-slide ftr presence, layouts exposing ftr |
| `footer_text` | footer string equals the workorder text | slides carrying it |
| `notes_master` | notes master present | part list |
| `media_copied` | template media preserved | part counts |

Status vocabulary: `pass` / `fail` / `warn` (recorded, not blocking) / `n/a` (nothing to inherit, e.g.
a builtin design). `overall_pass` ignores `warn` and `n/a` and fails on `slide_size`, `master`,
`layouts_resolved`, `theme_fonts`, `theme_colours`, `placeholder_binding`, `notes_master`.

## 5. `plan_v0.json` and rollback

`plan_v0.json` = `{version: "v0", roles[], requested, pages:[{index, role, title, quotes[]}], sha256}`
written after planning and before the file build. `--reuse-plan` replays it: quotes are matched back
to the current sentence pool, cover/outline/closing lines are re-filled from the workorder, and a
missing quote raises `PLAN_REUSE_MISS` instead of silently producing a different deck.

| target | command | effect |
|-|-|-|
| v0 skeleton | `--reuse-plan <out>/plan_v0.json` | rebuild from the recorded plan, no re-planning |
| v1 behaviour | `--no-golden` | only the v1 fields and files |
| v1 section labels | `--legacy-sections` | one label per page (the pre-v2 bug) |
| v1 package | restore the v1 `scripts/main.py` and `scripts/deckkit.py` from `baseline_v1.zip` (hashes in section 6 of this file), drop `gold.py` and `checks.py` | byte-level rollback |

`--legacy-sections` is the regression switch: on the same input it must reproduce the section gaps
that the v2 labelling fixed, which is the cheapest proof that the diff is not decorative.

## 6. Version hashes (computed, not typed)

See `version_history.md` inside each output directory, and run
`sha256sum scripts/*.py` in the package root to confirm the files you hold. The parent package
`baseline_v1.zip` holds v1.0.0 (`scripts/main.py`, `scripts/deckkit.py`); this package adds
`discover.py`, `build.py`, `gold.py`, `checks.py` and modifies the two v1 scripts, so a byte-level
rollback means restoring those two files and deleting the four new ones.
