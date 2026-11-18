# Evidence schema, quote gate, and strength rules

Reference for `literature-review-evidence-mapper` v1.0.0. The scripts read
`references/templates.json`; this file is the human-readable contract that
`result.json` and `evidence_map.csv` follow.

## 1. `evidence_map.csv` columns (fixed order)

| column | meaning | allowed values |
|-|-|-|
| `evidence_id` | row id, unique | `E001`, `E002`, ... |
| `claim` | the claim this row supports, in the agent's words | free text, one sentence |
| `source_id` | must exist in `sources` | `S01`, `S02`, ... |
| `locator` | where in the source | `p.3`, `para.4`, `row.7`, `sec.2.1`, `table.2`, `fig.1` |
| `quote` | verbatim span copied from that locator | must match the source text after whitespace/normalisation |
| `strength` | evidence strength | `directly_supported`, `inferred`, `insufficient`, `unassessed` |
| `claim_type` | kind of claim | `finding`, `method`, `limitation`, `background`, `contradiction`, `excerpt_only` |
| `topic` | theme id that owns the claim | `T1`, `T2`, ... or empty |
| `verification` | written by `verify.py` | `verified`, `verified_lenient`, `rejected_*` |

`verify.py` overwrites `verification` on every run. Rows that fail the quote
gate are kept in the CSV (so the failure stays auditable) and are copied to
`pending_human`.

## 2. Quote gate (deterministic, no network)

`verify_quote()` accepts a row only when the normalised `quote` is a substring of
the normalised source text at the stated locator:

1. `norm()` applies NFKC, maps typographic quotes/dashes/`\ufb01`/`\ufb02`, collapses
   whitespace, and lowercases. Ligatures, soft hyphens, and NBSP therefore do not
   create false rejections.
2. Status `verified` — the quote is found inside the block named by `locator`.
3. Status `verified_lenient` — the quote is found elsewhere in the document; the
   locator is corrected to `matched_locator` and the mismatch is recorded. Use
   this to catch wrong-page citations rather than wrong quotations.
4. Status `rejected_absent` — not found anywhere: the sentence is unsupported.
5. Status `rejected_source` — `source_id` is missing or unknown: the citation is
   dangling.

Never edit a source string to make a quote pass. Fix the quote, move the row to
`pending_human`, or drop the claim.

## 3. Strength assignment

- `directly_supported` — the cited span states the claim itself, including its
  scope (model system, temperature, sample size, conditions).
- `inferred` — the span supports steps in a reasoning chain, but the claim adds
  interpretation. State the extra assumption in `claim`.
- `insufficient` — the source is abstract-only, methods are unreadable, or the
  span contradicts the claim. Keep the row for transparency; do not let the
  draft cite it as settled.
- `unassessed` — produced automatically from `work/candidates.csv` when no agent
  evidence table exists. Always a degradation, never a finished state.

Strength is reported per row, so a theme with mixed rows reports mixed strength
instead of a single smoothed verdict.

## 4. Contrast rule (conflicting findings)

For a pair in `templates.json:oppose`, or for two rows that share a topic and
differ in polarity, the draft must present both sides in one paragraph with both
citations. `verify.py` records them under `conflicts`, and a theme that has a
conflict but no opposing citation is listed in `uncertainty`.

## 5. Coverage counters (contract-critical)

`counts` and `coverage` are recomputed from the CSV files, not from prose:

- `counts.documents` = corpus size, `included + excluded <= documents`.
- `coverage.included_cited_ratio` = included sources cited in `review.md`
  divided by included sources. Below `0.8` adds `low_citation_coverage` to
  `uncertainty`.
- `evidence_summary` = `verified` / `verified_lenient` / `rejected` row counts.

## 6. `pending_human` and `degradations`

`pending_human` items are actionable and each carries `item`, `why`, `action`.
Typical items: protocol not authored before screening, undecided screening rows,
rejected quotes, missing full text, dangling citations, missing research
question. `degradations` are non-blocking capability limits, e.g. `no pdftotext`,
`xlsx unparsed`, `baseline draft used`, `candidate excerpts used`.

`status` follows evidence, not effort: `ok` needs at least one included source,
zero rejected rows, an agent-authored protocol and draft, no undecided rows, and
citation coverage `>= 0.8`. Otherwise `partial`, or `insufficient_evidence` when
nothing could be included.
