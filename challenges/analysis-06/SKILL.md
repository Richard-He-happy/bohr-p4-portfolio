---
name: science-db-query-analysis
description: >-
  面向科研数据库快照（SQLite，或可物化为 SQLite 的 CSV 材料）的可复核查询与分析技能：
  发现库表与数据字典，生成并执行只读 SQL，把题目中的字面筛选值绑定到真实列值，
  推断并实测跨表连接与一对多膨胀，标注缺失/重复/异常/编码型字段，最后把结果、SQL、
  行数与逐条定位证据写入 result.json，并原样回填全部 output_contract 字段。
  适用于"科研数据库查询与分析"类的字段解释、结果抽取与跨表结论任务；
  不适用于需要联网、写库、或没有可读数据材料的任务。
version: 1.0.0
---

# 科研数据库查询与分析（science-db-query-analysis）

## 1. 用途与边界

**用途**：给定一个案例目录（`case.json` + 数据快照 + 可能的字段字典），完成一次可复跑的查询分析，产出结构化结果与可核验证据。

**适用**：
- 数据在本地 SQLite 文件（`.db/.sqlite/.sqlite3`）或 CSV/TSV 材料中，可以只读访问；
- 问题涉及计数、分组均值/极值、条件筛选、字段含义解释、跨表关联与行数膨胀判断；
- 需要留下"数字 → SQL → 快照版本 → 行数"的可复核链条。

**不适用**（遇到时如实降级，不要伪造）：
- 需要连接远程数据库、需要账号口令、需要写库或建表授权——本技能只做 `mode=ro` 只读访问；
- 需要联网检索或下载数据；
- 数据以扫描图片/无文本 PDF 形式给出且没有可解析表格（本技能不做 OCR）；
- 题目要求的指标在材料中无对应列，且无数据字典可推断（写入 `pending_human`）。

## 2. 运行契约

| 项 | 约定 |
|-|-|
| 入口 | `python3 scripts/main.py`（`--help` 可用，退出码 0） |
| 输入 | `/input/case.json` 与 `/input/task.md`，材料在同目录或子目录 |
| 工作目录 | `/app/work`（CSV 物化快照、临时文件） |
| 产物 | `/app/output/result.json` 及 `queries.sql`、`query_log.json`、`schema_card.json`、聚合 CSV、`chart_*.svg` |
| 路径覆盖 | 依次取 `--input/--output/--work`，再取 `SKILL_INPUT_DIR/SKILL_OUTPUT_DIR/SKILL_WORK_DIR`，最后用上述默认值；脚本不依赖当前工作目录 |
| 依赖 | 仅 Python 标准库（`sqlite3`、`json`、`csv`、`re`…），不联网，不装包 |
| 退出码 | **恒为 0**（含空输入、坏 JSON、查询报错、超时） |
| 写盘顺序 | 先写 partial `result.json`（契约字段置 null），分析后无条件覆盖 finalize |
| 只读保证 | 输入库以 `file:...?mode=ro` 打开；CSV 物化只写 `/app/work` 下的新文件 |

## 3. 输入发现（语义识别，不假设键名）

1. `discover()` 递归扫描输入目录；`case.json`（或任意 `case*.json`）为主控，缺失时继续运行并在 `errors` 记 `case.json not found`。
2. 数据库识别用**文件头魔数** `SQLite format 3\0`，不靠扩展名或材料标签；CSV/TSV 按扩展名识别；JSON/MD/TXT 作为字典与说明材料。
3. `case_id` 取 `case_id`/`id`，否则取 case 文件名。
4. 指令文本取语义键（`task_instruction`、`instruction`、`question*`、`requirement*`、`goal`、`scope`、`workorder`、`description`），键名不固定；`output_contract` 原样保留。
5. 子问题从 `questions`/`tasks`/`requirement*` 等任意嵌套位置收集（≤6 条）。
6. 材料清单不做内容假设：未在 `/input` 出现的对象在 `pending_human` 中列为缺口，不构造数据。

## 4. 输出契约

`result.json` 顶层=**meta 字段 + `output_contract` 的全部字段（原样键名）**：

| 分组 | 字段 |
|-|-|
| 标识 | `case_id`、`skill{name,version}`、`status` |
| 契约 | `output_contract`（原样）、`contract_fill{fields,filled_non_null,null_fields,note}`、以及每个契约字段同名字段 |
| 结果 | `main_result{primary_table,n_rows,aggregates,join_aggregates,filtered,summaries,sample_rows}`、`queries[]`、`schema[]`、`field_explanations[]`、`cross_table[]`、`data_quality{}`、`charts[]` |
| 证据 | `sources[]`（路径/字节/sha1）、`evidence[]`（claim/kind/source_path/locator/sql/quote） |
| 诚实性 | `status`、`assumptions[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime{}`、`question_attempts[]` |

契约回填规则：
- 契约字段**不改名、不删减**；无法生成的值写 `null` 并进入 `pending_human`，同时记入 `contract_fill.null_fields`。
- 字段名与语义表匹配（SQL/表结构/字段/连接/图表/质量/证据/结论/状态/问题…）；名字里含 `unmapped`、`unknown`、`custom`、`other`、`misc`、`extra`、`tbd` 的字段一律不猜，保留 `null`。
- 与 meta 同名的契约字段（`status`、`errors`…）沿用 meta 值，不覆盖结构。

## 5. 核心流程

1. **落盘**：解析前先写 partial `result.json`。
2. **发现**：扫描材料、读 case、保留契约。
3. **建卡**：每库每表取行列数、`PRAGMA table_info`、`foreign_key_list`、每列空值数/不同值数/样例值 → `schema_card.json`。
4. **接地**：把材料中的 JSON/MD 表格中能对上列名的条目映射为字段说明（`field_explanations.dictionary` + locator）。
5. **绑定筛选**：把指令中的字面量（引号串、标识符）与真实列值精确匹配；同一列多值用 `IN`，不拼成互相矛盾的 `=`。
6. **查询**：单表分组画像（分组列×度量列，`COUNT/AVG/MIN/MAX/SUM`）、条件计数、主表度量摘要、样本行；全部登记进 `query_log.json` 并导出 `queries.sql`。
7. **跨表**：声明外键优先，其次 `<parent>_id` 命名推断；实测父/子行数、可匹配子行数、孤儿行、每键最大子行数 → 给出膨胀结论；父表维度×子表度量再做一个 join 聚合。
8. **质检**：整行重复、忽略主键后的业务重复、空值率、1.5×IQR 离群、编码型字段（低基数字段不参与求均值）、类型混用。
9. **图表**：用首个可用聚合渲染 SVG 柱图（文本源文件，可直接改）。
10. **finalize**：回填契约、汇总计数、判定 `status`、写 `result.json`；`verify.py` 做确定性复核。

## 6. 任务质量规则（rubric → 字段/检查/产物）

| 评分关注 | 本技能的落实 | 落点字段/产物 |
|-|-|-|
| 真的连上并取回结果 | `mode=ro` 打开真实快照，SQL 由 schema 生成并实际执行 | `queries[]`、`query_log.json`、`queries.sql` |
| 数值站得住 | 聚合粒度=分组列；连接前先测膨胀；编码字段不求均值 | `aggregates[]`、`cross_table[].fanout_note`、`data_quality.coded_fields` |
| 字段口径说得清 | 字典接地 + 角色标注（key/dimension/measure/code）+ 样例值 | `field_explanations[]` |
| 覆盖度与缺口 | 契约逐字段回填，未覆盖写入 `null_fields`/`pending_human` | `contract_fill`、`pending_human[]` |
| 可复跑 | 快照 sha1、SQL 文本、行数、每条证据的 locator | `sources[]`、`evidence[]`、`runtime{}` |
| 异常处理 | 查询报错自动修复一次并记录；失败进 `errors` 不静默 | `errors[]`、`degradations[]` |
| 不虚报 | 未映射的全局结论标 `partial`/`insufficient_evidence` | `status`、`uncertainty[]` |

## 7. 证据与定位规范

每条 `evidence` 必须可复核：

```json
{"id":"E1","claim":"table wine holds 178 rows in snapshot wine.sqlite",
 "kind":"sql_aggregation","source_id":"wine.sqlite","source_path":"/input/wine.sqlite",
 "locator":"<sha1前12位>#table=wine;sha1 prefix",
 "sql":"SELECT COUNT(*) FROM \"wine\"","quote":"178"}
```

- `kind="sql_aggregation"`：`quote` 是 SQL 结果首格的字面值，`verify.py` 会用同一 `sql` 在同一 `source_path` 上**重跑比对**，不一致即判失败。
- `kind="query_result"`：`locator` 指向 `sha1前缀#Q编号;row=1`，`quote` 为该行 JSON 片段，`sql` 给出可复算语句。
- 文本类证据（`kind="dictionary_entry"`）：`quote` 是字典行的**逐字原文**，`locator=文件名:line:N`；`verify.py` 做子串校验，找不到即拒收，绝不改原文凑引用。
- 禁止无 locator 的数字、禁止手改结果表、禁止把示例写成正式案例结果。

## 8. 冲突、缺口与人工确认

- 同一列出现互相矛盾的筛选值 → 合并为 `IN`，并在 `assumptions` 说明依据。
- 字典与观测值冲突（字典说 1/2/3，数据出现 7）→ 以数据为准做统计，`uncertainty` 记"未知码值未归入任何类别"。
- 指标列缺失、口径不明、需要业务定义 → `pending_human` 写明"需要确认什么"，不猜。
- 问题无法自动映射到列 → `question_attempts[].status="deferred"`，`status` 降为 `partial`。

## 9. 预算与断点

- 单次分析默认软截止 `--max-seconds 660`（总预算 900s 内留余量）；到点即停止新查询并 finalize，`degradations` 记"deadline reached"。
- 每查询最多保留 `--row-limit` 行（默认 500）；聚合查询自带 `LIMIT 20`。
- 任何阶段异常都已被捕获，最终结果总是合法 JSON，退出码 0。

## 10. 异常与降级分支表

| 情况 | 处置 | 记录位置 |
|-|-|-|
| 无 `case.json` | 仍分析材料，状态 `input_error` | `errors[].stage=discover` |
| `case.json` 非法 JSON | 状态 `input_error`，继续分析材料 | `errors[].stage=case_json` |
| 无数据库文件，只有 CSV | 物化到 `/app/work/snapshot.sqlite` 再分析 | `degradations[]`、`sources[]` |
| 库文件损坏/无法只读打开 | 跳过该库，其余继续 | `errors[].stage=connect` |
| SQL 报 `no such column/table` | 大小写不敏感匹配后重试一次 | `queries[].sql` 已替换 + `errors` 无该项 |
| 查询返回 0 行 | 保留空结果并说明筛选条件 | `main_result.filtered[].n_rows=0` |
| 表为空（0 行） | 不做统计，`insufficient_evidence` | `schema[].rows=0` |
| 契约字段无生成器 | 置 `null` + 待确认 | `contract_fill.null_fields`、`pending_human` |
| 超时 | 停止新查询，保留已得结果 | `degradations[]` |

## 11. 自检清单

```bash
python3 -B scripts/main.py --help                       # 退出码 0
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
python3 -B scripts/verify.py --result /app/output/result.json
```

`verify.py` 的确定性检查（任一失败即 `verdict=fail`）：契约字段齐全、meta 字段齐全、`status` 合法、聚合/连接引用的 `query_id` 都能在日志里找到且行数一致、`sql_aggregation` 证据重跑复现、文本 quote 逐字命中、产物存在且非空。

人工复核（3 条）：
1. `queries.sql` 里的语句能否在 `sources[]` 记录的同一快照上直接跑通；
2. `cross_table[].max_children_per_key>1` 时，聚合是否已在子表侧完成；
3. `status` 与 `pending_human` 是否覆盖了所有没做到的项。

## 12. 最小调用示例（示例，非正式案例结果）

输入（示例）：

```json
{"case_id":"demo-001",
 "task_instruction":"统计 wine 表按 quality_code 分组的 alcohol 均值，并说明 cultivar_id 关联 cultivar.id 是否膨胀",
 "output_contract":{"answer":"object","sql_used":"list","join_check":"object",
                    "data_quality":"object","evidence":"list","chart":"path"}}
```

调用与示意输出（数字仅示意，来自一个自造 3 表小样例，不代表任何正式案例）：

```bash
SKILL_INPUT_DIR=/tmp/demo/in SKILL_OUTPUT_DIR=/tmp/demo/out python3 scripts/main.py
# science-db-query-analysis 1.0.0 | case=demo-001 status=ok queries=12 filled=6/6
```

```json
{"status":"ok",
 "answer":{"primary_table":"wine","row_count":62,
           "aggregates":[{"group_by":"quality_code","metric":"alcohol","query_id":"Q1",
                          "rows":[{"grp":1,"n":18,"mean":13.02}]}],
           "join_aggregates":[{"group_by":"cultivar.region","metric":"wine.alcohol",
                               "rows":[{"grp":"north","n":47,"mean":13.37}]}]},
 "join_check":{"paths":[{"child_table":"wine","child_key":"cultivar_id",
                          "max_children_per_key":26,"orphan_child_rows":7}]},
 "chart":[{"kind":"bar_svg","path":"/tmp/demo/out/chart_group_counts.svg"}]}
```

## 13. 文件清单与版本

| 文件 | 作用 | 版本 |
|-|-|-|
| `SKILL.md` | 用途、契约、流程、规则、自检 | 1.0.0 |
| `scripts/main.py` | 入口：发现→建卡→查询→跨表→质检→回填契约→写 `result.json` | 1.0.0 |
| `scripts/contractmap.py` | `output_contract` 字段语义映射与原子写盘 | 1.0.0 |
| `scripts/dbcore.py` | 材料发现、字典接地、schema 卡、只读执行与报错修复、CSV 物化 | 1.0.0 |
| `scripts/dbanalysis.py` | 筛选绑定、连接推断与膨胀实测、聚合、质检、字段角色、SVG | 1.0.0 |
| `scripts/verify.py` | 确定性复核（契约、引用、证据重跑、产物） | 1.0.0 |
| `references/schema-and-fields.md` | 建卡与字段语义判读规则 | 1.0.0 |
| `references/query-and-quality-rules.md` | 查询生成、脏数据与报错修复规则 | 1.0.0 |
| `references/output-contract.md` | `result.json` 字段表、状态词表、证据格式 | 1.0.0 |

运行环境：Python ≥3.8，仅标准库；实测 Python 3.12.4 / SQLite 3.46.0。

## 14. 维护说明

- 新增数据形态（如 Excel/Parquet）时，在 `dbcore.csv_table` 增加转换并在 `degradations` 记录降级原因，不改契约层。
- 调整字段语义规则时同步 `references/schema-and-fields.md` 与 `value_for()` 的键表，保持文档与代码一致。
- 每次改动后必跑第 11 节三条命令；`verify.py` 失败即视为不可交付。
- 已知限制：不跨语言词表匹配（中文"地区"不会自动等同 `region` 列名，此时给出按基数选取的分组并标注 caveat）；不做 OCR；不做写库。
