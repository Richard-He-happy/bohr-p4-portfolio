---
name: grant-proposal-seven-sections
description: "依据所供真实源材料写出可编辑、可回溯的基金申请书七要素章节草稿，覆盖立项依据/科学问题/研究目标/研究内容/创新点/技术路线/研究基础与可行性，并交付目标—工作包—里程碑—指标矩阵、规划单位分项、风险、人工确认件与已完成/拟开展边界；严格执行 organizer_workorder，区分外部作者已有成果与申请人拟开展计划。用于基金申请书写作、标书、立项依据、申报书章节稿等任务。"
version: 1.2.0
license: MIT
tags: [writing, grant-proposal, fund-application, evidence-traceability, consistency-audit, budget-aware]

# 基金申请书七要素章节稿（Agent-first 双路径 + 确定性兜底）

## 1. 用途与最高执行原则

本 Skill 把“实际科研材料 + `case.json` + `task.md` + 组织方写作要求”转成可直接进入申请书的中文七要素章节草稿，并同步交付事实与来源映射、修改记录、一致性与人工确认件。

**最高执行原则**：

1. 实际输入文件、PDF、论文原文是唯一事实依据；不依据文件名、领域标签或模型记忆补造数据。
2. 最终 `proposal.md` 必须是实质正文，不是写作建议、提纲、模板套用或预制答案。
3. 脚本用于确定性抽取、校验、契约回填和兜底；Agent 的职责是读材料、判断、补全和改稿。
4. 无法核实、材料缺失、合同缺口、申请人自有证据缺失，必须诚实写入不确定性或人工确认项，不得编造。

---

## 2. 触发条件

命中任一即调用本 Skill：

`基金申请书` / `标书` / `申报书` / `立项依据` / `科学问题` / `研究目标` / `研究内容` / `创新点` / `技术路线` / `研究基础与可行性` / `proposal` / `grant` / `工作包` / `考核指标`；或输入含 `organizer_workorder` 且要求七要素。

不适用：论文投稿正文、单纯翻译/润色、真实货币经费预算编制。

---

## 3. 运行契约

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/artifacts/**`、`/input/material.json` 及 PDF/DOCX/CSV/JSON/TXT/图片等实际材料 |
| 工作区 | `/app/work`：台账、中间抽取、draft、自检记录 |
| 最终产物 | `/app/output`：全部可交付文件与 `result.json` |
| 主入口 | `python3 -B scripts/skill_main.py all --input /input --output /app/output --work /app/work` |
| 主产物 | `/app/output/proposal.md`：中文七节正文，约 1600–2600 汉字 |
| 结构化结果 | `/app/output/result.json` |
| 退出码 | 恒为 0；任何异常都写入 `errors`/`degradations`，不得抛出 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理），必须预算感知 |

### 单命令全流程

优先只调用一次：

```bash
python3 -B scripts/skill_main.py all --input /input --output /app/output --work /app/work
```

该命令内部应完成：

1. `init`：盘点输入、材料来源编号、候选抽取、冲突分组；
2. `build/check`：校验/兜底抽取/渲染全部产物；
3. `finalize`：回填 `result.json` 契约字段、自检、写状态。

若主命令因旧版脚本参数不支持而失败，Agent 可降级为：

```bash
python3 -B scripts/skill_main.py init --input /input --output /app/output --work /app/work
# Agent 读材料、写 /app/work/draft.json（如需）
python3 -B scripts/skill_main.py finalize --input /input --output /app/output --work /app/work
python3 -B scripts/verify.py --output /app/output
```

任何失败都必须保持退出码 0，并产出合法 `result.json`。

---

## 4. Agent 修改边界

必须遵守：

1. **不得手改结构化产物**：`claims.json`、`evidence_table.json`、`evidence_map.json`、`preserved_facts.json`、`result.json` 的结构键名、claim_id、source_id、locator、quote、strength、support_scope、counts，必须保留脚本输出结构。
2. **Agent 可做**：
   - 真实阅读 `/input` 材料；
   - 核验脚本抽取的 quote/locator/数字是否与原文一致；
   - 写 `/app/work/draft.json`、`/app/output/agent_review.json`、`pending_human.json` 补充项；
   - 亲自撰写或改写 `proposal.md` 等正文交付物；
   - 若发现脚本缺陷，写临时 Python 调用脚本函数重算并覆盖，但不得手工篡改 JSON。
3. **不得自造评分或金标准**：不生成 `golden_standard`、`diff_report`、自设加权分；只引用 `verify.py` 的实际输出。
4. **所有关键数字、术语、引用和论断**，必须能在 `evidence_map.json` 或 `preserved_facts.json` 中找到 locator 与逐字 quote；否则降格为“待补”。

---

## 5. 双路径执行流程

### 5.1 路径 A：Agent 路径（优先）

当预算允许或材料冲突复杂时：

1. 运行 `init`，生成台账：`/app/work/inventory.json`、`source_map.json`、`candidate_quotes.json`、`conflict_groups.json`，并落一份 `status=partial` 的 `result.json`。
2. Agent 读原文字段，尤其论文数字、实验条件、结果、作者归属、限制，以及 `organizer_workorder` 的写作要求。
3. Agent 将判断写入 `/app/work/draft.json`，至少包含：
   - `case_id`
   - `sections`：七节正文或可渲染正文的关键内容块；
   - `goals`：G1/G2/G3；
   - `work_packages`：WP1/WP2/WP3；
   - `milestones`：月份节点；
   - `indicators`：可检验指标；
   - `evidence`：关键论断 → source_id/locator/quote；
   - `boundary`：已完成/拟开展；
   - `pending_human`：材料缺口与人工确认项。
4. 运行 `finalize` 或 `all`，脚本消费 draft、渲染全部产物、自检并回填 `result.json`。
5. 运行 `python3 -B scripts/verify.py --output /app/output`，确保 `counts.critical=0`、`counts.major=0`。

### 5.2 路径 B：无 draft 确定性兜底

当 Agent 未写 `/app/work/draft.json` 时，脚本必须用 `init` 台账确定性抽取生成实质工作稿：

- 从源材料抽逐字 quote；
- 每条 quote 带 `source_id` 与 `文件#行号/段落号` locator；
- 按七要素模板渲染为完整 `proposal.md`；
- 生成 `goal_matrix.md`、`planning_units.json`、`risks.md`、`pending_human.json`、`draft_boundary.md`；
- 在 `result.json` 的 `degradations` 中诚实记录 `auto_extract_fallback`。

两条路径必须产出**同一套产物与同一份 `result.json` 契约**。

---

## 6. 输出产物清单

| 文件 | 必需 | 说明 |
|-|-|-|
| `proposal.md` | 是 | 可编辑、可直接进入申请书的中文七节正文，约 1600–2600 汉字；关键事实带 `[S#; locator]` |
| `evidence_driven_draft.md` | 否/建议 | 带证据标记草稿；若存在，必须与 `proposal.md` 内容不同：前者为证据标记稿，后者为干净成稿 |
| `preserved_facts.json` | 是 | 数字、单位、术语、条件、归属，逐条带 locator 与逐字 quote |
| `evidence_map.json` | 是 | 关键论断 → section → claim → kind → source_id → locator → quote → verified |
| `change_log.json` | 是 | 修改动作、原因、locator、归属、未解决问题 |
| `goal_matrix.md` | 是 | G1/G2/G3 × 工作包 × 里程碑 × 指标，至少 3 行，可 join |
| `planning_units.json` | 是 | 分项合计 ≤100，`unit_meaning` 明确“非货币、非已获资金、非真实预算” |
| `risks.md` | 是 | ≥3 条风险，每条含触发信号与备选方案 |
| `pending_human.json` | 是 | ≥2 项：真实申请人前期成果/资源证据、真实资助机构指南与政策口径 |
| `draft_boundary.md` | 是 | 已完成 vs 拟开展双栏；论文结果标“外部作者已完成”，拟开展句带“拟/计划/将/预计” |
| `quote_bank.md` | 是 | 源材料逐字引文库，每条含 locator |
| `workorder.json` | 是 | workorder 原样保存与逐项执行回执 |
| `agent_review.json` | 建议 | Agent 核验结论：claim_id → verified/rejected/reason |
| `result.json` | 是 | 双回显契约字段与运行状态 |
| PDF/PNG 预览 | 条件必需 | 如产出可编辑 Office/幻灯片/图形产物，必须同时渲染真实 PDF/PNG 预览 |

---

## 7. result.json 契约与双回显

`result.json` 必须同时满足：

1. **顶层**出现契约字段：`case_id`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`；
2. **nested `output_contract`** 中再次出现原样契约字段，键名不变；
3. 额外包含：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`partial_missing`、`workorder_execution`、`counts`。

示例结构（不含正式案例内容）：

```json
{
  "case_id": "C01",
  "status": "ok",
  "deliverable": "proposal.md",
  "preserved_facts": "preserved_facts.json",
  "evidence_map": "evidence_map.json",
  "change_log": "change_log.json",
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "partial_missing": [],
  "workorder_execution": {},
  "counts": {},
  "output_contract": {
    "case_id": "C01",
    "deliverable": "proposal.md",
    "preserved_facts": "preserved_facts.json",
    "evidence_map": "evidence_map.json",
    "change_log": "change_log.json"
  }
}
```

若原 `output_contract` 包含额外字段，必须原样保留并回显，不删除、不重命名。

---

## 8. 七要素写作规则

正文七节合计约 1600–2600 汉字。每节最低要求：实质正文 + 来源/计划依据 + 邻节衔接。禁止只给标题、建议、占位模板。

| 节 | 字数预算 | 必须写到 | 禁止 |
|-|-|-|-|
| 立项依据 | ~420 | ①源材料显示的既有能力边界，带条件、数值与逐字事实；②该边界留下的具体空缺；③为何现在做、为何该路径能推进 | 政策口号堆叠、“具有重要意义”式空转 |
| 科学问题 | ~260 | 1 个主问题 + 2–3 个可分解子问题，各带对象/条件/可观测指标边界，写成“是否/在何种条件下” | 问题大于方法、问题与指标错位 |
| 研究目标 | ~220 | G1/G2/G3 各一句，含量化口径与评估方式，写明“为未来评估计划” | 写成保证实现的新结果 |
| 研究内容 | ~380 | WP1–WP3 与 G1–G3 一一对应，各写输入/方法/输出/依赖 | 方法名罗列、与目标数量不一致 |
| 创新点 | ~260 | 3 条，每条 = 与具体已有工作的差别 + 为什么难 + 凭什么可行 | 首次/国际领先/填补空白/重大突破 |
| 技术路线 | ~320 | 3 阶段，≤12 月，各写输入→方法→输出→关键节点，风险指向 `risks.md` | 罗列方法名、时间超 12 月 |
| 研究基础与可行性 | ~260 | 能力—证据—与本研究关系三段式；论文结果标“外部作者已完成”；申请人自有成果标“未提供，待补” | 把论文成果写成申请人已完成、写“设备已具备”而无证据 |

**数量硬约束**：

- 目标恰好 3 个：G1/G2/G3。
- 工作包恰好 3 个：WP1/WP2/WP3，与目标一一对应。
- 全部计划时间 ≤12 个月。
- 规划单位分项合计 ≤100，且非货币。
- 风险 ≥3 条。
- 人工确认 ≥2 项。

**归属纪律**：

- 论文结果一律写“已有研究显示（作者, 年）…”并标“外部作者已完成”。
- 拟开展内容必带“拟/计划/将/预计”。
- 禁用无据修饰：`首次、国际领先、填补空白、重大突破、国内外首创、世界首创、尚无先例`；确需使用必须在同句给出可核验 locator。
- 不虚构年份、试验结果、样本量、显著性、设备、伦理审批、政策或资助决定、经费额度。

---

## 9. 一致性与工作包对照

先定 G1/G2/G3 → WP1/WP2/WP3 → 里程碑 → 可检验指标，再写正文。

`goal_matrix.md` 至少包含：

| 目标 | 工作包 | 里程碑/月 | 可检验指标 |
|-|-|-|-|
| G1 | WP1 | 月 1–4 | I1 |
| G2 | WP2 | 月 4–8 | I2 |
| G3 | WP3 | 月 8–12 | I3 |

- 每个指标必须与目标直接对应，不另说一套。
- 每个工作包必须明确输入、方法、输出、依赖。
- 全部月份落在 ≤12 月内。

一致性问题属于 `major` 或 `critical`，必须清零后才能 `status=ok`；无法清零则如实标 `partial`。

---

## 10. 证据与定位规范

- `source_id` 形如 `S1`，与 `source_map.json` 对应。
- locator 形态：
  - 文本：`L12-L40`；
  - PDF：`pdf-stream-N` 或 `P2L3`；
  - DOCX：`para-N`；
  - JSON：JSON Pointer；
  - CSV：`row-N`。
- `evidence_map.json` 每条：
  - `claim_id / section / claim / kind(fact|plan|policy|method) / source_id / locator / quote(逐字) / verified`
- quote 必须能定位。脚本验证失败时：`verified=false` 并进 `pending_human`，不得改原文凑通过。
- `preserved_facts.json` 记录数字、单位、条件、术语、作者归属，逐条带 locator。
- `change_log.json` 每条：`original_quote → revised_quote + reason + locator + attribution`；论文结果转申请表述必须标外部作者。

---

## 11. 隐藏案例鲁棒性：正常 / 边界 / 异常

| 输入情形 | 应对 | result.json 记录 |
|-|-|-|
| 正常：材料齐全、workorder 完整 | 走 Agent 路径，完整七节与证据件 | `status=ok` |
| 边界：`case.json` 缺失/坏 JSON | 递归找材料，继续出稿；契约字段用默认值 | `errors`, `degradations:[case_json_unreadable]` |
| 边界：无 workorder | 默认七节 / 12 月 / 100 单位 | `degradations:[workorder_absent_defaults_applied]` |
| 边界：`output_contract` 缺失 | 用题面标准契约字段兜底 | `degradations:[output_contract_absent_defaults_applied]` |
| 边界：仅摘要材料 | 正文只用摘要可见事实，其余标“待补” | `uncertainty`, `pending_human` |
| 边界：PDF 无文本层/抽取失败 | 用可读文本层或 OCR；无法核实逐字引文时 `verified=false` | `degradations:[pdf_text_layer_unavailable]` |
| 边界：超长材料 | 只索引关键段落、数字化句子优先 | `degradations:[input_truncated]` |
| 边界：规划单位合计 >100 | 脚本按比例缩放到 cap 并记录 | `changes[]` |
| 边界：领域标签与材料矛盾 | 以实际材料为准，写 `draft_boundary` 说明 | `uncertainty` |
| 异常：材料为空 | 七节正文写明“无源材料，不虚构”，只写工作计划框架与待补项 | `status=degraded`, `errors:[empty_material]` |
| 异常：引用无法核实 | 保留原样，标 `unresolved`，进入人工确认 | `pending_human` |
| 异常：超时/预算耗尽 | 保留已落盘文件，写 partial 与缺失项 | `status=partial`, `partial_missing` |
| 异常：未写 `proposal.md` 就 finalize | 复制兜底稿并标降级 | `degradations:[proposal_absent_fallback_generated]` |

任何情况下都要产出合法 `result.json`，退出码 0。

---

## 12. 预算策略：64 次模型请求内分配

以“先完整、后增强”为原则。典型分配：

| 阶段 | 建议请求 | 必须/可跳过 | 产出 |
|-|-|-|-|
| 盘点输入 + 跑 init | 2–4 | 必须 | ledger + partial result.json |
| 精读源材料关键段 | 6–12 | 必须；只读与七要素相关的关键段 | 解析笔记 + quote_bank |
| 构建证据映射 | 4–8 | 必须；优先数字、条件、归属、结论 | evidence_map + preserved_facts |
| 写七节正文 + 矩阵 + 规划单位 + 风险 + 人工确认 | 14–22 | 必须；预算紧时先保完整七节正文 | 全部必需文件 |
| 自检 + finalize | 4–8 | 必须 | result.json 终稿 |
| 机动修复 | 4–10 | 可跳过非关键增强 | 修复校验红项 |

**原则**：

- 单命令 + 确定性兜底 = 少请求完成完整交付。
- 不要无限解析；先落一个完整可交付版本，再增量改进。
- 同一处修改最多迭代 2 次；仍不合格就标 `pending_human` 或 `limitations`。
- 每次重要里程碑后立即落盘。

---

## 13. 评分维度对照自检

| 评分维度 | 权重 | 交付证据 |
|-|-|-|
| 实际效果：任务完成度/正确性/完整性/可核验性 | 40 | `proposal.md` 七节实质正文；`evidence_map.json` 逐条可定位；`goal_matrix.md` 可 join；`workorder_execution` |
| 使用增益：质量/效率/可验证性 | 25 | `verify.py` 输出 `critical=0, major=0`；`change_log.json` 显示修改链路；`counts` 量化节数、字数、目标数、风险数、pending 数 |
| 创新增益：新增能力/方法改进/创新证据 | 15 | 抽取→映射→一致性回检→评审人视角自检闭环；`verified` 状态；`draft_boundary.md`；`goal_matrix.md` |
| 可靠体验：调用/稳定/异常 | 10 | 单命令主入口；标准库离线运行；退出码 0；第 11 节鲁棒性表 |
| 生态贡献：文档/资源复用/分享推广 | 10 | `references/workorder-protocol.md`、`references/consistency-checklist.md`、`references/examples.md` |

---

## 14. 最小调用示例

```bash
# 演示：正式案例下把 ./demo_input 换成 /input，./demo_out 换成 /app/output
python3 -B scripts/skill_main.py all --input ./demo_input --output ./demo_out --work ./demo_work
python3 -B scripts/verify.py --output ./demo_out
```

示意输出（**示例，非正式案例结果**）：`demo_out/result.json` 中 `status="ok"`、`deliverable="proposal.md"`、`counts.goals=3`、`counts.work_packages=3`、`counts.planning_units_total≤100`、`counts.risks≥3`、`counts.pending_human≥2`。

---

## 15. 提交前自检清单

- [ ] `/app/output/proposal.md` 七节标题齐，每节有实质正文，汉字 1600–2600。
- [ ] G1/G2/G3 × WP1/WP2/WP3 × 里程碑 × 指标，矩阵 ≥3 行且可 join。
- [ ] 全部计划时间 ≤12 月。
- [ ] 规划单位合计 ≤100，且脚本复算一致，非货币。
- [ ] 风险 ≥3，每条含触发信号与备选方案。
- [ ] `pending_human` ≥2，覆盖申请人证据与真实资助要求。
- [ ] 全文无禁用词，或均有来源 locator。
- [ ] 拟开展句均带“拟/计划/将/预计”；论文结果均标外部作者。
- [ ] `result.json` 契约字段齐全，`case_id` 原样，且顶层与 `output_contract` 双回显。
- [ ] `errors` / `degradations` / `uncertainty` 诚实。
- [ ] 可编辑 Office/幻灯片/图形产物若存在，已有真实渲染 PDF/PNG。
- [ ] `python3 -B scripts/verify.py --output /app/output` 的 `counts.critical=0`、`counts.major=0`。
- [ ] 任何异常下退出码 0，且有合法 `result.json`。