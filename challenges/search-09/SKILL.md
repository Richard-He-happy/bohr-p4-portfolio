---
name: literature-quality-appraisal
description: Evidence-anchored literature quality appraisal and search traceability. Reads actual /input files (PDF/DOCX/CSV/JSON/metadata) and produces a traceable candidate set with query/filter logs and a dimension -> judgment -> verbatim evidence + locator -> grade appraisal table. Use when the task asks for critical appraisal, risk-of-bias assessment, reporting completeness, search traceability, or a review-ready evidence table.
version: 2.0.0
license: MIT
---

# literature-quality-appraisal

**一句话用途**：对给定科研问题与文献材料产出可复核的「候选集 + 检索/筛选日志 + 质量评价表」。每条判断必须绑定：维度 → 条目 → 判定 → 原文逐字证据 → 定位 → 等级。

**核心原则**：实际输入文件和原论文是事实依据；不补造文献、统计量、DOI、页码或“看起来合理”的结论。证据不足就写 `unappraisable` 或 `not_reported`，并进入 `pending_human`。

---

## 0. 最高优先级：Agent 必须真实读材料，脚本只是工具

你是 Harness Agent，最终交付物必须由你实际读 `/input` 材料、核验、补全、撰写。脚本负责生成结构化基线、校验一致性和渲染产物；你不能把脚本空模板或未核验结果当最终成品。

禁止事项：

1. 禁止手改 `result.json`、`claims.json`、`evidence_table.json` 的结构字段；如需修正，通过 `draft.json`、`agent_review.json`、`pending_human.json` 或调用脚本函数完成，并在 `changes` 记录。
2. 禁止根据文献标签、标题、摘要印象或领域先验补造正文证据。每条判断必须可定位到原文。
3. 禁止自造 `golden_standard`、`diff_report`、加权自评分、benchmark 分数、平台对照分。只报告本 Skill 的真实运行结果。
4. 禁止把“脚本未检出”写成“原文没有”；应写“当前条件下未在可用文本中检出”，并记录检索探针或限制。
5. 禁止删除、清空或遗漏 output_contract 字段；部分完成必须显式登记。
6. 任何异常也必须最终产生合法 `result.json` 并 `exit 0`。

---

## 1. 单命令全流程入口

安装后唯一命令：

```bash
python3 scripts/appraise.py run --input /input --output /app/output --work /app/work
```

`run` 内部固定执行三个阶段：

1. **init**  
   盘点输入、建立来源编号、抽取候选、生成冲突分组、写 `/app/work/ledger.json` 和 `/app/work/inventory.json`。

2. **build**  
   校验 draft；若无 draft 则启用确定性兜底抽取生成工作稿；校验 quote/locator；渲染全部产物；最终化 `/app/output/result.json`。

3. **selfcheck**  
   检查 output_contract 字段是否齐全、磁盘产物是否齐全、每个关键数字/论断是否带 `[S#]` 与 locator、result.json 是否可被 JSON 解析。

**异常处理**：无论 init/build/selfcheck 是否发生错误，最终都要写 `/app/output/result.json`，包含 `status`、`errors`、`degradations`，并以 `exit 0` 结束。

可单独调用子命令用于 Agent 增量工作流：

```bash
python3 scripts/appraise.py init --input /input --output /app/output --work /app/work
python3 scripts/appraise.py check --input /input --output /app/output --work /app/work
python3 scripts/appraise.py build --input /input --output /app/output --work /app/work
python3 scripts/appraise.py selfcheck --input /input --output /app/output --work /app/work
```

脚本用 `Path(__file__).resolve().parent` 定位资源，不依赖 CWD。

---

## 2. Agent-first 双路径

### 2.1 Agent 路径（优先）

1. 先运行 `init`，读 `/app/work/ledger.json` 获取来源、候选和冲突分组。
2. 实际打开 `/input` 中每篇文献，逐段阅读方法与结果、偏倚相关段落、局限性、图表说明。
3. 把判断写入 `/app/work/draft.json`。格式见 `references/guide.md`。
4. 运行 `check`，脚本会校验 quote/locator/字段/契约。
5. 运行 `build`，渲染最终产物并写入 `result.json`。

### 2.2 无 draft 时的确定性兜底

若 Agent 未写 `draft.json`，`build` 必须依据 `init` 台账确定性抽取生成实质工作稿，逐条抽取原文逐字 quote 与 locator，并在 `result.json.gaps` / `result.json.degradations` 中写入：

```json
{
  "code": "AUTO_EXTRACT_WITHOUT_AGENT_REVIEW",
  "message": "No draft.json found; deterministic extraction was used. Quotes and locators were machine-generated and not verified by the agent.",
  "level": "partial"
}
```

两条路径必须产出同一套磁盘产物、同一份 `result.json` 契约；差异只能体现在 `status`、`changes`、`degradations`、`pending_human`。

---

## 3. 输出契约与磁盘产物

最终 `/app/output` 必须包含以下文件，且与 `result.json` 字段一一对应：

| 文件 | 必需内容 | rubric 证据价值 |
|---|---|---|
| `result.json` | 完整契约结果：顶层契约字段 + nested `output_contract` + 状态/来源/不确定性 | 所有维度 |
| `candidates.csv` | 候选文献、排序/筛选结果、元数据、`[S#]` 来源 | 实际效果、可核验性 |
| `query_log.json` | 查询、筛选、排序、追踪依据；空结果/错误正常记录 | 实际效果、可核验性 |
| `appraisal.csv` | 行级评价表：维度-条目-判断-原文证据-页码/章节-等级 | 实际效果 40 分核心 |
| `appraisal_report.md` | 可读评价报告，关键数字/论断带 `[S#]` 与 locator | 任务完成度、可核验性 |
| `evidence_table.json` | 结构化证据表：claim_id、quote、source_id、locator、strength | 结果正确性、可复核 |
| `claims.json` | 结构化声明：claim_id、statement、support_scope、counts | 完整性 |
| `agent_review.json` | Agent 核验结果：逐条 verified/rejected/conflicting/reason；脚本修复记录 | 使用增益、可核验性 |
| `pending_human.json` | 需要人工复核、OCR、全文获取、分歧裁决的条目 | 可靠体验、异常处理 |
| `verification.json` | `selfcheck`/`check` 的真实校验输出 | 增益可验证性、可靠 |

如存在 `deliverable.md` 与 `evidence_driven_draft.md` 两者，二者内容必须不同：前者是干净成稿，后者是带证据标记草稿，不得复制粘贴同一文本。

---

## 4. `result.json` 双回显与标准键

`result.json` 必须是合法 JSON，并满足：

1. 所有原始 `output_contract` 字段（含 `case_id`）出现在**顶层**。
2. 同时作为一个完整对象出现在 `result.json.output_contract` 中。
3. 顶层至少包含：

```json
{
  "case_id": "case-...",
  "status": "ok|partial|degraded|input_error",
  "sources": [{"source_id": "S1", "uri": "/input/artifacts/...", "kind": "pdf", "access": "full_text"}],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "gaps": [],
  "conflicts": [],
  "changes": [],
  "runtime": {"started_at": "...", "finished_at": "..."}
}
```

`status` 只能来自真实状态：全部完成且核验通过为 `ok`；部分完成或存在未核验为 `partial`；仅有摘要/不可解析/关键证据缺失为 `degraded`；输入非法或不可识别为 `input_error`。

---

## 5. 质量评价量表与分级规则

必须覆盖四类核心维度，并根据文献类型启用特有检查点：

| 维度 | 示例条目 | 必需证据 |
|---|---|---|
| 研究设计 | 设计类型、对照/暴露定义、随访/观察窗口、方案是否适用 | 方法章节原文 + 图表编号 |
| 证据充分性 | 样本量依据、抽样方式、结局测量、统计功效、效应量与置信区间 | 结果、统计方法、表格 |
| 偏倚风险 | 选择、实施、测量、随访、报告等适用领域 | 偏倚相关原文，明确“明确存在/可能存在/未见迹象/证据不足” |
| 报告完整性 | 报告规范条目、缺失项、预印本状态、方案注册、局限性 | 全文或摘要，未报告登记 |

每个条目必须：

- 有稳定 `item_id`，如 `D1.1`、`E2.1`、`B3.1`、`R4.1`。
- 写清判定所需证据。
- 写清什么情况下判定为 `not_reported` 或 `unappraisable`。
- 支持弃权：证据不足时不得猜判断。

分级汇总规则要显式化，例如：

- 任一高风险偏倚条目为 `high` → 总偏倚风险为 `high`。
- 存在关键条目 `unappraisable` 且无替代证据 → 总等级不得为 `low`，应标 `unclear`。
- 至少 4 个维度均完成且无高偏倚、无严重报告缺失 → 才可为 `low`。
- 分级理由必须写清由哪些条目、阈值、汇总规则得到，不得只给孤立等级标签。

---

## 6. 证据定位与引用格式

每条关键数字、统计量、判断、引文必须使用：

- 来源编号：`[S#]`
- 定位：`[S#] 文件名#页码/段落号` 或 `[S#] 文件名#章节/图表编号`
- 原文逐字 quote：`evidence_quote` 字段必须与原文一致，不得改写。

优先使用句子级或表格级定位；无法定位时，显式写：

- `locator_page`: `null`
- `locator_section`: `"methods"`
- `locator_status`: `"approximate_section"` 或 `"not_available"`
- `abstain_reason`: 说明原因。

---

## 7. 检索与筛选可追溯性

### 7.1 候选集

`candidates.csv` 每条候选必须包含：

- `candidate_id`
- `source_id`，如 `[S1]`
- `title`
- `authors`
- `year`
- `container`
- `doi` 若有，否则写空
- `source_db`
- `retrieved_at`
- `query_id`
- `provenance.source_file`
- `provenance.json_pointer` 或 `locator`
- `included` / `excluded`
- `inclusion_reason` / `exclusion_reason`

若检索结果缺失元数据，不得补造；应写入字段为 `"missing"`，并把限制登记到 `gaps`。

### 7.2 查询日志

`query_log.json` 每条必须记录：

- `query_id`
- `query_text`
- `database`
- `time`
- `status`: `ok` / `empty` / `error` / `rate_limited`
- `filters`
- `hits`
- `error_message` 若有

所有 `error`、`empty` 查询也必须保留，不得静默删除。

### 7.3 遗漏与冲突

- 材料缺失、无全文、仅有摘要、图表不可解析、权限不足：写入 `gaps` / `pending_human`，不猜补。
- 元数据冲突：年份/期刊/作者不一致时，保留多来源，冲突写入 `conflicts`，不静默取其一。

---

## 8. 完整执行流程

### 步骤 1：盘点和读取契约

- 读 `/input/case.json`、`/input/task.md`。
- 确认 `case_id` 和 `output_contract` 全部字段及类型。
- 扫描 `/input` 下所有文件，按扩展名 + 魔数识别实际材料：PDF `%PDF`、DOCX/ZIP、PNG/JPG、CSV、XLSX、JSON、JSONL、TXT/MD。
- 写 `/app/work/plan.md`：契约字段清单、artifact 清单、优先交付物、缺失材料。

失败分支：`case.json` 缺失或非法 → 降级查找 `case*.json`、`task.md`、`*manifest*.json`；仍失败则写最小合法 `result.json`，`status=input_error`，退出 0。

### 步骤 2：首先生成基线

运行：

```bash
python3 scripts/appraise.py run --input /input --output /app/output --work /app/work
```

脚本会自动完成 init → build → selfcheck。你应在运行后检查文件完整性，再进行 Agent 核验与增强。

失败分支：若脚本崩溃或未生成某些文件，作为 Agent 必须按 output_contract 手工补齐所有生产物；异常写 `errors`，不得留空。

### 步骤 3：真实解析材料并核验证据

- 对每份文献实际解析。脚本内置 `pdf-text-tool` / `pdftotext` / `pypdf` / `fitz` 探测；缺失时用内置抽取器。
- 亲自阅读方法与结果、局限性、偏倚相关内容。
- 逐条核验脚本产出：
  - `evidence_quote` 是否逐字一致；
  - `locator_page` / `locator_section` 是否真实对应；
  - `judgment` 是否与证据一致。
- 对 `not_reported` / `unappraisable` 条目，反向搜索探针词，确认证据缺失。

输出：将核验结果写入 `agent_review.json`：每条 `verified` / `rejected` / `conflicting` / `pending_human`，以及你发现但脚本漏掉的维度或证据。

失败分支：某文档全文不可得、扫描件无文本、图不可解析 → 相关条目全部 `unappraisable`，写 `pending_human`，不猜内容。

### 步骤 4：候选集与检索日志增强

- 核对每条 `candidate` 的检索来源、时间、过滤条件、provenance。
- 检查是否按 year/lang/topic 筛选；重复项合并为一条并保留多来源。
- 记录元数据冲突与检索失败。

失败分支：检索响应 `error`/`status!=ok`/限流 → 保留 query 记录 `status:"error"`，不重试不编造结果；空结果记录 `status:"empty"`。

### 步骤 5：Agent 产出完整成品

- 亲自撰写或改写 `appraisal_report.md` 的核心分析段落。
- 每篇文献给出「设计—证据—偏倚—报告完整性」的可读总结，引用原文句子和位置。
- 保留 `appraisal.csv` 行级证据，并在报告开头说明哪些行已经过核验。

失败分支：时间或预算不足先落盘当前 best-effort partial，后续再增强；不得删除已完成的基线产物。

### 步骤 6：自检 rubric 与完整性

逐项对照 `references/rubric.md`、`references/io_contract.md`、`references/playbook.md`：

- output_contract 每个键是否已在 `result.json` 中存在且非默认空。
- 磁盘产物是否齐全：`result.json`、`candidates.csv`、`appraisal.csv`、`query_log.json`、`appraisal_report.md`、`evidence_table.json`、`claims.json`、`agent_review.json`、`pending_human.json`。
- 关键字段是否双回显：顶层 + nested `output_contract`。
- 是否每个关键数字/论断有 `[S#]` 来源与 locator。
- 是否无未说明的空值、无虚构数据、无孤立等级。

输出：更新 `result.json.selfcheck`，记录断言结果与未满足项。

### 步骤 7：回填 result.json 并最终化

- 确保顶层 = 原 output_contract 全部字段 + 标准键。
- 填写 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- 所有增强和核验写入 `changes`，如：`agent_verified D1.1 quote; fixed locator_page from 7 to 8`。
- 最终原子写：先写 `tmp` 再 `os.replace`。

失败分支：任何异常写 `result.json` 后退出 0；若无法写完整 JSON，至少写最小合法 `{"case_id":null,"status":"input_error","errors":[...]}` 并退出 0。

---

## 9. 隐藏案例鲁棒性

### 9.1 正常案例

- 有 1–N 篇文献全文 PDF/题录/表格/检索响应导出。
- 必须产出完整评价表、候选集、检索日志、证据表、报告，且能逐条复核。

### 9.2 边界案例

- 只有摘要或元数据：质量评价仍可完成可评价维度；缺失维度写 `not_reported` / `unappraisable`，不写“原文没有”除非可验证。
- 扫描件/图表不可解析：自动 OCR 不可用时标 `unappraisable`，写 `pending_human: "OCR needed"`。
- 非英语文献：应真实按原文语言理解，禁止用语言标签自动否定；若无法解析则诚实降级。
- 预印本/报告不全：按预印本状态评价，报告完整性条目写清“预印本可能缺 peer review 后元数据”，不冒充正式版。
- 重复候选：合并并保留多来源；来源/元数据冲突写 `conflicts`。
- 空检索结果：保留 `query_log.json` 中 `status:"empty"`，不编造文献。

### 9.3 异常案例

- `/input/case.json` 缺失或非法：降级，写最小合法 result，退出 0。
- 文件损坏：识别为可用的其他文件，损坏文件相关条目标 `unappraisable`。
- 全部输入为空：写 `status:"input_error"`，无文献结果，不造数据。
- 脚本中间文件缺失但可重算：用确定性 fallback 重新生成。
- 时间/预算耗尽：保留已生成的 partial，最终 result 合法，写清未完成部分。

---

## 10. 预算策略

| 阶段 | 建议模型请求 | 必须完成 | 可缩减 |
|---|---|---|---|
| init + 运行单命令 | 1–2 | 生成全套基线，检查磁盘文件 | 细读全部材料 |
| 读原文与核验 | 8–20 | 逐条核验高权重条目、补漏、修正 | 低风险条目可抽样核验 |
| 成稿增强 | 4–8 | 将泛化总结改写为可复核判断 | 不重要的背景描述 |
| selfcheck 收尾 | 2–4 | 补齐契约字段、写 result、退出 0 | 忽略非必需美化 |

脚本是纯 CPU，不消耗模型请求。接近 64 次 / 900 秒时，立即保存 partial、写 result、退出 0。

---

## 11. 与基础 Agent 对照的增益证据

在 `agent_review.json` 和 `result.json.changes` 中显式记录：

- 本 Skill 新增了维度化条目，而不是泛化摘要。
- 本 Skill 为每条判断提供了逐字 quote 与 locator。
- 本 Skill 对证据不足显式弃权，而不是补齐纸面完整。
- 本 Skill 保留了检索失败、元数据冲突、空结果等真实状态。

`verification.json` 应包含可被第三人复用的校验断言，不包含自评 benchmark。

---

## 12. 生态与可靠体验

包内必须提供：

- `SELFTEST.md`：自检清单、最小调用示例、预期输出。
- `environment/resources.yaml`：预装依赖声明，仅 Python 3 标准库；若可用 `pdf-text-tool` / `pdftotext` / `pypdf` / `fitz` 则优先，否则降级。
- `references/guide.md`：`draft.json` 形状、工作流说明、字段含义。
- `references/rubric.md`：评分维度到本 Skill 动作的映射。
- `references/io_contract.md`：output_contract 字段、磁盘产物、result.json 标准键。
- `references/playbook.md`：异常处理 playbook。

约束：

- 离线运行，不依赖未说明的个人文件或手工操作。
- 纯标准库、Python 3 ≥ 3.8。
- 中英文自适应。
- ≤ 50 个 UTF-8 文本文件，每个 ≤ 500KB，总大小 ≤ 2MB。
- 不提交预生成答案、白板或隐藏测试结果。

---

## 13. 必须避免的扣分项

1. 把摘要换一种说法当评价表，缺少维度-判断-证据-等级。
2. 证据 quote 不逐字，或 locator 对不上原文。
3. 原文缺失却补造合理判断，不写 `not_reported` / `unappraisable`。
4. 孤立等级，无分级阈值和汇总轨迹。
5. 检索失败、空结果、元数据冲突静默丢弃。
6. 手改 JSON 导致 claim_id / source_id / locator 不一致。
7. 运行崩溃且不产生 result.json，或退出码非 0。
8. 把文字自述当增益证据，不给真实可核验记录。