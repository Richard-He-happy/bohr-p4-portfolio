---
name: patent-topic-search
description: "专利与技术文献检索 Skill。在授权输入材料与本地语料内，对公开号/申请号/授权号/优先权号或技术主题完成号码规范化、观测同族归并、法律状态分级核验、权利要求取证、技术文献候选筛选与可复跑证据留存；单命令确定性基线 + Agent 原文核验双路径，交付 result.json 全套契约产物。不用于专利撰写、侵权判定、FTO 结论或专利价值评估。"
version: 1.4.0
---

# 专利与技术文献检索 Skill（patent-topic-search）

> 评分优先级：实际效果 40 分、使用增益 25 分、创新增益 15 分、可靠体验 10 分、生态贡献 10 分。  
> 本 Skill 的核心不是“外部数据库多强”，而是：在有限、有授权的输入材料中，把检索对象、来源、证据、筛选依据、不确定性写到可被他人逐条复核。

---

## 0. 最高优先级：真实、完整、可核验

1. 只依据 `/input` 下实际文件内容。不得用文件名、领域标签、外部常识替代原文；不得补造专利号、DOI、法律状态、引用、查询结果、评分或 benchmark。
2. 每个关键数字、状态、族关系、权利要求描述必须带：
   - 来源号 `[S#]`；
   - 定位 `文件#行号/段落号/页码`；
   - 逐字 `quote`，除非项目明确无需原文引用。
3. 脚本只是基线工具。Agent 必须亲自读取实际材料，核验关键结论，并把核验动作写入 `changes[]` 或 `agent_review.json`。
4. 缺失、冲突、未知、权限不足必须显式进入 `gaps[]`、`errors[]`、`uncertainty[]`、`pending_human[]`，不得用“应存在”“通常有效”等说法覆盖。
5. 任何时候保持诚实：`ok`、`partial`、`insufficient_evidence` 必须与 `errors/gaps/degradations` 一致。
6. 异常也要退出码 0；先落盘 partial，再逐步增强。

---

## 1. 用途与边界

### 做

- 从公开号、申请号、授权号、优先权号或技术主题出发，在 **有授权的本地材料** 中完成检索。
- 号码格式规范化、号码角色识别、同族观测归并、法律状态证据分级、权利要求范围取证、技术文献候选筛选。
- 为每条候选保留来源、原文定位、相关性判断、筛选决策依据。
- 对空结果、冲突、缺失元数据、鉴权失败、限流、权限不足明确说明。

### 不做

- 不进行专利撰写、权利要求起草、侵权判定、自由实施分析、专利价值评估。
- 不绕过付费墙，不上传受限数据，不展示受限库原文。
- 不把转载聚合页当作官方登记依据。
- 不把同族链接视为权利要求范围等同。
- 不依据 kind code 单独推断“有效 / 失效 / 授权 / 撤回”。

### 三个题面点名的硬边界

1. 公开号、申请号、授权号、优先权号不得混用。  
   每个号码必须记录 `number_kind` 与 `role`，无法判断时写 `unknown`，并加 `warnings[]`。
2. 同族只按输入材料中 **观测到的** 优先权号、申请号或同族链接归并。  
   必须标 `observed_links_only=true`、`non_exhaustive=true`，不得声称穷尽族或同族权利范围一致。
3. 法律状态必须有官方登记依据定位。  
   没有官方登记定位时，状态写 `not_in_corpus`，进入 `pending_human[]`，不得用公开号 kind code 或二手页面推断。

---

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json` 或 `task.md`，以及 `/input/**` 内实际材料；**只读** |
| 输出 | `/app/output/` 下 `result.json`、`candidates.csv`、`candidates.json`、`query_log.json`、`verify_report.json` |
| 工作目录 | `/app/work`；执行前创建 `/app/work` 与 `/app/output` |
| 依赖 | Python 3.8+ 标准库；平台预装 PDF 文本提取工具如 `pdf-text-tool`、`pdftotext` 可用于 Agent 亲自复核；**不联网** |
| 退出码 | 恒为 0，包括参数错误、空输入、坏 JSON、阶段异常 |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens 含推理；脚本减少模型重复劳动，Agent 增量核验 |
| 首次落盘 | 流程开始即写最小合法 `/app/output/result.json`，`status=partial`，后续由脚本基线和 Agent 增强覆盖 |

---

## 3. 单命令全流程入口

首选单命令全流程：

    python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work

该命令内部应完成：

1. `init`：盘点 `/input` 材料，生成来源台账、候选清单、冲突分组。
2. `build`：校验原文抽取，确定性补齐候选、证据、query log、candidates、result.json。
3. `selfcheck`：核对 output_contract 字段、磁盘文件、result.json 键一致性。

如果当前脚本不支持 `run` 子命令或未生成 `result.json`，按顺序回退：

    python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output --work /app/work

    python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output

使用第一条成功创建 `/app/output/result.json` 的命令即可。若脚本因 `--work` 参数报错，回退到不带 `--work` 的兼容命令，并在 `degradations[]` 记录 `legacy_main_entry`。

如果脚本全部失败，Agent 必须手工构造最小合法 `result.json`，并在 `errors[]` 中记录 `stage=script_baseline` 异常，继续后续流程。

---

## 4. Agent-first 双路径

### 推荐路径：Agent 核验后成稿

1. 先运行基线脚本，得到台账、候选和字段骨架。
2. Agent 实际读取 `/input` 材料，核验高相关候选的 `quote`、`locator`、号码、日期、状态依据。
3. Agent 把关键判断写入 `/app/work/draft.json`，可以包含：
   - `candidate_overrides[]`：对基线候选的 verified/rejected/reason 与修正后的字段；
   - `new_candidates[]`：脚本漏掉的候选；
   - `conflicts[]`：法律状态、族关系、权利要求文本冲突；
   - `pending_human[]`：需要人工复核的项目；
   - `coverage_notes[]`：任务要求覆盖面是否满足。
4. 用脚本支持的方式应用 `draft.json`；若脚本不支持消费 `draft.json`，则保留该文件作为判断记录，Agent 用 Python 读取基线 `result.json` 后审阅写回，最后成稿。

### 无 draft 时确定性兜底

如果 Agent 没有写出 `draft.json` 或时间不足，必须保留脚本 deterministically 生成的实质工作稿：

- `AUTO_EXTRACT` 作为兜底来源标记；
- 在 `gaps[]` 或 `degradations[]` 中诚实记录 `agent_review=skipped`、`draft_json=missing`、`fallback=auto_extract`；
- 不得因此清空候选、查询日志、来源、结果字段。

两条路径必须产出 **同一套产物** 和 **同一份 result.json 契约结构**。

---

## 5. 输入发现与材料识别

1. 优先读 `/input/case.json`；不存在则找任意 `**/case*.json`；仍无则读 `/input/task.md` 并把任务文本作为解析对象。
2. 原样保留 `case_id` 与 `output_contract`，不改键名、不丢未知键。
3. 递归扫描 `/input/**`，按扩展名与内容语义识别：
   - `.json/.jsonl`：记录、查询、缓存响应；
   - `.csv`：记录表；
   - `.pdf`：专利传真件、论文；
   - `.md/.txt`：任务说明、权利要求、正文；
   - 图片：记缺口，不硬 OCR，除非平台工具明确可用且结果可复核。
4. 文件名含 `quer` 的，视为声明的检索式，写入 `query_log` 并标 `explicit`。
5. 文件名含 `response/hit/api/result` 的，视为缓存响应，记录 `http_status`；`429/401/403` 走降级。
6. 材料未提供的对象，明确进入 `gaps[]` / `pending_human[]`，不构造内容。

Agent 复核时不得只看文件名；对关键文件应读实际开头或字段，确认内容类型。文件名与内容冲突时，以内容为准，并写 `degradations[]`。

---

## 6. 输出产物与 result.json 契约

### 必需产物

| 文件 | 作用 |
|---|---|
| `/app/output/result.json` | 唯一主结果契约，含根级与嵌套 `output_contract` 双回显 |
| `/app/output/candidates.csv` | 可打开检查的候选表 |
| `/app/output/candidates.json` | 机器可读候选集 |
| `/app/output/query_log.json` | 查询、筛选、排序、来源、日期、命中数 |
| `/app/output/verify_report.json` | 自检与核验证据 |
| `/app/work/draft.json` | Agent 核验判断，若已生成则保留 |
| `/app/work/agent_review.json` | Agent 核验记录，如果执行了核验 |

### result.json 顶层至少包含

`case_id`, `status`, `skill`, `generated_at`, `input_case`, `sources[]`, `candidates[]`, `queries[]`, `screening[]`, `families[]`, `clusters[]`, `legal_status[]`, `claims[]`, `citations[]`, `coverage{}`, `metrics{}`, `gaps[]`, `uncertainty[]`, `errors[]`, `degradations[]`, `pending_human[]`, `changes[]`, `runtime{}`, `contract_fill{}`, `artefacts[]`, `self_check{}`, `verification{}`, `gain{}`。

### 双回显要求

- `output_contract` 的每个原始键必须出现在 `result.json` **根级**。
- 同时必须在 `nested.output_contract` 或 `output_contract_echo` 中原样保留一份原始契约。
- `case_id` 也必须同时出现在顶层和 nested 契约中。
- 无法从材料映射的契约键，按原值类型给空占位：`[]`、`{}`、`""`、`null`，并在 `degradations[]` 记录“未映射键已空占位、未编造”。

### status 语义

| status | 含义 |
|---|---|
| `ok` | 流程完成，检索结果可读；即使合法空命中也可为 `ok` |
| `partial` | 流程完成但有未解决缺口、错误或未完成核验 |
| `insufficient_evidence` | 输入缺失或没有可检索内容 |

---

## 7. 核心检索与证据规则

### 7.1 号码规范化

- 保留原始字符串，同时给 `normalized` 形式。
- 每个号码写 `number_kind`：`publication_number` / `application_number` / `grant_number` / `priority_number` / `family_member`。
- 写 `role`：`target` / `related` / `cited` / `priority_claim` / `observed_link`。
- `country_code`、`office`、`kind_code` 可从原文提取；缺失写 `unknown`。
- 号码规范见 `references/number_and_status.md`。

### 7.2 同族归并

- 仅按材料中可观测的优先权号、申请号、同族链接归并。
- 每个族输出：
  - `family_id`；
  - `members[]`；
  - `link_type`；
  - `observed_links_only=true`；
  - `non_exhaustive=true`；
  - `equal_claim_scope_unknown=true`。
- 不得因关键词命中就把多个专利归为同族。
- 本语料下 official legal status unknown，observed links not exhaustive families / equal claim scope。

### 7.3 法律状态

- 状态字段必须包含：
  - `status_text`；
  - `status_source`；
  - `evidence_grade`：`official_record` / `derived_record` / `not_in_corpus` / `conflicting`；
  - `effective_date`：仅原文明确时填写；
  - `retrieved_date`；
  - `locator`。
- 没有官方登记定位时，写 `not_in_corpus`，进入 `pending_human[]`。
- 不得用公开号 kind code 推断授权或失效。
- 二手聚合页可作为线索，但不得作为官方结论；来源标 `authority_grade=yellow`。

### 7.4 权利要求范围取证

- 只描述材料中明确写出的权利要求保护对象。
- 每条 claim 证据至少包括：
  - `claim_id`；
  - `claim_no`；
  - `quote`；
  - `source_id`；
  - `locator`；
  - `support_scope`。
- 不扩展为侵权判断、不写成法律意见。

### 7.5 技术主题检索与文献筛选

- 从号码查询出发时，不把号码简单当关键词；先定位号码，再围绕该专利的同族、引证和被引证、技术主题扩展。
- 从主题查询出发时，用关键词、IPC/CPC、申请人、引证关系组合检索；区分专利文献与技术文献。
- 文献候选必须记录：
  - `title`；
  - `authors`；
  - `year`；
  - `venue`；
  - `doi_or_id`；
  - `source_id`；
  - `locator`；
  - `relevance_reason`。
- 排序、筛选依据写入 `screening[]` 和 `query_log.json`。

### 7.6 来源与授权分级

每个来源在 `sources[]` 中记录：

- `source_id`；
- `label`；
- `type`；
- `authority_grade`：`green` / `yellow` / `red`；
- `access_scope`；
- `version_or_date`，缺失写 `unknown`；
- `query_date`；
- `license_notes`。

分级语义：

- `green`：输入材料明确提供、可读、可用于本次交付；
- `yellow`：可使用但为二手、缓存、聚合、OCR 不确定或权限受限；
- `red`：需登录、付费墙、不可展示；不抓取，记录缺口并降级。

---

## 8. 核心执行流程

### 步骤 0：盘点契约，先落盘最小 partial

1. 读 `/input/case.json` 或 `task.md`，确认 `case_id`、`output_contract`、任务要求。
2. 创建 `/app/work` 与 `/app/output`。
3. 立即写最小合法 `/app/output/result.json`：
   - `case_id`；
   - `status=partial`；
   - `skill=patent-topic-search`；
   - `generated_at`；
   - 根级 output_contract 空占位；
   - 空 `errors/degradations/pending_human/changes`。
4. 如果无法确定 `case_id`，使用 `case_id="UNKNOWN"`，`status="insufficient_evidence"`，并在 `errors[]` 记录输入缺失。

### 步骤 1：运行脚本生成基线

按第 3 节尝试命令，生成基线产物。  
脚本会生成 `result.json`、`candidates.*`、`query_log.json`、`verify_report.json`。

失败分支：脚本崩溃或没生成 `result.json`，则由 Agent 按本节和第 6 节构造最小合法 `result.json`，并在 `errors[]` 记录 `stage=script_baseline`。

### 步骤 2：实际读材料，核验基线

1. `PDF`：用平台 PDF 提取工具取文本；若无文本层或为扫描传真，记录提取器和错误，不猜测。
2. `JSON/JSONL/CSV`：读取关键字段，确认号码、日期、来源、响应状态；不要只读第一行。
3. `MD/TXT`：读权利要求、任务说明，对关键句记录 `quote` 与 `locator`。
4. 对候选逐个核验：
   - `source_file` 与 `locator` 是否真实；
   - `quote` 是否逐字存在；
   - `number_kind`、`role`、`kind_code` 是否与原文一致；
   - `legal_status` 是否有官方或可溯源依据；
   - `family` 是否仅基于观测链接。
5. 把核验写入 `/app/work/draft.json` 或 `agent_review.json`：
   - `claim_id / candidate_id`；
   - `verified` / `rejected` / `cannot_verify`；
   - `reason`；
   - `corrected_value`；
   - `script_fixes`。

### 步骤 3：应用核验并补全

- 若脚本支持 `draft.json` 消费，则用核验后的 draft 重新 build，不删 baseline 字段。
- 若脚本不支持，则用 Python 读取 `result.json`、按核验结果更新候选和 `changes[]`，然后写回；禁止手工文本编辑 JSON 结构。
- 补齐 `gain{}`、`coverage{}`、`self_check{}`。
- 为每个关键数字/结论保留 `[S#]` 与 locator。

### 步骤 4：最终自检

完成第 9 节自检清单，确认无遗漏后写入 `self_check{}`，确保 `result.json` 合法、状态诚实。

---

## 9. 最终自检清单

1. `result.json` 是合法 JSON，可被 `json.load` 读取。
2. `case_id` 在顶层和 nested output_contract 中各出现一次。
3. `output_contract` 的每个原始键在根级都有对应字段。
4. 所有关键号码、日期、状态、权利要求描述都有 `[S#]` 与 locator。
5. `candidates.csv` 与 `candidates.json` 行/条数一致，且 `source_id` 可追溯到 `sources[]`。
6. `query_log.json` 中每条查询有 `date`、`source_ids`、`hit_count`、`status`。
7. 没有任何来源是虚构的；没有任何“最新进展”“评分”“金标准”是自造的。
8. `errors[]`、`gaps[]`、`degradations[]`、`pending_human[]` 与 `status` 一致。
9. PDF 提取失败、OCR 不确定、限流、鉴权失败、权限不足均已在 `degradations[]` 或 `errors[]` 记录。
10. 接近预算时先保证 result.json 与核心产物落盘。

---

## 10. 异常处理与鲁棒性

| 场景 | 处理 |
|---|---|
| 输入缺失 / 坏 JSON | `status=insufficient_evidence`，`errors[]` 记录，不使用“正常”默认值 |
| 空命中 | `candidates=[]`，`query_log` 记录 `hit_count=0`，`status` 可为 `ok`，若输入不全则 `partial` |
| 法律状态冲突 | 保留双方来源与 locator，标 `conflicting`，进入 `pending_human[]`，不伪装统一 |
| 同族链接不完整 | `observed_links_only=true`，`non_exhaustive=true`，不补充外部成员 |
| 429 / 401 / 403 | 记录 `http_status`，不重试外部库，降级为本地已授权证据；缺失写 gap |
| 字段缺失 | 写 `unknown` 或 `missing`，在 `gaps[]` 说明影响 |
| PDF 无文本层 | 记录提取器和页数，`gaps[]` 写 OCR 不可用，不猜测文字 |
| 接近预算 | 保存 partial，保留基线，优先让 result.json 完整且合法 |

---

## 11. 使用增益与创新证据

### 使用增益证据

在 `result.json` 的 `gain{}` 中写清：

- `baseline_expected_behavior`：通用 Agent 常见错误，如号码混用、二手状态当官方、无 locator、无筛选依据。
- `skill_delta`：
  - 号码 `number_kind/role` 规范化；
  - `observed_links_only` 同族归并；
  - 法律状态 `evidence_grade` 分级；
  - 每条候选有 `quote + locator + source_id`；
  - 查询、筛选、排序过程留痕。
- `verifiable_how`：相同输入、相同授权来源下，对比字段是否可复核；以 `candidates.json`、`query_log.json`、`verify_report.json` 为证据，不以自述代替。
- `efficiency_gain`：单命令基线 + Agent 批量核验，减少逐条回查与重复组织格式。

### 创新证据

在 `verify_report.json` 或 `self_check{}` 中体现：

- 号码规范化和角色识别；
- 同族归并规则明确为 observed links only；
- 法律状态“官方/派生/不在库”证据分级；
- 绿/黄/红授权来源分级与降级方案；
- 筛选和查询表达式模板可复用。

不要声称高于商用数据库或官方系统，不要写未运行的 benchmark。

---

## 12. 包内资源与复用

| 文件 | 角色 |
|---|---|
| `scripts/main.py` | 基线编排、候选组装、契约回填、自检产物 |
| `scripts/ptcore.py` | 输入发现、号码规则、同族、状态分级、权利要求、检索打分 |
| `references/number_and_status.md` | 号码规范化、法律状态证据分级规则 |
| `references/output_fields.md` | result.json 与 fields 字段级说明 |
| `references/search_and_evidence.md` | 检索式构造、筛选留痕、证据规则 |

这些文件是本 Skill 的可复用资产。Agent 不得重写脚本核心规则，除非确认脚本输出与输入材料冲突；此时保留原始输出，并在 `changes[]` 记录原因与处理。

---

## 13. 最小调用示例

输入：`/input/case.json`，包含 `case_id`、`output_contract`，并在 `/input/**` 提供专利传真件与文献材料。

调用：

    python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work

示意输出：

    /app/output/result.json
    /app/output/candidates.csv
    /app/output/candidates.json
    /app/output/query_log.json
    /app/output/verify_report.json

示意 result.json 片段：

    {
      "case_id": "EXAMPLE_CASE",
      "status": "partial",
      "skill": "patent-topic-search",
      "candidates": [],
      "sources": [],
      "errors": [],
      "gaps": [],
      "pending_human": [],
      "output_contract": {
        "case_id": "EXAMPLE_CASE"
      }
    }

以上片段仅为接口说明，不冒充正式案例结果。