---
name: reading-02-scientific-figure-parser
description: Parse scientific figures and tables from a case directory into verifiable structured data — axis type/ticks/units, legend-to-series mapping, digitised curves with pixel-derived error bars, literal tables, and evidence-anchored claims. Use when a task asks to read axes, extract plotted values, compare series, parse statistics or interpret a figure/table with traceable evidence.
version: 1.0.0
license: MIT
---

# 科研图表解析（reading-02）

把「一张或一组科研图表 + 原表」读成**可复核的结构化结果**：坐标轴类型/刻度/单位、图例与系列对应、
数据点与趋势、误差线/显著性/比例尺/子图编号，以及每条结论回到原图位置的证据。

本 Skill 是**Agent + 确定性工具**的分工：Agent 负责视觉判读（刻度标签、单位、图例文字、图注、
科学解释），`scripts/main.py` 负责像素结构测量、坐标标定、曲线数字化、字面表格抽取和证据校验。
不做 OCR、不联网、不用第三方库；不能读出的一律写成 `undetermined`，绝不补造。

## 1. 何时使用

触发场景（满足任一）：
- 任务要求读取图中的坐标轴、刻度、单位、图例、数据点、误差线、比例尺或子图；
- 要求把曲线/柱状/散点/光谱/显微图转成 CSV 或数值表；
- 要求"回答并给出依据"，且依据必须在图或表中；
- 输入含 `artifacts/*.png|jpg|pdf`、`material.json`、论文 PDF 或数据表。

不适用：纯写作/翻译任务；需要在没有图像的情况下推断未给出的数据（应拒绝并列出缺口）。

## 2. 运行契约（必须逐条满足）

| 项 | 要求 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下材料（图片/PDF/CSV/XLSX/DOCX/JSON） |
| 输出 | `/app/output/`：`result.json`（必需）+ `figure_structure.json` + `digitized_series.csv` + `tables.json` + `tables/<id>.csv` |
| 契约 | `result.json` 原样回填输入 `output_contract` 的**全部**键（不改名、不丢未知键、缺值 null/[]） |
| 首步 | 分析前先写一份**合法 partial** `result.json`（status=partial），结束时无条件覆盖 |
| 退出码 | 恒 0；异常写入 `errors`/`degradations`/`pending_human`，不中断 |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（用 `Path(__file__)` 定位） |
| 预算 | 单例≈900 s；本脚本单次运行通常 <5 s（纯 CPU 像素运算） |

调用（两种等价方式，任选其一执行后读取 `result.json`）：

```bash
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output --readings /app/work/readings.json
```

## 3. 输入发现（语义识别，不假设键名）

1. 读 `case.json`（缺失则递归找 `case*.json`，再缺失仍继续）；
2. 保留 `case_id` 与 `output_contract`；`task_instruction`、`organizer_supplied_scope`、
   `organizer_workorder`、`formal_inputs`、`artifacts` 等按语义读取，**不依赖固定键名**；
3. 递归扫描输入目录，按**魔数**识别类型（不用文件名/标签猜内容）；
4. 必做对象取自带 `image/figure/photo` 的清单与含 `table` 的 ID 列表；命中情况写入
   `result.coverage`，未命中写 `pending_human`，**不构造**未提供的像素或图注。

## 4. 核心流程

1. **建立骨架**：读 case → 写 partial `result.json` → 记录 `sources`（相对路径 + sha256 + 字节数）。
2. **结构测量**（脚本自动）：图框 bbox、轴脊、刻度像素位置与间距、轴内高饱和色簇、图例色块组、
   图像尺寸与缩放系数。
3. **视觉判读**（Agent 必做，写 `readings.json`）：读刻度数字与单位、轴类型（线性/对数/双轴）、
   图例文字与色块顺序、图注、子图编号、误差线/显著性/比例尺语义、科学结论。
4. **标定与数字化**（脚本）：`tick_labels` × 检测到的刻度像素 → 最小二乘标定（线性/对数自适应），
   输出 r²、每像素数据量、残差；再按系列颜色逐列取中位坐标 → `digitized_series.csv`（含 ±半像素误差）。
5. **表格**（脚本）：CSV / 内联 JSON 表逐字保留表头与单元格；`*.xlsx`、`*.docx` 仅保留文本，
   单元格不解析时写入 `degradations`。
6. **证据校验**（脚本）：`text` 引文与源文件做规范化子串比对（exact/normalized/not_found）；
   `visual` 证据校验 bbox 落在图像范围内；校验结果写 `verification`，硬失败自动把状态降为 `partial`。

## 5. `readings.json` 契约（Agent 的输入端，也是增益来源）

```json
{"figures": {"artifacts/fig1.png": {
  "figure_id": "Fig. 1", "panel": "a", "caption": "图注逐字",
  "axes": {"x": {"label": "Displacement", "unit": "mm", "scale": "linear",
                 "tick_labels": ["0","2","4","6","8"], "tick_px": [90,210,330,450,570]},
           "y": {"label": "Load", "unit": "N", "scale": "linear",
                 "tick_labels": ["0","25","50","75","100"]}},
  "legend": {"entries": [{"label": "A", "rgb": [220,30,30]}]},
  "elements": {"error_bars": "SD, n=3", "significance": "* p<0.05", "scale_bar": "50 um"},
  "series": [{"name": "A", "rgb": [220,30,30], "digitize": true, "tol": 60}]}},
 "claims": [{"claim_id":"c01","kind":"value","text":"…","readability":"directly_read",
   "evidence":{"quote":"3.2","quote_type":"text","source_id":"material.json",
               "location":{"json_pointer":"/tables/0/rows/1/1"},"read_basis":"literal cell"},
   "conditions":"specimen A"}],
 "uncertainties": [], "pending_human": []}
```

要点：`tick_px` 可省略（脚本用检测值），但顺序须与 `tick_labels` 同向——脚本会按值/像素方向自动校正
并报告 `max_rel_dev`；数量不一致时写 `calibration` 不确定性。`rgb` 取自 `figure_structure.json`
的 `color_clusters`，不要凭印象填色。

## 6. 轴与读数的科学规则（决定正确性）

| 情形 | 处理 |
|-|-|
| 刻度等距 + 无次级刻度 | 倾向线性；**不得**仅凭像素间距判定对数（十进位刻度在对数轴上等距） |
| 次级刻度间距递减 | 记为对数轴候选，需标签值支持（如 1,10,100 或 10ⁿ） |
| 双侧纵轴 | 右轴刻度单列 `y2`，禁止把两组刻度混进同一标定 |
| 单位 | 逐字保留（mV≠V，µm≠mm）；无单位写 `null` 并在 `uncertainties` 说明，**不当作无量纲** |
| 误差线 | 只有图像可读出线帽位置时才给 `y_lo/y_hi`；无图例说明则 `readability=inferred` |
| 像素读数 | 一律 `approx=true`，误差按 ±半像素 × 每像素数据量给出，禁止把 4 位有效数字当原始表值 |
| 显著性/比例尺 | 图中字形不等于实测；只记录标记位置与图注原文，换算需比例尺数值 |

## 7. 输出字段

`result.json`：`case_id`、`status`（answered/partial/insufficient_evidence/input_error，依输入契约词表）、
`result`（`figures`/`tables`/`coverage`/`counts`/`digitized_series_file`）、`claims`、
`uncertainties`、`uncertainty`、`sources`、`pending_human`、`errors`、`degradations`、`changes`、
`runtime`、`verification`、`output_contract_spec`。

每条 claim 必含：`kind`、`text`、`evidence{quote, quote_type, source_id, location, read_basis}`、
`readability`（`directly_read` / `inferred` / `undetermined`）、`conditions`。
`location` 用 `{figure|panel|bbox_px|json_pointer|page|table_id}` 之一组合，指向可复核位置。

## 8. 异常与降级

| 异常 | 行为 |
|-|-|
| 无刻度/无图框（照片、示意图） | 记 `no_axis_frame`，仍报色簇与尺寸；`traceable=false` |
| JPEG/BMP/TIFF（无标准库解码器） | 记 `degradations` + `pending_human`，请 Agent 目视读数 |
| 图像裁切/曲线越界 | bbox 限定在绘图区内；越界点不输出，写 `uncertainties` |
| 图例缺失 | 以颜色出现顺序 + 位置给候选对应，`readability=inferred` |
| 单位不明 | 单位留 `null` + `uncertainties`，不猜 |
| 过曝/曲线重叠 | 报告色簇像素数与列厚度突变；重叠区标 `undetermined` |
| 表格单位在表头/脚注 | 表头逐字保留，脚注进 `uncertainties` |
| 材料未给（只在正文提及） | 列入 `coverage.missing_*` 与 `pending_human`，不生成像素或数值 |

## 9. 自检（提交前逐项）

- `result.json` 可 `json.loads`，契约键全部存在，`case_id` 原样；
- `status` 与实际完成度一致；部分完成必须是 `partial` 而非 `answered`；
- 每条 claim 的 `quote` 能在 `source_id` 中命中（`text`）或 bbox 在图像内（`visual`）；
- 数值带单位与精度，像素读数标 `approx` 与误差；
- `uncertainties` 覆盖未报告项；`pending_human` 给出可执行的人工动作；
- 输入为空/损坏时仍产出合法 `result.json` 且退出码 0。

## 10. 最小调用示例（示例，非正式案例结果）

输入（示例）：`case.json`（`case_id: TEST-C01`，`output_contract` 5 键 + 1 个未知键）+
`artifacts/fig1.png`（600×420 合成折线图，红/蓝两条曲线，图例两色块）+ `material.json`（表 T01）+
`readings.json`（x: 0–8 mm / y: 0–100 N，系列 A 数字化）。

```bash
python3 submission/scripts/main.py --input ./input --output ./out
# -> {"status":"partial","output":"./out","errors":1,"degradations":0,"claims":3}
```

该示例运行的真实产出：

| 产物 | 内容 |
|-|-|
| `result.json` | 契约 6 键全在（含未知键 `extra_field_unknown_vendor: null`）；`status=partial` |
| `figure_structure.json` | 图框 `[90,40,570,359]`；x 刻度 5 个、y 刻度 4 个；图例色块 bbox `[110,61,149,82]`，顺序红→蓝 |
| 标定 | x：linear，r²=1.0，0.0167 mm/px；y：linear，r²=1.0，0.3125 N/px |
| `digitized_series.csv` | 479 行；首点 x=0 → y≈96.9 N，末点 x≈7.98 → y≈15.6 N（与绘图公式一致） |
| `tables.json` | T01：`Specimen / Modulus (GPa) / Strength (MPa)`，2 行逐字 |
| `verification` | 1 条硬失败：一条引文在源文件中找不到，状态因此降为 `partial`（这是设计行为） |

## 11. 文件清单与版本

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（入口） |
| `scripts/main.py` | 流程编排：发现、契约、标定、数字化、表格、证据校验、finalize |
| `scripts/parsekit.py` | 纯像素引擎：PNG 解码、图框/刻度/色簇/图例、最小二乘标定、曲线追踪 |
| `references/schema.md` | `readings.json` 与 `result.json` 字段定义、误差口径 |
| `references/playbook.md` | 图型判读手册：轴类型、误差线、显著性、比例尺、子图、异常处置 |
| `references/checklist.md` | rubric→字段对照、标定公式、自检与评分口径 |

版本 1.0.0；Python ≥3.8；无外部依赖。维护：改动字段时同步 `references/schema.md` 与本文件第 7 节。
