# 输出契约与数据结构（v1.0.0）

本文件是 `result.json` 与三个复核用文件的字段字典。所有字段都由脚本实际写入，未写入的字段以 `null`/`[]` 保留，不删键。

## 1. 目录布局

```
/input/                 # 平台给定：case.json、task.md、材料（PDF/DOCX/TXT/表格/图片……）
/app/work/              # 中间产物（可编辑、可重跑）
  segments.json         # 分段结果（seg_id/page/kind/section/text/sents/id）
  source_units.md       # 人读的分段原文（P### 段号）
  glossary.csv          # 术语表模板：term,translation,...（填 translation 即锁定）
  state.json            # 跨进程元数据（task/sources/doc/errors 等，供 finalize 还原）
  translations/*.json   # Agent 写入的译文 {"P001": "译文"}
/app/output/            # 交付物
  result.json           # 结构化主结果（含 output_contract 回填）
  translation_bilingual.md
  alignment.csv
  glossary.csv
  verification.json
```

## 2. `result.json` 顶层字段

| 字段 | 类型 | 含义 |
|-|-|-|
| `skill` | object | `{name,version,files}`，标识 Skill 与包内文件 |
| `case_id` | string/null | 原样取自输入 `case.json`（缺失时按语义键查找） |
| `status` | string | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `status_reason` | string | 状态的可读理由（含覆盖率、保真率） |
| `task` | object | `{instruction,scope,target_language}` |
| `output_contract` | object/null | **输入契约原样深拷贝** |
| 契约镜像字段 | 任意 | 契约声明的每个字段名都在顶层出现（见第 6 节） |
| `translation` | object | 段落级翻译主结果（第 3 节） |
| `glossary` | object | 术语表与一致率（第 4 节） |
| `claims` | array | 可核验结论（第 5 节） |
| `sources` | array | `{source_id,path,rel,kind,bytes}` |
| `segments` | array | `{seg_id,page,kind}` 段号索引（全文见 `work/segments.json`） |
| `artifacts` | array | `{file,bytes,sha1}`，output 目录内除 result.json 外的文件 |
| `coverage` | object | `{coverage_rate,paragraphs,translated,token_rate,segments_with_flags}` |
| `verification` | object | `{passed,checks{},summary{},rejected_claim_ids,heuristics}` |
| `uncertainty` | array | 未确定项（如文字层不可读、无译文输入） |
| `pending_human` | array | 待人工处理项（未译段、术语表空缺） |
| `errors` | array | `{stage,error[,file][,trace]}` |
| `degradations` | array | 降级事实（PDF 无文字层、旧版 Office 不支持……） |
| `changes` | array | `{ts,stage,action,detail}` 变更记录 |
| `runtime` | object | `{started,updated,elapsed_s,python,argv,input_dir,output_dir,work_dir,network}` |

## 3. `translation`

```json
{
  "target_language": "zh-CN",
  "source_document": "paper.pdf",
  "extraction_method": "pdftotext -layout | stdlib-pdf-scan | zipfile-docx | text-read | agent-supplied-text",
  "segmentation": {"rule": "...", "anchor": "seg_id + page + kind + section",
                   "paragraphs": 42, "sentences": 210},
  "paragraphs": [ ... ],
  "coverage": {"paragraphs": 40, "translated": 40, "references_preserved": 2,
               "coverage_rate": 1.0, "translated_chars": 15234},
  "token_fidelity": {"expected": 133, "kept": 131, "missing": 2, "rate": 0.985},
  "source_text": "全文（段间空行分隔，供 quote 校验）",
  "translation_inputs": ["/app/work/translations/b1.json"]
}
```

`paragraphs[]` 单段记录：

| 键 | 含义 |
|-|-|
| `seg_id` | 稳定段号 `P001`…（与 `work/segments.json`、双语稿、CSV 完全一致） |
| `page` | 原文页码（PDF 有分页）；无分页材料为 `null` |
| `kind` | `heading` / `body` / `caption` / `equation` / `reference` |
| `section` | 所属最近标题 |
| `status` | `translated` / `untranslated` |
| `translation` | 译文（未译时为空串，绝不填摘要） |
| `src_chars` / `src_excerpt` | 原文长度与前 160 字符（定位用，非全文） |
| `kept` / `expected` | 该段受保护标记的保留数/应有数 |
| `missing` | `{formulas:[],citations:[],xrefs:[],numbers:[],units:[]}` 未逐字保留的标记 |
| `terms` | 该段触及的锁定术语数 |
| `gviol` | 该段违反的锁定术语（原文出现而译文未含译名） |
| `flags` | `token_missing`/`glossary_inconsistent`/`negation_dropped`/`length_anomaly`/`untranslated` |
| `ratio` | 译文/原文字符比（`<0.12` 或 `>1.6` 追加 `length_anomaly`，仅提示） |

> 覆盖率分母是**可译段落**（`kind != reference`）；参考文献按惯例逐字保留，记入 `references_preserved`。

## 4. `glossary`

```json
{"rows": [{"term": "siRNA", "translation": "小干扰RNA", "freq": 12,
           "violation_seg_ids": [], "status": "locked"}],
 "locked": 12,
 "counts": {"candidates": 60},
 "template": "work/glossary.csv",
 "consistency": {"opportunities": 34, "violations": 1, "rate": 0.9706,
                 "method": "锁定术语在原文出现时译文须含该译名（忽略空白/连字符）"}}
```

- 候选来源：缩写（`[A-Z]…[A-Z]`，出现≥2 次或与全称配对）、高频二元短语（≥3 次）、`全称(缩写)` 配对。
- 只有 `translation` 非空的行才参与强制校验（`locked`）。
- `consistency.opportunities` 是“原文出现且已锁定”的段落-术语对数；`violations` 是其中译文缺译名的对数。

## 5. `claims`（三类）

```json
{"id": "C001", "kind": "translation_fidelity",
 "statement": "P012 译文保留 7/7 处数字·单位·公式·文献标记",
 "source_id": "S1", "readability": "directly_read", "produced_by": "script",
 "condition": "译文来自本次 translations 输入；去空白后逐字包含比对",
 "evidence": [{"quote": "原文逐字句", "source_id": "S1",
               "location": {"seg_id": "P012", "page": 3, "anchor": "paragraph",
                            "pointer": "/translation/paragraphs/P012"}}]}
```

| kind | 触发 | 数量上限 |
|-|-|-|
| `translation_fidelity` | 有受保护标记且已译的段落 | 每案例 5 条 |
| `terminology_consistency` | 已锁定且原文出现的术语（附 `term/target/violation_seg_ids`） | 每案例 4 条 |
| `coverage_boundary` | 存在译文时给出覆盖终点句 | 1 条（当前版本默认不写入） |

`readability` 取值：`directly_read`（原文直接可读）/ `inferred`（合理推断）/ `undetermined`（无法确定）。脚本只产出 `directly_read`——quote 一定来自原文分段文本；推断类结论应由 Agent 在正文中另行标注，不冒充原文。

## 6. `output_contract` 回填规则

1. `output_contract` 原样深拷贝到 `result.json.output_contract`（不删键、不改名、不换顺序）。
2. 契约声明的每个字段名必须在顶层出现。实现：`engine.shp()` 把契约投影成同形空壳，再按键名语义映射：
   `translat/译文 → translation`、`glossar/术语 → glossary`、`claim/结论 → claims`、`evidence → evidence`、
   `source → sources`、`cover/覆盖 → coverage`、`uncertain → uncertainty`、`pending/人工 → pending_human`、
   `error → errors`、`degrad → degradations`、`change → changes`、`runtime → runtime`、`segment → segments`、`status → status`。
3. 无映射的未知字段保留 `null`/`[]`/空对象，绝不删除；`C1_contract` 检查在写盘前计算，`verification.summary.contract_missing` 记录缺口。

## 7. `alignment.csv`（UTF-8-SIG，Excel 可直接开）

`seg_id,page,kind,status,src_chars,tr_chars,ratio,kept,expected,terms,flags,src_excerpt,translation`

- 行序 = 段号序 = 原文顺序；`flags` 内多项以 `;` 连接（术语违反段号附在 `flags` 后，前缀为 `gviol:` 时表示术语违规段）。
- 未译段 `status=untranslated`、`translation` 为空——**留空即证据**，不用摘要填充。

## 8. `glossary.csv`

`term,translation,freq,violation_seg_ids,status`；`status` ∈ `locked`（有译名，参与强制校验）/ 空。

## 9. `verification.json`

```json
{"passed": true,
 "checks": {"C1_contract": true, "C2_anchor": true, "C3_coverage": true,
            "C4_tokens": true, "C5_glossary": true, "C6_claims": true, "C7_artifacts": true},
 "summary": {"segments": 40, "translated": 40, "coverage_rate": 1.0, "token_rate": 0.985,
             "glossary_locked": 12, "glossary_rate": 0.97, "claims": 6, "claims_rejected": 0,
             "contract_missing": [], "segments_with_flags": 2},
 "rejected_claim_ids": [],
 "heuristics": ["否定/限定计数比对为启发式，可能误报，仅进 pending_human", "..."]}
```

## 10. 未译与拒收约定

- 未译：`status=untranslated`，双语稿写 `【未译 untranslated】…`，`pending_human.H1` 列出段号。
- quote 无法在原文定位：不写入 `claims`（或从 `rejected_claim_ids` 剔除），进 `pending_human`。
- 标记缺失：段记录 `missing` + `flags=token_missing`，聚合进 `token_fidelity`。
