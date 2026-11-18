---
name: sci-data-cleaning
description: Audit-grade cleaning of scientific tabular data. Classifies missing/censored/sentinel values without statistical imputation, canonicalises numeric/date/unit/encoding faults with recorded reversible transforms, resolves duplicate records under a dictionary-derived key, and emits an analysis-ready table plus a field-level quality report whose numbers are re-derived from the emitted tables. Use when a case supplies dirty CSV/TSV tables together with a data dictionary and a cleaning workorder.
version: 1.2.0
---

# sci-data-cleaning（科研数据清洗与处理）

## 1. 用途与边界

对一个脏表完成题面约定的**五类处理**，并交出可复核的证据链：

| 类别 | 本 Skill 做什么 |
|---|---|
| 缺失值 | 区分 `blank / not_detected(ND) / below_LOQ(＜LOD) / sentinel(-999)`，写出缺失原因码，**不做统计填补** |
| 异常值 | 字典物理上下限（硬越界）+ 稳健分布判据（MAD-z，退化到 IQR）双判据，**只标记不删除** |
| 重复记录 | 由字典主键推断复合键；大小写/空格/分隔符/前导零归一后判重；保留最完整记录，其余进 `duplicates.csv` 隔离 |
| 格式/单位/编码 | 千分位、小数逗号、科学计数、脚注符、尾随单位、日期格式、GBK 乱码；换算因子与编码修复全部记录，**可逆** |
| 质量报告 | 字段级问题清单 + 五类汇总，报告数字由 `verify.py` 从产出表反算校验 |

**不做**：统计建模与假设检验、图表美化、数据库运维、实验设计、论文写作；不做均值/中位数填补（题面《Harbor 运行契约》明确"不得推断总体统计量或填补缺失/无效源值"）；不解析 XLSX/PDF 数据表（写入 `degradations` 并给出转换建议）。

## 2. 何时触发

- 用户给出**脏表格 + 数据字典/字段说明 + 清洗要求**，要"清洗表 + 质量报告 + 可复现证据"。
- 用户抱怨"报告数字和清洗后的表对不上""单位和编码不统一""同一样品重复出现"。
- 不适用：只需要画图/建模；只需要从 PDF 抄数字；没有表格只有正文。

## 3. 运行契约

```bash
python3 scripts/main.py --input /input --output /app/output     # 单入口
python3 scripts/verify.py --output /app/output                  # 独立复核（可选）
```

- 输入只读 `/input`（`case.json`、`task.md`、表格、字典），产物只写 `--output`（默认 `/app/output`）。
- **退出码恒为 0**；失败写进 `result.json` 的 `errors`，不抛栈、不静默。
- 纯标准库（`csv/json/re/zipfile/unicodedata/hashlib`），不联网、不 pip、不依赖 CWD（脚本用 `Path(__file__).resolve().parent` 定位 `references/`）。
- 确定性：行序=源文件行序，浮点 `%.12g`，无随机种子、无时区推断；同输入重跑 `cleaned.csv` 应逐字节一致（`__src` 记录"源文件:行号"）。

## 4. 输入发现（语义识别，不假设键名）

1. `case.json`（或 `--case`、任意 `case*.json`）：`case_id`、`output_contract`、`files`、`data_dictionary`、`workorder` 等键名不固定，按去分隔符小写后匹配（`output_contract`/`contract`/`outputs`/`output_schema` 等价）。
2. 递归扫描输入目录：`.csv/.tsv/.txt/.dat` → 数据表；`.md/.json/.docx` → 字典与任务说明候选；`case.json` 本身不做数据表。
3. 主表选择：`case.json` 中提到文件名的优先，否则取行数最多者；其余表仍登记进 `sources`。
4. 字典优先级：独立字典文件（Markdown 管道表 / JSON / DOCX）→ `case.json` 内联 `data_dictionary/fields/columns/schema`。字段名按去标点小写匹配，允许 `NO3_mgL` 与 `no3 mg/l` 对齐。
5. 表头括号内单位（`浓度 (mg/L)`）作为该列单位提示；字典 `unit` 列优先。
6. 材料缺失（无字典、无主键、无 workorder）→ 逐条写 `pending_human`，不臆造。

## 5. 输出契约

`result.json`：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`summary`、`sources`（每文件 sha256）、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`artifacts`（路径+字节+sha256）、`unresolved_contract_fields`、`runtime`，并**原样回填 `output_contract` 的每个键**（键名不改；未匹配到值按类型给 `null`/`[]` 并记入 `unresolved_contract_fields`，不删键）。

| 产物 | 内容 |
|---|---|
| `cleaned.csv` | `__row_id`、`__src`（文件:行）、原列、`__flags`（逐行故障码） |
| `transform_log.csv` | 逐单元格：原值→新值、故障码、单位因子、可逆性、备注 |
| `field_issues.csv` | 字段级：角色/单位/缺失率/缺失原因/无效文本/越界/分布异常 |
| `stats.json` | 描述统计（样本 sd、使用/缺失/删失计数），口径写明 |
| `quality_report.md/.json` | 质量报告（骨架见 `references/quality_report_template.md`） |
| `duplicates.csv` | 被隔离的重复行（含 `duplicate_of`）与近似重复组 |
| `assertions.json` | 一致性自检：行数、缺失总数、日志↔表逐格一致 |
| `run.log` | 错误/降级/待人工确认流水 |

被移除的行只进 `duplicates.csv`，原值永不丢失。

## 6. 核心流程

读表 → 列画像（角色/数值率/唯一率/字典规格）→ 逐格归一（缺失分类 → 格式 → 单位 → 日期）→ 主键去重 → 双判据异常标记 → 描述统计 → 落盘 → 自检。策略由**字典**驱动：`range`→上下限、`missing`→哨兵码、`unit`→换算目标单位、`key`→主键、`precision`→小数位；workorder 中的"统一为某单位"会覆盖该维度的目标单位。

## 7. 故障码（与 `references/cleaning_rules.json` 一致）

`M1` 空/占位 · `M2` 未检出 · `M3` 低于定量限 · `M4` 哨兵码 · `F1` 数值格式 · `F2` 日期格式 · `F3` 编码乱码 · `U1` 单位不一致/别名 · `U2` 单位不明 · `D1` 完全重复 · `D2` 主键重复 · `D3` 近似重复 · `R1` 越界 · `R2` 分布异常 · `T1` 类型冲突。

## 8. 评分点落点

| 评分维度 | 本包证据 |
|---|---|
| 任务完成度 | 五类处理各有 CSV 列与报告章节；`field_issues.csv` 覆盖每一列 |
| 结果正确性 | 字典驱动换算与判别；只做确定性修复；单位因子可逆；报告数字由 `assertions.json` 反算 |
| 结果完整性 | 字段级清单 + 逐格日志 + 未处理缺口 |
| 可核验性 | `__src` 行定位、`sources` 哈希、`transform_log` 原值、独立 `verify.py` |
| 使用增益 | 一条命令端到端；无需人工改表；规则外置可复用 |
| 创新 | 字典推断字段级策略、逐格行定位、可逆单位/编码映射、报告↔表一致性自检、拒绝统计填补 |
| 可靠体验 | 退出码恒 0；先写 partial 再 finalize；九类异常均有降级路径 |
| 生态贡献 | 规则表 JSON、报告模板、调用说明与限制 |

## 9. 证据与定位规范

每个被改写的单元格在 `transform_log.csv` 留 `row_id + locator(文件:行) + original_value + cleaned_value + fault_codes + reversible`；每个输入文件在 `sources` 留 sha256。报告中的任何数字都必须能由 `quality_report.json.summary` 复现，并由 `assertions.json` 反算通过。

## 10. 异常降级分支

| 情形 | 处置 |
|---|---|
| 无 `case.json` | 仍扫描目录；`errors=[CASE_MISSING]`，`status=input_error` |
| `case.json` 坏 JSON | 记 `CASE_MISSING`/`CASE`，继续尝试其它 `case*.json` |
| 无表 | `status=insufficient_evidence`，`pending_human=[NO_TABLE]` |
| 空表（仅表头） | 正常产出空表 + 报告，`n_rows=0` |
| 无主键 | 键回退为整行；`pending_human=[KEY_NOT_FOUND]`，只去完全重复 |
| 全列缺失 | 该列 `missing_pct=100`，仍出现在 `field_issues.csv` |
| GBK 乱码 | 多编码打分 + GB18030 回解，写 `degradations` |
| 单位不明 | 保留原值 + `U2`，进 `uncertainty` |
| XLSX/PDF 数据表 | `degradations=[UNSUPPORTED_FORMAT]`，提示转 CSV；字典仍尽力解析 |
| 输出目录不可写 | 依次退到 `./output`、系统临时目录 |
| 行数超限 | 截断并写 `ROW_LIMIT` 降级 |

## 11. 冲突与人工确认

字典与数据矛盾（单位不符、主键重复且值冲突、日期 `d/m` 与 `m/d` 均合法、哨兵码落在物理范围内、`1,234` 可能是千分位也可能是小数）时：保留原值、打标记、写 `pending_human`/`uncertainty`，绝不擅自选一边或改数。

## 12. 预算与断点

单案例典型 < 5 s；`--rows` 控制行数上限。先写 partial `result.json`（含全部契约键），流程结束无条件 finalize 覆盖；任何阶段抛错都被捕获并落盘。

## 13. 最小调用示例（示例，非正式案例结果）

下面是一次**构造的小样例**，仅示意接口，不代表任何正式案例的答案：

输入 `in/data.csv`：`sample_id,site,NO3_mgL` / `S-01,A,12.5` / `s-01 ,A,12.5` / `S-02,B,ND` / `S-03,B,-999`，加 `in/data_dictionary.md`（`NO3_mgL | 硝酸盐 | mg/L | 0-200 | -999`）与 `in/case.json`（`case_id:"DEMO"`，`output_contract:{"cleaned_table":"..."}`）。

```bash
python3 scripts/main.py --input in --output out
```

示意输出（**示例，非正式案例结果**）：`status=ok`；`cleaned.csv` 3 行（`s-01` 判为 `S-01` 重复，隔离到 `duplicates.csv`）；`NO3_mgL` 第 2 行空白 + `M2_not_detected`，第 3 行空白 + `M4_sentinel`；`field_issues.csv` 记 `n_missing=2`、`missing_pct=66.67`；`result.json` 的 `cleaned_table`、`row_counts` 已回填。

## 14. 文件清单、版本与维护

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明 |
| `scripts/main.py` | 单入口：发现→清洗→落盘→result |
| `scripts/verify.py` | I/O 适配、产物写出、独立复核、报告渲染 |
| `references/cleaning_rules.json` | 缺失词表、单位换算表、日期格式、故障码、契约同义词 |
| `references/quality_report_template.md` | 质量报告骨架（占位符由脚本填充） |
| `references/skill_guide.md` | 完整方法、字段约定、限制、FAQ、自检清单 |

版本 `1.2.0`；规则改动只改 `cleaning_rules.json`（自带 `version`），脚本逻辑不动。维护：新增单位→加到对应维度的 `factors`；新增缺失写法→加到 `missing_tokens`。
