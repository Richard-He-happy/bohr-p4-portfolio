---
name: multistep-data-analysis
description: Turn a raw scientific table (CSV/TSV/XLSX/JSON/SQLite + data dictionary + question list) into a reproducible analysis package — cleaning trace, descriptive and inferential statistics computed with real numbers, data-backed figures, and a report whose numbers are machine-checked against the result tables. Use for multi-step data analysis cases that require import, field alignment, cleaning, statistics, visualization and report generation in one run.
version: 1.1.0
license: MIT
---

# Multistep Data Analysis Skill

本 Skill 用于把科研原始数据（CSV/TSV/XLSX/JSON/SQLite 等）与任务说明、数据字典、问题清单，在同一个环境里真实推进为可复核的完整分析包：导入对齐、清洗、描述与推断统计、图表、报告、结果证据和不确定性说明全部落盘到 `/app/output`。脚本只是工具，最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作；禁止把脚本骨架、模板或中间输出直接当成品。

## 0. 最高优先级：完整性优先与真实推导

1. 先跑基线，再增强。进入任务后先运行本 Skill 自带脚本/流程，产出全套基线交付物，覆盖所有 `output_contract` 字段、题面要求文件、`result.json` 全部键。
2. 保留全部基线产物。后续校验与改写只能在基线上增强；不得删除、清空或遗漏任何基线与契约字段。若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。
3. 完整性自检。提交前逐项核对：`output_contract` 字段清单 × 磁盘文件 × `result.json` 键三者一一对应；缺任何一项先补齐再收尾；partial 状态必须列出缺失项。
4. 可核验增强。在基线产物之上，Agent 必须亲自核验关键论断、数字、统计口径、引用与源数据的一致性，把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`），作为“genuinely-derived”的证据。
5. 不得依据文件名或领域标签猜测、补造材料内容。所有结论必须有真实解析后的材料内容或计算结果支撑。

## 1. 输入与契约盘点

输入：
- `/input/case.json`
- `/input/task.md`
- 题面规定的材料文件：PDF、DOCX、CSV、XLSX、JSON、SQLite、图片等，位于 `/input` 下或 `/input` 子目录。
- 可能存在的 `output_contract` 定义在 `case.json` 中。
- 工作目录 `/app/work`，最终产物目录 `/app/output`。

动作：
1. 读取 `/input/task.md`，记录任务目标、评分要点、材料清单、输出要求、Runtime contract。
2. 读取 `/input/case.json`，记录 `case_id`、所有 `output_contract` 字段、输入材料路径或指向。
3. 列出 `/input` 目录树，确认实际存在的文件；不假设文件一定存在。
4. 若 `output_contract` 缺失，按 Runtime contract 推断最小合法字段集合：`case_id`、`status`、`results`、`sources`、`uncertainty`、`change_records`，并额外记录 `limitations` 与 `output_contract_missing: true`。
5. 确定必须生成的产物类型；可编辑 Office/幻灯片/图形产物必须额外生成真实渲染的 PDF/PNG 预览。

输出：
- 一份内部工作清单（可写入 `/app/work/plan.md`）：任务目标、材料路径、契约字段清单、必须产出文件、优先级排序（按 rubric 权重）。

失败分支：
- 若 `/input/case.json` 不存在或为空：创建最小合法 `result.json`，`status: failed`，`error: case.json missing or empty`，`limitations` 写明，退出码 0。
- 若 `task.md` 不存在：同样写最小合法 `result.json`，标注缺失输入，退出码 0。
- 若 `output_contract` 缺失或无法解析：使用推断的最小字段集合，并在 `uncertainty` 中说明。

## 2. 真实解析材料内容

输入：
- `/input` 下的所有材料路径。
- 步骤 1 的工作清单。

动作：
1. 根据扩展名选择解析工具：
   - CSV/TSV：优先 `pandas.read_csv`，尝试 `utf-8`、`latin-1`、`gbk` 等编码；如失败用 `python -c` 检测编码或输出错误。
   - XLSX/XLS：用 `openpyxl` 或 `pandas.read_excel`；如失败记录错误。
   - JSON：用 `json.load`；如嵌套，打印结构摘要。
   - SQLite：用 `sqlite3` 连接，列出表，查看 schema，读取前若干行。
   - PDF：必须使用平台预装的 `pdf-text-tool` 或其他可用 PDF 文本提取工具提取真实文本；不要使用文件名推断。
   - DOCX：使用 `python-docx` 或等价工具提取文本、表格、段落；如失败记录错误。
   - 图片：若需要 OCR 且平台有工具可用，则真实调用；否则标记无法解析并写 `pending_human`。
2. 每个材料解析后，打印/记录：前几行或摘要、字段名、行数、列数、缺失值概览、数据类型；对于 PDF/DOCX，摘录与任务相关的段落和表格。
3. 将解析出的内容摘要写入 `/app/work/parsed_summary.md`，包括每个文件的来源路径、解析状态（成功/部分成功/失败）、关键字段、异常编码、无法解析部分。
4. 不要根据文件名或领域标签补造内容；若材料无法解析，记录失败原因，不猜测内容。

输出：
- `/app/work/parsed_summary.md`：真实解析结果摘要，作为后续分析唯一事实依据。
- 工作记忆中的材料内容关键部分（可多次回看，避免重复解析）。

失败分支：
- 单个文件解析失败：尝试 1 次备用方法；仍失败则在摘要中标记 `parse_failed`，记录错误，继续其他文件；最终在 `result.json` 标注该文件不可用、`limitations` 描述影响。
- 所有材料均不可解析：产出最小合法 `result.json`，`status: failed` 或 `pending_human`，`results` 为空或仅描述可得的失败信息，`sources` 指向材料路径，`uncertainty` 说明完全无法验证，退出码 0。

## 3. 构建/核对证据并运行脚本基线

输入：
- `/app/work/parsed_summary.md`
- `/app/work/plan.md`
- Skill 自带脚本：`/skills/weekly-skill/scripts/analyze.py`、`/skills/weekly-skill/scripts/statslib.py`。

动作：
1. 查看脚本实际接口，不假设参数：
   - `python3 /skills/weekly-skill/scripts/analyze.py --help`
   - 若 `statslib.py` 是函数库：`python3 -c "import sys; sys.path.insert(0, '/skills/weekly-skill'); import scripts.statslib as s; print([n for n in dir(s) if not n.startswith('_')])"`
2. 根据脚本帮助和实际需求，构造输入参数。通常传入：解析后的数据文件路径、任务要求文件路径、输出目录 `/app/work` 或 `/app/output`。不要使用未经验证的参数，优先查看脚本自身说明。
3. 运行脚本，产出一套基线交付物到 `/app/output`。如果脚本默认输出到其他目录，复制/移动到 `/app/output` 并保持结构清晰。
4. 检查基线产物是否覆盖 `output_contract` 全部字段：清洗表、统计结果、图表、报告、代码、日志、规则表、版本记录等。
5. 用真实材料内容核对基线产出的关键数字：行数变化、缺失值规则、异常值判定、统计检验前提、图表聚合层次等；比对原始数据值，记录不一致。
6. 若脚本无法直接满足某些字段，Agent 必须亲自用 `python3` 或可用工具补全，不能留空字段。
7. 把基线运行命令、输出文件清单、关键数字核对结果写入 `/app/work/baseline_check.md`。

输出：
- `/app/output` 下的基线交付物。
- `/app/work/baseline_check.md`：运行命令、产物清单、字段覆盖检查、发现的不一致或缺失。
- `result.json` 初稿（可先落在 `/app/work/partial_result.json`，包含当前可信字段）。

失败分支：
- 脚本调用失败：记录错误，检查帮助，手动执行最小分析链；若仍失败，使用 `python3` 直接处理材料，保证至少产出合法 `result.json`。
- 脚本输出不完整：Agent 补做缺失部分，并在 `change_records` 中记录 `baseline incomplete, agent supplemented`。
- 材料内容与基线结论冲突：以真实材料为准，修正产物，并在 `change_records` 中记录 `conflict corrected by agent`。

## 4. Agent 亲自产出完整成品

输入：
- `/app/output` 基线产物。
- `/app/work/parsed_summary.md` 与 `/app/work/baseline_check.md`。

动作：
1. 亲自审阅原始材料摘要、数据字典、字段语义和约束，确定清洗规则、异常值定义、缺失值处理优先级、重复记录合并规则、统计检验前提与选择依据、图表选型理由。
2. 撰写/修改分析报告，确保正文数字、表格、图形同源，可回算、可更新；报告包含：数据来源、字段映射、清洗前后行数变化、缺失/异常/重复处理规则及影响、描述统计、推断统计及假设检验、图表解释、适用边界和不适用情况。
3. 确保报告中任何数字都能在 `result.json` 的 `results` 表中找到，且结果表来自实际计算或清洗，不是模板占位。
4. 生成/验证图表：用真实计算后数据绘图，确保坐标轴、聚合层级、误差表示与底层数据一致。图保存为 PNG/PDF，并在报告中引用。
5. 生成可编辑 Office/幻灯片/图形产物时，使用工具（如 `libreoffice --headless` 或等价的可用渲染器）生成 PDF/PNG 预览，与可编辑文件一同放在 `/app/output`。
6. 如果报告、图表、统计结果由 Agent 直接生成而未经过脚本，必须在 `change_records` 中标记 `agent_generated`，并保存相关代码或命令到 `/app/output/code/`，以便复现。
7. 将最终产物写入 `/app/output`，保持文件路径清晰，避免与基线冲突时覆盖需审查：保留旧版本或标注 `v1`。

输出：
- `/app/output` 下完整成品：清洗表、统计结果、图、代码、报告、可编辑产物及预览、`result.json`。
- `/app/work/final_review.md`：核验记录、修正记录、与 baseline 差异说明。

失败分支：
- 某个图表或报告小节无法完成：在 `limitations` 中写明，并尽力用替代形式（如 Markdown 表）提供关键信息；不得编造数字。
- 可编辑产物渲染失败：保留可编辑文件，在 `result.json` 中标注 `preview_pending: rendered preview failed`，并尝试生成静态图片替代。
- 时间/请求预算接近上限：先落盘已有完整 partial，再试图增强。

## 5. 自检 rubric 与回填 result.json

输入：
- `/app/output` 当前交付物。
- `/app/work/parsed_summary.md`、`/app/work/baseline_check.md`、`/app/work/final_review.md`。

动作：
1. 根据步骤 1 的 `output_contract` 字段清单，逐项核对 `/app/output` 是否有对应文件或结果。
2. 检查 `result.json` 是否包含：
   - `case_id`（来自 `/input/case.json`）
   - 所有 `output_contract` 字段（键名不改）
   - 真实 `status`（`completed` / `partial` / `failed` / `pending_human`）
   - `sources`：列出实际使用的材料路径、解析状态、证据来源位置（文件：行号/表名等）
   - `uncertainty`：真实不确定性、无法判断、材料不足、解析失败等
   - `change_records`：按时间顺序记录重要修正、Agent 核验结论、与基线差异
   - `limitations`：材料限制、方法局限、环境限制
   - 如有 `reviewed_by_agent` 字段，必须真实填写核验状态
3. 确认 `status` 为 `partial` 时必须列出缺失项和原因；`failed` 时必须说明失败步骤和错误。
4. 确认所有数字和结论有 `sources` 或 `results` 表支撑，不允许出现无来源的断言。
5. 写最终 `result.json` 到 `/app/output/result.json`，同时可保留 `/app/work/result.json` 备份。
6. 确保退出码为 0，不因错误导致运行中止。

输出：
- `/app/output/result.json`（最终）
- `/app/work/final_review.md` 更新为最终审查记录。

失败分支：
- 发现缺失字段：立即补做或写入 `limitations`，不得留空字段。
- 时间不足：优先保证 `result.json` 合法，其他工作可以简化为 honest partial 并记录。

## 6. 预算策略（64 次模型请求 / 900 秒 / 单次响应 16384 tokens）

原则：先完成 rubric 权重最高的交付物，优先落盘 honest partial，再增量改进；避免无意义循环和冗余调用。

推荐分配：
- 步骤 1 输入与契约盘点：3-5 次请求。必须完成，否则后面无法对齐。
- 步骤 2 真实解析材料：8-15 次请求。解析每个材料一次，记录摘要，避免重复完整解析。
- 步骤 3 运行脚本基线：5-10 次请求。查看帮助、运行、检查覆盖。
- 步骤 4 亲自产出完整成品：15-25 次请求。重点写报告、核对数字、修图、渲染预览。
- 步骤 5 自检与回填 result.json：5-10 次请求。逐项核对契约字段和文件存在性。
- 预留 3-6 次请求用于异常重试、重新解析、修正。

可跳过或简化：
- 不要求生成大量备选图表；只用满足题面要求的图。
- 不重复解析已成功解析的材料；使用 `/app/work/parsed_summary.md`。
- 若基线产物已覆盖契约，且核验通过，可减少 Agent 重写，只需补充 `reviewed_by_agent` 核验证据。
- 如果某项自证需要大量额外计算且分值较低（如生态贡献中的示例丰富度），可标记为部分完成。

任何时候如果剩余请求少于 8 次，立即停止新增分析，优先完善 `/app/output/result.json` 并确保退出码 0。

## 7. 隐藏案例鲁棒性与降级策略

目标：任意情况下都产出合法 `result.json`，退出码 0，不静默失败。

- 材料缺失 / 路径不存在：记录缺失路径，尝试查找 `/input` 下相似名称；不依据文件名猜测内容；缺失影响写入 `limitations`，对应结果标记 `pending_human`。
- 材料损坏 / 无法打开：尝试一次备用解析工具或编码；仍失败则记录错误，不生成伪造内容。
- 格式不支持：如果环境有可用转换工具（如 `libreoffice --headless`）可尝试转换；否则标记 `unsupported_format`，保留源文件路径，`pending_human`。
- 空输入 / 空表：生成状态 `partial` 或 `failed`，`results` 说明空数据，`sources` 指向空文件路径，`uncertainty` 注明无法分析。
- `output_contract` 缺失：按步骤 1 推断最小字段集合，并在 `result.json` 中写入 `output_contract_missing: true`、`limitations` 描述。
- 列缺失 / 类型不符：记录上下文（字段名、期望类型、实际类型），在 `change_records`或 `uncertainty` 中说明；不静默填补或删除，除非规则明确。
- 除零 / 统计检验前提不满足：捕获异常，记录错误，改为替代方法（如非参数检验），并在报告中说明选择依据。
- 编码错误：依次尝试 `utf-8-sig`、`latin-1`、`gbk`、`cp1252`；记录最终使用编码。
- 数据库连接失败 / SQLite 损坏：记录错误，尝试只读模式或备份恢复；仍失败则标记无法读取，保留其他可用材料。
- 超时：记录当前完成状态，立即写 `result.json`，`status: partial`，`limitations` 注明超时点。
- 任何内部异常：用 try/except 捕获，记录异常类型和信息，继续完成 result.json。

总之：永远不要让进程以非零退出码结束；即使彻底失败，也要写 `result.json`，状态诚实，错误清楚，然后退出 0。

## 8. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果-任务完成度 15 | 从原始表推进到报告，导入、清洗、分析、可视化、报告五段完整串联 | `result.json` 中 `results` 包含各阶段产物路径；报告有清洗前后、统计、图；文件清单覆盖五段 |
| 实际效果-结果正确性 15 | 数值、统计口径、图与真实数据一致，处理规则与实际执行一致 | `sources` 指向原始数据行列；`change_records` 记录规则与修正；报告数字能回查到 `results` 表 |
| 实际效果-结果完整性 5 | 题面要求字段、检查点、产物全部覆盖 | `output_contract` 字段清单与磁盘文件、result.json 键一一对应；缺失项列入 `limitations` |
| 实际效果-结果可核验性 5 | 证据链完整可重跑，不只是结论 | 保存清洗/统计代码、日志、版本记录；`results` 表含可复算的原始值、规则、中间结果 |
| 使用增益-质量增益 15 | 相同输入下加载后质量稳定提升 | 基线产物与 Agent 核验/修正记录对比；`change_records` 明确 `agent_reviewed` 和修正原因 |
| 使用增益-效率增益 5 | 减少人工改代码、补字段、重跑次数和端到端耗时 | 记录运行时间、请求次数（平台提供）；在 `result.json` 中说明自动化完成部分 |
| 使用增益-增益可验证性 5 | 用公平对照证明质量或效率改善 | 不做虚构对照；如有基线用 baseline vs agent_reviewed 对比；无对照则诚实说明 |
| 创新增益-新增能力 5 | 形成基础 Agent 或现有方案不具备的能力 | 在 `result.json` 或报告中描述本 Skill 的编排能力、失败回退、合同校验等新增能力；不夸大 |
| 创新增益-方法改进 5 | 步骤编排、检查点、失败回退等方法实质改进 | `change_records` 和 `plan.md` 中记录分步检查点；隐藏案例鲁棒性策略包含降级路径 |
| 创新增益-创新证据 5 | 证明创新点相对已有方案的边界和价值 | 结合本次运行实际结果，客观描述哪些步骤被自动化、哪些仍需人工，不做空洞自述 |
| 可靠体验-调用与易用性 3 | 能被正确触发和调用，按说明能跑完一条完整分析链 | SKILL.md 说明清晰，脚本帮助接口被正确使用；运行日志记录成功调用 |
| 可靠体验-运行稳定性 4 | 不同数据形态、规模和重复运行持续产出可用结果 | 隐藏案例鲁棒性处理；异常分支记录；重复运行尽量幂等或版本明确 |
| 可靠体验-异常处理 3 | 空表、列缺失、类型不符、除零、编码错误、连接失败等识别与处置 | `result.json` 中 `uncertainty`、`change_records`、`limitations` 记录具体异常和处置 |
| 生态贡献-文档完整性 3 | 使用说明、字段字典、环境依赖、示例、边界和维护信息齐全 | SKILL.md 包含以上内容；脚本帮助和注释；`result.json` 可读 |
| 生态贡献-资源可复用性 4 | 脚本、配置、模板等能被他人直接部署和复跑 | 脚本路径有效；参数可通过 `--help` 获取；输出目录约定明确；不依赖个人文件 |
| 生态贡献-分享推广价值 3 | 沉淀可迁移的分析流程、案例与真实应用价值 | SKILL.md 的执行流程通用；报告模板/清洗规则可迁移；诚实记录适用边界 |

## 9. 提交前自检清单

逐项检查，全部通过才可结束：

- [ ] `/app/output/result.json` 存在且为合法 JSON。
- [ ] `result.json` 包含 `case_id` 且与 `/input/case.json` 一致。
- [ ] `result.json` 包含原 `output_contract` 的全部字段，键名未改；若缺失，已写入 `limitations` 和 `output_contract_missing: true`。
- [ ] `result.json` 包含真实 `status`、`sources`、`uncertainty`、`change_records`；无编造数据或引用。
- [ ] 所有材料均真实解析；解析摘要写入 `/app/work/parsed_summary.md`；未依据文件名猜测内容。
- [ ] 清洗规则、异常处理、缺失值处理、重复记录合并均有明确记录，且与实际执行一致。
- [ ] 统计方法选择依据、检验前提、样本量、多重比较等说明在报告中体现。
- [ ] 图表与底层数据一致，坐标轴、聚合层级、误差表示正确；图文件在 `/app/output`。
- [ ] 可编辑 Office/幻灯片/图形产物有真实渲染的 PDF/PNG 预览。
- [ ] 正文数字、表格、图形同源，可回算；报告数字可在 `results` 表中找到。
- [ ] 基线产物未被删除或清空；若有增强，`change_records` 记录 `baseline_reviewed` 和修正。
- [ ] 缺失、异常、失败查询、无法解释结果明确说明，不静默修改或掩盖。
- [ ] 退出码为 0；最终输出目录包含所有必需文件。
- [ ] 文件引用路径只包含包内真实存在的文件：`SKILL.md`、`scripts/analyze.py`、`scripts/statslib.py`；运行时输入/输出路径合法。

## 10. 脚本调用与目录约定

- Skill 安装路径：`/skills/weekly-skill`。
- 可用脚本文件：
  - `/skills/weekly-skill/scripts/analyze.py`
  - `/skills/weekly-skill/scripts/statslib.py`
- 调用前先查看帮助，不假设参数：
  - `python3 /skills/weekly-skill/scripts/analyze.py --help`
  - 查看 `statslib.py` 接口：`python3 -c "import sys; sys.path.insert(0, '/skills/weekly-skill'); import scripts.statslib as s; print([n for n in dir(s) if not n.startswith('_')])"`
- 工作目录：`/app/work`；所有中间文件、解析摘要、审查记录写这里。
- 最终结果目录：`/app/output`；所有交付物写这里，包括 `result.json`、数据表、图、代码、报告、预览。
- 输入目录：`/input`；读取 `case.json`、`task.md` 和材料文件，绝不修改输入。
- 输出契约字段以 `/input/case.json` 中的 `output_contract` 为准；字段名保持原样，不得重命名。
- 任何脚本运行失败，Agent 必须用 `python3` 直接完成的最小必要分析，保证 `result.json` 合法。
- 诚实性：`status`、`sources`、`uncertainty`、`change_records`、`limitations` 必须真实；不确定或材料不足显式标注 `pending_human` 或 `limitations`，不得编造数据、引用、分数或对照结果。

## 11. 运行流程总结（速览）

1. 读 `/input/task.md`、`/input/case.json`，记录 `case_id`、`output_contract`、材料路径。
2. 真实解析全部材料，写 `/app/work/parsed_summary.md`。
3. 查看脚本 `analyze.py --help` 和 `statslib` 接口，跑基线，产出到 `/app/output`。
4. 核对基线数字与源材料，记录不一致；Agent 修正补全。
5. Agent 亲自写报告、修图、生成预览；所有数字同源。
6. 回填 `result.json`，覆盖全部契约字段，自检，退出码 0。
7. 任何异常写清楚，保留 partial，绝不静默失败或编造。