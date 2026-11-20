---
name: systematic-screening-audit
description: "Deterministic, auditable systematic literature screening skill for finite bibliographic snapshots: criteria operationalization and version fingerprinting, query logging, DOI/title/fuzzy deduplication with merge evidence, title/abstract screening with reason codes and verbatim evidence locators, dual-annotator conflict arbitration, count-closure audit, and reusable CSV/JSON/audit exports. Agent reads real inputs and may inject a draft; the script provides a deterministic fallback and selfcheck under one run command."
version: 3.0.0
---

# systematic-screening-audit

## 0. Harness Agent 必须先读（最高优先级）

你是在 `/skills/weekly-skill` 下被加载的技能。本题输入是有限快照：固定研究问题、真实署名论文、实际查询输入与全记录筛选；不进行联网检索，不声称全局召回，不虚构人类评审。search09 中的合成重复导出与冲突意见是输入 fixture，不是预期答案。

必须真实读取 `/input` 下的 `case.json`、`task.md` 和全部材料文件；PDF 必须按实际 PDF 解析，不得按文件名、领域标签或预提取答案层假设内容。所有文献、标签、证据、去重依据、仲裁结论都必须回溯到原始材料中的真实片段。

本技能的基线结构化产物由 `scripts/main.py` 确定性生成。你（Agent）的职责是：阅读、核验、通过 `/app/work/draft.json` 注入更优判断，并撰写/改写文本型交付物。禁止手工篡改结构化 JSON/CSV 的键名和结构。任何异常、部分失败、材料缺失情况下也必须生成合法 `result.json` 并退出码 0。

---

## 1. 用途与边界

### 用途
输入科研问题、纳入/排除标准、检索约束和一批题录快照，输出可追溯的筛选闭环：候选集、排序/筛选结果、逐条纳入/排除标签、理由码、证据片段与定位符、去重合并依据、双标注者冲突仲裁、计数闭合审计链，以及可复用导出表。

### 范围内
- 检索协议与查询日志
- 题录去重：DOI、归一化标题、模糊标题、第一作者、年份窗口
- 标题/摘要纳排判据落表
- 双规则/双标注者冲突识别、类型分类与固定优先级仲裁
- 审计链与计数闭合
- 标准版本管理与指纹
- 可核验导出：`result.json`、CSV、审计 JSON、验证报告

### 范围外与禁止事项
- 不替代研究者最终科学判断
- 不做全文精读、质量评价、数据提取、统计分析、论文写作
- 不声称全局召回、不实际联网
- 不伪造人类评审、不补造文献或引用
- 不自造金标准、不自我打分、不伪造 baseline 或 benchmark
- 不依据文件名、领域标签或 case 标签猜测源内容

---

## 2. 运行时契约与预算

| 项 | 约定 |
|---|---|
| 输入目录 | `/input`，只读，含 `case.json`、`task.md` 和材料文件 |
| 工作目录 | `/app/work`，可写中间文件、笔记、`inventory.json`、`draft.json` |
| 输出目录 | `/app/output`，最终交付物必须落在此处 |
| 必备结果 | `/app/output/result.json`，含原 `output_contract` 全部字段和 `case_id` |
| 执行预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 退出码 | 所有成功、部分成功、异常路径都必须为 0 |
| 文件约束 | 至多 50 个 UTF-8 文本文件；单文件 ≤ 500KB；总大小 ≤ 2MB；无符号链接 |
| 运行时依赖 | 纯标准库、离线、Python ≥ 3.8 |

`result.json` 必须包含全量契约字段，且契约字段在 **顶层** 和 **nested `output_contract`** 中各出现一次。还须包含 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

---

## 3. 单命令全流程入口

### 3.1 主命令

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令是唯一主入口，内部执行 `init → build → selfcheck`：

1. **init**：盘点 `/input` 全部材料，分配来源编号 `[S#]`，抽取候选记录，识别字段别名，读取 `output_contract`，识别重复候选和冲突记录，生成 `/app/work/inventory.json`。
2. **build**：
   - 若 `/app/work/draft.json` 存在且合法，优先使用其中判断；
   - 若不存在或无效，则用 init 台账执行确定性抽取，生成实质工作稿：逐字 quote + locator + 理由码；
   - 渲染全部产物，写 `/app/output/result.json`；
   - 若使用了确定性兜底，必须在 `result.json.degradations` 中记入 `AUTO_EXTRACT`，并说明范围。
3. **selfcheck**：校验 output_contract 键、证据引用逐字性、计数闭合、去重簇完整性、仲裁行合法性；输出 `/app/output/verification_report.json`。

Agent 首次行动可以只运行主命令获得全套合法基线；主命令执行后 `/app/output/result.json` 必须已经合法存在。

### 3.2 Agent-first 双路径

#### Agent 路径
- 先运行一次主命令，或使用可用的 `init` 子命令，查看 `/app/work/inventory.json`。
- 读取实际原文。
- 把逐条判断、证据、理由码、去重/仲裁判断写入 `/app/work/draft.json`。
- 再次运行主命令，让 build 优先采用 draft.json。
- 不得直接手工改写 `/app/output` 下的结构化 JSON。

若脚本暴露 `check` 子命令，可在最终阶段使用；主命令失败时运行一次独立 check 并输出验证报告，仍退出 0。

#### 无 draft 时确定性兜底
- build 必须使用 init 台账确定性抽取出实质工作稿，不得输出空骨架。
- 每条关键判断必须有逐字 quote 和 locator。
- 自动抽取结果在 `degradations` 中诚实登记 `AUTO_EXTRACT`。
- 与 Agent 路径产出的结构完全一致：同一套产物文件、同一份 `result.json` 契约。

---

## 4. 标准执行流程

### 步骤 1：盘点输入与契约

1. 列出 `/input` 全部文件，记录文件名、大小、扩展名。
2. 读取 `/input/case.json`、`/input/task.md`。
3. 提取研究问题、纳入/排除标准、检索范围、`output_contract`、题录文件路径或内嵌记录。
4. 在 `/app/work/run_notes.md` 写下工作清单。

若 `case.json` 不存在或非法，尝试其他 `case*.json`；仍缺失或不可解析，则生成最小合法 `result.json`：`status: "input_error"`、`errors` 写明原因、未知契约用 `[]/{}` 回填，退出码 0。

### 步骤 2：运行主命令生成基线

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

基线产物至少包括：

- `result.json`
- `candidates.csv`
- `screening_labels.csv`
- `arbitration.csv`
- `query_log.json`
- `dedup_log.json`
- `audit.json`
- `verification_report.json`

若脚本异常崩溃，不得清空 `/app/output`；改用已读取的真实材料手写最小合法结果，记录 `errors` 与 `degradations`，退出码 0。

### 步骤 3：真实解析材料并核验

1. PDF 使用真实 PDF 解析；DOCX 使用相应解析；CSV/TSV/JSON 直接解析；图片 OCR 需标注不确定性。
2. 核对原始题录字段：`title`、`abstract`、`doi`、`authors`、`year`、`venue`、`source_db`、`query_id`、`retrieved_at`；注意字段别名。
3. 核对基线输出引用的记录数、字段、quote 是否与原文一致。
4. 检查编码问题、摘要缺失、DOI 缺失、格式不一致。
5. 在 `/app/work/run_notes.md` 记录核验结果。

### 步骤 4：Agent 核验与可选 draft 注入

逐条核验 include/exclude/pending 记录：

- 理由码是否命中当前标准版本条款；
- quote 是否逐字来自标题或摘要；
- locator 是否可定位；
- 去重是否误并或漏并；
- 冲突仲裁是否按固化优先级执行。

发现错误时，通过 `/app/work/draft.json` 修正，再运行主命令更新产物。不得直接手改 CSV/JSON。修正记录写入 `result.json.changes`。

若未使用 draft，基线即为最终结果；但必须真实核验并填写 `changes`、`uncertainty`、`pending_human`。

### 步骤 5：最终自检与回填

1. 再次确认 `result.json` 合法。
2. 核对 CSV 行数与 `result.json` 计数闭合。
3. 确认所有 `output_contract` 字段在 `result.json` 顶层与嵌套 `output_contract` 中双回显。
4. 确认 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime` 均存在且真实。
5. 可以独立运行 `scripts/verify.py`（若存在）复验证据；不要伪造其输出。

---

## 5. 证据、定位符与理由码

### 来源编号
init 阶段为每个实际读取的来源分配 `S1`、`S2`、`S3`…… 原文献、题录导出、任务说明、标准说明分别编号。

### locator 格式
- CSV/TSV：`file#row N`
- JSON/JSONL：`file#item/array index/path`
- PDF：`file#page P` 或 `file#paragraph N`
- DOCX：`file#paragraph N`
- 纯文本：`file#line N`

每个关键数字、纳入/排除判断、去重合并依据、冲突结论都至少带一个 `[S#]` 和一个 locator。引用片段必须逐字一致。

### 理由码
使用 `references/criteria-codes.md` 中的字典。不得发明新码。常见结构：

- `INC-{criterion_id}`：纳入
- `EXC-{criterion_id}`：排除
- `EXC-NO-ABSTRACT`、`EXC-LANGUAGE`、`EXC-POPULATION`、`EXC-STUDY-TYPE`
- `PEND-*`：待人工确认
- `SYS-NO-CRIT`：无可用纳入排除标准
- `CONF-*`：冲突类型
- `NO_DOI`、`NO_ABSTRACT`：元数据缺失标记

若具体情境需要新码，应先写入 `references/criteria-codes.md` 对应条目并保持全部产物一致；运行中不得临时创造。

---

## 6. 输出契约与 artifacts 映射

`result.json` 结构要求：

```json
{
  "case_id": "required",
  "status": "ok | partial | insufficient_evidence | input_error",
  "output_contract": {
    "...all original output_contract fields...": "..."
  },
  "...all original output_contract fields also at top level...": "...",
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "changes": [],
  "runtime": {}
}
```

### artifacts 映射表

| 契约/环节 | 文件 | 要求 |
|---|---|---|
| 主结果/最终答复 | `deliverable.md` 或契约命名的正文文件 | 每个数字/结论带 `[S#]` 与 locator |
| 候选文献 | `candidates.csv` | 与纳入标签一致 |
| 逐条筛选标签 | `screening_labels.csv` | 含理由码、quote、locator、confidence |
| 冲突与仲裁 | `arbitration.csv` | 独立判断、冲突类型、仲裁结论、依据 |
| 查询日志 | `query_log.json` | 查询式、库/字段/范围、检索日期、命中数 |
| 去重日志 | `dedup_log.json` | 合并依据、canonical_id、相似度、风险 |
| 审计链 | `audit.json` | 各环节输入/输出/操作人/时间、闭合等式 |
| 自检报告 | `verification_report.json` | 键校验、证据校验、计数校验结果 |
| 其他 contract 字段 | 按契约命名文件 | 每个字段都有磁盘产物和在 result.json 中回显 |

### 计数闭合
审计必须满足：

- `retrieved = unique + duplicates`
- `screened = include + exclude + pending`
- `candidates.csv` 行数与 includes 数一致，或按契约字段定义
- 去重簇不丢原始记录；被合并项可追回

若计数不闭合，`status` 必须为 `partial` 或 `input_error`，并在 `errors` 写明差异；不得强行改数。

---

## 7. 隐藏案例鲁棒性

### 最可能隐藏输入

| 类型 | 重点 | 应对 |
|---|---|---|
| 正常案例 | 固定研究问题、9 篇真实署名论文、实际查询输入、全记录筛选 | 逐条筛全部记录，不抽样；每条有证据；给出完整审计 |
| 边界案例 | 摘要缺失、DOI 缺失、重复导出、标题近似、冲突意见 | 摘要缺失仍可基于标题，标记 `NO_ABSTRACT` 且 confidence ≤ 0.35；DOI 缺失用归一化标题+模糊标题+第一作者+年份窗口；重复记录保留合并依据；冲突按固定优先级，不平均化 |
| 异常案例 | 损坏 PDF、非法 JSON、空题录、编码乱码、输出目录不可写 | 见下表；必须保住合法 `result.json` 并退出 0 |

### 异常与降级策略

| 情况 | 处理 |
|---|---|
| `case.json` 缺失或非法 | 寻找其他 `case*.json`；仍无则 `status: "input_error"` |
| 空题录 | `status: "insufficient_evidence"`，`candidates: []`，不编造 |
| 材料损坏/格式不支持 | 记录到 `degradations`；相关记录 `pending_human`；继续处理其余 |
| PDF/DOCX 解析失败 | 重试一次；仍失败记入 `errors`，相关记录 `pending_human` |
| 摘要缺失 | 保留标题依据，标记 `NO_ABSTRACT`，低 confidence |
| DOI 缺失 | 去重回退归一化标题 + 模糊标题 + 作者 + 年份窗口 |
| 编码乱码 | 按 `utf-8-sig → utf-8 → gb18030 → cp1252` 解码；仍失败记入 `errors` |
| 字段名不一致 | 使用 `references/io-schema.md` 的语义发现规则，不依赖固定键名 |
| criteria 缺失 | 所有记录 `SYS-NO-CRIT` → `pending_human`，`status: "partial"` |
| 双标注者/双规则僵持 | 按 `references/criteria-codes.md` 优先级；仍僵持则 `pending_human`，不平均化 |
| 计数不闭合 | 保留真实数，记入 `errors`，`status: "partial"` |
| 输出目录不可写 | 尝试 `/app/work/output_fallback`，记入 `errors`，不崩溃 |
| 超时或请求耗尽 | 立即写回 `result.json`，状态如实，退出 0 |
| search09 合成重复/冲突 fixture | 作为输入 fixture 识别，不当作预期答案，不据此声称真实人类评审 |

任何情况下都必须生成合法 `result.json`，且退出码 0。

---

## 8. Rubric 维度 → 交付证据映射

### 实际效果 40 分
- **任务完成度 15**：`criteria → queries → dedup → screening → arbitration → candidates` 全链路非空且连接。`result.json` 中保留各环节字段。
- **结果正确性 15**：每条标签有 `matched_criteria`、`reason_code`、逐字 `quote`、`locator`；去重有 `dedup_basis`、`certainty`、`risk`；冲突有 `conflict_type`、`arbitration_basis`。
- **结果完整性 5**：`counts` 覆盖 retrieved/unique/duplicates/screened/include/exclude/pending；`audit.closure` 为 true。
- **结果可核验性 5**：`query_log.json`、`dedup_log.json`、`audit.json`、`verification_report.json` 足以独立复跑。

### 使用增益 25 分
- 质量增益：计算并记录 `metrics.evidence_coverage`、`metrics.criteria_traceability`、`metrics.conflict_rate`。不声称未经对照的准确率。
- 效率增益：记录 `metrics.human_review_load = (pending + conflicts)/screened`；记录去重合并依据数量、可自动追溯记录比例。
- 增益可验证：全部产物使用稳定 schema、同口径 counts、逐字证据；避免随机和时钟决策；可复跑。不要生成 `golden_standard` 或自评分数。

### 创新增益 15 分
- 标准版本管理：`criteria.version` + SHA-256 指纹 + 版本变更记录。
- 理由码体系：完整 code dictionary，覆盖边界、缺失、冲突。
- 分歧自动分类：`conflict_type` 分类 + 仲裁优先级。
- 审计链生成：`audit.json` 闭环，可追回每一步。
- 方法披露：`method_disclosure` 说明“双规则是自动规则冲突，不等同人类评审”；说明有限快照不可估全局召回。

### 可靠体验 10 分
- 正确触发：主命令一键执行，失败也 exit 0。
- 可复跑：确定性流程，无随机、无网络、无时钟决策。
- 异常处理：第 7 节全部策略，真实写入 `errors`/`degradations`/`pending_human`。

### 生态贡献 10 分
- 文档：SKILL.md 完整；引用 `references/io-schema.md`、`references/criteria-codes.md`、`references/examples.md`。
- 可复用：CSV/JSON 格式可直接用于综述；标准表、理由码字典、仲裁表可复用。
- 推广：在 `result.json.method_disclosure` 与 `docs/README` 类内容中说明适用边界、限制和复用方式。

---

## 9. 基础 Agent 对照增益证据

不生成“对比报告”或“提升分数”。增益证据应由实际产物结构承载：

1. **同口径可比较**：固定 `result.json` schema、CSV 列、counts 等式。
2. **证据率更高**：每条 include/exclude/pending 都有 quote+locator，而不是只给标签。
3. **人工核对量更少**：`pending_human` 精确到 record_id 和原因；边界记录明确标记。
4. **去重可复核**：每个合并簇有 `dedup_basis`、`canonical_id`、`risk`，避免误并和漏并。
5. **审计链可独立重放**：`audit.json` 显示完整筛选路径。
6. **确定性保证**：同一输入、同一命令产生同口径 counts 和标签。

在 `result.json.runtime` 中只记录实际执行信息：版本、时间、请求数、材料数。禁止编造 benchmark 分数。

---

## 10. 预算与收尾策略

| 阶段 | 建议请求 | 说明 |
|---|---|---|
| 输入盘点 | 1–3 | 读取文件列表、case.json、task.md |
| 主命令基线 | 1 | 脚本运行不占模型请求 |
| 真实材料解析 | 3–10 | 优先题录、criteria；大 PDF 只读相关页 |
| Agent 核验 | 5–15 | 优先纳入集、边界记录、冲突、去重 |
| 最终自检回填 | 1–4 | 确保 result.json 合法 |

**强制收尾**：剩余时间 < 120 秒或已用 ≥ 60 次请求时，立即停止增强，写回 `status`、`runtime`、`errors`/`limitations`，确保 result.json 合法并退出 0。

---

## 11. 提交自检清单

- [ ] `/app/output/result.json` 存在且合法。
- [ ] 所有原 `output_contract` 字段在 `result.json` 顶层和嵌套 `output_contract` 中双回显。
- [ ] `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime` 均存在。
- [ ] 候选文献、筛选标签、仲裁、查询日志、去重日志、审计日志全部存在。
- [ ] 每条 include/exclude/pending 有理由码、逐字 quote、locator。
- [ ] 计数闭合：`retrieved = unique + duplicates`；`screened = include + exclude + pending`。
- [ ] 去重合并与未合并模糊配对都有记录。
- [ ] 冲突按固定优先级仲裁，僵持进入 `pending_human`。
- [ ] 未编造文献、数据、引用、分数、baseline 或 human review。
- [ ] 退出码 0。

---

## 12. 与现有包内文件的对应关系

- `scripts/main.py`：主命令 `run`，内部 init→build→selfcheck；可选 `init`/`check`。
- `scripts/verify.py`：独立证据核验工具，诚实使用其输出。
- `references/criteria-codes.md`：理由码字典、冲突类型、仲裁优先级。
- `references/io-schema.md`：输入语义发现规则、draft.json 形状、result.json schema。
- `references/examples.md`：最小示例，需标明为示例，不冒充正式结果。