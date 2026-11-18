# rubric 对照、标定公式与自检（reading-02）

## 1. rubric → 字段 / 检查 / 产物

| 评分维度 | 得分点 | 本 Skill 的落点 | 可核验产物 |
|-|-|-|-|
| 实际效果 40 | 任务完成度 15 | 必做图/表全覆盖（`coverage`），`status` 如实 | `result.json`、`figure_structure.json` |
| | 结果正确性 15 | 轴类型/刻度/单位/图例逐项记录；标定 r²、残差公开 | `axes.*`（`scale`/`r2`/`max_rel_dev`）、`legend_candidates` |
| | 结果完整性 5 | 坐标轴、图例、系列、误差线、显著性、比例尺、子图、图注字段齐备 | `result.figures.*`、`elements` |
| | 结果可核验性 5 | 每条 claim 带 `quote`+`locator`；`verification` 给逐条命中结果 | `claims`、`verification.claim_checks` |
| 使用增益 25 | 质量增益 15 | 像素标定 + 逐列中位追踪替代目测；与基础 Agent 的读数误差可直接对比 | `digitized_series.csv`（含 `x_px/y_px` 回查） |
| | 效率增益 5 | 单命令完成结构测量+标定+抽表，无需手工量取 | `runtime.duration_s` |
| | 增益可验证性 5 | 同一 `readings.json` 可重复运行；结果含 r²/残差/误差列 | 重复运行 `verify` 输出一致 |
| 创新增益 15 | 新增能力 5 | 轴类型判别、像素→数据标定、图例色块自动分组、误差带提取 | `calibrate`、`legend_candidates` |
| | 方法改进 5 | Agent 判读 + 机器标定的多模态交叉校验（标签数 vs 检测刻度数） | `calibration_notes` |
| | 创新证据 5 | 标定残差、r²、替代拟合（linear/log）全部留痕 | `axes.*.alternatives` |
| 可靠体验 10 | 调用与易用性 3 | 两个位置参数；`--help` 自解释 | `python3 main.py --help` |
| | 运行稳定性 4 | 恒退出 0；先写 partial；单图失败不影响其他 | `errors`、`degradations` |
| | 异常处理 3 | 无刻度/裁切/缺图例/单位不明/过曝/重叠逐项有分支 | `warnings`、`uncertainties` |
| 生态贡献 10 | 文档完整性 3 | SKILL.md + 3 份 references | 本节与 schema/playbook |
| | 资源可复用性 4 | 标定与数字化模块可在新图上直接复用 | `scripts/parsekit.py` 纯函数 |
| | 分享推广价值 3 | 图型手册 + 异常矩阵 + 误差口径可对外复用 | `references/playbook.md` |

## 2. 标定公式

线性：`value = a·px + b`（最小二乘；`a` 为每像素数据量）

- `sxx = Σ(pᵢ−p̄)²`，`a = Σ(pᵢ−p̄)(vᵢ−v̄)/sxx`，`b = v̄ − a·p̄`
- `R² = 1 − SS_res/SS_tot`；`max_rel_dev = max |v̂ᵢ−vᵢ|/|vᵢ|`

对数：先 `t = log₁₀ v`，拟合 `t = a·px + b`，反解 `v = 10^(a·px+b)`；报告 `px_decade = |1/a|`。

误差：`err_data = 0.5 · s · |a|`（`s` 为降采样步长，未降采样时 `s=1`）。

轴方向：若 `(v_last−v_first)·(px_last−px_first) < 0`，反序 `px` 再配对（纵轴惯例）。

判定优先级：`max_rel_dev` 小者优先；两种尺度均 `R² ≥ 0.9995` 且偏差 ≤1% 时置 `ambiguous=true`，
必须由刻度标签值（而非像素间距）裁决。

## 3. 提交前自检清单

1. `python3 -B scripts/main.py --help` 退出码 0；
2. 最小输入试跑：`result.json` 可解析、契约键齐全、`coverage`/`counts` 与材料一致；
3. 空输入：仍生成 `result.json`（`status=insufficient_evidence` 或 `input_error`），退出码 0；
4. 坏 JSON（`case.json` 非法）：`errors` 记录原因，`status=input_error`，退出码 0；
5. 重复运行两次，`digitized_series.csv` 逐字节一致（确定性）；
6. 任何 `claims[].evidence.quote` 都能在 `source_id` 里命中，或在图像 bbox 内；
7. `uncertainties` 覆盖：未报告误差线、单位缺失、图被裁切、图例缺失；
8. `pending_human` 每条都有可执行 `action`；
9. 无 `__pycache__`/`.pyc`；无预制答案；示例均标注「示例」。

## 4. 常见失分与规避

| 失分点 | 规避 |
|-|-|
| 把图像读数写成精确表值 | 保留 `approx=true` 与 `err_*_data` |
| 对数轴当线性 | 先看次级刻度/标签 10ⁿ，再判尺度 |
| 图例与系列错配 | 用 `legend_candidates.entries_top_to_bottom` 对齐 `rgb`，不靠记忆 |
| 未给材料被当成缺项 | `coverage.missing_*` + `pending_human`，并声明「非未完成工作」 |
| 只给文字总结 | 必须落 `digitized_series.csv`、`tables.json`、`figure_structure.json` |
| 样本/条件丢在括号外 | `conditions` 字段绑定系列与子图 |
