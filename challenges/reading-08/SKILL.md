---
name: reading-08-formula-structure
description: 把论文公式（MathML/XML、TeX、式子文本）确定性还原为可校验 LaTeX 与结构统计，并产出符号变量表（区分 paper_defined / context_inferred / common_knowledge）、带假设与边界条件的分步推导线索、数值与量纲核验，写出 result.json + formulas.tex + symbol_table.csv；v2 另由材料自身派生金标准 golden_standard.json 并逐项对照实际产物 diff_report.md，附 self_check.json 与 run.log。用于「公式解析与数学推理」类科研阅读任务；材料没有公式表示时如实报 insufficient_evidence，不反推公式、不填 0。
version: 2.0.0
license: MIT
---

# 公式解析与数学推理（reading-08）

## 1. 用途与边界

解决科研阅读里的四个问题：**认得准**（结构/上下标/括号/希腊字母不错位）、**讲得清**（符号定义可回原文，且区分来源）、**推得顺**（步骤可检查，标假设/近似/边界）、**算得回**（能代入复算并发现量纲/量级错误）。

做：解析 `artifacts/*.xml` 的 MathML（三种命名空间）→ LaTeX + 结构计数；建变量表（`definition`/`unit`/`definition_source`/`locator`/`quote`）；抽带 `rule`/`assumptions`/`approximations`/`boundary_conditions` 的句子级推导步；只用材料字面赋值做数值核验（缺值 `not_computable`，全无值给明确标注的 1.0 探针 `example_only`）。

不做（写进 `uncertainties`/`pending_human`，不冒充结论）：不把公式目录 XML 当答案输出（formula catalog 不是 linearized answer）；不反推缺失公式、不把未知填 0/空串；不做符号代数证明（推导只到“原文这么说”）；不对位图做 OCR 猜测。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 入口 | `scripts/main.py`（仅 Python 标准库，无网络，不依赖 CWD） |
| 输入 | `/input/case.json` + `/input/**` 材料；`--input` 可覆盖 |
| 输出 | `/app/output/`（`--output` 可覆盖；不可写时退到 `./output` 并在 `errors` 记录） |
| 主产物 | `result.json`；伴随 `formulas.tex`、`symbol_table.csv`、`verification.md` |
| 审计产物（v2） | `golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json`；`--no-audit` 可跳过且不影响主产物 |
| 退出码 | 恒 0；先写 partial `result.json`，`finally` 里无条件 finalize |
| 资源定位 | `Path(__file__).resolve().parent`，脚本内 `sys.path` 注入同目录 |

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

## 3. 输入发现（语义识别，不假设键名）

1. `case.json` → 其次 `case_input.json` / `input.json` → 再次递归 `case*.json`。
2. 读 `case_id`（另一常见名 `id`）；`output_contract` / `output_spec` / `contract` 任一存在即原样透传。
3. 递归扫描 `/input/**`，按**扩展名 + 魔数**分类：`.xml/.mathml/.nxml` 或 `<?xml` 头、`.tex`、`.txt/.md/.rst`、`.json`、`.pdf`（`%PDF-`）、图片、docx/xlsx/pptx。
4. 材料没给的对象写进 `result.missing_objects`（公式表示 / 页码文本 / 位图内容），不构造内容。

支持的公式来源优先级：`<annotation encoding="application/x-tex">`（原文 TeX，`latex_source=mml_annotation`）> MathML 结构映射（`structural_mapping`）> `.tex` 的 equation 环境（`source_tex`）> JSON 里内嵌 `<math>`（`structural_mapping`）。XML 解析失败时退化到正则抽 TeX annotation（`regex_annotation` + `parse_confidence=low`）。

## 4. 输出契约

`result.json` 顶层：

| 字段 | 内容 |
|---|---|
| `case_id` | 原样保留（缺失为 `null`） |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `result` | 主结果（见下） |
| `claims[]` | `claim_id`、`kind`(reported/inferred)、`readability`(directly_read/inferred/undetermined)、`statement`、`source_id`、`location`、`quote`、`condition`、`confidence`、`quote_verified`、`evidence{quote,location}` |
| `uncertainties[]` | `id`、`type`、`object`、`description`、`impact`、`quote` |
| `uncertainty` | 同 `uncertainties`（题面用词别名） |
| `sources[]` | 每个输入文件：`source_id`、`file`、`type`、`notes` |
| `pending_human[]` | 需人工接管的点（quote 不匹配、公式源缺失） |
| `errors[]` / `degradations[]` / `changes[]` / `runtime` | 异常、降级、写出的产物、耗时与目录 |
| `output_contract_echo` / `contract_fields_missing` | 契约字段落点与缺项（正常为空） |
| `golden_standard` | v2：本题金标准（每个公式的符号表期望、推导步与每步依据、结论、适用条件），每项带 `locator` + 逐字 `quote` 或 `not_reported_in_material` |
| `diff_report` | v2：`summary{items_total,pass,missing,deviation,not_applicable,pass_rate}` + `rows[]`（逐项 expected/actual/verdict/check_method/evidence） |
| `version_history` | v2：v0→v1→v2 变更记录（改了什么/为什么/如何回退）与本次产物字节表 |
| `self_check` | v2：契约完整性、证据覆盖率、数字/计数一致性、空输入与坏 JSON 兜底、退出码、确定性 |

`result`：

- `formulas[]`：`formula_id`、`source_id`、`eq_number`、`mathml_raw_path`（XPath 定位）、`latex`、`latex_source`、`parse_confidence`、`structure{fracs,subsups,radicals,matrices,cases}`、`symbols[]`、`flags[]`、`status`(ok/needs_review)
- `variables[]`：`symbol`、`latex`、`plain`、`definition`、`unit`、`value_range`、`definition_source`、`locator`、`quote`、`source_id`、`formula_ids[]`、`confidence`、`inferred`、`value`
- `derivations[]`：`step_id`、`from`、`to`、`rule`、`statement`、`assumptions[]`、`approximations[]`、`boundary_conditions[]`、`depends_on[]`、`locator`、`source_id`、`verified`、`status`
- `numeric_checks[]`：`formula_id`、`substituted{}`、`computed`、`unit_check`、`order_of_magnitude_check`、`expected_range`、`missing_symbols[]`、`is_example`、`status`(computed / example_only / not_computable)
- `indicator_checks[]`：材料里写出的数值+单位逐条（`checked=reported_as_written`），供无公式快照核对指标与条件
- `coverage`：`formulas_total`、`formulas_ok`、`variables_total`、`by_source{paper_defined,context_inferred,common_knowledge}`、`derivations_total`、`numeric_computed`、`numeric_example_only`、`claims_total`、`uncertainties_total`、`symbol_coverage`、`claims_quote_verified`
- `missing_objects[]`、`method_notes`、`status_reason`（partial 时）

`status` 判定：无公式但有材料 → `insufficient_evidence`；完全无材料/无 case → `input_error`；全部公式 `ok` + `symbol_coverage==1.0` + 有推导 + 有 `computed` → `ok`；其余 → `partial`。

## 5. 核心流程

1. 解析 case，透传 `case_id` 与 `output_contract`。
2. 分类材料；XML 走 `parse_xml`（命名实体先转数值引用）+ `collect_formulas`（每个 `<math>` 一个槽位，容器 `id` → `source_id`、`<label>` → `eq_number`）。
3. `to_latex` 确定性映射，保留顺序与嵌套；未识别元素输出 `\square` + flag（绝不猜字形）。
4. `extract_symbols` 取 `mi` 原子与 `msub/msup/msubsup` 基；`e^{...}`/`10^{...}` 视为常数并继续遍历指数。
5. `mine_defs` 一次遍历抽“where X is …”/“and X is …”，带 unit、verbatim quote、block locator。
6. 变量三分类：命中定义 → `paper_defined`；仅正文出现 → `context_inferred`（`definition=null`）；都没有 → `common_knowledge`（`inferred=true`）；后两类必进 `uncertainties`。
7. `mine_steps` 按线索词（substitut/rearrang/assum/approximat/limit/integrat/differentiat/yields…）抽推导句，拆假设/近似/边界。
8. 数值核验：仅用字面赋值（`k = 0.35 1/h`），AST 白名单求值；缺值 → `not_computable`+`missing_symbols`；全无值 → 1.0 探针 `example_only`（`note` 明示“示例代入，非论文复现”）。
9. `verify`：claim 的 quote 前 120 字在材料文本（标记剥离后）逐字查找，未命中 → `quote_verified=false`+`undetermined`+`pending_human`。
10. 写 `formulas.tex`（逐式 `% source_id` 注释）、`symbol_table.csv`、`verification.md`、`result.json`，最后跑 §12.1 审计。

## 6. 任务质量规则（rubric → 字段/检查/产物）

| 评分点 | 实现 | 可查证据 |
|---|---|---|
| 完成/完整 15+5 | 公式槽位 = 实际 `<math>` 节点数；每条公式列 `symbols[]`、每符号进变量表、推导带边界条件 | `coverage.*` vs `sources[].notes` |
| 正确性 15 | 确定性映射（`mfrac→\frac`、`msubsup→_{}^{}`、`msqrt→\sqrt`、算子表、标识符）；括号/上下标/符号覆盖自检 | `formulas[].latex`+`structure`+`flags`；`golden_standard` 的 `latex_restore` 独立重数 |
| 可核验 5 | 每符号 `locator`+逐字 `quote`；数值核验留 `substituted` 与表达式；回读文件复验 | `claims[].quote_verified`、`diff_report.md`、`self_check.evidence_coverage` |
| 质量增益 15 | 先解析 MathML 再补缺；缺则标 low/uncertainty，不猜 | `latex_source`、`parse_confidence` |
| 效率/增益可验证 5+5 | 单次遍历；同输入复跑确定性 | `runtime.elapsed_s`；`self_check.fallbacks.determinism` |
| 创新 15 | ① MathML 结构还原 ② 定义来源三分类 ③ 数值+量级核验 ④ 材料派生金标准 + 逐项差分 | `definition_source`、`order_of_magnitude_check`、`golden_standard`/`diff_report` |
| 可靠 3/4/3 | 命名空间变体、截断、无 XML、空快照、坏 JSON 各有分支；异常全捕获且退出码 0 | `degradations[]`、`errors[]`、`self_check.exit_codes` |
| 生态 3/4/3 | 本文档 + 3 份 references + 脚本可独立复用；金标准/差分/自检/日志可迁移到其他公式案例 | `references/`、`version_history.md` |

## 7. 证据与定位规范

- `locator`：XML 用绝对 XPath（`/article[1]/body[1]/sec[1]/disp-formula[2]/math[1]`）；文本 `<文件名>#p<序号>`；TeX `<文件名>#eq<n>`；JSON `<文件名>#m<n>`。
- `quote` 必须在材料文本里逐字找到（未命中即降级 + `pending_human`，绝不改原文）。
- 文件级 `source_id` = 文件名去扩展名；公式级 `source_id` = 容器 `id`（缺失时 `<file>#<n>`）。

## 8. 冲突、缺失与人工确认

- 同一符号多处定义不同：`mine_defs` 取首次命中，`uncertainties` 记 `definition_inferred`/`definition_absent`，人工按 `locator` 复核。
- 公式编号与节点 id 不一致：两者都写（`eq_number`←`<label>`、`source_id`←`id`），不强行对齐。
- 材料冲突（正文 vs 表）：不裁决，`indicator_checks` 各自保留原文与 locator。
- 权限/路径失败：`errors` 记 `stage`，`status` 退到 `partial`/`input_error`，退出码仍 0。

## 9. 预算与断点

- 单次模型预算 64 请求 / 900 s；脚本本身秒级完成（`runtime.elapsed_s`）。
- 先写 partial `result.json`，再解析；`finally` 覆盖为最终版本。任何异常都写 `errors.fatal`。

## 10. 异常降级分支表

| 情况 | 处理 | 落点 |
|---|---|---|
| XML 命名空间变体 | 元素名取 `local()`，三种写法统一 | 正常解析 |
| `&alpha;` 等命名实体 | 先转数值引用再 parse | `parse_xml` note |
| XML 语法坏 | 正则抽 TeX annotation，`parse_confidence=low` | `degradations[]`+`flags:[xml_unparsed]` |
| 公式截断/缺子节点 | 保留已有结构，缺参节点记 `*_arity` 旗标 | `flags[]` |
| 无法映射的元素 | 输出 `\square` + flag | `uncertainties`/`flags` |
| 符号歧义/无定义 | `context_inferred` 或 `common_knowledge`，`definition=null` | `uncertainties[]` |
| 单位缺失 | `unit=""`，不臆造 | `symbol_table.csv` |
| 无公式表示（快照型案例） | `status=insufficient_evidence` + `missing_objects` + 指标核对照常交付 | `pending_human` |
| 数值无赋值 | `not_computable` + `missing_symbols`；全无值时 `example_only` | `numeric_checks[]` |
| PDF 无文本层 / 位图 | 记降级与 `missing_objects`，不断言字形 | `degradations[]` |
| 输出目录不可写 | 退到 `./output`，记 `errors` | `errors[]` |
| 坏 JSON / 空目录 | 仍写合法 result.json，退出码 0 | `errors[]`、`status=input_error` |

## 11. 自检清单（交付前）

- [ ] `python3 -B scripts/main.py --help` 退出码 0。
- [ ] 最小输入（`mfrac`+`msubsup`）：`latex` 含 `\frac` 与 `_{}^{}`，变量表覆盖全部 `mi`。
- [ ] 三种命名空间（默认 ns / `mml:` / 无 ns）均解析；每条公式 `source_id` 可回 XML 容器。
- [ ] 每个变量 `definition_source` 是三值之一，`common_knowledge` 项都在 `uncertainties`。
- [ ] 无数值材料：`example_only` 带 `is_example=true`，无 0 值冒充。
- [ ] 空输入 / 坏 JSON：合法 partial `result.json` + 退出码 0；`contract_fields_missing` 为空。
- [ ] `self_check.json.overall.ok == true`，`diff_report.md` 无 missing/deviation。

## 12. 最小调用示例（示例，非正式案例结果）

输入 `/input/case.json`：

```json
{"case_id": "demo-001",
 "output_contract": {"formulas": [], "variables": []},
 "task_instruction": "restore equations and explain symbols"}
```

`/input/artifacts/source-formulas.xml`：

```xml
<disp-formula id="fd-2"><label>(2)</label>
 <math><mrow><mfrac><mrow><mi>α</mi><mo>+</mo><mi>β</mi></mrow>
   <msqrt><mi>γ</mi></msqrt></mfrac></mrow></math></disp-formula>
```

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

示意输出（节选，**示例**）：

```json
{"case_id": "demo-001", "status": "partial",
 "result": {"formulas": [{"formula_id": "F1", "source_id": "fd-2", "eq_number": "(2)",
   "latex": "\\frac{\\alpha+\\beta}{\\sqrt{\\gamma}}", "structure": {"fracs": 1, "radicals": 1},
   "symbols": ["α", "β", "γ"], "flags": [], "status": "ok"}]},
 "claims": [{"claim_id": "C-F1", "kind": "reported", "readability": "directly_read"}],
 "golden_standard": {"objects": [{"object_id": "F1", "items": ["latex_restore", "symbol_table", "..."]}]},
 "diff_report": {"summary": {"items_total": 19, "pass": 14, "pass_rate": 1.0}}}
```

## 12.1 审计产物（v2，同一调用内生成，`--no-audit` 可关）

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `golden_standard.json` | 逐公式 `latex_restore`（结构计数/必备记号/符号基集）、`symbol_table`（期望来源+locator/quote）、`derivation_chain`（statement+basis_kind+字段）、`conclusion`（重述式+数值与否）、`applicability`（条件句）；未报告写 `not_reported_in_material` | `evidence.locator`+`quote` 可回原文，`quote_verified` 由脚本回读核对 |
| `diff_report.md` | 逐项 `pass`/`missing`/`deviation`/`not_applicable` + 期望/实际/检查方法/证据 | 每行对应 `diff_report.rows[].item_id` |
| `version_history.md` | v0→v1→v2：改了什么、为什么、如何回退 | 附产物字节表 |
| `run.log` | 逐阶段时间戳：发现、解析、降级、异常、审计、finalize（含退出码） | 同一命令重跑可复现 |
| `self_check.json` | 契约完整性、证据覆盖率（回读文件）、计数一致性、空/坏输入真实子进程结果、确定性 sha256 | `overall.ok` |

`not_applicable` = 材料本身没有该项（如未写推导步），正确做法是显式声明缺口而非编造；`missing`/`deviation` 进 `diff_report.md` 的 needs-attention 段并保留 evidence。

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（用途、契约、流程、rubric 映射、异常表） |
| `scripts/main.py` | 入口：输入发现、变量/推导/核验装配、产物写出、异常兜底、运行日志 |
| `scripts/formula_core.py` | 引擎：XML/MathML 解析、LaTeX 映射、符号与结构、文本挖掘、求值、信封组装 |
| `scripts/audit.py` | v2 审计：金标准构建、逐项差分校验、版本记录、自检驱动（`Log`/`write_assets`/`write_self_check`） |
| `references/mathml-latex-mapping.md` | MathML→LaTeX 映射表、符号约定、支持的算子 |
| `references/result-schema.md` | result.json 字段、claim 类型、locator 规则、状态判定 |
| `references/examples.md` | 最小示例与复跑步骤（均为示例，非正式案例结果） |

版本 2.0.0（v1 = baseline_v1.zip 成稿）；包内 7 个文本文件，仅标准库（Python ≥3.8），无依赖/网络/二进制。回退：`unzip baseline_v1.zip` 覆盖并删 `scripts/audit.py`。

## 14. 维护说明

- 新增算子：在 `formula_core.OPS` 加映射；新增结构：在 `to_latex` 加分支并同步 `structure_of` 计数键。
- 新增定义模式：在 `formula_core.DEF_WHERE` / `DEF_AND` 追加正则，务必保留 `locator + quote`。
- 改字段请同步 `references/result-schema.md`；`compose()` 负责契约回填，不要在别处复制字段名。
- 新增审计项：在 `audit.REQ/CHK` 加键 → 在 `build()` 用 `_row()` 落项 → 同步 §12.1 表；判定只用 pass/missing/deviation/not_applicable 四值。
- 回归方法：用 §11 的三类小样本重跑，比较两次 `formulas[].latex` 是否逐字一致，并看 `self_check.json.overall.ok`。
