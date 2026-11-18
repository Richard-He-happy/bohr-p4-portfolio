# 合规检查口径与复核方法

`build` 会读回自己产出的 `deliverable.docx`（解压 OOXML、正则取属性），把「期望值」与「实测值」并列写进 `result.json.compliance_checks`。检查项不写"我做到了"，只写读回来的值。

## 1. 12 项检查

| id | 检查 | 期望值来源 | 实测方式 |
|---|---|---|---|
| C1 | 纸张 | `page.size` | `w:pgSz` 的 w/h 与 A4 11906×16838 比对（±80 twips） |
| C2 | 四边页边距 | `page.margin.*` | `w:pgMar` 各属性 ÷1440×2.54，cm 误差 <0.06 |
| C3 | 栏数 | `page.columns` | `w:cols@num` |
| C4 | 正文字体 | `body.font` | `Normal` 样式 `w:rFonts@ascii`；另报 `runs_with_font/runs` 证明字体写进了每个 run |
| C5 | 正文字号 | `body.size` | `Normal` 的 `w:sz`÷2 |
| C6 | 行距 | `body.line_spacing` | `Normal` 的 `w:spacing@line`：auto 时 ÷240 得倍数，exact 时 ÷20 得 pt |
| C7 | 三级标题 | `heading.N.size` | `Heading1-3` 的 `w:sz`÷2 与 `w:outlineLvl`（0/1/2），并报输出里标题段数 |
| C8 | 题注 | `caption.size` | `Caption` 样式字号 + 写出的题注段数 |
| C9 | 页脚页码 | `footer.page_number` | `footer1.xml` 是否含 `PAGE` 域 + `w:jc` 对齐 |
| C10 | 三线表 | `table.style` | `w:tblBorders`：上下 single、`insideV=none`、`tblHeader` 重复表头 |
| C11 | 内容保真 | — | 源内容单元逐字命中率（应为 1.0） |
| C12 | 数字/引用 | — | 数字与引用标记前后计数，任何丢失即 fail |

任一项 fail 仍会产出文件，但 `status` 降为 `partial`，并在 `uncertainty`/`degradations` 写明原因。

## 2. 保真度怎么算

- **内容单元** = 段落文本 + 题注文本 + 表格行（单元格用 ` | ` 连接）。
- 比对前把所有空白压掉（`re.sub(r"\s+","")`），因此换行/空格差异不算改动；**改字、删字、改数字一定算**。
- `verbatim_ratio = 命中单元 / 源单元`；源单元为空时记 1.0（不得据此宣称"已完成"）。
- 数字：正则 `\d+([.,]\d+)?` 逐 token 计数；引用：`[1]`、`[2,3]`、`(Zheng et al., 2018)`、`Figure 1`、`Table 2`、`doi:`、`http(s)://`。
- 写出的文本会被再次解压比对（`fidelity_report.json.docx_roundtrip`），证明"写进去的"和"读回来的"一致。

## 3. 典型降级与处置

| 现象 | 判定 | 处置 |
|---|---|---|
| 规格 quote 在原文找不到 | Agent 记错或改了原文 | 拒收该条（`degradations`），回退挖掘值/默认值；**不要**改 quote |
| `NOT STATED` 的字段 | 材料确实没写 | 用默认值，`status=inferred`，进 `uncertainty` |
| 同字段两处规定不同 | 模板/要求冲突 | 保留高优先级，另一方写 `conflicts`，进 `pending_human` 请人确认 |
| 数字计数下降 | 内容被改写/合并 | 视为失败：改回逐字原文后重跑 |
| 无 LibreOffice | 环境缺工具 | 保留 docx/md + `preview.txt`，`export_artifact=null` 并记降级 |
| docx 打不开 | 写入异常 | 用默认规格重写最小 docx，错误入 `errors`，退出码仍 0 |

## 4. 人工复核步骤（30 秒）

1. `format_spec.json.counts` 看 explicit/inferred 比例；`decided_by=default` 的行是"没人规定、用了默认值"。
2. `compliance_checks` 逐条看 `expected` vs `actual`，fail 项读 `note`。
3. `fidelity_report.json.summary` 看 `verbatim_ratio`、`numbers_lost`、`citations_lost`；`block_map` 可逐段回溯到源 locator。
4. 打开 `preview.pdf` 看版面；`pdffonts preview.pdf` 看字体是否嵌入。
5. 编辑 `deliverable.docx`：标题应显示「标题 1/2/3」样式（不是手动加粗），页脚是页码域，表格为三线表。
