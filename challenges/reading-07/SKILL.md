---
name: literature-evidence-verification
description: Verify whether a claim about a paper, report or dataset is actually supported by the source text, not merely on-topic. Splits compound claims into atomic fact/comparison/causal/scope sub-claims, locates verbatim evidence with paragraph/page/field locators, and assigns one of four support levels—supported, partially_supported, contradicted, insufficient_evidence—with reasons, conflict pairing, uncertainty, and explicit limits. Use when the user asks to fact-check a claim, audit a citation, verify a claim list against a PDF, or produce evidence cards. Emphasizes actual source parsing, deterministic fallback, agent-authored final outputs, and honest partial delivery.
version: 3.0.0
---

# 文献证据溯源与事实核验 Skill：Agent 执行手册

## 0. 最高优先级：一条命令，全流程可运行

1. **先跑脚本基座，再做 Agent 核验。** 首选单命令：

   ```bash
   python3 -B scripts/verify_claims.py --input /input --output /app/output
   ```

   若安装的 `scripts/verify_claims.py` 支持 `--work`，优先使用：

   ```bash
   python3 -B scripts/verify_claims.py --input /input --output /app/output --work /app/work
   ```

   该命令内部等价于：`init`（材料盘点、来源编号、候选抽取、冲突分组）→ `build`（校验、兜底抽取、渲染全部产物、finalize `result.json`）→ `selfcheck`（产物与契约自检）。**没有人工草稿时，脚本必须用确定性抽取生成实质工作稿**：逐字 quote、locator、四级判定候选，并诚实写入 `AUTO_EXTRACT`。Agent 后续增量改进不能破坏这条基座。

2. **任何情况下退出码必须为 0。** 脚本崩溃时，阅读 traceback，尝试用 `scripts/verify_claims.py --help` 找到最小可用参数；若无法修复，则按 `references/io-contract.md` 手写最小合法 `result.json`，所有 claim 判 `insufficient_evidence`，并记录错误与可人工接管位置。

3. **结构化 JSON 不得手工编辑。** `result.json`、`evidence_cards.jsonl` 等结构化产物由脚本生成或由 `scripts/lit_core.py` 内的函数重算后覆盖。Agent 的核验、修正、改写通过 `/app/work/draft.json`、`/app/work/agent_review.json` 与脚本功能完成，不得直接改 JSON 文本。

---

## 1. 用途、触发与拒绝边界

### 适用

- 核对一个或多个科学论断是否真正被原文支持。
- 检查引用是否包含对应结论，尤其是摘要与正文不一致、跨页证据、图表引用。
- 输出证据卡片：`论断 → 证据片段 → 原文定位 → 支持度判定 → 判定理由`。
- 批量核验 `claims-to-verify.json` 或 `case.json` 中的 claims。

### 触发

- “帮我核验这句话/这段论断/这些 claims。”
- “检查引用是否真的支持结论。”
- “对这篇论文做引用审计/事实核验。”

### 拒绝/不适用

- 写论文、翻译、绘图、跑数值实验、跨文献 meta 分析等不属于单个文献证据核验的请求，直接说明不适用。
- 缺少 claims 或材料时，不发明论断、不补造科学数据，只返回 `status=input_error` 或 `partial`。

---

## 2. 输入、材料与运行目录

### 输入文件优先级

1. `/input/case.json`：`case_id`、`output_contract`、可能的 claims 或材料清单。
2. `/input/task.md`：任务要求、文件约定、额外输出字段。
3. `/input/claims-to-verify.json`：实际待核验论断。**这些是问题，不是权威事实。**
4. `/input/` 下所有材料：PDF、JSON、CSV、TXT、MD、DOCX、HTML 等。

### claims 字段别名

- claim 文本：`claim_text | text | statement | claim | sentence | quote`
- claim ID：`claim_id | cid | id | claim_no`
- claims 列表可能位于 `claims`、`claims_to_verify`、`statements`、`audit_claims`、`input.claims`。
- 纯字符串列表：自造 `C1..Cn`，并回填 `input_claim_id`。

### 输出

- 最终产物必须在 `/app/output/`。
- 中间语料、候选、草稿、agent 改稿放在 `/app/work/`。
- 最终结果至少包含：
  - `result.json`
  - `evidence_cards.jsonl`
  - `verification_report.md`
  - 若合同要求可编辑 Office/幻灯片/图形产物，则须同时附真实渲染的 PDF/PNG 预览。

---

## 3. 执行流程：init → build → selfcheck

### Phase 1：init —— 盘点、抽取、候选

1. 读取 `case_id`、`output_contract`、claims 列表、材料清单。
2. 在 `/app/work/manifest.json` 记录：
   - `case_id`
   - `contract_fields`：原始 `output_contract` 键列表
   - `claim_count`
   - `sources[]`：来源文件、格式、可解析方式、页数/单元数
   - `missing_inputs[]`
3. 真实解析材料：
   - 对 PDF 使用平台预装的 `pdftotext` 或 `pdf-text-tool`；记录 `extraction_method`。
   - 将文本切成带 locator 的段落/句子单元，写 `/app/work/corpus.jsonl`。
   - 每条包含 `source_id`、`unit_id`、`section`、`page`、`block`、`text`。
4. 拆解 claims：
   - 每个 claim 拆成 1–7 个子判断，类型：`fact / comparison / causal / scope`。
   - 为每个子判断标注 `required_evidence_type`。
   - 提取并保留 `comparator`、`negation`、`significance`、`conditions`、数值/型号锚点。
5. 确定性候选抽取：
   - 为每个子判断检索最小充分证据：逐字 quote + locator。
   - 不要只按主题相关性泛泛匹配；必须检查比较词、否定词、显著性、条件。
   - 冲突证据同时保留双方。
   - 写 `/app/work/candidates.json`。

### Phase 2：build —— 兜底抽取与产物渲染

1. 运行脚本基座生成全套基线：
   ```bash
   python3 -B scripts/verify_claims.py --input /input --output /app/output
   ```
2. 脚本必须产出并保留：
   - `result.json`
   - `evidence_cards.jsonl`
   - `verification_report.md`
3. 如果没有 Agent 草稿，脚本使用 init 阶段候选稿确定性生成工作稿。该稿必须：
   - 每条有 `verdict`：仅限 `supported / partially_supported / contradicted / insufficient_evidence`
   - 每条有 `quote` 与 `locator`
   - 标 `reviewed_by_agent: false`
   - 标 `extraction_method: "deterministic"`
   - 在 `degradations` / `gaps` 中写 `AUTO_EXTRACT`
4. 检查合同：`result.json` 顶层必须包含 `case_id` 与 `output_contract` 的每一个键；缺失用 `null / [] / {}` 补齐，并在 `degradations` 记录 `contract_field_filled_empty`。
5. 若题面要求可编辑 Office/幻灯片/图形产物，生成可编辑文件和真实渲染 PDF/PNG 预览；若渲染失败，保留可编辑文件并写 `degradations`，用纯文本或 HTML 预览替代。

### Phase 3：Agent 路径 —— 真实阅读与增量核验

1. 在脚本基座完成后，Agent 必须真实读取 `/input` 材料原文，逐条核验：
   - 抽取的 quote 是否逐字存在；
   - locator 是否指向正确 section/paragraph/page；
   - 数字、比较词、否定词、显著性、条件是否未被截断；
   - `supported` / `contradicted` 是否真的站得住，尤其要防止“主题相关”被判为“支持”。
2. Agent 修正写入 `/app/work/draft.json`，推荐形状：
   ```json
   {
     "overrides": [
       {
         "claim_id": "C1",
         "verdict": "partially_supported",
         "quote": "原文逐字句",
         "locator": {"source_id": "S1", "unit_id": "P3", "page": 5},
         "rationale": "判定理由",
         "confidence": "low|medium|high"
       }
     ]
   }
   ```
3. 若脚本支持 `--draft /app/work/draft.json`，则重新运行脚本合并 draft；若脚本不支持，则使用 `scripts/lit_core.py` 中的读取/合并/写入函数重算并覆盖 JSON，**不得手工编辑 JSON 文本**。所有 Agent 改过项写 `reviewed_by_agent: true` 与 `change_record`。
4. Agent 额外写 `/app/work/agent_review.json`：
   - 逐条 claim_id → `verified/rejected/reason`
   - `script_fixes`
   - `uncorrected_baseline_issues`
5. Agent 亲自撰写/改写正文型交付物，如 `verification_report.md` 或题面要求的可编辑产物。每个数字、引用、论断必须在 `evidence_cards.jsonl` 或 `result.json.verifications[]` 中有依据。

### Phase 4：selfcheck —— 契约与证据链自检

结束前逐项核对：

1. `result.json` 合法 JSON，`case_id` 与输入一致，或诚实标 `UNKNOWN`。
2. `output_contract` 的每个字段同时出现在：
   - `result.json` 顶层
   - `result.json.output_contract`（嵌套回显）
3. 每条输入 claim 都有 `verdict`，且只取四值之一。
4. 每个子判断有证据，或 `insufficient_evidence` 且 `search_scope` 非空。
5. 每条 quote 可在 `sources[].path` 对应文件中逐字检索；找不到就弃用，改 `pending_human`，不得改原文凑通过。
6. 含比较/否定/显著的 claim，`comparator/negation/significance` 非空。
7. 冲突两侧都有 locator + quote，保留性判定写 `qualified_verdict`，通常 `partially_supported` 且 `confidence=low`。
8. `coverage` 计数自洽；未报告项写 `uncertainty`；需人工项写 `pending_human`。
9. 异常、限制、运行状态真实。
10. 所有合同字段落盘；所有缺失显式列为缺口，不伪装为已完成。

---

## 4. 判定规则与证据规范

### 四级判定定义

- `supported`：原文明确陈述或者直接蕴含该子判断，且比较、否定、显著性、条件一致。
- `partially_supported`：原文支持部分内容，但缺少必要条件、存在范围限制、跨句拼凑而不完全等价、或证据强度弱。
- `contradicted`：原文明确给出相反表述或相反数据。
- `insufficient_evidence`：原文未报告、无法定位、图注缺失、扫描件无文本层、或只能主题相关但不能形成严格支持。

### 重要原则

- **主题相关不等于支持。** 关键词重叠不能判 `supported`。
- **未报告的扩展推断不是实验否定。** 原文没有做某种比较，不要判为 `contradicted`，只能 `insufficient_evidence`。
- **冲突来源必须并列。** `conflict.both_sides[]` 两条，各有 locator 与 quote。
- **跨页/跨段证据**：给两条 quote，逐条保留原始措辞与数值。
- **图表读数**：无图注或无法读取像素时，不猜，判 `insufficient_evidence`，写 `pending_human` 建议人工读图。

### 证据字段规范

每条证据包含：

- `source_id`
- `locator`：`json_pointer` 或 `unit_id + section + page + block`
- `quote`
- `supports`：true/false
- `role`：`minimal_sufficient / counter / context`
- `reason`

---

## 5. result.json 契约

`result.json` 必须包含：

```json
{
  "case_id": "输入 case_id 或 UNKNOWN",
  "status": "success|partial|insufficient_evidence|input_error",
  "output_contract": {},
  "verifications": [],
  "claims": [],
  "coverage": {},
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": []
}
```

要求：

- `output_contract` 中所有原始字段，必须**原样嵌套**在 `output_contract` 内；
- 同时也要在 `result.json` 顶层出现一次；缺失值用 `null/[]/{}` 补齐；
- 未知字段保留；
- 未产出字段在 `degradations` 记 `contract_field_filled_empty`；
- `result.verifications[]` 是输入论断判定；
- `claims[]` 是本次运行结论清单，`claim_id` 前缀 `V-`，包含 `kind`、`evidence[]`、`source_id`、`location`、`conditions`、`readability: directly_read|inferred|undetermined`。

---

## 6. 文件交付单

| 文件 | 作用 | 关键要求 |
|---|---|---|
| `result.json` | 主结构化结果 | 顶层与嵌套双回显；四级判定；来源、不确定、人工项、错误、降级 |
| `evidence_cards.jsonl` | 一卡一子判断机器可读底稿 | 每条含 `claim_id`、`sub_claim_id`、`evidence`、`verdict`、`rationale`、`locator` |
| `verification_report.md` | 人读核验摘要 | claim → 子判断 → 判定 → 原文 quote → 可复核定位 |
| `/app/work/draft.json` | Agent 覆盖稿 | Agent 修正判定、quote、locator、理由 |
| `/app/work/agent_review.json` | Agent 核验记录 | 逐条 `verified/rejected/reason`、`script_fixes` |
| 题面要求的可编辑产物 | 可编辑格式 + PDF/PNG 预览 | 不得只给扩展名假文件 |

---

## 7. 隐藏案例鲁棒性

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 坏 JSON / 缺失 | 记 `errors`，继续用目录其他材料；`case_id` 未知写 `UNKNOWN` | `partial` |
| `claims-to-verify.json` 缺失但 `case.json` 有 claims | 用 `case.json` 内 claims | 正常 |
| 无 claims 可读 | 不造论断，`verifications=[]`，写清原因 | `input_error` |
| 材料缺失 / 损坏 / 格式不支持 | 登记 `degradations` + `gaps`，只使用可用材料 | `partial` |
| PDF 无文本层 / 扫描件 / CID 乱码 | 不臆造原文；相关 claim 判 `insufficient_evidence`；建议 OCR | `insufficient_evidence` |
| 图注缺失且不能读图 | 判 `insufficient_evidence`，不猜像素 | `partial` |
| 证据冲突 | 双方并列，保留性判定 | 正常 |
| 单个 claim 异常 | 记 `errors`，该条判 `insufficient_evidence`，其余继续 | `partial` |
| 超时 / 请求不足 | 剩余标 `not_processed_budget`，保留已核验部分 | `partial` |
| 需要 Office/幻灯片/图形但无法渲染 | 保留可编辑文件，写 `degradations`，提供文本/HTML 预览 | `partial` |

---

## 8. 预算策略：64 次请求 / 900 秒

必须按权重分配：

1. **先跑脚本基座**：1 次调用产生全套基线；确认 `/app/output/result.json` 已落盘所有 contract 字段。
2. **读输入与合同**：3–6 次请求。
3. **核验高权重证据**：所有 `supported` / `contradicted` 卡逐字核验，约 10–20 次；`insufficient_evidence` 只抽 margin 接近的。
4. **回填 result.json**：4–8 次。
5. **每完成一轮立即覆盖保存**，不要最后才写盘。
6. 超时/请求不足：保留已核验部分，剩余标 `not_processed_budget`；永远返回合法 JSON 和退出码 0。

---

## 9. 与基础 Agent 的增益证据

不能自造评分。但必须在产物中留下可验证的增益证据：

- `search_scope`：记录每条 claim 扫描了多少段落/句子。
- `counter_evidence_searched`：列入每个子判断，表示已主动找反面证据。
- `reviewed_by_agent`：Agent 真正核验过的项标记为 true。
- `change_record`：写明哪些基线误支持被修正到 `partially_supported` / `insufficient_evidence`。
- `method_notes`：记录判定口径，确保重复运行可复现。
- 不引用包内不存在的 `golden_standard`、`diff_report`、自评分数。

---

## 10. Rubric 映射与自检

| Rubric 维度 | 交付动作 |
|---|---|
| 任务完成度 | 每个 claim 有 verdict；每个子判断有独立判定；`claims_requested == claims_verified` |
| 结果正确性 | quote 可逐字检索；四级判定符合 `references/verdict-rubric.md`；误支持被锚点门控挡住 |
| 结果完整性 | 覆盖事实/比较/因果/范围；正反证据；冲突双方；限制条件 |
| 结果可核验性 | 五段链完整：论断→证据片段→原文定位→支持度→理由 |
| 质量增益 | 四级判定表 + 锚点门控 + 主动找反面证据 |
| 效率增益 | 脚本基座 + 固定五步 + `search_scope` |
| 增益可验证性 | 无随机、离线、可复跑；`method_notes` |
| 新增能力 | 段落级定位、四级支持度、冲突并列、不确定性表达 |
| 方法改进 | 拆解粒度、证据检索、判定规则与 `references/` 一致 |
| 创新证据 | `reviewed_by_agent`、`change_record`、误支持修正记录 |
| 可靠性 | 异常表全处置；退出码 0；合法 partial |
| 生态贡献 | 使用 `references/io-contract.md`、`references/decomposition-and-cards.md`、`references/verdict-rubric.md`；示例输入/输出 |

提交前逐项核对 Section 4 和 Section 5 的完整链。

---

## 11. 最小调用示例（示例，非正式案例）

```bash
python3 -B scripts/verify_claims.py --input /input --output /app/output
```

示例输入：`case.json` 含 `case_id` 与 `output_contract`；`claims-to-verify.json` 一条论断“AA5052 在 300°C 退火后的疲劳寿命高于 200°C 退火试样。”；材料含 4 段正文。

示意输出：该论断判 `contradicted`，证据为结果段原句“在 300°C 条件下退火 4 h 后……疲劳寿命下降至 0.74×10^5 循环……”，`role=counter`，`locator={unit_id:P3, section:Results, page:5}`。

完整字段解释见 `references/io-contract.md`。