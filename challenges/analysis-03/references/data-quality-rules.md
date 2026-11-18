# 数据质量规则与降级表（data-quality-rules）

脚本 `scripts/viz_skill.py` 中 `RULES` 常量与本文件对应。五类问题全覆盖，逐字段记录，**不静默修改**。

## 1. 缺失（missing）

- 缺失标记集合：`""`, `-`, `--`, `—`, `.`, `?`, `na`, `n/a`, `nan`, `null`, `none`, `nil`, `#n/a`, `缺失`, `无`, `未知`, `待定`（大小写不敏感，trim 后比较）。
- 处置顺序：① 完整案例（complete-case）用于绘图与统计，逐图记录被剔除行数；② 数值列缺失率 >30% 或某组有效 n<3 → 该列/该组不进图，进 `pending_human`；③ 仅当某组 1≤n<3 且任务明确要求组均值时，用该组中位数填补并标记 `imputed=true`（图表数据表中另存一列 `imputed`）。
- 记录：`quality_report.field_issues[] = {field, type:"missing", count, rate, action, example_rows}`。禁止把缺失填 0 而不声明。

## 2. 异常值（outlier）

- 判据一（默认，稳健）：`x < Q1 − 1.5·IQR` 或 `x > Q3 + 1.5·IQR`（IQR 用线性插值分位数）。
- 判据二（极端）：MAD-z = `0.6745·|x − median| / MAD > 3.5`，MAD=0 时跳过并记录。
- 处置：**只标记不删除**；柱/点保留原值，箱线图须线延伸至 1.5·IQR 内最远观测、须线外画 fliers；图注写明 “n 个离群值保留”。删除仅在任务明确要求且写入 `changes`。
- 记录：`{field, type:"outlier", count, method:"iqr_1.5"|"mad_z_3.5", example_rows}`。

## 3. 重复（duplicate）

- 全行重复：按清洗后全部字段规范化字符串比较，保留首次出现行，`kept_row_index` 记入 `quality_report`。
- 主键重复：若 case 约束给出主键（`primary_key`/`主键`/`id`/`key` 语义键），按主键检查；冲突且其余字段不一致 → 不合并，全部保留并进 `pending_human`（主键冲突不可静默取舍）。
- 记录：`{type:"duplicate", scope:"full_row"|"primary_key", count, action:"drop_keep_first"|"flag_conflict"}`。

## 4. 格式（format）

- 数值文本清洗（可逆）：去掉千分位 `,`、货币/百分号（`%` → /100，记录 factor）、首尾单位串（`12.5 mm` → 12.5 + unit=mm）、全角数字与全角小数点转半角、Unicode 减号 `−`→`-`。
- 日期：支持 `YYYY-MM-DD`、`YYYY/M/D`、`DD.MM.YYYY`、`YYYY年M月D日`、ISO8601（含 Z）→ 统一 `YYYY-MM-DD`（保留 `HH:MM:SS`）；无法解析的进 `pending_human`，不猜。
- 类型混杂列（数字+文本）：若可解析比例 ≥0.8 视为数值列，剩余不可解析置空并记 missing；否则视为分类列（数值保留为字符串标签）。
- 编码：字节序探测 `utf-8-sig → utf-8 → gb18030 → cp1252 → latin-1`；仍失败按 `errors="replace"` 读取并记录替换字符数。列名乱码（UTF-8 被按 latin-1 解码的典型模式）尝试反向修复，修复前后都写入 `changes`。

## 5. 单位与编码（unit / encoding）

- 单位识别：列名 `name (unit)`、`name（单位）`、`name [unit]`，或数据字典 `unit` 字段。
- 归一化只在**可逆**时进行：`{µm→mm ×1e-3, nm→mm ×1e-6, cm→mm ×10, m→mm ×1000, g→kg ×1e-3, mg→g ×1e-3, µg→mg ×1e-3, s→min, min→h, %→fraction}`；每次换算写入 `unit_map = {field, from, to, factor, inverse_factor}`，并检查 `factor*inverse_factor ≈ 1`。
- 单位不明或混合单位（同一列出现 mm 与 cm）→ 不换算，`pending_human` 说明，图中轴标题标注原单位。
- 分类编码映射（如 0/1/2 → 组名）若字典给出则使用，`code_map` 可逆并记录。

## 6. 数据形态与规模

| 情形 | 判定 | 处置 |
|---|---|---|
| 长表 | 有 `group/value` 语义列，或列名含 `组/group/condition` + 单一数值列 | 直接按 group 分组 |
| 宽表 | 多个数值列、无 group 列 | 数值列转长表（melt）用于多系列对比，或按任务指定列 |
| 中文列名 | 列名含 CJK | 原样保留为标签（不音译、不改写） |
| 日期时间列 | 可解析为日期 | x 轴用时间序列折线，刻度为日期 |
| 行数 <5 | 样本量不足 | 只出点图/表，不做检验，`uncertainty` 说明 |
| 类别 >12 | 分类数过多 | Top-12 + “其他”聚合，聚合规则写入 `changes` |
| 空表 / 全缺失列 | 0 数据行 | 不绘图，输出空表与说明，`status=insufficient_evidence` |

## 7. 降级表（任何分支都不得抛未捕获异常，退出码恒 0）

| 触发 | 降级动作 | 记录位置 |
|---|---|---|
| case.json 缺失/损坏 | 扫描 `/input` 内的数据文件按语义重建任务，`status=partial` | `errors`, `degradations` |
| 数据文件损坏/加密 | 跳过该文件，尝试下一个；全失败 → `insufficient_evidence` | `errors` |
| XLSX 无法解析 | 纯标准库 sheet XML 解析；仍失败 → 提示转 CSV | `degradations` |
| 无 matplotlib | 只出 SVG 矢量 + 绘图数据表 | `degradations:["no_matplotlib"]` |
| 无 CJK 字体 | 不渲染位图（避免豆腐字），保留 SVG | `degradations:["no_cjk_font"]` |
| 输出目录只读 | 改写到 `output/_fallback_<ts>/` 并记录 | `errors`, `pending_human` |
| 统计量不可算（n<2、方差 0、常数向量） | 不输出伪 p 值，置 null 并说明 | `uncertainty` |
| 单位不明 | 不换算，轴标题用原单位 | `pending_human` |

## 8. 数据字典模板（当案例未给字典时由脚本生成 `data_dictionary.csv`）

| field | role | dtype | unit | n_valid | n_missing | unique | example | derived_from |
|---|---|---|---|---|---|---|---|---|
| petal_length | measure | numeric | cm | 150 | 0 | 43 | 1.4 | raw |

`role ∈ {id, measure, group, time, ignore}` 由脚本按唯一值数、类型、字段名语义推断，推断规则与置信度写入 `quality_report.type_inference`。
