---
name: library-auto-organizer
description: >-
  科研文献资料自动分类整理 Skill。先运行内置脚本生成完整基线，再由 Harness Agent 亲自读取真实材料内容、核对关键证据并修正增强，最终产出可复核的目录树、元数据、标签、命名、去重/版本链和完整 result.json。
  适用于 topic library-03（文献与资料自动分类）：归类、打标签、改名、去重、版本区分、批量整理，而不是停在建议层面。
version: 2.0.0
license: MIT
---

# library-auto-organizer

## 1. 总体原则：脚本是工具，Agent 是最终交付物负责人

本 Skill 提供一个完整运行脚本（`scripts/organize.py`）作为**基线工具**。它能生成全套产物：目录树、元数据、标签、命名、去重/版本链、清单、日志和 `result.json`。但是，**任何人、任何 Agent 都不能把基线脚本输出直接当最终成品提交**。

Harness Agent（你）必须：

- **亲自读取 `/input` 下真实材料内容**，至少对关键材料（每个分类目录代表文件、每个版本链成员、每个冲突项）调用 PDF/文本解析工具，阅读提取出的标题、作者、年份、DOI、正文片段等信息。
- **核对脚本生成结果与原文是否一致**：分类依据、标签来源、命名字段、去重/版本判断，必须是“读出来的”，不能只靠文件名或领域标签。
- **修正错误并记录**：发现脚本误判或证据不实时，纠正 `result.json` 中相应条目，并把修改写入 `changes`。
- **诚实标注不确定**：无法确认的字段写 `pending_human` 或 `uncertainty`，不得编造。
- **保留所有基线字段**：修正/增强只能增加或改值，不得删除基线已有字段、不得清空产物；若不慎改动，必须恢复。若脚本基线缺失某些题面要求的字段，Agent 必须补足。

简单说：**脚本负责 80% 的体力活，Agent 负责最后的真实推导与质量背书**。最终交付物必须体现 Agent 亲自阅读材料和核验证据的痕迹，否则评审判为“不完整”或“不是真实推导”。

## 2. 什么时候用 / 不用

**用**：任务要求“整理一批文件”“归类/打标签/改名/去重/建清单”“把资料库交接给他人”，输入是混合 PDF、扫描件、表格、笔记、代码等；或需要维护版本关系（预印本/正式版/修订版/补充材料）并输出可复核、可回滚的操作记录。

**不用**：只问某篇论文讲了什么（阅读类）、要求生成检索式或补全参考文献（检索/写作类）、要求改 Word 正文（写作类）、或要求联网验证 DOI 真伪（本 Skill 离线，DOI 只作文本证据）。

## 3. 运行时契约

| 项 | 约定 |
|-|-|
| 入口 | `python3 -B scripts/organize.py --input /input --output /app/output` |
| 复核 | `python3 -B scripts/verify.py --input /input --output /app/output`（写 `verify_report.json`） |
| 输入 | `/input/case.json`、`/input/task.md` 与 `materials/`、`artifacts/` 等材料；均在 `/input/**` 递归发现 |
| 输出 | `/app/output/{result.json, inventory.csv, operations.log, version_chain.json, rollback.sh, library/, verify_report.json}` |
| 先写 partial | 基线脚本启动即写一版 partial `result.json`；Agent 每次核验/修正后也立即覆盖落盘 |
| 退出码 | 恒 0（异常也写 partial 后返回 0；Agent 收尾时同样确保退出码 0） |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 预算 | 默认 soft 780 秒；超时即 finalize 为 `partial` 并列出未处理项。Agent 需额外预留时间做核验，600 秒时若仍未完成核验，立即进入收尾 |
| 源文件 | 只读。移动/删除一律不做，落库用复制；回滚脚本只删除 `library/` 内副本，不碰源文件 |

## 4. 输入发现（语义识别，不假设键名）

基线脚本会：

1. 读 `/input/case.json`；不存在则递归找 `case*.json`；仍失败则只做目录扫描，并在 `pending_human` 记 `case_json_repair`。
2. 保留 `case_id`；`output_contract`（或 `output_spec`/`result_contract`）整棵保留用于回填；`task_instruction`、`organizer_workorder`、`organizer_supplied_scope` 等键按语义读取并记入 `summary.workorder_keys_seen`。
3. 递归扫描 `/input/**`（跳过符号链接与 `__MACOSX`），按**魔数优先、扩展名兜底**判定类型：`%PDF`、JPEG/PNG 头、ZIP 内 `word/`|`xl/`|`ppt/`、UTF-8 可解码文本。
4. `case.json` 与 `task.md` 属于控制文件：仍进清单（`role=reserved`）但不落库、不分类，作为“跳过并说明”的显式记录。
5. 材料未提供（例如缺 `material.json`、缺伴随表）时**明确列缺口**，不构造内容。

Agent 应在基线运行前先读一遍 `case.json` 和 `task.md`，确认需要交付的字段，避免被脚本通用 schema 误导。如果题面有额外材料（如 PDF、DOCX、CSV、图片），Agent 要在核验阶段真实解析，不得依据文件名猜内容。

## 5. 输出契约与字段

`result.json` 顶层固定包含：`skill`、`case_id`、`status`、`generated_at`、`summary`、`library`、`inventory`、`classification`、`tags`、`naming`、`duplicates`、`versions`、`operations`、`metadata`、`coverage`、`evidence`、`sources`、`uncertainty`、`errors`、`degradations`、`pending_human`、`changes`、`runtime`、`output_contract`、`contract_backfill`。

回填规则：输入契约键名不改、未知键保留；无值标量写 `null`、列表写 `[]`；语义别名表在 `references/rules.json.aliases`；同一份值同时出现在 `output_contract` 内与（不冲突时）顶层，冲突键写进 `contract_backfill.base_key_collisions`。字段级语义、CSV 列、版本链结构见 `references/output_schema.md`。

Agent 在回填时必须先满足 `output_contract` 的**全部字段**，不得因为不想做而少填；若题面没有提供 `output_contract`，脚本已有通用 schema，Agent 不能以此为借口跳过。

## 6. 核心执行流程（Agent 必须逐步完成）

以下为编号步骤，每步都写明输入、动作、输出、失败分支。这是 Frame 的核心。

### 步骤 1：盘点输入并理解任务

- **输入**：`/input/case.json`、`/input/task.md`、`/input/**` 所有材料文件。
- **动作**：
  1. 读取 `case.json`，提取 `case_id`、`output_contract`（若存在）、`task_instruction` 等字段，明确本题必须交付哪些字段。
  2. 读取 `task.md`，确认评分维度、交付要求、运行时契约（尤其是否有额外指定产物）。
  3. 扫描 `/input` 目录，列出文件数量、类型、权限、可能的缺失。可使用 `python3 -B scripts/organize.py --input /input --output /app/work/scan` 预扫描（若担心覆盖正式输出，可用 `--help` 查看选项，但基线脚本会自己扫描；Agent 不必重复做全量）。
- **输出**：任务摘要（记录在 Agent 的思考上下文，不必须写文件），明确“必须产出什么”“现在有什么”。
- **失败分支**：若 `case.json` 缺失或无法解析，记录 `pending_human.case_json_repair`，继续目录扫描，不中断流程；若 `task.md` 缺失，以通用文献整理契约运行，并在 `pending_human` 注明。

### 步骤 2：运行基线脚本，生成全套基线交付物

- **输入**：`/input`（命令行参数）。
- **动作**：执行 `python3 -B scripts/organize.py --input /input --output /app/output`；随后执行 `python3 -B scripts/verify.py --input /input --output /app/output`。
- **输出**：全套基线产物：`/app/output/result.json`、`inventory.csv`、`operations.log`、`version_chain.json`、`rollback.sh`、`library/`、`verify_report.json`。
- **失败分支**：如果脚本异常退出（极少，因为内部有兜底），立即手动创建最小合法 `result.json`（包含 `case_id`、`status="partial"`、`errors=["script_failed"]`、`pending_human=["script_failed"]`、`runtime` 等），然后继续后续步骤，绝不空手。

### 步骤 3：Agent 独立解析与核验（真实推导的核心）

- **输入**：`/app/output/result.json`、`/input` 材料、基线产物（尤其 `evidence`、`signals`、`classifications`、`versions`）。
- **动作**：
  1. 阅读基线 `result.json` 的 `summary`、`classification`、`tags`、`naming`、`duplicates`、`versions`、`errors`、`pending_human` 等关键部分。
  2. **选择核验样本**：
     - 每个分类目录至少 1 个代表文件；
     - 每个版本链至少 1 个组成员（最好包含正式版与预印本各 1）；
     - 每个去重组至少 1 对；
     - 所有 `pending_human`、`errors`、`degradations` 中提到的材料；
     - 所有低置信度（`confidence=low`）材料。
  3. **真实解析材料内容**：调用平台提供的 `pdf-text-tool`（或 `scripts/organize.py` 内置的 PDF 文本提取，或 `pdftotext`），读取所选材料的关键文本片段（标题附近、作者、年份、DOI、摘要第一段、正文第一页等）。若材料是 DOCX/CSV/TXT，则直接读取相应内容。**不得只读文件名**。
  4. **核对一致性**：将提取到的内容与基线 `result.json` 中的每条对应证据（`evidence.locator`、`signals`、`metadata` 字段来源）逐一比对。重点检查：
     - 分类的 `doctype` 是否与原文类型一致；
     - 标签是否真的出现在标题/摘要/关键词/正文中；
     - 命名的作者、年份、标题是否与原文一致；
     - 去重/版本判断是否基于内容哈希或 DOI/arXiv/标题+年份，且证据真实存在。
  5. **记录核验结论**：在 Agent 思考中（后续写回）记下样本路径、提取片段、核对结果（一致/不一致/原因）。
- **输出**：核验记录（不直接写文件，先保留在上下文中，用于步骤 4 写 `agent_review`）。
- **失败分支**：
  - 若解析工具调用失败或时间严重不足，记录 `review_partial`，对已核验的样本写结论，对未核验的样本标记 `agent_review_pending`，并在下一步写入 `metadata.agent_review` 时明确说明。不得假装全部核验。
  - 若某材料无法解析（加密、扫描无文本、损坏），按 §7 异常表处理，并在核验记录中注明“无法核验理由”。

### 步骤 4：Agent 修正与增强，并写回 `agent_review`

- **输入**：步骤 3 的核验记录、`/app/output/result.json`。
- **动作**：
  1. 对核验中发现错误的条目（分类、标签、命名、去重/版本、元数据字段），**亲自修正** `result.json` 中的对应内容；同时修正 `evidence`/`signals` 中的错误来源，确保引用真实。
  2. 对无法确定的内容，在 `uncertainty` 和 `pending_human` 中补记（如“标题与文件名不一致，需人工确认”），不硬改。
  3. 将本次核验与修正写成 **`summary.agent_review`** 和 **`metadata.agent_review`**，至少包含：
     - `samples_reviewed`：核验样本数；
     - `materials_parsed`：实际解析的材料数；
     - `methods`：使用的解析方式（如 `pdf-text-tool`、`docx`、`csv` 读取）；
     - `findings`：发现的关键事实；
     - `errors_found`：基线误差数量与类型；
     - `corrections_made`：修正数量；
     - `pending_issues`：未解决的问题；
     - `review_status`：`full` / `partial` / `pending`；
     - `timestamp`。
  4. 所有修改追加到 `changes` 数组（每条包含 `item`、`before`、`after`、`reason`、`timestamp`）。
- **输出**：更新后的 `result.json`（保持基线所有字段完整，只增强或改值）。
- **失败分支**：若发现重大错误且短期无法修正，保留基线，并将问题写入 `metadata.agent_review.critical_failures` 和 `pending_human`，状态降级为 `partial`。不硬改造成更大错误。

### 步骤 5：完整性自检与契约回填

- **输入**：`/app/output/result.json`、`/input/case.json`（契约）、`/app/output` 全部产物。
- **动作**：
  1. 比对 `output_contract` 的每个键是否都已回填，键名是否原样保留，未知键是否保留；无值标量是否写 `null`、列表是否写 `[]`。
  2. 检查 `inventory.csv` 行数是否等于输入文件数；检查 `library/` 每个文件是否有清单条目和 `staged_sha256` 可复核。
  3. 检查 `operations.log` 非注释行数是否等于 `result.json.operations.count`。
  4. 运行 `python3 -B scripts/verify.py --input /input --output /app/output`，检查 `verify_report.json` 中 `ok: true`。
  5. 若发现字段缺失，立即补齐；若契约缺失，写通用 schema 并记录 `pending_human.contract_absent`。
- **输出**：完整且通过验证的 `result.json` 及配套产物。
- **失败分支**：若自检失败，根据具体缺失补充，再重新运行 verify；直到 `ok: true` 或错误已在 `errors`/`degradations` 中诚实记录。

### 步骤 6：最终收尾与退出

- **动作**：
  1. 最后更新 `result.json` 的 `generated_at`、`runtime`（包含 Agent 核验时间）、`status`（`ok` / `partial` / `needs_human` 按实际）。
  2. 确认 `verify.py` 通过且退出码 0。
  3. 确认所有产物都在 `/app/output`，且 `exit code 0`。
- **输出**：最终交付物。

## 7. 隐藏案例鲁棒性与异常降级

Base 脚本已处理大部分异常；Agent 必须在此基础上诚实标注，不掩盖。以下每个场景都必须**产出合法 `result.json`，退出码 0**。

| 情形 | 脚本基线动作 | Agent 额外动作 |
|-|-|-|
| 材料缺失 / `/input` 空 | 生成空库清单，`pending_human` 记录 `no_materials` | 核验 `case.json` 是否真的没给材料，不臆造；在 `summary.agent_review` 中说明 |
| `case.json` 缺失/损坏 | 记录 `case_json_repair`，继续目录扫描 | 尝试恢复 `case_id`，若不能，写 `case_id=null` 并记录 |
| `output_contract` 缺失 | 写通用 schema 并记 `pending_human.contract_absent` | 不回填空值，但检查是否需要按题面补齐；把题面要求字段都写入顶层 |
| 加密 PDF | 复制进 `90_quarantine`，分类 `unknown`，`errors.encrypted_pdf` | 不尝试破解；核验时记录该文件无法读取内容 |
| 扫描件无文本层 | 归 `30_scans`，标 `pdf_no_text` | 不伪造文本；若题面要求处理扫描件，写入 `pending_human.ocr_required` |
| 损坏/零字节文件 | 进 `90_quarantine`，`read_status=empty`，`errors` 记录 | 不强行解析 |
| 中文乱码/非 UTF-8 | 回退 GB18030/Big5 解码并记录 | 核实编码是否正确，若不正确，修正 `degradations.encoding` |
| 同名不同版本 | 版本链 + `92_superseded/<chain>`，不覆盖 | 核验版本链的决策依据（DOI/arXiv/标题年份）是否真实 |
| 无权限读/写 | 记 `unreadable`，不落库，转人工 | 在 `pending_human` 中给出源路径与建议 |
| 复制后哈希不符 | 删除副本、记失败 | 检查是否是磁盘问题或脚本 bug，必要时重试一次 |
| 重复运行 | 目标同哈希 → `skipped_exists` | 仅在幂等重跑时正常；不做二次重复移动 |
| 格式不支持（如特殊 DOCX 变体） | 记 `unsupported_format`，不伪造 | 尝试用平台工具转换；若不能，记录 `pending_human.unsupported_format` |
| 超时（≥780s 或 总900s 逼近） | 脚本 finalize 为 `partial`，列出 deferred | Agent 若发现时间不足，立即停止新核验，将已有 review 写入，并记录 `budget_stop` |
| 模型请求预算紧张 | 不影响脚本 | Agent 减少全量核验，只挑最高风险样本，保留基线 + 部分 review，不牺牲完整性 |

**任何情况下**，最终 `result.json` 必须存在且合法，退出码 0。若脚本意外失败，Agent 必须手工完成最小合法 `result.json`，包含 `case_id`、`status`、`errors`、`pending_human`、`runtime`、`output_contract`（或通用 schema）。

## 8. 预算策略（64 次模型请求 / 900 秒）

脚本运行与 `verify.py` 不消耗模型请求，但占用时间。合理分配如下：

| 阶段 | 预算（模型请求） | 时间估计 | 是否必须 |
|-|-|-|-|
| 步骤 1 盘点输入 | 2-3 次 | 5-15 秒 | 必须 |
| 步骤 2 运行基线脚本 | 0 次请求 | 30-120 秒 | 必须 |
| 步骤 3 核验关键材料 | 10-20 次 | 60-240 秒 | 必须做核心核验 |
|