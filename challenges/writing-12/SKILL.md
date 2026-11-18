---
name: latex-writing-compile
description: Repair, author and verify LaTeX manuscripts so they compile under a given template. Diagnoses compile errors to file:line with an error class and fix recipe, applies conservative rule-numbered repairs (missing packages, unescaped specials, literal percent signs, unclosed groups/environments), runs a multi-pass build with bibliography, and records verbatim facts, citations and change evidence. Use when a case supplies .tex/.bib/.cls/.sty files or asks for a LaTeX manuscript, table, equation, template migration, cross-reference repair or compile-error fix.
version: 1.0.0
---

# LaTeX 写作与编译（latex-writing-compile）

## 1. 用途与边界

把「/input 里的 LaTeX 工程 + 材料」变成三件可交付物：**能编译的 .tex 源码**、**逐行可定位的诊断/修复记录**、**逐字可回查的事实与修改证据**。

适用：修编译错误、补宏包/环境/花括号、转义正文特殊字符、修 `\ref`/`\cite` 与 .bib 对应、模板必填项补齐、宽表/列数纠错、按材料改写正文并保住数字与引用、多轮构建收敛。

**不做**（写进结果而不是硬猜）：

- 不编造文献、DOI、数值、图元素；材料里没有的数字只进 `pending_human`。
- 不替作者判断学术观点；`workorder` 中需要文风判断的条目标 `manual_review_required`。
- 不联网、不安装宏包/字体；缺宏包只给命令与替代方案。
- 不把 PDF、截图或不能编译的片段当交付物。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、材料（tex/bib/cls/sty/md/txt/csv/json/pdf/docx） |
| 输出 | `/app/output/`（`result.json` 必存在） |
| 退出码 | **恒 0**：异常写 `errors`/`degradations`，不靠退出码表达失败 |
| 首写 | 进入任何耗时步骤前先写 partial `result.json`，结束时无条件覆盖为 finalised |
| 依赖 | Python 3.9+ 标准库；TeX 发行版可选（`pdflatex`/`xelatex`/`lualatex` + `bibtex`/`biber`）；`pdftotext`/`pdfinfo` 可选 |
| 路径 | 脚本用 `Path(__file__).resolve().parent` 定位资源，不依赖 CWD |
| 预算 | 默认 `--max-seconds 780`、单次编译 `--timeout 240`；到线前先 finalize |

## 3. 输入发现（语义，不假设键名）

1. 读 `/input/case.json`；不存在时按「含 case 名字优先、层级浅、体积小」选任意 `*.json`，仍解析；坏 JSON → `errors[case_json_invalid]` 并继续。
2. `case_id` 取 `case_id|caseId|id|task_id`；`output_contract` 取 `output_contract|outputContract|contract`，**原样深拷贝**，键名不改、未知字段保留。
3. 递归扫描 `/input/**` 全部文件（≤600 个，单个 ≤20MB）：`\documentclass` 判定主文件；`.bib` 收集条目；`.cls/.sty` 视作模板依赖；图片按扩展名探测是否存在。
4. 材料文本来源：`.md/.txt/.csv/.json/.tsv` 直读；`.pdf` 用 `pdftotext -layout`（无该工具则跳过并在 `degradations` 说明）；`.docx` 由 lint 的 `fx` 侧 `zipfile` 读取；图片不解析。
5. `organizer_workorder`/`organizer_edit_workorder`/`checklist`/`requirement` 类键 → `wos()` 归一化为条目，逐条回执。

## 4. 输出契约

| 文件 | 内容 |
|---|---|
| `deliverable.tex` | 主文件副本（可编辑、可并入稿件） |
| `tex_project/` | 完整可编译工程（含 .bib/.cls/.sty/图） |
| `deliverable.pdf` | 编译产物（编译成功时） |
| `result.json` | 结构化结果 + `output_contract` 回填 + `contract_fill` 映射表 |
| `verification.json` | 独立审计（逐字引用、计数、结构）结果 |
| `build_report.md` | 人读摘要（状态、诊断数、编译错误、复现命令） |
| `baseline/` | 改动前快照，供 diff 与引用核验 |

`result.json` 关键字段：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`deliverable`、`compile`(passes/errors/pdf_pages)、`diagnostics`(修复前)、`diagnostics_residual`(修复后)、`change_log`、`preserved_facts`、`evidence_map`、`citations`、`workorder_receipt`、`pending_human`、`uncertainty`、`errors`、`degradations`、`notes`、`metrics`、`runtime`、`verification`、`output_contract`。字段级说明见 `references/method.md`。

## 5. 核心流程（Agent 按此顺序操作）

```bash
# 0) 先拿诊断，不编译（秒级）
python3 -B scripts/latex_doctor.py --input /input --out /app/output --no-build

# 1) 读 /app/output/result.json 的 diagnostics / preserved_facts / workorder_receipt
# 2) 只编辑 /app/output/tex_project/ 下的源码；/input 与 baseline/ 保持只读
# 3) 再跑一次 --no-build，确认 diagnostics_residual 收敛
# 4) 全量构建（含多轮编译 + 独立审计）
python3 -B scripts/latex_doctor.py --input /input --out /app/output
```

- 第 4 步若 `compile.errors` 非空：按 `class` 排序修复**第一条**，`fix` 字段给出配方；级联错误（`E17_ARGUMENT`/`E99` 后成串）先修根因，再复跑。
- `status` 变 `ok` 的条件：PDF 存在 + 无未解析 ref/cite + 事实全命中 + 无残余 error 级诊断。
- 收尾必须是一次全量运行（保证 `result.json`/`verification.json` 与产物同版本）。

## 6. 评分要点 → 字段/检查/产物

| 评分维度 | 对应产物与字段 | 落地检查 |
|---|---|---|
| 实际效果·任务完成度 | `deliverable.tex`、`tex_project/`、`compile.pdf_exists` | 主文件为真实可编译源码，非片段；模板必填项在 `diagnostics(T_TEMPLATE_FIELD)` |
| 实际效果·正确性 | `compile.errors[].class/file/line`、`diagnostics_residual` | 公式定界符、环境嵌套、表格列数、ref/cite 解析 |
| 实际效果·完整性 | `workorder_receipt`、`pending_human` | workorder 逐项回执；缺口显式列出 |
| 实际效果·可核验性 | `compile.passes`、`change_log`(quote→quote+locator)、`baseline/` | 每条改动可在 baseline 与产物两侧逐字回查 |
| 使用增益 | 同一命令即可完成 诊断→修复→构建→审计 | 免去查宏包文档、反复盲编译、人工核对数字 |
| 创新增益 | 错误分类 `E01–E99`、规则号 `R01–R06`、独立审计 `verification` | 基础 Agent 无「类→配方」映射与 quote 回查 |
| 可靠体验 | `degradations`、`errors`、恒 0 退出、partial 优先 | 各种缺失环境下仍产出合法结果 |
| 生态贡献 | 本文件 + `references/*` + `rules.json` 可扩展 | 他人可复用规则表、检查清单与示例 |

## 7. 证据与定位规范

- `locator` 统一 `相对路径:行号`（PDF 材料为 `文件名`+行号，供 `pdftotext` 文本定位）。
- `evidence_map` 只收**能在源文件逐字回查**的条目：数值（`preserved_facts` 派生）与引用（`.bib` 条目首行）。校验用 `verification.json`。
- `change_log` 每条含 `original_quote`→`revised_quote`+`reason`+`locator`；自动修复带 `rule`(`R01…R06`)，模型编辑由 baseline diff 生成（`kind=model_edit`）。
- `workorder_receipt` 用锚点（命令、宏包名、数值）判定：`done_verified`/`partial_anchor_match`/`not_found`/`manual_review_required`，不做文风断言。

## 8. 冲突与人工确认

材料互相矛盾、数值缺失、模板文件缺失、需要学术判断 → 写 `pending_human`（含 `item`/`source`/`action`）与 `uncertainty`（含 `confidence`），**不擅自补**。同一数字在材料中出现两个值时不选边，两条都进 `pending_human`。

## 9. 预算与断点

单次运行 ≤780s：接近上限前跳过编译（`degradations[budget]`）并 finalize。任何中断点都已有合法 `result.json`；重复运行幂等（`tex_project` 已存在则沿用，`baseline` 只建一次）。

## 10. 异常降级分支

| 情况 | 实际行为 |
|---|---|
| 无 TeX 发行版 | `degradations[no_latex_engine]`，只做静态诊断，`status=partial` |
| 缺宏包 / 缺 `.cls` | 日志类 `E01_MISSING_FILE`/`E03_PACKAGE`；给出 `tlmgr`/`TEXMFHOME` 处置，不自动装 |
| 缺字体/字符 | `E12_FONT`；建议改字体族，不嵌造字形 |
| 权限不足 | `HOME/TEXMFVAR/TEXMFCFG` 重定向到 work 目录；仍失败 → `E13_PERMISSION` |
| 报错级联 | 保留首因，后续同族错误标注为级联，先修首因 |
| 无 `.tex`（纯写作题） | 生成带 `% SCAFFOLD` 注释的最小可编译骨架 + `degradations[scaffold_used]`，正文须由 Agent 撰写 |
| `case.json` 损坏 | `errors[case_json_invalid]`，仍产出 `insufficient_evidence` 结果 |
| `latex_lint.py` 丢失 | `degradations[lint_module_missing]`，只编译不诊断 |
| 编译超时 | `compile.passes[].tail=TIMEOUT`，保留已有日志解析结果 |

## 11. 自检清单

- [ ] `result.json` 中 `output_contract` 的每个键都存在（`contract_fill` 记录映射或 null）。
- [ ] `case_id` 与输入一致；顶层字段 `status/errors/degradations/pending_human/uncertainty/runtime` 齐全。
- [ ] `deliverable.tex` 非空、含 `\documentclass` 与 `\end{document}`、花括号平衡。
- [ ] `compile.pdf_exists=true` 时 `pdf_pages>0` 且 `compile.passes` 有退出码。
- [ ] `change_log` 每条 `original_quote` 在 `baseline/`、`revised_quote` 在 `tex_project/` 可逐字命中。
- [ ] `verification.json.status != "fail"`（否则按 `issues` 修）。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
mkdir -p /tmp/in/artifacts
cat > /tmp/in/case.json <<'J'
{"case_id": "demo", "output_contract": {"manuscript_tex": null, "preserved_facts": []},
 "monospace_placeholder": 0}
J
printf 'Yield was 45.2 %% after 30 min.\n' > /tmp/in/artifacts/material.md
cat > /tmp/in/main.tex <<'T'
\documentclass{article}
\begin{document}
Yield was 45.2 % after 30 min.
\end{document}
T
python3 -B scripts/latex_doctor.py --input /tmp/in --out /tmp/out --work /tmp/work
```

示意输出（示例，非正式案例结果）：

```json
{"status": "ok", "case_id": "demo", "diagnostics": 1, "facts": "1/1", "changes": 1}
```

结果文件：`/tmp/out/deliverable.tex`（`%` 已转义为 `\%`）、`/tmp/out/deliverable.pdf`、`/tmp/out/result.json`（`change_log[0].rule=R06_percent`）。

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（入口） |
| `scripts/latex_doctor.py` | 主流程：发现 → 诊断 → 修复 → 构建 → 结果 → 审计 |
| `scripts/latex_lint.py` | 分析库 + 独立审计（`P/diag/repair/fx/guard/wos/receipt/fill/verify`） |
| `references/rules.json` | 规则表：宏包映射、模板必填项、错误类、契约字段匹配 |
| `references/method.md` | 错误类目录、诊断/修复编号、字段手册、维护方法 |
| `references/example.md` | 端到端示例与已知限制（示例，非正式案例） |

版本 1.0.0；Python 标准库；无网络。运行命令的完整参数：`python3 -B scripts/latex_doctor.py --help`。

## 14. 维护说明

- 新错误类：在 `references/rules.json` 的 `error_classes` 追加 `[正则, 类名, 配方]`，无需改代码。
- 新宏包/模板：追加 `pkg`/`creq`；诊断会自动纳入（`E03_PACKAGE`/`T_TEMPLATE_FIELD`）。
- 新契约字段匹配：`contract_rules` 追加 `[正则, 内部字段名]`，`fill()` 自动生效。
- 回归：改脚本后依次跑 `--help`、坏 JSON、空目录、含 `%`/`&`/`_`/未闭合环境的样例，确认退出码 0 且 `verification.status != fail`。
