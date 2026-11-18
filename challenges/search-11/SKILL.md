---
name: patent-topic-search
description: 专利与技术文献检索 Skill。给定公开号/申请号/授权号/优先权号或技术主题，在授权来源（输入材料与本地语料）内完成号码规范化、同族（仅观测链接）归并、法律状态分级核验、权利要求范围取证、技术文献候选检索与筛选留痕，输出 result.json + candidates.csv/json + query_log.json + verify_report.json，并对空结果、限流、鉴权失败、状态冲突、字段缺失给出降级与人工复核清单。适用于专利查新、企业研发情报、同族与法律状态核对；不用于专利撰写、侵权判定、自由实施(FTO)结论或专利价值评估。
version: 1.1.0
---

# 专利与技术文献检索（patent-topic-search）

## 1. 用途与边界

**做**：从号码或主题出发，在**有授权的来源**内定位专利与相关技术文献，产出可被他人按记录复跑的证据集：
号码规范化 → 同族（观测链接）归并 → 法律状态分级 → 权利要求取证 → 主题检索与筛选 → 契约回填与自检。

**不做**（越界即失分）：专利撰写与权利要求起草；侵权判定、FTO 结论、专利价值评估；替代专利律师意见；
绕过付费墙、上传受限数据、对外展示受限库原文；**不补造**号码、文献、DOI、法律状态或"最新进展"。

**三个硬边界**（题面点名的失败模式，本 Skill 专门规避）：
1. 公开号/授权号/申请号**混用** → 每个号码带 `number_kind` 与 `role`，未知即标 `unknown` + `warnings`。
2. **同族当权威结论** → 只按语料中**观测到的**优先权/申请号连边，标注 `observed_links_only` 与"非穷尽"。
3. **法律状态来自转载页** → 无官方登记定位时状态一律为 `not_in_corpus`，进 `pending_human`，绝不用 kind code 推断有效/失效。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（或 `task.md`）与 `/input/**` 内的材料；**只读** |
| 输出 | `/app/output/`：`result.json`、`candidates.csv`、`candidates.json`、`query_log.json`、`verify_report.json` |
| 入口 | `python3 -B scripts/main.py --input /input --output /app/output` |
| 依赖 | Python 3.8+ **标准库**；`pdftotext` 可选（缺失时用内置流解析并记录 tier）；**不联网** |
| 退出码 | **恒为 0**（含参数错误、空输入、坏 JSON、阶段异常） |
| 预算 | 单次运行近似 O(材料量)，无模型请求；不设 900s 上限的等待行为 |
| 首次落盘 | `main()` 一开始就写合法 `result.json`（`status=partial`），随后覆盖为最终版 |

脚本分工（共 2 个，均在 `scripts/`，各 ≤20KB）：
`main.py` 编排/候选组装/筛选/契约回填/自检；`ptcore.py` 输入发现、号码规则、同族、状态分级、权利要求、检索打分。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则找任意 `**/case*.json`；仍无则退回 `task.md` 文本（并写 degradation）。
2. 原样保留 `case_id` 与 `output_contract`（不改键名、不丢未知键）。
3. 递归扫描 `/input/**`，按**扩展名 + 内容语义**识别：
   `.json/.jsonl`（记录、查询、缓存响应）、`.csv`（记录表）、`.pdf`（传真件/论文）、`.md/.txt`（正文、权利要求、任务说明）、图片（记缺口）。
   记录判定看是否存在公开号/申请号/优先权/分类号类字段；文献判定看 DOI/题名/作者/期刊。
4. 文件名含 `quer` → 视为**声明的检索式**（写入 query_log，标 `explicit`）；含 `response/hit/api/result` → 视为**缓存响应**（记录 `http_status`，429/401/403 走降级）。
5. 材料未给的对象**明确列缺口**（`gaps` / `pending_human`），不构造内容。

## 4. 输出契约（`result.json`）

```text
case_id, status, skill, generated_at, input_case
<output_contract 的每一个键，原样键名>
sources[], uncertainty[], errors[], degradations[], pending_human[], changes[], runtime{}
contract_fill{contract_echo, filled_from_payload, placeholder_only}
candidates[], queries[], screening[], coverage{}, families[], clusters[], legal_status[], claims[],
citations[], metrics{}, gaps[], summary{}, gain{}, artefacts[], self_check{}, verification{}
```

- **契约回填**：`output_contract` 每个键都出现在根级；语义匹配（如 `results/papers/documents` → `candidates`）则填真实数据，否则按原值类型给空占位（`[]`/`{}`/`""`/`null`），并在 `degradations` 记录"未映射键已空占位、未编造"。`contract_echo` 保留原始契约。
- `status`：`ok`（有候选且无 error）/ `partial`（有材料但未完成或有 error）/ `insufficient_evidence`（无可检索内容或输入缺失）。输入缺失不单列 `input_error`，而是 `insufficient_evidence` + `errors[]`（说明"输入缺失"），以避免状态语义漂移。
- 字段级说明见 `references/output_fields.md`。

## 5. 核心流程（7 步）

| 步 | 动作 | 产出 |
|---|---|---|
| S1 | 首次写 partial `result.json` | 任何后续中断都不至于空盘 |
| S2 | 发现并解析材料（PDF 三级提取、JSON/JSONL/CSV/文本） | 文档集 + `sources[]`（含 sha256、retrieved_at、extractor） |
| S3 | 号码规范化（每记录分角色） | `numbers`、`number_roles`、`warnings` |
| S4 | 查询规划：声明式 → 号码 → 主题 + 语料扩展（高频共现词、IPC/CPC） | `queries[]`（hits/kept/status/error） |
| S5 | 检索打分与排序；同族（观测链接）并查集；状态分级；权利要求逐条取证 | `candidates[]`、`families[]`、`legal_status[]`、`claims[]` |
| S6 | 筛选（重复/年份/无引文）+ 覆盖率 + 指标 + 基线对照 | `screening[]`、`coverage`、`metrics`、`gain` |
| S7 | 写 artefact → 自检（`verify_report.json`）→ 覆盖 `result.json` | 交付件 + `verification` |

## 6. 评分要点 → 字段/检查/产物（逐条对应）

| 评分维度（题面 2 节） | 本 Skill 的落点 | 可核验位置 |
|---|---|---|
| 任务完成度 | `summary.what_was_done` / `coverage.surfaces`（目标专利、同族、技术文献、状态、权利要求五个面） | `result.json` |
| 结果正确性（号码/族/状态/权利要求不越界） | `number_kind`+`warnings`；`families.caliber/exhaustiveness`；`legal_status.verification`；`claims.scope_statement` | `candidates[*].numbers`、`families[*]`、`legal_status[*]` |
| 结果完整性 | `coverage.gaps`（外部库未查、族非穷尽、状态未核、OCR 边界）；`screening` 的排除理由 | `result.json` |
| 结果可核验性 | 每候选 `query_id + source_file + source_sha256 + locator + retrieved_at + evidence.quote`；`verify_report.json` 的 6 项检查 | `candidates.*`、`query_log.json`、`verify_report.json` |
| 质量增益 | `gain.baseline`（同语料、同预算的朴素关键词臂）与 `delta`；明显注明**非**组织方白板 | `result.json.gain` |
| 效率增益 | 一次运行产出"号码定位+主题检索+状态分级+权利要求取证"四件事；`metrics` 给出 locator/quote 覆盖 | `metrics` |
| 增益可验证性 | `gain.protocol` 写清同输入/同权限/同口径；基线指标可复算 | `gain`、`metrics` |
| 新增能力（号码规范化/族归并/状态追踪/受限降级） | `ptcore.nn()` 的多国号码规则；并查集只连观测链接；状态分级三档；`degradations[]` | 脚本 + `references/number_and_status.md` |
| 方法改进 | 检索式分面（关键词/IPC/申请人/共现扩展）；打分权重与分量；字段口径表 | `queries[*].expanded`、`relevance_reason`、`score_components` |
| 创新证据 | 与商用库/通用 Agent/人工查新的边界写在 `summary.what_was_not_done` 与 `coverage.recall_estimate` | `result.json` |
| 调用与易用性 | 单命令、`--help`、默认路径、失败也出件 | `SKILL.md` §2/§13 |
| 运行稳定性 | 阶段隔离（`stg`），单材料失败不扩散；重复运行幂等（见 §12） | `errors[*].stage`、`degradations[*].stage` |
| 异常处理 | 429/401/403/空命中/坏 JSON/无文本层/状态冲突/字段缺失 均有分支与记录 | §10 降级表 |
| 文档完整性 | 本文件 + 3 份 references（号码与状态、检索与证据、输出字段） | `references/` |
| 资源可复用性 | 号码规则表、kind code 表、状态词表、打分公式、检查清单可单独复用 | `references/*` |
| 分享推广价值 | 可复现的最小示例（§12，标注示例）、失败模式对照表 | 本文件 |

## 7. 证据与定位规范

- **quote 必须逐字**：只取来源中的**单个字段值**（`abstract|summary|description|claims|title`），不做字符串拼接、不润色、不修正 OCR 断行；`quote_field` 记录取自哪个字段。
- **locator** 形如 `records.jsonl#/0`、`patents/US99000000B2.txt#char:0+char:241`、`page:1`、`row:7`。
- **版本**：`source_sha256` 是读取时的文件哈希；`sources[*].sha256` 另存短哈希，二者一致即同一版本。
- **时间**：`retrieved_at` 是**读取来源**的时刻（离线运行=运行时刻），不是数据库的公开日。
- **自检**：`verify_report.json` 逐条复核 `contract_keys_present`、`quote_found_in_source`、`number_shape`、`csv_vs_json_count`、`status_never_inferred`、`artefacts_present`；`quote_verified=false` 会写入候选的 `evidence`，从而暴露"引不到原文"的候选。

## 8. 号码、字段口径与同族

- 规范化输出：`country / number_kind(publication|grant|application|pct_application|unknown) / role / kind_code / digits / year / canonical / stem / valid_format / warnings`。
- 规则要点（详见 `references/number_and_status.md`）：US 公开号 11 位=年+7 位、授权号 7–8 位、申请号=系列号/流水号；WO 年+6 位；EP 7–8 位；CN 9 位为公开、12–13 位为申请；JP 年+6 位为公开、7 位为授权；`PCT/CCYYYY/NNNNNN` 记为 `pct_application` 并警告"非公开号"。
- **同族**：仅在 `priority` 或 `application` 号码完全一致时连边（并查集），`caliber=observed_links_only`、`exhaustiveness=NOT exhaustive (no INPADOC/DOCDB offline)`、`claim_scope_note=links only; NOT equal claim scope`。**未连边不等于无族**。

## 9. 法律状态核验（三档）

| verification | 条件 | 用法 |
|---|---|---|
| `sourced_official_register` | 材料内状态字段 + **官方域名** URL（uspto.gov / epo.org / wipo.int / cnipa.gov.cn / j-platpat / jpo.go.jp / kipris.or.kr） | 可引用，须附来源 URL 与查询日期 |
| `secondary_or_unknown_provenance` | 有状态文本但无官方定位 | 仅作线索，进 `uncertainty` |
| `not_in_corpus` | 材料无状态字段 | **不得**给出有效/失效结论；进 `pending_human`，并给 `kind_code_hint` 说明 kind code 只是公开阶段 |

冲突处理：同一号码出现不同状态 → 写 `uncertainty[id=status_conflict:*]`，结论"按登记查询日期定序、不得取平均"。

## 10. 降级与异常分支

| 触发 | 处置 | 记录位置 |
|---|---|---|
| `case.json` 缺失 | 用 `task.md` 文本当任务指令，继续跑 | `degradations` |
| `case.json` 坏 JSON | 记 error，退回语义扫描，仍出件 | `errors` + `uncertainty` |
| 某材料解析失败 | 只跳过该文件 | `errors[stage=ingest]` |
| PDF 无文本层（扫描件） | 记 error + 该文档不参与结论；`flags=ocr_page_merged` 用于合并 OCR 页 | `errors`、`gaps` |
| 外部响应 429/限流 | 用缓存载荷，不重试风暴，预算保留 | `degradations` + `uncertainty` |
| 401/403 鉴权失败 | 该源排除，**不猜测、不绕付费墙** | `errors` |
| 查询无命中 | `status=no_hit` + `uncertainty`：这是覆盖限制，**不是**不存在证据 | `queries`、`uncertainty` |
| 缺法律状态 | `pending_human` + 逐号码复核说明 | `pending_human` |
| 状态冲突 | `uncertainty` + 定序规则 | `uncertainty` |
| 号码格式异常 | `warnings`（no_kind / length… ），仍保留记录 | `candidates[*].numbers`、`metrics.number_warnings` |
| 阶段异常 | 该阶段返回空默认，后续继续，最终 `status=partial` | `errors[stage=*]`、`degradations` |
| 输出目录不可写 | 退到临时目录并记录 | `degradations` |

## 11. 预算与断点

无网络调用、无模型请求；复杂度与材料量线性相关（单文件上限 2MB 读取、400 文件上限）。
首次 `partial` 落盘 + 阶段隔离 ⇒ 任何中断都留下可读结果；`runtime.seconds` 记录实际耗时。

## 12. 最小调用示例（**示例，非正式案例结果**）

输入（虚构，仅示接口）`/input/case.json`：
```json
{"case_id": "EXAMPLE-CASE-000",
 "task_instruction": "定位目标专利、观测同族、法律状态与权利要求范围，并检索同主题技术文献",
 "output_contract": {"candidates": [], "queries": [], "coverage": {}, "families": [], "notes": ""},
 "organizer_supplied_scope": {"topic": "ceramic coated separator solid electrolyte lithium cell",
   "years": "2015-2024", "seeds": ["US 99,000,000 B2"], "max_k": 10}}
```
调用：
```bash
python3 -B scripts/main.py --input /input --output /app/output
```
示意输出（**示例**，键值截断；正式运行以实际材料为准）：
```json
{"case_id": "EXAMPLE-CASE-000", "status": "ok",
 "candidates": [{"id": "C01", "kind": "primary", "numbers": ["US99000000B2"],
   "source_file": "records.jsonl", "locator": "/0", "query_id": "Q01", "retrieved_at": "…",
   "relevance_score": 0.57, "relevance_reason": "number_exact(US99000000B2); terms=0.35(7/20)",
   "legal_status": "unknown", "legal_status_verification": "not_in_corpus", "family_id": "F01",
   "evidence": {"quote": "…", "quote_verified": true}}],
 "families": [{"family_id": "F01", "caliber": "observed_links_only",
   "exhaustiveness": "NOT exhaustive offline (no INPADOC/DOCDB)"}],
 "queries": [{"query_id": "Q01", "type": "number", "hits": 2, "kept": 2, "status": "ok"}],
 "notes": "", "verification": {"passed": true}}
```

## 13. 自查清单（交付前）

1. `result.json` 可被 `json.load` 解析，`case_id` 与输入一致。
2. `output_contract` 每个键都在根级；未映射键为**空占位**且有 degradation 说明。
3. 每个候选都有 `query_id / source_file / locator / retrieved_at / evidence.quote`。
4. `verify_report.json.passed=true`；若 false，逐条看 `failed` 并修数据或如实降级。
5. 任何法律状态结论都有 `verification` 与官方定位；否则在 `pending_human`。
6. `families[*].caliber` 为 `observed_links_only`，无"完整族"措辞。
7. 空命中/限流/鉴权/缺字段各有记录，未编造替代结果。
8. 退出码 0；无 `__pycache__`、无临时文件、无预制答案。

## 14. 文件清单与版本

| 文件 | 作用 | 大小 |
|---|---|---|
| `SKILL.md` | 本说明（用途、契约、流程、评分映射、降级、自查） | 见提交报告 |
| `scripts/main.py` | 入口：编排、候选组装、筛选、契约回填、自检 artefact | ≤20KB |
| `scripts/ptcore.py` | 数据层：发现、号码、同族、状态、权利要求、检索打分 | ≤20KB |
| `references/number_and_status.md` | 各国号码格式、kind code 表、状态词表、官方登记入口 | 文本 |
| `references/search_and_evidence.md` | 检索式分面模板、打分公式、证据规范、降级表 | 文本 |
| `references/output_fields.md` | `result.json` 字段字典、状态枚举、契约回填语义、示例 | 文本 |

版本 `1.1.0`：合并确定性自检进 `main.py`（脚本数上限 2 的限制），新增 `pct_application` 识别与传真件首页号码抽取。

## 15. 维护说明

- 新增国家/局：在 `ptcore.py` 的 `CC`、号码规则分支与 `nn()` 的 `number_kind` 判定中扩展；同步 `references/number_and_status.md` 的格式表。
- 接入真实数据库：替换 `ptcore.qplan()/retrieve()` 的 `db` 与取数层，保持 `query_id → source → retrieved_at` 三元组不变；限流/鉴权沿用 §10 分支。
- 法律状态：接入官方登记 API 后，把 `legal()` 的 `verification` 依据改为"官方返回 + 查询日期"，其余口径不变。
- 修改任一规则后，先跑 §13 自查，再看 `verify_report.json`；`quote_found_in_source` 失败通常意味着改了抽取逻辑而不是材料问题。
