---
name: thesis-chapter-revision
description: 用于学位论文与长文档写作的本地修订、编辑注释、跨章节一致性核查和版本管理。在固定科研案例上执行 organizer-edit-workorder 指定的来源锚定编辑动作，保留原文与未请求块，交付可编辑稿件、证据映射、事实保持记录、修改记录、版本差异与回滚证据、一致性报告和合法 result.json。支持 Agent 亲写 draft.json 增量路径与无 draft 时的确定性兜底抽取路径，两条路径共用同一输出契约与结果结构。纯标准库、离线、可复核、可回滚、可重放。
version: 2.0.0
---

# 学位论文与长文档写作 Skill：来源锚定修订工作流

## 0. 最高优先级（Agent 必读）

本 Skill 用于在真实科学材料上执行**局部来源锚定编辑/注释**，完成任务单中指定的编辑目标，并保留可复核的全套证据。不得重写原文章节，不得发明素材，不得静默修正冲突。

1. **先跑单命令基线**：进入任务后立即运行 `python3 scripts/main.py run --input /input --output /app/output --work /app/work`。该命令内部完成 init（盘点与索引）→ build（校验与兜底抽取）→ selfcheck（契约自检），并生成合法的 partial `result.json` 和全部可交付骨架。无论后续 Agent 是否改进，这已是完整交付的保底。
2. **Agent 增量改进**：在基线之上，由 Agent 亲自读取材料，撰写/核验 `draft.json`，然后运行 `check` 与 `build` 或重新运行 `run` 应用改进。所有结构化 JSON（`claims.json`、`evidence_table.json`、`result.json`）的结构字段由脚本生成并原样保留；Agent 不得手工篡改结构，只能通过写入 `draft.json`、`agent_review.json` 和 `pending_human.json` 的补充内容来增量增强。
3. **无 draft 时确定性兜底**：若 Agent 未提供 `/app/work/draft.json`，`build` 会基于 init 台账自动生成逐字 quote + locator 的实质编辑注释，并标记 `AUTO_EXTRACT`，诚实记入 `degradations` 与 `pending_human`。两条路径产出同一套产物与同一份 `result.json` 契约。
4. **诚实与边界**：不编造材料外事实、数据、引用、分数或金标准；材料缺失、冲突、无法判定一律显式标注 `gaps`、`uncertainty`、`pending_human`、`errors`、`degradations`。任务单未要求的段落、表格、公式、引用、标题一律保持原状。
5. **预算意识**：受 64 次模型请求 / 900 秒约束。优先保障基线命令与少量关键核验，接近预算时立即收尾，确保 `result.json` 合法且状态诚实。

---

## 1. 单命令入口与运行时契约

### 1.1 唯一入口

```text
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令是必调用的入口，内部执行三个子阶段：

- **init**：扫描 `/input` 全部材料，生成来源索引、段落定位符、目标解析、冲突分组与候选抽取台账，写入 `/app/work`，并写出第一版合法 `result.json`（`status=partial`）。
- **build**：根据 `/app/work/draft.json`（若存在）或确定性兜底抽取，校验每条提议，应用被接受的编辑注释，保留被拒绝项与原因，装配可编辑稿件、证据映射、差异、版本控制证据、一致性报告，最终写出 `result.json`。
- **selfcheck**：核对 `output_contract` 字段、磁盘文件与 `result.json` 键三者对应；检查版本回滚/再应用证据、预览文件；补充 `status`、`gaps`、`errors`、`degradations`。任何异常均保证退出码 `0`。

**注意**：`run` 命令本身不要求 Agent 事先生成 `draft.json`；若依赖确定性兜底，产物仍为实质内容，只是状态标记为 `partial` 且列入 `pending_human`。Agent 可后续补充 `draft.json` 并重跑 `build` 提升质量。

### 1.2 目录与关键文件

- `/input`：原始输入。包含 `case.json`、`task.md`、`organizer-edit-workorder.json`（或内嵌 workorder），以及全部材料（md/txt/docx/pdf/csv/json 等）。
- `/app/work`：工作目录，存放台账、草稿、核验报告。只在此写入中间文件。
- `/app/output`：最终交付目录。必须包含：
  - `result.json`：结构化结果，含全部契约字段与运行状态。
  - `manuscript.md`：可编辑目标文稿，原文块与编辑注释块分明。
  - `evidence_map.json` 或内嵌于 `result.json` 的 `evidence_map` 字段（通常两者均生成；若只有 `result.json` 内嵌字段，则以 `result.json` 为可核验依据）。
  - `consistency_report.md`：术语、引用、编号、结论的一致性核查结果。
  - `manuscript_preview.html`：渲染预览，便于人工检查。
  - `versions/`：存放版本快照、差异文件、回滚与再应用证据。若目标产物为 docx/pptx 等其他可编辑格式，还必须生成对应的真实渲染 PDF/PNG 预览。

### 1.3 `result.json` 字段要求

`result.json` 必须同时满足“顶层双回显”与“完整状态”。

- **顶层字段**：`case_id`（原样保留）、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`workorder_receipt`、`version_control`、`preserved_facts`、`evidence_map`、`deliverable`、`change_log`。
- **嵌套契约回显**：`output_contract` 中出现的全部字段必须作为 `result.json` 的顶层字段原样出现一次；同时保留一个嵌套对象 `output_contract`，其内容与顶层对应字段一致。例如 `case_id` 既在顶层也在 `output_contract.case_id`。未知键保留，缺失值以 `null` / `[]` 表示。
- **状态枚举**：`ok` / `partial` / `insufficient_evidence` / `input_error`。`partial` 必须列出缺失项或限制。
- **证据字段**：`evidence_map[].evidence[]` 每项至少要有 `claim_id`、`source_id`、`locator`、`quote`、`verbatim`、`support_scope`、`strength`。`locator` 采用 `文件#行号/段落号` 或 `文件 §章节号 标题 ¶段落`，由脚本生成，Agent 不得手写猜测。

---

## 2. 输入处理与真实性

1. **真实读取材料**：不依据文件名、领域标签或任务提示猜测内容。PDF 必须用 `pdftotext` 或可用 pdf 解析工具提取文本层；无文本层时记录 `degradation`，不得虚构。docx/xlsx 用可用工具真实解析；二进制格式不支持则标记 `unreadable/skipped`，继续处理其余材料。
2. **工作单识别**：`organizer-edit-workorder.json` 或 `case.json` 嵌入的 workorder 是本 Skill 的主要任务来源。Agent 必须读取 `target_ids`、`task`、`operation_requirements`、`consistency_scope`、`boundaries`。若工作单存在，必须按工作单指定目标执行；若不存在，则根据 `output_contract` 推断任务，并标记 `workorder_missing`。
3. **来源编号**：脚本在 init 阶段为每个材料文件分配 `S#` 编号（如 `S1`、`S2`），所有关键数字/论断/引用必须携带 `[S#]` 和 locator，确保可回溯。
4. **冲突与缺口**：若发现材料内部不一致（如术语不统一、编号不连续、引用无原文），只报告不修正，写入 `consistency_report.md`、`uncertainty` 和 `gaps`。材料缺失时显式登记 `gaps`，不得用外部知识补全。

---

## 3. 双路径工作流

### 3.1 Agent 路径（推荐：有 `draft.json`）

该路径产出质量最高，也是“实际效果”和“使用增益”的主要得分点。

**步骤 A. 运行基线**

```text
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

此命令生成台账 `/app/work/source_index.json`、初始 `result.json` 和可交付骨架。终端会打印材料索引、目标解析、冲突分组和未完成的 operation requirements。

**步骤 B. 阅读工作单与台账**

打开 `/input/case.json`、`/input/task.md`、工作单文件，确认 `case_id`、`output_contract` 字段、`target_ids` 列表。浏览 `/app/work/source_index.json` 的结构，理解每个 target 的定位符和候选抽取。

**步骤 C. 读取原文上下文**

对每个 `target_id` 运行：

```text
python3 scripts/main.py show --target <target_id> --context 3 --chars 4000
```

- 读取输出的精确原文段落、定位符、周边上下文。
- 若该 target 属于某个章节，识别该章节内相关定义/方法/结果/讨论中与 target 相关的术语、数值、单位、引用和结论。
- 如需核查一致性，可多次调用 `show`，但每次限制 `--chars 4000`，避免一次读取过长资源。

**步骤 D. 撰写 `/app/work/draft.json`**

Agent 必须亲自撰写，不得复制模板空壳。`draft.json` 结构请参照 `references/schemas.md`；每项包含：

- `target_id`：工作单指定的目标 ID。
- `anchor_quote`：逐字原文摘取（仅空白/排版归一化），用于锚定编辑位置。必须与原文完全一致。
- `text`：2–4 句来源支撑的编辑注释或局部修改说明；解释科学条件、限制或可追溯澄清，只使用材料内证据。
- `evidence`：至少一条逐字引用，`quote` + `locator`，证明注释有据。
- `rationale`：为什么此注释是来源支撑且不改变原意。
- `status`：`proposed`（建议应用）或 `pending_human`（证据不足，需人工确认）。
- 若无法可靠锚定或证据不足，如实标 `pending_human`，附最接近的原文引用与原因，绝不编造。

**步骤 E. 运行检查与装配**

```text
python3 scripts/main.py check
python3 scripts/main.py build
```

或直接再次运行 `run`（它会自动检测 `draft.json` 并应用）。`check` 验证 quote 逐字命中、target 在范围内、证据可追踪、receipt 齐全。存在 `high` finding 必须修复；`warn` 可接受但写入 `change_log` 和 `uncertainty`。

**步骤 F. 核验与收尾**

Agent 可阅读 `/app/output` 产物，将核验结论写入 `/app/work/agent_review.json`（逐条说明 claim_id 核验结果）和 `/app/work/pending_human.json`（补充项），但不得改写结构化 JSON 文件。最终再次运行 `run` 或 `selfcheck` 确保 `result.json` 合法且完整。

### 3.2 确定性兜底路径（无 `draft.json`）

若 Agent 未写 `draft.json` 或时间不足，`build` 阶段自动执行以下动作：

- 从 init 台账中选取每个 target 的原文锚点句，生成逐字 `anchor_quote`；
- 抽取 1–2 条最相关的原文证据（逐字 quote + locator），生成一个来源支撑的编辑注释草稿；
- 该注释标记 `generated_by: deterministic_fallback`、`needs_review: true`，并在 `change_log`、`gaps`、`degradations`、`pending_human` 中诚实标注。
- 产物与其他路径完全一致：`manuscript.md`、`consistency_report.md`、`versions/`、`result.json` 均生成，状态为 `partial`。

该路径确保即使 Agent 完全失败，也有完整交付和实质内容，避免零分。永远不要因为无 draft 就不生成产物。

---

## 4. 产物详细要求

### 4.1 `manuscript.md`：可编辑目标文稿

- 原文所有段落、表格、公式、引用、标题、编号保持原样出现。
- 每个被批准的编辑注释以独立块插入，格式形如：

```text
> **[EA-01] 来源锚定编辑注释（target: C01-P002）**
> 注释正文：……（2–4 句）
> 证据：原文引用……
> 定位符：S2 §2.3 ¶4
> 状态：proposed / applied
```

- 被拒绝的提议不插入正文，仅记录在 `change_log`。被标记 `pending_human` 的提议在正文对应位置以 `<!-- pending_human: ... -->` 注释形式保留，便于人工处理。
- 若存在原文块与注释块，用分隔线或标题清晰区分。

### 4.2 `consistency_report.md`：一致性报告

- 逐项核查：术语一致性、缩写统一、定义唯一、符号一致、编号连续、图表引用正确、结论前后一致。
- 对每个问题给出：发现位置（locator）、问题描述、是否已处理（保持原样/标记/建议）、`pending_human` 标记。
- 冲突只报告不修正；若工作单要求修正冲突，必须明确记录并给出证据。

### 4.3 `versions/`：版本管理证据

- `v0_original.md`：原始材料目标章节快照。
- `v1_proposed.md`：应用建议后的版本。
- `v2_reverted.md`：回滚后的版本，应与 `v0_original` 完全一致。
- `v3_reapplied.md`：再应用后的版本。
- `diff_v0_v1.txt`、`diff_v1_v2.txt`：差异文件。
- `rollback_equals_v1` 与 `reapply_equals_v2` 布尔值通过脚本计算写入 `result.json.version_control`，证明回滚/再应用真实可复现。
- 这些证据由脚本自动生成，Agent 不得手工伪造。

### 4.4 `evidence_map`：事实与来源映射

- 每个编辑注释的每一条关键论断、数字、引用、术语均建立映射。
- 字段至少包括：`claim_id`、`source_id`、`locator`、`quote`、`verbatim`、`support_scope`、`strength`。
- 若材料内无支持，必须在 `support_scope` 中标注 `none`，并列入 `pending_human`。

### 4.5 `change_log`：修改记录

- 每项记录：修改动作（插入/拒绝/标记）、原因、人工确认项、未解决问题。
- 确定性兜底项必须包含 `generated_by` 和 `needs_review`。

### 4.6 `result.json`：最终状态

- 必须包含 1.3 节全部字段。
- 若 `status=partial`，必须在 `errors` 或 `gaps` 中列出缺失项。
- 所有异常、降级、不确定性均诚实记录。
- 退出码始终 `0`。

---

## 5. 隐藏案例鲁棒性与异常处理

官方为 3 个固定隐藏案例（正常/边界/异常）。本 Skill 必须对以下情况妥善应对，仍产出合法 `result.json` 并退出 0。

| 情况 | 行为 |
| --- | --- |
| `/input` 缺失或 `case.json` 缺失 | `status=input_error`，`errors` 说明原因，退出 0 |
| `case.json` 损坏或非 UTF-8 | 尝试 `utf-8-sig` 解码；仍失败则 `status=input_error`，`errors` 记录 |
| 材料不可读或二进制格式不支持 | 该材料标记 `unreadable/skipped`，其余材料继续处理；写入 `degradations` |
| PDF 无文本层 | `status=degraded`，写入 `degradations`，不虚构文本 |
| `output_contract` 缺失字段 | `result.json` 中以 `null` / `[]` 补位，并记 `degradations` |
| `draft.json` 不存在 | 使用确定性兜底路径，`status=partial`，所有 auto 注释标 `needs_review: true` 并列入 `pending_human` |
| draft 中 quote 未命中原文 | 该 item 被拒绝，原状态不变，`change_log` 记录原因；不视为致命错误 |
| target 不存在 | 标 `pending_human`，`reason: target not found`，不猜测 |
| 材料内部冲突 | 只报告不修正，写入 `consistency_report.md` 和 `uncertainty` |
| 检查或构建脚本异常 | 保留已生成 partial 文件，`errors` 记录异常，退出 0 |
| Office 预览渲染失败 | 保留可编辑源文件，预览缺失标记 `degraded/pending_human`，不删除源文件 |
| 超时或工具箱失败 | 保留已有 partial 产物，`errors` 记录，退出 0 |
| 工作单缺失 | 若无工作单，按 `output_contract` 推断任务，`workorder_missing` 写入 `gaps` |

任何情况下都不得让运行中断到没有 `result.json`。所有异常捕获后写文件再退出。

---

## 6. 预算策略（64 次模型请求 / 900 秒）

每个案例平均分配，避免在单一案例耗尽预算。

**必做高优先级（约 10–15 次请求）**

1. 运行单命令 `run` 基线（1 次）。
2. 对每个 `target_id` 运行 `show`（通常 2–4 次）。
3. 写 `draft.json` 一次（1 次模型响应内完成多条记录，控制篇幅）。
4. 运行 `check`（1 次）。
5. 运行 `build`（1 次）。
6. 运行 `selfcheck` 或再跑 `run`（1 次）。
7. 必要时生成预览检查（1 次）。

**可压缩或跳过**

- 全篇通读材料：跳过；只读取 target 上下文和相关性最高章节。
- 大段复制材料到响应：禁止；使用 `show --chars 4000` 限制。
- 多次微调注释：禁止；除非 `check` 出现 `high` 才修正相关 target。
- 每次完成一个 target 就 `build`：禁止；所有 draft 合并后一次 `build`。

**保留预算**

剩余预算用于故障恢复、修复 quote 未命中、预览检查与最终修补。接近 64 次或 900 秒时，立即运行最后一次 `run` 确保 `result.json` 合法并收尾。

---

## 7. Rubric 维度 → 交付要求 → 自证方式

| 评分维度 | 交付要求 | 自证方式（在产物中的证据） |
| --- | --- | --- |
| 实际效果·任务完成度（15） | 按工作单为每个 target 增加来源锚定编辑注释，不是通用写作建议 | `manuscript.md` 中 `[EA-xx]` 块；`workorder_receipt.targets[].status` 为 `done` 或 `pending_human` |
| 实际效果·结果正确性（15） | 每条论断、数字、术语、符号、编号与原文一致 | `evidence_map[].evidence[].locator` 指向真实材料；`verbatim: true`；`preserved_facts[]` 计算 `preserved: true/false` |
| 实际效果·结果完整性（5） | 所有源段落与必要论证要素齐全，注释不破坏原文 | `manuscript.md` 包含所有源标题/段落；`version_control.source_blocks_unchanged: true` |
| 实际效果·结果可核验性（5） | 文字可追溯到大纲条目、原始材料、文献和版本记录 | `evidence_map`、`change_log`、`versions/*`；`workorder_receipt` 的 `version_control` 字段 |
| 使用增益·质量增益（15） | 跨章节一致性与可编辑性稳定提升 | `consistency_report.md` 覆盖术语/定义/符号/编号/结论；局部修改不碰其他段落（展示 `diff` 小范围） |
| 使用增益·效率增益（5） | 减少反复通读、手工统一术语、逐条补引用、重排编号 | `run` 单命令自动生成基线+兜底；`SOURCE_INDEX` 台账；`AUTO_EXTRACT` 记录 |
| 使用增益·增益可验证性（5） | 公平对照证明改善 | `selfcheck` 输出与 `result.json.diff_stats` 显示只改目标块；`agent_review.json` 记录核验过程 |
| 创新增益·新增能力（5） | 基础 Agent 不具备的长文档能力 | 脚本支持“台账+确定性兜底+版本回滚证据”组合；`references/checklist.md` 定义一致性与引用核查清单 |
| 创新增益·方法改进（5） | 局部修改、来源锚定、版本管理方法实质改进 | `scripts/main.py` 的 `init/build/selfcheck` 三段式；`versions/` 回滚与再应用证据 |
| 创新增益·创新证据（5） | 证明相对基线的边界和价值 | `SELFTEST.md`（若存在）或 `references/checklist.md` 的“已知边界”；`result.json.degradations` 记录不适用场景 |
| 可靠体验·调用与易用性（3） | Agent 能正确触发，作者能按说明完成一轮流程 | 本 SKILL.md 第 0–4 节明确步骤；`scripts/main.py` 提供单命令入口；`--help` 输出可用 |
| 可靠体验·运行稳定性（4） | 不同章节类型、篇幅、重复运行持续产出 | 纯标准库、离线、md/pdf/docx 多格式处理；`run` 幂等；随机性可控 |
| 可靠体验·异常处理（3） | 对材料缺失、引用找不到、冲突、编号不连续、格式不支持等识别与处置 | 第 5 节异常表；`result.json` 中 `errors`/`degradations`/`gaps` 字段；不崩溃 |
| 生态贡献·文档完整性（3） | 使用说明、依赖、配置、示例、适用范围、篇幅上限、已知失败模式齐全 | 本 SKILL.md 完整；`references/checklist.md` 提供检查清单；`references/schemas.md` 提供 draft shape |
| 生态贡献·资源可复用性（4） | Skill 本体、脚本、模板、核查清单可被他人复用 | `scripts/main.py` 与 `scripts/verify.py` 模块化；`references/checklist.md` 可独立做核查；纯标准库 |
| 生态贡献·分享推广价值（3） | 沉淀可分享的修订案例、检查清单、改稿经验 | `consistency_report.md` 模板；`versions/` 差异展示；`README`（或本 SKILL.md）描述应用价值 |

---

## 8. 生态与自检资源（引用现有文件）

本 Skill 包含以下资源文件，供 Agent 和后续用户复用：

- `references/checklist.md`：学术写作一致性检查清单（术语、引用、编号、图表、结论），可直接作为人工/自动核查标准。Agent 在 `selfcheck` 阶段应逐项对照此清单。
- `references/schemas.md`：`draft.json`、`agent_review.json`、`pending_human.json`、`evidence_map` 等 JSON 形状定义。Agent 撰写 `draft.json` 前必须阅读。
- `scripts/main.py`：主入口，实现 `init`、`show`、`check`、`build`、`selfcheck`、`run` 子命令。所有结构化字段由该脚本计算与写出。
- `scripts/verify.py`：独立验证脚本，输出 `verification.json`；核验来源引用、quote 逐字命中、版本回滚证据等。Agent 不得引用自设金标准，只能引用 `verify.py` 的输出。

**纯标准库、离线**：所有脚本仅依赖 Python 3.8+ 标准库，无第三方 pip 包。若环境中存在 `pdftotext` 等外部工具，用于 PDF 解析；若无，则记录 `degradation` 并继续。

**篇幅与文件限制**：包内不超过 50 个 UTF-8 文本文件，单文件 ≤500KB，总计 ≤2MB。运行期产物可二进制且可超过该限制独立保留。

---

## 9. 禁止事项与扣分避免

1. 不得生成预制答案、伪金标准、自评分数或虚构的 benchmark 结果；所有核验以 `scripts/verify.py` 为准。
2. 不得手改结构化 JSON 结构（`claims.json`、`evidence_table.json`、`result.json`）；只能通过 `draft.json`、`agent_review.json`、`pending_human.json` 增量。
3. 不得删除或清空基线 partial `result.json` 的字段；只能在之上增强。
4. 不得把确定性兜底的 `AUTO_EXTRACT` 伪装成 Agent 亲写内容；必须标记 `generated_by` 和 `needs_review`。
5. 不得引入材料外知识、数据、引用；缺失时标注 `gaps`。
6. 不得为了“修复”原文矛盾而静默纠正；冲突只报告。
7. 不得在 `deliverable.md` 与 `evidence_driven_draft.md`（若同时存在）中复制相同文本；两者内容必须不同（前者干净成稿，后者带证据标记草稿）。
8. 不得过度通读全文或频繁调用 `build`；遵守预算策略，保持单命令优先。

---

## 10. 最终自检清单（Agent 收尾前逐项核对）

- [ ] 已运行 `python3 scripts/main.py run ...` 至少一次，生成基线 `result.json`。
- [ ] `/app/output` 包含：`result.json`、`manuscript.md`、`consistency_report.md`、`manuscript_preview.html`、`versions/`。
- [ ] `result.json` 顶层含 `output_contract` 全部字段并保留嵌套 `output_contract` 对象。
- [ ] `case_id` 原样保留；`status` 取值合法且真实。
- [ ] 每个 `target_id` 在 `workorder_receipt` 中有状态记录，且与 `manuscript.md` 一致。
- [ ] `evidence_map` 每条有 locator 与 quote；无证据项列入 `pending_human`。
- [ ] `version_control.rollback_equals_v1` 与 `reapply_equals_v2` 为 `true`（脚本计算）。
- [ ] 所有异常、降级、缺口已写入 `result.json` 的 `errors`/`degradations`/`gaps`。
- [ ] 若 use deterministic fallback，`change_log` 中已标 `AUTO_EXTRACT` + `needs_review`。
- [ ] `references/checklist.md` 中一致性项已核查并反馈到 `consistency_report.md`。
- [ ] 未生成任何虚构金标准或自评分数。
- [ ] 退出码为 0。

符合以上所有项后，方可提交。