---
name: thesis-chapter-revision
description: 在长文档/学位论文章节修订任务中，由 Agent 亲读材料撰写来源锚定的编辑注释或局部修改，脚本只负责索引、验证、装配、差异与预览；保留原文、输出可编辑稿件、证据映射、事实保持、修改记录、一致性报告和合法 result.json。用于章节起草/编辑、术语与编号一致性、引用锚点核查、局部修订复核。
version: 1.1.0
---

# 学位论文与长文档写作：真实解析、完整交付、可追溯修订

## 0. 完整性优先策略（最高优先级，未完成不得收尾）

1. **脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作**。禁止把脚本骨架、模板、确定性 fallback 或任何空壳内容直接当成品；它们只能作为基线和待核验草稿。
2. **先跑基线，再增量改进**：进入任务后，先运行本 Skill 的 `init` 命令，产出全套基线索引和合法 partial `result.json`。后续所有校验与改写只能在此基线上增强；**不得删除、清空或遗漏任何基线与契约字段**。
3. **完整交付优先**：最终交付物必须覆盖 `output_contract` 的全部字段、题面要求的所有可编辑产物、证据映射、修改记录和预览。缺任何一项先补齐再收尾；`status: partial` 必须列出缺失项。
4. **可核验增强**：在基线之上，由 Agent 亲自核验关键论断、数字、引用、术语、符号和跨章节一致性，把核验结论写入 `result.json`（`verified` / `pending_human` / `conflicts`）。这是“genuinely-derived”的直接证据，不可省略。
5. **诚实性优先**：不确定、材料不足、冲突或无法验证的问题必须显式标注 `pending_human` / `uncertainty` / `limitations`；不得编造数据、引用、分数或实验；不得静默“纠正”原文矛盾。

---

## 1. 用途与边界

本 Skill 面向“学位论文与长文档写作”的局部修订、编辑注释、一致性核查和版本管理任务。它加载材料中的章节或长文档，按工作单指定的 `target_ids` 或段落定位逐项执行：

- 在指定目标插入一条来源锚定的编辑注释或局部修改；
- 原样保留所有未请求的段落、表格、公式、引用、标题和编号；
- 生成可编辑的目标文稿，并输出事实/证据映射、修改记录、人工确认项和一致性报告；
- 通过版本控制证明原块未被改动、回滚与再应用真实可复现。

**边界**：它不重写作者原文，不发明引用、数值、表格、图表或章节，不把模糊单位静默改为标准单位，不把源内矛盾改“对”。材料未报告的内容明确标注为缺口，不联网补写。

---

## 2. 运行时契约

- **输入**：`/input/case.json`（或任意含 `case_id` / `output_contract` 的 JSON）、`/input/task.md`，以及 `/input/**` 下的材料（md、txt、docx、pdf、csv、json 等）。
- **工作目录**：`/app/work`；脚本生成的索引、草稿、检查报告均在此处。不要写入 `/app/output` 之外的临时文件。
- **输出目录**：`/app/output`。必须包含：
  - `result.json`
  - `manuscript.md`（可编辑目标文稿）
  - `consistency_report.md`
  - `manuscript_preview.html` 或等价可预览文件
  - `versions/`（包含版本、差异、回滚/再应用证据）
- **`result.json`** 必须包含：
  - `output_contract` 中的**全部字段**（键名不改，值按任务实际产出填写；未知键保留，缺失值以 `null` / `[]` 表示）
  - `case_id`（原样保留）
  - `status`：`ok` / `partial` / `insufficient_evidence` / `input_error`
  - `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`
  - `changes`、`runtime`
  - `deliverable`、`preserved_facts`、`evidence_map`、`change_log`
  - `workorder_receipt`
- **退出码**：任何路径都保证退出码 `0`；异常全部捕获并写入 `result.json`。
- **真实解析**：必须真实读取材料内容。不得依据文件名、领域标签或任务提示猜测材料内容。PDF 优先用可用的 `pdftotext` / pdf-text-tool 解析；没有文本层时记录为 degradation，不得虚构文本。
- **可编辑 Office/幻灯片/图形产物**：若目标产物是 docx/pptx/绘图等可编辑格式，必须额外给出真实渲染的 PDF/PNG 预览；若渲染工具不可用，必须记录 `degraded` / `pending_human`。

---

## 3. 输入发现与材料真实性

1. 运行 `init` 前，直接打开 `/input/case.json` 与 `/input/task.md`，确认：
   - `case_id`、`output_contract` 的具体字段；
   - 工作单（organizer workorder）中的 `target_ids`、`task`、`operation_requirements`、`consistency_scope`、`boundaries`。
2. `init` 会扫描 `/input`，按路径排序并识别材料。材料类型由扩展名**和** magic bytes 共同确定：`%PDF`、`PK` + `word/`、`PK` + `xl/` 等。**绝不信任文件名标签**。
3. `init` 打印材料索引、section 定位符、每个段落块的首部、工作单任务、每个 target 的解析定位符和尚未完成的 operation requirements。
4. 所有定位符由脚本生成，不得手写猜测。格式：
   - markdown/docx/pdf 散文：`<file> §<section number> <title> ¶<paragraph>`（标题本身写 `(heading)`）；
   - JSON：`<file> #<id>` 或 `<file> #/<json/path>`；
   - CSV/XLSX 行：`<file> #row N`（XLSX 若无法解析则记录 degradation）。
5. 如果 `/input` 不存在、`case.json` 缺失或损坏，`init` 仍必须写 `result.json`，`status=input_error`，`errors` 解释原因，退出码 `0`。

---

## 4. 本题专属执行流程

以下步骤按顺序执行。每步必须显式产生中间产物或可核验记录；失败时按“失败分支”降级，不得中断导致无 `result.json`。

### 步骤 0：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、工作单（若有）。
- **动作**：阅读 `output_contract` 的全部字段、`target_ids`、任务指令、边界；列出最终必须交付的文件与字段清单。不要跳过任何 `output_contract` 字段。
- **输出**：一份“交付物检查清单”（写入工作记忆，不要求落盘但必须用于最终自检）。
- **失败分支**：若 JSON 缺失或 `output_contract` 为空，仍继续执行 `init`，由脚本生成 `input_error` / `partial` 结果。

### 步骤 1：运行 `init` 建立索引与 partial 基线

```text
python3 scripts/main.py init --input /input --out /app/output
```

- **输入**：`/input` 全部文件。
- **动作**：脚本扫描材料、解析 case/workorder、生成 `/app/work/source_index.json`、材料索引、段落定位符，并写入第一版合法 partial `result.json`。
- **输出**：`/app/work/source_index.json`、`/app/output/result.json`（partial 基线）、终端打印的材料索引和 target 解析情况。
- **失败分支**：若材料无法解析，保留未解析材料名单，继续处理其余材料；`result.json.status` 为 `partial` 或 `input_error`。任何异常都不允许阻止 `result.json` 写入。

### 步骤 2：真实解析目标段落与相关证据

对每个 `target_id` 执行：

```text
python3 scripts/main.py show --target <target_id> --context 3 --chars 4000
```

- **输入**：`workorder.target_ids` 中的每个 target。
- **动作**：
  1. 读取 `show` 输出的精确原文段落和定位符；
  2. 根据 `init` 打印的索引，找到该段落所在章节的定义/方法/结果/讨论中与之相关的术语、数值、单位、引用和结论；
  3. 对可能产生冲突或需要一致性的地方，额外用 `show` 查看相关段落（保持 context 小，避免一次读取过长）；
  4. 记录每个 target 的“原文段落 → 锚定句 → 相关证据 → 可能存在的一致性问题”。
- **输出**：内部笔记（或工作记忆）中每个 target 的证据链与冲突清单。
- **失败分支**：
  - 若 target 不存在：不得猜测。在最终 draft 中标记 `status: pending_human`，`reason: target not found`，继续下一个 target。
  - 若段落文本乱码/无文本层：记录 degradation，不编造原文。
  - 若材料冲突：保留冲突，不修复；写入 `uncertainty` 和 `consistency_report.md`。

### 步骤 3：Agent 亲自撰写草稿 `work/draft.json`

- **输入**：步骤 2 的证据链和 `references/schemas.md` 中的 schema。
- **动作**：由你（Agent）手工创建/编写 `/app/work/draft.json`，不要复制模板空壳。每个 target 一项，必须包含：
  - `target_id`
  - `anchor_quote`：逐字从原文摘取的锚定句（必须与原文完全一致，只做空白/排版归一化）
  - `text`：2–4 句编辑注释或局部修改说明。解释科学条件、限制或可追溯澄清，**只能使用当前材料内证据**，不引入外部知识
  - `evidence`：至少一条逐字引用的证据 quote，并带 `locator`
  - `rationale`：说明为何这条注释/修改是来源支撑的
  - `status`：`proposed` 或 `pending_human`
- **输出**：`/app/work/draft.json`。
- **失败分支**：
  - 若某 target 无法可靠锚定或证据不足：写入 `pending_human`，附上最接近的原文引用和原因，不编造证据。
  - 若全部 target 均无法处理：仍保留草稿结构，目标项标记 `pending_human`，最终 build 使用确定性 fallback 并标 `needs_review`。
- **注意**：单次响应用来写多个 target 时要控制篇幅；每个 target 的 `text` 和证据要精炼。不要在 `draft.json` 中直接写整章重写内容。

### 步骤 4：运行 `check` 验证草稿

```text
python3 scripts/main.py check
```

- **输入**：`/app/work/draft.json` 与 `/app/work/source_index.json`。
- **动作**：脚本验证草稿的 quote 是否逐字命中、target 是否在范围内、证据是否可追踪、receipt 是否齐全。
- **输出**：终端打印高危/警告 findings。
- **失败分支**：
  - 存在 `high` finding：必须修复后再继续；修复可包括更正 quote、调整 locator、标记 `pending_human`。
  - 存在 `warn`：判断是否接受；若接受，记录到 `change_log` 和 `uncertainty`。
  - 若检查脚本因故无法运行：继续 `build`，但在 `result.json.errors` 中如实标注“check 未运行”，保持 partial。

### 步骤 5：运行 `build` 装配完整交付物

```text
python3 scripts/main.py build
```

- **输入**：`/app/work/draft.json`、`/app/work/source_index.json`。
- **动作**：脚本重新验证每条 proposal，应用被接受的注释/修改，保留被拒绝项及原因，装配 `manuscript.md`，生成版本、差异、回滚/再应用证据、一致性报告，并最终写出 `result.json`。
- **输出**：
  - `/app/output/manuscript.md`
  - `/app/output/consistency_report.md`
  - `/app/output/manuscript_preview.html`
  - `/app/output/versions/*`
  - `/app/output/result.json`
- **失败分支**：
  - 若某注释被拒：原文状态不变，`change_log` 记录拒绝原因。
  - 若 build 中途失败：保留已写入的 partial `result.json` 和已生成文件，`errors` 记录异常；退出码仍为 0。
  - 确定性 fallback 注释（若使用）必须标记 `generated_by: deterministic_fallback`、`needs_review: true`、`status: partial`，不得冒充 Agent 亲写内容。

### 步骤 6：生成预览并核对可编辑产物

- **输入**：`/app/output/manuscript.md` 或实际可编辑产物。
- **动作**：
  1. 确认 `manuscript.md` 可读且所有原文块与注释块分明；
  2. 若任务要求 docx/pptx 等可编辑 Office 产物，确认已生成，并尝试生成真实渲染的 PDF/PNG 预览；
  3. 若无法渲染，将原因写入 `result.json.degradations` 和 `pending_human`。
- **输出**：可预览文件；最终产物路径写入 `result.json.deliverable`。
- **失败分支**：渲染失败或超时，只影响预览，不删除已生成的可编辑产物；记录 degradation。

### 步骤 7：rubric 自检与 `result.json` 最终核对

- **输入**：步骤 0 的检查清单、`/app/output` 磁盘文件、`/app/output/result.json`。
- **动作**：
  1. 逐项核对 `output_contract` 字段、磁盘文件、`result.json` 键三者一一对应；
  2. 对照第 7 节“rubric 维度 → 交付要求 → 自证方式”表检查缺失；
  3. 检查 `status` 是否反映真实状态；`partial` 是否列出缺失项；
  4. 检查 `pending_human` 是否列出所有人工确认项；
  5. 检查版本证据：`rollback_equals_v1` 和 `reapply_equals_v2` 应为 `true`（脚本计算得到）。
- **输出**：最终 `result.json` 与所有交付文件。
- **失败分支**：任何字段缺失或文件缺失，补齐后重跑 `build` 或手工修补 `result.json`，确保合法 JSON。

---

## 5. 预算策略（64 次模型请求 / 900 秒）

按每案例一次运行分配：

1. **必做且高优先**：`init` → 每个 target 的 `show` → 1–2 次写入 `draft.json` → `check` → `build` → 渲染/预览。这些步骤保证完整交付物和合法 `result.json`。
2. **可跳过或压缩**：
   - 全篇通读材料：跳过；只读取 target 上下文和相关性最高的章节。
   - 非关键章节：只核对与 target 相关的定义/方法/结果/讨论。
   - 大段复制材料到响应：禁止；用 `show --chars 4000` 等限制。
3. **落盘 partial 时机**：`init` 已写第一版 partial；每完成一个 target 的草稿可考虑更新工作状态，但不要频繁调用 `build`；`build` 一次完成。
4. **避免无效循环**：不要在同一 target 上反复读同段文本；不要为微调注释多次整段重读；`check` 发现 `high` 才重写相关 target。
5. **保留预算**：通常 2–3 个 target 案例约需 10–15 次请求，剩余预算用于故障恢复、预览检查与最终修补。

---

## 6. 隐藏案例鲁棒性与异常处理

任何情况下都要产出合法 `result.json`，退出码 `0`。

| 情况 | 行为 |
| --- | --- |
| `/input` 缺失或 `case.json` 缺失 | `status=input_error`，`errors` 说明，退出 0 |
| `case.json` 损坏或非 UTF-8 | 尝试 `utf-8-sig` 解码；仍失败则 `status=input_error`，`errors` 记录 |
| 材料不可读或二进制格式不支持 | 该材料标记 `unreadable/skipped`，其余材料继续处理 |
| PDF 无文本层 | `status=degraded`，写 degradation 注记，不得虚构文本 |
| 无 `draft.json` | 使用确定性 fallback，`status=partial`，每项注释标 `needs_review: true` 并列入 `pending_human` |
| draft 中 quote 未命中 | 该 item 被拒绝，原状态不变，`change_log` 记录原因 |
| target 不存在 | 标 `pending_human`，不猜测 |
| 材料内部冲突 | 只报告不修正，写入 `consistency_report.md` 和 `uncertainty` |
| 检查脚本缺失或异常 | 继续 build，`errors` 说明检查未运行，`result.json` 仍合法 |
| 超时或工具箱失败 | 保留已有 partial `result.json` 和已生成文件，`errors` 记录，退出 0 |
| `output_contract` 缺失字段 | `result.json` 中以 `null` / `[]` 补位，并记 `degradations` |

---

## 7. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度（分值） | 交付要求 | 自证方式（必须在产物中体现） |
| --- | --- | --- |
| 实际效果：任务完成度（15） | 按工作单对每个 target 增加来源锚定编辑注释或局部修改，不是通用建议 | `manuscript.md` 中 `> **[EA-xx]**` 注释块；`workorder_receipt.targets[].status` 全部为 `done` 或 `pending_human` |
| 实际效果：结果正确性（15） | 每条论断、数字、术语、符号、图表编号与原文或给定材料一致 | `evidence_map[].evidence[].locator` 指向真实材料；`verbatim: true`；`preserved_facts[]` 逐项计算 `preserved: true/false` |
| 实际效果：结果完整性（5） | 要求的章节/段落、必要论证要素、著录项齐全，注释不破坏原文 | `manuscript.md` 包含所有源标题/段落；`version_control.source_blocks_unchanged: true` |
| 实际效果：结果可核验性（5） | 章节文字能追溯到大纲条目、原始材料、具体文献和版本记录 | `evidence_map`、`change_log`、`versions/*`；`workorder_receipt` 的 `version