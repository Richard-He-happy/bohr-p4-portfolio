# lexicon.md — editable term lists used by scripts/lens.py
# Format: sections in [brackets]; one entry per line; fields separated by "|".
#   [topics]  topic_id | alias;alias;alias | parent_topic_id
#   [gap]     gap_type | cue;cue;cue        (sentence-level cue phrases)
#   [method]  cue;cue;cue                   (method-first wording, one flat list)
#   [exclude] term;term                     (title-level exclusion keywords)
# Matching: ASCII terms match on word boundaries, CJK terms match as substrings,
# case-insensitive, on title + abstract + first 1500 chars of body text.
# Rules: (1) a record may carry several topics; (2) ids are lowercase and stable —
# renaming an id breaks comparability with earlier runs; (3) extend, do not delete,
# when the corpus vocabulary changes; (4) an unmatched record is counted in
# topic_evolution.unmapped_count instead of being forced into a topic.

[topics]
data-scarcity | data scarcity;limited data;small sample;scarce label;数据不足;数据稀缺;样本有限 | data
generalization | generaliz;transferab;robustness;distribution shift;泛化;鲁棒性;迁移能力 | method
interpretability | interpretab;explainab;black box;可解释;黑箱 | method
efficiency | efficien;computational cost;latency;throughput;效率;算力开销;时延 | method
scalability | scalab;large-scale;scale-up;扩展性;规模化 | method
reproducibility | reproducib;replicab;open data;open code;可复现;可重复 | method
benchmark | benchmark;dataset;evaluation protocol;基准;数据集;评测协议 | evaluation
multimodal | multimodal;multi-source;multi-modal;多模态;多源 | data
deployment | deployment;real-world;clinical use;field study;pilot;落地;真实场景;临床应用 | application
uncertainty | uncertainty quantif;error bar;confidence interval;不确定度;误差范围 | method
materials-energy | battery;catalys;perovskite;alloy;electrode;材料;电池;催化;钙钛矿;合金 | application
life-medicine | cancer;gene;protein;patient;trial;biomarker;基因;蛋白;临床;生物标志物 | application
ai-ml | neural;deep learning;transformer;large language model;模型;神经网络;大语言模型 | application
climate-policy | climate;emission;carbon;policy;governance;气候;排放;碳;政策;治理 | application
robotics-control | robot;manipulation;control law;autonomous;机器人;操作;控制;自主 | application

[gap]
unresolved | remains unclear;remains unknown;has not been;have not been;open question;future work;future research;not yet resolved;尚无定论;仍不清楚;有待;亟需;进一步研究;尚未解决
scope_limit | only tested;only evaluated;limited to;small sample;single-centre;single-center;in vitro only;狭窄;仅限于;样本量;局限于;仅适用
conflict | contradic;contradictory;discrepan;inconsistent;in contrast to;矛盾;相互矛盾;不一致;存在分歧;结论相反
data_limit | lack of data;no benchmark;no standard;not available;缺乏数据;尚无标准;缺少公开
cost_limit | expensive;costly;time-consuming;成本高;代价高;耗时

[method]
first;for the first time;novel;we propose;we introduce;propose a;introduce a;new framework;first demonstration;首次;率先;提出一种;首次提出

[exclude]
erratum;corrigendum;retraction;editorial;comment on;勘误;撤稿;更正;编者按;征稿
