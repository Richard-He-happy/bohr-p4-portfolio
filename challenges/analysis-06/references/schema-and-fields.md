# Schema 卡与字段语义判读规则

本文件规定"看到一张表之后怎么判读"，供 `scripts/dbcore.py` 与人工复核共用。

## 1. Schema 卡的采集项

每库：

| 项 | 来源 | 用途 |
|-|-|-|
| `name` / `path` / `bytes` / `sha1` | 文件系统 + 哈希 | 版本定位，证据 locator 前缀 |
| `tables[].rows` | `SELECT COUNT(*)` | 统计基数、膨胀判断的分母 |
| `tables[].columns[]` | `PRAGMA table_info(t)` | 列名、声明类型、是否主键 |
| `columns[].nulls` | `COUNT(*) WHERE col IS NULL` | 缺失率、可用性 |
| `columns[].distinct` | `COUNT(DISTINCT col)` | 区分维度/度量/编码 |
| `columns[].samples` | `SELECT DISTINCT col ... LIMIT 8` | 让读者看到真实取值，不靠猜 |
| `tables[].foreign_keys[]` | `PRAGMA foreign_key_list(t)` | 首选连接路径 |

原则：**先测量再判断**。不根据表名推断列含义，不根据列名推断单位。

## 2. 字段角色四分类

| 角色 | 判定 | 处理方式 | 误用后果 |
|-|-|-|-|
| `key` | 主键或名为 `id`/`*_id` | 只用于连接与去重，不参与聚合 | 对 ID 求均值会产出无意义数字 |
| `dimension` | 非数值、基数 2..30 | 分组维度 | 高基数字符串分组会产生上百行 |
| `measure` | 数值、基数 > 12、非 key | 可 `AVG/MIN/MAX/SUM` | — |
| `code` | 数值、基数 2..12、非 key | 视为枚举：计数与交叉表，**不聚合** | 把 1/2/3 当连续量求均值 |

`code` 的典型例子：`quality_code`（1/2/3 等级）、`class`、`stage`、`flag`。若字典给出码值映射（`1=low, 2=medium, 3=high`），按映射给出可读标签；字典外的码值（例如出现 7）单独列出，不并入已有类别。

## 3. 数据字典接地

材料可能给字典的三种形态：

1. JSON：键名与列名相同（大小写不敏感），值可为字符串或对象（`{"meaning": ..., "values": ...}`）；
2. Markdown/TSV 表：首列为字段名，后续列为含义、取值范围、单位；
3. 放在 `case.json` 内的 `fields`/`dictionary`/`schema` 子结构。

处理规则：
- 只在**列名精确匹配**（大小写不敏感）时接地，不做模糊猜测；
- 字典文本原样保留并记录 `文件名 + 行号 / JSON Pointer`，作为文本证据；
- 字典与观测值冲突时以数据为准，冲突写入 `uncertainty`；
- 无字典条目时，`field_explanations[].caution` 必须写明"角色由类型与取值推断"，不得伪装成权威定义。

## 4. 易混字段的取舍

| 易混对 | 判别 | 报告方式 |
|-|-|-|
| 样本状态 vs 实验状态（两个 code 字段） | 看字典文本；无字典则分别列出取值分布 | `field_explanations` 各自成条，禁止合并 |
| `id` vs 业务编号（如 `sample_no`） | `id` 为主键/外键；业务编号可能是维度或文本 | 业务编号参与分组前先看基数 |
| 同名列出现在两张表 | 各自独立成条，用 `table.column` 限定 | `locator` 必须带表名 |
| 单位不明（`concentration`） | 声明类型无法给单位，查字典；无则标"单位未在材料中说明" | `uncertainty` |

## 5. 连接键推断

按可信度排序，取前 3 条：

1. **声明外键**（`PRAGMA foreign_key_list`）——最高可信。
2. **命名模式**：子表列 `X_id` / `Xid`，父表名 `X` 或 `Xs`，且父表有 `id` 列 → 记为 `name pattern`，属于推断，须在报告中标 basis。
3. **同名列 + 值域包含**（本技能不自动采用，仅在人工复核时考虑）——容易误连，默认不做。

禁止：用同名列（如两表都有 `name`）做隐式连接；用 `SELECT * FROM a, b WHERE ...` 隐式笛卡尔后再过滤计数。

## 6. 膨胀（fan-out）的量化

对每条候选连接 `child(ck) → parent(pk)` 记录：

- `parent_rows`、`child_rows`；
- `child_rows_with_parent`：`EXISTS (SELECT 1 FROM parent p WHERE p.pk = c.ck)`；
- `orphan_child_rows = child_rows - child_rows_with_parent`（连接键在父表缺失，通常是脏数据或未知码）；
- `max_children_per_key = MAX(COUNT(*)) per key`；
- `avg_children_per_key`；
- 结论 `fanout_note`：
  - `max = 1` → "at most one child row per key; join safe for row counts"；
  - `max > 1` → "join fans out up to N rows per key; aggregate the child side before joining"。

据此决定聚合写法：

```sql
-- 安全：先在子表侧聚合，再连接
SELECT p.label, t.n, t.mean
FROM (SELECT ck, COUNT(*) AS n, AVG(v) AS mean FROM child GROUP BY ck) t
JOIN parent p ON p.pk = t.ck;
```

```sql
-- 危险（父表有多条匹配时行数膨胀、均值和被重复加权）
SELECT p.label, COUNT(*), AVG(c.v) FROM child c, parent p WHERE p.pk = c.ck GROUP BY 1;
```

## 7. 输出中的排序与基数控制

- 分组结果按 `COUNT(*) DESC` 排序，最多 20 组；超过 20 组时在 `uncertainty` 记"分组结果被截断"。
- 维度列基数 > 30 时不作为默认分组列（避免整表变成明细）。
- 每库最多 2 个分组列 × 2 个度量列，防止日志与结果膨胀。
