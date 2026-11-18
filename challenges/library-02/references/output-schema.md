# 输出字段规范（v1.0.0）

## 1. `result.json` 顶层

| 字段 | 类型 | 含义 |
|---|---|---|
| `skill` | obj | `{name, version}`，用于确认加载的是哪一版 |
| `case_id` | str/null | 原样保留输入的案例标识；缺失时用输入目录名 |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `status_note` | str | 一句话说明状态成因（文件数、错误数或检索结论） |
| `output_contract` | obj/list | **契约回填**：键名与原契约完全一致 |
| `output_contract_spec` | any | 原契约原文，便于逐键比对 |
| `sources` | list | 读过的输入契约文件：`{path, sha256, bytes, role}` |
| `directories` | list | `{path, n_files, readable}` |
| `files` | list | 逐文件清单，字段见 §2 |
| `duplicates` | list | `{dup_group, sha256, count, canonical, paths, basis}` |
| `version_chains` | list | 字段见 §3 |
| `queries` | list | 字段见 §4 |
| `failures` | list | `{path, stage, reason}`：stat/read/scan 阶段的硬失败 |
| `skipped` | list | `{path, reason, ...}`：符号链接、超大、上限截断 |
| `permissions` | list | `{path, mode, reason}`：不可读文件 |
| `pending_human` | list | 需人工处置：`{item, status\|locator, action}` |
| `degradations` | list | `{capability, path\|status, effect}`：局部能力降级 |
| `errors` | list | `{where, error, trace?}`：流程级异常（不影响已交付部分） |
| `artifacts` | list | `{file, path, bytes, sha256, note}`：本地产物及其哈希 |
| `counts` | obj | 见 §5 |
| `index_stats` | obj | `{searchable_units, chars}` |
| `verification` | obj | `{checks, pass, note}`，见 §6 |
| `operations` | list | 与 `operations.log` 同源的轨迹（末 2000 条） |
| `runtime` | obj | `{started, finished, ms, python, input, output}` |
| `admin_overlays` | obj | `{defined, applied}`：组织方备注的应用统计 |

## 2. `files[]` 记录

`path, name, ext, size, sha256, mtime, mode, readable, kind, role, extract, extract_note?, units,
project_id, year, doc_type, version_label, batch, chain_id, version_ordinal, is_current,
dup_group, dup_of, meta_sources, meta_evidence, admin_notes`

- `role`：`input_contract`（case.json/task.md）或 `material`（参与检索）。
- `extract`：`ok` 或失败码（见 `method.md` §7）。
- `meta_sources`：每个元数据字段的出处 `{字段: filename|content|fs_mtime|extension|case_note}`。
- `meta_evidence`：对应字段命中的原文片段或时间戳，供人工核对。

## 3. `version_chains[]`

```
{chain_id, group_key, ordering_basis: "version_label"|"mtime", n_members, distinct_contents,
 timestamp_anomaly: null|"mtime_not_monotonic_with_labels",
 members: [{path, label, sha256(前16位), mtime, extract, ordinal, is_current, dup_group}]}
```

`is_current=true` 的成员是该链的当前版本；`distinct_contents>1` 表示链内确有内容差异。

## 4. `queries[]`

```
{qid, query, origin, filters, status, candidates, filtered_out, notes,
 hits: [{rank, file, sha256(前16位), locator, section, locator_hint, backlink, quote,
         score, matched_terms, matched_primary, quote_verified,
         version:{chain, ordinal, is_current, label}, meta:{project_id, year, doc_type}, dup_group}]}
```

- `status`：`ok` / `partial`（仅同义词命中）/ `insufficient_evidence`（无命中或过滤不可满足）。
- `candidates`：通过硬过滤的文件数；`filtered_out`：被硬过滤排除的文件数。
- `quote_verified`：复核阶段写入，`true` 表示引文能在该定位单元内逐字找到。

## 5. `counts`

`files, directories, extracted_ok, not_searchable, duplicate_groups, version_chains, queries,
hits, no_hit, failures, skipped, permission_denied, pending_human`

## 6. `verification.checks`

| check | 含义 |
|---|---|
| `output_contract_keys` | 契约键全部出现；`missing` 列出缺失键 |
| `quotes_re_extracted_at_locator` | 用原始文件重新抽取后核对每条引文；`verified/total` |

`verification.pass` 为全部 check 的合取；为假时顶层 `status` 降为 `partial` 并在 `status_note` 注明。

## 7. `inventory.csv`

UTF-8（带 BOM，便于表格软件打开），列序固定：

```
path, role, kind, ext, size, sha256, mtime, mode, readable, extract, units,
project_id, year, doc_type, version_label, batch,
chain_id, version_ordinal, is_current, dup_group, meta_sources
```

`meta_sources` 在该列内以 `字段:出处; 字段:出处` 形式展开。

## 8. `version_chain.json`

`{"version_chains": [...], "duplicates": [...]}`，内容与 `result.json` 中同名列表一致，便于单独交接。

## 9. `operations.log`

每行 `时间戳 \t 操作名 \t JSON 详情`，操作名包括 `scan/extract/link/write` 等；用于他人复跑时核对执行顺序与输入。

## 10. 契约回填规则

1. 契约键**一律保留原名**，不新增、不改名。
2. 值按语义映射：键名（忽略大小写与分隔符）命中下表关键词即填对应结果，否则 `null`。

| 契约键含 | 填入 |
|---|---|
| inventory / filelist / listing / catalog / 清单 / files | `files` |
| version / chain / 版本 | `version_chains` |
| duplicate / dedup / alias / 重复 | `duplicates` |
| quer / question / search / answer / 检索 / 问答 | `queries` |
| operation / log / evidence / audit / 操作 | `operations` |
| fail / error / skip / 失败 / 跳过 | `failures` |
| permission / 权限 | `permissions` |
| metadata / 字段 / 元数据 | 由 `files[].meta_sources` 汇总（无独立字段时为 `null`） |
| count / stat / metric / 计数 | `counts` |
| status / state / 状态 | `status` |
| artifact / output / 产物 | `artifacts` |
| dir / folder / tree / 目录结构 | `directories` |
| uncertainty / pending / 不确定 / 人工 | 同名列表 |
