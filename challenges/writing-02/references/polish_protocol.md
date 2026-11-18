# 润色作业规程（polish_protocol）

本文件是 `SKILL.md` 第 7–9 节的展开版：拿一段稿子时按这里的顺序判断，不要凭感觉整段重写。

## 0. 一条铁律

**改的是表达，不是主张。** 任何会改变「作者断言了什么、断言得多强、依据哪个数字」的改动都不属于润色，属于内容修改，必须停下来写 `pending_human`。

## 1. 单段编辑流程（7 步）

1. **读锁**：从 `workpack.json` 取该段 `locks`：`numbers`、`citations`、`xrefs`、`hedges`、`boosters`、`abbreviations`。这是交付前的核对清单。
2. **定位硬错**：逐句找语法/句法/标点错误（见 §2 分类）。硬错优先，风格其次。
3. **判断改动粒度**：默认在**短语级**落刀。只有出现悬垂修饰、逻辑断裂、超长并列时才重排句子，且重排后逐项核对信息是否齐全。
4. **管制强度**：对照 §3 的强度阶梯；删一个 hedge 或加一个 booster，等同于改结论。
5. **锁事实**：数字、单位、样本量、p 值、浓度、时间点、引用编号、图表编号原样搬运；单位空格与拼写统一属于排版，不算改事实，但要全文一致。
6. **落地术语**：使用术语表 `target` 写法；无术语表时以首次出现写法为准并全篇回扫（见 §4）。
7. **写说明并回读**：每条改动写 `type / original_quote / revised_quote / reason / locator`；回读核对「意思不变、锁齐全、像同行写的、无新增信息」。

## 2. 错误分类与判定标准（`type` 受控词表）

| type | 判定标准（可举例） | 反例（不要这样标） |
|---|---|---|
| `grammar` | 主谓不一致、时态错、缺谓语、比较级错误 | 把可接受的语序变化标成 grammar |
| `agreement` | 单复数、代词指代不一致 | 与量词搭配有关时用 `collocation` |
| `tense` | 方法与结果时态混乱（方法过去时、结论现在时） | 因改写而顺带变时态 |
| `voice` | 不必要的被动、主语缺失（"It was found that…" 连用） | 方法段合理的被动 |
| `article` | a/an/the 缺失或误用（可数与不可数） | 专有名词前冠词属期刊风格 |
| `preposition` | measured **by/with**、consistent **with**、increase **in** | 搭配问题归 `collocation` |
| `punctuation` | 逗号粘连、冒号误用、破折号、连字符/短横 | 单位间距归 `unit_format` |
| `sentence_split` | 一句三行且含 3 个以上从句 | 只删一个逗号 |
| `word_order` | 修饰语位置导致歧义（"only treated 3 mice"） | 无歧义的语序偏好 |
| `collocation` | 动名/形名搭配不地道（perform an experiment ✓ / do an experiment ✗ 学术语境） | 拼写变体归 `terminology` |
| `redundancy` | "completely eliminate"、"results showed that the results…"、名词化堆叠 | 必要的限定重复 |
| `nominalization` | "the implementation of the analysis of…" → "we analysed…" | 术语本身是名词 |
| `chinglish` | 中译英直译腔：主题句堆叠、无主语句、逻辑连接词滥用（"and also moreover"） | 合规的中式术语译名 |
| `terminology` | 同一概念多种写法/译法、拼写体系混用（-ize/-ise、tumor/tumour） | 有意的近义区分 |
| `abbreviation` | 缩写未在首次出现处定义、定义重复、全大写与小写混用 | 通用缩写（DNA、SD）无需定义 |
| `register` | 口语化、宣传化、绝对化、第一人称误用（按体裁判断） | 学位论文允许的 "we" |
| `hedging` | 为顺畅而删/加 may、suggest、could、possibly | 只改 hedge 的位置不改强度 → `word_order` |
| `citation_format` | 引用标记位置（句末标点前/后）、编号样式、上标 | 引用内容本身 |
| `unit_format` | 数字与单位间距、单位大小写、± SD 写法、百分号 | 单位换算（属于改事实） |
| `typography` | 连字符 vs 短横（en dash）、引号、全半角、多余空格 | 用词错误 |
| `structure` | 段落切分、句序调整、主题句前移 | 只换连接词 |
| `translation` | 中英转换中的信息重心、主语选择、被动化 | 语法错误（另标 `grammar`） |
| `no_change` | 通读后确实无需改动（配 `unchanged_reason`） | 为凑数而改 |

一条改动只归一类；跨类时按「最需要评审判断的那一类」登记，并在 `reason` 里说明其余方面。

## 3. 强度阶梯（hedge / booster）

| 级 | hedge 表达 | booster 表达 | 允许的移动 |
|---|---|---|---|
| 5 断言 | — | demonstrate / prove / establish / 证明 / 证实 | 只能原样保留 |
| 4 强倾向 | clearly / consistently shows | significantly / markedly / 显著 / 大幅 | 保留；若原句只是趋势，禁止上升 |
| 3 倾向 | suggest / indicate / likely / 提示 / 表明（弱） | strongly support | 保留 |
| 2 可能 | may / might / could / 可能 / 或许 | — | 保留；可改位置不改强度 |
| 1 未知 | remains unclear / cannot exclude / 尚不清楚 / 有待 | — | 保留；不得删去 |

规则：
- 计数守恒：段落内 hedge 数不得减少、booster 数不得增加（`verify.py` 会逐段比对，`fail` 会阻断 `ok`）。
- 因果 vs 相关：`associated with`、`correlates with` 不得升级为 `causes`、`leads to`、`results in`；反向亦然。
- 否定范围：`did not significantly reduce` ≠ `did not reduce`；`no evidence of X` ≠ `evidence of no X`。
- 条件与量词：`in vitro`、`in this cohort`、`at 24 h`、`some/most/all` 原样保留。
- 统计措辞：`p = 0.003`、`95% CI`、`n = 48` 原样；不得把 `p = 0.003` 写成 `p < 0.01`。

## 4. 术语治理（术语表驱动）

1. **建表**：`workpack.json` 的 `glossary` 含案例给定条目 + 自动候选（首字母大写多词短语）。给定条目优先，候选仅提示。
2. **一次性决策**：同一源术语只允许一个 `target`。发现两个写法时不要自选，记 `pending_human`（`glossary_conflict`）。
3. **全篇回扫**：定稿前用 `target` 与常见变体（美/英拼写、单复数、连字符有无、缩写大小写）回扫全文，统一为 `target`。
4. **缩写三件事**：首次出现给全称＋括号缩写；之后一律用缩写；全篇同一缩写不重复定义。原文已有定义时沿用原文位置，不强行前移。
5. **符号与单位**：`µ` vs `μ`、`°C` 前空格、`%` 前空格、`×g`、`kDa` 大小写按原文统一，不混用。
6. **译名惯例**：学科内既有译法优先（基因/蛋白斜体与大小写、化合物命名、统计量符号）。不确定的译法保留原文并进 `pending_human`。

## 5. 语域基线（按 genre）

| 体裁 | 时态 | 人称 | 长度与结构 | 禁忌 |
|---|---|---|---|---|
| 期刊摘要 | 方法过去时、结论现在时 | 少用 we，可用被动 | 单段、无小标题、通常无引用 | 新数据、未定义缩写、宣传词 |
| 论文正文 | 方法过去时、结果过去时、推论现在时 | we 可用 | 主题句前置、一段一意 | 口语化、绝对化 |
| 学位论文 | 同上，可更铺陈 | 可用「本文/we」 | 允许回顾与铺垫 | 与期刊稿混用缩写体系 |
| 基金申请 | 现状现在时、计划将来时 | we | 问题—缺口—方案—预期影响 | 空泛承诺、无据的「首次」 |
| 审稿回复 | 回应过去/现在时 | we | 逐条编号对应、先结论后解释 | 争辩式语气、回避未做项 |
| 中英双语摘要 | 中文摘要与英文摘要信息一一对应 | — | 术语逐条对齐 | 英文摘要增删信息 |

## 6. 中译英与英文改写

- 先定**信息重心**：中文「通过…发现…」的结论重心在末句，英文应把结论前置为主句。
- 拆长定语：中文多重定语后置为从句或介词短语，不硬套 "which … which …"。
- 去冗余名词化：`对…进行分析` → `analyse`；`起到了…的作用` → 直接动词。
- 连接词节制：`and also moreover furthermore` 只留一个；逻辑关系用动词与句序表达。
- 主语补齐：无主语句补 `we / this study / the data`，但不得引入原文没有的施动者角色（如把「实验表明」写成「我们证明」会升级强度）。
- 术语对齐：中文术语 → 英文术语必须与 `glossary` 一致；同一中文词不得两种译法。
- 双语交付：`bilingual` 列表按段落给出 `{source, target}`，逐条对齐，不合并、不省略。

## 7. 工单执行（organizer_workorder / organizer_edit_workorder）

1. 逐项读，拆成可执行动作（如「统一缩写」→ 扫全部缩写 → 定首次定义 → 回扫）。
2. 每项在 `workorder_receipts` 写 `{id, status: done|not_applicable, evidence, locator}`；`evidence` 写具体做了什么、落在哪段。
3. 无法完成的项写 `pending_human` 并说明缺什么材料；不要用「已尽力」代替回执。

## 8. 红线（出现即停手并记录）

- 需要改数字、单位、样本量、p 值才能「通顺」。
- 需要新增引用、文献、基因名、化合物、统计量。
- 原文两处数值冲突且无法判断哪个正确。
- 要求把相关说成因果、把趋势说成结论、把 preliminary 说成 established。
- 引用编号在正文存在但材料中无对应文献表——只保留编号，不猜文献，进 `pending_human`。

## 9. 质量自评（写完一段就问）

1. 一个不了解该研究的同行，读完改文是否得到与原文**相同**的结论与相同的确定性？
2. 删掉我所有改动，读者会不会误解？若不会，这个改动是否必要？
3. 每处改动能否用一句话解释「为什么这样更好」？说不出来就回退。
4. 改后文本是否仍是该体裁该学科的正常写法（不是翻译腔、不是营销文案）？
