---
name: literature-field-extraction
description: Extract per-requested-field literature data (value/unit/statistic/experimental condition/comparator/exact quote/locator) from PDF/DOCX/XLSX/CSV/MD against /input/target-fields.json, with honest statuses reported/not_reported/source_conflict/extraction_failed and result.json honoring the original output_contract. Use for structured scientific reading, not prose summarization.
version: 3.0.0
license: MIT
---

# 文献结论与数据提取（逐字段 + 原文字面证据 + 可复核结构）

## 0. 最高优先级：完整、诚实、可复核

本 Skill 的目标不是压缩论文，而是把每个被要求的 `field_id` 还原成可独立抽查的结构化记录。每条关键数值、结论、条件、对照都必须能回到原文位置；猜出来的值不算抽取；原文没写不等于 0；quote 字面命中不等于语义正确。

必须同时满足：

1. 单命令能跑完整流程，异常也退出码 0，并产出合法 `result.json`。
2. Agent 路径与确定性兜底路径产出同一套产物、同一份契约。
3. 任何 “未报告 / 抽取失败 / 冲突” 都被诚实区分，不伪造、不合并、不升格成事实。
4. 所有关键数字/论断带 `[S#]` 来源和 `文件#行号/段落号/表格/图` 定位。
5. 时间或请求预算不足时，先落盘 honest partial，再增量改进。

---

## 1. 用途与边界

- 适用：输入包含任务说明 + 科研材料 + `/input/target-fields.json`，要求逐字段抽取结论、条件、数值、证据定位。
- 重点：正文、表格、图注、补充材料应作为同一张字段表的不同来源处理。
- 不适用：只给摘要式总结、跨文献合并、替作者下结论、自造评分或金标准。
- 铁律：抽取失败不等于原文未报告；缺失值不等于 0；数值不带单位、统计量、条件、对照时应明确留空或降级，不得脑补。

---

## 2. 运行契约

| 项目 | 说明 |
|---|---|
| Skill 目录 | `$SKILL_DIR`；评测机安装为 `/skills/weekly-skill`，不要写死绝对路径 |
| 输入目录 | `/input`：`case.json`、`task.md`、`target-fields.json`、论文/表格材料 |
| 工作目录 | `/app/work`：索引、草图、台账、日志 |
| 输出目录 | `/app/output`：全部交付物，包括 `result.json` |
| 运行依赖 | `python3 -B`，纯标准库，离线，不依赖 CWD，不依赖未说明的个人文件 |
| 退出码 | 任何情况下均应为 0；失败也要写合法 `result.json` |

---

## 3. 单命令全流程入口

首次执行优先尝试：

    python3 -B "$SKILL_DIR/scripts/main.py" run --input /input --output /app/output --work /app/work

该入口内部应等价于：

    init -> 发现材料与字段表 -> 若已有 draft.json 则 check -> build -> audit/selfcheck
    -> 若无 draft.json 则确定性兜底抽取 -> build -> audit/selfcheck

若当前包未提供 `run` 子命令，则使用兼容序列：

    python3 -B "$SKILL_DIR/scripts/main.py" init
    python3 -B "$SKILL_DIR/scripts/main.py" check
    python3 -B "$SKILL_DIR/scripts/main.py" build
    python3 -B "$SKILL_DIR/scripts/main.py" audit

脚本命令只能引用包内真实文件。缺失 `case.json` 时尝试 `case*.json`，读入时容忍尾逗号，使用 `utf-8-sig`。

---

## 4. Agent-first 双路径

### 路径 A：Agent 增强（优先）

1. 运行 `init`，阅读 `/app/work/workorder.md` 中的字段表、材料台账和契约键。
2. 用 `show --grep` 或 `show --para` 亲自读原文。表格字段还要读表头、行、列和前后段；图注字段读图注及正文提及处。
3. 把判断写入 `/app/work/draft.json`，一个 `field_id` 一行，按 §8 规则填写状态、值、quote、locator、reasoning。
4. `check` 通过后 `build`。
5. 调用 `show`/核对产物，把复核结论写入 `agent_review.json`；正文型交付物可由 Agent 改写，但结构化 JSON 结构不由手工覆盖。

Agent 增强证据必须体现为：

- `agent_review.json`：逐条 claim/field 复核结果 `verified/rejected/reason`。
- `result.json` 的 `reviewed_by_agent: true`、`verified`、`conflicts`。
- `changes` 中追加 `agent_reviewed`。

### 路径 B：无 draft 时确定性兜底

如果没有 `draft.json` 或草稿不合法：

1. `build` 必须用 `init` 台账中的段落、句子和候选片段确定性抽取，生成实质工作稿。
2. 每个可抽取字段必须有逐字 `quote` 和 locator。
3. 无法可靠抽取的字段标 `extraction_failed`；没有证据的标 `not_reported`。
4. 在 `result.json` 的 `gaps`/`degradations` 中诚实写入 `AUTO_EXTRACT`，并说明该轮为确定性兜底，不伪装成完整 Agent 复核。

两条路径必须产出同一套磁盘产物和同一份 `result.json` 契约。

---

## 5. 完整交付物清单

`/app/output` 至少产出：

| 文件 | 内容 |
|---|---|
| `result.json` | 最终契约结果；顶层与 nested `output_contract` 双回显 |
| `extraction.csv` 或 `extraction.json` | 逐字段表；行数等于字段表条数 |
| `evidence_table.json` | 每个字段的 quote、locator、来源、状态 |
| `claims.json` | 关键结论卡片；含 kind、evidence、source_id、location、field_ids |
| `deliverable.md` | 若题面要求正文类交付；每个数字/结论能回到 `evidence_table.json` |
| `golden_standard.json` | 内部重扫基准；仅一致性自检，不代表官方评分 |
| `diff_report.md` | match/deviation/gap/needs_review |
| `version_history.md` | 修改记录、回退记录、版本差异 |
| `run.log` | 真实执行过的步骤、耗时、退出码 |
| `self_check.json` | 契约自检结果；`summary.failed` 应为 0 或已说明 |

若题面要求可编辑 Office/幻灯片/图形产物，还必须额外输出真实渲染的 PDF/PNG 预览。

---

## 6. `result.json` 双回显与关键字段

`/app/output/result.json` 必须同时具备：

- 顶层直接出现原 `output_contract` 的全部字段：`case_id`、`status`、`result`、`claims`、`uncertainties`。
- 顶层额外出现：`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`counts`。
- `output_contract` nested 对象再次出现原契约字段：`case_id`、`status`、`result`、`claims`、`uncertainties`。
- 原契约中未知键也必须保留，缺值用 `null` 或 `[]`，不删除、不改名。

`status` 取值：

- `answered`：全部字段已处理且无未解决 gap。
- `partial`：存在未解决项，但已逐项标注。
- `insufficient_evidence`：证据不足无法完成关键字段。
- `input_error`：输入缺失或不可用。

若原契约只允许 `answered|partial|insufficient_evidence|input_error`，则必须适配该集合，优先使用 `answered`，不要使用 `ok`。

`counts` 应包含：

- `target_fields`
- `reported`
- `not_reported`
- `source_conflict`
- `extraction_failed`
- `quote_failed`
- `source_kinds_seen`

`runtime` 应包含：

- `requests_used`
- `seconds`
- `exit_code`

`sources` 每个材料至少包含：

- `source_id`，如 `M1`
- `title`
- `path`
- `format`
- `parse_status`
- `pages` 或 `paragraph_count`

---

## 7. `draft.json` 草稿形状

草稿写入 `/app/work/draft.json`：

    {
      "case_id": "原样保留",
      "fields": [
        {
          "field_id": "F1",
          "label": "IC50",
          "value": 12.4,
          "unit": "nM",
          "statistic": "95% CI 10.1-15.2 nM",
          "condition": "25 degrees C, 30 min, triplicate",
          "comparator": "vehicle",
          "source_kind": "text|table|figure|abstract|supplement",
          "status": "reported",
          "quote": "原文逐字片段",
          "locator": {
            "material_id": "M1",
            "paragraph_id": "M1-p0002",
            "page": 3,
            "table": "Table 2",
            "row": "control",
            "col": "mean",
            "figure": null
          },
          "reasoning": "怎么读出：句子/单元格/图注；单位与统计量来源",
          "conflict": null
        }
      ],
      "claims": [],
      "uncertainties": [],
      "pending_human": []
    }

---

## 8. 字段四状态判定

按以下顺序判定：

1. 材料里到底有没有该字段的证据？
2. 多处证据是否一致？
3. 有候选证据时，能否可靠读出？

| status | 含义 | 必填 |
|---|---|---|
| `reported` | 原文明确给出 | `value`、`quote`、`locator`；尽量给 `unit`/`statistic`/`condition`/`comparator` |
| `not_reported` | 材料范围内确实没有 | `reasoning`：搜索词、已查章节/表/补充材料 |
| `source_conflict` | 多处说法不一致 | 双方 `quote_a`/`quote_b`，可给 `value_a`/`value_b`；首选值写入 `value` 并注明 |
| `extraction_failed` | 有候选但读不出：跨页缺行、合并单元格、无文本层、单位缺失 | `reasoning`：失败点、已试手段、可人工接管位置 |

`not_reported` 与 `extraction_failed` 不得互换。

---

## 9. 引用、定位与数值规则

### quote

- `quote` 必须是原文字面片段，逐字复制，不翻译、不改词、不改数字顺序。
- 允许省略号截取连续片段，但不得改写。
- 脚本校验分级：`quote_strict` > `quote_normalized` > `quote_loose`；只有 `loose` 命中时记 warning 并尽量修复。

### locator

- 至少包含 `material_id` 和 `paragraph_id`。
- PDF 增加 `page`。
- 表格字段必须有 `table`、`row`、`col`；跨页表写两页页码。
- 图注字段必须有 `figure` 和子图号。
- 不能用 “结果段”“讨论部分” 这类二手定位代替段落/表格/图注定位。

### 数值、单位、统计量、条件、对照

- 保留原值形态：`12.4` 不写 `12`；`10.1–15.2 nM` 不改写成 `±2.5`；不换算单位。
- `statistic` 存误差、区间、检验量原文，如 `SD 0.4`、`p = 0.03`。
- `condition` 存温度、时间、剂量、样本、基线等。
- `comparator` 存对照或比较组；原文没有则留空，不写猜测的 “N/A”。
- 表格值必须与表头逐字对应，列不交换；合并单元格跨行时 `locator.row` 写所属组。
- 图注只取文字明确写出的数值；像素读数标 `approximate: true` 并给误差。

---

## 10. 结论、推测与人工复核

`claims` 每条应有：

- `id`
- `kind`：`author_conclusion` / `limitation` / `speculation` / `data_point`
- `text`
- `quote`
- `locator`
- `field_ids`

作者明确结论、限制条件、推测性表述必须分层； “可能”“提示” 不得改写为确定事实。

以下情况进入 `pending_human`：

- 扫描件无文本层
- 单位缺失
- 表格跨页缺行或合并单元格
- quote 仅 `loose` 命中
- 需要领域换算
- 冲突无法裁决

---

## 11. 异常、边界与隐藏案例鲁棒性

任何情况下都必须产出合法 `result.json`，且退出码为 0。

| 场景 | 处置 |
|---|---|
| `case.json` 缺失或坏 | 尝试 `case*.json`；仍失败则用材料 + 字段表继续，`status=partial` 或 `input_error` |
| `target-fields.json` 缺失 | 若 case 内有字段表则用 case 内；否则从 `task.md` 提取候选字段，并在 `uncertainties` 说明来源 |
| 材料缺失或损坏 | 对应字段标 `extraction_failed`，写入 `errors` 和 `degradations` |
| PDF 无文本层 | 标 `degradations: pdf_no_text_layer`，相关字段 `extraction_failed`，`pending_human` 说明需 OCR 或人工 |
| 表格跨页或合并单元格 | 不推测缺失行，标 `extraction_failed` 或 `source_conflict`；写两页页码和已读内容 |
| 多处数值冲突 | 标 `source_conflict`，保留双方证据，不偏袒、不合成 |
| 单材料解析失败 | 只降级该材料涉及字段，其他材料继续 |
| 草稿缺失或坏 JSON | 使用 `init` 台账自动兜底，字段标 `extraction_failed` + `fallback_used`，写入 `degradations` |
| 空输入或无字段 | 产出最小合法 `result.json`：`fields:[]`、`claims:[]`、`uncertainties` 说明无字段 |
| 输出契约缺失键 | 已知契约键全部回填；未知键保留，缺失值用 `null`/`[]` |
| 超时或请求用尽 | 保留最近一次 `build` 产物，`status=partial`，`uncertainties` 写未完成字段清单 |

---

## 12. `check` 错误与警告处置

| code | 处置 |
|---|---|
| `missing_field` | 补该 `field_id` |
| `bad_status` | 改四状态之一 |
| `quote_not_found` | 读取原文，复制逐字 quote；多为改写或断字 |
| `bad_locator` | 改用真实 `M*-pNNNN` 或表格图注定位 |
| `empty_value` / `quote_missing` | 补齐，或降级 `extraction_failed` 并写依据 |
| `no_justification` | 非 `reported` 补搜索词和已查范围 |
| `quote_loose` | 核对后修复；无法修复则在 `uncertainties` 说明 |
| `number_not_in_quote` | 数值不在 quote 中；补含有数值的原文片段或降级 |
| `conflict_sides` | 冲突双方 quote 必须都能查到 |
| `no_reasoning` | 补推理依据，尤其是非 `reported` 字段 |

---

## 13. 预算策略：64 次模型请求 / 900 秒 / 16384 tokens

优先完成高权重交付物，再增量改进。

| 阶段 | 请求数 | 说明 |
|---|---|---|
| `init` + 读 workorder | 1–2 | 必做，确认字段表与契约 |
| 批量读原文候选段 | 5–15 | 优先覆盖全部字段；表格/图注附近至少一次 |
| 写 draft + `check` | 2–5 | 可先写部分字段即校验 |
| `build` 生成基线 | 1–2 | 必做，尽早落盘 |
| Agent 复核 + 修复 + 再 build | 3–8 | 优先修正 `reported` 和高权重字段 |
| `audit` + 最终自检 | 1–2 | 必做，重算可核验资产 |
| 总预算 | ≤64 | 达到 80% 预算时停止检索，直接 build 并诚实标 partial |

剩余时间少于 150 秒时，只执行 `build` 或保留最近合法产物，不再检索、不再审计。

---

## 14. Rubric 维度 → 交付证据对照

| Rubric 维度 | 必须落盘证据 |
|---|---|
| 任务完成度 | `fields` 覆盖全部 `target-fields.json`；`extraction.csv` 行数等于字段数；`source_kind` 覆盖正文/表格/图注/补充 |
| 结果正确性 | `reported` 字段 quote 可严格命中；数值/单位/统计量/条件保持一致；`claims.kind` 分层正确 |
| 结果完整性 | 非 `reported` 字段有搜索词与范围；`counts` 四状态之和等于字段总数 |
| 结果可核验性 | 每个字段有 `paragraph_id`/`page`/`table`；字段词典与抽取口径随结果提交 |
| 质量增益 | `agent_review.json`、`diff_report.md`、`reviewed_by_agent` 证明 Agent 增强 |
| 效率增益 | `run.log` 记录真实耗时；索引、校验、产物由脚本完成；Agent 只需复核 |
| 增益可验证性 | `version_history.md`、`audit` 可重放；同一口径可复跑 |
| 新增能力 | `condition`/`comparator` 与 `value` 同源绑定；`locator` 支持表格行列 |
| 方法改进 | `references/field_dictionary.md` 记录字段词典与口径；`self_check.json` 真实自检 |
| 创新证据 | `references/verification_assets.md` 说明资产 schema、判定口径、复跑方法与限制 |
| 调用与易用性 | `SKILL.md` 单命令入口清晰；`references/example.md` 为合成示例 |
| 运行稳定性 | 纯标准库、路径固定；`run.log` 展示真实执行；`self_check` 包含重复运行一致性 |
| 异常处理 | §11 降级表；`degradations`、`pending_human` 记录异常 |
| 生态文档 | 词典、口径、证据规则、依赖、示例、限制、维护信息齐全 |
| 生态复用 | `scripts/main.py` 可直接运行；替换 `target-fields.json` 可迁移到其他文献 |
| 生态分享 | `version_history.md` 沉淀迭代；`golden_standard.json` 作为内部重扫基准；`diff_report.md` 展示对照 |

---

## 15. 完整性自检清单（提交前必做）

1. `/app/output/result.json` 存在且为合法 JSON。
2. 顶层与 nested `output_contract` 均出现原契约字段。
3. `counts.target_fields` 等于字段表条数，四状态之和等于它。
4. 每个 `reported` 有 `value`、`quote`、`locator`。
5. 每个非 `reported` 有可读依据和搜索范围。
6. 冲突字段双方 quote 均可查到。
7. `self_check.json` 的 `summary.failed` 为 0；有失败项则在 `uncertainties` 说明。
8. `diff_report.md` 中 `gap` 已处理；`deviation` 已返工；`needs_review` 写入 `pending_human`。
9. `run.log` 只含真实执行步骤。
10. 磁盘文件与 `result.json` 键一一对应。
11. `partial` 状态必须列出缺失项；`input_error` 必须说明原因和接管位置。
12. 不编造数据、引用、评分、基准分数；不确定项写入 `pending_human` 或 `limitations`。

---

## 16. 最小示例（仅示意，非正式案例）

    python3 -B "$SKILL_DIR/scripts/main.py" init
    # materials=1 target_fields=2 | M1 paper.pdf paras=2
    python3 -B "$SKILL_DIR/scripts/main.py" show --para M1-p0001
    # M1-p0001 [M1 p1] Results: compound A inhibited the kinase with an IC50 of 12.4 nM.
    python3 -B "$SKILL_DIR/scripts/main.py" check
    # PASS
    python3 -B "$SKILL_DIR/scripts/main.py" build
    # fields=2 reported=1 not_reported=1 -> /app/output/result.json
    python3 -B "$SKILL_DIR/scripts/main.py" audit

示意 `result.json`：

    {
      "case_id": "EXAMPLE-NOT-A-TEST-CASE",
      "status": "answered",
      "result": {"fields": []},
      "claims": [],
      "uncertainties": [],
      "sources": [],
      "uncertainty": null,
      "pending_human": [],
      "errors": [],
      "degradations": [],
      "changes": ["baseline_build", "agent_reviewed"],
      "runtime": {"requests_used": 12, "seconds": 180, "exit_code": 0},
      "counts": {},
      "reviewed_by_agent": true,
      "output_contract": {
        "case_id": "EXAMPLE-NOT-A-TEST-CASE",
        "status": "answered",
        "result": {"fields": []},
        "claims": [],
        "uncertainties": []
      }
    }

---

## 17. 生态资源引用

必须随结果说明以下资源，若包内存在则按路径引用：

- `references/example.md`：端到端合成示例，标明为示例，不冒充正式案例结果。
- `references/field_dictionary.md`：字段词典、定义、口径、别名。
- `references/verification_assets.md`：可核验资产 schema、verdict 口径、复跑方法、限制。
- `references/version_history.md`：迭代记录与版本差异。
- `environment/resources.yaml`：若存在，以该文件声明预装依赖；本包脚本只依赖 `python3 -B` 标准库。