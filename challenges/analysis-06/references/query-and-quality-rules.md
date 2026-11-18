# 查询生成、脏数据处理与报错修复规则

## 1. 查询生成

所有 SQL 由 schema 卡拼装，标识符一律用双引号转义（`q()`），值一律走参数绑定。

| 查询 | 模板 | 记录字段 |
|-|-|-|
| 分组画像 | `SELECT g AS grp, COUNT(*) n, AVG(v) mean, MIN(v) mn, MAX(v) mx, SUM(v) total FROM t GROUP BY g ORDER BY n DESC LIMIT 20` | `aggregates[]` |
| 条件计数 | `SELECT COUNT(*) n FROM t WHERE col IN (?,?)` | `main_result.filtered[]` |
| 度量摘要 | `SELECT COUNT(v) n, AVG(v) mean, MIN(v) mn, MAX(v) mx FROM t` | `summaries[]` |
| 样本行 | `SELECT * FROM t LIMIT 5` | `sample_rows` |
| 连接记账 | `SELECT (子行数), (父行数), (可匹配子行数)` | `cross_table[]` |
| 膨胀 | `SELECT MAX(n), AVG(n) FROM (SELECT ck, COUNT(*) n FROM child GROUP BY ck)` | `cross_table[]` |
| 跨表聚合 | `SELECT p.dim grp, COUNT(*) n, AVG(c.v) mean FROM child c JOIN parent p ON p.pk=c.ck GROUP BY p.dim` | `join_aggregates[]` |

约束：
- 一律 `mode=ro` 打开，不产生 `INSERT/UPDATE/DELETE/CREATE`（CSV 物化建的是 `/app/work` 下的新库）；
- 每查询保留行数 ≤ `--row-limit`（默认 500），聚合查询 `LIMIT 20`；
- 单库查询条数控制在个位到十几条，日志与结果都可复核而不冗长。

## 2. 筛选值绑定

把指令文本中的字面量与**真实列值**比对：

1. 提取引号串（`"..."`、`'...'`、`“...”`、`‘...’`）与标识符 token；
2. 只在基数 ≤ 60 的非数值列中，做大小写不敏感的**完全相等**匹配（不做模糊匹配、不做子串匹配）；
3. 命中即生成 `col = ?`；
4. **同一列多个取值必须合并为 `IN (?,?)`**——`col='a' AND col='b'` 恒为空集，是最常见的"跑通了但结果不对"；
5. 数值阈值只在"列名 + 40 字符内出现 `> < >= <=` + 数字"时采用；
6. 每条采用的筛选都写进 `assumptions`，让读者知道结果是在哪个子集上算的。

## 3. 脏数据规则

| 问题 | 检测 | 处理 | 报告字段 |
|-|-|-|-|
| 整行重复 | `rows - COUNT(DISTINCT *)` | 去重后再计数；统计结果标注"已去重" | `data_quality.duplicate_rows` |
| 业务键重复 | 忽略主键后 `COUNT(DISTINCT 其余列)` | 提示"主键唯一但业务记录重复" | `duplicate_rows_ignoring_pk` |
| 缺失值 | 每列 `IS NULL` 计数与占比 | 不删除行；均值用 `AVG()`（自动跳过 NULL），并报 `n` 与空值数 | `missing_values` |
| 编码型数值 | 数值 + 基数 2..12 + 非 key | 只做计数/交叉，不做均值 | `coded_fields` |
| 离群值 | 1.5×IQR：`[Q1-1.5IQR, Q3+1.5IQR]` | 保留原值，单独报数量与围栏；不擅自剔除 | `outliers` |
| 类型混用 | `SELECT typeof(col), COUNT(*) GROUP BY 1`（忽略 `null`） | 报混用类型与各自行数，聚合前说明 | `type_mix` |

原则：**不静默修改数据**。所有清洗都体现为"检测 + 报告 + 明确口径"，而不是悄悄删行。

## 4. SQL 报错修复（一次机会）

```
匹配 "no such column: X" / "no such table: X"
  → 在全部表/列中做大小写不敏感查找
  → 命中则替换标识符后重试一次
  → 成功：queries[].sql 记录替换后语句，errors 不记该项
  → 仍失败：errors 记录 "原错误 | retry: 新错误"，继续下一个查询
```

不做的：不做语义猜测式改写（例如把 `mean` 猜成 `avg`），不因一条查询失败中止整库分析。

## 5. 证据规则

| 证据类型 | 必备字段 | 复核方式 |
|-|-|-|
| `sql_aggregation` | `source_path`、`sql`、`quote`、`locator`（sha1 前缀 + 表名） | `verify.py` 在同一快照重跑 SQL，比对首格与 `quote` |
| `query_result` | `source_id`、`locator`（sha1 前缀 + `Q编号;row=1`）、`sql`、`quote`（首行 JSON 片段） | 按 `Q编号` 在 `query_log.json` 找到同一行 |
| 文本（字典条目） | `source_path`、`locator`（`文件名:行号`）、`quote` | 逐字子串命中源文件；不命中即拒收 |

数字与证据一一对应：报告里出现的每个关键数字，都应能追到一条 `evidence` 或一个 `query_id`。

## 6. 状态判定

| 条件 | `status` |
|-|-|
| 至少 1 个聚合成功、无失败查询、无待确认、无 deferred 问题 | `ok` |
| 有聚合或摘要，但存在失败查询 / 待确认 / deferred 问题 / 契约字段为 null | `partial` |
| 有数据但没有任何可用聚合（空表、全是维度、查询全失败） | `insufficient_evidence` |
| 无 case.json、case.json 非法、无可读材料 | `input_error` |

`ok` 是"这次能给的都给了且都验证过"，不是"题目答满了"。任何没做到的项必须出现在 `pending_human` 或 `uncertainty`。
