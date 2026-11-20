---
name: experiment-feasibility-review
version: 2.0.0
description: >-
  Experimental plan feasibility review for source-grounded candidate plans.
  Use when reviewing whether a research plan can actually start under equipment,
  material, time, cost, sample, ethical and safety constraints; when comparing
  two or more candidate plans; or when performing pre-submission/internal
  feasibility self-check. Produces seven-class check matrix, protocol, risk
  table, evidence table, pending-human list and result.json with source and
  locator evidence.
---

# 实验方案可行性审查 Skill

## 0. 最高优先级

本 Skill 的目标不是“点评方案是否科学合理”，而是把方案、资源、版本候选和硬约束逐条对账，回答：**哪个版本现在就能做、哪个不能做、要做还缺什么条件**。

必须遵守：

1. **未写 ≠ 满足**：方案没有写的检查项，判定为 `gap`，不得默认满足。
2. **只在输入上算术**：时间、费用、量程、样本量、货期、预算只使用 `/input` 中真实出现的数字。输入没有给到的阈值，记 `pending_human` 与 `uncertainty`，不编造。
3. **可复核**：每条判断都要有 `source_id + locator + quote`，指向原文的具体文件、段落/行/表行。
4. **结论可执行**：`feasible_with_conditions` 必须写成条件清单，例如“需要购买 X”“需要伦理审批 Y”“需要把参数 Z 调整到 A-B”“需要等 C 天货期”，不写“建议进一步确认”。
5. **诚实交付**：异常也必须 exit 0；缺材料、缺页面、PDF 不可读、参数缺失、方案自相矛盾等，要在结果中显式记录，不掩盖、不假装完整。
6. **组织方修订场景**：资源/价格/预约合同是组织方给定的前瞻性约束，用于算术核验。交付物中应表述为“给定资源合同/给定价格参数”，不得写成实际实验室采购、实际供应商报价或未来的实测结果。

---

## 1. 用途与边界

### 1.1 适用

- 用户给出 1 个或多个版本的实验方案/候选设计，要求判断可行性。
- 用户要求比较 2-3 个候选方案，选出可执行版本或最优版本。
- 用户要求做送审前自查、内部评审、资源缺口清查、时间成本估算。
- 输入中包含任务说明、材料、设备/试剂清单、预算、时间窗、参数域、SOP、风险/伦理表单。

### 1.2 不适用

- 不执行实验、不做数据分析或统计推断。
- 不替代伦理委员会、生物安全委员会、设备管理员或 PI 的签字。
- 不写文献综述、不做论文写作。

---

## 2. 触发条件

满足以下任一表述时触发本 Skill：

- “这个方案能不能做”
- “哪版方案更可行”
- “按现有设备/材料/预算/排期能否开工”
- “帮我审一下实验方案”
- “方案送审前检查”
- “实验设计可行性评估”

---

## 3. 输入、输出与运行契约

### 3.1 输入

- `/input/case.json`：案例主文件。
- `/input/task.md`：任务说明与输出契约。
- `/input/` 下全部材料：`md/txt/csv/xlsx/docx/pdf` 等。
- 必须真实解析材料内容，读取实际文本、数字和表格，不得依据文件名或领域标签猜测来源内容。

### 3.2 工作与产物目录

- 中间产物写入 `/app/work`。
- 最终产物写入 `/app/output`。
- 只读 `/input`；不写 `/input`。
- 产物不得依赖手工操作；不得依赖未声明的个人文件。

### 3.3 运行预算

- 64 次模型请求。
- 900 秒。
- 单次响应 16384 tokens，含推理。
- 默认策略：**先跑确定性脚本落盘 honest partial，再用剩余预算增量增强**。
- 接近预算时立即收尾，确保 `result.json` 合法、字段齐全、status 诚实。

### 3.4 运行基础

- Python 3.8+。
- 纯标准库优先；离线运行；不联网。
- 若存在 `pypdf`，用于解析 PDF；缺失时降级，不阻断。
- 位图 PDF/扫描件不做 OCR，记入 `degradations`。
- 单文件超过 4MB 时只截取前 400KB 文本，不阻塞，记录 `degraded`。

---

## 4. 单命令全流程入口

一次性运行：

    python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

该命令内部依次完成：

1. **init**：盘点材料、分配来源编号、抽取候选方案、识别多版本、分组冲突。
2. **build**：校验 Agent 草稿；若无草稿则执行确定性兜底抽取；渲染全部产物；生成并 finalize `result.json`。
3. **selfcheck**：检查产物与 `output_contract` 字段是否一致；检查 locator、quote、来源、缺项和运行状态。

也支持分步运行：

    python3 -B scripts/main.py init --input /input --output /app/output --work /app/work
    python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
    python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
    python3 -B scripts/main.py --input /input --output /app/output

`--help` 显示全部参数。脚本应打印一行摘要：

    case_id=... status=... checks=... artifacts=... elapsed=...s

任何异常都 exit 0。

---

## 5. Agent-first 双路径

### 5.1 优先路径：Agent 判断 + 脚本生成

1. 先运行 `init`，得到 `/app/work` 下的材料台账与候选清单。
2. Agent 真实阅读 `/input` 材料，逐项核验数字、条款、缺项。
3. 将 Agent 判断写入 `/app/work/draft.json`。
4. 运行 `build`，脚本读取 `draft.json` 并渲染正式产物。
5. 运行 `check` 做自检。

### 5.2 无草稿路径：确定性兜底抽取

若 `/app/work/draft.json` 不存在、非法或未覆盖关键项：

1. `build` 根据 `init` 台账做确定性抽取，生成实质工作稿。
2. 每个关键数字/论断尽量带逐字 `quote` 与 `locator`。
3. 在 `result.json` 中诚实记录 `AUTO_EXTRACT` 状态，写入 `gaps`、`degradations` 或 `uncertainty`。
4. 两条路径必须产出同一套产物、同一份 `result.json` 契约。

### 5.3 `draft.json` 最小形状

可写在 `/app/work/draft.json` 中，字段包括：

- `case_id`
- `agent_notes`
- `source_checks`：逐文件记录 `source_id`、`file`、`readable`、`degradation`
- `claims`：逐条记录 `class`、`version_id`、`item`、`judgement`、`quote`、`locator`、`condition`
- `overrides`：对确定性抽取结果的纠正，必须给出原文依据
- `pending_human`：需要人工/专家确认的事项

`judgement` 取值固定为：

- `met`：原文明确满足。
- `partial`：部分满足或满足附条件。
- `gap`：方案未写或材料缺失。
- `degraded`：材料存在但不可读/截断。
- `blocked`：给定约束下明确不满足或不可能。

---

## 6. 七类检查体系

固定顺序，不得漏项：

| 代码 | 检查类 | 核心问题 | 常见证据来源 |
|---|---|---|---|
| `HYPOTHESIS` | 假设与变量 | 研究目标能否转成可检验问题？变量、暴露、结局是否明确？ | 方案摘要、目标、变量表 |
| `CONTROL` | 对照组 | 是否有对照、阴性/阳性对照、批次对照？是否可执行？ | 方案设计与分组段 |
| `RESOURCE` | 设备与材料 | 型号、量程、精度、附件、试剂、耗材、库存、货期是否满足？ | 设备清单、试剂清单、采购记录、SOP |
| `TIME` | 时间与成本 | 各步骤时间、等待周期、总历时、人力、费用是否在窗口和预算内？ | 计划排期、人力、预算、合同 |
| `PARAM` | 参数范围 | 关键参数取值与容差是否有依据？是否落在设备/方法允许范围？ | 参数表、设备手册、方法段 |
| `RISK` | 风险与异常 | 设备故障、材料批次、样本不足、参数越界等是否有降级方案？ | 风险段、异常处置、SOP |
| `ETHICS` | 伦理与安全 | 是否涉及动物、人体、危险试剂、个人数据？审批路径和时间是否明确？ | 伦理表单、安全说明、审批记录 |

每条检查项必须落在一个具体版本的具体章节、参数或清单行上，不能只写“总体可行”。

---

## 7. 证据与 locator 规范

- 每个来源文件分配编号：`S1`、`S2`、`S3`……
- 每条关键判断使用 `[S#]`。
- locator 示例：
  - `plan.md#L12`：行号。
  - `equipment.csv#Tab1:row3`
  - `methods.md#¶5`
  - `sop.pdf#page3`
- 引文使用原文短句，不得改写关键数字或术语。
- 若证据来自多源，可写 `[S2][S5]`。
- 无材料支持的判断，必须进入 `uncertainty` 或 `pending_human`。

---

## 8. 算术核验规则

必须逐项复核：

- 设备量程是否覆盖方案需要的量程。
- 精度/分辨率是否满足测量要求。
- 试剂/耗材库存是否大于或等于方案需求量。
- 货期 + 到货后可操作时间是否晚于方案时间窗。
- 关键路径总时长 = 串行步骤求和 + 并行等待取最大；只使用输入给定时间。
- 成本 = 给定单价 × 数量；总费用不超过给定预算。
- 参数取值是否落在给定取值域内。
- 样本量是否满足方案声称的检测/统计要求。

如果缺少某个输入数字或公式不可完成，记 `pending_human`，不要猜测。

---

## 9. 输出产物

必须生成的最终交付物放在 `/app/output`：

| 文件 | 内容 |
|---|---|
| `result.json` | 结构化结果；见第 10 节。 |
| `protocol.md` | 推荐/优化后的实验方案，包含假设、变量、对照、步骤、参数、资源、判读标准；所有关键数字带 `[S#]` 和 locator。 |
| `check_matrix.csv` | 七类检查矩阵；每行一个检查项。 |
| `risk_table.csv` | 风险与异常处置表；含风险描述、触发条件、降级路径、替代方案、转人工节点。 |
| `evidence_table.json` | 逐条证据：claim_id、source_id、locator、quote、strength、support_scope、counts。 |
| `pending_human.json` | 安全、伦理、设备可用性、专家确认项；不得把未确认项写成可执行事实。 |
| `deliverable.md` | 每个版本的可行性结论、条件清单、缺项清单、建议采纳版本及理由。 |
| `input_inventory.md` 或 `manifest.md` | 输入材料清单、来源编号、版本计数、缺失/降级记录。 |

可选：

- `agent_review.json`：Agent 核验动作、发现、修正、conflicts。
- Office/幻灯片/图形类产物必须同时渲染为真实 PDF/PNG 预览。
- 本 Skill 默认产物为 Markdown/CSV/JSON，不强制生成 Office 文件。

---

## 10. `result.json` 契约

`result.json` 必须包含：

- 顶层 `case_id`。
- 顶层契约字段：`status`、`review_conclusion`、`experiment_plan`、`evidence_and_risks`、`confirmations`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`selfcheck`。
- 嵌套 `output_contract`：原 `task.md` 或 `references/schema.md` 中 `output_contract` 的全部字段，键名不改。
- 顶层与嵌套 `output_contract` 中相同契约字段应保持同步，值可相同或顶层为摘要。

### 10.1 契约字段内容要求

`experiment_plan`：

- `hypothesis`：研究假设/可检验问题。
- `variables`：变量、暴露、结局、混杂控制。
- `controls`：对照设计。
- `steps`：可执行步骤。
- `parameters`：参数范围与依据。
- `resources`：设备/材料/人力的明确状态。
- `criteria`：判读标准或 go/no-go 标准。

`evidence_and_risks`：

- `basis`：来源、证据定位、关键依据。
- `risks`：风险列表。
- `abnormal_handling`：异常处置与转人工节点。

`confirmations`：

- `safety`
- `ethics`
- `equipment_availability`
- `expert_confirmations`

未确认项必须标记为 `pending_human`，不得写成事实。

### 10.2 `status` 取值

- `complete`：全部契约产物存在，关键检查有依据，诚实记录了已存在的 gap。
- `partial`：产物可用，但存在材料缺失、PDF 不可读、关键字段无法核验、某些检查未完成。
- `failed`：几乎无可用产物；仍要输出合法 `result.json` 并 exit 0。

优先使用 `complete` 或 `partial`；不要为了避免扣分而掩盖缺失。

---

## 11. 执行流程

### 步骤 0：预算与优先级

1. 读取 `/input/task.md` 和 `/input/case.json` 顶层结构。
2. 识别 case 数量、版本数量、材料类型、输出契约字段。
3. 在 `/app/work/plan_notes.md` 写优先级。
4. 最高权重：七类检查、逐版本结论、`protocol.md`、`result.json`。

失败分支：

- `case.json` 缺失或不可解析 → 使用 `references/schema.md` 默认契约，继续生成最小合法 `result.json`。
- 输入目录为空 → 生成 `status=partial`，`errors` 记录无输入，exit 0。

### 步骤 1：运行 init

执行：

    python3 -B scripts/main.py init --input /input --output /app/output --work /app/work

产物：

- `/app/work/input_inventory.md`
- `/app/work/source_map.json`
- `/app/work/candidates.json`
- `/app/work/conflicts.json`

Agent 随后阅读台账，确认来源文件与实际内容对应。

### 步骤 2：真实解析材料

- PDF：优先使用 `pdf-text-tool` 或 `pypdf`，抽不到文本记 `degraded`。
- `.docx/.xlsx/.pptx`：解 zip 读取 XML 文本。
- `.md/.txt/.csv/.json`：直接读取。
- 位图不 OCR，记 `degradations`。
- 不得依据文件名或领域标签推断内容。

### 步骤 3：生成基线产物

执行：

    python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

或先生成基线：

    python3 -B scripts/main.py build --input /input --output /app/output --work /app/work

基线要求：

- 即使没有 `draft.json`，也必须生成实质可用工作稿。
- 不得把空模板当成最终产物。
- 尽早落盘 `/app/output/result.json` 的 honest partial。

### 步骤 4：Agent 核验与增强

Agent 必须亲自：

1. 抽查七类检查每类 1-2 条，核对 locator/quote。
2. 复核所有算术。
3. 补充脚本漏判的明确设备/材料/参数/风险。
4. 把不确定项标为 `pending_human`。
5. 把核验动作写入 `/app/output/agent_review.json`。
6. 若脚本输出存在结构错误，使用脚本函数重算，不得手工篡改 JSON。

### 步骤 5：重新运行 build/check

增强后再次运行：

    python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
    python3 -B scripts/main.py check --input /input --output /app/output --work /app/work

### 步骤 6：最终交付

确认：

- `result.json` 合法，字段齐全。
- 所有契约字段在顶层与嵌套 `output_contract` 中各出现一次。
- 所有产物位于 `/app/output`。
- 所有 gap/degradation/pending_human 都显式列出。
- 运行摘要 stdio 只能有脚本输出，不输出无关文本。

---

## 12. 异常与降级处理

| 异常 | 处置 |
|---|---|
| `case.json` 缺失 | 尝试读取 `/input/task.md` 和可用材料；生成最小合法 `result.json`，`status=partial`，`errors` 记录。 |
| `task.md` 缺失 | 使用 `references/schema.md` 默认契约，记录 `degradation`。 |
| PDF 无文本/为扫描件 | 该来源标记 `degraded`，保留来源编号，不阻断其他检查。 |
| 单文件过大 | 截取前 400KB 文本，`degraded=true`。 |
| 材料整体缺失 | 停止抽取，渲染可从任务说明得到的检查项，其余 `gap`。 |
| 版本无法识别 | 将全文视为单版本 `V0`，记录 `uncertainty`。 |
| 参数缺失 | 显示为 `gap` 并加入 `pending_human`，不得编造阈值。 |
| 方案自相矛盾 | 冲突双方都记录，写入 `uncertainty` 或 `errors`，不要自行选择一方。 |
| 脚本失败 | 捕获异常，使用 Oracle 标准库降级路径生成最小合法 `result.json`，写入 `errors`。 |

任何情况下 exit 0。

---

## 13. 自检

运行：

    python3 -B scripts/main.py check --input /input --output /app/output --work /app/work

检查项：

- `result.json` 是否可以解析。
- `case_id` 是否等于输入 case_id。
- `output_contract` 字段是否与 `task.md`/schema 完全一致。
- 每个契约字段是否在**顶层**与**嵌套 `output_contract`** 中同时存在。
- 每个关键数字/论断是否有 `source_id + locator + quote`。
- 七类检查类是否全部覆盖。
- `check_matrix.csv`、`risk_table.csv`、`evidence_table.json` 是否生成且不为空。
- `pending_human` 是否列出安全、伦理、设备可用性等未确认项。
- 是否有 `sources`、`uncertainty`、`errors`、`degradations`。
- 未出现伪造评分、伪造金标准、伪造 benchmark 分数。
- Office/图形产物是否有 PDF/PNG 预览；无此类产物则跳过。

自检结果写入 `result.json` 的 `selfcheck` 字段。

---

## 14. 生态与可复用资源

包内应包含并由 Skill 引用：

| 资源 | 用途 |
|---|---|
| `references/checks.md` | 七类检查项、证据来源、判定阈值、常见缺项。 |
| `references/schema.md` | 默认 `output_contract` 字段与键名。 |
| `references/guide.md` | `draft.json` 形状、双路径工作流、逐步骤说明。 |
| `references/example.md` | 最小调用示例，明确标注为示例，不冒充正式案例结果。 |
| `environment/resources.yaml` | 声明 Python 3.8+、标准库、可选 `pypdf`、离线、无系统依赖。 |
| `scripts/main.py` | CLI 入口，支持 `init/build/check/run`。 |
| `scripts/feas.py` | 确定性抽取、算术核验、渲染逻辑。 |
| `SELFTEST.md` | 自检清单与预期输出示例，供他人复跑。 |
| `GITHUB_URL.txt` | 提交根目录下公开作品链接。 |

资源限制：

- 最多 50 个 UTF-8 文本文件。
- 单文件 ≤ 500KB。
- 总大小 ≤ 2MB。
- 不包含 symlink。
- 不包含预先生成的正式测试答案。

---

## 15. 增益证据如何体现

为证明本 Skill 相对基础 Agent 的增量价值，产物中必须体现：

1. **质量增益**：每个结论都落到方案的具体章节、参数和清单行；不输出泛化建议。
2. **可核验增益**：`evidence_table.json` 提供逐条原文定位；`check_matrix.csv` 提供可勾选判定。
3. **效率增益**：`result.json` 直接给出 status、条件清单、缺项清单，减少专家返工。
4. **确定性增益**：无 Agent 判断时也能生成实质性工作稿，避免空响应。
5. **创新证据**：检查项来源、判定阈值、时间/成本算术、AUTO_EXTRACT 与 draft 分流，都在 `result.json` 的 `selfcheck`、`sources` 和 `agent_review.json` 中可见。

---

## 16. 禁止事项

1. 禁止提交预制答案或正式测试结果。
2. 禁止伪造来源、引文、数字、case_id、benchmark 分数。
3. 禁止手工改写 `claims.json`、`evidence_table.json`、`result.json` 的结构字段。
4. 禁止把 `AUTO_EXTRACT` 基线当成已由 Agent 核验的最终结论。
5. 禁止把“方案没写”默认为“方案满足”。
6. 禁止把前瞻性资源合同表述成实际供应商报价或实际审批结果。
7. 禁止联网、使用未声明依赖、使用 symlink。
8. 禁止在预算接近耗尽时仍反复重跑；应立即 finalize 合法 `result.json`。

---

## 17. 最终验收标准

每个案例运行结束后，评审应能：

- 从 `result.json` 直接看到 case_id、status、逐版本结论、条件清单、缺项和风险。
- 从 `check_matrix.csv` 看到七类约束是否逐项审查。
- 从 `protocol.md` 看到可执行方案或明确缺口。
- 从 `evidence_table.json` 复核每条判断的原文依据。
- 从 `pending_human.json` 看到哪些是必须由 PI/伦理/设备管理员确认的项。
- 从 `deliverable.md` 看到两个或三个候选版本中哪个更可行、还缺什么。
- 同一输入换一个 Agent 复跑时，能获得可比较的结构、相似结论和可追踪的证据链。