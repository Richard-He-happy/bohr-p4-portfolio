---
name: paper-pdf-structure-parser
description: 把科研 PDF 解析成可复核的结构化结果，并根据任务要求完成阅读、问答、翻译、提取、核验与知识结构化；多栏阅读顺序还原、章节层级、表格行列与合并单元格、公式编号与符号保真、图表题注与位置、参考文献、页眉页脚与脚注隔离；每条关键结论都给出逐字 quote 与页码/坐标/JSON Pointer 定位。用于文献全文提取、结构抽取、表格复用、问答与核验、翻译前清洗、以及解析质量对照。Use for scientific PDF parsing, reading-order repair, table extraction, section outline, formula preservation, evidence-located claims, and task-specific reading/QA.
version: 1.1.0
license: MIT
---

# 科研 PDF 结构化解析与证据化阅读 Skill（reading-01）

## 1. 本 Skill 是什么 / 最高优先级

本 Skill 用于在固定科研案例中完成文献阅读、解析、翻译、问答、提取、核验或知识结构化任务，并交付能被复核的结构化结果。

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本输出、骨架或模板直接当成品。你必须基于真实解析出的原文内容，逐项撰写答案、结论、译文、表格、结构化字段，并给出页码、段落、字段或公式定位。任何不确定或材料未报告的内容必须显式标注 `pending_human` / `limitations`，不得编造数据、引用、分数或科学事实。

**适用任务**：科学论文阅读与解析，包括但不限于：全文提取、多栏阅读顺序修正、章节结构识别、复杂表格解析、公式与特殊字符保真、扫描件 OCR 降级、基于证据的问答、片段翻译、实体/参数提取、参考文献核验。

**不做什么**：不解释图表和公式的科学含义；不补造材料中不存在的数值、图元素、DOI 或统计量；不把推断当事实；不代替人工做最终科学判断；不依据文件名或领域标签猜测内容。

---

## 2. 触发条件与调用方式

当用户/AI 需要“读 PDF、解析论文、提取全文与章节、抽表格、核验某句话出自哪页、翻译前拿干净文本、对比解析质量、回答科研阅读问题”时调用本 Skill。

```bash
# 标准调用（评测环境：原始输入在 /input，产物写到 /app/output）
python3 -B scripts/main.py

# 显式指定路径 / 单个 PDF
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/main.py --pdf /input/paper.pdf --output /app/output
python3 -B scripts/main.py --input /input --output /app/output --max-pages 12

# 只做环境与包自检（不写结果文件）
python3 -B scripts/main.py --selfcheck
python3 -B scripts/main.py --help
```

脚本退出码恒为 `0`；`status` 字段表示真实完成度。脚本不依赖 CWD，资源路径用 `Path(__file__).resolve().parent` 解析。脚本产出的是**基线中间产物**，不是最终交付物；你必须阅读并核验后亲自完成最终撰写。

---

## 3. 运行契约（评测环境，必须严格遵循）

| 项 | 约定 |
|-|-|
| 原始输入 | `/input/case.json`、`/input/task.md`，材料在 `/input/` 下（PDF/图片/CSV/XLSX/DOCX/JSON） |
| 工作目录 | `/app/work`（中间件、页级调试 JSON、核验用单页提取） |
| 产物目录 | `/app/output/`，必须含 `result.json`；本 Skill 缺省写到 `/output` 不存在时的 `./output` |
| result.json | 必须包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`；未知字段原样保留 |
| 可编辑产物 | 若契约要求 Office/幻灯片/图形等可编辑文件，必须额外给出真实渲染的 PDF/PNG 预览；无法渲染则如实标注 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）；脚本内部软截止 780 s，先落盘再优化 |
| 依赖 | 只用 Python 标准库；`pdftotext/pdftoppm/pdfinfo/mutool/tesseract` 若存在则作为增强后端，缺失自动降级 |
| 网络 | 不联网 |
| 资源限制 | 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink；运行时二进制产物不计入资源包 |

---

## 4. 分步执行流程（每步：输入 → 动作 → 输出 → 失败分支）

### 步骤 0：盘点输入、契约与材料（必须真实读取）

**输入**：`/input/case.json`、`/input/task.md`，以及 `/input/` 下的实际材料文件。

**动作**：
1. 读取 `case.json` 原文（若不存在则递归找 `case*.json`，再退到任意 `*.json` 中含 `case_id`/`output_contract`/`task_instruction` 者）。
2. 提取 `case_id`、`output_contract`、任务说明/指令、材料清单或 artifacts 路径。
3. 读取 `task.md` 的任务要求、评分侧重和运行约定。
4. 递归扫描 `/input/**`，按**扩展名 + 魔数**（`%PDF-`、`\x89PNG`、`PK\x03\x04`、`RIFF`、CSV 文本嗅探）识别材料；PDF 为主材料，图片/表格/JSON/DOCX 作为辅材料登记。
5. 核对 `output_contract` 的字段清单与类型。

**输出**：内部整理出「契约字段清单 × 材料清单 × 任务要求」三张表；写一份临时文件到 `/app/work/discovery.json`。

**失败分支**：
- `case.json` 缺失或坏 JSON：继续扫描材料；若仍无任何材料则 `status=input_error`，在 `errors` 中说明，仍必须产出合法 `result.json` 并退出 0。
- PDF 缺失但存在其他材料：处理能处理的文本型材料，PDF 相关需求标 `pending_human`。

---

### 步骤 1：运行脚本真实解析材料（先产出完整基线）

**输入**：步骤 0 发现的材料路径与输出目录。

**动作**：
1. 调用 `python3 -B scripts/main.py --input /input --output /app/output`。
2. 脚本会真实解析 PDF（逐字提取、版面重建、结构识别、表格/公式/题注/参考文献提取），并在 `/app/output/` 下产出基线文件，包括但不限于：
   - `result.json`（基线版本，状态可能为 partial）
   - `document.md`、`document.json`
   - `blocks.csv`、`tables.csv`
   - `claims.json`、`checks.json`、`report.md`
3. 这些文件是**材料真实解析后的中间产物**，不是最终答案。

**输出**：基线产物集合 + 脚本运行日志/错误信息。

**失败分支**：
- 脚本崩溃或超时：立即将已知信息写入 `/app/output/result.json`（状态 `partial`），错误写入 `errors`，并继续尝试用脚本提供的 `--selfcheck` 或标准库直接读取 PDF 的最小化处理。
- 输出目录不可写：回退到 `/app/work` 或 `/tmp/output`，最终尽量复制到 `/app/output`。
- PDF 加密、无文字层、字体乱码等异常按 §8 降级，并在 `degradations`/`pending_human` 中说明。

---

### 步骤 2：阅读脚本产物并核验材料证据（Agent 必须亲自做）

**输入**：`/app/output/` 下的基线产物，必要时原始 PDF。

**动作**：
1. 打开并阅读 `document.md`、`claims.json`、`tables.csv`、`checks.json` 等产物。
2. 核验以下内容：
   - 关键结论的 `quote` 是否逐字来自原文（在 `document.md` 中可检索到）。
   - 阅读顺序是否合理（双栏不串栏、页眉页脚已隔离、跨页续接正确）。
   - 章节层级、表格行列、公式编号、题注定位、参考文献条目是否完整且可追溯。
   - 对不确定或脚本无法读出的部分，确认是否已被标记为 `undetermined`、`garbled`、`footnote`、`header/footer` 等。
3. 对需要核验的关键数字/引用/结论，可额外用 `pdftotext -f N -l N` 或 `python3 -B scripts/main.py --pdf ... --max-pages N` 提取单页文本，与 claims 比对。
4. 记录核验结果：每个关键结论标记 `verified`（已核对）、`pending_human`（人工不可替代）、`conflicts`（冲突/不一致）。

**输出**：一份核验记录，写入 `result.json` 的 `checks`/`uncertainty`/`pending_human`/`changes`，以及最终产物。

**失败分支**：
- 发现脚本漏提、错置或读不出关键部分：在 `changes` 中记录修正动作，自行补提或标注缺口；不得因为脚本漏提就编造原文。
- 无法确认的结论：降级为 `pending_human`，并在 `uncertainty` 说明原因。

---

### 步骤 3：根据任务要求产出完整成品（由 Agent 亲自撰写/制作）

**输入**：步骤 0 的任务指令与 `output_contract`，步骤 2 的核验记录与真实解析内容。

**动作**：
1. 逐项对照 `output_contract` 的字段与任务问题，**亲自撰写**最终答案：
   - 问答类：直接给出答案，并附 `quote` + 页码/段落/字段定位。
   - 翻译类：逐段翻译，保留原文页码锚点，片段标注来源。
   - 提取类：列出实体、参数、数值、表格、图片、公式编号等，均给出位置与依据。
   - 结构化类：输出章节树、表格 Markdown/HTML、公式编号与符号、参考文献条目等，使用解析出的原文内容，不套用模板。
   - 核验类：给出核验结果、冲突项与未报告项，写明证据边界。
2. 若 `output_contract` 要求可编辑 Office/幻灯片/图形文件，Agent 需根据解析内容生成相应可编辑文件（如 `.docx`/`.pptx`/`.xlsx`/`.svg`），并生成真实渲染的 PDF/PNG 预览；若环境缺乏库或无法生成，则产出 Markdown/文本替代并在 `result.json` 中如实标注 `limitations`，不得伪造预览。
3. 所有写入 `result.json` 顶层字段的值必须来自真实材料；未知或无法判断用 `null`/`[]` 并标 `missing`。
4. 更新 `result.json` 的 `status` 为真实状态：`ok` / `partial` / `insufficient_evidence` / `input_error`。
5. 确保 `result.json` 包含原 `output_contract` 的**全部字段**（键名不改）和 `case_id`。

**输出**：最终版 `/app/output/result.json` 及契约要求的全部产物文件。

**失败分支**：
- 契约中某字段无法完成：将该字段填 `null` 或 `[]`，在 `contract_backfill.missing` 标出，并在 `pending_human` 说明原因；不得删除该字段。
- 时间或请求将耗尽：先落盘当前 partial，再继续优化。

---

### 步骤 4：Rubric 自检与结果回填

**输入**：最终产物、契约字段清单。

**动作**：
1. 逐项核对 `output_contract` 的每个键是否在 `result.json` 顶层出现，类型是否与模板一致。
2. 核对每个关键结论是否有证据定位（页码/段落/图表/公式位置），无法定位的是否标 `undetermined`。
3. 核对 `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`checks`、`runtime` 是否真实、非空且自洽。
4. 更新 `status` 与 `contract_backfill`，记录 `filled`/`missing`/`unknown_kept`。
5. 若发现缺字段或契约未覆盖，补齐或显式标缺，不得留空键。
6. 最终写回 `/app/output/result.json`。

**输出**：自检通过的最终 `result.json`，所有契约字段完整、证据可复核、状态诚实。

**失败分支**：
- 若自检发现缺字段、非法 JSON 或无法验证证据：立即修正；若无法修正，将问题写入 `errors`/`pending_human`，仍保持退出码 0。
- 若时间不足，保留当前 partial，不追求完美。

---

### 步骤 5：收尾与退出

**动作**：
1. 确保 `/app/output/result.json` 能被 `json.loads` 正确解析。
2. 清理 `__pycache__`、`.pyc`、临时文件。
3. 检查文件大小与数量符合资源限制（运行时产物不计入资源包）。
4. 退出码 0。

---

## 5. 预算策略（64 次模型请求 / 900 秒 / 单次 16384 tokens）

你必须预算感知，按以下分配执行；脚本运行时间不计模型请求，但占用 900s 预算。

| 步骤 | 模型请求预算 | 说明 |
|-|-|-|
| 步骤 0 盘点输入 | 2–3 | 读取 case.json/task.md，整理契约与材料 |
| 步骤 1 跑脚本 | 1 | 触发脚本，等待脚本完成 |
| 步骤 2 阅读核验 | 8–15 | 抽取关键页面/块核验 quote、阅读顺序、表格/公式 |
| 步骤 3 撰写成品 | 15–25 | 按契约逐项撰写；优先完成高权重交付物 |
| 步骤 4 自检回填 | 5–8 | 逐项核对契约、证据、状态、字段 |
| 步骤 5 收尾 | 1 | 最终确认并退出 |
| 余量 | 4–8 | 应对意外或返工 |

**优先级原则**：
- 先完成 rubric 权重最高的交付物：实际效果 40 分中的任务完成度/正确性/完整性/可核验性。优先产出完整的结构化结果、问答、关键证据定位。
- 再优化使用增益/创新增益相关指标（阅读顺序修正、表格重构、公式保真等）。
- 每次撰写前先问“这个字段/文件对 rubric 的影响有多大”，低权重且耗时的可降级标注，但不得省略契约字段。

**落盘策略**：
- 脚本运行结束即刻落盘基线 partial result.json。
- 每完成一个契约大项（例如全文、章节、表格、答案），更新一次 result.json。
- 剩余 120 秒或模型请求达 60 次时，冻结进一步优化，finalize 当前 partial，确保合法退出。

---

## 6. 隐藏案例鲁棒性

隐藏案例可能包含不同版式、不同语言、不同材料状态，必须稳定降级。

| 异常情形 | 降级策略 | 记录字段 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 扫描 `/input/**` 寻找材料；读取 `task.md` 推断任务；无材料则 `status=input_error`，退出 0 | `errors` |
| PDF 加密 | 试空密码（内置解析器/`pdftotext`）；失败 → 该 PDF 标 `insufficient_evidence` | `errors`,`pending_human` |
| 无文字层扫描件 | 检测页面词数≈0 且有图像 → 尝试 `pdftoppm`+`tesseract`；无 OCR 则标 `undetermined`，请人工 OCR | `degradations`,`pending_human` |
| 字体缺 ToUnicode 乱码 | 用 Encoding/Differences 回退；仍乱码 → 该块标 `garbled`，不计入 claims | `uncertainty` |
| 页眉页脚/页码错乱 | 以 PDF 物理页序为准，`page_label` 与 `page_index` 分开，错乱页码记录 | `changes` |
| 单页解析异常 | 仅该页标 `blocks_status=error`，其余继续 | `errors` |
| 超时（>780 s 或总预算） | 立即 finalize 已解析页，`status=partial`，写明截断页 | `runtime.truncated_pages` |
| 输出目录不可写 | 回退 `/app/work` 或临时目录，最终尽量复制到 `/app/output` | `degradations` |
| 非 PDF 材料 | 登记 `sources`，文本型材料做纯文本摘录，PDF 无法处理的部分标缺口 | `sources`,`gaps` |
| 空输入/无材料 | 生成 `status=input_error` 的合法 `result.json`，含完整结构，退出 0 | `errors` |

**任何情况下都必须产出合法 `result.json`，退出码 0。** 无法完成的任务字段填 `null`/`[]`，并在 `pending_human`/`limitations` 说明。

---

## 7. Rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度/分值 | 交付要求 | 自证方式（写入 result.json / 产物） |
|-|-|-|
| **实际效果 40** | | |
| 任务完成度 15 | 是否真的把 PDF 解析成可用结构化结果，而非“像全文”的文本 | `result.json` 中 `document`、`blocks`、`tables`、`figures`、`formulas` 非空；`coverage` 计数 |
| 结果正确性 15 | 文字与原文逐字一致、阅读顺序正确、表格行列/单元格归属准确、公式符号不失真 | 每个 claim 有逐字 `quote`，`checks.quote_hit_rate`；`document.md` 的 `[p.N]` 锚点可定位；表格 `md` 行列对齐 |
| 结果完整性 5 | 覆盖标题、作者单位、摘要、章节层级、图表题注、公式编号、参考文献、页眉页脚与脚注 | `document` 字段全覆盖；`coverage.missing` 列出缺项；`blocks.csv` 分类统计 |
| 结果可核验性 5 | 每个解析结果能指回原文页码、区块位置与依据 | 每个 block 带 `page`+`bbox`+`block_id`；claims 带 `location` 与 `json_pointer` |
| **使用增益 25** | | |
| 质量增益 15 | 相比不加载 Skill 是否提升解析准确性、版式还原度 | `checks.quality_gates`（页眉页脚剔除率、串栏检测数、表格重构数、公式保真数）+ `report.md` 方法对照段 |
| 效率增益 5 | 减少解析时间、人工校对、重跑成本 | `runtime.elapsed_s`、`pages_per_s`、单命令零手工步骤 |
| 增益可验证性 5 | 公平对照证明改善 | `checks.json` 可重跑同参复现；`changes` 记录每处修正；`runtime.caps` 说明后端 |
| **创新增益 15** | | |
| 新增能力 5 | 跨栏顺序还原、跨页表格合并、公式编号对照、扫描件增强 | `degradations`/`caps` 说明能力；`report.md` 专门段 |
| 方法改进 5 | 版面分析、阅读顺序判定、表格结构重建、公式识别、后处理校验的实质改进 | 技术描述（§7 原解析方法）+ `checks` 指标 + `runtime.caps` |
| 创新证据 5 | 相对已有方案边界与价值 | `report.md` 方法边界段 + 确定性指标 |
| **可靠体验 10** | | |
| 调用与易用性 3 | Agent 能正确触发调用，用户按说明完成一次解析 | 一条命令 + `--help` + 本文件 §2/§4 |
| 运行稳定性 4 | 不同版式、页数、语言、重复运行持续可用 | 恒退出码 0；每页 try/except，单页失败只降级该页；幂等 |
| 异常处理 3 | 加密、无文字层、图片表格、乱码字体、页码错乱的识别与处置 | §8 降级表 + `errors`/`degradations`/`pending_human` |
| **生态贡献 10** | | |
| 文档完整性 3 | 使用说明、依赖、配置、示例、适用范围、限制与维护信息齐全 | 本 SKILL.md + `report.md` + 脚本 `--help` |
| 资源可复用性 4 | 解析器、脚本、配置可被他人复用 | `scripts/main.py`、`scripts/pdfcore.py` 纯 stdlib、无硬编码路径、`--pdf` 可独立复用 |
| 分享推广价值 3 | 沉淀可分享案例/方法/Benchmark 经验 | `report.md` 总结方法、限制与可复现步骤 |

---

## 8. 输出契约与 result.json 结构

`result.json` 主结构模板（最终由 Agent 在脚本基线之上撰写；必须包含 `case_id` 和原 `output_contract` 全部字段）：

```json
{
  "skill": {"name": "...", "version": "...", "task_key": "reading-01"},
  "case_id": "原样",
  "status": "ok|partial|insufficient_evidence|input_error",
  "<output_contract 的每个键>": "按任务真实填写，无法完成填 null/[] 并标 missing",
  "contract_backfill": {"filled": [], "missing": [], "unknown_kept": []},
  "document": {"title": {}, "authors": [], "affiliations": [], "abstract": {}, "sections": [], "references": [], "page_count": 0},
  "blocks": [],
  "claims": [],
  "tables": [],
  "figures": [],
  "formulas": [],
  "coverage": {"pages": 0, "blocks": 0, "chars": 0, "sections": 0, "tables": 0, "missing": []},
  "sources": [],
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "changes": [],
  "checks": {},
  "runtime": {"started": "", "elapsed_s": 0, "backend": "", "caps": {}},
  "artifacts": {"main": "", "files": []}
}
```

配套产物（均在输出目录；由脚本基线产出，Agent 核验/改写后保留）：

| 文件 | 作用 |
|-|-|
| `result.json` | 主结果 + 契约回填 + 证据 + 状态（最终交付） |
| `document.md` | 可读全文，带 `<!-- page:N -->` 与 `[p.N]` 定位锚点、Markdown 表格 |
| `document.json` | 结构化模型（页 → 块 → 行 → 词坐标） |
| `blocks.csv` | 块级清单：page,block_id,type,section,x0,y0,x1,y1,size,text |
| `tables.csv` | 表清单：table_id,page,caption,rows,cols,confidence,cell_count,md |
| `claims.json` | claim 数组（kind/quote/s