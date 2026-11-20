---
name: bio-mechanism-figure
description: 把机制材料（工单、论文段落、数据表）转成可追溯、可编辑的生物学机制图/通路图：分层 SVG + 单页矢量 PDF/PNG 预览 + content_map + compliance_checks + 来源/变更/不确定性记录 + result.json（原 output_contract 全字段）。Agent 亲自读材料并写 plan.json（实体/关系/证据/区室），脚本只做索引、逐字校验、渲染与可核验资产生成。先跑本包基线产出全套交付物并保留，再增量增强；任何情况下 result.json 合法且退出码 0。Use when the task asks for a biological mechanism diagram, pathway figure, signalling schematic, graphical abstract of a mechanism, or a source-preserving edit of one.
version: 3.0.0
---

# 生物机制图与通路图（Agent 主导，完整性优先 v3）

## 0. 头部声明与最高优先级

**用途**：把输入材料中明确写出的生物机制、通路、实体关系与数据编码，做成一张可编辑、可回溯、可独立复核的机制图：分层 SVG 源文件、真实渲染的单页矢量 PDF/PNG 预览、逐元素来源映射（content_map）、合规检查（compliance_checks）、金标准/diff/version/self-check/run.log 资产，以及包含 `output_contract` 全部字段的 `result.json`。

**脚本只是工具**：最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。脚本 `scripts/main.py` 与 `scripts/render.py` 只提供材料索引、逐字引用校验、确定性渲染与可核验资产生成；它们不做生物学判断，不能把脚本骨架/模板直接当成品。

**完整性优先（v6 混合策略，最高优先级）**：
1. 进入任务后，**立即运行本包基线主流程**，产出全套基线交付物（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段）。
2. **保留全部基线产物**：后续校验与改写只能在基线上增强；**不得删除、清空或遗漏任何基线与契约字段**；若不确定，保留原产物并在 `result.json` 标注 `reviewed_by_agent=true`。
3. **提交前必做完整性自检**：逐项核对「`output_contract` 字段列表 × 磁盘文件 × `result.json` 键」三者一一对应；缺任何一项先补齐再收尾；`partial` 状态必须列出缺失项。
4. **可核验增强**：在基线产物之上，由 Agent 亲自核验关键论断/数字/引用的来源一致性，把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`），这才是“genuinely-derived”的证据。

## 1. 运行契约与目录

- 安装位置：`/skills/weekly-skill`；下文命令用 `SKILL_DIR=/skills/weekly-skill`。若实际路径不同，用实际路径。
- 输入：`/input/case.json`、`/input/task.md` 及题面规定的材料（PDF/DOCX/CSV/图片/JSON/MD 等）。**必须真实解析材料内容**，不得依据文件名或领域标签猜测/补造内容。用 `scripts/main.py show` 提取并阅读原文；PDF/DOCX 用标准库提取文本层。
- 工作目录：`/app/work`；最终产物：`/app/output`。
- 主产物：`figure.svg`（可编辑源）、`figure.pdf`（真实单页矢量导出/预览，如可能附 `figure.png`）、`content_map.json`、`compliance_checks.json`、`plan.normalized.json`、`result.json`。
- 可核验资产（同一次 build 产出）：`golden_standard.json`、`diff_report.md`、`version_history.md`、`self_check.json`、`run.log`。
- `result.json` 要求：原样回填 `case.json` 里 `output_contract` 的**全部字段**（键名不改、不遗漏；缺值用 `null` 或 `[]`），另带 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`，以及文件指针与摘要：`golden_standard`、`diff_report`、`version_history`、`self_check`。
- 调用约定：`python3 -B $SKILL_DIR/scripts/main.py <子命令> --input /input --output /app/output --work /app/work`。脚本不依赖 CWD，纯标准库，不联网，`--help` 退出码 0。
- 异常处理：所有异常捕获进 `errors`/`degradations`；脚本命令失败必须被记录，最终 `result.json` 合法且退出码恒为 0。

## 2. 专属执行流程（编号步骤）

> 先跑基线，再真实解析，再增量增强。每步可重入；任何步骤失败不得中断最终产出。

### 步骤 0：初始化与基线落盘（必须先做）
- **输入**：`/input/case.json`、`/input/task.md`、输出/工作目录。
- **动作**：
  - 先运行 `init`：生成材料清单与合法 partial `result.json`。
  - 立即运行 `build`（即使 `/app/work/plan.json` 尚未写好，脚本会用确定性兜底产出最小但完整的全套基线）：
    ```bash
    python3 -B $SKILL_DIR/scripts/main.py init  --input /input --output /app/output --work /app/work
    python3 -B $SKILL_DIR/scripts/main.py build --input /input --output /app/output --work /app/work
    ```
  - 检查 `/app/output` 下是否已有全套基线文件。已存在的文件保留，后续只覆盖增强，不删除。
- **输出**：全套基线交付物（SVG/PDF、content_map、compliance_checks、plan.normalized、golden_standard、diff_report、version_history、self_check、run.log、result.json）。若 `plan.json` 缺失，这些产物标记为脚本兜底，`status=partial`。
- **失败分支**：命令失败或磁盘不可写 → 创建最小合法 `result.json`，记录 `errors`/`degradations`，列出已存在文件，退出码 0；如果脚本完全不可用，Agent 手写最小 `result.json` 并保留已有文件，绝不能因异常而无产出。

### 步骤 1：盘点输入与真实解析材料
- **输入**：`/input` 下所有文件、步骤 0 的材料清单。
- **动作**：
  - 读 `/input/case.json` 与 `/input/task.md`，提取 `case_id`、`output_contract`、任务类型、材料路径。
  - 用 `show` 命令查看材料切块与 locator，例如：
    ```bash
    python3 -B $SKILL_DIR/scripts/main.py show --doc note --locator para3
    python3 -B $SKILL_DIR/scripts/main.py show --doc figure03 --locator stream7
    ```
  - **真实阅读**关键段落：机制描述、实体/关系句、数据/图例句子。PDF/DOCX 读取文本层；CSV/JSON 直接读。扫描 PDF/位图无法提取文本时，只列出缺口，不 OCR 编造。
  - 每一步记录 `locator` 与原文 quote 草稿。
- **输出**：已读原文切片与定位、材料缺口清单、数据编码线索。
- **失败分支**：材料缺失/损坏/格式不支持 → 在 `gaps`/`degradations` 中写明“无法解析的路径/原因”，继续后续步骤；不允许按文件名或领域标签猜内容。

### 步骤 2：Agent 亲自推导并写 `plan.json`
- **输入**：步骤 1 的原文切片、`references/plan-schema.md`。
- **动作**：
  - 读 `references/plan-schema.md` 了解 schema。
  - 由你（Agent）在 `/app/work/plan.json` 写入：`title`、`compartments[]`（按上游→下游排序）、`entities[]`、`relations[]`、`data_encoding[]`、`gaps[]`。
  - 每实体/关系必须带 `evidence.quote`（原文逐字切片，≥6 字符）与 `locator`；区室/方向来自原文语序；材料没写的用 `unspecified`，不要补造。
  - 基因/蛋白/复合物/细胞类型/区室用原文写法，不擅自归一化合并。
- **输出**：`/app/work/plan.json`。
- **失败分支**：实体歧义、方向缺失、数据与文字矛盾 → 保留原文写法，`type` 用 `unspecified`，写入 `gaps`/`pending_human`；无法确定的不要当作事实。

### 步骤 3：核对证据与工作单
- **输入**：`/app/work/plan.json`、材料原文。
- **动作**：
  - 运行 `check`：逐字回验 `quote`，检查实体/关系是否缺 id/type/compartment，对照 workorder 声明条目。
    ```bash
    python3 -B $SKILL_DIR/scripts/main.py check --input /input --output /app/output --work /app/work
    ```
  - 若有 `rejected` 或 `issues`，修正 `plan.json` 中的引文/字段或标为未核验。
- **输出**：`/app/work/check_report.json`；状态为 `CLEAN` 或 `rejected/uncertain` 列表。
- **失败分支**：引文找不到 → 仍可继续 build，但标未核验并把整体状态降为 `partial`，写入 `uncertainty`/`counts.rejected_quotes`。

### 步骤 4：重建增强产物（保留基线的条件下）
- **输入**：修正后的 `plan.json`、基线产物。
- **动作**：
  - 再次运行 `build`。脚本会写出全套产物（覆盖增强见步骤 0）；基线文件不删除，只覆盖增强。
  - 如需要可运行 `selftest` 做只验健壮性检查：
    ```bash
    python3 -B $SKILL_DIR/scripts/main.py build    --input /input --output /app/output --work /app/work
    python3 -B $SKILL_DIR/scripts/main.py selftest --output /app/output --work /app/work
    ```
- **输出**：最终全套交付物与更新后的 `result.json`（含 `status/sources/uncertainty/changes` 等）。
- **失败分支**：`build` 失败 → 回退到步骤 0 基线产物，在 `result.json` 中记录降级，不删除任何文件。

### 步骤 5：自检 rubric 并回填 `result.json`
- **输入**：`/app/output` 全部文件、`/app/work/check_report.json`、`case.json.output_contract`。
- **动作**：
  - 对照第 5 节 rubric 表与第 6 节自检清单逐项核对。
  - 检查「`output_contract` 字段 × 磁盘文件 × `result.json` 键」一一对应；缺值用 `null`/`[]` 并在 `exceptions` 说明。
  - 把 Agent 核验结论写进 `result.json.verified`、`pending_human`、`conflicts`；把本轮全部变更写进 `changes`。
  - 确认退出码 0。
- **输出**：最终 `/app/output/result.json`（合法、诚实、完整）。
- **失败分支**：字段缺失 → 先补 `null`/`[]` 并填写 `exceptions`；仍未达到完整标准则标 `status=partial` 并列出缺失项，退出码仍 0。

## 3. 预算策略（64 次模型请求 / 900 秒 / 单次 16384 tokens）

- **必须做的步骤**：步骤 0（基线 init+build）→ 步骤 1（读关键材料）→ 步骤 2（Agent 写 plan）→ 步骤 3（check）→ 步骤 4（重建 build）→ 步骤 5（自检与回填）。这些构成完整闭环，不可跳过。
- **可跳过或缩减**：版式美化、反复试错、过多 diff 人工推断；如时间不够，优先保证主产物、结果正确性与可核验性。
- **请求分配建议**：
  - 步骤 0：2–3 次（init + build + 检查产物清单）
  - 步骤 1：10–20 次（用 `show` 读材料，优先读机制段/工单指令/图例或数据段；3–8 个核心实体与关系即可）
  - 步骤 2：3–8 次（写 plan.json 可一次写入，留修订余量）
  - 步骤 3：2–5 次（check + 修 quote）
  - 步骤 4：2–5 次（build + selftest）
  - 步骤 5：2–4 次（自检 + 回填 result）
  - 预留约 25–30% 余量处理歧义、rebuild、异常恢复。
- **时间阈值**：超过约 780 秒或约 50 次模型请求仍未完成时，立即保存当前最完整产物，运行 `build` 或保留基线，写 honest partial `result.json`，不要继续循环。
- **落盘策略**：最早在步骤 0 落盘全套基线，后面每次成功增强都更新 output；不要等到最后一次性写。

## 4. 隐藏案例鲁棒性与降级

任何情况下都要产出合法 `result.json` 且退出码 0。无法判断的写进 `pending_human` 并说明需要人确认什么。

| 情况 | 行为 | 落点 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 抢救 `case_id`/`output_contract`，继续跑 | `errors`、`status=partial/input_error` |
| `output_contract` 缺失 | 至少保证 `case_id,status,editable_source,export_artifact,content_map,compliance_checks,exceptions` 字段；缺值 `null`/`[]` | `exceptions` |
| 材料缺失/损坏/格式不支持 | 列出缺口，不猜内容，能跑多少跑多少 | `gaps`、`degradations` |
| 扫描 PDF/位图无文本层 | 不进正文，只列缺口；如环境有 OCR 可尝试并注明不确定性，没有则放弃 | `gaps`、`pending_human` |
| 无 `plan.json` | 由 `build` 用确定性兜底（工单条目→语义句挖掘→材料清单）产出最小完整图 | `degradations`、`subtitle` |
| 引文找不到/check 不 CLEAN | 仍出图，标未核验，整体 partial | `uncertainty`、`counts.rejected_quotes` |
| 金标准为空/无 workorder | 不补造实体，说明缺口 | `golden_standard.gaps`、`pending_human` |
| diff 有缺失/偏差 | 图仍出，降 partial，动作逐条列出 | `diff_report.md` §5、`result.diff_report.actions` |
| 实体歧义（基因/蛋白同名） | 保留原文写法，用 `kind` 区分，不合并 | `gaps`、`kind_basis=not_stated` |
| PDF 非拉丁字符丢字 | SVG 保留原文，PDF 丢字并计数 | `compliance_checks.pdf.chars_dropped_for_winansi` |
| 无位图渲染器 | 不出 PNG，用 PDF 作检视件 | `raster_preview`、`degradations` |
| 超时/接近预算 | 立即保存当前产物，运行 `build` 收尾，状态诚实标注 | `status=partial`、`runtime` |
| 空输入 | 生成空图或最小占位图，`status=empty/partial`，不编造 | `status`、`exceptions` |
| 探针子进程失败 | 记 `pass=false`，不中断主流程 | `self_check.fallback`、`verdict.failures` |

## 5. rubric 维度 → 交付要求 → 自证方式

| rubric 维度 | 交付要求 | 自证方式 |
|---|---|---|
| **实际效果（任务完成度 15 / 正确性 15 / 完整性 5 / 可核验性 5）** | 完成“读机制材料—定实体与关系—定布局与图例—出源文件与导出件”完整闭环；实体类型（基因/蛋白/复合物/细胞/区室）不混用；相互作用类型（激活/抑制/结合/修饰/转运）可区分；通路方向与数据编码与输入一致；覆盖工作单要求的实体、分支、反馈环