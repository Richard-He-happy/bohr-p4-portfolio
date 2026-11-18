# 试跑记录（示例，非正式案例结果）

> 本文件是一次**示例输入**上的真实运行记录，用于说明接口与产出形态。
> 输入由本文档作者构造，**不是**组织方固定案例，也不是任何官方评分结果。

## 1. 示例输入（sample/input/）

| 文件 | 内容 |
|---|---|
| `case.json` | `case_id: fmt-001`，10 个 `output_contract` 键，`task_instruction`："Apply the journal template requirements to the manuscript. Do not rewrite the text." |
| `format_requirements.md` | 9 条英文投稿要求：A4 单栏、上下 2.5cm 左右 3.0cm、Liberation Serif 12pt/1.5、三级标题 14/12/12pt(bold / bold italic / italic)、图题在下表题在上 10pt、三线表、APA 7th + 悬挂 0.5cm、页脚居中页码、题名 16pt |
| `manuscript.md` | 1 篇 21 段示例稿件：题名、Abstract、4 个一级章节 + 2 个二级小节、1 张三线表、Figure 1/Table 1 交叉引用、3 条参考文献 |

## 2. 调用与实测结果

```bash
python3 scripts/main.py init  --input sample/input --work sample/work --out sample/output
#   材料 3 个：case.json(material) / format_requirements.md(format_source, 挖到 23 条) / manuscript.md(manuscript)
#   打印 32 项规格清单：24 项有 locator+quote，8 项标 NOT STATED
#   out/result.json 立即落盘（status=partial）
python3 scripts/main.py check --input sample/input --work sample/work --out sample/output
#   verdict ok | explicit 25/32 | quotes 25/25 verified | verbatim 1.0 | blocks 20
python3 scripts/main.py build --input sample/input --work sample/work --out sample/output
```

`build` 实测输出（本次运行，字节数为实际值）：

| 产物 | 字节 | 说明 |
|---|---|---|
| `deliverable.docx` | 4264 | 可编辑；A4、页边距 2.50/2.50/3.00/3.00cm、单栏、行距 1.5；`Normal` 12pt、`Heading1/2/3` 14/12/12pt 带 outlineLvl 0/1/2；`Caption` 10pt；三线表；页脚居中 PAGE 域 |
| `deliverable.md` | 1983 | 同一内容的 markdown（标题层级、题注、管道表） |
| `format_spec.json` | 8352 | 32 条规格，25 `explicit` / 7 `inferred`，含 conflicts |
| `fidelity_report.json` | 3218 | verbatim 1.0；数字 63→63；引用 8→8；逐段 block_map |
| `preview.pdf` | 50485 | LibreOffice 导出，2 页，Liberation Serif 已嵌入 |
| `result.json` | — | `status: ok`；`compliance_checks` 12/12 pass；契约 10 键全覆盖、无 null |

规格抽样（`decided_by: script` = 脚本从要求原文挖出）：

| field | value | locator | quote（截断） |
|---|---|---|---|
| `body.font` | Liberation Serif | `format_requirements.md#L0005` | 3. Body text: Liberation Serif, 12 pt, 1.5 line spacing, justified. |
| `page.margin.left` | 3.00cm | `format_requirements.md#L0004` | 2. Page margins: 2.5 cm top and bottom, 3.0 cm left and right. |
| `heading.2.emphasis` | bold italic | `format_requirements.md#L0006` | 4. Section headings are numbered decimally: level 1 heading 14 pt bold, level 2 12 pt bold italic, level 3 12 pt italic. |
| `caption.table.position` | above | `format_requirements.md#L0007` | 5. Figure captions are placed below the figure, 10 pt, … Table captions are placed above the table, … |

`compliance_checks` 抽样（读回 docx 后的实测值）：

| id | expected | actual | status |
|---|---|---|---|
| C2 | top 2.50 / left 3.00 cm | `{top: 2.5, bottom: 2.5, left: 3.0, right: 3.0}` | pass |
| C4 | Liberation Serif | `Liberation Serif`（`runs_with_font/runs = 40/40`） | pass |
| C7 | 14/12/12pt | `[[14.0, 0], [12.0, 1], [12.0, 2]]` | pass |
| C12 | 无丢失 | numbers 63, citations 8 | pass |

## 3. 其他已跑通的输入形态

| 形态 | 结果 |
|---|---|
| docx 模板 + docx 原稿 | 从 `sectPr`/`styles.xml` 反推 15 条规格（A4、双栏、Times New Roman 11pt、1.15 行距、上下 2.00/1.80cm 左右 2.20cm、标题 15/13/11pt、题注 9pt、悬挂 0.50cm），全部写入成品 |
| 中文格式要求 + 中文原稿 | 23/32 explicit：宋体小四、1.5 倍、两端对齐、首行缩进 2 字符、一级黑体三号加粗/二级黑体四号/三级宋体小四、图题下表题上五号、GB/T 7714 悬挂 0.74cm、页脚居中、三线表；docx 内 `eastAsia=宋体/黑体`、`firstLine=480` twips |
| 坏 JSON 的 case.json | 仍出 6 个产物；`status=partial`；`errors[stage=case]` 记两处 |
| 空 `/input` | 出 md/docx/spec/fidelity/preview；`status=insufficient_evidence`；退出码 0 |
| 删掉 `references/` 目录 | 功能不受影响（无外部资源依赖），25/32 explicit、12/12、verbatim 1.0 |
| 只给草稿 `spec_table.draft.json` | 仍出全部产物，但 `status=partial`，`pending_human` 要求确认规格表 |
