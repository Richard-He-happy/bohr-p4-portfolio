---
name: academic-format-template-adapter
description: 把一份真实稿件按给定模板/格式要求（期刊投稿要求、学位论文规范、docx 模板）重新排版：从模板文件与格式要求中抽取可逐项核对的 32 项规格（字体/字号/行距/页边距/栏数/标题层级/题注位置/三线表/参考文献样式/页脚页码），产出可编辑 docx + markdown + format_spec.json + fidelity_report.json + 真实 PDF 预览 + result.json。当任务涉及"按模板排版""套用格式要求""检查格式是否合规""学位论文/期刊格式适配""只改格式不改内容"时使用；纯写作、润色、翻译、文献综述不要用它。
version: 3.0.0
---

# 学术格式与模板适配 v3（Agent 判断规格 + 脚本确定性落版 + 兜底必成）

## 1. 用途与边界

**做**：识别输入里的「原稿」与「格式要求/模板」（docx / pdf / md / txt / tex），把格式要求拆成 **32 项可逐项核对的规格**，把规格真实写进 OOXML（style + sectPr + footer 域），交付可编辑 `deliverable.docx`、`deliverable.md`、`format_spec.json`、`fidelity_report.json`、`preview.pdf`、`result.json`。

**不做**：不改写、润色、翻译、增删文献、重排题注编号；不做学术判断。正文/数字/引用标记**逐字搬运**，只改格式。

**判定基线**：`fidelity_report.json.summary.verbatim_ratio = 1.0` 且 `numbers_preserved`/`citations_preserved` 为 `true`；`format_spec.json` 每条 `explicit` 都能在原文找到逐字 `quote`。

## 2. 运行契约

- 输入 `/input/case.json`（键名不固定）+ `/input/task.md` + 材料；工作目录 `/app/work`；产物 `/app/output`。
- 只用 Python 标准库；不联网；脚本用 `Path(__file__)` 定位，**与 CWD 无关**；**无任何外部资源依赖**（OOXML 全部写在脚本里，缺 `references/` 也能跑）。
- 退出码**恒为 0**；任何异常都捕获进 `result.json.errors`，并 finalize。
- 目录可用 `--input/--work/--out` 或 `SKILL_INPUT_DIR/SKILL_WORK_DIR/SKILL_OUT_DIR` 覆盖。
- 可选外部工具（`shutil.which` 探测，缺失即降级）：`soffice/libreoffice`（PDF 预览）、`pdftotext`（PDF 取文）、`pdffonts`（字体嵌入证据）。

## 3. 输入发现（语义识别，不假设键名、不假设文件名）

1. 递归扫描 `<input>/**`（≤80 文件，跳过 `output`/`work`/隐藏目录），按**魔数 + 扩展名**判类型：`%PDF`→pdf、`PK`+`word/document.xml`→docx、图片签名→image。
2. `case.json` 缺失或非法 JSON → 记 `errors[stage=case]`，改用目录扫描 + `task.md` 继续。
3. **原稿判定**：字符量 × 类型权重（docx×1.3）；文件名含 `templ|模板|requir|format|spec|要求|须知` 降权 95%；自身挖到 ≥3 条规格的降权到 30%。结果写 `work/index.json` 的 `manuscript`。
4. **格式来源判定**：除原稿外，任何挖出规格的材料都算格式来源，按条数排序；同一字段多个取值 → 记 `conflicts`（保留首个来源的值，双方 locator 都留档）。
5. 材料没给的对象一律进 `pending_human`，不猜、不补。

## 4. 核心流程（严格按序）

### 第 0 步：你（Agent）先读材料

读 `case.json` 的 `task_instruction`/`output_contract` 与格式要求全文。不要凭经验假设字号行距——**所有规格都要落到原文某一行**。
```bash
python3 scripts/main.py show --input /input --work /app/work --material m03 --from 1 --to 60
python3 scripts/main.py show --input /input --work /app/work --material m02 --items
```

### 第 1 步：`init` —— 建索引 + 打印「格式要求清单」+ 立刻落盘 partial result.json

```bash
python3 scripts/main.py init --input /input --work /app/work --out /app/output
```
打印内容：案件与 `output_contract` 键、材料表（角色/块数/字符数/挖到的规格条数）、**32 项规格清单**（候选值 / 来源 / locator / 逐字 quote，未给出的明确标 `NOT STATED`）、冲突项、原稿前 36 段（带 locator）。
同时写出 `work/index.json`（后续唯一数据源）、`work/spec_table.draft.json`（预填骨架）、`out/result.json`（合法 partial）。

### 第 2 步：你写 `work/spec_table.json`（本 Skill 的核心，脚本不替你做判断）

逐条核对 `init` 的清单：`explicit` 必须带**逐字 quote**；材料没写的项保留默认值并允许 `inferred`；互相矛盾的写进 `notes`。

```json
{"case_id": "…",
 "spec": [
  {"field": "body.font", "value": "Liberation Serif", "source": "m02",
   "locator": "m02#L0005",
   "quote": "3. Body text: Liberation Serif, 12 pt, 1.5 line spacing, justified."},
  {"field": "page.margin.left", "value": "3.0cm", "source": "m02",
   "locator": "m02#L0004",
   "quote": "2. Page margins: 2.5 cm top and bottom, 3.0 cm left and right."}
 ],
 "notes": "toc not required by this journal; figure images not present in source"}
```
规则：
- `field` 只能取第 6 节的 32 个字段名；`value` 可写 `12pt`/`2.5 cm`/`小四`/`below`，脚本会规范化。
- `quote` 必须**逐字**出现在源文件里（空白差异可忽略）。查不到 → 该条被拒收并记 `degradations`，绝不改原文凑通过。
- 有 `quote` = `explicit`；无 `quote` = `inferred`（沿用你的值，但仍计入不确定性）。
- 只有 `spec_table.json` 会被当作**已确认**；`spec_table.draft.json` 只是骨架，用它跑 `build` 结果最多 `partial`。

### 第 3 步：`check`

```bash
python3 scripts/main.py check --input /input --work /app/work --out /app/output
```
11 项：索引/原稿存在、规格表存在、32 字段齐全、explicit ≥8、quote 逐字命中率、块数、标题数、verbatim 1.0、数字保留、引用保留。结果写 `work/check_report.json`，逐条 PASS/FAIL。**FAIL 先修规格表**（quote 未命中 → 用 `show` 复制原文；数字丢失 → 说明你改动了内容）。

### 第 4 步：`build` —— 无条件 finalize

```bash
python3 scripts/main.py build --input /input --work /app/work --out /app/output
```
产出：`deliverable.docx`（可编辑，style 绑定）、`deliverable.md`、`format_spec.json`、`fidelity_report.json`、`preview.pdf`（有 LibreOffice 时）、`result.json`。
兜底顺序（任一步失败都不中断）：
1. 有 `spec_table.json` → 逐条校验后应用；
2. 无/坏规格表 → 用挖掘到的规格 + 默认值确定性落版，`status=partial`，并进 `pending_human`；
3. 原稿不可解析 → 写「说明文档」（非空、可打开），`status=insufficient_evidence`；
4. docx 写入异常 → 立即用默认规格重写一次最小 docx，错误入 `errors`。

## 5. 输出契约（`result.json`）

- **原样回填** `output_contract` 全部键（同名同数、不改名、未知键保留，缺值 `null`，缺失键补 `null` 并记 `degradations`）。
- 必有：`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`artifacts`、`deliverable`、`export_artifact`、`coverage`、`fidelity`、`compliance_checks`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- `status=ok` 仅当：规格表已确认、docx 存在、verbatim 1.0、数字与引用零丢失、explicit ≥ 50%、无 errors。其余一律 `partial` 并写清缺口。

## 6. 32 项规格字段（`format_spec.json.fields[].field`）

`page.size` `page.margin.top/bottom/left/right` `page.columns` `body.font` `body.font.eastasia` `body.size` `body.line_spacing` `body.align` `body.first_line_indent` `title.size` `heading.1.size` `heading.1.emphasis` `heading.1.font` `heading.2.size` `heading.2.emphasis` `heading.2.font` `heading.3.size` `heading.3.emphasis` `heading.3.font` `heading.numbering` `caption.size` `caption.figure.position` `caption.table.position` `table.style` `reference.style` `reference.hanging` `footer.page_number` `page.header` `toc.levels`

规范值：`page.size`=A4/A3/A5/Letter；边距=`2.50cm`；`body.size`=`12`（pt 数字）；`body.line_spacing`=`1.5` 或 `20pt`；`body.align`=both/left/center/right；`body.first_line_indent`=`0cm`/`2chars`；`heading.N.emphasis`=bold/bold italic/italic/none；`heading.N.font`=`inherit` 或字体名；`caption.*.position`=above/below；`table.style`=three-line；`footer.page_number`=center/right/left/none；`toc.levels`=0-3。

## 7. 证据与定位规范

- 每条规格带 `material@locator` + 逐字 `quote`：文本材料 `m02#L0005`（原始行号），docx 模板 `m01#sectPr/pgMar@top`、`m01#styles.xml[Normal]/sz`（quote 为该 OOXML 属性原文），PDF 为 pdftotext 行号。
- `check`/`build` 用去空白后的子串比对验证 quote；**未命中即拒收**，不近似匹配。
- 保真按「内容单元」计：段落文本、题注、表格行；数字与引用标记（`[1]`、`[2,3]`、`(Zheng et al., 2018)`、`Figure 1`、`DOI/URL`）单独计数比对。

## 8. 冲突与人工确认

同一字段多个不同取值 → `format_spec.json.conflicts` + `uncertainty`，保留优先来源（docx 模板 > tex 模板 > 格式要求文本；同源先出现者），另一方 locator 留档。
字段无出处 → 默认值 + `status=inferred` + 逐条 `uncertainty`。无法安全判断（如"参考文献样式只写了 GB/T 7714 未给版本"）→ `pending_human` 并给出可执行动作。

## 9. 预算与断点

64 次模型请求 / 900 秒。建议：`init`（约 3 s）→ 至多 4 次 `show` 核对 → 写 1 次规格表 → `check` → `build`（含 PDF 约 4 s）。> 780 s 立即 `build`：即使规格表未写完也会产出合法 partial 结果。重复运行幂等，同名产物覆盖；`result.json` 在 `build` 开头先写 partial，结束再覆盖。

## 10. 异常降级分支

| 情况 | 行为 | 记录 |
|---|---|---|
| `/input` 为空 | 仍产出 md/docx/spec/fidelity/preview，退出 0 | `status=insufficient_evidence`、`degradations` |
| `case.json` 非法 JSON | 目录扫描 + `task.md` 继续，仍出全产物 | `errors[stage=case]` |
| 无 `output_contract` | 只写 Skill 原生字段 + `uncertainty` | `uncertainty` |
| 规格表缺失/坏 JSON | 确定性落版，`status=partial` | `degradations`、`pending_human` |
| 规格 quote 不命中 | 拒收该条，回退挖掘值/默认值 | `degradations[stage=spec]` |
| 无格式要求 | 全套默认规格（题面字体 Liberation Serif） | 每条 `status=inferred` |
| 无 LibreOffice | 保留 docx/md，另写 `preview.txt`，`export_artifact=null` | `degradations[stage=preview]` |
| 单材料解析失败 | 只降级该材料 | `sources[].read_note` |
| docx 写入异常 | 用默认规格重写最小 docx | `errors[stage=docx]` |

## 11. 自检清单（交付前逐条打勾）

- [ ] `python3 -B scripts/main.py --help` 退出码 0。
- [ ] 空 `/input`：`out/` 有 md+docx+2 个 json，`result.json` 合法，退出码 0。
- [ ] 契约：`set(output_contract) ⊆ set(result.json)`，`status` 属于四个枚举值。
- [ ] `format_spec.json.fields` 32 条，每条有 `value/status`，`explicit` 都有 `quote` + `locator`。
- [ ] `fidelity_report.json.summary.verbatim_ratio == 1.0`，`numbers_preserved`/`citations_preserved` 为 true。
- [ ] `deliverable.docx` 可被 `zipfile` 打开，含 `word/document.xml`、`word/styles.xml`、`word/footer1.xml`；正文 run 带 `w:rFonts`（字体真进了 run，不只是 style）。
- [ ] `preview.pdf` 存在时页数 ≥1，`pdffonts` 显示字体嵌入。
- [ ] 无 `__pycache__`、`.pyc`、临时文件。

## 12. 最小调用示例（**示例，非正式案例结果**）

```bash
# 输入样例：sample/input/{case.json, format_requirements.md, manuscript.md, journal_template.docx}
python3 scripts/main.py init  --input sample/input --work sample/work --out sample/output
#   -> 3 个材料；m02 挖到 23 条规格；打印 32 项清单；out/result.json (partial)
# 你写 sample/work/spec_table.json（24 条 explicit + 8 条 inferred）
python3 scripts/main.py check --input sample/input --work sample/work --out sample/output
#   -> verdict ok | explicit 24/32 | quotes 24/24 | verbatim 1.0
python3 scripts/main.py build --input sample/input --work sample/work --out sample/output
#   -> status ok；A4、上/下 2.50cm、左 3.00cm、右 3.00cm、单栏、Liberation Serif 12pt/1.5、
#      标题 14/12/12pt(bold / bold italic / italic)、题注 10pt（图下/表上）、三线表、
#      页脚居中 PAGE 域；compliance_checks 12/12 pass；preview.pdf 2 页
```
示意输出仅说明接口，不是任何官方案例的结果。

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（流程、字段、降级、自检） |
| `scripts/main.py` | `init/show/check/build`、索引与规格合并、合规读回、result.json |
| `scripts/docxlib.py` | 材料解析（md/txt/docx/pdf/tex）、32 字段挖掘、保真度量、OOXML 写入与读回探针、PDF 预览 |
| `references/format_spec_schema.md` | 32 字段取值/单位/默认值 + 规格表 schema |
| `references/checklist.md` | 12 项合规检查判定口径 + 降级分支 + 复核方法 |
| `references/example-trial.md` | 试跑记录（标注为示例） |

依赖：Python ≥3.8 标准库；可选 LibreOffice/pdftotext/pdffonts。版本 3.0.0；字体默认 Liberation Serif（题面 revision3）。

## 14. 维护说明

- 新增字段：`docxlib.ORDER` + `DEF` 各加一行、在 `mine()` 加抽取规则、在 `GM()` 加落版换算，四处同步；`format_spec_schema.md` 补一行。
- 新增模板语法：只扩 `mine()`/`tpl()`，保持返回结构 `{field,value,source,locator,quote}` 不变。
- 改版式：只改 `styles()`/`build_docx()` 的 OOXML 片段，不动挖掘。
- 回归：先 `--help`，再跑「空输入」与「原稿+格式要求」两类输入，确认 `verbatim_ratio=1.0` 且 `compliance_checks` 全 pass。
