---
name: academic-talk-organizer
description: 把论文/研究材料组织成可上台的学术汇报：按听众、时长、页数生成逐页主张与要点、真实可编辑的 pptx（含逐页讲稿备注）、逐页证据映射（locator + 逐字 quote）、页数与版式合规检查，并导出 PDF 预览。适用于组会/答辩/评审等“从材料到可讲页面”的任务；不适用于论文精读、成稿写作或科研绘图本身。Harness Agent 必须亲自读材料、推导、撰写并审校交付物，脚本只做解析/校验/渲染。
version: 1.2.0
---

# 学术汇报内容组织（academic-talk-organizer）

## 0. 最高优先级声明（必须逐字执行）

本 Skill 的脚本只是工具，用于解析、校验、渲染与审计。**最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作并审校**。禁止把脚本骨架、模板或 init 产出直接当成品。

工作顺序必须是：先运行脚本产出**全套基线交付物**（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段），完整保留；再在基线上做真实核验与增强。不得删除、清空或遗漏任何基线产物与契约字段。若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。

## 1. 用途与边界

把**已有**研究材料（PDF/DOCX/MD/TXT/CSV/XLSX/PPTX）转成一份可上台的学术汇报：页级主张、要点、讲稿、证据定位、可编辑 pptx、PDF 预览。

- **做**：内容取舍、叙事顺序、页级组织、图表引用绑定、模板/母版适配、导出与合规检查。
- **不做**：论文精读与翻译、论文成稿写作、科研绘图本身、编造数据或参考文献。
- **不适用**：材料为空或全部为图像且无文字层时，只能给缺口页，不能生成“看似完整”的科学内容。

## 2. 运行时契约（评测实际路径）

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下材料（递归） |
| 工作区 | `/app/work`（本 Skill 写 `materials.json`、`index.md`、`slide_plan.json`、`check_report.json`） |
| 产物 | `/app/output/`：`presentation.pptx`、`preview.pdf`、`slide_plan.md`、`content_map.json`、`compliance_checks.json`、`result.json`，以及 5 个核验资产（见第 12 节） |
| 依赖 | Python 3 标准库；不联网；不依赖 CWD。`soffice/libreoffice`、`pdftotext` 可选，缺失自动降级 |
| 退出码 | 恒 0；任何异常都写进 `result.json.errors` |
| 预算 | 64 次模型请求 / 900 秒；单次响应 16384 tokens（含推理）；脚本内部约 5 秒 |

`result.json` 必须**原样回填** `output_contract` 的**全部字段**（键名不改，缺值用 `null`/`[]`），并包含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`deliverables`、`reviewed_by_agent`，以及 `golden_standard`、`diff_report`、`version_history`、`self_check` 四个核验字段（路径+计数，文件见第 12 节）。

可编辑 Office/幻灯片/图形产物必须额外给出**真实渲染的 PDF/PNG 预览**。本 Skill 默认生成 `preview.pdf`；若输出图形类可编辑产物，需用相同方式生成 PNG 预览并写入 `output_contract` 对应字段。

## 3. 执行流程（编号步骤，每步都要完成）

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input/` 下所有材料文件。
- **动作**：
  1. 读 `/input/case.json`，提取 `case_id` 与 `output_contract` 的**全部字段**（键名严格保留，不得增删改）。
  2. 读 `/input/task.md`，提取 audience、duration、slide_count、模板要求、评分侧重点等约束。
  3. 递归列出 `/input/` 下所有材料路径（PDF/DOCX/MD/TXT/CSV/XLSX/PPTX/图片等），形成材料清单。
- **输出**：`case_id`、`output_contract` 字段列表、材料路径列表、任务约束摘要。
- **失败分支**：`case.json` 缺失或坏 JSON → 使用最小默认契约字段（如 `slide_plan/presentation_file/content_map/compliance_checks/preview/coverage`），状态标 `input_error/partial`，继续执行；材料清单为空 → 记录 `input_error`，进入兜底生成最小合法 `result.json`，退出 0。

### 步骤 2：真实解析材料

- **输入**：材料文件路径列表。
- **动作**：
  1. 对每个文件按类型真实解析：PDF 用 `pdftotext` 或平台提供的 pdf-text-tool 提取文字层；DOCX 解压读取 `document.xml` 转纯文本；CSV/XLSX 读取单元格；MD/TXT 直接读取；PPTX 抽取文本。**必须读到原文内容，不得依据文件名或领域标签猜测/补造数据。**
  2. 运行 `python3 /skills/weekly-skill/scripts/main.py init`，生成 `/app/work/materials.json` 和 `/app/work/index.md`，把解析出的文本按材料、段落编号成 locator（如 `M1#p12`）。
  3. 用 `python3 /skills/weekly-skill/scripts/main.py show --grep '<关键词>'` 抽查至少 3 处原文，确认 locator 与文本一致；后续引用源文本必须来自 `show` 输出。
- **输出**：`/app/work/materials.json`、`/app/work/index.md`，真实文本与 locator 映射。
- **失败分支**：某文件损坏、无文字层（扫描件/图片 PDF）、格式不支持 → 该材料记入 `errors/degradations`，其他材料继续；全部材料不可读 → 只生成缺口页，状态 `input_error/partial`，写最小合法 `result.json` 并退出 0。

### 步骤 3：构建页级计划并核对证据

- **输入**：材料文本、`hints`（audience/duration/slides）、`task.md` 要求。
- **动作**：
  1. 按 `references/organizing_rules.md` 和 `references/slide_plan_schema.md`，由你亲自确定报告目标、听众定位、叙事顺序、每页唯一主张、要点、图表引用与问答准备。
  2. 手写 `/app/work/slide_plan.json`（结构见第 4 节）。每条要点必须带 `locator` 和逐字 `quote`；`quote` 必须与原文**逐字一致**。
  3. 运行 `python3 /skills/weekly-skill/scripts/main.py check` 校验。若 FAIL，依据返回的未匹配项修改 plan 或重新选 quote，**不得改写原文、不得补造数据**。
- **输出**：`/app/work/slide_plan.json`、`/app/work/check_report.json`（含 `quotes_checked`、`quotes_verified`、`usable`）。
- **失败分支**：quote 反复无法验证或要点数不符 → 修改 plan 重跑；仍失败则使用脚本确定性兜底计划（每页 3–5 条、带 locator+quote），但需注明高质量判断缺失。

### 步骤 4：产出完整成品并保留基线

- **输入**：通过 `check` 的 `/app/work/slide_plan.json`。
- **动作**：
  1. 运行 `python3 /skills/weekly-skill/scripts/main.py build`，生成 `/app/output` 全套基线：`presentation.pptx`、`preview.pdf`、`slide_plan.md`、`content_map.json`、`compliance_checks.json`、`result.json` 及第 12 节核验资产。
  2. **确认基线完整存在且非空**：每个 `output_contract` 字段都有对应文件或值；`presentation.pptx` 可打开；`preview.pdf` 页数正确。
  3. 你亲自审阅生成内容：页标题是否结论化、要点是否支持页面主张、`notes` 是否新增讲解信息而非复述、证据强度是否匹配、模板页数是否符合要求。发现问题就修改 `slide_plan.json` 后重跑 build，但**不得删除已存在的基线产物**。
- **输出**：完整基线交付物。
- **失败分支**：`build` 失败或部分文件缺失 → 保留已生成部分，记录 `errors/degradations`，用已解析材料生成最小合法 `result.json`；不得因 build 失败返回非 0 或删除已有文件。

### 步骤 5：自检 rubric 与一致性核验

- **输入**：`/app/output` 下所有产出文件。
- **动作**：
  1. 按第 10 节 rubric 对照表逐项核对，确保交付物覆盖考察点。
  2. 对关键数字、结论、图表引用做来源一致性核验：用 `show --grep` 复核关键 quote，确认没有改写、拼接或补造。把核验结果写入 `result.json` 的 `verified` / `pending_human` / `conflicts` 字段，并标注 `reviewed_by_agent: true`。
  3. 运行 `python3 /skills/weekly-skill/scripts/audit.py` 生成或刷新 `golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json`（若 `build` 已自动生成则核对内容）。保留全部基线，不准删除或清空。
- **输出**：核验字段、自检记录、差异报告。
- **失败分支**：发现不一致或缺口 → 能修的改 `slide_plan.json` 重跑；不能修的写 `pending_human`/`limitations`，状态降为 `partial` 但仍写完整 `result.json`。

### 步骤 6：回填并终检 result.json

- **输入**：全部产物与状态。
- **动作**：
  1. 确保 `/app/output/result.json` 包含 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`deliverables`、`reviewed_by_agent`，以及原 `output_contract` 全部字段（键名不变，值指向实际产物路径或 `null`/`[]`）。
  2. `status` 与真实完成度一致：`complete` / `partial` / `input_error`。诚实记录：哪些内容由脚本生成、哪些由你亲自核验、哪些待人工补充。
  3. 检查 `result.json` 可被 JSON 解析；检查 `presentation.pptx` 与 `preview.pdf` 页数一致；确保退出码 0。
- **输出**：合法 `result.json`。
- **失败分支**：JSON 损坏 → 用最小合法结构重建，退出 0；任何异常都不得以非 0 退出。

## 4. `work/slide_plan.json` 结构（本 Skill 输入契约）

```json
{
  "deck_title": "总标题",
  "subtitle": "副标题",
  "audience": "听众（如：课题组组会 / 答辩评委）",
  "duration_min": 12,
  "target_slides": 8,
  "goal": "这次汇报要达成的可检查目标",
  "narrative": [{"act": "动机", "slides": "2-3", "purpose": "建立共识"}],
  "slides": [
    {"n": 1, "title": "标题页", "layout": "title", "subtitle": "副标题", "bullets": [],
     "notes": "开场 30 秒说什么"},
    {"n": 2, "title": "页标题（一句话结论）", "claim": "本页唯一主张",
     "bullets": [{"text": "听众能听懂的要点", "locator": "M1#p12",
                  "quote": "源材料中逐字出现的一段原文"}],
     "visual": "用哪张图/表；无图则写'无'", "evidence_strength": "strong|moderate|weak",
     "notes": "讲解口径：先给什么、被追问时先答什么"}
  ],
  "qa": [{"q": "可能的追问", "a": "口径一致的回答", "backup": "备用页/页码"}]
}
```

字段规则：每张内容页 **3–5 条** `bullets`；每条至少给 `quote`（逐字）或 `locator`；`notes` 必须**新增信息**（讲法、条件、风险），不能复述页面文字；`layout: "title"` 仅用于首页。

## 5. 内容组织规则（评分核心）

1. **从约束反推结构**：先读 `init` 输出的 `hints`（audience/duration/slides）。无页数要求时按 `1 页 ≈ 1.2–1.5 分钟` 估算并写入 `target_slides`。
2. **听众决定取舍**：组会→方法与进度、风险优先，背景 1 页；答辩/评审→创新点与边界，证据强度优先。术语只解释听众可能不懂的。
3. **叙事不按论文目录搬运**：问题 →（为什么现有做法不够）→ 方法 → 关键结果 → 边界与结论；每页回答一个问题。
4. **页标题写结论，不写章名**：`"Top-1 从 31.4% 到 46.8%"` 优于 `"结果"`。
5. **数字只在源材料里有理**：百分比、样本量、时长、p 值必须能在 `quote` 中逐字找到；跨页引用同一数字要口径一致。
6. **证据强度**：单数据集/单模型/无对照 → `moderate` 或 `weak