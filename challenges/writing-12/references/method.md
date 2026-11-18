# 方法与字段手册（latex-writing-compile 1.0.0）

本文件说明脚本内部的两套编号、`result.json` 字段含义、审计项与维护方式。规则数据在
`rules.json`（宏包映射 `pkg`、模板必填项 `creq`、契约字段匹配 `contract_rules`、错误类
`error_classes`），本文件解释它们的用法。

## 1. 两阶段诊断

| 字段 | 何时生成 | 用途 |
|---|---|---|
| `diagnostics` | **修复前**（`tex_project` 已从 `/input` 复制、尚未改动） | 记录「原始工程有什么问题」，是改动的依据 |
| `diagnostics_residual` | **修复后**（自动修复 + 模型编辑之后） | 残余问题；`status`、`pending_human` 以此为准 |

同一条问题在两者中同时出现 = 未被修好；只在 `diagnostics` 中出现 = 已修复（并有对应
`change_log` 条目，若为自动修复则带 `rule`）。

## 2. 静态诊断类（`diagnostics[].cls`）

每条含 `cls / sev(error|warning|hazard) / file / line / msg / fix`；`msg` 写现象与根因，
`fix` 给可执行配方。

| 类 | 含义 | 典型根因 | 处置 |
|---|---|---|---|
| `E01_MISSING_FILE` | `\input`/图片目标不存在 | 工程裁剪、路径错 | 补文件或内联内容；不替换为臆造图 |
| `E03_PACKAGE` | 用了宏却不加载宏包 | `\toprule`、`\SI`、`\cref` | 前导区加 `\usepackage{...}`（自动修复 R02） |
| `E04_ENV` | `\begin`/`\end` 不配对或次序错 | 复制粘贴、块被截断 | 补对应 `\end` 或删多余 `\end` |
| `E05_BRACE` | 花括号不平衡 | 宏参数漏闭合 | 按报告行补齐（自动修复 R05 仅补文件末尾未闭合） |
| `E06_MATH` | `$` 计数为奇 / `\left` 与 `\right` 不配对 | 行内公式只写一半 | 补定界符，或统一改用 `\(...\)` |
| `E07_ALIGN_TAB` | 正文中的裸 `&` | 表格内容粘进段落 | 转义 `\&`（自动修复 R04） |
| `E08_TABLE_CELLS` | 行内单元格数与列声明不符 | 漏写/多写 `&`、`\multicolumn` 未计 | 修 `&` 或列声明，禁止用缩放掩盖 |
| `H_WIDE_TABLE` | ≥6 列宽表 | 直接 `tabular` | 改 `tabularx`/`p{}` 或拆行（hazard，非错误） |
| `E09_REF` | `\ref` 指向不存在的 `\label` | label 改名/缺失 | 补 label 或改 key；或再跑一轮编译 |
| `E10_CITE` | `\cite` 键在 `.bib`/`\bibitem` 中不存在 | 键拼错、条目缺失 | 从材料补条目；**不得编造文献信息** |
| `E14_ENCODING` | 中文但没有 CJK 宏包 | pdfLaTeX + 中文 | `\documentclass[UTF8]{ctexart}` + xelatex（自动切换引擎） |
| `E15_CLASS` | 无 `\documentclass` | 交来的是片段 | 套入题目要求的模板类 |
| `E18_MATH_MODE` | 正文里的裸 `_`/`^`/`#` | 变量名、标识符 | 转义（自动修复 R04） |
| `E19_PERCENT` | 数字后的裸 `%` | 「45.2 %」把后半行变注释 | 转义为 `\%`（自动修复 R06）；这是**最隐蔽的丢内容原因** |
| `T_TEMPLATE_FIELD` | 模板必填项缺失 | 未写 `\title`/abstract/keywords | 按模板补字段 |

## 3. 日志类（`compile.errors[].class`）

由 `.log` 解析，带 `file:line`（`-file-line-error`）与 `fix`：

`E01_MISSING_FILE`、`E02_UNDEFINED_MACRO`、`E03_PACKAGE`、`E04_ENV`、`E05_BRACE`、
`E09_REF`、`E10_CITE`、`E12_FONT`、`E13_PERMISSION`、`E14_ENCODING`、`E16_CAPACITY`、
`E17_ARGUMENT`（组未闭合/长度非法）、`E18_MATH_MODE`、`E99_EMERGENCY`、`E99_UNKNOWN`。

处置顺序：**先按 `class` 归类，再修同类第一条**。同一条 `Missing $ inserted` 或
`Paragraph ended before` 反复出现时，真正根因通常在第一处未闭合的 `{`，后序是级联。

## 4. 自动修复规则（`change_log[].rule`）

| 规则 | 动作 | 触发条件 | 风险控制 |
|---|---|---|---|
| `R01_normalize` | BOM/CRLF → UTF-8 LF | 文件含 BOM 或 `\r` | 只改编码不改内容 |
| `R02_package` | 前导区插入 `\usepackage{p}` | 用了 `pkg` 表中宏且未加载 | 去重；插入到最后一条 `\usepackage`/`\documentclass` 之后 |
| `R03_end_document` | 追加 `\end{document}` | 有 `\begin{document}` 无 `\end` | 只在文件末尾追加 |
| `R04_escape` | 正文 `& _ ^ #` 前加 `\` | 掩蔽数学/参数/verbatim/tabular 后仍裸露 | 仅正文；`\label`/`\cite` 参数等被掩蔽 |
| `R05_close_braces` | 文件末尾补 `}` | 括号深度 >0 | 记录首个未闭合行；不猜中间位置 |
| `R06_percent` | 数字/`)` 后的 `%` → `\%` | 该行 `%` 后仍有内容；同一行多处全部处理 | 已转义 `\%` 不重复；注释行不动 |

模型编辑不在上述规则内：脚本用 `baseline/` 与 `tex_project/` 的 `difflib` 差异生成
`kind=model_edit` 条目，`reason` 固定为 `content edit`，`locator` 为改动块起始行。

## 5. 构建流程

1. 复制 `tex_project/` 到 `<work>/latex-build/`（不污染交付目录）。
2. 引擎选择：`.tex` 含 CJK/`ctex`/`fontspec` → `xelatex`，否则 `pdflatex`（可按 `--engine` 覆盖）。
3. 轮次：`engine` →（文档声明 `\bibliography`/`\addbibresource`/`biblatex` 时）`bibtex`/`biber` →
   `engine` → `engine`。每轮记录 `cmd/exit/sec/tail`。
4. 环境：`HOME/TEXMFVAR/TEXMFCONFIG/TEXMFHOME` 指向 build 目录，规避只读主目录与权限问题；
   `SOURCE_DATE_EPOCH=0` 提升可复现性。
5. `.log` 解析 → `compile.errors`（去重，≤30 条）、`compile.warnings`（Overfull 等）。
6. PDF 页数：优先 `/Type /Page` 计数，PDF 使用对象流时回退 `pdfinfo`。

## 6. `result.json` 字段手册

| 字段 | 说明 |
|---|---|
| `case_id` | 原样回填 |
| `status` | `ok`：编译成功且无未解析 ref/cite、事实全命中、无残余 error；`partial`：其余可交付情形；`insufficient_evidence`：素材不足以产出；`input_error`：无输入 |
| `deliverable` | `path/format/editable/bytes/main/pdf/pdf_pages` |
| `compile` | `attempted/engine/passes/log_present/errors/warnings/pdf_exists/pdf_pages/pdf_delivered/build_dir/main` |
| `diagnostics` / `diagnostics_residual` | 见 §1 |
| `preserved_facts` | `token/value/unit/source_id/locator/quote/present/deliverable_locator/status` |
| `evidence_map` | `claim_id/claim/kind(number|citation)/source_id/locator/quote/verified` |
| `change_log` | `id/kind(auto_repair|model_edit)/rule/file/line/original_quote/revised_quote/reason/locator` |
| `workorder_receipt` | `id/requirement/locator/status/anchors_found/anchors_missing` |
| `pending_human` | `item/source/action`（缺失事实、未解析引用、error 级诊断） |
| `uncertainty` | `item/confidence` |
| `errors` / `degradations` | 输入与运行期异常；`degradations` 用 `code` 标识（`no_latex_engine`、`scaffold_used`、`lint_module_missing`、`no_log`、`verify_skipped`） |
| `metrics` | 计数与覆盖率（`facts_preserved`、`fact_coverage`、`compile_errors`、`pdf_pages`） |
| `output_contract` / `contract_fill` | 原字段回填 + 每个键的映射来源 |
| `verification` | 独立审计结果（见 §7） |

## 7. 独立审计（`latex_lint.verify`）

| 检查 | 判定 |
|---|---|
| `contract_keys` | 输入契约的每个键都出现在 `output_contract` |
| 顶层字段 | `case_id/status/errors/degradations/pending_human/uncertainty/runtime` 齐全 |
| `change_log_quotes` | `original_quote` 在 `baseline/`（或输入）、`revised_quote` 在 `tex_project/` 逐字命中（空白归一化比较） |
| `evidence_quotes` | `evidence_map[].quote` 在 `source_id` 指向的文件中逐字命中 |
| `deliverable` | 非空、含 `\documentclass` 与 `\end{document}`、花括号平衡 |
| `pdf` | 声称交付的 PDF 真实存在 |
| `counts` | `metrics` 与列表长度一致 |

审计失败不会掩盖结果：若 `status=ok` 且审计有 fail，脚本把状态降为 `partial` 并写
`degradations[verify_downgrade]`。

## 8. 已知限制

- 只做 **LaTeX 语义近似**：不渲染排版，列宽/浮动体位置仅在编译日志（Overfull）层面提示。
- 不解析图片内容；图片只核对是否存在。
- 自动修复刻意保守：环境嵌错、公式定界符缺失只报告不猜，避免把内容改坏；转义与插包按行就地改写，注释与 `%` 之后的正文一律原样保留。
- `E19_PERCENT` 依据「数字/右括号 + 空白 + %」判定，同一行多处裸 `%` 会全部转义；
  `\vspace{2mm} % 说明` 这类注释不受影响。**连续两个裸 `%`**（如 `12.7 %%`）只转义第一个，
  第二个仍会作为残余 `E19_PERCENT` 报出并进 `pending_human`——这是刻意选择：宁可报告也不擅自改写作者意图。
  形如「Table 2 %」的极端排版可能被误转义，会在 `change_log` 中列出供人工复核。

## 9. 维护

- 扩错误类：`rules.json → error_classes` 追加 `[regex, 类名, 配方]`。
- 扩宏包/模板：`pkg`、`creq`。
- 扩契约映射：`contract_rules` 追加 `[regex, 内部字段名]`，顺序即优先级（先具体后泛化）。
- 回归：`--help` → 坏 JSON → 空目录 → 含 `%`/`&`/`_`/未闭合环境的样例，四步都要求退出码 0
  且 `verification.status != "fail"`。
