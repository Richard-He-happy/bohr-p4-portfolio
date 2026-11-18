# 最小调用示例

> **本文档中的输入与输出全部是示例（示例，非正式案例结果）**，用于说明接口与流程，不是任何正式案例的答案。

## 1. 输入

目录（示例）：

```
/input/
├── case.json
├── task.md
├── artifacts/
│   ├── protocol_v1_2021.pdf          # 2 页，含 "2.3 Buffer formulation"
│   ├── protocol_v2_final_2021.pdf    # 3 页，同章节内容已修订
│   ├── protocol_v1_2021_copy.pdf     # 与 v1 字节相同（别名副本）
│   ├── experiment_record_2022.docx
│   ├── review_slides.pptx
│   ├── scan_page.png                 # 无文字层
│   ├── corrupt.docx                  # 损坏容器
│   └── legacy_export.doc             # 旧式 OLE
├── data/
│   └── measurements_batch_B-07.xlsx
└── paper_notes.md
```

`case.json`（示例）：

```json
{
  "case_id": "demo-001",
  "questions": [
    {"id": "Q1", "text": "Which version of the protocol contains the PBS buffer formulation?", "filters": {"project": "PRJ-2021"}},
    {"id": "Q2", "text": "Which files belong to batch B-07?"},
    {"id": "Q3", "text": "2023 protocol for project ZZZ-9999", "filters": {"year": 2023}}
  ],
  "administrative_notes": {"protocol_v1_2021.pdf": "superseded by v2; keep for audit"},
  "output_contract": {"inventory": null, "version_relations": null, "search_results": null,
                      "operation_log": null, "status": null, "custom_key": null}
}
```

## 2. 调用

```bash
python3 scripts/main.py --input /input --output /app/output
# 也可以追加临时提问：
python3 scripts/main.py --input /input --output /app/output --query "batch B-07 sample storage"
# 调试单个文件抽取：
python3 scripts/engine.py /input/artifacts/protocol_v2_final_2021.pdf
```

## 3. 输出（示例，截断）

目录：`result.json`、`inventory.csv`、`version_chain.json`、`operations.log`。

`result.json` 关键片段：

```json
{
 "case_id": "demo-001",
 "status": "ok",
 "counts": {"files": 11, "directories": 2, "extracted_ok": 8, "not_searchable": 3,
            "duplicate_groups": 1, "version_chains": 1, "queries": 3, "hits": 5, "no_hit": 1,
            "failures": 0, "skipped": 0, "permission_denied": 0, "pending_human": 3},
 "duplicates": [{"dup_group": "dup-01", "count": 2, "canonical": "artifacts/protocol_v1_2021.pdf",
                 "paths": ["artifacts/protocol_v1_2021.pdf", "artifacts/protocol_v1_2021_copy.pdf"],
                 "basis": "identical sha256: copies are not independent evidence"}],
 "version_chains": [{"chain_id": "ver-01", "ordering_basis": "version_label", "n_members": 2,
                     "members": [{"path": "artifacts/protocol_v1_2021.pdf", "label": "v1", "ordinal": 0, "is_current": false},
                                 {"path": "artifacts/protocol_v2_final_2021.pdf", "label": "v2", "ordinal": 1, "is_current": true}]}],
 "queries": [
   {"qid": "Q1", "status": "ok", "filters": {"project": ["prj-2021"]}, "candidates": 4,
    "hits": [{"file": "artifacts/protocol_v2_final_2021.pdf",
              "locator": {"kind": "pdf_page", "page": 1},
              "locator_hint": "p.1 §2.3 Buffer formulation",
              "backlink": "artifacts/protocol_v2_final_2021.pdf#page=1&char=0-258",
              "quote": "Prepare 1x PBS buffer with 12 mM Tris, pH 7.6 (revised).",
              "quote_verified": true,
              "version": {"chain": "ver-01", "ordinal": 1, "is_current": true, "label": "v2"}}]}],
 "pending_human": [
   {"item": "artifacts/corrupt.docx", "status": "parse_error:BadZipFile", "action": "inspect manually"},
   {"item": "artifacts/legacy_export.doc", "status": "unsupported_legacy_office", "action": "convert to OOXML"},
   {"item": "artifacts/scan_page.png", "status": "image_no_text_layer", "action": "OCR the image"},
   {"item": "Q3", "status": "insufficient_evidence"}],
 "verification": {"checks": [{"check": "output_contract_keys", "expected": 6, "missing": [], "pass": true},
                             {"check": "quotes_re_extracted_at_locator", "total": 5, "verified": 5, "pass": true}],
                  "pass": true},
 "output_contract": {"inventory": [], "version_relations": [], "search_results": [], "operation_log": [],
                     "status": "ok", "custom_key": null}
}
```

`inventory.csv`（示例，两行）：

```
path,role,kind,ext,size,sha256,mtime,mode,readable,extract,units,project_id,year,doc_type,version_label,batch,chain_id,version_ordinal,is_current,dup_group,meta_sources
artifacts/protocol_v1_2021.pdf,material,pdf,.pdf,612,9a1f…,2026-11-18T10:42:03Z,0644,True,ok,2,PRJ-2021,2021,protocol,v1,,ver-01,0,False,dup-01,year:filename; project_id:content; version_label:filename; doc_type:filename
artifacts/scan_page.png,material,png,.png,68,3c7d…,2026-11-18T10:42:03Z,0644,True,image_no_text_layer,0,,2026,file,,,None,None,True,,year:fs_mtime; doc_type:extension
```

## 4. 如何读这份输出

1. `queries[].hits[].locator` + `quote`：这是"找到的那一段"，可逐字核对。
2. `version.is_current` 与 `duplicate_group`：判断该证据是否为当前版本、是否为副本（副本不算独立证据）。
3. `pending_human`：无法检索的材料与不可满足的过滤条件，**都是未完成项，不是结论**。
4. `verification.checks`：引文是否被原始文件重新抽取验证过；`pass=false` 时不要把命中当定论。
