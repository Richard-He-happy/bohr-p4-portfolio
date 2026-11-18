---
name: reviewer-response-revision
description: 对指定版本稿件完成受控返修：把审稿意见（含一条意见内的多个子要求）拆成可执行条目，逐条给出决策与语气档，把实质性修改真实落到指定基线稿件，产出可编辑修订稿、逐条回复信、修改定位表、证据清单与结构化 result.json。用于投稿返修、rebuttal/response letter 起草，以及核对"回复信声称的修改是否真的在稿子里"。Use when asked to answer reviewer comments, revise a manuscript against them, draft a point-by-point response letter, or verify that claimed revisions match the manuscript version.
version: 1.0.0
---

# 审稿回复与论文修改（writing-07）

## 1. 用途与边界

输入「指定版本稿件基线 + 审稿意见摘要」，输出可直接提交编辑部的返修包：修订稿、逐条回复信、修改定位表、未到位证据清单。

**受控演练边界（最高优先级，任何输出不得越过）**

- `materials/manuscript-baseline.md` 是组织方基线摘要，`materials/reviewer-comments.md` 是组织方整理的意见摘要，**不是完整原稿，也不是审稿报告逐字全文**。
- 只修订指定基线；只处理实际给出的意见；不补写不存在章节；不臆造数据、文献或统计量。
- 不得声称："审稿人逐字要求"、"已补做实验/重做分析"、"原作者已改稿"、"编辑部已接收"、"整篇全文返修完成"、"已联网核验原评审"。
- **不得以"材料缺失"为由跳过可执行的实质修改**：基线内能改的必须改；改不了的进 `pending_human`，并在回复信中说明为什么改不了。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 入口 | `python3 scripts/main.py --input /input --output /app/output --work /app/work` |
| 依赖 | 仅 Python 3 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | 恒为 0；失败写入 `result.json` 的 `errors`/`degradations` |
| 第一落盘 | 任何处理前先写 partial `result.json`，结束时无条件覆盖为 final |
| 预算 | 64 次模型请求 / 900 秒；接近 780 秒直接 finalize 当前结果 |

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则递归找 `*case*.json`；JSON 坏掉时记 `errors` 并继续扫描材料。
2. 保留 `case_id` 与 `output_contract` 原样；再读 `task_instruction`、`organizer_workorder`、`organizer_edit_workorder` 等（键名不固定，按语义取）。
3. 递归扫描 `/input/**` 的 `.md/.txt/.rst/.tex`，用语料打分判定基线 vs 意见：文件名含 `manuscript|baseline|draft|paper|稿件` → 基线；含 `comment|reviewer|referee|意见|审稿` 或正文高频出现 reviewer/comment → 意见。
4. 其他附件（PDF/图片/CSV/XLSX/DOCX/JSON）只登记路径；未解析的材料在 `pending_human` 里列缺口，不猜内容。

## 4. 两遍工作流（必须两遍，缺第二遍视为未完成）

**第一遍（草稿与台账）**

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

产出 `comment_ledger.json`：每条意见 → 子要求列表（`C1.1`、`C1.2`…），每条带 `type`（method/data/format/ethics/writing）、默认 `decision`、`evidence_status`、建议 `anchor`（`P###` 段落号）。这一步不写正文。

**第二遍（逐条写修改，再 finalize）**

1. 读 `comment_ledger.json`，对每个 `sub_id` 决定 `decision` 与 `tone`，写出**修订后的原文级文本**。
2. 写入 `/app/work/edit_plan.json`（schema 与示例见 `references/usage.md`；模板见下文 §5）。
3. 再跑同一条命令；脚本会应用修改、逐条校验、生成回复信与 `result.json`。

**硬规则**：每条真正可执行的子要求都要有 edit；只有确实超出材料的条目才允许无 edit，并在 `sub_overrides` 中写清 `evidence_status=not_provided` 与理由。

## 5. edit_plan.json 最小形状

```json
{"edits": [{"id": "E1", "comment_id": "C1", "sub_id": "C1.1", "op": "replace",
            "anchor": "P005",
            "original_quote": "基线中逐字存在的一句",
            "revised_quote": "修改后的完整句子",
            "reason": "为什么改", "decision": "accept",
            "evidence_status": "provided", "response_note": "回复信中的补充说明"}],
 "sub_overrides": [{"sub_id": "C3.1", "decision": "partial",
                    "evidence_status": "not_provided",
                    "evidence_note": "为什么材料内无法完成",
                    "response_note": "回复信中的说明"}],
 "pending_human": [{"item": "C1.2", "reason": "需人工补的输入"}]}
```

`op` 取值：`replace`（默认，按 `original_quote` 定位并替换）、`replace_all`、`append_after`（在锚点段之后插入新段）、`append_end`。

## 6. comment_ledger 字段

| 层级 | 字段 |
|---|---|
| 意见 | `comment_id`、`source_label`（原文标题，用于编号对齐）、`raw_summary`、`decision`、`tone`、`change_ids`、`evidence_needed` |
| 子要求 | `sub_id`、`text`、`type`、`decision`、`tone`、`anchor`、`change_ids`、`evidence_status`、`evidence_note`、`needs_human` |

`decision ∈ {accept, partial, reject, clarify, invalid}`；`tone ∈ {accept, clarify, polite_rebuttal, appeal}`，由 `decision` 映射，回复信措辞由模板强制，不自由发挥。

## 7. 输出文件

| 文件 | 内容 |
|---|---|
| `revised_manuscript.md` | 唯一主产物：只在基线上做改动，章节层级与编号保持 |
| `response_letter.md` | 逐条回复：每条子要求一段，带 `decision/tone`、`P###` 定位、逐字改后原文 |
| `comment_ledger.json` | 意见→子要求→决策→改动→证据的中枢台账 |
| `change_locator.json` | 每处改动的 `P###` 定位与逐字 quote（可被独立核验） |
| `evidence_pending.md` | 未到位证据清单与运行异常 |
| `version_notes.md` | 版本、基线名、覆盖率与边界说明 |
| `pending_human.json` | 需人工确认的条目与原因 |
| `result.json` | 契约回填 + 计数 + 核验报告 |

`locator` 语义：`P###` = 交付文件中以空行分段的第 ### 个块（标题也计入），因此可在任意 Markdown 编辑器中独立复核。

## 8. result.json

- 原样回填输入 `output_contract` 的**全部键**（键名不改、缺值 `null`/`[]`、未知键保留）；`case_id` 原样。
- 必有：`status`（ok/partial/insufficient_evidence/input_error）、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`counts`、`comment_ledger_summary`、`workorder_report`、`verification`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`issues`、`changes`、`runtime`。
- `counts` 至少含：意见数、子要求数、已落实数、未到位数、`locator_hit_rate`、各类 decision 计数。

## 9. 质量规则（对应评分点）

1. **答得全**：意见数 = ledger 条目数；一条意见内的每个子要求各占一行、各有 `decision`；禁止"已按意见修改"式笼统回复。
2. **改得准**：`revised_quote` 必须能逐字出现在修订稿中（脚本用 `locate()` 校验并写 `hit`）；命中失败即降级为 partial 并进 `pending_human`，绝不改原文凑通过。
3. **证得住**：`evidence_status ∈ {provided, not_provided, not_applicable}`；未补做的写 `not_provided` + 原因，禁止写"已补做"。
4. **对得上**：回复信中的定位直接取自 `change_log.locator`，同一来源生成，天然 join 一致。
5. **不漂移**：每条改动的数字集合必须是原句数字集合的超集（`numbers_preserved`）；数字被改动即进 `pending_human`。
6. **语气**：四档模板化；`reject/invalid` 必须给出复核依据，不得人身或情绪化表达。

## 10. 异常与降级

| 情形 | 处置 |
|---|---|
| 意见互相冲突 | 各自独立给 `decision`，在回复信说明取舍规则，冲突项进 `pending_human` |
| 意见本身有误 | `decision=invalid`、`tone=appeal`，引用基线原文说明出入，不静默丢弃 |
| 基线缺章节 | 不新增整章；在现有段落内说明或进 `pending_human` |
| 无法补实验/数据 | `evidence_status=not_provided` + 原因 + 回复信如实说明，不假装完成 |
| 版本不匹配 | 以本次输入的基线为唯一版本；在 `version_notes.md` 记录基线文件名 |
| 权限/文件不可读 | 记 `errors`，其余流程继续，输出 partial |
| 无意见文件 | `degradations=comments_missing`，status=`insufficient_evidence` |
| 无基线文件 | 写占位产物，status=`input_error`，`pending_human` 说明 |
| edit 定位失败 | `edit_not_applied` + 该子要求降为 partial |
| 越界声明 | 自动删除该句并记 `overclaim_removed` |

## 11. 自检

```bash
python3 scripts/verify.py --output /app/output --input /input
```

检查项：契约键回填、产物齐全、`P###` 定位与逐字 quote 命中、decision 完整性、数字保持、越界声明扫描、`accept` 是否都有已核验改动。任一 `ok:false` 都要回到 edit_plan 修，或如实保留 partial。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py --input ./mycase --output ./out --work ./work   # 第一遍：生成台账
# 编辑 ./work/edit_plan.json（1 条 replace + 1 条 sub_override）
python3 scripts/main.py --input ./mycase --output ./out --work ./work   # 第二遍：落稿+回复信
python3 scripts/verify.py  --output ./out --input ./mycase
```

示意输出（示例）：`counts = {comments_total: 3, sub_requirements_total: 6, subs_with_verified_change: 3, locator_hit_rate: 1.0}`，`status = partial`（因 2 条证据未到位）。此数字来自自造夹具，仅演示接口。

## 13. 文件清单

```
SKILL.md                 元数据 + 本文档
scripts/main.py          输入发现、段落/意见解析、改稿应用、定位校验
scripts/verify.py        台账构建、回复信渲染、产物审计（可独立运行）
references/taxonomy.json 意见类型词表、语气映射、越界声明词表
references/templates.json 中英文回复信语气模板
references/usage.md      edit_plan 完整 schema、字段说明、自查与复用指引
```

## 14. 维护

- 版本 1.0.0；新增类型/词表只改 `references/taxonomy.json`，不动脚本。
- 调整语气措辞只改 `references/templates.json`。
- 修改脚本后必跑 §11 自检与一次最小夹具回归。
