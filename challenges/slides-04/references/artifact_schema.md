# Artifact contracts (v2)

六个新增产物与 `result.rollback` 的字段契约。所有数值都从本次运行的模板/pptx/PDF 回读，不存在占位常量。
路径均相对 `--output`。

## 1. `template_spec.json`

```jsonc
{
  "spec_version": "2.0",
  "template": {"path": "...", "bytes": 0, "sha256": "...", "package_parts": 0,
               "kind": "case_template | synthetic"},        // synthetic = 无模板时的内置骨架包
  "slide_size": {"cx_emu": 12192000, "cy_emu": 6858000, "width_in": 13.333, "height_in": 7.5,
                 "ratio": "16:9", "ratio_value": 1.7778, "orientation": "landscape",
                 "evidence": "<p:sldSz cx=\"...\" cy=\"...\"/>"},
  "counts": {"masters": 1, "layouts": 6, "themes": 1, "slides_in_template": 1, "media_parts": 0},
  "masters": [{"part": "ppt/slideMasters/slideMaster1.xml", "sha256": "...",
               "placeholders": [{"type": "title", "idx": "0", "name": "...", "rect_emu": [/*4*/], "rect_in": [/*4*/]}],
               "clr_map": {"bg1": "lt1", "tx1": "dk1", "...": "..."},
               "tx_styles": {"title": {"sz_pt": 30.0, "lnspc_pct": 90.0, "bullet": false, "marL_emu": 0},
                             "body":  {"sz_pt": 20.0, "lnspc_pct": 100.0, "bullet": true, "marL_emu": 228600},
                             "other": {"sz_pt": 18.0}},
               "title_sz_pt": 30.0, "body_sz_pt": 20.0, "body_lnspc_pct": 100.0,
               "layout_count_declared": 6}],
  "layouts": [{"index": 2, "part": "ppt/slideLayouts/slideLayout2.xml", "sha256": "...",
               "name": "Title and Content", "type": "obj",
               "placeholders": [{"type": "title", "idx": "0", "rect_emu": [/*4*/]}],
               "placeholder_types": ["body", "ftr", "sldNum", "title"],
               "clr_map_ovr": "masterClrMapping", "show_master_shapes": true}],
  "theme": {"part": "ppt/theme/theme1.xml", "sha256": "...", "name": "AcademicBlue",
            "color_scheme": {"dk1": {"kind": "sys", "value": "windowText", "last": "000000"},
                             "accent1": {"kind": "srgb", "value": "1F4E79"}},
            "colors": {"dk1": "windowText", "accent1": "1F4E79", "...": "..."},
            "fonts": {"major_latin": "Georgia", "major_ea": "Microsoft YaHei", "major_cs": "",
                      "minor_latin": "Calibri", "minor_ea": "Microsoft YaHei", "minor_cs": ""}},
  "theme_fonts": {/* = theme.fonts */},
  "palette": {/* = theme.colors */},
  "notes_slide_size": {"cx_emu": 6858000, "cy_emu": 9144000},
  "protected_parts": {"ppt/slideMasters/slideMaster1.xml": "<sha256>", "ppt/slideLayouts/...": "...",
                      "ppt/theme/theme1.xml": "..."},     // guard() 的保护对象
  "layout_map": [{"page": 3, "role": "content",
                  "layout_part": "ppt/slideLayouts/slideLayout2.xml", "layout_index": 2,
                  "layout_name": "Title and Content", "layout_type": "obj",
                  "placeholders_filled": ["title", "body", "ftr", "sldNum"],
                  "placeholders_available": ["body", "ftr", "sldNum", "title"],
                  "placeholders_used_of_available": ["title", "body", "ftr", "sldNum"],
                  "invented_placeholders": [], "freetext_boxes": 0}],
  "layout_map_status": "pending_build | resolved",   // 先写 pending，打包后回填
  "layout_map_summary": {"pages": 10, "distinct_layouts": 3, "invented_placeholders": 0},
  "workorder": {"slides": 10, "footer": "...", "min_pt": 12, "page_numbers": true, "mode": "..."},
  "parse_notes": ["no slideLayout part in template"]
}
```

## 2. `format_compliance.json`

```jsonc
{
  "items": [{"id": "CI-09", "item": "正文字号阶梯",
             "requirement": "最小正文字号 ≥ 12.0 pt；上限 = 母版 bodyStyle 20.0 pt",
             "actual": "实际字号集合 [18.0, 20.0] pt；最小 18.0 pt",
             "status": "pass | fail",
             "evidence": [{"part": "ppt/slides/slide3.xml", "locator": "<a:rPr@sz>",
                           "snippet": "<a:rPr lang=\"en-US\" sz=\"1800\"/>",
                           "verified_in_part": true}],   // snippet 必须是该部件中真实子串
             "note": ""}],
  "total": 16, "passed": 16, "failed": 0, "fail_ids": [], "pass_rate": 1.0, "pass": true,
  "template": "template_academic.pptx", "template_kind": "case_template | synthetic",
  "generated": "2026-11-13T01:20:51Z"
}
```

检查项：CI-01 页数 / CI-02 页面尺寸比例 / CI-03 母版未改写 / CI-04 版式未改写 / CI-05 主题未改写 /
CI-06 每页版式绑定 / CI-07 占位符继承 / CI-08 标题层级 / CI-09 正文字号 / CI-10 行距 / CI-11 主题字体 /
CI-12 色板 / CI-13 页脚 / CI-14 页码 / CI-15 溢出 / CI-16 讲稿。

## 3. `export_check.json`

```jsonc
{
  "pdf": {"path": "...", "header": "%PDF-1.7", "pages": 10, "bytes": 0,
          "size_in": [13.333, 7.5], "mediabox_pt": [960.0, 540.0],
          "embedded_font_programs": 5, "images": 1, "encrypted": false},
  "pptx": {"slides": 10, "size_in": [13.333, 7.5], "ratio": "16:9"},
  "consistency": {"pages_match": true, "pdf_pages": 10, "pptx_slides": 10, "size_match": true, "note": null},
  "fonts": {"theme_fonts": {"major_latin": "Georgia"}, "font_table_source": "pdffonts",
            "font_table": [{"name": "BAAAAA+Georgia-Bold", "type": "TrueType", "embedded": true}],
            "verdicts": [{"theme_font": "Calibri", "script": "latin", "status": "embedded | metric_substitute | substituted | unembedded | not_exercised",
                          "fc_match": "Carlito"}],
            "cjk_text_present": false, "all_theme_fonts_resolved": true},
  "render_text": {"tool": "pdftotext -bbox",
                  "pages": [{"page": 1, "page_pt": [960.0, 540.0], "words": 74,
                             "ink_bbox_pt": [97.1, 137.7, 705.3, 290.4], "outside": 0, "min_margin_pt": 97.1}],
                  "outside_words": 0, "pages_outside": [], "pages_tight_margin": []},
  "overflow": {"slides": [], "count": 0, "max_fit_ratio": 0.79,
               "model": "per-character advance (CJK 1.0em / Latin 0.52em) x 1.20 line height, 4% safety",
               "detail": []},
  "rules": {"pdf_pages_eq_slides": true, "pdf_size_eq_deck": true, "no_estimated_overflow": true,
            "text_inside_page": true, "fonts_embedded": true},
  "pass": true, "status": "pass | partial | no_pdf", "degradations": []
}
```

## 4. `page_diff.md`

四节：`§1` 模板级 diff（尺寸/版式库/受保护部件/页数/占位符/页脚/导出）、`§2` 逐页格式 diff
（页、角色、标题、版式、占位符 用/可用、最大字号、页脚、页码、填充率、偏差）、`§3` 逐页内容 diff
（主张、原稿定位、逐字证据、hit/miss）、`§4` 未解决偏差与人工动作。

## 5. `version_history.md`

`§1` 版本链（v0 骨架 → v1 成稿 → v2 本包）、`§2` v1→v2 逐条变更（问题/改法/验证）、
`§3` 本次运行产物字节数与 sha256、`§4` 回退路径（自动 guard + 手动步骤 + 边界）。

## 6. `run.log`

```
<ISO8601 UTC>  +000.021s  INFO   main.start         argv=[...]
<ISO8601 UTC>  +019.469s  ERROR  run                <traceback tail>
```
追加写入、每行立即落盘；`result.run_log` 给出 `path/lines/stages`。

## 7. `result.rollback`

```jsonc
{"strategy": "restore-protected-parts-from-template",
 "source_of_truth": "template_academic.pptx",
 "protected_parts": {"ppt/theme/theme1.xml": "<sha256>"},
 "checked": 8, "drift": [], "repaired": [], "verified": true,
 "method": "sha256 per part, byte restore + repack",
 "manual_path": ["compare sha256 ...", "unzip -p <template> <part> ...", "rerun main.py --template <template>"],
 "level": "template parts auto-restored; page level = idempotent rerun"}
```
