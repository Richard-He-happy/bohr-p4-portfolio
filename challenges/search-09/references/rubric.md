# 评价量表（rubric）· v1.0.0

## 0. 定位、来源与免责

本量表是**本 Skill 自建的、可复现的判定规则集**，用于把"研究设计—证据—偏倚—报告"拆成可逐条判断的条目。它**不是**任何外部量表的官方评分，也不输出 ROBINS-I / RoB 2 / AMSTAR 2 / PROBAST / GRADE / STROBE / PRISMA 的官方分级；不声称与上述工具的条目一一对应，也不引用其分值阈值（那些工具需按其官方手册执行，本 Skill 不代行）。

结构上参照了上述工具通用的问题分解方式（偏倚领域按"选择/混杂/实施/测量/缺失/报告"划分；系统评价另加检索、双人筛选、异质性、发表偏倚；诊断准确性另加参考标准与谱偏倚；预测模型另加校准与验证）。上述工具的正式条目与阈值请查其官方出版物。**本量表的一切阈值均由第 5 节明文给出，任何人可按同一算式复现同一等级。**

机器可读条目库在 §2 的 ```json 块内；`scripts/appraise.py` 启动时读取该块，缺失时用内置精简库并记 `degradations`。修改条目**不需要改代码**。

## 1. 维度定义

| 维度 | 代码 | 要回答的问题 | 允许的判定 |
|---|---|---|---|
| 研究设计 | D1 | 这个设计能否支持它的结论？对象、对照、随访是否交代清楚 | reported / partially_reported / not_reported / unappraisable |
| 证据充分性 | D2 | 结局、效应量、精度、样本量依据、混杂控制、稳健性是否支撑结论 | 同上 |
| 偏倚风险 | D3 | 风险落在哪个具体环节（六个领域） | 明确存在 / 可能存在 / 未见迹象 / 证据不足 |
| 报告完整性 | D4 | 必须报告项（数值、局限、利益冲突、注册、统计方法）缺了哪些 | reported / partially_reported / not_reported / unappraisable |
| 类型特有 | T | 该设计独有检查点（随机化/匹配/检索策略/校准…） | 同 D1 |

## 2. 条目库（机器可读）

字段：`id`、`dim`、`label`、`types`（适用设计，`*`=全部）、`req`（证据应出现的区域：`any` 不限、`methods` 方法区优先、`results` 结果区优先）、`w`（权重，默认 1）、`any`（命中任一词）、`all`（须同时出现）。

```json
{"rubric_version":"1.0.0","items":[
{"id":"D1.1","dim":"D1","label":"研究设计明确表述","types":["*"],"req":"any","w":1,"any":["randomized controlled trial","randomised controlled trial","randomized","randomised","cohort study","prospective cohort","retrospective cohort","case-control","case control","cross-sectional","cross sectional","nested case","population-based","nationwide","registry-based","systematic review","meta-analysis","observational study","longitudinal study","phase ii","phase iii","clinical trial"]},
{"id":"D1.2","dim":"D1","label":"研究目的与研究问题明确","types":["*"],"req":"any","w":1,"any":["we aimed","we aim","the aim of","the objective of","our objective","primary objective","we investigated","we examined","we tested the hypothesis","we hypothesized","research question","this study aimed"]},
{"id":"D1.3","dim":"D1","label":"纳入与排除标准","types":["rct","cohort","case_control","cross_sectional","diagnostic","other"],"req":"methods","w":1,"any":["inclusion criteria","exclusion criteria","were eligible","eligibility criteria","were included if","were excluded if","enrolled patients","consecutive patients","inclusion and exclusion"]},
{"id":"D1.4","dim":"D1","label":"研究现场、时间与对象来源","types":["*"],"req":"methods","w":1,"any":["single-center","single centre","multicenter","multi-centre","tertiary","hospital","clinics","population-based registry","from january","between 19","between 20","during the period","recruited from","study setting","general practice"]},
{"id":"D1.5","dim":"D1","label":"样本量与抽样方式","types":["*"],"req":"methods","w":1,"any":["sample size","consecutive","random sample","we enrolled","a total of","were recruited","participants were","patients were","n = ","n=","subjects were"]},
{"id":"D1.6","dim":"D1","label":"对照/比较组定义与分组方式","types":["rct","case_control","cross_sectional","other"],"req":"methods","w":1,"any":["control group","comparator","compared with","reference group","usual care","placebo","non-exposed","unexposed","matched controls","control participants","were compared"]},
{"id":"D1.7","dim":"D1","label":"随访时长、完整性与失访","types":["rct","cohort","case_control"],"req":"methods","w":1,"any":["follow-up","followed for","median follow-up","lost to follow-up","person-years","dropout","dropped out","attrition","censored","follow up period"]},
{"id":"D2.1","dim":"D2","label":"主要结局定义与测量工具","types":["*"],"req":"methods","w":1,"any":["primary outcome","primary endpoint","main outcome","outcomes were","outcome was defined","measured by","assessed using","adjudicated","defined as","ascertained"]},
{"id":"D2.2","dim":"D2","label":"效应量与精度（CI/SE/p）","types":["*"],"req":"results","w":2,"any":["hazard ratio","odds ratio","risk ratio","relative risk","confidence interval","95% ci","mean difference","incidence rate ratio","rate ratio","adjusted hr","adjusted or","beta coefficient","p =","p<","p <","i2","standardized mean difference"]},
{"id":"D2.3","dim":"D2","label":"样本量依据或把握度","types":["*"],"req":"methods","w":1,"any":["power calculation","power of","sample size calculation","sample size was calculated","detectable difference","to detect a","we calculated that","powered to"]},
{"id":"D2.4","dim":"D2","label":"混杂控制与多变量调整","types":["cohort","case_control","cross_sectional","other"],"req":"methods","w":2,"any":["adjusted for","multivariable","multivariate","propensity score","matched on","stratified by","covariates","confounder","confounding","inverse probability","doubly robust"]},
{"id":"D2.5","dim":"D2","label":"敏感性、亚组或稳健性分析","types":["*"],"req":"results","w":1,"any":["sensitivity analysis","subgroup analysis","subgroup analyses","e-value","alternative","robustness","stratified analysis","excluding participants"]},
{"id":"D2.6","dim":"D2","label":"结论与数据的一致性","types":["*"],"req":"any","w":2,"any":["was associated with","were associated with","no significant association","no association","we found","we conclude","in conclusion","these findings suggest","the results suggest"]},
{"id":"D4.1","dim":"D4","label":"关键数值逐项报告（分母/比例/缺失）","types":["*"],"req":"results","w":1,"any":["n (%)","n(%)","number of","proportion of","percentage","missing data","were missing","% of","per 1000","per 100"]},
{"id":"D4.2","dim":"D4","label":"局限性、利益冲突与资助","types":["*"],"req":"any","w":1,"any":["limitation","residual confounding","confounding by indication","caution","conflict of interest","competing interests","funding","funded by","grant"]},
{"id":"D4.3","dim":"D4","label":"注册、方案或数据可得性","types":["*"],"req":"any","w":1,"any":["registered","registration number","clinicaltrials.gov","isrctn","prospero","study protocol","data availability","data are available","available from the corresponding author","osf"]},
{"id":"D4.4","dim":"D4","label":"统计方法与软件可追溯","types":["*"],"req":"methods","w":1,"any":["statistical analysis","were performed using","software","sas version","stata","r version","spss","cox proportional","logistic regression","poisson regression","mixed-effects"]},
{"id":"D4.5","dim":"D4","label":"图表与补充材料可核对","types":["*"],"req":"any","w":1,"any":["table 1","table 2","figure 1","figure 2","supplementary table","supplementary figure","appendix","e-table"]},
{"id":"T.rct.1","dim":"T","label":"随机序列生成","types":["rct"],"req":"methods","w":2,"any":["random sequence","computer-generated","computer generated","random number","block randomization","block randomisation","stratified randomization","randomization list","randomly assigned"]},
{"id":"T.rct.2","dim":"T","label":"分配隐藏","types":["rct"],"req":"methods","w":2,"any":["allocation concealment","sealed envelope","central randomization","sequentially numbered","web-based randomization","independent statistician","opaque envelope"]},
{"id":"T.rct.3","dim":"T","label":"盲法实施","types":["rct","diagnostic"],"req":"methods","w":2,"any":["double-blind","double blind","single-blind","single blind","blinded","masked","open-label","open label","sham"]},
{"id":"T.rct.4","dim":"T","label":"分析集与缺失处理（ITT/PP）","types":["rct"],"req":"methods","w":1,"any":["intention-to-treat","intention to treat","per-protocol","per protocol","as-treated","multiple imputation","last observation carried forward","complete case"]},
{"id":"T.coh.1","dim":"T","label":"队列界定与随访完整性","types":["cohort"],"req":"methods","w":2,"any":["cohort was defined","entered the cohort","included in the cohort","follow-up rate","completeness of follow-up","person-years","were censored","end of follow-up"]},
{"id":"T.cc.1","dim":"T","label":"病例与对照的来源、匹配与回忆偏倚","types":["case_control"],"req":"methods","w":2,"any":["cases were","controls were","matched controls","population-based controls","hospital controls","recall bias","interviewer","proxy interview"]},
{"id":"T.cs.1","dim":"T","label":"抽样代表性与应答率","types":["cross_sectional"],"req":"methods","w":2,"any":["response rate","participation rate","random sampling","representative sample","survey","questionnaire","non-responders"]},
{"id":"T.sr.1","dim":"T","label":"检索策略与数据库覆盖","types":["systematic_review"],"req":"methods","w":2,"any":["we searched","pubmed","medline","embase","cochrane library","web of science","scopus","search strategy","from inception","reference lists"]},
{"id":"T.sr.2","dim":"T","label":"双人筛选与数据提取","types":["systematic_review"],"req":"methods","w":2,"any":["two reviewers independently","two authors independently","screened independently","duplicate","kappa","disagreements were resolved","consensus"]},
{"id":"T.sr.3","dim":"T","label":"偏倚风险工具、异质性与发表偏倚","types":["systematic_review"],"req":"results","w":2,"any":["risk of bias","newcastle-ottawa","robins","rob 2","i2","heterogeneity","random-effects","random effects","publication bias","funnel plot","egger"]},
{"id":"T.sr.4","dim":"T","label":"方案注册与报告规范","types":["systematic_review"],"req":"any","w":1,"any":["prospero","prisma","registered protocol","protocol was registered"]},
{"id":"T.dta.1","dim":"T","label":"参考标准、判读盲法与谱偏倚","types":["diagnostic"],"req":"methods","w":2,"any":["reference standard","index test","blinded to the reference","2x2","two-by-two","sensitivity and specificity","spectrum bias","consecutive patients"]},
{"id":"T.pred.1","dim":"T","label":"模型校准、区分度与验证","types":["prediction"],"req":"results","w":2,"any":["calibration","discrimination","c-statistic","c statistic","auc","external validation","internal validation","bootstrapping","events per variable","overfitting","net reclassification"]},
{"id":"T.qual.1","dim":"T","label":"定性方法严谨性","types":["qualitative"],"req":"methods","w":2,"any":["thematic analysis","saturation","triangulation","coding","purposive sampling","semi-structured interviews","member checking","reflexivity"]}
]}
```

## 3. 判定规则（D1/D2/D4/T 通用）

在**句级**检索：把正文切成句子（`。.!?` 与换行处切分，缩写 `et al.` / `e.g.` / `i.e.` / `vs.` 不切），对每条句子跑该条目全部探针（`any` 命中至少 1 个词，`all` 若给出则须同时命中），按命中词数与区域加权取最高分句。

| 判定 | 触发条件 | 必带字段 |
|---|---|---|
| `reported` | 最佳句得分 ≥1 **且**句所在区与 `req` 相符（`methods`/`results` 要求命中该区；`any` 不限），且有至少 1 个数值/术语证据 | quote + 页码 + 章节 + char_start |
| `partially_reported` | 命中但区域不符（例：`req=methods` 只在 Abstract 命中），或只命中泛化词、缺具体数值 | 同上 + `evidence_scope` |
| `not_reported` | **全文可得**、探针在全文跑过、无任何命中——这是"报告缺项"，本身是可评价结论 | 无需 quote，须带 `searched_chars` 与 `probe_count` |
| `unappraisable` | 文本不可得（仅摘要/无文本/乱码）、该条目对该设计不适用、或 quote 校验失败 | `abstain_reason` |

**禁止**：把 `not_reported` 用于"我只读了摘要"；把 `unappraisable` 用成"懒得判断"。二者区别是"读过全文但没有"与"没读到全文"。

## 4. 偏倚领域（D3）映射与四档判据

| 领域 | 主证据条目 | 判为「明确存在」 | 判为「可能存在」 | 判为「未见迹象」 | 判为「证据不足」 |
|---|---|---|---|---|---|
| 选择偏倚 selection | D1.1, D1.3, D1.4, D1.5, D1.6 | 无纳入标准且抽样为方便样本/来源不明 | 有纳入标准但抽样方式或对象来源缺失 | 对象来源、抽样与对照形成方式均已报告 | 相关条目均无法评价 |
| 混杂 confounding | D2.4, D1.6 | 未做任何混杂控制且正文自述存在组间差异（观察性设计） | 仅单变量分析或调整变量未列出 | 多变量/匹配/倾向评分报告完整 | 相关条目均无法评价 |
| 实施偏倚 performance | T.rct.1–T.rct.3 | 随机化与分配隐藏均无且非盲 | 有随机化但隐藏或盲法缺一项 | 随机、隐藏、盲法均已报告 | 相关条目均无法评价 |
| 测量/检出 detection | D2.1, T.rct.3, T.dta.1 | 结局判定方法未定义且判读者非盲 | 有定义但判定者盲法或工具效度未报告 | 结局定义、工具与判读均报告 | 相关条目均无法评价 |
| 失访 attrition | D1.7, D4.1 | 失访比例高且未做敏感性分析 | 报告失访但无缺失机制或敏感性分析 | 随访完整性与失访处理均报告 | 相关条目均无法评价 |
| 选择性报告 reporting | D2.6, D4.3, T.sr.4 | 结论强度明显超出数据（如无显著差异仍称"有效"）或结局与注册不一致 | 无注册/方案，结局定义事后调整迹象 | 有注册或方案且结局与之一致 | 相关条目均无法评价 |

系统性评价额外把 `T.sr.1`（检索不全）、`T.sr.3`（未评偏倚或未查发表偏倚）计入 selection 与 reporting 两个领域，规则同上。

## 5. 分级阈值与 grade_trace 算式

```
applicable_items = 对该设计适用的条目（types 命中 * 或该设计）
judged_items     = 判定为 reported / partially_reported / not_reported 的条目数
coverage         = judged_items / applicable_items            # 0..1
bias_points      = 2*明确存在 + 1*可能存在 + 0.5*证据不足      # 六个领域累加
```

`overall_risk` 按顺序取第一条命中：

1. `coverage < 0.40` 或 `applicable_items == 0` → `unappraisable`
2. 任一关键领域（selection / confounding / reporting）为 明确存在，或 `bias_points ≥ 4.0` → `high`
3. `bias_points ≥ 1.0` → `some_concerns`（例：3 个领域「可能存在」= 3.0，仍属 some_concerns，不升为 high）
4. `coverage ≥ 0.60` → `low`
5. 其余 → `some_concerns`

`confidence`：`text_source` 为全文且 `coverage ≥ 0.70` → `high`；全文且 `≥ 0.40` → `moderate`；仅摘要或无文本 → `low`。

`grade_trace` 必须写入 `result.json.grades[].grade_trace`：`{applicable, judged, coverage, bias_points, per_domain:[{domain,grade,points,basis_item_ids}], rule_fired:"R2", formula:"bias_points = 2*1 + 1*0 + 0.5*0 = 2.0"}`。缺轨迹即视为未完成分级。

## 6. 适用矩阵（研究设计 × 条目组）

| 设计 | 必评条目组 | 说明 |
|---|---|---|
| `rct` | D1 全部、D2 全部、D4 全部、T.rct.* | 侧重随机化、隐藏、盲法、分析集 |
| `cohort` | D1 全部（D1.6 仅在有对照组时评）、D2 全部、D4 全部、T.coh.1 | 侧重队列界定、随访、混杂；单臂队列缺 D1.6 不记为缺项 |
| `case_control` | D1 全部、D2 除 D2.3、D4 全部、T.cc.1 | 侧重来源与回忆偏倚 |
| `cross_sectional` | D1 除 D1.7、D2 全部、D4 全部、T.cs.1 | 侧重代表性、应答率、不可推因果 |
| `systematic_review` | D1 除 D1.6/D1.7、D2.2/D2.5/D2.6、D4 全部、T.sr.* | 侧重检索、双人、异质性、发表偏倚 |
| `diagnostic` | D1.1–D1.5、D2.1/D2.2、D4 全部、T.dta.1、T.rct.3 | 侧重参考标准与谱偏倚 |
| `prediction` | D1 全部、D2 全部、D4 全部、T.pred.1 | 侧重校准、验证、过拟合 |
| `qualitative` | D1、D4、T.qual.1 | 不套用效应量条目，`D2.2` 记 `unappraisable` 并说明降级 |
| `other` | D1、D2、D4 | 保守取通用条目，类型特有项在 `uncertainty` 说明未覆盖 |

## 7. 弃权（abstention）规则

1. 仅有摘要 → 全条目上限 `partially_reported`/`unappraisable`，`overall_risk` 仍可给但 `confidence:"low"`，`uncertainty` 记 `abstract_only`。
2. 文本乱码或非目标语言无法解析 → `text_source:"none"`，全条目 `unappraisable`，`overall_risk:"unappraisable"`。
3. quote 校验失败 → 该条降为 `unappraisable`，进 `pending_human`（reason `quote_not_found`），**不改原文**。
4. 设计无法识别 → 只跑 D1/D2/D4，`T` 组条目记 `unappraisable`（`abstain_reason:"design_undetermined"`），`uncertainty` 记一条。

## 8. 已知局限

- 句级探针是**词面匹配**，同义改写（如 "we accounted for" 代替 "adjusted for"）会漏检 → 漏检记为 `not_reported` 而非"原文没有"，正文措辞必须写成"本工具未检出可直接引用的表述"。
- 表格内数值若 PDF 文本层缺失（矢量图/扫描）无法抽取 → 记 `pending_human:"table_text_missing"`，不用图像推测。
- 语言：中/英文词表分别内置；其他语言仅做通用结构与数值探测，`uncertainty` 说明。
- 不评估真实世界效应、不核验数据真实性（仅核验"原文是否这样说"），不判断临床意义。
