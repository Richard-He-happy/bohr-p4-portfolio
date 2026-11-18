---
name: nanopub-forge
description: 把科研论文正文拆成可独立判断真假的原子断言（atomic assertion），为每条断言绑定逐字证据片段与页码/段落/字符定位，记录来源元数据与置信度依据，并导出可机器读取的 nanopublication 结构（result.json + assertions.jsonl）。用于 Nanopublication 生成、断言拆解、证据绑定、来源追溯、结构化导出类科研阅读任务。
version: 1.0.0
---

# nanopub-forge · 论文段落 → 原子断言 + 逐字证据

## 1. 用途

输入一篇（或若干）科研材料，输出一份**逐条可判真假**的断言表：每条断言只有一个谓词，带主体、关系、宾语、极性、限定条件、**逐字证据片段**、**页码/段落/句序/字符区间**定位、来源元数据、`np_id`（可重算的去重标识）与置信度依据。

适用：Nanopublication 生成（assertion/provenance/pubinfo）、断言拆解与校验、证据绑定、结构化导出、文献知识单元抽取。
不适用：需要 OCR 的扫描件、需要读图表内部数值的任务（本 Skill 只登记题注位置并转人工/视觉核对）、需要联网核对 DOI 真伪的任务。

## 2. 触发与边界

- 触发：任务要求"把段落拆成断言 / 给结论配证据 / 输出可机读的 claim 表 / 追来源"。
- 不触发：纯翻译、纯摘要、纯排版。摘要式输出不算完成本题。
- 边界：本 Skill 用**规则法**给出高召回候选 + 可复核定位；精度由第 6 节的 Agent 复核环与 `verify.py` 兜底。不声称达到人工金标准。

## 3. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`（或任意 `*case*.json`）、`/input/task.md`、`/input/**` 材料 |
| 输出 | `--output`（默认 `/app/output`）下 `result.json`、`assertions.jsonl`、`extracted_text.json`；`verify.py --patch` 追加 `verification.json` 并回写 `verification.external` |
| 依赖 | 仅 Python 3 标准库；离线；不依赖 CWD（用 `Path(__file__).resolve().parent`） |
| 退出码 | **恒 0** |
| 先落盘 | 进材料前先写一次 partial `result.json`；结束无条件 finalize 覆盖 |
| 预算 | 默认 760s / 400 条断言上限（`--time-budget`、`--max-assertions`）；到限即降级 finalize |

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --output /app/output --patch
```

## 4. 输入发现（语义识别，不假设键名）

1. `case.json`：若不存在或解析失败，递归找 `*case*.json`；仍失败则只靠目录扫描，并在 `errors` 记录解析异常。
2. `case_id`：依次尝试 `case_id/caseId/id/name`，再试 `case/task/meta/input` 下的同名键；都没有则用输入目录名。**原样保留，不改写**。
3. `output_contract`：在 case 元数据里按语义找 `output_contract / contract / output_schema / required_output / output_fields`（可嵌套）。
4. 材料：先读 case 中出现的文件路径（`/input/x` 会被展开），再递归扫描 `/input/**`，按扩展名+魔数识别 pdf / docx / xlsx / csv / tsv / md / txt / html / json / 图片。
5. 声明了但打不开的材料 → `input_gaps`；没有文本层的材料 → `pending_human(no_text_layer)`。**不构造内容**。

## 5. 输出与字段

`result.json` 顶层：`skill, case_id, status, status_reason, task_understanding, inputs, sources, assertions, figures, counts, verification, uncertainty, pending_human, errors, degradations, changes, runtime, artifacts, output_contract_keys, output_contract_echo, contract_fields_present`，并把契约键平铺到顶层（同名以 Skill 结构为准，但键一定存在）。

`assertions[]` 每条含：`assertion_id, np_id, kind, assertion_text, subject{text,type}, relation, relation_raw, object{text,type}, polarity, magnitude, condition[], evidence[{quote, source_id, locator, location{page,paragraph,sentence_index,char_start,char_end,locator_type,json_pointer},match}], readability, confidence{score,basis[],tier}, needs_review, review_reason, source_ids[]`。

完整字段语义、受控词表、定位符规则见 **`references/field-dictionary.md`**；判据见 **`references/rules.md`**；20 条示意样例见 **`references/examples.md`**。

契约回填：`output_contract` 原样按形状回填到 `output_contract_echo`（键名不改、缺失为 `null`/`[]`、未知键保留），叶子指针写入 `output_contract_keys`，`verification.contract` 给出键数与是否取到值。

## 6. 核心流程（含 Agent 复核环）

1. **跑主流程**：`main.py` 抽文本 → 断句 → 拆从句 → 判关系/极性/条件/量值 → 绑定逐字证据 → 去重合并 → 写 partial。
2. **看文本层**：读 `extracted_text.json`；若某页为空或 `flags` 含 `page_*_no_text_layer`，该页结论一律不得写成事实。
3. **复核候选**（这一步决定质量，务必做）：
   - 对 `tier=low` / `needs_review=true` 的条目，回到 quote 所在页确认主体与关系方向；不确定就改 `readability=undetermined` 并进 `pending_human`。
   - 补 `magnitude`、`condition`、`subject.type/object.type`；把 `other_relation` 映射到受控词表或降级。
   - 按 `references/rules.md` §1 检查"是否真的只有一条断言"，把复合句拆开；按 §2 裁剪证据到最小充分片段。
   - 图表只登记位置与题注，`chart_meta` 内不可读字段保持 `null` 并进 `pending_human(vision_required)`。
4. **校验并回写**：`python3 -B scripts/verify.py --output /app/output --patch`。它会把每条 quote 重新对 `extracted_text.json` **和原始文件重新抽取的文本**各查一遍；`failures` 非空时，逐条修正或移入 `pending_human`，**不允许改原文凑命中**。
5. **定状态**：全通过且无阻断项 → `ok`；有失败/无文本层 → `partial`；一条断言都抽不出 → `insufficient_evidence`；根本没材料 → `input_error`。

## 7. 质量规则（rubric → 字段/检查/产物）

| 评分点 | 对应字段/检查 | 产物 |
|-|-|-|
| 任务完成度（拆得细） | `counts.sentences_scanned / assertions_emitted / assertions_after_dedup / duplicates_merged`；每条 `kind`+单谓词 | `result.json` |
| 结果正确性（对得上） | `evidence.quote` 逐字命中率 `counts.quote_hit_rate`；`relation/polarity` 方向；`sources.title/doi/year` 只取自输入 | `result.json` + `verify.py` 报告 |
| 结果完整性 | 断言/主体关系/证据/定位/来源/置信度/`np_id` 七类字段齐备（`assertions.jsonl` 逐行 + `verify.py` 复核） | `assertions.jsonl` |
| 结果可核验性 | `locator` + `json_pointer` + `char_start/end`，任何人可回到原文该页该句 | `extracted_text.json` |
| 增益可验证 | 同一 case 与 baseline 用同一张表对比；计数在 `counts`，不自填分数 | `result.json` |
| 创新（方法） | 关系受控词表、被动换向、否定不改向、`np_id` 确定性去重、tier 分级 | `references/rules.md` |
| 可靠体验 | 异常全进 `errors/degradations/pending_human`；缺材料/坏 JSON 仍出合法 partial | 三场景自检 |
| 生态贡献 | 字段字典 + 规则 + 20 条样例 + 两脚本可独立运行 | `references/*` |

## 8. 证据与定位规范

- `quote` 必须是 `extracted_text.json` 对应页文本的**逐字子串**（比较时仅做空白折叠）；`match="verbatim"`。
- `location` 四元：`page`（PDF 物理页，1 起）、`paragraph`（页内空行分块序）、`sentence_index`（页内句序）、`char_start/char_end`（规范化页文本区间）。
- `json_pointer` 形如 `/sources/0/pages/2/text`，直接指向 `extracted_text.json`。
- 最小充分：片段内必须同时出现主体、关系、宾语；量化断言还必须出现数值与单位；不满足就降 `tier` 或进 `pending_human`。
- 三类可读性：`directly_read`（片段内自足）/ `inferred`（跨句指代、相对从句、题注转述）/ `undetermined`（不可解，必须同时出现在 `uncertainty` 或 `pending_human`）。

## 9. 状态、不确定性与人工接管

- `uncertainty[]`：`{id, claim_id, issue, kind=conflict|not_reported|ambiguous, detail, action}`。冲突**两侧都留**，不改写任何一方。
- `pending_human[]`：`{id, target, reason, required_action, blocking}`；`reason ∈ no_text_layer | image_no_ocr | vision_required | no_material | quote_not_traceable | ambiguous_referent`。
- 未报告 ≠ 不存在：材料里没有的数值/图元/结论一律不写进断言，只进 `pending_human` 或 `uncertainty`。

## 10. 预算与断点

先写 partial → 逐材料 try/except → 到 `--time-budget` 或 `--max-assertions` 立即停扫并 finalize，`degradations` 记 `budget reached / prefix only`。任何时刻中断，`result.json` 都已是合法 JSON。

## 11. 异常与降级分支表

| 触发 | 检测 | 处置 | 落点 |
|-|-|-|-|
| 无 case.json | 路径探测 + glob | 用 task.md 与目录扫描继续 | `errors` + `degradations` |
| case.json 非法 JSON | `json.loads` 异常 | 保留错误、按扫描继续，`status=partial` | `errors` |
| 无 output_contract | 键探测 | 用 schema 默认字段，`assumed_contract=true` | `task_understanding` |
| 扫描版 PDF（无文本层） | 每页字符<50 或质量<0.55 | 不伪造文本，该页只登记、进人工 | `sources[].flags` + `pending_human` |
| 字体编码不支持 | 抽取质量低 | 换 `pdftotext`/`pypdf`（有则用），仍差则标不可解析 | `degradations` |
| 外部 PDF 工具缺失 | `shutil.which` / import | 回落内置 stdlib 抽取器 | `runtime.extractors` |
| 图片材料 | 扩展名 + 魔数 | 不 OCR、不描述内容 | `pending_human(image_no_ocr)` |
| 单材料解析失败 | 逐材料 try/except | 只降级该材料，其余继续 | `errors` |
| quote 找不到 | 固化校验 | `needs_review=true` + 复核队列，**不改原文** | `verification.quote_checks.failures` |
| 预算耗尽 | 计时/计数 | finalize 已有结果 | `degradations` |

## 12. 自检清单（交付前）

1. `python3 -B scripts/main.py --help` 退出码 0。
2. 造一个含 `output_contract` + 1 个材料的最小 `/input`，跑完确认：`result.json` 合法、`output_contract_keys` 非空、`assertions.jsonl` 非空、`counts.quote_hit_rate=1.0`。
3. 空输入：`status=input_error`、退出码 0、`pending_human` 有 `no_material`。
4. 坏 JSON：`status=partial`、`errors` 有 `json_decode`、退出码 0。
5. `verify.py --patch` 的 `failures` 为空；否则逐条修正或转人工。
6. 无 `__pycache__`/`.pyc`/临时文件；包内不出现预制答案。

## 13. 最小调用示例（示例，非正式案例结果）

`/input/case.json`：`{"case_id":"demo-001","output_contract":{"claims":null,"status":null}}`；`/input/paper.pdf` 一页。

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

示意输出（**示例**，取自合成测试材料，非任何评测案例）：

```json
{"assertion_id":"A0004","np_id":"urn:nanopub:<32 hex>","kind":"quantitative",
 "assertion_text":"Compound Z decreases tumour volume by 38 percent in mice [in mice]",
 "subject":{"text":"Compound Z","type":"compound"},"relation":"decreases","object":{"text":"tumour volume","type":"variable"},
 "polarity":"affirm","magnitude":{"value":"38","unit":"percent","raw":"38 percent"},
 "condition":["in mice"],
 "evidence":[{"quote":"Compound Z reduced tumour volume by 38 percent in mice after 21 days, n = 8, p = 0.01.",
   "source_id":"S2","locator":"S2#p1/s1",
   "location":{"page":1,"paragraph":1,"sentence_index":1,"char_start":0,"char_end":88,
     "locator_type":"page+para+sent+char","json_pointer":"/sources/1/pages/0/text"},"match":"verbatim"}],
 "readability":"directly_read","confidence":{"score":0.72,"basis":["verbatim_quote_bound","relation_mapped"],"tier":"medium"},
 "needs_review":true,"review_reason":"medium_confidence","source_ids":["S2"]}
```

## 14. 文件清单、版本、限制与维护

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明：用途、契约、流程、规则索引、异常、自检 |
| `scripts/main.py` | 主流程：发现、契约回填、断句/拆句/关系抽取、证据绑定、导出 |
| `scripts/verify.py` | 源侧层：材料读取（PDF/DOCX/XLSX/CSV/HTML/JSON/纯文本）+ 独立复核 CLI |
| `references/field-dictionary.md` | 字段字典、受控词表、定位符规范 |
| `references/rules.md` | 断言粒度、证据最小性、关系方向、去重、冲突、降级表、对照协议 |
| `references/examples.md` | 20 条示意断言、最小示例、题集模板、已知限制 |

版本：`1.0.0`（schema `np-assertion/1`）。仅标准库；无需安装。

已知限制（不掩饰）：① 规则法在公式密集、长嵌套句上会漏抽或抽偏，靠 `tier`/`needs_review` 暴露而非掩盖；② 无 OCR、无视觉能力时图表内部数值恒为 `null`；③ 表格按"首行为表头"解析，合并单元格会退化；④ `np_id` 只保证本规范内确定可重算，**不是**已注册的 nanopub 服务器标识。

维护：改规则 → 同步 `references/rules.md`；改字段 → 同步 `references/field-dictionary.md` 并升 schema 次版本；每次改动重跑第 12 节四步自检。

提交目录根另需 `GITHUB_URL.txt`（非 Skill 运行时依赖，脚本不读取）：首行写本题作品的公开仓库/目录链接，需要指定文件时第二行写包内相对路径（如 `SKILL.md`）。该链接须用未登录浏览器验证可打开；无链接时不要填占位地址，宁缺勿造。
