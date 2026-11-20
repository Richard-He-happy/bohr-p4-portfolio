---
name: reviewer-response-revision
description: "面向审稿回复与论文修改的受控返修 Skill：把 reviewer-comments 摘要拆成意见/子要求台账，对 manuscript-baseline 做真实落点修改，产出可编辑修订稿、逐条回复信、修改定位表、证据清单和可复核 result.json。Use when asked to answer reviewer comments, revise a manuscript, draft a point-by-point response, or verify claimed revisions against the manuscript."
version: 3.0.0
---

# 审稿回复与论文修改 Skill

## 0. 最高优先级：要交付什么

输入是 `/input/case.json`、`/input/task.md` 和材料文件。输出必须是一套可直接复核的受控返修包：修订稿、逐条回复信、修改定位、证据清单、人工确认项、结构化 `result.json`。

本 Skill 只处理本次输入中实际给出的基线稿件与审稿意见摘要。基线材料和意见摘要通常是组织方提供的受控文本；不得声称“审稿人逐字要求”“已补做实验”“原作者已改稿”“编辑部已接收”“已联网核验原评审”或“整篇全文返修完成”。不得因材料不足跳过基线内可执行的实质修改。

所有关键数字、术语、引用、论断都必须带来源编号 `[S#]` 和定位 `文件#行号` 或 `文件#段落号`。不新增材料外事实，不编造数据、文献、统计量或文献出处。

## 1. 运行契约

| 项 | 约定 |
|---|---|
| 输入目录 | `/input` |
| 工作目录 | `/app/work` |
| 输出目录 | `/app/output` |
| 首选入口 | `python3 scripts/main.py run --input /input --output /app/output --work /app/work` |
| 兼容入口 | 如包内脚本暂不支持 `run` 子命令，则执行 `python3 scripts/main.py --input /input --output /app/output --work /app/work` |
| 校验入口 | `python3 scripts/verify.py --output /app/output --input /input` |
| 依赖 | 仅 Python 3 标准库，不联网，不依赖 CWD；资源路径用 `Path(__file__).resolve().parent` 定位 |
| 退出码 | 任何情况下必须退出 0；错误写入 `result.json` 的 `errors` / `degradations` / `gaps` |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 资源限制 | ≤50 个 UTF-8 文本文件，单文件 ≤500KB，总大小 ≤2MB，无 symlink |

## 2. 单命令全流程

`run` 命令内部必须完成四段流程：

1. `init`：盘点 `/input` 全部材料，建立来源编号 `S#`，抽取原文候选句、数字、引用，识别基线稿件与审稿意见，拆分意见/子要求，建立冲突分组。输出至少包含 `/app/work/inventory.json`、`/app/work/comment_ledger.json`、`/app/work/facts.json`、`/app/work/conflicts.json`，并立即落盘 partial `result.json`。
2. `check`：如果 `/app/work/draft.json` 已存在且非空，校验其 schema、quote 是否逐字存在于定位处、locator 是否有效；如 draft 无效，记录 `draft_invalid` 并回退确定性抽取。
3. `build`：应用 `/app/work/draft.json` 或确定性兜底稿，生成全部交付物与最终 `result.json`。
4. `selfcheck`：对产物与 `output_contract` 做契约自检，检查 locator 命中、越界声明、数字保持、文件完整性，并把结果写入 `result.json.verification`。

同一命令可重复运行。第一次运行通常生成确定性基线；Agent 写入 `draft.json` 后第二次运行会应用人工判断。

## 3. Agent-first 双路径

### 路径 A：Agent 判断路径

1. 先运行 `run` 或不带改稿的 init 命令，得到 `/app/work/inventory.json` 与 `/app/work/comment_ledger.json`。
2. Agent 真实阅读 `/input` 下的实际材料，核对来源编号、逐字 quote、locator 和数字。
3. Agent 把判断写入 `/app/work/draft.json`：每条意见/子要求给决策、语气、修改原文、回复说明、修改 op、证据状态。
4. 再次运行 `run`，让脚本按 `draft.json` 应用修改、定位校验、渲染产物、生成 `result.json`。

Agent 可以在脚本产物上增强正文型交付物，但不得改变结构化 JSON 的契约键名；增强后必须同步 `result.json` 的 `verification` 或 `change_log`。

### 路径 B：确定性兜底路径

如果 `/app/work/draft.json` 不存在或无效，`build` 必须用 `init` 台账做确定性抽取，生成实质工作稿，而不是空模板。该路径必须：

- 使用逐字 quote 与 locator；
- 对每条意见尽量给出可执行修改建议或说明不可执行原因；
- 在 `result.json.degradations` / `gaps` 中诚实记录 `AUTO_EXTRACT`；
- 不假装已经完成超出材料范围的人工核验。

### 两条路径同契约

无论走 Agent 路径还是确定性兜底，最终必须产出同一套文件、同一份 `result.json` 契约。差异只体现为 `reviewed_by_agent`、`auto_extract`、`draft_invalid` 和人工确认项的多少。

## 4. 输入发现与材料解析

1. 优先读取 `/input/case.json`；如果不存在，递归查找 `/input/**/*case*.json`。保留原始 `case_id` 和 `output_contract`，不要改键名。
2. 读取 `/input/task.md` 以及任何任务说明，按语义识别任务动作，不依赖固定键名。
3. 递归扫描 `/input/**` 下 `.md` `.txt` `.rst` `.tex` `.csv` `.json`；对 PDF、DOCX、XLSX、图片等，用可用解析工具实际提取文本，工具失败时只记录路径和原因，不猜测内容。
4. 基线/意见识别采用文件名加正文语义双重判断：文件名含 `manuscript|baseline|draft|paper|稿件` 且正文主要是论文段落，判为基线；文件名含 `comment|reviewer|referee|意见|审稿` 且正文高频出现评论要求，判为意见。
5. 给每个来源材料分配短编号：`S1` 基线，`S2` 意见，`S3` 附件等。所有事实抽取记录来源编号和 locator。
6. 解析失败、文件不可读、编码异常的，记入 `errors` / `degradations`，不中断流程。

## 5. 意见拆解与台账

意见台账必须覆盖“答得全”：一条意见内有多个子要求的，拆成 `C1.1`、`C1.2` 等。不得只写“已按意见修改”这类笼统回应。

### comment_ledger.json 字段

| 层级 | 字段 |
|---|---|
| 意见级 | `comment_id`、`source_label`、`raw_summary`、`decision`、`tone`、`change_ids`、`evidence_needed` |
| 子要求级 | `sub_id`、`text`、`type`、`decision`、`tone`、`anchor`、`change_ids`、`evidence_status`、`evidence_note`、`needs_human` |

### 枚举

- `type ∈ {method, data, writing, format, ethics}`；无法判断时可用 `unknown`，但在 `comment_ledger_summary` 中说明。
- `decision ∈ {accept, partial, reject, clarify, invalid}`。
- `tone ∈ {accept, clarify, polite_rebuttal, appeal}`。
- `evidence_status ∈ {provided, not_provided, not_applicable}`。

### 冲突处理

意见互相冲突、意见与基线不一致、意见本身可能有误时：不合并掩盖，逐条保留原文判断；在 `conflicts` 中登记，在回复信中说明采取哪个立场及理由；需要作者决定的写入 `pending_human`。

## 6. draft.json：Agent 判断的最小形状

Agent 应把真实判断写入 `/app/work/draft.json`，不要只使用空白模板。最小形状如下：

```
{
  "case_id": "来自输入",
  "comments": [
    {
      "comment_id": "C1",
      "source_quote": "意见原文中的关键句",
      "summary": "意见主旨",
      "type": "method",
      "decision": "accept",
      "tone": "accept"
    }
  ],
  "subs": [
    {
      "sub_id": "C1.1",
      "comment_id": "C1",
      "summary": "子要求",
      "type": "method",
      "decision": "accept",
      "tone": "accept",
      "anchor": "P005",
      "source_quote": "基线中逐字存在的一句",
      "source_locator": "manuscript-baseline.md#L12",
      "edit_op": "replace",
      "revised_quote": "修改后的完整句子",
      "reason": "为什么这样改",
      "response_note": "回复信中的说明",
      "evidence_status": "provided",
      "evidence_note": "证据已在基线或附件何处",
      "needs_human": false,
      "numbers_preserved": true
    }
  ],
  "pending_human": [
    {"sub_id": "C2.2", "reason": "需要作者补数据或确认"}
  ],
  "gaps": [],
  "conflicts": [],
  "overrides": []
}
```

`edit_op` 取值：`replace`、`replace_all`、`append_after`、`append_end`、`none`。`none` 仅在意见超出材料范围、不需或无法修改正文时使用，并必须有 `response_note` 和 `evidence_status`。

## 7. 输出文件与定位语义

最终产物放在 `/app/output`：

| 文件 | 内容 |
|---|---|
| `revised_manuscript.md` | 可编辑修订稿，只在输入基线上做改动，保持章节结构与编号 |
| `response_letter.md` | 逐条回复信，每条子要求一段，含决策、语气、定位、修改前后原文、理由 |
| `comment_ledger.json` | 意见→子要求→决策→改动→证据的中枢台账 |
| `change_locator.json` | 每处修改的来源定位、逐字 quote、修订后 quote |
| `evidence_pending.md` | 未到位证据、不可补做原因、材料缺口 |
| `version_notes.md` | 版本说明、基线名、覆盖范围、边界 |
| `pending_human.json` | 需人工确认条目 |
| `result.json` | 最终结构化结果，满足 output_contract 和附加契约 |

### locator 语义

- `locator` 统一使用 `source_file#L行号` 或 `source_file#P段落号`，其中行号为 1-based，段落号为按空行分割的块序号（标题也计入）。
- 回复信中的修改定位必须直接来自 `change_locator.json` 或同一台账，保证“回复信、修改稿、定位表”一致。
- `change_locator.json` 中每条修改必须能被独立检索核对；命中失败不得改稿凑通过，必须降级为 partial 并记 `pending_human`。

## 8. result.json 契约

`result.json` 必须做到双回显：

1. 顶层包含输入 `output_contract` 中的全部键，键名不变，并原样保留 `case_id`。
2. `output_contract` 作为嵌套对象再出现一次，包含同样键值。
3. 顶层除契约字段外，必须有：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`gaps`、`issues`、`changes`、`runtime`、`counts`、`comment_ledger_summary`、`workorder_report`、`verification`、`auto_extract`。

### status 取值

`ok`、`partial`、`insufficient_evidence`、`input_error`。未完成应使用 `partial` 并说明，不要伪造 `ok`。

### sources / evidence_map 条目形状

```
{
  "source_id": "S1",
  "file": "materials/manuscript-baseline.md",
  "locator": "materials/manuscript-baseline.md#L12",
  "quote": "原文逐字引用",
  "kind": "manuscript|reviewer_comment|attachment|parsed_text",
  "note": "可选说明"
}
```

### counts 至少包含

意见数、子要求数、已落实数、未到位数、evidence provided/not_provided/not_applicable 数、locator hit 数、locator_hit_rate、各类 decision 计数、各类 tone 计数。

### verification 必须写入

`reviewed_by_agent`、`auto_extract`、`verify_command`、`locator_hit_rate`、`overclaim_removed`、`numbers_checked`、`issues`。不生成 `golden_standard`、自造 `diff_report` 或加权自评分。

## 9. 质量规则：直接对应 rubric

### 实际效果 40 分

- 每条意见、每个子要求都能在 `comment_ledger.json` 中找到明确处理结论。
- `accept` 必须在 `revised_manuscript.md` 中真实出现；`partial` / `reject` 必须有理由。
- 回复信中不得空话致谢；必须给出具体动作、位置和修改前后文本。
- 数字保持：每条改动的数字集合必须是原句数字集合的超集。数字被改动、删除或新增关键数字，必须进 `pending_human` 并说明。
- 定位可核验：`change_locator.json` 中的每个 locator 都能在指定版本稿件中打开核对。

### 使用增益 25 分

- 交付物应让用户无需重新逐条比对意见和行号；台账、回复信、定位表直接可读。
- `comment_ledger.json` 可用于版本管理和多轮返修；`references/taxonomy.json`、`references/templates.json` 提供可复用分类法和语气模板。
- `result.json.verification` 中写明核验命令和结果，支撑“相对基础 Agent 的增益”复核证据。

### 创新增益 15 分

- 意见子要求拆解、`anchor` 定位、`edit_op` 应用、证据状态四类动作形成可复用流程。
- 语气四档强制映射，避免无原则顺从或冒犯性表达。
- 版本一致性由同一台账驱动，避免回复信与修改稿脱节。

### 可靠体验 10 分

- 脚本必须始终退出 0，所有异常写入结构化字段。
- 长稿件、多意见、冲突意见、缺章节、解析失败、权限不足、超时都需有明确降级。
- 首次运行即落盘 partial `result.json`；任何时候超时立即 finalize 当前已经存在的产物。

### 生态贡献 10 分

- `references/usage.md` 说明 schema 与复用方法。
- `references/taxonomy.json` 与 `references/templates.json` 可被其他返修任务直接使用。
- SKILL.md 自身包含完整调用、异常处理、自检清单。

## 10. 异常处理与隐藏案例鲁棒性

| 情形 | 处置 |
|---|---|
| 材料缺失 / 文件损坏 | 记录 `degradations` 和 `pending_human`；基线或意见完全缺失时 `status=insufficient_evidence` 或 `input_error`；仍生成合法 partial result.json，不编造内容 |
| PDF / DOCX / 图片解析失败 | 尝试可用解析工具；失败则记录路径和错误，继续处理其他可用材料 |
| 空输入 / `case.json` 缺失 | 递归查找；找不到则创建最小合法 `result.json`，记录 `errors`，不崩退出 |
| `output_contract` 缺失 | 按最小契约补齐 `case_id`、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`，并记录 `contract_missing` |
| 意见冲突 / 意见有误 | 逐条保留，冲突项进 `pending_human`，回复信说明取舍规则 |
| 基线缺章节 / 无法补实验 | 不新增整章；在现有可编辑句中修改或写 `pending_human`；说明为何不能补做 |
| 版本不匹配 | 以本次输入的基线为唯一版本，在 `version_notes.md` 记录基线文件名 |
| 文件不可读 / 权限不足 | 记 `errors`，其余流程继续，输出 partial |
| edit 定位失败 | 记 `edit_not_applied`，该子要求降级为 partial；绝不强行修改原文凑通过 |
| 越界声明 / 过度承诺 | 自动删除并记录 `overclaim_removed`，回应中改写为可核验的边界说明 |
| 超时 / 预算耗尽 | 立即 finalize 当前结果，状态为 `partial`，`issues` 中列出未完成项 |
| 任何情况 | 必须产出完整且合法的 `result.json`，退出码 0 |

## 11. 预算策略

| 阶段 | 模型请求预算 | 动作 |
|---|---|---|
| 初始化 | ≤2 | 跑 `run` init，落盘 partial |
| 材料解析 | ≤6 | 真实读取材料、解析附件、建立事实基线 |
| 台账与 draft | ≤15 | 拆意见、核子要求、写 `draft.json` |
| 构建 / 回填 | ≤5 | 跑 `run` build，或兼容入口生成产物 |
| 自检与增强 | ≤15 | 跑 `verify.py`，逐项检查定位和数字 |
| 最终 finalize | ≤2 | 确保 result.json 合法并退出 0 |

确定性兜底路径应尽量少用模型请求。Agent 应优先让脚本生成完整基线，用剩余请求做核验和正文增强。接近 780 秒或请求即将耗尽时，立即 finalize 当前产物。

## 12. 自检清单

- 已读取 `/input/case.json`、`task.md` 和全部可读材料，没有凭文件名猜测内容。
- 已保留原始 `case_id` 和 `output_contract` 键名。
- 已运行主命令至少一次；如有 `draft.json`，已运行第二次。
- 已检查 `revised_manuscript.md` 与 `response_letter.md` 不是空模板。
- 已运行 `python3 scripts/verify.py --output /app/output --input /input`。
- `result.json` 顶层和嵌套 `output_contract` 都包含契约字段。
- `status`、`sources`、`uncertainty`、`change_log`、`errors`、`degradations` 真实可信。
- 每条 `accept` 都有对应 edit 且 locator 命中；`partial` / `reject` 有明确理由。
- 数字保持规则已检查，数字改动已进 `pending_human`。
- 越界声明已扫描并记录 `overclaim_removed`。
- 可选 Office/图形产物如有，已提供 PDF/PNG 预览。
- 所有产物在 `/app/output`，无 symlink，符合资源限制。
- 所有命令退出码为 0，最终 `result.json` 合法。

## 13. 最小调用示例

输入 `/input/case.json` 及材料就绪后：

```
python3 scripts/main.py run --input /input --output /app/output --work /app/work
python3 scripts/verify.py --output /app/output --input /input
```

示意输出为示例，不代表正式案例结果：`status=partial`，`counts={comments_total:3, sub_requirements_total:6, subs_with_verified_change:3, locator_hit_rate:1.0}`，`auto_extract:true`，`pending_human` 包含需作者补数据的条目。

## 14. 文件清单

```
SKILL.md                 本说明，含触发条件、流程、契约、异常、自检
scripts/main.py          输入发现、意见拆解、改稿应用、定位校验、确定性兜底、result.json 生成
scripts/verify.py        产物与 output_contract 自检，可独立运行
references/taxonomy.json 意见类型词表、语气映射、越界声明词表
references/templates.json 中英文回复信语气模板
references/usage.md      draft.json / comment_ledger.json 完整 schema、字段说明、复用指引
```

包内路径只能引用上述文件。如 `scripts/main.py` 当前不支持 `run` 子命令，则执行兼容的 `python3 scripts/main.py --input /input --output /app/output --work /app/work`；结果契约不变。