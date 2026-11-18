# 引言与相关工作写作方法手册（v1.0.0）

本手册是 `intro-related-work-writer` 的方法层：脚本给结构与证据，本文件给判断规则。写作时**先按本文件判断，再落笔**；与脚本产出冲突时，以材料原文为准。

## 1. 四段式的承接关系

```
研究背景（任务与约束 → 现有做法边界 → 具体未解问题）
        ↓ 未解问题 = 研究空白的入口
相关工作（按路线分组 → 同维度比较 → 各路线取舍）
        ↓ 各路线共同/未覆盖/冲突 → 空白
研究空白（三类来源 + 已引文献 ID → 本文如何补）
        ↓ 补法 = 贡献
本文贡献（每条贡献 ↔ 方法/图/表/实验 locator）
```

硬约束：**空白段不得出现前两段没引过的文献；贡献段不得出现方法/结果里没有的动作**。承接断点即降级为 `partial`。

## 2. 研究背景：三句法

1. **任务与约束**：这个领域要解决什么、受什么限制（数据规模、标注成本、时空分辨率、可解释性要求、实验可行性）。写约束，不写"近年来受到广泛关注"。
2. **现有做法边界**：已有路线做到哪一步、在什么条件下失效。
3. **具体未解问题**：一句话把问题收窄到一个可检验的缺口，并与本文动作对齐。

反模式：`重要 → 重要 → 我们提出`；用"随着…的发展"开头；把综述性套话放在第一句。

## 3. 相关工作：分组与比较维度

分组**不是**按时间或按作者，而是按方法路线。四条比较维度（每条路线都要给）：

| 维度 | 要写什么 | 典型失效 |
|-|-|-|
| 问题设定 | 该路线假设什么输入/输出、目标函数是什么 | 只写"研究了 X"，不写设定差异 |
| 方法机制 | 核心机制一句话（不是步骤罗列） | 逐篇摘要拼接 |
| 数据与评价 | 用什么数据、什么指标、什么划分 | 指标不可比却直接比数值 |
| 结论与局限 | 作者自陈的适用条件与失败情形 | 把作者的话改写成更强的断言 |

段落写法：一段一条路线。首句给共性与为什么成组，中段给 2–4 篇代表工作的差异，末句给该路线的取舍与代价。

### 3.1 路线词表（与 `scripts/verify.py::ROUTES` 保持一致）

| 路线 | 触发关键词（标题权重 3、摘要权重 1） |
|-|-|
| transformer/LLM | transformer, attention, large language model, llm, pretrain, foundation model |
| deep learning | neural network, deep learning, convolutional, cnn, lstm, recurrent |
| graph-based | graph neural, gnn, message passing, knowledge graph, molecular graph |
| generative | diffusion, generative adversarial, gan, variational autoencoder |
| reinforcement learning | reinforcement learning, policy gradient, reward |
| classical ML | support vector, svm, random forest, gradient boosting, feature engineering |
| statistical modelling | bayesian, regression, likelihood, statistical model |
| mechanistic/experimental | mechanism, kinetic, in vitro, in vivo, assay, spectroscop |
| simulation/numerical | simulation, density functional, dft, finite element, molecular dynamics |
| benchmark/dataset | benchmark, dataset, corpus, evaluation protocol, annotation |
| multimodal | multimodal, cross-modal, image-text, vision-language |
| review/survey | survey, systematic review, meta-analysis, tutorial |

未命中任何路线 → `unclassified`，必须人工归组或补关键词，不得硬塞进最近的一组。

## 4. 研究空白：只从已引文献推

三类可接受来源，每类都要能指到具体文献 ID 与逐字依据：

1. **共同限制**：多篇工作在限制句（however/limited/cannot/仅/难以…）上重复同一约束。
2. **未覆盖场景**：作者自陈适用范围（only / limited to / in the setting of），本文场景落在此范围外。
3. **结论冲突**：两篇工作在同一设定下给出相反结论，且差异无法由数据或指标解释。

不可接受：无文献支撑的"据我们所知尚无研究"；把"我们没检索到"写成"领域空白"；把未来工作写成空白。

推导模板（中文）：
> 在 {路线} 路线上，{逐字局限句}（[k]）。这一限制在 {另一路线} 中同样存在（[m]），说明 {空白} 不是单一路线的实现问题。本文通过 {方法动作} 覆盖 {未覆盖场景}，对应第 {n} 节与 {表/图} 。

## 5. 贡献：可对账条目

每条贡献必须满足三条：**有动作**（提出/构建/证明/给出协议）、**有证据位置**（图号、表号、指标、定理编号）、**有边界**（在什么设定下成立）。

写法：`动词 + 对象 + 与已有工作的差别 + 证据位置`。禁止"显著优于现有方法"而无比较设定；禁止"首次"除非材料明写。

对齐检查（脚本自动产出 `contribution_alignment`）：贡献条目文本是否能在材料中找到逐字来源；找不到 → `aligned=false` → 进 `pending_human`，不得保留无依据条目。

## 6. 引用覆盖与元数据

- 三条覆盖线：**关键工作**（被后续工作反复当作基线）、**代表工作**（每条路线 ≥2 篇）、**近期进展**（近 3 年，脚本给 `coverage.recent_3y`）。
- 每条引用要能回答：作者、年份、来源；缺任一项 → `metadata_status=partial` 并进 `pending_human`。
- 引用格式：默认 author-year 编号（`[k]` + References 列表）。目标期刊格式未给定即在 `uncertainty` 说明，不擅自套用特定期刊模板。

## 7. 语言与语体

- 语言跟随 `task_instruction`；未指定按材料 CJK 占比判定（≥12% 视为中文）。
- 中文稿禁用"综上所述""具有重要意义"作为段首；英文稿禁用 "In recent years, ... has attracted increasing attention"。
- 时态：他人工作用现在完成/一般现在；本文工作用一般现在；实验结果用过去时（英文）。

## 8. 写作与核对分离（本 Skill 的核心方法）

1. 脚本产出**证据绑定骨架**：每句带 `[source_id#locator]`，句句可在 `sources_index.json` 逐字命中。
2. 作者/Agent 只做**表达层改写**：合并短句、补连接词、调整语序；不改数字、术语、引用编号、结论强度。
3. `python3 -B scripts/verify.py --result result.json --sources sources_index.json` 给出 `quote_verified_rate`；<0.8 不得 `status=ok`。
4. 改写稿交给 `main.py --manuscript <稿>` 复跑：原摘要句不再逐字出现即提示"需确认转述一致"，避免把原文结论改写走样。

## 9. 反模式清单

| 反模式 | 后果 | 替代做法 |
|-|-|-|
| 逐篇摘要拼接 | 分组维度缺失 | 一段一路线，先共性后差异 |
| 引用挂在段落末尾一串 | 论断与引用脱钩 | 每句一个引用，落在具体断言后 |
| 空白无引文支撑 | 正确性扣分 | 三类来源 + `supports` 列表 |
| 贡献夸大适用范围 | 与实际结果不符 | 写边界条件 |
| 补全缺失的作者/年份 | 元数据造假 | 标 `[待补]` 并入 `pending_human` |
| 把 PDF 乱码文本当原文引用 | quote 校验失败 | 降级到标题层面 + `pdf_text_heuristic` |
