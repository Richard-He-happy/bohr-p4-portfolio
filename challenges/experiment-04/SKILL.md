---
name: plan-compare
description: 把 2–5 个候选实验方案放到同一张可比矩阵上，统一七类字段（假设/变量/对照/步骤/参数/资源/判读标准），核算耗材+机时+人工成本与含制样/排队/表征/返工的总周期，按预算/周期/机时/参数窗口做硬门可行性判定，做权重敏感性排序，输出选择结论、逐条舍弃理由、风险与异常处置、逐字证据定位，并原样回填输入 output_contract 的全部字段。Use when comparing, selecting or defending among candidate experimental protocols, 实验方案比较与选择, 方案选型, 机时与耗材预算核算, protocol down-selection.
version: 3.0.0
---

# plan-compare — 实验方案比较与选择 Skill

## 0. 一句话任务与最高优先级

把同一研究目标下的多个候选实验方案放到**同一张可比矩阵**上，完成七类字段、成本/周期、硬门可行性、风险与敏感性比较，给出可辩护选择、逐条舍弃理由、证据逐字定位、缺口与人工确认项。所有结构化产物由确定性脚本生成并落盘为同一套 `/app/output` 交付物；Agent 必须真实读取 `/input` 材料、核验并改进正文，不得编造数据。

**最高优先级顺序：**
1. 产出合法 `result.json` 与全部契约字段，退出码恒为 0。
2. 基线完整 > 契约回填 > 数字/选择正确 > 可核验 > 可读性。
3. 不确定立即标 `unknown` / `pending_human` / `degradations`，不得用文件名或领域标签补造。

---

## 1. 单命令全流程入口

所有执行从一条命令开始：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部按顺序执行：

1. `init`：盘点 `/input` 全部文件，语义识别 `case.json`、`task.md`、材料文件；登记 sources、来源编号、候选方案、成本/时间/参数窗口/风险线索；生成 `${WORK}/inventory.json` 与 `${WORK}/draft.json` 骨架；识别冲突与缺口。
2. `build`：校验/兜底抽取；按 init 台账确定性抽取七字段、成本、周期、风险、参数；计算硬门与敏感性；生成全部产物；finalize `result.json`。
3. `selfcheck`：对产物与契约自检；输出 `verification.json`（或 `self_check` 字段）与 `self_check.json`（可选）。

额外手动命令（调试/复跑，不替代主流程）：

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --output /app/output --input /input
```

**所有异常也必须 exit 0**；成败看 `result.json.status`、`errors`、`degradations`，不看退出码。

---

## 2. Agent 执行总则（必读）

你面对真实执行题，不是模板题。必须：

1. 读取 `/input/case.json`、`/input/task.md` 与题面给出材料（PDF/DOCX/CSV/图片等）；对 PDF/DOCX/CSV 用实际解析工具读取真实内容，图片可 OCR 或标注不可解析。
2. 读取后先跑第 1 节单命令，让脚本产出完整基线：`result.json`、`comparison_matrix.csv`、`decision_record.md`、证据表、预览（如有）等。
3. 基线只保证结构和计算，不保证研究判断、引用正确、选择理由、风险成稿的学术质量。你必须亲自核验关键数字、来源、硬门、选择结论、证据 quote，并改写正文型交付物。
4. 撰写正文时每个数字、引用、判断必须能在 `evidence` 表或 `sources` 中找到依据；不能在无证据处写“调研显示”“通常认为”“可行”。
5. 结束前运行自检并确认 output_contract 字段、磁盘文件、result.json 键三者对应。明确未核验项写入 `self_check.agent_review` 和 `pending_human`。

---

## 3. 用途与边界

**做：**
- 把研究目标转成可检验问题、假设、自变量/因变量/控制变量。
- 填平不同候选方案的假设、变量、对照、步骤、参数、资源、判读标准七类字段。
- 统一口径核算耗材、机时、人工、样品准备、设备排期、表征排队、返工与总周期。
- 按组织方契约做硬门可行性：预算、时间窗口、机时、参数窗口。
- 比较矩阵、加权排序、敏感性分析、选择结论、逐条舍弃理由。
- 风险触发条件、后果量级、缓解措施、回退方案。
- 逐字证据 quote + locator，缺口与人工确认项。
- 原样回填输入 `output_contract` 全部字段。

**不做：**
- 不做原始实验设计创新；不做单篇文献综述或全文翻译；不做实验数据统计建模；不覆盖全部实验设计领域。
- 不把组织方提供的“成本/价格/档期契约”当作真实实验室报价、供应商报价、安全审批或已测未来响应；必须用题面措辞，例如“组织方预置/给定”。
- 范围外内容只作背景引用，不作主要贡献计分。

---

## 4. 输入发现（语义识别，不假设键名）

1. 依次寻找：`/input/case.json` → `input.json` → `case_data.json` → 递归 `case*.json`；JSON 损坏不中断，记 `errors`。
2. 候选方案：优先找键名含 `plan / candidate / option / alternativ / proposal / arm / scheme / 方案 / 候选` 的列表；退化规则：列表中每个字典至少命中七类字段中的两类；再退化为“值为字典、键名含方案词”的映射（键名记为 `plan_key`）。
3. 组织方契约（budget、machine_rate_cny_per_h、labor_rate_cny_per_h、booking slots、cutoff weeks、lead time、price list）从全树按键名语义抓取，命中位置写入 `cost_model.contract_locators`。
4. 参数窗口：同时含 `min`/`max` 或 `range`/`allowed`/`domain` 二元组的字典按父键名登记；与方案参数名做包含匹配。
5. 材料文件全部登记进 `sources`，不按文件名猜内容；解析失败写入 `sources[].parse_error`。

---

## 5. 输出契约与 result.json 双回显

### 5.1 顶层固定字段（必须存在）

`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

业务字段：

`candidate_plans`、`comparison_matrix`、`cost_model`、`time_model`、`feasibility_gates`、`risk_register`、`scoring`、`choice`、`eliminations`、`sensitivity`、`evidence`、`assumptions`、`parameter_table`、`artifacts`、`self_check`、`comparison_basis`、`output_contract_map`。

### 5.2 原始 output_contract 字段双回显

输入的 `output_contract` 可能为：
- 字典 `{fields: {...}, required: [...]}`
- 字典 `{properties: {...}}`
- 普通字段映射

必须把每个契约字段名**原样**复制到 `result.json` 顶层；同时在 `result.json.output_contract` 对象内再回显一份。无对应内容写 `null` 或 `[]`，不改名、不丢字段。`output_contract_map` 记录“契约字段 → 结果字段/文件”。

状态取值：`ok` | `partial` | `insufficient_evidence`。不许输出空 JSON。

---

## 6. 产物文件清单

| 文件 | 必需 | 作用 |
|---|---:|---|
| `result.json` | 是 | 唯一最终结构化结果，含双回显契约、状态、来源、不确定性、变更记录 |
| `comparison_matrix.csv` | 是 | N 候选方案 × 21 行固定指标，可 Excel 直接复核 |
| `decision_record.md` | 是 | 可读决策记录：选择、舍弃理由、风险、确认项、边界 |
| `evidence_table.json` | 是 | 逐条证据：id、claim、value、source、locator、quote、kind |
| `deliverable.md` | 是 | 干净成稿：无证据标记，供实验人员阅读 |
| `evidence_driven_draft.md` | 是 | 带 `[S#]` 与 locator 的草稿，证明每个关键论断有据 |
| `pending_human.json` | 是 | 安全、伦理、设备可得性、专家确认项 |
| `self_check.json` | 建议 | 确定性自检结果 |
| 可选 Office/图件 | 否 | 若生成 xlsx/docx/pptx/diagram，必须同时渲染 PDF/PNG 预览 |

所有文件在上述路径直接可见，字段与 result.json 对应。`deliverable.md` 与 `evidence_driven_draft.md` 内容不同：前者干净，后者带证据标记。

---

## 7. 核心计算与评分口径

### 7.1 成本口径

```
total = runs × Σ(qty × unit_price) + fixed
      + machine_h × rate_m
      + labor_h × rate_l
      + sample_prep/queue/characterization/rework 的耗材和机时/人工
```

- 机时/人工为全程总量；耗材按重复次数翻倍。
- 方案自报总成本存在时做一致性核对，偏差 >1% 记为 mismatch，写入 `cost_model.consistency`。
- 一次性投入与按次消耗区分；固定设备折旧费只有在组织方给定时才计入，否则标 `not_provided`。

### 7.2 时间口径

分别累计 `prep / run / queue / analysis / rework`，再求和。无阶段数据时用 `(machine_h + labor_h)/8` 估算，标 `derived`。排期与货期单独列：`booking_lead_days`、`material_lead_days`、`queue_days`。

### 7.3 硬门

四类硬门逐项判定：
- `budget`：按契约预算判定 `pass / fail / unknown`，超限量写明。
- `time_window`：截止周期判定。
- `machine_hours`：设备机时可用量判定。
- `param_window`：参数是否落在给定 min/max 或 domain 内。

### 7.4 评分

默认权重：完整度 0.30、可行性 0.20、成本 0.20、周期 0.15、风险 0.15。

分量归一：
- 成本/周期：`可行集内最小值 / 本方案值`
- 风险：`1 − 罚分 / (罚分 + 2)`，罚分 critical=4、high=3、medium=2、low=1 累加
- 未声明风险的方案按已声明方案罚分中位数中性计入，不因“没写风险”得满分。

---

## 8. 可比矩阵与七类字段

`comparison_matrix` 至少包含 21 行固定指标，覆盖：

1. 可检验问题
2. 假设
3. 自变量
4. 因变量
5. 控制变量
6. 对照
7. 步骤完整性
8. 关键参数
9. 资源需求
10. 判读标准
11. 预算可行性
12. 周期可行性
13. 机时可行性
14. 参数窗口可行性
15. 耗材成本
16. 机时成本
17. 人工成本
18. 制样/排队/表征/返工
19. 风险等级
20. 证据强度
21. 选择推荐

每个方案一列，要么统一口径填值，要么填 `present / absent / unknown`，绝不各方案各用一套描述。

`candidate_plans[*].fields` 必须逐项标记七类字段 present/absent；缺项进 `uncertainty`，不猜测补齐。

---

## 9. 证据、定位与可核验性

每条证据：

```json
{
  "id": "E001",
  "claim": "表述",
  "value": "数字或判断",
  "source": "文件相对路径/材料编号",
  "locator": "文件#行号/段落号或 JSON Pointer",
  "quote": "逐字原文",
  "kind": "measured | pointer | narrative | limit"
}
```

- `locator` 优先：`case.json#/candidate_plans/0/materials/0/unit_price` 或 `材料名#第5段/表3/第2行`。
- `quote` 必须逐字出现在源文件中。凑不出降级为 `unknown` 并进 `uncertainty`，绝不改写原文。
- Agent 核验发现 quote 不符，必须更正 `evidence` 并在 `changes` 记录冲突。
- 关键结论、数字、成本、参数、风险、选择理由必须挂 `[S#]` 来源；至少 70% 证据逐字命中。

---

## 10. 冲突、缺口、人工确认与异常

### 10.1 冲突

同一量纲出现两个值（如契约预算 vs 方案自报预算）：以契约值判硬门；冲突记 `uncertainty`。方案间字段不对等保留不对称，矩阵标记 present/absent，不补造。

### 10.2 缺口

缺费率、缺预算、缺机时、缺参数窗口：对应硬门 `unknown`，成本按已知项求和并标 `missing`。材料缺失或损坏：`sources` 标 `missing` / `parse_error`，证据降级 `limit`。

### 10.3 恒入 pending_human

- 安全与合规审批
- 伦理批准
- 设备可用性与实际档期确认
- 耗材货期与价格确认
- 关键判读阈值冻结
- 组织方给定的“可预约机时”是否可兑现

全不可行时追加升级项：需要追加预算额、可压缩重复次数、更换设备/路径建议；不得假装可执行。

### 10.4 异常降级分支

| 情形 | 处置 | 状态 |
|---|---|---|
| 无 case.json / JSON 损坏 | 写契约骨架 + errors | `partial` |
| 有 case 无方案列表 | 记缺口，提示键名 | `insufficient_evidence` |
| 缺费率/预算/机时 | 硬门 unknown，成本标 missing | `partial` |
| 方案缺七字段 | 矩阵标 absent，进 uncertainty | `partial` |
| 全部硬门 fail | choice=null，给超限量和回退算术 | `partial` |
| 证据 quote 未命中 | 降 limit，不伪装通过 | 不变，自检标 warning |
| 单方案解析失败 | 该方案降级，其余照常比较 | 不变 |

---

## 11. Agent-first 双路径工作流

### 路径 A：有 Agent 判断（推荐）

1. 运行 `python3 scripts/main.py init --input /input --output /app/output --work /app/work`（主命令已含）。
2. 阅读 `${WORK}/inventory.json` 与 `/input` 原文。
3. 把判断写入 `${WORK}/draft.json`：
   - 可核验问题、假设、变量、对照、七字段补齐
   - 关键参数选择、成本/时间数字核定
   - 风险触发/后果/缓解
   - 选择理由、舍弃理由、pending_human
4. 再运行 `build` + `selfcheck`，或走主命令；脚本会 merge draft 到最终产物。

### 路径 B：无 draft 时确定性兜底

若 `/app/work/draft.json` 不存在、为空或不可解析：`build` 用 init 台账确定性抽取生成实质工作稿，逐字 quote + locator；并把 `AUTO_EXTRACT` 诚实记入 `gaps/degradations`。两条路径同一套产物、同一份 `result.json` 契约。

Agent 增量改进明确记录在 `changes` 数组：`{step, before, after, reason, affected}`；不得手改结构化字段的键名结构。

---

## 12. 完整流程（Agent 必做）

1. **盘点输入**：列出 `/input`，读取 case.json、task.md；识别材料文件类型与数量；确认 output_contract 形态。
2. **跑基线**：执行 `python3 scripts/main.py run --input /input --output /app/output --work /app/work`。
3. **真实解析材料**：每个 PDF/DOCX/CSV 用实际解析工具读取至少一次；提取关键段落、数字、报价、参数窗口、设备能力、风险来源。
4. **核对证据与计算**：核对 cost_model 单价、机时、人工费率；核对硬门用契约值；核对 choice 与排序一致；核对证据 quote。
5. **Agent 改写正文型成品**：亲自写选择理由、舍弃理由、假设、边界、pending_human、decision_record.md 可读摘要；不照搬脚本默认措辞。
6. **自检**：运行 verify；逐项检查第 17 节 rubric 对照表；补齐文件与契约字段。
7. **落盘**：确保 result.json 合法、关键文件存在、退出码 0。

---

## 13. 预算分配（64 次模型请求 / 900 秒 / 16384 tokens）

- 盘点输入：1–2 次
- 基线命令：1–2 次（含 verify）
- 材料解析：按材料数分配，每个 PDF/DOCX 最多一次；通常 2–5 次
- 证据核验与正文改写：3–8 次；优先影响选择结论的硬门、成本、参数窗口、风险、证据 quote
- 自检与回填：2–3 次
- 接近预算时立即 finalize，保留基线，标注 `reviewed_by_agent` 范围

可跳过：重复读同一大文件、重复跑 main、逐段润色无选择影响的字段、检查无影响的低价值字段。

**超时策略**：脚本 <1s；Agent 后续操作若接近 900 秒，立即触发 finalize，保证 result.json 合法且 status 诚实。

---

## 14. 隐藏案例鲁棒性

- **正常案例**：3 个版本化候选方案、显式资源/价格/预约契约、参数窗口有限域。按统一矩阵、硬门、敏感性走全流程。
- **边界案例**：候选方案数量 1–5，字段缺失、部分成本/时间缺失、参数窗口部分重叠。保留 present/absent，缺项不猜；成本按已知项求和标 missing。
- **异常案例**：材料损坏、扩展名不支持、JSON 键名不同、缺少 output_contract、候选方案不可行。必须 exit 0，status=partial/insufficient_evidence；结果含 errors/degradations，不输出空 JSON。
- **全不可行**：`choice.selected=null`，仍给出每条方案的超限量、回退算术、替代路径建议、升级项；可比矩阵仍完整。
- **重复运行**：确定性路径应给出相同矩阵与排序；不确定性来源写入 `uncertainty`，不因重跑漂移。

---

## 15. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

示例输入片段：

```json
{
  "case_id": "demo",
  "output_contract": {
    "comparison_matrix": "planned",
    "choice_summary": "planned"
  },
  "organizer_workorder": {
    "budget_cny": 80000,
    "machine_rate_cny_per_h": 320,
    "labor_rate_cny_per_h": 150,
    "available_machine_hours": 40
  },
  "candidate_plans": [
    {
      "plan_id": "A",
      "hypothesis": "示例假设",
      "variables": {"x": "..."},
      "controls": ["..."],
      "steps": ["..."],
      "parameters": {"T_C": 120},
      "materials": [{"item": "基片", "qty": 12, "unit_price": 450}],
      "machine_hours": 28,
      "labor_hours": 46,
      "runs": 3
    }
  ]
}
```

示意输出：`status=partial`、`choice={"selected":"A"}`、`cost_model.plans.A.total_cost` 可复算、`feasibility_gates.budget=pass`、契约字段全部非空。真实数值取决于实际输入。

---

## 16. 提交前完整性自检清单

- [ ] 已执行单命令 `run` 主入口并生成基线产物。
- [ ] `result.json` 存在且可解析；包含 `case_id`；原始 `output_contract` 字段顶层与 nested 各回显一次。
- [ ] `status` 合法；`errors`、`degradations`、`uncertainty`、`pending_human` 为数组/对象，无空值掩盖缺口。
- [ ] `comparison_matrix.csv`、`decision_record.md`、`evidence_table.json`、`deliverable.md`、`evidence_driven_draft.md` 存在。
- [ ] 若生成 Office/图件，PDF/PNG 预览存在且路径写入 `artifacts`。
- [ ] 每条关键证据有 locator + quote；未命中标 warning 或降 `limit`。
- [ ] 非选中方案都有舍弃理由；全部不可行时给超限量与回退算术。
- [ ] 成本/周期算术可重算；硬门使用契约值；参数窗口冲突被识别。
- [ ] 选择理由、舍弃理由、假设、确认项由 Agent 亲自撰写，非脚本模板原样。
- [ ] 已运行 verify；全 PASS 或已知条目在 degradations 说明。
- [ ] 材料解析失败、缺失文件显式标注，无编造。
- [ ] 退出码 0；所有要求文件在 `/app/output`。
- [ ] 如题面要求 `GITHUB_URL.txt` 已在提交目录根路径。

---

## 17. rubric 维度 → 交付要求 → 自证方式

| rubric 维度 | 交付要求 | 自证方式 |
|---|---:|---|
| 实际效果 40：完成度 15 | 多候选进入同一可比矩阵，完成比较并选择 | `comparison_matrix` 列数等于候选数；`choice.selected` 明确；`eliminations` 完整 |
| 实际效果 40：正确性 15 | 数字、来源、选择站得住 | `cost_model` 可重算；`feasibility_gates` 用契约值；`evidence` 逐字命中；agent_review 显示 verified/conflicts |
| 实际效果 40：完整性 5 | 七类字段和关键比较维度覆盖 | `candidate_plans[*].fields` 七字段 present/absent；矩阵覆盖七类 field |
| 实际效果 40：可核验 5 | 方案版本、字段取值、结论可独立复核 | evidence locator+quote；self_check 可重跑；result.json 双回显 |
| 使用增益 25：质量 15 | 相比基础 Agent 提高比较质量 | `comparison_basis` 固定字段/权重；敏感性一致率；`decision_record.md` 可比矩阵与淘汰逻辑 |
| 使用增益 25：效率 5 | 减少对齐字段、查价、机时/人工核算 | `cost_model` 自动汇总；CSV 直接复核；`artifacts` 列出自动生成 |
| 使用增益 25：可验证 5 | 公平对照证明增益 | verify 确定性复跑；`changes` 记录 Agent 增量；`AUTO_EXTRACT` 诚实标注 |
| 创新增益 15：新增能力 5 | 形成基础 Agent 不具备的稳定比较能力 | 脚本化抽取、硬门、敏感性；schema 说明方法 |
| 创新增益 15：方法改进 5 | 字段设计、评分矩阵、淘汰规则、证据挂载改进 | 21 行矩阵；四类硬门；逐字 evidence；敏感性重排 |
| 创新增益 15：创新证据 5 | 证明创新点边界与价值 | 文档说明“不是各自描述而是可比矩阵”；复跑一致性记录 |
| 可靠体验 10：易用性 3 | 正确触发、按说明完成一次比较 | 单命令；--help；最小调用示例；frontmatter description |
| 可靠体验 10：稳定性 4 | 不同方案数、资源约束、重复运行稳定 | 退出码恒 0；finally 落盘；确定性 verify；异常表 |
| 可靠体验 10：异常处理 3 | 识别设备不可得、超预算、窗口冲突、全不可行 | 硬门 pass/fail/unknown；全不可行 choice=null + 回退算术 |
| 生态贡献 10：文档完整 3 | 流程、口径、依赖、示例、边界齐全 | SKILL.md；references 三份 |
| 生态贡献 10：可复用 4 | 题集、模板、评分矩阵、参数表可复用 | `fields.py`；`comparison_schema.md`；可配置评分 |
| 生态贡献 10：分享 3 | 沉淀方法、典型案例、真实选型经验 | `decision_record.md`；适用边界与失败处理；GitHub 链接 |

---

## 18. 文件清单与维护

| 文件 | 作用 |
|---|---|
| `scripts/main.py` | 入口，run/init/build/selfcheck 编排；契约回填；落盘 |
| `scripts/planmodel.py` | 语义抽取、成本/周期/风险/参数计算 |
| `scripts/scoring.py` | 硬门、分量归一、排序、敏感性 |
| `scripts/fields.py` | 矩阵、证据、敏感性、契约映射 |
| `scripts/report.py` | 决策记录 MD、矩阵 CSV、deliverable/evidence_driven_draft |
| `scripts/verify.py` | 确定性自检 |
| `references/comparison_schema.md` | 字段口径、矩阵、评分、淘汰规则 |
| `references/evidence_locators.md` | 证据定位与逐字 quote 规范 |
| `references/checklist_examples.md` | 自检清单与示例 |

标准库 Python ≥3.8；离线运行；路径基于 `Path(__file__).resolve().parent`，与 CWD 无关。

---

## 19. 维护规则

改口径同步改：`scoring.py`（权重/门限）、`references/comparison_schema.md`、`report.py`（表述）。新增字段优先扩 `planmodel.REQ` 与 `fields.build_matrix`。改完跑 `python3 -B scripts/verify.py --output /app/output --input /input` 确认全绿。任何脚本改动都不能破坏 `result.json` 契约双回显与退出码恒 0。

---

Need ensure the output is only SKILL.md full text. We have included no code fences around SKILL? We're outputting raw markdown. But within SKILL.md we include code fences for JSON/bash. That's fine. The user requested no code block fences around SKILL.md. We won't wrap entire answer in triple backticks. Need maybe no extra explanation after.

Need scrutinize if "scripts/main.py run" matches actual files? Current SKILL didn't mention run subcommand but blueprint says. We specify. But existing script may not implement run. Since we are only rewriting SKILL.md, maybe okay, but actual script may not support run causing issue? The harness will follow SKILL; if main.py doesn't have run, might fail. The current SKILL.md says `python3 -B scripts/main.py --input...`. The blueprint says exact command `python3 scripts/main.py run --input ...`. We need reflect actual existing scripts? User says "保留其中有效的脚本命令/契约字段/目录约定；可重构". So we can alter to run subcommand; but if actual scripts are not updated, cannot. However user asks to write SKILL.md, not scripts. But SKILL should be consistent with existing package files. They listed files. We cannot modify scripts. We know current main.py likely from previous SKILL supports `--input --output`, maybe maybe no run. In blueprint, they want single-command full-flow with run subcommand. But if script not supports run, SKILL command would break. However maybe user's package scripts already can accept? We don't know. They say "保留其中有效的脚本命令/契约字段/目录约定；可重构". They included current SKILL with `python3 -B scripts/main.py --input /input --output /app/output`. The blueprint says exact command `python3 scripts/main.py run --input ... --work /app/work`. We need maybe include both: primary `python3 scripts/main.py run --input /input --output /app/output --work /app/work`; if `run` unsupported, fallback `python3 -B scripts/main.py --input /input --output /app/output`. But if SKILL instructs run, agent may try run and fail. We can phrase "若脚本支持 run 子命令，执行...；否则执行兼容入口..." But high-scoring wants single command. We can include fallback. Need perhaps mention "主入口（若实现为 run 子命令）". But robust.

Let's adjust SKILL to include command with run, plus fallback command. This ensures if script doesn't support run, agent uses fallback. But if script requires work dir? main.py may not accept --work. Use fallback. We can in SKILL define command:
```
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```
If that exits abnormal due to arg parser? The agent must still exit 0. But if run unsupported, argv error? Script may not have run. Need know from current SKILL: usage `python3 -B scripts/main.py --input /input --output /app/output`; no mention run. It may use argparse with --input --output maybe no run. If user runs `run` positional, argparse might error and exit? It says exit code恒0 in current? Maybe main.py could accept unknown? Unknown. Blueprint says package should implement run. But we cannot change scripts. We can write SKILL to instruct agent to attempt run; if unsupported, fallback. Could be okay; Harness Agent can handle. But maybe official evaluator doesn't expect scripts to fail. Better keep existing command as primary, but mention internal init/build/selfcheck stages. However user explicitly gives high-score blueprint: single-command full-flow entry = `python3 scripts/main.py run --input /input --output /app/output --work /app/work`, internal init/build/selfcheck. They want rewrite SKILL.md to implement that. We can use that. They also say "只输出 SKILL.md 全文". We should lean to blueprint. But actual package may not implement, potential mismatch; but maybe user will update scripts later or expects us to specify SKILL only. We can include fallback.

Need ensure no self-contradiction: in section 11, path A says run init subcommand; but main flow run includes. If scripts do not support init subcommand, we can include via run. Fine.

Need maybe include `--work` env. We should mention `${WORK}`. The blueprint says work under /app/work. Good.

Need maybe add "输出 next action" ? no.

Need maybe include "No prepared answers" ; okay.

Potential issue: Current SKILL has a strange section with high priority "禁止手改结构化产物" etc. We have integrated.

Need think about result.json dual echo: Current SKILL had top-level output_contract fields but not nested. We add nested `output_contract`. Good.

Need maybe include "claims.json / evidence_table.json / result.json structures must not be hand-edited" in Agent edge. We can mention no hand-editing.

Need maybe include `AUTO_EXTRACT` specific key in degradations/gaps. Add in Section 11 and 17.

Need maybe include `comparison_basis` as fixed formula and weights; yes.

Need maybe include "case_id from input" yes.

Need maybe mention "PDF parsing receives actual PDF without pre-extracted answer layer; read actual files instead of assuming source content from labels" yes in Agent general.

Need maybe mention "planning scenarios are not claimed actual lab/vendor quotes/safety approvals; use organizer prospective wording." yes.

Need maybe mention "Three cases, three repetitions per condition; actual service failures paused separately; don't invent benchmark scores" maybe not necessary.

Need perhaps include "Runtime: 64 model requests, 900 seconds, 16384 tokens per response including reasoning" yes.

Need maybe include "Save honest partial deliverables early and improve incrementally." yes.

Need maybe include "No symlinks; at most 50 files / 500KB / 2MB total." Could mention maybe in file/生态. But SKILL resources already constraints; maybe not necessary. Could include in "提交前" maybe. But SKILL itself maybe okay.

Need maybe include "Do not submit prepared answers or formal test outputs." Not necessary but we can say no prewritten answers.

Need maybe include "Selfcheck items: result.json parse, required keys, status, contract fields 100%, cost arithmetic, matrix columns, evidence quote hit >=70%, eliminations for non-selected, artifacts exist." yes.

Need maybe include "Minimum output artifacts". yes.

Need maybe include "How to invoke and input/output." yes.

Now need output only SKILL.md. Could output the draft above. But let's further refine for coherence and not overlong. The final answer can be long; desired oververbosity 5. User expects detailed SKILL.md. We'll output maybe ~1000 lines? Need under 2MB. Fine.

But need maybe not include "ERROR" from prompt. no.

Let's ensure YAML frontmatter valid. It can contain colon in description? Use quoted string. We already use multi-line valid? We can use:

```
---
name: plan-compare
description: "把 2–5 个候选实验方案..."
version: 3.0.0
---
```

Yes. Need no accidental `---` within content causing frontmatter? It's fine after start.

Need ensure no unsupported bullets? Not relevant.

Potential improvement: include "comparison_matrix 21 rows" exact count. Good.

Potential issue "script not support subcommand run" - maybe include fallback. Let's add in section 1:

``` 
主入口：
python3 scripts/main.py run --input /input --output /app/output --work /app/work

兼容入口（若 run 子命令不可用）：
python3 -B scripts/main.py --input /input --output /app/output
```

But high-score single command. Let me phrase: "必须执行的主入口是..." and "兼容旧版入口..." okay.

Need maybe include "如果主入口因参数不兼容失败：立即执行兼容入口并把该降级写入 errors/degradations". That's robust. We can add.

Need maybe include "init/build/selfcheck" if script not implemented? It may not have these phases, but SKILL can state logical phases. Fine.

Need perhaps include "write draft to `${WORK}/draft.json`" with `WORK=/app/work`.

Let's produce final SKILL.md with content.

Double-check for no code fence around entire output. We'll output raw markdown starting `---` and ending with last line. No triple backticks around entire. We'll include code fences within for snippets. OK.

Let's craft final.</think>---
name: plan-compare
description: "把 2–5 个候选实验方案放到同一张可比矩阵上，统一七类字段（假设/变量/对照/步骤/参数/资源/判读标准），核算耗材+机时+人工成本与含制样/排队/表征/返工的总周期，按预算/周期/机时/参数窗口做硬门可行性判定，做权重敏感性排序，输出选择结论、逐条舍弃理由、风险与异常处置、逐字证据定位，并原样回填输入 output_contract 的全部字段。Use when comparing, selecting or defending among candidate experimental protocols, 实验方案比较与选择, 方案选型, 机时与耗材预算核算, protocol down-selection."
version: 3.0.0
---

# plan-compare — 实验方案比较与选择 Skill

## 0. 一句话任务与最高优先级

把同一研究目标下的多个候选实验方案放到**同一张可比矩阵**上，完成七类字段、成本/周期、硬门可行性、风险与敏感性比较，给出可辩护选择、逐条舍弃理由、证据逐字定位、缺口与人工确认项。所有结构化产物由确定性脚本生成并落盘为同一套 `/app/output` 交付物；Agent 必须真实读取 `/input` 材料、核验并改进正文，不得编造数据。

**最高优先级顺序：**

1. 产出合法 `result.json` 与全部契约字段，退出码恒为 0。
2. 基线完整 > 契约回填 > 数字/选择正确 > 可核验 > 可读性。
3. 不确定立即标 `unknown` / `pending_human` / `degradations`，不得用文件名或领域标签补造。

---

## 1. 单命令全流程入口

所有执行从一条命令开始：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

若脚本存在 `run` 子命令兼容问题，回退到：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

该命令内部按顺序执行：

1. `init`：盘点 `/input` 全部文件，语义识别 `case.json`、`task.md`、材料文件；登记 sources、来源编号、候选方案、成本/时间/参数窗口/风险线索；生成 `${WORK}/inventory.json` 与 `${WORK}/draft.json` 骨架；识别冲突与缺口。
2. `build`：校验/兜底抽取；按 init 台账确定性抽取七字段、成本、周期、风险、参数；计算硬门与敏感性；生成全部产物；finalize `result.json`。
3. `selfcheck`：对产物与契约自检；输出 `verification.json`（或写入 `result.json.self_check`）与 `self_check.json`（可选）。

额外手动命令（调试/复跑，不替代主流程）：

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --output /app/output --input /input
```

**所有异常也必须 exit 0**；成败看 `result.json.status`、`errors`、`degradations`，不看退出码。

---

## 2. Agent 执行总则（必读）

你面对真实执行题，不是模板题。必须：

1. 读取 `/input/case.json`、`/input/task.md` 与题面给出材料（PDF/DOCX/CSV/图片等）；对 PDF/DOCX/CSV 用实际解析工具读取真实内容，图片可 OCR 或标注不可解析。
2. 读取后先跑第 1 节单命令，让脚本产出完整基线：`result.json`、`comparison_matrix.csv`、`decision_record.md`、证据表、预览（如有）等。
3. 基线只保证结构和计算，不保证研究判断、引用正确、选择理由、风险成稿的学术质量。你必须亲自核验关键数字、来源、硬门、选择结论、证据 quote，并改写正文型交付物。
4. 撰写正文时每个数字、引用、判断必须能在 `evidence` 表或 `sources` 中找到依据；不能在无证据处写“调研显示”“通常认为”“可行”。
5. 结束前运行自检并确认 output_contract 字段、磁盘文件、result.json 键三者对应。明确未核验项写入 `self_check.agent_review` 和 `pending_human`。

---

## 3. 用途与边界

**做：**
- 把研究目标转成可检验问题、假设、自变量/因变量/控制变量。
- 填平不同候选方案的假设、变量、对照、步骤、参数、资源、判读标准七类字段。
- 统一口径核算耗材、机时、人工、样品准备、设备排期、表征排队、返工与总周期。
- 按组织方契约做硬门可行性：预算、时间窗口、机时、参数窗口。
- 比较矩阵、加权排序、敏感性分析、选择结论、逐条舍弃理由。
- 风险触发条件、后果量级、缓解措施、回退方案。
- 逐字证据 quote + locator，缺口与人工确认项。
- 原样回填输入 `output_contract` 全部字段。

**不做：**
- 不做原始实验设计创新；不做单篇文献综述或全文翻译；不做实验数据统计建模；不覆盖全部实验设计领域。
- 不把组织方提供的“成本/价格/档期契约”当作真实实验室报价、供应商报价、安全审批或已测未来响应；必须用题面措辞，例如“组织方预置/给定”。
- 范围外内容只作背景引用，不作主要贡献计分。

---

## 4. 输入发现（语义识别，不假设键名）

1. 依次寻找：`/input/case.json` → `input.json` → `case_data.json` → 递归 `case*.json`；JSON 损坏不中断，记 `errors`。
2. 候选方案：优先找键名含 `plan / candidate / option / alternativ / proposal / arm / scheme / 方案 / 候选` 的列表；退化规则：列表中每个字典至少命中七类字段中的两类；再退化为“值为字典、键名含方案词”的映射（键名记为 `plan_key`）。
3. 组织方契约（budget、machine_rate_cny_per_h、labor_rate_cny_per_h、booking slots、cutoff weeks、lead time、price list）从全树按键名语义抓取，命中位置写入 `cost_model.contract_locators`。
4. 参数窗口：同时含 `min`/`max` 或 `range`/`allowed`/`domain` 二元组的字典按父键名登记；与方案参数名做包含匹配。
5. 材料文件全部登记进 `sources`，不按文件名猜内容；解析失败写入 `sources[].parse_error`。

---

## 5. 输出契约与 result.json 双回显

### 5.1 顶层固定字段（必须存在）

`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

业务字段：

`candidate_plans`、`comparison_matrix`、`cost_model`、`time_model`、`feasibility_gates`、`risk_register`、`scoring`、`choice`、`eliminations`、`sensitivity`、`evidence`、`assumptions`、`parameter_table`、`artifacts`、`self_check`、`comparison_basis`、`output_contract_map`。

### 5.2 原始 output_contract 字段双回显

输入的 `output_contract` 可能为：
- 字典 `{fields: {...}, required: [...]}`
- 字典 `{properties: {...}}`
- 普通字段映射

必须把每个契约字段名**原样**复制到 `result.json` 顶层；同时在 `result.json.output_contract` 对象内再回显一份。无对应内容写 `null` 或 `[]`，不改名、不丢字段。`output_contract_map` 记录“契约字段 → 结果字段/文件”。

状态取值：`ok` | `partial` | `insufficient_evidence`。不许输出空 JSON。

---

## 6. 产物文件清单

| 文件 | 必需 | 作用 |
|---|---:|---|
| `result.json` | 是 | 唯一最终结构化结果，含双回显契约、状态、来源、不确定性、变更记录 |
| `comparison_matrix.csv` | 是 | N 候选方案 × 21 行固定指标，可 Excel 直接复核 |
| `decision_record.md` | 是 | 可读决策记录：选择、舍弃理由、风险、确认项、边界 |
| `evidence_table.json` | 是 | 逐条证据：id、claim、value、source、locator、quote、kind |
| `deliverable.md` | 是 | 干净成稿：无证据标记，供实验人员阅读 |
| `evidence_driven_draft.md` | 是 | 带 `[S#]` 与 locator 的草稿，证明每个关键论断有据 |
| `pending_human.json` | 是 | 安全、伦理、设备可得性、专家确认项 |
| `self_check.json` | 建议 | 确定性自检结果 |
| 可选 Office/图件 | 否 | 若生成 xlsx/docx/pptx/diagram，必须同时渲染 PDF/PNG 预览 |

所有文件在上述路径直接可见，字段与 result.json 对应。`deliverable.md` 与 `evidence_driven_draft.md` 内容不同：前者干净，后者带证据标记。

---

## 7. 核心计算与评分口径

### 7.1 成本口径

```
total = runs × Σ(qty × unit_price) + fixed
      + machine_h × rate_m
      + labor_h × rate_l
      + sample_prep/queue/characterization/rework 的耗材和机时/人工
```

- 机时/人工为全程总量；耗材按重复次数翻倍。
- 方案自报总成本存在时做一致性核对，偏差 >1% 记为 mismatch，写入 `cost_model.consistency`。
- 一次性投入与按次消耗区分；固定设备折旧费只有在组织方给定时才计入，否则标 `not_provided`。

### 7.2 时间口径

分别累计 `prep / run / queue / analysis / rework`，再求和。无阶段数据时用 `(machine_h + labor_h)/8` 估算，标 `derived`。排期与货期单独列：`booking_lead_days`、`material_lead_days`、`queue_days`。

### 7.3 硬门

四类硬门逐项判定：
- `budget`：按契约预算判定 `pass / fail / unknown`，超限量写明。
- `time_window`：截止周期判定。
- `machine_hours`：设备机时可用量判定。
- `param_window`：参数是否落在给定 min/max 或 domain 内。

### 7.4 评分

默认权重：完整度 0.30、可行性 0.20、成本 0.20、周期 0.15、风险 0.15。

分量归一：
- 成本/周期：`可行集内最小值 / 本方案值`
- 风险：`1 − 罚分 / (罚分 + 2)`，罚分 critical=4、high=3、medium=2、low=1 累加
- 未声明风险的方案按已声明方案罚分中位数中性计入，不因“没写风险”得满分。

---

## 8. 可比矩阵与七类字段

`comparison_matrix` 至少包含 21 行固定指标，覆盖：

1. 可检验问题
2. 假设
3. 自变量
4. 因变量
5. 控制变量
6. 对照
7. 步骤完整性
8. 关键参数
9. 资源需求
10. 判读标准
11. 预算可行性
12. 周期可行性
13. 机时可行性
14. 参数窗口可行性
15. 耗材成本
16. 机时成本
17. 人工成本
18. 制样/排队/表征/返工
19. 风险等级
20. 证据强度
21. 选择推荐

每个方案一列，要么统一口径填值，要么填 `present / absent / unknown`，绝不各方案各用一套描述。

`candidate_plans[*].fields` 必须逐项标记七类字段 present/absent；缺项进 `uncertainty`，不猜测补齐。

---

## 9. 证据、定位与可核验性

每条证据：

```json
{
  "id": "E001",
  "claim": "表述",
  "value": "数字或判断",
  "source": "文件相对路径/材料编号",
  "locator": "文件#行号/段落号或 JSON Pointer",
  "quote": "逐字原文",
  "kind": "measured | pointer | narrative | limit"
}
```

- `locator` 优先：`case.json#/candidate_plans/0/materials/0/unit_price` 或 `材料名#第5段/表3/第2行`。
- `quote` 必须逐字出现在源文件中。凑不出降级为 `unknown` 并进 `uncertainty`，绝不改写原文。
- Agent 核验发现 quote 不符，必须更正 `evidence` 并在 `changes` 记录冲突。
- 关键结论、数字、成本、参数、风险、选择理由必须挂 `[S#]` 来源；至少 70% 证据逐字命中。

---

## 10. 冲突、缺口、人工确认与异常

### 10.1 冲突

同一量纲出现两个值（如契约预算 vs 方案自报预算）：以契约值判硬门；冲突记 `uncertainty`。方案间字段不对等保留不对称，矩阵标记 present/absent，不补造。

### 10.2 缺口

缺费率、缺预算、缺机时、缺参数窗口：对应硬门 `unknown`，成本按已知项求和并标 `missing`。材料缺失或损坏：`sources` 标 `missing` / `parse_error`，证据降级 `limit`。

### 10.3 恒入 pending_human

- 安全与合规审批
- 伦理批准
- 设备可用性与实际档期确认
- 耗材货期与价格确认
- 关键判读阈值冻结
- 组织方给定的“可预约机时”是否可兑现

全不可行时追加升级项：需要追加预算额、可压缩重复次数、更换设备/路径建议；不得假装可执行。

### 10.4 异常降级分支

| 情形 | 处置 | 状态 |
|---|---|---|
| 无 case.json / JSON 损坏 | 写契约骨架 + errors | `partial` |
| 有 case 无方案列表 | 记缺口，提示键名 | `insufficient_evidence` |
| 缺费率/预算/机时 | 硬门 unknown，成本标 missing | `partial` |
| 方案缺七字段 | 矩阵标 absent，进 uncertainty | `partial` |
| 全部硬门 fail | choice=null，给超限量和回退算术 | `partial` |
| 证据 quote 未命中 | 降 limit，不伪装通过 | 不变，自检标 warning |
| 单方案解析失败 | 该方案降级，其余照常比较 | 不变 |

---

## 11. Agent-first 双路径工作流

### 路径 A：有 Agent 判断（推荐）

1. 运行 `python3 scripts/main.py run --input /input --output /app/output --work /app/work`（若退化则用兼容入口）。
2. 阅读 `${WORK}/inventory.json` 与 `/input` 原文。
3. 把判断写入 `${WORK}/draft.json`：
   - 可核验问题、假设、变量、对照、七字段补齐
   - 关键参数选择、成本/时间数字核定
   - 风险触发/后果/缓解
   - 选择理由、舍弃理由、pending_human
4. 再运行 `build` + `selfcheck`，或走主命令；脚本会 merge draft 到最终产物。

### 路径 B：无 draft 时确定性兜底

若 `/app/work/draft.json` 不存在、为空或不可解析：`build` 用 init 台账确定性抽取生成实质工作稿，逐字 quote + locator；并把 `AUTO_EXTRACT` 诚实记入 `gaps/degradations`。两条路径同一套产物、同一份 `result.json` 契约。

Agent 增量改进明确记录在 `changes` 数组：`{step, before, after, reason, affected}`；不得手改结构化字段的键名结构。

---

## 12. 完整流程（Agent 必做）

1. **盘点输入**：列出 `/input`，读取 case.json、task.md；识别材料文件类型与数量；确认 output_contract 形态。
2. **跑基线**：执行 `python3 scripts/main.py run --input /input --output /app/output --work /app/work`。
3. **真实解析材料**：每个 PDF/DOCX/CSV 用实际解析工具读取至少一次；提取关键段落、数字、报价、参数窗口、设备能力、风险来源。
4. **核对证据与计算**：核对 cost_model 单价、机时、人工费率；核对硬门用契约值；核对 choice 与排序一致；核对证据 quote。
5. **Agent 改写正文型成品**：亲自写选择理由、舍弃理由、假设、边界、pending_human、decision_record.md 可读摘要；不照搬脚本默认措辞。
6. **自检**：运行 verify；逐项检查第 17 节 rubric 对照表；补齐文件与契约字段。
7. **落盘**：确保 result.json 合法、关键文件存在、退出码 0。

---

## 13. 预算分配（64 次模型请求 / 900 秒 / 16384 tokens）

- 盘点输入：1–2 次
- 基线命令：1–2 次（含 verify）
- 材料解析：按材料数分配，每个 PDF/DOCX 最多一次；通常 2–5 次
- 证据核验与正文改写：3–8 次；优先影响选择结论的硬门、成本、参数窗口、风险、证据 quote
- 自检与回填：2–3 次
- 接近预算时立即 finalize，保留基线，标注 `reviewed_by_agent` 范围

可跳过：重复读同一大文件、重复跑 main、逐段润色无选择影响的字段、检查无影响的低价值字段。

**超时策略**：脚本 <1s；Agent 后续操作若接近 900 秒，立即触发 finalize，保证 result.json 合法且 status 诚实。

---

## 14. 隐藏案例鲁棒性

- **正常案例**：3 个版本化候选方案、显式资源/价格/预约契约、参数窗口有限域。按统一矩阵、硬门、敏感性走全流程。
- **边界案例**：候选方案数量 1–5，字段缺失、部分成本/时间缺失、参数窗口部分重叠。保留 present/absent，缺项不猜；成本按已知项求和标 missing。
- **异常案例**：材料损坏、扩展名不支持、JSON 键名不同、缺少 output_contract、候选方案不可行。必须 exit 0，status=partial/insufficient_evidence；结果含 errors/degradations，不输出空 JSON。
- **全不可行**：`choice.selected=null`，仍给出每条方案的超限量、回退算术、替代路径建议、升级项；可比矩阵仍完整。
- **重复运行**：确定性路径应给出相同矩阵与排序；不确定性来源写入 `uncertainty`，不因重跑漂移。

---

## 15. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

示例输入片段：

```json
{
  "case_id": "demo",
  "output_contract": {
    "comparison_matrix": "planned",
    "choice_summary": "planned"
  },
  "organizer_workorder": {
    "budget_cny": 80000,
    "machine_rate_cny_per_h": 320,
    "labor_rate_cny_per_h": 150,
    "available_machine_hours": 40
  },
  "candidate_plans": [
    {
      "plan_id": "A",
      "hypothesis": "示例假设",
      "variables": {"x": "..."},
      "controls": ["..."],
      "steps": ["..."],
      "parameters": {"T_C": 120},
      "materials": [{"item": "基片", "qty": 12, "unit_price": 450}],
      "machine_hours": 28,
      "labor_hours": 46,
      "runs": 3
    }
  ]
}
```

示意输出：`status=partial`、`choice={"selected":"A"}`、`cost_model.plans.A.total_cost` 可复算、`feasibility_gates.budget=pass`、契约字段全部非空。真实数值取决于实际输入。

---

## 16. 提交前完整性自检清单

- [ ] 已执行单命令 `run` 主入口并生成基线产物。
- [ ] `result.json` 存在且可解析；包含 `case_id`；原始 `output_contract` 字段顶层与 nested 各回显一次。
- [ ] `status` 合法；`errors`、`degradations`、`uncertainty`、`pending_human` 为数组/对象，无空值掩盖缺口。
- [ ] `comparison_matrix.csv`、`decision_record.md`、`evidence_table.json`、`deliverable.md`、`evidence_driven_draft.md` 存在。
- [ ] 若生成 Office/图件，PDF/PNG 预览存在且路径写入 `artifacts`。
- [ ] 每条关键证据有 locator + quote；未命中标 warning 或降 `limit`。
- [ ] 非选中方案都有舍弃理由；全部不可行时给超限量与回退算术。
- [ ] 成本/周期算术可重算；硬门使用契约值；参数窗口冲突被识别。
- [ ] 选择理由、舍弃理由、假设、确认项由 Agent 亲自撰写，非脚本模板原样。
- [ ] 已运行 verify；全 PASS 或已知条目在 degradations 说明。
- [ ] 材料解析失败、缺失文件显式标注，无编造。
- [ ] 退出码 0；所有要求文件在 `/app/output`。
- [ ] 如题面要求 `GITHUB_URL.txt` 已在提交目录根路径。

---

## 17. rubric 维度 → 交付要求 → 自证方式

| rubric 维度 | 交付要求 | 自证方式 |
|---|---:|---|
| 实际效果 40：完成度 15 | 多候选进入同一可比矩阵，完成比较并选择 | `comparison_matrix` 列数等于候选数；`choice.selected` 明确；`eliminations` 完整 |
| 实际效果 40：正确性 15 | 数字、来源、选择站得住 | `cost_model` 可重算；`feasibility_gates` 用契约值；`evidence` 逐字命中；agent_review 显示 verified/conflicts |
| 实际效果 40：完整性 5 | 七类字段和关键比较维度覆盖 | `candidate_plans[*].fields` 七字段 present/absent；矩阵覆盖七类 field |
| 实际效果 40：可核验 5 | 方案版本、字段取值、结论可独立复核 | evidence locator+quote；self_check 可重跑；result.json 双回显 |
| 使用增益 25：质量 15 | 相比基础 Agent 提高比较质量 | `comparison_basis` 固定字段/权重；敏感性一致率；`decision_record.md` 可比矩阵与淘汰逻辑 |
| 使用增益 25：效率 5 | 减少对齐字段、查价、机时/人工核算 | `cost_model` 自动汇总；CSV 直接复核；`artifacts` 列出自动生成 |
| 使用增益 25：可验证 5 | 公平对照证明增益 | verify 确定性复跑；`changes` 记录 Agent 增量；`AUTO_EXTRACT` 诚实标注 |
| 创新增益 15：新增能力 5 | 形成基础 Agent 不具备的稳定比较能力 | 脚本化抽取、硬门、敏感性；schema 说明方法 |
| 创新增益 15：方法改进 5 | 字段设计、评分矩阵、淘汰规则、证据挂载改进 | 21 行矩阵；四类硬门；逐字 evidence；敏感性重排 |
| 创新增益 15：创新证据 5 | 证明创新点边界与价值 | 文档说明“不是各自描述而是可比矩阵”；复跑一致性记录 |
| 可靠体验 10：易用性 3 | 正确触发、按说明完成一次比较 | 单命令；--help；最小调用示例；frontmatter description |
| 可靠体验 10：稳定性 4 | 不同方案数、资源约束、重复运行稳定 | 退出码恒 0；finally 落盘；确定性 verify；异常表 |
| 可靠体验 10：异常处理 3 | 识别设备不可得、超预算、窗口冲突、全不可行 | 硬门 pass/fail/unknown；全不可行 choice=null + 回退算术 |
| 生态贡献 10：文档完整 3 | 流程、口径、依赖、示例、边界齐全 | SKILL.md；references 三份 |
| 生态贡献 10：可复用 4 | 题集、模板、评分矩阵、参数表可复用 | `fields.py`；`comparison_schema.md`；可配置评分 |
| 生态贡献 10：分享 3 | 沉淀方法、典型案例、真实选型经验 | `decision_record.md`；适用边界与失败处理；GitHub 链接 |

---

## 18. 文件清单与维护

| 文件 | 作用 |
|---|---|
| `scripts/main.py` | 入口，run/init/build/selfcheck 编排；契约回填；落盘 |
| `scripts/planmodel.py` | 语义抽取、成本/周期/风险/参数计算 |
| `scripts/scoring.py` | 硬门、分量归一、排序、敏感性 |
| `scripts/fields.py` | 矩阵、证据、敏感性、契约映射 |
| `scripts/report.py` | 决策记录 MD、矩阵 CSV、deliverable/evidence_driven_draft |
| `scripts/verify.py` | 确定性自检 |
| `references/comparison_schema.md` | 字段口径、矩阵、评分、淘汰规则 |
| `references/evidence_locators.md` | 证据定位与逐字 quote 规范 |
| `references/checklist_examples.md` | 自检清单与示例 |

标准库 Python ≥3.8；离线运行；路径基于 `Path(__file__).resolve().parent`，与 CWD 无关。

---

## 19. 维护规则

改口径同步改：`scoring.py`（权重/门限）、`references/comparison_schema.md`、`report.py`（表述）。新增字段优先扩 `planmodel.REQ` 与 `fields.build_matrix`。改完跑 `python3 -B scripts/verify.py --output /app/output --input /input` 确认全绿。任何脚本改动都不能破坏 `result.json` 契约双回显与退出码恒 0。