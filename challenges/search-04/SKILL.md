---
name: citation-tracer
description: 以种子论文为起点，沿引用与关联关系执行方向感知的文献追踪、关联发现、身份合并与去重排序，输出可复核候选集、引用边表、路径与缺口。适用输入为 /input/case.json、/input/task.md 以及题面提供的 PDF/DOCX/CSV/JSON/JSONL/XML/BIB/RIS 等材料；不替代普通关键词检索，不做未授权的在线抓取。脚本只是工具，最终交付物由 Harness Agent 亲自读材料、推导、撰写/制作并核验。
version: 1.4.0
---

# citation-tracer

## 0. 总体要求与完整性优先（最高优先级）

本 Skill 被安装在 `/skills/weekly-skill`。官方 DeepSeek Harness 会在 3 个固定原始案例上真实运行。此前同类提交常见问题是：交付物不完整、像脚本模板、缺少真实核验。为避免出现“did not find a complete, genuinely-derived solution”，本版执行铁律如下：

1. **脚本只是工具，不是成品**。`scripts/main.py`、`scripts/citelib.py` 负责批量解析、合并、扩展、打分和落盘；但最终提交的 `result.json`、关键论断、完整性核验、材料真实性判断必须由你（Harness Agent）亲自读原文件、推导、撰写或增强。禁止把脚本骨架、空模板、占位符直接当交付物。
2. **先跑基线，再增强**。进入任务后，第一件事是用主脚本产出全套基线交付物：`/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/query_log.json`，以及契约要求的所有字段。基线产出前不要开始大规模人工分析。
3. **保留全部基线产物**。后续只能在此基线上增强、补字段、写核验标记；不得删除、清空或遗漏任何基线与契约字段。若你不确定是否该改某字段，保留原值，并在 `agent_review` 中标注 `reviewed_by_agent`。
4. **完整性自检（提交前必做）**。逐项核对「输入 `output_contract` 字段 × 磁盘文件 × `result.json` 键」三者一致；缺任何一项先补齐再收尾。`status=partial` 时必须列出缺失项和限制。
5. **可核验增强**。在基线之上，由 Agent 亲自核验关键论断、数字、引用方向和来源一致性，把核验结果写进 `result.json` 的 `agent_review`：`verified` / `pending_human` / `conflicts`。这条是“genuinely-derived”的证据。

## 1. 用途与边界

**用途**：以种子论文为起点，沿引用与关联关系扩展出一个可直接进综述的文献集，并为每条结果保留来源、依据和路径。

三个通道，全部方向感知：

| 通道 | 含义 | 数据依据 |
|-|-|-|
| backward | 种子引用的文献（方法与数据出处、奠基工作） | 种子记录里的参考文献表，或反查 `dst = 种子` 的边 |
| forward | 引用种子的文献（后续改进、批评、复用） | 其他记录的参考文献表里出现种子，或种子记录里的施引列表 |
| parallel | 不直接引用种子但同属一条方法脉络的平行工作 | 与种子共享 ≥2 条参考文献（文献耦合），或被同一批工作共同施引（共被引） |

**边界**：本 Skill 不做普通关键词检索、不做全文理解、不做在线抓取。它消费案例保留的引文记录与题面材料，因此**不会**声明“最新进展”“全局覆盖”或“该文献不存在”。

**方向读法（重要）**：`channel` 与 `citation_relation.direction` 记的是**到达该候选的最后一跳方向**，不是“相对种子的直接关系”。只有 `hop=1` 才能读作“直接引用/被种子引用”；`hop≥2` 的 `forward` 表示经中间邻居的施引边到达，该候选与种子可能并无直接引用关系，此时须结合 `related_evidence.basis` 与 `path` 判断它究竟是后续改进还是平行工作。

## 2. 运行契约

- 工作目录：`/app/work`；最终产物目录：`/app/output`；原始输入目录：`/input`。
- 入口命令：`python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output`。
- 脚本要首先写 partial `result.json`，再执行分析，最后**无条件**覆盖为终稿；任何异常都被捕获写入 `errors`，**退出码恒为 0**。
- 原样回填输入 `output_contract` 的全部字段（键名不改、缺值 `null`/`[]`、未知字段保留），`case_id` 原样透传。
- 只读 `--input`，只写 `--output`；不联网；不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位）。
- 预算：整个 Harness 运行不超过 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本调用不计为模型请求，但脚本运行时间计入 900 秒。Agent 务必避免无意义重复请求。
- 最终 `result.json` 必须包含原 `output_contract` 全部字段和 `case_id`；若可编辑 Office/幻灯片/图形产物被生成，必须额外给出真实渲染的 PDF/PNG 预览。

## 3. 执行流程（Harness Agent 必做）

以下步骤按顺序执行；每一步写完“输入 / 动作 / 输出 / 失败分支”，Agent 不得跳过基线步骤。

### 步骤 1：盘点输入

**输入**：`/input/case.json`、`/input/task.md`、题面规定的材料（PDF/DOCX/CSV/图片等）。  
**动作**：  
1. 列出 `/input` 下所有文件，识别材料类型与扩展名。  
2. 读 `case.json`，提取 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`；读 `task.md` 了解评分面孔与本题重点。  
3. 如果 `case.json` 不存在或坏 JSON，记录 `contract_missing`，继续扫描其他文件构建候选输入。  
**输出**：输入文件清单、契约字段清单、种子线索清单、待解析材料清单。  
**失败分支**：输入目录不存在 → 直接生成合法 `result.json`，`status=input_error`，`pending_human` 标记，退出码 0。

### 步骤 2：运行基线脚本，产出全套基线

**输入**：`/input`。  
**动作**：  
```bash
mkdir -p /app/work /app/output
python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output
```  
**输出**：`/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/query_log.json`；若脚本检测到可渲染的额外产物，也一并落盘。  
**失败分支**：脚本异常也会返回退出码 0；检查 `/app/output/result.json` 是否存在，若不存在则按 §12 手动降级生成合法 `result.json`，然后继续。

**关键要求**：此步骤产出的所有文件、所有 `result.json` 键都是基线。后续步骤只能增强，不得删除。

### 步骤 3：用工具真实解析材料

**输入**：`/input` 下所有原始材料。  
**动作**：  
1. 对 PDF：优先调用系统可用的 `pdftotext` / `pdf-text-tool` / `mutool` 抽取文本；没有可用工具则退回二进制字节扫描提取 DOI/首页题名。  
2. 对结构化文件：`scripts/main.py` 已扫描 JSON/JSONL/NDJSON/CSV/TSV/YAML/TXT/BIB/RIS/XML；你须抽查 2-3 个文件，确认脚本抽取的记录与边是否与原材料一致。  
3. 对 DOCX/XLSX/PPTX：若题面要求解析，使用系统可用转换工具（如 `libreoffice --headless --convert-to` 或 `pandoc`）抽取文本；不能解析时登记为 `unsupported_format`。  
4. **真实依据**：不得依据文件名、领域标签或案例标题猜测内容。所有结论必须回指材料中的实际字段、实际 DOI、实际引用边。  
**输出**：解析结果、抽查记录、`sources` 证据、`degradations`。  
**失败分支**：材料损坏、空输入、格式不支持 → 保留 partial，写 `degradations` 与 `pending_human`，继续后续步骤，不补造数据。

### 步骤 4：构建/核对证据，Agent 产出完整成品

**输入**：步骤 2 的基线产物 + 步骤 3 的解析结果。  
**动作**：  
1. 逐项核对 `result.json` 中 `seeds`、`candidates`、`edges`、`screening`、`coverage`、`queries` 是否齐全。  
2. 随机抽 3 条候选，按 `source_locator` 打开原文件确认题名与 DOI；随机抽 3 条边，确认 `citing` 确实引用了 `cited`。任何不一致写进 `agent_review.conflicts`，并修正可修正处。  
3. 对关键论断（如“该种子无前向引用”“某候选为平行工作”“某边来源可核验”）做来源一致性核验；能核验的标 `verified`，不能的标 `pending_human`。  
4. 把核验结果写进 `result.json` 顶层 `agent_review`：`{reviewed_by_agent: true, claims: [...], pending_human: [...], conflicts: [...]}`。  
5. 若 `output_contract` 要求额外结构或文件，在基线基础上补齐，不得删改契约字段。  
**输出**：增强后的 `result.json`、核验标注、冲突记录、变化记录 `changes`。  
**失败分支**：核验发现严重错误且无法修正 → 保留证据，写 `conflicts` 与 `pending_human`，不伪造正确结果。

### 步骤 5：自检 rubric 与完整性

**输入**：步骤 4 产物。  
**动作**：逐项执行 §13 自检清单；核对「`output_contract` 字段 list × 磁盘文件 × `result.json` 键」三者一致；缺项先补齐。  
**输出**：`checks` 自动重算结果、`agent_review` 中补充人工核验结论。  
**失败分支**：任何自检项不过 → 修正；无法修正 → 在 `status` 中保持 `partial`，在 `errors` 中写清限制，仍必须返回合法 `result.json`。

### 步骤 6：回填 result.json 并落盘最终产物

**动作**：  
1. 确保 `result.json` 包含：原 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`checks`、`agent_review`。  
2. 确保所有文件位于 `/app/output`。  
3. 若生成了可编辑 Office/幻灯片/图形产物，用可用渲染工具（如 `libreoffice --headless --convert-to pdf` 或 `rsvg-convert` 等）生成 PDF/PNG 预览；无法渲染则写 `degradations`。  
4. 无需退出码非 0；即使部分失败，也返回 0。

## 4. 输入发现与记录识别（语义识别，不假设键名）

1. `case.json`（或 `input.json` / `task.json` / 任意 `case*.json`）：取 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`。键名大小写与下划线差异由 `getf()` 归一化。  
2. 递归扫描 `--input` 下所有文件：`.json/.jsonl/.ndjson` 结构化解析；`.csv/.tsv` 按表头映射（`citing*`→施引侧、`cited*`→被引侧、`doi/id`→DOI、`title`→题名），两侧 DOI 齐全时同时产出两侧记录与一条 `cites` 边；`.yaml/.yml/.txt/.bib/.ris/.xml` 仅做 DOI 字面抽取（不猜题名年份，详见 `references/sources.md` §5.1）；`.pdf` 用 `pdftotext`（若存在）抽文本，提取 DOI 与首页题名作为**种子线索**，失败则降级并写入 `degradations`。文件名含 `import/sync/state` 的对象另作增量导入状态登记，写入 `coverage.import_states`。  
3. 记录识别：任何对象只要有外部标识（DOI/PMID/OpenAlex/arXiv/S2 id）或规范标题，即视为文献记录；连线由 `reference(s)`/`citations`/`cited_by`/`bibliography`/`referenced_works` 等字段或显式 `citing→cited` 对提取。  
4. 种子识别：语义扫描含 `seed/start_paper/target_paper/focal/root_paper` 的键；再补 `task_instruction` 里的 DOI；解析顺序 DOI → PMID → OpenAlex → 标题精确 → 标题模糊（≥0.90）。都没有时退化为“保留图中连接度最高的作品”，并把 `seed_inferred` 写进 `uncertainty` 与 `pending_human`。

## 5. 核心方法

1. 扫描输入 → 记录与原始边；每个文件写一条 `retained_cache_scan` 查询日志，PDF 另写 `local_pdf` 的 `pdf_seed_scan` 日志。  
2. 身份合并（union-find）：DOI/PMID/arXiv/OpenAlex/S2 精确键 → 规范化标题精确 → 标题模糊（≥0.93 且年份差 ≤1 且共享作者）。同年同名但年份差 >3 判为同名歧义，打 `homonym_suspect`，不合并。  
3. 种子解析 → 有向 BFS（`--depth` 默认 2，单节点单方向 30 邻居，候选上限 3×cap）。  
4. 关联发现：耦合（与种子共享 ≥2 参考文献）与共被引（被同一批保留工作施引）。  
5. 排序：`0.40*relation + 0.20*proximity + 0.15*topical + 0.15*centrality + 0.10*recency`，分项全部写入 `relevance_breakdown`。  
6. 覆盖与缺口、基线对照、自检、落盘。方法细节、停止判据与基线协议见 `references/workflow.md`。

## 6. 输出契约

固定主产物（写在 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 全部结构化结果 + 契约字段 + `status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`/`checks`/`agent_review` |
| `candidates.csv` | 候选清单（id、题名、作者、年、DOI、来源库、命中方式、分数、置信度、定位） |
| `query_log.json` | 逐条查询记录：`db / raw / kind / hits / retained / status / retrieved_at` |

`result.json` 关键块：`seeds`、`candidates`、`edges`、`screening`、`coverage`、`metrics`、`baseline`、`queries`、`sources`、`missing`、`checks`。字段字典见 `references/schema.md`。

`candidates.csv` 与 `query_log.json` 是主产物的可复用导出；`screening` 在 `result.json` 内逐条给出 `include`/`criteria`/`reason`，`missing` 列出材料无法提供的项及其补数动作。

每条候选必带：`source_locator{file,json_pointer,retrieved_at}`、`citation_relation{direction,edge_ids,hop_count}`、`relevance_reason`、`relevance_breakdown`、`metadata_confidence`、`evidence`、`path`（从种子逐跳到该文献的链）。

`agent_review` 是本版新增的顶层可扩展字段，不替代任何契约字段，不删除基线字段。

## 7. 预算策略（64 次模型请求 / 900 秒 / 16384 tokens）

**总原则**：用脚本做重体力，用模型做核验与决策。优先保证实际效果（40 分）和可靠体验（10 分）所必需的完整性、可核验性，再追求增益和创新证据。

**请求分配建议**：

| 阶段 | 模型请求 | 说明 |
|-|-|-|
| 步骤 1-2 盘点与基线运行 | 1-2 | 只运行脚本，读完输入清单和脚本输出后写一个简短核验计划；不被卷入逐条阅读 |
| 步骤 3 材料解析抽查 | 2-4 | 只抽查 2-3 个关键文件，确认脚本抽取与原材料一致；不逐行浏览全部记录 |
| 步骤 4 证据核验与增强 | 5-10 | 抽 3 条候选 + 3 条边核验；必要时抽一个路径链；把结论写入 `agent_review` |
| 步骤 5-6 完整性自检与落盘 | 2-4 | 核对契约字段、文件、缺项；最后写 `changes` 与 `status` |
| 保留余量 | 约 5-10 | 应对材料异常、契约缺失、额外渲染需求 |

**必须做**：基线脚本运行、契约字段回填、候选/边来源抽查、完整性自检。  
**可以跳过**：逐条阅读所有候选、重复运行无变化的脚本、重复解释已在 `references/` 说明清楚的方法。  
**何时落盘 partial**：基线脚本启动后立即可落盘；每次核验或修复后都要覆盖写 `/app/output/result.json`，最晚在 800 秒前完成终稿。任何情况下不得空手退出。

## 8. 隐藏案例鲁棒性

隐藏案例可能包含：材料缺失、PDF 损坏或扫描件、CSV 缺列、JSONL 半行损坏、空输入、种子未被识别、前向引用为空、跨库字段冲突、import_status 未完成、同名论文歧义、契约缺失、超时等。无论触发哪种情况，必须：

1. 继续产出合法 `result.json`，退出码 0。  
2. 不编造文献、引用边、分数或状态。  
3. 将问题写进 `degradations`、`uncertainty`、`pending_human`、`errors` 或 `missing` 中，并区分“已完成”与“未完成”。  
4. 若 `output_contract` 缺失，则按 `references/schema.md` 的规范 schema 输出，并在 `degradations` 中标记 `contract_missing`。  
5. 若超时临近，优先保存已有 partial，再考虑降级增强。

## 9. 评分维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果-任务完成度 | 15 | 以种子为起点沿 backward/forward/parallel 三通道扩展，交付候选集、边表、路径 | `seeds`→`candidates`、`edges`、`path`；`channel` 与 `hop_count` 齐全 |
| 实际效果-结果正确性 | 15 | 文献真实存在；引用方向正确；身份合并正确；关联依据明确 | `citation_relation.direction`；`identity_merges` 与 `homonym_suspect`；`metadata_confidence`；`agent_review.conflicts` |
| 实际效果-结果完整性 | 5 | 覆盖关键被引出处、主要后续改进、代表性平行工作；缺口显式列出 | `coverage.gaps`；`missing`；`seed_neighbourhood_coverage` |
| 实际效果-结果可核验性 | 5 | 每条候选可回指原文；每条边有来源；查询有日志 | `source_locator{file,json_pointer,retrieved_at}`；`edge_ids`；`query_log` |
| 使用增益-质量增益 | 15 | 相对基础 Agent 提升追踪质量：去重、方向标注、可解释来路 | `baseline.delta`；`identity_merges`；`direction` 标注率；`hop`/`via_work`/`edge_ids` |
| 使用增益-效率增益 | 5 | 减少无效翻页、去重返工、调用成本 | `runtime.duration_s`；`counts`；`queries` 的 `retained/hits` 比例 |
| 使用增益-增益可验证性 | 5 | 公平对照与重复运行 | `baseline.protocol`；脚本同输入重跑可得相同结构 |
| 创新增益-新增能力 | 5 | 跨库身份对齐、方向感知扩展、可解释路径 | `identity_merges`；`citation_relation.direction`；`path` |
| 创新增益-方法改进 | 5 | 去重键、路径排序、停止判据有实质改进 | `relevance_breakdown` 分项；`coverage` 停止判据；去重规则记录在 `references/schema.md` |
| 创新增益-创新证据 | 5 | 证明相对已有方案边界与价值 | `baseline.delta` + `coverage.gaps` + `agent_review` 中自评边界，避免自造 Recall |
| 可靠体验-调用与易用性 | 3 | 命令零配置、说明清晰 | `--help` 即用；本 SKILL §3、§14 |
| 可靠体验-运行稳定性 | 4 | 不同学科、覆盖度、数据源下持续产出可用结果 | 空输入/坏 JSON/无种子/无边均返回合法 `result.json`，退出码 0 |
| 可靠体验-异常处理 | 3 | 识别种子无引文、同名歧义、字段冲突、撤稿/更正、限流/权限不足 | §12 分支表；`uncertainty` + `pending_human` + `degradations` |
| 生态贡献-文档完整性 | 3 | 使用说明、依赖、配置、样例、边表字段、去重规则齐全 | 本 SKILL + `references/{schema,sources,workflow}.md` |
| 生态贡献-资源可复用性 | 4 | Skill 本体、脚本、边表结构、去重规则可复用 | `candidates.csv`、`query_log.json`、`scripts/citelib.py`、`references/schema.md` |
| 生态贡献-分享推广价值 | 3 | 沉淀追踪案例、路径图、去重经验 | `agent_review` 中记录实际追踪价值；`path` 可复核；不伪造 |

## 10. 证据与定位规范

- 定位三元组：`file`（相对 `--input`）+ `json_pointer`（记录在文件中的路径）+ `retrieved_at`（记录自带字段优先，否则文件 mtime，并在 `runtime` 标注）。  
- 引用边：`{edge_id, citing, cited, relation:"cites", source_file, evidence[{json_pointer, field, item_index, retrieved_at}]}`。同一对节点最多保留 5 条证据。  
- `url` 由 DOI 推导（`https://doi.org/<doi>`），**不是**抓取结果；只对有 DOI 的候选生成。  
- 不写任何无法定位的数值。`coverage.recall_estimate` 恒为 `null`，并写明“保留样本上不可计算”。

## 11. 冲突与人工确认

| 情形 | 处置 |
|-|-|
| 跨库字段冲突（题名/年份/期刊不一致） | 保留全部来源于 `provenance`，主值取置信度最高者；分歧进入 `coverage.gaps` 或 `flags` |
| 同名不同文 | 年份差 >3 不合并，双方打 `homonym_suspect` |
| 撤稿 / 更正 / 预印本 | `flags: retraction_marker / correction_marker / preprint / conference_version`，并在 gaps 提示“引用前需核实” |
| 种子无前向引用 | `uncertainty.seed_without_forward_citations` + 一条 `planned_query(status=not_executed)` |
| 种子无参考文献表 | `uncertainty.seed_without_reference_list` |
| 种子无法判定 | 退化 + `seed_inferred` + `pending_human`（请人工确认种子） |

## 12. 异常降级分支表

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
| DOCX/XLSX/PPTX 无法解析 | 登记来源和 `unsupported_format`，继续其他材料 | `degradations` |
| 增量导入未完成 | 读 `import/sync/state` 类对象 | `coverage.import_states` + `uncertainty.incremental_import_pending` |
| 权限/限流/离线补检 | 不发起、不假装 | `planned_query(status=not_executed)` |
| 超时临近 | 立即保存 partial，停止非关键增强 | `status=partial`，`runtime.timeout` 真实标记 |

## 13. 自检清单（提交前逐项检查）

**自动检查**（每次运行写入 `checks`）：  
`contract_complete` → `case_id_present` → `locator_present` → `doi_well_formed` → `direction_labeled` → `no_fabricated_recall` → `screening_complete`；全部通过时 `self_check_pass = true`。任一不通过时看 `contract_missing` 或该项的 `detail`。`checks` 在任何退出路径上都会写出。

**Agent 人工复核五条**：  
1. 随机抽 3