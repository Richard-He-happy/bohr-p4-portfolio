---
name: paper-reproduction-verify
description: Run a paper's candidate implementations for real, compare the observed metrics with the reported ones under a tolerance that was declared before the run, attribute each difference, and emit a reproduction record plus result.json that others can re-check. Use for reproduction, method verification, "结果对不上" attribution, parameter restoration, or environment/run-log alignment tasks.
version: 1.0.0
---

# 论文复现与方法验证（Agent 主答 + 脚本辅助）

## 1. 用途与边界

**用途**：给定论文材料（PDF/MD/表格）与一到多份候选实现/数据，完成
「材料定位 → 环境快照 → 参数复原 → 实际运行 → 事前容差比较 → 差异归因 → 分级结论」并交付可复核产物。

**边界（必须遵守）**：

- 复现结论只覆盖**实际运行到的**候选与指标。没跑起来就写 `insufficient_evidence`，不写"应该一致"。
- 数值只来自真实运行输出或材料原文；不得估算、补造、沿用记忆中的论文数字。
- 支持纯标准库能解析的材料（PDF 文本层、DOCX、XLSX、CSV、JSON、MD、TXT）。
  图片/扫描页无 OCR 时进 `pending_human`，不猜像素或图注。
- 不联网、不安装依赖、不改宿主环境。

## 2. 运行契约

| 项 | 值 |
|---|---|
| 输入 | `/input/case.json`（含 `case_id`、`output_contract`、workorder）与 `/input/**` 材料 |
| 工作区 | `/app/work`（`index.json`、`tolerance_plan.json`、`draft.json`、`runs/`） |
| 产物 | `/app/output/result.json`、`reproduction.md`、`reproduction.json` |
| 包根 | `SKILL.md` 所在目录；命令用绝对路径调用 |
| 依赖 | 仅 Python 3 标准库；不依赖 CWD（可用 `SCIM_INPUT/SCIM_OUTPUT/SCIM_WORK` 覆盖路径） |

进入任务先定位包根并确认脚本可运行：

```bash
SK=/skills/weekly-skill; [ -f "$SK/SKILL.md" ] || SK="$(dirname "$(find / -maxdepth 4 -name SKILL.md 2>/dev/null | head -1)")"
python3 -B "$SK/scripts/main.py" --help
```

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`（`utf-8-sig`，容忍 BOM/GB18030）；损坏时仍继续，错误写进 `errors`。
2. 递归扫描 `/input/**`，跳过 `case.json`；按**扩展名 + 魔数**判定类型（`%PDF`、`PK`+`word/`、`xl/`、PNG/JPEG 等），不按标签猜内容。
3. 识别 case 里的 `task_instruction`、`organizer_supplied_scope`、`organizer_workorder`、
   `candidates/implementations`、`reported_metrics`、`environment`、`output_contract` 等语义字段。
4. 每个材料分配稳定 `id`，并把正文切成带 `locator` 的单元：
   `paper:p3`（PDF 页）/`md:§标题/p2`/`csv:r7`/`json:#/results/accuracy`。

## 4. 输出契约

`result.json` **原样回填 `output_contract` 的全部字段**（不改名、不遗漏、缺值 `null`/`[]`），并保证存在：
`case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`sources`、`uncertainty`、
`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

字段按语义映射（键名不必一致）：`repro*`→复现记录、`compar*`→对比行、`attribut*`→归因、
`toler*`→容差表、`run*`→运行日志、`param*`→参数表、`evid*`→证据、`conclusion/verdict`→结论。
未识别的契约字段填 `null` 并在 `degradations` 记 `contract_field_unmapped:<字段>`。

## 5. 核心流程（四步，Agent 是主答）

```bash
cd /app/work
python3 -B "$SK/scripts/main.py" init      # ① 索引 + 事前容差 + 先写 partial result.json
python3 -B "$SK/scripts/main.py" show --id paper --grep "accuracy"   # ② 读原文（带 locator）
# ③ 你亲自写 /app/work/draft.json（见 §6；骨架在 /app/work/draft_skeleton.json）
python3 -B "$SK/scripts/main.py" check     # ④ 校验证据/字段/容差是否被事后放宽
python3 -B "$SK/scripts/main.py" build     # ⑤ 真实运行 + 比较 + 归因 + 定稿
```

**分工**：脚本负责确定性的事（索引、定位、跑代码、算偏差、校验、渲染）；
Agent 负责需要判断的事（复现计划、参数取值依据、指标口径、归因解释、结论措辞）。

`init` 会打印材料清单、段落预览、workorder 摘要与容差表——先读它，再决定读哪些原文。
`build` 无条件定稿：工作稿缺失/不完整时用确定性最小交付（仍写 `reproduction.md`、`result.json`，
`status=partial` 并列出缺口），不会空、不会崩、退出码恒 0。

## 6. 工作稿 `/app/work/draft.json`

最小可用骨架（完整字段见 `references/draft_schema.md`）：

| 字段 | 要求 |
|---|---|
| `paper` | 标题/DOI/repo/commit；未知写 `null`，不编造 |
| `plan` | 复现步骤（命令、期望、状态） |
| `environment` | python/平台/依赖版本/seed；由 `init` 与本机实测填 |
| `params` | 每个关键参数：值、`class`（`paper`/`code_inferred`/`chosen`）、`evidence{source_id,locator,quote}` |
| `paper_values` | 指标名（与候选输出同名）、报告值、单位、逐字 quote |
| `tolerance` | 只能等于或**严于** `tolerance_plan.json`，否则 `check` 报 `tolerance_widened_after_run` |
| `claims` | 每条含 `kind`、`text`、`confidence`（`direct`/`inferred`/`undetermined`）、逐字 `quote` |
| `conclusion.verdict` | `reproduced`/`partially_reproduced`/`not_reproduced`/`insufficient_evidence` |

`class` 的口径：论文正文/表格明确给出 → `paper`；只能从代码默认值/配置推断 → `code_inferred`；
两边都没有、由你设定 → `chosen`（后者必须进 `uncertainty`）。

## 7. 证据与定位规范

- 每条结论/数字/参数都要 `quote`（**逐字**）+ `locator`；`check` 会对索引正文做规范化（NFKC、空白折叠、去零宽）逐字查找，找不到即 `evidence_rejected`。
- quote 必须与材料完全一致；**绝不改原文凑通过**。找不到就删掉该 claim 或降级为 `pending_human`。
- 表格数字保留原始表头与单位；不交换列、不补缺失格。
- 近似读数（图像/曲线）标 `approximate: true` 与误差范围。

## 8. 事前容差（本题核心，禁止事后凑）

`init` 在**任何运行之前**写 `/app/work/tolerance_plan.json`：

```json
{"declared_step": "init", "before_any_run": true, "entries":
 {"top1_accuracy": {"abs_tol": 0.0038, "rel_tol": 0.02, "basis": "prior default: rel 2% ..."}}}
```

规则：case 明确给出容差 → 记为 `case_declared`；否则用默认先验
**相对 2% + 绝对 0.5%×报告值**（吸收报告位数与运行波动）。`check` 拒绝任何比计划更宽的容差。

## 9. 差异归因（脚本确定性判定 + Agent 解释）

| cause | 触发条件（脚本） | 含义 |
|---|---|---|
| `none` | 全部观测在容差内 | 无差异 |
| `shared_upstream_factor` | 候选间极差 ≤ 容差，但都偏离报告值 | 共同上游：数据版本/切分、关键参数、环境 |
| `implementation` | 候选间极差 > 容差，且至少一方超差 | 实现细节差异 |
| `unverified_single_implementation` | 仅一份候选产出数值 | 无法区分实现与上游 |
| `paper_value_unavailable` | 材料无报告值 | 无法判定一致性 |
| `parameter_restoration` | 存在 `chosen`/`code_inferred` 参数 | 参数复原不确定性 |
| `environment_underspecified` | 环境快照缺字段 | 跨机重建受限 |

Agent 可在 `draft.attribution` 追加条目；脚本保留并在 `reproduction.md` 中并列，冲突进 `uncertainty`。

## 10. 结论分级

`reproduced`（全部在容差内）/ `partially_reproduced`（部分）/ `not_reproduced`（全部超差）/
`insufficient_evidence`（没跑起来或没有可比报告值）。Agent 结论与脚本判定不一致时，
**保留可复核的脚本判定**并记录 `verdict_conflict`，不覆盖。

## 11. 异常降级表

| 情况 | 处理 | 状态 |
|---|---|---|
| case.json 缺失/损坏 | 空 case 继续，`errors` 记录原因 | `input_error` |
| 材料是图片/扫描页 | 不解析像素，进 `pending_human` | `partial` |
| PDF 无文本层 | 记 `pdf_text:failed`，建议渲染/OCR | `partial` |
| 候选找不到 | 不伪造运行，`pending_human` 要求人工运行并回填 | `insufficient_evidence` |
| 候选报错/超时 | 记 `exit_code`/`error`，保留 `runs/<name>/run.log` | `partial` |
| 候选无指标输出 | 记 `uncertainty`，不猜数值 | `partial` |
| 无工作稿 | 最小确定性交付（材料/环境/容差/真实运行/对比） | `partial` |
| 容差被放宽 | `check` 报错；`build` 以 `tolerance_widened_after_run` 记录 | `partial` |

## 12. 预算与断点

平台预算 64 次模型请求 / 900 秒 / 单次 16384 tokens。脚本内部软截止 780 秒：
`init` 与 `build` 都在开头先写一份合法 partial `result.json`；剩余时间 < 60 秒时跳过未跑的候选并记
`run_skipped_deadline`。任何未捕获异常都会兜底写出 partial 结果，进程退出码 0。

## 13. 自检清单

- [ ] `result.json` 含 `output_contract` 全部字段 + 9 个必备字段，`case_id` 与输入一致
- [ ] `check` 为 PASS（或所有 ERROR 都写进 `pending_human`）
- [ ] 容差表 `before_any_run=true`，且无条目被放宽
- [ ] 每个指标都有 `observed`/`reported`/容差/判定，或明确 `no_reported_value`
- [ ] `reproduction.md` 十节齐全，run 段含命令、退出码、耗时
- [ ] 状态与结论一致：没跑起来不得写 `reproduced`
- [ ] 编码 UTF-8 无 BOM；无 `__pycache__`/`.pyc`

## 14. 最小调用示例（示例，非正式案例结果）

输入：`/input/case.json`（`case_id=demo-001`，契约含 `reproduction_record`、`comparison_table`），
材料 `paper.md` 与 `impl/candidate_a.py`、`impl/candidate_b.py`。

```bash
python3 -B "$SK/scripts/main.py" init
# → 3 materials / 5 units；tolerance: top1_accuracy abs=0.003825 rel=0.02 (before_any_run=True)
python3 -B "$SK/scripts/main.py" show --id paper --grep "Top-1"
# → paper:§4.1 Main results/p1 | ... Top-1 accuracy 76.5% and macro F1 0.741 ...
# 写 draft.json 后：
python3 -B "$SK/scripts/main.py" check   # → PASS claims=2 ok=2 rejected=0 params=4 tol=2 widened=0
python3 -B "$SK/scripts/main.py" build   # → runs 2 (ok 2); rows 4 in=4 out=0; verdict reproduced
```

示意输出（**示例，非正式结果**）：

| run | metric | observed | reported | rel_dev | verdict |
|---|---|---|---|---|---|
| candidate_a | top1_accuracy | 0.766 | 0.765 | 0.0013 | in_tolerance |
| candidate_b | top1_accuracy | 0.7605 | 0.765 | 0.0059 | in_tolerance |

## 15. 文件清单与维护

```
SKILL.md                       本文件：契约、流程、规则、自检
scripts/main.py                init | show | check | build
scripts/verify.py              抽取/证据匹配/容差比较/契约回填（含 --selftest）
references/draft_schema.md     draft.json 字段与填写示范
references/repro_rules.md      容差先验、归因判定、结论分级、复核步骤
```

变更时同步三处：脚本行为 → §5/§11；字段 → §4/§6 与 `draft_schema.md`；判定规则 → §8~§10 与 `repro_rules.md`。
`python3 -B scripts/verify.py --selftest` 应输出 `PASS`。
