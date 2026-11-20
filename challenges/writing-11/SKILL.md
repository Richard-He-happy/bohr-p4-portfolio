---
name: academic-translation-bilingual
description: 学术翻译与双语写作 Skill。Agent 先逐段精读原文，再亲手写出逐段译文工作稿（workdraft.json），脚本负责材料抽取、句段对齐校验、术语/数字/引用核对、成稿拼装，并生成可核验资产（golden_standard.json 金标准、diff_report.md 产物对照、version_history.md 版本与回退、run.log 运行日志、self_check.json 自检）；用于论文摘要、正文、图表题注、参考文献的中英互译与双语对照交付，产出双语稿、术语表、逐段对齐表、事实与证据映射、修改记录和 result.json。材料缺失或术语无法确定时明确标注并降级为 partial。
version: 1.5.0
---

# 学术翻译与双语写作（Agent 主答 + 脚本辅助）

> 脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本骨架/模板直接当成品；必须真实解析材料内容并逐段撰写译文、证据映射和修改记录。脚本生成的空模板、索引、兜底骨架不是成品，只能作为起点，Agent 必须逐段实际阅读原文并亲自产出完整译文工作稿。

## 1. 用途与硬边界

把给定科研材料（中文或英文摘要、正文、图表题注、公式段、参考文献）译成目标语言，并交付**可直接进入作者修改流程**的双语稿：逐段对齐、术语全篇统一、数字/单位/引用编号逐字保留、每段可回溯原文。

适用：摘要/正文/题注/脚注/参考文献的中英互译、双语对照改稿、术语表建设、译后一致性核查。

不适用：无原文的创作型写作、需要外部文献补写结论、图像内文字识别（图像只登记为缺口，交人工）。

**硬边界**：不增删事实，不改科学判断，不补材料里没有的数值、文献或结论；拿不准就写进 `pending_human`。不得依据文件名或领域标签猜测/补造材料内容；所有事实、数字、引用、术语必须来自真实解析出的原文文本。

## 2. 运行契约与目录约定

- 输入：`/input/case.json`（含 `task_instruction`、`output_contract` 等，键名不固定）+ `/input/**` 材料；可能另有 `/input/task.md`。
- 工作目录 `/app/work`，产物 `/app/output`，其中必须有 `result.json`。
- 只用 Python 标准库，不联网（Python 3.8+）；路径默认 `/input`、`/app/work`、`/app/output`，也可用 `--input/--work/--output` 覆盖；脚本按自身位置定位，不依赖 CWD。
- 退出码恒为 0；任何异常都写进 `result.json.errors`，不中断。
- 预算：64 次模型请求 / 900 秒。做法是**先落盘再优化**：运行 `init` 写好合法 partial `result.json`，Agent 逐段写草稿时增量保存，接近 780 秒或 60 次模型请求时立刻执行 `build` 收尾。
- 可编辑 Office/幻灯片/图形产物：本包默认交付 `translation.md`、`glossary.csv`、`alignment.csv` 等可直接编辑文本/表格；若契约显式要求 `.docx/.pptx/.xlsx` 或图形格式，必须额外生成真实渲染的 PDF/PNG 预览。若当前环境/脚本不具备相应渲染能力，不得伪造预览，应在 `result.json` 和 `self_check.json` 中诚实标注 `format_preview_unavailable`，交付可编辑 Markdown/CSV 替代并记入 `pending_human`。

## 3. 输入发现与真实解析

1. 递归读 `/input`：`case.json`/`input.json`/`task.json`/`case*.json`，一律按 `utf-8-sig` 起的多编码尝试读取（防 BOM）。
2. 语义识别字段：`task_instruction|brief|request|workorder|prompt` 为任务说明；`output_contract` 为输出契约（**原样回填**）；`organizer_*`、`formal_inputs`、`artifacts`、`materials` 为材料清单；`glossary|locked_terms|terminology` 为给定术语（优先锁定）。
3. 材料按扩展名 + 魔数识别：PDF（`%PDF`，脚本用 zlib 解内容流取文本层）、DOCX（`word/document.xml`）、HTML、Markdown/TXT/TeX/CSV/JSON。扫描件或 CID 编码 PDF 取不到字时，quality 标 `low/unreadable`，写入 `degradations` 与 `pending_human`，**绝不凭标签猜正文**。
4. 材料没给的对象（图表、缺失页、附录）明确列缺口，不构造。材料中的图像、PPT、压缩包等非文本，只登记文件与 note，提示人工读取，不猜内容。

## 4. 本题专属执行流程（按序执行，Agent 主答）

技能根目录记为 `$SKILL`（本文件所在目录）。命令示例：

```bash
python3 "$SKILL/scripts/main.py" init     # 1) 建索引 + 先写 partial result.json
python3 "$SKILL/scripts/main.py" show --para M1-P001 --para M1-P002
python3 "$SKILL/scripts/main.py" show --material M1
python3 "$SKILL/scripts/main.py" show --grep 术语
python3 "$SKILL/scripts/main.py" check    # 3) 校验工作稿
python3 "$SKILL/scripts/main.py" build    # 4) 成稿 + finalize result.json
python3 "$SKILL/scripts/main.py" audit    # 可选：重算可核验资产
```

每次子命令都会向 `/app/work/run.log` 追加一行（阶段、事件、耗时）；`build` 把它整理成交付用 `/app/output/run.log`。

### 第 1 步：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md` 及材料文件。
- **动作**：
  1. 读入 `case.json`，完整解析 JSON，识别任务说明、输出契约、材料清单、给定术语。
  2. 记录 `output_contract` 的全部键名；这些键名必须原样出现在最终 `result.json` 中。
  3. 运行 `python3 "$SKILL/scripts/main.py" init`。
- **输出**：`/app/work/index.json`（每段 `para_id`、`locator`、`kind`、逐字 `text`）、`/app/work/workdraft.template.json`（空译文骨架）、`/app/output/result.json`（合法 partial 壳）以及材料清单和契约字段列表。
- **失败分支**：
  - `case.json` 缺失或坏 JSON：递归找 `case*.json`/`task.md` 继续；契约缺字段填 `null`，状态标 `partial` 或 `input_error`。
  - 输入为空：不造内容，写空 `sources` 与错误说明，状态 `insufficient_evidence`。
  - 任何解析异常不退出，写入 `errors`，继续后续步骤。

### 第 2 步：真实解析材料并核对证据

- **输入**：`/app/work/index.json`、材料文件、`output_contract` 字段。
- **动作**：
  1. 运行 `show --material M1` 或 `show --para M1-P001`，或直接打开材料文件，阅读实际文本。
  2. 逐段确认段落边界、图表题注、脚注、参考文献条目是否被正确抽取。
  3. 核对 `index.json` 中的 `text` 是否为原文逐字内容，而不是摘要或文件名。
  4. 识别公式、上下标、希腊字母、基因/材料专名：必须保存为原文形式，不能为通过脚本校验而改变原文。
- **输出**：已核对段落的列表；对低质量段落记录 `quality=low/unreadable` 与 `degradations`。
- **失败分支**：
  - 材料格式不支持：登记文件名与 note，标为 `pending_human`，不猜测内容。
  - PDF 文本层稀薄：保留可取文本，标 `quality=low`，提示对照页面核对，相关段落可进入 `pending_human`。
  - 单个文件解析失败：只降级该文件，其余照常；写入该文件的 `errors` 和 `degradations`。

### 第 3 步：构建/核对证据并撰写工作稿

这是本 Skill 的核心，不可跳过。

- **输入**：`/app/work/index.json`、`/app/work/workdraft.template.json`、真实材料文本。
- **动作**：
  1. 逐个 `para_id` 阅读原文，**亲手在 `/app/work/workdraft.json` 写逐段译文**：每段一条，`para_id` 照抄索引，`translation` 是你撰写的译文，`source_quote` 取该段一小段逐字原文（必须能在原文中找到）。
  2. 同步写 `glossary`：从原文抽出术语 → 译名 + `locator`（出处）。同一术语全篇只用一个译名；同一英文词在不同学科译法不同时，按本材料的学科语境定一次并全篇沿用，在 `note` 写依据。
  3. 图注、表题、脚注、参考文献条目同样逐段译：编号（`Fig. 3`/`图 3`/`Table 2`/`[12]`）与条目文字原位保留，不改写作者名、期刊名、卷页年。
  4. 修改变动写进 `change_log`（原文 → 译文 + 理由 + locator）。
  5. 每完成 3-5 段，将已写段落保存为 `/app/work/draft_*.json` 或合并入 `workdraft.json`；不要等到全部写完才落盘。
- **输出**：完整的 `/app/work/workdraft.json`，或至少覆盖全部索引段落的草稿；可有多份 draft 文件，脚本按 `paragraphs` 非空自动识别。
- **失败分支**：
  - 段落不可读或存在无法确定的数字/单位/引用：在 `note` 和 `pending_human` 标明，仍给出尽可能规范的译文，不删除该段。
  - 原文歧义、跨段指代不明、数字/单位冲突：保留原文数值并标注冲突，不擅自裁决。
  - 材料缺页、图像文字、扫描 PDF 取字失败、表格结构损坏：标注 `quality=low/unreadable` 的段落与缺口范围。

### 第 4 步：Agent 产出完整成品

- **输入**：`/app/work/workdraft.json`、`/app/work/index.json`、术语表。
- **动作**：
  1. 运行 `python3 "$SKILL/scripts/main.py" check` 做确定性校验。
  2. 若 `verdict: fail`，按报告逐条修稿，再 check，直到 `pass` 或确定无法通过时进入 `pending_human`。
  3. 运行 `python3 "$SKILL/scripts/main.py" build`，拼装最终产物并无条件 finalize `result.json`。
  4. `build` 在 `/app/output` 写出 `translation.md`、`glossary.csv`、`alignment.csv`、`preserved_facts.json`、`evidence_map.json`、`change_log.json`、`result.json` 及可核验资产（见第 7 节）。
- **输出**：`/app/output` 下所有最终交付物。
- **失败分支**：
  - 工作稿缺失/不全：`build` 用确定性兜底（完整双语骨架 + 空译文槽标记 `[待译 / PENDING TRANSLATION]`），状态标 `partial` 并记录缺口。
  - 金标准生成失败：主产物照常交付，`diff_report` 退化为文件级检查，状态 `partial` + `degradations`。
  - `diff`/`self_check` 生成异常：写降级版报告并记录 `errors`，不中断。
  - 可编辑 Office/图形预览生成失败：交付 Markdown/CSV 替代，标注 `format_preview_unavailable`。

### 第 5 步：自检 rubric

- **输入**：`/app/output` 全部产物、`result.json`、`output_contract` 字段。
- **动作**：
  1. 运行 `python3 "$SKILL/scripts/main.py" audit`（可选）重算 `golden_standard.json`、`diff_report.md`、`self_check.json`、`version_history.md`、`run.log`。
  2. 逐项检查 rubric 维度（见第 7 节对照表），重点确认：完整覆盖原文、术语/数字/引用正确、双语对齐、证据映射可追溯、事实无增删。
  3. 核对 `result.json` 中 `output_contract` 的每个字段是否都有值（文件路径或内容），`case_id` 与输入一致。
  4. 检查是否存在“空译文槽为 0”，即全部段落已翻译。
- **输出**：自检结论，必要时修正产物或状态。
- **失败分支**：
  - 发现缺失字段或产物：补齐后再收尾；不能补齐则标记 `partial` 并列出缺失项。
  - 发现事实错误：回修工作稿，重新 `check` 和 `build`。
  - 时间或模型请求预算接近上限：立即执行 `build` 收尾，确保 `result.json` 合法。**

### 第 6 步：回填 result.json

- **输入**：`/app/work` 和 `/app/output` 所有产物。
- **动作**：
  1. 打开 `/app/output/result.json`，逐字段核对：
     - 原始 `output_contract` 的全部字段，键名保持不变，值指向实际产物路径或摘要内容；缺失填 `null`/`[]`。
     - 必须包含 `case_id`（原样保留输入值）。
     - 包含诚实状态字段：`status`（`ok|partial|insufficient_evidence|input_error`）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`。
     - 如果契约字段与当前脚本字段同义，按契约字段名回填同一文件路径，不要改名、不删未知字段。
  2. 确认 `exit code` 为 0，不在 `result.json` 中显示任何中途崩溃。
  3. 确认 `/app/output/result.json` 是合法 JSON，可再次被脚本 `audit` 读取。
- **输出**：最终合法 `result.json`。
- **失败分支**：
  - `result.json` 不合法：用 `init`/`build` 重新生成完整壳，不中断。
  - 契约字段缺失：显式补 `null` 并标注该字段缺失原因，不得静默跳过。

## 5. 预算策略：64 次模型请求 / 900 秒内完成

必须在有限预算下优先完成 rubric 权重最高的交付物。分配建议：

| 阶段 | 建议模型请求次数 | 说明 |
|---|---|---|
| 输入发现与 init | 3-6 | 读 `case.json`、运行 `init`、查看段落清单 |
| 真实材料阅读与段落规划 | 8-15 | 用 `show --material` 或直接读材料，分批阅读，不要逐段反复调用；优先读摘要、图表题注、参考文献和含有数字/术语的段落 |
| 撰写工作稿 | 20-30 | 每 3-5 段写一次草稿，段内先写译文再填 `source_quote`、术语、change_log；尽量批量完成 |
| check 与修稿 | 3-6 | 依靠脚本确定性校验，不要逐段手动 check |
| build 与自检回填 | 3-7 | 运行 `build` 后检查关键产物和 result.json，必要时 1-2 次修正 |
| 预留处理异常 | 3-5 | 材料缺失、格式异常、字段补填 |

必须遵守：**先落盘再优化**。`init` 已写好合法 partial `result.json`。如果已经到 780 秒或 60 次模型请求，立即运行 `build` 收尾，不再继续优化风格或术语。每写一部分段落后保存 `/app/work/workdraft.json` 或分片文件，以防超时丢失。

## 6. 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json`，退出码 0。隐藏案例可能包含缺失、损坏、空输入、格式不支持、长度变化、语向变化等，处理原则如下：

| 情况 | 行为 | 结果状态 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找 `case*.json`/`task.md` 继续；契约缺字段填 `null` | `partial` / `input_error` |
| 材料为非文本（图像/PPT/压缩包） | 登记名称与 note，提示人工读取，不猜内容 | `partial` + `pending_human` |
| PDF 文本层稀薄 | 保留可取文本，标 `quality=low`，提示对照页面核对 | `partial` + `degradations` |
| 无工作稿 / 工作稿不全 | 确定性兜底：完整双语骨架 + 空译文槽标记 `[待译 / PENDING TRANSLATION]` | `partial` |
| 无任何可读材料 | 不造内容，写空 `sources` 与错误说明 | `insufficient_evidence` |
| 单个文件解析失败 | 只降级该文件，其余照常 | 视覆盖情况 `ok|partial` |
| 金标准生成失败 | 主产物照常交付，`diff_report` 退化为文件级检查 | `partial` + `degradations` |
| `diff`/`self_check` 生成异常 | 写降级版报告并记录 `errors`，不中断 | `partial` + `errors` |
| `audit` 时无既有 `result.json` | 造 partial 壳后重算资产，不改主产物 | `partial` |
| 超时/预算耗尽 | 立即运行 `build`，保留已有草稿与 partial 结果 | `partial` + 说明未完成部分 |
| 空输入 | 不造内容，写空 `sources` 与错误说明，契约字段填 `null` | `insufficient_evidence` |
| 契约为空或键名缺失 | 用默认字段结构生成 `result.json`，列出缺失键 | `input_error` / `partial` |
| 可编辑 Office/图形预览不可生成 | 交付可编辑 Markdown/CSV，标注 `format_preview_unavailable` | `partial` + `pending_human` |

所有状态必须在 `result.json` 中如实反映；`pending_human`、`errors`、`degradations` 不得为空而重写，必须与实际一致。没有足够证据时显式标注，不得编造数据、引用、分数或来源。

## 7. rubric 维度 → 交付要求 → 自证方式对照表

| rubric 维度 | 交付要求 | 自证方式（在 `/app/output` 中） |
|---|---|---|
| 实际效果：任务完成度 15 分 | 整篇原文译出，覆盖摘要、正文、图表题注、脚注、参考文献；输出形态符合要求（双语对照、纯译文、修订标记） | `translation.md` 分段数与 `index.json` 段数一致；`alignment.csv` 逐段覆盖；`result.json.deliverable` 指向实际产物 |
| 实际效果：结果正确性 15 分 | 术语、数字、单位、引用、否定与限定条件与原文一致；不得凭空补写或删改科学判断 | `glossary.csv` 无 `target` 为空的 pending 未说明项；`preserved_facts.json` 全部 `present_in_target=true` 或异常列入 `pending_human`；`alignment.csv` 的 `numbers_missing` 为空 |
| 实际效果：结果完整性 5 分 | 覆盖原文章节、图表、公式、脚注与参考文献；目标语言版本齐全 | `diff_report.md` 覆盖全部 paragraphs/figures/tables/references 且无 `missing`；`result.json.sources` 列出全部材料 |
| 实际效果：结果可核验性 5 分 | 可按句段追溯原文、术语依据、数字与引用核对结果及人工修改痕迹 | `evidence_map.json` 每段含逐字原文、译文、术语、数字/引用；`change_log.json` 记录修改动作和 locator；`alignment.csv` 有 para_id/locator/source_quote/target |
| 使用增益：质量增益 15 分 | 加载 Skill 后相对基础 Agent 稳定提升译文质量与术语统一性 | `self_check.json` 中 SC01-SC08 全部通过；`diff_report.md` 实际产物比对金标准 `verdict=pass`；`glossary.csv` 术语锁定 |
| 使用增益：效率增益 5 分 | 真实减少后编辑工时、术语统一、对照排版、数字/引用核对人工量 | `run.log` 记录各阶段耗时；`alignment.csv` 和 `glossary.csv` 可直接复用；`result.json.metrics` 给出段落数、术语数、校验通过率 |
| 使用增益：增益可验证性 5 分 | 通过公平对照证明质量或效率改善 | `diff_report.md` 与 `self_check.json` 的 `smoke` 真实子进程结果；`result.json.metrics` 有基线 vs Agent 产物的差异 |
| 创新增益：新增能力 5 分 | 形成基础 Agent 或不加载 Skill 难以实现的术语一致性、双语对齐、数字/引用保留能力 | `glossary.csv` 全篇锁定术语；`alignment.csv` 句段对齐；`preserved_facts.json` 数字/引用逐字保留；`golden_standard.json` 由材料派生 |
| 创新增益：方法改进 5 分 | 术语抽取、分块策略、对齐约束、二次校验、风格控制实质改进 | `references/quality_rules.md` 描述方法细则；`scripts/kit.py` 的校验逻辑与 `scripts/audit.py` 的 mechanistic 核对；`self_check.json` 的 `limits` 说明方法边界 |
| 创新增益：创新证据 5 分 | 证明创新点相对通用翻译工具或基础 Agent 的边界和价值 | `references/verifiability.md` 记录可复核方法；`result.json` 中的 `metrics` 与 `diff_report.md` 显示可量化改进 |
| 可靠体验：调用与易用性 3 分 | Agent 能正确触发调用，用户可按说明完成整篇翻译 | `SKILL.md` 本文件及最小调用示例；`run.log` 显示 init/show/check/build 正常 |
| 可靠体验：运行稳定性 4 分 | 不同文体、长度、语向、重复运行下持续产出可用结果 | `self_check.json` SC09/SC10 真实子进程结果；`version_history.md` 记录当前产物 sha256；`result.json` 状态稳定 |
| 可靠体验：异常处理 3 分 | 对公式与表格、术语表冲突、超长文本、语向不支持、引用格式