---
name: research-question-retrieval
description: >-
  科研问题驱动检索 Skill：把复杂科研问题拆为可检索子问题（对象/机制/方法/时间/比较/证据要求），
  在给定文献快照上规划多波查询和术语扩展，执行全记录筛选、去重保留映射、排序并输出可复核证据集。
  输出包含 result.json 双回显、trace.jsonl、query/screening/coverage/conflict/pending_human/errors/degradations。
  适用于科研文献检索、证据集构建和检索过程审计；不做单篇精读、全文翻译、写作润色或开放式科研问答，
  不联网、不假装实时数据库或全局召回。
version: 2.0.0
---

# research-question-retrieval

## 1. 触发与边界

触发条件：
- 任务要求围绕科研问题检索、筛选文献并保留筛选依据；
- 输入包含研究问题、文献快照或结构化题录，要求输出候选文献、查询日志、筛选日志、覆盖与遗漏说明；
- 评审或用户需要独立复核每条结果的来源、相关性和停止理由。

明确边界：
- 只处理 `/input` 中的有限快照；不访问互联网，不查询实时数据库。
- 不声称“最新”“全部数据库”“全局召回”；不把有限快照当完整科学证据。
- 不做单篇精读、全文翻译、写作润色、开放式科研问答。
- 不生成不存在文献、DOI、元数据、引用计数、人工复核或评分分数。
- 不以文件名、错误领域标签或预置答案代替原文内容。

## 2. 主命令、工作目录与双路径

主命令全流程：
`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

内部必须完成：
- `init`：盘点 `/input` 材料，分配来源编号 `[S#]`，生成候选抽取、冲突分组、术语/查询规划；写 `${WORK}/ledger.json`。
- `build`：校验已有 `draft.json`；若无 draft，则用 init 台账做确定性兜底抽取；渲染全部产物；finalize `result.json`。
- `selfcheck`：校验 result.json、trace、candidates、coverage 的契约一致性与计数；写 `selfcheck.json`。

任何异常都必须 `exit 0`；异常进入 `result.errors[]` 或 `result.degradations[]`，不得中断所有产物。

Agent-first 路径：
1. 运行 `python3 -B scripts/main.py init --input /input --output /app/output --work /app/work`。
2. 阅读 `${WORK}/ledger.json` 与 `/input` 中真实材料。
3. 将判断写入 `${WORK}/draft.json`：子问题、include/exclude/defer、证据 quote、locator、排序分项、缺口与冲突处理。
4. 运行 `python3 -B scripts/main.py check --input /input --output /app/output --work /app/work`；
   若 check 失败，只改 draft 或调用脚本修复，不手改最终结构化 JSON。
5. 运行 `python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`。

确定性兜底路径：
- 当 `${WORK}/draft.json` 不存在，或预算不足，或 Agent 无法逐条核验时，直接使用主命令 `run`。
- build 必须基于 init 台账做确定性抽取，逐字 quote 加 locator，并把 `AUTO_EXTRACT` 诚实写入 `degradations[]` 或 `coverage.gaps[]`；禁止把自动兜底写成人工核验。

兼容性：
- 如果已安装脚本不支持 `run` 子命令，则先调用旧入口
  `python3 -B scripts/main.py --input /input --output /app/output --max-queries 24 --self-check`
  做基线，再执行或模拟上述相同产物和契约；不得因接口不同而丢失 result.json、trace.jsonl 或输出契约字段。

## 3. 输出目录与文件清单

最终实际产物在 `/app/output`。既包括结构化结果，也包括可编辑/可检查文本：
- `result.json`：最终契约结果，包含原始输出字段、双回显和状态。
- `candidates.csv`：候选文献表，一行一条候选，保留来源与证据。
- `query_log.json` / `query_log.jsonl`：查询计划与执行记录。
- `trace.jsonl`：每一步实际查询、结果 ID、策略调整、证据缺口、停止理由。
- `screening_log.csv`：所有记录的筛选、去重、排除/保留决定。
- `coverage.csv`：子问题覆盖情况。
- `conflicts.json`：冲突证据与未解决冲突。
- `pending_human.json`：需要人工判断项。
- `agent_review.json`：Agent 核验和修改记录（若使用 Agent 路径）。
- `selfcheck.json`：产物自检结果。
- `deliverable.md` 或 `evidence_driven_draft.md`：若 output_contract 要求正文型交付物。所有数字/结论必须带 `[S#]` 和 locator。

如果 output_contract 要求其他文件，必须按题面字段生成对应文件，并把文件路径写入 `result.outputs[]`。

## 4. 输入读取与材料解析

1. 先列出 `/input` 下所有文件；读取 `/input/task.md` 和 `/input/case.json`。
2. 识别材料类型：JSON/JSONL/CSV 记录、PDF、DOCX、图片等。不得按文件名猜测内容。
3. 有结构化题录时，保留原始字段及原始别名；`result.sources[]` 记录来源文件、来源编号、解析方法、材料摘录。
4. 有 PDF 时，调用 `environment/resources.yaml` 中预装工具或平台 PDF 解析工具，提取真实正文和题录，不使用预提取答案层。
5. 有 DOCX 时按 docx/text 提取；有图片时若有 OCR 能力则 OCR，否则标记不可读。
6. 解析结果写入 `${WORK}/extracted_records.jsonl`，失败写入 `errors[].stage=parse_material` 或 `degradations[]`，不中止。

本题固定案例提供九篇真实署名论文；必须逐条核验这些论文的元数据、来源页码/段落、相关性、纳入/排除理由、排序分项；原始记录全覆盖，去重仍保留映射。

所有后续证据必须以这些真实解析记录为准；缺失元数据保留原值、用 `null` 或 `unknown` 填空，并记录在 `uncertainty` 或 `pending_human`。

## 5. 问题拆解与范围

必须从原始研究问题中显式识别以下要素：
- 研究对象；
- 机制/通路；
- 方法或研究设计；
- 时间范围；
- 比较关系；
- 证据要求。

输出 `sub_questions[]`，每个子问题包含：
- `id`；
- `text`；
- `question_field`：object/mechanism/method/time/comparison/evidence_requirement/limit；
- `evidence_requirement`；
- `wave`：初始可并行/后续依赖；
- `depends_on`：前置子问题或查询。

子问题数量一般不超过 6 个；如需更多，必须说明理由。子问题要可检索、可核验；不得只复制原问题，不得空泛。

## 6. 查询规划与术语扩展

为每个子问题设计查询计划，并形成“子问题—查询依赖—证据缺口”表：
- `query_id`
- `sub_question_id`
- `wave`
- `depends_on`
- `query_text`
- `term_expansions[]`：包含术语、来源（原文词、同义词、缩写、上位/下位、领域变体）、语言。
- `term_expansion_source`：依据哪条原文或已知领域词表；无依据不扩展。
- `scope_boundary`：该查询覆盖/不覆盖什么。
- `expected_record_scope`：在输入快照中预期的记录范围。
- `evidence_gap_after`：本轮后仍缺什么证据。
- `next_action`：下一轮只处理缺口或冲突，不重复已覆盖查询。
- `stop_condition`：达到该条件的判定。

查询必须记录实际输入和执行，不应与日志脱节。无效查询也要保留。

## 7. 全记录筛选、去重与排序

对输入快照中的每条记录都必须处理，不得静默丢弃。

- 每个原始记录分配 `source_id` 和 `record_id`；经过解析的九篇真实论文或其他记录都要登记。
- 先做去重：给定 canonical_id；重复记录在 `duplicate_mapping[]` 中保留 `original_ids[]`、重复原因、合并依据。去重后仍能追溯每条原始导出。
- 对每个 canonical record 给出筛选决定：
  - `include`：直接相关，进入候选集；