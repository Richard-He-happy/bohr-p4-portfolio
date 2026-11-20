---
name: multi-doc-comparison
description: 把同一研究问题下的多篇论文落到同一套字段上，逐格抽取值、单位、数据集、指标口径、逐字引文与 locator，判定 task/metric/units/material/pollutant/budget 可比性，解释结论一致或冲突，输出可复核的比较矩阵、证据卡片与完整 result.json。用于 comparison-workorder 类多文档比较任务。
version: 3.0.0
---

# 多文档比较与整合（Agent 主答 + 脚本工具 + 先落盘基线）

## 1. 核心承诺与边界

你（Harness Agent）是本题的**主答者、撰写者、复核者**。`scripts/main.py`、`scripts/verify.py` 只是确定性抽取、索引、格式校验与兜底工具；**不得把脚本骨架、空模板或 build 出的占位行直接当作最终成品**。最终交付物必须由你亲自阅读材料、逐格抽取、判断可比性、解释冲突，并把关键结论写到 quote、locator、note、agreement 等字段中。

任务目标：多篇论文 → 一张可逐格对照的共同字段比较矩阵 + 可比性判定 + 冲突归因 + 证据卡片 + `result.json`。单篇摘要不等于多文档比较。

做：真实解析材料、统一字段、逐篇逐格取值（含单位/数据集/指标口径/逐字引文/locator）、Comparability 判定、结论一致性与冲突归因、诚实标注 unreported/pending_human/limitations。

不做：不依据文件名或领域标签猜测内容；不跨数据集/染料/污染物/指标直接合并数值；不把“未报告”写成 0；不编造数据、页码、引文或分数。

## 2. 目录、输入与交付契约

- 输入：`/input/case.json`、`/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。特别地，多文档比较任务通常有 `/input/comparison-workorder.json`，其中包含 `fields`、`papers`、`question`、`output_contract` 等。
- 工作目录：`/app/work`。最终产物：`/app/output`。
- 必须产出四件：`comparison_matrix.csv`（长表含 quote/locator）、`comparison_table.md`（宽表+可比性+冲突归因）、`evidence_cards.jsonl`、`result.json`。
- `result.json` 必须包含：
  - `output_contract` 中的**全部字段（键名原样不变）**，未知字段保留键并标为 `null` 或 `""`，不得删除、改名或另建嵌套键替代；
  - `case_id`；
  - `status`：`ok` | `partial` | `insufficient_evidence` | `input_error`；
  - `sources`：真实文件来源、doc_id 映射、locator 范围；
  - `uncertainty`：不确定项列表；
  - `pending_human`：需要人工接管的项；
  - `errors`：运行期错误；
  - `degradations`：降级说明；
  - `changes`：关键变更记录，至少包含何时、做了什么、为什么；
  - `runtime`：脚本请求/耗时/失败重试等真实信息。
- 可编辑 Office/幻灯片/图形产物才需要额外渲染 PDF/PNG 预览；本任务通常只产出 CSV/MD/JSONL，无需预览，但如 workorder 要求图，必须输出真实渲染的 PNG/PDF。
- 只用包内资源：`scripts/main.py`、`scripts/verify.py`、`references/checklist.md`、`references/field-dictionary.md`。路径基于 `Path(__file__).parent`，不依赖 CWD，不联网。

## 3. 预算感知执行流程（按顺序执行）

预算：64 次模型请求、900 秒、单次响应 16384 tokens（含推理）。必须尽早落盘 honest partial，再增量增强。以下是唯一的执行主线。

### 步骤 1：盘点输入与契约（1 次模型调用，必要时再 1 次）
- 输入：`/input/` 下全部文件。
- 动作：
  1. 读 `/input/case.json`；若缺失则读任意 `*.json`，按语义识别 `case_id`、`output_contract`、`task_instruction`。
  2. 找 `/input/comparison-workorder.json`；若文件名不同但包含 `fields`/`papers`/`question`，按语义认。读取字段组、论文集合、问题定义。
  3. 递归扫描 `/input/**`，跳过 `case.json`、`task.md`、`*workorder*.json`；材料按扩展名+魔数识别（`%PDF` → pdf，`PK`+`word/` → docx，其余按文本多编码探测）。**不按文件名猜内容**。
- 输出：在内存中建立 `contract_fields`、`paper_ids`、`material_files` 清单。
- 失败分支：若输入空、`case.json` 坏、workorder 缺失字段，仍继续；用内置 8 维通用字段 `task/dataset/sample/material/method/metric/unit/budget` 作为 fallback，并记录 `degradations`。

### 步骤 2：运行 `init` 建立索引并落盘首个 partial（1 次脚本调用）
```bash
python3 -B scripts/main.py init
```
- 输入：`/input` 下材料与 workorder。
- 动作：脚本扫描材料、抽取文本、生成 `/app/work/index.json`（段落、locator、全文），并写入首个 partial `result.json`。
- 输出：打印 material index（doc_id、文件、类型、段落数、抽取器、workorder 论文 id）和 workorder 摘要。
- 失败分支：任何解析失败都要写入 `degradations`，但脚本仍退出码 0；若无法建索引也保留 partial。

### 步骤 3：立即运行 `build` 产出全套基线交付物（1 次脚本调用）
```bash
python3 -B scripts/main.py build
```
- 输入：当前可能还无 `draft.json`，脚本会用占位行（全部 `unreported`）生成 `comparison_matrix.csv`、`comparison_table.md`、`evidence_cards.jsonl`、`result.json`。
- 动作：**这是完整性基线**，保证所有契约字段和文件存在。不得删除或跳过。
- 输出：四件产物落盘 `/app/output`，status 至少为 `partial`。
- 失败分支：若 `init` 未完成，先手动按 `init` 输出写最小索引再 build；仍失败则保留部分产物并把错误写入 `result.json`。退出码恒 0。

### 步骤 4：Agent 亲自真实解析材料（预算主体 25–40 次模型调用）
- 输入：`/app/work/index.json` 中的段落文本和 locator。
- 动作：用 `show` 逐篇逐段阅读：
```bash
python3 -B scripts/main.py show --doc D1 --paras 1:40
```
  必须**逐篇读完再填表**。重点读 Abstract、Methods、Results、Tables/图注、Conclusions、Limitations。对每篇论文：
  - 记录研究对象、数据来源、样本量、方法设置、实验条件、指标口径、主要结论、局限性；
  - 记录 `quote`：必须是 `show` 输出中的**逐字原文**，不得改写、拼接、翻译；跨段引文取起始段 locator；
  - 记录 locator：`p3#para7` 形式；脚本给的页/块号即为权威，如无文本层则降级为 `s1#para3` 并说明。
- 输出：在草稿或内存中形成逐篇抽取表。
- 失败分支：某篇材料扫描 PDF、DOCX 损坏、格式不支持、主题不相关、同一论文多版本等，立即记录到 `pending_human` 和 `degradations`，不猜内容。若某篇完全不可读，该篇所有格为 `status:"unreported"`，`note` 写明原因。

### 步骤 5：写 `work/draft.json`（Agent 亲自完成高质量主体，1–3 次模型调用）
- 输入：步骤 4 的全部抽取结果。
- 动作：按第 4 节 schema 写 `/app/work/draft.json`。自己写，不依赖脚本模板。每个单元格包含：
  - `doc_id`、`field_id`
  - `value`、`unit`、`dataset`、`metric_scope`
  - `status`：`reported` | `unreported` | `not_applicable`
  - `quote`：逐字引文
  - `locator`：段落定位
  - `note`：解释取值规则、口径差异或为何未报告
  在 `comparability` 中逐维判定：`task`、`dataset`、`sample`、`material`、`method`、`metric`、`unit`、`budget`；**任一维度不一致 → comparable: false，保留数值但不合并**；缺失维度视为不可比，写明“未报告，无法确认同条件”。在 `agreement` 中判定结论一致性，冲突必须给出 `attribution`（sample/method/metric/condition/unresolved）。
- 输出：`/app/work/draft.json`。
- 失败分支：若时间不够或信息不足，至少完成关键字段组（对象、数据、方法、条件、指标、结论、局限）中能可靠抽取的部分，其余标 `unreported` 或 `pending_human`，决不为提高覆盖而编造。

### 步骤 6：运行 `check` 并修正（2–5 次模型调用）
```bash
python3 -B scripts/main.py check
```
- 输入：`work/draft.json` 与 `work/index.json`。
- 动作：脚本校验引文逐字命中、字段覆盖、locator 存在、conflicting 是否带归因。打印 `FIX [...]` 错误码。
- 输出：校验报告与计数。
- 失败分支：按 `FIX [...]` 逐条修改 draft 再跑；若仅剩少量警告，可记录到 `uncertainty` 后继续。

### 步骤 7：重新 `build` 生成最终交付物（1–2 次脚本调用）
```bash
python3 -B scripts/main.py build
```
- 输入：修正后的 `work/draft.json`。
- 动作：生成最终 CSV/MD/JSONL/result.json；脚本自动回填 `output_contract` 字段并打印 `unfilled contract`，应为 `none`。
- 输出：最终四件产物。
- 失败分支：若 build 因 draft 损坏失败，退回使用步骤 3 的完整基线，并把错误写入 `errors`、`degradations`，status 保持 `partial`；绝不产生空目录或缺失关键文件。

### 步骤 8：自检 rubric 与回填 result.json（2–4 次模型调用）
- 输入：`/app/output` 全部产物。
- 动作：逐项对照第 5 节自检清单和第 6 节 rubric 对照表。补充 `result.json` 的 `reviewed_by_agent`、`uncertainty`、`pending_human`、`changes`。若发现引用不实、口径错误，立即修正并记录变更。
- 输出：最终合法 `result.json`，退出码 0。

## 4. 预算分配建议（64 次模型请求内）

| 步骤 | 建议请求数 | 说明 |
|---|---|---|
| 步骤 1 盘点输入 | 1–2 | 必须做，确认契约和材料 |
| 步骤 2 init | 0（脚本调用不计模型请求） | 脚本确定性消耗，不计模型预算但计时间 |
| 步骤 3 基线 build | 0（脚本调用） | 保证完整性基线 |
| 步骤 4 真实解析材料 | 25–40 | 主体工作，逐篇阅读，必要时用 `show` 分段读；优先读 rubric 高权重字段 |
| 步骤 5 写 draft | 1–3 | 一次性写好，避免反复大改 |
| 步骤 6 check + 修正 | 2–5 | 只针对 FIX 项改，避免无关循环 |
| 步骤 7 build | 0（脚本调用） | 确定性生成 |
| 步骤 8 自检与回填 | 2–4 | 必须做，防止漏契约字段 |

- 任何阶段若预计剩余时间少于 90 秒或模型请求剩余少于 5 次，立即停止增强，重复步骤 3 基线 build 保证产物完整，并把 `changes` 写为“时间/预算不足，保留基线 partial”。
- **禁止无意义循环**：`check` 失败超过 3 轮仍无法满足，记录到 `pending_human` 转为 partial，不无限重试。
- 优先完成 `comparison_matrix.csv` 和 `result.json`；`comparison_table.md` 与 `evidence_cards.jsonl` 由 build 自动生成，无需手工逐字编辑。

## 5. 隐藏案例鲁棒性与诚实降级

任何情况下必须产出合法 `result.json` 且退出码 0。处理规则：

| 情况 | 处置 |
|---|---|
| 输入为空 / case.json 坏 / workorder 缺失 | 仍产出四件产物；`status=input_error` 或 `partial`；`errors` 记录原因；字段全部 `unreported`，不猜值 |
| PDF 无文本层（扫描件） | `degradations` 记录；该篇所有格 `status:unreported`，`note="scan PDF, OCR required"`；`pending_human` 提示需 OCR，不猜内容 |
| 系统 `pdftotext` 不存在 | 脚本内置 zlib 解析器兜底；locator 变为 `s1#para3` 并在 `degradations` 说明页号不权威 |
| DOCX/XLSX 以外容器或损坏 | 不解析，记降级；该篇全 `unreported` |
| 材料与 workorder 论文对不上 | 保留 `D1..Dn` 映射关系在 `sources` 中，并用 `pending_human` 说明 |
| workorder 字段缺失 | 使用内置 8 维通用字段（task/dataset/sample/material/method/metric/unit/budget），并在 `pending_human` 提示 |
| draft.json 缺失或坏 JSON | `build` 自动用占位行生成完整表格，`status=partial`，缺口写 `pending_human` |
| 结论冲突无法归因 | `attribution="unresolved"` + `pending_human`，不强行合并 |
| 同一论文多版本 | 保留每个 doc_id，比较时优先用 workorder 指定版本；未指定则记录版本差异到 `sources` 和 `uncertainty` |
| 主题不相关或混入染料/污染物不同 | 可比性判定为 false；不合并数值，并在 `note` 写明“不同 pollutant/dye，不可比” |
| 图表只有图无数据 | 只标“约”，写误差范围；无文本可依则 `pending_human` |

诚实性要求：`status`、`sources`、`uncertainty`、`pending_human`、`changes` 必须真实；不确定或材料不足显式标注。不得编造数据、引用、分数、locator。`changes` 中记录 Agent 修改过哪些字段、为什么改。

## 6. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 交付要求（本 Skill 必须实现） | 自证方式（在产物中可核查） |
|---|---|---|
| 实际效果 40：任务完成度 15 | 输出完整的共同字段比较矩阵，覆盖 workorder 指定论文集合与字段组；单篇摘要不得顶替多文档比较 | `comparison_matrix.csv` 行数 = 论文数 × 字段数；`comparison_table.md` 有宽表与覆盖说明 |
| 实际效果 40：结果正确性 15 | 每格取值来自标注论文，单位、数据集、指标口径随值记录；结论方向与强度不被误读 | `result.json` 和 CSV 中每格有 `quote` + `locator` + `unit` + `dataset` + `metric_scope`；`conclusions` 中 direction/strength 与原文一致 |
| 实际效果 40：结果完整性 5 | 覆盖对象、数据、方法、条件、指标、结论、局限字段组；未报告项明确标 `unreported` | `draft.json`/结果中每篇每字段有行；`unreported` 行有 `note` 说明缺什么 |
| 实际效果 40：结果可核验性 5 | 每格能回溯到具体论文具体段落；差异结论可按记录复现 | `quote` 逐字命中 `show` 输出；`verify.py quote` 可抽查；`evidence_cards.jsonl` 一行一卡含 locator |
| 使用增益 25：质量增益 15 | 相比基础 Agent，字段口径更统一、可比性判定更严格、冲突归因更可复核 | `result.json` 含 `comparability` 与 `agreement` 的完整判据；不用主观叙述替代证据 |
| 使用增益 25：效率增益 5 | 减少重复阅读与返工；提供可复跑脚本 | `scripts/main.py` 提供 init/check/build 确定性流程；`result.json` 的 `runtime` 记录实际执行成本 |
| 使用增益 25：增益可验证性 5 | 同论文同字段定义可公平对照 | `comparison_matrix.csv` 列包含 source_document_id 与 locator，可抽样重跑；`result.json` 的 `sources` 说明映射 |
| 创新增益 15：新增能力 5 | 跨文档对齐、逐字证据绑定、可比性分级 | CSV 列设置与 locator 强制绑定；可比性矩阵逐维判定而非简单平均 |
| 创新增益 15：方法改进 5 | 字段定义先于抽取；可比性先于合并；冲突归因到具体维度 | `draft.json` 中有 `fields` 定义与 `value_rule`；`build` 前先 `check` 可比性 |
| 创新增益 15：创新证据 5 | 与基础 Agent 的边界清晰，说明脚本只做确定性部分 | `result.json` 的 `changes` 和 `pending_human` 记录 Agent 亲自改写哪些内容 |
| 可靠体验 10：调用与易用性 3 | 命令清晰，单文件可执行 | `SKILL.md` 步骤可直接复制执行 |
| 可靠体验 10：运行稳定性 4 | 重复运行结果稳定，不因 CWD 或顺序变化 | 脚本路径基于 `Path(__file__).parent`；build 幂等；init 不覆盖已有 draft |
| 可靠体验 10：异常处理 3 | PDF 解析失败、图表无法读取、主题不相关、多版本、冲突无法归因均有明确处置 | 第 5 节异常表全部写入 `degradations`/`pending_human`，退出码 0 |
| 生态贡献 10：文档完整性 3 | 说明用途、依赖、权限、限制、失败处理 | `SKILL.md` 本文 + `references/checklist.md` + `references/field-dictionary.md` |
| 生态贡献 10：资源可复用性 4 | 字段字典、抽取脚本、输出模板可直接用于别的论文集合 | `scripts/main.py` 接受 `--input/--output/--work` 参数；`references/field-dictionary.md` 提供统一字段定义 |
| 生态贡献 10：分享推广价值 3 | 可沉淀比较案例与字段体系 | `result.json` 的 `sources` + `changes` 保留完整过程记录 |

## 7. 自检清单（提交前逐项检查）

1. `/app/output` 下四件产物齐全：`comparison_matrix.csv`、`comparison_table.md`、`evidence_cards.jsonl`、`result.json`。
2. `result.json` 包含 `output_contract` 全部键名（原样不变） + `case_id` + `status` + `sources` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime`。
3. `status` 为 `ok` 或 `partial`，且与 `errors`/`pending_human` 一致；不确定项都写在 `uncertainty`，不藏在正文里。
4. `comparison_matrix.csv` 行数 = 材料数 × 字段数；每个 `reported` 行都有非空 `quote` 和 `locator`。
5. 抽查至少 3 格用：
```bash
python3 -B scripts/verify.py quote --index work/index.json --doc D1 --quote "..."
```
   确保逐字命中。
6. `comparability` 覆盖 workorder 要求的所有维度（task/metric/units/material/pollutant/budget 至少）；任何不可比项没有做数值合并或平均。
7. 每篇论文覆盖“对象/数据/方法/条件/指标/结论/局限”中可得项；未报告项有 `note`，不是空白。
8. `agreement` 中 `conflicting` 项都有具体 `attribution`；无法归因则为 `unresolved` 并出现在 `pending_human`。
9. 没有依据文件名或领域标签补造内容；所有数字、引文、locator 均来自 `show` 输出。
10. 退出码为 0；若脚本异常，也已生成合法 `result.json` 并保留基线产物。

## 8. 工作稿 schema 与输出文件约定

`work/draft.json` schema 沿用：

- `question`：同一研究问题。
- `papers`：`[{doc_id, citation, study_type}]`。
- `fields`：`[{field_id, name, definition, unit, value_rule}]`。
- `matrix`：每格 `{doc_id, field_id, value, unit, dataset, metric_scope, status, quote, locator, note}`。
- `comparability`：`[{dimension, doc_ids, comparable, basis, quote, doc_id}]`。
- `conclusions`：`[{doc_id, direction, strength, claim, quote, locator}]`。
- `agreement`：`{overall, items:[{topic, verdict, attribution, explanation, evidence:[{doc_id, locator}]}]}`。
- `limitations`、`uncertainty`：字符串数组。

枚举：`status` = `reported|unreported|not_applicable`；`direction` = `increase|decrease|no_effect|mixed|unclear`；`verdict` = `consistent|partially_consistent|conflicting|insufficient`；`attribution` = `sample|method|metric|condition|unresolved`。

输出文件列定义：

- `comparison_matrix.csv`：`source_document_id, field_id, field_name, value, unit, dataset, metric_scope, status, confidence, quote, locator, note`
- `comparison_table.md`：宽表（字段×论文，每格带 locator）+ 可比性表 + 冲突归因段 + 覆盖率与复跑说明
- `evidence_cards.jsonl`：每格一张卡，含 `card_id, source_document_id, field_id, value, unit, dataset, metric_scope, quote, locator`
- `result.json`：契约字段 + 元数据 + 状态

## 9. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py init --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py show --doc D1 --paras 1:20
# Agent 写 ./demo/work/draft.json（两篇、至少 8 维字段）
python3 -B scripts/main.py check --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
```
示意输出（示例，非正式案例结果）：`status=partial docs=2 fields=8 cells=16 reported=12 coverage=0.75`，`comparison_matrix.csv` 16 行，4 行 `unreported`（作者未报告），`comparability` 2 条（dataset 不可比、metric 不可比）。

## 10. 文件与维护

包内实际可用文件：`SKILL.md`、`scripts/main.py`、`scripts/verify.py`、`references/checklist.md`、`references/field-dictionary.md`。不要引用或创建清单外路径。

维护建议：新增论文时重新运行 `init`，在 `draft.json` 增加对应矩阵行；字段定义变化时同步更新 `references/field-dictionary.md`；`references/checklist.md` 是交付前逐项核对模板，可被 Agent 读取但不得替代实际执行。