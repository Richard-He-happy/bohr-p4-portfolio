# Method — extraction, deduplication, versions, retrieval

Every rule below is implemented in `scripts/library.py` (extraction/naming) and `scripts/main.py` (structure, retrieval, audit).
Thresholds are given explicitly so a reviewer can recompute any verdict by hand.

## 1. Ingestion

| Step | Rule |
|---|---|
| Walk | `os.walk`, symlinks not followed; skipped dirs: `.*`, `__pycache__`, `node_modules`, `.git` |
| Identity | `sha256` streamed in 1 MiB blocks over the whole file (no size/time shortcut) |
| Type | extension **and** magic bytes (`%PDF`, `PK\x03\x04`, `\x89PNG`, `\xff\xd8\xff`, `RIFF`, `GIF8`, `BM`); mismatch is recorded, not resolved silently |
| Permission | `os.access(R_OK)` plus a real `open()`; running as root can mask mode bits, so a successful read is treated as readable (honest: the file *was* readable in this run) |

Extractors (stdlib only):

- **PDF** — objects parsed with `/Type /Page` in object order; each page's `/Contents` streams inflated with zlib when compressed; text show-operators `(...)Tj`, `[...]TJ`, `<hex>Tj` decoded; `/Title /Author /Producer /CreationDate` read from the info area. No text layer → `pdf_no_text_layer` (no OCR).
- **DOCX** — `word/document.xml`, one paragraph per `<w:p>`, `docProps/core.xml` for title/creator/created/modified.
- **XLSX** — `xl/sharedStrings.xml` + `xl/worksheets/sheet*.xml`, one paragraph per row as `col=value | col=value`, locator `<sheet>!r<row>`.
- **TXT/MD/CSV/JSON/…** — decoded `utf-8-sig → utf-8 → gb18030 → cp1252 → latin-1`, split into blank-line-separated blocks.
- **Images / unknown binaries** — hashed and inventoried only; `no_text_extractor` recorded.

Per-file warnings are strings, never exceptions: `permission_denied`, `zero_byte`, `empty_text`, `pdf_no_text_layer`, `pdf_text_too_short`, `pdf_page_objects_not_resolved`, `docx_no_paragraph_text`, `xlsx_no_cell_text`, `no_text_extractor:<kind>`, `extract_error`, `system_junk_skipped`.

## 2. Metadata with provenance

Fields and their source label: `ext`, `version_token`, `year`, `title` (when no document title) → `filename`;
`size_bytes`, `mtime` → `stat`; `title`, `author`, `created`, `modified` from document properties → `content:doc_props`;
`text_chars` → `content:<extractor>`; anything supplied by `material.json` / `metadata.csv` / `manifest.json` → `sidecar:<name>`.
Sidecar values never overwrite a measured value: they are applied with `setdefault`.

## 3. Duplicates — by content, never by name

Group by `sha256`. A group of ≥2 members gets `DG<n>`; the canonical member is the earliest `mtime`, tie-broken by the shortest
relative path; all others carry `duplicate_of = <canonical>` and are not copied or indexed twice.

## 4. Version chains — hash + time first, name only as a hint

Candidates: non-duplicate materials sharing a normalised stem (`norm_stem`: strip extension, copy/final/draft/修订/定稿 markers,
`(1)` counters, `v1.2` tokens, trailing year). A chain needs ≥2 members with **distinct** sha256.

Ordering: version token rank (numeric `v1.2` > `final` > `revised` > `draft` > `copy`) then `mtime`.
Confidence:

- `high` — the name ranking and the mtime ordering agree **and** every consecutive pair has text similarity ≥ 0.5
  (`difflib.SequenceMatcher.quick_ratio()` on the first 4000 chars);
- `medium` — orders agree but similarity is low or unavailable (typical for binary-only members);
- `low` — name ranking and mtime disagree.

`medium`/`low` chains emit a `pending_human` item; the chain itself is still reported with `evidence {distinct_sha256, pairwise_text_similarity, name_rank_matches_time_order}` so the inference is reproducible.

## 5. Retrieval and answering

- Chunking: paragraphs concatenated to ≤900 characters; chunk locator = first..last source locator.
- Tokens: lowercase Latin words/digits (≥2 chars) + CJK bigrams (single CJK runs of length 1 kept).
- Score per chunk: `coverage = |Q∩C|/|Q|`, `idf-weighted score = Σ idf(t) / |Q|`, `idf(t) = ln((N+1)/(df+1)) + 1` over N chunks. One pass, no re-query.
- Evidence: up to `--top-k` (default 3) chunks with `coverage ≥ 0.34`, at most one chunk per file, quote = the sentence of that chunk with the highest token overlap (≤300 chars, verbatim).
- Verdicts: `support ≥ 0.60`, `partial 0.40–0.60`, `insufficient < 0.40`. A candidate whose quote is not an exact substring of the chunk is dropped — nothing is paraphrased or repaired.
- Answer text is the quote(s) with `[n]` markers, never free prose (`answer_mode: "extractive"`).
- `missing_concepts` = question tokens with corpus document frequency 0, i.e. the library genuinely lacks the term.

Absence is asserted over the indexed corpus only: a scanned image or unreadable PDF can hide evidence, which is why those files are listed in `pending_human` alongside any `insufficient_evidence` verdict.

## 6. Version-aware answers

If the winning evidence file belongs to a chain whose `latest` is another file, a `version_conflict` is attached with both paths and
a `pending_human` entry. The answer is not silently swapped to the newest file, because the newest file may not contain the passage;
the conflict is reported instead.

## 7. Organisation

Target `library/<class>/<sha8>_<name>` (hash prefix makes collisions impossible and keeps provenance visible). Copy with `shutil.copy2`,
then re-hash the copy: `copied_verified` only when the hash matches, otherwise `copy_hash_mismatch`. Duplicates, unreadable and
zero-byte files are `skip_*` rows. Above `--copy-budget-mb` files become `deferred_size_budget`. The plan CSV always lists every
material, so the intended tree is inspectable even when copies are deferred.

## 8. Audit

`audit()` re-reads every inventoried file, recomputes its sha256, re-extracts every cited file and re-checks each quote as a substring.
Checks: `contract_fields`, `sha256_from_disk`, `quotes_verbatim`, `artifacts`. `--mode verify` repeats the audit from disk alone.

## 9. Known limits

1. Lexical retrieval only — paraphrase-heavy questions can return `insufficient_evidence`; the verdict says so rather than guessing.
2. No OCR — scanned PDFs/images are inventoried but never cited.
3. PDF page mapping assumes page objects appear in document order; if page objects cannot be resolved the file is flagged and its text is not indexed.
4. Root execution can mask Unix permission bits; `permission_denied` therefore reflects a real failed read, not the mode string.
5. Very large libraries are capped by `--max-files`; the remainder is listed in `skipped` with `max_files_reached`.
