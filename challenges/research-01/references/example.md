# 最小调用示例（示例，非正式案例结果）

> 本文件所有输入、输出、数值均为**构造的演示数据**，用于说明接口与流程，**不是**平台固定案例的结果，也不得作为正式答案使用。

## 1. 目录

```
/input/case.json          # case_id + output_contract + task_instruction
/input/paper_a.txt        # 材料：低剂量组报告
/input/paper_b.txt        # 材料：标准剂量组报告
/input/task.md            # 案例说明（被识别为 meta，不进证据语料）
```

`case.json` 片段：

```json
{"case_id": "MIN-001",
 "task_instruction": "比较低剂量与标准剂量 IL-2 对调节性 T 细胞的影响与安全性，并说明证据边界。",
 "output_contract": {"research_question": "string",
                     "sub_questions": ["{id, question, depends_on}"],
                     "evidence_matrix": ["{source_id, locator, quote}"],
                     "synthesis": {"claims": [], "conflicts": [], "gaps": []},
                     "citations": ["{n, source, locator}"],
                     "uncertainty": {}, "status": "ok|partial|insufficient_evidence|input_error"}}
```

## 2. 命令

```bash
python3 -B scripts/main.py --stage plan     --input /input --output /app/output
# → /app/output/result.json (partial)、evidence_candidates.json、source_index.json、tool_calls.jsonl

python3 -B scripts/main.py --stage finalize --input /input --output /app/output
# → research_report.md、evidence_map.csv、result.json (final)

python3 -B scripts/main.py --stage check    --input /input --output /app/output
# → selfcheck.json
```

## 3. plan 阶段示意输出（节选，示例数据）

```json
{"case_id": "MIN-001", "status": "partial",
 "sub_questions": [
   {"id": "SQ1", "type": "scope", "deps": [], "question": "研究对象与边界如何界定：核心对象（IL-2、…）"},
   {"id": "SQ2", "type": "evidence_scan", "deps": ["SQ1"], "question": "现有材料对 … 报告了哪些直接证据？"},
   {"id": "SQ5", "type": "comparison", "deps": ["SQ2", "SQ3"], "question": "在 … 之间，各结局指标的方向与量级差异是否一致？"}],
 "search_plan": [
   {"sq": "SQ1", "wave": 1, "mode": "sequential", "queries": ["\"IL-2\" \"regulatory\"", "…"], "hits": 2,
    "stop_condition": "新增支持性段落<2 / 遍历完毕 / 达候选上限"}],
 "coverage": {"n_sub_questions": 7, "n_covered": 7, "coverage_rate": 1.0, "n_candidates": 14}}
```

候选证据（`evidence_candidates.json`）每条形如：

```json
{"candidate_id": "E03", "sq": "SQ2", "source_id": "s1", "source_path": "paper_a.txt",
 "locator": "doc~p5", "quote": "Low-dose IL-2 expands regulatory T cells in patients with solid tumours …",
 "matched_terms": ["regulatory", "il-2"], "origin": "auto_retrieval"}
```

## 4. synthesis.json（Agent 自己写，节选）

```json
{"claims": [
   {"claim_id": "C1", "sq": "SQ2", "text": "…", "strength": "directly_supported",
    "evidence": ["E03"], "conditions": "…", "limits": "单臂，无对照"},
   {"claim_id": "C2", "sq": "SQ2", "text": "…", "strength": "directly_supported",
    "evidence": [{"source_id": "s2", "quote": "regulatory T cell frequency did not increase …",
                  "locator": "doc~p4"}]}],
 "conflicts": [{"conflict_id": "X1", "topic": "…", "side_a": {"label": "低剂量", "position": "…", "source_id": "s1"},
                "side_b": {"label": "标准剂量", "position": "…", "source_id": "s2"},
                "resolution": "contextual", "basis": "剂量差与瘤种差异"}],
 "gaps": [{"gap_id": "G1", "gap": "…", "basis": "material_gap", "what_would_close_it": "纳入随机对照研究"}]}
```

## 5. finalize 示意输出（示例数据）

```json
{"case_id": "MIN-001", "status": "ok",
 "citations": [{"n": 1, "source_id": "s1", "locator": "doc~p5", "quote_match": "strict", "used_by": ["C1", "C3"]}],
 "coverage": {"n_claims": 4, "quote_backlink_rate": 1.0, "claims_by_strength": {"directly_supported": 3, "inferred": 1, "insufficient": 0}},
 "verification": {"passed": 7, "total": 7, "failures": []}}
```

`selfcheck.json`：`{"passed": 7, "total": 7, "failures": []}`。

## 6. 演示一条失败路径（重要）

把 C2 的 quote 改成原文没有的句子（例如 `regulatory T cells doubled after low dose therapy`）后重跑 finalize，得到：

```json
{"status": "partial",
 "synthesis": {"claims": [{"claim_id": "C2", "strength": "insufficient", "citations": [],
                           "quote_failures": ["regulatory T cells doubled after low dose therapy"]}]},
 "errors": [{"stage": "verify_quote", "error": "C2: quote not in s2: 'regulatory T cells doubled …'"}],
 "pending_human": [{"item": "unmatched_quote:C2", "why": "not verbatim in s2",
                    "action": "supply a verbatim passage or drop the claim"}]}
```

即：**编造的引用不会进入证据表**，结论自动降级为 `insufficient`，状态降为 `partial`，并进入人工处置清单。
