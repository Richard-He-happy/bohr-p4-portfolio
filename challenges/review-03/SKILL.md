---
name: methods-stats-review
description: 让 Harness Agent 对科研稿件完成方法学与统计审查，产出带原文定位、逐字引用、缺陷类型、严重度、依据和修改建议的审查单；覆盖研究设计、变量定义、统计方法、样本量、结果报告及六类审查面。脚本产出基线与证据定位，Agent 必须亲自读材料、复核并撰写最终成品。
version: 2.0.0
---

# 研究方法与统计审查（methods-stats-review）

## 0 完整性优先：脚本只是工具，最终成品由你亲自完成（最高优先级）

> 本条高于之后所有自动化建议。平台评审会检查交付物是否完整、是否真实推导。你（Harness Agent）必须：
>
> 1. 先调用本 Skill 自带脚本生成完整基线，不得跳过。
> 2. 基线产物不得直接当作最终答案；你必须亲自读取 /input 原始材料和 /app/output/extracted/*.md，逐条核对并强化审查意见。
> 3. 保留所有基线字段和文件，不得删除、清空或遗漏；如需修改，在原基础上增量修订，并在 `result.json` 的 `changes[]` 和 `summary` 中记录 `agent_reviewed`。
> 4. 若脚本失败或产出不完整，你要手写合法 `result.json` 到 `/app/output`，并列出缺失项与限制。
> 5. 最终提交前，按 §9 自检清单逐项核对，确保 `/app/output` 下文件齐全且 `result.json` 含有 `case_id` 与 `output_contract` 全部字段。

## 1 用途与适用边界

输入一篇稿件（PDF/DOCX/MD/TXT/JSON 及伴随材料），输出可交给作者逐条回复的审查单：每条问题带 `locator`（章节/页/段）、逐字 `quote`、缺陷类型、严重度、依据、修改建议。覆盖六类审查面（事实核验/引用支持/方法设计/统计报告/论证链/学术规范）× 五个检查面（研究设计/变量定义/统计方法/样本量/结果报告）。

不适用：文献检索与综述、全文翻译、语言润色、代写审稿结论、投稿决策；扫描件与图片无 OCR 时不猜测内容。

## 2 输入、输出与运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json` + `/input/task.md` + `/input/**` 实际材料（PDF/DOCX/CSV/图片等） |
| 工作目录 | `/app/work`（临时文件） |
| 最终产物 | `/app/output/`，至少包括 `result.json`、`review_report.md`、`