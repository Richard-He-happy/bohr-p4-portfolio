---
name: academic-talk-organizer
description: 把 /input 中已有论文/研究材料组织成可上台的学术汇报：按听众、时长、页数生成页级主张、要点、讲稿备注、页级证据映射与真实可编辑 pptx，并导出 PDF/PNG 预览；内置确定性兜底，任何异常也返回合法 result.json。适用于组会/答辩/评审等“从材料到可讲页面”的任务；不涉及论文精读、写作成稿或科研绘图本身。
version: 2.0.0
---

# 学术汇报内容组织（academic-talk-organizer）

## 0. 最高优先级声明（Agent 必须先读）

本 Skill 的目标不是“生成很多页 PPT”，而是交付一份**可上台、可追溯、可复核**的学术汇报：每个页面上的科学论断都能回到源材料定位；叙事顺序服务听众与时长；从源材料到成稿的取舍过程有记录；可编辑文件与渲染预览都真实存在。

Agent 必须遵守：

1. **真实读取源材料**：不得依据文件名、领域标签或案例标题猜测科学内容。必须解析 `/input` 下真实 PDF/DOCX/MD/TXT/CSV/XLSX/PPTX，并复读关键原文。
2. **不得编造材料缺失的事实**：缺图、无文字层、表格缺失、字体丢失、导出失败等，必须写成 `errors/degradations/pending_human`，不得补造科学数据或伪造来源。
3. **脚本只做工具**：脚本负责解析、候选抽取、校验、渲染、审计。Agent 负责目标判断、叙述取舍、逐页组织、讲稿口径与终稿审校。
4. **禁止手改结构化 JSON 结构**：`claims.json`、`evidence_table.json`、`content_map.json`、`result.json` 的键名与结构字段必须保持脚本输出；Agent 的核验与修正写入 `agent_review.json`，或通过重跑脚本完成。
5. **任何异常也必须 exit 0**：`result.json` 永远合法生成；生成不了完整内容，就生成 partial 内容并诚实声明。
6. **不生成官方评分、白板、金标准或自评分**：不得声称“预计得分”“超过基础 Agent”“benchmark score”。自检只基于真实文件存在性与脚本自检结果。

---

## 1. 用途与边界

### 做什么
- 从已有论文/研究材料提取研究问题、方法、结果、限制，形成主线。
- 按听众、时长、页数设计页级主张、图表引用和讲解顺序。
- 生成可编辑 pptx、逐页讲稿备注、页级证据映射、Q&A 准备。
- 校验模板/页数/母版/字体/导出，并生成真实 PDF/PNG 预览。
- 保留每页内容与源材料的 `[S#]` 来源编号和 `文件#行号/段落号` locator。

### 不做什么
- 不做论文精读翻译、学术写作成稿、科研绘图本身。
- 不在材料缺失时补造图表、数据、参考文献或结论。
- 不覆盖“整个学术 PPT 领域”，只解决本任务中“已有材料 → 可讲页面”的组织与交付问题。

### 不适用情况
- 材料为空或全部为图像且无文字层：只能给出缺口页和 partial 结果。
- 输入没有任务约束、听众或页数要求：使用默认组会 10 分钟、约 8 页的保守设置，并在 `uncertainty` 中注明。

---

## 2. 运行时契约

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下全部材料 |
| 工作区 | `/app/work` |
| 产物 | `/app/output/`：`presentation.pptx`、`preview.pdf`、`slide_plan.md`、`content_map.json`、`claims.json`、`evidence_table.json`、`qa_briefing.md`、`compliance_checks.json`、`agent_review.json`、`result.json` 及题面 `output_contract` 要求的其他文件 |
| 脚本 | `/skills/weekly-skill/scripts/main.py`、`scripts/makeppt.py`、`scripts/audit.py` |
| 依赖 | Python 3.8+ 标准库；离线；不依赖 CWD。`libreoffice/soffice`、`pdftotext` 可选，缺失自动降级 |
| 退出码 | 恒 0；异常只进入 `result.json.errors` |
| 预算 | 64 次模型请求 / 900 秒；单次响应 16384 tokens，含推理 |

---

## 3. 单命令入口与双路径

### 3.1 首选单命令
```bash
python3 /skills/weekly-skill/scripts/main.py run \
  --input /input \
  --output /app/output \
  --work /app/work
```

该命令内部完成：
1. `init`：盘点材料、编号来源、抽取候选 claim/quote、生成台账 `materials.json`、`index.md`。
2. `build`：校验/兜底抽取、组织页面、渲染 pptx、导出 PDF、写全套产物。
3. `selfcheck`：核对 `output_contract` 字段、磁盘文件、`result.json` 三者的对应关系。

### 3.2 Agent-first 双路径

#### Agent 路径（预算允许时优先）
1. 运行 `init` 生成台账。
2. 亲自读 `/input` 材料。
3. 将判断写入 `${WORK}/draft.json`（结构见第 6 节）。
4. 运行 `check`，根据校验结果修改 draft。
5. 运行 `build` 生成成品。
6. 运行 `selfcheck` 做产物自检。

#### 无 draft 时确定性兜底
如果 `draft.json` 不存在或不可用，`build` 必须根据 `init` 台账**确定性抽取**生成实质工作稿。兜底抽取仍须：
- 每页产生 `claim`、`bullets`、逐字 `quote`、`locator`。
- 不生成无来源的页内容。
- 在 `result.json.degradations` 中记录 `AUTO_EXTRACT`。

两条路径产出同一套产物结构与同一份 `result.json` 契约；区别只在 `reviewed_by_agent` 与 `degradations` 是否记录 `AUTO_EXTRACT`。

---

## 4. 标准执行流程

### 步骤 1：盘点输入与契约

```bash
python3 /skills/weekly-skill/scripts/main.py init \
  --input /input \
  --output /app/output \
  --work /app/work
```

Agent 还需：
1. 读 `/input/case.json`，提取 `case_id` 和 `output_contract` 全部字段，**原样保留键名**。
2. 读 `/input/task.md`，提取 audience、duration、slide_count、模板要求、演讲场合、Q&A 压力、评分侧重点。
3. 递归列出 `/input/` 材料，识别类型并记录路径。

失败处理：
- `case.json` 缺失或损坏：使用最小默认契约字段，状态 `input_error/partial`。
- 材料清单为空：生成最小合法 `result.json`，退出 0。

### 步骤 2：真实解析材料并建立 locator

对每个文件真实解析：
- PDF：使用 `pdftotext` 或平台工具提取文字层；无文字层则标记 `NO_PDF_TEXT_LAYER`。
- DOCX：解压读取 `document.xml` 转文本。
- XLSX/CSV：读取单元格内容，记录 sheet/行号。
- MD/TXT：直接读取。
- PPTX：抽取文本、图表标题、备注。
- 图片：默认不可作为文字来源，除非题面要求；低分辨率/缺图标记为待补。

用 `init` 生成 `materials.json` 和 `index.md`。来源编号规则：材料文件编为 `M1`、`M2`…，段落/行号形成 locator，如 `M1#p12`。抽查命令：

```bash
python3 /skills/weekly-skill/scripts/main.py show --grep "<关键词>"
```

至少抽查 3 处，确认 `quote` 与原文逐字一致后再使用。

### 步骤 3：写 draft.json（Agent 路径）

将你的学术判断写入 `/app/work/draft.json`，结构同第 6 节 `slide_plan.json`。规则：
- 不用论文目录顺序搬运。
- 每页一个唯一主张。
- 每条要点给出 `locator` 与逐字 `quote`。
- 每页 `notes` 写讲解口径、条件、风险，不得复述页面文字。
- Q&A 准备 2–5 个可能的追问及口径一致的回答。

如果脚本版本只读取 `slide_plan.json`，将 `draft.json` 复制或写入为 `/app/work/slide_plan.json` 后再 `check`。

### 步骤 4：校验

```bash
python3 /skills/weekly-skill/scripts/main.py check \
  --work /app/work
```

检查：
- `quote` 是否逐字存在于原文。
- locator 是否存在。
- 每页 bullet 数量是否 3–5 条。
- 页数/时长是否匹配约束。
- 首页 layout 是否合规。

发现 FAIL：
- 修改草案或重新选择 quote；不得改写原文、不得补造来源。
- 仍无法通过则进入确定性兜底抽取，并在 `result.json.degradations` 记录。

### 步骤 5：构建全部产物

```bash
python3 /skills/weekly-skill/scripts/main.py build \
  --input /input \
  --output /app/output \
  --work /app/work
```

产出至少包括：
- `presentation.pptx`：可编辑演示文件，使用真实模板/母版布局。
- `preview.pdf`：由 pptx 导出的真实 PDF 预览。
- `slide_plan.md`：人类可读的页级计划。
- `content_map.json`：页 → 主张 → 来源映射。
- `claims.json`：逐页唯一主张、bullets、evidence_strength。
- `evidence_table.json`：每条主张的 `[S#]` 来源、locator、quote。
- `qa_briefing.md`：问答准备。
- `compliance_checks.json`：模板、页数、字体、导出检查。
- `result.json`：主回显文件。

`build` 后 Agent 必须确认：
- 所有 `output_contract` 字段都有对应产物文件或值。
- pptx 可打开；preview.pdf 非空且页数正确。
- 页面上的数字与 quote 一致。

### 步骤 6：自检与 result.json 终检

```bash
python3 /skills/weekly-skill/scripts/main.py selfcheck \
  --input /input \
  --output /app/output \
  --work /app/work
```

Agent 额外检查：
1. `result.json` 可被 JSON 解析。
2. `case_id` 正确。
3. `output_contract` 全部字段在 `result.json` **顶层**和 **nested `output_contract`** 中各出现一次。
4. `deliverables` 文件真实存在且非空。
5. `status` 诚实：`complete` / `partial` / `input_error`。
6. `uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`sources` 均写入。
7. 退出码 0。

---

## 5. 内容组织规则（评分核心）

1. **从约束反推结构**：先读 audience/duration/slide_count。无页数要求时按 `1 页 ≈ 1.2–1.5 分钟` 估算 `target_slides`。
2. **听众决定取舍**：
   - 组会：方法与进度、风险、下一步；背景 1 页。
   - 答辩/评审：创新点、边界、结论强度；证据强度优先。
   - 术语只解释听众可能不懂的。
3. **叙事不按论文目录搬运**：问题 → 现有做法为什么不够 → 方法 → 关键结果 → 边界与结论；每页回答一个可讲问题。
4. **页标题写结论，不写章名**：如“Top-1 从 31.4% 提升到 46.8%”优于“实验结果”。
5. **数字只在源材料里出现时才成立**：百分比、样本量、时长、p 值必须在 quote 中逐字找到；同一数字跨页引用必须口径一致。
6. **证据强度**：
   - `strong`：多组对照、多数据集、统计检验明确。
   - `moderate`：单数据集或单模型但有对照。
   - `weak`：观察性、无对照、样本小或结论超出支持范围。
7. **图表引用**：页内 `visual` 必须写清引用哪张图/表及 locator；无图则写“无”，不得虚构图表。
8. **备注新增信息**：`notes` 写“讲法、先讲什么、被追问先答什么、条件、风险”，不得复述 bullets。
9. **Q&A 准备**：针对机制、数据、对照、局限、泛化性预判问题；答案必须可定位到页面或备用页。
10. **模板与导出**：保持真实母版/layout；不硬编码字体；若字体缺失，使用平台可用替代并记录降级。

---

## 6. `slide_plan.json` 结构（构建输入契约）

```json
{
  "deck_title": "总标题",
  "subtitle": "副标题",
  "audience": "听众类型",
  "duration_min": 12,
  "target_slides": 8,
  "goal": "这次汇报要达成的可检查目标",
  "narrative": [
    {"act": "动机", "slides": "2-3", "purpose": "建立共识"}
  ],
  "slides": [
    {
      "n": 1,
      "title": "标题页",
      "layout": "title",
      "subtitle": "副标题",
      "bullets": [],
      "notes": "开场 30 秒说什么"
    },
    {
      "n": 2,
      "title": "页标题（一句话结论）",
      "claim": "本页唯一主张",
      "bullets": [
        {
          "text": "听众能听懂的要点",
          "locator": "M1#p12",
          "quote": "源材料中逐字出现的一段原文"
        }
      ],
      "visual": "图2 / 表1；无则写'无'",
      "evidence_strength": "strong | moderate | weak",
      "notes": "讲解口径：先给什么，追问时先答什么"
    }
  ],
  "qa": [
    {"q": "可能的追问", "a": "口径一致的回答", "backup": "备用页/页码"}
  ]
}
```

字段规则：
- 每页内容页 3–5 条 `bullets`。
- 每条至少给 `quote`（逐字）或 `locator`；两者都写更稳妥。
- 首页 `layout: "title"` 仅用于标题页。
- 页标题必须结论化，不写“背景”“方法”“结果”这类章节名。

---

## 7. `result.json` 契约与双回显

`result.json` 必须包含：

```json
{
  "case_id": "case_...",
  "status": "complete | partial | input_error",
  "output_contract": {
    "//": "原题面 output_contract 的全部字段，键名原样保留，缺值 null/[]"
  },
  "slide_plan": "output/slide_plan.md",
  "presentation_file": "output/presentation.pptx",
  "preview": "output/preview.pdf",
  "content_map": "output/content_map.json",
  "compliance_checks": "output/compliance_checks.json",
  "coverage": "output/coverage.json",
  "qa_briefing": "output/qa_briefing.md",
  "reviewed_by_agent": true,
  "sources": [
    {
      "source_id": "S1",
      "file": "/input/paper.pdf",
      "locator": "M1#p12",
      "quote": "原文逐字片段",
      "used_in": ["page_2_claim_1"],
      "evidence_strength": "moderate"
    }
  ],
  "uncertainty": {
    "missing_figures": [],
    "no_text_layer": [],
    "unresolved_conflicts": [],
    "assumed_constraints": []
  },
  "pending_human": [
    "图3分辨率不足，需人工替换",
    "公式编号跨页错位，推荐人工复核"
  ],
  "errors": [],
  "degradations": ["AUTO_EXTRACT", "NO_PDF_TEXT_LAYER", "FONT_FALLBACK"],
  "changes": [
    {"time": "0s", "event": "init complete"},
    {"time": "12s", "event": "agent draft accepted"},
    {"time": "28s", "event": "build complete"}
  ],
  "runtime": {"requests_used": 6, "seconds_used": 31},
  "deliverables": [
    {"file": "output/presentation.pptx", "kind": "editable_deck", "exists": true},
    {"file": "output/preview.pdf", "kind": "rendered_preview", "exists": true}
  ],
  "self_check": {"file": "output/self_check.json", "passed": true}
}
```

**双回显规则**：
- 题面 `output_contract` 的每个原始字段必须出现在 `result.json` 顶层一次。
- 同时必须原样出现在 `result.json.output_contract` 中一次。
- 缺值不得删键，用 `null` 或 `[]` 占位。

**来源规则**：
- 每个来源使用 `source_id: S1..Sn`。
- `locator` 格式优先 `文件#行号/段落号`，如 `paper.pdf#p12` 或 `M1#p12`。
- 每个数字、图表引用、关键论断都要有 `[S#]` 标记并在 `evidence_table.json` 中列明。

---

## 8. 异常处理与隐藏案例鲁棒性

### 正常案例
- 有文本层 PDF、任务约束完整：应交付完整 pptx、PDF、证据映射、Q&A 准备。
- `status = complete`。

### 边界案例
- 页数/时长不符：用 `target_slides` 校验，必要时裁减或增加页，并在 `changes` 记录。
- 缺图/低分辨率：保留文字结论，注明 `pending_human`，不伪造图。
- 公式或符号丢失：保留原文文本形式，标 `uncertainty`，提示人工复核。
- 模板与内容冲突：保持母版/layout，内容退让；记录 `degradations`。
- 字体缺失：使用已安装替代字体，记录 `FONT_FALLBACK`。

### 异常案例
- `case.json` 缺失或坏 JSON：使用默认契约，生成最小合法 `result.json`，退出 0。
- `/input` 无材料：生成缺口页与输入错误报告，退出 0。
- PDF 无文字层：生成“需 OCR/人工补录”缺口页，不生成“看似完整”的科学内容。
- `libreoffice/soffice` 缺失：仍生成 pptx，`preview.pdf` 可为缺失并记录 `PREVIEW_UNAVAILABLE`。
- 脚本内部错误：保留已生成部分，写 `errors`，继续 finish。

### 重复运行
- 不允许因输出已存在而失败。
- 未完成的新运行应覆盖旧产物或写入版本记录；不得删除旧的合法基线后留空。

---

## 9. 预算策略

1. 先跑确定性基线：`init` + `build` 或单命令 `run`，通常 1–2 次调用即可生成全套产物。
2. 若有剩余预算，Agent 做增量改进：读原文、抽查 quote、改 `slide_plan.json`、重跑 `check`/`build`。
3. Agent 额外请求优先用于：
   - 逐页核验数字/图表引用；
   - 改写页标题与 notes 增加讲解价值；
   - 补齐 Q&A 准备；
   - 修正 audience/duration/narrative 的适配问题。
4. 接近 64 次请求或 870 秒时立即收尾：确保 `result.json` 合法、`status` 诚实、退出 0。

---

## 10. 生态贡献与可靠性证据

本 Skill 使用以下文件支撑复用与审计：

- `SELFTEST.md`：自检清单、每个命令的预期输出、常见失败与恢复方式。
- `environment/resources.yaml`：预装依赖声明，说明 Python 版本、平台工具及可选依赖。
- `references/guide.md`：完整工作流说明、`draft.json` 形状、双路径解释、产物映射和失败处理示例。
- `references/organizing_rules.md`：页级叙事、听众适配、证据强度、Q&A 准备规则。
- `references/slide_plan_schema.md`：`slide_plan.json` 字段约束与校验规则。
- `scripts/main.py`：init/check/build/selfcheck/show/run 入口。
- `scripts/makeppt.py`：pptx 渲染与导出。
- `scripts/audit.py`：生成自检产物，不生成官方分数。

编码统一 UTF-8；不联网；不依赖 CWD；资源 ≤50 个 UTF-8 文本文件、单文件 ≤500KB、总大小 ≤2MB。

---

## 11. 收尾最小自检清单

- [ ] `/app/output/result.json` 存在且可解析。
- [ ] `case_id` 来自 `/input/case.json`。
- [ ] `output_contract` 全部字段在顶层与 nested `output_contract` 双出现。
- [ ] `presentation.pptx` 存在、非空。
- [ ] `preview.pdf` 存在、非空；如缺失则已记录 `PREVIEW_UNAVAILABLE`。
- [ ] 每页 claims 有 `[S#]` 来源与 `locator`。
- [ ] 所有 `quote` 逐字来自原文。
- [ ] Q&A 准备、讲稿备注、证据强度均已覆盖。
- [ ] `degradations` 诚实记录 `AUTO_EXTRACT`、缺图、字体回退等降级项。
- [ ] `errors`、`pending_human`、`uncertainty` 已填写。
- [ ] 最终命令退出码为 0。