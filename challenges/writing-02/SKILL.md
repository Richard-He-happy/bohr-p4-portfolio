---
name: academic-language-polish
description: Polish, copy-edit or translate academic prose sentence by sentence while locking numbers, units, citation markers, figure/table pointers, terminology and hedge strength. Use when a manuscript, abstract, thesis chapter, grant text, response-to-reviewers or bilingual abstract is supplied for language polishing, terminology unification, register adjustment or Chinese-English revision. Returns an editable manuscript plus a per-edit change log (original quote, revised quote, type, reason, locator), a preserved-fact inventory and a claim-to-source evidence map. Do not use it for content questions where no rewrite of the supplied text is requested.
version: 1.1.0
license: MIT
---

# 学术语言润色（writing-02）

## 0. 角色与最高优先级声明

本 Skill 对已有学术稿件做语言层润色：语法、句法、搭配、标点、术语一致、缩写首次出现、学术语气、中译英表达，产出**可编辑改稿 + 逐条修改说明 + 保留事实清单 + 证据定位**。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。**  
`scripts/main.py` 与 `scripts/verify.py` 负责取件、工作单生成、契约回填与确定性检查，但它们生成的骨架、模板、基线文本**不是最终成品**。你必须：
1. 真实读取 `/input` 下的材料与原文，逐段完成润色判断；
2. 亲自撰写每条 `edits` 的 `original_quote`、`revised_quote`、`type`、`reason`；
3. 亲自核验事实、数字、引用、图表指向与限定强度；
4. 将脚本产出视为“完整基线与契约容器”，在其上做真实增强，**不得删除或清空基线字段**。

**完整性优先（最高优先级）**：进入任务后先运行主脚本产出全套基线交付物（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段），再增量改进。提交前必须逐项核对「`output_contract` 字段 list × 磁盘文件 × `result.json` 键」三者一一对应；缺任何一项先补齐再收尾；`partial` 状态必须列出缺失项。

## 1. 用途与边界

对**已有稿件**做语言层润色，覆盖：
- 语法、句法、搭配、标点、断句、时态/语态/冠词/介词/单复数；
- 悬垂修饰、长句切分、中式英语、直译腔、冗余名词化；
- 术语全篇一致、缩写首次出现与大小写、连字符统一；
- 学术语气与语域：期刊论文、学位论文、基金申请书、审稿回复、英文摘要；
- 中英双语润色/翻译（在原文语种与目标语种之间保持语义）。

不做：代写新章节、补造数据/文献/结论、审稿意见真实性判断、把材料外知识写入稿件。原文是唯一事实依据；材料未给的内容一律不补。

## 2. 触发条件

**触发**：用户给出稿件/摘要/章节/基金文本/审稿回复，要求「润色、改写语言、校订英文、统一术语、改成期刊语气、中译英」。  
**不触发**：只问内容、只要提纲、只要翻译一句术语、只要文献清单、要求评价研究优劣而不改文本。此时说明本 Skill 的适用范围，不改写用户文本。

## 3. 运行契约

- 输入：`/input/case.json` + `/input/**` 材料（md/txt/tex/docx/pdf/csv/json，可能含图片）；工作目录 `/app/work`；最终产物 `/app/output`。
- 只依赖 Python 标准库；不联网；不依赖当前目录（脚本用 `Path(__file__).resolve().parent`）。
- **退出码恒为 0**；任何异常写入 `errors`/`degradations`/`pending_human`。
- **先落盘**：`main.py` 启动即写 partial `result.json`，结束时无条件覆盖为终版；你在过程中每完成一批段落也可重跑 `main.py` 增量落盘。
- 预算：单次 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。接近 780 秒时停止新增段落，直接重跑 `main.py` 落盘并说明未完成范围。
- 可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**（若输出为这些格式）；本题默认交付 `manuscript.md`（可直接编辑/粘贴）与 `deliverable.md`，无需额外渲染。

## 4. 输入发现（按语义，不假设键名）

1. 读 `case.json`；不存在时递归找 `case*.json`，仍无则用 `task.md` + 材料。
2. 指令语义键：`task_instruction / instruction / task / brief / goal / requirement(s) / deliverable_request / edit_instruction`（可嵌套）。
3. 工单：`organizer_workorder / organizer_edit_workorder / workorder / checklist` —— **逐项执行并在 `workorder_receipts` 回报**。
4. 术语：`glossary / termbase / terminology / terms`，支持 dict / list / `"a → b"` 三种写法；冲突进 `pending_human`。
5. 材料：递归扫描 `/input/**` + `formal_inputs / runtime_files / materials / artifacts / attachments` 中列出的路径；PDF 走 `pdftotext` → `pypdf` → 内置 FlateDecode；DOCX 走 zip XML；图片只登记不 OCR（记降级）。
6. 材料缺失（未给原稿、只给图片、PDF 无文本层）→ 明确写缺口，不推测内容。

## 5. 输出契约

`/app/output/` 下：

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 润色后全文，可直接编辑/粘贴 |
| `deliverable.md` | 交付包：全文 + 修改清单表 + 术语表 + 待确认项 |
| `change_log.csv` | 每条修改：段落/类型/原文/改文/理由/定位/校验 |
| `result.json` | 结构化结果，**原样回填 `output_contract` 全部键**（键名不改、缺值 null/[]），保留未知字段 |

`result.json` 必含：`case_id`、`status`（ok / partial / insufficient_evidence / input_error）、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`glossary`、`bilingual`、`workorder_receipts`、`checks`、`coverage`、`counts`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

若题面 `case.json` / `task.md` 提供了 `output_contract`，其全部字段必须原样键名出现在 `result.json` 顶层（或按约定层级），缺值用 `null` / `[]`，并保留未知字段不丢弃。

## 6. 本题专属执行流程（编号步骤）

### 步骤 0：基线落盘（0 模型请求，约 30–90 秒）
- **输入**：`/input` 目录（可能尚未完全解析）。
- **动作**：立即运行：
  ```bash
  python3 -B scripts/main.py --input /input --output /app/output --work /app/work
  ```
  生成 `work/workpack.json`（每段的 `id`、`text`、`section`、`locks`：numbers / citations / xrefs / hedges / boosters / abbreviations）和 partial `result.json`。  
- **输出**：`/app/output/result.json`（partial 基线）、`/app/output/manuscript.md`（初始为原文或脚本生成的骨架）、`/app/work/workpack.json`、`/app/work/polish_payload.json`（骨架）。  
- **失败分支**：若 `python3` 不可用或脚本报错 → 记 `degradations: script_unavailable`，按 `references/payload_and_result_schema.md` 手工产出 `manuscript.md`、`change_log.csv`、`result.json`，`status=partial`；**不得省略修改说明或保留事实清单**。

### 步骤 1：盘点输入（2–5 次模型请求）
- **输入**：`/input/case.json`、`/input/task.md`、递归素材清单、`work/workpack.json`。
- **动作**：  
  - 读 `case.json` 与 `task.md`，提取任务指令、体裁、目标语言、约束、`output_contract` 字段列表；  
  - 识别 `workorder` / `glossary` / `materials`；  
  - 判断段落数、字数、需要润色的范围；  
  - 若已有 `output_contract`，将其字段复制到你的计划中。  
- **输出**：任务摘要（内部笔记，不必写入文件），明确哪些段落必须处理、哪些可跳过，哪些术语/锁需要特别关注。  
- **失败分支**：`case.json` 缺失或解析失败 → 使用 `task.md` + 材料，`status=partial`，`input.case_path=null`，记入 `errors`。

### 步骤 2：用工具真实解析材料（脚本运行为主，可少量模型请求辅助判断）
- **输入**：`/input/**` 全部材料、`work/workpack.json` 锁清单。
- **动作**：  
  - 对每个材料文件运行对应的解析工具：PDF 走 `pdftotext` / `pypdf`；DOCX 走 zip XML；CSV 读为标准库；图片只登记不 OCR。  
  - **亲自阅读解析出的原文全文**，不要只依赖文件名或 `workpack` 的片段摘要。  
  - 对 `workpack` 中每段的 `locks` 做一次人工核验：数字、单位、引用编号、图表指向、hedge/booster 词是否与原文一致；不一致则修正 `workpack` 或记入 `pending_human`。  
- **输出**：确认可读的段落列表、锁清单修正、材料缺口记录。  
- **失败分支**：某段不可读、PDF 无文本层、编码混乱 → 参照第 8 节降级，但其他段照常处理；记 `degradations` 与 `pending_human`。

### 步骤 3：构建/核对证据与术语基线（3–8 次模型请求）
- **输入**：原文、`workpack.json`、术语表（如果有）。
- **动作**：  
  - 建立全篇术语表（从材料 `glossary` 提取，或从原文中识别同一概念的中英文变体、缩写）；  
  - 记录 `glossary` 每条的 `source` / `target`，并标记首次出现位置；  
  - 对关键数字、单位、引用编号、图表指向建立 `evidence_map`（每条证据含原文定位与改后定位）；  
  - 若材料中有冲突，立即写入 `pending_human`。  
- **输出**：写入 `work/polish_payload.json` 的 `glossary` 与 `evidence_map`（或先写在 `result.json` 骨架中），供后续润色使用。  
- **失败分支**：术语表缺失或冲突 → 明确填 `glossary: []` 或标记冲突，不擅自定义。

### 步骤 4：Agent 产出完整成品（核心，预算见第 7 节）
- **输入**：原文、`work/polish_payload.json` 骨架、术语表、锁清单。
- **动作**：  
  - 逐段润色，每段依次执行：读锁 → 找硬错 → 最小编辑 → 守住主张 → 守住事实 → 术语落地 → 写修改说明 → 回读。  
  - 将每段的 `revised` 整段、`edits` 数组（类型/原文/改文/理由/定位）、`unchanged_reason`（如无错）写入 `work/polish_payload.json`。  
  - **切忌整段重写而不给 `edits`**；每条修改的 `original_quote` 必须能在原文中逐字找到，`revised_quote` 必须能在改后段落中找到。  
  - 同时填充 `workorder_receipts`（针对每个工单项）与 `bilingual`（如要求中英对照）。  
  - 每完成一批段落（例如每 5 段或每完成一整节），重新运行：
    ```bash
    python3 -B scripts/main.py --input /input --output /app/output --work /app/work
    ```
    以增量落盘最新 partial。  
- **输出**：完整的 `polish_payload.json`、更新后的 `manuscript.md`、`deliverable.md`、`change_log.csv`、`result.json`（partial 或 final）。  
- **失败分支**：某段无法安全润色（如公式混杂、不明缩写、疑似数值错误）→ 保留原文段落，将该段写入 `pending_human`，其余段正常交付。

### 步骤 5：自检 rubric 与回填 result.json（3–8 次模型请求）
- **输入**：当前 `/app/output` 全部产物、`work/polish_payload.json`、`result.json` 当前状态。
- **动作**：  
  1. 运行：
     ```bash
     python3 -B scripts/verify.py --output /app/output
     ```
     打印检查表。  
  2. 逐项修复 `fail` 项：引用不匹配、锁丢失、契约字段缺漏、workorder 未回报等。  
  3. 回填 `result.json` 中 Agent 亲自核验的结果：`preserved_facts` 增添核验状态（verified / pending_human / conflicts）、`evidence_map` 完善、`changes` 记录 Agent 的增强与判断。  
  4. 核对 `output_contract` 字段 list × 磁盘文件 × `result.json` 键三者一一对应。  
- **输出**：最终 `result.json`、所有交付文件。  
- **失败分支**：若时间不足，停止新增改动，保留已完成的 partial，明确列出未完成范围并写 `pending_human`；退出码 0。

## 7. 预算策略：64 次模型请求 / 900 秒内分配

**优先级**（按 rubric 权重从高到低）：
1. **实际效果 40 分**：完整全文润色 + 逐句修改说明 + 事实锁定与证据映射。这是最高权重，必须优先完成。
2. **可靠体验 10 分**：契约字段齐全、异常处理、可编辑产物直接可用。
3. **使用增益 / 创新增益 / 生态贡献**：通过脚本锁清单、证据映射、术语表回扫与清晰文档体现，可在完成核心交付后逐步增强。

**请求分配建议**（总 64 次模型请求）：
- 步骤 0–1（基线 + 输入盘点）：5 次  
- 步骤 2（材料解析辅助判断）：5 次  
- 步骤 3（证据与术语基线）：8 次  
- 步骤 4（逐段润色，核心）：最多 35 次  
  - 若段落数 ≤ 25，每段 1 次请求完成润色 + 说明；  
  - 若段落数 26–40，每段 1 次但理由可更简洁（仍须 ≥6 字且说明语义保持）；  
  - 若段落数 > 40，优先处理摘要、引言、结果、讨论等核心章节，方法与补充章节可用 minimal edit 模式，但所有段落必须得到处理，不遗漏；  
  - 剩余预算用于抽查修改引用一致性（2–3 次）。
- 步骤 5（自检与修复）：8 次  
- 预留应急：3 次（处理冲突、重写个别修改）

**时间阈值**：
- 接近 **780 秒**：停止新增段落，立即重跑 `main.py` 落盘；已润色部分保留，未润色段落保留原文并记录 `pending_human`。  
- 全程避免无意义循环：每出现一次 `fail`，最多修复 2 轮；若仍不行，保留原文并写入 `pending_human`，不无限重试。

**增量落盘**：每完成一整节或每 5 段，重跑一次 `main.py`，使 `result.json` 始终反映最新 partial，防止最后一步超时导致全部丢失。

## 8. 隐藏案例鲁棒性与异常降级

任何情况下都要产出合法 `result.json`，退出码 0。以下为具体降级策略：

| 情况 | 处置 |
|---|---|
| 无 `case.json` | 递归找 `case*.json`；仍无则用 `task.md` + 材料，`status=partial`，`input.case_path=null` |
| `case.json` 解析失败 | 记 `errors: case_json_parse`，继续用 `task.md`；不因为解析失败而中断 |
| 无可读文本（空输入、纯图片无 OCR、PDF 无文本层） | `status=insufficient_evidence`，`pending_human` 写明「源文本」缺口；不应编造内容 |
| 某材料格式不支持（如 .pages、.xls 宏） | 记 `degradations: unsupported_format`，尝试朴素文本提取；失败则保留未解析说明，不猜测 |
| 编码混乱（乱码） | 依次尝试 utf-8/gb18030/big5/cp1252/latin-1；仍乱码则记 `encoding`，对应段落保留原文或请求可读版本 |
| PDF 无文本层 | 记 `pdf_text` 降级；若确无内容则标记 `pending_human`，不伪造原文 |
| `polish_payload.json` 缺失或损坏 | 交付原文基线 + `pending_human`，`status=partial`；不得省略修改说明或保留事实清单（手工补写） |
| 某段无 payload | 该段保留原文，段号写入 `pending_human`，其他段照常交付 |
| 超长输入（>200k 字符） | 记 `long_input`，修改清单可截断，但正文全量保留；优先处理核心段落 |
| 公式/LaTeX 混杂 | 公式原样保留，只改公式外文字；若公式使语义判断不确定，写入 `pending_human` |
| 术语表内部冲突 | 写入 `pending_human`，不擅自选择；在 `glossary` 中同时列出两种写法并标注待确认 |
| 目标文体 / 目标期刊不明 | 采用中性学术语域，记入 `uncertainty`；在 `deliverable.md` 中注明假设 |
| `output_contract` 缺失 | 使用本 Skill 默认字段（第 5 节），并记 `missing_contract_fields`；不减少必要字段 |
| 运行超时（>900 秒或 780 秒预警） | 立即停止新增，保留 partial，`status=partial`，`pending_human` 列出未完成项 |
| `python3` 不可用或脚本报错 | 按 `references/payload_and_result_schema.md` 手工产出三件套，`status=partial`，`degradations` 记 `script_unavailable` |
| 磁盘 / 权限错误 | 修复路径；若 `/app/output` 不可写，写 `/app/work` 并说明，尽力产出合法 JSON |

**隐藏案例注意事项**：
- 不得依据文件名或领域标签猜测源文本内容；必须实际解析材料。
- 科学数据、引用编号、样本量、p 值必须严格保持；不确定时写入 `pending_human`。
- 对白板 / 正式测试案例不提供预制答案；所有交付物必须由本次运行推导。
- 任何 `status` 为 `partial` / `insufficient_evidence` 时，`pending_human` 必须具体指出缺少什么、需要人工做什么。

## 9. 润色规程（每段照做）

1. **读锁**：该段的 numbers / units / citations / xrefs / hedges / boosters / abbreviations 是硬约束。
2. **找硬错**：主谓一致、时态、冠词/介词、单复数、悬垂修饰、标点、断句、搭配、重复。
3. **最小编辑**：先改词、再改短语、最后才重排句子；一个改动能用 3 个词解决就不用 10 个。保留作者信息顺序与句间逻辑连接。
4. **守住主张**：hedge（may / suggest / could / 可能 / 提示）与 booster（demonstrate / prove / 证明 / 首次 / 显著）的强度不得增删；因果（cause）与相关（associate with）不得互换；否定范围、条件句、量词不得改动。
5. **守住事实**：数字、单位、样本量、p 值、引用编号、图表指向原样保留；必须改数值时停手，写入 `pending_human`。
6. **术语落地**：使用术语表写法；全篇回扫同义变体（tumor/tumour、normalize/normalise、缩写大小写）。
7. **写说明**：每条改动给出类型、原文、改文、理由（≥6 字，说明改什么、为何不改变语义）、定位。
8. **回读**：改完通读该段，检查（a）意思是否仍等于原文（b）锁是否齐全（c）是否像同行写的（d）有无新增信息。任一项失败就回退该处。

无错可改时把 `revised` 填回原文并给 `unchanged_reason`，不要为改而改。

## 10. 语气与文体

按 `workpack.json` 的 `genre` 选基线：期刊论文=中性客观、方法过去时、结论现在时；摘要=单段无引用除非原文有；学位论文=可展开、允许第一人称复数；基金=问题—缺口—方案—影响，避免绝对化；审稿回复=逐