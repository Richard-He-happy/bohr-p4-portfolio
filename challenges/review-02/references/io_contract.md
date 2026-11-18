# 输入输出契约（review-fact-check）

## 1. 输入发现

| 位置 / 键 | 用途 | 缺失时 |
|---|---|---|
| `/input/case.json`（或 `**/case*.json`） | `case_id`、`output_contract`、任务说明、材料清单 | 继续运行，`errors[]` 记一条 |
| `/input/task.md` | 任务与检查范围 | 用 `task_instruction` 等字段替代 |
| `/input/**` 其他文件 | 论文全文/节选/补充材料 | 逐文件降级并记 `degradations[]` |
| `case.json` 内的 `text`/`content` 长字符串 | 内联材料正文 | — |
| `case.json` 内 `path/file/uri/artifact` | 期望材料 | 不存在则记 `uncertainty[]`（材料缺口） |

支持的抽取：PDF（`pdftotext -layout` → `-raw` → 内置 zlib 解析）、DOCX（`word/document.xml`）、XLSX（sharedStrings + worksheets）、CSV/TSV/JSON/MD/TeX/HTML/BIB（纯文本）、PNG/JPG/TIFF（`tesseract`，缺失即降级）。`case.json`、`task.md`、`material.json` 不当作稿件内容。

## 2. `result.json` 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `skill` | obj | `{name, version}` |
| `case_id` | str | 原样透传；缺失为 `unknown_case` |
| `status` | enum | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `task_summary` | obj | 输入/输出目录、备注 |
| `issues` | list | 问题清单（见 §3），按发现顺序编号 |
| `review_summary` | obj | 计数与覆盖率（见 §4） |
| `citation_support_matrix` | list | 句子→引用配对（见 §5） |
| `evidence_index` | obj | `issue_id → {doc, locator, quote, rule_id}` |
| `pending_human` | list | `{issue_id?, pair_id?, why, need}` |
| `uncertainty` | list | `{doc, item, reason}`：未检查项与输入缺口 |
| `sources` | list | `{id, name, extractor, chars}` |
| `errors` | list | `{stage, file?, error}`；非空时 `status` 不得为 `ok` |
| `degradations` | list | `{stage, file, note}`：可读性/OCR/格式降级 |
| `changes` | list | 本轮做了什么 |
| `rejected_findings` | list | 第二遍被拒绝的 findings 及原因 |
| `output_contract` | obj | 输入的 `output_contract` 结构，键名原样 |
| `contract_unmapped_fields` | list | 未识别/无值字段及原因 |
| `verification` | obj | `{checked, passed, failed, ok, failures[]}` 自检结果 |
| `runtime` | obj | `generated_at`、`elapsed_sec`、`python`、`script`、目录 |
| `artifacts` | obj | 产物相对路径 |

## 3. issue 对象

```json
{"issue_id":"R-001","kind":"fact_check","severity":"major","certainty":"confirmed",
 "status":"issue","rule_id":"fact.percent_fraction_mismatch","doc":"paper.pdf","page":"p3",
 "paragraph":12,"offset":10412,"locator":"paper.pdf#p3/para12@char10412","section":"results",
 "quote":"12% (n=5/60) of samples responded","claim":"百分比与分数不一致：12% 与 5/60（应为 8.3%）",
 "reason":"百分比与分数不一致：12% 与 5/60（应为 8.3%）","suggested_fix":"按 5/60 重算并同步正文、表格与图注",
 "lang":"zh"}
```

- `kind` ∈ `fact_check | citation_support | method_design | stats_report | argument_chain | academic_norm`
- `severity` ∈ `major | minor | info`；`certainty` ∈ `confirmed | likely | needs_human`
- `status` ∈ `issue | pending_human`；`pending_human` 必同时出现在顶层 `pending_human[]`
- `locator` 语法：`<文件>[#<页>][/para<段>]@char<字符偏移>`，无分页时省略页段
- `quote` 必须逐字来自原文（允许空白与大小写差异），由 `verify.py` 逐条复核

`issues.csv` 使用相同字段（UTF-8-SIG，便于 Excel 直接打开）。

## 4. review_summary

```json
{"documents":2,"characters":41233,"issues_total":14,
 "by_severity":{"major":3,"minor":9,"info":2},
 "by_kind":{"fact_check":2,"citation_support":4,"method_design":3,"stats_report":3,"argument_chain":1,"academic_norm":1},
 "pending_human":7,"citation_pairs":18,"language":"en",
 "coverage":{"stats_report":{"rules":["stats.p_zero","stats.no_effect_size"],"findings":3}, "...":"..."},
 "numeric_checks":{"fraction_pairs":6,"p_values":11,"n_mentions":4,"percent_mentions":23},
 "sections_found":{"paper.pdf":["abstract","introduction","methods","results","discussion","references"]},
 "agent_findings_merged":0,"agent_findings_rejected":0}
```

覆盖率说明：`coverage[kind].rules` 是本轮**实际命中**的规则 ID；未命中不代表未执行（`checks.json` 中全部 pattern 每轮都跑），而 `uncertainty[]` 记录因缺章节/缺材料而跳过的范围。

## 5. citation_support_matrix

```json
{"pair_id":"CP-003","doc":"D1","claim_quote":"...thus X causes Y in patients",
 "claim_locator":"paper.pdf#p6/para4@char20114","citation":"[17]","ref_number":17,
 "ref_raw":"Smith J, et al. A review of X. J Example. 2021;12:34-56. doi:10.1000/xyz",
 "ref_year":"2021","ref_is_review":true,"verdict":null,"verdict_reason":null,
 "requires_semantic_judgment":true,
 "needs":"read the cited source; decide full/partial/none/undetermined with evidence"}
```
`verdict` 只有四种：`full` / `partial` / `none` / `undetermined`。第一遍一律 `null`（不预设结论）；第二遍由语义审查写入。未判定的配对会进入 `pending_human[]`。

## 6. findings JSON（第二遍）

`python3 scripts/main.py --findings <file>` 合并。文件结构：

```json
{"findings":[{"kind":"citation_support","severity":"major","certainty":"likely",
  "quote":"逐字原文片段","claim":"该句把综述结论表述为因果结论","suggested_fix":"改引原始研究或降级表述",
  "rule_id":"semantic.review_causal","status":"issue"}],
 "citation_verdicts":[{"pair_id":"CP-003","verdict":"partial","reason":"原文仅支持相关性，未支持剂量效应"}]}
```

合并规则：
- `quote` 在源文本中找不到 → 拒绝，写入 `rejected_findings[]` 与 `pending_human[]`，**不**作为 issue 出现；
- `kind`/`severity` 不在枚举内 → 用默认值并保留原文字段在 `claim` 中；
- `rule_id` 自动加前缀 `agent.`，便于区分"规则命中"与"人工语义判定"；
- `citation_verdicts` 只对已存在的 `pair_id` 生效，未知 ID 忽略。

## 7. 契约回填规则

`output_contract` 的键名**永不改写**，按语义匹配填值（`checks.json.contract_rules`，可扩展）：

| 键名含 | 填入 |
|---|---|
| `case_id` | `case_id` |
| `csv` | `issues_csv_path` |
| `report`/`markdown`（含 `path/file` 时取路径，否则取正文） | `review_report.md` |
| `issue`/`finding`/`problem`/`意见`/`问题` | `issues` |
| `citation`/`reference`/`引用` | `citation_support_matrix` |
| `evidence`/`locator`/`quote`/`证据` | `evidence_index` |
| `summary`/`count`/`stat`/`coverage`/`概要` | `review_summary` |
| `pending`/`human`/`待复核` | `pending_human` |
| `uncertain`/`limitation` | `uncertainty` |
| `source`/`material`/`来源` | `sources` |
| `status`/`state`/`状态` | `status` |
| `error` / `degrad` / `change` / `runtime` | 对应字段 |

未识别键保留为 `null`，并在 `contract_unmapped_fields[]` 写明原因；嵌套 dict 递归回填，字符串数组按字段名映射。

## 8. 命令与退出码

```bash
python3 scripts/main.py --input /input --output /app/output            # 主流程
python3 scripts/main.py --input /input --output /app/output --findings work/findings.json
python3 scripts/verify.py --input /input --output /app/output          # 文本摘要
python3 scripts/verify.py --input /input --output /app/output --json   # 完整报告
```
两个脚本**退出码恒为 0**（异常写入 `errors[]`）；`verify.py` 的判定体现在输出文本与 `--json` 的 `ok` 字段。

## 9. 排查表

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `status=input_error` 且 `issues` 为空 | 输入目录无可读材料 | 检查 `degradations[]`；扫描件需 OCR |
| PDF 抽取为空 | 无文本层 / `pdftotext` 缺失 | 看 `degradations[]`；装 `poppler-utils` 或提供文本版 |
| `citation_pairs` 为空 | 未识别到参考文献章节或引用格式异常 | 检查 `sections_found`；参考文献标题需单独成行 |
| 引用编号全部"越界" | 稿件为作者-年份制，或编号从 0 开始 | 作者-年份制走 `citation.entry_missing` 分支，不按编号判 |
| `verify.py` 报 `quote_resolution` | 第二遍 quote 被改动或跨段截断 | 用完整句或短片段重试，不改原文 |
| 契约字段全为 null | 键名与映射表差异过大 | 在 `checks.json.contract_rules` 增补一条正则→字段 |
