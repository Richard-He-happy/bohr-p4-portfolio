---
name: proposal-writing
description: 编写开题报告与研究计划书；Harness Agent 必须亲自阅读材料、推导并撰写，脚本只做机械索引、校验与兜底成稿。七要素齐全、可证伪问题、里程碑可核验、风险可追踪，任何情况下产出合法 result.json 并退出码 0。
version: 3.0.0
---

# 开题报告与研究计划书（proposal-writing）

**一句话**：Harness Agent 亲自阅读原始材料、亲自推导并撰写开题报告与研究计划书；脚本只负责机械索引、校验、兜底成稿与可核验资产生成，任何脚本模板或 init 生成的 partial 结果都不得直接当作最终成品。

**最高优先级**：完整性优先——先产出全套基线交付物，再在此基础上增强；绝不因改写而删除、清空或遗漏任何 output_contract 字段或题面要求文件；脚本兜底永远能交出一份最小但完整的合法结果。

---

## 1. 运行时契约与目录约定

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`task_instruction`、`output_contract`，可选 `organizer_workorder`）+ `/input/**` 所有题面规定材料。必须真实解析材料内容，不得依据文件名或领域标签猜测。 |
| 工作区 | `/app/work`：`index.json`、`draft.json`、`draft.effective.json`、`check_report.json` 等中间文件。 |
| 产物 | `/app/output/`：主产物 `proposal.md`（可编辑 Markdown）、`proposal_matrix.json`、`milestones.csv`、`risks.md`、`result.json`，以及 5 件可核验资产（见 §7）。可编辑 Office/幻灯片/图形产物若被题面明确要求，需额外生成真实渲染 PDF/PNG 预览；本 Skill 默认交付 Markdown 文本，不生成 Office 二进制。 |
| 依赖 | Python 3.8+ 标准库；不联网；不依赖 CWD（`Path(__file__)` 定位）。 |
| 退出码 | 恒 0；所有异常写进 `result.json.errors` / `degradations`。 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。具体分配见 §3。 |
| 资源 | Skill 包最多 5 个文本文件、约 117KB，满足 50 文件 / 500KB / 2MB 限制，无 symlink。 |

---

## 2. 本题专属执行流程（必须按顺序执行）

### 第 1 步：盘点输入与契约

- **输入**：`/input` 目录全部内容；`/input/case.json`、`/input/task.md` 及材料文件。
- **动作**：运行初始化命令，让脚本机械扫描输入、识别材料、提取基础索引，并生成首份 partial `result.json` 作为兜底：
      python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
- **输出**：`/app/work/index.json`（材料清单 M1..Mn、类型、字数、段数、抽取方式、识别到的周期）；`/app/output/result.json`（首份 partial，包含所有 output_contract 字段与 `case_id`，值可能为空或占位）。
- **失败分支**：
  - `case.json` 缺失或坏 JSON → 脚本递归寻找 `case*.json`/`input*.json`；仍失败则记 `errors` 并继续。
  - 无任何材料或材料无文本 → 状态记 `input_error` 或 `insufficient_evidence`，仍产出合法 `result.json`。
  - 契约字段缺失 → 脚本按语义识别；找不到则使用默认字段（case_id, deliverable, preserved_facts, evidence_map, change_log）并标注 `degradations`。

### 第 2 步：真实解析材料

- **输入**：第 1 步索引结果与材料文件路径列表。
- **动作**：脚本已通过 `pdf-text-tool`、`pdftotext`、PyMuPDF、pdfminer、docx 的 zip-openxml 等方式抽取文本。Agent 必须检查抽取质量，对关键材料段落用 `show` 命令回看原文，确认抽取无乱码、无漏段。图片材料不做 OCR，记录 `no_ocr`，不猜测像素内容。
- **输出**：每个材料的可读文本摘录与定位（`M#/p#`），形成后续证据引文库。
- **失败分支**：某材料解析失败 → 降级标注 `extraction_failed`，仅跳过该材料；其他材料继续。绝不依据文件名或标签补造内容。

### 第 3 步：构建证据与工作稿（Agent 亲自撰写）

- **输入**：解析后的材料内容、`case.json` 中的 `task_instruction`、`output_contract`、题面要求。
- **动作**：Agent 必须亲自通读所有可读材料，提炼关键事实、数字、术语、周期、经费、样本量、条件等；逐字摘录引文 `quote` 与来源定位（`source_id`、`locator`）；将研究背景缺口、研究问题、目标、技术路线、阶段计划、风险、预期成果一一对应到材料证据；将不确定或材料不足项写入 `pending_human`。然后把完整的分析结果写入 `/app/work/draft.json`（结构见 §4）。
- **重要禁止**：不得将 `init` 生成的 partial `result.json` 当最终交付；不得直接把 `references/plan-template.md` 的模板块拼接成 `proposal.md` 而不依据材料证据；不得编写材料外的新数字、新文献或新结论，新增计划值必须标注“计划值”。
- **输出**：`/app/work/draft.json`，包含七要素全部内容与证据映射；或如果时间极度紧张，可写 `/app/work/draft.md`（七个小节标题），但状态必须为 `partial`。
- **失败分支**：
  - 材料无文本 → `insufficient_evidence`，用模板生成完整骨架并写明限制。
  - 关键字段缺失 → 写入 `pending_human` 并说明缺什么、何时补。
  - 时间不足 → 先落盘最小 draft.json 并标记 `partial`，随后进入第 5 步直接 build。

### 第 4 步：校验与成稿

- **输入**：`/app/work/draft.json` 或 `/app/work/draft.md`。
- **动作**：
  1. 运行校验命令：
         python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
  2. Agent 根据 `check` 报告修正 `draft.json`（优先修高权重项：七要素、周期相容、证据命中率、风险完整性）。
  3. 运行成稿命令，生成全套最终交付物：
         python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
- **输出**：`/app/output/` 下所有交付物（proposal.md、proposal_matrix.json、milestones.csv、risks.md、result.json、golden_standard.json、diff_report.md、version_history.md、run.log、self_check.json）。
- **失败分支**：`build` 失败 → 运行 `audit` 重算资产；仍失败则脚本兜底生成最小合法 `result.json`，Agent 记录 `errors` 并标注 `partial`。

### 第 5 步：rubric 自检与增强

- **输入**：`build` 产出的所有文件。
- **动作**：Agent 对照第 6 节 rubric 对照表逐项检查；如有缺漏，回到 `draft.json` 补充后重新执行 `check`/`build`；同时进行可核验增强——抽查关键论断、数字、引用的原文一致性，把核验结果写入 `result.json` 的 `verified`/`pending_human`/`conflicts` 字段。
- **完整性优先**：逐项核对「output_contract 字段列表 × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐再收尾；`partial` 状态必须列出缺失项。
- **输出**：最终高质量产物和增强后的 `result.json`。
- **失败分支**：时间不足则保留 `partial` 并清楚列出缺失项；不删除、不篡改任何已生成基线产物。

### 第 6 步：回填 result.json 与最终落盘

- **输入**：所有最终产物。
- **动作**：运行重算命令：
      python3 /skills/weekly-skill/scripts/main.py audit --input /input --output /app/output --work /app/work
  确保 `result.json` 包含原 `output_contract` 全部字段且键名不改，值符合语义；确保 `self_check.json` 的 `checks` 全部为 true 或每个 false 都有原因；确保所有文件在 `/app/output`。
- **输出**：最终 `result.json`，退出码 0。
- **失败分支**：任何异常均写入 `result.json.errors`/`degradations`，仍退出码 0。

---

## 3. 预算策略（64 次模型请求 / 900 秒）

| 阶段 | 建议请求数 | 必须/可跳过 | 说明 |
|---|---|---|---|
| 第 1 步 init | 1 | 必须 | 一次到位，生成索引和 partial result。 |
| 第 2 步解析检查 | 0–3 | 必须 | 只在提取质量可疑时用 `show` 回看，不要反复全文读。 |
| 第 3 步写 draft.json | 8–20 | 必须 | 每个材料读一次，提炼证据写 draft.json；多材料可合并读取。 |
| 第 4 步 check + 修正 | 2–6 | 必须 | check 一次得到全部问题，批量修改后再次 build，不要反复 check。 |
| 第 4 步 build | 1–2 | 必须 | 无论多不完美都要先 build 出一套完整基线。 |
| 第 5 步 rubric 自检增强 | 2–5 | 可跳过部分 | 时间充足则做；不足则保留 partial 并列出缺失。 |
| 第 6 步 audit | 1 | 必须 | 重算资产，确保一致性。 |
| 异常/查证余量 | 5–10 | 保留 | 用 `show` 查证引文、处理降级。 |

**关键原则**：
- **先落盘 honest partial**：第 3 步完成后立即 `build`，不要等完美才成稿。
- **增量改进**：若 check 报告多，优先修高权重项（七要素、周期相容、证据命中率），低权重问题可进 `pending_human`。
- **避免浪费**：不要无意义循环、不要重复读取同一材料全文、不要用 `show` 查看无关大段。
- **超时保护**：>780 秒直接 `build` 收尾，不再启动新的大动作；所有现有文件保持不变。

---

## 4. 工作稿 `draft.json` 结构（Agent 唯一必写文件）

      {
        "title": "…",
        "period": {"total": "24 个月", "quote": "执行期：24 个月", "source": "M1/p2"},
        "rqs": [{
          "id": "RQ1",
          "question": "…能否…（含对象与条件）",
          "hypothesis": "可被数据否定",
          "falsifier": "若…观测出现则假设被否定",
          "metrics": [{"name": "200 h 保持率", "threshold": "≥85%", "basis": "M4/p1"}],
          "sample": "12 例", "condition": "0.1 M 恒电位", "timepoint": "第 12 月",
          "evidence": [{"source_id": "M1", "locator": "p4", "quote": "逐字原文"}]
        }],
        "sections": [{
          "id": "background|problem|objectives|methods|plan|risks|outcomes",
          "blocks": [{"text": "正文", "evidence": [{"source_id": "M1", "locator": "p3", "quote": "逐字原文"}]}]
        }],
        "objectives": [{"id": "O1", "rq": "RQ1", "objective": "…", "criterion": "可检查判据"}],
        "steps": [{"id": "S1", "rq": "RQ1", "input": "…", "action": "…", "output": "…", "depends_on": []}],
        "resources": {"budget": "45 万元（M1/p2）", "people": "…", "data": "…", "note": "…"},
        "milestones": [{"id": "MS1", "period": "第 1–6 月", "task": "…（S1）", "deliverable": "…", "depends_on": "—", "criterion": "…", "critical_path": true}],
        "risks": [{"id": "R1", "type": "数据获取|方法可行性|进度|伦理与合规", "risk": "…", "trigger": "可观测信号+时点", "impact": "…", "fallback": "…", "decision_point": "…"}],
        "outcomes": [{"id": "D1", "rq": "RQ1", "outcome": "…", "verification": "怎么复跑", "criterion": "…"}],
        "preserved_facts": [{"term": "执行期", "value": "24 个月", "source_id": "M1", "locator": "p2", "quote": "…"}],
        "change_log": [{"action": "起草", "target": "proposal.md", "reason": "…", "before": "—", "after": "v1"}],
        "pending_human": [{"item": "阈值 ≥15%", "why": "材料未给", "needed_by": "答辩前"}]
      }

也可只写 `/app/work/draft.md`，用七个小节标题（`## 一、研究背景与缺口` … `## 七、预期成果与验证方式`）；此时状态必为 `partial`，且 `build` 会尽力解析。

---

## 5. 质量规则（对齐评分点）

1. **立得住**：每个 RQ 的 `question` 含对象+条件；`falsifier` 写清什么观测会否定它；每个 `metric` 有 `threshold` 与 `basis`。
2. **对得上**：目标 `rq` 指回 RQ；`steps.output`/`depends_on` 串成技术路线；`outcomes.verification` 说明怎么复跑。
3. **排得开**：里程碑必须落在材料给的周期内（超期判错）；每条有 `criterion`；标关键路径。
4. **说得清**：风险 ≥4 条、≥3 类，每条有 `trigger`、`fallback`、`decision_point`；引文 `quote` 逐字命中材料。
5. **不越界**：材料外的数字/文献/结论一律不写；计划新增值标“计划值”；缺口进 `pending_human`；不把设想写成结果。

---

## 6. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 评分点及分值 | 交付要求 | 自证方式 |
|---|---|---|---|---|
| 实际效果 | 40 | 任务完成度 15 | 交付研究背景、问题定义、目标、技术路线、阶段计划、风险、预期成果七要素齐全、与给定周期和资源相容的开题方案。 | `proposal.md` 七节齐全；`check` 报告要素覆盖为 true；`self_check.json` 中 `seven_sections` 通过。 |
| | | 结果正确性 15 | 事实、数据、引用、专业判断和计划口径准确；论断与引用一一对应，指标阈值有依据。 | `evidence_map` 每条论断有 `source_id`+`locator`+`quote`；`check` 中数字一致性、引文命中率 ≥90%；`pending_human` 列出无依据项。 |
| | | 结果完整性 5 | 七要素、风险类型、预期成果考核方式齐全，边界写明。 | `risks.md` 和 `draft.json` 中风险 ≥4 条、≥3 类；`outcomes` 有 `verification`；`result.json` 的 `coverage` 字段。 |
| | | 结果可核验性 5 | 每个论断能定位到输入材料、引用与版本。 | `evidence_map`、`preserved_facts`、`golden_standard.json` 的锚点均可 `show` 回查原文。 |
| 使用增益 | 25 | 质量增益 15 | 相比基础 Agent 提升开题方案质量。 | `diff_report.md` 展示金标准 27 条 vs 实际产物逐项 pass/missing；`result.json` 的 `runtime` 记录增强轨迹。 |
| | | 效率增益 5 | 减少大纲搭建、章节重写、往返修改和材料核对工作量。 | `version_history.md` 显示从 v0 骨架到 v1 成稿的快速路径；`run.log` 记录时间。 |
| | | 增益可验证性 5 | 通过公平对照证明质量或效率改善。 | `self_check.json` 的 `overall_pass` 和 `checks` 记录内部对照；`result.json.counts` 列请求数、耗时。 |
| 创新增益 | 15 | 新增能力 5 | 形成基础 Agent 不具备或难以稳定的自检与证据核验能力。 | `golden_standard.json` 提供 G01–G27 判据；`self_check.json` 自动化核对。 |
| | | 方法改进 5 | 约束抽取、要素对齐、计划可行性校验等方法带来实质改进。 | `check` 的周期相容、数字一致、引文逐字比对规则；`diff_report.md` 的 rule 映射。 |
| | | 创新证据 5 | 证明创新点相对已有方案的边界和价值。 | `version_history.md` 说明 v2 新增资产；`pending_human` 记录边界；文档 §10 维护说明。 |
| 可靠体验 | 10 | 调用与易用性 3 | 正确触发，模糊请求下先索要课题指南、周期、经费与数据条件。 | 本 SKILL 第 1-2 节明确输入契约；`init` 打印 `NEXT: write draft.json` 提示。 |
| | | 运行稳定性 4 | 不同学科、篇幅、重复运行下要素不漂移、目标数量与周期经费前后一致。 | 纯标准库脚本，无外部依赖；`run.log` 跨命令累积；`audit` 重算结果一致。 |
| | | 异常处理 3 | 材料缺失、周期过短、指标不可达、文献无法获取等识别与处置。 | §7 降级策略；`errors`/`degradations`/`pending_human` 字段；退出码恒 0。 |
| 生态贡献 | 10 | 文档完整性 3 | 使用说明、依赖、要素清单、示例、