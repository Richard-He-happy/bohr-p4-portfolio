---
name: research-library-qa
description: Inventory a research file library and answer knowledge-base questions with verifiable evidence. Scans the input tree, hashes every file (sha256), extracts text from PDF/DOCX/XLSX/CSV/JSON/MD, records metadata with per-field provenance, groups exact duplicates by hash, infers version chains, writes a canonical copy plan, and answers questions with verbatim quotes plus checkable locators, version-conflict warnings and explicit insufficient-evidence verdicts. The Agent must personally verify evidence and finalize deliverables; scripts are tools only.
version: 1.1.0
---

# research-library-qa（科研知识库问答：整理文件，保留版本关系）

## 0. 角色与最高优先级

本 Skill 提供可复跑的基线脚本 `/skills/weekly-skill/scripts/main.py`。脚本只负责机械盘点、哈希、文本提取、重复分组、版本推断、写出初步产物。**你（Harness Agent）是最终交付者**：必须亲自读取 `/input/case.json`、`/input/task.md` 与关键材料原文，核对脚本输出的关键论断、引用、数字、版本关系，并把核验结果写入 `result.json`。禁止把脚本骨架/模板直接当成品；禁止依据文件名、领域标签或 sidecar 摘要猜测内容。每个关键论断必须落到具体文件、具体版本、具体段落/行号，或明确标注 `pending_human`/`limitations`。先运行脚本产出完整基线，保留所有基线产物，再在此基础上增强；不得删除、清空或遗漏任何基线字段。若不确定，保留原产物并标注 `reviewed_by_agent`。任何情况下最终退出码 0，`/app/output/result.json` 必须存在且合法 JSON，包含原 `output_contract` 全部字段与 `case_id`。

## 1. 运行契约

- Skill 安装位置：`/skills/weekly-skill`。工作目录：`/app/work`。输入：`/input`（含 `case.json`、`task.md` 及材料）。输出：`/app/output`。
- 最终产物：`result.json`, `inventory.csv`, `version_chain.json`, `answers.md`, `reorganize_plan.csv`, `operations.log`, `library/`, `verify.json`。可编辑 Office/幻灯片/图形产物需额外真实渲染 PDF/PNG 预览（本题通常不需要，但若 case 要求可编辑产物，必须渲染）。
- 调用脚本：

```bash
cd /skills/weekly-skill && python3 scripts/main.py --input /input --output /app/output
```

- 自检：

```bash
cd /skills/weekly-skill && python3 scripts/main.py --mode verify --output /app/output
```

- 不联网，不使用未说明工具，不使用预制答案。

## 2. 执行流程（编号步骤）

### 步骤 1：盘点输入（1-3 次模型请求）
- 输入：`/input` 目录。
- 动作：运行 `ls -la /input`，读取 `/input/case.json`（若存在）和 `/input/task.md`。识别材料文件类型与数量，检查 `output_contract` 是否存在。
- 输出：内存中记录 case_id、契约字段、材料清单、问题列表。
- 失败分支：`/input/case.json` 缺失/解析失败 → 继续扫描材料，contract 缺失时以降级方式补齐；在 result.json `errors[]` 记录，不要中断。

### 步骤 2：运行基线脚本，立即产出全套基线（1 次 bash 调用）
- 输入：`/input`，`/app/output`。
- 动作：执行 `cd /skills/weekly-skill && python3 scripts/main.py --input /input --output /app/output`。脚本会：扫描文件、sha256 哈希、按 magic bytes 分类、提取 PDF/DOCX/XLSX/CSV/JSON/MD 等文本、合并 sidecar 元数据、按哈希分组重复、推断版本链、对问题做抽取式证据回答、写全套产物和 partial result.json。
- 输出：`/app/output/result.json` 及所有基线产物；脚本保证先写 partial。
- 失败分支：脚本崩溃或超时 → 立即用已产生 partial 或手工落盘最小合法 result.json（含 case_id、output_contract 字段、status、errors），继续步骤 3；绝不能退出非 0。

### 步骤 3：Agent 亲自读取关键材料并核验脚本输出（4-10 次请求，依据材料数量）
- 输入：`/input` 下关键材料（问题中引用文件、版本链涉及文件、元数据文件）与 `/app/output/result.json`、`answers.md`。
- 动作：
  1. 用 `pdf-text-tool` 等工具真实解析关键 PDF 的文本层（若脚本已提取，仍抽查至少 2-3 个关键材料；如果只有 1 个则全读）。
  2. 读取 `result.json` 中 `questions[].evidence[].quote` 与 `locator`；回到材料原文核对引用是否逐字存在、定位是否准确。
  3. 检查 `duplicates` 的哈希分组是否合理，`versions` 链的 latest/version_conflict 是否与文件名、mtime、内容版本标记一致。
  4. 检查 `coverage_dimensions` 六个维度是否有证据：文件类型、元数据字段、目录层级、重复文件、版本差异、权限/来源。
  5. 检查 output_contract 是否全部字段存在；缺失字段需补 `null` 或 `[]` 并注明。
- 输出：形成核验记录：每个问题 verdict 是否认可、每处引用是否吻合、每处冲突是否保留；写入 `result.json` 的 `reviewed_by_agent`、`verification`、`conflicts`、`uncertainty`、`changes` 等处。
- 失败分支：若材料不可读/证据不足，保留脚本标注并追加 `pending_human`/`limitations`，不得编造。若脚本基线缺失某文件，先尝试重跑；仍失败则手工按 schema 补齐。

### 步骤 4：Agent 撰写/增强成品（2-5 次请求）
- 输入：基线产物 + 核验记录。
- 动作：在基线上完善 `answers.md`（确保每个关键论断有引用、定位、版本、不确定提示）、`summary`（简明总结完成度、限制、可复跑性）；必要时完善 `reorganize_plan.csv` 或 `library/` 的说明。不得覆盖脚本正确输出。
- 输出：更新的 `/app/output/*` 文件。
- 失败分支：若无法改进，保留基线并标注 `reviewed_by_agent`；不强制改写。

### 步骤 5：完整性自检与 result.json 回填（2-4 次请求）
- 输入：`/app/output` 当前文件。
- 动作：逐项核对「output_contract 字段 list × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐。运行 verify 脚本。检查 `result.json` 包含 status/sources/uncertainty/change records，status 真实。
- 输出：最终 `/app/output/result.json` 与所有实物；退出码 0。
- 失败分支：发现缺失字段/文件 → 立即手工写入或补文件，然后再次核验。

## 3. 预算策略（64 次模型请求 / 900 秒）

- 优先级：先完成 rubric 高权重的「实际效果 40 分」所需的核心：完整清单、哈希、版本、证据回链、不确定性。因此步骤 1-2 必须最先做且不可跳过。
- 分配参考：
  - 步骤 1 盘点：1-3 次。
  - 步骤 2 运行脚本：1 次 bash 工具调用；脚本运行时间计入 900 秒，注意超时。
  - 步骤 3 核验关键材料：4-10 次，最多读 3-5 个关键文件；不要逐个读所有文件。
  - 步骤 4 增强成品：2-5 次。
  - 步骤 5 自检与回填：2-4 次。
  - 留 10 次以上余量应对重试/异常。
- 若剩余请求不足 10 次或时间不足 120 秒，立即停止增强，只做步骤 5 的最小合法收尾。
- 尽早落盘：脚本运行后结果已落盘；后续 Agent 每更新一次就写一次 result.json（partial 状态可注明 `reviewing` 但必须合法）。
- 避免无意义循环：同一个文件不重复读取；同一处引用核验失败就记录失败，不反复尝试不同措辞。

## 4. 隐藏案例鲁棒性

- 材料缺失/空输入：`status=input_error`，inventory 空，`pending_human` 说明缺什么，result.json 合法。
- `case.json` 损坏/无 output_contract：记录 `errors[]`，从材料中尽力发现任务与问题；缺失契约字段用 `null` 或 `[]` 补齐并注明。
- 文件不可读/权限不足：`readable=false`，排除出证据，入 `failures`/`pending_human`。
- 扫描件 PDF 无文本层：不强行 OCR，标注 `pdf_no_text_layer`，不做证据；若图片可用 `pdf-text-tool` 无法提取，就标明需要 OCR。
- 格式不支持：哈希并入库，`no_text_extractor:<kind>`，不编造内容。
- 超时：900 秒内优先完成最小合法 result.json 和基线产物；脚本已 partial-first，若 Agent 来不及，保留 partial 并注明。
- 版本冲突/证据矛盾：保留双方证据，标注 `version_conflict` 或 `conflict`，不要静默消解。
- 任何情况下退出码 0，`/app/output/result.json` 必须存在且可解析。

## 5. Rubric 维度 → 交付要求 → 自证方式

| Rubric 维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 任务完成度 | 15 | 完整完成多文件检索、带来源问答、证据回链、不确定提示 | `status` ok/partial；`questions[].verdict` 非空；`answers.md` 每问有关键论断 |
| 结果正确性 | 15 | 引用真实、定位准确、答案与证据逐句对应，版本/权限处置正确 | `questions[].evidence[].quote` 与原文逐字一致；`verification.checks[quotes_verbatim].pass`；`sha256` 对应文件 |
| 结果完整性 | 5 | 覆盖六维度：文件类型、元数据字段、目录层级、重复文件、版本差异、权限/来源 | `coverage_dimensions` 六个项均为 true/有数据 |
| 结果可核验性 | 5 | 文件哈希、版本记录、引用定位能独立复核 | `inventory.csv` sha256；`verify.json` 重新哈希/提取通过；locator 含 file/chunk/char_span |
| 质量增益 | 15 | 相比基础 Agent，抽取式证据、缺证判断、版本冲突提示 | `answers.md` 零改写引用；`insufficient_evidence` 明确；`version_conflict` 标记 |
| 效率增益 | 5 | 一轮检索得到清单+版本+问答；减少人工核对 | 单命令运行脚本 + Agent 核验；`operations.log` 显示步骤紧凑 |
| 增益可验证性 | 5 | 关键方法与结果可对照 | `references/method.md` 记录阈值和算法；`verify.json` 可复跑 |
| 新增能力 | 5 | sha256 去重、版本链、缺证判据 | `duplicates` 按哈希；`versions` 带置信度；`uncertainty` 分级 |
| 方法改进 | 5 | 分块、元数据过滤、重复/版本区分具体实现 | `references/method.md`；脚本实现与基线产物展示 |
| 创新证据 | 5 | 说明边界与价值 | `summary` 和 `references/method.md` 中对方法的边界说明 |
| 调用与易用性 | 3 | 可触发、一次完整运行 | SKILL.md 命令清晰，脚本 CLI 简单 |
| 运行稳定性 | 4 | 不同文件类型/规模下可用 | per-file warnings/failures；partial-first；退出码 0 |
| 异常处理 | 3 | 不可读/扫描/权限/空/冲突等识别与处置 | `failures`/`skipped`/`pending_human`/`degradations` 明确 |
| 文档完整性 | 3 | SKILL.md、references 齐备，说明用法/边界 | 本文件 + references/checklist.md、method.md、schema.md |
| 资源可复用性 | 4 | 脚本、配置、模式可被复用 | `scripts/main.py` 和 `library.py` 无第三方依赖，CSV/JSON 产物标准 |
| 分享推广价值 | 3 | 可沉淀问答案例、金标准做法 | `answers.md` 和 `operations.log` 作为可分享记录 |

## 6. 自检清单（提交前逐项检查）

1. `/app/output/result.json` 是否存在且合法 JSON；`case_id` 正确；`status` 真实。
2. 原 `output_contract` 的**全部字段**是否都在 result.json 中，键名未改；缺失项已用 null/[] 补。
3. `inventory.csv` 每行含 rel, role, class, size, sha256, mtime, readable, readability, duplicate_of, version_chain, text_chars, extract_method, metadata fields + provenance。
4. `version_chain.json` 存在且链有 documents/hashes/version tokens/confidence/rule。
5. `answers.md` 中每个问题有 verdict、抽取式答案、证据定位、冲突/不足说明；引用可回到原文件。
6. `reorganize_plan.csv` 与 `library/` 内容存在且哈希已复核。
7. `verify.json` 打印四项检查通过；若未通过，result.json 的 `verification.status` 不为 pass 并说明。
8. 所有 `failures`、`skipped`、`pending_human`、`uncertainty`、`changes` 真实，没有把未完成写成完成。
9. Agent 的 `reviewed_by_agent` 记录已写入 result.json，说明核验了哪些引用/版本/数字。
10. 若 case 需要可编辑产物，已渲染 PDF/PNG 预览；否则无此要求。
11. 最终命令以退出码 0 结束；如果脚本最后退出非 0，用手工写 result.json 确保退出码 0。

## 7. 保留的脚本调用与字段

- 命令行：

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output
python3 /skills/weekly-skill/scripts/main.py --mode verify --output /app/output
```

- 输出契约字段（除非 case 的 `output_contract` 另有规定，这些字段始终存在于 result.json）：
  `status`, `summary`, `library`, `inventory`, `metadata`, `duplicates`, `versions`, `questions`, `coverage_dimensions`, `sources`, `failures`, `skipped`, `conflicts`, `uncertainty`, `pending_human`, `degradations`, `errors`, `changes`, `operations`, `verification`, `runtime`, `output_contract_fields`。
  并且必须 echo 输入 `output_contract` 的每个键。
- 目录约定：
  - `/app/work` 是工作目录，脚本可能在其中写