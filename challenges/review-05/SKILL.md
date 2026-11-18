---
name: academic-compliance-review
description: 对论文/科研材料做学术规范与合规审查，输出带逐字定位证据的结构化审查意见。用于审稿、投稿前自查，以及学术诚信、引用、隐私、版权、伦理、投稿要求的合规检查；产出 result.json + review_report.md + issues.csv，覆盖事实核验、引用支持、方法设计、统计报告、论证链、学术规范六个检查面。
version: 1.0.0
---

# 学术规范与合规检查（review-05）

## 1. 用途与边界

**做什么**：读入科研材料，按六个检查面逐条给出**可定位、可核对**的问题（原文 locator + 逐字 quote + 判定依据 + 严重度 + 可执行建议），并如实区分"错误 / 证据不足 / 规范问题 / 建议"。

**不做什么**：不代写、不润色、不代投稿；不重做数据分析；不出具法务或伦理委员会的正式意见；不判断文献"是否真实存在"（离线无法核验 → 记 `insufficient_evidence`）。

**适用**：期刊稿件、结题/答辩材料、对外发布前自查；中英文；PDF/DOCX/MD/TXT/JSON/CSV/XLSX。
**不适用**：纯图片或扫描件（本 Skill 无 OCR 能力）、需要跨库查重或 DOI 核验、需伦理委员会裁定的争议。

## 2. 运行契约

- 输入 `/input`（`case.json` + `task.md` + 材料），工作目录 `/app/work`，产物 `/app/output`。
- 仅 Python 标准库（≥3.9），**不联网**，不依赖当前工作目录（脚本用 `Path(__file__).resolve().parent` 定位同目录模块）。
- **退出码恒 0**；任何异常都落成合法 `result.json`。
- 先写 partial（`status=partial`）再细化，最终无条件覆盖为终态。
- 预算：本地计算毫秒级；判读阶段建议 ≤64 次模型请求、900 秒，接近上限先 `--stage finalize` 落盘。

```bash
python3 scripts/main.py --input /input --output /app/output --stage scaffold   # 出候选 + partial
python3 scripts/main.py --input /input --output /app/output --stage finalize   # 校验并定稿
```

## 3. 输入发现（语义识别，不假设键名）

1. 递归扫描 `--input` 下全部文件（按名排序，上限 50；超出记 `degradations:file_cap`）。
2. `case.json`（或首个 `case*.json`）：原样保留 `case_id`；递归定位 `output_contract`（键名可为 `output_contract`/`contract`/`result_contract`）。
3. 材料按**扩展名 + 内容**解析：PDF 取文本层（zlib 解内容流）、DOCX 读 `word/document.xml`、XLSX 读 `sharedStrings`+`sheet*.xml`、文本类直读；图片只登记 `image_not_read`，**不读取像素、不做图内推断**。
4. `case.json` 中 ≥60 字符的字符串按 JSON Pointer 建为独立来源（稿件常直接内联在此）。
5. `<work>/review/text/*.txt` 视为"自行 OCR/转写"的补充文本（支持 `[[p3]]` 分页）。
6. 材料未提供的对象（文献表、图、补充材料、伦理附件）**明确列缺口**，不构造。

## 4. 输出契约

| 文件 | 作用 |
|---|---|
| `/app/output/result.json` | 主结果：`case_id`、`status`、`issues[]`、`checks{}`、`summary`、`sources`、`uncertainty`、`pending_human`、`review_records`、`errors`、`degradations`、`changes`、`artifacts`、`runtime`、`contract_fields` + **`output_contract` 的每个键** |
| `/app/output/review_report.md` | 人读报告：六面覆盖 + 逐条问题（位置/原文/依据/理由/建议）+ 待复核/拒收 + 不确定性 + 材料与运行 |
| `/app/output/issues.csv` | 同一批问题的表格视图（可直接排序、批注、交办） |
| `<work>/review/packets.md` | 按六面分组的**候选**证据包（判读入口） |
| `<work>/review/candidates.json` | 候选机读版（`cid`/`trigger`/`sev_hint`/`safe`） |

契约回填见 `references/schema.md` §5：键名从不改写，无对应值的键置 `null` 并记入 `contract_fields.unfilled`。

## 5. 核心流程（三步）

1. **scaffold**：解析材料 → 建行号级可定位语料（`sid:Pn` + `L a-b`）→ 解析引用与文献表 → 确定性检出器产出**候选**（不是结论）→ 写 `packets.md` + partial `result.json`。
2. **裁定（模型/人）**：逐条读候选，成立则写 `issues`（`quote` 必须逐字复制原文），不成立则写 `dismissed` 并给理由；六面各给 `status`。
3. **finalize**：逐字校验 → 拒收不可核验项 → 去重 → 覆盖守卫 → 计数 → 回填契约 → 渲染报告与 CSV。

## 6. 六面检查清单

完整 34 项见 `references/checklist.md`（含证据要求、严重度锚点、误报清单）。脚本自动检出的 17 项：

| 面 | 自动项 | 触发条件 |
|---|---|---|
| 事实核验 | FCT-02 | 正文引"图 N/表 N"但无对应题注 |
| 引用支持 | CIT-01 / CIT-01b / CIT-02 | 引用编号不在文献表 / 文献表条目未被引用 / 正文年份与文献表不符 |
| 方法设计 | MET-02 / MET-04 | 声称随机但无盲法或分配隐藏 / 未报分析软件与版本 |
| 统计报告 | STA-01 / STA-02 / STA-03 | p 值无检验名 / 全篇无统计方法 / "±"无 SD·SEM 标注 / 无样本量 |
| 论证链 | ARG-01 / ARG-02 | 强断言同句无数据无引用 / "已有研究表明"无引用 |
| 学术规范 | NRM-02~07 | 缺 COI、基金、数据可用性声明；涉人无伦理表述或批号；动物实验无伦理；PII；第三方材料无许可 |

**必须人工过的项**：FCT-01/03、CIT-03/04/05、MET-01/03、STA-04~07、ARG-03~05、NRM-01/08/09/10。自动候选为 0 的面也要给 `status`（`pass` 或 `not_applicable` + 理由），不得留空。

## 7. rubric → 字段/检查/产物

| 评分点 | 落到哪里 |
|---|---|
| 任务完成度（逐条含定位/依据/严重度/建议） | `issues[]` 强制 `locator`+`quote`+`severity`+`reason`+`suggestion`；`review_report.md` §2 |
| 结果正确性（不编造、不误判风格） | 逐字校验拒收未命中项；`verdict_type` 区分错误/证据不足/规范/建议；`checklist.md` 误报清单 |
| 结果完整性（按风险面逐项查） | `checks{}` 六面 `status` + 覆盖守卫（有未裁定候选时不得 `pass`）；`summary.unaddressed` |
| 结果可核验性 | `locator`+`line`+`quote`；`evidence[]` 指回文献表条目或指南原文；`review_records.rejected_issues` 留痕 |
| 使用增益（省时、少返工） | 一条命令产出候选+定位+文献表比对；`issues.csv` 可直接交办；`packets.md` 免通读全文 |
| 增益可验证 | 同输入重复运行结果一致（确定性排序与编号）；`runtime`、`changes` 记录 |
| 创新（句级清单、主张—引用配对、分面、证据链） | 行号级 unit/sentence 索引；CIT-01 正文↔文献表配对；六面独立 `checks`；ARG/CIT 证据—结论链条目 |
| 可靠体验（异常处理） | 见 §12 降级表；`status` 四态；`errors`/`degradations`/`pending_human` 分列 |
| 生态贡献（可复用） | `checklist.md` 34 项清单 + `schema.md` 词表 + `examples.md` 示例；`packets.md`/`candidates.json` 可作标注集 |

## 8. 证据与定位规范

- **quote**：原文逐字片段（≥8 字符，建议 10–200 字）。比较前做 NFKC + 空白折叠 + 引号/破折号归一；仍不命中即拒收。
- **locator**：`sid:P<n>`（段落块）、`sid:P<n>.S<k>`（句）、`sid:DOC`（仅整篇命中）、`REF:n<k>`（文献表条目）；同时给 `line`（文件行号）。
- **evidence**：外部依据（文献表条目、指南原文、规范条款）逐条给 `source/locator/quote/note`；只有稿件内部一致性时留空并在报告中写明。
- **禁止**：改写原文凑通过、编造页码/DOI/期刊名/统计量/图元素、把"未提供"写成"不存在"。

## 9. 严重度与判定类型

- `blocker`：结论不可信或硬性合规缺口（全篇无统计方法却有推断结论；涉人无任何伦理表述；直接暴露 PII；有编号引用但无文献表）。
- `major`：实质缺陷须修稿（文献表缺被引条目、p 值无检验名、强断言无支撑、必需声明缺失、第三方材料无许可）。
- `minor`：局部规范问题（引用格式不统一、缺资助号、缺数据可用性声明）。
- `suggestion`：风格或清晰度改进，**明确标注非规范违规**。
- `verdict_type`：`error` 事实/逻辑错误；`insufficient_evidence` 证据不足；`norm_violation` 违反明示规范或声明缺失；`suggestion` 建议。

## 10. 误报抑制与人工确认

1. 缺证据 ≠ 违规：材料未给声明页或附件 → `insufficient_evidence` + `pending_human`。
2. 风格差异最多 `suggestion`，并写明"非规范问题"。
3. 先判设计与体裁，再套统计/伦理条目（观察性研究不要求盲法）。
4. 同句多缺陷合并一条；不同位置不合并。
5. `dismissed` 必须写理由（"风格差异""学科惯例""材料未提供"），供复核。
6. 无法核验的对象（文献真实性、图像跨库复用、伦理批件真伪）一律进 `pending_human`。

## 11. 预算与断点

`result.json` 在任何阶段都合法：partial 阶段已含 `case_id`、契约键、`sources`、6 面 `checks` 与 `pending_human`。时间紧张时先 `--stage finalize`（无计划也合法），再补裁定。

## 12. 异常降级分支表

| 情况 | 表现 | 处置 |
|---|---|---|
| 输入目录不存在/为空 | `status=input_error`，`errors: input_missing` | 仍出 6 面 `checks` 与 partial 文件 |
| `case.json` 坏 JSON | 继续跑材料，`errors: case_json_invalid` | 契约字段为空，`contract_fields.requested=[]` |
| PDF 无文本层（扫描件） | `errors: pdf_no_text_layer`；全文 <400 字符时 `status=insufficient_evidence` | 提示改交可读文本，或把 OCR 结果放入 `<work>/review/text/*.txt` |
| 图片材料 | `degradations: image_not_read` | 不做图内推断，列 `pending_human` |
| DOCX/XLSX 解析失败 | `errors: docx_parse_failed / xlsx_parse_failed` | 该来源标 `unreadable`，其余照常 |
| 无文献表或不可解析 | `checks.citation_support` 只报"无文献表/未命中" | 不臆测文献存在性 |
| 裁定计划缺失 | `status=partial`，六面 `notes="无裁定计划"`，`degradations: plan_missing` | 不生成臆测意见 |
| 计划非法/顶层非对象 | `errors: plan_json_invalid` | 按无计划处理 |
| 意见 quote 未逐字命中 | 该意见不入 `issues`；进 `review_records.rejected_issues` + `pending_human` | 绝不放宽校验 |
| facet/severity/quote 非法 | 同上，理由列出缺项 | 提示按 `schema.md` 修正 |
| 同一问题重复提交 | 去重，记 `duplicate` | 保首条 |
| 某面判 `pass` 但有未裁定候选 | 强制改 `incomplete`，`notes` 列候选号，顶层降 `partial` | 防漏报 |
| 文件数超限 | `degradations: file_cap` | 只处理前 50 个（确定性顺序） |

## 13. 自检清单

1. `python3 scripts/main.py --help` 退出码 0。
2. 试跑含 `output_contract` 与 1 份材料的 `/input`：`result.json` 合法、契约字段齐全、`review_report.md` 与 `issues.csv` 存在且行数一致。
3. 空目录 / 坏 JSON：仍出 `status=input_error` 的 `result.json`，退出码 0。
4. 每条 issue 的 `quote` 能在其 `locator` 处逐字找到；`rejected_issues` 有留痕。
5. 六面 `checks` 全有 `status`；`summary.facet_coverage` 与 `status` 一致（<6/6 必为 `partial`）。
6. 无 `__pycache__`、无测试残留、无预制答案。

## 14. 最小调用示例与文件清单

调用示例、输入形态与示意输出（**示例，非正式案例结果**）见 `references/examples.md`。

```
SKILL.md                本文件：用途/契约/流程/清单/异常/自检
scripts/main.py         流程编排：发现→语料→候选→校验→契约回填→渲染
scripts/extract.py      解析/定位/引用结构/确定性检出库
references/checklist.md 34 项检查清单：证据要求·严重度锚点·误报清单
references/schema.md    输入输出 schema、locator 规则、词表、计划格式
references/examples.md  最小调用示例（标注示例）
```

依赖：Python ≥3.9 标准库（`json,re,csv,hashlib,zipfile,zlib,html,unicodedata,pathlib`）。无第三方包、无网络、无外部数据文件。

**维护**：新增检查项 → 在 `extract.detect()` 加检出器（`mk(facet,item,sev,quote,src,trigger,detail,safe,prio)`）并在 `checklist.md` 登记 ID；调整词表 → 同步 `schema.md` §3；两个脚本各保持 ≤20KB，改动后按 §13 自检。版本以 `result.json.runtime.skill_version` 为准。
