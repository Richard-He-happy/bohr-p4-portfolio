---
name: academic-slide-template-adapter
description: "Academic slide template adapter that turns actual paper/research material and a real .pptx template into an editable evidence-mapped deck with PDF/PNG previews, template spec, format compliance, page-level diff, version history, run log, and honest result.json. Use when a case requires fitting research content into a master/layout template, adapting a starting deck, or auditing template conformance. Runs deterministic baseline scripts first, then Harness Agent must verify quotes and improve outputs; if no agent draft exists, build falls back to deterministic extraction with explicit gaps and degradations."
version: 4.0.0
---

# Academic Slide Template Adapter

## 1. Mission

Turn actual source material and the organizer-provided template into a genuinely template-inherited, editable academic slide deck plus rendered PDF/PNG previews. Every slide must have page-level claims mapped to verbatim source quotes and locators. The package must work with one command, degrade honestly, exit 0, and produce a complete `result.json` that can be independently replayed and audited.

This skill is optimized for the Harbor rubric: actual task completion, verifiable correctness, completeness, reliability, and reuse evidence matter more than generating many slides or long self-descriptions.

## 2. Trigger conditions

Use this skill when:

- The case asks to produce academic slides from provided paper or research material and a `.pptx` template.
- The case asks to adapt an existing deck to organizer template constraints.
- The case requires template inheritance, figure adaptation, speaker notes, or export/render checking.
- The output contract requires an editable presentation and rendered previews.

Do not use this skill for non-slide document tasks unless the organizer contract explicitly requires a slide deck.

## 3. Hard rules

1. Read actual `/input` files. File names and labels are not facts.
2. Do not fabricate source content, quotations, citations, template evidence, hidden test outputs, or benchmark scores.
3. Scripts produce deterministic artifacts. The Harness Agent must personally read source material and verify claims. If no Agent draft exists, the deterministic fallback must record `AUTO_EXTRACT` as an honest degradation.
4. Always exit 0, including partial, insufficient-evidence, or input-error states.
5. Preserve all original `output_contract` keys unchanged. Echo contract fields plus `case_id` twice: at root level and under nested `output_contract`.
6. Never delete baseline artifacts. Agent enhancement only adds or improves.
7. Work under `/app/work`. Final deliverables belong under `/app/output`, never under `/tmp`.
8. Stay honest about missing software state, missing figures, missing fonts, missing text layers, and export failures.

## 4. Runtime contract

| Item | Requirement |
|---|---|
| Skill install dir | `/skills/weekly-skill` |
| Input dir | `/input` |
| Work dir | `/app/work` |
| Output dir | `/app/output` |
| Primary entry | `cd /skills/weekly-skill && python3 -B scripts/main.py run --input /input --output /app/output --work /app/work` |
| Exit code | Always 0 |
| Model budget | 64 model requests / 900 seconds / 16384 tokens per response including reasoning |
| Python | Standard library only, Python 3.8 or later |
| Optional binaries | `soffice`, `pdftoppm`, `pdftotext`, `pdffonts`, `fc-match`; detect first, degrade if missing |
| Submission resources | `SKILL.md`, `references/artifact_schema.md`, `scripts/main.py`, `scripts/verify.py`, `scripts/spec.py`, `scripts/reports.py`, `scripts/selfcheck.py` |
| Hidden tests | Do not provide hidden tests or whiteboards |

The helper modules are:

- `scripts/main.py` — orchestration.
- `scripts/verify.py` — parsing, planning, XML emission, compatibility checks.
- `scripts/spec.py` — template spec, compliance, export checks, rollback, synthetic skeleton.
- `scripts/reports.py` — run log, page diff, version history.
- `scripts/selfcheck.py` — final self-check.

## 5. Single-command full workflow

Execute:

`cd /skills/weekly-skill && python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

Internal phases:

- `init` — inventory `/input`, assign source IDs `S1..Sn`, compute `sha256`, byte size, mime type, extract source text and template/deck structure, produce `/app/work/ledger.json`, candidate claims, and conflict groups.
- `build` — read `/app/work/draft.json` if present; otherwise run deterministic fallback from `/app/work/ledger.json`. Produce the editable deck, notes, figure placement, rendered previews, evidence map, compliance artifacts, diff, version history, and draft `result.json`.
- `check` — verify contract field coverage, pptx zip structure, template inheritance, XML evidence, quote existence, file existence, export render consistency, font substitution, overflow status, and page count.
- `selfcheck` — run `scripts/selfcheck.py` against `/app/output` and `/app/work`; final result must still exit 0.

Optional checkpoint resumption:

- `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work --checkpoint init`
- `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work --checkpoint build`
- `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work --checkpoint check`

If the full command already runs init/build/check/selfcheck, a normal Harness Agent should call it once, then inspect.

## 6. Agent-first dual path

This is the core design for quality and budget.

### Agent path

1. Run init checkpoint.
2. Read `/app/work/ledger.json`.
3. Personally read the actual source materials indicated by ledger.
4. Write `/app/work/draft.json` with the intended slide plan, claims, source IDs, verbatim quotes, locators, figure references, speaker notes, and explicit uncertainty.
5. Run build/check.
6. The built deck then records `source_mode: agent_draft`.

### Deterministic fallback path

If `/app/work/draft.json` does not exist when build starts, the build phase deterministically extracts content from ledger.

Every fallback-generated claim must be marked `AUTO_EXTRACT: true`. Result `degradations` must include:

- `stage: content`
- `code: AUTO_EXTRACT`
- `detail: "No agent draft.json present; content was deterministically extracted from ledger and may need human review."`

Status in this path should be at most `partial` unless later agent review upgrades it. This design guarantees a complete deliverable even with zero model requests, while preserving an honest improvement path.

## 7. Draft shape for Agent

`/app/work/draft.json` must be valid JSON and should contain:

- `case_id` — from `/input/case.json`.
- `slide_plan` — array of planned slides.
- `slide_plan[].slide_index` — zero-based.
- `slide_plan[].page_type` — `cover`, `outline`, `research_question`, `method`, `results`, `figure`, `discussion`, `limitations`, `conclusion`, `references`, etc.
- `slide_plan[].title` — short slide title.
- `slide_plan[].claim` — single page-level claim.
- `slide_plan[].sources` — array of source IDs.
- `slide_plan[].quote` — exact quote from source, or `null`.
- `slide_plan[].locator` — `file:line/paragraph` or other precise locator.
- `slide_plan[].figure_ref` — figure/table number if any.
- `slide_plan[].speaker_notes` — concise explanation or uncertainty.
- `rules` — optional overrides such as `min_font_pt`, `max_bullet_chars`, `footer_text`, `page_number_required`.
- `uncertainty` — array of uncertain items.
- `pending_human` — array of items needing human review.

If quote cannot be confirmed verbatim, set `quote: null` and record why.

## 8. Output artifacts

All final artifacts must be under `/app/output`:

- `presentation.pptx` — editable slide deck.
- `presentation.pdf` — rendered PDF if export succeeded.
- `preview/page_001.png` etc. — page-level rendered previews for inspection.
- `result.json` — structured final result.
- `source_manifest.json` — input inventory with hashes.
- `content_map.json` — per-slide claims, evidence, notes, figure status.
- `template_spec.json` — extracted template master/layout/theme/placeholder spec.
- `format_compliance.json` — itemized compliance checks with XML snippets.
- `export_check.json` — PDF/PNG page count, size, font, overflow, consistency results.
- `page_diff.md` — page-by-page deviations, missing items, overflow items.
- `version_history.md` — rollback path and change log.
- `run.log` — phase timings, command echo, detected binaries, failures.

If PDF export is unavailable, keep `presentation.pptx` and use `export_check.status = "no_pdf"` with status `partial`.

## 9. `result.json` dual-echo contract

The original `output_contract` from `/input/case.json` and `case_id` must appear twice:

1. At root level.
2. Inside root key `output_contract` as a nested object.

Other required root fields:

- `status` — one of `ok`, `partial`, `insufficient_evidence`, `input_error`.
- `sources` — array with `source_id`, `path`, `sha256`, `bytes`, `mime`, `chars`, `used`.
- `uncertainty` — array.
- `pending_human` — array.
- `errors` — array, may be empty.
- `degradations` — array with `stage`, `code`, `detail`.
- `changes` — array of agent/script modifications.
- `runtime` — `command`, `started_at`, `ended_at`, `duration_seconds`, `timeout`.
- `artifacts` — map of artifact name to path.
- `workorder_echo` — extracted organizer constraints like slide count, footer, page number requirement, audience, min font.
- `agent_review` — optional but strongly recommended; records verified quotes, conflicts, pending items, reviewed locators, timestamp.

Contract fields must not be lost even if value is `null` or `[]`.

## 10. Evidence standards

- Every key number, claim, figure reference, or scientific statement in the deck must carry at least one `[S#]` source reference.
- Locator format is preferably `file:line/paragraph` for text-like sources, or `file:slide#/shape#` for template-derived locations.
- A quote must be verbatim when used as evidence. If only paraphrase is possible, set `quote: null` and `quote_status: paraphrased_or_missing`.
- `content_map` must include each slide index, page type, title, claim, source IDs, quote, locator, figure ref, speaker notes, and `source_mode`.
- No slide should contain an unsupported scientific statement without `pending_human` or `uncertainty`.

## 11. Template compliance and render quality

This skill must demonstrate:

- Real master/layout/theme inheritance, not synthetic flattening unless no template exists.
- Placeholder use where available; if missing, clone fallback plus explicit deviation.
- Theme fonts/colors maintained unless organizer overrides.
- Text fit inside box, no overflow, no unreadable font size.
- Chinese/English font pairing with explicit fallback handling.
- Charts and images aspect-ratio fitted or cropped, never stretched.
- Figure numbering consistent between visual, caption, body, and notes.
- Batch consistency for footer, page number, title position, margins, spacing, and font hierarchy.
- PDF/PNG render consistency: page count matches slides, page size matches deck, notes preserved, fonts embedded or substitutions recorded.
- If `soffice` or `pdftotext` is unavailable, record the resulting degradation.

## 12. Hidden case robustness

| Case type | Scenario | Required behavior | Evidence |
|---|---|---|---|
| Normal | Template, deck, PDF paper, images present | Full build plus Agent verification | `status: ok` or `partial` with few pending items; full artifacts |
| Boundary | Template missing a body placeholder, long title, large figure, no text layer | Use fallback placeholder, font scaling within organizer min, aspect fit, and remain partial if text unavailable | `deviation`, `format_compliance`, `content_map[].figure_status`, `degradations` |
| Boundary | One figure unreadable or corrupt | Skip figure, record `figure_unreadable`, do not invent figure data | `pending_human`, `degradations` |
| Boundary | Font missing or PDF export font substitution | Record font name and substitution, keep editable file correct | `export_check.fonts`, `degradations` |
| Abnormal | No template | Build minimal synthetic 16:9 deck, mark synthetic template | `template_spec.template.kind: synthetic`, `status: partial` |
| Abnormal | Scanned PDF with no text layer | Do not invent text; produce structural deck with missing source evidence | `errors` or `pending_human`, `status: insufficient_evidence` |
| Abnormal | Missing `/input/case.json` or malformed contract | Construct minimal `result.json`, echo null contract fields, `case_id: "unknown"`, `status: input_error` | `errors`, `workorder_echo.missing_contract: true` |
| Abnormal | Export binary unavailable | Keep pptx, set `no_pdf`, remain partial | `export_check.status: no_pdf` |
| Abnormal | Timeout or script crash | Save existing partial result, create minimal legal result if missing, exit 0 | `runtime.timeout: true`, `errors`, `status: partial` or `input_error` |

In all abnormal cases, final `result.json` must still be valid and exit 0.

## 13. Agent review checklist

The Harness Agent should perform these actions after the deterministic run, within budget:

1. Read `/input/case.json` and `/input/task.md` to confirm output contract and organizer constraints.
2. Run init or full command.
3. Read `/app/work/ledger.json`.
4. Verify at least 3 core slide claims against original source text:
   - research question
   - method
   - result or limitation
5. Verify at least 2 figure citations:
   - figure number exists
   - caption/quote matches source
   - body figure reference matches slide figure.
6. Inspect 2-3 format compliance evidence snippets to confirm they are real XML/master/layout evidence.
7. Write verified/rejected/corrected observations into `result.json.agent_review`.
8. If speaker notes are weak, rewrite only the notes object, not the evidence structure.
9. Do not manually rewrite structured JSON such as `format_compliance.json` or `content_map.json`.
10. Before finishing, confirm the dual echo of contract fields is present.

## 14. Budget plan

| Phase | Suggested model requests | Action |
|---|---|---|
| Inventory and command | 1-3 | Read `case.json`, `task.md`, verify input file list |
| Run main command | 1 | Execute full deterministic pipeline |
| Inspect outputs | 1-2 | Check `result.json`, file list, artifact existence |
| Agent evidence review | 5-10 | Verify core quotes, figures, compliance snippets |
| Final result update | 1-2 | Add `agent_review`, ensure legal JSON, exit 0 |

Priorities under tight budget:

1. Legal `result.json` with dual echo and `case_id`.
2. Existing `presentation.pptx`.
3. Existing PDF/PNG preview when possible.
4. `content_map.json` with evidence and locators.
5. Compliance and export checks.
6. Agent review traces.

Never loop scripts more than twice. If uncertain, mark `pending_human` and finish.

## 15. Rubric mapping

| Dimension | Weight | What to deliver | Self-evidence |
|---|---|---|---|
| Actual effect | 40 | Editable template-inherited pptx, rendered PDF/PNG, correct page content and figures, six required elements, replayable records | `presentation.pptx`, `presentation.pdf`, `content_map.json`, `template_spec.json`, `format_compliance.json`, `export_check.json`, `result.json` |
| Use gain | 25 | Real template use, no overflow, correct figure fit, consistent fonts/colors/footer/pagination, less manual rework | `format_compliance` pass items, `page_diff.md`, `run.log` phase timing, `agent_review` |
| Innovation | 15 | True master/layout extraction, XML-level evidence, aspect-ratio figure policy, typographic rule mapping, page-level diff | `template_spec.json`, `format_compliance.*.evidence.snippet`, `page_diff.md`, `scripts/spec.py` behavior |
| Reliability | 10 | One-command workflow, repeatable script, graceful optional binary handling, exception table, exit 0 | `run.log`, `export_check`, `degradations`, `selfcheck.py` |
| Ecosystem | 10 | Complete documentation, artifact schema, minimal example, maintainability, reusable rules | `SKILL.md`, `references/artifact_schema.md`, structured scripts |

## 16. Self-check before finish

Run:

`cd /skills/weekly-skill && python3 -B scripts/selfcheck.py --work /app/work --output /app/output`

The self-check must verify:

- `result.json` is valid JSON.
- Original output contract fields are present at root and nested under `output_contract`.
- `case_id` is not empty.
- `presentation.pptx` exists and contains `ppt/presentation.xml`.
- `content_map.json` exists and has at least one slide.
- `template_spec.json` exists.
- `format_compliance.json` exists.
- `run.log` exists.
- No file is under `/tmp`.
- If PDF export was attempted, PDF page count either matches slide count or `export_check` records failure honestly.

If self-check finds issues, fix by adding missing fields or marking degradation, never by deleting artifacts.

## 17. Failure and exit contract

The Skill must never crash the evaluation.

If the main script crashes or cannot run:

- Agent must create `/app/output/result.json` manually.
- Include `status: "input_error"` or `"partial"`.
- Include `case_id` from input or `"unknown"`.
- Echo all missing contract fields as `null` or `[]`.
- Add `errors` with `"main script failed: <message>"`.
- Ensure `exit_code` remains 0.

## 18. Minimal invocation example

This is an illustrative example, not a real hidden case answer.

Input:

- `/input/case.json` with `case_id: "example_case"` and output contract fields.
- `/input/paper.pdf` — actual paper.
- `/input/template.pptx` — organizer template.
- `/input/task.md` — organizer task.

Command:

`cd /skills/weekly-skill && python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

Expected output:

- `/app/output/presentation.pptx`
- `/app/output/presentation.pdf`
- `/app/output/preview/page_001.png`
- `/app/output/result.json`
- `/app/output/template_spec.json`
- `/app/output/format_compliance.json`
- `/app/output/export_check.json`
- `/app/output/page_diff.md`
- `/app/output/version_history.md`
- `/app/output/run.log`
- `/app/output/source_manifest.json`

The `result.json` should show the same contract fields twice, with status indicating real runtime state.

## 19. Reuse and maintenance

The package is designed to be reused by future academic slide tasks.

- `references/artifact_schema.md` documents each artifact field and contract field.
- `scripts/main.py` is the stable entry point.
- `scripts/verify.py` handles source parsing and XML compliance evidence.
- `scripts/spec.py` handles template extraction, synthetic fallback, and export checks.
- `scripts/reports.py` generates audit logs.
- `scripts/selfcheck.py` validates final output.

For a new case, the Agent only needs to inspect input, optionally write `/app/work/draft.json`, and run the single command. If no Agent attention is available, the deterministic fallback still delivers a real editable deck with honest gaps.

Do not submit pre-generated answers for hidden cases. This Skill must operate only from `/input` at runtime.