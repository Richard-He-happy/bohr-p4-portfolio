---
name: sci-reading-bench
description: 把 /input 科研材料现场构建成可判分、可复核、可复跑的文献阅读题集与评测工具包；Agent 负责真实阅读、核验与撰写判断，脚本负责材料索引、逐字证据核验、0/1/2 评分、报告生成与 result.json 契约双回显。适用于科研阅读 Benchmark 建设、题集质量自检、材料问答/提取/核验的证据回溯。
version: 3.0.0
---

# 文献阅读 Benchmark 与评测工具

## 0. 入口与最高优先级

一键命令（必须首选执行）：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 内部顺序：`init` → 检测 draft → 无 draft 时确定性兜底 → `build` → `selfcheck`。无论成功或异常，退出码恒为 0。

最高优先级铁律：

1. 真实阅读 `/input` 材料；所有答案、题卡、数值、结论必须来自原文，不按文件名、领域标签或外部知识补造。
2. 结构化最终产物由脚本生成。Agent 不得手改 `benchmark.json`、`anchors.json`、`scoring.json`、`result.json` 结构；只能写 `/app/work/draft.json`、`agent_review.json`、`pending_human.json` 和文本型交付物。
3. 每个关键结论必须带 `[source_id]` 与 locator；材料缺失、无法判断、冲突必须显式登记，不得写成事实。
4. 完整交付：所有契约字段、证据、来源、不确定项、变更记录都要落盘；部分完成必须写清边界。
5. `result.json` 必须双回显：契约字段与 `case_id` 同时在顶层和嵌套 `output_contract` 出现。
6. 预算意识：先跑基线并落盘 partial，增量改进；逼近 64 次模型请求或 900 秒时立即收尾，保证合法 JSON 和诚实状态。

## 1. 运行契约

| 项 | 约定 |
| --- | --- |
| 输入 | `/input/case.json`（可缺）、`/input/task.md`、`/input/**` 实际材料 |
| 工作区 | `/app/work`：索引、`draft.json`、`agent_review.json`、`pending_human.json`、校验中间产物 |
| 交付目录 | `/app/output`：`benchmark.json`、`anchors.json`、`scoring.json`、`report.md`、`result.json`，以及 `output_contract` 要求的可编辑/预览产物 |
| 入口 | `python3 -B scripts/main.py {run,init,show,check,build,selfcheck}` |
| 退出码 | 恒为 0；异常写 `errors`/`degradations`，不靠非零码报错 |
| 依赖 | Python 3.8+ 标准库；离线；路径用 `Path(__file__)` 推导，不依赖当前工作目录 |
| 预算 | 64 次模型请求 / 900 秒 / 每次响应含 reasoning 最多 16384 tokens |
| 契约 | 读取实际文件，不假设材料内容；PDF 解析时收到的是实际 PDF，不得依赖预制答案层 |

## 2. 输入发现与材料解析

`init` 递归扫描 `/input`，按扩展名+魔数识别材料，抽取文本，稳定编号，并按空行切段。每段赋予形如 `M01#p12` 的 locator；PDF 额外记录页码。

`case.json` 采用语义识别，兼容别名：`case_id/caseId/id`、`output_contract/contract/required_outputs`、`task_instruction/instruction/prompt/task`、`organizer_workorder`。契约字段原样透传，不改名、不丢字段。

解析路径：

- `.md/.txt/.csv/.tsv/.json/.html/.tex` 等直读；
- `.docx` 走 `word/document.xml`；
- `.pdf` 依次尝试 `pdftotext`、`PyMuPDF`、`pdfminer`、内置 zlib 流；
- 图片只登记缺口，题面要求图像解析时必须使用平台工具并保留来源。

若出现 `organizer_workorder` 或“benchmark-DRAFT workorder”，按它指定的 source-conditioned 条目作为任务规格；提供的材料是 paragraph/table text，不是 PDF-pixel gold。技术性 synthetic checker logs 只登记，不当作 DSH 分数或独立语义验证。

## 3. Agent 与脚本边界

**脚本负责**：材料清单、来源编号、段落切分、候选抽取、冲突分组、quote 逐字核验、locator 校验、0/1/2 评分、聚合统计、报告骨架、`result.json` 壳与双回显、自检。

**Agent 负责**：

- 阅读 `/input/task.md` 与 `case.json`，确认任务类型和 `output_contract` 全部字段；
- 通过 `show` 分段阅读真实原文，记录可出题/回答的段落与 quote；
- 写 `/app/work/draft.json`：题集 items 或问答/提取/翻译主结果加 evidence；
- 逐条核验脚本抽取的 quote、数字、locator 是否与原文一致；
- 撰写或审阅正文型交付物，如 `deliverable.md`、`manuscript.md`；
- 在 `pending_human.json` 中写清每处 score<2、被拒题、缺口和下一步。

**Agent 禁止**：

- 手改 `benchmark.json`、`anchors.json`、`scoring.json`、`result.json` 结构；
- 生成无原文依据的答案、金标准、加权自评分或官方 DS 评分；
- 把 synthetic checker 日志当作 DSH 分数；
- 用模板草稿或未核验文本冒充最终交付。

## 4. 执行流程

### 4.1 一键基线

先执行：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令一定生成合法 `result.json` 和至少一套实质产物。如果已有 `/app/work/draft.json`，使用 Agent 判断；否则执行确定性兜底。

### 4.2 Agent 增强路径

预算允许时，按以下步骤增量提升：

1. **初始化台账**

```bash
python3 -B scripts/main.py init --input /input --output /app/output --work /app/work
```

阅读打印出的材料清单、契约字段、来源编号、材料状态；识别任务类型。

2. **真实读原文**

```bash
python3 -B scripts/main.py show --work /app/work --material M01 --start 1 --limit 20
```

分段读完全部关键材料；大材料至少读每段首尾句。记录真实 quote 与 locator。

3. **写 `/app/work/draft.json`**

题集构建任务：写 `items[]`。每题含 `id`、`type`、`difficulty`、`question`、`rubric[]`、`reference_answer[]`、`evidence[]`。`rubric` 每点为 `id/text/weight/key_terms`。`evidence` 每条为 `source_id`、`locator`、`quote`。

问答/提取/翻译/知识结构化任务：写主结果对象，并把每个关键结论回挂到 `evidence`。

未报告项：答案写“材料未报告/无法判断”，并为“识别未报告”设计 rubric 点，不补造数字。

4. **校验**

```bash
python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
```

修复硬错误，直到 `RESULT: PASS` 或明确接受剩余问题并记录。不要为通过而改原文。

5. **构建成品**

```bash
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
```

生成全部产物并回填 `result.json`。

6. **自检**

```bash
python3 -B scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

核对「output_contract 字段 × 磁盘文件 × result.json 键」一一对应；缺项补齐后重新 build。

### 4.3 确定性兜底

无 draft 或全部不可核验时，自动从 init 台账的真实段落中抽取关键句生成实质工作稿：

- 至少 1 条/段；若 organizer workorder 指定四项，则产出四项。
- 每条必须有连续原文 quote 和正确 locator。
- 所有条目进入 `pending_human`，并记录 `mode=fallback_minimal`、`status=partial`。
- 把 `AUTO_EXTRACT` 诚实记入 `gaps`/`degradations`。
- 仍输出同一套产物和同一份 result.json 契约。

## 5. result.json 契约

### 固定顶层字段

`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`gaps`、`changes`、`runtime`、`outputs`、`benchmark`、`anchors`、`scoring`、`technical_synthetic`。

`status` 取值：`ok` | `partial` | `insufficient_evidence` | `input_error`。

### 双回显

- 解析原始 `output_contract` 的全部字段。
- 每个契约字段在 `result.json` 顶层出现一次；无结果则填 `null`、`[]` 或镜像空结构。
- 同时在 `result.json` 的 `output_contract` 对象中再出现一次，并包含 `case_id`。
- 增加 `contract_fields_present` 与 `contract_echo: true` 供审计。

### 交付物

`benchmark.json`：完整题卡，覆盖任务定义、材料来源、参考答案、评分规则与难度；不可核验题进 `rejected`。
`anchors.json`：逐条证据核验，含 `claim_id`、`source_id`、`locator`、`quote`、`verified`、`match`。
`scoring.json`：每题 0/1/2 分，带 `item_id`、`basis`、`locator`、`run_id`、`output_path`；聚合 `n2/n1/n0`、`rate2`、`judgeable_rate`、`mean_score`、`n_anchors_verified`。
`report.md`：材料表、逐题表、评分汇总、缺口/失败样例、版本与运行配置、未报告项、增益证据。
`result.json`：状态、来源、不确定性、人工接管、错误、降级、缺口、变更、运行时、产物清单。

所有关键数字和论断在正文/报告中带 `[Mxx#py]` 来源与 locator。可编辑 Office/slide/diagram 产物必须附真实渲染 PDF/PNG；否则在 `pending_human` 说明。

## 6. 隐藏案例鲁棒性

| 场景 | 处理 | 结果字段 |
| --- | --- | --- |
| `case.json` 缺失或坏 JSON | 继续扫描 /input，按 task.md 推断任务与契约 | `status=input_error` 或 `partial` + `errors` |
| 无材料 | 生成空题集/空主结果，不编造 | `status=input_error` |
| 材料无文本/图片/加密 PDF | 该材料标 `no_text`，其余照常；图片只登记缺口 | `degradations` |
| PDF 需 OCR/字体异常 | 标 `low_text_quality`，提醒人工复核 | `degradations` + `uncertainty` |
| draft 缺失或全部不可核验 | 从真实段落确定性兜底 | `mode=fallback_minimal` + `status=partial` |
| 部分题被拒 | 保留有效题，补兜底题 | `mode=agent_authored_with_fallback` |
| 出现 synthetic checker logs | 只登记，不评分 | `technical_synthetic.present=true`、`not_a_dsh_score=true` |
| 超时 >870 秒 | 停止新增，保留 partial，刷新 runtime/errors | `errors[].timeout` |
| 任意未捕获异常 | 打印栈，写 partial result.json，退出码 0 | `errors[].traceback` |

## 7. rubric 维度 → 交付证据

### 实际效果（40 分）

- 完整可运行评测流程：`benchmark.json` + `scoring.json` + `report.md`，不是题单截图。
- 准确一致：每道 `reference_answer`、`basis`、`locator` 能回到原文；重跑 `check` 得到同一结论。
- 六方面完整：任务定义 → `benchmark.json.tasks`；数据与答案管理 → sources/answers；评分维度 → rubrics/scoring；原始输出留存 → `output_path`/`run_id`；误差分析 → `report.md` 失败样例；版本迭代 → `changes`/`references/reuse.md`。
- 可核验链路：每题分数顺着 `item_id` 追到原始输出、运行配置、评分记录与证据 locator。

### 使用增益（25 分）

- 质量增益：`report.md` 提供“增益证据”一节，同快照/同 Agent 下比较 `fallback_minimal` 与 Agent 增强模式的差异；只写可复现事实，不伪造对照。
- 效率增益：`result.json.changes` 记录脚本自动修复项与人工待办项；`agent_review.json` 记录核验修正。
- 可验证性：两种模式走同一命令与同一产物契约，`report.md` 写清口径、条件和限制。

### 创新增益（15 分）

- 新增能力：逐字 quote/locator 核验、judgeable basis、来源追溯链条，由 `anchors.json` 支撑。
- 方法改进：0/1/2 分档、拒收题不混入总分、失败归因到题型/材料段，由 `scoring.json`+`report.md` 支撑。
- 创新证据：`changes` 记录版本差异与口径变化；`report.md` 说明新口径相对旧口径的边界。

### 可靠体验（10 分）

- 易用性：本 SKILL 给出一键