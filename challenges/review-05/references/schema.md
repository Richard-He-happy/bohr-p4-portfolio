# 输入 / 输出 schema 与词表（review-05）

本文件是 `scripts/main.py` 与 `scripts/extract.py` 的**行为契约**。脚本按此处描述工作；若材料与描述不符，以脚本实际输出（`result.json`）为准，并把差异记入 `errors` / `degradations`。

## 1. 输入发现

| 项 | 规则 |
|---|---|
| 入口 | `--input` 目录（默认 `/input`），递归扫描全部普通文件，按文件名排序，最多 50 个（超出写 `degradations: file_cap`） |
| 案件描述 | 优先 `<input>/case.json`；不存在则取首个 `case*.json`；解析失败写 `errors: case_json_invalid` 并继续 |
| 材料类型 | 按扩展名+内容解析：`.pdf`（zlib 解压内容流取文本层）、`.docx`（`word/document.xml`）、`.xlsx`（`sharedStrings`+`sheet*.xml`）、`.txt/.md/.csv/.json/.bib/.ris/.tex/.html` 等按文本；图片仅登记为 `image_not_read`，**不读取像素、不做图内推断** |
| 内联稿件 | `case.json` 中长度 ≥60 的字符串按 JSON Pointer 建为独立来源（sid 形如 `CASEMANUSCRIPT`），主要用于稿件直接写在 JSON 里的情况 |
| 编码 | 依次尝试 utf-8 / utf-8-sig / gb18030 / latin-1；全部失败 → `degradations: decode_failed` |
| 补充文本 | `<work>/review/text/*.txt`（如自行 OCR/转写结果）会被索引为 `operator_text` 来源；支持 `[[p3]]` / `<<<PAGE 3>>>` / 换页符分页 |
| 缺口 | 材料未提供的对象（参考文献表、图、补充材料、伦理附件）**必须**在 `uncertainty` / `pending_human` 中列明，不得构造 |

## 2. 定位符（locator）

| 形式 | 含义 | 例 |
|---|---|---|
| `<sid>:P<n>` | 第 n 个段落块（PDF/DOCX/XLSX 每 6 行一块，纯文本每 14 行一块） | `MS:P12` |
| `<sid>:P<n>.S<k>` | 该块内第 k 句 | `MS:P12.S3` |
| `<sid>:DOC` | 仅在整篇可命中、无法定位到块（逐字校验回退路径） | `MS:DOC` |
| `REF:n<k>` | 文献表第 k 条 | `REF:n7` |

同时给出 `line`（`L<a>-L<b>`，来源文件行号）便于人工回查。`quote` 必须能在对应 locator 处**逐字**找到。

## 3. 词表（不得自创取值）

- `status`（顶层）：`ok` | `partial` | `insufficient_evidence` | `input_error`
- `checks.<facet>.status`：`pass` | `issues_found` | `not_applicable` | `not_checked` | `incomplete`
- `severity`：`blocker` | `major` | `minor` | `suggestion`
- `verdict_type`：`error` | `insufficient_evidence` | `norm_violation` | `suggestion`
- `confidence`：`high` | `medium` | `low`（`high` → 意见 `status=confirmed`，其余 → `needs_human`）
- `quote_verification`：`verbatim` | `verbatim_ws_insensitive` | `verbatim_doc_level` | `verbatim_auto`（仅历史路径）
- facet 键：`fact_verification` `citation_support` `method_design` `statistical_reporting` `argument_chain` `academic_norms`（也接受中文名 `事实核验` 等，及项号前缀 `FCT-` → `fact_verification`）

## 4. 裁定计划 `issues_plan.json`（可选，位于 `<work>/review/issues_plan.json`）

```json
{
  "case_id": "与输入一致",
  "checks": {
    "fact_verification": {"status": "pass", "scope": "数值↔图表", "notes": "", "not_applicable_reason": null},
    "citation_support": {"status": "issues_found", "scope": "引用↔文献表", "notes": ""},
    "method_design": {"status": "not_checked", "scope": "", "notes": ""},
    "statistical_reporting": {"status": "issues_found", "scope": "p 值/检验", "notes": ""},
    "argument_chain": {"status": "issues_found", "scope": "断言强度", "notes": ""},
    "academic_norms": {"status": "not_applicable", "scope": "", "notes": "", "not_applicable_reason": "无人体/第三方材料"}
  },
  "issues": [{
    "facet": "citation_support", "item": "CIT-01", "severity": "major", "verdict_type": "error",
    "title": "一句话问题", "source_id": "MS", "locator": "MS:P7",
    "quote": "必须是材料中的逐字片段",
    "evidence": [{"source": "REF:n7", "locator": "REF:n7", "quote": "文献表条目原文", "note": "对照说明"}],
    "reason": "为何构成问题", "suggestion": "可直接执行的修改", "confidence": "high",
    "related_candidates": ["C004"]
  }],
  "dismissed": [{"cid": "C002", "reason": "风格差异，非违规"}],
  "pending_human": [{"item": "伦理批号", "why": "材料未提供", "needed": "作者提供批件"}],
  "uncertainty": [{"item": "样本量口径不明", "impact": "影响检验力判断"}],
  "notes": "本轮裁定说明"
}
```

**校验规则（finalize 时强制执行）**
1. `facet` / `severity` / `quote`（≥8 字符）任一不合法 → 该意见**拒收**，写入 `review_records.rejected_issues` 与 `pending_human`（`被拒收：…`）。
2. `quote` 无法在材料中逐字命中 → 拒收，理由 `quote 未逐字命中`；**绝不改写原文凑通过**。
3. 全字段去重：同一 `source_id` + 同一规范化 quote 只保留首条，其余记 `duplicate`。
4. 排序：`blocker > major > minor > suggestion`，同级按六面顺序；编号 `R-01…`。
5. `checks.<facet>.status=pass` 但该面仍有未裁定候选（既不在 issues 的 `related_candidates`，也不在 `dismissed`）→ 强制改判 `incomplete` 并在 `notes` 写明候选号。
6. 未提供计划 → 六面 `notes="无裁定计划"`，`status=partial`，不生成任何臆测意见。

## 5. `result.json` 结构

```jsonc
{
  "skill_version": "1.0.0",
  "case_id": "原样保留，缺失为 null",
  "status": "ok | partial | insufficient_evidence | input_error",
  "summary": {"issue_total": 0, "facet_coverage": "0/6", "by_severity": {"blocker":0,"major":0,"minor":0,"suggestion":0},
               "needs_human": 0, "rejected": 0, "unaddressed": 0},
  "issues": [ /* 见上；另含 id、source_id、locator、line、quote_verification、status=confirmed|needs_human */ ],
  "checks": { "<facet>": {"status":"...", "scope":"...", "notes":"...", "findings":0, "unresolved":["C001"]} },
  "pending_human": [{"item":"...","why":"..."}],
  "sources": [{"sid":"MS","name":"manuscript.md","path":"...","kind":"text","chars":1234,"sha256_12":"...","status":"parsed"}],
  "uncertainty": [{"item":"...","impact":"..."}],
  "review_records": {"stage":"finalize","rejected_issues":[],"dismissed_candidates":[],"candidate_count":14,"reference_mode":"numbered", "...":"..."},
  "errors": [], "degradations": [], "changes": ["scaffold","finalized_partial"],
  "artifacts": {"candidates_json":"...","packets_md":"...","result_json":"...","review_report_md":"...","issues_csv":"..."},
  "runtime": {"python":"3.12.x","elapsed_s":0.4,"argv":["..."],"skill_version":"1.0.0","stage":"auto"},
  "contract_fields": {"requested":["..."],"filled":["..."],"unfilled":[]},
  "<output_contract 的每个键>": "按名映射填入；无对应者置 null 并列入 unfilled"
}
```

**契约回填**：`output_contract` 原对象另存于独立键（键名照抄，如 `output_contract`），其字段一律出现在顶层：`issues/findings` → `issues`；`checks/facet` → `checks`；`summary/count/stat` → `summary`；`sources/material` → `sources`；`uncertainty` → `uncertainty`；`pending/human` → `pending_human`；`status` → `status`；`caseid/id` → `case_id`；`runtime` → `runtime`；`error` → `errors`；含 `csv` → `issues.csv` 路径；含 `report/md` → `review_report.md` 路径；未知键 → `null` 且写入 `contract_fields.unfilled`。键名从不改写。

## 6. 产物

| 文件 | 内容 | 完成标准 |
|---|---|---|
| `result.json` | 上述结构 | 契约字段齐全；`case_id`/`status`/`sources`/`uncertainty` 存在 |
| `review_report.md` | 六面覆盖表 + 逐条问题（位置/原文/依据/理由/建议）+ 待复核/拒收 + 不确定性 + 材料与运行记录 | 每条问题可回查原文 |
| `issues.csv` | `id,facet,facet_zh,item,severity,verdict_type,source_id,locator,quote,reason,suggestion,confidence,status,related_candidates` | 行数 = `summary.issue_total` |

**可复现性**：同一输入 + 同一计划重复运行，`result.json` 除 `runtime.elapsed_s`（耗时）与路径类字段（`artifacts.*`、契约中的 `report`）外逐字段一致（`changes` 记录阶段名，不含耗时）。
| `<work>/review/candidates.json` | 全部候选（含 `cid`、`trigger`、`sev_hint`、`safe`） | 供复核与复用 |
| `<work>/review/packets.md` | 按六面分组的候选证据包（人读） | 与 candidates.json 一致 |

## 7. 退出码与预算

- 任何输入（空目录、坏 JSON、PDF 无文本层、plan 非法）均**退出码 0**，并至少写出 partial `result.json`。
- 先写 partial（`status=partial`）再细化，最终无条件覆盖为终态。
- 时间/请求预算内优先产出可交付结果；超时前应先落盘（脚本本身为毫秒级本地计算）。
