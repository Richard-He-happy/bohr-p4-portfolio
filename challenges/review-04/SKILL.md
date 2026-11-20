---
name: paper-argument-audit
description: 对论文或科研材料进行可复核的逻辑与论证审查，逐条输出问题、类型、严重度、精确原文位置、逐字摘录与可执行修改建议；覆盖论点—证据对齐、推理链、章节衔接、方法、统计、引用与规范。Use when the task asks to review, peer-review, critique, audit, verify claims, or 审稿/审查 a manuscript. Emits result.json, review_report.md, issues.csv, claims.csv, evidence_table.json, pending_human.md, SELFTEST.md and selfcheck.json.
version: 2.0.0
license: MIT
---

# paper-argument-audit — 论文逻辑与论证审查

## 0. 运行契约（最高优先级）

本 Skill 的唯一标准入口：

```text
python3 -B $SKILL/scripts/audit.py run --input /input --output /app/output --work /app/work
```

`$SKILL` 默认是 `/skills/weekly-skill`；若不存在，用 `SKILL.md` 所在目录。

`audit.py run` 内部严格等于三步：

```text
init -> build -> selfcheck
```

也可以分步执行：

```text
python3 -B $SKILL/scripts/audit.py init --input /input --work /app/work --output /app/output
python3 -B $SKILL/scripts/audit.py build --input /input --work /app/work --output /app/output
python3 -B $SKILL/scripts/audit.py selfcheck --input /input --work /app/work --output /app/output
```

铁律：

1. 无论输入是否完整、解析是否失败、Agent 是否来得及写 draft，`audit.py` 必须退出码 0。
2. `init` 第一步必须先写一个合法 partial `/app/output/result.json`。
3. 最终 `result.json` 必须能被 `json.load` 解析，且同时回显 `case_id`、`output_contract` 与顶层契约字段。
4. 禁止以文件名、领域标签、外部知识猜测实际论文内容；所有判断必须来自实际解析出的原文文本。
5. 材料缺失、扫描版无文本、超长截断、引用无法获取、章节缺失，都要显式写入 `errors`、`degradations`、`uncertainty` 或 `pending_human`，不得编造。
6. 本包脚本只做确定性解析、定位、校验、渲染与兜底抽取；Agent 的职责是真实阅读、判断、区分作者主张/引用他人观点/假设情形，并提供最终成稿判断。

---

## 1. 使命与边界

### 做

- 抽取作者核心主张及其限定条件。
- 区分作者主张、引用他人观点、明确假设情形、背景共识。
- 逐条检查主张是否有本文数据、引用或明确假设支撑。
- 检查结论强度是否超过证据能支撑的范围。
- 检查推理链是否存在跳跃、隐含假设未说明、替代解释未排除、相关与因果混用。
- 检查章节衔接：摘要与正文、引言承诺与结果交付、方法与结果口径、图表与正文是否对应。
- 检查事实、引用支持、方法设计、统计报告、论证链、学术规范六类问题。
- 为每条问题给出精确定位、逐字原文、类型、严重度、判断依据和可执行改法。
- 对无法确认的条目标记待复核，不凭空补结论。

### 不做

- 不做文字润色与语言表达优化。
- 不做查重与学术不端判定。
- 不做参考文献格式排版检查。
- 不重做原始数据统计复算。
- 不提供投稿策略或选刊建议。

遇到题面排除项，只在 `uncertainty` 中记一行“超出范围，未审查”，不产出正式问题条目。

---

## 2. 触发与不触发

### 触发

- 输入包含论文、稿件、预印本、研究报告等科研材料，且任务要求审查、审稿、评审、逻辑审查、论证审查、claim verification、事实核验、引用核查、方法审查、统计审查、章节一致性检查。
- `case.json` 中 topic、task、output_contract 涉及 review、audit、argument、evidence、claim、论文质量、审稿。

### 不触发

- 仅要求润色、翻译、摘要、改写、投稿建议。
- 输入完全不是科研文本，例如纯数据表、纯图片、纯代码且无审查要求。

证据不足不是“不触发”。照常运行，输出 `status: partial` 或 `insufficient_evidence`。

---

## 3. 输入、工作目录与最终产物

### 输入

- `/input/case.json`：可能包含 `case_id`、`task`、`output_contract`、材料路径或说明。
- `/input/task.md`：题面任务说明。
- `/input/**`：实际科研材料，如 PDF、DOCX、TXT、MD、LaTeX、BIB、RIS、CSV、JSON。
- 实际论文文本是唯一事实依据。PDF 解析必须读取真实 PDF 文本层，不得使用预先生成的答案层。

### 工作目录

- `/app/work`：所有中间产物、台账、候选线索、draft、锁文件、临时解析结果。
- Agent 可读写此目录。

### 最终输出

- `/app/output`：最终交付物。
- 必需交付：

| 文件 | 作用 |
|-|-|
| `result.json` | 结构化总结果，含完整契约字段、问题清单、来源、状态、不确定性、变更记录 |
| `review_report.md` | 人可读的最终审查报告 |
| `issues.csv` | 问题清单表格，便于复算与筛选 |
| `claims.csv` | 主张清单，含说话人、限定条件、支撑证据与强度判断 |
| `evidence_table.json` | 主张—证据逐条对齐表 |
| `audit_digest.md` | 限长阅读摘要与逐句定位索引 |
| `pending_human.md` | 无法确认、材料缺失、需人工复核项 |
| `SELFTEST.md` | 自检清单与本次自检结果 |
| `selfcheck.json` | 结构化自检记录 |

如果 `output_contract` 要求额外可编辑产物，必须按契约字段生成对应文件；若要求 Office、幻灯片、图形等，还必须生成真实渲染 PDF/PNG 预览。

---

## 4. `audit.py` 三个阶段做了什么

### init

- 扫描 `/input`，读取 `case.json` 与 `task.md`。
- 解析材料文件类型，按实际内容生成来源编号 `S#`。
- 抽取章节、段落、句子，生成稳定 `sentence_id`、`locator`、字符区间。
- 生成候选线索、冲突分组、材料清单、解析降级记录。
- 写 `/app/work/ledger.json`、`/app/work/digest.md`、`/app/work/candidates.json`。
- 立即写合法 partial `/app/output/result.json`。

### build

- 若 `/app/work/draft.json` 存在，以 Agent 判断为主。
- 若 `/app/work/draft.json` 不存在，使用 `init` 台账做确定性兜底抽取，生成实质工作稿；每条必须有逐字 quote 与 locator。
- 将所有判断落成最终契约文件：
  - `result.json`
  - `review_report.md`
  - `issues.csv`
  - `claims.csv`
  - `evidence_table.json`
- 自动写入 `AUTO_EXTRACT` 到 `gaps` 或 `degradations`，诚实说明哪些内容来自规则兜底，哪些经过 Agent 裁定。
- 不因缺少 draft 失败。

### selfcheck

- 核对 `output_contract` 字段与磁盘文件是否一一对应。
- 核对 `result.json` 顶层与 nested `output_contract` 是否双回显。
- 核对每条 issue / claim 是否具备必要的 quote、locator、severity、类型、来源。
- 生成 `SELFTEST.md` 与 `selfcheck.json`。
- 自检失败项写入 `degradations`，不静默降级。

---

## 5. Agent-first 双路径

### 路径 A：Agent 判断路径（优先）

1. 运行 `main.py init` 或 `audit.py run` 获得台账、阅读摘要、候选线索。
2. 真实阅读 `audit_digest.md` 与关键原文片段，不依据候选线索直接当结论。
3. 把确认问题、否决候选、核验记录写入 `/app/work/draft.json`。
4. 运行 `main.py build`，生成最终产物。
5. 运行 `main.py selfcheck`。

`draft.json` 的最小可读形状推荐如下，完整字段说明见 `references/guide.md`：

```json
{
  "case_id": "case_...",
  "auto_extract": false,
  "findings": [
    {
      "id": "F001",
      "type": "argument",
      "severity": "major",
      "source_id": "S1",
      "locator": {
        "section": "Discussion",
        "paragraph": 4,
        "sentence_id": "S0123",
        "char_start": 1400,
        "char_end": 1550,
        "page": null
      },
      "quote": "逐字摘录的原文句子片段",
      "reason": "判断依据，说明违反什么原则，并引用第二处证据位置",
      "suggestion": "可执行修改建议：补什么证据、改哪个词、降哪一档结论强度",
      "evidence": [
        {
          "source_id": "S1",
          "quote": "第二处原文证据",
          "locator_text": "§Results ¶2 S0050"
        }
      ],
      "speaker": "author",
      "confidence": "high",
      "basis": "agent"
    }
  ],
  "rejected_candidates": [
    {
      "candidate_id": "C001",
      "rule": "result_direction_mismatch",
      "sid": "S0123",
      "reason": "作者已声明为假设情形，且结论未超出该限定"
    }
  ],
  "checks": {
    "factual": "done",
    "citation": "done",
    "method": "done",
    "statistics": "done",
    "argument": "done",
    "compliance": "done"
  }
}
```

### 路径 B：确定性兜底路径

若 Agent 未写 `draft.json`，`build` 必须完成：

- 从 `candidates.json` 中抽取硬候选。
- 逐字回填 quote 与 locator。
- 生成 `issues`、`claims`、`checks`、`evidence_table`。
- 在 `result.json` 中写入 `basis: "deterministic_rule"` 或 `"AUTO_EXTRACT"`。
- 在 `degradations` 中写明：
  - 哪些结果未经 Agent 人工裁定。
  - 哪些候选因 quote 无法逐字命中而进入 `pending_human`。
  - 哪些检查项仅完成结构级检查。

两种路径必须产出同一套产物结构和同一份 `result.json` 契约。区别只在 `basis`、`auto_extract`、`degradations` 的诚实记录。

---

## 6. 六类检查项

所有检查项在 `result.json` 的 `checks` 字段中必须出现，且状态只能为：

- `done`：已真实检查。
- `partial`：部分检查，受限原因写入 `degradations`。
- `not_applicable`：不适用，必须写出原因。
- `unreviewed`：应检但未完成，原因写入 `degradations`。

| key | 检查内容 | 典型问题 | 最小证据要求 |
|-|-|-|-|
| `factual` | 事实、数值、单位、术语、前后自洽 | 同一变量前后数值不一致；摘要数字正文追不到；单位量纲错；结论与自家数据方向相反 | 至少两处逐字 quote + locator |
| `citation` | 引用支持与编号完整 | 引用编号超出文献表；条目从未被引；引文不支持该句 | 断言 quote + 对应文献条目 |
| `method` | 研究设计能否回答研究问题 | 无对照或对照不含关键变量；样本量与结论外推范围不匹配；研究终点与假设不匹配；涉人/动物缺伦理声明 | 方法段 quote + 结论段 quote |
| `statistics` | 统计报告充分性 | “显著”无检验名；`p=0.000`；`±` 未标明 SD/SE；多重比较未校正；百分比无分母 | 该句 quote + 方法/图注 quote |
| `argument` | 推理链、因果措辞、结论强度 | 相关设计写因果；结论超出数据；以偏概全；替代解释未排除；引言承诺未交付 | 前提 quote + 结论 quote |
| `compliance` | 规范与可复现 | 占位符未清；缺数据/代码可得性；缺利益冲突/资助；样本量未报告 | 该处 quote |

实施细则、检出清单、误报防线、严重度锚点、规则表见 `references/checks.md`。

---

## 7. 五步裁定法

顺序不可换：

1. **抽主张**：从摘要、引言、结果、讨论、结论中抽取核心主张，记录物种、样本、剂量、时间窗、人群等限定条件，以及说话人类型。
2. **配证据**：对每条主张标记 `own_data`、`citation`、`assumption` 或 `none`。
3. **验强度**：相关设计写因果、横断面写预测、小样本写普适、单物种写类群、体外写体内、单时点写长期，均需降强度或补证据。
4. **查链条**：找前提到结论的断点：隐含假设未声明、替代解释未排除、对照不含关键变量、剂量/时间窗不匹配、混淆未控制。
5. **查衔接**：摘要数字是否正文可追；引言承诺是否交付；方法/结果样本量、分组、单位、终点是否同口径；图表编号与正文引用是否对应。

---

## 8. 误报防线

正确性得分很大程度取决于“少报不成立条目”。以下情形不得误报：

1. 有意设置的对照组、阴性对照、空白组。
2. 明确标注的假设、简化或近似，除非被当作结论使用。
3. 转述他人观点：`reported by / according to / 据……报道` 且有引用，责任在被引文献，只有引文明显不支持时归入 `citation`。
4. 已在 Limitations 中声明的局限，不重复报；只报“声明了但结论未收敛”。
5. 学科惯例：`p<0.001`、生态学使用 SE、质性研究不做 p 值，不轻易判缺陷。
6. 语法、拼写、期刊排版、文献格式不报。
7. 舍入差异不报，除非无法用舍入、分组或时间点解释。
8. 同一根因只报一次，多条证据合并到 `evidence[]`，不按句刷条数。

被否决的机器候选不删除，写入 `rejected_candidates`，用于证明误报控制能力。

---

## 9. 严重度与可执行建议

| severity | 判据，满足任一 | 含义 |
|-|-|-|
| `blocker` | 主结论不成立；结论方向与数据相反；研究设计无法回答研究问题 | 必须修，否则结论不成立 |
| `major` | 影响结论强度、外推边界或可复现性；补证据或降强度可修 | 必须修 |
| `minor` | 局部、不伤主结论，改一句或补一项即可 | 建议修 |
| `suggestion` | 提升清晰度或规范性，不改变结论 | 可选 |

每条问题必须有 `severity_basis`，至少写明三点：

- `affects_main_conclusion`：是否影响主结论。
- `fixable_by`：补什么证据、改哪句、删哪个词、降哪档强度。
- `affects_reproducibility`：是否影响可复现性。

`severity_basis` 也要写入 `reason` 或独立字段中。

`suggestion` 必须可执行。禁止出现：

- “建议补充论证”
- “建议加强逻辑”
- “建议进一步分析”

应写成：

- “将‘证明 A 导致 B’改为‘A 与 B 相关’，或在方法中补充纵向前瞻设计。”
- “在 Statistical analysis 段补充 Welch’s t-test 与效应量；报告 `n=X` 及 95% CI。”
- “将摘要的 OR=2.1 在 Results §3 中给出对应表号，否则删除或标记待核。”

---

## 10. 定位与逐字引用

- 每条问题必须有 `locator`：
  - `source_id`
  - `section`
  - `paragraph`
  - `sentence_id`
  - `char_start`
  - `char_end`
  - `page`，不可靠时为 `null`
  - 人读串 `locator_text`，例如：
    `§Discussion ¶4 S0123 p.5 chars 1400-1550`
- 每条问题必须有 `quote`，逐字来自原文，不改写、不拼接、不翻译、不补字。
- 正常 quote 长度为 8–400 字符；数字、编号、单位类问题可以更短。
- 若只给 `sentence_id`，脚本会自动回填 quote 与 locator；若 `sentence_id` 与 quote 冲突，以逐字匹配为准，并写入 `review_records.locator_corrections`。
- 引不到逐字原文时，不得进入正式 `issues`，改入 `pending_human`。
- 页码只在 PDF 内容流页数与 `/Type /Page` 数可靠一致时给出，否则为 `null`；不猜页码、不猜图号。

每条问题还必须写 `reason`：说明违反了什么原则、依赖哪几处原文位置，使复核者能独立验证。

---

## 11. 材料与异常处理

| 情形 | 识别 | 处置 | 退出码 |
|-|-|-|-|
| `/input` 不存在或为空 | 目录缺失或无文件 | `status=input_error`，`errors` 记录；仍写合法 partial `result.json` | 0 |
| `case.json` 非法 JSON | 解析异常 | `errors` 记录；按目录继续；`output_contract={}` 并说明无法回填 | 0 |
| 扫描版 PDF 无文本层 | 无可解码文本层；文本少于 200 字符 | `degradations` 记“需 OCR”；该源只做结构级检查；`pending_human` 记人工/OCR | 0 |
| PDF 文本乱码 | 解码失败或可读率极低 | 同上，不做逐字断言 | 0 |
| 超长稿，超过约 400k 字符 | 长度阈值 | 截断并记 `degradations`；`unreviewed` 写明未覆盖区间；不得声称审完全文 | 0 |
| 章节标题缺失 | 识别不到章节 | 全文归 `Front`，继续切句；说明这是解析限制，不直接判作者缺陷 | 0 |
| 文献表缺失或不可解析 | 无 References 段 | `checks.citation=partial`；`uncertainty` 记“无文献表，仅查文内编号连续性” | 0 |
| 图表文件缺失 | 正文引用图表但无文件 | `uncertainty` 记录；不进正式 `issues` | 0 |
| 单文件解析失败 | 异常捕获 | 只降级该源，其余继续；`degradations` 记录 | 0 |
| `draft.json` 未写或为空 | build 阶段无 Agent 判断 | 确定性规则兜底；`basis=AUTO_EXTRACT`；`degradations` 说明 | 0 |
| `output_contract` 与结果字段同名冲突 | 键名重叠 | 以真实结果填充；不编造；`coverage_note` 说明 | 0 |

所有异常都必须：

- 写入 `errors` 或 `degradations`。
- 保留已完成产物。
- 退出码保持 0。
- 不得伪装成完整成功。

---

## 12. 预算策略

官方预算：64 次模型请求、900 秒、单次响应 16384 tokens 含 reasoning。

推荐分配：

| 阶段 | 请求数 | 说明 |
|-:|-:|-|
| 运行 `audit.py run` 或 `init` | 1–2 | 脚本毫秒级完成，先拿完整基线 |
| 读台账、摘要、原文片段 | 3–8 | 优先读 `audit_digest.md`，按需点读高价值片段 |
| 写 `draft.json` | 3–6 | 每条确认问题写清证据、讲话人、严重度 |
| 运行 build / selfcheck | 2–3 | 定稿与自检 |
| 补充核验 | 3–8 | 对不确定条目、高价值候选、跨章节冲突点再核验 |
| 异常处理与收尾 | 2–5 | 补 pending_human、degradations、自检 |
| 保留余量 | 5–10 | 防止重复运行或补查 |

时间铁律：

- 当运行时间接近 780 秒，立即停止扩展阅读，运行 `build` 与 `selfcheck`。
- 若 draft 未完成，保留脚本兜底候选，标注 `basis=AUTO_EXTRACT`。
- 先落盘、退出码 0、不静默降级。

---

## 13. `result.json` 契约

最终 `result.json` 必须包含：

- `case_id`
- `status`
- `summary`
- `issues[]`
- `candidate_issues[]`
- `claims[]`
- `evidence_table`
- `checks{}`
- `review_records`
- `sources[]`
- `uncertainty[]`
- `pending_human[]`
- `errors[]`
- `degradations[]`
- `changes[]`
- `runtime`
- `artifacts`
- `output_contract`

### 双回显

- `output_contract` 的每个字段在 `result.json` 顶层出现一次。
- `output_contract` 内部也必须完整保留原字段。
- 例如题面要求 `review_report`、`issues_table`、`claims`、`evidence_table`，则顶层也要有对应字段名。

### 状态

`status` 只使用以下值：

- `success`：完整完成。
- `partial`：遇到限制但已可交付部分成果。
- `insufficient_evidence`：输入材料不足，无法形成充分审查。
- `input_error`：输入错误或缺失。
- `failed`：关键步骤失败，但已保留 partial 产物。

当 `status` 不是 `success` 时，必须注明缺少什么、影响哪些结论、下一步可如何补做。

---

## 14. 自检清单

结束前必须逐项确认：

1. `audit.py run` 已执行并退出码 0。
2. `result.json` 可被 JSON 解析。
3. `case_id` 存在。
4. `output_contract` 在顶层与 nested 中双回显。
5. `issues[]` 至少含字段：`id`、`type`、`severity`、`source_id`、`locator`、`quote`、`reason`、`suggestion`、`evidence`、`basis`。
6. 每条 `quote` 逐字命中原文。
7. 每条 issue 的 locator 精确到句子或字符区间。
8. `checks{}` 六个键全部存在且状态合法。
9. `claims[]` 非空，包含说话人、限定条件、支撑证据与强度判断。
10. `sources[]` 来自实际扫描到的材料。
11. `errors`、`degradations`、`uncertainty`、`pending_human` 不是空头字段；有则写实，无则写原因。
12. `review_report.md` 与 `result.json` 保持一致。
13. `issues.csv` 与 `issues[]` 行序、编号一致。
14. 没有出现“建议补充论证”“建议加强逻辑”等空泛建议。
15. 没有把暗示、假设、转述他人观点误报为作者缺陷。
16. 如果做了 Agent draft，`rejected_candidates` 已记录否决理由。
17. 如果没做 Agent draft，`degradations` 已注明 `AUTO_EXTRACT`。
18. `SELFTEST.md` 与 `selfcheck.json` 已生成。

---

## 15. 生态资源

本 Skill 附带以下资源，供评审与复用：

| 文件 | 内容 |
|-|-|
| `SKILL.md` | 本文档，总体规则、调用方式、工作流、异常处理 |
| `references/guide.md` | `draft.json` 形状、工作流说明、Agent 双路径示例 |
| `references/checks.md` | 六类检查细则、确定性规则、严重度锚点、误报防线 |
| `references/schema.md` | `result.json`、`evidence_table.json`、`issues.csv` 字段定义 |
| `references/examples.md` | 最小调用示例与示意输出；所有示例必须标为 example |
| `SELFTEST.md` | 自检清单模板与预期输出 |
| `environment/resources.yaml` | 预装依赖声明：Python >=3.8、纯标准库、离线运行 |
| `scripts/audit.py` | 单命令入口：init/build/selfcheck 与 run 包装 |
| `scripts/audit.py` | 材料解析、分段、切句、候选抽取 |
| `scripts/verify.py` | quote 校验、locator 回填、去重、严重度归一、渲染定稿 |

所有脚本：

- 只使用 Python 3.8+ 标准库。
- 不联网。
- 不依赖 CWD；用 `Path(__file__).resolve().parent` 定位自身与资源。
- 同输入同输出，保证重复运行确定性。
- 文件数量不超过 50，单个 UTF-8 文本文件不超过 500KB，总文本资源不超过 2MB。

---

## 16. 最终行为摘要

对每篇论文，本 Skill 必须产出一个可独立复核的审查包：

- 每条问题真实、可定位、有逐字摘录、有类型、有严重度、有可执行改法。
- 每条判断能追溯到原文的某一句话，而不是章节名或读后感。
- 明确区分事实错误、证据不足、规范问题、建议性意见。
- 明确区分作者主张、引用他人观点、假设情形。
- 不确认的材料缺口进入 `pending_human`，不伪装成结论。
- 脚本基线保证无需 Agent 也能跑出完整结构。
- Agent 增量判断在同样的产品结构中写入，提高真实性与精细度。
- 所有限制、失败、降级、待复核都显式记录，不静默。