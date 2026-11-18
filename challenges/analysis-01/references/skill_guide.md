# sci-data-cleaning — 使用与方法说明

面向"把一份带故障的科研表格清洗成可交付结果，并让别人能逐格复核"的场景。
本文件是 `SKILL.md` 的展开版：字段约定、方法细节、限制、排错与自检。

## 1. 一分钟上手

```bash
# 1) 准备输入目录（只读）
#    in/case.json          必选（含 case_id、output_contract；可选 files / data_dictionary / workorder）
#    in/task.md            可选（清洗要求，用于单位统一等覆盖）
#    in/data.csv           数据表（可多个；有 .xlsx 请先转 CSV）
#    in/data_dictionary.md 数据字典（Markdown 管道表 / JSON / DOCX 均可）
python3 scripts/main.py --input in --output out

# 2) 独立复核（重算报告数字，写 assertions.json）
python3 scripts/verify.py --output out
```

产物：`result.json`、`cleaned.csv`、`transform_log.csv`、`field_issues.csv`、
`duplicates.csv`、`stats.json`、`quality_report.md`、`quality_report.json`、
`assertions.json`、`run.log`。

## 2. 数据字典格式

最小可用（Markdown 管道表，列名任意，脚本按同义词识别）：

| name | description | unit | type | range | missing | precision |
|---|---|---|---|---|---|---|
| sample_id | 样品编号 | - | string | - | - | 0 |
| pH | 酸碱度 | - | float | 0-14 | ND | 2 |
| NO3_mgL | 硝酸盐 | mg/L | float | 0-200 | -999 | 2 |

也可用 JSON：`{"NO3_mgL": {"unit": "mg/L", "min": 0, "max": 200, "missing": "-999"}}`，
或直接写在 `case.json` 的 `data_dictionary` / `fields` / `columns` / `schema` 里。

识别字段：`name/description/unit/type/min/max/range/missing/precision/key`
（同义词表见 `cleaning_rules.json` 的 `dict_header_keys`）。
`range` 支持 `0-200`、`0 to 200`、`0~200`、`0 – 200`；`missing` 支持单码或逗号分隔多码。

## 3. 方法细节

### 3.1 缺失与删失
- 词表分四类：`blank`（空、NA、`-`、`.`）、`not_detected`（ND、"未检出"）、
  `below_loq`（`<LOD`、`<LOQ`、BDL、"低于检出限"）、`sentinel`（`-999`、`-9999`、`9999`）。
- 显式 `0` 永远是真值，不会被当缺失。
- 哨兵码只有**落在物理上下限之外**才判为缺失（`-999` 若在允许范围内则保留并标 `R1`）。
- 所有缺失在 `cleaned.csv` 写空串，在 `transform_log.csv` 记原值与原因码；
  `field_issues.csv` 汇总每列 `n_missing` 与 `missing_reasons`（形如 `not_detected=3;sentinel_code=1`）。
- **不做填补**：题面要求不得推断总体统计量或填补缺失/无效源值；下游统计用 `stats.json`
  的 `n_used`（排除缺失/删失/无效）而非编造值。

### 3.2 异常与越界
- 硬判据：字典 `min/max`；命中写 `R1_range_violation`，**保留数值**。
- 分布判据：n≥8 时用中位数与 MAD（`1.4826×MAD`）算稳健 z，|z|>3.5 记 `R2`；
  MAD=0 时退化到 IQR×1.5。判据与命中数写在 `field_issues.csv`（`n_out_of_range`、`n_dist_outlier`）。
- 从不删除、从不盖帽：真极值与应用错误无法仅凭数值区分，交由 `pending_human` 决策。

### 3.3 重复记录
- 键来源：字典 `key` 列 → 列名像标识（`*_id`、`sample`、`site`…）且唯一率高 → 回退整行。
- 归一：NFKC、去首尾空白、压缩内部空格、统一小写；宽松键再去分隔符与前导零。
- 同键多行：保留非空字段最多的一行（并列取源行序在前者），其余写入 `duplicates.csv`
  并记 `duplicate_of`；仅分隔符/大小写不同的记为 `D3_near_duplicate`，**不自动删**。
- 行账目：`rows.in = rows.out + duplicates_removed`，由 `assertions.json` 校验。

### 3.4 格式、单位与编码
- 数值：`1.234,5` / `1,234.5` / `1,234`（歧义时按千分位并记 `F1_thousands_sep_ambiguous`）/
  `1.2E-3` / `1.2×10⁻³` / 括号负数 / 尾随 `%` 或单位 / 脚注符 `*†`。
- 单位：按维度换算到字典单位（`µg/mL→mg/L` 因子 1，`µg/L→0.001` 等，共 10 个维度含温度仿射）；
  因子写入 `transform_log.csv` 的 `reversible` 列，`cleaned × 因子` 可回到原值（相对误差 ≤1e-12）。
- 日期：多格式解析为 ISO 8601；`d/m/Y` 优先，`d≤12` 时标注歧义；Excel 序列号支持。
- 编码：UTF-8/UTF-8-BOM 优先，失败则按 GB18030/latin-1 打分，拉丁补充区字符占比高时
  用 `latin-1 → GB18030` 回解（典型 GBK 乱码），并写 `degradations`。

### 3.5 质量报告与一致性
- `quality_report.md` 由 `references/quality_report_template.md` 填占位符生成，
  数字全部来自同一份汇总对象；`quality_report.json` 存同份汇总 + 字段级清单。
- `verify.py` 独立重算：行数、缺失总数、`transform_log` 与 `cleaned.csv` 逐格一致性；
  任一不符 → `assertions.json` 记 `pass:false` 并使 `result.json` 降级为 `partial`。

## 4. 输出字段速查

`result.json` 顶层除 `output_contract` 各键外，固定含：
`case_id` `status` `summary` `sources` `uncertainty` `pending_human` `errors`
`degradations` `changes` `artifacts` `unresolved_contract_fields` `runtime`。

`summary` 内含：`rows{in,out,duplicates_removed,near_duplicate_groups}`、`key_fields`、
`units`、`roles`、`missing_cells`、`outliers`、`preview`、`stats`、`checks`、`needs_human_review`。

契约键匹配：先精确名，再同义词包含（表见 `cleaning_rules.json` 的 `contract_synonyms`）；
未命中的键按名字类型给 `null`/`[]` 并进 `unresolved_contract_fields`，**绝不删键或改名**。

## 5. 适用与不适用

适用：CSV/TSV 为主的监测表、实验记录表、汇总转录表；列为数值/日期/类别/标识；
有（或可推断）字段语义与物理范围。

不适用：XLSX/PDF 直读（先转 CSV）；嵌套 JSON 深度 >1 的表；需要统计推断的场景；
行列互换的透视宽表（可先整形）。

## 6. 失败与降级

| 现象 | 结果里的表现 | 处置建议 |
|---|---|---|
| 没有 `case.json` | `errors=[CASE_MISSING]`，`status=input_error` | 补 `--case` 或放入 case.json |
| 表读不到 | `status=insufficient_evidence`、`pending_human=[NO_TABLE]` | 检查扩展名/编码/分隔符 |
| 无主键 | `pending_human=[KEY_NOT_FOUND]`，只去完全重复 | 在字典里补 `key` 列 |
| 单位不明 | `uncertainty` 记 `U2_unit_ambiguous` | 在字典 `unit` 列补单位 |
| 数据是 XLSX | `degradations=[UNSUPPORTED_FORMAT]` | 在 Excel 另存为 CSV(UTF-8) 后重跑 |
| 输出目录不可写 | 自动退到 `./output` 或临时目录 | 显式传 `--output` |

## 7. 自检清单（交付前）

1. `python3 scripts/main.py --help` 正常；`python3 scripts/verify.py --output out` 打印 `passed == total`。
2. `result.json` 含 `case_id` 与契约全部键；`unresolved_contract_fields` 逐条有解释。
3. `cleaned.csv` 行数 = `summary.rows.out`；`field_issues.csv` 的 `n_missing` 之和 = `missing_cells`。
4. 任一被改写单元格都能在 `transform_log.csv` 找到原值。
5. 重复行只出现在 `duplicates.csv`，`cleaned.csv` 无重复键。
6. 无编造值：空就是空，不做插补；`pending_human` 覆盖所有需要人判断的点。

## 8. 版本与维护

- 版本 `1.2.0`（`SKILL.md` frontmatter 与 `main.py` 的 `V` 同步）。
- 一切阈值/词表/单位在 `references/cleaning_rules.json`；改规则不动脚本。
- 兼容 Python 3.8+（仅标准库）。重跑同一输入应逐字节复现 `cleaned.csv`。
