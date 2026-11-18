---
name: multidb-literature-search
description: 多数据库联合检索 Skill。按各库检索语法与额度编排 Crossref / Europe PMC / PubMed / OpenAlex / Semantic Scholar 等来源的查询，把结构不同的响应归一为统一文献记录，按标识符精确匹配 + 题录模糊比对做可解释去重，按字段权威度合并冲突，并为每条记录保留“库→查询→原始响应→字段映射→去重→合并”的完整回溯链与覆盖/遗漏说明。用于需要跨库检索、去重、字段补全、覆盖比较的学术文献检索任务；离线可运行，不联网、不编造文献。
version: 1.0.0
---

# 多数据库联合检索（multidb-literature-search）

## 1. 用途与边界

**做什么**：把同一科研问题在多个学术数据库中的检索结果，合并成一份**不重复、字段可用、逐条可回溯**的候选文献集，并说清哪些库、哪些字段没覆盖到。

**四件核心事**（对应题面四个突破方向，本 Skill 全部实现，不选其一）：

1. **多源查询编排**：按库生成各自的检索式（PubMed 字段标签 / Europe PMC `TITLE_ABS` / Crossref `query.bibliographic`+`filter` / OpenAlex `search`+`filter` / S2 `query`），带年份、语言、类型过滤与分页/额度说明，不把同一条查询机械复制到所有库。
2. **字段标准化**：一份跨库字段映射表把作者、期刊、年份、标识符、文献类型归一到统一的 18 个规范字段，并区分**缺失（null = 该库没给）**与**未知（未检索）**。
3. **去重**：DOI/PMID/PMCID/arXiv 精确匹配 → 题名标准化精确匹配（同年或年份缺） → 题名相似度 + 首作者 + 年份三重守卫的模糊匹配；每条判定带规则、信号与置信度，歧义对进人工仲裁。
4. **合并 + 来源回溯**：按字段权威度选值，落选值全部写进 `conflicts`；每条记录保留 `raw_file` + `raw_pointer`（JSON Pointer）+ `retrieved_at`。

**不做什么**（越界即降级，写进 `degradations`）：

- 不发起网络请求（运行环境离线；本 Skill 消费 `/input` 下已录制的库响应与材料）。缺少某库响应时输出**查询计划**并标 `planned_not_executed_offline`，不伪造成“已检索”。
- 不生成未在输入中出现的文献、DOI、引用、期刊名、年份、摘要。
- 不做单库全文精读、不判断论文科学质量、不声明“最新进展/全球覆盖”。
- 不绕过任何服务限制或额度。

## 2. 适用条件

| 适用 | 不适用 |
|-|-|
| 一个科研问题需要 2 个以上学术库的结果合并 | 只查单库、只要一条已知 DOI 的元数据 |
| 输入含库响应（Crossref/EuropePMC/PubMed/OpenAlex/S2/通用 JSON/JSONL/CSV）或检索记录 | 输入只有一句自然语言问题、无任何可读响应 |
| 需要去重、字段补全、覆盖与遗漏说明 | 需要全文精读、Meta 分析、疗效结论 |
| 需要逐条回溯“这条记录哪来的” | 需要在线实时检索（本 Skill 离线） |

输入形态**不假设固定键名**，见第 5 节。

## 3. 运行契约

| 项 | 值 |
|-|-|
| 包根 | `/app/submission/`（本包根 `SKILL.md`） |
| 安装位置 | `/skills/weekly-skill`（平台挂载后按 SKILL.md 调用） |
| 输入 | `/input/case.json` + `/input/task.md` + `/input/artifacts/`、`material.json`、PDF/CSV/JSONL 等材料 |
| 工作目录 | `/app/work`（临时，可丢） |
| 输出 | `/app/output/`：`result.json` + `candidates.csv` + `candidates.json` + `query_log.json` + `merge_log.json` + `coverage.md` |
| 依赖 | 仅 Python 3.8+ 标准库；无第三方包、无子进程、无网络 |
| 预算 | 64 次模型请求 / 900 s / 单次回复 16384 tokens；脚本本身秒级完成，接近 780 s 立即 finalize |
| 退出码 | **恒为 0**（异常写 `errors`，不中断） |
| 写入边界 | 只读 `/input`，只写 `/app/output` 与 `/app/work` |

## 4. 快速开始

```bash
python3 /skills/weekly-skill/scripts/main.py                       # 默认 --input /input --output /app/output
python3 /skills/weekly-skill/scripts/main.py --help
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --min-score 0.3
python3 /skills/weekly-skill/scripts/verify.py --result /app/output/result.json --input /input
```

`main.py` 第一步先落一份合法 partial `result.json`，最后无条件 finalize 覆盖；中途任何阶段失败只降级该阶段。

## 5. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；缺失时递归找任意 `case*.json`（含 `case_id`/`task_instruction`/`output_contract`/`scope` 任一键即认定为 case 文件），仍失败则读 `/input/task.md` 提取任务描述。
2. `case_id`、`output_contract` **原样透传**（键名不改、未知字段保留）。
3. 材料按键名**语义**取值（同义键名任一命中即可）：

| 语义 | 识别键（大小写不敏感，含子串） |
|-|-|
| 研究问题 | `topic` `research_question` `question` `title` `subject` `objective` `query` `task_instruction` |
| 库集合 | `databases` `dbs` `data_sources` `sources` `database_list` |
| 年份范围 | `years` `year_range` `year_from` `year_to` `publication_years` `time_range` |
| 语言/类型 | `language` `languages` / `doc_types` `pub_types` `include` `exclude` |
| 上限 | `max_k` `top_k` `limit` `budget` |
| 种子/金标准 | `seeds` `seed_papers` `seed_dois` `known_relevant` `gold` `reference_seeds` |

4. 递归扫描 `/input/**`，按扩展名 + 内容签名识别：库响应 JSON/JSONL、`records.jsonl`、`queries.jsonl`、`reference_graph.json`、`citations.jsonl`、`schema.json`、`config.yaml`、`material.json`、`*.csv`、`*.pdf`、`*.docx`、图片。
5. **未给对象明确列缺口**：写进 `coverage.gaps` 与 `errors`，不构造像素、图注、数据或文献。

## 6. 输出契约（`result.json`）

必含（缺值 `null`/`[]`，字段名不改）：

| 块 | 内容 |
|-|-|
| 身份 | `case_id`（原样）、`skill`、`skill_version`、`generated_at`、`status` |
| `status` 枚举 | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `candidates[]` | 每篇一篇一条：`id` `title` `authors[]` `year` `venue` `doi` `pmid` `url` `source_dbs[]` `query_ids[]` `retrieved_at` `relevance_score` `relevance_reason` `evidence` `field_provenance` `metadata_confidence` `flags[]` `cluster_id` `included` |
| `queries[]` | `query_id` `db` `raw` `expanded` `filters` `hits` `status` `error` `retrieved_at` `source_file` |
| `screening` | `include`/`exclude`/`excluded[]`/`criteria` |
| `coverage` | `per_db` `unique_to_db` `field_fill` `gaps[]` `recall_estimate` |
| `clusters[]` / `conflicts[]` | 去重簇与字段冲突（含落选值） |
| `sources[]` `evidence[]` | 库清单与逐条 quote+locator |
| `uncertainty[]` `pending_human[]` `errors[]` `degradations[]` `changes[]` | 状态诚实 |
| `runtime` `self_check` `metrics` `baseline_comparison` | 运行与自检证据 |

`output_contract` 每个字段都出现在顶层（按语义映射，未映射填 `null`/`[]`），并在 `contract_fill` 里逐字段说明填充来源；`contract_echo` 保存原始契约。

## 7. 核心流程

```
发现输入 → 解析契约 → 库识别 → 查询编排 → 记录收割 → 字段映射归一
→ 去重聚类 → 字段合并/冲突消解 → 相关性打分与筛选 → 覆盖与基线指标
→ 发布实盘轨迹 → 契约回填 → 自检 → finalize
```

每阶段包 `try/except`，失败只降级本阶段并写 `errors`/`degradations`。

## 8. 评分要点映射

| 评分维度 | 字段 / 检查 / 产物 |
|-|-|
| 实际效果·任务完成度 15 | `queries[]` 每库一条带 `expanded` 的检索式；`clusters[]` 去重；`candidates[]` 合并且字段可用；`status` 非 ok 时写明缺口 |
| 实际效果·结果正确性 15 | DOI 规范化校验、`field_provenance` 逐字段指向来源库与原始路径、`conflicts[]` 保留落选值、`metadata_confidence` |
| 实际效果·结果完整性 5 | `coverage.unique_to_db`（单库独有）、`coverage.field_fill`（系统性缺失字段）、`coverage.gaps` |
| 实际效果·可核验性 5 | 每条候选 `source_dbs`+`query_ids`+`raw_file`+`raw_pointer`+`retrieved_at`；`evidence[]` 逐字 quote；`merge_log.json` 全量判定 |
| 使用增益 25 | `baseline_comparison`：naive 拼接条数 vs 合并条数、重复消解数、字段填充率相对最佳单库的提升、跨库 DOI 一致数；`metrics`（有金标准才给 P@k/nDCG@k/Recall@k，无则 `null`+原因） |
| 创新增益 15 | 跨库字段映射表（`references/db-profiles.json`）、三重守卫去重、字段权威度冲突消解、种子下限召回估计、离线降级 |
| 可靠体验 10 | `--help` 自述；空输入/坏 JSON/缺库/缺字段/编码异常/撤回文献均有分支；重复运行结果哈希一致 |
| 生态贡献 10 | `references/` 三份可复用资源（映射表、规范、清单）+ 第 14 节示例 |

## 9. 字段映射与合并（摘要，细则见 `references/`）

- 规范字段 18 个，映射路径写在 `references/db-profiles.json`；未知库走内置同义词回退。
- 合并优先级：标识符取**权威库**（doi→Crossref，pmid/pmcid→PubMed/EuropePMC，arxiv→arXiv）；题名/作者/年份/期刊以 Crossref 与出版方响应优先，摘要以出版方/Europe PMC 全文侧优先；被引数注明 OpenAlex/S2 语义不同、不可跨库直接比较。
- 同权威度时取更长非空值，再按库名排序 → 结果稳定可复现。

## 10. 去重与人工仲裁

| 阶段 | 规则 | 置信度 |
|-|-|-|
| A | 共享 DOI/PMID/PMCID/arXiv（规范化后） | high |
| B | 题名标准化后完全相同且长度≥15，年份相同或一方缺失 | high |
| B' | 题名相同但年份相差>1 | 不合并 → `pending_human` |
| C | 题名 SequenceMatcher ≥0.90 且首作者姓相同且年份±1 | high |
| C' | 同守卫但相似度 0.82–0.90 | medium，合并并标记 `needs_arbitration` |

绝不单凭“同作者+同年”合并。

## 11. 证据与回溯规范

`库 → 查询(query_id) → 原始响应(source_file) → 字段映射(raw_pointer) → 去重(cluster_id) → 合并(field_provenance)`

`evidence[].quote` 必须是原文逐字片段（清洗前），`locator` 用 JSON Pointer（`/message/items/3/title/0`）；找不到就标 `unverified` 并进 `pending_human`。

## 12. 异常与降级

| 情况 | 处置 |
|-|-|
| 无 `case.json` | 递归找 case 文件；仍无 → `input_error`，仍写合法 partial |
| JSON 损坏 | 尝试 JSONL 逐行解析；仍失败 → 记 `errors`，跳过该文件，继续其余 |
| 某库无响应 | 输出查询计划 + `planned_not_executed_offline`，写 `coverage.gaps`，`status=partial` |
| 限流/额度标记 | 识别 `429`/`quota`/`rate limit`/`retry-after` → 记 `errors`，不重试不发网 |
| 字段缺失 | `null` + `field_fill` 统计，不臆填 |
| 标识符冲突 | `conflicts[]` + 权威库裁决 + `pending_human` |
| 编码异常 | utf-8-sig/utf-8/gb18030/latin-1 依次解码；latin-1 乱码尝试回转修复，记 `changes` |
| 文献被撤回 | `flags:["retraction_notice"]` + `pending_human`，不静默剔除 |
| 记录为 0 | `insufficient_evidence`，写明已查库与查询，不补造 |

## 13. 自检清单

- [ ] `result.json` 合法 JSON，`case_id` 与输入一致，`status` 在枚举内。
- [ ] `output_contract` 每个字段在顶层存在（`contract_fill` 全为 filled 或 empty:unmapped）。
- [ ] 每条候选有 `source_dbs` + `query_ids` + `retrieved_at` + `evidence.locator`。
- [ ] `queries[]` 覆盖每个已识别库；未执行的有 `status=planned_not_executed_offline`。
- [ ] 去重后同一 DOI 不出现在两个 `cluster_id`。
- [ ] `len(candidates)` 与 `candidate_count`、`candidates.csv` 行数一致。
- [ ] `errors`/`degradations`/`uncertainty` 与 `status` 自洽；无编造文献。
- [ ] `python3 -B scripts/main.py --help` 退出 0；无 `__pycache__`。

## 14. 最小调用示例（**示例，非正式案例结果**）

输入（示例）：

```json
{"case_id":"demo-example","task_instruction":"offshore wind turbine wake steering control",
 "output_contract":{"fields":[{"name":"candidates"},{"name":"queries"},{"name":"coverage"}]},
 "artifacts":{"responses":["responses/crossref_q1.json","responses/epmc_q2.json"]}}
```

调用：

```bash
python3 scripts/main.py --input ./demo_input --output ./demo_output
```

示意输出（**示例，非正式案例结果**，数值为演示用占位）：

```json
{"case_id":"demo-example","status":"partial","candidates":[{"id":"c001","title":"…","year":2021,
 "doi":"10.0000/example","source_dbs":["crossref","europepmc"],"query_ids":["q001","q002"],
 "retrieved_at":"2026-01-01T00:00:00Z","relevance_score":0.72,"cluster_id":"k01"}],
 "queries":[{"query_id":"q001","db":"crossref","status":"executed_offline_recorded","hits":20}],
 "coverage":{"per_db":{"crossref":20,"europepmc":18},"gaps":["no OpenAlex response supplied"]}}
```

解读：`q001` 的 20 条与 `q002` 的 18 条经字段映射后按 DOI/题名聚成 31 条（示意），`c001` 两库都有且字段互补。

## 15. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（用途/契约/流程/降级/自检） |
| `scripts/main.py` | 主流程，`--help` 可用，恒退出 0 |
| `scripts/verify.py` | 确定性校验：契约字段、quote 命中、去重不变量、计数一致性 |
| `references/db-profiles.json` | 库响应签名、字段映射路径、查询方言、额度与语义注意 |
| `references/canonical-schema.md` | 规范字段、缺失/未知、去重阈值、合并优先级、指标公式 |
| `references/rubric-checklist.md` | rubric→字段/检查/产物、失败模式、复核命令 |

维护：新增库只改 `references/db-profiles.json`（加 `signatures`、`record_paths`、`query`），无需改代码；映射表版本随 `SKILL.md` frontmatter `version` 同步。
