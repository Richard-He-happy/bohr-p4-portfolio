# Output schema — research-library-qa v1.0.0

All paths below are relative to `/app/output` unless stated otherwise.

## 1. result.json (top level)

| Key | Type | Meaning |
|---|---|---|
| `case_id` | string | copied verbatim from `case.json` (`case_id`/`caseId`/`id`, else `"unknown"`) |
| `skill` | object | `{name, version}` |
| `status` | enum | `ok` \| `partial` \| `insufficient_evidence` \| `input_error` |
| `summary` | string | counts: files, materials, readable, duplicate groups, chains, question verdicts |
| `input` | object | `{dir, case, task_chars}` |
| `library` | object | `root`, `file_count`, `material_count`, `total_bytes`, `by_class`, `by_role`, `max_dir_depth`, `inventory_csv`, `dirs` |
| `inventory` | array | one object per file (see §2) |
| `metadata` | object | `fields`: field → `{files, sources{provenance: count}}`; plus `note` |
| `duplicates` | array | duplicate groups (see §3) |
| `versions` | object | `chain_count`, `chains[]`, `path` |
| `questions` | array | per-question answer records (see §4) |
| `answers_path` | string | `"answers.md"` |
| `coverage_dimensions` | object | six dimensions of completeness (see §5) |
| `sources` | array | `{id, rel, sha256, kind}` for every scanned file |
| `changes` | array | `read_only` marker + one `copy` record per canonical copy (`verified` bool) |
| `conflicts` | array | flattened `questions[].conflicts` |
| `skipped` | array | `{path, reason}` — junk files, `max_files_reached`, unreadable record |
| `failures` | array | `{rel, issue, handled, action}` per file warning |
| `operations` | object | `path`, `count`, `counts{files, materials, hashed, text_extracted, skipped, failures, copied}` |
| `uncertainty` | array | `{id, level(2|3), statement, why}` |
| `pending_human` | array | `{item, issue, needed, impact}` |
| `degradations` | array | `{item, reason, effect}` |
| `errors` | array | `{stage, path, error}` (non-fatal) |
| `verification` | object | self-audit result (see §6) |
| `output_contract_fields` | array | echoed contract keys |
| `runtime` | object | script, skill_version, finished, wall_seconds, args |
| *contract keys* | any | every input `output_contract` key, aliased to the matching section or `null`/`[]` |

Alias used when filling a contract key: `inventory|file_list|files` → `inventory`; `library|tree` → `library`;
`version_chain|versions` → `versions`; `answers|qa|questions|evidence|citations` → `questions`;
`operations|log` → `operations`; `coverage` → `coverage_dimensions`; others map to the key of the same name.

## 2. inventory[] entry

```json
{"rel": "reports/assay_v2.txt", "class": "text", "size_bytes": 142, "sha256": "…64 hex…",
 "readable": true, "duplicate_of": null, "version_chain": "VC01", "text_chars": 138,
 "metadata": {"title": {"value": "assay_report_v2", "source": "filename"},
              "mtime": {"value": "2026-01-02T03:04:05Z", "source": "stat"}}}
```

`metadata.*.source` is one of `filename`, `stat`, `content:<extractor>`, `sidecar:<file>` — every field states where it came from.

## 3. duplicates[] entry

`{group_id: "DG01", sha256, size_bytes, count, canonical, members[], rule}` — grouping is by **content hash only**;
the canonical member is the earliest mtime, then the shortest path.

## 4. versions and questions

`versions.chains[]` = `{chain_id:"VC01", stem, latest, confidence:"high|medium|low", documents[{rel, sha256, size_bytes, mtime, version_token, text_chars, is_latest}], evidence{distinct_sha256, pairwise_text_similarity[], name_rank_matches_time_order, rule}}`.

`questions[]` = `{qid, question, verdict, answer, answer_mode:"extractive", evidence[], best_coverage, missing_concepts[], conflicts[], note, asked_in_case_at}`.

`evidence[]` = `{source_id, rel, sha256, kind, locator, location{file, chunk, char_span[2]}, quote, coverage, score, quote_checked_in_chunk}`.

`verdict`: `supported` (best term coverage ≥ 0.60) · `partially_supported` (0.40–0.60) · `insufficient_evidence` (< 0.40 or no verbatim quote) · `no_question`.

## 5. coverage_dimensions

`file_types{count, classes}` · `metadata_fields{count, fields[]}` · `directory_depth{max_depth, root_files}` · `duplicate_files{groups, redundant_files}` · `version_differences{chains, stems[]}` · `permission_and_source{readable, unreadable, permission_denied}`.

## 6. verification

```json
{"status": "pass|fail",
 "checks": [{"check": "contract_fields", "n": 5, "missing": [], "pass": true},
            {"check": "sha256_from_disk", "n": 11, "mismatch": [], "missing_files": [], "pass": true},
            {"check": "quotes_verbatim", "n": 4, "failures": [], "pass": true},
            {"check": "artifacts", "pass": true}]}
```

## 7. inventory.csv columns

`rel, role, class, size_bytes, sha256, mtime, readable, readability, duplicate_of, version_chain, text_chars, extract_method, title, version_token, year, author, metadata_provenance`

`readability` lists the extractor warnings (`|`-joined); `metadata_provenance` is a JSON object field → provenance.

## 8. Locator grammar

`<rel path>#<locator>` where locator is `p<N>.l<a>-<b>` (PDF page/lines), `p.<N>` (DOCX paragraph), `<sheet>!r<N>` (XLSX row),
`line<a>-<b>` (text/CSV/MD/JSON), `stream<N>.l<a>-<b>` (PDF page mapping unresolved). Multiple chunks: `<first>..<last>`.
