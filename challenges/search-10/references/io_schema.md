# Interface and output schema

Version 1.0.0. Applies to `scripts/main.py` + `scripts/engine.py`.
Companion to `SKILL.md` and `method.md`.

## 1. Invocation

```bash
python3 scripts/main.py --input /input --out /app/output
python3 scripts/main.py --input /input --records /app/work/hits.jsonl --max-k 10
python3 scripts/main.py --help
```

| flag | default | meaning |
|---|---|---|
| `--input` | `/input` | case directory, read only |
| `--out` | `/app/output` | output directory, created if absent |
| `--records` | none | extra record file(s) to add to the corpus |
| `--max-k` | 0 | candidate cap; 0 means case scope or 15 |
| `--quiet` | off | suppress the one-line stdout summary |

No flag is required. The script never depends on the working directory
(resources are located from `Path(__file__).resolve().parent`), never writes
outside `--out`, never opens a network connection, and always exits 0. A crash
inside the run still leaves a valid `result.json` behind, because a partial
result is written first and the exception path rewrites it with the error
recorded.

## 2. Input discovery

Read in this order, by content rather than by file name:

1. `case.json` (or the first `case*.json` found recursively).
2. Any JSON/JSONL/NDJSON file anywhere under `--input`: every dict that carries a
   title-like key plus at least one of abstract/DOI/year/author/venue/language is
   treated as a record, whatever the file calls itself.
3. CSV/TSV: rows with a title-like column and one other bibliographic column.
4. Markdown/text/YAML: read as context (e.g. `task.md`), never as records.
5. PDF/PNG/JPG/DOCX/XLSX/ZIP: recorded as unparsed material and excluded from
   evidence, with a `degradations` entry.

Recognised field aliases (case-insensitive, first non-empty wins):

| role | accepted keys |
|---|---|
| title | `title`, `titulo`, `titre`, `titel`, `paper_title`, `article_title` |
| abstract | `abstract`, `resumo`, `resume`, `summary`, `zusammenfassung`, `abstract_text` |
| DOI | `doi`, `doi_url`, `identifier` |
| language | `lang`, `language`, `body_language`, `language_code`, `idioma`, `lingua` |
| year | `year`, `publication_year`, `pub_year`, `ano` |
| venue | `venue`, `journal`, `source_title`, `publication`, `container_title` |
| authors | `authors`, `author`, `autores`, `creator`, `creators` |
| URL | `url`, `link`, `fulltext_url`, `landing_page` |
| version/links | `version`, `view_type`, `version_type`, `version_role`, `is_translation`, `is_translation_of`, `translation_of`, `duplicate_of`, `same_as` |

Question text: `task_instruction`, `research_question`, `question`, `user_query`,
`query`, `request`, `task`, `instruction`, `known_item`, `citation`, falling back
to the `topic` of a scope object, then to the head of `task.md`.

Case fields read: `case_id` (passed through unchanged), `output_contract`
(passed through field by field), any object whose key contains `scope` or
`workorder` (`topic`, `languages`/`lang`, `max_k`/`top_k`).

## 3. Output files

| file | content |
|---|---|
| `result.json` | full structured result; every `output_contract` field present |
| `candidates.csv` | one row per candidate, UTF-8 with BOM for spreadsheet review |
| `candidates.json` | same candidates as a list |
| `query_log.json` | one entry per planned query with hits, status, timestamp |
| `term_table.json` | concept table with per-variant provenance and weight |
| `verification.json` | deterministic audit of `result.json` against its sources |

### `result.json` top level

`case_id`, `status`, `stage`, `skill_version`, `question`, `anchor_extraction`,
`queries`, `query_plan` (when present), `candidates`, `screening`, `coverage`,
`dedup`, `term_table`, `term_expansion`, `gain_analysis`, `sources`,
`verification` (path or inline), `uncertainty`, `pending_human`, `errors`,
`degradations`, `changes`, `runtime`, `output_contract`, plus every extra key
declared by the input contract.

`status` ∈ `ok` | `partial` | `insufficient_evidence` | `input_error`.
`ok` requires: candidates present, every evidence quote verbatim, every DOI
present, no coverage gap. Otherwise `partial`. No records at all →
`insufficient_evidence`; unreadable or absent case → `input_error`.

### Candidate object

| field | meaning |
|---|---|
| `candidate_id`, `work_id`, `rank` | identity and order |
| `title`, `authors`, `year`, `venue`, `doi`, `url` | bibliographic fields, copied not generated |
| `language`, `language_confidence`, `language_evidence` | body language and how it was decided |
| `version_label`, `version_tags`, `version_confidence`, `version_basis` | declared or inferred version role |
| `n_views`, `languages_in_work`, `view_records` | merged views of the same work (`rec_id:lang:doi`) |
| `source_db`, `source_file`, `retrieved_at` | provenance of the hit (`local_corpus`, file path, UTC timestamp) |
| `query_id` | the query that produced it, must exist in `query_log.json` |
| `relevance_score` | see `method.md` §6 |
| `matched_terms` | per concept: surface form, field, variant language, method, alignment |
| `relevance_reason` | human-readable version of `matched_terms` |
| `evidence_snippet`, `evidence_locator`, `evidence_quote_match` | verbatim quote, locator, match quality |
| `flags` | `missing_doi`, `language_low_confidence`, `quote_unverified` |

### `coverage` object

`question_language`, `target_languages_declared`, `languages_with_results`,
`records_in_corpus`, `works_after_dedup`, `candidates_returned`,
`non_source_language_works`, `duplicates_merged`, `dedup_rules_applied`, `gaps`,
`recall_estimate` (`value: null` unless the case supplies a reference set, with
`method` and a `proxy` number).

### `verification.json`

```json
{
  "checked_at": "<UTC>",
  "candidates": 3,
  "contract_fields": 8,
  "contract_missing": [],
  "unverified_candidates": [],
  "verdict": "pass"
}
```

Checks: every contract field present; every `evidence_snippet` still found in its
`source_file`; every `query_id` present in the query log; one candidate per work.

## 4. Minimal example (示例 — synthetic data, not a case result)

`/input/case.json`:

```json
{
  "case_id": "EXAMPLE-CASE-001",
  "task_instruction": "Which paper reports piroptose in macrophages?",
  "output_contract": {"query": "string", "candidates": "list", "notes": "string"},
  "organizer_supplied_scope": {"languages": ["pt", "en"], "max_k": 5},
  "artifacts": [{"path": "records.jsonl"}]
}
```

`/input/records.jsonl` (illustrative, invented records):

```json
{"id": "x1", "title": "Piroptose em macrófagos: um estudo in vitro", "abstract": "A piroptose foi induzida em macrófagos murinos.", "year": 2021, "language": "pt", "doi": "10.0000/example.pt", "journal": "Revista Exemplo"}
{"id": "x2", "title": "Pyroptosis in macrophages: an in vitro study", "abstract": "Pyroptosis was induced in murine macrophages.", "year": 2021, "language": "en", "doi": "10.0000/example.pt", "is_translation_of": "10.0000/example.pt"}
```

Command and shape of the result:

```bash
python3 scripts/main.py --input ./input --out ./output
# status=partial candidates=1 langs=['pt','en'] check=pass
```

```json
{
  "case_id": "EXAMPLE-CASE-001",
  "status": "partial",
  "candidates": [{
    "candidate_id": "c01", "work_id": "w01",
    "language": "pt", "n_views": 2, "languages_in_work": ["en", "pt"],
    "version_label": "translation_view",
    "query_id": "q01", "relevance_score": 1.0,
    "evidence_locator": "input/records.jsonl#$/...:abstract[s0]+0",
    "evidence_quote_match": "exact",
    "flags": []
  }],
  "coverage": {"duplicates_merged": 1, "works_after_dedup": 1,
               "languages_with_results": ["pt", "en"]},
  "query": null, "notes": null
}
```

`query` and `notes` are `null` because the contract field has no computed value;
the key is present, which is what the contract requires. `status` is `partial`
because a coverage gap (a declared language without a verified candidate) is
recorded — the exact reason is in `coverage.gaps`.

## 5. Failure-mode expectations

| input | expected result | exit |
|---|---|---|
| empty directory (no case.json) | `status: input_error`, queries listed as `not_executed_no_backend`, `degradations` + `uncertainty` explain the missing corpus and case | 0 |
| malformed `case.json` | `input_error` or `insufficient_evidence`, parse error in `errors`, contract fields defaulted to `null`/`[]` | 0 |
| valid case, no records | plan-only result, `pending_human` names the retrieval step | 0 |
| records with no DOI | candidates kept, `missing_doi` flag, `partial`, `uncertainty` entry | 0 |
| unreadable PDF only | `degradations` entry, no fabricated candidate | 0 |

## 6. Test recipe (reproducible, ~1 s)

```bash
mkdir -p /tmp/t/input && cp case.json records.jsonl /tmp/t/input/
python3 -B scripts/main.py --input /tmp/t/input --out /tmp/t/output
python3 -c "import json;d=json.load(open('/tmp/t/output/result.json'));print(d['status'],len(d['candidates']))"
python3 -c "import json;print(json.load(open('/tmp/t/output/verification.json'))['verdict'])"
mkdir -p /tmp/e/input && python3 -B scripts/main.py --input /tmp/e/input --out /tmp/e/output; echo $?
printf '{"case_id":' > /tmp/e/input/case.json && python3 -B scripts/main.py --input /tmp/e/input --out /tmp/e/output; echo $?
```
