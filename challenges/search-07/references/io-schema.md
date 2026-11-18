# 输入发现、契约回填与产物字段

## 1 输入发现规则（不假设键名）

| 步骤 | 行为 | 代码位置 |
|-|-|-|
| 1 | 读 `/input/case.json`；缺失则取任意 `case*.json`（记 `degradations`）；不可解析 → `errors` | `main.py` 阶段 A |
| 2 | `output_contract` 原样保留；`case_id` 原样保留 | 同上 |
| 3 | 抽取 scope：`organizer_supplied_scope`/`scope`/`search_scope`/`constraints` 下的 topic、databases、years、language、max_k、include/exclude、seeds | 同上 |
| 4 | 递归扫描 `/input/**`，按扩展名分发：`.json`（含嵌套）、`.jsonl`、`.csv/.tsv`、`.pdf` | `verify.py: disc/load/walk` |
| 5 | 每个"列表结构"按路径名 + 字段名打分，分为参考集 / 记录池 / 查询日志；引文边单独收集 | `verify.py: sc/rset` |

键名匹配是大小写与标点无关的（`nlp_key`），因此 `queryId`、`query_id`、`Query ID` 等价。

### 结构打分（路径与字段证据）

- 参考集：路径/文件名含 `reference / refs / seed / included / known / gold / relevant / expected / benchmark / must_find`（文件名命中权重更高），或项含 `include/relevant/decision` 等决策字段。
- 记录池：路径含 `response / result / hit / record / retriev / pool / candidate / import / crossref / europepmc / epmc / publisher`，或项含 `query_id / retrieved_at / source_db / database`；**且**至少一项有 title/doi（否则是查询日志而不是记录）。
- 查询日志：路径含 `quer/strateg/log`，或项同时含查询串（`query/query_string/q/...`）与计数（`hits/count/total/n_results`）。
- 引文图：项含 `citing/cited/from/to/source/target` 之二。

## 2 输出契约回填

1. 读取 `output_contract`（dict 或 list 两种形态都支持）。
2. 对每个键：先按归一化名精确匹配内部分区（`SD` 列表），再退化到包含匹配；命中则取值，否则 `unfilled`。
3. 按契约声明的类型强制转换：`number` 取对象内的标量（coverage/value/rate/count/n_hit/score/total）或列表长度；`array` 包一层；`string` 取字符串或标量文本；`object` 原样。
4. **键名不改、未知键保留**；`contract_fill[键] = {from, type}` 记录来源与转换，供复核。
5. `case_id` 从 case 读写回顶层，不变。

## 3 `result.json` 顶层结构

| 键 | 内容 |
|-|-|
| `case_id` / `status` / `skill` / `skill_version` | 标识与状态（`ok/partial/insufficient_evidence/input_error`） |
| `sources` / `input_manifest` | 输入文件清单（路径、字节、结构数） |
| `scope` | topic / databases / years / language / max_k / include / exclude / seeds |
| `reference_set` | sources、n_items_raw、n_unique、n_eligible、n_excluded、excluded[]、dedupe[]、dedupe_rule、frozen_at、reporting_policy |
| `retrieval_pool` | n_records_raw、n_records、n_queries、sources[]、missing_retrieved_at、n_citation_edges |
| `coverage` | denominator、n_eligible、n_hit、n_miss、coverage、miss_rate、coverage_over_all_refs、wilson95、formula |
| `miss_taxonomy` | order[]、classes[]{code,label,n,share_of_miss,example_ref_ids,repair,definition,evidence_required}、primary_counts、note |
| `hit_matrix` | 同 `hit_matrix.csv` 的行 |
| `candidates` | rank,rid,title,authors,year,venue,doi,url,source_db,retrieved_at,query_id,ref_link,relevance_score,relevance_reason,provenance |
| `queries` | query_id,db,raw,fields,hits,records_retained,year_from,year_to,status,error,path,n_tokens |
| `supplement` | rounds[]、coverage_before、coverage_after_offline、measured_gain_hits、reachable_not_counted、predicted_catch_total、stop_rule、residual_misses、residual_by_cause |
| `baseline_comparison` | baseline_exact_title_doi_only、baseline_circular_denominator、skill_coverage、skill_coverage_after_offline、delta_vs_exact_only、misses_baseline、misses_skill、note |
| `metrics` | n_pool、n_query、dedupe_removed、missing_retrieved_at、doi_in_pool、doi_format_ok_rate、P@10/20/50、note |
| `limits` / `uncertainty` / `pending_human` / `errors` / `degradations` / `changes` / `runtime` | 诚实性字段 |

## 4 `hit_matrix.csv`（主台账，逐条参考记录一行）

| 列 | 说明 |
|-|-|
| `ref_id` | R001… （去重后的稳定编号；被去重掉的记录出现在 `reference_set.dedupe`） |
| `title` `year` `doi` | 参考记录元数据（原样，不做美化） |
| `status` | `hit` / `hit_recovered`（R1 后）/ `miss` / `excluded` |
| `match_tier` `match_score` | 命中层级与分数 |
| `matched_rid` `matched_source` `matched_query_id` | 命中的池记录与来源、查询 |
| `cause_primary` | 主因代码（`miss` 必有） |
| `causes_all` | 全部支持原因（JSON 数组） |
| `evidence_locator` | 复核定位：文件#记录号 + query_id + retrieved_at，或 `hit_matrix R00x cause=... {证据}` |
| `repair` | 可执行修复动作 |

## 5 `candidates.csv`（候选文献主产物）

`rank,rid,title,authors,year,venue,doi,url,source_db,retrieved_at,query_id,ref_link,relevance_score,relevance_reason`
每条都带来源（`source_db` 或 `raw_path`）与检索定位（`query_id`/`retrieved_at`），无编造字段。

## 6 `query_log.json`

`{"queries": [...], "note": "..."}`，每条含查询原文、字段、报告命中数、保留记录数、时间窗、状态、错误、来源文件。若输入无日志，生成 1 条合成条目并把 `raw` 置 null，同时写 `degradations`。

## 7 `supplement_plan.json`

三轮结构：R1 对齐（`targets`、`new_ref_ids`、`rule`）；R2 引文路由（`reachable_ref_ids`、`rule`）；R3 查询修复（`specs[]`：cause、query_id、repair、added_terms、window、execution 级别、predicted_catch、prediction_basis）。外加 `coverage_before/after`、`measured_gain_*`、`stop_rule`、`residual_*`。

## 8 `verify.py` 的 14 项确定性检查

`contract_fields`（契约键齐全）、`case_id_echo`、`hit_matrix`（存在）、`row_partition`（行数=命中+漏检+排除）、`denominator`（n_eligible=n_hit+n_miss）、`coverage`（用 CSV 重算并比对，容差 2e-4）、`miss_has_cause`、`miss_has_repair`、`hit_has_locator`、`cause_in_taxonomy`、`candidate_trace`、`doi_format`、`supplement_rounds`、`offline`（未声称联网）。
结果写 `verify_report.json`，CLI 打印 `{"ok":…,"n_checks":…,"failed":[…]}`，退出码 0。

## 9 异常对照表

| 输入状况 | 输出表现 |
|-|-|
| `/input` 为空或不存在 | `status=insufficient_evidence`，`reference_set.n_eligible=0`，`coverage=null`，`limits` 说明 |
| `case.json` 损坏 | `status=input_error`，`errors[stage=case]`，其余结构照常解析 |
| 只有参考集没有记录池 | 全部 eligible → `miss` + C11，`status=partial` |
| 只有记录池没有参考集 | 只输出候选表与输入清单，`coverage=null` |
| 撤稿记录 | `status=excluded`、`cause_primary=C10`、`reference_set.excluded`，不进分子分母 |
| 同一论文多库重复 | 合并为一条，`provenance` 记录全部 (query_id, source, retrieved_at) |
| 缺 `retrieved_at` | 保留，`metrics.missing_retrieved_at` 计数 |
| 缺 DOI | `anomaly=missing_doi`，模糊层级仍可命中，同时作为 C10 的旁证 |
| DOI 大小写/前缀不一致 | 归一化后视为相同 DOI（`exact_doi`） |
| 参考集仅来自 PDF | `reference_set.sources[].derived=pdf_doi_scan`，提示覆盖不完整 |

## 10 最小示例（**示例，非正式案例结果**）

`/input/case.json`：

```json
{"case_id": "demo-y",
 "organizer_supplied_scope": {"topic": "SGLT2 inhibitors and heart failure", "years": [2016, 2021]},
 "output_contract": {"coverage": {"type": "object"}, "missed_studies": {"type": "array"}}}
```

调用与示意输出：

```bash
python3 -B scripts/main.py --input /input --output /app/output
# [skill] status=ok coverage=0.6 hits=3/5 misses=2 rounds=3
```

```json
{"case_id": "demo-y", "status": "ok",
 "coverage": {"n_eligible": 5, "n_hit": 3, "coverage": 0.6,
              "wilson95": [0.23, 0.88], "denominator": "reference_set.n_eligible"},
 "missed_studies": [{"ref_id": "R002", "cause_primary": "C06", "causes_all": ["C06", "C09"]},
                    {"ref_id": "R003", "cause_primary": "C06", "causes_all": ["C06", "C10"]}],
 "supplement": {"coverage_before": 0.6, "coverage_after_offline": 0.6, "measured_gain_hits": 0,
                "reachable_not_counted": 1}}
```

该数值仅用于说明接口形态，不代表任何正式案例的结果。
