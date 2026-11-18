# nanopub-forge · 示例与题集（示例全部为示意，非正式案例结果）

> **免责声明**：本文件的输入句均为**合成示意句**（synthetic），不对应任何真实论文，不含真实 DOI、作者或数值；凡 `source` 字段皆标 `SYNTH`。它们只用于说明"输入句 → 原子断言 → 证据绑定"的形态，**不是**任何评测案例的答案。

## 1. 最小调用示例（示例，非正式案例结果）

目录：

```
/input/case.json          # {"case_id":"demo-001","output_contract":{"assertions":"array","claims":"array","status":"string"},"task_instruction":"..."}
/input/material.md        # 一页正文（示意）
```

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
python3 -B scripts/verify.py --output /app/output --patch
```

示意输入句（合成）：

```
Treatment with compound Z reduced tumour volume by 38% in mice after 21 days (n = 8, p = 0.01).
```

示意输出（`assertions.jsonl` 其中一行，**示例**）：

```json
{"assertion_id":"A0001","np_id":"urn:nanopub:9c1f…(32 hex)",
 "kind":"quantitative","assertion_text":"In mice at 21 days, compound Z treatment reduces tumour volume (38%).",
 "subject":{"text":"compound Z treatment","type":"compound"},
 "relation":"decreases","relation_raw":"reduced",
 "object":{"text":"tumour volume","type":"variable"},
 "polarity":"affirm",
 "magnitude":{"value":"38","unit":"%","raw":"by 38%","ci":null,"p":"p = 0.01"},
 "condition":["in mice","after 21 days","n = 8"],
 "evidence":[{"quote":"Treatment with compound Z reduced tumour volume by 38% in mice after 21 days (n = 8, p = 0.01).",
   "source_id":"S1","locator":"S1#p1/s1",
   "location":{"page":1,"paragraph":1,"sentence_index":1,"char_start":0,"char_end":105,
     "locator_type":"page+paragraph+sentence+char","json_pointer":"/sources/0/pages/0/text","section":null},
   "match":"verbatim"}],
 "readability":"directly_read",
 "confidence":{"score":0.86,"basis":["verbatim_quote_bound","relation_mapped","stats_reported"],"tier":"high"},
 "needs_review":false,"review_reason":null,"source_ids":["S1"]}
```

同一输入会同时得到：`/app/output/result.json`、`assertions.jsonl`、`assertions.jsonl`、`assertions.jsonl`、`review_queue.md`、`extracted_text.json`。

## 2. 20 条示意断言（覆盖拆解判据）

格式：`# | 输入（合成） | 原子断言 | 关系 | 证据处理 | 判据`

| # | 输入（合成示意句） | 原子断言 | 关系 | 证据处理 | 判据 |
|-|-|-|-|-|-|
| 1 | Compound Z reduced tumour volume by 38% in mice. | Z decreases tumour volume (38%) in mice | decreases | 整句逐字绑定 | 单谓词 + 数值入 magnitude |
| 2 | Compound Z reduced tumour volume and increased survival. | Z decreases tumour volume | decreases | 拆前半句 | 并列拆分，条件共享 |
| 3 | Compound Z reduced tumour volume and increased survival. | Z increases survival | increases | 拆后半句 | 同上，两条 np_id 不同 |
| 4 | A was inhibited by B in a dose-dependent manner. | B inhibits A | inhibits | 整句；`basis+=passive_voice_swapped` | 被动换向 |
| 5 | A did not increase B. | A does not increase B | increases + `polarity=negated` | 整句 | 否定不改成 decreases |
| 6 | X was associated with Y, but the study did not establish causality. | X is associated with Y | associated_with | 拆首句 | 关联不升级因果 |
| 7 | Although A remained high, B declined after day 7. | B decreases after day 7 | decreases | 拆后半句，`condition+=although` 语境 | 让步从句拆分 |
| 8 | A induced B, which in turn reduced C. | A activates B | activates | 首句 | 因果链首环 |
| 9 | A induced B, which in turn reduced C. | B decreases C | decreases | 相对从句，`basis+=subject_inherited`、`readability=inferred` | 主语继承须标注 |
| 10 | Previous studies reported that A inhibits B. | Previous studies report A inhibits B | inhibits | 整句，`basis+=secondhand_citation`，`tier=medium` | 二手引用保留归因 |
| 11 | Expression of G was detected in the liver but not in the kidney. | G is expressed in liver | expressed_in | 拆前半句 | 正例拆分 |
| 12 | Expression of G was detected in the liver but not in the kidney. | G is not detected in kidney | expressed_in + `polarity=negated` | 拆后半句 | 负例拆分 |
| 13 | Levels in cases were higher than in controls (p < 0.001). | Levels in cases are higher than in controls | differs_between | 整句 + `stats_reported` | 比较方向 |
| 14 | Compound Z may improve survival in patients with advanced disease. | Z may improve survival in advanced-disease patients | increases + `hedged_language`，score 降档 | 整句 | 模糊语气降置信 |
| 15 | Samples were analysed by LC-MS/MS after 24 h incubation. | LC-MS/MS is the analytical method | uses_method | 整句，`kind=methodological` | 方法句不写机制 |
| 16 | The 3.2-fold increase in p-AKT was abolished by inhibitor W. | W inhibits p-AKT increase | inhibits | 整句；magnitude 保留 `3.2-fold` 原文 | 剂量化 + 抑制 |
| 17 | Neither A nor B was detected in serum. | A is not detected in serum | expressed_in + negated | 拆 A | `neither…nor` 两侧各一条 |
| 18 | Neither A nor B was detected in serum. | B is not detected in serum | expressed_in + negated | 拆 B | 同上 |
| 19 | Figure 2 shows that inhibition of A reduced B in all three donors. | Inhibition of A reduces B (3 donors) | decreases | 题注转述，`readability=inferred`，`figures[].chart_meta.status=not_read` | 图表只登记不造数 |
| 20 | The effect was significant (n.s. in donor 3). | Effect is significant | is_a | 冲突标记：`uncertainty.kind=conflict` + `pending_human` | 内部矛盾不写成事实 |

以上 20 条覆盖：并列拆分、被动换向、否定、关联/因果边界、让步、相对从句、二手引用、正负例、比较、模糊语气、方法句、量化、`neither…nor`、图表转述、内部冲突。

## 3. 复现题集模板（可扩展为 benchmark）

`task-set.jsonl` 每行一条，可直接喂给本 Skill 与任意基线做对照：

```json
{"case_id":"synth-001","sentence":"<合成句>","expected_assertions":[{"subject":"...","relation":"decreases","object":"...","polarity":"affirm","needs_review":false}],"expected_flags":["passive_voice_swapped"],"note":"unit test, synthetic"}
```

评分脚本建议（不随包发布，避免超出资源限额）：对每条 `expected_assertions` 计算集合级 P/R —— 需要 `(subject, relation, object, polarity)` 四元组归一后匹配，`expected_flags` 需出现在 `confidence.basis` 中。这给出原子率、关系正确率、方向正确率的可重复数值，而不是自述。

## 4. 已知限制（写清，不掩饰）

1. 内置 PDF 文本抽取只处理 `FlateDecode` + 常见文本算子；CID 字体无 `ToUnicode` 时文本会退化为乱码，此时脚本改用 `pdftotext`/`pypdf`（若镜像提供），否则把该材料标为不可解析，**不猜内容**。
2. 规则法三元组抽取在高嵌套句、公式密集句上会漏抽或抽偏；因此输出分 `tier` 并给出 `review_queue.md`，由 Agent/人复核，而不是假装全能。
3. 图表内部数值、误差线、比例尺、子图编号在无视觉能力时留 `null`，只登记题注与位置。
4. 表结构（xlsx/csv）按"表头=首行"解析；无表头或合并单元格会退化，`location.locator_type` 会退为 `sheet+row`。
5. `np_id` 只保证在本规范下的确定性与去重，不是已注册的 nanopublication 服务器标识；不要声称已发布到 nanopub 网络。

## 5. 维护

- 改抽取规则 → 同步改 `references/rules.md` 判据表与本节"已知限制"。
- 改字段 → 同步 `references/field-dictionary.md` 并升 `schema` 次版本。
- 每次改动后必须重跑：`--help`、最小输入、空输入、坏 JSON 三个自检（见 SKILL.md §12）。
