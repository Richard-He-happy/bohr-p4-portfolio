---
name: research-translation-writing
description: "把科研材料（论文、技术报告、数据表、图表说明）改写为面向指定受众与体裁的可直接使用稿件；逐段保留来源定位、数字单位、样本条件、术语和论断强度；交付成稿、必保留项、证据映射、改动记录、术语表、待确认项与双回显 result.json。适用于科研成功转化写作、科普改写、申报材料改写、技术简报、多文体转换等任务。"
version: 2.2.0
---

# 科研成果转化写作 Skill

## 0. 最高优先级规则：完整交付 + 可回溯 + 诚实降级

本 Skill 用于：读实际科研材料 → 按目标受众与体裁重写 → 保留来源定位、数字、条件、术语与论断强度 → 产出可编辑成稿与复核记录。

**脚本只是工具。** `scripts/main.py` 负责材料索引、原文带定位展示、工作稿校验、成稿渲染、契约回填；`scripts/verify.py` 负责确定性复核。最终实质内容必须来自对 `/input` 下材料的真实阅读与推导，不得按文件名、领域标签或提示样例补造内容、文献、数据或结论。

**完整性优先。** 任何情况下都要返回合法 `/app/output/result.json`，包含原 `output_contract` 全部字段与 `case_id`；缺口、冲突、解析降级和人工确认项必须诚实登记。运行退出码必须为 0。

---

## 1. 输入输出契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `output_contract`）、`/input/task.md`、`/input/` 下材料，可能是 PDF/DOCX/XLSX/CSV/MD/JSON/图片等 |
| 工作目录 | `/app/work`：`index.json`、`draft.json`、`check.json`、`verification.json` 等 |
| 输出目录 | `/app/output`：主成稿、证据映射、必保留项、改动记录、术语表、待确认项、自检记录、预览文件、`result.json` |
| 资源约束 | 仅 Python3 标准库，离线；`python3>=3.8`；不依赖当前工作目录；不调用外部网络服务 |
| 退出码 | 恒为 0；异常写入 `result.json.errors`/`degradations` 并保留已有产物 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |

---

## 2. 单命令全流程入口

首选执行：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部应完成 `init → 读取或生成 draft → check → build → finalize/selfcheck`。它必须幂等：若 `/app/work/draft.json` 已存在且由 Agent 填写，不得覆盖；若不存在，则执行确定性兜底抽取并生成工作稿。

若当前版本的 `scripts/main.py` 不支持 `run`，不要反复重试，按以下子命令完成同一流程：

`python3 scripts/main.py init`  
`python3 scripts/main.py show --ids <M#:P# 或范围>`  
`python3 scripts/main.py check`  
`python3 scripts/main.py build`  
`python3 scripts/verify.py`

两条路径必须产出同一套产物与同一份 `result.json` 契约。

---

## 3. 执行策略：Agent 路径与确定性兜底双路径

### 3.1 Agent 路径（高优先级）

当模型请求预算充足时，Agent 应亲自阅读材料、核验并产出高质量成稿。

1. 先运行 `init` 或 `run` 获得材料台账和基线。
2. 阅读 `/input/case.json` 的 `output_contract`、`/input/task.md` 的受众/体裁/篇幅/格式要求。
3. 用 `show` 读取关键原文：标题/摘要/引言、数字段、方法关键条件段、结果段、局限与结论段、图表标题。
4. 将完整正文、证据映射、必保留项、改动记录写入 `/app/work/draft.json`。
5. 运行 `check` 修复错误，再运行 `build` 生成 `/app/output` 下的最终产物。

### 3.2 确定性兜底路径（无 draft 或预算不足时）

当 `/app/work/draft.json` 不存在、不可解析或 Agent 来不及写时，`build` 或 `run` 必须用 `init` 产生的事实性台账做确定性抽取，生成可复核的实质工作稿：

- 从源材料中逐字抽取关键句、数字、条件、图表标题，形成 `quote + locator`。
- 将抽取结果作为 `sections` 内容，成稿开头标明“兜底稿，已完成来源锚定，但受众改写与文体润色不完整”。
- 在 `result.json.degradations`、`errors` 与 `change_log` 中加入 `AUTO_EXTRACT`，说明该稿不是完整人工改写稿。
- `status` 应为 `partial`，不得伪装成 `ok`。

兜底稿也必须真实、可回溯，不编造内容。

---

## 4. 步骤 A：init 盘点材料与契约

执行：

`python3 scripts/main.py init`

Agent 必须读取并核验：

- `/app/work/index.json`：材料清单、来源编号、解析方法、段落/行号区间、候选关键句。
- `/app/work/draft.json` 模板：用于后续填写。
- `/app/output/result.json` 是否已生成合法 partial 结果。
- `/input/case.json` 中的 `output_contract` 字段，必须原样回填。
- `/input/task.md` 中的受众、体裁、篇幅上限、格式要求。

**来源编号规则：** 每份材料分配一个 `source_id`，使用 `S1`、`S2`、...；同时保留 `M<材料号>:P<段号>` 这种细粒度 locator。最终证据映射中两者都写清楚。

**失败处理：**

- `/input/case.json` 缺失或坏 JSON：递归查找 `/input` 下含 `output_contract` 的 JSON；仍无则用内置契约字段，并在 `degradations` 记录。
- 缺材料：照常 init，缺口写入 `errors` 与 `pending_human`。
- 材料解析失败：只降级该文件，其余继续。

---

## 5. 步骤 B：真实解析材料

执行 `show` 读取原文，至少覆盖：

- 题目/摘要/引言：确定研究对象、主结论、边界。
- 含数字段落：数值、单位、比较基准、样本量、统计口径、图表编号。
- 方法关键条件段：物种、剂量、时长、平台、分组、样本筛选条件。
- 结果段：主要发现、效应大小、显著性、限定语。
- 局限与结论段：外部效度、未解决问题、作者给出的边界。
- 图/表标题：图表编号与含义。

**解析方法声明：**

- PDF：优先 `pdftotext`；不可用时使用脚本内置 PDF 流解析，标记 `builtin-pdf-lowconf`。
- DOCX/XLSX：读取 XML 源，标记 `docx-xml` / `xlsx-xml`。
- TXT/CSV/MD/JSON：按文本读取。
- 图片：不 OCR，标记 `image-no-ocr`，并在 `pending_human` 中写明“图内文字未提取，需人工补充”。

---

## 6. 步骤 C：Agent 填写 draft.json

`draft.json` 是 Agent 的最重要中间产物。必须按 `references/draft-schema.md` 的形状填写，至少包含：

- `case_id`：原样保留。
- `audience`：目标读者画像、知识背景、解释深度、术语密度、篇幅分配策略。
- `genre`：目标体裁及结构要素。
- `transformation_spec`：从源文体到目标文体的转换规则，至少覆盖受众适配、内容取舍、术语锁定、论据边界。
- `sections`：完整成稿正文，按目标体裁组织；每段正文必须有 `cites`，引用具体 `source_id + locator`；每个关键论断标注 `strength`。
- `preserved`：P0 必保留项，含数字+单位、条件与样本、图表引用、关键结论、局限与不确定性；每项带逐字 `quote` 和 `locator`。
- `evidence_map`：关键论断到来源定位的映射，必须逐段可回溯。
- `change_log`：每次修改动作，包含原文→改后、修改类型、理由。
- `removed`：被删除内容，说明为何是冗余而不是证据。
- `glossary`：缩写首次展开、同义术语收敛、跨文体术语替换；同一概念全文只保留一个说法。
- `pending_human`：需人工确认项，如缺失图表编号、数据冲突、涉密内容、外推风险。
- `uncertainty`：数据冲突、口径不一致、无法判断的内容。

**填写约束：**

- 数字、单位、样本量、图表编号、引用必须能在源文找到逐字依据。
- 不允许新增材料外文献、数字、机构、商业结论。
- 不把相关写成因果；不把初步结果写成定论。
- 压缩时删冗余，不删证据；若删掉某句后导致结论失去限定条件，必须把限定条件补回。
- `sections` 必须是成稿正文，不允许用提纲、片段润色或写作建议充数。

---

## 7. 步骤 D：check 校验与修复

执行：

`python3 scripts/main.py check`

修复优先级：

1. 引文未命中：改逐字 `quote` 或 `locator`；仍无法命中，移入 `pending_human`。
2. 数值不在源文：改为源文数值，或做等价换算并在 `note` 说明，同时放入 `pending`。
3. 缺字段：补齐字段。
4. 篇幅不足目标 45%：继续补写正文，不得用提纲充数。
5. 术语不一致：更新 `glossary` 与正文。

**禁止为了通过校验修改原文词句。** 无法命中时就写 `pending_human`，不得伪造来源。

---

## 8. 步骤 E：build 生成交付物

执行：

`python3 scripts/main.py build`

该命令必须生成：

- `/app/output/deliverable.md`：可编辑、干净的目标成稿。
- `/app/output/evidence_driven_draft.md`：带证据标记的成稿草稿，与 clean 版内容应有差异。
- `/app/output/preserved_facts.md`：P0 必保留项清单。
- `/app/output/evidence_map.md`：关键论断到来源定位的映射。
- `/app/output/change_log.md`：修改动作、理由、人工确认项与未解决问题。
- `/app/output/glossary.md`：术语表。
- `/app/output/pending_human.md`：待人工确认项。
- `/app/output/uncertainty.md`：不确定与冲突项。
- `/app/output/self_check.md`：自检清单与结果。
- `/app/output/result.json`：结构化契约回填。

若 `output_contract` 要求可编辑 Office/幻灯片/图形，则额外生成对应可编辑文件，并尽力生成真实渲染的 PDF/PNG 预览。若环境缺少转换器，保留 Markdown 或可编辑源文件，并在 `result.json.degradations` 如实说明预览缺失。

---

## 9. result.json 双回显契约

`/app/output/result.json` 必须满足：

1. 顶层包含原 `output_contract` 的全部字段。
2. 顶层同时包含固定状态字段：`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`self_check`、`runtime`。
3. 嵌套 `output_contract` 中再次出现原契约全部字段，并回填对应文件引用或结构化值。
4. 若原契约中有扩展字段（如 `deliverable_format`、`audience` 等），也要在顶层和嵌套 `output_contract` 中分别保留。

`status` 取值规则：

- `ok`：Agent 已完成成稿，check 通过或仅剩非阻塞 warning，证据映射命中率达到 100%。
- `partial`：已交付实质产物，但存在缺口、兜底抽取、解析降级或待人工确认。
- `insufficient_evidence`：源材料无法支持任务要求，仍输出合法可复核结果。
- `input_error`：输入不可解析或材料完全缺失。

---

## 10. 证据与来源定位规范

- `locator` 格式为 `文件路径#段落号/行号` 与 `M<材料号>:P<段号>` 并存。
- 交付正文中关键数字、术语、图表引用和论断应标注 `[S#]` 或 `[S#: M#:P#]`，与 `evidence_map` 一致。
- `quote` 必须逐字来自源材料，允许空白/全半角差异，不允许改词、补字、翻译。
- 成稿中出现的每个数字都必须在源材料找到，含单位写法。
- 同一概念全文只允许一个标准说法，首次出现缩写必须展开。
- 核验不过的处理顺序：改 quote → 改 locator → 移入 `pending_human`。

---

## 11. 受众、体裁与论据边界

使用 `references/genre-playbook.md` 做体裁映射。

三要素判定：

- 读者知识背景决定解释深度与术语密度。
- 阅读目的决定结构、例子与篇幅分配。
- 源文体与目标文体差异决定证明材料保留方式。

论据强度只分三级：

- `established`：源文明确结论，可保留较强表述。
- `preliminary`：初步、单一实验、体外结果，须保留“初步”“有待验证”。
- `hypothesis`：机制推测、外推应用、商业前景，必须降级表述，并进 `pending_human`。

---

## 12. 取舍规则

| 优先级 | 内容 | 处理 |
|---|---|---|
| P0 必保留 | 主结论、关键数字+单位、条件与样本、图表编号、局限与不确定性 | 保留并进入 `preserved` |
| P1 可压缩 | 方法细节、参数罗列、文献堆叠 | 一句话概括，不改数值 |
| P2 可删除 | 重复表述、与目标读者无关的推导、致谢与投稿信息 | 进 `removed` 并写明理由 |

压缩后如果某结论失去限定条件，必须补回限定语。宁可多一句限定，不可少一个条件。

---

## 13. 冲突、缺口与人工确认

- 受众与体裁冲突：以受众为纲，方法压缩为一句，冲突写 `pending_human`。
- 篇幅与内容冲突：保 P0，删 P2，并在交付稿首节说明篇幅取舍。
- 数据自相矛盾：两值都列，标 `uncertainty`，不得擅自选一个。
- 材料涉密/未发表/含个人信息：不做外推，写“需授权确认后发布”。
- 缺引用/缺图表编号：不用占位数字补，写“原文未给编号，需补”，并进 `pending`。

---

## 14. 异常降级与鲁棒性

| 情形 | 行为 |
|---|---|
| `case.json` 缺失/坏 JSON | 递归查找含 `output_contract` 的 JSON；仍无则用内置字段并记录 degradation |
| PDF 无 `pdftotext` | 使用内置 PDF 流解析；质量低时标 `builtin-pdf-lowconf`，并要求人工核对 |
| 材料是图片 | 不 OCR，记 `image-no-ocr`，不臆造图注 |
| 材料解析失败 | 只降级该文件，其余继续；`degradations` 记文件名与原因 |
| 空输入/无材料 | 仍生成合法 `result.json`，`status=insufficient_evidence` 或 `input_error` |
| `draft.json` 缺失/不合格 | `build` 用确定性抽取兜底，写 `AUTO_EXTRACT`，`status=partial` |
| 超时/服务异常 | 保留 partial `result.json`；退出码 0 |

任何情况下必须返回合法 `result.json`，包含所有契约字段与 `case_id`，并如实说明缺陷。

---

## 15. 预算意识：用最少请求完成完整交付

推荐请求分配：

1. 基线生成与盘点：0-3 次模型请求。优先直接调用 `run` 生成全套确定性基线。
2. 读取关键原文：5-12 次。一次读取一个段落范围，不要重复读取同一段。
3. 填写 `draft.json`：15-25 次。先写正文骨架，再逐段补证据与措辞。
4. check/build/verify：3-8 次。一次修完所有 `[错误]`。
5. 自检与补契约：3-6 次。
6. 预留 3-8 次处理异常。

接近 780 秒或 60 次请求时，停止新增内容，立即运行 `build`，保证 `result.json` 合法、状态诚实、退出码 0。

---

## 16. rubric 维度到产物证据对照

| 评分维度 | 交付证据 |
|---|---|
| 实际效果 40：任务完成度 15 | `deliverable.md` 是完整可编辑成稿，不是建议或提纲；`sections` 为完整正文 |
| 实际效果 40：结果正确性 15 | 数字/单位/图表编号/引用与源文一致；`preserved_facts` 逐条 `quote+locator`；无新增事实 |
| 实际效果 40：结果完整性 5 | P0 必保留项完整；`removed` 写出被删内容及理由；`change_log` 区分删改性质 |
| 实际效果 40：结果可核验性 5 | `evidence_map` 逐段对照；`change_log` 可逐条复核；`pending_human` 明确待确认项 |
| 使用增益 25 | `glossary` 锁定术语；`transformation_spec` 给出受众策略；`preserved_facts` 降低返工；`self_check` 给出核验结论 |
| 创新增益 15 | 形成“受众画像→取舍策略→边界标注→多文体映射”链条；`sections[].strength` 展示论据强度分级 |
| 可靠体验 10 | 全流程幂等、退出码 0；`degradations`/`errors` 如实记录异常；空输入也能产出合法 result.json |
| 生态贡献 10 | `references/draft-schema.md` 定义字段；`references/genre-playbook.md` 提供体裁规则；`scripts/verify.py` 提供复核；SKILL.md 含自检清单与最小示例 |

---

## 17. 自检清单（收尾前逐项检查）

- 已真实读取 `/input` 下实际材料，不是按文件名或领域标签猜测。
- `deliverable.md` 含：适配说明、成稿正文、逐段对照、必保留项、改动记录、术语表、待确认项、自检说明。
- `evidence_map` 与成稿中 `[S#]` 标注一致。
- 无新增源文没有的数字、文献、机构、商业结论。
- 所有数字、图表编号、术语均可回溯到原文。
- `result.json` 顶层与嵌套 `output_contract` 均包含原契约束全部字段与 `case_id`。
- `status` 与实况一致；`sources`、`uncertainty`、`pending_human`、`errors`、`degradations` 已如实填写。
- 若契约要求 Office/幻灯片/图形，已尽力生成真实预览；无法生成已记 degradation。
- 退出码为 0；任何异常都已写入对应字段。
- 兜底路径的 `AUTO_EXTRACT` 已明确写进 `degradations`/`change_log`。
- 基线产物与 Agent 增强后的产物共用同一套文件契约，字段不因路径切换而缺失。

---

## 18. 最小调用示例

示例输入：

`/input/case.json`：

`case_id: EXAMPLE-NOT-A-TEST-CASE`

`task_instruction: Synthetic interface example only; actual task inputs are supplied at evaluation.`

`output_contract: case_id, deliverable, preserved_facts, evidence_map, change_log`

示例调用：

`python3 scripts/main.py run --input /input --output /app/output --work /app/work`

输出摘要：

材料索引 S1 `demo_paper.md` text 820 字/6 段  
受众：产业界 ← `产业界`  
体裁：技术转化简报  
篇幅：1200 字  
契约：5 字段已回填  
产出：`deliverable.md`、`evidence_map.md`、`preserved_facts.md`、`change_log.md`、`result.json`  
状态：`partial`（示例材料，非正式案例）  
说明：本示例仅用于接口证明，不是正式测试结果。