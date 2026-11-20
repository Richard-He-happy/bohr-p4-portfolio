---
name: systematic-screening-audit
description: Run an auditable systematic literature screening on an organizer record snapshot — criteria operationalization with version fingerprint, query log, DOI/title/fuzzy dedup with merge basis, title/abstract inclusion-exclusion with reason codes and verbatim evidence quotes, dual-annotator conflict arbitration, count-closure audit chain, and reusable label/arbitration/audit export. The Harness Agent must read actual input materials, verify and derive the final deliverable; scripts are tools only.
version: 2.0.0
---

# systematic-screening-audit

## 0. 给 Harness Agent 的总指令（必读）

本 Skill 用于把科研问题、检索约束和题录快照转换成可审计的系统性筛选结果。最终交付物由你（Harness Agent）**亲自阅读 /input 下的真实材料、逐条推导、逐段核验后撰写/制作**。`scripts/main.py` 和 `scripts/verify.py` 只是确定性工具，用来快速生成基线产物、检测引用片段真伪、审计计数闭合，**不能把脚本骨架、空模板或未核对的默认输出直接当作成品**。

你必须做到：

- 真实读取 `/input/case.json`、`/input/task.md` 以及所有材料文件（PDF/DOCX/CSV/JSON/图片等），不得依据文件名、领域标签或记忆猜测内容。
- 先运行基线脚本产生全套交付物，然后在此基础上做 **Agent 核验与增量增强**，不得删除或清空基线产物。
- 所有标签、理由码、证据引用、去重合并依据、冲突仲裁结论，都要能回溯到原始材料中的真实片段。
- 遇到材料缺失、格式不支持、字段不全、编码乱码、计数不闭合等情况，必须诚实标注 `pending_human`、`limitations`、`errors` 或 `degradations`，不得补造文献、数据、引用、分数。
- 任何情况下都要在 `/app/output` 写出合法 `result.json`，并保持退出码 0。

## 1. 用途与范围

**用途**：输入一个科研问题、纳入/排除标准、检索约束和一组题录快照（JSON/JSONL/CSV/TSV 等），输出可追溯的候选文献集、逐条纳入/排除标签、理由码、真实证据片段、去重合并依据、双标注者冲突仲裁记录、计数闭合审计链，以及可复用标签表/仲裁表/查询日志/审计日志。

**范围内**：检索协议日志、题录去重、标题与摘要筛选、标准版本管理与指纹、双规则配置冲突仲裁、审计链生成、流程指标计算、结果可核验导出。

**范围外**：全文精读、质量评价、数据提取、统计分析、论文写作；不声称全局召回，不进行实际数据库联网；不替代研究者对边界文献的最终科学判断。

## 2. 运行时契约与输入输出

| 项 | 约定 |
|---|---|
| 输入目录 | `/input`（只读）：`case.json` + `task.md` + 材料文件（`artifacts/` 或根目录下） |
| 工作目录 | `/app/work`：你的笔记、中间文件可写在这里，不影响最终交付 |
| 输出目录 | `/app/output`：最终实际结果和可编辑产物必须放这里 |
| 必备结果 | `result.json`，必须包含原 `output_contract` 的全部字段（键名不改）和 `case_id` |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 退出码 | 所有路径下都必须为 0，即使任务部分失败 |

`result.json` 应包括的字段见第 8 节；详细 schema 见 `references/io-schema.md`。可编辑 Office/幻灯片/图形产物必须额外生成**真实渲染的 PDF/PNG 预览**，方便检查。

必须先真实解析材料，不得仅靠脚本推断材料内容；脚本运行失败时，你仍要基于已读取的内容手写合法结果并标注限制。

## 3. 本题专属执行流程（必须按顺序完成）

### 步骤 1：盘点输入与任务要求

- **输入**：`/input` 目录。
- **动作**：
  1. 列出 `/input` 目录全部文件，记录文件名、大小、扩展名。
  2. 读取 `/input/case.json` 与 `/input/task.md`，找出 `output_contract`（如果有）、研究问题、纳入/排除标准、检索范围、题录文件路径或内嵌记录。
  3. 识别所有材料文件（PDF/DOCX/CSV/JSON/JSONL/TSV/图片等），不要依据文件名判断内容。
- **输出**：在 `/app/work/run_notes.md` 写一份简短工作清单：问题、标准、记录来源、材料路径、契约字段。
- **失败分支**：
  - 若 `/input/case.json` 不存在或 JSON 非法，寻找其他 `case*.json`；仍缺失或不可解析，则生成最小合法 `result.json`：`status: "input_error"`，`errors` 写清原因，契约未知用 `[]`/`{}` 回填，退出码 0。
  - 若 `task.md` 缺失，不阻断；从 case.json 提取任务信息继续。

### 步骤 2：运行基线脚本，先落盘全套基线

- **输入**：已确认的 `/input` 与 `/app/output` 目录。
- **动作**：执行
  `python3 scripts/main.py -i /input -o /app/output`
  该脚本会解析输入、生成 criteria、查询日志、去重、筛选标签、仲裁表、审计记录、候选文献，并写出：
  - `result.json`
  - `candidates.csv`
  - `screening_labels.csv`
  - `arbitration.csv`
  - `query_log.json`
  - `dedup_log.json`
  - `audit.json`
- **输出**：基线全套产物。
- **失败分支**：
  - 若脚本异常崩溃或无法运行，不得清空 `/app/output`；改用你已读取的真实材料，在 `/app/output/result.json` 手写最小合法结果，记录 `errors` 与 `degradations`，退出码 0。
  - 如果只是个别材料格式不支持，脚本可能跳过并记录；你要保留这些记录，不要删除。

### 步骤 3：真实解析材料并核对证据基础

- **输入**：`/input` 下所有材料文件；步骤 2 的基线输出。
- **动作**：
  1. 对 PDF 使用 `pdf-text-tool` 等真实解析；对 DOCX 使用相应工具解析；对 CSV/TSV 使用可用的 Python 解析或直接读取；对图片若有文字，用 OCR 工具但需在结果中说明 OCR 不确定性。
  2. 读取原始题录记录，逐字段核对 `title`、`abstract`、`doi`、`authors`、`year`、`venue`、`source_db`、`query_id`、`retrieved_at` 等；注意字段别名可能不同。
  3. 核对纳入/排除标准，确认标准版本、标题摘要原文是否与基线 criteria 一致。
  4. 查看基线输出的 `query_log.json`、`dedup_log.json`、`screening_labels.csv`，确认它们引用的记录数和字段与原始记录一致。
- **输出**：在 `/app/work/run_notes.md` 更新核对结果，记录哪些来源已核验、哪些存在编码/字段/解析问题。
- **失败分支**：
  - 某材料损坏、无法解析或格式不支持：保留该路径，记录到 `errors`/`degradations`，相关记录标记 `pending_human`；继续处理其余材料。
  - 题录为空或没有合法记录：生成 `insufficient_evidence` 状态，不编造候选文献。

### 步骤 4：Agent 亲自核验与推导筛选结果

- **输入**：基线输出文件与原始材料。
- **动作**：
  1. 打开 `screening_labels.csv`、`arbitration.csv`、`dedup_log.json`、`candidates.csv`。
  2. 对每一条 **纳入/排除/待人工确认** 的记录，至少核对：理由码是否匹配标准条目；`evidence` 引用是否为标题或摘要中的逐字片段；去重合并依据是否合理、是否有误并；冲突结论是否符合优先级规则。
  3. 重点核验边界记录、低覆盖记录、无摘要记录、DOI 缺失记录、冲突僵持记录。如果发现脚本判断与标准要求不一致，将你的推断和依据写入 `result.json` 的 `agent_review` 字段（例如 `verification` 列表），并更新 `changes` / `errors`。
  4. 如果你修正了任何标签、理由码或证据片段，必须同步更新对应的 CSV 文件，并保证 `screening_labels.csv` 与 `result.json.counts` 闭合。
  5. 将核验情况写入 `result.json`：例如 `sources` 列出实际读取的材料路径；`uncertainty` 说明哪些边界未决；`pending_human` 列出需要研究者确认的项；`changes` 记录脚本输出与你的核验之间的变更。
- **输出**：一套经过 Agent 核验并增强的筛选结果，不删除基线产物。
- **失败分支**：发现严重不一致但无法立刻解决，保留原记录，在 `errors` 和 `pending_human` 中说明；不要让矛盾静默存在。

### 步骤 5：产出最终文件与预览

- **输入**：步骤 4 更新后的输出目录。
- **动作**：
  1. 确认 `/app/output` 下所有承诺交付文件均存在（见第 8 节）。
  2. 若存在可编辑 Office/幻灯片/图形产物，用可用工具生成真实渲染的 PDF/PNG 预览，放在 `/app/output` 并为预览文件命名清晰。
  3. 核对 CSV 行数与 `result.json` 中的 counts、审计等式是否一致。
- **输出**：完整、可检查的最终产物集合。
- **失败分支**：若无法生成预览，例如缺少 LibreOffice/工具，记录到 `degradations`，并说明预览缺失原因；不要伪造预览文件。

### 步骤 6：最终自检与回填 result.json

- **输入**：`/app/output` 全部交付物。
- **动作**：
  1. 运行
     `python3 scripts/main.py --check -i /input -o /app/output`
     它会重新证明契约键、证据引用逐字性、计数等式、去重簇完整性、仲裁行合法性等，并生成 `verification_report.json`。始终退出 0。
  2. 对照第 6 节 rubric 映射表与第 7 节自检清单逐项检查。
  3. 回填 `result.json`：确保所有 `output_contract` 字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime` 均存在且真实。
- **输出**：最终合法 `result.json`。
- **失败分支**：若 `--check` 发现错误，优先修复脚本输出与你手动修改之间的不一致；如果无法修复，记录到 `errors` 并保证 `status` 如实为 `partial` 或 `input_error`，仍退出 0。

## 4. 预算策略

总预算为 64 次模型请求、900 秒。请按以下优先级分配：

| 步骤 | 建议请求数 | 优先级 | 说明 |
|---|---|---|---|
| 1. 盘点输入 | 1–3 | 必须 | 只读取必要文件，不要重复读取大材料 |
| 2. 运行基线脚本 | 1 | 必须 | 脚本本身耗时为秒级，不占 token；立即得到全套基线 |
| 3. 真实解析材料 | 3–10 | 必须 | 优先解析记录集和 criteria；大 PDF 只解析相关页或关键段落，避免全文重复读取 |
| 4. Agent 核验与推导 | 5–15 | 最高 | 优先核验候选集、排除理由、证据引用、去重、冲突；时间或请求紧张时先核验纳入集和边界冲突 |
| 5. 最终文件与预览 | 2–6 | 中 | 确认文件存在、行数闭合；可编辑格式预览如果耗时过多，记录缺失原因即可 |
| 6. 最终自检与回填 | 1–4 | 必须 | 必须先落盘 honest partial 再增量改进 |

**落盘策略**：步骤 2 后即保证 `/app/output/result.json` 合法存在。之后每次修改都写回磁盘。剩余时间低于 120 秒或已使用 ≥60 次请求时，立即停止增强，回填 `status`、`runtime`、`errors`/`limitations`，退出 0。不要进行无意义的反复读取或循环检查。

## 5. 隐藏案例鲁棒性

| 情况 | 降级与诚实标注策略 |
|---|---|
| `case.json` 缺失、非法 JSON | 尝试其他 `case*.json`；仍无则 `status: "input_error"`，`errors` 写明，输出合法最小 `result.json`，退出 0 |
| 没有题录记录 / 空输入 | `status: "insufficient_evidence"`，`candidates: []`，`uncertainty` 说明，不编造文献 |
| 材料损坏或格式不支持 | 保留源文件路径，记录到 `degradations`；相关记录标 `pending_human`；继续处理其余记录 |
| PDF/DOCX 解析失败 | 用其他可用工具重试一次；仍失败则记入 `errors`，该材料相关记录标 `pending_human` |
| 摘要缺失 | 记录仍基于标题筛选；标签加 `NO_ABSTRACT`，confidence ≤0.35，证据引注只能来自标题 |
| DOI 缺失 | 去重回退到归一化标题 + 模糊标题 + 第一作者 + 年份窗口；记录 `NO_DOI` |
| 编码乱码 / mojibake | 按 `utf-8-sig → utf-8 → gb18030 → cp1252` 解码；cp1252 仅当替换字符减少时使用；无法修复则记录错误 |
| 字段名不一致 / 嵌套记录 | 用 `references/io-schema.md` §1 的语义发现规则，不依赖键名；找不到则按无记录处理 |
| criteria 缺失 | 所有记录 `SYS-NO-CRIT` → `pending_human`，`status: "partial"` |
| 双标注者/双规则僵持 | 按 `references/criteria-codes.md` §4 优先级；仍不能判定则 `pending_human`，绝不平均化 |
| 计数不闭合 | 记录错误，`status: "partial"`，保留计算出的数字，不强行改数 |
| 输出目录不可写 | 尝试 `/app/output`；若不可写，使用 `/app/work/output_fallback`，并在 `errors` 说明；不能崩溃 |
| 超时或请求耗尽 | 保证最后一次写回 `result.json`，其中 `status` 如实，退出 0 |

任何情况下都要生成合法 `result.json` 并退出码 0。

## 6. Rubric 维度 → 交付要求 → 自证方式对照表

| Rubric 维度 | 交付要求 | 如何自证 |
|---|---|---|
| 任务完成度（闭环） | 从 criteria → queries → dedup → screening → arbitration → candidates 各环节都有产出 | `result.json` 的 `criteria`、`queries`、`screening`、`dedup`、`arbitration`、`counts`、`candidates` 均非空且相互连接 |
| 结果正确性 | 每条记录标签符合当前标准版本；理由码指向真实标题/摘要片段；去重不误并/漏并 | `screening[].matched_criteria` + `evidence[]` 逐字引用；`dedup[].basis`；`scripts/main.py --check` 逐字验证证据 |
| 结果完整性 | 检索、去重、纳排、冲突、审计各环节都有产出，各环节条目数闭合 | `counts` 含 retrieved/unique/duplicates/screened/include/exclude/pending；`audit.closure` 为 true |
| 结果可核验性 | 第三人能独立复跑同一批题录 | `queries[]` 有 db/raw/hits/retrieved_at；`dedup[].basis`；每条 `evidence_locator`；`audit.json`；`--check` 复算全部 |
| 质量增益 | 相比未加载 Skill 提升纳排准确率与双人一致率，证据覆盖率提高 | `metrics.kappa_A_B`、`criteria_traceability`、`evidence_rate`；无金标准时 `metrics.note` 说明不声称准确率 |
| 效率增益 | 减少人工逐条核对量、冲突解决时间、去重返工 | `metrics.human_review_load` = (pending + conflicts)/screened；`records_per_second` |
| 新增能力 | 标准版本管理与回溯重判、理由码体系、分歧自动分类、审计链生成 | `criteria.version` + SHA-256 指纹；`references/criteria-codes.md`；`conflict_type`；`audit.json` |
| 方法改进 | 去重、纳排、冲突仲裁、审计方法有实质改进 | 去重阈值和防误并记录；A/B 规则配置披露；固定仲裁优先级；计数闭合 |
| 创新证据 | 证明方法边界与价值 | `method_disclosure` 说明双规则不是人类标注者；`limitations` 说明有限快照不可估全局召回 |
| 可靠易用 | 正确触发、可按说明完成一次筛选 | `scripts/main.py` 一键运行；`--help`；`--check` 自检；本 SKILL 步骤清晰 |
| 运行稳定性 | 同一输入重复运行输出同口径 | 确定性流程，无随机、无时钟决策；`verification_report.json` 可比较 |
| 异常处理 | 对待 DOI 缺失、摘要为空、编码乱吗、格式不一致、标准冲突、双标注僵持等 | 第 5 节异常表；`errors`/`degradations`/`pending_human` 真实填充 |
| 生态贡献 | 协议模板、标准表、理由码字典、配置、示例、边界维护信息齐全 | `references/` 下 protocol、code dictionary、schema、example；CSV 导出可复用 |

## 7. 自检清单（提交前逐项检查）

- [ ] 已真实读取 `/input/case.json` 与 `/input/task.md`；没有靠文件名猜测内容。
- [ ] 已用适用工具解析所有材料；解析失败或限制已记录在 `errors` / `degradations`。
- [ ] 已运行 `python3 scripts/main.py -i /input -o /app/output`，基线产物存在且未被删除。
- [ ] `result.json` 包含原 `output_contract` 全部字段（键名不变）和 `case_id`。
- [ ] `result.json` 包含 `status`（合法枚举值）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- [ ] `candidates.csv`、`screening_labels.csv`、`arbitration.csv`、`query_log.json`、`dedup_log.json`、`audit.json` 全部存在。
- [ ] 每条 include/exclude/unresolved 记录都有理由码、证据引用和定位符；证据引文逐字来自原文。
- [ ] 去重合并与移除有 `dedup_log.json` 记录依据；未合并的模糊配对已在 `dedup_log` 中标记。
- [ ] 冲突仲裁结论按 `references/criteria-codes.md` §4 优先级执行；僵持者进入 `pending_human`。
- [ ] 审计等式成立：`retrieved = unique + duplicates`；`screened = include + exclude + pending`。
- [ ] 候选文献与纳入标签一致；`candidates.csv` 行数等于 includes 数（或 plus unresolved 视字段定义）。
- [ ] 已运行 `python3 scripts/main.py --check -i /input -o /app/output`；`verification_report.json` 存在；无严重失败或失败已记录。
- [ ] 所有可编辑产物都有真实渲染预览；缺失预览已在 `degradations` 说明。
- [ ] 没有编造科学数据、文献、引用、分数、白板；不确定项已标 `pending_human`。
- [ ] 最终命令和流程可复现；退出码 0。
- [ ] `GITHUB_URL.txt` 是否在提交根目录不属本 Skill 运行范围，但你若在 `/input` 看到它可忽略；不要把它当作文献来源。

## 8. 输出契约字段与制品

`result.json` 必须包含（除原 `output_contract` 字段外）：

- `case_id`
- `status`：`ok` | `partial` | `insufficient_evidence` | `input_error`
- `sources`：实际读取的材料路径与简要说明
- `uncertainty`：未决边界、缺失元数据、低置信度等
- `pending_human`：需要研究者确认的记录/事项
- `errors`：解析错误、契约缺失、材料无法处理等
- `degradations`：降级处理说明（如编码修复、OCR 不确定性、预览缺失）
- `changes`：脚本输出后 Agent 核验/修改记录
- `runtime`：执行时间、请求数、版本信息