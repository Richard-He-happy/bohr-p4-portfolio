---
name: library-annotation-sediment
description: Repair a research file library and turn reading annotations into traceable, searchable notes. Scans real PDF/DOCX/HTML/text materials, extracts highlight/underline/margin/handwriting annotations with page- and character-level anchors, inventories files with sha256 and provenance-tagged metadata, resolves duplicates and version chains by content hash and administrative version notes, links annotations to structured notes, builds a searchable index, answers the case search questions, and emits result.json plus inventory.csv, operations.log, version_chain.json with honest errors/degradations. Use when a task supplies a library/ or materials directory of documents and asks for annotation extraction, note sedimentation, duplicates/versions, an inventory, or library repair.
version: 0.1.0
---

# library-annotation-sediment

Repairs a research file library and converts reading annotations into traceable, searchable notes. Stdlib only, no network, deterministic.

## 1. Use & boundary

- In scope: annotation extraction (PDF highlight/underline/squiggly/strikeout/ink/text + DOCX comments), note structuring with source locators, duplicates/version-chain repair, lexical search index, honest inventory with sha256.
- Out of scope: literature search, scholarly judgement, academic writing, long-term archive governance, OCR (scanned pages are flagged, anchors unresolved).

## 2. Runtime contract

- Entry: `python3 scripts/main.py --input /input --output /app/output [--work /app/work]` (—work reserved, unused).
- First action: write a partial `result.json`; every exception is captured; final `result.json` overwrite is unconditional; exit code is always 0.
- Stdlib only; no network; paths resolved via `Path(__file__)` (never CWD); UTF-8 text files only.

## 3. Input discovery

1. Read `/input/case.json`; if absent, search `**/case*.json` recursively; still scan files if none is parseable.
2. Preserve `case_id` and `output_contract` (located by key semantics: output_contract / contract / output_schema — key names are not hard-coded). Also read `task_instruction` and any `query/question/search_query/ask` fields.
3. Recursively walk `/input/**`; identify type by extension + magic bytes (never by label). Materials not supplied are listed as gaps, not fabricated.

## 4. Output contract

`result.json` always contains: `case_id`, `status` (ok|partial|insufficient_evidence|input_error), `sources`, `artifacts`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `inventory`, `duplicates`, `version_chain`, `annotations`, `notes`, `links`, `search`, `recovery`, `summary`, `contract_fill`, plus every `output_contract` field backfilled (unknown fields get `value: null`; the raw contract is also kept under `output_contract`).

Side artifacts: `inventory.csv`, `operations.log`, `version_chain.json`, `annotations.json`, `notes.json`, `index.json`.

## 5. Pipeline

1. `scan`: per file record id/path/sha256/size/mtime/mode/readable/type; PDF text layer + encrypted/scanned flags + metadata; DOCX comments/highlights; XLSX/HTML/CSV/text minimal text.
2. `duplicates`: sha256 byte-identical groups; others flagged `duplicate_of`, nothing deleted.
3. `version_chain`: PDF family key (filename stripped of version/draft tags) + version tags/dates + mtime → ordered chain, edges `supersedes` (name alone is not proof; basis recorded).
4. `annotations`: geometry→char anchor (quad/rect overlap, nearest-line fallback); keeps type, color, color_semantics (from admin legend), author, created, comment, quote, precision, locator (page + char_start/end + rect); flags `anchor_unresolved` when no quote.
5. `notes`: dedupe identical quote+comment; classify kind (question/method/result/limitation/reusable/unspecified); each note carries evidence (file, page, quote, precision, locator, annotation_id).
6. `links`: notes sharing ≥3 terms → `shared_concept` edges with the shared terms.
7. `index` + `search`: lexical note/file term index; answer case questions; `no_recall` is a vocabulary gap, never absence.
8. `verification`: each note quote checked `in source`; miss → note flagged (kept, not silently dropped).
9. `recovery`: admin-file references resolved by basename → relink/missing.

## 6. Rubric map

- 完成度/正确性 → `annotations`, `notes`, `verification` (quote + locator back to page/char).
- 完整性 → `inventory` (type/metadata/dirs), `duplicates`, `version_chain`, `sources`.
- 可核验 → `sha256`, `locator`, `quote`, `operations.log`, `contract_fill` counts.
- 异常处理 → `errors`, `degradations`, `skipped`, `pending_human`, status honesty.

## 7. Evidence & locator rules

Every annotation/note claim carries a verbatim `quote` + `locator` (page, char_start/end, rect). `quote_in_source` is computed deterministically. A quote that is not found in the source is rejected to `pending_human`, never rewritten to pass.

## 8. Conflicts & human confirmation

Duplicates are flagged, not deleted. Version order from filename tags + mtime is marked uncertain. Missing referenced files and permission-denied files go to `pending_human` with the required action; no fabricated content.

## 9. Budget & checkpoint

Partial `result.json` is written before any heavy work. Near 780s the caller should finalize; the script already writes final output in one pass. No model calls inside the scripts.

## 10. Degradation table

| Condition | Handling |
|-|-|
| missing/invalid case.json | error + pending; scan files only; status partial/insufficient_evidence |
| unreadable file | size+hash only; skipped + pending |
| encrypted PDF | skipped, `encrypted` note |
| scanned PDF, no text layer | kept; anchors unresolved; pending OCR |
| parse error (one file) | that file degraded, others continue |
| empty library | insufficient_evidence, valid result.json, exit 0 |

## 11. Self-check

1. `python3 -B scripts/main.py --help` → exit 0.
2. Minimal case: 1 PDF + case.json (with output_contract) → result.json valid, contract fields backfilled, case_id kept.
3. Empty dir / bad JSON → valid partial result.json, exit 0, errors/degradations recorded.
4. No `__pycache__`/`.pyc`; ≤15 files; no prepared answers.

## 12. Minimal example (示例，非正式案例结果)

```bash
python3 scripts/main.py --input /input --output /app/output
# prints: status=ok files=2 annotations=1 notes=1 links=0 dup=0 chains=0
```

## 13. File list & version

- `SKILL.md` — this file.
- `scripts/main.py` — pipeline v1.0.0.
- `scripts/docext.py` — stdlib PDF/DOCX/XLSX/HTML extractors (imported by main).

## 14. Maintenance

Change detection is by sha256; reruns are deterministic given the same input. Update `docext.py` for new parsers, `main.py` for schema/contract changes; keep both ≤20KB and stdlib-only. Report parsing limits honestly instead of guessing content.
