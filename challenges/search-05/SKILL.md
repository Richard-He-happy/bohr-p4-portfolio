---
name: multidb-literature-search
version: 1.1.0
description: 多数据库联合检索 Skill。按各库检索语法与额度编排 Crossref / Europe PMC / PubMed / OpenAlex / Semantic Scholar 等来源的查询，把结构不同的响应归一为统一文献记录，按标识符精确匹配 + 题录模糊比对做可解释去重，按字段权威度合并冲突，并为每条记录保留“库→查询→原始响应→字段映射→去重→合并”的完整回溯链与覆盖/遗漏说明。用于需要跨库检索、去重、字段补全、覆盖比较的学术文献检索任务；离线可运行，不联网、不编造文献。
---

# 多数据库联合检索（multidb-literature-search）

## 0. 首要原则：Agent 是作者，脚本只是工具

- `scripts/main.py` 只做**机械活**：发现输入、解析契约、抽取原始响应字段、跑归一/去重/合并的**草稿**、做确定性校验、落合法 JSON 骨架。
- **最终交付物（`result.json` 的候选集、相关性依据、去重裁决、覆盖与遗漏说明）必须由 Harness 中的 Agent 亲自读原始材料推导后撰写。** 脚本产出的骨架、占位字段、自动打分为**草稿证据**，不是成品。
- **禁止**把 `main.py` 的输出、模板、示例（第 11 节的 demo）直接当成本案例结论提交；**禁止**用领域标签或常识替代 `/input` 中的真实响应内容。
- 每一处结论都要能指回“哪个库、哪次查询、原始响应的哪个位置”。Agent 写不出 locator 的结论，删掉或降级为 `uncertainty`。

## 1. 用途与边界

**做什么**：把同一科研问题在多个学术数据库中的检索结果，合并成一份**不重复、字段可用、逐条可回溯**的候选文献集，并说清哪些库、哪些字段没覆盖到。四件核心事全部实现：

1. **多源查询编排**：按库生成各自检索式（PubMed 字段标签 / Europe PMC `TITLE_ABS` / Crossref `query.bibliographic`+`filter` / OpenAlex `search`+`filter` / S2 `query`），带年份、语言、类型过滤与分页/额度说明，不把同一条查询机械复制到所有库。
2. **字段标准化**：跨库字段映射表把作者、期刊、年份、标识符、文献类型归一到统一 18 个规范字段，区分**缺失（null = 该库没给）**与**未知（未检索）**。
3. **去重**：DOI/PMID/PMCID/arXiv 精确匹配 → 题名标准化精确匹配 → 题名相似度 + 首作者 + 年份三重守卫模糊匹配；每条判定带规则、信号、置信度，歧义进人工仲裁。
4. **合并 + 来源回溯**：按字段权威度选值，落选值写进 `conflicts`；每条记录保留 `source_dbs`、`query_ids`、`raw_file`、`raw_pointer`、`retrieved_at`。

**不做什么**（越界即降级，写进 `degradations`）：不发起网络请求（离线，消费 `/input` 下已录制响应）；不生成输入中不存在的文献、DOI、引用、期刊、年份、摘要；不做全文精读、不判断科学质量、不声明“全球覆盖/最新进展”；不绕过任何服务限制或额度。

## 2. 运行契约

| 项 | 值 |
|-|-|
| 包根 | `/app/submission/`（本包根 `SKILL.md`） |
| 安装位置 | `/skills/weekly-skill` |
| 输入 | `/input/case.json` + `/input/task.md` + `/input/artifacts/`、`material.json`、PDF/CSV/JSONL 等材料 |
| 工作目录 | `/app/work`（临时，存 Agent 的核对草稿） |
| 输出 | `/app/output/`：`result.json` + `candidates.csv` + `candidates.json` + `query_log.json` + `merge_log.json` + `coverage.md` |
| 依赖 | 仅 Python 3.8+ 标准库；无第三方包、无子进程、无网络 |
| 预算 | 64 次模型请求 / 900 s / 单次回复 16384 tokens；脚本秒级完成，接近 780 s 立即 finalize 并声明 partial |
| 退出码 | **恒为 0**（异常写 `errors`，不中断） |
| 写入边界 | 只读 `/input`，只写 `/app/output` 与 `/app/work` |
| 案例数 | 3 个固定案例，逐案独立执行，`case_id` 原样透传，不跨案例复用结论 |

## 3. 工具调用方式

```bash
python3 /skills/weekly-skill/scripts/main.py                       # 默认 --input /input --output /app/output
python3 /skills/weekly-skill/scripts/main.py --help
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --min-score 0.3
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/work/draft --min-score 0.3
```

用法分工（Agent-first）：

- **先跑草稿**：输出到 `/app/work/draft`，得到结构、去重簇、字段占用情况的草稿，供 Agent 阅读与质疑。
- **再跑正式**：`--output /app/output`，落合法 partial `result.json`；`main.py` 第一步就写 partial，最后无条件 finalize。**finalize 只保证 JSON 合法，不代表内容已通过 Agent 复核。**
- 中途任何阶段失败只降级该阶段（写 `errors`/`degradations`），不影响其他阶段与退出码。

## 4. Agent 执行流程（六步，逐案执行）

**Step 0 盘点输入，写清单。**
读 `/input/case.json` 与 `/input/task.md`；递归列出 `/input/**` 实际文件。产出 `/app/work/00_inventory.md`：研究问题原文、案例要求的库集合、年份/语言/类型约束、`output_contract` 字段名逐条列出、每个库响应文件 → 文件名/格式/可读记录条数/关键字段是否存在的表格、以及**缺失清单**。禁止凭领域标签假设文件内容。

**Step 1 跑工具取证据。**
`main.py --output /app/work/draft`，然后 **Agent 亲自读**：`draft/query_log.json`（每库查询式与 hits）、`draft/merge_log.json`（每条去重判定）、`draft/coverage.md`（每库条数与字段填充）。把其中明显可疑处（同 DOI 落两簇、hits 为 0 但库响应非空、年份为 null 但原文有）记进 `/app/work/01_issues.md`。

**Step 2 Agent 逐库核对原始响应。**
对每个库至少抽样 3 条（不足 3 条则全查）：把原始响应片段（`raw_file` + JSON Pointer）与草稿的 `candidates[]` 对照，核对 `title`/`authors`/`year`/`venue`/`doi` 是否逐字一致、`field_provenance` 是否指向真实存在的路径。对脚本无法判断的情形（作者别名、期刊缩写全称、年份跨库差 1、卷期缺失、撤回标记、编码乱码）由 Agent 读原文裁决，结论写进 `changes[]` 或 `pending_human[]`。核对记录写 `/app/work/02_verify.md`，含每次抽样的 locator。

**Step 3 Agent 撰写交付内容（核心步骤）。**
在 `/app/output/result.json` 上**逐字段改写**，不得留模板值：

- `candidates[]`：每条亲自确认 `title`、`authors[]`（保留原库写法差异并记录归一规则）、`year`、`venue`、`doi`、`url`、`source_dbs[]`、`query_ids[]`、`retrieved_at`、`cluster_id`、`included`。
- `relevance_score` + `relevance_reason`：理由必须**引用材料中的原话片段**（研究问题/摘要/关键词），并给 locator；不得写“看起来相关”。
- `clusters[]` / `conflicts[]`：每条去重写清命中哪条规则（A/B/C）、信号（共享 DOI？题名相似度？首作者姓？）、置信度；冲突写清落选值与落选理由（哪一库权威）。
- `screening`：`criteria` 按案例真实纳入/排除条件写；`excluded[]` 每条给排除理由 + 证据 locator。
- `queries[]`：每库至少一条，`expanded` 是**该库语法**的检索式；未执行的写 `status=planned_not_executed_offline` 并进 `coverage.gaps`。
- `coverage`：`per_db`、`unique_to_db`（**逐条点名只在单库出现的文献**）、`field_fill`、`gaps[]`（哪些库/字段系统性缺失，为什么）。
- `baseline_comparison`：naive 拼接条数（各库 hits 之和）vs 合并后条数、消解重复数、跨库 DOI 一致数、关键字段填充率相对最佳单库的提升。有种子/金标准才写 `metrics`（P@k/Recall@k），否则 `null` + 原因。
- `uncertainty[]` / `pending_human[]` / `errors[]` / `degradations[]` / `changes[]`：状态诚实，与 `status` 自洽。

**Step 4 正例证伪。**
Agent 自查三条反例：①是否存在“只在一个库出现过却被合并”的记录；②是否存在“同 DOI 出现在两个簇”；③是否存在 `relevance_reason` 无 locator 的候选。任一命中即回 Step 3 修正，并把修正写入 `changes[]`。

**Step 5 同步派生文件。**
`candidates.csv` 行数与 `candidates.json`/`candidates[]` 一致；`coverage.md` 与 `coverage` 块一致；`output_contract` 每个字段在顶层存在（按语义映射，未映射填 `null`/`[]`），`contract_fill` 逐字段说明填充来源，`contract_echo` 保留原始契约。

**Step 6 自检并定稿。**
过第 10 节清单；`status` 只能是 `ok` / `partial` / `insufficient_evidence` / `input_error`。若预算将尽，先落**诚实的 partial**（写明已查库、已核条数、未完成部分），再增量改进，不得为凑完整而编造。

## 5. 输出契约（`result.json`）

必含（缺值 `null`/`[]`，字段名不改）：

| 块 | 内容 |
|-|-|
| 身份 | `case_id`（原样）、`skill`、`skill_version`、`generated_at`、`status` |
| `candidates[]` | `id` `title` `authors[]` `year` `venue` `doi` `pmid` `url` `source_dbs[]` `query_ids[]` `retrieved_at` `relevance_score` `relevance_reason` `evidence` `field_provenance` `metadata_confidence` `flags[]` `cluster_id` `included` |
| `queries[]` | `query_id` `db` `raw` `expanded` `filters` `hits` `status` `error` `retrieved_at` `source_file` |
| `screening` | `include`/`exclude`/`excluded[]`/`criteria` |
| `coverage` | `per_db` `unique_to_db` `field_fill` `gaps[]` `recall_estimate` |
| `clusters[]` / `conflicts[]` | 去重簇与字段冲突（含落选值） |
| `sources[]` `evidence[]` | 库清单与逐条 quote + locator |
| `uncertainty[]` `pending_human[]` `errors[]` `degradations[]` `changes[]` | 状态诚实 |
| `runtime` `self_check` `metrics` `baseline_comparison` `contract_fill` `contract_echo` | 运行与自检证据 |

## 6. 评分 rubric → Agent 交付要求对照

| 评分维度（分值） | Agent 必须交付什么 | 怎么自证 |
|-|-|-|
| 实际效果·任务完成度 15 | 每个案例的联合候选集已合并、已排序、已筛；`queries[]` 每库一条带 `expanded` 的真实检索式 | `queries[].status` 与实际响应文件一一对应；`screening.criteria` 引用题面约束原文 |
| 实际效果·结果正确性 15 | 论文身份可靠（DOI/PMID 规范化后一致）、字段按各库真实语义填充、重复判定成立 | 抽样对照 `raw_pointer` 的 `02_verify.md`；`clusters[]` 写明命中规则；`conflicts[]` 保留落选值 |
| 实际效果·结果完整性 5 | 覆盖案例要求的库集合与关键字段；点名 `unique_to_db`；列出 `field_fill` 与系统性缺失 | `coverage.gaps[]` 每条给“哪个库/哪个字段/为什么”；未执行库显式标 `planned_not_executed_offline` |
| 实际效果·可核验性 5 | 每条候选可沿“库→查询→原始响应→映射→去重→合并”回溯 | 候选必备 `source_dbs`+`query_ids`+`raw_file`+`raw_pointer`+`retrieved_at`；`evidence[].quote` 为清洗前逐字片段 |
| 使用增益 25 | 相比 naive 拼接的质量与效率改善 | `baseline_comparison` 给：拼接条数 vs 合并条数、消解重复数、跨库 DOI 一致数、字段填充率提升；有种子才给 `metrics`，否则 `null`+原因 |
| 创新增益 15 | 跨库字段映射、三重守卫去重、权威度冲突消解、种子下限召回估计、离线降级 | 映射表在 `references/db-profiles.json`；每条创新点对应到具体字段与具体记录（举例 1–2 条） |
| 可靠体验 10 | 可独立跑通、重复运行稳定、异常有分支 | `changes[]` 记录重复运行差异（若有）；第 9 节场景全部有处置痕迹 |
| 生态贡献 10 | 文档与资源可复用 | 本文件 + `references/db-profiles.json` 即可复现；第 11 节示例标明为示例 |

## 7. 字段映射、去重与合并（摘要，细则见 `references/db-profiles.json`）

- 规范字段 18 个，映射路径写在 `references/db-profiles.json`；未知库走内置同义词回退并记 `changes`。
- 合并优先级：标识符取权威库（doi→Crossref，pmid/pmcid→PubMed/EuropePMC，arxiv→arXiv）；题名/作者/年份/期刊以 Crossref 与出版方响应优先；摘要以出版方/Europe PMC 优先；被引数须注明 OpenAlex/S2 语义不同、不可跨库直接比较。
- 同权威度取更长非空值，再按库名排序 → 结果稳定可复现。

| 去重阶段 | 规则 | 置信度 |
|-|-|-|
| A | 共享 DOI/PMID/PMCID/arXiv（规范化后） | high |
| B | 题名标准化后完全相同且长度≥15，年份相同或一方缺失 | high |
| B' | 题名相同但年份相差>1 | 不合并 → `pending_human` |
| C | 题名 SequenceMatcher ≥0.90 且首作者姓相同且年份±1 | high |
| C' | 同守卫但相似度 0.82–0.90 | medium，合并并标 `needs_arbitration` |

绝不单凭“同作者+同年”合并。`evidence[].quote` 必须是原文逐字片段，`locator` 用 JSON Pointer（如 `/message/items/3/title/0`）；找不到标 `unverified` 并进 `pending_human`。

## 8. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；缺失时递归找任意 `case*.json`（含 `case_id`/`task_instruction`/`output_contract`/`scope` 任一键即认定），仍失败则读 `/input/task.md` 提取任务描述。
2. `case_id`、`output_contract` **原样透传**（键名不改、未知字段保留）。
3. 材料按键名**语义**取值：研究问题（`topic` `research_question` `question` `title` `subject` `objective` `query` `task_instruction`）、库集合（`databases` `dbs` `data_sources` `sources`）、年份（`years` `year_range` `year_from` `year_to`）、语言/类型（`language` `doc_types` `pub_types` `include` `exclude`）、上限（`max_k` `top_k` `limit` `budget`）、种子/金标准（`seeds` `seed_dois` `known_relevant` `gold`）。
4. 递归扫描 `/input/**`，按扩展名 + 内容签名识别：库响应 JSON/JSONL、`records.jsonl`、`queries.jsonl`、`reference_graph.json`、`citations.jsonl`、`schema.json`、`config.yaml`、`material.json`、`*.csv`、`*.pdf`、`*.docx`、图片。
5. **未给对象明确列缺口**，写进 `coverage.gaps` 与 `errors`，不构造像素、图注、数据或文献。

## 9. 异常与降级

| 情况 | 处置 |
|-|-|
| 无 `case.json` | 递归找 case 文件；仍无 → `input_error`，仍写合法 partial |
| JSON 损坏 | 尝试 JSONL 逐行解析；仍失败 → 记 `errors`，跳过该文件，继续其余 |
| 某库无响应 | 输出查询计划 + `planned_not_executed_offline`，写 `coverage.gaps`，`status=partial` |
| 限流/额度标记 | 识别 `429`/`quota`/`rate limit`/`retry-after` → 记 `errors`，不重试不联网 |
| 字段缺失 | `null` + `field_fill` 统计，不臆填 |
| 标识符冲突 | `conflicts[]` + 权威库裁决 + `pending_human` |
| 编码异常 | utf-8-sig/utf-8/gb18030/latin-1 依次解码；乱码尝试回转修复，记 `changes` |
| 文献被撤回 | `flags:["retraction_notice"]` + `pending_human`，不静默剔除 |
| 记录为 0 | `insufficient_evidence`，写明已查库与查询，不补造 |

## 10. 质量红线与自检清单

**红线（触碰即视为未完成）**：编造文献/DOI/年份/摘要；把 demo 或模板值当结论；`relevance_reason` 无 locator；`status` 明明是缺口却写 `ok`；把 `main.py` 的草稿原样 finalize 而不做 Step 2–4。

- [ ] `result.json` 合法 JSON，`case_id` 与输入一致，`status` 在枚举内。
- [ ] Agent 已跑过 Step 0–4，`/app/work/00_inventory.md`、`02_verify.md` 存在且含真实 locator。
- [ ] `output_contract` 每个字段在顶层存在（`contract_fill` 全 filled 或 empty:unmapped）。
- [ ] 每条候选有 `source_dbs` + `query_ids` + `retrieved_at` + `evidence.locator`。
- [ ] `queries[]` 覆盖每个已识别库；未执行的标 `planned_not_executed_offline`。
- [ ] 同一 DOI 不出现在两个 `cluster_id`；`excluded[]` 每条有理由与证据。
- [ ] `len(candidates)` 与 `candidate_count`、`candidates.csv` 行数、`candidates.json` 条数一致。
- [ ] `coverage.unique_to_db` 与 `gaps[]` 是逐条点名的，不是形容词。
- [ ] `errors`/`degradations`/`uncertainty`/`changes` 与 `status` 自洽；无编造内容。
- [ ] `python3 -B scripts/main.py --help` 退出 0；无 `__pycache__`、无越界写入。

## 11. 最小调用示例（**示例，非正式案例结果**）

输入（示例）：

```json
{"case_id":"demo-example","task_instruction":"offshore wind turbine wake steering control",
 "output_contract":{"fields":[{"name":"candidates"},{"name":"queries"},{"name":"coverage"}]},
 "artifacts":{"responses":["responses/crossref_q1.json","responses/epmc_q2.json"]}}
```

调用：

```bash
python3 /skills/weekly-skill/scripts/main.py --input ./demo_input --output ./demo_output
```

示意输出（**示例，非正式案例结果**，数值为演示用占位）：

```json
{"case_id":"demo-example","status":"partial","candidates":[{"id":"c001","title":"…","year":2021,
 "doi":"10.0000/example","source_dbs":["crossref","europepmc"],"query_ids":["q001","q002"],
 "retrieved_at":"2026-01-01T00:00:00Z","relevance_score":0.72,"relevance_reason":"题面含 'wake steering'，摘要原句见 evidence[0]","cluster_id":"k01"}],
 "queries":[{"query_id":"q001","db":"crossref","status":"executed_offline_recorded","hits":20}],
 "coverage":{"per_db":{"crossref":20,"europepmc":18},"gaps":["no OpenAlex response supplied"]}}
```

解读：`q001` 的 20 条与 `q002` 的 18 条经字段映射后按 DOI/题名聚成 31 条（示意）；`c001` 两库都有且字段互补。**示例仅供说明接口，正式案例必须由 Agent 依第 4 节流程重新推导。**

## 12. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（Agent-first 原则 / 契约 / 六步流程 / rubric 对照 / 降级 / 自检） |
| `scripts/main.py` | 工具：输入发现、契约解析、字段抽取与归一草稿、去重合并草稿、确定性校验、落合法 JSON；`--help` 可用，恒退出 0 |
| `references/db-profiles.json` | 库响应签名、字段映射路径、查询方言、额度与语义注意 |

维护：新增库只改 `references/db-profiles.json`（加 `signatures`、`record_paths`、`query`），无需改代码；映射表版本随 frontmatter `version` 同步。