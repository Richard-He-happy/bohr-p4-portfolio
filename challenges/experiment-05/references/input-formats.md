# 输入格式、字段含义与产物结构

## 1. 输入目录

```
/input/
  case.json            # 案例定义（必需，缺失时降级）
  task.md              # 题面文本（跳过）
  material.json        # 材料清单（跳过）
  artifacts/           # 实测数据（CSV/TSV/XLSX/…，可多层子目录）
  *.pdf / *.png        # 文献或图谱（登记为缺口，不读数）
```

发现规则：递归扫描输入目录，跳过 `case.json`、`task.md`、`material.json` 与隐藏文件；
最多登记 200 个文件（超出记 `SCAN_TRUNCATED`）。文件类型按**文件头**判定（`%PDF`、`PK\x03\x04`
再按 zip 内 `xl/` 或 `word/` 区分、PNG 魔数），扩展名仅作兜底。

## 2. `case.json` 常用字段

| 字段 | 用途 | 缺失时 |
|---|---|---|
| `case_id` | 原样写入 `result.json.case_id` | 记 `UNKNOWN` |
| `topic` / `domain` / `goal` | 结果头部标识（也接受 `objective`/`question`） | 空字符串 |
| `output_contract` | 待回填结构（也接受 `outputContract`） | 不回填，`output_contract: {}` |
| `equipment[{name,model,range,精度}]` | 写入 `protocol.equipment` | 空数组 |
| `reagents[{name,规格,库存}]` | 写入 `protocol.materials` | 空数组 |
| `time` / `budget` / `personnel` | 写入 `protocol.schedule` | 空数组 |
| `constraints` / `existing_protocol` / `raw_files` | 仅记录，不参与判定 | — |

字段匹配为**语义别名**：键名先正则归一化（去除非字母数字、转小写），再做别名集合匹配，
因此 `caseId`、`case_id`、`Case ID` 等价；未知键保留原值。

## 3. 表结构识别

1. 同一文件可有多个表：CSV/TSV 一个表；XLSX 每个 worksheet 一个表（表名 `sheet:第N表`）。
2. 表头行 = 前 6 行中第一行「至少 2 个非空单元格」的行；若该行过半是数字，则视为无表头数据表
   （列名用 `col1..colN`，表头行也算数据）。
3. 列类型按取值比例判定：非空值中 ≥70% 可解析为数字 → `num`，否则 `cat`，全空 → `empty`。
4. 数字解析容忍：千分位逗号、`−`（U+2212）负号、单位后缀（`12.5 mg`）、不可见空格；
   拒绝占位符（`ND`、`>`、`saturat*`、`超量程`、`溢出`、`饱和`）。

## 4. 产物结构

### `result.json`（顶层）

```jsonc
{
  "case_id": "…", "status": "ok|partial|insufficient_evidence|input_error",
  "skill": {"name": "…", "version": "1.0.0"},
  "topic": "", "domain": "", "goal": "",
  "summary": "…",                       // 一句话结论 + 计数
  "trend": [], "anomalies": [], "causes": [], "recheck": [], "next_experiment": [],
  "five_sections": {"trend": [], "anomalies": [], "causes": [], "recheck": [], "next_experiment": []},
  "protocol": {},                        // hypotheses/variables/controls/steps/parameters/…
  "hypotheses": [], "variables": {}, "controls": [], "materials": [], "equipment": [], "schedule": [],
  "parameters": {}, "thresholds": {}, "risks": [], "validation": {}, "feasibility": {},
  "groups": [], "comparison": [], "binding": null, "clip": [],
  "sources": [], "uncertainty": [], "pending_human": [], "errors": [], "degradations": [],
  "counts": {}, "runtime": {}, "artifacts": [], "output_contract": {}, "changes": []
}
```

### 关键子结构

- `anomalies[]`：`id, type, verdict, object, metric, value, reference, dev_pct, robust_z, threshold,
  n_ref, batch, file, locator, quote`
  - `type`：`outlier`（单点稳健 z）、`series_outlier`（跨曲线比较）、`oos_limit`（文本声明的限度超限）
  - `verdict`：`confirmed_outlier` | `watch` | `out_of_spec`
  - `locator`：`文件 | 表 | row N | col 列名`，可直接回查
- `causes[]`：`rank, id, candidate, mechanism, support_evidence[], counter_evidence[], testability,
  test, supported_if, refuted_if, caveat, score`
- `recheck[]`：`id, priority(P1/P2), action, file, field, condition, if_confirmed, if_refuted, effort`
- `next_experiment[]`：`id, change, rationale, discriminating_outcome, closes_gap, relative_cost`
- `sources[]`：`id, file, kind, bytes, parsed`
  - `parsed`：`workbook` | `delimited` | `not-read` | `error`

### `protocol.md`

下一轮实验方案，含：假设（H1…，附验证方式与成立/否定判据）、变量（自变量/因变量/控制）、
对照、步骤、判读标准、资源（仪器/材料/排期）、风险与处置、未解释缺口。

### CSV 表

| 文件 | 列 |
|---|---|
| `anomaly_table.csv` | id,type,verdict,object,metric,value,reference,dev_pct,robust_z,n_ref,batch,file,locator,quote |
| `recheck_checklist.csv` | id,priority,action,file,field,condition,if_confirmed,if_refuted,effort |
| `risk_table.csv` | risk,trigger,mitigation,alternative |

UTF-8 BOM 编码，Excel 直接可读；`None` 写空串。

## 5. `protocol` 追加字段（题面「实验方案 / 依据与风险 / 确认项」对应）

- `confirmations[]`：`item, status, need`。固定四项——设备可用性、安全、伦理、专家确认，
  `status` 恒为 `unconfirmed`，`need` 写清由谁确认什么。**未确认内容不得写成可执行事实。**
- `basis[]`：`choice, source, locator, quote`。数据侧给 `anomalies[].locator` + 逐字 `quote`；
  方法侧给 `scripts/analysis.py#CFG` 与阈值原文（如 `z=3.5 cv=30 n=3`）。材料未给的参数不填。

`counts` 键：`files, tables, anomalies, confirmed, causes, recheck, next, gaps, errors`。
