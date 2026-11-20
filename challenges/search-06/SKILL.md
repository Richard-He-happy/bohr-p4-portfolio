---
name: literature-delta-tracker
description: >-
  Incremental literature discovery and tracking. 围绕“订阅配置—固定时间窗检索—与上一快照比对—新增/变更清单—按规则提醒”的完整闭环，在 organizer-supplied source snapshots（Crossref/EuropePMC/publisher JSON、records.jsonl、CSV、queries.jsonl）上真实解析、重建记录、归一身份、去重与版本/撤稿链合并，对每个窗口做 delta diff，输出可回放证据。该 Skill 要求 Harness Agent 先运行基线脚本，再亲自读取材料、核验候选与窗口归属、修正缺失并诚实标注，禁止把脚本骨架/模板直接当成品。Use when a task asks for "latest / new / weekly literature tracking", a topic subscription, a new-item list between two dates, or a delta against an earlier snapshot. Writes result.json with all output_contract fields echoed, plus candidates.csv, query_log.json, alerts.json, alerts.md, snapshot.json and deltas/window_NN.json.
version: 1.1.0
license: MIT
---

# literature-delta-tracker

## 0. 给 Harness Agent 的最高优先级指令（先读这里）

你是最终交付负责人。`scripts/main.py` 与 `scripts/core.py` 只是工具，**最终交付物由你亲自读材料、推导、撰写/制作**。禁止把脚本骨架、模板或未经核验的自动输出直接当成品。

执行顺序必须是：

1. 先运行基线脚本，产出全套文件和所有 `output_contract` 字段的落盘版本（**完整性优先**）。
2. 再亲自打开 `/input` 下的真实材料与基线输出，逐项核验：候选文献是否真实存在于材料、窗口归属是否正确、去重和版本合并是否正确、提醒是否被正确抑制、状态/缺失项是否诚实。
3. 在基线之上修正和补强，**不得删除、清空或遗漏任何基线与契约字段**；若不确定，保留原产物并在 result.json 标注 `reviewed_by_agent`。
4. 完稿前按第 10 节自检清单逐项确认，再用 `scripts/core.py` 校验输出。

## 1. 用途与边界

本 Skill 解决“最新文献发现与追踪”的增量判定问题。给定订阅主题/查询集/时间窗和上一快照，返回相对上一个快照真正新增或改变的文献，并保留可回放依据。**判断是否做对，不看抓了多少条，而看增量判定是否可复算、重复与误报是否被压住、每个提醒是否有回放依据。**

在范围内：订阅配置、窗口定义、增量检索、身份归一、去重、预印本-正式版-修订-撤稿链合并、快照 diff、提醒合并/抑制、回放记录。

不在范围：全文阅读、自动写综述、未授权定时抓取、把提醒当科学结论；也不得编造数据、引用、分数或来源状态。

## 2. 何时使用 / 不使用

使用：任务包含 bibliographic records 且要求“latest / new / weekly literature tracking”、主题订阅、某日期窗口内新条目、或与旧快照比较。

不使用 / 无记录：输入没有任何 record-like 材料时，必须返回 `status=insufficient_evidence` 或 `input_error`，在 `missing[]` 说明缺什么，不发明文献。

## 3. Runtime contract（必须逐条落实）

- 输入 `/input`（只读）：`case.json`、`task.md`、题面规定的材料（PDF/DOCX/CSV/图片等）。**必须真实解析材料内容**，用环境提供的 `pdf-text-tool` 等工具实际读取 PDF/DOCX/图片，不得依据文件名或领域标签猜测/补造内容。
- 工作目录 `/app/work`：可写状态，如 `state.json`、中间校验文件。
- 输出 `/app/output`：最终 `result.json` + 全部 sidecar。可编辑 Office/slide/diagram 产物必须额外给出真实渲染的 PDF/PNG 预览；本题通常无此类产物，若 `output_contract` 要求则必须真实生成。
- `result.json` 必须包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`，并添加 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`missing`、`runtime` 等真实字段。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。先明确 rubric 权重最高的交付物，优先完成并**尽早落盘 honest partial**，再增量改进。
- 诚实性：status/sources/uncertainty/change records 必须真实；不确定或材料不足要显式标注 `pending_human` / `limitations`；不得编造数据、引用、分数。
- 任何情况下 exit code 为 0，包括空输入、坏 JSON、内部异常、超时降级。

## 4. 快速开始与保留的脚本命令

运行前先进入工作目录或传入绝对路径。标准命令：

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work
python3 /skills/weekly-skill/scripts/core.py --input /input --output /app/output
```

可选 flags：`--now 2024-03-01` 冻结时钟；`--window-start 2024-02-01 --window-end 2024-03-01` 覆盖窗口；`--max-k 20` 限制候选数。

注意：`main.py` 生成的是**基线骨架**，不是最终成品。你必须在其基础上完成真实材料核验、修正与诚实标注。

## 5. 执行流程（编号步骤）

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input` 下全部材料文件。
- **动作**：
  1. 读 `case.json`（fallback：任意 `case*.json`），保留 `case_id` 和 `output_contract` 原样。
  2. 读取 `task_instruction`、`organizer_supplied_scope`、`scope`、`constraints`（topic、include/exclude、lang、max_k 等）。
  3. 递归扫描 `/input/**`，按扩展名和内容识别材料文件；不要只凭文件名假设来源。
  4. 识别哪些文件是当前候选记录，哪些是 `snapshot|previous|baseline|state` 历史文件。
  5. 用 `pdf-text-tool` 等真实解析 PDF/DOCX/CSV/图片；解析失败则记录。
- **输出**：写入 `/app/work/agent_workplan.json`，至少包含：关键输入文件路径、`output_contract` 字段列表、识别到的窗口/订阅提示、rubric 权重最高的交付物清单、材料解析状态。
- **失败分支**：
  - `case.json` 缺失/不可解析：尝试扫描其他 JSON；仍不可用则准备最小合法 result.json（`status=input_error`，`errors[]`，`missing[]`），退出码 0。
  - 某材料无法解析：记入 `degradations[]`，继续处理其他文件。

### 步骤 2：运行基线脚本，产出全套骨架（完整性优先）

- **输入**：步骤 1 确认的 `/input`。
- **动作**：运行 `scripts/main.py`，确保输出目录 `/app/output` 被创建并写入所有 sidecar。
- **输出**：`result.json` 初稿（应 echo 所有 `output_contract` 字段）、`candidates.csv`、`query_log.json`、`alerts.json`、`alerts.md`、`snapshot.json`、`deltas/window_NN.json`。
- **失败分支**：
  - 脚本异常/超时：捕获错误到 `/app/work/script_error.txt`；立即尝试用 `scripts/core.py` 做静态校验；如果 result.json 未生成，手工创建包含全部 `output_contract` 字段与 `case_id` 的最小合法 JSON，`status=partial` 或 `input_error`，退出码 0。
  - 脚本成功但少字段：手工补齐缺失字段，不要删除已生成内容。

### 步骤 3：真实解析材料并核验证据

- **输入**：`/input` 全部材料、`/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/alerts.json`。
- **动作**：
  1. 亲自读取解析后的材料内容，提取订阅主题、查询式、时间窗起止、来源快照、去重键、无用记录等。
  2. 逐条检查候选文献：标题/DOI/作者/日期/期刊/版本是否真实出现在输入材料中。每个 DOI 若存在必须能在输入文本中 verbatim 找到；不能补造。
  3. 核验窗口归属：是否按 `[start, end)` 使用 UTC index/import date；跨窗、延迟入库、补抓是否被正确归类为 `recovered_late` 或 `out_of_window`。
  4. 核验版本链：预印本→正式版→修订→勘误/撤稿是否合并为同一 work；`version_chain` 是否保留各节点。
  5. 核验提醒：是否每条 merged work 只提醒一次；已提醒/低置信是否抑制；提醒投递记录是否可解析。
  6. 记录任何脚本判断与你阅读材料后判断不一致的地方。
- **输出**：在 `/app/work/agent_review_notes.json` 中写出核验结论，包括 `verified`、`conflicts`、`missing_evidence`、`pending_human`、`fixes_to_apply`。
- **失败分支**：
  - 材料缺失导致无法核验：在 result.json `uncertainty[]` / `pending_human[]` 标明，不伪造。
  - 冲突：保留基线产物，在 result.json 中标注 `conflict`，列出双方依据。

### 步骤 4：产出完整成品，回填 result.json 与 sidecar

- **输入**：步骤 3 的核验结论和基线产物。
- **动作**：
  1. 将核验结论写回 result.json：`checks.agent_review.summary`、`checks.agent_review.verified`、`pending_human`、`conflicts` 等。
  2. 修正候选、窗口、版本链、提醒等字段，但**只能增强，不得破坏基线结构**。
  3. 确保所有 sidecar 与 result.json 一致；如 `candidates.csv` 中行与 candidates 数组一一对应。
  4. 如果 `output_contract` 要求可编辑 Office/slide/diagram，生成真实文件并渲染 PDF/PNG 预览。
  5. 用 `scripts/core.py --input /input --output /app/output` 再校验一次。
- **输出**：最终 `/app/output` 完整文件。
- **失败分支**：
  - core.py 校验失败：修复具体错误；若无法修复，保留字段并标 `pending_human` / `limitations`，不能为空。
  - 时间不足：立即写回当前 result.json，`status=partial`，并确保所有契约字段存在。

### 步骤 5：rubric 自检与最终校验

- **输入**：最终 `/app/output` 全部文件。
- **动作**：按第 10 节自检清单逐项核对；检查 result.json 合法性；再次确认 exit code 0。
- **输出**：合规提交。
- **失败分支**：若