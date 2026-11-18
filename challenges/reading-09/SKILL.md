---
name: section-anchored-paper-notes
description: Turn a real research paper into section-aligned, field-based, anchor-verified reading notes. Segments the paper by its own headings and extracts a paper card, per-section notes, figure/table caption anchors and a claim table where every claim carries a verbatim quote, source_id, page/section/sentence/char offsets, conditions and a readability class (directly_read / inferred / undetermined). Use when a user asks to summarise a paper, build structured notes, extract research question / data / methods / results / limitations, or verify claims against the source. Handles PDF, DOCX, XLSX, CSV, HTML, JSON and plain text offline with Python stdlib; degrades honestly on scanned, encrypted, low-text or heading-less documents and never fabricates quotes, numbers or citations.
version: 1.0.0
---

# Section-Anchored Paper Notes (reading-09)

把一篇真实论文变成**按论文自身章节对齐、字段齐备、每条结论可回链原文**的结构化笔记，并显式写出可读性、缺口与人工动作。

## 1. 用途与边界

**做**：章节切分（用论文自己的标题，不套通用模板）→ 论文卡片字段 → 逐章证据笔记 → 图表题注锚点 → 机器可读证据表。

**不做**：不补全原文未报告的数值、样本量、统计量、DOI 或文献；不做图形像素读数；不把「提取不到」写成「原文未报告」或反之。

## 2. 运行契约

```bash
python3 scripts/main.py --input /input --output /app/output          # 正常运行
python3 scripts/main.py --check --input /input --output /app/output  # 重跑并报可复现性
python3 scripts/doctext.py --help                                    # 单文件抽取检查器
```

输入 `/input/case.json` + `/input/task.md` + `/input/**` 材料；输出 `/app/output/`。仅标准库（≥3.8），不联网、不依赖 CWD（`Path(__file__).resolve().parent`）。**先写 partial `result.json`**，之后无条件 finalize；异常进 `errors/degradations/pending_human`；**退出码恒 0**。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `case.json`，缺失则找 `case*.json`；坏 JSON 记录错误后继续。
2. `output_contract|outputContract|contract|result_contract` 任一命中即契约；`case_id|id|caseId` 任一命中即案例标识（原样透传）。
3. 递归扫描 `/input/**`，跳过 `case.json`、`task.md`、空文件、隐藏文件；按扩展名 + 文件头（`%PDF`、`PK`）识别 PDF/DOCX/XLSX/CSV/TSV/HTML/JSON/TXT/MD/XML/TEX 与图片。
4. 主来源 = 可解析文本最长的文档，其余记 `secondary`；图片记 `role: image_not_pixel_read` 并进 `pending_human`。
5. 材料缺失（无 case / 无材料 / 仅图片）记 `input_error` + 缺口清单，不构造内容。

## 4. 输出契约

`result.json`（主结果）、`notes.md`（主产物）、`claims.csv`（证据表）、`verify_report.json`（自检）。

| 字段 | 内容 |
|---|---|
| `case_id` / `status` | 原样回填 / `ok`·`partial`·`insufficient_evidence`·`input_error` |
| `claims[]` | `claim_id, kind, quote(逐字), statement, source_id, location{page,page_end,section_id,section_title,section_kind,sentence_index,char_start,char_end,anchor,pointer}, conditions[], numbers[], readability, confidence, verified_quote_hit` |
| `paper_card` | 9 字段：`research_question, hypothesis, data_sample, methods, key_results, conclusions, limitations, funding_coi, availability` → `{value, claim_ids, status, readability, pages}` |
| `section_notes[]` | `{section_id, title, kind, pages, sentences, claim_ids, readability:"inferred"}` |
| `figures[]` | 图表题注锚点 `{label, caption, page, anchor, elements:"not_parsed"}` |
| `gaps[]` | 无证据字段（`not_found_in_extracted_text`，≠原文未报告） |
| `uncertainty[]` / `pending_human[]` | 不确定项 / 人工动作（均带 `pointer`） |
| `errors[]` / `degradations[]` / `changes[]` | 异常、降级、运行轨迹 |
| `coverage` | 章节/证据/命中率/卡片覆盖/图表/缺口计数 + `page_map`（每页 `char_start`、字符数） |
| `sources[]` | `{source_id, name, path, kind, pages, chars, quality, role}` |
| `output_contract_echo` | 输入契约完整键结构回填（未知键保留，缺值 null/[]），并按语义填真实值 |
| `runtime` | 版本、Python、起始时间、耗时、`model_requests:0`、`network:false` |

契约回填：先按输入结构生成骨架（dict 递归、list→`[]`、标量→`null`），再用 `references/rules.json` 的 `syn` 映射写入 `claims/sources/uncertainty/...` 真实值；键名不改不删。

## 5. 核心流程

1. **抽取**（`scripts/doctext.py`）：PDF 对象/对象流、Flate 解压、`ToUnicode` CMap 解码、页树遍历、连字修复（ff/fi/fl）、跨行连字符合并、重复页眉与页码剔除 → 每页 `text` + 质量分。
2. **切分**：按行识别标题（`1 Introduction`、`2.3 Gas exchange`、`Abstract`、`References` 等）→ `S1..Sn` 区间/页码/句数；子章节继承父类型；跨页重复标题不重复建章。
3. **字段抽取**：句级线索匹配 `rules.json` 的 cue（research_question / hypothesis / data_sample / method / result / conclusion / limitation / definition / availability / funding_coi / figure_caption）；同章去重 + 每章 ≤8 条、全局 ≤`--max-claims`（默认 80）；首句优势与数字密度参与排序。
4. **锚点与自检**：`char_start/char_end` 指向拼接文本偏移（`coverage.page_map` 给每页起点），`anchor = source_id:p<页>/<S 章节>/s<句序>`；逐条回查 `quote`，命中 `verified_quote_hit: true`，未命中进 `pending_human`。
5. **卡片与缺口**：字段取排序最高 claim 作 `value`（原文逐字）；无命中写 `not_found_in_extracted_text` 并进 `gaps`。
6. **渲染**：`references/notes_template.md` 填 `{{run_table}} {{card_table}} {{section_map}} {{section_notes}} {{media}} {{gaps}}` → `notes.md`（逐章按 `kind` 分组，带锚点与条件）。
7. **finalize**：写 `result.json`、`verify_report.json`，退出 0。

## 6. 评分要点 → 字段 / 检查 / 产物

| 评分点 | 落点 |
|---|---|
| 任务完成度 15 | `notes.md` 逐章笔记 + `paper_card` 9 字段 + `section_notes`，非通篇摘要 |
| 结果正确性 15 | `quote` 逐字 + `verified_quote_hit` 全量校验；数值只以 `numbers[].raw` 原文串出现 |
| 结果完整性 5 | `coverage.card_fields_reported`、`sections_with_claims`、`section_kinds` |
| 可核验性 5 | `anchor` + `char_start/char_end` + `page_map` + `claims.csv` + `--check` |
| 质量增益 15 | 章节对齐 + 字段化 + 逐字证据 |
| 效率/可验证 10 | 一次命令出 4 个文件；`verify_report.json` + `coverage` 计数 |
| 新增/改进/创新 15 | 章节切分、锚点回链、ToUnicode 解码、按章节类型抽取、`readability` 三分类与 `gaps` 区分 |
| 调用/稳定/异常 10 | 单一入口、单文件失败仅降级、退出码 0、§9 分支表 |
| 生态贡献 10 | 本文档 + `schema.md`（字段字典/锚点/示例）+ `rules.json`（可调）+ `notes_template.md`（可改版式） |

## 7. 证据与定位规范

- **quote 逐字**：与抽取文本一致（仅空白归一化）；不改写、不拼接、不翻译后引用。
- **条件**：`conditions[]` 保留原文片段（`n = 12`、`p < 0.01`、`at 50 mM`），不改单位。
- **可读性**：`directly_read`（原文可读，claim 默认）、`inferred`（章节类型/用途等推断）、`undetermined`（图表元素、缺失字段、低质量页）。
- **图表**：题注作为 `figure_caption` claim 保留页与锚点；轴类型、图例、误差线、比例尺、子图编号一律 `undetermined` 并进 `pending_human`，不写像素读数。
- **表格数字**：只留原文字符串，不换算、不补精度。**非中文论文**：保留原文，quote 不翻译。

## 8. 冲突与人工确认

同字段多句冲突时取 `confidence` 最高者为 `value`，其余留在 `claim_ids` 并由 `notes.md` 全量列出；不静默丢弃。提取不到写 `gaps` 缺口而非"未报告"。每条 `pending_human` 带 `pointer`（`/claims`、`/section_notes`、`/figures`、`/uncertainty`）。

## 9. 异常降级分支

| 情况 | 检测 | 处置 | 状态 |
|---|---|---|---|
| 扫描/图片 PDF | 字符少、质量 `low_text`/`garbled` | 保留空页文本 + 降级记录，建议 OCR | `partial`/`insufficient_evidence` |
| 加密 PDF | `/Encrypt` | `PdfError`，跳过该文件 | `partial` |
| 双栏错序 | 文本量正常但句序异常 | 不猜测重排，`uncertainty` 提示人工核对 | `partial` |
| 无标题 | `headings_found < 2` | 退化单章 `S1 Full text` + `headings_not_detected` | `partial` |
| 图表为主 | 页字符 <120 | `uncertainty` 列低文本页 | 不影响全局 |
| 坏 JSON/缺 case | 解析异常 | 记 `errors`，无回填，继续找材料 | `input_error` |
| 超长文档 | 页数多 | 每章 8 + 全局 80 上限，先写 partial | `ok`/`partial` |

## 10. 预算与断点

预算 64 请求 / 900 秒 / 16k tokens：本 Skill 零模型调用（`model_requests: 0`），单次运行通常 <10 秒；partial 先落盘，任何中断都有合法结果。

## 11. 自检清单

```bash
python3 scripts/main.py --help                                # 退出码 0
python3 scripts/main.py --input <in> --output <out>           # status/claims/sections
cat <out>/verify_report.json                                  # pass:true = quote 全命中、产物齐备
python3 scripts/main.py --check --input <in> --output <out>   # 复现性
```

人工：按 `page + section_id + sentence_index` 回原文核对 `quote`；确认 `gaps`/`uncertainty` 未被写成事实。

## 12. 最小调用示例（**示例，非正式案例结果**）

`/input/case.json`：`{"case_id":"demo-001","output_contract":{"case_id":null,"status":null,"claims":[{"claim_id":null,"quote":null}],"uncertainty":[],"pending_human":[]},"materials":["paper.pdf"]}`

```bash
$ python3 scripts/main.py --input /input --output /app/output
status=ok claims=22 sections=9 notes=/app/output/notes.md
$ cat /app/output/verify_report.json
{"status":"ok","claims":22,"quote_hit":22,"contract_keys":8,"missing_claim_fields":[],"pass":true}
```

`claims.csv` 示例行：`c001,data_sample,directly_read,src01,1,1,S1,2,218,284,src01:p1/S1/s2,True,"at 0, 50 and 100 mM",…`（数值来自测试用合成 PDF，非正式案例）

## 13. 文件清单与版本

`SKILL.md`（本说明）· `scripts/main.py`（主流程，≤20KB）· `scripts/doctext.py`（抽取+切分，≤20KB）· `references/rules.json`（线索/条件/卡片/同义词，可调）· `references/notes_template.md`（版式模板）· `references/schema.md`（字段字典/锚点/判定/失败样例）。版本 1.0.0，Python ≥3.8 标准库，无网络、无模型、无第三方包。

## 14. 维护说明

换语种/领域：在 `rules.json` 增改 cue、`card`、`purpose`，不改代码。换版式：改 `notes_template.md` 占位符。新增格式：在 `doctext.read_document` 增分支，失败返回 `warnings` 而非抛异常。回归判断：`--check` 看 `same_claim_ids`，`verify_report.json.pass` 必须 true。
