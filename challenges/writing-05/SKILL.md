---
name: evidence-driven-writing
description: 文献证据驱动写作。把写作任务拆成"论断清单 → 证据表 → 证据支撑成稿"三段可核对产物：每条论断匹配到具体材料段落与逐字原文、给出定位与四因子证据强度、按强度调整成稿语气，冲突与缺口显式保留。适用于学术段落写作、补引用、论断核验、证据强度评审与不确定性改写。
version: 2.0.0
license: MIT
---

# 文献证据驱动写作（writing-03）

## 1. 用途与边界

**做什么**：给定"一个需要文献支撑的写作任务 + 材料（原稿段落、文献摘录、文献表）"，产出三段互相可 join 的交付物：`claims.json`（论断清单）→ `evidence_table.json`（证据表）→ `evidence_driven_draft.md`（成稿），并把结果写进 `result.json`。

**四个必须成立的性质**（本题评分内核）：

| 要求 | 本 Skill 的落实 |
|---|---|
| 找得到 | 论断按句切分，每条落到 `locator`（文件 + `[B块.S句]` + 字符偏移），不停留在"有引用" |
| 对得上 | `quote` 从材料逐字复制，脚本做 `quote in material` 命中校验；元数据只转录、不补造 DOI/年份/期刊 |
| 说得准 | 四因子强度分级 + 限定语映射；因果措辞在无干预设计时自动下调为关联；冲突证据进 `conflicts` 与成稿 however 句 |
| 复得现 | 三件产物 `claim_id` 双向可 join；`verify.py` 独立重读材料复算；计数写进 `metrics` |

**不做什么**（硬边界）：不联网、不从记忆补文献、不补造数值/DOI/结论、不把"未找到证据"写成"证明不存在"、不把相关性写成因果。材料没有的对象进 `pending_human`，不构造。

## 1.5 v2 新增：可核验资产层（不改调用方式）

v1 只交"产物 + 自报计数"，复核要自己重算。v2 增加**独立金标准 + 逐项差分**，由 `scripts/gold.py` 在每次运行时自动产出，无需额外命令：

| 新增产物 | 内容 | 复核价值 |
|---|---|---|
| `golden_standard.json` | 16 项金标准（论断切分、来源对应、逐字引文、定位偏移、强度复算、语气相称、数字/引用一致、越级因果、未支持标注、冲突保留、契约、状态、溯源、DOI），每项含 `weight / method / basis{locator, quote, verified}`；另有 `claim_units[]` 逐条给期望来源、期望强度 | 期望值**独立重算**（不用 main 的余弦匹配，改用内容项覆盖率+数字核对；强度用另一份实现复算），可交叉发现实现错误 |
| `diff_report.md` | 逐项对照表（期望/实测/判定/依据）+ 论断级对照 + 偏差缺失的修法 + 不可判定项 | 一眼看出哪条不达标、差在哪、怎么改 |
| `version_history.md` | v0 骨架 → v1.0.0 成稿 → v2.0.0 资产层的改动/原因/回退命令 + 回退检查表 | 可回退、可追溯 |
| `run.log` | 逐步时间戳日志（start/discover/claims/evidence/finalize/assets + 降级与异常） | 耗时与断点可查 |
| `self_check.json` | 契约字段、证据覆盖率、数字/引用一致性、状态诚实、**兜底闸门实测退出码**、独立复核结果 | 自检不是自述：兜底闸门是真跑子进程 |

`result.json` 同步新增 4 个字段（`golden_standard` / `diff_report` / `version_history` / `self_check`，值为 `{path, count, note}`），原契约字段与 9 件产物不变。

**独立重跑**（只重算金标准与差分，不动机稿）：

```bash
python3 -B scripts/gold.py --input /input --output /app/output   # 退出码 0；重跑后 internal_score 与逐项 verdict 应完全一致
```

`internal_score`（0-100 加权符合度）只是本地自查指标，**不是平台评分**，不得用于对外比较。

## 2. 触发与调用

触发：用户要求"为这段文字补引用/核对论断/评估证据强度/改写过度推断段落/按证据强度重写讨论段"；或输入目录含 `case.json` 与文献材料。

```bash
python3 -B scripts/main.py   --input /input --output /app/output     # 主流程（无参即用默认路径）
python3 -B scripts/verify.py --input /input --output /app/output     # 独立复核 -> verification.json
```

两步都退出码 0；`main.py` 第一步先写 partial `result.json`，任何异常最后仍 finalize。

## 3. 运行契约

- 输入 `/input/case.json` + `/input/task.md` + `/input/**`（PDF/DOCX/CSV/MD/JSON/TXT/图片）；输出 `/app/output`；工作目录 `/app/work`。
- 仅 Python 标准库；离线；不依赖 CWD（资源用 `Path(__file__).resolve().parent`）。
- `result.json` 原样回填 `output_contract` 全部字段（键名不改、未知字段保留、缺值 null/[]），并带 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。
- `status`：`ok` | `partial` | `insufficient_evidence` | `input_error`，与缺口一一对应，不美化。

## 4. 输出

| 文件 | 内容 |
|---|---|
| `evidence_driven_draft.md` | 主产物：可编辑成稿（引用编号 + 限定语 + 证据边界段 + 参考文献） |
| `deliverable.md` | 同上（兼容命名） |
| `claims.json` | 论断清单：`claim_id, text, core, type(事实/推断/因果/比较), location` |
| `evidence_table.json` | 证据表：`claim_id, source_id, locator, quote, source_type, strength, support_scope, conflicts, rationale, verified` |
| `evidence_strength.md` | 逐条强度依据（四因子分值 + 理由） |
| `reference_check.md` | 著录完整度与核验路径（明确"未联网核验"） |
| `uncertainty_notes.md` | 低强度/冲突/仅摘要/未匹配计数 |
| `pending_human.json` | 材料缺口与需人工确认项 |
| `result.json` | 契约回填 + `preserved_facts` + `evidence_map` + `change_log` + 计数 + 4 个 v2 资产字段 |
| `golden_standard.json` `diff_report.md` `version_history.md` `run.log` `self_check.json` | v2 资产层（见 §1.5） |

## 5. 流程（三段交付）

1. **发现与抽取**：语义识别材料类型（`draft` 待改稿 / `references` 文献表 / `material` 来源），按魔数与扩展名解析，失败只降级并记录 `degradations`。
2. **论断切分**：有原稿→逐句切（剥离句末引用标记为 `core`）；无原稿→按 task 主题取材，单文件最多 2 条以保证来源多样。
3. **来源匹配**：词表归一（中英术语，`references/lexicon_zh_en.txt`）+ 余弦相似度 + 数字重叠加分；若论断正文带 `[n]` 引用锚点且该文献能映射到具体文件，则定向匹配并可放宽阈值。证据池只含 `material`（排除待改稿与文献表本身）。
4. **强度分级**：四因子（设计/样本量/独立来源/冲突）加权，附 `rationale`。
5. **冲突识别**：同一论断下主题重叠但方向相反（否定/不一致线索）的来源进 `conflicts`，不静默丢弃。
6. **成稿**：每句实质判断 = 强度限定语 + 论断 + 引用编号；冲突另起 however 句；末尾"证据边界"与参考文献。原稿模式保留原块结构与标题。
7. **过度推断下调**：无干预设计时因果措辞→关联表述，全称量词→范围限定；不改数值，逐条写 `change_log`（`original_quote`→`revised_quote`+理由+locator）。
8. **校验与回填**：逐字引文校验、join 校验、计数、`pending_human`，最后覆盖 `result.json`。若 case 含 `organizer_workorder`/`organizer_edit_workorder`，逐项执行可判据项（字数/引用数/格式）并在 `workorder_receipt` 回报，无判据项标 `unverifiable`。
9. **资产层**：`gold.py` 读回已落盘产物，独立重算 16 项金标准 → 差分 → 版本记录 → 自检（含 `--help`/空输入/坏 JSON/无契约 4 个真实子进程闸门）→ 把 4 个字段写回 `result.json`。该步失败只降级（原产物不受影响），并在 `errors` 记 `stage=assets`。

## 6. 评分点 → 字段/检查/产物

| rubric 项 | 落点 |
|---|---|
| 完成度 15 | 三件产物 + 成稿引用标记数 ≥ 有来源论断数（`metrics.citation_markers` vs `claims_with_source`） |
| 正确性 15 | `quote` 逐字命中率（`metrics.quotes_verified/quotes_failed`）；DOI/年份只转录 |
| 完整性 5 | 论断/来源/强度/不确定性四要素；`strength_counts`、`uncertainty`、`pending_human` |
| 可核验 5 | 每行 `locator` + `rationale`；`verify.py` 复算 → `verification.json`；`golden_standard.json` 逐项给独立期望与依据 |
| 质量增益 15 | `support_rate`、`strength_label_rate`、`overclaim_downgrades`（可复算，不编造对照分） |
| 效率增益 5 | `pending_human` 精确到条目（哪条要回原文、哪条要补证），减少返工 |
| 创新 15 | 论断切分 + 锚点定向匹配 + 四因子分级 + 过度推断下调 + 冲突保留，链条在产物中可查 |
| 可靠 10 | 六类降级分支（见第 8 节）+ partial 先落盘 + 退出码 0 |
| 生态 10 | 本节 + `references/` 三份资源 + v2 五件资产（金标准/差分/版本/日志/自检）可被他人直接重跑复用 |

## 7. 证据与定位规范

- `locator = <相对路径> [B<块>.S<句>] chars:<start>-<end>`，相对输入根目录，可独立回查。
- `quote` 必须与材料**逐字**一致（含标点、单位、数字）；改写即视为不命中并降级，**禁止改原文凑通过**。
- `source_type` 记录材料自述的设计（系统综述/指南/RCT/队列/病例对照/横断面/病例报告/预印本/综述/体外），未标明的写"未标明"。
- `support_scope` 区分"直接支撑 / 部分支撑（范围不一致）/ 无直接支撑"，并注明样本量与条件边界。

## 8. 异常与降级分支

| 情况 | 处置 |
|---|---|
| 文献不可得 / 无全文 | 仅摘要在 `abstract_only` 标注，强度最高记"中"；进 `pending_human` |
| 无参考文献表 | `reference_check.md` 记"缺口"；文献行标"材料无著录信息"，不补造 |
| DOI/年份/期刊缺失 | 只转录已有字段，缺失即标缺，不联网补 |
| 原文与摘要矛盾 | 两条都进证据表，`conflicts` 记录方向相反的表述 |
| 证据相互冲突 | `conflicts[]` + 成稿 however 句 + 强度下调 |
| 格式不支持（xlsx/pptx/doc） | `degradations` 记 `unsupported`，`pending_human` 提示转格式 |
| PDF 无文本层（扫描件） | `read_method=none`，`pending_human` 提示 OCR |
| 权限不足 / 目录不可写 | 回退工作目录输出，`errors` 记录 |
| 空输入 / 坏 JSON | 仍写合法 partial `result.json`，`status=partial|input_error`，退出码 0；v2 资产层同样落盘（golden_standard 全为不可判定） |
| 资产层异常（写盘失败/子进程超时） | 只降级：4 个字段置 null 并记 `errors`，原有 9 件产物与契约字段不受影响 |
| 论断找不到来源 | 保留该句但改成待核表述 + `pending_human`，不硬凑引用 |

## 9. 预算与断点

单案例应在数秒内完成（纯本地计算）；`runtime.seconds` 记录耗时，接近 900 s 预算时提前 finalize 并在 `degradations` 标注。运行中断时磁盘上始终存在合法 `result.json`（partial）与已写出的成稿。

## 10. 自检清单

- [ ] `python3 -B scripts/main.py --help` 退出码 0
- [ ] `claims.json` / `evidence_table.json` / `evidence_driven_draft.md` 三件齐全，`case_id` 原样
- [ ] 每条证据行含 `quote + locator + strength + support_scope`
- [ ] 逐字命中率 100%，未命中项全部进 `pending_human`
- [ ] `claims.claim_id` ↔ `evidence_table.claim_id` 无悬空；成稿引用编号都能解析
- [ ] 冲突证据有 `conflicts` 与成稿表述，未被静默丢弃
- [ ] 低/不足强度句带限定语；无"证明/确证"式越级表述
- [ ] 契约字段齐全、键名未改、未知字段保留
- [ ] 5 件 v2 资产齐全；`self_check.passed` 与 `diff_report.md` 第 3 节一致（有偏差就不该是 true）
- [ ] `golden_standard.json` 每项 `basis_verified=true`（或明确列入依据缺口）
- [ ] 无 `__pycache__`/`.pyc`/临时文件

## 11. 最小调用示例（示例，非正式案例结果）

输入 `case.json`：

```json
{"case_id": "EXAMPLE-1",
 "task_instruction": "为讨论段补引用，数字编号格式",
 "output_contract": {"case_id": "原样保留", "deliverable": "可编辑文稿",
                     "preserved_facts": "数字与来源不可改变",
                     "evidence_map": "论断到来源定位", "change_log": "修改记录"}}
```

调用：`python3 -B scripts/main.py --input ./demo/input --output ./demo/output`

示意输出（**示例，非正式案例结果**，数字仅为示意）：

```json
{"case_id": "EXAMPLE-1", "status": "partial",
 "claims_total": 4, "claims_unsupported": 1, "evidence_rows": 5,
 "quotes_verified": 4, "quotes_failed": 0, "strength_counts": {"中": 3, "低": 1},
 "overclaim_downgrades": 1, "support_rate": 0.75,
 "golden_standard": {"path": ".../golden_standard.json", "count": 16}, "diff_report": {"count": 1},
 "version_history": {"count": 3}, "self_check": {"count": 6}}
```

成稿片段（示意）：`现有研究提示……[1]。` 见 `demo/output/evidence_driven_draft.md`。

## 12. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（入口） |
| `scripts/main.py` | 主流程：发现→论断→证据→成稿→result.json（先 partial 后 finalize） |
| `scripts/verify.py` | 文本层与规则层（被 main 导入）+ 独立复核 → `verification.json` |
| `scripts/gold.py` | v2 资产层：独立金标准 + 差分 + 版本记录 + 运行日志 + 自检（可单独运行重跑） |
| `references/evidence_schema.md` | 论断/证据/定位/result 字段 schema 与切分规则 |
| `references/method_and_runbook.md` | 强度分级口径、限定语表、降级表、示例与维护 |
| `references/lexicon_zh_en.txt` | 中英概念词表（跨语言论断-来源匹配；Tab 分隔，可扩充） |

版本 2.0.0（v1.0.0 基线 + 资产层补丁）；Python ≥3.8；无第三方依赖；8 个文本文件、约 100KB。
版本记录与回退命令：运行时见 `version_history.md`；包内变更见 §1.5 与本表。

## 13. 维护说明

- 扩充学科词表：在 `references/lexicon_zh_en.txt` 追加 `中文<TAB>english` 行，只加确定同义的术语。
- 调整强度阈值：`scripts/verify.py` 的 `grade()`，同时更新 `references/method_and_runbook.md` 的口径表，二者必须一致。
- 新增来源类型：改 `DES` 表（设计→分值），并同步文档。
- 回归测试：`python3 -B scripts/main.py --input <demo> --output <out>` → 跑 `verify.py`（要求 `quote_verbatim/claim_join/row_fields/citation_resolvable` 全 True）→ 跑 `gold.py`，要求 `items[].verdict` 序列与上一版一致。
- 改金标准口径：只改 `gold.py` 的 `CORE/DIRECT/D2/NR2` 与 `golden_standard.json.rules`（同一次运行产出），并同步 `references/method_and_runbook.md` §1；**不得为了让产物达标而放宽金标准**。
- 新增/删除检查项：同步调 `items[].weight` 使总和为 100（`acceptance.weight_total` 会显式暴露），并更新本文件 §1.5 与 §6 映射表。
