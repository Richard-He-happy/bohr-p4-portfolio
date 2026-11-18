---
name: search-coverage-gap-auditor
description: Audit literature-search coverage against a frozen reference set and diagnose every miss. Use when a case supplies known-relevant papers (review reference list, guideline, seed set, citation graph) together with retrieved records and/or query logs, and the task is 检索覆盖率、遗漏率、漏检归因、补充检索 (coverage, recall, missed studies, gap analysis, search audit). Produces a per-record hit matrix, coverage on an explicit auditable denominator, one attributed cause per miss bound to a concrete query/field/year-window/source, and directed supplementary rounds with measured marginal gain.
version: 1.1.0
---

# search-coverage-gap-auditor

## 1 用途与边界

输入一个**冻结的参考集**（已知相关文献）和一份**已保留的检索记录/查询日志**，输出：

1. 逐条命中状态（`hit / miss / excluded`）与命中层级；
2. 覆盖率（分子分母都可复算，分母在匹配前冻结）；
3. 每条未命中的**具体归因**：哪一次查询、哪个字段、哪个时间窗、哪个来源；
4. 定向补充检索：可离线复算的立即执行，需要联网的给出查询式与预测命中（标注为预测）；
5. 残余遗漏规模与停止理由。

**不做**：不联网、不接数据库、不读全文做正式纳排、不判断论文质量、不生成正式案例答案。
覆盖率只对"输入中能找到的参考集"精确成立；它是真实文献覆盖率的界，不是等号。

## 2 触发条件

用户或案例要求以下任一事项时使用：覆盖率 / 召回率 / 漏检 / 遗漏分析 / 参考集比对 / 检索策略审计 / 补充检索 / recall estimate against a known set。
不适用：只要一份普通文献列表（用检索类 Skill）、只要全文阅读或系统综述纳排。

## 3 运行契约

- 输入 `/input`（只读）：`case.json` + `task.md` + `artifacts/`。
- 输出 `/app/output`：`result.json`（必有）+ `hit_matrix.csv`、`candidates.csv`、`query_log.json`、`supplement_plan.json`、`coverage_report.md`、`verify_report.json`（跑 `verify.py` 后）。
- 入口：`python3 -B scripts/main.py --input /input --output /app/output`
- 预算：64 次模型请求 / 900 s；本 Skill 是确定性脚本，单次运行 <2 s，无网络。
- 退出码恒 0；任何异常写入 `errors`/`degradations`/`pending_human`，绝不静默失败。

## 4 输入发现（语义识别，不假设键名）

递归扫描 `/input/**`，按扩展名+内容识别（`scripts/verify.py: load/walk`）：

| 角色 | 识别方式 |
|-|-|
| 参考集 | 列表项含 title/doi/year，或路径/键名含 reference、refs、seed、included、known、gold、relevant、must_find；或项含 include/relevant 决策字段 |
| 检索记录池 | 项含 title/doi 且路径/键名含 response、result、hit、record、retriev、pool、candidate、crossref、europepmc、publisher，或项含 query_id/retrieved_at/source_db |
| 查询日志 | 项含 query/query_string + hits/count/total，或位于 queries/strategy/log 文件 |
| 引文图 | 项含 citing/cited/from/to/source/target |

支持 `.json .jsonl .csv .tsv .pdf`。`case.json` 缺失时退回任意 `case*.json` 并记 `degradations`。
材料未给的对象记入 `limits`/`errors`，不构造替代数据。

## 5 输出契约

`result.json` 顶层**原样回填**输入 `output_contract` 的全部键（不改名、不丢未知键、缺值 null/[]/""），并附 `case_id`、`status`、`sources`、`scope`、`reference_set`、`retrieval_pool`、`coverage`、`miss_taxonomy`、`hit_matrix`、`candidates`、`queries`、`supplement`、`baseline_comparison`、`metrics`、`limits`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`contract_fill`。
`contract_fill` 记录每个契约字段取自哪个内部分区及强制类型转换，便于复核。
`status ∈ {ok, partial, insufficient_evidence, input_error}`。

## 6 核心流程

1. 读 `case.json`，透传 `case_id`/`output_contract`，抽取 `organizer_supplied_scope`（topic/db/years/lang/max_k）。
2. **先写 partial `result.json`**（已实测），随后每阶段失败只降级该阶段。
3. 建参考集：去重（DOI → 标题+年）→ 排除撤稿/无法获取全文 → 冻结分母 → 记 `excluded`/`dedupe`。
4. 匹配：分块索引 + 分层判定（见 §8）→ 逐条命中状态。
5. 归因：每条 miss 按证据判定 1 个主因 + 全部支持原因（§9）。
6. 补检：R1 对齐修复（离线，真增益）→ R2 引文路由（有图才做，仅路由不计覆盖）→ R3 查询修复（给式+预测）。
7. 产出 `hit_matrix.csv`（逐条）、`candidates.csv`（去重候选+相关性依据）、`query_log.json`、`supplement_plan.json`、`coverage_report.md`。
8. 评估：`Wilcoxon`无关；报 Wilson 95% 区间、P@k 代理指标、两种失效口径基线。
9. finalize 覆盖 partial（无条件执行）。

## 7 覆盖率口径

- 主口径：`coverage = 命中(eligible ∩ 匹配到的池记录) / |eligible 参考集|`，分母在匹配前冻结。
- `coverage_over_all_refs` 用全部去重记录做分母（含撤稿/不可得），供保守解读。
- 禁止：以检索结果集为分母（循环）；把"没找到"当作"不相关"；把撤稿记录算作漏检。
- 报告 Wilson 95% 置信区间；参考集很小时覆盖率的不确定性必须一并给出。

## 8 命中判定分级

| 层级 | 规则 | 取值 |
|-|-|-|
| `exact_doi` | 归一化 DOI 相等（大小写/前缀/尾标点无关） | 1.00 |
| `identifier` | PMID/PMCID/arXiv/ISBN/OpenAlex 任一相等 | 0.97 |
| `exact_title` | 归一化标题完全相同 | 0.98 |
| `fuzzy_title` | 0.6·Jaccard + 0.4·difflib ≥0.90 且 \|Δyear\|≤1 | 0.90–0.98 |
| `fuzzy_author_year` | 同上 ≥0.86 且首作者姓氏一致 | 0.86–0.90 |
| `soft_candidate` | ≥0.62：**不直接计入命中**，进 R1 裁决（≥阈值自动接受，其余进 `pending_human`） | — |

每条命中在 `hit_matrix.csv.evidence_locator` 写明文件、记录号、query_id、retrieved_at。

## 9 漏检分类（`references/lexicon.json: miss_taxonomy`）

| 代码 | 类型 | 判定证据 |
|-|-|-|
| C01 | 池内未对齐 | 同一记录已在池中但低于阈值（给相似度与双方 DOI） |
| C02 | 命中被截断/排序未覆盖 | query_id + 报告命中数 > 保留记录数 |
| C03 | 来源库未返回 | query_id + 主题词重叠度 + 库名 |
| C04 | 时间窗截断 | query_id 或 scope 的 [year_from, year_to] + 文献年份 |
| C05 | 检索字段过窄 | query_id + 声明字段 + 实际匹配字段 |
| C06 | 查询词未覆盖 | 未覆盖术语清单 + 最近查询 + 查询词表规模 |
| C07 | 来源未覆盖 | 文献来源 + 已检索来源集合 |
| C08 | 语种/过滤器排除 | 文献语种 + 查询语种限制 |
| C09 | 引文路由未用 | 引文边 [citing, cited] + 图文件 |
| C10 | 参考记录异常 | 缺/错 DOI、缺年、重复、撤稿（单独报，不进分子） |
| C11 | 无记录池 | 输入清单 |
| C12 | 证据不足 | 列出所需证据，不猜 |

主因按 `cause_priority` 固定顺序取；`causes_all` 保留全部支持原因（满足"类型分全"）。
每条 miss 都带 `repair`（可执行动作），空归因不写"数据库覆盖不足"这类泛泛结论。

## 10 补充检索与停止规则

- R1 对齐修复：`offline_recomputable`，命中数**真实增加**并计入 `coverage_after_offline`。
- R2 引文路由：有引文图时给出 1-hop 可达证据；**只作为路由，不计入覆盖率**（记录还需取回）。
- R3 查询修复：按主因生成查询式（加词/放宽字段/扩窗/换库）+ 预测命中（基于参考标题术语集）；`requires_live_source=true`，标注为预测。
- 停止：某轮离线新增为 0 且残余原因全部需要外部来源访问；最多 3 轮。
- 残余遗漏按原因计数写入 `supplement.residual_by_cause`。

## 11 评分要点 → 字段/产物

| 评分点 | 落点 |
|-|-|
| 任务完成度：算覆盖→列漏检→补检闭环 | `coverage`、`hit_matrix`、`supplement.rounds` |
| 结果正确性 | 分层匹配 `match_tier`；`reference_set.excluded/dedupe`；`baseline_comparison` 同数据复算 |
| 完整性：逐条覆盖 + 类型分全 | `hit_matrix.csv` 每行一条；`miss_taxonomy.classes[].n` + `causes_all` |
| 可核验性 | `evidence_locator`、`query_log.json`、`verify.py` 复算 14 项检查 |
| 使用增益 | `baseline_comparison.delta_vs_exact_only`、`coverage_after_offline`、`metrics.dedupe_removed` |
| 创新增益 | 池内未对齐检测（C01）、多因归类、引文路由、离线可执行补检 |
| 可靠体验 | `status`、`errors`、`degradations`、`pending_human`、重复运行确定性（无随机、无网络） |
| 生态贡献 | `references/method.md` 口径+分类表、`io-schema.md` 字段、`lexicon.json` 词表可替换到新主题 |

## 12 证据与定位规范

- 每条命中/miss 必须有 `evidence_locator`；缺失由 `verify.py` 判失败。
- 逐字引用只用于参考集标题/查询式原文；推断写进 `cause_evidence` 的 `why`/`needed`。
- 不编造 DOI、年份、来源、检索时间；未知写 null 并在 `metrics.missing_retrieved_at` 计数。
- 预测值（`predicted_catch`）必须带 `prediction_basis`，不得当作观测。

## 13 异常与降级

| 情况 | 行为 |
|-|-|
| 无 `case.json` / JSON 损坏 | 尝试 `case*.json`；仍失败 → `status=input_error`，其余照跑 |
| 找不到参考集 | `insufficient_evidence`，只交输入清单，coverage=null |
| 找不到记录池 | 全部 eligible 记为 C11，`status=partial` |
| 查询日志缺失 | 由池记录生成 1 条合成查询并记 `degradations`（query 文本为 null） |
| 缺 `retrieved_at` / DOI | 保留记录，计数并在 `metrics` 暴露 |
| 撤稿/无法获取全文 | 排除出分母，写 `reference_set.excluded`，不算漏检 |
| 同一论文多库重复 | 合并为主记录 + `provenance` 列表，`metrics.dedupe_removed` 报告 |
| 材料过大/不可解析 | 跳过该文件，记 `degradations`，不影响全局 |
| 阶段级异常 | 捕获写 `errors`，继续后续阶段，退出码仍为 0 |

## 14 最小调用示例（示例，非正式案例结果）

输入（`/input/case.json` 节选）：

```json
{"case_id": "demo-x",
 "organizer_supplied_scope": {"topic": "gut microbiome and insulin resistance", "years": [2015, 2022]},
 "output_contract": {"coverage_rate": {"type": "number"}, "missed_papers": {"type": "array"}}}
```

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --input /input --output /app/output
```

示意输出（**示例，仅为接口说明，不是任何案例的真实结果**）：

```json
{"case_id": "demo-x", "status": "ok",
 "coverage_rate": 0.8,
 "missed_papers": [{"ref_id": "R007", "cause_primary": "C06", "repair": "add the uncovered term group to the query and re-run"}],
 "coverage": {"n_eligible": 5, "n_hit": 4, "coverage": 0.8, "wilson95": [0.38, 0.96]},
 "supplement": {"coverage_before": 0.8, "coverage_after_offline": 0.8, "measured_gain_hits": 0}}
```

## 15 文件清单与自检

```
SKILL.md                 本文件
scripts/main.py          流水线（导入 verify 的判定核）
scripts/verify.py        判定核 + 确定性自检 CLI（14 项检查）
references/lexicon.json  停用词、12 类漏检定义与修复动作、路径提示
references/method.md     口径、公式、分类体系、补检与复用手册
references/io-schema.md  输入发现、契约回填、产物字段、异常表
```

自检：`main.py --help` 退出码 0；空输入/坏 JSON 仍产出合法 `result.json` 且退出码 0；`hit_matrix.csv` 行数 = 命中+漏检+排除；`coverage` 与 `hit_matrix` 计数一致；无 `__pycache__`/`.pyc`。

## 16 维护

新增主题只需替换 `lexicon.json` 的停用词与可选的 synonym 组；判定阈值在 `main.py --accept`（默认 0.86）。
升级判定规则必须同步 `references/method.md` 与 `verify.py` 的检查项，否则自检会报错（这是有意的：文档与实现必须同版）。
