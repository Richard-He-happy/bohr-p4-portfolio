---
name: evidence-driven-writing
description: 文献证据驱动写作。Agent 必须亲自读取并解析 /input 内实际材料，把写作任务拆成“论断清单 → 证据表 → 证据支撑成稿”三段可核对产物；脚本只是基线工具，最终交付物由 Harness Agent 本人读材料、推导、撰写/制作并复核。适用于学术段落写作、补引用、论断核验、证据强度评审与不确定性改写。
version: 3.0.0
license: MIT
---

## ★ Agent 修改边界（最高优先级，先读）

本 Skill 的**结构化产物由脚本生成**；你（Agent）的职责是真实阅读材料、核验、补全文本型交付物，**不是重写结构化 JSON 的结构**。严格遵守：

1. **禁止手改结构化产物**：`claims.json`、`evidence_table.json`、`result.json` 的结构字段（键名、claim_id、source_id、locator、quote、strength、support_scope、counts）**必须原样保留脚本输出**。不得用文本编辑覆盖这些文件。
2. **允许 Agent 做的事**：
   - 真实阅读 `/input` 材料，核验脚本抽取的 quote / locator / 数字是否与原文一致；
   - 把核验结论写进 `agent_review.json`（新增文件：逐条列出 claim_id → 核验结果 verified/rejected/reason）以及 `pending_human.json` 的补充项；
   - 亲自撰写/改写 **正文型交付物**（`deliverable.md` / `manuscript.md` 等），但每个数字、引用、论断必须能在 `evidence_table.json` 中找到依据；成稿不得删除契约要求的字段；
   - 若发现脚本缺陷：写一个临时 python 调用脚本函数重算并覆盖（记录在 `agent_review.json` 的 `script_fixes`），**不得手工篡改 JSON**。
3. **禁止生成无依据的评分/金标准**：不要自造 `golden_standard`、`diff_report`、加权自评分；核验只引用 `verify.py` 的真实输出 `verification.json`。若脚本已生成上述自设资产，**不要引用、不要美化**，在 `agent_review.json` 里说明其局限。
4. **完整性自检**：结束前核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；`deliverable.md` 与 `evidence_driven_draft.md` 如同时存在，两者内容必须不同（前者=干净成稿，后者=带证据标记草稿），不得复制粘贴同一文本。
5. **预算**：先让脚本产出全套基线（通常 1–2 次调用即可），再把剩余请求用于逐条核验与成稿改进；接近 64 次/900 秒时立即收尾，保证 result.json 合法且 status 诚实。

# 文献证据驱动写作（writing-03）

## 0. 最高优先级：完整性优先与“脚本只是工具”

**脚本 `scripts/main.py`、`scripts/verify.py`、`scripts/gold.py` 只是工具，不是成品。最终交付物必须由你（Harness Agent）亲自阅读 `/input` 内实际材料，推导并撰写/制作完成。**

本 Skill 采用“基线 + Agent 增强”混合策略：

1. **先跑基线脚本**：进入任务后，先运行主脚本，产出全套基线交付物（所有 output_contract 字段、所有题面要求文件、合法 `result.json`）。
2. **保留全部基线产物**：之后的任何校验、改写、补充只能在基线上增强；不得删除、清空或遗漏任何基线与契约字段；不确定时保留原产物并在 `result.json` 中标注。
3. **Agent 亲自核验与改写**：在基线之上，你需要亲自读材料、抽查原句、核对数字/引用/术语/证据强度，并将核验结果写入 `result.json.agent_review`。
4. **完整性自检**：提交前逐项核对「output_contract 字段列表 × 磁盘文件 × result.json 键」三者一一对应；partial 状态必须列出缺失项。
5. **任何情况下都产出合法 `result.json` 并退出码 0**：材料缺失、解析失败、超时、契约缺失时，降级并诚实标注，绝不编造。

---

## 1. 用途与边界

**做什么**：给定“一个需要文献支撑的写作任务 + 实际材料（PDF/DOCX/CSV/MD/JSON/TXT/图片等）”，产出可独立回查的三段交付物：

- `claims.json`：论断清单，每条论断含 `claim_id, text, core, type, location`。
- `evidence_table.json`：证据表，每条证据含 `claim_id, source_id, locator, quote, source_type, strength, support_scope, conflicts, rationale, verified`。
- `evidence_driven_draft.md`：按证据强度调整语气后的成稿，含引用编号、冲突句、证据边界段与参考文献。
- 所有结果写入 `result.json`，并回填原 `output_contract` 的全部字段。

**四个必须成立的性质**（本题评分内核）：

| 要求 | 本 Skill 的落实 |
|---|---|
| 找得到 | 论断按句切分，每条落到 `locator`（文件 + `[B块.S句]` + 字符偏移），不停留在“有引用”。 |
| 对得上 | `quote` 必须逐字复制自实际材料；元数据只转录、不补造 DOI/年份/期刊。 |
| 说得准 | 四因子强度分级 + 限定语映射；无干预设计时因果措辞自动下调为关联；冲突证据进 `conflicts` 与成稿 however 句。 |
| 复得现 | 三件产物通过 `claim_id` 双向可 join；`verify.py` 独立重读材料复算；`gold.py` 产出金标准、差分、版本记录、日志与自检。 |

**不做什么**（硬边界）：不联网、不从记忆补文献、不补造数值/DOI/结论、不把“未找到证据”写成“证明不存在”、不把相关性写成因果。材料没有的对象进 `pending_human`，不构造。

---

## 2. 运行契约

### 2.1 输入

- `/input/case.json`：任务主输入，含 `case_id`、`task_instruction`、`output_contract`、`source` 等。
- `/input/task.md`：题面任务说明与评分维度。
- `/input/**`：题面规定的实际材料，可能是 PDF、DOCX、CSV、MD、JSON、TXT、图片等。

### 2.2 输出

- 工作目录：`/app/work`
- 最终产物目录：`/app/output`
- 必须存在合法 `result.json`，包含原 `output_contract` 全部字段（键名不改、未知字段保留、缺值 `null`/`[]`）与 `case_id`。
- 状态字段：`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- `status` 取值：`ok` | `partial` | `insufficient_evidence` | `input_error`，必须与缺口一一对应，不美化。

### 2.3 脚本调用

```bash
python3 -B scripts/main.py   --input /input --output /app/output     # 主流程：生成基线全套产物
python3 -B scripts/verify.py --input /input --output /app/output     # 独立复核 -> verification.json
python3 -B scripts/gold.py   --input /input --output /app/output     # 资产层：金标准/差分/版本/日志/自检
```

三步都应要求退出码 0；`main.py` 会先写 partial `result.json`，异常时 finalize。  
**注意**：这些脚本是离线工具，只允许 Python 标准库，不依赖 CWD，不联网。

### 2.4 资源限制

- 本次 Skill 包最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。
- 运行预算：**64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）**。必须预算感知，尽早落盘 honest partial。

---

## 3. 输出文件清单

| 文件 | 内容 |
|---|---|
| `evidence_driven_draft.md` | 主产物：可编辑成稿（引用编号 + 限定语 + 证据边界段 + 参考文献） |
| `deliverable.md` | 主产物兼容命名 |
| `claims.json` | 论断清单 |
| `evidence_table.json` | 证据表 |
| `evidence_strength.md` | 逐条强度依据（四因子分值 + 理由） |
| `reference_check.md` | 著录完整度与核验路径（明确“未联网核验”） |
| `uncertainty_notes.md` | 低强度/冲突/仅摘要/未匹配计数 |
| `pending_human.json` | 材料缺口与需人工确认项 |
| `verification.json` | `verify.py` 独立复核结果 |
| `result.json` | 契约回填 + 计数 + 资产层字段 + Agent 复核字段 |
| `golden_standard.json` | 金标准 16 项（独立重算） |
| `diff_report.md` | 逐项对照与偏差修法 |
| `version_history.md` | 运行时版本记录 |
| `run.log` | 时间戳日志 |
| `self_check.json` | 自检（契约字段、证据覆盖率、兜底闸门实际退出码等） |

---

## 4. 专属执行流程（编号步骤）

> 每个步骤都要写：输入 → 动作 → 输出 → 失败分支。你（Agent）必须实际执行，不得只读脚本输出。

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input/**` 材料清单。
- **动作**：
  1. 读取 `case.json`，提取 `case_id`、`task_instruction`、`output_contract` 的全部字段名。
  2. 读取 `task.md`，确认任务体裁、受众、格式约束、评分侧重点。
  3. 列出 `/input` 下所有真实文件，识别材料类型（PDF/DOCX/CSV/MD/JSON/TXT/图片）。
  4. 在工作目录 `/app/work` 记录契约字段清单与材料清单（可写在内存/临时 notes，不必额外成稿）。
- **输出**：清晰的“契约字段清单 + 材料清单”。
- **失败分支**：
  - `case.json` 缺失或损坏：`status=input_error`，`output_contract` 缺失则使用题面默认最小字段集（`case_id`, `deliverable`, `preserved_facts`, `evidence_map`, `change_log`），继续后续步骤，不得退出。
  - 材料清单为空：`status=partial`，`pending_human` 标注“无材料可解析”。

### 步骤 2：运行基线脚本（必须）

- **输入**：`/input`、`/app/output` 路径。
- **动作**：运行 `python3 -B scripts/main.py --input /input --output /app/output`。
- **输出**：全套基线产物（见第 3 节文件清单中脚本可生成的部分），以及初始 `result.json`。
- **失败分支**：
  - 脚本超时或退出码非 0：立即降级，手动创建最小合法 `result.json`，`status=partial`，`errors` 记录 `stage=baseline`；但不得跳过后续步骤。
  - 某个产物缺失：记录到 `pending_human` / `errors`，后续用 Agent 亲自产出的内容补齐。

### 步骤 3：用工具真实解析材料

- **输入**：`/input/**` 实际材料文件。
- **动作**：
  1. 对每个材料文件用可用工具实际解析文本：
     - PDF：优先使用平台提供的 `pdf-text-tool` 或等价文本抽取工具；若为扫描件且无 OCR，记 `read_method=none`。
     - DOCX/CSV/MD/JSON/TXT：用 Python 标准库或对应轻量工具读取。
     - 图片：如平台提供 OCR 工具则使用；否则 `pending_human` 提示需要 OCR。
  2. 不得依据文件名、领域标签猜测内容；必须真实读入。
  3. 将材料的章节/段落/句子位置信息保存为可回查的 `locator`（文件相对路径 + `[B块.S句]` + 字符偏移）。
- **输出**：可核验的材料结构化块/句子与定位信息。
- **失败分支**：
  - 文件损坏/格式不支持：`degradations` 记录 `unsupported`，`pending_human` 提示转格式或人审。
  - 只有摘要/无全文：标注 `abstract_only`，相关证据强度最高记“中”，进 `pending_human`。
  - 原文与摘要矛盾：两条都录入证据表，冲突进 `conflicts`。

### 步骤 4：构建/核对证据与论断

- **输入**：步骤 3 解析出的材料文本、步骤 2 基线 `claims.json` 与 `evidence_table.json`。
- **动作**：
  1. 亲自逐条核对基线论断是否真的来自材料；用 `quote in material` 的真实文本匹配而非模糊猜测。
  2. 对每条论断，确认数字、术语、引用、图表、关键结论的来源定位与逐字摘录。
  3. 缺失来源或来源不支持时，改写为待核表述并加入 `pending_human`；不得硬凑引用。
  4. 冲突证据要保留并进入 `conflicts`，不静默丢弃。
  5. 证据强度按四因子（研究设计/样本量/独立来源/冲突）复算，写 `rationale`。
- **输出**：经 Agent 核验/修正后的 `claims.json`、`evidence_table.json`、`evidence_strength.md`、`uncertainty_notes.md`。
- **失败分支**：
  - 材料整体不足：`status=insufficient_evidence`，三件交付物仍尽量产出，每条缺口进 `pending_human`。
  - 个别论断找不到来源：保留该论断但标 `unsupported` + `pending_human`，不删除观点也不编造证据。

### 步骤 5：Agent 产出完整成品

- **输入**：核验后的证据表、原写作任务约束。
- **动作**：
  1. 基于证据亲自撰写/改写 `evidence_driven_draft.md` 与 `deliverable.md`。
  2. 保持事实、数字、引用、术语一致；只做有依据的修改；改写时记录 `change_log`（`original_quote` → `revised_quote` + 理由 + `locator`）。
  3. 低强度/未证实表述使用适当限定语；冲突证据另起 however 句；末尾写“证据边界”与参考文献表。
  4. 如任务要求 Office/幻灯片/图形等可编辑产物，必须额外生成真实渲染的 PDF/PNG 预览；本包默认主产物为 Markdown，可编辑且无需额外预览。
- **输出**：完整成稿与修改记录。
- **失败分支**：
  - 因预算不足无法完成全文时，至少保留脚本基线成稿，并在 `result.json` 标注 `reviewed_by_agent`、列出未完成项。
  - 任何改写不得删除脚本产出的原基线；原样保留并新增版本说明。

### 步骤 6：自检 rubric 与运行验证

- **输入**：`/app/output` 已落盘产物。
- **动作**：
  1. 运行 `python3 -B scripts/verify.py --input /input --output /app/output`，复核逐字引文、claim-join、字段完整性、引用可解析性。
  2. 运行 `python3 -B scripts/gold.py --input /input --output /app/output`，产出金标准、差分报告、版本记录、日志与自检；该步失败只降级，不影响主产物。
  3. 亲自对照第 7 节 rubric 对照表与第 8 节自检清单，逐项核对。
- **输出**：`verification.json`、`golden_standard.json`、`diff_report.md`、`self_check.json`。
- **失败分支**：
  - 验证脚本失败：记录到 `errors`，不得隐藏；尽量修复后重跑一次，仍失败则诚实保留 partial。
  - 自检未通过：修复可修复项；不可修复项写入 `pending_human`。

### 步骤 7：回填并 finalize `result.json`

- **输入**：所有产物与自检结果。
- **动作**：
  1. 读取原始 `output_contract`，把每个字段原样写入 `result.json` 顶层，键名不改、未知字段保留、缺值 `null`/`[]`。
  2. 加入 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
  3. 加入基线计数字段（`claims_total`、`evidence_rows`、`quotes_verified` 等）与资产层字段（`golden_standard`、`diff_report`、`version_history`、`self_check`，值为 `{path, count, note}`）。
  4. 加入 `agent_review`：列出你实际阅读的材料文件名、亲自抽核的索赔数、确认/修正/待人工项、以及未完成边界。
  5. 确认 `result.json` 合法；若 partial，必须列出缺失项。
- **输出**：最终合法 `result.json`。
- **失败分支**：
  - 无法写入 `/app/output`：回退到 `/app/work` 写一份，再尝试复制；仍失败则至少保证退出码 0 并在 `errors` 记录。

---

## 5. 预算策略（64 次模型请求 / 900 秒）

**必须在预算内优先完成 rubric 权重最高的交付物：三件核心产物（亲笔成稿、证据表、论断清单）与合法 `result.json`。**

建议请求分配如下：

| 阶段 | 动作 | 估计请求数 |
|---|---|---|
| 必做 | 读 `case.json` + `task.md`，梳理契约 | 1-2 |
| 必做 | 运行 `main.py` 基线 | 0-1（工具调用，不消耗模型请求） |
| 必做 | 解析关键材料（只看与任务直接相关的章节/页码） | 3-8 |
| 必做 | 核验重点论断/数字/引用，修正证据表 | 2-5 |
| 必做 | 撰写/改写主成稿 | 2-5 |
| 必做 | 运行 `verify.py` 与 `gold.py` | 0-2（工具调用） |
| 必做 | 回填 `result.json` | 1-2 |
| 可跳过 | 重复阅读同一份大 PDF、无关附录、逐页细读 | 跳过 |
| 可跳过 | 多次运行 `gold.py`、格式装饰、无依据重写 | 跳过 |

总计通常 10-24 次模型请求，留足余量。  
**关键原则**：

- 先落盘：步骤 2 之后立即有 partial `result.json`；步骤 5 写完主成稿后再次落盘。
- 接近 900 秒或 64 次请求时：立即 finalize 当前已写出的产物，标注 `degradations=["time_budget_reached"]` 或 `["request_budget_reached"]`，确保退出码 0。
- 单次响应 ≤16384 tokens：不要一次性读入超大 PDF；分段读取，每段只摘录需要的 block/sentence。

---

## 6. 隐藏案例鲁棒性与降级

| 情况 | 处置 | result.json 状态 |
|---|---|---|
| 材料缺失 / 无输入文件 | 产出最小产物，`pending_human` 标“无材料”；不编造 | `partial` / `input_error` |
| 材料损坏 / 格式不支持（xlsx/pptx/doc 等） | `degradations` 记 `unsupported`；`pending_human` 提示转格式 | `partial` |
| PDF 无文本层（扫描件） | `read_method=none`；`pending_human` 提示 OCR | `partial` |
| 仅有摘要 / 文献不可得 | 标 `abstract_only`；强度最高“中”；进 `pending_human` | `insufficient_evidence` |
| 原文与摘要矛盾 | 两条进证据表，`conflicts` 记录，成稿保留冲突 | `ok`/`partial` |
| 证据相互冲突 | `conflicts[]` + however 句 + 强度下调 | `ok`/`partial` |
| 契约缺失 / `output_contract` 不存在 | 用最小默认契约字段（`case_id`, `deliverable`, `preserved_facts`, `evidence_map`, `change_log`），`errors` 记录 | `partial` |
| 运行超时 / 请求接近上限 | 立即 finalize 已产出 partial；`degradations` 记录原因 | `partial` |
| 脚本退出码非 0 | 手动实现关键结果，`errors` 记录 `stage=baseline/tool`，继续跑完全流程 | `partial`/`input_error` |
| 空输入 / 坏 JSON | 写合法 partial `result.json`，`status=input_error`；资产层照常落盘（金标准全部不可判定） | `input_error` |
| 目录不可写 | 回退 `/app/work` 输出，`errors` 记录 | `partial` |
| 资产层异常（写盘失败/子进程超时） |