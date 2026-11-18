# 渲染与导出规则

同一份 `plan.json` → 同一个显示列表 → SVG 与 PDF 同遍输出，几何完全一致；源文件与导出件不可能不一致。

## 分层与 id

`layer-background` → `layer-title` → `layer-compartments` → `layer-entities` → `layer-relations`
→ `layer-legend` → `layer-notes`；元素 id `comp-<区室>`、`ent-<实体>`、`rel-<关系>`（`content_map` 用它指回图面）。
所有文字是 `<text>`（非路径），字体族 `DejaVu Sans, Helvetica, Arial, sans-serif`，改标签只需改文本节点。

## 布局

- 画布宽 1240 px，高按内容增长；页边距 32 px。
- 每个区室一条横带，按 `order` 自上而下：上游在上、下游在下；带内实体按 plan 顺序左→右，每行最多 4 个。
- 跨膜语义靠带表达：配体在胞外带、受体在膜带、激酶在胞质带、转录因子/靶基因在核带。

## 走线

| 情形 | 走线 |
|---|---|
| 跨带向下 | 源框底中点竖下 → 两带间通道水平 → 靶框顶中点（正交三段） |
| 向上（反馈） | 源框右侧出 → 最右通道上行 → 靶框右侧；多条按 12 px 错列 |
| 同行相邻 | 直接水平连接 |
| 同行反向/重叠 | 下绕 20 px 通道 |

箭头端点落在框边缘，方向严格 `source → target`，不反向绘制。

## 图元编码

填充色只编码 `kind`；边色+端点形状编码关系类型：实心箭头=激活、T 形=抑制、空心箭头=结合、
虚线+`P`=修饰、双箭头=转运、点线=间接/未说明。图例由**实际出现的** kind/type 生成，
所以「图例项 ↔ 图面图元」必然一致；不要手写图例。节点上的小字是 kind，不是数据值。

## 导出与检查

| 检查 | 判据 |
|---|---|
| SVG 可编辑 | `<text>`>0 且 `layer-*` 分组 ≥4 |
| PDF 真实 | `%PDF-1.4` 开头、含 `/Type /Page`、`%%EOF` 结尾、内容流含 `Tj`（文字可选中） |
| 映射完整 | `content_map.entities` 数 == 图面实体数 |
| 语义完整 | `unplaced_entities` 为空 |

PDF：单页，尺寸 = 画布 px × 0.75 pt；Helvetica/Helvetica-Bold（base-14，无需字体文件）；
WinAnsi 之外的字符（中日韩等）在 PDF 中丢弃并计数，**SVG 保留原文**，非拉丁文字以 SVG 为准。

## 已知限制（如实报告）

1. 不产出 PNG：标准库无位图文字光栅器；`figure.pdf` 作检视件（`raster_preview`、`degradations`）。
2. 规则化正交布线，不做全局避障；实体 >16 时拥挤，应拆图或写进 `gaps`。
3. 自动布局只保证区室层级 + 上下游方向；精修直接改 `figure.svg` 坐标。语义只来自 `plan.json`。
