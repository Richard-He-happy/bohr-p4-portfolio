---
name: paper-structure-logic-review
version: 1.1.0
description: 对一篇完整稿件做结构诊断并交付作者可直接执行的结构修改方案；覆盖研究问题对齐、章节结构、论证链、段落关系、重复内容、结论边界六类问题，保留原文定位与来源映射。由 Harness Agent 亲自阅读真实材料、推导、撰写/制作，脚本仅作基线生成与独立复核。
license: MIT
tags: [academic-writing, structural-review, argument-mapping, editing-plan]
---

# 论文结构与逻辑优化（结构诊断 Skill，Agent 亲自推导版）

## 1. 用途、边界与最高优先级

本 Skill 对一篇完整稿件做结构级诊断，交付作者可直接执行的修改方案：每条发现定位到具体章节/段落/句子，说明属于哪类结构问题，并给出可执行动作（移到哪、与哪段合并、从哪拆分、哪句论断要收窄、重复从哪删、缺哪段插入）。

**最高优先级：脚本只是工具，最终交付物由你（Harness Agent）亲自阅读 `/input` 中真实材料后推导、撰写/制作。** 禁止把 `scripts/main.py` 的基线输出、`references/messages.json` 的措辞模板或 `references/taxonomy.md` 的规则描述直接当成品。所有交付物必须是本 case 的专属结果；每条 finding/action 必须来自原文定位，不得套用模板或编造缺陷、数据、引用、分数。

**做**：结构级诊断、论证链映射、跨章节冗余检测、结论与数据范围比对、动作清单、来源与修改记录。
**不做**：整篇改写（题面：full unsolicited rewrites are not required）、语言润色、补写科学内容、生成文献或数据、判断科学结论本身是否正确。

## 2. 触发条件

用户要求「结构诊断 / 逻辑优化 / 论文架构 / 章节顺序 / 论证链 / 重复内容 / 结论收窄 / 审稿意见里的结构问题」，或给出完整稿件要求"指出问题在哪一章哪一段、怎么改"时触发。若用户要的是另一篇改写稿，或只需语言润色，则不应触发。

## 3. 运行契约与目录约定

- 输入目录 `/input`：`case.json` + `task.md` + 材料（md/txt/docx/pdf/html/csv/图片等）。
- 工作目录 `/app/work`：解析文本、基线候选、Agent 审校笔记等中间产物可写这里。
- 最终产物目录 `/app/output`：所有正式交付物与 `result.json` 必须落在这里。
- 必须真实解析材料内容；不得依据文件名或领域标签猜测/补造内容。
- 可编辑 Office/幻灯片/图形产物若出现，必须额外给出真实渲染的 PDF/PNG 预览。本题固定要求以可编辑 JSON/Markdown 为主，故通常不需要额外 PDF/PNG；若案例额外要求，则用实际可用工具渲染，不得伪造。

保留的脚本命令：

`python3 -B scripts/main.py --input /input --out /app/work/baseline`

优先输出基线到 `/app/work/baseline`，避免覆盖最终成品。若脚本版本只接受 `/app/output`，则先运行至 `/app/output`，然后立即复制到 `/app/work/baseline` 保留基线，最终 Agent 亲自重写 `/app/output`。

`python3 -B scripts/verify.py --out /app/output --input /input`

用于最终独立复核；必须得到 `pass=true` 或记录 pass=false 的具体原因并修正。

退出码恒 0；任何异常都被捕获；先写 partial `result.json`，最后无条件 finalize 覆盖。脚本只围绕包内资源运行，不依赖 CWD；不联网。

## 4. 输入发现与真实解析（不假设键名、不依据文件名猜测）

1. 读取 `/input/case.json`。若缺失，递归查找 `case*.json`。原样保留 `case_id` 与 `output_contract`。若 `output_contract` 存在，必须把其中每个字段原样展开到 `result.json` 顶层，键名不改。
2. 语义读取以下字段（若存在）：`task_instruction`、`organizer_workorder`、`organizer_edit_workorder`、`organizer_supplied_scope`、`material_version`、`source`。`workorder` 逐项执行并在 `workorder_receipts` 回报：`done` / `not_applicable` / `declined_by_scope` / `partial`。
3. 递归扫描 `/input/**`，按扩展名识别；`task.md`/`guide.md`/`instruction*.md` 记为指令，不作为稿件。
4. **真实解析材料**：
   - PDF：优先调用环境提供的 `pdf-text-tool`；若无，则使用 `pdftotext -layout` 或 Python `pypdf`/`pdfplumber` 提取真实文本。扫描件无文本层时，不造文字，记入 `pending_human` 与 `errors.pdf_ocr_required`。
   - DOCX：用 `python-docx` 或解压 `document.xml` 抽取段落；不得按文件名臆测。
   - CSV/TSV：用标准库 `csv` 读取真实行。
   - 图片：如属于需诊断的图表/公式材料，优先读取可见信息；无法识别文字时标 `pending_human`，不得编造图题/数据。
   - Markdown/TXT：直接读取。
5. **稿件判定**：所有可解析文本中最长者为主稿件；多个候选或无法唯一确定时写 `pending_human`，不得随意认定。
6. 材料未给出的对象（缺提纲、缺参考文献、缺图表、缺附录）明确列缺口，不构造内容。

## 5. 输出契约

最终必须在 `/app/output` 下至少提供以下文件