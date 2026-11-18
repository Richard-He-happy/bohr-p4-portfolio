# draft.json 结构与校验口径

`init` 会在 `/app/work/draft.json` 生成模板；Agent 填写后由 `check` 校验、`build` 排版。
工作稿只描述"写什么"，排版由脚本负责。

## 1. 结构

```json
{
  "audience": {
    "label": "产业界（企业合作/投资评估）",
    "profile": "有工程背景、无本领域实验经验的技术与投资人员",
    "reading_goal": "判断能否落地、需要什么条件、风险在哪",
    "knowledge": "懂基本统计，不熟悉本文缩写与实验平台",
    "depth": "机制给一层因果，不展开参数推导",
    "term_policy": "缩写首次展开；保留 3 个核心术语并给一句解释",
    "strength_policy": "初步结果写'初步'；应用前景单列为待验证"
  },
  "genre": {"label": "技术转化简报", "conventions": ["结论先行", "小标题问句化"], "length_target": 1200, "length_unit": "字"},
  "headline": "一句话结论（含对象与效果）",
  "deck": "可选副标题/导语，一句",
  "sections": [
    {"id": "S1", "title": "问题与现状", "text": "成稿正文段落……", "cites": ["M1:P2"], "strength": "established"}
  ],
  "preserved": [
    {"id": "F1", "kind": "number", "value": "87.5%", "locator": "M1:P4",
     "quote": "删除率由 62.1% 提升至 87.5%（n=48）", "treatment": "kept", "note": "保留 n 与条件"}
  ],
  "map": [
    {"section_id": "S2", "source_locator": "M1:P4", "source_quote": "删除率由 62.1% 提升至 87.5%",
     "relation": "condensed", "note": "合并两句，未改数值"}
  ],
  "changes": [
    {"action": "trim", "locator": "M1:P6", "original_quote": "……", "revised_quote": "……",
     "reason": "方法参数与目标读者无关，压缩为一句"}
  ],
  "removed": [{"item": "Sanger 测序流程细节", "locator": "M1:P6", "action": "delete", "why": "方法复现信息，非证据"}],
  "glossary": [{"term": "LNP", "expansion": "脂质纳米颗粒（lipid nanoparticle）", "usage": "LNP", "locator": "M1:P3"}],
  "pending": [{"issue": "年产能数字仅有厂商宣传口径", "why": "非同行评议来源", "action": "作者确认后可发布"}],
  "uncertainty": ["体外数据向体内外推尚未验证"]
}
```

## 2. 字段规则

| 字段 | 必填 | 规则 |
|---|---|---|
| `audience.label` | 是 | 一句话受众标签；同时填 `profile`/`reading_goal`/`knowledge`/`depth`/`term_policy`/`strength_policy` |
| `genre.label` | 是 | 体裁；`length_target` 为字数上限（整数） |
| `sections` | 是 | ≥3 段；每段 `title`+`text`；`text` 是**成稿正文**，不是要点罗列 |
| `sections[].cites` | 建议 | `M1:P3` 或列表；用于逐段回溯 |
| `sections[].strength` | 建议 | `established` / `preliminary` / `hypothesis` |
| `preserved` | 是 | ≥5 条；`value`+`locator`+逐字 `quote`+`treatment`(kept/reworded/moved/condensed) |
| `map` | 是 | 每个 section 至少 1 条；`section_id` 必须存在 |
| `changes` | 是 | 每处删改：`action`+`reason`（`original_quote` 建议逐字） |
| `removed` | 建议 | 删除/压缩项与理由（为何不是证据） |
| `glossary` | 建议 | 缩写与统一说法，面向公众稿必填 |
| `pending`/`uncertainty` | 建议 | 待人工确认与不确定，会成为 result.json 同名字段 |

## 3. check 的判定

| 代码 | 级别 | 含义 |
|---|---|---|
| `missing_field` / `empty_field` | 错误 | 结构缺失，无法成稿 |
| `section_empty` / `too_short` | 错误 | 正文空或不足目标 45%（提纲判定） |
| `*_quote_miss` | 错误 | quote 在源材料找不到（禁止改原文凑通过） |
| `locator_not_found` | 错误 | 定位不存在于材料索引 |
| `number_not_in_source` | 错误 | 成稿数字源文没有（换算需进 pending） |
| `map_locator_missing` | 错误 | 对照表缺定位 |
| `change_action_missing`/`change_reason_missing` | 错误 | 删改缺动作或理由 |
| `short` / `long` | 提示 | 篇幅偏离 70%–150% |
| `preserved_not_in_body` | 提示 | 必保留项未出现在正文 |
| `terms_lost` | 提示 | 源文缩写多未出现（公众稿需术语表） |
| `low_paragraph_coverage` | 提示 | 进入对照的段落 <15% |
| `unit_variant` | 提示 | 数值对得上但单位写法不同 |

校验统计写入 `result.json.self_check`：`quote_hit/quote_total`、`numbers_in_body`、`number_errors`、`paragraph_coverage`、`acronyms_in_source/in_body`。

## 4. 写作口径提醒

- `text` 里不要写"本文将讨论……"式的元话语，直接给内容。
- 一段一义；每段首句承载结论，便于审稿人快速核对。
- 数字、单位、样本量、比较基准按原文写法照搬（`12.5%` 不要写成 `约一成`）。
- 源文没有的商业前景、成本、时间表，一律进 `pending`，不得写入正文当结论。
