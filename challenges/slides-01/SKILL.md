---
name: paper-to-academic-slides
description: Convert one research paper (PDF/DOCX/MD/TXT) plus an optional target template deck into an editable academic presentation — mainline page plan, per-slide evidence with verbatim quotes and figure/table/section locators, speaker notes kept separate from slide text, template-inheriting .pptx, real PDF export, and a result.json that fills the case output_contract. Use for 论文转学术 PPT / paper-to-slides / 学术汇报 / 组会汇报 / 会议报告 / 模板适配汇报 / deck revision from a paper.
version: 1.0.0
---

# 论文转学术 PPT（paper-to-academic-slides）

Rewrites one paper into a **page-level, evidence-anchored, deliverable** academic deck: one claim per page, each claim carrying a locator and a verbatim quote from the paper, laid out on the supplied template.

- **Input**: `/input/case.json`, `/input/task.md`, the paper (`*.pdf|docx|md|txt`), optional `artifacts/slide-workorder.json`, optional `*.pptx` target template.
- **Output** in `/app/output`: `presentation.pptx` (editable, template-inheriting), `presentation.pdf` (real render), `plan.json`, `deck_model.json`, `result.json`.
- **Dependencies**: Python 3.8+ standard library only. Optional, auto-probed, never required: `pdftotext`, `soffice|libreoffice`, `office-renderer`. No network.

## 1. Purpose and boundaries

In scope: mainline extraction, page roles and claims, figure/table reference alignment, per-page evidence mapping, speaker notes, template placeholder layout, export verification.

Out of scope: new scientific interpretation, redrawing paper figures, manuscript polishing, peer review. Nothing is added to the source: every number, unit, method name, figure/table id and claim on a slide must be traceable to the paper text.

## 2. Run contract

| Item | Value |
|---|---|
| Command | `python3 <skill>/scripts/main.py --input /input --output /app/output --work /app/work` |
| Exit code | always `0`; failures are reported inside `result.json` |
| First write | partial `result.json` (with every `output_contract` key) before any heavy work |
| Last write | unconditional overwrite of `result.json` with the finished envelope |
| Budget | ~900 s, 64 model requests; one run is a single process, no background jobs |

`--help` prints the three path options. A run takes a few seconds on a normal paper (measured: 1.9 s on the bundled fixture).

## 3. Input discovery (semantic, not key-name dependent)

1. Read `<input>/case.json`; if absent, search the input tree for `case*.json`, then continue with defaults.
2. Keep `case_id` and `output_contract` verbatim (unknown fields preserved, missing values `null`/`[]`).
3. Workorder: read from any case sub-dict containing slide keys, or from `*workorder*.json` / `slide*spec*.json` in the input tree. Fields consumed: **mode**, **total slide count**, **source preservation**, **template inheritance**, plus audience, duration, language; everything else is echoed into `deck_model.workorder.raw`.
4. Paper: first file of `pdf|docx|md|txt` larger than 1.5 kB that is not `task.md`/`README`.
5. Template: a `.pptx` whose name matches `template|master|layout|style|brand`; otherwise the first `.pptx` (a starting deck then serves as the template base). No `.pptx` → built-in master/layout/theme, recorded as a degradation.
6. Anything missing (no paper, no captions, unreadable PDF) becomes an explicit entry in `exceptions` / `pending_human`; nothing is fabricated to fill it.

## 4. Output contract

`result.json` echoes every `output_contract` key, then fills:

- `editable_source` — `{path, format:"pptx", slides, bytes, sha256, engine, notes_slides, template:{path, master, layouts_used, inherited}}`
- `export_artifact` — `{pdf:{path, pages, engine, valid}, png:{dir, count}}` (PNG is `null`/0 by design; the PDF is the render evidence)
- `content_map` — `{unit:"slide", slides:[{n, title, role, claim, bullets, evidence:[{type,id,locator,quote,matched}], assets, notes}], coverage:{slides, with_evidence, evidence_items, quotes_matched}}`
- `compliance_checks` — `slide_count`, `template_inheritance`, `overflow`, `notes_coverage`, `notes_overlap`, `figure_refs`, `number_whitelist`, `evidence_coverage`, `mode`, `fonts`, `files`, `pass`, `failures[]`
- `exceptions[]`, `degradations[]`, `pending_human[]`, `uncertainty[]`, `changes{}`, `sources{}`, `runtime{}`, `errors[]`
- `status ∈ ok | partial | input_error`

Field-level schema, quoting rules and thresholds: `references/output-schema.md`.

## 5. Core pipeline

```
discover -> extract -> parse (sentences + sections + figure/table captions)
        -> page plan (roles -> claims -> bullets -> evidence -> notes)
        -> template-inheriting pptx -> PDF export -> verify -> result.json
```

**One representation.** `deck_model.json` holds the whole deck (`slides[]`: role, title, claim, bullets, evidence, notes). `plan.json`, `content_map`, the pptx and the PDF are projections of that one model, so slide text and evidence can never drift apart. Edits belong in `deck_model.json`; re-running the script reproduces the same deck.

### 5.1 Extraction chain (engine recorded in `sources.engine`)

`pdftotext -layout -enc UTF-8` → stdlib PDF parse (inflate `FlateDecode` streams, read `Tj/TJ` strings) → DOCX/PPTX XML text → Markdown/plain text. Pages are split on form feeds, so locators carry real page numbers. Empty extraction is **never** read as "the paper is empty": it produces `status=partial`, an `exceptions` entry and no deck.

### 5.2 Mainline, not paragraph order

Roles follow the paper's contribution, not its section order: `title → motivation → approach → method → evidence (one page per figure/table) → discussion → limitation → conclusion (→ thanks)`.

The role sequence is scaled to the requested slide count by `plan(n)`: sections are dropped in a fixed priority order (limitation → discussion → method → approach → motivation) and freed slots become evidence pages. Page budgets and per-role rules: `references/page-outline.md`.

Every page carries **one claim** (a verbatim clause of the anchoring sentence, never a paraphrase that adds facts), **≤5 bullets** (verbatim prefixes of paper sentences cut at clause boundaries, so numbers and units survive unchanged), **evidence** (page + section + figure/table locator + the full sentence as quote) and **notes**.

### 5.3 Evidence, numbers and figure ids

- Every evidence `quote` is checked against the extracted text (normalised, then de-punctuated); `matched` records the result, misses appear in `compliance_checks.failures`.
- Every number/percentage on a page must occur in the paper (`number_whitelist.misses`).
- Every `Figure N` / `Table N` mentioned on a page must exist in the paper's caption list (`figure_refs.mismatch`).
- Bullets are cut, never rewritten, so "12.5%" cannot silently become "12%" or "about 13%".

### 5.4 Template and starting deck

With a `.pptx` in the input, the output **inherits** that file's `slideMasters`, `slideLayouts` and `theme1.xml` (SHA-256 compared before/after; result in `template_inheritance`). Slides are rebuilt on the layout's real placeholders (`<p:ph type idx>`), so position, size and font come from the master; the template's own slides are replaced (count in `changes`). Without a template a self-contained package is generated (master + title layout + content layout + theme + notesMaster).

### 5.5 Speaker notes

Notes are generated as an actionable pointer — `If asked, cite Figure 1, p.3; p.3 / Results. Next: What it means.` — transition plus the evidence to bring up when challenged. Notes are measured for token overlap with slide text (threshold 0.6) so they never restate the bullets.

## 6. Exception branches

| Condition | Detection | Action |
|---|---|---|
| Encrypted / scanned PDF | pdftotext empty, stdlib text < 100 chars | `partial`, `exceptions` entry, no invented text |
| No text layer | `len(text) < 200` | `status=partial`, sources recorded, no deck |
| No figure captions | caption regex finds nothing | `pending_human` asks to confirm the figure list; slides cite page/section only |
| Figure image not embedded | by design: no image is copied from the PDF | caption + `Figure N, p.X` locator cited; `assets` notes `caption+locator only` |
| No office renderer | `soffice`/`office-renderer` absent | `pdf.valid=false`, `degradations[]` entry, pptx still delivered |
| No template | no `.pptx` in input | built-in master/layout/theme, `degradations[]` entry |
| Slide count impossible | requested count < 3 | roles collapse to title/motivation/conclusion, `slide_count.ok=false` reported |
| Layout without body placeholder | placeholder scan returns none | absolute text box in the safe area; master/theme still inherited |
| Bad / missing case.json | JSON error or absent | `input_error` or `partial`, valid `result.json`, exit 0 |

## 7. Self-check

`result.json → compliance_checks` is machine-computed every run: `slide_count`, `template_inheritance` (theme/master hashes), `overflow` (≤5 bullets, ≤190 chars), `notes_coverage`, `notes_overlap`, `figure_refs`, `number_whitelist`, `evidence_coverage`, plus `files` (pptx zip members, slide count, notes count, PDF header and page count). `pass` is the conjunction. Checklist and rubric mapping: `references/checklist.md`.

## 8. Minimal call example (示例，非正式案例结果)

Input (fixture, illustrative only):

```json
{"case_id": "demo-fixture-001",
 "output_contract": ["case_id","status","editable_source","export_artifact","content_map","compliance_checks","exceptions"],
 "organizer_workorder": {"mode":"generate","total_slide_count":12,"source_preservation":"full","template_inheritance":true},
 "formal_inputs": {"paper":"paper.pdf"}}
```

Run: `python3 scripts/main.py --input ./case --output ./out --work ./work`

Observed on that fixture (**example, not an official case result**): `status=ok`, 12 slides, `presentation.pptx` 30.8 kB, `presentation.pdf` 12 pages / 52 kB, `notes_coverage 12/12`, `quotes_matched` all pages with 0 missing, `number_whitelist.misses 0`, `figure_refs.mismatch 0`, runtime 1.9 s.

## 9. Files and maintenance

| Path | Role |
|---|---|
| `SKILL.md` | contract and method (this file) |
| `scripts/main.py` (~20.4 kB) | discovery, parsing, page plan, result.json |
| `scripts/deckbuild.py` (~20.5 kB) | extraction chain, pptx build/template surgery, PDF export, file checks |
| `references/page-outline.md` | page roles, role budget, bullet/claim rules |
| `references/output-schema.md` | result.json schema, quoting and threshold rules |
| `references/checklist.md` | rubric → field/check/artifact map, pre-submission checklist |

Version 1.0.0. Bump the version here and in `references/checklist.md` on any rule change, then re-run the fixture and confirm `compliance_checks.pass = true`. All rules are paper-, template- and case-independent; no artifact in this package contains a prepared answer.
