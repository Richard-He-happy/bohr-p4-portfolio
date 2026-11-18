# 字段词典与抽取口径（v1.0.0）

供 `scripts/build.py` 与人工复核共用；与 `SKILL.md` 冲突时以本文件的口径细节为准。

## 1. 结果行字段

| 键 | 含义 | 规则 |
|---|---|---|
| `field_id` | 字段表的 id | 必须与 `target-fields.json` 的 `field_id|id|key` 完全一致 |
| `label` | 字段名 | 取字段表 `label|name|question`，可原样保留 |
| `value` | 抽取值 | 标量优先（数/字符串）；多值用列表；`reported` 才允许非空 |
| `unit` | 单位 | 原文单位逐字（`nM`、`µg/mL`、`%`）；无单位留空 |
| `statistic` | 误差/区间/检验量 | 原文形态（`SD 0.4`、`95% CI 10.1-15.2 nM`、`p = 0.03`） |
| `condition` | 成立条件 | 温度、时间、剂量、样本、基线、仪器设置等，原文措辞 |
| `comparator` | 对照/比较组 | 原文组名（`vehicle`、`control`），没有留空 |
| `source_kind` | 证据来源类型 | `text` / `table` / `figure` / `caption` / `abstract` / `supplement` |
| `quote` | 逐字证据 | 连续原文片段；省略用 `…`；不改词、数、标点顺序 |
| `locator` | 定位 | 见 §3 |
| `verification` | 脚本判定 | `quote_strict` / `quote_normalized` / `quote_loose` / `quote_unverified` / `no_quote` |
| `reasoning` | 判读依据 | 如何读出、单位与统计量来源；非 `reported` 时为搜索依据 |
| `conflict` | 冲突双方 | `{quote_a, quote_b, value_a, value_b}`，`source_conflict` 必填 |

## 2. 状态判定表

| status | 判据 | 反例（禁止） |
|---|---|---|
| `reported` | 原文同段明确给出该字段值（含单位/条件） | 由两个数字算出的派生值当原文值 |
| `not_reported` | 已检索全文（含表、图注、补充材料）且确无 | 没找到就写 0、写 "unknown" 当值 |
| `source_conflict` | 两处及以上材料给出不同值/结论 | 只说"有冲突"却不给双方 quote |
| `extraction_failed` | 有候选但无法确定（无文本层、跨页缺行、单位不可判定） | 用 `not_reported` 掩盖没读成 |

判定顺序：**有无 → 是否一致 → 是否读得出**。

## 3. locator 结构

```json
{"material_id": "M2", "paragraph_id": "M2-p0017", "page": 4,
 "table": "Table 2", "row": "TNF-α 10 ng/mL", "col": "24 h", "cell": "B7",
 "figure": "Fig. 3b", "section": "Results 3.2", "pointer": "/data/0/ic50"}
```

- `material_id` + `paragraph_id` 必备（`M*` 由 `init` 分配，`pNNNN` 为段号）。
- PDF 加 `page`（`pdftotext` 分页 `\f` 计数；stdlib 降级时页码不可用，需在 `reasoning` 说明）。
- 表格给 `table`+`row`+`col`；跨页表写主表号与 `page`，另一页在 `reasoning` 说明。
- 补充材料/附录给 `section` 或 `pointer`。

## 4. quote 匹配三级

| 级别 | 归一化 | 处置 |
|---|---|---|
| `quote_strict` | 原样 | 通过 |
| `quote_normalized` | NFKC、合并空白、软连字符、连字符换行 | 通过（记录级别） |
| `quote_loose` | 再去掉全部标点与空白 | 通过但记 warning，需人工确认没跨句拼接 |
| `quote_unverified` | 三级都未命中 | `check` error；必须回原文重取 |

`reported` 的 quote 建议 ≥8 字符且覆盖被抽数值；数值与 quote 不一致会触发 `number_not_in_quote`。

## 5. 数值与表格规则

1. 不四舍五入、不换算、不合并多列（`mean±SD` 拆成 `value` 与 `statistic`）。
2. 范围值保留原文连接符（`10.1–15.2`）；`<0.001`、`>90%` 原样保留，不改写成具体数。
3. 表格数字逐字保留；表头单位与数值分列保存；合并单元格需写出所属行列标签。
4. 正文与表格数值不同 → `source_conflict`，双方 quote 各一条，`value` 写正文值并注明。
5. 图注文字给出的数值可直接 `reported`；像素估读值须加 `approximate` 并给误差，且优先标 `extraction_failed`。
6. 原文缺失（未测、未报告）→ `not_reported`，值留 `null`，不得填 0。

## 6. claims

| kind | 用途 |
|---|---|
| `author_conclusion` | 作者明确结论（"X inhibited Y"） |
| `limitation` | 作者声明的限制、样本量不足、外部效度 |
| `speculation` | "may/suggest/possibly" 类推测，不得升格为事实 |
| `data_point` | 纯数值陈述 |

每条 claim 带 `quote` 与 `locator`；`field_ids` 关联到受影响字段。

## 7. counts 与 status

`counts = {target_fields, reported, not_reported, source_conflict, extraction_failed, quote_verified, quote_loose, quote_failed, fallback_fields, coverage_pct}`；四状态之和应等于 `target_fields`，`coverage_pct = 100 * (target_fields - fallback_fields) / target_fields`。

| 内部状态 | 触发条件 |
|---|---|
| `ok`/`answered` | 全覆盖、无 `extraction_failed`、`quote_failed = 0`、无 error |
| `partial` | 有 fallback、quote 未命中、字段缺失或 `extraction_failed` |
| `insufficient_evidence` | 无可读文本或无字段表 |
| `input_error` | 输入根下无材料 |

## 8. 输出契约回填

`output_contract` 每个键都出现：已知语义键（`case_id`/`status`/`result`/`claims`/`uncertainties`/`sources`/`pending_human`/`errors`/`changes`/`runtime`/`verification`/`counts`…）填对应结构；未知键按名称或说明中的关键词映射；仍无法判断时列表键给 `[]`、其余给 `null`。契约要求的 `status` 词形从契约描述中取（如 `answered|partial|insufficient_evidence|input_error`）。

## 9. 限制

扫描件无 OCR；跨页合并表只按已抽出文本行处理；跨文献核对与单位换算需人工确认。
