---
name: experiment-plan-builder
description: 从研究目标、真实科学材料、资源/价格/预订契约、有限参数域和版本化候选方案生成、比较、修订并核验可排期、可计价、可复核的湿实验方案；先单命令产出完整基线，再以 Agent 精读和 draft.json 增量增强；所有产物与 result.json 契约双回显；无 draft 时确定性兜底并诚实记为 AUTO_EXTRACT。
version: 3.0.0
license: MIT
---

# 实验方案生成与优化 Skill（Harness Agent 执行手册）

本文件是给 Harness Agent 的操作手册。你不是只调用脚本，也不是把题目复述成通用实验目录。你必须基于 `/input` 中真实材料、资源契约、价格/预订约束、有限参数域和版本化候选方案，产出一份可排期、可计价、可复核、可执行或明确说明缺口的实验方案。所有内容必须能回到输入中的原文或显式规则；无法确认的只能标 `missing`、`uncertainty` 或 `pending_human`，不得编造。

---

## 0. 最高优先级铁律

1. **先落盘，后增强**：第一步运行单命令全流程，先产出全套基线，再增量改进。
2. **真实解析材料**：不允许只凭文件名、领域标签或题面摘要猜内容；必须实际读取文件。
3. **无依据不写**：不编造仪器型号、量程、试剂目录号、文献、DOI、价格、库存、预算、统计量、批准意见。
4. **所有关键设计与数字必须可核验**：使用 `[S#]` 来源编号和 `文件#页码/行号/段落号` locator。
5. **任何情况 exit 0**：即使输入损坏、约束冲突或材料缺失，也要输出 partial result，并在 `errors` / `degradations` 中诚实记录。
6. **保留基线**：不要删除脚本产出的基线文件；Agent 改进要有 before/after 记录，用作增益证据。

---

## 1. 运行入口：单命令全流程

### 1.1 第一步总是先运行

    python3 -B scripts/build_plan.py run --input /input --output /app/output --work /app/work

该命令应完成：

- `init`：盘点 `/input` 材料，生成来源编号、候选方案抽取、约束与冲突分组；
- `build`：校验输入、必要时做确定性兜底抽取、渲染所有产物、写 `result.json`；
- `selfcheck`：检查产物文件与 `result.json` 契约是否一一对应。

### 1.2 如果 `scripts/build_plan.py` 不存在或 `run` 不可用

立即改为：

    python3 -B scripts/build_plan.py --input /input --output /app/output --work /app/work

如果该命令不识别 `--work`，去掉 `--work` 重试一次：

    python3 -B scripts/build_plan.py --input /input --output /app/output

### 1.3 如果脚本仍然失败

不得停住。手动创建最小合法 `/app/output/result.json`：

    {
      "case_id": "${case_id 或 unknown}",
      "status": "partial",
      "errors": ["scripts_failed: ..."],
      "degradations": ["minimal_manual_result"],
      "sources": [],
      "uncertainty": [],
      "pending_human": [],
      "output_contract": {}
    }

然后在剩余预算内继续读取材料并增强 `protocol.md`、`risk_table.csv` 和 `result.json`。退出码保持 0。

---

## 2. 输入、工作区与输出

### 2.1 输入

- `/input/case.json`：研究目标、约束、设备/试剂/价格/预订契约、参数域、预算、时间窗、候选方案、`output_contract`。
- `/input/task.md`：任务说明、Runtime contract、评分要求。
- `/input` 下的真实材料：PDF、DOCX、CSV、图片等。必须实际解析，PDF 不得假设已有预抽取答案层。

### 2.2 工作区

- `/app/work`：台账、来源清单、冲突分组、`draft.json`、基线快照、脚本运行日志。
- 建议保留 `/app/work/00_baseline`，用于证明 Agent 相对基线的增益。

### 2.3 输出区

最终交付物位于 `/app/output`，至少包含：

- `/app/output/result.json`：机器可读结果与契约双回显；
- `/app/output/protocol.md`：完整可执行方案正文；
- `/app/output/risk_table.csv`：风险与异常处置逐项表；
- 其他脚本生成的证据表、候选方案比较表等不得删除。

---

## 3. 双路径工作流：Agent 路径与确定性兜底

### 3.1 初始化和台账

第一步运行脚本后，先查看 `/app/work` 下是否有：

- `ledger.json`：来源清单、材料编号、候选方案清单、冲突分组；
- `source_index.json`：每个材料的 `source_id`、文件名、哈希前 16 位、解析状态；
- `00_baseline/`：脚本产出基线。

如果没有台账，但输入可读，则自己建立一份简洁台账，写清：

- 每个输入文件的 `source_id`；
- 材料类型与解析工具；
- 与本题相关的关键事实、原文摘录、定位；
- 候选方案编号和主要差异。

### 3.2 Agent 路径：先读原文，再写 draft.json

如果预算允许，走 Agent 路径：

1. 读 `task.md`，提取 Runtime contract、输出要求、六类要素要求；
2. 读 `case.json`，提取 `case_id`、研究目标、资源契约、价格/预订约束、参数域、候选方案、`output_contract`；
3. 实际解析每个材料，提取与假设、变量、对照、设备材料、时间成本、参数范围、风险异常相关的事实；
4. 将你的判断写入 `/app/work/draft.json`，至少包含：

       {
         "case_id": "来自输入",
         "research_question": "可检验问题",
         "hypotheses": [],
         "variables": [],
         "groups": [],
         "equipment_materials": [],
         "steps": [],
         "parameters": [],
         "schedule_costs": [],
         "risks": [],
         "readouts": [],
         "evidence": [],
         "uncertainty": [],
         "pending_human": [],
         "changes": []
       }

5. 写完后运行校验与构建：

       python3 -B scripts/build_plan.py check --work /app/work --input /input --output /app/output

   或回退：

       python3 -B scripts/build_plan.py --input /input --output /app/output --work /app/work

6. 根据 check 输出补齐文件与字段，再进入自检。

### 3.3 无 draft 时的确定性兜底

如果 Agent 没有写 `/app/work/draft.json`，`build` 必须依据 init 台账做确定性抽取，生成实质工作稿，而不是空模板：

- 逐字引用 `quote`；
- 给出 `locator`；
- 从输入中可确定地抽取设备型号、试剂规格、价格、时间窗、参数域、候选方案步骤；
- 对每个候选方案做算术校验；
- 在 `result.json` 的 `gaps` 或 `degradations` 中显式记入 `AUTO_EXTRACT`，例如：

      "degradations": [
        {
          "code": "AUTO_EXTRACT",
          "meaning": "未使用 Agent draft.json，方案由确定性脚本从台账抽取生成",
          "action": "建议人工/Agent 复核原文后再执行"
        }
      ]

`AUTO_EXTRACT` 不是失败，而是诚实的降级标记。

---

## 4. 必须解析与记录的事实

对每个输入材料，至少记录：

- 文件名；
- sha256 前 16 位；
- 解析工具；
- 关键原文摘录 `quote`；
- 定位 `locator`；
- 与六类要素的对应关系。

重点事实包括：

- 设备型号、量程、精度；
- 试剂名称、规格、目录号、单价、库存；
- 预订窗口、可用机时、可预约数量；
- 参数允许值域和单位；
- 预算上限、时间窗、样本量约束；
- 候选方案的步骤、耗时、资源占用、风险点；
- 材料中已有的风险或异常处理信息。

---

## 5. 实验方案六类要素：必须产出且可核验

无论最终结构如何，`protocol.md` 和 `result.json` 必须覆盖以下六类要素，且每项尽量带证据。

### 5.1 假设与变量

- 把研究目标转成可检验问题；
- 写出原假设、备择假设或零假设；
- 明确自变量、因变量、混杂变量；
- 每个变量有操作定义、测量方式、单位、取值范围；
- 给出可反证条件或判读标准。

### 5.2 对照组

至少考虑：

- 空白对照；
- 阴性对照；
- 阳性对照；
- 剂量梯度或条件梯度对照。

每个对照写明排除哪一类混杂，不能只有“空白组”或“未处理组”。

### 5.3 设备材料

- 步骤绑定具体设备型号、量程、耗材规格、试剂信息；
- 标注可替代项和不可替代项；
- 价格与库存须与输入契约一致；
- 若输入只有部分信息，缺失项写 `missing`，不得用模糊常见型号补齐。

### 5.4 时间成本

- 步骤时长；
- 并行关系；
- 样本量与分组数；
- 试剂/耗材成本小计；
- 机时费；
- 总预算；
- 墙钟时间；
- 排期表。

### 5.5 参数范围

- 关键参数、单位、允许区间；
- 超出区间的处置；
- 参数依据来自设备手册、预实验还是文献/材料；
- 若输入允许裁剪，裁剪到最近允许值并记录 `changes`；若没有规则，标 `pending_human`。

### 5.6 风险与异常

每个风险至少包含：

- 失败模式；
- 早期信号；
- 缓解措施；
- 止损点；
- 替代路径；
- 负责人/角色；
- 来源。

常见风险包括：污染、无信号、重复性差、样本不足、试剂缺货、设备排期已满、参数超量程、时间窗冲突。

---

## 6. result.json 契约与双回显

### 6.1 顶层字段

`result.json` 顶层应包含：

- `case_id`
- `status`
- `schema_version`
- `runtime`
- `version`
- `changes`
- `sources`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `self_check`
- `coverage`
- 以及原 `output_contract` 中的全部字段。

### 6.2 嵌套 output_contract 双回显

原 `output_contract` 的全部字段，包括 `case_id`，必须在两个地方各出现一次：

1. `result.json` 顶层；
2. `result.json` 的 `output_contract` 对象中。

两层值必须一致。若原合同有嵌套结构，保留原键名，不得改名，不得只写摘要。

### 6.3 status 取值

- `ok`：六类要素齐备，无阻塞问题，主要事实可回源；
- `partial`：有缺口、冲突未解决、部分材料缺失或存在降级；
- `input_error`：输入不可用或无有效任务。

只要不是完全无阻塞，优先使用 `partial`，不要勉强标 `ok`。

### 6.4 输出字段与磁盘文件对应

对于 `output_contract` 中要求的每个字段，必须有对应磁盘文件或结果字段。例如：

- 实验方案正文：`protocol.md`；
- 风险表：`risk_table.csv`；
- 证据表：`evidence_table.json` 或 `evidence` 字段；
- 候选方案比较：`candidate_comparison.md` 或 `result.json` 中 `comparison` 字段。

结束前逐项核对“契约字段 × 磁盘文件 × result.json 键”三者一致。

---

## 7. 必须执行的算术与约束校验

对每个候选方案和最终方案，都要做真实算术校验：

- 材料成本 = Σ(单价 × 数量)
- 合计样本数 = 组数 × 每组重复数
- 机时成本 = 机时费 × 使用时长
- 机时需求 ≤ 可用机时
- 预订日期 ≤ 时间窗
- 参数值 ∈ 输入允许域
- 总成本 ≤ 预算上限

若出现时间窗与样本量冲突、试剂缺货、设备排期已满、参数超量程：

- 在 `feasibility` 中给出硬约束数值；
- 将不可行项标为 `not_feasible`；
- 不通过编造或硬压缩重复数“解决”冲突；
- 写 `pending_human`，说明需要人确认的替换或放宽项。

对三个版本候选方案，若输入中提供：

- 横向比较总成本、墙钟时间、样本量、预订可行性、风险可接受性；
- 选择或推荐时写明依据和证据；
- 不自行杜撰输入没有的候选方案。

---

## 8. 产出文件规范

### 8.1 protocol.md

- 面向实验人员，可据此排期、报价、评审；
- 包含标题、研究目标、假设、变量、对照、设备材料、步骤、参数、排期表、预算、判读标准、风险简述；
- 每个关键数字/规则带 `[S#]` 和 locator；
- 不得含未替换的 `{{...}}` 占位符；
- 不得复制脚本模板而不填入真实内容。

### 8.2 risk_table.csv

列名建议为：

    risk_id, code, failure_mode, likelihood, impact, early_signal, mitigation, stop_condition, fallback, owner, source_ref

每行对应一个明确风险；不得只写“注意安全”。

### 8.3 evidence_table.json 或 evidence 字段

每条证据包含：

    evidence_id, claim_id, source_ref, locator, quote, verified, basis_type, support_scope

`basis_type` 可取值：

- `source`：来自材料原文；
- `input`：来自 `case.json` 或 `task.md`；
- `rule`：来自输入明确规则；
- `principle`：一般科研原则；
- `missing`：缺失；
- `pending_human`：需专家确认。

---

## 9. 不确定性与 pending_human 的使用

- `uncertainty`：当前材料不完整、有冲突或只能给出范围，但不阻塞交付。写清问题、影响范围、可能解决路径。
- `pending_human`：只有真正需要人确认才能继续执行的事项才写入，例如缺少关键设备量程、试剂缺货且不可替代、安全/伦理边界需要批准。
- 不得把未经确认的建议写成“可执行事实”，不得写“经专家确认”“已通过安全审批”等未发生声明。

---

## 10. 预算策略：64 次模型请求 / 900 秒 / 16384 tokens

### 10.1 请求优先级

1. 先跑单命令，拿到完整基线；
2. 补齐六类要素和 `protocol.md`；
3. 补证据表和 `risk_table.csv`；
4. 做算术校验与契约自检；
5. 增益记录与美化最后做。

### 10.2 建议分配

- 初始化与脚本运行：1-3 次；
- 读取 task/case 契约：2-4 次；
- 解析材料：每个材料 1-2 次，通常 3 个材料 5-8 次；
- 写 draft 或增强方案：8-14 次；
- 证据核对：5-8 次；
- 自检与 finalize：3-6 次。

总计约 25-45 次，留足余量。

### 10.3 预算保护规则

- 每完成一个大步骤，立即写回 `/app/output`，不要等全部完成；
- 超过 50 次请求或剩余时间不足 300 秒，停止所有非必要增强，只做 finalize；
- 不要重复读取同一大文件；
- 如果无法完成精细增强，保留诚实 partial，不要提交空文件或非法 JSON。

---

## 11. 隐藏案例鲁棒性

| 情况 | 正确处置 |
|---|---|
| 空输入 / 无 `case.json` | 继续读 `task.md` 和其他材料；无有效输入则 `status=input_error`，退出 0 |
| 材料缺失 | 只依据 `case.json` / `task.md` 明确字段；缺失参数写 `missing` 或 `pending_human` |
| 材料损坏 / 无法打开 | 记录 `sources` 和 `parse_failed`，相关事实写缺口，不猜内容 |
| 格式不支持 | 尝试 `environment/resources.yaml` 中可用工具；失败则记录工具缺失，不强行解析 |
| 约束冲突 | 在 `feasibility` 给硬约束数值，标 `not_feasible`，写 `pending_human` |
| 参数超量程 | 输入有规则则裁剪并记 `changes`；无规则则标 `pending_human` |
| `output_contract` 缺失 | 使用本文件第 12 节默认字段清单，并写 `self_check.contract_missing=true` |
| 预算/时间快耗尽 | 立即写 partial result，保证 `result.json` 合法且退出 0 |
| 中英文输入 | 结果语言自适应；关键字段可中英并列，但不得改变契约键名 |

---

## 12. 若 output_contract 缺失的默认字段

如果 `/input/case.json` 中没有 `output_contract`，使用以下通用字段，并在 `self_check` 中标明：

    hypotheses
    variables
    groups
    equipment_materials
    steps
    parameters
    readouts
    schedule_costs
    risks
    feasibility
    evidence
    confirmation_items
    sources
    uncertainty
    pending_human
    changes

这些字段也应同时出现在 `result.json` 顶层和 `output_contract` 对象中。

---

## 13. rubric 自检清单

提交前逐项确认：

- [ ] `/app/output/result.json` 存在且为合法 JSON；顶层与 `output_contract` 均含 `case_id` 和契约字段；
- [ ] `/app/output/protocol.md` 存在、非空、无未替换占位符、可直接排期；
- [ ] `/app/output/risk_table.csv` 存在且列名正确；
- [ ] 六类要素全部覆盖；若有覆盖缺口，`coverage` 中对应项为 false，且 `status=partial`；
- [ ] 每个关键设计、价格、参数、预算有证据和 locator；
- [ ] `sources` 包含所有输入材料与前 16 位 sha256；
- [ ] 算术自检通过：材料小计、样本量、机时成本、预算上限、时间窗；
- [ ] 候选方案比较和最终选择有依据；
- [ ] `changes` 完整记录 before/after/rule/evidence；
- [ ] `uncertainty`、`pending_human`、`errors`、`degradations` 如实填写；
- [ ] 没有编造设备、试剂、文献、DOI、价格、统计量、批准意见；
- [ ] 基线与 Agent 增强内容都保留，增益可查；
- [ ] 任何情况下退出码为 0。

---

## 14. 禁止事项

- 禁止跳过原始材料阅读，只凭文件名或标签写作；
- 禁止生成“经专家确认”“实际安全批准”等未发生声明；
- 禁止自造 `golden_standard`、自设评分或加权自评分；
- 禁止手工篡改结构化 JSON 结构；若脚本有缺陷，写临时脚本重算，不手工覆盖核心键；
- 禁止删除脚本生成的基线产物；
- 禁止空模版或仅复述目标；
- 禁止写出 NaN、Infinity 等非法 JSON；
- 禁止伪造 GitHub 链接、benchmark 分数或测评结果。

---

## 15. 生态资源使用

包内可用资源：

- `references/protocol_template.md`：用于组织实验方案结构，不是成品；
- `references/checklists.md`：六类要素、rubric 自检、评审检查表；
- `references/catalog.json`：可复用清单或锚点示例。

使用这些资源时，只作为结构和检查工具，不得替代对 `/input` 材料的真实解析。

---

## 16. 最终收尾

最后执行：

1. 重读 `result.json` 确认合法 JSON；
2. 确认 `case_id`、顶层契约、嵌套 output_contract 三方一致；
3. 确认 `/app/output` 中所有必需文件存在；
4. 确认 `status` 与实际完成度一致；
5. 输出最终结果，退出码 0。

如果时间或请求不足，保留 partial，不空转。