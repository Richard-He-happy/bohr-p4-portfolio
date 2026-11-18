---
name: research-file-library
description: 科研文件库的入库与检索 Skill。扫描一个文件库（PDF/Word/Excel/PPT/TXT/CSV/图片），产出逐文件清单（路径、大小、sha256、角色、元数据及出处）、按内容哈希判定的重复组、版本链、章节级索引，并按提问做硬过滤检索，返回落在原文段落上的逐字引用、定位与回链，再做独立复核。输出 result.json（原样回填 output_contract）、inventory.csv、version_chain.json、operations.log。
version: 1.0.0
license: 供本赛题提交与复用；脚本仅用 Python 标准库
---

# research-file-library（library-02 科研文件智能检索）

## 1. 用途与边界

**做**：把一个已经存在的文件库整理成可交接的清单，保留版本与重复关系，然后按提问在**文件内容**里做语义检索，把命中落到**章节/页码/段落/工作表行/幻灯片**，给出逐字引用与可复核回链，并把无法处理的文件如实记入失败与待人工清单。

**不做**：不联网、不做开放文献检索、不读扫描件像素（无 OCR）、不解析 `.doc/.xls/.ppt` 等旧式二进制 Office、不判断底层存储权限策略、不生成或补写任何材料里没有的数据。

**适用**：文件已在本目录、需要"哪一版写了什么、在哪一段"的可核验回答。
**不适用**：需要 OCR 的纯扫描库（只能入库不能检索）、跨库联邦检索、改写原文类任务。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json` 与 `/input/task.md`，材料在 `/input/**`（可用 `--input` 覆盖） |
| 输出 | `/app/output/`（可用 `--output` 覆盖） |
| 入口 | `python3 scripts/main.py`（`--help` 可用） |
| 退出码 | **恒为 0**；失败只体现在 `result.json` 的 `status`/`errors`/`pending_human` |
| 顺序 | 任何重活之前先写 partial `result.json`，收尾无条件覆盖为最终版 |
| 依赖 | Python 3 标准库；`scripts/engine.py` 由 `main.py` 用 `Path(__file__).resolve().parent` 定位导入，不依赖 CWD |
| 规模 | 单库数千文件、秒级完成；`--max-files` 默认 4000 |

## 3. 输入发现（按语义，不假设键名）

1. 在输入根递归找 `case*.json`；优先 `case.json` / `input.json` / `task.json`。
2. `case_id` 依次尝试 `case_id`/`caseId`/`case`/`id`，均无则用输入目录名；**原样保留**。
3. `output_contract` 原样取出（dict 或 list-of-dict 均支持），末尾回填。
4. 提问按语义在整棵 JSON 里找：键名含 `query/question/ask/request/检索/提问/问题`（拉丁词按**整词**匹配，`text` 不会被当成 `ext`）；值可为字符串、对象（取 `text/query/question/内容`）或列表。
5. 材料按**魔数优先、扩展名其次**识别（`%PDF`、`PK\x03\x04`、OLE、PNG/JPEG/TIFF），不靠文件名猜内容。
6. 组织方备注/别名：键名含 `note/alias/rename/metadata/version/admin/备注/别名` 的字典或列表，按文件名或路径子串匹配后作为权威覆盖写入，`meta_sources` 记 `case_note`。

## 4. 输出契约

- `result.json`：`output_contract` 每个键都在，**键名不改、未知键保留**，语义能对上的填对应结果，对不上的填 `null`（列表类为 `[]`）；原始契约另存 `output_contract_spec` 便于复核。
- 同目录写 `inventory.csv`（每文件一行）、`version_chain.json`（版本链 + 重复组）、`operations.log`（制表符分隔的操作轨迹）。
- 顶层还包括 `files/directories/duplicates/version_chains/queries/failures/skipped/permissions/pending_human/errors/degradations/counts/verification/runtime` 与 `status`。
- 字段细则见 `references/output-schema.md`。

## 5. 核心流程

1. **先落盘**：骨架 `result.json`（`status=partial`）。
2. **盘点**：逐文件 `stat` → `sha256` → 魔数 → 抽取文本单元（`loc` + `text`）；目录单独记录文件数与可读性。
3. **元数据**：项目号/年份/文档类型/版本标签/批次，每项带 `source`（filename/content/fs_mtime/extension/case_note）与 `evidence`（命中的原文片段）。
4. **关系**：按 sha256 判重复（别名不算独立证据）；按"项目号 + 去版本化文件名"聚簇，再按版本标签序号、否则按 mtime 排序成链，`is_current` 取链尾，并记时间单调性异常。
5. **索引**：以抽取单元为单位建索引（页/段/行/幻灯片），把"当前生效章节标题"附着到单元（标题跨页继承）；契约文件（`case.json`/`task.md`）不参与检索。
6. **检索**：词项 = 字面词（权重 1.0）+ 同义/缩写扩展（0.55）；硬过滤先执行，再算 IDF 加权得分（章节命中 ×1.8，文件名命中 ×1.4），截断到 `--top-k`。
7. **回链与复核**：每条命中给 `locator`、`locator_hint`、`backlink`、逐字 `quote`；再用**原始文件重新抽取**校验引文，写 `verification`。

## 6. 质量规则（评分点 → 字段/检查/产物）

| 评分点 | 落点 |
|---|---|
| 任务完成度 | `status` + `counts` + 四件产物齐备；缺件进 `errors` |
| 结果正确性 | 命中落 `locator`（页/段/行/幻灯片），`quote` 逐字 |
| 结果完整性 | `inventory.csv` 每文件一行；`queries[].filtered_out`/`notes` 记录过滤影响面 |
| 结果可核验性 | `verification.checks`（契约键、引文重抽取）+ `artifacts[].sha256` |
| 质量增益 | 章节级定位 + 逐字引用 + 版本/重复标注，非文件名搜索可得 |
| 效率增益 | 一次运行同时给出清单、版本链、检索与复核 |
| 新增能力 | 章节标题跨页继承、过滤器不可满足时如实报告、字节级重复识别 |
| 方法改进 | 哈希优先的关系判定、按语义发现提问、独立重抽取复核 |
| 可靠体验 | §9 异常分支 + 恒 0 退出码 + partial 先落盘 |
| 生态贡献 | 本文件 + `references/` 的字段规范、方法说明、最小示例 |

## 7. 证据与定位规范

- 定位类型：`pdf_page{page}`（物理页，1 起）、`docx_para{para}`、`xlsx_row{sheet,row}`、`pptx_slide{slide}`、`text_line{line_start,line_end}`。
- `locator_hint` 形如 `p.3 §2.3 Buffer formulation`；`backlink` 形如 `artifacts/x.pdf#page=3&char=120-420`。
- `quote` 必须能在该定位单元内逐字找到（允许空白折叠）。找不到即 `quote_verified=false` 并入 `pending_human`，绝不改原文凑通过。
- PDF 只取文字层、不重排、不做 OCR；双栏阅读顺序可能错乱，此时定位仍指向正确物理页，栏内顺序需人工确认（记入 `uncertainty`）。

## 8. 过滤与冲突

- 硬过滤维度：`year/project/ext/batch/version/path`，来自提问对象字段或提问措辞。
- **不可满足不放宽**：某维 0 命中时写 `queries[].notes`，该问题 `status=insufficient_evidence`、`hits=[]`。
- 重复文件（同 sha256）只保留一个命中，其余打 `dup_group`；版本链中非 `is_current` 命中仍返回但带 `is_current=false`。
- 同版本标签不同内容 → `version_conflicts`；版本序与 mtime 矛盾 → `timestamp_anomaly`。

## 9. 异常与降级分支

| 情形 | 识别 | 处置 | 记录位置 |
|---|---|---|---|
| 无权限 | 读取抛 `PermissionError` | 跳过内容 | `permissions` + `pending_human` |
| 加密 PDF | `/Encrypt` | 不入索引 | `extract=encrypted_pdf` |
| 无文本层扫描件 | 每页字母数 < 20 | 只入库 | `scanned_no_text_layer` |
| 图片 | 魔数 | 只入库 | `image_no_text_layer` |
| 损坏容器 | `BadZipFile` 等 | 只入库 | `parse_error:*` |
| 旧式 Office | OLE 魔数 | 只入库 | `unsupported_legacy_office` |
| 超大文件 | > `--max-mb` | 记账跳过 | `skipped` |
| 符号链接 | `is_symlink` | 不跟随 | `skipped` |
| 重名不同内容 | 同名不同哈希 | 视为不同文件，链内标冲突 | `version_conflicts` |
| 无 `case.json` | 发现失败 | 仍旧全量扫描 | `errors` + `degradations`，`status=partial` |
| 契约缺失 | 无 `output_contract` | 输出空契约并说明 | `uncertainty` |

所有分支都只**局部降级**，不影响其余文件的清单与检索。

## 10. 预算与断点

- 第一个动作即写 partial；各阶段异常都被 `try/except` 捕获写入 `errors`，末尾兜底再写一次 `result.json`。
- 需要更短耗时可加 `--skip-verify` 关闭复核。
- 重复运行结果确定（无随机、无缓存依赖），同一输入两次运行产物一致（`mtime` 字段除外）。

## 11. 自检清单

- [ ] `result.json` 存在且 JSON 合法，`status` 与实际情况一致
- [ ] `output_contract` 键数与原契约一致、无改名
- [ ] `inventory.csv` 行数 = 文件数（不含表头）
- [ ] 每条命中都有 `locator` + `quote`，`verification.checks[*].pass` 为真
- [ ] 每个未抽取成功的文件都在 `pending_human` 或 `permissions` 里
- [ ] `operations.log` 非空（含 scan/extract/link/write）
- [ ] 退出码为 0

## 12. 最小调用示例（示例，非正式案例结果）

输入（节选，示例）：

```json
{"case_id": "demo-001",
 "questions": [{"id": "Q1", "text": "哪一版写了 PBS 缓冲液配方？", "filters": {"project": "PRJ-2021"}}],
 "output_contract": {"inventory": null, "version_relations": null, "search_results": null, "status": null},
 "administrative_notes": {"protocol_v1_2021.pdf": "superseded by v2"}}
```

调用：

```bash
python3 scripts/main.py --input /input --output /app/output
```

示意输出（截断，示例）：`status=ok`；`counts.files=11`；`version_chains[0].ordering_basis=version_label`，`is_current` 指向 v2；`queries[0].hits[0]` 形如

```json
{"file": "artifacts/protocol_v2_final_2021.pdf", "locator": {"kind": "pdf_page", "page": 1},
 "locator_hint": "p.1 §2.3 Buffer formulation",
 "quote": "Prepare 1x PBS buffer with 12 mM Tris, pH 7.6 (revised).", "quote_verified": true}
```

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（v1.0.0） |
| `scripts/main.py` | 清单 / 关系 / 索引 / 检索 / 输出 / 复核 |
| `scripts/engine.py` | 抽取层：文本单元、元数据、版本键、查询词与硬过滤、提问与备注发现、定位与引用 |
| `references/output-schema.md` | result.json / CSV / JSON / LOG 字段规范与契约映射 |
| `references/method.md` | 抽取、判定、排序、定位、失败码的完整规则 |
| `references/example.md` | 最小示例（标注为示例） |

## 14. 维护说明

- 新增文件类型：只改 `engine.units_of` 的分支与 `kind_of` 的魔数表，`loc` 约定不变，检索与回链自动生效。
- 调整章节识别：改 `engine.HEAD`；调整同义词：改 `engine.SYNS`（`中文=english aliases`，分号分隔）。
- 改动抽取逻辑后同步更新 `references/method.md`，并重跑 §11 自检清单。
