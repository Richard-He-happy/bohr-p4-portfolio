---
name: academic-language-polish
description: >-
  Polish, copy-edit or translate academic prose sentence by sentence while
  locking numbers, units, citation markers, figure/table pointers, terminology
  and hedge strength. Use when a manuscript, abstract, thesis chapter, grant
  text, response-to-reviewers or bilingual abstract is supplied for language
  polishing, terminology unification, register adjustment or Chinese-English
  revision. Returns an editable manuscript plus a per-edit change log, a
  preserved-fact inventory and a claim-to-source evidence map. Do not use for
  content questions where no rewrite of the supplied text is requested.
version: 2.0.0
license: MIT
---

# 学术语言润色（writing-02）

## ★ 最高优先级规则

1. 本 Skill 解决的是“已有学术文本的语言润色”：改得对、说得像、没改坏、讲得清。
2. 交付物必须是**可编辑改稿 + 逐条修改说明 + 保留事实清单 + 来源定位 + 不确定性/待确认项**，不能只给写作建议或整段重写。
3. **事实守恒**：数字、单位、样本量、p 值、引用编号、图表指向、限定词强度、因果/相关区别、否定范围、条件句、量词必须原样保留；不确定时写入 pending_human，不编造。
4. **入口唯一**：优先执行 `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`。若脚本不支持 `run` 子命令，则退化为 `python3 -B scripts/main.py --input /input --output /app/output --work /app/work`。
5. **退出码恒为 0**。任何异常写入 errors/degradations/pending_human；不得抛出未处理异常。
6. **先落盘后增强**：尽量先得到完整 partial 基线，再增量改进；接近 780 秒时停止新增，重跑主脚本落盘并说明未完成范围。

---

## 1. 运行契约

- 输入：`/input/case.json` + `/input/task.md` + `/input/**` 材料。
- 工作目录：`/app/work`。
- 最终产物：`/app/output`。
- 仅使用 Python 标准库；离线；不依赖当前目录。
- 执行预算：64 次模型请求 / 900 秒 / 16384 tokens per response。
- Skill 资源约束：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB；不创建 symlink。
- 不提交预制答案；不生成白板、golden_standard、伪造 benchmark 分数。
- 原论文和实际输入文件是唯一事实依据；不按文件名或领域标签补造数据。

---

## 2. 单命令全流程入口

主命令内部等价于三个阶段：

`init` → `build` → `selfcheck`

```text
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

若 `run` 子命令不可用：

```text
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
```

### 2.1 init：盘点、编号、候选抽取、冲突分组

init 阶段必须完成：

- 递归扫描 `/input`，为每个可用材料分配稳定来源编号 `S1, S2, ... Sn`。
- 生成 `work/inventory.json`：文件路径、来源编号、类型、可读性、编码、文本规模。
- 抽取段落候选并建立 `work/workpack.json`，每段至少包含：
  `id, section, text, genre, locks[]`。
  `locks` 必须覆盖：numbers、units、citations、xrefs、hedges、boosters、abbreviations。
- 将术语冲突、引用冲突、数字冲突、材料缺口写入 `work/conflicts.json`，随后进入 pending_human。
- 解析 PDF 时按 `pdftotext` → `pypdf` → 内置 FlateDecode 顺序尝试；DOCX 走 zip XML；图片只登记不 OCR，记 degradations。
- 读不到 case.json 时递归找 `case*.json`；仍无则用 `task.md` + 材料，status=partial，错误如实写入 input_error/errors。

### 2.2 Agent-first 双路径

#### Agent 路径（优先）

1. 先运行 init，得到台账 `inventory.json`、`workpack.json`、`conflicts.json`。
2. Agent 真实读取 `/input` 原始材料，不依赖文件名或摘要猜测内容。
3. Agent 逐段判断润色动作，把判断写入 `work/draft.json`：
   - 每段含 `original`、`revised`、`edits[]`、`unchanged_reason`（无错时）。
   - 每条 edit 必须含：
     `id, section, para, original_quote, revised_quote, type, reason, locator, locks_checked`。
   - `original_quote` 必须在原文中逐字存在；`revised_quote` 必须在改后段落中存在；locator 使用 `[S#] 文件#段落/行号`。
4. 然后执行 build，将 draft 渲染为全部产物并回填 result.json。
5. 最后 selfcheck。

#### 确定性兜底路径（无 draft 时）

若 `work/draft.json` 不存在或为空，build 必须仍然产出**实质工作稿**：

- 用台账中的逐字文本 + init 候选生成每段基线润色。
- 每条修改必须带 verbatim `original_quote` 和 locator。
- 在 `result.json.degradations` 中诚实记录 `AUTO_EXTRACT`。
- 在 `change_log.csv` 中标记 `is_deterministic=true`。
- 不得伪造数字、引用、术语归属；不确定项进入 pending_human。
- 两条路径产出同一套文件与同一份 result.json 契约。

### 2.3 build：校验、兜底抽取、渲染全部产物、finalize result.json

build 必须：

1. 校验 `draft.json` 中的 quote 可回溯、revised quote 可定位。
2. 无 draft 时执行 2.2 的确定性兜底。
3. 渲染 `manuscript.md`、`deliverable.md`、`change_log.csv`、`evidence_table.json`、`glossary.json`、`result.json`。
4. finalize result.json：双回显 contract 字段，状态诚实。

### 2.4 selfcheck：产物与契约自检

运行：

```text
python3 -B scripts/verify.py --output /app/output --work /app/work
```

至少检查：

- output_contract 字段 × 磁盘文件 × result.json 键三者一致。
- original_quote 可回溯到来源；revised_quote 可定位到改稿。
- 锁项：数字、单位、引用、图表指向、hedges/boosters 未被改动。
- result.json 顶层与 nested output_contract 均含契约字段且值一致。
- status/sources/uncertainty/pending_human/errors/degradations 存在且真实。

---

## 3. 交付文件清单

所有可编辑文本产物写入 `/app/output`：

| 文件 | 作用 |
|---|---|
| `manuscript.md` | 润色后全文，可直接编辑/粘贴。 |
| `deliverable.md` | 交付包：全文 + 修改清单表 + 术语表 + 待确认项。 |
| `change_log.csv` | 每条修改：段落、类型、原文、改文、理由、定位、是否 deterministic、是否 verified。 |
| `evidence_table.json` | 事实/数字/引用/术语的 claim_id、source_id、locator、quote、strength、support_scope。 |
| `glossary.json` | 术语与同义变体、首次出现位置、source/target、冲突状态。 |
| `result.json` | 结构化结果，见第 4 节。 |

若题面要求 Office/slide/diagram 可编辑产物，必须额外给出真实渲染的 PDF/PNG 预览；本题默认交付 Markdown 可编辑稿，无需 Office 渲染。

---

## 4. result.json 契约与双回显

### 4.1 顶层必含字段

`case_id, status, deliverable, preserved_facts, evidence_map, change_log, glossary, bilingual, workorder_receipts, checks, coverage, counts, sources, uncertainty, pending_human, errors, degradations, changes, runtime`

### 4.2 output_contract 双回显

- 从 `case.json` / `task.md` 提取 `output_contract` 后，其所有字段必须**原样键名**同时出现在：
  1. `result.json` 顶层。
  2. `result.json.output_contract` 嵌套对象中。
- 两个位置的值必须一致；缺失值用 `null` / `[]`；未知字段保留不丢弃。
- 若材料未提供 output_contract，使用本 Skill 默认契约字段，并记 `missing_contract_fields`。

### 4.3 status 取值

- `ok`：完成核心交付。
- `partial`：有部分完成，且 pending_human 明确指出缺失/未完成范围。
- `insufficient_evidence`：无可读源文本或材料不足。
- `input_error`：输入解析失败、结构异常。

任何非 `ok` 状态，`pending_human` 必须具体说明缺什么、需要人工做什么。

---

## 5. 润色执行协议

每段按以下顺序执行：

1. **读锁**：numbers / units / citations / xrefs / hedges / boosters / abbreviations 是硬约束。
2. **找硬错**：主谓一致、时态、语态、冠词/介词、单复数、悬垂修饰、标点、长句切分、搭配、重复。
3. **最小编辑**：先改词、再改短语、最后才重排句子；不整段重写。
4. **守住主张**：hedge 不得加强或削弱；causal 与 correlational 不得互换；否定范围、条件句、量词不得改动。
5. **守住事实**：数字、单位、样本量、p 值、引用编号、图表指向原样保留；必须改数值时停手并记录。
6. **术语落地**：用术语表统一全篇同一概念；处理缩写首次出现、大小写、连字符、中英变体对齐。
7. **写说明**：每条 edit 必须给出 original_quote、revised_quote、type、reason、locator。
8. **回读**：改后段落必须仍等于原意、锁齐全、语气符合学术语域、不新增信息。

无错可改时，不要为改而改：`revised=original`，写 `unchanged_reason`。

---

## 6. 预算策略

优先级按 rubric 权重排序：

1. 实际效果 40 分：完整全文 + 逐条修改说明 + 事实与来源映射。
2. 可靠体验 10 分：契约完整、退出安全、异常诚实。
3. 使用增益/创新增益/生态贡献：通过锁清单、术语表回扫、证据映射、确定性兜底和文档体现。

推荐分配：

- 步骤 0–1 init + 盘点：最多 5 次模型请求。
- 步骤 2 材料解析核验：最多 5 次。
- 步骤 3 证据/术语基线：最多 8 次。
- 步骤 4 逐段润色：最多 35 次；每完成一整节或每 5 段重跑主脚本增量落盘。
- 步骤 5 selfcheck 修复：最多 8 次。
- 预留 3 次应急。

接近 780 秒或 60 次请求时：停止新增，重跑主脚本，保留 partial，写清未完成项。

---

## 7. 隐藏案例鲁棒性与异常降级

任何情况下退出码 0，产出合法 result.json。

| 情况 | 处置 |
|---|---|
| 无 `case.json` | 递归找 `case*.json`；仍无则用 task.md + 材料，status=partial。 |
| case.json 解析失败 | 记 errors，继续用 task.md，不中断。 |
| 无可读文本 | status=insufficient_evidence；pending_human 写明缺源文本；不编造。 |
| PDF 无文本层 | 记 pdf_text 降级；有图无文则 insufficient_evidence；不伪造原文。 |
| 编码混乱 | 依次尝试 utf-8/gb18030/big5/cp1252/latin-1；仍乱码则标记 encoding，段落保留原文。 |
| 公式/LaTeX 混杂 | 公式原样保留，只改公式外文字；不确定判断时 write pending_human。 |
| 术语表内部冲突 | 同时列出冲突写法，标 pending_human；不擅自选择。 |
| 目标文体不明 | 采用中性学术语域，记入 uncertainty；在 deliverable.md 注明假设。 |
| output_contract 缺失 | 使用默认字段并记 missing_contract_fields。 |
| 超长输入 | 正文全量保留；修改清单可优先核心段落，pending_human 列截断范围。 |
| `python3` 不可用或脚本报错 | 按 references/payload_and_result_schema.md 手工产出 manuscript.md、change_log.csv、result.json；status=partial；degradations 记 script_unavailable。 |
| 磁盘/权限错误 | 若 `/app/output` 不可写，写 `/app/work` 并说明；尽力产出合法 JSON。 |

---

## 8. 生态与复用

- `SKILL.md`：本文件，用途、触发、调用、输出、异常。
- `references/polish_protocol.md`：逐段润饰协议、最小编辑原则、术语回扫方法。
- `references/payload_and_result_schema.md`：draft.json、workpack.json、result.json 字段形状与契约说明。
- `references/evaluation_and_maintenance.md`：自检清单、限制、维护与复用说明。
- `environment/resources.yaml`：离线运行依赖与资源声明。

复用方应能使用同一套契约、同一套脚本、同一条命令，对自己的稿件完成一致的语言润色与可核验修改记录。

---

## 9. 禁止事项

- 禁止把“润色后的完整文本”降级为写作建议。
- 禁止无编辑痕迹的整段重写。
- 禁止删除、增强或削弱限定词、数据、单位、引用编号、图表指向。
- 禁止新增原文没有的事实、文献、数据或结论。
- 禁止手工篡改最终结构化 JSON；Agent 只写 draft.json，最终 JSON 由脚本渲染。
- 禁止生成无依据的 benchmark 分数、golden_standard、加权自评分。
- 禁止依据文件名或领域标签猜测源文本内容。
- 禁止用非本次运行产生的预制答案替代实际交付。