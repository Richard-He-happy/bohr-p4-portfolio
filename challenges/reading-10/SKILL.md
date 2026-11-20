---
name: paper-reproduction-verify
description: 对论文候选实现进行真实运行、事前容差比较与差异归因，交付可复核复现记录与 result.json。适用于参数/代码/指标验算，强调单命令全流程、Agent 优先与确定性兜底、诚实缺失标注、预算感知。
version: 2.0.0
---

# 论文复现与方法验证（paper-reproduction-verify）

## 0. Agent 修改边界与最高优先级

本 Skill 的结构化产物由脚本生成并校验；Agent 的职责是真实阅读材料、核验证据、补全正文型交付物，不得重写结构化 JSON 结构。

必须遵守：

1. **脚本拥有结构化文件**：`index.json`、`tolerance_plan.json`、`claims.json`、`evidence_table.json`、`verification.json`、`result.json` 的键名、`claim_id`、`source_id`、`locator`、`quote`、`strength`、`support_scope`、`counts` 必须保留脚本输出，不得用文本编辑覆盖。
2. **Agent 可写文件**：`draft.json`（按 `references/draft_schema.md`）、`agent_review.json`、`pending_human.json` 的补充项、`reproduction.md`、`deliverable.md` 等正文型交付物。
3. Agent 核验结果必须写入 `agent_review.json`，逐条给出 `claim_id -> verified/rejected/reason`；若脚本缺陷要修复，写临时 Python 调用脚本函数重算并覆盖，并记录在 `agent_review.json.script_fixes`，不得手改 JSON。
4. 禁止生成或引用无依据的 `golden_standard`、自设加权总分、自封“优于基准”的分数；只引用 `scripts/verify.py` 的真实输出。若脚本已生成此类自设资产，不得引用、不得美化，在 `agent_review.json` 说明局限。
5. 成稿中的每个数字、引用、论断必须能在 `evidence_table.json` 或实际运行日志中找到依据；不得把推测归因写成已证实原因。
6. 无论脚本阶段是否异常，最终执行必须退出码 0 并写出合法 `result.json`。

---

## 1. 触发范围与适用条件

当任务要求从论文材料出发，完成以下至少一项时，应调用本 Skill：

- 论文复现清单、材料定位、版本与许可证核验
- 参数/代码/指标验算与差异归因
- 从正文、附录、仓库、配置恢复可执行参数
- 运行两份候选数值方法并做同口径比较
- 生成带证据链接的复现报告
- 对材料缺失、冲突、不可复现做诚实分级

适合场景：有论文、代码/候选实现、关键指标、需要实际运行和比较的科研复现任务。

不适合：只需泛泛总结摘要、无候选实现、无任何运行对象、或题面明确不要求执行方法。此时应降级为证据梳理并诚实填写 `pending_human`。

---

## 2. 输入输出契约

### 2.1 输入

| 项 | 位置与含义 |
|---|---|
| `case.json` | `/input/case.json`；含 `case_id`、`output_contract`、`task_instruction`、workorder、候选/材料说明等，字段名可能变化 |
| `task.md` | `/input/task.md`；任务说明 |
| 科研材料 | `/input/**`；PDF、DOCX、XLSX、CSV、图片、代码、JSON、MD 等 |
| Skill 根 | 默认 `/skills/weekly-skill`；不可用时在 `/` 下查找 `SKILL.md` |
| 包内资源 | `environment/resources.yaml`、`references/guide.md`/`draft_schema.md`/`repro_rules.md`、`SELFTEST.md` |

所有输入均以实际文件内容和元数据为准，不以文件名或错误标签猜测。

### 2.2 输出

最终必须写入 `/app/output`：

- `/app/output/result.json`：总契约回显与状态
- `/app/output/reproduction.md`：可读复现报告
- `/app/output/reproduction.json`：结构化复现结果
- `/app/output/runs/`：每次候选运行日志、命令、退出码、原始指标
- 任何 `output_contract` 明确要求的文件必须生成到对应路径；契约中的字段必须在 `result.json` 和磁盘文件中同时可查
- 若要求可编辑 Office/幻灯片/图形产物，必须额外给出真实渲染的 PDF/PNG 预览；无法生成时写入 `pending_human` 原因

### 2.3 result.json 契约

`result.json` 必须同时满足：

1. 保留输入 `output_contract` 的全部原始字段，并在两个位置出现：
   - 顶层直接出现每个 `output_contract` 字段
   - `output_contract` 对象内完整重复
   - 顶层 `case_id` 与嵌套 `output_contract` 内 case_id 值一致
2. 额外包含可核验运行状态字段，例如：

    {
      "case_id": "<case_id>",
      "repeat_id": "<平台重复编号，未知则 repeat_1>",
      "condition": "<平台条件，未知则 null>",
      "status": "success|partial|input_error|insufficient_evidence",
      "sources": [
        {
          "source_id": "S1",
          "type": "pdf|csv|code|json|...",
          "path": "/input/...",
          "locator": "paper:p3"
        }
      ],
      "uncertainty": [],
      "pending_human": [],
      "errors": [],
      "degradations": [],
      "changes": [],
      "output_contract": { "...原样保留所有契约字段..." }
    }

3. `status` 必须诚实；部分成果必须明确限制。不得把缺失写成成功。

---

## 3. 单命令全流程入口

首选命令：

    python3 -B "$SK/scripts/main.py" run --input /input --output /app/output --work /app/work

`run` 内部执行：

    init → build → selfcheck

并保证：

- 先落盘合法 partial `result.json`
- 无 `draft.json` 时使用确定性兜底抽取
- 异常仍退出码 0
- 不依赖当前工作目录

也可使用环境变量覆盖路径：

    SCIM_INPUT=/input SCIM_OUTPUT=/app/output SCIM_WORK=/app/work python3 -B "$SK/scripts/main.py" run

如需 Agent 增强，可分步执行：

    python3 -B "$SK/scripts/main.py" init
    # Agent 读材料、写 draft.json
    python3 -B "$SK/scripts/main.py" check
    python3 -B "$SK/scripts/main.py" build
    python3 -B "$SK/scripts/main.py" selfcheck

---

## 4. 执行流程

### 步骤 0：定位 Skill 并自检

    SK=/skills/weekly-skill; [ -f "$SK/SKILL.md" ] || SK="$(dirname "$(find / -maxdepth 4 -name SKILL.md 2>/dev/null | head -1)")"
    python3 -B "$SK/scripts/main.py" --help
    python3 -B "$SK/scripts/verify.py" --selftest

失败时记录 `init_failed` 与 stderr，继续尝试生成最小合法 `result.json`，最终退出码 0。

### 步骤 1：init，建立台账与先落 partial

    mkdir -p /app/work /app/output
    python3 -B "$SK/scripts/main.py" init --input /input --output /app/output --work /app/work

`init` 必须完成：

- 索引 `/input` 全部材料
- 分配稳定 `source_id`
- 抽取材料类型、元数据、候选入口
- 冲突分组
- 生成 `/app/work/index.json`
- 生成 `/app/work/tolerance_plan.json`
- 在 `/app/work` 与 `/app/output` 先写合法 partial `result.json`

Agent 必须亲自读 `/input/case.json`，识别 `case_id`、`output_contract`、`task_instruction`、`organizer_supplied_scope`、`organizer_workorder`、`candidates/implementations`、`reported_metrics`、`environment` 等语义字段，不假设键名。

材料扫描规则：

- 跳过 `case.json`
- 按扩展名 + 魔数判定类型：`%PDF`、`PK` + `word/`、`xl/`、PNG/JPEG 等
- 不按文件名或领域标签猜内容
- locator 形式如：`paper:p3`、`md:§标题/p2`、`csv:r7`、`json:#/results/accuracy`

### 步骤 2：真实解析材料，读原文而不是猜

对每个关键材料，真实读取内容：

- PDF：优先调用平台预装解析工具；无文本层时记录 `pdf_text:failed`
- DOCX/XLSX/CSV/JSON/MD/TXT：使用对应解析路径读取
- 图片/扫描页：无 OCR 不得猜像素或图注，进入 `pending_human`

定位关键片段：

    python3 -B "$SK/scripts/main.py" show --id paper --grep "accuracy"
    python3 -B "$SK/scripts/main.py" show --id paper --grep "learning_rate"

Agent 必须亲自阅读 `show` 输出，确定论文报告值、表头、单位、条件、页码/段落，并记录逐字 quote 与 locator。

候选实现/代码也必须读取实际命令、入口、默认参数、commit、依赖，不得仅凭文件名推断。

### 步骤 3：写 draft.json，建立证据与参数表

Agent 写 `/app/work/draft.json`，至少覆盖：

- `paper`：标题、DOI、repo、commit；未知写 `null`
- `plan`：复现步骤、命令、期望、状态
- `environment`：python/平台/依赖版本/seed；由 `init` 与本机实测填，不伪造
- `params`：每个关键参数的值、`class`、`evidence{source_id,locator,quote}`
- `paper_values`：指标名、报告值、单位、逐字 quote
- `tolerance`：只能等于或严于 `tolerance_plan.json`
- `claims`：每条含 `kind`、`text`、`confidence`、逐字 `quote`
- `conclusion.verdict`：`reproduced` / `partially_reproduced` / `not_reproduced` / `insufficient_evidence`

参数归类必须真实：

- 论文正文/表格/附录明确给出 → `paper`
- 只能从代码默认值/配置推断 → `code_inferred`
- 两边都没有、由 Agent 设定 → `chosen`，并写入 `uncertainty`

### 步骤 4：check，运行前校验

    cd /app/work
    python3 -B "$SK/scripts/main.py" check --work /app/work

`check` 校验：

- quote 是否能在材料中定位
- locator 是否有效
- 容差是否事前声明
- 关键字段是否缺失
- evidence 是否被拒绝

若 `check` 报 `evidence_rejected`：绝不改原文凑通过；删除该 claim 或降级为 `pending_human`。

### 步骤 5：build，真实运行候选并生成基线交付

    cd /app/work
    python3 -B "$SK/scripts/main.py" build --input /input --output /app/output --work /app/work

`build` 无条件定稿：

- 真实运行候选实现
- 保留 `/app/work/runs/<name>/run.log`
- 记录每次运行：命令、`exit_code`、耗时、stdout/stderr、缺失依赖
- 计算偏差：`observed` / `reported` / `abs_dev` / `rel_dev` / 容差 / 判定
- 写入 `reproduction.md`、`reproduction.json`、`result.json`

如果没有有效 `draft.json`，`build` 必须使用 `init` 台账进行确定性兜底抽取，生成实质工作稿，逐字 quote + locator，并把 `AUTO_EXTRACT` 诚实记入 `gaps`/`degradations` 或 `changes`。

候选没跑起来时：

- 不伪造运行
- 不猜数值
- 记录 `insufficient_evidence` 或 `pending_human` 要求人工回填
- 保留部分日志

### 步骤 6：selfcheck，产物与契约自检

    python3 -B "$SK/scripts/main.py" selfcheck --input /input --output /app/output --work /app/work

核对：

- `output_contract` 字段 → 磁盘文件 → `result.json` 键三者一一对应
- `result.json` 顶层与嵌套 `output_contract` 双回显
- 关键文件存在且非空
- 无旧结果混入
- Office/图形预览存在或已登记 `pending_human`

### 步骤 7：Agent 增强与核验，不删基线

Agent 通读基线三件套，核对：

- 材料定位是否回到原文 locator
- 参数值、分类、quote 是否一致
- 报告值是否逐字来自论文材料
- `observed` 是否来自单次真实运行
- 容差是否事前声明且未被放宽
- 差异归因是否与运行现象一致

然后：

- 将脚本产生的确定性判定保留为基线字段
- 增加 `reviewed_by_agent` 标记、Agent 核验结论、冲突与限制
- 新增/修正内容写入 `changes`
- 无法确认项标 `verified` / `pending_human` / `conflicts`

若 `deliverable.md` 与 `evidence_driven_draft.md` 同时存在，二者内容必须不同：前者是干净成稿，后者是带证据标记草稿，不得复制粘贴。

---

## 5. Agent 优先与确定性兜底双路径

### Agent 路径

    init → 读台账 → 读原文 → 写 draft.json → check → build → selfcheck

此路径允许 Agent 亲自核验，产出更高质量归因和正文。

### 无 draft 时的确定性兜底

若没用 `draft.json` 或 `draft.json` 无效：

- `build` 从 `init` 台账确定性抽取生成实质工作稿
- 必须带逐字 quote + locator
- 必须将 `AUTO_EXTRACT` 记入 `gaps`/`degradations`
- 两条路径产出同一套产物与同一份 `result.json` 契约

兜底结果不冒充高质量 Agent 成果；在 `changes` 中说明“此为基础确定性提取，未经人工逐条核验或仅部分核验”。

---

## 6. 容差、单位与比较口径

容差必须在任何运行之前冻结：

- case 明确给出容差 → 记为 `case_declared`
- 否则使用默认先验：**相对 2% + 绝对 0.5% × 报告值**
- `check` 发现事后放宽 → 记 `tolerance_widened_after_run`，不能通过

比较口径必须明确：

- 指标名、单位、数据切分、随机种子、模型/代码版本
- 若论文与代码单位或切分不可比，不得强行比较；结论标 `not_comparable`
- 若论文没有报告值，指标项写 `no_reported_value`
- 合成验算不得冒称原论文复现

每次比较输出：

- 参考值
- 实测值
- 绝对偏差
- 相对偏差
- 容差
- 判定：`in_tolerance` / `out_tolerance` / `not_comparable`
- 归因证据：链接到运行日志、材料 locator、参数证据

---

## 7. 证据、冲突与归因规则

### 7.1 证据单元

每条关键 claim 必须包含：

    {
      "claim_id": "C01",
      "kind": "report|param|metric|attribution|gap",
      "text": "...",
      "confidence": "明确|推断|自设",
      "source_id": "S1",
      "locator": "paper:p3",
      "quote": "..."
    }

### 7.2 冲突处理

- 正文与代码冲突时，保留双方证据
- 记录冲突来源、冲突值、裁决依据
- 无法裁决时写 `unresolved_conflict`，不硬选一个伪装成事实

### 7.3 归因分级

归因只能写为：

- `environment`
- `data`
- `implementation`
- `insufficient_description`
- `stochastic_seed`
- `unexplained`

推测性归因必须标为 `hypothesis`，不得写成已证实原因。

---

## 8. 异常与隐藏案例鲁棒性

### 正常案例

- 材料齐全、两方法可运行
- 完成双运行与同口径比较
- 保存命令、环境、seed、退出码、日志、原始指标

### 边界案例

- 正文与代码参数冲突、指标单位或切分不同
- 列出冲突证据并裁决
- 不可比则停止数值一致性判定
- 报告 `not_comparable`，不强行打分

### 异常案例

- 仓库、数据、依赖缺失或超时
- 分别标 `material_missing`、`unable_to_judge`、`run_failed`
- 保留日志及部分产物
- 不补造事实

材料全部不可用时：

- `status=insufficient_evidence` 或 `input_error`
- 仍产出合法 `result.json`
- `pending_human` 说明人工接管位置

---

## 9. 评分导向的证据清单

本 Skill 运行后必须留下以下可复核证据链，不依赖自述。

### 实际效果 40 分对应动作

- 输出材料与参数表：逐项标来源位置、版本、缺失、冲突裁决及“明确/推断/自设”
- 实际运行两份候选方法：保存命令、环境、种子、退出码、日志、原始指标
- 运行前冻结容差与比较口径：输出参考值、实测值、偏差、判定和归因证据
- 不将合成验算称为原论文复现

### 使用增益 25 分对应动作

- 逐任务项登记完成情况、证据覆盖、错误及人工接管项
- 记录查找、安装重试、重复运行次数与耗时
- 提供与平台基础结果对齐的表格；缺对照时不填提升率
- 保留失败与无提升结果

### 创新增益 15 分对应动作

- 交付“原文→参数→命令→指标→归因”关联 ID 表
- 交付冲突裁决、容差冻结和失败分级规则
- 用实际记录展示解决的问题及适用边界

### 可靠体验 10 分对应动作

- 单入口运行
- 探测资源、校验输入、隔离案例目录并支持断点续跑
- 先保存部分成果
- 异常写原因、已完成项、恢复命令和接管位置
- 重复运行不混入旧结果

### 生态贡献 10 分对应动作

- README 写安装、调用、来源、版本、许可、限制和维护方式
- 提供可复用模板及标注为示例的最小示例
- 根目录保留 `GITHUB_URL.txt`

---

## 10. 交付物与文件边界

### 10.1 可引用资源

- `SKILL.md`
- `references/draft_schema.md`
- `references/repro_rules.md`
- `references/guide.md`（若存在；若缺失，以 `draft_schema.md` 为 schema 来源，并在 `degradations` 记录缺包资源）
- `scripts/main.py`
- `scripts/verify.py`
- `environment/resources.yaml`
- `SELFTEST.md`
- `templates/*`
- `examples/*`

不得依赖任何作者私人路径或手工步骤。

### 10.2 文件限制

- 最多 50 个 UTF-8 文本文件
- 单文件 ≤ 500KB
- 总大小 ≤ 2MB
- 不得有符号链接
- 纯标准库、离线、Python ≥ 3.8
- 中英文自适应

### 10.3 重复运行隔离

- 默认按 `case_id` 隔离工作目录
- 每次运行前清理或隔离同 case 旧产物，不得混入旧 `runs/`
- 断点续跑时基于 manifest 追加，不得覆盖同路径不同内容

---

## 11. 预算与恢复策略

官方执行预算：

- 64 次模型请求
- 900 秒
- 每次响应 16384 tokens 含 reasoning

使用策略：

1. 先跑 `init`，落盘 partial
2. 再跑 `check` / `build`，尽量一次完成全套基线
3. 剩余请求用于逐条核验证据和成稿改进
4. 接近 60 秒剩余时，跳过未跑候选，记 `run_skipped_deadline`，立即定稿
5. 最终 `result.json` 合法且 status 诚实

无 draft 的确定性兜底应能在 1–3 次请求内完成全部产物；剩余预算用于 Agent 增强。

---

## 12. 最终验收清单

结束前逐项确认：

- [ ] `name`、`description` YAML 有效
- [ ] 单命令 `run` 可执行且退出码 0
- [ ] `result.json` 包含 `case_id` 与全部 `output_contract` 字段，顶层与嵌套双回显
- [ ] 至少尝试运行两份候选方法，保存实际日志和原始指标
- [ ] 容差在运行前冻结，未随结果放宽
- [ ] 关键数字与论断有 `[S#]` 来源与文件/行号段落 locator
- [ ] 缺失、冲突、无法判断在 `gaps`/`uncertainty`/`pending_human` 中登记
- [ ] 未生成或引用无依据的评分/金标准
- [ ] 可编辑 Office/图形产物已有 PDF/PNG 预览或已登记人工接管
- [ ] 重复运行不会混入旧结果
- [ ] 不声称成功但实际只有 partial
- [ ] 文件数量、大小、无符号链接符合约束

如任一不满足，不得自评成功；应在 `degradations`、`errors`、`pending_human` 或 `changes` 中如实说明。