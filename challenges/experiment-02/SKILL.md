---
name: experiment-feasibility-review
version: 1.0.0
description: 实验方案可行性审查。当用户给出一份或多版本实验方案、候选设计、SOP、课题计划书，要求判断"能不能按现有设备、材料、预算、排期、样本与伦理状态真实开工"，或要求做方案自查、内部评审、送审前检查、版本比选时使用。把方案与设备量程、试剂库存与货期、预算与时间窗、参数范围、风险处置、伦理与安全状态逐条核对，输出七类约束检查表、逐版本可执行结论、protocol.md、risk_table.csv、check_matrix.csv 与 result.json。不做实验执行、数据分析与文献综述。
---

# 实验方案可行性审查

## 1. 用途与边界

**做**：把一份（或 2–3 个版本）实验方案，转成可逐条判定的七类约束检查表，用输入给出的真实数字做算术，给出可执行结论与条件清单。

七类检查（固定顺序）：`HYPOTHESIS` 假设与变量 / `CONTROL` 对照组 / `RESOURCE` 设备与材料 / `TIME` 时间与成本 / `PARAM` 参数范围 / `RISK` 风险与异常 / `ETHICS` 伦理与安全。

**不做**：实验执行、数据分析与统计结论、文献综述、论文写作；不替代伦理委员会、生物安全委员会、设备管理员或 PI 的签字。

**四条立场**（与"技术上看起来合理"式点评的分界）：

1. **未写 ≠ 满足**：方案没写的检查项一律 `gap`，不因"通常会做"记 `met`。
2. **只在输入上算术**：时间、费用、量程余量只用输入数字；输入没给的阈值不臆造，进 `pending_human` 与 `uncertainty`。
3. **可复核**：每条判断带 `source_id + locator + quote`，指向方案原文的具体字段或行。
4. **结论可执行**：`feasible_with_conditions` 必须写成条件清单（买什么、批什么、改哪个参数、等多少天），不写"建议进一步确认"。

## 2. 触发条件

适用：用户给出实验方案/设计/多版本候选，问"能不能做""还缺什么""哪版可行""按现有条件能不能开工""帮我审一下方案"。

不适用：纯文献综述、数据分析、图表绘制、论文润色——改用对应 Skill。

## 3. 运行契约

- 输入：`/input/case.json`（或任意 `case*.json`）+ `/input/` 下材料（md/txt/csv/xlsx/docx/pdf/图片）。
- 只读 `/input`，只写 `--output`（默认 `/app/output`）；不联网；纯 Python 标准库（`pypdf` 存在时用于 PDF，缺失则降级，不是硬依赖）。
- 退出码恒 0；先写 partial `result.json`，最后无条件 finalize。

## 4. 调用方式

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/main.py --help      # 参数说明
```

脚本入口自解析参数，不依赖当前工作目录（用 `Path(__file__)` 定位 `references/`）。
stdout 只打一行摘要：`case_id=… status=… checks=… elapsed=…s`。

## 5. 输入发现（语义识别，不假设键名）

递归遍历 `case.json`，按键名子串匹配：`plan/candidate/version/方案/版本`（多版本方案，取内容最长的一组，≤6 版）、`equipment/instrument/设备/仪器`、`reagent/material/试剂/耗材`、`parameter/factor/参数/取值`；预算、时间窗、人力按键名+指针（`budget/预算`、`deadline/window/周期/期限`、`personnel/人员`）。

其余文件按扩展名抽文本：`.md/.txt/.csv/.json` 直读；`.docx/.xlsx/.pptx` 解 zip 取 XML 文本；`.pdf` 用 `pypdf`；位图不做 OCR（记 `degradations`）。单文件 ≤4 MB、最多 80 个。

完整规则见 `references/schema.md` §1。

## 6. 核心流程

```
读输入 → 语义发现 → 归一化（设备/材料/参数/多版本方案）
      → 七类检查（35 项：探针命中 + 5 组算术）
      → 逐版本判定（verdict/条件/阻断项）
      → 落盘 protocol.md + 2 CSV + result.json → 回填契约 → selftest
```

## 7. 检查项与判定口径

检查项库在 `references/checks.md`（35 项，脚本启动时解析，不在代码里重复定义）。改检查项只改这个文件。

| 判定 | 含义 |
|-|-|
| `met` | 探针组全部命中，或算术满足（左值 ≤ 右值） |
| `partial` | 部分要素具备（部分设备/试剂有状态、库存字段） |
| `gap` | 任一探针组未命中 / 缺基准（窗口/预算/货期/单价）/ 输入无对应清单 |
| `blocked` | 算术硬冲突：参数越出全部设备量程、货期或总历时超时间窗、材料费超预算 |
| `na` | 不适用（未涉及人体/动物/危险试剂/个人数据；输入无取值域） |

算术只有 5 组，全部只用输入数字，`inputs` 原样落盘可复算：R-02/P-02 参数量程、R-04 货期 vs 时间窗、T-02 总历时 vs 时间窗、T-04 费用 vs 预算、P-05 取值域。

## 8. 输出物

| 文件 | 内容 |
|-|-|
| `result.json` | 契约回填 + `plans`（逐版本结论）+ `checks`（35×N 条）+ `gaps` + `pending_human` + `uncertainty` + `sources`；主结果语义键 `feasibility`/`comparison`/`variables`/`validation`/`anomaly` 恒输出真实内容 |
| `protocol.md` | 可执行方案：结论/执行条件/假设/变量/分组/材料仪器/参数/步骤/判读与停止/风险/伦理/缺失信息 |
| `risk_table.csv` | 风险与异常处置：`mode,status,trigger,mitigation,fallback,escalation,locator` |
| `check_matrix.csv` | 逐条检查与证据：`check_id,plan,class,item,severity,verdict,basis,needs_human,locator,quote,arithmetic,action,note` |

字段字典见 `references/schema.md` §2；每条判断的证据都在 `check_matrix.csv` 里可查。

## 9. 结论口径

- `infeasible`：存在 `blocked`（按现有条件无法开工）。
- `feasible_with_conditions`：无硬冲突但有缺口，条件清单给出修复路径。
- `feasible`：无缺口。

评分 `score = 100 × (met + 0.5×partial) / (总检查数 − na)`，仅用于同批版本互比；推荐顺序 `blocking↑ → score↓ → 条件数↑ → 版本序`。

## 10. 证据与定位

`locator` 两种形态：`case.json#/plans/1/parameters/2`（JSON Pointer）、`material.md#L12`（行号）。
`quote` 取自对应行的整句原文；`arithmetic.inputs` 全部为输入原值。三层证据链 = 结论 → 检查行 → 原文位置。

## 11. 异常与降级

| 情形 | 处置 | status |
|-|-|-|
| `case.json` 缺失 / 坏 JSON | 记 `errors`，用其余文件继续 | `input_error` |
| 无方案文本 | 七类全 `gap` | `insufficient_evidence` |
| 无设备/材料清单 | R-01/R-02/R-03 记 `gap` + `pending_human`，不补量程 | `partial` |
| 无预算/时间窗 | R-04/T-02/T-04 记 `gap`，写入 `uncertainty` | `partial` |
| PDF 抽不到文本 / 位图 | 记 `degradations`，不阻断其余检查 | 不变 |
| `checks.md` 缺失 | 内置 7 条兜底项，`lib_source=builtin-fallback` | `partial` |
| 任一异常 | 捕获进 `errors`，仍写合法 `result.json`，退出码 0 | 视剩余证据 |

## 12. 预算与断点

先落盘 partial（含契约空值），再逐步补全；单案例在本机 0.4 s 量级，远低于 900 s 预算。长文档只截取前 400 KB 文本，不阻塞。任何阶段中断，`result.json` 都合法且 `status` 说明缺口。

## 13. 自检

`result.json.selftest` 字段给出：`checks` 条数、`contract_missing`（契约缺字段）、`artifacts_missing`（产物缺失）、`classes`（覆盖到的检查类）。三项为空且 `classes` 含 7 类即为通过。人工复核：打开 `check_matrix.csv`，抽任意一行按 `locator` 回原文对照 `quote`。

## 14. 最小调用示例

见 `references/example.md`（含完整最小 `case.json`、调用命令、示意输出）。**该示例为说明用自造数据，不是平台正式案例结果。**

## 15. 适用限制

- 只审"能不能按条件开工"，不判断科学价值与创新性。
- 探针为字面量匹配（中英关键词），同义改写可能漏检 → 标 `gap` 并列入条件，不会误判为 `met`。
- 外部资料（价格、货期、审批周期）一律以输入为准；输入缺就记缺口，不做行业假设。
- 图片材料不做 OCR。
- 多版本超过 6 个时只审前 6 个。

## 16. 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本文件 |
| `scripts/main.py` | 入口：发现/抽取/七类检查引擎/产物/契约回填 |
| `scripts/feas.py` | 内核：解析归一化、量纲算术、证据定位、protocol 渲染 |
| `references/checks.md` | 35 项检查库与判定依据（脚本唯一数据源） |
| `references/schema.md` | 输入输出契约、字段字典、公式表、降级表 |
| `references/example.md` | 最小示例（示例数据） |

依赖：Python 3.8+ 标准库；可选 `pypdf`（PDF 文本）。无网络、无第三方硬依赖、无外部数据文件。

## 17. 维护

- 改检查项：编辑 `references/checks.md` 并递增版本号，`id` 不复用。
- 改字段：同步 `references/schema.md`；契约回填逻辑在 `main.py:fill_contract`。
- 回归：用 `references/example.md` 的输入跑一遍，确认 `selftest.classes` 含 7 类、`contract_missing` 为空。
