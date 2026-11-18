# 最小调用示例（示例，非正式案例结果）

> **本文件全部数字来自一次本地演示运行，用于说明接口与输出格式；不是平台固定案例的答案，也不能当作正式结果引用。**

## 1. 输入

`/input/case.json`（示例）：

```json
{"case_id":"demo-01","topic":"analysis-02",
 "output_contract":{"descriptive":null,"hypothesis_tests":null,"effect_sizes":null,
   "confidence_intervals":null,"cleaning":null,"interpretation":null,
   "sources":null,"uncertainty":null,"pending_human":null,"tables":null,"dataset":null},
 "primary_key":["sample_id"],"group":"group","files":["data.csv"]}
```

`/input/data.csv`（演示用合成数据，A/B 两组各 30 行，含 2 行缺失、离群值、带 `%` 的字符串、2 行重复）：

```
sample_id,group,value_mg,pct_value,weight
id6500,A,10.42,11.5%,48.3
...
```

## 2. 调用

```bash
python3 scripts/main.py --input /input --output /app/output
# 输出：result.json, analysis.md, cleaned.csv, tables/descriptive.csv,
#       tables/tests.csv, tables/correlation.csv, run.log
# run.log 实得一行（示例）：
# case_id=demo-01 status=ok file=.../data.csv raw=60 kept=58 dropped=2 errors=0 pending=1
```

退出码 0；分析开始前已写入 partial `result.json`。

## 3. 示意输出（示例，非正式案例结果）

`result.json` 关键字段：

```json
{"case_id":"demo-01","status":"ok",
 "cleaning":{"key":["sample_id"],
  "rows":{"raw":60,"kept":58,"dropped":2},
  "issues":[{"rule":"M-01","field":"*","issue":"missing_cell","count":0},
            {"rule":"O-01","field":"value_mg","issue":"outlier_tukey_1.5iqr","count":2},
            {"rule":"N-01","field":"pct_value","issue":"numeric_format_repaired","count":11},
            {"rule":"O-01","field":"weight","issue":"outlier_tukey_1.5iqr","count":1},
            {"rule":"D-01","field":"*","issue":"duplicate_key_row","count":2}]},
 "runtime":{"checks":{"n_accounting":true,"ci_p_consistency":true,
   "contract_keys_present":true},"python":"3.12.4","seed":2000,
   "finished_utc":"2026-01-01T00:00:00+00:00"}}
```

`tables/tests.csv` 中三行比较（数值与 `analysis.md` 完全一致，同一 dict 渲染）：

| id | method_id | statistic | df | p_value | 效应量 | 效应 CI | 点估计 | 点估计 95% CI | 判定 |
|-|-|-|-|-|-|-|-|-|-|
| `value_mg:A~B` | mannwhitney | U=238.0 | – | 0.004738 | rank-biserial r=−0.433 | 不可得 | 中位数差 −1.465 | [−3.810, −0.355] | significant |
| `pct_value:A~B` | t_student | t=−2.4602 | 56 | 0.01700 | Hedges g=−0.638 | [−1.147, −0.117] | 均值差 −1.768 | [−3.208, −0.328] | significant |
| `weight:A~B` | t_student | t=−1.7717 | 56 | 0.08189 | Hedges g=−0.459 | [−0.974, 0.056] | 均值差 −3.247 | [−6.918, 0.424] | not_significant |

方法选择可复核：`value_mg` 的正态性被拒绝且某组 n<30 → 秩检验；`pct_value`/`weight` 正态且方差齐 → 合并方差 t。

`analysis.md` 第 1 节对应的一句话（原文）：

> value_mg (A vs B)：Mann-Whitney U test，U=238.000，df=-，p=0.0047 → 差异有统计学意义。点估计 median1 - median2 = -1.465（95% CI -3.810 至 -0.355）；效应量 rank-biserial r = -0.433，按惯例属中效应。

同一次运行里 `weight` 的 p=0.0819、区间跨 0，被写成“差异无统计学意义”，而不是“证明无差异”——区间上限 0.424 仍容许小幅差异，`uncertainty` 里另有 6 条限制说明。

`tables/descriptive.csv`（节选）：

| variable | n | mean | sd | median | mean CI |
|-|-|-|-|-|-|
| value_mg | 58 | 13.1624 | 8.9001 | 11.845 | [10.8223, 15.5026] |
| pct_value | 58 | 12.8103 | 2.8541 | 12.500 | [12.0599, 13.5608] |
| weight | 58 | 50.9207 | 7.1036 | 51.450 | [49.0529, 52.7885] |

## 4. 复算方式

1. `cleaned.csv` 有 58 行（60 − 2 重复），列名与原件一致；
2. 取 `cleaned.csv` 的 `value_mg` 按 `group` 分组，得到 A/B 两组，做 Mann–Whitney U（正态近似 + 连续性 + 结校正）应得 U=238.0、p=0.0047；
3. `pct_value`/`weight` 做合并方差 t 检验应得 df=56 与上表的 t 值；
4. Hedges g 与 CI 按 `references/method_rules.md` 第 3 节公式计算；
5. 全部 p、（效应量）区间、行号都能在 `result.json`、`tables/*.csv`、`run.log` 中对上。

## 5. 该示例同时演示的失败处理

- `pending_human`：`确认重复主键应合并、保留还是剔除: *`（D-01 触发，没有静默合并）；
- 若把 `data.csv` 删掉只留 `case.json` → `status="input_error"`，`errors[0].stage="read"`，仍写出合法 `result.json`；
- 若 `case.json` 是坏 JSON → 继续按目录扫描，`errors` 记录解析失败，数据表照常分析；
- 若工作区只给了 `.xlsx` → `degradations` 记录“xlsx 需外部解析器，仅标准库已跳过”，不透支信任去解析未知二进制。
