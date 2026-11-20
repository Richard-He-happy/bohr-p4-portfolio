---
name: library-annotation-sediment
description: Repair a research file library and turn reading annotations into traceable, searchable notes. Scans real PDF/DOCX/HTML/text materials, extracts highlight/underline/margin/handwriting annotations with page- and character-level anchors, inventories files with sha256 and provenance-tagged metadata, resolves duplicates and version chains by content hash and administrative version notes, links annotations to structured notes, builds a searchable index, answers the case search questions, and emits result.json plus inventory.csv, operations.log, version_chain.json with honest errors/degradations. Use when a task supplies a library/ or materials directory of documents and asks for annotation extraction, note sedimentation, duplicates/versions, an inventory, or library repair. The ship has been tuned for the Bohrium Agent Skill competition: it first runs the included deterministic baseline, then requires the Harness Agent to personally read the actual materials, verify evidence, and enhance the deliverables before finalizing.
version: 0.2.0
---

# library-annotation-sediment

一个用于“阅读批注与知识沉淀：科研资料管理，整理文件，也保留版本关系”的 Skill。它先运行包内确定性脚本产出完整基线交付物，然后要求 Harness Agent 亲自读取 `/input` 中的真实材料、核验原文引用、批注定位、哈希与版本链，并在基线上增强写出可复核的 `/app/output/result.json` 与全部相关文件。

脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本生成的骨架、模板或中间 JSON 直接当最终成品。你必须在基线上完成真实核验、修正、补充并留下可复跑证据。

## 0. 运行时契约与硬性要求

- 输入位置：`/input/case.json`、`/input/task.md`，以及题面规定的材料目录（PDF、DOCX、XLSX、CSV、HTML、TXT、图片等）。
- 工作目录：`/app/work`；最终产物必须落在 `/app/output`。
- 最终必须有 `/app/output/result.json`，包含 `case_id` 和原 `output_contract` 中提取的全部字段（键名不改），未知字段写 `value: null`；同时保留原始 `output_contract`。
- 若产生可编辑 Office、幻灯片、图等产物，必须额外生成真实渲染的 PDF/PNG 预览；无法渲染时要在 `errors`/`pending_human` 中如实说明。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。必须预算感知：先产出 honest partial，优先完成 rubric 权重最高的交付物，再增量改进。
- 诚实性：`status`、`sources`、`uncertainty`、`changes` 必须真实；材料缺失、解析失败、不确定一律显式标注，不得编造数据、引用、分数。
- 资源限制：Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。脚本与文档不能包含预制答案或正式案例结果。

## 1. 核心原则：先跑基线，再亲自复核增强

1. **必须第一步运行基线脚本**：进入任务后，立即执行：
   `python3 -B scripts/main.py --input /input --output /app/output --work /app/work`
   该脚本会确定性产出全套基线：`result.json`、`inventory.csv`、`operations.log`、`version_chain.json`、`annotations.json`、`notes.json`、`index.json`，并回填 `output_contract` 字段。
2. **保留全部基线产物**：后续 Agent 只能修订或新增，不得删除、清空、覆盖任何基线与契约字段。若发现脚本结果可疑，保留原值并在 `changes`/`summary` 中记录 `reviewed_by_agent`。
3. **Agent 亲自核验**：在基线之上，你必须读取实际材料并核验关键论断、数字、引用、定位、来源一致性，把核验结论写进 `result.json`（`verified`、`pending_human`、`conflicts`、`limitations`）。
4. **不要只跑脚本就结束**：脚本是 stdlib 基线，不能证明你真正读过材料。高分的“genuinely-derived solution”要求你在结果中留下亲自阅读与推导的证据。

## 2. 本题专属执行流程

### 步骤 1：盘点输入

- 输入：`/input/case.json`、`/input/task.md`、材料目录树。
- 动作：
  1. 读取 `/input/case.json`；若缺失，递归搜索 `**/case*.json`；仍失败则记录 `input_error`。
  2. 读取 `/input/task.md`，提取任务说明、限制、评分证据范围。
  3. 从 `case.json` 中提取 `case_id`、`output_contract`（键名语义可兼容：`output_contract`/`contract`/`output_schema`）、`task_instruction`、检索问题/询问字段（`query`/`question`/`search_query`/`ask`）。
  4. 递归遍历 `/input/**`，用扩展名 + magic bytes 识别文件类型，绝不依据文件名或领域标签猜测内容。
- 输出：文件清单、输出契约、检索问题列表、风险提示。
- 失败分支：`case.json` 缺失或不可解析 → 继续扫描所有材料；`status` 设为 `partial` 或 `insufficient_evidence`；错误写入 `errors`，待人工项写入 `pending_human`；最终仍 exit 0。

### 步骤 2：用工具真实解析材料

- 输入：步骤 1 得到的材料文件列表。
- 动作：
  1. 对每个 PDF：优先调用平台提供的 `pdf-text-tool`（如果可用）或系统 PATH 中的 `pdftotext -layout`；若这些不可用，退回包内 `python3 -B scripts/docext.py` 的 PDF 提取逻辑。必须提取真实文本层、页码、字符级锚点信息；对没有文本层的扫描件，使用可用的 OCR 工具；无 OCR 时保留文件并标记 `anchor_unresolved`、`scanned_pdf`，写入 `pending_human`。
  2. 对 DOCX：用 `scripts/docext.py` 或环境中的 `python-docx` 提取正文、comments、高亮/批注位置。
  3. 对 XLSX/CSV：提取行列文本，记录 sheet/表头/源文件。
  4. 对 HTML/TXT：按 UTF-8 提取文本或 DOM 文本。
  5. 任何材料实际不可读、加密、损坏、格式不支持 → 不猜测内容；记录 `skipped` + `pending_human`。
- 输出：各文件可核验的文本层、页号、坐标、批注类型/颜色/作者/时间、错误与降级记录。
- 失败分支：单文件解析失败 → 只把该文件降级，其他文件继续；不要整体失败。解析工具全部缺失 → 基线脚本仍可生成部分内容，但你必须在 `limitations` 中说明哪些文件未被真实读取。

### 步骤 3：构建/核对证据

- 输入：脚本基线产物 + 步骤 2 的真实解析结果。
- 动作：
  1. 对每份文件：核验 `id/path/sha256/size/mtime/mode/readable/type`，与实际文件一致；不一致时以实际为准并记录修正。
  2. 对重复文件：基于 sha256 字节级哈希分组；其他疑似重复只标记 `duplicate_of`，不删除任何文件。
  3. 对版本链：按文件名去除版本/draft 标签 + 版本标签/日期 + mtime 排序，形成 `supersedes` 边；文件名本身不能当证据，依据要写入 `basis`；不确定标 `uncertain`。
  4. 对每条 annotation：核验 `quote` 是否在原文中真实存在，`locator`（page + char_start/end + rect）是否落在源文件页内；若脚本定位漂移，手工修正或用文本重定位；无法确认则标 `anchor_unresolved`。
  5. 对每条 note：核验其 evidence 的 `file/page/quote/precision/locator/annotation_id` 是否可回溯；没有原文支撑的论断不得写成确定结论。
  6. 对每个 search 问题：执行真实检索，记录 `query → matched_notes/files → shared terms`；词汇缺口标 `no_recall`，绝不能把无结果写成没有答案。
- 输出：证据核验后的 `inventory`、`duplicates`、`version_chain`、`annotations`、`notes`、`links`、`search`、`verification` 增强。
- 失败分支：核验发现冲突 → 写入 `conflicts` 与 `pending_human`，保留原脚本值。

### 步骤 4：Agent 产出完整成品

- 输入：步骤 3 核验后的基线产物与材料。
- 动作：
  1. 补齐 `/app/output/result.json` 的所有规定字段，加上 `case_id` 与 `output_contract` 全部字段。
  2. 保证 `sources`、`artifacts`、`runtime`、`summary`、`contract_fill` 反映实际工作，而不是脚本占位。
  3. 如果 `output_contract` 要求可编辑 Office/slide/diagram 产物，用 `libreoffice --headless` 或等价工具真实渲染 PDF/PNG 到 `/app/output`，并把预览路径写入 `artifacts`；渲染失败写入 `errors` 和 `pending_human`。
  4. 在 `changes` 或新增的 `reviewed_by_agent` 字段中记录 Agent 亲自核验了哪些文件、哪些 quote/locator/hash 经过人工核对；保留 `verified`/`pending_human`/`conflicts` 证据。
  5. 完成后写一次 final `result.json`；partial 状态必须列出缺失项，不要把未完成写成完成。
- 输出：完整、可复核的 `/app/output` 交付物套件。
- 失败分支：任何材料不足或无法确认 → `status` 设为 `partial` 或 `insufficient_evidence`，`pending_human` 列出具体 action；仍 exit 0。

### 步骤 5：自检 rubric 与回填 result.json

- 输入：当前 `/app/output` 文件与 `output_contract`。
- 动作：
  1. 逐项检查本文第 6 节 rubric 对照表。
  2. 检查 `result.json` 的键是否包含所有 `output_contract` 字段 + `case_id`；未知字段写 `null`。
  3. 检查磁盘文件列表与 `result.json.artifacts` 一一对应；缺文件先补齐或标注。
  4. 检查 `errors`/`degradations`/`pending_human` 与真实失败一致。
  5. 回填 `status`、`sources`、`uncertainty`、`changes`、`runtime`、`contract_fill`。
- 输出：最终提交就绪的 `/app/output`。
- 失败分支：发现缺失字段或文件 → 先补齐再收尾；如果时间到 720 秒还差，写一个明确列出缺失项的 partial `result.json`（exit 0）。

## 3. 预算策略：64 次模型请求 / 900 秒内如何分配

按 rubrics 权重优先：实际效果（40 分）> 使用增益（25 分）> 创新增益（15 分）> 可靠体验（10 分）> 生态贡献（10 分）。

- **必须做（约前 10 次请求）**：读 `case.json` 和 `task.md`；运行基线脚本；确认 `output_contract` 字段。
- **重点做（约 15–25 次请求）**：真实解析关键材料，特别是 PDF/DOCX 批注。优先处理高价值文件：含批注、版本链、重复文件、检索问题涉及的文件。不要对每个文件都做同样深度的解析。
- **核验与增强（约 15–20 次请求）**：抽查或全量核验 annotation/note 的 quote 与 locator；修正明显错误；补齐结果 JSON 的关键证据。
- **可跳过或压缩**：对纯文本、CSV 等低风险文件只做轻量核验；对非关键元数据不逐项重算；不进行无收益的多轮循环。
- **尽早落盘 partial**：脚本跑完立即保证 `/app/output/result.json` 已存在；之后每次增强都及时覆盖写回。
- **720 秒前**：进行完整性自检，若发现缺失项立即补齐 partial 并标记。
- **900 秒前**：无条件写最终 `result.json`，exit 0。

## 4. 隐藏案例鲁棒性

任何情况下都要产出合法 `result.json` 且退出码为 0。降级策略：

| 情况 | 处理 |
|-|-|
| `/input/case.json` 缺失或无法解析 | `errors` + `pending_human`；仍扫描全部文件；`status`=`partial` 或 `insufficient_evidence`；exit 0 |
| `output_contract` 缺失或为空 | 保留默认字段集；`contract_fill` 记录无法回填；`status`=`partial`；exit 0 |
| 材料文件缺失或空目录 | `status`=`insufficient_evidence`；`errors` 记录无材料；仍生成合法 result.json 与空 artifacts；exit 0 |
| 文件加密/损坏/无法读取 | 保留可获取的 size/hash，类型标 unknown；`skipped` + `pending_human` |
| PDF 为扫描件无文本层 | 保留文件；`anchor_unresolved`；`pending_ocr`；不编造文本；exit 0 |
| OCR 置信度低 | 标 `uncertain`，锚点置 `pending_human`，不修改原文 |
| 单文件解析失败 | 只降级该文件，不中断整体 |
| 时间即将用尽 | 立即写 partial `result.json`，列出缺失项，exit 0 |
| 工具缺失（如 pdf-text-tool、libreoffice） | 退回 `scripts/docext.py`；仍失败则写 `limitations`，不做伪结果 |
| 版本链同名/同日期不确定 | 标 `uncertain`；不强制排序；不删除 |
| 重复文件 | 标 `duplicate_of`，绝不删除、移动原文件 |
| 检索无结果 | `no_recall` 是词汇缺口，不是“没有答案” |

## 5. 输出契约与目录约定

### 输入目录

`/input/case.json`、`/input/task.md`、`/input/**` 材料。

### 工作目录

`/app/work` 用于临时文件；最终可交付物写在 `/app/output`。

### 脚本调用

```
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
```

基线脚本会先写一个 partial `result.json`，异常捕获，最后无条件覆盖 final `result.json`，退出码始终 0。脚本本身不产生模型请求。

### `result.json` 必须包含的字段

`case_id`、`status`（`ok`、`partial`、`insufficient_evidence`、`input_error`）、`sources`、`artifacts`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`inventory`、`duplicates`、`version_chain`、`annotations`、`notes`、`links`、`search`、`recovery`、`summary`、`contract_fill`，加上从 `output_contract` 提取的全部字段（键名不改，未知字段置 `null`）。原始 `output_contract` 保留在 `output_contract` 字段下。此外可以加入 `reviewed_by_agent`、`verification`、`conflicts` 等增强字段，但不得删除原字段。

### 侧产物文件

基线脚本产物至少包括：`/app/output/inventory.csv`、`/app/output/operations.log`、`/app/output/version_chain.json`、`/app/output/annotations.json`、`/app/output/notes.json`、`/app/output/index.json`。如果 `output_contract` 要求其他文件名，Agent 必须补齐。

## 6. Rubric 维度 → 交付要求 → 自证方式对照表

| Rubric 维度 | 交付要求 | 自证方式 |
|-|-|-|
| 任务完成度 15 分 | 跑完“批注抽取—笔记结构化—关联—入库/检索”闭环，交付可用结果 | `result.json` 的 `annotations`、`notes`、`links`、`search` 非空且来自真实材料；`summary` 描述闭环 |
| 结果正确性 15 分 | 原文片段、页码、位置与文件一致；笔记论断有原文支撑；关联有依据 | 每条 annotation/note 有 `quote`+`locator`；`verification` 中 `quote_in_source=true`；`links` 标 `shared_terms`；错误在 `errors` |
| 结果完整性 5 分 | 覆盖各类批注、关键元数据、文件类型、目录层级、重复文件、版本差异、权限与来源 | `inventory` 字段完整；`duplicates`、`version_chain`、`sources` 覆盖关键文件 |
| 结果可核验性 5 分 | 抽取、笔记、关联、入库可复跑核对 | `sha256`、`locator`、`quote`、`operations.log`、`script version` |
| 质量增益 15 分 | 相同材料下批注抽取准确率、笔记可用性、关联有效性提升 | 基线与 Agent 增强对比记录在 `changes`；标注哪些字段由 Agent 修正 |
| 效率增益 5 分 | 把批注整理成可检索笔记所需人工修改量下降 | `notes` 结构化程度高，可直接检索；`index` 有效 |
| 增益可验证性 5 分 | 同输入对照证明改善 | `changes` 记录“脚本基线 → Agent 修正”的差异；不用编造分数 |
| 新增能力 5 分 | 形成基础 Agent 不易稳定实现的能力 | `anchor对齐`、`跨版本`、`批注到笔记到检索` 贯通，记录方法 |
| 方法改进 5 分 | 锚点对齐、笔记 schema、关联判定、检索入口有实质改进 | `notes` schema 含 question/method/result/limitation/reusable；`links` 依据明确；`search` 词汇缺口策略 |
| 创新证据 5 分 | 证明创新点相对基线价值与边界 | `summary`/`changes` 说明方法优势、边界；不吹嘘 |
| 调用与易用性 3 分 | 给定材料目录能正确触发，能按说明复现 | 本文档的调用步骤最小示例；`scripts/main.py --help` 可运行 |
| 运行稳定性 4 分 | 不同文件类型、页数、版式、重复运行持续可用 | 确定性脚本 + 实际解析记录；`errors` 少且诚实 |
| 异常处理 3 分 | 加密、损坏、无文本层、OCR低置信度、旧版本、重复、权限不足识别处置 | `errors`、`degradations`、`pending_human` 覆盖 |
| 文档完整性 3 分 | 使用说明、依赖、输入输出约定、schema、示例、维护信息齐全 | 本文档第 0–7 节 |
| 资源可复用性 4 分 | 批注抽取脚本、结构、规则可复用复跑 | 包内 `scripts/main.py`、`scripts/docext.py` 无外部依赖 |
| 分享推广价值 3 分 | 沉淀可分享案例、schema、方法价值 | `README` 说明 + `SKILL.md` 方法与局限 |

## 7. 自检清单（提交前逐项检查）

1. 已运行 `python3 -B scripts/main.py --input /input --output /app/output --work /app/work` 产生基线。
2. 已真实读取 `/input/case.json` 和 `/input/task.md`，提取 `case_id` 与 `output_contract` 全部字段。
3. 已用 `pdf-text-tool` 或 `scripts/docext.py` 等工具真实解析了关键材料，没有凭文件名猜测内容。
4. `result.json` 包含 `case_id`、`status`、`sources`、`artifacts`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`inventory`、`duplicates`、`version_chain`、`annotations`、`notes`、`links`、`search`、`recovery`、`summary`、`contract_fill`。
5. `result.json` 对 `output_contract` 每个字段都有回填（未知字段 `value: null`），且原始 `output_contract` 被保留。
6. 所有 annotation/note 的 `quote` 能在源文件中找到，`locator` 归属正确；未找到的标 `pending_human`。
7. 所有文件哈希、重复、版本链依据真实，无编造数据。
8. 生成了 `inventory.csv`、`operations.log`、`version_chain.json`、`annotations.json`、`notes.json`、`index.json`；`result.json.artifacts` 列出这些文件。
9. 若有可编辑 Office/slide/diagram，已生成 PDF/PNG 预览且路径有效；否则在 `errors` 中说明。
10. `status` 选择诚实：全部完成 `ok`，部分完成 `partial`，材料不足 `insufficient_evidence`，输入错误 `input_error`。
11. 无 `__pycache__`/`.pyc` 文件；不超过 50 个 UTF-8 文本文件；无 symlink；无预先写好的正式答案。
12. 命令 `python3 -B scripts/main.py --help` 可退出 0；`python3 -B scripts/main.py --input /input --output /app/output --work /app/work` 在空目录或坏 JSON 下仍 exit 0 且写出合法 partial result.json。

## 8. 最小调用示例（示例，非正式案例结果）

```
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
# 预期输出：status=ok files=2 annotations=1 notes=1 links=0 dup=0 chains=0
```

## 9. 文件清单与版本

- `SKILL.md` — 本文件，版本 0.2.0。
- `scripts/main.py` — 基线流水线，负责扫描、重复检测、版本链、批注/笔记/检索、result.json 回填。
- `scripts/docext.py` — stdlib PDF/DOCX/XLSX/HTML 解析器，被 main.py 导入。

维护建议：变更检测依赖 sha256；相同输入重复运行应确定。若需新增解析器，更新 `scripts/docext.py`；若需更改 schema 或 output_contract 回填，更新 `scripts/main.py`。保持 stdlib-only，报告解析限制要诚实，不得猜测内容。

## 10. 关键提醒

- 你提交的是 Skill，不是三个案例的答案。
- 基线脚本给的只是结构化初稿；高分来自你亲自核验和增强之后的可复核证据。
- 不确定的内容标 `pending_human`，不要为了完整而编造。
- 最终退出码必须是 0，`result.json` 必须合法存在。