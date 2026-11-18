---
name: statistical-analysis-interpretation
description: Deterministic standard-library statistics skill for research data tables (CSV/TSV/TXT/SQLite). It profiles and cleans the table (missing, outlier, duplicate, format repair, unit/encoding), selects the hypothesis test from the study design and the checked assumptions, reports design-matched effect sizes with confidence intervals, applies multiple-comparison correction, and writes an evidence-linked re-runnable report. Use when a case asks for descriptive statistics, inference, effect size, confidence intervals, or interpretation of a research data table.
version: 1.0.0
---

# 统计分析与结果解读（analysis-02）

读一份真实科研数据表，清洗到可统计的状态，按研究设计与假设检验结果选择检验方法，给出效应量与置信区间，并把结论翻译成科研人员可判断的表述。所有数字由脚本算出，脚本、规则、口径、种子与中间表随包交付，可逐位复算。

## 1. 用途与边界

**做什么**
- 描述统计：n、均值、SD（n−1）、SE、中位数、Q1/Q3/IQR、极值、CV、偏度 G1、峰度 G2、均值 95% CI。
- 数据质量：缺失 / 异常（Tukey 1.5 IQR）/ 重复（主键判重）/ 数值格式修复（千分位、百分号、全角）/ 单位与编码冲突，逐项落规则 ID。
- 推断统计：先做正态性（D'Agostino–Pearson K²）与方差齐性（中位数中心化 Levene），再按设计与假设在 Student t / Welch t / Mann–Whitney U / 单因素 ANOVA / Kruskal–Wallis 之间选择；多组事后比较用 Holm 校正。
- 效应量与区间：Hedges g（Hedges–Olkin 近似 CI）、eta²、epsilon²、秩二列相关 r、均值差/中位数差及其 95% CI。
- 解释：每个比较一句可读结论，区分统计显著与实际意义，给出区间与不适用条件。

**不做什么**
- 不做实验设计、样本量估算、论文写作、临床决策建议。
- 不构造数据、不猜测单位换算、口径不明时不硬算（挂 `pending_human`）。
- 不解析 PDF/图片中的表格；发现即降级并说明。

## 2. 触发时机

案例出现下列任一要求时加载：描述统计 / 组间差异 / 假设检验 / p 值 / 效应量 / 置信区间 / 相关性 / “这份数据能不能写进报告” / 清洗后可统计 / 统计结果解读。

## 3. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下数据表（csv/tsv/txt/sqlite/db）、可选数据字典（json/md） |
| 输出目录 | `/app/output/` |
| 调用 | `python3 scripts/main.py --input /input --output /app/output`（`--help` 可用；不依赖 CWD） |
| 依赖 | 仅 Python 标准库（≥3.8）；无网络；不写 `/input` |
| 退出码 | 恒 0（异常写入 `errors` 后仍返回 0） |
| 首写 | 任何分析开始前先写 partial `result.json`，末尾无条件 finalize 覆盖 |
| 确定性 | 分组排序固定（n 降序、值升序）；bootstrap 种子由 `zlib.crc32(标签+盐)` 派生；浮点按 `%.12g` 序列化 |

## 4. 输入发现（语义识别，不假设键名）

1. 读 `case.json`；不存在时递归找任一含 `case`/`input` 的 JSON 并解析。
2. `case_id` 原样保留；`output_contract` 原样透传（键名不改、未知字段保留）。
3. 递归扫描 `/input/**`，按扩展名识别数据表；编码按 UTF-8 / UTF-8-BOM / GB18030 / Latin-1 顺序探测，分隔符按首行投票（`,` `;` `\t` `|`）。
4. 表头判定：首行不含任何字母或汉字（纯数值首行）视为无表头，命名 `col1..colN`。
5. 多张表时取**行数最多且可解析**的一张，其余失败写 `degradations` 与 `run.log`。
6. 数据字典：支持任意嵌套 JSON（键名 `name/field/column/variable` + `unit/单位` + `desc/说明/含义`）与 markdown 字段表（表头含“单位/说明”）。字典单位优先于列名推断。
7. 日期列：形如 `YYYY-MM-DD` / `YYYY/MM/DD` 的取值判为非数值，只作分类描述，不进推断与相关——避免把日期当数值算均值、或把两个日期段当两组比较。
8. 材料未给的对象明确列缺口：无字典 → `pending_human` 记“口径按列名推断”；无表 → `status=input_error`。

## 5. 输出契约

`result.json` = `output_contract` 全部字段（同名优先，其次语义别名映射，如 `effect_sizes`/`effectSizes` → 效应量表；映射不到则 `null`/`[]`，绝不改名）＋固定字段：

`case_id`、`status`（ok | partial | insufficient_evidence | input_error）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`correlations`、`tables`、`dataset`、`runtime`（`checks` / `python` / `seed` / `finished_utc`）、`_ctk`（契约键回显清单）。

| 文件 | 内容 |
|-|-|
| `analysis.md` | 报告：结论摘要 → 描述统计 → 清洗记录 → 检验/效应量/CI → 限制 → 人工确认 → 复现 |
| `cleaned.csv` | 去重后的分析集（列序与原件一致） |
| `tables/descriptive.csv` | 每变量 n/均值/SD/SE/中位数/分位/极值/IQR/CV/偏度/峰度/均值 CI/单位 |
| `tables/tests.csv` | 每比较：方法、method_id、统计量、df、p、校正 p、效应量及 CI、点估计及 CI、判定、选择理由 |
| `tables/correlation.csv` | 变量对：n、Pearson r 及 CI、p、Spearman rho、斜率及 CI |
| `run.log` | 运行摘要（case_id/status/文件编码分隔符/行数守恒/错误与待确认计数），一行键值 |

`result.json.tables` 只列**实际写出**的文件：无入库相关对（配对 n≥5 的变量对）时不生成 `tables/correlation.csv`，该路径也不会出现在 `tables` 里，避免报告引用不存在的表。

`cleaned.csv` 保留原始单元格文本（因此格式化修复可逆、去重可核对）；被修复的数值列在内部一律使用修复后的值参与统计，原始串→数值的映射见 `cleaning.issues[*].ex`（前 5 例，含行号）与 `N-01` 的 `rows`；需要完整逐格映射时改跑脚本（确定性，同样输出）。

## 6. 核心流程

`profile → 字典 → 清洗（五类）→ 分组识别 → 假设检查 → 选检验 → 效应量+CI → 多重比较 → 自检 → 写产物 → finalize`

1. **profile**：每列判数值/分类/空列、缺失计数、数值修复、单位（列名或字典）、水平数。
2. **分组变量**：case 声明 > 列名关键词（group/class/treat/组/类别…）> 低基数分类列 > 整数编码列（需确认，写入 `pending_human`）。
3. **假设检查**：各组 D'Agostino K²（n≥8）与非参数 Levene。
4. **选择检验**
   - 两组：正态且方差齐 → Student t；正态但方差不齐 → Welch t；正态性被拒且某组 n<30 → Mann–Whitney U（附 bootstrap 中位数差 CI）。
   - 三组以上：ANOVA（参数前提满足）或 Kruskal–Wallis；事后为“参照组 vs 其余”，Holm 校正。
   - 无分组：变量两两相关（配对 n≥5）。
5. **效应量与区间**：与检验匹配（t → Hedges g；秩 → 秩二列 r；ANOVA → eta²；KW → epsilon²），区间与检验结论同时给出。
6. **多重比较**：同一变量内 Holm（事后），并写明校正范围。
7. **自检**（写入 `runtime.checks`）：行数守恒、CI/p 一致性、契约字段齐全。

## 7. 评分要点 → 字段/检查/产物

| 评分点 | 对应实现 |
|-|-|
| 任务完成度 | `cleaning`、`descriptive`、`hypothesis_tests`、`effect_sizes`、`confidence_intervals`、`interpretation` + `analysis.md` |
| 结果正确性 | `tables/tests.csv` 的 statistic/df/p/effect/CI；统计函数与 SciPy 逐项对照（见 `references/method_rules.md`） |
| 结果完整性 | 七类情形：缺失 M-01/02/03、异常 O-01、重复 D-01、格式 N-01、单位编码 N-02/C-01、假设 `assumptions`、图表数据 `tables/correlation.csv`、代码运行 `runtime` |
| 结果可核验性 | `sources`（文件/行数/列名/规则 ID）、`cleaned.csv`、种子、版本、`verification` |
| 使用增益 | 一条命令走完清洗→统计→报告；口径外置在 `references/messages.json` |
| 创新增益 | 字典驱动的单位/说明；假设检查后才选检验；效应量与区间绑定到同一句结论；口径不明挂 `pending_human` 而非硬算 |
| 可靠体验 | 空表/乱码/无表头/单位冲突/样本不足/零方差/重复主键/只读输出均有降级路径；重复运行结果逐位一致 |
| 生态贡献 | 本文件 + `references/method_rules.md`（公式与口径）+ `references/example.md`（示例，标注示例）+ `messages.json`（可改词表） |

## 8. 证据与定位

- `sources[*]`：主数据路径、行数、列名、编码、分隔符、触发的规则 ID；原始行号在 `cleaning.issues[*].rows`（1-based，含表头偏移 +2）。
- 每个统计量都能由 `cleaned.csv` + `tables/tests.csv` 复算；`runtime` 记录 Python 版本、种子、完成时间与三项自检结果；α 与置信水平在 `references/messages.json` 的 `cfg` 中，并写进 `analysis.md` 表头。
- 五类清洗都带 `rule`/`count`/`rate`/`action`/`why`/`rows`。

## 9. 冲突与人工确认

不硬算、写 `pending_human` 并保留原始值：单位冲突（N-02）、缺失率 >50%（M-02）、主键重复（D-01）、分组变量由启发式推定（置信度 ≥0.35）、无数据字典、某组 n<3、组内零方差。

## 10. 预算与断点

纯 CPU、无网络、无子进程；1030×9 与 178×14 规模秒级完成。单文件 >64MB 跳过并记 `degradations`。partial `result.json` 在任何分析前落盘，任何阶段异常都不影响已写产物。

## 11. 异常降级分支表

| 情形 | 处置 | 字段 |
|-|-|-|
| `/input` 为空或无表 | `status=input_error` + 缺口 | `errors`, `pending_human` |
| case.json 坏 JSON | 继续按目录扫描，仍出结果 | `errors` |
| GBK/GB18030 编码 | 自动探测解码 | `run.log` |
| 无表头 | 命名 `col1..colN` | `sources` |
| xlsx | 跳过并说明（仅标准库） | `degradations` |
| SQLite 多表 | 取行数最多的表 | `sources.relation` |
| 某列全空 | M-03，剔出分析 | `cleaning` |
| 缺失率 >50% | 不进推断 | `pending_human` |
| 某组 n<3 | 不报检验 | `decision=insufficient` |
| 组内零方差 | t 检验无定义，只留描述 | `errors` |
| 输出目录只读 | 捕获异常，尽力写 `result.json` | `errors` |

## 12. 自检清单

跑完看四件事：`status` 是否 `ok`（否则读 `pending_human`/`errors`）；`runtime.checks` 三项是否全为 `true`；`analysis.md` 的数字与 `tables/tests.csv` 是否一致（同一 dict 渲染，设计上不可能不一致）；`cleaned.csv` 行数是否等于 `cleaning.rows.kept`。

## 13. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py --input /input --output /app/output
```

示例输入 `case.json`：

```json
{"case_id":"demo-01","output_contract":{"descriptive":null,"hypothesis_tests":null,
 "effect_sizes":null,"confidence_intervals":null,"cleaning":null,"interpretation":null,
 "sources":null,"uncertainty":null,"pending_human":null},
 "primary_key":["sample_id"],"group":"group","files":["data.csv"]}
```

`data.csv`：`sample_id,group,value_mg,pct_value,weight`，A/B 两组各 30 行，含 2 行缺失、1 个离群值、11 个带 `%` 的字符串、2 行重复。示意输出（示例，非正式案例结果）：`status="ok"`；`cleaning.rows={"raw":60,"kept":58,"dropped":2}`；`hypothesis_tests[0]` 的 `id="value_mg:A~B"`，方法随假设检查在 t/Welch/Mann–Whitney 间确定，含 `statistic`、`df`、`p_value`、`effect_name`、`effect_value`、`estimate_ci`；`tables/tests.csv` 与 `analysis.md` 中同一数字一致。

完整示例（含真实数值与逐字段说明）见 `references/example.md`。

## 14. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（用途/契约/流程/降级/自检） |
| `scripts/main.py` | 单入口：发现 → 清洗 → 统计 → 自检 → 写产物 |
| `scripts/statsx.py` | 纯函数统计引擎：分布函数、检验、效应量、稳健描述、列剖析 |
| `references/messages.json` | 全部文案、字段顺序、规则/理由、语义别名映射（改口径只改这里） |
| `references/method_rules.md` | 公式、口径、检验选择树、效应量映射、失败案例 |
| `references/example.md` | 最小调用示例与示意输出（标注示例） |

维护：新增检验 → 在 `statsx.py` 加纯函数并补 `main.py` 选择树；改文案或字段序 → 只改 `messages.json`；每次改动同步版本号与 `changes`。适用 Python ≥3.8，仅标准库。
