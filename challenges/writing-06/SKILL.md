---
name: paper-structure-logic-review
version: 2.0.0
description: 对一篇完整论文稿件做源文定位的六维结构诊断，交付作者可直接执行的结构修改方案；覆盖研究问题对齐、章节结构、论证链、段落关系、重复内容、结论边界，保留逐条引用与 locator、修改记录、不确定性、缺口与人工确认项。单命令运行，Agent-first 但带确定性兜底。
license: MIT
tags: [academic-writing, structural-review, argument-mapping, editing-plan]

## ★ 本 Skill 最高优先级：源文定位、可执行动作、诚实交付

1. 所有诊断必须从 `/input` 内真实材料抽取，不能依据文件名、领域标签、task 标题推断内容；PDF 必须读取真实文本，不能使用预置答案层。
2. 最终产物必须同时满足：定位到具体章节/段落/句子；说明属于哪一类结构问题；给出作者可直接执行的动作（移动到哪、与哪段合并、从哪拆、哪句需收窄、哪里需删/补）。
3. 任何事实、数字、术语、引用、图表、关键论断必须有 `[S#]` 来源与 `文件#行号/段落号` locator；无法回溯的内容不得进入最终产物。
4. 不能生成无依据的 benchmark/score/reference，不能自造 `golden_standard`；所有可核验性证据只能来自本 Skill 真实运行、`verify.py` 或 case 材料。
5. 脚本输出是基线与兜底，不是成品；Agent 必须阅读原文判断。若脚本已经给出 AUTO_EXTRACT 产物，应诚实标注在 `degradations`，不能假装是人工精读结果。

## 1. 用途、适用条件与不做清单

**用途**：对一篇完整科研稿件做结构级诊断，交付作者可编辑的、带来源映射的诊断与修改方案。

**触发条件**：用户给出完整稿件，要求结构诊断、逻辑优化、章节顺序、论证链、重复内容、结论边界、审稿意见中的结构问题处理，或要求逐段指出“问题在哪、怎么改”。

**不做**：
- 不做整篇改写、不另起一篇替代稿。
- 不做语言润色为主的工作。
- 不新增材料外数据、文献、图表、科学结论。
- 不把风格偏好当成结构错误。
- 不评判科学结论本身是否正确，只评判结构、论证、边界、重复、衔接。
- 不生成考题答案、隐藏测试、白板或伪造评分。

## 2. 单命令全流程入口

优先一次性执行：

    python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

该命令期望内部完成：
- `init`：盘点材料、分配来源编号 S1..Sn、抽取候选、分组冲突点。
- `build`：校验/兜底抽取/渲染全部产物/finalize `result.json`。
- `selfcheck`：检查产物与契约字段一致、JSON 合法、引用可回溯。

Agent 策略：
- 若 `run` 子命令可用，先执行它作为基线落地；然后再用原文核验与改进。
- 若脚本只支持旧接口或 `run` 不可用，则先执行：

      python3 -B scripts/main.py --input /input --out /app/work/baseline

  然后以 `/app/work/baseline` 为确定性台账，由 Agent 在 `/app/output` 完成最终交付，并执行：

      python3 -B scripts/verify.py --out /app/output --input /input

无论如何必须 exit 0；任何异常都捕获后写 partial `result.json`，最后无条件 finalize。

## 3. Agent-first 双路径

### 路径 A：Agent 真读真判

1. 初始化并读取台账：
   - 若支持子命令，执行 `python3 -B scripts/main.py init --input /input --work /app/work`；否则用 `baseline` 作为台账。
   - 读取 `/input` 全部材料原文。
2. 在 `${WORK}/draft.json` 写入 Agent 判断。`draft.json` 至少包含：

       case_id
       scope / main_manuscript
       findings: [{id, dimension, locator, quote, problem, action, severity}]
       claims: [{claim_id, locator, quote, support_refs, support_scope, strength}]
       repetition_groups: [{id, locators[], duplicate_type, action}]
       pending_human: [{item, reason}]
       uncertainties: [{item, impact}]

   每个字段必须来自原文，不套模板。
3. 运行 check / build：
   - 更推荐直接执行 `run`；若已 init，也可执行：

         python3 -B scripts/main.py check --work /app/work --output /app/output
         python3 -B scripts/main.py build --work /app/work --output /app/output
         python3 -B scripts/main.py selfcheck --work /app/work --output /app/output

### 路径 B：无 draft 时确定性兜底

- 若 `${WORK}/draft.json` 不存在，`build` 必须用 init 台账中的确定性抽取结果生成实质工作稿：逐字 quote + locator，不得因为“没有 Agent 判断”而交付空稿。
- 兜底产出的关键判断若来自 AUTO_EXTRACT，必须在 `result.json.degradations` 中诚实记录：

      {type: "AUTO_EXTRACT", scope: "baseline", status: "acknowledged", note: "该部分为脚本确定性抽取，Agent 未逐条精读或未能完成人工核验"}

- 两条路径必须产出同一套产物与同一份 `result.json` 契约。路径 B 不等同取消 Agent 责任；若预算允许，Agent 应继续补充 `agent_review.json` 和改进正文。

## 4. 输入发现与真实解析

1. 读取 `/input/case.json`，原样保留 `case_id` 与 `output_contract`。若 `case.json` 缺失，查找 `case*.json`。
2. 若 `output_contract` 存在，其中每个字段必须原样展开到 `result.json` 顶层，键名不改。
3. 语义读取以下字段（若存在）：`task_instruction`、`organizer_workorder`、`organizer_edit_workorder`、`organizer_supplied_scope`、`material_version`、`source`。
4. `organizer_workorder` / `organizer_edit_workorder` 逐项执行，并在 `workorder_receipts` 中回报：`done` / `not_applicable` / `declined_by_scope` / `partial`。
5. 递归扫描 `/input/**`，识别所有材料；`task.md`、`guide.md`、`instruction*.md` 记为指令，不作为稿件。
6. 真实解析材料：
   - PDF：优先用环境提供的 `pdf-text-tool`；不存在则 `pdftotext -layout` 或 Python `pdfplumber/pypdf`。扫描件无文本层时不要造文字，记入 `pending_human` 与 `errors.pdf_ocr_required`。
   - DOCX：用 `python-docx` 或解压 `document.xml`；不得按文件名臆测。
   - CSV/TSV：用标准库 `csv` 读真实行。
   - Markdown/TXT：直接读。
   - 图片：可见信息可读则读，无法识别则记 `pending_human`，不编造图题或数据。
7. 稿件判定：所有可解析文本中最长者为主稿件；有歧义写 `pending_human`。
8. 缺章节、缺参考文献、缺图表、缺附录、稿件截断、格式混乱等情况，明确写缺口和异常，不构造缺失内容。

## 5. 六维诊断与可执行动作

必须覆盖以下六类，且缺项尽量不把非主要问题强行当成主要问题。

### RQ：研究问题与贡献主张对齐
- 诊什么：研究问题是否提出、是否贯穿全文；贡献主张是否与实际完成工作一致；问题与方法是否各说各话。
- 动作：在哪一段收窄/补写问题；在哪个章节回扣贡献；哪句贡献表述需改为实际结果等价表述。

### STR：章节结构与叙事顺序
- 诊什么：章节顺序、篇幅、信息释放顺序；哪些铺垫应前置、哪些细节应后移、哪些章节应合并。
- 动作：明确“X 段/小节移到 Y 前/后”“从 Z 拆出”“将 A 与 B 合并为 C”，并给原因与原文 locator。

### ARG：论证链与论据对应
- 诊什么：逐条抽取论断与支撑论据；找出断裂、跳跃、循环论证、论据强度不足。
- 动作：为每个核心论断给支持证据映射；缺失论据标注“需补什么证据或在讨论中改称假设/初步结果”。

### PAR：段落关系与过渡
- 诊什么：段落间缺少过渡、逻辑跳跃、前后矛盾、指向不清。
- 动作：明确“在 x 段末与 y 段首补一句过渡”“将 y 段拆掉以承接 z 段”等。

### REP：重复内容
- 诊什么：同义重复、跨章节重复表述、冗余背景、数据/论断重复出现但结论不一致。
- 动作：指出哪两处重复、谁是主位置、从何处删、是否保留交叉引用。

### CON：结论边界与表述尺度
- 诊什么：结论是否超出数据与实验条件、是否遗漏限制说明、是否把相关性写成因果。
- 动作：指出哪句结论需加限制条件、哪个因果词需改为相关性表述、哪段需增加 limitations 说明。

每条 finding 必须含：`id`、`dimension`、`severity`、`locator`、`quote`、`problem`、`action`、`source_refs`。不允许只给一般写作原则。

## 6. 默认产出物与契约字段

若 `case.json.output_contract` 规定了文件字段和命名，以它为准；否则默认在 `/app/output` 生成：

- `structural_diagnosis.md`：作者可直接阅读和执行的结构诊断定稿。
- `editing_plan.json`：机器可读动作清单。
- `claims.json`：论点抽取与论据映射。
- `evidence_table.json`：逐条事实/数字/引用/论断的来源映射。
- `repetition_map.json` / `repetition_map.md`：跨章节重复内容映射。
- `gap_log.md` / `gap_log.json`：材料缺口、冲突点、异常。
- `pending_human.json`：需人工复核或确认项。
- `agent_review.json`：Agent 对脚本产出/原文的核验记录。
- `workorder_receipts.json`：任务要求逐项回报。
- `result.json`：最终契约回显。

以上文件必须与 `result.json` 中字段一一对应。若两个 Markdown 同时存在，`structural_diagnosis.md` 为干净成稿，`evidence_driven_draft.md` 为带证据标记草稿，二者不得复制粘贴同一文本。

## 7. result.json 双回显与元数据

`result.json` 必须合法 JSON，并同时满足：

1. 顶层出现所有 `output_contract` 字段，键名原样。
2. `output_contract` 嵌套对象中再出现一次，内容一致。
3. 顶层额外包含：

       case_id
       status: complete | partial | failed
       sources: [{source_id, file, type}]
       uncertainty: [{item, impact}]
       pending_human: [{item, reason}]
       errors: []
       degradations: []
       generated_at
       contract_version

`status=partial` 时必须说明哪些字段完成、哪些受限；不能无说明给 complete。

## 8. 自检清单与收尾

结束前执行：

1. 核对 `output_contract` 字段 × 磁盘文件 × `result.json` 键三者一致。
2. 逐条核对每项 finding/claim/action 至少有 `[S#]` 来源和 locator；无来源不得留在最终诊断。
3. 若有 `scripts/verify.py`，运行：

       python3 -B scripts/verify.py --out /app/output --input /input

   `pass=true` 方可收尾；`pass=false` 记录原因并修正，仍失败则在 `result.json.errors` 中如实写。
4. 检查 JSON 合法性、Markdown 可读性、所有路径为 `/app/output` 下真实文件。
5. 检查是否有虚构数据、缺失材料未标 pending、脚本 AUTO_EXTRACT 未标 degradation。
6. 只允许脚本改结构化 JSON 的结构；Agent 要写判断应写 `${WORK}/draft.json`。若脚本不可用而人工落盘最终 JSON，必须在 `result.json.degradations` 记录 `manual_build`。
7. 不写 `golden_standard`、`diff_report`、自设 benchmark；只引用真实运行输出。

## 9. 异常处理与稳定性

- 任何异常捕获后仍 exit 0，并在 `result.json.status/errors/degradations` 中如实记录。
- 输入为空：写 partial result，列出 `errors.no_input`。
- 材料无法识别或 PDF 无文本：不要编造，记入 `pending_human` 与 `errors.*`。
- 脚本不存在/不能运行：使用包内其他可运行脚本或 Agent 手动按键；但必须在 `result.json.degradations` 标注 `manual_fallback`。
- 输出过大/预算接近：先保存已完成部分，立刻 finalize，确保 `result.json` 合法且状态诚实。不要因追求完整而空手结束。
- 不依赖网络、不依赖 CWD、不依赖未说明的个人文件；只用 Python 标准库和包内资源。

## 10. 预算意识

- 首选单命令生成完整基线，再让 Agent 做真读、补充 draft 和核验，避免无约束多次对话。
- 理想请求安排：1 次 command 基线；1–4 次读材料与核验；1–2 次修正；最后 1 次 selfcheck/verify。
- 若预算少于 8 次模型请求或时间不足 120 秒，立即走确定性兜底路径，确保 `/app/output/result.json` 完整、合法、诚实，并有可复核的来源映射。

## 11. 资源使用说明

- `references/example.md`：仅作为交付物格式与结构示意，不得复制其案例内容。
- `references/taxonomy.md`：用于六类结构问题归类与动作动词选择，不替代对原稿的判断。
- `references/messages.json`：仅用于语言/表述模板，不替代 case 专属内容。
- `scripts/main.py`：基线、台账、抽取、生成、自检入口。
- `scripts/verify.py`：最终独立核验。

以上文件路径均为相对本 Skill 根目录；运行时 Agent 优先从实际安装路径 `/skills/weekly-skill` 调用。