---
name: traceable-literature-retrieval
description: Offline traceable academic literature retrieval and screening over organizer-provided source records (Crossref items, Europe PMC resultList, publisher dumps, JSONL/JSON workloads, reference graphs, seed lists). Plans multi-facet queries with synonym/acronym/cross-language expansion, unions and de-duplicates records across databases, ranks by IDF-weighted facet coverage with per-item relevance reasons, screens against years/language/exclusion scope, chains citations from seeds, accounts for coverage gaps and writes result.json (full output_contract backfill) plus candidates.csv, candidates.json and query_log.json. Use for literature search, candidate recall, screening, deduplication, citation chasing and evidence logging. Never fabricates papers, DOIs or metadata; empty results, rate limits and missing fields go to uncertainties/missing.
version: 1.0.0
---

# 可追溯学术文献检索 Skill（search-01）

## 1. 用途与边界

对组织方给出的科研案例，在**给定材料上**完成一次真实可复核的文献检索：拆解检索问题 → 规划多轮查询 → 合并去重多来源记录 → 排序与筛选 → 引文追踪 → 覆盖与缺口统计，并把每条候选的来源、查询与时间戳写进结果。

**做**：检索结果集、查询/筛选日志、排序依据、覆盖与遗漏说明、状态与不确定性。
**不做**：单篇论文精读、全文解析、写作润色、资料库整理、**任何联网检索或凭记忆补全文献**。本 Skill 严格离线：只处理 `/input` 下真实存在的响应/记录文件，不联网，不生成不存在的文献、DOI、年份或"最新进展"。

## 2. 运行契约

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/artifacts/**`、`/input/material.json`、`patents/**`、`seed_papers/**` 等（只读，按内容探测，不依赖固定文件名） |
| 输出 | `/app/output/{result.json, candidates.csv, candidates.json, query_log.json}` |
| 入口 | `python3 -B <skill>/scripts/main.py --input /input --output /app/output [--max-k N] [--quiet]` |
| 依赖 | Python ≥3.8 **仅标准库**；无网络；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`） |
| 退出码 | 恒为 0；任何异常都写入 `result.json` 的 `errors[]`/`degradations[]` |
| 预算 | 单进程一次扫描（默认 400 文件、单文件 ≤30MB、JSON 递归深度 ≤14）；`runtime.budget_s=780` |

**先落盘后计算**：脚本第一步就写出合法 partial `result.json`（含 `case_id` 与全部 `output_contract` 键），结尾无条件覆盖为最终结果。

## 3. 输入发现（语义识别，不假设键名）

1. `case.json` → 否则 `case*.json` → 否则任意含 `output_contract` 的 `*.json`；`case_id` 原样透传。
2. 作用域对象：任意层级（≤3）出现 `topic / research_question / question / search_topic / keywords / include / exclude / years / year_from / year_to / language / databases / db / max_k / k / seeds / known_items` 即视为 scope。
3. 递归扫描 `/input/**` 全部文件，按扩展名 + 结构识别：
   - `*.json` / `*.jsonl`：递归遍历，凡"像文献记录的字典"（title + 任一 DOI/year/author/venue/abstract 信号）即为一条记录；`{"message":…}`→Crossref、`{"resultList":…}`→Europe PMC；含 `query` 键的对象记为**源端真实查询**；`{"from","to"}` 记为引用边。
   - `*.md/.txt/.yaml`：抽取引用边与 seed DOI。
   - `*.pdf` / `*.csv` / `*.tsv`：**不解析**，列入 `missing[]` 并说明原因（离线 + 仅标准库）。
4. 材料未给的对象一律列入 `missing[]` / `pending_human[]`，不构造内容。

## 4. 输出契约

- `result.json` **原样回填 `output_contract` 的全部字段**：已知同名键映射到本 Skill 字段；嵌套 dict 递归；未知标量 → `null`；未知列表 → `[]`；另以 `output_contract` 键回显契约原文，键名不改、不丢。
- 核心字段：`candidates[]`、`queries[]`、`screening`、`coverage`、`evaluation`、`citation_chaining`、`sources`、`uncertainty`、`missing`、`errors`、`degradations`、`pending_human`、`changes`、`runtime`、`artifacts`、`self_check`、`status`。
- `status`：`ok`（有记录、契约完整、无缺口）/ `partial`（部分完成或存在缺口）/ `insufficient_evidence`（案例可读但无记录）/ `input_error`（输入完全不可读）。
- 字段级规范见 `references/schema.md`。

## 5. 核心流程

1. 读案例 → 取 `case_id`、`output_contract`、scope → **立即写 partial `result.json`**。
2. 扫描 `/input`：归一化记录（title/authors/year/venue/doi/abstract/keywords/cited_by），带 `source_db`、`query_id`、`retrieved_at`（记录字段 → 信封 → 文件 mtime，并标 `retrieved_at_source`）、`locator`（JSON pointer）。
3. 查询规划：把 `topic` 切成短语，配同义/缩写（`Full Name (ABC)` 双向）/连字符变体/中英词表扩展，生成 `q1 core`、逐 facet 查询、以及**重放源端真实查询**（保留其自报命中数）。
4. 合并去重：DOI 精确 + 标题归一化相似度 ≥0.93（union-find）；保留 `sources[]`、`provenance[]`、合并数 `n_records`。
5. 排序：`0.55×IDF 加权 facet 覆盖 + 0.20×时效 + 0.10×被引 + 0.15×标题命中 −0.03 缺 DOI`（公式见 `schema.md` §3）。
6. 引文追踪：seed DOI 命中 → `route=seed_direct`；引用边邻居 → `citation_chaining`。
7. 筛选：年份窗 / 语言 / 排除词 / 库约束 / 零 facet 命中，逐条写 `excluded_items[].reason`。
8. 统计与落盘：coverage（facet、元数据缺口、seed 命中、recall 估计）、evaluation（P@k、nDCG@k、known-item recall）、`self_check`、四个输出文件。

## 6. 评分点对应

| 评分点 | 字段/检查 |
|-|-|
| 任务完成度 | 契约全字段回填 + `candidates.csv/json` + `query_log.json` + `search_scope` |
| 结果正确性 | 题录逐字来自源记录；`flags[]` 标注缺 DOI/年份/期刊/摘要；`metadata_gaps` 计数 |
| 结果完整性 | `coverage.facet_coverage`、`uncovered_facets`、`recall_estimate`、`missing[]` |
| 结果可核验性 | 每条候选 `provenance[]`（库+query_id+retrieved_at+文件+pointer）+ `evidence_snippet` + `query_log.json`（每步含 `db/filters/hits/status/retrieved_at`）；无源端查询时置 `query_id=null` 并加 `missing_query_id` flag |
| 质量/创新 | 多库合并、跨库去重、术语扩展、facet 加权排序、引文追踪、覆盖缺口 |
| 增益可验证 | `evaluation` 只给"可复算"的自评指标与标签规则，声明官方白板为准，不冒充白板 |
| 可靠体验 | `--help`、无参数默认 `/input`→`/app/output`、异常分支表（§10）、`self_check` |
| 生态贡献 | 本文档 + `references/{schema,terms,checklist}.md`；词表可编辑、`engine.py` 可 import |

## 7. 证据与定位规范

- 每条候选必须有：`sources[]`（≥1 个库）、`query_id`（源端真实查询 id，缺失即 `null` 并记 `missing_retrieved_at` 等 flag）、`retrieved_at`、`provenance[].locator`（如 `/1/message/items/3`）。
- `evidence_snippet` 是**从该记录 abstract 中逐字截取的句子**（无 abstract 时取标题），不是生成文本。
- 不得改写标题/作者/DOI 以"修正"来源；冲突原样保留并加 flag。

## 8. 冲突与人工确认

| 情形 | 处理 |
|-|-|
| 同一条记录年份不一致 | 保留两值 → `conflict_year` → 候选 flag `year_conflict` |
| seed 不在材料中 | `citation_chaining.seeds_missing` + `missing[]` + `pending_human` |
| 案例无 `output_contract` | `pending_human` 提示补齐后重跑 |
| 全被筛掉 | `screening.excluded_items[].reason` 逐条说明；`pending_human` 询问是否需要联网检索 |

## 9. 预算与断点

单进程、单遍扫描，无网络调用；`runtime` 记录 `elapsed_s`、`budget_s`、`python`、`network_used=false`。任何阶段异常只影响该阶段（`errors[]` 标 `stage`），不影响已写出的 partial 结果。

## 10. 异常降级分支

| 分支 | 行为 | 结果字段 |
|-|-|-|
| 输入目录不存在 / 为空 | 直接 finalize | `status=input_error`，`errors[]`，`pending_human[]` |
| `case.json` 坏 JSON | 记录后继续扫描其他文件 | `errors[stage=case_json]`，`status=insufficient_evidence` |
| 无任何记录 | 输出空候选并说明 | `status=insufficient_evidence`，`missing[]`，`pending_human[]` |
| 单条记录字段缺失 | 不补造，只标 flag | `flags[]`、`coverage.metadata_gaps` |
| PDF/CSV 材料 | 不解析 | `missing[].reason` |
| 记录解析异常 | 跳过该记录 | `errors[stage=scan/record_normalize]` |
| 限流/权限（离线不联网） | 声明从未发起网络请求 | `degradations[]`、`uncertainty[]` |

## 11. 自检清单

- [ ] `python3 -B scripts/main.py --help` 退出码 0。
- [ ] 有输入时 `result.json` 合法，`self_check` 四项皆 true，`output_contract` 键全部存在。
- [ ] 每条候选都有 `sources`、`relevance_reason`、`retrieved_at`（或显式 flag）。
- [ ] `candidates.csv` 行数 == `candidates[]` 长度。
- [ ] 空输入 / 坏 JSON：仍生成合法 partial `result.json`，退出码 0。
- [ ] 包内无 `__pycache__`、`.pyc`、临时文件、`*.part`。

## 12. 最小调用示例（**示例，非正式案例结果**）

```bash
# /input: case.json（含 output_contract 与 scope）+ artifacts/crossref_response.json 等
python3 -B scripts/main.py --input /input --output /app/output
```

示意输出（**示例数据，不是任何正式案例的结果**）：

```json
{"case_id": "demo-min-001", "status": "ok",
 "candidates": [{"id": "c001", "rank": 1, "year": 2021, "venue": "Nature",
                 "doi": "10.1038/s41586-021-03380-y", "url": "https://doi.org/10.1038/s41586-021-03380-y",
                 "source_db": "Crossref",
                 "sources": ["Crossref", "EuropePMC"], "query_id": "src_...",
                 "retrieved_at": "2026-11-18T12:40:00+00:00",
                 "relevance_score": 87.3, "flags": [],
                 "relevance_reason": "1/1 facets [research_problem]; terms: …; route=seed_direct; 2 record(s)"}],
 "coverage": {"k_returned": 2, "n_records_read": 6, "n_unique": 4, "n_duplicates_merged": 2, "uncovered_facets": ["methods"], "recall_estimate": 1.0},
 "evaluation": {"p_at_k": 1.0, "ndcg_at_k": 1.0, "known_item_recall": 1.0}}
```

## 13. 文件清单与版本

```
SKILL.md                 本文件（用途/契约/流程/异常/自检）
scripts/main.py          CLI：案例解析、查询规划、装配、契约回填、输出、self_check
scripts/engine.py        解析层：扫描、记录归一化、去重、排序、筛选、词表加载（可 import）
references/schema.md     输入发现 + 字段规范 + 排序公式
references/terms.md      可编辑 facet 词表 + 中英对照（仅此处扩展词汇）
references/checklist.md  评分点映射、自检命令、失败模式、维护说明
```

版本 1.0.0（2026-11）；Python ≥3.8；无第三方依赖；无网络。

## 14. 维护说明

- 中文/专利记录：Han 词按子串匹配（`\b` 在汉字串内不成立），无 DOI 的专利保留并标 `missing_doi`，不会把专利号写进 `doi`。
- 扩充同义词/中文词：只改 `references/terms.md`（`label | term; term` 与 `cn2en | 中文=english`）。
- 改排序权重：改 `engine.rank` 并同步 `schema.md` §3。
- 任何改动后重跑三组冒烟测试：最小案例、空目录、坏 JSON。
- 已知限制：不解析 PDF/CSV；不做动词/词形还原（只做单复数与连字符变体）；不联网，故 recall 仅能就材料内 seed 估计。
