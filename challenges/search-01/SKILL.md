---
name: traceable-literature-retrieval
description: 离线可追溯学术文献检索与筛选 Skill。读取 /input 中科研案例与真实材料（Crossref、Europe PMC、publisher dumps、JSONL/JSON、引用图、seed 列表、PDF/DOCX/CSV/图片等），执行多轮查询规划、同义词/缩写扩展、多库合并去重、IDF 加权排序、筛选与引文追踪，并回填完整 output_contract 到 result.json。脚本提供确定性基线与兜底；Agent 负责阅读、核验、补全文本交付物；空结果、缺失、冲突、失败诚实写入，不编造。
version: 2.0.0
---

# 可追溯学术文献检索 Skill（traceable-literature-retrieval）

## 0. 最高优先级：真实、可追溯、契约完整

本 Skill 不是让你写一段“像检索结果”的文字，而是要你在 `/input` 的真实材料中完成检索、筛选、排序、去重、引文追踪和证据记录。每个交付物都必须能被第三方独立复核。

核心规则：

1. 只使用 `/input` 中实际存在的材料。禁止联网检索；禁止声称获得未在 `/input` 中出现的外部服务响应；禁止编造标题、作者、年份、期刊、DOI、引用关系、IDF 分数、召回率或“关键文献命中”。
2. 脚本是基线和兜底工具，不是成品。必须先运行脚本生成结构化基线和候选台账，再由 Agent 实际阅读材料、核验关键引用、撰写相关性依据和缺口说明。
3. 每个关键数字、每条候选、每个筛选/排序依据都要带 `[S#]` 来源编号和 `文件#行号` 或 `文件#段落号` locator，并有逐字 quote 或可定位 evidence_snippet。
4. 无法核验的信息不得进入正式结果；缺失、冲突、空结果、权限问题必须显式写入 `uncertainty` / `pending_human` / `errors` / `degradations`。
5. 任何情况下都必须生成合法 `result.json`，并退出码为 0。部分完成也是有效交付，但要诚实标注 `status: "partial"` 或 `"failed"`，不得伪装成功。

## 1. 输入、输出与运行契约

| 项 | 要求 |
|---|---|
| Skill 根目录 | `/skills/weekly-skill` |
| 输入目录 | `/input`，只读。包含 `case.json`、`task.md` 及材料文件 |
| 材料类型 | 可能是 JSON/JSONL/CSV/TSV/PDF/DOCX/图片、Crossref/Europe PMC/publisher dump、引用边、seed 列表等。不得依赖固定文件名，按内容探测 |
| 工作目录 | `/app/work`，可写。存放 init 台账、临时提取、draft、校验记录 |
| 输出目录 | `/app/output`，可写。最终结果和可编辑产物必须放这里 |
| 网络 | 严格离线。不发起任何联网检索 |
| 退出码 | 恒为 0。任何异常都写 errors/degradations，仍生成合法 result.json |
| 资源限制 | Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink |
| 执行预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |

## 2. 单命令全流程入口

进入任务后，优先使用唯一入口：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部应完成：

1. `init`：盘点 `/input` 中所有材料，生成 source inventory、来源编号、候选抽取、冲突分组。
2. `build`：校验/兜底抽取、渲染全部产物、生成 `result.json`。
3. `selfcheck`：核对产物与 output_contract、result.json 字段、来源引用一致性。

如果 `run` 不支持这些参数，先查看 `python3 scripts/main.py --help`，再使用等价子命令。无论子命令如何变化，必须完整覆盖 `init -> build -> selfcheck`，不得绕过脚本只写文本。若脚本运行失败，把失败原因写入 errors，继续进行可用的手工/脚本混合兜底，并保证最终 result.json 合法。

## 3. Agent-first 双路径

本 Skill 采用双路径，保证预算受限时仍可获得完整交付物。

### 路径 A：Agent 路径

1. 运行一次脚本 init 或 run，得到台账和基线产物。
2. Agent 阅读 `/app/work` 中 ledger 文件：inventory、candidate ledger、query ledger、gap ledger 等。实际名称以 `/app/work` 目录中的文件为准，不要假设固定文件名。
3. Agent 阅读 `/input/case.json`、`/input/task.md` 和实际材料文件，核对基线提取的 quote、locator、元数据是否与原文一致。
4. Agent 把判断写入 `/app/work/draft.json`，并同时写入 `/app/work/agent_review.json`。`draft.json` 用于 build 阶段；`agent_review.json` 记录逐条核验结果、修改原因和脚本修复说明。
5. 再运行 `python3 scripts/main.py build --input /input --output /app/output --work /app/work --draft /app/work/draft.json`，或等价的 `run --draft /app/work/draft.json ...`。

### 路径 B：确定性兜底

如果没有 `draft.json` 或 Agent 没有写 draft，`build` 必须用 init 台账中的来源编号、`候选抽取`、`冲突分组`、`query_plan` 等确定性信息生成实质工作稿。兜底抽取必须保留：

- 逐字 quote
- locator：`文件#行号` 或 `文件#段落号`
- source_id
- 初步相关性理由，明确标记为 `AUTO_EXTRACT`
- 将 `AUTO_EXTRACT` 诚实地写入 result.json 的 `degradations` 或 `gaps`

两条路径最终必须生成同一套产物和同一份 result.json 契约结构。Agent 路径是质量增强，兜底路径是完整性保障。

## 4. 检索方法论要求

每个案例都必须完成以下步骤，不能省略：

1. 明确研究问题和检索范围：从 `case.json` 和 `task.md` 提取研究问题、约束、期望证据范围。
2. 查询规划：把复杂科研问题拆成多个查询步骤，每个步骤写出检索意图和预期命中。
3. 关键词扩展：使用 `references/terms.md` 中的术语、同义词、缩写、跨语言表达、相关概念扩展查询词。控制无关结果，避免关键词爆炸。
4. 多源合并：从 `/input` 所有相关材料中收集候选记录。不同来源可能重复，必须按规范化标题或 DOI 去重。
5. 去重与来源记录：优先使用 DOI 作为强去重键；无 DOI 时使用规范化标题 + 第一作者 + 年份。保留来源优先级和冲突说明。
6. 引文追踪：如果材料中存在 reference graph / citing-cited edges / retained reference graph，应把引用边、被引边纳入候选扩展，并标注引用路径。
7. 排序与筛选：按研究问题相关性、题面约束、来源可靠性、元数据完整性排序。不要只按年份或数据库返回顺序。排序依据要写进 query_log 或 evidence。
8. 证据记录：每个候选必须至少有一条 evidence，包含 source_id、locator、quote、relevance_reason。评审人员必须能独立复核。

## 5. 产物清单与 result.json 契约

### 必须产物

- `/app/output/result.json`
- `/app/output/candidates.csv`
- `/app/output/candidates.json`
- `/app/output/query_log.json`
- `/app/output/evidence_table.json` 或等价证据文件
- `/app/output/deliverable.md`：干净的人类可读交付报告
- `/app/output/agent_review.json`：Agent 核验记录
- `/app/output/pending_human.json`：需要人工判断的事项

如果 `output_contract` 要求其他文件，如：

- 检索报告
- 筛选过程
- 遗漏说明
- 方法说明
- 可编辑 Office/幻灯片/图

必须按 contract 字段生成对应文件。Office/slide/diagram 等可编辑产物若属于 contract，还需要真实渲染的 PDF/PNG 预览。

### result.json 双回显

`result.json` 必须同时包含：

1. 顶层契约字段：所有 `output_contract` 字段原样出现在 result.json 顶层。
2. 嵌套契约：同一批字段也要出现在 `result.json.output_contract` 对象中。
3. `case_id` 必须在顶层和 nested output_contract 中都出现。
4. 顶层还应有：
   - `status`: `success` / `partial` / `failed`
   - `sources`: 使用到的材料来源列表
   - `uncertainty`: 不确定性说明
   - `pending_human`: 需要人工复核的项目
   - `errors`: 运行错误
   - `degradations`: 质量降级、AUTO_EXTRACT、缺失元数据、未完成部分
   - `created_at` / `schema_version` / `change_log`

不得重命名 `output_contract` 原有字段，不得遗漏字段。如果某个 contract 字段无法完成，也要把该字段写为 null 或空集合，并在 `errors` / `degradations` 中说明原因。

## 6. 异常处理与诚实状态

处理以下情况：

- 空结果：candidates 为空，status 可为 `success` 或 `partial`，但必须写清“结果为空”和原因。
- 元数据缺失：缺失字段不编造，在候选记录中写 `null`，并在 pending_human 中记录。
- 来源冲突：同一文献多个来源元数据不一致时，保留所有来源并标注 `conflict`，不要隐式选择一个假装无冲突。
- 权限不足：如果文件不可读，写 errors。
- 文件损坏：记录文件来源和错误，不从损坏处推断内容。
- 预算不足：先保存合法 partial result.json，再继续改进；如果接近 64 次 / 900 秒，立即收尾，不要追求过度优化。

## 7. 增益证据

为体现相对于基础 Agent 的增益，产物中必须包含：

1. `query_log.json`：完整查询计划、关键词扩展、查询组合、来源检索、去重、筛选记录。
2. `evidence_table.json`：每条候选的证据链，使评审能直接复核。
3. `gaps`：诚实列出基础检索可能遗漏，但本 Skill 通过 query planning / citation tracing / dedup 覆盖或显式标记为未覆盖的内容。
4. `agent_review.json`：说明 Agent 在基线之上实际核实和修正了什么，例如修正元数据、补充 relevance_reason、删除不可靠候选、发现冲突。
5. `deliverable.md`：叙述检索过程、结果亮点、限制、依据，不写空泛“完成”。

增益必须是实际产物证据，不能只写“比基础 Agent 更优”。

## 8. 完成前自检清单

结束前逐项检查：

1. 已运行 `python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work`。
2. `result.json` 是合法 JSON。
3. `result.json` 顶层与 `output_contract` 嵌套字段一一对应，`case_id` 存在。
4. 所有 contract 字段都有对应文件或 JSON 值，没有遗漏。
5. 每条候选在 `candidates.csv/json` 与 `evidence_table.json` 中一致，有 source_id 和 locator。
6. 所有 quote 与原始材料逐字一致，或标记为 paraphrase 及原因。
7. 空结果、冲突、缺失元数据、失败均写入诚实状态。
8. `/app/output` 下没有未说明的临时文件或不属于 contract 的形式化测试输出。
9. 没有将脚本生成的金标准、自评分、伪造 benchmark 作为证据。
10. 若 `deliverable.md` 与 evidence draft 同时存在，内容不能是同一份文本复制。

## 9. 最小调用示例

输入 `/input/case.json` 可能包含：

`case_id`, `task`, `research_question`, `constraints`, `output_contract`

调用：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

示意输出只作为接口说明，不代表正式案例结果：

`/app/output/result.json`

包含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations` 和完整的 `output_contract` 字段。

`/app/output/candidates.csv` 每行一个候选文献，列包括 `source_id`、`title`、`authors`、`year`、`journal`、`doi`、`rank`、`relevance_reason`、`locator`。

`/app/output/deliverable.md` 为可读报告，标注示例。

## 10. 文档与复用

Agent 可使用本包内资源：

- `references/checklist.md`：运行前/结束前核对清单。
- `references/schema.md`：结构化字段、候选记录、evidence、draft.json 形状说明。
- `references/terms.md`：中英文术语、同义词、缩写扩展表。
- `scripts/main.py`：主入口。
- `scripts/engine.py`：抽取、归一化、去重、排序、引文追踪等核心函数。

如脚本产生额外说明文件，以脚本实际输出为准，但不得删除或无视以上资源。

最终目标：让评审人员仅凭 `/app/output` 与 `/input` 材料，即可独立重复你的检索逻辑，并确认每条候选、每个排序决策都真实可溯源。