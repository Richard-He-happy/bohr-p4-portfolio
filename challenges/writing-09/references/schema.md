# schema 与 locator 细则（v3）

## 1 locator 语法

| 材料 | 形式 | 例 |
|---|---|---|
| 文本 / Markdown / JSON / DOCX 段落 | `<相对路径>#p<段号>` | `material.json#p3` |
| CSV / TSV / XLSX 行（表头算 r1） | `<相对路径>#r<行号>` | `data/viability.csv#r2` |
| PDF 页 | `<相对路径>#pg<页号>` | `paper.pdf#pg4` |
| 位图 | `<相对路径>#fig` | `data/fig1.png#fig` |

行号/段号以 `init` 打印的 `loc :: text` 为准，直接复制，不要凭记忆写。`quote` 必须能在该 locator 的文本里逐字找到（比对前做 NFKC + 空白归一，不忽略数字与单位）。

## 2 `work/draft.json` 字段

| 字段 | 必需 | 含义 |
|---|---|---|
| `results` | 是 | `[{heading, paragraphs[], xref[]}]`，只写读数的段落 |
| `discussion` | 是 | 同上，解释 / 文献关系 / 因果边界 |
| `limitations` | 是（≥2） | 字符串数组，覆盖 method / sample / measure / stat 四层 |
| `evidence` | 是 | `[{id, quote, locator, approx?}]`，逐字引文 |
| `derived` | 否 | `[{value, formula, note}]`，自算值（差值、百分比） |
| `preserved_facts` | 否 | `[{fact, quote, locator}]`，必须逐字可核 |
| `changes` | 否 | 修改记录：`action / original_quote / revised_quote / reason` |
| `pending_human` | 否 | 材料缺口、需作者确认项 |
| `uncertainty` | 否 | 做了但不确定的判断 |
| `language` | 否 | `zh` / `en`；缺省按正文汉字比例判断 |

数字放行规则：Results 里每个数字必须命中某条 `evidence.quote`（或 `approx` 引文），或等于某条 `derived.value`。找不到就报 `number_unverified` 并给候选 locator。

## 3 `result.json` 字段

固定字段：`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`、`output_contract`、`contract_fields`。

`output_contract` 原样透传输入契约（键名不改、不省略；缺值 `null` / `[]`）。契约里的每个键再单独回填一份值（`deliverable` / `results_map` / `preserved_facts` / `evidence_map` / `change_log` / `limitations`，未知键给 `not_separately_produced` + `see`）。

`status`：`ok`（Agent 草稿 + 0 error）/ `partial`（兜底稿、或有 error、或补写了缺节）/ `insufficient_evidence`（无可读文本块）/ `input_error`（输入目录不可用）。

`metrics` 关键项：`numbers_total`、`numbers_verified`、`numbers_unverified`、`traceability_rate`、`evidence_total`、`evidence_ok`、`evidence_failed`、`results_sections`、`discussion_sections`、`limitations`、`mode`。

## 4 产物文件

| 文件 | 内容 |
|---|---|
| `manuscript.md` | `## 1. Results` / `## 2. Discussion` 两节 + `### Limitations` |
| `results_map.json` | 每个 Results 段落的读数 → 值 + 单位 + 来源 locator；含 `coverage`、`unverified` |
| `evidence_map.json` | 每条 evidence 的 `quote`/`locator`/`verified`（`exact`/`span`/`misplaced`/`notfound`） |
| `preserved_facts.json` | 事实 → 逐字引文 → locator → `verified` |
| `change_log.json` | `changes`、`pending_human`、`degradations` |
| `result.json` | 契约回填 + 状态 + 指标 + 错误 |

`results_map.sections[].readouts[].sources` 为该值在材料中出现的块 locator（最多 2 个）；`coverage.verified / coverage.numbers` 是整体可溯源率。
