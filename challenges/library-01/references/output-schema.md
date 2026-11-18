# 产物字段说明（output-schema）v1.0.0

所有产物写在 `--output` 目录（默认 `/app/output`）。除 `library/` 内文件外，全部为 UTF-8 文本；CSV 带 BOM 便于 Excel 打开。

## 1. result.json（顶层）

| 字段 | 类型 | 含义 |
|---|---|---|
| `skill` | object | `{name, version}` |
| `case_id` | string/null | 原样保留输入的 `case_id/caseId/id`；缺失时退为 case.json 所在目录名 |
| `status` | enum | `ok｜partial｜insufficient_evidence｜input_error` |
| `generated_at` | ISO8601 | UTC 生成时间 |
| `inventory` | array | 文件清单（见 §3），上限 5000 条，全量在 `inventory.csv` |
| `directory` | object | `{root:"library", template, tree_text, path:"directory_tree.txt", dirs:[...]}` |
| `metadata` | object | `{field_dictionary, fill_rate{field:{filled,total,rate}}, path:"metadata.csv", per_file{item_id:{filename,fields}}, provenance_rule}` |
| `versions` | object | `{chains:[...], path:"version_chain.json", basis}` |
| `duplicates` | object | `{exact_groups:[...], aliases:[...], basis:"content_sha256"}` |
| `operations` | object | `{path:"operations.log", count, records[≤1000]}` |
| `failures` | object | `{unreadable[], integrity_suspect[], failed_actions[], denied_paths[], excluded[]}` |
| `queries` | array | 每条 `{query, method, status, confidence, matches[], evidence_locator[], answer}` |
| `report` | object | `{path:"report.md", text}` |
| `metrics` | object | 计数与填充率（见 §6） |
| `sources` | array | 每个材料 `{id:"input:<rel>", kind, sha256, item_id}`；末尾追加 `case` 项 |
| `uncertainty` | array[string] | 会影响结论或使用方式的限制 |
| `pending_human` | array | `{kind,message,ref?}` 需人工确认项 |
| `errors` | array | `{kind,message,ref?}` 失败项（含 `fatal`） |
| `degradations` | array | 降级项（有界读取、无文本层、空间不足…） |
| `changes` | array | 操作摘要 `{ts,op,item_id,dst}` |
| `runtime` | object | `{python, elapsed_s, input, output}` |
| `verification` | object | `--check` 结果（见 §7） |
| `contract_echo` | object | 输入 `output_contract` 原文（未被改写） |
| `contract_unresolved` | array | 未能映射到产物的契约字段及所填类型 |
| **契约字段** | 任意 | 输入 `output_contract` 的每个键都出现在顶层，值来自语义映射或空容器 |

**契约字段映射表**（按「键名 + 描述」匹配，先到先得）

| 目标键 | 命中特征（正则，英文不区分大小写；中文直接匹配） |
|---|---|
| `failures` | `fail|skip|error|conflict|exclud|missing|失败|跳过|异常|冲突|排除|缺失` |
| `queries` | `\bquer|\bsearch|\bquestion|\bask|answer|检索|查询|问题|回答` |
| `versions` | `version|chain|supersed|谱系|版本` |
| `duplicates` | `dup|重复|alias|别名|rename|重名` |
| `operations` | `operat|log|journal|日志|操作|变更|审计` |
| `metadata` | `meta|field|属性|元数据|字段` |
| `directory` | `director|tree|folder|目录|结构|层级` |
| `inventory` | `inventor|file.?list|清单|文件|列表` |
| `report` | `report|summary|handoff|报告|摘要|交接|说明` |
| `metrics` | `count|stat|metric|rate|cover|统计|数量|率|覆盖` |
| `sources` | `source|provenance|evidence|来源|证据` |
| `uncertainty` | `uncertain|limitation|risk|gap|不确定|限制|风险|缺口` |
| `status` | `status|state|状态` |

未命中：键名含 `unknown|other|extra|misc|其它|其他` → 恒 `null`（记录进 `contract_unresolved`）；否则按描述推断容器：列表语义 → `[]`，对象语义 → `{}`，其余 → `null`。**任何情况下都不丢键、不改名。**

## 2. directory_tree.txt

```
library/
|-- <project>
  |-- <year>
    |-- <category>
      |-- <canonical_name>
```

只列真实入库文件（`reuse` 的文件也在其中；`exact_duplicate` 不在）。

## 3. inventory.csv（21 列）

`item_id, path_source, path_library, filename, size_bytes, sha256, ext, mime_guess, mtime, category, project, year, version_label, base_key, chain_id, action, dup_of, read_status, integrity_flag, metadata_fields, metadata_sources`

| 列 | 说明 |
|---|---|
| `item_id` | `IT0001` 起，按 `path_source` 排序分配 |
| `path_source` | 相对输入根的路径（复跑定位锚点） |
| `path_library` | 相对输出根的库内路径；未入库为 `null` |
| `sha256` | 源文件流式哈希；不可读为 `null` |
| `mime_guess` | 魔数判定：`pdf/zip/png/jpeg/tiff/gif/ole/gzip/7z/text/binary/empty` |
| `action` | `copied｜reuse｜keep_canonical｜exact_duplicate｜skipped_no_space｜failed_copy｜failed_hash_mismatch` |
| `dup_of` | 精确重复时指向保留项 |
| `read_status` | `ok｜ok:<encoding>｜no_text_layer｜corrupt｜permission_denied｜bounded_read｜empty｜not_attempted` |
| `integrity_flag` | `empty_file｜symlink?｜ext_magic_mismatch(...)｜name_conflict｜unreadable` |
| `metadata_fields` / `metadata_sources` | 已填字段与来源集合，便于一眼判断填充质量 |

## 4. metadata.csv（长表，字段级出处）

`item_id, field, value, source, locator, confidence`

`source ∈ {filename, content, companion_table, admin_note, derived}`；`locator` 示例：`filename#regex:year`、`content:offset=118`、`content:line=1`、`artifacts/notes.csv:row=2`、`$.admin_notes`、`filesystem:mtime`。

## 5. version_chain.json

```json
{"basis": "content sha256 + mtime + version label; never filename alone",
 "chains": [{"chain_id": "VC001", "base_key": ".csv|proj 2023 014 xrd 2019",
   "basis": ["content_sha256", "mtime", "version_label"],
   "members": [{"item_id": "IT0007", "filename": "...v1.csv", "path_source": "...",
                "sha256": "…", "size_bytes": 26, "mtime": "2019-…", "version_label": "v1",
                "order": 1, "supersedes": null, "superseded_by": "IT0008"},
               {"item_id": "IT0008", "…": "…", "order": 2, "supersedes": "IT0007",
                "diff_vs_previous": {"basis": "text_lines", "lines_before": 3, "lines_after": 4,
                                     "lines_added": 2, "lines_removed": 1}}],
   "head": "IT0008"}]}
```

`diff_vs_previous.basis` 为 `text_lines`（两侧都有文本）或 `size_only`（`bytes_delta`）。

## 6. metrics

`files_seen`（扫描到的文件 + 拒绝路径）、`materials_indexed`、`excluded_control`、`denied_paths`、`copied`、`reused`、`exact_duplicates`、`dup_groups`、`version_chains`、`unreadable`、`integrity_suspect`、`metadata_fill_rate{field:rate}`、`queries_answered`。

**守恒式**：`materials_indexed + excluded_control + denied_paths == files_seen`。

## 7. verify_report.json

```json
{"passed": true, "checked_at": "…",
 "checks": [{"check": "contract_complete", "ok": true, "detail": "declared=11 missing=[]"}],
 "counts": {"checks": 9, "failed": 0}}
```

九项检查：`result_json_parsable`、`status_enum`、`contract_complete`（用 `contract_echo` 对照顶层键）、`source_sha256_recompute`（重算源文件哈希）、`library_copies_verified`（副本存在且哈希一致）、`no_silent_skip`（计数守恒）、`duplicate_groups_sane`（组内 ≥2 且哈希不跨组）、`version_chains_sane`（成员哈希互异、`order` 连续）、`operations_log_jsonl`（每行合法 JSON；空批次允许 0 行）。

## 8. operations.log（JSONL，逐行）

| `op` | 何时 | 关键字段 |
|---|---|---|
| `copy` | 复制成功并校验 | `item_id, src, dst, sha256_before, sha256_after, result:"verified"` |
| `reuse` | 目标已存在且哈希相同 | `item_id, src, dst, sha256, result` |
| `skip_duplicate` | 精确重复不复制 | `item_id, src, sha256, dup_of, result:"not_copied"` |
| `skip_unreadable` | 权限/哈希失败 | `item_id, src, result` |
| `skip_disk_space` | 空间不足 | `item_id, src, result:"skipped"` |
| `copy_rollback` | 复制后哈希不符 | `sha256_expected, sha256_got, result:"rolled_back"` |
| `copy_failed` | 复制异常 | `result:"<error>"` |

## 9. run_manifest.json

`{run_id, generated_at, skill_version, files:{rel: {bytes, sha256}}}`。`run_id` 由版本号、`case_id`、`(path_source, sha256)` 有序集合派生，用于判定两次运行是否同输入同结果。

## 10. report.md

人读交接稿：状态与计数、目录树、判重/版本策略、失败与人工确认清单、复跑命令。内容与 `result.json` 同源，不引入新事实。
