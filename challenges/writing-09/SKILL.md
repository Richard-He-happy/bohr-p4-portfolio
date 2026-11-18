---
name: results-discussion-writer
description: 把实验材料（数据表、图注、统计输出、文本/JSON/PDF 文本层）写成 Results 与 Discussion 分离的可投稿章节。Agent 先写 work/draft.json 工作稿，脚本以逐字引文核验每个读数，按图注补引用，检查因果词/显著性/局限层级，再成稿并输出 results_map / evidence_map / preserved_facts / change_log / result.json。适用于"数据已在手、图表已画好"的章节起草与自查。
version: 3.0.0
---

# 结果与讨论章节写作（writing-06，v3）

## 1 用途与边界

生成 **Results 与 Discussion 分离** 的可编辑章节（`manuscript.md`），并给出每个读数的来源定位：

- **Results**：只写观察到的读数（值 + 单位 + 条件 + 离散度/统计量 + 图/表号），不做解释。
- **Discussion**：解释、与文献/本研究数据的关系、因果边界、局限。
- **核验**：正文里出现的每个数字，必须能在材料的某条逐字引文里找到（或来自显式 `derived` 公式）；找不到就报 `number_unverified` 并给出候选 locator。

不适用：需要外部文献检索的综述、需要重算统计的数据分析、需要生成图表本体的绘图任务。

已知边界（如实说明，不假装支持）：

| 材料 | 支持程度 |
|---|---|
| CSV / TSV 数据表 | 完整：逐行 locator、列角色识别（剂量/时间、测量值、离散度、n） |
| 文本 / Markdown / JSON（图注、统计输出、材料 JSON） | 完整：按段落或 JSON 行定位 |
| PDF | **只取未被压缩编码的文本层**；多数 PDF 需先导出文本/CSV，否则列入 `pending_human` |
| 位图（PNG/JPG/SVG） | 不做 OCR；提供 `#fig` 占位与"目视近似需标约"的缺口提示 |
| DOCX / XLSX | **未解析**，会作为 `binary` 记入缺口 |

## 2 运行契约

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`（递归兜底 `case*.json`）+ `/input/**` 材料 |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`check_report.json`） |
| 产物 | `/app/output/manuscript.md`、`results_map.json`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`、`result.json` |
| 脚本 | `scripts/main.py`（`init`/`check`/`build`）、`scripts/core.py`（引擎） |
| 依赖 | Python 3 标准库；无网络；不依赖当前工作目录 |
| 退出码 | **恒为 0**；任何异常都会留下合法 `result.json` |

`result.json` 原样回填输入 `output_contract` 的全部字段（不改名、不遗漏，缺值 `null`/`[]`），并附 `case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`。

## 3 四步流程

```bash
python3 scripts/main.py init  --input /input --work /app/work --out /app/output
#   打印材料清单、每张表的全部数据行（含 locator）、图注行、缺口；写 work/index.json + partial result.json
#   → 自己写 /app/work/draft.json（schema 见 §4）
python3 scripts/main.py check --input /input --work /app/work --out /app/output
#   校验逐字引文、数字可溯源、Results/Discussion 分离、显著性、局限层级；有 error 就改 draft 再跑
python3 scripts/main.py build --input /input --work /app/work --out /app/output
#   拼装 manuscript.md + 五份映射 + result.json；无 draft 时用材料生成完整兜底稿
```

`init` 已经把 partial `result.json` 写好，随时中断都合法。**单次回复内尽量跑完 init→draft→check→build**；接近时间上限立即 `build`。

## 4 工作稿 schema（`/app/work/draft.json`）

```json
{
  "case_id": "原样",
  "title": "章节标题",
  "language": "zh|en",
  "results":    [{"heading": "剂量依赖性活力下降", "xref": ["Fig. 1A"], "paragraphs": ["……"]}],
  "discussion": [{"heading": "与既有证据的关系", "xref": [], "paragraphs": ["……"]}],
  "limitations": ["方法层：…… 因此不能……", "统计层：……"],
  "evidence": [{"id": "e1", "quote": "逐字原文", "locator": "data/viability.csv#r1"}],
  "derived":  [{"value": "55.3", "formula": "94.2-38.9", "note": "端点变化"}],
  "preserved_facts": [{"fact": "0.5 µM 组 94.2%（SD 4.1）", "quote": "row 2: dose_uM=0.5 | viability_pct=94.2 | sd_pct=4.1 | n=3", "locator": "data/viability.csv#r1"}],
  "changes": [{"action": "table cell -> sentence", "original_quote": "viability_pct=94.2", "revised_quote": "94.2% (SD 4.1, n = 3)", "reason": "转写为叙述值"}],
  "pending_human": ["作者确认 Fig. 1A 面板编号"],
  "uncertainty": ["未给误差棒定义"]
}
```

- `results`/`discussion` 至少各 1 节；正文写在 `paragraphs`，一段一个字符串。
- `quote` 必须是材料的**逐字**片段（脚本做 NFKC + 空白归一后比对）；`locator` 见 §5。
- 自己算出的数（差值、百分比、fold change）放 `derived` 并给公式，`build` 会用它放行对应数值。
- 目视读图（图注没给数值）加 `"approx": true`，正文写"约 / approx."，精度不超过坐标刻度。
- 最小模板：把上面这段改成自己的数值与 locator 即可。

## 5 locator 语法

| 材料 | 形式 | 例 |
|---|---|---|
| 文本 / JSON / DOCX 段落 | `<相对路径>#p<段号>` | `material.json#p3` |
| CSV / TSV / XLSX 行 | `<相对路径>#r<行号>`（表头为 r1） | `data/viability.csv#r2` |
| PDF 页 | `<相对路径>#pg<页号>` | `paper.pdf#pg4` |
| 图件 | `<相对路径>#fig` | `data/fig1.png#fig` |

行号/段号以 `init` 打印的 `loc :: text` 为准，直接复制，不要凭记忆写。

## 6 Results 只写观察

一段一个发现，按图序或按问题组织。每个读数写全：**值 + 单位 + 条件 + 离散度或统计量 + 图/表号**。

- 必须带：`n`、误差棒含义（SD/SEM/CI）、检验名与 p 值（材料给出时）。
- 禁止：`导致/造成/因为/由于/机制/证明/证实/调控/驱动` 与文献比较（`check` 报 `results_causal`，属 error）——这些属 Discussion。
- 阴性/不显著结果照写：`p = 0.41，未与溶剂对照分离`；不省略、不改写成"趋势"。
- 未达显著的差异只写方向与幅度，不写"显著"（`sig_without_stat`）。

## 7 Discussion 承担解释

三拍推进，`build` 的兜底稿也按这三拍生成：

1. **本研究数据支持什么**——回指 Results 的具体读数，只到数据允许的强度。
2. **与已有证据的关系**——一致/不一致/部分一致及可能原因；材料没有文献时**明确写出**"材料未提供可对照文献"，不堆引用。
3. **边界与替代解释**——相关≠因果；机制推测标为推测；给出能证伪该解释的实验。

`limitations` 至少 2 条，覆盖四层：方法（单一检测、单时间点）、样本（n、重复、代表性）、测量（误差棒含义、读数精度）、统计（多重比较、效应量、缺失检验）。要写"因此不能得出什么"，不写"样本量有限"这类空话。

## 8 因果梯度与语气

| 级 | 证据要求 | 允许表述 |
|---|---|---|
| 相关 | 观察性共变 | `与……相关` / `associated with` |
| 提示 | 剂量依赖、时间先后、方向一致 | `提示` / `与……一致` / `suggests` / `consistent with` |
| 因果 | 干预/敲除/救援 + 对照 | `导致` / `causes` / `leads to` |

材料只有观察数据时最高到第二级。`证明/证实/首次/确证/demonstrated/confirm` 属过度断言（`overclaim`，error）。否定句（"不能证明"）不误报。

## 9 `check` 的判据（error 必须清零）

| 代码 | 级别 | 含义 / 改法 |
|---|---|---|
| `draft_missing` / `schema` | error | 草稿缺失或 `results`/`discussion` 为空 |
| `evidence_bad` | error | 引文缺失，或不是逐字原文；`suggest` 给出候选 locator+原文 |
| `number_unverified` | error | Results 中的数字找不到逐字来源；`suggest` 列出含该值的行 |
| `results_causal` | error | Results 出现因果/机制词或文献比较，移到 Discussion |
| `sig_without_stat` | error | 写"显著"但没有检验或 p 值 |
| `overclaim` | error | Discussion 过度断言，改成 `consistent with` / `suggests` |
| `no_limitations` / `limitations_weak` | error / warn | 局限为空；或条数<2、缺层 |
| `discussion_no_boundary` | warn | Discussion 没有因果边界句 |
| `discussion_new_number` | warn | Discussion 出现 Results 里没有、也无来源的数字 |
| `unit_missing` / `evidence_fix` | warn / info | 数字缺单位；locator 偏移（已给出正确位置） |

`check` 会打印 `errors/warnings`、证据与数字统计，以及每条问题的 `@locator` 与候选原文。

## 10 缺口与人工确认

材料缺什么就写进 `pending_human`，不要补造：缺图注→不写图号语义；缺统计量→不写 p 值；缺误差棒定义→不解读离散度；读数冲突（表 vs 图注）→以数据表为准并在 `pending_human` 记冲突；文献查不到→不写该文献。`uncertainty` 记录"做了但不确定"的判断（面板归属、单位换算、目视读数）。

## 11 异常降级

| 现象 | 脚本行为 | Agent 应做 |
|---|---|---|
| 无 `case.json` | 递归索引，契约回退为 4 个默认字段 | 仍按材料写稿 |
| `case.json` 坏 JSON | 记 `errors`，继续索引其他材料 | 照常写稿 |
| 无 `draft.json` | `build` 用材料生成**完整**兜底稿（Results 读数句 + Discussion 三分段 + 局限） | 交付即可用，但需改写润色 |
| draft 缺 `results`/`discussion`/`limitations` | 只补缺的那一节，记 `degradations` | 检查补写处是否符合预期 |
| PDF 文本层不可解压 | 记 `PG` 占位 + 缺口 | 改用表格/图注，或 `pending_human` |
| 单个材料解析失败 | 只降级该材料 | 其余照常 |

兜底稿的每个数字都来自带 locator 的逐字引文，`numbers_verified` 应等于 `numbers_total`；`status` 会是 `partial`，因为叙述强度与文献对照仍需作者补。

## 12 文件清单与维护

```
SKILL.md                        本文件（用途、契约、schema、规则、降级）
scripts/main.py                 CLI：init / check / build，索引、审计、成稿、写 result.json
scripts/core.py                 引擎：读数抽取与数字核验、表格列角色、缺口扫描、兜底叙述、成稿拼装
references/schema.md            draft.json / result.json / results_map 字段与 locator 细则
references/writing-rules.md     句式模板、因果词表、局限清单、检查清单
```

改词表要同步 `references/writing-rules.md` 与 `main.py` 的 `BAN/OVER/LAYERS`；改 schema 保持向后兼容（缺字段按空处理）。版本 3.0.0。

## 13 最小调用示例（示例，非正式案例结果）

输入：`/input/case.json`（契约含 `deliverable`/`results_map`/`preserved_facts`/`evidence_map`/`change_log`/`limitations`）+ `data/viability.csv`（列 `dose_uM,viability_pct,sd_pct,n`）+ `material.json`（图注与 ANOVA）。

```bash
python3 scripts/main.py init --input /input --work /app/work --out /app/output
#  case_id SYNTH-001 | contract(6): deliverable, results_map, ...
#  [table] data/viability.csv: dose_uM | viability_pct | sd_pct | n (4 rows)
#     data/viability.csv#r1 :: row 2: dose_uM=0.5 | viability_pct=94.2 | sd_pct=4.1 | n=3
#     data/viability.csv#r4 :: row 5: dose_uM=10 | viability_pct=38.9 | sd_pct=6.0 | n=3
#  [caption] material.json#p2 :: "figure_caption": "Fig. 1A. Viability ... mean +/- SD, n = 3 ..."
#  [gap] no_lit: No literature: no consistency claims.
# → 写 work/draft.json（2 个 Results 段 + 3 个 Discussion 段 + 4 条局限 + 4 条 evidence）
python3 scripts/main.py check
#  errors=0 warnings=0 | evidence 4 ok/0 bad | numbers 11/11
python3 scripts/main.py build
#  status=ok mode=agent-draft contract=6/6 | 1578B | results 2/3 | lim 4 | numbers 11/11
```

成稿结构：`# 标题` → `## 1. Results` → `### 1.1 …` → `## 2. Discussion` → `### 2.x …` → `### Limitations`。示例数值仅演示接口，不代表任何真实实验。

## 14 自检清单（交付前）

1. `python3 scripts/main.py --help` 退出码 0。
2. `init` 打印出材料、表行、图注与缺口；`work/index.json` 存在。
3. 造一个无 draft 的输入跑 `build`：`status=partial`、`numbers_verified == numbers_total`、`manuscript.md` 含两节。
4. 空输入目录、坏 `case.json`：仍生成合法 `result.json`，退出码 0。
5. 故意把某读数改成材料里没有的值：`check` 报 `number_unverified` 并给出候选 locator。
6. 确保无 `__pycache__`/`.pyc`，无预制正式答案。
