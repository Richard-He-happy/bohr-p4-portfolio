# Method note — cross-lingual known-item retrieval

Companion to `SKILL.md`. This file records the rules the scripts actually apply,
so a reviewer can re-derive every number in `result.json` by hand.

Version 1.0.0. Applies to `scripts/main.py` and `scripts/engine.py`.

## 1. What the method does and does not do

It decides, for a research question written in one language, which supplied
records answer it, which language and version each record is, and which records
are the same work in different languages. It does not translate whole papers, it
does not browse the web, and it never invents a record.

Offline constraint: the harness provides no search API. Retrieval therefore runs
over the record corpus present in the case (`/input/**` JSON, JSONL, CSV, TSV) or
over a record file an agent collected with its own search tool and passed via
`--records`. When no corpus exists the run stops at plan stage and says so
(`status: insufficient_evidence`), listing the exact per-language queries that
still need to be executed.

## 2. Pipeline

| step | function | product |
|---|---|---|
| 1 question parse | `concepts_of` | concept list, each with weighted variants |
| 2 language ID | `langid` | question language + evidence; per-record language |
| 3 variant expansion | `expand` | rule-derived variants for languages missing from the table |
| 4 query planning | `plan` | one AND-of-ORs query per target language + citation-anchor query |
| 5 retrieval | `retrieve` | per-query hit count, status, timestamp (`query_log.json`) |
| 6 scoring / screening | `score`, `build` in `main.py` | ranked candidates + include/exclude reasons |
| 7 version merge | `cluster` | work clusters; duplicates counted once |
| 8 evidence alignment | `evid` | verbatim quote + locator per candidate |
| 9 audit | `checks` in `main.py` | `verification.json` |

## 3. Concept table and variant provenance

Every variant records `method` and `weight`, and both appear in `term_table.json`
and in each candidate's `matched_terms`, so a reviewer can tell how a hit was
found.

| method | weight | origin |
|---|---|---|
| `glossary_exact` | 1.0 | `references/glossary.tsv`, one row per concept |
| `glossary_abbrev` | 1.0 | the `abbrev` column of the same row (e.g. `ROS`, `RCT`) |
| `question_literal` | 1.0 | content word of the question not covered by the table |
| `cognate_rule` | 0.6 | suffix rewrite between EN and PT/ES (see below) |

Cognate rules (applied only when the pair language is absent from the table):
`-cao/-coes → -tion/-tions`, `-dade → -ity`, `-mento → -ment`, `-ico → -ic`,
`-oso → -ous`, `-encia → -ence`, `-logia → -logy`, `-ite → -itis`, `-ose → -osis`,
and the reverse direction. A cognate variant is kept only if the produced string
is longer than 6 characters or already occurs in the corpus; both the rule and
the corpus test are recorded (`found_in_corpus`). This is a heuristic: it is
marked `cognate_rule` everywhere and never outranks a glossary term.

Keywords: a concept present in the question gets weight 1.5; literal terms 1.0;
variants inherit their method weight, so a title match on a glossary term scores
1.0 while a title match on a cognate guess scores 0.6.

## 4. Language identification

Order of decision, first hit wins:

1. Script: kana → `ja`; more than 15% CJK ideographs → `zh`; Hangul → `ko`;
   Cyrillic → `ru`. Confidence 0.93–0.97, evidence `script:<code>`.
2. A declared field (`language`, `lang`, `idioma`, `lingua`, `body_language`, …)
   is trusted as-is, confidence 0.95, evidence `declared_field`.
3. Otherwise Latin-script scoring over the first 400 characters of title +
   abstract: stopword hits per language (EN/PT/ES/FR/DE), +1.5 per diacritic
   cluster (`ãõ`, `ñ`, `êèàûœ`, `ßäöü`, capped at 3), +0.3 per productive suffix.
   The winner needs ≥2 points; below that the language is `unknown`.

`language_evidence` is copied into each candidate so a wrong label can be
audited. Records whose confidence is below 0.6 carry `language_low_confidence`
and the run reports `partial`.

## 5. Query planning

For each target language, one query of the form
`("term A" OR "term B") AND ("term C" OR "term D")`, built from that language's
variants only. A concept with no variant in that language is listed in
`missing_concepts`; a language with no variant at all gets `status:
no_term_mapping` and is not silently dropped. One extra query carries the
citation anchors extracted from the question (DOI, year, capitalised
author-like tokens) and is language-neutral.

Target languages come from the case scope when present, otherwise from the
question language plus the three best-covered languages in the concept table
(cap 6). The choice is written to `coverage.target_languages_declared`.

`query_log.json` records per query: `query_id`, `lang`, `raw`, `expanded`,
`methods`, `db` (`local_corpus`), `filters`, `hits`, `status`, `error`,
`retrieved_at`, `missing_concepts`. `status` is one of `ok`, `empty_result`,
`no_term_mapping`, `not_executed_no_backend`.

## 6. Scoring

```
concept_score = Σ_concepts best_variant_match_weight / Σ_concepts weight
best_variant_match_weight = variant.weight × field_multiplier
field_multiplier: title 1.0, abstract 0.75
score = min(1.0, concept_score + anchor_bonus)
anchor_bonus: DOI exact 0.5, publication year in question 0.15,
              author surname in the author list min(0.25, 0.12 × hits)
```

A matched variant is scored once, at its first and strongest occurrence (title
before abstract), so long abstracts cannot inflate a weak match.

Threshold: `max(0.12, 0.35 × best score in the corpus)`, computed per run, not
fixed in advance. Every record is either kept or listed in `screening` with one
of `no_query_term_matched`, `below_threshold`, `max_k_cut`,
`duplicate_view_merged`. `max_k` comes from `--max-k`, else the case scope, else 15.

Each match records `alignment`: `native` (variant language equals record
language), `abbrev` (language-neutral abbreviation), or `loanword` (the term is
written in a language other than the record's declared body language). Loanword
matches are kept but surfaced, because they are exactly where "words correspond,
meaning does not" errors hide.

## 7. Version merge (deduplication)

Union-find over the corpus, rules in this order, each counted in
`coverage.dedup_rules_applied`:

1. `same_doi` — normalised DOI equality (prefix, case and trailing punctuation
   stripped).
2. `same_declared_work_id` — equal `work_id` / `record_id` / `openalex_id`.
3. `declared_<field>` — `is_translation_of`, `translation_of`, `duplicate_of`,
   `same_as` pointing at another record's DOI, record id or title.
4. `title_jaccard>=0.9` — token Jaccard on normalised titles, at least 3 tokens,
   and not both records carrying different known years.

The highest-scoring view becomes the work's representative; the others are
listed in `screening` as `duplicate_view_merged` and in the candidate's
`view_records`. One candidate per work: version inflation cannot increase the
count.

`version_label` comes from declared fields when present (`translation_view`,
`original_view`, `exact_duplicate`, `abstract_only_view`), otherwise
`multilingual_version_set` when a work has several languages, otherwise
`single_view`. `version_confidence` drops to 0.45 when the label is inferred
rather than declared, and `version_basis` shows the raw declared fields.

## 8. Evidence alignment

For each candidate the best sentence of the record's own title or abstract (most
distinct matched surface forms, title preferred) is quoted verbatim, truncated at
400 characters, with the locator

```
<source file>#<json pointer or row index>:<field>[s<sentence index>]+<char offset>
```

`evidence_quote_match` is `exact`, `deaccented_normalized` (equal after accent
folding, which is not a verbatim match) or `failed`. A failed quote sets
`quote_unverified`, adds a `pending_human` entry and downgrades the run to
`partial`. The quote is never rewritten to fit.

## 9. Baseline ablation (what the `gain_analysis` numbers mean)

On the same corpus, the same tokenizer and the same threshold, a baseline run
uses only the literal question tokens in the question language, without the
concept table, without cognate variants and without version merging. Both runs
report records kept, languages reached and evidence-verified count.

This is a structural comparison of the two configurations on one corpus. It is
not the platform's baseline, it is not a recall measurement (no reference set
exists in the case), and it cannot show quality on papers that are absent from
the corpus. `coverage.recall_estimate.value` is `null` for that reason.

## 10. Degradation branches

| trigger | detection | behaviour |
|---|---|---|
| no corpus | zero record-like objects | `insufficient_evidence`, queries listed as `not_executed_no_backend`, no candidates |
| bad JSON | parse error, JSONL fallback failed | error entry, file skipped, run continues |
| PDF/PNG/DOCX/XLSX | extension | `degradations` entry, excluded from evidence |
| no glossary | file missing | literal-term concept table only |
| term has no translation | variant set empty for a language | `missing_concepts`, `no_term_mapping` query status |
| language uncertain | confidence < 0.6 | `unknown` or flagged candidate, `partial` |
| translation service | not applicable offline | `degradations` entry where a translation step was skipped |
| empty result | all records below threshold | `insufficient_evidence`, threshold recorded |
| quote not found | substring test fails | `quote_unverified`, `pending_human` |
| budget exhausted | 780 s elapsed | the last valid `result.json` stays; no partial writes |

## 11. Rubric to field map

| rubric item | field or artefact |
|---|---|
| task completed end to end | `status`, `queries`, `candidates`, `coverage` |
| results correct | `doi`, `language`, `version_label`, `matched_terms.surface` |
| results complete | `coverage.languages_with_results`, `gaps`, `duplicate_view_merged` |
| verifiable | `query_id`, `source_file`, `retrieved_at`, `evidence_locator`, `quote_match` |
| quality gain | `gain_analysis.baseline` vs `.skill` |
| efficiency gain | `gain_analysis.skill.queries`, per-query `hits`/`status` |
| gain verifiability | `verification.json`, `changes`, `runtime` |
| new capability | `term_table`, `term_expansion`, `dedup.rules`, `version_basis` |
| method improvement | `method` per variant, `alignment`, `score` components |
| stability | `errors`, `degradations`, `runtime.seconds` |
| documentation | `SKILL.md`, this file, `io_schema.md` |

## 12. Limits

* Lexical matching only: no embeddings, so paraphrase without shared surface
  forms is missed. Cognate rules cover EN↔PT/ES, not JA/ZH compounds.
* German compounds written as one word are not split.
* Japanese and Chinese matching is character-sequence based; no word segmentation.
* Year and author anchors assume a citation-style question; free-text questions
  simply get no bonus.
* Offline: no live coverage claim is possible, and none is made.

## 13. Worked shape (示例 — synthetic, not a real paper, not a case result)

Question (illustrative only): an English sentence containing the concept
`pyroptosis` plus a 2021 year.

```
term_table: concept pyroptosis, variants
  en pyroptosis      glossary_exact 1.0
  pt piroptose       glossary_exact 1.0
  zh 细胞焦亡         glossary_exact 1.0
  ja パイロトーシス    glossary_exact 1.0
queries: q01 lang=pt raw=("piroptose") hits=1 status=ok
         q02 lang=zh raw=("细胞焦亡")   hits=1 status=ok
         q03 lang=und raw=PY:2021      hits=2 status=ok
candidate c01: language=pt version_label=single_view n_views=1
         evidence_locator=/input/records.jsonl#$/items[3]:abstract[s1]+0
         evidence_quote_match=exact
```

The record ids, titles and counts above are illustrative placeholders. Only runs
written by the scripts on a real case directory count as results.

## 14. Maintenance

* New concept: append a row to `glossary.tsv`, keep `concept_id` stable.
* New stopword or suffix cue: edit `STOP` / `SUF` in `engine.py`; re-run the
  minimal case and compare `verification.json`.
* New dedup rule: add it to `cluster()` **and** to section 7 of this file; the
  rule name appears in `coverage.dedup_rules_applied`.
* Any change to scoring must keep the threshold rule adaptive; a fixed threshold
  overfits one corpus.
