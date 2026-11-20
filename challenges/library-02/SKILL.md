---
name: research-file-library
description: 科研文件库的入库与检索 Skill。扫描文件库（PDF/Word/Excel/PPT/TXT/CSV/图片），产出逐文件清单、重复组、版本链、章节级索引；按提问做硬过滤检索，返回逐字引用与可核验回链。脚本生成基线，Agent 必须亲自读材料并完成最终推导与核验。
version: 2.0.0
license: 供本赛题提交与复用；脚本仅用 Python 标准库
---

# research-file-library（科研文件智能检索：整理文件，也保留版本关系）

## 0. 关键声明：谁在完成这份成果

本 Skill 提供 `scripts/main.py` 与 `scripts/engine.py` 作为**工具与基线生成器**。最终提交的 `result.json`、`inventory.csv`、`version_chain.json`、`operations.log` 以及所有可编辑/渲染预览，必须由你（Harness Agent）**亲自阅读 `/input` 实际材料、真实解析内容、核对证据、撰写或修正后产出**。禁止把脚本原始输出、模板、文件名猜测或领域标签直接当作成品；脚本未覆盖的字段与判断必须由你补齐，并在 `result.json.reviewed_by_agent` 中留痕。

## 1. 用途与边界

**做**：把一个已经存在的文件库整理成可交接的清单，保留版本与重复关系，然后按提问在**文件内容**里做语义检索，把命中落到**章节/页码/段落/工作表行/幻灯片**，给出逐字引用与可复核回链，并把无法处理的文件如实记入失败与待人工清单。

**不做**：不联网、不做开放文献检索、不读扫描件像素（无 OCR）、不解析 `.doc/.xls/.ppt` 等旧式二进制 Office、不判断底层存储权限策略、不生成或补写任何材料里没有的数据。

**适用**：文件已在本目录、需要“哪一版写了什么、在哪一段”的可核验回答。  
**不适用**：需要 OCR 的纯扫描库（只能入库不能检索）、跨库联邦检索、改写原文类任务。

## 2. 运行契约与目录约定

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json` 与 `/input/task.md`，材料在 `/input/**`（可用 `--input` 覆盖） |
| 工作目录 | `/app/work`；Agent 的中间笔记与核验草稿放这里 |
| 输出 | `/app/output/`（可用 `--output` 覆盖） |
| 入口 | `python3 scripts/main.py --help` 查看用法 |
| 退出码 | **恒为 0**；失败只体现在 `result.json` 的 `status`/`errors`/`pending_human` |
| 顺序 | 任何重活之前先写 partial `result.json`，收尾无条件覆盖为最终版 |
| 依赖 | Python 3 标准库；`scripts/engine.py` 由 `main.py` 用 `Path(__file__).resolve().parent` 定位导入，不依赖 CWD |
| 规模 | 单库数千文件、秒级完成；`--max-files` 默认 4000 |
| 产物 | `result.json`、`inventory.csv`、`version_chain.json`、`operations.log`；若题面要求可编辑 Office/幻灯片/图形，还须额外给出真实渲染的 PDF/PNG 预览 |

## 3. 输入发现、输出契约与字段

### 3.1 输入发现（按语义，不假设键名）

1. 在输入根递归找 `case*.json`；优先 `case.json` / `input.json` / `task.json`。
2. `case_id` 依次尝试 `case_id`/`caseId`/`case`/`id`，均无则用输入目录名；**原样保留**。
3. `output_contract` 原样取出（dict 或 list-of-dict 均支持），末尾回填。
4. 提问按语义在整棵 JSON 里找：键名含 `query/question/ask/request/检索/提问/问题`（拉丁词按**整词**匹配，`text` 不会被当成 `ext`）；值可为字符串、对象（取 `text/query/question/内容`）或列表。
5. 材料按**魔数优先、扩展名其次**识别（`%PDF`、`PK\x03\x04`、OLE、PNG/JPEG/TIFF），不靠文件名猜内容。
6. 组织方备注/别名：键名含 `note/alias/rename/metadata/version/admin/备注/别名` 的字典或列表，按文件名或路径子串匹配后作为权威覆盖写入，`meta_sources` 记 `case_note`。

### 3.2 输出契约与顶层字段

- `result.json`：`output_contract` 每个键都在，**键名不改、未知键保留**，语义能对上的填对应结果，对不上的填 `null`（列表类为 `[]`）；原始契约另存 `output_contract_spec` 便于复核。
- 同目录写 `inventory.csv`（每文件一行）、`version_chain.json`（版本链 + 重复组）、`operations.log`（制表符分隔的操作轨迹）。
- `result.json` 顶层还包括：`files`、`directories`、`duplicates`、`version_chains`、`queries`、`failures`、`skipped`、`permissions`、`pending_human`、`errors`、`degradations`、`counts`、`verification`、`runtime`、`sources`、`uncertainty`、`change_records`、`reviewed_by_agent`、`status`。
- 字段细则见 `references/output-schema.md`。

## 4. 本题专属执行流程（必须逐条执行）

### 步骤 0：读取任务与契约，先落盘 honest partial

- **输入**：`/input/task.md`、`/input/case*.json`
- **动作**：
  1. 读取 `task.md` 与 `case.json`（若多个，选 `case.json` 或语义最明确的）。
  2. 提取 `output_contract`、`case_id`、问题列表、材料路径、组织方备注/别名。
  3. 在 `/app/output/result.json` 写入 partial skeleton：`status=partial`，包含 `case_id`，把 `output_contract` 的每个键填入 `null` 或空结构；同时写入 `errors`/`degradations` 初值。
  4. 建立 `/app/work/working_notes.md` 记录任务要点与后续动作。
- **输出**：`/app/work/working_notes.md`、`/app/output/result.json`（partial）
- **失败分支**：读不到 `case.json` 时，`case_id` 用输入目录名，`output_contract` 记空对象，继续执行；任何读取异常写入 `errors`，但仍写 partial。

### 步骤 1：盘点输入并真实解析材料（含运行基线脚本）

- **输入**：`/input` 目录
- **动作**：
  1. 递归列出文件，忽略符号链接，记录大小、权限、魔数。
  2. 对每个可解析文件**真实解析**：PDF 用平台提供的 `pdf-text-tool` 或 `scripts/engine.py` 抽取文本层；DOCX/XLSX/PPTX 用标准库/可用工具抽取段落/行/幻灯片；TXT/CSV 直接读；图片只记录元数据不 OCR。
  3. **同时运行基线**：`python3 scripts/main.py --input /input --output /app/output`，生成全套基线四件套。
  4. 将基线输出视为起点，不要直接当最终答案；把解析到的关键内容摘入 `/app/work/parsed_materials.md`。
- **输出**：基线 `result.json`、`inventory.csv`、`version_chain.json`、`operations.log`；Agent 解析笔记
- **失败分支**：单个文件无权限、损坏、加密 PDF、无文本层扫描件、旧式 Office 等，写入对应 `permissions`/`failures`/`pending_human`，**不阻塞整体**；若基线脚本本身异常，继续步骤2，Agent 需手工构建关键字段。

### 步骤 2：构建与核对证据（Agent 亲自验证）

- **输入**：基线产物与解析笔记
- **动作**：
  1. 核对文件哈希、路径、大小、元数据与出处是否真实来自材料内容或 `case_note`；不得根据文件名/领域标签猜测。
  2. 核对重复组（同 sha256）与版本链（项目号 + 去版本化文件名 + 版本标签/mtime 排序），识别 `version_conflicts`、`timestamp_anomaly`。
  3. 对每个提问的硬过滤条件逐项核对；过滤不可满足时依然保持空命中，写入 `queries[].notes`，不放松。
  4. 对基线给出的每条检索命中，**亲自回到原文验证 `locator` 与 `quote` 是否逐字存在**；凡不一致，设置 `quote_verified=false`，并记入 `pending_human`，不改写原文凑数。
  5. 把核验结论写入 `change_records` 和 `reviewed_by_agent`。
- **输出**：`/app/work/evidence_checks.md`、更新后的 `result.json` 相关字段
- **失败分支**：证据冲突无法解决时，如实记入 `uncertainty`，并将相关条目标为 `pending_human`；禁止编造引用、分数、数据。

### 步骤 3：Agent 产出完整成品

- **输入**：步骤 2 的核验结果与基线产物
- **动作**：
  1. **保留并增强基线四件套**：补全所有 `output_contract` 字段，确保键名与原契约一致；不得删除或清空基线中的有效数据。
  2. 如题面要求可编辑 Office/幻灯片/图形产物，**生成真实可编辑文件**，并额外渲染 PDF/PNG 预览，放在 `/app/output`；在 `result.json.artifacts` 中记录路径、类型、sha256。
  3. 撰写最终 `result.json` 顶层完整字段，包括 `status`、`counts`、`queries`、`failures`、`pending_human`、`verification`、`sources`、`uncertainty`、`change_records`、`reviewed_by_agent`。
  4. 更新 `operations.log`，追加 Agent 动作（reverify/enhance/render/write）与时间戳。
- **输出**：最终 `/app/output` 交付物
- **失败分支**：无法生成预览或可编辑产物时，保留基线产物，在 `limitations` 说明缺什么；`status` 降为 `partial_with_limitations`，但退出码仍为 0。

### 步骤 4：按 rubric 逐项自检

- **输入**：`/app/output`
- **动作**：对照第 6 节 rubric 对照表逐项核对；检查磁盘文件、`output_contract` 字段、`result.json` 键三者一一对应；缺任何一项先补齐。
- **输出**：`/app/work/self_check.md` 或 `operations.log` 中的自检记录
- **失败分支**：发现缺失立即补齐后再次自检；若时间不足，至少保证 `result.json` 合法且包含全部契约键，并把未完成项写入 `pending_human`。

### 步骤 5：回填 result.json 并收尾

- **输入**：自检通过或降级状态
- **动作**：确保 `output_contract` 全部字段、`case_id`、`status`、`sources`、`uncertainty`、`change_records` 真实存在；最终写入 `result.json`；确保退出码 0。
- **输出**：最终 `result.json` 与全部产物
- **失败分支**：任何异常都由兜底逻辑写合法 `result.json`（可调用 `python3 scripts/main.py --input /input --output /app/output` 重新生成基线再补字段），退出码仍 0。

## 5. 预算策略（64 次模型请求 / 900 秒 / 单次 16384 tokens）

### 5.1 请求分配参考

| 阶段 | 模型请求数 | 说明 |
|---|---|---|
| 步骤 0-1：读任务、盘点、跑基线 | 5-10 | 用较少请求完成，脚本扫描不占模型请求 |
| 步骤 2：核验关键证据与检索引用 | 10-25 | 最高优先级，聚焦 rubric 实际效果 40 分 |
| 步骤 3：补全成品与生成预览 | 10-20 | 确保完整性，可编辑产物与预览 |
| 步骤 4-5：自检与修复 | 5-15 | 逐项核对，修正缺漏 |
| 储备 | 5-10 | 用于失败重试、边缘材料解析、契约字段补充 |

### 5.2 优先级与落盘时机

1. **最高**：完成 `queries` 检索结果、定位与逐字引用、证据回链；这是实际效果 40 分的核心。
2. **次高**：确保 `output_contract` 全部字段和磁盘文件齐全；可用基线填充，再 Agent 增强。
3. **随后**：真实记录 `failures`、`skipped`、`permissions`、`pending_human`、`uncertainty`。
4. **最后**：预览渲染、方法说明、自检记录、文档完整性。

**何时落盘 partial**：步骤 0、1、2、3 结束时都覆盖写 `result.json`；每个阶段异常都 try/except 捕获并写入 `errors`，不因单点失败丢光成果。

**避免无意义消耗**：不重复运行脚本；不一次性读超大文件全文；单个 PDF/Office 只解析必要的页/段；使用 `--skip-verify` 时可跳过脚本复核，但 Agent 必须亲自核验关键命中的 `quote`。

## 6. rubric 维度 → 交付要求 → 自证方式对照表

| rubric 维度 / 评分点 | 交付要求 | 自证方式（落在 result.json / 磁盘文件） |
|---|---|---|
| 实际效果 40：任务完成度 15 | 完成文件盘点、版本关系、索引、检索、证据回链全流程；不是只做文件名搜索 | `status=ok` 或 `partial_with_limitations`；`counts` 显示文件数、查询数、命中数；四件套产物存在 |
| 实际效果 40：结果正确性 15 | 命中文件与章节真正回答提问，定位落在原文那一段，引用与元数据真实 | 每个 `queries[].hits[]` 有 `locator`、`quote`、`quote_verified=true`；`verification.checks` 记录重抽取结果 |
| 实际效果 40：结果完整性 5 | 覆盖提问要求的关键文件、关键章节、关键元数据与全部过滤维度 | `inventory.csv` 每文件一行；`queries[].filtered_out`/`notes` 记录过滤影响面；`files` 列表完整 |
| 实际效果 40：结果可核验性 5 | 检索路径、文件与版本标识、章节定位、引用片段可独立复核 | `locator_hint`、`backlink`、`artifacts[].sha256`、`verification.checks`；`operations.log` 记录操作 |
| 使用增益 25：质量增益 15 | 相比基础 Agent 提升命中率、定位准确性与回链可靠性 | 章节级 `locator`（页/段/行/幻灯片）+ 逐字引用 + 版本/重复标注；不是文件名命中的结果 |
| 使用增益 25：效率增益 5 | 减少人工翻文件、核对页码、比对版本与去重时间 | 一次运行同时给出清单、版本链、检索与复核；`runtime` 记录耗时 |
| 使用增益 25：增益可验证性 5 | 通过公平对照证明改善 | `reviewed_by_agent` 记录 Agent 增强点；`verification` 说明独立重抽取与手动核验 |
| 创新增益 15：新增能力 5 | 具备基础 Agent 不具备的跨文件语义对齐、章节级定位、硬过滤执行、回链校验 | `queries[].hits[]` 的定位类型与 `quote_verified`；`filters` 硬约束执行 |
| 创新增益 15：方法改进 5 | 切分/索引/检索/过滤/定位/回链方法有实质改进 | `references/method.md` 描述方法；`verification` 展示哈希去重、版本链、章节继承等 |
| 创新增益 15：创新证据 5 | 用真实文件集证明创新点边界与价值 | `queries` 结果中体现跨文件命中、章节定位、硬过滤不可满足时的空结果 |
| 可靠体验 10：调用与易用性 3 | Agent 能正确触发，用户能按说明完成一次检索 | `python3 scripts/main.py --help`；SKILL.md 调用示例；步骤清晰 |
| 可靠体验 10：运行稳定性 4 | 不同文件类型、目录规模、重复运行下持续给出可用定位 | 魔数识别、异常分支、`status`/`errors`/`degradations`；同一输入重复运行结果确定 |
| 可靠体验 10：异常处理 3 | 识别并处置无权限、加密、无文本层、重名、空结果、路径失效 | `permissions`、`failures`、`pending_human`、`skipped`、`errors` 各字段；`queries[].notes` |
| 生态贡献 10：文档完整性 3 | 使用说明、依赖、目录约定、元数据字段、定位规则、示例与维护信息齐全 | 本 SKILL.md、`references/output-schema.md`、`references/method.md`、`references/example.md` |
| 生态贡献 10：资源可复用性 4 | Skill 本体、脚本、题集、目录模板、分类与元数据金标准可复用 | `scripts/main.py`、`scripts/engine.py`、`references/` 全部文本文件 |
| 生态贡献 10：分享推广价值 3 | 沉淀可分享的题集、元数据规范、案例和经验 | 文件清单与版本说明；`references/example.md` 标记为示例 |

## 7. 隐藏案例鲁棒性与降级

| 情形 | 识别 | 处置 | 记录位置 |
|---|---|---|---|
| 无 `case.json` | 找不到 case 文件 | 继续全量扫描，`case_id` 用目录名 | `errors` + `degradations