---
name: literature-review-evidence-synthesis
description: 将一个真实文献集（PDF/CSV/DOCX/JSON/题录/协议笔记等）转成可复核的文献综述，覆盖筛选协议先于写作、去重与摘要处理、从材料中归纳主题、逐字证据回链、冲突并列与研究空白证据化。适合文献综述生成、系统筛选、证据综合、主题分析、研究空白分析等需要可回链成稿的任务。单命令可产生完整基线，Agent 可增量核验与改写，最终交付同一套契约产物。
version: 3.0.0
license: MIT
---

# 文献综述生成：筛选 → 主题归纳 → 证据组织 → 可回链草稿

## 0. 评分导向：评委真正看重什么

本 Skill 的目标不是“生成更多字”或“引更多文献”，而是让 Agent 在给定真实文献集上完整、正确地跑完四步：

1. 筛选标准是否先于写作写明，并被一致执行；
2. 每条实质论断是否指回具体文献的具体位置；
3. 主题与研究空白是否从这批文献里长出来，而不是套“背景—方法—挑战—展望”；
4. 冲突、证据边界、无法确定项是否被诚实保留。

因此，执行时优先保证：四步齐全、evidence 可核验、结果文件契约完整、不确定项显式登记、无依据不补造。任何时候都要先落盘一份合法 partial 结果，再增量改进。

## 1. 单命令入口与内部阶段

优先使用以下命令一次性完成基线、构建与自检：

    python3 scripts/main.py run --input /input --output /app/output --work /app/work

该命令内部包含三个阶段：

- init：盘点 /input 全部材料，登记来源编号、文件类型、可用字段、定位体系、sha1，抽取候选证据，生成冲突/重复分组与协议候选。
- build：校验/合并 Agent 判断，若存在 /app/work/draft.json 则使用；若不存在，则用 init 台账做确定性兜底抽取，渲染全部产物，并 finalize result.json。
- selfcheck：检查产物文件、result.json 契约字段、quote/locator 回链、计数一致性和引用一致性，输出自检报告。

异常情况下也必须 exit 0。错误写入 result.json 的 `errors` 或 `degradations`，不得让进程崩溃或缺失 result.json。

## 2. Agent-first 双路径

### 2.1 Agent 路径

Agent 应先跑 init 阶段，读取台账与原文，做出真实判断，再让 build 渲染：

    python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase init

1. 读取 /app/work/init/ledger.json、/app/work/init/sources.json、/app/work/init/candidates.json 或同类台账。
2. 真实读取 /input/case.json、/input/task.md 与 /input 下材料文件，不依据文件名或领域标签猜测内容。
3. 将筛选决定、主题归纳、证据行、草稿结构与不确定项写入 /app/work/draft.json。
4. 再执行 build 与 selfcheck：

       python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase build
       python3 scripts/main.py run --input /input --output /app/output --work /app/work --phase selfcheck

也可以执行完整 run，脚本会检测 draft.json 并自动使用。

draft.json 至少包含以下字段：

- case_id
- research_question
- screening_protocol：written_before_screening 必须为 true
- screening_decisions：逐源 include/exclude + reason_code + source_id + note
- themes：3–7 个主题，每个主题含 label、basis、sources、boundary
- evidence_rows：source_id、locator、quote、claim、topic、strength、claim_type
- draft_outline：综述章节结构
- gaps：缺全文、缺元数据、定位不全、证据不足、冲突未解决
- changes：记录相对 init 台账或先前判断的变更

### 2.2 无 draft 时的确定性兜底

如果 /app/work/draft.json 不存在，build 必须自动执行：

- 用 init 台账中的原文候选做确定性抽取；
- 生成逐字 quote 与 locator；
- 生成实质工作稿，而不是空壳；
- 在 result.json 的 `degradations` 或 `gaps` 中记录 AUTO_EXTRACT；
- 对每个 AUTO_EXTRACT 项标记是否需要人工复核。

两条路径必须产出同一套 /app/output 产物和同一份 result.json 契约，差异只体现在 status、degradations、pending_human 和 changes 中，不改变字段结构。

## 3. 输入与输出契约

### 3.1 输入

- /input/case.json：任务标识、case_id、研究问题或约束、输出契约。
- /input/task.md：题目说明、评分与交付要求。
- /input/ 下任意材料：PDF、DOCX、CSV、XLSX、JSON、MD、TXT、图片等。
- 输入材料是事实依据。缺全文、缺元数据、缺字段要登记为缺口，不补造。

### 3.2 输出

最终结果必须写入 /app/output，至少包括：

- result.json：结构化结果与状态，必须包含 case_id 与 output_contract 全部字段。
- screening_log.csv：逐源筛选决定、理由码、重复处理与依据。
- evidence_map.csv 或 evidence_table.json：证据矩阵。
- review.md：可回链综述成稿。
- 其他 output_contract 要求的文件：按字段名生成对应文件；若字段是 office/slide/diagram 等可编辑格式，必须另配真实渲染的 PDF/PNG 预览。

### 3.3 result.json 双回显

每个契约字段必须在以下位置各出现一次：

- result.json 顶层；
- result.json 的 nested `output_contract` 对象。

result.json 必须包含：

- case_id：原样保留输入 case_id。
- status：`ok`、`partial` 或 `error`；部分结果必须说明限制。
- output_contract：与输入契约一致的字段值和产物路径。
- sources：来源清单与来源编号。
- uncertainty：冲突、偏倚、空白、无法确定项。
- pending_human：需要人工复核或补全项。
- errors：运行或材料错误。
- degradations：降级处理、AUTO_EXTRACT、缺全文、无文本层等。
- changes：任务执行中的关键变更记录。
- runtime：开始/结束时间、阶段耗时、模型请求计数等。

## 4. 核心工作流

### 步骤 1：盘点输入和契约

1. 真实读取 /input/case.json 与 /input/task.md。
2. 提取研究问题、任务边界、输入材料清单、输出契约字段。
3. 扫描 /input 全部文件，按扩展名和文件头识别类型，登记 source_id、路径、类型、定位体系、sha1。
4. 缺失材料或字段写入 gaps/pending_human。

### 步骤 2：真实解析材料

1. PDF 优先使用环境提供的 pdftotext 或 pdf-text-tool；失败时按 pypdf、纯 Python PDF 流解析降级。
2. DOCX/CSV/XLSX/JSON/MD/TXT 使用标准库或可用的轻量脚本解析。
3. 无文本层 PDF 标记 fulltext=false 或 abstract_only，locator 使用段落块编号。
4. 图片只登记存在，不做像素推断。
5. 不依据文件名、标签或领域先验补造内容。

### 步骤 3：先写筛选协议

筛选协议必须先于最终 screening_log.csv 确定，并写入 draft.json：

- research_question
- inclusion_criteria：明确纳入什么研究问题、对象、方法、证据类型。
- exclusion_criteria：明确排除什么。
- dedup_rule：DOI 优先；无 DOI 用归一化标题 + 首作者 + 年份。
- strength_rule：摘录如何映射到 directly_supported / inferred / insufficient。
- written_before_screening：必须为 true。

理由码统一使用：

- I1–I9：命中纳入标准，可细分对象、方法、结果、数据等。
- E1 主题不符
- E2 人群/对象不符
- E3 方法不符
- E4 无全文且摘要不足
- E5 重复
- E6 非研究性文本
- E7 年份/语言超范围
- E8 数据不可用
- E9 其他，必须写具体原因

### 步骤 4：逐源筛选与去重

1. 逐条文献给出 include/exclude，写入 screening_log.csv。
2. 重复文献合并，保留信息最全者，并在原记录行注明被合并到哪个 source_id。
3. 不足判断时依据标题、摘要或首页摘录，并标 metadata_estimated=true。
4. 无法判断的文献排除并给 E4。

### 步骤 5：主题归纳

1. 从 init 的候选主题簇出发，按“方法路线、对象、结论方向、材料/尺度/场景”确定 3–7 个主题。
2. 每个主题必须有：
   - label：简短主题名
   - basis：从哪些共现信号或证据中归纳出来
   - sources：支撑主题的 source_id 列表
   - boundary：明确该主题不包含什么，避免重叠或遗漏
   - derived_from：corpus_cluster 或 agent_revision
3. 覆盖全部 include 文献；无法归类的源要写明原因。
4. 单源主题保留但标 thin=true，并进入 gaps。

### 步骤 6：建立证据矩阵

evidence_map.csv 或 evidence_table.json 一行一条证据，至少包含：

- source_id
- locator：文件 + 页码/段落号，例如 PDF1:p12.para3
- quote：逐字摘录。唯一允许的修改是省略号 `…`；不得改写、拼接、翻译、纠错。
- claim：该证据支持的实质论断。
- topic：所属主题。
- strength：只能取 directly_supported、inferred、insufficient。
- claim_type：fact、interpretation、uncertainty 等。
- verification：verified、rejected 或 pending_human。

强度措辞必须与原文一致：

- directly_supported：已报告、在该样本中观察到、结果显示。
- inferred：提示、可推断、与……一致。
- insufficient：尚不能判断、仅有摘要层面证据、证据不足。

不得把 may/suggests/associated with 写成 proves/causes。

### 步骤 7：写可回链综述草稿

review.md 必须包含：

1. 研究问题与证据范围；
2. 筛选与覆盖说明；
3. 分主题综合；
4. 冲突与反面证据并列；
5. 研究空白与证据缺口；
6. 局限；
7. 参考文献。

写法规则：

- 每个实质论断后挂来源标记 `[Sxx]`；
- 必要时加证据行 `{Exx}`；
- 一段只承载一个主题或一个论证节点；
- 不平滑反面证据；
- 研究空白必须落到具体证据缺口，不用套话收尾；
- 语言与输入一致：输入为中文则输出中文，输入为英文则输出英文。

### 步骤 8：回填 result.json 并自检

1. 运行 build 回填 result.json。
2. 运行 selfcheck 或 `python3 scripts/verify.py --input /input --output /app/output --work /app/work`。
3. 根据报告修正 rejected 证据行或把无法验证项写入 pending_human。
4. 确保 result.json 顶层与 output_contract 双重存在契约字段。
5. 确保输出文件齐全；缺失项写入 pending_human。

## 5. 确定性兜底与诚实降级

当 Agent 没有写 draft.json 时，build 必须生成实质性兜底：

- 不得输出空 review.md 或空 evidence_map.csv；
- 每条 AUTO_EXTRACT 行必须有 quote 与 locator；
- result.json 中必须记录 `AUTO_EXTRACT` 或 `deterministic_fallback`；
- 兜底来源只能来自 init 台账中的原文候选；
- 若候选不足，明确输出 partial 与 pending_human。

## 6. 异常与隐藏案例鲁棒性

| 情况 | 处置 | 记录 |
|---|---|---|
| case.json 缺失或坏 JSON | 递归查找 case*.json；仍失败则从 task.md 提取信息继续 | errors + input_error |
| 材料目录为空 | 产出合法 partial，result.status=partial | pending_human + no_material |
| 缺 PDF 全文 | 使用摘要或题录，标 fulltext=false | gaps: no_fulltext |
| PDF 无文本层 | pdftotext → pypdf → 纯 PDF 流解析；仍失败标 abstract_only | degradations: no_text_layer |
| DOCX/CSV 坏文件 | 跳过并说明 | errors + file_error |
| 题录重复 | DOI 优先合并；保留信息最全源 | changes + dedup |
| 元数据不完整 | 依据题录/摘要推断并标 metadata_estimated=true | pending_human |
| 结论冲突 | 证据矩阵并列呈现，不平滑 | uncertainty: conflicting_evidence |
| 证据不足 | quote 写成 insufficient 或 pending_human，不编造 | uncertainty: insufficient |
| 上下文超出预算 | 分批读取 corpus.json 块，先写大纲再逐节补 | runtime.notes |
| 输出契约字段缺失 | 生成该字段文件并写入 null/partial，不静默跳过 | pending_human + missing_output_field |
| 时间/请求接近上限 | 立即运行 build + selfcheck，保留 legal partial | runtime.budget_finalized |

## 7. 预算策略

官方预算：64 次模型请求，900 秒，单回复 16384 tokens（含推理）。

推荐分配：

- 触发 run init + 读契约：0–5 次；
- 材料抽查与关键段阅读：5–15 次；
- 协议与筛选：15–25 次；
- 主题与证据矩阵：25–40 次；
- 综述草稿：40–50 次；
- build + selfcheck + 修正：50–60 次；
- 缓冲与收尾：60–64 次。

接近约 780 秒时，必须执行 finalize，保证 result.json 合法、产物齐全、status 诚实。不要为润色重复跑脚本覆盖高质量 Agent 结果。

## 8. 资源与生态要求

包内应包含且仅引用以下资源：

- SKILL.md
- scripts/main.py
- scripts/verify.py 或 main.py 内嵌 selfcheck
- references/evidence_schema.md：字段定义、locator/strength 规范、理由码、写法规则
- references/guide.md：draft.json 形状、双路径说明、最小调用示例与限制
- references/templates.json：契约别名、多语言章节标签、冲突/反义标记、筛选词表
- environment/resources.yaml：预装依赖声明
- SELFTEST.md：自检清单、预期输出与失败处置

资源约束：

- 纯 Python 标准库，离线运行，python3 >= 3.8；
- 不依赖 CWD；脚本使用 Path(__file__).resolve().parent；
- 最多 50 个 UTF-8 文本文件，单文件 ≤ 500KB，总 ≤ 2MB；
- 不联网，不下载外部资源，不读取未声明个人文件；
- 运行时产物可为二进制并保留，但最终 JSON 有效性独立保证。

## 9. 最小调用示例

输入 /app/input/case.json 示例：

    {
      "case_id": "c001",
      "research_question": "干预 X 在人群 Y 中对结局 Z 的证据强度如何？",
      "output_contract": {
        "review": "review.md",
        "screening_log": "screening_log.csv",
        "evidence_map": "evidence_map.csv"
      }
    }

调用：

    python3 scripts/main.py run --input /input --output /app/output --work /app/work

示意输出标明为示例：

- /app/output/review.md：示例综述，不冒充正式案例结果。
- /app/output/screening_log.csv：示例筛选表。
- /app/output/evidence_map.csv：示例证据表。
- /app/output/result.json：示例结构，含 case_id、status、output_contract、sources、uncertainty、pending_human。

## 10. 最终自检清单

结束前按以下清单检查：

1. `/app/output/result.json` 存在且可解析；
2. result.json 顶层与 output_contract 中都包含 case_id 和全部契约字段；
3. 每个 output_contract 字段都有对应文件或明确 partial 说明；
4. 每条实质论断有 source_id + locator；
5. evidence_map 中 quote 为逐字摘录，strength 与原文措辞一致；
6. screening_log 每条文献都有决定与理由码；
7. 筛选协议 written_before_screening = true；
8. 主题有 label、basis、sources、boundary；
9. 冲突和空白有具体证据指向；
10. 异常、降级、缺料写入 errors/degradations/gaps/pending_human；
11. 没有发明评分、白板、golden_standard 或预生成正式答案；
12. 最终 exit 0。