# 论文质量审查报告

- case_id：`{{case_id}}`　status：**{{status}}**
- 稿件指纹：{{fingerprint}}
- 生成时间：{{generated}}　技能：{{skill}}

## 1. 结论摘要

{{summary}}

{{top_major}}

## 2. 逐条问题（按六类检查项分面）

{{issues}}

## 3. 待复核 / 未检查项

{{pending}}

{{unchecked}}

## 4. 检查项执行覆盖

| 分面 | 状态 | 已执行/总数 |
|---|---|---|
{{coverage}}

## 5. 依据、边界与自查记录

{{basis}}

## 6. 复核指引

按 `locator`（页码 / 段落 / 句号 / 字符区间）回到原文，用 `quote` 原串检索即可逐条核对；
`issues.csv` 为同内容的表格版，可直接交办给作者或编辑；`result.json` 为机器可读版，
契约字段（output_contract）已原样回填。若 `status` 为 `partial` 或 `insufficient_evidence`，
请先阅读第 3 节与第 5 节的缺口说明，再决定是否采信相关分面的结论。
