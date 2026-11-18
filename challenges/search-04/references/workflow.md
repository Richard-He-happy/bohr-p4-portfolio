# 方法：扩展策略、停止判据、排序、基线与复核

## 1 为什么不是"关键词 + 高被引"

关键词检索找得到同名词，找不到来路。本 Skill 只认三种关系，每种都能指回一条具体记录：

1. **backward**：种子自带的参考文献表（方法与数据出处、奠基工作）。
2. **forward**：其他保留记录的参考文献表里出现了种子（后续改进、批评、复用）。
3. **parallel**：不直接引用但同源——与种子共享 ≥2 条参考文献（文献耦合），或被同一批工作共同施引（共被引）。

判断"做对没有"的标准不是条数，而是：扩出来的每一篇能否顺着边说清来路，每条边能否指回一个文件与 JSON 路径，去重后的清单是否干净。

## 2 扩展

有向 BFS。队列元素是 `(work, hop)`：

- 每个节点分别向 `out-edges`（backward）与 `in-edges`（forward）展开，两个方向独立计数、独立裁剪。
- 单节点单方向最多取 `fanout=30` 个邻居；候选总数上限 `3×cap`（`cap` 来自 `--max-candidates` 或 case 的 `max_k/top_k/k`）。
- 层数上限 `depth`（默认 2，可由 `--depth` 或 case 的 `depth/expansion_depth/hops` 覆盖，夹在 1–4）。
- 邻居排序按题名长度降序（长题名更可能是真论文而不是 stub），保证裁剪时先丢低信息量节点。
- 一个节点若同时被两个方向触达，`edges` 会累积多条边，用于后续的方向证据。

**停止判据**（四者任一满足即停）：

1. 队列空；
2. `hop >= depth`；
3. 候选数达上限；
4. 触及 760s 软时限（`DL`），或扫描阶段剩余 <60s。

不使用"分数阈值"停止，因为分数是相对量，阈值会随学科漂移。

## 3 排序

```
score = 0.40*relation + 0.20*proximity + 0.15*topical + 0.15*centrality + 0.10*recency
```

| 分项 | 定义 |
|-|-|
| `relation` | forward=1.0，backward=0.85，parallel=0.60，seed=1.0；每多一层减 0.05，下限 0.30；`metadata_confidence=low` 再乘 0.85 |
| `proximity` | `1/(1+hop)` |
| `topical` | 主题词集合与题名+摘要前 400 字的命中率，按 `min(|主题词|,4)` 归一 |
| `centrality` | 该节点度数 / 图内最大度数 |
| `recency` | `(year-ymin)/(ymax-ymin)`；无年份或年份全同记 0 |

五个分项全部写入 `relevance_breakdown`，`relevance_reason` 用一句话复述，所以"为什么排第 3"是可读的，不是黑箱。

关系权重 > 邻近 > 主题 > 中心性 > 年份，是因为本题要的是"沿着引用说清来路"：主题词重叠会把同领域但不相关的工作排上来，这正是要压制的。

## 4 身份合并

预印本、会议版、期刊版、增补版会以不同 DOI 散落在不同库。合并按下表分层，每条合并记录触发规则：

| 层 | 条件 | 风险控制 |
|-|-|-|
| 1 | DOI 相同 | 无 |
| 2 | PMID / arXiv / OpenAlex / S2 id 相同 | 无 |
| 3 | 规范化标题完全相同 | 年份差 >3 → 不合并，打 `homonym_suspect` |
| 4 | 标题相似度 ≥0.93 且长度差 ≤35% 且年份差 ≤1 且共享作者姓氏 | 四项同时满足才合并 |

合并后主值取"字段最全"的那条（先比 `metadata_confidence`，再比摘要长度），其余来源进 `provenance`。标题规范化：NFKD → 小写 → 去 HTML 标签 → 非字母数字替换为空格 → 压空白；规范化后短于 15 字符的标题不参与键匹配。

## 5 覆盖与缺口（而不是 Recall）

`Recall@k` 需要金标准，本 Skill 没有，所以 **`coverage.recall_estimate` 恒为 `null`**，只报告能在保留图上算清的量：

- `seed_neighbourhood_coverage`：与种子直接相连的保留边中，有多少条的另一端出现在返回集里。这是"我把我手上的图用完了没有"，不是"我覆盖了全世界"。
- `gaps`：无前向引用的种子数、无法解析到记录的边数、仅标识候选数、撤稿/更正/预印本标记。

把这三类写成缺口，比写一个漂亮的 Recall 数字更有用——审稿人一眼能看出哪些方向没做。

## 6 基线协议（用于"增益可验证"）

同一次运行内，用同一套 `set_metrics` 计算两组指标：

| 组 | 定义 |
|-|-|
| 候选集 | 本 Skill 输出：已合并、有方向、有定位、有排序 |
| 基线 | 同一批保留记录上的朴素关键词匹配：命中主题词即入选，按输入顺序取前 k；不合并、不标方向 |

`baseline.delta` = 候选集 − 基线。典型差值落在三处：`duplicate_rate`（合并带来的重复下降）、`direction_labeled_rate`（0 → 1）、`related_basis_rate`（0 → >0）。

**注意**：这是运行内对照，用于说明"相对朴素做法改了什么"，**不是**组织方白板分数，`note` 字段已写明。平台侧的公平对照由平台自己跑。

## 7 复核流程（他人可独立验证）

1. 打开 `result.json`，看 `status`；`partial` 时先读 `uncertainty` 与 `degradations`。
2. 随机取 3 条 `candidates`，按 `source_locator.file` 打开原文件，用 `json_pointer` 定位，核对题名/DOI 一致。
3. 取 3 条 `edges`，确认 `citing` 的参考文献表里确实有 `cited`（方向不能反）。
4. 取 1 条带 `homonym_suspect` 或 `retraction_marker` 的候选，确认它没有被当成干净结果。
5. 对照 `coverage.gaps`，确认你已知的缺口在内。
6. 重跑同一命令，`checks` 与 `counts` 应完全一致（无随机源）。

## 8 一个玩具算例（示例，非正式案例结果）

输入 4 条记录：种子 S（2019，引用 R1、R2），F1（2020，引用 S，题名为 S 的"期刊版"），F2（2022，引用 S 与 R1），P1（2021，引用 R1、R2 但不引用 S）。

期望：

- backward：R1、R2（hop1）；
- forward：F1、F2（hop1）；
- parallel：P1 与种子共享 2 条参考文献 → `basis = "2 shared refs"`；
- R1 同时被 F2 施引、且与种子共被引 → `basis` 含 `co-cited by 1`；
- 方向标注率 1.0，定位率 1.0，`recall_estimate = null`。

实际运行（本仓库自测）得到 5 条候选、7 条边、`self_check_pass = true`，与上述期望一致。这个算例只用来展示接口与判定逻辑，不代表任何正式案例。
