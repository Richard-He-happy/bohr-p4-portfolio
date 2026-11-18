# 关系词表与端点语义（relation vocabulary）

用于两件事：① 无 workorder 时从材料句子解析 `头实体 — 关系 — 尾实体`；② 把关系类型映射到图上的端点符号与颜色，使「抑制」不会被画成「激活」。

机器可读的权威副本是 `scripts/main.py` 中的 `REL`（类型名即 marker/配色键）。改词表时**两处同步**。

## 1. 类型 → 图形语义

| type | 语义 | marker | 颜色 | SVG 记录 |
|-|-|-|-|-|
| `activation` | 激活 / 促进 / 上调 | 箭头 | `#0072B2` | `data-rel-type="activation" marker-end="url(#mk-activation)"` |
| `inhibition` | 抑制 / 下调 / 阻遏 | T 形端（平头） | `#D55E00` | `marker-end="url(#mk-inhibition)"` |
| `binding` | 结合 / 互作 / 复合物 | 菱形 | `#009E73` | `marker-end="url(#mk-binding)"` |
| `phosphorylation` | 磷酸化 | 箭头 | `#CC79A7` | 与 activation 同形、不同色，靠图例区分 |
| `expression` | 表达 / 编码 | 箭头 | `#56B4E9` | 同上 |
| `containment` | 包含 / 组成 / 属于 | 箭头 | `#8d979f` | 层级关系，通常落在分层布局的相邻列 |
| `conversion` | 转化 / 生成 | 箭头 | `#E69F00` | 同上 |
| `causal` | 导致 / 因此 | 箭头 | `#333333` | 与 activation 区分靠图例文字 |
| `causal2` | 随后 / 之后（时序） | 箭头 | `#999999` | 时序提示，非因果关系 |

> 规则：**端点形状只区分 activation / inhibition / binding**，其余类型靠颜色 + 图例。任何时刻「图例项数 == 图面使用的类型数」必须成立（脚本在 `legend_consistency` 里机器校验）。

## 2. 中英模式（正则片段，`re.I`）

- activation：`activates?|activated|promotes?|induces?|upregulates?|up-regulates?|stimulates?|enhances?|促进|激活|上调|诱导|增强`
- inhibition：`inhibits?|inhibited|suppress(es|ed)?|repress(es|ed)?|blocks?|downregulates?|down-regulates?|attenuates?|抑制|下调|阻遏|阻断`
- binding：`binds?|binding|interacts? with|forms? a complex|recruits?|结合|互作|相互作用|复合物|招募`
- phosphorylation：`phosphorylates?|phosphorylated|phosphorylation|磷酸化`
- expression：`expresses?|encoded? by|encodes?|表达|编码`
- containment：`contains?|includes?|comprises?|consists? of|is part of|subunit of|包含|包括|属于`
- conversion：`converts?|converted to|produces?|generates?|yields?|转化为|生成`
- causal：`leads? to|results? in|causes?|caused by|therefore|thus|hence|导致|引起|因此`
- causal2：`followed by|subsequently|随后|之后|接着`

## 3. 方向判定

默认 `方向 = forward`（句中先说者 → 后说者）。出现被动结构时翻转：

- 英文：关系词后 14 字符内以 `is / are / was / were / been` 起头，或句中含 `by <agent>`。
- 中文：关系短语以 `被`、`受到`、`由` 起头。

例：`STAT3 is inhibited by SOCS3` → `SOCS3 --| STAT3`（inhibition，方向 SOCS3→STAT3）。

workorder 里的显式 `direction` 优先于启发式；workorder 给的 `from`/`to` 一律按原样使用，不再翻转。

## 4. 实体边界启发式

- 拉丁文实体：取关系词前最后一个 token（`[A-Za-z][A-Za-z0-9-]{1,15}`）；若该 token 全小写且前一个 token 首字母大写，则合并两词（`TNF signaling`）。
- 中文实体：取关系词前最后一段 `[\u4e00-\u9fa5]{2,8}`。
- 长度 < 2 或头尾规范化后相同 → 丢弃。
- 上限 16 实体 / 22 关系，保证图面可读；超限记入 `uncertainty`。

## 5. 何时不下结论

| 情况 | 处置 |
|-|-|
| 只有共现没有关系词 | 不画边；必要时记 `pending_human` |
| 同一句多个关系词、端点不明确 | 只保留端点互异且能各自定位的关系 |
| 材料与 workorder 冲突（如 workorder 说抑制、原文说激活） | 以材料为准画图，冲突写入 `exceptions`（`type=source_conflict`）并列入 `pending_human` |
| 关系端点无法在材料中逐字定位 | 该关系不入图，`relation_unverified` |

## 6. 扩展方法

1. 在 `REL` 增加 `("type", r"pattern", "marker", "#RRGGBB")`；`marker` 只取已实现的三种（activation / inhibition / binding），新形状需在 `render.MARKERS` 与 `render.heads` 同步增加。
2. 在本文件表格补一行，说明语义与何时使用。
3. 跑 `python3 -B scripts/main.py --input <case> --output <out>`，确认 `compliance_checks.legend_consistency.ok == true`。
