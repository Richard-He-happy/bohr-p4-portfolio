# 方法与使用手册（writing-03 v1.0.0）

## 1. 证据强度口径（四因子，固定）

| 因子 | 取值 | 分值 |
|---|---|---|
| 研究设计 | 系统综述/荟萃分析、指南/共识、RCT | 3.0 |
| | 队列、病例对照 | 2.0 |
| | 横断面/调查 | 1.5 |
| | 叙述性综述、预印本、体外/动物 | 1.0 |
| | 病例报告/个案 | 0.5 |
| | 未标明设计 | 1.0 |
| 样本量 | ≥1000 | 2.0 |
| | 100–999 | 1.5 |
| | 10–99 | 1.0 |
| | <10 | 0.5 |
| | 未报告 | 0 |
| 重复验证 | 同一论断有 ≥2 个独立来源 | +1.0 |
| 冲突证据 | 存在方向相反的来源 | −1.0 |

**阈值**：≥5.5 高；3.5–5.4 中；1.5–3.4 低；<1.5 不足。

**封顶规则**：预印本 ≤4.0（最高"中"）；n<100 ≤3.4（最高"低"）；仅摘要可核的来源最高"中"。

**使用纪律**：
- 不因"看起来重要"上调；不因"结论符合预期"上调。
- 单篇小样本不得写成领域共识；观察性设计不得写成因果。
- 材料未报告样本量时如实写"未报告"，不估算。

## 2. 限定语映射（成稿必须与强度相称）

| 强度 | 中文 | English |
|---|---|---|
| 高 | 多项证据一致表明 | Evidence indicates that |
| 中 | 现有研究提示 | Studies suggest that |
| 低 | 初步证据提示 | Preliminary evidence suggests |
| 不足 | 材料尚不足以判断 | The material cannot determine |

低/不足强度句若已含"可能/提示/初步/尚/may/suggest/prelim"，不再叠加限定语，避免双重弱化。

## 3. 过度推断下调规则（写进 change_log）

| 触发 | 下调为 | 适用条件 |
|---|---|---|
| causes / leads to / proves / demonstrates that / confirms that | is associated with | 材料无随机化或干预对照 |
| 导致 X（中文） | 与 X 相关 | 同上 |
| 证明了 / 证实了 / 确证 / 必然 | 提示 | 观察性或单一来源 |
| all / always / never | in the material reviewed | 单篇或小样本 |
| 所有 / 全部 / 总是 / 从来 | 在所纳入材料中 | 同上 |

只改措辞、不改数值与单位；`original_quote` 与 `revised_quote` 同时入账，`human_confirm: true`。

## 4. 论断-来源匹配（可解释的确定性流程）

1. **术语归一**：按 `lexicon_zh_en.txt` 把中文短语替换为英文概念词（长词优先），使中文原稿能与英文文献对齐；词表没有的概念保留中文 bigram。
2. **相似度**：`|A∩B| / sqrt(|A|·|B|)`（英文词 + 中文 bigram，去停用词），数字重叠 +0.08。
3. **引用锚点优先**：论断正文带 `[n]`（或 `［n］`）时，先把文献表第 n 条映射到具体材料文件（DOI 命中或标题相似度 ≥0.45），匹配优先在该文件内进行，阈值放宽到 0.05。
4. **多来源**：主来源之外，相似度 ≥ max(阈值, 主来源×0.72) 且来自不同文件者，追加为独立来源（最多 3 个），用于"重复验证"因子。
5. **失败即承认**：低于阈值 → `source_id=null`、`strength=不足`、成稿改待核表述、进 `pending_human`。

## 5. 使用步骤

```bash
# 1) 准备输入：/input/case.json（含 output_contract）、/input/task.md、/input/artifacts/*
# 2) 主流程（无参默认 /input -> /app/output）
python3 -B scripts/main.py
# 3) 独立复核（重读材料，逐字校验与 join 校验）
python3 -B scripts/verify.py
# 4) 查看产物
ls /app/output   # result.json, evidence_driven_draft.md, claims.json, evidence_table.json,
                 # evidence_strength.md, reference_check.md, uncertainty_notes.md,
                 # pending_human.json, verification.json
```

预期：`verify.py` 输出 `verify PASS` 且各项 `True`；`result.json` 的 `status` 与 `pending_human` 一致。

## 6. 异常处置表

| 输入情况 | 脚本行为 | 用户可见标识 |
|---|---|---|
| 只有摘要 | 正常出表，`abstract_only: true` | 强度最高"中"，`uncertainty` 提示 |
| 无参考文献表 | 照常出证据表 | `reference_check.md` 记"缺口"，`pending_human` 一条 |
| DOI/年份缺失 | 只转录已有字段 | `reference_check.md` 的"缺失"列 |
| 摘要与原文矛盾 | 两条都入表并标冲突 | `conflicts[]` + 成稿 however 句 |
| 证据相互冲突 | 不取平均，保留冲突 | 强度下调 + `claims_with_conflict` 计数 |
| xlsx/pptx/doc | 返回 `unsupported` | `degradations` + `pending_human` 建议转 CSV/文本 |
| 扫描件 PDF | `read_method: none` | `degradations` + 需 OCR |
| 图像材料 | 不臆测内容 | `pending_human` |
| 目录不可写 | 回退工作目录 | `errors` 记录 |
| 无 case.json | 按材料目录尽力推断，5 字段兜底 | `errors` + `status=partial` |
| 空目录 / 坏 JSON | 写合法 partial `result.json` | `status=input_error/partial`，退出码 0 |

## 7. 最小示例（示例，非正式案例结果）

输入 `demo/input/`：`case.json`（`case_id: EXAMPLE-1`）、`artifacts/section_draft.md`（2 句，含 1 处因果越级）、`artifacts/source_A.md`（英文摘要，队列 n=412）、`artifacts/source_B.md`（RCT，no significant difference）、`artifacts/references.md`（2 条）。

```bash
python3 -B scripts/main.py --input demo/input --output demo/output
```

示意输出（**示例，非正式案例结果**）：

```
done partial claims=5 rows=7 quote=6/6 pending=1
```

- `claims.json`：5 条（其中 1 条无法匹配来源）
- `evidence_table.json`：7 行，6 行逐字命中，冲突 0 条（本例方向一致）
- 成稿：因果句被下调为"与……相关[1][2]"，句末引用编号可解析
- `result.json`：`status=partial`（1 条待核）、`support_rate=0.8`、`overclaim_downgrades=1`

## 8. 已知限制

1. **不做联网核验**：DOI/期刊/年份只转录材料，`reference_check.md` 明确标"未联网核验"。真实性核验需在联网环境用 Crossref/PubMed 复核。
2. **相似度为词面近似**：同义改写（尤其跨语言、无词表覆盖的术语）可能召回不足，表现为"部分支撑"或"无直接支撑"，此时一律标待核而不硬凑。
3. **强度是启发式分级**：设计/样本量靠关键词与数字抽取，不替代方法学审读；`strength_basis` 给出分值明细以便复核。
4. **参考文献编号按首次引用重排**：与原文编号可能不同；`材料内文献表（原样转录）`保留原始条目以便对照。
5. **图像、扫描件、Office 表格不解析**：按第 6 节降级，需人工或主 Agent 补充。

## 9. 维护与回归

- 改强度阈值：同步 `scripts/verify.py::grade()` 与本文第 1 节，二者必须一致。
- 扩词表：向 `lexicon_zh_en.txt` 追加确定同义的术语，避免强行等同不同概念。
- 回归：`main.py` → `verify.py`，要求 `quote_verbatim/claim_join/row_fields/citation_resolvable` 全为 `True`。

## 10. v2 资产层：金标准、差分与自检（口径固定）

`scripts/gold.py` 每次运行重算一份**独立期望值**再与产物逐项比对；三处实现与 v1 不同，用于交叉发现错误：

1. **论断-来源匹配**：不用余弦相似度，改用**内容项覆盖率** `|T(论断)∩T(来源)|/|T(论断)|`（T 为中英归一后的词项集合）+ 数字核对；判定门槛 `>=0.30` 才算"有期望来源"，`>=0.45` 才算"直接支撑"。原始引用锚点 `[n]` 仍优先（文献表→文件：DOI 精确命中优先，否则条目内容词覆盖率 `>=0.45`）。
2. **强度分级**：`band()` 独立实现四因子表（§1），与 `verify.grade()` 互为校验；两者不一致即判 `GS-06` 偏差，说明有一侧实现与文档口径偏离。
3. **数字一致性**：成稿正文（不含标题行、`[n]`、`C001` 类内部编号）的强数字必须在**来源材料**（排除待改稿自身）中找到同值；比较以数值为准（中英单位可不同），百分号另行校验；裸 1-2 位数字（序数/编号）不计。

16 项检查、权重与判定规则全部写进运行产物 `golden_standard.json.items[]`：每项含 `requirement / expectation / weight / severity / method / basis{locator,quote,verified}`。

| 维度 | 检查项 |
|---|---|
| 找得到 | GS-01 论断切分（原稿句全覆盖 / 取材模式单句） |
| 对得上 | GS-03 逐字命中、GS-05 来源对应、GS-08 数字、GS-09 引用编号与著录、GS-16 材料外 DOI |
| 说得准 | GS-06 强度复算、GS-07 语气相称、GS-10 越级因果、GS-11 未支持标注、GS-12 冲突保留 |
| 复得现 | GS-02 join、GS-04 locator 偏移精确（`chars:a-b` 切片须等于 quote） |
| 契约/可靠 | GS-13 契约字段、GS-14 状态诚实、GS-15 来源 sha256 溯源 |

判定三级：`达标 / 偏差 / 缺失`，另设 `不可判定`（本次材料不足以判，例如材料无文献表时著录无法溯源——**不报达标**）。`acceptance.internal_score` 是加权符合度，仅供本地回归，**不是平台评分**。

## 11. v2 自检与复现

```bash
python3 -B scripts/main.py   --input /input --output /app/output   # 主流程 + 资产层
python3 -B scripts/verify.py --input /input --output /app/output   # 二次复核 -> verification.json
python3 -B scripts/gold.py   --input /input --output /app/output   # 只重算金标准与差分
```

`self_check.json` 的 `fallback_gates` 是**真实子进程**结果：`--help`、空输入、坏 JSON、无 `output_contract` 各跑一次，记录退出码与 `result.json` 合法性。子进程用 `W3_ASSET_GATES=0` 抑制再生成，避免递归。

v2 特有的两条限制（其余见 §8）：

1. **冲突检测依赖词面重叠**：跨语言的"方向相反"来源（中文论断 vs 英文 no significant difference）可能漏检，`GS-12` 会呈现"受检 0 条"。漏检不误报，但会低估冲突。
2. **期望来源仍是词面近似**：同义改写或无词表覆盖的术语会召回不足，表现为 `GS-05` 偏差或 `不可判定`，需人工裁决。
