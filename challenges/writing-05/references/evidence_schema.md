# 论断 / 证据 / 定位 schema（writing-03 v1.0.0）

一切条目以"可被他人独立回查"为准：能给定位就给定位，能给逐字原文就给逐字原文，缺什么就标什么。

## 1. 论断清单 `claims.json`

```json
{
  "case_id": "C01",
  "language": "zh",
  "count": 5,
  "claims": [
    {"claim_id": "C001",
     "text": "原文句（含原句末引用标记）",
     "core": "剥离句末引用标记后的论断文本",
     "type": "事实|推断|因果|比较",
     "location": "draft:artifacts/section.md [B2.S1] chars:0-38"}
  ]
}
```

切分规则：

| 规则 | 说明 |
|---|---|
| 粒度 | 一句 = 一个可判定命题；**禁止**把整段当一条 claim |
| 拆分点 | 句号/问号/感叹号/分号；英文句点需后接大写或数字才切（避免切开小数与缩写） |
| 排除 | 标题行、表格分隔线、纯编号行、参考文献条目本身 |
| `type` | 出现比较词→比较；出现因果词→因果；出现情态/推测词→推断；其余→事实 |
| `location` | 原稿模式指向"原稿文件 + 句 locator"；取材模式直接给材料 locator |

## 2. 证据表 `evidence_table.json`

```json
{
  "case_id": "C01",
  "count": 7,
  "schema": "claim_id,source_id,locator,quote,strength,support_scope,conflicts,rationale,verified",
  "rows": [
    {"claim_id": "C001",
     "claim": "论断文本",
     "source_id": "D03",
     "source_path": "artifacts/source_A.md",
     "locator": "artifacts/source_A.md [B2.S1] chars:120-268",
     "quote": "逐字原文，含标点与单位",
     "source_type": "队列",
     "strength": "中",
     "strength_basis": {"design": "队列", "design_pts": 2.0, "sample_size": 412,
                        "size_pts": 1.5, "sources": 2, "conflict": false, "score": 4.5},
     "rationale": "设计=队列(2.0)；样本=100-999(1.5)；独立来源=2(1.0)；冲突=0",
     "support_scope": "直接支撑；n~412",
     "conflicts": [{"source_id": "D04", "locator": "...", "quote": "...",
                    "similarity": 0.52, "why": "主题重叠但结论方向相反"}],
     "verified": true,
     "abstract_only": true}
  ]
}
```

字段纪律：

- `quote`：**逐字**。不翻译、不拼接、不改标点。命中校验失败 → `verified:false` + `pending_human`，不得改原文迁就。
- `locator`：`<相对路径> [B<块>.S<句>] chars:<start>-<end>`，字符偏移基于解析后的纯文本。
- `strength`：`高|中|低|不足`；口径见 `method_and_runbook.md`。
- `support_scope`：`直接支撑` / `部分支撑（范围不一致）` / `无直接支撑`，并附样本量或条件边界。
- `conflicts`：方向相反的来源（否定/不一致线索 + 主题重叠），最多保留 3 条；无冲突时为空数组，不留 `null`。
- 未匹配到来源的行：`source_id/quote/locator = null`，`strength = 不足`，`support_scope = 无直接支撑`。

## 3. 成稿 `evidence_driven_draft.md`

结构（原稿模式保留原块/标题；取材模式按段落聚合）：

```
# 标题
> 案例元数据（原样转录，未联网核验）
（正文：每句 = 强度限定语 + 内容 + [n]）
## 证据边界
## 参考文献           ← 编号 = 首次引用顺序
## 材料内文献表（原样转录）
```

约束：正文引用编号 `[n]` 必须能解析到参考文献条目；参考文献条目只能来自材料，缺 DOI 就缺，不补。

## 4. `result.json` 关键字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | str | 输入原样回填 |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | str | 成稿全文（另给 `deliverable_path`） |
| `preserved_facts` | list | `{fact_id, value, quote, locator, source_id, in_draft}`：数字/单位/DOI 逐条保留 |
| `evidence_map` | list | `{claim_id, claim, claim_type, claim_location, strength, evidence[], unsupported}` |
| `change_log` | list | `{change_id, claim_id, action, original_quote, revised_quote, reason, locator, human_confirm}` |
| `sources` | list | 每个输入文件：路径、字节数、sha256、类型、解析方式 |
| `metrics` | obj | 可复算计数：论断数/支撑率/引文命中/强度分布/冲突数/降级数 |
| `pending_human` | list | `{id, issue, detail, needed, source_id}`：真正需要人做的事 |
| `errors` / `degradations` / `changes` | list | 异常、降级、变更 |
| `runtime` | obj | 脚本版本、Python、耗时、参数、是否联网 |

契约字段（`output_contract` 的键）一律原样保留键名：已知键填实值，未知键保留输入原值，缺值给 `null`/`[]`。

## 5. 三件产物的 join 约定

```
claims.claim_id  ──┬──> evidence_table.claim_id
                   ├──> evidence_map.claim_id
                   └──> 成稿中的 [n]（经 evidence_table.source_id → 参考文献编号）
```

`verify.py` 会检查：悬空 `claim_id`、引用编号越界、缺 `locator/strength/support_scope/quote`、引文未逐字命中、契约字段缺失。

## 6. v2 新增 result.json 字段（资产层）

| 字段 | 说明 |
|---|---|
| `golden_standard` | `{path,count,note}`；文件含 `items[]`（16 项，逐项 `basis{locator,quote,verified}`）与 `claim_units[]`（逐条论断的期望来源/定位/逐字引文/期望强度） |
| `diff_report` | `{path,count,note}`；`count` = 未达标项数 |
| `version_history` | `{path,count,note}`；版本链与回退命令 |
| `self_check` | `{path,count,note}`；契约/覆盖率/数字引用一致性/兜底闸门/独立复核 |

约定：四值恒为对象（失败置 `null` 并记 `errors.stage=assets`），不改动原有契约字段语义；`items[].weight` 总和须为 100；`claim_units` 的 `expected.locator` 与 `actual.locator` 不同即需人工裁决，不得默认信任任一侧。
