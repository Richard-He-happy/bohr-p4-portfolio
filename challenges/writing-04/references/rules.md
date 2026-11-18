# 判据与规则表（去重 / 引用匹配 / 编号 / 核验）

本文件是 `reftool.dec()`、`reftool.dedup()`、`main.best()`、`main.scan()`、`reftool.checks()` 的规格说明。
改动实现时请同步本表；评审与复现均以此为准。

## 1. 文本归一化

| 函数 | 规则 | 目的 |
|-|-|-|
| `nz(s)` | NFKC + 小写 + 去所有非字母数字（含中文） | 作者、刊名比较 |
| `nt(s)` | 去 HTML 标签 + NFKC + 小写 + 非 `[0-9a-z中文]` → 空格 + 折叠 | 题名比较、词项切分 |
| `nd(s)` | 去 `doi:`、`https://doi.org/`、尾随标点 + 小写 | DOI 比较 |
| `yr(s)` | 抓首个 `19xx/20xx` | 年份回填 |

## 2. 去重判据链（按顺序命中即返回）

对库内每一对条目 `(a,b)` 计算：

| 序 | 条件 | 置信度 | 理由码 | 动作 |
|-|-|-|-|-|
| 1 | 两边 DOI 归一后非空且相等 | 0.99 | `doi_exact` | 合并 |
| 2 | 题名归一后相等，年份差 ≤2（或任一方缺年份），且首作者相同或任一方缺作者 | 0.95 | `title_normalized_equal` | 合并 |
| 3 | 题名归一后相等，但双方都有作者且首作者不同 | 0.80 | `title_equal_author_differs` | 合并（多为同题不同署名版本，保留双方来源） |
| 4 | 题名相似 ≥0.93，首作者相同，年份差 ≤2（或缺失） | 0.88 | `title_sim_0.xx` + `same_first_author` | 合并（预印本/正式版、中英文题名接近） |
| 5 | 题名相似 ≥0.85，首作者相同，年份相同，刊名归一后相同 | 0.80 | `title_sim_0.xx` + `same_author_year_container` | 合并 |
| 6 | 题名归一后相等但年份差 ≥3 | 0.0 | `title_equal_year_gap_N` | **不合并**，进 `ambiguous_pairs` |
| 7 | 题名相似 ≥0.85 但无作者证据 | 0.0 | `ambiguous_sim_0.xx` | **不合并**，进 `ambiguous_pairs` |

相似度：`max(SequenceMatcher(nt(a), nt(b)).ratio(), Jaccard(词集合))`。

合并执行（并查集）：

1. 组内按 `completeness`（title/authors/year/container/volume/pages/doi 命中数）降序取基准条目。
2. 只**补空**，不覆盖：`title/year/container/volume/issue/pages/doi/publisher/url` 及更长的作者列表。
3. 记录 `fills=[{field, from}]`、`merged_from=[key…]`，基准条目保留自身 `source`。

**防误合并的硬约束**：题名相似但年份差 ≥3 一律不合并；同名作者的不同文献因题名不同不会进入判据 2–5；任何低于 0.80 的对都不合并。

## 3. 原文献表 ↔ 文献库对齐

题名/DOI 按 §2 判据与库条目逐条比对，首个 ≥0.80 命中即认作同一文献（`orig_map[n]=key`）。
未命中：保留原编号、不重排该标记、写入 `pending_human`（`item=manuscript_ref_N`）。
稿件没有文末表时：按文献库读取顺序建立 1..N 的隐式映射。

## 4. 论断级引用匹配（插入）

1. 候选句：段内分句后，**不含任何引用标记**、长度 ≥15 字、匹配 `CLAIM` 正则（数字/百分比/`p<0.05`/`显著/表明/说明/发现/证实/提示/提高/降低/增加/减少/约为/达到/相比/归因` 或英文 `significan|indicat|suggest|show|found|increas|decreas|reduc|higher|lower|correlat|associat`）。
2. 词项集：英文取长度 >2 的实词（去停用词表 `STOP`），中文取相邻二元组。
3. 打分：`score = |句∩条目| / |条目词项|`，条目词项 = 题名 + 摘要前 400 字；该条目已被引用过时乘 0.85。
4. 插入条件：`score ≥ 0.20` 且命中实词 ≥3；句末标点前插入 `[n]`（`[[INS:key]]` 令牌先占位，再由编号阶段统一渲染）。
5. 单次运行最多插入 40 处；`--no-insert` 时只登记建议（`change_log.applied=false`）。

阈值取舍：0.20 偏保守（宁可漏插也不乱插），因为错插引用比缺引更伤"结果正确性"；放宽到 0.10 会显著增加无关插入。

## 5. 编号重排

- 扫描顺序：段落（非空行）→ 句 → 句内标记；**首现即编号**，后续复用。
- 标记形态：`[1]`、`[1,3]`、`[3-5]`、`^[1]^`、`\cite{a,b}`、`[@a]`、内部 `[[INS:key]]`。
- 区间展开：`3-5` → 3,4,5（跨度 >60 视为异常，丢弃该段）。
- 输出压缩：连续 ≥3 个编号写成 `a-b`，否则逗号列出；上标形式保留 `^…^` 包裹。
- 孤立编号（超出原文献表长度）：原标记不动，记 `unresolved_markers`。
- 未被引用的库条目：不进最终列表，计入 `counts.uncited_entries`；原文文献表中未被引用的条目同样剔除（原始文本仍保留在输入文件中）。

## 6. 一致性核验（`verification.checks`，10 项）

| id | 判定 | 通过条件 |
|-|-|-|
| `numbering_continuous` | 正文编号集合 | 等于 `1..max` |
| `ref_list_covers_body` | 列表条目数 vs 正文最大编号 | 条目数 ≥ 最大编号 |
| `no_orphan_citation` | `citation_map` 中空 key | 无 |
| `doi_syntax` | 每条 DOI | 匹配 `^10\.\d{4,9}/\S+$` |
| `no_duplicate_doi` | DOI 去重后数量 | 与总数一致 |
| `entries_have_title` | 条目题名 | 全部非空 |
| `evidence_has_locator` | `evidence_map` | 非空且逐条有 locator |
| `facts_preserved` | `preserved_facts[].kept` | 全部为 true |
| `dedup_explained` | `dedup_decisions[].reasons` | 全部非空 |
| `weak_claim_matches`（计数，非布尔） | `citation_map` 中 `verdict=weak_match` | 仅报告 |

`facts_preserved` 提取前会先移除引用标记，避免 `[3-4]` 这类区间被误判为"数字丢失"。

## 7. 失败模式与处置（实测经验）

| 现象 | 根因 | 处置 |
|-|-|-|
| 库记录数为 0 | 库被判定为 `unknown`；或 `.csv/.xlsx/.enw` | 看 `degradations`；转 RIS/CSL-JSON 后重跑 |
| 稿件自带文献表被当成第二个库 | 早期版本未排除稿件文件 | 已在 `main.pipeline` 排除稿件与 `case.json` |
| 同一文献出现两条 | 判据 4 的作者名写法不一致（`Wang, Ming` vs `王明`） | 保留两条并进 `ambiguous_pairs`；建议在库中统一作者写法 |
| 中文条目在 APA 下作者为原文 | 无转写能力 | 人工按期刊要求改写 |
| `weak_match` 很多 | 论断与文献主题确实不符，或题名过短（<3 个实词） | 人工补引；或补充摘要字段提高区分度 |
| 编号跳号 | 原文献表条目数少于最大编号 | 看 `unresolved_markers`，补全原表后重跑 |
| 全部条目变 `[待补]` | 库字段缺失（常见于仅导出题名的 CSV 转 RIS） | 补齐 DOI/卷期页后重跑 |

## 8. 调参指引

| 目标 | 位置 | 建议 |
|-|-|-|
| 更激进补引 | `main.pipeline` 中 `sc >= 0.2` | 降到 0.15，同时把命中实词数提到 4 |
| 更保守合并 | `reftool.dec` 判据 3 | 把 0.80 改为 0.0（改为不合并，进歧义对） |
| 增加样式 | `reftool.render` | 复制 gbt/apa 分支，改模板；同步 `styles.md` |
| 支持新库格式 | `reftool.PARSER` | 写 `pXXX(text, src) -> list[rec]` 并注册键名 |
