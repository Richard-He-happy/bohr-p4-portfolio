---
name: search-screen-rank
description: >-
  Agent-first 文献筛选与智能排序 Skill。单命令全流程 init→build→selfcheck，
  支持 Agent draft 增量改进与无 draft 确定性兜底双路径。对已收集候选文献集真实解析、
  逐条相关性判断、分层标签、去重合并、冲突升级，产出可解释排序与完整 result.json。
  覆盖科研检索去噪、排序与人工复核辅助；不负责底层数据库接入、全文阅读或系统综述纳排。
version: 3.0.0
---

# search-screen-rank — 文献筛选与智能排序

## 0. 触发条件与最高铁律

**触发条件**：用户给定一批已收集候选文献（PDF/DOCX/JSON/CSV/图片等），需要完成相关性判断、分层筛选、去重合并、冲突处理、可解释排序和人工复核辅助时使用。

**最高铁律**：
- 完整交付优先于任何优化。脚本只是工具，最终提交物必须真实、可复核、不编造。
- 不得手改结构化结果文件（`result.json`、`candidates.csv`、`evidence.jsonl` 等）的键名与结构。Agent 判断写入 `/app/work/draft.json`，由 build 合并。
- 不确定内容必须标 `pending_human` / `uncertainty` / `limitations`；不得编造文献、摘要、DOI、年份、分数、引用。
- 任何情况下必须产出合法 `/app/output/result.json` 并退出码 0，即使状态为 partial 或 input_error。

## 1. 输入、输出与工作目录

- 只读输入：`/input/case.json`、`/input/task.md`、题面提供的全部材料文件；若存在 `/input/environment/resources.yaml` 读取预装工具与依赖。
- 工作目录：`/app/work`（写台账、draft.json、中间 JSON）。
- 最终输出：`/app/output`（写 `result.json`、`candidates.csv`、`evidence.jsonl`、`query_log.json`、`verify_report.json` 等）。
- 运行约束：Python >=3.8 标准库；无第三方包、无网络、无模型请求；离线、确定性优先。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本自身消耗 0 次模型请求。

## 2. 单命令全流程入口

**首选单命令**（必须优先尝试）：

```text
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部按顺序完成：
1. **init**：盘点 `/input` 材料，登记 `case_id`、`output_contract` 字段；来源编号；候选抽取；冲突分组；生成台账 `/app/work/inventory.json` 和候选表。
2. **build**：校验 Agent draft（若存在）；无 draft 时使用 init 台账确定性抽取生成实质工作稿；渲染全部产物；finalize `result.json`。
3. **selfcheck**：运行契约与产物自检，生成 `verify_report.json`；检查输入覆盖、ID 唯一、字段完整、排序确定性、证据逐字可核验。

**降级命令**（仅当 `run` 子命令不可用时使用）：

```text
python3 -B scripts/main.py --input /input --out /app/output
python3 -B scripts/verify.py --input /input --out /app/output
```

降级后仍需按本文件第 9 节补全 result.json 状态字段，并保证退出码 0。

## 3. Agent-first 双路径协议

### 路径 A：Agent draft 增量改进

1. 运行 `init`（或完整 `run` 到 init 阶段）获得 `/app/work/inventory.json` 和候选台账。
2. 真实阅读 `/input` 材料，不凭文件名猜测内容。批量提取 PDF/DOCX/图片文本后，逐条判断每条候选。
3. 将判断写入 `/app/work/draft.json`，每条至少包含：
   - `record_id`、`tier`、`decision`、`relevance_score`、`rank`
   - `evidence_quote`（逐字原文）、`locator`（`文件#行号/段落号` 或 `abstract`/`title`）
   - `reason`、`flags`、`pending_reason`（若 pending）、`group_ids`（若合并）
4. 调用 `check`（或 build 前校验）让脚本校验 draft 覆盖全部记录、ID 唯一、quote 可定位。
5. 调用 `build` 合并 draft 并生成 `/app/output` 全部产物。
6. 调用 `selfcheck`；根据报告局部修正，但修正只能通过更新 draft.json 后重跑 build，或通过允许的脚本函数覆盖。

### 路径 B：无 draft 确定性兜底

- 当 `/app/work/draft.json` 不存在或未覆盖全部候选时，`build` 使用 init 台账进行确定性抽取，生成实质工作稿。
- 兜底输出逐字 quote + locator；将 `AUTO_EXTRACT` 诚实记入 `gaps` 和 `degradations`。
- 兜底路径证据置信度标为 `auto` 或 `medium_low`；冲突项进入 `pending_human`；不得伪装成 Agent 已逐条核验。
- 两条路径产出**同一套产物与同一份 result.json 契约**，字段、结构、文件完全一致。

**禁止手改结构化产物**。若发现脚本错误，可写临时 Python 调用脚本函数重算并覆盖，但必须将修改记录到 `changes` 和 `agent_review`。不要用文本编辑器直接改 JSON 结构。

## 4. 详细执行步骤

### Step 0 — 读任务与契约

- `ls -R /input` 列出全部文件。
- 读取 `/input/task.md`，明确评分维度、Runtime contract、输出要求。
- 读取 `/input/case.json`（若存在），提取 `case_id`、`output_contract`、任务说明、科研问题、范围约束、候选材料路径。
- 将 `output_contract` 全部字段记录到 `/app/work/contract_fields.txt`；未知字段也要保留清单。
- 若 `case.json` 缺失或坏 JSON：继续读 `task.md` 并扫描材料，不得停止运行。
- 若 `output_contract` 缺失：按 Runtime contract 标准字段生成，并在 `contract_missing` 说明。

### Step 1 — 运行单命令全流程

- 执行 `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`。
- 立即获得完整基线：`result.json`、`candidates.csv`、`query_log.json`、`evidence.jsonl` 等。
- 若脚本异常：捕获错误写 `/app/work/baseline_error.txt`；仍必须手工构造最小合法 `result.json`（空 candidates、status=input_error、errors 记录）。
- 启动即写 partial；后续增量增强不能删除基线文件，除非有可核验证据并保存 `changes`。

### Step 2 — 真实解析材料

- 逐条读取候选记录：题名、摘要、作者、年份、出处、DOI、URL、来源数据库、query_id、retrieved_at、已有标注。
- 每条保存 `provenance.file` 与定位信息。
- 对 PDF：使用环境提供的 PDF 文本提取工具提取全文文本，再定位候选记录。不得因文件名或领域标签推断摘要、结论、数据。
- 单文件解析失败只跳过该文件，写 `degradations[stage=parse]`；不得补造内容。
- 材料为空：输出空 `candidates`，不补造文献。

### Step 3 — 生成 draft.json 与证据

- 根据 `references/label_taxonomy.md` 分档规则，为每条候选打 `tier`：
  - `core`：直接相关，回答研究问题或提供核心证据
  - `method`：方法参考或设计匹配但非直接证据
  - `background`：背景资料或间接相关
  - `pending`：信息不足、冲突、无法判断
  - `exclude`：明确不相关
- 条件匹配优先级：**研究对象、人群、研究设计、时间范围实质匹配 > 标题关键词**。
- 证据充分性：摘要缺失或证据不足必须标 `pending`，不得强行高置信排序。
- 每条排序理由必须写明：命中哪条纳排条件、依据摘要哪段证据、置信度。
- 证据 quote 必须逐字来自该记录摘要或题名；locator 写 `abstract` 或 `title`，或 `文件#行号/段落号`。
- 版本合并：DOI 归一化一致或归一化题名一致合并；预印本优先升级正式版本；同一研究多篇报道保留全部成员并链到 `group_ids`。
- 冲突处理：标注分歧、版本不决、意见冲突送 `conflicts` 和 `pending_human`，附双方依据，不擅自删除。

### Step 4 — build 合并与产物渲染

- `build` 校验 draft.json 覆盖全部候选；缺失项由确定性兜底补充。
- 生成或更新：
  - `/app/output/result.json`
  - `/app/output/candidates.csv`
  - `/app/output/evidence.jsonl`
  - `/app/output/query_log.json`
  - 若需交付规则文档，生成 `/app/output/rules.md`（从 `references/label_taxonomy.md` 导出）
- `candidates.csv` 一候选一行，字段：rank、id、tier、decision、relevance_score、score、题录、DOI/URL、source_db、query_id、retrieved_at、design_fit、reason、flags、evidence_quote、group_ids。
- `evidence.jsonl` 每条至少：原始 record_id、规则 ID、证据原文、来源位置、理由、不确定性、版本合并后的原 ID 映射。
- 契约字段对应文件必须覆盖全部字段；缺失字段写 `null`/`[]`，不得省略键。

### Step 5 — selfcheck 与修复

- 运行 `python3 -B scripts/verify.py --input /input --out /app/output`（或 run 内嵌 selfcheck）。
- 检查 `verify_report.json` 中：
  - `contract_missing`：输出契约字段是否缺失
  - `evidence_verbatim`：quote 是否逐字可核验
  - 输入覆盖：是否每条输入记录都有输出条目
  - ID 唯一性
  - 排序确定性
- 只针对报告失败项修复；修复后重跑 build 和 selfcheck。
- 不要为了凑数创建 `output_contract` 不要求的文件。

### Step 6 — 最终回填与退出

- 回填 `result.json`：
  - `status`：`ok | partial | insufficient_evidence | input_error`
  - `sources`：来源数组，每个来源有 `[S#]` 编号
  - `uncertainty`、`pending_human`、`errors`、`degradations`
  - `runtime`：实际耗时、请求消耗
  - `changes`：每条修改含 `stage`、`reason`、`detail`
  - `method`：打分公式、分档规则、平局键、版本
  - `reviewed_by_agent`：`verified | corrected | pending_human`
- 确保 `/app/output/result.json` 合法，退出码 0。
- 任何失败都保留已落盘 partial，退出码仍为 0。

## 5. 证据规则与标签体系

- 使用 `references/label_taxonomy.md` 定义标签边界；`references/io_contract.md` 定义字段形状。
- **逐字 quote**：每条关键判断必须有证据 quote；不能用自己的话替代原文；quote 不匹配时标 `pending_human`。
- **来源编号**：所有数字、论断引用使用 `[S#]`，对应 `result.json.sources[]` 中的来源项；locator 需到文件+行号/段落号。
- **材料缺失**：摘要、年份、DOI 等缺失时：
  - 缺摘要 → 标 `pending`
  - 缺年份 → 不参与年份排除，只用其他键排序
  - 缺 DOI → 不推断、不合并，标 `flags`
- **不凭领域标签推测论文内容**：必须读实际摘要/题名，不能由学科标签推断相关性或结论。

## 6. 排序、平局与冲突处理

- **主排序键**：
  1. `tier_priority`：core=0, method=1, background=2, pending=3, exclude=4
  2. `relevance_score` 降序
  3. `year` 降序
  4. `normalized_title` 升序
  5. `record_id` 升序
- **平局处理**：同排序键记录 `tie_group`，复用上述键兜底。不得随机顺序。
- **k 值**：默认 k=10，也可按 `output_contract` 指定；前 k 需包含全部 core，然后 method；若 k 小于 core 数，按 relevance_score 截断并在 `limitations` 说明。
- **重复与版本合并**：DOI 归一化（小写、去空白）一致或归一化题名一致合并；预印本优先升级正式版本；合并后保留全部原始 member IDs 在 `group_ids`。
- **冲突**：标注分歧、版本不决、多篇报道冲突 → 送入 `conflicts` 队列，每条含双方证据；升级 `pending_human`。不与排除项合并。

## 7. result.json 契约与双回显

`result.json` 必须同时包含：

- **顶层字段**：
  - `case_id`
  - `status`
  - `sources`
  - `uncertainty`
  - `pending_human`
  - `errors`
  - `degradations`
  - `runtime`
  - `changes`
  - `method`
  - `reviewed_by_agent`
  - `contract_echo`
  - `contract_fields`
  - `contract_fill`
  - `contract_missing`
  - `candidates`
  - `tiers`
  - `screening`
  - `metrics`
  - `conflicts`
- **nested output_contract**：将 `/input/case.json` 中的原 `output_contract` 全部字段原样放置，含 `case_id`；与顶层字段一一对应。
- **双回显要求**：契约字段（含 `case_id`）在顶层与 `output_contract` 嵌套中各出现一次；未知字段透传，缺值写 `null`/`[]`。
- `status` 允许值：`ok | partial | insufficient_evidence | input_error`。
- 不擅自覆盖输出契约；若平台另有字段要求，保留并填充。

## 8. 异常、降级与鲁棒性

| 情况 | 处理 | 落点 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续读 `task.md` 并扫描材料；无记录则空候选 | `errors[stage=read_case]`，`status=input_error` 或 `insufficient_evidence` |
| `output_contract` 缺失 | 按 Runtime contract 标准字段生成；记录缺失 | `contract_missing` |
| 候选集为空 | 输出空 `candidates`，不补造文献 | `uncertainty`，`errors` |
| PDF 无文本层/提取失败 | 不按文件名编造；相关记录标 `pending` | `degradations[stage=parse]`，`pending_human` |
| 单个文件解析失败 | 跳过该文件，记录不支持 | `degradations` |
| 摘要/年份/DOI 缺失 | 缺摘要→pending；缺年份不参与年份排除；缺 DOI 打标 | `flags`，`uncertainty` |
| 查询 429/权限/接口异常 | 保留原始 status/error，不替换为成功 | `queries[].status/error` |
| 大量同分 | 记录 `tie_group`，用排序键兜底 | `tie_group` |
| 超大输入或中断 | 已处理部分保留 partial | `errors[stage=run]`，`changes` |
| 时间/预算耗尽 | 停止增强，写 `status=partial`，列出缺失项，退出 0 | `degradations` |
| 内部异常 | 捕获并写 `errors`，保留 partial，退出 0 | `errors[stage=run]` |

**任何情况下**：
- 必须产出 `/app/output/result.json`。
- `result.json` 合法 JSON，退出码 0。
- 不确定内容显式标注 `pending_human` / `uncertainty` / `limitations`。
- 不补造文献、摘要、DOI、年份、引用、分数。

## 9. 预算意识与快速收尾

执行预算：64 次模型请求 / 900 秒。建议请求分配：

| 阶段 | 模型请求 | 说明 |
|---|---|---|
| 读 task/case/契约 | ≤4 | 先读关键字段，避免重复 |
| init/基线 | ≤2 | 单命令产出基线 |
| 解析材料 | ≤12 | 批量读取；大文件用脚本抽取片段 |
| draft 判断/evidence | ≤15 | 优先 core/method 文献，再边缘项 |
| build/selfcheck | ≤10 | 只针对报告失败项修复 |
| 修正与提升 | ≤8 | 关键错误优先 |
| 异常储备 | ≤13 | 解析失败、契约缺失等 |

**执行原则**：
1. 第 1 步必须先跑 `run` 单命令，约 30 秒内获得完整基线。
2. 时间 <120 秒或模型请求 ≥55 次：停止新增强，只做“补字段 + 写 changes + 保证合法 JSON”。
3. 不要在单次响应中读取超大材料；用脚本或分段读取。
4. 脚本产生的兜底结果是安全网；不要为了“更聪明”删掉它。
5. 若只能部分完成，先落盘 honest partial，再增量改进。

## 10. Rubric 自检清单

**实际效果（40 分）**
- 覆盖全部输入记录，逐条交付标签、名次、元数据、缺失项。
- `tier` 与 `label_taxonomy` 一致；证据 quote 逐字可核验。
- 重复与版本变体已处理；`group_ids` 保留全部成员。
- 排序键、k 值、平局处理可复核。

**使用增益（25 分）**
- 若有平台标注及对照：运行 `evaluate.py`（若存在）或等价脚本计算标签一致性、P@k、快照内召回及差值；无数据输出不可计算，不得虚构。
- 输出待定数量、需核查字段及证据位置；耗时真实记录，人工复核时间未测则留空。
- 保留基线产物与核验报告；不发明 benchmark 分数。

**创新增益（15 分）**
- 实现“条件匹配→证据充分性→分层排序”；冲突送入可定位复核队列。
- 规则可配置；如存在消融开关或比较脚本，用实际结果验证贡献；无运行证据不宣称提升。

**可靠体验（10 分）**
- 单入口调用可用；校验脚本检查输入覆盖、ID 唯一、字段完整、排序确定性。
- 先保存诚实部分结果，再增量完善；异常输出已完成、未完成、原因及恢复办法。

**生态贡献（10 分）**
- README 交付安装、调用、版本、限制、维护及资源来源；示例明确标为示意。
- 复用 `references/label_taxonomy.md` 标签指南、`scripts/main.py` 脚本、`scripts/verify.py` 校验脚本。
- 根目录放 `GITHUB_URL.txt`，验证公开链接无需登录可见。

## 11. 文件与路径

- 包内现有资源：
  - `references/example_walkthrough.md`：draft/工作流示例
  - `references/io_contract.md`：契约字段与 draft.json 形状
  - `references/label_taxonomy.md`：标签边界与纳排规则
  - `scripts/main.py`：init/build/selfcheck 或基线生成
  - `scripts/verify.py`：独立结构校验
- 输出文件：
  - `result.json`
  - `candidates.csv`
  - `evidence.jsonl`
  - `query_log.json`
  - `verify_report.json`
  - `rules.md`（按需从标签指南导出）
- 提交目录必须包含 SKILL.md、README.md、rules.md、schema.json、run.py、evaluate.py、validate.py、examples/demo.json、GITHUB_URL.txt（若题目要求）。如某资源缺失，运行时根据 `references/label_taxonomy.md` 生成 `rules.md`，根据 `scripts/verify.py` 生成校验报告，不因此阻断主流程。
- 脚本只使用 Python 标准库；加载 `/input/environment/resources.yaml`（若存在）获取预装工具说明；不依赖个人路径或未说明文件。