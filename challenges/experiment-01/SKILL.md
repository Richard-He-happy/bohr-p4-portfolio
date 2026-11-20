---
name: experiment-plan-builder
description: 让 Harness Agent 从研究目标、真实科学材料、资源/价格/预订契约、有限参数域和版本化候选方案中生成、比较、修订并核验可排期、可计价、可复核的湿实验方案。脚本只生成基线骨架；最终交付物必须由 Agent 亲自解析材料、推导并撰写/制作。
version: 2.0.0
license: MIT
---

# 实验方案生成与优化 Skill（Harness Agent 执行手册）

本 SKILL.md 是给 Harness Agent 使用的执行手册。`scripts/build_plan.py` 与 `scripts/plan_core.py` 只是生成基线骨架和做初步算术的工具；**最终交付物必须由你（Agent）亲自读材料、推导、核验、撰写/制作**。禁止直接把脚本默认输出当作完整成品；禁止依据文件名或领域标签猜测材料内容。必须真实解析材料原文，所有方案内容都要能回指输入中的事实节点或明确标为 `principle` / `missing` / `pending_human`。

---

## 1. 运行契约与交付物

### 1.1 输入与输出

- 输入目录：`/input`
  - `case.json`：任务与资源/价格/预订契约，可能包含候选方案、参数域、预算、时间窗、`output_contract`
  - `task.md`：题面任务说明、运行时契约、评分要求
  - 题面规定的材料：PDF / DOCX / CSV / 图片等，必须真实解析
- 工作目录：`/app/work`
- 输出目录：`/app/output`
  - `result.json`（必需）
  - `protocol.md`（必需，完整可执行方案正文）
  - `risk_table.csv`（必需，风险与异常处置逐项表）

### 1.2 基线脚本调用

先运行：

`python3 -B scripts/build_plan.py --input /input --output /app/output`

脚本只读 `--input`，只写 `--output`，不联网，退出码恒为 0。它会生成全套基线产物和合法 `result.json` 骨架。可选参数：`--mode auto|generate|revise`（默认 auto）、`--version`。

### 1.3 最终交付物

- `result.json` 必须包含原 `output_contract` 的全部字段（键名不改）与 `case_id`，并包含原输出契约字段表（见第 7 节）。
- `protocol.md` 必须是人可照做/排期的方案正文，而不是模板占位符。
- `risk_table.csv` 必须逐项列出失败模式、判据、止损点与替代路径。
- 可编辑 Office/幻灯片/图形产物若涉及，必须额外生成真实渲染的 PDF/PNG 预览；本 Skill 主产物为 md/csv/json，通常无需预览，但如果 Agent 额外制作了图或幻灯片，必须渲染预览。

---

## 2. 本题专属执行流程

按顺序执行。每一步写清输入、动作、输出、失败分支。**任何情况下先落盘 honest partial，再增量改进。**

### 步骤 0：先落盘脚本基线

- 输入：`/input` 目录、`scripts/build_plan.py`
- 动作：立即运行 `python3 -B scripts/build_plan.py --input /input --output /app/output`。即使不确定输入是否完整，也先让脚本产出全套基线产物。
- 输出：`/app/output/result.json`、`/app/output/protocol.md`、`/app/output/risk_table.csv` 的基线版本。
- 失败分支：脚本若报错，仍应写出 `result.json` 骨架；如果 `/app/output` 为空，则手动创建含 `case_id`、`status: partial`、`errors` 的最小合法 `result.json`。退出码仍保持 0。

### 步骤 1：盘点输入

- 输入：`/input` 目录
- 动作：
  1. 列 `/input` 文件清单。
  2. 读 `task.md`，提取 Runtime contract、输出要求、评分维度。
  3. 读 `case.json`，提取 `case_id`、研究目标、设备/试剂/价格/预订契约、参数域、预算、时间窗、候选方案、`output_contract`。
  4. 识别全部材料文件（PDF/DOCX/CSV/图片等）。注意：不能只记文件名，不能凭扩展名假设内容。
- 输出：输入清单、识别出的材料列表、契约字段清单。
- 失败分支：无 `case.json` 或坏 JSON：记录 `input_error`，继续用 `task.md` 和其他材料；产出骨架方案。

### 步骤 2：用工具真实解析材料

- 输入：步骤 1 识别出的材料文件
- 动作：
  1. 优先使用 `environment/resources.yaml` 中列出的解析工具。对 PDF 用 `pdf-text-tool` 或等价工具提取文本、表格；对 DOCX 提取正文；对 CSV 读取真实行；对图片如有 OCR 工具则提取文本。
  2. 逐个材料提取与本题相关的事实：研究目标、假设、变量、设备型号/量程、试剂规格/单价/库存、价格或预订窗口、参数允许域、候选方案步骤、风险相关说明。
  3. 为每个材料记录：文件名、sha256 前 16 位、解析工具、关键原文摘录、页码或定位。
- 输出：材料事实笔记（可放在 `/app/work` 或内存），每条事实带引用。
- 失败分支：工具不可用或材料损坏/格式不支持，登记 `sources` 与 `parse_failed`，相关事实字段标 `missing` / `pending_human`；**不得猜测内容**。

### 步骤 3：构建并核对证据

- 输入：材料事实笔记 + `case.json` 内容
- 动作：
  1. 将材料中的事实与 `case.json` 中的设备量程、试剂单价、库存、预订可用量、预算、时间窗、参数域交叉核对。
  2. 重点核对：材料中的参数是否在允许域内；价格与报价单是否一致；预订时间是否足够；候选方案步骤是否与材料一致。
  3. 每条关键事实生成 `evidence`，格式含 `locator`、`quote`、`source_ref`、`verified`。
- 输出：证据列表、冲突列表、不确定项列表。
- 失败分支：事实只有 `case.json` 无材料支撑，可标 `basis_type: input` 并注明；材料与 `case.json` 冲突，保留更保守或更原始的值，在 `uncertainty` 记录 `conflict`，必要时标 `pending_human`。

### 步骤 4：Agent 亲自产出完整成品

- 输入：步骤 3 的证据和脚本基线
- 动作：
  1. 在脚本基线上增强 `result.json`，补齐六类要素：假设与变量、对照组、设备材料、时间成本、参数范围、风险异常。
  2. 亲自重写/增强 `protocol.md`：明确排期表、步骤、设备与耗材型号/规格、参数范围、判读标准、风险与异常处置。
  3. 亲自增强 `risk_table.csv`：每行含失败模式、早期信号、缓解、止损点、替代路径、负责人、来源。
  4. 对每个候选方案做真实算术复核：试剂成本、机时成本、墙钟时间、样本量、预算上限、时间窗。不得直接照抄脚本数字而不理解。
  5. 修订方案时，不重写全部内容；如脚本已做裁剪/替换/降样本量，验证其规则与证据，并把修改记录写入 `changes`。
- 输出：增强后的 `result.json`、`protocol.md`、`risk_table.csv`
- 失败分支：某部分材料不足以确定，写入 `pending_human` 或 `uncertainty`，不编造参数、文献或价格；缺少关键参数不影响产出的，继续产出结构方案并标注缺口。

### 步骤 5：按 rubric 自检

- 输入：增强后的交付物
- 动作：
  1. 核对 `result.json` 是否包含原 `output_contract` 全部字段与 `case_id`。
  2. 逐项检查第 6 节 rubric 对照表。
  3. 运行第 7 节自检清单。
- 输出：自检结果，写入 `result.json.self_check`
- 失败分支：缺字段补字段；磁盘文件缺失补文件；如果时间或请求预算不足，将状态定为 `partial`，并逐项列出缺失。

### 步骤 6：回填 result.json 并 finalize

- 输入：自检后的交付物与原始输入
- 动作：
  1. 重读输入材料与 `case.json`，逐条复核 evidence 中的 `quote` 是否能复现。
  2. 将 `verified: true|false` 写回；无法复核的写 `verified: false` 并说明。
  3. 写 `status`、`runtime`、`version`、`changes`、`self_check`。
  4. 确认 `result.json`、`protocol.md`、`risk_table.csv` 都在 `/app/output`，且退出码为 0。
- 输出：最终合法交付物。
- 失败分支：即使有失败，也必须保留 partial，不得删除，退出码 0。

---

## 3. 预算策略（64 次模型请求 / 900 秒 / 单次响应 16384 tokens）

### 3.1 优先级

1. 最高优先级：**完整交付**。先确保 `/app/output` 有全套基线产物和合法 `result.json`。
2. 第二优先级：**实际效果**。补齐假设、变量、对照、设备材料、时间成本、参数范围、风险异常六类要素，使方案可排期、可执行。
3. 第三优先级：**可核验性**。每条关键设计都有证据定位与原文摘录，参数来源可复核。
4. 第四优先级：使用增益与创新增益证据写入 `changes` 与 `feasibility`。
5. 画面美化、重复解析、非必要的文献扩展可以跳过。

### 3.2 请求次数建议分配

- 步骤 0 运行基线脚本：1 次 Bash 工具调用
- 步骤 1 盘点输入：2-4 次请求
- 步骤 2 解析材料：每个材料 1-2 次工具调用，通常 3 个材料约 5-8 次请求
- 步骤 3 证据核对：5-8 次请求
- 步骤 4 方案增强与文件写入：8-12 次请求
- 步骤 5 自检：3-5 次请求
- 步骤 6 finalize：2-4 次请求

总计约 26-42 次请求，留足余量。

### 3.3 增量落盘规则

- 每完成一个大步骤，立即写回 `/app/output/result.json` 和 `protocol.md` / `risk_table.csv`，不要等全部完成。
- 如果已经使用 50 次以上请求，或剩余时间不足 300 秒，停掉所有非必要增强，只做 finalize。
- 不要重复读取大文件。先读脚本生成的关键行，再回查材料定位；不要用多次请求反复读同一整篇 PDF。

---

## 4. 隐藏案例鲁棒性

| 情况 | 处置 |
|---|---|
| 空输入 / 无 `case.json` | 运行脚本若失败则手动创建 `status: input_error` 骨架；`errors` 记录原因；退出 0 |
| 材料缺失 | 只依据 `case.json` 中明确字段；相关参数标 `missing` 或 `pending_human`，不猜 |
| 材料损坏 / 无法打开 | 登记 `sources` 与 `parse_failed`，不猜测内容；如果关键参数受影响，在 `uncertainty` 说明 |
| 格式不支持 | 尝试 environment/resources.yaml 中的可用工具；无法解析则记录工具缺失与现象 |
| 超时风险 | 先用脚本快速落盘；解析每个材料限时约 30 秒，超时则记 `parse_failed` 并继续 |
| `output_contract` 缺失 | 使用本文件第 7 节列出通用字段清单，并在 `self_check.contract_missing` 标注 |
| 约束冲突（时间窗与样本量冲突、试剂缺货、设备排期已满） | 不通过编造或硬压缩重复数“解决”冲突；在 `feasibility` 硬约束行给出数值，标 `not_feasible`，写 `pending_human` |
| 参数超量程或不在允许域 | 若输入给出规则或允许域，裁剪到最近允许值并记 `changes`；否则保留硬约束，标 `pending_human` |
| 任何其他异常 | 最终仍须产出合法 `result.json`，退出码 0，并在 `errors` / `degradations` 如实记录 |

**绝对禁止**：把材料标签当作已读内容；编造仪器量程、试剂目录号、文献、DOI、价格、统计量；在证据不足时写“经专家确认”“实际安全批准”等未发生声明。

---

## 5. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 任务完成度 | 15 | 方案确实从研究目标落成可排期、可执行的实验流程，不是复述目标 | `protocol.md` 排期表 + `steps` + `schedule`；每步有动作、设备/试剂、时长、关键参数 |
| 结果正确性 | 15 | 假设可检验；变量有操作定义与测量方式；对照组能排除混杂；参数在设备与试剂允许范围内 | `hypotheses` 含零假设/判据/反证条件；`variables` 有操作定义；`groups` 含空白/阴性/阳性并写明排除的混杂；`evidence` 中有材料原文 quote |
| 结果完整性 | 5 | 六类要素齐全：假设变量、对照、设备材料、时间成本、参数范围、风险异常 | `coverage.elements` 六项布尔为 true，或明确标 partial |
| 结果可核验性 | 5 | 方案版本、参数来源、金标准、运行记录可复核 | `evidence` 的 locator + quote + verified；`sources` 哈希；`changes` 版本链；`runtime`；`validation.gold_standard` |
| 使用增益-质量 | 15 | 同样输入下比基础 Agent 方案更正确、完整、可执行 | 展示脚本基线后 Agent 增强内容；`changes` 中记录裁剪、替代、补对照、降样本量等具体改进 |
| 使用增益-效率 | 5 | 减少澄清次数、返工轮次 | `pending_human` 只列真正阻塞项；`uncertainty` 给出解决路径；`status` 明确可用性 |
| 增益可验证性 | 5 | 公平对照证明质量/效率改善 | 保留脚本基线与 Agent 修改记录；不删除原始产物；`changes` 标注 before/after |
| 创新增益-新增能力 | 5 | 能按设备量程与预算裁剪参数、按目标反推对照、生成风险备用路径 | `changes` 中 clip/substitute/reduce_replicates 规则与证据；`risks.fallback`；`groups` 的四类对照 |
| 创新增益-方法改进 | 5 | 从目标到假设、变量、对照、参数、资源的生成方法有实质改进 | 说明六类要素如何从材料推出；每个推导写 `basis_type` |
| 创新增益-创新证据 | 5 | 说明创新点相对现有能力的边界与价值 | `result.json` 的 `summary` 或 `validation` 写清方法改进；不空洞自夸 |
| 可靠体验-调用易用性 | 3 | Agent 能正确触发，说明输入输出与用法 | 本文件第 1 节与第 2 节 |
| 可靠体验-运行稳定性 | 4 | 不同实验体系、资源条件下持续可用 | 语义匹配输入键名；标准库运行；隐藏案例分支见第 4 节 |
| 可靠体验-异常处理 | 3 | 缺失、冲突、依赖不可用等能识别并处置 | `feasibility` 硬约束台账；`pending_human`；`errors` / `degradations` |
| 生态贡献-文档完整性 | 3 | 输入清单、输出结构、依赖、示例、适用范围、限制齐全 | 本文件；`result.json` 的字段说明 |
| 生态贡献-资源可复用性 | 4 | 清单、模板、检查表可复用 | `references/catalog.json`、`references/protocol_template.md`、`references/checklists.md` |
| 生态贡献-分享推广 | 3 | 有案例、清单、实践价值 | `references/checklists.md` 与 `protocol_template.md` 可直接被其他 Agent 使用 |

---

## 6. 自检清单（提交前逐项检查）

- [ ] `/app/output/result.json` 存在且合法 JSON；包含 `case_id` 与原 `output_contract` 全部字段，缺值用 `null` 或 `[]`
- [ ] `/app/output/protocol.md` 存在且非空，不是模板占位符，不含未替换的 `{{...}}`
- [ ] `/app/output/risk_table.csv` 存在且非空，列名为 `risk_id, code, failure_mode, likelihood, impact, early_signal, mitigation, stop_condition, fallback, owner, source_ref`
- [ ] 六类要素全部覆盖，`coverage.elements` 无 false；若有 false 则 `status=partial` 并列出缺失
- [ ] 每个关键设计/参数/价格/预算都有 `evidence`，且 `quote` 能在输入材料中复现，`verified` 已更新
- [ ] `sources` 包含所有输入材料及 sha256 前 16 位，解析失败材料已标 `parse_failed`
- [ ] 算术自检通过：材料小计之和 = 材料成本；n × 组数 = 合计样本；机时成本 = 用时 × 机时费；机时需用 ≤ 可用
- [ ] `changes` 版本链完整，裁剪/替换/降样本量有 before/after/rule/evidence
- [ ] `status` 与实际一致：`ok` 仅当无阻塞、六类要素齐备；否则用 `partial` 或 `input_error`
- [ ] 不确定项已在 `uncertainty` 列明；阻塞项已在 `pending_human` 列明；没有编造数值、引用、DOI、批准意见
- [ ] 运行脚本产生的基线产物未被删除或清空；Agent 增强内容已写入 `reviewed_by_agent` 或相应字段
- [ ] 任何情况下退出码为 0

---

## 7. 保留的脚本调用、输出契约字段与目录约定

### 7.1 脚本调用

```bash
python3 -B scripts/build_plan.py