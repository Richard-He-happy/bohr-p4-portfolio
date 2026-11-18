# 输入负载与输出字段规范（schema）

## 1. 三个阶段的数据流

```
/input/case.json + 材料
        │  main.py（阶段 1）
        ├─→ /app/work/workpack.json      逐段工作单（id / text / section / locks / glossary / workorder）
        ├─→ /app/work/polish_payload.json 骨架（agent 填写）
        │  agent 写 revised + edits
        │  main.py（阶段 3）→ verify.py: assemble_payload → fill_contract → verify_all → write_outputs
        └─→ /app/output/{manuscript.md, deliverable.md, change_log.csv, result.json}
```

`main.py` 在启动时就写入 partial `result.json`，结束时覆盖为终版；任何阶段失败都保留合法 JSON 且退出码 0。

## 2. `work/polish_payload.json`（agent 填写）

```json
{
  "case_id": "CASE-1",
  "paragraphs": [
    {
      "id": "P002",
      "revised": "整段改后文本（必须整段，不要只给片段）",
      "edits": [
        {
          "type": "collocation",
          "original_quote": "These results suggest that",
          "revised_quote": "These findings suggest that",
          "reason": "上句刚用过 results，替换避免重复；suggest 保留，结论强度不变",
          "locator": "P002"
        }
      ],
      "unchanged_reason": "该段无硬错，术语与单位已合规"
    }
  ],
  "glossary": [{"source": "reactive oxygen species", "target": "ROS"}],
  "bilingual": [{"source": "中文原句", "target": "English sentence"}],
  "workorder_receipts": [
    {"id": "WO01", "status": "done", "evidence": "ROS 首次出现处给出全称定义", "locator": "P002"}
  ],
  "pending_human": [{"item": "引用 [17]", "why": "正文有编号但材料无文献表，未猜文献"}],
  "uncertainty": ["p = 0.003 的报告精度按原文保留"],
  "notes": ""
}
```

字段约束：

| 字段 | 必需 | 约束 |
|---|---|---|
| `paragraphs[].id` | 是 | 必须是 `workpack.json` 中的段落 id（`P001`…） |
| `paragraphs[].revised` | 是 | 整段文本；留空即视为未润色，会写入 `pending_human` |
| `paragraphs[].edits[]` | 改动段必需 | 每条含 `type/original_quote/revised_quote/reason`；缺说明会被标 `unclassified` 并阻断 `ok` |
| `edits[].original_quote` | 是 | 必须**逐字**出现在原段落（空白按单空格归一后比较） |
| `edits[].revised_quote` | 是 | 必须出现在该段 `revised` 中；纯删除可留空字符串 |
| `edits[].reason` | 是 | ≥3 字符；写清「改什么 + 为何不改变语义」 |
| `edits[].locator` | 否 | 缺省填 `<源文件>#<段落id>` |
| `glossary[]` | 否 | `{source,target}`，会覆盖同源术语的既有条目 |
| `bilingual[]` | 双语案例必需 | `{source,target}` 逐段对齐 |
| `workorder_receipts[]` | 有工单时必需 | `status` 取 `done` / `covered` / `not_applicable`；`evidence` 写实际动作 |
| `pending_human[]` | 否 | `{item, why}`：缺材料、冲突、需人工定夺 |
| `uncertainty[]` | 否 | 字符串或 `{note}`：已做判断但把握不足 |

`type` 受控词表（与 `verify.py::CT` 一致）：
`grammar, agreement, tense, voice, article, preposition, punctuation, sentence_split, word_order, collocation, redundancy, nominalization, chinglish, terminology, abbreviation, register, hedging, citation_format, unit_format, typography, structure, translation, no_change, unclassified`。

## 3. `work/workpack.json`（阶段 1 产物）

```json
{
  "case_id": "CASE-1", "genre": "journal_abstract", "target_language": null,
  "instruction": ["…case 中的任务说明原文…"],
  "workorder": [{"id": "WO01", "text": "统一缩写首次出现形式", "scope": ""}],
  "glossary": [{"source": "reactive oxygen species", "target": "ROS"}],
  "conflicts": [],
  "paragraphs": [{"id": "P002", "kind": "body", "section": "Abstract",
                  "source": "abstract.md", "text": "…",
                  "locks": {"numbers": ["48", "25mg/kg"], "citations": ["[12]"],
                            "xrefs": [], "hedges": ["may", "suggest"],
                            "boosters": [], "abbreviations": ["ROS"]}}],
  "material_index": [{"name": "abstract.md", "kind": "md", "chars": 812, "method": "text"}],
  "hedge_lexicon": ["…"], "booster_lexicon": ["…"]
}
```

`locks` 是逐字核对清单：改文必须让这些 token 全部再次出现（数字比对已归一空格与大小写）。

## 4. `result.json` 字段

| 字段 | 说明 |
|---|---|
| `case_id` | 原样取自输入 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | `{main_path, bundle_path, files[], word_count}` |
| `manuscript_text` / `manuscript_path` | 润色后全文及文件路径 |
| `change_log[]` | `{paragraph_id, type, original_quote, revised_quote, reason, locator, verified}` |
| `preserved_facts[]` | `{kind: number/citation/xref/abbreviation, value, locator, present_in_revision}` |
| `evidence_map[]` | `{claim_id, claim, locator, source_id, quote}`：每条保留事实 → 原文逐字片段 |
| `glossary[]` | 术语表（案例给定 + 本次确认） |
| `bilingual[]` | 中英对照（无则空） |
| `workorder_receipts[]` | `{id, requirement, status, evidence, locator}` |
| `checks[]` | `{id, status: pass/warn/fail/skip, detail, counts}` |
| `coverage` | `{paragraphs, revised, ratio, changed, edits}` |
| `counts` | 各类计数（编辑数、通过数、缺失数、契约字段数） |
| `sources[]` | 材料清单与抽取方式（`pdftotext`/`pypdf`/`builtin-flate`/`zipxml`/`text`） |
| `uncertainty[]` / `pending_human[]` | 不确定项与人工确认项 |
| `errors[]` / `degradations[]` | 致命错误与降级（`what`, `detail`, 可含 `file`） |
| `changes[]` | 本次写出的文件清单 |
| `output_contract` | **原样回填**输入 `output_contract` 的全部键，值为按语义映射的结果 |

`output_contract` 映射规则（键名语义 → 取值）：

| 键名包含 | 取值 |
|---|---|
| change / changelog / diff / 修改 | `change_log` |
| gloss / termin / 术语 | `glossary` |
| preserv / fact / number | `preserved_facts` |
| evidence / trace | `evidence_map` |
| bilingual / 双语 | `bilingual` |
| workorder / receipt / 回执 | `workorder_receipts` |
| status / state | `status` |
| uncertain / confidence / note | `uncertainty` |
| pending / human / confirm | `pending_human` |
| check / coverage / metric | `checks` / `coverage` |
| path / file / artifact | `manuscript_path` |
| text / manuscript / polish / revis / translat / abstract / 正文 / 稿件 | 润色后全文 |
| error | `errors` |
| 其他未知键 | `null`（对象→`{}`，数组→`[]`），键名保留 |

取值的容器类型跟随输入示例：示例为数组则输出数组，示例为字符串则输出字符串，示例为对象则输出对象。

## 5. `checks` 项目（verify.py）

| id | 检查 | 判 fail 的条件 |
|---|---|---|
| `contract_fields` | 契约字段全部回填 | 任一键缺失 |
| `fact_locks` | 数字/单位/引用/图表指向守恒 | 源有而改文缺失（新增数字记 warn 并进 `pending_human`） |
| `hedge_strength` | 逐段 hedge/booster 计数 | 段落原有 hedge 全部消失 |
| `terminology` | 术语表目标写法落地 | 源术语出现但目标写法在改文中不存在 |
| `edit_traceability` | 引文可回溯、类型合法、理由非空 | 任一不满足 |
| `coverage` | 段落覆盖 | 有 payload 但 0 段改文 |
| `language_residual` | 目标语言残留（仅 target=en） | CJK 占比 > 0.05 |
| `workorder_receipts` | 工单回执 | 有工单但存在未回报项 |
| `revision_hash` | 漂移基线（sha256 前 16 位） | 永不 fail，用于重复运行比对 |

## 6. 示例（示例，非正式案例结果）

输入 `abstract.md` 两句：`We treated 48 mice with 25 mg/kg of the inhibitor for 14 days … These results suggest that …`，

示意 `change_log.csv` 片段：

```
paragraph_id,type,original_quote,revised_quote,reason,locator,verified
P002,collocation,These results suggest that,These findings suggest that,上句刚用过 results；suggest 保留，强度不变,P002,True
```

示意 `result.json` 关键字段：`{"status":"ok","case_id":"DEMO","counts":{"paragraphs":4,"edits":1,"edits_verified":1,"missing_numbers":0},"checks":[{"id":"fact_locks","status":"pass"}]}`。

以上为接口示意，不构成任何正式案例的答案或结果。
