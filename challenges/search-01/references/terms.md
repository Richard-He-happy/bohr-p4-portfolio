# Lexicon for query expansion (consumed by scripts/engine.py::load_lexicon)
#
# Format:  label | term ; term ; term
#   - `label` becomes a facet name in result.json (coverage.facet_coverage).
#   - terms are matched case-insensitively, order-insensitive on content tokens.
#   - a group is only used when one of its terms occurs in the case topic, task text
#     or the keywords block, so unrelated groups stay silent.
#   - add domain vocabulary here; no code change is required.
#
# Format:  cn2en | 中文=english
#   - when a Chinese term occurs in the topic, the English variant is added to the
#     research_problem facet. Best-effort only: this is a bundled miniature glossary,
#     not a translation service.

single_cell | single-cell ; single cell ; scRNA-seq ; scRNA ; single-nucleus ; snRNA-seq
sequencing | RNA sequencing ; RNA-seq ; transcriptome ; transcriptomics ; sequencing
spatial | spatial transcriptomics ; spatial omics ; imaging-based spatial ; Visium ; MERFISH
crispr | CRISPR ; CRISPR-Cas9 ; gene editing ; base editing ; prime editing
perturbation | perturbation screen ; Perturb-seq ; pooled screen ; knockout screen
cell_type | cell type ; cell atlas ; lineage ; progenitor ; stem cell ; differentiation
neuro | neuron ; cortical ; cortex ; brain ; neural ; interneuron ; astrocyte ; microglia
dev_bio | development ; developmental ; embryonic ; postnatal ; organogenesis ; fate specification
disease_model | disease model ; knockout mouse ; transgenic ; knock-in ; patient-derived
machine_learning | machine learning ; deep learning ; neural network ; foundation model ; representation learning
statistics | regression ; Bayesian ; mixed model ; survival analysis ; causal inference ; propensity score
clinical_trial | randomized controlled trial ; RCT ; clinical trial ; phase II ; phase III ; cohort
evidence_synthesis | systematic review ; meta-analysis ; umbrella review ; scoping review ; PRISMA
genomics | genome-wide association ; GWAS ; whole-genome ; exome ; variant calling ; polygenic
proteomics | proteomics ; mass spectrometry ; protein interaction ; phosphoproteomics
imaging | MRI ; microscopy ; cryo-EM ; histology ; calcium imaging ; two-photon
microbiome | microbiome ; metagenomics ; 16S ; gut microbiota
immunology | immunotherapy ; CAR-T ; T cell ; antibody ; cytokine ; inflammation
drug | drug discovery ; small molecule ; inhibitor ; target validation ; pharmacokinetics
materials | materials ; nanoparticle ; catalyst ; polymer ; alloy ; thin film
energy | battery ; photovoltaic ; electrocatalyst ; energy storage ; fuel cell
climate | climate model ; carbon ; emissions ; remote sensing ; land use
plant | Arabidopsis ; rice ; crop ; plant ; root ; leaf
methods | protocol ; benchmark ; dataset ; pipeline ; workflow ; software ; toolbox

cn2en | 单细胞=single-cell ; 测序=sequencing ; 转录组=transcriptomics ; 皮层=cortex ; 发育=development ; 小鼠=mouse ; 脑=brain ; 神经元=neuron ; 图谱=atlas ; 基因编辑=gene editing ; 机器学习=machine learning ; 深度学习=deep learning ; 系统综述=systematic review ; 荟萃分析=meta-analysis ; 队列=cohort ; 随机对照试验=randomized controlled trial ; 生物标志物=biomarker ; 蛋白质组=proteomics ; 代谢组=metabolomics ; 微生物组=microbiome ; 免疫治疗=immunotherapy ; 药物发现=drug discovery ; 催化剂=catalyst ; 电池=battery ; 气候变化=climate change ; 水稻=rice ; 拟南芥=Arabidopsis ; 空间转录组=spatial transcriptomics ; 类器官=organoid ; 专利=patent
