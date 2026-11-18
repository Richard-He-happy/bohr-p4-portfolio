# 题集草稿规范（`work/questions.draft.json`）

`check` 与 `build` 读取的唯一定义。字段名有别名（脚本用 `pick()` 兼容），但**推荐只写左列**。

## 1. 顶层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | str | 否 | 与 case.json 一致便于追溯；缺省取 case.json |
| `notes` | str | 否 | 出题思路、覆盖了哪些段落（写给复核人看） |
| `items` | array | 是 | 题目数组；空数组 → build 走兜底 |

## 2. 单题

| 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|
| `id` | str | 是 | 唯一，建议 `Q01`；重复会被改名为 `Q01b` 并记错 |
| `type` | enum | 是 | `extraction` `numeric` `method` `definition` `conflict` `coverage` `table` `other`；未知值归 `other` |
| `difficulty` | enum | 否 | `easy` `medium` `hard`，缺省 `medium`（只做展示，不参与算分） |
| `question` | str | 是 | ≥10 字符；必须能只靠材料回答 |
| `rubric` | array | 是 | ≥1 个评分点，见下 |
| `reference_answer` | str[] | 是 | ≥1 条，写"答到什么算对"，可含 locator |
| `evidence` | array | 是 | ≥1 条 `{material, locator, quote}` |

### rubric 点

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | str | 题内唯一，建议 `R1` |
| `text` | str | "答到什么算过"，一句话 |
| `weight` | float | 所有点之和 ≈1.0（±0.02，超差只警告） |
| `key_terms` | str[] | 1–5 个短串，取**原文用词**；省略则从 `reference_answer` 自动抽取 |

`key_terms` 是自动评分的关键：脚本统计这些串在证据 quote 里的覆盖率。写原文里的实词（数字、单位、术语），不要写"正确""完整"这类空话。

### evidence 条

| 字段 | 类型 | 规则 |
|---|---|---|
| `material` | str | 材料 ID，如 `M01`；省略时从 locator 前缀推断 |
| `locator` | str | `M01#p7`，省略时由 quote 命中位置自动填（并记 warning） |
| `quote` | str | **逐字**原文片段，≥12 字符，允许空白差异，不允许改写/拼接/翻译 |

## 3. 校验规则（`check` 会逐条报）

1. 结构：题必填项缺失 → `ERROR`，题不进题集。
2. 引文命中：空白归一后必须是材料文本的连续子串（大小写敏感优先，其次不敏感，再次忽略全部空白）；不命中 → `quote not found in M01 (...)`，要回 `show` 重新复制。
3. 定位一致：命中位置反推段号，与声明 locator 不同 → `locator_mismatch: M01#p3 vs M01#p7`。
4. 权重：Σweight 偏离 1.0 超过 0.02 → `WARN`。
5. 引文过短：<12 字符 → `ERROR`。
6. 无 `key_terms`：`WARN`，改用 `reference_answer` 抽取。
7. 一道题没有任何 verified quote → 拒收，进 `benchmark.json.rejected` 与 `pending_human`。

`check_report.json` 保存机器可读结果（issues / warnings / rejected / n_raw / draft_path）。

## 4. 示例（示例，非正式案例结果）

```json
{
  "case_id": "demo-001",
  "notes": "M01#p2 数值、M01#p5 结论与局限各一题",
  "items": [
    {
      "id": "Q01",
      "type": "numeric",
      "difficulty": "easy",
      "question": "盐度从 25 psu 升到 45 psu 时比生长速率从多少降到多少，降幅百分比是多少？请给出 locator。",
      "rubric": [
        {"id": "R1", "text": "给出 1.42 与 0.87 d-1 两个数值", "weight": 0.6, "key_terms": ["1.42", "0.87"]},
        {"id": "R2", "text": "给出 39 percent 的降幅", "weight": 0.4, "key_terms": ["39 percent"]}
      ],
      "reference_answer": ["从 1.42 d-1 降到 0.87 d-1，降幅 39 percent"],
      "evidence": [{
        "material": "M01",
        "locator": "M01#p2",
        "quote": "Salinity stress reduced the specific growth rate of Thalassiosira weissflogii from 1.42 d-1 at 25 psu to 0.87 d-1 at 45 psu, a decline of 39 percent relative to the control."
      }]
    }
  ]
}
```

## 5. 出题建议（提分点）

- 至少覆盖 3 种题型：数值、方法与条件、机制/主张、材料内冲突或未报告项。
- 每题 2 个 rubric 点比 1 个更能区分"答对一半"；权重给 0.5/0.5 或 0.6/0.4。
- `reference_answer` 写要点；证据 quote 才需要整句。跨段对比题给两条 evidence。
- 材料未给的结论，题面就问"材料是否报告了 X"，答案写"未报告"。
