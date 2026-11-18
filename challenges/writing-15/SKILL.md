---
name: thesis-chapter-revision
description: Revise a supplied long document (degree-thesis chapters, reports) under an organizer edit workorder - add source-grounded editorial annotations at the given targets, keep every original block byte-identical, and return manuscript.md plus receipts, evidence map, preserved facts, change log and a computed cross-chapter consistency report. Use for chapter drafting/editing, terminology and numbering consistency, citation-anchor checks, or any local revision of a multi-chapter manuscript with target ids.
version: 1.0.0
---

# Thesis chapter revision (writing-11)

## 1. What it does and what it does not

Loads the supplied chapters, indexes them into locatable blocks, lets the **agent write the
editorial content**, then mechanically verifies and assembles the manuscript:

* adds one annotation per workorder target, anchored to a verbatim source sentence;
* reproduces every source block unchanged (proved by hash in `versions/`);
* reports terminology, numbering, citation, unit and numeric conflicts it can compute;
* records per-target receipts, change log, evidence map and human-confirmation items.

Boundaries: it never rewrites author text, never invents a citation, value, table, figure or
section, and never "corrects" a source contradiction. Fields the material does not support are
reported as gaps, not filled. PDF is read only when `pdftotext` exists; otherwise the file is
recorded as a degradation.

## 2. Runtime contract

* Input: `/input/case.json` (or any `case*.json` with `case_id`/`output_contract`), `task.md`,
  and materials under `/input/**` (md, txt, docx, json, csv, pdf).
* Work dir: `/app/work` (`work/source_index.json`, `work/draft.json`, `work/check_report.json`).
* Output dir: `/app/output` - `result.json`, `manuscript.md`, `consistency_report.md`,
  `manuscript_preview.html`, `versions/*`.
* Every path is computed from `Path(__file__).parent` or an explicit flag; nothing depends on
  the current directory. Standard library only, no network.
* `result.json` echoes **every** `output_contract` key unchanged (unknown keys kept, missing
  values `null`/`[]`) plus `case_id`, `status` (`ok|partial|insufficient_evidence|input_error`),
  `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`,
  `deliverable`, `preserved_facts`, `evidence_map`, `change_log`, `workorder_receipt`.
* A legal partial `result.json` is written first; all exceptions are caught; **exit code is 0**
  on every path.

## 3. Input discovery (no key-name assumptions)

1. `init` looks for `case.json`, then `input.json`, then any JSON containing `case_id` or
   `output_contract`, all read as `utf-8-sig` (BOM safe).
2. The workorder is found semantically: any case key matching `work?order` (dict or list), then
   any `*workorder*.json` in the input tree; both are merged, the file wins.
3. Materials are sorted by path and typed by extension **and magic bytes** (`%PDF`, `PK` +
   `word/`|`xl/`). Labels are never trusted.
4. `init` prints a material index, section locators, the first blocks, the workorder task, the
   resolved locator of every target, and the outstanding operation requirements.

## 4. Workflow (agent-led, four commands)

```
python3 scripts/main.py init  --input /input --out /app/output     # index + partial result
python3 scripts/main.py show  --target C01-P002  [--context 3]     # exact text + locator
python3 scripts/main.py check                                      # validate your draft
python3 scripts/main.py build                                      # manuscript + reports
```

**Step 1 - read.** Run `init`. Read the printed blocks; for every target run
`show --target <id>` and note the locator. Look for the paragraph's condition, scope, measured
values and any contradiction with another chapter.

**Step 2 - write `work/draft.json` yourself.** One item per target: exact `anchor_quote`,
2-4 sentence `text` that explains the claim's condition/limitation **using only supplied
material**, one `evidence` entry with a verbatim quote and the locator you read, and a short
`rationale`. A ready skeleton is at `work/draft_template.json`. Schema: `references/schemas.md`.

**Step 3 - check.** Fix every `high` finding (quote not verbatim, target out of scope, missing
receipt). `warn` items are judgement calls; record them.

**Step 4 - build.** `build` re-validates each proposal with the same validator used for fault
injection, applies accepted ones, keeps rejected ones in `change_log` with the reason, assembles
`manuscript.md`, and writes `result.json`. Anything the draft does not cover gets a
**deterministic fallback note** (source quote + related passage selected by term overlap) marked
`generated_by: deterministic_fallback`, `needs_review: true`, `status: partial`.

## 5. Quality rules mapped to what gets written

| Requirement | Where it shows up |
|---|---|
| Real, usable chapters (not advice) | `manuscript.md` with all source headings/paragraphs |
| Only the targets change | `versions/diff_v1_v2.patch`; `version_control.source_blocks_unchanged` |
| Every claim traceable | `evidence_map[].evidence[].locator` + `verbatim: true` |
| Facts/numbers/terms unchanged | `preserved_facts[]` with `preserved: true/false` computed by substring test |
| Workorder executed per item | `workorder_receipt.targets[]` = done / pending_human + reason + locator |
| Rollback demonstrated | `version_control.rollback_equals_v1`, `reapply_equals_v2` (recomputed, not asserted) |
| Invalid operations handled | `workorder_receipt.fault_injections[]` (4 deliberate rejects) |
| Cross-chapter consistency | `consistency_report.md`, computed by `scripts/verify.py` |
| Honest incompleteness | `status`, `pending_human`, `uncertainty`, `errors`, `degradations` |

## 6. Evidence and locator format

Locators are generated, never guessed:

* markdown/docx/pdf prose: `<file> §<section number> <title> ¶<paragraph>` (`(heading)` for the
  heading block itself);
* JSON: `<file> #<id>` when a dict carries an id + text, otherwise `<file> #/<json/path>`;
* CSV/XLSX rows: `<file> #row N` (XLSX is not parsed; recorded as a degradation).

A quote counts as verified only after whitespace/typography normalisation and a hit inside one
block, or a cross-block hit inside one material. Quotes that fail are rejected, never adjusted.

## 7. Conflicts and human confirmation

Source-internal contradictions (two values for the same quantity, two expansions of one
abbreviation, mixed units) are **reported, not corrected**: they go to `consistency_report.md`,
`uncertainty` and - when severe - `pending_human`. Unresolvable targets, missing
chapters, absent bibliographies and fallback notes always appear in `pending_human` with the
action a human must take. Target ids without an explicit anchor fall back to the `P<nnn>`
paragraph index and are labelled `resolution: heuristic` plus an uncertainty entry.

## 8. Failure behaviour

| Situation | Behaviour |
|---|---|
| no `/input` or no case JSON | `result.json` `status=input_error`, `errors` explains, exit 0 |
| case JSON malformed | same; index still written with `errors` seeded from `init` |
| unreadable / binary material | that material `status=unreadable/skipped`, other materials proceed |
| PDF without text layer | `status=degraded`, degradation note, no invented text |
| no draft.json | full deterministic fallback, `status=partial`, pending items listed |
| draft quote not found | item rejected with reason, original state unchanged |
| verifier module missing | workflow still builds; `consistency` block reports zero findings and says so |

## 9. Budget and checkpoints

Budget is 64 model requests / 900 s per case. `init` writes a valid partial `result.json`
before any parsing, so an interrupted run still leaves a legal artifact; `build` finalises
unconditionally. Keep `show --chars` low and print only the targets you need.

## 10. Self-check before returning

1. `result.json` parses; all `output_contract` keys are present; `status` matches reality.
2. `manuscript.md` contains every source heading/paragraph; annotations are inside `> **[EA-...`.
3. `version_control.rollback_equals_v1` and `source_blocks_unchanged` are `true`.
4. Every target in `workorder_receipt.targets` is `done` or `pending_human` with a reason.
5. `pending_human` lists missing material and every fallback note.
6. No new numbers, citations or section numbers were introduced by an annotation.

## 11. Minimal example (illustrative, not a case result)

Input: one chapter `ch03.md` with `<!-- T01-P002 -->` before a methods paragraph, a workorder
with `target_ids: ["T01-P002"]`, `output_contract` = {case_id, deliverable, preserved_facts,
evidence_map, change_log}.

```
python3 scripts/main.py init --input /tmp/in --out /tmp/out     # -> 1 material, 6 blocks
# agent writes work/draft.json with anchor_quote + evidence quote
python3 scripts/main.py check                                   # -> 0 high, targets 1/1
python3 scripts/main.py build                                   # -> status=ok, 1 applied
```

Illustrative `result.json` fragment (**example, not a formal case result**):

```json
{"case_id": "T01", "status": "ok",
 "workorder_receipt": {"targets": [{"target_id": "T01-P002", "status": "done",
   "locator": "chapters/ch03.md §3 Materials and methods ¶3", "resolution": "anchor",
   "annotations": ["EA-01"]}],
   "version_control": {"rollback_equals_v1": true, "reapply_equals_v2": true}}}
```

## 12. Files and version

| File | Role |
|---|---|
| `SKILL.md` | this contract and workflow |
| `scripts/main.py` | `init`, `show`, `check`, `build`; indexing, assembly, receipts |
| `scripts/verify.py` | quote lookup, draft validation, consistency scan, report rendering |
| `references/schemas.md` | draft/result schemas and locator rules |
| `references/checklist.md` | review checklist, computed checks, known failure modes |

Version 1.0.0, standard library only, Python 3.9+ (tested on 3.12). No configuration, no
services, no cached state outside `/app/work`.

## 13. Maintenance

Change checks in `scripts/verify.py` only - `main.py` calls them through a small API
(`resolve`, `find_quote`, `norm`, `check_draft`, `scan_manuscript`, `preserved_facts`,
`consistency_markdown`). Keep `run` deterministic: same input and draft must give the same
`manuscript.md` hash. New material types belong in `parse_material` as one branch, never as a
new dependency.
