---
name: methods-stats-review
description: Reviews a research manuscript's methods and statistics and returns an evidence-bound review sheet (locator + verbatim quote + severity + fix) covering fact check, citation support, design, variables, tests, sample size, reporting, argument chain and research norms. Use when asked to 审稿/审查/检查 a paper's methods, statistics or reporting, or to produce a review report or 审稿意见 from a manuscript file.
version: 1.0.0
---

# methods-stats-review（review-03 研究方法与统计审查）

## 1 用途与边界
输入一篇稿件（PDF/DOCX/MD/TXT/JSON 及伴随材料），输出可交给作者逐条回复的**审查单**：
每条问题带 `locator`（章节/页/段）、**逐字 `quote`**、缺陷类型、严重度、依据、修改建议。
覆盖六类审查面（事实核验/引用支持/方法设计/统计报告/论证链/学术规范）× 五个检查面
（研究设计/变量定义/统计方法/样本量/结果报告）。

**不适用**：文献检索与综述、全文翻译、语言润色、代写审稿结论、投稿决策；扫描件与图片无 OCR。

## 2 运行契约
| 项 | 约定 |
|-|-|
| 入口 | `python3 scripts/main.py --run`（阶段 1）｜`--merge <json> --run`（阶段 2）｜`--help` |
| 输入 | `/input/case.json` + `/input/**` 材料（可用 `--input` 覆盖） |
| 输出 | `/app/output/`（可用 `--output` 覆盖）：`result.json`、`review_report.md`、`issues.csv`、`extracted/*.md` |
| 依赖 | 仅 Python 标准库；`pdftotext` 存在则优先调用，失败自动回退；不联网 |
| 退出码 | 恒 0。任何失败写入 `errors`/`degradations`/`pending_human` |
| 预算 | 单次运行 < 5 s、无模型请求；适合 64 请求 / 900 s 的 Harness 预算 |

## 3 输入发现（语义识别，不假设键名）
1. `case.json`（缺失则递归找 `case*.json`）→ 保留 `case_id`、原样透传 `output_contract`。
2. 递归扫描 `/input/**`（最多 300 个文件，跳过 `__pycache__/.git/node_modules/output`），
   按**扩展名 + 实际解析结果**识别：PDF→pdftotext，DOCX→`word/document.xml`，XLSX→sheet XML，
   JSON→文本解码，PNG/JPG 等→`image_not_parsed`（进 `pending_human`，不猜内容）。
3. `case.json` 内长度 > 400 且含方法/结果语义的字符串按"内嵌稿件"处理（locator 前缀 `inline:`）。
4. 材料未给的对象**明确列缺口**：`input_inventory.missing`、`uncertainty[]`。

## 4 输出契约
`result.json` 顶层：`case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`topic`、
`skill_version`、`input_inventory`、`summary`、`issues[]`、`checks{}`、`review_records`、`sources[]`、
`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime`、`artifacts`，
并**原样回填 `output_contract` 的每个键**（缺值 `null`/`[]`，键名不改，未知键保留）。

`issues[]` 单条：`id`、`rule_id`、`category`、`facet`、`defect_type`、`severity`、`evidence_strength`、
`title`、`locator`、`quote`、`reason`、`suggestion`、`evidence{kind,support}`、`confidence`、`source_id`。
字段语义见 `references/schema.md`；示例（**示例，非正式案例结果**）见同文件 §8。

## 5 核心流程（两阶段）
**阶段 1（脚本，确定性）**：抽取 → 段落/章节切分 → 32 条自动规则（`references/stat_rules.md` §6）
→ **逐字 quote 回查**（`verify_quote`：空白归一化后必须是源文档子串；命中失败的意见移入
`pending_human`，绝不进入 `issues[]`）→ `checks{}` 六类状态 → 写三份产物。
**阶段 2（Agent 判定，强烈建议）**：读 `output/extracted/*.md`（每行带 `§章节:¶段号`），按
`output/manual_checks_template.md` 逐条判定 14 项语义条目（结论强度、跨节数值一致、设计匹配、
作者-年份引用、检验与结构匹配等），写 `issues_model.json`（字段同 `issues[]`），再 `--merge` 归并；
quote 未逐字命中者一律进 `pending_human`。

## 6 评分要点 → 字段/检查/产物
| 评分维度 | 落点 |
|-|-|
| 任务完成度 15 | `checks{}` 六类全部运行（`pass/fail/manual/skipped` 四态）；`summary.facet_coverage` 五面 |
| 结果正确性 15 | 严重度锚点（`review_checklist.md` §1）；`evidence_strength` 区分 error/gap/judgment；数值自洽计算（F-02/S-02/S-04/C-01/C-02） |
| 结果完整性 5 | `issues.csv` 全字段；`review_report.md` §2–§5 |
| 结果可核验性 5 | 每条 `locator` + 逐字 `quote`；absence 类给检索词；报告 §7 复核步骤 |
| 质量/效率增益 25 | 自动定位 + 逐字引用 + 结构化交办，免去人工回查原句与补写依据；阶段 2 作业单降低返工 |
| 创新 15 | **quote 回查闸门**（改写/拼接引用一律拦下）、三档证据强度、数值自洽计算、六类×五面双坐标 |
| 可靠体验 10 | `--help`；空输入/坏 JSON 仍产合法 partial；扫描件、缺文献表、超短文本分别降级并可追溯 |
| 生态 10 | 46 条可复用规则（JSON 单一真源）、严重度定义、I/O schema、示例、限制说明 |

## 7 证据与定位规范
- `locator`：文本 `§方法:¶37`；PDF `p.3/¶12`；表格 `r4c2`；内嵌 `inline:<键>:¶5`；文献条目 `refs:#7`。
- `quote` 必须是 12–200 字符的**连续原文子串**；超长截断以 `…` 结尾（核验按前缀匹配）。
- **禁止**编造页码、表号、图号、文献编号、DOI、统计量；无法定位的内容不得进入 `issues[]`。
- `evidence.kind`：`numerical`（数值对照）/`contrast`（两处原文并列）/`absence`（全文无命中，须给检索词）。

## 8 冲突与人工确认
「作者没报告」≠「作者做错了」：`gap` 类写"未报告/无法核实"，不得写成"错误"；需领域外部信息
（剂量是否合理、结论是否有临床价值）→ `pending_human`。语言风格与期刊格式细节不在范围内，不得输出。

## 9 预算与断点
先写合法 partial `result.json` 再解析；每阶段结束即落盘；单文件解析异常只影响该文件。

## 10 异常降级分支表
| 情况 | 处置 | 落点 |
|-|-|-|
| 无 `case.json` | 继续用目录材料；无材料时 `status=input_error` | `errors[]` |
| case.json 坏 JSON | 记 `case_json_parse_error`，继续扫描材料 | `degradations[]` |
| 扫描件/图片 | 不猜内容，标待人工读图 | `pending_human[]` |
| PDF 无 pdftotext | zlib 流回退（无页码） | `degradations[]` |
| 无参考文献表 | C-05 记 major；C-01/02/03 标 `skipped` | `checks.citation` |
| 文本 < 800 字符 | 抑制缺失类规则，`status=insufficient_evidence` | `uncertainty[]` |
| 规则目录缺失 | `rule_catalog_load_failed`，仍输出合法 partial | `errors[]` |
| 未捕获异常 | `fatal()` 写合法 partial | `errors[].code=unhandled_exception` |

## 11 自检清单
1. `python3 -B scripts/main.py --help` 退出码 0。
2. `result.json` 含 `output_contract` 全部键；`case_id` 原样。
3. `issues[]` 每条 quote 可回查（`summary.quote_failed == 0`）。
4. `checks{}` 六个键齐全，无 `not_checked`（除非无正文）。
5. `review_report.md`、`issues.csv` 与 `result.json` 计数一致。
6. 空输入/坏 JSON 均产出合法 partial 且退出码 0。

## 12 最小调用示例（示例，非正式案例结果）
```bash
# 阶段 1
python3 scripts/main.py --run --input /input --output /app/output
# 阶段 2（可选）：按 manual_checks_template.md 判定后
python3 scripts/main.py --merge /app/output/issues_model.json --run
```
示例输入：`{"case_id":"EXAMPLE-001","output_contract":{"issues":null,"custom":"keep"},
"manuscript_file":"artifacts/demo.md"}`｜示例输出 `issues[0]`：
`{"id":"I01","rule_id":"S-08","severity":"major","locator":"§方法:¶12",
"quote":"两组各纳入 40 例患者，比较治疗前后差异。", ...}`。
**以上仅为接口示意，不是任何正式案例结果。**

## 13 文件清单与版本
| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（用途、契约、流程、降级、自检） |
| `scripts/main.py` | 引擎：输入发现、检测、编排、落盘 |
| `scripts/verify.py` | 抽取、文档模型、逐字核验、`checks{}`、阶段 2 归并、渲染 |
| `references/review_checklist.md` | 检查项权威定义 + 严重度锚点（复用核心） |
| `references/stat_rules.md` | 规则说明、误报护栏、缺陷类型库 + §6 机器可读规则目录 |
| `references/schema.md` | 输入输出契约、locator 语法、最小示例 |

版本 1.0.0；仅标准库；无网络；资源定位一律 `Path(__file__).resolve().parent`，不依赖 CWD。

## 14 维护说明
新增检查项：在 `stat_rules.md` §6 追加一行 JSON 并在 `review_checklist.md` 登记 ID（无需改代码）；
`kind=manual` 表示交阶段 2 判定。新增输入格式：在 `verify.extract()` 增加分支并在 §3 登记。
调整严重度锚点须同步 `review_checklist.md` §1，保持同一缺陷前后判级一致。
