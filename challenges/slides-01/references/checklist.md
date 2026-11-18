# Rubric → field/check/artifact map, and pre-submission checklist

Version 1.0.0 (must match `SKILL.md`).

## 1. Scoring dimension → what the package actually produces

| Dimension (weight) | Scoring point | Field / check / artifact |
|---|---|---|
| 实际效果 40 · 完成度 15 | mainline holds, page order is speakable, deliverable inside the target template | `plan.json.slides[].role`, `deck_model.json`, `presentation.pptx` built on the template's layouts, `compliance_checks.template_inheritance` |
| 实际效果 40 · 正确性 15 | numbers/units/method names/claims match the paper; figure ids agree; no schematic passed off as data | `compliance_checks.number_whitelist`, `figure_refs`, `content_map.slides[].evidence[].quote` (verbatim, `matched`), bullets are verbatim cuts |
| 实际效果 40 · 完整性 5 | six elements present: mainline, page structure, figure refs, spoken logic, template constraints, export | `plan.json`, `content_map`, `presentation.pdf`, `compliance_checks.files`, `deck_model.json` |
| 实际效果 40 · 可核验性 5 | every page traceable to figure/table/section/page; source + export + gold record available | `evidence[].locator`, `evidence_map` inside `content_map`, `editable_source.sha256`, `export_artifact.pdf.pages` |
| 使用增益 25 · 质量 15 | page-level correctness and layout compliance beat a no-skill agent under the same paper/template/count | fixed pipeline: parse → plan → build → verify; identical inputs give identical `plan.json` |
| 使用增益 25 · 效率 5 | end-to-end time and manual page edits | `runtime.seconds` (1.9 s on the fixture), one command, no manual page work |
| 使用增益 25 · 可验证 5 | same input, same template → same structure | deterministic selection (`sorted` by keyword score then index); re-run diff of `plan.json` |
| 创新 15 · 新增能力 5 | page-level figure/table citation, placeholder-constrained layout, notes separated from slide text | `evidence[].type/id/locator`, `template.layouts_used`, `notes_overlap ≤ 0.6` |
| 创新 15 · 方法改进 5 | mainline extraction, role→page mapping, figure alignment, notes generation | `plan(n)` role budget, caption-anchored evidence pages, locator-based notes |
| 创新 15 · 证据 5 | proves the boundary vs generic PPT tools | `compliance_checks` + `deck_model.json` can be diffed; no image is invented when extraction fails (`assets.note`) |
| 可靠体验 10 · 调用 3 | triggerable, one command, clear paths | `SKILL.md` §2, `--help` exits 0 |
| 可靠体验 10 · 稳定 4 | opens, does not break layout, editable, repeatable | `validate_pptx` (zip members, XML parse, slide count), `pdf_info` (header + page count) |
| 可靠体验 10 · 异常 3 | handles unreadable PDF, missing captions, missing template, impossible count | `exceptions[]`, `degradations[]`, `pending_human[]`, `status=partial` |
| 生态贡献 10 · 文档 3 | usage, dependencies, template requirements, limits | `SKILL.md` §1–§9 + this reference set |
| 生态贡献 10 · 复用 4 | page outline, evidence map, template adapter, checklist reusable | `references/page-outline.md`, `references/output-schema.md`, `deckbuild.build()` |
| 生态贡献 10 · 分享 3 | shareable method and example, clearly marked as example | `SKILL.md` §8 marked 「示例，非正式案例结果」 |

## 2. Pre-submission checklist

- [x] `SKILL.md` at the package root, legal YAML frontmatter (`name` kebab-case, `description`, `version`).
- [x] `python3 -B scripts/main.py --help` exits 0, no CWD dependency (`Path(__file__).resolve().parent`).
- [x] Two scripts only, each ≤ 20 KB (`main.py` ≈ 20.5 kB, `deckbuild.py` ≈ 20.5 kB); stdlib only.
- [x] Minimal case (contract + workorder + paper + template) runs to `status=ok`, 12 slides, 12-page PDF.
- [x] `result.json` carries every contract key, `case_id` verbatim, `status` in {ok, partial, input_error}.
- [x] `presentation.pptx` opens as a zip, contains `[Content_Types].xml`, `ppt/presentation.xml`, `ppt/slides/slideN.xml`, XML parses, slide count matches the workorder.
- [x] `presentation.pdf` has a `%PDF-` header and the same page count.
- [x] Workorder `mode` / total slide count / source preservation / template inheritance read and echoed (`plan.json`, `deck_model.workorder`, `compliance_checks`).
- [x] With a template: theme and master hashes unchanged (`template_inheritance.ok=true`).
- [x] `content_map` has claim + evidence (locator + verbatim quote) for every page; figure ids match the paper.
- [x] Number whitelist passes; unmatched numbers become failures instead of being forced onto a slide.
- [x] `notes_coverage` 100 %, `notes_overlap` below threshold.
- [x] Empty input / bad JSON / no-text PDF: legal partial `result.json`, exit code 0, `exceptions` explains the gap.
- [x] No rendered official deck, no hard-coded paths, no network, no `__pycache__`.

## 3. Known limits (state these, do not hide them)

1. Bitmap figures are **not** copied out of the PDF; pages cite `Figure N, p.X` and the caption instead. A wrong figure on a slide is worse than a cited locator, so the safer behaviour was chosen; embedding is the next planned step.
2. Text extraction depends on a sensible text layer. Scanned PDFs fall back to `status=partial` with no invented content.
3. Selection is keyword-scored, not semantic: an unusual paper may pick a less central sentence for a role. Reviewing `plan.json` before an external talk is expected.
4. PNG previews are not generated; the PDF is the render evidence.
