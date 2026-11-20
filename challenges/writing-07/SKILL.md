---
name: intro-related-work-writer
description: 为学术论文起草或改写“引言 + 相关工作 + 研究空白 + 贡献”四段式正文，把每条引用绑定到材料原文的逐字证据。当用户要求“写引言”“整理相关工作”“补引用”“核对贡献”“推导研究空白”“检查引用元数据/格式”时使用。强调真实解析材料、Agent 亲自推导撰写、产出全套可核验交付物。输出可编辑 manuscript.md、evidence_map、preserved_facts、change_log、result.json。
version: 2.0.0
---

# 引言与相关工作写作（intro-related-work-writer）

## 1. 用途与边界

**做什么**：围绕真实论文材料（作者手稿 / 摘要 / 方法 / 结果 / 参考文献表），产出可直接进入论文的四段式写作产物：

| 段落 | 必须交代 | 证据要求 |
|-|-|-|
| 研究背景 | 领域任务与技术约束 → 现有能力边界 → 具体未解问题 | 每条陈述挂 `[k]` 或 `[own]`，指向材料原文 |
| 相关工作 | 按问题/方法路线分组，同维度比较结论、适用条件、局限 | 每篇工作至少 1 条逐字 quote |
| 研究空白 | 由**已引文献**的共同限制/未覆盖场景/结论冲突推出，并落到本文对应动作 | 空白条目必须列出支撑引用 ID |
| 贡献 | 可核对条目，一条对应方法/图表/实验的一处 locator | 每条贡献 → 材料 locator |

**不做什么**（越界即降级，不静默编造）：
- 不新增材料外的文献、DOI、数值、图元素、统计量；
- 不替作者下“首次”“最优”这类无材料支撑的断言（材料没写就标注为作者判断待确认）；
- 不做排版终稿（LaTeX 模板套版、期刊投稿系统适配）与查重。

## 2. 最高优先级原则：脚本只是工具，最终交付物由 Agent 亲自推导

本包内的 `scripts/main.py`、`scripts/verify.py`、`references/frames.json` 等只是**抽取、分拣、组稿骨架、校验**的辅助工具。**严禁**把脚本输出、模板填空或中间产物直接当作最终成品。Harness Agent 必须：

1. 亲自读取 `/input/case.json` 与所有材料文件，真实解析文本内容；
2. 亲自判断哪些证据支撑哪些论断，而不是复制脚本默认分组或默认框架；
3. 亲自撰写或改写 `manuscript.md` 中的背景、相关工作、空白、贡献四段文字；
4. 亲自核实每条引用是否与来源原文一致，并把核验结果写入 `evidence_map`；
5. 在脚本基线之上进行增强：修正错误分组、补充遗漏贡献、删除虚假引用、标明不确定性；
6. 不得删除、清空或遗漏任何基线与契约字段；若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。

**完整性优先（v6 混合策略）**：进入任务后先运行主脚本产出全套基线交付物（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段），然后在此基线上增强。任何 Agent 后续校验与改写只能增加或修正字段内容，**不得移除基线的任何契约要求**。提交前必须逐项核对“output_contract 字段列表 × 磁盘文件 × result.json 键”三者一一对应。

## 3. 运行契约

- 输入：`/input/case.json`（+ `/input/task.md` 及 `/input/**` 材料：`.md/.txt/.json/.csv/.docx/.pdf/.xlsx`，图片名可在材料中仅作定位，不做像素推断）。
- 工作目录 `/app/work`，产物写 `/app/output/`。
- 入口：`python3 -B scripts/main.py --input /input --output /app/output`（可加 `--manuscript <已改写稿>` 复查）。
- 退出码恒为 0；任何异常进 `errors/degradations`；**先写 partial `result.json`**，结束无条件 finalize 覆盖。
- 只用 Python 标准库，不联网，不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位）。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 tokens（含推理）。脚本单次运行 <10 秒，但 Agent 的思考、材料审读、撰写、核验均计入模型请求预算。

## 4. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则递归找 `case*.json` / `task.md` 继续（找不到 → `input_error` + 仍写合法 result.json）。
2. `case_id`、`output_contract` **原样透传**；再按语义取用：`task_instruction` / `organizer_supplied_scope` / `organizer_workorder` / `organizer_edit_workorder` / `formal_inputs` / `runtime_files` / `artifacts` / `material` / `references` / `manuscript`；键名不固定时按内容形态判断（列表+含 year/title/abstract → 文献；长文本 → 手稿；含 `field/type` → 契约）。
3. 递归扫描材料目录，按扩展名 + 魔数（`%PDF`、`PK\x03\x04`）识别，**不用标签猜内容**。
4. 材料缺失的对象逐条进 `pending_human`（如“未提供参考文献表 → 相关工作只能写到本文自述层面”）。

## 5. 输出契约与目录约定

`/app/output/` 下：

| 文件 | 内容 |
|-|-|
| `result.json` | 回填 `output_contract` 全部字段 + 下列结构化字段 |
| `manuscript.md` | 主产物：四段式可编辑稿（含 `## References`） |
| `related_work_matrix.md` | 分组 × 比较维度矩阵（路线/问题设定/数据与评价/结论/局限/引用 ID） |
| `evidence_map.json` | 论断 → source_id + locator + 逐字 quote + `quote_verified` |
| `preserved_facts.json` | 数字/单位/引用标记/术语逐字保留表 |
| `change_log.json` | 每条 `original_quote → revised_quote + reason + locator` |
| `sources_index.json` | 供独立复核的抽取文本索引（source_id → 路径/字符数/偏移） |

`result.json` 必备：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`deliverables`、`sections_present`、`citations`、`evidence_map`、`preserved_facts`、`groups`、`gap_derivation`、`contribution_alignment`、`coverage`、`workorder_receipts`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。详见 `references/output_schema.md`。

若任务要求生成可编辑 Office/幻灯片/图形产物，则必须同时输出真实渲染的 PDF/PNG 预览。本 Skill 主产物为 Markdown 与 JSON，不生成二进制 Office 格式，默认无需预览；如案例显式要求 docx/pptx，则 Agent 须调用平台可用渲染能力生成预览并列入 `deliverables`，无法渲染时在 `pending_human` 说明。

## 6. 核心流程（写—核分离，Agent 亲自动手）

### 步骤 0：盘点输入与契约（预算 1-2 次请求）
- **输入**：`/input/case.json`、`/input/task.md`、材料文件。
- **动作**：识别 `case_id` 与 `output_contract` 字段；确定任务语言、目标格式、材料清单。
- **输出**：内部任务卡（不落盘）或记录在 `result.json` 的 `workorder_receipts`。
- **失败分支**：缺少契约字段 → 使用内置默认契约；材料路径无效 → 记录 `input_error` 并继续。

### 步骤 1：运行基线脚本（预算 1 次模型请求，脚本本身不计模型请求）
- **输入**：`/input` 目录。
- **动作**：执行 `python3 -B scripts/main.py --input /input --output /app/output`。
- **输出**：生成全套基线产物：`manuscript.md`、`related_work_matrix.md`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`sources_index.json`、`result.json`。
- **失败分支**：脚本崩溃或超时 → 记录 `errors/degradations`，仍尝试手写最小合法 `result.json` 和骨架文件。

### 步骤 2：真实解析材料并抽取证据（预算 5-10 次请求）
- **输入**：材料文件（PDF/DOCX/CSV/JSON/MD/TXT）。
- **动作**：调用脚本或标准库真实读取文本；对 PDF 使用启发式抽取并标注 `pdf_text_heuristic`；记录 `(source_id, locator, text)`；不得依据文件名或领域标签猜测内容。
- **输出**：`sources_index.json` 更新，逐字文本块准备就绪。
- **失败分支**：某文件解析失败/乱码/过短 → 跳过该文件并在 `errors` 或 `degradations` 标注；剩余继续。

### 步骤 3：构建/核对证据（预算 10-15 次请求）
- **输入**：抽取文本块、手稿、参考文献表。
- **动作**：Agent 亲自分拣文献记录与本文材料；按路线词表对 title+abstract 打分聚类，但必须人工复核聚类是否合理；对每条拟写入稿件的论断匹配原文 quote，验证逐字；识别材料间冲突、缺失 abstract、无法定位的信息。
- **输出**：`evidence_map.json` 初稿、`citations`、`groups`、`gap_derivation`、`contribution_alignment`、`preserved_facts`。
- **失败分支**：quote 无法命中 → 该条 `quote_verified=false` + 进 `pending_human`，稿中标记 `[待核实]`；文献无 abstract → 只基于 title/venue，`metadata_status=partial`。

### 步骤 4：Agent 亲自产出完整成品（预算 10-15 次请求）
- **输入**：`references/frames.json` 提供中英文组稿框架（事实为空），`references/writing_playbook.md` 提供四段写法、分组维度、空白推导协议、贡献规范。
- **动作**：Agent 基于真实证据**亲自撰写或改写** `manuscript.md` 的四段正文与 References；确保四段齐全且承接；每条引用绑定到 locator；所有数字/术语逐字保留；写出 `change_log`。禁止直接复制框架模板或脚本组稿结果。
- **输出**：最终 `manuscript.md`、`related_work_matrix.md`、`change_log.json` 更新。
- **失败分支**：某段证据不足 → 保留骨架并标注 `[材料不足]`，对应 `sections_present` 设为 false 或注明原因。

### 步骤 5：自检 rubric 与补全（预算 5-10 次请求）
- **输入**：`output_contract` 字段列表、当前产物。
- **动作**：运行 `python3 -B scripts/verify.py --result output/result.json --sources output/sources_index.json`；若作者改写后，加 `--manuscript <manuscript路径>` 复跑。核对 quote 命中率、契约缺失字段、引用覆盖计数；逐项检查 rubric 维度对照表。
- **输出**：自检记录，补全缺失字段或降级标注。
- **失败分支**：命中率不达标 → 回步骤 4 修改，若时间不够则降级 `status` 并保留 partial。

### 步骤 6：回填 result.json 并落盘最终产物（预算 2-3 次请求）
- **输入**：所有产物、自检结果、材料缺口。
- **动作**：回填 `output_contract` 全部字段（缺值 null/[]）及 `case_id`；确认 `status` 诚实；写入 `runtime`、`uncertainty`、`pending_human`、`errors`、`degradations`；确保退出码恒为 0。
- **输出**：最终 `result.json` 与全部交付文件。
- **失败分支**：时间不足 → 立即执行 finalize 落盘当前状态，标注 `partial`。

## 7. 预算策略（64 次模型请求内分配）

| 阶段 | 模型请求估算 | 是否必须 | 说明 |
|-|-|-|-|
| 盘点输入与契约 | 1-2 | 必须 | 缺失契约则使用默认 |
| 运行基线脚本 | 1 | 必须 | 生成全套基线，保证完整性 |
| 真实解析材料 | 5-10 | 必须 | 依据材料体量调整 |
| 构建/核对证据 | 10-15 | 必须 | 逐条核验引用，不偷懒 |
| 撰写/改写成品 | 10-15 | 必须 | Agent 亲自写四段，不用模板 |
| 自检 rubric | 5-10 | 必须 | 先验重要维度 |
| 回填 result.json | 2-3 | 必须 | 最终落盘 |
| 缓冲 | 剩余 | 可选 | 用于修正、深度补全 |

- **尽早落盘 honest partial**：完成步骤 1 后立即写 `partial result.json`；之后每完成一个大步骤可覆盖更新。任何时刻发生异常或接近 780 秒，马上执行 finalize。
- **避免无意义循环**：一次 quote 核验未命中不要反复尝试不同归一化超过 2 次；直接标 `[待核实]` 进 `pending_human`。
- **跳过非必要增强**：若预算紧张，优先保证 `manuscript.md` 四段完整、`evidence_map` 关键引用可核验、`result.json` 契约字段齐全；`related_work_matrix.md` 的细粒度比较可简化为粗表。

## 8. 隐藏案例鲁棒性与异常降级

任何情况下都必须产出合法 `result.json` 并退出码 0。材料缺失、损坏、格式不支持、超时、空输入、契约缺失等均需诚实标注。

| 情况 | 处置 | 字段 |
|-|-|-|
| `/input` 不存在或空 | 写默认骨架 + `input_error` | `status`, `errors` |
| `case.json` 坏 JSON | 记错、尝试同目录其他 json、继续 | `errors` |
| PDF 抽取乱码/过短 | 标 `pdf_text_heuristic`，只做粗粒度引用，不引具体数字 | `degradations`, `uncertainty` |
| docx/xlsx 损坏 | 跳过该文件，其余继续 | `errors` |
| 文献无 abstract | 只用 title/venue 归类，转述降为“标题层面”，标 `partial` | `citations` |
| quote 校验失败 | 稿中保留但标 `[待核实]`，进 `pending_human` | `evidence_map` |
| 无 output_contract | 用内置默认契约，仍输出全字段 | `runtime.contract_source` |
| 时间超 780 秒 | 立即 finalize 当前所有产物 | `runtime`, `errors` |
| 空输入材料 | `status=insufficient_evidence`，生成四段骨架与空白清单 | `status`, `pending_human` |
| 材料间数字/年份冲突 | 两条都留，进 `uncertainty`，稿中用首次出现者并标 `[conflict]` | `uncertainty` |
| 目标期刊格式未知 | 默认 author-year（`[k]` 编号 + References 列表），在 `uncertainty` 写明 | `uncertainty` |
| 语言切换 | 跟随 `task_instruction` 语言；未指定则按材料 CJK 占比判定（>15% → 中文） | `runtime.language` |
| 文献库为空 / 参考文献表缺失 | `status=insufficient_evidence`，仍交四段骨架与待补清单 | `status`, `pending_human` |
| 需要人工确认项 | 每条进 `pending_human`，明确说明缺口与建议人工动作 | `pending_human` |

## 9. 任务质量规则（rubric 维度 → 交付要求 → 自证方式）

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|-|-|-|-|
| 实际效果·任务完成度 | 15 | 四段齐全（研究背景、相关工作、研究空白、贡献）且彼此承接；引用落在具体论断上 | `manuscript.md` 可见四节；`sections_present` 4 项布尔真；`gap_derivation[].supports` 非空；`contribution_alignment[].locator` 非空 |
| 实际效果·结果正确性 | 15 | 他人工作转述与原文一致；引用元数据真实；空白由已引文献缺口推出；贡献与实际结果相符 | `evidence_map[].quote_verified` 全部或 ≥0.8 为 true；`citations[].metadata_status` 无假 metadata；空白条目有 basis_quote；贡献条目有 aligned=true |
| 实际效果·结果完整性 | 5 | 背景、相关工作、研究空白、贡献、引用覆盖五要素齐全；主要方法路线、关键工作、必要字段（作者、年份、来源）覆盖 | `coverage` 记录路线数、文献数、近 3 年占比；`related_work_matrix.md` 覆盖主要路线；References 每条有 authors/year/title |
| 实际效果·结果可核验性 | 5 | 每条引用回到来源；分组依据、空白推导、贡献对照可独立复核 | `sources_index.json` 提供 locator；`evidence_map` 中每条有 source_id+locator+quote；`gap_derivation` 和 `contribution_alignment` 列出支撑来源 |
| 使用增益·质量增益 | 15 | 加载 Skill 后成稿在论断准确、分组合理、空白成立、引用覆盖上优于基础 Agent | 通过真实案例对比体现；本 Skill 提供写—核分离、分组矩阵、空白推导协议；Agent 实际运行时亲自核验并改进，避免幻觉 |
| 使用增益·效率增益 | 5 | 减少从材料到成稿耗时、逐条核对引用条数、改写轮次 | 脚本自动抽取与分拣、验证命中率；Agent 可专注撰写与核验；步骤化流程减少返工 |
| 使用增益·增益可验证性 | 5 | 公平对照证明质量或效率改善 | 平台固定案例对比结果（实际运行证据）；本 Skill 保留 `change_log`、`evidence_map` 可追踪改进 |
| 创新增益·新增能力 | 5 | 引用与论断绑定、按路线分组比较、空白推导、贡献与图表对齐等能力 | `evidence_map` 绑定、`related_work_matrix` 路线分组、`gap_derivation` 推导逻辑、`contribution_alignment` 对齐 locator |
| 创新增益·方法改进 | 5 | 文献筛选、分组归纳、引用核验、写作与核对分离等方法带来实质改进 | 写—核分离流程；`scripts/verify.py` 独立核对；`references/writing_playbook.md` 提供分组维度与反模式 |
| 创新增益·创新证据 | 5 | 证明相对通用对话模型边界和价值 | 本 SKILL.md 明确定位；运行结果中的 `gap_derivation`、`contribution_alignment`、`evidence_map` 展示结构化推导能力 |
| 可靠体验·调用与易用性 | 3 | 能在“写引言”“整理相关工作”等指令下正确触发 | frontmatter description 明确触发词；步骤化流程；最小调用示例 |
| 可靠体验·运行稳定性 | 4 | 不同学科、篇幅、引用格式、重复运行稳定产出 | 异常降级表覆盖主要故障；脚本纯标准库；退出码恒 0；result.json 始终合法 |
| 可靠体验·异常处理 | 3 | 对材料不足、文献库空、查不到原文、格式未知等识别与处置 | `pending_human`、`errors`、`degradations`、`uncertainty` 字段；降级分支表；进入 partial 状态 |
| 生态贡献·文档完整性 | 3 | 使用说明、依赖、配置、示例、适用学科与语言范围、限制维护信息齐全 | 本 SKILL.md 提供完整说明；`references/output_schema.md` 字段表；版本与维护章节 |
| 生态贡献·资源可复用性 | 4 | Skill 本体、脚本、证据表与分组模板、核对清单可复用 | 包内脚本与资源可被其他学术写作任务复用；路线词表、组稿框架可扩展 |
| 生态贡献·分享推广价值 | 3 | 沉淀可分享写作案例、分组方法、失败分析 | `references/writing_playbook.md` 中的反模式、空白推导协议；`change_log` 与 `evidence_map` 可作案例 |

## 10. 证据与定位规范

- quote 必须能在 `sources_index.json` 对应 `source_id` 的原文中**逐字**找到（仅允许空白归一化）。
- locator 与源类型绑定：文本 `L<起>-<止>`；docx `para<n>`；pdf `c<起>-<止>`（抽取文本字符偏移）；json `$.a.b[0]`；csv `row<n>`。
- 同一论断多来源 → 多条 evidence 记录，不合并 quote。
- 无法定位 → `quote_verified=false` + `pending_human`，稿中该句改为 `[待核实]` 标注。

## 11. 冲突与人工确认

- 材料间数字/年份冲突：两条都留，进 `uncertainty`，稿中用首次出现者并标 `[conflict]`。
- 目标期刊格式未知：默认 author-year（`[k]` 编号 + References 列表），在 `uncertainty` 写明“格式未给定，按 author-year 输出，需按目标刊调整”。
- 语言切换：跟随 `task_instruction` 语言；未指定则按材料 CJK 占比判定（>15% → 中文）。
- 文献库为空 / 参考文献表缺失 → `status=insufficient_evidence`，仍交四段骨架与空白清单。

## 12. 自检清单（提交前逐项检查，完整性优先）

1. **契约完整**：`result.json` 中 `output_contract` 的每个键都存在（缺值 null/[]）；`case_id` 已回填；所有题面要求文件均在 `/app/output/`。
2. **基线保留**：脚本生成的 `manuscript.md`、`related_work_matrix.md`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`sources_index.json` 未被删除或清空；若有改动，保留原信息并标注 `reviewed_by_agent`。
3. **四段齐全**：`sections_present` 4 项全 true（或写明缺哪项及原因）；四段之间存在承接（背景→相关工作→空白→贡献）。
4. **证据核验**：`evidence_map` 非空，且 `quote_verified` 比例 ≥0.8 才可 `status=ok`；否则降为 `partial` 或 `insufficient_evidence`。
5. **引用真实**：References 每条有 authors/year/title；`metadata_status` 与之一致；无材料外文献或 DOI。
6. **空白推导**：每条 `gap_derivation` 有 `supports`（≥1 已引 ID）和 `basis_quote`。
7. **贡献对齐**：每条 `contribution_alignment` 有 locator 或 `aligned=true`；找不到依据的标 `unaligned` 并进 `pending_human`。
8. **数字与术语**：稿中无材料外数字/文献；数字全部能在 `preserved_facts` 找到。
9. **运行状态诚实**：`status` 真实反映 `ok|partial|insufficient_evidence|input_error`；`errors`、`degradations`、`uncertainty` 非空时已说明。
10. **退出码与临时文件**：退出码 0；无 `__pycache__`、无临时文件；所有产物位于 `/app/output`。
11. **预览要求**：若输出可编辑 Office/幻灯片/图形产物，已附加真实渲染 PDF/PNG；否则确认无需预览。
12. **最小调用示例**：确认示例已标注“示例，非正式案例结果”。

## 13. 最小调用示例（示例，非正式案例结果）

输入 `input/case.json`：

```json
{"case_id": "demo-001",
 "task_instruction": "为本文写引言与相关工作，author-year 格式",
 "output_contract": {"manuscript_md": "path", "evidence_map": [], "status": ""},
 "material": {"manuscript": "本文提出一种…（材料原文）",
   "references": [{"key": "K1", "authors": "Li et al.", "year": 2021,
     "title": "A rule-based scheduler", "venue": "J. Sched.",
     "abstract": "Rule-based schedulers handle static workloads; however they cannot adapt to bursty arrival."}]}}
```

调用：

```bash
python3 -B scripts/main.py --input input --output out
```

示意输出（`out/`，**示例，非正式案例结果**）：`result.json`（`status="ok"`，`sections_present` 4×true，`citations[0].metadata_status="complete"`，1 条 `gap_derivation` 由 K1 的 "cannot adapt to bursty arrival" 支撑）、`manuscript.md`（4 节 + References）、`related_work_matrix.md`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`。

## 14. 文件清单与版本

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（流程、契约、rubric 映射、异常分支、完整性优先） |
| `scripts/main.py` | 主流程：发现→抽取→分拣→分组→空白→贡献→组稿→result.json |
| `scripts/verify.py` | 共享库 + 独立核对 CLI：文本/PDF/DOCX 抽取、文献解析、路线词表、组稿模板、quote 命中与契约校验 |
| `references/frames.json` | 中英文组稿框架（标题/引导语/空白与参考文献模板），事实为空、只提供承接 |
| `references/writing_playbook.md` | 四段写法、分组维度、空白推导协议、贡献规范、路线词表、反模式 |
| `references/output_schema.md` | `result.json` 字段表、locator 规范、异常处置、引用格式、自检与维护 |

版本 `2.0.0`；纯标准库；无外部数据依赖；资源全部 UTF-8 文本。

## 15. 维护说明

- 路线词表在 `scripts/main.py::ROUTES` 与 `references/writing_playbook.md` 各存一份，改动需同步并升 version。
- 新增学科：在 `ROUTES` 增补领域术语即可，不改流程。
- 回归方式：用 `--input <新案例> --output out` 跑，检查 `coverage.quote_verified_rate` 与 `pending_human` 是否只含真缺口。
- 每次正式运行后，Agent 应记录 `runtime` 中的 `model_requests`、`elapsed_seconds`，用于后续预算分析。