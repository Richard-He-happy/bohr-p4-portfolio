---
name: proposal-writing
description: 面向开题报告与研究计划书的可核验写作 Skill；读取 /input 原始材料与输出契约，生成七要素 proposal.md、证据映射、里程碑、风险和 result.json。Agent 通过 draft.json 表达判断，脚本提供确定性兜底、校验与产物渲染；所有事实和数字必须带来源定位，材料缺失或冲突如实标注，不编造数据。
version: 4.0.0
---

# proposal-writing：开题报告与研究计划书

## 0. 最高优先级

1. **先交完整基线，再做增量增强。** 绝不因追求完美导致 `/app/output` 缺文件、`result.json` 缺字段或进程非 0 退出。
2. **Agent 亲自读原始材料。** 不依据文件名、领域标签或错误元数据补造内容；PDF 解析读实际 PDF，不假设已有抽取层。
3. **所有关键数字、术语、引用、论断都必须可定位。** 标记为 `[S#/locator]`，并在证据文件中给出逐字 `quote`。
4. **结构化产物由脚本生成，Agent 不手改 JSON 结构。** Agent 的主要判断写入 `/app/work/draft.json`；脚本负责校验、渲染和审计。
5. **材料不足、冲突、人工确认项必须显式登记。** 写入 `gaps`/`conflicts`/`pending_human`/`uncertainty`。
6. **不编造评测分数、金标准、基准或材料外科学数据。** 不生成 `golden_standard.json`、`diff_report.md` 或加权自评分。
7. **任何情况下退出码为 0。** 异常写入 `errors`/`degradations`，`result.json` 仍合法。

---

## 1. 触发与调用方式

### 1.1 单命令全流程入口（首选）

```bash
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input \
  --output /app/output \
  --work /app/work
```

`run` 内部应完成：

- `init`：盘点 `/input` 全部材料、生成来源台账、候选抽取、冲突分组。
- 若 `/app/work/draft.json` 存在：`check` → 按报告修正 → `build`。
- 若 `/app/work/draft.json` 不存在：直接 `build`，由确定性兜底抽取生成实质工作稿。
- 最后执行 `selfcheck`/`audit`，补齐 `result.json` 与自检记录。

### 1.2 等价回退命令

若当前脚本版本不提供 `run`，必须按顺序执行以下命令，效果与 `run` 一致：

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
# Agent 阅读材料并写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/main.py audit --input /input --output /app/output --work /app/work
```

可选查看原文与台账：

```bash
python3 /skills/weekly-skill/scripts/main.py show --work /app/work --source S1 --locator p3
```

---

## 2. 输入、输出与运行环境

### 2.1 输入

- `/input/case.json`：含 `case_id`、`task_instruction`、`output_contract`，可能含 `organizer_workorder`。
- `/input/task.md`：题面任务与评分/运行约定。
- `/input/**`：实际科研材料，可能是 PDF、DOCX、TXT、MD、CSV、图片等。

### 2.2 工作区

- `/app/work/index.json`：来源台账。
- `/app/work/draft.json`：Agent 工作稿，或兜底工作稿。
- `/app/work/draft.effective.json`：实际用于 build 的有效稿。
- `/app/work/check_report.json`：校验报告。
- `/app/work/agent_review.json`：Agent 核验记录。

### 2.3 最终产物

必须落入 `/app/output/`：

| 文件 | 用途 |
|---|---|
| `proposal.md` | 可编辑成稿；七要素齐全，带 `[S#/locator]` 证据标记 |
| `proposal_matrix.json` | RQ→目标→步骤→里程碑→风险→成果映射 |
| `milestones.csv` | 阶段计划表，可被表格工具继续编辑 |
| `risks.md` | 风险登记表：类型、触发信号、影响、备选方案、决策时点 |
| `evidence_map.json` | 论断到来源、定位、逐字引文的映射 |
| `preserved_facts.json` | 数字、条件、术语、来源与版本 |
| `change_log.json` | 修改动作、原因、前后版本、人工确认项 |
| `self_check.json` | 自动化自查结果 |
| `run.log` | 命令/时间/请求次数轨迹 |
| `result.json` | 最终结构化结果，双回显 `output_contract` |

### 2.4 运行环境

- Python 3.8+，仅标准库，离线运行。
- 不依赖当前工作目录；路径用 `Path(__file__)` 定位。
- 包内文件满足 50 个文本文件 / 单文件 500KB / 总 2MB 限制，无 symlink。
- 中英文自适应：输入为英文时输出英文标题与正文；中文时输出中文；专业术语和原文引用不擅自翻译。需要双语时保留原文并给出译文。

---

## 3. 双路径执行流程

### 路径 A：Agent 路径（优先，质量更高）

1. **运行 `init`。** 生成 `/app/work/index.json`，包含每个来源 `S1..Sn` 的路径、类型、字数、段数、抽取状态、识别到的周期/经费/样本约束。
2. **检查台账与抽取质量。** 发现乱码、漏段、无法抽取的 PDF 页面时，用 `show` 回看关键段；图片不 OCR，记录 `no_ocr`，不猜测像素内容。
3. **完整阅读材料。** 提炼事实、数字、术语、约束、已知结论与缺口。逐字摘录 `quote` 并标注 `source_id` 与 `locator`。
4. **写 `/app/work/draft.json`。** 按第 4 节 schema 填写七要素及证据映射。计划新增值标为“计划值”，材料未给出的阈值或条件写入 `pending_human`。
5. **运行 `check`。** 根据报告优先修复高权重问题：七要素缺失、周期/经费不相容、引文不命中、目标与问题不对齐、风险类型不足。
6. **运行 `build`。** 生成全套产物。
7. **运行 `audit`。** 核对 `output_contract` 字段、磁盘文件、`result.json` 键三方一致。

### 路径 B：无 `draft.json` 时的确定性兜底（必须成功）

当时间不足、材料极少或 Agent 未写 `draft.json` 时，`build` 必须自动执行：

- 从 `index.json` 提取来源台账；
- 从材料中做确定性基础抽取：标题、执行周期、经费、样本、数据条件、关键数字和可识别术语；
- 按 `task_instruction` 与题面七要素要求生成实质工作稿骨架；
- 对每个可写内容只引用逐字原文；无法可靠推导的研究判断不编造，写入 `pending_human`；
- 在 `result.json.degradations` 中记录 `AUTO_EXTRACT`，状态不得为 `ok`，应为 `partial` 或 `degraded`；
- 产物与 Agent 路径完全同一套文件与契约。

---

## 4. `draft.json` 结构

Agent 唯一必须写好的文件是 `/app/work/draft.json`。

```json
{
  "case_id": "原样保留输入 case_id",
  "title": "开题报告标题，应体现对象、问题与条件",
  "language": "zh 或 en",
  "period": {
    "total": "24 个月",
    "quote": "执行期：24 个月",
    "source_id": "S1",
    "locator": "p2"
  },
  "rqs": [
    {
      "id": "RQ1",
      "question": "具体、可证伪，含对象与条件",
      "hypothesis": "可被数据否定的假设",
      "falsifier": "出现什么观测/结果会否定该假设",
      "metrics": [
        {"name": "200 h 保持率", "threshold": "≥85%", "basis": "S4/p1"}
      ],
      "sample": "12 例",
      "condition": "0.1 M 恒电位",
      "timepoint": "第 12 月",
      "evidence": [
        {"source_id": "S1", "locator": "p4", "quote": "逐字原文"}
      ]
    }
  ],
  "sections": [
    {
      "id": "background|problem|objectives|methods|plan|risks|outcomes",
      "blocks": [
        {
          "text": "正文段落",
          "evidence": [
            {"source_id": "S1", "locator": "p3", "quote": "逐字原文"}
          ]
        }
      ]
    }
  ],
  "objectives": [
    {
      "id": "O1",
      "rq": "RQ1",
      "objective": "可考核目标",
      "criterion": "检查判据：指标、样本、对照、时间点"
    }
  ],
  "steps": [
    {"id": "S1", "rq": "RQ1", "input": "输入", "action": "动作", "output": "输出", "depends_on": []}
  ],
  "resources": {
    "budget": "45 万元（S1/p2）",
    "people": "人员条件",
    "data": "数据条件",
    "note": "未给出的资源约束写 pending_human"
  },
  "milestones": [
    {
      "id": "MS1",
      "period": "第 1–6 月",
      "task": "阶段任务（映射到 step id）",
      "deliverable": "阶段交付物",
      "depends_on": "—",
      "criterion": "完成判据",
      "critical_path": true
    }
  ],
  "risks": [
    {
      "id": "R1",
      "type": "数据获取|方法可行性|进度|伦理与合规",
      "risk": "风险描述",
      "trigger": "可观测触发信号 + 时点",
      "impact": "影响范围",
      "fallback": "备选方案",
      "decision_point": "决策时点"
    }
  ],
  "outcomes": [
    {
      "id": "D1",
      "rq": "RQ1",
      "outcome": "预期成果",
      "verification": "如何复跑/核验",
      "criterion": "考核方式"
    }
  ],
  "preserved_facts": [
    {"term": "执行期", "value": "24 个月", "source_id": "S1", "locator": "p2", "quote": "..."}
  ],
  "change_log": [
    {"action": "起草", "target": "proposal.md", "reason": "基于材料形成初稿", "before": "—", "after": "v1"}
  ],
  "pending_human": [
    {"item": "阈值 ≥15%", "why": "材料未给出依据", "needed_by": "答辩前"}
  ],
  "conflicts": [
    {"item": "两组样本量不一致", "sources": ["S1/p2", "S4/p3"], "resolved": false}
  ]
}
```

若时间严重不足，可只写 `/app/work/draft.md`，用七个小节标题：`## 一、研究背景与缺口` 到 `## 七、预期成果与验证方式`。此时状态必须为 `partial`，`build` 会做尽力解析并登记降级。

---

## 5. 七要素质量规则

1. **研究背景与缺口：** 写“已知—未知—待验证”，不得写成文献综述罗列。每个背景判断都要指向材料。
2. **问题定义：** 收敛为 1–3 个可回答、可证伪的问题；每个 RQ 含对象、条件、假设、否定条件。
3. **目标与判据：** 每个目标指回相应 RQ；写清指标、样本、对照、时间点，阈值有依据。
4. **技术路线：** 步骤串成有输入输出和依赖关系；与目标一一对应，不各写各的。
5. **阶段计划：** 里程碑必须落在材料给定周期与资源内；每条有交付物、完成判据、关键路径。
6. **风险与备选方案：** 不少于 4 条、覆盖至少 3 类（数据获取、方法可行性、进度、伦理与合规）；每条有触发信号、影响、备选方案、决策时点。
7. **预期成果与验证方式：** 每个成果指回 RQ；写清考核方式与复跑方法。

---

## 6. `result.json` 契约与双回显

`result.json` 必须是合法 JSON，顶层与 `output_contract` 中同时保留原始契约字段，且不改变原始键名。

```json
{
  "case_id": "原始 case_id",
  "status": "ok|partial|degraded|insufficient_evidence|input_error",
  "sources": [
    {"source_id": "S1", "path": "/input/xxx.pdf", "type": "pdf", "chars": 12345, "extraction": "ok"}
  ],
  "artifacts": {
    "proposal": "proposal.md",
    "matrix": "proposal_matrix.json",
    "milestones": "milestones.csv",
    "risks": "risks.md",
    "evidence_map": "evidence_map.json",
    "preserved_facts": "preserved_facts.json",
    "change_log": "change_log.json",
    "self_check": "self_check.json"
  },
  "coverage": {
    "seven_sections": true,
    "risk_categories": 4,
    "evidence_hit_rate": 0.93,
    "missing_required_items": []
  },
  "uncertainty": [
    "材料未给出伦理批件要求，按 pending_human 处理"
  ],
  "pending_human": [
    "阈值 ≥15% 的依据缺失"
  ],
  "errors": [],
  "degradations": [
    "AUTO_EXTRACT: 未提供 draft.json，脚本确定性兜底生成"
  ],
  "deliverable": "proposal.md",
  "preserved_facts": "preserved_facts.json",
  "evidence_map": "evidence_map.json",
  "change_log": "change_log.json",
  "output_contract": {
    "case_id": "原始 case_id",
    "deliverable": "proposal.md",
    "preserved_facts": "preserved_facts.json",
    "evidence_map": "evidence_map.json",
    "change_log": "change_log.json"
  }
}
```

若 `/input/case.json` 的 `output_contract` 还有额外字段，必须原样透传，并在顶层同步相同键名。不得改写、删除或替换为自造字段。

---

## 7. 证据与引用规范

- 来源编号统一使用 `S1..Sn`；若 `init` 台账使用 `M1..Mn`，以台账输出的 `source_id` 为准。
- `locator` 格式：
  - PDF：`p3` 或 `p3/para2`
  - DOCX：`para12` 或 `section2/para4`
  - TXT/MD：`line8`
- `proposal.md` 中的关键论断使用 `[S1/p3]` 或 `[S1/para12]` 标记；读者可在 `evidence_map.json` 找到逐字 `quote`。
- `evidence_map.json` 至少包含：`claim_id`、`claim`、`source_id`、`locator`、`quote`、`strength`（`direct`/`inferred`/`planned`）。
- 数字、术语、引用不得新增。材料没有但计划必须新设的值，标为“计划值”并写入 `pending_human`。
- 冲突数字同时列出多个来源，不在未核实情况下强行选择。

---

## 8. 失败与异常处理

| 情况 | 处理 |
|---|---|
| `/input/case.json` 缺失或坏 JSON | 递归寻找 `case*.json`/`input*.json`；仍失败则状态 `input_error`，继续生成合法 `result.json` |
| 无任何材料或材料无文本 | 状态 `insufficient_evidence`；仍生成七要素骨架并说明限制；不得编造研究事实 |
| PDF/DOCX 解析失败 | 跳过该材料并在 `sources` 中标记 `extraction_failed`；继续处理其他材料 |
| 材料冲突 | 写入 `conflicts` 与 `uncertainty`；在正文中使用保守表述并保留双方来源 |
| 周期过短、指标不可达、资源不足 | 在 `pending_human` 明确写出缺什么、何时补、备选路径 |
| 引用无法获取 | 删除该来源判断，写入 `degradations`；不得用文件名或领域标签猜测 |
| 脚本任一步骤异常 | 记录 `errors`/`degradations`，执行兜底渲染，仍退出 0 |
| 超过 780 秒或接近 64 次模型请求 | 立即 `build`/`audit`，保留现有产物并标注 `partial` |

---

## 9. 模型请求预算策略

- `init`：1 次请求。
- 材料抽取质量核验：0–3 次，仅在乱码、漏段时回看。
- 精读与写 `draft.json`：5–15 次，按材料数量和长度压缩；每个材料读一次，避免反复全文读取。
- `check` + 修正：2–5 次。
- `build`：1–2 次，无论多不完整先产出基线。
- `audit`/`selfcheck`：1 次。
- 保留 5–10 次应对查证、冲突、格式修复。
- 接近 50 次请求或 700 秒时，只做 `build` + `audit`，不再启动新的全面阅读。

---

## 10. rubric 自检清单（结束前逐项核对）

| 维度 | 必须可查的证据 |
|---|---|
| 实际效果 | `proposal.md` 七节齐全；`self_check.json` 显示七要素通过；`evidence_map.json` 每条关键论断可回溯；数字/周期/预算与来源一致 |
| 使用增益 | 单命令 `run` 可在无 draft 时也产出完整基线；`run.log` 显示从 init 到 build 的短路径；`change_log.json` 记录机器抽取与人工判断分流 |
| 创新增益 | `check` 执行周期相容、证据命中、RQ-目标-步骤-成果对齐、风险触发信号等自动化校验；`self_check.json` 保留校验证据；无自造分数 |
| 可靠体验 | 模糊请求下应先索要课题指南、周期、经费与数据条件；材料缺失/冲突/解析失败有明确状态；退出码恒 0 |
| 生态贡献 | 本 SKILL.md 即是完整调用说明；`references/plan-template.md` 仅作版式模板复用；`proposal_matrix.json`、`milestones.csv`、`risks.md` 可直接二次编辑 |

---

## 11. 禁止事项

1. 禁止手改 `result.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json` 的结构键。
2. 禁止把 `init` 的 partial `result.json` 直接当最终结果。
3. 禁止只拼接模板而不阅读材料。
4. 禁止新增材料外文献、数字、结论或领域标签。
5. 禁止声称有 benchmark 分数、金标准或公平对照评分。
6. 禁止生成 `golden_standard.json`、`diff_report.md` 或加权自评分。
7. 禁止因某材料解析失败而放弃整体交付。
8. 禁止在 `result.json` 中使用非 UTF-8、NaN、Infinity 或注释。