# 研究前沿与趋势分析报告

- case_id：`{{CASE}}`
- 研究主题（来自 case）：{{TOPIC}}
- 语料与产物口径：{{META}}
- **口径声明**：本报告的全部计数、主题占比、代表作与空白判断只针对本次输入语料；未检索任何外部数据库，不声称领域完整性。所有结论的逐字引文与定位见 `evidence_map.csv`。

## 1. 研究问题与拆解（固定权重，可复核）

{{QTAB}}

拆解规则：每个子问题对应一个可检查产物；`Q5` 负责把越过证据的表述单独隔离，避免结论外推。

## 2. 检索与纳排

- 检索式（本 Skill 离线运行时不执行；供复跑与人工补检使用）：
  - 主题检索：`("<case 主题词>" OR "<lexicon 别名 1>" OR "<lexicon 别名 2>") AND PY=<窗口起>..<窗口末>`
  - 字段：title / abstract / keywords；数据库建议按领域选择（Web of Science、Scopus、PubMed、arXiv）
  - 递增策略：先主题词精确检索，再用 `cites:` / 参考文献回溯补齐各窗口的代表作
- 实际执行的筛选（自动）：年份窗口过滤、无题名/无可抽文本剔除、去重（DOI 精确 → 题名全等 → 题名 Jaccard ≥ 0.92 且年份差 ≤ 1）
- 排除记录（前 8 条，完整版见 `screening_log.csv`）：
{{SCREEN}}

## 3. 时间趋势

{{TREND}}

{{TRENDNOTE}}

读法：先看年度计数是否连续，再看窗口均值是否改变方向；拐点判定需要"方向持续 + 幅度 ≥ 1.5 倍"才记为 `supported_change`，否则只记为 `candidate_only`，并把高变异（CV）情形写成"离散波动"。年份口径取自文献元数据，缺失时才从题名/摘要/正文抽取，逐条来源写在 `evidence_map.csv`。

## 4. 主题演化

{{EVOL}}

判定规则（阈值写死在脚本里，可复算）：`emergence` 首次非零窗口 ≥ 2 且计数 ≥ max(2, 2%N)；`decline` 峰值不在最后窗口且末窗口 ≤ 峰值的 50%；`persistence` 出现窗口数 ≥ 60%；`single_mention` 总量 ≤ 1。术语合并/分裂只作为 `candidate_merge` / `candidate_split` 提出，需人工确认术语同一性；未命中任何主题词的记录单独计数，不强行归类。

## 5. 各阶段代表性工作

{{REPS}}

选取规则：`0.45 × 窗口内主题中心性 + 0.35 × 语料内被引度 + 0.20 × 方法首创措辞`，每窗口取前 3 篇，并额外保留 1 篇"低被引但含首创措辞"的长尾工作。被引度只来自 case 提供的引文图；未提供时该项为 0 并在降级记录中说明——**不使用总被引排序**。

## 6. 研究空白

{{GAPS}}

空白类型：`unresolved`（被反复提出未解决）、`scope_limit`（方法在特定对象/尺度上失效）、`conflict`（证据冲突未决）、`data_limit` / `cost_limit`（数据与成本约束）。每条空白都记录"在 N 条纳入文献中出现 M 次"，属于语料内证据，不把检索遗漏当作空白。

## 7. 冲突证据

{{CONF}}

## 8. 引用可追溯表（节选）

{{EVID}}

## 9. 不确定性与限制

{{LIMIT}}

## 10. 复跑与自查

1. `python3 -B scripts/main.py --input <case 目录> --out <输出目录>`；退出码恒为 0。
2. 打开 `evidence_map.csv`，对每个 `claim_id` 抽查至少一条引文，用 `locator` 回到原文核对逐字文本；`quote_verified=false` 的条目不得当作事实。
3. 用 `trend_annual.csv` 的 `count` 求和，应等于 `result.json` 中 `verification.dated_records`。
4. 用 `topic_evolution.csv` 校验报告第 4 节的窗口序列；不一致说明输出被手工改过。
