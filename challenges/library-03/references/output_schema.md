# 输出契约（library-auto-organizer v1.0.0）

所有产物写到 `--output`（评测环境为 `/app/output`）。下列字段名与 `SKILL.md`、脚本实现一致，可直接作为复核依据。

## 1. 文件清单

| 文件 | 内容 | 是否必需 |
|-|-|-|
| `result.json` | 结构化主结果：契约回填、清单、分类、标签、命名、去重、版本、操作、证据、状态 | 必需 |
| `inventory.csv` | 每个输入文件的路径/大小/sha256/mtime/权限/类型/分类/命名/落库路径 | 必需 |
| `operations.log` | 只追加的操作流水：op、seq、ts、status、src、dst、sha256、bytes、reason | 必需 |
| `version_chain.json` | 版本链与精确重复分组 | 必需（无重复时为空数组） |
| `rollback.sh` | 逐条 `rm -f <staged_path>` 的撤销脚本 | 必需 |
| `library/` | 落库后的目录树（真实副本） | 必需 |
| `verify_report.json` | `verify.py` 的确定性复核结果 | 由 `verify.py` 生成 |

## 2. result.json 顶层字段

| 字段 | 类型 | 说明 |
|-|-|-|
| `skill` | object | `{name, version, case}` |
| `case_id` | string/null | 原样来自输入 `case.json`；缺失为 null |
| `status` | enum | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `generated_at` | string | UTC ISO8601 |
| `summary` | object | 计数：files_total、materials、by_doctype、by_dir、staged、duplicates_archived、superseded_archived、errors、degradations、pending_human |
| `library` | object | `root`、`nodes`（已用目录与文件数）、`taxonomy`（来自 rules.json） |
| `inventory` | array | 每文件：file_id、path、role(`material`/`reserved`)、type、mime、size、sha256、mtime、permissions{mode,readable}、read_status、staged_path、staged_sha256 |
| `classification` | array | 每材料：file_id、rel_path、doctype、dir、confidence、signals[{signal,value,source}]；低置信另带 alt_dir_if_unsure |
| `tags` | array | 每材料：tags[]、evidence[{tag,matched_term}]、status(`ok`/`no_vocab_match`/`insufficient_text`) |
| `naming` | array | 每材料：original、proposed_name、template、degraded_fields[] |
| `duplicates` | object | exact[]（group_id、sha256、keeper、duplicates[]、reason）、chains[]、dupfiles、method |
| `versions` | object | `chains`（见 §4）与 `file=version_chain.json` |
| `operations` | object | `log`、`count`、`by_status` |
| `metadata` | array | file_id、rel_path、fields{名称: {value, source, locator, confidence}} |
| `coverage` | object | files_discovered、materials、classified、tagged、named、staged、coverage_rate、six_elements |
| `evidence` | array | 逐字证据：file_id、path、field、value、source、locator、confidence |
| `sources` | array | 输入根与各产物角色说明 |
| `uncertainty` | array | 低置信分类、作者/年份缺失、未处理项等 |
| `errors` / `degradations` / `pending_human` | array | 见 §5 |
| `changes` | array | 与 operations 对应的落库变更（seq、op、status、from_path、to_path、sha256） |
| `runtime` | object | seconds、python、budget_seconds、budget_stop、stdlib_only、network |
| `output_contract` | object | 输入契约逐字段回填的副本 |
| `contract_backfill` | object | source_key、field_count、filled_paths、mirrored_at_top_level、base_key_collisions、note |

### 契约回填规则

1. 输入 `output_contract` 的键名不改、不新增语义、未知键保留；无值的标量写 `null`，列表写 `[]`。
2. 语义识别（大小写/下划线不敏感的子串匹配）：`inventory/files/manifest/catalog` → 文件清单；
   `classification/directory/folder` → 分类；`tag/label/keyword` → 标签；`name/rename/filename` → 命名；
   `dup/dedup` → 重复；`version/chain` → 版本；`operations/log/audit` → 操作；`metadata/biblio` → 元数据；
   `evid/provenance/locator` → 证据；`uncertain/risk` → 不确定性；`pending/human` → 人工项；`error/fail/skip` → 错误；
   `status` → 状态；`tree/structure` → 目录树；`coverage/summary/count` → 覆盖率与计数；`csv` → CSV 文件名。
3. 同一份值既写在 `output_contract` 内，也在不与基础键冲突时镜像到顶层；冲突键记录在 `contract_backfill.base_key_collisions`。

## 3. inventory.csv 列

`file_id, rel_path, role, kind, size, sha256, mtime, perm_mode, readable, read_status, doctype, dir, confidence, tags, proposed_name, staged_path, staged_sha256, dup_role, version_role, fields`

`dup_role` ∈ {`keeper`,`exact_duplicate`}；`version_role` ∈ {`keep`,`superseded`}；`fields` 为该文件已抽到的元数据字段名（`|` 分隔）。

## 4. versions.chains[] 结构

```json
{"chain_id": "V001", "identity_key": "doi:10.1234/abcd", "key_type": "doi",
 "status": "resolved", "nodes": [["materials/a.pdf", "published"], ["materials/preprint.pdf", "preprint"]],
 "keep": "10_papers/2019/2019-Smith-...-jou.pdf",
 "superseded": ["11_preprints/2019/...-pre.pdf"],
 "decision": "version of record kept"}
```
`key_type` ∈ {`doi`,`arxiv_id`,`title_author_year`}；后者 `status=needs_human`（标题归一只是提示，不是同一性证明）。

## 5. 三类记录的分工

- `errors`：真实失败（加密、无权限、复制后哈希不符、case.json 不可解析、致命异常）。有 error 时 `status` 不会是 `ok`。
- `degradations`：降级但已产出（非 UTF-8 编码回退、零字节、元数据抽取失败、rules.json 不可用走内置回退、时间预算截断）。
- `pending_human`：需要人确认的动作（元数据冲突、需手工复制的文件、无契约、低置信改判建议）。

## 6. 最小调用示例（示例，非正式案例结果）

输入（自造的示例目录，非平台正式案例）：

```bash
mkdir -p /tmp/demo/input/materials /tmp/demo/output
# case.json（示例）
cat > /tmp/demo/input/case.json <<'JSON'
{"case_id":"DEMO-001","output_contract":{"case_id":null,"status":null,
 "files":{"inventory":null,"count":null},"tags":null,"duplicates":{"groups":null}}}
JSON
cp some-paper.pdf /tmp/demo/input/materials/
python3 -B scripts/organize.py --input /tmp/demo/input --output /tmp/demo/output
python3 -B scripts/verify.py  --input /tmp/demo/input --output /tmp/demo/output
```

示意输出（**示例**，取自本包自测，字段值非任何正式案例结论）：

```json
{"case_id": "DEMO-001", "status": "ok",
 "summary": {"files_total": 3, "materials": 1, "staged": 1, "duplicates_archived": 0, "errors": 0},
 "inventory": [{"file_id": "F0002", "path": "materials/some-paper.pdf", "role": "material", "type": "pdf",
                "sha256": "<64 hex>", "staged_path": "library/10_papers/2019/2019-Smith-...-jou.pdf"}],
 "classification": [{"file_id": "F0002", "doctype": "journal_article", "dir": "10_papers/2019",
                     "confidence": "high", "signals": [{"signal": "doi", "value": "10.1234/abcd", "source": "content_scan"}]}],
 "output_contract": {"case_id": "DEMO-001", "status": "ok", "files": {"inventory": ["..."], "count": 3}, "tags": ["..."], "duplicates": {"groups": []}}}
```

## 7. 状态判定

| status | 条件 |
|-|-|
| `input_error` | 输入根不存在或无任何可读文件 |
| `insufficient_evidence` | 有文件但没有任何材料被解析/分类 |
| `partial` | 有错误、有未落库材料、触及预算、或有契约缺口 |
| `ok` | 全部材料分类、命名、落库，且 errors/deferred 为空 |
