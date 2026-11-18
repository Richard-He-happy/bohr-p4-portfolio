# 最小调用示例（**示例，非正式案例结果**）

> 以下输入与输出均为**构造的示例**，用于说明接口与完整流程，不代表任何正式测试案例，也不能当作案例答案。示例材料是为验证接口而编造的合成文本（如“某指标”），不对应任何真实论文。

## 1. 最小输入

`/input/case.json`

```json
{
  "case_id": "EXAMPLE-01",
  "output_contract": {
    "findings": "逐条问题",
    "checks": "六面状态",
    "summary": "计数",
    "case_id": "输入标识",
    "report": "报告路径"
  },
  "manuscript_file": "manuscript.md"
}
```

`/input/manuscript.md`（合成片段，仅示意）

```markdown
## Abstract

我们纳入 48 名患者，结果显示该指标显著升高（p = 0.03）。

## Results

干预组指标升高 12.5%（图 3）。该结果与既往报道一致 [7]。

本研究首次证明该指标可作为独立预测因子。

## References

1. Smith J. A study of markers. J Test. 2019;12:1-9.
```

## 2. 调用

```bash
# 第一步：生成可定位语料 + 候选证据包（同时先落盘 partial result.json）
python3 scripts/main.py --input /input --output /app/output --stage scaffold

# 第二步：阅读 /app/work/review/packets.md，写 /app/work/review/issues_plan.json（schema 见 references/schema.md）

# 第三步：校验并产出终态
python3 scripts/main.py --input /input --output /app/output --stage finalize
```

`--stage auto`（默认）等价于“有计划就跑完两步，没计划就只出候选并给 partial”。

## 3. 示意输出（节选，示例）

`/app/output/result.json`

```json
{
  "case_id": "EXAMPLE-01",
  "status": "partial",
  "summary": {"issue_total": 2, "facet_coverage": "5/6",
              "by_severity": {"blocker": 0, "major": 2, "minor": 0, "suggestion": 0},
              "needs_human": 1, "rejected": 1, "unaddressed": 12},
  "issues": [
    {"id": "R-01", "facet": "statistical_reporting", "item": "STA-01", "severity": "major",
     "verdict_type": "insufficient_evidence", "title": "报告 p 值但未说明检验方法",
     "source_id": "MS", "locator": "MS:P3", "quote": "该指标显著升高（p = 0.03）",
     "quote_verification": "verbatim", "evidence": [], "reason": "未给出检验方法、自由度与样本定义。",
     "suggestion": "补充检验名称、各组 n 与效应量。", "confidence": "medium", "status": "needs_human",
     "related_candidates": []},
    {"id": "R-02", "facet": "argument_chain", "item": "ARG-01", "severity": "major",
     "verdict_type": "error", "title": "结论句使用“首次证明”级强断言",
     "source_id": "MS", "locator": "MS:P3", "quote": "本研究首次证明该指标可作为独立预测因子。",
     "quote_verification": "verbatim", "evidence": [], "reason": "同句无统计量、无引用，单中心小样本不足以“证明”。",
     "suggestion": "改为“提示……可能”，并补充效应量与置信区间。", "confidence": "high",
     "status": "confirmed", "related_candidates": ["C001"]}
  ],
  "checks": {"fact_verification": {"status": "pass", "findings": 0, "unresolved": []},
             "method_design": {"status": "not_checked", "findings": 0, "unresolved": ["C009"]}},
  "review_records": {"rejected_issues": [{"quote": "该指标显著提高（p=0.03）", "reason": "quote 未逐字命中"}]},
  "contract_fields": {"requested": ["findings", "checks", "summary", "case_id", "report"],
                      "filled": ["findings", "checks", "summary", "case_id", "report"], "unfilled": []}
}
```

`/app/output/issues.csv`（表头 + 1 行示例）

```
id,facet,facet_zh,item,severity,verdict_type,source_id,locator,quote,reason,suggestion,confidence,status,related_candidates
R-01,statistical_reporting,统计报告,STA-01,major,insufficient_evidence,MS,MS:P3,该指标显著升高（p = 0.03）,未给出检验方法,…,-,medium,needs_human,
```

`/app/output/review_report.md`（节选）

```markdown
# 学术规范与合规审查报告

- case `EXAMPLE-01`｜partial｜问题 2（major 2）｜覆盖 5/6｜待复核 1｜拒收 1｜未裁定 12

## 1. 六面覆盖

- 【fact_verification】事实核验 pass｜0 条｜-
- 【method_design】方法设计 not_checked｜0 条｜无裁定计划

## 2. 问题清单（quote 已逐字校验；未命中者见第 3 节）

### R-02 [major｜论证链] 结论句使用“首次证明”级强断言
- 位置 `MS` MS:P3｜`ARG-01`｜error｜置信 high
- 原文：「本研究首次证明该指标可作为独立预测因子。」
- 依据 仅稿件内部一致性
- 理由 同句无统计量、无引用…
- 建议 改为“提示……可能”…

## 3. 待复核 / 拒收

- 被拒收：该指标显著提高（p=0.03） — quote 未逐字命中
```

## 4. 这个示例说明了什么

| 观察点 | 说明 |
|---|---|
| 拒收机制 | 计划里那条**改写过的**引文没有进入 `issues`，而是进了 `review_records.rejected_issues` 与待复核 |
| 定位回填 | 作者只给 `facet/quote`，脚本自动回填 `source_id` 与 `locator`（`MS:P3`） |
| 覆盖守卫 | `method_design` 未裁定 → `facet_coverage` 不足 6/6，顶层状态降为 `partial`，不冒充 `ok` |
| 契约回填 | `output_contract` 的 5 个字段全部出现在顶层，`unfilled` 为空 |
| 未裁定候选 | `unaddressed=12` 提示仍有候选待裁定（对应 `checks.*.unresolved`） |
