# usage.md — 调用、输入、字段与自查（writing-07 · v1.0.0）

> 本文件示例均标注「示例」，是自造夹具上的接口演示，不是任何正式案例的结果。

## 1. 三次命令的完整流程

```bash
# 1) 第一遍：解析材料，生成意见台账（不改正文）
python3 scripts/main.py --input /input --output /app/output --work /app/work

# 2) 人工/模型填写 /app/work/edit_plan.json（见 §3）

# 3) 第二遍：应用修改、生成回复信与 result.json
python3 scripts/main.py --input /input --output /app/output --work /app/work

# 4) 审计（可反复运行，不修改任何产物）
python3 scripts/verify.py --output /app/output --input /input
```

参数：`--input`（默认 `/input`）、`--output`（默认 `/app/output`）、`--work`（默认 `/app/work`）、`--plan`（显式指定 edit plan）、`--stage {auto,plan,draft,finalize}`、`--deliverable-name`（默认 `revised_manuscript.md`，若案例指定了文件名则改为对应名字）。

`--stage auto` 的行为：存在 `edit_plan.json` 且含 `edits`/`sub_overrides` → finalize；否则 draft（只出台账，正文不改）。

## 2. 输入

必需：
- `/input/case.json`（含 `case_id`、`output_contract`，可选 `organizer_workorder`/`organizer_edit_workorder`）
- 稿件基线：文件名含 `manuscript`/`baseline` 的 Markdown/TXT（如 `materials/manuscript-baseline.md`）
- 意见摘要：文件名含 `comment`/`reviewer`/`意见` 的文件（如 `materials/reviewer-comments.md`）

可选：其他附件（PDF/图片/表格）。脚本只登记不解析，未用到的材料在 `pending_human` 中列为缺口。

意见文件的结构容错：支持 `## Reviewer 1` + `### Comment 2`、`Comment 1:`、`1. ...`、`**Comment 3**`、`意见2：` 等写法；一条意见内的 `(a)/(b)`、`- `、`1)` 列表会被拆成多个子要求，否则按句法 + 情态动词线索（should/please/add/clarify/建议/请/需要…）拆分。

## 3. edit_plan.json 完整 schema

```json
{
  "edits": [
    {
      "id": "E1",
      "comment_id": "C1",
      "sub_id": "C1.1",
      "op": "replace",
      "anchor": "P005",
      "original_quote": "基线中逐字存在的一句原文",
      "revised_quote": "修改后的完整句子（会替换进正文）",
      "reason": "改动原因（写进 change_log）",
      "decision": "accept",
      "tone": "accept",
      "evidence_status": "provided",
      "evidence_note": "",
      "response_note": "回复信中该子要求的补充说明（可空）"
    }
  ],
  "sub_overrides": [
    {"sub_id": "C3.1", "decision": "partial", "tone": "clarify",
     "evidence_status": "not_provided",
     "evidence_note": "材料内没有炎症指标数据，无法补测",
     "response_note": "如实说明为何无法补做，并给出替代说明"}
  ],
  "pending_human": [{"item": "C1.2", "reason": "需作者提供精确 p 值"}]
}
```

字段规则：

| 字段 | 说明 |
|---|---|
| `op` | `replace`（默认）/`replace_all`/`append_after`/`append_end` |
| `anchor` | 建议定位（台账里给出的 `P###`）；有 `original_quote` 时可省略，脚本会全文查找 |
| `original_quote` | 必须在基线中逐字存在；`append_after` 用它确定插入点 |
| `revised_quote` | 必填；finalize 后必须能在修订稿中逐字命中，否则该条降级 partial 并进 `pending_human` |
| `decision` | `accept`/`partial`/`reject`/`clarify`/`invalid` |
| `tone` | 可省略；默认由 decision 映射为 accept/clarify/polite_rebuttal/appeal |
| `evidence_status` | `provided`（材料内可查）/`not_provided`（明确说明未提供）/`not_applicable` |

多条子要求可以共用一次 `replace`（一条 `revised_quote` 同时满足两点）——把两条 edit 的 `revised_quote` 写成同一句即可，两条都会各自登记 `change_ids`。

## 4. 定位规范（可核验性的关键）

- `locator` = `P###`，即交付文件中「以空行分隔的第 ### 个块」，标题块也计数。
- 每条改动同时记录 `baseline_anchor`（改前块号）与 `locator`（改后块号）。
- 回复信里的位置**直接取自** `change_log.locator`，因此回复信与定位表天然一致；评审可打开 `revised_manuscript.md` 数到第 ### 块逐字比对 `revised_quote`。
- 不使用页码/行号（基线无稳定行号，跨工具不可复现）。

## 5. result.json 字段速查

| 字段 | 含义 |
|---|---|
| `case_id` | 原样保留 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | 主产物文件名 |
| `preserved_facts` | 未改动处的数字/引用原句 + `locator`（防"顺手改数") |
| `evidence_map` | `claim` → `locator` → `source_quote`（改动）或 `basis=baseline_unchanged`（未改动） |
| `change_log` | 每条改动 `original_quote`/`revised_quote`/`reason`/`locator`/`numbers_preserved`/`hit` |
| `counts` | 意见数、子要求数、已落实数、未到位数、`locator_hit_rate`、decision 计数 |
| `verification` | 审计报告（9 项检查 + 计数） |
| `workorder_report` | `organizer_workorder` 每项的执行状态 |
| `pending_human` / `errors` / `degradations` / `issues` / `uncertainty` | 缺口、异常、降级、不确定性 |
| `output_contract` 的所有键 | 原样回填（未知键保留，缺值 `null`/`[]`） |

## 6. 决策与语气对照

| decision | tone | 使用条件 | 回复信写法 |
|---|---|---|---|
| accept | accept | 基线内可完成且已完成 | 认同 + 落点定位 + 改后原文 |
| partial | clarify | 只能完成一部分，其余进 `pending_human` | 认同部分 + 已改定位 + 未完成原因 |
| clarify | clarify | 意见基于误读，但改写措辞确有帮助 | 先复述基线实际写法，再给改动 |
| reject | polite_rebuttal | 改动会与材料事实矛盾，保留原文 | 认同关切 + 复核依据 + 保留说明 |
| invalid | appeal | 意见与基线明显不符（章节/数字/已处理） | 事实性指出出入 + 若编辑坚持愿配合 |

禁止：无原则顺从（"完全同意并已全面修改"但正文无改动）、冒犯性反驳、承诺材料外的工作。

## 7. 示例（示例，非正式案例结果）

自造夹具：3 条意见 / 6 个子要求 / 3 次 replace。

```json
{"edits": [{"id": "E1", "comment_id": "C2", "sub_id": "C2.1", "op": "replace", "anchor": "P003",
  "original_quote": "HbA1c decreased by 0.6 percentage points in the exercise group and by 0.1 percentage points in the usual-care group (p < 0.05). [12]",
  "revised_quote": "HbA1c decreased by 0.6 percentage points in the exercise group (n = 42) and by 0.1 percentage points in the usual-care group (n = 42) (p < 0.05). [12]",
  "reason": "Abstract must state per-group sample size", "decision": "accept", "evidence_status": "provided"}]}
```

运行后（示例）：`status=partial`、`counts.locator_hit_rate=1.0`、`counts.sub_requirements_total=6`、`counts.subs_with_verified_change=3`，两条证据类意见为 `not_provided`。

## 8. 复用建议（生态）

- **意见分类法**：`taxonomy.json` 的 `types`/`tone_map`/`decision_rules` 可直接用于其他期刊返修，改词表即可。
- **回复信模板**：`templates.json` 的四档措辞可替换成本领域习惯表达，不影响脚本。
- **定位脚手架**：`P###` 方案对任何 Markdown 稿件通用；若输入是 DOCX/PDF，先转 Markdown 再复用。
- **评分表**：`verify.py` 的 9 项检查可直接当作人工评审清单使用。

## 9. 自查清单（交付前）

1. `comment_ledger.json` 的意见数与意见文件条目数一致；
2. 抽查 ≥1 条含多个子要求的意见，确认已拆成 `C1.1`/`C1.2` 且各有 decision；
3. 每条 `accept` 都有 `change_ids` 且 `locator_hit_rate=1.0`；
4. `response_letter.md` 中出现的每个 `P###` 都能在 `revised_manuscript.md` 中数到；
5. `evidence_pending.md` 无"已补做"类表述；
6. `result.json` 的 `output_contract` 键一个不少；
7. `verify.py` 的 `ok` 为 true；不为 true 时确认对应 partial 已在 `pending_human` 中如实记录。
