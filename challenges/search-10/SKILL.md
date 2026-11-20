---
name: cross-lingual-known-item-search
description: >-
  Cross-lingual literature retrieval skill for academic known-item search. Builds a concept table, plans one query per target language, retrieves over the case-supplied corpus, identifies language/version/attribution, merges duplicate language versions, and aligns every candidate to verbatim source evidence. Use when the question language and paper body language differ, or when language/version attribution must be auditable. Offline, standard library only.
version: 1.1.0
license: MIT
---

# 跨语言已知条目文献检索 Skill（Harness Agent 执行版）

## 0. 致 Harness Agent：最终交付物必须由你亲自完成

本 Skill 自带的 `scripts/main.py` 与 `scripts/engine.py` 只是工具，用于生成基线、解析文本类材料、执行检索与字段校验。**脚本产出的初步 JSON/CSV 不能原样当作最终成品提交。**

你必须作为 Harness Agent 亲自完成以下事项：

1. 读取 `/input/case.json`、`/input/task.md` 以及所有原始材料，理解研究问题、目标语种、已知条目与证据边界。
2. 使用真实解析工具读取 PDF/DOCX/CSV/图片等材料内容，不得只依据文件名或领域标签猜测与补造。
3. 在脚本基线之上，亲自核对关键候选的标题、DOI、语种、版本、术语命中与证据摘录是否真实、一致、可溯源。
4. 亲自回填并修正 `result.json`，保留所有 `output_contract` 字段，不得删除、清空或遗漏基线字段。若不确定，保留原值并标注 `reviewed_by_agent`、`pending_human` 或 `conflicts`。
5. 任何不确定、缺失、冲突或失败都必须如实写入 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 与 `runtime`。

题目原题评分强调“完整交付”与“真实推导”。只运行脚本、不读材料、不亲自核对证据，会被判定为不完整或非真实推导。

## 1. 用途与边界

面向科研文献检索场景，完成跨语言文献检索与筛选，并输出可追溯的候选集、排序/筛选依据、术语对齐依据、版本/语言归属与遗漏说明。

适用条件：

- 问题用一种语言提出，但相关论文可能以另一种语言写作或被翻译为另一种语言。
- 需要审计式记录每个命中项的语种、版本（原文、译文、双语刊）、来源文件、术语命中的原文表面形式、证据摘录与定位符。
- 题面固定案例为 3 个双向跨语言 known-item 研究问题，涉及真实 3 篇作品/6 视图（原文葡萄牙语/英语、出版社全文翻译、英语摘要等场景）。源文件、DOI、版本、正文语言与归属必须保留为一等证据。

不适用/不可宣称：

- 不进行整篇翻译、写作润色或未经授权的跨境实时抓取。
- 不声称实时覆盖、未见语言或新研究声称；只处理 case 实际提供的材料。
- 材料不足时不补造文献、数据、引用、分数或评分。

## 2. 运行时契约与目录

### 2.1 目录

- `/input`：只读输入。包含 `case.json`、`task.md`、以及题面规定的材料（PDF/DOCX/CSV/图片等）。
- `/app/work`：工作目录。用于保存解析文本、中间语料、临时文件、脚本输出。
- `/app/output`：最终产物目录。必须包含合法的 `result.json`，以及所有题面要求的可编辑/可复核文件。

### 2.2 入口与脚本调用

标准入口：

```bash
python3 scripts/main.py --input /input --out /app/output
```

也可调用：

```bash
python3 scripts/main.py --help
python3 scripts/engine.py --help
```

脚本只使用 Python 标准库、无网络、无额外依赖。脚本本身不消耗模型请求。

### 2.3 产物要求

- `result.json` 必须存在且合法。
- `result.json` 必须包含 `case_id`。
- `result.json` 必须包含原 `output_contract` 中出现的**全部字段**，键名不改、原样保留；缺失值用 `null` 或 `[]`。
- 可编辑 Office/幻灯片/图形产物必须额外提供真实渲染的 PDF/PNG 预览，预览写入 `/app/output`。
- 保留基线产物：`candidates.csv`、`candidates.json`、`query_log.json`、`term_table.json`、`verification.json` 等。
- 任何情况退出码保持 0。

## 3. 输入盘点流程

按以下顺序盘点 `/input`：

1. 读取 `/input/case.json`。
   - 若不存在，递归查找第一个 `case*.json`。
   - 若仍不存在，必须在 `status` 标为 `input_error`，产出最小合法 `result.json`，退出码 0。
2. 读取 `/input/task.md`。
   - 若存在，用于补充问题、约束、输出契约与评分说明。
3. 列出 `/input` 下所有文件与目录。
4. 对每个 JSON/JSONL/CSV/TSV 文件按内容解码：
   - 任何含 title-like 键 + 至少一个 bibliographic 键的对象视为一条文献记录，无论文件叫什么。
   - 标题/摘要/DOI/语言/年份/期刊/作者等别名见 `references/io_schema.md` §2。
5. 对 PDF/DOCX/XLSX/PNG/JPG 等材料：
   - **必须尝试真实解析**，提取文本、表格或 OCR 文本。
   - JSON/CSV/TSV 可直接用脚本解析；PDF/DOCX/图片应优先调用平台提供的 `pdf-text-tool`、`pdftotext`、`python-docx` 等工具。
   - 将解析结果保存为 `/app/work/parsed/` 下的结构化 JSONL/JSON/CSV 文件，保留源文件路径与页/行定位。
   - 不得因为扩展名不是 JSON/CSV 就跳过材料。
6. 如果材料损坏、格式不支持或解析失败：
   - 记录到 `errors[]` 与 `degradations[]`。
   - 将该材料的可用部分保留为 `pending_human`。
   - 不得将未解析内容当作证据，不得补造其中元数据。

## 4. 完整执行流程（按顺序）

### 步骤 4.1：盘点输入

**输入**：`/input` 目录。

**动作**：列出全部文件；读取 `case.json` 与 `task.md`；识别 `output_contract`、`case_id`、问题文本、范围约束、已知条目/引用、目标语种、评价要求。

**输出**：输入清单；问题/约束/契约摘要。

**失败分支**：若 `case.json` 缺失或不可解析，进入降级模式（见第 6 节）。

### 步骤 4.2：真实解析材料

**输入**：`/input` 下的所有材料。

**动作**：

- 对文本类材料用 `scripts/main.py` 或 `scripts/engine.py` 解析。
- 对 PDF/DOCX/图片等使用平台解析工具提取正文与元数据。
- 将提取结果保存到 `/app/work/parsed/`，每条记录至少包含：`title`、`abstract`、`doi`、`year`、`venue`、`authors`、`language`、`body_language`、`version_label`、`source_file`、`locator`。未知项为 `null`。
- 若同一文献存在多语言版本/多视图，保留各视图记录，但 `source_file` 与 `locator` 必须真实指向对应文件。

**输出**：`/app/work/parsed/` 下的结构化语料；材料来源清单。

**失败分支**：某文件解析失败时，保留文件清单，写入 `errors`/`degradations`，不阻断其他材料。

### 步骤 4.3：构建/核对证据语料

**输入**：步骤 4.2 的解析结果；`references/glossary.tsv`；`case.json` 已知条目信息。

**动作**：

- 确认解析语料覆盖 case 所声明的所有材料；若缺失，记录 `coverage.gaps[]`。
- 对每个候选记录建立证据定位：`source_file`、`page/line`、JSON pointer 或 row index、field、句子/字符偏移。
- 核对术语表是否覆盖研究问题中的关键概念；缺失时从材料原文中提取并补充到 `term_table[]`，方法标为 `agent_supplied_from_source`。
- 不得根据文件名推断语言、DOI、标题或领域标签；必须依据文件内容。

**输出**：可用于检索的结构化记录集合；术语表与证据定位草案。

**失败分支**：无可用语料时进入 `insufficient_evidence` 模式，但仍产出合法 `result.json`。

### 步骤 4.4：生成基线产物

**输入**：已解析语料与 case 约束。

**动作**：

- 运行：

```bash
python3 scripts/main.py --input /input --out /app/output
```

- 该脚本会生成全套基线：`result.json`、`candidates.csv`、`candidates.json`、`query_log.json`、`term_table.json`、`verification.json`。
- 脚本自动完成概念表、语言识别、术语扩展、逐语种查询、检索、打分、排序、去重、版本标注、证据附加与审计。
- 立即确认 `/app/output/result.json` 合法且包含 `output_contract` 全字段与 `case_id`。

**输出**：完整基线产物。

**失败分支**：若脚本异常，使用 try/except 包裹；若失败，创建最小合法 `result.json`，复制 case.json 的 `case_id` 与 `output_contract` 每个键（值 `null` 或 `[]`），`status` 标为 `input_error` 或 `partial`，并写入 `errors`/`degradations`。

### 步骤 4.5：Agent 亲自审查与增强

**输入**：基线产物；`/app/work/parsed/`；原始材料。

**动作**：

- 阅读 `case.json` 与 `task.md`，确认研究问题、目标语言、已知条目。
- 打开关键材料，优先检查：
  - 非英语候选是否真实存在；
  - 标题、DOI、作者、年份、期刊是否与材料一致；
  - `language` / `version_label` / `version_basis` 是否正确；
  - `matched_terms.surface` 是否与论文原文用词一致；
  - `evidence_snippet` 是否逐字来自源文件；
  - `evidence_locator` 是否能定位到原句。
- 对脚本输出中的错误或遗漏亲手修正；所有修正写入 `changes[]`。
- 对无法确认的内容标为 `pending_human` 或 `uncertainty`，不要改写成看似确定。
- 如脚本未生成某些题面要求文件，由你补做，但不得删除基线产物。
- 可编辑 Office/幻灯片/图形产物如需生成，必须同时提供真实渲染的 PDF/PNG 预览。

**输出**：增强后的完整产物与审核记录。

**失败分支**：若时间或请求预算不足，保留当前基线并更新 `status` 为 `partial`；不要丢弃任何已有合法字段。

### 步骤 4.6：Rubric 自检

**输入**：增强后的 `/app/output` 全部产物。

**动作**：逐项检查第 7 节对照表与第 8 节自检清单。

**输出**：自检记录，可写入 `verification.json` 或 `result.json` 的 `runtime`/`changes`。

**失败分支**：发现缺失字段立即补齐；发现证据不匹配立即回退为 `partial`/`pending_human`，绝不伪造通过。

### 步骤 4.7：回填 result.json 并落盘最终产物

**输入**：自检通过的产物。

**动作**：

- 确保 `result.json` 包含原 `output_contract` 全部字段，键名不变。
- 确保 `case_id` 与输入完全一致。
- 确保 `status` 与所有记录的问题相符：无 `gaps`/`uncertainty` 且证据全部通过才可为 `ok`；有任一项未决则为 `partial`；证据不足为 `insufficient_evidence`；输入错误为 `input_error`。
- 最终写回 `/app/output/result.json`，保留所有附加文件。
- 退出码 0。

## 5. 预算策略（64 次模型请求 / 900 秒 / 16384 tokens）

模型请求预算非常有限，必须按优先级分配：

1. **必须先做**：
   - 步骤 4.1 与 4.2 输入盘点和真实解析：约 4-8 次请求。
   - 步骤 4.4 运行脚本：脚本执行不消耗模型请求，但需确认合法输出。
   - 步骤 4.5 中抽取关键候选核查：约 10-16 次请求，优先非英语候选、版本/重复标注、证据摘录精确性。
   - 步骤 4.6 与 4.7 自检与回填：约 4-8 次请求。

2. **可增量改进**：
   - 术语表补充、查询日志核对、去重规则解释：约 6-10 次请求。
   - 补做 Office/图形产物预览：如材料要求，约 4-6 次请求。

3. **可跳过**：
   - 对低权重候选逐条复查。
   - 反复重跑脚本。
   - 高风险但低收益的全文翻译、逐引用核对。
   - 不产生额外证据的格式美化。

4. **诚实 partial 落盘时机**：
   - 步骤 4.4 完成后立即落盘基线 partial。
   - 每完成一轮关键核查，更新一次 `result.json`。
   - 若剩余预算不足 15%或时间不足 90 秒，停止新任务，保留当前 `result.json` 并退出 0。

## 6. 隐藏案例鲁棒性与降级

任何情况下都要产出合法 `result.json`（退出码 0）。遇到以下情况按规则降级：

| 触发条件 | 行为 |
|---|---|
| `case.json` 缺失或不可解析 | `status: input_error`，复制未知输出契约中每个键为 `null`/`[]`，写入 `errors`；退出 0 |
| 材料缺失 | `coverage.gaps[]` 记录缺失项；`status: insufficient_evidence` 或 `partial`；不补造记录 |
| PDF/DOCX/图片解析失败 | 写入 `errors[]`/`degradations[]`；该材料标 `pending_human`；不将其作为证据 |
| 格式不支持 | 保留原始文件清单，标为 `unsupported`；`status: partial` |
| 空输入/无候选 | `status: insufficient_evidence`；记录阈值、记录数、查询日志；候选为空 |
| 超时/中断 | 保留最后合法 `result.json`；若有未完成步骤，在 `status`/`stage` 标为 `partial` 并写入 `degradations[]` |
| 输出契约缺失或不明确 | 以 `case.json` 实际存在的 `output_contract` 键为准；若根本没有，使用本 Skill 标准字段 + `case_id`，并写入 `sources.note` |
| 术语无对应译文 | 写入 `missing_concepts[]`；查询标记 `no_term_mapping`；不静默丢弃 |
| 语言识别置信度低于 0.6 | 标为 `language_low_confidence`；`status` 至少为 `partial` |
| 证据摘录无法定位 | `evidence_quote_match: failed`；写入 `pending_human`；`status: partial`；不调整摘录以通过检查 |
| 数值/引用不在材料中 | 不报告该数值/引用；如 case 声称存在但材料缺失，记录冲突，不补造 |

## 7. Rubric 维度 → 交付要求 → 自证方式

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 实际效果：任务完成度 | 15 | 真实运行跨语言检索：从原问题确定目标语种、术语表、逐语种查询、取回结果并对齐到原文证据 | `queries[]` 中每个声明语言都有查询；`term_table[]` 每个变体有方法与权重；`query_log.json` 每条查询有命中与状态；无未解释空查询 |
| 实际效果：结果正确性 | 15 | 命中文献真实存在；语种与版本标注正确；术语与原文用词一致；译文与原文同义 | 每个候选的 `doi`/`title`/`source_file` 在解析语料中存在；`language*`/`version*` 有 `language_evidence`/`version_basis`；`evidence_snippet` 逐字可查，`evidence_quote_match` 非 `failed` |
| 实际效果：结果完整性 | 5 | 声明的语种都有有效结果；关键非英语文献覆盖；同一论文不同语言版本去重后计数 | `coverage.languages_with_results`、`coverage.non_source_language_works`、`coverage.duplicates_merged` 数字完整；每个工作只有一个候选，`view_records` 列出合并视图 |
| 实际效果：结果可核验性 | 5 | 术语表、查询式、翻译服务与版本、语种判断依据可独立复核 | `term_table.json`、`query_log.json`、`sources[]`、`verification.json` 可供第三方逐个追溯 |
| 使用增益：质量增益 | 15 | 相比基础 Agent 提升跨语言召回与术语对齐质量 | `gain_analysis.baseline` 与 `.skill` 明确对比，使用相同语料与阈值，说明提升点及限制 |
| 使用增益：效率增益 | 5 | 减少翻译调用、无效语种查询、人工逐条核对工作量 | `gain_analysis` 中记录实际查询数、翻译调用数、人工核对项；说明由术语表/查询规划带来的减少 |
| 使用增益：增益可验证性 | 5 | 通过公平对照证明质量或效率改善 | `gain_analysis` 引用固定 case 的原始记录，避免虚报；无对照时说明边界 |
| 创新增益：新增能力 | 5 | 术语表驱动查询生成、语种识别与路由、译文与原文版本归并等能力 | `term_table[]`、`query_plan[]`、`dedup.rules`、`screening[]` 中体现新增能力 |
| 创新增益：方法改进 | 5 | 术语扩展、翻译与回译校验、跨语言匹配、误译复核等措施有实质改进 | `term_expansion`、`screening[include reason]`、`uncertainty[]` 中记录方法改进与结果 |
| 创新增益：创新证据 | 5 | 证明创新点相对已有方案边界和价值 | 在 `result.json` 内 `runtime`/`changes` 或补充说明中给出边界与价值；不虚构基准 |
| 可靠体验：调用与易用性 | 3 | Agent 能正确触发和调用，用户能说清源语言、目标语种、术语要求并完成检索 | 本 SKILL 头部说明用途/触发条件/输入输出；`question` 字段记录语言推断与依据 |
| 可靠体验：运行稳定性 | 4 | 不同语种、来源、重复运行下能持续产出可用结果 | 脚本标准库、确定性算法；同一输入重复运行结果一致；`runtime` 记录重跑次数与一致状态 |
| 可靠体验：异常处理 | 3 | 对术语无对应译法、语种不确定、翻译失败、原文不可得、版本冲突等有处置能力 | 第 6 节降级表与 `pending_human[]`、`errors[]`、`degradations[]` 对应 |
| 生态贡献：文档完整性 | 3 | 使用说明、术语表来源与许可、语种清单、依赖、示例、范围、限制维护信息齐全 | 本 SKILL、`references/method.md`、`references/io_schema.md`、`references/glossary.tsv` 均可读且一致 |
| 生态贡献：资源可复用性 | 4 | Skill 本体、脚本、术语表、多语种查询模板、题集和去重规则可复用 | 文件路径均为包内相对路径；`scripts/engine.py` 与 `main.py` 可独立调用；`glossary.tsv` 与 `method.md` 可被复用 |
| 生态贡献：分享推广价值 | 3 | 沉淀可分享跨语种案例、术语表、评测题和实践经验 | 不提交预生成答案，但保留示例与透明记录；GitHub 链接按要求填写 |

## 8. 提交前自