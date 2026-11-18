---
name: research-library-curator
description: Ingest a batch of research files into a rule-driven library with real directory placement, hash-verified inventory, metadata carrying per-field provenance, content-hash deduplication, version chains with diffs, an operations log and a handoff report; answer search questions over the built index and report unreadable, corrupt, conflicting or skipped items instead of hiding them. Use when a case asks to organize, catalogue, deduplicate, version, archive, find or hand over a research file collection (整理文件/落库/元数据/去重/版本/归档/清单/检索).
version: 1.0.0
---

# Research Library Curator（科研资料库落库与版本管理）

## 1. 用途与边界

**做什么（真实执行，不是给建议）**：把一个批次的科研文件落库到
`<output>/library/<project_code|project>/<year>/<category>/`，为每个文件写 sha256、大小、来源、元数据（逐字段带出处），按**内容哈希**判重、按**内容哈希 + mtime + 版本标记 + 行政批注**重建版本链并给出差异，产出清单、日志、版本谱系、复核报告与交接说明。

**不适用 / 不做**
- 不做语义检索：`queries[]` 是词法匹配（文件名/路径/元数据/抽取文本），`method` 字段显式标注 `lexical`。
- 不移动、不改写、不删除源文件：只**复制**入库，源目录只读。
- 不猜作者、期刊、DOI、仪器：抽不到就是 `null` + `pending_human`。
- 不做 OCR：无文本层的 PDF 记 `no_text_layer`，不生成假文本。
- 不做云同步/断点续传协议层；重名冲突保留双份并记录，永不覆盖。

## 2. 运行契约（Harbor）

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`；材料在 `/input/` 任意子目录、任意扩展名 |
| 输出 | `/app/output/`（含 `result.json` 与主产物；`library/` 下是真实文件） |
| 入口 | `python3 -B scripts/main.py --input /input --output /app/output` |
| 复核 | `python3 -B scripts/main.py --check --input /input --output /app/output` |
| 退出码 | **恒 0**；问题写进 `errors`/`degradations`/`pending_human`，不用退出码表达 |
| 依赖 | 仅 Python 3 标准库（csv/json/hashlib/zipfile/zlib/difflib/shutil/os/re）；不联网、不读包外路径、不依赖 CWD |
| 预算 | 900 秒 / 64 次请求；单文件文本 ≤2MB、总文本 ≤32MB、文件数 ≤4000，超限记 `degradations`；单文件失败只降级该文件 |

脚本分工：`scripts/curator.py` 负责扫描·哈希·类型嗅探·文本·元数据·判重·版本链·复制；`scripts/main.py` 负责 case/契约解析、产物写出、自检与 `--check`。`main.py` 通过 `Path(__file__).resolve().parent` 导入 `curator.py`。

## 3. 输入发现（语义识别，不假设键名）

1. case 候选：`--input` → `/input` → `/app/input` → `./input`，取 `case.json`，否则递归 `case*.json`；坏 JSON 记 `errors` 后继续（不崩）。
2. 在 case 内递归（深度 ≤6）按**键名模糊匹配**收集语义对象，**跳过 `output_contract` 子树**避免把契约字段当成数据：
   - `output_contract|contract|output_spec|契约` → 契约（dict 原样；`[{field,description}]` 列表规范化为 dict）
   - `alias|别名|rename|曾用名` → 别名记录；`note|admin|supersed|replace|批注|版本说明` → 行政批注
   - `quer|search|question|ask|检索|查询|问题` → 检索问题（`\b` 边界，避免命中 `task_instruction`）
3. 扫描输入目录全部文件，按**扩展名 + 魔数**双判类型；`case*.json`/`task.md` 记 `role=control` 列入 `failures.excluded`（不静默丢弃）。
4. 取不到的字段 → `null` + 汇总进 `pending_human`；不构造值。

## 4. 输出契约（原样回填）

`result.json` 顶层**原样包含输入 `output_contract` 的每个键**：键名不改、未知字段保留、缺值 `null`/`[]`/`{}`；`case_id` 原样保留。同时保留 `contract_echo`（契约原文）与 `contract_unresolved`（未能映射的字段及所填类型），便于核对未被改写。

固定键：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`inventory`、`directory`、`metadata`、`versions`、`duplicates`、`operations`、`failures`、`queries`、`report`、`metrics`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`verification`。

契约字段按"键名 + 描述"匹配到上述产物；键名含 `unknown|other|extra|misc|其它|其他` 的一律视为未知 → `null`/按描述取空容器，绝不塞入别的产物。

**产物清单**：`result.json`、`inventory.csv`、`metadata.csv`（长表：item_id,field,value,source,locator,confidence）、`operations.log`（JSONL）、`version_chain.json`、`directory_tree.txt`、`report.md`、`run_manifest.json`（每个产物的 sha256）、`verify_report.json`、`library/` 文件树。

## 5. 核心流程

1. **先落盘**：解析 case 后立刻写 partial `result.json`（含 `contract_echo`、`status=partial`）。
2. **索引**：`lstat`/`stat`、流式 sha256、魔数、编码探测、可读性；不可读 → `read_status=permission_denied` 仍入清单。
3. **元数据（带出处）**：文件名规则 → 伴随表（CSV/TSV/JSON 列表按 file/name/path 列连表）→ 内容（DOI、仪器词、首行标题）→ case 内批注。冲突时高置信度优先，低置信度保留 `confidence`。
4. **判重**：同 sha256 = 精确重复，保留一份（`keep` 优先非 copy/shortest name），其余 `action=exact_duplicate` 且**不重复复制**。
5. **版本链**：排除精确重复后按 `base_key` 分组（去除版本标记与 copy 标记的规范化名 + 扩展名），同组多哈希才成链；按 `(mtime, 版本号, 文件名)` 排序，输出 `supersedes/superseded_by/diff_vs_previous`（文本行增删，否则字节差）。
6. **归位**：`library/<project>/<year>/<category>/<canonical_name>`，复制后**重算哈希校验**；不符即删除半成品并记 `hash_mismatch_after_copy`；同名不同内容 → `__altN`，同名同哈希 → `reuse`（不复制）。
7. **记账**：每次复制/复用/跳过写 `operations.log`（含 before/after 哈希）。
8. **自检 + finalize**：`--check` 的 9 项不变量检查写 `verify_report.json` 并回填 `verification`，**无条件**重写 `result.json`（终态），退出码 0。

## 6. 目录模板与命名

```
library/<project>/<year>/<category>/<canonical_name>
```

- `project`：元数据 `project_code`（如 `PROJ-2023-014`，可由文件名正则得到）→ 退 `project`（项目名）→ `_unassigned`
- `year`：仅取**文件名/伴随表**的 1900–2100 四位年份（且排除项目号内的数字）；取不到 → `_undated`。mtime 年只写进 `metadata.mtime_year`（`source=derived`），**不当作年份入目录**
- `category`：`01_literature`（PDF 且有 DOI 或 journal/article/abstract 信号）、`02_documents`、`03_tables`、`04_figures`、`05_code`、`06_archives`、`07_other`
- `canonical_name`：NFC 归一、控制字符与 `<>:"/\|?*` → `-`、折叠空白、≤120 字符（保留扩展名）；原始名始终保留在 `inventory.csv:filename`
- 冲突：目标已存在且哈希相同 → `reuse`；不同 → `__altN` + `integrity_flag=name_conflict`；**不覆盖**

## 7. 元数据字段字典（含出处等级）

| 字段 | 来源顺序 | `source` 取值 |
|---|---|---|
| `title` | 伴随表 → 内容首行（>12 字符） | `companion_table|content` |
| `authors` | 伴随表 → 内容 | `companion_table|content` |
| `year` | 文件名四位年（排除项目号内）→ 伴随表 | `filename|companion_table` |
| `mtime_year` | 文件系统 mtime 年（仅参考） | `derived` |
| `project` / `project_code` | 伴随表 → 文件名编码 | `companion_table|filename` |
| `instrument` | 文件名 → 内容词表（LC-MS/GC-MS/ICP-MS/HPLC/XRD/SEM/TEM/NMR/FTIR/Raman/MicroCT/PCR） | `filename|content` |
| `doi` | 内容正则 `10.\d{4,9}/…` → 文件名 | `content|filename` |
| `version_label` | 文件名（`v3`、`_final`、`定稿`、`修订`、`copy`、`(1)`） | `filename` |
| `notes` | case 内别名/行政批注原文 | `admin_note` |
| `data_type` | 伴随表 → 扩展名推断 | `companion_table|derived` |

`metadata.csv` 每行一个字段：`locator` 形如 `filename#regex:year`、`content:offset=123`、`artifacts/notes.csv:row=2`、`$.admin_notes`。**无出处不写值**；缺失字段不逐文件刷屏，汇总进 `pending_human`。

## 8. 证据与定位

- `inventory.csv:sha256` 是唯一事实锚点；`operations.log` 的 before/after 哈希证明复制完整。
- `run_manifest.json` 记录所有产物大小与 sha256 + `run_id`（由契约版本、case_id、输入哈希集合派生），他人可复跑比对。
- 复跑一致性：同输入再跑，已入库文件 `action=reuse`、`copied=0`，清单排序与哈希集合不变。

## 9. 冲突与人工确认

进 `pending_human`：`authors/title/doi` 全无来源；批注目标文件不在批次内（`admin_or_alias_unresolved`）；契约缺失（`contract_missing`）；重名不同内容无法判定替代关系；文件损坏；权限不足；空间不足。
原则：**宁可标"未完成"，不写成"已完成"**；任一未解决阻断项 → `status=partial`；无 case → `input_error`；批次为空 → `insufficient_evidence`。

## 10. 预算与断点

时间/字节上限见 §2；超限记 `degraded`，不再新增抽取，直接 finalize 已得结果。`runtime.elapsed_s`、`runtime.python` 记录真实运行信息。任何中断前 `output/result.json` 都是合法 JSON。

## 11. 异常降级分支表

| 情形 | 检测 | 处置 | 记录 |
|---|---|---|---|
| 零字节 / 上传中断 | `size==0` | 入清单，标 `empty_file`，不参与版本比较 | `degradations` |
| 权限不足 | 读/stat 失败 | 不复制，`read_status=permission_denied` | `failures.unreadable` |
| 目录不可遍历 | `os.walk onerror` | 记录该目录，继续其余 | `failures.denied_paths` |
| 重名冲突 | 目标存在且哈希不同 | `__altN` 双份保留 | `operations.log:name_conflict` |
| 扩展名/魔数不符 | 魔数表比对 | 仍入库，标 `ext_magic_mismatch` | `failures.integrity_suspect` |
| 复制后哈希不符 | 重算 sha256 | 删除半成品 + `copy_rollback` | `errors` |
| 压缩/Office 损坏 | `zipfile` 异常 | 仅元数据，`read_status=corrupt` | `errors` |
| PDF 无文本层 | 抽取为空 | 仅元数据，`no_text_layer` | `degradations` |
| 元数据缺失 | 全来源皆无 | `null` + 缺口汇总 | `pending_human` |
| 存储不足 | `disk_usage().free < 50MB` | 只写清单/日志，跳过复制 | `degradations:disk_space` |
| case.json 坏 | `JSONDecodeError` | 空契约继续扫描 | `errors` |
| 输出不可写 | mkdir/写失败 | 退到 `./output` 仍写 result.json | `errors` |

## 12. 调用方式与最小示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py --input /input --output /app/output          # 落库
python3 -B scripts/main.py --check --input /input --output /app/output  # 独立复核
python3 -B scripts/main.py --help
```

示例输入（示例，非正式案例结果）：

```json
{"case_id": "demo-001",
 "output_contract": {"inventory": "list of files", "version_chains": "array", "status": "string"},
 "aliases": {"旧名_A.csv": "sample_A_v2.csv"},
 "queries": ["2019 年 XRD 原始数据在哪"]}
```

示意输出（示例，非正式案例结果，字段截断）：`status="partial"`；`inventory` 3 条（1 条 `exact_duplicate`、1 条 `reuse`）；`versions.chains[0]` 为 `sample_A.csv → sample_A_v2.csv`（依据 `sha256` 差异 + mtime + `v2` 标记，`diff_vs_previous.lines_added=2`）；`queries[0].answer` 指向 `library/PROJ-2023/2019/01_literature/…`；`pending_human` 记"authors/doi 缺失 2 项"。真实案例结果以运行时产物为准。

## 13. 自检清单（运行后逐条确认）

1. `result.json` 可 `json.loads`，`case_id` 与输入一致，契约键 100% 出现（`verification` 中 `contract_complete`）。
2. `materials_indexed + excluded + denied_paths == files_seen`（无静默跳过）。
3. `source_sha256_recompute` 与 `library_copies_verified` 均通过（源文件与副本哈希逐一重算）。
4. 精确重复组内哈希相同、组间不重复；版本链成员哈希互异、`order` 连续、有 `diff_vs_previous`。
5. `operations.log` 每行合法 JSON 且覆盖每次复制/复用/跳过；`version_chain.json`、`inventory.csv`、`metadata.csv`、`report.md` 均存在。
6. `run_manifest.json` 中每个文件的大小/哈希与磁盘一致；重复运行 `copied=0`。
7. 无预制答案、无编造 DOI/数值；所有示例均标注"示例"。

## 14. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：用途/契约/流程/规则/异常/自检 |
| `scripts/main.py` | CLI 入口：路径解析、case+契约、产物写出、9 项自检、`--check` |
| `scripts/curator.py` | 采集核心：扫描、哈希、类型嗅探、文本、元数据出处、判重、版本链、复制 |
| `references/library-rules.md` | 目录模板、命名规则、判重/版本策略、字段字典、处置矩阵 |
| `references/output-schema.md` | `result.json`/`inventory.csv`/`metadata.csv`/`version_chain.json`/`operations.log`/`verify_report.json` 字段级说明与契约映射 |
| `references/playbook.md` | 分步操作手册、复核方法、降级演练、FAQ、限制与维护记录 |

版本 `1.0.0`（2026-11）。已知边界：PDF 文本依赖 FlateDecode 明文串（无 pdftotext 更快更准的路径，扫描件无文本层）；检索为词法匹配；不维护跨批次增量库；版本顺序以 mtime 为主键。维护：改规则先改 `references/library-rules.md`，再同步 `curator.py` 的 `CG/FA/INSTR/VW` 与本表版本号。
