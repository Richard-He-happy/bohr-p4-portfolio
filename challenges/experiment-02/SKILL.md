---
name: experiment-feasibility-review
version: 1.1.0
description: 实验方案可行性审查。当用户给出一份或多版本实验方案、候选设计、SOP、课题计划书，要求判断“能不能按现有设备、材料、预算、排期、样本与伦理状态真实开工”，或要求做方案自查、内部评审、送审前检查、版本比选时使用。把方案与设备量程、试剂库存与货期、预算与时间窗、参数范围、风险处置、伦理与安全状态逐条核对，输出七类约束检查表、逐版本可执行结论、protocol.md、risk_table.csv、check_matrix.csv 与 result.json。不做实验执行、数据分析与文献综述。
---

# 实验方案可行性审查

## 0. 最高优先级：你才是交付者，脚本只是工具

**本 Skill 的真正作者是你——Harness Agent。** 你必须亲自阅读 `/input/case.json`、`/input/task.md` 及全部材料，从真实内容中提取证据、做算术、判断缺口、撰写 protocol.md 与表格。`scripts/main.py` 只负责生成**基线候选结果**和结构化骨架；这些基线可能不完整、可能有误判，**不得原样当作最终成品**。你必须至少完成：
- 对七类检查逐类抽查 1–2 条，核对 `locator`/`quote` 与原文一致；
- 复核每个版本的算术（量程、货期、总历时、费用、取值域）与结论；
- 把脚本未识别、但材料中明确存在的设备/材料/参数/风险补充进表格；
- 将不确定项明确标为 `pending_human`，不编造数据、引用、分数。
最终交付物必须是你读材料、推导、撰写/制作后的**完整且经核验**的成果。

---

## 1. 用途与边界

**做**：把一份（或 2–3 个版本）实验方案，转成可逐条判定的七类约束检查表，用输入给出的真实数字做算术，给出可执行结论与条件清单。

七类检查（固定顺序）：`HYPOTHESIS` 假设与变量 / `CONTROL` 对照组 / `RESOURCE` 设备与材料 / `TIME` 时间与成本 / `PARAM` 参数范围 / `RISK` 风险与异常 / `ETHICS` 伦理与安全。

**不做**：实验执行、数据分析与统计结论、文献综述、论文写作；不替代伦理委员会、生物安全委员会、设备管理员或 PI 的签字。

**四条立场**（与“技术上看起来合理”式点评的分界）：

1. **未写 ≠ 满足**：方案没写的检查项一律 `gap`，不因“通常会做”记 `met`。
2. **只在输入上算术**：时间、费用、量程余量只用输入数字；输入没给的阈值不臆造，进 `pending_human` 与 `uncertainty`。
3. **可复核**：每条判断带 `source_id + locator + quote`，指向方案原文的具体字段或行。
4. **结论可执行**：`feasible_with_conditions` 必须写成条件清单（买什么、批什么、改哪个参数、等多少天），不写“建议进一步确认”。

---

## 2. 触发条件

适用：用户给出实验方案/设计/多版本候选，问“能不能做”“还缺什么”“哪版可行”“按现有条件能不能开工”“帮我审一下方案”。

不适用：纯文献综述、数据分析、图表绘制、论文润色——改用对应 Skill。

---

## 3. 输入、输出与运行契约

- 输入：`/input/case.json`（或任意 `case*.json`）+ `/input/task.md` + `/input/` 下全部材料（md/txt/csv/xlsx/docx/pdf/图片等）。**必须真实解析材料内容**，从文件/字段中读取实际文本、数字、表格，不得依据文件名或领域标签猜测。
- 工作目录：`/app/work`（中间产物可放这里）；最终产物必须落在 `/app/output`。
- `result.json` 必须包含 `case_id` 和**原 `output_contract` 的全部字段**（键名不改）。若 `task.md` 中提供 output_contract 定义，逐键保留；否则使用 `references/schema.md` §2 的默认契约字段。
- 可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**；本 Skill 默认输出 Markdown/CSV/JSON，如无 Office 类产物则跳过，但需在自检中确认。
- 预算：**64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）**。先明确 rubric 权重最高的交付物，优先完成并**尽早落盘 honest partial**，再增量改进；避免无意义循环与冗余调用。
- 只读 `/input`，只写 `/app/work` 与 `/app/output`；不联网；纯 Python 3.8+ 标准库（`pypdf` 存在时用于 PDF，缺失则降级，不是硬依赖）。
- 退出码恒 0；任何异常都写合法 `result.json` 并说明缺口。

---

## 4. 调用方式

运行基线脚本：

    python3 -B scripts/main.py --input /input --output /app/output
    python3 -B scripts/main.py --help

`--help` 显示全部参数。脚本入口自解析参数，不依赖当前工作目录（用 `Path(__file__)` 定位 `references/`）。
stdout 只打一行摘要：`case_id=… status=… checks=… elapsed=…s`。

**重要**：脚本输出只是基线。你必须随后按第 5 节流程亲自核验并增强，不得把脚本骨架当成品。

---

## 5. 本题专属执行流程（编号步骤）

### 步骤 0：预算与交付优先级初始化
- **输入**：`/input/task.md`、`/input/case.json` 顶层结构
- **动作**：快速浏览确定案例数、是否有 output_contract 字段说明、材料类型与数量；标记最高权重交付物（七类检查、逐版本结论、protocol.md、result.json）
- **输出**：内存中的优先级清单；可写入 `/app/work/plan_notes.md`
- **失败分支**：`case.json` 缺失或不可解析 → 进入第 7 节降级流程，仍产出合法 `result.json`

### 步骤 1：盘点输入
- **输入**：`/input` 目录递归列表、`case.json`、`task.md`
- **动作**：递归遍历 `case.json`，按键名子串匹配 `plan/candidate/version/方案/版本`（多版本方案取内容最长的一组，≤6 版）、`equipment/instrument/设备/仪器`、`reagent/material/试剂/耗材`、`parameter/factor/参数/取值`；预算、时间窗、人力按 `budget/预算`、`deadline/window/周期/期限`、`personnel/人员`。其余文件按扩展名记录，准备解析。
- **输出**：输入清单与版本计数，保存至 `/app/work/input_inventory.md`
- **失败分支**：文件过多或单文件过大（>4MB），只截取前 400KB 文本，不阻塞；不可读文件标记 `degraded`

### 步骤 2：真实解析材料
- **输入**：全部材料文件
- **动作**：用 `pdf-text-tool`（若平台提供）或 `pypdf` 解析 PDF；`.docx/.xlsx/.pptx` 解 zip 取 XML 文本；`.md/.txt/.csv/.json` 直读；位图不做 OCR（记 `degradations`）。**必须获得实际文本和数字，禁止依据文件名猜测内容。**
- **输出**：每个文件的文本摘录及来源路径；缺失/损坏列表
- **失败分支**：PDF 抽不到文本或位图，记入 `degradations`，不阻断其余检查；材料整体缺失进入第 7 节降级

### 步骤 3：运行基线脚本
- **输入**：步骤 1/2 识别的输入
- **动作**：执行 `python3 -B scripts/main.py --input /input --output /app/output`，生成基线 `result.json`、`protocol.md`、`risk_table.csv`、`check_matrix.csv`
- **输出**：基线全套产物
- **失败分支**：脚本报错或依赖缺失，捕获报错进 `errors`，尝试内置 fallback；仍失败则手工构建最小合法 `result.json` 并记录，随后继续 Agent 增强

### 步骤 4：Agent 逐项核验与增强
- **输入**：基线产物 + 原始材料文本
- **动作**：你必须亲自打开并阅读输出文件，完成以下动作：
  - 对七类检查每类抽查 1–2 条，核对 `locator`/`quote` 与原文一致；
  - 复核所有算术：`R-02/P-02` 参数量程、`R-04` 货期 vs 时间窗、`T-02` 总历时 vs 时间窗、`T-04` 费用 vs 预算、`P-05` 取值域；
  - 查找脚本漏判的明确设备/材料/参数/风险，补充进 `check_matrix.csv` 与 `risk_table.csv`；
  - 将不确定项标为 `pending_human`，在 `result.json` 的 `agent_review` 字段记录你的核验动作、发现、修正。
- **输出**：更新后的 `result.json`、`protocol.md`、`check_matrix.csv`、`risk_table.csv`
- **失败分支**：发现矛盾或不确定，不删除基线字段，在 `agent_review` 记录 `conflicts`，并通过 `pending_human` 暴露；无法完成的检查保留为 `gap`

### 步骤 5：生成/补全可编辑预览
- **输入**：更新后的产物
- **动作**：若目标产物包含 Office/幻灯片/图形（本 Skill 通常不包含），生成真实渲染的 PDF/PNG 预览到 `/app/output`；否则跳过
- **输出**：预览文件（如适用）
- **失败分支**：渲染失败记录 `degradations`，不阻断最终结果

### 步骤 6：自检 rubric
- **输入**：全部产物
- **动作**：对照第 8 节 rubric 表逐项自检，检查完整性、字段齐全、证据可复核、降级标注；写入 `result.json.selftest`
- **输出**：`selftest` 字段（`checks` 条数、`contract_missing`、`artifacts_missing`、`classes`）
- **失败分支**：发现缺失，回到步骤 4 补齐；仍有缺项，按第 7 节降级

### 步骤 7：回填 result.json 并 finalize
- **输入**：最终结果
- **动作**：确保