---
name: search-coverage-gap-auditor
description: Audit literature-search coverage against a frozen reference set and attribute every miss to a concrete query/field/year-window/source. Use when the case provides known-relevant references plus retrieved records or query logs and asks for coverage, recall, missed-study analysis, or supplementary retrieval. Produces a hit matrix, auditable source locators, coverage metrics on a non-circular denominator, per-miss cause codes, and directed supplementary rounds with measured marginal gain. The agent must read /input directly, treat deterministic script outputs as a baseline, and write corrections through draft.json/agent_review.json instead of fabricating data.
version: 3.0.0
---

# search-coverage-gap-auditor

## 0. 唯一入口与最高优先级

标准入口为单命令：

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部执行：

- `init`：盘点 `/input`，建立材料清单、来源编号 `S#`、候选记录抽取、参考集/检索池/查询日志识别、冲突分组。
- `build`：校验抽取结果；若存在 `/app/work/draft.json` 则采用 Agent 核验后的判断，否则启用确定性兜底抽取；生成全部产物并 finalize `result.json`。
- `selfcheck`：核对 `output_contract` 字段、磁盘产物、`result.json` 键三者一致；运行 `scripts/verify.py` 并生成 `verify_report.json`。

若当前安装的 `scripts/main.py` 不识别 `run` 子命令，立即退化为兼容入口：

```bash
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
```

无论脚本是否报错、材料是否缺失，最终必须退出码 0，并把失败写入 `result.json.errors/degradations/pending_human`，不得静默失败。

## 1. 任务边界与诚实原则

本 Skill 用于：

- 对冻结参考集和实际检索记录池做覆盖率、遗漏率、逐条命中/漏检审计；
- 对每条漏检给出可操作的 `cause_code` 和具体证据；
- 记录查询式、字段、时间窗、来源库，判断补检是否真的新增命中；
- 输出可复核的 `hit_matrix`、`candidates`、`query_log`、`supplement_plan`、`coverage_report`。

本 Skill 不做：

- 正式全文阅读、研究质量评价、系统综述纳排流程；
- 接入外部数据库、实时联网检索；
- 用检索结果自己反推“应检文献”；
- 把“池中没找到”直接当成“不相关”；
- 声称全球查全、最新文献或无法验证的 citation/status。

覆盖率的分子、分母必须来自可核对的参考集和实际命中记录。若输入没有可识别参考集，只能计算“输入覆盖/候选池覆盖”，并在结果中明确说明这不是真实召回率。

## 2. 输入、输出与工具

- 输入目录 `/input` 只读：`case.json`、`task.md` 和题面提供的材料。必须读取实际文件内容，不得按文件名或领域标签假设内容。
- 工作目录 `/app/work`：保存解析文本、台账、候选抽取、冲突组、`draft.json`、中间核对结果。
- 输出目录 `/app/output`：保留全部最终交付物和 `result.json`。
- 最终必须存在 `/app/output/result.json`，包含 `case_id` 和题面 `output_contract` 的全部字段。
- 若任务要求可编辑 Office/幻灯片/图形产物，必须实际渲染真实 PDF/PNG 预览；否则不额外生成。
- 资源限制：最多 50 个 UTF-8 文本文件，单文件 ≤500KB，总计 ≤2MB；纯 Python 标准库，Python ≥3.8；离线可用。

## 3. 双路径：Agent-first + 确定性兜底

### 3.1 Agent 路径

Agent 优先，但必须通过 `draft.json` 施加判断，不直接手改结构化 JSON：

1. 先运行单命令入口，获得基线产物；
2. 读取 `/app/work` 下的台账、抽取结果、冲突组；
3. 对照原始 `/input` 材料逐条核验；
4. 将核验后的权威判断写入 `/app/work/draft.json`；
5. 重新运行 `build` 和 `selfcheck`；
6. 运行验证脚本，完成最终交付。

`draft.json` 至少包含：

- `case_id`
- `reference_set[]`：`ref_id`, `doi`, `title`, `year`, `authors`, `eligible`, `excluded`, `exclusion_reason`, `inclusion_reason`, `source_id`, `locator`, `quote`
- `retrieval_pool[]`：`rec_id`, `doi`, `title`, `year`, `source_id`, `locator`, `query_id`, `retrieved_at`, `duplicate_of`
- `queries[]`：`query_id`, `query_string`, `fields`, `year_window`, `source_db`, `hits`, `retained`
- `hit_decisions[]`：`ref_id`, `rec_id`, `match_type`, `score`, `reviewed`, `evidence`
- `miss_causes[]`：`ref_id`, `cause_code`, `query_id`, `field`, `window`, `source_db`, `evidence`
- `supplement_rounds[]`：`round_id`, `query_id`, `query_string`, `new_hits[]`, `marginal_gain`
- `uncertainty[]`, `pending_human[]`

完整字段见 `references/io-schema.md`。

### 3.2 确定性兜底路径

若 Agent 未写 `draft.json`，`build` 必须基于 `init` 台账做确定性抽取，生成实质工作稿：

- 每条参考集记录和候选记录都要有 `quote` 和 `locator`；
- 命中判定按确定性规则执行；
- 在 `result.json.gaps/degradations` 中诚实写入 `AUTO_EXTRACT`，标明“本产出由确定性兜底生成，未经 Agent 逐条人审”；
- 不得把 `AUTO_EXTRACT` 伪装成已核验证据。

两条路径必须产出同一套 `result.json` 契约、同一套交付物文件命名。

## 4. 来源编号与证据定位

所有关键数字、命中、漏检、补检结论必须带来源：

- `S#` 来源编号，写入 `result.json.sources`；
- locator 格式：`文件名#L12`、`文件名#para 3`、或 JSON 路径 `file.json#$.items[4]`；
- 禁止用“数据库覆盖不足”“关键词不好”等泛化归因；每条漏检必须至少落到 `query_id + field + year_window + source_db` 中可追溯的具体点。

材料缺失、无法解析、权限失败、无法获取全文时，分别写入：

- `errors`：运行失败或文件损坏；
- `degradations`：解析降级、AUTO_EXTRACT、工具缺失；
- `pending_human`：需要人工裁决或补充材料；
- `uncertainty`：统计不确定性、口径不确定、近似匹配不确定。

不得补造文献、引用、DOI、命中状态、作者、年份、来源或评分。

## 5. 覆盖口径与命中判定

### 5.1 分母

- 主口径：`coverage = n_hit / n_eligible`
- `n_eligible`：冻结后参考集数量，在匹配前锁定；排除撤稿、无法获取全文、重复记录。
- 同时输出 `coverage_over_all_refs`：以全部去重参考集记录为分母的保守口径。
- 参考集很小时必须报告 Wilson 95% 置信区间和不确定性。
- 禁止循环定义：不得以检索结果自身作为应检文献分母。

### 5.2 命中分级

| 层级 | 规则 |
|-|-|
| `exact_doi` | DOI 归一化后完全相同 |
| `identifier` | PMID/PMCID/arXiv/ISBN/OpenAlex 任一标识符匹配 |
| `exact_title` | 归一化标题完全相同 |
| `fuzzy_title` | 标题归一化后高相似，且作者+年份一致；需保留相似度证据 |
| `manual` | Agent 人工裁决，必须附理由、来源、locator |
| `miss` | 参考集记录在检索池/查询日志中无有效命中 |

### 5.3 漏检分类

至少使用可操作原因类：

- `C01`：查询词未覆盖同义表达、缩写、变体；
- `C02`：检索字段限制过窄；
- `C03`：时间窗截断；
- `C04`：来源库未收录该记录；
- `C05`：记录标识异常、元数据错误、被去重误合并；
- `C06`：补检空转：新查询只是同义词重跑，无新增命中。

每个 `miss_causes` 必须包含具体 `query_id`、字段、时间窗、来源库和证据。无法归因时写 `pending_human`，不得猜。

## 6. 交付物清单

每次运行必须产出：

- `/app/output/result.json`
- `/app/output/hit_matrix.csv`
- `/app/output/candidates.csv`
- `/app/output/query_log.json`
- `/app/output/supplement_plan.json`
- `/app/output/coverage_report.md`
- `/app/output/verify_report.json`

建议产出：

- `/app/output/agent_review.json`：逐条核验结论与脚本修复记录；
- `/app/output/pending_human.json`：需人工复核项。

`result.json` 必须双回显：

```json
{
  "case_id": "...",
  "status": "...",
  "sources": ["..."],
  "uncertainty": ["..."],
  "pending_human": ["..."],
  "errors": ["..."],
  "degradations": ["..."],
  "...output_contract 字段平铺在顶层...": "",
  "output_contract": {
    "...output_contract 字段完整嵌套回显...": ""
  }
}
```

任何 `output_contract` 字段缺失时，用 `null`/`[]`/`""` 补齐，并在 `contract_fill` 中注明来源与转换方式。

## 7. 执行流程与预算

### 7.1 执行顺序

1. 立即运行单命令入口，落盘完整基线；
2. 读取 `/app/work` 台账和原始材料，按“参考集 → 检索池 → 查询日志 → 命中矩阵 → 漏检归因 → 补充检索”顺序核验；
3. 写出或修正 `/app/work/draft.json`；
4. 运行 `build` 和 `selfcheck`；
5. 运行 `python3 -B scripts/verify.py --input /input --output /app/output --work /app/work`；
6. 按第 8 节自检清单收尾。

### 7.2 预算分配

| 阶段 | 模型请求建议 |
|-|-|
| 运行脚本、读取台账和原文盘点 | 6–10 |
| 批量解析 PDF/DOCX/CSV/JSON 证据 | 12–16 |
| 核验参考集、检索池、命中矩阵 | 14–18 |
| 核验漏检归因和补充检索边际收益 | 8–12 |
| 回填 result.json、自检、修复 | 6–10 |
| 预留异常处理 | 4 |

接近 64 次请求或 900 秒时，必须优先保证 `result.json` 合法、完整、诚实落盘，设置 `status=partial` 并写明未完成项。

## 8. 自检清单

提交前逐项确认：

1. `result.json` 是合法 JSON，`case_id` 与 `/input/case.json` 一致；
2. 所有 `output_contract` 字段同时出现在顶层和 `nested output_contract` 中；
3. `hit_matrix.csv` 行数覆盖所有参考集记录，并有 `ref_id`、`match_type`、`score`；
4. 每条漏检都有 `cause_code`、`query_id`、`field`、`window`、`source_db`、`evidence`；
5. 没有任何“以检索结果自行定义分母”的口径；
6. 所有数值/论断都可回溯到 `S#` 和 `文件#行号/段落号`；
7. `query_log.json` 中每个查询都有实际命中数、保留数、字段限制、时间窗、来源库；
8. `supplement_plan.json` 只报告真实新增命中；无新增则明确标记“补检空转”，不得声称遗漏下降；
9. `coverage_report.md` 包含研究问题、参考集说明、覆盖结果、逐条命中/漏检表、漏检分类统计、补检式与边际收益、残余遗漏与停止理由；
10. `verify_report.json` 通过；若未通过，`status` 必须为 `partial` 并在 `errors` 中列明。

## 9. 隐藏案例鲁棒性

| 情况 | 处理 |
|-|-|
| 正常案例：参考集+检索池+查询日志完整 | 跑满闭环：冻结分母 → 命中矩阵 → 漏检归因 → 补检边际收益 → 残余遗漏 |
| 边界案例：重复记录、撤稿、无法获取全文、标识冲突 | 去重合并，保留来源数组；排除不可用记录并记录原因；标识冲突标 `pending_human` |
| 异常案例：PDF 无文本层、CSV 缺列、JSON 损坏、缺 `case.json` | 尝试替代文件和可用解析器；失败则保留文件路径和错误；继续生成 `result.json`，`status=partial/input_error`，退出码 0 |
| 空参考集或材料不足 | 不编造分母；`coverage=null`，`status=insufficient_evidence`，说明无法计算真实召回率 |
| 超时临近 | 立即落盘当前 `result.json`，`runtime.timeout_near=true`，`status=partial` |

## 10. 与基础 Agent 对照的增益证据

不引用平台白板分差，不伪造 benchmark。用产物内的可复算变化证明增益：

- `auto_deterministic_baseline`：脚本兜底的覆盖率；
- `agent_reviewed`：Agent 核验纠正后的覆盖率；
- `supplement_after`：定向补检后的覆盖率；
- `marginal_gain`：补检真实新增命中数；
- `misses_resolved`：从漏检转为命中的具体 `ref_id` 列表；
- `baseline_comparison`：记录原值、修正值、修正理由和证据。

`coverage_report.md` 必须展示“基线 → Agent 核验 → 补检后”的变化，不用文字自述代替运行证据。

## 11. 禁止扣分项

1. 禁用预制答案、伪造隐藏案例输出或评分结果；
2. 禁止以检索结果自身定义覆盖率分母；
3. 禁止把“未命中”直接标为“不相关”；
4. 禁止泛化漏检原因，必须落到具体查询式/字段/时间窗/来源库；
5. 禁止把同义词重跑且无新增命中报告为补检有效；
6. 禁止删除或清空基线产物、`result.json` 契约字段、来源定位；
7. 禁止引用不存在的文件、来源或外部个人文件；
8. 禁止在脚本失败时静默退出；必须写入 `errors/degradations` 并 exit 0。