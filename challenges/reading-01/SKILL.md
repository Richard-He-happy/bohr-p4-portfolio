---
name: paper-pdf-evidence-parser
description: >-
  科研文献 PDF 解析与证据化阅读 Skill。围绕真实科研论文材料完成阅读、问答、翻译、提取、核验与知识结构化，
  重点修正多栏阅读顺序、章节层级、表格行列与合并单元格、公式编号与特殊字符保真、图表题注定位、参考文献、
  页眉页脚与脚注隔离；为每个关键结论提供逐字 quote、来源编号 S#、页码/段落/坐标 locator。
  Use for scientific PDF parsing, reading-order repair, table extraction, section outline, formula preservation,
  evidence-located claims, task-specific reading/QA, and honest fallback when materials are incomplete.
version: 2.0.0
license: MIT
---

# 科研文献 PDF 解析与证据化阅读 Skill

## 0. 最高优先级：运行边界与不可违背规则

1. **单命令完整交付优先**：先运行
   `python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work`
   脚本内部依次执行 `init → build → selfcheck`，必须有可用的确定性兜底产物。
2. **所有脚本调用必须退出码 0**：即使输入缺失、PDF 损坏、任务无法完成，也要产出合法 `result.json` 并记录诚实状态。
3. **契约双回显**：`case_id` 与题面 `output_contract` 的全部字段必须既出现在 `result.json` 顶层，也出现在
   `result.json["output_contract"]` 中；缺字段不得删除，只能填 `null`/`[]` 并登记 `missing`。
4. **证据可核验**：每个关键结论必须有来源编号 `S#` 与 locator：`文件名#页码/段落号` 或 `文件名#块号/坐标`；
   无法核实的内容写入 `pending_human` / `uncertainty` / `degradations`，不得编造科学事实或来源。
5. **脚本产出结构化 JSON 的契约键不得手工篡改**。Agent 可以写 `${WORK}/draft.json`、改正文型交付物草稿，
   并让 `check`/`build` 合并；不得直接编辑 `result.json`、`document.json`、`claims.json` 等最终结构化文件。
6. **不联网、不安装依赖**：只用 Python 标准库；可选 `pdftotext/pdftoppm/pdfinfo/tesseract`，缺失自动降级。
   不生成自造评分、golden_standard、模拟 benchmark；不把不确定当事实。

## 1. 触发条件与标准调用

适用：科研论文 PDF 阅读、全文提取、多栏顺序还原、章节结构识别、表格解析、公式/特殊字符提取、扫描件 OCR 降级、
基于证据的问答、翻译、实体/参数提取、参考文献核验、结构与原文核验。

```bash
# 首选：单命令全流程，内部 init → build → selfcheck
python3 -B /skills/weekly-skill/scripts/main.py run \
  --input /input --output /app/output --work /app/work

# 如果 Skill 被装在当前目录或脚本路径不同
cd /skills/weekly-skill 2>/dev/null || true
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work

# 查看可用命令
python3 -B /skills/weekly-skill/scripts/main.py --help
```

路径约定：

| 路径 | 用途 |
|-|-|
| `/input` | 原始输入：`case.json`、`task.md`、材料 PDF/图片/CSV/XLSX/DOCX/JSON |
| `/app/work` | 工作目录：台账、候选块、冲突组、`draft.json`、页级提取 |
| `/app/output` | 最终产物：必须含 `result.json` 及契约要求文件 |
| `/skills/weekly-skill` | Skill 安装根目录 |

## 2. 两段式工作流：Agent-first + 确定性兜底

### 2.1 `init`：先盘点，不急着写答案

```bash
python3 -B /skills/weekly-skill/scripts/main.py init \
  --input /input --output /app/output --work /app/work
```

`init` 必须产出：

- `/app/work/ledger.json`：任务契约、材料清单、来源编号、候选抽取项、冲突分组；
- `/app/work/sources.json`：所有材料文件与 `S#` 来源编号；
- `/app/work/candidates.json`：候选块、表、图、公式、参考文献、页眉页脚等；
- `/app/work/conflicts.json`：疑似冲突/跨栏/跨页/OCR 异常候选；
- `/app/work/pages/`：单页文本与可视化定位辅助文件。

Agent 在 `init` 后必须真实阅读：

1. `/input/case.json`、`/input/task.md`；
2. `/app/work/ledger.json` 与 `/app/work/sources.json`；
3. 原始 PDF 的关键页码或 `document.md`/候选文本；
4. 不用文件名或领域标签猜测内容。

### 2.2 Agent 路径：写 draft.json 后 check → build

如果预算允许，Agent 应写 `/app/work/draft.json` 以提高质量。

```bash
# 1) init 后阅读台账与原文，完成判断
python3 -B /skills/weekly-skill/scripts/main.py init \
  --input /input --output /app/output --work /app/work

# 2) 按 references/guide.md 形状写 /app/work/draft.json

# 3) 校验 draft 中的 quote、locator、来源是否可回溯
python3 -B /skills/weekly-skill/scripts/main.py check \
  --input /input --output /app/output --work /app/work \
  --draft /app/work/draft.json

# 4) 校验通过后生成最终产物
python3 -B /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work \
  --draft /app/work/draft.json
```

`draft.json` 至少包含：

```json
{
  "case_id": "原样",
  "field_answers": {"<output_contract 字段名>": "回答或结构化内容"},
  "claims": [
    {
      "claim_id": "C1",
      "kind": "qa|table|formula|figure|reference|extraction|translation",
      "text": "结论/答案/译文/结构文字",
      "sources": ["S1"],
      "quote": "逐字原文片段",
      "locator": "文件名#页码/段落号",
      "confidence": "high|medium|low"
    }
  ],
  "tables": [],
  "figures": [],
  "formulas": [],
  "missing": [],
  "pending_human": []
}
```

完整形状以 `/skills/weekly-skill/references/guide.md` 为准。

### 2.3 无 draft 时确定性兜底

如果时间不足，或 Agent 未写 `draft.json`，仍执行：

```bash
python3 -B /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work
```

`build` 必须使用 `init` 台账确定性抽取，生成实质工作稿，包括：

- 阅读顺序修正后的正文；
- 章节树；
- 表格 Markdown/HTML；
- 公式编号与符号文本；
- 图表题注和位置；
- 参考文献条目；
- 逐字 quote 与 locator。

同时必须在 `degradations`/`gaps` 中记录：

```json
{
  "code": "AUTO_EXTRACT_FALLBACK",
  "detail": "No agent draft.json supplied; deterministic extraction was used for baseline deliverables.",
  "affected_fields": ["<未完成高级任务的字段>"]
}
```

两条路径最终产出同一套产物和同一份 `result.json`，只是 Agent 路径通常在任务完成度、正确性与可核验性上更好。

## 3. 输出文件清单与 result.json 契约

### 3.1 标准产物

| 文件 | 必需 | 内容 |
|-|-|-|
| `result.json` | 是 | 主状态、契约回显、来源、不确定性、errors/degradations/changes/artifacts |
| `document.md` | 是 | 阅读顺序修正后的可读全文，带 `<!-- page:N -->`、`[p.N]`、`[S#]` 定位 |
| `document.json` | 是 | 页 → 块 → 行/词坐标的结构化模型 |
| `blocks.csv` | 是 | 块级清单：page, block_id, type, section, bbox, text 摘要 |
| `tables.csv` | 是 | 表格：table_id, page, caption, rows, cols, markdown/HTML, confidence |
| `figures.json` | 是 | 图编号、题注、页/坐标、是否可提取预览 |
| `formulas.json` | 是 | 公式编号、页/坐标、符号文本、是否失真/低置信 |
| `references.json` | 是 | 参考文献条目与来源定位 |
| `evidence_table.json` | 是 | claim_id → source_id → quote/locator/confidence |
| `claims.json` | 是 | 逐句声明式证据，禁止无来源论断 |
| `checks.json` | 是 | 质量门：quote 命中率、串栏检测、表格重构、公式保真、缺失区块 |
| `report.md` | 是 | 方法、边界、可复现步骤、异常说明、与基础 Agent 对比的改进证据 |
| 契约要求文件 | 条件 | 若 `output_contract` 要求 docx/pptx/xlsx/svg 等，则生成并额外渲染 PDF/PNG 预览 |

### 3.2 `result.json` 结构

```json
{
  "skill": {"name": "paper-pdf-evidence-parser", "version": "2.0.0"},
  "case_id": "原样",
  "status": "ok|partial|insufficient_evidence|input_error",
  "<output_contract 字段>": "按任务填写，无法完成填 null/[] 并标 missing",
  "output_contract": {
    "case_id": "原样",
    "<output_contract 字段>": "与顶层同值"
  },
  "contract_backfill": {"filled": [], "missing": [], "unknown_kept": []},
  "document": {},
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

注意：

- `output_contract` 是原始契约的完整镜像，字段名不能改；
- `case_id` 在顶层和 `output_contract` 内都要有；
- 无法完成的契约字段必须填 `null`/`[]`，并在 `contract_backfill.missing` 与 `pending_human` 说明原因；
- `status` 为 `partial` 时必须有明确的 `limitations`/`pending_human`/`errors`。

## 4. 分步执行指南

### 步骤 0：先运行 init，不要直接答

```bash
python3 -B /skills/weekly-skill/scripts/main.py init \
  --input /input --output /app/output --work /app/work
```

读取并核实：

- `case_id` 与 `output_contract` 全部键；
- 材料清单与 `S#` 编号；
- 任务要求与评分侧重；
- 材料边界、疑似冲突、未报告项。

### 步骤 1：优先完成高权重实际效果产物

1. 阅读 `document.md`/候选人块/页级提取；
2. 核验多栏顺序：双栏不串栏、不把页眉页脚混入正文、跨页续接正确；
3. 核验表格行列、合并单元格和多层表头；
4. 核验公式编号、上下标、希腊字母是否保真；
5. 核验图表题注、参考文献、脚注是否齐全；
6. 按 `output_contract` 逐字段写 `/app/work/draft.json`。

### 步骤 2：check → build

```bash
python3 -B /skills/weekly-skill/scripts/main.py check \
  --input /input --output /app/output --work /app/work \
  --draft /app/work/draft.json

python3 -B /skills/weekly-skill/scripts/main.py build \
  --input /input --output /app/output --work /app/work \
  --draft /app/work/draft.json
```

如果 `check` 发现 quote/locator 不匹配：

- 先回原文核验；
- 调整 `draft.json` 中来源、quote、locator；
- 不要在最终 JSON 里手工改证据。

### 步骤 3：selfcheck

```bash
python3 -B /skills/weekly-skill/scripts/main.py selfcheck \
  --input /input --output /app/output --work /app/work
```

必须核对：

- 契约字段是否全部出现且类型正确；
- `result.json` 顶层与 `output_contract` 是否双回显；
- 每个关键结论是否有来源和 locator；
- `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 是否真实；
- `artifacts` 中的文件是否真实存在；
- `status` 是否诚实。

### 步骤 4：收尾

1. 确保 `/app/output/result.json` 可用 `json.loads` 解析；
2. 清理 `__pycache__`、`.pyc`；
3. 不删除任何契约要求文件；
4. 如果时间不足，保留当前 partial 并显式标注 truncation。

## 5. 证据与来源规则

1. 来源编号：每个材料文件在 `init` 中分配 `S#`，并在 `sources` 列出。
2. locator 至少包含 `文件名#页码/段落号`；结构化块尽量加 `块号/坐标`。
3. `quote` 必须逐字取自 `document.md` 或页级提取文本；OCR 低置信处标 `quote_status=approximate`。
4. 结论分为：`reported`、`not_reported`、`conflict`、`unverifiable`。
5. 材料缺失、无法判定、冲突，必须落入 `uncertainty` 或 `pending_human`，禁止写成事实。
6. 对“页眉页脚/脚注”必须在文档/块分类中分离，不混入正文。

## 6. 隐藏案例鲁棒性

| 场景 | 应对 | 记录字段 |
|-|-|-|
| 正常 PDF | 完整 init → Agent draft → check → build → selfcheck | `runtime.caps` |
| 边界案例：多栏、跨页表格、复杂公式、扫描页 | 使用脚本阅读顺序修正、表格重建、公式区提取；Agent 重点核验 | `checks` |
| 异常：加密 PDF | 尝试空白密码；失败则标 `insufficient_evidence` | `errors`, `pending_human` |
| 无文字层扫描件 | `pdftoppm` + `tesseract` 若可用；否则标 UNDETERMINED | `degradations`, `pending_human` |
| 字体乱码/缺 ToUnicode | 保留原始块，该块 `garbled`，不进入关键 claims | `uncertainty` |
| 页码错乱 | `page_index` 与 `page_label` 分列，按物理页序为主 | `changes` |
| 单页解析失败 | 只降级该页，其余继续 | `errors` |
| 输入无材料/坏 JSON | 生成 `status=input_error` 的合法 result.json，退出 0 | `errors` |
| 输出目录不可写 | 回退 `/app/work` 或 `/tmp/output`，尽量复制回 `/app/output` | `degradations` |
| 超时 | 执行 `selfcheck` 前先落盘 partial，写明截断页 | `runtime.truncated_pages` |

**任何情况下：合法 `result.json` + 退出码 0 + 诚实状态。**

## 7. 预算策略：64 模型请求 / 900 秒 / 16384 tokens

| 阶段 | 模型请求预算 | 说明 |
|-|-|-|
| init + 阅读台账 | 2–4 | 读 case.json/task.md/ledger/sources |
| 关键原文核验 | 6–12 | 选关键页、表格、公式、题注、参考文献 |
| 写 draft.json | 10–20 | 优先高权重字段 |
| check/build/selfcheck | 2–4 | 脚本运行，不占高模型请求 |
| 最终收尾 | 2–4 | 检查 result.json 与产物一致性 |
| 余量 | 4–8 | 处理意外返工 |

优先级：

1. 实际效果：完成度、正确性、完整性、可核验性；
2. 使用增益：清晰记录质量门、单命令、无人工步骤；
3. 创新增益：记录阅读顺序修复、表格重建、公式区域、OCR 降级策略；
4. 生态贡献：文档齐全、示例、限制说明。

当剩余时间小于 120 秒，或模型请求接近 60 次时：

- 冻结优化；
- 运行 `selfcheck`；
- 保留 partial；
- 退出 0。

## 8. Rubric 高分散点 → 产物证据

| Rubric 维度 | 分数 | 可检查证据 |
|-|-|-|
| 实际效果 40 | 任务完成 15 / 正确 15 / 完整 5 / 可核验 5 | 每个契约字段有实际内容；claims 有逐字 quote；blocks/tables/formulas/figures/references 完整；每个关键项有 locator |
| 使用增益 25 | 质量 15 / 效率 5 / 可验证 5 | `checks.quality_gates`；`runtime.elapsed_s`；单命令；`checks.json` 可重跑；`report.md` 对比说明 |
| 创新增益 15 | 新增能力 5 / 方法改进 5 / 创新证据 5 | `report.md` 描述阅读顺序、表格重建、公式、OCR；`degradations`/`runtime.caps` 说明边界与方法 |
| 可靠体验 10 | 易用 3 / 稳定 4 / 异常 3 | SKILL 本文件 + `--help`；退出码 0；分页 try/except；异常降级记录 |
| 生态贡献 10 | 文档 3 / 复用 4 / 分享 3 | `SELFTEST.md`、`environment/resources.yaml`、`references/guide.md`；纯标准库脚本；`report.md` |

## 9. 生态与可复用资源

提交包内应有：

- `SKILL.md`：本说明；
- `scripts/main.py`：生命周期命令 `run|init|check|build|selfcheck`；
- `scripts/pdfcore.py`：纯标准库解析核心；
- `SELFTEST.md`：本地自检清单与预期输出；
- `environment/resources.yaml`：运行资源入口声明；Bundled files 相对该目录；声明 Python 版本与可选二进制；
- `references/guide.md`：`draft.json` 完整形状、工作流示例、常见失败处理；
- `GITHUB_URL.txt`：如需 GitHub 附加分，放在提交根路径第一行。

要求：

- Python >= 3.8；
- 仅标准库；
- 离线；
- 无 symlink；
- UTF-8 文本文件 ≤50 个，单文件 ≤500KB，总大小 ≤2MB。

## 10. 禁止事项

1. 禁止手改 `result.json` 的结构化契约键；
2. 禁止无来源结论；
3. 禁止编造材料中不存在的页码、DOI、数据、统计量、图元素；
4. 禁止假设文件名或领域标签等于内容；
5. 禁止制造自评分、golden_standard、模拟 benchmark；
6. 禁止忽略异常而假装成功；
7. 禁止删除契约字段；
8. 禁止让脚本异常导致 nonzero 退出；所有错误必须在 `errors` 中记录。

## 11. 最小可执行检查清单

- [ ] `init` 后已阅读 case.json、task.md、ledger.json、sources.json；
- [ ] 已写 `/app/work/draft.json` 或明确使用 AUTO_EXTRACT fallback；
- [ ] 已运行 `check` 且无未解决的 quote/locator 错误；
- [ ] 已运行 `build` 生成完整产物；
- [ ] 已运行 `selfcheck`；
- [ ] `result.json` 中包含 `case_id`、原 `output_contract` 全部字段、`output_contract` 嵌套镜像；
- [ ] 所有关键结论有 `S#`、locator、quote 或未报告声明；
- [ ] 异常、缺失、冲突、降级已记录；
- [ ] 退出码 0。