# 中英检索词表（glossary）

脚本 `core.load_gloss()` 逐行解析本文件的 `中文|英文1, 英文2` 结构（`#` 开头为注释）。
用途：把中文问题里的实体词映射成论文正文中的英文词形，供段落打分使用。
词表只影响「找哪几段」，不产生事实；找不到证据时按未报告处理，不补外部知识。

## 通用问句词
数值|value, amount, magnitude
条件|condition, under, at
方法|method, approach, procedure, protocol
结果|result, finding, observation
结论|conclusion, summary
优势|advantage, benefit
局限|limitation, drawback, shortcoming
误差|error, deviation, uncertainty
范围|range, window
比例|ratio, fraction, percentage
提升|improve, increase, enhance, gain
降低|decrease, reduce
相比|compared with, relative to, versus
基线|baseline, reference
最优|best, optimal, highest, maximum
平均|average, mean
单位|unit
实验|experiment, test, measurement
样品|sample, specimen
表征|characterization, characterization technique
参数|parameter
稳定性|stability, durability, robust

## 材料与机械制造
合成|synthesis, synthesize, synthesized
制备|preparation, prepared, fabricate
步骤|step, procedure, route, protocol
原料|precursor, reagent, raw material, starting material
前驱体|precursor
用量|dosage, loading, amount, quantity
配比|ratio, molar ratio
掺杂|doping, doped
负载|loading, supported
煅烧|calcination, calcined
干燥|drying, dried
形貌|morphology, shape
粒径|particle size, diameter
比表面积|surface area, BET
强度|strength
抗拉强度|tensile strength, UTS
屈服强度|yield strength
硬度|hardness, HV
塑性|ductility, elongation
韧性|toughness
延伸率|elongation, ductility
热处理|heat treatment, annealing, quenching, tempering
退火|annealing, annealed
淬火|quenching, quenched
回火|tempering, tempered
时效|aging, aged
合金|alloy, steel, aluminium, aluminum, titanium
晶粒|grain, grain size
晶界|grain boundary
细化|refinement, refine
再结晶|recrystallization
相|phase, precipitate, precipitation
显微组织|microstructure
位错|dislocation
缺陷|defect, porosity, void
夹杂|inclusion
偏析|segregation
应变|strain
应力|stress
应变速率|strain rate
变形|deformation, rolling, forging, extrusion
轧制|rolling, rolled
烧结|sintering, sintered
涂层|coating, coated
疲劳|fatigue
蠕变|creep
磨损|wear, friction
腐蚀|corrosion
断裂|fracture
孔隙|porosity, pore
密度|density
温度|temperature
加热|heating, heated
冷却|cooling, cooled
保温|holding, dwell
压力|pressure
载荷|load, loading
转速|speed, rpm
加工|machining, processing
表面粗糙度|surface roughness, Ra
尺寸精度|dimensional accuracy, tolerance
焊接|welding, weld
残余应力|residual stress
裂纹|crack, cracking
冲击|impact, Charpy

## 计算机与机器学习
模型|model, network, architecture
数据集|dataset, benchmark, corpus
训练|training, train
推理|inference, test time
准确率|accuracy
精确率|precision
召回率|recall
F1|F1, f1-score
误差|error, MAE, RMSE
损失|loss
基线|baseline
消融|ablation
超参数|hyperparameter
学习率|learning rate
批大小|batch size
轮次|epoch
参数量|parameters, FLOPs
预训练|pre-training, pretrained
微调|fine-tuning, fine-tune
注意力|attention
卷积|convolution, CNN
Transformer|Transformer
图神经网络|graph neural network, GNN
泛化|generalization
过拟合|overfitting
正则|regularization, dropout
鲁棒性|robustness, adversarial
标注|annotation, label
划分|split, train/validation/test
评估指标|metric, evaluation
显著性|significance, p-value
置信区间|confidence interval
推理时延|latency, throughput
显存|memory, GPU
提升幅度|improvement, gain

## 环境工程与光催化
光催化|photocatalysis, photocatalytic
催化剂|catalyst, photocatalyst
降解|degradation, degrade
去除率|removal efficiency, removal rate
矿化|mineralization
染料|dye, methylene blue, rhodamine
污染物|pollutant, contaminant
抗生素|antibiotic, tetracycline
光源|light source, lamp
氙灯|xenon lamp
汞灯|mercury lamp
可见光|visible light
紫外|UV, ultraviolet
波长|wavelength, nm
光强|light intensity, irradiance
带隙|band gap, Eg
导带|conduction band
价带|valence band
自由基|radical
羟基自由基|hydroxyl radical, ·OH
超氧|superoxide
空穴|hole
电子|electron
复合|recombination
比表面积|surface area, BET
孔容|pore volume
投加量|dosage, loading
浓度|concentration
初始浓度|initial concentration
pH|pH
温度|temperature
时间|time, irradiation time
循环|cycle, cycling
重复使用|reusability, reuse
稳定性|stability, leaching
速率常数|rate constant, k
动力学|kinetics, pseudo-first-order
吸附|adsorption
活性|activity
选择性|selectivity
副产物|by-product, intermediate
毒性|toxicity
总有机碳|TOC
化学需氧量|COD

## 章节名（用于章节加权）
摘要|abstract
引言|introduction
方法|methods, experimental, materials and methods
结果|results
讨论|discussion
结论|conclusion, conclusions
参考文献|references, bibliography
图注|figure caption, Fig.
表格|table
