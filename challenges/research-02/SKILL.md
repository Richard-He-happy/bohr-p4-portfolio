---
name: literature-review-evidence-mapper
description: Turn a supplied folder of real papers, abstracts, bibliographic records and protocol notes into a traceable literature review. Builds a prospective screening protocol before reading results, handles duplicates and abstract-only records, induces themes bottom-up from the supplied corpus, maps every claim to a verbatim quote plus locator, stages conflicting evidence side by side, grounds research gaps in explicit evidence gaps, and emits a contract-complete result.json with evidence_map.csv and review.md. Use when asked for a literature review, systematic screening, evidence synthesis, theme/topic analysis, research-gap analysis, or a citation-traceable review draft over given sources.
version: 1.0.0
license: MIT
---

# 文献综述生成：筛选 → 主题 → 证据 → 草稿

## 1. 用途与边界

把一个真实文献集转成四件可复核的产物：**筛选记录**（标准先于写作）、**主题归纳**（从这批文献长出来）、**证据矩阵**（每条论断 → 源 + 定位 + 逐字摘录 + 强度）、**综述草稿**（每句实质论断可回链）。

做：研究问题分解、检索/证据覆盖说明、分主题综合、冲突与空白、引用可追溯表。
不做：单篇精读报告、全文翻译、语言润色、投稿选刊、事实层面的学术审查。不引入材料外文献、数值或结论。

**硬边界**：只有材料里出现的文献才算数。缺全文、缺元数据、缺字段时写成缺口，不补造。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下任意材料（PDF/CSV/XLSX/DOCX/JSON/MD/TXT/图片） |
| 工作区 | `/app/work`（中间件）、`/app/output`（交付件） |
| 入口 | `python3 scripts/main.py all`（`collect` + `assemble` 两段等价于 `all`） |
| 校验 | `python3 scripts/verify.py`（确定性检查，打印报告，非 0 也算通过只需看报告） |
| 退出码 | 恒 0；任何异常进 `errors`，不让流程中断 |
| 依赖 | 仅 Python 标准库；不联网；不依赖 CWD（脚本用 `Path(__file__).resolve().parent`） |
| 预算 | 64 次模型请求 / 900 秒 / 单回复 16384 tokens；约 780 秒立即 finalize |

脚本 argv 可覆盖目录：`--input DIR --output DIR --work DIR`（评测时默认值即可）。

## 3. 调用方式（两种执行形态）

**形态 A（推荐，Agent 有推理预算）**

```bash
python3 scripts/main.py collect     # 抽取语料、候选证据、主题簇、筛选工作表；先落 partial result.json
# Agent 读 /app/work/next_steps.json、corpus.json、candidates.csv → 写 protocol.json、screening.csv
# Agent 写 /app/output/evidence_map.csv 与 /app/output/review.md（用 work/ 里的定位与逐字摘录）
python3 scripts/main.py assemble    # 校验 quote/契约/计数，finalize result.json
python3 scripts/verify.py           # 自检报告；按 rejected 行修引用
```

**形态 B（无 Agent 编辑能力或时间不足）**：`python3 scripts/main.py all` 一条命令产出基线草稿（`draft_mode="deterministic_baseline"`，status=`partial`），保证永远有合法交付。

## 4. 输入发现（语义识别，不假设键名）

1. 读 `case.json`；不存在则递归找 `case*.json`/`task.md`，仍可解析。
2. 原样保留 `case_id` 与 `output_contract`（键名不改、未知字段保留、缺值 null/[]）。
3. 语义识别：研究问题/任务指令（`task_instruction`、`research_question`、`question`、`topic`、`prompt`）、范围（`scope`、`organizer_supplied_scope`）、工单（`organizer_workorder`、`formal_inputs`、`runtime_files`）、文献清单（`papers`、`records`、`sources`、`literature`、`references`）、纳排约束（`criteria`、`inclusion`、`exclusion`）。
4. 递归扫描 `/input/**`，按扩展名 + 魔数识别，**不按标签猜内容**。每个文件登记 `source_id`、路径、类型、可用字段、定位体系。
5. 材料未给的对象写进 `gaps` 与 `pending_human`，不构造。

## 5. 七步工作流

| # | 动作 | 归属 | 落盘 |
|---|---|---|---|
| 1 | 语料抽取：文本 + block 级 locator（`p.3`/`para.12`/`row.7`/`block.4`）+ 元数据 | 脚本 | `work/corpus.json` |
| 2 | **先写筛选协议**（研究问题、PICO、纳入/排除标准、去重规则、证据强度定义） | Agent → `work/protocol.json` | 时间上先于筛选 |
| 3 | 筛选：逐条 `include/exclude` + 理由码 + 命中标准 | Agent → `work/screening.csv` | `output/screening_log.csv` |
| 4 | 主题归纳：读 `work/themes.json`（脚本给共享词簇与代表文献），改名/合并/拆分，写 `basis` 与边界 | Agent | `output/result.json:themes` |
| 5 | 证据组织：从 `work/candidates.csv` 选句，逐字回填 `quote`，写 `claim`/`strength` | Agent → `output/evidence_map.csv` | 一行一论断 |
| 6 | 起草：按主题写 `review.md`，每句实质论断挂 `[S03]`（可选 `{E012}` 指证据行） | Agent | `output/review.md` |
| 7 | 校验交付：quote 命中、契约回填、计数、冲突/空白回链 | 脚本 | `output/result.json` |

协议必须先于筛选：`protocol.json` 的 `criteria` 一旦写入，后续筛选只允许引用，不允许为迁就结果改标准；必须改时记 `changes`。

## 6. 输出契约（四件套）

| 文件 | 内容 | 完成标准 |
|---|---|---|
| `output/result.json` | 主结果 + 契约全字段 + `status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime` | 键名与输入 `output_contract` 一致，`case_id` 原样 |
| `output/review.md` | 综述正文：研究问题、筛选与覆盖、分主题综合、冲突、空白、局限、参考文献 | 每句实质论断带引用 |
| `output/evidence_map.csv` | `evidence_id,claim,source_id,locator,quote,strength,claim_type,topic,verification` | 关键判断可回材料 |
| `output/screening_log.csv` | `source_id,title,year,doi,decision,reason_code,criterion,note,verification` | 每条文献有决定与理由 |

`status` 取值：`ok`｜`partial`｜`insufficient_evidence`｜`input_error`。**做不到 `ok` 就写 `partial` 并列出缺口与人工动作**，不把未读内容写成事实。

## 7. 评分点 → 字段/检查/产物

| 评分点 | 落点 | 机器检查 |
|---|---|---|
| 任务完成度 15 | 四步全跑 + `review.md` 存在 + `pipeline_steps` 全 true | 文件存在 + 章节齐全 + 非空 |
| 结果正确性 15 | `evidence_map.csv` 的 `quote` + `locator` | quote 归一化后在对应 block 内命中（`verified`/`verified_lenient`/`rejected`） |
| 结果完整性 5 | `themes` 覆盖、`conflicts`、`gaps`、正反证据 | 主题覆盖源比例、纳入文献未覆盖清单 |
| 结果可核验性 5 | `sources`、`screening_log`、`runtime.versions` | 每源有 id/路径/sha1；计数自洽 |
| 质量增益 15 | `review.md` 主题由语料驱动、论断—证据一对一、强度分层 | 引用覆盖率、`strength` 分布、无引用句计数 |
| 效率增益 5 | `candidates.csv` 预切句、`themes.json` 预聚类、`quote` 自动校验 | 候选句数、主题簇数、人工待办条目数 |
| 增益可验证性 5 | `runtime.counts` + `changes` + `verify.py` 报告 | 计数可重算、报告可复跑 |
| 新增能力 5 | 逐字 quote 门禁 + 契约回填器 + locator 一致性 | `verification` 列统计 |
| 方法改进 5 | 协议先于筛选、主题来自共词簇、空白来自证据缺口 | `protocol.order_ok`、`themes[].basis`、`gaps[].linked_sources` |
| 创新证据 5 | `counts`/`evidence_summary`/`review` 三项统计 + `degradations` 记录 | 计数可由 CSV 重算 |
| 调用与易用性 3 | 本文档 §3/§16 + `--help` | `--help` 退出码 0 |
| 运行稳定性 4 | 两级目录解析、逐文件降级、先 partial 后 finalize | 空输入/坏 JSON 仍产出合法 JSON |
| 异常处理 3 | `degradations`/`errors`/`pending_human` + 分支表 §13 | 每类异常有对应记录 |
| 文档完整性 3 | 本文档 + `references/` 两件 | 引用文件均存在 |
| 资源可复用性 4 | `verify.py`、CSV 模板、理由码词表 | 可对任意文献集复跑 |
| 分享推广价值 3 | `references/evidence_schema.md` 的证据表规范与写法 | 通用规范非案例专属 |

## 8. 证据与定位规范

- **quote 必须逐字**：来自 `work/corpus.json` 的 block 文本，允许改动的只有省略号；不许改写、拼接、翻译、纠错。找不到就换句，或进 `pending_human`。
- **locator 语法**：`p.<n>`（PDF 页，`\f` 分页可信时）、`block.<n>`（PDF 流块，页码不可信时）、`para.<n>`、`row.<n>`、`rec.<n>`、`sec:<标题>`；可加 `#c<char>` 字符偏移。
- **strength**：`directly_supported`（原文明确陈述该关系/数值）｜`inferred`（由多条原文合理推出，需写出推理）｜`insufficient`（材料只到摘要/单例/间接，写清缺什么）。
- 引述强度必须与原文一致：原文 `may`/`suggests`/`associated with` 不得写成 `proves`/`causes`。

## 9. 筛选协议规范

`work/protocol.json`：

```json
{"research_question": {"primary": "", "sub_questions": [], "pico": {"population": "", "intervention": "", "comparison": "", "outcome": ""}},
 "criteria": {"include": [{"id": "I1", "text": ""}], "exclude": [{"id": "E1", "text": ""}]},
 "dedup_rule": "DOI 优先，无 DOI 用 归一化标题+首作者+年",
 "strength_rule": "见 references/evidence_schema.md",
 "written_before_screening": true}
```

理由码（`screening_log.csv.reason_code`）：`I1..I9` 命中纳入标准；`E1` 主题不符、`E2` 人群/对象不符、`E3` 方法不符、`E4` 无全文且摘要不足、`E5` 重复、`E6` 非研究性文本、`E7` 年份/语言超范围、`E8` 数据不可用、`E9` 其他（须写明）。每个排除必须给码 + 一句话理由，且能指回原文。

## 10. 主题归纳规则

主题只能从这批文献的共同点长出来：方法路线、研究对象、结论方向、材料/尺度/场景。禁止套「背景—方法—挑战—展望」四段壳。

- 每个主题写 `label`、`basis`（共现词或方法/对象信号 + 支撑源）、`sources`、`boundary`（该主题不含什么）。
- 主题数 3–7；单源主题保留但标 `thin=true`，并进 `gaps`。
- 主题必须覆盖全部 `include` 文献，或明确写出未归类源及原因。
- 脚本给的 `work/themes.json` 只是候选（共词聚类），**命名与边界由 Agent 定**，并写 `derived_from: "corpus_cluster"|"agent_revision"`。

## 11. 冲突、空白、不确定性

- **冲突**：同一问题下结论相反/方法互斥的文献必须并列呈现（`conflicts[]`：`topic`、`side_a`、`side_b` 各带源与 quote、`basis_of_conflict`＝人群/剂量/终点/方法差异、`resolution`＝`unresolved`｜`explained_by`）。脚本给的 `conflict_candidates` 只是候选，须判定或标 `unresolved`。
- **空白**：只能落在证据缺口上（`gaps[]`：`statement` + `linked_sources` + `evidence_gap` 类型：`no_fulltext`｜`single_source`｜`unresolved_conflict`｜`missing_outcome`｜`method_gap`）。禁止「未来研究应进一步探索」式套话。
- **不确定性**：冲突、偏倚（单库/单国/单团队、仅摘要、样本小）、空白、无法确定项，逐条进 `uncertainty[]`，每条带影响范围。

## 12. 结果强度分层表述

`directly_supported` 用「已报告/显示/在该样本中观察到」；`inferred` 用「提示/可推断/与…一致」；`insufficient` 用「尚不能判断/仅摘要层面」。反向证据出现时写「但 S0x 报告了相反结果」，不平滑掉。

## 13. 异常降级分支

| 情况 | 处置 | 记录 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找替代，仍失败→空壳继续 | `input_error` + `errors[]` |
| PDF 无文本层 | `pdftotext`/`pypdf`/纯 Python 流解析三级降级；仍空→`abstract_only` | `degradations[]`，locator 用 `block.n` |
| 仅摘要 | 纳入但标 `fulltext=false`，论断上限 `inferred` | `gaps: no_fulltext` |
| 元数据不全 | 用文件名/首页推断并标 `metadata_estimated=true`；DOI 缺失不编 | `pending_human[]` |
| 重复文献 | DOI/标题+年归并，保留信息最全者 | `dedup` 计数 + `E5` |
| 结论冲突 | 并列呈现，不取平均 | `conflicts[]` |
| 超上下文 | 按主题分批读 `corpus.json`，先写 `review.md` 大纲再逐节补 | `changes[]` |
| 检索/材料为空 | `status=insufficient_evidence`，写清缺什么、要什么 | `pending_human[]` |
| 图片材料 | 只登记存在，不做像素推断 | `degradations[]` |
| 时间/预算将尽 | 立即 `assemble`，`partial` 收尾 | `runtime.budget_note` |

## 14. 预算与断点

`collect` 一结束就写合法 partial `result.json`；`assemble` 无条件覆盖为 final。任何一步失败只降级该步，其余产物保留。接近 780 秒直接 finalize。

## 15. 自检清单

- [ ] `result.json` 含 `output_contract` 全部键（`contract_backfill.missing == []`）、`case_id` 原样
- [ ] `status` 与实际情况一致；`errors`/`degradations`/`pending_human` 非空时正文有对应说明
- [ ] `evidence_map.csv` 无 `rejected` 行（或已列入 `pending_human`）
- [ ] 每个 `include` 文献至少出现在一个主题或明确未归类
- [ ] `conflicts` 有正反两方 quote；`gaps` 均挂 `linked_sources`
- [ ] 引用编号连续且与 `sources` 一一对应；无悬空 `[S99]`
- [ ] 无材料外文献/数值/DOI；无「示例」串入正式结果

## 16. 最小调用示例（示例，非正式案例结果）

输入（示例）：

```json
{"case_id": "demo-000", "task_instruction": "Compare methods for X on Y and identify gaps.",
 "output_contract": {"review_md": "string", "evidence_matrix": "array", "themes": "array", "uncertainty": "array"},
 "artifacts": ["papers/"]}
```

调用（示例）：

```bash
python3 scripts/main.py all --input ./demo_input --output ./demo_output --work ./demo_work
```

示意输出（示例，非正式案例结果）：

```
demo_output/result.json        status=partial, themes=3, evidence_rows=12, contract_backfill.missing=[]
demo_output/review.md          "## 1 研究问题 … [S01] … " (deterministic_baseline)
demo_output/evidence_map.csv   E001,S01,p.2,"…verbatim…",inferred,…
demo_output/screening_log.csv  S01,include,I1,…
```

## 17. 文件清单与版本

```
SKILL.md                              本文件，流程与契约
scripts/main.py                       抽取/筛选表/主题簇/证据候选/起草/契约回填（stdlib）
scripts/verify.py                     确定性校验：quote、locator、契约、计数、引用（stdlib）
references/evidence_schema.md         result.json 与 CSV 字段、locator/strength 规范、理由码、写法规则
references/templates.json            契约别名（aliases）、多语言章节标签（labels）、反义/冲突标记（oppose）、筛选词表（criteria）
```

版本 `1.0.0`；无第三方依赖；无网络；资源均为文本，路径相对脚本目录解析。

## 18. 维护说明

改流程只改 `main.py` 的阶段函数与本文档表格；新增字段先进 `references/evidence_schema.md` 再改代码，避免契约漂移。`verify.py` 是唯一判据来源：任何"看起来对"的结论以它的报告为准。回归方式：`main.py all` + `verify.py` 在最小示例上全绿后再提交。
