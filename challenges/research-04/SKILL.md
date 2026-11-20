---
name: research-trend-lens
description: >-
  基于给定文献材料真实产出四类可核验的研究前沿产物：年度趋势与变点、时间窗主题演化、各阶段代表作、有排除证据的研究空白；所有结论回链到材料定位与原文引用，区分事实、推断与不确定。适用于研究前沿与趋势分析、时间趋势、主题演化、代表作选取、研究空白识别、evidence-based research frontier mapping。
version: 2.0.0
---

# research-trend-lens（研究前沿与趋势分析）

## 0. 核心原则（最高优先级）

**一句话用途**：将给定文献集转化为四类可复核的研究前沿产物——年度趋势、主题演化、代表性工作、研究空白，并附证据矩阵、不确定性声明和运行记录。

**脚本只是工具，最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把 `scripts/main.py` 的原始输出、`references/report_template.md` 的空模板、或任何骨架内容直接当作正式成品提交。主脚本的作用是快速生成完整基线，Agent 必须在该基线上完成证据核验、结论润色、边界说明和结果回填。

**完整性优先（v6 混合策略）**：
1. 进入任务后先运行本 Skill 自带的主脚本，产出**全套基线交付物**（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段）。
2. 后续的 Agent 校验与改写只能在基线上**增强**；不得删除、清空或遗漏任何基线与契约字段。若不确定，保留原产物，并在 `result.json` 中标注 `reviewed_by_agent`。
3. 提交前必须逐项核对「`output_contract` 字段 list × 磁盘文件 × `result.json` 键」三者一一对应；缺任何一项先补齐再收尾；`status=partial` 时必须列出缺失项。
4. Agent 亲自核验关键论断、数字、引用的来源一致性，把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`），这是“genuinely-derived solution”的证据。

---

## 1. 用途与边界

本 Skill 在**给定材料**内回答四个问题：产出量如何随年份变化，主题如何按时间窗出现/持续/衰退，各阶段由哪些工作代表，哪些问题被反复提出但未被解决。它**不**检索外部数据库，**不**根据文件名或领域标签猜测内容，**不**声称覆盖整个领域。

适用场景：case 提供了研究问题与材料（PDF / RIS / CSV / JSON 题录 / TXT），并要求做趋势、演化、代表作或空白判断。

不适用：单篇精读、效应量元分析、需要外部引用数或数据库检索、材料完全缺失且无法形成任何证据基础。

所有结论都只能基于**实际解析到的材料内容**。材料不足、年份缺失、主题歧义、证据冲突都必须在结果中显式标注，不得编造。

---

## 2. 运行契约与目录

- Skill 包安装在 `/skills/weekly-skill`，本文件是包根目录。
- 输入目录：`/input`，其中至少有 `case.json` 与 `task.md`，以及题面提供的材料文件。
- 工作目录：`/app/work`。运行命令时先 `cd /app/work`，脚本自身可解析包内路径，CWD 不敏感，但所有临时文件写在工作目录。
- 最终产物目录：`/app/output`。`result.json`、报告、CSV、预览等所有最终交付物必须落在 `/app/output`。
- 运行基线主脚本命令：

```bash
cd /app/work && python3 -B /skills/weekly-skill/scripts/main.py --input /input --out /app/output
```

- 脚本只使用 Python 标准库，不访问网络，不依赖第三方包；`pdftotext` 如存在则优先使用，否则使用内置流式提取器。若平台提供 `pdf-text-tool`，也优先用于 PDF 实文本提取。
- **退出码始终为 0**。脚本会在解析前先写一个合法 partial `result.json`，最终再覆盖；`changes[]` 记录两次写入。
- 运行资源：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。本章的预算策略以该约束为准。
- 可编辑 Office / 幻灯片 / 图形产物必须额外给出真实渲染的 PDF/PNG 预览；数据 CSV 与 Markdown 报告不要求预览，但如果 Agent 额外生成图表或 PPTX，必须附渲染产物。

---

## 3. 本题专属执行流程（编号步骤）

以下每步都给出输入、动作、输出、失败分支。**顺序不可跳过，尤其是步骤 3 的基线生成和步骤 4 的 Agent 核验。**

### 步骤 0：初始化与预算规划

- **输入**：`/input/case.json`、`/input/task.md` 的头部信息、可用材料文件名。
- **动作**：
  1. 读取 `case.json` 的 `case_id`、`research_topic`/`research_question`、`output_contract` 摘要；读取 `task.md` 的评分点与 Runtime contract。
  2. 列出 `/input` 下所有文件，识别格式（用扩展名和 magic bytes，不只看文件名）。
  3. 制定预算：确定必须完成的基线、核验、增强、回填步骤，预留异常恢复请求数（见第 4 节）。
- **输出**：内存中的任务计划；可以写在 `/app/work/plan.md`，不必须。
- **失败分支**：若无法读取 `case.json`，按第 5 节空输入/契约缺失处理，仍要运行脚本生成合法 `result.json`。

### 步骤 1：盘点输入

- **输入**：`/input` 目录。
- **动作**：
  - 解析 `case.json`（或 `task.json`、`case*.json`），提取 `case_id`、研究问题、时间窗口、纳排规则、`output_contract`。
  - 递归扫描所有材料文件，按扩展名与 magic bytes 分类：PDF、RIS、CSV/TSV、JSON/JSONL（题录或 `nodes`/`edges`）、TXT/MD。
  - 记录不支持的格式（`.docx`、`.xlsx`、图片、压缩包等）：这些**不解析**，只列入 `uncertainty[material_unparsed]` 和 `screening.excluded`，绝不猜测内容。
- **输出**：输入清单（case 摘要 + 文件分类列表）。
- **失败分支**：没有 `case.json` 或无法解析 JSON → 脚本会写 `status=input_error`，报告仍要生成；其他材料继续扫描。

### 步骤 2：真实解析材料

- **输入**：步骤 1 识别的受支持材料文件。
- **动作**：
  - 对每个 PDF 用 `pdftotext` 或环境提供的 `pdf-text-tool` 提取真实文本，生成页面级定位。
  - 对 RIS/CSV/JSON 题录逐条提取字段；对 TXT/MD 按段提取文本。
  - **不依据文件名或领域标签猜测内容**。必须读取实际解析文本，若提取质量过低（quality < 0.55，如扫描版或 CID 编码），则标题作为引用，正文不用于证据。
  - 记录每个文件的解析成功、失败、页数、记录数、质量评分。
- **输出**：解析后的记录集（标题、年份、DOI、摘要、正文、定位、quality）与解析日志。
- **失败分支**：某个文件解析异常/损坏或为不支持格式 → 列入 `degradations` 和 `screening.excluded`，继续处理其他文件。全部材料不可用 → 产出 `status=insufficient_evidence`，空趋势表和空证据矩阵，绝不编造。

### 步骤 3：运行基线脚本并产出全套基线

- **输入**：`/input` 与已解析材料。
- **动作**：
  1. 执行：
     ```bash
     cd /app/work && python3 -B /skills/weekly-skill/scripts/main.py --input /input --out /app/output
     ```
  2. 该命令一次性完成：部分契约回填 → 提取 → 年份归一 → 去重 → 筛选 → 年度统计/变点检测 → 主题演化 → 代表作选取 → 空白识别 → 冲突检测 → 生成证据矩阵、CSV、报告、最终 `result.json`。
  3. 脚本会输出所有 `output_contract` 字段、`case_id`、产品 CSV、`research_report.md`、`evidence_map.csv`、`run_ledger.json`。
- **输出**：完整基线交付物，位于 `/app/output`。
- **失败分支**：脚本崩溃 → 依据 `references/method.md` 手动写最小合法 `result.json`，退出码 0；不得删除已落盘的部分产物。

### 步骤 4：Agent 亲自核验证据

- **输入**：`/app/output/result.json`、`/app/output/evidence_map.csv`、材料原文。
- **动作**：
  1. 从 `claims[]` 中随机或按优先级抽取 3-8 条关键论断，覆盖时间趋势、主题演化、代表作、空白。
  2. 对每条论断，根据 `evidence_map.csv` 的定位（`file.pdf#p<page>`、`file.ris#rec<n>` 等）打开对应材料段落，核对原文是否支持。
  3. 检查引用是否真实存在（NFKC 归一、去除多余空白、大小写敏感的子串匹配）。
  4. 检查统计数字是否可复算：`verification.dated_records` 与 `trend_annual.csv` 行计数一致；`screening.records_included` 与去重后记录数一致。
  5. 将核验结果写入 `reviewed_by_agent` 字段：每个样本记录 `claim_id`、`result`（verified/pending_human/conflict）、`note`。
- **输出**：核验记录（可先存在 `/app/work/review_notes.md`）。
- **失败分支**：无法打开原文或定位失效 → 将该引用标为 `quote_verified=false`，对应 claim 降级为 `insufficient` 或 `pending_human`；不删除证据矩阵，但要标注问题。

### 步骤 5：Agent 产出/增强完整成品

- **输入**：基线产物 + 核验记录。
- **动作**：
  1. 在 `research_report.md` 基线上润色：确保四个产品（年度趋势、主题演化、代表作、研究空白）各自有独立章节，包含趋势图背后的数据说明、演化阶段依据、代表作选取口径、空白排除证据。
  2. 修正自动提取中发现的明显错误（如年份错位、主题误归、引用错位），并在 `changes[]` 中记录修改。
  3. 补充结论边界：哪些是材料事实、哪些是合理推断、哪些无法确定；写入 `limitations` 和 `uncertainty`。
  4. 如要生成图表，必须连带生成真实渲染的 PDF/PNG 预览，并放入 `/app/output`。
  5. **不删除、不清空任何基线字段**；如不同意脚本输出，保留原字段并在 `reviewed_by_agent` 中说明。
- **输出**：最终可读的 `research_report.md`，增强后的 `evidence_map.csv`，图表预览（如有）。
- **失败分支**：时间不足 → 保留基线产物，标记 `status=partial`，不要未完成就提交。

### 步骤 6：自检 rubric 与契约

- **输入**：`/app/output/result.json`、`/app/output/research_report.md`、产品 CSV。
- **动作**：
  1. 逐项核对 `output_contract` 字段是否全部出现在 `result.json` 顶层，键名不变，未知标量保持 `null`，列表成为 `[]`。
  2. 核对产品文件是否齐全：`research_report.md`、`evidence_map.csv`、`trend_annual.csv`、`topic_evolution.csv`、`representative_works.csv`、`screening_log.csv`、`run_ledger.json`。
  3. 运行自检命令：
     ```bash
     python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['status'],r['verification'])"
     ```
  4. 检查 `contract_backfill.filled` 是否等于契约字段总数；`verification.quotes`