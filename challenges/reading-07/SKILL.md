---
name: literature-evidence-verification
description: Verify whether a statement about a paper, report or dataset is actually supported by the source text, not merely on-topic. Splits compound claims into atomic fact/comparison/causal/scope sub-claims, locates verbatim evidence with paragraph and page locators, and assigns one of four support levels (supported, partially_supported, contradicted, insufficient_evidence) with reasons, conflict pairing and explicit uncertainty. Use when the user asks 核验这句话 / 证据溯源 / 这句话有依据吗 / fact-check this claim / check whether a citation supports a sentence / audit a claim list against a PDF.
version: 1.0.0
---

# 文献证据溯源与事实核验（literature-evidence-verification）

## 1. 用途与边界

把**待核验论断当作待证问题**（不是既定事实），拆成可独立核验的子判断，回到原文段落取逐字证据，
给出四级支持度、判定理由、冲突双方定位与不确定性，产出可直接复核的证据卡片。

适用：单篇或少量文献的论断核验、引用支持度检查、摘要与正文一致性核对、论断清单批量核验。
边界（如实写进 `limitations`/`uncertainties`，不要假装能做到）：

- 定位粒度是**句子 / 两句窗口 / 段落单元**，不是像素级图表读数；图注缺失时图表结论只能判 `insufficient_evidence`。
- 不做跨文献元分析、不算统计量、不推断原文没做的实验。
- 扫描件或 CID 编码 PDF 无文本层时，不臆造原文，只登记缺口并建议 OCR / 人工读页。

不属于本课题的请求（写论文、翻译、绘图、跑数值实验）应直接说明不适用，不要硬套本 Skill。

## 2. 运行契约

- 入口 `scripts/verify_claims.py`；同目录库 `scripts/lit_core.py`（`Path(__file__).resolve().parent` 定位，不依赖 CWD）。
- 输入 `/input/case.json`、`/input/claims-to-verify.json` 与 `/input/` 下材料；输出 `/app/output/`。
- 仅 Python 标准库，无网络；**先写 partial `result.json` 再 finalize 覆盖**；任何异常都捕获；**退出码恒 0**。
- 软时间预算 `--max-seconds`（默认 780）；超时剩余 claim 标 `not_processed_budget`。

## 3. 输入发现（语义识别，不假设键名）

1. `claims-to-verify.json` → `claims_to_verify.json` → `claims.json`；再查 `case.json` 的
   `claims|claims_to_verify|statements|claims_to_check|claim_list|audit_claims`（含 `input.*`）。
2. claim 字段别名：`claim_id|cid|id|claim_no`、`claim_text|text|statement|claim|sentence|quote`。
   纯字符串列表自造 `C1..Cn`，原名回填 `claims[].input_claim_id`。
3. 材料：递归扫 `/input/**`，按扩展名与内容识别 JSON / CSV / TXT / MD / DOCX / PDF / HTML；
   图表只登记 `gaps`，不猜像素或图注。
4. **claims 文本一律当问题**：不得把它当结论照抄进 `claims[].text` 之外的事实位。

## 4. 输出契约

| 文件 | 作用 |
|---|---|
| `result.json` | 主产物：契约字段 + `result.verifications[]` + `claims[]` + `coverage` + `uncertainties` + 运行状态 |
| `evidence_cards.jsonl` | 一卡一子判断（grep/标注底稿） |
| `verification_report.md` | 人读摘要（claim → 子判断 → 判定 → 原句） |

`output_contract` 的每个键都原样出现在 `result.json` 顶层（缺值 `null/[]/{}`，键名不改，未知字段保留），
未产出的键在 `degradations` 记 `contract_field_filled_empty`。字段细节见 `references/io-contract.md`。

**命名分工**：`result.verifications[]` 是输入论断的判定；`claims[]` 是本次运行的结论清单
（`claim_id` 前缀 `V-`，含 `kind`、`evidence[]`、`source_id`、`location`、`conditions`、
`readability: directly_read|inferred|undetermined`）。两者不混用。

## 5. 核心流程（五步，固定顺序）

1. **建语料**：把材料切成带 locator 的段落单元；记录 `sources[]`（路径、格式、单元数、提取方式）。
2. **拆论断**：按 `references/decomposition-and-cards.md` 拆成 1–7 个子判断，标 `type`
   （fact / comparison / causal / scope）与 `required_evidence_type`；抽取 comparator / negation /
   significance / conditions / 数值与型号锚点（`200°C`、`6061`、`35%`）。
3. **检索与门控**：内容词覆盖度打分取前 6 个句子窗口；**锚点门控**——论断含数值/型号而窗口一个都不命中，
   按同主题不同条件处理（折减 0.35），不得作为支持证据。
4. **先反证再定级**：方向相反或否定极性相反且对象/条件对齐 → `contradicted`；不同 source/section
   方向相反且锚点一致 → `partially_supported` + `conflict.both_sides` 双方并列；要素未对齐 → 封顶
   `partially_supported`；只有主题相关 → `insufficient_evidence`。
5. **落盘与计数**：写 cards、report、`coverage` 四类计数与 `uncertainties`，最后 finalize。

判定口径以 `references/verdict-rubric.md` 为唯一依据；脚本与文档不一致时以文档为准并修正脚本。

## 6. 评分要点 → 实现位置

| 评分点 | 本 Skill 的落点 |
|---|---|
| 任务完成度 | 每条 claim 必有 `verdict`（含 `insufficient_evidence`）；拆出的每个子判断有独立判定；`claims_requested == claims_verified` |
| 结果正确性 | 锚点门控 + 反证优先 + 要素对齐；`supported` 需覆盖度 ≥ 0.72 且无 `limitations`；误支持（主题相关当支持）被硬性挡住 |
| 结果完整性 | 每子判断带最小充分证据 + `counter_evidence_searched:true` + `search_scope`；冲突带双方 quote/locator |
| 结果可核验 | `claim → sub_claim → quote → locator → verdict + rationale` 五段齐全；quote 经 `verify_quote` 逐字校验 |
| 质量增益 | 四级定义表 + 判定决策树（references）+ 同输入可复跑；误支持/漏检可逐张卡片核对 |
| 效率增益 | 固定五步流程替代全文重读；`search_scope` 记录扫描段落数，便于对照人工耗时 |
| 增益可验证 | `method_notes` 写判定口径与反误支持规则，同输入同文献重复运行结果一致（无随机） |
| 创新 | 复合论断拆分、段落级定位、四级支持度、冲突并列、不确定性显式化 |
| 可靠体验 | 触发条件与越界拒绝（第 1 节）；六类异常分支（第 9 节）；单条失败不影响全局 |
| 生态贡献 | 本文档 + 四级规范 + 拆解/卡片/仲裁规范 + 最小示例 + 维护说明 |

## 7. 证据与定位规范

- 每条证据含 `source_id`、`locator`（`json_pointer` 或 `unit_id` + `section` + `page` 或 `block`）、
  逐字 `quote`、`supports`（true/false）、`role`（`minimal_sufficient` / `counter`）。
- quote 保持原文措辞与数值，**不得截断掉比较对象、否定词、数值或显著性表述**；跨段证据给两条 quote。
- quote 在原文找不到 → 弃用该证据并写 `pending_human`；**不改原文凑通过**。
- PDF 页序与提取方式写入 `sources[]`；提取质量差（CID/乱码）记 `degradations` 并要求人工复核。

## 8. 冲突与人工确认

- 冲突必须**双方并列**：`conflict.both_sides[]` 两条，各有 locator 与 quote，`qualified_verdict` 给保留判定
  （通常 `partially_supported`，`verdict_confidence=low`），并说明条件差异；禁止折中、禁止只报一方。
- 进 `pending_human` 的情形：原文缺失/不可读、图注缺失、quote 无法定位、论断拆不开、冲突无法裁决、
  contract 字段无法产出。每条写清"缺什么 + 人工下一步"。

## 9. 异常降级分支

| 情况 | 处置 | status |
|---|---|---|
| `case.json` 坏 JSON | 记 `errors`，继续用目录其它材料 | `partial` |
| 无 claims | 不造论断，提示补齐清单 | `input_error` |
| 原文缺失 / PDF 无文本层 | 登记 `degradations`+`gaps`，全部判 `insufficient_evidence` | `insufficient_evidence` |
| 单 claim 异常 | 记 `errors`，该条判 `insufficient_evidence`，其余继续 | `partial` |
| 证据冲突 | 双方并列 + 保留判定 | 正常 |
| 超时 | 剩余标 `not_processed_budget` | `partial` |

## 10. 最小调用示例（**示例数据，非正式案例结果**）

```bash
python3 -B scripts/verify_claims.py --input /input --output /app/output
python3 -B scripts/verify_claims.py --help
```

输入（示例）：`case.json` 含 `case_id`/`output_contract`；`claims-to-verify.json` 一条论断
"AA5052 在 300 °C 退火后的疲劳寿命高于 200 °C 退火试样。"；`paper.json` 含 4 段正文。
示意输出（示例）：该论断判 `contradicted`，证据为结果段原句"在 300 °C 条件下退火 4 h 后…疲劳寿命下降至
0.74×10^5 循环…"，`role=counter`，`locator={unit_id:P3, section:Results, page:5}`。
完整示例与字段解释见 `references/io-contract.md` 第 3 节。

## 11. 自检清单

- [ ] `result.json` 合法，`case_id` 与输入一致，`output_contract` 键齐全。
- [ ] 每条 claim 有 `verdict`，取值只在四级集合内。
- [ ] 每个子判断有 `evidence` 或（`insufficient_evidence` 且 `search_scope` 非空）。
- [ ] 证据 quote 能在 `sources[].path` 对应文件中逐字检索到。
- [ ] 含比较/否定/显著的 claim，`comparator/negation/significance` 非空且与原文一致。
- [ ] 冲突卡两侧都有 locator + quote，判定带保留。
- [ ] `coverage` 计数自洽；未报告项在 `uncertainties`，需人工项在 `pending_human`。
- [ ] 空输入 / 坏 JSON 仍产出合法 partial，退出码 0。

## 12. 文件清单与版本

```
SKILL.md                                 本文档（使用说明与流程）
scripts/verify_claims.py                 主流程：拆解、检索、判定、产物落盘
scripts/lit_core.py                      输入发现、语料构建、quote 校验、卡片刻画
references/verdict-rubric.md             四级判定规范、决策顺序、limitations 标签
references/decomposition-and-cards.md    拆解规则、证据卡 schema、双人标注与仲裁
references/io-contract.md                输入发现、输出字段、异常分支、最小示例
```

版本 `1.0.0`；依赖 Python ≥3.8 标准库；可选 `pdftotext`/`pypdf` 提升 PDF 抽取质量（缺失时自动降级）。

## 13. 维护说明

- 改动判定阈值（`SUPPORT_C=0.72`、`PARTIAL_C=0.40`、锚点折减 0.35）必须同步
  `references/verdict-rubric.md`，并在提交说明里写清改前/改后对照案例。
- 新增材料格式时只改 `lit_core.load_corpus`，产物 schema 不变。
- 复跑一致性：无随机、无外部依赖；同一输入两次运行应完全一致，用于证明"增益可验证"。
