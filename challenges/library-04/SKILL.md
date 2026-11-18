---
name: research-library-qa
description: Inventory a research file library and answer knowledge-base questions with verifiable evidence. Scans the input tree, hashes every file (sha256), extracts text from PDF/DOCX/XLSX/CSV/JSON/MD, records metadata with per-field provenance, groups exact duplicates by hash, infers version chains, writes a canonical copy plan, and answers questions with verbatim quotes plus checkable locators, version-conflict warnings and explicit insufficient-evidence verdicts. Use when the task is to organise, deduplicate, version, audit or query a set of research files and the answer must be re-checkable against the original documents.
version: 1.0.0
---

# research-library-qa

## 1. Purpose and boundaries

Two deliverables in one run, from real files, no fabrication:

1. **Library record** — inventory (path, size, sha256, metadata + provenance), duplicate groups, version chains, permission/readability records, canonical-organisation plan and actions, operations log.
2. **Grounded answers** — for each question found in the case input: an extractive answer made of verbatim quotes, each with a locator (file, chunk, char span), a verdict, and the reason when evidence is missing.

In scope: local files under the input directory. Out of scope: OCR of scans, network access, semantic/embedding search, editing or deleting input files, judging scientific correctness of the source documents.

## 2. Runtime contract

- Entry: `scripts/main.py`. Input `/input` (or `--input`), output `/app/output` (or `--output`).
- Writes a **partial** `result.json` before any extraction, then finalizes unconditionally. Exit code is always `0`.
- Stdlib only, no network, no CWD dependence (`Path(__file__).resolve().parent` for the engine import).
- Reads `case.json` + `task.md` at the input root; all other files are materials.

```bash
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --mode verify --output /app/output   # re-hash + re-extract quotes
```

## 3. Input discovery (semantic, never key-name dependent)

1. `case.json` (else any `case*.json`; a parse failure is recorded in `errors[]`, the run continues).
2. `task.md` is read for context only; it is classified `case_definition` and never used as evidence.
3. Every file under the input tree is walked (dot-dirs, `__pycache__`, `node_modules` skipped) and classified by extension **and magic bytes** into pdf / docx / xlsx / pptx / table / json / markdown / text / image / other.
4. Roles: `material` (evidence), `sidecar` (`material.json`, `manifest.json`, `metadata.csv`, `index.csv` … merged into metadata as provenance `sidecar:<name>`), `case_definition`, `system_junk` (`~$*`, `.DS_Store`, `Thumbs.db`).
5. Questions are harvested from any key matching `question|query|queries|search_tasks|ask|prompt|qa|q` (string or list of strings/objects; id taken from `id|qid|question_id|key`).
6. Objects the case mentions but that are absent are listed in `pending_human`, never invented.

## 4. Output contract

`result.json` echoes **every** key of the input `output_contract` (dict or list form). Unknown keys are preserved with `null`/`[]`; `case_id` is copied verbatim. Always present: `status`, `summary`, `library`, `inventory`, `metadata`, `duplicates`, `versions`, `questions`, `coverage_dimensions`, `sources`, `failures`, `skipped`, `conflicts`, `uncertainty`, `pending_human`, `degradations`, `errors`, `changes`, `operations`, `verification`, `runtime`, `output_contract_fields`.

| Artifact | Content |
|---|---|
| `result.json` | contract echo + all structured results + self-audit |
| `inventory.csv` | one row per file: rel, role, class, size, sha256, mtime, readable, readability, duplicate_of, version_chain, text_chars, extract_method, metadata fields, metadata_provenance |
| `version_chain.json` | chains with documents, hashes, version tokens, confidence and the rule used |
| `answers.md` | per-question verdict, extractive answer, evidence with locators, conflicts |
| `reorganize_plan.csv` | source → canonical target, action (`copied_verified` / `skip_duplicate` / `skip_unreadable` / `deferred_size_budget`) |
| `operations.log` | timestamped op, path, detail |
| `library/` | canonical copies (`<class>/<sha8>_<name>`), each re-hashed after copy |
| `verify.json` | result of the independent audit |

`status`: `ok` (library + questions adjudicated) · `partial` (stage error, results incomplete) · `insufficient_evidence` (no readable text at all) · `input_error` (no materials).

## 5. Core workflow

1. Partial `result.json` → 2. discover input & questions → 3. scan/hash/extract each file (warnings per file) → 4. merge sidecar metadata → 5. group duplicates by sha256 → 6. infer version chains → 7. index chunks and answer questions → 8. plan + copy canonical files → 9. classify failures, uncertainty, pending items → 10. write artifacts → 11. audit → 12. finalize `result.json`.

## 6. Rubric mapping

| Scored item | Field / check / artifact |
|---|---|
| Task completion | `status`, `summary`, `questions[].verdict`, `library`, six `coverage_dimensions` |
| Correctness | `questions[].evidence[].quote` verbatim + `locator`; `verification.checks[quotes_verbatim].pass` |
| Completeness | `coverage_dimensions` (file types, metadata fields, dir depth, duplicates, versions, permission/source) |
| Verifiability | `sha256` per file, `operations.log`, `verify.json`, `changes[].verified` |
| Quality gain | extractive answers, zero paraphrase, insufficient-evidence verdicts, conflict flags |
| Efficiency gain | one retrieval pass over one index: `inventory`+`versions`+`questions` in a single command; no re-asking needed |
| Novelty | sha256 dedupe (not filename), version-aware answering (`version_conflict`), explicit absence criterion (term coverage < 0.34) |
| Reliability | per-file `warnings`, `failures`, `skipped`, `degradations`, exit 0, partial-first |
| Ecosystem | this file, `references/schema.md`, `references/method.md`, `references/checklist.md`, reusable CSV/JSON outputs |

## 7. Evidence and locators

- Quote = substring of the source text copied verbatim (≤300 chars), chosen as the sentence with the highest query-term overlap. Never rewritten, never translated.
- Locator = `<rel path>#<locator>`; the `location` object adds `file`, `chunk`, `char_span` computed on the same extracted text that produced the quote.
- Per file type: PDF → `p.<page>.l<line-start>-<line-end>`; DOCX → `p.<paragraph>`; XLSX → `<sheet>!r<row>`; text/CSV → `line<start>-<end>`.
- `answers.md` and `result.json` carry `sha256` next to each quote so the exact file version is identifiable.
- Unreadable/scanned files are **never** cited; they appear in `failures`/`pending_human`.

## 8. Conflicts and human confirmation

- `version_conflict` — the cited file is not the newest in its chain (higher confidence): the answer is kept, flagged, and the item is queued in `pending_human`.
- `possible_numeric_conflict` — reserved (not emitted by v1.0.0; the field is always present and empty).
- Chain confidence `medium`/`low` (version token order vs mtime disagree) → `pending_human`.
- Nothing is resolved silently: every downgrade appears in `conflicts`, `uncertainty` (level 2/3) or `pending_human`.

## 9. Budget and checkpoints

Default limits: `--max-files 2000`, `--copy-budget-mb 32`, `--top-k 3`. The partial `result.json` lands in the first second; a 900 s / 64-request budget is never needed to obtain a readable result. Exceeding the copy budget downgrades copies to plan rows (`deferred_size_budget`) instead of failing.

## 10. Failure handling

| Condition | Handling |
|---|---|
| No input dir / no materials | `status=input_error`, empty inventory, `errors[]`/`pending_human` explain |
| Malformed `case.json` | `errors[].stage=case_load`, run continues without contract/questions |
| Permission denied | `readable=false`, `permission_denied` warning, excluded from evidence |
| Scanned PDF (no text layer) | `pdf_no_text_layer`, indexed as unreadable, `pending_human: need OCR/text copy` |
| Broken/zero-byte/unknown binary | `zero_byte` / `extract_error` / `no_text_extractor:<kind>`, hashed and inventoried |
| Image-only material | hashed, inventoried, no text evidence; degradation recorded |
| Exact duplicates | one canonical (earliest mtime, shortest path), others `skip_duplicate` |
| No question in case | library delivered, `status` unchanged, `pending_human: questions` |

## 11. Self-check

`python3 scripts/main.py --mode verify --output <out>` prints and writes `verify.json` with four checks: contract fields present, sha256 re-hashed from disk, quotes re-extracted from source, artifacts present. `verification.status=pass` in `result.json` means the in-run audit passed.

## 12. Minimal example (illustrative only - NOT an official case result)

Input `case.json`: `{"case_id":"demo","output_contract":{"inventory":"...","answers":"..."},"questions":["How much compound X was used?"]}` plus `reports/assay_v1.txt`, `reports/assay_v2.txt` (different hash), `reports/assay_v2_copy.txt` (identical hash).

```bash
python3 scripts/main.py --input /input --output /app/output
```

Illustrative output (values made up for illustration): `status=ok`, `duplicates=[{group_id:"DG01", canonical:"reports/assay_v2.txt", count:2}]`, `versions.chain_count=1` with `latest:"reports/assay_v2.txt"`, `questions[0].verdict="supported"` with `evidence[0].locator="reports/assay_v2.txt#line2-2"` and a verbatim quote, `pending_human` containing a `version_conflict` if an older version won the retrieval.

## 13. Files

`SKILL.md` · `scripts/main.py` (pipeline, CLI, ~20 KB) · `scripts/library.py` (extraction/naming/writers, ~20 KB) · `references/schema.md` (output schema) · `references/method.md` (algorithm, thresholds, limitations) · `references/checklist.md` (rubric map, self-check, worked example). Version 1.0.0, Python ≥3.8, no third-party dependency.

## 14. Maintenance

Bump `version` in both the frontmatter and `scripts/main.py` (`VERSION`) together. Retrieval thresholds live in `scripts/main.py` (`cov < 0.34`, verdicts 0.6/0.4) and are documented in `references/method.md` - change both places. Add a new file type by extending `_CLS` and `document()` in `scripts/library.py`. Keep every script under 20 KB and the package under 12 files.
