# 最小调用示例（示例，非正式案例结果）

> 本文件中的输入为**手工构造的示例**，输出为示意，用于说明接口与流程，**不是**任何正式测试案例的答案，也不代表平台评分结果。

## 1. 输入

`/input/case.json`：

```json
{
  "case_id": "EXAMPLE-001",
  "task_instruction": "SGLT2 inhibitors and heart failure hospitalisation in adults with type 2 diabetes",
  "output_contract": {"candidates": "ranked list", "top_k": "ids", "metrics": "P@k/nDCG@k", "notes": "free text"},
  "organizer_supplied_scope": {
    "topic": "SGLT2 inhibitors heart failure hospitalization",
    "include": ["heart failure", "hospitalization"],
    "exclude": ["pediatric"],
    "year_start": 2015, "year_end": 2024, "max_k": 3
  }
}
```

`/input/records.jsonl`（两条示例记录，其一缺摘要）：

```json
{"id":"A1","title":"Empagliflozin and cardiovascular outcomes in heart failure","abstract":"Randomized double-blind trial of 4687 adults; empagliflozin reduced hospitalization for heart failure (hazard ratio 0.65, 95% CI 0.50-0.85).","year":2015,"journal":"NEJM","doi":"10.1056/NEJMoa1504720","label":"relevant"}
{"id":"A2","title":"Renal sodium-glucose transport physiology","year":2019,"journal":"Physiol Rev"}
```

## 2. 调用

```bash
python3 scripts/main.py --input /input --out /app/output
# 可选：--k 5,10 指定指标截断；--out 指定输出目录
```

## 3. 示意输出（节选，示例）

`result.json`：

```json
{
 "case_id": "EXAMPLE-001",
 "status": "ok",
 "tiers": {"core": 1, "method": 0, "background": 0, "pending": 1, "exclude": 0},
 "top_k": ["A1", "A2"],
 "candidates": [
  {"id": "A1", "rank": 1, "tier": "core", "relevance": "direct", "relevance_score": 0.71,
   "coverage": 0.92, "design_fit": 1.0,
   "relevance_reason": "命中术语0.92，设计一致",
   "evidence": [{"quote": "empagliflozin reduced hospitalization for heart failure (hazard ratio 0.65, 95% CI 0.50-0.85)",
                 "locator": "abstract"}],
   "provenance": {"file": "records.jsonl", "json_pointer": "/0"}},
  {"id": "A2", "rank": 2, "tier": "pending", "relevance": "undetermined", "relevance_score": 0.33,
   "relevance_reason": "缺摘要", "evidence": [{"quote": "Renal sodium-glucose transport physiology", "locator": "title"}]}
 ],
 "metrics": {"gold_source": "input labels", "labelled_records": 1,
             "note": "少于3条标注，未算P@k/nDCG"},
 "contract_fill": {"candidates": "filled:same_named_field", "top_k": "filled:same_named_field",
                   "metrics": "filled:same_named_field", "notes": "null_no_source"},
 "contract_missing": ["notes"]
}
```

## 4. 判读要点

1. `A1` 有摘要、命中纳入词、设计为 RCT，进 `core`；`evidence.quote` 是摘要原文逐字片段。
2. `A2` 缺摘要 → `pending`，同时进入 `pending_human`，**不**因标题像综述就判排除。
3. `notes` 无法由材料支撑 → `null` 并在 `contract_missing` 记账，不改键名。
4. 只有 1 条标注时不计算 P@k（阈值 ≥3），避免用单点算指标。

## 5. 自查

```bash
python3 scripts/verify.py --input /input --out /app/output   # 独立复核契约/排序/证据/计数
```

预期：`verify_report.json` 中 `passed` 全为 true；若 `evidence_not_in_source` 非空，说明摘要被改写或来源错位，应修正提取而非放宽检查。
