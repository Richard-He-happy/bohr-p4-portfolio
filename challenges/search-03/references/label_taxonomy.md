# 标签体系、判据与打分口径（search-screen-rank v1.0.0）

本文件是 `scripts/main.py` 的规则来源：五档标签、判定边界、打分公式、平局与冲突规则，以及可扩展的术语扩展词表。

## 1. 五档标签（tier）

| tier | relevance | 判定条件（按顺序匹配，先命中先定档） | 处置 |
|---|---|---|---|
| exclude | unrelated | 命中排除词；或年份超出检索时间窗；或得分 < 0.40 且无纳排命中 | 不进短名单，写明理由 |
| pending | undetermined | 无摘要（题录不足）；或输入标注意见互相冲突 | 升级人工，写入 `pending_human` |
| core | direct | 得分 ≥ 0.62、设计匹配 ≥ 0.45、无违规项 | 短名单前列，直接作为证据 |
| method | indirect | 得分 ≥ 0.50 且设计匹配 ≥ 0.45 | 方法学参考 |
| background | indirect | 得分 ≥ 0.40 | 背景资料 |

边界约定：
1. 缺摘要一律 `pending`，不据标题猜测设计；`evidence.locator` 记为 `title`。
2. 预印本与正式版本合并为一个候选组；组内标注冲突直接 `pending` 并写入 `conflicts`。
3. 综述不因"是综述"被排除；仅当检索范围要求原始研究时，设计不匹配通过 `design_fit` 降低得分。
4. 排除词优先于纳入词：同一词同时出现在纳排两侧时，按 `criteria_overlap` 记录并按排除处理。
5. 同分不随机：见第 4 节。

## 2. 相关性判据（逐条可复核）

- **主题覆盖 `coverage`**：检索问题词项覆盖，IDF 加权，标题 1.0 / 关键词 0.7 / 摘要 0.6 的命中折扣，按问题词项 IDF 总和归一。
- **设计匹配 `design_fit`**：从问题/范围抽取目标研究设计（系统综述、RCT、队列、病例对照、横断面、定性、体外、动物、计算/建模）。命中目标设计=1.0；检出其它设计=0.45（无设计要求时=1.0/0.6）。
- **证据强度 `evidence_strength`**：摘要长度归一（700 字符饱和），替代全文可读性。
- **元数据完备 `metadata_completeness`**：题名/摘要/作者/年份/出处/DOI 六项占比。

## 3. 打分与惩罚

```
score = 0.42*coverage + 0.22*exp + 0.18*design_fit + 0.12*evidence_strength   (截断到 0.99，保留三位)
penalty  year_out_of_range ×0.45 | exclude_term 命中 ×0.30 | 无任何 include_term 命中 ×0.78
```

- `coverage` 先按候选集内最高值做平方根归一：`min(1, (cov/max_cov)**0.5)`，避免词表长短不同导致的绝对分漂移。
- `exp` = 术语扩展命中覆盖（§7 词表，含排除词展形），独立计分，不再并入 coverage 分母。

`result.json.method.scoring` 与逐条 `coverage` / `design_fit` / `relevance_score` 一并回填，任何人可用上述公式复算。

## 4. 平局与排序

排序键严格确定：`tier 顺序 → score 降序 → 年份降序 → 归一化标题升序 → record_id 升序`。
每条候选写入 `tie_group`（与该条同分的候选数）。同分不视为错误，但必须在结果里可见。

## 5. k 值与指标

- `k` 默认 5、10，取不超过带标注记录数的最大可用值；短名单长度由 `scope.max_k` 决定。
- 指标只在存在标注（`label`/`relevance`/`grade`/`gold` 等字段）时计算：`P@k`、`nDCG@k`（增益 `2^rel-1`）。
- 基线对照：同一候选集、只用 `coverage` 排序、不做分层/去重/设计匹配；`metrics.delta` 给出逐指标差值。无标注时不输出指标，避免伪造。

## 6. 冲突与人工升级

| 冲突类型 | 识别 | 处置 |
|---|---|---|
| label_disagreement | 同组记录标注不一致 | 不取多数票，`pending` + `pending_human` |
| year_disagreement | 同组年份不一致 | 记录 `conflicts`，取出版版本年份 |
| criteria_overlap | 纳排词表重叠 | 按排除优先，写入 `uncertainty` |
| 版本重复 | DOI/归一化标题一致，或预印本 DOI 前缀 | 合并为组，`version_resolved=published_version_preferred` |

## 7. 术语扩展词表（可编辑，`main.py` 读取本区块）

格式：每行 `主词|同义词1,同义词2`，主词与同义词互为扩展，命中任一侧即扩展整组。仅在检索问题文本里出现主词或同义词时触发。

```
sglt2|empagliflozin,dapagliflozin,canagliflozin,ertugliflozin,sglt2i
glp-1|semaglutide,liraglutide,dulaglutide,exenatide,tirzepatide
statin|atorvastatin,rosuvastatin,simvastatin,pravastatin
pd-1|pembrolizumab,nivolumab,atezolizumab
hfref|heart failure,reduced ejection fraction
hfpef|heart failure,preserved ejection fraction
covid-19|sars-cov-2,covid
llm|large language model,gpt,transformer,chatgpt
crispr|cas9,genome editing
metformin|biguanide
pediatric|children,paediatric,child,adolescents
```

维护：新增领域词表只需追加行；解析失败时（文件缺失/格式不符）自动降级为"无扩展"，不影响主流程，并在 `degradations` 记录。

## 8. 适用范围与限制

- 只对**给定候选集**做筛选与排序，不连接数据库、不宣称数据库级召回（`coverage.recall_estimate` 恒为 `null`）。
- 判断依据是题录+摘要；不含全文阅读。摘要不足的候选一律 `pending`。
- 术语扩展仅覆盖第 7 节列出的词族；未覆盖领域需自行追加。
- 中文/英文均可处理（英文按词切分，CJK 按二元组切分）；混合语料不区分数值型指标口径。
