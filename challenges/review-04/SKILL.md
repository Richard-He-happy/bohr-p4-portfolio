---
name: paper-argument-audit
description: Audit a research manuscript's argument and evidence chain and return a locatable, quotable, severity-graded review. Use when the task asks to review, peer-review, critique or 审查/审稿 a paper or manuscript; to check claims against evidence, citations, methods, statistics or cross-section consistency; or to produce issues with verbatim quotes, sentence-level locators and actionable revision advice. Emits result.json, review_report.md and issues.csv.
version: 1.1.0
license: MIT
---

# paper-argument-audit — 论文逻辑与论证审查

本 Skill 把一篇稿件变成**可复核的审查意见**：每条问题都有类别、严重度、精确定位、逐字原文、判断依据和可执行改法；六类检查显式跑过；材料缺口单列，既不当作者缺陷，也不把“没审到”写成“没问题”。

**铁律：本包内的脚本只是工具，最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、候选线索或模板直接当成品。你必须先运行脚本产出完整基线，再在其上亲自核验、增补、改写，并保留全部基线产物。

## 1. 用途与边界

**做**：主张抽取；主张—证据对齐；推理链断点；章节衔接（摘要↔正文、引言承诺↔结果交付、方法口径↔结果口径、图表↔正文）；统计报告充分性；引用支持与编号完整性；学术规范；严重度分级与改法。

**不做**（题面排除项，越界即扣分）：文字润色与语言表达、查重与学术不端判定、参考文献**格式**排版（APA/Vancouver）、原始数据重分析与统计复算、投稿策略与选刊。遇到时只在 `uncertainty` 记一行“超出范围，未审查”，不产出条目。

## 2. 触发与不触发

- 触发：输入含论文/稿件（PDF/DOCX/MD/TXT/LaTeX）+ 审查要求；或 `case.json` 的 topic/task 涉及 review、审稿、评审、逻辑审查、claim verification。
- 不触发：只要润色/翻译/摘要/投稿建议；或输入不是稿件（纯数据、纯作图）。
- 证据不足不是“不触发”：照常运行并给 `status: partial` 或 `insufficient_evidence`。

## 3. 运行时契约

| 项 | 值 |
|-|-|
| 入口 | 本文件；`scripts/audit.py`（解析与脚手架）、`scripts/verify.py`（校验与定稿） |
| 输入 | `/input/case.json`（可缺）+ `/input/**` 材料（PDF/DOCX/TXT/MD/LaTeX/CSV/JSON/BIB/RIS…） |
| 工作目录 | `/app/work`；中间文件写此处 |
| 最终输出 | `/app/output`；必需 `result.json`、`review_report.md`、`issues.csv`；辅助 `audit_digest.md`、`issues_draft.json`、`.audit/index.json` |
| 可编辑产物 | 本题默认输出 markdown/csv；若 `output_contract` 要求 Office/幻灯片/图形，必须额外生成真实渲染的 PDF/PNG 预览 |
| 依赖 | Python ≥3.8 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位自身） |
| 退出码 | 两个脚本恒为 0；异常写入 `errors`/`degradations`/`pending_human` |
| 首写 | `audit.py` 第一步即写合法 partial `result.json`，之后才做重活 |

`$SKILL` = Skill 安装目录（评测时 `/skills/weekly-skill`）；若不存在用本文件所在目录。

## 4. 执行流程（六步）

### 步骤 1：盘点输入
- **输入**：`/input` 目录。
- **动作**：读 `/input/case.json`（缺失或坏 JSON 则递归找 `**/case*.json`，仍失败按目录扫描继续）；读 `/input/task.md`；扫描 `/input/**` 所有材料文件，按扩展名与魔数识别类型；保存 `case_id` 与 `output_contract` 原样透传（键名不改、未知字段保留），其每个键在顶层也出现。
- **输出**：输入清单、`case_id`、`output_contract`、材料列表。
- **失败分支**：`/input` 不存在或空 → `status=input_error`，`errors` 记，仍写合法 partial `result.json`；`case.json` 非法 → 记 `errors`，按目录继续，`output_contract={}` 并说明无法回填。

### 步骤 2：真实解析材料
- **输入**：步骤 1 定位到的材料文件。
- **动作**：运行
  ```bash
  python3 -B $SKILL/scripts/audit.py --input /input --output /app/output
  ```
  该脚本真实解析 PDF 文本层（FlateDecode 内容流）、DOCX `word/document.xml`、TXT/MD/LaTeX/CSV 等；切句生成稳定 `sid`、章节、段落、页码（仅在页数可靠时）和字符区间；产出确定性候选线索与阅读摘要。**你不得依据文件名或领域标签猜测内容；凡脚本解析不出的对象一律进入 `uncertainty`/`pending_human`，不构造像素、图注、数据或文献细节。**
- **输出**：`partial result.json`（已合法可交）、`audit_digest.md`、`.audit/index.json`、`result.json.candidate_issues`。
- **失败分支**：扫描版 PDF 无文本层 / 文本乱码 / 超长截断等 → 脚本自动降级并记 `degradations`/`pending_human`；你仍需继续后续步骤，但只做可支持的结构级检查，不得声称审完全文。

### 步骤 3：构建 / 核对证据
- **输入**：`audit_digest.md`（已压缩的限长摘要，默认 60000 字符，含逐句清单）、`.audit/index.json` 详情、必要时点读原文片段。
- **动作**：按第 9 节五步裁定法、第 10 节六类检查项、第 11 节误报防线，**由你亲自**：抽主张、配证据、验强度、查推理链、查章节衔接；核验每条问题是否真实存在、quote 是否逐字命中、定位是否精确到句/段/字符、严重度判据是否成立；把确认问题写入 `/app/output/issues_draft.json`，否决的候选线索写入 `rejected_candidates` 并给否决理由。
- **输出**：`issues_draft.json`（确认问题与否决记录）。
- **失败分支**：若时间或请求预算不足（见第 6 节预算策略），跳过本步，保留候选线索并标 `basis: deterministic_rule`；不确定的条目进 `pending_human`；不得伪造裁定。

### 步骤 4：产出完整成品
- **输入**：步骤 3 的 `issues_draft.json`（或步骤 2 的候选线索）。
- **动作**：运行
  ```bash
  python3 -B $SKILL/scripts/verify.py --input /input --output /app/output
  ```
  该脚本逐字校验 quote、回填 locator、归一类别/严重度、去重、按严重度+位置确定性编号、生成 `result.json`、`review_report.md`、`issues.csv`；若你补写了更多确认问题，必须写进 `issues_draft.json` 后再跑定稿。
- **输出**：最终 `result.json`、`review_report.md`、`issues.csv`。
- **失败分支**：若 `issues_draft.json` 未写/为空，脚本用确定性规则兜底（`basis: deterministic_rule`）并在 `degradations` 说明，你仍需保留基线产物；若脚本异常，手动补齐 `result.json` 必需字段，不得删除基线。

### 步骤 5：自检 rubric
- **输入**：最终产物。
- **动作**：按第 8 节 rubric 对照表、第 17 节自检清单逐项核对；缺任何 output_contract 字段或文件先补齐。
- **输出**：自检通过或待补清单。
- **失败分支**：发现缺失或占位符 → 立即补写；若无法补，在 `degradations` 明确列出缺失项，状态改为 `partial`。

### 步骤 6：回填 result.json
- **输入**：最终产物。
- **动作**：确认 `result.json` 包含 `case_id`、`status`、`summary`、`issues[]`、`candidate_issues[]`、`claims[]`、`checks{}`（六键）、`review_records`、`sources[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`、`artifacts`、`output_contract` 全部字段；`output_contract` 的每个键在顶层与 `output_contract` 内都存在；逐字核验关键数字、引用、统计量，把核验结果写进 `review_records`（verified / pending_human / conflicts）。
- **输出**：合法 `result.json`。
- **失败分支**：字段冲突以真实结果填，不编造；`coverage_note` 说明冲突；退出码仍 0。

## 5. 脚本实际做了什么

| 阶段 | 行为 | 产物 |
|-|-|-|
| parse | PDF 取 FlateDecode 内容流的文本层（平衡括号扫描，含十六进制串）；DOCX 解 `word/document.xml`；其余按纯文本读（utf-8/gb18030/latin-1）。二进制表/图不解码 | `degradations`、`uncertainty` |
| segment | 章节标题（Markdown `#`、编号、LaTeX `\section{…}`、中英文章节名）→ 空行分段 → 切句（带缩写与小数字保护）；每句一个稳定 `sid` + 章节 + 段号 + 页 + 字符区间 | `.audit/index.json` |
| leads | 确定性规则产出**未裁定线索**（带 `rule`、`sid`、逐字 `quote`、`hard` 标记），清单见 `references/checks.md` 第 8 节 | `audit_digest.md`、`result.json.candidate_issues` |
| digest | 限长阅读摘要（默认 60000 字符）：章节大纲 + 线索 + 逐句清单（`S0001 §Results ¶3 p.5 \| 原文`） | `audit_digest.md` |
| finalize | 逐字校验每条 quote；回填 locator；归一类别/严重度；去重；按严重度+位置确定性编号；生成报告与 CSV | `result.json`、`review_report.md`、`issues.csv` |

跨运行确定性：同输入 → 同 `sid`、同 `R##`、同 CSV 行序。

## 6. 预算策略（64 次模型请求 / 900 秒 / 单次响应 16384 tokens）

- 步骤 1–2（脚本运行）：耗时毫秒级，最多 2 次模型请求（读输入清单与运行脚本）。
- 步骤 3（Agent 亲自阅读与裁定）：核心消耗，分配 **20–30 次请求**。优先读 `audit_digest.md`，只对高价值候选或需要逐字核验处用 `Read`/`Grep` 点读 `.audit/index.json` 或原文片段；六类检查至少各抽 1–3 条真实证据。
- 步骤 4（定稿）：分配 2–3 次请求。
- 步骤 5–6（自检与回填）：分配 3–5 次请求。
- 保留 5–10 次请求处理异常或补查。
- **到 780 秒立即停手并运行 `verify.py` 定稿；如果步骤 3 未完成，保留脚本候选线索并标注 `basis: deterministic_rule`，不得再继续阅读。**
- 三条铁律：**先落盘、退出码 0、不静默降级**。

## 7. 隐藏案例鲁棒性

| 情形 | 识别 | 处置（写到哪） | 退出码 |
|-|-|-|-|
| `/input` 不存在或空 | 目录缺失/无文件 | `status=input_error`，`errors` 记；仍写合法 partial；不编造 | 0 |
| `case.json` 非法 JSON | 解析异常 | `errors` 记，按目录继续；`output_contract={}` 并说明无法回填 | 0 |
| 扫描版 PDF 无文本层 | 无可解码内容流；文本 < 200 字符 | `degradations` 记“需 OCR”；该源只做结构级检查；`pending_human` 记需人工/OCR | 0 |
| PDF 文本乱码（CID 字体） | 十六进制串解码失败/可读率低 | 同上，不据此做逐字断言 | 0 |
| 超长稿（> 400k 字符） | 长度阈值 | 截断并记 `degradations`；`checks.*.unreviewed` 写未覆盖区间；**不得声称审完全文** | 0 |
| 章节标题缺失 | 识别不到章节 | 全文归 `Front` 并照常切句；`compliance` note 说明（不直接判缺陷） | 0 |
| 文献表缺失/不可解析 | 无 References 段 | `citation` 记 partial，`uncertainty` 记“无文献表，仅查文内编号连续性” | 0 |
| 图表文件缺失 | 正文引用图表但无对应文件 | `uncertainty` 记；不进 `issues`（材料缺口 ≠ 作者缺陷） | 0 |
| 单文件解析失败 | 异常捕获 | 只降级该源，其余照常；`degradations` 记 | 0 |
| `issues_draft.json` 未写/为空 | 步骤 3 未做 | 确定性规则兜底（`basis: deterministic_rule`）+ `degradations` 说明 | 0 |
| 契约字段与结果同名冲突 | 键名重叠 | 以真实结果填；不编造；`coverage_note` 说明 | 0 |

任何情况下：**都必须产出合法 `result.json`**（可 `json.load`，含 `case_id` 与 `output_contract` 字段），退出码为 0；无法判断的材料缺口写 `pending_human`，不得凭空补齐。

## 8. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果 | 40 | | |
| ↳ 任务完成度 | 15 | 产出带位置、类型、严重度和修改建议的问题清单，覆盖论点、证据、推理链与章节衔接 | `issues[]` 字段完整；`checks{}` 六类全部有 status；`claims[]` 非空 |
| ↳ 结果正确性 | 15 | 报出的问题真实成立，原文摘录与论文一致，不误判有意的对照、明确假设或转述他人观点 | `issues[].quote` 逐字命中；`rejected_candidates` 记录否决理由；`review_records` 记录核验结果 |
| ↳ 结果完整性 | 5 | 覆盖事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类检查项，以及跨章节主张—证据对应 | `checks{}` 六键齐全；`claims[]` 含限定条件与说话人；`review_records` 记录跨章节对应关系 |
| ↳ 结果可核验性 | 5 | 定位粒度、原文摘录与判断依据能被独立复核 | 每条 `locator_text` 精确到 sentence_id/字符区间；`quote` 可检索；`reason` 写明依赖位置 |
| 使用增益 | 25 | | |
| ↳ 质量增益 | 15 | 相比基础 Agent 稳定多发现真实问题、少报不成立条目 | 本 Skill 的规则预检 + Agent 亲自裁定 + 误报防线；实际运行由平台对照，本包不自称分数 |
| ↳ 效率增益 | 5 | 减少人工通读、逐句定位和重写建议的条目数 | `locator` 精确到句/字符；`suggestion` 可执行具体到句子、词汇、证据 |
| ↳ 增益可验证性 | 5 | 通过公平对照证明质量或效率改善 | 平台比较基础 Agent 与 Skill Agent 的运行记录；本包提供可复跑命令与 `rejected_candidates` 作为误报控制证据 |
| 创新增益 | 15 | | |
| ↳ 新增能力 | 5 | 主张—证据逐条对齐、跨章节一致性检查、可解释的严重度分级 | `claims[]` + `evidence[]`；`checks.argument` 跨章节；`severity_basis` 三句判据 |
| ↳ 方法改进 | 5 | 主张抽取、证据比对、跨段核查与严重度判据带来实质改进 | 五步裁定法（第 9 节）+ 六类检查细则（`references/checks.md`） |
| ↳ 创新证据 | 5 | 证明新增方法相对已有方案的边界和价值 | 文档说明方法边界；`review_records` 中的核验与纠偏记录，不伪造 |
| 可靠体验 | 10 | | |
| ↳ 调用与易用性 | 3 | 正确触发，按说明对新论文完成审查 | 第 4 节六步流程；单命令可跑通 |
| ↳ 运行稳定性 | 4 | 不同学科、不同长度论文、重复运行稳定可用 | 解析与定位确定性（同输入同 `sid`/`R##`）；异常降级分支表（第 7 节） |
| ↳ 异常处理 | 3 | 解析失败、扫描版无文本、超长截断、引用无法获取、章节缺失等识别与处置 | 第 7 节鲁棒性表；`degradations`/`pending_human`/`uncertainty` 实际字段 |
| 生态贡献 | 10 | | |
| ↳ 文档完整性 | 3 | 输入要求、输出字段、严重度标准、配置、示例、适用范围、限制和维护信息齐全 | 本文件 + `references/schema.md` + `references/checks.md` + `references/examples.md` |
| ↳ 资源可复用性 | 4 | 题集、审查清单、标注模板、报告模板与脚本可被复用和复跑 | `scripts/audit.py`、`scripts/verify.py`；规则表、模板、示例文件 |
| ↳ 分享推广价值 | 3 | 沉淀可分享的审查案例、清单、经验与真实应用价值 | 示例（非正式案例结果）与好/坏条目对照；文档说明适用于不同学科与限制 |

## 9. 裁定方法（五步，顺序不可换）

1. **抽主张**：从摘要/引言/结果/讨论/结论抽核心主张，记限定条件（物种、样本、剂量、时间窗、人群）与说话人（作者主张/引用他人观点/假设情形/背景共识）。`verify.py` 把 `claims[]` 落进结果。
2. **配证据**：`own_data`（本文数据、图表、统计量）/`citation`（编号或作者-年）/`assumption`（明确假设推演）/`none`。`none` 且落在结果/结论段 = 高强度候选断点。
3. **验强度**：相关设计写因果；横断面写预测；n 小写普适；单物种写类群；体外写体内；单时点写长期——都要降强度或补证据。
4. **查链条**：前提→结论缺哪一环（隐含假设未声明、替代解释未排除、对照不含关键变量、剂量/时间窗不匹配、混淆未控）。
5. **查衔接**：摘要数字是否正文可追；引言承诺的分析是否交付；方法与结果的样本量/分组/单位/终点是否同口径；图表编号与正文引用是否对应。

## 10. 六类检查项（每类必须给 status，不适用写 `not_applicable` + 原因）

| key | 检查内容 | 典型检出 | 需要的证据 |
|-|-|-|-|
| `factual` | 事实/数值/单位/术语自洽 | 同一量前后数值不一致；单位量纲错；摘要数与正文不符；结论与自家数据方向相反 | 两处 quote + 各自 locator |
| `citation` | 引用支持与编号完整 | 编号超出文献表；条目从未被引；引用不支持该句 | 断言 quote + 文献条目 |
| `method` | 设计能否回答研究问题 | 无对照/对照不含关键变量；样本量与结论范围不匹配；终点与假设不匹配；涉人/动物缺伦理声明 | 方法段 quote + 结论段 quote |
| `statistics` | 统计报告充分性 | “显著”无检验名；`p = 0.000`；`±` 未标 SD/SE；多重比较未校正；百分比无分母 | 该句 quote + 方法段 quote |
| `argument` | 推理链与强度 | 结论超出数据；相关当因果；以偏概全；替代解释未排除；承诺未交付 | 前提 quote + 结论 quote |
| `compliance` | 规范与可复现 | 占位符未清；缺数据/代码可得性；缺利益冲突/资助；样本量未报告 | 该处 quote |

细则（检出清单、误报防线、严重度锚点、规则表）见 `references/checks.md`。

## 11. 误报防线（正确性得分的主要来源，提交前逐条自查）

1. **有意设置的对照**：作者写明 control/阴性对照/空白组 → 不报“分组不合理”。
2. **明确标注的假设/简化**：`assume/for simplicity/近似/为简化` → 是条件推演，不是缺证据（除非被当结论用）。
3. **转述他人观点**：`reported by/according to/据…报道` + 引用 → 责任在被引文献；只有引用不支持才归 `citation`。
4. **已声明的局限**：Limitations 写了就不重复报；只报“声明了但结论没收敛”（需两句 quote）。
5. **学科惯例**：临床常用 p<0.001、生态学用 SE、质性研究不用 p → 不算缺陷；不确定进 `pending_human`。
6. **格式与表达**：语法、拼写、期刊排版不报（越界）。
7. **舍入**：`12.3%` vs `12.34%` 不报；只报无法用舍入/分组/时间点解释的差异。
8. **一句一条**：同根因只报一次，关联证据放 `evidence[]`，不按句刷条数。

被否决的机器线索不必删：写进 `issues_draft.json.rejected_candidates`（`sid + rule + 否决理由`），这是误报控制证据。

## 12. 严重度与改法

| severity | 判据（满足任一） | 处置含义 |
|-|-|-|
| `blocker` | 主结论不成立；结论方向与数据相反；方法无法回答研究问题 | 必须修，否则结论不成立 |
| `major` | 影响结论强度/外推边界/可复现性；补证据或降强度可修 | 必须修 |
| `minor` | 局部、不影响主结论，改一句或补一项即可 | 建议修 |
| `suggestion` | 提升清晰度/规范性，不改结论 | 可选 |

`severity_basis` 三句填：`affects_main_conclusion` / `fixable_by` / `affects_reproducibility`。全条同档视为失准——`verify.py` 在单档占比 >80% 时记 `degradations`。

`suggestion` 必须可执行：补什么证据、改哪一句、把哪个词换成什么、把强度降到哪一档。禁止“建议补充论证”“建议加强逻辑”。

## 13. 定位与引用规范

- 每条问题有 `locator`：`{section, paragraph, sentence_id, page, char_start, char_end, source_id}` + 人读串 `locator_text`（`§Discussion ¶10 S0020 p.5 chars 1065-1167`）。
- 只给 `sentence_id` 即可：`verify.py` 自动回填逐字 `quote` 与完整 locator（最稳做法）。若 `sentence_id` 与 `quote` 不一致，以逐字匹配为准，并记入 `review_records.locator_corrections`。
- `quote` 必须逐字来自稿件（不改写、不拼接、不翻译）；8–400 字符（数字/编号类可更短）。引不到 → 拒收，进 `pending_human`，不进 `issues`。
- 页码只在「内容流数 = `/Type /Page` 数」时给出，否则 `null`；不猜页码、不猜图号。
- 判断写 `reason`：违反了什么 + 依赖的原文位置；建议写 `suggestion`。