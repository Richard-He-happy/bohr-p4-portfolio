# Checklist, rubric map and worked example

## 1. Before submitting a run (verify each line on the artifacts)

1. `result.json` parses; every key of the input `output_contract` is present (`verification.checks[contract_fields].pass = true`).
2. `case_id` equals the input value (not `"unknown"` unless the case truly lacks it).
3. `inventory.csv` row count = `library.file_count`; every row has a 64-hex `sha256` (junk/unreadable included).
4. `duplicates` groups are hash-identical; each group has exactly one canonical member.
5. `versions.chains[]` documents all carry distinct `sha256`; `confidence` and `evidence` are filled.
6. Every `questions[].evidence[]` has `quote`, `locator`, `sha256`; `verification.checks[quotes_verbatim].pass = true`.
7. `questions[].verdict = insufficient_evidence` has `missing_concepts` or a `note` explaining the gap.
8. `pending_human`, `failures`, `degradations`, `errors` were read; nothing that failed is reported as complete.
9. `operations.log` contains scan / hash_dedup / version_chains / qa / organize / artifacts_written lines.
10. `reorganize_plan.csv` covers every material (copied, skipped or deferred).

Run `python3 scripts/main.py --mode verify --output <out>`; `verify.json.status` must be `pass`.

## 2. Rubric → field mapping (library-04)

| Rubric item | Evidence in the deliverable |
|---|---|
| Task completion (15) | `status`, `summary`, `library`, `questions[].verdict`, `coverage_dimensions` |
| Result correctness (15) | verbatim `quote` + `locator` + `sha256` per claim; version conflict on stale citations; unreadable files never cited |
| Result completeness (5) | six `coverage_dimensions`: file types, metadata fields, directory depth, duplicates, versions, permission/source |
| Verifiability (5) | sha256 per file, `operations.log`, `verify.json`, `changes[].verified`, re-runnable `--mode verify` |
| Quality gain (15) | extractive answers instead of prose; explicit absence verdicts; duplicate/version awareness |
| Efficiency gain (5) | one command, one retrieval pass, library + versions + answers together (`summary` counts) |
| Gain checkability (5) | both conditions can use the same inputs; every output carries hashes/locators, so the two runs are diffable |
| New capability (5) | hash-based dedupe, version chain with confidence, version-aware citation, term-coverage absence criterion |
| Method improvement (5) | chunking with source locators, per-field metadata provenance, warning taxonomy instead of crashes |
| Innovation evidence (5) | `versions[].evidence` (similarity, order agreement) and `verification` make the claims self-auditing |
| Usability (3) | SKILL.md §2 invocation, §12 minimal example, `--help` |
| Stability (4) | stdlib only, no network, per-file isolation, exit 0, partial-first |
| Exception handling (3) | failure table in SKILL.md §10 ↔ `failures[]`, `skipped[]`, `pending_human[]` |
| Docs (3) | SKILL.md (14 sections) + this file + `schema.md` + `method.md` |
| Reusability (4) | CSV/JSON schemas, stable column names, no personal paths, deterministic targets |
| Sharing value (3) | the record format is transferable to any file library; thresholds and rules are published |

## 3. Worked example — ILLUSTRATIVE, NOT AN OFFICIAL CASE RESULT

Input (2 files, 1 question):

```
case.json   {"case_id":"demo-x","output_contract":{"inventory":"…","answers":"…"},
             "questions":[{"id":"q1","question":"How much compound X was used?"}]}
reports/assay_v1.txt   "… the assay used 10 mg of compound X in 5 mL buffer …"
reports/assay_v2.txt   "… the assay used 25 mg of compound X in 10 mL buffer …"
reports/assay_v2_copy.txt  (byte-identical to assay_v2.txt)
```

Command: `python3 scripts/main.py --input /input --output /app/output`

Illustrative result (numbers invented for illustration):

```json
{"case_id": "demo-x", "status": "ok",
 "duplicates": [{"group_id": "DG01", "canonical": "reports/assay_v2.txt", "count": 2,
                 "members": ["reports/assay_v2.txt", "reports/assay_v2_copy.txt"]}],
 "versions": {"chain_count": 1, "chains": [{"chain_id": "VC01", "latest": "reports/assay_v2.txt",
              "confidence": "high", "documents": [{"rel": "reports/assay_v1.txt", "is_latest": false},
              {"rel": "reports/assay_v2.txt", "is_latest": true}]}]},
 "questions": [{"qid": "q1", "verdict": "supported", "answer_mode": "extractive",
                "evidence": [{"rel": "reports/assay_v2.txt", "locator": "reports/assay_v2.txt#line2-2",
                              "quote": "The assay used 25 mg of compound X in 10 mL buffer."}]}],
 "conflicts": [{"type": "version_conflict", "cited_version": "reports/assay_v1.txt",
                "latest_version": "reports/assay_v2.txt"}]}
```

Reading it: the duplicate copy is not indexed twice, the v1/v2 pair is recognised as one chain with v2 latest, and citing v1 raises a
`version_conflict` instead of silently answering from an outdated file. A question about a term absent from every file returns
`verdict = insufficient_evidence` with that term in `missing_concepts` — the run does not manufacture an answer.

## 4. Frequently asked

- **Why is a file not cited?** It has no extractable text (`readability` column) — see `failures[]` and `pending_human[]`.
- **Why is a version chain `low` confidence?** The filename token order and the mtime order disagree; the chain is still reported with `evidence`.
- **Why "insufficient_evidence" when the term exists in the library?** Terms exist but never co-occur in one chunk at coverage ≥ 0.40 — the note says so; re-ask with the document's own wording.
- **Can I change the thresholds?** Yes: `cov < 0.34` and the 0.60/0.40 verdict cut-offs in `scripts/main.py`; document the change here and in `method.md`.
- **Where do I put the GitHub link?** In `GITHUB_URL.txt` at the root of the submitted directory, one URL on the first line (it is not part of the loadable skill package).
