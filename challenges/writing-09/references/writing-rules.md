# 写作规则速查（v3）

`check` 判据与本文一致；改词表时同步 `scripts/main.py` 的 `BAN / OVER / BOUND / LAYERS`。

## 1 Results 句式（只写观察）

四件套：**值 + 单位 + 条件 + 离散度/统计量 + 图/表号**。

| 场景 | 可写 | 不要写 |
|---|---|---|
| 端点比较 | "Viability was 94.2% (SD 4.1, n = 3) at 0.5 µM and 38.9% (SD 6.0, n = 3) at 10 µM (Fig. 1A; Table 1)." | "Compound X inhibited growth by 55.3% because of…" |
| 剂量梯度 | "Readouts decreased monotonically across the four dose levels." | "Readouts decreased sharply, indicating toxicity." |
| 统计 | "one-way ANOVA gave p = 0.003; 10 µM differed from vehicle (p < 0.001)." | "差异非常显著"（无检验） |
| 阴性 | "p = 0.41；未与溶剂对照分离。" | "有下降趋势"（把不显著写成趋势） |
| 目视 | "约 62%（approx., 目视读图）" | "62.0%"（假精度） |

组织方式：一段一个发现，按图序或按问题排序，不写流水账。

## 2 Discussion 三拍

1. **数据支持什么**：回指 Results 的具体读数，强度只到数据允许处。
2. **与已有证据的关系**：一致 / 不一致 / 部分一致 + 可能原因（体系、剂量、时程、检测方法）。材料无文献时写"材料未提供可对照文献"，不堆引用。
3. **边界与替代解释**：相关≠因果；机制推测标为推测；给出可证伪该解释的实验。

`BOUND` 词（至少要出现一个，否则 `discussion_no_boundary`）：
局限 / 不能排除 / 相关不等于因果 / 不能证明 / 不推断因果 / limitation / association。

## 3 因果梯度

| 级 | 证据 | 允许表述 |
|---|---|---|
| 相关 | 观察性共变 | 与……相关 / associated with |
| 提示 | 剂量依赖、时序、方向一致 | 提示 / 与……一致 / suggests / consistent with |
| 因果 | 干预、敲除、救援 + 对照 | 导致 / causes / leads to |

观察数据最高到第二级。

- `BAN`（Results 禁用，命中即 `results_causal` error）：导致 造成 因为 由于 机制 证明 证实 调控 cause because mechanism prove demonstrat
- `OVER`（Discussion 过度断言，`overclaim` error）：证明 证实 确证 首次 prove proven confirm definitiv establish
- 否定/让步语境（"不能证明""cannot confirm"）不计为过度断言。

## 4 局限四层（`LAYERS`）

| 层 | 关键词示例 | 写法要求 |
|---|---|---|
| 方法 method | 方法 / method / assay / 检测 / endpoint / 单一 | 单一检测、单时间点 → "不能判断效应是否可逆" |
| 样本 sample | n= / 重复 / replicat / sample / 细胞系 / line | n=3、单一细胞系 → "不能评估批间波动与细胞类型依赖" |
| 测量 measure | 误差棒 / SD / SEM / CI / 精度 / 读数 / 目视 | 未给误差棒定义 → "不解读离散度" |
| 统计 stat | p 值 / 检验 / 多重比较 / 效应量 / test / correction | 无多重比较校正 → "p 值为未校正值" |

每条都要写"因此不能得出什么"，不写"样本量有限"这类空话。少于 2 条或缺层 → `limitations_weak`。

## 5 数字与引文

- 正文每个数字必须来自 `evidence` 里某条逐字 `quote`，或来自 `derived`（带公式）；否则 `number_unverified`。
- 禁止改原文凑通过：引文对不上就改引文（回原文复制），不是改材料。
- `12.40` 与 `12.4` 视为同一值；单位不同（% vs 无）分别记录。
- 单位不明 → 不写单位，记 `uncertainty`。

## 6 交付前自查

```bash
python3 scripts/main.py init  --input /input --work /app/work --out /app/output   # 索引 + 读数行
#   写 /app/work/draft.json
python3 scripts/main.py check --input /input --work /app/work --out /app/output   # errors 必须为 0
python3 scripts/main.py build --input /input --work /app/work --out /app/output   # 成稿 + result.json
```

通过标准：`errors=0`、`numbers_verified == numbers_total`、`evidence_failed == 0`、`limitations >= 2` 且四层齐全、Results 无因果词、Discussion 有边界句、契约 `filled == total`。
