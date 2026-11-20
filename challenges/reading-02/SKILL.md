---
name: reading-02-scientific-figure-parser
description: 解析科研图表与表格为可复核结构化数据；结合确定性脚本与 Agent 视觉判读，提取轴类型/刻度/单位、图例系列映射、数字化曲线、字面表格及证据锚定结论。适用任务：读图、提取数据点、解析统计图表、多子图关联、输出 CSV/JSON 并保留证据定位。
version: 1.1.0
license: MIT
---

# 科研图表解析（reading-02）

**本 Skill 将一张或一组科研图表及原表读成可复核的结构化结果**：坐标轴类型/刻度/单位、图例与系列对应、数据点与趋势、误差线/显著性/比例尺/子图编号，以及每条结论回到原图位置的证据。

> 最高原则：脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本骨架、模板或基线产物直接当成品；必须基于真实解析的材料内容，由 Agent 亲自核实、补充、改写并证明每一条关键结论。

## 0. 完整性优先（v6 混合策略，最高优先级）

1. **先跑基线**：进入任务后先运行本 Skill 自带主脚本/流程，产出全套基线交付物（所有 output_contract 字段、所有题面要求文件、所有 result.json 字段）。
2. **保留全部基线产物**：后续校验与改写只能在基线上增强；不得删除、清空或遗漏任何基线与契约字段。若不确定，保留原产物并在 result.json 中标注 `reviewed_by_agent`。
3. **完整性自检**：提交前逐项核对「output_contract 字段 list × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐再收尾；partial 状态必须列出缺失项。
4. **可核验增强**：在基线之上，由 Agent 亲自核验关键论断/数字/引用的来源一致性，把核验结果写入 `verification`/`pending_human`/`conflicts`。

## 1. 何时使用

满足任一触发：
- 任务要求读取图中的坐标轴、刻度、单位、图例、数据点、误差线、比例尺或子图；
- 要求把曲线/柱状/散点/光谱/显微图转成 CSV 或数值表；
- 要求“回答并给出依据”，且依据必须在图或表中；
- 输入含 `artifacts/*.png|jpg|pdf`、`material.json`、论文 PDF、CSV 或数据表。

不适用：纯写作/翻译；需要在无图像情况下推断未给数据（应拒绝并列出缺口）。

## 2. 运行契约（必须逐条满足）

| 项 | 要求 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下材料（图片/PDF/CSV/XLSX/DOCX/JSON） |
| 工作目录 | `/app/work`（中间文件写入此处，不污染输出） |
| 输出目录 | `/app/output`（最终产物必须落在这里） |
| 必需输出 | `result.json`（至少存在且合法） |
| 契约回填 | `result.json` 原样包含输入 `output_contract` 的全部字段（键名不改、不丢未知键，缺值写 `null`/`[]`） |
| 附加产物 | `figure_structure.json`、`digitized_series.csv`、`tables.json`、`tables/<id>.csv` 等，按实际任务要求 |
| 可编辑 Office