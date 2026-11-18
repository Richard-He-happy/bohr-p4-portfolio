# 方法说明：覆盖率口径、漏检分类与补检流程

本文件是可独立阅读的方法手册；`scripts/verify.py` 实现了这里描述的判定，`scripts/main.py` 按此顺序执行。

## 1 参考集冻结（分母从哪来）

1. **来源**：综述/指南的参考文献表、种子论文清单、已有系统综述的纳入清单、案例显式给出的 known-relevant 列表。
2. **去重**：先按归一化 DOI（小写、去 `https://doi.org/` 前缀、去尾标点）；无 DOI 时按 `归一化标题 + 年份`。保留首次出现，其余进 `reference_set.dedupe`（记录 `kept`/`dropped`）。
3. **排除**（仍逐条报告，不进分子分母）：
   - 撤稿：状态含 `retract`、标题以 `RETRACTED` 开头、常见撤稿声明字段；
   - 无法获取全文：状态含 `unavailable / no_fulltext / cannot / closed / denied`；
   - 无可识别标识（既无标题又无 DOI）不进入参考集。
4. **冻结**：`reference_set.frozen_at` 记录冻结时刻；此后分母不变。
5. **两个分母**：
   - `n_eligible`：排除后的去重记录数 —— 主口径；
   - `n_unique`：去重后全部记录数 —— `coverage_over_all_refs` 的保守分母。

> 反模式警示：用检索结果自身的条数做分母，覆盖率会自然接近 1.0。本 Skill 在 `baseline_comparison.baseline_circular_denominator` 里把这个循环口径的数值算出来，正是为了让差异可见。

## 2 覆盖率与区间

```
coverage        = n_hit / n_eligible
miss_rate       = n_miss / n_eligible
coverage_all    = n_hit / n_unique
Wilson95(k, n)  = 标准 Wilson score interval, z = 1.96
```

小样本（n_eligible < 20）时 Wilson 区间很宽，必须与点估计一起读。参考集本身不是总体抽样，覆盖率是**对给定参考集**的精确值，对真实文献总体只是下界式的估计。

## 3 命中判定分级

| 层级 | 规则 | 分数 |
|-|-|-|
| `exact_doi` | 归一化 DOI 相等 | 1.00 |
| `identifier` | pmid/pmcid/arxiv/isbn/openalex 任一相等 | 0.97 |
| `exact_title` | 归一化标题等同 | 0.98 |
| `fuzzy_title` | `0.6·Jaccard(tokens) + 0.4·difflib(norm_title)` ≥ 0.90 且 \|Δyear\| ≤ 1 | 0.90–0.98 |
| `fuzzy_author_year` | 同式 ≥ 0.86，且首作者姓氏相同、\|Δyear\| ≤ 1 | 0.86–0.90 |
| `soft_candidate` | ≥ 0.62：**不计命中**，进 R1 裁决 | — |

实现要点：先用倒排索引分块（只对出现在 <60% 记录中的词建候选），候选需共享 ≥2 个词（短标题 ≥1），再算 difflib。候选上限 300/条，保证千级参考集 × 万级记录仍可秒级完成，结果与顺序无关（确定性）。

## 4 漏检分类体系

代码按 `lexicon.json: cause_priority` 的固定顺序取主因，`causes_all` 保留全部支持原因。

| 代码 | 标签 | 定义 | 判定证据 | 修复动作 |
|-|-|-|-|-|
| C01 | 池内未对齐 | 记录已在池中，标识差异使其低于阈值 | 池记录号、标题相似度、双方 DOI | 对齐修复（重跑分级匹配 + 裁决队列） |
| C02 | 命中截断 | 查询报告命中数 > 保留记录数 | query_id、hits、records_retained | 提高该查询的 max_k 重筛 |
| C03 | 来源未返回 | 查询主题上够得着、过滤也放行，但该库没有返回 | query_id、词重叠度、库名 | 原式重发 + 检查库对期刊的索引 |
| C04 | 时间窗截断 | 年份在能力查询或 scope 的窗口之外 | query_id/scope、窗口、文献年 | 扩窗重跑 |
| C05 | 字段过窄 | 查询词能匹配，但声明字段排除了匹配所在字段 | query_id、fields、匹配字段 | 放宽到 title+abstract+keywords |
| C06 | 查询词未覆盖 | 查询词表不含该文献的特征词或其同义表达 | 未覆盖术语、最近查询、词表规模 | 加同义组后重跑 |
| C07 | 来源未覆盖 | 文献所在库/索引从未被检索 | 文献来源、已检索来源集合 | 增加来源并重筛 |
| C08 | 语种/过滤排除 | 语种或文献类型限制把记录挡掉 | 文献语种、查询语种 | 去限制或加译文查询 |
| C09 | 引文路由未用 | 与已保留材料存在 1 跳引文关系，但没做滚雪球 | 引文边、图文件 | 从指定文献做前后向滚雪球 |
| C10 | 参考记录异常 | 缺/错 DOI、缺年、重复、撤稿 | 异常标记、排除规则、原始字段 | 先核身份，再决定是否计入可检索 |
| C11 | 无记录池 | 没有可用的检索记录 | 输入清单 | 执行计划查询并记录 query/source/retrieved_at |
| C12 | 证据不足 | 保留证据不支持任何具体原因 | 缺失证据清单 | 人工裁决 |

判定顺序（`main.py: attr`）：

1. 池内软匹配存在 → C01；
2. 找到词重叠 ≥0.34 的"能力查询"：窗口挡 → C04；字段挡 → C05；命中被截断 → C02；否则 → C03；
3. 无能力查询：scope 窗口挡 → C04；来源未检索 → C07；术语完全不在词表 → C06；非英文 → C08；
4. 引文边可达 → C09；参考记录异常 → C10；
5. 都没有 → C12（列出所需证据，不猜）。

## 5 补充检索的三种可执行级别

| 轮次 | 动作 | 执行级别 | 是否计入覆盖率 |
|-|-|-|-|
| R1 | 对齐修复（soft → 命中，其余人工队列） | `offline_recomputable` | **是**，`coverage_after_offline` |
| R2 | 引文路由（1 跳，基于保留图） | `route_proposed_live_required` | 否（记录仍需取回） |
| R3 | 查询修复（加词/扩窗/放宽字段/换库） | `spec_generated_live_required` | 否，仅 `predicted_catch` |

R3 的预测基于参考标题术语集：`predicted_catch = |{miss : tokens(title) ∩ (查询词表 ∪ 新增术语)} ≠ ∅|`，并显式写 `prediction_basis`。这是**预测**，不是观测。

停止规则：某轮离线新增命中为 0，且残余原因全部为来源侧（C02/C03/C04/C05/C06/C07/C08/C11）时停止；最多 3 轮。

## 6 基线与增益（同参考集、同记录池）

在同一份数据上重算两种已知失效口径：

1. `baseline_exact_title_doi_only`：只用精确 DOI/标题匹配（低估，脆弱于大小写与题录差异）；
2. `baseline_circular_denominator`：以结果集为分母（恒为 1.0，无信息量）。

`delta_vs_exact_only = skill_coverage − baseline_exact_title_doi_only` 是**同数据复算**的差值，不是对平台白板的声称。`misses_baseline` 与 `misses_skill` 同理。

## 7 候选相关性依据（可复算，非人工打分）

```
relevance_score = 0.5·[命中参考集] + 0.3·min(1, |tok ∩ scope_topic| / |scope_topic|) + 0.2·min(1, provenance/3)
relevance_reason = "reference_match=…; scope_term_coverage=…; distinct_provenance=…"
```

`provenance` = 该记录被多少个 (query_id, source) 返回。加权是显式的人工设定，故在 `metrics.note` 与 SKILL.md 中声明为筛选代理，不冒充人工相关性判断。

## 8 复用到新主题

1. 新案例无需改代码：参考集/记录池/查询日志/引文图按 §SKILL 4 的语义被自动识别。
2. 换词表：替换 `lexicon.json.stopwords`；如需同义扩展，在 R3 规格的 `added_terms` 中由案例的查询日志提供。
3. 改阈值：`--accept`（默认 0.86）只影响 R1 自动接受线，不影响主口径评分的匹配层级。
4. 复用产物：`hit_matrix.csv` 可直接作为漏检治理台账；`supplement_plan.json` 可直接作为下一轮检索的工单。

## 9 已知限制

- 参考集只在输入里；输入没给的文献无法评估"是否被漏"。因此本 Skill 报"对参考集的覆盖"，不是绝对召回。
- 无网络，无法验证 DOI 是否真实存在于 Crossref，只能校验格式与内部冲突（`doi_format_ok_rate`、`anomaly`）。
- PDF 材料仅做 DOI 扫描（优先 `pdftotext`，否则字节级正则）；若参考集只存在于 PDF 正文，建议先转成 CSV/JSON，否则参考集可能不完整（会在 `reference_set.sources[].derived` 标注 `pdf_doi_scan`）。
- 归因依赖查询日志的字段/年份/命中数字段；日志缺失时只能给出 C11/C12 或主题词层面的结论（会在 `degradations` 注明）。
- 覆盖率对分母定义敏感：撤稿与不可得记录的处理方式已显式写出，改变规则会改变数值。
