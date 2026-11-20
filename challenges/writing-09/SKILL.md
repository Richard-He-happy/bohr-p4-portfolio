---
name: results-discussion-writer
description: 面向“结果与讨论章节写作”的 Agent Skill。单命令可运行完整工作流：材料盘点、来源编号、逐字证据抽取、Results/Discussion 分离成稿、证据映射、修改记录与诚实缺口登记。支持 Agent 先写 draft 增量改进，也支持无 draft 时确定性兜底成稿。强调逐字 quote、locator、因果语气控制、结果可核验、离线稳定与 result.json 契约双回显。
version: 5.0.0
---

# Results & Discussion Writer

## 0. 高层原则与优先级

本 Skill 的目标不是“生成一篇看上去像论文的文本”，而是：

1. 从 `/input` 真实材料中读取事实底稿、数据、图注、统计输出和引用信息；
2. 生成可编辑、可投稿、可复核的 Results 与 Discussion 分离章节；
3. 每个关键数字、单位、误差棒含义、统计量、引用与论断都可回溯到来源文件与 locator；
4. 对材料不足、冲突、无法判断和需要人工确认处诚实标注；
5. 输出合法 `/app/output/result.json`，满足原始 `output_contract` 全部字段；
6. 脚本异常也必须有 partial 结果并 `exit 0`。

执行优先级遵循 rubric 权重：

- 先保证 `manuscript.md` 存在、结构正确、可编辑；
- 再保证 `evidence_map.json` / `preserved_facts.json` / `change_log.json` 完整；
- 再保证 `result.json` 合法、双回显契约字段；
- 再在预算内做润色、核验与增量改进。

禁止：

- 依据文件名、领域标签或题目暗示补造数据；
- 把示例数值、模板字段、脚本兜底稿冒充正式成品；
- 自造 `golden_standard`、`diff_report`、加权自评分或 benchmark 分数；
- 对不可读图片/PDF 做无依据 OCR 式猜测；
- 删改事实以通过 check；
- 手工篡改结构化 JSON 结构字段。

---

## 1. 单一命令入口

最稳定、最省模型请求的入口：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 内部按顺序执行：

1. `init`：盘点 `/input` 全部材料，生成 `/app/work/index.json`，建立 source_id、文件类型、候选证据、冲突分组、缺口清单，并尽早落盘 partial `/app/output/result.json`；
2. `build`：若 `/app/work/draft.json` 已由 Agent 撰写，则使用该 draft；否则用 `/app/work/index.json` 确定性抽取生成 `/app/work/draft.auto.json`，逐字 quote + locator，写入 `AUTO_EXTRACT` 到 degradations，再渲染全部交付物；
3. `selfcheck`：校验产物文件、契约字段、result.json 双回显、证据 locator、Results/Discussion 语言边界和缺口登记。

Agent 推荐增量路径：

```bash
python3 /skills/weekly-skill/scripts/main.py init --input /input --work /app/work --out /app/output
# Agent 读取 /input 材料与 /app/work/index.json，撰写 /app/work/draft.json
python3 /skills/weekly-skill/scripts/main.py check --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py build --input /input --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/main.py selfcheck --input /input --work /app/work --out /app/output
```

两种路径必须产出同一套文件和同一份 result.json 契约：

- Agent 路径：质量更高，因为 Agent 实际读过原文并撰写 draft；
- 无 draft 兜底：确定性抽取，保证 partial/兜底成果落盘，并诚实记录 `AUTO_EXTRACT`。

任何阶段异常都必须写合法 `/app/output/result.json`，最后退出码 `0`。

---

## 2. 输入、工作目录与输出

### 输入

- `/input/case.json`：主任务契约，包含 `case_id`、`task_instruction`、`output_contract`、`source` 等；
- `/input/task.md`：任务说明、体裁、受众与约束；
- `/input/**`：真实科研材料，可能包括 CSV/TSV、TXT/MD/JSON、PDF、图片、补充表格、图注等。

如果 `/input/case.json` 不存在，脚本应递归查找 `case*.json`；仍不存在则使用默认契约字段并标 `input_error`。

所有事实必须来自实际文件内容。文件名只是索引，不是证据。

### 工作目录

`/app/work` 只放过程文件，至少包括：

- `index.json`：完整材料台账与来源编号；
- `draft.json`：Agent 撰写的工作稿；无 Agent 时由脚本生成 `draft.auto.json`；
- `check_report.json`：check 输出；
- `selfcheck_report.json`：selfcheck 输出。

### 输出目录

`/app/output` 必须包含：

- `result.json`：最终结构化结果；
- `manuscript.md`：可编辑的目标章节；
- `results_map.json`：结果段结构与段落级来源映射；
- `evidence_map.json`：关键论断到来源定位的映射；
- `preserved_facts.json`：数字、条件、术语和来源的逐字保存记录；
- `change_log.json`：修改动作、原因、人工确认项、未解决问题。

若原始 `output_contract` 额外要求 Office/slide/diagram 等可编辑产物，还必须生成对应可编辑文件，并尽可能提供真实渲染 PDF/PNG 预览；无法渲染时写 `errors`，不得伪造预览。

---

## 3. result.json 契约

`result.json` 必须同时满足以下要求：

### 顶层字段

- 必须包含输入 `output_contract` 的所有字段；
- 必须包含 `case_id`；
- 必须包含以下附加字段：
  - `status`：`ok` | `partial` | `insufficient_evidence` | `input_error`
  - `sources`：实际读取的文件列表
  - `uncertainty`：单位不明、误差棒不清、统计量缺失等
  - `pending_human`：需要作者确认的事项
  - `errors`：运行中不能消除但已处理的错误
  - `degradations`：降级处理，如 `AUTO_EXTRACT`、`PDF_NO_TEXT`、`NO_RENDER_PREVIEW`
  - `changes`：真实修改记录
  - `metrics`：工具调用次数、耗时、check 统计等
  - `runtime`：运行时间、命令、文件数量等

### 嵌套双回显

- `result.json` 内必须有 `output_contract` 字段；
- `output_contract` 再次包含与顶层相同的契约字段，键名完全一致；
- 不允许只放顶层或只放嵌套，必须两层都出现。

示例最小结构：

```json
{
  "case_id": "EXAMPLE",
  "deliverable": "manuscript.md",
  "preserved_facts": ["..."],
  "evidence_map": "evidence_map.json",
  "change_log": ["..."],
  "output_contract": {
    "case_id": "EXAMPLE",
    "deliverable": "manuscript.md",
    "preserved_facts": ["..."],
    "evidence_map": "evidence_map.json",
    "change_log": ["..."]
  },
  "status": "partial",
  "sources": ["/input/viability.csv"],
  "uncertainty": ["误差棒含义未给出"],
  "pending_human": ["请确认 Fig. 1A 面板编号"],
  "errors": [],
  "degradations": ["AUTO_EXTRACT"],
  "changes": [],
  "metrics": {"script_calls": 3, "evidence_claims": 12, "verified_claims": 10},
  "runtime": {"seconds": 18.4, "entry": "run"}
}
```

---

## 4. init：材料盘点、来源编号与候选抽取

`init` 必须完成：

1. 列出 `/input/**` 全部文件；
2. 为每个来源文件分配 `S#` 编号，例如 `S1`、`S2`；
3. 识别文件类型并抽取候选证据；
4. 对每个候选证据写入：
   - `source_id`
   - `quote`：逐字片段
   - `locator`：`<file>#p<段落号>`、`<file>#r<行号>`、`<file>#pg<页号>`、`<file>#fig`
   - 可能的消息类型：数值、单位、误差棒、统计、图注、文献；
5. 冲突分组：同一指标出现不同取值、同一名词出现多种单位、同一图号出现不同面板时，进入冲突组；
6. 缺口清单：文件缺失、PDF 无文本层、图片无图注、统计量缺失、单位不明等写入 `gaps`；
7. 立即写 partial `/app/output/result.json`。

### locator 规则

| 材料 | locator 形式 | 示例 |
|---|---|---|
| CSV/TSV | `<file>#r<行号>` | `S1:data/viability.csv#r2` |
| TXT/MD/JSON 段落 | `<file>#p<段号>` | `S2:material.md#p3` |
| PDF 页/段落 | `<file>#pg<页号>`[#p<段号>] | `S3:paper.pdf#pg4` |
| 图件 | `<file>#fig` | `S4:fig1.png#fig` |

行号/段号以 `init` 打印的 `loc` 为准，不得凭记忆写。

### 文件抽取策略

- CSV/TSV：表头为 r1，逐行读列，记录剂量、时间、测量值、离散度、n；
- JSON：递归读取文本和数值字段，保留路径；
- TXT/MD：分段读取，识别数字、单位、统计量、图注、引文；
- PDF：优先使用环境已有 `pdf-text-tool`/`pdftotext`，然后尝试文本层解析；实际 PDF 没有预抽取答案层时，只使用真实文本层内容；
- 图片：不做 OCR。若图片附近有图注，抽取图注；若图注缺失，写 `approx` 或 `gap`；
- 文件损坏或不支持：写 `degradations` 和 `pending_human`，不影响其他材料。

---

## 5. Agent 写 draft：事实与判断的增量层

Agent 在 `init` 后应亲自读取 `/app/work/index.json` 和 `/input/**` 原始材料，并写 `/app/work/draft.json`。

### draft.json 最小 schema

```json
{
  "case_id": "原样",
  "title": "章节标题",
  "language": "zh 或 en",
  "results": [
    {
      "heading": "剂量依赖性下降",
      "xref": ["S3:paper.pdf#pg4"],
      "paragraphs": ["正文段落"]
    }
  ],
  "discussion": [
    {
      "heading": "与已有证据的关系",
      "xref": ["S2:material.md#p3"],
      "paragraphs": ["正文段落"]
    }
  ],
  "limitations": [
    "方法层：……",
    "统计层：……"
  ],
  "evidence": [
    {
      "id": "e1",
      "quote": "viability_pct=94.2 | sd_pct=4.1 | n=3",
      "locator": "S1:data/viability.csv#r2"
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
      "fact": "0.5 µM 组 94.2% (SD 4.1, n=3)",
      "quote": "viability_pct=94.2 | sd_pct=4.1 | n=3",
      "locator": "S1:data/viability.csv#r2"
    }
  ],
  "changes": [
    {
      "action": "table cell -> sentence",
      "original_quote": "viability_pct=94.2",
      "revised_quote": "94.2% (SD 4.1, n=3)",
      "reason": "转写为叙述值"
    }
  ],
  "pending_human": ["作者确认 Fig. 1A 面板编号"],
  "uncertainty": ["误差棒含义未给出"]
}
```

### Agent 写作规则

- Results 只写观察；
- Discussion 承担解释、文献对照、因果边界和局限；
- 每个数字、引用、论断必须能在 `evidence_table.json` 或 `draft.json.evidence` 中找到依据；
- 自己计算的差值/百分比/倍数放 `derived` 并给公式；
- 材料没有文献时写“材料未提供可对照文献”，不堆引用；
- 目视读图且图注未给数值时，正文写“约 / approx.”，精度不超过坐标刻度。

### 禁止手改结构化产物

- `claims.json`、`evidence_table.json`、`result.json` 的结构字段必须由脚本生成；
- Agent 不覆盖键名、claim_id、source_id、locator、quote、counts；
- Agent 核验结论写入 `agent_review.json`；
- 若需修正脚本缺陷，用临时脚本调用原函数重写并记录到 `agent_review.json` 的 `script_fixes`，不手工篡改 JSON。

---

## 6. 无 draft 确定性兜底

若 `/app/work/draft.json` 不存在，`build` 必须：

1. 基于 `/app/work/index.json` 的台账确定性抽取；
2. 生成 `/app/work/draft.auto.json`；
3. 每个数值/论断带 `quote` 与 `locator`；
4. 自动生成 `manuscript.md`、`results_map.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`；
5. 在 `result.json.degradations` 和 `draft.auto.json` 中记录 `AUTO_EXTRACT`；
6. 不新增材料外事实；
7. 对不能确定的内容写 `pending_human` 和 `uncertainty`。

该兜底用于节省模型请求并在极端预算下仍交付可复核产物。兜底稿可能不流畅，但必须事实正确、边界清楚。

---

## 7. check：质量与契约核验

`check` 应至少检查：

- `number_unverified`：正文数字无 quote/locator；
- `quote_not_verbatim`：quote 与原文不一致；
- `locator_invalid`：locator 不在 index；
- `derived_without_formula`：派生值无公式；
- `results_causal`：Results 中使用“导致/因为/机制/证明”等因果词；
- `discussion_without_evidence`：Discussion 关键论断无证据支撑；
- `sig_without_stat`：写“显著”但无检验名/p 值；
- `overclaim`：出现“证明/证实/首次/确证/demonstrated/confirm”等过度断言；
- `no_limitations` / `limitations_weak`：未写局限或局限空泛；
- `result_contract_key_missing`：result.json 缺原始契约字段；
- `case_id_missing`：缺失 case_id。

`check` 输出 `/app/work/check_report.json`。

Agent 应逐项修正 error；无法修正或材料不支持时必须写 `pending_human`，不得为清零删改事实。`errors=0` 不等于完美；剩余 uncertainty 要保留。

---

## 8. build：渲染全部产物

`build` 必须：

1. 读取 `/app/work/draft.json` 或 `draft.auto.json`；
2. 渲染 `/app/output/manuscript.md`；
3. 生成所有映射 JSON；
4. 回填 `result.json` 顶层与嵌套 `output_contract`；
5. 写入 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`；
6. 若交付物要求可编辑 Office/幻灯片/图形，尝试渲染 PDF/PNG；无法渲染写 errors；
7. 保证退出码 0。

`manuscript.md` 至少包含：

- `## 1. Results`
- `## 2. Discussion`
- `## 3. Limitations`
- `### Pending human checks`（若有）
- `### Source notes`（简短，说明 locator 约定）

---

## 9. selfcheck：最终自检清单

`selfcheck` 或 Agent 结束前必须核对：

- 原始 `output_contract` 字段是否全部出现在 `result.json` 顶层；
- 原始 `output_contract` 字段是否全部出现在 `result.json.output_contract`；
- `case_id` 是否保留原样；
- `manuscript.md` 是否存在且非空；
- `evidence_map.json`、`preserved_facts.json`、`change_log.json` 是否存在且非空；
- 正文中每个关键数字是否可回溯到 locator；
- Results 是否存在因果语言；
- Discussion 是否包含证据对照与局限；
- 缺失证据是否写 `pending_human`；
- 异常是否写 `errors` 或 `degradations`；
- 是否使用了合法 `/app/output` 路径；
- 是否有结果但 status 被误标为 ok。

若存在缺口，`status` 应为 `partial` 或 `insufficient_evidence`。

---

## 10. 学术写作规则

### Results 只写观察

- 一段一个发现，按图序或问题组织；
- 每个读数写全：值 + 单位 + 条件 + 离散度 + n + 统计量 + 图/表号；
- 材料给出统计量时，写检验名与 p 值；未给出时不写“显著”；
- 阴性结果照写，如“p = 0.41，未与溶剂对照分离”；
- 未达显著只写方向与幅度；
- 禁止：`导致、造成、因为、由于、机制、证明、证实、调控、驱动`；
- 禁止文献比较，文献比较属于 Discussion。

### Discussion 承担解释

三拍推进：

1. 本研究数据支持什么：回指 Results 具体读数，只到数据允许强度；
2. 与已有证据关系：一致、不一致、部分一致及可能原因；没有文献就写“材料未提供可对照文献”；
3. 边界与替代解释：相关不等于因果；机制推测标为推测；给出能证伪该解释的实验方向。

### 因果梯度与语气

| 证据等级 | 表述 |
|---|---|
| 观察性共变 | `与……相关` / `associated with` |
| 剂量依赖、时间先后、方向一致 | `提示` / `与……一致` / `suggests` / `consistent with` |
| 干预/敲除/救援 + 对照 | `导致` / `causes` / `leads to` |

材料只有观察数据时最高到第二级。

### 局限性

`limitations` 至少 2 条，覆盖方法、样本、测量、统计层面，并写出“因此不能得出什么”。例如：

- “样本量有限，因此不能排除较小效应的假阴性”；
- “误差棒含义未说明，因此无法判断离散度是 SD 还是 SEM”。

只写“样本量有限”是空话，不可作为唯一局限。

### 语言自适应

- 任务明确中文则用中文；
- 任务明确英文则用英文；
- 未明确时默认源材料语言；
- 双语要求时，`manuscript.md` 需包含双语版本段落或双语映射，并保持证据 locator 一致。

---

## 11. 隐藏案例鲁棒性

### 正常案例

- 材料包含 CSV/表格/图注/统计输出/PDF，任务要求写 Results 与 Discussion；
- 正常路径：init → Agent/兜底 draft → check → build → selfcheck；
- 交付：`manuscript.md`、映射 JSON、result.json。

### 边界案例

- 只有图片无数据表；
- 只有图注无统计量；
- 多面板图/补充材料编号复杂；
- 单位模糊、误差棒含义未说明；
- 语言切换、目标格式为双语或结构化产物。

应对：

- 图注缺失数值时标 `approx` 或 `gap`；
- 统计缺失时不写“显著”；
- 多面板图保留原始编号，不重命名；
- 单位不明写 `pending_human`，正文不使用未确认单位；
- 双语或结构化成稿保留相同事实和 locator。

### 异常案例

- `/input/case.json` 缺失或坏 JSON；
- 材料文件损坏或格式不支持；
- PDF 没有文本层；
- 图片无图注；
- 同一指标冲突；
- output_contract 字段异常。

应对：

- 坏 JSON 写 `input_error`，尽量解析可用字段；
- 文件损坏写 `degradations`；
- PDF 无文本层写 `PDF_NO_TEXT`；
- 图片无图注写 `FIG_NO_LEGEND`；
- 冲突写 `pending_human`，不随意选一个；
- 缺 case_id 时使用 `MISSING_CASE_ID` 并写 `errors`。

---

## 12. 预算策略与收尾

官方预算：64 次模型请求 / 900 秒 / 单次 16384 tokens。

推荐分配：

| 阶段 | 请求次数 | 强制产出 |
|---|---|---|
| init | 1-3 | partial result.json |
| 材料解析 | 5-10 | evidence 骨架 |
| Agent 成稿 | 8-15 | draft.json + manuscript.md |
| check/修正 | 3-6 | check_report |
| build/selfcheck | 2-4 | 最终产物 |

接近 850 秒或 58 次请求时：

1. 立即执行 `build`；
2. 写合法 `result.json`；
3. `status` 标 `partial`；
4. 确保 `pending_human` / `limitations` 说明未完成项；
5. 退出码 0。

不为了穷尽修正耗尽预算；先落盘，再增强。

---

## 13. 包结构与复用

提交包应保持精简：

```text
SKILL.md
scripts/main.py
scripts/core.py
references/guide.md
references/writing-rules.md
references/schema.md
SELFTEST.md
environment/resources.yaml
```

- `scripts/core.py`：纯标准库，完成文件扫描、文本层提取、CSV/TSV/JSON/TXT/MD 解析、draft/schema 校验、result.json 拼装；
- `scripts/main.py`：提供 `run` / `init` / `check` / `build` / `selfcheck` 命令；
- `references/guide.md`：draft.json 形状、Agent 工作流、常见错误修复；
- `references/writing-rules.md`：Results/Discussion 语言规则和因果梯度；
- `SELFTEST.md`：自检清单与预期输出；
- `environment/resources.yaml`：依赖声明，默认空或仅标准库。

资源限制：

- 纯 Python 标准库；
- 离线运行，无网络依赖；
- Python >= 3.8；
- 不超过 50 个 UTF-8 文本文件；
- 单文件不超过 500KB，总提交不超过 2MB；
- 不创建 symlink。

---

## 14. 最小调用示例

示例输入 `/input/case.json`：

```json
{
  "case_id": "EXAMPLE-NOT-A-TEST-CASE",
  "task_instruction": "示例：写一段 Results，保留来源。",
  "output_contract": {
    "case_id": "原样保留",
    "deliverable": "可编辑的目标文稿/结构化产物",
    "preserved_facts": "数字、条件、术语和来源不可凭空改变",
    "evidence_map": "关键论断到来源定位的映射",
    "change_log": "修改动作、原因、人工确认项和未解决问题"
  },
  "source": {
    "title": "Synthetic example",
    "doi": null
  }
}
```

示意调用：

```bash
python3 /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出 `result.json` 上方已给出。此为示例，不冒充正式案例结果。

---

## 15. 最终交付自检

提交前逐项确认：

1. `/app/output/result.json` 合法 JSON；
2. 原始 `output_contract` 字段顶层与嵌套均存在；
3. `case_id` 保留；
4. `manuscript.md` 可编辑、结构正确；
5. 每个关键数字有 `[S#]` 或 locator 回溯；
6. 证据冲突、缺口、不确定性写入 `pending_human`；
7. Results 无因果语言；
8. Discussion 有证据对照与局限；
9. 所有异常均无误退出，退出码 0；
10. 没有伪造评分、白板、金标准或未读取材料的结论。