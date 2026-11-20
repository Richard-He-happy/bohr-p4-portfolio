---
name: literature-data-cleaner
description: >-
  Clean and standardize a batch of literature extraction records into a
  statistically usable table, with a rule-numbered change log, a pending-human
  review list and a source-traceable duplicate/conflict report. The Skill
  instructs the Harness Agent to genuinely read the original materials, run the
  included baseline scripts as tools, verify and enhance their outputs, then
  write final deliverables. Use when the input supplies paper-extracted rows
  (values, units, material/indicator names, condition columns) plus
  unit/number/region rules or a target field dictionary, and asks for unified
  field names, unit conversion with formulas, synonym normalization,
  missing/outlier handling, duplicate handling and source traceability. Trigger
  phrases: "文献数据清洗", "抽取记录标准化", "单位换算并保留原值", "去重并给变更记录".
version: 3.0.0
---

# 文献数据清洗与标准化

## 0. 最高优先级：先跑通、再增强、不造假

本 Skill 采用单命令全流程入口，内部按 init → build → selfcheck 执行。脚本负责确定性产出与契约兜底；Agent 负责阅读原文、写 draft、核验和文本成稿。两端共用同一套产物与同一份 result.json 契约。

必须遵守：

1. 单命令入口为：  
   `python3 scripts/main.py run --input /input --output /app/output --work /app/work`
2. 所有异常从脚本/流程层处理为降级状态，最终都要退出码 0。
3. 结构化数据（claims、evidence_table、result.json、cleaned_data 等）由脚本生成；Agent 可写 `/app/work/draft.json` 和文本型交付物，不得手工改写脚本最终 JSON 结构。
4. 不编造文件、软件状态、缺失值、科学数据或 benchmark 分数。
5. 材料缺失、单位无法识别、科学冲突、文件不可解析必须进入 gaps/degradations 或 pending_human，不伪装成功。
6. 预算敏感：优先脚本完整产出，剩余请求用于增量核验和文本成稿；接近 64 次模型请求 / 900 秒 / 16384 tokens 时立即收尾。

## 1. 用途与边界

本 Skill 把真实文献抽取记录端到端清洗成可统计宽表，并同时交付：

- 字段映射结果与未映射字段清单；
- 单位换算表，含原值、目标单位、公式、精度、规则编号；
- 重复记录检测、同义名称归一、合并建议与待人工确认项；
- 行级变更记录；
- 异常、缺失、越界、冲突与来源覆盖报告；
- 可复核的证据表：每个关键数值/论断带 `[S#]` 来源与 `文件#行号/段落号` locator。

不做的部分：

- 不把缺失写成 0，不把区间压成中值，不丢掉 `±` 误差。
- 不猜单位。`a.u.`、`arb. units`、无法解析 token、缺失单位不换算。
- 对不同来源、不同条件、不同实验上下文不强行合并。
- 科学冲突不以字面单位换算抹平；同源同条件下显著不一致时标 `source_conflict` 并保留原值。

## 2. 输入与输出契约

输入默认位置：

- `/input/case.json`：case_id、output_contract、任务约束与材料清单。
- `/input/task.md`：题面要求、评分关注点、Runtime contract。
- `/input/**`：CSV/JSON 抽取记录、规则文件、字段字典、PDF/DOCX/图片原文。

输出默认位置：

- `/app/output/result.json`：最终结构化结果。
- `/app/output/cleaned_data_table.csv`：可统计宽表。
- `/app/output/evidence_table.csv`：行级证据，含 quote/locator/rule_id/formula。
- `/app/output/change_log.csv`：before → after → reason → rule_id → row_id。
- `/app/output/field_mapping.csv`：原字段、规范字段、映射依据、未映射项。
- `/app/output/unit_conversion.csv`：原值、原单位、目标单位、公式、精度、规则编号。
- `/app/output/deduplication.csv`：合并建议、判定键、重复记录 vs 重复实验、状态。
- `/app/output/pending_human.csv`：必须人工确认的值、原因、位置。
- `/app/output/conflict_report.csv`：来源冲突、同义冲突、条件冲突、处理方式。
- `/app/output/anomaly_report.csv`：缺失、越界、编码错乱、不可解析单位等。
- `/app/output/source_ledger.csv`：来源文件、来源编号、可用性、解析状态。
- `/app/output/method_report.md`：方法说明、规则生效情况、限制与人工接管位置。
- 若 output_contract 另有字段要求，脚本应按字段逐个渲染文件，并在 result.json.files 中登记。

每个契约字段必须在 result.json 顶层与 nested output_contract 中各出现一次。

## 3. 标准执行流程

### 步骤 A：初始化并写最小 partial

优先立即创建 `/app/work/workflow_state.json`，并尽力写出最小合法 `/app/output/result.json`，至少包含 `case_id`、空骨架的 output_contract、`status: partial`、`errors: []`、`degradations: []`。

命令：  
`python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase init`

init 必须完成：

- 盘点 `/input` 全部文件，按角色分类；
- 给每个来源分配 `source_id`；
- 识别记录表、规则文件、字段字典、原文 PDF/DOCX/图片；
- 抽取候选行、冲突分组、缺失与异常候选；
- 写出 `/app/work/inventory.json`、`/app/work/source_ledger.json`、`/app/work/contract.json`、`/app/work/candidates.json`。

### 步骤 B：Agent 阅读与判断

Agent 必须阅读 `/input/task.md`、`/input/case.json` 和材料本体，不能只看文件名或标签。

对 PDF/DOCX/图片，使用平台预装解析工具真实提取内容，保存到 `/app/work/evidence/`。如无法解析，记录到 `/app/work/parse_report.json`，不得凭标题臆造原文。

Agent 依据 init 台账和原文，将判断写入 `/app/work/draft.json`。draft 形状至少包括：

- `mode: "agent"`
- `case_id`
- `rows`：逐行规范化结果，每行含 row_id、source_id、locator、quote、original_value、normalized_value、target_unit、rule_id、formula、precision、confidence、missing_flag、uncertainty
- `duplicates`：每组合并建议，含 group_key、row_ids、decision、reason、status
- `conflicts`：冲突项，含 conflict_id、row_ids、description、decision、pending
- `pending_human`：item_id、type、location、reason
- `limitations`：真实限制

写 draft 前先看 `/app/work/inventory.json`，避免重写结构或漏字段。

### 步骤 C：校验 draft

命令：  
`python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase check`

check 校验 draft 的字段完整性、source_id 可解析、locator 格式、rule_id 存在、数值与原值一致性。校验报告写入 `/app/work/check_report.json`。若 draft 无效，Agent 只补 draft，不手改最终产物。

### 步骤 D：build 与确定性兜底

命令：  
`python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase build`

此时：

- 若 `/app/work/draft.json` 存在且 check 通过，build 使用 agent draft 渲染全部产物。
- 若 draft 不存在或无效，build 使用 init 台账确定性抽取生成实质工作稿：逐字 quote、locator、rule_id、formula、原始值保留；该稿标记 `provenance_mode: automatic`，并把 `deterministic_fallback_used` 写入 degradations。
- 两条路径产出同一套文件与同一份 result.json 契约。

### 步骤 E：selfcheck 与 finalize

命令：  
`python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase selfcheck`

selfcheck 必须校验：

- result.json 顶层与 nested output_contract 的 case_id/契约字段一致；
- output_contract 要求字段都有对应产物文件；
- 每个可追溯结果有 row_id → source_id → locator → quote → rule_id；
- CSV/JSON 列名稳定，空值保留，不写编造值；
- 状态字段与 gaps/degradations 一致；
- 所有错误已写入 errors，但流程仍 exit 0。

最终 result.json 无条件覆盖。状态可取：`success`、`partial`、`insufficient_evidence`、`failed`。

## 4. Agent 路径增量规则

Agent 路径的目标是在确定性基线之上提高完成度和可核验性，不是替换脚本。

Agent 可做：

- 真实阅读原文，核验 quote/locator/数字是否一致；
- 在 `/app/output/agent_review.md` 中写核验结论：claim_id → verified/rejected/reason；
- 补充 pending_human 中真正需要人工判断的项；
- 亲自撰写或改写正文型交付物，但每个数字、引用、论断必须能在 evidence_table 中找到来源；
- 若发现脚本缺陷，用临时 Python 调用脚本函数重算并记录在 agent_review.md 的 script_fixes，不手工篡改 JSON。

Agent 禁止：

- 直接编辑 claims.json、evidence_table.json、result.json 等结构化文件键值；
- 生成无依据的 golden_standard、diff_report、加权自评分；
- 用“看起来合理”的领域标签补造数据。

## 5. 清洗与标准化规则

脚本和 Agent 均按以下规则库执行，规则来自 `references/rules_library.json` 与 `references/unit_table.json`。

字段规范：

- 同一指标统一到同一字段名、同一数据类型、同一允许值集合；
- 同义字段映射要有 mapping_from、mapping_to、mapping_basis；
- 未映射字段必须出现在 field_mapping.csv 的 unmapped 区。

单位与格式转换：

- 保留 original_value；
- 写清 original_unit、target_unit、formula、precision；
- 复合单位、数量级前缀、区间值不能出错；
- 区间转换保留区间两端与误差；不把误差折叠成中值；
- 未知单位进入 pending_human，不强行换算。

重复与同义词归一：

- 判定键必须可解释：material_synonym ∪ indicator_synonym ∪ condition_context ∪ source；
- 区分“重复记录”与“重复实验”；
- 不同来源、不同条件不合并；
- 合并输出 merge_id、merged_from_row_ids、decision、confidence、manual_review_required。

缺失与异常：

- 缺失保持空缺；
- 越界和异常标 anomaly_type；
- 编码错乱标 encoding_error，并在 source_ledger 记录；
- 空表输出空表结构，状态 partial，不假装成功。

冲突：

- 规则冲突按 priority + scope 处理；
- 同源同条件数值显著矛盾标 `source_conflict`，保留原值；
- 规则失效情形写入 rule_id 的 failure_mode 或 pending_human。

## 6. 可追溯性要求

每个被改动的值必须形成可复核链：

`row_id → source_id → file → locator → quote → original_value → normalized_value → rule_id → formula → precision`

可追溯字段写入 evidence_table 和 change_log，不能只给成品表。

来源定位格式优先为：`文件路径#页码#段落号`、`文件路径#表号#行号`、`文件路径#字段名`。

无法确认来源的值不得进入主结果表；进入 pending_human 或 gaps。

## 7. result.json 双回显契约

result.json 顶层至少包含：

- `case_id`
- `status`
- `sources`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `files`
- 所有 output_contract 字段

同时 nested `output_contract` 中再次包含同样的 case_id 与契约字段，不得只写在顶层或只写在嵌套。

示例结构要点：

顶层：
- case_id: 原样输入
- status: 成功/部分完成/证据不足/失败
- output_contract: 原样契约对象
- sources: 来源列表
- uncertainty: 不确定项及位置
- pending_human: 待人工项及原因
- errors: 捕获的异常
- degradations: 降级、缺失、fallback 等诚实记录
- files: 产物文件名与路径映射

nested output_contract 中继续包含原契约字段和 case_id。

## 8. 异常、边界与预算处理

异常处理统一策略：

- 任何解析失败：写 degradations，保留其他可用产物；
- case.json 缺失：记录 degradations，output_contract 视为空，继续执行；
- task.md 缺失：记录 limitations，继续执行；
- 抽取记录表为空：输出空表结构 + partial；
- CSV 编码错乱：尝试标准库编码回退，仍失败则 source_ledger 标 encoding_error；
- PDF/DOCX/图片无法解析：记录到 parse_report，不推断正文；
- 单位不可识别：进入 pending_human；
- 规则冲突：按 priority 处理，无法裁决则标 pending。

预算：

- 先运行完整单命令流程，再决定是否让 Agent 写 draft 增强；
- 确定性兜底不消耗模型请求；
- 记录 pipelines、tool calls、时间戳到 workflow_state.json；
- 不虚构 benchmark scores、金标准或人工验证结果。

## 9. 增益证据与生态文档

为便于平台对照基础 Agent 与 Skill Agent，skill 必须输出可核验证据：

- `workflow_state.json`：实际使用的脚本、phases、耗时、工具调用；
- `selfcheck.json`：完整性校验结果，不是加权自评分；
- `agent_review.md`：Agent 核验和被采纳的修正；
- `method_report.md`：规则生效情况、样例 before/after、限制。

增益应体现在：

- 同一批脏数据经过 Skill 后字段更统一；
- 换算有公式和精度，不靠临时推断；
- 去重有可解释判定键；
- 变更可回溯；
- 异常和待确认项被显式列出，而不是由 Agent 临时决定口径。

文档资源：

- `SKILL.md`
- `references/guide.md`
- `references/cleaning_guide.md`
- `references/rules_library.json`
- `references/unit_table.json`
- `environment/resources.yaml`
- `SELFTEST.md`
- `scripts/main.py`
- `scripts/clean_core.py`

所有资源只使用 Python 标准库，离线可运行，Python >= 3.8。提交文件不超过 50 个 UTF-8 文本文件，单文件不超过 500KB，总大小不超过 2MB。

## 10. 最终收尾清单

结束前必须逐项确认：

1. result.json 合法 JSON；
2. 顶层与 nested output_contract 都有 case_id 和契约字段；
3. output_contract 每个字段都有对应文件并在 result.json.files 登记；
4. cleaned_data_table.csv 可用于统计，不把缺失写成 0；
5. change_log.csv 行级可追溯；
6. pending_human.csv 明确人工接管位置；
7. gaps/degradations 诚实，不把 fallback 写成人工核验；
8. 所有可编辑 Office/slide/diagram 产物如有要求，必须同时给真实 PDF/PNG preview，并记录 preview_path；
9. 无编造文件、无编造原文、无编造领域标签；
10. 若接近预算，先保存 partial 并 finalize，保持 status 诚实。