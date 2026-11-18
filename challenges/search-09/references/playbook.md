# 操作手册（playbook）· v1.0.0

面向"第二个人如何按记录复核出同一判断"。本文只写可执行的动作与判据，不写愿景。

## 1. 定位规范（locator）

| 层级 | 字段 | 规则 |
|---|---|---|
| 页 | `locator_page` | PDF 抽取的物理页序号，从 1 起；`pdftotext -layout` 的 `\f` 分页与之一致 |
| 章节 | `locator_section` | 由行首标题匹配得到：`Abstract, Introduction, Methods, Materials and Methods, Patients and Methods, Results, Discussion, Conclusion(s), Limitations, Statistical analysis, Funding, Conflict of interest, Data availability, References, Supplementary`；匹配不到记 `unknown` |
| 字符 | `char_start` | 归一化全文（去多余空白、统一连字符）中的起始偏移；`quote` 是该串的子串 |
| 表图 | `locator_table` / `locator_figure` | 检测 `Table 1`~`Table 9`、`Figure 1`~`Figure 9` 就近出现时填编号，否则 `null` |
| 区 | `evidence_scope` | `abstract` / `methods` / `results` / `discussion` / `other`：由该句所属章节映射 |

归一化：`re.sub(r"\s+"," ", text)`、把 `‐‑‒–—` 统一为 `-`、去掉 `ﬁﬂ` 连字、`\u00a0` 转空格。**只做这些，不删词、不改数字**，保证 quote 仍是原文子串。

## 2. 证据抽取顺序（三选一取先命中）

1. `pdftotext -layout`（poppler，若 `shutil.which("pdftotext")` 命中）；
2. 可选库 `pypdf` → `fitz`（`try/except ImportError`，缺失不影响主流程）；
3. 内置抽取器：`zlib` 解压 `FlateDecode` 流 → 解析 `BT/ET` 中的 `Tj/TJ/'/"` 操作数 → 处理 `\(\)\\` 转义与 `-`/数字位移（间距变化不插空格，除非位移 > 阈值）。此路径只对文本层有效字体可靠，CID 字体可能产出乱码 → 用"可打印字符占比 < 0.85 或元音缺失"判定乱码并降级。

任何路径失败：`text_source:"none"`，不猜内容，`pending_human:["ocr:<doc_id>"]`。

## 3. 探针（probe）编写规则

- 一律小写、去标点后匹配；词组内部保留空格（"95% ci" 写成 `"95% ci"` 与 `"95%"` 两种形态各列一次）。
- 一个条目给 5–15 个同义/近义表述，宁可多不可少：漏词的代价是假 `not_reported`。
- 避免过泛词单独成条（`study`、`patients`），否则满篇命中，等级失去区分度。
- 区域约束用 `req`：方法学细节（随机化、调整、样本量）`methods`；数值（HR/CI）`results`；态度性内容（局限、资助）`any`。
- 新增条目：只改 `references/rubric.md` 的 `items` 块并递增 `rubric_version`；脚本每次运行读取，无需改代码。
- 词表取向：英文为主，中文常见表述（"纳入标准""敏感性分析""随访""缺失""注册号"）以子串形式另列；不要在探针里写正则（脚本按字面匹配，避免转义歧义）。

## 4. 缺口分类（写进 `missing[]` / `uncertainty[]`，不要混用）

| 类别 | 例子 | 落到哪 |
|---|---|---|
| 输入缺失 | 无 `query_log`、无题录文件 | `missing` |
| 全文缺失 | 只有摘要、PDF 未随输入给出 | `missing` + `coverage.gaps` |
| 文本不可解析 | 扫描件、CID 乱码、加密 PDF | `degradations` + `pending_human` |
| 元数据缺失 | 无 DOI、无年份、无期刊 | `candidates[].flags` + `missing` |
| 元数据冲突 | 同 DOI 两版年份/期刊不符 | `candidates[].flags:"metadata_conflict"` + `uncertainty` |
| 接口/权限异常 | 检索响应含 `error`/`429`/`403` | `queries[].status:"error"` + `errors` |
| 证据未命中 | quote 回查失败 | `pending_human[].reason:"quote_not_found"` |
| 类型未识别 | 设计判不出 | `uncertainty` + `T` 组 `unappraisable` |

## 5. 人工复核与裁决（双人协议）

1. **独立评**：两名评审各自用同一 `appraisal.csv`，只看 `evidence_quote + locator_page`，不看对方列。
2. **比对**：按 `doc_id + item_id` 对齐，统计一致率；对 `judgment` 不一致项逐条回原文该页该句。
3. **裁决**：以"该句是否支持该判定"为准，不以资历或多数票为准。裁决结果写入 `adjudication` 列（`agree_original` / `revise_to:<judgment>` / `exclude_item`）。
4. **沉淀**：分歧若源于探针漏词 → 扩词表；源于条目歧义 → 拆条目或补判据；源于原文不可读 → 记 `pending_human`。每次修订递增 `rubric_version`，旧版本结果保留以便追溯。
5. 脚本重跑默认保留已填的 `human_override`（`--keep-overrides`），不覆盖人工结论。

可重复性自证：同输入连跑两次，比对 `runtime.determinism.sha1`（对 `appraisal_items + candidates` 取哈希）与 `appraisal.csv` 全文；不一致说明存在非确定性（如依赖文件遍历顺序），必须修。

## 6. 基线对照（增益可验证性的做法）

`result.json.metrics.naive_reference` 给出"摘要式整体评价"的内部模拟参照值（无维度拆分、无定位、无等级轨迹），与本 Skill 实测 `metrics` 并排放，用于说明增益方向：

| 指标 | 含义 | 基线典型值 |
|---|---|---|
| `dimension_coverage` | 四类维度中至少有一条判断的维度数 / 4 | 1/4（只有整体评价） |
| `evidence_anchor_rate` | 有 quote + 页码的行 / 总行 | ~0 |
| `recheckable_rows` | 可被第二人按记录复核的行数 | ~0 |
| `abstain_rows` | 明确弃权（承认证据不足）的行数 | 0 |

该参照值是**本 Skill 内部的对照模拟**，只在 `metrics.naive_reference` 里给两个常数（`dimension_coverage:0.2`、`evidence_anchor_rate:0.0`），不与平台白板数值混用，也不声称代表官方基线得分；正式对照由平台按基础 Agent/Skill Agent 同案运行生成。

## 7. 失败经验（来自构建期实测）

- **页码必须实测**：早期版本 `locator_page` 用 `1 + sum(...)` 导致整体 +1 页；现按 `max(1, 落在 off 之前的页首个数)` 计算，并用"quote 落在该页窗口内"做硬校验。
- **小数点别当句号**：句子切分原用 `[.!?]`，把 `3.2 years` 切成两句，证据被截断；现要求句点后必须空白或行尾。
- **别用摘要冒充全文**：早期版本在 `text_source` 判定出错时仍给出 `reported`，导致页码指向摘要。现在强制：`evidence_scope=="abstract"` 且 `req!="any"` → 一律 `partially_reported`。
- **别让 `not_reported` 吞掉"没读到"**：只有 `text_source` 以 `pdf:`/`docx:`/`text:` 开头（全文）才允许 `not_reported`；摘要模式一律 `unappraisable`。
- **PDF 抽取失败要单文档降级**：一个损坏 PDF 曾让整批评价为空。现在每文档独立 `try`，异常写 `degradations` 并继续。
- **不要遍历顺序决定输出**：`os.walk` 顺序不稳定会让重跑哈希不一致；所有文件按 `str(path)` 排序后处理。
- **契约字段别丢**：`output_contract` 里出现脚本不认识的键时，早期版本直接丢掉；现在一律保留 `null` 并登记 `output_contract_unfilled`。

## 8. 自查命令

```bash
python3 -B scripts/appraise.py --input /input --output /app/output           # 期望 exit 0
python3 -B scripts/appraise.py --input /tmp/empty --output /tmp/out_empty    # 空输入仍 exit 0
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['selfcheck'])"
```

确定性：`runtime.determinism.sha1` 是对 `appraisal_items + candidates` 的哈希；同输入重跑应得同一值（已实测两次一致）。

`selfcheck` 检查项：契约键是否全部拿到值 / `verified` 行是否有 quote 且 `locator_page ≥ 1` / `unappraisable` 行是否有 `abstain_reason`。其余人工核对按 SKILL.md §13 的五步执行。
