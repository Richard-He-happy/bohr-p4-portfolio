---
name: literature-qa
description: 文献智能问答。读取带段落编号的英文论文文本与中文问题清单，逐题（含子问）作答，并把每条论断、每个关键数值绑定到逐字原文引文、段落编号、字符偏移与成立条件；材料未报告时给出检索统计并明确说“未报告”，不补外部知识。适用于论文精读问答、数值与条件核验、跨章节整合与方法-结果合证、“论文是否报告 X”类边界判断。
version: 2.0.0
---

# literature-qa（reading-03 文献智能问答）

## 1. 用途与边界

输入「一篇带段落编号的论文文本 + N 个中文问题」，输出结构化问答结果：

- 每题一条 `answers[]`（含无法回答的题），题内再拆 `sub_questions[]` 逐子问标注状态；
- 每个关键数值一条 `claims[]`（`label = value unit`），每条论断带 `kind`（`reported`/`inferred`）与逐字 `evidence[]`；
- 未答部分进 `unanswered_parts[]`，未报告/低召回进 `uncertainties[]`，材料缺口进 `coverage.not_supplied`。

**边界**：只依据输入材料作答。不做 PDF 解析、OCR、像素读数、联网检索或外部知识补全；
材料没给的对象（表格、图注、章节）明确列缺口，不构造页码、图注或数值。

## 2. 本版（v2.0.0）相对 v1 的改动

在 v1 主流程与运行契约不变的前提下做最小稳健增强，只改 `SKILL.md`、`scripts/main.py`、`scripts/core.py`：

| 类型 | 改动 | 修正的问题 |
|-|-|-|
| 正确性 | 单位表补齐 ASCII 写法（`um`、`850 C`、`wt%`、`min-1`）与最长优先匹配 | v1 把 “18 um” 判为“无数值”，数值题被误标 `partial` |
| 正确性 | 数值名不再跨过前一个数值的单位取词；条件型数值按单位归名（`温度 = 850 C`、`时间 = 1 h`）；`18% higher than` 记为 `相对变化` | v1 冗余标签（如 `MPa at C for = 1 h`） |
| 完整性 | **每个数值单独一条 claim**；跨子问重复数值复用同一 `claim_id` | v1 一条 claim 塞多个数值，关键数字无法逐条核验 |
| 完整性 | 新增 `sub_questions[]`（序号/子问原文/状态/claim_id/段落号），`answer` 内保留 `【子问N】` | 子问覆盖无法机器核对 |
| 召回 | 前缀/词形容错打分（`degradation`↔`degraded`）；扩充中英同义词（退火、固溶、屈服、机制、模块、贡献、时延…）；章节名正确继承（`{"results": [...]}` 不再退化成 `sections`） | 同义改写/跨语言桥接召回不足 |
| 召回 | 子问无独立命中时改用同句/同段共用证据；条件型子问采用兄弟子问段中带该单位数值的证据 | 一句话含两个子问时，第二个子问被判“无原文” |
| 召回 | 文档频次过滤：去掉“photocatalyst/model”这类在多数段落都出现的词；正文仅以整篇字符串给出时回退切分（`P1 …` 标记或空行） | 泛词命中导致每题都“有证据”；整篇文本未给 `paragraphs` 时 0 段可检 |
| 判断 | 边界题（“是否报告 X”）要求证据确实涉及被问特征，否则按未报告处理 | 把“提到催化剂”当成“报告了带隙” |
| 判断 | 数值题要求命中数值的单位与所问量一致（问比表面积→`m2/g`，问温度→`C/K`），否则按未报告处理并记 `uncertainty=unit_mismatch` | 把保留率百分比当成比表面积作答 |
| 可核验 | 非数值题只对最高分段落抽数值，其余段落只引原文，避免无关数字 | 机制题里混入稳定性百分比 |
| 判断 | 全篇无可用证据 → `status=insufficient_evidence` + `unanswered_parts[]`（v1 可能落成 `answered`） | 材料不足时的诚实标注 |
| 可核验 | `verification`（自检项 + 逐字命中率 + 引文词数分布）、`summary`、`answers` 镜像、`runtime.budget`/`truncated`、`coverage.sections_unread`+`unread_reason`（如 `only_abstract_supplied`） | 契约与核验字段不全 |

## 3. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`（缺失或坏 JSON 时在 `/input/**` 找非评分类 JSON）；`/input/task.md` 仅作上下文 |
| 输出 | 主产物 `/app/output/result.json`；同目录 `answers.json`、`paragraph_index.json`、`evidence_map.csv`、`verify_report.json`；`/app` 可写时另写兼容件 `/app/answers.json` |
| 调用 | `python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output` |
| 参数 | `--input` `--out` `--case` `--apply` `--quiet` `--version` `--help`；**无参数也能跑**（默认 `/input`、`/app/output`，不可写时退 `./output`） |
| 依赖 | 仅 Python 标准库（3.8+），无第三方依赖、无联网、不依赖当前工作目录（资源用 `Path(__file__).resolve().parent` 定位） |
| 退出码 | 恒为 0；**第一步先写 partial `result.json`**，异常写入 `errors`，最后无条件 finalize 覆盖 |
| 预算 | 脚本秒级完成、不发起模型请求；900 s / 64 次请求预算由平台 DSH 计数，脚本侧记录 `runtime.budget`（`truncated=false`） |

脚本两个文件：`scripts/main.py`（检索、作答、输出、自检）与 `scripts/core.py`（输入发现、解析、数值与引文工具、CSV）。单次调用即完成全部阶段，无需分步。

## 4. 输入发现（按语义，不假设键名）

1. 读 `/input/case.json`；不存在或坏 JSON 时按 `case*.json` 递归找，跳过含 `score/gold/rubric/verifier/expected` 的评分数据。
2. `case_id`、`paper_id`、`material_version`、`output_contract` 原样保留；`paper_id` 缺失记 `null`，不自造。
3. 段落：识别 `paragraphs`/`paragraph_list`/`paras`/`segments`/`blocks`/`corpus`/`段落`，支持 `list` 与**按章节嵌套的 dict**（`{"sections": {"results": [...]}}` 保留章节名作为 `section`）；
   字段兼容 `paragraph_id|para_id|pid|id`、`text|content|body|paragraph`、`section|heading`。整篇文本带 `P12 …` 行首标记时按标记切段。
4. 表格/图注/参考文献作为伪段落纳入（`section=table|figure_caption|references`；表格 `rows` 展开为 `表头: 值` 序列，避免列错位）。
5. 问题：识别 `questions`/`question_list`/`qas`/`queries`/`问题清单`；条目可为 `dict`（`question_id`+`question`）或纯字符串（生成稳定 `Q1..Qn`）。问题顺序即输出顺序。
6. 材料未给的对象写入 `coverage.not_supplied`（如“材料未提供 table”）或置 `null`，不虚构。

## 5. 输出契约

`result.json` 顶层：`case_id`、`paper_id`、`material_version`、`status`、`summary`、`result{answers,unanswered_parts,coverage}`、
`answers`（= `result.answers` 镜像）、`claims`、`uncertainties`/`uncertainty`、`sources`、`pending_human`、`errors`、`degradations`、`changes`、
`counts`、`verification`、`primary_result`、`method_notes`、`runtime`、`contract_keys`、`question_ids`，
并**原样回填**输入 `output_contract` 的每个键（未知键保留，缺值 `null`/`[]`，键名不改）。

逐题字段：`question_id`、`question`、`answer`、`conditions`、`status`、`question_type`、`flags`、
`sub_questions[{index,question,status,claim_ids,evidence_paragraph_ids}]`、`claims`、`unanswered_parts`、`evidence_paragraph_ids`。

| 枚举 | 允许值 |
|-|-|
| 整体 `status` | `ok` / `partial` / `insufficient_evidence` / `input_error` |
| 逐题与逐子问 `status` | `answered` / `partial` / `insufficient_evidence` / `input_error` |
| `claims[].kind` | `reported` / `inferred` |

判定：题干所有子问都有原文依据（数值题必须有带单位数值）→ `answered`；缺子问或缺数值 → `partial`；
全篇检索无可用依据 → `insufficient_evidence`（**必须同时有 `unanswered_parts` 条目**）；案例包读不出 → `input_error`。
逐题不得出现 `ok`、`unknown`、`N/A`。字段细则仍以 `references/schema.md` 为准（v2 只增加字段，未改 v1 字段含义）。

## 6. 核心流程（固定六步，便于同输入对照）

1. **发现并解析**：建段落索引（`paragraph_id`、`section`、`locator`、字符数），统计章节，登记表格/图注/参考文献伪段落；
2. **问题分解**：按 `？；。` 与 `（1）` 拆子问，一句话里出现两个疑问焦点时按逗号拆（最多 4 个）；按提示词判题型（`NUM`/`MECH`/`BND`/`INT`）；
3. **双语检索**：中文问题词经 `references/glossary.md` 与 `scripts/core.py` 内置同义词表映射成英文本体词，加 ASCII 词与数字（≥2 位，
   短于 4 字母的别名如 `Eg` 不入表），按词面命中打分并做前缀/词形容错；大小写/连字符/上下标归一；
   段落数 ≥4 时按文档频次去掉在多数段落出现的泛词；章节类型加权（数值题偏向 results/abstract/table，方法题偏向 methods，边界题偏向 discussion/conclusion）；
4. **证据筛选**：命中段落内按句打分，取每段最高的 1 句，按字符区间切出 15–60 词引文（同段内句子感知延伸），保留 2–3 段；
   子问无独立命中时用同句/同段共用证据；条件型子问（温度/时间/浓度…）可采纳兄弟子问段中带该单位数值的证据；
   边界题若所有命中段落都未涉及被问特征（如问“带隙”而只提到“催化剂”），清空该子问证据并按未报告处理；
   数值题的命中数值单位必须与所问量一致（温度 `C/K`、比表面积 `m2/g`、效率 `%`…），不一致则清空该子问证据；
5. **作答与标注**：每个数值一条 claim（非数值题只取最高分段落中的数值），条件绑定 `conditions`；
   某段未产出数值 claim 时仍为该引文立一条 `原文（section，P#）：…` claim，保证每条证据都有归属；
   跨段落时另立 `INT1` 推断 claim（标注两段落号）；
   全篇零命中时立 `ABS1` 未报告 claim 并附检索统计，同时把该题置 `insufficient_evidence`；
6. **自检**：写 `result.json` 后跑自检（契约键、题数与子问编号、枚举、引文逐字与字符偏移、非 answered 的缺口、coverage、runtime.budget），
   结果同时写入 `result.json.verification` 与 `verify_report.json`，`counts.quote_hit_rate` 记录命中率。

## 7. Agent 复核与改写（可选增强）

脚本产出的是「可直接提交」的抽取式回答：数值、单位、条件、引文均来自原文，但中文表达偏模板化。
如需更自然的中文，按下列方式改写，**不要手工改 `result.json`**：

```bash
# 1) 读 /app/output/result.json 与 /app/output/paragraph_index.json，按题改写 answer 文本
# 2) 写 answers_patch.json: {"answers": {"Q1": {"answer": "...", "conditions": ["..."]}}}
python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output --apply /app/output/answers_patch.json
```

`--apply` 硬规则：改写文本中出现的每个数字都必须能在该题已有引文中逐字找到，否则整段拒收并记入 `pending_human`。

## 8. 质量规则（rubric → 字段/检查）

| 评分点 | 落地方式 |
|-|-|
| 任务完成度 | 每个输入问题一条 `answers[]`（含无法回答的），题数 = 输入题数；子问在 `sub_questions[]` 逐条带状态 |
| 结果正确性 | 数值/单位/条件取自引文；`claims[].text` 形如 `label = value unit`；条件片段与段落号写入 `conditions` |
| 结果完整性 | 子问拆块 `【子问N】` + `sub_questions[]`；缺项进 `unanswered_parts`，不丢弃 |
| 结果可核验性 | `paragraph_id` + `locator` + `char_start` + `quote_verified` + `evidence_map.csv` + `verification.quote_hit_rate` |
| 质量与效率增益 | `counts`（题数/子问数/数值 claim 数/引文命中率/引文词数分布）、`method_notes`、`verify_report.json`，可与同输入白板逐条对照 |
| 创新（跨章节/条件/拒答） | `INT1` 跨段推断、`sub_questions` 子问级状态、`conditions` 数值绑定条件、`ABS1` 未报告判定与零命中检索词 |
| 可靠体验 | 缺文件/坏 JSON/缺问题/单题异常各有分支，均不中断；退出码恒 0 |
| 生态贡献 | 本文件 + `references/schema.md` + `references/glossary.md` + `references/example.md` |

## 9. 证据与定位规范

- `quote` 必须是原段落逐字子串：不翻译、不改写、不拼接两段、不加省略号；长度约 15–60 词（同段内向前/向后延伸取整句；
  整段本就短于 15 词时保留自然句长，不强行截断，`counts.quotes_below_15_words` 如实计数）。
- 定位三元组：`paragraph_id` + `locator`（`/paragraphs/12` 之类）+ `char_start`（`paragraph.text[char_start:char_start+len(quote)] == quote`）。
- 交叉核对：`quote_verified=true` 且 `quote_hit_rate=1.0` 才算通过；`char_start=-1` 的引文不纳入。
- `evidence[].paper_id` 与顶层 `paper_id` 一致；`claims[].source_id` 同值。
- 数值 `±`、p 值、比较符号、单位（`MPa`、`°C`、`850 C`、`%`、`mg/L`、`h`、`min-1`）原样保留，不做单位换算；`1,250` 视为千分位而非小数。
- `readability` 与 `kind` 对应：`reported → directly_read`；`inferred → inferred`；未报告/无法确定 → `undetermined`。

## 10. 冲突、缺口与人工确认

- **未报告**：全篇检索零命中或仅定性表述时，写 `ABS1`（`kind=inferred`、`readability=undetermined`）；
  该题 `status=insufficient_evidence`，且 `unanswered_parts` 写明缺什么/为什么缺/需要什么才能补；
  `uncertainties[]` 记 `type=not_reported|low_recall`、`zero_hit_terms`、`paragraphs_searched`；不得写成“不存在”。
- **部分回答**：子问无匹配 → `status=partial` + `unanswered_parts(reason=no_matching_paragraph|not_reported_after_full_search)`；
  数值题只有定性表述 → `reason=numeric_value_not_reported`。
- **冲突**：同一量出现两个值，两条都保留 `reported` 并在 `uncertainties` 记 `conflict` 与两个段落号，不择一当唯一事实。
- **待人工**：`pending_human` 写具体动作（如“Q3 请人工确认未报告结论并核对检索词”），不写泛泛的“需复核”。

## 11. 预算与断点

- 解析前先写 partial `result.json`（`status=partial`、空业务字段），保证任何中断都有合法产物；
- 全流程秒级，无需分页续跑；单题异常只降级该题（`status=partial` + `unanswered_parts(reason=internal_error)`），其余照常；
- 平台若限制写盘目录，`--out` 指向可写目录即可（`/app/output` → `./output` 顺序探测）。

## 12. 异常降级分支

| 情况 | 行为 | 结果痕迹 |
|-|-|-|
| `/input` 无案例或坏 JSON | 不抛错，写 `input_error` | `status=input_error`、`errors[stage=load_case]`、`answers=[]` |
| 无问题清单 | 空 `answers`，契约仍完整 | `degradations[item=questions]`、`status=input_error` |
| 段落无编号 | 生成 `P1..Pn`，`locator` 指回来源数组 | `paragraph_index.json` 可核对映射 |
| 只给整篇文本（无 `paragraphs`） | 按 `P1 …` 行首标记或空行回退切分 | `changes[item=paragraphs]`、`run_status` 见 `coverage.read_status` |
| 段落无章节标签 | 全部段落 `section=unknown` | `coverage.read_status=section_labels_not_supplied`，`sections_unread=[]` |
| 段落编号重复 | 追加序号去重 | 保留两段原文，不丢内容 |
| 章节嵌套 | 以键名作为 `section`（`{"results": [...]}` → `results`） | `coverage.sections_read` 显示真实章节 |
| 材料只有摘要 | 其余章节计入 `sections_unread` | `unread_reason=[{section,reason:only_abstract_supplied}]`、`read_status` |
| 单题异常 | 该题 `partial` 并继续 | `errors[stage=answer]` |
| `--apply` patch 不合格 | 拒收该段，保留原回答 | `pending_human` + `changes` |
| `/app` 不可写 | 只写 `--out` 目录 | `degradations[item=/app/answers.json]` |

## 13. 自检清单（提交前逐项运行核对）

```bash
python3 -B /skills/literature-qa/scripts/main.py --help            # 退出码 0
python3 -B /skills/literature-qa/scripts/main.py --input /input --out /app/output
head -40 /app/output/verify_report.json                            # 看 checks / quote_hit_rate
```

- [ ] `result.json` 合法 JSON，`output_contract` 每个键都在顶层；`result.answers` 与 `answers` 镜像一致；
- [ ] `answers` 题数 = 输入题数，每题有 `status` 且属于四个允许值，`sub_questions` 序号从 1 连续；
- [ ] 每个报告数值都有独立 claim；`kind` 只有 `reported`/`inferred`；
- [ ] `quote_hit_rate=1.0`、`char_start` 逐字对上、`paragraph_id` 均存在于段落清单；
- [ ] `partial`/`insufficient_evidence` 题都有 `unanswered_parts`；未报告项有 `uncertainties` 记录；
- [ ] `coverage` 含已读章节、未读章节与原因、`not_supplied`；
- [ ] 空输入 / 坏 JSON / 缺 `questions` 仍产出合法 partial `result.json`，退出码 0；
- [ ] 无外部知识、无翻译引文、无自造 `paragraph_id`。

## 14. 最小调用示例、文件清单与版本

```bash
python3 -B scripts/main.py --input /input --out /app/output
# [literature-qa 2.0.0] case=<case_id> status=<ok|partial|insufficient_evidence|input_error> q=3 subq=5 claims=14 quote_hit=1.0 selfcheck=True fails=[]
```

输入片段、输出节选与 `question_id → sub_questions → claim_id → paragraph_id → quote` 的对应关系见 `references/example.md`
（该示例为自拟短材料，输出仅示意接口，不是任何正式案例的答案或效果证明；其中数值标签为 v1 风格，v2 起标签形如 `温度 = 850 C`）。

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 入口说明：用途、契约、流程、质量规则、降级、自检 |
| `scripts/main.py` | 检索、作答、输出与自检（`--input/--out/--case/--apply/--quiet/--version`） |
| `scripts/core.py` | 输入发现与解析、数值/引文/覆盖工具、`evidence_map.csv` |
| `references/schema.md` | 字段字典、状态/枚举判定、与评分维度对应（v1 字段全部保留） |
| `references/glossary.md` | 中英检索词表（材料/机械、CS/ML、环境/光催化三域） |
| `references/example.md` | 最小调用示例（标注示例）与复用建议 |

版本 `2.0.0`。维护：新增领域先补 `references/glossary.md` 或 `core.FALLBACK_GLOSS`；调整检索权重在 `main.py` 的 `SEC_PREF`/`pscore`；
改动字段同步 `references/schema.md` 与第 5 节；改版本后重跑第 13 节自检并如实记录结果。

**已知限制**：检索仍为词面/词形匹配（依赖词表覆盖），语义等价但用词完全不同的段落可能漏检，此时按 `insufficient_evidence` 处理而不猜；
回答为抽取式，句式偏模板化；跨语言仅通过词表桥接，不做语义翻译；数值标签由邻近词或单位类别生成，个别偏宽（如 `相对变化`）；
`conditions` 是原文条件片段而非规范化实验设计描述；材料未提供页图/表格图元时无法给出页码与图像读数。
