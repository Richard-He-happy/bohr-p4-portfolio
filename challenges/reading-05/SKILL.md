---
name: multi-doc-comparison
description: 把同一研究问题下的多篇论文落到同一套字段上，逐格抽取（值+单位+数据集+指标口径+逐字引文+locator），判定可比性、解释结论一致或冲突，并输出可复核的比较表、证据卡片与 result.json。用于 comparison-workorder 类多文档比较任务。
version: 2.0.0
---

# 多文档比较与整合（Agent 主答 + 脚本辅助 + 兜底必成）

## 1. 用途与边界

同一研究问题、多篇论文 → 一张**逐格对照**的比较矩阵：每格=某篇论文某字段的值，附单位、数据集、指标口径、逐字引文与 locator；再给出可比性判定、结论一致/冲突与归因。

做：共同字段对齐、逐篇抽取、可比性判定、冲突归因、证据卡片、可复跑表格与 result.json。
不做：把单位/数据集/指标不同的数字直接平均；替作者补值；用常识造数；把"未报告"写成 0。

产出四件（都在 `/app/output`）：`comparison_matrix.csv`（长表含 quote/locator）、`comparison_table.md`（宽表+可比性+冲突）、`evidence_cards.jsonl`、`result.json`（契约字段+状态）。

## 2. 何时用 / 何时不用

- 用：多篇材料 + 要求统一字段的 workorder（`comparison-workorder.json`、`organizer_workorder`、`fields`/`papers` 键）。
- 不用：只有一篇材料（单篇抽取）；写作/制图任务。

## 3. 运行契约

- 输入 `/input/case.json` + `task.md` + 材料（PDF/DOCX/TXT/MD/CSV/JSON…）。
- 工作目录 `/app/work`，产物 `/app/output`；脚本默认路径即如此，也可 `--input/--output/--work` 覆盖。
- `result.json` 必须**原样回填** `output_contract` 的每个字段（不改名、不漏未知字段），并带 `case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- **第一步先落盘**合法 partial `result.json`；任何异常写入 `errors`，退出码恒 0。
- 只用 Python 标准库；不联网；路径基于 `Path(__file__).parent`，不依赖 CWD。

## 4. 输入发现（语义识别，不假设键名）

1. 找 `case.json`（缺失则任意 `*.json`），读 `case_id`、`output_contract`、`task_instruction` 等；键名可能不同，按语义认。
2. 递归扫描 `/input/**`，跳过 `case*.json`、`task.md`、`*workorder*.json`；材料按**扩展名+魔数**识别（`%PDF`→pdf、`PK`+`word/`→docx、其余按文本多编码探测），不按文件名猜内容。
3. workorder 的 `fields`/`papers`/`question` 由脚本抽取并打印；论文 id 按文件名匹配材料，未匹配保留 `D1..Dn` 并在 `sources` 说明。

## 5. 工作流（四步，Agent 主导）

### 第 1 步 `init`：建索引
```bash
python3 -B scripts/main.py init
```
打印材料索引（doc_id、文件、类型、段落数、抽取器、workorder 论文 id）与 workorder 摘要；写 `work/index.json`（段落+locator+全文）与 partial `result.json`。

### 第 2 步 读材料
```bash
python3 -B scripts/main.py show --doc D1 --paras 1:40
```
**逐篇读完再填表**，不凭标题或摘要臆测。locator 形如 `p3#para7`（页/块+段号）。

### 第 3 步 写 `work/draft.json`（Agent 亲自做，这是质量主体）
按 workorder 字段逐篇抽取，schema 见第 6 节；每格必须给 `quote`（**逐字复制** `show` 输出，不许改写）+ `locator` + `unit`/`dataset`/`metric_scope`。未报告写 `status:"unreported"`、`value:null`、`note` 说明原因（如 "not reported in text"）。

### 第 4 步 `check` → `build`
```bash
python3 -B scripts/main.py check   # 引文命中/字段/覆盖校验，输出错误码与计数
python3 -B scripts/main.py build    # 生成 CVS/MD/卡片/result.json
```
`check` 报错按 `FIX [...]` 逐条改 draft 再跑；`build` 不因 check 失败而停，缺格自动补为 `unreported` 占位（不造值）并记 `degradations`。

## 6. `draft.json` schema（唯一工作稿）

```json
{
  "question": "同一研究问题",
  "papers": [{"doc_id": "D1", "citation": "Author Year", "study_type": "RCT"}],
  "fields": [{"field_id": "sample_size", "name": "样本量", "definition": "纳入分析的受试者/样本数",
              "unit": "participants", "value_rule": "取 Methods 报告的最终分析 n，不取筛选前"}],
  "matrix": [{"doc_id": "D1", "field_id": "sample_size", "value": "128", "unit": "participants",
              "dataset": "GSE12345", "metric_scope": "primary endpoint only",
              "status": "reported", "quote": "A total of 128 participants were analysed.",
              "locator": "p3#para7", "note": ""}],
  "comparability": [{"dimension": "metric", "doc_ids": ["D1", "D2"], "comparable": false,
                     "basis": "D1 报 AUC，D2 报 accuracy；口径不同，不合并",
                     "quote": "…", "doc_id": "D1"}],
  "conclusions": [{"doc_id": "D1", "direction": "increase", "strength": "significant",
                   "claim": "处理组主要终点升高", "quote": "…", "locator": "p6#para3"}],
  "agreement": {"overall": "conflicting",
                "items": [{"topic": "effect direction", "verdict": "conflicting",
                           "attribution": "condition",
                           "explanation": "D1 高剂量 8 周升高，D2 低剂量 2 周无变化；差异来自剂量与时长",
                           "evidence": [{"doc_id": "D1", "locator": "p5#para2"}]}]},
  "limitations": ["…"], "uncertainty": ["…"]
}
```
枚举：`status`=reported|unreported|not_applicable；`direction`=increase|decrease|no_effect|mixed|unclear；`verdict`=consistent|partially_consistent|conflicting|insufficient；`attribution`=sample|method|metric|condition|unresolved。

字段可缺省：`name`/`definition`/`unit`/`value_rule` 建议齐全（缺则 check 警告，影响"对得齐"）。

## 7. 证据与定位规范

- `quote` 必须能在该 `doc_id` 的抽取文本中**逐字命中**（`verify.py quote` 可单独抽查）；不许改写、拼接、翻译。找不到就降级为 `unreported` + `note`，或进 `pending_human`，绝不凑引文。
- `locator` 用脚本给的 `p3#para7` 形式；跨段引文取起始段。
- 数值单元格必须同时给 `unit`；跨数据集/跨指标的值额外给 `dataset` / `metric_scope`。
- 图表读数只能标"约"，并写误差范围；无文本可依时记 `pending_human`。

## 8. 可比性判定（先对齐，再合并）

按维度逐条判定，写进 `comparability`：`task`、`dataset`（版本/来源）、`sample`（人群/物种/n）、`material`（对象/污染物/染料）、`method`（设置/剂量/时长）、`metric`（指标/口径）、`unit`、`budget`。

- 所有维度一致 → `comparable: true`，可做数值合并/差值。
- 任一维度不一致 → `comparable: false`，给出 `basis`（哪一维不同、原文依据），**保留数值但不合并**，改为分层叙述。
- 缺失维度 → 视为不可比（写"未报告，无法确认同条件"）。

## 9. 结论一致性与冲突归因

- `consistent`：方向与强度一致且条件可比。
- `partially_consistent`：方向一致但强度/适用人群不同。
- `conflicting`：方向相反或显著性相反；**必须**给 `attribution`（sample/method/metric/condition），并说明哪一维差异导致；不能归因时写 `unresolved` 并进 `pending_human`（check 会把 `conflicting`+`unresolved` 记为错误）。
- `insufficient`：证据不足（如只有 1 篇报告该指标）。

## 10. 输出产物

| 文件 | 内容 |
|---|---|
| `comparison_matrix.csv` | 长表：source_document_id, field_id, field_name, value, unit, dataset, metric_scope, status, confidence, quote, locator, note |
| `comparison_table.md` | 宽表（字段×论文，每格带 locator）+ 可比性 + 冲突归因 + 覆盖率/复跑 |
| `evidence_cards.jsonl` | 每格一张卡：card_id, source_document_id, field_id, value/unit/dataset/metric_scope, quote, locator |
| `result.json` | 契约字段 + case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime |

## 11. 异常与降级

| 情况 | 处置 |
|---|---|
| PDF 无文本层（扫描） | 记 `degradations`，该篇转 `pending_human`（需 OCR），不猜内容 |
| `pdftotext` 不存在 | 内置 zlib 解析器兜底，locator 变为 `s1#para3` 并在 `degradations` 说明页号不权威 |
| DOCX/XLSX 以外的容器 | 不解析，记降级 |
| workorder 字段缺失 | 用内置 8 维通用字段（task/dataset/sample/material/method/metric/unit/budget），并在 `pending_human` 提示 |
| 材料与 workorder 论文对不上 | 保留 `D1..Dn`，`sources` 记录映射关系 |
| draft.json 缺失/坏 JSON | `build` 用占位行（全部 `unreported`）生成完整表格，`status=partial`，缺口写 `pending_human` |
| 输入为空 / case.json 坏 | 仍写合法 partial `result.json`（`status=input_error` 或 `partial` + `errors`），退出码 0 |
| 结论冲突无法归因 | `attribution="unresolved"` + `pending_human`，不强行合并 |

## 12. 自检清单（交付前）

1. `result.json` 契约字段齐全（`build` 打印 `unfilled contract`，应为 `none`）。
2. `comparison_matrix.csv` 行数 = 材料数 × 字段数；`reported` 行都有 quote+locator。
3. 抽查 3 格：`verify.py quote --index work/index.json --doc D1 --quote "..."`
4. 每篇覆盖"对象/数据/方法/条件/指标/结论/局限"中的可得项；未报告项有 `note`。
5. `comparability` 覆盖 workorder 维度；不可比项未做数值合并；`conflicting` 项都有具体归因。

## 13. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py init --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py show --doc D1 --paras 1:20
# Agent 写 ./demo/work/draft.json（两篇、4 字段）
python3 -B scripts/main.py check --input ./demo/input --output ./demo/output --work ./demo/work
python3 -B scripts/main.py build --input ./demo/input --output ./demo/output --work ./demo/work
```
示意输出（示例，非正式案例结果）：`status=partial docs=2 fields=4 cells=8 reported=6 coverage=0.75`，`comparison_matrix.csv` 8 行，2 行 `unreported`（作者未报告），`comparability` 2 条（dataset 不可比、metric 不可比）。

## 14. 文件与维护

```
SKILL.md                     本文件
scripts/main.py              init / show / check / build（≤20KB）
scripts/verify.py            抽取核心 + 引文/草稿校验（≤20KB）
references/field-dictionary.md  统一字段字典、取值规则、可比性判据
references/checklist.md      质检清单、冲突归因模板、draft 示例
```
版本 2.0.0：Agent 写工作稿，脚本只做确定性抽取与校验；`build` 自带兜底，缺稿也出完整空表 + 缺口清单。维护：新增论文重跑 `init` 并在 draft 增列；字段改动同步 `references/field-dictionary.md`。
