---
name: citation-manager
description: 参考文献与引用管理 Skill。读取真实稿件与真实文献库（BibTeX / RIS / CSL-JSON / GB/T 7714 文本），完成论断级引用插入定位、顺序编码制编号连锁更新、文献去重归并（可解释判据）、GB/T 7714—2015 或 APA 7 格式转换、DOI 与元数据核验、正文—文献表一致性检查，产出可继续编辑的稿件、同步的文献表与逐条可回溯的 result.json。当用户要求“整理参考文献”“补插引用”“更新/重排编号”“文献去重合并”“改成 GB/T 7714 或 APA”“核对正文引用与文献表是否一致”时使用。
version: 2.1.0
license: MIT
entrypoint: scripts/main.py
runtime: python3 >=3.9，仅标准库，无网络
---

## ★ Agent 修改边界（最高优先级，先读）

本 Skill 的**结构化产物由脚本生成**；你（Agent）的职责是真实阅读材料、核验、补全文本型交付物，**不是重写结构化 JSON 的结构**。严格遵守：

1. **禁止手改结构化产物**：`claims.json`、`evidence_table.json`、`result.json` 的结构字段（键名、claim_id、source_id、locator、quote、strength、support_scope、counts）**必须原样保留脚本输出**。不得用文本编辑覆盖这些文件。
2. **允许 Agent 做的事**：
   - 真实阅读 `/input` 材料，核验脚本抽取的 quote / locator / 数字是否与原文一致；
   - 把核验结论写进 `agent_review.json`（新增文件：逐条列出 claim_id → 核验结果 verified/rejected/reason）以及 `pending_human.json` 的补充项；
   - 亲自撰写/改写 **正文型交付物**（`deliverable.md` / `manuscript.md` 等），但每个数字、引用、论断必须能在 `evidence_table.json` 中找到依据；成稿不得删除契约要求的字段；
   - 若发现脚本缺陷：写一个临时 python 调用脚本函数重算并覆盖（记录在 `agent_review.json` 的 `script_fixes`），**不得手工篡改 JSON**。
3. **禁止生成无依据的评分/金标准**：不要自造 `golden_standard`、`diff_report`、加权自评分；核验只引用 `verify.py` 的真实输出 `verification.json`。若脚本已生成上述自设资产，**不要引用、不要美化**，在 `agent_review.json` 里说明其局限。
4. **完整性自检**：结束前核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；`deliverable.md` 与 `evidence_driven_draft.md` 如同时存在，两者内容必须不同（前者=干净成稿，后者=带证据标记草稿），不得复制粘贴同一文本。
5. **预算**：先让脚本产出全套基线（通常 1–2 次调用即可），再把剩余请求用于逐条核验与成稿改进；接近 64 次/900 秒时立即收尾，保证 result.json 合法且 status 诚实。

# citation-manager（写作04｜参考文献与引用管理）

## 0. 最高优先级：谁为结果负责

本 Skill 帮助 Harness Agent 完成“参考文献与引用管理”的实际案例。`scripts/main.py` 与 `scripts/reftool.py` 只是工具：它们负责确定性解析、编号、去重、渲染，产出基线。**最终交付物由你（Harness Agent）亲自阅读 `/input` 真实材料、逐条核验与推导、撰写或修正；脚本输出只是基线，禁止把脚本模板、示例结果或骨架直接当作成品。**

你必须本着自己阅读材料、自己做判断的方式完成案例。任何引用插入、去重合并、字段补齐、格式转换、来源核验，都必须有原始材料证据；不允许根据文件名、领域标签或案例标题猜测内容，不允许补造 DOI、卷期页、作者、引用或分数。脚本能做的自动化动作可以信任但其结果仍要抽核；涉及 `weak_match`、`ambiguous_pairs`、`pending_human` 的项必须由你亲自复核。

“完整优先”是最低要求：先得到全套基线交付物，再在其上增量增强；不得删除、清空或遗漏任何基线与契约字段。

---

## 1. 用途与边界

一次运行覆盖六类动作中的可自动化部分，并由 Agent 完成人工判断闭环：

| 动作 | 工具实现 | Agent 必须补足的部分 | 主要产物 |
|-|-|-|-|
| A 引用插入与定位 | 识别缺来源的论断句，按题名+摘要词项覆盖率匹配文献库，句末插入编号 | 核对每条插入是否落在真正需要支撑的句子；排除整段末尾灌注 | `change_log` / `citation_map` |
| B 编号连锁更新 | 按正文首次出现顺序重排 `[n]`，同步正文与文末列表；保留 `[3-5]`、`[1,3]`、`^[1]^` 等样式 | 检查编号连续性、交叉引用、上标一致性 | `manuscript.md` / `changes` |
| C 文献去重归并 | DOI 精确 → 规范化题名相等 → 题名相似+同作者+年份接近；冲突进入 `ambiguous_pairs` | 解释每条合并或保留的判据，避免误合并同名作者不同文献 | `dedup_decisions` / `merge_groups` |
| D 格式转换 | 统一条目模型 → GB/T 7714—2015 或 APA 7；保留 DOI、卷期页、类型标识 | 检查中英文混排、标点、字段占位 | `references_formatted.md` |
| E 来源核验 | DOI 语法、重复 DOI、按类型缺字段、孤立引用、编号连续性、数字/单位保留 | 发现脚本未检出的异常；对可疑条目手动核对原稿 | `verification` |
| F 论断–文献匹配 | 每条引用所在句与被引条目题名/摘要词项重叠，低重叠标 `weak_match` | 逐条复核低重叠项，决定接受、改写或 pending_human | `citation_map` |

**不做**：不联网检索、不补造 DOI/卷期页/作者、不改写事实与结论、不臆造文献条目。所有条目只来自输入文献库或稿件自带的参考文献表。若题面要求需要网络检索，则公开说明无法执行并写 `limitations`，不伪造检索结果。

---

## 2. 适用条件

- 稿件为 Markdown/TXT；`.docx` 会被抽取正文文本，但版式与上标样式可能丢失，需人工复核；含或不含文末参考文献表均可。
- 文献库为 `.bib` / `.ris` / `.json`（CSL-JSON）或 GB/T 7714 文本列表。
- 需要中文顺序编码制（GB/T 7714—2015）或英文 APA 7；其他规范需改 `references/styles.md` 的渲染规则，不在当前版本内。
- `.xlsx` / `.csv` / `.enw` 文献库未内置解析器，会被记为 `degradations: unsupported_or_unrecognized_format`；此时请先导出为 RIS/CSL-JSON 再运行，或由 Agent 如实标注不支持。

---

## 3. 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。**必须真实解析材料内容**，不得依据文件名或领域标签猜测/补造内容。
- 工作目录 `/app/work`；最终产物必须落在 `/app/output`；可编辑 Office/幻灯片/图形产物必须额外给出真实渲染的 PDF/PNG 预览（本 Skill 默认输出 Markdown，可直接编辑；若契约要求 .docx/.pptx 等，则用环境可用工具生成并渲染预览）。
- 只用 Python 标准库；不联网；不依赖当前目录（资源路径基于 `__file__`）。
- **退出码恒 0**；启动即写 partial `result.json`，结束时无条件 finalize 覆盖；任何异常写入 `errors`/`degradations`。
- 必须包含 `result.json`，且包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`。
- 若 `output_contract` 缺失，则以本 SKILL §7 列出的固定字段作为最小契约回填；无法满足的字段写 `null` 或 `[]` 并在 `uncertainty` 说明。

---

## 4. 工具脚本调用方式

从包目录运行：

```bash
cd /skills/weekly-skill
python3 -B scripts/main.py --help
python3 -B scripts/main.py                                   # /input -> /app/output, GB/T 7714
python3 -B scripts/main.py --input /input --output /app/output --style apa
python3 -B scripts/main.py --input ./caseA --output ./outA --no-insert   # 只出建议，不改稿
```

| 参数 | 说明 |
|-|-|
| `--input` | 输入目录，默认 `/input`；不存在时回退到 `/input`、包根同级 `input/` |
| `--output` | 输出目录，默认 `/app/output`；不可写时回退 |
| `--style` | `gbt7714`（默认）或 `apa` |
| `--no-insert` | 只登记引用插入建议（`change_log.applied=false`），不修改稿件 |
| `--version` | 打印版本 |

脚本核心流程：

`discover → 选稿件 → parse_library（逐文件容错）→ 去重归并 → 文末表↔库对齐 → 论断级插入 → 首现编号重排 → 渲染 → 校验 → 落盘 → 契约回填`

输入发现与算法细节见 `references/rules.md`；格式字段映射见 `references/styles.md`；完整调用步骤、字段说明、限制见 `references/usage.md`。

---

## 5. 本题专属执行流程（Harness Agent 必做）

以下编号为执行顺序。每步都要落盘；不要等全部完成才写 `/app/output/result.json`。

### 步骤 0：读取任务与输出契约（1–3 次模型请求）

- 输入：`/input/task.md`、`/input/case.json`
- 动作：读取 task.md 的题面约束与 case.json 的 `case_id`、`output_contract`、`task_instruction`、`organizer_workorder` 等字段。
- 输出：在内存或 `/app/work/agent_checks.md` 中记录：`case_id`、预期交付物列表、要求风格（GB/T/APA）、需覆盖动作、输出字段。
- 失败分支：`case.json` 缺失或坏 JSON → 记入 `errors`，继续从 `/input` 扫描材料；`output_contract` 缺失 → 用本 SKILL §7 字段兜底。

### 步骤 1：盘点输入与材料（1–4 次模型请求）

- 输入：`/input/**` 全部文件。
- 动作：递归列出文件；按扩展名 + 文件头识别稿件、文献库、case JSON 等。脚本会自动做，但你必须核对识别结果是否合理。若材料是 PDF，**调用环境提供的 PDF 文本提取工具（如 pdf-text-tool）抽取文本**；不要仅凭文件名或标签推测内容。
- 输出：`sources` 清单（每个文件的 `id`、`kind`、`bytes`、`sha16`），选定稿件与文献库。
- 失败分支：材料缺失/格式不支持 → 记录 `missing_materials` 或 `degradations`；不构造内容。

### 步骤 2：运行脚本生成全套基线（1 次命令，不消耗模型请求）

- 输入：盘点结果。
- 动作：执行 `python3 -B scripts/main.py --input /input --output /app/output --style <gbt7714|apa>`。若题面只要求插入建议，可加 `--no-insert`。
- 输出：基线 `manuscript.md`、`references_formatted.md`、`references.json`、`report.md`、`result.json`。
- 失败分支：脚本崩溃 → 你必须在 `/app/output` 手工创建合法 `result.json`（可先写 `status: input_error`），继续 Agent 手工作业；已写文件保留。

### 步骤 3：真实解析关键材料（5–10 次模型请求）

- 输入：步骤 1 选定的稿件与文献库。
- 动作：**亲自读取稿件全文或关键段落，以及文献库条目题名、摘要、作者、年份、DOI、卷期页等字段。** 对 PDF 先转文本再读。记录证据摘录到 `/app/work/agent_checks.md`。
- 输出：证据笔记，至少包含：所有小节标题、引用标记位置、每条文献的关键识别信息、稿件中数字/单位/关键论断。
- 失败分支：PDF 未提供解析器或提取失败 → `degradations.unsupported_binary_pdf`，稿件无法解析则标 `insufficient_evidence` 并尽力保留原始内容。

### 步骤 4：核对与修正脚本结果（15–25 次模型请求）

- 输入：基线产物 + 步骤 3 证据笔记。
- 动作：逐项核对：
  1. `citation_map` 每条 `locator` 是否指向真实原句，`claim_quote` 是否逐字。
  2. 每条引用是否落在真正需要支撑的句子（而非整段末尾）。
  3. `dedup_decisions` 与 `ambiguous_pairs` 的判据是否成立。
  4. 正文编号是否 1..n 连续，文末列表是否与正文一一对应。
  5. 格式转换是否符合目标规范；缺字段是否用 `[待补]` 标记。
  6. `verification` 中 10 项检查是否真实通过。
- 输出：纠正错误后的 `manuscript.md`、`references_formatted.md`、`references.json`；在 `citation_map` 中可附加 `agent_review`、`agent_evidence_quote`；将无法确定项写入 `pending_human`。
- 失败分支：证据不足 → 保留原值 + `weak_match`/`pending_human`，不强行判定。

### 步骤 5：拟定完整成品与报告（4–8 次模型请求）

- 输入：修正后的结果。
- 动作：最终确认 `manuscript.md` 为可编辑成品；`references_formatted.md` 为同步文献表；`report.md` 含人读摘要、待人工确认项、错误与降级。若题面要求 Office 产物，则用环境可用工具生成并渲染 PDF/PNG 预览。
- 输出：`/app/output/` 最终文件。
- 失败分支：时间不足 → 保留现有完整基线，写 partial，列出未完成项；不得清空。

### 步骤 6：回填 result.json（3–6 次模型请求）

- 输入：全部产物。
- 动作：确保 `result.json` 合法且包含：
  - `case_id`
  - `output_contract` 的全部字段（缺失写 null）
  - §7 固定字段
  - 真实 `sources`、`runtime`、`status`、`errors`、`degradations`、`pending_human`
- 输出：合法 `result.json`。
- 失败分支：JSON 序列化失败 → 写最小合法 JSON，`status: partial`，`errors` 说明原因；退出码仍 0。

### 步骤 7：自检（2–4 次模型请求）

- 按 §9 自检清单逐项检查；发现缺项优先补齐或标注。
- 检查 `/app/output` 文件齐全、`result.json` 可解析、所有 `output_contract` 键存在。
- 提交前确认未把任何未核验脚本输出冒充最终成品。

---

## 6. 预算策略

总预算：**64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）**。脚本运行为普通进程调用，不计模型请求。建议分配如下：

| 步骤 | 建议请求数 | 必须/可跳 | 说明 |
|-|-|-|-|
| 步骤 0 读任务契约 | 1–3 | 必做 | 先确定最高权重交付物 |
| 步骤 1 盘点输入 | 1–4 | 必做 | 发现材料与格式 |
| 步骤 2 基线脚本 | 0 | 必做 | 可全自动 |
| 步骤 3 真实解析 | 5–10 | 必做 | 是“真实推导”的核心 |
| 步骤 4 核对修正 | 15–25 | 必做 | 重点核对 citation_map/去重/编号 |
| 步骤 5 成品与报告 | 4–8 | 必做 | 但可缩减润色 |
| 步骤 6 回填 JSON | 3–6 | 必做 | 契约完整优先 |
| 步骤 7 自检 | 2–4 | 必做 | 提交前把关 |
| 预留异常/返工 | ≤10 | 可跳 | 处理意外格式或契约 |

**优先级原则**：
1. 最先完成并落盘诚实 partial，然后增量改进。
2. 如果预算紧张，先保 `manuscript.md` + `result.json` + 契约字段；报告润色可减。
3. 避免重复解析同一文件；同一疑问只回看一次。
4. 超过 800 秒或接近 60 次请求时，停止非