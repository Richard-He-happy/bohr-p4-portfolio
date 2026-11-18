# 图面与导出规范（apparatus & technical route v3）

## 1. 版式

| 区域 | 位置（1200×800） | 内容 |
|-|-|-|
| 页眉 | y 0–76 | 标题（22px）、副标题/来源（11px）、右上 `FIG. 1 · 装置 / 技术路线示意` 与单元/连接/步骤/阶段计数 |
| A 面板 | x 22–840, y 86–674 | 装置与物料流向：按有向图最长路径分列（≤4 列），上游在左；列内按首次出现顺序；节点 188×58 |
| B 面板 | x 856–1178 | 技术路线与操作序列：每步 42px 高、编号徽标、阶段分组条；步骤 >8 或阶段 >3 时截断并在下方注明 |
| 图例 | y 688–762 | 线型＝流向类型，琥珀虚线框＝待确认；只列实际用到的类型 |
| 页脚 | y 774–792 | 证据说明 + 图注 |

画布升级：`nodes>10` 或 `steps>8` → 1200×900（A/B 面板同步加高）。

## 2. 图层（SVG `<g id>`，固定 7 层）

`layer-background`（底色/标题/分隔线）→ `layer-panels`（面板与面板标题）→ `layer-edges` → `layer-nodes` → `layer-steps` → `layer-legend` → `layer-annotations`。

每层内含元素组：`<g id="node-N1" data-kind="part" data-quote="…" data-locator="S1 ¶12" data-resolution="exact">`。
图元 id 前缀：`node-`、`edge-`、`step-`、`stage-`、`legend-`；id 全局唯一（`compliance_checks.element_ids.unique`）。

## 3. 颜色与线型

| 语义 | 颜色 | 线型 |
|-|-|-|
| 物料 / 样品流 | `#2563eb` | 实线 |
| 能量 / 热流 | `#ea580c` | `7 4` 虚线 |
| 信号 / 控制 | `#7c3aed` | `2.5 3` 点线 |
| 回流 / 循环 | `#16a34a` | `7 4` 虚线 |
| 废液 / 尾气 | `#b91c1c` | `7 4` 虚线 |
| 顺序推断（无原文连接） | `#9ca3af` | `4 4` 虚线 |
| 待确认图元 | 填充 `#fffbeb` / 描边 `#d97706` | `5 4` 虚线 |

节点角色：device `#eff6ff/#2563eb`、material `#f0fdf4/#16a34a`、measurement `#f5f3ff/#7c3aed`、waste `#fef2f2/#b91c1c`。
字号：标题 22 / 面板标题 13.5 / 节点 13.5 / 参数 9.5 / 连线标签 10 / 图例 10 / 页脚 9.5。

## 4. 导出参数

| 产物 | 规格 |
|-|-|
| `figure.svg` | XML 1.1、`viewBox="0 0 W H"`、文字全为 `<text>`、无 `<image>`、无外部字体依赖（font-family 首选 AR PL SungtiL GB / Noto Sans CJK SC，回退 sans-serif） |
| `figure.pdf` | PDF 1.4，单页，MediaBox = 画布像素当 point；Type0/Identity-H + CIDFontType2 内嵌 TrueType（FontFile2），附 ToUnicode；矢量矩形/折线/多边形 + 文本 |
| `figure.png` | 150 dpi 预览，由 PDF 渲染（`pdftoppm -singlefile` → `mutool draw`），失败则 `png=null` 并记降级 |

## 5. 检查项判据（`compliance_checks`）

| 键 | 判据 |
|-|-|
| `canvas` | W ≥ 1000、H ≥ 700、图层 ≥ 6 |
| `text_editable` | `<text>` > 20 且无 `<image>` |
| `element_ids` | id 唯一，且 `data-quote` 属性 ≥ 3 |
| `evidence` | 带 quote 图元占比 ≥ 0.6 |
| `connections` | 箭头（`<polygon>`）≥ 2，悬空连接 0 |
| `pdf` | 头 `%PDF-`、含 MediaBox、内嵌字体、可提取 CJK > 20 字 |
| `png` | 文件存在且为 PNG 魔数 |
| `determinism` | 同 plan 两次布局产出的 SVG 字节一致 |

## 6. 已知失败清单

| 现象 | 原因 | 处置 |
|-|-|-|
| 中文在 PDF 中变方框 | 未内嵌字体 | 本 Skill 内嵌 TrueType；无可用字体时降级为 ASCII（Helvetica）并记降级 |
| 连线穿框 | 跨列且行列错位 | 走下方通道（`_route` 的 j2≤j1 分支），回流/回边固定下绕 |
| 标签溢出 | 器件名过长 | 自动两行换行；仍超长截断，完整名见 content_map |
| 图例与图不符 | 手写图例 | 图例由实际 edge 的 flow 集合生成 |
| 步骤编号与正文错位 | 材料编号不连续 | `build` 按数组顺序重排 1..N，原文编号保留在 `quote` 中 |
| PDF 无文本层 | 只画图形 | 逐文本项写 Tj + ToUnicode；`pdftotext` 可回读校验 |
