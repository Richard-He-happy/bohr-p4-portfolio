# 检测规则目录与误报护栏（review-03）

版本 1.0.0。本文件记录 `scripts/main.py` 中**自动检测器**的触发条件、护栏与严重度，以及
Agent 在阶段 2 需要人工补充的判定型问题。规则 ID 与 `references/review_checklist.md` 完全一致。

## 0. 三级证据强度（每条 issue 必须声明）

| level | 含义 | 允许的措辞 |
|-|-|-|
| `error` | 稿件内部可自证矛盾：两处数值冲突、引用越界、结论与 p 值反向 | "错误"、"矛盾"、"不成立" |
| `gap` | 稿件缺该报告项，无法据此判断做法对错 | "未报告"、"无法核实"、"建议补充" |
| `judgment` | 需要方法学或领域判断，稿件本身不构成反证 | "可能不匹配"、"建议说明" |

`evidence_strength` 写入每条 issue。**把 `gap` 写成 `error` 是最常见的掉分方式。**

## 1. 通用护栏（所有检测器共用，顺序执行）

1. **段落优先**：先按段落（章节标题变化处切分）定位，再取句。`quote` 必须是该段落内**连续原文子串**，
   长度 12–200 字符；超长则截断并在 `quote` 末尾标注 `…`（截断标记不属于原文，验证时按前缀匹配）。
2. **去噪**：参考文献表内的段落不参与统计/方法类检测（避免把文献标题里的 `p` 值当结果）。
3. **否定与条件从句**：触发词若处在前 12 字符内出现 `不`、`未`、`无`、`无需`、`not`、`no `、`without`、`if `、
   `是否`，则判定为"讨论/要求"语境，不触发（例："未进行多重比较校正"本身是已披露信息，触发时应降级为
   `suggestion` 而非 `major`）。
4. **方法节 vs 结果节**：检验方法名若在方法节出现即视为"已报告"（不因结果节未重复而报 S-05）。
5. **单次触发原则**：同一 rule_id + 同一段落只输出一条；同一 rule 全稿最多输出 5 条（超出合并为一条
   "另见 N 处"并列出 locator 列表）。
6. **短文本豁免**：全稿有效字符 < 800 时，S-03/S-04/S-08/D-01/E-01 等"缺失类"规则不触发，改为在
   `uncertainty` 记录"材料过短，缺失类判定不成立"，避免对小样本输入狂报缺失。
7. **语言混合**：中英混排时，中英文关键词表同时启用；只匹配到一侧不构成缺失证据。

## 2. 自动检测器（脚本真实实现）

| rule | 触发（正则要点） | 护栏 | sev | strength |
|-|-|-|-|-|
| F-01 | 正文 `表\s*(\d+)\|Table\s*(\d+)` / `图\s*(\d+)\|Fig(?:ure)?\.?\s*(\d+)` 的编号集合 − 稿内标题定义的编号集合 ≠ ∅ | 稿内无任何表图标题时，整条规则不触发（无法判断是否存在） | major | error |
| F-02 | 全文 `n\s*=\s*(\d+)` / `N\s*=\s*(\d+)` 去重后出现 ≥2 个互不相同的值，且差值 > 5% | 排除 `n = 3`（重复测量/亚组示例）、排除参考文献段；若两值分别位于"估算"与"实际"语境则不触发（转 S-09） | major | error |
| F-03 | 同句内 `(\d+)\s*/\s*(\d+)` 与 `(\d+(?:\.\d+)?)\s*%` 并存，\|a/b*100 − p\| > 0.6 | 分母 < 10 不触发 | major | error |
| S-01 | `[Pp]\s*[<≤]\s*0?\.0*5` 或 `P\s*>\s*0\.05` 等不等式 | 若同句另有 `p = 0.03` 精确值则不触发 | minor | gap |
| S-02 | 同一段落内：`显著(升高\|降低\|差异\|改善)` 且 `p\s*=\s*0\.(0[6-9]\|[1-9]\d*)` 或 `p\s*>\s*0\.05`；反向：`无显著\|不显著\|no significant` 且 `p\s*[<=]\s*0?\.0[0-4]` | 需同段共现；跨段不判 | major | error |
| S-03 | 全文有 p 值（≥2 处）但无 `95%\s*(CI\|置信区间)`、无 `OR\|HR\|RR\|效应量\|effect size\|mean difference\|MD\b` | 纯描述性研究（无组间比较词）不触发 | major | gap |
| S-04 | 组间比较词（`vs\.?\|与.*组比较\|compared with`）+ p 值 ≥3 处，且全文无 `多重比较\|校正\|Bonferroni\|Holm\|Tukey\|FDR\|Benjamini\|Bonferroni` | 若文本出现"未校正"披露 → suggestion | major | gap |
| S-05 | 结果节有 p 值但全文无检验名（`t 检验\|t-test\|ANOVA\|方差分析\|χ2\|卡方\|Mann-Whitney\|Wilcoxon\|Kruskal\|Fisher\|log-rank\|回归\|regression\|mixed model`） | 护栏 4 | major | gap |
| S-06 | 不匹配组合：(`中位数\|median\|IQR\|四分位`) 且 (`t 检验\|t-test\|ANOVA`)；(`mean\s*±\s*SD\|均数±标准差`) 且 (`Mann-Whitney\|Wilcoxon\|Kruskal`)；(`配对\|paired\|自身前后\|before and after`) 且 (`独立样本\|independent`) | 组合须在同一文件内；同段共现提高 confidence | major | judgment |
| S-07 | 出现 `t 检验\|ANOVA` 且全文无 `正态\|normal distribution\|Shapiro\|Kolmogorov\|方差齐\|Levene\|homogeneity` | 短文本豁免 | minor | gap |
| S-08 | 全文无 `样本量\|sample size\|检验效能\|把握度\|power\|效应量估算\|样本量估算`；且稿件有组间比较（≥2 组） | 短文本豁免；纯二次分析/全库研究不触发（样本已固定）→ 转 pending_human | major | gap |
| S-09 | 存在 `估算\|预计\|计划\|planned\|required` 附近的 N 与实际 `n =` 差异 > 10%，且无 `失访\|脱落\|排除\|excluded\|flow` 说明 | 无估算值则不触发 | major | gap |
| S-10 | 出现 `随访\|follow-up\|周\|月\|年` 纵向表述且全文无 `失访\|脱落\|退出\|withdraw\|dropout\|lost to` | 横断面不触发 | minor | gap |
| S-11 | `分为高\|分为低\|高分组\|低分组\|二分类\|dichotomiz\|cut-?off` 且涉及连续量（同句有 `±` 或 `mmol\|mg\|score\|评分`） | 若给出切点依据（ROC/文献）→ suggestion | minor | judgment |
| S-12 | 有统计检验但全文无 `SPSS\|R \|R\$\|SAS\|Stata\|Python\|GraphPad\|软件` | — | suggestion | gap |
| S-14 | `[Pp]\s*=\s*0?\.0+\b`（即 p=0.000）或 `P\s*<\s*\.\d` | — | suggestion | judgment |
| S-15 | 结果节含 p 值但同段无 `t\s*=\|F\s*=\|χ2\s*=\|χ²\s*=\|z\s*=\|r\s*=` | 只报前 2 处 | minor | gap |
| D-01 | 全文无设计词（`随机\|randomi\|队列\|cohort\|病例对照\|case-control\|横断面\|cross-sectional\|前后对照\|pre-post\|RCT\|回顾性\|前瞻性`） | 短文本豁免 | major | gap |
| D-02 | 有干预/暴露词（`治疗\|干预\|intervention\|用药\|dose\|剂量\|暴露`）但无 `对照\|control\|安慰剂\|placebo\|sham\|比较组\|comparator` | 单臂研究（single-arm）无对照属设计选择 → 降为 minor 并 suggestion 说明 | major/minor | judgment |
| D-03 | 有随机/干预且无 `盲\|blind\|masked` | 手术/器械类可豁免 → minor | minor | gap |
| D-04 | 全文无 `主要终点\|主要结局\|primary outcome\|primary endpoint\|主要指标` 且存在 ≥2 个结局指标 | 短文本豁免 | major | gap |
| D-05 | 方法节无 `定义\|判据\|标准\|defined as\|criteria\|operational` 而结果节有多变量分析 | — | minor | gap |
| D-06 | 切点句（`切点\|临界值\|cut-?off\|界值`）同句无 `文献\|ROC\|曲线下\|预设\|既往\|previous\|based on` | — | minor | judgment |
| D-07 | 全文无 `缺失\|missing\|插补\|imputation\|完整病例\|complete case` 且有 ≥2 变量分析 | — | minor | gap |
| C-01 | 正文 `[n]`（含 `[1,2]`、`[1-3]`）最大值 > 参考文献表条目数 | 参考文献表须成功识别；否则不触发 | major | error |
| C-02 | 参考文献表编号跨度内缺号 ≥1 个 | 只报首个缺口 | minor | error |
| C-03 | 正文 `(Smith et al., 2019)` 的姓氏不在参考文献表文本中 | 参考文献表须存在且 ≥5 条；只报前 3 个姓氏 | major | error |
| C-05 | 全文无 `参考文献\|References\|Bibliography` | 稿件 < 1500 字符时不判 | major | gap |
| E-01 | 有 `患者\|受试者\|participants\|patients\|小鼠\|大鼠\|mice\|rats\|动物` 且无 `伦理\|ethic\|IRB\|知情同意\|informed consent\|审批` | 综述/方法学文稿不触发；短文本豁免 | major | gap |
| E-02 | 无 `利益冲突\|conflict of interest\|competing interest\|COI` | 纯方法学/预印本可豁免；仍以 minor 报 | minor | gap |
| E-03 | 无 `基金\|资助\|funding\|grant\|supported by` | — | suggestion | gap |
| E-04 | 无 `数据可得\|data availability\|数据可用` | — | suggestion | gap |
| E-05 | 大写 2–6 字母缩写出现 ≥3 次、首次出现处无 `(...)` 或 `（...）` 展开 | 排除 `CI/OR/HR/RR/SD/SE/SPSS/ANOVA/DOI/PDF/IRB/COI/ROC/AUC/PCR/DNA/RNA/COVID` 等通用词 | suggestion | judgment |
| E-06 | 有明确设计词但无 `CONSORT\|STROBE\|PRISMA\|ARRIVE\|CARE\|reporting guideline` | — | suggestion | judgment |
| E-07 | `首次\|first report\|首次报道\|填补空白\|尚无报道` | 需同句有 `本研究` 或 `we` | minor | judgment |

## 3. 阶段 2 人工判定项（脚本不实现，必须在 `checks[].items[]` 留记录）

以下条目依赖语义理解，脚本只在 `checks{}` 中标 `manual` 并在 SKILL.md 中要求 Agent 逐条判定：

- D-09 研究问题与设计匹配（横断面回答疗效问题）
- L-01 结论强度超出支持（对照组缺失 + 绝对化结论）
- L-02 观察性数据因果化表述
- L-03 阴性结果阳性化
- L-04/L-05/L-06 讨论与结论一致性、推荐越界
- F-04 摘要—正文—表格跨节数值一致
- C-06 断言的引用支持
- S-13 回归变量筛选与前提
- S-06 的复杂变体（重复测量用 t 检验、聚类数据未用多层模型）

**人工判定项的落盘方式**：Agent 读取 `output/extracted/*.md` 后，把发现写进 `output/issues_model.json`
（数组，元素含 `rule_id/category/facet/severity/evidence_strength/locator_hint/quote/reason/suggestion/confidence`），
再运行 `main.py --merge`。脚本会对每条 `quote` 做**逐字回查**：
命中则并入 `issues[]`；未命中则移入 `pending_human`（`reason="quote_not_found_in_source"`），
**绝不把找不到原文的意见当作已确认结论输出**。

## 4. 缺陷类型库（用于 issue 归类与统计，可直接复用）

`stat_mismatch`（统计量与结论矛盾）、`reporting_gap_p`（p 值/CI 报告不足）、`multiplicity`（多重比较）、
`test_mismatch`（检验与数据结构不匹配）、`power_gap`（样本量/效能）、`sample_inconsistency`（样本量不一致）、
`num_inconsistency`（数值/百分比不自洽）、`cite_out_of_range`（引用越界）、`cite_missing_entry`（条目缺失）、
`design_reporting`（设计/对照/盲法未报告）、`endpoint_undefined`（主要终点缺失）、`variable_undefined`（变量定义）、
`cutoff_unsupported`（切点无依据）、`missing_data`（缺失值处理）、`causal_overreach`（因果越界）、
`negative_as_positive`（阴性阳性化）、`ethics_missing`（伦理声明）、`norms_missing`（声明类缺失）、
`abbrev_undefined`（缩略语）、`consistency_cross_section`（跨节数值）。

## 5. 已知误报源（Agent 必须主动排除）

1. 参考文献标题内含 `p` 值、`n =`（如统计学教材条目）→ 已在护栏 2 排除。
2. 方法节写"若不满足正态性则用 Mann-Whitney"（条件式正确做法）→ 护栏 3 排除。
3. 讨论节写"本研究未进行多重比较校正，属局限"→ 已披露，降级 suggestion。
4. 单臂可行性研究无对照组 → 设计选择，不判 major。
5. 表格转写导致同一数值出现两次不同格式（`0.03` vs `.03`）→ 归一化后比较，不算矛盾。
6. 中英文关键词只命中一侧 → 不构成"缺失"证据。

## 6 规则目录（机器可读，脚本直接加载）

本节末尾的 HTML 注释块是**唯一规则真源**：`scripts/main.py` 用起止标记（RULES-JSON 与 END-RULES-JSON）
抓取其中的 `{...}` 行并逐行 `json.loads`。新增规则只需追加一行 JSON 并在 `review_checklist.md` 登记 ID，无需改代码。

字段：`id cat facet dt sev es cf kind` + 判定字段（`pat`/`need`/`absent`/`guard_para`/`guard_global`/`cap`/`sev_if`）+ 文案字段（`title`/`reason`/`sug`/`terms`）。

`kind` 取值：`presence`（命中触发）、`absence`（全文缺失触发）、`tail`（文末声明缺失）、`manual`（脚本不判，交阶段 2 人工判定并在 checks 中标 manual）、`xref`/`sample`/`pct`/`sigconf`/`multi`/`refmax`/`refgap`（脚本内专门函数，含数值一致性计算）。

统计：共 46 条，其中自动检测 32 条、人工判定 14 条。

<!--RULES-JSON
{"id": "C-01", "cat": "citation", "facet": "reporting", "dt": "cite_out_of_range", "sev": "major", "es": "error", "cf": 0.85, "kind": "refmax", "title": "正文引用编号超出参考文献表范围", "reason": "正文引用编号大于参考文献表最大编号，该引用无对应条目，读者无法核查被引内容。", "sug": "补齐被引条目，或修正正文编号（常见为编号错位）。", "terms": "正文编号 max vs 条目数"}
{"id": "C-02", "cat": "citation", "facet": "reporting", "dt": "cite_missing_entry", "sev": "minor", "es": "error", "cf": 0.8, "kind": "refgap", "title": "参考文献编号缺号", "reason": "参考文献编号不连续，缺号会使正文引用与条目错位。", "sug": "重新连续编号，并同步更新正文引用。", "terms": "编号集合差"}
{"id": "C-03", "cat": "citation", "facet": "reporting", "dt": "cite_missing_entry", "sev": "major", "es": "judgment", "cf": 0.7, "kind": "manual", "title": "作者-年份引用在文献表中无对应条目", "reason": "逐个核对 (作者, 年份) 与文献表；条目缺失即该断言无来源。", "sug": "补齐条目或改引已列文献；二手引用注明“转引自”。", "terms": "surname vs reference list"}
{"id": "C-05", "cat": "citation", "facet": "reporting", "dt": "cite_missing_entry", "sev": "major", "es": "gap", "cf": 0.6, "kind": "absence", "need": "研究|本文|结果|study", "absent": "参考文献|references|bibliography|literature cited", "title": "稿件缺少参考文献表", "reason": "全文未出现参考文献表，正文即使有引用编号也无对应条目，任何文献支持的断言都无法核查。", "sug": "补齐与正文编号一一对应的参考文献表；若本稿为节选，在说明中标注。", "terms": "参考文献|References|Bibliography"}
{"id": "C-06", "cat": "citation", "facet": "reporting", "dt": "cite_missing_entry", "sev": "minor", "es": "judgment", "cf": 0.6, "kind": "manual", "title": "强断言缺少支持性引用", "reason": "既有知识类断言需要一条真正支持该具体说法的引用。", "sug": "附上与句意相符的引用，或弱化该句。", "terms": "claim-citation pairing"}
{"id": "D-01", "cat": "design", "facet": "design", "dt": "design_reporting", "sev": "major", "es": "gap", "cf": 0.68, "kind": "absence", "need": "患者|受试者|病例|样本|participants|patients|subjects|纳入", "absent": "随机|randomi|队列|cohort|病例对照|case-control|横断面|cross-sectional|前后对照|pre-post|RCT|回顾性|前瞻性|retrospective|prospective|自身对照", "title": "未明确报告研究设计类型", "reason": "全文未出现任何设计类型表述，无法判断设计与研究问题是否匹配，也无法评估偏倚控制与可推广性。", "sug": "在方法节首句明确设计（单中心前瞻性队列/随机双盲对照/横断面调查）及研究地点与时间窗。", "terms": "随机对照|队列|病例对照|横断面|回顾性|前瞻性", "skip_short": true}
{"id": "D-02", "cat": "design", "facet": "design", "dt": "design_reporting", "sev": "major", "es": "judgment", "cf": 0.65, "kind": "absence", "need": "治疗|干预|intervention|用药|剂量|暴露|护理|训练", "absent": "对照|control group|安慰剂|placebo|sham|比较组|comparator|对照组", "title": "干预性研究未设置或未描述对照组", "reason": "比较性结论需要可比参照；全文未出现对照/安慰剂/比较组表述，无法区分干预效应与时间趋势、回归均值或测量反应。", "sug": "说明分组与对照类型、随机化与分配隐藏；若为单臂设计须明确声明并在局限中说明。", "terms": "对照组|control|placebo|comparator", "sev_if": {"re": "单臂|single-arm|single arm", "sev": "minor"}}
{"id": "D-03", "cat": "design", "facet": "design", "dt": "design_reporting", "sev": "minor", "es": "gap", "cf": 0.55, "kind": "absence", "need": "随机|randomi", "absent": "盲|blind|masked", "title": "随机研究未报告盲法与分配隐藏", "reason": "未报告设盲对象（受试者/实施者/评估者）与分配隐藏方式时，无法排除实施偏倚与测量偏倚。", "sug": "补：双盲（受试者与结局评估者设盲）、随机序列生成方式与分配隐藏方法。", "terms": "盲法|blind|allocation concealment"}
{"id": "D-04", "cat": "design", "facet": "design", "dt": "endpoint_undefined", "sev": "major", "es": "gap", "cf": 0.66, "kind": "absence", "need": "结局|终点|指标|outcome|endpoint", "absent": "主要终点|主要结局|主要指标|primary (?:outcome|endpoint|efficacy)|主要观察指标|主要疗效指标|主要安全性指标", "title": "未事先指定主要终点", "reason": "缺主要终点声明时，多重结局中“挑显著者报告”的风险无法排除，读者也无从判断结论针对哪个终点。", "sug": "明确 1 个主要终点与其余次要终点，并给出判定时间点与测量方法。", "terms": "主要终点|主要结局|primary outcome", "skip_short": true}
{"id": "D-05", "cat": "design", "facet": "variables", "dt": "variable_undefined", "sev": "minor", "es": "gap", "cf": 0.6, "kind": "absence", "need": "回归|logistic|Cox|模型|model|多因素|多变量", "absent": "定义|判据|标准|defined as|criteria|operational", "title": "结局/暴露/协变量缺少操作性定义", "reason": "进入模型的关键变量未给操作性定义（测量方法、判定阈值、时间窗），不同中心会得到不同编码，变量类型与模型假设也无法核对。", "sug": "逐变量给出定义，如“高血压：收缩压≥140 mmHg 或正在服用降压药”。", "terms": "定义|判据|defined as|criteria"}
{"id": "D-06", "cat": "design", "facet": "variables", "dt": "cutoff_unsupported", "sev": "minor", "es": "judgment", "cf": 0.62, "kind": "presence", "cap": 2, "pat": "切点|临界值|界值|cut-?off|分为高|分为低|高分组|低分组|二分类|dichotomiz", "guard_para": "文献|ROC|曲线下|预设|既往|previous|based on|依据|参照", "title": "分类切点/二分类未说明依据", "reason": "连续变量按未说明来源的切点分组会丢失信息、降低效能，且存在事后择优风险。", "sug": "补充切点来源（既往文献或 ROC 约登指数），并以连续变量分析作为敏感性结果。", "terms": "切点|cutoff|ROC"}
{"id": "D-07", "cat": "design", "facet": "variables", "dt": "missing_data", "sev": "minor", "es": "gap", "cf": 0.6, "kind": "absence", "need": "变量|指标|数据|data", "absent": "缺失|missing|插补|imputation|完整病例|complete case|删除", "title": "未报告缺失值情况与处理", "reason": "缺失比例与处理方式（完整病例/多重插补）直接影响效应估计与有效样本量，未报告时结果不可复现。", "sug": "报告各变量缺失例数与比例，说明处理方法（如多重插补 m=20）并做完整病例分析的敏感性比较。", "terms": "缺失值|missing data|插补|imputation|完整病例"}
{"id": "D-08", "cat": "design", "facet": "variables", "dt": "variable_undefined", "sev": "suggestion", "es": "judgment", "cf": 0.55, "kind": "manual", "title": "协变量/亚组选择无依据", "reason": "无依据的协变量清单易导致过拟合与选择性报告。", "sug": "说明选择规则（预先的临床相关性/DAG），其余标为探索性。", "terms": "covariate list"}
{"id": "D-09", "cat": "design", "facet": "design", "dt": "design_reporting", "sev": "major", "es": "judgment", "cf": 0.7, "kind": "manual", "title": "设计无法回答所提问题", "reason": "把设计与断言对照：横断面数据不能支撑疗效或因果结论。", "sug": "把断言收窄为关联，或补充所需的纵向/对照设计。", "terms": "design vs aim"}
{"id": "F-01", "cat": "fact", "facet": "reporting", "dt": "num_inconsistency", "sev": "major", "es": "error", "cf": 0.8, "kind": "xref", "title": "正文引用的表/图编号在稿内不存在", "reason": "正文交叉引用指向的编号超出稿内已定义的表/图范围，读者无法定位被引对象。", "sug": "改用实际存在的编号，或在稿件中补齐缺失的表/图。", "terms": "表/图标题清单"}
{"id": "F-02", "cat": "fact", "facet": "sample_size", "dt": "sample_inconsistency", "sev": "major", "es": "error", "cf": 0.8, "kind": "sample", "cap": 1, "title": "样本量在稿内不一致", "reason": "同一稿件不同位置给出不同 n 且未见失访/排除说明，读者无法确定分析样本量，也无法核对统计量与自由度。", "sug": "统一入组/随机/分析各档样本量，并补受试者流程图说明差异来源。", "terms": "全文 n= 抽取"}
{"id": "F-03", "cat": "fact", "facet": "reporting", "dt": "num_inconsistency", "sev": "major", "es": "judgment", "cf": 0.82, "kind": "manual", "cap": 3, "title": "百分比与分子分母不自洽", "reason": "同句内 a/b 与报告百分比不符提示转写或计算错误；请逐格核对 p=a/b×100。", "sug": "按 a/b×100 复核该单元格并统一保留 1 位小数。", "terms": "同句 a/b 与 % 对照"}
{"id": "F-04", "cat": "fact", "facet": "reporting", "dt": "consistency_cross_section", "sev": "major", "es": "judgment", "cf": 0.7, "kind": "manual", "title": "摘要/正文/表格中同一统计量不一致", "reason": "逐节比对同一统计量；摘要—正文—表格互相矛盾属读者无法自行解决的硬错误。", "sug": "统一数值与舍入方式，每个统计量只报一次。", "terms": "abstract vs results vs table"}
{"id": "L-01", "cat": "logic", "facet": "reporting", "dt": "causal_overreach", "sev": "major", "es": "judgment", "cf": 0.72, "kind": "manual", "title": "结论强度超出结果支持", "reason": "把结论逐句映射到具体结果；缺支撑的疗效或因果断言是论证链上最严重的缺陷。", "sug": "把结论收窄到数据支持的范围，或补充缺失证据。", "terms": "conclusion vs results"}
{"id": "L-02", "cat": "logic", "facet": "design", "dt": "causal_overreach", "sev": "major", "es": "judgment", "cf": 0.7, "kind": "presence", "cap": 2, "pat": "导致|引起|造成|caus(?:e|es|ed)|leads? to", "guard_global": "随机|randomi|RCT|干预试验|动物实验", "title": "观察性证据被表述为因果关系", "reason": "稿件未报告随机化或干预分配，此处因果动词超出设计可支持的推断范围（横断面/队列只能支持关联）。", "sug": "改为关联表述，并在局限中说明残余混杂与反向因果的可能。", "terms": "导致|引起|cause|lead to"}
{"id": "L-03", "cat": "logic", "facet": "reporting", "dt": "negative_as_positive", "sev": "major", "es": "error", "cf": 0.75, "kind": "presence", "cap": 1, "pat": "无(?:统计学)?显著(?:性)?差异.{0,40}(?:说明|表明|提示).{0,20}(?:有效|改善|优于|获益)", "title": "阴性结果被解读为阳性", "reason": "组间差异无统计学意义时不能据此得出“有效/改善”，这把“未能证明差异”当作“证明有益”。", "sug": "改为“差异无统计学意义（P=…），提示作用有限/需更大样本验证”，并结合置信区间讨论精度。", "terms": "无显著差异+有效"}
{"id": "L-04", "cat": "logic", "facet": "reporting", "dt": "causal_overreach", "sev": "minor", "es": "judgment", "cf": 0.6, "kind": "manual", "title": "讨论中的比较无本文结果或引用支持", "reason": "讨论里的每个比较都应指向本文数据或已引研究。", "sug": "补上结果位置或引用，否则删除该比较。", "terms": "discussion claims"}
{"id": "L-05", "cat": "logic", "facet": "reporting", "dt": "causal_overreach", "sev": "minor", "es": "judgment", "cf": 0.6, "kind": "manual", "title": "结论未回应主要终点", "reason": "核对结论是否针对主要终点，是否引入未检验的指标。", "sug": "围绕主要终点结果重写结论。", "terms": "conclusion vs primary endpoint"}
{"id": "L-06", "cat": "logic", "facet": "reporting", "dt": "causal_overreach", "sev": "suggestion", "es": "judgment", "cf": 0.55, "kind": "manual", "title": "推荐/建议超出数据适用范围", "reason": "临床或政策建议必须落在所研究人群与设计能覆盖的范围内。", "sug": "限定建议的适用人群，或明确标为待验证假设。", "terms": "recommendation scope"}
{"id": "E-01", "cat": "norms", "facet": "design", "dt": "ethics_missing", "sev": "major", "es": "gap", "cf": 0.62, "kind": "absence", "need": "患者|受试者|志愿者|participants|patients|小鼠|大鼠|mice|rats|动物|animal", "absent": "伦理|ethic|IRB|知情同意|informed consent|审批|approval|委员会", "title": "人体/动物研究缺少伦理审批与知情同意声明", "reason": "涉及人/动物受试者的研究，ICMJE 与期刊要求声明伦理批准编号与知情同意获取方式，缺失属硬性规范缺陷。", "sug": "补：本研究经…伦理委员会批准（批号），全部受试者签署知情同意书。", "terms": "伦理审批|IRB|知情同意|informed consent", "skip_short": true}
{"id": "E-02", "cat": "norms", "facet": "reporting", "dt": "norms_missing", "sev": "minor", "es": "gap", "cf": 0.55, "kind": "tail", "need": "", "absent": "利益冲突|conflict of interest|competing interest|\\bCOI\\b", "title": "缺少利益冲突声明", "reason": "全文检索未发现利益冲突声明段落；多数期刊将其列为投稿必备项。", "sug": "在文末补“利益冲突：所有作者声明无利益冲突”，或据实披露。", "terms": "利益冲突|conflict of interest"}
{"id": "E-03", "cat": "norms", "facet": "reporting", "dt": "norms_missing", "sev": "suggestion", "es": "gap", "cf": 0.5, "kind": "tail", "need": "", "absent": "基金|资助|funding|grant|supported by|课题", "title": "缺少基金/资助声明", "reason": "全文检索未发现资助来源声明；资助信息影响对研究独立性与利益关联的判断。", "sug": "补资助来源与编号，或声明无资助。", "terms": "基金|资助|funding|grant"}
{"id": "E-04", "cat": "norms", "facet": "reporting", "dt": "norms_missing", "sev": "suggestion", "es": "gap", "cf": 0.5, "kind": "tail", "need": "", "absent": "数据可得|数据可用|数据共享|data availability|available from", "title": "缺少数据可得性声明", "reason": "全文检索未发现数据可得性声明，读者无法知晓原始数据能否获取及获取条件。", "sug": "补数据可得性声明或去标识数据仓库链接。", "terms": "数据可得性|data availability"}
{"id": "E-05", "cat": "norms", "facet": "reporting", "dt": "abbrev_undefined", "sev": "suggestion", "es": "judgment", "cf": 0.55, "kind": "manual", "title": "缩略语重复使用但未展开", "reason": "首次出现处无展开式的缩略语会迫使读者猜测；核查出现 ≥3 次的全部缩略语。", "sug": "首次出现写成：中文全称（English full term, ABBR）。", "terms": "abbreviations at first use"}
{"id": "E-06", "cat": "norms", "facet": "reporting", "dt": "norms_missing", "sev": "suggestion", "es": "gap", "cf": 0.5, "kind": "absence", "need": "随机|队列|病例对照|横断面|randomi|cohort", "absent": "CONSORT|STROBE|PRISMA|ARRIVE|CARE|reporting guideline|报告规范", "title": "未声明遵循的报告规范", "reason": "设计类型已明确但未声明遵循相应报告规范（RCT→CONSORT，观察性→STROBE），条目级完整性无法核对。", "sug": "声明遵循的报告规范并附条目完成清单作为补充材料。", "terms": "CONSORT|STROBE|PRISMA|ARRIVE|CARE"}
{"id": "E-07", "cat": "norms", "facet": "design", "dt": "norms_missing", "sev": "minor", "es": "judgment", "cf": 0.55, "kind": "presence", "cap": 1, "pat": "首次(?:报道|发现|提出|证实)|填补.{0,4}空白|尚无(?:报道|研究)|first report", "guard_para": "本研究|本文|we |our ", "title": "出现不可核验的优先权声明", "reason": "“首次报道/填补空白”需穷尽检索支撑，本稿未给检索范围与时间窗，属不可核验声明。", "sug": "删除该表述，或改为“据我们所知（检索至某年某月，数据库：X）”并说明检索策略。", "terms": "首次|first report|填补空白"}
{"id": "S-01", "cat": "statistics", "facet": "reporting", "dt": "reporting_gap_p", "sev": "minor", "es": "gap", "cf": 0.7, "kind": "presence", "cap": 2, "pat": "[Pp]\\s*[<≤]\\s*0?\\.0?5|[Pp]\\s*>\\s*0\\.05", "guard_para": "[Pp]\\s*=\\s*0?\\.\\d+|为差异有统计学意义|差异具有统计学意义|显著性水平|检验水准|统计显著性", "title": "p 值仅给不等式", "reason": "仅报 P<0.05 时读者无法判断真实显著性水平，也无法复算或纳入 meta 分析。", "sug": "改为精确 p 值（2–3 位有效数字），极小值统一写作 P<0.001。", "terms": "P<0.05|P>0.05"}
{"id": "S-02", "cat": "statistics", "facet": "reporting", "dt": "stat_mismatch", "sev": "major", "es": "error", "cf": 0.75, "kind": "sigconf", "title": "显著性结论与 p 值方向矛盾", "reason": "同段内“显著”结论与所列 p 值（≥0.05）不相容，或“无显著差异”与 p<0.05 并存。", "sug": "按 p 值改写结论，或核对 p 值对应的比较组是否配对正确。", "terms": "同段共现"}
{"id": "S-03", "cat": "statistics", "facet": "reporting", "dt": "reporting_gap_p", "sev": "major", "es": "gap", "cf": 0.7, "kind": "absence", "need": "[Pp]\\s*[=<>≤]\\s*0?\\.\\d", "absent": "95\\s*%\\s*(?:CI|置信)|置信区间|效应量|effect size|\\bOR\\b|\\bHR\\b|\\bRR\\b|风险比|均数差|mean difference", "title": "只报 p 值，未报效应量与置信区间", "reason": "p 值不反映差异大小与精度；缺效应量与 95%CI 时读者无法判断实际意义（CONSORT/STROBE 要求报告效应量及其精度）。", "sug": "为主要比较补效应量与 95%CI，如 MD=1.8（95%CI 0.6–3.0）或 OR=1.42（95%CI 1.05–1.92）。", "terms": "95%CI|置信区间|效应量|OR|HR|RR|mean difference", "skip_short": true}
{"id": "S-04", "cat": "statistics", "facet": "statistics", "dt": "multiplicity", "sev": "major", "es": "gap", "cf": 0.7, "kind": "multi", "title": "多组比较未做多重比较校正", "reason": "稿内检出多处组间比较并给出 p 值，但全文未见多重比较校正；比较次数增加会抬高 I 类错误率。", "sug": "说明校正方法（Holm-Bonferroni/FDR）与校正后阈值，或声明这些比较为探索性并弱化结论。", "terms": "多重比较|校正|Bonferroni|Holm|Tukey|FDR"}
{"id": "S-05", "cat": "statistics", "facet": "statistics", "dt": "test_mismatch", "sev": "major", "es": "gap", "cf": 0.72, "kind": "absence", "need": "[Pp]\\s*[=<>≤]\\s*0?\\.\\d", "absent": "t\\s*检验|t-test|student|ANOVA|方差分析|χ2|χ²|卡方|Mann-Whitney|Wilcoxon|Kruskal|Fisher|log-rank|回归|regression|mixed model|混合模型|秩和", "title": "未报告统计检验方法", "reason": "给出 p 值但全文未出现任何检验名称，读者无法判断检验是否匹配数据结构（分布、配对、组数），也无法复算。", "sug": "在方法节逐一列出每个终点所用检验、软件版本与显著性水平。", "terms": "t检验|ANOVA|χ²|Mann-Whitney|Wilcoxon|Kruskal|回归", "skip_short": true}
{"id": "S-06", "cat": "statistics", "facet": "statistics", "dt": "test_mismatch", "sev": "major", "es": "judgment", "cf": 0.72, "kind": "manual", "title": "检验方法与数据分布/配对/聚类结构不匹配", "reason": "对照所报集中趋势与离散度（中位数/IQR vs 均数±SD）、配对与重复测量结构，核对所用检验的前提。", "sug": "改用与分布/结构匹配的检验，或报告支撑该选择的前提检验结果。", "terms": "median/IQR vs t-test; paired vs independent"}
{"id": "S-07", "cat": "statistics", "facet": "statistics", "dt": "test_mismatch", "sev": "minor", "es": "gap", "cf": 0.62, "kind": "absence", "need": "\\bt\\s*检验|t-test|ANOVA|方差分析", "absent": "正态|normal(?:ity)?|Shapiro|Kolmogorov|方差齐|Levene|homogen", "title": "参数检验未报告正态性/方差齐性检验", "reason": "t 检验与 ANOVA 的前提是近似正态与方差齐性，未报告前提检验时无法判断方法选择是否恰当。", "sug": "补 Shapiro-Wilk 与 Levene 检验结果，并说明不满足前提时的替代策略。", "terms": "正态性|Shapiro-Wilk|Kolmogorov-Smirnov|Levene", "skip_short": true}
{"id": "S-08", "cat": "statistics", "facet": "sample_size", "dt": "power_gap", "sev": "major", "es": "gap", "cf": 0.7, "kind": "absence", "need": "组间|两组|三组|compared|versus|\\bvs\\b|比较", "absent": "样本量(?:估算|计算|确定|估计)|sample size|检验效能|把握度|\\bpower\\b|最少需要|计算.{0,6}例", "title": "未报告样本量估算依据", "reason": "方法节未出现样本量估算、效应量来源、α 与把握度设定，读者无法判断实际样本能否检出目标效应（STROBE 条目 10）。", "sug": "补：基于效应量 d=（来源）、α=0.05（双侧）、把握度 80% 需每组 n=；并给出实际样本对应的可检出效应量。", "terms": "样本量估算|sample size|检验效能|power|把握度", "skip_short": true}
{"id": "S-09", "cat": "statistics", "facet": "sample_size", "dt": "power_gap", "sev": "major", "es": "judgment", "cf": 0.65, "kind": "manual", "title": "计划样本与实际分析样本不符且未解释", "reason": "比对计划样本与实际 n；未解释的缺口直接改变检验效能与偏倚方向。", "sug": "报告入组/随机/分析三档人数及每一步减少的原因。", "terms": "planned n vs analysed n"}
{"id": "S-10", "cat": "statistics", "facet": "sample_size", "dt": "power_gap", "sev": "minor", "es": "gap", "cf": 0.6, "kind": "absence", "need": "随访|follow-up|随访期|个月后|周后|年后", "absent": "失访|脱落|退出|withdraw|dropout|lost to|剔除|依从性", "title": "纵向研究未报告失访与脱落", "reason": "有随访的稿件未报告失访人数、原因与处理，实际分析样本可能少于入组样本，存在 attrition bias。", "sug": "补受试者流程图，并比较失访者与完成者的基线特征。", "terms": "失访|脱落|退出|dropout|lost to follow-up"}
{"id": "S-11", "cat": "statistics", "facet": "variables", "dt": "cutoff_unsupported", "sev": "minor", "es": "judgment", "cf": 0.6, "kind": "manual", "title": "连续变量被二分类，损失信息", "reason": "二分类会丢信息并降低效能；需核查是否同时给出连续变量分析。", "sug": "补充以连续变量分析的敏感性结果。", "terms": "high/low groups"}
{"id": "S-12", "cat": "statistics", "facet": "statistics", "dt": "reporting_gap_p", "sev": "suggestion", "es": "gap", "cf": 0.55, "kind": "absence", "need": "[Pp]\\s*[=<>≤]\\s*0?\\.\\d", "absent": "SPSS|SAS\\b|Stata|GraphPad|Statistica|MedCalc|软件|software|Python|R\\s*(?:\\(|软件|version)", "title": "未报告统计软件与版本", "reason": "不同软件默认算法与舍入处理不同（如 χ² 连续性校正、混合模型自由度），缺软件信息会妨碍复现。", "sug": "补：所有分析使用 SPSS 26.0（IBM, Armonk, NY）完成，双侧 P<0.05 为差异有统计学意义。", "terms": "SPSS|SAS|Stata|R|GraphPad|软件版本"}
{"id": "S-13", "cat": "statistics", "facet": "statistics", "dt": "test_mismatch", "sev": "minor", "es": "judgment", "cf": 0.6, "kind": "manual", "title": "回归的变量筛选与前提检验未报告", "reason": "逐步筛选、共线性与风险比例/线性前提会实质改变估计值。", "sug": "报告筛选流程、共线性诊断与前提检验结果。", "terms": "model building"}
{"id": "S-14", "cat": "statistics", "facet": "reporting", "dt": "reporting_gap_p", "sev": "suggestion", "es": "judgment", "cf": 0.6, "kind": "presence", "cap": 2, "pat": "[Pp]\\s*=\\s*0?\\.0{2,}\\b|[Pp]\\s*<\\s*\\.\\d", "title": "p 值格式不规范", "reason": "P=0.000 在数学上不可能，省略前导零（P<.05）不利于跨语言排版与自动化解析。", "sug": "改为 P<0.001，并统一保留前导零。", "terms": "P=0.000|P<.05"}
{"id": "S-15", "cat": "statistics", "facet": "reporting", "dt": "reporting_gap_p", "sev": "minor", "es": "gap", "cf": 0.62, "kind": "presence", "cap": 2, "pat": "[Pp]\\s*[=<>≤]\\s*0?\\.\\d{1,4}", "guard_para": "\\bt\\s*=|\\bF\\s*=|\\bχ|\\bchi|\\bz\\s*=|\\br\\s*=|\\bU\\s*=|\\bH\\s*=|为差异有统计学意义|差异具有统计学意义|显著性水平|检验水准", "title": "只给 p 值未给检验统计量与自由度", "reason": "缺 t/F/χ² 值与自由度时，读者无法核对检验是否用对、样本量与自由度是否自洽，也无法复算 p 值。", "sug": "在 p 值前补统计量与自由度，如 t(38)=2.41, P=0.021。", "terms": "t=|F=|χ²=|df"}
END-RULES-JSON-->
