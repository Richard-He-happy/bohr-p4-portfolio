---
name: methods-experiments-writer
description: Assemble a traceable Methods and Experiments section from scattered research materials (config files, training logs, source code, dataset notes, result tables, author drafts). Extracts the six element classes (procedure, setup, parameters, datasets, controls, reproducibility and limitations), tags every clause with an evidence id, reconciles draft numbers against config and log values, and reports material gaps for author confirmation. Use when writing, completing or auditing a methods / experimental-setup / hyperparameter / dataset-split / reproducibility section, or when checking that reported values match the code and logs.
version: 1.9.0
---

# Methods & Experiments Writer（方法与实验章节写作）

**核心用途**：将散乱的科研材料（配置、日志、代码、数据说明、结果表、作者草稿）整理成可溯源、可复核、可复现的“方法与实验”章节，并保留每条事实的来源、修改记录和人工确认项。

**强制角色定位**：本包中的 `scripts/main.py`、`scripts/kit.py`、`references/*` 只是**提取和落盘工具/基线**，不是最终答案。最终交付物必须由你（Harness Agent）亲自打开原始材料、亲自核对数值与来源、亲自撰写/修改/制作；禁止把脚本骨架、模板、中间产物直接当作成品提交。

---

## 1. 适用与不适用场景

**适用**：案例提供科研材料，要求补写、改写、校对或结构化“方法与实验章节”，包括方法步骤、实验设置、参数、数据集与划分、对照实验、可复现性与限制条件等。

**不适用**：纯引言/摘要/讨论写作、无材料支撑的语言润色、仅引用格式整理、或目标产物不是方法与实验类型章节。

---

## 2. 运行时契约（必须逐条落实）

| 项目 | 约定 |
|-|-|
| 输入 | `/input/case.json` 与 `/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。必须真实解析材料内容；不得依据文件名或领域标签猜测/补造数据。 |
| 工作目录 | `/app/work`（中间文件、临时转储可放在这里）。 |
| 最终产物目录 | `/app/output`。所有交付物必须落盘到此目录。 |
| `result.json` | 必须存在，包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。 |
| 可编辑 Office/幻灯片/图形产物 | 必须额外生成真实渲染的 PDF/PNG 预览，并记录在 `result.json.outputs`。 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。必须预算感知，尽早落盘 honest partial。 |
| 诚实性 | `status`、`sources`、`uncertainty`、`changes`、`errors`、`degradations` 必须真实；不确定或材料不足须显式标注 `pending_human` / `limitations`；不得编造数据、引用、分数、DOI、arXiv 等。 |
| 退出码 | 任何情况下最终退出码都应为 `0`，即使 partial/失败也要输出合法 `result.json`。 |
| 脚本入口 | `python3 -B scripts/main.py --input-dir /input --out /app/output`。`--case` 指定单个 case 文件，`--lang {auto,zh,en}` 控制语言。`--help` 输出契约。 |

**关键**：脚本只是第一步基线。Agent 必须亲自读取材料、亲自完成最终成品并覆盖/增强 `result.json`。严禁直接提交脚本原样生成物。

---

## 3. 预算感知执行策略（64 请求 / 900s）

### 必须做（不可跳过）

| 步骤 | 预估请求 | 理由 |
|-|-|-|
| 1. 盘点输入与契约 | 1-2 | 确定任务、材料、输出字段，否则无法对齐 rubric |
| 2. 运行基线脚本 | 1 | 立即落盘合法 partial，保证不会 0 分 |
| 3. 真实解析材料 | 8-12 | 题目核心要求：必须读到真实内容 |
| 4. 构建/核对证据 | 8-10 | 数值与来源逐条对齐 |
| 5. Agent 撰写完整成品 | 15-20 | 六要素齐全、可溯源、可复现 |
| 6. 自检 rubric | 5-8 | 完整性、契约、可核验性 |
| 7. 回填 result.json | 2-3 | 合并 output_contract 全部字段 |

### 可跳过 / 降级

- 若时间低于 200 秒：跳过步骤 6 的深度二次校验，直接以步骤 5 产物为最终版，并在 `uncertainty` 中标注“时间受限”。
- 若材料不足且六要素已尽最大努力：跳过重复提取，将缺失项写入 `pending_human` 后落盘。
- 若某个非六要素的扩展检查（如重复消费大量请求）可延后：先保证六要素齐全，再增量增强。

### 尽早落盘

- **步骤 2 后立即有基线 `result.json` 与 `manuscript.md` 等文件**。若后续失败，这就是 honest partial。
- 任何一步完成后，若检测到时间/请求接近上限，立即将当前状态写入 `/app/output/result.json`，设置 `status=partial`，并列出 `limitations` 与 `pending_human`。

---

## 4. 专属执行流程（编号步骤）

### 步骤 1：盘点输入与输出契约

**输入**：`/input/case.json`、`/input/task.md`、材料目录。

**动作**：
1. 读取 `case.json`，提取 `case_id`、`output_contract`、任务指令、材料清单/路径。
2. 从 `task.md` 确认本题任务说明、体裁、受众、格式约束、必交付字段。
3. 递归扫描 `/input`，按扩展名与 magic bytes 分类材料（PDF、DOCX、CSV/TSV、YAML/JSON/CFG/INI、代码、日志、Markdown/TXT）。记录清单。

**输出**：内部清单 `case_id`、`output_contract` 字段列表、材料文件列表、任务要求要点。

**失败分支**：若 `case.json` 缺失或 JSON 错误，仍从材料与 `task.md` 推断任务；`errors[].stage = case`，状态降级，但继续执行。

---

### 步骤 2：运行基线脚本（作为工具，不作为最终答案）

**输入**：上述盘点结果。

**动作**：
- 执行 `python3 -B scripts/main.py --input-dir /input --out /app/output`（可加 `--case`、`--lang`）。
- 脚本会生成第一版 `result.json` 与基线产物（`manuscript.md`、`parameter_table.csv`、`evidence_map.json`、`change_log.md`、`pending_human.md`）。

**输出**：`/app/output` 下出现基线文件，包含全部标准字段和可能的 `output_contract` 填充。

**失败分支**：
- 若脚本报错/缺失依赖/资源文件缺失，Agent 必须**自己**用可用工具构建最小合法 `result.json`，写入 `/app/output`。
- 最小结果必须包含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`outputs`，以及原 `output_contract` 所有字段（值可为空/原始值）。`errors` 中记录脚本失败原因。

**关键**：基线产物只是暂存。接下来 Agent 必须亲自打开材料并增强。

---

### 步骤 3：真实解析材料内容（Agent 亲自执行）

**输入**：材料清单。

**动作**：
- 使用平台可用解析工具（如 `pdf-text-tool`、`python-docx`、csv 读取、yaml/json 解析等）打开每个材料文件，提取可读文本或结构化字段。
- 不得仅依赖脚本输出；至少对关键材料亲自验证：
  - PDF：抽取文本层，检查可打印字符比例；若不可解码，记录为 degraded。
  - DOCX：提取段落文本、表格。
  - CSV/TSV：读取行列，记录表头。
  - YAML/CFG/INI/JSON：解析为键值对，记录行号。
  - 日志/代码：提取关键参数、命令、种子、版本、评估指标。
- 将提取内容组织为 `{loc, text}` 片段；locator 规则沿用：PDF `p.<n>`，DOCX/MD `para <n>`，YAML/INI/LOG/CODE/TXT `L<n>`，CSV `row <n>`，JSON `/a/b/0`。

**输出**：证据语料（可存入 `/app/work/parsed_corpus.json` 或直接记忆）。

**失败分支**：
- 某文件损坏/无法解析：该文件标记 `degraded`，记录错误类型，继续其余文件。
- PDF 无文本层或可打印字符比例 <62%：标记需 OCR/作者提供文本，写入 `pending_human`。
- 图片、压缩包、`.xlsx` 等无解析能力：标记 `skipped`，记录 unmet need。

---

### 步骤 4：构建/核对证据与六要素覆盖

**输入**：解析语料、基线产物、`output_contract`。

**动作**：
1. 从语料中抽取六要素：
   - 步骤 procedure：步骤标记或代码函数顺序
   - 实验设置 setup：硬件、GPU 数量、精度、框架、版本、环境
   - 参数 parameters：学习率、batch、epochs、weight decay、优化器、调度器等
   - 数据集 datasets：名称、版本、规模、预处理、划分比例、随机方式
   - 对照 controls：基线对象、版本、预算、评价指标、统计方式
   - 可复现与限制 repro/limitations：种子、重复次数、命令、代码版本、失效场景
2. 为每个数字、术语、关键论断建立证据条目：`evidence_id → source_id + locator + verbatim quote`。
3. 将草稿/任务要求中出现的数值与材料比对；若冲突，保留双方 locator，以配置/日志为准，写入 `change_log` 并生成冲突 `C#` 问题。
4. 无法从材料找到来源的数值/事实：绝不写入正文，写入 `pending_human` 作为缺失项。

**输出**：证据表、参数表（更新）、变更日志（更新）、待确认问题（更新）。

**失败分支**：
- 材料太少无法覆盖某要素：该要素留空，写入 `pending_human`，并在 `element_coverage` 中标注。
- 多来源冲突且无法裁决：保留双方，blocking question 标记。

---

### 步骤 5：Agent 亲自撰写/修改完整成品

**输入**：证据表、参数表、变更日志、待确认问题、任务要求的体裁/受众/格式。

**动作**：
- 由 Agent 亲自起草或改写 `manuscript.md`，不以模板生成器直接输出。
- 章节结构至少包含：
  - 概述（不超过材料范围）
  - 数据集描述
  - 方法步骤（有序，可执行：输入、操作、输出、判断条件）
  - 实验设置（训练/验证/测试流程分开，含硬件、软件、种子、重复次数）
  - 超参数表（名称、取值、单位、作用对象、来源 locator）
  - 对照组与指标
  - 可复现清单（代码版本、环境、命令、数据获取方式）
  - 限制条件（落到具体失效场景，避免套话）
  - Appendix A：证据索引 `[E<k>] → 来源+locator+引文`
  - Appendix B：待人工确认项 `Q#` / `C#`
- 每个事实性语句携带 `[E<k>]` 标记。
- 数值必须能在材料中找到引文；否则不写。
- 对任务要求的 `organizer_workorder` / `organizer_edit_workorder` 逐项执行；每项结果写入 `workorder_report`。
- 如果要求可编辑 Office/幻灯片/图形，则用相应库生成可编辑文件，并渲染 PDF/PNG 预览到 `/app/output`。预览文件命名清晰，如 `manuscript_preview.pdf`。

**输出**：最终 `manuscript.md` 及其他可编辑产物 + 预览。

**失败分支**：
- Agent 无法在预算内完成全部：优先完成六要素主章节，将未完成部分写入 `pending_human`，状态设为 `partial`。
- 缺少关键元素（数据集、划分、学习率、batch、epochs）且材料没有：标记 `blocking: true`，不假装补齐。

---

### 步骤 6：自检 rubric 与完整性

**输入**：最终产物、`result.json` 草案。

**动作**：
逐一执行第 7 节自检清单。
检查 `output_contract` 字段是否全部存在于 result；检查磁盘文件与 result 引用的文件是否齐全；检查 quotes 是否 verbatim；检查数字支持；检查证据标记可解析；检查六要素覆盖；检查 gaps 写入 pending_human。

**输出**：`checks` 对象，列出每项 pass/fail；`derived_counts` 更新。

**失败分支**：
- 任一关键检查失败：尝试修复；若无法修复，在 `errors` 中保留失败项，状态设为 `partial`，但不得删除契约字段。
- 若时间少于 60s，停止修复，保留失败记录并落盘。

---

### 步骤 7：回填 `result.json` 并最终落盘

**输入**：所有产物、检查结果、原始 `output_contract`。

**动作**：
1. 深拷贝原 `output_contract`，填充可匹配字段（键名不改；未知键保留原值）。
2. 写入标准字段：`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`outputs`、`manuscript`、`preserved_facts`、`evidence_map`、`change_log`、`parameter_table`、`dataset_summary`、`procedure`、`reproducibility_checklist`、`limitations`、`element_coverage`、`workorder_report`、`checks`、`derived_counts`。
3. 确认 `/app/output` 下文件齐全，`result.json` 可被 JSON 解析。
4. 设置退出码 0。

**输出**：最终合法 `result.json` 与所有交付物。

**失败分支**：若写盘失败，尝试写 `/app/output/result.json`；若仍失败，写 `/app/work/result.json` 作为逃生，并在 stderr 记录。但正常情况下保持退出码 0。

---

## 5. 隐藏案例鲁棒性

| 异常场景 | 降级策略 |
|-|-|
| `case.json` 缺失/非法 | 从 `task.md` 与材料推断任务；`errors[].stage=case`；继续运行。 |
| 材料缺失（清单有但磁盘无） | 记录为显式缺口，写入 `pending_human`；不要静默跳过。 |
| 材料损坏/格式不支持 | 该文件标记 `degraded` 或 `skipped`，记录原因；在 `pending_human` 请求作者提供可读版本。 |
| PDF 无文本层或可打印字符比例低 | 标记 degraded，请求 OCR/作者文本；不调用不存在工具假装提取。 |
| 空输入（无材料/无任务） | `status=insufficient_evidence` 或 `input_error`，`result.json` 仍合法，退出码 0。 |
| 输出契约缺失/为空 | 使用本节标准字段作为默认 schema，并额外保留所有题面要求字段。 |
| 超时/请求耗尽 | 立即将当前 partial 产物写入 `/app/output`，`status=partial`，`errors[].stage=budget`，退出码 0。 |
| 脚本或资源文件缺失 | 由 Agent 手动构建 minimal result，记录缺失包资源，继续按流程处理。 |
| 多材料数值冲突 | 保留双方 locator，正文采用配置/日志值，生成 blocking `C#` 问题，绝不静默选一个。 |

**任何情况下**：最终必须输出合法的 `/app/output/result.json`，且退出码为 0。不允许崩溃或空输出。

---

## 6. Rubric 维度 → 交付要求 → 自证方式对照表

| Rubric 维度 | 交付要求 | 自证方式 |
|-|-|-|
| 实际效果：任务完成度 | 覆盖步骤、设置、参数、数据、对照、复现与限制，产成可执行方法与实验章节 | `manuscript.md` 分区完整；`element_coverage` 报告各要素覆盖；`workorder_report` 对任务项逐条 done/noted |
| 实际效果：结果正确性 | 参数、数据集版本、划分、训练/评测条件与材料一致，不补造 | `parameter_table.csv` 含 locator/quote；`change_log` 记录修正；`checks.numerals_supported_by_materials` pass |
| 实际效果：结果完整性 | 六要素尽量齐全，缺失显式标注 | `checks.six_element_coverage` pass 或缺失项在 `pending_human`；`derived_counts.coverage_rate` |
| 实际效果：结果可核验性 | 每条事实可回溯 | `[E<k>]` 标记可解析；`evidence_map.json` 每个证据有引文；`checks.quotes_verbatim_in_materials` pass |
| 使用增益：质量增益 | 相对无 Skill，数值有来源、冲突被纠正、缺口被追问 | result 中 `checks` 与 `change_log` 展示差异；`pending_human` 列出作者须补的信息 |
| 使用增益：效率增益 | 一条命令产出章节、表格、变更日志、问题清单 | `outputs` 列出所有文件；`runtime` 显示耗时 |
| 使用增益：增益可验证性 | 相同材料/预算下改进可对比 | 保留基线产物与最终产物；`changes` 字段记录增强点；平台对照可追溯 |
| 创新增益：新增能力 | “抽取要素—对齐正文—发现缺口—追问”闭环 | `vocab.json` 驱动提取；`pending_human` 结构化问题；`element_coverage` 缺口准确 |
| 创新增益：方法改进 | 参数对齐、条件校验、缺口追问带来实质性提升 | `checks.numerals_supported_by_materials`、`checks.quotes_verbatim_in_materials`、冲突 `C#` 问题 |
| 创新增益：创新证据 | 证明方案边界与价值 | `examples.md` 提供示范（标记示例），`templates.md` 给出 schema，实际 result 展示运行证据 |
| 可靠体验：调用与易用性 | Agent 在给定材料下能正确触发 | `SKILL.md` 步骤清晰；入口命令明确 |
| 可靠体验：运行稳定性 | 更换论文方向、材料形态、重复运行可稳定产出 | 标准库解析；确定性排序；partial-first 写盘；退出码 0 |
| 可靠体验：异常处理 | 识别并处置材料缺失、配置冲突、参数无来源、版本不明等 | `errors`、`degradations`、`pending_human`、`status` 联合记录 |
| 生态贡献：文档完整性 | 使用说明、依赖、配置、示例、适用边界、维护信息齐全 | 本 SKILL.md 各节；`references/templates.md`；`references/examples.md` |
| 生态贡献：资源可复用性 | 脚本、配置、要素清单模板、参数表模板、追问清单可复用 | `scripts/kit.py`（抽取/组合）、`scripts/main.py`（发现/解析/落盘）、`references/vocab.json`（别名/问题/模板） |
| 生态贡献：分享推广价值 | 沉淀可分享样例、失败模式、实践 | `references/examples.md` 含失败案例与 walkthrough |

---

## 7. 自检清单（提交前逐项检查）

- [ ] `/app/output/result.json` 存在且可被 JSON 解析。
- [ ] `result.json` 包含 `case_id` 和原 `output_contract` 的全部字段（键名不改；未知键保留）。
- [ ] `result.json` 中包含标准字段：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`outputs`、`manuscript`、`preserved_facts`、`evidence_map`、`change_log`、`parameter_table`、`dataset_summary`、`procedure`、`reproducibility_checklist`、`limitations`、`element_coverage`、`workorder_report`、`checks`、`derived_counts`。
- [ ] 所有声明的磁盘产物都在 `/app/output` 下存在且非空。
- [ ] 若要求可编辑 Office/幻灯片/图形，已生成 PDF/PNG 预览并记录在 `outputs`。
- [ ] `manuscript.md` 覆盖六要素：步骤、实验设置、参数、数据集、对照、复现与限制。
- [ ] 每个数字、参数、数据集版本、划分、指标在材料中有对应引文（`[E<k>]`）。若有材料外数字，必须是 `derived_counts` 声明的衍生计数，并在 `uncertainty` 中标记 `kind: derived`。
- [ ] 每条证据 quote 是解析语料的 verbatim 子串。
- [ ] `[E<k>]` 标记均在 `evidence_map.json` 中有条目。
- [ ] 非空 gap（六要素缺失、材料缺口、冲突）已全部写入 `pending_human`；blocking 问题已标识。
- [ ] 材料冲突已记录双方 locator，正文采用来源值，`change_log` 有修正记录。
- [ ] 无编造 DOI/arXiv/文献 ID；若出现，必须能在材料中找到。
- [ ] `checks` 已记录 pass/fail；若有 fail，已在 `errors` 或 `pending_human` 说明。
- [ ] 退出码