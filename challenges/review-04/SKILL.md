---
name: paper-argument-audit
description: Audit a research manuscript's argument and evidence chain and return a locatable, quotable, severity-graded review. Use when the task asks to review, peer-review, critique or 审查/审稿 a paper or manuscript; to check claims against evidence, citations, methods, statistics or cross-section consistency; or to produce issues with verbatim quotes, sentence-level locators and actionable revision advice. Emits result.json, review_report.md and issues.csv.
version: 1.0.0
license: MIT
---

# paper-argument-audit — 论文逻辑与论证审查

## 1. 用途与边界

把一篇稿件变成**可复核的审查意见**：每条问题都有类别、严重度、精确定位、逐字原文、判断依据和可执行改法；六类检查显式跑过；材料缺口单列，既不当作者缺陷，也不把"没审到"写成"没问题"。

**做**：主张抽取；主张—证据对齐；推理链断点；章节衔接（摘要↔正文、引言承诺↔结果交付、方法口径↔结果口径、图表↔正文）；统计报告充分性；引用支持与编号完整性；学术规范；严重度分级与改法。

**不做**（题面排除项，越界即扣分）：文字润色与语言表达、查重与学术不端判定、参考文献**格式**排版（APA/Vancouver）、原始数据重分析与统计复算、投稿策略与选刊。遇到时只在 `uncertainty` 记一行"超出范围，未审查"，不产出条目。

## 2. 触发与不触发

- 触发：输入含论文/稿件（PDF/DOCX/MD/TXT/LaTeX）+ 审查要求；或 `case.json` 的 topic/task 涉及 review、审稿、评审、逻辑审查、claim verification。
- 不触发：只要润色/翻译/摘要/投稿建议；或输入不是稿件（纯数据、纯作图）。
- 证据不足不是"不触发"：照常运行并给 `status: partial` 或 `insufficient_evidence`。

## 3. 运行契约

| 项 | 值 |
|-|-|
| 入口 | 本文件；`scripts/audit.py`（解析与脚手架）、`scripts/verify.py`（校验与定稿） |
| 输入 | `/input/case.json`（可缺）+ `/input/**` 材料（PDF/DOCX/TXT/MD/LaTeX/CSV/JSON/BIB/RIS…） |
| 输出 | `/app/output/result.json`（必需）、`review_report.md`、`issues.csv`；辅助 `audit_digest.md`、`issues_draft.json`、`.audit/index.json` |
| 依赖 | Python ≥3.8 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位自身） |
| 退出码 | 两个脚本恒为 0；异常写入 `errors`/`degradations`/`pending_human` |
| 首写 | `audit.py` 第一步即写合法 partial `result.json`，之后才做重活 |

`$SKILL` = Skill 安装目录（评测时 `/skills/weekly-skill`）；若不存在用本文件所在目录。

## 4. 三步流程（缺一步都会掉分）

```bash
# 步1 脚手架：解析、切句定位、规则预检、写 partial result.json + 阅读摘要
python3 -B $SKILL/scripts/audit.py --input /input --output /app/output

# 步2 裁定：读 audit_digest.md（限长摘要），按第 7–10 节逐条判断，
#      把结论写进 /app/output/issues_draft.json

# 步3 定稿：逐字校验 quote、回填 locator、回填 output_contract，
#      生成 result.json + review_report.md + issues.csv
python3 -B $SKILL/scripts/verify.py --input /input --output /app/output
```

时间不足（≥780s）只做步1：partial `result.json` 已合法可交，`summary`/`review_records` 写明"仅脚手架，未裁定"。若步2 完全没做，步3 用确定性规则兜底（`basis: deterministic_rule`）并在 `degradations` 记明，不伪造裁定。

## 5. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；缺失或坏 JSON 则递归找 `**/case*.json`，仍失败则按目录扫描继续（坏 JSON 记 `errors`）。
2. `case_id` 原样保留；缺失用目录名并记 `degradations`。`output_contract` **整块原样透传**（键名不改、未知字段保留），其每个键在顶层也出现，缺值 `null`/`[]`/`{}`。
3. 语义识别其它字段：`task_instruction`/`instruction`/`prompt`、`manuscript`/`paper`、`references`、`tables_figures`、`checklist`、`domain`、`citation_style`、`ethics_metadata`、`budget`、`artifacts`/`materials`。
4. 递归扫 `/input/**`，按扩展名 + 魔数判定类型；`task.md` 视为指令源，其要求写进 `checks.*.scope`。
5. 材料未给的对象进 `uncertainty`（例："未提供图 3 图像，图内元素未核验"），不构造像素、图注、数据或文献细节。

## 6. 脚本实际做了什么

| 阶段 | 行为 | 产物 |
|-|-|-|
| parse | PDF 取 FlateDecode 内容流的文本层（平衡括号扫描，含十六进制串）；DOCX 解 `word/document.xml`；其余按纯文本读（utf-8/gb18030/latin-1）。二进制表/图不解码 | `degradations`、`uncertainty` |
| segment | 章节标题（Markdown `#`、编号、LaTeX `\section{…}`、中英文章节名）→ 空行分段 → 切句（带缩写与小数字保护）；每句一个稳定 `sid` + 章节 + 段号 + 页 + 字符区间 | `.audit/index.json` |
| leads | 确定性规则产出**未裁定线索**（带 `rule`、`sid`、逐字 `quote`、`hard` 标记），清单见 `references/checks.md` 第 8 节 | `audit_digest.md`、`result.json.candidate_issues` |
| digest | 限长阅读摘要（默认 60000 字符）：章节大纲 + 线索 + 逐句清单（`S0001 §Results ¶3 p.5 \| 原文`） | `audit_digest.md` |
| finalize | 逐字校验每条 quote；回填 locator；归一类别/严重度；去重；按严重度+位置确定性编号；生成报告与 CSV | `result.json`、`review_report.md`、`issues.csv` |

跨运行确定性：同输入 → 同 `sid`、同 `R##`、同 CSV 行序。

## 7. 裁定方法（五步，顺序不可换）

1. **抽主张**：从摘要/引言/结果/讨论/结论抽核心主张，记限定条件（物种、样本、剂量、时间窗、人群）与说话人（作者主张/引用他人观点/假设情形/背景共识）。`verify.py` 把 `claims[]` 落进结果。
2. **配证据**：`own_data`（本文数据、图表、统计量）/`citation`（编号或作者-年）/`assumption`（明确假设推演）/`none`。`none` 且落在结果/结论段 = 高强度候选断点。
3. **验强度**：相关设计写因果；横断面写预测；n 小写普适；单物种写类群；体外写体内；单时点写长期——都要降强度或补证据。
4. **查链条**：前提→结论缺哪一环（隐含假设未声明、替代解释未排除、对照不含关键变量、剂量/时间窗不匹配、混淆未控）。
5. **查衔接**：摘要数字是否正文可追；引言承诺的分析是否交付；方法与结果的样本量/分组/单位/终点是否同口径；图表编号与正文引用是否对应。

## 8. 六类检查项（每类必须给 status，不适用写 `not_applicable` + 原因）

| key | 检查内容 | 典型检出 | 需要的证据 |
|-|-|-|-|
| `factual` | 事实/数值/单位/术语自洽 | 同一量前后数值不一致；单位量纲错；摘要数与正文不符；结论与自家数据方向相反 | 两处 quote + 各自 locator |
| `citation` | 引用支持与编号完整 | 编号超出文献表；条目从未被引；引用不支持该句 | 断言 quote + 文献条目 |
| `method` | 设计能否回答研究问题 | 无对照/对照不含关键变量；样本量与结论范围不匹配；终点与假设不匹配；涉人/动物缺伦理声明 | 方法段 quote + 结论段 quote |
| `statistics` | 统计报告充分性 | "显著"无检验名；`p = 0.000`；`±` 未标 SD/SE；多重比较未校正；百分比无分母 | 该句 quote + 方法段 quote |
| `argument` | 推理链与强度 | 结论超出数据；相关当因果；以偏概全；替代解释未排除；承诺未交付 | 前提 quote + 结论 quote |
| `compliance` | 规范与可复现 | 占位符未清；缺数据/代码可得性；缺利益冲突/资助；样本量未报告 | 该处 quote |

细则（检出清单、误报防线、严重度锚点、规则表）见 `references/checks.md`。

## 9. 误报防线（正确性得分的主要来源，提交前逐条自查）

1. **有意设置的对照**：作者写明 control/阴性对照/空白组 → 不报"分组不合理"。
2. **明确标注的假设/简化**：`assume/for simplicity/近似/为简化` → 是条件推演，不是缺证据（除非被当结论用）。
3. **转述他人观点**：`reported by/according to/据…报道` + 引用 → 责任在被引文献；只有引用不支持才归 `citation`。
4. **已声明的局限**：Limitations 写了就不重复报；只报"声明了但结论没收敛"（需两句 quote）。
5. **学科惯例**：临床常用 p<0.001、生态学用 SE、质性研究不用 p → 不算缺陷；不确定进 `pending_human`。
6. **格式与表达**：语法、拼写、期刊排版不报（越界）。
7. **舍入**：`12.3%` vs `12.34%` 不报；只报无法用舍入/分组/时间点解释的差异。
8. **一句一条**：同根因只报一次，关联证据放 `evidence[]`，不按句刷条数。

被否决的机器线索不必删：写进 `issues_draft.json.rejected_candidates`（`sid + rule + 否决理由`），这是误报控制证据。

## 10. 严重度与改法

| severity | 判据（满足任一） | 处置含义 |
|-|-|-|
| `blocker` | 主结论不成立；结论方向与数据相反；方法无法回答研究问题 | 必须修，否则结论不成立 |
| `major` | 影响结论强度/外推边界/可复现性；补证据或降强度可修 | 必须修 |
| `minor` | 局部、不影响主结论，改一句或补一项即可 | 建议修 |
| `suggestion` | 提升清晰度/规范性，不改结论 | 可选 |

`severity_basis` 三句填：`affects_main_conclusion` / `fixable_by` / `affects_reproducibility`。全条同档视为失准——`verify.py` 在单档占比 >80% 时记 `degradations`。

`suggestion` 必须可执行：补什么证据、改哪一句、把哪个词换成什么、把强度降到哪一档。禁止"建议补充论证""建议加强逻辑"。

## 11. 定位与引用规范

- 每条问题有 `locator`：`{section, paragraph, sentence_id, page, char_start, char_end, source_id}` + 人读串 `locator_text`（`§Discussion ¶10 S0020 p.5 chars 1065-1167`）。
- 只给 `sentence_id` 即可：`verify.py` 自动回填逐字 `quote` 与完整 locator（最稳做法）。若 `sentence_id` 与 `quote` 不一致，以逐字匹配为准，并记入 `review_records.locator_corrections`。
- `quote` 必须逐字来自稿件（不改写、不拼接、不翻译）；8–400 字符（数字/编号类可更短）。引不到 → 拒收，进 `pending_human`，不进 `issues`。
- 页码只在「内容流数 = `/Type /Page` 数」时给出，否则 `null`；不猜页码、不猜图号。
- 判断写 `reason`：违反了什么 + 依赖的原文位置；建议写 `suggestion`。
- 引用只做**文内 ↔ 文献表**一致性；离线不核验 DOI/全文，不编造文献题目、作者、年份、页码。无法获取全文时写 `uncertainty`。

## 12. 输出契约

`result.json` 顶层：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`summary`、`issues[]`、`candidate_issues[]`、`claims[]`、`checks{}`（六键）、`review_records`、`sources[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`、`artifacts`、`output_contract`。

- `issues[]` 单条：`id`、`category`、`severity`、`severity_basis`、`title`、`locator`、`locator_text`、`quote`、`evidence[]`、`reason`、`suggestion`、`check_item`、`confidence`、`status`、`basis`。
- `checks.<key>`：`status`(`ok|issues_found|partial|not_applicable`)、`scope`、`items_checked`、`findings[]`、`unreviewed[]`、`note`。
- `status` 判定：能读到稿件文本且（有已校验条目或至少一类检查非 `partial`）→ `ok`；文本不可用 → `insufficient_evidence`；其余 → `partial`。

字段全表、枚举与回填规则见 `references/schema.md`。主产物：`review_report.md`（结论摘要、问题表、逐条详述、覆盖表、缺口、复现命令）、`issues.csv`（一问题一行，含 locator 与 quote）。

## 13. 异常与降级分支

| 情形 | 识别 | 处置（写到哪） |
|-|-|-|
| `/input` 不存在或空 | 目录缺失/无文件 | `status=input_error`，`errors` 记；仍写合法 partial；不编造 |
| `case.json` 非法 JSON | 解析异常 | `errors` 记，按目录继续；`output_contract={}` 并说明无法回填 |
| 扫描版 PDF 无文本层 | 无可解码内容流；文本 < 200 字符 | `degradations` 记"需 OCR"；该源只做结构级检查；`pending_human` 记需人工/OCR |
| PDF 文本乱码（CID 字体） | 十六进制串解码失败/可读率低 | 同上，不据此做逐字断言 |
| 超长稿（> 400k 字符） | 长度阈值 | 截断并记 `degradations`；`checks.*.unreviewed` 写未覆盖区间；**不得声称审完全文** |
| 章节标题缺失 | 识别不到章节 | 全文归 `Front` 并照常切句；`compliance` note 说明（不直接判缺陷） |
| 文献表缺失/不可解析 | 无 References 段 | `citation` 记 partial，`uncertainty` 记"无文献表，仅查文内编号连续性" |
| 图表文件缺失 | 正文引用图表但无对应文件 | `uncertainty` 记；不进 `issues`（材料缺口 ≠ 作者缺陷） |
| 单文件解析失败 | 异常捕获 | 只降级该源，其余照常；`degradations` 记 |
| `issues_draft.json` 未写/为空 | 步2 未做 | 确定性规则兜底（`basis: deterministic_rule`）+ `degradations` 说明 |
| 契约字段与结果同名冲突 | 键名重叠 | 以真实结果填；不编造；`coverage_note` 说明 |

## 14. 预算与断点

评测预算 64 次模型请求 / 900 秒 / 单次回复 16384 tokens。脚本毫秒级，瓶颈在阅读：先读 `audit_digest.md`（已压缩，含逐句清单），需要细节再 `Read`/`Grep` `.audit/index.json`，不要整篇重读原文。到 780 秒立即停手并跑步3定稿。三条铁律：先落盘、退出码 0、不静默降级。

## 15. 自检清单

1. `result.json` 可 `json.load`；`case_id` 与输入一致。
2. `output_contract` 每个键都在顶层与 `output_contract` 内。
3. 六类 `checks` 全部存在且 status 合法（`not_applicable` 附原因）。
4. `issues[].quote` 全部逐字命中原文；被拒条目在 `pending_human`。
5. 每条有 `locator_text`、`reason`、`suggestion`、`severity_basis`。
6. `issues.csv` 行数 = `summary.total_issues`；`review_report.md` 条目数一致。
7. 无占位符残留（TODO/XXX）；无"加强论证"类空话。
8. `degradations`/`uncertainty` 与实际阅读情况相符，未审部分没写成已审。
9. 单档严重度未占 >80%（否则复核判据）。

## 16. 最小调用示例（**示例，非正式案例结果**）

输入 `/input/case.json`：

```json
{"case_id": "demo-000",
 "output_contract": {"issues": {"type": "array"}, "verdict": {"type": "string"}},
 "manuscript": "paper.md"}
```

`paper.md` 片段（示例）：`… Treatment significantly improved survival (p = 0.000, n = 6 per group). …`（方法段为 cross-sectional survey）

步2 写入 `issues_draft.json`：

```json
{"case_id": "demo-000", "verdict": "观察性设计被用于因果结论，主结论需降强度。",
 "issues": [{"category": "statistics", "severity": "minor", "sentence_id": "S0004",
             "title": "p 值报为 0.000",
             "reason": "统计软件不输出 p=0.000，应报阈值；且 n=6 未说明检验方法。",
             "suggestion": "改为 p < 0.001，并在方法段注明检验（如 log-rank），补效应量与 95% CI。"}]}
```

示意输出（**示例，非正式案例结果**，仅示字段形状）：

```json
{"case_id": "demo-000", "status": "ok",
 "issues": [{"id": "R01", "category": "statistics", "severity": "minor", "basis": "agent",
   "locator_text": "§Results ¶1 S0004 p.2 chars 421-503",
   "quote": "Treatment significantly improved survival (p = 0.000, n = 6 per group).",
   "reason": "…", "suggestion": "…", "confidence": "high", "status": "confirmed"}],
 "checks": {"statistics": {"status": "issues_found"}}}
```

## 17. 文件清单、版本与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 入口：用途、契约、流程、方法、规范、降级、自检 |
| `scripts/audit.py` | 材料发现与解析、切句定位、规则预检、partial `result.json`、digest、draft 骨架 |
| `scripts/verify.py` | quote 逐字校验、locator 回填与纠正、契约回填、六类检查归一、`claims[]` 生成、三产物定稿 |
| `references/checks.md` | 六类检查细则、规则表、误报对照、严重度锚点 |
| `references/schema.md` | 输入发现、`issues_draft.json`/`result.json` 字段、枚举、契约回填 |
| `references/examples.md` | 好/坏条目对照与报告片段（示例，非正式案例结果） |

版本 1.0.0（2026-11），纯标准库，无外部服务，无网络。运行产物：`result.json`、`review_report.md`、`issues.csv`、`audit_digest.md`、`issues_draft.json`、`.audit/index.json`。维护：新增规则时同步 `audit.py` 的 `RULES`、`references/checks.md` 第 8 节；改动 `sid` 规则需同时检查 `verify.py` 的 locator 解析。
