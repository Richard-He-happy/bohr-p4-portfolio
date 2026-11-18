# 字段字典与锚点规范 / Field dictionary and anchor spec

版本 1.0.0。`scripts/main.py` 产出 4 个文件，本文件说明每个字段的含义、取值、判定规则与复用方式。

## 1. 文件与角色

| 文件 | 角色 | 是否可编辑 |
|---|---|---|
| `result.json` | 机器可读主结果：契约回填、claims、paper_card、section_notes、figures、gaps、uncertainty、pending_human、errors、degradations、changes、coverage、sources、runtime | 是（人工复核后可补 `pending_human`） |
| `notes.md` | 人读主产物：运行信息 → 论文卡片 → 章节地图 → 逐章笔记 → 图表 → 缺口 | 是（版式来自 `notes_template.md`） |
| `claims.csv` | 证据表，一行一条 claim，可直接导入表格/知识库 | 是 |
| `verify_report.json` | 本次运行自检：`quote_hit`、`contract_keys`、`missing_claim_fields`、`artifacts_exist`、`pass` | 否（每次运行重写） |

## 2. claim 字段（result.json `claims[]` / claims.csv 列）

| 字段 | 类型 | 说明 |
|---|---|---|
| `claim_id` | str | `c001` 起顺序编号，同输入可复现 |
| `kind` | enum | `research_question` `hypothesis` `data_sample` `method` `result` `conclusion` `limitation` `definition` `availability` `funding_coi` `figure_caption`（命中多类时取优先级最高者，其余进 `also_matches`） |
| `statement` | str | 结论陈述；本 Skill 直接使用原文句（`statement_mode: verbatim_quote`），避免改写导致的事实漂移 |
| `quote` | str | **逐字**原文句（仅空白归一化）。改写、拼接、翻译后的引用一律不允许 |
| `source_id` | str | `src01`…对应 `sources[].source_id`；图片为 `img01`…（不产生 claim） |
| `location.page` / `page_end` | int | 句首/句尾所在页（1 起） |
| `location.section_id` / `section_title` / `section_kind` | str | 所属章节与类型（abstract/intro/methods/results/discussion/conclusion/limitation/references/ack/front/other） |
| `location.sentence_index` | int | 该章节内第几句（1 起，按 `doctext.split_sentences` 的确定性切分） |
| `location.char_start` / `char_end` | int | 在拼接抽取文本中的字符偏移；`coverage.page_map[]` 给出每页 `char_start` 与字符数，据此可还原页码与页内偏移 |
| `location.anchor` | str | `source_id:p<页>/<S 章节>/s<句序>`，例如 `src01:p4/S6/s2` |
| `location.pointer` | str | JSON Pointer，例如 `/claims/12` |
| `conditions[]` | [str] | 原文条件片段：`n = 12`、`p < 0.01`、`at 50 mM`、`1200 micromol ...` 等；不改单位、不换算 |
| `numbers[]` | [{raw, unit}] | `raw` 为原文数字串（可能含单位），`unit` 为可选单位组；不重算、不补精度 |
| `readability` | enum | `directly_read`：原文直接可读；`inferred`：由结构推断（章节用途等）；`undetermined`：无法确定（图表元素、缺失字段、低质量页） |
| `confidence` | float | 抽取排序分（0.5–0.96），用于卡片取值的先后；不是统计置信度 |
| `verified_quote_hit` | bool | `quote` 是否在抽取文本中命中；`false` 时进 `pending_human` |

## 3. 其他结构

- `paper_card.<field>`：`{value, claim_ids[], status, readability, pages[]}`；`status ∈ {reported, not_found_in_extracted_text}`；`value` 是原文逐字句。
- `section_notes[]`：章节级索引，`readability: inferred` 表示"章节用途"为推断而非原文陈述。
- `figures[]`：`{label, caption, page, anchor, elements}`；`elements: "not_parsed"` 明确表示轴类型/图例/误差线/比例尺/子图编号**未解析**，不得当成已核实的图内数据；图内数值一律不写。
- `gaps[]`：`{field, status, note, readability}`，`note` 固定说明"无匹配线索句；视为提取缺口而非原文未报告"。
- `uncertainty[]`：`{item, severity, basis, readability}`；`pending_human[]`：`{item, reason, suggested_action, pointer}`。
- `coverage`：`sections_total / sections_with_claims / section_kinds / claims_total / quote_verified / quote_hit_ratio / card_fields_reported / card_fields_total / figure_captions / gaps / documents_read / images_not_read / errors / degradations / text_quality / page_map`。
- `status` 判定：`garbled` 文本或无可靠 claim → `insufficient_evidence`；命中率 <0.8、章节覆盖不足、或无标题 → `partial`；无材料/无契约可解析但材料不可读 → `input_error`；其余 `ok`。

## 4. 可读性判定规则（三分类的边界）

1. `directly_read`：句子完整出现在抽取文本中，且 `verified_quote_hit = true`。
2. `inferred`：由结构或规则推出，例如"这一章是 Methods"、"该字段属于结论"；只写在 `section_notes` / `paper_card.status` 等元数据位，不写进 `quote`。
3. `undetermined`：图表元素、缺失卡片字段、低质量页、加密/扫描导致的缺章；必须同时出现在 `uncertainty` 或 `pending_human` 或 `gaps` 中。

## 5. 复用方式

- 建库：`claims.csv` 直接导入（一行一条，含页码/章节/偏移）。
- 多篇比较：以 `paper_card` 的 9 字段并排，`status` 区分"有据/缺口"。
- 复核：按 `anchor` 回到 `sources[].path` 的对应页；或重跑 `--check` 比对 `same_claim_ids`。
- 改判：人工修改 `readability` 或补 `value` 时，同步更新 `verify_report.json` 之外的证据字段，避免 `quote` 被改写。

## 6. 已知失败样例（诚实记录）

| 现象 | 本文档中的记录位置 | 处理 |
|---|---|---|
| 扫描件无文字层 | `sources[].quality = low_text`，`uncertainty` 一条，`pending_human` 建议 OCR | 不虚构句子 |
| 加密 PDF | `errors` 一条 `pdf_error: encrypted /Encrypt` | 跳过该文件，其它材料继续 |
| 图表数值 | `figures[].elements = "not_parsed"` | 需人工/视觉工具读数 |
| 无标题排版 | `status_reasons: headings_not_detected`，`section_notes` 只有 `S1 Full text` | 提示人工标注标题行 |
| 参考文献 | 不进入 claims（`references` 章节整体跳过） | 避免把引文当研究结论 |
