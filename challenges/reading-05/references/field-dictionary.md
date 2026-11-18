# 字段字典与可比性判据（v2.0）

本文件是 `draft.json` 的填写依据：同一套 `field_id` 覆盖所有论文，每格按"值 + 单位 + 数据集 + 指标口径 + 逐字引文 + locator"记录。

## 1. 核心字段组（workorder 未给字段时用这 8 维兜底）

| field_id | 含义 | 取值规则（写进 `value_rule`） | 常见单位 |
|---|---|---|---|
| task | 研究问题/任务 | 用材料原句概括研究目标，不改写结论 | — |
| dataset | 数据来源与版本 | 数据集编号/队列/语料名 + 版本；同一数据集不同版本视为不同值 | — |
| sample | 样本量与构成 | 取**最终分析** n（非筛选前）；人群/物种/细胞系单列 | participants / samples |
| material | 研究对象/基质 | 药物、染料、污染物、组织、菌株等实体名，保持原文命名 | — |
| method | 方法与设置 | 方法名 + 关键设置（剂量、时长、温度、仪器型号） | 见设置 |
| metric | 评价指标与口径 | 指标名 + 方向（越高越好/越低越好）+ 计算口径（如 AUC vs accuracy） | 见指标 |
| unit | 数值单位 | 与 `value` 严格配套；换算过的值必须注明 "converted" | mg/L、µM、% |
| budget | 成本/资源约束 | 计算预算、样本成本、时间窗；只在 workorder 要求时填 | USD、GPU-h |

## 2. 字段填写通则

1. **一字段一含义**：不得在同一 `field_id` 下混放两种口径（如把"剂量"和"暴露时长"放一起）。
2. **值随单位走**：`value` 只放数值或原文短语，单位进 `unit`；范围写 "10–20"，不自算均值。
3. **不换算**：除非 workorder 要求，换算后 `note: "converted from X"`。
4. **缺即缺**：`status:"unreported"` + `value:null` + `note`（如 "not reported in text"）；不得填 0、不得由图表估算值冒充正文值。
5. **不适用**：`status:"not_applicable"`（如综述无原始样本量）；同义指标统一到同一 `field_id` 并在 `definition` 写清范围。
6. **同义术语**：跨论文的同义指标统一到同一 `field_id`，在 `definition` 里写清同义范围（如 "accuracy (incl. balanced accuracy)"）。

## 3. 常见"看似可比、实则不可比"

| 陷阱 | 判定 | basis 示例 |
|---|---|---|
| 同数据集不同版本 | 不可比 | "GSE123 v1 vs v2，探针注释不同" |
| 指标名相同、口径不同 | 不可比 | "AUC(全样本) vs AUC(仅测试集)" |
| 单位不同且未换算 | 不可比（或换算后再比） | "mg/kg vs µM，缺分子量无法换算" |
| 剂量/时程不同 | 不可比（仅分层叙事） | "8 周高剂量 vs 2 周低剂量" |
| 人群/物种不同 | 不可比 | "小鼠 vs 人队列" |

## 4. 可比性判定的执行顺序

1. `task` → 2. `dataset` → 3. `sample`/`material` → 4. `method`（设置）→ 5. `metric`/`unit` → 6. `budget`（若要求）。

任一维不同：`comparable:false` + `basis`（哪维、原文依据、影响方向）；数值**保留**不合并，必要时给"分层子集可比"结论（如"仅 D2/D3 在高剂量层可比"）。

## 5. 冲突归因模板

| attribution | 何时用 | 说明写法 |
|---|---|---|
| sample | 人群/物种/n 差异导致 | "D1 n=32 小鼠，D2 n=410 人队列；效应量不可直接对比" |
| method | 剂量/时长/仪器差异 | "D1 10 mg/kg 8 周，D2 1 mg/kg 2 周" |
| metric | 指标或口径差异 | "D1 报 AUC，D2 报 accuracy；同一模型两种口径" |
| condition | 环境/基质/共变量差异 | "pH 5 vs pH 7；降解率方向相反" |
| unresolved | 材料不足以归因 | 同时写 `pending_human`，不硬下结论 |

## 6. 证据与 locator

引文逐字复制 `main.py show` 输出（1–2 句即可独立支撑该格）；locator 形如 `p3#para7`，内置 PDF 解析器下为 `s2#para5`；p 值/效应量/样本量必须与引文数字一致。
