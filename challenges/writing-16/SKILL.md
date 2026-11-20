---
name: research-translation-writing
description: "把科研材料（论文、技术报告、数据表、图表说明）改写成面向指定受众与体裁的可直接使用稿件，逐段保留来源定位、数字与论断强度，交付必保留项清单、逐段来源对照、change log 与 result.json；当任务要求把成果写给某类读者、改写成申报/科普/简报、多文体转换时使用。"
version: 2.0.0
---

# 科研成果转化写作（受众/体裁改写）

## 0. 最高优先级规则：脚本只是工具，成品必须由 Agent 亲自推导

本 Skill 用于：**读源材料 → 按目标受众与体裁重写 → 每处保留可回溯的来源、数字、限定条件与论断强度**。

**脚本只是工具。** `scripts/main.py` 负责索引材料、打印带定位原文、校验工作稿、排版成稿、回填契约；`scripts/verify.py` 负责确定性校验。**最终交付物（deliverable.md 正文、preserved_facts、evidence_map、change_log、transformation_spec 等实质内容）必须由 Harness Agent 亲自阅读实际材料、推导判断、撰写或制作。** 禁止把脚本生成的模板、骨架、提纲、原文抽取或片段润色当作最终成品；禁止依据文件名或领域标签猜测、补造内容。

**完整性优先。** 进入任务后先运行 Skill 主流程产出全套基线交付物；后续校验与改写只能在基线上增强，不得删除、清空或遗漏任何基线产物与契约字段。若不确定，保留原产物并在 result.json 标注 `reviewed_by_agent`。

## 1. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `output_contract`）、`/input/task.md`、`/input/` 下材料（PDF/DOCX/XLSX/CSV/MD/JSON/图片等） |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`check.json` 等） |
| 最终产物 | `/app/output/deliverable.md` + `/app/output/result.json`；如契约要求的可编辑 Office/幻灯片/图形产物，另需真实渲染的 PDF/PNG 预览 |
| 依赖 | 仅 Python3 标准库；离线；不依赖当前工作目录（脚本用 `Path(__file__).resolve()`） |
| 退出码 | 恒为 0；异常写入 `result.json.errors` 并保留已有产物 |
| 预算 | 64 次模型请求 / 900 秒 / 单次回复 16384 tokens（含推理）；接近 780 秒立即 `build` 收口 |

## 2. 预算感知策略（64 次模型请求 / 900 秒）

必须先保 rubric 权重最高的实际效果：**完整、正确、可核验的转化稿**。

建议请求分配：

1. 盘点输入并解析材料：8-15 次。`init` + `show` 阅读摘要、数字段、图表标题、结论与局限。
2. 写 draft.json 完整正文与证据映射：20-30 次。先写正文骨架，再逐段补证据与措辞。
3. check 与修复：5-10 次。一次修完所有 `[错误]`，避免反复 show 全部原文。
4. build、finalize、自检：3-8 次。核对契约字段、文件、预览与自检。
5. 预留 3-8 次应对超时、缺材料、校验冲突。

**尽早落盘 honest partial：** `init` 完成后即写合法 partial `result.json`；写出 `draft.json` 后立即 `check` + `build` 更新。无论后续是否继续，都可保留一个可复核的半成品，而不是空手返回。

**避免无意义循环：** 不要重复读同一段原文；不要为了追求完美反复重写非 P0 段落；check 失败时先分类，再一次性修复。接近时间预算时，停止新增，立即 `build`。

## 3. 执行流程（按序执行）

### 步骤 1：盘点输入与契约

**输入：** `/input/case.json`、`/input/task.md`、`/input/` 下所有材料。

**动作：**
1. 运行 `python3 scripts/main.py init`。
2. 阅读 `case.json` 的 `output_contract`，明确必须回填的字段名、数量、约束。
3. 阅读 `task.md` 的受众、体裁、篇幅、格式、交付要求。
4. 记录材料清单、材料号、解析状态。

**输出：** `/app/work/index.json`、`/app/work/draft.json` 模板、合法的 partial `result.json`、打印出的段落清单/关键数字/缩写。

**失败分支：** `case.json` 缺失或坏 JSON：递归查找含 `output_contract` 的 JSON；仍无则用内置字段，并在 `degradations` 记录。缺材料：照常 init，缺口写入 `errors`/`pending_human`。

### 步骤 2：用工具真实解析材料

**输入：** init 输出的材料清单与段落编号（`M1:P3` 形式）。

**动作：**
1. 用 `python3 scripts/main.py show --ids M1:P1-M1:P8` 或 `--grep 关键词` 读取原文。
2. **至少读：题目/摘要/引言、含数字的段落、方法关键条件段、结果段、局限与结论段、图表标题。**
3. 按实际文本理解内容，不按文件名或领域标签猜内容。
4. PDF 解析优先使用系统 `pdftotext`；不可用时使用脚本内置 PDF 流解析。DOCX/XLSX 读 XML 源，TXT/CSV/MD/JSON 读文本。图片不 OCR。

**输出：** 已读原文摘录与带定位 `quote`。

**失败分支：** 某份材料解析失败或质量低：只降级该文件，其余继续；在 `sources` 标 `pdftotext` / `builtin-pdf-lowconf` / `docx-xml` / `xlsx-xml` / `text` / `image-no-ocr`，在 `degradations` 记录文件名与原因。不得臆造内容。

### 步骤 3：构建与核对证据底稿

**输入：** 上一步已读原文。

**动作：**
1. 为每个关键论断、数字、术语、图表引用建立 `quote + locator`。
2. 核对数字、单位、样本量、条件、缩写首次展开、图表编号是否与源文一致。
3. 记录数据冲突、材料缺口、体裁与篇幅冲突。

**输出：** 证据清单、术语表草稿、P0 必保留项清单草稿、冲突/待确认清单。

**失败分支：** 材料过少或冲突无法判断：写入 `pending_human`/`uncertainty`，后续 `status=partial`。

### 步骤 4：Agent 产出完整成品

**输入：** 证据底稿 + `/app/work/draft.json` 模板。

**动作：** 按 `references/draft-schema.md` 填写：
- `audience`/`genre`：给出读者画像、解释深度、术语密度、篇幅分配策略。
- `sections`：**成稿正文**，按目标体裁组织；每段 `cites` 标 `M1:P3`；每段标 `strength`。
- `preserved`：P0 必保留项（数字+单位、样本/条件、图表引用、关键结论、限定语），带逐字 `quote` 与 `locator`。
- `map`：逐段来源对照；`changes`：删改动作、理由、原文→改后；`removed`：删了什么、为什么不是证据。
- `glossary`：缩写首次展开与全文统一说法；`pending`/`uncertainty`：待确认与不确定。
- 不新增源材料没有的数字、文献、机构、商业结论。

**输出：** 完整 `/app/work/draft.json`。

**失败分支：** 篇幅不足目标 45% 时，不得用提纲、片段润色或写作建议充数，必须继续补写正文。若源材料确少，写 `status=insufficient_evidence`。

### 步骤 5：校验与修复

**输入：** `/app/work/draft.json`。

**动作：** 运行 `python3 scripts/main.py check`，按报告修复，直到无 `[错误]`。常见错误修复顺序：
- 引文未命中：改 `quote` 或 `locator`，或移入 `pending_human`。
- 数字不在源文：改为源文数字，或换算并在 `note` 说明并放入 `pending`。
- 缺字段：补齐字段。
- 篇幅不足：继续补写正文。

**输出：** 校验报告与实际修好的 `draft.json`。

**失败分支：** 禁止为通过校验修改原文词句。无法命中引文时，宁可写 `pending_human`，不得伪造来源。

### 步骤 6：build 并交付

**输入：** 通过 check 的 `draft.json`。

**动作：**
1. 运行 `python3 scripts/main.py build`。
2. 生成 `/app/output/deliverable.md` 并无条件 finalize `/app/output/result.json`。
3. 若 `output_contract` 要求可编辑 Office/幻灯片/图形，额外生成对应可编辑文件与真实渲染的 PDF/PNG 预览。优先用环境可用转换器（如 `pandoc`、`libreoffice` 等）；若不可用，保留 Markdown 交付并在 `result.json.degradations` 如实说明预览缺失。

**输出：** `/app/output/deliverable.md`、`/app/output/result.json` 及必要预览文件。

**失败分支：** 转换失败不阻塞交付：保留可编辑 Markdown/源文件，`degradations` 记录；`result.json` 仍合法。

### 步骤 7：自检 rubric 并回填 result.json

**输入：** `/app/output` 下所有文件。

**动作：**
1. 逐项核对 `output_contract 字段 list × 磁盘文件 × result.json 键`，缺一不可。
2. 用 `python3 scripts/verify.py` 或 `main.py check` 复查。
3. 把 Agent 亲自核验来源的结果写进 `result.json.self_check` 与 `reviewed_by_agent`，识别 `verified` / `pending_human` / `conflicts`。
4. 确保 `status` 与实况一致。

**输出：** 最终 deliverable.md + result.json。

**失败分支：** 缺任何契约字段先补齐再收尾；超时也要保证 result.json 合法、退出码 0。

## 4. 输出契约与产物规范

- 必须原样回填 `case.json` 的 `output_contract` **全部字段**（键名不改、不缺项；无对应内容填 `null`/`[]`），并写 `contract_fill` 统计。
- 固定字段：`case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`changes`、`glossary`、`removed`、`transformation_spec`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`self_check`、`runtime`。
- `status` 规则：结构/引文/数字全过 → `ok`；有缺口但已交付 → `partial`（缺口写进 `errors`/`pending_human`）；无可用材料 → `insufficient_evidence`；输入本身不可解析 → `input_error`。
- `sources` 记录每份材料的 `method` 与解析状态；解析降级同时写入 `degradations`。
- 交付正文至少包含：适配说明、转化稿正文、逐段对照、必保留项清单、删改/change log、术语表、待确认项、自检。

## 5. 证据与定位规范

- 定位格式：`M<材料号>:P<段号>`，段落号取自 `init` 输出；也可写 `M1:P3-M1:P6`。
- `quote` 必须**逐字**取自源材料（允许空白/全半角差异，不允许改词、补字、翻译）。
- 成稿中出现的每个数字都必须能在源材料找到（含单位写法）；换算须在 `note` 说明，并把该项放进 `pending`。
- 核验不过的处理顺序：改 quote → 改 locator → 把该项移入 `pending_human`。**禁止为了通过校验而修改原文。**

## 6. 受众 / 体裁 / 论断强度

- 三要素判定：读者知识背景 → 解释深度与术语密度 → 例子与篇幅分配（详见 `references/genre-playbook.md`）。
- 论断强度只分三级并写进 `sections[].strength`：
  - `established`：源文明确结论（含“显著”“证明”等）；
  - `preliminary`：初步/单一实验/体外结果，须保留“初步”“有待验证”；
  - `hypothesis`：机制推测、外推应用、商业前景 → 转写时必须降级表述并进 `pending_human`。
- 相关不写成因果；样本量与条件（物种、剂量、时长、平台）随结论一起搬。

## 7. 取舍规则（删什么不是删证据）

| 优先级 | 内容 | 处理 |
|---|---|---|
| P0 必保留 | 主结论、关键数字+单位、条件与样本、图表编号、局限与不确定性 | 逐字或等价保留，进 `preserved` |
| P1 可压缩 | 方法细节、参数罗列、文献堆叠 | 一句话概括，不改数值 |
| P2 可删 | 重复表述、与目标读者无关的推导、致谢与投稿信息 | 进 `removed` 并写理由 |

压缩后如果某结论失去限定条件，就把限定条件补回；**宁可多一句限定，不可少一个条件**。

## 8. 冲突、缺口与人工确认

- 受众与体裁冲突（如“面向公众”却要求“完整方法”）→ 以受众为纲，方法压缩为一句，冲突写 `pending_human`。
- 篇幅与内容冲突 → 保 P0，删 P2；在 `deliverable.md` 首节说明篇幅取舍。
- 数据自相矛盾（同一指标两个值）→ 两值都列，标 `uncertainty`，不擅自选一个。
- 材料涉密/未发表/含个人信息 → 不做外推，`pending_human` 写“需授权确认后发布”。
- 缺引用/缺图表编号 → 不用占位数字补，写“（原文未给编号，需补）”并进 `pending`。

## 9. 异常降级与鲁棒性

| 情形 | 行为 |
|---|---|
| `case.json` 缺失/坏 JSON | 递归找含 `output_contract` 的 json；仍无则用内置字段，`degradations` 记录 |
| PDF 无 `pdftotext` | 内置流解析；质量低时标 `builtin-pdf-lowconf`，并提示人工核对 |
| 材料是图片 | 不 OCR，记 `image-no-ocr` 缺口，不臆造图注 |
| 材料解析失败 | 只降级该文件，其余继续；`degradations` 记文件名与原因 |
| 空输入/无材料 | init 返回无材料；仍生成合法 `result.json`，`status=insufficient_evidence` 或 `input_error` |
| `draft.json` 缺失/不合格 | `build` 用源文句子做确定性抽取兜底，`status=partial` 并在稿首标注“兜底稿，未完成受众改写” |
| 运行超时/异常 | 仍有 partial `result.json`；`build` 可重跑覆盖；退出码 0 |

任何情况下，都必须返回合法 `result.json`，包含所有契约字段与 `case_id`，并如实说明缺陷。

## 10. rubric 维度 → 交付要求 → 自证方式

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果 40：任务完成度 15 | 给出可直接使用的完整转化稿，而不是建议、提纲或片段润色 | `deliverable.md` 有完整正文；`status=ok` 时篇幅达标；`sections` 为完整成稿 |
| 实际效果 40：结果正确性 15 | 事实、数据、单位、图表编号、引用、论断强度与源文一致，不新增源文没有支持的新结论 | `preserved_facts` 逐条 quote+locator；数字校验 0 不匹配；`evidence_map` 可回溯；冲突放 `uncertainty`/`pending_human` |
| 实际效果 40：结果完整性 5 | 保住关键结论、数据、限定条件、方法要点、图表引用 | P0 清单完整；`removed` 记录可删内容及理由；`changes` 区分删改性质 |
| 实际效果 40：结果可核验性 5 | 原作者能按段复核 | `evidence_map` 逐段对照；`change_log` 逐条删改理由；`deliverable` 含逐段对照与待确认 |
| 使用增益 25 | 比基础 Agent 更少事实漂移、受众错配、术语不一致；降低人工编辑成本 | `glossary` 锁定术语；`transformation_spec` 写明受众策略；`preserved_facts` 与 `change_log` 可减少返工；`self_check` 记录核验结论 |
| 创新增益 15 | 形成“受众画像→取舍策略→边界标注→多文体映射”链条 | `transformation_spec`、`sections[].strength`、`genre-playbook` 引用、`pending_human` 边界标注齐全 |
| 可靠体验 10 | 可重复、稳定、异常可处理 | `init/show/check/build` 全流程幂等；退出码 0；`degradations`/`errors` 如实记录异常；任何失败输出合法 result.json |
| 生态贡献 10 | 文档、模板、词表、验收口径可复用 | `SKILL.md` 完整流程；`references/draft-schema.md` 定义字段；`references/genre-playbook.md` 提供体裁映射；`scripts/verify.py` 提供校验；最小示例标注为示例 |

## 11. 自检清单（提交前逐项检查）

- [ ] 已真实解析并阅读 `/input` 材料，而非按文件名猜测。
- [ ] `deliverable.md` 含：适配说明、转化稿正文、逐段对照、必保留项清单、删改/change log、术语表、待确认、自检。
- [ ] `check` 无 `[错误]`；引文命中率 100%；数字不匹配 0。
- [ ] 每个关键论断能在 `evidence_map` 找到 `locator`，`quote` 逐字来自原文。
- [ ] 没有新增源文没有的数字、文献、机构、商业结论；不确定项写入 `pending_human`。
- [ ] `result.json` 原样保留 `output_contract` 全部字段，且包含 `case_id`。
- [ ] 三人逐条核对：契约字段 list × 磁盘文件 × result.json 键一一对应。
- [ ] 若契约要求 Office/幻灯片/图形，已尽力提供真实 PDF/PNG 预览；无法提供已记录 degradation。
- [ ] `status` 与实况一致；退出码 0；任何异常都写入了 `errors`/`degradations`。
- [ ] 基线产物全部保留，Agent 增强后未删除任何契约字段与磁盘文件。

## 12. 最小调用示例（示例，非正式案例结果）

运行：`python3 scripts/main.py init`

输出摘要示例：

材料索引 M1 demo_paper.md text text 820字/6段  
受众：产业界 <- `产业界`  
体裁：技术转化简报   篇幅：1200 字  
契约：case_id, deliverable, preserved_facts, evidence_map, change_log（5 字段）

随后 Agent 写 `/app/work/d