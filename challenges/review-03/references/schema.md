# 输入输出契约与字段定义（review-03）

版本 1.0.0。本文件定义 `result.json` 的结构、字段语义、定位符语法，并给出**一份明确标注为示例的**
最小调用与示意输出。示意输出不是任何正式案例的结果。

## 1. 输入发现（不假设固定键名）

运行器按下列顺序发现输入，任一步失败只降级该步：

1. `--input` 指定的目录（默认 `/input`；不存在则试 `./input`；再不存在则试脚本同级的 `input/`）。
2. 主入口：`<input>/case.json`；不存在则递归找 `case*.json`（深度 ≤6，取修改时间最新者）。
   全部缺失 → `status="input_error"`，仍写合法 result.json。
3. 递归扫描 `<input>/**`（深度 ≤6，文件数 ≤400，跳过 `__pycache__`/`.git`/`node_modules`），
   按**扩展名 + 魔数**识别：`.pdf`(25 50 44 46) `.docx`/`.xlsx`(50 4B 03 04) `.json`(7B/5B) `.md` `.txt` `.csv` `.tsv`
   `.png`(89 50 4E 47) `.jpg` `.tif` `.bib` `.ris`，其余按文本尝试解码。
4. case.json 中的文本字段同样视为材料：凡键名语义含 `manuscript|text|content|abstract|body|full_text`
   且值为长度 >200 的字符串，直接作为"内嵌稿件"文档（`locator` 前缀 `inline:`）。
5. `output_contract` 原样透传：键名不改、未知键保留、缺值 `null`（契约暗示数组则 `[]`）。

## 2. `result.json` 顶层结构

| 字段 | 类型 | 说明 |
|-|-|-|
| `case_id` | str | 原样取输入；缺失时 `"unknown"` |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `topic` / `skill_version` | str | 主题标识与 Skill 版本 |
| `input_inventory` | obj | `discovered[]`（路径、类型、字节、解析器）、`inline_texts`、`missing[]` |
| `summary` | obj | 计数与覆盖度，见 §3 |
| `issues[]` | arr | 审查单主表，见 §4 |
| `checks{}` | obj | 六类审查面状态，见 §5 |
| `review_records` | obj | 复核轨迹，见 §6 |
| `sources[]` | arr | 每个被引用的证据源（文档 + 定位） |
| `uncertainty[]` | arr | 每条不确定性：`what` / `why` / `impact` / `resolved_by` |
| `pending_human[]` | arr | 需人工确认的项（含 quote 未命中、材料不足、领域外部信息） |
| `errors[]` / `degradations[]` | arr | 明确失败 / 已降级能力（含替代手段） |
| `changes[]` | arr | 每次运行的行为记录（阶段、写入文件、动作） |
| `runtime` | obj | 耗时、文件数、字节数、引擎 |
| `artifacts` | obj | 主产物相对路径：`review_report` / `issues_csv` / `result` |

其余顶层键按 `output_contract` 补齐。

## 3. `summary`

```json
{"total_issues": 0, "by_severity": {"blocker":0,"major":0,"minor":0,"suggestion":0},
 "by_category": {"fact":0,"citation":0,"design":0,"statistics":0,"logic":0,"norms":0},
 "facet_coverage": {"design":"not_covered","variables":"not_covered","statistics":"not_covered",
                    "sample_size":"not_covered","reporting":"not_covered"},
 "blockers": [], "quote_verified": 0, "quote_failed": 0,
 "reproducibility": "每条 issue 均可由 locator + quote 在源文档中独立定位"}
```

## 4. `issues[]` 单条结构（**主产物**）

| 字段 | 必填 | 说明 |
|-|-|-|
| `id` | ✓ | 确定性编号 `I01`、`I02`…（同一输入重复运行编号一致） |
| `rule_id` | ✓ | 清单 ID（`S-03` 等）；人工项用 `M-*` |
| `category` | ✓ | 六类之一；`facet` | ✓ | 五面之一 |
| `defect_type` | ✓ | 缺陷类型库键（见 `stat_rules.md` §4） |
| `severity` | ✓ | `blocker`/`major`/`minor`/`suggestion` |
| `evidence_strength` | ✓ | `error`/`gap`/`judgment` |
| `title` | ✓ | ≤40 字一句话问题陈述 |
| `locator` | ✓ | 见 §7 | `quote` | ✓ | 逐字原文子串（12–200 字符） |
| `reason` | ✓ | 为什么是问题（引用规范名称或稿件内证据，不编造文献） |
| `suggestion` | ✓ | 可执行的修改动作（改哪句、补什么） |
| `evidence` | ✓ | `{"kind":"absence\|contrast\|numerical","support":"..."}` |
| `confidence` | ✓ | 0–1；`gap` 类上限 0.75，`judgment` 类上限 0.8 |
| `source_id` | ✓ | 指向 `sources[]` |

`evidence.kind` 语义：`numerical` = 稿件内数值对照；`contrast` = 两处原文并列（如结论 vs p 值）；
`absence` = 全文检索未见（必须同时给出检索关键词集合，供复核人重跑）。

## 5. `checks{}` 六类状态项

```json
{"fact": {"status":"checked","scope":"全文 42 段 / 3 表 / 2 图","items":[{"rule_id":"F-01","status":"pass",
  "note":"正文引用的 图1、表2 均存在"}],"findings":["I03"],"open":[]}}
```
`status` ∈ `checked` / `partially_checked` / `not_applicable` / `not_checked`；`not_applicable` 必须有 `reason`。
`items[].status` ∈ `pass`（检查过且无问题）/ `fail`（对应 issue）/ `manual`（需模型判定）/ `skipped`。

## 6. `review_records`

`parser_warnings[]`、`documents[]`（id/路径/类型/段落数/字符数/解析器）、
`citation_match`（正文编号 max vs 条目数）、`stats_audit`（p 值数、CI 提及、检验名、样本量估算）、
`quote_verification`（`checked`/`passed`/`failed` 计数）、`rerun`（`fingerprint` 与是否与上次一致）、
`limits[]`（本次未能检查的内容与原因）。

## 7. 定位符语法（locator）

统一格式 `<doc_id>:<unit>`，`unit` 按文档类型取值：

- 文本/Markdown/DOCX：`¶<段号>`（1 起），可加章节：`§方法:¶37`
- PDF：`p.<页号>/¶<页内段号>`（页码来自 `pdftotext -layout` 分页符；纯 Python 回退时**按内容流顺序估算**，
  此时 `review_records.limits` 必须写入"页码为估算值"）
- 表格（CSV/XLSX）：`r<行号>c<列>`；图：`fig.<图号>`（仅在稿内已定义时使用）
- 内嵌文本字段：`inline:<键名>:¶<段号>`
- 参考文献条目：`refs:#<编号>`

**禁止**：编造页号、表号、图号、文献编号。无法定位的内容不得作为 `issues[]` 输出。

## 8. 最小调用示例（**示例，非正式案例结果**）

输入 `input/case.json`（示例）：

```json
{"case_id":"EXAMPLE-001","topic":"research-methods-and-statistics-review",
 "output_contract":{"case_id":null,"status":null,"issues":null,"summary":null,"checks":null,
                    "sources":null,"uncertainty":null,"custom_hash":"keep-me"},
 "manuscript_file":"artifacts/demo_manuscript.md"}
```

调用（示例）：

```bash
python3 scripts/main.py --run --input input --output output
# → 阶段1：output/result.json(partial) + output/extracted/*.md
# → 阶段2（Agent 读全文后）：python3 scripts/main.py --merge output/issues_model.json --run
# 核验：result.json 的 summary.quote_failed 应为 0（verify.py 是库，由 main.py 调用，不单独运行）
```

示意输出（**示例，非正式案例结果**，仅示字段形态）：

```json
{"case_id":"EXAMPLE-001","status":"ok","custom_hash":"keep-me",
 "issues":[{"id":"I01","rule_id":"S-08","category":"statistics","facet":"sample_size",
   "defect_type":"power_gap","severity":"major","evidence_strength":"gap",
   "title":"未报告样本量估算依据",
   "locator":"demo_manuscript:§方法:¶12",
   "quote":"两组各纳入 40 例患者，比较治疗前后差异。",
   "reason":"方法节未出现样本量估算、效应量来源、α 与把握度表述，无法判断 40 例是否足以支撑组间比较（STROBE 条目 10 要求报告样本量确定方式）。",
   "suggestion":"在方法节补一句：基于既往效应量 d=0.6、α=0.05（双侧）、把握度 80% 计算需每组 45 例，实际纳入 40 例，故本研究为探索性。",
   "evidence":{"kind":"absence","support":"检索词：样本量|sample size|检验效能|power|把握度"},
   "confidence":0.72,"source_id":"doc-001"}],
 "summary":{"total_issues":1,"by_severity":{"blocker":0,"major":1,"minor":0,"suggestion":0}},
 "checks":{"fact":{"status":"checked","items":[{"rule_id":"F-01","status":"pass"}],"findings":[]}}}
```

## 9. 不可用/缺失时的写法（诚实降级）

| 情况 | 写法 |
|-|-|
| PDF 无法抽取文本（扫描件） | `degradations[]` 记 `pdf_text_unavailable`，`uncertainty[]` 记"无法读取正文"，`status="insufficient_evidence"`；仍输出结构化空审查单与缺口清单 |
| 图片/图表不可读 | `pending_human[]` 记图号与需要人工核对的内容；**不猜测坐标或数据点** |
| 无参考文献表 | C-05 = fail（major, gap），其余引用类条目 `not_applicable` 并给 reason |
| 统计输出缺失 | 只报"未报告"（gap），不得推断作者用了什么检验 |
| 语言混杂 | 中英双词表同时启用；不因一侧缺失判 gap |
