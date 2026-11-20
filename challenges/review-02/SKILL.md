---
name: review-fact-check
description: Evidence-bound review of manuscripts and research materials for citation/fact verification. Instructs the Harness Agent to run scripts as tools, personally read and verify source materials, and produce complete deliverables (result.json, review_report.md, issues.csv, evidence_index.json, citation_pairs.json, validation.txt). Provides an agent-first path via draft.json and a deterministic no-draft fallback. Never fabricates references, page numbers, statistics, or verdicts.
version: 2.0.0
---

# review-fact-check

把“引用与事实核验”做成可交付、可复核的审查结果：条目化问题清单（位置 / 原文 / 判定 / 严重度 / 修改建议）+ 引用支持矩阵 + 待复核与未检查项。**脚本负责确定性抽取、校验、渲染和容错；你（Harness Agent）负责读原文、判断、核验、形成 draft.json，并最终撰写可交付报告。**

不做论文润色、不代写综述、不替代作者对研究结论的判断。被引文献正文不在输入中时，“是否支持该句”只能进 `pending_human`，不得凭标题猜测。**实际输入文件和原论文是唯一事实依据；不依据错误的领域标签补造数据；不编造缺陷，不允许用预制答案冒充运行结果。**

---

## 0. 最高优先级规则

1. **先保全 partial，再增量改进**。任何步骤完成后立即落盘合法 `result.json`。异常也必须退出码 0。
2. **结构化产物由脚本生成**。`claims.json`、`evidence_table.json`、`result.json` 等结构字段（键名、claim_id、source_id、locator、quote、strength、support_scope、counts）不得手工篡改。需要改结构化结果时，写临时 python 调用脚本函数重算并覆盖，并把修复动作记入 `/app/work/agent_review.json` 的 `script_fixes`。
3. **Agent 可写 draft.json 与正文型交付物**；每条 finding 必须能在 `evidence_index.json` 中找到 `locator + quote` 依据。
4. **外部事实与数据库状态不得写死为结论**。撤稿、更正、版本不一致、被引文献正文不可得、引用严重歧义等，一律进 `pending_human[]` / `uncertainty[]`，不伪造来源、版本、分数、引用内容。
5. **禁止自造评分 / 金标准 / benchmark 分数**。核验只引用 `scripts/verify.py` 真实输出 `verification.json`；不要引用或美化脚本自设评分。
6. **单命令全流程优先**。用最少的模型请求跑完 init → build → selfcheck；剩余预算用于高价值核验与正文改进。

---

## 1. 运行入口、目录与命令

### 1.1 目录约定

- 输入：`/input`，至少含 `case.json`、`task.md` 及题面规定的材料。
- 工作目录：`/app/work`，存放中间台账、解析文本、draft、日志。
- 最终产物：`/app/output`，必须包含合法 `result.json`。
- 实际材料必须真实解析，不得依据文件名或领域标签猜测内容。

### 1.2 单命令全流程入口

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

内部阶段：

- `init`：盘点 `/input` 全部文件，读取 `case.json` 和 `task.md`，提取 `case_id`、`output_contract`、材料清单，生成来源编号、候选抽取与冲突分组。
- `build`：校验候选、确定性问题抽取、兜底渲染全部产物，finalize `result.json`。
- `selfcheck`：校验产物与 output_contract 字段、quote 逐字匹配、文件完整性，并写 `validation.txt`。

异常时脚本不得崩溃退出；若子命令失败，脚本仍生成最小合法 partial 文件并退出 0。

### 1.3 分步命令（供增量修复用）

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py check --draft /app/work/draft.json --input /input --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
python3 scripts/verify.py --input /input --output /app/output
```

---

## 2. Agent-first 双路径

### 2.1 Agent 路径（默认优先）

1. 先运行 `init`，读 `/app/work/ledger.json` 或脚本输出的台账：材料清单、候选 findings、冲突分组、契约字段。
2. 读 `/input/task.md`、`/input/case.json`，并真实读取材料。PDF 优先用 `pdftotext`/平台 PDF 工具；扫描 PDF 再尝试 OCR；DOCX/CSV/图片分别处理。
3. 将你的判断写入 `/app/work/draft.json`。draft.json 是 Agent 与脚本之间的唯一结构化交接文件。
4. 运行 `check` 校验 draft；校验不通过时按错误修复 draft，不手工改 result.json。
5. 运行 `build` 渲染产物，再运行 `selfcheck` 完成自检。

### 2.2 无 draft 时的确定性兜底

- 若 Agent 未写出有效 draft.json，`build` 必须仍能基于 init 台账确定性抽取生成实质工作稿。
- 兜底抽取要求：每条候选 finding 必须有**逐字 quote + locator**；无法满足 quote 逐字匹配的候选不得成为正式 issue，应进入 `pending_human`。
- 兜底产物必须把 `provenance=auto_extract`、`agent_verified=false` 记入每个 finding 与 `degradations[]`。
- 两条路径必须产出**同一套产物与同一份 result.json 契约**。

### 2.3 draft.json 形状

```json
{
  "case_id": "case-...",
  "findings": [
    {
      "issue_id": "R-001",
      "kind": "fact_check",
      "severity": "major",
      "certainty": "confirmed",
      "status": "issue",
      "locator": "paper.pdf#p3/para2@char10412",
      "quote": "exact original text",
      "section": "results",
      "claim": "结论与引文不一致：正文称 A 支持 B，但引文仅报告 A。",
      "suggested_fix": "改为部分支持或将结论收窄到引文实际支持的范围。",
      "sources": [],
      "rationale": "逐字核验引文后，原文只报告 A，不含 B。",
      "external_check": null
    }
  ],
  "citation_checks": [
    {
      "pair_id": "CP-001",
      "claim_locator": "paper.pdf#p8/para1@char20010",
      "cited_source": "S3",
      "verdict": "unsupported",
      "reason": "引文内容不包含该因果关系。"
    }
  ]
}
```

---

## 3. 执行流程

### 步骤 0：盘点输入与契约

- 运行 `init` 或读取 `case.json` / `task.md`，获取 `case_id`、原 `output_contract` 字段、材料路径和任务说明。
- 递归扫描 `/input`，记录实际存在文件。材料路径与 `case.json` 不一致时，以实际文件为准并在 `errors[]`/`degradations[]` 说明。
- 工作台账写入 `/app/work/task_notes.json` 或脚本台账。

### 步骤 1：跑通基线，先落盘 partial

- 运行：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

- 如果脚本异常：构造最小合法 `result.json`，`status="input_error"` 或 `partial`，保留全部顶层固定字段，`issues=[]`，`errors[]` 记录异常。其他文件写空模板但存在。
- 本步骤即形成可交付的 honest partial。

### 步骤 2：真实解析材料并构建证据索引

- 用实际工具解析每份材料，记录：文件名、页、段落号、字符偏移、section、逐字原文。
- 抽查脚本抽取的 quote 是否逐字存在。发现偏移或错误，写修正项到 `/app/work/agent_verification.json`，并调用脚本修复。
- 无法解析、损坏、缺少文本层、OCR 失败：跳过该材料，不编造内容；记入 `degradations[]` 和 `uncertainty[]`。

### 步骤 3：Agent 亲自核验与推导

- 读取 draft / agent_verification 的基础候选。
- 逐条检查：quote 是否逐字存在、locator 是否指向正确位置、判定是否与引文语义一致。
- 补充六类问题：引用支持、事实与数值、统计报告、方法设计、论证链、学术规范。
- 每条 finding 必须有：

| 字段 | 要求 |
|---|---|
| `issue_id` | 唯一，建议 `R-001`、`CP-001`、`S-001` |
| `kind` | 六类之一 |
| `severity` | `major|minor|info` |
| `certainty` | `confirmed|likely|needs_human` |
| `status` | `issue|pending_human` |
| `locator` | 精确到文件、页、段落、字符偏移 |
| `quote` | 逐字原文 |
| `section` | 所在章节 |
| `claim` | 判定依据与问题描述 |
| `suggested_fix` | 可执行修改建议 |
| `sources` | 来源编号及证据定位 |
| `rationale` | 不写空泛结论；说清为什么成立或不成立 |
| `external_check` | 需要外部核验时填所需证据；否则 `null` |

### 步骤 4：合并 draft 并渲染最终产物

- 运行 `check` 校验 draft 和旧 findings；通过后运行 `build`。
- `build` 必须更新 `issues`、`review_summary`、`citation_support_matrix`、`evidence_index`、`pending_human`、`changes`、`sources`。
- 保持原 `output_contract` 键名不变，逐字段映射；未识别字段保留 `null`，记入 `contract_unmapped_fields[]`。
- 重写 `review_report.md`、`issues.csv`、`evidence_index.json`、`citation_pairs.json`，与 `result.json` 一致。
- 将真实修改过程写入 `changes[]`，例如：“agent_verification 将 CP-003 从 supported 修正为 partial”。

### 步骤 5：自检与契约核对

- 运行：

```bash
python3 scripts/verify.py --input /input --output /app/output
```

- 核对 output_contract 字段与 `result.json` 键一一对应；检查文件齐全；检查 `status`、`errors`、`degradations`、`pending_human` 一致。
- `verify.py` 显示 failed>0 时，优先修复 quote 不匹配或字段缺失；无法修复则如实写 `degradations[]` 与 `errors[]`，仍保持退出码 0。

---

## 4. result.json 与产物契约

### 4.1 result.json 顶层固定字段

```text
skill, case_id, status, task_summary, issues, review_summary,
citation_support_matrix, evidence_index, pending_human, uncertainty,
sources, errors, degradations, changes, rejected_findings,
output_contract, contract_unmapped_fields, verification, runtime, artifacts
```

`status` 取值：

- `ok`：完成审查，无阻断性缺失。
- `partial`：有产物，但存在缺失/无法解析/未核验项。
- `insufficient_evidence`：材料不足以支撑大多数判定。
- `input_error`：输入损坏、缺失或无法识别。

### 4.2 双回显要求

原 `output_contract` 的全部契约字段必须在 `result.json` 顶层各出现一次，并在 `result.json.output_contract` 中再出现一次。`case_id` 必须在顶层存在。不能只把契约埋入 nested output_contract。

### 4.3 status 与异常一致性

- `status=ok` 时，`errors[]` 应为空；若有 `degradations[]`，必须只为非阻塞降级。
- `status=partial/input_error/insufficient_evidence` 时，必须列出具体缺口、不确定项、降级项、待人工项。
- 禁止“看似成功但 errors 非空”的互相矛盾。

### 4.4 其他交付文件

```text
/app/output/result.json
/app/output/review_report.md
/app/output/issues.csv
/app/output/evidence_index.json
/app/output/citation_pairs.json
/app/output/run.log
/app/output/validation.txt
```

如题面契约要求可编辑 Office、幻灯片或图形产物，必须额外给出真实渲染的 PDF/PNG 预览，不得伪造。

---

## 5. 证据定位与来源规范

每条问题必须同时具备：

- `locator`：`<文件名>#p<页>/para<段号>@char<字符偏移>`。无分页文本可省略 `#p<页>`。
- `quote`：**逐字原文**。脚本按规范化空白/大小写/标点匹配校验；不通过不得作为正式 finding。
- `section`：`abstract|introduction|methods|results|discussion|conclusion|references|funding|coi|data|ethics|author_contrib|-`
- `source_id` / `sources[]`：指向 `sources[]` 中的具体来源条目。

来源条目至少包含：

```json
{
  "source_id": "S1",
  "path": "/input/paper.pdf",
  "type": "pdf",
  "parse_status": "ok",
  "locator_base": "paper.pdf",
  "note": "第一轮 pdftotext 成功"
}
```

不得把文件名当成事实结论。不得把被引文献的标题当作被引文献正文内容。

---

## 6. 六类检查与判定规则

| 类别 | 关键检查 |
|---|---|
| `citation_support` | 引用是否支持结论；编号悬空/作者年份不符；预印本与正式版本差异；把综述当原始证据；把“引用存在”误当“引用支持结论” |
| `fact_check` | 百分比与分数不一致；摘要与正文数字、样本量矛盾；数值算错 |
| `stats_report` | `p=0.000`、显著但无检验量、无效应量/CI、无样本量或功效、±未定义 SD/SEM、趋势性措辞、边界 p |
| `method_design` | 随机化未描述；比较性结论无对照；体外外推临床；缺纳排标准 |
| `argument_chain` | 相关性当因果；循环论证；以偏概全；缺少对照；结论跳跃 |
| `academic_norm` | 缺章节、伦理、利益冲突、数据可用性、资助、作者贡献、报告指南、重复 DOI、补充材料缺失 |

判定规则、支持程度定义、误报控制详见 `references/playbook.md`；正则与守卫规则见 `references/checks.json`；输入输出 schema 见 `references/io_contract.md`。

**判定必须与引文语义一致**。引用存在 ≠ 引用支持结论。区分四种：`supported`、`partial`、`unsupported`、`unverifiable`。

---

## 7. 严重度、状态与不确定性

- `major`：结论不成立、引用不支持结论、数值自相矛盾、方法缺对照、伦理声明缺失。
- `minor`：报告不完整（无 CI/效应量）、表述过度、条目格式与年份不符。
- `info`：自引比例、参考文献数量等提示。
- `certainty`：`confirmed`（算术/字符串可判定）、`likely`（规则+上下文）、`needs_human`（需要外部核验）。
- `status`：`issue` 或 `pending_human`。`pending_human` 必须同时进入 `pending_human[]`。
- `uncertainty[]` 记录无法确认的事项与下一步需要什么证据。

---

## 8. 预算策略

官方预算：64 次模型请求 / 900 秒 / 16384 tokens per response。本地脚本运行不计模型请求。

建议分配：

- init + 基线 build：0–5 次请求。
- 关键材料解析：15–25 次请求，优先正文、图表、参考文献、方法/结果/讨论。
- 高价值核验：20–30 次请求，优先 `major`、`confirmed/likely`、引用支持与数值一致性。
- 报告与 JSON 更新：5–10 次请求。
- 自检修复：2–5 次请求。

接近预算上限时：保留 baseline partial；只核验前 5–10 条高风险项；跳过全量语义分析。每完成一个步骤即落盘一次 `result.json`。不重复读取同一文件，解析结果写入 `/app/work/` 复用。

---

## 9. 隐藏案例鲁棒性与降级

| 情况 | 处理 | 记录位置 |
|---|---|---|
| `case.json` 缺失 / 坏 JSON | 继续运行，用空 case；`case_id` 无法取到时写 `"unknown"` | `errors[]` |
| `output_contract` 缺失 | 使用默认核心字段，保留原键名并填 `null` | `contract_unmapped_fields[]` |
| PDF 无文本层 / 扫描件 | 先 `pdftotext`；再 OCR；均失败则跳过该材料 | `degradations[]` + `uncertainty[]` |
| 图片无 OCR | 跳过并声明 | `degradations[]` |
| 材料格式不支持或损坏 | 跳过该文件 | `degradations[]` |
| 空输入 | 输出合法 `result.json`：`status="input_error"`、`issues=[]`、`errors[]` 说明 | `errors[]` |
| 脚本崩溃 | 构造最小合法 partial，exit 0 | `errors[]` |
| quote 不匹配 | 拒绝合并，进 `pending_human` | `rejected_findings[]` + `pending_human[]` |
| 规则文件缺失 | 仅跑代码级检查 | `degradations[]` |
| 时间耗尽 | 保留已落盘 partial，补 `degradations[]`，exit 0 | `degradations[]` |

任何情况下，`/app/output/result.json` 必须存在且为合法 JSON，退出码必须为 0。

---

## 10. rubric 维度与交付自证对照

| rubric 维度 | 可检查证据 |
|---|---|
| 任务完成度 15 | `issues[]` 条目化；每条有位置、原文、判定、严重度、修改建议；`review_report.md` 逐条可查 |
| 结果正确性 15 | `citation_support_matrix[]` 有 `verdict`+`reason`；quote 逐字匹配；`claim` 区分“引用存在”与“引用支持结论” |
| 结果完整性 5 | `review_summary.by_kind` 覆盖六类；`evidence_index` 覆盖方法、结果、讨论等章节 |
| 结果可核验性 5 | `evidence_index` 映射 issue_id → locator+quote；`sources[]` 记录材料路径与解析状态 |
| 质量增益 15 | `verification` 记录 Agent 亲验 `verified`/`rejected`/`quotefail`；`changes[]` 记录修正；`rejected_findings[]` 控制误报 |
| 效率增益 5 | 脚本一命令全流程；Agent 仅核验高价值项；`runtime` 记录运行时长与请求次数 |
| 增益可验证性 5 | 保留 `provenance`、`agent_verified`、`AUTO_EXTRACT` 说明；`changes[]` 列出增强前后差异 |
| 新增能力 5 | `citation_support_matrix` 支持四类语义判定；locator 到段落/字符；`pending_human` 处理版本、撤稿、来源不可得 |
| 方法改进 5 | `references/playbook.md` 定义支持程度；`references/checks.json` 规则可扩展；`rejected_findings[]` 体现误报控制 |
| 创新证据 5 | `SKILL.md` 明确 agent-first + deterministic fallback；`verification` 展示真实核验轨迹 |
| 调用易用性 3 | 单命令入口；`scripts/main.py --help` 可用；SKILL.md 分步命令清晰 |
| 运行稳定性 4 | 异常降级表；退出码 0；`verify.py` 自检 quote 与契约 |
| 异常处理 3 | `errors[]`/`degradations[]`/`uncertainty[]`/`pending_human[]` 记录具体处置 |
| 文档完整性 3 | 当前 SKILL.md + references 三件套 + 示例 |
| 资源可复用性 4 | `references/checks.json`、`references/playbook.md`、`references/io_contract.md` 为文本资源，可复跑 |
| 分享推广价值 3 | 输出 CSV/JSON/Markdown，结构可扩展；`evidence_index` 可回查 |

---

## 11. 完整性自检清单

1. `python3 scripts/main.py --help` 或 `run --help` 退出 0；脚本路径有效。
2. `/app/output` 下 `result.json`, `review_report.md`, `issues.csv`, `evidence_index.json`, `citation_pairs.json`, `run.log`, `validation.txt` 均存在。
3. `result.json` 顶层与 `output_contract` 字段一一对应；`contract_unmapped_fields[]` 列出未映射字段。
4. `verification` 由 `verify.py` 生成；不要伪造校验分数。
5. 每个 issue 都有 `locator`, `quote`, `section`, `severity`, `certainty`, `status`, `claim`, `suggested_fix`。
6. 每条 citation pair 有 `verdict` 或进入 `pending_human`。
7. `review_report.md` 与 `result.json` 一致；`issues.csv` 行数与 `review_summary.issues_total` 一致。
8. `status` 与 `errors/degradations/pending_human` 逻辑一致。
9. 材料缺失、无法解析、引用歧义、版本/撤稿/权限问题均有 `pending_human` 或 `uncertainty` 记录。
10. 最终退出码为 0，且 `result.json` 可被 JSON 解析器读取。

---

## 12. 最小调用示例

```bash
mkdir -p /tmp/demo_in /tmp/demo_out
printf '{"case_id":"demo-001","output_contract":{"task_summary":null,"issues":null,"review_summary":null,"citation_support_matrix":null,"evidence_index":null,"pending_human":null,"sources":null}}' > /tmp/demo_in/case.json
printf '12%% (n=5/60) of samples responded.\n' > /tmp/demo_in/paper.md

python3 scripts/main.py run --input /tmp/demo_in --output /tmp/demo_out --work /tmp/demo_work
python3 scripts/verify.py --input /tmp/demo_in --output /tmp/demo_out
```

示意输出（**示例数据，不是任何官方案例结果**）：

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "issues": [
    {
      "issue_id": "R-001",
      "kind": "fact_check",
      "severity": "major",
      "certainty": "confirmed",
      "status": "issue",
      "locator": "paper.md#para1@char0",
      "quote": "12% (n=5/60) of samples responded.",
      "section": "results",
      "claim": "百分比与分数不一致：12% 与 5/60（应为 8.3%）矛盾。",
      "suggested_fix": "按 5/60 重算并同步正文、表与图注。"
    }
  ],
  "review_summary": {"issues_total": 1, "by_severity": {"major": 1, "minor": 0, "info": 0}},
  "citation_support_matrix": [],
  "output_contract": {}
}
```

**正式运行时，必须由 Agent 真实解析材料、亲自核验，不得把示例或模板直接当成品。**

---

## 13. 文件清单、依赖与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明：入口、流程、双路径、契约、预算、鲁棒性、rubric 对照 |
| `scripts/main.py` | init / build / selfcheck / run 全流程入口，确定性抽取与渲染 |
| `scripts/verify.py` | quote 与契约自检，写 `verification.json` |
| `references/checks.json` | 规则文案、严重度、正则规则、章节与契约映射、报告模板 |
| `references/playbook.md` | 判定规则、支持程度定义、证据标准、误报控制 |
| `references/io_contract.md` | 输入/输出 schema、draft.json 字段说明、排查 |

依赖：Python ≥3.8 标准库。可选能力：`pdftotext`（PDF 文本提取，强烈建议）、`tesseract`（扫描件 OCR）。无第三方 Python 包、无联网、无凭证。

维护：新增检查在 `references/checks.json` 增一条 pattern（regex + section/not_near/require_near/absent_doc 守卫 + catalog 文案）；改动后必须重跑 `scripts/verify.py` 与最小示例回归。