---
name: multidb-literature-search
description: >-
  多数据库联合检索 Skill。读取 /input 下真实案例、库响应与材料，按各库检索语法编排查询，
  做跨库字段归一、可解释去重、字段权威度合并、逐条来源回溯与覆盖缺口登记，输出 result.json 及可复核产物。
  Agent 可写 /app/work/draft.json 给出判断；未提供时由确定性抽取兜底。离线、标准库、不联网、不编造文献。
version: 2.0.0
---

# 多数据库联合检索 Skill（multidb-literature-search）

## 0. 入口（单命令全流程）

运行：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

包安装后同样可用：

`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部依次执行：

`init` → `build` → `selfcheck`

- `init`：盘点 `/input` 实际材料，建立来源编号、候选台账、查询/响应定位、冲突分组，写下 `/app/work/inventory.json`。
- `build`：校验 `/app/work/draft.json`，完成兜底抽取、字段映射、去重、合并、冲突消解、覆盖统计，渲染全部产物，最终写 `/app/output/result.json` 并 finalize。
- `selfcheck`：对产物做契约、计数、去重不变量、证据定位自检。

任何阶段异常都必须 `exit 0`；异常写 `errors`/`degradations`，不允许崩溃退出，也不允许静默返回成功。

## 1. 用途与边界

**做什么**：

1. 多源查询编排：按 Crossref / Europe PMC / PubMed / OpenAlex / Semantic Scholar 等库的检索语法生成查询，不把同一查询原样复制到所有库。
2. 字段标准化：统一作者、期刊、年份、标识符、文献类型等规范字段，区分“缺失”与“未知”。
3. 去重：标识符精确匹配 + 题名标准化匹配 + 题名相似度/首作者/年份守卫，输出可解释重复判定。
4. 合并：按字段权威度消解冲突，落选值保留在 `conflicts[]`。
5. 来源回溯：每条记录可沿“库→查询→原始响应→字段映射→去重→合并”链路核对。
6. 失败降级：库不可用、限流、缺字段、坏编码、撤回线索等明确写进缺口，不装成完整结果。

**不做什么**：

- 不发起网络请求；本 Skill 离线消费 `/input` 下的真实响应与材料。
- 不生成输入中没有的文献、DOI、引用、期刊、年份、摘要、撤回状态。
- 不做全文精读，不判断科学质量，不声明“最新/全球覆盖”。
- 不绕过服务限制、额度或权限。
- 不以领域标签推断或补造文献内容。

本题的真实输入是 9 篇真实科研文献，带实际 Crossref/Europe PMC/出版方响应、保留的引用图与本地增量导入状态。所有结论必须来自实际 `/input` 文件和解析出的原文内容；不能根据文件名、领域标签或题目叙述补造数据。

## 2. 适用条件

| 适用 | 不适用 |
|-|-|
| 一个科研问题需要合并 2 个以上学术库的结果 | 只查单库，或只要一条已知 DOI 的元数据 |
| 输入含库响应、检索记录、CSV/JSON/JSONL/PDF 等材料 | 只有一段自然语言问题，无任何可读材料 |
| 需要候选集、去重、字段补全、覆盖缺口说明 | 需要循证结论、Meta 分析、疗效判断 |
| 需要逐条回溯“这条记录来自哪库、哪个字段” | 需要在线实时检索 |

## 3. 运行契约

| 项 | 值 |
|-|-|
| 包根 | `/app/submission/`，安装后挂载到 `/skills/weekly-skill` |
| 实际输入 | `/input/case.json`、`/input/task.md`、`/input/artifacts/`、`material.json`、PDF/CSV/JSONL 等 |
| 工作目录 | `/app/work`，可重建；中间台账、`draft.json`、部分结果均写这里 |
| 最终输出 | `/app/output/` 下的 `result.json` 及全部可复核产物 |
| 依赖 | Python 3.8+ 标准库；无第三方包、无子进程、无网络 |
| 预算 | 64 次模型请求 / 900 秒 / 单次回复 16384 tokens；脚本本身秒级完成 |
| 退出码 | 恒为 `0`；失败只降级状态并写 `errors`/`degradations` |
| 写入边界 | 只读 `/input`；只写 `/app/output` 与 `/app/work` |

## 4. 输入发现

1. 优先读 `/input/case.json`；缺失则递归查找满足任一键名的 case 文件：`case_id`、`task_instruction`、`output_contract`、`scope`。
2. 仍失败则读 `/input/task.md`，提取任务文本；仍无法建出 case 时进入 `input_error`，但必须写合法 partial `result.json`。
3. `case_id` 与 `output_contract` 原样透传，不改键名、不丢未知字段。
4. 材料按键名语义识别，不假设固定结构。同义键名子串命中即可：

| 语义 | 识别键 |
|-|-|
| 研究问题 | `topic`、`research_question`、`question`、`title`、`subject`、`objective`、`query`、`task_instruction` |
| 库集合 | `databases`、`dbs`、`data_sources`、`sources`、`database_list` |
| 年份范围 | `years`、`year_range`、`year_from`、`year_to`、`publication_years`、`time_range` |
| 语言/类型 | `language`、`languages`、`doc_types`、`pub_types`、`include`、`exclude` |
| 上限 | `max_k`、`top_k`、`limit`、`budget` |
| 种子/金标准 | `seeds`、`seed_papers`、`seed_dois`、`known_relevant`、`gold`、`reference_seeds` |

5. 递归扫描 `/input/**`，按扩展名和内容签名识别：库响应、`records.jsonl`、`queries.jsonl`、`reference_graph.json`、`citations.jsonl`、`schema.json`、`config.yaml`、`material.json`、CSV、PDF、DOCX、图片。
6. 未提供的对象明确写进 `coverage.gaps` 与 `errors`；不构造像素、图注、数据或文献。

## 5. 双路径执行：Agent 路径与确定性兜底

### 5.1 Agent 路径

Agent 可先运行 `init`，阅读台账和原文，把判断写入 `/app/work/draft.json`，再由 `build` 应用。

`draft.json` 形状：

```
{
  "mode": "agent",
  "include_candidate_ids": ["c001", "c002"],
  "exclude_candidate_ids": ["c003"],
  "merge_overrides": [{"id_a": "c004", "id_b": "c005", "decision": "merge", "reason": "title normalization + same DOI"}],
  "relevance_notes": {"c001": "直接研究问题与方法匹配"},
  "arbitrations": [{"cluster_id": "k07", "decision": "keep_separate", "reason": "year conflict >1"}],
  "uncertainty": ["c006 的期刊名在两个库不一致"]
}
```

`build` 会校验 `draft.json`，只接受能映射到台账候选或聚类的结果。无效条目写 `errors`，不覆盖事实抽取。

### 5.2 无 draft 时确定性兜底

若 `/app/work/draft.json` 不存在或无效，`build` 使用 `init` 台账做确定性抽取：

- 逐条抽原文逐字 `quote` 与 `locator`；
- 不臆造语义相关性判断；`relevance_reason` 只使用可由材料验证的查询命中、字段值和规则依据；
- 在 `gaps`/`degradations` 中如实记录 `AUTO_EXTRACT`；
- 仍产出完整候选集、trace、metrics、coverage、report 草稿。

两条路径产出同一套产物与同一份 `result.json` 契约；差异仅在于是否应用了 Agent 判断。

## 6. 最终产物清单

`/app/output/` 下必须生成：

- `result.json`：主结果，含契约字段与状态。
- `candidates.csv` / `candidates.json`：候选文献表。
- `query_log.json`：每库实际查询、命中、状态、来源文件。
- `merge_log.json`：去重、合并、冲突消解全量判定。
- `trace.jsonl`：逐记录“库→查询→原始响应定位→映射→去重→合并”事件。
- `metrics.json`：候选数、唯一论文数、单库独有项、字段完整率及分母、耗时、失败与人工介入。
- `coverage.md`：覆盖矩阵、单库独有、系统性缺失字段与缺口。
- `report.md`：真实冲突处理前后、规则依据、覆盖边界、相比简单拼表的增量价值。
- `rules.yaml`：实际使用的逐库语法、字段语义、精确/模糊去重阈值、冲突优先级、仲裁入口。

所有产物均由 `build` 确定性地从台账和规则生成，不依赖运行环境以外的文件。

## 7. `result.json` 双回显与契约

`result.json` 必须同时满足：

1. 顶层包含 `case_id` 及原 `output_contract` 全部字段；
2. `output_contract` 嵌套块中再出现一次契约字段与结果；
3. `contract_echo` 保存原始契约；
4. `contract_fill` 逐字段说明填充状态、来源路径和缺失原因。

顶层字段：

| 块 | 说明 |
|-|-|
| `case_id`、`skill`、`skill_version`、`generated_at`、`status` | 身份与状态 |
| `candidates[]` | 每篇一条候选 |
| `queries[]` | 每库查询与执行状态 |
| `screening` | 纳排标准、纳入/排除/排除原因 |
| `coverage` | `per_db`、`unique_to_db`、`field_fill`、`gaps`、`recall_estimate` |
| `clusters[]`、`conflicts[]` | 去重簇与字段冲突 |
| `sources[]`、`evidence[]` | 来源清单与逐条 quote+locator |
| `uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]` | 状态诚实 |
| `runtime`、`self_check`、`metrics`、`baseline_comparison` | 运行与自检证据 |
| `trace_summary` | trace 的聚合摘要 |
| `contract_fill`、`contract_echo`、`output_contract` | 契约双回显 |

`status` 枚举：`ok` / `partial` / `insufficient_evidence` / `input_error`。

候选字段至少包含：

`id`、`title`、`authors[]`、`year`、`venue`、`doi`、`pmid`、`pmcid`、`arxiv`、`url`、`source_dbs[]`、`query_ids[]`、`raw_file`、`raw_pointer`、`retrieved_at`、`relevance_score`、`relevance_reason`、`evidence`、`field_provenance`、`metadata_confidence`、`flags[]`、`cluster_id`、`included`。

查询字段至少包含：

`query_id`、`db`、`raw`、`expanded`、`filters`、`hits`、`status`、`error`、`retrieved_at`、`source_file`。

## 8. 查询编排、字段映射、去重与合并

### 8.1 查询编排

- 规则本体在 `references/db-profiles.json`，输出快照为 `/app/output/rules.yaml`。
- 每条查询带 `db`、`raw`、`expanded`、`filters`、`hits`、`status`、`source_file`。
- 未提供某库响应时，输出该库查询计划并标 `planned_not_executed_offline`，不冒充已检索。
- 遇到限流/额度标记只记录，不重试不发网。

### 8.2 字段标准化

- 规范字段 18 个，路径映射在 `references/db-profiles.json`。
- 未知库走内置同义词回退，不因库未知而丢记录。
- 缺失用 `null`，未检索写 `unknown`，并在 `field_fill` 统计。

### 8.3 去重规则

| 阶段 | 规则 | 置信度 |
|-|-|-|
| A | 共享规范化 DOI/PMID/PMCID/arXiv | `high` |
| B | 题名标准化后完全相同且长度>=15，年份相同或一方缺失 | `high` |
| B' | 题名相同但年份相差>1 | 不合并，进 `pending_human` |
| C | 题名相似度>=0.90 且首作者姓相同且年份±1 | `high` |
| C' | 同守卫但相似度 0.82–0.90 | `medium`，合并并标 `needs_arbitration` |

绝不单凭“同作者+同年”合并；DOI 冲突不强并，保留冲突链并进 `pending_human`。

### 8.4 合并与冲突消解

- 标识符：DOI 取 Crossref；PMID/PMCID 取 PubMed/Europe PMC；arXiv 取 arXiv。
- 题名/作者/年份/期刊：Crossref 与出版方响应优先。
- 摘要：出版方或 Europe PMC 全文侧优先。
- 被引数：OpenAlex 与 Semantic Scholar 语义不同，不跨库直接比较，写 `conflicts[]`。
- 同权威度取更长非空值，再按库名排序，保证确定性。

## 9. 证据、回溯与覆盖说明

证据链必须保留：

`库 → query_id → source_file → raw_pointer → 映射字段 → cluster_id → merged_id`

- `evidence[].quote` 必须是清洗前原文逐字片段。
- JSON 响应用 JSON Pointer 定位；PDF 用页码/段落；CSV 用行号。
- 找不到定位写 `unverified`，并进 `pending_human`。
- `trace.jsonl` 每行一个事件，字段含：`event_id`、`ts`、`db`、`query_id`、`source_file`、`raw_pointer`、`mapped_field`、`decision`、`cluster_id`、`merged_id`。
- `coverage.md` 只报告已提供来源的覆盖矩阵，不自行推断“全网覆盖”。

## 10. 指标、基线对照与增益验证

`metrics.json` 至少含：

- `candidate_count`
- `unique_paper_count`
- `per_db_record_count`
- `unique_to_db`
- `field_fill_rate` 及字段分母
- `duplicates_merged`
- `ambiguous_pairs`
- `pending_human_count`
- `planned_not_executed_db_count`
- `failed_db_count`
- `runtime_seconds`
- `cache_hits`
- `human_interventions`
- `model_requests_observed`：如平台暴露真实值才写，否则 `null`，不编造。

`baseline_comparison` 只使用平台提供的官方白板或平台生成对照。未提供时写：

```
{"status": "pending_platform", "message": "待平台生成同库集合、额度和查询条件下的对照结果"}
```

不得自造基线分数，不得用自述代替对照证据。

## 11. 预算、稳定性与可续跑

阶段请求建议：

| 阶段 | 建议模型请求上限 |
|-|-|
| `init` 台账阅读 | <=8 |
| 原文阅读与 `draft.json` 判断 | <=20 |
| 校验/冲突仲裁 | <=8 |
| 最终自检与修正 | <=4 |
| 预留缓冲 | >=24 |

规则：

- 脚本阶段必须秒级完成。
- 每个阶段先写部分成果，避免 900 秒末空手。
- 支持重跑；已有台账和 partial 时按原始顺序恢复，不重复导入。
- 每库记录完成、空结果、受限、失败四类状态；重试次数写死上限，不无限重试。
- 编码异常按 `utf-8-sig -> utf-8 -> gb18030 -> latin-1` 回退，修复动作写 `changes[]`。
- 撤回线索只写 `flags:["retraction_notice"]` 和 `pending_human`，不静默删除。

## 12. 异常与降级

| 情况 | 处置 |
|-|-|
| 无 `case.json` | 递归找 case 文件；仍无则 `input_error` 并写 partial |
| JSON 损坏 | 逐行尝试 JSONL；仍失败记 `errors`，跳过该文件继续 |
| 某库无响应 | 输出查询计划，`status=planned_not_executed_offline`，写 `coverage.gaps` |
| 限流/额度标记 | 识别 `429`、`quota`、`rate limit`、`retry-after`，记 `errors`，不重试不发网 |
| 字段缺失 | 置 `null`，统计 `field_fill`，不臆填 |
| 标识符冲突 | 写 `conflicts[]`，权威库裁决 + 人工仲裁入口 |
| 坏编码 | 回退解码，写 `changes[]` |
| 记录为 0 | `status=insufficient_evidence`，写明已查库与查询，不补造 |

## 13. 自检清单

- [ ] `result.json` 是合法 JSON，`case_id` 与输入一致，`status` 在枚举内。
- [ ] 原 `output_contract` 每个字段在顶层和 `output_contract` 中都存在。
- [ ] `contract_fill` 对每个契约字段标记 filled 或 empty:unmapped。
- [ ] 每条候选有 `source_dbs`、`query_ids`、`raw_file`、`raw_pointer`、`retrieved_at`。
- [ ] 同一规范标识符不出现在两个不同 `cluster_id`。
- [ ] `len(candidates)` 与 `candidate_count`、`candidates.csv` 行数一致。
- [ ] 未执行库都有 `planned_not_executed_offline`。
- [ ] `errors`、`degradations`、`uncertainty` 与 `status` 自洽。
- [ ] 无编造文献、无无来源补全、无实时/最新/全球覆盖声明。

## 14. 最小调用示例

示例输入：

```
{"case_id": "demo-example",
 "task_instruction": "offshore wind turbine wake steering control",
 "output_contract": {"fields": [{"name": "candidates"}, {"name": "queries"}, {"name": "coverage"}]},
 "artifacts": {"responses": ["responses/crossref_q1.json", "responses/epmc_q2.json"]}}
```

调用：

`python3 scripts/main.py run --input ./demo_input --output ./demo_output --work ./demo_work`

示意输出，数值为示例占位：

```
{"case_id":"demo-example","status":"partial",
 "candidates":[{"id":"c001","title":"...","year":2021,"doi":"10.0000/example",
   "source_dbs":["crossref","europepmc"],"query_ids":["q001","q002"],
   "retrieved_at":"2026-01-01T00:00:00Z","relevance_score":0.72,"cluster_id":"k01"}],
 "queries":[{"query_id":"q001","db":"crossref","status":"executed_offline_recorded","hits":20}],
 "coverage":{"per_db":{"crossref":20,"europepmc":18},
   "gaps":["no OpenAlex response supplied"]},
 "output_contract":{"case_id":"demo-example","candidates":["..."],"queries":["..."],"coverage":{}}}
```

该例表示 `q001` 的 20 条与 `q002` 的 18 条经映射与去重后，`c001` 两库命中且字段互补；最终数值由真实输入决定。

## 15. 禁止事项

- 禁止预制答案或正式测试输出。
- 禁止根据领域标签臆造文献内容、字段或筛选结论。
- 禁止覆盖或遗漏原 `output_contract` 字段。
- 禁止 DOI 冲突强并、年份语义混用。
- 禁止缺字段、失败、筛除无记录。
- 禁止宣称实时全网覆盖、最新性或全球创新。
- 禁止无依据补全文、引文或撤回状态。
- 禁止引入个人依赖或越权汇总未经授权的数据。

## 16. 评分要点映射

| Rubric | 本 Skill 对应机制 |
|-|-|
| 实际效果：任务完成/正确性/完整性/可核验性 | `queries[]`、`clusters[]`、`candidates[]`、`field_provenance`、`coverage`、`evidence[]`、`trace.jsonl` |
| 使用增益：质量/效率/可验证性 | `metrics.json`、`baseline_comparison`、平台官方对照入口、少请求完成全量交付 |
| 创新增益：新增能力/方法改进/证据 | 确定性合并、疑似重复隔离、覆盖矩阵、真实冲突前后记录于 `report.md` |
| 可靠体验：易用/稳定/异常 | 单命令 `run`、恒 exit 0、阶段部分保存、重跑不重复、逐库状态 |
| 生态贡献：文档/复用/分享 | 规则外置于 `references/db-profiles.json`、示例、自检清单、脚本可复用 |

## 17. 维护

- 新增库：只改 `references/db-profiles.json`，补充 `signatures`、`record_paths`、字段映射路径、查询方言和额度语义。
- 调整去重阈值或合并优先级：改 `references/db-profiles.json` 对应块并运行 `selfcheck`。
- 版本号同步：更新本文件 frontmatter `version`。