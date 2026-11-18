---
name: citation-tracer
description: Trace a literature set from seed papers along citation and association edges, fully offline. Accepts seeds from case.json, task.md or a seed PDF (DOI / first-page title), then builds direction-aware backward (references) and forward (citing works) expansion, discovers parallel work by bibliographic coupling and co-citation, merges preprint / conference / journal / erratum versions into one identity, and emits a ranked, deduplicated candidate list with per-item screening reasons, a citation-edge table, hop-by-hop paths, coverage-and-gap report, query log, in-run baseline delta and self-check. Use when a case supplies seed papers and retained citation records (case.json, task.md, artifacts/records.jsonl, citations.jsonl, reference_graph.json, import_state.json, cached Crossref / EuropePMC / OpenAlex / Semantic Scholar JSON, seed PDFs) and asks for citation tracking, related-work discovery or deduplication rather than plain keyword search.
version: 1.3.0
---

# citation-tracer

## 1. 用途与边界

**用途**：以种子论文为起点，沿引用与关联关系扩展出一个可直接进综述的文献集，并为每条结果保留来路。

三个通道，全部方向感知：

| 通道 | 含义 | 数据依据 |
|-|-|-|
| backward | 种子引用的文献（方法与数据出处、奠基工作） | 种子记录里的参考文献表，或反查 `dst = 种子` 的边 |
| forward | 引用种子的文献（后续改进、批评、复用） | 其他记录的参考文献表里出现种子，或种子记录里的施引列表 |
| parallel | 不直接引用种子但同属一条方法脉络的平行工作 | 与种子共享 ≥2 条参考文献（文献耦合），或被同一批工作共同施引（共被引） |

**边界**：本 Skill 不做普通关键词检索、不做全文理解、不做在线抓取。它只消费本案保留的引文记录，因此**不会**声明任何"最新进展""全局覆盖"或"该文献不存在"。

**方向读法（重要）**：`channel` 与 `citation_relation.direction` 记的是**到达该候选的最后一跳方向**，不是"相对种子的直接关系"。只有 `hop=1` 才能读作"直接引用/被种子引用"；`hop≥2` 的 `forward` 表示经中间邻居的施引边到达，该候选与种子可能并无直接引用关系，此时须结合 `related_evidence.basis` 与 `path` 判断它究竟是后续改进还是平行工作。

## 2. 运行契约

- 入口：`python3 -B scripts/main.py --input <case_dir> --output <out_dir>`；默认 `/input` → `/app/output`。
- 先写 partial `result.json`，再跑分析，最后**无条件**覆盖为终稿；任何异常都被捕获写入 `errors`，**退出码恒为 0**。
- 原样回填输入 `output_contract` 的全部字段（键名不改、缺值 `null`/`[]`、未知字段保留），`case_id` 原样透传。
- 只读 `--input`，只写 `--output`；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位）。
- 预算：单次运行 760 秒软上限（`DL`），触及后停止扩展并按现有结果 finalize。

## 3. 输入发现（语义识别，不假设键名）

1. `case.json`（或 `input.json` / `task.json` / 任意 `case*.json`）：取 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`。键名大小写与下划线差异由 `getf()` 归一化。
2. 递归扫描 `--input` 下所有文件：`.json/.jsonl/.ndjson` 结构化解析；`.csv/.tsv` 按表头映射（`citing*`→施引侧、`cited*`→被引侧、`doi/id`→DOI、`title`→题名），两侧 DOI 齐全时同时产出两侧记录与一条 `cites` 边；`.yaml/.yml/.txt/.bib/.ris/.xml` 仅做 DOI 字面抽取（不猜题名年份，详见 `references/sources.md` §5.1）；`.pdf` 用 `pdftotext`（若存在）抽文本，提取 DOI 与首页题名作为**种子线索**，失败则降级并写入 `degradations`（见 §10）。文件名含 `import/sync/state` 的对象另作增量导入状态登记，写入 `coverage.import_states`。
3. 记录识别：任何对象只要有外部标识（DOI/PMID/OpenAlex/arXiv/S2 id）或规范标题，即视为文献记录；连线由 `reference(s)`/`citations`/`cited_by`/`bibliography`/`referenced_works` 等字段或显式 `citing→cited` 对提取。
4. 种子识别：语义扫描含 `seed/start_paper/target_paper/focal/root_paper` 的键；再补 `task_instruction` 里的 DOI；解析顺序 DOI → PMID → OpenAlex → 标题精确 → 标题模糊（≥0.90）。都没有时退化为"保留图中连接度最高的作品"，并把 `seed_inferred` 写进 `uncertainty` 与 `pending_human`。

## 4. 输出契约

固定主产物（写在 `--output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 全部结构化结果 + 契约字段 + `status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`/`checks` |
| `candidates.csv` | 候选清单（id、题名、作者、年、DOI、来源库、命中方式、分数、置信度、定位） |
| `query_log.json` | 逐条查询记录：`db / raw / kind / hits / retained / status / retrieved_at` |

`result.json` 关键块：`seeds`、`candidates`、`edges`、`screening`、`coverage`、`metrics`、`baseline`、`queries`、`sources`、`missing`、`checks`。字段字典见 `references/schema.md`。

`candidates.csv` 与 `query_log.json` 是主产物的可复用导出；`screening` 另在 result.json 内逐条给出 `include` / `criteria` / `reason`（搜索赛道要求的"保留/排除理由"），`missing` 列出材料无法提供的项及其补数动作。

每条候选必带：`source_locator{file,json_pointer,retrieved_at}`、`citation_relation{direction,edge_ids,hop_count}`、`relevance_reason`、`relevance_breakdown`、`metadata_confidence`、`evidence`、`path`（从种子逐跳到该文献的链）。

## 5. 核心流程

1. 扫描输入 → 记录与原始边；每个文件写一条 `retained_cache_scan` 查询日志，PDF 另写 `local_pdf` 的 `pdf_seed_scan`。
2. 身份合并（union-find）：DOI/PMID/arXiv/OpenAlex/S2 精确键 → 规范化标题精确 → 标题模糊（≥0.93 且年份差 ≤1 且共享作者）。同年同名但年份差 >3 判为同名歧义，打 `homonym_suspect`，不合并。
3. 种子解析 → 有向 BFS（`--depth` 默认 2，单节点单方向 30 邻居，候选上限 3×cap）。
4. 关联发现：耦合（与种子共享 ≥2 参考文献）与共被引（被同一批保留工作施引）。
5. 排序：`0.40*relation + 0.20*proximity + 0.15*topical + 0.15*centrality + 0.10*recency`，分项全部写入 `relevance_breakdown`。
6. 覆盖与缺口、基线对照、自检、落盘。

方法细节、停止判据与基线协议见 `references/workflow.md`。

## 6. 评分要点 → 字段/检查/产物

| 评分点 | 本 Skill 的对应物 |
|-|-|
| 任务完成度 | `seeds` → `candidates`（backward/forward/parallel 三通道）+ `edges` |
| 结果正确性 | 边表 `citing cites cited` 单向语义；`citation_relation.direction` 逐条标注；`metadata_confidence` 区分全字段/仅标识；`identity_merges` 计数 + `homonym_suspect` |
| 结果完整性 | `coverage.gaps`（无前向引用的种子、无法解析的边、仅标识候选、撤稿/更正/预印本标记） |
| 结果可核验性 | 每条候选 `source_locator{file,json_pointer,retrieved_at}` + `edge_ids` + `query_log` |
| 质量增益 | `metrics` 与 `baseline.delta`（去重率、DOI 率、方向标注率、定位率、关联依据率） |
| 效率增益 | `counts`（扫描文件数、原始记录数、合并后作品数、边数、查询数）+ `runtime.duration_s` |
| 增益可验证性 | `baseline.protocol` + 同一脚本重跑即复现（`checks` 随每次运行重算） |
| 新增能力 | 跨库身份对齐（`identity_merges`）、方向感知扩展（`direction`）、可解释来路（`hop`/`via_work`/`edge_ids`） |
| 方法改进 | 去重键分层、路径排序分项、`coverage` 停止与缺口判据 |
| 创新证据 | `baseline.delta` + `coverage.seed_neighbourhood_coverage`（保留图内的覆盖，而不是自造 Recall） |
| 调用与易用性 | `--help` 即用，默认路径零配置 |
| 运行稳定性 | 空输入 / 坏 JSON / 无种子 / 无引文均返回合法 `result.json`，退出码 0（§10 已验证） |
| 异常处理 | §10 分支表；`uncertainty` + `pending_human` + `degradations` 三分 |
| 文档完整性 | 本文件 + `references/{schema,sources,workflow}.md` |
| 资源可复用性 | `candidates.csv`、`query_log.json`、边表结构、去重规则可被他人直接消费 |

## 7. 证据与定位规范

- 定位三元组：`file`（相对 `--input`）+ `json_pointer`（记录在文件中的路径）+ `retrieved_at`（记录自带字段优先，否则文件 mtime，并在 `runtime` 标注）。
- 引用边：`{edge_id, citing, cited, relation:"cites", source_file, evidence[{json_pointer, field, item_index, retrieved_at}]}`。同一对节点最多保留 5 条证据。
- `url` 由 DOI 推导（`https://doi.org/<doi>`），**不是**抓取结果；只对有 DOI 的候选生成。
- 不写任何无法定位的数值。`coverage.recall_estimate` 恒为 `null`，并写明"保留样本上不可计算"。

## 8. 冲突与人工确认

| 情形 | 处置 |
|-|-|
| 跨库字段冲突（题名/年份/期刊不一致） | 保留全部来源于 `provenance`，主值取置信度最高者；分歧进入 `coverage.gaps` 或 `flags` |
| 同名不同文 | 年份差 >3 不合并，双方打 `homonym_suspect` |
| 撤稿 / 更正 / 预印本 | `flags: retraction_marker / correction_marker / preprint / conference_version`，并在 gaps 提示"引用前需核实" |
| 种子无前向引用 | `uncertainty.seed_without_forward_citations` + 一条 `planned_query(status=not_executed)` |
| 种子无参考文献表 | `uncertainty.seed_without_reference_list` |
| 种子无法判定 | 退化 + `seed_inferred` + `pending_human`（请人工确认种子） |

## 9. 预算与断点

- 760s 软上限：扫描阶段剩 60s 即停扫；扩展循环内持续检查 `DL`。
- 候选上限 `--max-candidates`（默认 60，可被 case 的 `max_k/top_k/k` 覆盖）；边表输出上限 4000 行。
- 记录数上限 30000（`citelib.MAX_RAW`），超出后不再新增。
- partial `result.json` 在任何分析之前落盘，中断也有合法产物。

## 10. 异常降级分支表

| 触发 | 行为 | 字段 |
|-|-|-|
| 输入目录不存在 | 直接返回，保留 partial | `status=input_error`，`pending_human` |
| `case.json` 缺失/坏 JSON | 继续扫描其他文件；无契约则只输出规范 schema | `degradations`，`contract_missing` |
| JSONL 部分行损坏 | 跳过坏行，计数量 | `degradations[{what,count,fallback}]` |
| 无任何文献记录 | 停止，不补造 | `status=insufficient_evidence` |
| 无种子 | 退化推断或停止 | `uncertainty.seed_inferred` / `insufficient_evidence` |
| 种子已解析但无边可扩展 | 候选为空 | `status=insufficient_evidence`，`empty_candidate_set` |
| 引用边无法落库到记录 | 跳过并计数 | `counts.edges_unresolved`，写入 gaps |
| PDF 可抽文本 | 抽出 DOI / 首页题名作种子线索，写入 `sources{kind:"pdf",doi_candidates}` 与 `pdf_seed_scan` 日志 | — |
| PDF 不可抽文本 | 只登记来源，种子退回 case.json | `degradations`：`pdf metadata only` |
| 增量导入未完成 | 读 `import/sync/state` 类对象 | `coverage.import_states` + `uncertainty.incremental_import_pending` |
| 权限/限流/离线补检 | 不发起、不假装 | `planned_query(status=not_executed)` |

## 11. 自检清单（每次运行自动执行，写入 `checks`）

固定七项：`contract_complete` → `case_id_present` → `locator_present` → `doi_well_formed` → `direction_labeled` → `no_fabricated_recall` → `screening_complete`；全部通过时 `self_check_pass = true`。任一不通过时看 `contract_missing` 或该项的 `detail`。`checks` 在任何退出路径上都会写出。

人工复核三条：① 随机抽 3 条候选，按 `source_locator` 打开原文件确认题名与 DOI；② 抽 3 条边，确认 `citing` 确实引用了 `cited`；③ 看 `coverage.gaps` 是否覆盖了你已知的缺口。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py --input ./demo_case --output ./demo_out
```

`demo_case/case.json`（示意）：

```json
{"case_id": "demo-min",
 "task_instruction": "Trace improvements of 10.1000/seed.a",
 "organizer_supplied_scope": {"seeds": ["10.1000/seed.a"], "max_k": 10, "depth": 2},
 "output_contract": {"candidates": "ranked list", "queries": "query log", "coverage": "gaps"}}
```

示意输出（**示例，非正式案例结果**，来自本仓库自建的 4 条记录玩具输入）：

```
status: ok | seeds: 1 | candidates: 5 | edges: 7 | self_check_pass: True
c001 forward hop1 0.79  Revisiting Graph Neural Retrieval with Contrastive Training
c003 forward hop2 0.64  Sparse Retrieval without Graphs        basis: 2 shared refs
c004 backward hop1 0.63 Early Graph Retrieval Baseline         basis: co-cited by 1
```

## 13. 文件清单与版本

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本文件：契约、流程、异常、自检 |
| `scripts/main.py` | 入口：输入发现、种子、扩展、排序、覆盖、基线、落盘、自检 |
| `scripts/citelib.py` | 记录/边抽取、身份合并、邻接、打分基元、候选装配、自检 |
| `references/schema.md` | `result.json` 字段字典、边表结构、去重规则、状态取值 |
| `references/sources.md` | Crossref / EuropePMC / OpenAlex / Semantic Scholar 字段映射与失效处理 |
| `references/workflow.md` | 扩展策略、停止判据、评分公式、基线协议、复核流程 |

版本 1.3.0（1.3.0 起支持 `.csv/.tsv` 定界表与 `.yaml/.txt/.xml` DOI 抽取；1.2.0 为纯 JSON 输入版）。依赖：Python 3.8+ 标准库（`json/re/csv/difflib/hashlib/unicodedata/datetime/pathlib/shutil/subprocess`），无第三方包，无网络。PDF 文本优先调用系统 `pdftotext`（`shutil.which` 探测，缺失时退回原始字节扫描并记录 `runtime.pdf_tool`）。无需安装步骤。

## 14. 维护说明

- 新增数据源：只改 `citelib.norm_*` / `ids_of` / `keys_of_item`，不要动主流程；改完跑 §11 三条人工复核。
- 调整合并激进度：`citelib.build_index` 里的模糊阈值 0.93 与长度差 0.35；放宽会提高合并率也会提高错并率，改动需在 `references/schema.md` 记录。
- 已知限制：PDF 只取 DOI/首页题名作种子线索，不做正文理解；标题差异大于 7% 的预印本/期刊版不会被合并；`Recall@k` 需要金标准，本 Skill 不产出该数值；`.csv/.tsv` 只取 DOI/题名/边，年份、期刊、作者列不读；`.yaml/.txt/.xml` 只取 DOI 字面串，不解析结构。
