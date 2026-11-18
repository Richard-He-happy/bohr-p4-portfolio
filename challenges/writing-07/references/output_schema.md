# 输出契约、异常处置与自检清单（v1.0.0）

## 1. `/app/output/` 文件

| 文件 | 类型 | 说明 |
|-|-|-|
| `result.json` | 结构化 | 平台主接口；回填 `output_contract` 全部字段 |
| `manuscript.md` | 可编辑稿 | 主产物：四段式 + References |
| `related_work_matrix.md` | 表格 | 路线 × 维度矩阵，含 locator 列 |
| `evidence_map.json` | 证据表 | 论断 → source_id / locator / 逐字 quote / 命中结果 |
| `preserved_facts.json` | 事实表 | 数字+单位逐字保留，附来源句 |
| `change_log.json` | 变更记录 | original_quote → revised_quote + reason + locator |
| `sources_index.json` | 复核索引 | source_id → 抽取文本（供 `verify.py` 独立核验） |

全部为 UTF-8 文本，可继续编辑；不产出截图或位图替代物。

## 2. `result.json` 字段

| 字段 | 类型 | 含义 |
|-|-|-|
| `case_id` | str | 原样保留输入 |
| `status` | str | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| `deliverables` | obj | 产物名 → 相对路径 |
| `sections_present` | obj | background / related_work / research_gap / contributions 四布尔 |
| `citations` | list | 文献记录：id, key, authors, year, title, venue, doi, abstract, route, route_score, metadata_status, source_id, locator, origin |
| `evidence_map` | list | claim_id, section, citation, claim, source_id, locator, quote, quote_verified |
| `preserved_facts` | list | fact（数字+单位逐字）, source_id, locator, quote |
| `groups` | list | route, count, members[] |
| `gap_derivation` | list | gap_id, gap_type(shared_limitation/uncovered_scenario/conflict), route, basis_quote, supports[], source_id, locator |
| `contribution_alignment` | list | contribution_id, text, aligned, locator |
| `coverage` | obj | references, routes, unclassified, with_abstract, metadata_complete, recent_3y, evidence_items, quote_verified_rate, citation_markers_in_manuscript, preserved_facts |
| `workorder_receipts` | list | item, instruction, status(done/pending_human), evidence |
| `changes` | list | change_id, section, original_quote, revised_quote, reason, locator |
| `sources` | list | source_id, path, kind, chars |
| `uncertainty` | list | item, detail（判断不确定处） |
| `pending_human` | list | item, detail, locator/ids/missing（必须人工处理项） |
| `errors` / `degradations` | list | 失败与降级记录 |
| `verification` | obj | engine, checked, quote_verified_rate, failures[] |
| `runtime` | obj | skill_version, started_at, finished_at, python, output_dir, contract_source |
| `output_contract` | any | 输入原样透传 |

缺值规则：字符串 `null`，列表 `[]`，对象 `{}`；`output_contract` 的键一个不改、一个不删。

## 3. locator 规范

| 源类型 | 形式 | 例 |
|-|-|-|
| 文本 / markdown / docx 段 | `L<起>-<止>` | `material.md#L12-L14` |
| PDF（抽取文本） | `c<起>-<止>` 字符偏移 | `paper.pdf#c1024-1300` |
| JSON | `$` 路径 | `refs.json#$.references[3]` |
| CSV / XLSX | 行号 | `table.csv#row5` |

quote 判定：仅做空白归一化后子串匹配；不改标点、不改大小写、不做同义替换。

## 4. 异常处置

| 情况 | status | 处置 | 记录位置 |
|-|-|-|-|
| `/input` 空 / 无 case.json | `input_error` | 仍写合法 result.json + 空产物说明 | errors |
| case.json 坏 JSON | `input_error` | 尝试同目录 `case*.json` 继续 | errors |
| 有 case 无材料 | `insufficient_evidence` | 交骨架 + 缺口清单 | pending_human |
| 文献库为空 | `insufficient_evidence` | 四段骨架 + 空白说明，不编造文献 | pending_human |
| 单文件损坏 | 其余继续 | 跳过该文件 | errors |
| PDF 乱码/过短 | `partial` | `pdf_text_heuristic`，只到标题层面 | degradations + uncertainty |
| quote 未命中 | `partial` | 保留原文但标 `[待核实]` | evidence_map + pending_human |
| 引用元数据缺项 | `partial` | 标 `[待补]`，不补造 | citations + pending_human |
| 目标期刊格式未知 | 不影响 | 默认 author-year，说明需调整 | uncertainty |
| 语言未指定 | 不影响 | 按材料 CJK 占比判定 | result.language |

## 5. 引用格式支持

| 格式 | 用法 | 说明 |
|-|-|-|
| author-year 编号（默认） | 正文 `[1]`，References 编号列表 | 无需改模板 |
| 作者-年份 | `(Li et al., 2021)` | 作者/年份取自材料，不推断 et al. 规则之外的信息 |
| GB/T 7714 / Vancouver | 顺序编号 + 著录项 | 仅在输入明确要求时使用；缺项保留 `[待补]` |

不支持：自动补 DOI、自动查库补全缺失著录项（不联网，禁止编造）。

## 6. 交付前自检

1. `python3 -B scripts/main.py --help` 退出码 0。
2. `result.json` 为合法 JSON；`case_id` 与输入一致；`output_contract` 每个键都在。
3. `sections_present` 四项与 `manuscript.md` 标题一致。
4. `evidence_map` 非空；`quote_verified_rate ≥ 0.8` 才可 `status=ok`。
5. `gap_derivation` 每条有 `supports`；`contribution_alignment` 每条有 `locator`。
6. `preserved_facts` 覆盖稿中所有带单位数字；稿中无材料外数字。
7. `pending_human` 只含真实缺口（缺元数据、缺摘要、未分组、未对齐贡献）。
8. 目录无 `__pycache__`、`.pyc`、临时文件。

## 7. 维护

- 版本 1.0.0；纯标准库（Python ≥3.8）；无网络、无外部数据。
- 路线词表两处：`scripts/verify.py::ROUTES`（运行时）与 `references/writing_playbook.md` 3.1（文档），改动需同步并升版本。
- 回归：`python3 -B scripts/main.py --input <案例> --output <dir>` 后跑 `verify.py`，看 `quote_verified_rate` 与 `pending_human` 是否只含真缺口。
- 已知限制：PDF 抽取不保页号、不解析扫描件；路线词表为英文关键词，纯中文文献标题命中率低，需人工归组。
