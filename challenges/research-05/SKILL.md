---
name: research-topic-novelty-appraisal
description: 科研选题与创新性评估 Skill。把研究设想推进为可决策的四件交付：问题定义、已有工作比较、创新点识别、可行性判断；每条判断绑定 S# 来源与逐字 quote/locator；离线、纯标准库、单命令全流程；支持 Agent 草稿路径与无草稿确定性兜底；任何异常也保证合法 partial 并 exit 0。
version: 2.0.0
license: MIT
---

# 0. 最高执行约定（先读）

1. 你必须在 `/app/output` 产出合法 `result.json` 及题面要求的全部产物。脚本保下限，Agent 做上限；不得只跑脚本就交差，也不得空谈方法论而没有实际交付。
2. 输入事实只来自 `/input` 下的实际文件：`case.json`、`task.md`、材料原文。**不依据文件名、领域标签、题面关键词补造内容**；PDF 必须读实际文本层，不能假设原文。
3. 不编造文献、DOI、数值、统计量、实验条件、评分。材料缺失/无法判断必须写入 `gaps`、`pending_human`、`insufficient` 或 `not_found_in_provided_materials`，绝不写成“尚无人研究”。
4. 任何异常都必须保存已有产物、写清 `errors`/`degradations`、保证 JSON 可解析，并以 `exit 0` 结束。官方预算 64 次模型请求、900 秒、单次 16384 tokens，必须节约。
5. 只引用本包真实存在的文件：
   - `/skills/weekly-skill/scripts/appraise.py`
   - `/skills/weekly-skill/scripts/assess.py`
   - `/skills/weekly-skill/references/method.md`
   - `/skills/weekly-skill/references/output_schema.md`
   - `/skills/weekly-skill/references/report_template.md`

---

# 1. 本 Skill 做什么

把模糊研究设想推进为四个互证交付：

| 交付 | 必须产出 |
|---|---|
| `problem_definition` | 研究对象、关键变量、结局、比较基线、预期结论、可证伪条件 |
| `prior_work_comparison` | 按任务/方法/数据/评价方式/结论建比较矩阵，标不可比原因 |
| `novelty_assessment` | 每条创新陈述分类：方法/数据/场景迁移/结论修正；逐条判定是否被已有材料覆盖 |
| `feasibility` | 数据、算力、实验条件、时间窗口、人员能力前提核查；给出带条件结论与失败风险 |

同时必须覆盖六类内容：问题拆解、检索协议、证据回链、冲突证据、综合结论、研究空白。

---

# 2. 单命令全流程入口

运行基线全流程：

    mkdir -p /app/work /app/output
    cd /app/work
    python3 /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output

`appraise.py` 是基准执行入口，至少实现 init→build→baseline selfcheck 的确定性下限。该脚本必须尽快先跑完，让所有盘上产物先存在。

随后立即做确定性自检：

    python3 /skills/weekly-skill/scripts/assess.py --check --output /app/output --input /input

基线产物至少包括：

- `/app/output/result.json`
- `/app/output/research_report.md`
- `/app/output/evidence_map.csv`
- `/app/output/comparison_matrix.csv`

Agent 不能把基线直接当最终成品。基线跑完后必须继续做材料核验、关键证据逐字核对、四项交付增强、契约双回显与 `assess.py --check`。

---

# 3. 双路径工作方式

## 3.1 Agent 路径（优先）

1. 先盘点输入与契约，读取全部材料，形成来源台账。
2. 亲自阅读关键原文段落，把判断写入 `/app/work/draft.json`。
3. `draft.json` 中每条判断必须带：
   - `source_id`：如 `S1`
   - `locator`：如 `S1#p3`、`S1#para7`、`S1#rec12`
   - `quote`：原文逐字连续子串，空白折叠后不少于 12 字符
   - `strength`：`directly_supported` / `inferred` / `insufficient`
4. 然后运行 `appraise.py`、`assess.py`，将 `draft.json` 作为 Agent 增强与 `changes` 记录依据，合并进最终产物。

## 3.2 无草稿确定性兜底（必须成立）

如果没有 `draft.json`，或 Agent 尚未写完，`appraise.py` 仍必须基于来源台账确定性抽取证据、生成实质工作稿：

- 每条关键陈述仍要有 `quote` 和 `locator`
- 自动抽取内容必须诚实标记为 `AUTO_EXTRACT`
- 自动抽取造成的未核验/未决项写入 `degradations` 或 `pending_human`
- 两条路径最终必须落到同一套产物和同一份 `result.json` 契约

---

# 4. 执行流程（必须顺序完成）

## Phase A：init——盘点输入与契约

1. 读 `/input/case.json`。若解析失败，尝试修复 JSON；仍失败则从 `/input/task.md` 提取题面。
2. 识别字段接受同义键：`case_id`、研究主题、研究设想、创新陈述、时间窗、纳排规则、`output_contract`。
3. 扫描 `/input` 下所有材料，忽略 `case.json`、`task.md`，形成 `source_inventory`：
   - `source_id`：按稳定顺序编号 `S1`、`S2`……
   - 相对路径、扩展名、大小、解析方式、文本可读性
   - 同名或重复内容按 sha256 去重
4. 保存 `output_contract` 原样，作为后续双回显依据。

阶段输出建议落盘：

- `/app/work/inventory.json`
- `/app/work/contract.json`
- `/app/work/source_manifest.json`

## Phase B：解析材料，建立源级文本

按扩展名真实解析：

- PDF：提取实际文本层；无文本层标记 `no_text`，进 `degradations`，不 OCR、不猜测。
- DOCX：作为 zip 提取 `document.xml` 文本；损坏则写 `docx_unreadable` 到 `errors`。
- CSV/TSV/TXT/MD/JSON：直接读取；RIS 按题录解析。
- 图片：记录为 `degradations`，不推断文字。
- 不支持格式：记录 `degradations`，继续处理其他材料。

所有文本按段落/页/记录切块，使用 `p./para./rec./blk.` 定位。

## Phase C：Agent 判断写入 draft.json

Agent 必须基于实际阅读形成：

- 四项交付初稿
- 检索协议：检索词、筛选标准、纳排规则；材料外检索标为 `executed:false`
- 证据表：来源、定位、引文、立场、强度
- 冲突证据：同一问题相反结论的双方 quote 与 locator
- 空白：材料未覆盖的内容
- 可行性前提：哪些有来源，哪些标为 `assumed_not_documented`

## Phase D：build 与基线生成

运行：

    python3 /skills/weekly-skill/scripts/appraise.py --input /input --output /app/output

`appraise.py` 生成完整基线。Agent 随后：

1. 抽查至少 5–10 条关键 quote，确认在原文中逐字可查。
2. 对冲突、空白、创新点覆盖、可行性前提逐条复核。
3. 如有修正，用 Python 标准库更新 JSON，不手改键名，不回退成文本粘贴。所有修正写入 `changes`。
4. 需要增强的正文型产物 `research_report.md` 可亲自改写，但内容必须来自材料且每个数字、引用、论断有证据定位。
5. 禁止生成自评分数、金标准、`golden_standard`、`diff_report`、加权自评分；只能引用 `assess.py` 的真实检查输出。

## Phase E：自检

运行：

    python3 /skills/weekly-skill/scripts/assess.py --check --output /app/output --input /input

核对：

1. `output_contract` 每个字段都进入 `result.json` 顶层，并在 `result.json.output_contract` 原样出现一次。
2. 缺省类型：list→`[]`，dict→`{}`，其他→`null`；未知字段保留。
3. `result.json`、`research_report.md`、`evidence_map.csv`、`comparison_matrix.csv` 均存在。
4. 可编辑 Office/slide/diagram 要求时，`/app/output/previews/` 下必须有真实渲染的 PDF/PNG，并在 `artifacts` 登记。
5. `status` 与 `pending_human`/`errors`/`gaps` 一致。

## Phase F：finalize

回填并保存最终 `result.json`：

- `case_id` 正确
- `output_contract` 双回显完成
- `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 真实
- `runtime`：开始/结束时间、耗时、模型请求预算估算
- `tool_call_trace`：记录 appraise.py、assess.py、材料解析、关键文件读打开等实际动作
- `artifacts`：列出每个产物相对路径
- `reviewed_by_agent`：说明核验范围与结论

即使异常也要保存 partial 后退出 0。

---

# 5. `result.json` 必备字段与铁律

必含顶层键，键名不得改：

`case_id`, `status`, `research_product`, `evidence`, `claims`, `evidence_matrix`, `comparison_matrix`, `conflicts`, `gaps`, `search_protocol`, `coverage_metrics`, `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`, `runtime`, `tool_call_trace`, `output_contract`, `artifacts`, `consistency_check`, `reviewed_by_agent`

另加 `auto_extracted` 标记是否为无草稿确定性兜底。

`status` 枚举：

- `ok`：无缺口、无 pending、无错误
- `partial`：存在缺口或错误但已交付可复核部分
- `insufficient_evidence`：材料不足以支撑结论
- `input_error`：输入缺失或不可解析

只有真正无缺口才能写 `ok`。

`output_contract`：必须保留原对象；其字段必须在顶层同步出现一次。若 `output_contract` 本身含 `case_id`，顶层 `case_id` 与之一致。

---

# 6. 证据与来源规则

- 每条关键判断必须有 `source_id` + `locator`。
- 引文 `quote` 必须是原文逐字连续子串，空白折叠后 ≥ 12 字符。
- `locator` 示例：
  - `S3#p4`
  - `S2#para11`
  - `S1#rec8`
  - `S4#blk17`
- `strength` 只允许：
  - `directly_supported`
  - `inferred`
  - `insufficient`
- 材料中没有 → `not_found_in_provided_materials`，绝对不能写成“尚无人研究”。
- 冲突证据必须保留双方 quote 与 locator，写 `resolution`/`needs_human`。
- 可行性前提要有来源；无来源标 `assumed_not_documented`。
- 检索协议中，未执行的外部检索必须 `executed:false`。

---

# 7. 输出文件清单

- `result.json`：始终存在，合法 JSON。
- `research_report.md`：完整、可读、有证据定位的评估报告。
- `evidence_map.csv`：证据表，至少含 `evidence_id`, `source_id`, `locator`, `quote`, `stance`, `strength`。
- `comparison_matrix.csv`：已有工作比较矩阵，含纳排理由与不可比原因。
- 如题面要求可编辑 Office/slide/diagram，必须同时提供真实渲染 PDF/PNG 预览，放在 `/app/output/previews/`，并在 `artifacts` 登记。

---

# 8. 预算策略

脚本执行不消耗模型请求，务必先跑 `appraise.py` 生成全套基线并立即落盘。模型请求优先用于：

1. 真实阅读材料、核验关键引文。
2. 推导四项交付、冲突裁定、空白清单。
3. 校验契约、修复 `assess.py` 不过项。

参考分配：

- init + 基线 + 材料解析：2–6 次模型请求
- 阅读关键材料与证据核验：15–25 次
- 四项交付推导与报告改写：15–25 次
- 自检与 finalize：5–10 次

硬性收尾条件：

- 达到 55 次模型请求，或耗时超过 800 秒：立即跳过非关键增强，执行 finalize。
- `assess.py --check` 失败且 3 次请求内无法修复：保留 partial，列明缺失，退出 0。
- 基线生成后必须至少有一次完整 `result.json` 落盘，之后每完成一个交付物再更新一次。

---

# 9. 异常处理清单

| 异常 | 应对 |
|---|---|
| `/input/case.json` 缺失 | 从 `task.md` 提取题面；`status=input_error`；继续尝试解析材料 |
| `output_contract` 缺失 | 按 §5 默认字段回填；不报致命错误 |
| PDF 无文本层 | 标 `no_text`；进 `degradations`；不 OCR |
| DOCX 损坏 | 标 `docx_unreadable`；进 `errors`；继续处理其他材料 |
| 材料为空 | `status=insufficient_evidence`；只输出协议与空白清单 |
| 证据冲突 | `conflicts` 登记双方 quote/locator，写 resolution/needs_human |
| 证据引文无法在原文找到 | 删除或修正该证据及关联 claims；不允许不可追溯结论 |
| 输出目录不可写 | 尽量写 `/app/work` 临时文件后重试；最终失败也要有 `errors` 并退出 0 |
| 可编辑产物渲染失败 | 保留源文件；`errors`/`degradations` 写明预览失败 |
| 任何未捕获异常 | 捕获后写 `errors`，保存 partial，退出 0 |

---

# 10. rubric 得分动作自查

| 维度 | 必须做到 |
|---|---|
| 实际效果 40 | 四项交付齐全且一致；真实文献；正确比较对象；创新点逐条覆盖判定；可行性前提带来源或标假设；六类内容齐备；每条判断可回原文 |
| 可核验性 | `claims[].evidence_ids` 可追溯；`evidence_map.csv` 每行有 locator+quote；`assess.py --check` 可独立复跑 |
| 使用增益 25 | 一键基线；双路径一致；`changes` 记录 Agent 增量；`reviewed_by_agent` 写明核验动作；不假装全自动 |
| 创新增益 15 | 逐字 quote 定位；冲突双方保留；`coverage_metrics` 明确覆盖/空白；`pending_human` 明确不越界；方法细节在 `references/method.md` |
| 可靠体验 10 | 单命令可触发；异常不停摆；partial 仍可复核；无隐藏外部依赖；纯标准库、Python 3.8+离线运行 |
| 生态贡献 10 | `references/method.md` 写方法依据；`references/output_schema.md` 写字段契约；`references/report_template.md` 写报告版式；本 SKILL.md 写调用、输入输出、限制、失败处理、自查 |

---

# 11. 最终收尾清单

- [ ] 已真实读取 `/input/case.json`、`/input/task.md` 和至少一篇核心材料原文
- [ ] 已跑 `appraise.py --input /input --output /app/output`
- [ ] 已跑 `assess.py --check --output /app/output --input /input`
- [ ] `result.json` 合法且含全部必填顶层键
- [ ] `output_contract` 在顶层和 nested `output_contract` 各出现一次
- [ ] 每个关键数字/论断有 `S#` 和 `文件#行号/段号/记录号`
- [ ] `quote` 均为原文逐字连续子串
- [ ] 冲突、空白、不确定性均已落盘
- [ ] 没有伪造文献、DOI、数值、评分或软件状态
- [ ] 若需可编辑产物，已生成真实预览并登记
- [ ] `status` 诚实；非 `ok` 时已列明 limits
- [ ] 即使异常也 `exit 0`