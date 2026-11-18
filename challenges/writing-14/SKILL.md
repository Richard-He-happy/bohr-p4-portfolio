---
name: proposal-writing
description: 依据 case.json 与材料（指南/前期数据/讨论记录/文献）写开题报告与研究计划书，七要素齐全、研究问题可证伪、里程碑与风险可检查；带金标准对照（27 条判据）、逐字证据核验、自检与版本回退记录，脚本兜底必出稿。
version: 2.1.0
---

# 开题报告与研究计划书（proposal-writing）

**一句话**：Agent 读材料亲自写工作稿 `draft.json`，脚本负责索引、校验与成稿；脚本永远能交出一份最小但完整的稿子。

适用：把研究基础材料组织成开题报告/研究计划书，含七要素（背景缺口、研究问题、目标、技术路线、阶段计划、风险、预期成果）。不适用：纯文献综述、纯润色、投稿信。

## 1. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（`case_id`、`task_instruction`、`output_contract`、可选 `organizer_workorder`）+ `/input/**` 材料 |
| 工作区 | `/app/work`：`index.json`、`draft.json`、`draft.effective.json`、`check_report.json` |
| 产物 | `/app/output/`：`proposal.md`（主产物）、`proposal_matrix.json`、`milestones.csv`、`risks.md`、`result.json` + 5 件可核验资产（§6.1） |
| 依赖 | Python 3.8+ 标准库；不联网；不依赖 CWD（`Path(__file__)` 定位） |
| 退出码 | 恒 0；异常写进 `result.json.errors`/`degradations` |
| 预算 | 64 次请求 / 900 秒；>780 秒直接 `build` 收尾 |

## 2. 标准流程（Agent 主答，脚本辅助）

```bash
python3 /skills/weekly-skill/scripts/main.py init    # ① 索引 + 首份 partial result.json
# ② Agent 读材料，写 /app/work/draft.json（§3）；引文逐字抄原文
python3 /skills/weekly-skill/scripts/main.py check   # ③ 要素/判伪/证据/周期/数字
python3 /skills/weekly-skill/scripts/main.py build   # ④ 成稿 + 终版 result.json + 5 件资产
python3 /skills/weekly-skill/scripts/main.py audit   # ⑤ 只重算资产与 pmatrix/csv/risks.md
python3 /skills/weekly-skill/scripts/main.py show --id M1 --grep 周期   # 回看原文
```

参数：`--input/--output/--work`（默认 `/input`、`/app/output`、`/app/work`；亦可用 `INPUT_DIR` 等环境变量）。

**分工**：`init` 只做机械索引；内容判断由 Agent 做。`check` 只报告不改稿；`build` 接受不完美工作稿，缺什么用模板补什么并记 `degradations`。

### 2.1 输入发现

递归扫 `/input`，不假设键名：`case.json` 缺失时按 `case*.json`/`input*.json` 兜底，键按语义识别（`task_instruction`/`organizer_workorder`/`output_contract` 等）。材料按扩展名 + 魔数识别（`%PDF`、`PK`），JSON 一律 `utf-8-sig` 读（防 BOM）。`init` 打印 `M1..Mn`、类型、字数、段数、抽取方式与识别到的周期；段落定位为 `M3/p2`。

### 2.2 异常降级（均不中断）

| 情况 | 处理 |
|---|---|
| case.json 缺失/坏 JSON | 递归找替代文件；仍失败则 `errors` 记解析错误，按材料继续 |
| 图片材料 | 不转写像素，记 `no_ocr`，不猜内容 |
| PDF 无文本层 | 依次试 `pdftotext`→`pdf-text-tool`→PyMuPDF→pdfminer→标准库粗解析；只降级该材料 |
| 周期识别不到 | 里程碑按 12 个月占位并进 `pending_human` |
| 无工作稿 | 模板生成完整骨架，`status=partial` |
| 只有 draft.md | 正文按标题成节，表格要素用模板补，`status=partial`（`agent+template`） |

## 3. 工作稿 `draft.json`（Agent 唯一必写文件）

```jsonc
{
  "title": "…",
  "period": {"total": "24 个月", "quote": "执行期：24 个月", "source": "M1/p2"},
  "rqs": [{"id": "RQ1", "question": "…能否…（含对象与条件）", "hypothesis": "可被数据否定",
           "falsifier": "若…观测出现则假设被否定", "metrics": [{"name": "200 h 保持率", "threshold": "≥85%", "basis": "M4/p1"}],
           "sample": "12 例", "condition": "0.1 M 恒电位", "timepoint": "第 12 月",
           "evidence": [{"source_id": "M1", "locator": "p4", "quote": "逐字原文"}]}],
  "sections": [{"id": "background|problem|objectives|methods|plan|risks|outcomes",
                "blocks": [{"text": "正文", "evidence": [{"source_id": "M1", "locator": "p3", "quote": "逐字原文"}]}]}],
  "objectives": [{"id": "O1", "rq": "RQ1", "objective": "…", "criterion": "可检查判据"}],
  "steps": [{"id": "S1", "rq": "RQ1", "input": "…", "action": "…", "output": "…", "depends_on": []}],
  "resources": {"budget": "45 万元（M1/p2）", "people": "…", "data": "…", "note": "…"},
  "milestones": [{"id": "MS1", "period": "第 1–6 月", "task": "…（S1）", "deliverable": "…",
                  "depends_on": "—", "criterion": "…", "critical_path": true}],
  "risks": [{"id": "R1", "type": "数据获取|方法可行性|进度|伦理与合规", "risk": "…",
             "trigger": "可观测信号+时点", "impact": "…", "fallback": "…", "decision_point": "…"}],
  "outcomes": [{"id": "D1", "rq": "RQ1", "outcome": "…", "verification": "怎么复跑", "criterion": "…"}],
  "preserved_facts": [{"term": "执行期", "value": "24 个月", "source_id": "M1", "locator": "p2", "quote": "…"}],
  "change_log": [{"action": "起草", "target": "proposal.md", "reason": "…", "before": "—", "after": "v1"}],
  "pending_human": [{"item": "阈值 ≥15%", "why": "材料未给", "needed_by": "答辩前"}]
}
```

也可只写 `/app/work/draft.md`，用七个小节标题（`## 一、研究背景与缺口` … `## 七、预期成果与验证方式`）；此时状态必为 `partial`。

## 4. 质量规则（对齐评分点）

1. **立得住**：`question` 含对象+条件；`falsifier` 写清"何种观测会否定它"；每个 `metric` 有 `threshold` 与 `basis`。
2. **对得上**：目标 `rq` 指回 RQ；`steps.output`/`depends_on` 串成路线；`outcomes.verification` 说明怎么复跑。
3. **排得开**：里程碑落在材料给的周期内（超期判错）；每条有 `criterion`；标关键路径。
4. **说得清**：风险 ≥4 条、≥3 类，每条 `trigger`+`fallback`+`decision_point`；`quote` 逐字命中。
5. **不越界**：材料外的数字/文献/结论一律不写；计划新增值标"计划值"；缺口进 `pending_human`；不把设想写成结果。

## 5. `check` 判什么

- 七要素是否成节、是否过短（<20 词提醒）。
- RQ 的 `question`/`falsifier`/阈值是否齐，阈值是否给依据。
- 里程碑 <3、风险 <4、风险类型 <3 类、成果缺验证方式。
- **周期相容**：里程碑最远月份 > `period.total` → 错误。
- **数字一致**：草稿"数字+单位"在材料中找不到同形文本 → 提醒（须标计划值或补依据）。
- **引文核验**：按去空白逐字比对；命中率 <90% → `build` 判 `partial`。找不到就报，不改原文凑通过。

## 6. 输出契约

`result.json` 原样回填 `output_contract` **每个**字段（不改名、不遗漏，缺值 `null`/`[]`），另带 `case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`deliverable`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`coverage`、`counts`、`preserved_facts`、`evidence_map`、`change_log`、`milestones`、`risks`、`outcomes`。契约字段按语义映射（如 `research_question_falsifiability`→RQ 列表、`milestone_feasibility`→里程碑），未知字段给 `null` 但保留键。

状态：工作稿齐全、无错误、命中率 ≥90% → `ok`；用兜底/模板补要素、有错误或命中不足 → `partial`；材料无可解析文本 → `insufficient_evidence`；无材料 → `input_error`。

## 6.1 可核验资产（v2 新增，`build` 自动生成；`audit` 可重算）

| 文件 | 内容 | 复核方式 |
|---|---|---|
| `golden_standard.json` | G01–G27 金标准：8 要素 + 元数据的逐项期望、`must_have`、`check`、rubric、逐字锚点 | 每条带 `source_id/locator/quote`，`show` 可回看原文 |
| `diff_report.md` | 金标准 vs 实际产物逐项对照（pass/missing/deviation）+ 现状 + 处置 + 锚点核验 | 每行对应 `scripts/assets.py` 的 `rule:<名>` |
| `version_history.md` | v0 模板骨架 → v1 成稿：改了什么/为什么/如何回退；含包版本变更 | 回退命令可直接执行 |
| `run.log` | 每次命令的时间、耗时、降级、异常（追加写，超 64KB 留尾） | 跨命令累积，可对时序 |
| `self_check.json` | 契约完整性、证据覆盖率、数字/引用一致性、空/坏输入探测、真实退出码 | `overall_pass` + `checks` + `failures` |

`result.json` 另增 `golden_standard`/`diff_report`/`version_history`/`self_check`/`artifacts`/`period` 字段，**原 `output_contract` 字段全部保留并回填**。`build` 把生效工作稿存入 `/app/work/draft.effective.json`，使 `audit` 结论与 `build` 一致。

## 7. 自检清单（成稿前逐条过）

- [ ] 七要素齐；背景是"已知—未知—待验证"，不是领域综述。
- [ ] 每条 RQ 有判伪条件与阈值；阈值有来源或进 `pending_human`。
- [ ] 里程碑落在周期内，有交付物与完成判据；关键路径已标。
- [ ] 风险覆盖数据/方法/进度/伦理，每条有触发信号与备选。
- [ ] 引文 `quote` 与原文逐字一致；`M#/p#` 可回查。
- [ ] 数字、单位、样本量、经费与材料同形；新增值标"计划值"。
- [ ] `pending_human` 写清缺什么、何时补。
- [ ] `status` 与实际完成度一致。
- [ ] `diff_report.md` 全部 pass，或每条非 pass 都有处置归属（脚本可补 / pending_human）。
- [ ] `self_check.json` 的 `checks` 全 true；未通过项已写明原因。

## 8. 最小调用示例（示例，非正式案例结果）

```bash
$ python3 scripts/main.py init --input /input --output /app/output --work /app/work
== init v2.1.0 == /input/case.json | task.md /input/task.md
contract case_id, deliverable, preserved_facts, evidence_map, change_log | materials 5 | chars 612 | period (24, '执行期：24 个月')
  M1  guide.md                text   311字   5段 plain
  M2  meeting_notes.docx      docx    93字   3段 zip-openxml
NEXT: write /app/work/draft.json then check then build
```
`check` 打印计数与错误/提醒；`build` 打印 `status`、`proposal.md` 大小、要素覆盖与引文命中数，并落 10 个产物；`audit` 只重算资产。以上数字仅示意接口，**不是任何正式案例的评测结果**。

## 9. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明 |
| `scripts/main.py` | 抽取/索引/契约/命令（约 20KB） |
| `scripts/proposal.py` | 工作稿解析、证据核验、校验、兜底、渲染（约 20KB） |
| `scripts/assets.py` | **v2 新增**：金标准 27 条判据、diff/版本/self_check/run.log、矩阵与 csv/risks 产物（约 56KB） |
| `references/plan-template.md` | 七要素检查表 + 表头 + 兜底文案与行模板（`<!-- KEY:... -->` 块） |

共 5 个文件、~117KB。版本 2.1.0。改表头/兜底文案只改 `plan-template.md`；改校验改 `proposal.py` 的 `check()`；改金标准判据只改 `assets.py` 的 `G` 表与 `rule:*` 函数。三脚本纯标准库、支持 `--help`。

## 10. 维护与已知边界

- 定位基于"段"（空行分隔）；PDF 粗解析可能丢失阅读顺序，重要引文先 `show` 回看原文。
- 图片不做 OCR；表格按行转文本，不还原公式或合并单元格。
- 数字一致性是**字面匹配**，`85%` 与 `85 %` 会误报为提醒，属预期。
- 学科差异（伦理批件号、样机指标等）由 Agent 在 `pending_human` 补，不硬编码在脚本里。
- 金标准锚点优先用关键词命中；材料短或无对应词时退为“最长可读段落”的 context 锚点（`anchor_kind` 已标注），不伪造定位。
- `self_check` 的子进程探测可用 `SKILL_INNER=1` 关闭（内部调用已自动关闭，避免递归）。
