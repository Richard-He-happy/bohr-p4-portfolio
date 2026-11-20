---
name: citation-tracer
description: 以种子论文为起点，沿引用与关联关系执行方向感知的文献追踪、关联发现、身份合并与去重排序，输出可复核候选集、引用边表、路径与缺口。适用输入为 /input/case.json、/input/task.md 以及题面提供的 PDF/DOCX/CSV/JSON/JSONL/XML/BIB/RIS 等材料；不替代普通关键词检索，不做未授权的在线抓取。脚本是工具，Agent 必须真实阅读材料、核验并增强产物，不允许把脚本骨架当成品。
version: 2.0.0
---

# Citation Tracer

## 0. 最高优先级：完整性、可核验与诚实

1. 本 Skill 由脚本产出结构化基线，由 Agent 亲自核验、增强文本型交付物，**不是**手工重写 JSON 结构。
2. 禁止直接手改 `result.json` 的脚本字段（键名、claim_id、source_id、locator、quote、strength、counts 等）。若发现错误，写临时调用脚本函数修正并记录于 `agent_review.script_fixes`，不手工篡改。
3. 禁止编造文献、引用边、分数、状态或无法定位的数值；禁止自造 `golden_standard`、加权自评、假 Recall。
4. 无论成功失败，必须生成合法 `result.json`，退出码恒为 0。partial 可接受，但须诚实标注 limits。
5. 提交前逐项核对「`output_contract` 字段 × 磁盘文件 × `result.json` 键」三者一致；缺项补齐或明确 `missing`。

## 1. 用途与边界

**用途**：以种子论文为起点，沿引用与关联关系扩展出可直接进综述的文献集，并为每条结果保留来源、依据与路径。

三通道，全部方向感知：

| 通道 | 含义 | 数据依据 |
|-|-|-|
| `backward` | 种子引用的文献（方法与数据出处、奠基工作） | 种子参考文献表，或反查 `dst=种子` 的边 |
| `forward` | 引用种子的文献（后续改进、批评、复用） | 其他记录参考文献表出现种子，或种子记录施引列表 |
| `parallel` | 不直接引用种子但同属一条方法脉络的平行工作 | 与种子共享 ≥2 条参考文献（文献耦合），或被同一批工作共同施引（共被引） |

**边界**：不做普通关键词检索、不做全文理解、不做在线抓取、不声明“最新进展”或“全局覆盖”。

**方向读法（重要）**：`channel` 与 `citation_relation.direction` 记录**最后一跳方向**，不是相对种子的直接关系。仅 `hop=1` 可读作直接引用/被种子引用；`hop≥2` 须结合 `related_evidence.basis` 与 `path` 判断它是后续改进还是平行工作。

## 2. 运行契约

- 输入目录：`/input`；工作目录：`/app/work`（由 `--work` 指定，默认 `/app/work`）；最终产物目录：`/app/output`。
- 本包安装位置：`/skills/weekly-skill`。
- **主入口（单命令全流程）**：
  ```bash
  python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
  ```
- 内部阶段：`run` = **init → build → selfcheck**。可分别调用：
  ```bash
  python3 -B /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
  python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
  python3 -B /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work
  ```
  若子命令不受支持，Agent 应回退到：
  ```bash
  python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output
  ```
  并手动按本 SKILL 的阶段顺序执行核验。
- 脚本只读 `--input`，只写 `--output` 和 `--work`；不联网；不依赖 CWD。资源定位使用 `Path(__file__).resolve().parent`。
- 任何异常均捕获写入 `errors`，退出码恒为 0。
- 最终 `result.json` 必须包含原始 `output_contract` 全部字段（顶层）以及 nested `output_contract`（见 §6）。若生成了可编辑 Office/slide/diagram 产物，须有真实 PDF/PNG 预览；无法渲染写 `degradations`。

## 3. 执行流程（Agent 必做，按顺序）

每一步都写“输入 / 动作 / 输出 / 失败分支”；Agent 不跳过基线。

### 阶段 1：Init — 盘点、台账与来源编号

**输入**：`/input` 下所有文件。
**动作**：
1. 列出 `/input` 全部文件；读取 `case.json`（或同名 case 文件），提取 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`。
2. 运行 init（或主命令）产出**台账**（通常在 `/app/work/manifest.json` 或类似）：来源文件编号、记录识别、候选/边/种子清单、冲突分组。
3. Agent 抽查 1-2 个源文件，确认台账抽取与原材料一致。
**输出**：来源编号表（`S#`）、台账、契约清单、种子线索、待解析材料清单。
**失败分支**：输入不存在/坏 JSON → 写 `input_error` 或 `contract_missing`，继续生成合法产物，退出码 0。

### 阶段 2：Agent 路径与确定性兜底（二选一）

**路径 A（Agent-first）**：
- Agent 真实阅读原文，对 init 台账中的候选/边做逐条核验：确认 quote、locator、方向、身份合并。
- 将判断写入 `/app/work/draft.json`（形状见 §7）。可增量更新。
- 然后执行 `check`（或主命令的 selfcheck 阶段）后再 `build`。

**路径 B（无 draft 时确定性兜底）**：
- 若 Agent 未写 draft.json（时间不足或材料不可读），build 必须**使用 init 台账执行确定性抽取**生成实质工作稿，不依赖模型判断。
- 确定性兜底要求：
  - 每条候选和边都有逐字 `quote` + `source_locator`。
  - 将 `AUTO_EXTRACT` 诚实记入 `gaps`/`degradations` 及 `agent_review` 中，说明未经过人工/模型核验。
- 两条路径产出**同一套产物文件与同一份 result.json 契约**。

### 阶段 3：Build — 生成全部产物

**动作**：
1. 运行 build（或主命令）生成 `/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/query_log.json`、`/app/output/deliverable.md`（或契约指定正文型文件）以及任何契约要求文件。
2. 若存在 draft.json，则使用 draft 中的判断覆盖/增强确定性结果；若不存在，保留 AUTO_EXTRACT 标记。
3. 确保每条关键数字/论断在交付物正文中带 `[S#]` 来源引用，以及 `文件#行号/段落号` locator。
**输出**：全套基线产物。
**失败分支**：脚本异常也返回 0；若产物不存在，按 §9 降级生成合法 result.json 并继续。

### 阶段 4：Selfcheck — 自检与 Agent 复核

**动作**：
1. 执行自动 checks（写入 `result.json.checks`）。
2. Agent 随机抽 3 条候选、3 条边、1 条路径链核验：原文 quote、DOI、方向一致性。
3. 将核验结论写入 `agent_review`：`verified` / `pending_human` / `conflicts`。
4. 核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；双层回显完整。
5. 写 `changes`，更新 `status`，确保所有文件位于 `/app/output`。
**输出**：增强后终稿。
**失败分支**：发现严重错误无法修正 → 保留证据，写 `conflicts` 与 `pending_human`，保持 `partial`，不伪造正确结果。

## 4. 输入发现与记录识别

1. `case.json`（或 `input.json`/`task.json`/任意 `case*.json`）：取 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`。键名大小写与下划线差异归一化。
2. 递归扫描 `/input`：`.json/.jsonl/.ndjson` 结构化解析；`.csv/.tsv` 表头映射（`citing*`→施引侧，`cited*`→被引侧），两侧 DOI 齐全时产出一条 `cites` 边和两侧记录；`.yaml/.yml/.txt/.bib/.ris/.xml` 提取 DOI 字面值，不猜题名年份；`.pdf` 用系统可用 `pdftotext` 抽文本，提取 DOI 与首页题名作为种子线索；失败降级并写 `degradations`。
3. 记录识别：对象只要有外部标识（DOI/PMID/OpenAlex/arXiv/S2）或规范标题，即视为文献记录；连线由 `references`/`citations`/`cited_by`/`bibliography`/`referenced_works` 或显式 `citing→cited` 对提取。
4. 种子识别：语义扫描 `seed/start_paper/target_paper/focal/root_paper` 键；再补 `task_instruction` 里的 DOI；解析顺序 DOI → PMID → OpenAlex → 标题精确 → 标题模糊（≥0.90）。都没有时退化“图中连接度最高作品”，并写 `seed_inferred` 到 `uncertainty` 和 `pending_human`。

## 5. 核心方法

1. 扫描输入 → 记录与原始边；每个文件写一条 `retained_cache_scan` 查询日志；PDF 另写 `local_pdf` 的 `pdf_seed_scan` 日志。
2. 身份合并（union-find）：DOI/PMID/arXiv/OpenAlex/S2 精确键 → 规范化标题精确 → 标题模糊（≥0.93 且年份差 ≤1 且共享作者）。同年同名但年份差 >3 判为同名歧义，打 `homonym_suspect`，不合并。
3. 种子解析 → 有向 BFS（默认 `--depth 2`，单节点单方向 30 邻居，候选上限 3×cap）。
4. 关联发现：文献耦合（与种子共享 ≥2 参考文献）与共被引（被同一批保留工作施引）。
5. 排序：`0.40*relation + 0.20*proximity + 0.15*topical + 0.15*centrality + 0.10*recency`，分项写入 `relevance_breakdown`。
6. 覆盖与缺口、基线对照、自检、落盘；方法细节参见 `references/workflow.md`。

每条候选必带：`source_locator{file,json_pointer,retrieved_at}`、`citation_relation{direction,edge_ids,hop_count}`、`relevance_reason`、`relevance_breakdown`、`metadata_confidence`、`evidence`、`path`（从种子逐跳到该文献的链）。

## 6. 输出契约与 result.json 双回显

固定主产物（位于 `/app/output`）：

| 文件 | 内容 |
|-|-|
| `result.json` | 全部结构化结果 + 契约字段双回显 + `status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`/`checks`/`agent_review` |
| `candidates.csv` | 候选清单：id、题名、作者、年、DOI、来源库、命中方式、分数、置信度、定位 |
| `query_log.json` | 逐条查询：`db / raw / kind / hits / retained / status / retrieved_at` |
| `deliverable.md` | 正文型交付物，带 `[S#]` 和 `文件#行号/段落号` locator；不得删除契约字段 |

`result.json` 必须满足**双回显**：
- **顶层**：填写原 `output_contract` 的全部原始字段，包括 `case_id`，值必须与输入一致。
- **嵌套**：同时存在一个 `"output_contract"` 对象，内容为同一份原始契约字段的完整副本（含 `case_id`）。
- 示例结构（字段按实际契约调整）：
  ```json
  {
    "case_id": "...",
    "...contract fields...": "...",
    "output_contract": {
      "case_id": "...",
      "...contract fields...": "..."
    },
    "status": "partial",
    "sources": [],
    "uncertainty": {},
    "pending_human": [],
    "errors": [],
    "degradations": [],
    "changes": [],
    "runtime": {},
    "checks": {},
    "agent_review": {}
  }
  ```

`result.json` 内关键块：`seeds`、`candidates`、`edges`、`screening`、`coverage`、`metrics`、`baseline`、`queries`、`sources`、`missing`、`checks`。字段字典见 `references/schema.md`。

## 7. draft.json 形状（Agent 路径）

Agent 在 `/app/work/draft.json` 中写入判断，作为 build 的增强输入。最小形状：

```json
{
  "draft_version": "1.0",
  "case_id": "...",
  "decisions": [
    {
      "candidate_id": "...",
      "include": true,
      "reason": "...",
      "quote": "...",
      "locator": {"file": "...", "line": 12, "paragraph": 3},
      "verified_fields": ["title", "doi", "direction"]
    }
  ],
  "edge_confirmations": [
    {"edge_id": "...", "direction_ok": true, "evidence_locator": "...", "note": "..."}
  ],
  "identity_merges": [
    {"base_id": "...", "merged_ids": ["..."], "evidence": "..."}
  ],
  "conflicts": [],
  "pending_human": [],
  "auto_extract_fallback": false
}
```

若该文件不存在或 `auto_extract_fallback: true`，build 走确定性兜底路径（§3 阶段2 路径 B）。

## 8. 证据与定位规范

- 定位三元组：`file`（相对 `/input`）+ `json_pointer`（记录在文件中的路径）+ `retrieved_at`（记录自带字段优先，否则文件 mtime，并在 `runtime` 标注）。
- 引用边：`{edge_id, citing, cited, relation:"cites", source_file, evidence[{json_pointer, field, item_index, retrieved_at}]}`。同一对节点最多保留 5 条证据。
- `url` 由 DOI 推导（`https://doi.org/<doi>`），**不是**抓取结果；只对有 DOI 的候选生成。
- 不写任何无法定位的数值；`coverage.recall_estimate` 恒为 `null`，并写明“保留样本上不可计算”。
- 正文型交付物中的每个关键数字、每条引用边、每个关联判断都使用 `[S#]` 标记指向来源，并同时给出 `文件#行号/段落号`（例如 `[S3] 材料.json#42`）。

## 9. 异常与降级

| 触发 | 行为 | 字段 |
|-|-|-|
| 输入目录不存在 | 生成合法结果，退出码 0 | `status=input_error`，`pending_human` |
| `case.json` 缺失/坏 JSON | 继续扫描其他文件；无契约则仅输出规范 schema | `degradations`，`contract_missing` |
| JSONL 部分行损坏 | 跳过坏行，计数 | `degradations[{what,count,fallback}]` |
| 无任何文献记录 | 停止，不补造 | `status=insufficient_evidence` |
| 无种子 | 退化推断或停止 | `uncertainty.seed_inferred` / `insufficient_evidence` |
| 种子已解析但无边可扩展 | 候选为空 | `status=insufficient_evidence`，`empty_candidate_set` |
| 引用边无法落库到记录 | 跳过并计数 | `counts.edges_unresolved`，写 gaps |
| PDF 可抽文本 | 提取 DOI/首页题名作为种子线索 | `sources{kind:"pdf",doi_candidates}`，`pdf_seed_scan` 日志 |
| PDF 不可抽文本 | 只登记来源 | `degradations`：`pdf metadata only` |
| DOCX/XLSX/PPTX 无法解析 | 登记 `unsupported_format`，继续 | `degradations` |
| 增量导入未完成 | 读 `import/sync/state` 类对象 | `coverage.import_states` + `uncertainty.incremental_import_pending` |
| 权限/限流/离线补检 | 不发起、不假装 | `planned_query(status=not_executed)` |
| 超时临近 | 立即保存 partial，停止非关键增强 | `status=partial`，`runtime.timeout` 真实标记 |
| `run` 子命令不可用 | 回退旧式主命令并手动按 §3 阶段执行 | 记录于 `agent_review` 或 `degradations` |

## 10. 增益证据（相对基础 Agent）

在 `result.json` 中显式提供以下字段作为可验证增益：

- `baseline.delta`：描述加载本 Skill 后相对基础 Agent 在候选集、去重、方向标注、路径解释上的差异；不声称未实测的分数。
- `identity_merges`：列出合并证据，说明减少了多少重复项。
- `direction_labeled_rate`：候选中有方向标注的比例（`counts` 中）。
- `hop/edge_ids/path`：来路可解释性证据。
- `runtime.duration_s` 与 `queries` 的 `retained/hits` 比例：效率证据。
- `agent_review`：核验记录，证明不是自动生成无依据。
- 不创建假 `recall`、`f1`、未经运行的基准。

## 11. 预算策略（64 次模型请求 / 900 秒 / 16384 tokens）

**原则**：脚本做重体力，模型做核验与决策；优先保证实际效果与可靠体验。

| 阶段 | 模型请求 | 说明 |
|-|-|-|
| Init 盘点与基线运行 | 1-2 | 运行脚本，读清单，写简短计划 |
| 材料解析抽查 | 2-4 | 抽 1-2 个关键文件确认一致性 |
| 证据核验与增强 | 5-10 | 抽 3 候选 + 3 边 + 1 路径；写入 `agent_review` |
| 完整性自检与落盘 | 2-4 | 核对契约、文件、缺项，写 `changes` |
| 保留余量 | 5-10 | 应对异常、额外渲染 |

**必须做**：运行基线脚本、回填契约字段、候选/边抽查、完整性自检。
**可选**：逐条阅读所有候选、重复运行无变化脚本。
**最晚保存点**：800 秒前完成终稿；任何情况不得空手退出。

## 12. 自检清单

**自动检查**（由脚本写入 `checks`）：
`contract_complete` → `case_id_present` → `locator_present` → `doi_well_formed` → `direction_labeled` → `no_fabricated_recall` → `screening_complete`；全部通过时 `self_check_pass = true`。任一不通过看该项 `detail`。

**Agent 人工复核五条**：
1. 随机抽 3 条候选，按 locator 打开原文件确认题名与 DOI 存在且一致。
2. 随机抽 3 条边，确认 `citing` 确实引用了 `cited`，方向无颠倒。
3. 抽 1 条路径链，逐跳确认方向和源文件。
4. 核对 `result.json` 顶层与 nested `output_contract` 的契约字段完全一致。
5. 核对磁盘文件与 `result.json` 中引用的文件都存在；缺失文件写入 `degradations`。

## 13. 文档与生态

- 本包提供以下参考文件，Agent 应查阅：
  - `references/schema.md`：字段字典与去重规则。
  - `references/sources.md`：数据源识别与解析规则。
  - `references/workflow.md`：方法细节、停止判据与基线协议。
- 运行环境：**纯 Python 标准库**，**离线**，Python >= 3.8；不依赖第三方包。
- Skill 本体、脚本、边表结构、去重规则均可复用：`scripts/citelib.py`、`scripts/main.py`、`references/schema.md`。
- 本 SKILL 内置了自检清单、draft 形状、异常降级和增益证据要求，可作为独立文档使用。

## 14. 最小调用示例

以下示例仅用于说明接口，不是正式案例结果。

**输入**：`/input/case.json`（含种子 DOI 与 output_contract），若干 JSONL 引文记录。
**调用**：
```bash
mkdir -p /app/work /app/output
python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```
**示意输出**：
- `/app/output/result.json`：含顶层与 nested output_contract 双回显，`status=partial`，`candidates` 非空，每条候选有 `source_locator`、`citation_relation`、`path`.
- `/app/output/candidates.csv`：可读候选清单。
- `/app/output/query_log.json`：查询与保留率。
- `/app/output/deliverable.md`：带 `[S#]` 来源标记的正文综述。

**退出码**：始终 0。