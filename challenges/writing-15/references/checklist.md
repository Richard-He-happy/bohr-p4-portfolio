# Review checklist, computed checks, known failure modes

## 1. What `verify.py` computes (not asserted)

| Check | Rule | Severity |
|---|---|---|
| quote_traceability | `anchor_quote`/`evidence` quote must hit a block after whitespace+typography normalisation | high |
| annotation_scope | target outside the workorder, or a proposal that rewrites original text | high |
| workorder_receipt | every target needs an accepted or explicitly rejected item, with a reason for rejection | high |
| terminology | one abbreviation with several expansions in the source; same abbreviation defined twice; `3D/3-D`, `modeling/modelling`, `fiber/fibre`, `µm/um` etc. coexisting; abbreviation used before its definition | high / warn / info |
| numbering | two captions sharing a number, gaps in Table/Figure/Equation numbering, `Section N.M` without a matching heading | warn / info |
| citation | `[n]` cited but absent from the reference list; list entries never cited; `[CITATION]`, `??`, `待补` placeholders | high / info |
| units | the same quantity expressed in mixed units | info |
| numeric_conflict | one quantity key with several values (a `from X to Y` range is not a conflict) | warn |

Each finding carries `id`, `check`, `severity`, `message`, `locators`, `action`; high findings
are copied into `pending_human` and `uncertainty`.

## 2. Pre-submit checklist

- [ ] `init` ran; `work/source_index.json` has every material and the resolved target locators.
- [ ] `draft.json` has one item per target; every quote was copied from `show`, not retyped.
- [ ] `check` shows 0 `high`; each remaining `warn` is understood and left in the report.
- [ ] `build` printed `status=ok` (or `partial` with reasons you accept).
- [ ] `manuscript.md`: headings preserved, annotations only inside `> **[EA-...`, no text deleted.
- [ ] `versions/diff_v1_v2.patch` touches only added blocks.
- [ ] `workorder_receipt.targets[]` all `done` or `pending_human` with an action.
- [ ] `pending_human` names every missing chapter, fallback note and unresolved id.
- [ ] No annotation introduces a number, citation, table or section that is absent from the source.

## 3. Known failure modes and the intended handling

| Failure mode | What the skill does | What a human must do |
|---|---|---|
| workorder target id not present anywhere | `status=pending_human`, reason recorded, no annotation invented | confirm the id or supply the chapter |
| id present but without an explicit anchor | paragraph index from the `P<nnn>` suffix, `resolution: heuristic`, uncertainty entry | check the paragraph on the printed manuscript |
| chapter file unreadable (binary, broken zip) | that material `unreadable`, others proceed, degradation note | provide a text/PDF version |
| PDF without a text layer and no `pdftotext` | `degraded`, no guessed text | install `pdftotext` or supply the source text |
| two source values for one quantity | reported as `numeric_conflict`, both kept | decide which value the author meant |
| reference list absent from the materials | citations carried verbatim, info note | author completes the bibliography |
| draft missing or invalid | deterministic fallback notes, `status=partial` | replace fallback notes with reviewed ones |
| agent quotes from memory | quote does not hit any block, item rejected | re-read the paragraph with `show` |

## 4. Why the original text is never edited

The workorder demands traceable, minimal change. The skill therefore:

1. copies every source block into `manuscript.md` unchanged;
2. inserts only blockquotes that start with `> **[EA-`;
3. recomputes `rollback_equals_v1` by deleting those blockquotes and hashing the result, and
   `reapply_equals_v2` by re-inserting them from the accepted list;
4. stores `source_blocks_unchanged`, `annotations_in_v2` and `annotations_after_rollback` so a
   reviewer can confirm the invariant without re-running the diff.

## 5. Worked micro-example (example, not a case result)

Target `T01-P002` reads: "Tensile tests followed ASTM D638 at a crosshead speed of 5 mm/min,
and the reported strength is the mean of five specimens."

Accepted annotation: "The reported strength is a static mean over five specimens at 5 mm/min;
the paragraph states neither specimen conditioning nor test temperature, so the value is a
within-study comparison rather than a material property." Evidence: the same sentence, locator
`chapters/ch03.md §3 Materials and methods ¶3`. Result: one blockquote inserted after the
paragraph, hash equality holds, one `change_log` entry, one `evidence_map` entry.
