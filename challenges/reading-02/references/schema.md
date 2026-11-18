# 字段定义与误差口径（reading-02）

本文件是 `readings.json`（Agent 输入）与 `result.json`（最终交付）的字段契约。
所有坐标单位为**原图像素**（左上角为原点，x 右增，y 下增）。

## 1. `readings.json`（Agent 视觉判读结果）

| 字段 | 类型 | 必填 | 说明 |
|-|-|-|-|
| `figures` | object | 是 | 键为 `source_id`（相对 `/input` 的路径）或文件名 |
| `figures.<sid>.figure_id` | string | 否 | 如 `"Fig. 2"`；与图注一致 |
| `figures.<sid>.panel` | string | 否 | 子图编号，如 `"a"`；**不得跨子图错配** |
| `figures.<sid>.caption` | string | 否 | 图注逐字（可截取，但不得改写数值） |
| `axes.x/.y/.y2` | object | 是（有坐标轴时） | `label`、`unit`、`scale`(`linear`\|`log`\|`auto`)、`tick_labels`、可选 `tick_px` |
| `legend.entries[]` | array | 否 | `label` + `rgb`；顺序须与图中**自上而下**一致 |
| `elements` | object | 否 | `error_bars` / `significance` / `scale_bar` / `n` 等语义描述 |
| `series[]` | array | 否 | `name`、`rgb`、`digitize`(bool)、`tol`(默认 60)、可选 `visual_points` |
| `claims[]` | array | 是 | 见 §3 |
| `uncertainties[]` | array | 否 | 未报告、冲突、需人工复核项 |
| `pending_human[]` | array | 否 | `{item, why, action}`，`action` 必须是可执行动作 |

`tick_labels` 与 `tick_px` 顺序必须**同向**（通常自下而上或自左而右）。脚本按
「值趋势 × 像素趋势」自动校正方向；数量不一致时在 `result.figures.<sid>.calibration_notes`
记录 `label/pixel count mismatch`，并按轴起点配对前 n 对。

## 2. `result.json`

| 字段 | 说明 |
|-|-|
| `case_id` | 输入原样 |
| `status` | 契约词表优先（`answered`/`ok` 视为成功）；部分完成必须 `partial` |
| `result.figures.<sid>` | `figure_id`、`panel`、`caption`、`image_px`、`plot_box_px`、`spines_px`、`ticks_px`、`spacing`、`axes`、`color_clusters`、`legend_candidates`、`elements`、`digitized`、`traceable`、`warnings`、`calibration_notes` |
| `result.tables[]` | `table_id`、`source_id`、`columns`、`n_rows`（逐字，不重排、不换列） |
| `result.coverage` | `images[]`（含 `declared`）、`tables[]`（`resolved`）、`missing_images`、`missing_tables` |
| `result.counts` | 必做图数、已解析图数、缺失图数、抽表数、必做表数、已定位表数、claim 数、数字化点数 |
| `claims[]` | 见 §3 |
| `uncertainties[]` | 未报告/冲突/无法判断/需人工 |
| `uncertainty` | 概况对象：`visual_readings`、`missing_materials`、`scope`、`counts`、`fatal` |
| `sources[]` | `source_id`、`kind`、`bytes`、`sha256`、`path` |
| `pending_human[]` | 人工接管位置与动作 |
| `errors[]` / `degradations[]` / `changes[]` | 失败、降级、变更记录 |
| `runtime` | skill 版本、Python 版本、输入/输出目录、耗时 |
| `verification` | `n_claims`、`n_contract_keys`、`issues`、`claim_checks`、`hard_failures` |
| `output_contract_spec` | 输入契约原文（键→原描述），便于对照 |

## 3. claim 结构

```json
{"claim_id":"c01","kind":"value|trend|element|comparison|caption_fact|table_cell",
 "text":"结论句，数值与单位逐字","readability":"directly_read|inferred|undetermined",
 "conditions":"适用条件（系列、子图、样本、扫描速率等）",
 "evidence":{"quote":"逐字文本或视觉描述","quote_type":"text|visual",
             "source_id":"相对路径","location":{...},"read_basis":"读取依据"}}
```

`location` 允许组合：`figure`、`panel`、`bbox_px:[x0,y0,x1,y1]`、`json_pointer`、`page`、`table_id`、`row`。

## 4. 误差口径

| 量 | 口径 |
|-|-|
| 像素量化 | 分析图可能被 stride 降采样，`analysis_scale=s` ⇒ 坐标误差 ±s px |
| 数据误差 | `err = 0.5 × s × |slope|`（每像素数据量）；写入 `err_x_data` / `err_y_data` |
| 标定残差 | 逐刻度相对偏差 → `max_rel_dev`；`r2` 与 `alternatives` 一并报告 |
| 对数轴 | 残差按 `log10(value)` 拟合；`value_per_px` 置 `null`，给出 `px_decade` |
| 线宽/误差线 | 每列像素厚度 `px_thickness`；`y_lo`/`y_hi` 取该列上下边界，代表线帽或厚度范围 |
| 有效数字 | `sig(x,4)`；像素读数**不得**写成原始表值，`approx=true` 必须保留 |

## 5. 数字化 CSV 列

`figure, panel, series, x, y, y_lo, y_hi, x_unit, y_unit, err_x_data, err_y_data, x_px, y_px, approx`

同一文件内多图多系列按 `figure/series` 区分；`x_px`/`y_px` 保留原图像素坐标，供逐点回查。
