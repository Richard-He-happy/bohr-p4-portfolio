# Method, stop rules, and self-check (research-question-retrieval 1.0.0)

This file documents what `scripts/main.py` + `scripts/retrieval.py` actually do, so a reviewer can
reproduce or audit a run. Every claim here matches the code; if code and text disagree, code wins.

## 1. Pipeline (deterministic, offline)

```
discover /input  ->  normalise records  ->  decompose question  ->  query waves
     ->  BM25 score on snapshot  ->  screen all records  ->  dedupe/cluster
     ->  rank  ->  coverage + conflicts + baseline  ->  result.json + logs
```

No network call is made. Nothing is looked up from memory. If a paper is not in the input
snapshot, it does not appear in `candidates`.

## 2. Question reading

1. `q_of()` reads, in order: `case.json` keys `task_instruction`, `research_question`,
   `question`, `task`, `instruction` (recursive lookup), then a `# 研究问题` /
   `# Research question` heading in `task.md`, then `organizer_supplied_scope.topic`.
2. The chosen field name is recorded in `sources[]` as `question_field`, so the reviewer can see
   which text drove the decomposition.
3. If no question text exists, `sub_questions` stays empty, `uncertainty` gets a
   `research_question` entry, and only the supplied records are screened. That is a declared
   limitation, not an error.

## 3. Facet detection and term expansion

`facets(q)` matches cue phrases from `references/lexicon.md` against the question. Five facets:
`method`, `mechanism`, `outcome`, `comparison`, `gap`. Each hit becomes an anchor word set, then
`expand()` adds synonyms from the `## syn` block (both directions) and tokenised variants
(hyphen/suffix trimming happens through tokenisation, not stemming).

Expansion is capped: 14 terms per facet group, 16 for the topic anchor, 12 default in `expand()`.
This is the anti-divergence control — expansion grows recall but cannot run away.

`anchors(q)` pulls quoted phrases and 2–4 word capitalised/technical phrases out of the question
and demotes phrases that consist only of facet vocabulary, so the topic anchor stays topic-like.

## 4. Decomposition and wave planning

`decompose()` emits at most 6 sub-questions:

| sub-question | facet | wave | why that wave |
|---|---|---|---|
| `sq01` | `core` | 1 | topic anchor only; establishes the in-scope set cheaply |
| method | `method` | 2 | needs the topic anchor as a filter |
| mechanism | `mechanism` | 2 | needs the topic anchor; independent of method |
| outcome | `outcome` | 3 | runs after method/mechanism clarify vocabulary |
| comparison | `comparison` | 3 | needs both sides of a contrast to be in scope |
| gap | `gap` | 3 | limitation wording is only informative once core hits exist |

Wave 1 is a prerequisite for waves 2–3 (all queries carry the topic anchor group and require at
least one anchor hit). Waves 2 and 3 are parallel within themselves. Every sub-question stores
`groups` (with `role`, `label`, `terms`, `min_hits`), `derived_from` (the cue or question text that
created it) and `query_ids`, so the plan is auditable without re-running.

If the question is Chinese and anchors exist, one extra cross-language variant sub-question is
added at wave 1.

## 5. Retrieval and scoring

`build_index()` builds a weighted term-frequency index: title ×3.0, keywords ×2.0, abstract ×1.0,
venue ×0.5, authors ×0.3. IDF is `log(1 + (N - df + 0.5)/(df + 0.5))`. `score()` uses a BM25-style
saturation `idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len/avgLen))` and scores each concept group
by its single best matching term; a record matches a query only if **every** group matches
(`ok`), which is what keeps AND semantics honest.

`execute()` applies the year window before scoring, writes one `query_log` entry per query with
`hits`, `returned_ids`, `filters`, `status` (`ok` / `empty`) and `retrieved_at`, and stops early at
the query budget. `seen` accumulates per-cluster provenance: best score, best sub-question, best
query id, matched terms and timestamp — this is where `query_id`/`retrieved_at` on each candidate
comes from.

Final `relevance_score = 0.55 * BM25_norm + 0.30 * facet_coverage + 0.15 * recency`, where
`BM25_norm = score/(score+4)`, facet coverage counts distinct non-topic groups matched (÷2, capped
at 1), and recency is the position of the year inside the requested window. The weights are a fixed
policy, not tuned on any case; they are written into `changes[]`.

## 6. Screening (all records, not just hits)

Every record in the snapshot gets exactly one decision in `screening.decisions`:
`include`, `exclude`, or `defer`.

- `exclude` triggers: outside year window; language mismatch; exclude-term hit; retraction/
  corrigendum/editorial/comment-on markers; missing title; duplicate suppression.
- `defer` = passes screening but matched no sub-question. It is listed in `missing[]` with the
  reason, because "in scope but unattributed" is exactly what a reviewer needs to see.
- Counts land in `screening.counts` (`records_screened`, `include`, `exclude`, `defer`,
  `below_cutoff`).

Screening is keyword-based and deliberately conservative: it never uses the model's own judgement
about scientific merit, and it never removes a record because it looks unimportant.

## 7. Deduplication

Union–find over three signals: identical DOI, identical normalised title, and ≥90% title-token
Jaccard with |Δyear| ≤ 1. Each cluster keeps all member exports in `provenance[]`, sets
`duplicate_export_merged`, and counts into `metrics.n_dup_merged`. The cheapest record id survives
as `candidate_id`. This is what stops a synthetic duplicate export from being counted twice.

## 8. Stop rules (explicit, three independent triggers)

`stopping.rule` states the policy; `stopping.waves` shows per-wave query and hit counts:

1. **Coverage stop** — every sub-question has ≥1 included candidate → `all_sub_questions_covered`.
2. **Diminishing-returns stop** — a wave adds no new cluster to `seen`.
3. **Budget stop** — query budget (`--max-queries`, default 24) reached.

If gaps remain after wave 3, `stopping.reason = gaps_after_wave_3` and each gap carries an
`action` (`widen expansion or add records`). A gap is reported, never filled with a plausible
citation.

## 9. Conflicts

`pol()` classifies each abstract/title as positive / negative / mixed by lexicon phrases
(negation is checked first, so "no significant improvement" is not read as positive). Two
candidates conflict when they share ≥2 topic tokens and have opposite polarity. Conflicts are
`confidence: low (lexical polarity heuristic)` by construction and are copied into
`pending_human` with the action "read both; decide which applies". They are surfaced, never
resolved by the script.

## 10. Baseline control (usage gain, self-contained)

`baseline()` runs one flat OR query (the 8 longest content tokens of the question) over the *same*
snapshot with the *same* `max_k`, no decomposition, no expansion, no dedupe, no screening, and
reports `hits`, `returned`, `candidate_ids`, `in_scope_share`, `facets` covered and
`duplicate_exports_in_returned`. `metrics.comparison_vs_baseline` puts both sides side by side on
the same snapshot. This is an internal control, explicitly annotated as *not* the organizer
whiteboard; the platform supplies the official comparison.

`skill_in_scope_share_by_construction` is named that way on purpose: screening decides inclusion,
so that number is 1.0 by construction and is not evidence of quality. Facet coverage, duplicate
leakage and query count are the meaningful deltas.

## 11. Self-check (`--self-check`)

Writes `selfcheck.json` and re-checks the produced `result.json`:

| check | failure recorded as |
|---|---|
| every candidate has title / source_db / retrieved_at / query_id / relevance_reason / evidence_snippet | `missing_<field>` |
| candidate `query_id` exists in `queries[]` | `query_id_not_in_log` |
| DOI matches `^10\.\d{4,9}/\S+$` | `malformed_doi` |
| `evidence_snippet` is a verbatim substring of its own source record | `snippet_not_found_in_source_record` |

The snippet check is the anti-fabrication guard: a snippet that cannot be found in the source
record is flagged, not accepted. Status is `pass` or `warn`; `warn` is honest, not a crash.

## 12. Known limits (do not overstate)

- **Recall is not measured.** No gold labels and no live database. `coverage.recall_estimate` is
  `null` with a reason; `P@k`, `nDCG@k`, `Recall@k` are not computed and never guessed.
- **Snapshot-bound.** Only records present in `/input` can be retrieved; a real systematic review
  needs live databases. This is stated in `uncertainty` on every run.
- **Lexical, not semantic.** No embeddings, no stemming beyond tokenisation, no transliteration.
  Vocabulary outside `lexicon.md` relies on the question's own tokens.
- **Conflict detection is heuristic** (polarity + token overlap) and labelled `low` confidence.
- **Screening is rule-based**; it cannot judge study quality, so risk-of-bias is out of scope.
- **Metadata is passed through, never repaired.** A missing DOI stays `null` and lowers
  `metadata_confidence`; nothing is looked up to fill it.

## 13. Reviewer checklist (run in this order)

1. `python3 scripts/main.py --help` → exit 0.
2. `python3 scripts/main.py --input <case dir> --output <out dir>` → exit 0, `result.json` valid.
3. `python3 scripts/main.py ... --self-check` → `selfcheck.json` status `pass`/`warn`, read issues.
4. Check every `output_contract` key from the input exists in `result.json` with the same name.
5. Check `case_id` is byte-identical to the input.
6. Spot-check 2 candidates: does `query_id` exist in `queries[]`? does `evidence_snippet` appear
   in the source record? does `retrieved_at` match the query entry?
7. Confirm `status` matches reality: `ok` only when records, candidates and no gaps/errors.
8. Confirm `uncertainty` mentions gold labels / snapshot bound, and `missing[]` lists deferred
   records.
