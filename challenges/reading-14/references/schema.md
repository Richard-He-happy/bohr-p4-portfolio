# 数据模式（graph schema）v1.0.0

本文件定义 `literature-knowledge-graph` 产出的节点、边、claim、证据与 result.json 字段。字段名是契约的一部分，改动须同步 `scripts/build_graph.py`、`scripts/verify.py` 与本文件。

## 1. 节点（node）

| 字段 | 类型 | 含义 | 来源 |
|-|-|-|-|
| `id` | str | `n-<sha1(规范化 label)[:8]>`，跨批次稳定 | 计算 |
| `label` | str | 该实体在原文中的**逐字**写法（第一次出现的形式） | 原文 |
| `type` | enum | `paper` / `researcher` / `material` / `method` / `task` / `dataset` / `metric` / `concept` | 推断 |
| `type_basis` | enum | `source_metadata` / `manifest_authors` / `cue_word` / `default`，标明类型是怎么来的 | 元数据 |
| `aliases` | list[str] | 同一规范化形式下的其他写法（大小写、连字符、复数、缩写） | 原文 |
| `sources` | list[str] | 出现该实体的 source_id（DOI 优先，否则文件名主语 / 文档 id） | 原文 |
| `evidence` | list[evidence] | 最多 3 条，指向首次出现处的句级引文与段号 | 原文 |
| `mention_count` | int | 命中次数（用于置信度与排序，不是统计推断） | 计算 |
| `confidence` | enum | `high`（≥2 次命中且单来源）/ `medium`（单次命中或跨来源） | 计算 |

**type 证据分级**：`label` 与 `evidence.quote` 是 `directly_read`；`type` 一律是启发式（`inferred`），取决于是否命中 `graph_rules.json` 的 `lexicon`。未定型的一律记 `concept`，不做猜测性归类。

## 2. 边（edge）

| 字段 | 类型 | 含义 |
|-|-|-|
| `id` | str | `e-<sha1(triple+source+paragraph)[:8]>` |
| `subject` / `object` | str | 节点 id，方向即 `subject -> object` |
| `predicate` | enum | `uses` / `measures` / `improves_over` / `compared_with` / `consistent_with` / `contradicts` / `is_a` / `reports` / `author_of` |
| `subject_label` / `object_label` | str | 冗余标签，便于在 CSV/查询结果里直接读 |
| `cue` | str | 触发该边的原文谓语片段（逐字） |
| `evidence` | list[evidence] | 句级逐字引文 + 段号 + 字符区间 |
| `condition` | dict | `paragraph_id`、`section`、`source_id`，以及 `note`：该断言只在该段范围内成立 |
| `direction` | str | 固定 `subject->object` |
| `evidence_strength` | enum | `direct_cue`（uses/measures/improves_over）/ `weak_cue`（对比、一致、矛盾类） |
| `cross_source` | bool | 端点是否已被跨篇对齐节点占用 |

**硬约束**：没有谓语线索（cue）的同句共现**不产生边**。共现只作为候选线索，可被查询用于人工复核，但不入图、不计分证据。

## 3. claim

| 字段 | 含义 |
|-|-|
| `claim_id` | `c-<sha1(key)[:8]>` |
| `kind` | `entity_mention` / `relation` / `cross_source_alignment` / `authorship` |
| `subject` / `predicate` / `object` | 断言主体（predicate/object 视 kind 而定） |
| `assertion` | 人可读的断言文本（**不是**新增事实，只是对 id 的复述） |
| `source_id` | 单一来源；跨篇对齐用 `+` 连接 |
| `evidence` | 逐字 `quote`，必须能在 `location` 指向的位置原样找到 |
| `location` | 定位对象，见第 4 节 |
| `condition` | 该断言成立的条件范围（段落、章节、来源、搜索范围） |
| `evidence_class` | `directly_read` / `inferred` / `undetermined` |
| `type_evidence_class` | 仅 `entity_mention`：类型的证据等级（通常 `inferred`） |
| `inference_class` | 仅 `cross_source_alignment`：`inferred` |
| `not_claimed` | 显式声明**没有**主张的东西（例如"没主张两者是同一物理样品"） |

## 4. 定位（location）

| `kind` | 字段 | 何时使用 |
|-|-|-|
| `jats_paragraph_id` | `paragraph_id`、`section`、`char_span` | 组织方提供的 JATS 段落 id（首选） |
| `source_metadata` | `field` | 标题等来源级字段 |
| `json_field` | `file`、`pointer` | `corpus-manifest.json` 的作者/license 字段，JSON Pointer 风格 |
| `text_block` | — | 无段落 id 的纯文本回退（此时 quote 仍逐字可查） |

**禁止**：不要生成 PDF 页码。本题输入是 JATS 段落与 JSON 索引，没有页码层；`char_span` 是"段内字符区间"，不是版式坐标。

## 5. result.json 字段

顶层固定字段：

```
case_id, status, output_contract, task, inputs, sources, schema, graph_summary,
nodes, edges, claims, queries, merge, uncertainty, pending_human,
errors, degradations, changes, incremental, runtime, artifacts, contract_coverage
```

- `status`：`ok`（有论文、有边、有已答复查询、引文零失败）/ `partial` / `insufficient_evidence` / `input_error`。`partial` 必须同时给出缺口（`uncertainty`、`pending_human`）。
- `merge`：`policy`、`auto_merged`（每次合并的记录：`into`、`from`、`basis`、`risk`）、`cross_source_nodes`、`non_merge_conflicts`（同名不合并的证据）、`guard`。
- `uncertainty`：每条含 `id`、`kind`、`statement`、`evidence_class`、`impact`；不得把不确定项写成事实。
- `pending_human`：每条含 `id`、`action`（人工要做什么）、`why`（为什么机器做不了）。
- `errors` / `degradations`：前者是失败步骤，后者是"降级但仍可用"（如无 pdftotext、段落 id 为合成）。
- `changes`：去重与合并的动作记录，便于复现。
- `runtime`：耗时、python 版本、是否联网、脚本路径。
- `artifacts`：产物绝对路径。
- `contract_coverage`：`provided_keys`、`filled`、`unmapped_nulled` —— 契约回填的自述，可被机械核对。

## 6. output_contract 回填规则

1. 契约原样保存在 `output_contract`（键名不改）。
2. 每个契约键都在顶层出现：能按语义映射的填真实内容，映射不到的填 `null` 并列入 `contract_coverage.unmapped_nulled`。
3. 映射表（子串匹配，先中文后英文）：节点/实体→`nodes`，边/关系→`edges`，查询→`queries`，结论/claim→`claims`，证据→`evidence`，来源/文献→`sources`，不确定→`uncertainty`，人工→`pending_human`，类型/定义→`schema`，摘要→`summary`，图谱→`graph_summary`，合并/对齐→`merge`，增量→`incremental`，自查/检查→`self_check`。
4. 缺值一律 `null` 或 `[]`，**不省略键**。

## 7. 三类可读性标注

| 标记 | 判据 | 例子 |
|-|-|-|
| `directly_read` | 引文能在该位置逐字找到；实体 label 是原文子串 | 段落 p-12 里的 "we used SAC305 solder paste" |
| `inferred` | 由规则从直接证据推出，且规则写在包内 | 实体类型来自 lexicon；跨篇对齐来自规范化字符串相同 |
| `undetermined` | 材料里没有能判定的信息 | 两篇是否同一批样品、同一数据集 |
