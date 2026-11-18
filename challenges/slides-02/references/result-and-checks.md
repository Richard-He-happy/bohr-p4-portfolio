# result.json schema, locator grammar, exception codes, review checklist

## 1. Root object
```json
{
  "case_id": "as received",
  "status": "ok | partial | insufficient_evidence",
  "editable_source": {"path","format","bytes","sha256","slides","slide_size_emu","template_source"},
  "export_artifact": {"path","format","pages","bytes","method","degraded"} | null,
  "content_map": [ {"slide_index","role","title","layout","notes",
                    "bullets":[{"text","quote","locator","verified"}]} ],
  "compliance_checks": {"slide_count","page_order","template","notes","text_fit",
                        "figures","evidence","export","contract","overall_pass"},
  "exceptions": [ {"code","stage","detail"} ],
  "errors": [], "degradations": [], "pending_human": [], "uncertainty": [],
  "sources": [ {"kind","path","pages","extraction"} ],
  "changes": [ {"version","time","slides","pptx_sha256"} ],
  "runtime": {"seconds","extraction","language","mode","slides_requested","slides_delivered"},
  "audit": {"bullets","verified","rate","method"}
}
```
Every key present in the input `output_contract` is mirrored at root with the same spelling; a contract key that has no produced value is `null`/`[]` and appears in `compliance_checks.contract.unknown_keys`.

`status` semantics: `ok` = deck written, every bullet verified against the source, PDF rendered. `partial` = deck written but some check failed or a stage degraded (details in `compliance_checks` / `exceptions`). `insufficient_evidence` = no usable source text, so no deck was produced.

## 2. Locator grammar
`<source file name> p.<1-based PDF page> <section label>`, e.g. `paper.pdf p.3 results`, `paper.pdf p.1 abstract`.
Section labels come from heading detection (`abstract, intro, related, methods, results, discussion, conclusion, limits, body`). When the heading is missing the label is `body`; when the text came from DOCX/TXT the page is `1`.

## 3. Bullet verification
`quote` = the full source sentence; `text` = display form (verbatim prefix, ≤118 chars, optional trailing `…`). `verified` is true when `quote` or `text` (without the ellipsis) occurs in the normalised extracted text. This is a substring test on the real source, not a semantic similarity score. Failures become `QUOTE_UNVERIFIED` and the slide is kept as-is for human review.

## 4. Exception and degradation codes
| code | stage | meaning |
|-|-|-|
| `NO_CASE_JSON` | discover | no readable `case.json`; contract keys unknown |
| `LOW_SOURCE_TEXT` | extract | fewer than 4 usable sentences; OCR is out of scope |
| `POOL_EXHAUSTED` | plan | not enough unused sentences for a requested role; slide dropped |
| `QUOTE_UNVERIFIED` | audit | bullet not found verbatim in the source |
| `PDF_RENDER_UNAVAILABLE` | export | no working `soffice`; `export_artifact` stays null |
| `PDF_EXPORT_SKIPPED` | export | `--no-pdf` was used |
| `EDIT_WITHOUT_STARTING_DECK` | discover | workorder mode is edit/adapt but no starting deck; degraded to generate |
| `degradations[]` (no code field) | template | template unreadable → builtin design; starting deck design inherited |

`pending_human[]` lists decisions a person must confirm: missing template, slide-count shortfall, ambiguous edit scope.

## 5. Compliance checks
- `mode` — requested mode as read from the workorder (`generate`/`edit`/`adapt`), after any degradation.
- `source_preservation` — the source-preservation rule echoed from the workorder/case.
- `template_inheritance` — the template-inheritance rule echoed from the workorder/case.
- `slide_count` — requested vs actual.
- `page_order` — role sequence; must start with `title`, end with `thanks`.
- `template` — source id, `inherited`, slide width, layout count, theme fonts, footer slot/text, title/thanks presence.
- `notes` — slides carrying speaker notes.
- `text_fit` — max utilisation of the body box and the slide numbers that still overflow after auto-shrink.
- `figures` — embedded figures found/placed, captions cited, redrawn (always 0).
- `evidence` — bullets vs verified.
- `export` — method, degraded flag, page count, match with slide count.
- `contract` — required vs filled keys, unknown keys (recomputed at finalize, so a key that is filled
  later in the run is not counted as unknown).
- `overall_pass` — conjunction used to decide `status: ok`.

## 5b. v2 audit fields (patch 2.0.0)

| Field | Meaning |
|-|-|
| `page_golden` | written before the deck exists: per page role, expected sections, bullet range, required verbatim numbers, required figure/table numbers, narrative job, claim expectation. Schema in `golden-and-checks.md` §1. |
| `page_diff` | per-page verdicts (`PASS`/`PARTIAL`/`FAIL`), hard and soft gap counts, headline-number coverage, gap list. Source of `page_diff.md`. |
| `export_check` | PDF header, page count vs slide count, embedded fonts, font substitution vs the theme, text overflow measured on rendered word boxes, pictures reaching the PDF. |
| `template_check` | slide size, master, layouts, theme fonts/colours, placeholder binding, footer slot/text, notes master, media — each `pass`/`fail`/`warn`/`n/a` with evidence. |
| `version_history` | package lineage (v0.1.0 → v2.0.0) plus the run record: one row per executed step with its timestamp. |

`status` is `ok` only when the deck is written, every bullet verifies, the PDF exists, the compliance
checks pass and no page hard-fails its golden standard. Soft gaps (section/numbers/citations) keep
`status: ok` but are listed in `page_diff.gaps` and in `uncertainty`.

## 6. Reviewer checklist (independent re-check)
1. `python3 -B scripts/main.py --help` exits 0.
2. `python3 -c "import json;d=json.load(open('result.json'));print(sorted(d))"` shows the contract keys.
3. `len(content_map) == editable_source.slides`.
4. `compliance_checks.evidence.verified == compliance_checks.evidence.bullets`.
5. Open `presentation.pptx`: notes pane populated on every slide; theme colours come from the template; text stays inside the box.
6. `presentation.pdf` page count equals slide count; fonts are embedded by LibreOffice.
7. Re-read one `quote` in the PDF at the recorded page; it must match character for character.
8. `page_diff.md` covers every page and its gap index is consistent with `result.json.page_diff.gaps`.
9. `export_check.json`: `page_count.ok`, `fonts_embedded.status == pass`, `text_overflow.ok`.
10. `template_check.json`: every item `pass`, or the `warn`/`n/a` reason is visible in its evidence.

## 7. Known limits
- Scanned/OCR-only PDFs yield no text (`LOW_SOURCE_TEXT`), by design.
- Only JPEG/DCTDecode figures are reusable; vector figures are not rasterised.
- Tables and charts are not rebuilt; no native OOXML chart or data table is emitted.
- Placeholder geometry is computed inside the safe area rather than read from the layout, so a heavily customised template keeps its master/theme but not bespoke placeholder rectangles.
- One deck per run; multi-round diff is recorded through `changes` and file `sha256`, not full history.
