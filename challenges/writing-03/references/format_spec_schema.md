# format_spec.json / spec_table.json schema（32 字段）

`work/spec_table.json` 由 Agent 写；`out/format_spec.json` 由 `build` 写。两者共用同一套 `field` 名。

## 1. 规格表（Agent 输入）

```json
{"case_id": "…",
 "spec": [{"field": "body.size", "value": "12pt", "source": "m02",
           "locator": "m02#L0005", "quote": "3. Body text: Liberation Serif, 12 pt, 1.5 line spacing, justified."}],
 "notes": "自由文本：冲突、假定、未覆盖要求"}
```

- `field`：下表字段名，写错会被忽略并记 `degradations`。
- `value`：宽松写法（`12pt`、`2.5 cm`、`小四`、`三号`、`1.5 倍`、`below`），脚本用 `canon()` 规范化。
- `source`/`locator`：`m02` 为 `work/index.json` 里的材料 id；`locator` 建议直接抄 `init` 打出的那串。
- `quote`：**逐字**原文片段。有 quote → `explicit`；无 quote → `inferred`。quote 归一化空白后必须能在源文件命中，否则整条拒收。

## 2. 字段表

| field | 取值 | 默认 | 说明 |
|---|---|---|---|
| `page.size` | A4 / A3 / A5 / Letter / Legal | A4 | 写入 `w:pgSz` |
| `page.margin.top/bottom/left/right` | `2.50cm` / `25mm` / `1in` | 2.54cm | 写入 `w:pgMar`，cm 精度 0.01 |
| `page.columns` | 1 / 2 / 3 | 1 | 写入 `w:cols`，分栏时首段前不加分节 |
| `body.font` | 字体名 | Liberation Serif | 西文字体，逐 run 写 `w:rFonts@ascii` |
| `body.font.eastasia` | 字体名 | SimSun | 中文字体，写 `w:rFonts@eastAsia` |
| `body.size` | pt 数字（`12`/`10.5`） | 12 | `w:sz` = pt×2 |
| `body.line_spacing` | `1.5` / `2` / `20pt` | 1.5 | 倍数 → `w:line=倍数×240`；带 pt → `lineRule=exact` |
| `body.align` | both / left / center / right | both | `w:jc` |
| `body.first_line_indent` | `0cm` / `2chars` | 0cm | chars → `字符数×字号×20` twips |
| `title.size` | pt | 16 | Title style |
| `heading.1.size` / `.2` / `.3` | pt | 14 / 12 / 12 | Heading1-3 style |
| `heading.N.emphasis` | bold / bold italic / italic / none | bold / bold italic / italic | 只影响 Heading 样式 |
| `heading.N.font` | 字体名 / inherit | inherit | 标题中文字体（如"一级标题黑体"） |
| `heading.numbering` | decimal / manual | decimal | 记录来源；编号文本一律逐字保留，不重编 |
| `caption.size` | pt | 10 | Caption style |
| `caption.figure.position` | below / above | below | 图题在图下/上 |
| `caption.table.position` | above / below | above | 表题在表上/下 |
| `table.style` | three-line | three-line | 三线表：上下粗线 + 表头细线，无竖线 |
| `reference.style` | APA / GB/T 7714 / IEEE / Vancouver / Harvard … | author-year | 记录样式；条目不重排 |
| `reference.hanging` | cm | 0.5cm | Bibliography style 悬挂缩进 |
| `footer.page_number` | center / right / left / none | center | 页脚 PAGE 域 + 对齐 |
| `page.header` | none / 文本 | none | 没有页眉要求时不生成页眉 |
| `toc.levels` | 0-3 | 0 | >0 才插入 TOC 域（需标题 ≥1 个）；生成的目录需在 Word 里更新域 |

## 3. 输出侧 `format_spec.json`

```json
{"case_id": "…", "generated_at": "…",
 "counts": {"total": 32, "explicit": 24, "inferred": 8},
 "conflicts": [{"field": "body.size", "kept": {"value": "12", "locator": "m01#…"},
                "other": {"value": "10.5", "locator": "m02#…"}}],
 "fields": [{"field": "…", "value": "…", "status": "explicit|inferred",
             "source": "m02", "locator": "m02#L0005", "quote": "…", "decided_by": "agent|script|default"}]}
```

`decided_by` 说明该值来自 Agent 确认、脚本挖掘还是默认值——复核时先看这一列。

## 4. 优先级

`spec_table.json`（Agent）> docx 模板/tex 模板挖掘 > 格式要求文本挖掘 > 默认值。
同一字段多来源冲突时保留高优先级者，低优先级的 value+locator 写进 `conflicts`，并在 `uncertainty` 里留一条。
