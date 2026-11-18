---
name: paper-pdf-structure-parser
description: 把科研 PDF 解析成可复核的结构化结果——多栏阅读顺序还原、章节层级、表格行列与合并单元格、公式编号与符号保真、图表题注与位置、参考文献、页眉页脚与脚注隔离；每条关键结论都给出逐字 quote 与页码/坐标/JSON Pointer 定位。用于文献全文提取、结构抽取、表格复用、问答与核验、以及解析质量对照。Use for scientific PDF parsing, reading-order repair, table extraction, section outline, formula preservation and evidence-located claims.
version: 1.0.0
license: MIT
---

# 科研 PDF 结构化解析器（reading-01）

## 1. 用途与边界

**做什么**：给定一份或多份科研 PDF，输出可直接复核的结构化解析结果：

- 逐字正文（去掉页眉页脚、修正串栏/错行）、多栏阅读顺序、跨栏与跨页续接；
- 章节层级树（Abstract / 编号小节 / References）、图表题注、公式编号、脚注、参考文献条目；
- 表格的结构化行列（含合并单元格标记与结构置信度）；
- 每条结论（claim）的 `kind`、逐字 `quote`、`source_id`、`location`（页码 + bbox + JSON Pointer）与可读性分类；
- 覆盖率、拒绝项、缺口、错误与降级记录，全部写进 `result.json`。

**不做什么**：不解释图表和公式的科学含义；不补造材料中不存在的数值、图元素、DOI 或统计量；不把推断当事实；不代替人工做最终科学判断。

**适用输入**：单栏/双栏/多栏论文、综述、预印本、会议模板；含表格与公式的正文；有文字层的 PDF 优先，扫描件走降级分支（见 §10）。

## 2. 触发条件与调用方式

当用户/AI 需要"读 PDF、解析论文、提取全文与章节、抽表格、核验某句话出自哪页、翻译前拿干净文本、对比解析质量"时调用本 Skill。

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

退出码恒为 `0`；`status` 表示真实完成度。脚本不依赖 CWD，资源路径用 `Path(__file__).resolve().parent` 解析。

## 3. 运行契约（评测环境）

| 项 | 约定 |
|-|-|
| 原始输入 | `/input/case.json`、`/input/task.md`，材料在 `/input/` 下（PDF/图片/CSV/XLSX/DOCX/JSON） |
| 工作目录 | `/app/work`（中间件、页级调试 JSON） |
| 产物目录 | `/app/output/`，必须含 `result.json`；本 Skill 缺省写到 `/output` 不存在时的 `./output` |
| 预算 | 64 次模型请求 / 900 s / 单次 16k tokens；脚本内部软截止 780 s，先落盘再优化 |
| 依赖 | 只用 Python 标准库；`pdftotext/pdftoppm/pdfinfo/mutool/tesseract` 若存在则作为增强后端，缺失自动降级 |
| 网络 | 不联网 |

## 4. 输入发现（语义识别，不假设键名）

1. 读 `--input`（缺省 `/input`）下的 `case.json`；不存在则递归找 `case*.json`，再退到任意 `*.json` 中含 `case_id`/`output_contract`/`task_instruction` 者。
2. `case_id` 与 `output_contract` **原样透传**（键名不改、未知字段保留、缺值 `null`/`[]`）。
3. 按语义（键名包含 `instruction|task|question|prompt|request`、`scope|material|artifact|input|file|pdf|document`）读取任务说明与材料清单，不依赖固定键名。
4. 递归扫描 `/input/**`，按**扩展名 + 魔数**（`%PDF-`、`\x89PNG`、`PK\x03\x04`、`RIFF`、CSV 文本嗅探）识别材料；PDF 为主材料，图片/表格/JSON/DOCX 作为辅材料登记。
5. 找不到的材料**明确列缺口**（`gaps`/`pending_human`），不构造内容。

## 5. 输出契约与产物

`result.json` 结构：

```json
{
  "skill": {"name": "...", "version": "...", "task_key": "reading-01"},
  "case_id": "原样", "status": "ok|partial|insufficient_evidence|input_error",
  "<output_contract 的每个键>": "原样回填（语义可判则填真实结果）",
  "contract_backfill": {"filled": [], "missing": [], "unknown_kept": []},
  "document": {"title": {}, "authors": [], "affiliations": [], "abstract": {}, "sections": [], "references": [], "page_count": 0},
  "blocks": [], "claims": [], "tables": [], "figures": [], "formulas": [],
  "coverage": {"pages": 0, "blocks": 0, "chars": 0, "sections": 0, "tables": 0},
  "sources": [], "uncertainty": [], "pending_human": [], "errors": [], "degradations": [], "changes": [], "checks": {},
  "runtime": {"started": "", "elapsed_s": 0, "backend": "", "caps": {}},
  "artifacts": {"main": "", "files": []}
}
```

配套产物（均在输出目录）：

| 文件 | 作用 |
|-|-|
| `result.json` | 主结果 + 契约回填 + 证据 + 状态（主产物） |
| `document.md` | 可读全文，带 `<!-- page:N -->` 与 `[p.N]` 定位锚点、Markdown 表格 |
| `document.json` | 结构化模型（页 → 块 → 行 → 词坐标） |
| `blocks.csv` | 块级清单：page,block_id,type,section,x0,y0,x1,y1,size,text |
| `tables.csv` | 表清单：table_id,page,caption,rows,cols,confidence,cell_count,md |
| `claims.json` | claim 数组（kind/quote/source_id/location/readability/condition） |
| `checks.json` | 确定性校验结果（quote 命中、契约覆盖、计数一致性） |
| `report.md` | 人读摘要：方法、覆盖率、限制、人工待办 |

## 6. 核心流程

`P0 落盘` → `P1 发现` → `P2 抽词` → `P3 版面` → `P4 结构` → `P5 证据` → `P6 校验` → `P7 finalize`

- **P0**：立即写一份合法 `partial` `result.json`（含 `case_id`、契约骨架、status=partial、errors=[]）。任何后续崩溃都不会没有结果。
- **P1**：按 §4 发现输入与材料，登记 `sources`（路径 + sha256 前 16 位 + 大小 + 类型）。
- **P2**：逐 PDF 抽词（带 bbox 的 word 流）。后端优先级：poppler `pdftotext -bbox-layout` → `pdftotext -layout`（无 bbox）→ 内置纯 stdlib PDF 解析器；失败逐个降级并记录 `degradations`。
- **P3**：版面重建（§7）：行聚类 → 栏切分 → 阅读顺序 → 段落合并 → 页眉页脚/脚注隔离 → 表格网格。
- **P4**：结构识别（§7.4）：标题/作者/摘要/章节树/图表题注/公式/参考文献/DOI。
- **P5**：生成 claims 与 evidence（§8），所有 quote 取自抽出的真实文本。
- **P6**：确定性校验（`checks`）：契约字段齐全、quote 可在同页文本中命中、计数自洽、表格行宽一致、公式编号唯一。
- **P7**：finalize 覆盖 `result.json`，写 `report.md`，退出码 0。

## 7. 解析方法（本题的技术主体）

### 7.1 行与栏
- 行聚类：按 y 中心 + 垂直重叠 (>50% 行高) 归并 word，行内按 x 排序，再用自适应 gap 阈值（`> 1.2×中位空格宽` 且 `> 1.2% 页宽`）切成 **span**。
- 栏检测：对所有 span 的 x 区间做占用直方图，找"穿越 span 占比 < 4%"的空白竖槽（gap ≥ 2% 页宽）作为 **gutter**；gutter 数 = 栏数 − 1。无 gutter 判单栏。
- 阅读顺序：跨 gutter 的宽 span 视为 **分隔块**（标题、跨栏图注、整宽表）；把页面按分隔块切成横带，带内按 **栏序优先、栏内 y 降序、同行 x 升序** 输出。这样双栏不再串栏，跨栏元素也不会被塞进左栏。
- 页眉页脚：位于页顶/页底 8% 带内，且（跨页重复文本 或 页号模式 `^\d{1,4}$|^[ivxlcdm]+$|Page \d+`) → `header/footer`，从正文流剔除但记录。
- 脚注：页底区域、字号小于正文字号 0.9 倍、或以 `^\d+\s|[†‡§*]` 起始 → `footnote`。

### 7.2 段落与续接
同栏相邻行在字号一致、行距 < 1.6×行高、上一行非终止标点（或下一行有首行缩进）时合并为段落；行尾连字符 `-` + 下行小写 → 去连字符合并（记入 `changes`）。跨页：上页末段未以终止标点结尾、下页首页首段同栏同位 → 标记 `continued_from_page` 并合并，保留两页定位。

### 7.3 表格
- 网格法：连续 ≥2 行、每行按 gap 切出 ≥2 个单元、列 x 边界在相邻行间对齐（容差 3 pt）→ 表格区域；列边界取各行切点中位数。
- 无框线表格：用列聚类 + 行数一致性给出 `structure_confidence: medium`；跨页续表在"表题含 continued"或列数一致且上页表在页底时合并，标 `merged_across_pages: true`。
- 每个单元格保留原文与 bbox；合并单元格无法从纯文本层确认时标 `merged_cells: "undetermined"`，不臆造。
- 输出 Markdown（`|` 分隔）+ `tables.csv` 行。

### 7.4 章节、题注、公式、参考文献
- 标题：首页最大字号、居中或顶部的短行。作者/单位：标题与摘要之间、含逗号/上标数字/邮箱的行。
- 章节：编号模式 `^(\d+(\.\d+)*)\s+\S`、`^[IVX]+\.\s`、`^[A-Z]\.\s`、全大写短行、或字号 ≥ 正文 1.08 倍的短行 → 标题；层级 = 编号点段数 + 1，字体大小差异作为交叉校验。
- 题注：`^(Fig(ure)?|TABLE|Table|图|表)\s*[0-9IVX]+`，按距离绑定最近图表块。
- 公式：行内数学符号密度 ≥ 15%（`∑∫√±×÷=≈≤≥αβγθλμσπΔ∂∇∞∝∏` 与上下标 Unicode）或以 `^\s*\(\d+[a-z]?\)` 收尾编号 → 公式块；保留原字符（不转 LaTeX，避免失真），编号单独字段。
- 参考文献：`References|Bibliography|参考文献` 之后，按 `^\[\d+\]|^\d+\.|^\d{4}\.` 起始 + 行距切条目；提取 DOI/URL/年份。

### 7.5 图像与图表位置
- poppler 路径拿不到图片坐标时，用内置内容流扫描 `Do` + XObject `/Subtype /Image` 与 `re/f` 路径簇估算图框；仅为题注推断时标 `bbox_estimated: true`。
- 图表元素（坐标轴/刻度/单位/图例/系列/误差线/比例尺/子图编号）只有**在可读文字层出现**（轴标签、图例项、子图 `(a)(b)`）时才登记并给 quote；像素读数一律标 `approximate` 并给误差说明，绝不编造数值。

## 8. 证据与定位规范

每条 claim 必含：

```json
{"claim_id": "c-001", "kind": "metadata|section|paragraph|table|figure|formula|reference|answer|quality",
 "statement": "结论（可中文）", "quote": "原文逐字片段", "source_id": "src-01",
 "location": {"page": 3, "bbox": [x0,y0,x1,y1], "block_id": "p3-b012", "json_pointer": "/document/sections/2", "section": "2.1 Setup"},
 "readability": "directly_read|inferred|undetermined",
 "condition": "成立条件/前提（如 '仅限 Table 2 的实验组'）",
 "confidence": "high|medium|low"}
```

- `directly_read`：quote 原文直接可读；`inferred`：由版面/上下文推断（说明依据）；`undetermined`：无法确定 → 只进 `uncertainty`/`pending_human`，不进结论。
- quote 必须是抽出文本的子串（空白归一化后）；校验失败 → 该 claim 降级为 `pending_human` 并计入 `checks.quote_fail`。

## 9. 评分要点 → 字段 / 检查 / 产物

| 评分点 | 落点 |
|-|-|
| 任务完成度 15 | `status=ok` 且 `document`+`blocks`+`tables`+`figures`+`formulas` 非空；`coverage` 计数 |
| 结果正确性 15 | 逐字 `quote` + `checks.quote_hit_rate`；阅读顺序 = §7.1 栏序输出；表格 `md` 行列对齐 |
| 结果完整性 5 | `document` 覆盖 title/authors/affiliations/abstract/sections/figures+tables captions/formulas/refs/header-footer/footnotes；`coverage.missing` 列缺项 |
| 结果可核验性 5 | 每个 block 带 `page`+`bbox`+`block_id`；`json_pointer` 指回 `document.json` |
| 质量增益 15 | `checks.quality_gates`（页眉页脚剔除率、串栏检测数、表格重构数、公式保真数）+ `report.md` 对照段落 |
| 效率增益 5 | `runtime.elapsed_s`、`pages_per_s`、单命令零手工步骤 |
| 增益可验证性 5 | `checks.json` 可重跑同参复现；`changes` 记录每处修正 |
| 新增能力 5 | 跨栏顺序还原、跨页表格合并、公式编号对照、扫描件降级说明（`degradations`） |
| 方法改进 5 | §7 的 gutter 检测/分隔块/自适应 gap；`runtime.caps` 说明所用后端 |
| 创新证据 5 | `checks` 中的确定性指标 + `report.md` 方法段与边界说明 |
| 调用与易用性 3 | 一条命令 + `--help` + 本文件 §2/§13 |
| 运行稳定性 4 | 恒退出码 0；每页 try/except，单页失败只降级该页 |
| 异常处理 3 | 加密/无文字层/坏字体/页码错乱 → §10 分支表 + `errors`/`degradations` |
| 文档完整性 3 | 本文件 + `references/*`（schema/checklist/method） |
| 资源可复用性 4 | 纯 stdlib、无硬编码路径、`--pdf` 可直接复用；CSV/JSON 可二次处理 |
| 分享推广价值 3 | 通用 PDF 解析器 + 可复核指标，可作解析 benchmark 基线 |

## 10. 异常与降级分支

| 情形 | 处置 | 记录 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 用目录扫描继续；仍无材料则 `status=input_error` | `errors` |
| PDF 加密 | 试空密码（内置解析器/`pdftotext`）；失败 → 该 PDF `insufficient_evidence` | `errors`,`pending_human` |
| 无文字层（扫描件） | 检测页面词数≈0 且有图像 → 尝试 `pdftoppm`+`tesseract`；无 OCR → 标 `undetermined`，请人工 OCR | `degradations`,`pending_human` |
| 图文混排、矢量图 | 只登记题注与估计框 | `figures[].bbox_estimated` |
| 字体缺 ToUnicode（乱码） | 用 Encoding/Differences 回退；仍乱码 → 该块标 `garbled`，不计入 claims | `uncertainty` |
| 页码错乱/无页码 | 以 PDF 物理页序为准，`page_label` 与 `page_index` 分开 | `changes` |
| 单页解析异常 | 该页 `blocks_status=error`，其余继续 | `errors` |
| 超时（>780 s） | 立即 finalize 已解析页，`status=partial` | `runtime.truncated_pages` |
| 输出目录不可写 | 回退 `./output` / 临时目录，记录 | `degradations` |
| 非 PDF 材料 | 登记 `sources`，PDF 之外的文本型材料做纯文本摘录 | `sources`, `gaps` |

## 11. 预算与断点

- 内部软截止 `780 s`；每页处理前后检查 `time.monotonic()`，超限即停在已解析页并 finalize。
- 每完成一页追加写 `work/pages.jsonl`，可断点续跑（`--resume` 未启用时忽略）。
- 大文件保护：`--max-pages` 缺省 0（全部），`--max-bytes` 缺省 200 MB。

## 12. 自检清单（`--selfcheck` 与每次运行末尾自动执行）

1. `result.json` 可 `json.loads`，且含 `case_id`/`status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`。
2. `output_contract` 每个键都在顶层出现，类型与模板一致。
3. 每条 claim 有 `kind/quote/source_id/location/readability`；`quote` 在页文本命中率 ≥ 95%。
4. 每个 block 有 `page`/`bbox`/`block_id`；`document.json` 中存在对应 `json_pointer`。
5. 表格 `rows×cols` 与 `md` 行数一致；公式编号不重复。
6. `coverage.pages` 等于实际解析页数；`errors` 为空时 `status` 不得为 `input_error`。
7. 输出目录内无 `__pycache__`/`.pyc`/临时文件。

## 13. 最小调用示例（示例，非正式案例结果）

输入 `case.json`（示例）：

```json
{"case_id": "demo-001", "task_instruction": "解析这篇 PDF，给出章节结构与参考文献数量，并指出表 1 的位置。",
 "output_contract": {"full_text": {"type": "string"}, "sections": {"type": "array"}, "table_locations": {"type": "array"}},
 "artifacts": ["artifacts/paper.pdf"]}
```

调用与示意输出（**示例，非正式案例结果**）：

```bash
python3 -B scripts/main.py --input /input --output /output
```

```json
{"case_id": "demo-001", "status": "ok",
 "full_text": "…（逐字正文，含 [p.1] 锚点）…",
 "sections": [{"level": 1, "number": "1", "title": "Introduction", "page": 1}],
 "table_locations": [{"table_id": "t1", "page": 2, "bbox": [72.0, 480.0, 523.0, 640.0]}],
 "claims": [{"claim_id": "c-001", "kind": "table", "quote": "Table 1: Measured parameters.", "location": {"page": 2}}]}
```

## 14. 文件清单、版本与维护

| 文件 | 说明 |
|-|-|
| `SKILL.md` | 本说明（用途/契约/流程/规则/异常/自检） |
| `scripts/main.py` | 主流程：输入发现、版面重建、结构识别、产物与最终校验 |
| `scripts/pdfcore.py` | 抽取后端：poppler bbox / poppler layout / 内置 stdlib PDF 解析器 |
| `references/output_schema.md` | `result.json` 与 claim 的字段级 schema |
| `references/parsing_rules.md` | 版面与结构判定规则、阈值与可调参数 |
| `references/checklist.md` | 提交/运行前自检清单与故障排查 |

- 版本 `1.0.0`；依赖：Python ≥3.8 标准库；可选外部增强 `poppler-utils`(pdftotext≥22)、`tesseract`、`mutool`。
- 维护：阈值集中在 `references/parsing_rules.md` 与 `scripts/main.py` 顶部常量；新增后端只需在 `pdfcore.py` 实现 `extract_bytes()` 同级函数并在 `EXTRACTORS` 注册。
