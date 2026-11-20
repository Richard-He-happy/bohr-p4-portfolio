---
name: literature-knowledge-graph
description: 从一批论文（JATS XML / JSON 段落索引 / 纯文本 / DOCX）构建带逐字证据的文献知识图谱：抽实体与关系、别名归一与跨篇对齐、来源绑定、图谱查询，并导出 result.json、graph_raw.json、claims.json、queries.md、nodes.csv、edges.csv 与核验报告。Use when a task asks to turn papers into a queryable knowledge graph with nodes, edges, evidence locators, entity alignment, merge decisions or literature-graph queries. Not for single-paper translation, pure summarisation or generic QA.
version: 1.1.0
---

# 文献知识图谱构建（literature-knowledge-graph）

一句话用途：把给定科研材料真实解析为可查询、可回源的文献知识图谱，并将实体、关系、别名对齐、跨篇对齐与查询结果落到可复核文件。

> 脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本骨架、模板或脚本首次输出直接当最终成品；必须先跑本包脚本得到基线，再由 Agent 对原文、证据位置、关系方向、合并冲突和查询结果逐项核验、修正、增强后提交。

## 0. 完整性优先（最高优先级）

1. 进入任务后，先运行本 Skill 自带主脚本/流程，产出全套基线交付物：所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段。
2. 后续 Agent 的校验、改写、增强只能在此基线上增加或修正；不得删除、清空、遗漏基线与契约字段。若不确定是否应删除，保留原产物并在 `result.json.changes` 中写一条 `agent_reviewed`。
3. 提交前必须逐项核对「`output_contract` 字段 × 磁盘产物 × `result.json` 键」三者一一对应；缺任何一项先补齐再收尾。`partial` 状态必须列出缺失项。
4. 在基线之上，由 Agent 亲自核验关键论断、数字、引文、来源一致性，并把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`）。这是“genuinely-derived”的证据。

## 1. 用途与边界

做：实体/关系抽取、别名归一、跨篇对齐、证据绑定、图谱导出、查询执行、增量续建规则。
不做：图像像素/图注读数、OCR、PDF 页码定位、跨篇数值元分析、用常识补全原文没有的实体或关系。

固定科研案例要求把两篇独立论文纳入同一张图谱，并保留每篇独立的 `source_id`、段落 ID 与原文短引。根 DOI/title/authors 只属于第一篇；第二篇用其自身元数据。同一篇的多种文件格式不算跨篇证据。

## 2. 运行契约

- 输入目录：`/input/`
- 工作目录：`/app/work/`
- 最终产物目录：`/app/output/`
- 先建目录，再运行基线：

```bash
mkdir -p /app/work /app/output
python3 -B /skills/weekly-skill/scripts/build_graph.py --input /input --output /app/output
python3 -B /skills/weekly-skill/scripts/verify.py --input /input --output /app/output
```

- `build_graph.py` 负责解析、去重、抽取、归一、图导出；`verify.py` 负责引文核验、claim 派生、查询执行、CSV/报告导出、契约终填。
- 若第一条命令已自动调用 `verify.py`，也仍可在 Agent 修正产物后显式再跑一次 `verify.py` 复核。
- 只用包内脚本与 Python 标准库；不联网；不依赖 CWD；退出码恒 0。
- 第一秒/第一阶段结束就写 partial `result.json`；任何异常都被捕获并落盘；最终无条件覆盖为完整或诚实 partial 结果。
- `case_id` 原样保留；`output_contract` 全部原始键必须原样出现在最终 `result.json` 顶层，键名不改；缺值用 `null`/`[]` 并在 `contract_coverage.unmapped_nulled` 说明。

## 3. 输入发现与材料解析流程

### 步骤 1：盘点输入与运行契约

- 输入：`/input/case.json`、`/input/task.md`、`/input/*` 下的材料与 manifest。
- 动作：
  1. 读取 `case.json`，提取 `case_id`、`task_instruction`、`output_contract`、材料清单/提示。
  2. 若 `case.json` 缺失，递归查找 `case*.json`；仍失败则只扫描目录，并记 `uncertainty[U-CASE]`。
  3. 列出 `output_contract` 的全部字段名，作为最终 `result.json` 的必填顶层键。
  4. 检查是否存在 `corpus-manifest.json`；若存在，读取每篇的 `doi`、`authors`、`source_hash`、`license`，并记入 `sources`。
  5. 检查是否存在 `material.json`、`primary-material.json`、`secondary-material.json`、`secondary-publisher.xml` 等材料。
- 输出：输入清单、材料清单、契约键清单、预算与风险标记。
- 失败分支：无 `case.json` 也要继续；契约缺失则记 `uncertainty[U-CONTRACT]` 并继续用默认字段集合。

### 步骤 2：真实解析材料并建立来源索引

- 输入：上一步发现的全部材料文件。
- 动作：
  1. 运行 `build_graph.py` 生成基线产物。基线产物必须保留。
  2. 对 JSON/XML 材料，按扩展名和内容判断类型；JSON 用“同时有文本键和 id 键”识别段落对象；XML 抓 JATS 的 `<article-id>/<article-title>/<sec><title>/<p id=>`。
  3. 对 DOCX，如脚本支持则解包 XML 提取段落；对 PDF，只有在能取得真实文本层时才提取，否则跳过并列入缺口。
  4. 读取 `material.json` 时只作为段落汇总索引，不替代 `primary-material.json` 或 `secondary-material.json` 的原文定位。
  5. 来源划分规则：
     - 第一篇：`primary-material.json`，使用其 DOI/title/authors。
     - 第二篇：`secondary-material.json`，不得套用第一篇根 DOI/title/authors。
     - `corpus-manifest.json` 中存在两篇独立文献条目时，以该 manifest 的 DOI/作者/许可为准。
     - 同一段正文只保留一份；去重按内容哈希 + 文件优先级 `primary` > `secondary` > 其他 > `material.json` 汇总。
  6. 位置字段一律采用组织方 JATS 段落 ID（`paragraph_id`），不要生成 PDF 页码，也不要把自建连续号称为原 PDF 页。
  7. 对正文行内公式/上下标被线性化的情况，可参考 `secondary-publisher.xml`，但不推断底层数值。
- 输出：`graph_raw.json` 中 `source_id||paragraph_id -> {source_id, paragraph_id, section?, text}` 索引、来源清单、去重与退化记录。
- 失败分支：
  - 材料缺失/损坏：跳过该文件，记入 `errors[stage=parse]` 与 `pending_human`。
  - 无任何可解析段落：最终 `status=input_error`，空图 partial，退出码 0。
  - 段落无组织方 ID：生成并标注合成 ID，记 `degradations[PID_SYNTHETIC]`。

### 步骤 3：构建实体、关系、对齐与冲突记录

- 输入：段落索引、两篇论文原文、`references/graph_rules.json` 的词表/cue/策略开关。
- 动作：
  1. 实体抽取优先用词表 + 大写短语 + 缩写/型号；段内不重叠，取最长匹配，规范化后分配 `n-<sha1[:8]>`。
  2. 关系只在有直接句内 cue 与左右实体时建立，不把共现、综述转述或推测当成直接证据。明确关系类型、方向和适用条件。
  3. 每个实质节点/边必须携带：`source_id`、`paragraph_id`、`evidence.quote`（原文短引，不超过 400 字符）、`location.kind=jats_paragraph_id`、`char_span`、`evidence_class`。
  4. 别名归一：
     - 同一论文内同一规范化形式可合并，必须记录 `merge` 依据；
     - 字符串字形相同或缩写相同但全称不同的，不得强制合并，应保留不同节点并写入 `merge.non_merge_conflicts`。
  5. 跨篇对齐：
     - 只有两篇文本都能明确指向同一具体对象、样品、模型实例、数据集或注册标识时才合并；
     - “相同通用方法/材料术语”不足以说明两篇使用了相同物理样品、模型实例、数据集或实验条件；
     - 不能把两篇的条件、样本、数值结果合成一个结论。
  6. 指标只按来源分别列出，不做跨篇算术合并。
- 输出：`nodes`、`edges`、`claims`、`merge` 初稿，并落 partial `result.json`。
- 失败分支：
  - 线索不足处不建边；
  - 冲突处同时保留对立证据，各自带段号与引文，不覆盖、不裁决；
  - 合并不确定的实体进入 `pending_human[H-MERGE]`。

### 步骤 4：Agent 亲自核验并产出完整成品

- 输入：脚本基线 `graph_raw.json`、`nodes.csv`、`edges.csv`，以及 `primary-material.json`、`secondary-material.json`。
- 动作：
  1. 抽查关键节点标签是否确为材料原文子串；关系主语/谓词/宾语是否与 cue 方向一致。
  2. 对重点实体和边，回到 `paragraph_id` 原文片段核验 `evidence.quote`。
  3. 检查跨篇合并判断：是否错把同名字段/通用术语合并；是否漏掉本应合并的同一实体。
  4. 至少检查 3 条查询，确认查询确为实际执行、有结果子图与证据，且不确定项被明确标注。
  5. 修正或补强后运行 `verify.py` 复核；保留所有真实核验结果。
- 输出：由 Agent 撰写的最终图谱说明、查询说明、不确定性、限制、人工确认项。
- 失败分支：Agent 修正失败或无法完成核验时，仍保留脚本基线，并在 `result.json.changes` 写明“agent_review_partial”，不得删除事实产物。

### 步骤 5：自检 rubric 并回填 `result.json`

- 输入：完整产物、原始 `output_contract` 字段。
- 动作：
  1. 逐项核对 `output_contract` 每个字段是否已在 `result.json` 顶层出现。
  2. 核对 `result.json` 是否含：`case_id`、`status`、`sources`、`nodes`、`edges`、`claims`、`queries`、`merge`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`contract_coverage`。
  3. 更新 `status`：仅在关键契约字段非空且引文核验通过时为 `ok`；否则 `partial`；无材料为 `insufficient_evidence`；输入完全不可用为 `input_error`。
  4. 更新 `contract_coverage.filled` 与 `unmapped_nulled`。
  5. 写最终 `result.json`。
- 输出：合法最终 `result.json` 与完整产物集。
- 失败分支：任何异常都保留已有 partial，退出码 0。

## 4. 预算策略（64 次模型请求 / 900 秒 / 单次 16384 tokens 含推理）

按 64 次模型请求分配：

- 第 1–3 次：读 `case.json`、`task.md`、`corpus-manifest.json`，锁定契约与两篇来源。
- 第 4–8 次：运行脚本并检查 stdout/stderr，记录脚本是否自动完成、生成了哪些文件、是否缺失关键字段。
- 第 9–24 次：分批读取 `primary-material.json` 与 `secondary-material.json` 的关键段落，做 Agent 级实体/关系/证据抽检。优先读开头、方法、结果、结论及脚本生成节点/边对应段落。
- 第 25–36 次：核验重点实体/边，生成/修正跨篇对齐与 `non_merge_conflicts`。
- 第 37–46 次：执行/核验查询；为每类查询写结果、证据和不确定项。
- 第 47–56 次：回填/修正 `result.json`、`queries.md`、`claims.json`、CSV；必要处补 `pending_human`。
- 第 57–64 次：最终自检与兜底；若时间已过 840 秒或请求已接近上限，停止新工作，把当前最完整 partial 写成合法 `result.json`。

优先级：`output_contract` 字段 > 节点/边/证据 > 跨篇对齐与冲突 > 查询 > 格式美化。务必在阶段结束时落盘 partial；脚本失败、解析失败或超时时仍输出合法 `result.json`，不要死循环或反复读同一批大文件。

## 5. 隐藏案例鲁棒性

| 情形 | 行为 | 落点 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 递归发现其它 `case*.json`；仍失败则只扫描目录并继续 | `errors` + `degradations` + `uncertainty[U-CASE]` |
| `corpus-manifest.json` 缺失 | 从段落自带 `source_id`/`doi` 或正文 DOI 分篇；无法确定则标出并继续 | `uncertainty[U-SOURCE]` |
| 输入为空/目录不存在 | 空图 partial，`status=input_error` 或 `insufficient_evidence`，退出码 0 | `uncertainty[U-INPUT]` |
| 无任何可解析段落 | 空图，`status=input_error` | `pending_human[H-NOMAT]` |
| PDF 无文本层或图像型材料 | 跳过并列出人工项，不猜测数值 | `degradations[PDF_UNPARSED]` |
| 段落无组织方 ID | 生成并标注合成 ID，不冒充原 JATS/PDF 页码 | `degradations[PID_SYNTHETIC]` |
| 单文件解析异常 | 仅跳过该文件，保留其它材料结果 | `errors[stage=parse]` |
| 引文核验失败 | 不删除条目；计数、列样例、`status` 降 `partial` | `uncertainty[U-QUOTE]` |
| 查询无结果 | 保留查询、`status=no_result`，并说明可人工接管位置 | `queries[]` |
| `output_contract` 缺失 | 使用默认字段集合，并在 `contract_coverage.unmapped_nulled` 说明 | `uncertainty[U-CONTRACT]` |
| 超时/请求将尽 | 停新动作，写出当前最完整合法 partial，退出码 0 | `degradations[TIMEOUT]` |

任何情况下都要产出合法 `result.json`，退出码 0；材料不足时用 `pending_human` / `limitations` 明确标注，不得编造数据、引用、分数或白板结果。

## 6. Rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果：任务完成度 | 15 | 两篇论文都进入图谱；节点、边、查询与产物齐全；至少 3 条查询实际执行 | `nodes`/`edges`/`queries`/`artifacts` 非空；`queries` 含 executed 状态；产物齐全 |
| 实际效果：结果正确性 | 15 | 实体真实来自原文；关系方向/类型与原文一致；不把通用术语当同一对象 | `evidence.quote` 为原文子串；`verify_report.quotes_failed == 0`；跨篇 merge 有依据 |
| 实际效果：结果完整性 | 5 | 覆盖任务要求的实体类型、关系类型、证据字段与查询问题 | `graph_summary` 类型覆盖；两篇均有边；`result.json` 覆盖契约字段 |
| 实际效果：结果可核验性 | 5 | 节点/边可回到论文具体段落和原文短引；合并与冲突有记录 | `source_id`/`paragraph_id`/`char_span` 与 `merge`/`non_