---
name: latex-writing-compile
description: 真实解析 /input 中的 LaTeX 工程与科研材料，亲自完成学术写作、编译修复、公式/表格/引用/模板适配、双语或结构化写作等任务，产出可编译 .tex 工程、PDF 预览、逐行诊断/修复记录、逐字来源映射与合规 result.json。脚本只作工具，Agent 必须读材料、推导并撰写/制作最终交付物；任何情况下 result.json 字段完整、退出码 0。
version: 1.1.0
---

# LaTeX 写作与编译（latex-writing-compile）

## 0. 最高准则：完整交付、真实推导、契约优先

本 Skill 的脚本可做诊断、修复、构建、审计，但脚本只是工具。最终交付物必须由你（Harness Agent）亲自读取 `/input` 中的真实材料，逐条理解任务要求，完成事实核对、内容撰写、编辑与自检。不得把脚本骨架、模板修复、示例文件或未经验证的自动产物直接当成品。

**必须做到：**

1. **先跑完整基线，再增量改进。** 进入任务后先运行本 Skill 自带脚本，产出全套基线与所有 output_contract 所需字段。后续只能增强，不得删除、清空或遗漏基线产物。
2. **所有事实、数字、引用、修改记录可回溯。** 不得按文件名、领域标签、标题猜测材料内容。材料里没有的数据不得补造；材料冲突或不足必须写 `pending_human` / `limitations` / `uncertainty`。
3. **任何情况下都产出合法 `result.json`，退出码恒为 0。** 异常写 `errors` / `degradations`，不靠退出码表达失败。
4. **时间与请求预算内优先交付评分权重最高的产物。** 先落盘 honest partial，再增量完善；不要反复盲编译，不要无意义循环。
5. **所有产物最终位于 `/app/output`，工作目录使用 `/app/work`，输入只读。**

---

## 1. 输入与输出契约

| 项 | 约定 |
|---|---|
| 输入目录 | `/input`：`case.json`、`task.md`、材料文件（`.tex`/`.bib`/`.cls`/`.sty`/`.md`/`.txt`/`.csv`/`.json`/`.pdf`/`.docx`/图片等） |
| 工作目录 | `/app/work`：可写中间文件、日志、临时编译目录 |
| 输出目录 | `/app/output`：所有最终产物与 `result.json` |
| 退出码 | 恒 0；失败通过 `result.json` 的 `status` / `errors` / `degradations` 表达 |
| 读取原则 | 输入目录只读；不得覆盖 `/input`；材料内容必须真实解析 |
| 结果文件 | `/app/output/result.json` 必存在，且包含原 `output_contract` 全部字段（键名不改）与 `case_id` |
| 预览要求 | `.tex` 编译产物应给 PDF；可编辑 Office/幻灯片/图形类产物如被契约要求，必须额外给出真实渲染的 PDF/PNG 预览 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 依赖 | Python 3.9+ 标准库；TeX 发行版可选（`pdflatex`/`xelatex`/`lualatex` + `bibtex`/`biber`）；PDF 文本提取可选（`pdftotext`/`pdfinfo`） |
| 网络 | 禁止联网；缺宏包/字体只写处置建议，不自动安装 |

### 1.1 输出文件

| 文件 | 内容 |
|---|---|
| `deliverable.tex` | 主文件副本，可编辑、可并入稿件 |
| `tex_project/` | 完整可编译工程（含 `.bib`/`.cls`/`.sty`/图等） |
| `deliverable.pdf` | 编译产物；编译成功时存在，失败时说明原因 |
| `result.json` | 结构化结果 + `output_contract` 回填 + `contract_fill` 映射表 |
| `verification.json` | 独立审计：逐字引用、计数、结构、契约覆盖检查 |
| `build_report.md` | 人读摘要：状态、诊断数、编译错误、复现命令、限制 |
| `baseline/` | 改动前快照，供 diff 与引用核验 |

### 1.2 `result.json` 关键字段

必须包含且不得改名：

`case_id`、`status`、`deliverable`、`compile`、`diagnostics`、`diagnostics_residual`、`change_log`、`preserved_facts`、`evidence_map`、`citations`、`workorder_receipt`、`pending_human`、`uncertainty`、`errors`、`degradations`、`notes`、`metrics`、`runtime`、`verification`、`output_contract`、`contract_fill`。

`output_contract` 从输入原样深拷贝，未知字段保留，不修改键名。`contract_fill` 记录每个契约字段由哪个文件或结果字段满足；无法满足的字段写 `null` 并在 `pending_human` 或 `errors` 说明原因。

`status` 取值：

- `ok`：PDF 存在、关键诊断收敛、事实核验通过、契约字段完整。
- `partial`：已产出可编辑成果，但编译失败、部分字段未完整覆盖或存在未确认修改。
- `insufficient_evidence`：材料不足、无法完成可信写作或核验。
- `input_error`：`case.json` 无效、契约缺失或输入不可解析，但仍然产出结构完整的结果。

---

## 2. 专属执行流程

每个步骤按「输入 → 动作 → 输出 → 失败分支」执行。

### 步骤 1：盘点输入与契约

**输入**：`/input/case.json`、`/input/task.md`、`/input/**` 下所有文件。

**动作**：

1. 读取 `case.json`。若不存在，找层级浅、体积小的 `*.json`，仍解析。
2. 提取 `case_id`：`case_id | caseId | id | task_id`。
3. 提取 `output_contract`：`output_contract | outputContract | contract`，原样保留。
4. 递归扫描 `/input`（≤600 个，单个 ≤20MB）。识别：
   - `.tex`：按 `\documentclass` 判定主文件。
   - `.bib`：参考文献条目。
   - `.cls/.sty`：模板依赖。
   - `.pdf/.docx/.md/.txt/.csv/.json/.tsv`：事实材料与任务约束。
   - 图片：只记录存在性，不 OCR，除非任务明确要求且工具可用。
5. 从 `task.md` / `case.json` 中提取任务要求、检查清单、格式约束、评分证据范围。

**输出**：输入清单、`case_id`、输出契约副本、任务要求清单。

**失败分支**：

- 坏 JSON → `errors[case_json_invalid]`，继续执行。
- 找不到 `case_id` → 使用 `unknown_case`，写入 `errors[case_id_missing]`。
- 找不到契约 → `output_contract: {}`，写入 `errors[output_contract_missing]`。

**禁止**：根据文件名、文件夹名、领域标签猜测材料内容；必须打开文件真实读取。

---

### 步骤 2：真实解析材料

**输入**：步骤 1 发现的所有材料文件。

**动作**：

1. `.md/.txt/.csv/.json/.tsv`：直接读取原文。
2. `.tex/.bib/.cls/.sty`：直接读取源码，不忽略注释。
3. `.pdf`：优先调用 `pdftotext -layout <file> -` 提取文本；若不可用，标记 `degradations[pdf_text_unavailable]`。不要依据文件名推断 PDF 内容。
4. `.docx`：由脚本的 `fx` 侧通过 `zipfile` 读取；若损坏，标记 `errors[docx_read_failed]`。
5. 图片 / 扫描 PDF：不进行 OCR；若任务要求解析图片中的科学数据，写 `pending_human`，不得虚构。
6. 将材料中的数字、术语、引用、图表描述、关键论断逐条提取，形成事实底稿。

**输出**：事实底稿、引用清单、材料缺陷清单。

**失败分支**：

- 材料缺失 → `pending_human[item]`，说明缺失材料与所需字段。
- 材料格式不支持 → `degradations[unsupported_material_format]`，继续。
- 材料冲突 → 所有冲突值均保留，写 `pending_human`，不选边。

---

### 步骤 3：先跑完整基线脚本

**输入**：`/input`、`/app/output`、`/app/work`。

**动作**：

先做静态诊断，不立即编译：

    python3 -B scripts/latex_doctor.py --input /input --out /app/output --work /app/work --no-build

再执行完整流程：

    python3 -B scripts/latex_doctor.py --input /input --out /app/output --work /app/work --max-seconds 780 --timeout 240

如果脚本不支持以上某参数，先运行 `python3 -B scripts/latex_doctor.py --help` 确认可用的等价参数；但不得跳过基线流程。

**输出**：`result.json`、`deliverable.tex`、`tex_project/`、`baseline/`、`verification.json`、`build_report.md`。这是完整基线，不得删除。

**失败分支**：

- 脚本异常 → 记录 `errors[script_failed]`；仍必须手工生成合法 `result.json`。
- 编译失败 → 保留诊断，继续步骤 4。
- 依赖缺失 → 记录 `degradations[no_latex_engine]` 等，不中止。

---

### 步骤 4：读取基线与诊断，形成修复/写作清单

**输入**：`/app/output/result.json`、`/app/output/build_report.md`、`/app/output/verification.json`。

**动作**：

1. 读取 `diagnostics` 与 `diagnostics_residual`，理解错误类、文件、行号、修复配方。
2. 读取 `preserved_facts`、`evidence_map`、`citations`、`workorder_receipt`。
3. 对照材料底稿与任务要求，找出需要你亲自改写、补写的正文、表格、公式、引用、模板字段。
4. 检查基线是否只是脚本骨架；若是，标记为 `agent_review_required`，准备增强。

**输出**：Agent 自己的任务清单：哪些由脚本已解决，哪些必须亲自完成。

**失败分支**：

- 基线字段缺失 → 先补齐 `result.json` 字段，再继续。
- 诊断偏离材料 → 回到步骤 2 重新解析材料，不信任脚本的自动判断。

---

### 步骤 5：Agent 亲自完成核心写作与修复

**输入**：`/app/output/tex_project/` 源码、材料底稿、任务要求。

**动作**：

1. 只编辑 `/app/output/tex_project/` 下的源码；`/input` 与 `/app/output/baseline/` 保持只读。
2. 按任务要求完成：
   - 修编译错误：只修根因，保留首因记录，级联错误标注。
   - 修公式：符号、上下标、多行对齐、编号、单位正斜体。
   - 修表格：列宽、对齐、合并单元格、三线表、溢出、列数。
   - 修引用：`\ref`/`\cite` 与 `.bib` 条目、编号、排序、多轮编译收敛。
   - 模板适配：模板必填项、文件结构、版式约束。
   - 写作/改写：基于真实材料撰写正文，保留事实、数字、引用来源。
3. 每次重大改动后写 `change_log`：`original_quote → revised_quote + reason + locator`。
4. 对每个事实、数字、引用做逐字回查；完成核验后写回 `result.json`。

**不得**：

- 把 PDF、截图或无法编译片段当 `.tex` 成品。
- 用脚本自动修复代替你本人的判断。
- 编造材料中不存在的文献、DOI、数值、结论。

**输出**：增强后的 `deliverable.tex`、`tex_project/`、更新后的 `change_log`、`evidence_map`、`pending_human`。

**失败分支**：

- 无法确认某项事实 → 写 `pending_human`，不硬写。
- 材料冲突 → 两条都进 `pending_human`。
- 模板文件缺失 → `degradations[missing_cls]`，继续静态修复。

---

### 步骤 6：增量复跑与收敛

**输入**：增强后的 `tex_project/`、更新后的 `result.json`。

**动作**：

先静态诊断：

    python3 -B scripts/latex_doctor.py --input /input --out /app/output --work /app/work --no-build

再全量构建与审计：

    python3 -B scripts/latex_doctor.py --input /input --out /app/output --work /app/work --max-seconds 780 --timeout 240

若 `compile.errors` 非空，按错误分类排序先修第一条；级联错误先修根因。不要无限循环，最多执行 3 轮修复；3 轮后仍失败就保留 `partial`。

**输出**：更新版 `deliverable.tex`、`deliverable.pdf`（如成功）、`verification.json`、`result.json`。

**失败分支**：

- 编译超时 → `compile.passes[].tail=TIMEOUT`，保留已有日志。
- 缺宏包/缺字体 → 写清 `tlmgr` / `TEXMFHOME` 命令或字体替代方案，不自动安装。
- 报错级联 → 保留首因，后续标注为级联。

---

### 步骤 7：自检 rubric 与契约覆盖

**输入**：当前 `/app/output` 下全部产物。

**动作**：

逐项检查：
- `output_contract` 每个键是否已回填或显式写 `null`。
- `result.json` 顶层字段是否齐全。
- `deliverable.tex` 是否为真实可编辑源码。
- 所有可编辑产物是否有对应的 PDF/PNG 预览（如契约要求）。
- 每条 `change_log` 是否能在 `baseline/` 与 `tex_project/` 中逐字命中。
- `verification.json.status` 是否 `fail`。

**输出**：自检结论、待修项清单。

**失败分支**：

- 缺字段 → 先补字段再收尾。
- 验证失败 → 按 `verification.issues` 修复后重跑一次。

---

### 步骤 8：最终收尾

**动作**：

1. 确保 `/app/output/result.json` 为最新版本，与磁盘产物同源。
2. 确保 `status`、`errors`、`degradations`、`pending_human`、`uncertainty`、`runtime` 诚实填写。
3. 确保 `/app/output/build_report.md` 含复现命令、版本、限制、人工确认项。
4. 最后再跑一次全量脚本，保证结果与产物一致。
5. 无论结果是否完整，退出码保持 0。

---

## 3. 预算策略

默认预算：**64 次模型请求 / 900 秒 / 单次响应 16384 tokens**。

### 3.1 请求分配建议

| 阶段 | 请求数 | 说明 |
|---|---|---|
| 步骤 1-2：输入盘点 + 材料解析 | 8-12 | 读取 `case.json`、`task.md`、材料、事实底稿 |
| 步骤 3：基线脚本运行 | 1-3 | 脚本调用不要占用模型循环 |
| 步骤 4：诊断阅读 | 4-8 | 错误、事实、引用、workorder |
| 步骤 5：核心写作/修复 | 12-20 | 最高权重，优先完成可编译 `.tex` 与事实正确性 |
| 步骤 6：增量复跑 | 3-6 | 避免重复编译；只在关键改动后跑 |
| 步骤 7-8：自检与收尾 | 5-8 | 契约回填、验证、finalize |
| 预留 | 5-10 | 异常恢复、partial 增强 |

### 3.2 优先级

按评分权重：

1. **实际效果 40 分**：先保证 `deliverable.tex`、编译通过、事实正确、契约字段完整。
2. **可靠体验 10 分**：保持 result.json 合法、异常处理真实；这是稳定产出基础。
3. **使用增益 25 分 / 创新增益 15 分**：主要依赖脚本流程、错误分类、审计机制；不要用模型请求堆砌文字自述。
4. **生态贡献 10 分**：主要由 `SKILL.md`、`references/`、`rules.json` 支撑；无需在案例中额外耗费大量请求。

### 3.3 尽早落盘

- 步骤 3 跑完基线后，立刻确保 `/app/output/result.json` 存在且合法。
- 每完成一项重大修改，就写回 `result.json`。
- 到 56 次请求或 780 秒时，停止新增改进，优先 finalize。
- 若预算将尽：写 `degradations[budget]`，保留 partial，不丢失已有成果。

---

## 4. 隐藏案例鲁棒性

隐藏案例可能故意包含缺失、损坏、格式不支持、空输入、契约缺失、模板缺失、字体/宏包缺失、超时等情况。

| 情况 | 处置 |
|---|---|
| 无 `case.json` | 选任意浅层 `*.json`；仍失败则 `case_id=unknown_case`，继续解析材料 |
| `case.json` 损坏 | `errors[case_json_invalid]`，`status=input_error`，仍产出合法 `result.json` |
| `output_contract` 缺失 | `output_contract: {}`，同时强制输出本文件规定的关键字段 |
| `task.md` 缺失 | `degradations[task_md_missing]`；从材料与 `case.json` 推断任务，不编造任务外事实 |
| 无 `.tex` 文件 | 若为纯写作题，生成带 `% SCAFFOLD` 注释的最小可编译骨架；正文必须由 Agent 撰写，并写 `degradations[scaffold_used]` |
| 无 TeX 发行版 | `degradations[no_latex_engine]`，只做静态诊断，`status=partial` |
| 缺宏包 / 缺 `.cls` | 错误类 `E01_MISSING_FILE` / `E03_PACKAGE`；给出 `tlmgr` / `TEXMFHOME` 建议，不自动安装 |
| 缺字体 / 特殊字符 | `E12_FONT`；建议替代字体族或改用 LaTeX 安全字符 |
| PDF 无文本层 / 提取失败 | `degradations[pdf_text_unavailable]`；不依据文件名猜内容 |
| DOCX 损坏 | `errors[docx_read_failed]`；从其他材料继续 |
| 空输入 | `status=insufficient_evidence`，`pending_human` 说明缺少材料 |
| 编译超时 | `compile.passes[].tail=TIMEOUT`；保留已解析日志 |
| 权限不足 | `HOME/TEXMFVAR/TEXMFCFG` 重定向到 `/app/work`；仍失败则 `E13_PERMISSION` |
| 材料冲突 | 所有冲突值均保留，`pending_human` 列出两个来源与冲突项 |
| 材料不足 | 不补造数据；写 `pending_human` 与 `uncertainty` |
| 脚本异常 | `errors[script_failed]`；仍手工写 legal `result.json` |

任何情况下：

- 必须返回退出码 0。
- 必须存在 `/app/output/result.json`。
- 必须包含 `case_id`、`status`、`errors`、`degradations`、`pending_human`、`uncertainty`、`runtime`、`output_contract`。
- 不编造安装状态、软件版本、benchmark 分数、运行 trace。

---

## 5. rubric 维度 → 交付要求 → 自证方式

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果·任务完成度 15 | 真正交付能在指定模板下编译并可靠 `\input` / `\include` 的 `.tex` 成果 | `deliverable.tex` 含 `\documentclass`、`\end{document}`；`compile.pdf_exists=true`；`tex_project/` 完整 |
| 实际效果·结果正确性 15 | 公式、表格、引用、版式与原文意图及模板要求一致 | `compile.errors`、`diagnostics_residual`、`verification.json`；公式/表格/引用逐项定位 |
| 实际效果·结果完整性 5 | 任务要求改动点、模板必填项、配套文件逐项覆盖 | `workorder_receipt` 每条为 `done_verified` 或缺项列 `pending_human` |
| 实际效果·结果可核验性 5 | 源码改动、编译过程、产物可独立复核 | `change_log`、`baseline/`、`evidence_map`、`compile.passes`；逐字回查 |
| 使用增益·质量增益 15 | 加载后编译成功率与修复正确率提升 | 同一命令完成诊断→修复→构建→审计；减少盲编译 |
| 使用