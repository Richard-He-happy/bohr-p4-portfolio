---
name: academic-translation-bilingual
description: 学术翻译与双语写作 Skill。Agent 先逐段精读原文，再亲手写出逐段译文工作稿（workdraft.json），脚本负责材料抽取、句段对齐校验、术语/数字/引用核对、成稿拼装，并生成可核验资产（golden_standard.json 金标准、diff_report.md 产物对照、version_history.md 版本与回退、run.log 运行日志、self_check.json 自检）；用于论文摘要、正文、图表题注、参考文献的中英互译与双语对照交付，产出双语稿、术语表、逐段对齐表、事实与证据映射、修改记录和 result.json。材料缺失或术语无法确定时明确标注并降级为 partial。
version: 1.4.0
---

# 学术翻译与双语写作（Agent 主答 + 脚本辅助）

## 1. 用途与边界
把给定科研材料（中文或英文摘要、正文、图表题注、公式段、参考文献）译成目标语言，并交付**可直接进入作者修改流程**的双语稿：逐段对齐、术语全篇统一、数字/单位/引用编号逐字保留、每段可回溯原文。
适用：摘要/正文/题注/脚注/参考文献的中英互译、双语对照改稿、术语表建设、译后一致性核查。
不适用：无原文的创作型写作、需要外部文献补写结论、图像内文字识别（图像只登记为缺口，交人工）。
**硬边界**：不增删事实，不改科学判断，不补材料里没有的数值、文献或结论；拿不准就写进 `pending_human`。

## 2. 运行契约
- 输入：`/input/case.json`（含 `task_instruction`、`output_contract` 等，键名不固定）+ `/input/**` 材料；可能另有 `/input/task.md`。
- 工作目录 `/app/work`，产物 `/app/output`，其中必须有 `result.json`。
- 只用 Python 标准库，不联网（Python 3.8+）；路径默认 `/input`、`/app/work`、`/app/output`，也可用 `--input/--work/--output` 覆盖；脚本按自身位置定位，不依赖 CWD。
- 退出码恒为 0；任何异常都写进 `result.json.errors`，不中断。
- 预算：64 次模型请求 / 900 秒。做法是**先落盘再优化**：init 已写好合法 partial `result.json`，接近 780 秒立刻执行 build 收尾。

## 3. 输入发现（不假设键名）
1. 递归读 `/input`：`case.json`/`input.json`/`task.json`/`case*.json`，一律按 `utf-8-sig` 起的多编码尝试读取（防 BOM）。
2. 语义识别字段：`task_instruction|brief|request|workorder|prompt` 为任务说明；`output_contract` 为输出契约（**原样回填**）；`organizer_*`、`formal_inputs`、`artifacts`、`materials` 为材料清单；`glossary|locked_terms|terminology` 为给定术语（优先锁定）。
3. 材料按扩展名 + 魔数识别：PDF（`%PDF`，脚本用 zlib 解内容流取文本层）、DOCX（`word/document.xml`）、HTML、Markdown/TXT/TeX/CSV/JSON。扫描件或 CID 编码 PDF 取不到字时，quality 标 `low/unreadable`，写入 `degradations` 与 `pending_human`，**绝不凭标签猜正文**。
4. 材料没给的对象（图表、缺失页、附录）明确列缺口，不构造。

## 4. 四步工作流（必须按序，Agent 主答）
技能根目录记为 `$SKILL`（本文件所在目录）。命令示例：

```bash
python3 "$SKILL/scripts/main.py" init     # 1) 建索引 + 先写 partial result.json
python3 "$SKILL/scripts/main.py" show --para M1-P001 --para M1-P002
python3 "$SKILL/scripts/main.py" check    # 3) 校验工作稿
python3 "$SKILL/scripts/main.py" build    # 4) 成稿 + finalize result.json
```

每次子命令都会向 `work/run.log` 追加一行（阶段、事件、耗时）；`build` 把它整理成交付用 `run.log`。

**第 1 步 init**：输出材料表、段落数、契约字段名、术语（含给定术语与缩写候选）。同时写 `work/index.json`（每段 `para_id`、`locator`、`kind`、逐字 `text`）与 `work/workdraft.template.json`（空译文骨架）。

**第 2 步 读原文并亲手写译文**（这一步是本 Skill 的核心，不可跳过）：
- 用 `show --para ...`、`show --material M1`、`show --grep 术语` 或直接打开材料文件，**逐段读原文**。
- 在 `work/workdraft.json` 写下**逐段译文**：每段一条，`para_id` 照抄索引，`translation` 是你撰写的译文，`source_quote` 取该段一小段逐字原文（校验用，必须能在原文中找到）。
- 同步写 `glossary`：从原文抽出的术语 → 译名 + `locator`（出处）。同一术语全篇只用一个译名；同一英文词在不同学科译法不同时，按本材料的学科语境定一次并全篇沿用，在 `note` 写依据。
- 图注、表题、脚注、参考文献条目同样逐段译：编号（`Fig. 3`/`图 3`/`Table 2`/`[12]`）与条目文字原位保留，不改写作者名、期刊名、卷页年。
- 修改变动写进 `change_log`（原文 → 译文 + 理由 + locator）。

**第 3 步 check**：确定性校验（下一节）。`verdict: pass` 才进入 build；`fail` 就按报告逐条修稿再 check。**不要为了通过校验改原文**：原文不符就修译文或把该段列入 `pending_human`。

**第 4 步 build**：拼装最终产物并无条件 finalize `result.json`（工作稿缺失/不全时用确定性兜底，`status=partial` 并记录缺口）。

## 5. 工作稿格式（`work/workdraft.json`）
```json
{
  "case_id": "照抄输入",
  "target_lang": "en 或 zh",
  "glossary": [{"term": "光催化", "target": "photocatalysis", "locator": "M1:paper.md#P002", "note": "学科语境依据"}],
  "paragraphs": [
    {"para_id": "M1-P002", "source_quote": "该段开头若干字逐字原文",
     "translation": "整段译文", "note": "处理说明，可空"}
  ],
  "change_log": [
    {"para_id": "M1-P002", "action": "translate", "original_quote": "原文片段",
     "revised_quote": "译文片段", "reason": "术语锁定/数字保留", "locator": "M1:paper.md#P002"}
  ]
}
```
也可拆到 `work/draft*.json`：脚本按 `paragraphs` 非空自动识别（模板文件不会被误用）。

## 6. 校验口径（check 报什么就改什么）
| 检查 | 判据 | 不合格处置 |
|---|---|---|
| 覆盖 | 索引中每个 `para_id` 都有非空译文，覆盖率 100% | 补译漏段 |
| 引文 | `source_quote` 归一化空白后必须是原文子串 | 改引文或改译文，**不改原文** |
| 数字 | 原文每个数字串（含小数、千分位、百分号、`n = 3`、`95% CI`）都要出现在译文中 | 原样落地；`万/亿`↔`million/billion` 换算须在 `note` 说明并保留原数值 |
| 单位 | 原文单位（mg/L、°C、min、kPa…）在译文中出现 | 补回单位，不做单位换算 |
| 引用 | `[12]`、`[3,4]`、`(Zhang, 2019)` 等标记原样保留 | 补回标记；作者—年份体例差异只改格式不改编号 |
| 术语 | 术语表中每个术语在其出现段落里用同一译名（容忍英文词形变化） | 统一译名；确需变体则改术语表并说明 |

## 7. 产物与 result.json
`build` 在 `/app/output` 写出：
- `translation.md`：双语逐段对照（每段 `Source` 逐字原文 + `Target` 译文 + `para_id`/`locator`），开头是锁定的术语表；可选 `--deliverable-name` 改名。
- `glossary.csv`：`term,target,locator,note,status`（`status=locked` 或 `pending_human`）。
- `alignment.csv`：`para_id,material,locator,kind,source,target,aligned,numbers_missing,terms`。
- `preserved_facts.json`：每个数字/引用 → `present_in_target` 布尔 + 原文片段 + locator。
- `evidence_map.json`：每段 → 逐字原文、译文、涉及术语、推导说明。
- `change_log.json`：Agent 的修改记录 + 脚本兜底动作（`actor=agent|script`）。
- - `result.json`：`output_contract` 每个字段原样回填（按语义映射到上述文件，缺失填 `null`/`[]`，**不改名、不删未知字段**），并含 `case_id`、`status`（`ok|partial|insufficient_evidence|input_error`）、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`metrics`、`runtime`。

### 7.1 可核验资产（`build` 自动生成，`audit` 可重算）

| 文件 | 内容 | 复核口径 |
|---|---|---|
| `golden_standard.json` | 本题金标准：逐段译文要求（`para_id`+`locator`+逐字 `source_quote`）、术语（term→target，`locked`/`pending_human`）、数字/单位/引用清单、证据映射要求、元检查 | 每项带 `req_id`+`locator`+逐字 quote；只由索引/契约/给定术语派生，**不含预制译文** |
| `diff_report.md` | 实际产物 vs 金标准逐项对照：`ok`/`missing`/`deviated`/`na`、分类达标率、待处置明细 | 逐项比对**落盘产物**，不引用内存中间态；判 `pass` 才等于全覆盖 |
| `version_history.md` | Skill 版本线（1.3.0→1.4.0）+ 产物 v0 骨架→v1 成稿（改了什么/为什么/如何回退）+ 产物 sha256 | 回退命令可直接执行 |
| `run.log` | 运行日志：`init/show/check/build/audit` 的时间戳、耗时、降级、异常 | 执行时逐事件追加，不做事后补写 |
| `self_check.json` | 自检：契约完整性、逐段覆盖、数字/引用/术语、证据逐字性、空输入与坏 JSON 兜底（真实子进程）、退出码 | `verdict=pass` 表示可机械核验项全通过；`limits` 写明未覆盖维度 |

`result.json` 另含四个字段指向这些资产：`golden_standard`（含 `requirements` 计数与 `sha256`）、`diff_report`（`ok/total/missing/deviated/match_ratio/verdict`）、`version_history`（`versions/current/rollback/deliverable_sha256`）、`self_check`（`checks/passed/failed/verdict/smoke`）。字段名与契约同义时按契约字段名回填同一文件路径。

## 8. 事实、数字与语义边界
- 数字、单位、量级、年份、样本量、统计口径逐字落地；不改写为整数、不四舍五入、不换单位。
- 否定范围（`not … because`）、限定条件（`under N2, at 25 °C`）、因果强度（`suggests/indicates/demonstrates`）、模糊限制语（`may/might/likely`）保持同等强度；`suggests` 不许译成“证明”。
- 增译只为可读性（补主语、连接词），不得引入新事实；省译只限重复虚词，不得省掉限定条件。
- 公式、上下标、希腊字母、基因/材料专名（`TiO2`、`·OH`、`p = 0.03`）逐字保留。
- 引用与归属完整：`et al.`、上标、方括号体例按目标语言习惯调整格式，编号与作者年份不变。

## 9. 冲突与人工确认（写进 `pending_human`）
- 术语无公认译名、或同一词在本材料语境出现两种合理译法 → 择一并标注待确认，不静默切换。
- 原文歧义、跨段指代不明、原文自身数字/单位冲突 → 保留原文数值并标注冲突，不擅自裁决。
- 材料缺页、图像文字、扫描 PDF 取字失败、表格结构损坏 → 标注 `quality=low/unreadable` 的段落与缺口范围。
- 需要外部文献才能确定的结论 → 不补写，列为待确认。

## 10. 异常与降级分支
| 情况 | 行为 | 结果状态 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 递归找 `case*.json`/`task.md` 继续；契约缺字段填 `null` | `partial` / `input_error` |
| 材料为非文本（图像/PPT/压缩包） | 登记名称与 note，提示人工读取，不猜内容 | `partial` + `pending_human` |
| PDF 文本层稀薄 | 保留可取文本，标 `quality=low`，提示对照页面核对 | `partial` + `degradations` |
| 无工作稿 / 工作稿不全 | 确定性兜底：完整双语骨架 + 空译文槽标记 `[待译 / PENDING TRANSLATION]` | `partial` |
| 无任何可读材料 | 不造内容，写空 `sources` 与错误说明 | `insufficient_evidence` |
| 单个文件解析失败 | 只降级该文件，其余照常 | 视覆盖情况 `ok|partial` |
| 金标准生成失败 | 主产物照常交付，`diff_report` 退化为文件级检查 | `partial` + `degradations` |
| `diff`/`self_check` 生成异常 | 写降级版报告并记录 `errors`，不中断 | `partial` + `errors` |
| `audit` 时无既有 `result.json` | 造 partial 壳后重算资产，不改主产物 | `partial` |

## 11. 自检清单（交付前）
1. `result.json` 存在且合法，`output_contract` 字段全部出现；`case_id` 与输入一致。
2. `translation.md` 段数 = 索引段数；每段有 `para_id` 与 `locator`；空译文槽为 0。
3. `alignment.csv` 的 `aligned` 全为 `yes`；`numbers_missing` 为空。
4. `glossary.csv` 无 `target` 为空的行（有则必须出现在 `pending_human`）。
5. `preserved_facts.json` 无 `present_in_target=false`（有则说明并列入 `pending_human`）。
6. `status` 与实际情况一致；`errors`/`degradations`/`pending_human` 不为凑数而空。
7. `diff_report.md` 无 `missing`/`deviated`；若有，每项都给处置或进 `pending_human`。
8. `self_check.json` `verdict=pass`；SC09/SC10 是真实子进程结果，不是声明。
9. 五个可核验资产都在 `/app/output` 且非空；`run.log` 含本次 `init/check/build` 记录。

## 12. 最小调用示例（示例，非正式案例结果）
```bash
$ python3 scripts/main.py init --input ./input --work ./work --output ./out
case_id: EXAMPLE-NOT-A-TEST-CASE
  M1  abstract.md   kind=text  quality=ok  chars=390  paras=6
paragraphs: 6 | contract fields: deliverable, glossary, alignment_table, ... | supplied terms: 1

$ python3 scripts/main.py show --para M1-P002
[M1-P002] M1:abstract.md#P002 (body, 140 chars)
本研究考察了 TiO2 光催化降解苯酚的动力学行为。……      # Agent 逐段读原文并写 work/workdraft.json

$ python3 scripts/main.py check
verdict: pass | coverage 6/6 (1.0)

$ python3 scripts/main.py build
status: ok | paragraphs: 6 | translated: 6 | glossary: 5 | verdict: pass
diff: pass 41/41 | self_check: pass
result: out/result.json

$ python3 scripts/main.py audit          # 可选：不重写主产物，只重算 5 个可核验资产
audit: status ok | golden 42 reqs | diff pass 41/41 | self_check pass
```
示意输出为**示例**，仅说明接口与流程，不是任何正式案例结果。

## 13. 文件清单与版本
```
SKILL.md                          本文件（用途/契约/流程/口径/降级/自检）
scripts/main.py   (≈28KB)         子命令 init/show/check/build(+audit)；md+csv+json 成稿；兜底与 finalize
scripts/kit.py    (≈21KB)         材料抽取(pdf/docx/html/text)、索引、工作稿校验、结果装配
scripts/audit.py  (≈25KB)        金标准派生 + 逐项比对 + 自检取证（golden/compare/selfcheck）
scripts/reports.py (≈14KB)       报告渲染：diff_report / version_history / run.log / 自检落盘
references/workdraft_schema.md    工作稿字段、校验规则与排错
references/verifiability.md       五个可核验资产的 schema、判读与人工复核步骤
references/quality_rules.md       术语/数字/引用/语域处理细则与判定示例
```
版本 1.4.0；仅标准库（Python 3.8+）；无外部依赖、无需安装，单次运行数秒（自检子进程另计约 2s）。

## 14. 维护说明
- 题型变化：新增材料类型时只扩展 `kit.extract()`，其余流程不变。
- 校验口径变化：只改 `kit.validate()`，输出契约由 `result.json` 的 `output_contract` 自动跟随。
- 复用：`kit` 的段落索引、逐字引文核对、数字/引用比对可直接用于校对、审稿回复等写作任务。
- 核验口径变化：只改 `audit.compare()`；报告样式只改 `reports.py`，两者互不影响。
- `audit.py` 可单独复用：`golden()`/`compare()` 的 req_id+locator+逐字 quote 结构同样适用于校对、审稿回复、译文验收等需要「可逐条复核」的写作任务。
- 回退到 1.3.0：删除 `scripts/audit.py`、`scripts/reports.py`、`references/verifiability.md`，还原 `main.py`/`kit.py`/本文件即可；原四个子命令的调用方式与产物不变。
