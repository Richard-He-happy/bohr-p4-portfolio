---
name: systematic-literature-review
description: >-
  对给定文献材料执行可复核的系统性文献综述（SLR）：把研究问题拆成检索要素并生成可执行
  布尔检索式，冻结条款化纳排标准，做两轮筛选并逐条留痕（含两遍阈值一致性与人工队列），
  用 SLR-6D 量表逐维度评价质量，最后输出每条论断都带逐字引文与定位的综述、证据矩阵、
  冲突证据与研究空白。Run an auditable systematic literature review over supplied
  records: executable Boolean search protocol, versioned eligibility clauses,
  two-round screening log with per-record reasons, SLR-6D appraisal, and claims
  backed by verbatim quotes plus character-span locators. Writes result.json,
  review.md and evidence_map.csv; never fabricates records, numbers or DOIs.
  预算感知：先产出完整基线并尽早落盘 honest partial，再在核验与综合上增量增强。
version: 1.1.0
---

# 系统性文献综述（SLR）Skill

**脚本只是工具，不是成品：你必须（Harness Agent）亲自读取并解析材料内容，亲自完成证据核对、判定复核、综述撰写与不确定性标注，不得把脚本骨架或模板输出直接当作最终交付物。**

## 1. 用途与边界

把「研究问题 + 给定文献材料」走完一条可复跑的综述链路：问题拆解 → 检索协议 → 条款化纳排 → 两轮筛选留痕 → 质量评价 → 带引文定位的分主题综合 → 冲突证据与研究空白。

**做**：真实解析题录与全文材料（PDF/DOCX/JSON/CSV/MD/TXT/图片中的文本层）、检索式构造、纳排判定、筛选记录、质量评价、证据综合、可复核输出。
**不做**：单篇精读与翻译、论文润色、代替学术审查做事实/方法核验；**不联网检索数据库**，不做全文获取，不生成材料以外的文献、DOI、数值或结论。材料未给出的对象必须标为缺口，不得补造。

## 2. 运行契约与预算红线

- 环境：Python 3.9+，优先使用包内脚本；平台可能提供 `pdf-text-tool` 等解析工具，优先真实解析原始 PDF/DOCX，不得依据文件名或领域标签猜测内容。
- 输入：`/input/case.json` 与 `/input/task.md`，以及题面规定材料（可能位于 `/input/artifacts/`、`/input/material.json`、任意 PDF/CSV/XLSX/DOCX/JSON/图片）。
- 工作目录 `/app/work`；最终产物必须落在 `/app/output`。
- 必须产出 `result.json`，包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。
- 可编辑 Office/幻灯片/图形产物若被要求或产生，必须额外给出**真实渲染的 PDF/PNG 预览**。
- 预算：**64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）**。脚本运行不计模型请求，但占用时间。优先完成 rubric 权重最高的交付物，尽早落盘 honest partial，再增量增强。
- 结果必须诚实：`status`、`sources`、`uncertainty`、`changes` 等字段真实；不确定或材料不足显式标注 `pending_human` 或 `limitations`；不编造文献、引用、分数或软件状态。
- 任何情况下都产出合法 `result.json`，退出码 0。

## 3. 步骤 1：盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、全部材料文件。
**动作**：
1. 读取 `/input/case.json`；若缺失，递归查找含 `output_contract`、`outputContract`、`case_id`、`task_instruction` 的 JSON。
2. 原样取出 `output_contract`（或其别名）与 `case_id`。题目文本按 `research_question`、`question`、`task_instruction`、`objective`、`topic` 取；缺失则从 `task.md` 的「研究问题 / Research question」段落取。
3. 递归扫描输入目录下可解析文件，按扩展名与内容识别；每个文件记录 `sha256[0:12]`、字符数、抽取器名、解析出的记录数。
4. 记录字段按同义词表识别：`title/标题/题名`、`abstract/摘要`、`authors/作者`、`year/年份`、`journal/期刊/venue`、`doi`、`url`、`fulltext/content/text`。
5. 若找不到任何产出契约，不要停摆：使用默认最小契约 `{"review": "path", "included_studies": "array", "quality": "object", "gaps": "array"}`，并在 `contract_check.assumed_default=true` 中诚实说明。

**输出**：`/app/work/discovery.json`（或写回内存），内容含输入文件清单、识别出的契约、研究问题、材料清单。
**失败分支**：`case.json` 缺失/损坏或契约字段不可读，记录到 `errors[].stage=discover`，继续用 `task.md` 与材料推进，先把 partial `result.json` 落盘。

## 4. 步骤 2：真实解析材料

**输入**：步骤 1 得到的材料文件清单。
**动作**：
1. **禁止依据文件名、领域标签或样例答案猜测材料内容**。对每个 PDF/DOCX/CSV/图片/文本文件，用平台提供的 `pdf-text-tool` 或包内脚本/标准库解析器实际提取文本层。
2. 将提取的纯文本写入 `/app/work/extracted/<record_id>.txt`，保留可复核的字符区间。原始材料为图片且无文本层时，记录为 `degradations` 并标 `pending_human.ocr_required`，不得编造可见文本。
3. 每个文件记录：源文件路径、`sha256[0:12]`、字符数、抽取器名、解析出的记录数、解析质量标记。
4. 亲自打开并阅读关键提取文本，尤其确认研究问题、纳入排除标准、文献元数据、摘要/全文是否真实存在于材料。若脚本已抽取，抽查至少每个材料的首尾段和中间关键段，确认不是垃圾文本或模板占位。

**输出**：`/app/work/extracted/` 下逐字文本，以及写入 `materials[]` 的解析记录。
**失败分支**：单个 PDF/DOCX 打不开或文本差，只跳过该文件并在 `degradations` 记录文件路径与原因；不要中止整个任务，不要用文件名补内容。

## 5. 步骤 3：运行基线脚本并核对证据

**动作**：
1. 先运行包内主流程，生成完整基线交付物，避免只写部分成品：
   `python3 -B scripts/slr_review.py --input /input --output /app/output --work /app/work`
   该脚本会执行输入发现、记录解析、问题拆解、检索协议、条款冻结、`state.json` 写入、partial `result.json`，并自动调用 `scripts/verify.py` 完成筛选、SLR-6D 评价、分主题综合、结果装配与引文/契约核验。
2. 脚本运行失败或部分产物缺失时，不要清空重来：保留已有 `/app/output` 文件，手工补足缺失环节，并记录 `changes`。
3. 在基线产物之上，由你本人核验：
   - 每条纳入/排除是否有 `clause_id`、`verdict`、`reason_code`、`reason_text`、`evidence_quote`；
   - 每条综述论断是否回到具体 `record_id + locator + quote`；
   - 筛选记录与冻结标准是否一致，排除理由是否前后矛盾；
   - `result.json` 是否含全部 `output_contract` 字段与 `case_id`；
   - 引文是否逐字命中提取文本。
4. 利用 `scripts/verify.py` 的结果：`verification.result` 若非 `pass`，逐条修复；无法修复则保留并在 `pending_human`/`errors` 中说明。

**输出**：基线全套产物：`result.json`、`review.md`、`evidence_map.csv`、`screening_log.csv`、`appraisal.csv`，及核验后的差异记录。
**失败分支**：脚本超时或异常，立即保存已产生的部分文件，手工生成合法 `result.json`，退出码 0，绝不交出空文件或仅有骨架的 result。

## 6. 步骤 4：产出完整成品与增强

**动作**：
1. 在基线之上审校并改写 `review.md`，确保不是模板套话。每条论断必须属于三型之一：`directly_supported` / `inferred` / `insufficient_evidence`；直接支持型必须带逐字引文与定位，推断型必须写明条件与边界，证据不足型不越界下结论。
2. 补齐并核对 `evidence_map.csv`：每条证据一行，含文献来源、纳排理由、比较字段、定位、方向与质量等级。
3. 若 `output_contract` 要求 Office/幻灯片/图形产物，除可编辑原件外，必须生成真实渲染的 PDF/PNG 预览并写入 `artifacts`。无此类要求则跳过并记录。
4. 将所有关键判断写回 `result.json`：`status`、`sources`、`uncertainty`、`coverage`、`summary`、`conflicts`、`gaps`、`pending_human`、`limitations`。
5. 区分材料事实、合理推断和无法确定的部分：事实只能来自提取文本；推断需要指出依据和前提；不确定/材料不足显式放入 `pending_human` 或 `limitations`。

**输出**：终版可交付物，所有契约字段有值或显式 `null`，磁盘文件与 `result.json.artifacts` 一致。
**失败分支**：若无法完成全部增强，至少保留完整基线并标记已核验/未核验部分；不删除任何基线字段。

## 7. 步骤 5：rubric 自检

按“第 11 节 rubric 对照表”逐条检查。重点确认：
- 是否走完「问题拆解 → 检索式 → 纳排 → 筛选留痕 → 质量评价 → 带证据回链综述」；
- 检索式是否可执行并逐块解释意图；
- 每篇文献纳入或排除都有可查理由；
- 每条论断都能回链原文位置；
- 换一个人能否复跑出基本一致的纳入集与结论。

发现缺口立即补齐；时间不足时，优先保证筛选记录、证据回链、契约字段齐全，其他可降级但必须诚实标注。

## 8. 步骤 6：回填 result.json 并终验

**动作**：
1. 把 `output_contract` 原样作为 `output_contract` 字段写入，键名不改；未知字段保留，占位型字符串 → `null`。
2. 写入 `skill`、`case_id`、`status`、`contract_check`、`research_question`、`search`、`criteria`、`screening`、`appraisal`、`synthesis`、`sources`、`coverage`、`summary`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`verification`。
3. `contract_check.fields_null` 记录仍为空的契约字段数目；若为 0 且 `verification.result=pass`，`status=ok`；否则按实际状态写 `partial` 或 `insufficient_evidence`。
4. 终版 `result.json` 无条件覆盖 `/app/output/result.json`。确保退出码 0。
5. 写 `runtime` 时记录实际运行阶段、关键脚本调用与耗时，不编造 benchmark 分数或平台记录。

**输出**：合法 `result.json` 及全部产物。
**失败分支**：磁盘写入失败，尝试 `/app/output` 重试；仍失败则写 `/app/work/result.json` 并在 `errors` 中说明，但最终退出码仍为 0。

## 9. 预算策略

默认在 64 次模型请求内完成。脚本里程碑通常可批量生成大量结构化字段，不占模型请求；模型请求应优先用于“真实理解材料、核验证据、撰写综合、修正矛盾”。

建议分配（可按材料规模调整）：
- 步骤 1 输入盘点与契约识别：≤6 次请求；
- 步骤 2 材料真实解析与抽查阅读：≤12 次请求；材料超过 20 篇时，优先脚本确定性解析，人工只抽查每篇关键段，不逐篇全文精读；
- 步骤 3 运行脚本与证据核验：≤10 次请求；只核验影响结论的纳排、引文、契约字段，不做冗余重读；
- 步骤 4 综述撰写与产物增强：≤14 次请求；优先写全主产物，再考虑 Office/图形预览；
- 步骤 5/6 自检与回填：≤10 次请求；发现问题只修关键点；
- 异常兜底：≤12 次请求。

必须做：完整沉淀基线、冻结标准、逐条筛选留痕、质量评价、带引文综合、契约回填、合法 result.json。可跳过或降级：非核心材料的全文精读、低权重字段美化、反复重写非关键段落、重复验证已 pass 的引文。任何阶段都要先把 partial `result.json` 写盘；进入步骤 3 前、脚本完成后、终版前各落盘一次。若已用 80% 请求且核心链路仍未完成，停止扩展，先确保筛选记录、证据回链、契约字段完整。

## 10. 隐藏案例鲁棒性

| 情形 | 处置 | 落点 |
|---|---|---|
| 检索/语料为空 | 不编造记录，`status=insufficient_evidence` | `status`、`pending_human` |
| case.json 缺失/损坏 | 从 `task.md` 与材料继续，记录 `errors[].stage=discover`，退出码 0，先落 partial | `errors` |
| 单个 PDF/DOCX 打不开 | 只跳过该文件，记录抽取器与限制 | `degradations` |
| PDF 文本质量差/图片无文本层 | 保留已抽取文本，标记 `stdlib_flate` 或 `ocr_required`，不猜测 | `materials[].extractor`、`pending_human` |
| 全文不可得 | EC7 软排除 + 摘要级证据 + 等级上限 low | `screening_log.csv`、`appraisal` |
| 术语歧义 | 逐块同义词/词形扩展 + 核心词阈值，存疑进队列 | `search.blocks`、`manual_queue` |
| 条款冲突 | 优先级裁决；同级冲突 → uncertain | `criteria.priority_order` |
| 纳入证据互相矛盾 | 冲突条目 + 论断降级 | `synthesis.conflicts` |
| 权限/IO 失败 | 按文件或阶段捕获，`status=partial` | `errors`、`degradations` |
| 重复题录 | DOI 或规范化题名合并，保留原 id | `degradations` |
| 输出契约缺失 | 使用默认最小契约，`contract_check.assumed_default=true` | `contract_check` |
| 超时/预算将尽 | 停止扩展，保留已有产物，补最小合法 `result.json` | `errors`、`runtime` |

**任何情况下**：产出合法 `result.json`，退出码 0；`status` 只能为 `ok`、`partial`、`insufficient_evidence` 或 `input_error`；缺什么写缺什么，不伪装成功。

## 11. rubric 维度对照表

| 评分维度 | 对应交付要求 | 自证方式 |
|---|---|---|
| 实际效果：任务完成度 | 走完问题拆解、检索式构造、纳排筛选、质量评价、带证据回链的结论 | `result.json` 五段齐备；`review.md` 含分主题综合、冲突证据、研究空白 |
| 实际效果：结果正确性 | 检索式可执行并命中领域文献；纳排判定符合事先写定条款；元数据/DOI 真实；论断不越界 | `search.blocks` 逐块解释与命中；`screening_log.csv` 每行 `clause_id`；`sources[]` 只来自材料；`verification.quotes_verified` |
| 实际效果：结果完整性 | 覆盖问题拆解、检索覆盖、证据回链、冲突证据、综合结论、研究空白六方面 | `coverage` 计数；`synthesis.conflicts`、`synthesis.gaps`；`review.md` 六部分均可定位 |
| 实际效果：结果可核验性 | 检索式原文、检索日期与数据库、筛选记录、质量评价依据、引用定位可复跑 | `search.query_original`、`search.date`、`screening.rounds`、`appraisal.items[].basis`、`locator=file#chars=a-b` |
| 使用增益：质量增益 | 纳排一致、证据回链质量与结论稳健性优于基础 Agent | 逐条留痕、冻结版本；同输入重跑判定一致；`verification.result=pass` |
| 使用增益：效率增益 | 减少人工逐条核对、重做筛选、补检索或重写结论的返工量 | 脚本自动生成完整基线；`changes` 记录人工修正量与原因 |
| 使用增益：增益可验证性 | 提供可复核的对照证据 | `verification` 记录核验项；`artifacts` 列出全部产物路径 |
| 创新增益：新增能力 | 结构化检索要素、版本冻结、双人/双阈值分歧、证据自动回链、冲突矩阵 | `search.blocks`、`criteria.version`、`screening.dual_pass`、`evidence_map.csv`、`synthesis.conflicts` |
| 创新增益：方法改进 | 检索式构造、纳排判定规则、质量量表、证据综合方法有实质改进 | `references/slr-protocol.md`、`references/appraisal-rubrics.md`、`references/output-schema.md` 中的定义与模板 |
| 创新增益：创新证据 | 说明创新点相对已有方案的边界与价值 | `SKILL.md` 第 1 节与第 11 节；基线脚本生成的结构化字段可作为对照 |
| 可靠体验：调用与易用性 | 能正确触发与调用，说明完整使用流程 | `SKILL.md` 第 12 节最小调用示例；`python3 -B scripts/slr_review.py --help` 退出码 0 |
| 可靠体验：运行稳定性 | 不同主题、文献规模、数据库和重复运行下持续产出 | 脚本无第三方依赖、确定性流程；多次运行 `verification.result` 稳定 |
| 可靠体验：异常处理 | 检索为空、接口超时、全文不可得、条款冲突、证据矛盾、权限不足等识别与处置 | 第 10 节表格；`errors`/`degradations`/`pending_human` 记录 |
| 生态贡献：文档完整性 | 使用说明、依赖、配置、示例、适用范围、限制与维护信息齐全 | `SKILL.md` 全部章节；`references/` 三份文件 |
| 生态贡献：资源可复用性 | 检索式模板、纳排标准模板、筛选表、证据表、质量量表可复用 | `references/slr-protocol.md`（模板、reason code）、`references/appraisal-rubrics.md`（量表定义）、`references/output-schema.md`（字段定义） |
| 生态贡献：分享推广价值 | 沉淀可分享案例、综述模板、量表、实践经验 | 包内资源与 `SKILL.md` 维护说明；提交目录可附 GitHub 链接（平台侧要求） |

## 12. 自检清单（提交前逐项检查）

- [ ] `python3 -B scripts/slr_review.py --help` 退出码 0，包内脚本可运行。
- [ ] `result.json` 可解析，`output_contract` 键齐全且键名未改，`case_id` 原样。
- [ ] `result.json` 中 `contract_check.fields_null` 已记录；若为 0 且核验 pass，`status=ok`；否则为 `partial` 或 `insufficient_evidence`。
- [ ] `review.md` 存在且含论断引文与 `locator`；不是模板占位，每条直接支持证据有逐字引文。
- [ ] `evidence_map.csv` 行数等于 `coverage.quotes_total`；列定义符合 `references/output-schema.md`。
- [ ] `screening_log.csv` 每行含 `clause_id/verdict/reason_code/reason_text/evidence_quote/screener/ts/criteria_version`。
- [ ] `verification.result` 为 `pass`（引文全部命中、产物齐备）；若非 pass，`errors`/`pending_human` 已说明原因。
- [ ] 空输入或坏 JSON：仍产出合法 `result.json`，退出码 0。
- [ ] 未出现材料外文献/DOI/数值；未编造数据库、检索日期、质量评分或平台成绩。
- [ ] 若要求 Office/幻灯片/图形产物，已额外提供真实渲染的 PDF/PNG 预览并写入 `artifacts`。
- [ ] 所有文件均位于包内且 UTF-8 文本；未引用不存在的文件或 symlink。

## 13. 最小调用示例（示例，非正式案例结果）

示例输入（示意，非正式案例结果）：

    {"case_id": "demo-000",
     "research_question": "住院老年人跌倒预防干预对跌倒发生率的影响",
     "output_contract": {"review": "path", "included_studies": "array", "quality": "object", "gaps": "array"},
     "records": [{"title": "Exercise-based fall prevention in older inpatients: a cohort study",
                  "abstract": "Aim: to assess the effect. Methods: n = 412 cohort. Results: a 23% reduction (p = 0.01). Limitations: single centre.",
                  "year":