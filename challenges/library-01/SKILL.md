---
name: research-library-curator
description: Ingest a batch of research files into a rule-driven library with real directory placement, hash-verified inventory, metadata carrying per-field provenance, content-hash deduplication, version chains with diffs, an operations log and a handoff report; answer search questions over the built index and report unreadable, corrupt, conflicting or skipped items instead of hiding them. The Harness Agent must read actual materials, verify derived facts, and produce the final deliverables; scripts are utilities, not the final answer. Use when a case asks to organize, catalogue, deduplicate, version, archive, find or hand over a research file collection.
version: 1.1.0
---

# Research Library Curator（科研资料库落库与版本管理，Agent 增强版）

## 0. 最高优先级：脚本只是工具，最终交付物由你亲自完成

你是在 Harbor 中实际运行本 Skill 的 Harness Agent。`scripts/main.py` 与 `scripts/curator.py` 是**采集、哈希、类型嗅探、元数据抽取、判重、版本链、复制、写基线 JSON/CSV/日志**的工具。它们**不能替你**判断哪些元数据真实、哪些冲突需要人工标注、报告怎么写才可复核、哪些字段来源可信。**最终交付物必须由你亲自读材料、推导、撰写/制作**。禁止把脚本骨架、CSV 模板或基线 JSON 直接当成最终成品；禁止只返回脚本输出而不经审阅与补充；禁止用文件名或领域标签猜内容；禁止为补全字段而编造数据、引用、DOI、数值或状态。

## 1. 用途与边界

**做什么（真实执行，不是给建议）**：把一个批次的科研文件落库到 `<output>/library/<project_code|project>/<year>/<category>/`，为每个文件写 sha256、大小、来源、元数据（逐字段带出处），按**内容哈希**判重、按**内容哈希 + mtime + 版本标记 + 行政批注**重建版本链并给出差异，产出清单、日志、版本谱系、复核报告与交接说明。

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
| 预算 | 900 秒 / 64 次请求 / 单次响应 16384 tokens；单文件文本 ≤2MB、总文本 ≤32MB、文件数 ≤4000，超限记 `degradations`；单文件失败只降级该文件 |

脚本分工：`scripts/curator.py` 负责扫描·哈希·类型嗅探·文本·元数据·判重·版本链·复制；`scripts/main.py` 负责 case/契约解析、产物写出、自检与 `--check`。`main.py` 通过 `Path(__file__).resolve().parent` 导入 `curator.py`。

## 3. 输入发现与材料盘点（Agent 必做前序）

在调用脚本前，你必须先亲自盘点输入，避免脚本输出成为唯一依据。

1. 读取 `/input/case.json`（若无则递归查找 `case*.json`），确认 `case_id`、`output_contract` 及任务说明 `/input/task.md`。
2. 列出 `/input/` 下所有材料文件（含扩展名、大小、可读性）。**不依据文件名或领域标签预测内容**；每个需要解析的文件都应当被工具真实读取。
3. 确认材料数量、类型与契约字段范围。若无法判断某字段是否属于材料，记入 `pending_human` 并在后续处理。

## 4. Agent 专属执行流程（必须按序执行）

### 步骤 1：盘点输入与契约
- 输入：`/input/` 全部文件、`/input/case.json`、`/input/task.md`
- 动作：
  - 用 `ls -la /input` 或等价方式列出所有文件，确认材料与 control 文件。
  - 读取 `case.json`，提取 `case_id` 与 `output_contract` 全部字段。
  - 若 `case.json` 缺失或损坏，记录错误，仍继续扫描材料。
- 输出：内部记录 `case_id`、材料清单、契约字段列表。
- 失败分支：若 `/input` 不可读或为空，进入降级流程（见第 12 节），最终仍产出合法 `result.json`。

### 步骤 2：运行基线脚本，先落盘完整基线
- 动作：执行 `python3 -B scripts/main.py --input /input --output /app/output`。
- 输出：`/app/output/result.json` 及全套基线产物（`inventory.csv`、`metadata.csv`、`operations.log`、`version_chain.json`、`directory_tree.txt`、`report.md`、`run_manifest.json`、`verify_report.json`、`library/`）。
- 失败分支：若脚本因任何原因未产出 `result.json`，你必须手工构造最小合法 `result.json`（含 `case_id`、原 `output_contract` 全字段、固定键、`status` 真实值、`errors` 记录）；不因脚本失败而放弃。

### 步骤 3：用工具真实解析材料
- 输入：步骤 1 材料清单。
- 动作：
  - 对 PDF 使用 pdf-text-tool 提取文本层；对 DOCX 使用相应文本提取工具；对 CSV/TSV 读取真实行列；对图片只读取可得的元数据或说明（不做 OCR）。
  - 将提取结果与脚本 `inventory.csv` / `metadata.csv` 中的来源定位进行比对。
  - 对无法提取的 PDF 标 `no_text_layer`；对损坏文件标 `corrupt`；对无权限文件标 `permission_denied`。
- 输出：材料真实内容摘要、与基线不一致处。
- 失败分支：某文件无法解析时，绝不臆造内容；在 `failures` / `degradations` / `pending_human` 中如实记录。

### 步骤 4：构建/核对证据
- 动作：
  - 执行 `python3 -B scripts/main.py --check --input /input --output /app/output` 获得独立核验报告。
  - 检查 `run_manifest.json` 中每个产物的 sha256 是否与磁盘一致。
  - 抽验至少 3 个关键文件（若有）的 sha256、元数据出处、版本链与去重关系。若基线判断与你自己读到的材料冲突，以真实材料为准修正，并记录到 `changes`。
- 输出：核验结果，写入 `verify_report.json` 或新补充的 `verification.agent_review`。
- 失败分支：核验发现不可恢复的冲突或材料不足以判定，标记 `pending_human` 或 `conflicts`，保持 `status=partial`。

### 步骤 5：Agent 产出完整成品
- 动作：
  - 在基线产物之上增强，不删除、不清空任何基线文件或字段。
  - 亲自撰写或改写 `report.md`：明确目录树、元数据来源、重复与版本关系、失败与恢复、适用边界、限制。
  - 在 `result.json` 的 `verification` 对象中补充 `agent_review`，至少包含：亲读材料列表、核验的关键断言、方法说明、发现的问题、遗留风险。
  - 检查 `result.json` 是否包含原 `output_contract` 全部键名，缺失的以 `null`/`[]`/`{}` 补齐；决不改写键名，不把未知键塞入其他产物。
- 输出：完整成品与合法 `result.json`。
- 失败分支：若时间或预算不足，保留当前完整基线并写清楚 `status=partial` 与 `limitations`，先落盘。

### 步骤 6：自检 rubric 并回填最终 result.json
- 动作：
  - 逐条对照第 13 节「rubric 维度 → 交付要求 → 自证方式」检查。
  - 确认 `result.json` 可 `json.loads`，`case_id` 与输入一致，契约字段 100% 出现。
  - 确认 `status` 真实：所有契约字段有真实值且无未解决阻断才可写 `ok`；否则写 `partial` 或 `input_error`。
  - 无条件重写 `/app/output/result.json` 为最终态，退出码 0。
- 输出：最终合法 `result.json` 与全部交付物。

## 5. 脚本核心流程（供你理解基线）

1. **先落盘**：解析 case 后立刻写 partial `result.json`（含 `contract_echo`、`status=partial`）。
2. **索引**：`lstat`/`stat`、流式 sha256、魔数、编码探测、可读性；不可读 → `read_status=permission_denied` 仍入清单。
3. **元数据（带出处）**：文件名规则 → 伴随表（CSV/TSV/JSON 列表按 file/name/path 列连表）→ 内容（DOI、仪器词、首行标题）→ case 内批注。冲突时高置信度优先，低置信度保留 `confidence`。
4. **判重**：同 sha256 = 精确重复，保留一份（`keep` 优先非 copy/shortest name），其余 `action=exact_duplicate` 且**不重复复制**。
5. **版本链**：排除精确重复后按 `base_key` 分组（去除版本标记与 copy 标记的规范化名 + 扩展名），同组多哈希才成链；按 `(mtime, 版本号, 文件名)` 排序，输出 `supersedes/superseded_by/diff_vs_previous`（文本行增删，否则字节差）。
6. **归位**：`library/<project>/<year>/<category>/<canonical_name>`，复制后**重算哈希校验**；不符即删除半成品并记 `hash_mismatch_after_copy`；同名不同内容 → `__altN`，同名同哈希 → `reuse`（不复制）。
7. **记账**：每次复制/复用/跳过写 `operations.log`（含 before/after 哈希）。
8. **自检 + finalize**：`--check` 的 9 项不变量检查写 `verify_report.json` 并回填 `verification`，**无条件**重写 `result.json`（终态），退出码 0。

## 6. 输出契约与产物清单（原样回填）

`result.json` 顶层**原样包含输入 `output_contract` 的每个键**：键名不改、未知字段保留、缺值 `null`/`[]`/`{}`；`case_id` 原样保留。同时保留 `contract_echo`（契约原文）与 `contract_unresolved`（未能映射的字段及所填类型），便于核对未被改写。

固定键：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`inventory`、`directory`、`metadata`、`versions`、`duplicates`、`operations`、`failures`、`queries`、`report`、`metrics`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`verification`。

契约字段按"键名 + 描述"匹配到上述产物；键名含 `unknown|other|extra|misc|其它|其他` 的一律视为未知 → `null`/按描述取空容器，绝不塞入别的产物。

**产物清单**：`result.json`、`inventory.csv`、`metadata.csv`（长表：item_id,field,value,source,locator,confidence）、`operations.log`（JSONL）、`version_chain.json`、`directory_tree.txt`、`report.md`、`run_manifest.json`（每个产物的 sha256）、`verify_report.json`、`library/` 文件树。

你可以在 `verification` 对象内新增 `agent_review` 字段，记录你的亲自核验，但不得修改或删除固定键与契约键。

## 7. 目录模板与命名

```
library/<project>/<year>/<category>/<canonical_name>
```

- `project`：元数据 `project_code`（如 `PROJ-2023-014`，可由文件名正则得到）→ 退 `project`（项目名）→ `_unassigned`
- `year`：仅取**文件名/伴随表**的 1900–2100 四位年份（且排除项目号内的数字）；取不到 → `_undated`。mtime 年只写进 `metadata.mtime_year`（`source=derived`），**不当作年份入目录**
- `category`：`01_literature`（PDF 且有 DOI 或 journal/article/abstract 信号）、`02_documents`、`03_tables`、`04_figures`、`05_code`、`06_archives`、`07_other`
- `canonical_name`：NFC 归一、控制字符与 `<>:"/\|?*` → `-`、折叠空白、≤120 字符（保留扩展名）；原始名始终保留在 `inventory.csv:filename`
- 冲突：目标已存在且哈希相同 → `reuse`；不同 → `__altN` + `integrity_flag=name_conflict`；**不覆盖**

## 8. 元数据字段字典（含出处等级）

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

## 9. 证据与定位

- `inventory.csv:sha256` 是唯一事实锚点；`operations.log` 的 before/after 哈希证明复制完整。
- `run_manifest.json` 记录所有产物大小与 sha256 + `run_id`（由契约版本、case_id、输入哈希集合派生），他人可复跑比对。
- 复跑一致性：同输入再跑，已入库文件 `action=reuse`、`copied=0`，清单排序与哈希集合不变。

你在 `agent_review` 中应引用上述证据，并注明你亲自核验了哪些文件、哪些结论由材料直接支持、哪些依赖脚本推断。

## 10. 冲突与人工确认

进 `pending_human`：`authors/title/doi` 全无来源；批注目标文件不在批次内（`admin_or_alias_unresolved`）；契约缺失（`contract_missing`）；重名不同内容无法判定替代关系；文件损坏；权限不足；空间不足。
原则：**宁可标"未完成"，不写成"已完成"**；任一未解决阻断项 → `status=partial`；无 case → `input_error`；批次为空 → `insufficient_evidence`。

## 11. 预算策略（64 次请求内完成）

预算感知优先级：**实际效果 40 分 > 使用增益 25 分 > 创新增益 15 分 > 可靠体验 10 分 > 生态贡献 10 分**。务必先保证实际效果与完整交付。

建议分配：

| 请求范围 | 动作 | 说明 |
|---|---|---|
| 1–2 | 盘点输入、读 `case.json` / `task.md`、确认契约 | 合并观察，不要反复列举目录 |
| 3–4 | 运行脚本产出基线；确认 `result.json` 存在且合法 | 脚本调用通常 1 次即可，失败时再补 1 次诊断 |
| 5–12 | 真实解析关键材料（PDF/DOCX/CSV） | 优先处理高价值、影响元数据与版本判断的文件；可批量调用工具 |
| 13–18 | 核验基线关键断言；运行 `--check` | 检查哈希、去重、版本链、契约字段 |
| 19–26 | 撰写/补强 `report.md`，回填 `result.json.verification.agent_review` | 保留全部基线字段，只增不删 |
| 27–32 | 自检、修复、最终重写 `result.json` | 契约字段缺失、非法 JSON、状态不真实等优先修复 |
|