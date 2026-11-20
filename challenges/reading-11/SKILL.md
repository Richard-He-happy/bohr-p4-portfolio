---
name: sci-reading-bench
description: 把输入科研材料现场做成"可判分"的文献阅读题集与评测工具包：Agent 亲自读原文、出题、写评分锚点与答案，脚本负责材料索引、逐字证据核验、0/1/2 评分、报告与 result.json 契约回填。适用于文献阅读 benchmark 建设、题集质量自检、评分可复核性核查，以及材料解析/问答类任务的证据回溯。
version: 2.0.0
---

# 文献阅读 Benchmark 与评测工具（Agent 主导 + 脚本辅助）

## 0. 一句话用途与铁律

本 Skill 用于把 `/input` 下的科研材料现场做成可判分、可复核、可复跑的文献阅读题集与评测流程，并把关键结论逐字锚定回原文。脚本负责材料索引、结构校验、逐字核验、评分表与 result.json 回填；**Agent 是最终交付物的唯一责任人**：必须亲自阅读材料原文、亲自推导题目/答案/评分点、亲自撰写或制作成品。禁止把脚本骨架、模板或未经核验的草稿直接当成品提交。任何一份交付物都必须能追溯到 `/input` 材料的真实片段或明确标注“材料未报告/无法判断”。

铁律：
- **先跑基线，再增强**：进入任务后先运行 `python3 -B scripts/main.py init`，落盘合法 partial `result.json` 与索引；后续所有 Agent 撰写与校验只在此基线上增量增强，不得删除、清空或遗漏基线产物。
- **保留全部基线产物**：无论后续是否改写，`/app/output` 下必须始终保留契约要求的全部文件；不确定时保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。
- **完整交付**：`result.json` 包含 `output_contract` 的全部字段（键名不改）与 `case_id`；所有可编辑 Office/幻灯片/图形产物必须额外有真实渲染的 PDF/PNG 预览；没有此类产物则如实说明。
- **真实推导**：所有引文、数字、locator、评分点必须来自 `/input` 材料；不得依据文件名、领域标签或外部知识补造内容；不确定项显式标为 `pending_human` 或 `limitations`。
- **退出码恒为 0**：任何异常都写进 `result.json` 的 `errors`/`degradations`，不靠非零码报错。

## 1. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（可缺）与 `/input/**` 材料；也接受 `case*.json` |
| 工作目录 | `/app/work`（索引、草稿、check 中间产物） |
| 产物目录 | `/app/output/`：`benchmark.json`、`anchors.json`、`scoring.json`、`report.md`、`result.json`，以及题面要求的其他可编辑/预览产物 |
| 入口 | `python3 -B scripts/main.py {init|show|check|build}`；`scripts/bench.py` 为库，也可 `--help` |
| 退出码 | **恒为 0**（异常写进 result.json 的 `errors`，不靠非零码报错） |
| 依赖 | Python 3 标准库；不联网；不依赖当前工作目录（路径用 `Path(__file__)` 推导） |
| 预算 | 64 次模型请求 / 900 秒；每步都可中断，`init` 已先落盘合法 partial `result.json` |
| 契约 | 必须真实解析材料内容；不得依据文件名或领域标签猜测；可编辑 Office/幻灯片/图形产物必须附真实渲染 PDF/PNG 预览 |

## 2. 输入发现与材料解析

`init` 会递归扫描 `/input`（跳过隐藏文件、`__pycache__`、根目录的 `case.json`/`task.md`/`result.json`），按扩展名+魔数判定类型（`%PDF`、`PK`），抽取文本，按空行切段，给每段一个稳定 locator `M01#p7`（M=材料序号，#p=段序号），PDF 额外记页码。

文本处理：JSON 用 `utf-8-sig` 解码（防 BOM），每个材料按 `utf-8-sig → utf-8 → gb18030 → latin-1` 依次尝试，全部失败才 `ignore` 并记降级。

`case.json` 采用语义识别，兼容别名：`case_id/caseId/id`、`output_contract/contract/required_outputs`、`task_instruction/instruction/prompt/task`、`organizer_workorder` 等；**契约字段原样透传**，不改名、不丢字段。

材料解析路径：`.md/.txt/.csv/.tsv/.json/.html/.tex/...` 直读 → `.docx` 走 `word/document.xml` → `.pdf` 依次尝试 `pdftotext`、`PyMuPDF`、`pdfminer`、内置 zlib 流抽取（探测失败才降级）。图片只登记缺口，题面要求图片解析时必须使用平台提供的图像工具并保留来源。

## 3. 核心执行流程（必须按序，Agent 主导）

### 步骤 0：盘点输入与输出契约
- 输入：`/input/case.json`（如有）、`/input/task.md`、`/input/**` 材料文件。
- 动作：运行 `python3 -B scripts/main.py init`，阅读打印出的材料清单、契约字段名、材料状态标记（`!` 表示降级）。同时打开 `/input/task.md` 和 `case.json`，识别任务类型（题集构建 / 材料解析 / 翻译 / 问答 / 提取 / 核验 / 知识结构化）与 `output_contract` 每个字段。
- 输出：`/app/work` 索引与 partial `/app/output/result.json`。
- 失败分支：`case.json` 缺失或坏 JSON → 继续用目录扫描与 task.md 推断；无任何材料 → 仍生成空题集产物，`status=input_error`，退出码 0。

### 步骤 1：真实解析材料
- 输入：`/app/work` 索引与材料文件。
- 动作：运行 `python3 -B scripts/main.py show --material Mxx --start 1 --limit 20` 逐段调取原文。**Agent 亲自阅读**，不得只凭摘要或文件名判断；对每个材料至少读完所有段落（分页读取）。记录可能出题/回答的段落 locator 与原文用词。
- 输出：材料内容印象与可复用的段落清单。
- 失败分支：材料无文本 / 图片不可读 → 登记 `degradations`，其余材料照常；PDF 需要 OCR 时记录 `low_text_quality`，并用平台工具复核。

### 步骤 2：构建题集或回答材料问题
- 输入：案例任务要求 + 已读原文。
- 动作：
  - 若任务为**题集构建**：Agent 亲手写 `work/questions.draft.json`，字段见 `references/schema.md`。每题含 `id`、`type`、`difficulty`、`question`、`rubric[]`（每点 `id`/`text`/`weight`/`key_terms`）、`reference_answer[]`、`evidence[]`（`material`+`locator`+`quote`）。题目覆盖可核对数值/摘录、方法与条件、机制与主张、材料内冲突或未报告项。说明：`rubric` 的 `key_terms` 取原文用词（1–5 个短字符串），脚本用覆盖度评分；`quote` 逐字复制自 `show` 输出，locator 写 `Mxx#py`。
  - 若任务为**材料解析/问答/翻译/提取等**：Agent 亲自撰写主结果（答案/结构化字段/翻译/知识结构），并将关键结论用 `evidence` 数组回挂到原文 locator 与逐字引文。不强制生成 benchmark 产物，但必须在 `result.json` 中放置主结果与证据；若契约要求可编辑/预览产物，按题面要求生成。
- 输出：草稿文件（题集草稿或主结果草稿）。
- 失败分支：若无法从材料中找到任何支持内容，写出“材料未报告/无法判断”，不补造数字；必要时生成最小兜底题集（见第 5 节）。

### 步骤 3：核验证据与结构
- 输入：草稿文件 + `/app/work` 索引。
- 动作：运行 `python3 -B scripts/main.py check`。脚本逐条校验：`question`≥10 字符、`rubric`≥1、`reference_answer`≥1、`evidence`≥1；quote 空白归一后子串匹配（大小写敏感优先）；locator 与 quote 实际段落一致；权重总和≈1.0（±0.02）。Agent 根据报错修改草稿，重复 `check` 直到 `RESULT: PASS` 或明确接受剩余错误（记录到 `changes`）。
- 输出：校验报告与修订后的草稿。
- 失败分支：全部题不可核验 → 触发确定性兜底（第 5 节）；部分不可核验 → 被拒题进 `rejected`，其余继续；不要为通过而改写原文。

### 步骤 4：生成成品与回填 result.json
- 输入：通过校验的草稿。
- 动作：运行 `python3 -B scripts/main.py build`。生成 `/app/output` 下全套产物：`benchmark.json`、`anchors.json`、`scoring.json`、`report.md`、`result.json`。随后 Agent 亲自审阅产物：核对 `result.json` 是否包含 `output_contract` 全部字段、`case_id`、状态、来源、不确定性、变更记录；确认所有可编辑/预览产物已存在且真实渲染。
- 输出：最终交付物。
- 失败分支：build 异常 → 打印栈，回退保留 partial result.json 与已有产物，记录 `errors[].traceback`，退出码 0。

### 步骤 5：自检 rubric 与完整性
- 输入：最终产物。
- 动作：按第 6 节对照表逐项自证，按第 7 节清单检查文件、字段、磁盘产物三者对应；缺失项先补齐再收尾。将自检结论写入 `result.json.changes`（如 “agent_review_passed” 或列出剩余问题）。
- 输出：可提交的完整 Skill 运行结果。
- 失败分支：自检发现缺项 → 补齐后重新 build；若时间不足，保留 partial 并在 `pending_human` 明确缺失项。

## 4. 预算策略与断点

64 次模型请求 / 900 秒内，优先级从高到低：

1. **必须做**（约 15-20 次请求）：
   - `init` 1 次：拿到索引、partial result.json。
   - `show` 分页 4-8 次：读完全部关键材料段落（材料大则只读每段首尾句，但不允许不读就出题）。
   - 写草稿 2-4 次：Agent 一次性写出题集或主结果，避免反复修改。
   - `check` 2-3 次：修复硬错误。
   - `build` 1 次：生成全套产物。
   - 自检与回填 1-2 次：看 result.json 与产物，补缺口。

2. **可跳过**：非核心材料的全量精读、额外题型扩展、非必要的评分细化。若剩下不足 60 秒，直接 `build`，不要因增加一两道题丢掉整包。

3. **尽早落盘 partial**：`init` 后立即有合法 `result.json`；每一步后都可调用 `build` 或 `main.py` 的幂等命令刷新 partial。接近 780 秒时无条件 `build` 并写结果。

4. **禁用冗余**：不重复扫描同一目录，不重复生成相同文件，不进行无意义的全文重读；单一 show 调用可一次读取 20 段以上。

## 5. 隐藏案例鲁棒性（异常降级与兜底）

任何情况下都要产出合法 `result.json` 且退出码 0。处理规则：

| 情况 | 行为 | 结果字段 |
|---|---|---|
| `case.json` 缺失或坏 JSON | 继续扫描材料，按 task.md 推断任务与契约 | `errors` + `status=partial` |
| 无材料 | 产物仍生成（空题集或空主结果） | `status=input_error` |
| 材料无文本 / 图片 / 加密 PDF | 该材料标 `no_text`，其余照常；图片只有登记缺口 | `degradations` |
| PDF 需 OCR / 字体异常 | 记 `low_text_quality`，提醒平台工具复核 quote | `degradations` + `uncertainty` |
| 草稿缺失或全部不可核验 | **确定性兜底**：从真实段落生成最小摘录/数值题（1 题/段，最多 6 题），产物不空 | `mode=fallback_minimal` + `status=partial` |
| 部分题被拒 | 其余题正常出包，补 2 道兜底题 | `mode=agent_authored_with_fallback` |
| 输入含 checker/合成数据 | 只登记，不参与评分 | `technical_synthetic.present=true, not_a_dsh_score=true` |
| 超时（>870 秒） | 停止新增，保留已有 partial，刷新 result.json 的 `runtime` 与 `errors` | `errors[].timeout` |
| 任何未捕获异常 | 打印栈，写 partial result.json，退出码 0 | `errors[].traceback` |

兜底题必须同样真实：quote 来自原文、locator 正确、rubric 与答案不夸大；不因兜底而降低证据标准。

## 6. rubric 维度 → 交付要求 → 自证方式对照表

### 实际效果（40 分）

| 交付要求 | 自证方式 |
|---|---|
| 建成可判分、可复跑的题集与评测流程，而非题单+截图 | `benchmark.json` 含完整题卡，`scoring.json` 含逐题判分与聚合；`report.md` 有运行配置与记录 |
| 参考答案、判分结果与汇总指标准确一致，自动得分与人工结论对得上 | `anchors.json` 每个 verified 锚点都能回原文；`scoring.json` 的 `basis` 与 `locator` 可重跑 `check` 得到相同结论 |
| 覆盖任务定义、数据与答案管理、评分维度、原始输出留存、误差分析、版本迭代六个方面 | `benchmark.json` 含任务字段、材料来源、参考答案、评分规则；`scoring.json` 含 raw 输出留存路径；`report.md` 含误差分析与版本记录 |
| 每个分数能顺着题目 ID 追到原始输出、运行配置与评分记录 | `scoring.json` 每题带 `item_id`、`run_id`、`output_path`、`basis`；`report.md` 提供追踪说明 |

### 使用增益（25 分）

| 交付要求 | 自证方式 |
|---|---|
| 在同一题集快照与同一 Agent 版本下，加载成果相比不加载提升评测质量 | 产物中记录 `mode` 为 `agent_authored` 或 `agent_authored_with_fallback`，并提供质量自检对比说明；`report.md` 给出前后对照口径 |
| 建题、跑评测、汇总与复核的人工修改量下降 | `result.json.changes` 记录 Agent 自动修复项与人工待办项数量；`report.md` 展示脚本自动化环节 |
| 通过公平对照证明质量或效率改善 | 不伪造基准，如实记录本 Skill 的自动校验项与人工复核项，说明提升边界 |

### 创新增益（15 分）

| 交付要求 | 自证方式 |
|---|---|
| 形成基础 Agent 不具备的评测基础设施能力 | `anchors.json` 的逐字核验逻辑、`scoring.json` 的 0/1/2 评分与可复核 basis、`report.md` 的版本对比框架 |
| 题集设计、评分档位、运行与失败归因方法带来实质改进 | `references/schema.md` 与 `references/reuse.md` 体现可复用方法；`report.md` 记录失败样例归因与改进建议 |
| 用同批题目证明新做法相对旧口径的边界与价值 | `changes` 中保留版本差异说明；`technical_synthetic` 不计入分数；明确口径变化与可比性 |

### 可靠体验（10 分）

| 交付要求 | 自证方式 |
|---|---|
| 用户能按说明跑完一轮评测 | 本 SKILL 与 `references/reuse.md` 给出从 `/input` 到 `/app/output` 的完整命令与示例 |
| 同一题集在不同环境与重复运行下持续产出可用结果 | 脚本只依赖标准库，路径用 `Path(__file__)`；`build` 幂等；`result.json` 记录 `runtime` 与 `changes` |
| 对缺参考答案、输出为空或超长、格式不合规、文件损坏、权限不足等识别与处置 | 第 5 节表格覆盖；`errors` 与 `degradations` 如实记录；空输出不会被当作正常结果 |

### 生态贡献（10 分）

| 交付要求 | 自证方式 |
|---|---|
| 题卡规范、运行方法、依赖、示例、结果字段与维护信息齐全 | `references/schema.md` 提供字段规范；`references/reuse.md` 提供换案例与维护步骤 |
| 题集、评分表、运行器、结果模板能被他人直接复用 | 提交目录包含 `scripts/`、`references/` 与 SKILL 文档；任何人拷贝后即可跑通 |
| 沉淀可分享的建题经验、失败样例与真实应用价值 | `report.md` 含典型失败样例与归因；`references/reuse.md` 记录版本演进 |

## 7. 输出契约（result.json 字段与自检清单）

### result.json 固定字段

`case_id`、`status`（ok|partial|insufficient_evidence|input_error）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`outputs`、`benchmark`、`anchors`、`scoring`、`technical_synthetic`。

外加：`output_contract` 里的**每个字段都在顶层出现**（有对应结果就填真实值，没有就 `null`/`[]`/镜像空结构），并保留 `contract_fields_present` 与 `contract_echo` 便于审计。UTF-8 无 BOM。`outputs` 列出 `/app/output` 下所有实际文件及其用途；任何预览文件必须真实渲染，不以空文件占位。

### 提交前自检清单

- [ ] `python3 -B scripts/main.py --help` 与 `python3 -B scripts/bench.py --help` 均退出 0
- [ ] 已运行 `init`，且 `/app/output/result.json` 存在且合法 JSON
- [ ] `result.json` 的 `contract_fields_present` 里每个字段都在顶层出现，`case_id` 正确
- [ ] `/app/output` 下必有 `benchmark.json`、`anchors.json`、`scoring.json`、`report.md`、`result.json`
- [ ] `benchmark.json.items` 非空（或 `status` 明确说明为何为空）
- [ ] 每条 `anchors.json.anchors[].verified` 为 true，或该题在 `benchmark.json.rejected`
- [ ] `scoring.json.aggregate.n2+n1+n0 == n_points`
- [ ] `report.md` 有材料表、逐题表、评分汇总、缺口、失败样例或未报告项
- [ ] 若 output_contract 要求 Office/幻灯片/图形产物，存在且附真实 PDF/PNG 预览；无此类要求则忽略
- [ ] 无 `__pycache__`、无临时文件、无预制正式答案
- [ ] `status`、`sources`、`uncertainty`、`pending_human`、`changes` 内容真实，无编造
- [ ] 所有草稿（`work/questions.draft.json` 等）不留在 `/app/output`，只留最终产物
- [ ] 已按第 6 节对照表逐项自证并记录结果

## 8. 题集质量规则与评分口径（脚本辅助）

### 质量规则

| 规则 | 脚本动作 | 落点 |
|---|---|---|
| 每题任务/答案/rubric 齐备 | `question`≥10 字符、`rubric`≥1、`reference_answer`≥1、`evidence`≥1 | `check` 报错，缺项题进 `rejected` |
| 引用逐字可核验 | 空白归一后子串匹配（大小写敏感优先） | `anchors.json` 的 `verified`/`match` |
| locator 与引文一致 | 命中位置反推段号，与声明 locator 比对 | `locator_mismatch` 错误 |
| 权重可加 | Σweight≈1.0（±0.02） | `check` warning |
| 不可判的题不混进分数 | 无任何 verified quote → 拒收 | `benchmark.json.rejected` + `pending_human` |

### 证据与定位规范

- locator 唯一格式：`M<材料号>#p<段号>`，如 `M01#p12`；PDF 另带页码字段。
- quote 必须是原文的**连续片段**（允许空白差异），不得拼接、改词、翻译、加省略号。
- 长度 ≥12 字符；一句话最好完整，避免只抄三个词。
- 同一题可以有多条证据，评分取覆盖度最高的那条。
- 找不到引文就改题或降级到 `pending_human`，**绝不改原文凑通过**。

### 评分口径（0/1/2，可复核）

点级：**2** = 原文有逐字锚点且覆盖该点关键项（coverage≥0.6）；**1** = 锚点存在但覆盖不足，需人工复核；**0** = 无可用锚点。

题分 = Σ(weight × 点分)，满分 2；`aggregate` 给 `n1/n2/n0`、`rate2`、`judgeable_rate`、`mean_score`、`n_anchors_verified`。

**这不是被评测 Agent 的答题分，也不是 DSH 分数**：它衡量“这套题能否被判、判分依据是否落在原文上”。`scoring.json` 每题带 `basis` 与 `locator`，任何人重跑 `check` 应得到同一结论。

## 9. 冲突、未报告与人工接管

- 材料之间矛盾：写出两种说法各自 locator，题面要求“指出冲突”，不裁决对错。
- 材料未报告：`reference_answer` 写“材料未报告”，rubric 给“识别为未报告”的分，不补造数字。
- 每条 score<2、每个被拒题、每次解析降级都进 `pending_human`，写清缺什么、下一步做什么。

## 10. 最小调用示例（示例，非正式案例结果）

    python3 -B scripts/main.py init          # 索引 + partial result.json
    python3 -B scripts/main.py show --material M01 --start 1 --limit 8
    #   → [M01#p2] Salinity stress reduced the specific growth rate ... 39 percent ...
    #   （把该段原文粘进草稿的 evidence.quote，locator 写 M01#p2）
    python3 -B scripts/main.py check         # PASS / 逐条 ERROR
    python3 -B scripts/main.py build         # 五件产物 + SELF-AUDIT PASS

示意产物（节选，示例）：

    {"id": "Q01", "type": "numeric", "difficulty": "easy",
     "question": "盐度从 25 升到 45 psu 时比生长速率从多少降到多少？",
     "rubric": [{"id": "R1", "text": "给出两个数值", "weight": 0.6, "key_terms": ["1.42", "0.87"]},
                {"id": "R2", "text": "给出降幅百分比", "weight": 0.4, "key_terms": ["39 percent"]}],
     "reference_answer": ["1.42 d-1 → 0.87 d-1，降幅 39 percent"],
     "evidence": [{"material": "M01", "locator": "M01#p2", "quote": "…from 1.42 d-1 at 25 psu to 0.87 d-1 at 45 psu…"}]}

## 11. 文件清单与复用

    SKILL.md                 本文件：流程、规则、异常分支、自检
    scripts/main.py          CLI：init / show / check / build（≤20KB）
    scripts/bench.py         库：抽取、索引、核验、校验、result.json 壳（≤20KB）
    references/schema.md     草稿 JSON 字段规范 + 示例 + check 规则
    references/reuse.md      换新案例 / 扩展题型 / 版本与维护

**换新案例**：替换 `/input/case.json` 与材料 → `init` → `show` → 写草稿 → `check` → `build`。命令不变，产物结构不变，旧产物被覆盖（需要留档就先 `cp -r /app/output /app/output.v1`）。
**别人怎么复用**：整套 `submission/` 拷走即可跑；`benchmark.json` 当题集快照，`scoring.json` 做逐题对照，`anchors.json` 做引文抽查表，`report.md` 直接进汇报。改流程要同步改 `scripts/`，改评分口径要升版本并在 `references/reuse.md` 记一条。

版本：2.0.0（Agent 主导 + 完整性优先 + 契约严格 + 鲁棒兜底 + 自审计）。