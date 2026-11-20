---
name: results-discussion-writer
description: 面向“结果与讨论章节写作”的 Agent Skill：Agent 必须亲自读取 /input 真实材料，并把实验数据、图注、统计输出写成 Results 与 Discussion 分离的可编辑 manuscript.md，同时回填完整 result.json。脚本 init/check/build 只做材料盘点、证据核验、兜底成稿和契约拼装；最终章节、证据映射、修改记录和不确定性判断必须由 Agent 基于真实材料亲自推导和撰写。
version: 4.0.0
---

# 结果与讨论章节写作（writing-06，v4）

## 0 总原则与完整性优先

1. **脚本只是工具，不是成品**：`scripts/main.py init/check/build` 只负责材料索引、逐字引文核验、兜底稿生成、契约回填。最终交付物 `manuscript.md`、`results_map.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`result.json` 必须由 Agent 亲自读材料、推导、撰写或改写。禁止把 `draft.json` 模板、脚本兜底稿、示例数值直接当正式成品。
2. **先跑脚本产出完整基线，再增强**：进入任务后先运行 `init`，确保 `/app/output` 下尽早落盘 partial `result.json`；随后 Agent 撰写 `draft.json` 与完整章节；最后 `check`、`build`，在基线上增强并保留全部契约字段。
3. **完整性自检**：提交前必须逐项核对「`output_contract` 字段列表 × 磁盘产物文件 × `result.json` 键」三者一致。缺任何一项先补齐再收尾。partial 状态必须明确列出缺失项与限制。
4. **诚实优先**：不确定或材料不足必须写入 `pending_human`/`limitations`/`uncertainty`，不得编造数值、引用、统计量、图注语义或分数。材料里没有的文献、图号、单位含义，一律标缺口。
5. **退出码恒为 0**：任何异常都要留下合法 `/app/output/result.json`。

## 1 输入、目录与产物契约

### 输入
- `/input/case.json`：任务主契约。若不存在，递归查找 `case*.json`；若仍无，按默认契约字段回退。
- `/input/task.md`：任务说明与评分要求。
- `/input/**` 其他材料：CSV/TSV、TXT/MD/JSON、PDF、图片等。**必须真实解析材料内容**，不得依据文件名或领域标签猜测或补造。

### 工作目录
- `/app/work`：只能写 `index.json`、`draft.json`、`check_report.json` 等工作文件。

### 最终产物目录
- `/app/output`：必须包含 `result.json`。其他目标产物按任务要求生成，通常包括：
  - `/app/output/manuscript.md`
  - `/app/output/results_map.json`
  - `/app/output/evidence_map.json`
  - `/app/output/preserved_facts.json`
  - `/app/output/change_log.json`
- 若交付物是可编辑 Office/幻灯片/图形产物，则必须额外提供真实渲染的 PDF/PNG 预览；本题通常交付 Markdown 文稿，不强制 PDF/PNG，但若 `output_contract` 明确要求则必须满足。若环境无渲染工具，如实写入 `result.json.errors`/`pending_human`，不要伪造预览文件。

### `result.json` 要求
- 必须包含输入 `output_contract` 的**全部字段**，键名不改、不缺、缺值用 `null`/`[]`。
- 必须包含 `case_id`。
- 附加字段至少包括：`status`（`ok|partial|insufficient_evidence|input_error`）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`。
- 字段值必须真实：`sources` 列实际读取的文件；`metrics` 记录工具调用次数、耗时、`check` 统计等；`changes` 记录真实修改动作、原因、人工确认项和未解决问题。

## 2 预算策略（64 次模型请求 / 900 秒 / 单次响应 16384 tokens）

约束下必须优先完成 rubric 权重最高且最基础的交付物：**完整 manuscript.md + 合法 result.json**。

| 阶段 | 预计请求 | 动作 | 必须先落盘 |
|---|---|---|---|
| A 盘点与初始化 | 3-6 | 运行 `init`，读 `case.json`、`task.md`、材料清单 | partial `result.json` |
| B 材料解析与证据建立 | 8-15 | 打开/提取 CSV/TSV/JSON/TXT/PDF 文本层，逐表逐段读出数字、单位、误差棒、统计量、图注、行号 | 可先写 `work/draft.json` 的 `evidence` 骨架 |
| C Agent 撰写 | 10-20 | 基于真实材料亲自写 `draft.json` 与 `manuscript.md` 初稿 | `work/draft.json` |
| D 核验与修正 | 3-8 | 运行 `check`，消除 error；无法消除标 `pending_human` | `check_report.json` |
| E 成稿与收尾 | 2-6 | 运行 `build`，回填 `result.json`，逐项自检 rubric | 最终 `/app/output/*` |

- 阶段 A、E 必须做；时间不足时先 `build` 再润色。
- 避免反复读取同一文件；一次读取多个行/段。发现证据冲突先记录，不在同一问题上循环。
- 接近 850 秒或 58 次请求时，立即执行 `build` 并写 `result.json`，确保退出码 0。
- `init` 后若发现材料量很大，优先读取与 Results/Discussion 直接相关的表、图注、统计输出，不逐字通读全文。

## 3 执行流程

### 步骤 1：盘点输入与契约

**输入**：`/input`、`/app/output`、`/app/work`、`/skills/weekly-skill`  
**动作**：
```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --out /app/output
```
同时自行读取 `/input/case.json` 和 `/input/task.md`，确认 `case_id`、`output_contract` 字段、任务体裁与评分规则。列出 `/input/**` 下全部材料。

**输出**：`/app/work/index.json`、partial `/app/output/result.json`。`init` 会打印材料清单、表格数据行（含 locator）、图注行、缺口。

**失败分支**：脚本异常时，手动列出 `/input` 文件，读取 `case.json`（坏 JSON 则记入 `errors`），仍写出 minimal partial `result.json`，退出码 0。

### 步骤 2：用工具真实解析材料并建立证据基线

**输入**：`/app/work/index.json`、`/input/**` 实际文件  
**动作**：
- CSV/TSV：逐行读取数据列，确认剂量/时间、测量值、离散度、n。以 `init` 打印的 `locator` 为准。
- 文本/JSON/MD：逐段读取，抽取图注、统计输出、材料内引文。
- PDF：优先使用环境提供的 `pdf-text-tool` 等工具提取文本；若不可用，尝试脚本内置文本层解析。失败则记入 `pending_human`：`PDF 未被文本层解析`，不要猜测内容。
- 图片/位图：不做 OCR。若图注有数值，用图注；若图注也没有，写 `approx` 并说明“目视近似/未标约”。  
- 对每个关键数字、单位、误差棒含义、统计量，记录**逐字 quote + locator**。

**输出**：证据候选清单，放入 `work/draft.json` 的 `evidence`、`quotes`。

**失败分支**：材料缺失/损坏/格式不支持：将具体文件路径与原因写入 `degradations`、`pending_human`，不影响其他材料继续处理。

### 步骤 3：Agent 亲自撰写 `draft.json` 与 `manuscript.md`

**输入**：步骤 2 的证据清单、`task.md`、`references/writing-rules.md`  
**动作**：
- 写 `/app/work/draft.json`，包含 `results`、`discussion`、`limitations`、`evidence`、`derived`、`preserved_facts`、`changes`、`pending_human`、`uncertainty`。schema 见本文第 4 节。
- 写 `/app/output/manuscript.md`：`## 1. Results` 与 `## 2. Discussion` 分离。Results 只写观察，Discussion 承担解释、文献对照、因果边界、局限性。
- 每个数字能从 `locator` 回溯；自己算出的差值/百分比/倍数放 `derived` 并给公式。
- 材料不足或图表读数不明，写 `pending_human`，不要在正文中自行补造。

**输出**：`/app/work/draft.json`、`/app/output/manuscript.md` 初稿。

**失败分支**：缺少某类证据导致无法完成句子：保留缺口、写 `limitations`/`pending_human`，宁可不写也不要编造；可完成的其他段落继续写。

### 步骤 4：运行核验并修正错误

**输入**：`/app/work/draft.json`  
**动作**：
```bash
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --out /app/output
```
读取 `work/check_report.json`。针对 `error` 修正：
- `number_unverified`：补 quote/locator，或改为材料中真实数字。
- `evidence_bad`：用候选 locator 里的逐字原文。
- `results_causal`：把因果/机制词移到 Discussion。
- `sig_without_stat`：不写“显著”，或补材料中真实检验名/p 值。
- `overclaim`：改成 `suggests/consistent with`。
- `no_limitations/limitations_weak`：补足至少 2 条，覆盖方法、样本、测量、统计。

重复 `check`，直到 `errors=0`，或把无法修复的问题写入 `pending_human` 并进入下步。不得为了清零而删改事实。

**输出**：`/app/work/check_report.json`，`errors=0` 或误差已在 `pending_human` 中诚实说明。

**失败分支**：脚本报错无法完成 check：保留 `draft.json`，手工按其逻辑核验，将未核验内容写入 `pending_human`，继续 `build`。

### 步骤 5：成稿与预览自检

**输入**：`/app/work/draft.json`、`/app/output/manuscript.md`  
**动作**：
```bash
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --out /app/output
```
若脚本生成 `manuscript.md`、各映射 JSON；检查文件非空、可读。若交付物含 Office/图形，尝试用环境已有工具渲染 PDF/PNG，无法渲染则如实写入 `result.json.errors`。

**输出**：`/app/output/manuscript.md`、`results_map.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`result.json`。

**失败分支**：`build` 失败时，不要直接结束。使用现有 `draft.json` 和 partial `result.json`，手工补齐输出文件与 `result.json`，保证合法。

### 步骤 6：回填 result.json 并自检 rubric

**输入**：`/app/output/*`、`/app/work/*`  
**动作**：
- 核对 `result.json` 包含 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`。
- 确认 `status` 真实：全部数值核验通过且无缺口为 `ok`；有已标注缺口为 `partial`；材料不足为 `insufficient_evidence`；输入异常为 `input_error`。
- 把 Agent 亲自核验的结论写入 `changes`/`uncertainty`：如“已核验 table r2 与 manuscript 第 2 段一致”。

**输出**：最终 `/app/output/result.json`。

**失败分支**：任何字段缺失，补 `null`/`[]`；遇到未捕获异常，写 `result.json` 并退出码 0。

## 4 工作稿 schema（`/app/work/draft.json`）

```json
{
  "case_id": "原样",
  "title": "章节标题",
  "language": "zh|en",
  "results": [
    {
      "heading": "剂量依赖性活力下降",
      "xref": ["Fig. 1A"],
      "paragraphs": ["……"]
    }
  ],
  "discussion": [
    {
      "heading": "与已有证据的关系",
      "xref": [],
      "paragraphs": ["……"]
    }
  ],
  "limitations": [
    "方法层：……因此不能……",
    "统计层：……"
  ],
  "evidence": [
    {
      "id": "e1",
      "quote": "逐字原文",
      "locator": "data/viability.csv#r2"
    }
  ],
  "derived": [
    {
      "value": "55.3",
      "formula": "94.2 - 38.9",
      "note": "端点变化"
    }
  ],
  "preserved_facts": [
    {
      "fact": "0.5 µM 组 94.2%（SD 4.1, n=3）",
      "quote": "dose_uM=0.5 | viability_pct=94.2 | sd_pct=4.1 | n=3",
      "locator": "data/viability.csv#r2"
    }
  ],
  "changes": [
    {
      "action": "table cell -> sentence",
      "original_quote": "viability_pct=94.2",
      "revised_quote": "94.2% (SD 4.1, n = 3)",
      "reason": "转写为叙述值"
    }
  ],
  "pending_human": ["作者确认 Fig. 1A 面板编号"],
  "uncertainty": ["误差棒含义未给出"]
}
```

- `results`/`discussion` 至少各 1 节；正文一段一个字符串。
- `quote` 必须是材料的**逐字**片段（脚本做 NFKC + 空白归一后比对）；`locator` 见第 5 节。
- 自己算出的数放 `derived` 并给公式。
- 目视读图（图注没给数值）加 `"approx": true`，正文写“约 / approx.”，精度不超过坐标刻度。

## 5 locator 语法

| 材料 | 形式 | 例 |
|---|---|---|
| 文本 / JSON / Markdown 段落 | `<相对路径>#p<段号>` | `material.json#p3` |
| CSV / TSV 行 | `<相对路径>#r<行号>`（表头为 r1） | `data/viability.csv#r2` |
| PDF 页 | `<相对路径>#pg<页号>` | `paper.pdf#pg4` |
| 图件 | `<相对路径>#fig` | `data/fig1.png#fig` |

行号/段号以 `init` 打印的 `loc :: text` 为准，直接复制，不凭记忆写。

## 6 写作规则

### Results 只写观察
- 一段一个发现，按图序或问题组织。每个读数写全：**值 + 单位 + 条件 + 离散度/统计量 + 图/表号**。
- 必须带：`n`、误差棒含义（SD/SEM/CI）、检验名与 p 值（材料给出时）。
- 禁止：`导致/造成/因为/由于/机制/证明/证实/调控/驱动` 以及文献比较，这些属于 Discussion。
- 阴性/不显著结果照写，如 `p = 0.41，未与溶剂对照分离`；不省略、不改写成“趋势”。
- 未达显著的差异只写方向与幅度，不写“显著”。

### Discussion 承担解释
三拍推进：
1. **本研究数据支持什么**——回指 Results 具体读数，只到数据允许的强度。
2. **与已有证据的关系**——一致/不一致/部分一致及可能原因；材料没有文献时明确写出“材料未提供可对照文献”，不堆引用。
3. **边界与替代解释**——相关≠因果；机制推测标为推测；给出能证伪该解释的实验。

`limitations` 至少 2 条，覆盖方法、样本、测量、统计，要写“因此不能得出什么”，不写“样本量有限”空话。

### 因果梯度与语气

| 级 | 证据要求 | 允许表述 |
|---|---|---|
| 相关 | 观察性共变 | `与……相关` / `associated with` |
| 提示 | 剂量依赖、时间先后、方向一致 | `提示` / `与……一致` / `suggests` / `consistent with` |
| 因果 | 干预/敲除/救援 + 对照 | `导致` / `causes` / `leads to` |

材料只有观察数据时最高只到第二级。`证明/证实/首次/确证/demonstrated/confirm` 属过度断言。

###