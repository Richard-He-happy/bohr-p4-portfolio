---
name: academic-compliance-review
description: 对论文/科研材料做学术规范与合规审查，输出带逐字定位证据的结构化审查意见。用于审稿、投稿前自查，以及学术诚信、引用、隐私、版权、伦理、投稿要求的合规检查；产出 result.json + review_report.md + issues.csv，覆盖事实核验、引用支持、方法设计、统计报告、论证链、学术规范六个检查面。版本 2.0：增加 Agent 亲自推导、完整性优先、预算感知、隐藏案例鲁棒性。
version: 2.0.0
---

# 学术规范与合规检查（review-05）

## 0. 最高优先级：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作

`scripts/main.py` 与 `scripts/extract.py` 只负责解析材料、建立可定位语料、生成确定性候选、校验 quote、回填契约和渲染报告。它们产出的 candidates、packets、partial result 都不是最终成品，**不得把脚本骨架、模板或未裁定候选直接当成品提交**。

你必须完成以下“亲自推导”动作：

1. 真实读取 `/input` 下每个材料，不得仅凭文件名或领域标签猜测内容。
2. 逐条阅读 `/app/work/review/packets.md` 与 `/app/work/review/candidates.json`，回到原文 `locator` 处核对每个候选是否成立。
3. 每条进入 `issues` 的问题由你亲自确认：`quote` 必须逐字来自原文，`reason`/`suggestion` 必须结合具体材料写出，不得复制脚本触发条件。
4. 脚本候选不足或漏报时，由你亲自补报；脚本误报的候选必须写 `dismissed` 并给理由。
5. 完整性优先：先运行脚本得到全套基线交付物，之后只能增量增强，**不得删除、清空或遗漏任何基线产物、`output_contract` 字段或 `result.json` 键**。

---

## 1. 用途与边界

**做什么**：读入科研材料，按六个检查面逐条给出**可定位、可核对**的问题（原文 locator + 逐字 quote + 判定依据 + 严重度 + 可执行建议），并如实区分“错误 / 证据不足 / 规范问题 / 建议”。

六个检查面：

- 事实核验
- 引用支持
- 方法设计
- 统计报告
- 论证链
- 学术规范（诚信、隐私、版权、伦理、投稿要求）

**不做什么**：不代写、不润色、不代投稿；不重做数据分析；不出具法务或伦理委员会的正式意见；不判断文献“是否真实存在”（离线无法核验 → 记 `insufficient_evidence` 并 `pending_human`）。

**适用**：期刊稿件、结题/答辩材料、对外发布前自查；中英文；PDF/DOCX/MD/TXT/JSON/CSV/XLSX。
**不适用**：纯图片或扫描件（本 Skill 无 OCR 能力）、需要跨库查重或 DOI 核验、需伦理委员会裁定的争议。

---

## 2. 运行契约

- 输入 `/input`（`case.json` + `task.md` + 材料），工作目录 `/app/work`，产物 `/app/output`。
- 仅 Python 标准库（≥3.9），**不联网**，不依赖当前工作目录（脚本用 `Path(__file__).resolve().parent` 定位同目录模块）。
- **退出码恒 0**；任何异常都落成合法 `result.json`。
- 先写 partial（`status=partial`）再细化，最终无条件覆盖为终态。
- 预算：本地计算毫秒级；判读阶段建议 ≤64 次模型请求、900 秒，单次响应 ≤16384 tokens；接近上限先落盘 honest partial，再增量改进。

```bash
python3 scripts/main.py --input /input --output /app/output --stage scaffold   # 出候选 + partial
python3 scripts/main.py --input /input --output /app/output --stage finalize   # 校验、去重、契约回填、渲染
```

**你不可直接以 `finalize` 默认输出为最终答案。** 正确顺序是：scaffold → 你亲自裁定候选并补漏 → 再 finalize 校验。若 finalize 产物缺少你的裁定，应视为 partial，继续补全。

---

## 3. 输入发现与真实解析

1. 递归扫描 `/input` 下全部文件（按名排序，上限 50；超出记 `degradations:file_cap`）。
2. `case.json`（或首个 `case*.json`）：原样保留 `case_id`；递归定位 `output_contract`（键名可为 `output_contract`/`contract`/`result_contract`）。
3. 材料按**扩展名 + 内容**解析，禁止用文件名判断内容：
   - PDF：用环境提供的 `pdf-text-tool` 或 `scripts/extract.py` 提取文本层；若无文本层，记为 `pdf_no_text_layer`。
   - DOCX：读 `word/document.xml`。
   - XLSX：读 `sharedStrings` + `sheet*.xml`。
   - 文本类：直接读取 UTF-8。
   - 图片：只登记 `image_not_read`，**不读取像素、不做图内推断**。
4. `case.json` 中 ≥60 字符的字符串按 JSON Pointer 建为独立来源，因为稿件可能直接内联。
5. `/app/work/review/text/*.txt` 可视为“自行 OCR/转写”的补充文本，支持 `[[p3]]` 分页。
6. 材料未提供的对象（文献表、图、补充材料、伦理附件）**明确列缺口，不构造**。

**真实解析要求**：所有引用、数字、统计量、伦理表述、版权表述、投稿要求都必须来自实际提取文本或材料原文；无法提取的内容只可写“材料未提供/无法判断”，不得补造。

---

## 4. 输出契约

| 文件 | 作用 |
|---|---|
| `/app/output/result.json` | 主结果：`case_id`、`status`、`issues[]`、`checks{}`、`summary`、`sources`、`uncertainty`、`pending_human`、`review_records`、`errors`、`degradations`、`changes`、`artifacts`、`runtime`、`contract_fields` + **`output_contract` 的每个键** |
| `/app/output/review_report.md` | 人读报告：六面覆盖 + 逐条问题（位置/原文/依据/理由/建议）+ 待复核/拒收 + 不确定性 + 材料与运行 |
| `/app/output/issues.csv` | 同一批问题的表格视图，可直接排序、批注、交办 |
| `/app/work/review/packets.md` | 按六面分组的**候选**证据包（判读入口） |
| `/app/work/review/candidates.json` | 候选机读版（`cid`/`trigger`/`sev_hint`/`safe`） |

契约回填见 `references/schema.md` §5：键名从不改写，无对应值的键置 `null` 并记入 `contract_fields.unfilled`。

**可编辑 Office/幻灯片/图形产物预览**：本 Skill 原生输出为 JSON/MD/CSV，通常不需要渲染。若 `output_contract` 或题面额外要求可编辑 Office/幻灯片/图形产物，你必须同时产生**真实渲染的 PDF/PNG 预览**。若环境没有可用的渲染工具，要在 `result.json.degradations` 写入 `preview_missing`，并保持 `status` 为非 `pass`；不得伪造预览。

---

## 5. 本题专属执行流程（编号步骤）

### 步骤 1：盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、题面规定材料。

**动作**：
- 列出 `/input` 下文件及其类型。
- 读取 `case.json`，提取 `case_id` 和 `output_contract` 要求的全部字段。
- 若 `output_contract` 缺失或为空，依据本题 Runtime contract 默认字段准备回填。

**输出**：文件清单、契约字段清单、材料可解析性初判。

**失败分支**：目录不存在/为空 → `status=input_error`，仍继续产出合法 `result.json`；`case.json` 坏 JSON → 记 `errors:case_json_invalid`，契约字段只能置空。

### 步骤 2：运行基线 scaffold，尽早落盘 partial

**输入**：上一步文件清单。

**动作**：
- 运行：
  ```bash
  python3 scripts/main.py --input /input --output /app/output --stage scaffold
  ```
- 产生全套基线候选与 partial `result.json`、`packets.md`、`candidates.json`。

**输出**：基线 partial 产物；六面候选分组。

**失败分支**：脚本异常也要保证退出码 0，结果文件存在；记 `errors` 后继续人工兜底解析。

### 步骤 3：真实解析材料，构建/核对证据

**输入**：材料文件、scaffold 候选。

**动作**：
- 对每个关键材料用 `pdf-text-tool` 或 `scripts/extract.py` 提取文本。
- 对每个候选面，回到候选 `locator`/`line` 处查看原文上下文。
- 对关键数字、引用编号、伦理表述、版权表述、统计量做二次确认；必要时手动查看来源文件。

**输出**：你本人确认过的原文片段、候选证据清单、缺失或不可解析项目。

**失败分支**：PDF 无文本层 / 图片 / DOCX 损坏 → 记 `errors` 或 `degradations`，不猜测内容；该来源标 `unreadable`。

### 步骤 4： Agent 亲自逐条裁定并补漏

**输入**：候选清单、原文定位、六面清单 `/app/work/review/packets.md`。

**动作**：
- 对每条候选四选一：
  1. 成立 → 写入 `issues[]`，要求 `locator`、`line`、`quote`、`severity`、`verdict_type`、`reason`、`suggestion`、`evidence`。
  2. 证据不足 → 写入 `issues`，`verdict_type=insufficient_evidence`，并加入 `pending_human`。
  3. 风格差异或误报 → 写入 `review_records.rejected_issues` 或 `dismissed`，给理由。
  4. 脚本漏报 → 你亲自追加 issue。
- 六面均给 `status`：`pass`、`issues_found`、`incomplete`、`not_applicable`；有未裁定候选不得 `pass`。
- 对无法确认的条目标记 `pending_human`，不凭空补结论。

**输出**：完整 `issues[]`、六面 `checks{}`、待复核清单。

**失败分支**：时间或请求数不足 → 保留 partial，`summary.unaddressed` 列明未完成面。

### 步骤 5：产出完整成品

**输入**：你的裁定结果。

**动作**：
- 撰写 `review_report.md`：六面覆盖、逐条问题、原文定位、依据与修改建议、待复核/拒收、不确定性。
- 生成 `issues.csv`，与 `issues[]` 行一致。
- 运行：
  ```bash
  python3 scripts/main.py --input /input --output /app/output --stage finalize
  ```
  让其做逐字校验、去重、契约回填、渲染；但你必须确认校验后没有丢失你的裁定或被误拒。

**输出**：最终 `result.json`、`review_report.md`、`issues.csv`。

**失败分支**：finalize 导致字段缺失 → 手工补回 `output_contract` 字段与 `case_id`；仍以合法 JSON 保存。

### 步骤 6：rubric 自检与证据回填

**输入**：最终产物。

**动作**：
- 逐条对照第 11 节 rubric 表，检查交付物是否覆盖高权重项。
- 核查 `quote` 逐字命中、`evidence` 来源可回查、`output_contract` 字段齐全。
- 更新 `result.json.review_records`：写入 `reviewed_by_agent: true`、关键核验结论、剔除项理由。
- 更新 `changes`：记录你从 scaffold 到 final 的实质性修改。

**输出**：经过自检的最终结果。

**失败分支**：发现契约字段缺失或预览缺失 → 立即补齐；补不上则在 `degradations`/`pending_human` 如实标注。

### 步骤 7：终态落盘

**动作**：确认 `/app/output` 文件完整、`result.json` 合法、退出码 0；保留所有基线与增强产物。

**失败分支**：若时间耗尽，保持当前 honest partial；不得删除 partial 结果或伪造终态。

---

## 6. 预算策略：64 次模型请求 / 900 秒 / 16384 tokens

Rubric 权重最高的是**实际效果 40 分**，因此预算优先保证：完整 `issues`、正确性、完整性、可核验性。其次保证可靠体验与使用增益。

| 阶段 | 预计请求 | 必须/可跳过 | 说明 |
|---|---|---|---|
| 盘点输入、读 case/task/契约 | 2-4 | 必须 | 一次性读取，避免反复打开 |
| 运行 scaffold、读候选 | 1-3 | 必须 | 脚本调用不算模型推理，但读产物算 |
| 按面读原文关键片段 | 8-15 | 必须 | 合并阅读同一材料，避免重复 |
| 六面逐条裁定 | 6-12 | 必须 | 每面可批量处理，不逐句循环 |
| 补充检查脚本漏报 | 3-6 | 条件 | 高权重面优先；低权重可跳过 |
| 写报告、回填 result | 3-5 | 必须 | 尽量一次生成，少改 |
| 自检与契约核对 | 2-4 | 必须 | 发现缺失时低成本补齐 |
| 安全缓冲 | 5-10 | 保留 | 处理意外，不主动用满 |

**何时落盘 partial**：
- scaffold 完成后立即保存 partial。
- 每完成一个检查面的裁定并写回 issue，可增量更新一次。
- 当已用约 50 次请求或运行时间约 700 秒时，停止新增检查，立即 finalize 当前部分结果。
- 若只剩 2-3 次请求，只做契约字段补齐，不再扩写报告。

**避免无意义循环**：同一文件不要重复提取；同一候选不要反复读；如果材料已经足以判断，不要反复调用脚本。

---

## 7. 隐藏案例鲁棒性与降级

| 情况 | 表现 | 处置 |
|---|---|---|
| 输入目录不存在/为空 | `status=input_error`，`errors: input_missing` | 仍出合法 `result.json`，六面 `checks` 为 `not_applicable`，退出码 0 |
| `case.json` 坏 JSON |