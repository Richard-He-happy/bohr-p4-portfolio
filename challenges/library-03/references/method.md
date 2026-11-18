# 方法说明（library-auto-organizer v1.0.0）

本文说明规则依据、字段映射、命名与去重逻辑、失败处置与自查方法。机器可读规则在 `references/rules.json`，
输出字段语义在 `references/output_schema.md`，调用与边界见 `SKILL.md`。

## 1. 处理流程与产物对应

| 阶段 | 做什么 | 落盘证据 |
|-|-|-|
| 0 预写 | 先写一版 partial `result.json`（含 case_id、output_contract 骨架） | `result.json` |
| 1 发现 | 读 `case.json`（缺失时递归找 `case*.json`）、保留 `case_id` 与 `output_contract` 原样透传 | `result.json.sources`、`contract_backfill` |
| 2 盘点 | 逐文件记录相对路径、大小、mtime、权限位、sha256、类型（魔数优先，扩展名兜底）、可读状态 | `inventory.csv`、`inventory[]` |
| 3 抽元数据 | PDF `/Info` 与解压后的内容流、文本类解码（含 GB18030 回退）、文件名降级；每字段记 `source`+`locator`+`confidence`；不合并伴随表（见 §9 限制） | `metadata[]`、`evidence[]` |
| 4 分类 | doctype → 目录（论文/预印本按年份二级目录），记录命中信号与置信度；伴随元数据表（BibTeX/含 file 列的表格）归 `metadata_table` | `classification[]`、`library.nodes` |
| 5 标签 | 受控词表匹配标题/正文/文件名，同义归一到 canonical tag，上限 8 个 | `tags[]` |
| 6 去重与版本 | sha256 分组去重；DOI > arXiv id > 标题+年份 判定同源作品并排版本 | `duplicates()`、`versions`、`version_chain.json` |
| 7 命名 | 模板 `{year}-{author}-{title}-{doctype}`，缺失字段降级 | `naming[]`、`inventory.csv.proposed_name` |
| 8 落库 | 复制到 `library/`（不移动、不删除），逐条校验复制前后 sha256 | `operations.log`、`rollback.sh`、`changes[]` |
| 9 finalize | 无条件重写 result.json，按失败面判定 ok / partial / insufficient_evidence / input_error | `result.json.status` |

## 2. 目录规范（六类要素之一）

一级目录固定，二级仅论文类按年：`10_papers/<year>`、`11_preprints/<year>`、`12_conference/<year>`、
`13_thesis/<year>`、`14_supplementary`、`15_books_chapters`、`20_datasets`、`20_datasets/metadata_tables`、
`30_scans`、`40_notes`、`50_code`、`00_inbox`、`90_quarantine`、`91_duplicates/<sha8>`、`92_superseded/<chain_id>`。
年份不可判定时用 `undated`，不猜年份。空目录不创建（`library.nodes` 里可见已用目录与文件数）。

## 3. 元数据字段与出处

| 字段 | 取值来源（`source`） | `locator` 示例 | 缺值行为 |
|-|-|-|-|
| title | `pdf_info` / `pdf_text` / `file_text` / `filename` | `/Info /Title`；`page 1 line 3` | 记 `untitled` 并列入 uncertainty |
| authors | `pdf_info` / `filename` | `/Info /Author` | 记 `null`，命名用 `anon` |
| year | `pdf_text` / `file_text` / `filename` | `year token` | 目录 `undated`、命名 `nd` |
| doi | `content_scan` / `filename` | `DOI pattern` | `null` |
| arxiv_id | `content_scan` / `filename` | `arXiv id` | `null` |
| doc_type | `metadata_table` | 伴随表内 `type`/`itemtype` | 无伴随表时 `null` |

`/Info` 标题命中 `microsoft word|untitled|document\d|.doc/.pdf` 等样板串时降级为 `filename`，避免把编辑器标题当论文题名。
置信度：`high`（结构化元数据字段）、`medium`（正文/标题推断）、`low`（仅文件名推断）。

## 4. 分类信号与冲突

信号顺序（先命中先定，命中即记录）：元数据表 `doc_type` → 预印本服务/arXiv id → 学位论文 → 补充材料 →
会议 → DOI（含正文或期刊元数据）→ 图片/无文本层 PDF → 代码 → BibTeX/元数据表 → 数据扩展名 → 散文类扩展名。
PDF 加密或无文本层时不做内容推断：加密件直接进 `90_quarantine`，无文本层归 `30_scans` 并记录 `pdf_no_text` 信号。
置信度 `high` 需 ≥2 条内容级信号（内容扫描、魔数、内容流、文件名+内容），单条为 `medium`，仅扩展名为 `low`；
`low` 件同时写 `alt_dir_if_unsure` 与 uncertainty，便于人工改判。

## 5. 命名规则

- 模板：`{year}-{author}-{title}-{doctype}`；`doctype` 取 doctype 前 3 字符（`jou`/`pre`/`the`/`dat`/`sca`/`not`…）。
- 允许 token：`{year}{author}{title}{doctype}`，模板与词表在 `rules.json.naming`，可用 `--template` 覆盖（若模板含未知 token，按顺序拼接降级并记 degradation）。
- 清洗：NFKC 归一；`\ / : * ? " < > | # % { } ^ ~ [ ] \` $ @ ! + =` 与控制字符替换为 `-`；空白与连字符合并；去掉首尾 `-._ `；
  title token 上限 70 字符、整名上限 150 字符；Windows 保留名加 `x-` 前缀；CJK 原样保留，不音译、不造罗马字。
- 缺字段：`nd` / `anon` / `untitled`，并写 `degraded_fields`，绝不臆造作者或年份。
- 目标名冲突：追加 `-<sha256 前 8 位>`；扩展名统一小写保留原扩展名。

## 6. 去重与版本判定

- 精确重复：内容 sha256 相同即同一文件；keeper 取“来源路径层级最浅 → mtime 最早 → 路径字典序”，其余复制进 `91_duplicates/<sha8>/`。
- 近重复：仅标题+年份一致且无 DOI 时标记 `possible_duplicate_by_title`（`duplicates.near_duplicates`），只提示不自动归档。
- 版本链：同源键 = 规范化 DOI → arXiv id（去 `vN`）→ 归一化标题+年份。链内角色：期刊/会议/学位论文 = `published`，
  预印本 = `preprint`，补充材料 = `supplement`。keep = 有正式版取正式版，否则取最新；其余复制进 `92_superseded/<chain_id>/`。
- 全流程不删除、不移动源文件；`rollback.sh` 只删除本 Skill 生成的副本。

## 7. 异常与处置表

| 情形 | 识别方式 | 处置 | 记录位置 |
|-|-|-|-|
| 加密 PDF | `/Encrypt` 出现在 trailer | 复制进 `90_quarantine`，分类记 `unknown` | `errors[]` kind=`encrypted_pdf` |
| 扫描件无文本层 | 解压后文本 < 40 字符或字母占比过低 | 归 `30_scans`，标 `pdf_no_text` | `classification.signals` |
| 损坏 PDF/零字节 | 无 `%PDF` 头或 `st_size==0` | 归 `90_quarantine` / `read_status=empty` | `degradations[]` |
| 中文乱码/非 UTF-8 | 解码回退到 GB18030/Big5 或出现 `锟斤拷` | 记录实际编码，仍按内容匹配 | `degradations[]` kind=`encoding` |
| 同名不同版本 | 同 basename 不同 sha256 | 走版本链，不覆盖，分别命名为 `…-<sha8>` 或归档 | `versions.chains` |
| 无权限 | `PermissionError` | `read_status=unreadable`，不进入落库，写人工动作 | `errors[]`、`pending_human[]` |
| 复制后哈希不符 | 复制后重算 sha256 不一致 | 删除该副本，记为失败 | `errors[]` kind=`hash_mismatch` |
| 重复运行 | 目标已存在且哈希相同 | 记 `skipped_exists`，不改写 | `operations.log` |
| 预算耗尽 | 超过 `--time-budget` | 停止后续阶段，finalize 为 `partial`，列出未处理项 | `runtime.budget_stop`、`coverage.deferred` |
| 契约缺失 | case.json 无 `output_contract` | 输出通用 schema，`contract_backfill.source_key=null` | `pending_human[]` |

## 8. 幂等与回滚

同一输入重复运行：已落库且哈希一致的副本记为 `skipped_exists`，`operations.log` 追加而不改写历史；
`before_after.csv` 语义体现在 `inventory.csv`（`staged_path`/`staged_sha256`）与 `result.inventory`；
`rollback.sh` 逐条列出 `rm -f <staged_path>`，执行后输入目录保持原状。

## 9. 适用与不适用

适用：期刊论文/预印本/会议文/学位论文/补充材料/数据表/扫描件/笔记混合的资料库批量整理与交接。
已知限制：伴随元数据表（CSV/JSON/BibTeX 形式的作者-年份汇总）只被盘点并归类为 `metadata_table`，字段仍以文件内证据为准；
文本层稀薄的 PDF（<40 字符）按扫描件处理，题名回退到文件名（`confidence=low`）。
不适用：单篇文献精读或全文翻译、文献检索发现、需要 OCR 的纯图像扫描件（本 Skill 只标 `pdf_no_text`，不做 OCR）、
需要联网校验 DOI 真伪的场景（离线运行，DOI 只作为文本证据，不做在线解码）。

## 10. 自查（交付前逐项）

1. `python3 -B scripts/organize.py --help` 与 `python3 -B scripts/verify.py --help` 退出码 0。
2. `result.json` 含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`inventory`。
3. `output_contract` 全部字段存在（缺值 null/[]），`contract_backfill.field_count` 与已填字段数一致。
4. `inventory.csv` 行数 = 输入文件数；`sha256` 可与源文件重算比对。
5. `library/` 内每个文件都能在 `inventory.csv.staged_path` 找到，且 `staged_sha256` 一致。
6. `operations.log` 非注释行数 = `operations.count`。
7. `verify.py` 输出 `ok=true`（否则按 `failed` 列表修）。
8. 空输入或坏 `case.json` 时仍生成合法 `result.json`，退出码 0。
