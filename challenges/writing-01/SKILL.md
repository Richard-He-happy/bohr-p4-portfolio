---
name: writing-01-academic-writing
description: >-
  学术论文写作完整可核验 Skill。Agent 必须真实读取并解析 /input 中的科研材料，依据材料完成可编辑章节稿、证据映射、保留事实、修改记录与诚实 result.json。
  单命令入口：python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work。
  确定性兜底 + Agent draft 双路径，产出同一套契约。适用于从固定科研案例材料生成“写得实、引得对、全得起来、改得动”的学术写作产物。
version: 7.0.0
---

# writing-01 学术论文写作：完成产物，也保留来源

## 0. 最高执行原则（先读，不可违背）

1. **单命令全流程入口优先。** 在任何可用情况下，第一步运行：

       python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work

   该命令内部完成 init → build → selfcheck，并生成基线交付物。Agent 后续工作是在基线之上核验、补强，不是推翻结构。

2. **任何情况退出码必须为 0。** 材料缺失、解析失败、脚本失败、输出目录不可写、JSON 损坏、超时等，都要落盘诚实 partial 结果并退出 0。

3. **真实性优先。** 不编造数字、单位、样本量、p 值、误差、显著性标记、图注、作者、年份、期刊、DOI、结论或数据。材料不足、冲突、无法确认的内容显式记为 `pending_human`、`uncertainty`、`gaps`、`degradations`。

4. **最终成品必须是可编辑的完整稿件，不是写作建议、提纲或素材堆叠。** 每个关键事实、数字、引用、图注必须能通过证据映射回到来源定位。

5. **Agent 路径与确定性兜底路径必须产出同一套产物与同一份 result.json 契约。** 若 Agent 写了 `/app/work/draft.json`，build 使用 draft；若没有 draft，build 必须依据 init 台账确定性抽取证据，生成实质工作稿，并把 `AUTO_EXTRACT` 诚实写入 `degradations`。

6. **不生成无依据的 benchmark 分数、golden score 或自评高分。** 只记录真实运行状态、计数、耗时、来源与不确定项。

7. **预算意识。** 官方执行预算为 64 次模型请求、900 秒、单次响应 16384 tokens（含推理）。先完成完整交付，再增量改进；每完成一个阶段就把 partial 结果写盘。

---

## 1. 用途与边界

本 Skill 用于学术论文写作任务：读取事实底稿、实验记录、图表、参考文献、任务约束，完成指定生成、改写、校对、格式整理、引用管理、双语或结构化写作动作。

核心目标对应四个要求：

- **写得实**：稿件中的数值、单位、样本量、图注和结论来自给定材料与真实文献，不新增材料外事实。
- **引得对**：每条引用真正支撑所在论断，作者、年份、期刊、DOI 等信息来自材料，缺失时显式标注。
- **全得起来**：学科模板与任务要求的关键章节、图表、参考文献、声明字段齐备，缺项显式登记。
- **改得动**：保留章节层级、图注编号、引用格式，作者可继续在 Word 或 Markdown 中修改并逐条复核。

边界：

- 不生成材料外数值、文献条目、实验数据或结论。
- 不依赖互联网检索。
- 不假设文件名或领域标签等于内容；必须读取实际文件。
- 不依赖作者未说明的个人文件、手工操作或预制答案。
- 纯标准库、离线运行，Python ≥ 3.8。

---

## 2. 运行时契约

### 2.1 输入

- `/input/case.json`：必需。含 `case_id`、`task_instruction`、`output_contract`、`source` 等字段。
- `/input/task.md`：通常存在。描述体裁、受众、章节、格式、引用、字数、声明等要求。
- `/input` 下其他材料：PDF、DOCX、CSV、XLSX、PPTX、图片、文本等。必须实际读取，不得只看标签。

### 2.2 工作目录与输出

- 工作目录：`/app/work`。
- 最终产物：`/app/output`。
- `/app/output/result.json` 必须存在且合法，包含原 `output_contract` 全部字段与 `case_id`。
- 可编辑 Office、幻灯片、图形产物如需交付，必须同时给出真实渲染的 PDF/PNG 预览，供评审检查。

### 2.3 result.json 双回显

- 原 `output_contract` 中的每个字段，必须同时在 result.json **顶层**和 **`output_contract` 嵌套对象**中各出现一次。
- 顶层与嵌套值必须一致；如原字段缺失或无法完成，置 `null`，并在 `change_log` 与 `degradations` 说明。
- `output_contract` 可能包含但不限于：

      case_id
      deliverable
      preserved_facts
      evidence_map
      change_log

  实际字段以 `/input/case.json` 中的 `output_contract` 为准，不得删改键名。

- result.json 还必须包含：

      case_id
      status
      sources
      uncertainty
      pending_human
      errors
      degradations
      output_contract

- `status` 取值为 `complete`、`partial` 或 `input_error`。

---

## 3. 工作流与命令

### 3.1 单命令入口

    S=/skills/weekly-skill
    python3 -B "$S/scripts/main.py" run --input /input --output /app/output --work /app/work

`run` 内部必须依次完成：

1. **init**：盘点材料、生成来源编号、抽取候选事实、识别冲突、生成契约检查表。
2. **build**：校验 draft 或确定性兜底抽取，渲染全部产物，写入 result.json。
3. **selfcheck**：检查 result.json 契约、证据 locator、文件存在性、preview 存在性、退出码。

### 3.2 Init：材料盘点与候选抽取

init 阶段写入 `/app/work` 的文件：

- `material_index.json`：材料索引。
- `sources.json`：来源编号与可读性状态。
- `evidence_candidates.json`：候选事实句。
- `conflicts.json`：口径冲突分组。
- `contract_checklist.json`：输出契约与章节要求检查项。
- `run_log.jsonl`：步骤、耗时、异常、降级记录。

`source_id` 必须稳定、简短、唯一。每个来源记录至少包含：

    {
      "source_id": "mat1",
      "path": "/input/xxx.pdf",
      "type": "pdf",
      "bytes": 123456,
      "sha256": "...",
      "readable": true,
      "extracted_text_path": "/app/work/extracted/mat1.txt",
      "pages_or_rows": 12
    }

候选抽取规则：

- 对数字、单位、样本量、p 值、误差、显著性标记、作者、年份、期刊、DOI 建立候选。
- 每条候选必须带 `quote` 逐字原文与 `locator`。
- 冲突分组：同一变量数值不一致、图表与正文不一致、文献字段不一致、材料间说法冲突。

### 3.3 Agent 路径：阅读材料并写 draft

如果 Agent 有预算，应按以下路径增量改进：

1. 运行 init，读 `/app/work/material_index.json`、`evidence_candidates.json`、`conflicts.json`。
2. 真实读取 `/input` 中的实际材料与 `/app/work/extracted/` 提取文本。
3. 核验候选 `quote` 是否逐字命中；修正 locator；补录遗漏。
4. 写 `/app/work/draft.json`，格式见 `references/guide.md`。
5. 运行 check 校验 draft。
6. 运行 build 生成最终产物。
7. 运行 selfcheck；不通过则修复或降级。

`draft.json` 至少包括：

    {
      "case_id": "...",
      "task_extraction": {
        "genre": "...",
        "audience": "...",
        "sections_required": [],
        "citation_style": "...",
        "length_constraint": "...",
        "format_constraint": "..."
      },
      "manuscript_plan": [],
      "preserved_facts": [],
      "evidence_map": [],
      "reference_map": [],
      "missing_materials": [],
      "conflicts": [],
      "pending_human": [],
      "output_contract_completion": {}
    }

### 3.4 Check 校验

check 阶段至少校验：

- 每条正文关键论断是否在 `evidence_map` 中有 `claim_id`、`source_id`、`locator`、`quote`。
- `quote` 是否逐字出现在提取文本中。
- 所有 `output_contract` 字段是否已分配产物或显式置 `null`。
- 数字、引用、图注是否能在来源中命中。
- 章节缺项是否登记。

未命中的 `quote` 必须记入 `quotes_rejected`，不得强行通过。

### 3.5 Build 渲染产物

build 阶段必须生成：

- 可编辑主产物，默认 `/app/output/manuscript.md`；若任务要求 DOCX/PPTX/图，应生成对应可编辑文件。
- `/app/output/evidence_map.json`
- `/app/output/preserved_facts.json`
- `/app/output/change_log.json` 与 `/app/output/change_log.md`
- `/app/output/pending_human.json`
- `/app/output/gaps.json`
- `/app/output/result.json`
- 如需 Office/图，生成 `/app/output/previews/` 下真实 PDF/PNG 预览。

### 3.6 无 draft 的确定性兜底

以下情况使用确定性兜底：

- `/app/work/draft.json` 不存在；
- draft.json 不合法；
- draft.json 内容为空或关键字段缺失。

兜底规则：

- 使用 init 台账中的候选事实与来源定位，生成实质工作稿。
- 所有关键事实必须保留逐字 quote 与 locator。
- 不允许把空模板、占位文字或仅标题大纲当作交付物。
- 在 `result.json.degradations` 中记入 `AUTO_EXTRACT`，说明“由确定性兜底生成，未经 Agent 逐条增强”。
- 若材料不足，不能写实的内容应保留为缺口段落，并显式标注“材料未覆盖 / 待作者确认”。

### 3.7 脚本失败兜底

若 `scripts/main.py` 不可用或 `run` 子命令不存在：

    python3 -B "$S/scripts/main.py" init
    # Agent 自行阅读并写 /app/work/draft.json
    python3 -B "$S/scripts/main.py" check
    python3 -B "$S/scripts/main.py" build
    python3 -B "$S/scripts/main.py" selfcheck

若脚本完全不可用，Agent 必须手工完成等效动作，并写合法 result.json。所有失败诚实记录到 `errors` 与 `degradations`。

---

## 4. 证据模型与定位格式

### 4.1 证据项 schema

每一条 `evidence_map` 记录：

    {
      "claim_id": "C001",
      "section": "Results",
      "source_id": "mat1",
      "locator": "mat1.pdf:L42",
      "quote": "The mean difference was 0.42 (95% CI 0.31-0.53).",
      "kind": "number|term|citation|figure|method_step|conclusion",
      "reference_id": null,
      "confidence": "high|medium|low|unconfirmed",
      "needs_human": false,
      "note": ""
    }

### 4.2 Locator 格式

- 提取文本：`文件名:L行号`
- 段落：`文件名:段落号`
- CSV/XLSX：`文件名:sheet名:行号` 或 `文件名:sheet名:单元格`
- PPTX：`文件名:slide编号`
- 图片：`文件名:图编号`
- 必须使用实际解析后文本的位置，不能只给原始二进制范围。

### 4.3 事实保全

`preserved_facts.json` 记录必须原样保留的事实：

    {
      "fact_id": "F001",
      "fact": "sample size was 48",
      "quote": "...",
      "source_id": "mat1",
      "locator": "mat1.pdf:L17",
      "kind": "sample_size"
    }

只改变表达方式，不改变数值、单位、样本量、显著性、术语、引用编号。

---

## 5. 输出产物与契约映射

| output_contract 字段 | 磁盘文件 | 说明 |
|---|---|---|
| case_id | result.json 顶层与嵌套 | 原样保留 |
| deliverable | manuscript.md / 指定 Office 文件 | 可编辑完整稿件 |
| preserved_facts | preserved_facts.json | 数字、条件、术语和来源不可凭空改变 |
| evidence_map | evidence_map.json | 关键论断到来源定位的映射 |
| change_log | change_log.json / change_log.md | 修改动作、原因、人工确认项和未解决问题 |

`result.json` 中 `deliverable`、`preserved_facts`、`evidence_map`、`change_log` 等字段值可以是文件路径字符串，也可以是结构化对象；但必须与磁盘文件对应，不得声称不存在的文件。

---

## 6. 隐藏案例鲁棒性

### 6.1 正常案例

- 材料完整、任务清晰。
- 必须产出完整章节稿、证据映射、参考文献、数据可得性或声明字段。
- 每节应有实质段落；事实密集章节优先写实。

### 6.2 边界案例

- PDF 无文本层或扫描版：尝试平台工具、`pdftotext`、`PyMuPDF`、OCR；失败记 `pdf_unparsed` 或 `ocr_failed`。
- 图表无图注、图表与正文冲突、文献不全：不补齐，写入 `pending_human` 与 `conflicts`。
- 材料超长：读前 2MB 或限时截断，记 `file_truncated`。
- 引用格式不认识：保留原格式，记录任务要求格式，不强行重写。
- 文件损坏：跳过该文件，记 `file_error` 或 `file_unparsed`，继续处理其他材料。

### 6.3 异常案例

- 无 `/input/case.json`：寻找 `case*.json`；仍无则记 `case_json_missing`，从 `task.md` 和材料推断任务。
- 空材料目录：生成合法 result.json，`deliverable` 为“无法完成，缺少材料”，`status=input_error`。
- JSON 损坏：按文本行解析可用字段，记 `json_parse_failed`。
- 输出目录不可写：回退到 `/app/work/output`，并在 result.json 说明。
- 无论何种异常，result.json 合法，退出码 0。

---

## 7. 预算策略

建议分配：

- init 与输入解析：4–8 次请求。
- 阅读材料与证据核验：10–18 次请求。
- 撰写完整稿件：15–25 次请求，按 Results/Methods 优先，再 Introduction/Discussion，最后 Abstract/Conclusion/References。
- check/build/selfcheck 与修复：6–10 次请求。
- 预留 5–8 次请求处理异常。

必须动作：

- 尽早运行单命令或 init，先落盘 partial。
- 每完成一章或一轮核验就更新磁盘文件。
- 接近预算时立即运行 build 或手工写 result.json，保证 final JSON 合法。
- 不重复审计；不润色非核心内容。

---

## 8. Rubric 到产物证据对照

| 评分维度 | 分值 | 关键动作 | 证据文件 |
|---|---|---|---|
| 实际效果 | 40 | 完整可修改章节稿，事实正确，章节齐备，逐条可核验 | manuscript.md、evidence_map.json、preserved_facts.json、gaps.json |
| 使用增益 | 25 | 快速生成可编辑初稿，减少人工返工，记录公平对比信息 | run_log.jsonl、change_log.json、GAIN_EVIDENCE.md、result.json |
| 创新增益 | 15 | 材料-正文-图表三向对齐，论断-引用绑定，缺项检测，冲突识别 | evidence_map.json、conflicts.json、contract_checklist.json、selfcheck.json |
| 可靠体验 | 10 | 易触发、稳定运行、异常诚实处置 | SKILL.md、errors、degradations、pending_human.json |
| 生态贡献 | 10 | 文档完整、脚本可复用、资源可复用 | references/guide.md、references/schema.md、environment/resources.yaml、SELFTEST.md |

GAIN_EVIDENCE.md 必须记录真实计数与路径：

    claims_total
    claims_with_verbatim_quote
    claims_verified
    quotes_rejected
    missing_sections
    conflicts_detected
    pending_human_items
    elapsed_seconds

不得写出“我们比基线高多少分”这类无来源 benchmark 结论。

---

## 9. Selfcheck 与收尾清单

最终输出前逐项检查：

1. `/app/output/result.json` 是合法 JSON。
2. 原始 `output_contract` 全部字段在 result.json 顶层与嵌套 `output_contract` 中各出现一次。
3. `case_id` 原样保留。
4. `manuscript.md` 或指定可编辑产物存在且包含实质段落，不是大纲。
5. 稿件中每个数字、样本量、p 值、引用、图注都有对应 `evidence_map` 记录。
6. 每条 `evidence_map` 都有 `quote`、`source_id`、`locator`。
7. 缺失、冲突、不确定项写入 `pending_human`、`uncertainty` 或 `gaps`。
8. 若交付 Office/幻灯片/图，存在真实渲染预览；无预览则记录 `preview_render_failed`。
9. `status` 诚实：全部完成即 `complete`，有缺口即 `partial`，输入错误即 `input_error`。
10. `errors`、`degradations` 不为空时要能解释。
11. 退出码为 0。

---

## 10. 文件结构

    SKILL.md
    scripts/main.py
    scripts/audit.py
    references/guide.md
    references/schema.md
    environment/resources.yaml
    SELFTEST.md

维护要求：

- Python ≥ 3.8，优先标准库。
- 离线运行。
- 不依赖未声明服务。
- 不超过 50 个 UTF-8 文本文件，单文件 ≤ 500KB，总 ≤ 2MB，无 symlink。
- 复用者可按 SKILL.md 与 SELFTEST.md 独立运行。