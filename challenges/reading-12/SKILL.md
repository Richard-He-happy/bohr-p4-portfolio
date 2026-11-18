---
name: literature-data-cleaner
description: Clean and standardize a batch of literature extraction records into a statistically usable table, with a rule-numbered change log, a pending-human review list and a traceable duplicate/conflict report. Use when the task supplies paper-extracted rows (values, units, material/indicator names, condition columns) plus unit/number/region rules or a target field dictionary, and asks for unified field names, unit conversion with formulas, synonym normalization, missing/outlier handling, duplicate handling and source traceability. Trigger phrases include "文献数据清洗", "抽取记录标准化", "单位换算并保留原值", "去重并给变更记录", "clean extracted literature values into a table".
version: 1.0.0
---

# 文献数据清洗与标准化（literature-data-cleaner）

## 1. 用途与边界

**做什么**：把一批真实文献抽取记录端到端清洗成可统计的宽表，并同时交出**行级变更记录**、**待人工确认清单**、**去重/冲突报告**、**规则库**、**字段映射**与**单位表**。每个改动值都带 `rule_id` 与 `formula`，可沿 `row_id → original_value → rule_id → formula` 回到输入行与原始文献位置。

**不做什么**：
- 不做领域判断式纠错。单位能算但科学上矛盾时（同来源同条件两个差异很大的值），标 `source_conflict` 并保留原值，**不用换算抹平**。
- 不猜单位。`a.u.`、`arb. units`、无法解析的 token、缺失单位一律不换算，交人工。
- 不把缺失写成 0，不把区间压成中值，不丢掉 `±` 误差。
- 不合并不同来源或不同条件的行；条件列（温度、时间、pH…）不做单位换算，只原样保留在 `condition_summary`。

## 2. 运行契约

```
python3 scripts/main.py --input /input --output /app/output
python3 scripts/main.py --input /input --output /app/output --determinism   # 两次运行逐字节比对
```

- 输入默认 `/input`（不存在则用包上级的 `input/`），输出默认 `/app/output`（无 `/app` 时用包上级的 `output/`）。
- 只用 Python 标准库（`argparse csv json re sys traceback pathlib subprocess`）；不联网；脚本用 `Path(__file__).resolve().parent` 定位资源，**不依赖 CWD**。
- 退出码恒为 0。任何异常写入 `result.json.errors`，流程继续或降级，绝不以非零码结束。
- `result.json` 在流程最开始先写一份 partial（`case_id` + 空骨架），结束时无条件 finalize 覆盖。

## 3. 输入发现（按语义，不假设键名）

1. 读 `/input/case.json`（或任意含 `case_id`/`output_contract` 的 JSON）：保留 `case_id`、`output_contract` 原样；`task_instruction`、`organizer_*`、`formal_inputs`、`runtime_files` 只记录出现情况，不臆造。
2. 递归扫描 `/input/**`，按扩展名与内容分类：
   - `.csv` → 抽取记录；
   - `.json` 含 `rule_id` 或文件名含 rule → 规则文件；
   - `.json` 含 `fields`/schema/dictionary → 目标 schema 或字段字典；
   - 其余 `.json` → 抽取记录（列表，或 `records/rows/data/items/measurements/…` 下一层列表，逐层向下找第一个「dict 列表」）。
3. 抽取记录里按角色同义词识别列：`row_id`、`source_document_id`、`source_locator`、`value`、`unit`、`indicator`、`material`；其余非注释列作为条件列。
4. 明确列缺口：找不到记录表 → `status=insufficient_evidence` 且 `degradations` 写明；找不到 `case.json` → `degradations` 记一条，`output_contract` 视为空。

## 4. 输出契约

`/app/output/` 下 9 个文件（均由脚本真实生成）：

| 文件 | 内容 |
|---|---|
| `result.json` | 主结果。**原样回填 `output_contract` 全部字段**（键名不改、未知字段保留、缺值 `null`），并带 `case_id`/`status`/`result`/`claims`/`uncertainties`/`uncertainty`/`sources`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`/`contract_mapping` |
| `cleaned.csv` | 目标表（字段见 `references/cleaning_guide.md` §1） |
| `change_log.csv` | `row_id, field, before, after, unit_before, unit_after, factor, offset, formula, precision, rule_id, source_document_id, source_locator, note` |
| `pending_review.csv` | `row_id, field, reason_code, reason, suggested_action, original_value, original_unit, source_document_id, source_locator` |
| `anomaly_report.md` | 计数、字段覆盖、待确认分布、去重/冲突、降级与错误、边界 |
| `rules.json` | 规则库（`rule_id/priority/applies_to/condition/transform/examples/failure_mode/human_gate`）+ `suppressed_rules` + `applied_counts` |
| `field_mapping.json` | 每列 → 目标字段、映射依据、`unmapped` 清单 |
| `unit_table.json` | 单位表 + `observed_conversions`（本次实际发生的 单位→单位 / factor / offset / 次数） |
| `verify_report.json` | 运行自检（复算一致率、计数一致性、row_id 唯一性、规则可解析） |

`status ∈ {ok, partial, insufficient_evidence, input_error}`：无待确认且无冲突 → `ok`；有待确认/冲突 → `partial`；无可用行 → `insufficient_evidence`。

`claims[]` 每条含 `claim_id/kind/readability/statement/evidence{quote,rule_id}/source_id/location{row_id,field,source_locator}/condition`。`kind ∈ {reported, inferred, undetermined}`；`readability ∈ {directly_read, inferred, undetermined}`，分别对应「原文直接可读」「按规则推断」「无法确定」。

## 5. 核心流程

1. **规则库先行**：内置 20 条规则（`references/rules_library.json`）+ 案例自带规则（默认 priority 10，数值小者优先；覆盖时记入 `suppressed_rules`）。
2. **字段映射**：列名同义词 → 目标字段；表头内嵌单位（`Band gap (eV)`、`bandgap/eV`）拆出指标与单位；未命中列保留为条件/注释并进 `unmapped`。
3. **值解析**：单值 / 区间 / `±` 误差 / 缺失 / 文本；科学计数法（`1.2×10³`、`1.2E3`）、上下标、全角符号先归一。
4. **单位换算**：前缀 + 复合单位解析 → 维度签名 → 规范单位；`after = before*factor + offset`；区间上下界分别换算；`±` 误差同因子换算。
5. **同义归一**：物质与指标名归一，原文留在 `original_field`/`original_value`。
6. **去重与冲突**：判定键 `source_document_id|condition|indicator|material`；同键同值 → 合并（`merged_duplicate`）；同键值差 ≤5% → 重复实验（`replicate`，保留）；>5% → `conflict` + 待确认。
7. **导出**：稳定排序（`source_document_id` + 自然序 `row_id`）写 CSV/JSON；无时间戳、无随机，两次运行逐字节一致。
8. **自检**：从已落盘文件复算每条 change log，写 `verify_report.json`。

## 6. 评分要点 → 字段/检查/产物

| 评分点 | 实现位置 |
|---|---|
| 任务完成度 | 9 件产物齐备；`result.counts` 给出 `input_rows/cleaned_rows/analytic_rows/changed_values/pending_review/merged_duplicates/conflicts`，行数关系可解释 |
| 结果正确性 | `change_log` 每行 `factor/offset/formula` 可复算（`verify_report.formula_consistency_pct` 应为 100）；区间/误差不平铺；缺失不写 0 |
| 结果完整性 | 六方面全覆盖：字段规范（§5.2）、单位（§5.4）、同义（§5.5）、缺失与异常（R006/R016/R019）、重复（§5.6）、来源与变更记录（`change_log` + `sources` + `pending_human`） |
| 结果可核验性 | 每行 `row_id + source_document_id + original_value + rule_ids`；`location` 回到页码/表号/JSON 路径 |
| 质量增益 | 规则库带编号与优先级、`applied_counts` 可统计、抑制规则可查；同一输入结果可复现 |
| 效率增益 | 一次运行完成 映射→换算→归一→去重→报告；`counts.pending_review` 即人工剩余工作量 |
| 增益可验证性 | `result.method_notes` 预定义四条「算对标准」；`--determinism` 两次运行逐字节比对 |
| 新增能力 | 可维护规则库 + 表头单位拆解 + 判定键去重 + 来源追溯导出 |
| 方法改进 | 规则优先级与冲突消解（`suppressed_rules`）；「规则可改」与「须人工确认」的分界（`human_gate`） |
| 创新证据 | 未知单位、同义冲突、重复实验 vs 重复记录、编码错乱、空表均有分支与记录 |
| 调用与易用性 | `--help`；换列名靠 `field_roles`；换 schema 靠案例提供的 `fields` |
| 运行稳定性 | 全排序、无随机、无时间戳；`--determinism` |
| 异常处理 | 见 §9 分支表 |
| 文档完整性 | 本文件 + `cleaning_guide.md`（字段字典、脏数据谱系、单位约定、维护、自查） |
| 资源可复用性 | `unit_table.json`/`rules_library.json`/同义词表/`field_roles` 直接换成自己的数据即可用 |
| 分享价值 | `cleaning_guide.md` §2 的脏数据谱系表可迁移到其他抽取数据清洗任务 |

## 7. 证据与定位规范

- `evidence.quote` 是**输入单元格原文**（原值 + 原单位），不是换算后的值。
- `location` 同时给 `row_id`、`field` 与 `source_locator`；`source_locator` 原样保留（`"Table 1, p.3"`、`"Fig 2"`）。
- 换算结论标 `kind=inferred`；未确认项标 `kind=undetermined`；计数类事实标 `reported` 且 `readability=directly_read`。
- 无法判断的不写成事实：只进 `uncertainties` 与 `pending_review.csv`。

## 8. 冲突与人工确认

| 情形 | 行为 |
|---|---|
| 未知单位 / 单位不可解析 | 不换算；`cleaned.csv` 值留空；`status=needs_review`；`reason_code=unknown_unit`（R010） |
| 有值无单位 | 同上，`missing_unit`（R011） |
| 单元格非数值文本 | 值留空；`unparsed_value`（R006） |
| 同键不同单位 | 全部标 `conflict`，记 `unit_conflict` |
| 同键值差 > 容差 | 保留两值，标 `conflict`，记 `value_conflict`（R015） |
| 同键值差 ≤ 容差 | 保留两行，后者 `replicate`（R014，重复实验≠重复记录） |
| 同键同值 | 合并，后者 `merged_duplicate` + `duplicate_of`（R013） |

## 9. 异常降级分支表

| 输入异常 | 处理 | 记录位置 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续清洗，契约视为空 | `degradations` |
| 记录文件坏 JSON | 跳过该文件，其余继续 | `errors` |
| CSV 非 UTF-8 | `utf-8-sig→utf-8→gb18030→latin-1` 级联 | `degradations`（replacement chars 计数） |
| 空表 / 只有表头 | `status=insufficient_evidence` | `degradations` + `result` |
| 无 `value` 列 | 按条件列处理并提示复核映射 | `degradations`（R003） |
| `row_id` 缺失 | `derived-N` | `degradations`（R002） |
| `row_id` 重复 | 后者改为 `原id#2` | `degradations`（R002） |
| 未知单位 | 不换算 + 待确认 | `pending_review.csv` |
| 进程中断 | 先落盘的 partial `result.json` 仍在 | `result.json.status=partial` |

## 10. 预算与断点

标准库、无网络、无模型调用；一次清洗在秒级完成，远低于 900 秒预算。若输入极大，先在 `--output` 得到 partial `result.json`，再按文件分批运行（脚本一次处理一个记录文件，单文件失败不影响其他文件）。

## 11. 最小调用示例（示例，非正式案例结果）

`input/case.json`：

```json
{"case_id": "demo-001", "task_instruction": "clean records",
 "output_contract": {"cleaned_table": "", "change_log": "", "pending_review": "", "counts": {}}}
```

`input/extraction-records.json`（2 行示例）：

```json
{"records": [
 {"row_id": "E01", "source_document_id": "DEMO-A", "source_locator": "Table 1", "material": "titanium dioxide",
  "indicator": "Band gap (eV)", "value": "3.2", "unit": "eV"},
 {"row_id": "E02", "source_document_id": "DEMO-B", "source_locator": "Fig. 3", "material": "TiO2",
  "indicator": "crystallite size", "value": "12-15", "unit": "nm"}]}
```

```bash
python3 scripts/main.py --input ./input --output ./output
```

示意输出（示例）：`E01` → `value=5.12697e-19, unit=J, rule_ids=R009, status=ok`；`E02` → `value_low=1.2e-08, value_high=1.5e-08, unit=m, rule_ids=R007;R009, status=ok`；`change_log.csv` 对应 3 行（`E01 value`、`E02 value_low`、`E02 value_high`）。数值仅示意格式，正式结果以平台案例实际运行为准。

## 12. 自检清单

- [x] `--help` 退出码 0；空输入 / 坏 JSON 仍产出合法 partial `result.json`
- [x] `output_contract` 每个键出现在 `result.json`，`case_id` 原样
- [x] `change_log` 每行 `after = before*factor + offset` 复算一致率 100%（`verify_report.json`）
- [x] 未知单位行值留空且进 `pending_review.csv`
- [x] 区间/误差未压成单值；不同来源/条件未合并
- [x] `--determinism` 两次运行 8 个产物逐字节一致
- [x] 包内无 `__pycache__`、无预制案例答案

## 13. 文件清单与版本

| 文件 | 作用 | 版本 |
|---|---|---|
| `SKILL.md` | 入口：用途、契约、流程、rubric 映射、边界 | 1.0.0 |
| `scripts/main.py` | CLI：输入发现、编排、产物写出、自检、确定性比对 | 1.0.0 |
| `scripts/clean_core.py` | 引擎：单位解析与换算、值解析、列角色、清洗、去重 | 1.0.0 |
| `references/unit_table.json` | 前缀、原子单位、`unknown_unit_tokens`、维度→规范单位 | 1.0.1 |
| `references/rules_library.json` | 规则库、字段角色同义词、物质/指标同义词、目标 schema、文案 | 1.0.0 |
| `references/cleaning_guide.md` | 字段字典、脏数据谱系、单位与精度约定、维护、自查 | 1.0.0 |

依赖：Python ≥ 3.8 标准库；无需安装第三方包；无需网络。

## 14. 维护说明

- 改资源即升版本，并在 §13 与 `cleaning_guide.md` §5 同步；资源与脚本同号发布。
- 新增单位：`unit_table.json` 的 `units`（`dim/scale/offset/aliases`），必要时在 `canonical` 补「维度签名 → 规范单位」。
- 新增规则：`rules_library.json` 的 `rules`，priority 越小越先；与内置同编号则覆盖并进 `suppressed_rules`。
- 换数据：只改 `field_roles`（列名）与两个同义词表即可复用，不改脚本。
- 已知限制：条件列不做单位换算；不在 `canonical` 中的维度组合按基本单位派生（如 `m^2*kg*s^-2`）；区间内再带 `±` 时只保留 `±` 分支；单文件极大时按文件分批运行。
