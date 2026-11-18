# result.json schema, quoting rules and thresholds

## 1. Top level

Every key listed in the input `output_contract` is present with the same key name; unknown keys are preserved (value `null` when unused). On top of that the envelope always contains:

| field | type | meaning |
|---|---|---|
| `case_id` | str/null | copied verbatim from the case |
| `status` | `ok`/`partial`/`insufficient_evidence`/`input_error` | `ok` only when every compliance check passes and no exception was raised |
| `sources` | obj | `{file, engine, chars, pages, figures, tables, template}` |
| `runtime` | obj | `{started, seconds, model_requests}` |
| `exceptions` | list | `{kind, detail}` — missing material, unreadable PDF, figure list unconfirmed |
| `degradations` | list | `{what, detail}` — template missing, python-only parsing, PDF renderer missing |
| `pending_human` | list | `{action, detail}` — what a human must confirm before external use |
| `uncertainty` | list | `{about, detail}` |
| `changes` | obj | `{artifact, engine, slides, action: add/modify}` |
| `errors` | list | runtime exceptions (the process still exits 0) |

## 2. `editable_source`

```json
{"path": "/app/output/presentation.pptx", "format": "pptx", "slides": 12, "bytes": 30787,
 "sha256": "<64 hex>", "engine": "stdlib-ooxml-template-surgery", "notes_slides": 12,
 "template": {"path": "/input/artifacts/target-template.pptx", "master": ["slideMaster1.xml"],
              "layouts_used": ["slideLayout1.xml","slideLayout2.xml"], "inherited": true}}
```

`template.inherited` is `true` only when the theme and master SHA-256 hashes are unchanged after the build; the check is reported as `compliance_checks.template_inheritance`.

## 3. `export_artifact`

```json
{"pdf": {"path": "/app/output/presentation.pdf", "pages": 12, "engine": "libreoffice", "valid": true},
 "png": {"dir": null, "count": 0}}
```

`valid` requires the `%PDF-` header plus a parsed page count equal to the slide count. PNG previews are not produced by this version; the PDF is the render evidence.

## 4. `content_map`

```json
{"unit": "slide",
 "slides": [{"n": 7, "title": "Figure 1: Accuracy versus training set size",
             "role": "evidence", "claim": "Accuracy of the proposed network versus training set size…",
             "bullets": ["Accuracy of the proposed network versus training set size…", "…"],
             "evidence": [{"type": "figure", "id": "Figure 1", "locator": "Figure 1, p.3",
                           "quote": "Figure 1. Accuracy of the proposed network versus training set size.",
                           "matched": true}],
             "assets": [{"path": null, "note": "figure cited by caption+locator"}],
             "notes": "If asked, cite Figure 1, p.3. Next: What it means."}],
 "coverage": {"slides": 12, "with_evidence": 12, "evidence_items": 27, "quotes_matched": 27}}
```

Rules:

- `role ∈ title|motivation|approach|method|evidence|discussion|limitation|conclusion|thanks`.
- `claim` = the page's single assertion, taken verbatim from the anchoring sentence (a cut is allowed, a rewrite is not).
- `evidence[].quote` must be a **verbatim** passage of the paper; checking is case-insensitive, whitespace-normalised, then de-punctuated. A quote shorter than 8 characters is rejected.
- `evidence[].locator` = `p.<page>` optionally followed by ` / <section>`, or `Figure N, p.X` / `Table N, p.X`.
- `evidence[].matched=false` means the quote was not found; such a page also appears in `compliance_checks.failures`.
- `assets[].path` is `null` because this version does not copy bitmap figures out of the PDF — the caption and its locator carry the reference instead. That is stated rather than papered over with a stand-in image.

## 5. `compliance_checks`

| key | content |
|---|---|
| `slide_count` | `{expected, actual, ok}` |
| `template_inheritance` | `{declared, engine, theme_unchanged, master_unchanged, layouts_used, ok}` |
| `overflow` | `{dense_slides: [], ok}` — pages over 5 bullets or 190 chars |
| `notes_coverage` | `{n, total, ok}` — every page must carry notes |
| `notes_overlap` | `{max, threshold: 0.6, ok}` — share of note tokens also on the page |
| `figure_refs` | `{paper_count, mismatch, ok}` — figure/table ids cited vs ids in the paper |
| `number_whitelist` | `{misses, ok}` — numbers on slides that are absent from the paper |
| `evidence_coverage` | `{n, total, quotes_missing}` |
| `mode` | `{declared}` — mode read from the workorder |
| `fonts` | `{theme: template|builtin, embedded: false}` |
| `files` | `{pptx_ok, pdf_ok, png, pptx_slides, pdf_pages, pptx_notes}` |
| `pass` | `true` only when `failures` is empty |
| `failures` | human-readable list, capped at 30 entries |

## 6. Thresholds (change here first, then in code)

| rule | value | where |
|---|---|---|
| minimum extracted text to build a deck | 200 chars | `main.py` |
| minimum quote length | 8 chars | `hit()` |
| bullets per page / chars per bullet | 5 / 190 | `checks()` |
| notes overlap ceiling | 0.6 | `checks()` |
| figure page density | caption clause ≤ 95 chars | `model()` |
| maximum slides | from the workorder, default 12 | `worder()` |

## 7. Status decision

```
input_error   no paper file, or case.json unreadable and no material to work from
partial       deck built but a check failed, an exception was raised, or the text layer was empty
insufficient_evidence  material present but no usable sentences/captions (nothing to put on a page)
ok            deck built, all compliance checks pass, exceptions list empty
```
