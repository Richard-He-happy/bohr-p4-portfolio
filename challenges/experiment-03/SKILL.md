---
name: experiment-parameter-optimizer
description: 将研究目标、设备量程、试剂与材料限制、预算/机时、历史数据与候选方案转化为可执行的实验参数方案；输出关键参数、建议值、可行区间、响应指标口径、序贯搜索轨迹、成本核算、风险与停止判据。强调真实解析材料、约束感知搜索、成本-响应联合权衡、逐字来源可核验；提供 Agent-first 与无草稿时确定性兜底双路径，所有最终产物统一回填同一 result.json 契约。适用于有界参数优化、候选方案比较与择优、可行性与约束冲突检查、筛选设计。输入为 /input/case.json、/input/task.md 与 /input 下 PDF/CSV/XLSX/DOCX/JSON 材料；输出到 /app/output。纯 Python ≥3.8 标准库、离线、确定性运行。
version: 1.2.0
---

# 实验参数优化 / Experiment Parameter Optimizer

## 0. 最高执行优先级：rubric 高分契约

本 Skill 只做一件事：把给定研究问题、设备/材料约束、预算/机时和已有数据变成一份可开机的参数方案，并且让每个关键数字、来源、搜索步骤、成本口径可以被独立复核。你（Agent）不是改写 JSON 结构，而是在脚本生成的高完整性基线上做真实阅读、核验、补全与增强。

必须遵守：
1. **单命令完整交付**：默认入口必须从输入直达全套产物，不要求外部手工串联。
2. **双路径同契约**：有 Agent draft 时与无 draft 时都产出同一套文件、同一份 `result.json` 契约；无 draft 时不得给空骨架，必须确定性生成实质工作稿。
3. **所有关键数字/论断必须带 `[S#]` 来源与 `文件#行号/段落号` locator，且 quote 为原文逐字子串。** 没有来源不放进建议值；材料缺失写 `gaps/pending_human/degradations`。
4. **result.json 双回显**：`output_contract` 字段在 `result.json` 顶层和 `result.json.output_contract` 中各出现一次；保留 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`contract_backfill`。
5. **诚实 partial > 伪造完整**：无法确认的设备/材料/价格/安全阈值必须显式登记，不得把未经确认的建议写成可执行事实。任何异常也退出码 0。

---

## 1. 入口与运行时契约

### 1.1 单命令全流程入口

在 Skill 安装根目录执行：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

必须实现为三个内部阶段：

1. **init** — 盘点 `/input` 材料与 `case.json`；生成来源编号；抽取候选参数、约束、候选方案；进行冲突分组；把台账写入 `/app/work/ledger.json`。若 Agent 未提供 `draft.json`，则进一步生成确定性兜底草稿 `/app/work/draft.auto.json`。
2. **build** — 校验 draft/auto draft 的 quote 与 locator；执行确定性兜底抽取；求出可行域、冲突检测、候选生成、搜索轨迹、响应模型选择、成本核算；渲染 `protocol.md`、`parameter_plan.csv`、`risk_table.csv`；最终回填 `result.json`。
3. **selfcheck** — 运行自检，检查 `output_contract` 字段、磁盘产物、来源计数；生成 `/app/output/verify_report.json`；保证 `result.json` 合法。

若当前安装的 `scripts/main.py` 只支持旧式 `--input/--output` 而暂无 `run` 子命令，则等价调用 `python3 -B scripts/main.py --input /input --output /app/output`，但 Agent 必须确保在 `/app/work` 下完成 init/build/selfcheck 三阶段；正常评测以本 Skill 期望的 `run` 入口为准。

### 1.2 自检命令

```bash
python3 -B scripts/verify.py --input /input --output /app/output --work /app/work
```

如脚本不接受 `--work`，则退化为 `python3 -B scripts/verify.py --input /input --output /app/output`。verify 必须确定性检查：`result.json` 合法、契约字段完整、`case_id` 存在、主产物存在、quote/source 计数合理。

### 1.3 资源限制

- 仅用 Python ≥3.8 标准库；不联网；不依赖 CWD。
- 文件总数 ≤ 50 个 UTF-8 文本文件，单文件 ≤ 500 KB，总 ≤ 2 MB，不建 symlink。
- 退出码恒 0；即使输入错误或产物缺失也返回合法 partial。

---

## 2. Agent-first 双路径

### 2.1 路径 A：Agent 判断优先

1. 先运行 `init` 得到台账 `/app/work/ledger.json`。
2. Agent 亲自读 `/input/case.json`、`/input/task.md`、原始 PDF/CSV/XLSX/DOCX 内容。
3. Agent 把判断写入 `/app/work/draft.json`。draft 形状见第 4 节。
4. 再运行 `run`（会完成 check→build→selfcheck）。build 必须合并 draft 中的 Agent 判断，但每条仍要经过 quote/constraint 校验；不合法或不来自原文的内容不能作为高可信建议，除非显式 marker。

### 2.2 路径 B：无 draft 时确定性兜底

若 `/app/work/draft.json` 不存在，`init` 必须生成 `/app/work/draft.auto.json`。该草稿不是空模板，而是从台账和原文中确定性抽取出的实质工作稿：
- 每个候选参数/约束/响应指标给出 `source_id`、`locator`、逐字 `quote`；
- 搜索策略使用确定性全因子/序贯细化；
- 成本行只填可解析项，未知项留 `null` 并进 `unknown_cost`；
- 将 `AUTO_EXTRACT` 作为 `degradations[]` 项与 `changes[]` 记录，说明“由确定性脚本抽取，Agent 未逐条复核”。

两条路径最终必须产出同一套产物文件和同一份 `result.json` 契约结构，只是 `reviewed_by_agent`、`changes`、`uncertainty.level`、`degradations` 的 nuanced 差异允许不同。

---

## 3. 输入发现与 init 台账

1. 首选 `/input/case.json`；不存在则递归找 `*case*.json`；仍无则回退到 `/input/task.md` 与原始材料。
2. 按扩展名 + 魔数识别 `/input/**`：
   - PDF 依次尝试 `pdftotext`、`pypdf`、标准库可用解析；不得只凭文件名判断。
   - DOCX/XLSX 用 `zipfile` + XML 正则取文本；CSV/JSON 直接读；图片只登记，无 OCR 不编造。
   - 未解析文件登记到 `errors[]/degradations[]`，不阻断主流程。
3. 语义键匹配（大小写/中英不敏感）：`goal|目标`、`equipment|instrument|设备|仪器`、`reagent|material|试剂|材料`、`param|factor|参数|因子`、`domain|levels|范围`、`constraint|limit|threshold|阈值`、`budget|cost|price|预算|费用|报价`、`booking|机时`、`plan|candidate|version|方案|版本`、`existing_results|history|历史`、`output_contract|输出契约`。
4. 台账每项至少含：`source_id`、`path/pointer`、`locator`、`quote`、`quote_verified`、`category`、`needs_human_check`。
5. `source_id` 命名：`case-<case_id>-<file_key>-<page_or_table>`；`case.json` 字段用 JSON Pointer，如 `/equipment/hplc/flow_rate/min`。

---

## 4. draft.json 形状

Agent 写入 `/app/work/draft.json` 时使用以下形状；键名保持稳定，缺项可 `null`/`[]`/`{}`。

```json
{
  "case_id": "string",
  "parameter_decisions": [
    {
      "parameter": "string",
      "recommended": null,
      "min": null,
      "max": null,
      "unit": "string",
      "rationale": "string",
      "source_id": "string",
      "quote": "string",
      "locator": "string",
      "quote_verified": false,
      "bound_type": "equipment|reagent|safety|budget|domain|explicit"
    }
  ],
  "response_model": {
    "type": "none|linear|quadratic|piecewise|screening",
    "formula": "string",
    "sources": [],
    "note": "string"
  },
  "search": {
    "strategy": "string",
    "stop_criteria": "string",
    "rounds": []
  },
  "cost": {
    "lines": [
      {
        "item": "string",
        "formula_or_quote": "string",
        "amount": null,
        "unit": "string",
        "source_id": "string"
      }
    ],
    "cost_per_run": null,
    "unknown_cost": []
  },
  "conflicts": [],
  "pending_human": [],
  "notes": "string"
}
```

Agent 可以只填入有把握的部分；其余由 build/auto draft 补全，并如实记录。

---

## 5. Build：校验、可行域、搜索、成本与渲染

### 5.1 可行域与来源边界

对每个参数建立 `feasibility.bounds_by_source[]`，逐项记录：
- `parameter`；
- `bound_type`；
- `min/max/step`；
- 来源 `source_id`、`locator`、`quote`、`quote_verified`；
- 是否专家确认项。

推荐值必须落在设备量程 ∩ 材料限制 ∩ 安全阈值 ∩ 显式 domain 的交集内。边界为空时生成 `feasibility.conflicts[]`，不得强行推荐。

### 5.2 候选生成与搜索

搜索记录在 `search.rounds[]`，每个 round 含：
- `round_id`；
- `candidates_total`；
- `candidates_feasible`；
- `best_point`；
- `response_estimate`；
- `cost_estimate`；
- `reason`；
- `sources_used`。

确定性策略：
- 第 1 轮：全因子枚举显式 domain，候选上限 600 点，记录可行候选数。
- 第 2 轮：沿各参数轴 ±半步细化当前最优点邻域，记录响应/成本变化。
- 后续轮：仅当预期改进 ≥ 域宽 1% 且候选预算未耗尽时继续。
- 停止条件写入 `stop_criteria`，至少包含：改进 < 1% 域宽、候选预算耗尽、临近 780s 时间预算。

### 5.3 响应模型

- 有历史数据：优先线性/二次/分段代理模型；给出公式、残差/拟合说明、来源；未验证关系标注 `uncertainty.level`。
- 无历史数据：转 screening 设计，`response_model.type=screening`，`response_model.ok=false`，`uncertainty.level=high`，`parameter_decisions[].recommended` 标为“设计选择，非实验实证”。

### 5.4 成本核算

成本记录在 `result.json.cost[]`：
- 每行含 `item`、`formula`、`unit_cost`、`amount`、`subtotal`、`source_id`。
- 无法获得单价/用量时写入 `cost.unknown_cost[]`，对应 `cost_per_run=null`，并 `status=partial`；不得用常识编价。
- 单位必须自洽；不一时在 `degradations[]` 说明。

### 5.5 产物渲染

必须生成：
- `result.json`；
- `protocol.md`：假设、变量、对照、步骤、参数、资源、判读标准、依据与风险、异常处置、待确认事项；
- `parameter_plan.csv`：关键参数、建议值、可行区间、单位、绑定约束、依据 ID、核验状态；
- `risk_table.csv`：触发条件、检测方式、处置动作、替代方案、风险类别；
- `verify_report.json`：自检报告。

如果 `output_contract` 要求可编辑 Office/slide/diagram，则额外生成真实渲染 PDF/PNG 预览；默认主产物为 Markdown/CSV。

---

## 6. result.json 契约与双回显

`result.json` 必须同时满足：

### 6.1 顶层字段

- `output_contract`：嵌套对象，原样回填契约全部字段。
- 顶层同时包含与 `output_contract` 相同的业务字段，不回改键名，未知键保留，缺失按声明类型填 `null`/`[]`/`{}`。
- `case_id`：从 `case.json` 或输入定位，缺失则 `input_error`。
- `status`：`ok|partial|insufficient_evidence|input_error`。
- `sources`：数组，每项 `{source_id,path,locator,quote,quote_verified}`。
- `uncertainty`：`{level,reasons[]}`。
- `pending_human`：数组，每项 `{item,reason,blocking}`。
- `errors`：数组，每项 `{code,message,file,scope}`。
- `degradations`：数组，每项 `{scope,reason,impact}`。
- `changes`：数组，每项 `{time,scope,before,after,reason}`。
- `runtime`：`{started_at,finished_at,time_remaining}`。
- `contract_backfill`：数组，逐字段记录值来自 slot 还是 default。
- `reviewed_by_agent`：布尔或对象，记录 Agent 是否核验/增强。

### 6.2 契约字段覆盖

若 `output_contract` 缺失或空，使用默认契约字段：关键参数、响应指标、搜索策略、实验成本、假设/变量/对照、设备材料、时间成本、参数范围、风险/异常、确认项。并在 `contract_backfill` 记录“使用默认题目契约”。

### 6.3 回显示例结构（不含真实数据）

```json
{
  "case_id": "...",
  "parameters": [],
  "response_metrics": [],
  "search": {},
  "cost": [],
  "protocol_summary": {},
  "risks": [],
  "pending_human": [],
  "sources": [],
  "status": "partial",
  "output_contract": {
    "parameters": [],
    "response_metrics": [],
    "search": {},
    "cost": [],
    "protocol_summary": {},
    "risks": []
  }
}
```

---

## 7. 证据与定位规范

1. 每个关键数值、约束边界、参数建议、成本行必须附 `source_id`、`path`/`pointer`、`locator`、`quote`、`quote_verified`。
2. `locator` 可以是 `文件#页码/段落号`、JSON Pointer、CSV 行列号。
3. `quote` 必须是原文逐字子串。表格内容按单元格/行定位，仍需给行号或表头。
4. 无法逐字命中时置 `quote_verified=false`，进入 `degradations[]`，不要把该数值当已证实事实；若需要推理，标注 `source_id=expert_prior`。
5. Agent 核验时必须回到原文检索 quote，确认连续性；未访问原文或原文损坏时，必须显式写 `quote_verified=false` 和原因。

---

## 8. 冲突、风险与人工确认

约束冲突或不可行时，每个 `feasibility.conflicts[]` 项必须包含：
- `conflict_id`；
- `constraint_a`、`constraint_b` 及各自来源；
- `gap`：数值差或逻辑矛盾；
- `options`：至少三个备选方案及可行性备注；
- `recommended`：Agent 基于证据推荐的选项；
- `pending_human`：需要专家确认的内容。

三类必须 `pending_human.blocking=true` 的内容：
- 人身安全/关键设备超限；
- 伦理审批、真实临床/动物实验批准；
- 设备可用性、准确报价或供应商合同未经确认。

`risk_table.csv` 至少覆盖：无可行解、设备报错、指标矛盾、数据缺失、成本超预算、机时不足、材料缺失/损坏、格式不支持、权限不足、超时。

任何异常都不得抛异常；必须落合法 `result.json` 并退出 0。

---

## 9. 预算感知执行

预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本运行不计模型请求，但占时间。

推荐分配：
- 输入盘点与契约识别：2–4 次；
- 运行 baseline/init/build：0 次模型请求，60–180 秒；
- 证据核验与来源比对：15–20 次；
- 成稿补全与参数方案改写：5–8 次；
- rubric 自检与 finalize：2–4 次；
- 预留异常修复：10–15 次。

当剩余时间 < 120 秒：停止一切增强，执行 verify，保证 `result.json` 合法、字段完整，写 `runtime.time_remaining`，退出 0。

---

## 10. 输出文件清单与异常分支

| 文件 | 必需品 | 说明 |
|---|---|---|
| `result.json` | 是 | 双回显契约、状态、来源、不确定性、pending_human |
| `protocol.md` | 是 | 可执行方案正文 |
| `parameter_plan.csv` | 是 | 参数表 |
| `risk_table.csv` | 是 | 风险与异常表 |
| `verify_report.json` | 是 | 自检输出 |
| `/app/work/ledger.json` | 是 | 台账 |
| `/app/work/draft.json` 或 `draft.auto.json` | 是 | Agent 判断或确定性兜底草稿 |

异常兜底：
- 无 `/input`/坏 JSON/空输入：`status=input_error`，仍写合法骨架产物。
- 可行域为空：`status=partial`，输出冲突与选项。
- PDF/图片未解析：记入 `degradations[]`，其余继续。
- 无价目/用量：`status=partial`，`unknown_cost[]` 列出，不编价。
- 指标矛盾：并列报告，不合并，写 `validation` 双判据。
- 输出目录不可写：尝试回退 `/app/work` 并记录，最终尽力写 `/app/output`；仍失败则退出 0 并记错误。

---

## 11. 自检清单 / SELFTEST

1. `result.json` 存在且 JSON 语法合法。
2. `output_contract` 全部字段在顶层和嵌套 `output_contract` 中各出现一次。
3. `case_id` 存在且来自输入。
4. `status/sources/uncertainty/pending_human/errors/degradations/changes/runtime/contract_backfill` 均存在。
5. `protocol.md`、`parameter_plan.csv`、`risk_table.csv` 非空且可核验。
6. 关键数字均有 `[S#]` 和 `文件#行号/段落号` locator。
7. `quote` 均为原文逐字子串或显式 `false`。
8. 可行域来源逐项记录；推荐值在可行域内。
9. `search.rounds[]` 含停止判据；`cost[]` 单位自洽。
10. 冲突均给出三选项；安全/伦理/合同未确认项均 `blocking=true`。
11. 已运行 verify 并生成 `verify_report.json`。
12. 无任何未来源实验室数据、评分、白板对比或伪造文件。

任何一项否：先补齐，再收尾；无法补齐则如实写入 `errors/degradations/pending_human`。

---

## 12. 最小调用示例

示例输入与示意输出见 `references/example.md`，必须标明“示例，非正式案例结果”。最小调用：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
python3 -B scripts/verify.py --input /input --output /app/output --work /app/work
```

预期：`/app/output/result.json` 状态为 `partial`，包含全部契约字段；`protocol.md` 可执行；`parameter_plan.csv`、`risk_table.csv` 非空；`verify_report.json` 出现。

---

## 13. 维护与生态

- 判定逻辑与常量优先改 `scripts/main.py` 的常数量表；保持 `result.json` 键名稳定。
- 新增题型先在 `references/checklist.md` 增加 rubric→字段映射，再改脚本。
- 不引入随机/网络/外部状态；重复运行必须结果确定。
- 复用资源：`scripts/main.py`、`scripts/verify.py`、`references/protocol_template.md`、`references/checklist.md`、`references/example.md`。
- 依赖：仅 Python ≥3.8 标准库；可选增强：`pdftotext`、`pypdf`，缺失即降级并在 `degradations` 记录。