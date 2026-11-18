# 数据结构与定位规则（v5.0.0）

## 1. draft.json（可选；Agent 写 `/app/work/draft.json`）
```json
{"title": "可选",
 "sections": [{"heading": "2 方法",
   "paragraphs": [{"text": "段落（只改表达不改事实）",
     "quotes": [{"quote": "材料逐字原句", "locator": "paper.md:L9", "source_id": "M01"}]}]}],
 "facts": [{"quote": "含数值原句", "locator": "paper.md:L13"}]}
```
- `paragraphs[]` 可为字符串；`quotes[]` 可为字符串（无定位，靠全材料校验）。
- 校验：去掉全部空白后 `quote` 须出现在某材料文本中，否则**拒收**（进 `pending_human`，不入 `evidence_map`）。
- 限制：草稿 ≤8MB；未知键忽略。

## 2. result.json
| 字段 | 说明 |
|-|-|
| `output_contract` 各键 | 原样回填；值取 `case_id/deliverable/preserved_facts/evidence_map/change_log`，未知键 null |
| `case_id` | 取自输入，缺失为空串 |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverable` | `manuscript.md` |
| `preserved_facts` | 含数字原句 `{fact_id,value_text,source_id,locator}`，≤30 |
| `evidence_map` | `{claim_id,section,quote,source_id,locator,verified}`，≤150 |
| `change_log` / `changes` | 每节 `action/section[/verified|evidence]` + 末条 `finalize` |
| `sources` | `{id,path,kind,bytes,chars,readable,note}` |
| `uncertainty` | 摘录式组装、定位精度、PDF 未解析等声明 |
| `pending_human` | `{item,reason,action}`：PDF/二进制/拒收引用/缺章节/金标准未达标项 |
| `errors` | 输入级错误（如 `case_json_missing`） |
| `degradations` | `{code,path[,detail]}`，见 SKILL.md 第 10 节 |
| `exceptions` | 致命/审计层异常名（正常为空 []） |
| `coverage` | 材料/可读/证据句/事实/引用通过/拒收/H2/字符数 |
| `runtime` | `started_at/elapsed_s/python/version/input_root/output_root` |
| `artifacts` | 7 个产物的 `{path,bytes,sha256(16)}` |

### 2.1 v5 新增字段
| 字段 | 内容 |
|-|-|
| `golden_standard` | 与 `golden_standard.json` 同构：`schema/case_id/scope/section_standard/fact_preservation/citation_standard/global_checklist/provenance` |
| `diff_report` | `{schema,path,sha256,summary{total,met,deviated,missing,pass_rate,verdict,by_kind},items[≤80],items_total,truncated}` |
| `version_history` | `{schema,path,versions[{id,kind,path,bytes,sha256,status,how}],actions,rollback[]}` |
| `self_check` | `{schema,case_id,status,checks[],summary{passed,total,skipped,failed,ok},diff_summary,notes}` |

审计层不可用时上述三键为 `{"unavailable": true, "reason": ...}`，不阻塞主稿。

## 3. golden_standard.json（金标准，逐项可核）
```json
{"schema": "writing-01/golden-standard/v1",
 "case_id": "...", "run_status": "partial",
 "scope": {"materials": 4, "readable": 2, "sections": 8, "anchors": 10, "facts": 11, "citations": 3},
 "section_standard": [{"section_id": "S3", "key": "me", "heading": "2 方法", "required": true,
   "expected_elements": [{"element": "材料/样本与来源", "check": "heuristic", "criterion": "..."}],
   "material_anchors": [{"anchor_id": "S3.A1", "quote": "材料逐字原句", "locator": "notes.md:L7",
                         "source_id": "M03", "role": "required_quote", "verify": "去空白后逐字命中"}],
   "acceptance": "...", "anchor_count": 1}],
 "fact_preservation": {"rule": "数值/单位/样本量/p 值逐字保留", "items": [{"fact_id": "F02",
   "quote": "含数值原句", "locator": "notes.md:L7", "source_id": "M03", "must_keep": ["240", "4", "3", "20"]}]},
 "citation_standard": {"style_detected": "numeric-or-doi",
   "entries": [{"entry_id": "R01", "quote": "整条参考文献", "locator": "refs.md:L3",
                "source_id": "M04", "doi": "10.1016/j.postharvbio.2020.111289", "year": "2020"}],
   "rules": ["每条引用须支撑其所在论断", "..."]},
 "global_checklist": [{"id": "G1", "item": "六要素章节齐备", "check": "diff_report 全部 达标"}],
 "provenance": {"derived_from": "只读 /input 材料", "fabrication_policy": "材料外不生成",
                "quote_verification": "去空白后逐字比对；未命中者拒收"}}
```
要素级判定为 heuristic（语义），锚句/事实/引用级判定为确定性字符串比对。

## 4. diff_report.md（逐项对照）
表结构固定：`项目 | 类别 | 目标 | 期望 | 观测 | 状态 | 来源`。类别 6 种：
`section_presence`（H2 是否存在）、`section_content`（该节有无实质内容，防空节假达标）、
`anchor_quote`（逐字命中）、`fact_number`（数值保全）、`citation`（条目整条/分片/DOI）、
`declaration`（附录缺口行、数据可得性声明）。判定阈值：`NEAR=0.60`（trigram 覆盖）。

## 5. version_history.md（v0 → v1）
| 版本 | 含义 |
|-|-|
| v0 | `<work>/manuscript.v0.md`：章节骨架 + 待补要素 + 可用锚句计数 |
| v1 | `<output>/manuscript.md`：锚句组装成稿（或并入 draft.json） |

回退：`cp <work>/manuscript.v0.md <output>/manuscript.md`；或恢复 `draft.json` 后重跑 `build`。

## 6. run.log（一次运行一份）
`T+elapsed seq level event key=value`，level ∈ `START/STEP/FILE/WARN/EXC/END`；
最多 600 行（超限记 `entries dropped`）；`FILE` 行逐文件记录 kind/bytes/chars/readable/note。

## 7. self_check.json
| check id | 判据 |
|-|-|
| `contract_fields` | `output_contract` 每个键 + 5 个固定键 + 4 个新增键都出现在 result.json |
| `evidence_coverage` | 锚句逐字命中率 = 1.0、`quotes_rejected` = 0、evidence_map 非空 |
| `number_consistency` | 正文段落（排除标题/引用块/附录条目/元信息行）每个数字串以独立数值形式存在于材料；DOI 段剔除后比较 |
| `citation_consistency` | 金标准引用条目全部 达标（整条/分片/DOI 三级） |
| `empty_input_fallback` | 子进程实跑 `case.json={}`：退出码 0 且 result.json 合法 |
| `bad_json_fallback` | 子进程实跑截断 JSON + 1 份材料：退出码 0 且 result.json 合法 |
| `exit_code` | `main()` 全路径返回 0；记录探测子进程退出码 |
| `file_budget` | 包内文件 ≤10、总计 ≤120KB |

`ok=null` 表示跳过（嵌套探测），不是通过；`ok=false` 表示**检出问题**（如草稿含材料外数字），
不是运行崩溃——崩溃会落在 `exceptions`/`degradations`。

## 8. 定位符
`相对路径:L行号`。文本按原行；docx 按 `</w:p>` 切段后的行；JSON 材料按 `json.dumps(indent=1)` 展平后的行。
参考文献行整行作为一个引用单元（不拆句），避免拆断作者/卷期/DOI。跨行拆句可能偏移 ±1 行。

## 9. 状态判定
`input_error`：材料目录不存在且无材料；`insufficient_evidence`：无草稿且证据句为 0；
`ok`：有草稿、引用零拒收、`evidence_map` ≥5；其余 `partial`（含无草稿兜底组装）。
diff 的 `verdict` 与 `status` 相互独立：`status` 描述运行形态，`verdict` 描述与金标准的差距。
