---
name: sciviz-figure-forge
description: 把一份科研数据表做成可直接用于投稿或正式报告的图件：清洗记录 + 图表选型理由 + 编码映射 + 统计标注与图注 + 发表级矢量导出 + 图元与原数据逐项一致性校验。输入 /input/case.json 与数据材料，输出 /app/output 下的 result.json、cleaned.csv、stats.json、tables/、figures/、quality_report.json、analysis.md、run.log。当用户要求「画图/可视化/出图/figures/plots/图表规范/期刊导出」并提供了数据或数据路径时使用。脚本只是工具，最终交付物必须由 Harness Agent 亲自读材料、推导、撰写和制作。
version: 2.0.0
---

# sciviz-figure-forge（科研数据可视化）

> **最高优先级声明**：`scripts/viz_skill.py` 和 `scripts/vizlib.py` 只是工具。Harness Agent 必须亲自读取 `/input/case.json`、`/input/task.md` 与全部科研材料，真实解析内容，独立推导清洗、统计、图表选择、编码、标注和导出决策；禁止把脚本骨架、模板或未核验输出直接当最终成品。最终交付物必须体现 Agent 的推导与检查，而不是“脚本跑通了就当完成”。

## 1. 用途与边界

### 1.1 用途
- 将科研数据表转化为可复核、可发表或可正式报告的图表。
- 输出数据清洗记录、统计结果、图表选型理由、编码映射、统计标注与图注、发表级导出、质量检查。
- 强调从源数据到图件的完整可复跑链，而不是只画图或只给建议。

### 1.2 适用边界
- 适用于给定数据表或可解析数据材料，并进行数据可视化、统计标注、图表规范检查、发表级导出。
- 不负责实验设计、统计方法创新、论文写作、图像后期美化。
- 若材料不足、字段语义不明、统计口径无法判断，必须诚实标注 `pending_human` 或 `limitations`，不得补造。

### 1.3 输入
- `/input/case.json`：案例标识、`output_contract`、材料路径、任务约束等。
- `/input/task.md`：任务说明、评分维度、Runtime contract。
- `/input` 下的实际材料：CSV、DOCX、PDF、SQLite、图片等。

### 1.4 输出
- `/app/output/result.json`
- `/app/output/cleaned.csv`
- `/app/output/stats.json`
- `/app/output/tables/*.csv`
- `/app/output/figures/*`
- `/app/output/quality_report.json`
- `/app/output/analysis.md`
- `/app/output/run.log`
- 可编辑 Office/幻灯片/图形产物如存在，必须额外给出真实渲染的 PDF/PNG 预览。

## 2. 调用方式

```bash
python3 scripts/viz_skill.py --help
python3 scripts/viz_skill.py --input /input --output /app/output
```

`--help` 输出只用于确认参数和脚本能力，不能替代实际阅读脚本行为或实际材料解析。

## 3. 输出契约与 result.json

### 3.1 必须落盘的文件
- `result.json`：总结果，包含 `case_id` 和 `output_contract` 中的全部字段，键名不改。
- `cleaned.csv`：清洗后数据，保留原始值与来源定位，必要时含变换列和规则标记。
- `stats.json`：统计结果、统计方法、样本量、缺失/异常/重复处理说明、误差线定义、显著性标记定义。
- `tables/`：汇总表、成对比较、效应量等可复核表格。
- `figures/`：图件；优先 PDF/PNG，满足可发表导出要求。
- `quality_report.json`：质量检查、图元与源数据一致性校验、失败项、限制项。
- `analysis.md`：数据字典、清洗规则、图表选型理由、编码映射、图注、可复跑记录。
- `run.log`：实际运行记录，含主要命令、脚本输出、错误与恢复。

### 3.2 result.json 最低结构
必须从 `/input/case.json` 读取 `output_contract`；如果存在：
- 在 `result.json` 中**原样保留** `output_contract` 对象；
- 将 `output_contract` 中要求的字段**同时提升到顶层**，键名不改；
- 顶层必须还要有 `case_id`。

如果 `/input/case.json` 缺少 `output_contract`，使用本 Skill 默认契约字段：
```json
{
  "case_id": "unknown_case_id_from_task_or_filename",
  "status": "partial",
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
  "uncertainty": ["missing output_contract in /input/case.json"],
  "change_records": ["fallback default output contract used"],
  "deliverables": {}
}
```

### 3.3 诚实字段
- `status`：`complete` / `partial` / `pending_human` / `failed`。
- `sources`：只写实际读取过的文件、路径、段落或表名，不写未读取的来源。
- `uncertainty`：列出数据缺失、统计假设无法判断、字体缺失、无法解析等不确定性。
- `change_records`：记录 Agent 对基线输出、清洗规则、图表、统计结果的核验与修改。
- 不得编造数据、引用、分数、软件状态或基准结果。

## 4. 执行流程

### 步骤 1：盘点输入与契约
**输入**：`/input/case.json`、`/input/task.md`、`/input` 目录。

**动作**：
- 读取 `/input/case.json`，提取 `case_id`、`output_contract`、材料路径、任务约束。
- 读取 `/input/task.md`，确认评分维度与 Runtime contract。
- 列出 `/input` 下所有文件，区分数据文件、材料、图片、数据库等。
- 将契约和文件清单写入 `/app/work/checkpoint/00_contract.json` 与 `/app/work/evidence/input_inventory.md`。
- 至少请求 1 次读取 `case.json` 和 `task.md`，不能只用文件名猜测内容。

**输出**：输入清单、`case_id`、`output_contract`、材料路径、失败分支记录。

**失败分支**：
- `/input/case.json` 缺失：读取 `task.md` 和目录列表，尝试推断 `case_id`，使用默认输出契约，状态标记 `pending_human`。
- 材料缺失：继续产出合法 `result.json`，在 `uncertainty` 和 `limitations` 中说明。
- 任何失败都不得让进程异常退出；最终退出码应为 0。

### 步骤 2：真实解析科研材料
**输入**：步骤 1 的材料路径与文件类型。

**动作**：
- CSV/TSV：用 `pandas` 读取，检查列名、行数、缺失值、重复行、字段类型混杂、中文列名、日期时间列。
- Excel：逐 sheet 读取，不要只读默认 sheet。
- SQLite：连接数据库，列出表并读取相关表内容。
- PDF：使用预装的 `pdf-text-tool` 或等效文本提取工具读取真实文本；不要使用文件名或领域标签充当内容；若为扫描版且无 OCR，则记录 `unsupported_or_scanned_pdf`。
- DOCX：用 `python-docx` 或解包 XML 提取段落和表格。
- 图片：若环境提供 OCR 工具则进行 OCR，否则记录图片无法文本化。
- 提取：原始值、单位、样本量、误差线定义、显著性标记、统计方法、类别水平、时间粒度、数据口径。
- 将原始快照写入 `/app/work/evidence/raw_material_digest.md`。
- 同时写 `/app/work/checkpoint/10_parsed.json`，保存已解析表名、行数、字段、缺失情况。

**输出**：解析后的数据结构、原始值快照、字段语义、限制列表。

**失败分支**：
- 单个文件解析失败：记录准确错误和文件路径，继续解析其他文件。
- 所有数据材料不可用：不编造数据，生成带 `status: "failed"` 或 `status: "pending_human"` 的 `result.json`，仍写出 `/app/output` 其他空但合法的占位文件。
- 字体缺失、编码错误：记录限制，不静默替换为错误字符。

### 步骤 3：运行自带脚本产出完整基线并先落盘 partial
**输入**：步骤 1 的契约，步骤 2 的解析结果。

**动作**：
- 先运行：
  ```bash
  python3 scripts/viz_skill.py --input /input --output /app/output
  ```
- 检查是否生成基线全套文件：
  - `result.json`
  - `cleaned.csv`
  - `stats.json`
  - `tables/`
  - `figures/`
  - `quality_report.json`
  - `analysis.md`
  - `run.log`
- 立即保留所有基线产物；后续增强只能在此基础上增补，不得删除或清空。
- 将基线 `result.json` 的字段与 `/input/case.json` 的 `output_contract` 做第一次核对。
- 如果脚本产出明显是模板或空壳，记录到 `change_records`，并在后续步骤中由 Agent 亲自补全。

**输出**：完整基线文件、初步核对记录、`/app/work/checkpoint/20_baseline.json`。

**失败分支**：
- 脚本运行失败：写 `/app/work/checkpoint/20_baseline_failed.json`，记录错误输出；继续使用 `scripts/vizlib.py` 或 matplotlib 手动生成最小可行产物。
- 脚本部分失败：保留已生成文件，未生成的文件进入 `pending_human` 或 `partial` 列表。
- 脚本未生成 `result.json`：Agent 必须手写合法 `result.json`，不得以脚本失败为由退出。

### 步骤 4：构建并核对证据
**输入**：步骤 2 的原始快照，步骤 3 的基线产物，`references/` 下的规则文件。

**动作**：
- 使用 `references/data-quality-rules.md` 核对：
  - 缺失值、异常值、重复记录如何处理；
  - 是否有静默删除、静默填补；
  - 清洗规则是否写明来源和阈值。
- 使用 `references/chart-selection.md` 核对：
  - 数据类型：连续、分类、时间序列、多变量、分组比较；
  - 分析目的：分布、比较、相关、趋势、构成；
  - 推荐图型理由，不推荐图型原因；
  - 编码方式：位置、长度、颜色、形状、分面；
  - 类别过多、量纲差异、双轴、对数变换等处理。
- 使用 `references/publication-export.md` 核对：
  - 矢量导出、300 dpi 以上位图；
  - 字体嵌入、中文与特殊符号；
  - 单栏/双栏宽度、线宽、最小字号；
  - 色盲友好与灰度可辨配色。
- 核验统计假设：正态性、方差齐性、配对或非配对、多重比较、误差线是标准差/标准误/置信区间。
- 对每个图元做“源数据 → 图元”对应关系核查，把结果写入 `/app/work/evidence/verification_notes.md`。
- 更新 `quality_report.json`：逐项列出通过/失败/限制。

**输出**：证据核对记录，更新的 `quality_report.json`，明确的核验问题列表。

**失败分支**：
- 证据不足或口径冲突：在 `quality_report.json` 和 `result.json` 中标记 `pending_human` 或 `conflicts`，不强行下结论。
- 图表类型与数据结构冲突：修正图型；若无法修正，保留原因并降级为 `partial`。
- 统计假设无法判断：明确写“未满足/未判断”，不报告未经证明的检验结果。

### 步骤 5：Agent 亲自产出完整交付物
**输入**：步骤 3 的基线，步骤 4 的核验记录。

**动作**：
- 由 Agent 亲自撰写或校改：
  - `analysis.md`：数据字典、清洗规则、统计口径、图表选型理由、编码映射、图注、限制；
  - `cleaned.csv`：保留原始值、来源定位、规则标记，不删除难以说明的记录；
  - `stats.json`：样本量、缺失/异常/重复数量、统计结果、误差线定义、显著性标记定义；
  - `tables/`：汇总表、成对比较、效应量等；
  - `figures/`：修正图表类型、坐标轴标目、单位、图例、误差线、显著性标记、色标范围、面板编号；
  - `quality_report.json`：图元与源数据对应关系、失败项、修复记录；
  - `run.log`：追加本次 Agent 实际执行的操作和错误恢复。
- 若存在可编辑 Office/幻灯片/图形产物，必须渲染真实 PDF/PNG 预览并放入 `/app/output`。
- 不把 `scripts/viz_skill.py` 的骨架输出当作成品；必须确认每个字段和图片元素来自实际材料内容。
- 若预算不足，优先保证核心图件、`cleaned.csv`、`stats.json`、`analysis.md` 和合法 `result.json` 完成，再补充其他文件。

**输出**：完整或 partial 的最终交付物。

**失败分支**：
- 时间或请求不足：保留已完成的 partial 文件，明确列出缺失项。
- 图表无法正确生成：输出可读的最小图，并在 `quality_report.json` 和 `result.json` 中标记问题。
- 字体缺失导致渲染异常：标记 `pending_human`，并描述需要人工安装的字体。

### 步骤 6：按 rubric 自检
**输入**：步骤 5 的最终产物。

**动作**：
- 逐项检查第 7 节表格中的 rubric 维度。
- 检查 `result.json` 是否是合法 JSON。
- 检查 `result.json` 是否包含 `case_id` 和原 `output_contract` 全部字段。
- 检查所有输出文件是否真实存在于 `/app/output`。
- 检查图表坐标轴、单位、图例、误差线、显著性标记是否与源数据一致。
- 检查图注是否可独立读懂。
- 检查清洗和统计口径是否可复跑。
- 检查是否诚实标注 `status`、`sources`、`uncertainty`、`change_records`。

**输出**：自查记录，写入 `/app/work/checkpoint/60_selfcheck.json`。

**失败分支**：
- 缺字段：先补齐再收尾；无法补齐则 `status: "partial"` 并列出缺失项。
- 发现编造或不一致：立即修正；无法修正则明确标记 `pending_human`。

### 步骤 7：回填并最终固化 result.json
**输入**：所有核验与产出结果。

**动作**：
- 将 `case_id` 写入顶层。
- 将 `output_contract` 字段逐一回填。
- 设置真实 `status`。
- 写 `sources`：只写实际读取和用于推断的文件路径/表名/段落。
- 写 `uncertainty`：列出所有已知限制。
- 写 `change_records`：记录脚本基线、Agent 修改、核验结果。
- 写 `reviewed_by_agent`：标记关键产出已由 Agent 亲自核验。
- 最终检查退出码为 0，即使 `status` 为 `partial` / `pending_human` / `failed`，也要产出合法 `result.json`。

**输出**：最终 `/app/output/result.json`。

**失败分支**：
- 无法写入 `/app/output`：记录到 stderr，但不要覆盖已完成文件；若连 `result.json` 也无法写，仍必须尝试用最小内容写入 `/app/output/result.json` 并保持退出码 0。

## 5. 预算策略

总预算：64 次模型请求、900 秒、单次响应 16384 tokens。

### 5.1 建议分配
| 阶段 | 建议请求数 | 说明 |
|---|---|---|
| 步骤 1-2：盘点与解析材料 | 6-10 | 必须真实读取，不能省 |
| 步骤 3：跑脚本并检查基线 | 4-8 | 先落盘完整基线，防止最后丢产物 |
| 步骤 4：核对证据 | 10-16 | 高权重，花最多请求做正确性核验 |
| 步骤 5：产出/修改最终交付物 | 14-20 | 优先图、表、analysis.md、result.json |
| 步骤 6-7：自检与回填 | 4-8 | 必要性检查，不能省 |
| 预留与兜底 | 3-6 | 处理解析失败、脚本失败、字体缺失 |

### 5.2 优先顺序
1. **必须完成**：读输入、解析材料、跑脚本基线、写合法 `result.json`。
2. **优先完成**：核心图件、清洗表、统计结果、图注、质量核验。
3. **可增量增强**：更多 tables、更多图、更完整的 `analysis.md`。
4. **可跳过低优先级**：重复导出多格式、冗长创新说明、非必要装饰。

### 5.3 落盘策略
- 每完成一个阶段就写 checkpoint 到 `/