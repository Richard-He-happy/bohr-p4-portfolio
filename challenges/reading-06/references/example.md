# 端到端示例（示例，非正式案例结果）

> 全部数据为**合成示例**，仅演示接口与流程，不是真实论文或正式评测结果。

## 1. 输入

`/input/case.json`

```json
{"case_id": "SYN-001", "output_contract": {"case_id": "keep",
  "status": "answered|partial|insufficient_evidence|input_error",
  "result": "fields", "claims": "claims with evidence", "uncertainties": "gaps"}}
```

`/input/target-fields.json`

```json
{"target_fields": [
  {"field_id": "F1", "label": "IC50 of compound A", "aliases": ["IC50"]},
  {"field_id": "F2", "label": "sample size", "aliases": ["participants"]},
  {"field_id": "F3", "label": "funding source", "aliases": ["funding", "grant"]}]}
```

`/input/material.md`（节选）

```
Compound A inhibited the kinase with an IC50 of 12.4 nM (95% CI 10.1-15.2 nM)
after 30 min pre-incubation at 25 degrees C.
We enrolled n = 48 participants across two centres.
```

## 2. init

```
$ python3 -B $S/main.py init
== init ==
input: /input
case_id: SYN-001
contract keys: case_id, status, result, claims, uncertainties
materials=1 target_fields=3
  M1   material.md    md  paras=3  text
  field F1   IC50 of compound A
...
-> /app/output/result.json (partial), /app/work/workorder.md
```

`init` 先写 partial `result.json` 再建索引；`workorder.md` 汇总任务、字段表、材料表与契约键。

## 3. 读原文

```
$ python3 -B $S/main.py show --para M1-p0002
M1-p0002 [M1 p?] Compound A inhibited the kinase with an IC50 of 12.4 nM (95% CI 10.1-15.2 nM)
after 30 min pre-incubation at 25 degrees C.
```

## 4. 写 `/app/work/draft.json`（节选）

```json
{"fields": [
 {"field_id": "F1", "label": "IC50 of compound A", "value": 12.4, "unit": "nM",
  "statistic": "95% CI 10.1-15.2 nM", "condition": "30 min pre-incubation at 25 degrees C",
  "comparator": "", "source_kind": "text", "status": "reported",
  "quote": "Compound A inhibited the kinase with an IC50 of 12.4 nM (95% CI 10.1-15.2 nM)",
  "locator": {"material_id": "M1", "paragraph_id": "M1-p0002"},
  "reasoning": "点估计 12.4 nM 取自同一句；CI 与温度条件同句给出，未换算"},
 {"field_id": "F2", "label": "sample size", "value": "48", "unit": "participants",
  "status": "reported", "quote": "We enrolled n = 48 participants across two centres.",
  "locator": {"material_id": "M1", "paragraph_id": "M1-p0003"},
  "reasoning": "入组句显式给出 n"},
 {"field_id": "F3", "label": "funding source", "value": null, "status": "not_reported",
  "quote": "", "locator": "",
  "reasoning": "在 M1 全文检索 funding/grant/support/acknowledgement，无资助声明"}]}
```

## 5. check

```
$ python3 -B $S/main.py check
== check == draft=/app/work/draft.json fields=3 rows=3
WARN  F3  no_locator  locator empty
=> PASS (0 errors, 1 warnings) /app/work/check_report.json
```

quote 被改写（`12.4`→`12`）会得 `number_not_in_quote`；原文查不到则 `quote_not_found`（error），须回原文复制。

## 6. build 产物（示意）

```
$ python3 -B $S/main.py build
== build ==
case_id: SYN-001 | status: answered
fields=3 reported=2 not_reported=1 conflict=0 failed=0 fallback=0 quote_failed=0
```

`/app/output/result.json`（键齐全，节选）：

```json
{"case_id": "SYN-001", "status": "answered",
 "result": {"field_results": [{"field_id": "F1", "status": "reported", "value": 12.4,
   "unit": "nM", "quote": "Compound A inhibited the kinase with an IC50 of 12.4 nM (95% CI 10.1-15.2 nM)",
   "locator": "material_id=M1; paragraph_id=M1-p0002", "verification": "quote_strict"}],
   "counts": {"target_fields": 3, "reported": 2, "not_reported": 1, "source_conflict": 0,
              "extraction_failed": 0, "quote_failed": 0, "coverage_pct": 100.0}},
 "claims": [{"id": "C-F1", "kind": "extracted_value", "quote": "…IC50 of 12.4 nM…",
             "quote_verification": "quote_strict"}],
 "uncertainties": [{"field_id": "F3", "status": "not_reported",
                    "basis": "在 M1 全文检索 funding/grant/support/acknowledgement，无资助声明"}],
 "sources": [{"material_id": "M1", "name": "material.md", "kind": "md", "paragraphs": 3}],
 "pending_human": [], "errors": [], "degradations": [], "changes": [{"action": "finalize"}],
 "runtime": {"skill_version": "1.0.0", "phase": "build"}}
```

另有 `extraction.json`（全量）、`extraction.csv`（每字段一行）、`extraction.md`（人读表）。

## 7. 反例（避免）

| 错误做法 | 后果 |
|---|---|
| 把 `12.4 nM` 写成 `12 nM` | `number_not_in_quote` warning，数值失真 |
| 没有资助声明就写 `value: 0` | 违反"缺失 ≠ 0"，应为 `not_reported` |
| quote 用自己的话改写 | `quote_not_found`，必须回原文复制 |
| 只写"结果段"当定位 | `no_locator`，无法复核 |
| 表格与正文不一致时只保留一个值 | 丢证据，应为 `source_conflict` 保留双方 |
| 无草稿直接交结果 | `fallback_used`、覆盖率 0、状态 `partial` |
