---
name: reading-08-formula-structure
description: 用于公式解析与数学推理科研阅读任务：确定性还原 MathML/TeX 公式为可校验 LaTeX 与结构统计，产出符号变量表（区分 paper_defined/context_inferred/common_knowledge）、带假设与边界条件的推导步骤、数值与量纲核验，并生成 result.json、formulas.tex、symbol_table.csv、verification.md；脚本只是解析工具，最终交付物由 Harness Agent 亲自读材料、推导、核验并撰写。材料无公式表示时如实报 insufficient_evidence，不反推、不填 0。
version: 3.0.0
license: MIT
---

# 公式解析与数学推理（reading-08）

## 0. 角色与铁律（最高优先级）

本 Skill 用于科研阅读中的**公式解析与数学推理**：认得准、讲得清、推得顺、算得回。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、模板或未经验证的脚本输出直接当成品。你必须：

1. 真实解析 `/input` 下的材料内容，不得依据文件名或领域标签猜测/补造。
2. 先运行 `scripts/main.py` 产出基线交付物；后续所有校验与改写只能**叠加增强**，不得删除、清空或遗漏任何基线与契约字段。
3. 对每个关键结论（公式、变量、推导、数值）亲自回看材料，确认 `quote` + `locator` 可追溯。
4. 不确定、缺失、冲突必须显式标注 `pending_human` / `limitations` / `uncertainties`，不得编造数据、引用、分数。
5. 任何情况下都要产出合法 `result.json`（退出码 0），即使状态为 `partial` 或 `insufficient_evidence`。

## 1. 用途与边界

**做：**

- 解析 `artifacts/*.xml` / MathML / TeX / 文本中的公式，确定性映射为可校验 LaTeX 与结构统计（`fracs`、`subsups`、`radicals`、`matrices`、`cases`）。
- 建立符号变量表，区分来源：`paper_defined`（原文定义）、`context_inferred`（上下文推断）、`common_knowledge`（常识补充）。
- 抽取带 `rule`、`assumptions`、`approximations`、`boundary_conditions` 的分步推导线索。
- 只使用材料中字面给出的数值做代入核验；缺值标注 `not_computable`，全无赋值时给出明确标注的 `example_only` 探针。
- 对无公式表示但有材料的快照型案例，如实报 `insufficient_evidence`，并尽可能完成指标/条件核验。

**不做：**

- 不把公式目录 XML 当答案输出（formula catalog 不是 linearized answer）。
- 不反推缺失公式、不把未知填 0、不臆造符号定义、单位或数值。
- 不做符号代数证明，推导只到“原文这么说”并附依据。
- 不对位图做 OCR 猜测，除非环境提供可用的 OCR 工具且你已验证其输出可回原文。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 入口 | `scripts/main.py`（仅 Python 标准库，无网络，不依赖 CWD） |
| 输入 | `/input/case.json` + `/input/task.md` + `/input/**` 材料；`--input` 可覆盖 |
| 工作目录 | `/app/work`（可存放临时文件、笔记、中间提取文本） |
| 输出 | `/app/output/`（`--output` 可覆盖；不可写时退到 `./output` 并在 `errors` 记录） |
| 主产物 | `result.json`；伴随 `formulas.tex`、`symbol_table.csv`、`verification.md` |
| 审计产物 | `golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json`；`--no-audit` 可跳过且不影响主产物 |
| 退出码 | 恒 0；先写 partial `result.json`，`finally` 里无条件 finalize |
| 资源定位 | 脚本内 `Path(__file__).resolve().parent`，脚本内 `sys.path` 注入同目录 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 资源限制 | Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink |

**调用命令：**

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

脚本本身秒级完成；你的模型请求预算用于：读输入、跑脚本、读脚本输出、亲自核验材料、补全契约字段、写增强产物。

## 3. 输入发现与材料解析规则

1. 优先读 `/input/case.json`；其次 `case_input.json` / `input.json`，再递归 `case*.json`。
2. 读 `case_id`（常见别名 `id`）；`output_contract` / `output_spec` / `contract` 任一存在即原样保留，用于后续回填。
3. 递归扫描 `/input/**`，按**扩展名 + 魔数**分类：`.xml/.mathml/.nxml` 或 `<?xml` 头、`.tex`、`.txt/.md/.rst`、`.json`、`.pdf`（`%PDF-`）、图片、docx/xlsx/pptx。
4. **脚本能直接解析：** XML/MathML、TeX、文本、JSON 内嵌 `<math>`。
5. **脚本不能直接解析：** PDF、图片、Office 文档。若材料包含这些格式，你必须调用环境自带的解析/提取工具（如 PDF 文本提取工具，命令以 `environment/resources.yaml` 为准）将其转为文本或结构化数据，再交给脚本或亲自阅读提取文本。提取后的中间文件放在 `/app/work/`，不要污染 `/input`。
6. 材料没给的对象写进 `result.missing_objects`，不构造内容。

支持的公式来源优先级：`<annotation encoding="application/x-tex">`（原文 TeX，`latex_source=mml_annotation`）> MathML 结构映射（`structural_mapping`）> `.tex` 的 equation 环境（`source_tex`）> JSON 里内嵌 `<math>`（`structural_mapping`）。XML 解析失败时退化到正则抽 TeX annotation（`regex_annotation` + `parse_confidence=low`）。

## 4. 本题专属执行流程（编号步骤）

> 每步标注：**输入 → 动作 → 输出 → 失败分支**。你必须在预算内按顺序执行，并尽早落盘 partial。

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、递归列出 `/input` 下所有文件。
- **动作**：读取 `case_id`、`output_contract`（或 `output_spec` / `contract`），记录所有输入文件路径与类型；确认任务要求与评分维度（见 §7）。
- **输出**：将盘点结果写入 `/app/work/input_inventory.json`：包含 `case_id`、`contract_raw`、`files[]`（路径、扩展名、魔数、大小）。
- **失败分支**：
  - 无 `case.json` 或无 `output_contract` → 记录 `contract_missing`，从 `task.md` 推断最小交付物集合，继续执行。
  - 无法读取输入 → 仍需写出合法 `result.json`（`status=input_error`），退出码 0。

### 步骤 2：运行基线脚本（必须执行）

- **输入**：`/input` 目录，脚本路径 `scripts/main.py`。
- **动作**：执行 `python3 -B scripts/main.py --input /input --output /app/output`。若 `/app/output` 已有旧产物，先备份到 `/app/work/backup/`。观察脚本日志，记录 `runtime` 与 `errors`/`degradations`。
- **输出**：基线 `result.json`、`formulas.tex`、`symbol_table.csv`、`verification.md` 及审计产物。
- **失败分支**：
  - 脚本异常：记录 `errors.fatal`，尝试手动调用 `formula_core` 中可用函数或直接构造最小 `result.json`；必须保证 `result.json` 存在且合法。
  - 脚本无法解析部分材料：记录 `degradations`，不影响其他部分。

### 步骤 3：真实解析材料内容（Agent 亲自做）

- **输入**：所有材料文件 + 脚本提取的中间产物（XML 解析结果、文本段落等）。
- **动作**：
  1. 对 XML/MathML：抽查至少一个公式节点，确认脚本还原的 LaTeX 与原文结构一致（上下标、分数、根号、希腊字母）。
  2. 对 PDF：用环境 PDF 文本提取工具提取文本层到 `/app/work/<file>.txt`；若 PDF 无文本层或只有公式图像，标记 `missing_objects`，不 OCR 猜测。
  3. 对 TeX / 文本：阅读定义句、推导句、数值赋值，找出可回原文的证据段落。
  4. **亲自核验至少一个关键对象**：公式 LaTeX、一个变量的定义、一个推导步骤、一个数值代入，确保每个都有 `locator` 与逐字 `quote`。
- **输出**：核验笔记 `/app/work/agent_review.md`，包含：核验对象、原文证据、是否一致、发现的问题。
- **失败分支**：
  - 材料缺失/损坏/格式不支持 → 在 `result.missing_objects` 与 `pending_human` 中写明原因，不猜内容。
  - 核验发现脚本错误 → 在 `result` 对应条目上修正，并记录 `changes[]`。

### 步骤 4：补全契约字段并增强交付物

- **输入**：基线产物 + 核验笔记。
- **动作**：
  1. 读取 `output_contract`（若存在）的每个字段键名；将每个键作为 `result.json` 顶层键写入，并填充数据。数据来源：脚本 `result` 子对象、你的核验笔记、材料原文。若字段无法提供数据，设置为空列表 `[]` 或空对象 `{}`，并在 `contract_fields_missing` 中记录。
  2. 保留脚本生成的详细字段（`result`、`claims`、`uncertainties` 等），不得删除。
  3. 由你亲自撰写或修改 `verification.md` 中的 “Agent 核验结论” 段：说明哪些结论直接可读，哪些是推断，哪些缺失；对每个关键对象给出 `quote + locator`。
  4. 将核验结果回写 `result.json`：新增或更新 `claims`、`uncertainties`、`pending_human`；在 `changes[]` 中记录你做了哪些修改及原因。
- **输出**：更新后的 `result.json` 和 `verification.md`。
- **失败分支**：
  - 契约字段难以满足 → 记录 `contract_fields_missing` 和原因；不删除已有内容。
  - 时间不足 → 立即执行步骤 6，确保 `result.json` 合法。

### 步骤 5：自检 rubric 与契约一致性

- **输入**：当前 `/app/output` 目录。
- **动作**：
  1. 逐项对照 §7 的 Rubric 表格和 §8 自检清单。
  2. 检查 `result.json` 是否包含 `case_id` 与 `output_contract` 全部键。
  3. 检查 `claims` 中每条 `quote` 能否在材料文本中逐字找到；未找到的降级为 `quote_verified=false` + `undetermined`。
  4. 检查 `status` 判定是否诚实：无