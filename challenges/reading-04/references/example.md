# 最小调用示例（示例，非正式案例结果）

> 本节材料为自拟短文本，输出为「示例，非正式案例结果」，只用于说明接口与字段关联，
> 不作为任何隐藏案例的效果证明或答案来源。正式案例的论文与九道问题由组织方保管。

## 1. 示例输入

`/input/case.json`（键名可不同，脚本按语义识别）：

```json
{
  "case_id": "demo-case",
  "paper_id": "DEMO-PAPER",
  "material_version": "v3",
  "output_contract": {"case_id": null, "status": null, "result": null, "claims": [], "uncertainties": []},
  "questions": [
    {"question_id": "Q1", "question": "最高抗拉强度是多少，在什么热处理温度下获得？"},
    {"question_id": "Q2", "question": "该研究采用什么方法细化晶粒，效果如何？"}
  ],
  "materials": {"paragraphs": [
    {"paragraph_id": "P1", "section": "abstract",
     "text": "The tensile strength reached 1250 MPa at 850 C for 1 h, with an elongation of 12%."},
    {"paragraph_id": "P2", "section": "methods",
     "text": "Grain refinement was achieved by severe plastic deformation combined with recovery annealing."},
    {"paragraph_id": "P3", "section": "results",
     "text": "The average grain size decreased from 18 um to 2.4 um after annealing at 850 C."}
  ]}
}
```

## 2. 调用

```bash
python3 -B scripts/main.py --input /input --out /app/output
```

终端摘要（示例）：

```
[literature-qa 1.0.0] case=demo-case status=ok q=2 claims=5 quote_hit=1.0 selfcheck=True fails=[]
```

## 3. 示例输出（节选，字段已截短）

```json
{
  "case_id": "demo-case", "paper_id": "DEMO-PAPER", "material_version": "v3", "status": "ok",
  "result": {"answers": [{
      "question_id": "Q1",
      "question": "最高抗拉强度是多少，在什么热处理温度下获得？",
      "status": "answered",
      "answer": "【子问1】最高抗拉强度是多少，在什么热处理温度下获得\n数值：The tensile strength = 1250 MPa；with an elongation = 12 %。\n原文依据：\"The tensile strength reached 1250 MPa at 850 C for 1 h, with an elongation of 12%.\"（P1）\n成立条件：at 850 C for 1 h, with an elongation of 12%。",
      "conditions": ["at 850 C for 1 h, with an elongation of 12%（P1）"],
      "claims": [{
        "claim_id": "Q1-S1-C1", "kind": "reported", "readability": "directly_read",
        "text": "The tensile strength = 1250 MPa；with an elongation = 12 %",
        "source_id": "DEMO-PAPER",
        "conditions": ["at 850 C for 1 h, with an elongation of 12%"],
        "evidence": [{"paper_id": "DEMO-PAPER", "paragraph_id": "P1", "section": "abstract",
                      "locator": "/paragraphs/0", "quote": "The tensile strength reached 1250 MPa at 850 C for 1 h, with an elongation of 12%.",
                      "char_start": 0, "quote_verified": true, "quote_words": 14}]}],
      "unanswered_parts": [],
      "evidence_paragraph_ids": ["P1"]}],
    "unanswered_parts": [],
    "coverage": {"paragraphs_supplied": 3, "paragraphs_indexed": 3, "paragraphs_cited": 3,
                 "sections_read": [{"section": "abstract", "paragraphs": 1}],
                 "sections_unread": [], "unread_reason": [],
                 "not_supplied": [], "note": "材料为已抽取文本，无页图/像素"}},
  "counts": {"questions": 2, "answered": 2, "partial": 0, "insufficient_evidence": 0,
             "claims": 5, "evidence": 5, "evidence_verified": 5, "quote_hit_rate": 1.0},
  "uncertainties": [], "pending_human": [], "errors": [], "degradations": []
}
```

对应关系：`question_id`（Q1）→ `answers[]` 一项 → `claims[].claim_id`（Q1-S1-C1）→
`evidence[].paragraph_id`（P1）+ `char_start`（0）→ `paragraph_index.json` 中 P1 原文按偏移取到的 `quote`。
`evidence_map.csv` 为同一关系的表格视图（一行一条证据），可直接筛选 `quote_verified=false` 复核。

## 4. 未报告与部分回答的示例（同一映射）

- 若问题问「是否报告疲劳寿命」，而材料只有 “did not evaluate fatigue performance”：
  `status=answered`，`claims[].claim_id=Q?-ABS1`，`kind=inferred`、`readability=undetermined`，
  `uncertainties[]` 记 `type=not_reported` 与零命中检索词。
- 若问「降解率是多少」而材料只给“显著提高”而无数字：`status=partial`，
  `unanswered_parts[]` 记 `reason=numeric_value_not_reported`。
- 若 `/input` 下没有可读案例：`status=input_error`、`errors[]` 记 `stage=load_case`、`answers=[]`，退出码仍为 0。

## 5. 复用建议（换论文/换领域）

1. 只换 `/input`，脚本不需要改；新领域词先补 `references/glossary.md`（`中文|英文` 一行一个）。
2. 段落编号缺失时脚本会按 `P1..Pn` 生成并在 `locator` 记来源数组，可在结果里核对映射是否合理。
3. 若某案例的答案文本需要更自然的中文，可写 `answers_patch.json`（见 SKILL.md 第 6 节）后再跑 `--apply`，
   脚本会拒收含引文外数字的段落，避免改写引入未经原文支持的数值。
