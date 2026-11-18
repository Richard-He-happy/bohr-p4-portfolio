---
name: grant-proposal-seven-sections
description: 依据所供源材料写出可编辑、可回溯的基金申请书七要素章节草稿（立项依据/科学问题/研究目标/研究内容/创新点/技术路线/研究基础与可行性），并交付目标—工作包—里程碑—指标矩阵、规划单位分项（合计≤100）、风险与备选、人工确认项、已完成/拟开展边界。用于"基金申请书写作""标书""立项依据""申报书章节稿"等任务；严格执行 organizer_workorder 并区分论文既有成果与拟开展计划。
version: 1.0.0
license: MIT
tags: [writing, grant-proposal, fund-application, evidence-traceability, consistency-audit]
---

# 基金申请书七要素章节稿（源材料限定）

## 1. 用途

把「一篇论文 / 一组散乱材料 + 一份组织方写作要求」转成**可以直接进入申请书**的中文七要素章节草稿，并同时给出要素对照说明、证据映射、数量一致性回检结果。

解决四类高频失败：立项依据写成政策口号堆叠；创新点靠"首次/国际领先/填补空白"；目标、内容、路线、指标各说一套；论文既有成果被冒充成申请人前期基础。

本 Skill 只做**写作与回检**，不代替申请人提供真实前期成果、平台条件与真实资助指南；这些缺口一律进 `pending_human.json`。

## 2. 触发条件

命中任一即调用：`基金申请书`/`标书`/`申报书`/`立项依据`/`科学问题`/`研究目标`/`技术路线`/`研究基础与可行性`/`proposal`/`grant`/`工作包`/`考核指标`；或输入含 `organizer_workorder` 且要求"七要素"。
不适用：论文投稿正文（用 manuscript 类流程）、单纯翻译/润色（无要素结构需求）、经费预算表编制（本 Skill 只做非货币规划单位）。

## 3. 运行契约

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/artifacts/**`、`/input/material.json`、PDF/DOCX/CSV/JSON 附件 |
| 工作区 | `/app/work`（中间件），产物 `/app/output` |
| 主产物 | `/app/output/proposal.md`（七节正文，约 1600–2600 汉字） |
| 结构化结果 | `/app/output/result.json`（原样回填 `output_contract` 全部字段 + `case_id`） |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（脚本内用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | 恒 0（异常写入 `errors`，不抛出） |

## 4. 三步调用（必须按序）

```bash
# 1) 建骨架：发现输入、抽引文、落 partial result.json
python3 -B scripts/skill_main.py init --input /input --output /app/output
# 2) 用你的文件写入工具改写 proposal.md 与各附属产物（见第 6 节）
# 3) 回检 + finalize：一致性审计、契约回填、无条件覆盖 result.json
python3 -B scripts/skill_main.py finalize --input /input --output /app/output
```

`init` 后**立即**存在合法 `result.json`（`status=partial`）。任何阶段中断，盘上都有可读结果。
单独审计（只读，不改稿件）：`python3 -B scripts/verify.py --output /app/output`；`counts.critical` 与 `counts.major` 必须为 0。

## 5. 输入发现（语义，不假设键名）

1. 读 `case.json`；缺失则递归找 `case*.json`、`task.md`，仍解析。
2. 透传 `case_id`、`output_contract`（键名不改、未知字段原样保留）。
3. 递归识别 workorder：任意字典含 `sections` + (`draft_size` 或 `planning_months`) → 视为 workorder；`organizer_workorder` / `organizer_edit_workorder` 优先。**原样存 `output/workorder.json` 再动手写正文**。
4. 扫 `/input/**` 材料，按扩展名 + 内容识别（PDF/DOCX/CSV/JSON/TXT/MD）；`task.md`、`case.json` 视为元信息，不作事实源。
5. 材料未给的对象列缺口，不用领域标签脑补（例：题面写"增材制造"，材料里没有碳捕集就绝不写碳捕集）。

## 6. 核心流程（7 步）

1. **抽取**：`init` 生成 `quote_bank.md`（带 locator 的候选逐字引文 + 执行约束）。需要更多引文时读原文件，不编。
2. **建表**：把 workorder 的 `sections / draft_size / planning_months / planning_unit_cap / consistency / required_supporting_files / scientific_limits` 逐字段对照 `result.workorder_execution` 的回执位（第 8 节）。
3. **要素映射**：先定 G1/G2/G3 → WP1/WP2/WP3 → 里程碑（月）→ 可检验指标，再写正文；顺序反了必然"对不上"。
4. **写作**：按第 7 节七节规则与字数预算写 `proposal.md`，事实句从 `quote_bank.md` 取逐字引文。
5. **一致性回检**：`finalize` 会报红项，逐项修掉（字数、目标数、月份、规划单位合计、风险数、人工确认数、禁用词、归属）；也可单独跑 `verify.py`。
6. **评审人视角自检**：以"这句子凭什么这么写"逐段问 3 问（见第 11 节），不合格处补 locator 或降格为"待补"。
7. **finalize**：生成 `result.json`，`workorder_execution` 给逐项回执。

## 7. 七要素写作规则（每节最低要求 = 实质正文 + 依据 + 与邻节衔接）

| 节 | 字数预算 | 必须写到 | 禁止 |
|-|-|-|-|
| 立项依据 | ~420 | ①源材料显示的既有能力边界（带条件/数值的逐字事实）②这条边界留下的具体空缺 ③为何现在做、为何该路径能推进 | 政策口号堆叠、"具有重要意义"式空转 |
| 科学问题 | ~260 | 1 个主问题 + 2–3 个可分解子问题，各带对象/条件/可观测指标边界，写成"是否/在何种条件下" | 问题大于方法、问题与指标错位 |
| 研究目标 | ~220 | G1/G2/G3 各一句，含量化口径与评估方式，写明"为未来评估计划" | 写成保证实现的新结果 |
| 研究内容 | ~380 | WP1–WP3 与 G1–G3 一一对应，各写输入/方法/输出/依赖 | 方法名罗列、与目标数量不一致 |
| 创新点 | ~260 | 3 条，每条 = 与**具体**已有工作的差别（点名该工作）+ 为什么难 + 凭什么可行 | 首次/国际领先/填补空白/重大突破 |
| 技术路线 | ~320 | 3 阶段（≤12 月）各写输入→方法→输出→关键节点，风险指向 `risks.md` | 罗列方法名、时间超 12 月 |
| 研究基础与可行性 | ~260 | 能力—证据—与本研究关系三段式；论文结果标注"外部作者已完成"；申请人自有成果标"未提供，待补" | 把论文成果写成申请人已完成、写"设备已具备"而无证据 |

衔接要求：立项依据的空缺 → 科学问题 → G1–G3 → WP1–WP3 → 里程碑 → 指标，链条上每一环在正文里能被同一编号指认。

## 8. workorder 执行协议（逐项回执）

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

## 9. 数量与一致性硬约束

- 目标**恰好 3 个**，编号 G1/G2/G3；每个目标在 `goal_matrix.md` 出现且能 join 到工作包、里程碑、指标。
- 全部计划时间 ≤ 12 个月；`M1–M4 / M5–M8 / M9–M12` 为推荐切分。
- `planning_units.json` 分项之和 = `total` ≤ 100；`unit_meaning` 必须写明"非货币、非已获资金、非真实预算"。禁止"申请 100 万元"式表述。
- 风险 ≥3，每条含**触发信号**与**备选方案**。
- 人工确认 ≥2，且必须覆盖：①真实申请人前期成果/资源证据 ②真实资助机构指南与政策口径。

## 10. 归属与表述纪律

- 论文结果一律写"已有研究显示（作者, 年）…"并标"外部作者已完成"，不得写"申请人已完成/本课题组已发表"。
- 拟开展内容必带"拟/计划/将/预计"，并与已完成逐条分开（`draft_boundary.md` 双栏）。
- 禁用无据修饰：`首次、国际领先、填补空白、重大突破、国内外首创、世界首创、尚无先例`。确需使用必须在同句给出可核验来源（locator），否则删。
- 不虚构：年份、试验结果、样本量、显著性、设备已具备、伦理审批、真实政策或资助决定、经费额度。

## 11. 证据与定位规范

- `evidence_map.json` 每条：`claim_id / section / claim / kind(fact|plan|policy|method) / source_id / locator / quote(逐字) / verified`。
- locator 形态：文本 `L12-L40`；PDF `pdf-stream-N`；DOCX `para-N`；JSON `JSON-Pointer`；CSV `row-N`。
- quote 必须能在源文本中定位（脚本做去空白/全半角归一后比对）。比对失败：`verified=false` 并进 `pending_human`，**不得改原文凑通过**。
- `preserved_facts.json` 记录数字/单位/条件/术语/作者归属，逐条带 locator；改写只改表达不改事实。
- `change_log.json` 每条：`original_quote → revised_quote + reason + locator + attribution`（论文结果→申请表述必须标外部作者）。

## 12. 异常降级表

| 情形 | 处置 | result 记录 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 递归找材料，仍出稿 | `errors`, `degradations:[case_json_unreadable]` |
| 无 workorder | 默认七节/12 月/100 单位 | `degradations:[workorder_absent_defaults_applied]` |
| 源材料仅摘要 | 正文只用摘要可见事实，其余标"待补" | `uncertainty`, `pending_human` |
| PDF 无文本层/抽取失败 | 用 agent 自身阅读能力补，`quote.verified` 置 false | `degradations:[pdf_text_layer_unavailable]` |
| 领域标签与材料矛盾 | 以材料为准，写 `draft_boundary` 说明 | `uncertainty` |
| 超长材料 | 只索引前 N 单元 + 数字化句子优先 | `degradations:[input_truncated]` |
| 字数不足下限 | 不注水；标 `partial` 并给缺口 | `status=partial` |
| 规划单位合计 >100 | finalize 按比例缩放到 cap 并记录 | `changes[]` |
| 未写 `proposal.md` 就 finalize | 复制骨架为保底稿并标降级 | `degradations:[proposal_absent_fallback_generated]` |

## 13. 自检清单（提交前）

- [ ] `proposal.md` 七节标题齐、每节有实质正文，汉字 1600–2600。
- [ ] G1/G2/G3 × WP × 里程碑 × 指标，矩阵 ≥3 行且可 join。
- [ ] 时间 ≤12 月；规划单位合计 ≤100 且脚本复算一致。
- [ ] 风险 ≥3（含触发信号/备选）；`pending_human` ≥2（含申请人证据、真实资助要求）。
- [ ] 全文无禁用词，或均有来源标注。
- [ ] 拟开展句均带"拟/计划/将"；论文结果均标外部作者。
- [ ] `result.json` 契约字段齐全、`case_id` 原样、`errors/degradations` 诚实。

## 14. 最小调用示例（示意，非正式案例结果）

```bash
python3 -B scripts/skill_main.py init --input ./demo_input --output ./demo_out
# 编辑 demo_out/proposal.md 后
python3 -B scripts/skill_main.py finalize --input ./demo_input --output ./demo_out
python3 -B scripts/verify.py --output ./demo_out
```

示意输出（**示例，非正式案例结果**）：`demo_out/result.json` 中 `status="ok"`、`deliverable.char_count=2130`、`workorder_execution.goals_count=3`、`planning_units_total=96`、`risks_count=3`、`pending_human=2`。数值仅示范字段形态。

## 15. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（触发、契约、流程、规则、降级） |
| `scripts/skill_main.py` | `init / finalize / all` 主流程；`--help` 可用 |
| `scripts/verify.py` | 抽取归一、引文定位、字数/数量/一致性确定性校验 |
| `references/workorder-protocol.md` | workorder 字段→动作→回执全表、七节 minimum 落地写法 |
| `references/consistency-checklist.md` | 数量约束表、禁用词表、审计条目，以及脚本运行时读取的产物模板块（`<!--BEGIN:…-->`） |
| `references/examples.md` | 最小输入、调用与示意输出（标注示例） |

版本 1.0.0。维护：新增规则先进 `references/`，脚本只做确定性校验；改判据须同步 `references/consistency-checklist.md` 与 `verify.py` 常量。
