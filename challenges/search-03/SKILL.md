---
name: search-screen-rank
description: >-
  面向 Harness Agent 的文献筛选与智能排序 Skill。对已收集候选文献集真实解析、逐条判相关性、分层标注、去重合并、冲突升级，并产出确定性可解释排序与完整 result.json。本 Skill 的脚本只生成基线；最终交付物必须由 Agent 亲自读材料、推导、核验、撰写。
version: 2.0.0
---

# search-screen-rank — 文献筛选与智能排序

## 0. 最高铁律：完整交付 + 真实推导

脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作；禁止把脚本骨架、模板、未核验基线直接当成品。

- 先运行 `scripts/main.py` 产出全套基线，再在基线之上逐条核验证据、修正错误、补充缺失。
- 不得删除、清空或遗漏任何 `output_contract` 字段、基线文件、法定 `result.json` 字段。
- 不确定或材料不足必须标 `pending_human` / `uncertainty` / `limitations`；不得编造文献、摘要、DOI、年份、分数、引用或“最新进展”。
- 任何情况下都要产出合法 `result.json`，退出码 0。

## 1. 目录、预算与调用契约

- 输入：`/input/case.json`、`/input/task.md`、题面提供的材料（PDF/DOCX/CSV/图片等）。
- 工作目录：`/app/work`；最终产物：`/app/output`。
- 只读 `/input`，只写 `--out`（默认 `/app/output`）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本本身消耗 0 次模型请求。
- 启动即落盘 honest partial；后续增量增强。

调用命令：

    python3 -B scripts/main.py --input /input --out /app/output
    python3 -B scripts/main.py --input /input --out /app/output --k 5,10
    python3 -B scripts/verify.py --input /input --out /app/output

脚本依赖：Python ≥3.8 标准库；无第三方包、无网络、无模型请求。`scripts/main.py` 使用 `Path(__file__).resolve().parent.parent` 定位 `references/`，与当前工作目录无关。

## 2. 本题专属执行流程

### Step 1 — 盘点输入与输出契约

- 输入：`/input/case.json`、`/input/task.md`、题面材料文件。
- 动作：
  1. 列出 `/input` 下文件：`ls -R /input`。
  2. 读取 `task.md`，明确评分维度、Runtime contract、输出要求。
  3. 读取 `case.json`（若存在），提取 `case_id`、`output_contract`、任务说明、科研问题、范围约束、候选材料路径。
  4. 将 `output_contract` 全部字段记录到 `/app/work/contract_fields.txt`；未知字段也要保留清单。
- 输出：`/app/work/inventory_notes.json`，含 `case_id`、`contract_fields`、待解析材料列表、缺失项。
- 失败分支：
  - `case.json` 缺失或坏 JSON：继续读 `task.md` 并扫描材料；不要停止运行。
  - 无 `output_contract`：按 Runtime contract 要求生成标准字段，并在 `contract_missing` 说明。

### Step 2 — 立即运行基线脚本，先落完整基线

- 输入：`/input`。
- 动作：运行 `python3 -B scripts/main.py --input /input --out /app/output`。
- 目的：立刻产出全套基线：`result.json`、`candidates.csv`、`query_log.json`。启动即写 partial，即使中断也保留合法 JSON。
- 输出：`/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/query_log.json`。
- 失败分支：
  - 脚本异常：捕获错误，写入 `/app/work/baseline_error.txt`；仍必须手工构造最小合法 `result.json`。
  - 脚本生成不全：继续后续增强；不得删改基线文件，除非你有可核验证据并保存 `changes` 记录。

### Step 3 — 真实解析材料，不凭文件名猜测

- 输入：题面提供的 PDF/DOCX/CSV/图片/JSON/JSONL 等材料。
- 动作：
  1. 对 JSON/JSONL/CSV：真实读取内容与记录字段。
  2. 对 PDF：使用环境提供的 PDF 文本提取工具（如 `pdf-text-tool` 或平台预装等价工具）提取**全文文本**，再从文本中定位候选记录。不得因为文件名或领域标签推断摘要、结论、数据。
  3. 对 DOCX/图片：能用平台工具提取则提取；无法提取内容则不要补造，在 `degradations` 记录。
  4. 每条候选记录保存真实原文字段：题名、摘要、作者、年份、出处、DOI、URL、来源数据库、query_id、retrieved_at、已有标注等。
  5. 保存每条的 `provenance.file` 与定位信息。
- 输出：`/app/work/parsed_records.json` 或等价工作文件。
- 失败分支：
  - 单个文件解析失败：只跳过该文件，写 `degradations[stage=parse]`。
  - PDF 无文本层或解析失败：不得按文件名编造内容；相关记录标 `pending` 或 `insufficient_evidence`，进入 `pending_human`。
  - 材料为空：输出空 `candidates`，不补造文献。

### Step 4 — 构建/核对证据与判据

- 输入：`/app/work/parsed_records.json`、基线 `result.json`、`references/label_taxonomy.md`、`references/io_contract.md`。
- 动作：
  1. 逐条核对基线中的候选记录与真实解析内容是否一致。
  2. 逐条检查 `evidence[0].quote` 是否来自该记录摘要或题名的逐字片段；`locator` 应写 `abstract` 或 `title`。
  3. 按 `label_taxonomy.md` 的分档规则核对 tier：`core` / `method` / `background` / `pending` / `exclude`。
  4. 检查重复与版本合并：DOI 归一化后一致或归一化题名一致应合并；预印本优先升级为正式发表版本。
  5. 检查冲突：标注不一致、预印本与正式版本并存、同一研究多篇报道等，记录到 `conflicts` 并按规则升级 `pending_human`。
  6. 检查排序和平局键：`tier → score↓ → year↓ → 归一化题名↑ → record_id↑`；每条写 `tie_group`。
- 输出：`/app/work/evidence_check.json`，含 `verified`、`corrected`、`pending_human`、`conflicts`。
- 失败分支：
  - 发现基线错误：直接在 `/app/output/result.json` 与 `candidates.csv` 上修正，并追加 `changes` 记录。
  - 证据无法逐字匹配：将该项标 `pending_human`，不要强行写入不可核验 quote。
  - 材料不足：标 `uncertainty`，列出 `limitations`。

### Step 5 — Agent 亲自产出完整成品

- 输入：Step 4 核验结果、原始材料、输出契约。
- 动作：
  1. 确保每条候选文献都有：rank、id、tier、decision、relevance_score、score、题录、DOI/URL、source_db、query_id、retrieved_at、design_fit、reason、flags、evidence_quote。
  2. 确保覆盖候选集全部条目；重复与版本变体合并后仍要在 `group_ids` 中保留全部成员。
  3. 生成或修正 `candidates.csv`：一候选一行，字段与基线保持一致。
  4. 生成或修正 `query_log.json`：查询→来源→报告命中数→关联记录数→保留/待定/排除。
  5. 逐条写排序理由：命中哪条纳排条件、依据摘要哪段证据、置信度如何。
  6. 若 `output_contract` 要求可编辑 Office/幻灯片/图形成品，必须额外生成**真实渲染的 PDF/PNG 预览**；本题若未要求，不要为了凑数创建缺失文件。
  7. 最终 `result.json` 必须包含原 `output_contract` 全部字段，键名不改，未知字段透传，缺值写 `null`/`[]`。
- 输出：最终 `/app/output/result.json`、`/app/output/candidates.csv`、`/app/output/query_log.json`。
- 失败分支：
  - 无法完成所有候选：写 `status=partial` 或 `insufficient_evidence`，明确列出缺失项。
  - 只能判断部分：未完成项进入 `pending_human`，并写清原因。

### Step 6 — 自检 rubric 与契约

- 输入：`/app/output`、`/input`。
- 动作：
  1. 运行 `python3 -B scripts/verify.py --input /input --out /app/output`。
  2. 查看 `verify_report.json`，修复 `contract_missing`、`evidence_verbatim` 失败项、排序错误、计数错误。
  3. 对照 `task.md` 的评分维度逐项检查：实际效果、使用增益、创新增益、可靠体验、生态贡献。
  4. 检查 `result.json` JSON 合法性，以及 `case_id` 是否与输入一致。
  5. 检查 `status` ∈ `ok | partial | insufficient_evidence | input_error`。
- 输出：`/app/output/verify_report.json`。
- 失败分支：
  - 自检发现缺字段：先补齐字段再收尾。
  - 无法补齐：在 `degradations` / `pending_human` 中明确说明。

### Step 7 — 最终回填与退出

- 动作：
  1. 回填 `result.json` 的 `status`、`sources`、`uncertainty`、`changes`、`runtime`、`reviewed_by_agent`。
  2. 确保 `/app/output/result.json` 存在并且是合法 JSON。
  3. 确保脚本退出码 0，即使存在 `errors`、`degradations`。
  4. 写 `changes`：每条修改都要有 `stage`、`reason`、`detail`，不得伪装成正式测试结果。
- 输出：最终合法 `result.json`。
- 失败分支：任何失败都保留已落盘 partial，退出码仍为 0。

## 3. 预算策略：64 次请求内先保 40 分实际效果

评分权重最高的是“实际效果 40 分”，要优先保证候选集逐条完整筛选、分层、排序、证据可核验。

建议模型请求分配：

| 阶段 | 预算 | 说明 |
|---|---|---|
| 读 task/case/契约 | ≤4 | 不要重复读同一文件；先读关键字段 |
| 真实解析材料 | ≤12 | 批量读取记录；大文件用脚本抽取片段后再读 |
| 核验基线与证据 | ≤15 | 优先核验高分/关键文献，再核验边缘项 |
| 修正与提升 | ≤8 | 宁改关键错误，不做无限润色 |
| 自检与 verify | ≤10 | 只针对报告中的失败项修改 |
| 异常储备 | ≤15 | 解析失败、契约缺失、时间紧张时使用 |

执行原则：

1. 第 2 步必须先跑 `scripts/main.py`，在约 30 秒内获得完整基线。
2. 时间 <120 秒或模型请求 ≥55 次：停止新增强，只做“补字段 + 写 changes + 保证合法 JSON”。
3. 不要在单次响应中读取超大材料；用脚本或分段读取，避免超出 16384 tokens。
4. 避免重复读同一候选或同一文件；将解析结果写入 `/app/work` 后复用。
5. 若只能部分完成，先落盘 honest partial，再增量改进。
6. 脚本产生的 baseline 是安全网；不要为了“更聪明”删掉它。

## 4. 隐藏案例鲁棒性与降级

三个隐藏案例会变主题、规模、格式、缺失情况；脚本可能遇到任何输入，但你必须稳定交付合法 `result.json`。

| 情况 | 处理 | 落点 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续读 `task.md` 并扫描材料；无记录则空候选 | `errors[stage=read_case]`，`status=input_error` 或 `insufficient_evidence` |
| `output_contract` 缺失 | 按 Runtime contract 标准字段生成；用 `contract_missing` 记录缺失 | `contract_missing` |
| 候选集为空 | 输出空 `candidates`，不补造文献 | `errors` + `uncertainty` |
| PDF 无文本层/提取失败 | 不按文件名编造内容；相关记录标 `pending` 并升级人工 | `degradations[stage=parse]`、`pending_human` |
| DOCX/XLSX 等二进制不解析 | 记录不支持，提示导出 CSV/JSON；不编造 | `degradations` |
| 摘要/年份/DOI 缺失 | 缺摘要→`pending`；缺年份不参与年份排除；缺 DOI 打标不推断 | `flags`、`uncertainty` |
| 查询 429/权限/接口异常 | 保留原始 status/error，不要替换为成功 | `queries[].status/error` |
| 大量同分 | 记录 `tie_group`，用排序键兜底 | 每条 `tie_group` |
| 超大输入或中断 | 已处理部分保留在 partial `result.json` | `errors[stage=run]`、`changes` |
| 时间/预算耗尽 | 停止增强，写出`status=partial`，列出缺失项，退出 0 | `degradations` |
| 内部异常 | 捕获并写 `errors`，保留 partial，退出 0 | `errors[stage=run]` |

任何情况下：

- 必须产出 `/app/output/result.json`。
- `result.json` 必须合法 JSON，退出码 0。
- 不确定的内容必须显式标注 `pending_human` / `uncertainty` / `limitations`。
- 不补造文献、摘要、DOI、年份、引用、分数。

## 5. 输出契约字段与文件

### `result.json` 必须包含

- `case_id`
- 原 `output_contract` 全部字段，键名不改，未知字段透传
- `contract_echo`
- `contract_fields`
- `contract_fill`
- `contract_missing`
- `status`
- `candidates`
- `tiers`
- `screening`
- `metrics`
- `conflicts`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `sources`
- `runtime`
- `changes`
- `method`（打分公式、分档规则、平局键、版本）
- `reviewed_by_agent`（核验状态：verified / corrected / pending_human）

`status` 允许值：`ok | partial | insufficient_evidence | input_error`。

### 磁盘产物

| 文件 | 内容 |
|---|---|
| `result.json` | 最终结构化结果，含上述字段 |
| `candidates.csv` | 一候选一行：rank、id、tier、decision、relevance_score、score、题录、DOI/URL、source_db、query_id、retrieved_at、design_fit、reason、flags、evidence_quote |
| `query_log.json` | 查询→来源→报告命中数→关联记录数→保留/待定/排除 |
| `verify_report.json` | `scripts/verify.py` 独立复核报告 |

## 6. Rubric 维度 → 交付要求 → 自证方式

| Rubric 维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 实际效果：任务完成度 | 15 | 对给定候选集逐条完成相关性判断、分层筛选、排序 | `candidates` 覆盖全部输入记录；`screening` 计数与输入一致 |
| 实际效果：结果正确性 | 15 | 相关性标签与标注标准一致，排序把真正相关文献放在前面，元数据准确 | `tier` 与 `label_taxonomy` 一致；`evidence_quote` 逐字可核验；verify_report 通过 |
| 实际效果：结果完整性 | 5 | 覆盖候选集全部条目，召回不丢，重复与版本变体被处理 | `input_record_count - Σ(version_count-1) == len(candidates)`；`group_ids` 保留全部成员 |
| 实际效果：结果可核验性 | 5 | 逐条理由、打分口径、k 值与平局处理可复核 | `method.scoring`、`tie_group`、`changes`、`provenance` 清晰 |
| 使用增益：质量增益 | 15 | 相对基础 Agent 提升筛选与排序质量 | `metrics` 与 `changes` 记录基线-vs-核验后差异，不伪造分数 |
| 使用增益：效率增益 | 5 | 降低单位文献复核时间、待定区规模、人工返工 | 分层明确，待定/冲突项集中；`metrics` 写实际可验证口径 |
| 使用增益：增益可验证性 | 5 | 通过公平对照证明改善 | 保留基线产物与核验报告；不发明 benchmark 分数 |
| 创新增益：新增