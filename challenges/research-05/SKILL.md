---
name: research-topic-novelty-appraisal
description: 把模糊研究设想推进到可决策的选题评估——问题定义、已有工作比较、创新点识别、可行性判断四件交付一次成型，每条判断绑定材料定位与逐字引文；离线运行，只用标准库。
version: 1.0.1
license: MIT
---

# 科研选题与创新性评估（research-topic-novelty-appraisal）

## 1. 用途与边界

**做什么**：输入一个研究设想（或案例题面）+ 一批本地文献材料，输出四件彼此一致的交付，并附证据矩阵、冲突证据、研究空白与不确定性：

1. `problem_definition`：研究对象 / 关键变量 / 结局 / 比较基线 / 预期结论 / 可证伪条件，产出可检验表述；
2. `prior_work_comparison`：按 任务 / 方法 / 数据 / 评价方式 / 结论 建比较矩阵，标出不可比原因；
3. `novelty_assessment`：逐条创新陈述归类（方法 / 数据 / 场景 / 结论修正），判定是否已被材料覆盖；
4. `feasibility`：核查 数据 / 算力 / 实验条件 / 时间窗 / 人员能力，给出带条件的可行性结论与失败风险。

**不做什么**：
- 不联网、不查库。检索协议只作为**待执行计划**输出（`executed:false`）；"材料里没有"一律写成 `not_found_in_provided_materials`，绝不写成"尚无人研究"。
- 不补造文献、DOI、数值、统计量。材料未给的对象进 `pending_human`，不猜。
- 不做领域穷尽综述；不替代实验设计与统计。

**适用**：立项/开题前评估、创新点查重、可行性论证、审稿式新颖性质询。
**不适用**：需要跨库穷尽的系统综述 / Meta 分析；纯写作润色；需要生成实验数据的任务。

## 2. 调用方式

```bash
# 评估（主入口）
python3 {skill_dir}/scripts/appraise.py --input /input --output /app/output
# 结果复核（确定性校验）
python3 {skill_dir}/scripts/assess.py --check --output /app/output --input /input
```

`--input` 缺省依次探测 `/input`、`./input`；`--output` 缺省 `/app/output`，不可写时退回包内 `_out`。两个脚本都不依赖 CWD，资源用 `Path(__file__).resolve().parent` 定位。

| 产物 | 作用 |
|---|---|
| `result.json` | 结构化主结果：契约全字段回填 + 四项交付 + 证据 + 冲突/空白 + 不确定性 |
| `research_report.md` | 主产物：可读评估报告（模板 `references/report_template.md`） |
| `evidence_map.csv` | 证据表：evidence_id / source_id / locator / quote / stance / strength |
| `comparison_matrix.csv` | 已有工作比较矩阵（含纳排理由与可比性说明） |

## 3. 输入发现（语义识别，不假设键名）

1. 定位 case：`/input/case.json` → 递归 `case*.json` → `/input/task.md`（题面兜底）；case JSON 损坏时尝试修复尾逗号，仍失败则记 `case_json_unreadable` 并从 task.md 取题面。
2. 按**语义**取字段（同义键都接受）：`case_id`；主题（`research_topic/topic/title/question/题目`）；设想（`research_idea/proposal/idea/hypothesis/设想/objective`）；创新陈述（`innovation/novelty/创新点`）；时间窗（`time_window/year_range/时间窗`）；纳排（`inclusion/exclusion/criteria`）；`output_contract`（原样透传）。
3. 递归扫描材料，按扩展名识别：PDF、RIS、CSV/TSV、TXT/MD、JSON；同名内容按 sha256 去重；`case*.json` 不作为材料。
4. 图片记录到 `degradations` 但不作文字推定；材料缺失 → `gaps` + `pending_human`。

## 4. 输出契约

必含：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`research_product`、`evidence`、`claims`、`evidence_matrix`、`comparison_matrix`、`conflicts`、`gaps`、`search_protocol`、`coverage_metrics`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`tool_call_trace`、`output_contract`(回填)、`artifacts`、`consistency_check`。

**回填铁律**：`output_contract` 的每个键在顶层同名出现，键名不改，缺值 list→`[]`、dict→`{}`、其余→`null`，未知字段保留。字段级定义见 `references/output_schema.md`。

## 5. 核心流程

1. 先写 partial `result.json`，再解析材料——任何时刻中断都有合法结果；
2. 材料 → 块级文本（locator `p./para./rec./blk.`）→ 句级证据单元（术语命中 + 结果提示词）；
3. 术语抽取（拉丁词 + 中文二元组，含跨界/包含剪枝）→ 分面 → 检索协议（计划态）+ 本地覆盖统计；
4. 四项交付依次生成，逐条写 `evidence_ids` 与 `strength`；
5. 冲突检测（同一术语下极性相反的结论对）→ `conflicts`；无证据维度 → `gaps`；
6. 写 `evidence_map.csv`、`comparison_matrix.csv`、`research_report.md`；
7. finalize 覆盖 `result.json`，重算 status 与计数，退出码恒 0。

方法细节、阈值与局限见 `references/method.md`。

## 6. 质量规则（rubric → 字段/检查/产物）

| 评分要点 | 落地字段 / 检查 | 产物 |
|---|---|---|
| 四项交付齐全且一致 | `research_product` 四键非空；`consistency_check.four_deliverables_present` | report §1–§4 |
| 比较对象选对、文献真实 | `sources[].inclusion_reason` 逐条纳排理由；来源仅来自实际文件 | comparison_matrix.csv |
| 创新点是否被覆盖 | `novelty_assessment.items[].coverage` + 最近来源定位与引文 | report §3 |
| 可行性前提成立 | `feasibility.premises[].status` 三分 + `blocking_premises` | report §4 |
| 六类内容覆盖 | 问题拆解/检索规划/证据/冲突/综合结论/空白，六键非空 | result.json |
| 可独立复核 | `claims[].evidence_ids` 可回查；`assess.py --check` 重放引文与契约 | --check 输出 |
| 异常处置 | `errors`/`degradations`/`pending_human` 分类记录，退出码 0 | result.json |

## 7. 证据与定位规范

- 证据 ID `E01…`：一个 source + 一个 locator + 一段**逐字** quote（空白折叠后的连续子串，≥12 字符）。
- 不改字、不拼接、不翻译后回填；quote 在原文找不到 → `assess.py --check` 报 `misses`，该条不得作为结论依据。
- `strength`：`directly_supported` / `inferred` / `insufficient`。无证据的判断写 `insufficient` 并进 `gaps`。

## 8. 冲突证据与人工确认

- 冲突不删：保留双方 quote 与定位，给 `resolution`（口径不同可并存 / 方向相反无法裁定）与 `needs_human`。
- 必须进 `pending_human` 的情形：材料互相矛盾且无法用材料内信息裁定；创新判定落在阈值灰区；可行性前提 `assumed_not_documented`；图片或扫描件无文本层；契约要求的对象在材料中不存在。

## 9. 预算与断点

目标 <60 s（样例 0.4 s）。`BUD=700 s` 软预算；接近即在 `runtime.within_budget` 记录并立即 finalize。未捕获异常写入 `errors` 后仍 finalize。

## 10. 异常降级分支

| 情形 | 检测 | 处置 | status |
|---|---|---|---|
| 无输入目录 | 路径不存在 | 写 partial + `input_dir_not_found` | `input_error` |
| case 坏 JSON | 解析失败 | 尾逗号修复；仍失败从 task.md 取题面 | `partial` |
| 材料为空 | 0 个来源 | 只输出协议与空白清单 | `insufficient_evidence` |
| PDF 无文本层 | 解压后无文本 | 记 `no_text`，标需 OCR | `partial`+pending |
| 文献过少 | <2 篇或证据 <5 | 结论降级为方向性提示 | `partial` |
| 证据冲突 | 极性相反句 | 保留双向证据 + 裁定理由 | 不变 |
| 元数据缺失 | 无年份/DOI | `纳入(缺年份)` + 元数据缺口 | 不变 |
| 输出目录不可写 | OSError | 退回包内 `_out` | `partial` |
| 判定层缺失 | `import assess` 失败 | 仅产出证据与来源 | `partial` |

## 11. 自检清单

1. `result.json` 可 `json.load`；契约键齐全且类型一致；
2. 四项交付非空，`claims[*].evidence_ids` 均指向存在的证据；
3. `evidence_map.csv` 行数 = `evidence` 条数；
4. `python3 scripts/assess.py --check --output <out> --input <in>` 输出 `pass: true`；
5. `status` 与实情一致：有缺口就不写 `ok`；
6. 报告中无材料之外的文献、数值或结论。

## 12. 最小调用示例（示例，非正式案例结果）

输入（`输入目录/case.json`，示例数据）：

```json
{"case_id": "demo-001",
 "research_topic": "示例主题：某缓释载体对候选化合物释放速率的影响",
 "research_idea": "拟提出改进载体设计方法，并首次把温度响应材料用于该化合物",
 "innovation": "首次把温度响应材料用于该化合物；改进释放速率评价方法",
 "time_window": "2018-2026",
 "output_contract": {"problem_definition": null, "prior_work_comparison": null,
                     "novelty_assessment": null, "feasibility": null, "extra_field": "keep-me"}}
```

`输入目录/materials/` 放 1 篇 md + 1 个 RIS 题录 + 1 个 CSV + 1 个 PDF 即可。调用：

```bash
python3 scripts/appraise.py --input ./mycase --output ./myout
```

示意输出（示例，非正式结果）：`src=5 ev=6 conf=1 gap=5`；`result.json` 中 `status:"ok"`、`research_product` 四键齐全、`evidence[0].locator:"rec.2.AB"`、`conflicts[0].topic_term:"释放"`；`research_report.md` 含 8 节表格；`assess.py --check` 返回 `quote_hit:"6/6", pass:true`。示例中的主题与材料均为占位内容，不代表任何真实研究结论。

## 13. 文件清单与版本

```
SKILL.md                            本文件
scripts/appraise.py     (20542 B)   主入口：输入发现、材料解析、取证、编排、落盘
scripts/assess.py       (20479 B)   判定层：四项交付/冲突/空白/协议 + 报告渲染 + --check 复核
references/output_schema.md         字段定义、枚举值、契约回填规则、locator 与 quote 规范
references/method.md                拆解/切词/阈值/前提/降级/复核方法/已知局限
references/report_template.md       报告模板（可自行改写，缺占位符时自动降级为简报）
```

版本 1.0.1；Python ≥3.9；仅标准库（`argparse, csv, hashlib, json, os, re, sys, time, zipfile, zlib, pathlib`）；无网络；无第三方硬依赖。

## 14. 维护说明

- 阈值与词表集中在 `appraise.py` 顶部常量（`NH/NL` 覆盖阈值、`POS/NEG` 极性、`FUNC` 功能字、`PR` 前提线索、`FLD` 比较字段），调参不改接口。
- 新增材料类型：在 `EX` 注册 `suffix -> (blocks, quality)`；RIS 走 `recs_of` 专用分支。
- 改报告版式只改 `references/report_template.md`，占位符集合见 `assess.render` 的 `v` 字典。
- 变更须同步本文件 §13 版本号与 `references/output_schema.md`。
