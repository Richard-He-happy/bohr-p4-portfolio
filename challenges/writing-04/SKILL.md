---
name: citation-manager
description: 参考文献与引用管理 Skill。读取真实稿件与真实文献库（BibTeX / RIS / CSL-JSON / GB/T 7714 文本），完成论断级引用插入定位、顺序编码制编号连锁更新、文献去重归并（可解释判据）、GB/T 7714—2015 或 APA 7 格式转换、DOI 与元数据核验、正文—文献表一致性检查，产出可继续编辑的稿件、同步的文献表与逐条可回溯的 result.json。当用户要求“整理参考文献”“补插引用”“更新/重排编号”“文献去重合并”“改成 GB/T 7714 或 APA”“核对正文引用与文献表是否一致”时使用。脚本是工具，最终交付物由 Harness Agent 亲自读材料、推导、撰写/制作；不得将脚本骨架/模板直接当作成品。
version: 3.0.0
license: MIT
entrypoint: scripts/main.py
runtime: python3 >=3.8，仅标准库，离线
---

# citation-manager（写作04｜参考文献与引用管理）

## 0. 核心规则（最高优先级）

1. **单命令全流程优先**：先执行一次主命令，让脚本完成 init → build → selfcheck 基线；随后你在其基础上做核验、修正、补全。
2. **Agent-first**：你必须真实阅读 `/input` 原文与文献库，把你的判断写入 `/app/work/draft.json`，再让脚本按 draft 构建。不要把脚本自动抽取结果直接当作最终答案。
3. **确定性兜底**：如果预算或时间不足、模型无法继续，脚本/工作流必须用 init 台账确定性抽取生成实质工作稿，并诚实记入 `gaps/degradations` 为 `AUTO_EXTRACT`。
4. **完整性优先**：最终 `/app/output/result.json` 必须同时回显原始 `output_contract` 字段（顶层 + `output_contract` 嵌套各一次），包含 `case_id`。
5. **不编造**：不得补造材料中不存在的文献、数字、元数据、benchmark 分数或软件状态。
6. **永远退出码 0**：即使输入错误、脚本失败、材料缺失，也要产出合法 partial `result.json` 并退出 0。

---

## 1. 单命令入口

首选执行：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部完成：

- `init`：盘点 `/input` 全部材料，分配来源编号 `S1..Sn`，生成 `/app/work/input_manifest.json` 与 `/app/work/init_ledger.json`，抽取候选引用、条目、冲突分组。
- `build`：校验或兜底抽取，生成全部产物：`manuscript.md`、`references_formatted.md`、`references.json`、`result.json`、`report.md` 等。
- `selfcheck`：校验 JSON 合法性、产物存在性、契约字段覆盖、编号连续性、来源 locator 可回溯性。

如果 `run` 子命令不可用或返回非零：

1. 先运行 `python3 -B scripts/main.py --help` 确认当前入口。
2. 使用兼容基线命令，例如：

```bash
python3 -B scripts/main.py --input /input --output /app/output --style gbt7714
```

3. 然后手动执行本文件第 8 节的自检流程，绝不因脚本非零退出而放弃。

---

## 2. 运行时契约

| 项 | 路径 |
|-|-|
| 输入目录 | `/input` |
| 工作目录 | `/app/work` |
| 最终输出目录 | `/app/output` |
| 输入信息 | `/input/case.json`、`/input/task.md`、`/input/**` 材料 |
| 文档规则 | `references/rules.md`、`references/styles.md`、`references/usage.md` |
| 脚本 | `scripts/main.py`、`scripts/reftool.py` |

- 仅使用 Python 标准库，禁止联网。
- 所有路径基于 `__file__`，不依赖当前工作目录。
- 最终产物为 UTF-8 文本；不产生 symlink。
- 大纲、判断、中间数据可写 `/app/work`，最终交付物必须写 `/app/output`。
- 如果 `/app/output` 不可写，按脚本已实现的回退路径处理；不得因此崩溃。

---

## 3. 输入盘点与来源编号（init）

### 3.1 必须读取

- `/input/case.json`：提取 `case_id`、`output_contract`、任务指令、约束。
- `/input/task.md`：提取评分要求、输出字段、目标规范、边界条件。
- 递归扫描 `/input/**`，判断稿件、文献库、辅助材料。

### 3.2 材料类型识别

按文件头、扩展名和内容嗅探，而不是只看文件名。常见类型：

- 稿件：Markdown、TXT、DOCX（抽取正文文本）、PDF（实际 PDF，无预提取答案层）。
- 文献库：`.bib`、`.ris`、`.json`、`.enw`、GB/T 7714 文本列表。
- 辅助文件：说明、证据范围、白板信息等。

### 3.3 来源编号与 locator

每个输入文件分配稳定来源编号：

- `S1`、`S2`、...、`Sn`。
- `locator` 用 `S#` 加行号/段落号/页码，例如：`S1#L12-L14`、`S2#para3`、`S3#page5`。
- 所有引用、事实、数字、论断必须带 `[S#]` 与 locator。

### 3.4 生成台账

`/app/work/input_manifest.json` 至少包含：

```json
{
  "case_id": "从 case.json 提取，未知则用 task.md 标识或时间戳",
  "files": [
    {
      "source_id": "S1",
      "path": "manuscript.md",
      "kind": "manuscript",
      "bytes": 1234,
      "sha16": "..."
    }
  ]
}
```

`/app/work/init_ledger.json` 至少包含候选引用、候选条目、冲突分组、证据锚点。

---

## 4. Agent 路径：先读材料，写 draft.json

### 4.1 你的职责

在脚本基线之上，你必须亲自：

1. 读原始稿件相关段落，定位所有引用标记，如 `[1]`、`[3-5]`、`^[1]^`、`\cite{}`、`[@key]`。
2. 读文献库关键条目，核验作者、题名、年份、DOI、卷期页等。
3. 将脚本抽取的 quote、locator、数字与原文逐项比对。
4. 对不一致、低置信、重复条目、错误编号、错误合并做出决策。
5. 把决策写入 `/app/work/draft.json`。

### 4.2 draft.json 形状

建议每个决策项使用如下结构：

```json
[
  {
    "decision_id": "D1",
    "type": "insert_citation|replace_citation|renumber|merge|format|verify",
    "source_id": "S2",
    "locator": "S2#L12-L14",
    "quote": "原文逐字摘录",
    "manuscript_locator": "M1#para4",
    "decision": "插入到第4段第2句之后",
    "reason": "该句为可证伪论断，需要来源支撑",
    "confidence": "high"
  }
]
```

- `quote` 必须逐字来自原文，不得改写为摘要冒充原文。
- 找不到依据、无法判断的项，不要写进 draft；进入 `pending_human` 或 `uncertainty`。
- 每条合并决策必须写清依据：年、卷、页、DOI、题名、作者、文献类型。
- 不得将同一文献的不同版本/语言/数据库记录误合并，也不得把同名作者的不同文献误合并。

### 4.3 增量构建

Agent 路径下，先生成 draft，再让脚本 build。脚本应优先采用 draft 中的判断与原文证据构建成品；若脚本没有显式 draft 接口，则运行主命令后，由你按 draft 对成稿做增量修正，但结构化 JSON 的修改应通过 Python 脚本或脚本函数完成，而不是手工文本覆盖。

---

## 5. 无 draft 时的确定性兜底

如果预算/时间不足，或模型请求已接近上限，不能继续做逐条核验，则：

1. 使用 init 台账中的来源编号、候选引用、候选条目、冲突分组。
2. 用确定性规则构建实质工作稿：逐字 `quote`、locator、编号重排、按目标格式生成文献表。
3. 自动抽取/构建得到的内容必须在 `result.json.degradations` 或 `gaps` 中记入：

```json
{
  "mode": "AUTO_EXTRACT",
  "message": "未进行 Agent 逐条核验；产出为确定性基线。"
}
```

4. 此时 `status` 应设为 `partial` 或更诚实的 `insufficient_evidence`/`input_error`，不得伪装成 `ok`。
5. 保留所有已生成的中间文件和 final partial 结果，提前落盘，确保可复核。

---

## 6. 目标产物与契约回填

### 6.1 产物文件

默认必须交付：

| 文件 | 内容 |
|-|-|
| `manuscript.md` | 可继续编辑的稿件；编号连续、文末文献表同步、引用位置尽量落到论断句 |
| `references_formatted.md` | 按目标规范格式化后的文献表 |
| `references.json` | 结构化文献条目 |
| `result.json` | 最终结构化结果与契约回显 |
| `report.md` | 方法、结果、自检、增益证据、创新证据、限制与失败处理 |

若脚本额外生成 `citation_map.json`、`evidence_map.json`、`dedup_decisions.json`、`verification.json`，保留并纳入 result。

### 6.2 每个数字/论断的出处

在 `manuscript.md` 或 `evidence_map` 中，每个关键数字/论断/引用必须带：

- `[S#]` 来源编号。
- `S#` 对应的 `文件路径 + 行号/段落号/页码`。
- 源头 `quote`。

不允许出现“材料外新增事实”。

### 6.3 result.json 双回显

`result.json` 必须满足：

1. 顶层包含 `case_id`。
2. 顶层包含 `output_contract`。
3. `output_contract` 内也包含 `case_id`。
4. `output_contract` 内字段名与原始任务要求完全一致，原样回填。
5. 原始 `output_contract` 中的字段同时在顶层以同名或合适字段出现一次，形成双回显。
6. 所有数组字段即使为空也要存在，键名不可改。

### 6.4 result.json 推荐结构

```json
{
  "case_id": "CASE-X",
  "status": "ok|partial|insufficient_evidence|input_error",
  "sources": [
    {"source_id": "S1", "path": "manuscript.md", "kind": "manuscript", "bytes": 123, "sha16": "..."}
  ],
  "citation_map": [
    {
      "citation_id": "C1",
      "manuscript_locator": "M1#para4",
      "in_text_key": "[1]",
      "source_id": "S2",
      "quote": "原文内容",
      "claim_quote": "被支撑论断",
      "match_status": "exact_match|theme_match|weak_match|unverified",
      "match_rationale": "依据..."
    }
  ],
  "evidence_map": [
    {"claim_id": "CL1", "source_id": "S2", "locator": "S2#L12-L14", "quote": "...", "support_scope": "direct|partial|contextual"}
  ],
  "dedup_decisions": [
    {"decision_id": "DD1", "decision": "merge|keep_separate|ambiguous", "reference_ids": ["R3","R7"], "basis": "doi|title_year_volume|authors", "reason": "..."}
  ],
  "merge_groups": [
    {"canonical_source_id": "R3", "merged_source_ids": ["R7"], "fills": {}, "reason": "..."}
  ],
  "ambiguous_pairs": [],
  "change_log": [
    {"change_id": "CH1", "kind": "renumber|insert|delete|merge|format", "before": "...", "after": "...", "locator": "...", "reason": "..."}
  ],
  "verification": [
    {"check": "key", "status": "pass|warn|fail", "detail": "..."}
  ],
  "counts": {
    "input_files": 0,
    "source_entries": 0,
    "citations_in_text": 0,
    "references_final": 0,
    "inserted_citations": 0,
    "renumbered": 0,
    "merged": 0,
    "format_fixed": 0,
    "verified": 0,
    "pending_human": 0,
    "unresolved_markers": 0,
    "uncited_entries": 0,
    "missing_required": 0,
    "auto_applied": 0
  },
  "uncertainty": [],
  "pending_human": [],
  "missing_materials": [],
  "errors": [],
  "degradations": [],
  "runtime": {},
  "output_contract": {
    "case_id": "CASE-X"
  },
  "outputs": [
    {"path": "manuscript.md", "description": "可编辑成品稿件"}
  ],
  "agent_review": {}
}
```

---

## 7. 六类动作的完成与自证

### 7.1 引用插入与定位

- 不把引用统一堆在段末或图表注附近。
- 每个引用点尽量落在真正需要来源支撑的论断句或短句后。
- 一句多引、多句一引要明确：在 `citation_map` 中分别记录每个 `source_id` 与对应句。

### 7.2 编号更新与交叉引用

- 插入、删除、调序后，正文标号与文末列表同步更新。
- 编号必须 1..n 连续。
- 图表注、附录引用、交叉引用同步更新；无法解决的记为 `unresolved_markers`。
- `change_log` 中保留 `kind=renumber` 的前后映射，作为连锁更新证据。

### 7.3 文献去重与条目归并

- 同一文献的不同语言题名、预印本/正式版、期刊/会议版、不同数据库导出必须可解释合并。
- 合并依据写入 `dedup_decisions`：DOI、作者、年份、卷期页、文献类型、题名相似性。
- 相似但不确定的放入 `ambiguous_pairs`，不得强行合并。
- `merge_groups` 记录 canonical 条目与补全字段。

### 7.4 格式转换与字段补齐

- 目标规范为 GB/T 7714—2015 或 APA 7；根据输入自动判断。
- 保留 DOI、卷、期、页、文献类型标识等。
- 中英文混排、标点差异按 `references/styles.md` 处理。
- 缺失字段保留原值并写 `[待补]`，进入 `pending_human`。
- 不使用网络补全字段。

### 7.5 来源核验与一致性检查

- DOI 只做语法/格式核验，不联网解析。
- 元数据与正文引用条目逐条比对。
- 检出并标记疑似编造、错配、证据不足的句子。
- 每个引用条目必须在 `references.json` 中存在；文末列表与被引条目数一致。
- `uncited_entries` 只记入 `counts`，不应出现在最终文末引用表中。

### 7.6 正文—文献表一致性

- 文中每个编号在列表中有对应条目。
- 文献表中每条被引文献在正文有对应标记。
- 删除/合并后旧编号不得继续残留。
- 一致性结果写入 `verification`。

---

## 8. 自检流程（selfcheck）

结束前逐项执行：

1. `result.json` 是合法 JSON，无注释、无尾逗号；可执行：
   ```bash
   python3 -B -c 'import json,sys; json.load(open(sys.argv[1]))' /app/output/result.json
   ```
2. `case_id` 在 `result.json` 顶层与 `result.json.output_contract` 中均存在。
3. `output_contract` 的全部原始字段原样出现，类型合法。
4. `/app/output` 下存在：`manuscript.md`、`references_formatted.md`、`references.json`、`result.json`、`report.md`；若材料不足，则 `missing_materials` 中说明。
5. 正文引用编号为 1..n 连续，或未解析标记已记录。
6. 每个正文编号在文末文献表有对应条目；文末列表无孤立条目。
7. `citation_map` 每条有 `key/source_id/locator/claim_quote/quote`。
8. `dedup_decisions` 每条有 `reasons`；不确定项在 `ambiguous_pairs`。
9. `sources[]` 包含每个输入文件的 `id/kind/path/bytes/sha16`。
10. 所有 `quote` 均逐字来自源文件，不在材料中的事实不进入交付物。
11. `agent_review` 字段存在，记录 Agent 亲核至少 3 项：引用定位、编号、去重、格式、事实保留。
12. `errors`、`degradations`、`pending_human`、`uncertainty` 均存在，即使为空数组。
13. 无网络依赖、无第三方依赖；脚本 `--help` 可用且退出码 0。
14. 最终 `status` 诚实；不确定项已标注。
15. 若生成 Office/slide/diagram 类可编辑文件，若平台有 `soffice` 或等价转换器，应附 PDF/PNG 预览；若不可用，保留可编辑文件并记录 `no_office_preview` degradation。

---

## 9. 预算策略

- 官方预算：64 次模型请求、900 秒、单次响应含推理 16384 tokens。
- 脚本运行不消耗模型请求，但尽量控制在 30–60 秒内。
- 推荐模型请求分配：

| 阶段 | 请求数 |
|-|-|
| init/盘点输入 | 1–2 |
| 读材料/证据 | 3–6 |
| 写 draft/修正成稿 | 3–5 |
| selfcheck/契约回填 | 1–2 |
| 终检 | 1 |

合计约 12–17 次，留 47 次以上余量。

**止损规则**：

- 一旦累计请求 ≥ 60，或耗时 ≥ 800 秒：立即停止增强，写合法 partial `result.json`，退出 0。
- 大文件不要全文读，只读引用标记、文末列表、关键论断周边段落。
- 先落盘完整 baseline，再逐步增强；不要为低价值细节消耗请求。
- 如果 `/app/output` 已有一份合法 partial，增强失败时保留旧 partial 版本可核验。

---

## 10. 异常与降级

始终产出合法 `result.json`，退出码 0。

| 情况 | 处置 | status |
|-|-|-|
| `case.json` 缺失或坏 JSON | 记录 `errors`，继续扫描材料，用 `task.md` 标识或时间戳作 case_id | `input_error` 或 `partial` |
| `/input` 为空 | 生成最小合法 result，所有字段占位，记录 `missing_materials` | `input_error` |
| 稿件缺失 | 不虚构稿件，缺失材料登记 | `insufficient_evidence` |
| 文献库缺失/无法识别 | 不构造条目，只做结构回显或建议，记录缺失 | `insufficient_evidence` |
| PDF 无文本层/乱码 | 不伪造答案层，记录 `unsupported_binary_pdf` | 视其余材料 |
| DOCX 解析丢失上标/版式 | 保留文本，标注版式需人工复核 | `partial` |
| 单文件解析异常 | 只降级该文件，记录 `degradations` | 继续 |
| 条目字段缺失 | 保留原值/`[待补]`，加入 `pending_human` | `partial` |
| DOI 非法 | 保留原值，DOI 语法检查不通过 | 继续 |
| 编号指向列表外 | 原样保留，记录 `unresolved_markers` | 继续 |
| 重复/歧义无法判断 | 不合并，放入 `ambiguous_pairs` | 继续 |
| 脚本失败 | 捕获错误，Agent 手工构造最小合法 result，退出 0 | `partial`/`input_error` |
| 模型请求/时间耗尽 | 保存当前 partial，不再调用模型 | `partial` |

---

## 11. 使用增益与创新证据

平台会做基础 Agent 与 Skill Agent 对照；你不需要自造 baseline 分数。

在 `report.md` 中如实呈现以下证据，全部来自本地实际产物：

### 11.1 质量增益证据

- `verification` 中通过的确定性检查：编号连续、无孤立引用、无重复 DOI、正文—文献表一致。
- `citation_map` 中 `weak_match`/`unverified` 数量，说明低置信项被显式标出。
- `pending_human` 数量，说明减少人工逐条核对量。

### 11.2 效率增益证据

- `counts.auto_applied`：自动完成的插入/编号/去重/格式转换数量。
- `counts.pending_human`：仍需人工确认的数量。
- 两者比例用于说明人工修改量下降；不要编造外部流程的具体工时。

### 11.3 创新证据

- 编号连锁更新：`change_log` 中 `kind=renumber` 的前后映射链。
- 论断级引用匹配：`citation_map` 中每条的 `claim_quote` 与 `match_rationale`。
- 可解释去重：`dedup_decisions` 与 `merge_groups` 的合并判据。
- 格式映射规则：`references/styles.md` 中 GB/T 7714 / APA 映射表。

### 11.4 生态复用证据

- 去重规则、冲突处理规则见 `references/rules.md`。
- 格式规则见 `references/styles.md`。
- 调用说明、限制、失败模式见 `references/usage.md`。
- 脚本为可运行、无网络、纯标准库工具。

---

## 12. 最小调用示例

示例输入：

```text
/input/case.json
/input/task.md
/input/manuscript.md
/input/refs.bib
```

示例调用：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出：

```text
/app/output/manuscript.md
/app/output/references_formatted.md
/app/output/references.json
/app/output/report.md
/app/output/result.json
```

`result.json` 中的 `status` 为示意，正式案例下必须诚实反映实际运行状态。

---

## 13. 禁止事项

1. 不得将脚本骨架、模板或未经验证的 baseline 直接当最终成品。
2. 不得手工覆盖结构化 JSON 的契约字段结构；应通过脚本函数或 Python json 处理。
3. 不得生成金标准答案、伪造 diff 报告、伪造 benchmark 分数。
4. 不得补造材料中不存在的科学事实、文献、DOI、卷期页。
5. 不得因脚本失败、输入错误或格式不支持而退出非 0。
6. 不得忽略 `output_contract` 中任何原始字段。
7. 不得把同一篇文献的不同版本误合并，也不得把同名作者的不同文献误合并。
8. 不得网络检索或调用未声明的第三方依赖。

---

## 14. 成功兜底定义

如果无法达到 `ok`，至少做到：

- `/app/output/result.json` 存在且合法。
- `case_id` 尽力提取，未知则 `"unknown"`。
- `status` 诚实为 `input_error`、`insufficient_evidence` 或 `partial`。
- `sources` 列出已扫描到的输入文件。
- `output_contract` 的原字段全部出现，空值/占位合法。
- `errors`/`missing_materials`/`degradations` 说清限制。
- 其他产物若无法生成，在 `outputs` 中说明原因。

这比完美但崩溃更能得分，也符合 runtime contract。