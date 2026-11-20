---
name: literature-review-evidence-mapper
description: 将一个真实文献集（PDF/CSV/DOCX/JSON/题录/协议笔记）转成可复核的文献综述：先运行自带脚本产生契约完整基线，再由 Harness Agent 亲自解析真实材料、推导筛选协议、主题与证据链，改写综述稿与证据矩阵，最后回填 result.json。包含筛选协议先于写作、去重与摘要处理、证据逐字回链、冲突并列与研究空白证据化。适用于文献综述、系统筛选、证据综合、主题分析、研究空白分析或带引用追溯的综述草稿。
version: 2.0.0
license: MIT
---

# 文献综述生成：筛选 → 主题 → 证据 → 草稿

## 0. 先读我：脚本只是工具，成品由你亲自推导

本 Skill 自带的 `scripts/main.py` 与 `scripts/verify.py` 是**工具**，负责材料抽取、候选证据切分、主题预聚类、契约回填、确定性基线生成和自检。**它们不是最终成品**。

评测关注的是你（Harness Agent）是否在给定真实输入材料上，完成文献综述四步：筛选标准先于写作并一致执行、主题从这批文献里长出来、每条实质论断能指回具体文献的具体位置、冲突与空白被如实呈现。因此你必须：

1. 真实读取 `/input/case.json`、`/input/task.md` 和 `/input` 下全部材料文件，实际提取文本，不依据文件名或领域标签猜测内容。
2. 亲自判断筛选纳排、主题命名与边界、证据选择与引述强度、冲突与研究空白。
3. 亲自撰写或改写 `/app/output/review.md` 与 `/app/output/evidence_map.csv` 等成品，把脚本基线当作兜底与工作底稿，而不是直接提交。
4. 保留脚本生成的整套基线产物；任何改写前先快照到 `/app/work/baseline/`；不要删除、清空或遗漏契约字段。
5. 若时间或预算不足，保留基线并诚实标注 `status=partial` 与 `pending_human`，远好于缺字段或编造。

**完整性优先策略**：进入任务后先运行脚本产出全套基线并落盘；在此之上逐项核验与增强；提交前做契约完整性自检。

## 1. 用途与边界

把一个真实文献集转成四件可复核交付物：

- **筛选记录**：纳入/排除标准先于写作，逐条文献有决定、理由码和可回链依据。
- **主题归纳**：从这批文献的方法、对象、结论分歧中归纳主题，不套「背景—方法—挑战—展望」壳。
- **证据矩阵**：每条实质论断对应 `source_id + locator + 逐字 quote + strength`。
- **综述草稿**：每句实质论断可回链文献，并区分事实、推断和无法确定项。

做：研究问题分解、检索/证据覆盖说明、分主题综合、冲突与空白、引用可追溯表。  
不做：单篇精读报告、全文翻译、语言润色、投稿选刊、事实层面的学术审查。不引入材料外文献、数值或结论。

**硬边界**：只有材料里出现的文献才算数。缺全文、缺元数据、缺字段时写成缺口或 `pending_human`，不补造。

## 2. 运行时契约与目录约定

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下任意材料（PDF/CSV/XLSX/DOCX/JSON/MD/TXT/图片） |
| 工作区 | `/app/work`（中间件、基线快照、解析结果、候选证据） |
| 最终输出 | `/app/output`（交付件，必须包含 `result.json`） |
| 入口 | `python3 scripts/main.py all`（`collect` + `assemble` 两段等价于 `all`） |
| 校验 | `python3 scripts/verify.py`（确定性检查，打印报告，非 0 不一定失败但需按报告修正） |
| 退出码 | 恒 0；任何异常进入 `errors` 或 `degradations`，不让流程中断 |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent`） |
| 预算 | 64 次模型请求 / 900 秒 / 单回复 16384 tokens（含推理）；约 780 秒立即 finalize |
| 可编辑产物 | 本题标准产物为 Markdown/CSV/JSON，属于文本；若扩展生成 DOCX/PPTX/图表等，必须额外输出真实渲染的 PDF/PNG 预览 |

脚本 argv 可覆盖目录：`--input DIR --output DIR --work DIR`（评测时默认值即可）。

## 3. 包内真实文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本文件，流程、契约、预算与鲁棒性说明 |
| `scripts/main.py` | 材料抽取、筛选表/主题簇/证据候选/基线起草/契约回填 |
| `scripts/verify.py` | 确定性校验：quote、locator、契约、计数、引用一致性 |
| `references/evidence_schema.md` | `result.json` 与 CSV 字段、locator/strength 规范、理由码、写法规则 |
| `references/templates.json` | 契约别名、多语言章节标签、反义/冲突标记、筛选词表 |

只能引用以上包内文件；运行时平台提供的预装工具（如 `pdf-text-tool`、`pdftotext`、`pypdf`）用于真实解析材料，不属于本包资源。

## 4. 执行流程（按序执行，每步先落盘再前进）

> 所有步骤中，脚本生成的 `work/` 中间件只是候选与预切结果；**必须由 Agent 阅读真实材料后，亲自决定最终文本与证据链**。每步失败只降级该步，不删除既有产物。

### 步骤 0：触发基线，保证全套交付物存在

- **输入**：`/input/case.json`、`/input/task.md`、`/input/` 下材料。
- **动作**：
  1. 确认 `/app/work` 与 `/app/output` 存在，不存在则创建。
  2. 运行 `python3 scripts/main.py all`，立即产出基线 `result.json`、`review.md`、`evidence_map.csv`、`screening_log.csv` 到 `/app/output`。
  3. 将 `/app/output` 下脚本生成的基线文件复制到 `/app/work/baseline/`（若有）。
  4. 读 `/app/output/result.json`，确认 `case_id` 与 `output_contract` 字段存在。
- **输出**：全套契约合法基线，状态为 `partial` 或 `ok`。
- **失败分支**：`case.json` 缺失或脚本异常→进入 §6 降级表；不得因脚本失败而让流程退出码非 0。

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input/` 文件树。
- **动作**：
  1. 亲自读 `case.json` 与 `task.md` 原文，不只看脚本摘要。
  2. 提取研究问题/任务指令、范围、工单、文献清单、纳排约束、输出契约。
  3. 递归扫描 `/input/**`，按扩展名 + 魔数识别文件；登记 `source_id`、路径、类型、可用字段、定位体系与 sha1。
  4. 记录材料缺失、字段缺失到 `gaps`/`pending_human`，不构造。
- **输出**：对输入材料与 `output_contract` 字段的完整认知；脚本已写 `work/corpus.json` 时直接使用。
- **失败分支**：`case.json` 坏 JSON→递归找替代文件；仍失败→空壳继续并标 `input_error`。

### 步骤 2：真实解析材料内容

- **输入**：`/input` 下每个 PDF/DOCX/CSV/JSON/MD/TXT/图片。
- **动作**：
  1. 使用环境预装的 `pdf-text-tool`、`pdftotext`、`pypdf` 或脚本内部解析器提取文本；对 DOCX/CSV 用相应方法读取。
  2. 检查 PDF 是否有文本层；若没有，按 `pdftotext` → `pypdf` → 纯 Python PDF 流解析三级降级；仍无文本则标 `abstract_only` 且 locator 用 `block.n`。
  3. 真实打开 `work/corpus.json`，至少抽查每个源的关键段落；确认 quote/locator 能否回指。
  4. 图片只登记存在，不做像素推断。
  5. 不按文件名或领域标签猜测文献内容。
- **输出**：脚本写好的 `work/corpus.json` 以及 Agent 的抽查记录（写入 `changes` 或 `runtime.notes`）。
- **失败分支**：文件损坏、格式不支持→记录 `degradations[]`；缺失全文→标 `fulltext=false` 并进 `gaps: no_fulltext`。

### 步骤 3：先写筛选协议

- **输入**：研究问题、范围、纳排约束。
- **动作**：
  1. Agent 亲自写 `/app/work/protocol.json`，含 `research_question`、`pico`、`criteria`、`dedup_rule`、`strength_rule`，并写入 `written_before_screening: true`。
  2. 筛选标准必须具体、可执行，且只允许引用 `include`/`exclude`；后续筛选不得为了迁就结果修改标准；必须改时记 `changes`。
- **输出**：`work/protocol.json`（时间上先于筛选）。
- **失败分支**：研究问题不明确→采用 `task.md` 中最具体问题，并在 `pending_human` 标注。

### 步骤 4：筛查与去重

- **输入**：`work/protocol.json`、`work/corpus.json`。
- **动作**：
  1. Agent 逐条阅读文献记录，给出 `include`/`exclude` 决定、理由码、命中标准与可回链依据。
  2. 按 DOI 优先，无 DOI 用归一化标题+首作者+年合并重复；保留信息最全者。
  3. 写 `output/screening_log.csv`，保证每条文献有决定与理由。
  4. 使用 `reason_code` 词表：`I1..I9` 命中纳入标准；`E1` 主题不符、`E2` 人群/对象不符、`E3` 方法不符、`E4` 无全文且摘要不足、`E5` 重复、`E6` 非研究性文本、`E7` 年份/语言超范围、`E8` 数据不可用、`E9` 其他（须写明）。
- **输出**：`output/screening_log.csv`。
- **失败分支**：标题/题录不足→依据摘要或首页推断并标 `metadata_estimated=true`；无法判断→排除并给 `E4`。

### 步骤 5：主题归纳

- **输入**：`work/themes.json`（脚本给出的共享词簇与代表文献）、`work/corpus.json`、`output/screening_log.csv`。
- **动作**：
  1. Agent 读候选主题簇，结合文献的**方法路线、研究对象、结论方向、材料/尺度/场景**确定最终主题 3–7 个。
  2. 每个主题写 `label`、`basis`（共现词或方法/对象信号 + 支撑源）、`sources`、`boundary`（不含什么）、`derived_from: "corpus_cluster" | "agent_revision"`。
  3. 确保主题覆盖全部 `include` 文献，或明确写出未归类源及原因。
  4. 单源主题保留但标 `thin=true`，并进 `gaps`。
- **输出**：`output/result.json` 中的 `themes` 字段。
- **失败分支**：无足够文献聚类→降低主题数或如实写 `insufficient`。

### 步骤 6：证据组织与逐字回链

- **输入**：`work/candidates.csv`、`work/corpus.json`。
- **动作**：
  1. Agent 从候选句中选出真正支撑论断的原文，逐字回填 `quote`；允许改动只有省略号；不许可改写、拼接、翻译、纠错。
  2. 每条证据写 `claim`、`source_id`、`locator`、`quote`、`strength`、`claim_type`、`topic`、`verification`。
  3. `strength` 只取：`directly_supported`、`inferred`、`insufficient`；原文说 `may`/`suggests`/`associated with` 时不得写成 `proves`/`causes`。
  4. 写 `output/evidence_map.csv`，一行一论断。
- **输出**：`output/evidence_map.csv`。
- **失败分支**：找不到逐字支持→换句或列入 `pending_human`；不编造 quote。

### 步骤 7：综述草稿

- **输入**：`output/screening_log.csv`、`result.json` 的 `themes`、`output/evidence_map.csv`。
- **动作**：
  1. Agent 亲自写 `output/review.md`，章节包含：研究问题、筛选与覆盖、分主题综合、冲突并列、研究空白、局限、参考文献。
  2. 每个主题下先写论断，再挂 `[Sxx]` 引用，可加 `{Eyy}` 指证据行。
  3. 强度分层：`directly_supported` 用「已报告/显示/在该样本中观察到」；`inferred` 用「提示/可推断/与…一致」；`insufficient` 用「尚不能判断/仅摘要层面」。
  4. 反向证据并列，不平滑掉。
- **输出**：`output/review.md`。
- **失败分支**：超上下文→按主题分批读 `corpus.json`，先写大纲再逐节补；时间不足→保留 baseline 草稿并标 `partial`。

### 步骤 8：回填 `result.json` 并运行自检

- **输入**：所有 `output/` 与 `work/` 产物。
- **动作**：
  1. 运行 `python3 scripts/main.py assemble`（或 `all`）回填 `result.json` 的 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
  2. 运行 `python3 scripts/verify.py`，读报告。
  3. 修正 `rejected` 证据行或将其列入 `pending_human`。
  4. 确保 `result.json` 键名与输入 `output_contract` 一致，`case_id` 原样。
- **输出**：最终合法 `output/result.json`。
- **失败分支**：verify 报告有错但时间不足→在 `result.json.errors` 或 `pending_human` 中列出，退出码仍 0。

### 步骤 9：完整性自检与收尾

- **输入**：`/app/output/` 全部文件。
- **动作**：执行 §14 自检清单；缺项立即补齐；无法补齐则写入 `pending_human` 并保留 `partial`。
- **输出**：完整交付物集合。
- **失败分支**：任何缺失都不得静默提交；必须显式标注。

## 5. 预算策略（64 次请求 / 900 秒 / 单回复 16384 tokens）

按以下优先级分配模型请求与时间：

| 阶段 | 建议请求数 | 关键动作 | 说明 |
|---|---|---|---|
| 触发与基线 | 0–5 | 运行 `main.py all`，读 case/task，确认契约 | 立即落盘合法 partial |
| 材料解析 | 5–15 | 逐文件读 `corpus.json` 块；抽查关键段落 | 优先读高相关源，不要逐页全文读 |
| 协议与筛选 | 15–25 | 写 `protocol.json`；逐条给出纳排 | 筛选先于主题，时间不足可先完成 |
| 主题与证据 | 25–40 | 归纳 3–7 主题；写 `evidence_map.csv` | 每条证据必须逐字 quote |
| 综述草稿 | 40–50 | 写 `review.md` | 按主题分节，每句实质论断带引用 |
| 校验与修补 | 50–60 | `assemble` + `verify.py`；修 rejected | 只针对报告错误修，不重复验证 |
| 缓冲 | 60–64 | 增量润色、补 pending_human | 避免无意义循环 |

**原则**：实际效果 40 分权重最高，优先保证四步齐全和证据行可核验；其次契约完整。任何时点接近 780 秒，立即运行 `assemble` 并 finalize。若 Agent 已写高质量产物，不要为了完美反复重跑脚本覆盖。

## 6. 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json`，退出码 0。异常处置如下：

| 情况 | 处置 | 记录 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找替代 `case*.json`/`task.md`；仍失败→空壳继续 | `input_error` + `errors[]` |
|