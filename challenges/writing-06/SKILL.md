---
name: paper-structure-logic-review
version: 1.0.0
description: Diagnose the structure and argument logic of a full manuscript and deliver an executable edit plan. Segments the real input file into chapter/paragraph/sentence locators, covers six dimensions (research-question alignment, section structure, argument chain, paragraph relations, duplication, conclusion boundary) with verbatim-quoted findings and move/merge/split/narrow/delete/insert actions. Review only - never rewrites the paper.
license: MIT
tags: [academic-writing, structural-review, argument-mapping, editing-plan]
---

# 论文结构与逻辑优化（结构诊断 Skill）

## 1. 用途与边界

对一篇**完整稿件**做结构诊断，交付作者可直接执行的结构修改方案：每条发现定位到章节/段落/句子，
说明属于哪类结构问题，并给出可执行动作（移到哪、与哪段合并、从哪拆分、哪句论断要收窄）。

**做**：结构级诊断、论证链映射、跨章节冗余检测、结论与数据范围比对、动作清单。
**不做**：整篇改写（题面：full unsolicited rewrites are not required）、语言润色、补写科学内容、
生成文献或数据、判断科学结论本身是否正确。

## 2. 触发条件

用户要求「结构诊断 / 逻辑优化 / 论文架构 / 章节顺序 / 论证链 / 重复内容 / 结论收窄 / 审稿意见里的结构问题」，
或给出完整稿件要求"指出问题在哪一章哪一段、怎么改"时触发。若用户要的是**另一篇改写稿**，
或只需语言润色，则不应触发（会与题面冲突）。

## 3. 运行契约

```bash
python3 -B scripts/main.py --input /input --out /app/output      # 诊断并写全部产物
python3 -B scripts/verify.py --out /app/output --input /input    # 独立复核
```

- 输入 `/input`：`case.json` + `task.md` + 材料（md/txt/docx/pdf/html/csv）。
- 输出 `/app/output`：主产物 + `result.json`。
- 先写 partial `result.json`，最后无条件 finalize 覆盖；**任何异常都被捕获，退出码恒 0**。
- 只用 Python 标准库；不联网；脚本用 `Path(__file__).resolve().parent` 定位资源，不依赖 CWD。
- 纯脚本、0 次模型请求，单次运行 <1s。

## 4. 输入发现（语义识别，不假设键名）

1. `/input/case.json`（缺失则递归找 `case*.json`）→ 原样保留 `case_id` 与 `output_contract`。
2. 语义读取 `task_instruction`、`organizer_workorder`、`organizer_edit_workorder`、`organizer_supplied_scope`、
   `material_version`、`source`；workorder 逐项执行并在 `workorder_receipts` 回报（done / not_applicable /
   declined_by_scope / partial）。
3. `/input/**` 全递归扫描，按扩展名识别；`task.md`/`guide.md` 记为 instruction，不作为稿件。
4. **稿件判定**：所有可解析文本中最长者为主稿件；多个候选写 `pending_human`。
5. 材料未给出的对象（缺提纲、缺参考文献、缺图表、缺附录）明确列缺口，不构造内容。

## 5. 输出契约

| 文件 | 内容 | 关键字段 |
|---|---|---|
| `structural_review.json` | 主结果 | `dimension_coverage`、`findings`、`actions`、`grounding`、`manuscript` |
| `edit_plan.md` | 作者执行清单 | 每条按 P1→P3 排序，含 locator、原文、判断、依据、动作、风险 |
| `outline_after.md` | 建议后结构 | 章节顺序、功能、篇幅占比、结构处置 |
| `argument_map.json` | 论点—论据映射 | `chains[].claim/evidence/status`、`unsupported_chains` |
| `consistency_report.md` | 一致性核验 | 章节占比、引用/图表解析、重复对、截断与降级 |
| `pending_human.json` | 无法判断项 | `items[].kind/detail/needed_action` |
| `result.json` | 平台回执 | 契约字段 + status/sources/uncertainty/errors/degradations/changes/runtime |

`result.json` 顶层另含：`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、
`editable_source`、`export_artifact`（null：本题不要求 PDF）、`content_map`、`compliance_checks`、
`exceptions`、`metrics`、`workorder_receipts`，以及 4 个 JSON 产物的路径。

## 6. 六维度（固定枚举）

| key | 检查什么 | 主要规则 |
|---|---|---|
| `research_question_alignment` | 研究问题/贡献主张是否贯穿、是否与结果一致 | RQ 句缺失、RQ 核心项未进结果/结论、贡献句超范围 |
| `section_structure` | 章节完备性、顺序、篇幅、参考文献章 | 无标题、缺核心章、结果先于方法、参考文献章无条目 |
| `argument_chain` | 论断是否都有论据；引用/图表是否可回溯 | 段内主张句无引用/数值/图表、引用编号无条目、图表无图题 |
| `paragraph_relations` | 段落之间是否有关系、是否混层 | 相邻段词项 Jaccard<0.05 且段首无过渡、同段混"结果+解释" |
| `duplication` | 同义重复、跨章节重复 | 10 词 shingle Jaccard≥0.30、整句逐字重复（≥55 字符） |
| `conclusion_boundary` | 结论是否越出数据范围 | 相关性证据+因果表述、绝对化无限定、结论出现结果未报告数值 |

每维必须输出 `findings` 或 `no_issue_with_evidence`（附"检查了什么、计数多少"的证据）。

## 7. 核心流程

1. 写 partial `result.json` → 2. 发现并解析输入 → 3. 分段成 `C01` / `C01-P002` / `C01-P002-S03` 定位 →
4. 六维度规则扫描（`verify.run`）→ 5. 生成动作（finding→action，固定 operation 枚举）→
6. 写 6 个产物 → 7. 契约回填 + finalize → 退出码 0。

## 8. finding / action schema

```json
finding = {"finding_id":"F01","dimension":"<六类之一>","severity":"high|medium|low",
           "locator":"C03-P002-S01","quote":"<原文逐字>","diagnosis":"...",
           "evidence_for_judgment":"...","confidence":"high|medium|low-medium","action_id":"A01"}
action  = {"action_id":"A01","finding_id":"F01","operation":"move|merge|split|narrow|delete|insert",
           "from_locator":"...","to_locator":"...","expected_effect":"...","risk":"...",
           "priority":"P1|P2|P3","executable":true}
```

约束：`operation` 只能取 6 个枚举值；`from_locator` 与 `expected_effect` 必填；
不得出现"建议加强论证""语言可更简洁"这类不可执行或纯润色条目。

## 9. 证据与定位规范

- **quote 必须是稿件正文的逐字子串**（空白归一化后）。生成前逐条校验，未命中即丢弃并记入
  `errors`（宁缺勿造），`grounding.hit_rate` 恒为 1.0。
- 每条 finding 先有 locator + quote 才允许写 diagnosis；diagnosis 的每个数量断言都写在
  `evidence_for_judgment`（如"段内 2 句，含主张标记 1 句，含引用 0 句"），第三方可回原文复核。
- 不入库：无 quote 的判断、风格偏好（单句成段、长短句）、作者未提供的科学解释。

## 10. 质量规则（rubric → 字段/检查）

| 评分点 | 落地方式 |
|---|---|
| 任务完成度 | 3 件主产物齐备；`edit_plan` 每条可执行；`workorder_receipts` 逐项回报 |
| 结果正确性 | `grounding.hit_rate=1.0`；诊断只由命中 quote 触发；不虚构缺陷（规则未命中即 `no_issue_with_evidence`） |
| 结果完整性 | `dimension_coverage` 六键齐全；每维给 `finding_ids` 或检查证据 |
| 可核验性 | 每条 finding/action 带 locator；`evidence_for_judgment` 给可复算计数 |
| 质量增益 | `metrics.findings/actions/quote_hit_rate` + 六类问题检出，构成同口径对照 |
| 效率增益 | `metrics.estimated_revision_rounds`、`action_ratio_per_finding`（标注估算，非实测） |
| 可验证性 | 复跑入口 `scripts/verify.py`，输出 pass 与计数 |
| 创新 | `argument_map.json`（论点—论据映射）、跨章节 shingle 冗余检测、结论 vs 结果数值范围比对 |
| 可靠性 | 见第 12 节降级表；`status` 取 ok/partial/insufficient_evidence/input_error |
| 生态 | 本文件 + taxonomy（规则与阈值）+ example（调用示例）+ messages（措辞模板可换语言） |

## 11. 冲突与人工确认

以下情况**不下结论**，写入 `pending_human`：稿件疑似截断导致缺章、无参考文献列表、
无研究问题句且稿件过短、多个文本候选无法判断主稿、结论数值可能来自未提供的补充材料。
每条写 `kind` + `detail` + `needed_action`（作者需要补什么）。

## 12. 异常降级表

| 情况 | 处置 | 状态 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续跑，契约字段置 null/[]，记 `errors.case_parse` | ok/partial |
| 无稿件文本（PDF 扫描件） | 不编造内容，列 `no_manuscript` | `input_error` |
| PDF 有文本层 | `pdftotext` 提取（`shutil.which` 探测） | ok |
| PDF 无文本层/无 pdftotext | 记 `errors.pdf`，不中断其他材料 | partial |
| 稿件 <60 词 / 只有提纲 | 诊断为不可行，`pending_human` 说明 | `insufficient_evidence` |
| 稿件末字符非结束标点 | 判疑似截断，缺章节判断降级为待确认 | partial |
| 缺章节 / 无参考文献 / 图表缺图题 | 照常输出 finding（这类正是被考察的结构缺陷） | ok |
| 格式混乱（无空行、编号乱） | 按行切段兜底，仍给出可用定位 | ok |
| 单条规则异常 | 只降级该维度，其他维度照常 | partial |

## 13. 预算与断点

脚本先落盘 partial `result.json`，任何阶段中断都保留合法结果；重复运行幂等（覆盖写）。
不发起模型请求，不联网，900s 预算下可反复重跑。

## 14. 自检清单（提交前）

```bash
python3 -B scripts/main.py --help                                  # 退出码 0
python3 -B scripts/main.py --input /input --out /app/output
python3 -B scripts/verify.py --out /app/output --input /input      # pass=true
```

- [ ] 6 个产物齐备，`result.json` 契约字段齐全、`case_id` 原样
- [ ] `grounding.hit_rate == 1.0`；无 finding 缺 locator/quote
- [ ] 六维度均出现（findings 或 no_issue_with_evidence）
- [ ] 无整篇改写稿产物（`manuscript.md` / `rewrite.md` 不存在）
- [ ] 空输入、坏 JSON 下仍生成合法 partial `result.json` 且退出码 0

## 15. 最小调用示例（示例，非正式案例结果）

见 `references/example.md`：3 段极简稿件 → 示意输出 3 条 finding（论证链 / 重复 / 结论边界），
用来说明接口与产物结构，**不是任何正式案例的结果**。

## 16. 文件清单与维护

```
SKILL.md                        本文件：用途/契约/schema/降级/自检
scripts/main.py   (~19.7KB)     I/O：输入发现、解析、分段、产物与 result.json
scripts/verify.py (~18.1KB)     规则引擎 + 复核：六维度规则、动作、verify()
references/messages.json        措辞模板与正则（可整体替换语言或调阈值）
references/taxonomy.md          六维度定义、规则 ID/阈值、问题分类、映射表模板
references/example.md           最小输入/调用/示意输出（示例）
```

维护：调阈值改 `references/messages.json` 的 `pat` 与 `scripts/verify.py` 中的常量；
新增规则需同时给 `诊断 / _b 依据 / _e 动作 / _r 风险` 四条模板，否则回落到维度默认文案。
