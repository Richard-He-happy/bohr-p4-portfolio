---
name: research-library-qa
description: Inventory a research file library, maintain metadata/version relationships, and answer knowledge-base questions with verifiable evidence. Uses a one-command init→build→selfcheck pipeline with an Agent-first draft.json path and a deterministic AUTO_EXTRACT fallback. Produces inventory, version chain, evidence-grounded answers, reorganize plan, operations log, and a dual-echo result.json under /app/output.
version: 1.2.0
---

# research-library-qa（科研知识库问答：整理文件，也保留版本关系）

## 0. 最高准则：评委真正看重什么

本题高分不是“检索了多少文件”或“答案写了多少字”，而是**每个关键论断都能回到具体文件、具体版本、具体段落；证据不足时敢说“没有”并说明缺什么；换一个人拿着提交记录能复跑核对**。

因此本 Skill 的必须达成：

1. 每个关键论断、数字、引用必须带 `[S#]` 来源编号与 `文件相对路径#段落号/行号/页码` locator。
2. 引用必须是原文逐字 quote，不概括、不改写、不推测；quote 与 locator 必须能独立回到原文核对。
3. 材料缺失、文件不可读、扫描件无文本层、权限不足、版本冲突、证据矛盾，必须显式登记，不得把未完成写成完成。
4. 所有产物必须与题面 `output_contract` 字段一一对应；`result.json` 必须双回显契约字段。
5. 单命令即可完成完整流程；任何异常也退出码 0，且 `/app/output/result.json` 必须存在并合法。
6. 实际文件和原文是事实依据；不得根据文件名、领域标签、sidecar 摘要或预制答案补造内容。

---

## 1. 运行契约与目录

- Skill 安装位置：`/skills/weekly-skill`
- 输入目录：`/input`，其中通常包含 `case.json`、`task.md` 及科研材料
- 工作目录：`/app/work`，用于台账、draft、中间文件
- 最终输出目录：`/app/output`，所有最终产物与可复核证据都写在这里
- Python：`python3 >= 3.8`，仅标准库，离线运行
- 执行预算：64 次模型请求 / 900 秒 / 每条响应 16384 tokens

### 1.1 单命令全流程入口

首选用一个命令完成 init→build→selfcheck：

```bash
cd /skills/weekly-skill
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 内部必须依次完成：

1. `init`：盘点材料、来源编号、候选抽取、冲突分组、写台账
2. `build`：校验/兜底抽取、渲染全部产物、finalize `result.json`
3. `selfcheck`：产物与契约自检、验证哈希/quote/locator、回填状态

也可以分阶段执行：

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work --draft /app/work/draft.json
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

`run` 或分阶段命令在异常情况下也必须退出 0；脚本内部必须把错误写入 `errors`/`failures`/`degradations`，而不是崩溃。

---

## 2. Agent-first 双路径执行流程

### 2.1 路径 A：Agent 核验并写 draft.json（推荐，质量更高）

1. 读取 `/input/case.json` 与 `/input/task.md`，确认 `case_id`、问题列表、材料位置、`output_contract` 字段。
2. 运行 `init` 产出台账：`/app/work/ledger.json`、`/app/work/files.json`、`/app/work/candidates.json`。
3. Agent 亲自读取台账中与问题最相关的关键原文（PDF/DOCX/CSV/JSON/MD），至少核验每个问题对应的候选证据。若案例文件少则全读；文件多则只读最相关 3–5 个。
4. Agent 将判断写入 `/app/work/draft.json`，至少包含：

```
{
  "case_id": "...",
  "questions": [
    {
      "id": "Q1",
      "verdict": "answered | insufficient_evidence | conflicting",
      "answer": "本问的明确结论或明确缺证结论",
      "evidence": [
        {
          "source_id": "S3",
          "quote": "逐字原文片段",
          "locator": "docs/a.pdf#para4",
          "strength": "direct | inferred",
          "support_scope": "该证据支撑哪个分句"
        }
      ],
      "uncertainty": "低/中/高，及原因",
      "missing": "若缺证，缺什么材料或什么字段"
    }
  ],
  "version_decisions": [
    {
      "source_id": "S2",
      "decision": "latest_version | duplicate_of | conflict",
      "reason": "基于 mtime/hash/内容版本标记的具体理由",
      "locator": "docs/a_v2.pdf#para1"
    }
  ],
  "gaps": ["无文本层文件：x.pdf", "权限不足：y.csv"],
  "reviewed_by_agent": true
}
```

5. `draft.json` 中每个判断必须来自原文或文件系统可验证事实；不确定就写 `pending_human`。
6. 再运行 `build --draft /app/work/draft.json`，让脚本渲染最终产物。
7. 运行 `selfcheck`，必要时增强 `answers.md` 或 `summary`，但不得手改结构化 JSON 字段结构。

### 2.2 路径 B：无 draft 时确定性兜底

如果 Agent 未写 `draft.json`，`build` 必须依据 `init` 台账**确定性生成实质工作稿**：

- 抽取逐字 quote；
- 生成 `source_id` 与 `locator`；
- 对每个问题生成初步 evidence 列表；
- 证据不足时 verdict 写 `insufficient_evidence`；
- 在 `result.json` 和 `changes` 中诚实记录 `AUTO_EXTRACT`，并把自动抽取的限制写入 `gaps` 或 `degradations`。

两条路径最终产出**同一套产物**与**同一份 result.json 契约结构**。路径 B 不得为空壳；它必须已经能交付可复核的清单、版本、问答与不确定性提示。

---

## 3. 最终产物清单

每个案例必须生成以下产物，除非 case 的 `output_contract` 明确要求额外文件：

- `result.json`：唯一最终状态机器可读文件，双回显契约字段
- `inventory.csv`：文件清单，一行一个真实文件，字段包含：
  - `rel, role, class, size, sha256, mtime, readable, readability`
  - `duplicate_of, version_chain, text_chars, extract_method`
  - 元数据字段及每个字段来源 provenance
- `version_chain.json`：版本链，含 document、hash、version token、confidence、rule
- `answers.md`：每个问题的最终回答。每段关键论断必须带 `[S#]` 与 locator
- `reorganize_plan.csv`：组织/重排计划，含原始路径、目标路径、操作、状态、来源
- `operations.log`：操作记录，含可复跑步骤、变更、跳过、失败、恢复
- `library/`：按 plan 实际整理后的文件或副本，并保留哈希可核对
- `verify.json`：自检报告，含哈希抽查、quote 抽查、契约字段检查

### 3.1 证据格式强制要求

- 引用用 `[S#]` 标记；`[S#]` 必须能在 `sources` 中找到。
- locator 格式统一为：
  - `相对路径#L12` 表示第 12 行
  - `相对路径#para4` 表示第 4 段
  - `相对路径#page3#para2` 表示第 3 页第 2 段
- 若原文是表格，locator 可写 `相对路径#sheet2#cellC7` 或 `相对路径#table3#row5`。
- 若引用为 paraphrase 或推断，必须在 `strength` 标 `inferred`，且不得作为 direct quote。

### 3.2 完整性六维度

`result.json` 的 `coverage_dimensions` 必须逐项覆盖：

1. 文件类型
2. 元数据字段
3. 目录层级
4. 重复文件
5. 版本差异
6. 权限与来源

每项要么有数据，要么显式 `false` 并在 `gaps` 或 `pending_human` 说明为什么无法覆盖。

---

## 4. result.json 契约：双回显

`result.json` 必须同时满足：

### 4.1 顶层字段

顶层必须包含：

- `case_id`
- 原 `output_contract` 的每个字段，且键名保持不变
- `status`
- `summary`
- `library`
- `inventory`
- `metadata`
- `duplicates`
- `versions`
- `questions`
- `coverage_dimensions`
- `sources`
- `failures`
- `skipped`
- `conflicts`
- `uncertainty`
- `pending_human`
- `degradations`
- `errors`
- `changes`
- `operations`
- `verification`
- `runtime`
- `output_contract_fields`

### 4.2 嵌套 output_contract

必须在 `result.json` 中再放一份：

```
"output_contract": {
  "case_id": "<case_id>",
  "<原契约字段1>": ...,
  "<原契约字段2>": ...
}
```

双回显要求：原契约字段在**顶层**和**嵌套 output_contract** 中各出现一次；`case_id` 两处也必须一致。缺失字段用 `null` 或 `[]` 补齐，并在 `errors` 或 `degradations` 说明。

### 4.3 状态必须诚实

- 全部完成且可核验：`status = "ok"`
- 部分完成但有限制：`status = "partial"`
- 输入异常：`status = "input_error"`
- 任何未完成项不得写成已完成；缺证问题 verdict 必须是 `insufficient_evidence`。

---

## 5. 隐藏案例鲁棒性

### 5.1 正常案例

- 完整执行 `run`，产出全部基线资产。
- Agent 按路径 A 核验关键引用和版本判断。
- 重点核验：quote 逐字一致性、locator 存在性、重复文件哈希分组、版本链 latest/conflict 是否合理。

### 5.2 边界案例

- **扫描件 PDF 无文本层**：不强行 OCR；在 `inventory` 中 `readable=false`，标记 `pdf_no_text_layer`，排除出证据，入 `pending_human`，说明需要 OCR。
- **文件不可读/权限不足**：保留文件条目，`readable=false`，记录具体原因，不编造内容。
- **目录为空**：`status=input_error` 或 `partial`，库存空，`pending_human` 说明缺材料。
- **`case.json` 损坏/无 output_contract**：记录 `errors[]`，继续扫描材料；契约字段缺失用 `null`/`[]` 补齐并注明。
- **重复文件与版本冲突**：按 sha256 去重；版本冲突保留双方证据，标记 `version_conflict` 或 `conflict`，不静默消解。
- **证据互相矛盾**：不选边，列出双方原文 quote 与 locator，标 `conflicting`，说明冲突点。

### 5.3 异常案例

- `/input` 缺失或不可读：写最小合法 `result.json`，`status=input_error`，`errors[]` 说明，退出 0。
- 脚本超时或崩溃：使用已落盘 partial 产物；若没有，Agent 手工写最小合法 `result.json`，退出 0。
- 不支持的二进制格式：哈希并入库，`no_text_extractor:<kind>` 标记，不猜内容。

---

## 6. 预算策略：64 次模型请求 / 900 秒

优先完成实际效果 40 分的核心，而非花预算在装饰性文本上。

推荐分配：

- 步骤 1 盘点输入：1–2 次请求
- 步骤 2 运行 `init`：1 次 bash 调用
- 步骤 3 Agent 读关键原文：4–10 次请求，最多读 3–5 个文件
- 步骤 4 写 `draft.json`：1–2 次请求
- 步骤 5 运行 `build` + `selfcheck`：1–2 次 bash 调用
- 步骤 6 增强 `answers.md`/`summary`：2–4 次请求
- 步骤 7 最终自检：2–4 次请求

若剩余请求不足 10 次或时间不足 120 秒，立即停止增强，只保证：

1. `result.json` 合法且双回显契约字段；
2. `inventory.csv` 与 `version_chain.json` 存在；
3. `answers.md` 每问有 verdict；
4. 退出码 0。

---

## 7. Rubric 维度 → 交付动作

### 实际效果 40 分

- **任务完成度 15**：`questions[].verdict` 非空；`answers.md` 每问有关键论断、证据、locator、不确定性。
- **结果正确性 15**：每个 `quote` 与原文逐字一致；`locator` 可回到真实文件；版本与权限处置正确；无编造引用。
- **结果完整性 5**：`coverage_dimensions` 六维度均有数据或明确 false+原因。
- **结果可核验性 5**：`inventory.csv` 有 sha256；`version_chain.json` 有哈希和版本 token；`verify.json` 可复跑。

### 使用增益 25 分

- **质量增益 15**：用逐字 quote 与 locator 代替基础 Agent 的泛化答案；缺证敢说“没有”；证据冲突显式标记。
- **效率增益 5**：一个 `run` 命令产出清单、版本、问答、计划、日志，减少人工核对。
- **增益可验证性 5**：`operations.log` 记录步骤；`verify.json` 可复跑；`references/method.md` 记录判定阈值与方法。

### 创新增益 15 分

- **新增能力 5**：sha256 去重、版本链推断、缺证判据、逐字证据回链。
- **方法改进 5**：确定性抽取 + Agent draft 两层；按哈希分组重复文件；按 mtime/hash/内容标记区分版本。
- **创新证据 5**：在 `summary` 与 `references/method.md` 中说明方法边界与适合/不适合场景。

### 可靠体验 10 分

- **调用易用性 3**：单命令 `run` 即可运行。
- **运行稳定性 4**：partial-first，异常写 `failures`/`degradations`，但持续产出可用结果。
- **异常处理 3**：不可读、扫描件、权限、空目录、版本冲突、证据矛盾均显式分类处理。

### 生态贡献 10 分

- **文档完整性 3**：本 SKILL.md + `references/method.md` + `references/schema.md` + `references/checklist.md`。
- **资源可复用性 4**：`scripts/main.py`、`scripts/library.py` 无第三方依赖；CSV/JSON 产物标准。
- **分享推广价值 3**：`answers.md` 与 `operations.log` 成为可分享、可移交的科研资料管理记录。

---

## 8. 自检清单

完成后逐项核对：

1. `/app/output/result.json` 存在且合法 JSON；`case_id` 正确；双回显完成。
2. 原 `output_contract` 的每个字段在顶层和嵌套 `output_contract` 中各出现一次。
3. `inventory.csv` 每行有 `sha256`、`readable`、`duplicate_of`、`version_chain`、来源 provenance。
4. `version_chain.json` 有 hash、version token、confidence、rule。
5. `answers.md` 每个问题有 verdict、证据 `[S#]`、locator、不确定性或缺证说明。
6. `reorganize_plan.csv` 与 `library/` 对应；哈希可复核。
7. `verify.json` 检查哈希、quote、locator、契约字段；若 fail，`result.json.verification.status` 不为 pass 并说明。
8. `coverage_dimensions` 六维度真实覆盖或显式缺失。
9. 所有 `failures`、`skipped`、`pending_human`、`degradations`、`errors`、`conflicts` 真实且具体。
10. Agent 的 `reviewed_by_agent` 记录核验了哪些引用/版本/数字。
11. 若 case 要求可编辑 Office/幻灯片/图形产物，已渲染 PDF/PNG 预览；否则无此要求。
12. 最终退出码 0；如果脚本异常，Agent 写最小合法 `result.json` 后退出 0。

---

## 9. 失败恢复与异常处理

- **脚本异常**：立即用已落盘的 partial 产物执行 finalize；若没有 partial，则手工写最小合法 `result.json`。
- **单文件解析失败**：不中断整体；该文件保留 inventory 并写 `failures`，其余继续。
- **契约字段缺失**：用 `null` 或 `[]` 补齐；在 `degradations` 记录“contract missing: <field>”。
- **证据不足**：verdict `insufficient_evidence`，`evidence` 可空，`missing` 写明缺什么。
- **版本冲突**：保留所有相关原文件与哈希，在 `conflicts` 中写双方 locator，不做主观选择。
- **任何情况下**：不伪造 `golden_standard`、不编造 benchmark 分数、不生成无来源评分。

---

## 10. 资源与依赖

- 运行脚本：`scripts/main.py`
- 核心库：`scripts/library.py`
- 方法说明：`references/method.md`
- schema 说明：`references/schema.md`
- 提交前自查：`references/checklist.md`
- 依赖：Python 3.8+ 标准库；离线；无需 pip install；无需网络
- 资源限制：最多 50 个 UTF-8 文本文件，单文件 ≤ 500KB，总大小 ≤ 2MB，无 symlink
- 中英文自适应：案例为中文则中文输出，英文则英文输出；引用保持原语言
- 运行工件可二进制保留，独立于最终 JSON 合法性

---

## 11. 最终交付一句话

用一条命令完成“盘点→哈希去重→版本链→证据抽取→问答→计划→日志→结果”，所有断言带 `[S#]` 与 locator，缺证敢标明，产物可复跑，`result.json` 双向回显契约字段，任何异常退出 0。