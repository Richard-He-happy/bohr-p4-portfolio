---
name: systematic-literature-review
description: >-
  对给定文献材料执行可复核的系统性文献综述（SLR）：把研究问题拆成检索要素并生成可执行
  布尔检索式，冻结条款化纳排标准，做两轮筛选并逐条留痕（含两遍阈值一致性与人工队列），
  用 SLR-6D 量表逐维度评价质量，最后输出每条论断都带逐字引文与定位的综述、证据矩阵、
  冲突证据与研究空白。Run an auditable systematic literature review over supplied
  records: executable Boolean search protocol, versioned eligibility clauses,
  two-round screening log with per-record reasons, SLR-6D appraisal, and claims
  backed by verbatim quotes plus character-span locators. Writes result.json,
  review.md and evidence_map.csv; never fabricates records, numbers or DOIs.
version: 1.0.0
---

# 系统性文献综述（SLR）Skill

## 1. 用途与边界

把「研究问题 + 给定文献材料」走完一条别人可复跑的综述链路：问题拆解 → 检索协议 →
条款化纳排 → 两轮筛选留痕 → 质量评价 → 带引文定位的分主题综合 → 冲突证据与研究空白。

**做**：题录解析（PDF/DOCX/JSON/CSV/MD/TXT）、检索式构造、纳排判定、筛选记录、质量评价、
证据综合、可复核输出。
**不做**：单篇精读与翻译、论文润色、代替学术审查做事实/方法核验；**不联网检索数据库**，
不做全文获取，不生成材料以外的文献、DOI、数值或结论。

## 2. 运行契约

- 环境：Python 3.9+，仅标准库，无联网；不依赖当前目录（脚本用 `Path(__file__).resolve()` 定位资源）。
- 输入：`/input/case.json` + `task.md` + 材料（`artifacts/`、`material.json`、任意 PDF/CSV/XLSX/DOCX/JSON）。
- 工作目录 `/app/work`，产物 `/app/output`。可用 `--input/--output/--work` 覆盖，或 `SLR_INPUT/SLR_OUTPUT/SLR_WORK`。
- 两阶段：`slr_review.py`（协议与记录）→ 自动调用 `verify.py`（筛选、评价、综合、装配、渲染、核验）。
- `result.json` 在分析前先写 partial，结束时**无条件**覆盖为终版；异常被捕获并记录，**退出码恒 0**。

## 3. 输入发现（按语义，不假设键名）

1. 读 `/input/case.json`；若无，递归找含 `output_contract/outputContract/case_id/task_instruction` 的 JSON。
2. 原样取出 `output_contract`（或其别名）与 `case_id`；题目文本按 `research_question/question/task_instruction/objective/topic` 取，缺失则从 `task.md` 的「研究问题 / Research question」段落取。
3. 递归扫描输入目录下的可解析文件，按扩展名 + 内容识别；每个文件记录 `sha256[0:12]`、字符数、抽取器名、解析出的记录数。
4. 记录字段按同义词表识别：`title/标题/题名`、`abstract/摘要`、`authors/作者`、`year/年份`、`journal/期刊/venue`、`doi`、`url`、`fulltext/content/text`（有则计入全文）。
5. 材料未给出的对象**明确列缺口**（`pending_human` 或 `degradations`），不补造。

## 4. 输出契约

`result.json` 必含：`skill, case_id, status, output_contract, contract_check, research_question,
search, criteria, screening, appraisal, synthesis, sources, coverage, summary, uncertainty,
pending_human, errors, degradations, changes, runtime, artifacts, verification`。

`status`：`ok` | `partial` | `insufficient_evidence` | `input_error`（含义见 `references/output-schema.md`）。
契约回填：键名不改、未知字段保留；占位型字符串 → `null`；`contract_check.fields_null` 记录仍为空的数量。

另输出：`review.md`（主产物）、`evidence_map.csv`、`screening_log.csv`、`appraisal.csv`，
列定义见 `references/output-schema.md` §1。

## 5. 核心流程

1. **问题拆解**：取 population/intervention/comparison/outcome/design/time/language；未给结构化要素时按措辞启发式拆分，标 `derivation.confidence=low` + `pending_human.confirm_structured_question`。
2. **检索协议**：每要素一块（同义/词形扩展、字段、布尔、意图、受控词说明），生成 `pubmed_style` 与 `generic_boolean` 原文字符串；在给定语料上执行，报告逐块与全块命中，**不冒充数据库命中**。
3. **纳排冻结**：IC1–IC3 / EC1–EC7（含软排除 EC7），带优先级、机器规则、可判定性；冻结时间记入 `criteria.frozen_at`。
4. **两轮筛选**：题录级（A_strict / B_lenient 两遍阈值 + Cohen's kappa + 分歧队列）→ 全文级（有全文则读；无全文则 EC7 软排除、降级为摘要级证据）。每行含 `clause_id/verdict/reason_code/reason_text/evidence_quote/screener/ts/criteria_version`。
5. **质量评价**：SLR-6D 六维度逐维判定 + 逐字引文；分数、等级与「等级如何限制论断」写入 `appraisal.items[].effect_on_claims`。
6. **综合**：按核心概念分主题，每条论断给出 `kind`（directly_supported / inferred / insufficient_evidence）、证据（record_id + locator + 逐字 quote + 质量等级 + 方向）、条件与边界；方向相反者进 `conflicts` 并降级该论断；单研究主题、报告不足、时间断层、缺对照条件进 `gaps`。
7. **核验**：`verify.py` 按 `char_start/char_end` 重新切片比对每条引文，统计契约空值与产物齐备性，写入 `verification`。

## 6. 任务质量规则（rubric → 字段 / 检查 / 产物）

| 评分维度 | 对应字段与检查 | 产物 |
|---|---|---|
| 任务完成度 | `search`/`criteria`/`screening`/`appraisal`/`synthesis` 五段齐备 | `result.json`、`review.md` |
| 结果正确性 | 判定只由冻结条款产生（`reason_code` 回指 `clauses[].id`）；引文逐字；`doi/year` 仅取自材料 | `screening_log.csv`、`sources[]` |
| 结果完整性 | `coverage` 计数（语料/纳入/排除/论断/冲突/空白/引文）+ `uncertainty` | `result.json` |
| 可核验性 | `locator=file#chars=a-b` 且 `verification.quotes_verified`；`criteria.version/frozen_at`；`materials[].sha256` | `evidence_map.csv` |
| 质量/效率增益 | 逐条理由齐全、可重跑（同输入 → 同判定），无需人工补理由 | 全部产物 |
| 创新 | 结构化检索块、条款版本冻结、双阈值一致性与分歧标记、证据自动回链、冲突矩阵 | `search`/`criteria`/`screening.dual_pass`/`evidence_map.csv`/`synthesis.conflicts` |
| 可靠体验 | 异常分支降级不中断、退出码 0、`--help`、空输入可跑 | `errors`/`degradations` |
| 生态贡献 | 本文件 + `references/` 三份可复用资源 | 包内资源 |

## 7. 证据与定位规范

- 引文必须是抽取文本的**逐字切片**：`text[a:b] == quote`，定位写作 `<file>#chars=a-b`。
- 抽取文本落在 `work/extracted/<record_id>.txt`，可脱离原 PDF/DOCX 复核。
- 不做字符级改写、不用「意思相近」的引文；找不到可引句时该条不生成论断（记 `pending_human`）。
- 页码：stdlib PDF 兜底不产出可靠页码，故**不写页码**，以字符区间替代并在 `degradations` 说明。
- 方向判定（POS/NEG/NUL）表示「相对所述结局的报告方向」，不是价值判断。

## 8. 冲突与人工确认

进入 `pending_human`：问题要素靠启发式拆分、两遍筛选分歧、题录级判定存疑、无足够质量证据、
无法生成论断、无任何记录可解析。进入 `conflicts`：同一主题纳入证据报告方向相反（按质量加权后
仍相反）。前者等人工裁决，后者把论断降为 `insufficient_evidence` 并写清所需证据类型。

## 9. 预算与断点

单案例预算 900 秒 / 64 次模型请求（平台侧记录）。脚本为确定性流程，通常数秒完成：
`slr_review.py` 先写 partial `result.json`，再写 `state.json`；`verify.py` 结束时覆盖终版。
任何时刻中断都有合法 `result.json`，`stage` 指示停在哪一步。

## 10. 异常降级分支

| 情形 | 处置 | 落点 |
|---|---|---|
| 检索/语料为空 | 不编造记录，`insufficient_evidence` | `status`、`pending_human` |
| case.json 缺失/损坏 | 记 `errors[].stage=discover`，退出码 0，先落 partial | `errors` |
| 单个 PDF/DOCX 打不开 | 只跳过该文件 | `degradations` |
| PDF 文本质量差 | 记录抽取器与限制（`stdlib_flate`） | `materials[].extractor` |
| 全文不可得 | EC7 软排除 + 摘要级证据 + 等级上限 low | `screening_log.csv`、`appraisal` |
| 术语歧义 | 逐块同义词/词形扩展 + 核心词阈值，存疑进队列 | `search.blocks`、`manual_queue` |
| 条款冲突 | 优先级裁决；同级冲突 → uncertain | `criteria.priority_order` |
| 纳入证据互相矛盾 | 冲突条目 + 论断降级 | `synthesis.conflicts` |
| 权限/IO 失败 | 按文件或按阶段捕获，`status=partial` | `errors`、`degradations` |
| 重复题录 | DOI 或规范化题名合并，保留原 id | `degradations` |

## 11. 自检清单

- [ ] `python3 -B scripts/slr_review.py --help` 退出码 0。
- [ ] `result.json` 可解析，`output_contract` 键齐全，`case_id` 原样。
- [ ] `review.md` 存在且含论断引文与 locator；`evidence_map.csv` 行数 = `coverage.quotes_total`。
- [ ] `verification.result` 为 `pass`（引文全部命中、产物齐备）。
- [ ] 空输入或坏 JSON：仍产出合法 `result.json`，退出码 0。
- [ ] 未出现材料外文献/DOI/数值。

## 12. 最小调用示例（示例，非正式案例结果）

```json
{"case_id": "demo-000",
 "research_question": "住院老年人跌倒预防干预对跌倒发生率的影响",
 "output_contract": {"review": "path", "included_studies": "array", "quality": "object", "gaps": "array"},
 "records": [{"title": "Exercise-based fall prevention in older inpatients: a cohort study",
              "abstract": "Aim: to assess the effect. Methods: n = 412 cohort. Results: a 23% reduction (p = 0.01). Limitations: single centre.",
              "year": 2021, "doi": "10.0000/demo.1"}]}
```

```bash
python3 -B scripts/slr_review.py --input ./demo_input --output ./demo_out --work ./demo_work
```

示意输出（**示例**，非正式案例结果）：`status=ok`；`screening.rounds[1]` 给出该题录的
include/exclude 计数；`appraisal.items[0].grade` 按可见披露信号给出；只有 1 条证据时
`claims[0].kind` 不会是 `directly_supported`；`verification.result=pass`。

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（用途、契约、流程、异常、自检） |
| `scripts/slr_review.py` | 阶段 1：输入发现、记录解析、问题拆解、检索协议、条款冻结、`state.json`、partial `result.json`，并调用阶段 2 |
| `scripts/verify.py` | 阶段 2：两轮筛选、SLR-6D 评价、分主题综合、结果装配与契约回填、`review.md` 与三个 CSV、引文/契约核验 |
| `references/slr-protocol.md` | 检索块模板、条款库、reason code、全部输出消息（中/英） |
| `references/appraisal-rubrics.md` | SLR-6D 量表定义、分级规则、判定用正则标记 |
| `references/output-schema.md` | 输出文件与字段、locator 语法、异常分类、标注示例 |

版本 1.0.0；Python 标准库；无第三方依赖；资源均为 UTF-8 文本。

## 14. 维护说明

- 改措辞：编辑 `references/slr-protocol.md` 的 `<!--slr:msg ... -->` 块（`key|中文|English`），不改代码。
- 调量表敏感度：编辑 `references/appraisal-rubrics.md` 的 `<!--slr:markers ... -->` 块；正则非法时该维度自动落为 `unclear`，不中断。
- 改条款文字：`build_crit` 中的 `c_*` 消息；条款 id 与优先级保持不变，避免历史筛选记录失去可回指性。
- 兼容性：新增记录字段同步 `scripts/slr_review.py` 的 `FK` 同义词表；新增输出同步 `references/output-schema.md`。
