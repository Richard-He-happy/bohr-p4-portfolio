# result.json 字段、claim 类型与定位规则

## 1. 顶层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | str/null | 是 | 输入 `case_id` 原样；输入缺失则 null |
| `status` | str | 是 | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `result` | obj | 是 | 主结果（见 §2） |
| `claims` | list | 是 | 关键结论 + 证据（见 §3） |
| `uncertainties` | list | 是 | 未报告/冲突/需复核项（见 §4） |
| `uncertainty` | list | 是 | 与 `uncertainties` 同值（题面用词） |
| `sources` | list | 是 | `{source_id, file, type, notes?, role?}`，每个输入文件一条 |
| `pending_human` | list | 是 | `{item, why, action?}`，人工接管点 |
| `errors` | list | 是 | `{stage, path?, message}` |
| `degradations` | list | 是 | `{item, stage, action, impact}` |
| `changes` | list | 是 | `{item, action, reason}`，本次运行写了什么 |
| `runtime` | obj | 是 | `skill/version/python/elapsed_s/output_dir/input_dir` |
| `output_contract_echo` | obj | 是 | 契约字段 → 落点（`result.<k>` / `semantic_fill` / `contract_default`） |
| `contract_fields_missing` | list | 是 | 恒为空；非空即失败 |
| `golden_standard` | obj | 是 | v2 金标准：`objects[]{object_id,items[]{item_id,kind,expected,evidence}}` + `global_items[]` + `summary` |
| `diff_report` | obj | 是 | v2 差分：`summary` + `rows[]{expected,actual,verdict}` + `markdown` |
| `version_history` | obj | 是 | v2 版本记录：`entries[]{version,label}` + `markdown` |
| `self_check` | obj | 是 | v2 自检：`contract`/`evidence_coverage`/`number_consistency`/`fallbacks`/`exit_codes`/`overall` |

v2 说明：`golden_standard.expected` 只写材料支持的期望（未报告写 `not_reported_in_material`）；`diff_report.rows[].verdict ∈ {pass, missing, deviation, not_applicable}`；`self_check.overall.ok` 见 SKILL.md §12.1。审计缺失时四字段回退为 `{"status":"skipped","reason":...}`，主结果不受影响。

契约字段回填规则：`output_contract`（或 `output_spec`/`contract`）的每个键都必须出现在顶层，**不改名、不丢键**；脚本 `result` 中同名键（`formulas`/`variables`/`derivations`/`numeric_checks`/`indicator_checks`/`coverage`）直接镜像，其余按原类型给空值（list→`[]`，dict→`{}`，其他→`null`）。

## 2. `result`

```text
result
├─ formulas[]        formula_id, source_id, eq_number, mathml_raw_path, latex,
│                    latex_source(mml_annotation|structural_mapping|source_tex|regex_annotation),
│                    parse_confidence(high|medium|low),
│                    structure{fracs,subsups,radicals,matrices,cases},
│                    symbols[](变量), operators[](函数/算子), flags[], status(ok|needs_review)
├─ variables[]       symbol, latex, plain, definition(str|null), unit(str),
│                    value_range(null|str), definition_source, locator, quote,
│                    source_id, formula_ids[], confidence, inferred, value|null
├─ derivations[]     step_id, from, to, rule, statement, assumptions[],
│                    approximations[], boundary_conditions[], depends_on[],
│                    quote, locator, source_id, verified(false), status(textual_only)
├─ numeric_checks[]  formula_id, substituted{}, computed|null, unit_check,
│                    order_of_magnitude_check, expected_range, missing_symbols[],
│                    is_example, note?, status
├─ indicator_checks[]  value, unit, quote, locator, source_id, checked(=reported_as_written)
├─ coverage{}        formulas_total, formulas_ok, variables_total, by_source{},
│                    derivations_total, numeric_computed, numeric_example_only,
│                    claims_total, uncertainties_total, symbol_coverage,
│                    claims_quote_verified
├─ missing_objects[] object, reason, needed
├─ method_notes      str
└─ status_reason{}   仅 partial 时：formulas_needing_review[], symbol_coverage, …
```

`definition_source` 取值与含义：

- `paper_defined`：命中“where X is …”/“and X is …”等显式定义句，`locator` + `quote` 可回原文，`confidence=high`。
- `context_inferred`：符号在正文出现但无定义句，`definition=null`、`quote=""`，必在 `uncertainties`。
- `common_knowledge`：材料内完全未出现，`definition=null`、`inferred=true`，可选 `common_knowledge_hint`，必在 `uncertainties`。

`numeric_checks[].status`：

- `computed`：公式内所有变量都有材料字面赋值，`substituted` 记录代入值，`order_of_magnitude_check` 给 `log10|v|`。
- `example_only`：无任何赋值，用 1.0 探针验证表达式可求值，`is_example=true`，`note` 明示示例。
- `not_computable`：缺值（`missing_symbols`）或表达式不可标量求值。

## 3. `claims[]`

必含字段：`claim_id`、`kind`、`readability`、`statement`、`source_id`、`location`、`quote`、`condition`、`confidence`、`quote_verified`、`evidence{quote,location}`。

`kind`：`reported`（原文直接陈述/原文结构）/ `inferred`（本项目推断或语境归纳）。
`readability`：`directly_read`（原文可直接读出）/ `inferred`（合理推断）/ `undetermined`（quote 未逐字命中，需人工）。
`quote_verified`：`true`（quote 在材料语料中逐字命中）/ `false`（未命中→已降级为 undetermined）/ `null`（该 claim 无可引用文本，如纯结构推断）。

类型：`C-F<n>` 公式还原；`S-<symbol>` 符号定义或“未定义”；`C-D<n>` 推导步骤；`C-N-F<n>` 数值核验结论。

## 4. `uncertainties[]`

`{id, type, object, description, impact, quote}`，`type` 取值：`definition_inferred`、`definition_absent`、`parse_failure`、`synthetic_example`。

规则：无法判断的内容只出现在这里与 `pending_human`，**不得**写进 `formulas[].latex`、`variables[].definition` 或 `numeric_checks[].computed`。

## 5. locator 规范

| 来源 | 形式 | 例 |
|---|---|---|
| XML 节点 | 绝对 XPath（local-name + 位置谓词） | `/article[1]/body[1]/sec[1]/disp-formula[1]/math[1]` |
| 文本段落 | `<文件名>#p<序号>` | `notes.txt#p3` |
| TeX 公式 | `<文件名>#eq<序号>` | `main.tex#eq2` |
| XML 失败回退 | `<文件名>#annotation<n>` | `paper.xml#annotation1` |
| JSON 内嵌公式 | `<文件名>#m<n>` | `formulas.json#m1` |

## 6. 状态判定

| 条件 | status |
|---|---|
| 无 case 且无任何文件 | `input_error` |
| 有材料但 `formulas` 为空 | `insufficient_evidence` |
| 全部公式 `status=ok` 且 `symbol_coverage=1.0` 且有 `derivations` 且有 `numeric_computed>0` | `ok` |
| 其余 | `partial`（`status_reason` 说明缺哪一项） |

`ok` 是严格条件：任一公式带 flag、任一符号只有 common_knowledge、或无数值可算，都会落到 `partial`，这是有意为之。
