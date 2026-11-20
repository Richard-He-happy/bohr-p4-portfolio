---
name: academic-translation-bilingual
description: "学术翻译与双语写作 Skill：Agent 先真实阅读材料并写 draft.json，脚本负责材料盘点、术语/数字/引用/句段对齐核验、成稿拼装和 result.json 双回显；无 draft 时确定性抽取原文 work draft 并诚实降级。支持中英双向、双语对照、图表题注、脚注、参考文献；纯标准库、离线、Python3.8+。"
version: 2.0.0
---

# 学术翻译与双语写作 Skill：可核验、可降级、Agent 主答

本 Skill 的目标不是输出一个“看起来像翻译”的空壳，而是在有限预算内交付：
- 真正覆盖原文的翻译/双语稿件；
- 全篇术语、数字、单位、引用、否定与限定条件的保留记录；
- 每段可回溯原文的证据映射；
- 合法、诚实、可复核的 `result.json`。

最高优先级：**先落盘完整 partial 结果，再逐步提高完成度；任何异常都要 exit 0。**

---

## 0. 安装路径与预算

- Skill 根目录记为 `$SKILL`，通常为 `/skills/weekly-skill`。
- 输入固定为 `/input/case.json` 与 `/input/task.md`，材料在 `/input` 下。
- 工作目录 `/app/work`，最终交付目录 `/app/output`。
- 预算：64 次模型请求 / 900 秒。始终以“先运行脚本落盘，再用 Agent 增量改进”的方式执行。
- 若接近 60 次请求或 780 秒，立即执行 `build` 收尾，不要继续逐段优化。

---

## 1. 单命令入口与子命令

对每个案例，Agent 的第一动作应是运行：

    python3 "$SKILL/scripts/main.py" run --input /input --output /app/output --work /app/work

`run` 是完整流程入口，等价于：

1. `init`：盘点输入契约、材料、来源编号、候选术语、冲突分组；
2. 检查 `/app/work/draft.json` 是否存在且非空；存在则使用 Agent 草稿，不存在则确定性抽取原文 work draft；
3. `build`：校验/兜底抽取/渲染全部交付产物/写 `result.json`；
4. `selfcheck`：产物与契约自检并写 `self_check.json`。

子命令如下：

    python3 "$SKILL/scripts/main.py" init --input /input --work /app/work --output /app/output
    python3 "$SKILL/scripts/main.py" show --work /app/work --material S1
    python3 "$SKILL/scripts/main.py" show --work /app/work --para S1-P001 --material S1
    python3 "$SKILL/scripts/main.py" check --input /input --work /app/work
    python3 "$SKILL/scripts/main.py" build --input /input --work /app/work --output /app/output
    python3 "$SKILL/scripts/main.py" selfcheck --input /input --work /app/work --output /app/output

脚本使用自身文件路径定位资源，不依赖当前工作目录。所有子命令都必须捕获异常、返回 0，并把错误写入 `result.json.errors` 或 `degradations`。

---

## 2. 目录与产物约定

工作目录：

    /app/work/index.json
    /app/work/input_contract.json
    /app/work/conflicts.json
    /app/work/draft.json
    /app/work/run.log

最终输出：

    /app/output/result.json
    /app/output/deliverable.md
    /app/output/evidence_driven_draft.md
    /app/output/translation.md
    /app/output/glossary.csv
    /app/output/alignment.csv
    /app/output/preserved_facts.json
    /app/output/evidence_map.json
    /app/output/change_log.json
    /app/output/conflicts.json
    /app/output/self_check.json
    /app/output/run.log
    /app/output/version_history.md
    /app/output/SELFTEST.md

`deliverable.md` 是干净可编辑成稿；`evidence_driven_draft.md` 是带 `[S#]` 来源与 locator 的证据草稿。两者内容不能是同一文本复制。

---

## 3. 执行流程

### 第 1 步：init——盘点与来源编号

Agent 运行：

    python3 "$SKILL/scripts/main.py" init --input /input --work /app/work --output /app/output

`init` 必须完成：

- 递归发现 `/input` 下 `case.json`、`task.md` 及全部材料；
- 用多编码读取文件，防 BOM、防坏编码；
- 解析任务说明字段：`task_instruction|brief|request|workorder|prompt`；
- 原样保存 `output_contract` 的全部键，写入 `/app/work/input_contract.json`；
- 分配来源编号：`S1`, `S2`, `S3` ...；
- 为每段建立 `para_id`：`S1-P001`, `S1-P002` ...；
- 图、表、公式、脚注、参考文献分别用 `S1-FIG1`, `S1-TAB1`, `S1-REF1`, `S1-FN1`, `S1-FORMULA1` 等编号；
- 记录 locator，优先用 `S1#L12-L15` 行号；无行号则用 `S1#para3` 或 `S1#page2`；
- 识别并记录候选术语、缩写、数字、单位、引用标记；
- 对材料内同一数字/术语/引用出现冲突时写入 `/app/work/conflicts.json`，不静默裁决；
- 立即写出一个合法 partial 的 `/app/output/result.json`。

如果 `case.json` 不存在或坏 JSON，`init` 应从 `task.md` 或其它材料继续。输出契约缺失字段时填 `null`，状态标 `partial` 或 `input_error`。

### 第 2 步：真实阅读材料

Agent 不能只依赖文件名或领域标签。必须真实读取材料文本：

    python3 "$SKILL/scripts/main.py" show --work /app/work --material S1

或直接用文件读取工具打开实际材料。阅读重点：

- 逐段确认原文段落、标题、图表题注、脚注、参考文献条目是否完整；
- 核查 `index.json` 中的 `text` 是否为原文逐字内容；
- 公式、上下标、希腊字母、基因名、材料专名必须保留原文形式；
- PDF 仅有扫描图、文本层为空或乱码时，不得猜测正文，应在 `quality` 标 `low/unreadable`，并写入 `degradations` 与 `pending_human`。

### 第 3 步：Agent 写 draft.json

Agent 亲手在 `/app/work/draft.json` 写逐段译文工作稿。每段一条：

    {
      "case_id": "输入中的 case_id",
      "language_direction": "en->zh 或 zh->en；不确定时写 unknown",
      "paragraphs": [
        {
          "para_id": "S1-P001",
          "locator": "S1#L12-L15",
          "source_quote": "逐字原文片段，必须能在原文中找到",
          "translation": "目标语言译文；未译则 null",
          "auto_extracted": false,
          "terms": [{"term": "adenocarcinoma", "translation": "腺癌", "locator": "S1#L12", "note": ""}],
          "numbers": ["n=42", "95% CI"],
          "citations": ["[12]", "Smith et al."],
          "semantic_flags": ["negation_kept", "hedge_kept"],
          "note": ""
        }
      ],
      "glossary": [],
      "changes": [],
      "pending_human": []
    }

写作规则：

- 每段 `source_quote` 必须是原文逐字片段，`check` 会验证其是否为原文子串；
- `translation` 必须是 Agent 亲自撰写的译文，不能把脚本骨架当成品；
- 全文同一术语只锁定一个译名；同一词在语境中可能多义时，按本材料学科语境决定，并在 `glossary.note` 写明依据；
- 图注、表题、脚注、参考文献条目同样逐段翻译；编号、作者名、期刊名、卷页年保留原格式；
- 数字、单位、量级、范围、年份、统计口径不得四舍五入、单位错配或顺手取整；
- 否定范围、因果强度、模糊限制语、增译/省译必须保持原意；
- 修改或锁定的术语、数字格式、引用格式变化写进 `changes`；
- 每写 3-5 段保存一次 `/app/work/draft.json`，不要等到最后才落盘。

如果段落不可读或无法确定数字/单位/引用，不得删除该段。仍给尽量规范的译文，同时写入 `note` 与 `pending_human`。

### 第 4 步：check——确定性校验

Agent 写完草稿后运行：

    python3 "$SKILL/scripts/main.py" check --input /input --work /app/work

`check` 至少校验：

- `draft.json` 结构合法；
- 每个 `para_id` 都能对应 `/app/work/index.json`；
- 每个 `source_quote` 是原文逐字子串；
- 每个段落都有 `locator`；
- `glossary.csv` 中术语全篇一致，同一术语不出现多个无说明译法；
- `preserved_facts.json` 中数字/引用在译文中存在，缺失或人为改写要列 `present_in_target=false`；
- `alignment.csv` 与索引段落一一对应；
- 输出契约字段与磁盘产物对应。

若 `check` 报告 `verdict: fail`，Agent 必须按报告逐条修稿，再运行 `check`，直到 `pass` 或确定无法通过的部分进入 `pending_human`。

### 第 5 步：build——渲染最终产物

    python3 "$SKILL/scripts/main.py" build --input /input --work /app/work --output /app/output

`build` 必须：

- 使用 `/app/work/draft.json` 渲染全部交付物；
- 无论 `check` 是否完全通过，都要无条件 finalize `/app/output/result.json`；
- 写 `deliverable.md`、`evidence_driven_draft.md`、`translation.md`、`glossary.csv`、`alignment.csv`、`preserved_facts.json`、`evidence_map.json`、`change_log.json`、`self_check.json` 等产物；
- 如果某个可编辑 Office/图形格式被契约明确要求且当前环境无法生成，不得伪造；应交付 Markdown/CSV 可编辑替代，并在 `result.json` 和 `self_check.json` 标注 `format_preview_unavailable`；
- 全部异常都写 `errors`/`degradations`，不中断。

### 第 6 步：selfcheck——自检与收尾

    python3 "$SKILL/scripts/main.py" selfcheck --input /input --work /app/work --output /app/output

自检至少包含：

- `result.json` 是合法 JSON；
- `case_id` 与输入一致，且 `output_contract` 嵌套字段齐全；
- `output_contract` 的每个原始字段在产物中都有对应文件路径或明确 `null`；
- `index.json` 中全部段落都出现在 `alignment.csv`；
- 没有空译文槽未标记，或空槽已显式进入 `pending_human`；
- `source_quote` 全部能在原文中定位；
- 术语表、数字核对、引用核对无未说明失败；
- `run.log` 与 `version_history.md` 存在。

自检结果写 `/app/output/self_check.json`。

---

## 4. 无 draft 时的确定性兜底

当 `/app/work/draft.json` 不存在、为空或严重不完整时，`build` 必须使用 `init` 台账确定性生成实质工作稿，而不要只输出空模板。

确定性兜底应：

- 为每个索引段落生成 `para_id`、`source_quote` 和 `locator`；
- `source_quote` 是原文逐字片段；
- `translation` 保持 `null` 或 `"[待译 / PENDING TRANSLATION]"`；
- `auto_extracted` 标 `true`；
- 在 `result.json.degradations` 中记录 `AUTO_EXTRACT`，说明“无 Agent 草稿，已确定性抽取原文，目标译文待补”；
- 输出 `deliverable.md` 仍为可编辑的原文-待译双语骨架；
- 状态标 `partial`。

不得在无依据的情况下伪造译文、数字、引用、术语或结论。

---

## 5. result.json 双回显契约

`build` 写 `result.json` 时必须满足：

- 原始 `output_contract` 的每个字段，键名原样保留；
- `case_id` 原样保留；
- 每个契约字段在 `result.json` 顶层和嵌套 `output_contract` 中同时出现一次；
- 嵌套结构例如：

    {
      "case_id": "原输入 case_id",
      "status": "ok | partial | insufficient_evidence | input_error",
      "deliverable": "/app/output/deliverable.md",
      "preserved_facts": "/app/output/preserved_facts.json",
      "evidence_map": "/app/output/evidence_map.json",
      "change_log": "/app/output/change_log.json",
      "sources": [
        {"source_id": "S1", "path": "/input/material1.pdf", "quality": "ok"}
      ],
      "uncertainty": [],
      "pending_human": [],
      "errors": [],
      "degradations": [],
      "metrics": {},
      "runtime": {},
      "output_contract": {
        "case_id": "原输入 case_id",
        "deliverable": "/app/output/deliverable.md",
        "preserved_facts": "/app/output/preserved_facts.json",
        "evidence_map": "/app/output/evidence_map.json",
        "change_log": "/app/output/change_log.json"
      }
    }

如果原输入没有 `output_contract`，则创建一个包含 `case_id` 和默认可用字段的嵌套对象，并标 `output_contract_missing`。缺失字段填 `null`，不得静默删除。

`status` 取值规则：

- 全部段落已翻译、校验通过、契约字段齐全：`ok`；
- 有部分缺口、未翻译槽、低质量文本或格式预览缺失：`partial`；
- 无任何可读材料、无法完成任务：`insufficient_evidence`；
- 输入 JSON 损坏、契约缺失严重且无法恢复：`input_error`。

---

## 6. 材料解析与事实边界

- 递归读 `/input`，使用多编码尝试：`utf-8-sig`, `utf-8`, `gb18030`, `big5`, `latin-1` 等；
- PDF：实际读取文本层；不把扫描 PDF 当作已解析答案；无文本层时记录 `low/unreadable`；
- DOCX：从 `word/document.xml` 抽取文本；
- HTML/Markdown/TXT/TeX/CSV/JSON：直接解析；
- 图像内文字、压缩包内非文本：只登记文件和 note，写入 `pending_human`，不猜测内容；
- 实际输入文件和原论文是事实依据，不依据错误的领域标签补造数据。

材料缺失、冲突、无法判断的情况，分别写入：

- `errors`：机器/脚本/解析错误；
- `degradations`：可降级但影响质量的情况；
- `pending_human`：需要人工确认的科学或语义问题；
- `conflicts.json`：相同数字、术语、引用在材料内不一致。

---

## 7. 隐藏案例鲁棒性

| 情况 | 行为 |
|---|---|
| `case.json` 缺失或坏 JSON | 从 `task.md`/其它材料恢复；契约缺字段填 `null`；状态 `partial` 或 `input_error` |
| 空输入 | 不造内容；空 `sources`；写错误说明；`insufficient_evidence` |
| PDF 无文本层/乱码 | 保留可取文本；标 `low/unreadable`；不猜正文 |
| 材料为图片、PPT、压缩包等 | 只登记文件与 note；请求人工读取 |
| 超长材料 | 使用来源编号 + 段落编号分块；不截断任意段落；先保完整覆盖，再逐步提高翻译比例 |
| 公式、表格、脚注、参考文献 | 原文形式保留；图表题注逐条翻译；编号原位保留 |
| 术语表冲突 | 优先使用输入给定的锁定术语；无锁定时按语境选择并在 `note` 写明；冲突进入 `pending_human` |
| 语向不支持/不明确 | 依据材料语言与任务说明判断；仍不确定则标 `unknown`，不擅自决定 |
| 单个材料解析失败 | 只降级该文件，其余继续处理 |
| Office/图形预览无法生成 | 交付 Markdown/CSV 可编辑替代，标注 `format_preview_unavailable` |
| 超时/预算耗尽 | 立即运行 `build` 收尾，保留已有草稿并诚实标注未完成部分 |

任何情况下退出码为 0，`result.json` 必须存在且为合法 JSON。

---

## 8. 预算策略

| 阶段 | 建议请求数 | 说明 |
|---|---|---|
| `run` 基线落盘 | 1-2 | 先调用一次 `run`，立即得到 partial 结果 |
| 阅读材料与核对 index | 5-10 | 分批读实际材料，优先读摘要、图表题注、参考文献、含有数字与术语的段落 |
| 写 draft.json | 20-30 | 每 3-5 段保存一次，批量写，不逐段重复调用工具 |
| `check` 与修稿 | 3-6 | 依靠脚本确定性校验 |
| `build` 与 selfcheck | 2-5 | 最后收尾 |
| 预留异常 | 3-5 | 材料缺失、格式异常、字段补填 |

原则：先保完整覆盖，再保术语统一，再保风格优化。没有剩余请求时，优先保证 `result.json` 合法和 `draft.json` 落盘。

---

## 9. 禁止行为与常见扣分项

- 不得手改 `result.json`、`preserved_facts.json`、`evidence_map.json` 等结构化产物结构；修正需通过脚本重算。
- 不得把脚本生成的空模板、索引或骨架当正式译文交付。
- 不得根据文件名、领域标签或案例标签猜测原文内容。
- 不得伪造数字、单位、引用、公式、结论、材料缺失状态。
- 不得伪造基准分数、白板、隐藏案例答案或自造 `golden_standard` 类评分证据。
- 不得静默跳过缺失字段；必须显式填 `null` 或写入 `pending_human`。
- 不得依赖网络、第三方库或未声明的手工操作。
- 不得输出非零退出码；任何失败都要写成合法 partial `result.json`。
- 不得删除原始 `output_contract` 中的未知键。
- 不得让 `deliverable.md` 与 `evidence_driven_draft.md` 变成同一文本复制。

---

## 10. rubric 对应证据

| rubric 维度 | 主要自证 |
|---|---|
| 实际效果：任务完成度 15 | `deliverable.md`、`alignment.csv` 完整覆盖索引段落；`result.json.status` 诚实 |
| 实际效果：结果正确性 15 | `preserved_facts.json` 中数字/术语/引用保留一致；`check` 的 `source_quote` 逐字验证 |
| 实际效果：结果完整性 5 | `index.json` 全部段落/图表/参考文献出现在对齐表与产物中 |
| 实际效果：结果可核验性 5 | `evidence_map.json`、`change_log.json`、`glossary.csv` 均可回溯到 locator 与原文 |
| 使用增益：质量增益 15 | `self_check.json` 机械通过项；术语锁定记录；数字/引用核对记录 |
| 使用增益：效率增益 5 | `run.log` 阶段耗时；CSV/JSON 可复用资产 |
| 使用增益：增益可验证性 5 | `self_check.json` 由脚本真实子进程产生，不是文字自述；`metrics` 给出覆盖/一致/可溯数 |
| 创新增益：新增能力 5 | 双语对齐、事实保留、术语锁定、冲突暴露等独立资产 |
| 创新增益：方法改进 5 | `references/quality_rules.md`、`references/verifiability.md`、`scripts/kit.py` 的确定性校验路径 |
| 创新增益：创新证据 5 | `evidence_driven_draft.md` 的 `[S#]` 与 locator；`preserved_facts.json` 的保留状态 |
| 可靠体验：调用与易用性 3 | 单命令 `run` 入口；SKILL.md 分级命令 |
| 可靠体验：运行稳定性 4 | 重复可运行；退出码 0；`version_history.md` 记录产物指纹 |
| 可靠体验：异常处理 3 | `degradations`、`errors`、`pending_human` 显式记录 |
| 生态贡献：文档完整性 3 | SKILL.md、SELFTEST.md、references 完整 |
| 生态贡献：资源可复用性 4 | `scripts/main.py`、`references/guide.md`、模板可复用 |
| 生态贡献：分享推广价值 3 | 工作流可迁移到其它学术翻译/双语写作任务 |

---

## 11. Agent 最低交付清单

最后收尾前必须确认：

1. `/app/output/result.json` 合法且 `case_id` 正确；
2. 原始 `output_contract` 字段全部在顶层与嵌套 `output_contract` 中保留；
3. `deliverable.md` 非空且不是脚本骨架；
4. `alignment.csv` 覆盖所有索引段落；
5. `source_quote` 全部经过 `check`，无凭空写入；
6. `glossary.csv` 无未说明的术语冲突；
7. `preserved_facts.json` 无未标记的数字/引用缺失；
8. `pending_human` 与 `degradations` 诚实记录；
9. 全部脚本返回 0；
10. `run.log` 与 `self_check.json` 存在。

以上任何一条不满足，都应在 `result.json` 中如实标 `partial` 并列出原因，而不是伪装成功。