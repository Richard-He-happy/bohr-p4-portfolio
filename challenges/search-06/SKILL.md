---
name: literature-delta-tracker
description: >-
  Incremental literature discovery and tracking Skill for source-bound scientific cases. It implements the closed loop of subscription configuration → fixed-window retrieval → previous snapshot diff → new/update/retraction list → reproducible alerts. It parses organizer-supplied Crossref/EuropePMC/publisher snapshots, JSONL, CSV, XML, PDF and task material without live network access, normalizes identities, merges duplicates and preprint/version/retraction chains, emits delta windows with verbatim evidence locators, and writes an honest result.json containing all original output_contract fields and case_id. Use when the task asks for latest/new/weekly literature tracking, fixed-window new-item detection, topical subscription, deduplication, version-chain merging, or a delta against an earlier snapshot. It is agent-first but also has a deterministic fallback so the full deliverable is produced even when no model draft is available.
version: 2.0.0
license: MIT
---

# ★ Agent 修改边界（最高优先级，先读这里）

本 Skill 的结构化产物由 `scripts/main.py` 与 `scripts/core.py` 生成；你（Agent）的职责是真实阅读材料、核验证据、补强文本型交付物，并诚实标注限制。**不是重写结构化 JSON 的键名或结构**。

必须遵守：

1. **禁止手改结构化产物**：`result.json`、`evidence_table.json`、`query_log.json`、`alerts.json`、`snapshot.json` 的字段键名必须保留脚本输出。不能手工覆盖为无依据内容。
2. **允许 Agent 做的事**：
   - 真实阅读 `/input` 下所有材料，核验候选的标题、DOI、作者、期刊、日期、版本、窗口归属、去重与提醒判断；
   - 把判断写入 `/app/work/draft.json`；
   - 写 `agent_review.json` / `agent_review_notes.json`：逐条给出 `verified`、`rejected`、`conflict`、`missing_evidence`、`pending_human`；
   - 改进正文型交付物，但每个数字、引用、论断必须能在证据表或原始材料中找到依据；
   - 若发现脚本缺陷，写临时 Python 调脚本函数重算，并在 `agent_review.json` 的 `script_fixes` 记录，**不能手工篡改 JSON**。
3. **禁止生成无依据的评分/金标准**：不伪造 benchmark、不伪造 baseline、不伪造成绩。只记录脚本真实输出 `verification.json` / `core.py` 结果。
4. **完整性自检**：结束前核对「`output_contract` 字段 × 磁盘文件 × `result.json` 键」一一对应。`deliverable.md` 与 `alerts.md` 等正文产物不能复制同一文本冒充不同产物。
5. **预算**：先用单命令产出全套基线；剩余请求用于逐条核验与修正。接近 64 次 / 900 秒时立即收尾，保证 `result.json` 合法且 `status` 诚实。

# 0. 给 Harness Agent 的最高优先级指令

你是最终交付负责人。`scripts/main.py` 和 `scripts/core.py` 只是工具。**最终交付必须真实、可回放、可核验**。

执行顺序固定为：

1. **init**：盘点输入、来源编号、候选抽取、冲突分组。
2. **读取与判断**：读台账和原始材料，写 `/app/work/draft.json`（无模型时间则跳过）。
3. **build**：校验、兜底抽取、渲染全部产物、finalize `result.json`。
4. **selfcheck**：用 `scripts/core.py` 检查产物与契约。

**标准入口命令：**

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

若安装环境不支持 `run` 子命令，按序执行：

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

**任何情况下 exit code 必须为 0**，包括坏 JSON、空输入、脚本异常、超时降级、材料缺失。异常写入 `errors[]` / `degradations[]`，不空手退出。

# 1. 用途与边界

本 Skill 解决“最新文献发现与追踪”的增量判定问题：给定订阅主题、查询集、固定时间窗和上一快照，返回相对上一快照真正新增或改变的文献，并保留可回放依据。判断是否正确，不看抓了多少条，而看三件事：**新增判断是否可复算、重复与误报是否被压住、每次提醒是否有回放依据**。

在范围内：

- 订阅配置与查询式记录；
- 固定时间窗定义、UTC 归一、跨窗边界与延迟补录判断；
- 来源快照解析、记录归一、稳定去重键；
- 预印本→正式版→修订→勘误/撤稿链合并；
- 快照 diff、新增/更新/撤稿更正识别；
- 提醒合并/抑制/投递记录；
- 回放证据、locator、quote、状态和不确定性登记。

不在范围：

- 全文阅读、自动写综述、未经授权的定时抓取；
- 把提醒内容当科学结论；
- 实时网络检索、全球最新论文声称、无来源的全文/引用/状态声明；
- 编造 DOI、作者、日期、引用、分数或来源。

# 2. 何时使用 / 不使用

**使用**：任务包含文献记录，且要求“latest / new / weekly literature tracking”、主题订阅、两个快照/日期窗口之间的新增条目、去重、版本追踪、或对旧快照的 delta diff。

**不使用 / 无记录**：输入没有任何 record-like 材料时，必须返回 `status=insufficient_evidence` 或 `input_error`，在 `missing[]` 说明缺少什么，不发明文献。

# 3. Runtime contract（必须逐条落实）

- 输入 `/input`（只读）：`case.json`、`task.md`、题面规定的材料。材料可能包括 JSON/JSONL/CSV/XML/PDF/DOCX/图片。**必须真实解析材料内容**，不能依据文件名或领域标签猜测/补造。
- 工作目录 `/app/work`：可写状态、清单、临时校验、draft、review 笔记等。
- 输出 `/app/output`：最终 `result.json` + 全部 sidecar。
- `result.json` 必须包含题面/`case.json` 中声明的 `output_contract` 全部字段（键名不改）与 `case_id`，并添加真实状态字段。
- 每个关键数字、候选、提醒、窗口归属必须有 `[S#]` 来源与 `文件#行号/段落号` locator。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。先完成高权重交付物，尽早落盘 honest partial，再增量改进。
- 诚实性：`status/sources/uncertainty/pending_human/errors/degradations/changes/missing` 必须真实；不确定或材料不足显式标注，不编造。
- 任何情况下 exit code 为 0。

# 4. 单命令全流程入口

标准命令同时满足 init → build → selfcheck：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

可选 flags：

- `--window-start YYYY-MM-DD`：覆盖窗口起点；
- `--window-end YYYY-MM-DD`：覆盖窗口终点；
- `--now YYYY-MM-DD`：冻结时钟，保证重复运行幂等；
- `--max-k N`：限制候选输出上限。

说明：

- **init**：盘点 `/input` 材料、分配 `S#` 来源编号、抽取候选记录、按身份冲突分组、写 `/app/work/agent_workplan.json` 与 `/app/work/manifest.json`。
- **build**：校验已有 draft 或确定性兜底抽取，渲染 `result.json` 与全部 sidecar。
- **selfcheck**：调用 `scripts/core.py --input /input --output /app/output` 校验产物与契约。

脚本首先生成的是**基线产物**，不是最终成品。你需要在其上核验与增强。

# 5. 执行流程（编号步骤）

## 步骤 1：init 盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、`/input` 下全部材料。

**动作**：

1. 读 `case.json`；若缺失，扫描任意 `case*.json`。保留 `case_id` 和 `output_contract` 原样。
2. 读取任务说明、订阅主题、查询式、窗口起始、来源范围、约束和评分要求。
3. 递归扫描 `/input/**`，按内容识别材料类型；不要只凭文件名假设来源。
4. 识别当前候选记录与 `previous|snapshot|baseline|state` 历史文件。
5. 对 PDF/DOCX/图片，实际调用可用解析工具；解析失败记录到 `degradations[]`。

**输出**：`/app/work/agent_workplan.json`，至少包含：

- 关键输入文件路径；
- `output_contract` 字段列表；
- 识别到的订阅主题、查询、窗口提示；
- rubric 权重最高的交付物清单；
- 材料解析状态。

**失败分支**：

- `case.json` 缺失或不可解析：挖其他 JSON，仍不可用则准备最小合法 `result.json`，`status=input_error`，`errors[]` 写明原因，退出码 0。
- 某材料无法解析：记 `degradations[]`，继续处理。

## 步骤 2：运行基线脚本产出全套骨架

**动作**：运行单命令 `run`，确保 `/app/output` 创建并写入 sidecar。

**预期 sidecar**：

- `result.json`
- `candidates.csv`
- `query_log.json`
- `evidence_table.json`
- `alerts.json`
- `alerts.md`
- `snapshot.json`
- `deltas/window_NN.json`

**失败分支**：

- 脚本异常/超时：把异常写入 `/app/work/script_error.txt`；仍调用 `scripts/core.py` 静态检查；若 `result.json` 未生成，创建包含全部 `output_contract` 字段与 `case_id` 的最小合法 JSON，`status=partial` 或 `input_error`，退出码 0。
- 脚本成功但少字段：补齐缺失字段，不删除已生成内容。

## 步骤 3：真实解析材料并核验证据

**动作**：

1. 打开 `/input` 材料，逐条核验候选：标题/DOI/作者/期刊/日期/版本是否真实出现在输入材料中。每个 DOI 若存在必须能在输入文本 verbatim 找到；不能补造。
2. 核验窗口归属：是否按 `[start, end)` UTC import/index/available date 判断；跨窗、延迟入库、补抓是否被正确标记。
3. 核验版本链：预印本→正式版→修订→勘误/撤稿是否合并为同一 work；保留各节点。
4. 核验去重：同文多源是否合并，去重键是否稳定，有无误合并。
5. 核验提醒：是否一个 merged work 只提醒一次；撤稿/更正绝不抑制；低置信进入 pending，不静默丢弃。
6. 记录脚本判断与你阅读材料后判断不一致处。

**输出**：`/app/work/agent_review_notes.json`：`verified`、`conflicts`、`missing_evidence`、`pending_human`、`fixes_to_apply`。

**失败分支**：

- 材料缺失：`uncertainty[]` / `pending_human[]` 标明，不伪造。
- 冲突：保留基线产物，在 `result.json` 标 `conflict` 并列出双方依据。

## 步骤 4：Agent 路径与 draft.json

若条件允许，在 init 后不要立即 finalize。应：

1. 读 `/app/work/manifest.json` 台账和 `/input` 原始材料。
2. 把判断写入 `/app/work/draft.json`：

```json
{
  "case_id": "来自 case.json",
  "reviewed_sources": ["S1", "S2"],
  "selected_candidate_ids": ["C1", "C2"],
  "excluded": [{"candidate_id": "C3", "reason": "out_of_scope", "evidence_locator": "S2::file.json#para3"}],
  "merged_works": [{"work_id": "W1", "member_ids": ["C1", "C4"], "canonical_id": "C1", "version_chain": "preprint->published"}],
  "alerts": [{"work_id": "W1", "alert_type": "new", "emit": true, "reason": "first seen in window"}],
  "window_attributions": [{"candidate_id": "C5", "window_status": "recovered_late", "actual_window": "2024-01-01"}],
  "missing": ["缺少 PMID 字段"],
  "uncertainty": ["S3 日期不含时区，未确认 UTC 归属"],
  "pending_human": []
}
```

3. 再运行 `build`，由脚本合并 draft 与确定性抽取。

draft 中的 quote、DOI、作者、日期等必须来自原文；没有原文依据的字段写 `null` + `missing`。

## 步骤 5：无 draft 时的确定性兜底

若无 `/app/work/draft.json` 或 draft 无效，`build` 必须：

- 使用 init 台账确定性地抽取候选；
- 为每个保留字段生成逐字 `quote` 与 `locator`；
- 将 `AUTO_EXTRACT=true` 诚实记入 `gaps[]` / `degradations[]`；
- 生成与 Agent 路径**同一套产物、同一份 result.json 契约**；
- 不得因无 Agent 判断而少写 `output_contract` 字段。

兜底抽取必须保守：没有原文依据的字段标 `UNVERIFIED` / `missing`，不能冒充事实。

## 步骤 6：build 与 finalize

**动作**：

1. 合并 Agent draft（如存在）和脚本候选；
2. 校验候选/去重/版本链/窗口/提醒；
3. 渲染全部产物：
   - `result.json`
   - `candidates.csv`
   - `query_log.json`
   - `evidence_table.json`
   - `alerts.json`
   - `alerts.md`
   - `snapshot.json`
   - `deltas/window_NN.json`
4. 核对 `output_contract` 字段在 `result.json` 顶层与 nested `output_contract` 中各出现一次；
5. 写本轮 watermark / snapshot，确保下一窗口可复算。

## 步骤 7：selfcheck 与最终校验

**动作**：

1. 运行 `python3 /skills/weekly-skill/scripts/core.py --input /input --output /app/output`；
2. 检查 `result.json` 合法性；
3. 按第 10 节自检清单逐项核对；
4. 确认 exit code 0；
5. 若时间不足，立即写回当前 `result.json`，`status=partial`，所有契约字段保留。

# 6. 输出产物与字段

## `result.json`

必须包含 `case_id` 和题面声明的全部 `output_contract` 字段；并在 `output_contract` nested 对象中再回显一次。推荐同时包含：

```json
{
  "case_id": "case-001",
  "status": "complete | partial | insufficient_evidence | input_error",
  "output_contract": {},
  "subscription": {"topic": "", "query": "", "window_start": "", "window_end": "", "timezone": "UTC"},
  "summary": {
    "source_count": 0,
    "raw_record_count": 0,
    "candidate_count": 0,
    "dedup_key_count": 0,
    "new_count": 0,
    "version_update_count": 0,
    "retraction_count": 0,
    "correction_count": 0,
    "duplicate_count": 0,
    "recovered_late_count": 0,
    "out_of_window_count": 0,
    "alert_count": 0
  },
  "candidates": [],
  "alerts": [],
  "query_log": [],
  "sources": [],
  "evidence": [],
  "dedup_keys": [],
  "version_chains": [],
  "snapshot": {},
  "uncertainty": [],
  "pending_human": [],
  "conflicts": [],
  "errors": [],
  "degradations": [],
  "missing": [],
  "changes": [],
  "runtime": {"auto_extract": false, "agent_reviewed": false, "model_requests_used": 0}
}
```

若 `output_contract` 中已存在同名字段，以题面原字段为准，不另起冲突字段。

## `candidates.csv`

至少包含：`candidate_id,work_id,title,doi,arxiv,pmid,journal,publication_date,version_status,source_id,source_locator,window_status,dedup_status,confidence,relevance_note`。

一行对应一个候选/merged work；若一个 work 有多个版本节点，保留主节点并另列 `version_chain` 成员。

## `query_log.json`

每个查询一条：

```json
{"query_id":"Q1","query_text":"...","window_start":"...","window_end":"...","source_id":"S1","raw_count":10,"candidate_count":8,"new_count":4,"duplicate_count":2,"version_update_count":1,"retraction_count":0,"error_count":0,"status":"ok"}
```

## `alerts.json`

每个提醒一条：

```json
{"alert_id":"A1","work_id":"W1","title":"...","alert_type":"new | version_update | retraction | correction","reason":"...","evidence_locator":"S1::records.jsonl#line12","suppressed":false,"suppress_reason":null,"delivered":true}
```

撤稿/更正不能被抑制；同一 work 同一状态只发一次。

## `evidence_table.json`

每个关键候选/提醒/统计至少有：`claim_id, claim_text, source_id, locator, quote, strength, support_scope, status`。`quote` 必须逐字来自来源；无法逐字引用时标 `UNVERIFIED`。

## `snapshot.json`

写本轮水位：

```json
{"window_end":"2024-03-01T00:00:00Z","snapshot_time":"...","seen_work_ids":[],"seen_dedup_keys":[],"counts":{}}
```

## `deltas/window_NN.json`

逐窗口保存 diff 结果，包含新增、更新、撤稿、重复、recovered_late、out_of_window 等状态。

## `/app/work/` 下的工作产物

- `agent_workplan.json`
- `manifest.json`
- `draft.json`（可选）
- `agent_review_notes.json`
- `agent_review.json`（可选）
- `script_error.txt`（异常时）

# 7. 核心方法规则

## 7.1 来源清单与候选抽取

- 每个输入来源分配稳定 `source_id`：`S1,S2,...`；保留原始文件路径、行号/段落号、来源类型。
- 候选记录抽取字段：标题、DOI、arXiv 编号、PMID、作者、期刊/会议、出版日期、版本、来源 URL（若原文有）、来源快照/导入日期、状态标签。
- 抽取不到字段时写 `null` 并登记 `missing[]`，不补造。

## 7.2 去重键与身份归一

优先使用：

1. 规范化 DOI（小写、去引号）；
2. 规范化 arXiv 编号或 PMID；
3. 规范化标题 + 第一作者姓氏 + 年份 + 期刊。

标题规范化：UTF-8 小写、删除标点、合并空白、展开常见连字符差异。

## 7.3 固定窗口与 delta 判断

时间窗默认使用 `[window_start, window_end)`，UTC 处理。若材料只有日期无时间，用当天 00:00 UTC。

delta 分类：

- `new`：当前窗口首次出现，且上一快照 seen 集合中无同一去重键；
- `unchanged`：上一快照已 seen；
- `version_update`：同一 work 身份但新版本/日期/状态（preprint→published、v1→v2、erratum、correction）；
- `retraction`：记录含 retraction notice/status；
- `correction`：记录含 correction/erratum；
- `recovered_late`：实际出版/导入日期属于更早窗口，但当前窗口才入库；
- `duplicate`：同 dedup key 多来源/多版本重复；
- `out_of_window`：不在当前窗口；
- `out_of_scope`：与订阅主题/查询明显不相关。

## 7.4 版本链合并

- 同一 work 的多个节点：preprint、journal published、revision、erratum、retraction。
- `work_id` 使用 canonical DOI 或归一身份键。
- 版本链列出所有节点，标明 `preprint_of`、`version_of`、`erratum_of`、`retraction_of`。
- 合并后主记录的元数据优先使用正式版；若正式版不存在，使用 preprint 并标记。

## 7.5 提醒合并与抑制

- 一个 merged work 只提醒一次，除非出现新的状态变化（如 retraction）。
- 抑制重复、未变化、纯镜像重复；不抑制低置信，改标 pending。
- 提醒类型：`new`、`version_update`、`retraction`、`correction`。

## 7.6 排序依据

候选排序建议：

1. 相关性强：exact query/概念匹配；
2. 窗口状态：new 优先于 version_update 与 recovered_late；
3. 元数据完整度：DOI 与作者完整优先；
4. 日期递减。

排序原因写入 `relevance_note`。

## 7.7 幂等与失败重试

- 同一输入、同一 `--now`、同一代码版本重复运行应产生相同 `dedup_key`、相同窗口归属、相同 `snapshot.json`。
- 解析失败可重试；已有输出不重复二次投递。
- 无实时网络访问；任何“接口异常/限流”只能登记 `errors[]`，不得伪装联网结果。

# 8. 与基础 Agent 对照的增益证据

加载本 Skill 后的增益证据必须来自真实产物，不写不可观测的隐藏 baseline。

在 `result.json.summary` 和 `verification.json` 中体现：

- `raw_record_count` → `candidate_count` → `new_count`：证明筛选而非全量推送；
- `duplicate_count`：证明重复压减；
- `version_update_count` / `retraction_count`：证明版本链能力；
- `recovered_late_count`：证明跨窗补回；
- `evidence_count` / `verified_count`：证明可回放证据密度；
- `agent_reviewed` 与 `auto_extract`：证明是否经过核验或确定性兜底。

所有计数必须来自脚本实际统计；不得虚构对照结果、不得写 golden_standard。

# 9. 异常与边界场景处理

- **空窗口**：`status=complete`，`new_count=0`，`alerts=[]`，但必须保留窗口说明；
- **材料坏 JSON / 不可识别**：`status=input_error`，`errors[]` 写明文件路径与原因；
- **缺 DOI/作者/日期**：能用标题+年份也要登记；完全无法建立身份进 `uncertainty[]`；
- **时区缺失**：默认 UTC，并在 `uncertainty[]` 说明；若任务有明确时区则优先采用；
- **撤稿/更正**：绝对保留 alert，且 `suppressed=false`；
- **多个 previous snapshots**：选最新/最接近窗口的作为基线；若不确定，在 `conflicts[]` 记录；
- **来源改版**：解析失败记 `degradations[]`，不中断其他来源；
- **权限限制**：仅说明无法访问，不补造。

# 10. 自检清单（必须逐项执行）

1. `case_id` 存在且与 `case.json` 一致。
2. `output_contract` 所有字段在 `result.json` 顶层存在。
3. 同一批字段在 `result.json.output_contract` nested 对象中再次存在。
4. 每个候选/提醒/关键数字有 `source_id` 和 locator；声明 DOI 必须能在原文 verbatim 找到。
5. 窗口起止、时区、水位记录清晰。
6. 去重键稳定，版本链节点完整，撤稿/更正未被抑制。
7. `candidates.csv` 行与 `result.json.candidates` 一致。
8. `alerts.json` 与 `alerts.md` 对应，且无重复提醒。
9. `query_log.json` 记录所有查询与来源。
10. `snapshot.json` 保存了本轮 watermarks，以供下一窗口 diff。
11. 所有材料缺失、解析失败、时区模糊都写入 `missing[]` / `errors[]` / `degradations[]` / `uncertainty[]`。
12. `core.py` 校验通过；失败项已修复或标记 `pending_human`。
13. `runtime.auto_extract` 与 `runtime.agent_reviewed` 真实填写。
14. exit code 为 0。

遇到任何不确定项，保留原始字段并加 `uncertainty` / `pending_human`，不要删除、不要伪造。

# 11. 方法与输出说明

- 方法细节：`references/01-methods-rules.md`
- 输出 schema 与字段约定：`references/02-output-schema.md`
- 自检清单、最小示例与常见错误：`references/03-checks-and-example.md`

运行前应阅读对应文件；如与 SKILL.md 冲突，以 SKILL.md 与题面 `output_contract` 为准。

# 12. 必须避免的扣分项

1. 把一次主题检索当增量追踪，输出没有上一快照 diff；
2. 手改结构化 JSON，破坏字段键名或脚本输出；
3. 遗漏 `output_contract` 字段，未在顶层与 nested 回显；
4. 伪造 DOI、作者、日期、引用、全文状态或隐藏 benchmark；
5. 对撤稿/更正静默抑制；
6. 异常时非 0 退出或未落 `result.json`；
7. 空窗口/无结果时返回空对象而不给状态说明；
8. 忽视 `AUTO_EXTRACT` / `agent_reviewed` 诚实标记。

# 13. 预算与收尾策略

- 先运行单命令，保证全量 sidecar 落盘；
- 用剩余模型请求核验高权重产物：窗口归属、去重、版本链、撤稿；
- 若接近预算：保存当前 partial result，补齐所有契约字段，`status=partial`，不要为完美延误落盘；
- 最终再次运行 `core.py` 校验并确认 exit 0。