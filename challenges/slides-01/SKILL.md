---
name: paper-to-academic-slides
description: Convert one research paper (PDF/DOCX/MD/TXT) plus an optional target template deck into an editable academic presentation — mainline page plan, per-slide evidence with verbatim quotes and figure/table/section locators, speaker notes kept separate from slide text, template-inheriting .pptx, real PDF export, and a result.json that fills the case output_contract. Use for 论文转学术 PPT / paper-to-slides / 学术汇报 / 组会汇报 / 会议报告 / 模板适配汇报 / deck revision from a paper.
version: 2.0.0
---

# 论文转学术 PPT（paper-to-academic-slides）

将一篇科研论文转换为**页级、证据可回溯、可编辑、可放映**的学术汇报 PPT。每个页面承载一个明确主张，主张必须能回溯到论文的具体图、表、章节或句子；最终交付物包括模板继承的 `.pptx`、真实渲染的 `.pdf`、结构化证据映射和完整的 `result.json`。

**重要约束：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 本包中的 `scripts/main.py` 和 `scripts/deckbuild.py` 负责发现、提取、版式、渲染和机器检查；它们产出的 `deck_model.json` / `plan.json` / `content_map` 只是**基线与容器**，不能未经 Agent 核验与改写就直接当作成品。禁止把脚本骨架、模板占位内容或自动段落当作最终答案；你必须基于原始论文的真实内容独立完成主线提取、主张撰写、证据选择与讲解备注，并将核验结果写入 `result.json`。

## 1. 运行时契约与资源限制

| 项 | 要求 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、论文材料（PDF/DOCX/CSV/图片等） |
| 工作目录 | `/app/work`（中间文件、提取文本、修改中的 deck_model） |
| 最终输出 | `/app/output`，必须包含 `result.json` 且含原 `output_contract` 全部字段与 `case_id` |
| 可编辑 Office/幻灯片产物 | 必须额外给出真实渲染的 PDF/PNG 预览 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理） |
| 资源限制 | Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink |
| 退出码 | 任何情况下退出码 0；失败/部分成功写入 `result.json` 而不是崩溃 |
| 诚实性 | 状态、来源、不确定性、变更记录必须真实；不确定或材料不足显式标注 `pending_human` / `limitations`；不得编造数据、引用、分数 |

## 2. 输入与输出契约

- **发现规则**：
  1. 读取 `/input/case.json`；若缺失，搜索输入树中的 `case*.json`，仍无则继续用默认值。
  2. 保留 `case_id` 和 `output_contract` 原样（未知字段保留，缺失值用 `null`/`[]`）。
  3. 工作指令从任意包含 slide 键的 case 子字典或 `*workorder*.json` / `slide*spec*.json` 读取；字段包括 `mode`、`total_slide_count`、`source_preservation`、`template_inheritance`、audience、duration、language；其他内容原样回显到 `deck_model.workorder.raw`。
  4. 论文文件：第一个大于 1.5KB 的 `pdf|docx|md|txt`，且不是 `task.md`/`README`。
  5. 模板：文件名匹配 `template|master|layout|style|brand` 的 `.pptx`；否则第一个 `.pptx`（起始 deck 作为模板基座）。无 `.pptx` 则使用内置 master/layout/theme，并记录为降级。
  6. 缺失或不可读的内容必须进入 `exceptions` / `pending_human`，不得凭空补造。

- **`result.json` 必须包含所有原始 `output_contract` 字段**，并填充以下标准字段（详参 `references/output-schema.md`）：
  - `editable_source`: `{path, format:"pptx", slides, bytes, sha256, engine, notes_slides, template:{path, master, layouts_used, inherited}}`
  - `export_artifact`: `{pdf:{path, pages, engine, valid}, png:{dir, count}}`（PDF 为渲染证据；PNG 可选，可根据实际能力提供）
  - `content_map`: `{unit:"slide", slides:[{n, title, role, claim, bullets, evidence:[{type,id,locator,quote,matched}], assets, notes}], coverage:{slides, with_evidence, evidence_items, quotes_matched}}`
  - `compliance_checks`: `slide_count`、`template_inheritance`、`overflow`、`notes_coverage`、`notes_overlap`、`figure_refs`、`number_whitelist`、`evidence_coverage`、`mode`、`fonts`、`files`、`pass`、`failures[]`
  - `exceptions[]`、`degradations[]`、`pending_human[]`、`uncertainty[]`、`changes{}`、`sources{}`、`runtime{}`、`errors[]`
  - `status ∈ ok | partial | input_error`

- **唯一主命令**（始终可用，退出码 0）：
  ```
  python3 <skill>/scripts/main.py --input /input --output /app/output --work /app/work
  ```
  `<skill>` 安装路径为 `/skills/weekly-skill`。执行时使用实际路径。

## 3. 本题专属执行流程（完整性优先 v6 混合策略）

> 核心原则：**先跑基线，再增强；保留全部基线产物；缺一补全；逐项核验。** 流程中每个步骤都要有输入、动作、输出和失败分支。所有产物最终由 Agent 亲自核验并落盘。

### 步骤 0：初始化与预算感知落盘
- **输入**：`/input/case.json`、`/input/task.md`、包内脚本路径。
- **动作**：
  1. 读取 `case.json`，提取 `case_id` 与 `output_contract`。
  2. 确认 `/app/work` 与 `/app/output` 存在（不存在则创建）。
  3. 立即写一个**合法的部分 `result.json`** 到 `/app/output`，包含所有 `output_contract` 字段和 `case_id`，`status=partial`，`errors` 标注“任务初始化中，尚未完成提取与核验”。这保证超时或后续失败时仍有可交付骨架。
- **输出**：初始 `result.json`、目录就绪、已知契约字段清单。
- **失败分支**：若 `/input/case.json` 不存在且找不到 `case*.json`，仍写 `result.json`（含 `case_id: null`），`status=input_error`，记录“缺失 case.json”，退出码 0。

### 步骤 1：盘点输入与读取工作指令
- **输入**：`/input` 下所有文件、上一步的 `result.json`。
- **动作**：
  1. 列出 `/input` 全部文件，按扩展名分类（论文、模板、工作指令、辅助材料）。
  2. 阅读 `task.md` 的 Runtime contract 和任何具体页数/受众/模板要求。
  3. 若 `case.json` 中有 `organizer_workorder` 或幻灯片规格，提取页数、模式、模板继承、来源保留等字段。
  4. 将发现的文件路径和类型记录到工作日志（可写入 `/app/work/discovery.json` 或保留在 Agent 推理中）。
- **输出**：明确的输入清单、论文路径、模板路径（可选）、工作指令。
- **失败分支**：论文缺失 → `status=partial`，`exceptions` 记录“无论文文件”，停止生成 PPT，但仍写合法 `result.json`。模板缺失 → 内置模板，记录在 `degradations`。

### 步骤 2：真实解析材料内容
- **输入**：论文文件（PDF/DOCX/MD/TXT）、可用的解析工具（如 `pdf-text-tool`、`pdftotext`、包内 extraction 链）。
- **动作**：
  1. **必须真实解析论文内容**，不得依据文件名或领域标签猜测/补造。优先使用包内脚本的提取链：运行 `scripts/main.py --input /input --output /app/output --work /app/work`，它会执行发现、提取、基线页面规划、模板继承、pptx 构建、PDF 导出和机器检查。
  2. 脚本运行后，检查 `/app/work` 下是否生成了提取文本、段落、句子、图/表标题列表等中间文件；若有，**Agent 亲自阅读**这些提取内容，并与原始 PDF 的可读部分（如可用工具查看前几页）核对。
  3. 若脚本提取结果为空或质量差（见异常分支），Agent 应使用独立工具再次提取，或读取 `.txt/.md` 直接获取文本。
  4. 提取的关键信息：研究问题、方法、结果、讨论、限制、结论、图表编号与标题、关键数字/单位、章节/页码定位。
- **输出**：提取文本或结构化中间文件、图/表标题列表、关键数字与引用定位。
- **失败分支**：加密/扫描 PDF、无文本层、提取字符数 <200 → `status=partial`，`exceptions` 记录“不可提取文本”，不生成 PPT。材料可读但缺图/表标题 → 继续，但页面证据降级为页/节定位，`pending_human` 提示确认图表列表。

### 步骤 3：Agent 亲自构建/核对证据与内容模型
- **输入**：步骤 2 的提取内容、脚本生成的基线 `deck_model.json` / `plan.json`（若已生成）、`references/page-outline.md` 的页角色规则。
- **动作**：
  1. **独立推导主线**：不是按段落顺序搬运，而是按论文贡献组织 `motivation → approach → method → evidence（每图/表一页）→ discussion → limitation → conclusion` 的叙事骨架，根据总页数裁剪角色优先级（详见 `references/page-outline.md`）。
  2. **逐页撰写主张**：每页一个主张，主张必须来自原文句子或从句，不得添加论文没有的事实；bullet ≤5 条，必须是从原文句子切出的短语，数字/单位/方法名/结论表述不做任何改写。
  3. **为每页选择证据**：每条证据包含类型、编号、定位（页码/节）、原文引用句；所有引用必须经过与提取文本的精确匹配校验（`matched` 字段）。
  4. **撰写讲解备注**：备注与页面文字分离，包含过渡语、强调点、可能被问到的补充证据；不得复述 bullets。
  5. **核对数字和图表引用**：每页出现的数字/百分比必须能在原文中找到；每页提到的 Figure N / Table N 必须存在于论文的图表标题列表。
  6. 将最终内容模型写入 `/app/work/deck_model.json`（Agent 亲自编辑或由 Agent 指令重写），确保该文件代表 Agent 的完整推导结果。
- **输出**：经 Agent 核验的 `deck_model.json`、`plan.json`、逐页证据映射。
- **失败分支**：若脚本基线内容质量不足，Agent 必须覆盖 `deck_model.json` 的相应字段；若脚本尚未生成模型，Agent 直接按 `references/output-schema.md` 的 schema 自行创建。任何不确定的引用/数字/图表 → 投入 `uncertainty` / `pending_human`，不得保留错误内容。

### 步骤 4：渲染生成与增量改进
- **输入**：经 Agent 核验的 `deck_model.json`、模板（若有）、包内脚本。
- **动作**：
  1. 使用同一主命令重新运行脚本，使其基于修改后的 `deck_model.json` 生成/更新 `.pptx` 和 `.pdf`。
  2. 确认输出文件：`/app/output/presentation.pptx`、`presentation.pdf`、`plan.json`、`deck_model.json`。若脚本不支持基于已有 `deck_model.json` 重建，则 Agent 应直接调用 `scripts/deckbuild.py` 中的构建函数（用 Python 交互）重新生成；若无法重建，至少保留已核验的 `deck_model.json` 和基线 `.pptx`，并在 `result.json.changes` 中说明“脚本重建限制，内容以 deck_model.json 为准”。
  3. 检查模板继承（theme/master hash 是否保持）、页数、溢出、字体等机器检查项。
- **输出**：更新后的可编辑 `.pptx`、渲染 `.pdf`、机器检查报告。
- **失败分支**：无 Office 渲染器 → `.pdf` 缺失或 `valid=false`，保留 `.pptx`，在 `degradations` 记录。模板附占位符不足 → 使用绝对文本框，记录降级。页数不符 → 调整大纲或裁剪，仍不满足则在 `compliance_checks.failures` 标记。

### 步骤 5：完整性自检与 rubric 核对
- **输入**：`/app/output` 全部产物、`references/checklist.md`、`references/output-schema.md`。
- **动作**：
  1. 逐项核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐。
  2. 检查所有必需文件存在且非空：`result.json`、`presentation.pptx`、`presentation.pdf`、`plan.json`、`deck_model.json`。
  3. 运行脚本自带的 `compliance_checks`，并手动复核关键项：主线连贯性、证据准确性、数字未改写、图表引用匹配、备注不重叠、模板继承。
  4. 若有任一 `compliance_checks.pass = false`，修复对应问题并重新渲染，直到通过或明确记录无法通过的原因。
- **输出**：机器+人工双检通过或带说明的失败项。
- **失败分支**：预算不足 → 保留当前 best-effort 产物，确保 `result.json` 合法；在 `errors` 中记录“自检未完全完成”。

### 步骤 6：回填 result.json 与最终提交
- **输入**：步骤 4/5 的所有产物、Agent 推理记录。
- **动作**：
  1. 在基线 `result.json` 上增强，填入 Agent 实际核验结果：
     - `reviewed_by_agent: true`
     - `verifications` 数组：每页或关键论断的核验状态（`verified` / `pending_human` / `conflict`），记录核验依据。
     - `changes`：记录 Agent 对基线模型做了哪些修改。
     - `sources`：记录实际读取的文件、解析引擎、版本。
     - `uncertainty` / `pending_human`：列出不确定项和需人工确认项。
  2. 确认 `status` 真实：全部通过且证据匹配 → `ok`；有降级或未证实 → `partial`；输入缺失/不可读 → `input_error`。
  3. 无条件覆盖写入 `/app/output/result.json`，保证所有 `output_contract` 字段齐全、`case_id` 正确。
- **输出**：最终 `result.json`、全部交付物。
- **失败分支**：写入失败或字段缺失 → 在 `/app/work` 保留临时文件并重试，保证最终 json 可解析且退出码 0。

## 4. 预算策略（64 次模型请求 / 900 秒）

**总原则**：先完成评分权重最高的实际效果（主线成立、证据准确、可编辑渲染），再补完整性和可核验记录；尽早落盘 partial，避免无意义循环。

| 阶段 | 建议模型请求 | 必须完成的关键动作 |
|---|---|---|
| 初始化 + 盘点 | 2-4 | 写 partial result、识别论文/模板/契约 |
| 材料解析 | 5-10 | 调用脚本 or 工具提取文本；Agent 阅读关键段落；定位图表 |
| 主线与逐页撰写 | 12-20 | Agent 亲自推导页角色、claim、bullets、evidence、notes；核对数字与图表 |
| 渲染与验证 | 3-6 | 重跑脚本生成/更新 pptx/pdf；检查模板与导出 |
| 完整性自检 | 3-6 | 字段×文件×键逐项核对；修复缺失 |
| 回填与收尾 | 2-4 | 写入核验记录、状态真实、最终 result.json |

- **预算紧张时**：跳过非关键性调优（如额外排版美化、冗余自检），优先保证 `presentation.pptx`、`presentation.pdf`、`result.json`、`deck_model.json` 四件套内容完整且证据可回溯。
- **何时落盘 partial**：步骤 0 必须落盘骨架；步骤 2 基线脚本跑完后再覆盖一次；步骤 4 渲染后更新；步骤 6 最终覆盖。每次落盘都包含全部契约字段。
- **避免冗余**：不重复运行相同提取；不重复生成同样的错误；一次脚本调用能完成的多项检查不要拆成多次模型请求。

## 5. 隐藏案例鲁棒性

| 异常情况 | 检测方法 | 降级/处理 | 状态与记录 |
|---|---|---|---|
| `case.json` 缺失/损坏 | JSON 解析失败或文件不存在 | 使用默认空契约；`case_id=null`；`status=input_error` | `errors[]`，退出码 0 |
| `output_contract` 缺失 | 字段不存在 | 以标准字段集合填充，并记录 | `exceptions` |
| 论文文件缺失 | 输入树无 pdf/docx/md/txt | 不生成 PPT；`status=partial` | `exceptions`，`pending_human` |
| PDF 加密/扫描/无文本层 | 提取字符 < 200 | 不生成 PPT；记录材料不可用 | `status=partial`，`pending_human` |
| 图/表标题缺失 | 标题正则无匹配 | 证据降级为页/节定位；`pending_human` 请求确认图表列表 | `degradations` |
| 模板缺失或占位符不足 | 无 `.pptx` 或扫描无 body placeholder | 使用内置 master/layout/theme；绝对文本框 | `degradations` |
| 无 Office 渲染器 | `soffice`/`office-renderer` 不可用 | `.pptx` 仍交付；`pdf.valid=false`；`degradations` | `export_artifact.pdf.valid=false` |
| 页数约束不满/超限 | slide_count 检查失败 | 调整大纲或记录失败；不删除已交付内容 | `compliance_checks.failures` |
| 超时/预算耗尽 | 检测到剩余时间或请求不足 | 保留 best-effort 产物，确保 `result.json` 合法；`status` 根据实际完成度定 | `errors` / `runtime` |
| 空输入/空文本 | 文件存在但提取为空 | 视为“无文本层”；`status=partial`，不编造 | `exceptions` |
| 领域标签与实际材料不符 | 人工检查材料标题/摘要与任务说明冲突 | 以实际材料为准；记录冲突 | `sources` / `uncertainty` |

任何情况下：**必须产出合法 `result.json`（可解析 JSON），退出码 0。**

## 6. Rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 实际效果-任务完成度 | 15 | 真正把论文变成主线成立、页序可讲、模板可交付的学术 PPT；不是段落切块 | `content_map` 中每页 role/claim 反映贡献主线；`plan.json` 显示角色顺序；`changes` 记录 Agent 对基线的改写 |
| 实际效果-结果正确性 | 15 | 数字、单位、方法名、结论表述与论文一致；图表编号与引用对得上；不把示意图当数据 | 证据 `quote` 与原文精确匹配；`number_whitelist.misses=0`；`figure_refs.mismatch=0`；Agent 核验记录写入 `verifications` |
| 实际效果-结果完整性 | 5 | 主线必需页齐全，六类要素覆盖 | `content_map.coverage.slides` ≥ 要求页数；`compliance_checks.notes_coverage`、`evidence_coverage` 通过 |
| 实际效果-结果可核验性 | 5 | 每页内容回溯到具体图/表/章节/页码；页级金标准、源文件与导出文件齐全 | 证据条目含 `id, locator, quote, matched`；提供 `editable_source`、`export_artifact`、`sources` |
| 使用增益-质量增益 | 15 | 同输入下页级正确性、主线清晰度、版面合规稳定优于基础 Agent | 通过 `compliance_checks.pass`、`verifications` 展示改进；保留基线对比记录于 `changes` |
| 使用增益-效率增益 | 5 | 端到端耗时、人工修改页数下降 | `runtime` 记录实际耗时；`changes` 标注人工修改范围；不虚构基准分数 |
| 使用增益-增益可验证性 | 5 | 同输入、同模板、同版本公平对照 | `sources` 记录输入与版本；不编造未提供的白板或评分 |
| 创新增益-新增能力 | 5 | 图表定位与页级引用、模板占位符约束排版、备注与页面分离等新能力 | `content_map` 每条证据含图表定位；`template_inheritance` 显示占位符继承；备注与 bullets 重叠率低 |
| 创新增益-方法改进 | 5 | 主线提取、页结构映射、图表对齐、备注生成实质改进而非包装 | `deck_model.json` 体现 Agent 自己的主线推导；`changes` 记录独立改写 |
| 创新增益-创新证据 | 5 | 证明创新点相对通用方案/手工流程的边界与价值 | 在 `result.json` 中记录相对基线的差异与边界，不夸大 |
| 可靠体验-调用与易用性 | 3 | 用户能按说明用一篇论文跑出可打开、可编辑 PPT | SKILL.md 提供明确命令与步骤；`editable_source.engine` 记录生成引擎 |
| 可靠体验-运行稳定性 | 4 | 不同论文类型、模板、重复运行持续产出可打开结果 | 鲁棒性分支覆盖；`runtime` 记录单次进程；退出码 0 |
| 可靠体验-异常处理 | 3 | 图表无法提取、公式为图片、PDF 加密、模板占位符不足、字体缺失、页数超限的处置 | 异常分支表在 SKILL.md 和 `result.json.exceptions/degradations/pending_human` 中体现 |
| 生态贡献-文档完整性 | 3 | 使用说明、依赖、模板要求、限制、维护信息齐全 | SKILL.md 本文 + `references/checklist.md` |
| 生态贡献-资源可复用性 | 4 | Skill 本体、模板、页级大纲模板、证据映射表等可复用 | 包内文件清单明确，`references/page-outline.md`、`references/output-schema.md` 可被他人复用 |
| 生态贡献-分享推广价值 | 3 | 沉淀可分享案例、模板方法、实践经验 | 不要求预生成正式答案；SKILL.md 提供最小示例说明流程 |
| GitHub 公开链接（附加） | 5 | 有效链接，评审可免登录查看 | 不在 SKILL.md 内实现；提交目录根放置 `GITHUB_URL.txt` |

## 7. 自检清单（提交前逐项检查）

1. `/app/output/result.json` 存在且可解析，退出码 0。
2. `result.json` 包含所有原 `output_contract` 字段且键名不改，包含 `case_id`。
3. `presentation.pptx` 存在且非空，文件可打开。
4. `presentation.pdf` 存在且为真实渲染（或者记录 `pdf.valid=false` 的降级）。
5. `plan.json`、`deck_model.json` 存在且内容一致，无互相矛盾。
6. 每页 `claim` 来自原文句子或从句，无编造事实。
7. 每页 `bullets` ≤5 条，且为原文短语，数字/单位/方法名未改写。
8. 每页至少有 1 条证据，且证据 `quote` 与提取文本匹配，`locator` 指向正确页/节/图/表。
9. `figure_refs.mismatch = 0`；任何页提到的 Figure N / Table N 均存在。
10. `number_whitelist.misses = 0`；所有数字/百分比在原文中出现。
11. 备注与页面文字重叠率低于阈值（`notes_overlap` 检查通过）。
12. 模板继承：若提供了 `.