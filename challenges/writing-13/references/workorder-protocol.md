# workorder 执行协议与七要素落地写法

`organizer_workorder` 是本次评测给出的写作要求，`authority=organizer-workorder-not-funder-policy`，
**不是**真实资助机构通知、政策或资助承诺。全文不得把它当政策引用，也不得据它推断经费额度。

## 1. 字段 → 动作 → 回执

| workorder 字段 | 必须做的动作 | result.json 回执 |
|-|-|-|
| `id` / `version` | 原样存 `output/workorder.json` 留痕 | `workorder_execution.workorder_id` |
| `authority` | 全文只当写作要求 | `authority_honored: true` |
| `purpose` | 影响"研究意义"表述的口径，不写"响应国家政策" | `background` 章节写法 |
| `actual_topic` | 与材料实际领域对照，冲突以材料为准 | `degradations` / `uncertainty` |
| `source_basis.published_paper` | 事实来源标识，进 `sources` | `sources[]` |
| `source_basis.external_authors` | 每个既有结果句尾标"外部作者" | `limits_checks.external_author_marked` |
| `source_basis.*_supplied=false` | 对应缺口写入 `pending_human` | `pending_human[]` |
| `sections[]` | 七节逐节写实质正文，逐节对 `minimum` 自检 | `sections_satisfied` / `section_detail` |
| `draft_size` | 汉字数落区间，不足不注水 | `char_count` / `char_count_in_range` |
| `planning_months` | 所有时间标记 ≤ 上限 | `max_month_found` |
| `planning_unit_cap` | 分项合计 = total ≤ 上限 | `planning_units_total` / `planning_units_in_cap` |
| `planning_unit_meaning` | 全文禁止货币化表述 | `limits_checks.currency_free` |
| `consistency` | G1/G2/G3 各对应工作包+里程碑+指标 | `goals_count` / `matrix_rows` |
| `required_supporting_files[]` | 六件附属产物齐备 | `supporting_files` |
| `scientific_limits[]` | 逐条不得违反（归属/越界/虚构） | `limits_checks` / `checks.issues` |

## 2. 七节 minimum 的可操作解释

**立项依据（≈420 字）**——三段：
1. 既有能力边界：引用源材料 1–2 条带条件的逐字事实（"在 X 条件下达到 Y"）。
2. 边界留下的空缺：把空缺写成可观测的差距，不写成"研究不足"。
3. 为何现在做：说明该差距与本次拟采用路径的关系。禁止政策口号堆叠。

**科学问题（≈260 字）**——1 主问题 + 2–3 子问题，每个写清对象/条件/可观测指标，用"是否/在何种条件下"表述。子问题数量应与目标数一致。

**研究目标（≈220 字）**——G1/G2/G3 各一句：做什么 + 量化口径 + 评估方式 + 时间点。加一句"指标为未来评估计划，不构成结果承诺"。

**研究内容（≈380 字）**——WP1/WP2/WP3 与 G1/G2/G3 一一对应，各写输入→方法→输出→依赖。工作包不得多于目标。

**创新点（≈260 字）**——三条，每条三句：与哪项具体已有工作不同（点名）+ 难在哪里 + 凭什么可行（源材料方法或计划依据）。禁用无据修饰。

**技术路线（≈320 字）**——三阶段（M1–M4 / M5–M8 / M9–M12），各写输入→方法→输出→关键节点；风险与备选指向 `risks.md` 编号。

**研究基础与可行性（≈260 字）**——能力—证据—与本研究关系三段式：
- 能力（做什么）；
- 证据（论文结果标"外部作者已完成"；申请人自有成果标"未提供，待补"）；
- 关系（该能力如何支撑 WP1–WP3）。
平台条件无证据时写"拟依托（待补 PH3）"，不写"已具备"。

## 3. 变体处理

| 变体 | 处理 |
|-|-|
| case.json 无 workorder | 默认七节 / 12 月 / 100 单位；`degradations: workorder_absent_defaults_applied` |
| 只给摘要 | 正文只用摘要可见事实，其余标"待补"，进 `pending_human` |
| 领域标签与材料矛盾 | 以材料为准，在 `draft_boundary.md` 与 `uncertainty` 说明 |
| 无预算/指南信息 | 不补造；PH2 说明缺口 |
| 材料超长 | 只索引前若干单元 + 带数值句子优先，`degradations: input_truncated` |

## 4. 运行顺序（不可颠倒）

1. `skill_main.py init` → 落 partial `result.json`，产出骨架/引文库/模板。
2. agent 写 `proposal.md` 与附属产物（读 `quote_bank.md` 取逐字事实）。
3. `skill_main.py finalize` → 归属回填、规划单位复算、引文核验、审计、覆盖 `result.json`。
4. `verify.py --output <out>` 复核；`counts.critical`/`counts.major` 为 0 才算完成。
