---
name: experiment-parameter-optimizer
description: 将研究目标、设备量程、试剂规格、预算/机时与已有数据转化为可执行的实验参数方案（关键参数、建议值、可行区间、响应指标口径、序贯搜索轨迹、成本核算、验证与停止判据）。适用于有界参数优化、候选方案比较与择优、可行性与约束冲突检查、筛选设计。输入为 /input/case.json、/input/task.md 与 PDF/CSV/XLSX/DOCX 材料；输出到 /app/output，包含 result.json、protocol.md、parameter_plan.csv、risk_table.csv。本 Skill 强调真实解析材料、约束感知搜索与成本-响应联合权衡，不依据文件名或领域标签猜测。
version: 1.1.0
---

# 实验参数优化 / Experiment Parameter Optimizer

## 0. Agent 总则：真实推导、脚本只是工具

本 Skill 的脚本、模板和参考文件是**工具与基线生成器**，不是最终交付物。负责本次实际案例的 Harness Agent 必须亲自读取 `/input` 下的任务与材料，使用平台提供的 PDF 文本解析工具（如 `pdftotext` 或 `pypdf`）真实提取全文；对 DOCX/XLSX 使用 `zipfile` + XML 正则取文本；对 CSV/JSON 直接读取；不得依据文件名、领域标签、记忆或示例猜测/补造任何数据。

运行 `python3 -B scripts/main.py` 后得到的是**基线交付物**。Agent 必须在此基础上逐项核验来源、数字、引用、可行域、成本公式与输出契约字段，修正明显解析或计算错误，补充“由 Agent 阅读材料后独立推导出的”方案优化、冲突判断和专家确认项。禁止把脚本骨架、模板输出或示例内容直接当作成品提交。

任何未经 Agent 亲自核验、或材料不足无法判断的内容，必须显式标记 `pending_human` / `uncertainty` / `limitations`，不得改写为已证实事实。不得编造数据、引用、分数或基准结果。

完整性优先：先运行基线脚本产出全套交付物；后续 Agent 的校验与改写只能在此基线上增强；不得删除、清空或遗漏任何基线与契约字段；若对某字段不确定，保留原产物并在 `changes` 或 `reviewed_by_agent` 中注明。

最终 `result.json` 必须包含原 `output_contract` 全部字段（键名不改、未知键保留、缺值按声明类型给 `null`/`[]`/`{}`）与 `case_id`，并真实记录 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`contract_backfill`。

## 1. 用途与边界

把「研究目标 + 设备量程 + 材料限制 + 预算/机时 + 已有数据」转成一份可用于开机的参数方案：关键参数、建议值、可行区间、响应指标口径、搜索策略、成本与耗时、风险与替代、判读与停止判据；每个数值给出来源定位。

适用：有界参数优化；多版候选方案比较与择优；可行性与约束冲突检查；无历史数据时的筛选（screening）设计；实验成本与时间预算权衡；设备与材料约束感知的参数搜索。

不适用：需要发明新合成路线/分子设计的任务；需要真实仪器控制或远程下单的任务；必须先经伦理审批的人体/动物实验（这类只输出方案骨架与确认项，`status=partial` 或 `insufficient_evidence`）。

输入：`/input/case.json`（首选结构化任务）、`/input/task.md`（题面与运行时契约），以及 `/input/` 下任意 PDF/CSV/XLSX/DOCX/JSON/PNG 材料。

输出：全部写 `/app/output/`，必须包含 `result.json`、`protocol.md`、`parameter_plan.csv`、`risk_table.csv`。若题面要求可编辑 Office/幻灯片/图形产物，则必须额外生成真实渲染的 PDF/PNG 预览。

边界条件：本 Skill 只提供参数优化建议与依据/风险/确认项，不替代实际实验、真实报价、安全审批或未来响应测量。任何无法验证的设备/材料/价格信息列为 `pending_human`。

## 2. 运行契约

- 输入：`/input/case.json`（首选）、`/input/task.md`，以及 `/input/` 下任意 PDF/CSV/XLSX/DOCX/JSON/PNG 材料。**必须真实解析材料内容**，不得依据文件名或领域标签猜测/补造内容。
- 工作目录：`/app/work`；最终产物落在 `/app/output`。
- 产物：`/app/output/result.json` 必须存在且合法；同时生成 `protocol.md`、`parameter_plan.csv`、`risk_table.csv`。可编辑 Office/幻灯片/图形产物必须额外给出真实渲染的 PDF/PNG 预览。
- 入口命令（在 Skill 安装根目录执行）：

```
python3 -B scripts/main.py   --input /input --output /app/output
python3 -B scripts/verify.py --input /input --output /app/output
```

- 只用 Python 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`）。
- 退出码恒 0；任何异常写入 `errors`/`degradations`/`pending_human`，先落 partial 再 finalize。
- 运行预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行不计模型请求，但占用时间；Agent 应在其推理中完成真实推导，而不是反复调用模型重复相同信息。
- 模型、source/case 版本、运行时、预算和实际 native traces 由平台记录；不得编造基准分数、白板对比数据或 formal test outputs。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则递归找 `*case*.json`，再退化为只读 `/input/task.md` 与材料文件。
2. 递归扫描 `/input/**`，按扩展名 + 魔数分类；PDF 依次尝试 `pdftotext`、`pypdf`、stdlib zlib 流解码；DOCX/XLSX 用 `zipfile` + XML 正则取文本；CSV/JSON 直接读取；图片只登记、不做 OCR，除非平台明确支持 OCR 工具且已安装；无法解析的文件登记到 `errors` 或 `degradations`。
3. 语义键匹配（大小写、中英不敏感，允许嵌套）：`goal|目标`、`equipment|instrument|设备|仪器`、`reagent|material|试剂|材料`、`param|factor|参数|因子`、`domain|levels|范围`、`constraint|limit|threshold|阈值`、`budget|cost|price|预算|费用|报价`、`booking|机时`、`plan|candidate|version|方案|版本`、`existing_results|history|历史`、`output_contract|输出契约`。
4. 材料未给的对象（无价目、无毒理、无仪器精度、无伦理批件）**明确列入 `pending_human` 与 `materials[].gap`**，不构造。不得用一般常识或训练记忆填补具体数值；确需使用通用常识时，必须写明 `source_id=expert_prior`、`quote_verified=false`，并提升 `uncertainty.level`。
5. 解析 `case.json` 时，遇到 `output_contract` 字段要原样保留在 `result.json` 中；未知键不删除，缺失键按声明类型填默认值并在 `contract_backfill` 中记录。

## 4. 输出契约

`result.json` = `output_contract` 全部字段回填（键名不改、未知键保留、缺值 `null`/`[]`/`{}` 按其声明类型）+ `case_id` + `status`(`ok|partial|insufficient_evidence|input_error`) + `sources` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime` + `contract_backfill`（逐字段记录取到 slot 还是 default）+ `reviewed_by_agent`（布尔或对象，记录 Agent 是否对基线产物做了核验与增强）。

主产物：
- `protocol.md`：可照做的实验方案，含假设、变量、对照、步骤、参数、资源、判读标准、依据与风险、异常处置、待确认事项。
- `parameter_plan.csv`：关键参数、建议值、可行区间、单位、绑定约束、依据 ID、核验状态。
- `risk_table.csv`：触发条件—检测方式—处置动作—替代方案—所属风险类别。
- 搜索轨迹、响应模型、成本明细、判读判据在 `result.json` 的 `search`/`response_model`/`cost`/`validation` 中。

若 `output_contract` 缺失或空，则按 task.md 的 Runtime contract，至少生成上述三个主产物与 `result.json`，并在 `contract_backfill` 中注明“使用默认题目契约”。

可编辑 Office/slide/diagram 产物（如题面或案例要求）必须额外提供真实渲染 PDF/PNG 预览；本 Skill 默认主产物为 Markdown/CSV，不涉及此类二进制，但如 Agent 额外生成 Office 文件，必须同时导出 PDF/PNG。

## 5. 核心流程

**脚本基线流程**：建参数登记表 → 设备量程 ∩ 材料限制 ∩ 安全阈值 ∩ 显式域求交得可行域 → 冲突检测 → 候选生成（确定性全因子，候选上限 600 点）→ 序贯细化与停止判据 → 成本-响应联合权衡 → 生成协议/参数表/风险表 → 契约回填与自检。

**Agent 增强流程**：
1. 先运行 `python3 -B scripts/main.py --input /input --output /app/output` 生成全套基线。
2. 读取 `/app/output/result.json` 及各主产物，与 `/input` 材料原文逐条比对。
3. 修正明显解析错误、补充缺失的 schema 字段、将未验证内容标记 `pending_human`。
4. 对关键数字执行来源定位与原文子串验证，验证通过写 `quote_verified=true`；否则写 `false` 并提升不确定性。
5. 写入 `changes` 记录每次修改的内容、原因与时间。
6. 最后运行 `python3 -B scripts/verify.py --input /input --output /app/output` 并修正报告问题。

搜索与停止写在 `search` 的 `rounds` 里：
- 第 1 轮：全因子枚举全部候选点（上限 600），记录候选数、可行候选数、响应指标估算范围。
- 第 2 轮：沿各参数轴 ±半步细化当前最优点邻域，记录新候选数、响应变化、成本变化。
- 后续轮：仅当预期改进 ≥ 1% 域宽且候选预算未耗尽时继续。
- 停止条件：改进 < 1% 域宽；候选预算耗尽；临近时间预算（脚本内置 780 s，Agent 根据 900 s 总量预留 120 s 最后自检与 finalize）。
- 每轮记录候选数、最优点、理由、成本、指标值，保证他人可按同一初始点和确定性规则复算。

响应模型：若历史数据可用，优先使用可解释代理模型（线性/二次/分段），并给出 `R^2`/残差或离散点拟合说明；若无数据，转 screening 设计，`response_model.ok=false`，`uncertainty.level=high`，建议值标为“设计选择，非实验实证”。

成本核算：逐项记录公式、单价、用量、小计；无法获得单价或用量时，不编造，列入 `cost.unknown_cost[]`，`cost_per_run=null`，`status=partial`。

## 6. 任务质量规则（rubric → 交付要求 → 自证方式）

本表覆盖本题评分维度，逐条说明交付要求与自证方式；自证方式以 `result.json` 字段、主产物和 `verify_report.json` 为准。

| 评分维度 | 子项 | 交付要求 | 自证方式 |
|---|---|---|---|
| 实际效果 40 | 任务完成度 15 | 真正完成“给定研究问题与设备材料约束、产出一份可执行参数方案”；交付物包含关键参数、建议值、可行区间、响应指标口径与验证方式 | `result.json.parameters[]` 每条有 `name/unit/recommended/min/max/response_metric/validation`；`protocol.md` 全节可执行 |
| 实际效果 40 | 结果正确性 15 | 建议参数落在设备量程、材料限制与安全阈值之内；响应指标与参数关系判断成立；成本与单位自洽 | `feasibility.parameters[]` 逐项展示边界来源；`result.json.cost[]` 每项有公式/单位；`verify_report.quotes_ok=true` |
| 实际效果 40 | 结果完整性 5 | 同时覆盖关键参数、响应指标、搜索策略与实验成本，并交代假设与变量、对照组、设备材料、时间成本、参数范围、风险和异常 | `result.json` 含 `hypotheses`+`variables`+`groups/controls`+`materials`+`equipment`+`schedule`+`risks`+`validation`；`protocol.md` 各节齐全 |
| 实际效果 40 | 结果可核验性 5 | 候选参数产生过程、每轮评估结果、取舍理由与停止判据可独立复核 | `result.json.search.rounds[]` 含候选数/最优点/理由；`sources[]` 有 `source_id/path/locator/quote/quote_verified`；`contract_backfill` 列全字段来源 |
| 使用增益 25 | 质量增益 15 | 相同条件下比基础 Agent 更可行、指标一致；约束感知搜索与成本-响应联合权衡带来提升 | `feasibility.conflicts[]` 捕获冲突；`cost` 与 `response_model` 有明确公式；`protocol.md` 的每一步有依据 |
| 使用增益 25 | 效率增益 5 | 减少候选点筛选、人工改参数、重复实验与方案返工 | `search.strategy` 解释序贯设计；`search.rounds` 体现每轮淘汰依据；`steps` 可执行 |
| 使用增益 25 | 增益可验证性 5 | 通过公平对照证明改善 | 不提供 hidden tests 或白板；在 `result.json.runtime` 记录本 Skill 运行状态；`changes` 记录 Agent 增强；不声称未经验证的对比结果 |
| 创新增益 15 | 新增能力 5 | 约束感知参数搜索与成本-响应联合权衡，基础 Agent 难以稳定实现 | `feasibility.bounds_by_source[]` 每条边界带来源；`cost` 含多目标权衡说明 |
| 创新增益 15 | 方法改进 5 | 搜索策略、停止判据、响应建模或约束处理有实质改进 | `search.method` 描述迭代规则；`stop_criteria` 可复算；`response_model.formula` 或 `screening` 设计 |
| 创新增益 15 | 创新证据 5 | 证明创新相对已有方案的边界和价值 | `result.json.notes` 或 `main_findings` 说明与 naive 方法的差异；示例仅作说明，不用作正式证据 |
| 可靠体验 10 | 调用与易用性 3 | 用户/Agent 能按说明从输入走完全程 | `SKILL.md` 第 2、3、5、15 章步骤可直接执行；`references/example.md` 提供最小示例 |
| 可靠体验 10 | 运行稳定性 4 | 不同实验类型、设备材料、重复运行持续产出可执行方案 | 确定性算法（无随机/无网络）；`verify_report.contract_complete=true`；退出码 0 |
| 可靠体验 10 | 异常处理 3 | 识别无可行解、约束冲突、数据缺失、设备报错、指标矛盾、权限不足等 | `errors[]`/`degradations[]`/`pending_human[]` 分条；`feasibility.conflicts[]` 含冲突来源；`status` 诚实 |
| 生态贡献 10 | 文档完整性 3 | 使用说明、依赖、约束来源、配置、示例、适用范围、限制、维护信息齐全 | `SKILL.md` 全文；`references/checklist.md`；`references/example.md` |
| 生态贡献 10 | 资源可复用性 4 | 脚本、参数模板、约束库、题集与评分表可复用 | `scripts/main.py`、`scripts/verify.py`、`references/protocol_template.md` 均为标准库；输出 CSV/Markdown 易复用 |
| 生态贡献 10 | 分享推广价值 3 | 沉淀案例、参数模板、实践经验与真实实验价值 | `references/protocol_template.md` 和 `references/example.md` 示意思路；正式案例结果由平台运行，不预先编写 |

## 7. 证据与定位规范

每条关键数值附 `{source_id, path, locator, quote, quote_verified}`；`locator` 用 JSON Pointer / 表行号 / 页码；`quote` 必须是原文逐字子串。无法逐字命中时置 `quote_verified=false` 并写 `degradations`，**不改原文凑通过**，也不把该数值当已成事实。

`source_id` 命名规则：`case-<case_id>-<文件别名>-<页码/表号>`；若来自 `case.json` 字段则用 JSON Pointer（如 `/equipment/hplc/flow_rate/min`）。所有 `sources[]` 必须有 `path` 或 `pointer`；不能只有模糊说明。

Agent 核验时，需要重新在原文中查找 `quote` 并确认其为连续子串；若原文包含换行或表格分隔，可注明“按单元格/行定位”，但仍需给出行号或表头。若无法访问原文或原文损坏，置 `quote_verified=false`，在 `degradations` 中记录原因。

## 8. 冲突与人工确认

约束交集为空、目标温度与材料耐温冲突、成本超预算、机时不足、指标互相矛盾、无可行解 → 输出 `feasibility.conflicts`（含两侧来源与 gap）+ 三种处置选项（调整参数/放宽约束/终止或转人工）+ `pending_human[].blocking=true`，并把 `status` 降为 `partial`（若完全无法出方案则 `insufficient_evidence`）。

对每个冲突，必须在 `conflict_id` 下记录：
- `constraint_a` / `constraint_b`：两个冲突条件及来源；
- `gap`：不可兼容的数值差或逻辑矛盾；
- `options`：不少于三种备选，每种给出可行性备注；
- `recommended`：Agent 基于已有证据推荐的选项；
- `pending_human`：需要专家确认的内容。

不未经确认改写建议值为可执行事实；一切人身安全、关键设备超限、伦理审批相关内容必须 `pending_human.blocking=true`。

## 9. 预算与断点

总预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行不计模型请求，但占用时间。Agent 必须“预算感知”：
- 优先完成 rubric 权重最高的交付物：`result.json` 完整字段、`protocol.md`、`parameter_plan.csv`、`risk_table.csv`。
- 尽早落盘 honest partial：启动后先写 partial `result.json`；脚本已经内置 780 秒时间预算，Agent 在脚本结束后，先核验字段完整性，再逐项增强。
- 建议请求分配（按模型请求记）：
  - 输入盘点与材料解析：2–4 次；
  - 运行基线脚本：0 次（脚本运行），但占用 60–180 秒；
  - 逐段核验来源 / 计算：15–20 次；
  - 撰写/补全最终产物：5–8 次；
  - 自检 rubric + 回填 finalize：2–4 次；
  - 预留 10–15 次用于异常修复与冲突处理。
- 当 900 秒剩余 < 120 秒时：停止一切增强，立即运行 `verify.py`，修正致命错误，写合法 `result.json` 并退出 0。
- 避免无意义循环与冗余调用；同一材料不重复解析；不确定时保持诚实 partial，不反复猜测。

## 10. 异常降级分支表

| 场景 | 处置 | 产物 |
|---|---|---|
| 无 `/input`、无 case.json | `status=input_error`，仍写合法 result.json 与三件产物骨架 | 退出码 0 |
| case.json 坏 JSON | 记 `errors`，尝试材料文本，`status=input_error` | 保留已解析材料 |
| 无参数定义 | `parameters=[]`，`pending_human` 要求补参数域 | protocol.md 标注缺口 |
| 可行域为空 | `feasibility.conflicts` + gap 数值 + 三选项 | `status=partial` |
| PDF/图片未解析 | `degradations` 记录，`input_files[]` 标注 | 其余流程继续 |
| 无历史数据 | 转 screening，`response_model` 标 `ok=false`，`uncertainty.level=high` | 建议值标为设计选择 |
| 缺价目/用量 | `cost.unknown_cost[]` 列出，`cost_per_run=null`，不编价 | `status=partial` |
| 指标互相矛盾 | 各自拟合 + 并列报告，不合并 | `validation` 双判据 |
| 材料缺失/损坏/格式不支持 | 记录到 `errors` 或 `degradations`，相应字段 `pending_human`；不阻断整体方案骨架 | 合法 result.json + 骨架产物 |
| 超时（剩余 < 120 秒） | 停止细化，执行 verify/finalize，保留已完成的 partial 并在 `runtime.time_remaining` 记录 | 合法 result.json |
| 空输入（/input 存在但空） | `status=input_error`，`errors[]` 写“empty input”，生成骨架产物 | 退出码 0 |
| `output_contract` 缺失或空 | 使用默认契约：`protocol.md`、`parameter_plan.csv`、`risk_table.csv`、`result.json` 主字段；在 `contract_backfill` 注明 | 合法 result.json |
| 权限不足/无法写 /app/output | 尝试回退 `/app/work` 并记录；最终仍写 `/app/output`；若仍失败，返回退出码 0 并在 errors 记录 | 尽力合法，不抛异常 |
| 设备报错/仪器量程互斥 | 按冲突处置，写 `feasibility.conflicts`，推荐替代参数 | `status=partial` |

任何情况下都要产出合法 `result.json`（退出码 0）。如果实在无法生成主产物，则生成骨架文件与合法 `result.json`，并在 `status`、`errors`、`degradations` 中明确说明。

## 11. 自检清单

1. `result.json` 是否存在且 JSON 语法合法？
2. 是否包含原 `output_contract` 全部字段（键名不改、未知键保留）与 `case_id`？
3. 是否包含 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`contract_backfill`？
4. `protocol.md`、`parameter_plan.csv`、`risk_table.csv` 是否都已生成且非空骨架？
5. 每个关键数值和参数建议是否都有 `source_id` 和 `quote_verified` 状态？
6. 是否避免编造数据、引用、价格、评分？缺口是否进了 `pending_human`？
7. 冲突是否都写进 `feasibility.conflicts` 并给出三种处置选项？
8. 是否保留所有基线产物字段，未删除/清空任何基线内容？
9. 是否运行 `python3 -B scripts/verify.py --input /input --output /app/output` 并生成 `/app/output/verify_report.json`？
10. 是否在提交前逐项核对「output_contract 字段列表 × 磁盘文件 × result.json 键」三者一一对应？
11. 退出码是否恒 0？是否在最后一步 finalize 并写 runtime？

若任何一项否，先补齐再收尾；无法补齐时，在 `errors`/`degradations`/`pending_human` 中诚实标注。

## 12. 最小调用示例（示例，非正式案例结果）

`references/example.md`：一组最小输入 + 调用命令 + 示意输出片段，已明确标注为示例，不冒充正式案例结果。示例中展示：
- 输入：最小 `case.json`，含 `goal`、`equipment`、`reagent`、`param`、`constraint`、`budget`、`output_contract`。
- 调用：`python3 -B scripts/main.py --input /input --output /app/output`。
- 示意输出：`parameter_plan.csv` 的前几行、`result.json.status` 为 `partial` 且注明“示例，非正式案例结果”。

## 13. 文件清单与版本

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 本文件，v1.1.0；Agent 执行总则、流程、预算、鲁棒性与自检 |
| `scripts/main.py` | 主流程（含输入发现、材料解析、可行域、搜索、成本、产物生成、契约回填） |
| `scripts/verify.py` | 确定性校验（契约、quote、计数、产物、合法性） |
| `references/protocol_template.md` | `protocol.md` 渲染模板 |
| `references/checklist.md` | rubric→字段映射、失败分支、自检表 |
| `references/example.md` | 最小示例（标注示例） |

依赖：Python ≥3.8 标准库。可选增强（缺失即降级）：`pdftotext`、`pypdf`。

## 14. 维护说明

调整判定逻辑只改 `main.py` 的常数量表（单位换算、参数别名、权重、容差），保持 `result.json` 键名稳定；改动后跑 `verify.py` 做回归。新增题型先在 `references/checklist.md` 补一行 rubric→字段，再改代码。若扩展材料解析器，需保持“真实解析、不依据文件名”原则，并为无法解析的文件提供 `degradations` 记录。任何修改不得引入随机性、网络依赖或外部状态，确保重复运行结果确定。

## 15. Agent 专属执行流程（六步，每步含输入/动作/输出/失败分支）

**步骤 1：盘点输入与契约**
- 输入：`/input/case.json`、`/input/task.md`、`/input/**` 文件列表。
- 动作：列出所有输入文件；打开 `case.json`（若有）找到 `output_contract`、`case_id`、`goal`、`equipment`、`reagent`、`param`、`constraint`、`budget` 等字段；若 `case.json` 不存在则从 `task.md` 和材料文件提取。
- 输出：内部清单（可写入 `/app/work/input_inventory.md` 供自查，不算交付物）。
- 失败分支：`case.json` 坏 JSON → 按异常表记 `input_error`；材料缺失 → 记录 `errors`/`degradations`，但继续尝试生成骨架。

**步骤 2：运行基线脚本并真实解析材料**
- 输入：`/input`、`/app/output`。
- 动作：运行 `python3 -B scripts/main.py --input /input --output /app/output`；等待其完成；若脚本内部已解析 PDF/CSV/XLSX/DOCX，则记录其产出；若脚本未解析出材料文本，Agent 自行调用平台可用工具（`pdftotext` 等）提取全文，并将结果写回 `/app/work` 或 `/app/output` 材料摘要。
- 输出：全套基线交付物：`result.json`、`protocol.md`、`parameter_plan.csv`、`risk_table.csv`；及可能的材料解析摘要。
- 失败分支：脚本异常但退出码 0 且产物缺失 → Agent 必须手工补齐骨架；脚本超时 → 使用已落盘 partial，Agent 继续手工完成关键字段。

**步骤 3：构建/核对证据库**
- 输入：`/app/output/result.json` 的 `sources`、原始材料内容、可执行建议。
- 动作：逐条核验关键数值的 `path/locator/quote` 是否真实；用原文查找 `quote` 子串；核验建议值是否在 `feasibility` 可行域内；核验成本公式中的单价/用量是否与材料一致；核验约束边界是否来自原文。
- 输出：更新后的 `sources[]`（`quote_verified` 置为 true/false）、`feasibility.bounds_by_source[]`、`contract_backfill`。
- 失败分支：原文无法定位或 `quote` 不匹配 → 将该条背景置 `quote_verified=false`，进入 `degradations` 或 `pending_human`；若关键参数完全无来源 → `status=insufficient_evidence` 或 `partial`，不编造来源。

**步骤 4：Agent 产出完整成品并增强**
- 输入：基线产物 + 核验后的证据库。
- 动作：由 Agent 亲自阅读 `protocol.md` 与 CSV，重写/补充各节，使文件成为可直接执行的完整方案；对基线中未解决的风险、冲突、确认项给出 Agent 的推导；修正解析错误、单位不统一、公式不完整；若基线有缺失字段，补齐；若需要，添加优化建议（如序贯搜索下一步、多目标取舍解释）。
- 输出：更新后的 `protocol.md`、`parameter_plan.csv`、`risk_table.csv`；`changes[]` 记录每项修改。
- 失败分支：若 Agent 无法在剩余预算内完成全部改写，优先保障 `result.json` 和三个主产物的完整字段，未深入改写部分保留基线并在 `changes` 注明“基线保留，Agent 未增强”。

**步骤 5：rubric 自检**
- 输入：`/app/output` 下的交付物、`result.json` 字段。
- 动作：逐项对照本文件第 6 章 rubric 表与第 11 章自检清单；运行 `python3 -B scripts/verify.py --input /input --output /app/output`；读取 `/app/output/verify_report.json` 的 `contract_complete/quotes_ok/artifacts_ok/has_uncertainty`。
- 输出：`verify_report.json`；若验证失败，修正交付物。
- 失败分支：若 `verify.py` 报告 `contract_complete=false` 或 `artifacts_ok=false`，Agent 必须补齐缺失字段/文件后重新运行，直到合法或时间耗尽；时间耗尽时保留部分修复并在 `errors` 说明。

**步骤 6：回填 result.json 并最终提交**
- 输入：所有交付物 + 自检结果。
- 动作：将 `status` 设为最终状态；记录 `runtime`（开始时间、结束时间、耗时、剩余时间）；把 `changes[]`、`reviewed_by_agent`、`errors/degradations/pending_human` 写入最终 `result.json`；确认 `case_id` 已填入；确认所有 `output_contract` 字段回填完成；写入 `/app/output/verify_report.json`；确认退出码 0。
- 输出：最终 `/app/output/result.json` 及全部产物。
- 失败分支：任何最终写入失败 → 重试一次；仍失败则回退 `/app/work` 写副本并记录错误，同时保证 `/app/output` 下至少有合法 `result.json` 骨架。

## 16. 预算分配与 partial 落盘策略

在 64 次模型请求 / 900 秒 / 16384 tokens 约束下，按以下优先级执行：

1. **必做（不允许跳过）**：运行基线 `main.py`；生成合法 `result.json`；生成 `protocol.md`、`parameter_plan.csv`、`risk_table.csv`；至少核验三个关键数值的来源；运行 `verify.py`；将 `verify_report.json` 写入 `/app/output`。
2. **优先做（rubric 权重高）**：完整性字段（假设/变量/对照/设备材料/时间成本/参数范围/风险/异常）全部出现；每个参数建议值落在可行域；每个冲突写入 `feasibility.conflicts`；每个未知/未验证进入 `pending_human`。
3. **可跳过/降级**：当时间不足时，可暂不逐条精修 `protocol.md` 的语言，但必须包含可执行步骤；可暂不为所有历史数据拟合代理模型，改用 screening 设计；可暂不生成额外 Office/图形预览（除非题面要求）。
4. **partial 落盘时机**：
   - 启动后立即写 `result.json`（`status=partial`）。
   - `main.py` 运行完成后更新一次 `result.json` 并落盘。
   - Agent 每完成一个主产物（protocol / CSV / risk）或每完成一轮证据核验后，重写 `result.json` 落盘。
   - 距离 900 秒剩余 120 秒时，强制 finalize 当前状态为最终 `result.json`，退出码 0。
5. **模型请求控制**：不要在循环中重复读取相同长材料；将关键事实浓缩成内部笔记后继续推理；不要反复生成相似文本。所有 Agent 自身推理消耗的请求计入 64 次，脚本运行不计入。

## 17. 隐藏案例鲁棒性

三个固定隐藏案例可能包含不同设备类型、材料格式、材料缺失、格式损坏或不支持的扩展名。必须按以下原则降级并诚实标注，任何情况下都产出合法 `result.json`（退出码 0）：

- **材料缺失**：不构造数据，`materials[]` 中该对象标 `missing=true`，`pending_human` 列出所需信息；`status` 至少为 `partial`。
- **材料损坏/无法解析**：尝试多种解析路径（PDF 用 `pdftotext` 后 `pypdf`；DOCX/XLSX 用 `zipfile`；CSV 尝试多编码）；仍失败则置 `input_files[].parse_status=failed`，写入 `degradations`，但不阻塞其他材料处理。
- **格式不支持**：如图片（PNG/JPG）默认不做 OCR（除非平台支持），登记为 `unprocessed` 并说明“未解析，无法提取文本”，内容相关字段标记 `pending_human`。
- **超时**：脚本和 Agent 分别有 780 秒和 900 秒预算；一旦 Agent 检测到剩余时间低于 120 秒，停止所有非必要任务，运行 `verify.py`，写最终 `result.json`。
- **空输入**：`/input` 存在但无有效文件或 `case.json` 为空 → `status=input_error`，三个主产物输出骨架，`result.json` 合法，`errors[]` 说明“empty input”。
- **契约缺失**：`case.json` 中无 `output_contract` → 使用默认契约，并在 `contract_backfill` 每条字段注明“默认契约”；主产物仍生成，保证人工可复核。
- **输出目录不可达**：尝试 `/app/output`；若权限错误，尝试 `/app/work` 做临时保存，然后再次尝试 `/app/output`；最终若仍失败，也要返回退出码 0 并在错误记录中说明。
- **任意未知异常**：捕获后写入 `errors[]`，保留已完成的交付物，确保不 crash。

所有降级都必须在 `result.json` 的 `status`、`errors`、`degradations`、`pending_human` 中真实反映，不得伪装为 `ok`。同时，不能因为降级而删除或忽略任何基线已生成的合法字段。

## 18. 契约回填与可核验性要求

`contract_backfill` 必须逐字段列出 `output_contract` 中每个键的来源：`slot`（从输入材料对应字段取得）、`default`（输入缺失时代用既定默认值）、`agent_revised`（Agent 在核验后修正）、`baseline`（保留基线自动值）等。每个字段注明 `field_path`、`source_path`、`status`。这样评审者可以逐项核对。

`runtime` 记录：`started_at`、`finished_at`、`elapsed_seconds`、`model_requests_used`（由 Agent 估算或平台记录，不伪造）、`time_remaining_seconds`、`fallback_triggered`。

`reviewed_by_agent`：布尔值加上 `agent_enhancements` 数组，逐条列出 Agent 对基线做出的增强或修正，如“参数 X 建议值从 37 修正为 36.5，依据设备量程上限（source_id=...）”。

所有修改通过 `changes` 追加记录：`{time, field, before, after, reason, source}`。

## 19. 完成标准与最终检查

最终交付必须满足：
- 实验人员可根据 `protocol.md` 执行，或明确知道缺少哪些信息。
- 每条关键数值、参数建议、风险触发条件都有来源定位或明确未验证标记。
- 所有约束上的冲突都有三种处置选项和推荐。
- `result.json` 合法、字段完整、状态诚实；`contract_backfill` 可核验。
- 磁盘上的文件与 `result.json` 中列出的主产物一致，无缺失。
- 退出码为 0，且提交目录包含本 SKILL.md、脚本和 references。

提交前按第 11 章自检清单逐项打勾，并确认没有删除/清空任何基线产物；若执行过增强，`reviewed_by_agent` 与 `changes` 中留有证据。这就是“genuinely-derived”的可核验痕迹。