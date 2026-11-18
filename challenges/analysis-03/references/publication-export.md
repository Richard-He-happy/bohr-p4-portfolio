# 发表级导出、配色与图注规范（publication-export）

## 1. 导出规格档（`--journal` 可选值）

| profile | 单栏宽 mm | 双栏宽 mm | 字号 pt | 轴线 mm | 数据线 mm | 位图 dpi | 允许格式 |
|---|---|---|---|---|---|---|---|
| nature | 89 | 183 | 5–7 | 0.25 | 0.5 | 300/600 | SVG/PDF/EPS/TIFF |
| science | 55 | 120 | 5–7 | 0.25 | 0.5 | 300/600 | PDF/EPS/TIFF |
| cell | 85 | 174 | 6–8 | 0.35 | 0.75 | 300/1000 | PDF/EPS/AI |
| ieee | 88.9 | 181 | 8 | 0.25 | 0.6 | 600 | PDF/EPS(矢量优先) |
| report | 160 | 170 | 9–11 | 0.3 | 0.6 | 300 | SVG/PDF/PNG |
| screen | 180 | 180 | 9–12 | 0.3 | 0.7 | 150 | SVG/PNG |

通则：矢量（SVG）始终输出，作为主交付；位图/PDF 为可选增强（需 matplotlib，缺失时降级并写 `degradations`）。**最小字号 5 pt**（−1 pt 容差，低于 5 pt 记 `checks` 失败）；线宽不得 <0.25 mm；画布尺寸与栏宽偏差 ≤1.0 mm。

## 2. 字体与中文

- SVG 中文字以真实文本写入，`font-family` 依次尝试：`Noto Sans CJK SC, Source Han Sans SC, WenQuanYi Micro Hei, SimHei, Helvetica, Arial, sans-serif`，由渲染器回退，不内嵌字体文件（避免二进制与许可问题）。
- 位图渲染前探测 CJK 字体；无可用 CJK 字体且标签含中文时**不输出位图**，降级为 SVG + 数据表（`degradations: ["no_cjk_font_for_raster"]`），避免输出方框豆腐字。
- 特殊符号（µ、±、×、°、⁻¹、Δ、α）以 Unicode 写入；上下标用 `<tspan baseline-shift>` 或直接 Unicode（如 mm²、µm）。

## 3. 配色与可读性判据（脚本 `accessibility()` 实际计算）

调色板：Okabe–Ito 色盲友好 7 色 `#0072B2 #D55E00 #009E73 #CC79A7 #E69F00 #56B4E9 #666666`，顺序按相对亮度错开排列。

判据（全部实算并写入 `accessibility_checks`）：

1. **灰度可分**：任意两系列在 sRGB 相对亮度 L 上 |ΔL| ≥ 0.10，或二者填充纹理不同。
2. **色觉障碍可分**：用 Machado (2009) 严重度 1.0 的 deuteranopia / protanopia / tritanopia 线性矩阵模拟后，|ΔL| ≥ 0.08（任一模态不满足即告警）。
3. **与背景对比**：线/点相对白底对比度 ≥ 3:1（WCAG 非文本阈值）。
4. **同一通道**：类别需同时具备颜色 + 形状/纹理两个通道（类别 >4 强制）。

未通过时的处置：改用下一套调色板 → 仍不通过则追加纹理（hatch）→ 再不行降为分面/分面板，并把处置记录到 `changes`。判据不改变数据，只改变编码。

## 4. 图注模板（脚本 `caption()` 生成，禁止留空）

```
图 {n}. {图题：变量 A 对 变量 B 的 {目的}}。{图型说明}。
{误差与统计}：数据为 {mean ± SD/SE/95% CI}（n = {每类 n}，共 {N} 行；
{分组说明}）。{检验}：{方法}，{p 值与符号}；多重比较未校正/已用 {方法} 校正。
{编码说明}：{颜色/形状/纹理} 表示 {系列}；{色标} 范围 {vmin}–{vmax}（{单位}）。
{坐标轴说明}：x 轴为 {类型}{log10 若适用}，y 轴为 {类型}{log10 若适用}，单位 {unit}。
{数据处理}：剔除 {n_missing} 个缺失与 {n_dup} 条重复记录（详见 quality_report.json）。
数据来源：{文件名}{sheet/表}{行号范围}。绘制：{脚本名} v{ver}，{profile} 规格 {w}×{h} mm，{格式}。
```

要求：图注可脱离正文独立读懂；每个数字（n、p、范围、单位）必须能追到 `stats.json` / `chart_data.csv` / 源文件行号；无证据的数字用 `未确定` 占位并进 `pending_human`。

## 5. 一致性校验清单（脚本 `verify()` 实际执行，逐项写入 `checks`）

| id | 检查 | 判据 |
|---|---|---|
| C01 | 轴范围覆盖数据 | 全部绘图值 ∈ 轴范围，裁切点计数 = 0 或有记录 |
| C02 | 柱高/点坐标 = 源数据聚合 | 与 `cleaned.csv` 复算值差 ≤1e-9（相对 1e-6） |
| C03 | 轴标题含单位 | 源列名/字典给出的单位出现在轴标题 |
| C04 | 图注 n = 实际使用行数 | 相等 |
| C05 | 图例系列数 = 实际绘制系列数 | 相等 |
| C06 | 字号与画布 | ≥5 pt（profile 下限 ±1），画布宽与 profile 差 ≤1 mm |
| C07 | 显著性标记与 p 值一致 | 仅 p<α 有括号，符号与阈值匹配 |
| C08 | 色标范围 = 数据 min/max | 相等（保留 3 位有效数字） |
| C09 | 类别无静默截断 | 绘制类别数 = 数据类别数，或聚合记录在 `changes` |
| C10 | 误差线语义已声明 | `err_kind` ∈ {sd,se,ci95,iqr} 且出现在图注 |

任一失败：不修改数据、不隐藏，写入 `checks[].passed=false` 与 `pending_human` 说明；状态降为 `partial`。
