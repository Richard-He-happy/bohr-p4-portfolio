# 深度研究流程协议（protocol.md）

本文件同时是**人读规则**与**脚本可读模板**。`scripts/main.py --stage plan` 读取 `<!-- SQ_TEMPLATES -->`
区块生成拆解树；改模板即改拆解策略，无需改代码。

<!-- SQ_TEMPLATES -->
SQ1|scope||研究对象与边界如何界定：核心对象（{obj}）、时间范围（{years}）、研究与设计限定（{ds}）。|明确写出对象定义/范围/时间或设计限定的原文句|
SQ2|evidence_scan|SQ1|现有材料对 {obj} 报告了哪些直接证据（研究设计、样本或数据规模、关键结果）？|至少一条含设计或规模的原文句 + 一条含结果方向或数值的原文句|
SQ3|mechanism|SQ1|{mc} 层面：材料给出的机制解释、方法路径或干预点是什么，附带哪些限定条件？|机制或方法陈述句，须能与结果句区分|
SQ4|quantitative|SQ2|关于 {oc}，材料报告了哪些可比较的量化结果（数值、单位、对照条件、误差）？|数值与单位、对照条件出现在同一材料单元|
SQ5|comparison|SQ2,SQ3|在 {obj} 之间，各结局指标的方向与量级差异是否一致，差异由何条件造成？|每个比较臂至少一条独立原文证据；差异须可归因到条件/人群/方法|
SQ6|conflict|SQ2,SQ3,SQ4|哪些结论相互冲突或不一致，冲突能否由人群、条件、方法或时间窗差异解释？|冲突双方各一条原文句；解释句只能标 inferred|
SQ7|gap|SQ1,SQ2,SQ3,SQ4,SQ6|材料覆盖与研究空白：哪些是检索缺口，哪些是材料本身的证据缺口？|空白须绑定未覆盖子问题或未出现字段，禁止无据套话|
<!-- /SQ_TEMPLATES -->

`when` 列（第 6 列，可空）填 `compare` 表示仅在问题含比较关系时启用。占位符：`{obj}` 研究对象、
`{oc}` 结局指标、`{mc}` 机制/方法、`{ds}` 设计类型、`{years}` 时间范围。

## 1. 拆解规则

1. 拆解必须**可分配检索动作**：每个子问题都要落到「能拿去检索的名词短语」，不能只把原句改写成关键词。
2. 依赖必须是 DAG，且依赖有语义理由：界定范围（SQ1）先于取证；比较（SQ5）依赖两臂证据；冲突（SQ6）
   依赖已成立的量化证据；空白（SQ7）依赖其余全部。无依赖关系的子问题必须并行，不得串行浪费预算。
3. 子问题类型固定为 `scope / evidence_scan / mechanism / quantitative / comparison / conflict / gap`，
   便于机器校验覆盖度。
4. 若材料使某个子问题不可回答，保留该子问题并在结果中记为 `no_evidence`，**不得删除**——删掉会把缺口洗成完备。

## 2. 检索计划规则

- 顺序：波次 1 顺序（scope），其后波次并行；同一波次内不得重复同一批段落（`evidence_candidates.json` 的去重键是 passage）。
- 范围：`provided_corpus_only`。离线执行本地词法检索，检索式仍完整记录，供有权访问数据库者复跑。
- 停止条件：新增支持性段落 <2 条 / 已遍历全部已解析材料 / 达候选上限。三者取先到者。
- 每轮检索必须留 `tool`、`args`、`status`、`elapsed_ms`、`result` 五项，写入 `tool_calls.jsonl`。

## 3. synthesis.json（综合阶段写入，供 finalize 校验）

```json
{
  "research_question": "…",
  "sub_questions": [{"id": "SQ3b", "type": "agent_added", "question": "…", "depends_on": ["SQ2"]}],
  "claims": [
    {"claim_id": "C1", "sq": "SQ2", "text": "一句话结论（不含材料外内容）",
     "strength": "directly_supported",
     "evidence": [{"candidate_id": "E03"}, {"source_id": "s2", "quote": "逐字原文", "locator": "p.4"}],
     "conditions": "适用人群/条件/剂量等", "limits": "该结论不能外推到什么"}
  ],
  "conflicts": [{"conflict_id": "X1", "topic": "…",
                 "side_a": {"label": "A 方", "position": "…", "source_id": "s2"},
                 "side_b": {"label": "B 方", "position": "…", "source_id": "s5"},
                 "resolution": "unresolved|contextual|evidence_favours_a|evidence_favours_b",
                 "basis": "判据（条件差异/方法差异/样本差异）", "note": "…"}],
  "gaps": [{"gap_id": "G1", "gap": "…", "basis": "retrieval_gap|material_gap|inference",
            "searched": "已用的检索式/范围", "what_would_close_it": "…"}],
  "screening": [{"source_id": "s1", "decision": "include|exclude", "reason": "…",
                 "fields": {"design": "…", "n": "…", "outcome": "…"}}],
  "limits": ["…"]
}
```

`evidence` 的两种写法都接受：引用 `candidate_id`（脚本已校验过是逐字原文），或直接给 `source_id`+`quote`
（finalize 会重新逐字校验）。**不允许**只给结论不给 quote。

## 4. 证据强度口径

| 强度 | 判据 | 允许的措辞 |
|---|---|---|
| `directly_supported` | 至少一条通过校验的逐字 quote 直接陈述该结论，且条件一致 | 「材料显示…」 |
| `inferred` | 由多条已校验证据合成，材料未直接陈述 | 「由此可推断…」 |
| `insufficient` | 无通过校验的证据，或证据只覆盖部分条件 | 「材料不足以判断…」 |

校验等级：`strict`（归一化空白后逐字命中）> `whitespace_insensitive`（去空白后命中，PDF 换行所致）> `none`（拒收）。

## 5. 冲突处理

1. 必须同时呈现双方，各带 locator；不得只写「尚存争议」。
2. `contextual` 须指出差异变量（人群、剂量、时间窗、方法、终点定义），并给出能支持该变量的证据。
3. 无法解释时写 `unresolved`，在结论里保留双方区间，不取中位数、不取一方。
4. 若一方证据明显更弱（如无对照、n 极小），可写 `evidence_favours_*`，但必须写明「更弱在哪」。

## 6. 研究空白的三分法

- `retrieval_gap`：材料里有，检索没命中 → 给检索式，注明可重跑。
- `material_gap`：材料本身没有该证据 → 写明缺哪一类材料（如缺对照实验、缺长期随访）。
- `inference`：由已读证据推断出的空白 → 强度最低，必须写推断链。

禁止写「有待进一步研究」这类无绑定空话；每条空白必须绑定子问题 id 或缺失字段名。

## 7. locator 规范

| 材料类型 | locator 形式 | 例 |
|---|---|---|
| PDF（pdftotext 可用） | `p.<页码>` | `p.7` |
| PDF（标准库退化） | `stream:<序号>`（并在 degradations 说明无页码表） | `stream:12` |
| DOCX / 纯文本 | `doc`（+`~c<块号>` 表示切块） | `doc~c2` |
| CSV/TSV | `row=<行号>`（表头参与字段名） | `row=14` |
| XLSX | `<sheet>!row=<行号>` | `sheet1!row=9` |
| JSON | `$[<记录序号>]` | `$[3]` |
| 图片 | 不解析，记 `unsupported` + 缺口 | — |

quote 必须是该 locator 所指文本的**逐字子串**；跨块引用要拆成多条证据，不要拼接。
