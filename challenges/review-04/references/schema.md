# 输入输出契约（review-04）

本文件说明：输入如何被发现、`issues_draft.json`（Agent 写入）与 `result.json`（最终产物）的字段、枚举、定位语义、`output_contract` 回填规则。

## 1. 输入发现（不假设键名）

| 顺序 | 位置 | 处理 |
|-|-|-|
| 1 | `/input/case.json`，否则 `**/case*.json` | 读 JSON；解析失败记 `errors`，继续按目录扫描 |
| 2 | `/input/task.md` | 视为指令源；其审查要求写进 `checks.*.scope`（不放 `issues`） |
| 3 | `/input/**` 其它文件 | 递归扫描，按扩展名 + 魔数判定类型 |

类型识别：`.pdf`（FlateDecode 内容流取文本层）、`.docx`（`word/document.xml`）、`.md/.tex/.txt/.csv/.json/.bib/.ris/.html`（纯文本读取）、其它二进制（`.xlsx/.png/.jpg`…）→ 不解码，记 `degradations`，其内容进 `uncertainty`（材料缺口，不当作者缺陷）。

`case.json` 里语义识别的键（存在即用，不强制）：
`case_id`/`id`、`output_contract`、`task_instruction`/`instruction`/`prompt`、`manuscript`/`paper`、`references`、`tables_figures`、`checklist`、`domain`/`field`、`citation_style`、`ethics_metadata`、`budget`、`artifacts`/`materials`。

稿件选取：可抽取文本的源按（类型优先级 pdf/docx/md/tex/txt，字符数降序）排序，取第一个有文本者为主稿；其余作参照材料。

## 2. `issues_draft.json`（Agent 写这个，`audit.py` 生成骨架）

```json
{
  "case_id": "...",
  "verdict": "一句总判断（可选）",
  "issues": [
    {
      "category": "argument",
      "severity": "major",
      "sentence_id": "S0020",
      "quote": "可省略：给了 sentence_id 就自动回填逐字原文",
      "title": "短标题（≤160 字）",
      "reason": "判断依据：违反了哪条，依赖哪两处原文",
      "suggestion": "可执行改法：补什么证据/改哪个词/降到什么强度",
      "evidence": [{"sentence_id": "S0011", "kind": "design"}],
      "severity_basis": {"affects_main_conclusion": true, "fixable_by": "降强度或补纵向设计",
                         "affects_reproducibility": false},
      "confidence": "high|medium|low",
      "status": "confirmed|pending_human",
      "check_item": "argument:strength"
    }
  ],
  "checks": {"factual": {"status": "ok|issues_found|partial|not_applicable", "scope": "...",
                         "unreviewed": ["..."], "note": "..."}},
  "uncertainty": ["未获取文献全文…"],
  "pending_human": ["图 1 无图像文件，图内元素未核验"],
  "rejected_candidates": [{"sid": "S0014", "rule": "statistics.reporting", "why": "方法段已给检验名"}]
}
```

规则：
- `category` 可用中文别名（统计/论证/引用…），`verify.py` 归一。
- `severity` 可写 major/minor 或 重要/次要，归一为 blocker/major/minor/suggestion。
- `quote` 省略时用 `sentence_id` 的原文回填；两者冲突以逐字匹配为准。
- `sentence_id` 与 `quote` 指向不同句 → 自动纠正 locator 并记入 `review_records.locator_corrections`。
- 引不到原文的 `quote`（改写/翻译/臆造）→ 拒收，进 `pending_human`，不进 `issues`。
- 空 `reason` 或空 `suggestion` → 保留但记入 `review_records.issues_missing_reason_or_suggestion`（会被评审视为可执行性不足）。
- `rejected_candidates` 记录被否决的机器线索，是误报控制证据。

## 3. `result.json`（最终，`verify.py` 写）

顶层必含：

| 字段 | 说明 |
|-|-|
| `case_id` | 原样保留输入值；缺失时用目录名并记 `degradations` |
| `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `summary` | `counts_by_category`、`counts_by_severity`、`total_issues`、`blockers`、`coverage_note`、`facet_coverage` |
| `issues[]` | 见下 |
| `candidate_issues[]` | 机器线索（未裁定），保留以便复核 |
| `claims[]` | 主张表：`sid, section, page, kind(own_data/citation/assumption/others_view/none), quote, support_type, support_refs` |
| `checks` | 六键：`factual, citation, method, statistics, argument, compliance` |
| `review_records` | 输入清单、稿件字符数、句子数、章节大纲、规则命中、locator 修正、拒收数、局限 |
| `sources[]` | `id, path, kind, chars, pages, segments, warnings` |
| `uncertainty[]` / `pending_human[]` / `errors[]` / `degradations[]` / `changes[]` | 诚实性字段 |
| `runtime` | skill/version/script/started/duration_s |
| `artifacts` | 各产物路径 |
| `output_contract` | 输入契约**整块原样**拷贝；其每个键同时出现在顶层（缺值 `null`/`[]`/`{}`） |

`issues[]` 单条：

| 字段 | 说明 |
|-|-|
| `id` | `R01`…（按严重度、字符位置确定性排序，同输入同编号） |
| `category` | 六类之一 |
| `severity` | `blocker/major/minor/suggestion` |
| `severity_basis` | `affects_main_conclusion` / `fixable_by` / `affects_reproducibility` |
| `title` | 短标题 |
| `locator` | `{section, paragraph, sentence_id, page, char_start, char_end, source_id}` |
| `locator_text` | 人读串：`§Discussion ¶10 S0020 p.5 chars 1065-1167` |
| `quote` | 稿件逐字原文（不改写、不拼接、不翻译） |
| `evidence[]` | 其它佐证：`{quote, locator, kind}`，同样逐字校验 |
| `reason` / `suggestion` | 判断依据 / 可执行改法 |
| `check_item` | `<类别>:<子项>` |
| `confidence` | `high/medium/low` |
| `status` | `confirmed` / `pending_human` |
| `basis` | `agent`（Agent 裁定）或 `deterministic_rule`（规则兜底，Agent 未写结论时） |

`checks.<key>`：`{status, scope, items_checked, findings[issue ids], unreviewed[], note}`。合法 status：`ok`（已查无问题）、`issues_found`、`partial`（部分未查，须在 `unreviewed` 写清）、`not_applicable`（须给原因）。

## 4. 定位精度（可核验性的下限）

- 句级 `sentence_id`（`S0001` 起，按全文顺序）+ 字符区间 `char_start/char_end`（相对提取后的纯文本）+ 章节 + 段号 + 页码（PDF 可映射时给，否则 `null`）。
- 页码只在「内容流数 = `/Type /Page` 数」时可一一对应；否则一律 `null`，不得猜页码。
- 报告中的引用与 CSV 使用同一 locator，便于交叉核对。

## 5. 产物清单与退出码

| 文件 | 作用 |
|-|-|
| `result.json` | 唯一必需产物，结构化结果 |
| `review_report.md` | 人读报告：结论摘要、问题表、逐条详述、覆盖表、缺口、复现命令 |
| `issues.csv` | 一行一条问题，含 locator 与 quote，可直接进评审表或 issue tracker |
| `audit_digest.md` | 限长阅读摘要（章节大纲 + 线索 + 逐句清单），供 Agent 在 token 预算内通读 |
| `issues_draft.json` | Agent 填写的问题骨架 |
| `.audit/index.json` | 解析缓存：源文本、句子表、线索、契约；`verify.py` 依赖它 |

两个脚本退出码恒为 0；失败信息一律写入 `errors`/`degradations`/`pending_human`，`result.json` 始终为合法 JSON。

## 6. `output_contract` 回填规则

1. `output_contract` 整块拷贝到 `result.json.output_contract`，键名不改、未知字段保留。
2. 其每个键在顶层也存在；缺值按声明类型给空：`array→[]`、`object→{}`、其它→`null`。
3. 若契约键与本 schema 同名（如 `issues`/`checks`/`verdict`），以本 schema 的值为准（即真实结果填充契约字段），不得为了填满契约而编造。
4. 契约含 `verdict` 等文本字段时，用 `issues_draft.json.verdict` 填入；未提供则留 `null` 并在 `coverage_note` 说明。
