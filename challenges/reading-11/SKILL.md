---
name: sci-reading-bench
description: 把输入科研材料现场做成"可判分"的文献阅读题集与评测工具包：Agent 亲自出题与写评分锚点，脚本负责材料索引、逐字证据核验、0/1/2 评分、报告与 result.json 契约回填。适用于文献阅读 benchmark 建设、题集质量自检、评分可复核性核查。
version: 1.5.0
---

# 文献阅读 Benchmark 与评测工具（Agent 主导 + 脚本辅助）

## 1. 用途与边界

**做**：读 `/input` 的材料 → 现场出题（题目 / rubric 点 / 参考答案 / 逐字证据锚点）→ 校验 → 生成 `benchmark.json`、`anchors.json`、`scoring.json`、`report.md`、`result.json` 五件产物，形成"题目—锚点—评分—报告"闭环。

**不做**：不替被评测 Agent 答题；不编造分数；不把材料外的知识当证据；checker 日志/合成数据不当成官方分数。

**适用**：单篇或多篇论文、报告、表格、DOCX/PDF/TXT 材料的阅读题集建设；任意语言的评分点（脚本对中文按 4 字滑窗、英文按词做关键词覆盖）。
**不适用**：需要图像 OCR 的纯图片材料（脚本仅登记缺口，由你人工/平台工具补读）；需要运行代码复现实验的任务。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（可缺）+ `/input/**` 材料；也接受 `case*.json` |
| 工作目录 | `/app/work`（索引、草稿、check_report.json） |
| 产物 | `/app/output/`：`benchmark.json` `anchors.json` `scoring.json` `report.md` `result.json` |
| 入口 | `python3 -B scripts/main.py {init|show|check|build}`；`scripts/bench.py` 为库，也可 `--help` |
| 退出码 | **恒为 0**（异常写进 result.json 的 `errors`，不是靠非零码报错） |
| 依赖 | Python 3 标准库；不联网；不依赖当前工作目录（路径用 `Path(__file__)` 推导） |
| 预算 | 64 次模型请求 / 900 秒；每步都可中断，`init` 已先落盘合法 partial `result.json` |

## 3. 输入发现（不要假设键名）

`init` 会：递归扫描 `/input`（跳过隐藏文件、`__pycache__`、根目录的 `case.json`/`task.md`/`result.json`）→ 按扩展名+魔数判定类型（`%PDF`、`PK`）→ 抽取文本 → 按空行切段，给每段一个**稳定 locator** `M01#p7`（M=材料序号，#p=段序号），PDF 额外记页码。

文本处理：JSON 用 `utf-8-sig` 解码（防 BOM），每个材料按 `utf-8-sig → utf-8 → gb18030 → latin-1` 依次尝试，全部失败才 `ignore` 并记降级。

`case.json` 采用语义识别，兼容别名：`case_id/caseId/id`、`output_contract/contract/required_outputs`、`task_instruction/instruction/prompt/task`、`organizer_workorder` 等；**契约字段原样透传**，不改名、不丢字段。

材料解析路径：`.md/.txt/.csv/.tsv/.json/.html/.tex/...` 直读 → `.docx` 走 `word/document.xml` → `.pdf` 依次尝试 `pdftotext`、`PyMuPDF`、`pdfminer`、内置 zlib 流抽取（探测失败才降级）。图片只登记缺口。

## 4. 输出契约（result.json）

固定字段：`case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`outputs`、`benchmark`、`anchors`、`scoring`、`technical_synthetic`。

外加：`output_contract` 里的**每个字段都在顶层出现**（有对应结果就填真实值，没有就 `null`/`[]`/镜像空结构），并保留 `contract_fields_present` 与 `contract_echo` 便于审计。UTF-8 无 BOM。

## 5. 核心流程（必须按序，Agent 是出题人）

1. **`init`**：建索引，打印材料清单与契约字段名，写出 partial `result.json`。看清 `paras`/`chars`/`status`，材料降级会标 `!`。
2. **`show`**：`--material M01 --start 1 --limit 20` 逐段读原文。**你亲自读**，判断哪些段落能出什么题；引文从这里复制，不要手打。
3. **自己写题集草稿** `work/questions.draft.json`（格式见 `references/schema.md`）：
   - 每题：`id`、`type`(extraction|numeric|method|definition|conflict|coverage|table|other)、`difficulty`、`question`、`rubric[]`（每点 `id`/`text`/`weight`/`key_terms`）、`reference_answer[]`、`evidence[]`（`material`+`locator`+`quote`）；
   - 题目要覆盖不同层次：可核对的数值/摘录、方法与条件、机制与主张、材料内冲突或未报告项；
   - 每条 rubric 写出"答到什么算过"的**关键项** `key_terms`（1–5 个短字符串，取原文用词），脚本用它做覆盖度评分；
   - 证据 quote **逐字**复制，locator 写 `M01#p7`（PDF 记页码）。
4. **`check`**：逐条校验结构、quote 是否命中原文、locator 是否与 quote 实际所在段落一致、权重是否合理。按报错改草稿再跑，直到 `RESULT: PASS`（或明确接受剩余错误）。
5. **`build`**：生成五件产物并 finalize `result.json`；末尾打印 `SELF-AUDIT`（契约字段数、计数一致性）。

## 6. 题集质量规则（评分点 → 检查 → 产物）

| 规则 | 脚本动作 | 落点 |
|---|---|---|
| 每题任务/答案/rubric 齐备 | `question`≥10 字符、`rubric`≥1、`reference_answer`≥1、`evidence`≥1 | `check` 报错，缺项题进 `rejected` |
| 引用逐字可核验 | 空白归一后子串匹配（大小写敏感优先） | `anchors.json` 的 `verified`/`match` |
| locator 与引文一致 | 命中位置反推段号，与声明 locator 比对 | `locator_mismatch` 错误 |
| 权重可加 | Σweight≈1.0（±0.02） | `check` warning |
| 不可判的题不混进分数 | 无任何 verified quote → 拒收 | `benchmark.json.rejected` + `pending_human` |

## 7. 证据与定位规范

- locator 唯一格式：`M<材料号>#p<段号>`，如 `M01#p12`；PDF 另带页码字段。
- quote 必须是原文的**连续片段**（允许空白差异），不得拼接、改词、翻译、加省略号。
- 长度 ≥12 字符；一句话最好完整，避免只抄三个词。
- 同一题可以有多条证据，评分取覆盖度最高的那条。
- 找不到引文就改题或降级到 `pending_human`，**绝不改原文凑通过**。

## 8. 评分口径（0/1/2，可复核）

点级：**2** = 原文有逐字锚点且覆盖该点关键项（coverage≥0.6）；**1** = 锚点存在但覆盖不足，需人工复核；**0** = 无可用锚点。

题分 = Σ(weight × 点分)，满分 2；`aggregate` 给 `n1/n2/n0`、`rate2`、`judgeable_rate`、`mean_score`、`n_anchors_verified`。

**这不是被评测 Agent 的答题分，也不是 DSH 分数**：它衡量"这套题能否被判、判分依据是否落在原文上"。`scoring.json` 每题带 `basis` 与 `locator`，任何人重跑 `check` 应得到同一结论。

## 9. 冲突、未报告与人工接管

- 材料之间矛盾：写出两种说法各自 locator，题面要求"指出冲突"，不裁决对错。
- 材料未报告：`reference_answer` 写"材料未报告"，rubric 给"识别为未报告"的分，不补造数字。
- 每条 score<2、每个被拒题、每次解析降级都进 `pending_human`，写清缺什么、下一步做什么。

## 10. 异常降级分支

| 情况 | 行为 | 结果字段 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 继续跑，用目录扫描结果出题 | `errors` + `status=partial` |
| 无材料 | 产物仍生成（空题集） | `status=input_error` |
| 材料无文本（图片/加密 PDF） | 该材料标 `no_text`，其余材料照常 | `degradations` |
| PDF 需 OCR / 字体异常 | 记 `low_text_quality`，提醒用平台工具复核 quote | `degradations` + `uncertainty` |
| 草稿缺失/全部不可核验 | **确定性兜底**：从真实段落生成最小摘录/数值题（1 题/段，最多 6 题），产物不空 | `mode=fallback_minimal` + `status=partial` |
| 部分题被拒 | 其余题正常出包，补 2 道兜底题 | `mode=agent_authored_with_fallback` |
| 输入含 checker/合成数据 | 只登记、不参与评分 | `technical_synthetic.present=true, not_a_dsh_score=true` |
| 任何未捕获异常 | 打印栈、写 partial result.json、退出码 0 | `errors[].traceback` |

## 11. 预算与断点

`init` 一跑就有合法 `result.json`；每步都可中断重跑（`build` 幂等）。接近 780 秒直接 `build`，别为多出两题丢掉整包；材料大时用 `show --start/--limit` 分页读。

## 12. 自检清单（交付前）

- [ ] `python3 -B scripts/main.py --help` 与 `bench.py --help` 均退出 0
- [ ] `/input` 有 case 时 `result.json` 的 `contract_fields_present` 里每个字段都在顶层出现
- [ ] `benchmark.json.items` 非空（或 `status` 明确说明为何为空）
- [ ] 每条 `anchors.json.anchors[].verified` 为 true，或该题在 `rejected`
- [ ] `scoring.json.aggregate.n2+n1+n0 == n_points`
- [ ] `report.md` 有材料表、逐题表、评分汇总、缺口
- [ ] 无 `__pycache__`、无临时文件、无预制正式答案

## 13. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py init          # 索引 + partial result.json
python3 -B scripts/main.py show --material M01 --start 1 --limit 8
#   → [M01#p2] Salinity stress reduced the specific growth rate ... 39 percent ...
#   （把该段原文粘进草稿的 evidence.quote，locator 写 M01#p2）
python3 -B scripts/main.py check         # PASS / 逐条 ERROR
python3 -B scripts/main.py build         # 五件产物 + SELF-AUDIT PASS
```

示意产物（节选，**示例**）：

```json
{"id": "Q01", "type": "numeric", "difficulty": "easy",
 "question": "盐度从 25 升到 45 psu 时比生长速率从多少降到多少？",
 "rubric": [{"id": "R1", "text": "给出两个数值", "weight": 0.6, "key_terms": ["1.42", "0.87"]},
            {"id": "R2", "text": "给出降幅百分比", "weight": 0.4, "key_terms": ["39 percent"]}],
 "reference_answer": ["1.42 d-1 → 0.87 d-1，降幅 39 percent"],
 "evidence": [{"material": "M01", "locator": "M01#p2", "quote": "…from 1.42 d-1 at 25 psu to 0.87 d-1 at 45 psu…"}]}
```

## 14. 文件清单、版本与复用

```
SKILL.md                 本文件：流程、规则、异常分支、自检
scripts/main.py          CLI：init / show / check / build（≤20KB）
scripts/bench.py         库：抽取、索引、核验、校验、result.json 壳（≤20KB）
references/schema.md     草稿 JSON 字段规范 + 示例 + check 规则
references/reuse.md      换新案例 / 扩展题型 / 版本与维护
```

**换新案例**：替换 `/input/case.json` 与材料 → `init` → `show` → 写草稿 → `check` → `build`。命令不变，产物结构不变，旧产物被覆盖（需要留档就先 `cp -r /app/output /app/output.v1`）。
**别人怎么复用**：整套 `submission/` 拷走即可跑；`benchmark.json` 当题集快照，`scoring.json` 做逐题对照，`anchors.json` 做引文抽查表，`report.md` 直接进汇报。改流程要同步改 `scripts/`，改评分口径要升版本并在 `references/reuse.md` 记一条。

版本：1.5.0（Agent 主导出题 + 确定性兜底 + 契约回填 + 自审计）。
