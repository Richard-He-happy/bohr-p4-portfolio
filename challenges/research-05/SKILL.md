---
name: research-topic-novelty-appraisal
description: 把模糊研究设想推进到可决策的选题评估——问题定义、已有工作比较、创新点识别、可行性判断四件交付一次成型，每条判断绑定材料定位与逐字引文；离线运行，只用标准库；要求 Agent 必须亲自读材料、推导并核验，不能把脚本输出直接当成品。
version: 1.1.0
license: MIT
---

# 科研选题与创新性评估（research-topic-novelty-appraisal）

## 0. 最高优先级：脚本只是工具，你必须亲自完成推导与成品

`scripts/appraise.py` 会生成一套完整的**基线骨架**，`scripts/assess.py` 会做确定性复核。它们负责解决“字段齐全、文件齐全、退出码 0、契约可回填”的下限问题，但**不能把基线输出直接当作最终交付物**。

作为 Harness Agent，你的职责是：

1. **先运行基线脚本**，确保所有 output_contract 字段、所有产物文件、所有 result.json 键都先落盘；任何时刻中断都能留下合法 partial。
2. **在基线之上，亲自打开输入材料**，逐段阅读 PDF/DOCX/CSV/TXT/MD/RIS 的实际内容，而不是依据文件名或领域标签补造。
3. **逐条核验基线中的关键论断、证据引文、比较对象、可行性前提**：引文必须能在原文中找到，结论必须来自材料；不确定就标记 `pending_human` / `insufficient` / `not_found_in_provided_materials`。
4. **补全 Agent 亲自推导的部分**：四项交付的写法、冲突裁定、研究空白、创新点覆盖判断、可行性风险，要体现出你读过材料并做出独立判断。
5. **保留基线所有字段与文件**，不得删除、清空或遗漏；若你不确定，保留原内容并添加 `reviewed_by_agent` 记录。
6. **诚实记录状态与变化**：`status`、`sources`、`uncertainty`、`changes`、`errors`、`degradations` 必须真实反映本次运行；不得编造文献、DOI、数值、统计量或评分。

一句话：脚本保下限，Agent 做上限；完整交付 + 真实推导 + 契约严格 + 鲁棒兜底。

---

## 1. 用途与边界

**做什么**：输入一个研究设想（或案例题面）+ 一批本地文献材料，输出四件彼此一致的交付，并附证据矩阵、冲突证据、研究空白与不确定性：

1. `problem_definition`：研究对象 / 关键变量 / 结局 / 比较基线 / 预期结论 / 可证伪条件，产出可检验表述；
2. `prior_work_comparison`：按 任务 / 方法 / 数据 / 评价方式 / 结论 建比较矩阵，标出不可比原因；
3. `novelty_assessment`：逐条创新陈述归类（方法 / 数据 / 场景 / 结论修正），判定是否已被材料覆盖；
4. `feasibility`：核查 数据 / 算力 / 实验条件 / 时间窗 / 人员能力，给出带条件的可行性结论与失败风险。

**不做什么**：
- 不联网、不查库。检索协议只作为**待执行计划**输出（`executed:false`）；“材料里没有”一律写成 `not_found_in_provided_materials`，绝不写成“尚无人研究”。
- 不补造文献、DOI、数值、统计量。材料未给的对象进 `pending_human`，不猜。
- 不做领域穷尽综述；不替代实验设计与统计。

**适用**：立项/开题前评估、创新点查重、可行性论证、审稿式新颖性质询。

**不适用**：需要跨库穷尽的系统综述 / Meta 分析；纯写作润色；需要生成实验数据的任务。

---

## 2. 目录与关键路径约定

- 输入目录：`/input`
  - 案例元数据：`/input/case.json`
  - 题面与评分说明：`/input/task.md`
  - 文献材料：通常在 `/input/materials/` 或 `/input` 下，可能包含 PDF / DOCX / CSV / TXT / MD / RIS / JSON / 图片。
- 工作目录：`/app/work`
  - 所有中间文件、临时提取文本、草稿都放这里；不要污染 `/app/output`。
- 最终产物目录：`/app/output`
  - 必须包含 `result.json`；可编辑 Office/幻灯片/图形产物必须额外渲染 PDF/PNG 预览。
- Skill 安装目录：`/skills/weekly-skill`
  - 脚本路径：`/skills/weekly-skill/scripts/appraise.py`、`/skills/weekly-skill/scripts/assess.py`
  - 参考资源：`/skills/weekly-skill/references/method.md`、`/skills/weekly-skill/references/output_schema.md`、`/skills/weekly-skill/references/report_template.md`

**只能引用包内真实存在的文件**：`SKILL.md`、`references/method.md`、`references/output_schema.md`、`references/report_template.md`、`scripts/appraise.py`、`scripts/assess.py`。不得引用不存在的工具脚本或数据文件。

---

## 3. 调用方式与基线命令

先运行主脚本生成基线全套产物：

```bash
mkdir -p /app/work /app/output
cd /app/work
python3 /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output
```

再运行确定性复核：

```bash
python3 /skills/weekly-skill/scripts/assess.py --check --output /app/output --input /input
```

`--input` 必须指向 `/input`；`--output` 必须指向 `/app/output`。不要使用脚本默认回退到包内 `_out` 的行为，因为最终产物必须落在 `/app/output`。

基线产物包括：

| 产物 | 作用 |
|---|---|
| `result.json` | 结构化主结果：契约全字段回填 + 四项交付 + 证据 + 冲突/空白 + 不确定性 |
| `research_report.md` | 主产物：可读评估报告（基于 `references/report_template.md`，但允许 Agent 改写为更完整版本） |
| `evidence_map.csv` | 证据表：evidence_id / source_id / locator / quote / stance / strength |
| `comparison_matrix.csv` | 已有工作比较矩阵（含纳排理由与可比性说明） |

**基线跑完后，Agent 必须继续做 §4 的步骤 3-6，打开材料核验并增强，不能直接提交。**

---

## 4. 本题专属执行流程（编号步骤）

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input` 下所有材料文件。
- **动作**：
  1. 读取 `case.json`；若解析失败，尝试修复尾逗号，仍失败则从 `task.md` 提取题面。
  2. 按语义识别字段（接受同义键）：`case_id`、研究主题、研究设想、创新陈述、时间窗、纳排规则、`output_contract`。
  3. 扫描 `/input` 下所有非 `case*.json`、非 `task.md` 文件，记录来源清单；同名内容按 sha256 去重。
  4. 确认 `output_contract` 全部字段名并记录，用于后续回填。
- **输出**：`source_inventory`（来源文件、扩展名、大小）、`output_contract` 原样副本、`input_notes`。
- **失败分支**：若 `/input` 不存在或 `case.json` 缺失，从 `task.md` 取得题面，`status` 至少为 `partial` 或 `input_error`，记录 `errors`，仍继续尝试解析材料；若 `output_contract` 缺失，则按 §6 的默认字段回填，不报致命错误。

### 步骤 2：用工具真实解析材料，构建源级文本

- **输入**：步骤 1 的 `source_inventory`。
- **动作**：
  1. 对所有来源按扩展名选择解析路径：PDF 提取文本层；DOCX 作为 zip 提取 `document.xml` 文本；CSV/TSV/TXT/MD/JSON 直接读取；RIS 按题录解析；图片记录为 `degradations` 且不推断文字。
  2. **必须读取实际内容**，不得依据文件名、领域标签或题面关键词补造。例如文件名是“某主题论文”，但文本内容必须逐段确认。
  3. 将文本切成块级定位（locator：`p./para./rec./blk.`），供后续句级证据抽取。
- **输出**：`sources` 列表（source_id、文件名、路径、解析方式、文本可读性、页/段数、quality）、块级文本存入 `/app/work/extracted/`。
- **失败分支**：
  - PDF 无文本层：标记 `no_text`，写入 `degradations`，进入 `pending_human`，不 OCR 不猜测。
  - DOCX 无法解压或损坏：标记 `docx_unreadable`，写入 `errors`，继续处理其他材料。
  - 材料为空：来源数为 0，`status` 置 `insufficient_evidence`，只输出协议与空白清单。
  - 格式不支持：记录在 `degradations`，不 panic，继续处理支持的材料。

### 步骤 3：构建与核对证据

- **输入**：块级文本。
- **动作**：
  1. 运行脚本的证据抽取逻辑：术语抽取（拉丁词 + 中文二元组，含剪枝）、分面划分、结果提示词与极性检测。
  2. 生成句级证据单元：每个证据包含 `evidence_id`、`source_id`、`locator`、`quote`（逐字连续子串，空白折叠后 ≥12 字符）、`stance`、`strength`（`directly_supported` / `inferred` / `insufficient`）。
  3. **Agent 核验关键引文**：随机或定向抽查至少 5-10 条证据，确认 quote 能在原文中找到，特别是用于支撑四项交付核心结论的证据。
- **输出**：`evidence` 列表、`evidence_map.csv`、`evidence_hit_check`（核验结果）。
- **失败分支**：如果 `assess.py --check` 报 `misses`，说明引文在原文中找不到，必须删除或修正该证据及其关联 claims；不得保留不可追溯的结论。

### 步骤 4：Agent 亲自产出完整成品

- **输入**：证据、来源、材料事实、output_contract 字段。
- **动作**：
  1. **四项交付**：在基线内容基础上，由 Agent 根据实际材料逐条推导：
     - `problem_definition`：把研究设想拆成可检验表述，明确比较基线与可证伪条件。
     - `prior_work_comparison`：按任务/方法/数据/评价方式/结论建立比较矩阵，说明纳排理由与不可比原因。
     - `novelty_assessment`：逐条创新陈述归类，判断是否已被材料覆盖，给出最近来源定位与引文。
     - `feasibility`：核查数据/算力/实验条件/时间窗/人员能力，给出带条件结论与失败风险；前提无材料支持时标记 `assumed_not_documented`。
  2. **冲突与空白**：检测同一术语下极性相反的结论对；保留双方 quote 与定位，写入 `conflicts`，给出 `resolution` 与 `needs_human`；无证据维度写入 `gaps`。
  3. **研究报告**：改写或补全 `research_report.md`，使用 `references/report_template.md` 的版式，但内容必须是 Agent 亲自撰写的、有材料依据的完整报告。
  4. **可编辑产物预览**：如果题面要求交付 Office/幻灯片/图形等可编辑产物，必须生成真实渲染的 PDF/PNG 预览；若渲染失败，保留源文件并在 `errors`/`degradations` 中说明。
- **输出**：`research_product` 四键齐全；`research_report.md` 完整；`comparison_matrix.csv` 与 `evidence_map.csv` 更新；预览 PDF/PNG 存放在 `/app/output/previews/`。
- **失败分支**：某一篇材料不足以支撑某条创新判断时，标记 `insufficient` 并写入 `pending_human`；不要强行给结论。

### 步骤 5：自检 rubric 与契约完整性

- **输入**：当前 `/app/output` 全部产物。
- **动作**：
  1. 运行 `assess.py --check`，确保 `pass: true`。
  2. 逐项核对 `output_contract` 字段：每个键在 result.json 顶层同名出现，键名不改，缺值 `list->[]`、`dict->{}`、其余 `null`，未知字段保留。
  3. 检查文件：`result.json`、`research_report.md`、`evidence_map.csv`、`comparison_matrix.csv` 都存在；若有可编辑产物，预览也存在。
  4. 检查 `status` 与实情一致：存在缺口就不写 `ok`；有 `pending_human` 或 `errors` 时为 `partial` 或 `input_error`/`insufficient_evidence`。
- **输出**：`assess_check_result`、`consistency_check` 填充到 result.json。
- **失败分支**：任何检查不过，先补全再收尾；如果无法补全，保持 partial 并列出缺失项，不得侥幸。

### 步骤 6：回填 result.json 并 finalize

- **输入**：前面所有步骤的结果。
- **动作**：
  1. 回填 `output_contract` 到顶层；确保 `case_id` 正确。
  2. 写 `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`（记录 Agent 每一步改动：改了什么、为什么、结果如何）。
  3. 写 `runtime`：包括开始时间、结束时间、模型请求数预算估算、耗时。
  4. 写 `tool_call_trace`：记录所有工具调用（appraise.py、assess.py、文件打开、材料解析等）。
  5. 确保退出码 0。
- **输出**：最终 `/app/output/result.json`。
- **失败分支**：即使遇到未捕获异常，也要写入 `errors` 后保存并退出 0；不要崩溃或留下不合法 JSON。

---

## 5. 预算策略：64 次模型请求 / 900 秒 / 单次 16384 tokens

目标：**在预算内先夯实下限，再增量增强**。

建议分配：

1. **步骤 1-2（约 8-12 次请求）**：盘点输入、运行基线脚本、解析材料、生成证据。脚本运行本身不消耗模型请求，耗时时间不占用主要预算，但要留出读取提取文本的时间。
2. **步骤 3-4（约 25-35 次请求）**：核验关键引文、逐条推导四项交付、处理冲突和空白、撰写报告。这是收益最大的部分，优先保证。
3. **步骤 5-6（约 10-15 次请求）**：assess 自检、补漏、渲染预览、回填 result.json、finalize。

**必须做**：
- 运行 `appraise.py` 生成基线；
- 真实读取至少一篇核心材料的关键段落；
- 核验至少 5 条关键证据引文；
- 生成完整四项交付；
- 写入合法 `result.json`；
- 运行 `assess.py --check` 得到 `pass: true`。

**可跳过（预算紧张时）**：
- 过度穷尽的正则调参；
- 对所有证据逐条复读（有余力再做）；
- 非必要的报告润色（但完整性不能牺牲）；
- 任何重复解析或重复核验同一文件。

**何时落盘 partial**：
- 基线脚本运行后立即写一次 `result.json`（即使只有骨架）；
- 每完成一个交付物就更新一次 `result.json`；
- 当请求数达到 55 次或耗时超过 800 秒时，立即跳过非关键增强，执行 finalize；
- 当 `assess.py --check` 失败且无法在 3 次请求内修复时，保留 partial，列出问题，退出 0。

---

## 6. 输出契约与字段铁律

最终 `/app/output/result.json` 必含字段（键名不改）：

`case_id`、`status`、`research_product`、`evidence`、`claims`、`evidence_matrix`、`comparison_matrix`、`conflicts`、`gaps`、`search_protocol`、`coverage_metrics`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`tool_call_trace`、`output_contract`、`artifacts`、`consistency_check`。

外加 Agent 核验记录：`reviewed_by_agent`（布尔或对象，说明核验范围与结论）。

`status` 枚举：`ok` | `partial` | `insufficient_evidence` | `input_error`。只有在无缺口、无 pending、无错误时才能写 `ok`；否则写 `partial`。

**回填铁律**：`output_contract` 的每个键必须在 result.json 顶层同名出现，键名不改；缺值类型规定：list->`[]`、dict->`{}`、其余->`null`。未知字段保留原样。

**产物清单**：
- `result.json`：始终存在，合法 JSON。
- `research_report.md`：可读报告。
- `evidence_map.csv`：证据表。
- `comparison_matrix.csv`：比较矩阵。
- 若有可编辑 Office/幻灯片/图形产物，必须同时提供真实渲染的 PDF/PNG 预览，例如放在 `/app/output/previews/` 并在 `artifacts` 中登记。

字段级定义见 `references/output_schema.md`。

---

## 7. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| **实际效果 40** | 四项交付齐全且相互一致；文献真实存在；比较对象选对；创新点覆盖判断正确；可行性前提成立；覆盖六类内容（问题拆解、检索规划、证据回链、冲突证据、综合结论、研究空白） | `research_product` 四键非空；`sources` 仅来自实际文件；`claims` 逐条挂 `evidence_ids`；`conflicts`/`gaps` 非空；`search_protocol` 非空；`consistency_check.four_deliverables_present` 为 true |
| 实际效果-可核验性 | 每条判断可回到具体文献位置与引文 | `claims[].evidence_ids` 可追溯；`evidence_map.csv` 每行有 locator + quote；`assess.py --check` 输出 `quote_hit` 与 `pass:true` |
| **使用增益 25** | 相比基础 Agent 更稳：问题定义可检验、比较矩阵可交互、创新判定逐条划界、可行性前提有来源或标假设 | result.json 中 `problem_definition` 含可证伪条件；`comparison_matrix` 含不可比原因；`novelty_assessment.items[].coverage` 与位置；`feasibility.premises[].status` |
| 使用增益-效率 | 减少人工补文献与返工 | 基线脚本一键生成全套产物；`changes` 记录 Agent 增量改进，不重复劳动 |
| 使用增益-可验证性 | 展示增益可复现 | `assess.py --check` 可独立运行；`reviewed_by_agent` 说明核验动作 |
| **创新增益 15** | 形成基础 Agent 不具备的稳定能力：证据逐字定位、冲突登记、边界标注、覆盖统计 | `evidence` 中 quote 逐字；`conflicts` 保留双方证据；`coverage_metrics` 明确覆盖/空白；`pending_human` 明确不越界 |
| 创新增益-方法改进 | 分面术语抽取、比较维度设计、前提核查方法 | 方法细节记录在 `references/method.md`；result.json 的 `coverage_metrics` 与 `feasibility.premises` 体现 |
| **可靠体验 10** | 易触发、易读、