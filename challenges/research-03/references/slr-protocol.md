# SLR protocol and message templates

This file is **read at runtime** by `scripts/slr_review.py` and `scripts/verify.py`.
The `<!--slr:msg ... -->` block below holds every user-facing string as
`key|中文|English`. Edit the text freely; keep the keys and the `|` columns.
A missing key degrades to the bare key name (no crash).

## 1. Search protocol template (how the query is built)

1. **Decompose** the question into `population` / `intervention or exposure` /
   `outcome` (+ optional `comparison`, `design`, `time frame`, `language`).
   Take only elements that the case actually states; mark heuristic derivations.
2. **Expand** each element with word-form variants (plural, `-ies`→`-y`, `-ing`)
   and, when the case supplies keywords or a thesaurus, with those terms.
   Never invent MeSH/Emtree descriptors: the vocabulary block is only asserted
   when a controlled list is present in the input.
3. **Compose** one block per element, `AND` between blocks, `OR` inside.
   Record the intent of each block, the fields searched (`title`, `abstract`,
   `keywords`) and the limits (time window, language).
4. **Execute** what can be executed here: the string is run against the supplied
   corpus (in-corpus hit counts, per block, plus the record set that satisfies all
   blocks). Database hit counts are *not* available offline and are never claimed.

## 2. Eligibility clause library (versioned, frozen before screening)

| id | type | priority | machine rule | intent |
|---|---|---|---|---|
| IC1 | include | 2 | `core_term_hits >= k` | topic relevance |
| IC2 | include | 3 | empirical markers present | empirical study |
| IC3 | include | 3 | outcome/result markers present | reports a result |
| EC1 | exclude | 1 | `core_term_hits == 0` | off-topic |
| EC2 | exclude | 2 | population marker absent | wrong population |
| EC3 | exclude | 1 | editorial/erratum marker and no data | non-empirical item |
| EC4 | exclude | 3 | review-type item without primary data | no usable outcome data |
| EC6 | exclude | 1 | outside time/language window | limit breach |
| EC7 | exclude | 5 | full text unavailable (**soft**) | downgrade, do not drop |

**Priority and conflict handling.** Hard clauses (EC1, EC3, EC6) outrank topic
clauses. Equal-priority conflict, or a record that passes one clause and fails
another of the same rank, becomes `uncertain` and enters the human queue. The
clause set is frozen at `criteria.frozen_at`; every later change is logged in
`changes`, never applied silently.

**Two threshold passes.** Pass A (`A_strict`) requires all core terms, pass B
(`B_lenient`) requires half. Agreement and Cohen's kappa are reported; a
disagreement is queued for adjudication, never averaged away. These are two
parameterisations of one deterministic rule set — an agreement audit, not human
dual screening.

## 3. Reason codes used in `screening_log.csv`

`EC0` no title · `EC1` off-topic · `EC2` wrong population · `EC3` non-empirical ·
`EC4` no outcome data · `EC6` window/language · `EC7` full text unavailable
(soft) · `IC1` topic met · `IC3` result unclear · `FT_AVAILABLE` full text read.

## 4. Message table

<!--slr:msg
h_title|系统性文献综述报告|Systematic Literature Review Report
h_sum|摘要|Summary
h_q|研究问题与证据范围|Research question and evidence scope
h_search|检索策略|Search strategy
h_screen|纳排标准与筛选流程|Eligibility criteria and screening
h_app|质量评价|Quality appraisal
h_syn|分主题综合|Synthesis by theme
h_conf|冲突证据|Conflicting evidence
h_gap|研究空白|Research gaps
h_unc|不确定性、异常与人工待办|Uncertainty, exceptions and human queue
h_rep|复现说明|Reproducibility
t_counts|计数：语料 {a} 条，纳入 {b} 条，排除 {c} 条；论断 {d} 条（直接支撑 {e}），冲突 {f} 组，空白 {g} 项。|Counts: corpus {a}, included {b}, excluded {c}; claims {d} (directly supported {e}), conflicts {f}, gaps {g}.
t_core|核心检索词|Core concept terms
t_deriv|问题结构化方式|Question structuring method
t_exec|检索式在给定语料上命中全部检索块的记录 {n} 条（语料 {m} 条）；此处为语料内匹配，不是数据库命中数。|Query matched all blocks for {n} of {m} supplied records; this is an in-corpus match, not a database hit count.
t_dual|两遍阈值筛选一致性 {a}，Cohen's kappa {b}，分歧 {c} 条进入人工裁决。|Two threshold passes: agreement {a}, Cohen's kappa {b}, {c} disagreement(s) queued for adjudication.
t_manual|人工裁决队列|Human adjudication queue
t_ev|证据 `{r}`（质量 {g}）定位 `{loc}`|Evidence `{r}` (quality {g}) at `{loc}`
t_cond|适用条件：{a}|Conditions: {a}
t_noconf|未检出方向相反的纳入证据；这不等于证据一致，仅表示本次纳入集内无冲突。|No opposite-direction evidence was found among included studies; this is not proof of consistency, only absence of conflict in this set.
t_pend|待人工处理：{a} — {b}|Pending human action: {a} — {b}
t_err|错误：{a} — {b}|Error: {a} — {b}
t_deg|降级：{a} — {b}|Degradation: {a} — {b}
t_rep|复现：`{a}` 生成协议与记录，`{b}` 完成筛选、评价、综合与核验；共校验逐字引文 {c} 条。材料哈希见下表。|Reproduce: `{a}` builds protocol and records, `{b}` screens, appraises, synthesises and verifies; {c} verbatim quotes re-checked. Material hashes below.
t_note_example|说明：本文件的数值来自当次运行输入，不含预制答案；示例见 `references/output-schema.md`（标注为示例）。|Note: values come from this run's input, not from prepared answers; see `references/output-schema.md` for a labelled example.
q_scope|证据范围限于所给 {n} 条记录；结论不超出该语料。|Evidence is limited to the {n} supplied records; conclusions do not extend beyond them.
s_intent|检索该要素的同义词与词形变化，减少漏检|capture synonyms and word forms for this element
s_vocab|输入未提供受控词表，故不断言 MeSH/Emtree 主题词命中|no controlled vocabulary supplied, so no MeSH/Emtree assertion is made
s_db_corpus|无联网数据库：检索式在给定语料上执行，命中数按语料内匹配统计|no live database: the query runs over the supplied corpus and counts in-corpus matches
s_db_pubmed|检索式原文可直接粘贴执行；本环境未联网，未断言行数|the string is executable verbatim; not run here, so no row count is claimed
s_lim|检索式未在真实数据库运行；命中数为语料内匹配，不能等同于数据库检索结果|the query was not run on a live database; counts are in-corpus matches, not database retrieval results
c_ic1|题名/摘要须命中核心概念词≥{k}个：{t}|Title/abstract must match >= {k} core concept terms: {t}
c_ic2|须为实证研究（含样本、数据或结果），综述与社论不纳入|Empirical study with sample, data or result; reviews and editorials excluded
c_ic3|须报告与结局变量相关的结果，而非仅背景陈述|Must report a result bearing on the outcome, not background only
c_ec1|与研究生题无关：题名与摘要均无核心概念词|Off-topic: no core concept term in title or abstract
c_ec2|非目标人群或对象|Wrong population or object of study
c_ec3|非实证条目（社论、评论、勘误、书评）|Non-empirical item (editorial, commentary, erratum, book review)
c_ec4|综述类条目且无原始结局数据|Review-type item without primary outcome data
c_ec6|超出协议设定的时间窗或语言限制|Outside the protocol's time window or language limit
c_ec7|全文不可得：软排除，降级为摘要级证据，质量等级上限 low|Full text unavailable: soft exclusion, kept as abstract-level evidence, grade capped at low
c_policy|硬条款（EC1/EC3/EC6）优先于主题条款；同优先级冲突判为 uncertain 并进入人工队列；标准冻结后任何改动都记入 changes|Hard clauses (EC1/EC3/EC6) outrank topic clauses; equal-priority conflicts become uncertain and enter the human queue; after the freeze every edit is logged in changes
r_notitle|无可用题名，无法判定|no usable title, cannot decide
r_edit|非实证条目（社论/评论/勘误），按 EC3 排除|non-empirical item (editorial/comment/erratum), excluded by EC3
r_off|题名与摘要均未命中核心概念词（{t}）|no core concept term in title or abstract ({t})
r_partial|仅命中 {a}/{b} 个核心概念词，人群与结局是否相符需人工确认|only {a}/{b} core concept terms matched; population and outcome need human confirmation
r_revno|综述类条目且摘要无原始数据，无可用结局数据|review-type item without primary data in the abstract
r_nores|摘要未见结果数值或样本量，结局报告存疑|no numeric result or sample size in the abstract; outcome reporting uncertain
r_ok|命中核心概念且报告结果|core concept met and a result is reported
r_ftok|全文可读，保留|full text readable, retained
r_ftsoft|全文不可得，按软排除保留为摘要级证据，质量等级上限 low|full text unavailable: kept as abstract-level evidence under the soft exclusion, grade capped at low
r_dual|两遍为同一确定性规则的不同阈值，用于一致性审查，不等同人类双人筛选|two threshold parameterisations of one deterministic rule set, an agreement audit, not human dual screening
a_d1|问题与设计明确性|question and design clarity
a_d2|样本与数据透明度|sample and data transparency
a_d3|方法可复现性|method reproducibility
a_d4|结果报告完整性|results reporting completeness
a_d5|偏倚与局限披露|bias and limitation disclosure
a_d6|适用边界与外推|boundary and generalisation
a_note|量表只读取文本中可见的披露信号，属机器初判，需人工复核；摘要级证据的分数上限为 6|the instrument reads only visible reporting signals: a machine pre-screen that needs human review; abstract-only evidence is capped at 6
a_eff_high|可支撑直接结论|can support a direct claim
a_eff_moderate|可支撑直接结论，但须注明条件|can support a direct claim with stated conditions
a_eff_low|仅支撑推断性表述|supports inferential statements only
a_eff_very_low|不单独支撑结论|cannot support a claim on its own
y_claim|就「{th}」而言，{n} 项纳入研究提供可引证证据，报告方向为{d}。本句由证据计数生成，不含材料外数值。|On "{th}", {n} included study(ies) provide citable evidence reporting {d}. This sentence is generated from evidence counts and adds no external values.
y_pos|较高或正向|higher or positive
y_neg|较低或负向|lower or negative
y_null|无显著差异|no significant difference
y_unclear|方向不明确|direction unclear
y_cond|解释限定于所引材料的对象、时期与测量口径|interpretation is limited to the cited material's object, period and measure
y_rule|证据数 {n}，质量等级 {g}，方向类别数 {d}；达到两条及以上同向且有中高等级证据才判为直接支撑|evidence {n}, grades {g}, distinct directions {d}; only two or more same-direction items with moderate/high quality reach direct support
y_bound|不越过材料外推|no extrapolation beyond the material
y_confres|按质量等级加权后方向仍不一致：判为证据冲突，论断降为 insufficient_evidence，需原始数据或更多研究裁决|the direction contrast survives quality weighting: recorded as conflict, the claim is capped at insufficient_evidence and needs primary data or further studies
y_gap1|主题「{th}」仅由 1 项研究支撑，无法判断稳健性|theme "{th}" rests on a single study; robustness cannot be judged
y_gap2|不存在两条及以上同向且质量中上的研究，无法形成直接支撑结论|no two same-direction moderate/high-quality studies exist, so no directly supported claim is possible
y_gap3|{n} 项纳入研究的报告信息不足（方法、结果或局限披露缺失）|{n} included study(ies) under-report methods, results or limitations
y_gap4|最新证据为 {y} 年，近两年证据缺失|newest evidence is {y}; the last two years are uncovered
y_gap5|研究问题未定义对照或比较条件，比较类问题无法回答|no comparison condition is defined, so comparative questions cannot be answered
y_sum|在 {n} 条语料中纳入 {i} 条，形成 {c} 条论断（直接支撑 {d} 条）、{k} 组冲突证据与 {g} 项研究空白。结论只在所给语料范围内成立。|Of {n} supplied records, {i} were included, giving {c} claims ({d} directly supported), {k} conflict(s) and {g} gap(s). Conclusions hold only within the supplied corpus.
u_b1|纳入研究的报告质量偏低，结论稳健性受限于原文披露|low reporting quality among included studies limits robustness
u_b2|题录级判定存疑的记录尚未人工复核|records with uncertain title/abstract decisions await human review
u_b3|仅摘要级证据，未见全文，数值与条件可能缺项|abstract-only evidence: full text unseen, values and conditions may be missing
u_scope|语料 {n} 条，纳入 {i} 条，材料 {m} 个；不覆盖该领域全部文献|corpus {n}, included {i}, materials {m}; the field is not exhaustively covered
-->
