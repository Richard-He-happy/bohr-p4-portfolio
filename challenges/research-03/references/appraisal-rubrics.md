# SLR-6D appraisal instrument and detection markers

Read at runtime by `scripts/verify.py`. The `<!--slr:markers ... -->` block holds
regular expressions (`key=pattern`) that define what counts as *visible evidence*
for each judgement; edit them to retune sensitivity. A missing or invalid pattern
makes that dimension score `unclear` (never an exception).

## 1. Instrument `SLR-6D` v1.0

Six dimensions, scored from what the record's own text discloses. Each dimension
is judged `yes` (2 points) or `unclear` (0 points) by locating a sentence that
satisfies the dimension's pattern; the matched sentence is stored verbatim as the
judgement's evidence. Score 0–12. Grades: `>=10 high`, `7–9 moderate`,
`4–6 low`, `<4 very_low`. Abstract-level records are capped at score 6 and grade
`low`, and the cap is written into the item, not into the text.

| id | dimension | what counts as present | typical marker |
|---|---|---|---|
| D1 | question and design clarity | an explicit objective or design statement | "aim", "objective", "本研究" |
| D2 | sample and data transparency | sample size, participants, corpus or dataset named | "n = 120", "participants", "样本" |
| D3 | method reproducibility | procedure, instrument, model or protocol described | "method", "model", "量表" |
| D4 | results reporting completeness | a quantity, dispersion, test statistic or p-value | "12.4%", "p < 0.05", "CI" |
| D5 | bias and limitation disclosure | limitations, bias or caution discussed | "limitation", "bias", "局限" |
| D6 | boundary and generalisation | conditions of applicability or future work | "generaliz", "limited to", "外推" |

**Why this scale.** It is a reporting-completeness screen suited to heterogeneous
supplied corpora (no design-specific risk-of-bias tool can be applied uniformly to
mixed study types), it is fully rule-based and reproducible, and every judgement
carries a verbatim quote so a reader can overrule it. It does **not** estimate
risk of bias for a specific design; that requires the design-specific tool named in
the protocol and is listed in `pending_human` when the corpus is mixed.

**How the grade constrains the synthesis.** A claim needs at least two
same-direction evidence items, one of them `high` or `moderate`, to be labelled
`directly_supported`. A single `high`/`moderate` item gives `inferred`. Anything
else, and every direction contrast, gives `insufficient_evidence`. `low` and
`very_low` items never carry a direct claim alone.

## 2. Direction and item-type markers

`POS`/`NEG`/`NUL` decide the reported direction of a sentence (checked in that
order: a null finding wins over a directional verb). `EDIT` flags editorials,
commentaries, errata and book reviews so they can be excluded as non-empirical;
`REVW` flags review-type items, which are only excluded when the abstract shows no
primary data. Direction is the *reported* direction relative to the named outcome,
not a valence judgement.

## 3. Markers

<!--slr:markers
D1=objective|aim|we (?:investigate|examine|assess|test|evaluate)|the purpose of this|本研究|目的|旨在|考察|探讨
D2=\bn\s*=\s*\d+|sample size|participants|respondents|cohort|dataset|corpus|样本|被试|受试|例
D3=method|procedure|protocol|instrument|regression|model|assay|survey|questionnaire|trial design|方法|模型|量表|实验设计|流程
D4=\d+(?:\.\d+)?\s*%|p\s*[<>=]\s*0?\.\d+|confidence interval|\bCI\b|\bOR\s*=|\bHR\s*=|\bRR\s*=|β\s*=|显著
D5=limitation|bias|confound|caution|weakness|局限|偏倚|不足
D6=generaliz|external validity|further (?:research|study)|future work|limited to|推广|外推|适用
POS=improv|increas|higher|enhanc|positive(?:ly)? associat|effective|benefit|提升|提高|改善|增强|有效|正相关|升高
NEG=decreas|lower|worse|adverse|negative(?:ly)? associat|harm|reduce[sd]?\b|reduction|下降|降低|恶化|不利|负相关|减少
NUL=no (?:significant|evidence of)|not significant|non-?significant|no (?:difference|association|effect)|无显著|无差异|不相关|未见
EDIT=editorial|commentary|letter to the editor|erratum|corrigendum|book review|社论|评论|勘误|征稿|编者按
REVW=systematic review|meta-?analysis|scoping review|narrative review|系统评价|系统综述|荟萃分析
-->
