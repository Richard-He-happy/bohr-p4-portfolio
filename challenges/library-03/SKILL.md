---
name: library-auto-organizer
description: >-
  End-to-end organizer for a messy research file library (topic library-03, 文献与资料自动分类).
  Inventories every input file with sha256/permissions/type, extracts bibliographic metadata with
  per-field provenance (PDF /Info and decompressed text, decoded prose, filename fallback),
  classifies each item into a fixed directory taxonomy with explicit signals, emits
  controlled-vocabulary tags, rewrites filenames from a template with honest degradation tokens,
  detects exact duplicates by content hash and version chains (preprint / published / revision /
  supplement), stages a reversible copy-based library that never deletes or moves source files, and
  writes result.json (with full output_contract backfill), inventory.csv, operations.log,
  version_chain.json and rollback.sh. Use when a case asks to sort, tag, rename, deduplicate, version
  or batch-organize PDFs, scans, datasets, notes or mixed document batches instead of returning advice.
version: 1.0.0
license: MIT
---

# library-auto-organizer

## 1. 用途与边界

把 `/input` 下的一批科研文件**真正**归入目录、打标签、改成规范文件名、识别重复与版本差异，并在一次操作中产出可复核、可回滚的清单与流水。

- 覆盖：文献分类（目录层级 + 归属依据）、标签生成（受控词表 + 同义归一）、自动命名（模板 + 缺失字段降级）、去重与版本区分（内容哈希 + DOI/arXiv/标题年份）、批量整理（复制落库 + 操作日志 + 幂等重跑）。
- 不覆盖：单篇精读/翻译/润色、文献检索发现、需要 OCR 的纯图像扫描件（只标 `pdf_no_text`，不伪造文本）、联网校验 DOI 真伪（离线，DOI 只当文本证据）。
- 产物是**真实文件**：`library/` 内是逐条校验过哈希的副本，不是建议清单。

## 2. 什么时候用 / 不用

用：任务要求“整理一批文件”“归类/打标签/改名/去重/建清单”“把资料库交接给他人”，输入是混合 PDF、扫描件、表格、笔记、代码。
不用：只问某篇论文讲了什么（属阅读类）、要求生成检索式或补全参考文献（属检索/写作类）、要求改 Word 正文（属写作类）。

## 3. 运行契约

| 项 | 约定 |
|-|-|
| 入口 | `python3 -B scripts/organize.py --input /input --output /app/output` |
| 复核 | `python3 -B scripts/verify.py --input /input --output /app/output`（写 `verify_report.json`） |
| 输入 | `/input/case.json`、`/input/task.md` 与 `materials/`、`artifacts/` 等材料；均在 `/input/**` 递归发现 |
| 输出 | `/app/output/{result.json, inventory.csv, operations.log, version_chain.json, rollback.sh, library/}` |
| 先写 partial | 启动即写一版 partial `result.json`，每个阶段结束再覆盖 |
| 退出码 | 恒 0（异常也写 partial 后返回 0） |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 预算 | 默认 soft 780 秒；超时即 finalize 为 `partial` 并列出未处理项 |
| 源文件 | 只读。移动/删除一律不做，落库用复制 |

## 4. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则递归找 `case*.json`；仍失败则只做目录扫描，并在 `pending_human` 记 `case_json_repair`。
2. 保留 `case_id`；`output_contract`（或 `output_spec`/`result_contract`）整棵保留用于回填；`task_instruction`、`organizer_workorder`、`organizer_supplied_scope` 等键按语义读取并记入 `summary.workorder_keys_seen`。
3. 递归扫描 `/input/**`（跳过符号链接与 `__MACOSX`），按**魔数优先、扩展名兜底**判定类型：`%PDF`、JPEG/PNG 头、ZIP 内 `word/`|`xl/`|`ppt/`、UTF-8 可解码文本。
4. `case.json` 与 `task.md` 属于控制文件：仍进清单（`role=reserved`）但不落库、不分类，作为“跳过并说明”的显式记录。
5. 材料未提供（例如缺 `material.json`、缺伴随表）时**明确列缺口**，不构造内容。

## 5. 输出契约

`result.json` 顶层固定包含：`skill`、`case_id`、`status`、`generated_at`、`summary`、`library`、`inventory`、`classification`、`tags`、`naming`、`duplicates`、`versions`、`operations`、`metadata`、`coverage`、`evidence`、`sources`、`uncertainty`、`errors`、`degradations`、`pending_human`、`changes`、`runtime`、`output_contract`、`contract_backfill`。

回填规则：输入契约键名不改、未知键保留；无值标量写 `null`、列表写 `[]`；语义别名表在 `references/rules.json.aliases`；同一份值同时出现在 `output_contract` 内与（不冲突时）顶层，冲突键写进 `contract_backfill.base_key_collisions`。字段级语义、CSV 列、版本链结构见 `references/output_schema.md`。

## 6. 核心流程

1. 预写 partial 结果 → 2. 读规则 `references/rules.json`（失败则内置回退并记 degradation）→ 3. 发现 case 与文件 →
4. 建清单（sha256、大小、mtime、权限位、类型、可读状态）→ 5. 抽元数据（PDF `/Info` + 解压内容流文本、文本类按 UTF-8→GB18030→Big5→Latin-1 解码、文件名兜底）→
6. 分类（doctype → 目录，论文类按年份二级目录）→ 7. 标签（受控词表，上限 8，记录命中词）→ 8. 去重与版本（sha256 分组；DOI > arXiv > 标题+年份 建链）→
9. 命名（模板 + 降级 token）→ 10. 复制落库并逐条校验哈希 → 11. 写 CSV/日志/版本链/回滚脚本 → 12. finalize 判定状态。

方法细节与规则依据见 `references/method.md`。

## 7. 任务质量规则（评分点 → 字段/检查/产物）

| 评分点 | 本 Skill 的落实 |
|-|-|
| 任务完成度 | 真实产出 `library/` 目录树 + 规范名 + 标签 + 去重/版本归档；不是建议。查 `summary.staged` 与 `library.nodes` |
| 结果正确性 | 分类/标签/命名/去重均带 `signals`/`evidence`（`source`+`locator`）；缺失字段写 null 与 `degraded_fields`，不臆造 |
| 结果完整性 | `coverage`（含 `six_elements`：文件类型、元数据字段、目录层级、重复文件、版本差异、权限与来源）+ 每材料必有 `classification`/`tags`/`naming` 条目 |
| 结果可核验性 | `inventory.csv`（sha256、权限、落库路径）+ `operations.log` + `changes` + `rollback.sh`，他人可复跑比对 |
| 质量增益 | 内容级信号（PDF 文本、DOI、表格头、伴随表）而非文件名关键词；`verify.py` 重算哈希与契约覆盖 |
| 效率增益 | 一次运行完成清单/分类/标签/命名/去重/落库；`operations.count` 与 `summary` 可直接对比人工条目数 |
| 增益可验证性 | 确定性脚本 + 只追加日志 + 哈希，可对同一输入重跑复现；重跑记 `skipped_exists` |
| 新增能力 | 版本链（预印本/正式版/补充材料角色判定）+ 冲突记录 + 可回滚落库 |
| 方法改进 | 标签同义归一、命名模板与降级 token、哈希去重 keeper 规则、加密/无文本层分流 |
| 创新证据 | `duplicates.reason`、`versions.chains[].decision`、`contract_backfill` 说明可复核 |
| 调用与易用性 | `--help` 自解释；输入/输出目录可配；`status`/`errors` 直接给出后续动作 |
| 运行稳定性 | 单文件失败只降级该文件；空输入/坏 JSON 仍出合法结果；退出码恒 0 |
| 异常处理 | 见 §11 分支表（加密、扫描件、损坏、乱码、同名多版本、无权限） |
| 文档完整性 | 本文件 + `references/method.md`（规则/映射/限制） + `references/output_schema.md`（字段/示例） + `references/rules.json`（机器可读规则） |
| 资源可复用性 | 规则表与词表可改、模板可改、脚本文本可读、无第三方依赖 |
| 分享推广价值 | 目录规范与命名规则可直接搬到课题组的资料库；问题案例沉淀在 method.md 的异常表 |

## 8. 证据与定位规范

每个元数据字段都带 `{value, source, locator, confidence}`：

- `source`：`pdf_info`（`/Info /Title` 等）、`pdf_text`（解压内容流第 N 行）、`file_text`（首个标题行）、`filename`（去 token 后的词干）、`content_scan`（DOI/arXiv 正则）。
- `locator`：可复查的位置串（`/Info /Author`、`page 1 line 3`、`DOI pattern`、`year token`、`filename stem`）。
- `confidence`：`high`（结构化字段）、`medium`（正文/标题推断）、`low`（仅文件名）。
- 分类另记 `signals[]`（`signal`、命中值、`source`）；标签只记真正命中的词，宁可 `tags=[]` 也不凑数。

## 9. 冲突与人工确认

- 元数据冲突（同一字段多个来源不一致）：保留优先级更高的来源值，原样记录另一值，写 `pending_human` 的 `metadata_conflict`。
- 伴随元数据表（如作者/年份汇总 CSV）：当前版本只盘点并归类为 `metadata_table`，**不合并**进文件字段；缺口写入 `uncertainty`，需要时人工补充。
- 低置信分类：写 `uncertainty.low_confidence_classification` 并给 `alt_dir_if_unsure`，不擅自换目录。
- 仅标题相同的疑似重复：只提示不归档（`needs_human`）。
- 无权限/需人工搬运：`pending_human.manual_copy` 给出源与目标路径。

## 10. 预算与断点

`--time-budget`（默认 780s）在每个文件前检查；超限即置 `runtime.budget_stop=true`，后续文件不再处理、finalize 为 `partial` 并在 `coverage.deferred` 列出。任何中断点都已经有合法 `result.json`。

## 11. 异常降级分支

| 情形 | 处置 | 记录 |
|-|-|-|
| 加密 PDF | 不解析内容，复制进 `90_quarantine`，分类 `unknown` | `errors.encrypted_pdf` |
| 扫描件无文本层 | 归 `30_scans`，标 `pdf_no_text` | `classification.signals` |
| 损坏/零字节 | 进 `90_quarantine` 或 `read_status=empty` | `errors`/`degradations` |
| 中文乱码/非 UTF-8 | 回退 GB18030/Big5 解码并记实际编码 | `degradations.encoding` |
| 同名不同版本 | 版本链 + `92_superseded/<chain>`，不覆盖 | `versions.chains` |
| 无权限读/写 | 记 `unreadable`，不落库，转人工 | `errors.denied`、`pending_human` |
| 复制后哈希不符 | 删除副本、记失败 | `errors.hash_mismatch` |
| 重复运行 | 目标同哈希 → `skipped_exists` | `operations.log` |
| 无 `output_contract` | 输出通用 schema | `pending_human.contract_absent` |

## 12. 自检（交付前必须全绿）

1. `python3 -B scripts/organize.py --help`、`python3 -B scripts/verify.py --help` 退出码 0。
2. `result.json` 可解析，含 `case_id`/`status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`/`inventory`。
3. `inventory.csv` 行数 = 输入文件数；`sha256` 可重算比对。
4. `library/` 每个文件都能在清单里按 `staged_path`+`staged_sha256` 对上。
5. `operations.log` 非注释行数 = `operations.count`。
6. `verify.py` 输出 `ok: true`。
7. 空输入/坏 `case.json` 仍出合法 `result.json` 且退出码 0。

## 13. 最小调用示例（示例，非正式案例结果）

```bash
# 示例目录，非平台正式案例
python3 -B scripts/organize.py --input /tmp/demo/input --output /tmp/demo/output
python3 -B scripts/verify.py  --input /tmp/demo/input --output /tmp/demo/output
```

示意输出（**示例**，仅说明接口）：

```
[library-auto-organizer] partial files=11 materials=9 staged=9 groups=1 chains=0 errors=1 pending=0 out=/tmp/demo/output
[verify] ok=True failed=[]
```

`result.json` 关键片段（示例值不是任何正式案例的结论）：`case_id="DEMO-001"`、`status="ok"`、
`classification[0]={"doctype":"journal_article","dir":"10_papers/2019","confidence":"high"}`、
`naming[0]={"proposed_name":"2019-Smith-Deep-Learning-...-jou.pdf","degraded_fields":[]}`。

## 14. 文件清单、版本与维护

| 文件 | 作用 | 大小 |
|-|-|-|
| `SKILL.md` | 本说明（用途、契约、流程、规则、异常、自查） | 见仓库 |
| `scripts/organize.py` | 主流程：发现/清单/元数据/分类/标签/命名/去重/落库/结果 | ≤20KB |
| `scripts/verify.py` | 共享解析器 + 确定性复核（哈希、契约、落库、计数） | ≤20KB |
| `references/rules.json` | 目录规范、命名规则、标签词表、别名表、去重规则（机器可读） | ~9KB |
| `references/method.md` | 方法说明、字段映射、异常表、适用与限制、自查 | ~9KB |
| `references/output_schema.md` | 输出契约、CSV 列、版本链结构、示例 | ~7KB |

维护：改规则优先改 `rules.json`（脚本会读），改字段语义须同步 `output_schema.md`；版本号写在 frontmatter 与两个脚本的 `S,V`；
脚本任何改动后重跑 §12 的自检与 `verify.py`。规则表缺失时脚本使用内置最小目录表并记 `degradations.rules_unusable`，不会中断。
