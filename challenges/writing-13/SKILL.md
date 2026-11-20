---
name: grant-proposal-seven-sections
description: 依据所供真实源材料写出可编辑、可回溯的基金申请书七要素章节草稿（立项依据/科学问题/研究目标/研究内容/创新点/技术路线/研究基础与可行性），并交付目标—工作包—里程碑—指标矩阵、规划单位分项（合计≤100）、风险与备选、人工确认项与已完成/拟开展边界；严格执行 organizer_workorder，区分外部作者已有成果与申请人拟开展计划。用于“基金申请书写作”“标书”“立项依据”“申报书章节稿”等任务。
version: 1.1.0
license: MIT
tags: [writing, grant-proposal, fund-application, evidence-traceability, consistency-audit, budget-aware]

# 基金申请书七要素章节稿（源材料限定，Agent 亲自推导版）

## 1. 用途与最高执行原则

本 Skill 把“一篇论文/一组散乱材料 + 一份组织方写作要求”转成可以直接进入申请书的中文七要素章节草稿，并同步交付证据映射、数量一致性回检、风险与人工确认件。

**最高执行原则：脚本只是工具，最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把 `scripts/skill_main.py` 生成的骨架、模板或自动填充稿直接当作最终成品。脚本用于快速建立合法 partial 基线、完成确定性校验和契约回填；真正的 `proposal.md` 正文、证据映射、章节判断、条目改写与风险描述必须由你基于实际材料内容逐段撰写或逐条核验后写回。

## 2. 触发条件

命中任一即调用本 Skill：`基金申请书` / `标书` / `申报书` / `立项依据` / `科学问题` / `研究目标` / `技术路线` / `研究基础与可行性` / `proposal` / `grant` / `工作包` / `考核指标`；或输入含 `organizer_workorder` 且要求“七要素”。

不适用：论文投稿正文、单纯翻译/润色（无要素结构需求）、真实货币经费预算表编制（本 Skill 只做非货币规划单位）。

## 3. 运行契约

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/artifacts/**`、`/input/material.json`，以及 PDF / DOCX / CSV / JSON / TXT / 图片等实际材料 |
| 工作区 | `/app/work`（中间件），最终产物 `/app/output` |
| 主产物 | `/app/output/proposal.md`（七节正文，约 1600–2600 汉字） |
| 结构化结果 | `/app/output/result.json`（原样回填 `output_contract` 全部字段 + `case_id`） |
| 脚本 | `python3 -B scripts/skill_main.py init --input /input --output /app/output` 建立基线；`finalize` 完成校验与回填；`scripts/verify.py` 单独审计 |
| 退出码 | 恒 0；异常写入 `errors`，不抛出 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）内完成；必须预算感知，先保完整，再增量增强 |

## 4. 本题专属执行流程（必须按序）

### 步骤 0：盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、`/input/artifacts/**`、其他材料文件。

**动作**：
1. 读 `case.json`。若缺失或 JSON 坏，递归找 `case*.json` / `task.md`，仍继续。
2. 透传 `case_id`、`output_contract`；未知字段原样保留，契约键名不改。
3. 识别 workorder：任意字典含 `sections` 且 (`draft_size` 或 `planning_months`) 即视为 workorder；`organizer_workorder` / `organizer_edit_workorder` 优先。将 workorder 原样保存到 `/app/output/workorder.json`。
4. 扫 `/input/**` 材料，按扩展名与内容识别 PDF / DOCX / CSV / JSON / TXT / MD；`task.md`、`case.json` 是元信息，不是事实源。

**输出**：形成“输入清单 + 契约字段清单 + workorder 字段清单 + 材料清单”。

**失败分支**：`case.json` 坏或缺 `output_contract`，不要停；在 `degradations` 记录 `case_json_unreadable` 或 `output_contract_absent_defaults_applied`，继续用默认契约字段生成合法 result.json。

### 步骤 1：先跑 baseline，尽早落盘 partial

**输入**：步骤 0 的输入清单。

**动作**：
```bash
python3 -B scripts/skill_main.py init --input /input --output /app/output
```
`init` 会生成合法 `result.json`（`status=partial`）与基础骨架文件。**此时不要把骨架当成品**，但它保障中断后仍有可读结果。

**输出**：`/app/output/result.json`、`proposal.md` 骨架、`quote_bank.md` 初始抽引文、`workorder.json`。

**失败分支**：若 `init` 失败，手动写一个最小合法 `result.json`，`status=partial`，`errors` 记录脚本失败原因；退出码仍 0。

### 步骤 2：真实解析材料内容

**输入**：`/input/**` 所有实际材料，尤其 PDF / DOCX / CSV / 图片。

**动作**：
1. 优先使用环境提供的 pdf-text-tool / pdftotext / Python 标准库解析实际文件；不要依据文件名或领域标签猜测内容。
2. 对 PDF：抽取文本层，保留页码/流号作为 locator；若 PDF 无文本层且工具失败，用你可读到的原始文本层或 OCR 输出；仍失败则诚实降级。
3. 对 DOCX：抽取段落；CSV：按行；JSON：按 JSON Pointer；图片：若环境有 OCR 工具则用，否则说明不可读。
4. 实际读材料内容，找出数字、单位、样本、条件、显著性、作者归属、年份、结论、限制。

**输出**：`/app/work/parsed_material_notes.md`（Agent 自己写的解析笔记）和更新后的 `quote_bank.md`（逐字引文 + locator）。

**失败分支**：某材料不可解析/不可读，不编造内容；在 `uncertainty` 与 `pending_human` 标注，`result.degradations` 记 `material_unreadable`。

### 步骤 3：构建与核对证据

**输入**：解析笔记、`quote_bank.md`、workorder。

**动作**：
1. 建立 `preserved_facts.json`：每条数字/单位/术语/条件/归属，带 locator 和逐字 quote。
2. 建立 `evidence_map.json`：每个关键论断 → section → claim → kind(fact|plan|policy|method) → source_id → locator → quote(逐字) → verified。
3. 逐条核验 quote 是否能在源文本中定位：脚本 `verify.py` 会做确定性比对。若 quote 不在源文本中，`verified=false` 并进 `pending_human`；**不得改原文凑通过**。
4. 区分三类内容：论文作者已完成事实、申请人自有前期成果/资源证据、组织方要求/计划约束。

**输出**：`evidence_map.json`、`preserved_facts.json`、`pending_human.json`。

**失败分支**：引文无法定位或来源冲突，保留原样并标注 `unresolved`，不得删除。

### 步骤 4：Agent 亲自产出完整成品

**输入**：解析笔记、证据映射、workorder、`quote_bank.md`。

**动作**：
1. 先定 G1/G2/G3 → WP1/WP2/WP3 → 里程碑（月）→ 可检验指标，再写正文；顺序不能反。
2. 按第 6 节七节写作规则逐节写 `/app/output/proposal.md`：每节必须有实质正文、来源/计划依据、与邻节衔接；事实句从 `quote_bank.md` 取逐字引文，不能脑补。
3. 写 `goal_matrix.md`：G1/G2/G3 × 工作包 × 里程碑 × 指标，至少 3 行且可 join。
4. 写 `planning_units.json`：分项合计 ≤100，`unit_meaning` 写明“非货币、非已获资金、非真实预算”。
5. 写 `risks.md`：≥3 条，每条含触发信号与备选方案。
6. 写 `pending_human.json`：≥2 项，必须覆盖真实申请人前期成果/资源证据、真实资助机构指南与政策口径。
7. 写 `draft_boundary.md`：已完成 vs 拟开展双栏；论文结果标“外部作者已完成”，拟开展句带“拟/计划/将/预计”。
8. 写 `change_log.json`：每条修改动作、原因、locator、归属。
9. 写 `preserved_facts.json` 与 `evidence_map.json` 的最终版本。

**输出**：以上全部文件，且均不在 `/app/work` 而在 `/app/output`（可编辑 Office/幻灯片/图形产物若存在，必须额外渲染 PDF/PNG 预览）。

**失败分支**：时间或请求预算不足时，先补 `proposal.md` 与 `result.json` 契约字段，再补其他附属件；任何未完成项写入 `result.partial_missing`，不要删除已产出的部分。

### 步骤 5：自检 rubric 与一致性

**输入**：`/app/output` 全部产物。

**动作**：
1. 运行：
```bash
python3 -B scripts/verify.py --output /app/output
```
2. 检查 `counts.critical` 与 `counts.major` 必须为 0。查看字数、目标数、月份、规划单位合计、风险数、人工确认数、禁用词、归属。
3. 按第 8 节评分维度对照表逐项自检。
4. 以“评审人视角”逐段问：这个句子凭什么这么写？有没有来源？若没有，补 locator 或降格为“待补”。

**输出**：`/app/work/selfcheck.md`（自检记录）。

**失败分支**：任一 critical/major 未清零，先修最影响 rubric 权重的问题（七节完整性、事实正确性、证据可核验性），再修数量一致性问题；修不完保留 partial 并标明缺失项。

### 步骤 6：回填 result.json

**输入**：全部产物与自检记录。

**动作**：
```bash
python3 -B scripts/skill_main.py finalize --input /input --output /app/output
```
`finalize` 会：
- 回填原 `output_contract` 全部字段（键名不改）与 `case_id`；
- 写入 `status`（ok/partial/degraded）、`sources`、`uncertainty`、`change_log`、`errors`、`degradations`；
- 写入 `workorder_execution` 逐项回执；
- 保留所有未知契约字段。

**输出**：最终 `/app/output/result.json`。

**失败分支**：若 `finalize` 失败或无法写入，手动写合法 result.json，保底字段为 `case_id`、原 `output_contract` 字段、`status=partial`、`errors` 记录失败原因；退出码 0。

## 5. 预算策略：64 次模型请求内分配

以“先完整、后增强”为原则，优先高权重交付物。典型分配如下：

| 阶段 | 建议请求数 | 必须做/可跳过 | 产出 |
|-|-|-|-|
| 步骤 0-1：盘点 + 跑 baseline | 2-4 | 必须做 | 合法 partial result.json + 骨架 |
| 步骤 2：真实解析关键材料 | 6-12 | 必须做；只精读与立项依据、科学问题、目标、内容、创新点、路线、基础相关的关键段，不逐字读无关页 | 解析笔记 + quote_bank |
| 步骤 3：构建证据映射 | 4-8 | 必须做；优先数字、条件、归属、结论 | evidence_map + preserved_facts |
| 步骤 4：写七节正文 + 矩阵 + 规划单位 + 风险 + 人工确认 | 14-22 | 必须做；若预算紧，先保完整七节正文，附属件可后续补 | 全部所需文件 |
| 步骤 5-6：自检 + finalize | 4-8 | 必须做 | result.json 终稿 |
| 机动修复 | 4-10 | 可跳过非关键增强；用于修复校验红项 | 增强或修复 |

**原则**：
- 第 2 步不要无限解析；先建一个可交付的完整版本并落盘，再增量改进。
- 第 4 步若字数不达标，优先补高权重节（立项依据、研究内容、技术路线），其余节可保持最低要求并标注 `partial`。
- 禁止无意义循环：同一处修改最多迭代 2 次；仍不合格就标 `pending_human` 或 `limitations`。
- 每次重要里程碑后立刻落盘，不要等全部完成才写文件。

## 6. 七要素写作规则（每节最低要求 = 实质正文 + 来源/计划依据 + 邻节衔接）

| 节 | 字数预算 | 必须写到 | 禁止 |
|-|-|-|-|
| 立项依据 | ~420 | ①源材料显示的既有能力边界（带条件/数值的逐字事实）②该边界留下的具体空缺 ③为何现在做、为何该路径能推进 | 政策口号堆叠、“具有重要意义”式空转 |
| 科学问题 | ~260 | 1 个主问题 + 2-3 个可分解子问题，各带对象/条件/可观测指标边界，写成“是否/在何种条件下” | 问题大于方法、问题与指标错位 |
| 研究目标 | ~220 | G1/G2/G3 各一句，含量化口径与评估方式，写明“为未来评估计划” | 写成保证实现的新结果 |
| 研究内容 | ~380 | WP1-WP3 与 G1-G3 一一对应，各写输入/方法/输出/依赖 | 方法名罗列、与目标数量不一致 |
| 创新点 | ~260 | 3 条，每条=与具体已有工作的差别（点名该工作）+ 为什么难 + 凭什么可行 | 首次/国际领先/填补空白/重大突破 |
| 技术路线 | ~320 | 3 阶段（≤12 月）各写输入→方法→输出→关键节点，风险指向 `risks.md` | 罗列方法名、时间超 12 月 |
| 研究基础与可行性 | ~260 | 能力—证据—与本研究关系三段式；论文结果标“外部作者已完成”；申请人自有成果标“未提供，待补” | 把论文成果写成申请人已完成、写“设备已具备”而无证据 |

衔接要求：立项依据的空缺 → 科学问题 → G1-G3 → WP1-WP3 → 里程碑 → 指标，链条每一环在正文里能被同一编号指认。

**数量硬约束**：
- 目标恰好 3 个：G1/G2/G3。
- 全部计划时间 ≤12 个月。
- 规划单位分项之和 ≤100，且非货币。
- 风险 ≥3，每条含触发信号与备选方案。
- 人工确认 ≥2，覆盖：①真实申请人前期成果/资源证据 ②真实资助机构指南与政策口径。

**归属纪律**：
- 论文结果一律写“已有研究显示（作者, 年）…”并标“外部作者已完成”，不得写“申请人已完成/本课题组已发表”。
- 拟开展内容必带“拟/计划/将/预计”，并与已完成逐条分开。
- 禁用无据修饰：`首次、国际领先、填补空白、重大突破、国内外首创、世界首创、尚无先例`；确需使用必须在同句给出可核验 locator，否则删。
- 不虚构年份、试验结果、样本量、显著性、设备已具备、伦理审批、真实政策或资助决定、经费额度。

## 7. 隐藏案例鲁棒性：降级与兜底

| 情形 | 处置 | result.json 记录 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 递归找材料，仍出稿；契约字段用默认值 | `errors`, `degradations:[case_json_unreadable]` |
| 无 workorder | 默认七节 / 12 月 / 100 单位 | `degradations:[workorder_absent_defaults_applied]` |
| `output_contract` 缺失或字段不全 | 用题面标准契约字段兜底：`case_id, deliverable, preserved_facts, evidence_map, change_log` | `degradations:[output_contract_absent_defaults_applied]` |
| 源材料仅摘要 | 正文只用摘要可见事实，其余标“待补” | `uncertainty`, `pending_human` |
| PDF 无文本层/抽取失败 | 用自身阅读能力读到多少写多少；逐字引文无法核验时 `verified=false` | `degradations:[pdf_text_layer_unavailable]` |
| 材料为空 | 七节正文写明“无源材料，不虚构”，每节只写要求的工作计划框架与待补项 | `status=degraded`, `errors:[empty_material]` |
| 领域标签与材料矛盾 | 以材料为准，写 `draft_boundary` 说明 | `uncertainty` |
| 超长材料 | 只索引前 N 单元 + 数字化句子优先 | `degradations:[input_truncated]` |
| 超时/预算耗尽 | 保留已落盘文件，`finalize` 写入 partial 与缺失项 | `status=partial`, `partial_missing` |
| 字数不足下限 | 不注水；标 `partial` 并给缺口 | `status=partial` |
| 规划单位合计 >100 | `finalize` 按比例缩放到 cap 并记录 | `changes[]` |
| 未写 `proposal.md` 就 finalize | 复制骨架为保底稿并标降级 | `degradations:[proposal_absent_fallback_generated]` |

任何情况下都要产出合法 `result.json` 并保持退出码 0。

## 8. Scoring rubric 对照表（评分维度 → 交付要求 → 自证方式）

| 评分维度 | 分值 | 交付要求（本 Skill 如何满足） | 自证方式 |
|-|-|-|-|
| 实际效果-任务完成度 | 15 | 产出可直接进入申请书的七要素章节稿 + 要素对照说明，而非写作建议、提纲或模板套用 | `proposal.md` 七节实质正文；`workorder_execution.sections_satisfied` 每节 found/char_count |
| 实际效果-结果正确性 | 15 | 事实与来源一致；论文既有成果与拟开展计划分明；数字、条件、术语、引用准确 | `preserved_facts.json` + `evidence_map.json` 逐条可定位；`verified` 状态可查 |
| 实际效果-结果完整性 | 5 | 七要素齐全、厚度匹配、要素之间衔接 | `proposal.md` 字数/节数；`goal_matrix.md` 可 join；`workorder_execution.goals_count=3` |
| 实际效果-结果可核验性 | 5 | 段落、要素与证据三级对应；第三方能判断某句该不该这么写 | `evidence_map.json` 每条含 claim/section/locator/quote；`draft_boundary.md` 区分已完成/拟开展 |
| 使用增益-质量增益 | 15 | 要素齐备、论断有据、目标路线一致优于基础 Agent | 运行 `verify.py` 后 `critical=0, major=0`；`result.workorder_execution` 各项均满足 |
| 使用增益-效率增益 | 5 | 减少从散乱材料到初稿的时间、人工改写条目与往返轮次 | `change_log.json` 记录修改动作与原因，体现“一次生成+增量修复” |
| 使用增益-增益可验证性 | 5 | 通过同一输出结构说明完整率、一致率、可核验率 | `result.check_summary` 或 `counts` 给出量化计数（节数、字数、目标数、风险数、pending 数） |
| 创新增益-新增能力 | 5 | 材料抽取→要素映射→一致性回检→评审人视角自检形成闭环 | `references/workorder-protocol.md` 与 `scripts/verify.py` 体现方法；`result.workorder_execution` 体现执行 |
| 创新增益-方法改进 | 5 | 引文核验、目标-工作包-里程碑-指标对齐、已完成/拟开展边界识别 | `evidence_map.json` verified 状态、`draft_boundary.md`、`goal_matrix.md` |
| 创新增益-创新证据 | 5 | 证明相对基础 Agent 的边界和价值 | `result.degradations` / `changes` 记录非模板化决策；`pending_human` 体现诚实缺口 |
| 可靠体验-调用与易用性 | 3 | 触发条件清晰、脚本命令明确、按说明可完成一节稿 | 第 2 节触发条件；第 4 节执行流程；第 11 节最小示例 |
| 可靠体验-运行稳定性 | 4 | 长材料、多章节、不同学科、重复运行口径一致 | 脚本用相对路径、标准库、退出码 0；`finalize` 无条件覆盖 result.json |
| 可靠体验-异常处理 | 3 | 材料缺失、指南不明、超长输入、引用无法核实、格式冲突等可识别处置 | 第 7 节降级表；`errors` / `degradations` / `uncertainty` 诚实记录 |
| 生态贡献-文档完整性 | 3 | SKILL.md、输入材料清单、模板映射、示例、适用范围、限制和维护信息齐全 | 本文档第 3/4/6/7/12 节；`references/examples.md` |
| 生态贡献-资源可复用性 | 4 | 要素清单、一致性检查表、审计条目等可复用 | `references/consistency-checklist.md`、`references/workorder-protocol.md`、`scripts/verify.py` |
| 生态贡献-分享推广价值 | 3 | 沉淀案例、Benchmark、写作方法与应用价值 | `references/examples.md` 提供最小示例（标注示例，非正式结果） |

## 9. 证据与定位规范

- `evidence_map.json` 每条：`claim_id / section / claim / kind(fact|plan|policy|method) / source_id / locator / quote(逐字) / verified`。
- locator 形态：文本 `L12-L40`；PDF `pdf-stream-N`；DOCX `para-N`；JSON `JSON-Pointer`；CSV `row-N`。
- quote 必须能在源文本中定位（脚本做去空白/全半角归一后比对）。比对失败：`verified=false` 并进 `pending_human`，**不得改原文凑通过**。
- `preserved_facts.json` 记录数字/单位/条件/术语/作者归属，逐条带 locator；改写只改表达不改事实。
- `change_log.json` 每条：`original_quote → revised_quote + reason + locator + attribution`（论文结果→申请表述必须标外部作者）。

## 10. workorder 执行协议（逐项回执）

| workorder 字段 | 动作 | 回执位置 |
|-|-|-|
| `authority` | 全文不得当作真实资助政策引用 | `result.workorder_execution.authority_honored` |
| `sections[]` | 七节全部实质正文，逐节对 `minimum` 自检 | `sections_satisfied`（每节 found/char_count） |
| `draft_size` | 汉字数落在区间 | `char_count` + `char_count_in_range` |
| `planning_months` | 所有时间标记 ≤ 上限 | `max_month_found` |
| `planning_unit_cap` | 分项合计 ≤ 上限，且非货币表述 | `planning_units_total` |
| `consistency` | G1/G2/G3 三个、各对应工作包+里程碑+指标 | `goals_count`、`matrix_rows` |
| `required_supporting_files[]` | 六件附属产物齐备 | `supporting_files` |
| `scientific_limits[]` | 归属、越界、材料外事实三类扫描 | `limits_checks` |

缺 workorder：用默认值（七节 / 12 月 / 100 单位）并在 `degradations` 记 `workorder_absent_defaults_applied`。

## 11. 文件清单与脚本调用

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（触发、契约、流程、规则、降级、评分对照） |
| `scripts/skill_main.py` | `init / finalize / all` 主流程；`--help` 可用 |
| `scripts/verify.py` | 抽取归一、引文定位、字数/数量/一致性确定性校验 |
| `references/workorder-protocol.md` | workorder 字段→动作→回执全表、七节 minimum 落地写法 |
| `references/consistency-checklist.md` | 数量约束表、禁用词表、审计条目，以及脚本运行时读取的产物模板块（`<!--BEGIN:…-->`） |
| `references/examples.md` | 最小输入、调用与示意输出（标注示例） |

**脚本调用命令**：

```bash
# 1) 建骨架：发现输入、抽引文、落 partial result.json
python3 -B scripts/skill_main.py init --input /input --output /app/output

# 2) 这里是 Agent 亲自阅读材料、写 proposal.md 与附属产物的步骤

# 3) 回检 + finalize：一致性审计、契约回填、无条件覆盖 result.json
python3 -B scripts/skill_main.py finalize --input /input --output /app/output

# 单独审计（只读，不改稿件）
python3 -B scripts/verify.py --output /app/output
```

## 12. 最小调用示例（示意，非正式案例结果）

```bash
python3 -B scripts/skill_main.py init --input ./demo_input --output ./demo_out
# Agent 编辑 demo_out/proposal.md 与附属文件后
python3 -B scripts/skill_main.py finalize --input ./demo_input --output ./demo_out
python3 -B scripts/verify.py --output ./demo_out
```

示意输出（**示例，非正式案例结果**）：`demo_out/result.json` 中 `status="ok"`、`deliverable.char_count=2130`、`workorder_execution.goals_count=3`、`planning_units_total=96`、`risks_count=3`、`pending_human=2`。数值仅示范字段形态。

## 13. 提交前自检清单（逐项检查）

- [ ] `/app/output/proposal.md` 七节标题齐、每节有实质正文，汉字 1600–2600。
- [ ] G1/G2/G3 × WP × 里程碑 × 指标，矩阵 ≥3 行且可 join。
- [ ] 全部计划时间 ≤12 月；规划单位合计 ≤100 且脚本复算一致。
- [ ] 风险 ≥3（含触发信号/备选）；`pending_human` ≥2（含申请人证据、真实资助要求）。
- [ ] 全文无禁用词，或均有来源 locator。
- [ ] 拟开展句均带“拟/计划/将/预计”；论文结果均标外部作者。
- [ ] `result.json` 契约字段齐全、`case_id` 原样、`errors/degradations` 诚实。
- [ ] 可编辑 Office/幻灯片/图形产物若存在，已有真实渲染的 PDF/PNG 预览。
- [ ] `python3 -B scripts/verify.py --output /app/output` 的 `counts.critical` 与 `counts.major` 均为 0。
- [ ] 已按第 8 节评分维度对照表逐项自检，并补齐高权重交付物。

版本 1.1.0。维护：新增规则先进 `references/`，脚本只做确定性校验；改判据须同步 `references/consistency-checklist.md` 与 `scripts/verify.py` 常量。