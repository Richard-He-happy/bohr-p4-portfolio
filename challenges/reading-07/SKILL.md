---
name: literature-evidence-verification
description: Verify whether a statement about a paper, report or dataset is actually supported by the source text, not merely on-topic. Splits compound claims into atomic fact/comparison/causal/scope sub-claims, locates verbatim evidence with paragraph and page locators, and assigns one of four support levels—supported, partially_supported, contradicted, insufficient_evidence—with reasons, conflict pairing, and explicit uncertainty. Use when the user asks to fact-check a claim, audit a citation, or verify a claim list against a PDF. Emphasizes actual source parsing, honest partial delivery, and agent-authored final outputs.
version: 2.0.0
---

# 文献证据溯源与事实核验（literature-evidence-verification）

## 0. 铁律：脚本只是工具，最终交付物必须由 Agent 亲自读材料、推导、撰写

1. 本 Skill 内的脚本和模板用于构建语料、检索候选证据、执行初判、落盘基线产物。  
   **最终 `result.json`、`evidence_cards.jsonl`、`verification_report.md` 以及题面额外要求的可编辑产物，必须经过你（Harness Agent）亲自读取实际材料、核对关键证据、推导后增强或改写。**
2. 不得把脚本骨架、模板输出、未核验的自动结果直接当成品提交。
3. 先运行脚本产出全套基线交付物，再在其上增量增强；不得删除、清空或遗漏基线与契约字段。  
   所有 Agent 增强过的地方写 `reviewed_by_agent: true`，并记录改了什么、依据哪段原文。
4. 完整性优先于数量：先保证 `output_contract` 全部字段、`result.json` 本身、题面要求的每个文件都存在；再追求额外判定的精细度。
5. 诚实优先：不确定、材料不足、定位失败，写 `pending_human` / `limitations` / `insufficient_evidence`，不得编造数据、引用、分数、页码。

---

## 1. 用途与边界

把待核验论断当作待证问题，拆成可独立核验的子判断，回到原文段落取逐字证据，给出四级支持度、判定理由、冲突双方定位与不确定性，产出可复核的证据卡片或核验报告。

适用：单篇或少量文献的论断核验、引用支持度检查、摘要与正文一致性核对、论断清单批量核验。

边界（如实写进 `limitations` / `uncertainties`）：

- 定位粒度是句子 / 两句窗口 / 段落单元，不是像素级图表读数；图注缺失时图表结论只能判 `insufficient_evidence`。
- 不做跨文献元分析、不算统计量、不推断原文没做的实验。
- 扫描件或 CID 编码 PDF 无文本层时，不臆造原文，只登记缺口并建议 OCR / 人工读页。
- 不属于本课题的请求（写论文、翻译、绘图、跑数值实验）应直接说明不适用，不要硬套本 Skill。

---

## 2. 运行契约与目录

- 输入：`/input/case.json`、`/input/task.md`、`/input/claims-to-verify.json`，以及题面规定的材料。  
  **必须真实解析材料内容**，用平台预装 PDF 文本提取工具（如 `pdf-text-tool` 或 `pdftotext`）或脚本内置提取器读取实际文件内容；不得依据文件名、领域标签或题目背景猜测内容。
- 工作目录：`/app/work`，中间语料、候选证据、草稿写在这里。
- 最终产物：`/app/output`，必须包含：
  - `result.json`：含输入 `case_id` 和原 `output_contract` 的全部字段（键名不改）。
  - `evidence_cards.jsonl`：一卡一子判断的机器可读底稿。
  - `verification_report.md`：人读核验摘要。
  - 若题面要求可编辑 Office / 幻灯片 / 图形产物，则除原格式外，必须在 `/app/output` 额外生成真实渲染的 PDF / PNG 预览。
- 调用脚本：

      python3 -B scripts/verify_claims.py --input /input --output /app/output

  查看参数：

      python3 -B scripts/verify_claims.py --help

- 只有 Python 标准库时不依赖网络；若环境提供 `pdftotext` / `pdf-text-tool` / OCR，优先使用并把工具名写入 `sources[].extraction_method`。
- 异常必须捕获，**退出码恒 0**；先写 partial `result.json`，再 finalize 覆盖。

---

## 3. 输入发现与语义识别

1. 首先读取 `/input/case.json` 的 `case_id`、`output_contract`，并识别 claims 来源。
2. claims 读取顺序：`/input/claims-to-verify.json` → `case.json` 中的 `claims` / `claims_to_verify` / `statements` / `audit_claims` / `input.claims` → 其他明显 claim 列表字段。
3. claim 字段别名：`claim_id | cid | id | claim_no`，文本别名：`claim_text | text | statement | claim | sentence | quote`。纯字符串列表自造 `C1..Cn`，原名回填 `claims[].input_claim_id`。
4. 材料发现：递归扫 `/input/**`，按扩展名与内容识别 JSON / CSV / TXT / MD / DOCX / PDF / HTML。图表只登记 `gaps`，不猜像素或图注。
5. **claims 文本一律当问题**，不得当结论照抄进 `claims[].text` 之外的事实位。

---

## 4. 本题专属执行流程

以下步骤按顺序执行；每一步失败只降级到对应分支，不得中断全局。

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input/claims-to-verify.json`、`/input/**`。
- **动作**：
  1. 读取 `case_id`、`output_contract`、claims 列表、材料清单。
  2. 在 `/app/work/manifest.json` 写清字段名、文件路径、可解析格式。
  3. 缺失 `output_contract` 时，按 `references/io-contract.md` 的默认字段回退。
- **输出**：输入清单、claims 数、contract 键列表、可用材料列表。
- **失败分支**：`case.json` 坏 JSON → 记 `errors`，继续用目录其他材料，最终 `status=partial`；claims 缺失 → 不造论断，`status=input_error`，但仍产出合法 `result.json`。

### 步骤 2：真实解析材料

- **输入**：步骤 1 发现的材料文件。
- **动作**：
  1. 对每个材料调用平台文本提取工具或脚本解析器，陪出实际文本层。
  2. 将每篇材料切成带 locator 的段落单元；记录 `sources[]`（路径、格式、单元数、提取方式、页序）。
  3. 记录 `extraction_quality`：直接文本 / OCR / CID 乱码 / 无文本层。
- **输出**：`/app/work/corpus.jsonl` 或等价语料，每条带 `source_id`、`unit_id`、`section`、`page`、`block`、`text`。
- **失败分支**：
  - PDF 无文本层或扫描件：登记 `degradations` + `gaps`，相关 claims 判 `insufficient_evidence`，并写 `pending_human` 建议 OCR。
  - 材料损坏 / 格式不支持：保留可用材料，缺失材料写 `sources[].status=unavailable`，不臆造。

### 步骤 3：拆解论断并建立证据锚点

- **输入**：claims 文本 + 语料。
- **动作**：
  1. 按 `references/decomposition-and-cards.md` 将每条 claim 拆成 1–7 个子判断，标 `type`：`fact / comparison / causal / scope`。
  2. 标明每个子判断的 `required_evidence_type`。
  3. 抽取 `comparator`、`negation`、`significance`、`conditions`、数值与型号锚点（如 `200°C`、`6061`、`35%`）。
- **输出**：`/app/work/claims_decomposed.json`。
- **失败分支**：拆不开 → 将该 claim 标记 `decomposition: failed`，整条按原始表述核验，并记录 `pending_human: 需要人工拆解`。

### 步骤 4：运行基线脚本产出全套候选

- **输入**：步骤 2 语料 + 步骤 3 拆解结果。
- **动作**：
  1. 运行 `scripts/verify_claims.py --input /input --output /app/output`。
  2. 确保脚本产出 `result.json`、`evidence_cards.jsonl`、`verification_report.md` 三个基线文件。
  3. 检查 `result.json` 顶层是否已包含 `case_id` 与 `output_contract` 全部键；缺失字段用 `null / [] / {}` 补齐，并在 `degradations` 记 `contract_field_filled_empty`。
- **输出**：完整基线交付物，但仍是“候选”，不是最终判定。
- **失败分支**：脚本崩溃 → 读脚本 traceback，若可修复则修复后重跑；不可修复则手工按插件内容生成最低合法 `result.json`，所有 claim 判 `insufficient_evidence`，记录错误。

### 步骤 5：Agent 亲自核验、增强与派生

- **输入**：基线产物 + 语料 + claims 列表。
- **动作**：
  1. 优先核验 rubric 权重最高的交付物：所有 claim 是否有 verdict、关键证据是否真实存在、支持度判定是否站得住。
  2. 抽查至少全部 `supported` / `contradicted` 卡的 quote，与原文逐字比对；若存在误支持，修正为 `partially_supported` 或 `insufficient_evidence`。
  3. 对长难句、跨页证据、冲突卡逐个精读，补齐判定理据。
  4. 若题面要求 Office / 幻灯片 / 图形产物，亲自撰写/制作可编辑文件，并生成真实渲染的 PDF / PNG 预览。
  5. 将 Agent 核验结果写入 `result.json`：哪些维持基线、哪些改写、哪些 `pending_human`、哪些修正为 `conflicts`。
- **输出**：增强后的全套交付物；每条 Agent 改过项有 `reviewed_by_agent: true` 和 `change_record`。
- **失败分支**：单个 claim 证据不足 → 判 `insufficient_evidence`，保留 `search_scope`，继续处理其他 claim；单个 claim 异常不中断全局。

### 步骤 6：自检 rubric 并回填 result.json

- **输入**：增强后的产物 + `references/verdict-rubric.md` + 输入 contract。
- **动作**：
  1. 逐条核对“rubric 维度 → 交付要求 → 自证方式”表。
  2. 核对 `claim → sub_claim → quote → locator → verdict + rationale` 五段链完整。
  3. 检查 `coverage` 计数自洽，`uncertainties` / `pending_human` 与实际一致。
  4. 确认 `status` 真实：`success` / `partial` / `insufficient_evidence` / `input_error`。
  5. 确认所有 `output_contract` 键已回填。
- **输出**：最终 `/app/output/result.json` 等文件。
- **失败分支**：缺字段则先补全；离预算不足时至少保留已落盘的 honest partial，不要为了完美破坏完整性。

---

## 5. 预算策略：64 次模型请求 / 900 秒内如何分配

1. **必须完成的高权重事项，先做**：
   - 读 input、contract、claims：约 3–6 次模型请求。
   - 运行基线脚本，获得全套候选：1 次脚本调用。
   - 核验并修正所有 `supported` / `contradicted` 卡的关键证据：约 10–20 次模型请求。
   - 回填 contract 字段、写 status / limitations / pending_human：约 4–8 次模型请求。
2. **可跳过或压缩的低优先级事项**：
   - 对所有 `insufficient_evidence` 卡逐条人工解释：仅在证据 margin 接近阈值时做。
   - 对每项子判断做额外统计元分析：不做。
   - 冗余重复验证：同一证据只需一次逐字核验，后续引用记录 `evidence_id`。
3. **尽早落盘 partial**：
   - 步骤 4 脚本跑完立即确认 `/app/output/result.json` 已写入所有 contract 键，即使个别字段为空。
   - 步骤 5、6 每完成一轮核验就覆盖保存一次；不要在最后才一次性写盘。
4. **超时 / 请求不足时**：
   - 剩余 claim 标 `not_processed_budget`。
   - 已核验部分保留 `success` 或 `partial`，缺失部分写入 `limitations`。
   - 永远返回退出码 0 和合法 `result.json`。

---

## 6. 隐藏案例鲁棒性与异常降级

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 坏 JSON / 缺失 | 记 `errors`，继续用目录其他材料；`case_id` 未知则写 `UNKNOWN` | `partial` |
| `claims-to-verify.json` 缺失但 `case.json` 有 claims | 用 `case.json` 内 claims | 正常 |
| 无 claims 可读 | 不造论断，`result.verifications=[]`，提示补齐清单 | `input_error` |
| 材料缺失 / 损坏 / 格式不支持 | 登记 `degradations` + `gaps`，仅用可用材料，缺失部分挂 `pending_human` | `partial` |
| PDF 无文本层 / 扫描件 / CID 乱码 | 不臆造原文；相关 claims 判 `insufficient_evidence`；建议 OCR / 人工读页 | `insufficient_evidence` |
| claim 含未提供的图表读数，图注缺失 | 图注结论判 `insufficient_evidence`，不猜像素 | `partial` |
| 证据冲突 | 双方并列 `conflict.both_sides[]`，每条带 locator + quote，给出保留判定 | 正常 |
| 单 claim 异常 | 记 `errors`，该条判 `insufficient_evidence`，其余继续 | `partial` |
| 超时 / 请求不足 | 剩余标 `not_processed_budget`，保留已核验部分 | `partial` |
| 需要可编辑 Office/幻灯片/图形但无法渲染 | 保留可编辑文件；渲染失败写 `degradations` 并尽快用纯文本或 HTML 预览替代 | `partial` |

任何情况下都要产出合法 `result.json`，退出码 0。无法判断原因和可人工接管位置必须写清楚。

---

## 7. 输出契约与完整交付单

| 文件 | 作用 | 关键要求 |
|---|---|---|
| `result.json` | 主产物 | 含 `case_id`；原 `output_contract` 全部字段在顶层；`result.verifications[]` + `claims[]` + `coverage` + `uncertainties` + `pending_human` + 运行状态 |
| `evidence_cards.jsonl` | 一卡一子判断 | 每条含 `claim_id`、`sub_claim_id`、`evidence`、`verdict`、`rationale`、`locator` |
| `verification_report.md` | 人读摘要 | claim → 子判断 → 判定 → 原句 → 可复核定位 |
| 可编辑产物及预览 | 若题面要求 | 可编辑 Office/幻灯片/图形产物 + 真实渲染的 PDF/PNG 预览，不能只给扩展名假文件 |

命名分工：`result.verifications[]` 是输入论断的判定；`claims[]` 是本次运行的结论清单（`claim_id` 前缀 `V-`，含 `kind`、`evidence[]`、`source_id`、`location`、`conditions`、`readability: directly_read|inferred|undetermined`）。两者不混用。

`output_contract` 的每个键都原样出现在 `result.json` 顶层；缺值用 `null/[]/{}` 补齐；未知字段保留。未产出的键在 `degradations` 记 `contract_field_filled_empty`。字段细节见 `references/io-contract.md`。

---

## 8. 证据与定位规范

- 每条证据含 `source_id`、`locator`（`json_pointer` 或 `unit_id` + `section` + `page` 或 `block`）、逐字 `quote`、`supports`（true/false）、`role`（`minimal_sufficient` / `counter`）。
- quote 保持原文措辞与数值，**不得截断掉比较对象、否定词、数值或显著性表述**；跨段证据给两条 quote。
- quote 在原文找不到 → 弃用该证据并写 `pending_human`；**不改原文凑通过**。
- PDF 页序与提取方式写入 `sources[]`；提取质量差（CID/乱码）记 `degradations` 并要求人工复核。

---

## 9. 冲突与人工确认

- 冲突必须**双方并列**：`conflict.both_sides[]` 两条，各有 locator 与 quote，`qualified_verdict` 给保留判定（通常 `partially_supported`，`verdict_confidence=low`），并说明条件差异；禁止折中、禁止只报一方。
- 进 `pending_human` 的情形：原文缺失/不可读、图注缺失、quote 无法定位、论断拆不开、冲突无法裁决、contract 字段无法产出。每条写清“缺什么 + 人工下一步”。

---

## 10. rubric 维度 → 交付要求 → 自证方式对照表

| rubric 维度 | 交付要求 | 自证方式 |
|---|---|---|
| 任务完成度 15 | 每条 claim 必有 `verdict`；拆出的每个子判断有独立判定；`claims_requested == claims_verified` | `result.verifications[]` 长度和 claim 总数一致；`coverage.counts` 自洽 |
| 结果正确性 15 | 证据片段真实存在于所标位置；支持度判定站得住；区分主题相关与真正支持 | quote 可以通过脚本逐字检索到；`verdict` 与 `references/verdict-rubric.md` 规则一致；误支持被锚点门控挡住 |
| 结果完整性 5 | 覆盖事实、比较、因果、范围子判断；正反证据；冲突来源与限制条件 | 每子判断有 `evidence` 或 `insufficient_evidence` 且 `search_scope` 非空；冲突卡 `both_sides` 齐全 |
| 结果可核验性 5 | 论断 → 证据片段 → 原文定位 → 支持度判定 → 判定理由，整条链可复核 | 五段链完整；quote 经 `verify_quote` 校验；locator 可回到 `sources[].path` |
| 质量增益 15 | 降低误支持与漏检 | 四级判定表 + 决策树 + 同输入复跑；误支持被硬性规则阻断；漏检通过 `counter_evidence_searched:true` 记录 |
| 效率增益 5 | 单条论断从人工翻原文到核卡 | `search_scope` 记录扫描段落数；固定五步流程替代全文重读 |
| 增益可验证性 5 | 同输入同文献同工具可复现 | 无随机、无外部网络；两次运行结果一致；`method_notes` 写判定口径 |
| 新增能力 5 | 段落级定位、四级支持度、冲突并列、不确定性表达能力 | `result.verifications[]` 中体现；`conflict.both_sides`；`uncertainties[]` |
| 方法改进 5 | 拆解粒度、证据检索、判定规则 | `references/decomposition-and-cards.md` / `references/verdict-rubric.md` 与实际结果一致 |
| 创新证据 5 | 相对基础 Agent 或现有方案的边界和价值 | 运行记录中的 `reviewed_by_agent` 字段、`change_record`、误支持修正记录 |
| 调用与易用性 3 | “帮我核验这句话”可触发；不属于本课题请求可拒绝 | 第 1 节边界；`errors` / `input_error` 清晰 |
| 运行稳定性 4 | 长论文、跨页证据、扫描件、多语言文献、重复运行可持续产出 | 第 6 节异常分支；`result.status`；重复运行无随机 |
| 异常处理 3 | PDF 无文本层、定位失败、证据冲突、部分匹配 | 所有异常均返回合法 `result.json`，退出码 0 |
| 文档完整性 3 | 使用说明、四级定义、输入输出、配置、示例、限制 | 本文档 + `references/io-contract.md` |
| 资源可复用性 4 | 证据卡片模板、拆解规范、标注规范可复用 | `references/decomposition-and-cards.md` + `references/verdict-rubric.md` |
| 分享推广价值 3 | 沉淀可分享案例、标注经验 | 示例数据；运行报告可复用 |

---

## 11. 自检清单：提交前逐项检查

- [ ] `result.json` 合法 JSON，`case_id` 与输入一致（或诚实标记 `UNKNOWN`）。
- [ ] `output_contract` 每个键都出现在 `result.json` 顶层；缺失键已空值补齐并记录。
- [ ] 每一条输入 claim 都有 `verdict`，且取值只在四级集合内。
- [ ] 每个子判断有 `evidence`，或 `insufficient_evidence` 且 `search_scope` 非空。
- [ ] 每条 quote 能在 `sources[].path` 对应文件中逐字检索到；无伪造原文。
- [ ] 含比较/否定/显著的 claim，`comparator/negation/significance` 非空且与原文一致。
- [ ] 冲突卡两侧都有 locator + quote，判定带保留。
- [ ] `coverage` 计数自洽；未报告项在 `uncertainties`；需人工项在 `pending_human`。
- [ ] 空输入 / 坏 JSON / 超时仍产出合法 partial，退出码 0。
- [ ] 题面若要求可编辑 Office/幻灯片/图形产物，已附真实渲染的 PDF/PNG 预览。
- [ ] Agent 核验过的项带 `reviewed_by_agent: true`，并写明改动依据；基线文件未被破坏。
- [ ] 没有引用包内不存在的文件或脚本；本文档只引用 `scripts/verify_claims.py`、`scripts/lit_core.py` 和 `references/` 下现有文件。

---

## 12. 最小调用示例（示例数据，非正式案例结果）

运行：

    python3 -B scripts/verify_claims.py --input /input --output /app/output

输入（示例）：`case.json` 含 `case_id` / `output_contract`；`claims-to-verify.json` 一条论断“AA5052 在 300 °C 退火后的疲劳寿命高于 200 °C 退火试样。”；`paper.json` 含 4 段正文。

示意输出（示例）：该论断判 `contradicted`，证据为结果段原句“在 300 °C 条件下退火 4 h 后…疲劳寿命下降至 0.74×10^5 循环…”，`role=counter`，`locator={unit_id:P3, section:Results, page:5}`。

完整示例与字段解释见 `references/io-contract.md