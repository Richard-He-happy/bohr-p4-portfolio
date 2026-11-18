# Lexicon for research-question-retrieval (machine-read by scripts/main.py)

Format rules (UTF-8, plain text):

- `## facet: <name>` then ONE line of cue phrases separated by `|` (lowercase; matched as
  substrings of the research question).
- `## syn` then one line per entry: `term => synonym|synonym|…` (both directions are used).
- `## polarity: pos` / `## polarity: neg` then one line of phrases each, used only by the
  heuristic conflict detector.
- Edit freely; keep the section headers. If this file is missing the script falls back to a
  minimal built-in table and records a degradation.

## facet: method
randomized|randomised|controlled trial|cohort|case-control|meta-analysis|systematic review|simulation|molecular dynamics|density functional|machine learning|deep learning|neural network|crispr|sequencing|rna-seq|scrna-seq|pcr|immunohistochemistry|western blot|mri|eeg|fmri|imaging|spectroscopy|xrd|nmr|chromatography|mass spectrometry|assay|knockout|knockdown|transgenic|in vivo|in vitro|benchmark|transcriptom|proteom|genome-wide|gwas|single-cell|方法|队列|随机对照|系统综述|荟萃分析|深度学习|机器学习|测序

## facet: mechanism
mechanism|pathway|signaling|signalling|regulation|regulatory|expression|mutation|inhibition|inhibitor|agonist|antagonist|binding|interaction|cascade|transcription|epigenetic|metabolic|immune|inflammation|apoptosis|autophagy|oxidative stress|机制|通路|调控|表达|突变|抑制|靶点

## facet: outcome
efficacy|accuracy|sensitivity|specificity|survival|mortality|prognosis|performance|yield|efficiency|risk|association|correlation|safety|toxicity|cost|outcome|response rate|疗效|预后|准确|敏感性|特异性|生存|风险|安全性

## facet: comparison
versus|vs|compared with|comparison|better than|superior|inferior|non-inferior|alternative to|instead of|相比|对比|优于

## facet: gap
limitation|limitations|challenge|failure|conflicting|controversial|controversy|unclear|unknown|lacking|barrier|drawback|insufficient|bias|局限|争议|不足|挑战|偏倚

## syn
scrna-seq => single-cell rna sequencing|single cell|single-cell
rna-seq => transcriptome sequencing|transcriptomic
gwas => genome-wide association
rct => randomized controlled trial|randomised controlled trial
ml => machine learning
dl => deep learning
ihc => immunohistochemistry
auc => area under the curve
tumor => tumour|cancer|neoplasm
cancer => tumour|tumor|malignancy
mechanism => mechanistic
efficacy => effectiveness
prognosis => prognostic|outcome
therapy => treatment|intervention
biomarker => marker
crispr => cas9
inflammation => inflammatory
mouse => mice|murine
patient => patients|cohort
meta-analysis => systematic review|pooled analysis
机制 => mechanism|pathway
疗效 => efficacy
预后 => prognosis
队列 => cohort
单细胞 => single-cell
肿瘤 => tumor|cancer
小鼠 => mouse|mice
免疫 => immune
炎症 => inflammation
耐药 => resistance
靶点 => target
深度学习 => deep learning
机器学习 => machine learning
随机对照 => randomized controlled trial

## polarity: pos
increase|improve|effective|superior|outperform|benefit|support|confirm|reduce|promising|higher|enhance

## polarity: neg
no significant|not significant|no difference|ineffective|no effect|inferior|failed|failure|contradict|challenge|no association|does not|did not|unclear|limited evidence|not improve|lower|worse
