# nanopub-forge · 字段字典与受控词表（schema `np-assertion/1`，Skill 版本 1.0.0）

本文件是 `result.json`、`assertions.jsonl`、`assertions.jsonl`、`assertions.jsonl` 的字段唯一解释来源。
键名一律 `snake_case`；未知值一律 `null`（标量）/ `[]`（列表），**不得用 0、"N/A"、"unknown" 冒充**。

## 1. 顶层结果字段

| 字段 | 类型 | 含义 | 缺失时 |
|-|-|-|-|
| `skill` | object | `{name, version, schema}`，运行时自报，便于版本追溯 | 运行时必填 |
| `case_id` | string|null | 原样复制输入的案例标识，**不改写** | `null` 并记入 errors |
| `status` | enum | `ok` / `partial` / `insufficient_evidence` / `input_error` | 必填 |
| `status_reason` | string | 一句话说明状态判据（含计数） | `null` |
| `task_understanding` | object | `{question, scope, required_outputs, assumed_contract}`：Skill 对题面/工单的复述，供人核对是否走偏 | `{}` |
| `inputs` | array | 每个被发现的材料：`{source_id, path, kind, bytes, declared_by, present}` | `[]` |
| `input_gaps` | array | 输入声明但缺失的材料、缺字段的工单：`{what, why_needed, impact}` | `[]` |
| `sources` | array | 来源元数据（见 §3） | `[]` |
| `assertions` | array | 原子断言主结果（见 §4），**主产物** | `[]` |
| `figures` | array | 图/表登记与图表元信息槽位（见 §6） | `[]` |
| `counts` | object | 覆盖率与拒绝计数（见 §7） | 全 0 |
| `verification` | object | 逐字命中、契约完整性、词表合法性等自检结果（见 §8） | `{}` |
| `uncertainty` | array | 未报告项、冲突、不确定项：`{id, claim_id, issue, kind, detail, action}` | `[]` |
| `pending_human` | array | 需人工/视觉接管：`{id, target, reason, required_action, blocking}` | `[]` |
| `errors` | array | 真实异常：`{stage, message, type}` | `[]` |
| `degradations` | array | 有意的功能降级：`{capability, cause, fallback}` | `[]` |
| `changes` | array | 运行轨迹：`{t, action, detail}`，用于复现与审计 | `[]` |
| `runtime` | object | `{skill_version, python, started_utc, finished_utc, elapsed_s, input_dir, output_dir, extractors, limits}` | 必填 |
| `artifacts` | object | 产出文件相对路径表 | `{}` |
| `output_contract_keys` | array | 输入 `output_contract` 的全部叶子键 JSON Pointer，用于证明 100% 回填 | `[]` |
| `output_contract_echo` | object|array|null | 原样形状回填后的契约镜像（键名不改、未知键保留） | 原样 |
| `contract_fields_present` | object | 每个契约键是否取到值：`{pointer: bool}` | `{}` |
| `notes_for_agent` | array | 给下游 Agent 的续做提示（低置信断言、缺视觉读图等） | `[]` |

契约键（`output_contract` 中的键）**同时平铺在顶层**，与上表字段同名时以 Skill 结构为准，但键一定存在。

## 2. 定位符（locator）规范

`location` 对象：

```json
{"page": 3, "paragraph": 1, "sentence_index": 7,
 "char_start": 1204, "char_end": 1379,
 "locator_type": "page+sentence+char",
 "json_pointer": "/sources/0/pages/2/text",
 "section": null}
```

- `page`：PDF 物理页序号，**从 1 开始**；不可得时 `null` + flag `page_number_unavailable`。
- `paragraph`：该页内以空行/分块切出的段落序号（1 起）。文本层丢失段落结构时可能恒为 1，此时 `locator_type` 不含 `paragraph`。
- `sentence_index`：规范化页文本内的句子序号（1 起）。
- `char_start`/`char_end`：句子在**规范化页文本**中的字符区间（左闭右开），用于机器二次切片。
- `json_pointer`：指向 `extracted_text.json` 中该页 `text` 的指针，任何人可据此取回原文串。
- `locator_type` 是自描述串，由实际可得的维度拼成（如 `page+sentence+char`、`sentence+char`、`table+row`）。

`assertions.jsonl` 同时给出扁平的 `page, paragraph, sentence_index, char_start, char_end, locator`。

## 3. `sources[]`

```json
{"source_id": "S1", "path": "/input/paper.pdf", "kind": "pdf", "bytes": 1234567,
 "extractor": "pdftotext|pypdf|pdf-internal|zip-xml|plain|none",
 "pages": 12, "text_chars": 48210, "text_quality": 0.97,
 "title": null, "authors": [], "year": null, "journal": null,
 "doi": null, "version": null, "license": null,
 "flags": ["page_4_no_text_layer"]}
```

- 元数据**只从输入本身取**（PDF Info 字典、DOI 正则、case 元数据字段、正文首屏）。取不到就是 `null`，**不推测、不补全**。
- `text_quality` = 可打印拉丁/汉字字符数 ÷ 非空白字符数，用于判断文本层是否可信。
- 同一论文多份材料（正文 + 补充材料）各占一个 `source_id`，在断言里以 `source_ids` 归并。

## 4. `assertions[]`

| 字段 | 类型 | 说明 |
|-|-|-|
| `assertion_id` | string | 本次运行内的稳定编号 `A0001`，按输出顺序 |
| `np_id` | string | 确定性标识 `urn:nanopub:<sha256[:32]>`，由规范化三元组+极性+条件算出，可独立重算、可去重 |
| `kind` | enum | `quantitative` / `comparative` / `mechanistic` / `associational` / `descriptive` / `definitional` / `methodological` / `limitation` |
| `assertion_text` | string | 单一、可判真假的断言陈述（一句，主语+关系+宾语，含限定条件）；不引入原文之外的信息 |
| `subject` | object | `{text, type}`，`type` 为 `gene|protein|compound|organism|cohort|method|variable|null`，只在原文可判时填 |
| `relation` | enum | 受控词表（§5）；无法映射时 `other_relation` 且 `needs_review=true` |
| `relation_raw` | string | 原文表面形式（如 `was significantly reduced`），逐字保留，不改写 |
| `object` | object | `{text, type}` |
| `polarity` | enum | `affirm` / `negated`（原文否定词作用于该关系时） |
| `magnitude` | object|null | `{value, unit, raw, ci, p}`；`value` 保持原文精度字符串，不换算 |
| `condition` | array | 限定条件短语原文片段：物种、剂量、时间点、体系、比较对象、n 等 |
| `evidence` | array | 至少 1 条：`{quote, source_id, location, locator, match}` |
| `readability` | enum | `directly_read` / `inferred` / `undetermined`（§5.3） |
| `confidence` | object | `{score, basis[], tier}`，`score` ∈ [0,1]，`basis` 为可复核的判据码 |
| `needs_review` | bool | 是否进入人工/Agent 复核队列 |
| `review_reason` | string|null | 复核原因码 |
| `source_ids` | array | 该断言涉及的来源 |

`quote` 的硬约束：必须是 `extracted_text.json` 对应页文本的**逐字子串**（比较时仅做空白折叠与连字符归一）。做不到就不得作为支撑证据——移入 `pending_human` 或改绑正确片段。

## 5. 受控词表

### 5.1 关系（`relation`）

| 值 | 触发语义 | 常见表面形式 |
|-|-|-|
| `increases` | 上调/升高/增强 | increased, elevated, upregulated, enhanced, higher, greater, 升高, 增加, 上调 |
| `decreases` | 下调/降低/减弱 | decreased, reduced, lowered, downregulated, attenuated, impaired, 降低, 减少, 下调 |
| `inhibits` | 抑制/阻断 | inhibited, suppressed, blocked, abolished |
| `activates` | 激活/诱导/促进 | activated, induced, stimulated, promoted |
| `associated_with` | 关联/相关（**不是因果**） | associated with, correlated with, linked to |
| `binds` | 结合/相互作用 | binds, interacts with, targets |
| `encodes` | 编码 | encodes, is encoded by（注意方向） |
| `expressed_in` | 表达/检出/定位 | expressed in, detected in, localized to |
| `mediates` | 介导/调控 | mediates, regulates, modulates |
| `causes` | 因果（需原文因果表述） | causes, leads to, results in, due to |
| `differs_between` | 组间差异 | higher in ... than, differed between |
| `is_a` | 定义/归类/属性 | is, are, constitutes, remains |
| `has_part` | 组成/包含 | contains, comprises, consists of |
| `uses_method` | 方法/流程 | measured by, performed using, quantified with |
| `other_relation` | 无法映射（**必须**进复核队列） | — |

规则：`associated_with` 不得升级为 `causes`；`expressed_in` 不得写成 `binds`。被动句 `A was reduced by B` 必须交换主体方向（subject=B，object=A）并记 `basis` 含 `passive_voice_swapped`。

### 5.2 `confidence.basis` 判据码

`verbatim_quote_bound` / `relation_mapped` / `stats_reported` / `hedged_language` / `subject_inherited` / `pronoun_resolved` / `passive_voice_swapped` / `span_heuristic` / `predicate_unmapped` / `cross_clause_merge` / `secondhand_citation` / `no_text_layer`。

`tier`：`high`（关系已映射 + 逐字绑定 + 无继承/代词/二手引用）／`medium`（映射成功但存在 span 启发式、继承主语、二手引用之一）／`low`（`predicate_unmapped` 或需视觉核对）。

### 5.3 `readability`

| 值 | 判据 |
|-|-|
| `directly_read` | 关系、主体、宾语、条件全部出现在被引片段中，无需推断 |
| `inferred` | 依赖跨句指代消解、相对从句主语继承、或由图表题注转述 |
| `undetermined` | 指代不可解、否定辖域不明、片段与断言冲突且无法判定 —— 同时必须出现在 `uncertainty` 或 `pending_human` |

## 6. `figures[]`（图表登记，诚实留白）

```json
{"label": "Fig. 2", "page": 5, "status": "not_read",
 "caption_quote": "Fig. 2. Tumour volume over 21 days ...",
 "locator": "S1#p5/Fig. 2",
 "chart_meta": {"axis_x_type": null, "axis_x_scale": null, "axis_y_type": null, "axis_y_scale": null,
                "units": null, "legend_entries": null, "series_count": null, "error_bars": null,
                "scale_bar": null, "subpanel_labels": null, "pixel_readings": [],
                "status": "not_read", "reason": "no_vision"}}
```

`label/page/caption_quote/locator` 来自文本层题注匹配（同一页最多 8 条）。`chart_meta` 的可读维度（坐标轴类型与刻度、单位、图例、系列数、误差线、比例尺、子图编号）在无视觉能力时**恒为 `null`**、`status` 恒为 `not_read`；这些图表不支撑任何断言，需要时进 `pending_human`（`vision_required`）。若某次运行做了像素读数，`pixel_readings` 每项须写 `{value, unit, approx: true, error, method}`。

## 7. `counts`

```json
{"sources_total": 1, "pages_total": 12, "sentences_scanned": 412, "assertions_emitted": 143,
 "assertions_after_dedup": 131, "duplicates_merged": 12,
 "assertions_quote_bound": 129, "assertions_quote_failed": 2,
 "contract_keys_total": 9, "quote_hit_rate": 0.985}
```

`clauses_candidate`、`assertions_high/medium/low`、`pending_human_total`、`readability` 分布、`relations_used` 等派生量**不由本版输出**：需要时从 `assertions[]` 现算（`len(r["assertions"])`、按 `confidence.tier`/`readability` 计数），不要假设它们存在。

## 8. `verification`

`{"quote_checks": {"checked", "passed", "failed", "failures[]"}, "contract": {"keys", "echo_ok"}, "external": {…}}`

- `quote_checks`：固化的逐字命中检查（每条 evidence 对 `extracted_text.json` 对应页）。
- `contract`：`output_contract` 回填的键数与 echo 形状是否可遍历。
- `external`：仅由 `verify.py --patch` 写入，含 `quote_vs_dump` / `quote_vs_original` 双通道计数、`contract_missing`、`pass`。

字段齐备性、词表合法性与 `np_id` 重算不在本字段内：由 `verify.py` 独立复核（`verification.json`）或从 `assertions[]` 现算。

## 9. 版本与兼容

`np-assertion/1`：首版。字段只增不改；新增字段必须在本文件登记并升 `schema` 次版本号。
