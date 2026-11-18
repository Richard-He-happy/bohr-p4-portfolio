---
name: review-fact-check
description: Evidence-bound review of manuscripts and research materials for citation/fact verification. Use when asked to review a paper, judge whether citations actually support their claims, check numbers, sample sizes, statistics, methods, argument chains or academic norms, or produce a structured issue list with locators, verbatim quotes, severity and concrete fixes. Produces result.json plus review_report.md and issues.csv; never invents references, page numbers, statistics or verdicts.
version: 1.0.0
---

# review-fact-check

把"引用与事实核验"做成可交付的审查结果：条目化问题清单（位置 / 原文 / 判定 / 严重度 / 修改建议）+ 引用支持矩阵 + 待复核与未检查项。不做论文润色、不代写综述、不替代作者对结论的判断。

## 1. 用途与边界

**做**：核对正文陈述与被引文献是否对得上（引用支持判定）、数值与百分比自洽、样本量与统计报告完整性、方法设计与论证链、学术规范（伦理/利益冲突/数据可用性/撤稿与预印本状态）、以及"结论是否有原文位置可回查"。
**不做**：不联网检索数据库；不判断论文科学价值；不重写稿件；不在证据缺失时补结论。被引文献正文不在输入中时，"是否支持该句"只能进 `pending_human`，不得凭标题猜测。

## 2. 适用条件与触发

输入包含论文全文/节选/摘要、审稿任务说明、同类科研材料（PDF、DOCX、XLSX、CSV、JSON、Markdown/TeX，或扫描件图片）时触发。用户说"审查这篇稿件""核对这些引用是否支持结论""查数字与统计有没有矛盾""生成审稿意见"均属本 Skill 场景。

## 3. 运行契约

- 入口：`scripts/main.py`；自检：`scripts/verify.py`。均只用 Python 标准库、不联网、不依赖当前工作目录（资源用 `Path(__file__).resolve().parent` 定位）。
- 输入：`/input`（或 `--input`、`$REVIEW_INPUT`）；产物：`/app/output`（或 `--output`、`$REVIEW_OUTPUT`），不可写时依次退到包内 `output/`、工作目录。
- **先写 partial `result.json`，最后无条件 finalize 覆盖**；任何异常写入 `errors`/`degradations`/`pending_human`；**退出码恒为 0**。
- 运行方式（在 Skill 根目录）：

```bash
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --input /input --output /app/output --findings /app/work/findings.json   # 可选第二遍
python3 scripts/verify.py --input /input --output /app/output                                   # 自检，可随时跑
```

## 4. 输入发现（按语义，不假设键名）

1. 读 `case.json`（缺失时递归找 `case*.json`，仍失败则继续并记 `errors`）。
2. 透传 `case_id` 与 `output_contract`；`task_instruction`/`formal_inputs`/`artifacts`/`material.json` 等键名不固定，按语义读取。
3. 递归扫描输入目录全部文件，按扩展名 + 实际内容抽取：PDF（`pdftotext -layout/-raw`，缺失则内置 `zlib` 解析）、DOCX/XLSX（zip+XML）、CSV/TSV/JSON/MD/TeX（纯文本）、图片（`tesseract` 存在则 OCR）。
4. `case.json` 中名为 `path/file/uri/artifact` 但输入内不存在的对象 → 写入 `uncertainty`（材料缺口），不构造内容。

## 5. 输出契约

`result.json` 顶层固定字段：`skill`、`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`task_summary`、`issues`、`review_summary`、`citation_support_matrix`、`evidence_index`、`pending_human`、`uncertainty`、`sources`、`errors`、`degradations`、`changes`、`rejected_findings`、`output_contract`、`contract_unmapped_fields`、`verification`、`runtime`、`artifacts`。

- `output_contract`：**键名原样保留**，按语义映射填入（issues / summary / citation / evidence / sources / status / pending / 报告路径…）；未识别字段保留为 `null` 并记入 `contract_unmapped_fields`。
- 同目录另出：`review_report.md`（主产物，含问题清单、引用矩阵、待复核、复现命令）、`issues.csv`（逐条问题，UTF-8-SIG）、`evidence_index.json`（issue_id → 定位串+原文）、`citation_pairs.json`（句子→引用配对）、`run.log`。

## 6. 核心流程（两遍，第一遍即可交付）

**第一遍（确定性，脚本自动）**：抽取文本 → 识别章节/段落/页码 → 运行 `references/checks.json` 的规则（引用编号与条目一致性、数值与百分比自洽、统计报告、方法设计、论证链、学术规范）→ 生成 `issues`、`citation_support_matrix`。

**第二遍（语义，Agent 可选增强）**：读 `citation_pairs.json` + 原文，逐条判定引用支持程度并写出 `findings.json`，再 `--findings` 合并。合并时**逐字校验 quote**：找不到即拒绝并进 `pending_human`，绝不改写原文凑匹配。

```json
{"findings":[{"kind":"citation_support","severity":"major","certainty":"likely",
  "quote":"句中逐字原文","claim":"该句把综述结论表述为因果结论","suggested_fix":"改引原始研究或降级表述",
  "rule_id":"semantic.support","status":"issue"}],
 "citation_verdicts":[{"pair_id":"CP-003","verdict":"partial","reason":"原文仅支持相关性，未支持剂量效应"}]}
```
详见 `references/io_contract.md#findings-json-second-pass`。

## 7. 六类检查与判定规则

| 类别 | 关键检查（规则见 `references/checks.json`） |
|---|---|
| 引用支持 citation_support | 编号/条目悬空、作者-年份不符、撤稿与预印本状态、综述支撑因果、无来源断言 |
| 事实与数值 fact_check | 百分比与分数不符（如 `12% (n=5/60)` = 8.3%）、摘要与正文 N 不一致 |
| 统计报告 stats_report | `p=0.000`、显著无检验量、无效应量/CI、无样本量或功效、±未定义 SD/SEM、趋势性措辞、边界 p |
| 方法设计 method_design | 随机化未描述、比较性结论无对照、体外结论外推临床、缺纳入排除标准 |
| 论证链 argument_chain | 相关性当因果、综述当原始证据、首次性断言、结论绝对化 |
| 学术规范 academic_norm | 缺章节、缺伦理/利益冲突/数据可用性/资助/作者贡献、报告指南、重复 DOI、补充材料缺失 |

判定规则与严重度分级见 `references/playbook.md`。**判定必须与引文语义一致**；"引用存在"不等于"引用支持结论"。

## 8. 证据与定位规范

每条 issue 必带三项：

- `locator`：`<文件名>#<页>/para<段号>@char<字符偏移>`，例 `paper.pdf#p3/para2@char10412`（无分页文本省略 `#页`）。
- `quote`：**逐字原文**（脚本按规范化空白/大小写匹配校验；不通过即进 `pending_human`）。
- `section`：`abstract|introduction|methods|results|discussion|conclusion|references|funding|coi|data|ethics|author_contrib` 之一或 `-`。

外部事实（被引文献内容、出版状态、数据库权限）不得写成结论：只能记 `pending_human` 并写明需要什么证据。

## 9. 严重度与状态

- `major`（阻断）：结论不成立、引用不支持结论、数值自相矛盾、方法缺对照、伦理声明缺失。
- `minor`（建议）：报告不完整（无 CI/效应量）、表述过度、条目格式与年份不符。
- `info`：自引比例、参考文献数量等提示。
- `certainty`：`confirmed`（算术/字符串可判定）、`likely`（规则+上下文）、`needs_human`（需外部核验）。
- `status`：`issue` 或 `pending_human`（后者同时进 `pending_human[]`）。

## 10. 冲突与人工确认

- 规则命中但语义可能合理（如"综述"被用于背景陈述）→ 降 `minor`/`info` 或记 `pending_human`，不硬判。
- 同一句命中多条规则 → 保留最具体的一条，其余作为上下文写入 `claim`。
- 原文取不到（扫描件无 OCR）、引文严重歧义、来源撤稿/版本不一致、数据库权限不足 → 一律 `pending_human` + `uncertainty`，写明处置建议。

## 11. 预算与断点

单脚本秒级完成；模型预算紧张时只跑第一遍（脚本已覆盖六类），第二遍挑 `citation_pairs.json` 中 major 风险最高的 5–10 组。接近时限时立即停手——partial `result.json` 已在第一步落盘，可直接交付。

## 12. 异常降级分支

| 情况 | 处理 | 记录位置 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续跑，用空 case | `errors[]` |
| PDF 无文本层/扫描件 | `pdftotext`→内置解析→OCR；仍失败则该文件不计入，其余继续 | `degradations[]` + `uncertainty[]` |
| 图片无 OCR | 跳过并声明 | `degradations[]` |
| 未识别材料格式 | 跳过该文件 | `degradations[]` |
| 契约字段无法映射 | 保留键名 `null` | `contract_unmapped_fields[]` |
| 第二遍 quote 不匹配 | 拒绝合并 | `rejected_findings[]` + `pending_human[]` |
| 规则文件缺失 | 仅跑代码级检查 | `degradations[]` |
| 任一材料异常 | 只降级该材料，不影响整体 | — |

## 13. 自检清单

1. `python3 scripts/main.py --help` 退出 0；2. `--output` 下 `result.json`、`review_report.md`、`issues.csv` 均存在；3. `output_contract` 键与输入逐一对应；4. `python3 scripts/verify.py` 显示 `failed=0`（quote 全部可解析、计数一致）；5. 空输入/坏 JSON 也返回合法 partial 且退出 0；6. `status` 与 `errors/degradations/pending_human` 一致，无"ok 却有错误"。

## 14. 最小调用示例（示例，非正式案例结果）

```bash
# 输入：/tmp/demo/ 下 case.json + paper.md（1 篇短文）
python3 scripts/main.py --input /tmp/demo --output /tmp/demo_out
```

示意输出（**示例数据，非任何官方案例结果**）：

```json
{"case_id":"demo-001","status":"partial",
 "issues":[{"issue_id":"R-001","kind":"fact_check","severity":"major","certainty":"confirmed",
   "locator":"paper.md#para3@char412","quote":"12% (n=5/60) of samples responded",
   "claim":"百分比与分数不一致：12% 与 5/60（应为 8.3%）","suggested_fix":"按 5/60 重算并同步正文、表与图注"}],
 "review_summary":{"issues_total":1,"by_severity":{"major":1,"minor":0,"info":0}},
 "citation_support_matrix":[{"pair_id":"CP-001","claim_locator":"paper.md#para5@char880","verdict":null}]}
```

## 15. 文件清单、依赖与维护

| 文件 | 作用 | 大小 |
|---|---|---|
| `SKILL.md` | 本说明 | ~8 KB |
| `scripts/main.py` | 抽取、编排、报告（入口） | ≤20 KB |
| `scripts/verify.py` | 规则引擎、引用/数值核验、契约回填、结果自检 | ≤20 KB |
| `references/checks.json` | 39 条规则的文案/严重度 + 24 条正则规则 + 章节与契约映射 + 报告模板 | ~35 KB |
| `references/playbook.md` | 判定规则、支持程度定义、证据标准、误报控制 | ~9 KB |
| `references/io_contract.md` | 输入/输出 schema、第二遍 findings 格式、排查 | ~7 KB |

依赖：Python ≥3.8 标准库。可选（缺失即降级，不报错）：`pdftotext`（PDF 版面文本，强烈建议）、`tesseract`（图片 OCR）。无第三方 Python 包、无网络、无凭证。
维护：新增检查只需在 `checks.json` 增一条 pattern（regex + `section`/`not_near`/`require_near`/`absent_doc` 守卫 + `catalog` 文案），无需改代码；改动后跑 `verify.py` 与最小示例回归。
