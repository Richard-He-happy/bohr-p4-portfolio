---
name: research-question-retrieval
description: >-
  科研问题驱动检索 Skill：把复杂科研问题拆成可检索子问题（对象/机制/方法/比较/局限），
  规划分波查询与术语扩展，在案例提供的文献快照上完成检索、去重、全量筛选与排序，输出带
  query/source/retrieved_at 定位的候选集、查询与筛选日志、覆盖与遗漏说明、冲突与异常记录。
  适用于学术文献检索、证据集构建、检索过程可复现审计；不做单篇精读、全文翻译、写作润色或开放式科研问答。
version: 1.1.0
---

# research-question-retrieval（search-02）

科研问题驱动检索：先拆问题，再规划查询，最后交付证据集与可复核日志。**脚本只是工具，最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作；禁止把脚本骨架/模板直接当成品。**

## 1. 用途与适用边界

**做**：把一个包含研究对象、机制、方法、时间范围、比较关系的科研问题，拆成可检索子问题；
按波次规划查询；做术语/缩写/跨语言扩展；在给定文献快照上检索、去重、全量筛选、排序；输出
候选集 + 可复核日志 + 覆盖与遗漏说明。

**不做**：单篇精读、全文翻译、写作润色、开放式科研问答；不联网、不查实时数据库、不生成
不存在的文献/DOI/引用；不声称“最新进展”（只反映输入快照）。

**适用条件**：`/input` 下存在任务说明与文献材料（JSON/JSONL/CSV 记录，或含题录的 case 文件，
或 PDF/DOCX/图片原文）。材料只有 PDF/DOCX 正文而无结构化题录时，Agent 必须先解析正文提取题录；
解析失败则候选集如实为空并明确标注，不得依据文件名猜测内容。

## 2. 运行契约与目录约定

脚本入口：

```
python3 -B scripts/main.py [--input /input] [--output /app/output]
                          [--max-queries 24] [--max-k 0] [--self-check] [--version]
```

- 只读 `/input`，工作目录 `/app/work`，最终产物落在 `/app/output`；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`）。
- 仅 Python 标准库；无网络；脚本不发起模型调用（`model_requests: 0`）。
- **先落盘**：解析 case 后立刻写 partial `result.json`，随后无条件 finalize 覆盖。
- 退出码**恒为 0**；任何异常进 `errors[]`，不中断其它产物。
- `result.json` 原子写（临时文件 + `os.replace`）。

## 3. 本题专属执行流程（必须按序执行）

### Step 0 预算优先级初始化
- **输入**：`task.md` 评分维度、Runtime contract、本 SKILL。
- **动作**：明确最高权重交付物：结果正确性/完整性/可核验性（实际效果 40 分）、使用增益（25 分）对应的基线对照与候选集；先跑脚本生成全套基线，再增量增强。优先级：`result.json` 合法 > 候选集与子问题对应 > 查询/筛选日志 > 基线对照 > 异常记录 > 文档说明。
- **输出**：内部优先级顺序，写入 `runtime.agent_budget_plan`（可选，不新增顶层键；可放在 `logs[]`）。
- **失败分支**：若连计划都写不下，直接跳到 Step 3 运行脚本。

### Step 1 盘点输入
- **输入**：`/input` 目录。
- **动作**：列出 `/input` 下全部文件与大小，确认 `case.json` 与 `task.md` 是否存在；识别材料类型：JSON/JSONL/CSV/PDF/DOCX/图片。不要根据文件名推断内容。
- **输出**：输入文件清单，记入 `sources[].input_manifest`。
- **失败分支**：若 `/input` 不存在或为空，运行脚本生成合法 partial `result.json`，`status=insufficient_evidence`，`errors[].stage=load_case`，然后跳到 Step 6。

### Step 2 真实解析材料
- **输入**：`/input` 下全部材料文件。
- **动作**：
  1. 若存在结构化题录 JSON/JSONL/CSV，直接读取并保留原始字段；任何 `title`、`authors`、`year`、`venue`、`doi`、`abstract`、`keywords`、`source_db`、`id` 别名均按 `retrieval.py` 的 `AL` 识别。
  2. 若存在 PDF/DOCX/图片，**必须真实解析内容**：对 PDF 调用平台预装解析工具（如 `pdf-text-tool`）；对 DOCX 调用 docx/text 提取工具；对图片若有 OCR 能力则 OCR，否则标为不可解析。抽取文本后提取题录：标题、作者、年份、期刊/会议、DOI、摘要、关键词、来源数据库（若可识别）。提取结果写入 `/app/work/extracted_records.jsonl`（UTF-8）。
  3. 对每个解析失败或格式不支持的文档，记 `errors[].stage=parse_material` 或 `degradations[]`，不中止整体流程。
- **输出**：真实解析后的题录集合，记录每个材料的来源文件、解析方法、解析结果。材料内容摘录存入 `sources[].material_snippets` 以供核验。
- **失败分支**：全部解析失败且无结构化题录 → `status=insufficient_evidence`，候选集为空，但子问题拆解和查询规划仍可从研究问题生成。

### Step 3 生成基线全套交付物
- **输入**：Step 1/2 确认的 `/input`。
- **动作**：运行 `python3 -B scripts/main.py --input /input --output /app/output --max-queries 24 --max-k 0 --self-check`。脚本会解析 case、识别文献记录、完成问题拆解、检索、去重、筛选、排序、基线对照，写出全部 contract 字段及 `candidates.csv`、`query_log.json/.jsonl`、`screening_log.csv`、`selfcheck.json`。
- **输出**：完整基线 `result.json` 与伴随文件。**这是后续 agent 改写的基础，不是最终交付物。**
- **失败分支**：若脚本未运行或运行异常，确保存在最小合法 `result.json`（含 `case_id`、`status`、`question`、空 `candidates`、空 `queries`、`errors[]`、`output_contract_echo`）；继续 Step 4。

### Step 4 Agent 亲自核验与真实推导增强
- **输入**：Step 3 的基线 `result.json`、Step 2 的真实题录、原 `case.json` 问题文本。
- **动作**：你（Harness Agent）必须亲自做以下事，不能只复制脚本输出：
  1. **拆解核验/重写**：读原研究问题，检查 `sub_questions[]` 是否真正覆盖对象、机制、方法、比较、时间、证据要求；如果不准、遗漏或太模板化，就亲自重写每个子问题，并在 `sources[].question_field` 或 `changes[]` 记录修改理由。子问题数量 ≤6，wave 标注合理。
  2. **候选核验/重写**：逐条读 `candidates[]`，确认论文元数据真实（与解析材料逐字一致），`relevance_reason` 必须基于摘要或标题的具体内容，不能是“与子问题相关”的套话；`evidence_snippet` 必须逐字摘自来源记录。发现元数据错误、证据片段不实、理由笼统的，直接修正。
  3. **查询/日志核验**：检查 `queries[]` 与实际检索过程是否一致；若脚本因材料格式未能读到文献而查询为空，你需依据 Step 2 提取的题录重写查询，并确保每条候选有 `query_id`、`source_db`、`retrieved_at`。
  4. **筛选/排序核验**：检查 `screening.decisions[]` 的 include/exclude/defer 理由是否真实、可复核；排序分数是否基于规则；若不满意，写出修正后的筛选和排序。
  5. **缺口与冲突核验**：检查 `coverage.gaps[]`、`conflicts[]`、`pending_human[]` 是否真实反映未解决问题；不要隐瞒或假装完成。
  6. **基线保留**：不得删除或清空脚本生成的任何契约字段；你的改动只能增强或修正，并在 `changes[]` 中记录 `{"stage":"agent_review","field":"...","action":"...","reason":"..."}`。
- **输出**：修订后的 `result.json`（保留全部原始键与 `output_contract_echo`）以及更新的伴随文件（如需重写 CSV/JSONL 可调用脚本或手工写入）。
- **失败分支**：若你无法在预算内完成所有核验，优先保留脚本字段为默认值，只修正明显错误（例如无效 DOI、证据片段不出现、漏掉关键候选）；并在 `uncertainty` 中注明哪些字段未经人工复核。

### Step 5 完整性补漏与可核验增强
- **输入**：Step 4 的修订产物。
- **动作**：
  1. 检查 `coverage.per_sub_question` 是否每个子问题都有 `covered`/`uncovered`；对未覆盖子问题，尝试追加查询或把相关文献补充为 `defer` 并说明。
  2. 检查 `metrics` 中数据是否与 `candidates`、`queries`、`screening` 一致；修正任何矛盾。
  3. 若 `baseline` 对照不可用或无意义，检查输入是否缺少同快照基线；若有材料可建基线，写脚本或手工补充。
  4. 若有可编辑 Office/幻灯片/图形产物要求（本 Skill 主要输出 JSON/CSV，通常不适用），则必须生成真实渲染的 PDF/PNG 预览。
- **输出**：最终版结果集。
- **失败分支**：若时间不足，优先保证高权重字段（候选人、子问题、查询、筛选、覆盖、status）完整，其余标注 pending。

### Step 6 提交前自检与最终落盘
- **输入**：最终产物。
- **动作**：
  1. 运行 `python3 -B scripts/main.py --input /input --output /app/output --self-check` 或读取已有 `selfcheck.json`，确认 `pass` 或明确 `warn` 原因。
  2. 逐项核对 `/app/output/result.json` 存在且 JSON 合法；包含 `case_id` 和全部 `output_contract` 字段（键名不改，缺值用 `null`/`[]`）。
  3. 确认伴随文件 `candidates.csv`、`query_log.json`、`query_log.json