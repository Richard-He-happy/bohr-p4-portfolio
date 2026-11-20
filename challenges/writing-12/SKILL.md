---
name: latex-writing-compile
description: 单命令完成 /input 科研案例的 LaTeX 写作、编译修复、公式/表格/引用/模板适配、证据映射与 result.json 契约回填；支持 Agent draft 改进与无 draft 确定性兜底；任何异常退出码仍为 0。
version: 2.0.0
---

# LaTeX 写作与编译：单命令全流程 + Agent 优先双路径

## 0. 最高优先级（先读）

1. **第一动作必须是执行单命令全流程脚本**，先落盘完整 baseline，不要先读完全部材料再开始。
2. **任何情况下都以退出码 0 结束**。失败通过 `result.json` 的 `status` / `errors` / `degradations` 表达。
3. **只依据 `/input` 真实材料写作和修复**。不按文件名、领域标签猜测内容；材料缺失、冲突、无法判断时必须显式登记，不编造科学数据。
4. **所有事实、数字、引用、图表、关键论断必须可回溯到原文**，使用 `[S#]` 来源编号与 `文件#行号/段落/条目` locator。
5. **优先保护完整交付物**。脚本产出的结构化产物不得为了“好看”手改；Agent 的增强必须保留可审计记录。
6. **预算意识**：官方执行预算约 64 次模型请求 / 900 秒。脚本 1–3 次调用产出 baseline，其余请求用于核验、修正和写作改进；接近 56 次请求或 780 秒时立即收尾。

---

## 1. 输入、输出与契约

### 1.1 目录约定

| 项 | 约定 |
|---|---|
| Skill 根目录 | `/skills/weekly-skill` |
| 输入 | `/input`：`case.json`、`task.md`、材料、`.tex/.bib/.cls/.sty/.md/.txt/.csv/.json/.tsv/.pdf/.docx/图片` |
| 工作目录 | `/app/work`：可写中间文件、日志、`draft.json`、临时编译产物 |
| 输出 | `/app/output`：全部最终产物与 `result.json` |
| 退出码 | 恒为 0 |
| 网络 | 禁止联网；缺宏包/字体只给处置建议，不自动安装 |

### 1.2 最终产物清单

| 文件/目录 | 内容 |
|---|---|
| `deliverable.tex` | 主文件副本，可继续编辑、可并入稿件 |
| `tex_project/` | 完整可编译工程，含 `.tex/.bib/.cls/.sty/图片` 等 |
| `deliverable.pdf` | 编译成功时存在；失败时明确说明原因 |
| `result.json` | 结构化结果，包含原 `output_contract` 全部字段和 `case_id` |
| `verification.json` | 独立审计：逐字引用、计数、结构、契约覆盖检查 |
| `build_report.md` | 人读摘要：状态、错误根因、复现命令、版本、限制 |
| `baseline/` | 改动前快照，供 diff 与核验 |
| `agent_review.json` | Agent 对脚本基线的核验与增强记录 |
| `pending_human.json` | 人工确认项、材料缺口、冲突项 |
| `evidence_table.json` | 事实、来源、逐字 quote、locator、强度、覆盖范围 |

### 1.3 `result.json` 最小字段与双回显

`result.json` 顶层至少包含：

  case_id
  status
  deliverable
  compile
  diagnostics
  diagnostics_residual
  change_log
  preserved_facts
  evidence_map
  citations
  workorder_receipt
  pending_human
  uncertainty
  errors
  degradations
  notes
  metrics
  runtime
  verification
  output_contract
  contract_fill

同时必须做双回显：

  result.json 顶层重复原 output_contract 的全部字段（键名不变）。
  result.json.output_contract 也从输入原样深拷贝，未知字段保留。
  case_id 必须同时出现在 result.json 顶层与 result.json.output_contract 内。

`contract_fill` 记录每个契约字段由哪个文件或哪个 result 字段满足：

  { "<契约字段>": "<磁盘文件路径或 result.json 字段名> | null }

无法满足的字段写 `null`，并在 `pending_human` 或 `errors` 说明原因。

### 1.4 `status` 取值

- `ok`：PDF 存在、关键诊断收敛、事实核验通过、契约字段完整。
- `partial`：已产出可编辑成果，但编译失败、部分字段未覆盖或存在未确认修改。
- `insufficient_evidence`：材料不足，无法完成可信写作或核验。
- `input_error`：`case.json` 无效、契约缺失或输入不可解析，但仍产出结构完整结果。

---

## 2. 单命令全流程入口

第一步必须执行，不要先读全部材料：

  python3 -B /skills/weekly-skill/scripts/latex_doctor.py run \
    --input /input \
    --output /app/output \
    --work /app/work

若 `scripts/latex_doctor.py` 不存在，则使用本包等价入口：

  python3 -B /skills/weekly-skill/scripts/latex_doctor.py \
    --input /input \
    --out /app/output \
    --work /app/work \
    --max-seconds 820 \
    --timeout 180

如果上述命令因参数不匹配失败：

  python3 -B /skills/weekly-skill/scripts/latex_doctor.py --help

然后使用等价参数继续，不得跳过 baseline；若参数确实不兼容，在 `degradations` 中写 `script_args_mismatch`。

该命令内部必须完成：

1. **init**：盘点 `/input`，分配来源编号，抽取事实，建立契约台账，进行冲突分组。
2. **build**：校验/兜底抽取，生成全部产物，渲染可编译 `.tex` 工程，finalize `result.json`。
3. **selfcheck**：产物与契约自检，生成 `verification.json`。

脚本跑完后，先读：

  /app/output/result.json
  /app/output/build_report.md
  /app/output/verification.json

再决定哪些内容需要 Agent 增强。

---

## 3. Agent 优先双路径

### 3.1 Agent 路径（优先）

在脚本 baseline 落盘后，如果预算允许：

1. 读 `/app/output` 中的台账、`evidence_table.json`、`verification.json`。
2. 回到 `/input` 真实读原文，核对 script 抽取的 quote、数字、locator。
3. 将你的任务理解和修改计划写入：

  /app/work/draft.json

4. 如需重新抽取或修复，将 `draft.json` 写入后重跑第 2 节命令。
5. 若脚本不消费 `draft.json`，则按 `draft.json` 的批准项直接修改 `/app/output/tex_project`，并把执行结果写入 `agent_review.json`。

`draft.json` 推荐形状：

  {
    "case_id": "...",
    "mode": "agent|auto",
    "source_assignments": [
      {
        "source_id": "S1",
        "file": "materials/xxx.md",
        "kind": "md|tex|bib|cls|sty|pdf|docx|csv|json|image",
        "role": "main|template|bibliography|fact|constraint",
        "extract": "原文逐字内容",
        "locator": "materials/xxx.md#L42",
        "confidence": "high|medium|low"
      }
    ],
    "claims": [
      {
        "claim_id": "C1",
        "type": "fact|formula|table|citation|meta|change",
        "source_ids": ["S1"],
        "quote": "原始逐字片段",
        "locator": "file#L42",
        "target": "deliverable.tex 或 tex_project 中的目标位置",
        "constraint": "模板/格式/受众约束",
        "action": "keep|fix|rewrite|compile|observe",
        "reason": "为何这样处理",
        "human_confirm": false
      }
    ],
    "change_plan": [],
    "missing": [],
    "conflicts": [],
    "uncertainty": []
  }

### 3.2 无 draft 确定性兜底

如果没有时间写 `draft.json`，或模型请求预算不足：

- 第 2 节命令必须自动完成基线产出。
- `build` 阶段用 init 台账做确定性抽取，生成实质工作稿。
- 每个关键数字/论断仍必须带 `[S#]` 来源和 `文件#行号/段落/条目` locator。
- 自动抽取内容必须逐字 quote，不得用模型“补写”替代原文核验。
- 自动抽取状态必须诚实写入：

  gaps
  degradations
  AUTO_EXTRACT_DETERMINISTIC
  pending_human

两条路径产出同一套产物、同一 `result.json` 契约，不产生两套不同结构。

---

## 4. 材料解析与事实底稿

### 4.1 读取规则

| 类型 | 动作 |
|---|---|
| `.md/.txt/.csv/.json/.tsv` | 直接读取原文 |
| `.tex/.bib/.cls/.sty` | 直接读源码，不忽略注释 |
| `.pdf` | 优先 `pdftotext -layout <file> -`；无文本层则写 `degradations[pdf_text_unavailable]` |
| `.docx` | 用标准库 `zipfile` 或已有脚本解析；失败写 `errors[docx_read_failed]` |
| 图片/扫描 PDF | 不 OCR；若任务必需图片数据，写 `pending_human`，不得虚构 |
| `.log/.aux/.out` | 作为编译诊断材料，不作为科学事实来源 |

### 4.2 事实抽取要求

- 数字、单位、变量、符号、表格数值、引用条目、图表标题、结论、任务约束都要进入事实底稿。
- 每条事实必须至少一个 `source_id` 和 locator。
- 同一事实出现在多个来源时全部记录；冲突不选边，进入 `pending_human`。
- 材料没有的事实不得补造；如任务要求材料外的事实，写 `pending_human` 与 `uncertainty`。

### 4.3 来源编号

- 脚本初始化时给每个来源分配 `S1, S2, ...`。
- 每条 `evidence_map` / `claims` / quote 都必须引用该编号。
- locator 示例：
  - `manuscript.tex#L23`
  - `refs.bib#entry:he2025`
  - `notes.md#para4`
  - `case.json#output_contract`
  - `data.csv#row12`

---

## 5. LaTeX 修复与写作规则

### 5.1 诊断顺序

1. 先静态诊断，不盲目编译。
2. 用 `-interaction=nonstopmode -file-line-error` 编译。
3. 从 `.log` 中提取第一条关键错误，定位文件、行号、根因。
4. 级联错误只保留首因，后续标记为 `cascade`。
5. 最多执行 3 轮修复循环；仍失败则保留 `partial`，不得无限循环。

### 5.2 错误分类

| 分类 | 内容 |
|---|---|
| `E01_MISSING_FILE` | 缺 `.tex/.cls/.sty/.bib/图片` |
| `E02_TEX_SYNTAX` | 未闭合括号、命令拼写、环境错误 |
| `E03_PACKAGE` | 宏包缺失、冲突、option 顺序 |
| `E04_PREAMBLE_OPTION` | 导言区 option 冲突、重复加载 |
| `E05_MATH` | 公式符号、上下标、对齐、编号、单位正斜体 |
| `E06_TABLE` | 列宽、列数、合并单元格、三线表、溢出 |
| `E07_REF_CITE` | `\ref/\cite` 未定义、`.bib` 条目不匹配、编号不收敛 |
| `E08_TEMPLATE` | 模板必填项、文件结构、版式合规 |
| `E09_FONT_ENCODING` | 缺字体、非 ASCII、特殊字符 |
| `E10_PERMISSION` | 输出目录、TEXMFVAR、权限不足 |
| `E11_TIMEOUT` | 编译超时 |
| `E12_CASCADE` | 首因之后的级联错误 |
| `E13_INFO` | 警告，不影响本轮编译 |

### 5.3 修复优先级

按评分权重：

1. 先保 `.tex` 可编辑、可编译、可并入稿件。
2. 再保事实正确：公式、表格数值、引用、结论与原文意图一致。
3. 再保模板合规：模板必填项、版式、文件结构。
4. 最后补证据映射、自检、pending_human。

### 5.4 编译工作流

- 有 `bibliography` 需求时：
  1. `pdflatex -interaction=nonstopmode -file-line-error`
  2. `bibtex` 或 `biber`
  3. `pdflatex`
  4. `pdflatex`
- 无参考文献时至少跑 2 轮 `pdflatex` 使交叉引用收敛。
- 编译失败时保留 `.log`、命令、tail；不要用 PDF 截图替代源码。
- 缺 TeX 发行版时：只做静态诊断，`compile.status=skipped`，`status=partial`。

### 5.5 写作与改写规则

- 只编辑 `/app/output/tex_project` 下的源码；`/input` 和 `/app/output/baseline` 保持只读。
- 所有正文型改写必须来自真实材料。
- 每次重大改动写 `change_log`：
  - original_quote
  - revised_quote
  - reason
  - locator
- 每次改动后更新 `evidence_map` 和 `verification.json`。
- 不把 PDF、截图或无法编译片段当 `.tex` 成品。
- 不编造文献、DOI、数值、结论。

---

## 6. 隐藏案例鲁棒性

隐藏案例最可能分三类：正常、边界、异常。必须分别处置。

| 情况 | 处置 |
|---|---|
| 正常：完整 `.tex` 工程 + `.bib` + 模板 | 先跑单命令全流程，再核验公式、表格、引用、模板字段 |
| 边界：无 TeX 发行版 | 只做静态诊断，`compile.status=skipped`，`status=partial`，写 `degradations[no_latex_engine]` |
| 边界：缺 `.cls/.sty` | `E01_MISSING_FILE`/`E03_PACKAGE`；给 `tlmgr` / `TEXMFHOME` 建议，不自动安装 |
| 边界：缺字体/特殊字符 | `E09_FONT_ENCODING`；建议替代字体族或安全字符 |
| 边界：无 `.tex` 纯写作题 | 生成最小可编译骨架，正文由 Agent 撰写，写 `degradations[scaffold_used]` |
| 边界：PDF 无文本层 | `degradations[pdf_text_unavailable]`；不依据文件名猜内容 |
| 边界：材料冲突 | 所有冲突值保留，进入 `pending_human`，不选边 |
| 边界：材料不足 | 不补造数据；写 `pending_human` 与 `uncertainty` |
| 异常：`case.json` 缺失/损坏 | `status=input_error`，`errors[case_json_invalid]`，仍产出合法 `result.json` |
| 异常：`output_contract` 缺失 | `output_contract: {}`，仍强制输出本文件规定的最小字段 |
| 异常：空输入 | `status=insufficient_evidence`，`pending_human` 说明缺少材料 |
| 异常：DOCX 损坏 | `errors[docx_read_failed]`，从其他材料继续 |
| 异常：编译超时 | `compile.passes[].tail=TIMEOUT`，保留已有日志 |
| 异常：权限不足 | `HOME/TEXMFVAR/TEXMFCFG` 重定向到 `/app/work`；仍失败则 `E10_PERMISSION` |
| 异常：脚本异常 | `errors[script_failed]`；仍手工生成合法 `result.json` |
| 异常：预算告急 | 停止新增改进，保留 partial，写 `degradations[budget]` |

任何情况下必须确保：

- 退出码 0。
- `/app/output/result.json` 存在且合法。
- 包含 `case_id.status.errors.degradations.pending_human.uncertainty.runtime.output_contract`。
- 不编造软件安装状态、benchmark 分数、运行 trace。

---

## 7. 保护 Agent 编辑不丢失

脚本重跑可能覆盖已有成果。执行以下保护：

1. 在 Agent 作出实质修改后，先复制一份：

  cp -rp /app/output/tex_project /app/work/last_good
  cp -p /app/output/deliverable.tex /app/work/last_good 2>/dev/null || true

2. 重跑脚本后，比较 `deliverable.tex` 与 `tex_project`。
3. 若脚本覆盖了好的 Agent 编辑，从 `/app/work/last_good` 恢复编辑产物。
4. 恢复后必须重新校验 `result.json` 与磁盘产物一致；不一致时重跑脚本或用脚本更新 result。
5. 不要频繁重跑完整脚本；只在 baseline、重大修改后、最终收尾时运行。

---

## 8. 自检与 finalize

### 8.1 契约自检

逐项确认：

- `output_contract` 每个键已在 `result.json` 顶层与嵌套 `output_contract` 中回显。
- `case_id` 在顶层与嵌套中均存在。
- `contract_fill` 已为每个契约字段给出磁盘文件或 result 字段，无法满足则为 `null`。
- `result.json` 可用以下命令解析：

  python3 -m json.tool /app/output/result.json

### 8.2 产物自检

- `deliverable.tex` 含 `\documentclass` 与完整 `\end{document}`。
- `tex_project/` 包含编译所需的 `.bib/.cls/.sty/图片`。
- 如存在可编辑 Office/幻灯片/图形类产物，且有契约要求，必须有真实渲染 PDF/PNG 预览。
- `.tex` 编译成功时 `deliverable.pdf` 存在；失败时 `build_report.md` 说明原因。

### 8.3 证据自检

- 每个数字、术语、引用、图表、关键论断都有 `[S#]`。
- 每条 `evidence_map` 均含 `source_id`、`locator`、逐字 `quote`。
- `change_log` 能被 `baseline/` 与 `tex_project/` 双向命中。
- 自动抽取项写 `AUTO_EXTRACT_DETERMINISTIC`，Agnet 核验项写 `agent_review.json`。

### 8.4 最终命令

最后再执行一次全流程命令，保证产物与 `result.json` 同源：

  python3 -B /skills/weekly-skill/scripts/latex_doctor.py \
    --input /input \
    --out /app/output \
    --work /app/work \
    --max-seconds 820 \
    --timeout 180

如果脚本会覆盖 Agent 编辑，先按第 7 节保护/恢复，再执行最终校验。

---

## 9. 预算策略

| 阶段 | 请求数 | 动作 |
|---|---|---|
| 开局 baseline | 1–3 | 先跑脚本，再读 `result.json/build_report.md/verification.json` |
| 材料与契约阅读 | 5–10 | 读 `task.md`、关键原始材料、`output_contract` |
| 事实核验 | 8–15 | 核对数字、公式、表格、引用，写 `agent_review.json` |
| 核心 LaTeX 修复/写作 | 10–20 | 优先完成可编译 `.tex` 与事实正确性 |
| 复跑与自检 | 4–8 | 保持 result 与磁盘产物一致 |
| 预留 | 5–10 | 异常恢复、partial 增强 |

不能把请求浪费在：

- 反复盲编译。
- 重复读同一文件。
- 生造评分、金标准、白板。
- 写无法落盘的长篇自述。

到 56 次请求或 780 秒时，停止新增改进，优先 finalize：

  status 必须诚实。
  errors / degradations 必须记录限制。
  result.json 必须合法。
  退出码必须为 0。

---

## 10. 生态与可靠体验要求

- 纯标准库、离线、Python 3.9+。
- 提交包内所有脚本路径有效，不依赖未说明的个人文件。
- 若存在 `environment/resources.yaml`，以它作为环境事实来源；否则以脚本 `--help` 和运行时输出为准。
- 若存在 `SELFTEST.md`，其检查清单应与本 SKILL 的自检一致。
- `references/rules.json`、`references/method.md`、`references/example.md` 是可选辅助材料，只在遇到不确定处理方式时阅读。
- 不创建超过 50 个 UTF-8 文本文件，单文件不超过 500KB，总提交体积不超过 2MB。
- 所有中间日志可以保留在工作目录，但最终输出只保留评分所需产物。

---

## 11. 禁止事项

1. 禁止手改脚本生成的 `claims.json`、`evidence_table.json`、`result.json` 结构字段，除非脚本损坏且需要恢复。
2. 禁止删除、清空或遗漏 baseline 产物。
3. 禁止覆盖 `/input`。
4. 禁止根据文件名、标题、领域标签猜测材料内容。
5. 禁止补造材料外数字、文献、结论、软件版本。
6. 禁止用 PDF、截图或无法编译片段冒充 `.tex` 成品。
7. 禁止无限编译或超过 3 轮修复循环。
8. 禁止非零退出码；失败只能写入 `result.json`。