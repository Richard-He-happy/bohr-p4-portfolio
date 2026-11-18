---
name: academic-slides-from-paper
description: Turn a research paper (PDF/DOCX/TXT/MD) plus an optional organizer PPTX template into an editable, template-inheriting academic deck (.pptx with real speaker notes), a PDF preview, and a page-level audit trail - page_golden.json, page_diff.md, run.log, export_check.json, template_check.json, version_history.md and a contract-complete result.json whose every slide carries verbatim evidence (quote + locator). Use for 论文转汇报 / academic slide generation / deck editing and adaptation / 模板套版 / evidence-mapped presentation build.
version: 2.0.0
---

# Academic slides from a paper (slides-02)

## 1. Purpose and boundaries

Build one openable, editable deck that argues the paper's main line: page roles, page order,
per-slide claim, cited figures, speaker notes, template inheritance, and page-level evidence —
plus the audit trail that lets someone else re-check those claims without re-reading the deck.

Suitable for group meeting, 答辩/中期, project review and 开题 style talks with a fixed template.

Not in scope: paper comprehension or peer review, statistical re-analysis, chart design from raw
pixels, prose polishing, PPT application development. No fabricated numbers: every body bullet is
a verbatim substring of a sentence found in the source text.

## 2. Runtime contract

- Entry: `python3 scripts/main.py --input /input --output /app/output [--work /app/work] [--slides N] [--template X.pptx] [--no-pdf]`
- Optional v2 switches (the v1 call above still works unchanged):
  `--reuse-plan <plan_v0.json>` replay a recorded page skeleton, `--no-golden` produce only the v1
  outputs, `--legacy-sections` restore the v1 section labelling.
- Modules: `scripts/main.py` (CLI + orchestration), `scripts/discover.py` (input discovery, contract
  echo), `scripts/build.py` (page planning, OOXML packaging), `scripts/deckkit.py` (readers, sentence
  analysis, shapes), `scripts/gold.py` (golden standard, diff, version history),
  `scripts/checks.py` (export/render and template inspection). Resource:
  `references/deck-parts.json` (OOXML shells + builtin design). Every path is resolved from
  `Path(__file__).resolve().parent`, never from the CWD.
- Inputs: `/input/case.json`, `/input/task.md`, `/input/material.json`, `/input/artifacts/*.json`,
  any PDF/DOCX/TXT/MD, optional `template*.pptx` / `starting*.pptx`.
- Outputs (in `--output`): `presentation.pptx`, `presentation.pdf`, `result.json`, `run.log`,
  `plan_v0.json`, `page_golden.json`, `page_diff.md`, `export_check.json`, `template_check.json`,
  `version_history.md`.
- Stdlib only, offline, no third-party hard dependency. Exit code is always 0. A partial
  `result.json` is written before any heavy work and overwritten at the end.

## 3. Input discovery (semantic, not fixed keys)

1. `case.json` is read as a dict (or the first dict of a list); on parse failure the run continues
   with `{}` and records `NO_CASE_JSON`.
2. `output_contract` is captured verbatim (list or dict) and every key is echoed back under its own
   spelling through an alias table (`editable_source`≈`deck`/`pptx`, `export_artifact`≈`pdf`/`render`,
   `content_map`≈`slide_map`, `compliance_checks`≈`checks`, `exceptions`≈`issues`, plus the v2 keys
   `page_golden`, `page_diff`, `version_history`, `export_check`, `template_check`). Values are never
   renamed; a key with no produced value is `null`/`[]` and is listed in
   `compliance_checks.contract.unknown_keys`.
3. Workorder: `artifacts/slide-workorder.json`, `workorder.json`, or any JSON carrying
   `slide_count`/`total_slides`/`slide_spec`; it yields slide count, `mode`, `source_preservation`,
   `template_inheritance`, language, audience, footer, template name and the edit scope. Those four
   contract fields are echoed in `compliance_checks` and `runtime`/`editable_source.mode`.
4. Material scan by extension **and** magic bytes (`%PDF`, `PK`+`.pptx/.docx/.xlsx`, text, images).
   Labels are never trusted over file content.
5. Anything not supplied is listed in `pending_human` instead of being invented (no template, no
   figure, no caption, no page count).

## 4. Output contract (`result.json`)

Root keys: `case_id`, `status` (`ok|partial|insufficient_evidence`), `editable_source`,
`export_artifact`, `content_map`, `compliance_checks`, `exceptions`, plus `errors`, `degradations`,
`pending_human`, `uncertainty`, `sources`, `changes`, `runtime`, and the v2 fields `page_golden`,
`page_diff`, `version_history`, `export_check`, `template_check`, plus every key of the input
`output_contract`.

| Field | Content |
|-|-|
| `editable_source` | path, format, bytes, sha256, slides, slide_size_emu, mode, template_source (`template:<name>` / `starting-deck:<name>` / `builtin-default`) |
| `export_artifact` | path, format, pages, bytes, method, degraded |
| `content_map[i]` | slide_index, role, title, layout, notes, bullets[{text, quote, locator, verified, kind}] (`kind=source` carries a quote, `kind=front_matter` is workorder metadata) |
| `compliance_checks` | mode, source_preservation, template_inheritance, slide_count, page_order, template, notes, text_fit, figures, evidence, export, contract, overall_pass |
| `page_golden` | path + rules_version + source fingerprint + `deck` (headline numbers, figure/table numbers, sections) + `pages[]` (role, expected sections, bullet range, required numbers, required citations, claim expectation) |
| `page_diff` | path, overall, pages_pass/partial/fail, hard_gaps, soft_gaps, headline_coverage, per_page verdicts, gaps[] |
| `export_check` | path, overall_pass, verdict, pdf_pages, slides, fonts, font_substituted, overflow_violations, checks[] |
| `template_check` | path, source, inherited, overall_pass, passes/fails/warns/na, failures[], checks[] |
| `version_history` | path, package_version, rollback[], records[] (one per executed step) |
| `exceptions[]` | `{code, stage, detail}` (+`action` for export) |

## 5. Core flow (what the script actually does)

1. Discover case/material/workorder/template; write the partial `result.json` first.
2. Extract text: `pdftotext -layout` when available, else a stdlib FlateDecode/`Tj-TJ` reader; DOCX
   via `word/document.xml`; TXT/MD directly. Page index is kept for locators.
3. Split sentences (≥45 Latin chars, ≥18 Han chars) and label each with the section of its **own
   position** (Abstract/Intro/Related/Methods/Results/Discussion/Conclusions/Limitations, English
   headings and Chinese 摘要/引言/方法/结果/讨论/结论/局限). A heading is a ≤6-word line that starts
   with a section word; the title block before the first heading is skipped.
4. Plan pages (v0 skeleton, written to `plan_v0.json`): title → outline → background → question →
   methods → results×k → discussion → limitations → conclusion → thanks. Each role draws sentences
   from its own section contract, anchored on its primary section; a section still owed to a later
   role is reserved, and (strict mode) a page keeps to its own sections rather than borrowing.
5. Pre-register the golden standard (`page_golden.json`) from the plan and the source inventory,
   before any slide XML exists.
6. Build shapes: title 32/30 pt, body 20→12 pt auto-shrunk by a line-fit model, footer 10 pt in the
   template `ftr` slot when the layout has one; run-level `a:latin` set to the template's major/minor
   theme font so PowerPoint and the PDF export agree; the first results page carries an embedded
   original figure when the PDF has one.
7. Write the .pptx by regenerating `presentation.xml`, slide/notes parts and relationships while
   copying the template's master, layouts, theme, media and notesMaster; slide size follows the
   template (16:9 or 4:3).
8. Export PDF with `soffice --headless`; on failure record `PDF_RENDER_UNAVAILABLE` and leave
   `export_artifact: null`.
9. Audit: every source bullet's `quote` must be a verbatim substring of the extracted source;
   failures become `QUOTE_UNVERIFIED` and stay visible.
10. Inspect the produced files: `export_check.json` (header, page count, fonts, rendered text boxes,
    pictures) and `template_check.json` (size, master, layouts, theme fonts/colours, placeholder
    binding, footer, notes master, media).
11. Diff the delivered deck against the golden standard → `page_diff.md`; write
    `version_history.md` and `run.log`; finalize `result.json`.
12. `status` is `ok` only when every bullet verifies, the PDF exists and no page hard-fails its
    golden standard; `insufficient_evidence` when no usable source text was found (a 3-page notice
    deck is still written); otherwise `partial`.

## 6. Quality rules (rubric → field / check / artifact)

| Rubric item | Where it is satisfied |
|-|-|
| Task completion: openable deck, page order, roles, notes, export | `editable_source.slides`, `compliance_checks.page_order`, `.notes`, `export_artifact`, `page_diff` |
| Correctness: numbers/captions/citations match the paper | verbatim `quote` + `locator` per bullet, `compliance_checks.evidence`, `page_diff` numbers/citations columns |
| Completeness: main line, page structure, figure citation, notes logic, template, render | `content_map` roles, `figures`, `template`, `export`, `page_golden.deck` |
| Verifiability: source, page gold, export, diff, logs, version | `sources`, `content_map`, `page_golden.json`, `page_diff.md`, `export_check.json`, `template_check.json`, `run.log`, `version_history.md` |
| Usability / stability / exceptions | single CLI, no CWD dependency, `exceptions`/`degradations`/`pending_human`, notice deck on empty input |
| Reuse | `references/deck-parts.json` (page skeleton), `references/golden-and-checks.md` (golden + check schema), role plan |

## 7. Evidence and locator rules

- Bullet text is a verbatim prefix of a source sentence; `quote` is the full sentence (never
  rewritten, never rounded, never re-numbered).
- Locator format: `<source file> p.<page> <section>` (e.g. `paper.pdf p.3 results`). The section is
  the heading in force at that sentence, so a methods page cites `methods`, not the last heading of
  the document.
- Numbers keep the source notation (`27 percent`, `4.8 mg per square metre per day`, `p < 0.01`,
  `27%`); no unit conversion, no rounding, no translation of a figure.
- Figures are cited as embedded originals (labelled `not redrawn`); captions are quoted, never
  re-invented. A results page that reports a figure carries the sentence that names it.
- A bullet that cannot be verified is reported, not silently edited.

## 8. Conflicts and human confirmation

Stop and list in `pending_human` when: no template was supplied (`builtin-default` is used), the
workorder's slide count is unreachable from the available sentence pool, the PDF has no text layer
(scanned), or an edit workorder implies slide deletion whose scope is unclear. Never guess a page
count, a figure value or a template slot.

## 9. Budget and checkpoints

Written for the 64-request / 900 s / 16384-token envelope: no model calls inside the script, one
process, one PDF conversion (≤280 s timeout), roughly 5–16 s end-to-end for a 10–12 slide deck on a
2-core runtime. Partial `result.json` after discovery, `plan_v0.json` after planning, `run.log` after
every step. If the run dies, the exception handler rewrites `result.json` with `status: partial` and
the traceback and still flushes `run.log`.

## 10. Failure and degradation table

| Situation | Behaviour |
|-|-|
| `case.json` missing/corrupt | `NO_CASE_JSON`, continue, contract keys = 0, notice deck |
| No source text (<4 sentences) | `LOW_SOURCE_TEXT` + `INSUFFICIENT_INPUT`, 3-slide notice deck, `status: insufficient_evidence` |
| No template | builtin 16:9 design from `references/deck-parts.json`, `pending_human`, `template_check` marks inherited items `n/a` |
| Template unreadable | `degradations.template`, builtin design, `template_check.template_readable = warn` (inheritance not verified) |
| mode=edit/adapt but no starting deck | `EDIT_WITHOUT_STARTING_DECK`, degraded to generate |
| `soffice` missing/failing | `PDF_RENDER_UNAVAILABLE`, `export_artifact: null`, pptx kept, `export_check.overall_pass = false` |
| PDF has no text layer | text extraction returns little → `LOW_SOURCE_TEXT` (no OCR) |
| No embedded JPEG figure | `figures.embedded_from_source: 0`, text-only slides, `figure_placement: not_available_in_source` |
| Sentence pool exhausted | `POOL_EXHAUSTED`, slide dropped, count reported in `slide_count` and `uncertainty` |
| Text overflow | font auto-shrinks to 12 pt; residual overflow listed in `text_fit.overflow_slides` and by real word boxes in `export_check.text_overflow` |
| Template font not installed | `export_check.fonts.substituted` lists the PDF font, `fonts_inherited = warn`, `overall_pass` unaffected |
| Han text in the deck | CJK glyph fallback is reported as `cjk_fallback`, not as a substitution |
| `--reuse-plan` with a stale plan | `PLAN_REUSE_MISS` / `PLAN_REUSE_INVALID`, pages rebuilt from what matched |

## 11. Self-check before delivery

`python3 -B scripts/main.py --help` exits 0; `result.json` parses and holds every contract key;
`content_map` length equals `editable_source.slides`; `compliance_checks.evidence.verified == bullets`;
`presentation.pdf` page count equals slide count; `page_diff.md` lists every page; `run.log` has a
line per step; open the pptx in PowerPoint/LibreOffice and confirm the notes pane and theme font.

```bash
python3 -B scripts/main.py --input /input --output /app/output      # full run
python3 -B scripts/main.py --help                                   # interface only
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['status'],r['page_diff']['overall'])"
```

## 12. Minimal call example (example, not a formal case result)

Input `case.json`: `{"case_id": "DEMO-1", "output_contract": ["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"]}`
with `paper.pdf` (4 pages) and `artifacts/slide-workorder.json` =
`{"slide_count": 10, "language": "en", "footer": "Group meeting"}`.

```
python3 scripts/main.py --input /input --output /app/output
```

Illustrative output: 10 slides, 20–30 bullets, all verified, `export_artifact.pages = 10`,
`page_diff.overall = PASS`, `status: ok`. These numbers describe the interface only; they are not a
benchmark score, and a different paper produces different counts and different gaps.

## 13. Files and versions

```
SKILL.md                        this file (spec + usage)
scripts/main.py                 CLI, orchestration, step log             ~23 KB
scripts/discover.py             input discovery, output dir, contract    ~6 KB
scripts/build.py                page planning, plan replay, OOXML packing ~11 KB
scripts/deckkit.py              readers, sentence/section analysis, shapes ~25 KB
scripts/gold.py                 golden standard, diff, version history   ~22 KB
scripts/checks.py               export/render and template inspection    ~19 KB
references/deck-parts.json      OOXML shells + builtin design (reusable)
references/slide-planning.md    role taxonomy, ordering, budgets, edit policy
references/result-and-checks.md result schema, locator grammar, exception codes
references/golden-and-checks.md page_golden / page_diff / export_check / template_check schema
```

Version 2.0.0 (patch over 1.0.0), Python 3.9+ (stdlib only), no network, no credentials, no CWD
assumption. The module split replaced a single 36 KB main so each file stays reviewable.

## 14. Maintenance

Change role rules in `build.RULES` / `dk.roles`, sentence scoring in `dk.score`, section contracts and
bullet ranges in `gold.ROLE_SPEC`, geometry/typography in `dk.slide_shapes`, template slot logic in
`dk.read_template` plus `checks.template_check`, export inspection in `checks.export_check`. Static
XML belongs in `references/deck-parts.json`, not in code. After any change re-run the battery in §11
on (a) an English paper, (b) a Chinese paper, (c) a case with an organizer template, (d) an empty
input, and confirm `page_diff.md` still discriminates a good deck from a bad one
(`--legacy-sections` reproduces the pre-v2 labelling and must show section gaps).
