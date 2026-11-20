---
name: literature-structured-notes
description: 将真实科研材料解析为按论文自身章节对齐、字段齐备、逐条结论可回链原文的结构化阅读笔记。优先运行 scripts/main.py run 完成 init→build→selfcheck；Agent 可先读台账与原文撰写 draft.json，再 check/build；无 draft 时脚本确定性抽取兜底。绝不编造缺失数据、引用、分数或软件状态，异常也 exit 0。适用于 PDF、DOCX、XLSX、CSV、HTML、JSON、TXT、MD、XML、TEX 等离线材料，支持科研阅读、问答、提取、翻译、核验与知识结构化。
version: 2.0.0
---

# Section-Anchored Paper Notes

## 0. 最高优先级：真实读取、完整交付、诚实降级

1. **实际材料优先**：必须阅读 `/input` 下真实文件，不依据文件名、标签或领域猜测补造内容。
2. **单命令全流程入口**：先尝试运行：
   ```bash
   python3 scripts/main.py run --input /input --output /app/output --work /app/work
   ```
   该命令内部应完成 `init → build → selfcheck`。如果脚本版本不支持 `run`，立即 fallback 到 §4.3 的命令序列，不得中断。
3. **Agent-first，但必须有确定性兜底**：
   - Agent 路径：先跑 init 看台账，再读解析文本，把判断写入 `${WORK}/draft.json`，然后运行 build；
   - 无 draft 时：build 必须根据 init 台账做确定性抽取，生成实质工作稿，并在 `degradations[]` 中诚实记录 `AUTO_EXTRACT`。
4. **结果优先预算**：任何情况下先落盘合法 `result.json`、`notes.md`、`claims.csv`；预算紧张时保留 `partial`，写清 `limits[]` 与 `pending_human[]`。
5. **禁止编造**：抽取不到写 `not_found_in_extracted_text`；原文未报告写 `not_reported_in_source`；不确定写 `uncertainty[]`；禁止把“提取不到”改写成“原文未报告”。
6. **退出码恒 0**：运行失败、材料缺失、契约缺失、预算耗尽都要生成合法 `/app/output/result.json` 后退出 0。

---

## 1. 用途与边界

**做**：
- 按论文自身章节结构生成章节对齐笔记，而不是通用摘要；
- 生成论文卡片字段：研究问题、假设、数据/样本、方法、主要结果、结论、局限性、资助/利益冲突、可获得性；
- 抽取图表题注锚点；
- 构建可核验 claims 表，每条关键结论带逐字 quote、来源编号、页码/段落/句级 locator；
- 回答 task.md 中明确要求的问答、翻译、提取、核验或知识结构化任务；
- 保留输入 case_id、运行状态、来源、不确定性、人工接管项。

**不做**：
- 不补全原文未报告的数据、样本量、统计量、DOI、引用；
- 不读取图形像素；
- 不使用通用摘要模板替代论文结构；
- 不自造 `golden_standard`、基准分数、金标准答案或未运行的 benchmark 结果；
- 不把脚本生成骨架直接当作最终成稿，除非无 draft 时由确定性兜底生成并明确标注 `AUTO_EXTRACT`。

---

## 2. 运行环境与资源

- 包根目录：`/skills/weekly-skill`
- 输入目录：`/input`
- 工作目录：`/app/work`
- 最终产物目录：`/app/output`
- 仅用 Python 标准库，Python ≥ 3.8
- 离线运行，不访问网络
- 包内现有资源：
  - `scripts/main.py`：主流程，优先使用 `run` 子命令
  - `scripts/doctext.py`：单文件文本抽取工具
  - `references/rules.json`：契约字段/同义映射/抽取规则
  - `references/schema.md`：输出 schema 与 draft 形状
  - `references/notes_template.md`：结构化笔记模板
- 不要引用包内不存在的文件；如需临时文件写在 `/app/work`，最终交付在 `/app/output`。

---

## 3. 输入发现与 contract 识别

### 3.1 读取顺序

1. 读 `/input/case.json`；若不存在，找 `/input` 下 `case*.json`。
2. 读 `/input/task.md`，确认本题具体任务：是章节笔记、论文卡片、知识点提取、问答、翻译、核验还是混合任务。
3. 递归扫描 `/input/**`，跳过 `case.json`、`task.md`、空文件、隐藏文件。
4. 通过扩展名与文件头识别材料类型：`%PDF`、`PK`、DOCX、XLSX、CSV、TSV、HTML、JSON、TXT、MD、XML、TEX、图片。
5. 主来源 = 可解析文本最长的文档；其余记 `secondary`；图片记 `role: image_not_pixel_read` 并加入 `pending_human[]`。

### 3.2 contract 字段识别

- `output_contract|outputContract|contract|result_contract` 任一命中即为输出契约。
- `case_id|id|caseId` 任一命中即为案例标识，必须原样透传。
- 如果 `case.json` 坏 JSON，记录 `input_error` 后继续。
- 如果 `output_contract` 缺失，按本文件 §5 的默认结构化输出生成合法 result，并注明 `contract_missing`。

---

## 4. 执行流程

### 4.1 预算意识

官方预算：64 次模型请求、900 秒、单次响应 16384 tokens（含 reasoning）。脚本运行不占用模型请求，但占用墙钟时间。必须优先完成最小完整交付，再增量增强。

### 4.2 推荐单命令

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令应完成：

1. `init`：盘点材料、生成 source_id、抽取候选章节与候选 claims、冲突分组、写入 `/app/work/inventory.json` 与 `/app/work/baseline`。
2. `build`：校验抽取质量；若存在 `/app/work/draft.json` 则合并 Agent 判断；否则确定性兜底抽取；渲染全部产物；finalize `/app/output/result.json`。
3. `selfcheck`：检查产物与 output_contract 字段、文件映射、quote 命中率、result.json 合法性。

### 4.3 如果 `run` 子命令不可用

按以下顺序执行，并把执行轨迹写入 `changes[]`：

```bash
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --check --input /input --output /app/output
```

若主文档无法被 main.py 成功解析，可用：

```bash
python3 scripts/doctext.py --help
```

对单文件尝试抽取，结果写入 `/app/work/extracted/`。

### 4.4 Agent 路径：先读台账，再写 draft

当预算允许时，按以下顺序增量改进：

1. 读取 `/app/work/inventory.json` 与 `/app/work/baseline`。
2. 读取 `/app/work/extracted/*.txt` 或 baseline 中的逐字 quote 与 page_map。
3. 核对 task.md 与 output_contract 的全部必需字段。
4. 亲自撰写/核验 `paper_card`、`section_notes`、`claims`、`figures`、`gaps`，将判断写入 `/app/work/draft.json`。
5. 运行：
   ```bash
   python3 scripts/main.py run --input /input --output /app/output --work /app/work --draft /app/work/draft.json
   ```
   或等价地 `check` 后 `build`。
6. 不得手工覆盖 `result.json`；结构化 JSON 由脚本 build 生成。

### 4.5 无 draft 时确定性兜底

如果未生成 `/app/work/draft.json`，build 必须利用 init 台账做确定性抽取：
- 逐字 quote 必须来自解析文本；
- locator 必须来自 page_map/章节/句索引；
- 无法抽取的字段写 `not_found_in_extracted_text`；
- 在 `degradations[]` 中记录 `AUTO_EXTRACT`；
- 该兜底仍须生成完整 `/app/output` 产物。

### 4.6 产物落盘顺序

1. `/app/output/result.json` — 主结果，必须合法 JSON；
2. `/app/output/notes.md` — 结构化阅读笔记；
3. `/app/output/claims.csv` — evidence 表；
4. `/app/output/verify_report.json` — 自检报告；
5. 如 output_contract 要求额外文件，如 `paper_card.json`、`evidence_table.json`、`figures.json`、`answers.json`，按字段映射生成；
6. 如生成 Office、幻灯片或图形，必须同时渲染真人可查看的 PDF/PNG 预览到 `/app/output`。

---

## 5. 默认输出契约与 result.json

`result.json` 必须同时具备：

- **顶层真实字段**：`case_id`、`status`、`sources`、`claims`、`paper_card`、`section_notes`、`figures`、`gaps`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`coverage`、`runtime`；
- **嵌套 `output_contract` 回显**：输入契约的完整结构，字段名不改不删，缺失填 `null`/`[]`，已确定字段填入真实值。顶层与嵌套中的 `case_id`、契约字段都要对得上。

### 5.1 字段含义

| 字段 | 内容 |
|---|---|
| `case_id` | 原样回填，来自输入；无法得到填 `null` |
| `status` | `ok`、`partial`、`insufficient_evidence`、`input_error` 中真实取值 |
| `sources[]` | `{source_id, name, path, kind, pages, chars, quality, role}` |
| `claims[]` | `{claim_id, kind, quote, statement, source_id, location{page,page_end,section_id,section_title,section_kind,sentence_index,char_start,char_end,anchor,pointer}, conditions[], numbers[], readability, confidence, verified_quote_hit}` |
| `paper_card` | 9 字段：`research_question, hypothesis, data_sample, methods, key_results, conclusions, limitations, funding_coi, availability`，每个为 `{value, claim_ids, status, readability, pages}` |
| `section_notes[]` | `{section_id, title, kind, pages, sentences, claim_ids, readability}` |
| `figures[]` | `{label, caption, page, anchor, elements:"not_parsed"}` |
| `gaps[]` | 无证据字段，`{field, status, pointer, reason}` |
| `uncertainty[]` | 不确定项，`{item, pointer, reason}` |
| `pending_human[]` | 人工动作，`{action, pointer, reason}` |
| `errors[]` / `degradations[]` | 运行异常/降级，`{time, step, message, evidence}` |
| `changes[]` | 变更轨迹，至少包含 `baseline_generated`、`draft_written`、`auto_extract_fallback`、`finalized` 中发生项 |
| `coverage` | 章节/证据/命中率/卡片覆盖/图表/缺口计数 + `page_map` |
| `runtime` | 版本、Python 版本、开始时间、耗时、实际模型请求数；不得编造模型请求数 |

### 5.2 文件与契约字段映射

- 每个 output_contract 字段必须对应到磁盘文件或 result.json 顶层字段。
- 若契约要求“可编辑 Office/slide/diagram”，必须同时提供渲染 PDF/PNG。
- 若契约要求“答案/翻译/QA”，在 `notes.md` 的主结果中回答，并在 `result.json` 顶层与 `output_contract` 中放入同一答案。
- 不允许只有 result.json 而没有人类可读主产物。

---

## 6. Agent 写 draft.json 的规范

`/app/work/draft.json` 是 Agent 判断文件，不是最终 result.json。形状应遵循 `references/schema.md`；若 schema 缺失，至少包含：

```json
{
  "case_id": "",
  "paper_card": {
    "research_question": {"value": "", "claim_ids": []},
    "hypothesis": {"value": "", "claim_ids": []},
    "data_sample": {"value": "", "claim_ids": []},
    "methods": {"value": "", "claim_ids": []},
    "key_results": {"value": "", "claim_ids": []},
    "conclusions": {"value": "", "claim_ids": []},
    "limitations": {"value": "", "claim_ids": []},
    "funding_coi": {"value": "", "claim_ids": []},
    "availability": {"value": "", "claim_ids": []}
  },
  "section_notes": [
    {
      "section_id": "S1",
      "title": "",
      "kind": "introduction|methods|results|discussion|conclusion|other",
      "pages": [],
      "purpose": "",
      "methods": "",
      "results": "",
      "conclusions": "",
      "limitations": "",
      "claim_ids": []
    }
  ],
  "claims": [
    {
      "claim_id": "C1",
      "kind": "research_question|hypothesis|data|method|result|conclusion|limitation|availability|other",
      "source_id": "S1",
      "quote": "",
      "statement": "",
      "locator": {
        "page": 1,
        "section_id": "S1",
        "section_title": "",
        "sentence_index": 0,
        "char_start": 0,
        "char_end": 0,
        "anchor": "Introduction, paragraph 1"
      },
      "conditions": [],
      "numbers": [],
      "confidence": "high|medium|low",
      "readability": "inferred|verbatim",
      "verified_quote_hit": true
    }
  ],
  "figures": [
    {
      "label": "",
      "caption": "",
      "page": 0,
      "anchor": ""
    }
  ],
  "gaps": [],
  "uncertainty": [],
  "pending_human": [],
  "agent_review": {
    "baseline_read": true,
    "all_contract_fields_reviewed": true,
    "summary": ""
  }
}
```

**写入 draft 的规则**：
- `quote` 必须是原文逐字字符串，禁止改写、换算、翻译后冒充原文；
- `locator` 必须可回原文；章节、页码、句索引、char_start/char_end 至少有一项有效；
- 冲突结论保留为多条 claims，在 `conditions[]` 或 `uncertainty[]` 说明；
- 没有证据时不要写 confidence=high。

---

## 7. 证据与来源回链协议

1. 来源编号：主材料 `S1`，次要材料 `S2`、`S3`...；链接到 `sources[]`。
2. 正文引注格式：每条关键数字、论断、变量、方法条件后面标注 `[S#] @file#L行号/段落号` 或 `[S#] @page:paragraph/section`。
3. 图表锚点只写题注与页面位置；图内数值不解析。
4. `verified_quote_hit` 为 true 时，quote 必须可在原文定位；为 false 时进入 `pending_human[]`。
5. `not_found_in_extracted_text` 表示“提取不到”，不等于原文未报告；`not_reported_in_source` 才是原文未报告。两者不可混用。
6. 所有数字、单位、条件只保留原文字符串，不做单位换算或统计推断。

---

## 8. 任务适配与优先级

1. 先完成 task.md 明确要求的主任务；默认任务同时输出结构化论文笔记、论文卡片、图表锚点与 claims 表。
2. 如果 task.md 侧重问答/翻译/提取，则：
   - 在 `notes.md` 第一段给出直接答案；
   - 在 `result.json` 顶层和 `output_contract` 中写同一答案；
   - 每条答案都带 `[S#]` 锚点。
3. 如果 task.md 要求“知识点提取/可检索条目”，按术语、变量、方法、结论拆条，处理缩写与同义表达，避免重复。
4. 如果 task.md 要求“结果复核与复用”，在 `notes.md` 中标注“机器可判 / 人工确认”两类字段，并把人工项放入 `pending_human[]`。

---

## 9. 异常处理与隐藏案例鲁棒性

| 情况 | 检测 | 处置 | status |
|---|---|---|---|
| 正常论文 | 文本量充足、有标题 | 完整章节笔记 + 论文卡片 + claims | `ok` |
| 无标题/少标题 | headings < 2 | 退化单章 `S1 Full text`，加 `headings_not_detected` | `partial` |
| 扫描/图片 PDF | 字符少、quality=low_text/garbled | 保留空文本，写 `degradations[]`，建议 OCR，不编造 | `partial` 或 `insufficient_evidence` |
| 加密 PDF | `/Encrypt` | 跳过该文件，记 `errors[]` | `partial` |
| 双栏错序 | 句序异常 | 不猜测重排，`uncertainty[]` 提示人工核对 | `partial` |
| 图表为主 | 页字符 < 120 | `uncertainty[]` 列低文本页；图元素不解析 | `partial` |
| 超长文 | 文本量过大 | 优先标题、摘要、结果、局限；其余标 `deferred` | `partial` |
| 非中文论文 | 语言非中文 | 保留原语言 quote，必要时在 statement 做翻译，注明原文语言 | `ok` 或 `partial` |
| 材料缺失/坏 JSON | 无 case、无材料、JSON 解析失败 | 记 `input_error`、缺口清单，继续生成合法空 result | `input_error` |
| 格式不支持 | 未识别扩展名/文件头 | 标记 `unsupported_format`，不强行解析 | `partial` |
| 契约缺失 | 无 output_contract | 按本文件 §5 默认输出，注明 `contract_missing` | `partial` |
| 预算耗尽 | 时间将尽或请求将尽 | 保留当前 partial，写 `limits[]`，退出码 0 | `partial` |

任何情况下 `/app/output/result.json` 必须合法，并且包含可得 case_id、真实 status、`errors[]`、`degradations[]`、`pending_human[]`。

---

## 10. Rubric 得分动作清单

### 实际效果 40 分

- 任务完成度 15：逐章笔记按论文原有顺序；不只输出通读摘要；每章有 `purpose/methods/results/conclusions/limitations` 中可获取部分。
- 结果正确性 15：每条论断与 quote、数字、变量、方法条件一致；anchor 指向真正对应位置。
- 结果完整性 5：覆盖研究问题、数据、方法、主要发现、结论、局限性 6 大要素；缺的写 gaps。
- 结果可核验性 5：每个关键结论都能按 locator 回到原文；`verify_report.json` 显示 quote 命中。

### 使用增益 25 分

- 质量增益 15：保存 `/app/work/baseline` 与 final `/app/output`；在 `changes[]` 记录 Agent 增强项；不允许最终产物退回通用摘要。
- 效率增益 5：单命令完成 init→build→selfcheck；无 draft 时确定性兜底也产出完整交付。
- 增益可验证性 5：`changes[]` + `runtime` + `verify_report.json` 证明“从基线到最终”的实际改进，不写未运行的对比分数。

### 创新增益 15 分

- 新增能力 5：章节对齐、字段化卡片、claims 表、锚点回链，不是普通摘要。
- 方法改进 5：用 init 台账来源编号、候选抽取、冲突分组；用 draft.json 分离 Agent 判断与脚本构建。
- 创新证据 5：在 `notes.md` 方法说明和 `verify_report.json` 中写清“本包相对于通用摘要的边界”。

### 可靠体验 10 分

- 调用易用 3：单命令入口明确，输入输出说明清楚。
- 运行稳定 4：重复运行可复现；失败也 exit 0。
- 异常处理 3：§9 的异常表完整，且真实记入 result.json。

### 生态贡献 10 分

- 文档完整 3：SKILL.md 写清用途、适用条件、调用方式、输入输出、异常处理。
- 资源可复用 4：使用已有 `references/rules.json`、`references/schema.md`、`references/notes_template.md`，不要新增未说明路径。
- 分享价值 3：交付可复现产物与 `claims.csv`，可作为他人继续加工笔记的基础。

---

## 11. 最终自检清单

结束前逐项确认：

1. `/app/output/result.json` 合法 JSON，UTF-8，退出码 0。
2. 顶层含 `case_id`、`status`、`sources`、`claims`、`paper_card`、`section_notes`、`figures`、`gaps`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`coverage`、`runtime`。
3. 嵌套 `output_contract` 回显原契约全部字段；未知字段保留，不删除。
4. `/app/output/notes.md` 存在，且按章节顺序组织；每条关键结论有 `[S#]` 锚点。
5. `/app/output/claims.csv` 存在，与 result.json 的 claims 对齐。
6. `/app/output/verify_report.json` 存在，含 pass/fail、quote 命中、文件清单。
7. 无证据字段写 `not_found_in_extracted_text`，不确定项在 `uncertainty[]`，人工动作在 `pending_human[]`。
8. 没有自造 benchmark 分数、golden_standard、未运行对比结果或编造论文数据。
9. 若生成 Office/幻灯片/图形，预览 PDF/PNG 已渲染。
10. `changes[]` 中记录 `baseline_generated`、`draft_written` 或 `auto_extract_fallback`、`finalized`。

---

## 12. 最小调用示例

示例输入：

```text
/input/case.json
/input/task.md
/input/paper.pdf
```

示例调用：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

示例输出结构：

```text
/app/output/result.json
/app/output/notes.md
/app/output/claims.csv
/app/output/verify_report.json
```

示意输出字段：

```json
{
  "case_id": "case-001",
  "status": "partial",
  "sources": [],
  "claims": [],
  "paper_card": {},
  "section_notes": [],
  "figures": [],
  "gaps": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": ["AUTO_EXTRACT"],
  "changes": ["baseline_generated", "auto_extract_fallback", "finalized"],
  "coverage": {},
  "runtime": {},
  "output_contract": {}
}
```

示意输出仅为说明接口，不代表正式案例结果。