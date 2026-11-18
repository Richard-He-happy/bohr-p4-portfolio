# 图面规范与导出预设（style / export presets）

本文件是 `scripts/render.py` 中 `STY` 与导出链的说明与可复用清单。改预设时两处同步。

## 1. 画布

| 项 | 默认 | 说明 |
|-|-|-|
| 单位 | px（`viewBox` 与 `width/height` 同数） | SVG 内不写 `mm`，导出时按 dpi 换算 |
| 初始画布 | 1200 × 760 | workorder 给了 `canvas{width,height}` 也只作为**下限** |
| 自适应 | `auto_fit=true` | 内容超界时画布自动放大，避免溢出；`compliance_checks.canvas` 记录最终尺寸 |
| 边距 | 外 38 px；列间距 74 px；行间距 26 px | 列间距 > 行间距，保证箭头有落点 |
| 上限 | 4000 × 4000 | 超限判 `canvas.ok=false` |

## 2. 排版

| 元素 | 字号 (pt) | 其他 |
|-|-|-|
| 标题 | 11 | 粗体，左上，基线 y=34 |
| 实体标签 | 8.5 | 居中；>22 字符按空格/字符换行，行高 1.5 |
| 图例 | 7 | 图例框左上对齐，行距 19 px |
| 子图字母 | 11（粗体） | 仅当同时有示意区与数据区时出现 A/B |

**最低字号 6 pt**：小于此值在期刊缩印后不可读，`compliance_checks.style.ok` 会判失败。

线宽：连接线 1.2 pt，实体框 1.2 pt，抑制端横杠 2.2 pt，网格 0.6 pt。实体框圆角 4、填充 `#F2F7FB`、描边 `#0B5F8A`。

## 3. 配色（色盲安全，Okabe–Ito 系）

| 用途 | 色值 |
|-|-|
| activation | `#0072B2` |
| inhibition | `#D55E00` |
| binding | `#009E73` |
| phosphorylation | `#CC79A7` |
| expression | `#56B4E9` |
| conversion | `#E69F00` |
| containment | `#8d979f` |
| causal / 其他 | `#333333` |
| 数据系列（按序） | `#0072B2`, `#E69F00`, `#009E73`, `#CC79A7`, `#D55E00`, `#56B4E9`, `#117733`, `#333333` |

规则：同一个语义只用一个颜色；颜色不是唯一信息载体（同时有 marker 形状或图例文字），灰度打印仍可读。

## 4. 图例

- 关系图例：线样 + 端点符号 + 类型名（`activation` / `inhibition` / …）。
- 数据图例：色块 + 系列名（含单位，如 `Expression (fold)`）。
- **图例项数必须等于图面使用的编码分类数**：`图例项 = 关系类型数 + 数据系列数`，脚本在 `legend_consistency` 里机器校验；不一致即失败。

## 5. SVG 结构（可编辑性契约）

```
<svg width height viewBox role="img">
  <title>  <desc>
  <defs> mk-activation / mk-inhibition / mk-binding </defs>
  <g id="layer-background"> | panels | edges | entities | labels | legend | title
```

- 文字一律 `<text>`，**不转曲**、不置入图片；字体只写回退栈 `Arial, Helvetica, 'DejaVu Sans', sans-serif`。
- 每个图元有稳定 `id`（`ent-e1`、`lbl-e1`、`lbl-e1-2`（换行第 2 行）、`edge-r1`、`lg-l1`、`bar-1-1`），与 `content_map.svg_ids_expected` 一一对应。
- 连线带 `data-rel-type`、`data-from`、`data-to`，便于脚本化改图。
- 改一个标签后重导出应保持其他元素不变：`edit_record.json` 记录 `baseline.sha256` 与 `revised.sha256`。

## 6. 导出预设

| 目标 | 参数 | 引擎优先级（自动探测） |
|-|-|-|
| SVG（基线，必须） | UTF-8，无外部 CSS/字体 | 本 Skill 直接手写 |
| PNG | 300 dpi，RGB，白底 | matplotlib Agg → rsvg-convert / cairosvg / inkscape → LibreOffice 转 PDF + `pdftoppm` → ImageMagick `convert` |
| PDF | 1 页，矢量优先，RGB | rsvg-convert / cairosvg / inkscape → LibreOffice Draw → matplotlib PDF |

实际使用的引擎写入 `result.json → export_artifact.<fmt>.engine`；任何降级（含「无引擎」）写进 `degradations`，不静默换格式。

## 7. 常见期刊参数对照（按需在 workorder 里覆盖）

| 场景 | 宽度 | 字号 | 线宽 | 备注 |
|-|-|-|-|-|
| 单栏图 | 85 mm | 7–8 pt | 0.5–1 pt | 缩印后最小字 ≥ 6 pt |
| 双栏图 | 170 mm | 8–9 pt | 0.75–1.2 pt | 保证 300 dpi 以上位图 |
| 答辩/基金 | 160–200 mm | 9–11 pt | 1–1.5 pt | 允许更大留白 |

Skill 默认按 px + 300 dpi 输出；需要精确物理尺寸时，在上层用 `width_mm = width_px / 300 * 25.4` 换算后写入 workorder 的 `canvas`。
