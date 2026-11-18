# 文献数据清洗与标准化 · 字段字典、脏数据谱系与维护指南

本文件是 `literature-data-cleaner` Skill 的配套资源，与 `scripts/main.py`、`scripts/clean_core.py` 同版本（1.0.0）。
文中数据除明确标注「示例」外，均为说明性构造，不是任何正式案例的结果。

## 1. 目标表（默认 target_schema）

见 `rules_library.json` 的 `target_schema`。案例若提供自己的 schema（`fields`/`schema`/`target_schema`），脚本读取其中的字段名与允许值；否则用默认表。

| 字段 | 类型 | 含义 | 取值规则 |
|---|---|---|---|
| `row_id` | string | 行身份，原样保留 | 输入缺失时 `derived-N`；输入重复时后者加 `#2`（前缀仍是原 id，见 `degradations`） |
| `source_document_id` | string | 来源文献 | 原样 |
| `source_locator` | string | 页码/表号/图号/段落 | 原样，不做规范化 |
| `indicator` | string | 指标标签 | 同义词归一（`indicator_synonyms`），公式型名称去空格 |
| `material` | string | 物质/样品 | 同义词归一（`material_synonyms`），如 `titanium dioxide`→`TiO2` |
| `condition_summary` | string | 条件摘要 `k=v; k=v` | 条件列文本保留，**不做条件单位换算** |
| `value` | number\|null | 单值 | 缺失、区间、纯误差、待确认时为空 |
| `value_low` / `value_high` | number\|null | 区间上下界 | 分别换算，不取中值 |
| `value_err` | number\|null | 误差项 | 与主值同因子换算 |
| `value_text` | string | 规整后的原值文本 | 便于人读 |
| `unit` | string | 规范化单位 | 不可换算时为空 |
| `original_field` | string | 原列名/原指标名 | 逐字 |
| `original_value` | string | 原单元格文本 | 逐字，绝不被换算值覆盖 |
| `original_unit` | string | 原单位文本 | 逐字 |
| `rule_ids` | string | 本行用到的规则 | `;` 分隔，对应 `rules.json` |
| `judgment_key` | string | 去重判定键 | `source|condition|indicator|material` |
| `status` | enum | 行状态 | `ok`/`needs_review`/`missing`/`replicate`/`merged_duplicate`/`conflict` |
| `duplicate_of` | string | 合并去向 | 仅 `merged_duplicate` 有值 |

## 2. 脏数据谱系（可直接迁移到自己的数据）

| 形态 | 例子 | 处理 | 规则 |
|---|---|---|---|
| 数量级前缀 + 上下标 | `μM`、`µmol L⁻¹`、`cm²` | 前缀表 + 上标归一后换算 | R009 |
| 科学计数法 | `1.2×10³`、`1.2E3`、`1.2 10^3` | 统一解析为 1.2e3 | R009 |
| 复合单位 | `mg L-1 h-1`、`mg/(L*h)`、`umol/L/h` | 逐 token 累加维度与量纲指数 | R009 |
| 区间 | `12–15`、`12 to 15`、`0.5–0.8` | 上下界分别换算，`value` 留空 | R007 |
| 误差 | `12 ± 0.5`、`12 +/- 0.5` | 主值与误差分列，同因子换算 | R008 |
| 不等号 | `<0.1`、`≥99` | 保留 `ineq` 标记，值照换，进 `uncertainties` | R009 |
| 缺失 | `n.r.`、`–`、`n.d.`、空串、`-` | 值留空并 `status=missing`，**绝不写 0** | R006 |
| 未知/任意单位 | `a.u.`、`arb. units`、`counts/s` | 不换算，`status=needs_review`，进 `pending_review.csv` | R010 |
| 缺单位 | 有数值无单位 | 不换算，进 `pending_review.csv`（`missing_unit`） | R011 |
| 同义物质 | `TiO2`/`titanium dioxide`/`TiO₂` | 归一到一个标签，原文留在 `original_field` | R012 |
| 同义指标 | `band gap`/`bandgap`/`Eg` | 归一为 `band_gap` | R012 |
| 重复记录 | 同一来源同一条件同值出现两次 | 判定键相同且值相同 → 合并，后来者 `merged_duplicate` | R013 |
| 重复实验 | 同条件两次测量，值有差异 | 保留两行，后者 `replicate` | R014 |
| 科学冲突 | 同来源同条件值相差远超容差 | 两行都保留、标 `conflict`、进 `pending_review.csv` | R015 |
| 编码错乱 | GBK/GB18030 导出的 CSV | `utf-8-sig→utf-8→gb18030→latin-1` 级联解码并记 `degradations` | R019 |
| 空表 | 只有表头 | `status=insufficient_evidence`，不假装清洗成功 | R020 |
| 列名变化 | `measured value`/`数值`/`raw_value` | 角色同义词表匹配，未命中列进 `field_mapping.unmapped` | R003 |

## 3. 单位与精度约定

- 换算模型是仿射式：`after = before * factor + offset`。纯温度维度用 offset（`25 C → 298.15 K`），复合单位里的温度只用 factor。
- `change_log.csv` 同时给出 `factor`、`offset`、`formula`（如 `v*1.602176634e-19`）与 `precision`（源小数位），因此任一值可复算。
- 百分数、ppm、ppb 属于独立的 `fraction` 维度，不会被当成无量纲计数，也不会把 `0.5` 自动变成 `50 %`。
- 规范化单位字符串采用左结合斜杠链：`mg/L/h` = mg per litre per hour。维度签名不在 `canonical` 表中时，按基本单位派生（如 `m^2*kg*s^-2`），并在 change log 中如实记录。
- 换算值统一打印 6 位有效数字；`precision` 记录源数据小数位，提醒读者换算位数不是测量精度。

## 4. 最小调用示例（示例数据，非正式案例结果）

输入 `/input/extraction-records.json`（示例，2 行）：

```json
{"records": [
  {"row_id": "E01", "source_document_id": "DEMO-A", "source_locator": "Table 1, p.2",
   "material": "titanium dioxide", "indicator": "Band gap (eV)", "value": "3.2", "unit": "eV"},
  {"row_id": "E02", "source_document_id": "DEMO-B", "source_locator": "Fig. 3",
   "material": "TiO2", "indicator": "crystallite size", "value": "12-15", "unit": "nm"}
]}
```

调用：

```bash
python3 scripts/main.py --input ./input --output ./output
```

示意输出（**示例**，摘自一次真实运行的格式，数值仅对应上面示例数据）：

| row_id | indicator | value | value_low | value_high | unit | rule_ids | status |
|---|---|---|---|---|---|---|---|
| E01 | band_gap | 5.12697e-19 | | | J | R009 | ok |
| E02 | crystallite_size | | 1.2e-08 | 1.5e-08 | m | R007;R009 | ok |

`change_log.csv` 对应两行：`E01 value 3.2→5.12697e-19 eV→J v*1.602176634e-19 R009`，
`E02 value_low 12→1.2e-08 nm→m v*1e-09 R009`（另一行是 `value_high`）。

## 5. 维护与扩展

1. **加单位**：在 `unit_table.json` 的 `units` 增条目（`dim`/`scale`/`offset`/`aliases`）。若出现新维度组合，在 `canonical` 里补一条 `维度签名 → 规范单位`。
2. **加规则**：在 `rules_library.json` 的 `rules` 追加 `{rule_id, priority, applies_to, condition, transform, examples, failure_mode, human_gate}`。案例自带的规则文件优先级默认 10，会覆盖同编号的内置规则，并写入 `rules.json.suppressed_rules`。
3. **改列名映射**：在 `field_roles` 里给角色加别名（`row_id`/`source_document_id`/`source_locator`/`value`/`unit`/`indicator`/`material`）。
4. **改同义词**：`material_synonyms`、`indicator_synonyms`。只加真正等价的名字；不同物质（如 `TiO2` 与 `TiN`）绝不可指向同一标签。
5. **改去重容差**：`judgment_key.conflict_relative_tolerance` / `replicate_relative_tolerance`（默认 0.05）。
6. **版本一致性**：三份资源与两个脚本同号发布；改资源即升版本号，并在 SKILL.md 的变更记录里写一行。

## 6. 自查方法

```bash
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --input /input --output /app/output --determinism   # 两次运行逐字节比对
cat /app/output/verify_report.json                                          # 复算一致率、计数、row_id 唯一性
```

人工抽查建议：
- 随机取 5 个 `change_log.csv` 行，用 `before*factor+offset` 手算一次；
- 取 3 组 `duplicates` 的 `judgment_key`，确认来源或条件确实不同/相同；
- 检查 `pending_review.csv` 里的行在 `cleaned.csv` 中 `value` 为空；
- 检查 `status=conflict` 的行是否都出现在异常报告里。
