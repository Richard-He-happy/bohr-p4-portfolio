---
name: paper-to-academic-slides
description: Convert one research paper (PDF/DOCX/MD/TXT) plus an optional target template deck into an editable academic presentation. Builds a contribution-driven mainline, page-level claims, per-slide evidence with verbatim quotes and figure/table/section locators, separated speaker notes, template-inheriting .pptx, real PDF preview, and a dual-echo result.json covering the original output_contract. Use for paper-to-slides, 论文转PPT, 学术汇报, 组会, 会议报告, deck revision.
version: 3.0.0
---

# 论文转学术 PPT：组织页面并保留证据映射

## 0. 最高优先级：运行模型与边界

1. 唯一全流程入口（必须可用，且任何情况下退出码 0）：
   `python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`
   该命令内部依次完成 init → build → selfcheck：
   - init：盘点材料，给来源编号，抽取候选 quote、figures、tables、numbers，分组冲突项。
   - build：校验来源与候选；若 `/app/work/draft.json` 存在且合法则优先按 draft 生成；否则执行确定性兜底抽取，保留逐字 quote + locator，渲染全部产物，finalize `result.json`。
   - selfcheck：检查“原 output_contract 字段 × 磁盘文件 × result.json 键”是否一致，把结果写入 `compliance_checks`。

2. Agent-first 双路径：
   - Agent 路径：先运行 init 查看台账，真实阅读原文，把每页判断写入 `/app/work/draft.json`，再运行 build 和 selfcheck。
   - 无 draft 兜底：build 用 init 台账确定性生成实质工作稿，逐字 quote + locator；并把 `AUTO_EXTRACT` 写入 `degradations[]`/`gaps[]`，不得伪装成 Agent 已核验。
   两条路径必须产出同一套产物与同一条 result.json 契约。

3. 结构化产物由脚本生成。Agent 不直接手工改 `deck_model.json`、`evidence_table.json`、`content_map.json`、`result.json`；Agent 的增量判断写入 `draft.json`。确需脚本修复时，用 Python 调用 `scripts/main.py` 或 `scripts/deckbuild.py` 的函数重算，并在 `changes[]` 记录。

4. 任何失败、超时、缺失、低置信都不得崩溃：必须写合法 `result.json`，退出码 0。

## 1. 输入发现与契约

输入：
- `/input/case.json`：保留 `case_id` 与 `output_contract`；未知字段不得丢弃。
- `/input/task.md`：读取页数、受众、时长、模板继承、来源保留规则。
- 材料：第一个 >1.5KB 的 `pdf|docx|md|txt` 且非 `task.md/README` 作为论文；文件名匹配 `template|master|layout|style|brand` 的 `.pptx` 作为模板；无模板则用内置 master/layout/theme 并记降级。
- 其他图片/CSV/表格为辅助材料；实际科学事实以原始论文为准，不依据文件名或领域标签补造。

输出：
- `/app/output/result.json`：必须可解析 JSON，且包含原 `output_contract` 全部字段与 `case_id`。
- 可编辑幻灯片源文件：`presentation.pptx`。
- 渲染证据：`presentation.pdf`；无渲染器时 `export_artifact.pdf.valid=false`，保留 `.pptx`。
- 页级证据映射：`content_map.json` 或等价文件，必须逐页回溯。
- 页计划与模型：`plan.json`、`deck_model.json`。
- 其他检查报告/提取文本可放 `/app/work`；最终可核验文件放 `/app/output`。

## 2. Agent 应执行的步骤

建议预算：先完成 baseline，再增量核验；每阶段落盘 partial。

步骤 0：立即落盘骨架
- 读 `/input/case.json`；若无则搜索 `case*.json`。
- 写 `/app/output/result.json` 骨架：`case_id`、原契约字段、`status=partial`、`errors=["任务初始化中"]`。
- 保证即使后续超时也有合法 JSON。

步骤 1：盘点与解析
- 运行：
  `python3 /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work`
- 阅读 init 生成的台账：来源编号、候选 quote、图表表格编号、数字、冲突分组。
- 真实读取论文文本，与台账核对；解析研究问题、方法、结果、讨论、限制、结论、图表编号和关键数字。
- 若 PDF 加密/扫描/无文本层，停止生成 PPT：`status=partial`，记录不可提取，退出码 0。

步骤 2：写 `draft.json`（Agent 核心增值）
- 按 `references/output-schema.md` 的形状写入 `/app/work/draft.json`。
- 每页至少包含字段：`n, role, title, claim, bullets, evidence[{type,id,locator,quote,matched}], assets, notes`。
- `role` 使用 `references/page-outline.md` 的页角色，不按段落顺序搬运。
- 主张、bullet、数字、单位、方法名、结论表述必须来自原文；图表引用必须真实存在；不把示意图当实验数据。
- 每页 notes 与页面文字不重复：写过渡、强调点、可能追问的补充证据。

步骤 3：构建与渲染
- 运行：
  `python3 /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work`
- 若脚本需要一步完成，则直接运行：
  `python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`
- 生成/更新 `presentation.pptx`、`presentation.pdf`、`plan.json`、`deck_model.json`、`content_map.json`。
- 检查模板继承、页数、溢出、字体、备注覆盖、数字白名单、图表引用一致。

步骤 4：自检与收尾
- 运行：
  `python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work`
- 对照 `references/checklist.md` 逐项复核。
- 更新 `result.json`：`status` 据实取 `ok|partial|input_error`，写入 `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`verifications`。
- 最终 `result.json` 必须是合法 JSON，退出码 0。

## 3. 主线与页结构规则（实际效果 40 分核心）

主线按“论文贡献”组织，不按原文段落顺序：
`Problem → Contribution/Question → Approach → Method → Evidence(每关键 figure/table 一页) → Discussion → Limitation → Conclusion`
页数不足时保留：问题页、贡献页、方法页、核心证据页、结论页；页数富余再扩展。

每页规则：
- 一页一主张；标题是页级结论，不是 “Results (cont.)”。
- bullets ≤5 条；优先短语；不得出现新数字、新单位、新方法名、新结论。
- 每条证据必须含 `type`（figure/table/section/data/equation）、`id`（如 Fig. 3 / Table 2 / Sec. 4.2 / PDF p. 7 行 12）、`locator`、`quote`（逐字）、`matched`。
- 页面文字中的每个关键数字/百分比/单位/名称必须能在原文 quote 中找到。
- 页面提到 Figure N / Table N 时，必须存在；否则删除引用或标记 `pending_human`。

讲解备注规则：
- 与 bullets 不重复；写“为什么这一页在这里、强调什么、被追问时用哪个证据”。
- 备注中也使用来源编号 `[S#]`，便于复核。

## 4. 模板、版式与渲染规则

- 优先使用目标模板的 master/layout/placeholder；保留主题字体、配色、页脚。
- 占位符不足时才使用绝对文本框，并在 `degradations[]` 记录。
- 长标题换行分级；多图并列时使用模板既有布局或简单表格栅格，不硬塞导致溢出。
- 字号不得因自动缩小到不可读；溢出时先删冗余 bullet，而不是无限 shrink。
- 导出 PDF 为渲染证据；无渲染器时保留 `.pptx` 并设 `export_artifact.pdf.valid=false`。
- 源文件必须可编辑，PDF/PNG 用于复核，不能只提交 PDF。

## 5. result.json 双回显与字段

`result.json` 必须有两个位置回显契约：
1. 顶层直接放所有原 `output_contract` 字段和 `case_id`。
2. `output_contract` 对象内再放同样字段。
两者不得冲突；顶层供 harness 快速读取，nested 供复核。

标准字段：
- `status`：`ok | partial | input_error`
- `editable_source`：path、format、slides、bytes、sha256、engine、notes_slides、template_inheritance
- `export_artifact`：pdf path/pages/engine/valid、png dir/count（如有）
- `content_map`：unit=slide、slides[]、coverage{slides,with_evidence,evidence_items,quotes_matched}
- `compliance_checks`：slide_count、template_inheritance、overflow、notes_coverage、notes_overlap、figure_refs、number_whitelist、evidence_coverage、mode、fonts、files、pass、failures[]
- `sources`：实际读取的文件、解析引擎、版本、sha256
- `uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes{}`、`runtime{}`、`verifications[]`

`verifications[]` 逐页/逐关键论断记录：
- claim_id 或 slide n；
- status：`verified | pending_human | conflict`；
- quote 匹配结果与检查依据。

## 6. 异常与降级（可靠体验 10 分）

| 情况 | 检测 | 处理 | 记录 |
|---|---|---|---|
| case.json 缺失/损坏 | 文件不存在或 JSON 解析失败 | 搜索 `case*.json`；仍无则 `case_id=null`，默认契约 | `errors[]`，`status=input_error` |
| 论文缺失 | 无 >1.5KB pdf/docx/md/txt | 不生成 PPT | `exceptions[]` |
| PDF 加密/扫描/无文本层 | 提取字符 <200 | 不生成 PPT，不编造 | `pending_human[]`，`status=partial` |
| 图表标题缺失 | 无 Fig./Table 标题 | 证据降级为页/节定位 | `degradations[]`，`pending_human[]` |
| 模板缺失 | 无 .pptx | 内置 master/layout/theme | `degradations[]` |
| 占位符不足 | 模板扫描无足够 body placeholder | 绝对文本框 | `degradations[]` |
| 无渲染器 | soffice 不可用 | 交付 .pptx，pdf.valid=false | `degradations[]` |
| 页数超限/不足 | slide_count check 失败 | 裁剪或扩展角色页；仍失败保留现有并记录 | `compliance_checks.failures[]` |
| 预算耗尽 | 请求/时间接近上限 | 保留 best-effort，确保 JSON 合法 | `errors[]`/`runtime` |

任何异常都必须 exit 0，产出合法 `result.json`。

## 7. 预算使用（64 次模型请求 / 900 秒）

确定性兜底的意义：即使 Agent 不做复杂推理，`run` 也能产出完整 `pptx/pdf/result`；模型请求仅用于增量核验和改写。优先顺序：

1. 初始化 + init 台账：1–3 次
2. 阅读原文关键段与图表：5–10 次
3. 写 `draft.json`（页级 claim/evidence/notes）：10–18 次
4. build/render/selfcheck：2–5 次
5. 补齐与回填：2–5 次

接近上限立即收尾，保证 `status` 诚实、JSON 合法。

## 8. 评分对齐与自检

- 实际效果：`content_map` 每页 role/claim/evidence 显示主线；数字与图表零 mismatch；提供 source、editable、PDF。
- 使用增益：`compliance_checks.pass`、`runtime` 实际耗时、`changes` 记录相对兜底/基线的改进；不得自造未提供的白板/评分。
- 创新增益：体现页级证据定位、模板继承、备注与页面分离。
- 可靠体验：SKILL.md 命令明确、异常表完整、exit 0。
- 生态贡献：`references/output-schema.md`、`references/page-outline.md`、`references/checklist.md` 提供可复用资源。

提交前运行自检：
`python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --output /app/output --work /app/work`

按 `references/checklist.md` 逐项确认：
- `result.json` 可解析，双回显字段齐全；
- `.pptx` 非空、可编辑；PDF 为真实渲染或如实降级；
- 每页 claim 有来源；quote matched；无图表引用错位；备注不重复；
- 状态、不确定性、降级、错误真实；退出码 0。