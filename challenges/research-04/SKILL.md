---
name: research-trend-lens
description: >-
  将给定文献材料转化为四类可复核的研究前沿产物：年度趋势与变点、主题演化、各阶段代表作、有排除证据的研究空白。所有结论必须回链到材料来源与原文定位，区分事实、合理推断与无法确定项。适用于研究前沿与趋势分析、时间趋势统计、主题演化追踪、代表作筛选、研究空白识别、证据矩阵构建。
version: 2.2.0
---

# research-trend-lens（研究前沿与趋势分析）

## 0. 最高优先级：先完整交付，再增量改进

本 Skill 的目标不是生成“前沿清单”，而是交付可复核的四类研究产物：

1. **时间趋势**：由可核对的年度分布支撑，区分离散波动与真实拐点。
2. **主题演化**：说明主题何时出现、合并、分裂、衰退，避免把关键词热度当趋势。
3. **代表性工作**：覆盖各阶段，说明入选口径，避免只用被引排序。
4. **研究空白**：必须有排除证据或方法失效/冲突证据，不能把“未检索到”当成空白。

Agent 的职责是读取真实材料、核验证据、补全成稿，而不是重写结构化 JSON 结构。脚本生成的 `result.json`、`claims.json`、`evidence_table.json` 结构字段必须保留；如需修正，写 `draft.json` 后重新 build，或写入 `changes[]` 与 `reviewed_by_agent`。

---

## 1. 用途与边界

**用途**：围绕给定研究问题，在 `/input` 提供的实际材料内完成证据抽取、筛选、趋势统计、主题演化、代表作选取、空白识别和证据回链。

**适用**：case 提供了研究问题、材料（PDF/RIS/CSV/JSON/JSONL/TXT/MD）、纳排规则、契约字段，并要求趋势/演化/代表作/空白判断。

**不适用**：外部数据库检索、单篇精读、效应量元分析、需要外部引用数或网络访问、材料完全缺失且无法形成任何证据基础。

**铁律**：

- 只能依据实际解析到的材料内容。
- 不依据文件名或领域标签猜测内容。
- 不编造年份、统计数、引文、方法、空白、基准分。
- 材料不足、年份缺失、主题歧义、证据冲突必须显式登记。
- 不提交预制答案或正式测试输出。

---

## 2. 目录与运行契约

- Skill 包根：`/skills/weekly-skill`
- 输入目录：`/input`
- 工作目录：`/app/work`
- 最终产物目录：`/app/output`
- 运行中所有临时文件写入 `/app/work`，所有最终交付物写入 `/app/output`
- 脚本仅使用 Python 标准库，离线运行，不访问网络，不依赖第三方包
- `pdftotext` 或环境提供的 `pdf-text-tool` 存在时优先用于 PDF 实文本提取
- **退出码始终为 0**：即使输入错误、解析失败、时间不足，也必须落盘合法 `result.json`
- 运行资源：64 次模型请求 / 900 秒 / 单次响应 16384 tokens
- Skill 资源：最多 50 个 UTF-8 文本文件，单文件 ≤500KB，总 ≤2MB，无 symlink

---

## 3. 单命令全流程入口

唯一必需入口：

```text
cd /app/work && python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部按顺序执行：

1. `init`：扫描 `/input`，读取 `case.json` 与 `task.md`，为材料分配 `source_id`（`S#`），完成候选语句抽取、年份归一、去重、冲突分组，写入 `/app/work/init_ledger.json`；如无 Agent draft，则生成 draft 模板。
2. `check`：如果 `/app/work/draft.json` 存在且非空，校验其结构、来源编号、locator、引用串；否则走确定性兜底。
3. `build`：基于台账与 draft 决策，确定性完成年度统计、主题演化、代表作选取、空白识别、证据矩阵、CSV、报告、图表预览、最终 `result.json`。
4. `selfcheck`：校验产物文件齐备、`result.json` 契约字段双层回显、数字可复算、引用可定位、错误项齿合。

Agent 不得把 `scripts/main.py` 的原始输出、空模板或骨架内容直接当正式成稿提交。脚本基线完成后，Agent 必须至少在证据核验和成稿润色上做真实增强。

---

## 4. Agent-first 双路径

### 4.1 确定性兜底路径

如果 `/app/work/draft.json` 不存在，`run` 必须使用 `init_ledger.json` 中的台账确定性抽取：

- 每个关键结论必须带逐字 `quote` 与 `locator`。
- 自动抽取结果应标记 `AUTO_EXTRACT=true`。
- 自动抽取无法判定的年份、主题归属、代表性口径、空白判定，必须记入 `gaps/degradations`，不得伪装为 Agent 已核验结论。
- 这是“无 draft 时仍产出实质工作稿”的保证，不是空转。

### 4.2 Agent 主动路径

Agent 可以按以下方式增强：

1. 先运行一次 `run`，获得完整基线产物与 `/app/work/init_ledger.json`。
2. 阅读 `/input` 中的真实材料，逐条核验关键 quote/locator/数字。
3. 将新的判断写入 `/app/work/draft.json`。
4. 再次运行同一 `run` 命令，脚本会消费 draft 重建产物。
5. 把核验过程写入 `/app/output/agent_review.json`，并在 `result.json` 的 `reviewed_by_agent`、`changes[]` 中留痕。

`draft.json` 建议形状：

```text
{
  "case_id": "...",
  "research_question": "...",
  "inclusion_criteria": [],
  "exclusion_criteria": [],
  "decisions": [
    {
      "decision_type": "trend_interval|topic_phase|representative_selection|gap_claim|conflict_resolution",
      "claim_id": "...",
      "source_id": "S#",
      "locator": "file.pdf#page=3",
      "quote": "...",
      "strength": "fact|inference|uncertain",
      "note": "..."
    }
  ],
  "rejected_materials": [
    {"file": "...", "reason": "unsupported_format|unreadable_pdf|out_of_scope"}
  ]
}
```

完整说明见 `references/method.md`。若 draft 写法不确定，保留脚本基线，不要手改 `result.json`。

---

## 5. 交付物清单

以下为默认交付物。若 `/input/case.json` 的 `output_contract` 指定了不同文件名，必须同时满足契约文件名与下列默认文件名，避免漏判。

| 文件 | 必含内容 |
| --- | --- |
| `/app/output/result.json` | 契约字段双层回显、状态、来源、不确定性、待人工核验项、错误、降级、变更记录 |
| `/app/output/research_report.md` | 研究问题、检索/纳排、四类产物、冲突证据、不确定性、边界 |
| `/app/output/evidence_map.csv` | `claim_id, source_id, locator, quote, strength, support_scope, verified` |
| `/app/output/trend_annual.csv` | `year, n_records, theme_count, share, growth_rate, fluctuation, change_point` |
| `/app/output/topic_evolution.csv` | `time_window, theme, status, evidence, source_ids` |
| `/app/output/representative_works.csv` | `phase, work, selection_rationale, citation, coverage` |
| `/app/output/research_gaps.csv` | `gap_id, gap_type, exclusion_evidence, status, confidence` |
| `/app/output/screening_log.csv` | `source_id, file, included/excluded, reason` |
| `/app/output/run_ledger.json` | 运行时间、脚本版本、文件解析质量、changes、失败恢复记录 |
| `/app/output/agent_review.json` | Agent 核验样本、判断、修正说明（若有） |

Agent 若额外生成图表、PPTX、可编辑 Office 文件，必须同时生成真实渲染的 PDF/PNG 预览，放入 `/app/output`。

---

## 6. result.json 双层回显契约

`/app/output/result.json` 必须合法、UTF-8、可被 JSON 加载。

顶层必须至少包含：

```text
case_id
status
output_contract
sources
claims
evidence
uncertainty
pending_human
conflicts
errors
degradations
changes
verification
reviewed_by_agent
```

`output_contract` 必须是嵌套对象，并再次包含原始 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`。

`status` 只能是：

- `ok`
- `partial`
- `insufficient_evidence`
- `input_error`
- `failed`

`status=partial` 时，`errors[]` 或 `degradations[]` 必须列出具体缺失项与原因。

`changes[]` 每项至少包含 `time`、`scope`、`reason`、`before`、`after`。

`verification` 必须记录可复核数字，例如：

```text
dated_records
records_included
records_excluded
quote_checked
quote_verified
contract_fields_filled
```

不得编造 `golden_standard`、官方分数、基准对比分数。平台会记录真实运行。

---

## 7. 证据、来源编号与 locator

- 每个材料解析后分配稳定 `source_id`，格式 `S1`、`S2`，在单次运行内唯一。
- 每条 `claim` 必须有 `source_id`、`locator`、`quote`、`strength`。
- locator 示例：

```text
file.pdf#page=3
file.ris#rec2
file.csv#row=7
file.txt#para=4
```

- 所有关键数字、趋势判断、主题归属、代表作入选理由、空白主张必须带 `[S#]` 和 locator。
- `quote` 必须来自解析后的真实文本；核验时先做 NFKC 归一、去多余空格、大小写敏感子串匹配。
- 若引用无法核验，将对应 claim 标为 `quote_verified=false` 并降级为 `insufficient` 或 `pending_human`，不得删除证据矩阵。

---

## 8. 四类产物方法要求

### 8.1 时间趋势

- 使用年度或题面指定时间窗统计记录数、主题占比、增长速率。
- 必须说明数据口径：在线发表、见刊、预印本、年份缺失。
- 区分离散波动与真实拐点；数据点不足 2 个时不得声称趋势。
- 缺失年份记录列入 `year_missing`，不补造。

### 8.2 主题演化

- 识别主题词出现、合并、分裂、衰退。
- 明确时间窗阶段划分依据。
- 术语漂移、同名异义必须显式说明。
- 不得仅凭关键词出现次数判定“新兴主题”。

### 8.3 代表性工作

- 覆盖全部阶段，不只选总被引最高文献。
- 说明入选口径：方法首创、问题定义、证据贡献、长尾覆盖等。
- 每个推荐必须引用原文定位，说明它为何代表该阶段。

### 8.4 研究空白

- 来源只能是：被反复提出但未解决的问题、方法在特定对象/尺度失效、证据冲突未决。
- 每条空白必须有排除证据或明确限制条件。
- “未检索到”不能单独构成空白；只能作为待核验项。
- 没有合格排除证据时，写入 `pending_human`，不要上升为空白结论。

---

## 9. 冲突证据与不确定性

- 两条以上来源对同一问题不一致时，建立冲突分组，不压制、不合并。
- 在 `evidence_map.csv` 和报告中给出各方来源、原文、定位、冲突性质。
- 冲突无法基于材料解决时，状态写 `unresolved`，将决策提交 `pending_human`。

不确定性至少覆盖：

```text
material_unparsed
year_missing
theme_ambiguity
conflicting_evidence
inference_boundary
missing_metadata
```

---

## 10. 异常处理

| 情况 | 动作 |
| --- | --- |
| 无 `/input/case.json` | 写 `status=input_error`，继续输出合法 report 与 result.json |
| 材料全部不可解析 | `status=insufficient_evidence`，产出空统计表和空证据矩阵，不编造结论 |
| 某些 PDF 为扫描版/低质量 | 只将标题作为引用，正文不用于证据；写入 `degradations` |
| 不支持的 `.docx/.xlsx/图片/压缩包` | 不解析、不猜测，列入 `screening.excluded` 与 `material_unparsed` |
| 年份缺失 | 不补年份，对应记录不进入年度趋势统计 |
| 主题严重歧义 | 建立 `theme_ambiguity` 条目，不用默认主题归并 |
| 文献量过大 | 保留全部来源编号，优先生成基础 CSV 与最小证据矩阵，报告降级为 `partial` |
| 时间或请求预算接近上限 | 立刻保留已落盘 partial 产物，写合法 result.json，退出码 0 |
| 脚本崩溃 | 读取已有 `/app/output/result.json` 或依据 `references/method.md` 写最小合法 result.json，退出码 0 |

---

## 11. 自检清单（提交前必须逐项核对）

1. `result.json` 可被 `json.load` 成功加载。
2. `output_contract` 原始字段在顶层与 `result.json["output_contract"]` 中各出现一次。
3. `case_id` 在顶层与嵌套契约中存在且来自实际输入。
4. 所有必需交付文件存在且非空。
5. 每条 `claim` 都有 `source_id`、`locator`、`quote`。
6. `quote_verified` 与 `verification` 数字互相一致。
7. `trend_annual.csv` 行数等于 `verification.dated_records`。
8. `evidence_map.csv` 记录数等于纳入材料可覆盖证据。
9. `research_gaps.csv` 中每条空白都有排除证据或明确待核验标记。
10. `research_report.md` 四类产物均独立成章，不是检索清单。
11. 报告语言与输入一致：中文输入输出中文，英文输入输出英文。
12. 没有 `golden_standard`、假基准分、预制答案。
13. 所有变更写入 `changes[]`，Agent 核验写入 `reviewed_by_agent`。
14. 若 `status=partial`，`errors[]` 或 `degradations[]` 明确列出缺项。

---

## 12. 预算策略

- 先运行 1 次 `run` 获得全套基线；这部分不消耗模型请求。
- 将模型请求集中用于：阅读材料原文、核验 3-8 条关键引用、补写空白排除证据、润色成稿。
- 需要 Agent 主动路径时，至多再运行 1 次 `run` 消费 draft。
- 接近 64 次请求或 900 秒时立即收尾，确保 `result.json` 合法且 `status` 诚实。
- 不要在脚本已经稳定生成全部产物后反复全量重跑。

---

## 13. 资源与参考

- `references/method.md`：方法、时间窗规则、主题归并、代表作选取口径、draft/check/build 细节。
- `references/lexicon.md`：主题词表、术语漂移、同义归并。
- `references/report_template.md`：报告骨架，仅作结构参考，不得当正式成稿提交。
- `environment/resources.yaml`：预装依赖与可用工具声明。
- 实际隐藏案例以 `/input/task.md` 与 `/input/case.json` 为准；若本 SKILL 与 Runtime contract 冲突，以 Runtime contract 和实际输入为准。

**一句话总则**：先让脚本把可核验的完整结果落盘，再用 Agent 的真实阅读和判断增强它；永远不因过度修饰而丢失契约字段、证据回链或诚实状态。