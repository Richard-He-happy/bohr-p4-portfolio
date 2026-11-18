# result.json 契约与字段说明

## 1. 顶层结构

```
result.json
├── case_id, skill{name,version}, status
├── output_contract          # 输入契约原样
├── contract_fill{fields, filled_non_null, null_fields, note}
├── <每个 output_contract 字段>   # 同名字段直接置于顶层，缺值 null
├── main_result{...}         # 主结果
├── queries[]                # 执行日志（可复跑）
├── schema[]                 # schema 卡
├── field_explanations[]     # 字段语义
├── cross_table[]            # 连接与膨胀
├── data_quality{}           # 质检
├── charts[], artifacts[]
├── sources[], evidence[]    # 来源与证据
└── status 之外的诚实性字段：assumptions, uncertainty, pending_human,
    errors, degradations, changes, runtime, question_attempts
```

## 2. 必填 meta 字段

| 字段 | 类型 | 含义 |
|-|-|-|
| `case_id` | str | 案例标识（来自 case 或文件名） |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `sources` | list | `{id,path,name,bytes,sha1}`，输入材料清单 |
| `uncertainty` | list[str] | 已知不确定性与推断边界 |
| `pending_human` | list[str] | 需要人工确认的具体动作 |
| `errors` | list | `{stage, error, ...}`，失败但未中断 |
| `degradations` | list | 降级路径（如 CSV 物化、超时跳过） |
| `changes` | list | `{action, detail}`，运行中发生的写盘/决策 |
| `runtime` | dict | `started_at, seconds, python, sqlite, budget_seconds, row_limit` |

## 3. 契约回填算法

1. 读 `case.json` 的 `output_contract`（列表形式则转换为等键 null 的字典）；字段集合**只增不减**。
2. 分析前先写一份 partial：所有契约字段 = `null`，`status="partial"`。
3. 分析后按字段名语义匹配生成值（顺序即优先级）：

| 字段名包含 | 生成值 |
|-|-|
| `sql` / `quer` / `statement` | `queries[]`（id、purpose、sql、rows、error） |
| `schema` / `table` / `database` / `snapshot` | `schema[]` 概要（库名、sha1、表、行数、列名） |
| `field` / `dictionary` / `semantic` / `explain` / `column` | `field_explanations[]` |
| `join` / `cross` / `relation` / `link` | `{paths, aggregates}` |
| `chart` / `figure` / `plot` / `visual` | `charts[]`（无图表时为 `null`） |
| `quality` / `clean` / `dirty` / `missing` / `duplicate` / `outlier` / `check` | `data_quality{}` |
| `evidence` / `source` / `locator` / `provenance` / `trace` | `evidence[]` |
| `caveat` / `uncertain` / `limit` / `risk` | `uncertainty[]` |
| `assumption` | `assumptions[]` |
| `status_note` / `state` / `status` | `status` 字符串 |
| `question` / `sub_task` | `question_attempts[]` |
| `row_count` / `n_rows` / `count` | 主表行数（int） |
| `code` / `script` / `program` | 入口与校验脚本路径 |
| `conclusion` / `finding` / `answer` / `result` / `output` / `summary` / `analysis` / `stat` / `metric` / `value` | `{primary_table, row_count, aggregates, join_aggregates, summaries, filtered_counts, sample_rows}` |
| `unmapped` / `unknown` / `custom` / `other` / `misc` / `extra` / `tbd` | **不猜，`null`** + 进 `pending_human` |
| 其它 | `null` + 进 `pending_human` |

4. 与 meta 同名的契约字段沿用 meta 值（如契约要求 `status`，就用状态字符串）。
5. `contract_fill.null_fields` 必须等于实际为 null 的契约字段名列表。

## 4. 子结构

`main_result`：

```json
{"primary_table":"wine","n_rows":178,
 "aggregates":[{"table":"wine","group_by":"class","metric":"alcohol",
                "query_id":"Q2","rows":[{"grp":1,"n":59,"mean":13.74,"mn":11.03,"mx":14.83,"total":810.7}]}],
 "summaries":[{"table":"wine","column":"alcohol","query_id":"Q6","stats":{"n":178,"mean":13.0,"mn":11.03,"mx":14.83},"sql":"..."}],
 "join_aggregates":[{"group_by":"cultivar.region","metric":"wine.alcohol","query_id":"Q9","rows":[...],"sql":"..."}],
 "filtered":[{"table":"wine","where":"WHERE \"class\" IN (?,?)","params":[1,2],"n_rows":130,"query_id":"Q5"}],
 "sample_rows":[{"id":1,"alcohol":14.23}]}
```

`cross_table[]`：`{parent_table, parent_key, child_table, child_key, basis, parent_rows, child_rows, child_rows_with_parent, orphan_child_rows, max_children_per_key, avg_children_per_key, fanout_note, query_id, sql}`。

`evidence[]`：

```json
{"id":"E1","claim":"...","kind":"sql_aggregation","source_id":"wine.sqlite",
 "source_path":"/input/wine.sqlite","locator":"<sha1:12>#table=wine;sha1 prefix",
 "sql":"SELECT COUNT(*) FROM \"wine\"","quote":"178"}
```

`question_attempts[]`：`{question, status: answered_from_aggregate|answered_from_join_aggregate|answered_from_cross_table|deferred, query_ids[], answer, limitation}`。

## 5. 状态词表

| 值 | 含义 | 典型触发 |
|-|-|-|
| `ok` | 查询与聚合全部成功，无待确认项 | 正常完成 |
| `partial` | 有可用结果但有明确缺口 | 契约字段为 null、问题 deferred、部分查询失败 |
| `insufficient_evidence` | 数据不足以支撑任何结论 | 空表、只有维度列、查询全失败、无材料 |
| `input_error` | 输入本身不可用 | 无 case.json、JSON 非法 |

四个状态都必须附 `result.json` 与已得产物；**不存在"什么都不写"的分支**。

## 6. 与平台约定的对应

| 平台要求 | 本实现 |
|-|-|
| 回填 `output_contract` 全部字段 | 顶层同名键 + `contract_fill` 覆盖统计 |
| 带 `case_id` | 顶层 `case_id` |
| 诚实 status / sources / uncertainty / changes | 同名顶层字段 |
| 部分结果须说明边界 | `pending_human` + `uncertainty` + `degradations` |
| 不伪造缺失的软件状态或科学数据 | 无数据即 `null`/`insufficient_evidence`，不编数 |
