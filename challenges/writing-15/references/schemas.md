# Schemas: draft, result, locators

## 1. `work/draft.json` (written by the agent)

```json
{
  "case_id": "C01",
  "annotations": [
    {
      "annotation_id": "EA-01",
      "target_id": "C01-P002",
      "operation": "annotate",
      "status": "accepted",                  // accepted | rejected (rejected needs "reason")
      "anchor_quote": "<sentence copied verbatim from the target paragraph>",
      "text": "<2-4 sentences: the claim, the condition or limitation it depends on, quoted
                exactly from the source; no new data, no new citation>",
      "evidence": [
        {"quote": "<verbatim sentence from any supplied material>",
         "locator": "chapters/ch03.md §3 Methods ¶4",
         "note": "what this sentence establishes"}
      ],
      "rationale": "<why the chapter argument needs this clarification>"
    }
  ],
  "outline": [{"id": "ch3", "heading": "3 Methods"}],   // optional, checked for coverage
  "chapter_drafts": [{"id": "ch3", "heading": "3 Methods", "blocks": []}],  // optional
  "pending_human": ["<what the agent could not settle>"]                    // optional
}
```

Rules enforced by `check` and re-enforced by `build`:

* `target_id` must be in the workorder; a target outside it is rejected, not applied.
* `anchor_quote` must occur verbatim (after whitespace normalisation) inside the target block.
* every `evidence[].quote` must occur verbatim somewhere in the materials.
* `text` shorter than 40 characters is rejected as non-substantive.
* `rejected` items are kept in `change_log` with their reason and change nothing.

## 2. `result.json`

| Key | Content |
|---|---|
| *all `output_contract` keys* | echoed verbatim; unknown keys kept; unmatched values `null` |
| `case_id` | copied from the case (never from the contract placeholder) |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | `{primary, editable, files, block_coverage, blocks, annotations_applied, annotations_rejected, words_added, source_words_rewritten}` |
| `preserved_facts` | `[{fact_id, kind, quote, source_locator, preserved}]` - computed substring test |
| `evidence_map` | `[{claim_id, target_id, target_locator, claim, evidence:[{quote, locator, verbatim}]}]` |
| `change_log` / `changes` | one entry per applied annotation (`original_quote`, `revised_text`, `original_text_changed: false`) and per rejection with `reason` |
| `workorder_receipt` | `{workorder_id, authority, targets[], operation_requirements[], version_control, fault_injections}` |
| `consistency` | `{report, findings, high, warn, info, facts_verified, checks}` |
| `sources` | per material: `id, path, kind, blocks, status, sha` |
| `uncertainty`, `pending_human`, `errors`, `degradations` | lists of objects with a reason and, where relevant, locators |
| `runtime` | skill, version, python, utc, elapsed_s, budget note |

`workorder_receipt.targets[]` = `{item_id, target_id, status: done|pending_human, locator,
resolution: anchor|heuristic, annotations[], reason}`.

`version_control` = `{v1_sha, v2_sha, rollback_equals_v1, reapply_equals_v2,
source_blocks_unchanged, annotations_in_v2, annotations_after_rollback}` - all recomputed from
the files on every build.

## 3. Locator grammar

* `chapters/ch03.md §3 Materials and methods ¶4` - section and paragraph in prose materials.
* `... §3 Materials and methods (heading)` - the heading block itself.
* `chapters/ch06.json #C01-P057` - JSON block carrying that id.
* `chapters/ch06.json #/chapters/0/text` - plain JSON pointer for dicts without ids.
* `data.csv #row 12` - tabular row.

Locators are produced by `init` and printed by `show`; use the printed string, do not retype it.

## 4. Annotation rendering

Applied annotations are inserted after their target block as:

```
> **[EA-01 · editorial annotation · added by writing-11; original text unchanged]**
> <text>
> *Evidence:* "<quote>" - `<locator>`
> *Why:* <rationale>
```

Ann-blockquotes are the only added text; the diff and the hashes prove it.
