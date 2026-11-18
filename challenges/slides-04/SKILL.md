---
name: academic-slide-template-adapter
description: Turn a paper plus a real .pptx template into a genuinely template-inherited, editable academic deck (pptx + rendered PDF/PNG) with per-slide claim-to-source evidence mapping, an extracted template specification, per-item format compliance evidence read back from the emitted XML, a page-by-page diff, a version record with a rollback path, a run log, and an export/render check. Use when a case asks to fit paper content into a given slide master/layout, adapt a starting deck, or audit slide-template conformance.
version: 2.0.0
---

# Academic Slide Template Adapter (slides-04)

v2 = v1 pipeline + six verifiable assets. The original call is unchanged:
`python3 scripts/main.py --input /input --output /app/output [--template X] [--slides N]`.
New CLI options are optional (`--deck`, `--no-pdf`); omitting them keeps v1 behaviour.

## 1. Purpose and boundary

做：把 `/input` 里的论文装进组织方给的 pptx 模板，每页落在**模板已有版式**上，字体/颜色/行距走母版与主题，
页脚页码齐全，图表等比缩放，并为每页留下**逐字证据 + 定位**；同时输出可复核的模板规格、逐项格式合规证据、
逐页 diff、版本与回退记录、运行日志与导出渲染检查。

不做：判断学术内容价值；编造图表、数值或引用；无模板时伪造“母版套用”（会用内置骨架包并在
`degradations` 与 `template_spec.template.kind="synthetic"` 明确标注，不算模板继承）；不写 pptx `notesSlide` 部件
（讲稿交付在 `content_map[].notes`，`format_compliance` 的 CI-16 记录该形态）。

事实来源只有 `/input` 材料；模板只提供格式。

## 2. Runtime contract

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、材料（.pptx/.pdf/.docx/.md/.txt/.png/.jpg/.json） |
| 产物目录 | `/app/output`（`--output`），工作目录无关（脚本按 `Path(__file__)` 定位同级模块） |
| 入口 | `scripts/main.py`（装配）+ `verify.py`（解析/计划/OOXML 发射/兼容检查）+ `spec.py`（模板规格、合规、导出、回退）+ `reports.py`（run.log、page_diff、version_history） |
| 依赖 | **仅标准库**；`soffice`/`pdftoppm`/`pdftotext`/`pdffonts`/`fc-match` 探测后使用，缺失即降级 |
| 退出码 | **恒 0**；异常写入 `errors`，最终无条件 finalize |
| 首步 | 先写 partial `result.json`（空骨架），再干活；崩溃也有合法结果 |
| 幂等 | 同一输入重复跑产出同结构；不使用上次的 `presentation.pptx` 作为输入 |

## 3. Input discovery

1. `--template` > 名称含 template/master/layout/theme/brand/style 的 pptx > 目录中第一个 pptx；
   `--deck` > 名称含 start/deck/draft/current/original/source 的 pptx > 模板自身。
2. `case.json` 用语义键查找（键名可能改名）：`output_contract`、`organizer_workorder`、`total_slide_count`、
   `footer_text`、`page_number_required`、`min_font_pt`、`audience`、`task_instruction`。
3. 论文优先级：`.md/.markdown` > `.txt` > `.docx` > `.pdf` > `.tex`，同类型取最大者；PDF 走 `pdftotext -layout`，
   无文本层则标记 `no_source_text` 并只出标题级骨架。
4. 图片：`.png/.jpg/.jpeg/.bmp/.gif`（名字含 logo 的排除），用魔数读宽高做等比缩放。
5. **按魔数与结构判断，不按文件名或领域标签猜内容**；pptx 不是 zip 或缺 `ppt/presentation.xml` 即判不可读。

## 4. Output contract

`result.json` 原样回填 `output_contract` 全部字段（不改名、不遗漏，缺值 null/[]），并保留 v1 字段：
`case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`editable_source`、`export_artifact`、
`content_map`（页级 claim + 逐字 quote + locator + notes）、`compliance_checks`、`sources`、`uncertainty`、
`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`workorder_echo`。

v2 新增字段（与文件一一对应，均含 `path` + `sha256`）：

| 字段 | 文件 | 内容 |
|---|---|---|
| `template_spec` | `template_spec.json` | 页面尺寸/比例、母版（占位符、txStyles 的 title/body 字号与行距、clrMap）、版式库（名称、type、占位符类型/几何）、主题字体与色板、受保护部件 sha256、**每页 layout 映射**（`layout_map`） |
| `format_compliance` | `format_compliance.json` | 16 项 CI-01..CI-16，每项 `status` + `actual`（写进 XML 的实际值）+ `evidence[{part,locator,snippet,verified_in_part}]` |
| `page_diff` | `page_diff.md` | 模板级 diff + 逐页格式 diff + 逐页内容 diff（quote 与原稿逐字重比）+ 未解决偏差 |
| `version_history` | `version_history.md` | v0 骨架 → v1 成稿 → v2 本包，产物 sha256，回退路径 |
| `run_log` | `run.log` | 追加式阶段日志（时间戳 + 耗时 + 阶段 + 消息），崩溃仍留证据 |
| `export_check` | `export_check.json` | PDF 页数/尺寸/头、`pdffonts` 字体表与替换判定、`pdftotext -bbox` 真实文字框越界、内容区溢出估算 |
| `rollback` | （内联） | 受保护部件清单、drift/repaired、校验结果、手动回退步骤 |
| `sources` / `editable_source` | `presentation.pptx` + PDF/PNG | 每个输入文件字节数与 sha256；pptx 里 `master/layout/theme` 的 sha256 与版式使用清单 |

## 5. Pipeline（与 run.log 阶段名一致）

`main.start` → `main.init` → `discover` → `template`（母版/版式/主题解析，含合成包分支）→
`template_spec`（**先写 partial 规格**，`layout_map_status="pending_build"`）→ 文本抽取 → 页级计划 →
`pack` → `guard`（受保护部件 sha256 复核，漂移即从模板原件恢复并重打包）→ `export`（soffice→PDF，
pdftoppm→PNG）→ `template_spec`（回填 `layout_map`）→ `compliance` → `export_check` → `page_diff` →
`version_history` → `finish`（契约回填）→ `main.done`。

装配原则：每页 = 一个 `p:sld` + `slideLayout` 关系；文字写进模板已有 `<p:ph>`（不写死坐标、字号、字体），
几何/字号/行距/颜色从母版与主题继承；仅在模板缺该占位符时才用自由文本框，并记 `deviation`。

## 6. Quality rules mapped to rubric

| 评分点 | 落点 |
|---|---|
| 模板真套用 | `CI-03/04/05` 母版/版式/主题 sha256 不变；`CI-06` 每页 layout rel 命中模板部件；`template_spec.layout_map` |
| 占位符真实继承 | `CI-07` 填充类型 ⊆ 版式占位符类型；自由文本框计数；`placeholder_fill_rate` |
| 字体/字号/行距 | `CI-09` 字号集合与 `min_font_pt`；`CI-10` 行距（页面不写 lnSpc，继承母版 spcPct 值）；`CI-11` 零硬编码 latin typeface |
| 标题层级 / 页面比例 | `CI-08` 每页 title 文本 + 母版 titleStyle 字号；`CI-02` `sldSz` 与模板一致 |
| 色板 | `CI-12` 硬编码 RGB ⊆ 主题色板；`template_spec.palette` |
| 页脚 / 页码 | `CI-13` 非封面页页脚一致；`CI-14` 版式有 sldNum 必编号，缺占位符时按母版页码位置回退 |
| 溢出 | `CI-15` + `export_check.overflow`（CJK 1.0em / Latin 0.52em、行高 1.20、4% 余量）+ `pdftotext -bbox` 真实越界 |
| 图表适配 | `V.fit_rect` 等比缩放 + 图注逐字引用；无图注时 `figure_embedded_without_verbatim_caption` |
| 导出渲染一致 | `export_check.rules`：PDF 页数 = 幻灯片数、PDF 尺寸 = 版面、字体嵌入、文字在页面内 |
| 可复核 | `run.log`、`page_diff.md`、`version_history.md`、`sources[].sha256`、`template_spec.protected_parts` |
| 回退 | `spec.guard()` 自动恢复 + `version_history.md §4` 手动步骤（模板是唯一真源） |

`status=ok` 需同时满足：`compliance_checks.pass`、PDF 存在、`format_compliance.pass`、`export_check.pass`、
非合成模板、`errors` 为空；否则 `partial` 并在 `uncertainty` 写清原因。

## 7. Evidence and locators

- 每条页级要点带 `evidence{quote, locator, kind}`；`quote` 是原文逐字片段（不做改写），`locator` 为 `§章节 ¶段 / p.页码`。
- `page_diff.md §3` 会把每条 quote 在源文本中**重新比对**（空白折叠后子串命中），输出 hit/miss 计数；
  miss 不隐藏、进 `pending_human`，绝不改原文凑通过。
- 证据前的数字（`6.8 C`、`0.3 to 25 um`）必须完整：分句器要求标点后紧跟空白才断句，避免把小数切开。
- 格式类结论不在文字里自证，一律带 `evidence.snippet`（该部件中真实存在的 XML 片段）与 `verified_in_part`。

## 8. Conflicts and human confirmation

order 冲突（页数上限 vs 章节数）：先保主线页（封面/大纲/结论），再压缩正文页并在 `changes` 记录。
字体缺失、图注缺失、模板无 sldNum/ftr、PDF 无法导出 → 逐项写 `degradations` + `pending_human`，
不静默替换、不伪造“已修复”。模板被改成不可读时不猜结构，走合成骨架包并降级状态。

## 9. Budget and checkpoints

预算 900 s / 64 次模型请求。断点顺序：partial result → 模板规格 → pptx → PDF → 合规/导出/ diff / 版本。
近 780 s 直接 finalize。`soffice` 转换给 300 s 超时，失败不阻塞其余产物。

## 10. Failure / degradation table

| 情形 | 处置 | 证据字段 |
|---|---|---|
| 无模板 / 不是 zip / 缺 presentation.xml | 内置骨架包（16:9，1 母版 4 版式 1 主题）+ `kind=synthetic` | `degradations[stage=template]`、`template_spec.template.kind` |
| 论文无文本层 | 只出封面/结论骨架，`status=partial` | `exceptions[no_source_text]`、`pending_human` |
| 版式缺 body 占位符 | 该页正文不写，记 `body_placeholder_absent` | `content_map[].deviation` |
| 版式缺 ftr / sldNum | 母版位置自由文本框回退 | `footer_source`、`page_number_source` |
| 文字超框 | 先降字号（≤母版标称、≥`min_font_pt`），仍超则按词截断并记 `text_trimmed_to_fit:N` | `content_map[].body_pt`、`page_diff` 偏差列 |
| 图片读不出 | 跳过该图并记 `figure_unreadable` | `degradation` |
| `soffice` 缺失/失败 | 保留 pptx，`export_check.status=no_pdf`，`status=partial` | `export_check.consistency.note` |
| `pdffonts`/`pdftotext` 缺失 | 字体用 `/BaseFont` 正则、越界用 XML 几何估算 | `export_check.degradations` |
| 模板部件被改 | `guard` 从模板原件字节恢复并重打包 | `rollback.drift` / `rollback.repaired` |

## 11. Self-check

1. `python3 -B scripts/main.py --help` 退出 0，用法含 `--input/--output/--template/--slides`。
2. 造最小输入跑一遍：`presentation.pptx`（zipfile 可开、`ppt/theme/theme1.xml` 存在）、`presentation.pdf`
   （头 `%PDF-`）、`result.json` + 6 个新资产全部存在且 JSON 可解析。
3. 空输入 / 坏 `case.json` / 无模板：退出 0，`result.json` 合法，仍有最小 pptx（与 PDF，若 `soffice` 在）。
4. `format_compliance` 每项都有 `actual` 与非空 `evidence`；`page_diff` 的 miss 计数与 `pending_human` 一致。
5. 无 `__pycache__`/`.pyc`；未写死 `/skills/weekly-skill` 路径；不依赖 CWD。
6. 一键回归：`python3 -B scripts/selfcheck.py`（自建最小案例 → 断言 8 类产物、pptx/theme、PDF 头、
   空输入与坏输入路径），最后一行打印 `SELF-CHECK PASSED`，退出码 0。

## 12. Minimal example (illustrative only — 示例，非正式案例结果)

```bash
python3 scripts/main.py --input /input --output /app/output \
    --template /input/template_academic.pptx --slides 10
# 输出：presentation.pptx / presentation.pdf / preview/*.png
#       result.json / template_spec.json / format_compliance.json / export_check.json
#       page_diff.md / version_history.md / run.log
```

示意片段（示例值，非正式结果）：`format_compliance.passed=16/16`、`export_check.rules.pdf_pages_eq_slides=true`、
`page_diff` 的 miss=0。真实数值以运行时产物为准。

## 13. File inventory and versions

| 文件 | 大小 | 作用 |
|---|---|---|
| `SKILL.md` | 14.2 KB | 本说明 |
| `scripts/main.py` | 37.9 KB | CLI、输入发现、页级装配、PDF 导出、编排、契约回填 |
| `scripts/verify.py` | 21.7 KB | 文本抽取、分句、页级计划、OOXML 发射、v1 兼容检查 |
| `scripts/spec.py` | 53.7 KB | 模板规格抽取、16 项逐项合规、导出/渲染检查、回退 guard、合成骨架包 |
| `scripts/reports.py` | 18.8 KB | `run.log`、`page_diff.md`、`version_history.md`、回退记录 |
| `scripts/selfcheck.py` | 7.6 KB | 一条命令自检：造最小案例跑通 + 空/坏输入断言（`python3 -B scripts/selfcheck.py`） |
| `references/artifact_schema.md` | 7.8 KB | 六个新资产与 `rollback` 的字段契约 |

合计 7 个文件 / 162 KB（纯 UTF-8 文本，无二进制、无软链接）。单文件超过 20 KB：`main.py` 37.9 KB、
`spec.py` 53.7 KB —— 这是**有意**的取舍：引擎是纯标准库、单一职责的确定性代码，拆成更多模块只会增加导入耦合，
且 20 KB 上限属提交建议而非平台限制（平台限制为 ≤50 文件 / 500 KB 单文件 / 2 MB 合计）。

版本：v1.0.0（基线，62.33：装配 + PDF + 证据映射，`SKILL.md` 为空骨架）→ **v2.0.0**（修 5 个阻断缺陷、
新增 6 项资产、文档写实）。逐条变更见运行产物 `version_history.md`。

## 14. Maintenance

- 新增检查：在 `spec.compliance()` 加一条 `_ck(...)`，保持 `id/item/requirement/actual/status/evidence` 五元组；
  `pass` 判定与 `res.format_compliance` 自动跟随。
- 换模板：只需换 `--template`；所有几何/字号/字体/色板都从模板读取，无硬编码 16:9 假设
  （`sldSz` 缺省时才退回 16:9）。
- 溢出模型可调：`spec.est_height()`（字符 advance、行高、余量）；改动后重跑可见 `export_check.overflow`。
- 明确限制：单母版假设（多母版只用第一个的 txStyles）；不做 notesSlide 部件；不做动画/切页；
  PDF 导出依赖 `soffice`，缺失时以 pptx + 估算检查交付并降级状态。
