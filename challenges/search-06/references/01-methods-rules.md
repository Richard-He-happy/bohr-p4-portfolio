# 01 — Window, identity, version and alert rules (normative)

Anything below is implemented in `scripts/core.py` (identity) and `scripts/main.py`
(windows, delta, alerts). Change code and this file together.

## 1. Time window

- A window is `[start, end)` with `start < end`, both resolved to UTC datetimes.
  Half-open on the right so consecutive windows never double-count a record.
- Resolution order: `--window-start/--window-end` → case keys
  (`window/period/range/interval` with `start|window_start|from|since` and
  `end|window_end|to|until|as_of`) → artifact configs (`config.yaml`, `state.json`,
  import-state files) → derived (previous snapshot end, else `end - 7 days` when `--now`
  is fixed, else the latest index date + 1 day).
- **Membership uses the index/import date**, not the publication date: Crossref `created`
  / `deposited`, EuropePMC `firstIndexDate`, organizer `imported_at` / `entry_date`.
  Priority list: `first_index_date, index_date, indexed_date, created, deposited,
  imported_at, import_date, entry_date, db_date, added_at, ingested_at, updated`.
  If no index field exists, the publication date is used and the record is flagged
  `index_date_proxy` (visible in `evidence_locator.index_date_field = null`); the run adds
  an `uncertainty[]` entry, because "newly indexed" then cannot be proven.
- Multi-window inputs are processed in ascending order with the delta state advanced after
  each window, so window *n* is diffed against windows *0..n-1* plus the previous snapshot.
- Continuity: `coverage.continuity_ok` is true only when the previous snapshot end is not
  earlier than the first window start and no two consecutive windows leave a gap.
  `gap_count` counts those holes; they are also written as `coverage.gaps`.

## 2. Identity keys and deduplication

Keys computed per record:

| Key | Normalization |
|---|---|
| `doi:` | lower-cased, strip `https://doi.org/`, `doi:` prefix, trailing punctuation; must match `^10\.\d{4,9}/\S+$` |
| `arxiv:` | `10.48550/arXiv.X` → `X`; `arXiv:Xv2` → `X` (version suffix dropped) |
| `pmid:` | 6-9 digit PMID |
| `pmcid:` | `PMC` + digits, lower-cased |
| `title:` | NFKD-stripped ASCII, lower-cased, tags removed, non-alphanumerics → space, whitespace collapsed |

Union-find merges records sharing any key. A missing key never merges anything; two
records that share only a title key are the same work (preprint and published versions of
one paper usually share the title).

`sig(keys)` = the strong keys (everything except `title:`), falling back to the title key
only when a record has no strong identifier. Delta decisions use `sig()` so that a title
shared by a preprint and its published version cannot mark the later version as "already
seen"; dedup uses all keys.

Records named `snapshot|previous|baseline|state` are history: their `sig()` keys and work
ids seed the previous snapshot, and they never enter the candidate list.

## 3. Version chains

Per work, items are ordered by `version_rank` (descending), then by publication/index date:

- `6` notice (retraction, withdrawal, expression of concern, erratum, correction,
  corrigendum, editorial note)
- `3 + n` published version `n` (default `3`; `v2`/`version 2` in title/venue raises it)
- `1` preprint (arXiv, bioRxiv, medRxiv, Research Square, SSRN, `10.1101/`, `10.48550/`)

The first item is the canonical record; every item is preserved in
`version_chain[]` (`doi, arxiv, type, index_date, version_rank, source`) so a reader can
see that "preprint → published" was merged rather than duplicated, and a retraction stays
attached to the work it concerns.

## 4. Window classification

For each ranked work and window `[ws, we)`:

- `new` — at least one item in the window whose `sig()` keys are unknown, and the work is
  unknown (notices are classified `correction_or_retraction`).
- `version_update` — the work is known, a new item falls in the window, and its
  `version_rank` exceeds the rank of earlier items (e.g. published version of a known
  preprint).
- `correction_or_retraction` — the new item is a notice.
- `recovered_late` — the work is unknown but its dates precede `ws`: delayed indexing is
  reported, as backfill, instead of being dropped.
- `duplicate_noise` — a window item adds no unknown strong key (re-indexed duplicate);
  counted in `deltas[].suppressed.in_snapshot_or_known_version` and not alerted.
- `out_of_window` — nothing in this window.

`relevance_score` is `0.60 * topic_term_coverage + 0.25 * seed_similarity + 0.15 * recency`
(weights in `main.py`). Coverage counts a topic term 1.0 in the title, 0.6 in
abstract/venue; seed similarity is 1.0 for a gold/seed identity hit, otherwise the best
title-token Jaccard against seed titles; recency decays linearly over 730 days
(0.3 when no date). `rank_basis` in `screening` repeats the formula at run time.

## 5. Alert policy

- One alert per merged work per window (never per version), id
  `al_<window_index>_<sha1(work_id+class)[:10]>`.
- Suppressed, counted by reason in `deltas[].suppressed`: `already_alerted` (same id in an
  earlier window), `alert_cap` (more than 12 per window), `low_confidence_no_doi`,
  `in_snapshot_or_known_version`.
- Every emitted alert carries `delivery{channel: local_digest_file, target:
  alerts.md/alerts.json, delivered_at, status: written}`; `alerts.md` is the human digest.
  No outbound message is sent by the skill, so the delivery record states the truth.
- Alerts are delta signals. `alerts.md` and every alert object keep that disclaimer.

## 6. Idempotency and replay

State written after a run: `output/snapshot.json` (`item_keys` = strong keys,
`work_ids`, `alert_ids`, `window_end`) and `work/state.json` (same, compact).
Re-running the same window therefore yields `new: 0`, `alerts: 0`, and only
`suppressed` counts — the observable definition of idempotency used in self-checks.

Replay recipe for a disputed item:

1. Open `result.json`, take the candidate's `evidence_locator.source_file` + `evidence_locator.pointer` and read the record.
2. Check `index_date_field` and the date value against `windows[i].start/end`.
3. Check `version_chain` to see which versions existed before the window.
4. Check `query_id` in `query_log.json` (or `q_unmapped` with the flag) for the retrieval
   provenance, and `deltas/window_NN.json` for the classification of that window.
5. Compare against `snapshot.json` from the previous run to confirm the item was unknown.
