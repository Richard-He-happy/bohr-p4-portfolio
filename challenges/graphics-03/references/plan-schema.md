# plan.json 工作稿契约

`/app/work/plan.json` 是你（Agent）读材料后的判断结果，也是图的唯一内容来源。脚本不改写你的生物学判断。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | str | ✓ | 写清机制，不写「Figure 1」 |
| `subtitle` | str | | 条件/来源，如「human, in vitro」 |
| `compartments` | list | ✓ | 区室，按**上游→下游**排序：`{"id","label","order"}` |
| `entities` | list | ✓ | ≥1 才出图；0 个 → `insufficient_evidence` |
| `relations` | list | | 有向关系；可以不画（实体+区室图也成立） |
| `data_encoding` | list | | 颜色/线宽→数值的映射，每项须有 quote |
| `legend_extra` | list[str] | | 图例下方追加说明（≤6 条） |
| `gaps` | list[str] | ✓ | 缺口/不确定项，画进图面并进 `uncertainty` |
| `edits` | list | | 改已有图时逐条 `{element,before,after,reason}` → `changes` |

`order` 越小越靠上；常用顺序：胞外 → 膜 → 胞质 → 核。实体引用不存在的区室 → 落入 `unspecified` 带。

## 实体

```json
{"id": "EGFR", "label": "EGFR", "kind": "protein", "compartment": "membrane",
 "evidence": {"quote": "<逐字原文≥6字符>", "locator": "paper.pdf#stream2"}}
```

`kind`：`protein` / `gene` / `complex` / `cell` / `ligand` / `metabolite` / `phenotype` / `unspecified`（决定填充色与图例）。
`label` 用原文写法：`TP53`(基因) 与 `p53`(蛋白) 不混用；复合物整体画（`kind=complex`），不把成员拆成边。

## 关系

```json
{"id": "r3", "source": "RAS", "target": "RAF", "type": "activation",
 "evidence": {"quote": "RAS activates RAF", "locator": "note.md#para4"}}
```

- `source`/`target` 必须是实体 `id`（大小写不敏感）；对不上的关系被丢弃，`check` 报 issue。
- **方向=原文语序**：「A 被 B 激活」写成 `B -> A`。
- `type` 词表见 SKILL.md §4，同义词自动归一；判不准用 `unspecified`（灰点线），不要瞎猜。
- 修饰关系把基团写进 `label`（`P`/`Ub`/`Me`）；反馈环正常写 `ERK -> EGFR`（inhibition），渲染器自动走侧通道。

## 数据编码（有证据才写）

```json
"data_encoding": [{"visual": "node fill lightness", "maps_to": "log2FC",
  "evidence": {"quote": "<含数值的原文>", "locator": "table1.csv#para4"},
  "items": [{"entity": "FOS", "value": "2.4"}]}]
```

无证据就留空：`content_map.encoding_notes` 会声明「仅编码实体种类」。

## 反模式（会被 check 抓到或直接判错）

| 反模式 | 后果 |
|---|---|
| 名词平铺成圈、随意连线 | 机制不成立 |
| 激活/抑制同一种箭头 | 语义丢失 |
| 受体画在胞质带 | 区室错误 |
| quote 是转述/翻译/拼接 | `check` 判 rejected |
| 图上出现材料没有的分子或数值 | 事实错误（最重） |
| 为凑图拆分复合物/家族 | 实体层级错乱 |
| 关系方向凭常识补全 | 与原文矛盾 |
