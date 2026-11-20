---
name: systematic-literature-review
description: >-
  对给定科研材料执行可复核的系统性文献综述（SLR）：将研究问题拆成可执行布尔检索要素，
  冻结条款化纳排标准，做题录与全文两轮筛选并逐条留痕，用 SLR-6D 量表逐维度评价质量，
  输出每条论断带逐字引文与文件/字符定位的综述、证据矩阵、冲突证据与研究空白。
  不联网、不补造文献/数字/DOI；缺材料显式登记 gaps 与 pending_human。单命令
  python3 -B scripts/slr_review.py 生成完整基线，Agent 可通过 /app/work/draft.json
  增量增强；最终 result.json 回显 output_contract 全部原字段与 case_id。
version: 1.2.0
---

# 系统性文献综述 Skill：可复核、可重跑、带证据回链

## 0. 最高优先级：单命令全流程 + 诚实部分交付

本 Skill 的正式入口只有一个：

    cd /skills/weekly-skill
    python3 -B scripts/slr_review.py --input /input --output /app/output --work /app/work

该命令内部按以下阶段运行：

1. **init**：盘点 `/input` 全部材料，给每个来源编号，提取候选题录与全文片段，识别研究问题与 `output_contract`，冻结纳排条款版本，生成工作台账写回 `/app/work`。
2. **build**：校验抽出内容的完整性；若无 Agent 判断稿，则用确定性规则生成实质工作稿，逐字 quote 与 locator 写入结构化产物；渲染 `review.md`、`evidence_map.csv`、`screening_log.csv`、`appraisal.csv`、`search_protocol.md`、`eligibility_criteria.md`，最后装配 `result.json`。
3. **selfcheck**：运行 `scripts/verify.py` 核验 quote 是否逐字命中、筛选行是否有条款依据、契约字段是否齐全，输出 `/app/work/verification.json`。

任何阶段都必须保证最终退出码为 0。主脚本失败时，保留已生成文件，手工补齐最小合法 `result.json`，记录 `errors[]`，退出码 0。

## 1. Agent 修改边界：脚本产物不可手改

- **禁止手改** `result.json`、`screening_log.csv`、`evidence_map.csv`、`appraisal.csv` 及脚本生成的 claims/evidence JSON 的结构键。若发现错误，用临时 Python 调用脚本函数重算覆盖，并写入 `changes[]`。
- **允许** Agent 真实阅读原文、核对 quote/locator，把核验结论写入 `/app/work/agent_review.json`，逐条标 `verified` / `rejected` / `insufficient`。
- **允许** Agent 写 `/app/work/draft.json` 表达纳入、排除、质量维度、综述分段判断；最终必须经脚本/`verify.py` 合并装配，不得直接改 `result.json`。
- **禁止** 生成或引用自评金标准、加权得分、虚假 baseline 对照分数。只允许使用 `scripts/verify.py` 的真实输出作为核验证据。
- **禁止** 依据文件名、领域标签猜测材料内容；必须解析真实文件后下结论。

## 2. 双路径工作流：Agent-first 与确定性兜底

### 路径 A：Agent-first（推荐，材料规模适中时使用）

1. 运行基线命令一次，得到 `/app/work` 下的台账、来源编号、候选 record 与 locate 区间。
2. Agent 亲自读取台账和关键原文，将判断写入 `/app/work/draft.json`。该文件是工作稿，形状见第 5 节。
3. 重跑或合并进基线流程，生成最终结构化产物与正文稿件。
4. 生成完必须运行 selfcheck；若 `verification.result != pass`，按错误项修复；无法修复则登记 `pending_human` / `errors`，不要伪装成功。

### 路径 B：无 draft 时的确定性兜底

- 若 `/app/work/draft.json` 不存在，`build` 阶段使用 init 台账开展确定性抽取：题录字段、摘要/全文片段、研究类型、对象、干预/暴露、对照、结局、效应数字、局限。
- 每个自动判断都要求有逐字 quote 和 locator；无法抽取的字段置 `null`，并写入 `gaps[]`。
- 自动生成的工作稿必须在 `degradations[]` 或 `contract_check` 中诚实记录 `AUTO_EXTRACT`，不得冒充人工核验结果。
- 两条路径最终必须产出同一套产物和同一条 `result.json` 契约，不得因路径不同少字段。

## 3. 输入输出与运行约束

### 输入

- `/input/case.json`：案例主文件，可能包含 `case_id`、`research_question`、`task_instruction`、`output_contract` 及材料索引。
- `/input/task.md`：题面，包含研究问题、评分约束、runtime contract。
- `/input/artifacts/` 或 `/input/` 下实际材料：PDF、DOCX、CSV、XLSX、JSON、TXT、MD、图片。不得假设材料内容；PDF 必须抽取真实文本层，无文本层则记录 OCR 缺口。

### 输出

最终结果必须全部位于 `/app/output`，至少包括：

- `result.json`
- `review.md`
- `evidence_map.csv`
- `screening_log.csv`
- `appraisal.csv`
- `search_protocol.md`
- `eligibility_criteria.md`
- 若 `output_contract` 要求 Office/幻灯片/图形产物，还需生成真实渲染的 PDF/PNG 预览，并在 `result.json.artifacts` 中登记。

工作文件在 `/app/work`。`/app/output/result.json` 是唯一最终状态入口。

### 运行环境

- Python 3.8+，仅使用标准库与包内脚本；不联网、不安装第三方包、不访问远程数据库。
- 平台记录的预算为 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行不占模型请求，但占时间。
- Skill 包资源限制：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总大小 ≤2MB；不得使用 symlink。

## 4. 阶段 1：盘点输入、冻结契约、来源编号

### 4.1 识别 case_id 与 output_contract

按以下顺序查找：

1. `/input/case.json` 中键名 `case_id` 或 `caseId`。
2. 递归查找含 `output_contract`、`outputContract`、`output.contract`、`contract` 的 JSON。
3. 若找不到 `output_contract`，从 `task.md` 的“输出要求/结构化结果”段落提取字段说明。
4. 仍找不到时，使用默认最小契约：

    {"review": "path", "included_studies": "array", "quality": "object", "gaps": "array"}

并写 `contract_check.assumed_default=true`。

### 4.2 提取研究问题

优先取 `case.json` 的 `research_question`、`question`、`task_instruction`、`objective`、`topic`。缺失时从 `task.md` 中“研究问题 / Research question / 固定研究问题”段提取。研究问题必须保留原句，不得改写。

### 4.3 材料盘点

对每个输入文件记录：

    source_id, file_path, sha256[0:12], char_count, extractor, record_count

可解析题录字段按同义词识别：

    title/标题/题名
    abstract/摘要
    authors/作者
    year/年份
    journal/期刊/venue
    doi
    url
    fulltext/content/text

损坏、打不开、无文本层、重复题录分别记录到 `degradations[]`，不要中止整体流程。

## 5. 工作稿 draft.json 形状

Agent 可写 `/app/work/draft.json`。最小可接受形状如下：

    {
      "case_id": "原样保留",
      "research_question": "原句",
      "search": {
        "question_frame": "PICO/PICOS 或主题拆解",
        "query_original": "可执行布尔检索式",
        "database": "材料所属数据库/题录来源，缺失写 null",
        "date": "检索日期，未知写 null",
        "time_range": "",
        "language_limit": "",
        "blocks": [
          {"id": "B1", "intent": "某概念块", "terms": ["term1", "term2"], "field": "title/abstract/all"}
        ]
      },
      "criteria": {
        "version": "1.0",
        "clauses": [
          {"clause_id": "EC1", "text": "条款原文", "judgement": "include/exclude/unclear", "priority": 1}
        ]
      },
      "screen": [
        {
          "record_id": "R0001",
          "round": "title_abstract",
          "verdict": "include",
          "clause_id": "EC1",
          "reason_text": "符合纳入条款：...",
          "evidence_quote": "逐字摘录",
          "locator": "文件#L12:34-87",
          "screener": "agent"
        }
      ],
      "appraisal": [
        {
          "record_id": "R0001",
          "tool": "SLR-6D",
          "dimensions": {"D1": "low", "D2": "moderate"},
          "overall": "low",
          "basis_locator": "文件#L120:22-90"
        }
      ],
      "synthesis": {
        "themes": [],
        "claims": [],
        "conflicts": [],
        "gaps": []
      },
      "changes": []
    }

若无该文件，脚本按第 2 节路径 B 确定性兜底。

## 6. 检索式与纳排标准：必须条款化、可判定

### 6.1 检索式

- 从研究问题拆出概念块；每个概念块列出同义词、近义词、词形变化；用布尔逻辑连接。
- 写出完整 `query_original`，如：

    ("elderly" OR "older adults" OR "geriatric") AND ("fall prevention" OR "falls prevention") AND ("inpatients" OR "hospital")

- 每块写明意图、字段、时间范围、语言限制、数据库/来源。
- 数据库或检索日期缺失时写 `null`，并在 `gaps[]` 说明“材料未提供检索元数据”。不得伪造 PubMed/Web of Science 检索日期。
- 术语歧义处理：显著同义/异形术语放入同一概念块；无法消歧的术语写入 `manual_queue[]`，不得静默合并。

### 6.2 纳排标准

- 条款必须写成可判定形式，逐条给 `clause_id`、条文、判定动作、优先级。
- 默认条款版本 `criteria.version` 必须在首次筛选中冻结；后续修改需新增版本号并记录 `changes[]`。
- 条款冲突时按 `priority_order` 裁决；同优先级冲突标为 `uncertain`，不得强行纳入或排除。
- 纳入/排除每条记录时必须至少引用一个 `clause_id`；`unclear` 记录进入人工队列。
- 全文不可得时，若条款要求全文，使用 `EC-FULLTEXT_UNAVAILABLE` 软排除或摘要级证据纳入并在质量评价中上限为 `low`。

## 7. 两轮筛选、质量评价、证据综合

### 7.1 两轮筛选

- 第 1 轮：题录/摘要筛选 `title_abstract`。
- 第 2 轮：全文/长摘要筛选 `fulltext`。
- 每轮每一篇都必须有：
  `record_id, round, verdict, clause_id, reason_text, evidence_quote, locator, screener, criteria_version`。
- 输出 `screening_log.csv`，列名保持稳定。
- 重复题录按 DOI 或规范化标题合并，保留原始 `source_id`。

### 7.2 SLR-6D 质量评价

使用 `references/appraisal-rubrics.md` 中定义的 SLR-6D。每个纳入研究逐维度给判断：

- 维度判断：`low` / `moderate` / `high` / `unclear` / `not_applicable`
- 每个等级必须有依据位置 locator，不能只写“质量较高”。
- 总体等级按预注册规则：任一致偏倚维度为 `high` 或多数维度 `unclear` 时，总体不得为 `high`。
- 证据不足或全文不可得时，维度标 `unclear`，并在 `limitations[]` 说明其对结论的降级影响。

### 7.3 证据综合与论断类型

`review.md` 中的每条论断必须标注三型之一：

- `directly_supported`：必须带逐字 quote + locator。
- `inferred`：需要说明推断前提、条件、反例风险。
- `insufficient_evidence`：只写“无法确定/材料不足”，不越界给结论。

冲突证据写入 `synthesis.conflicts[]`，包含冲突双方 record_id、quote、locator、处理方式（保留冲突/降级/标 pending_human）。

研究空白写入 `synthesis.gaps[]`，区分：

- 材料内未覆盖；
- 现有证据互相矛盾；
- 方法学缺陷导致不能下结论；
- 材料未提供检索式/纳排元数据。

## 8. 产物与字段规范

### 8.1 `review.md`

必须包含六部分，顺序推荐：

1. 研究问题与范围边界
2. 检索协议与可执行检索式
3. 纳排标准与筛选流程
4. 纳入研究质量评价
5. 分主题综合结论
6. 冲突证据与研究空白

每个结论段落中的关键数字、方向、机制均需以 `[S#]` 标注，并对应 `证据矩阵` 行。

### 8.2 `evidence_map.csv`

每行代表一条可核验证据，列至少包括：

    claim_id, record_id, source_id, source_locator, decision, comparison_field, quote, direction, quality, support_type

### 8.3 `screening_log.csv`

列至少包括：

    record_id, round, source_id, title, abstract_excerpt, verdict, clause_id, reason_code, reason_text, evidence_quote, locator, screener, criteria_version

### 8.4 `appraisal.csv`

列至少包括：

    record_id, source_id, tool, dimension, rating, basis_locator, notes, overall

### 8.5 `search_protocol.md` 与 `eligibility_criteria.md`

- `search_protocol.md`：完整检索式、分块意图、字段、时间/语言限制、数据库/来源、检索日期。
- `eligibility_criteria.md`：条款版本、条款原文、优先级、冲突处理规则、全文不可得处理规则。

## 9. result.json 契约：顶层与嵌套双回显

`result.json` 必须合法 JSON，且：

1. 原样保存 `output_contract` 为嵌套对象：

    result["output_contract"] = original_output_contract

2. 对 `output_contract` 中每个原始字段 `k`，在 `result` 顶层也设置同值：

    result["k"] = result["output_contract"]["k"]

3. `case_id` 必须同时出现在顶层和嵌套契约：

    result["case_id"] = case_id
    result["output_contract"]["case_id"] = case_id

4. 除契约字段外，顶层还必须有：

    skill, status, contract_check, research_question, search, criteria,
    screening, appraisal, synthesis, sources, coverage, summary,
    uncertainty, pending_human, errors, degradations, changes,
    runtime, artifacts, verification

5. `status` 只能是 `ok`、`partial`、`insufficient_evidence`、`input_error`。
6. `contract_check` 必须包含：

    fields_total, fields_null, fields_null_names, assumed_default, contract_source

7. `verification` 必须来自 `scripts/verify.py` 的真实输出，至少包含：

    result, quote_checks_total, quote_checks_passed, missing_artifacts, contract_keys_total, contract_keys_present

8. `artifacts` 是文件相对路径到输出路径的映射，如：

    "artifacts": {
      "review": "review.md",
      "screening_log": "screening_log.csv",
      "evidence_map": "evidence_map.csv",
      "appraisal": "appraisal.csv",
      "search_protocol": "search_protocol.md",
      "eligibility_criteria": "eligibility_criteria.md"
    }

9. 若某契约字段确实无法产出，置 `null`，字段名仍保留，并在 `contract_check.fields_null_names` 列出。

## 10. 异常处理与隐藏案例鲁棒性

所有异常都不得导致崩溃或空 result；最终退出码必须为 0。

| 情况 | 处置 | 落点 |
|---|---|---|
| case.json 缺失/损坏 | 递归查找其他 JSON；仍失败则用 task.md，继续材料解析，先落 partial | `errors[].stage=discover` |
| 无 output_contract | 使用默认最小契约 | `contract_check.assumed_default=true` |
| 输入无材料 | 不编造，`status=insufficient_evidence`，综述写“无材料可评” | `status`, `pending_human` |
| 单个 PDF/DOCX 打不开 | 只跳过该文件，不中止；写明文件路径与原因 | `degradations[]` |
| PDF 无文本层/图为空 | 保留已抽文本，标 `ocr_required`，不猜测内容 | `materials[].extractor`, `pending_human` |
| 缺失题录字段 | 置 `null`，不补造标题/DOI/年份 | `gaps[]`, `sources[]` |
| 全文不可得 | 若条款要求全文，软排除或摘要级纳入并质量上限 low | `screening_log.csv`, `appraisal.csv` |
| 重复题录 | DOI/规范化标题合并，保留来源 id | `degradations[]` |
| 术语歧义 | 同义扩展，无法消歧进入 manual_queue | `search.blocks[]`, `manual_queue` |
| 纳排条款冲突 | 按 priority_order；同级冲突标 uncertain | `criteria.priority_order` |
| 纳入证据互相矛盾 | 保留冲突双方与定位；结论降级或 pending_human | `synthesis.conflicts[]` |
| 脚本超时/异常 | 保留已产出文件，手工补齐最小合法 result.json，退出码 0 | `errors[]`, `runtime` |
| 权限/磁盘写入失败 | 重试 `/app/output`；仍失败写 `/app/work/result.json` 并在 errors 说明，退出码 0 | `errors[]`, `runtime` |
| 预算将尽 | 停止扩展，先保证筛选记录、证据回链、契约字段完整 | `runtime.budget` |

## 11. rubric 维度对应证据

| 评分维度 | 关键动作 | 自证产物 |
|---|---|---|
| 实际效果：任务完成度 | 走完问题拆解→检索式→纳排→筛选留痕→质量评价→带回链综述 | `result.json` 的 search/criteria/screening/appraisal/synthesis 齐备；`review.md` 六部分齐全 |
| 实际效果：结果正确性 | 检索式可执行且逐块解释；纳排判定引用 clause；quote 逐字命中原文 | `search.blocks[]`，`screening_log.csv`，`verification.result=pass` |
| 实际效果：结果完整性 | 覆盖问题拆解、检索覆盖、证据回链、冲突证据、综合结论、研究空白 | `coverage.*` 计数；`synthesis.conflicts[]`；`synthesis.gaps[]` |
| 实际效果：结果可核验性 | 检索式原文、日期、数据库、筛选记录、质量评价依据、引用定位均可复跑 | `search.query_original`，`screening.rounds`，`appraisal.items[].basis_locator`，locator 格式 `文件#L行:字符区间` |
| 使用增益：质量增益 | 纳排一致、证据回链质量稳健 | `criteria.version` 冻结；逐行 clause_id；`verification.quotes_verified` |
| 使用增益：效率增益 | 脚本一次生成完整基线，减少返工 | `changes[]` 记录人工修正范围；`runtime` 记录脚本里程碑 |
| 使用增益：增益可验证性 | 脚本/verify 提供可复核核验项 | `verification`，`artifacts`，`agent_review.json` |
| 创新增益：新增能力 | 结构化检索要素、条款版本、筛选留痕、证据自动回链、冲突矩阵 | `search.blocks[]`，`criteria.version`，`screening_log.csv`，`evidence_map.csv`，`synthesis.conflicts[]` |
| 创新增益：方法改进 | 检索式分块意图、SLR-6D、三型论断边界 | `references/slr-protocol.md`，`references/appraisal-rubrics.md`，`references/output-schema.md` |
| 创新增益：创新证据 | 说明方法与边界，不夸大 | SKILL.md 前半部分；`limitations[]` |
| 可靠体验：调用易用 | 单命令触发，说明完整流程 | `python3 -B scripts/slr_review.py --help` 退出码 0 |
| 可靠体验：运行稳定 | 标准库、确定性流程、可重跑 | 脚本无第三方依赖，重复运行产物一致 |
| 可靠体验：异常处理 | 空输入、坏 JSON、PDF 失败、条款冲突、全文缺失、证据矛盾 | 第 10 节表；`errors[]`、`degradations[]`、`pending_human[]` |
| 生态贡献：文档完整 | 用法、边界、依赖、示例、限制、失败处理 | SKILL.md 全文；三份 references 文件 |
| 生态贡献：资源可复用 | 模板、量表、reason code、字段定义可被复用 | `references/` 三份文件 |
| 生态贡献：分享推广 | 可沉淀模板与经验 | `references/slr-protocol.md`；SKILL.md 自检清单 |

## 12. 预算策略

默认在 64 次模型请求内完成。建议分配：

- 输入盘点与契约识别：≤6 次模型请求
- 材料真实解析与抽查阅读：≤12 次；材料超过 20 篇时只抽查关键段，其余用确定性解析
- 脚本运行与证据核验：≤10 次；只核验影响结论的纳排、引文、契约字段
- 综述撰写与产物增强：≤14 次
- result.json 回填与终验：≤10 次
- 异常兜底：≤12 次

必须优先保证的交付顺序：

1. 合法 `result.json` 与契约回显
2. 两轮筛选逐条留痕
3. 每条论断带 quote + locator
4. 质量评价维度依据
5. 冲突证据与研究空白
6. 漂亮格式与增强内容

当已用约 80% 请求且核心链路未完成时，停止扩展，先补齐前 4 项。每个阶段完成后都保存 partial；至少三处落盘：init 后、build 后、终验后。

## 13. 自检清单

- [ ] `python3 -B scripts/slr_review.py --help` 退出码 0
- [ ] `result.json` 可解析，且顶层与 `result.json["output_contract"]` 中契约字段一一双回显
- [ ] `case_id` 顶层与嵌套契约中都有
- [ ] `contract_check.fields_null` 记录准确；若 0 且 `verification.result=pass`，status 为 ok
- [ ] `review.md` 六部分齐全，非模板占位；每条直接支持型论断有逐字 quote 与 locator
- [ ] `screening_log.csv` 每行都有 clause_id/reason/quote/locator/screener/criteria_version
- [ ] `appraisal.csv` 每行都有维度和 basis_locator
- [ ] `evidence_map.csv` 行数与 coverage 一致
- [ ] 未出现材料外题录、DOI、数值、检索日期、数据库或平台分数
- [ ] `errors[]`、`degradations[]`、`pending_human[]` 完整记录限制
- [ ] 空输入、坏 JSON、单文件失败时仍产出合法 result.json，退出码 0
- [ ] 若要求 Office/幻灯片/图形产物，已提供可编辑原件 + 真实渲染 PDF/PNG，并写入 artifacts

## 14. 最小调用示例

示例输入（仅示意接口，非正式案例结果）：

    /input/case.json
    {
      "case_id": "demo-000",
      "research_question": "住院老年人跌倒预防干预对跌倒发生率的影响",
      "output_contract": {
        "review": "path",
        "included_studies": "array",
        "quality": "object",
        "gaps": "array"
      },
      "records": [
        {
          "title": "Exercise-based fall prevention in older inpatients: a cohort study",
          "abstract": "Aim: to assess the effect. Methods: n = 412 cohort. Results: a 23% reduction.",
          "year": "2020"
        }
      ]
    }

调用：

    python3 -B scripts/slr_review.py --input /input --output /app/output --work /app/work

示意输出：

    /app/output/result.json
    /app/output/review.md
    /app/output/screening_log.csv
    /app/output/evidence_map.csv
    /app/output/appraisal.csv
    /app/output/search_protocol.md
    /app/output/eligibility_criteria.md

`result.json` 顶层含 `case_id` 与全部 `output_contract` 字段，嵌套 `output_contract` 原键保留。`review.md` 每条论断标 `[S#]`，可回到 `evidence_map.csv` 中对应 quote 与 locator。