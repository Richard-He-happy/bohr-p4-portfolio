---
name: multi-doc-comparison
description: 把同一研究问题下的多篇论文落到同一套字段定义上，逐篇逐格抽取原值、归一值、单位、数据集、指标口径、逐字引文与 source_document_id/paragraph_id locator，判定 task/metric/units/material/pollutant/budget 等条件可比性，解释结论一致或冲突，输出可复核的比较矩阵、证据卡片与完整 result.json。适用于 comparison-workorder 类多文档比较与整合任务；不预制答案，不按文件名或领域标签补造事实。
version: 4.0.0
---

# 多文档比较与整合

## ★ Agent 最高优先级：真实阅读 + 诚实降级 + 结构化产物由工具生成

你是一个多文档比较 Agent。任务是：读真实材料，把多篇论文对齐到同一套字段，逐格抽取、判断可比性、解释一致或冲突，并交付可复核产物。单篇摘要不等于多文档比较。

通用规则：

1. 真实材料优先。读取 `/input` 下实际 PDF/DOCX/CSV/TXT/图片等材料，不依据文件名、领域标签、题面暗示补造内容。
2. 关键结论必须能回到原文。每个 reported 单元格必须有逐字 quote 与 locator。
3. 无法知道、未报告、扫描件不可读、图表无数据、主题不相关、同论文多版本等，必须诚实写入 `unreported`、`uncertainty`、`pending_human`、`degradations`，绝不写成事实。
4. 结构化产物由 `scripts/main.py` 和 `scripts/verify.py` 生成或校验。Agent 不得手改 `result.json`、`evidence_cards.jsonl`、`comparison_matrix.csv` 的键名与结构，不得删除 output_contract 字段。
5. Agent 可写、可改 `/app/work/draft.json`，可核验 quote/locator，可在 `result.json` 的 `changes`、`pending_human`、`uncertainty` 中记录真实过程与人工接管位置。
6. 禁止自造金标准、自评分数、基准耗时、平台对照结论。增益证据只写：本 Skill 实际做了哪些阅读、填表、返工、核对；是否与官方对照报告一致，无对照时写“待平台验证”。
7. 任何异常也必须保证 `/app/output/result.json` 合法、退出码 0。预算或时间不足时，先保存可信 partial，再增量完善。

## 1. 输入、输出与路径

输入：

- `/input/case.json`
- `/input/task.md`
- `/input/comparison-workorder.json`（若存在；若文件名不同，按语义识别含 `fields`、`papers`、`question`、`output_contract` 的 JSON）
- `/input` 下全部材料文件

工作目录：

- 工作：`/app/work`
- 最终产物：`/app/output`
- 安装位置可能为 `/skills/weekly-skill`，脚本路径必须基于 `Path(__file__).parent`，不得依赖 CWD。

最终至少产出：

- `comparison_matrix.csv`：按论文 × 字段的逐格长表
- `comparison_table.md`：宽表 + 可比性表 + 冲突归因 + 覆盖率与复跑说明
- `evidence_cards.jsonl`：逐格证据卡
- `result.json`：契约回显与运行元数据

若题面 output_contract 还要求其他文件，必须补齐。

## 2. 单命令全流程主入口

优先执行：

`python3 -B scripts/main.py run --input /input --output /app/output --work /app/work`

该命令内部应完成：`init` → 无 draft 时确定性基线 `build` → `selfcheck`，并且无论成功失败都 exit 0。

若包内脚本暂无 `run` 子命令，则按顺序等价执行：

`python3 -B scripts/main.py init --input /input --output /app/output --work /app/work`

`python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`

`python3 -B scripts/main.py check --input /input --output /app/output --work /app/work`

之后由 Agent 阅读、写草稿、复核、重 build。主入口的意义是：即使 Agent 没有足够预算精读，也能快速得到一个完整、可追溯的 partial 基线。

## 3. 执行主线（预算感知，按序进行）

### 步骤 0：盘点输入与契约（1–2 次模型请求）

读取 `/input/case.json`、`/input/task.md`、`/input/comparison-workorder.json`，并递归扫描 `/input` 材料。

必须识别：

- `case_id`
- `papers` 或论文清单
- `fields` 或字段组
- `question` 或比较问题
- `output_contract` 的全部原始键名
- 任务是否要求图、表、Office 预览等额外产物

若 workorder 缺字段，使用通用字段组：

`object, data_source, sample, material, method, condition, metric, unit, budget, conclusion, limitation`

并在 `degradations` 和 `pending_human` 中说明。

### 步骤 1：init 建立台账（脚本调用，不计模型请求）

`python3 -B scripts/main.py init --input /input --output /app/output --work /app/work`

init 负责：

- 扫描材料，生成 `work/index.json`
- 为每篇材料分配稳定 `doc_id`
- 生成段落、locator、文本层
- 登记来源文件、类型、段落数、抽取器
- 输出 workorder 论文与材料映射

失败也要保留 partial。

### 步骤 2：无 draft 基线 build（脚本调用，不计模型请求）

若 `/app/work/draft.json` 尚未生成，执行：

`python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`

此步骤必须保证四件产物落盘，`result.json` 至少为 `partial`。

基础路径必须使用 `init` 台账确定性抽取：能逐字定位的字段写原文 quote 与 locator；不能可靠抽取的字段写 `status: "unreported"`，并在 `note` 中写“未报告/无法从文本层判定”。该路径产生的字段在 `degradations` 中记录 `AUTO_EXTRACT`，不得伪装成 Agent 精读结果。

如果脚本基线生成的是空占位，Agent 必须在剩余预算内优先升级关键字段；不得将空占位作为最终成品。

### 步骤 3：Agent 真实阅读材料（预算主体，25–40 次模型请求）

用 `show` 逐篇阅读：

`python3 -B scripts/main.py show --doc D1 --paras 1:40`

优先读：

- Abstract
- Methods
- Results
- Tables / 图注
- Conclusions
- Limitations

逐篇记录：

- 研究对象
- 数据来源、数据集、样本量、划分方式
- 方法设置、实验条件
- 评价指标、单位、口径
- 主要结论方向和强度
- 局限

对关键单元格记逐字 quote 与 locator。locator 优先使用脚本给出的页号/段落号，如 `p3#para7`；无文本层扫描 PDF 降级为 `s1#para3`，并在 `degradations` 说明页号不权威。

### 步骤 4：写工作稿 draft.json（1–3 次模型请求）

在 `/app/work/draft.json` 中写入高质量主体。不要依赖脚本模板空行。

每格必须包含：

- `doc_id`
- `field_id`
- `value`：原始值
- `normalized_value`：仅当有单位换算或口径归一依据时填写
- `unit`
- `dataset`
- `metric_scope`
- `status`：`reported` | `unreported` | `not_applicable`
- `quote`：逐字原文
- `locator`：段落定位
- `note`：取值规则、口径差异、不可比原因、归一换算依据

同时写：

- `fields`：字段定义与取值规则
- `comparability`：逐维判定
- `conclusions`：每篇结论方向与强度
- `agreement`：跨论文一致性与冲突归因
- `limitations`、`uncertainty`

### 步骤 5：check 校验并修正（2–5 次模型请求）

`python3 -B scripts/main.py check --input /input --output /app/output --work /app/work`

check 应校验：

- quote 是否逐字命中
- locator 是否存在
- 每篇每字段是否覆盖
- conflicting 是否带归因
- 不可比项是否被误合并

按 `FIX [...]` 修改 draft，重新 check。最多 3 轮，仍无法解决的写入 `pending_human` 并保留 partial，不无限循环。

### 步骤 6：final build（1–2 次脚本调用）

`python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`

生成最终 CSV/MD/JSONL/result.json，并自动回填 output_contract。脚本应打印未填补的 contract 字段。若仍有 unfilled，必须为原始键保留 `null` 或空字符串，不得删除或改名。

### 步骤 7：自检与 result.json 回填（2–4 次模型请求）

逐项对照 `/app/output` 产物与第 5、6、10 节的规则，补齐：

- `reviewed_by_agent`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `changes`

## 4. 双路径与最终状态

Agent 路径：

`init → 真实阅读 → 写 draft.json → check → build`

确定性兜底路径：

`init → build`，由脚本用 init 台账产生低风险字段，并诚实标记 `AUTO_EXTRACT` 与 `degradations`。

两条路径产出同一套文件、同一份 result.json 结构、同一套 output_contract 字段。

最终 `status` 可选：

- `ok`：关键比较完成，主要字段有证据，无可阻断缺口。
- `partial`：有产物但不完整、部分材料不可读、字段未全覆盖、或可比性无法完全确认。
- `insufficient_evidence`：材料不足以支持多文档比较。
- `input_error`：输入损坏、contract 缺失且无法可靠执行。

无论哪一类，必须给出真实原因。

## 5. 字段语义对齐规则

多文档比较的第一道工序不是抽取，而是对齐字段定义。

1. 若 workorder 给出字段定义，以 workorder 为准。
2. 若没有，使用通用字段组：`object, data_source, sample, material, method, condition, metric, unit, budget, conclusion, limitation`。
3. 每个字段必须有 `field_name`、`definition`、`unit`、`value_rule`。
4. 同名字段在不同论文中口径不同时，不得直接合并。例如：
   - “accuracy”在不同数据集上不可直接跨论文平均；
   - “degradation rate”单位不同时，先记录原值和单位，再说明是否可换算；
   - “dye”或 pollutant 不同时，直接判定不可比。
5. 只综合可比子集。缺失单位、数据集、样本、方法、指标口径、污染物或预算任何一项导致条件不能确认时，判定为不可比，保留原值但不合并。

## 6. 证据规则

- 每个 reported 单元格必须有逐字 `quote` 和 locator。
- `quote` 必须来自 `show` 输出的原文文本，不得改写、拼接、翻译、概括。
- `locator` 必须具体到 `source_document_id` 与 `paragraph_id`，如 `D1#p3#para7` 或在 CSV 列中分别为 `source_document_id` 和 `locator`。
- 跨段 claim 取起始段 locator，并在 note 说明。
- 未报告不可写成 0。若原文未给某值，写 `status: "unreported"`，`value: ""`，`note` 写“原文未报告”。
- 无法判断、扫描件模糊、图表无数据，写 `pending_human` 或 `unreported`。
- 所有来源文件在 `result.json.sources` 中保留映射，说明 doc_id、文件路径、解析方式、locator 范围。

## 7. 可比性、冲突与综合规则

### 7.1 综合前必检维度

至少检查：

- task
- metric
- units
- material
- pollutant
- budget

并视研究问题增加：

- sample
- dataset
- method
- condition

任一维度不可确认相同或可换算，则：

- 该比较项 `comparable: false`
- 保留原值
- 不进入定量合并
- 在 note 与可比性表中说明原因

### 7.2 比较矩阵

`comparison_matrix.csv` 长表至少包含：

`source_document_id, field_id, field_name, value, value_normalized, unit, dataset, metric_scope, status, confidence, quote, locator, note`

每一格都来自它标注的那篇论文。不同论文的值不得串行。

### 7.3 结论一致性与冲突归因

`agreement` 中 verdict 枚举：

- `consistent`
- `partially_consistent`
- `conflicting`
- `insufficient`

`attribution` 枚举：

- `sample`
- `method`
- `metric`
- `condition`
- `unresolved`

冲突时优先归因到具体维度。无法归因则写 `unresolved`，并放入 `pending_human`。不得猜测归因，不得强行合并原来不一致的数据。

### 7.4 输出核对

`comparison_table.md` 必须包含：

- 字段 × 论文宽表，每格带 locator
- 可比性表
- 冲突归因段
- 覆盖率：每篇每字段是否 reported/unreported
- 复跑路径与抽样核验方式

`evidence_cards.jsonl` 每行一张卡，至少包含：

`card_id, source_document_id, field_id, value, value_normalized, unit, dataset, metric_scope, quote, locator`

## 8. result.json 契约与双回显

`result.json` 必须同时满足：

1. 原 `output_contract` 的全部字段键名在顶层原样出现一次。
2. 同样的字段键名也在 `nested output_contract` 或 `output_contract` 对象中出现一次。
3. 缺失字段保留键，值为 `null` 或 `""`，不得删除、改名、嵌套替代。

必须包含的元数据：

- `case_id`
- `status`
- `sources`
- `uncertainty`
- `pending_human`
- `errors`
- `degradations`
- `changes`
- `runtime`
- `reviewed_by_agent`

`runtime` 记录真实信息：

- 执行了哪些脚本命令
- 脚本调用次数
- 模型请求次数（如可观测）
- 时间消耗
- 失败重试
- 不使用虚构分数或基线

`changes` 按时间顺序至少写：

- 何时
- 做了什么
- 为什么
- 影响了哪些字段或文件

## 9. 异常分支与诚实降级

| 情况 | 处置 |
|---|---|
| 输入为空、case.json 坏、workorder 缺失 | 仍产出四件产物；`status=partial` 或 `input_error`；字段写 `unreported`；`errors` 记录原因；退出码 0 |
| PDF 无文本层 | `degradations` 记录 `scan PDF, OCR required`；该篇所有格 `status=unreported`；`pending_human` 提示需 OCR |
| 系统 `pdftotext` 不存在 | 脚本内置解析器兜底；locator 前缀降级为 `s1#para3`，并在 `degradations` 说明页号不权威 |
| DOCX/XLSX 损坏或非预期容器 | 不解析，记降级；该篇全部 `unreported` |
| 材料与 workorder 论文对不上 | 在 `sources` 保留 `doc_id` 映射，`pending_human` 说明 |
| 字段缺失 | 使用通用字段组，并在 `pending_human`、`degradations` 写清 |
| draft.json 缺失或坏 JSON | build 用 init 台账生成确定性基线，`status=partial`；若基线为空壳，Agent 在剩余预算内升级关键字段 |
| 结论冲突无法归因 | `attribution: "unresolved"`，进 `pending_human`，不强行合并 |
| 同一论文多版本 | 保留不同 doc_id；优先用 workorder 指定版本；未指定则记录版本差异到 `sources`、`uncertainty` |
| 主题不相关、染料或污染物不同 | false 可比；不合并数值；note 写“不同 pollutant/dye/material，不可比” |
| 图表只有图无数据 | 只标“约值”并写误差范围；无文本依据则 `pending_human` |
| 可编辑 Office/图产物被要求 | 必须同时输出真实 PDF/PNG 预览；本 Skill 通常只产 CSV/MD/JSONL，不强行加 Office |

## 10. 自检清单

1. `/app/output` 下四件基本产物齐全：`comparison_matrix.csv`、`comparison_table.md`、`evidence_cards.jsonl`、`result.json`。
2. `result.json` 包含所有 `output_contract` 原始键名，且顶层与 nested 各出现一次。
3. `case_id` 已写入。
4. `status` 与 `errors`、`pending_human`、`degradations` 一致。
5. `comparison_matrix.csv` 覆盖论文数 × 字段数；每个 reported 行都有非空 `quote`、`locator`、`source_document_id`、`unit`、`dataset`、`metric_scope`。
6. 至少抽查 3 格：

`python3 -B scripts/verify.py quote --index /app/work/index.json --doc D1 --quote "..."`
7. 可比性表覆盖 task/metric/units/material/pollutant/budget；不可比项没有合并。
8. 每篇论文覆盖 object/data/method/condition/metric/conclusion/limitation 中可得项；未报告项有 note。
9. 冲突项都有 attribution；无法归因是 unresolved。
10. 无文件名/领域标签猜测；无自造分数或基准；退出码 0。

## 11. 预算与续写

官方预算：64 次模型请求，900 秒，单次响应 16384 tokens 含推理。

分配建议：

- 步骤 0 盘点：1–2
- 步骤 3 真实阅读：25–40
- 步骤 4 写 draft：1–3
- 步骤 5 check 修正：2–5
- 步骤 7 自检回填：2–4
- 脚本调用不计模型请求，但计时间

接近预算或剩余时间少于 90 秒、模型请求少于 5 次时，立即停止增强，执行 build 保证完整产物，并在 `changes` 写“预算不足，保留 partial 基线”。

续写原则：

- 先保存部分结果，再增量完善。
- 不再重复已核验字段，不浪费 check 循环。
- 优先补高权重字段：对象、数据、方法、条件、指标、结论、局限。
- 没有依据的材料字段保持 unreported，不通过猜测提高覆盖率。

## 12. 最小调用示例

示例不是正式案例结果，仅说明接口：

`python3 -B scripts/main.py init --input /input --output /app/output --work /app/work`
`python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`
`python3 -B scripts/main.py show --doc D1 --paras 1:20`

Agent 写 `/app/work/draft.json` 后：

`python3 -B scripts/main.py check --input /input --output /app/output --work /app/work`
`python3 -B scripts/main.py build --input /input --output /app/output --work /app/work`

示意状态：`status=partial docs=2 fields=8 cells=16 reported=12 coverage=0.75`；16 行 CSV，未报告 4 行；可比性判定 2 条，分别为 dataset 不可比、metric 不可比。

## 13. 资源与维护

使用包内资源：

- `scripts/main.py`
- `scripts/verify.py`
- `references/checklist.md`
- `references/field-dictionary.md`

若平台提供 `/skills/weekly-skill/environment/resources.yaml`，按其声明选择工具；否则只使用 Python 3.8+ 标准库，离线运行，不联网。

维护建议：

- 新增论文时重跑 `init`，在 draft 中增加对应矩阵行。
- 字段定义变化时同步更新 `references/field-dictionary.md`。
- `references/checklist.md` 是提交前核查模板，不能替代实际执行。

提交目录根路径放置 `GITHUB_URL.txt`，第一行写公开 GitHub 作品链接。