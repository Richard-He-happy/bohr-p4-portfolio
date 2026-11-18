---
name: literature-knowledge-graph
description: 从一批论文（JATS XML / JSON 段落索引 / 纯文本 / DOCX）构建带逐字证据的文献知识图谱：抽实体与关系、别名归一与跨篇对齐、来源绑定、至少 6 个实际执行的图谱查询，并导出 result.json、graph_raw.json、claims.json、queries.md、nodes.csv、edges.csv 与核验报告。Use when a task asks to turn papers into a queryable knowledge graph with nodes, edges, evidence locators, entity alignment, merge decisions or literature-graph queries. Not for single-paper translation, pure summarisation or generic QA.
version: 1.0.0
---

# 文献知识图谱构建（literature-knowledge-graph）

## 1. 用途与边界

把"一批论文"变成**可查询、可回源**的知识图谱：每个节点与每条边都挂在论文的某个段号与一段逐字引文上；跨篇只在有依据时对齐，不合并不同论文的条件与数值。

做：实体/关系抽取、别名归一、跨篇对齐、证据绑定、图谱导出、查询执行、增量续建规则。
不做：图像像素/图注读数、OCR、PDF 页码定位、跨篇数值元分析、用常识补全原文没有的实体。

## 2. 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 材料（JATS/XML、`material.json` 段落索引、`primary-*/secondary-*`、`corpus-manifest.json`、txt/md/docx）。
- 输出：`/app/output/`（或 `--output` 指定）。
- 两步，第二步由第一步自动调用：

```bash
python3 /skills/weekly-skill/scripts/build_graph.py --input /input --output /app/output
python3 /skills/weekly-skill/scripts/verify.py       --input /input --output /app/output
```

- 只用 Python 标准库；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent`）；退出码恒 0。
- 第一秒就写 partial `result.json`，任何异常都被捕获并落盘，最终无条件覆盖为完整结果。
- `case_id` 原样保留；`output_contract` 全部键原样回填（键名不改，缺值 `null`/`[]`）。

## 3. 输入发现

1. 读 `case.json`；缺失则递归找 `case*.json`，仍失败就只靠目录扫描（记 `uncertainty[U-CASE]`）。
2. 递归扫描全部文件，按扩展名 + 内容判断类型；JSON 用"同时有文本键和 id 键"识别段落对象，XML 抓 JATS 的 `<article-id>/<article-title>/<sec><title>/<p id=>`。
3. 同一段正文只保留一份（去重哈希 + 文件优先级 `primary` > `secondary` > 其他 > `material.json` 汇总），写进 `changes`。
4. 来源划分用段落自带的 `doi/source_id`，其次正文里的 DOI，最后文件名；根 DOI/title/authors 只给第一篇。
5. 缺少的材料（PDF 无文本层、缺段号、缺样品标识）**明确列缺口**，不构造内容。

## 4. 输出契约

| 产物 | 内容 |
|-|-|
| `result.json` | 契约字段 + `case_id` + `status` + `sources` + `nodes` + `edges` + `claims` + `queries` + `merge` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime` + `artifacts` + `contract_coverage` |
| `graph_raw.json` | 节点、边、来源、段落索引（`source_id||paragraph_id -> {source_id, paragraph_id, text}`），供复核与增量续建 |
| `claims.json` | 全部 claim（实体出现、关系、跨篇对齐） |
| `queries.md` | 6 条查询的问题、状态、回答、证据、无法确定项 |
| `nodes.csv` / `edges.csv` | 可直接开表复核 |
| `verify_report.json` | 引文命中/失败计数、悬空边、查询状态 |

字段定义见 `references/schema.md`；`status` 取 `ok|partial|insufficient_evidence|input_error`。

## 5. 核心流程

1. 解析 → 去重 → 按来源分组，建立 `pid → 段落正文` 索引。
2. 实体：词表命中 + 大写短语 + 缩写/型号，段内不重叠、取最长，规范化后定 id（`n-<sha1[:8]>`）。
3. 关系：句内找 cue，左实体→右实体建边，带引文、段号、字符区间、条件。
4. 归一与对齐：同一规范化形式合并并记录依据；同缩写异全称不合并；跨篇只在字符串层面命中。
5. 落盘 `graph_raw.json` + partial `result.json`。
6. `verify.py`：逐字核对引文 → 派生 claim → 执行 Q1–Q6 → 导出 CSV/report → 契约终填。

## 6. 质量规则（评分点 → 字段/检查/产物）

| 评分点 | 落到哪 | 怎么核对 |
|-|-|-|
| 任务完成度 | `nodes`/`edges`/`queries`/`artifacts` | 两篇都非空、≥6 条查询、产物齐全 |
| 结果正确性 | 每条 `evidence.quote` + `location` | `verify_report.json.quotes_failed == 0`；实体 label 必是原文子串 |
| 关系方向与类型 | `edge.subject/predicate/object` + `cue` | 抽查 cue 左右实体顺序 |
| 结果完整性 | `schema.entity_types`、`graph_summary` | 实体类型覆盖、两篇边数均 >0 |
| 可核验性 | `location.kind=jats_paragraph_id`、`char_span`、`merge.auto_merged` | 随机抽 3 条回原文段落查找 |
| 质量增益 | `merge`、`non_merge_conflicts`、`queries[].undetermined` | 有无合并依据、有无"不合并"记录 |
| 效率增益 | 一条命令跑完；`runtime.elapsed` | 无需人工逐篇摘录 |
| 创新点 | 跨篇对齐节点 id 复用、证据绑定、增量 id 规则 | `incremental.id_policy` |
| 调用与易用 | `--help`、SKILL.md 示例 | 照抄命令即可跑 |
| 异常处理 | `errors`/`degradations`/`pending_human` | 坏 JSON、空输入仍出合法 partial |
| 文档与复用 | 本文件 + `references/*` + `graph_rules.json` | 换领域只改词表 |

## 7. 证据与定位规范

- 每条 claim 必备：`kind`、`evidence`（逐字 `quote`）、`source_id`、`location`、`condition`、`evidence_class`。
- 定位用组织方 JATS 段落 id + 段内字符区间；**不生成 PDF 页码**。
- 三类标注：`directly_read`（原文可直接读到）/ `inferred`（规则推出，规则在包内）/ `undetermined`（材料不足以判定）。
- 引文一律原样截取（≤400 字符），不改写、不补全、不翻译后当证据。

## 8. 冲突与人工确认

- 同时保留对立证据：两条边各自带段号与引文，不覆盖、不裁决。
- 同名不合并：缩写相同而全称不同 → 各自成节点，`merge.non_merge_conflicts` 附双方引文。
- 进 `pending_human`：PDF 文本层缺失、段号缺失导致定位退化、样品/数据集同一性判定、引文核验失败项。
- 指标只按来源分别列出，**不做跨篇算术合并**。

## 9. 预算与断点

- 单案例预算按平台给（本包默认软预算 780 秒）；解析、抽取、核验三阶段都可独立重跑。
- 每阶段结束即落盘：`graph_raw.json` → `result.json`(partial) → `result.json`(final)。中断后已有可用结果。
- 实体/边有上限（45/篇、120/篇），保证规模可控、运行时间稳定。

## 10. 异常降级分支

| 情形 | 行为 | 落点 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 继续递归发现 | `errors` + `degradations` |
| 输入为空/目录不存在 | 空图 partial，退出码 0 | `uncertainty[U-INPUT]` |
| 无任何可解析段落 | 空图，status=`input_error` | `pending_human[H-NOMAT]` |
| 单文件解析异常 | 仅跳过该文件 | `errors[stage=parse]` |
| PDF 无文本层 | 跳过并列出人工项 | `degradations[PDF_UNPARSED]` |
| 段落无组织方 id | 生成并标注合成 id | `degradations[PID_SYNTHETIC]` |
| 引文核验失败 | 计数、列样例、status 降 partial | `uncertainty[U-QUOTE]` |
| 查询无结果 | 保留查询、`status=no_result` | `queries[]` |
| 未捕获异常 | 保留 partial、退出码 0 | `errors[stage=fatal]` |

## 11. 自检清单

1. `--help` 退出码 0；
2. `result.json` 能被 `json.load` 解析，且 `case_id`、`status`、`output_contract` 齐全；
3. 契约每个键都在顶层出现（`contract_coverage.unmapped_nulled` 为空或已说明）；
4. `verify_report.json.quotes_failed == 0`；
5. `graph_summary.edges_per_paper` 两篇都 >0；
6. `queries` ≥3 条 `answered`，且 Q5 明确 `undetermined`；
7. 空输入、坏 JSON 两种情形仍产出合法 partial。

## 12. 最小调用示例（**示例，非正式案例结果**）

输入 `<input>/case.json`（示意）：

```json
{"case_id": "demo-001",
 "task_instruction": "把两篇论文做成带证据的图谱",
 "output_contract": {"nodes": null, "edges": null, "queries": null, "uncertainty": null}}
```

调用：

```bash
python3 -B scripts/build_graph.py --input ./input --output ./out --quiet
```

示意输出（**示例值，仅示形状，不代表任何真实案例**）：

```json
{"case_id": "demo-001", "status": "ok",
 "nodes": [{"id": "n-1a2b3c4d", "label": "SAC305", "type": "material", "type_basis": "cue_word",
            "sources": ["10.xxxx/demo.1"],
            "evidence": [{"quote": "we used SAC305 solder paste", "source_id": "10.xxxx/demo.1",
                          "location": {"kind": "jats_paragraph_id", "paragraph_id": "p-12",
                                       "section": "Methods", "char_span": [0, 28]},
                          "evidence_class": "directly_read"}]}],
 "queries": [{"query_id": "Q5", "kind": "sameness_check", "executed": true, "status": "undetermined",
              "answer": "无法确定。"}],
 "contract_coverage": {"filled": {"nodes": "nodes", "edges": "edges", "queries": "queries"}, "unmapped_nulled": []}}
```

## 13. 文件清单与版本

```
SKILL.md                      本文件（入口，14 节）
scripts/build_graph.py        解析 + 抽取 + 归一 + 图导出（纯标准库，支持 --help）
scripts/verify.py             引文核验 + claim 派生 + 6 查询 + CSV + 契约终填（纯标准库，支持 --help）
references/graph_rules.json   词表 / cue 正则 / 停用词 / 块标题 / 策略开关
references/schema.md          节点、边、claim、location、result.json 字段定义与契约回填规则（第 6 节）
references/method.md          方法、异常分支、自查、适用边界、维护
```

版本 v1.0.0；Python ≥3.9；依赖：标准库（`argparse/json/re/hashlib/csv/zipfile/subprocess/pathlib`）；无网络、无模型调用。

## 14. 维护

- 换领域：只改 `references/graph_rules.json` 的 `lexicon` 与 `cues`，代码不动。
- 改字段：`references/schema.md` 与两个脚本同步改；字段名即契约。
- 回归：改完跑第 11 节 7 步；引用核验失败率必须回到 0 才可发布。
- 已知限制：关系抽取高精度低召回（只有含 cue 的句子成边）；实体类型是启发式；不输出 PDF 页码。
