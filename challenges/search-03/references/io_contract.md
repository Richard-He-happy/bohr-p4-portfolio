# 输入发现与输出契约（search-screen-rank v1.0.0）

## 1. 输入发现（语义识别，不假设键名）

入口：`/input`（可用 `--input` 覆盖）。按顺序：

1. `case.json`；缺失时递归匹配 `case*.json`。读取并原样保留 `case_id` 与 `output_contract`。
2. 范围字段（语义，不固定键名）：`organizer_supplied_scope` / `scope` / `search_scope` / `constraints` / `criteria` 中的
   `topic|research_question|question|objective|title|pico`、`include|inclusion|include_terms|must_have`、
   `exclude|exclusion|exclude_terms|must_not_have`、`year_start|from_year|start_year|since` 与
   `year_end|to_year|end_year|until`、`max_k|top_k|k`、`seed_papers|seeds`。
   任务说明取 `task_instruction|instruction|task|prompt|question|objective|research_question`。
3. 材料扫描：递归全部文件，按扩展名+内容处理
   - `.json`：整份解析；若含 `queries`/`query_log` 键即视为查询日志；其余按记录递归收集。
   - `.jsonl/.ndjson`：逐行解析；文件名含 `quer` 时同时作为查询日志。
   - `.csv`：`DictReader`；文件名含 `quer` 时同时作为查询日志。
   - `.pdf`：只以文件名生成一条低置信记录（`source_db=input_attachment`，标注需人工补题录）。
   - `.xlsx/.docx`：不解析二进制，写入 `degradations` 提示导出 CSV/JSON。
   - `.md/.txt/.yaml`：不参与记录抽取，仅登记。
4. 记录识别：字典同时具备类题名字段与（DOI/摘要/关键词/年份/作者/出处/URL 任一）即为候选记录；支持 Elasticsearch 风格包裹与 `versions/duplicates/records/items/hits` 嵌套。
5. 每条记录保留 `provenance.file` + `provenance.json_pointer`（或 `/filename`），供逐条回查。

材料未提供的对象（如未给 DOI、未给摘要、未给查询日志）一律显式列缺口，不构造。

## 2. 输出文件（写到 `--out`，默认 `/app/output`）

| 文件 | 内容 | 用途 |
|---|---|---|
| `result.json` | 契约全字段 + 分层/排序主结果 + 证据/状态/不确定性 | 主产物，评审与脚本复核入口 |
| `candidates.csv` | 每行一条候选：rank/record_id/tier/decision/relevance/score/题录/DOI/URL/source_db/query_id/retrieved_at/design_fit/reason/flags/evidence_quote | 人工复核表（可直接排序筛选） |
| `query_log.json` | 查询→来源→命中数→关联记录数→保留/待定/排除计数 | 查询可追溯 |

`result.json` 顶层字段：

| 字段 | 含义 |
|---|---|
| `case_id` | 原样回填输入 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `task_instruction`、`scope` | 解析出的问题与检索范围（含年份窗、max_k、纳入/排除文本） |
| `method` | 名称、版本、打分公式、平局规则（与 label_taxonomy.md 一致） |
| `candidates` | 排序后的候选组，每条含 `id/record_id/rank/title/authors/year/venue/doi/url/source_db/query_id/retrieved_at/tier/decision/relevance/relevance_score/relevance_reason/evidence[{quote,locator}]/coverage/design_fit/flags/violations/group_ids/version_count/tie_group/provenance` |
| `top_k` | 短名单 id 列表（长度 = `scope.max_k`） |
| `tiers`、`screening` | 五档计数（include/pending/exclude）+ 去重与覆盖计数：`input_records/groups/merged/with_abstract/missing_abstract_ids` |
| `queries`、`query_log_path` | 查询日志与其可追溯链接 |
| `metrics` | `skill`/`baseline`/`delta`（P@k、nDCG@k）；无标注时 `gold_source=none` 并说明未计算 |
| `conflicts` | 标注冲突、年份冲突、纳排重叠；含涉事 id 与处置规则 |
| `uncertainty`、`pending_human`、`errors`、`degradations` | 诚实状态四件套 |
| `sources`、`runtime`、`changes`、`contract_fill`、`contract_missing` | 来源定位、运行记录、契约回填审计 |

## 3. 契约回填规则

1. 读取 `output_contract`（dict 或 list 均可），逐字段回填；**键名不改、未知字段保留**。
2. 命中同名字段用本 Skill 结果；命中别名（`candidate_list`、`ranked_list`、`shortlist`、`top_k`、`tier_counts`、`screening_result`、`candidates_csv`、`query_log`）用映射值。
3. 无法由材料支撑的字段写 `null`（或按契约声明类型写 `[]`/`{}`/`""`），并记入 `contract_missing`。
4. `contract_fill` 对每个字段记录来源：`filled:same_named_field` / `filled:alias` / `null_no_source`。

## 4. 状态与异常约定

| 情形 | status | 落地位置 |
|---|---|---|
| 正常完成 | `ok` | — |
| 部分材料不可解析、缺摘要、指标不足 | `partial` | `degradations` / `uncertainty` |
| 候选集为空或无可判断记录 | `insufficient_evidence` | `errors` + `uncertainty` + 空 `candidates` |
| case.json 无法解析且无材料 | `input_error` | `errors` |
| 查询 429/权限/接口错误 | 保留在 `queries[].status/error` | 不静默丢弃，不补造命中 |
| 标注/年份冲突 | 该组 `pending` | `conflicts` + `pending_human` |

退出码恒为 0；任何异常写入 `errors` 并保留中断前已落盘的 partial `result.json`。

## 5. 预算与确定性

- 无网络、无第三方依赖、0 次模型请求；典型 9–50 条候选集耗时 < 1 s，远低于 900 s 预算。
- 同一输入重复运行必须得到逐字节一致的 `candidates` 顺序（排序键全确定，无随机、无时间戳参与排序）。
- 不使用当前工作目录：资源以 `Path(__file__).resolve().parent.parent` 定位；输出目录不存在时自动创建。
