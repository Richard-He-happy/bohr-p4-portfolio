---
name: academic-slides-from-paper
description: >-
  Build an evidence-mapped, editable academic presentation from research material
  and organizer PPTX constraints. Use for paper-to-deck generation, academic
  slide editing, template inheritance, claim-source audit, and PDF export.
  Produces presentation.pptx, real rendered PDF, page-level claim/source/change
  records, and result.json with original output_contract fields at top level and
  nested under output_contract. Version 3.1.0 adds strict single-command
  init/build/selfcheck workflow, deterministic fallback, and double contract echo.
version: 3.1.0
---

# 学术 PPT 生成与编辑：证据映射、模板继承、可核验交付

## 0. 最高优先级：Agent 执行边界

本 Skill 的目标不是“生成几页漂亮的文字”，而是生成**能打开、能编辑、可复核、不编造**的学术演示稿。你在 Harness 中的每一步都必须遵守：

1. **先落盘全套基线，再做增强**。进入任务后立即运行 §3 的单命令主流程。不要空想结构，不要手工从零造 PPTX。
2. **禁止伪造科学数据、引用、图片、评分、白板结果**。所有正文 bullet 的关键论断、数字、图表引用必须能回到 `/input` 中的真实文件。
3. **不要手改结构化 JSON 的结构**：`content_map`、`result.json`、`page_golden.json` 等脚本产物的字段名、ID 体系、证据字段必须原样保留。如需修正，写 `agent_review.json` / `draft.json`，或通过脚本函数重算。只有在脚本彻底失败且无法重跑时，才允许按 §7 手工生成最小合法 `result.json`，并明确记录 `AUTO_EXTRACT` / `MANUAL_FALLBACK`。
4. **完整契约优先**。`output_contract` 的字段必须全部出现在 `result.json` 顶层，并同时在 `output_contract` 对象中回显一次。缺失字段、缺失文件、运行失败、材料不足，都必须显式写入 `exceptions`、`degradations`、`pending_human`、`uncertainty`。
5. **任何情况都要 exit 0**。即使 PPTX 或 PDF 失败，也要写出合法 `result.json`，状态可为 `partial` 或 `insufficient_evidence`，但不得崩溃退出。

---

## 1. 用途与边界

### 1.1 适用
- 从论文或研究材料生成固定页数的学术汇报 PPTX。
- 按组织方提供的 `target-template.pptx` 或 `starting-deck.pptx` 进行生成/编辑/适配。
- 生成页级主张、演讲备注、图表引用、来源定位和导出 PDF 预览。
- 输出可复核的证据链接：每页内容对应论文图、表、章节、数据位置。

### 1.2 不适用
- 不重做论文精读与文献综述。
- 不从原始像素设计科研图表，也不凭空生成曲线。
- 不做学术写作润色。
- 不开发 PPT 软件本身。
- 不负责 PDF 原文的 OCR 重建；扫描件无文本层时只做诚实降级。

---

## 2. 运行时契约（Harness 必读）

### 2.1 输入
- `/input/case.json`：案例标识与任务要求。
- `/input/task.md`：题目说明与 `output_contract`。
- `/input/material.json`：题面材料清单。
- `/input/artifacts/slide-workorder.json`：实际页数、模式、受众、时间、模板继承、源保留规则。
- `/input/artifacts/` 下实际 PPTX 文件：`target-template.pptx`、`starting-deck.pptx` 等。
- 论文或研究材料：PDF / DOCX / TXT / MD / 图片 / CSV / JSON 等。

禁止只依据文件名、领域标签或 `material.json` 的说明猜测内容。必须读取实际文件。

### 2.2 工作目录与输出
- 工作目录：`/app/work`
- 最终目录：`/app/output`
- 必产文件：
  - `presentation.pptx`
  - `presentation.pdf`（如可渲染）
  - `result.json`
  - `plan_v0.json` 或 `content_map.json`
  - `page_golden.json`
  - `page_diff.md`
  - `export_check.json`
  - `template_check.json`
  - `version_history.md`
  - `run.log`
- 可选但推荐：
  - `evidence_table.json`
  - `extracted_evidence.md`
  - `agent_review.json`
  - `draft.json`

### 2.3 资源预算
- 总模型请求：64 次。
- 总时长：900 秒。
- 单次响应 tokens：≤16384（含推理）。
- Skill 包：≤50 个 UTF-8 文本文件；单文件 ≤500KB；总 ≤2MB；无 symlink。
- 运行环境：Python ≥3.8；优先纯标准库；离线可用；中英文自适应。

---

## 3. 单命令全流程入口

### 3.1 必须首先执行
```bash
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
```

这是本 Skill 的**唯一主入口**。它的语义等于：

1. `INIT`：盘点 `/input`，识别材料、模板、workorder、契约字段，写入 `/app/work` 下的 manifest。
2. `BUILD`：校验输入，做确定性兜底抽取，按模板和 workorder 生成 `presentation.pptx`，渲染 PDF，生成 `content_map`、`page_golden`、`page_diff`、`export_check`、`template_check`、`version_history`。
3. `SELFCHECK`：检查文件、页数、契约字段、证据 locator、result.json 合法性；把缺口写进 `degradations` / `exceptions` / `pending_human`。

### 3.2 单命令执行后的 Agent 增强路径
Agent 路径不是替代主脚本，而是在主脚本产物上做真实核验与增量增强：

1. 读取 `/app/output/result.json` 和 `/app/work` 下的 manifest。
2. 真实阅读 `/input` 中源材料。
3. 逐条核验关键页面 bullet 的 `quote` 是否为原文逐字子串，`locator` 是否指向正确页/节/表/图。
4. 把 Agent 判断写入 `/app/work/draft.json` 或 `/app/work/agent_review.json`；不得删除主脚本生成的结构化产物。
5. 如需改文案，只改正文型交付物，或通过脚本函数重算；禁止手工覆盖 `content_map` 的 JSON 结构。

### 3.3 无 draft 时的确定性兜底
如果没有 Agent 审查或未写 `draft.json`，主脚本仍必须生成**实质性工作稿**，而不是占位空页。默认动作：
- 从 PDF/DOCX/TXT/MD 提取真实句子。
- 每页生成逐字 `quote`、`locator`、来源编号 `[S#]`。
- 无模板时使用 `references/deck-parts.json` 内置设计。
- 无法渲染 PDF 时保留 PPTX，`export_artifact` 置 `null`，记录 `PDF_RENDER_UNAVAILABLE`。
- 将本次为确定性抽取写入 `degradations`：`AUTO_EXTRACT`，并注明“未经过 Agent 逐条人工核验”。

---

## 4. 执行步骤：INIT → BUILD → SELFCHECK

### 4.1 INIT：盘点输入与契约

**动作**
1. 读取 `/input/case.json`。若失败，记录 `NO_CASE_JSON`，继续。
2. 读取 `/input/task.md`，确认 `output_contract` 至少包含：
   - `case_id`
   - `status`
   - `editable_source`
   - `export_artifact`
   - `content_map`
   - `compliance_checks`
   - `exceptions`
3. 读取 `/input/artifacts/slide-workorder.json`。提取：
   - 目标总页数：优先取 `slide_count` / `total_slides` / `slide_spec.total` 或等价字段。
   - 模式：`generate` / `edit` / `adapt`。
   - 受众、时间、页数限制、模板继承规则、源保留规则。
4. 识别文件：
   - 模板：`target-template.pptx`、`template*.pptx`
   - 起点稿：`starting-deck.pptx`、`source-deck.pptx`
   - 源材料：PDF / DOCX / TXT / MD / CSV / 图片
   - 任何 `slide-workorder.json`
5. 为每个源材料分配稳定来源 ID：`S1`、`S2`、`S3` ...，写入 manifest 和最终 `sources`。

**输出**
- `/app/work/input_manifest.md` 或脚本生成的 manifest JSON。
- 明确写清：契约字段、页数、模式、模板文件、起始稿、来源 ID 列表。

**失败分支**
- 找不到 case.json：继续执行，`case_id` 可写 `unknown` 或文件中的可识别 ID；`exceptions` 加 `NO_CASE_JSON`。
- 找不到 workorder：从 task.md 或材料推断页数；若无法判断，默认生成 8 页，并标记 `WORKORDER_MISSING`。
- 找不到模板：使用内置 16:9 设计；`template_check` 标记 `builtin-default`。
- 没有 `starting-deck.pptx` 但 mode=edit/adapt：降级为 generate，并记录 `EDIT_WITHOUT_STARTING_DECK`。

---

### 4.2 BUILD：确定性生成与模板继承

#### 4.2.1 提取源证据
- PDF：优先用 `pdftotext -layout` 或 `scripts/deckkit.py` 内置读取器提取文本和页码。
- DOCX：读取 `word/document.xml` 文本。
- TXT/MD：直接读取。
- 提取研究问题、方法、结果、限制、关键数字、图表编号、图注、引用编号。
- 每项证据必须记录：
  - `source_id`：如 `S1`
  - `locator`：`S1#p.3 §Results` 或 `S1#Fig.2 caption`
  - `quote`：原文逐字子串
  - `claim_type`：`research_question` / `method` / `result` / `limitation` / `figure` / `table` / `citation`

#### 4.2.2 页级规划
每页必须有明确叙事角色：
- 标题页
- 研究问题
- 方法
- 关键结果 1 / 关键结果 2
- 证据与图表
- 限制与未来工作
- 结论
- 参考文献/附录

角色数量和顺序必须服从 `slide-workorder.json` 的页数和模式要求。若 workorder 给定了页级规范，以 workorder 为准。

#### 4.2.3 模板与编辑
- 模式为 `generate`：优先以 `target-template.pptx` 为基础。保留母版、布局、配色、页脚、logo 和默认字体策略。
- 模式为 `edit` / `adapt`：以 `starting-deck.pptx` 为基础。不得删除母版、不得重建整个文件。仅修改或添加必要 slide；保留组织方模板继承关系。
- 标题/正文优先使用模板 layout 的 placeholder；不额外插入覆盖模板的硬编码 textbox。
- 若模板槽位不足：记录 `template_slots_insufficient`，使用最接近的 layout，并在 `template_check` 中说明。
- 字体缺失：列出替换字体，写 `fonts_inherited = warn`，不要因此放弃整版。
- 页脚/页码/配色：不得覆盖为默认 Calibri 或无主题色。

#### 4.2.4 生成产物
- `presentation.pptx`
- `presentation.pdf`（若环境有 LibreOffice/Soffice；否则 null）
- `content_map.json`：页级主张、来源、备注、bullet 证据。
- `evidence_table.json`：抽取证据清单。
- `plan_v0.json`：页序和角色规划。
- `page_golden.json`：页级金标准检查。
- `page_diff.md`：与起点稿/计划稿的差异。
- `version_history.md`：版本与修改记录。
- `export_check.json`：PDF 页数、溢出、字体等。
- `template_check.json`：模板继承、母版、布局检查。
- `run.log`：完整运行日志。

### 4.3 SELFCHECK：契约与产物自检

提交前必须核对：
1. `result.json` 合法 JSON。
2. `result.json` 顶层包含 `case_id` + 全部 `output_contract` 字段。
3. `result.json.output_contract` 对象中同样包含这些字段。
4. 磁盘上存在 `presentation.pptx`。
5. `content_map` 的每个 slide 有 `slide_index`、`role`、`title`、`notes`。
6. 每条 `bullets` 中 `kind=source` 的条目有逐字 `quote` 和 `locator`。
7. 页数符合 workorder 或已记录页数偏离。
8. 若 PDF 存在，`export_artifact.pages` 与 PPTX 页数一致或偏差已说明。
9. 所有材料缺失、模板缺失、渲染失败、字体替换、OCR 不足等均已记录。
10. status 取值合法：`ok` / `partial` / `insufficient_evidence`。

---

## 5. `result.json` 契约与双回显

### 5.1 顶层字段
必须出现的根字段：
```json
{
  "case_id": "string",
  "status": "ok | partial | insufficient_evidence",
  "editable_source": {},
  "export_artifact": {},
  "content_map": [],
  "compliance_checks": {},
  "exceptions": [],
  "errors": [],
  "degradations": [],
  "pending_human": [],
  "uncertainty": [],
  "sources": [],
  "changes": [],
  "runtime": {},
  "reviewed_by_agent": {},
  "output_contract": {}
}
```

### 5.2 嵌套 `output_contract`
`)`
必须原样回显题面要求的所有根字段，至少：
```json
{
  "output_contract": {
    "case_id": "string",
    "status": "ok | partial | insufficient_evidence",
    "editable_source": {},
    "export_artifact": {},
    "content_map": [],
    "compliance_checks": {},
    "exceptions": []
  }
}
```

### 5.3 关键字段内容

#### `editable_source`
- `path`: `/app/output/presentation.pptx`
- `format`: `pptx`
- `bytes`: 文件大小
- `sha256`: 文件哈希
- `slides`: 实际页数
- `mode`: `generate` / `edit` / `adapt`
- `template_source`: `target-template:<name>` / `starting-deck:<name>` / `builtin-default`
- `template_inheritance`: `ok` / `warn` / `fail`

#### `export_artifact`
- `path`: `/app/output/presentation.pdf`
- `format`: `pdf`
- `pages`: PDF 页数
- `bytes`: 文件大小
- `method`: `soffice_headless` / `unavailable`
- `degraded`: true/false

#### `content_map[i]`
- `slide_index`: 1-based
- `role`: 叙事角色
- `title`: 页面标题
- `layout`: 模板 layout 名或 built-in
- `notes`: 演讲备注
- `bullets`: 数组，元素含：
  - `text`: 页面正文
  - `quote`: 原文逐字证据
  - `locator`: `S#p.页号#段落号/节/图/表`
  - `verified`: true/false/null
  - `kind`: `source` / `front_matter` / `synthesis`
- `figures`: 图表引用，如 `S1#Fig.2`

#### `compliance_checks`
至少包含：
- `template`: `{ pass, warn, fail, message, font_substitution: [] }`
- `slide_count`: `{ expected, actual, pass, message }`
- `export`: `{ pass, message, text_overflow: [] }`
- `source_preservation`: `{ pass, message }`
- `contract`: `{ pass, missing_fields: [], message }`

---

## 6. 证据与来源定位规则

1. 每个实质性 bullet 必须带 `[S#]`。
2. 数字、单位、统计量、图表编号、图注：不得四舍五入、不得按印象重写。
3. 引用原文时，`quote` 必须是源文本的逐字子串。若原文跨行、连字符或 PDF 抽取噪声，需在 `uncertainty` 中说明。
4. `locator` 使用 `S#p.<页码>#<节/段/表/图>`。例如：
   - `S1#p.4 §Methods para2`
   - `S2#Fig.3 caption`
   - `S3#Table 2 row 5`
5. 源中无图、图无法读取、图注缺失：不得画占位图或生成曲线。写：
   - `figure_not_available_in_source`
   - `figure_bitmap_no_vector`
   - `figure_caption_missing`
6. 扫描 PDF 无文本层：不使用臆造文本；写入 `scanned_no_text_layer`、`LOW_SOURCE_TEXT`，状态可为 `insufficient_evidence`。

---

## 7. 异常与降级处理

| 情况 | 降级动作 |
|---|---|
| `case.json` 缺失/损坏 | 继续运行；记录 `NO_CASE_JSON`；`case_id` 用可识别值或 `unknown` |
| `slide-workorder.json` 缺失 | 从 task.md 推断 total slides；否则默认 8 页；记录 `WORKORDER_MISSING` |
| 源文本为空或 <4 句 | 生成最小通知 deck；status=`insufficient_evidence`；记录 `LOW_SOURCE_TEXT` |
| 无 `target-template.pptx` | 使用 `references/deck-parts.json` 内置 16:9 设计；`template_source=builtin-default` |
| 模板损坏 | 回退内置设计；记录 `template_unreadable` |
| mode=edit/adapt 但无 `starting-deck.pptx` | 降级为 generate；记录 `EDIT_WITHOUT_STARTING_DECK` |
| PDF 无文本层 | 不 OCR；记录 `scanned_no_text_layer`；降低可核验完整度 |
| 图片无法取数 | 不重绘、不猜测；记录 `figure_not_available_in_source` |
| `soffice` 缺失或渲染失败 | 保留 PPTX；`export_artifact` 置 null；记录 `PDF_RENDER_UNAVAILABLE` |
| 字体缺失 | 记录替换字体；`template_check.font_substitution`；`overall_pass` 仍可 true |
| 页数超限或过少 | 保留 workorder 约束；若无法满足，记录 `SLIDE_COUNT_DEVIATION` |
| 脚本异常 | 捕获异常；强制写 `result.json`；status=`partial`；`errors` 含 traceback；exit 0 |
| 超时 | 保留已生成产物；写 partial result；记录未完成项 |

任何情况下，`result.json` 必须可解析，且 `case_id` 字段存在。

---

## 8. 预算策略：先交付后增强

### 8.1 必须预算
- INIT：1–2 次模型调用。
- 运行主脚本：1 次工具调用（脚本内部无模型调用）。
- 阅读/核验关键来源：2–4 次。
- SELFCHECK / result 回填：1–2 次。

### 8.2 可选预算
- 写 `draft.json` 或 `agent_review.json`：2–3 次。
- 高置信度修正：最多 2–3 次。
- 不要反复重跑 PPTX 以求“美观”；先保证契约完整和证据准确。

### 8.3 单次响应控制
- 不要在单次响应中输出完整源文件。
- 只输出关键句子、引用、审查结论、JSON 摘要。
- 每次响应控制在 16384 tokens 内。

---

## 9. 自检清单（SELFTEST）

提交前逐项确认：

- [ ] `presentation.pptx` 存在且非空。
- [ ] `presentation.pdf` 存在，或已记录 `PDF_RENDER_UNAVAILABLE`。
- [ ] `result.json` 可被 JSON 解析。
- [ ] 顶层 `case_id` 与 `output_contract.case_id` 都存在。
- [ ] 顶层与嵌套都包含 `editable_source`、`export_artifact`、`content_map`、`compliance_checks`、`exceptions`。
- [ ] `content_map` 页数与 PPTX 页数一致，或差异已记录。
- [ ] 每条 `kind=source` bullet 有 `quote` 和 `locator`。
- [ ] 所有关键数字/图注/引用编号都有来源。
- [ ] 所有缺失、降级、异常都在 `exceptions` / `degradations` / `pending_human` 中。
- [ ] `run.log` 写到最后一步。
- [ ] 没有空文件伪装成产物。
- [ ] 没有自造分数、白板、金标准或 benchmark 数值。

---

## 10. 包内文件与生态复用

本包只使用以下真实资源：

### 脚本
- `scripts/main.py`：CLI 主入口、编排、步骤日志、异常兜底。
- `scripts/discover.py`：输入发现、输出目录、契约回显。
- `scripts/build.py`：页面规划、计划回放、OOXML 打包。
- `scripts/deckkit.py`：读取器、句子/章节分析、形状构建。
- `scripts/gold.py`：金标准、diff、版本历史。
- `scripts/checks.py`：导出/渲染与模板检查。

### 参考资源
- `references/deck-parts.json`：OOXML shell 与内置设计。
- `references/slide-planning.md`：角色分类、排序、预算、编辑策略。
- `references/result-and-checks.md`：结果 schema、定位语法、异常代码。
- `references/golden-and-checks.md`：`page_golden` / `page_diff` / `export_check` / `template_check` schema。

这些文件已覆盖模板兜底、结果契约、自检和版本记录要求。若脚本失败，也按上述 schema 手工补齐最小合法交付物。

---

## 11. 最终交付判断

你的最终状态只有三种：

- `ok`：PPTX/PDF 齐备，页数吻合，模板继承通过，证据链完整，无未解决异常。
- `partial`：有产物，但存在渲染失败、模板偏差、证据缺口、页数偏差、或 agent 未完全核验。
- `insufficient_evidence`：源材料几乎不可用、文本层缺失、或无法形成可信幻灯片。

不要为了“好看”而写 `ok`。真实、可复核、可回退，比虚假完整更得分。