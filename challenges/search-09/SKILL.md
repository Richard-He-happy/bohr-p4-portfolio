---
name: literature-quality-appraisal
description: Evidence-anchored literature quality appraisal for a given document set. Reads the actual files under /input (PDF/DOCX/CSV/JSON/metadata exports), builds a traceable candidate list with query log, and returns a dimension -> judgment -> verbatim evidence + locator -> grade appraisal table with documented thresholds and explicit abstention when evidence is missing. Use for literature quality evaluation, critical appraisal, risk-of-bias assessment, reporting-completeness review, or review-ready evidence tables.
version: 1.0.0
license: MIT
---

# 文献研究质量评价（literature-quality-appraisal）

## 1. 用途与边界

对给定文献集合产出一张**可逐条复核**的质量评价表：每条判断绑定「维度 → 条目 → 判定 → 原文逐字证据 + 定位 → 等级」，而不是复述摘要。

产出三类东西：

1. **候选集与检索日志**（search 赛道主产物）：`candidates.csv` + `query_log.json`，每条候选带 `source_db`、`retrieved_at`、`query_id`、`provenance.source_file/json_pointer`。
2. **评价表**（本题主产物）：`appraisal.csv`（行级：维度-条目-判定-逐字证据-页码-章节）+ `result.json.appraisals`（文档级：维度等级 + 汇总风险 + 置信度 + 分级轨迹）。
3. **`result.json`**：原样回填输入 `output_contract` 全部字段，并带 `case_id` / `status` / `sources` / `uncertainty` / `pending_human` / `errors` / `degradations` / `changes` / `runtime`。

**不做**：不替代同行评审、不做事实核验或临床/政策决策、不联网检索、不生成未见于输入材料的文献/DOI/数值/统计量、不把"未检出"说成"原文没有"。本 Skill 的等级阈值是**本 Skill 自己的可复核判据**，不是任何外部量表的官方评分（见 `references/rubric.md` §0）。

## 2. 适用条件与触发

- 案例要求对给定论文做质量评价、批判性评价、偏倚风险、报告完整性、证据表、系统评价数据提取。
- 输入含 1 篇以上文献（PDF 全文 / 仅摘要 / 题录 JSON / 检索响应导出）。
- 反向条件：要求做文献综述写作、单纯题录补全、或要求上网找"最新进展"——超出边界，按 §12 降级并如实说明。

## 3. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json` + `/input/task.md` + `/input/artifacts/**`（PDF/图片/表格/JSON/DOCX） |
| 工作目录 | `/app/work` |
| 输出 | `/app/output/`：`result.json`、`candidates.csv`、`appraisal.csv`、`query_log.json`、`appraisal_report.md` |
| 只读/只写 | 只读 `/input`；只写 `/app/output`（与 `/app/work`） |
| 退出码 | **恒 0**（含空输入、坏 JSON、全失败） |
| 断点 | 启动即写 partial `result.json`；任何分支结束前 finalize 覆盖 |
| 预算 | 64 请求 / 900 s / 16384 tokens；本 Skill 不发模型请求，单次纯 CPU 运行；内部 780 s 截止（`runtime.budget.deadline_s`），到时立即 finalize |
| 依赖 | 仅 Python 3 标准库；`pdftotext`/`pypdf`/`fitz` 若存在则优先（`shutil.which` / `try-import` 探测），缺失自动降级到内置抽取器 |

调用（脚本用 `Path(__file__).resolve().parent` 定位资源，不依赖 CWD）：

```bash
python3 -B /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output
python3 -B /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output --help
```

## 4. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；缺失则递归找 `case*.json` / `task.md` / `*manifest*.json`，仍解析。
2. 原样保留 `case_id` 与 `output_contract`（键名不改、未知字段保留）。
3. 语义抽取（键名不固定，按同义词命中）：`task_instruction`、`organizer_supplied_scope`（topic / db / years / lang / include / exclude / seeds / max_k）、`formal_inputs`、`runtime_files`、`artifacts/`、`material.json`。
4. 递归扫描 `/input/**`，按**扩展名 + 魔数**识别：PDF(`%PDF`)、DOCX/ZIP、PNG/JPG/JPEG、CSV、XLSX、JSON、JSONL、TXT/MD。不靠文件名标签猜内容。
5. 文献记录不依赖固定 `title` 键：用 `title`/`Title`/`paperTitle`/`题名`、`DOI`/`doi`/`identifier`、`author`/`authors`/`authorString`、`year`/`issued`/`published`/`firstPublicationDate`、`container-title`/`journal`/`venue` 等**同义词组**识别，兼容 Crossref `message.items`、EuropePMC `resultList.result`、裸 list、JSONL。
6. 材料未给的对象写入 `missing[]`（例：`fulltext_for:<doc>`、`doi_for:<doc>`、`query_log`），**不构造**。

## 5. 输出契约

`result.json` 顶层 = **输入 `output_contract` 的每个键（原样、逐字段）** + 本 Skill 标准键。回填算法：

- 先建契约模板：`null`（标量名未知时）/`[]`（列表型）/`{}`（字典型）；
- 已知语义键按同义映射填值（`candidates|papers|records|literatures` → 候选集；`queries|query_log|logs` → 检索日志；`screening|filters` → 筛选；`coverage|gaps` → 覆盖；`citations|clusters` → 引用/聚类以输入里有则填否则 `[]`；`appraisal*|assessment*|quality*|grades` → 评价）；
- 未识别键保持 `null`/`[]` 并登记在 `output_contract_unfilled[]`；
- `output_contract_echo` 保留输入原文，便于逐字段核对。

标准键：`case_id` `status`(ok|partial|insufficient_evidence|input_error) `skill` `task` `inputs` `candidates` `queries` `appraisals` `appraisal_items` `grades` `coverage` `metrics` `artifacts` `sources` `uncertainty` `pending_human` `errors` `degradations` `changes` `missing` `selfcheck` `output_contract` `output_contract_unfilled` `runtime`。其中 `grades` 与 `appraisals` 同源（文档级：设计、风险、置信、`per_domain`、`grade_trace`）。

行级评价字段（`appraisal_items[]`，与 `appraisal.csv` 同列）：`doc_id, dimension, item_id, item_label, judgment, evidence_quote, locator_page, locator_section, evidence_scope, quote_verified, char_start, probe_hit, confidence, human_override, override_reason, adjudication`。

## 6. 核心流程

1. **落盘**：写 partial `result.json`（契约模板 + `status:"partial"`）。
2. **发现与解析**：扫描 `/input`，抽文本（PDF 三路：`pdftotext` → 可选 `pypdf`/`fitz` → 内置 zlib 流解析；DOCX 走 zip+XML；TXT/MD 直读），记录 `text_source` 与页数。
3. **候选集**：从题录/检索响应聚合记录 → DOI/标题去重 → 相关性打分（scope 关键词 + 种子）→ 排序 → 筛选（含 year/lang 边界）→ 输出候选表 + 日志。
4. **类型识别**：按标题/摘要/全文判定研究设计（RCT / 队列 / 病例对照 / 横断面 / 系统评价-Meta / 诊断准确性 / 定性 / 建模预测 / 其他），记录判定依据与置信度。
5. **逐条评价**：按设计取用条目库（`references/rubric.md` 的机器可读 `items` 块）→ 证据探针在**句级**检索 → 抽最佳句 → 逐字校验 → 判定 → 生成偏倚领域与等级。
6. **汇总与自检**：算 `metrics`（条目覆盖、证据锚定率、可复核行数）→ 写 CSV/JSON/MD → 内建 `selfcheck` 断言 → finalize。

## 7. 量表结构（详见 `references/rubric.md`）

四类必评维度 + 类型特有检查点：

| 维度 | 覆盖内容 | 必答问题 |
|---|---|---|
| D1 研究设计 | 设计表述、研究问题、纳入排除、样本来源、对照、随访 | 这个设计能否支持它的结论？ |
| D2 证据充分性 | 结局定义、效应量与精度、样本量依据、混杂控制、稳健性、结论一致性 | 数据够不够支撑这句话？ |
| D3 偏倚风险 | 选择/混杂/实施/测量/失访/选择性报告 | 风险落在哪个具体环节？ |
| D4 报告完整性 | 数值逐项报告、局限性、利益冲突与资助、注册/方案/数据可得 | 缺了哪些必须报告项？ |

判定词表（固定，不可混用）：`reported` / `partially_reported` / `not_reported` / `unappraisable`；偏倚领域四档：`明确存在` / `可能存在` / `未见迹象` / `证据不足`。

## 8. 证据与定位规范

- 每条 `reported`/`partially_reported` **必须**带 `evidence_quote`（原文逐字，去多余空白后仍是原文子串）+ `locator_page`（页码，从 1 起）+ `locator_section`（章节名，来自标题行或 `unknown`）+ `char_start`（归一化全文偏移）。
- 校验：脚本在归一化文本中查子串，命中 `quote_verified:"verified"`；不命中则**不改原文**，降级为 `unappraisable` + `pending_human`（`reason:"quote_not_found"`）。绝不改写 quote 去凑命中。
- 若证据只出现在摘要区而条目要求方法与结果区：判定 `partially_reported`，`evidence_scope:"abstract"`，并在 `uncertainty` 记一条——这是"只复述摘要"与"落到方法细节"的分界。
- `not_reported` 仅在**全文可得且探针确实跑过全文**时使用；摘要模式或文本不可得一律 `unappraisable`（`abstain_reason`）。
- 图像/扫描件无法取文本：`text_source:"none"`，该文档全条目 `unappraisable`，`pending_human` 记 OCR 需求，不猜图内容。

## 9. 分级与弃权（阈值见 `references/rubric.md` §5）

- 偏倚领域赋分：`明确存在`=2、`可能存在`=1、`未见迹象`=0、`证据不足`=0.5（并计入弃权数）。
- `overall_risk`：`coverage < 0.40` → `unappraisable`；任一关键领域（选择/混杂/选择性报告）为 `明确存在` 或 `bias_points ≥ 4.0` → `high`；`bias_points ≥ 1.0` → `some_concerns`；`coverage ≥ 0.60` 且 0 分 → `low`；其余 `some_concerns`。
- `confidence`：全文且覆盖 ≥ 0.70 → `high`；全文且 ≥ 0.40 → `moderate`；仅摘要/无文本 → `low`。
- 每条等级必须附 `grade_trace`（参与的条目 id、判定、赋分与算式），只给标签不给轨迹视为未完成。
- **弃权优先于猜测**：拿不到证据时输出 `unappraisable` + 缺什么证据 + 需要哪一页/哪张表，而不是补一个看似合理的判断。

## 10. 冲突与人工确认

- 同一文档同一 DOI 出现相互矛盾的题录（年份/期刊/作者不符）：两版并存写入 `candidates[].flags:"metadata_conflict"`，以 `source_priority` 排序（Crossref/EuropePMC 优先于无来源记录），冲突本身进 `uncertainty`，不静默取其一。
- 复核入口：`appraisal.csv` 保留空列 `human_override` / `override_reason` / `adjudication`，评审可原位改写；脚本重跑不覆盖非空 override（`--keep-overrides` 默认开）。
- 双人复核与裁决协议见 `references/playbook.md` §5（独立评分 → 逐条比对 → 分歧按"证据是否存在"裁决 → 分歧条目沉淀为探针/词表修订，而非一次性修补）。

## 11. 预算与断点

单次运行纯 CPU，无网络、无模型调用。分阶段写盘：partial → 候选集 → 评价表 → finalize；每阶段后 `json.dump` 原子写（`tmp` + `os.replace`）。内部截止 780 s（`runtime.budget.deadline_s`）到达后停止新增文档评价并 finalize 当前结果，缺口进 `pending_human`。

## 12. 异常降级分支表

| 情况 | 处理 | 记录 |
|---|---|---|
| `/input` 不存在 / 空 | 写契约模板 partial，`status:"input_error"`，退出 0 | `errors` |
| `case.json` 非法 JSON | 用文本兜底抓 `case_id`/`output_contract` 片段，失败则空模板 | `errors`,`degradations` |
| 无 `output_contract` | 输出标准键全套，`output_contract_unfilled:["<absent>"]` | `uncertainty` |
| PDF 文本抽取为空/乱码 | 依次降级 pdftotext→pypdf→内置；仍失败标 `text_source:"none"` + OCR 需求 | `degradations`,`pending_human` |
| 仅摘要 | 全条目上限 `partially_reported`/`unappraisable`，`overall_risk` 置信 `low` | `uncertainty` |
| 元数据缺 DOI/年份/期刊 | 字段 `null` + `flags`，不补造 | `missing` |
| 检索响应含 `error`/`status!=ok`/限流字样 | 该 query 记 `status:"error"`，不重试不编造结果 | `queries[].error` |
| 记录全部重复 | 合并为一，保留 `provenance[]` 多来源 | `changes` |
| 单文档解析失败 | 只降级该文档，其余继续（不误杀全局） | `degradations` |
| 输入含图片且无文本 | 登记 `pending_human:"ocr"`，不描述图内容 | `pending_human` |

## 13. 自检清单

```bash
python3 -B scripts/appraise.py --input /input --output /app/output   # 期望 exit 0
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['selfcheck'], r['output_contract_unfilled'])"
```

**内建自检（`selfcheck`）**：每次运行把三项断言写进 `result.json.selfcheck` ——
`contract_keys_resolved`（契约键是否都拿到值）、`verified_rows_located`（凡 `quote_verified:"verified"` 的行必有 quote 且 `locator_page ≥ 1`）、`unappraisable_reasoned`（凡 `unappraisable` 必有 `abstain_reason`）。

**第二人复核步骤（5 步，不需再做别的工具）**：
1. `appraisal.csv` 按 `doc_id + item_id` 排序，检查每行是否 `judgment` 与 `evidence_quote` 自洽；
2. 打开 `locator_page` 指的那一页，核对 quote 是否逐字存在（`char_start` 给出归一化偏移）；
3. `not_reported` 行要在该文档全文里反向搜一遍探针词，确认确实没有；
4. `unappraisable` 行检查 `abstain_reason` 是否成立（如 `abstract_only` 是否真的没有全文）；
5. `candidates.csv` 每条回查 `source_file + json_pointer`（写在 `result.json.candidates[].provenance`）。

## 14. 最小调用示例（**示例，非正式案例结果**）

输入（`/input/case.json`，示例）：

```json
{"case_id":"demo-001","task_instruction":"评价所给文献的研究质量",
 "output_contract":{"candidates":[],"queries":[],"appraisal":[],"status":null,"notes":null},
 "organizer_supplied_scope":{"topic":"statin adherence","years":[2015,2024]},
 "artifacts":["artifacts/epmc.json"]}
```

调用：`python3 -B scripts/appraise.py --input /input --output /app/output`

示意输出（示例，非正式案例结果）：

```json
{"case_id":"demo-001","status":"partial",
 "candidates":[{"candidate_id":"c001","title":"…","doi":"10.xxxx/demo","source_db":"EuropePMC",
                "retrieved_at":"2024-01-01T00:00:00Z","query_id":"q1","relevance_score":3.5}],
 "appraisal_items":[{"doc_id":"d001","dimension":"D2","item_id":"D2.2","judgment":"reported",
                     "evidence_quote":"…(原文示例)…","locator_page":4,"quote_verified":"verified"}],
 "output_contract":{"candidates":["…"],"queries":["…"],"appraisal":["…"],"status":"partial","notes":null},
 "pending_human":[]}
```

## 15. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 入口：用途、契约、流程、异常、自检 |
| `scripts/appraise.py` | 主流程：发现→解析→候选集→评价→分级→写盘→finalize（含 `selfcheck`） |
| `scripts/engine.py` | 解析与评价引擎：PDF/DOCX 抽取、题录识别、句级探针、量表读取、分级算式 |
| `references/rubric.md` | 量表：条目库（机器可读）、判定规则、偏倚映射、分级阈值 |
| `references/io_contract.md` | 输入发现细则、输出 schema、契约回填算法、示例 |
| `references/playbook.md` | 定位规范、探针编写、缺口分类、双人复核与裁决、失败经验 |

版本 1.0.0。维护：新增条目 → 改 `references/rubric.md` 的 `items` 块（脚本自动读取，无需改代码）；阈值调整 → 改 §5 并在 `result.json.runtime.rubric_version` 记录。所有判断均可由 `appraisal.csv` 的 `item_id + locator_page + char_start` 回溯，规则变更须递增 `rubric_version`。
