---
name: traceable-literature-retrieval
description: 离线可追溯学术文献检索与筛选 Skill。对 /input 中的科研案例与真实材料（Crossref、Europe PMC、publisher dumps、JSONL/JSON、引用图、seed 列表、PDF/DOCX/CSV/图片等）进行多轮查询规划、同义词/缩写扩展、多库合并去重、IDF 加权排序、筛选与引文追踪，并回填完整 output_contract 到 result.json。脚本只提供基线工具，最终候选集、证据、缺口和自检必须由 Harness Agent 亲自阅读材料、核验后撰写。禁止把脚本模板当成品；空结果、缺字段、冲突、失败均诚实写入 uncertainties/missing/errors，不编造。
version: 1.1.0
---

# 可追溯学术文献检索 Skill（search-01）

## 0. 最高优先级：完整性与真实推导

- 脚本只是工具：scripts/main.py 与 scripts/engine.py 负责输入扫描、记录归一化、去重、排序、筛选、引文追踪与产出基线 result.json、candidates.csv、candidates.json、query_log.json。最终交付物必须由 Harness Agent 亲自阅读 /input 材料、逐条核实关键题录、依据证据撰写 relevance_reason、coverage 与 uncertainty。
- 禁止把脚本生成的空模板、未填充 output_contract 的半成品、未经验证的源记录直接作为最终交付。
- 先跑基线，再增强：进入任务后立即运行 scripts/main.py 产出全套基线交付物；之后只能在其上增强，不得删除、清空或遗漏基线已有字段与文件。若需修正，保留原值并新增 reviewed_by_agent / conflicts / pending_human 说明。
- 任何输出必须真实可追溯：每条候选来自 /input 实际文件，带 locator 与 evidence_snippet；不确定、缺失、冲突必须显式标注，不编造标题、作者、DOI、年份、引用、分数或“最新进展”。

## 1. 运行契约与预算

| 项 | 要求 |
|-|-|
| 输入目录 | /input 只读；包含 case.json、task.md 及材料（JSON/JSONL/CSV/TSV/PDF/DOCX/图片/引用边/seed 列表等）。按内容探测，不依赖固定文件名。 |
| 工作目录 | /app/work；可写中间提取、临时文件 |
| 输出目录 | /app/output；必须包含 result.json，以及 candidates.csv、candidates.json、query_log.json；若有 Office/幻灯片/图形可编辑产物，必须同时提供真实渲染的 PDF/PNG 预览 |
| 输出契约 | result.json 必须包含原 output_contract 的全部字段（键名不改）与 case_id；不得漏字段 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）；优先高分值交付物并尽早落盘 honest partial |
| 网络 | 严格离线；不发起任何联网检索；不得宣称获取到未在 /input 中出现的外部服务响应 |
| 退出码 | 恒为 0；任何异常都写 errors/degradations，仍生成合法 result.json |
| 资源限制 | Skill 最多 50 个 UTF-8 文本文件、单文件≤500KB、总≤2MB、无 symlink |

## 2. 预算策略（64 次