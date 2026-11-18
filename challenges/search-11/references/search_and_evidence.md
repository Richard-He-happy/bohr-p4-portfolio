# 检索式构造、打分、证据与降级规则

本文件是 `ptcore.qplan()` / `ptcore.retrieve()` / `main.screen()` / `main.audit()` 的口径说明，可直接复用于其他专利检索 Agent。

## 1. 检索面（一次任务要同时回答的五件事）

| 面 | 对应产物 | 判断"做到了"的依据 |
|---|---|---|
| 这件专利保护什么 | `claims[]`（逐条逐字 + locator） | 有 `quote`、`locator`、`claim_no`、`independent` |
| 与同族什么关系 | `families[]`（观测链接） | 有 `basis`（共享的优先权/申请号）与 `caliber` |
| 现在是否有效 | `legal_status[]` | 只有三档之一，`not_in_corpus` 必须带 `pending_human` |
| 同主题还有谁在做 | `candidates[]`（专利 + 非专利文献） | 每条有 `query_id` 与 `relevance_reason` |
| 是否有权访问与展示 | `sources[*].license_note`、`degradations` | 无许可字段时标注"内部使用"，不做原文外传 |

任务只覆盖其中一部分时，未覆盖的面写进 `coverage.gaps` 与 `summary.what_was_not_done`。

## 2. 查询规划（4 类，写入 `queries[]`）

| 类型 | 来源 | 例子（示意） | 说明 |
|---|---|---|---|
| `explicit` | 输入中声明的检索式（文件名含 `quer`） | 原样保留 | `source=input:<file>#<locator>` |
| `number` | `scope.seeds` / 目标号码 / 语料公开号 | `US99000000B2` | 同时把 `stem` 与原始写法放入 `expanded` |
| `topic` | 主题词（scope.topic/keywords） | `ceramic coated separator solid electrolyte` | 分面扩展见下 |
| `topic`（扩展） | 语料高频共现词、IPC/CPC | `… H01M50/449` | `source=planner:expansion` / `planner:classification` |

主题检索的**分面模板**（缺哪面就少一路覆盖，须在 `coverage.gaps` 注明）：

```text
(关键词 OR 同义词) AND (IPC/CPC)            # 技术主题
(申请人/发明人) AND (关键词)                 # 竞争主体
引证关系：被引/引用                          # 需要引文图数据，离线时缺失
同族：优先权号 / 申请号                       # 需要族数据，离线时只做观测链接
```

离线场景的诚实写法：`db=local_corpus`，并在 `coverage.recall_estimate` 写明"无 gold set、未查外部库，召回不可估计"——**不写 P@k/nDCG@k 的具体数值**。

## 3. 打分（可解释、可复算）

```text
score = 0.55*number_exact + 0.30*term_overlap + 0.08*classification + 0.05*assignee + 0.02*base
```

| 分量 | 计算 | 说明 |
|---|---|---|
| `number_exact` | 归一化后 `stem` 命中 → 1.0 | 号码查询的决定性信号 |
| `term_overlap` | 与查询词集（去停用词）的交集比例 | 记入 `relevance_reason` 的分子/分母 |
| `classification` | 查询扩展中的 IPC/CPC 出现在文档分类号 → 1.0 | 分类号来自语料自身，不凭记忆填 |
| `assignee` | 查询扩展中的申请人名出现在文档申请人 → 1.0 | 名称取自语料 |
| `base` | 主题查询的文档类型匹配加成 | 固定 0.02 |

`relevance_reason` 必须能复算出分数，例如：`number_exact(US99000000B2); term_overlap=0.35(7/20)`。
未命中（`score=0`）的文档不进 `candidates`；若某查询整条为空，写 `status=no_hit`。

## 4. 证据规范（可核验性）

| 要求 | 实现 |
|---|---|
| 逐字 | `evidence.quote` 只截取单一字段值（`abstract/summary/description/claims/title`），不做拼接与润色 |
| 定位 | `evidence.locator` = `文件#JSON指针` / `文件#char:偏移` / `page:N` / `row:N` |
| 版本 | `source_sha256`（完整）+ `sources[*].sha256`（短）来自同一读取时刻 |
| 时间 | `retrieved_at`（读取时刻）+ `verify_report.generated_at`（自检时刻） |
| 可复核 | `verify_report.json` 的 `quote_found_in_source` 会重读源文件核对引文 |
| 不可核验时 | `quote_verified=false` 保留在候选中并计入 `failed`，**不删除候选、不改原文** |

引文长度上限 400 字符（候选摘要）、600 字符（权利要求）；超长不截断原文，只截断展示并保留 `locator`。

## 5. 筛选（include/exclude 必带理由）

| 判据 | 排除理由写法 |
|---|---|
| 同一归一化号码重复 | `duplicate of C0x (same normalised number + title)` |
| 年份超出 scope | `year 1998 outside scope 2015-2024` |
| 无任何可引原文（仅元数据桩） | `no verbatim evidence locatable in source (metadata stub)` |
| 其他 | 默认保留，理由 `in scope and has a located source` |

筛选只做"是否进入交付集"，**不删除**被排除项：`candidates` 全量保留，`include=false` + `exclude_reason`，便于复核。

## 6. OCR 与多语言

- 传真件文本可能整页合并：`provenance=page_merged_ocr`，并在候选 `flags` 标 `ocr_page_merged`。
- 引文保留 OCR 原样（双空格、断词、页眉），不"修正"；`locator` 的字符偏移以抽取文本为准。
- 无文本层（纯扫描）时不猜测内容：写 `errors` + `pending_human`，该文档不参与结论。
- 中文/日文/韩文按字符 bigram 参与词集匹配；跨语言检索需另配词表，缺词表时在 `gaps` 注明。

## 7. 降级与异常（与 SKILL.md §10 对应）

| 情形 | 处置 | 字段 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 退回 `task.md`；坏 JSON 记 error 后继续 | `degradations` / `errors` |
| 单文件解析失败 | 跳过该文件，其余继续 | `errors[stage=ingest]` |
| PDF 无文本层 | 记 error，不进入结论 | `errors` + `pending_human` |
| 429 | 用缓存载荷，不重试风暴 | `degradations` + `uncertainty[ratelimit:*]` |
| 401/403 | 排除该源，不猜测、不绕墙 | `errors` |
| 空命中 | `status=no_hit` + 覆盖限制说明 | `queries` / `uncertainty[empty:*]` |
| 状态缺失 | 逐号码人工复核清单 | `pending_human[legal_status:*]` |
| 状态冲突 | 定序规则，不取平均 | `uncertainty[status_conflict:*]` |
| 阶段异常 | 该阶段空默认，最终 `status=partial` | `errors[stage=*]` |

## 8. 预算

- 无网络、无模型请求；单文件读取上限 2MB、最多 400 个文件、PDF 单文件 18MB 上限。
- 不重试外部接口（离线），限流只做"用缓存 + 记录"。
- 近饱和时的写法：先把 `partial` 落盘（运行一开始就做），再逐阶段推进。
