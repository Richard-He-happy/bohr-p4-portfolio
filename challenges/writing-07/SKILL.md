---
name: intro-related-work-writer
description: 为学术论文起草或改写“引言 + 相关工作 + 研究空白 + 贡献”四段式正文，把每条引用绑定到材料原文的逐字证据。当用户要求“写引言”“整理相关工作”“补引用”“核对贡献”“推导研究空白”“检查引用元数据/格式”“修改引言”时使用。强调真实解析材料、Agent 亲自审阅撰写、确定性兜底与全套可核验交付物。输出 manuscript.md、evidence_driven_draft.md、evidence_map、preserved_facts、change_log、sources_index、result.json。
version: 3.0.0
---

# 引言与相关工作写作 Skill

## 1. 用途与触发边界

本 Skill 用于根据给定科研材料完成可进入论文的“引言与相关工作”写作、改写、引用绑定、空白推导与贡献对齐。它解决四类问题：立得住、分得清、说得实、对得上。

| 段落 | 必须完成 | 证据要求 |
|-|-|-|
| 研究背景 | 从领域任务、技术约束、现有能力边界指向具体未解问题 | 每条核心陈述挂 `[S#]`，作者判断标 `[own]` |
| 相关工作 | 按问题/方法/技术路线分组，在同一维度比较结论、适用条件、局限 | 每组至少 1 条逐字 quote，并给 locator |
| 研究空白 | 由已引文献的共同限制、未覆盖场景、冲突结论推导出来，并落到本文动作 | 每条 gap 必须列出支撑引用 ID 与原文依据 |
| 贡献 | 贡献条目可核对，对应方法、图表、实验或结果 locator | 每条贡献至少有 1 个 locator；找不到则标 `unaligned` |

不做什么：不新增材料外文献、DOI、数值、图表、统计量；不替作者下“首次/最优”等无材料支撑断言；不做投稿系统级排版终稿。

## 2. 最高优先级：脚本是基线，Agent 负责判断与改进

结构化 JSON 的结构字段由脚本生成；Agent 不得手工篡改 JSON 结构。Agent 的职责是真实阅读材料、核验证据、写 `draft.json`、改写正文、补全缺口、诚实标注。

必须遵守：

1. 不得删除或清空任务契约字段；缺值用 `null` / `[]`，缺失原因写入 `pending_human`。
2. 不得手改 `evidence_map.json`、`preserved_facts.json`、`result.json` 的结构键；若脚本输出有误，调用脚本函数或重跑流程，不得文本覆盖。
3. Agent 可以在 `${WORK}/draft.json` 写判断，在 `agent_review.json` 写逐条核验结论，在 `manuscript.md` / `evidence_driven_draft.md` 写正文改写。
4. 不得伪造基准分、金标准、白板对比成绩；只依据脚本实际核验输出 `verification.json` 或 `scripts/verify.py` 的结果。
5. 任何异常也必须退出码 0；先生成诚实 partial，再增量增强。

## 3. 运行契约

- 输入：`/input/case.json`，`/input/task.md`，以及 `/input/**` 下的材料文件（`.md/.txt/.json/.csv/.docx/.pdf/.xlsx`）。
- 工作目录：`/app/work`。
- 最终产物目录：`/app/output/`。
- 依赖：Python 3.8+，仅标准库，离线运行，不依赖 CWD；资源路径用 `Path(__file__).resolve().parent` 定位。
- 退出码：恒为 0。
- 预算：64 次模型请求 / 900 秒 / 单响应 16384 tokens（含推理）。脚本运行本身不计模型请求，但 Agent 阅读、写作、核验、改稿计入模型请求。

## 4. 单命令全流程入口

优先执行：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部完成：

1. `init`：盘点材料、分配 `source_id`、抽取候选文本、识别引用/数字/贡献线索、做初步冲突分组，写 `${WORK}/ledger.json` 与 `${WORK}/sources_index.json`。
2. `build`：校验 `${WORK}/draft.json`；若无 draft，则用 init 台账确定性抽取生成实质工作稿；渲染全部产物；生成合法 `result.json`。
3. `selfcheck`：调用 `scripts/verify.py` 检查结果完整性、quote 命中率、契约字段、产物文件存在性，并写 `${WORK}/verification.json`。

若该命令语法在当前包版本不可用，回退为：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

并把工作目录视为 `/app/work`。任何路径或参数错误都不得导致非 0 退出；记入 `errors`，并继续尝试生成最小合法结果。

## 5. 目录与产物

`/app/output/` 下交付：

| 文件 | 内容 |
|-|-|
| `result.json` | 双回显结果：顶层字段 + `output_contract` 原样字段 |
| `manuscript.md` | 干净四段式主稿，含 `## References` |
| `evidence_driven_draft.md` | 带 `[S#]`、`[待核实]`、`[conflict]` 标记的核查稿；不得与 `manuscript.md` 简单复制 |
| `related_work_matrix.md` | 分组 × 比较维度矩阵：问题设定/方法路线/数据与评价/结论/局限/引用 ID |
| `evidence_map.json` | 论断 → `source_id` + `locator` + 逐字 quote + `quote_verified` |
| `preserved_facts.json` | 数字/单位/引用标记/术语逐字保留表 |
| `change_log.json` | 原始表达 → 改写表达 + 修改理由 + locator |
| `sources_index.json` | 可独立复核的抽取文本索引；`source_id` → 路径/字符偏移/段落定位 |
| `agent_review.json` | Agent 对关键 claim、引用、贡献、gap 的核验补充 |
| `verification.json` | 可选：`scripts/verify.py` 实际输出的核验结果 |

若任务显式要求可编辑 Office / 幻灯片 / 图形产物，则必须同时输出真实渲染 PDF/PNG 预览；无法渲染时写入 `pending_human`。本 Skill 默认产物为 Markdown 与 JSON，不生成二进制 Office 格式。

## 6. 输入发现与材料盘点

1. 优先读 `/input/case.json`；不存在则递归查找 `case*.json`、`task.md`。
2. `case_id`、`output_contract` 必须原样透传；再按语义识别任务说明、材料路径、格式约束、语言要求。
3. 递归扫描 `/input`，按扩展名和魔数识别文件：`%PDF` 为 PDF，`PK\x03\x04` 为 docx/xlsx。不得只按文件名或领域标签猜内容。
4. 材料缺失、解析失败、文献为空、无法定位原文等情况，必须进入 `pending_human` 或 `errors`；不编造。
5. 语言选择：优先跟随 `task_instruction` 语言；未指定时，材料 CJK 字符占比 > 15% 则输出中文，否则输出英文。结果记入 `runtime.language`。

## 7. Agent-first 双路径

### 7.1 Agent 路径（推荐，质量更高）

如果预算允许，先只清点材料：

```bash
python3 -B scripts/main.py init --input /input --work /app/work
```

然后 Agent 执行：

1. 阅读 `${WORK}/ledger.json` 与 `/input` 原文。
2. 逐条核验候选 quote、数字、引用元数据、贡献线索。
3. 写 `${WORK}/draft.json`。形状至少包含：

```json
{
  "case_id": "来自输入",
  "sections": {
    "background": [
      {"claim": "陈述", "source_ids": ["S1"], "locators": ["file#para"], "quote": "逐字原文", "confidence": "high|medium|low", "flags": ["own|conflict|missing"]}
    ],
    "related_work": [
      {"group": "分组名", "dimensions": {"problem": "", "method": "", "evaluation": ""}, "works": [
        {"cite_key": "K1", "claim": "转述", "source_id": "S2", "locator": "file#para", "quote": "逐字原文", "comparison": "局限或取舍"}
      ]}
    ],
    "gap": [
      {"gap": "空白描述", "supports": ["K1", "K3"], "basis_quote": "原文缺口句", "locator": "file#para", "how_filled": "本文如何填补"}
    ],
    "contributions": [
      {"contribution": "贡献条目", "locator": "file#table1", "aligned": true, "claim_scope": "不夸大范围"}
    ]
  },
  "citations": [
    {"key": "K1", "authors": "Li et al.", "year": 2021, "title": "标题", "venue": "来源", "source_id": "S9", "locator": "file#para", "metadata_status": "complete|partial|inferred"}
  ],
  "uncertainties": [],
  "pending_human": []
}
```

无法命中的 quote 不要编；写 `quote_verified=false`，并在正文标 `[待核实]`。

然后运行：

```bash
python3 -B scripts/main.py check --input /input --work /app/work --output /app/output
```

或直接运行 `build`。`check` 只核验并给出问题；`build` 渲染并 finalize。

### 7.2 无 draft 时确定性兜底

如果 `/app/work/draft.json` 不存在，`build` 必须确定性抽取生成工作稿。该兜底路径：

- 从 init 台账候选抽取逐字 quote；
- 每个关键数字、引用、论断绑定 `[S#]` 与 `文件#行号/段落号` locator；
- 按 route 关键词和文献元数据做分组；
- 记录 `AUTO_EXTRACT` 到 `gaps` / `degradations`，明确“该稿为脚本确定性抽取，Agent 未逐条改写”；
- 缺失、冲突、无法定位的项进入 `pending_human`；
- 产出与 Agent 路径完全相同的产物集合与同一份 `result.json` 契约。

两条路径都必须保证产物齐全、可复核、诚实。

## 8. build 与 result.json 要求

`build` 必须：

1. 校验 draft 中的引用、locator、quote 是否能在 `sources_index.json` 命中。
2. 渲染 `manuscript.md`、`evidence_driven_draft.md`、`related_work_matrix.md`。
3. 写 `evidence_map.json`、`preserved_facts.json`、`change_log.json`、`sources_index.json`。
4. finalize `result.json`。

`result.json` 必备：

- 顶层：`case_id`、`status`、`deliverables`、`sections_present`、`citations`、`evidence_map`、`preserved_facts`、`groups`、`gap_derivation`、`contribution_alignment`、`coverage`、`workorder_receipts`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`gain_evidence`
- `output_contract`：原样保留输入中的全部字段；缺值写 `null` / `[]`
- 双回显：输入 `output_contract` 中的每个字段，同时出现在 `result.json` 顶层与 `output_contract` 内；`case_id` 顶层与 `output_contract.case_id` 同时存在

`status` 取值：

| 状态 | 条件 |
|-|-|
| `ok` | 四段齐全、关键引用可核验、契约完整、quote_verified 比例 ≥ 0.8 |
| `partial` | 已交付大量结果，但存在缺口、待核实项、解析降级或时间压力 |
| `insufficient_evidence` | 材料显著不足：无参考文献、空材料、主要文献缺失；仍给四段骨架 |
| `input_error` | 输入不可读、case 坏 JSON、/input 不存在；仍写合法 result.json |

## 9. 写作质量规则

### 9.1 研究背景

- 避免“近年来受到广泛关注”式空话。
- 从材料中的具体任务、约束、现有方法边界出发。
- 每个背景陈述尽量挂 `[S#]`；无法挂的标 `[own]`。

### 9.2 相关工作

- 必须分组：按问题设定、方法路线、数据与评价方式或技术路线。
- 不做逐篇摘要拼接；要比较结论、适用条件、局限。
- 每篇被引工作至少 1 条逐字 quote。
- 没有 abstract 时只做 title/venue 层面转述，并标 `metadata_status=partial`。

### 9.3 研究空白

- 空白必须由已引文献的缺口推出：共同限制、未覆盖场景、相互冲突结论。
- 每条 gap 有 `supports`（≥1 已引文献 ID）和 `basis_quote`。
- 若无法从材料推出，写“材料不足以推出空白”并进 `pending_human`，不得硬编。

### 9.4 贡献表述

- 每条贡献对应方法、图表、实验或结果的 locator。
- 找不到依据的标 `unaligned`，进 `pending_human`。
- 不夸大适用范围；材料没写“最优/首次/通用”就不写。

### 9.5 引用覆盖与元数据

- 覆盖关键工作、代表性工作、近期进展。
- References 每条有 authors/year/title；缺失时标 `incomplete`。
- 引用元数据必须来自材料；不得补造 DOI、venue、年份。
- 目标期刊格式未知时默认 author-year 编号格式，并在 `uncertainty` 说明。

## 10. 证据与定位规范

- quote 必须能在 `sources_index.json` 对应 `source_id` 原文中逐字找到，仅允许空白归一化。
- locator 与源类型绑定：文本 `L<起>-<止>`；docx `para<n>`；pdf `c<起>-<止>`；json `$.a.b[0]`；csv `row<n>`。
- 同一论断多来源时列出多条 evidence，不合并 quote。
- 无法定位的写 `quote_verified=false`，正文标 `[待核实]`，并进 `pending_human`。
- 数字、单位、引用标记、术语进入 `preserved_facts.json` 并逐字保留。

## 11. 隐藏案例鲁棒性与降级

| 情况 | 处置 | 记录字段 |
|-|-|-|
| `/input` 不存在或空 | 写默认骨架，`status=input_error` 或 `insufficient_evidence` | `status`, `errors`, `pending_human` |
| `case.json` 坏 JSON | 记错，尝试同目录其他 JSON，继续 | `errors` |
| PDF 抽取乱码/过短 | 标 `pdf_text_heuristic`，粗粒度引用，不引具体数字 | `degradations`, `uncertainty` |
| docx/xlsx 损坏 | 跳过该文件，其余继续 | `errors` |
| 文献无 abstract | 仅 title/venue 归类，转述降级 | `citations[].metadata_status` |
| quote 校验失败 | 正文标 `[待核实]`，进 `pending_human` | `evidence_map`, `pending_human` |
| 无 output_contract | 使用内置默认契约，仍输出全字段 | `runtime.contract_source` |
| 时间超过 780 秒 | 立即 finalize 当前产物并标 `partial` | `runtime`, `errors` |
| 空输入材料 | `status=insufficient_evidence`，生成四段骨架与缺口清单 | `status`, `pending_human` |
| 材料间数字/年份冲突 | 两条都保留，进 `uncertainty`，正文用首次出现者标 `[conflict]` | `uncertainty` |
| 期刊格式未知 | 默认 author-year，写清需人工调整 | `uncertainty` |
| 语言切换 | 跟随任务语言；未指定按 CJK 占比判定 | `runtime.language` |
| 文献库为空 | 仍交付四段骨架与空白清单 | `status`, `pending_human` |
| 需要人工确认项 | 每条说明缺口与建议动作 | `pending_human` |

任何情况下都不得因异常退出非 0；先写 partial `result.json`，再增量覆盖。

## 12. 预算策略

推荐预算分配：

| 阶段 | 模型请求 | 说明 |
|-|-|-|
| 运行单命令基线 | 1 | 脚本内部完成 init/build/selfcheck |
| 阅读 ledger 与原文 | 1-3 | 只读关键材料，不逐字全量复述 |
| 核验关键引用/数字 | 6-12 | 只核验写入稿件的关键 claim |
| Agent 改写 draft | 4-8 | 四段改写与缺口补全 |
| selfcheck 与修复 | 2-5 | 使用 `scripts/verify.py` |
| finalize | 1 | 回填 result.json |

总计控制在 15-30 次请求内，留充足缓冲。接近 780 秒或 60 次请求时立即 finalize。先保证 `manuscript.md` 四段完整、`evidence_map` 关键引用可核验、`result.json` 契约字段齐全；相关矩阵可粗化。

## 13. 增益证据

`result.json` 的 `gain_evidence` 应诚实记录：

- `baseline_path`：确定性兜底生成的结果文件。
- `agent_changed_files`：Agent 实际改写/补充的文件列表。
- `verified_claims` / `rejected_claims`：来自 `agent_review.json` 的条数。
- `efficiency_records`：如“单命令基线已生成 N 条可复核引用，Agent 只核验关键条”。
- `no_claimed_score`：明确写“本文件不构造白板分数；平台对比结果由评分方生成”。

不得自造 benchmark 分数、golden_standard 或加权自评分。

## 14. rubric 对照自检

提交前逐项检查：

1. 四段齐全且彼此承接；`sections_present` 全 true 或如实说明缺失。
2. 每条他人工作转述有原文出处；引用元数据真实。
3. 研究空白由已引文献缺口推出；每条 gap 有 supports 与 basis_quote。
4. 每条贡献有 locator 或 `aligned=true`；未对齐的标 `unaligned`。
5. 每条引用能回到 `sources_index.json`。
6. `result.json` 顶层与 `output_contract` 双回显；所有契约键存在。
7. quote_verified 比例 ≥ 0.8 才可 `status=ok`；否则降级。
8. 无材料外数字、文献、DOI。
9. `errors`、`degradations`、`uncertainty` 非空时已说明。
10. 主稿与 evidence_driven_draft 不同；后者带证据标记。
11. 退出码 0；无 `__pycache__`，无临时文件遗漏至最终产物。
12. 若要求 Office/幻灯片/图形产物，已附真实 PDF/PNG 预览。
13. 示例已标注“示例，非正式案例结果”。

## 15. 最小调用示例

示例输入 `input/case.json`：

```json
{"case_id": "demo-001",
 "task_instruction": "为本文写引言与相关工作，author-year 格式",
 "output_contract": {"manuscript_md": "path", "evidence_map": [], "status": ""},
 "material": {"manuscript": "本文提出一种…（材料原文）",
   "references": [{"key": "K1", "authors": "Li et al.", "year": 2021,
     "title": "A rule-based scheduler", "venue": "J. Sched.",
     "abstract": "Rule-based schedulers handle static workloads; however they cannot adapt to bursty arrival."}]}}
```

调用：

```bash
python3 -B scripts/main.py run --input input --output out --work work
```

示意输出，`out/`：`result.json`（`status="ok"`，`sections_present` 4×true，`citations[0].metadata_status="complete"`，1 条 `gap_derivation` 由 K1 的 "cannot adapt to bursty arrival" 支撑）、`manuscript.md`、`evidence_driven_draft.md`、`related_work_matrix.md`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`。

## 16. 文件清单与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明：流程、契约、双路径、降级、预算、自检 |
| `scripts/main.py` | 主流程：`run` / `init` / `check` / `build`；确定性兜底与 finalize |
| `scripts/verify.py` | 独立性核验：quote 命中、契约字段、产物存在性 |
| `references/frames.json` | 中英文组稿框架：只提供承接句，事实必须来自材料 |
| `references/writing_playbook.md` | 四段写法、分组维度、空白推导协议、贡献规范、反模式 |
| `references/output_schema.md` | `result.json` 字段表、locator 规范、异常处置 |

维护：路线词表若同时存在于 `scripts/main.py` 与 `references/writing_playbook.md`，改动需同步并升 version。新增学科只需增补路线术语，不改流程。回归验证：替换新案例运行单命令入口，检查 `coverage.quote_verified_rate`、`pending_human` 是否只含真实缺口、`status` 是否诚实。