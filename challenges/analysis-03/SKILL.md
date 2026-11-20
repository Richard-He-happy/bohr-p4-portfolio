---
name: sciviz-figure-forge
description: "把科研数据表做成可复核、可发表或可正式报告的图件：数据清洗记录、统计假设与结果、图表选型与编码理由、统计标注与图注、发表级矢量/300dpi导出、图元与源数据逐项一致性核验、result.json 契约双回显。适用输入为 /input/case.json、/input/task.md 及实际 CSV/DOCX/PDF/SQLite/图片材料；当用户要求科研可视化、画图、图表规范、期刊导出、可复跑图件时触发。脚本只是工具，最终交付物必须由 Agent 从实际材料推导、核验并落盘。"
version: 3.0.0
---

# sciviz-figure-forge

> **最高优先级**：本 Skill 不是“给一段画图建议”，也不是“跑通脚本就完成”。必须把给定数据表做成可从原始数据复算到图元的可发表图件，并保留完整计算依据、来源定位与质量检查。所有关键数字、字段语义、清洗动作、统计口径、图元映射都必须来自 `/input` 实际材料，不得按文件名、领域标签或已知数据集先验补造。

## 0. 运行红线

1. 单命令生成全量基线；后续 Agent 可增量增强，但不得删除基线产物。
2. 任何异常、缺失、脚本失败、字体缺失、解析失败都不能让进程非 0 退出；最终必须落盘合法 `/app/output/result.json`，即使 `status` 是 `partial` / `pending_human` / `failed`。
3. 只读取实际文件；PDF 必须解析真实文本，SQLite 必须读取真实表，CSV/DOCX 必须读取真实行列与段落。无法解析就记录“无法解析”，不得补造。
4. 不预置隐藏案例答案，不生成伪造的评分、金标准、benchmark 分数或未经平台提供的对照结果。
5. 所有产物必须在 `/app/output` 下；过程文件、台账、draft 放在 `/app/work` 下。
6. 关键数字、关键论断必须带 `[S#]` 来源号；来源表写入 `result.json.sources`，每个来源至少包含 `source_id`, `path`, `locator`, `quote`, `used_for`。
7. 预算默认 64 次模型请求 / 900 秒 / 单次 16384 tokens。先落盘完整 partial，再逐项核验，接近预算时立即收尾。

---

## 1. 单命令全流程入口

在 Skill 根目录（通常为 `/skills/weekly-skill`）执行：

```bash
python3 scripts/viz_skill.py --input /input --output /app/output
```

如果脚本支持工作目录参数，优先使用：

```bash
python3 scripts/viz_skill.py --input /input --output /app/output --work /app/work
```

如果 `--work` 参数不被支持，不要因此报错退出；退回第一条命令即可。脚本内部应完成 `init → build → selfcheck` 的确定性全流程，并生成所有契约文件。若脚本未生成合法产物，Agent 必须用 `scripts/vizlib.py` 或其他标准库/可用工具手写最小可行产物，仍须保证 `result.json` 合法。

---

## 2. 双路径设计：Agent 路径与确定性兜底

### 2.1 Agent 优先路径

当预算允许时，按以下顺序执行：

1. **init**：读取 `/input/case.json`、`/input/task.md`、`/input` 下全部材料；写入：
   - `/app/work/checkpoint/00_contract.json`
   - `/app/work/evidence/input_inventory.md`
2. **parse**：真实解析数据材料，写入：
   - `/app/work/evidence/raw_material_digest.md`
   - `/app/work/checkpoint/10_parsed.json`
3. **draft**：Agent 亲笔写 `/app/work/draft.json`，内容包括：
   - 选定的数据文件与来源编号；
   - 清洗规则、阈值、原因；
   - 统计假设判断与方法选择；
   - 图表类型推荐及理由；
   - 编码映射、图例、单位、误差线定义、显著性标记；
   - 目标导出规格；
   - 已知限制与待人工确认项。
4. **build**：运行单命令脚本生成全套产物。脚本读到 `/app/work/draft.json` 时，应把它视为 Agent 判断覆盖层，与台账合并；读不到 draft 时，执行确定性抽取。
5. **check**：Agent 核验 `quote / locator / 统计结果 / 图元对应`；写入 `/app/output/agent_review.json`，记录逐条 `claim_id → verified/rejected/reason`。
6. **finalize**：回填 `result.json`，完成 selfcheck。

### 2.2 确定性兜底路径

如果没有 `/app/work/draft.json`，或者预算不足，直接运行单命令脚本：

- 脚本必须用 init 台账做确定性抽取，生成本质工作稿：`cleaned.csv`, `stats.json`, `tables/`, `figures/`, `quality_report.json`, `analysis.md`, `run.log`, `result.json`；
- 每条自动抽取结论必须有逐字 `quote` 与 `locator`；
- 自动抽取而非 Agent 逐项确认的部分，必须在 `result.json.degradations` 或 `quality_report.json` 中登记 `AUTO_EXTRACT`；
- 两条路径必须产出同一套产物与同一份 `result.json` 契约结构，不得因为无 draft 就缺字段。

---

## 3. 输出契约与 result.json 结构

### 3.1 必须生成的文件

默认交付物：

```text
/app/output/result.json
/app/output/cleaned.csv
/app/output/stats.json
/app/output/tables/
/app/output/figures/
/app/output/quality_report.json
/app/output/analysis.md
/app/output/run.log
```

如果 `/input/case.json` 的 `output_contract` 要求更多文件，必须补齐；可编辑 Office/幻灯片/图形产物如存在，必须同时渲染真实 PDF 或 PNG 预览，不能只交付可编辑源文件。

### 3.2 result.json 双回显

`result.json` 必须：

- 从 `/input/case.json` 原样读取 `output_contract`，并嵌套保留在 `result.json.output_contract`；
- 同时把 `output_contract` 中要求的每个字段提升到 `result.json` 顶层，键名不变；
- 顶层必须有 `case_id`。

示例最低结构：

```json
{
  "case_id": "case_xxx",
  "status": "complete|partial|pending_human|failed",
  "cleaned_csv": "/app/output/cleaned.csv",
  "stats_json": "/app/output/stats.json",
  "tables_dir": "/app/output/tables",
  "figures_dir": "/app/output/figures",
  "quality_report": "/app/output/quality_report.json",
  "analysis_md": "/app/output/analysis.md",
  "run_log": "/app/output/run.log",
  "output_contract": {
    "cleaned_csv": "/app/output/cleaned.csv",
    "stats_json": "/app/output/stats.json",
    "tables_dir": "/app/output/tables",
    "figures_dir": "/app/output/figures",
    "quality_report": "/app/output/quality_report.json",
    "analysis_md": "/app/output/analysis.md",
    "run_log": "/app/output/run.log"
  },
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "change_records": []
}
```

如果 `/input/case.json` 没有 `output_contract`，使用上述默认契约，并在 `uncertainty` 中记录：
`"missing output_contract in /input/case.json, fallback default contract used"`。

### 3.3 诚实字段

- `status`：`complete|partial|pending_human|failed`，按真实完成度设置。
- `sources`：只列实际读取并用于推导的文件、表、段落、行列号或 sheet 名。
- `uncertainty`：列数据缺失、异常、统计假设无法判断、字体缺失、无法解析、口径冲突等。
- `pending_human`：列必须由人工确认才能发表或进入正式报告的事项。
- `errors`：列真实错误，不隐藏。
- `degradations`：列自动兜底、降级处理、非 Agent 亲核产物等。
- `change_records`：列脚本基线、Agent 核验修改、脚本修复、导出参数变更。

---

## 4. 来源编号与证据规则

1. 所有源材料先编号：`S1`, `S2`, ...；写入 `result.json.sources`。
2. `locator` 必须可复核，例如：
   - CSV：`/input/iris.csv; line 5; columns: sepal_length, species`
   - SQLite：`/input/data.sqlite; table: concrete; row_id=103`
   - DOCX：`/input/report.docx; paragraph 12`
   - PDF：`/input/paper.pdf; page 3; extracted_text`
3. 所有关键数字、清洗动作、统计结果、图元映射、单位、误差线含义、显著性标记，必须在 `analysis.md` 或 `quality_report.json` 中以 `[S#]` 标注。
4. `quality_report.json` 中建立 `source_element_map`，逐项列出：
   - 图元、数据列、统计结果；
   - 对应来源 `S#`；
   - 对应文件路径与 locator；
   - 对应 quote；
   - 校验结果 `ok|failed|limited`。
5. 不得出现“一般认为”“通常建议”等无来源结论替代实际数据结论。

---

## 5. 科研数据清洗与统计分析规则

必须使用 `references/data-quality-rules.md` 作为规则基座，但最终阈值和动作必须结合当前案例。

### 5.1 清洗

- 明确报告：行数、列数、缺失值数、重复记录数、异常值定义及数量。
- 缺失去向：删除、插补、成对删除、不处理，必须写明原因和来源；不得静默删除。
- 重复记录：按哪些列判定，保留首条还是末条，写明理由。
- 字段类型混杂、中文列名、日期时间、宽表/长表，分别判断并记录处理方式。
- 清洗结果写入 `cleaned.csv`，保留原始值、来源列、规则标记；不能只给清洗后数值而丢失依据。

### 5.2 统计判断

必须报告：

- 样本量；
- 分组与比较类型：独立/配对、单因素/多因素；
- 正态性检验、方差齐性检验结果；
- 选择的统计检验方法；
- 效应量；
- 多重比较校正；
- 误差线定义：标准差、标准误还是置信区间；
- 显著性标记星号与阈值；
- 统计不满足假设时，诚实写“未满足/未判断”，不得硬解释检验结果。

结果写入 `stats.json`；细表写入 `tables/`，并与 `analysis.md` 对应。

---

## 6. 图表选型、编码与标注规则

必须使用 `references/chart-selection.md` 判断图表类型，并用 `references/publication-export.md` 检查发表级规范。

### 6.1 图表选型

按数据类型与分析目的组合选图：

- 时间序列：趋势用折线或点线图，不用并列柱；
- 无序分类比较：条形图或点图，避免用饼图夸大构成；
- 分布：直方图、密度图、箱线图或小提琴图；
- 相关：散点图，必要时加回归线，不把相关画成分组柱；
- 多变量：分面、热图、气泡图或平行坐标；
- 构成：堆叠条形或百分比条形，避免大量类别硬塞进饼图。

必须写明推荐理由，并说明不推荐某些图型的原因。

### 6.2 编码映射

- 优先位置、长度；面积、角度、颜色只用于必要编码；
- 颜色必须色盲友好，并在灰度打印下可区分；
- 类别过多时分面或截断，不得硬塞单图；
- 对数量级过大使用 log 轴时必须明确“对数轴”并保留刻度可读；
- 双轴需说明必要性，并避免制造虚假相关；
- 量纲差异大时优先多面板或标准化，不默认双轴。

### 6.3 标注与图注

每张图必须有：

- 坐标轴标目、单位、刻度；
- 图例与系列对应；
- 误差线类型；
- 显著性标记；
- 样本量与统计方法；
- 色标范围；
- 面板编号与顺序；
- 图注能独立于正文理解。

---

## 7. 发表级导出规则

优先矢量 PDF，并附至少 300 dpi 的 PNG 预览；根据任务要求可用 PDF/SVG/PNG/TIFF。

检查项：

- 字体嵌入；
- 中文字符与特殊符号不乱码；
- 单栏/双栏宽度匹配；
- 线宽不小于 0.5 pt；
- 最小字号不低于目标期刊要求；
- 无色觉障碍不可读配色；
- 面板编号、图题、图注完整；
- 如字体缺失，记录在 `pending_human` 与 `quality_report.json`，不得静默替换为乱码字形。

---

## 8. Agent 工作流

### 阶段 1：盘点与契约

读取 `/input/case.json`、`/input/task.md`，列出 `/input` 下所有文件。

产出：

- `/app/work/checkpoint/00_contract.json`
- `/app/work/evidence/input_inventory.md`

必须至少真实读取一次 case 契约与 task 要求，不能用文件名猜测。

### 阶段 2：材料解析

按文件类型解析：

- CSV/TSV：检查列名、行数、缺失、重复、类型混杂、中文列名、日期时间；
- Excel：逐 sheet 读取；
- SQLite：列出表，读取真实 schema 和表内容；
- PDF：使用可用的 PDF 文本提取；扫描件无 OCR 则记录 `unsupported_or_scanned_pdf`；
- DOCX：提取段落与表格；
- 图片：有 OCR 则用，没有则记录不可文本化。

产出：

- `/app/work/evidence/raw_material_digest.md`
- `/app/work/checkpoint/10_parsed.json`

### 阶段 3：运行脚本生成基线并立即落盘

执行单命令：

```bash
python3 scripts/viz_skill.py --input /input --output /app/output
```

检查脚本是否生成全部输出；如果部分失败，保留已生成文件，并记为 partial。

产出：

- `/app/work/checkpoint/20_baseline.json`
- 至少保留脚本产出的全部文件。

### 阶段 4：证据核验

阅读 `references/data-quality-rules.md`、`references/chart-selection.md`、`references/publication-export.md`，逐项核验脚本输出。

重点核验：

- 清洗规则是否有来源、阈值、受影响行数；
- 统计结果是否与 `cleaned.csv` 一致；
- 图型是否与数据结构匹配；
- 图上的点、误差线、显著性标记是否可追溯到源数据；
- 轴单位、图例、图注是否齐全；
- 导出格式是否可发表。

产出：

- `/app/work/evidence/verification_notes.md`
- 更新 `quality_report.json`

### 阶段 5：Agent 亲写或核验核心交付物

Agent 必须亲自确认或修改：

- `analysis.md`：数据字典、清洗规则、统计口径、图表选择理由、编码映射、图注、限制；
- `cleaned.csv`：清理规则与来源；
- `stats.json`：统计方法、误差线定义；
- `tables/`：汇总表、比较表；
- `figures/`：图像类型与可读性；
- `quality_report.json`：图元与源数据映射；
- `run.log`：追加实际执行记录。

如果脚本输出为模板空壳，必须补成真实内容；但结构化 JSON 的键结构不要随意改写，如需修正，写入 `agent_review.json` 的 `script_fixes`，并用脚本重算，不手改 JSON。

### 阶段 6：收尾自检

- `python3 -m json.tool /app/output/result.json` 必须是合法 JSON；
- `result.json` 顶层与 `output_contract` 字段一致；
- 所有输出文件存在；
- 状态诚实；
- 异常和限制已列；
- 退出码为 0。

---

## 9. 预算意识

| 阶段 | 建议请求 | 说明 |
|---|---|---|
| 盘点+解析 | 6–10 | 真实读取，不能省 |
| 脚本基线 | 2–4 | 尽早落盘完整 partial |
| 证据核验 | 10–16 | 最高分权重点 |
| 成稿与图表修正 | 14–20 | 优先 analysis、cleaned、stats、figures |
| selfcheck/回填 | 4–8 | 契约一致与合法 JSON |
| 预留兜底 | 3–6 | 解析/脚本/导出异常 |

无 draft 时，直接脚本兜底应尽量少消耗模型请求；把请求留给核验和成稿。

---

## 10. 必须避免的扣分项

1. 只给“建议使用柱状图”的文本，不产出实际图件。
2. 图件数值、轴类型、单位、误差线、显著性标记与源数据不一致。
3. 轴截断、对数轴当线性轴、饼图/双轴滥用、配色不可读。
4. 标注缺失：无单位、图例、误差线定义、样本量、统计方法、面板编号。
5. 字体未嵌入、中文乱码、分辨率不足、尺寸不符合栏宽。
6. 清洗删除缺失值或异常值却不说明，无法复跑。
7. 输出 `result.json` 缺 `case_id` / 缺 `output_contract` 字段 / 非法 JSON / 非 0 退出。
8. 伪造软件状态、科学数据、benchmark 分数、金标准或未提供的对比结果。
9. 用文件名或领域标签假设材料内容，不读取真实文件。
10. 把脚本骨架输出直接当最终结果，不核对实际来源、不写入证据。

---

## 11. 自我检查清单

最终提交前逐项确认：

- [ ] 读到了 `/input/case.json` 的 `case_id` 与 `output_contract`；
- [ ] 读到了实际数据与材料，不只是文件名；
- [ ] `/app/output` 下所有契约文件存在；
- [ ] `result.json` 顶层与 `output_contract` 字段一一对应；
- [ ] `cleaned.csv` 含原始值、来源、规则标记；
- [ ] `stats.json` 含误差线定义与统计方法；
- [ ] 每张图都有单位、图例、图注，能独立读懂；
- [ ] 每个关键数字或图元可追溯到 `S#` 与 locator；
- [ ] PDF/PNG 满足发表级导出；
- [ ] 缺失、异常、失败、待人工项已明确列出；
- [ ] 已写入 `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `change_records`；
- [ ] 最终退出码为 0。