# nanopub-forge · 抽取与校验规则（rules v1.0.0）

配套实现：`scripts/main.py`（抽取）、`scripts/verify.py`（确定性校验）。本文件给判据，脚本给执行；两者冲突时以本文件的判据为准，并应在 `changes` 中登记偏离。

## 1. 断言粒度判据（"拆得细"）

一次输出**一条**断言，当且仅当以下四条同时成立：

1. **单一谓词**：只含一个可判断的关系。含 `and`/`同时`/`并且` 连接的两个谓词 → 拆两条（共享主语，各自保留条件）。
2. **可判真假**：能对原文提出"是/否"问题并回答。*"X 可能参与调控"* 属可判（低置信），*"X 很重要"* 属不可判 → 不进断言，进 `pending_human`。
3. **主体与宾语可指认**：`subject.text`/`object.text` 必须能在被引片段中定位到字面锚点。片段里是代词且原文前文无法唯一消解 → `readability=inferred` 且 `needs_review=true`，不得默认猜。
4. **限定条件不丢**：物种/细胞系/剂量/时间/体系/比较对象/样本量若出现在原句，必须进 `condition`；若条件只在**上一句**给出，则沿用并在 `basis` 记 `cross_clause_merge`。

拆解边界实例（判据，不是案例答案）：

- 并列：`A increased B and decreased C` → `A increases B` + `A decreases C`（不写成 `A affects B and C`）。
- 因果链：`A induced B, which in turn reduced C` → `A activates B` + `B decreases C`；不得合并为 `A decreases C`（那是推断，须 `inferred` 且 `basis` 含 `cross_clause_merge`）。
- 让步/对比：`Although A was high, B remained low` → 两条，且各自 `condition` 记 `although` 从句设定的语境。
- 相对从句：`A, which binds B, ...` → `A binds B`，`basis` 含 `subject_inherited`。
- 方法句：`Proteins were separated by SDS-PAGE` → `kind=methodological`，`relation=uses_method`，不得写成机制断言。
- 二手引用：`Previous studies reported that A inhibits B` → 可产出断言，但 `basis` 含 `secondhand_citation`、`tier=medium`，且 `assertion_text` 须保留"前人报道"限定（不得冒充本文发现）。

## 2. 证据最小充分性判据（"对得上"）

`evidence.quote` 必须满足：

1. **逐字**：是来源文本的连续子串（仅允许空白折叠、软连字符/连字符断行归一、连字 `ﬁ ﬂ` 归一）。任何拼写"修正"都算不合格。
2. **最小**：删去片段首尾任意一个从句后，若主体、关系、宾语仍然齐全，则该片段不最小 → 继续裁剪。片段长度目标：1 句，最多 2 句（跨句仅在必要时，且 `readability=inferred`）。
3. **充分**：片段内必须同时出现主体、关系词、宾语；量化断言还必须在片段内出现数值与单位。缺任一要素 → 不得把别处数值补进来，只能降 `tier` 或进 `pending_human`。
4. **单一来源**：一条 `evidence` 项只绑定一个 `source_id` 与一个 `location`；多来源支撑就多条 `evidence`。
5. **不可用即拒**：quote 无法在原文命中 → `needs_review=true`、`review_reason=quote_not_traceable`，并进 `pending_human`；**禁止改写原文凑命中**。

## 3. 关系与方向（"主体不混淆"）

- 被动语态交换方向：`B was reduced by A` → subject=A，object=B，`basis+=passive_voice_swapped`。
- `A is encoded by B` → subject=B，object=A，`relation=encodes`。
- 关联≠因果：`associated_with` 不得输出为 `causes`；原文用 `may cause`/`could lead to` 时保留 `relation=causes` 但 `basis+=hedged_language`、`confidence.score` 降档。
- 否定辖域：`A did not increase B` → `polarity=negated`，`relation` 仍取 `increases`（不造 `decreases`）。`neither ... nor` 两侧各一条，均 `negated`。
- 比较方向：`X was higher in cases than controls` → subject=`X in cases`，`relation=differs_between`，`object=controls`，`condition` 记 `compared with controls`。

## 4. 去重与合并

规范化键 = `(lower(subject.text) 去冠词/标点, relation, polarity, lower(object.text), 排序后的 condition)`。

- 键相同、`location` 不同 → 合并为一条，`evidence` 追加，`counts.duplicates_merged += 1`；保留首个 `np_id`（确定性）。
- 键相同但极性相反 → **不合并**，两侧各留，并生成 `uncertainty` 条目 `kind=conflict`。
- 同一事实在不同章节重复表述 → 合并；但综述句与结果句同时出现时，保留结果句为 `directly_read`，综述句并入 `evidence` 并标注 `secondhand_citation`。
- `np_id` = `urn:nanopub:` + `sha256(canonical_string)[:32]`，`canonical_string = lower(subject)|relation|polarity|lower(object)|sorted(condition)`，可被任何人独立重算。

## 5. 冲突与不可判定

| 情形 | 处置 |
|-|-|
| 同断言在不同来源相反 | 两条都保留，`uncertainty.kind=conflict`，写清各自 locator，不改写任何一方 |
| 原文数值与正文文字不一致（摘要 vs 表） | 分别成条，`uncertainty` 记录差异，标 `pending_human` |
| 指代不可解（`it`/`this`/`该过程`） | `readability=undetermined`，进 `pending_human`，**不猜主体** |
| 断言需要图表内部数值 | 只登记图题，`figures.chart_meta.status=not_read`，进 `pending_human`(`vision_required`) |
| 材料缺失/不可访问 | 记 `input_gaps`，`status` 至少 `partial`；**不构造内容** |

## 6. 异常与降级分支表

| 触发 | 检测手段 | 降级动作 | 落点字段 |
|-|-|-|-|
| 无 `/input/case.json` | 路径探测 + 递归 glob | 用 `task.md` 与目录扫描继续，`status=partial` | `errors`/`input_gaps` |
| case.json 非法 JSON | `json.loads` 异常 | 保留原文到 `raw_case_bytes` 说明，按目录扫描继续 | `errors` |
| `output_contract` 缺失 | 键探测 | 用 schema 默认字段输出，`assumed_contract=true` | `task_understanding` |
| 扫描版 PDF（无文本层） | 每页 `text_quality<0.55` 或字符数<50 | 不伪造文本；该页写入 `sources[].flags` 的 `page_<n>_no_text_layer`，并进 `pending_human`(`ocr_required`) | `sources[].flags`/`pending_human` |
| 字体编码不支持（CID 无 ToUnicode） | 抽取文本中非可打印占比高 | 记 `pdf_font_encoding_unsupported`，尝试 `pdftotext`/`pypdf`，仍失败则拒答该材料 | `degradations` |
| 外部 PDF 工具缺失 | `shutil.which` / `import` | 回落到内置 stdlib 抽取器 | `runtime.extractors` |
| 图片材料（png/jpg） | 扩展名 + 魔数 | 不 OCR、不描述内容，只登记存在性与尺寸（如可得） | `pending_human`(`vision_required`) |
| 文档无句子（只有表格/公式） | 句子数=0 | 输出空 `assertions` + `insufficient_evidence` 说明 | `status` |
| 时间/条数预算耗尽 | 运行计时 + 计数 | 立即 finalize 已得结果，`degradations` 记 `budget_cut` | `degradations` |
| 任一材料解析异常 | 逐材料 try/except | 仅该材料降级，其余继续 | `errors` |

**退出码恒 0**；`result.json` 在流程开始就写一次 partial，结束再无条件 finalize 覆盖。

## 7. 公平对照协议（用于"使用增益"可核验）

同一案例、同一模型、同一工具权限，跑两条件：`baseline`（不给 Skill）与 `skill`（加载本 Skill）。对两份输出用同一张评分表逐项打：

| 指标 | 取法 | 判据 |
|-|-|-|
| 断言条数 | `counts.assertions_after_dedup` | 越多不等于越好，需配合下项 |
| 原子率 | 人工/脚本判：单谓词且可判真假的断言占比 | 分母为抽检 20 条 |
| 证据命中率 | quote 能在原文逐字定位的比例 | `counts.quote_hit_rate` |
| 定位完备率 | 同时具备 page/sentence/char 的断言占比 | 脚本可算 |
| 关系正确率 | 抽检 20 条中关系与方向正确的占比 | 人工 |
| 契约完整率 | `output_contract` 叶子键被填充的比例 | `counts.contract_keys_*` |
| 用时/请求数 | 平台 trace | 由平台记录，**不要自填分数** |

结论只写"在本次运行中观察到 X 与 Y 的差异"，不写"提升 N%"，除非 n 与重复次数都落在记录里。
