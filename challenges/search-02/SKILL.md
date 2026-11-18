---
name: research-question-retrieval
description: >-
  科研问题驱动的文献检索 Skill：把复杂科研问题拆成可检索子问题（对象/机制/方法/比较/局限），
  规划分波查询与术语扩展，在案例提供的文献快照上完成检索、去重、全量筛选与排序，输出带
  query/source/retrieved_at 定位的候选集、查询与筛选日志、覆盖与遗漏说明、冲突与异常记录。
  适用于学术文献检索、证据集构建、检索过程可复现审计；不做全文精读、翻译或写作润色。
version: 1.0.0
---

# research-question-retrieval（search-02）

问题驱动检索：先拆问题，再规划查询，最后交付证据集与可复核日志。

## 1. 用途与适用边界

**做**：把一个包含研究对象、机制、方法、时间范围、比较关系的科研问题，拆成可检索子问题；
按波次规划查询；做术语/缩写/跨语言扩展；在给定文献快照上检索、去重、全量筛选、排序；输出
候选集 + 可复核日志 + 覆盖与遗漏说明。

**不做**：单篇精读、全文翻译、写作润色、开放式科研问答；不联网、不查真实数据库、不生成
不存在的文献/DOI/引用；不声称"最新进展"（只反映输入快照）。

**适用条件**：`/input` 下存在任务说明与文献材料（JSON/JSONL/CSV 记录，或含题录的 case 文件）。
材料只有 PDF 正文而无结构化题录时，本 Skill 只能做问题拆解与查询规划，候选集应如实为空。

## 2. 运行契约

```
python3 -B scripts/main.py [--input /input] [--output /app/output]
                          [--max-queries 24] [--max-k 0] [--self-check] [--version]
```

- 只读 `/input`，只写 `/app/output`；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`）。
- 仅 Python 标准库；无网络；无模型调用（`model_requests: 0`）。
- **先落盘**：解析 case 后立刻写 partial `result.json`，随后无条件 finalize 覆盖。
- 退出码**恒为 0**；任何异常进 `errors[]`，不中断其它产物。
- `result.json` 原子写（临时文件 + `os.replace`）。

## 3. 输入发现（语义识别，不假设键名）

1. `case.json` → `input/case.json` → `case*.json`（递归兜底）。解析失败不致命，记 `errors.stage=load_case`。
2. 研究问题取值顺序：`task_instruction` / `research_question` / `question` / `task` / `instruction`
   （>10 字符）；否则 `organizer_supplied_scope` 等块内的 `research_question|question|topic|objective`；
   否则 `task.md` 中 `# Research question` / `# 研究问题` 标题下正文。来源记入 `sources[].question_field`。
3. 检索范围从 `organizer_supplied_scope` / `scope` / `constraints` / `search_scope` 读取：
   `years|year_range`、`max_k|top_k|max_results`、`include`、`exclude`、`dbs|databases`；
   年份缺失时从问题文本里的 `2018-2024` 形式回退。全部记入 `scope_used.inferred_from`。
4. 文献记录：递归扫描 `/input/**` 的 `.json`/`.jsonl`/`.csv`（跳过文件名含 case/config/schema/contract
   者与隐藏文件）；凡含 title 或 doi 且无 `results` 列表的对象即视为一条记录；CSV 按行读。
   别名表见 `retrieval.py` 的 `AL`（title/authors/year/venue/doi/url/abstract/keywords/source_db/id，含中文）。
5. 材料未给的对象（如 citation graph、gold labels、实时数据库）**明确列缺口**，不构造。

## 4. 输出契约

`result.json` 原样回填输入 `output_contract` 的**全部**键（键名不改，缺值 `null`/`[]`），
并在 `output_contract_echo` 保留原对象、`contract_report.mapped_fields` 记录哪些键拿到真实数据。
`CMAP` 把契约键名（中英）语义映射到本 Skill 字段（candidates / queries / screening / coverage /
metrics / conflicts / uncertainty / sources / stopping / missing / pending_human 等）。

固定字段：`case_id`、`skill`、`status`、`question`、`sub_questions`、`candidates`、`queries`、
`screening`、`coverage`、`citations`、`conflicts`、`missing`、`metrics`、`baseline`、`stopping`、
`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`logs`、
`output_contract_echo`、`runtime`、`scope_used`、`contract_report`。
逐字段类型见 `references/output_schema.md`。

每次运行还写：`candidates.csv`、`query_log.json`、`query_log.jsonl`、`screening_log.csv`；
`--self-check` 追加 `selfcheck.json`。单文件写失败只记 `errors`，不影响其它产物。

## 5. 核心流程

1. **拆解**：从问题抽取 facets（core/method/mechanism/outcome/comparison/gap，词表 `references/lexicon.md`），
   抽 anchors（引号内短语、专名短语）。生成 ≤6 个子问题，每个含 `groups[]`（anchor 组 + facet 组）
   与 `wave`：core=1，method/mechanism=2，outcome/comparison/gap=3。中文问题且有 anchors 时加跨语言变体。
2. **规划**：按 wave 升序执行，前置波次的命中构成后续波次的证据基础；同一波次内并行（同一索引）。
3. **检索**：BM25（字段权重 title 3.0 / keywords 2.0 / abstract 1.0 / venue 0.5 / authors 0.3），
   组内取最佳词、组间求和；每个组必须命中（`ok`），anchor 组需满足 `min_hits`。
4. **去重**：并查集合并——同 DOI、同规范标题、标题词 Jaccard >0.9 且年份差 ≤1。保留全部
   `provenance` 成员记录，`flags` 标 `duplicate_export_merged`。
5. **筛选**：年窗、排除词、非研究条目（erratum/retraction/comment/editorial）、包含词（若给定则必需命中）；
   标记 `no_abstract`/`no_doi`/`year_unknown`。决策 `include` / `exclude` / `defer`
   （`defer` = 通过范围筛选但无子问题命中，进 `missing[]` 与 `pending_human`）。
6. **排序**：`0.55*BM25归一 + 0.30*命中facet组数 + 0.15*时间新近度`，截断至 `max_k`。
7. **收敛**：全部子问题有 ≥1 条 included 候选、某波次无新增证据、或达到查询预算即停；
   `stopping` 记录 waves 统计、`reason`、预算用量。

## 6. 质量规则（rubric → 字段 / 检查 / 产物）

| 评分维度 | 本 Skill 的对应实现 | 字段/产物 |
|-|-|-|
| 任务完成度 | 问题→子问题→查询→证据链完整；每子问题标注 covered/uncovered | `sub_questions[]`、`coverage.per_sub_question` |
| 结果正确性 | 元数据逐字取自输入记录，不生成；可查 DOI 良构率、片段命中率 | `candidates[]`、`metrics.doi_wellformed_rate`、`metrics.snippet_rate` |
| 结果完整性 | 记录级全量筛选（含排除理由），缺口显式列出 | `screening.decisions[]`、`coverage.gaps[]`、`missing[]` |
| 结果可核验性 | 每条候选带 `query_id`+`source_db`+`retrieved_at`+`evidence_locator`，可按 `query_log` 复现 | `candidates[]`、`query_log.json/.jsonl`、`screening_log.csv` |
| 使用增益 | 与同快照单轮扁平查询基线对照（同 max_k） | `baseline{}`、`metrics.comparison_vs_baseline{}` |
| 效率增益 | 记录查询数、空查询数、去重合并数 | `metrics.n_queries`、`n_queries_empty`、`n_dup_merged` |
| 创新增益 | 分波规划、术语/跨语言扩展、DOI+标题去重、facet 覆盖判据、停止规则 | `sub_questions[].wave`、`queries[].expanded_terms`、`stopping` |
| 可靠体验 | 空/坏输入仍出合法 partial；异常分支显式记录 | `errors[]`、`degradations[]`、`status` |
| 生态贡献 | `SKILL.md` + `references/`（schema、方法清单、词表）可独立复用 | 本包文件 |

## 7. 证据与定位规范

- 每条候选的 `evidence_snippet` 逐字截取自该记录的 abstract 句子（无 abstract 时取 title），
  `evidence_locator` 标 `abstract:sentN` 或 `title`；`--self-check` 会校验片段确实出现在源记录中。
- `retrieved_at` 为该记录胜出查询的 UTC 时间戳，与 `query_log[].retrieved_at` 一致。
- `metadata_confidence`：有 DOI+authors+year → `high`，否则 `medium`；**缺失字段留 `null`，绝不补造**。
- 无 citation 图输入时 `citations.graph_available=false`、`edges=[]`，不虚构引文关系。

## 8. 冲突与人工确认

`conflicts[]` 用词表极性启发式（pos/neg）检测同一主题下的相反结论，要求标题/摘要词重叠 ≥2 才配对，
置信度标为 `low (lexical polarity heuristic)`，结论一律 `unresolved`，并写入 `pending_human`
（动作：人工读两篇原文判定适用条件）。术语严重歧义、多义缩写、证据不足同样进 `pending_human`。

## 9. 预算与断点

- 参数上限：`--max-queries`（默认 24，仅执行前 N 个子问题查询）、`--max-k`（默认取 scope，缺省 20）、
  记录上限 `MAXR=4000`、递归深度 ≤10。
- 平台预算 64 请求 / 900 s / 16384 tokens：本 Skill 不发起模型或网络请求，耗时由输入规模决定。
- partial `result.json` 在解析 case 后立即落盘，任何后续中断都留下合法文件。

## 10. 异常降级分支表

| 情况 | 处置 | 记录位置 |
|-|-|-|
| `/input` 不存在或为空 | 仍写合法 result.json，`status=insufficient_evidence` | `errors[].stage=load_case`、`logs[]` |
| case.json 坏 JSON / 无 case 文件 | 继续扫描材料，question 走 task.md 兜底 | `errors[]`、`uncertainty[].topic=research_question` |
| 无文献记录 / 无候选 | `status=insufficient_evidence`，候选为空不填充 | `coverage.n_records_in_snapshot` |
| 子问题查询 0 命中 | 该查询 `status=empty`，子问题 `uncovered`，进 `coverage.gaps` | `queries[].status`、`coverage.gaps[]` |
| 记录缺 DOI / 无摘要 / 无年份 | 打 flag、降 confidence、记 degradation，不补值 | `candidates[].flags`、`degradations[]` |
| 词表文件缺失/损坏 | 回退内置最小 facet 表 | `degradations[]`、`skill.lexicon_loaded` |
| 输出目录不可写 | 回退 `$TMPDIR/search02-out` | `runtime.output_dir` |
| 单个产物写失败 | 捕获并在 finalize 前重写 result.json | `errors[].stage=write_artifacts` |
| 未捕获异常 | 保留已有 partial，追加 `errors.stage=fatal`，退出码 0 | `errors[]`、`runtime` |
| 无 gold labels | 不计算 P/R/nDCG，只用结构化覆盖与基线对照 | `uncertainty[].topic=gold_labels` |
| 接口限流/权限不足 | 本 Skill 离线运行不触发；如上游注入此类错误，按 errors 记录并保持候选为空 | `errors[]` |

## 11. 自检清单

`--self-check` 自动校验：契约键是否全部存在、候选是否缺 title/source_db/retrieved_at/query_id/
relevance_reason/evidence_snippet、`query_id` 是否出现在 `queries[]`、DOI 是否良构、
evidence_snippet 是否真在源记录文本中；结果写 `selfcheck.json` 并打印 `pass|warn`。

人工复核顺序：`result.json.status` → `metrics.sub_question_coverage` → `coverage.gaps` →
`candidates[].relevance_reason` 与 `query_log` → `errors/degradations/uncertainty`。

## 12. 最小调用示例（示例，非正式案例结果）

输入 `/input/case.json`（合成示意，仅演示接口）：

```json
{"case_id": "SYNTHETIC-DEMO-001",
 "task_instruction": "Assess whether single-cell RNA sequencing resolves tumor heterogeneity better than bulk RNA sequencing in glioma, 2018-2024.",
 "output_contract": {"candidates": {"type": "array"}, "queries": {"type": "array"},
                     "screening": {"type": "object"}, "coverage": {"type": "object"},
                     "metrics": {"type": "object"}, "uncertainty": {"type": "array"},
                     "status": {"type": "string"}}}
```

加一个含 8 条合成题录的 `artifacts/records.jsonl`，运行：

```bash
python3 -B scripts/main.py --input /input --output /app/output --self-check
```

上述合成输入上的实测示意输出（示例，非正式案例结果）：`status=partial`、`case_id=SYNTHETIC-DEMO-001`、
5 个子问题（core/method/mechanism 覆盖 3，outcome/comparison 未覆盖→`coverage.gaps`）、
5 条候选、5 条查询、8 条记录全量筛选（include 6 / exclude 1 / defer 1）、
基线对照 `in_scope_share=0.833`、`queries{baseline:1, skill:5}`、`duplicate_exports{baseline:1, skill:0}`、
`selfcheck=pass`。真实案例数值由平台运行产生，本文件不提供任何正式案例答案。

## 13. 文件清单与版本

| 文件 | 大小 | 作用 |
|-|-|-|
| `SKILL.md` | 本文件 | 入口说明、契约与流程 |
| `scripts/main.py` | ~20 KB | 入口：解析、编排、组装 result.json 与 CSV/JSONL、自检、异常兜底 |
| `scripts/retrieval.py` | ~20 KB | 引擎：扫描、规范化、拆解、BM25、去重、筛选、基线 |
| `references/lexicon.md` | ~3 KB | facet 词表、同义词、极性词；纯文本，可自由编辑 |
| `references/output_schema.md` | ~7 KB | 输出字段逐个解释 + 异常分支 |
| `references/method_and_checklist.md` | ~10 KB | 方法说明、rubric 映射、自查清单、局限 |

版本 `1.0.0`；Python ≥3.8（仅标准库，无第三方依赖，无需安装）。

## 14. 维护说明

- 换领域只改 `references/lexicon.md`（facet 线索、同义词、极性词），不改代码；改完跑 `--self-check` 回归。
- 新增输入格式：在 `retrieval.py` 的 `AL` 加字段别名，或在 `scan()` 加扩展名分支。
- 调整排序：`main.py` 的 `cand_row()` 里 0.55/0.30/0.15 权重；调整后比较 `metrics.comparison_vs_baseline`。
- 已知局限：快照检索无法给出真实召回率（无 gold labels）；极性冲突检测是词面启发式；
  仅消费结构化题录，不解析 PDF 正文。
