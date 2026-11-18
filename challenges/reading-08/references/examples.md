# 最小调用示例与复跑步骤

> 本文件所有输入/输出均为**示例，非正式案例结果**。正式 3 个案例由平台提供，脚本不在包内预置任何答案。

## 1. 输入骨架

```text
/input/
├─ case.json
├─ task.md                     # 平台给的任务说明（脚本不解析，仅透传存在性）
└─ artifacts/
   ├─ publisher-source.xml     # 原始出版商 XML（可含全文）
   └─ source-formulas.xml      # 公式节点子集（MathML）
```

`case.json`（示例）：

```json
{
  "case_id": "demo-001",
  "paper_id": "demo-paper",
  "material_version": "v1",
  "output_contract": {
    "formulas": [],
    "variables": [],
    "derivations": [],
    "numeric_checks": [],
    "notes": null
  },
  "task_instruction": "Restore the equations, explain every symbol, verify one substitution."
}
```

`artifacts/source-formulas.xml`（示例，含 `mfrac` + `msubsup` + 正文定义句）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<article xmlns:mml="http://www.w3.org/1998/Math/MathML">
 <body><sec>
  <p>We model growth where <italic>k</italic> is the specific growth rate in 1/h,
     and <italic>t</italic> is time in h.</p>
  <p>Parameters were <italic>k</italic> = 0.35 1/h and <italic>t</italic> = 6 h.</p>
  <disp-formula id="fd-1"><label>(1)</label>
   <mml:math id="m1">
    <mml:msubsup><mml:mi>N</mml:mi><mml:mn>0</mml:mn><mml:mn>2</mml:mn></mml:msubsup>
    <mml:mo>=</mml:mo>
    <mml:msup><mml:mi>e</mml:mi><mml:mrow><mml:mi>k</mml:mi><mml:mi>t</mml:mi></mml:mrow></mml:msup>
   </mml:math>
  </disp-formula>
 </sec></body>
</article>
```

## 2. 调用

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

退出码恒 0；`/app/output/result.json` 在解析前就已存在（partial），结束时被最终版本覆盖。

## 3. 示意输出（节选，**示例**）

```json
{
  "case_id": "demo-001",
  "status": "partial",
  "result": {
    "formulas": [{
      "formula_id": "F1", "source_id": "fd-1", "eq_number": "(1)",
      "mathml_raw_path": "/article[1]/body[1]/sec[1]/disp-formula[1]/math[1]",
      "latex": "N_{0}^{2}=e^{kt}",
      "latex_source": "structural_mapping", "parse_confidence": "high",
      "structure": {"fracs": 0, "subsups": 2, "radicals": 0, "matrices": 0, "cases": 0},
      "symbols": ["N_{0}^{2}", "k", "t"], "flags": [], "status": "ok"
    }],
    "variables": [
      {"symbol": "k", "plain": "k", "definition": "the specific growth rate in 1/h",
       "unit": "1/h", "definition_source": "paper_defined",
       "locator": "/article[1]/body[1]/sec[1]/p[1]", "quote": "We model growth where k is …",
       "value": {"value": 0.35, "unit": "1/h", "locator": "/article[1]/body[1]/sec[1]/p[2]"}},
      {"symbol": "t", "plain": "t", "definition": "time in h", "unit": "h",
       "definition_source": "paper_defined", "locator": "/article[1]/body[1]/sec[1]/p[1]"}
    ],
    "numeric_checks": [{
      "formula_id": "F1", "substituted": {"k": 0.35, "t": 6.0}, "computed": null,
      "status": "not_computable", "missing_symbols": ["N0"],
      "unit_check": "not_evaluated", "order_of_magnitude_check": "not_evaluated"
    }],
    "coverage": {"formulas_total": 1, "formulas_ok": 1, "variables_total": 3,
                 "by_source": {"paper_defined": 2, "common_knowledge": 1},
                 "symbol_coverage": 0.667, "numeric_computed": 0}
  },
  "claims": [
    {"claim_id": "C-F1", "kind": "reported", "readability": "directly_read",
     "statement": "Formula F1 from /article[1]/…/disp-formula[1]/math[1]",
     "locator": "/article[1]/body[1]/sec[1]/disp-formula[1]/math[1]", "quote_verified": true},
    {"claim_id": "S-k", "kind": "reported", "readability": "directly_read",
     "statement": "k: the specific growth rate in 1/h", "quote_verified": true}
  ],
  "uncertainties": [
    {"id": "U-gloss-N0", "type": "definition_absent", "object": "N_{0}^{2}",
     "description": "not defined in material", "impact": "common_knowledge/inferred"}
  ],
  "contract_fields_missing": [],
  "runtime": {"skill": "reading-08-formula-structure", "version": "1.0.0", "elapsed_s": 0.01}
}
```

## 4. 何时会得到 `insufficient_evidence`（示例）

材料只有文字指标、没有公式表示时（题面 C02 型真实缺失分支）：

```text
/input/artifacts/notes.txt:
  The catalyst was tested at 523 K and 1 bar with a space velocity of 12 000 h-1.
  Conversion reached 87 % after 40 h on stream.
```

输出要点（示例）：`status="insufficient_evidence"`，`formulas=[]`，`missing_objects=[{"object":"formula representation", …}]`，`pending_human=[{"item":"formula_source_missing", …}]`，同时 `result.indicator_checks[]` 逐条给出 `523 K`、`1 bar`、`12 000 h-1`、`87 %`、`40 h` 及其原文 quote 与 locator。**不反推公式、不填 0。**

## 5. 复跑与自查

```bash
python3 -B scripts/main.py --help                     # 退出码 0
python3 -B scripts/main.py --input /input --output /tmp/o1
python3 -B scripts/main.py --input /input --output /tmp/o2
diff /tmp/o1/formulas.tex /tmp/o2/formulas.tex        # 应为空：确定性
python3 -B scripts/main.py --input /tmp/empty --output /tmp/o3   # 仍产出合法 partial，退出码 0
```

对照 `references/result-schema.md` 检查：`contract_fields_missing` 为空、每条 claim 的 `quote_verified` 非 `false`（除非已在 `pending_human`）、`by_source.common_knowledge` 项与 `uncertainties` 数量对得上。
