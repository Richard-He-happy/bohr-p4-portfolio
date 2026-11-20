---
name: sci-data-cleaning
description: Audit-grade cleaning of scientific tabular data. Classifies missing/censored/sentinel values without statistical imputation, canonicalises numeric/date/unit/encoding faults with recorded reversible transforms, resolves duplicate records under a dictionary-derived key, and emits an analysis-ready table plus a field-level quality report whose numbers are re-derived from the emitted tables. Use when a case supplies dirty CSV/TSV/PDF/DOCX table transcriptions, a data dictionary and a cleaning workorder.
version: 1.3.0
---

# sci-data-cleaning（科研数据清洗与处理）

## 0. 最高优先级：完整性优先（v6）

**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、模板或未审阅的中间产物直接当成品提交。

进入任务后必须先运行本 Skill 自带脚本/流程，产出**全套基线交付物**，再在此基础上做核验与改进。后续改动只能增强基线，不得删除、清空或遗漏任何基线产物与 `output_contract` 字段。若不确定字段含义，保留原产物并在 `result.json` 中记录 `reviewed_by_agent`。提交前必须逐项核对「output_contract 字段 × 磁盘文件 × result.json 键」，任何缺项先补齐再收尾。

## 1. 用途与边界

对给定脏表完成题面约定的**五类处理**，交付可复核证据链：

| 类别 | 本 Skill 做什么 |
|---|---|
| 缺失值 | 区分 `blank / not_detected(ND) / below_LOQ(＜LOD) / sentinel(-999)`，写出缺失原因码，**不做统计填补** |
| 异常值 | 字典物理上下限（硬越界）+ 稳健分布判据（MAD-z，退化到 IQR）双判据，**只标记不删除** |
| 重复记录 | 由字典主键推断复合键；大小写/空格/分隔符/前导零归一后判重；保留最完整记录，其余进 `duplicates.csv` 隔离 |
| 格式/单位/编码 | 千分位、小数逗号、科学计数、脚注符、尾随单位、日期格式、GBK 乱码；换算因子与编码修复全部记录，**可逆** |
| 质量报告 | 字段级问题清单 + 五类汇总，报告数字由 `verify.py` 从产出表反算校验 |

**不做**：统计建模与假设检验、图表美化、数据库运维、实验方案设计、论文写作；不做均值/中位数填补，不推断总体统计量，不填补缺失或无效源值（题面运行时契约明确禁止）。自带脚本只稳定处理 CSV/TSV/TXT；对 PDF/DOCX/图片，必须由 Agent 先用平台工具真实解析出文本/表格，再进入清洗流程，不得跳过或按文件名猜测内容。

## 2. 触发条件

- 用户给出**脏表格 + 数据字典/字段说明 + 清洗要求**，要求交付清洗表、质量报告、可复现证据。
- 用户报告“报告数字与清洗表不一致”“单位/编码不统一”“同一样品重复”“缺失值处理不清”。
- 不适用：只需要画图/建模；只有正文无表格；需要从原始 PDF 推断总体统计量或做统计填补。

## 3. 运行时契约与目录约定

```bash
cd /app/work
python3 /skills/weekly-skill/scripts/main.py --input /input --output /app/output
python3 /skills/weekly-skill/scripts/verify.py --output /app/output
```

- 输入只读 `/input`（含 `case.json`、`task.md`、表格、字典及其他材料），工作目录 `/app/work`，最终产物只写 `/app/output`。
- 若脚本安装在 `/skills/weekly-skill`，使用上述路径；若路径不同，以实际安装目录为准。脚本不依赖 CWD，内部用 `Path(__file__).resolve().parent` 定位 `references/`。
- 纯标准库，不联网、不 pip、无随机种子；行序=源文件行序，浮点 `%.12g`。
- **退出码恒为 0**，失败写入 `result.json` 的 `errors`，不抛栈、不静默。
- 可编辑 Office/幻灯片/图形产物若被产出，必须额外渲染 PDF/PNG 预览；本题通常交付 CSV/JSON/MD，但若平台要求渲染则执行。

## 4. 输入盘点与材料真实解析

1. 读 `/input/case.json`（若无则找 `case*.json`）获取 `case_id`、`output_contract`、`files`、`data_dictionary`、`workorder` 等；键名按去分隔符小写匹配，不假设固定键。
2. 读 `/input/task.md` 获取题目约束、评分要求与输出规定。
3. 递归扫描 `/input`：`.csv/.tsv/.txt/.dat` 是数据表候选；`.md/.json/.docx` 是字典/任务说明候选；`case.json` 本身不是数据表。
4. **真实解析每个材料**：CSV/TSV/TXT 直接读取；PDF 用平台提供的 `pdf-text-tool` 或其他文档解析工具抽取文本/表格，DOCX 用可用解析库抽取表格/段落，图片表格用 OCR 或平台工具识别并复核。将抽取结果保存到 `/app/work/extracted/`，并记录提取方式。
5. 主表选择：`case.json` 中明确提到的文件名优先；否则取行数最多者，其余表登记进 `sources`。
6. 字典优先级：独立字典文件（Markdown 管道表 / JSON / DOCX）→ `case.json` 内联 `data_dictionary/fields/columns/schema`。字段名去标点小写对齐，允许 `NO3_mgL` 与 `no3 mg/l` 匹配。
7. 表头括号内单位（`浓度 (mg/L)`）作为该列单位提示；字典 `unit` 列优先。
8. 若材料缺失、损坏或无法解析：逐条写 `pending_human`，不臆造数据、引用或分数。

## 5. 本题专属执行流程

**步骤 1：盘点输入**
- 输入：`/input/case.json`、`/input/task.md`、目录列表。
- 动作：读取 `case.json` 与 `task.md`，扫描材料，建立文件清单、`output_contract` 字段清单、字典/主键/workorder 候选。
- 输出：输入清单、契约键列表、清洗目标。
- 失败：`case.json` 缺失或坏 JSON → 尝试其他 `case*.json`；仍失败则 `status=input_error` 并继续可处理部分。

**步骤 2：真实解析材料**
- 输入：文件清单。
- 动作：按第 4 节解析每个数据表、字典、workorder；保留源文件 sha256；抽取产物写入 `/app/work/extracted/`。
- 输出：可读取的数据表、字典、workorder；`sources` 哈希表。
- 失败：格式不支持、文件损坏或 OCR 无法识别 → 写入 `degradations`/`errors`，标 `pending_human`，绝不猜测内容。

**步骤 3：运行基线脚本生成全套产物**
- 输入：解析后的材料路径。
- 动作：执行 `scripts/main.py --input /input --output /app/output`，生成基线文件；再执行 `scripts/verify.py --output /app/output` 做一致性校验。
- 输出：`/app/output` 下全集产物 + `result.json` 初稿。
- 失败：脚本异常 → 捕获堆栈写入 `errors`，仍须按输出契约手动生成必要文件，保证 `result.json` 合法。

**步骤 4：Agent 亲自核验证据与推导一致性**
- 输入：基线产物、原始解析材料、字典/workorder。
- 动作：逐列核对字段角色、单位、缺失哨兵、异常阈值是否与字典一致；抽查若干原值→清洗值；核对报告数字是否由表反算；检查重复记录保留是否合理；必要时重新推导补齐缺口。
- 输出：核验记录（`verified`、`pending_human`、`conflicts`）及修订清单。
- 失败：发现不一致 → 修正规则/产物，记录 `changes`；无法判断 → 保留原值并标 `pending_human`。

**步骤 5：产出完整成品并增量改进**
- 输入：核验结果与修订清单。
- 动作：更新清洗表、日志、报告、`result.json`；补齐所有 `output_contract` 字段；若有可编辑 Office 产物则渲染 PDF/PNG 预览。
- 输出：最终 `/app/output` 全套交付物。
- 失败：预算/时间不足 → 保留当前部分结果，标 `status=partial`，列出缺失项。

**步骤 6：自检 rubric 并回填 `result.json`**
- 输入：`/app/output` 与契约字段清单。
- 动作：逐项执行第 9 节自检清单；确认 `result.json` 含 `case_id` 及 `output_contract` 全部键；审核状态、来源、不确定性、变更记录真实；确认退出码 0。
- 输出：合法 `result.json`。
- 失败：契约字段缺失 → 补齐；无法补齐 → 写入 `unresolved_contract_fields` 并标 `partial`，不得删键。

## 6. 预算策略（64 次请求 / 900 秒）

总预算 64 次模型请求，3 个固定案例，单案例目标 **≤20 次请求**。分配如下：

| 步骤 | 请求次数 | 必须/可选 |
|---|---|---|
| 盘点输入 | 1-2 | 必须 |
| 解析材料 | 2-5 | 必须；每个 PDF/DOCX 解析算 1 次 |
| 运行脚本+verify | 1-2 | 必须；脚本不占用模型请求，仅结果读取 |
| 核验关键字段/抽查 | 3-6 | 必须，至少抽查 3-5 组关键原值 |
| 修订与补齐 | 2-4 | 按需，发现不一致才做 |
| 自检回填 | 1-2 | 必须 |

- **尽早落盘 honest partial**：步骤 3 完成后立即保存 `result.json`，确保 `status`、`sources`、`artifacts` 等真实存在。
- 若单案例接近 20 次或运行接近 840 秒，停止改进，保留 partial，无条件 finalize。
- 禁止无意义循环、重复读同一文件或重新清洗无变化数据；无需对所有行逐行人工核验，按字段级和随机抽查即可。

## 7. 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json`，退出码 0。

| 情形 | 处置 |
|---|---|
| `case.json` 缺失/坏 JSON | 扫描其他 `case*.json`；仍失败记 `errors=[CASE_MISSING]`，`status=input_error`，继续扫描目录 |
| 无数据表 | `status=insufficient_evidence`，`pending_human=[NO_TABLE]`，输出空 `result.json` |
| 空表（仅表头） | 正常产出空清洗表与质量报告，`n_rows=0` |
| 无字典/主键/workorder | 键回退整行，只去完全重复；写 `pending_human=[KEY_NOT_FOUND]` |
| 全列缺失 | 该列 `missing_pct=100`，仍出现在 `field_issues.csv` |
| PDF/DOCX/图片无法解析 | 写 `degradations=[UNSUPPORTED_FORMAT]` 或解析错误，提示转 CSV/TXT；不猜测内容 |
| 编码乱码 | 多编码打分 + GB18030 回解，写 `degradations` |
| 单位不明 | 保留原值 + `U2`，写 `uncertainty` |
| 主键冲突且值冲突、日期 `d/m` 与 `m/d` 均合法、`1,234` 千分位/小数歧义 | 保留原值、打标记、写 `pending_human/uncertainty`，不擅自选边 |
| 输出目录不可写 | 依次退到 `./output`、系统临时目录 |
| 超时 | 900 秒内留 60 秒收尾；到 840 秒必须停止一切改进，写入 `result.json` 并退出 |
| 行数超限 | 脚本 `--rows` 控制上限，截断并写 `ROW_LIMIT` |

## 8. 评分维度 → 交付要求 → 自证方式对照表

| 评分维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果 40：任务完成度 15 | 五类处理均有 CSV 列与报告章节，每列都在 `field_issues.csv` | `cleaned.csv`、`field_issues.csv`、`quality_report.md` |
| 实际效果 40：结果正确性 15 | 字段处理符合字典语义与量纲；异常判据与分布匹配；去重主键真实；单位/编码转换无损；报告数字与结果表一致 | 字典驱动规则、`transform_log.csv`、`assertions.json` 反算、`verify.py` |
| 实际效果 40：结果完整性 5 | 覆盖约定五类处理；字段级问题清单；统计假设与图表选择依赖的记录被保留 | `field_issues.csv`、`stats.json`、报告章节完整 |
| 实际效果 40：结果可核验性 5 | 输入、规则、日志、输出可独立复核并复跑 | `__src` 行号、`sources` sha256、`transform_log.csv` 原值、`run.log`、`assertions.json` |
| 使用增益 25：质量增益 15 | 相同输入下比基础 Agent 更少误改、更一致 | 逐字段规则、拒绝统计填补、可逆转换、字典驱动去重 |
| 使用增益 25：效率增益 5 | 减少人工改表与返工 | 一条命令端到端，`run.log` 显示无人工干预 |
| 使用增益 25：增益可验证性 5 | 公平对照证明改善 | `assertions.json` 反算通过、`changes` 记录修订前后差异 |
| 创新增益 15：新增能力 5 | 基础 Agent 难以稳定实现的字段级策略推断、跨表主键对齐、可逆映射、报告一致性自检 | `cleaning_rules.json` + 脚本输出 + 文档说明 |
| 创新增益 15：方法改进 5 | 缺失分类、异常标记策略、近似重复归一、格式映射有实质改进 | `references/skill_guide.md` 方法说明 |
| 创新增益 15：创新证据 5 | 证明创新点相对已有方案的边界与价值 | `references/skill_guide.md` 的适用边界与限制 |
| 可靠体验 10：调用与易用性 3 | 正确触发，按说明完成一次清洗 | SKILL.md 指引、一条命令 |
| 可靠体验 10：运行稳定性 4 | 不同表结构/编码/规模/重复运行稳定 | 标准库、确定性输出、无随机种子 |
| 可靠体验 10：异常处理 3 | 对空表、全列缺失、乱码、单位不明、主键冲突、文件损坏等识别处置 |