---
name: sci-mindmap-builder
description: >-
  从真实科研材料解析出发，由 Agent 先盘点、读原文、写 draft.json；无 draft 时用确定性抽兜底。最终输出可编辑、可追溯的思维导图 SVG/JSON/PNG/content_map/result.json，保留逐字 quote、文件#行号/段落号 locator、冲突/缺口/人工确认项和自检记录。
version: 1.3.0
---

# 0. 本 Skill 的最高优先级规则

本 Skill 用于把 `/input` 中给定的科研材料真实解析后生成可编辑、可复核的思维导图，并保留事实与来源映射。运行目标是：材料抽取准、层级清、关系有依据、证据可回溯、结果可编辑、预算内稳定完成。

必须遵守以下铁律：

1. 先跑脚本生成完整基线，尽早落盘，再让 Agent 增量核验与改进。
2. Agent 的职责是：读原文、写 `/app/work/draft.json`、核验 quote/locator、撰写正文型产物、补 `agent_review.json` 与 `pending_human.json`，不手改脚本生成的结构化 JSON。
3. 最终交付物必须覆盖题面 `output_contract` 全部字段；关键数字、术语、引用、论断必须有 `[S#]` 来源和 `文件#行号/段落号` locator。
4. 材料缺失、冲突、无文本层、无法确认的节点，必须显式进入 `gaps` / `pending_human` / `uncertainty`，不得补造。
5. 无论发生什么异常，最终都要生成合法 `result.json` 且退出码为 0。

---

## 1. 用途与边界

### 1.1 做什么

- 从 `/input/case.json` 读取 `case_id`、`task_instruction`、`output_contract`。
- 从 `/input/task.md` 读取任务目标、受众、格式约束、评分重点。
- 真实读取 `/input/**` 中的 PDF、DOCX、TXT、MD、JSON、CSV 等材料。
- 生成分层思维导图：中心主题、3–6 个主分支、分支下要点节点。
- 每个节点尽量带 `quote`、`source_id`、`locator`、`strength`。
- 输出 `mindmap.svg`、`mindmap.json`、`content_map.json`、`mindmap.png`、`result.json` 及其余自检/证据文件。

### 1.2 不做什么

- 不新增材料外的事实、数字、文献、结论。
- 不把装饰性词语或“像结论”的句子当作关键节点。
- 不做 OCR；图片材料无文本层时只登记存在性，不臆造内容。
- 不生成无依据的评分、金标准或虚假 benchmark。
- 不依赖文件名、领域标签补造材料内容。

---

## 2. 输入、工作区、产物与命令

### 2.1 路径约定

- 输入：`/input/case.json`、`/input/task.md` 及 `/input/**` 材料。
- 工作区：`/app/work`。
- 最终产物：`/app/output`。
- Skill 根目录：`/skills/weekly-skill`。

### 2.2 命令入口

推荐单命令入口：

`python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`

如果当前脚本版本不支持 `run` 子命令，则用以下等价流程，不得把“没有 run 子命令”当作失败理由：

`python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work`

`python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work`

`python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work`

其他可用命令：

- `python3 /skills/weekly-skill/scripts/main.py show --help`：查看材料单元内容。
- `python3 /skills/weekly-skill/scripts/verify.py`：运行已有自检。
- `python3 /skills/weekly-skill/scripts/report.py`：生成运行/产物报告，如果存在且可调用。

所有命令只依赖 Python 3 标准库；外部工具 `pdftotext`、`rsvg-convert`、`convert` 存在则优先使用，缺失则降级并在 `result.json.degradations` 中记录。

### 2.3 必须产物

`/app/output` 至少应包含：

- `mindmap.svg`：可编辑 SVG 思维导图。
- `mindmap.json`：结构化节点、关系、证据。
- `content_map.json`：节点到材料单元的映射。
- `mindmap.png`：PNG 预览；渲染器缺失时保留 SVG 并降级说明。
- `result.json`：最终状态、契约回填、证据、边界。
- 证据/自检文件：`evidence_table.json`、`claims.json`、`agent_review.json`、`pending_human.json`、`self_check.json`、`run.log` 等，按脚本实际输出保留。

---

## 3. 执行流程

### 步骤 0：立即生成基线，不等待完美理解

进入任务后第一步必须执行：

`python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work`

然后立即执行：

`python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work`

这一步的目的是先得到一套完整 partial 基线，确保即使后续 Agent 核验时间不够，仍然有可交付文件。基线产物不得删除或清空；后续增强只能在其上覆盖或增加。

如果当前没有 `draft.json`，`build` 会使用 `init` 台账确定性抽取生成 fallback 工作稿。该 fallback 必须在 `result.json.degradations` 或 `change_log` 中记录为 `AUTO_EXTRACT`，不得伪装为 Agent 精读结果。

### 步骤 1：读 case.json 与 task.md

Agent 必须亲自读取：

- `/input/case.json` 中的 `case_id`、`output_contract`、`task_instruction`、材料来源字段。
- `/input/task.md` 的任务说明、目标读者、格式要求、输出要求。

必须识别：

- 任务要的是纯导图，还是“导图 + 学术写作产物/改稿/引用结果”。
- `output_contract` 中所有字段名，不允许用默认字段名覆盖原字段名。
- 哪些是评分要求的可编辑产物、证据映射、版本记录、人工确认项。

### 步骤 2：盘点材料与来源编号

查看 `/app/work/index.json` 或 `init` 输出台账，确认：

- 每个材料有一个稳定 `source_id`，形如 `S1`、`S2`。
- 台账包含类型、路径、单元数、首段、是否解析成功。
- 每个来源的解析状态为 `ok`、`empty`、`binary_no_text`、`corrupt` 或 `unsupported`。

用 `show` 命令真实阅读文本单元，例如按来源查看：

`python3 /skills/weekly-skill/scripts/main.py show --source S1 --window 40`

具体参数以 `show --help` 为准。不得只看文件名、摘要或领域标签。

### 步骤 3：Agent 撰写 draft.json

如果时间和请求预算允许，Agent 必须在真实阅读后写：

`/app/work/draft.json`

`draft.json` 至少包含：

- `case_id`
- `central_topic`
- `branches` 数组，每项含 `id`、`title`、`rationale`、`nodes`
- 每个节点含 `id`、`text`、`node_type`、`quote`、`source_id`、`locator`、`strength`、`relation`
- `cross_links` 数组，含 `from`、`to`、`relation`、`evidence`

`node_type` 限用：`topic`、`research_question`、`method`、`evidence`、`result`、`conclusion`、`task`、`risk`、`gap`、`term`、`inference`。无逐字 quote 支撑的节点必须标 `strength: "inferred"` 并进入 `pending_human`。

写完后运行：

`python3 /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work`

若 check 通过，再运行：

`python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work`

让脚本用 Agent 的 `draft.json` 渲染最终产品。

### 步骤 4：无 draft 或 draft 不合法时使用确定性兜底

如果以下任一情况发生：

- `/app/work/draft.json` 不存在。
- Agent 预算不足，来不及写。
- `check` 判定结构错误。
- 材料无法安全支持 Agent 推断。

则必须回到基线：

`python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work`

脚本会从 `init` 台账确定性抽取节点，为每个节点附逐字 `quote` 与 `locator`，并把以下内容如实写入 `result.json.degradations`：

`"AUTO_EXTRACT": "no agent draft; deterministic extraction used"`

无论哪条路径，产物文件集和 `result.json` 契约必须一致。

### 步骤 5：核验与自检

执行以下动作：

1. 运行 `python3 /skills/weekly-skill/scripts/main.py check ...`。
2. 运行 `python3 /skills/weekly-skill/scripts/verify.py`，把实际输出作为核验记录；不要手写评分。
3. 若有 `report.py`，运行它生成运行报告。
4. 检查 `output_contract` 字段 × 磁盘文件 × `result.json` 键三者一一对应。
5. 检查 `result.json` 合法 JSON，`case_id` 正确，顶层与 `output_contract` 嵌套都回显契约字段。

---

## 4. result.json 契约与双回显

`result.json` 必须满足：

- `case_id` 在顶层出现一次，也在 `output_contract` 对象内出现一次。
- 原始 `output_contract` 的每个字段，都要在 `result.json` 顶层和 `result.json.output_contract` 中各出现一次。
- 缺省契约字段如果题面没有给出，至少映射为：
  - `deliverable`
  - `preserved_facts`
  - `evidence_map`
  - `change_log`

### 4.1 顶层附加字段

必须包含这些附加字段：

- `status`：`success` 或 `partial` 或 `degraded`。
- `sources`：数组，每项含 `source_id`、`path`、`type`、`status`、`units`、`used`、`notes`。
- `uncertainty`：数组，每项含 `id`、`item`、`reason`。
- `pending_human`：数组，每项含 `id`、`item`、`why`、`action`。
- `errors`：数组。
- `degradations`：数组。
- `changes`：数组，含修改动作、原因、时间点。
- `runtime`：含 `start`、`end`、`exit_code`、`commands`。
- `artifacts`：对象，列出路径、大小、格式、是否可编辑、是否有预览。
- `coverage`：含 `node_count`、`verified_count`、`inferred_count`。

### 4.2 契约字段语义映射

- `deliverable`：列出 `mindmap.svg`、`mindmap.json`、`content_map.json`、`mindmap.png` 的相对路径、字节数、格式、可编辑性。如果任务还要求学术写作稿，列出 `deliverable.md` 或 `manuscript.md`，且每个数字/论断必须能在 `evidence_table.json` 或 `result.json.preserved_facts` 中找到。
- `preserved_facts`：数字、术语、引用、关键论断列表，字段含 `fact_id`、`text`、`source_id`、`locator`、`quote`、`status`。
- `evidence_map`：节点到材料来源的映射，字段含 `node_id`、`source_id`、`locator`、`quote`、`strength`。
- `change_log`：Agent 或脚本做的修改、原因、人工确认项、未解决问题。

### 4.3 状态判断

- `success`：所有契约字段均存在，所有关键事实都有可核验 quote 与 locator，且没有未解决的致命缺项。
- `partial`：有产物但存在部分材料缺失、无法确认节点、渲染降级、未完成人工核验。
- `degraded`：材料很多不可用、脚本降级、渲染失败但仍能交付可读结构文本。

---

## 5. 证据与来源规则

1. 每个事实/数字/术语/引用必须有 `[S#]` 来源标记。
2. `locator` 优先使用 `文件#行号/段落号`，PDF 可标页号，表格可标 sheet/行列。
3. `quote` 必须是原文逐字片段。若只能概括，标 `quote: null`、`strength: "summary"` 或 `"inference"`，并加入 `uncertainty` 或 `pending_human`。
4. 关系必须有材料依据。`supports`、`contradicts`、`causes`、`depends_on`、`contrasts`、`temporal`、`references` 等关系，遇到材料冲突时不做强制合并，保留冲突节点，并在 `change_log` 中记录。
5. PDF 必须真实解析；如果 PDF 无文本层或图片型 PDF，不得靠文件名补造。在 `sources` 中记录 `binary_no_text`，在结果中保留可编辑导图，但节点只写“材料不可用/需人工检查”。

---

## 6. 隐藏案例鲁棒性

### 6.1 正常案例

输入通常包含：

- 一篇或多篇论文/材料。
- 明确任务说明，可能要求思维导图，也可能同时要求学术写作产物。
- 明确 `case_id` 和 `output_contract`。

应对：完整走步骤 0–5，使用 Agent 精读路径，优先生成带逐字证据的导图；同时补齐 `deliverable.md` / `manuscript.md` 之类的正文产物，保持两者内容不重复。

### 6.2 边界案例

可能出现：

- 多材料、长文档、节点规模爆炸。
- 材料中缺部分关键信息。
- PDF 是扫描件或无文本层。
- 要求多种输出但时间有限。
- 材料之间存在冲突。

应对：

- 先跑基线，控制节点数量：中心主题下不超过 6 个主分支，每个分支不超过 30 个原始节点；超出部分进入 `content_map.json` 而不强行塞入主图。
- 长文档按节/段落抽取，用 `show` 分段阅读。
- 无文本层材料不 OCR，只登记存在性并列入 `gaps`。
- 冲突保留双方，明确标 `conflict`，不单方面删除。
- 输出 `pending_human.json` 让用户处理材料不足。

### 6.3 异常案例

可能出现：

- `/input/case.json` 缺失、坏 JSON。
- `/input` 下没有材料。
- 文件损坏、权限不足。
- 命令失败、渲染器缺失。
- 预算耗尽。

应对：

- 所有异常必须被捕获，继续生成产物。
- `case.json` 缺失时从 `task.md` 提取可用信息，`case_id` 用 `unknown`，并在 `errors` 中记录。
- 无材料时生成含根节点“材料不可用”的 SVG/JSON，契约字段回填空数组/null，`status` 设为 `partial`。
- 外部渲染器缺失时只交付 SVG 和 JSON，`mindmap.png` 缺失时在 `artifacts` 与 `degradations` 说明。
- 命令失败不得退出非 0；用 `|| true` 或等价方式继续。

---

## 7. 预算与停止策略

官方预算：64 次模型请求 / 900 秒 / 每次响应含 reasoning 不超 16384 tokens。

预算分配：

1. 第 1–2 次请求：跑 `init` + `build` 基线。
2. 接下来 5–15 次请求：盘点材料和阅读关键原文片段。
3. 之后 3–8 次请求：写 `draft.json`，`check`，`build`。
4. 之后 1–3 次请求：运行 `verify.py`、`report.py`，检查契约。
5. 剩余预算：改写正文型产物、补 `agent_review.json`、`pending_human.json`、自检。

停止条件：

- 一旦已经得到合法 `result.json` 和可打开、可读的导图，就不要再无限打磨。
- 接近 90% 预算或剩余时间不足以再完整执行一次 `init + build` 时，立即收尾。
- 最后一步永远是检查并刷新 `result.json`，而不是重生成大型产物。

---

## 8. 使用增益证据与禁止自评

### 8.1 增益证据

增益证据要体现在产物中：

- `result.json.coverage`：统计被原文 quote 覆盖的节点数、inferred 节点数。
- `result.json.changes`：记录 `baseline -> agent_enhanced` 的变化。
- `agent_review.json`：逐条记录 `claim_id`、`verified`/`rejected`/`fixed`、`reason`。
- `pending_human.json`：记录哪些事实需要人工确认。
- 保留基线产物与最终产物相对路径，允许评委回查“基底稳固、增益真实”。
- 若优化了布局、层级或节点数量控制，在 `change_log` 中写“结构改善原因 + 实际文件路径”，不要写自评分。

### 8.2 禁止自评

不得生成：

- 虚假 benchmark 分数。
- 无依据的 `golden_standard` 声称。
- 手写 `verification.json` 冒充验证结果。
- 把文字自述说成实际运行证据。

验证只引用 `verify.py` 的真实输出，无明显输出则在 `degradations` 中说明自检脚本不可用。

---

## 9. 交付前必须检查的清单

- [ ] `result.json` 是合法 JSON。
- [ ] `case_id` 顶层和 `output_contract.case_id` 都存在且一致。
- [ ] 原始 `output_contract` 字段全部回填。
- [ ] 顶层契约字段与嵌套字段双回显。
- [ ] `mindmap.svg`、`mindmap.json`、`content_map.json` 存在且可读。
- [ ] `mindmap.png` 存在；若缺失，已在 `degradations` 说明。
- [ ] 每个关键数字/引用/论断至少有 `[S#]` 和 locator。
- [ ] 无节点使用材料外事实。
- [ ] 材料缺失、冲突、未确认项进入 `gaps`、`pending_human`、`uncertainty`。
- [ ] 异常都已进入 `errors` 或 `degradations`。
- [ ] 最终退出码为 0。

---

## 10. 快速执行摘要

执行顺序：

1. `init`。
2. `build` 落盘 baseline。
3. 读 `/input/case.json` 和 `/input/task.md`。
4. 读材料原文。
5. 写 `/app/work/draft.json`。
6. `check`。
7. 用 draft 执行 `build`；草稿不合规则退回 fallback。
8. `verify.py` / `report.py`。
9. 检查 result.json 双回显。
10. 不论成不成功，都保留诚实 partial 与合法 result.json，exit 0。