# 工作稿 schema 与检查规则（mindmap.json）

## 1. 工作稿结构

```json
{
  "schema": "mindmap/1.0",
  "case_id": "案例标识（可空）",
  "theme": {"id": "root", "label": "中心主题（≤40 字）", "evidence": [EVID]},
  "nodes": [
    {"id": "n1", "label": "分支名或要点（≤20 字）", "parent": "root",
     "role": "question|method|evidence|finding|conclusion|limitation|gap|task|risk|concept|subtopic",
     "summary": "可选，一句话结论（可在 build 后不进图）",
     "status": "fact|summary|inference",
     "evidence": [EVID]}
  ],
  "edges": [
    {"id": "e1", "from": "n1", "to": "n4",
     "type": "cause|contrast|support|conflict|sequence|depends|cite|example|definition",
     "label": "可选，边标签（≤14 字）", "evidence": [EVID]}
  ]
}
```

`EVID = {"material": "M1", "locator": "p.3¶2", "quote": "原文连续片段"}`

- `parent` 决定层级：`root` → level 1 → level 2 → level 3；不要出现环。
- `edges` 只写**跨分支**关系；父子连线由 `parent` 自动生成，不重复写 `hierarchy` 边。
- 图片/表格类证据允许 `locator` 写成 `figure2` / `table1` 且 `quote` 为空（计为 figure 证据，不参与文本比对）。

## 2. 关系类型与方向

| type | from → to | 判定依据（须有 quote） |
|---|---|---|
| cause | 原因 → 结果 | "导致/因此/归因于" 等明确因果 |
| contrast | A ↔ B | "相比/不同于/而" 对照 |
| support | 证据 → 论断 | "支持/证实/与…一致" |
| conflict | A ↔ B | "然而/不一致/矛盾" |
| sequence | 先 → 后 | 时间点、步骤序 |
| depends | 依赖方 → 被依赖方 | "基于/依赖/需要先" |
| cite | 引用方 → 被引 | 文献编号/作者年份 |
| example | 概念 → 例证 | "例如/以…为例" |
| definition | 术语 → 定义 | "是指/定义为" |

## 3. 校验规则（`check` 输出）

| 级别 | code | 含义 | 处理 |
|---|---|---|---|
| error | `theme_missing` | 缺中心主题 | 补 `theme.label` |
| error | `no_nodes` | 无节点 | 至少写 6 个 |
| error | `node_unverified` | 节点无任何命中 quote | 补逐字 quote 或删除 |
| error | `cycle_broken` | 父子链成环/断链 | 修 `parent` |
| error | `edge_dropped`（非法） | 端点不存在/类型不在词表/自环 | 修端点或类型 |
| warn | `edge_dropped`（无证据） | 关系没有 quote | 补证据，否则不会绘制 |
| warn | `label_long` | 标签 > 30 字 | 精简或改 `summary` |
| warn | `dup_label` | 同图重复标签 | 合并节点 |
| warn | `depth_deep` | 深度 > 4 | 合并中间层 |
| warn | `node_few` / `node_many` | 节点 < 6 / > 60 | 扩写或合并 |
| warn | `role_missing` | 缺 `method`/`finding` 角色 | 检查是否漏方法/结论分支 |
| warn | `edge_unverified` | 关系无证据 | 保留但不绘制 |

通过条件：**0 error、节点 ≥ 6、带证据节点比例 ≥ 0.8**（`check` 显示"可 build"）。

## 4. 定位格式

| 材料 | locator 示例 | 说明 |
|---|---|---|
| PDF（pdftotext） | `p.12¶3` | 第 12 页第 3 段 |
| PDF（正则回退） | `stream7` | 页码为估计值，进 `uncertainty` |
| DOCX | `¶15` | 第 15 段 |
| Markdown / TXT | `¶8` | 空行分段后的第 8 段 |
| CSV / TSV | `row42` | 第 42 行 |
| JSON | `json:/materials/0/text` | JSON Pointer |
| 图片 / 表格 | `figure2` / `table1` | 无文本，需人工核图 |

## 5. 产物文件

| 文件 | 内容 | 可编辑性 |
|---|---|---|
| `mindmap.svg` | `<g id="node-<id>">` + `<text>/<tspan>` + `<path id="edge-*">` | 文字、颜色、位置均可改 |
| `mindmap.json` | 规范化后的 theme/nodes/edges + `stats` + `dropped_edges` | 可直接再编辑后重新 build |
| `content_map.json` | 每个节点/关系的 material + locator + quote + verified | 逐条回溯 |
| `mindmap.png` | SVG 渲染预览（无渲染器时降级缺失） | 只看不改 |
| `result.json` | 契约字段 + 状态 + 来源 + 不确定性 + 变更 | 机器读取 |

## 6. 变更记录约定

`changes[]` 每条形如 `{"action": "build", "detail": "工作稿=agent；18 节点/3 关系；PNG=convert"}`。
被丢弃的关系写入 `change_log`（`action: dropped_edge`）并附原因，便于复核者区分"材料没有"与"脚本没画"。
