# 方法说明（v1.0.0）

## 1. 抽取：文件 → 可定位文本单元

单元是 `{"loc": {...}, "text": "..."}`，`loc` 是**可复核的位置**，不是行号猜测。

| 类型 | 判定 | 单元 | `loc` | 说明 |
|---|---|---|---|---|
| PDF | `%PDF` | 每页一个 | `pdf_page{page}` | 物理页（1 起）；解开 `/FlateDecode`；正确处理 `/Contents` 引用与数组；无文字层（每页字母 <20）判 `scanned_no_text_layer`；`/Encrypt` 判 `encrypted_pdf` |
| DOCX | zip + `word/document.xml` | 每段一个 | `docx_para{para}` | 段落序号即 XML 中 `<w:p>` 出现次序（含表格单元内段落） |
| XLSX | zip + `xl/worksheets/*` | 每行一个 | `xlsx_row{sheet,row}` | 解 sharedStrings 与 inlineStr；`A=值 \| B=值`，保留列字母 |
| PPTX | zip + `ppt/slides/*` | 每页一个 | `pptx_slide{slide}` | 页面文本按 `<a:t>` 顺序拼接 |
| TXT/CSV/MD/JSON… | 扩展名 + 解码 | 每 40 行一块 | `text_line{line_start,line_end}` | 依次尝试 utf-8-sig / utf-8 / gb18030 / latin-1 |
| 图片 | PNG/JPEG/TIFF 魔数 | — | — | `image_no_text_layer`，只入库 |
| OLE（.doc/.xls/.ppt） | `D0CF11E0` | — | — | `unsupported_legacy_office`，只入库 |

抽取失败**不抛异常**：`units_of` 返回 `(units, status, note)`，主流程据此写 `degradations` 与 `pending_human`。
PDF 不做重排、不做 OCR：双栏文档的阅读顺序可能错乱，但页码始终正确。

## 2. 元数据与出处

| 字段 | 正则（摘要） | 出处判定 |
|---|---|---|
`project_id` | `(?:project|proj|项目|课题)[\s_\-\:：#]*([A-Za-z]{1,5}[\-_]?\d{1,6})` | 先文件名，再正文前 4000 字 |
`year` | `(19|20)\d{2}`；先试 `YYYY-MM-DD` | 文件名 → 正文 → 文件 mtime |
`doc_type` | 关键词表：protocol/record/report/manuscript/supplementary/data/figure/slide | 命中位置在文件名则 `filename`，否则 `content`；都没有则 `extension` |
`version_label` | `v1`/`ver 1.2`/`rev2`/`final`/`draft`/`定稿`/`修订版` | 文件名 |
`batch` | `(?:batch|lot|批次|批号)[\s_\-\:：#]*([A-Za-z0-9\-]{1,12})` | 文件名 |

每个字段都在 `meta_sources` 记来源、在 `meta_evidence` 记命中的原文片段。
组织方备注命中时来源改为 `case_note`，并在 `admin_notes` 保留原始备注文本。

## 3. 重复与版本

1. **重复**：按完整 `sha256` 分组，同组即字节级复制。`canonical` 取路径最短、其次 mtime 最早者。重复件不是独立证据，检索时同组只保留一条命中。
2. **版本链**：聚簇键 = `(project_id 或 NA, stem_key(name))`。`stem_key` 去掉 `v1/v2.3`、`rev2`、`final/draft/定稿/修订`、`copy/副本`、`(1)`、日期与标点，只留主体。
3. **排序**：链内若 ≥2 个成员带可解析版本标签，按标签序号（`定稿/final`=900，`初稿/draft`=1，纯数字取数值），否则按 mtime；`is_current` 取链尾。
4. **异常**：版本序与 mtime 顺序相反 → `timestamp_anomaly`；同标签不同哈希 → 该链 `distinct_contents>1`，需人工裁决。

## 4. 章节定位

`HEAD` 正则识别：`1`/`2.3`/`1.2.3` 编号开头、`第X章/节`、全大写短行、以及 摘要/目录/引言/前言/方法/材料与方法/结果/讨论/结论/参考文献/附录/实验方法/数据分析。
逐单元扫描标题；单元内命中点之前最近的标题即为该元点的章节；单元内无标题时继承上一单元的"当前生效标题"（标题跨页/跨幻灯片继承）。
`locator_hint = 位置 + §章节`，`backlink = 相对路径 + #位置&char=起-止`。

## 5. 检索打分

1. 词项：NFKC 归一 → 小写 → 拉丁词切分（去复数 s）+ 中文二元组；同义词/缩写表 `SYNS`（`中文=english aliases`，分号分隔）扩展，扩展词权重 0.55，字面词 1.0。
2. 硬过滤先执行（见 §6），只对被允许的文件计分。
3. `idf(t) = ln(1 + N / (1 + df(t)))`，`N` = 候选单元数，`df(t)` = 含该词的候选单元数。
4. `score += idf(t) × w × (1 + ln(tf)) × (章节命中?1.8:1) × (文件名命中?1.4:1)`。
5. 按分数降序，跳过已出现的重复哈希，取前 `--top-k`。
6. 引文：在单元文本中定位最强命中词，向前后扩到句界（`。！？.!?` 或换行），截断到 340 字符。

## 6. 硬过滤

| 维度 | 取值来源 | 判定 |
|---|---|---|
`year` | 提问字段或问句中的四位年份 | 与元数据 `year` 相等 |
`project` | 提问字段或 `项目/课题/project` 后的编号 | 相等或子串包含 |
`ext` | 提问字段或问句中的"pdf/word/excel/表格/ppt" | 文件扩展名相等 |
`batch` | 提问字段或 `批次/批号/batch` 后的编号 | 相等 |
`version` | 提问字段或"最新/latest/current/定稿" | 仅保留 `is_current` |
`path` | 提问字段 | 路径子串匹配 |

维度名按**整词**匹配，避免 `text` 被当成 `ext`。
某维在库中 0 命中时不放宽，写 `queries[].notes` 并把该问题置 `insufficient_evidence`。

## 7. 失败码

`ok`、`encrypted_pdf`、`scanned_no_text_layer`、`image_no_text_layer`、`unsupported_legacy_office`、
`unsupported_binary`、`undecodable_text`、`parse_error:<异常类名>`、`permission_denied`、`read_error`、
`stat_error`、`skipped_size`、`extraction_module_unavailable`。

除 `ok` 外，文件仍进入清单与哈希统计，但不进入检索索引；同时写 `degradations`（能力与影响）与
`pending_human`（建议动作，如"OCR 或提供文字层"）。

## 8. 已知限制

1. PDF 只做文字层提取：不处理加密、不做 OCR、不重排双栏与跨页表格。
2. 旧式 `.doc/.xls/.ppt` 与其它二进制容器只入库不可检索。
3. 章节识别基于版式启发式；无编号、无典型标题的文档只能退化到"页/段"级定位。
4. 版本链依赖文件名线索（版本标签）与 mtime；文件名不含版本信息时只能按时间推断，并在 `ordering_basis` 中如实写明。
5. 打分是词项级 BM25 近似，不含向量语义模型；同义扩展依赖 `SYNS` 表，覆盖面有限。
