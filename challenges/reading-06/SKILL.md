---
name: literature-field-extraction
description: Extract per-field results from a paper (PDF/DOCX/XLSX/CSV/MD) against a supplied target-fields.json, with a verbatim quote and paragraph/page/table locator for every field, four honest statuses (reported / not_reported / source_conflict / extraction_failed), and a result.json filling every output_contract key. Use when a case ships a field list plus source material and asks for structured literature data, conclusions or conditions rather than a prose summary.
version: 2.0.0
license: MIT
---

# 文献结论与数据提取（逐字段 + 原文证据）

## 1. 用途与边界

把案例（`/input/case.json` + `target-fields.json` + 论文/表格）转成**逐字段可核对**的结果：每个 `field_id` 一行，含值、单位、统计量、条件、对照、四状态之一、逐字 `quote`、可定位 `locator`。

- 适用：结论/条件/数值/证据定位；正文、表格、图注、补充材料同表处理。
- 不适用：替作者补结论、跨文献合并、把摘要式总结当交付。
- 铁律：猜出来的值不算抽取；原文没有 ≠ 0；quote 字面命中 ≠ 语义正确——语义由你判断，脚本只校验字面与覆盖。

## 2. 运行契约

| 项 | 值 |
|---|---|
| Skill 目录 | `$SKILL_DIR`（评测机 `/skills/weekly-skill`，勿写死） |
| 输入 | `/input/case.json`、`task.md`、`target-fields.json`、材料 |
| 工作/产物 | `/app/work` 草稿与索引；`/app/output` 交付 |
| 依赖 | `python3 -B`，纯标准库，不联网，不依赖 CWD |
| 退出码 | 恒 0；失败也写合法 `result.json` |

```bash
S=$SKILL_DIR/scripts
python3 -B $S/main.py init     # 建索引 + 首份 partial result.json
python3 -B $S/main.py show --grep "IC50" --limit 20
python3 -B $S/main.py check    # 校验草稿
python3 -B $S/main.py build    # 定稿产 extraction.* + result.json + 5 个可核验资产
python3 -B $S/main.py audit    # 只重算 golden_standard/diff_report/version_history/self_check/run.log
python3 -B $S/main.py build --no-audit   # 只出 v1 产物（不生成可核验资产）
```

`main.py check|build` 转发到 `build.py`（也可直接调用）。

## 3. 输入发现（脚本已实现）

1. 递归扫 `/input`；`case.json` 缺失时取 `case*.json`，按 `utf-8-sig` 读、容忍尾逗号。
2. 字段表取 `target-fields.json` 或 case 内 `target_fields|fields`；语义键：`field_id|id|key`、`label|name|question`、`aliases|keywords`。
3. 材料按**扩展名 + 魔数**：`%PDF`（`pdftotext -layout`，缺失时 zlib 流解析并记降级）、`PK`+`word/|xl/`（DOCX/XLSX）、CSV/TSV、MD/TXT/JSON；图片无 OCR 只记降级，不造内容。
4. 排除自身产物与配置；段落 id `M1-p0002`，PDF 另给 `page`；索引写 `/app/work/index.json`、`paragraphs.json`。

## 4. 核心流程（Agent 主导，脚本只辅助）

1. **`init`** → 读 `/app/work/workorder.md`（任务、字段表、材料表、契约键）。
2. **亲自读原文**：`show --grep` 找候选段，`show --para M1-p0002` 读整段；逐字段确认值、单位、统计量、条件、对照、来源（正文/表格/图注/摘要/补充）。
3. **写 `/app/work/draft.json`**（schema §5；也可写 `draft.md` 管线表，JSON 优先）。
4. **`check`** → 按错误码逐条修（§10）。
5. **`build`** → 读回 `counts` 与 `uncertainties`，确认状态与缺口。
6. 剩余 <150 s：停止检索直接 `build`；任何时刻磁盘上都有合法 `result.json`。

## 5. 草稿 schema（`draft.json`）

```json
{"case_id": "原样", "fields": [
  {"field_id": "F1", "label": "IC50", "value": 12.4, "unit": "nM",
   "statistic": "95% CI 10.1-15.2 nM", "condition": "25 degrees C, 30 min, triplicate",
   "comparator": "vehicle", "source_kind": "text|table|figure|abstract|supplement",
   "status": "reported", "quote": "原文逐字片段",
   "locator": {"material_id": "M1", "paragraph_id": "M1-p0002", "page": 3,
               "table": "Table 2", "row": "control", "col": "mean"},
   "reasoning": "怎么读出：句子/单元格/图注；单位与统计量来源", "conflict": null}],
 "claims": [{"id": "C1", "kind": "author_conclusion|limitation|speculation|data_point",
             "text": "结论", "quote": "逐字", "locator": "M1-p0005", "field_ids": ["F1"]}],
 "uncertainties": [], "pending_human": []}
```

`reported` 必须有 `value`+`quote`+可定位 `locator`；其余三值 `value` 留空，`reasoning` 写查过的词/节/表。

## 6. 四状态判定

| status | 含义 | 必填 |
|---|---|---|
| `reported` | 原文明确给出 | `value`+`quote`+`locator`（+`unit`/`statistic`/`condition`） |
| `not_reported` | 材料范围内确实没有 | `reasoning`：搜索词、已查章节/表/补充材料 |
| `source_conflict` | 多处说法不一致 | 双方 `conflict.quote_a`/`quote_b`（可加 `value_a`/`value_b`），`value` 写首选并注明 |
| `extraction_failed` | 有候选但读不出（无文本层、跨页缺行、单位缺失） | `reasoning` 写失败点与已试手段 |

判定顺序：材料里有没有 → 多处是否一致 → 能不能读出来。`not_reported`（原文没有）与 `extraction_failed`（有但没读成）不得互换。

## 7. 证据与定位

- `quote` **逐字复制**（可省略号截连续片段；不改词、数、标点顺序，不翻译）。脚本三级校验：`quote_strict` > `quote_normalized`（大小写/空白）> `quote_loose`（去标点，记 warning）；找不到即 error。
- `locator` 至少 `material_id`+`paragraph_id`；PDF 加 `page`；表格给 `table`+`row`+`col`（跨页写两页页码）；图给 `figure` 子图号。"结果段"这类二手定位不可接受。
- 数值在正文、CI 在表格时：`quote` 取主值处，另一处写进 `reasoning`。
- `claims.kind` 区分作者结论、限制、推测、数据点；推测不得升格为事实。

## 8. 数值、单位与条件

- 保留原值形态：`12.4` 不写 `12`；`10.1–15.2 nM` 不改写成 `±2.5`；不换算单位（换算值只进 `reasoning`）。
- `statistic` 存误差/区间/检验量原文（`SD 0.4`、`p = 0.03`）；`condition` 存温度/时间/剂量/样本/基线；`comparator` 存对照或比较组；原文没有就留空，不写 "N/A" 猜测。
- 表格：数字与表头逐字保留，列不交换，合并单元格跨行时 `locator.row` 写所属组；表格与正文数值不同即 `source_conflict`。
- 图注只取文字明确写出的数值；像素读数标 `approximate: true` 并给误差。

## 9. 冲突与人工复核

- 冲突**保留双方**，两侧 quote 都要能在原文查到（否则 warning `conflict_sides`）。
- 不自造 `field_id`；`pending_human` 用于扫描件、单位缺失、跨页缺行、quote 仅 `loose` 命中、需领域换算。

## 10. check 错误码 → 处置

| code | 处置 |
|---|---|
| `missing_field` | 补该 `field_id` |
| `bad_status` | 改四状态之一（小写） |
| `quote_not_found` | 回 `show` 复制原文（多为改写/断字） |
| `bad_locator` | 段落 id 不存在，用真实 `M*-pNNNN` |
| `empty_value` / `quote_missing` | 补齐，或降级 `extraction_failed` 并写依据 |
| `no_justification` | 非 `reported` 补搜索词与范围 |
| `quote_loose` / `number_not_in_quote` / `conflict_sides` / `no_reasoning` | warning：核对后修，或保留并在 `uncertainties` 说明 |

`result.json` **原样回填** `output_contract` 全部键（不改名、不遗漏未知键，缺值 `null`/`[]`），并补 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`；`status` 适配契约提示（`ok|answered`、`partial`、`insufficient_evidence`、`input_error`）。

## 11. 异常与降级

| 场景 | 行为 |
|---|---|
| `case.json` 缺失/坏 | 记 `errors`，继续用材料+字段表，`partial` |
| 无材料 | `input_error`，仍写全部契约键 |
| PDF 无文本层 | `degradations: pdf_no_text_layer`，字段 `extraction_failed` + `pending_human` |
| 表格跨页/缺行 | `extraction_failed` 或 `source_conflict`，不推测缺失行 |
| 草稿缺失/坏 | 关键词检索给候选 quote，标 `extraction_failed`+`fallback_used`，覆盖率写进 `counts` |
| 单材料解析失败 | 只降级该材料 |

## 12. 预算与断点

64 请求 / 900 s / 单次 16k tokens。建议 8–15 次工具调用：`init` → 读 workorder → 批量 `show` → 写 draft → `check` → `build`。每完成一批字段重跑 `build`（幂等覆盖）。

## 13. 自检清单

1. `result.json` 含契约全部键 + `case_id`/`status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`。
2. `counts.target_fields` = 字段表条数，四个状态之和等于它。
3. 每个 `reported` 有 `value`、`quote`、`paragraph_id`，且 `counts.quote_failed = 0`。
4. 每个非 `reported` 有可读依据且确实查过对应关键词。
5. 冲突字段双方 quote 都能查到；`extraction.csv` 行数 = 字段数。
6. `self_check.json` 的 `summary.failed = 0`；有失败项就在 `uncertainties` 写明是哪一条、为什么。
7. `diff_report.md` 里没有 `gap`；`deviation` 必须返工，`needs_review` 写进 `pending_human`。
8. `run.log` 只含真实执行过的步骤（不许补写未跑的步骤），退出码列全为 0。

## 14. 最小示例（示例，非正式案例结果）

```bash
python3 -B $S/main.py init          # materials=1 target_fields=2 | M1 paper.pdf pdf paras=2
python3 -B $S/main.py show --para M1-p0001
# M1-p0001 [M1 p1] Results: compound A inhibited the kinase with an IC50 of 12.4 nM.
python3 -B $S/main.py check         # => PASS
python3 -B $S/main.py build         # fields=2 reported=1 not_reported=1 -> /app/output/result.json
```

## 15. 五个可核验资产（v2 新增，`build` 自动产出）

`build` 在 `/app/output` 与 `extraction.*` 并列写出下列文件；详细 schema 与判定口径见
`references/verification_assets.md`，`result.json` 同时用 `golden_standard`/`diff_report`/
`version_history`/`self_check` 四个字段回填摘要（原 `output_contract` 字段一个不减）。

| 资产 | 内容 | 关键点 |
|---|---|---|
| `golden_standard.json` | 逐字段期望：`expected_status`、`expected{value,unit,statistic,condition}`、`evidence{locator,quote}` 或 `search_ledger`、`basis`、`confidence`、`verdict` | **自建基准**：字段表义务 + 对同一批材料的独立词面重扫；`is_organizer_key: false`，不得当成组织方隐藏答案 |
| `diff_report.md` | 逐项对照表 + 明细 + 汇总 + 复跑命令 | verdict 只有 `match/deviation/gap/needs_review`；达标率 = match/字段数 |
| `version_history.md` | 复制 `references/version_history.md` 并追加本次运行段 | 改了什么、为什么、如何回退 |
| `run.log` | 步骤表（at/step/exit/ms/argv）、降级、异常、产物字节 | 事件来自真实执行；每次命令后由 `main.py` 重写，含当前命令退出码 |
| `self_check.json` | 17 项自检（契约键、行键、四状态计数、证据覆盖率、数字一致性、locator 粒度、golden 一致性、diff 覆盖、空/坏输入实测、退出码、包预算） | 自检**真跑**空输入与坏 JSON 子流程，结果写 `fallback_tests`；`SKILL_SELFTEST=1` 防递归 |

判定顺序不变：**有无 → 是否一致 → 是否读得出**。检测不到锚点不等于原文没写，`undetermined` 与
`needs_review` 是把判断交给人，不是把猜测写成事实。

## 文件清单与维护

```
SKILL.md                          本文档
scripts/main.py                   输入发现、段落索引、证据语料、init/show、run 事件
scripts/build.py                  check/build、四状态校验、契约回填、产物
scripts/audit.py                  五个可核验资产：金标准/对照/版本/日志/自检
references/field_dictionary.md    字段词典、状态口径、quote/locator 规范、check 码表
references/verification_assets.md 五个资产的 schema、verdict 口径、复跑与迁移、限制
references/version_history.md     版本记录与回退（运行时复制到输出）
references/example.md             端到端示例（合成数据，非正式结果）
```

依赖 Python ≥3.8 标准库；`pdftotext` 可选。换字段表只替换 `target-fields.json`，换材料直接放 `/input`。限制：扫描件无 OCR、跨页合并表格只按已抽出的文本行处理、图内数值仅取图注文字。版本 2.0.0（与 `main.py`/`audit.py` 的 `V` 一致；v1.0.0 的行为可用 `build --no-audit` 复现）。
