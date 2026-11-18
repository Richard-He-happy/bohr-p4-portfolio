---
name: experiment-parameter-optimizer
description: Turn a research goal plus equipment ranges, reagent specs, budget/time limits and existing data into an executable, evidence-located experiment parameter plan (key parameters, recommended values, feasible intervals, response-metric definitions, sequential search trace, cost accounting, validation and stop criteria). Use for experiment-parameter optimisation, protocol/candidate comparison and selection, feasibility or conflict checks, and screening design when inputs arrive as case.json plus PDF/CSV/XLSX/DOCX materials.
version: 1.0.0
---

# 实验参数优化 / Experiment Parameter Optimizer

## 1. 用途与边界

把「研究目标 + 设备量程 + 材料限制 + 预算/机时 + 已有数据」转成一份可用于开机的参数方案：关键参数、建议值、可行区间、响应指标口径、搜索策略、成本与耗时、风险与替代、判读与停止判据；每个数值给出来源定位。

适用：有界参数优化；多版候选方案比较与择优；可行性与约束冲突检查；无历史数据时的筛选（screening）设计。
不适用：需要发明新合成路线/分子设计的任务；需要真实仪器控制或远程下单的任务；必须先经伦理审批的人体/动物实验（这类只输出方案骨架与确认项，`status=partial`）。

## 2. 运行契约

- 输入：`/input/case.json`（首选）、`/input/task.md`，以及 `/input/` 下任意 PDF/CSV/XLSX/DOCX/JSON/PNG 材料。
- 产物：全部写 `/app/output/`，根目录必须有 `result.json`。
- 入口（在 Skill 安装根目录执行）：

```
python3 -B scripts/main.py   --input /input --output /app/output
python3 -B scripts/verify.py --input /input --output /app/output
```

- 只用 Python 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`）。
- 退出码恒 0；任何异常写入 `errors`/`degradations`/`pending_human`，先落 partial 再 finalize。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `case.json`；不存在则递归找 `*case*.json`，再退化为只读 `task.md` 与材料文件。
2. 递归扫描 `/input/**`，按扩展名 + 魔数分类；PDF 依次尝试 `pdftotext`、`pypdf`、stdlib zlib 流解码；DOCX/XLSX 用 `zipfile` + XML 正则取文本；图片只登记、不做 OCR。
3. 语义键匹配（大小写、中英不敏感，允许嵌套）：`goal|目标`、`equipment|instrument|设备|仪器`、`reagent|material|试剂|材料`、`param|factor|参数|因子`、`domain|levels|范围`、`constraint|limit|threshold|阈值`、`budget|cost|price|预算|费用|报价`、`booking|机时`、`plan|candidate|version|方案|版本`、`existing_results|history|历史`、`output_contract|输出契约`。
4. 材料未给的对象（无价目、无毒理、无仪器精度、无伦理批件）**明确列入 `pending_human` 与 `materials[].gap`**，不构造。

## 4. 输出契约

`result.json` = `output_contract` 全部字段回填（键名不改、未知键保留、缺值 `null`/`[]`/`{}` 按其声明类型）+ `case_id` + `status`(`ok|partial|insufficient_evidence|input_error`) + `sources` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime` + `contract_backfill`（逐字段记录取到 slot 还是 default）。

主产物：`protocol.md`（可照做）、`parameter_plan.csv`（建议值/区间/绑定约束/依据 ID）、`risk_table.csv`（触发—检测—处置—替代）。搜索轨迹、响应模型、成本、判读判据在 `result.json` 的 `search`/`response_model`/`cost`/`validation`。

## 5. 核心流程

建参数登记表 → 设备量程 ∩ 材料限制 ∩ 安全阈值 ∩ 显式域求交得可行域 → 冲突检测 → 候选生成（确定性全因子，候选上限 600 点）→ 序贯细化与停止判据 → 成本-响应联合权衡 → 生成协议/参数表/风险表 → 契约回填与自检。

搜索与停止写在 `search` 的 `rounds` 里：第 1 轮全因子枚举，第 2 轮沿各轴 ±半步细化；停止条件为「改进 < 1% 域宽」或「候选预算耗尽」或「临近时间预算」，逐轮记录候选数、最优点与理由。

## 6. 任务质量规则（rubric → 字段/检查/产物）

| rubric | 落点 |
|---|---|
| 任务完成度 | `parameters`(建议值+区间+单位)、`summary`、`protocol.md` 全节 |
| 结果正确性 | 建议值 ∈ `feasibility` 可行域；`cost` 逐项 `formula`；单位经 `unit` 归一 |
| 结果完整性 | `hypotheses`+`variables`+`groups`/`controls`+`materials`+`equipment`+`schedule`+`risks`+`validation` 八项齐全 |
| 结果可核验性 | `sources[]` 的 `locator`+`quote`；`search.rounds` 每轮可复算；`contract_backfill` |
| 使用增益 | `steps` 可直接执行；缺口只进 `pending_human`，不阻塞方案主体 |
| 创新增益 | 约束感知可行域（每边界带来源）+ 成本-响应联合权衡 + 停止判据 |
| 可靠体验 | `status` 四态诚实；`errors`/`degradations` 分条；重复运行确定性（无随机、无网络） |
| 生态贡献 | 本文件 + `references/checklist.md`（模板与检查表）+ `references/example.md` |

## 7. 证据与定位规范

每条关键数值附 `{source_id, path, locator, quote, quote_verified}`；`locator` 用 JSON Pointer / 表行号 / 页码；`quote` 必须是原文逐字子串。无法逐字命中时置 `quote_verified=false` 并写 `degradations`，**不改原文凑通过**，也不把该数值当已成事实。

## 8. 冲突与人工确认

约束交集为空、目标温度与材料耐温冲突、成本超预算、机时不足、指标互相矛盾 → 输出 `feasibility.conflicts`（含两侧来源与 gap）+ 三种处置选项 + `pending_human[].blocking=true`，并把 `status` 降为 `partial`。

## 9. 预算与断点

64 请求 / 900 s；启动即写 partial `result.json`；脚本内置 780 s 时间预算（常量，无需传参），临近时停止细化、以当前最优 finalize。

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

## 11. 自检清单

`references/checklist.md` 第 4 节；另跑 `python3 -B scripts/verify.py --input /input --output /app/output`，报告写 `/app/output/verify_report.json`（`contract_complete`/`quotes_ok`/`artifacts_ok`/`has_uncertainty`）。

## 12. 最小调用示例（示例，非正式案例结果）

`references/example.md`：一组最小输入 + 调用命令 + 示意输出片段，已明确标注为示例，不冒充正式案例结果。

## 13. 文件清单与版本

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 本文件，v1.0.0 |
| `scripts/main.py` | 主流程（含输入发现、可行域、搜索、成本、产物生成） |
| `scripts/verify.py` | 确定性校验（契约、quote、计数、产物） |
| `references/protocol_template.md` | `protocol.md` 渲染模板 |
| `references/checklist.md` | rubric→字段映射、失败分支、自检表 |
| `references/example.md` | 最小示例（标注示例） |

依赖：Python ≥3.8 标准库。可选增强（缺失即降级）：`pdftotext`、`pypdf`。

## 14. 维护说明

调整判定逻辑只改 `main.py` 的常数量表（单位换算、参数别名、权重、容差），保持 `result.json` 键名稳定；改动后跑 `verify.py` 做回归。新增题型先在 `references/checklist.md` 补一行 rubric→字段，再改代码。
