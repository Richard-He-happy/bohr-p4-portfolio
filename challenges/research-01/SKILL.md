---
name: deep-research-evidence-ledger
description: Decompose a research question into retrieval-addressable sub-questions with a dependency DAG, plan and log retrieval over the supplied corpus, and assemble a literature-review deliverable in which every claim carries a verbatim quote plus a locator. Use for literature review, evidence synthesis, screening, trend analysis or topic assessment that must stay inside the provided materials.
version: 1.0.0
license: MIT
---

# 深度研究 Agent：证据台账式文献综述

## 1. 用途与边界

把研究问题拆成**可独立检索的子问题**，规划检索波次与停止条件，在**已提供材料**上执行检索并留下可复跑的参数记录，产出「每条论断 → locator + 逐字 quote」的综述、证据矩阵与研究空白。

- 做：问题拆解、检索规划、多步工具调用记录、证据综合、冲突呈现、空白登记、可核验交付。
- 不做：逐句精读、方法学审查、翻译润色、材料外检索。不联网；检索式完整记录供有权者复跑，不据此声称领域完备性或新颖性。

适用：给定材料要求综述/证据表/选题评估，或多来源结论不一致需分清冲突与空白。不适用：要求现场联网检索、单篇翻译润色、给出材料中不存在的数值或引用。

## 2. 运行契约

```bash
python3 -B scripts/main.py --stage plan     --input /input --output /app/output
#   读 /app/output/evidence_candidates.json，写 /app/work/synthesis.json
python3 -B scripts/main.py --stage finalize --input /input --output /app/output
python3 -B scripts/main.py --stage check    --input /input --output /app/output
# 一次跑完：--stage auto（默认）
```

- 入口 `scripts/main.py`，依赖模块 `scripts/research_core.py`；资源按 `Path(__file__).parent` 定位，不依赖 CWD。
- 仅标准库，无网络，Python ≥3.8。有 `pdftotext` 时优先调用以获得页级 locator，否则退化为 stdlib 流解析（`stream:N` 并记 `degradations`）。
- 预算 64 次请求 / 900 秒 / 16k tokens；脚本软预算 `--budget-seconds 780`，超时先落盘 partial。
- **退出码恒为 0**；异常写入 `errors`，不阻断其他材料。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`（缺失则递归找 `case*.json`），原样保留 `case_id` 与 `output_contract`。
2. 研究问题按语义取 `research_question / question / task_instruction / instruction / prompt / objective / topic / 研究问题 / 研究任务 / goal / title` 中第一个 ≥15 字字符串；都没有则用 `task.md` 首句。
3. 递归扫描 `/input/**`，按扩展名 + **文件魔数**分类（%PDF→pdf，PK→docx，编码探测→text），不按文件名猜内容。
4. `case.json` / `task.md` 记 `parse_status: meta`，**不进证据语料**，避免把题面当证据。
5. 解析不了的材料（图片、xlsx、损坏 PDF）记 `unsupported/failed` + 缺口，不构造内容。

## 4. 输出契约

`result.json` 必含：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`research_question`、`sub_questions`、`search_plan`、`evidence_matrix`、`citations`、`synthesis{claims,conflicts,gaps}`、`sources`、`coverage`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`tool_calls`、`output_contract_echo`、`contract_fill`、`verification`。

输入 `output_contract` 的**每个字段名都作为顶层键出现**（缺值写 `null`/`[]`，键名不改）；`contract_fill` 给 `filled / null_filled / n_fields`；未知字段原样保留。

其它产物：`research_report.md`（主产物，8 节）、`evidence_map.csv`（claim→source→locator→quote→校验）、`evidence_candidates.json`、`source_index.json`、`tool_calls.jsonl`（每步参数/状态/耗时）、`selfcheck.json`。

## 5. 核心流程（Agent 侧 5 步）

1. `--stage plan`：产出拆解树（含 `depends_on`）、检索计划（波次/模式/检索式/停止条件）、逐子问题候选证据（已校验的逐字 quote + locator）。
2. 读 `evidence_candidates.json`：候选即「已确认存在于原文的句子」，引用其 `candidate_id` 最省事。
3. 候选不足时提高 `--top-k`，或改 `references/protocol.md` 的检索模板后重跑（可复跑、可对照）。
4. 写 `/app/work/synthesis.json`（schema 见 `references/protocol.md` §3）：claims（strength/evidence/conditions/limits）、conflicts、gaps、screening、limits。
5. `--stage finalize` → `--stage check`。finalize **重新解析原始文件**校验每个 quote；check 复核契约完整性、引用逐字命中、报告与 CSV 齐备。

## 6. 质量规则（题面六类要点 → 字段/检查/产物）

| 要点 | 字段 | 检查 | 产物 |
|---|---|---|---|
| 问题拆解 | `sub_questions[].type/deps` | 子问题可检索、依赖为 DAG、波次可并行 | `result.json`、报告 §2 |
| 检索覆盖 | `search_plan[]`（wave/mode/queries/hits/stop_condition） | 每子问题有检索式与命中数，空命中即缺口 | `tool_calls.jsonl` |
| 证据回链 | `citations[]`（source+locator+quote+used_by） | quote 逐字命中；非 insufficient 结论至少 1 条引用 | `evidence_map.csv`、报告 §7 |
| 冲突证据 | `synthesis.conflicts[]`（side_a/side_b/resolution/basis） | 双方各带引用；口径限 contextual / evidence_favours_* / unresolved | 报告 §5 |
| 综合结论 | `synthesis.claims[]`（strength/citations/conditions/limits） | 强度与证据一致，无证据即 insufficient | 报告 §4 |
| 研究空白 | `synthesis.gaps[].basis` | 绑定未覆盖子问题或缺失字段，禁止套话 | 报告 §6 |

## 7. 证据与定位规范

| 材料 | locator | 例 |
|---|---|---|
| PDF（pdftotext） / PDF（stdlib） | `p.<页>` / `stream:<n>` | `p.7` / `stream:3` |
| TXT/MD/DOCX | `doc~p<段>`（段落级） | `doc~p4` |
| CSV/TSV / JSON | `row=<行>` / `$[<记录>]` | `row=14` / `$[2]` |

quote 三级校验：`strict`（归一化空白后逐字命中）> `whitespace_insensitive`（去空白后命中，PDF 换行所致）> `none`（**拒收**：进 `pending_human`，强度降为 `insufficient`）。禁止改写原文凑通过。

## 8. 冲突与人工确认

- 双方同时呈现并各带引用，不得只写「尚存争议」。
- `contextual` 须给出人群/条件/方法差异证据；`evidence_favours_*` 须说明更强在哪；`unresolved` 保留双方区间，不取一方、不取均值。
- 进 `pending_human`：quote 未命中、零命中子问题、图片/表格解析失败、契约字段无法填值。每条含 `item / why / action`。

## 9. 预算与断点

`plan` 逐子问题落盘；超预算后余下子问题标 `budget_skipped` 并写 `degradations`，仍产出完整 `result.json`。任一阶段失败都保留上一次 `ok/partial` 结果，只追加 `errors`，不覆盖为空白。

## 10. 异常降级分支

| 情形 | 处置 | 可见位置 |
|---|---|---|
| 无材料 / 无 case.json | 仍写合法 partial，`input_error` 或 `partial` | `errors`、`pending_human` |
| case.json 非法 JSON | 记 `load_case` 错误，继续用 task.md 与目录材料 | `errors` |
| PDF 无 pdftotext | stdlib 流解析，locator 降 `stream:N` | `degradations` |
| PDF 损坏 / 扫描件 / 图片 | `failed`/`unsupported`，登记缺口，其余材料继续 | `sources`、`pending_human` |
| 子问题零命中 | 标 `empty` 并自动生成 `retrieval_gap` | `coverage`、`gaps` |
| quote 未命中 | 拒收该证据，结论降级 | `errors`、`pending_human` |
| 缺 synthesis.json | 只交证据台账，报告写明「未生成结论」 | 报告 §4 |

## 11. 自检清单

`--stage check` 输出 `selfcheck.json` 七项：`result_json`、`contract_fields`、`citations_verbatim`、`status_enum`、`report_exists`、`evidence_csv`、`claims_cited`，全过即 `7/7`。人工再核：能否顺 `[n]` 找到 locator 处原文；`status` 是否与实际完成度一致；`pending_human` 是否逐条处置。

## 12. 最小调用示例（示例，非正式案例结果）

输入：`/input/case.json`（含 `case_id` 与 `output_contract`）+ 两篇 txt 摘要；命令即 §2 的 plan/finalize/check。示意输出（**示例数据，仅示字段形状**）：

```json
{"case_id": "MIN-001", "status": "ok",
 "sub_questions": [{"id": "SQ1", "type": "scope", "deps": []}],
 "search_plan": [{"sq": "SQ1", "wave": 1, "queries": ["\"IL-2\" \"regulatory\""], "hits": 4}],
 "citations": [{"n": 1, "source_id": "s1", "locator": "doc~p5", "quote": "…", "quote_match": "strict",
                "used_by": ["C1"]}],
 "coverage": {"n_claims": 4, "quote_backlink_rate": 1.0}}
```

完整可运行示例见 `references/example.md`。

## 13. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 契约 / 流程 / 规则 / 自检 |
| `scripts/main.py` | 入口：`plan / finalize / check / auto` |
| `scripts/research_core.py` | 解析、索引、检索、契约回填、报告渲染、模板加载 |
| `references/protocol.md` | 拆解模板（脚本读取）、检索规则、synthesis schema、强度与 locator 口径 |
| `references/rubric_map.md` | 评分点 → 字段 → 检查 → 产物 对照 |
| `references/example.md` | 最小示例与演练步骤（标注示例） |

版本 1.0.0。调整拆解或检索策略只需改 `protocol.md` 的模板与检索词（无需改代码）；改版式改 `research_core.tb` 的调用点。回归自检：`--stage auto` 后看 `selfcheck.json` 是否 7/7。
