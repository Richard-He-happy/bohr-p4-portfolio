# 最小调用示例

> **本文件全部为示例，非正式案例结果，也不是组织方白板。** 用于说明接口、产物结构与自检方式。

## 1. 最小输入

`/input/case.json`

```json
{
  "case_id": "example-001",
  "task_instruction": "对稿件做结构诊断，覆盖六个维度，给出可执行修改动作，不要改写全文。",
  "output_contract": {
    "case_id": null,
    "deliverable": null,
    "preserved_facts": [],
    "evidence_map": [],
    "change_log": [],
    "dimension_coverage": null,
    "noted_by_organizer": null
  },
  "organizer_workorder": ["Cover all six structural dimensions with locators",
                          "Do not rewrite the manuscript"]
}
```

`/input/manuscript.md`（节选，真实使用时为完整稿件）

```markdown
## Introduction
Deficit irrigation stabilises maize production [1]. Here we ask whether soil moisture memory
explains yield variability.

Water availability is the main driver of crop productivity in drylands.

## Results
Memory was associated with yield (r = 0.61, Fig. 3).

## Conclusion
Soil moisture memory determines maize yield, and all plots benefited [1].
```

## 2. 调用

```bash
python3 -B scripts/main.py --input /input --out /app/output
python3 -B scripts/verify.py --out /app/output --input /input
```

## 3. 示意输出（示例）

`structural_review.json`（结构示意，数值仅示例）

```json
{"case_id": "example-001",
 "manuscript": {"chapters": 3, "paragraphs": 4, "words": 74, "truncated": false},
 "dimension_coverage": {
   "research_question_alignment": {"status": "no_issue_with_evidence", "finding_ids": []},
   "section_structure": {"status": "findings", "finding_ids": ["F01"]},
   "argument_chain": {"status": "findings", "finding_ids": ["F02"]},
   "paragraph_relations": {"status": "no_issue_with_evidence", "finding_ids": []},
   "duplication": {"status": "no_issue_with_evidence", "finding_ids": []},
   "conclusion_boundary": {"status": "findings", "finding_ids": ["F03"]}},
 "findings": [
  {"finding_id": "F01", "dimension": "section_structure", "severity": "high",
   "locator": "C03-P001", "quote": "Soil moisture memory determines maize yield, and all plots benefited [1].",
   "diagnosis": "全文缺少「方法与材料」章：稿件在最后一个可见段落处结束……",
   "evidence_for_judgment": "已识别章节角色为 ['conclusion','introduction','result']，未出现 method 角色；全文 4 个段落。",
   "confidence": "high"},
  {"finding_id": "F02", "dimension": "argument_chain", "severity": "high",
   "locator": "C02-P001-S01",
   "quote": "Memory was associated with yield (r = 0.61, Fig. 3).",
   "diagnosis": "正文引用了 [1]，但参考文献列表里没有对应条目……",
   "evidence_for_judgment": "正文引用编号 1 个，参考文献条目 0 条，缺号 [1]。",
   "confidence": "high"},
  {"finding_id": "F03", "dimension": "conclusion_boundary", "severity": "high",
   "locator": "C03-P001-S01", "quote": "Soil moisture memory determines maize yield, and all plots benefited [1].",
   "diagnosis": "结论使用了因果动词，但方法与结果只给出了相关性表述……",
   "evidence_for_judgment": "该句命中因果动词；方法/结果章命中相关性表述（associat, correlat），未命中干预/随机化/对照设计。",
   "confidence": "high"}],
 "actions": [
  {"action_id": "A01", "finding_id": "F01", "operation": "insert",
   "from_locator": "C03-P001", "to_locator": "C03-P001", "priority": "P1", "executable": true,
   "expected_effect": "在最后一个可见段落之后补一节「方法与材料」……",
   "risk": "新增章节会牵动后续引用编号，需要作者确认。"}],
 "grounding": {"findings_total": 3, "quote_verbatim_hit": 3, "hit_rate": 1.0}}
```

`result.json` 关键字段（示例）

```json
{"case_id": "example-001", "status": "partial",
 "deliverable": {"primary": "/app/output/edit_plan.md", "editable": true, "format": "markdown+json"},
 "preserved_facts": [{"fact_id": "PF01", "kind": "number", "quote": "r = 0.61", "locator": "C02-P001-S01"}],
 "evidence_map": [{"claim_id": "F03", "locator": "C03-P001-S01", "quote": "Soil moisture memory determines maize yield, and all plots benefited [1]."}],
 "change_log": [{"change_id": "CH01", "action_id": "A01", "original_quote": "Soil moisture memory determines maize yield, and all plots benefited [1].",
                 "revised_quote": null, "change_type": "structural_action_proposed", "status": "proposed_not_applied"}],
 "metrics": {"dimensions_covered": 3, "dimensions_no_issue_with_evidence": 3, "findings": 3,
             "actions": 3, "quote_hit_rate": 1.0, "estimated_revision_rounds": 1},
 "noted_by_organizer": null, "contract_unfilled_keys": []}
```

`edit_plan.md` 片段（示例）

```markdown
# 结构修改方案（edit_plan）

- case_id: `example-001`
- 规格: 3 条发现 → 3 个可执行动作
- 用法: 按 P1→P3 顺序执行；每条动作给出 from/to locator，可在稿件中直接定位。

## P1 · 先改：影响论证是否成立

### A01 · 章节结构 · 严重度高

- 位置: `C03-P001`
- 原文: > Soil moisture memory determines maize yield, and all plots benefited [1].
- 判断: 全文缺少「方法与材料」章……
- 依据: 已识别章节角色为 [...]，未出现 method 角色；全文 4 个段落。
- 动作: `insert` — 在最后一个可见段落之后补一节「方法与材料」……
- 风险: 新增章节会牵动后续引用编号，需要作者确认。
```

`verify.py` 示意输出（示例）

```json
{"pass": true, "checks": [{"check": "six_dimensions", "pass": true},
 {"check": "finding_action_join", "pass": true}, {"check": "actions_valid", "pass": true}],
 "counts": {"findings": 3, "actions": 3, "dimensions_with_findings": 3, "quote_hit_rate": 1.0}}
```

## 4. 从示例能看出的接口约定

1. **一条 finding 只对应一条 action**，`finding_id` 双向可 join。
2. 每条 finding 的 `quote` 都能在 `manuscript.md` 中逐字找到（上例 "Soil moisture memory determines maize yield, and all plots benefited [1]."）。
3. `no_issue_with_evidence` 是"检查过且无发现"，不是漏项；`checked` 里写检查对象数量。
4. 未确认的部分（如需要作者补写的文献、需作者决定是否收窄的措辞）出现在 `pending_human.json`，不出现在事实陈述里。
5. 全程不产出 `manuscript.md` / `rewrite.md` 等改写稿；`change_log.revised_quote` 恒为 null，
   只记录"提出了哪种结构动作、依据哪句原文"。
