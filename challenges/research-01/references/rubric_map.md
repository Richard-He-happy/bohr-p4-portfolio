# 评分点 → 字段 → 检查 → 产物 对照表

本表把题面 rubric 的每一项落到可检查的字段与文件上，便于评审复核，也便于他人改造后回归自检。
所有检查项都能用 `scripts/main.py --stage check`（输出 `selfcheck.json`）或人工读 `result.json` 复现。

## 1. 实际效果（40 分）

| 评分点 | 对应字段 | 可执行检查 | 产物 |
|---|---|---|---|
| 任务完成度 15 | `sub_questions`、`search_plan`、`synthesis.claims` | 子问题可检索且带 `type/deps`；每条检索式有 `wave/mode/hits`；结论按子问题归类 | `result.json`、`research_report.md` §2–§4 |
| 结果正确性 15 | `citations[].quote/quote_match`、`synthesis.claims[].strength` | 每个 quote 在**重新解析的原文**中逐字命中（`strict` 或 `whitespace_insensitive`）；`strength` 与证据一致 | `evidence_map.csv`、`result.json.verification` |
| 结果完整性 5 | `sub_questions`（7 类）、`gaps`、`conflicts` | scope/evidence_scan/mechanism/quantitative/comparison/conflict/gap 齐备；零命中子问题进 `gaps` | 报告 §2、§5、§6 |
| 结果可核验性 5 | `tool_calls`、`search_plan`、`citations` | 每步工具含 `tool/args/status/elapsed_ms/result`；引用编号与来源一一对应 | `tool_calls.jsonl`、报告 §7 |

## 2. 使用增益（25 分）

| 评分点 | 本 Skill 的做法 | 可对照的度量 |
|---|---|---|
| 质量增益 15 | 固定 7 类子问题模板 + DAG 波次，避免「只把原句改写成关键词」；候选 quote 由程序预校验，结论必须回链 | `coverage.quote_backlink_rate`、`claims_by_strength`、`verification.passed/7` |
| 效率增益 5 | 一次 `plan` 覆盖全部子问题的检索，同一段落不重复计入；`--top-k` 控制候选量，减少无效追加 | `coverage.n_queries`、`n_candidates`、`runtime.tool_calls` |
| 增益可验证性 5 | 同一输入可重复运行，输出结构与计数稳定；`selfcheck.json` 给出确定性的通过项 | 重跑两次比对 `result.json` 的 `coverage`/`verification` |

## 3. 创新增益（15 分）

| 评分点 | 落点 |
|---|---|
| 新增能力 5 | 「候选证据预校验」：程序先把逐字句子连同 locator 取出，Agent 只能引用已存在文本，结构上排除编造引用 |
| 方法改进 5 | 拆解模板与检索词外置到 `protocol.md`，改策略不改代码；依赖性波次并行，避免重复检索 |
| 创新证据 5 | `verification` 记录重解析校验结果；`changes` 记录结论降级、子问题增补等运行期决策 |

## 4. 可靠体验（10 分）

| 评分点 | 检查 |
|---|---|
| 调用与易用性 3 | `--help` 可用；`--stage plan|finalize|check|auto` 四段式；默认 `auto` 一条命令跑完 |
| 运行稳定性 4 | 退出码恒 0；partial 先行落盘；失败不覆盖已有 `ok/partial`；单材料失败只降级该材料 |
| 异常处理 3 | 见 SKILL.md §10 降级表：无输入、坏 JSON、无 pdftotext、扫描件、零命中、quote 未命中 |

## 5. 生态贡献（10 分）

| 评分点 | 凭据 |
|---|---|
| 文档完整性 3 | `SKILL.md` 13 节：用途/契约/输入/输出/流程/规则/定位/冲突/预算/降级/自检/示例/维护 |
| 资源可复用性 4 | 拆解模板（`protocol.md` 的 SQ_TEMPLATES）、检索计划结构、证据矩阵列定义、`result.json` schema 均可直接复用 |
| 分享推广价值 3 | 纯标准库、零网络、单入口；换材料即可跑其他综述题；示例见 `example.md` |

## 6. 一致性自检（提交前跑一遍）

```bash
python3 -B scripts/main.py --stage auto --input /input --output /app/output
python3 -c "import json;d=json.load(open('/app/output/selfcheck.json'));print(d['passed'],'/',d['total'],d['failures'])"
```

期望：`7 / 7 []`。若非全过，按 `failures` 指向的键逐条修：`contract_fields` → 契约字段缺失；`citations_verbatim` → 有 quote 未命中原文（应删证据或降级结论）；`claims_cited` → 有非 insufficient 结论缺引用。
