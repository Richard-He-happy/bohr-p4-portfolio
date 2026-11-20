---
name: paper-reproduction-verify
description: 对论文候选实现进行真实运行、事前容差比较与差异归因，交付可复核的复现记录与 result.json。适用于参数/代码/指标验算，强调先跑基线再增强、真实读材料、诚实标注缺失与边界。
version: 1.1.0
---

# 论文复现与方法验证（Agent 主答 + 脚本辅助；完整性优先）

一句话用途：读取论文材料，真实运行一到多份候选实现，按事前声明的容差比较关键指标，给出可复核的差异归因与复现结论，并完整回填 `result.json`。

**最高优先级：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** `scripts/main.py` 的 `init` / `show` / `check` / `build` 只负责索引、候选运行、数值比较、契约校验和最小兜底；`scripts/verify.py` 只做证据匹配、容差比较、契约回填等确定性校验。禁止把脚本生成的骨架、模板、中间预览直接当成品；禁止删除、清空或遗漏基线产物。你必须在基线产物之上亲自核验关键论断、数字、引用与归因，并把核验结果写回 `result.json`。

---

## 1. 运行契约与文件边界

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`output_contract`、workorder、候选/材料说明）、`/input/task.md`、题面规定的材料（PDF/DOCX/CSV/图片/代码/JSON/MD 等） |
| 工作区 | `/app/work`：`index.json`、`tolerance_plan.json`、`draft.json`、`runs/`、中间产物 |
| 最终产物 | `/app/output/result.json`、`/app/output/reproduction.md`、`/app/output/reproduction.json` |
| 预览 | 若契约要求可编辑 Office/幻灯片/图形产物，必须额外给出真实渲染的 PDF/PNG 预览；无法生成要写明 `pending_human` 原因 |
| 脚本根 | 先定位 `/skills/weekly-skill`；不可用时在 `/` 下查找 `SKILL.md` |
| 依赖 | 仅 Python 3 标准库；脚本不依赖 CWD；可用 `SCIM_INPUT/SCIM_OUTPUT/SCIM_WORK` 覆盖路径 |
| 包内文件 | 只允许引用：`SKILL.md`、`references/draft_schema.md`、`references/repro_rules.md`、`scripts/main.py`、`scripts/verify.py` |

进入任务先定位包根并确认脚本可运行：

```bash
SK=/skills/weekly-skill; [ -f "$SK/SKILL.md" ] || SK="$(dirname "$(find / -maxdepth 4 -name SKILL.md 2>/dev/null | head -1)")"
python3 -B "$SK/scripts/main.py" --help
python3 -B "$SK/scripts/verify.py" --selftest
```

---

## 2. 本题专属执行流程（先跑基线，再 Agent 增强）

每一步都要看清“输入 / 动作 / 输出 / 失败分支”。**先运行基线，尽早落盘合法 partial，再增量改进。**

### 步骤 1：盘点输入并先落基线 partial

**输入**：`/input/case.json`、`/input/task.md`、`/input/**` 材料；`/app/work` 与 `/app/output` 可能为空。

**动作**：

1. 先定位 `SK`，运行：
   ```bash
   mkdir -p /app/work /app/output
   python3 -B "$SK/scripts/main.py" init
   ```
   `init` 会索引 `/input`、检测材料类型、生成 `/app/work/index.json`、`tolerance_plan.json`、draft 骨架，并在 `/app/work` 与 `/app/output` 先写合法 partial `result.json`。
2. 亲自读 `/input/case.json`，用 `utf-8-sig` 容忍 BOM/GB18030；损坏时继续。识别 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`、`organizer_workorder`、`candidates/implementations`、`reported_metrics`、`environment` 等语义字段，不假设键名。
3. 递归扫描 `/input/**`，跳过 `case.json`；按**扩展名 + 魔数**判定类型（`%PDF`、`PK` + `word/`、`xl/`、PNG/JPEG 等），不按文件名或领域标签猜内容。
4. 给每个材料分配稳定 `id`，记录正文单元 locator：`paper:p3`、`md:§标题/p2`、`csv:r7`、`json:#/results/accuracy`。

**输出**：`case_id`、材料清单、摘要、事前容差表、基线 partial `result.json`。

**失败分支**：

- `init` 失败：先记录 `init_failed` 与 stderr；再运行 `python3 -B "$SK/scripts/verify.py" --selftest`。若仍失败，必须手写最小合法 `result.json` 到 `/app/output`，`status=input_error`，退出码 0。
- `/input/case.json` 缺失/损坏：继续以空 case 运行；`case_id=unknown`，`output_contract={}`，`errors` 写原因，`status=input_error` 或 `partial`。

### 步骤 2：真实解析材料，读原文而不是猜

**输入**：步骤 1 的材料清单与 `index.json`。

**动作**：

1. 对每个关键材料，真实读取内容：
   - PDF：优先调用平台预装工具，如 `pdf-text-tool` / `pdftotext`；若包内 `main.py show` 能读取文本层，也可用其定位。
   - DOCX/XLSX/CSV/JSON/MD/TXT：用对应解析路径读取；不得只依赖文件名。
   - 图片/扫描页：不猜像素或图注；无 OCR 就进入 `pending_human`。
2. 用脚本检索关键片段并回到原文：
   ```bash
   python3 -B "$SK/scripts/main.py" show --id paper --grep "accuracy"
   python3 -B "$SK/scripts/main.py" show --id paper --grep "learning_rate"
   ```
3. 亲自读 `show` 输出，确定论文报告值、表头、单位、条件、页码/段落；记录逐字 quote 和 locator。
4. 对候选实现/代码，读取实际命令、入口、默认参数、commit、依赖；不要仅凭文件名推断代码内容。

**输出**：逐字证据单元、论文报告值、关键参数、候选实现信息、材料限制清单。

**失败分支**：

- PDF 无文本层：记 `pdf_text:failed`，建议渲染/OCR，该材料不进数值判断，相关结论标 `pending_human`。
- DOCX/XLSX 无法解析或结果为空：记 `parse_failed:<type>`，不补造表格。
- 材料全部不可用：`status=insufficient_evidence` 或 `input_error`，仍产出合法 `result.json`。
- 材料内容与任务标签疑似冲突：以实际解析内容为准，在 `uncertainty` 中记录冲突，不得按错误标签补造数据。

### 步骤 3：构建证据、参数表与事前容差

**输入**：解析后的材料内容、`output_contract`、`draft_schema.md`、`repro_rules.md`。

**动作**：

1. 亲自写 `/app/work/draft.json`，至少覆盖：
   - `paper`：标题/DOI/repo/commit；未知写 `null`。
   - `plan`：复现步骤、命令、期望、状态。
   - `environment`：python/平台/依赖版本/seed；由 `init` 与本机实测填，不伪造。
   - `params`：每个关键参数的值、`class`、`evidence{source_id,locator,quote}`。
   - `paper_values`：指标名、报告值、单位、逐字 quote。
   - `tolerance`：只能等于或严于 `tolerance_plan.json`。
   - `claims`：每条含 `kind`、`text`、`confidence`、逐字 `quote`。
   - `conclusion.verdict`：`reproduced` / `partially_reproduced` / `not_reproduced` / `insufficient_evidence`。
2. 参数归类口径必须真实：
   - 论文正文/表格/附录明确给出 → `paper`。
   - 只能从代码默认值/配置推断 → `code_inferred`。
   - 两边都没有、由你设定 → `chosen`，并写入 `uncertainty`。
3. 容差必须在**任何运行之前**确定：
   - case 明确给出容差 → 记为 `case_declared`。
   - 否则使用默认先验：**相对 2% + 绝对 0.5% × 报告值**。
   - `check` 发现事后放宽 → 记 `tolerance_widened_after_run`，不能通过。
4. 运行证据/字段/容差校验：
   ```bash
   cd /app/work
   python3 -B "$SK/scripts/main.py" check
   ```

**输出**：`/app/work/draft.json`、`tolerance_plan.json`、`check` 报告。

**失败分支**：

- quote 找不到或与材料不一致：`check` 报 `evidence_rejected`。**绝不改原文凑通过**；删除该 claim 或降级为 `pending_human`。
- 关键字段缺失：补 `null`/`[]` 并在 `degradations` 中记 `missing_field:<字段>`。
- 参数值冲突：保留冲突，写入 `uncertainty`，不要强选一个伪装成事实。

### 步骤 4：真实运行候选方法并生成基线对比

**输入**：`draft.json`、`/app/work/tolerance_plan.json`、输入中的候选实现/命令。

**动作**：

1. 运行：
   ```bash
   cd /app/work
   python3 -B "$SK/scripts/main.py" build
   ```
   `build` 会无条件定稿：真实运行候选、保留 `/app/work/runs/<name>/run.log`、算偏差、做归因判断、写 `reproduction.md`、`reproduction.json`、回填 `result.json`。即使工作稿不完整也产出确定性最小交付，退出码恒 0。
2. 如果候选实现是脚本/命令，不要用伪输出替代；`observed` 只来自实际运行日志或标准输出。候选没跑起来就写 `insufficient_evidence`。
3. 记录每个候选：命令、`exit_code`、耗时、stdout/stderr、缺失依赖。
4. 对比每个指标：`observed` / `reported` / `abs_dev` / `rel_dev` / 容差 / 判定；没有论文报告值就写 `no_reported_value`。

**输出**：运行日志、对比表、基线归因、`reproduction.md`、`reproduction.json`、完整字段的 `result.json`。

**失败分支**：

- 候选找不到：不伪造运行，`pending_human` 要求人工运行回填，`status=insufficient_evidence`。
- 候选报错/超时：保留 `run.log`，记录 `exit_code/error`，`status=partial`。
- 候选无指标输出：记 `uncertainty`，不猜数值。
- 剩余时间 < 60 秒：跳过未跑的候选，记 `run_skipped_deadline`，立刻定稿。

### 步骤 5：Agent 亲自增强与核验（不得删基线）

**输入**：基线 `reproduction.md`、`reproduction.json`、`result.json`、`runs/`、原文证据。

**动作**：

1. 通读基线三件套，核对以下内容是否真实：
   - 材料定位是否回到原文 locator。
   - 参数值、分类、quote 是否一致。
   - 报告值是否逐字来自论文材料。
   - `observed` 是否来自单次真实运行。
   - 容差是否事前声明且未被放宽。
   - 差异归因是否与运行现象一致。
2. 你亲自增强 `reproduction.md` 和 `result.json`，而不是覆盖脚本结果：
   - 将脚本产生的确定性判定保留为基线字段；
   - 增加 `reviewed_by_agent` 标记、Agent 核验结论、冲突与限制；
   - 新增/修正内容写入 `changes`；
   - 对无法确认的项标 `verified` / `pending_human` / `conflicts`。
3. 若 `output_contract` 要求可编辑 Office/幻灯片/图形产物，生成或保留真实产物，并额外给出渲染 PDF/PNG 预览；