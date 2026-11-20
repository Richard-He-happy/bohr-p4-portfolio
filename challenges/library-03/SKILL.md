---
name: library-auto-organizer
description: >-
  科研文献资料自动分类整理 Skill。用单命令完成输入盘点、来源编号、候选抽取、冲突分组、分类/标签/命名/去重/版本链生成、可回滚复制落库、清单与操作日志、自检和 result.json 契约回填。
  Agent 可先阅读真实材料并把判断写入 draft.json 增强；未提供 draft 时脚本确定性兜底抽取，但绝不编造元数据。适用于 topic library-03 的文献与资料自动分类任务。
version: 3.0.0
license: MIT
---

# 科研文献资料自动分类整理

## 0. 最高优先级规则（每次运行前先读）

1. 本 Skill 不输出“整理建议”，必须实际完成输入盘点、分类、标签、命名、去重、版本区分、批量落库与可复核清单。
2. 默认唯一入口：
   python3 -B scripts/organize.py run --input /input --output /app/output --work /app/work
3. 该命令内部完成 init → build → selfcheck。任何异常都必须被抓取并 finalize 为 partial，最终 exit code 必须为 0。
4. 如果包内没有 scripts/organize.py，使用回退入口：
   python3 -B scripts/organize.py --input /input --output /app/output
   python3 -B scripts/verify.py --input /input --output /app/output
   回退时也必须保证产物与 result.json 契约完整。
5. Agent 可以先运行 init 查看台账，阅读真实材料，把自己的判断写入 /app/work/draft.json，再执行 build；没有 draft.json 时，build 必须用 init 台账确定性兜底生成实质工作稿，并把 AUTO_EXTRACT 诚实写入 gaps/degradations。
6. 所有源文件只读。移动、重命名、删除一律只作用于 /app/output/library 内的副本。不得以任何理由改写 /input。
7. 所有字段缺失都必须显式写成 null、[]、unknown 或 pending_human，不得补造作者、年份、DOI、期刊、引用、金标准、白板结果或 benchmark 分数。
8. 最终 /app/output/result.json 必须存在且合法，包含 case_id 和 output_contract 双层回显。

## 1. 用途与边界

使用本 Skill：任务要求对科研文件进行组织、元数据整理、版本维护、检索或知识沉淀，输入为混合源的 PDF、预印本、会议论文、学位论文、补充材料、数据集、扫描件、CSV、DOCX、TXT 等，输出必须可复核、可回滚、可交接。

不使用本 Skill：只要求总结单篇论文观点、翻译、写作润色、生成检索式、补充参考文献，或要求联网验证 DOI 真伪。本 Skill 离线运行，DOI 只作为文本证据使用，不进行联网确权。

## 2. 运行时契约

| 项 | 约定 |
|-|-|
| 输入 | /input/case.json、/input/task.md 以及 /input 下递归发现的全部材料与 artifacts |
| 工作目录 | /app/work，用于台账、draft、候选、冲突、auto_draft、自检中间文件 |
| 最终输出 | /app/output |
| 源文件策略 | 只读；落库采用复制；rollback.sh 只删除 library 内副本，不触碰源文件 |
| 依赖 | 仅 Python 3.8+ 标准库；离线；不依赖当前工作目录 |
| 退出码 | 无论成功、部分完成还是异常，最终 exit 0 |
| 预算 | 64 次模型请求，900 秒，16384 tokens/response；脚本不与模型请求争抢 token，优先用确定性兜底 |

## 3. 单命令全流程：init → build → selfcheck

### 3.1 init：盘点、来源编号、候选抽取、冲突分组

init 必须完成以下动作：

1. 读取 /input/case.json；若不存在，则递归查找 case*.json；仍失败则只做目录扫描，并记录 pending_human.case_json_repair。
2. 保留 case_id、原始 output_contract 或 result_contract，按语义读取 task_instruction、organizer_workorder、organizer_supplied_scope 等键。
3. 递归扫描 /input/**，跳过符号链接和 __MACOSX，按魔数优先、扩展名兜底判定类型。至少识别 PDF、JPEG、PNG、DOCX、XLSX、PPTX、CSV、UTF-8 文本。
4. 为每个材料文件分配来源编号 S1、S2、S3…。case.json 与 task.md 属于控制文件，可进入清单但 role=reserved，不落库、不分类。
5. 计算并记录每个来源的 sha256、size、mtime、权限、可读状态、文本可提取状态。
6. 抽取候选元数据和候选标签，记录每一条候选的来源位置 /path#page/paragraph/line，不得只基于文件名。
7. 生成 /app/work/init_manifest.json、candidates.json、conflicts.json、source_index.json。
8. 对候选之间的冲突进行分组：同名不同哈希、同 DOI 不同版本、同标题不同年份、同哈希不同文件名等。

### 3.2 Agent 路径：真实阅读后写 draft.json

Agent 路径不是必须，但能显著提高质量。执行方式：

1. 先运行：
   python3 -B scripts/organize.py init --input /input --work /app/work
2. 阅读 init_manifest.json、candidates.json、conflicts.json。
3. 真实打开关键材料：每个分类目录至少 1 个代表文件，每个版本链至少 1 个成员，每个去重组至少 1 对，每个 pending_human、errors、degradations 相关材料，以及所有 confidence=low 材料。
4. 对读到的标题、作者、年份、DOI、摘要、正文首段与 init 候选逐条核对。核对结论必须引用原文 locator 和原文摘录 quote。
5. 将判断写入 /app/work/draft.json。

draft.json 建议形状如下，字段必须精确定位：

{
  "case_id": "原输入 case_id 或 null",
  "extraction_mode": "agent",
  "entries": [
    {
      "source_id": "S1",
      "path": "/input/materials/example.pdf",
      "sha256": "实际哈希",
      "doctype": "journal_article",
      "classification": {"project": "项目A", "theme": "主题B", "year": "2022", "doctype": "journal_article"},
      "metadata": {"title": "已核验标题", "authors": ["作者1", "作者2"], "year": "2022", "journal": "期刊名或 null", "doi": "DOI或 null"},
      "tags": ["标签1", "标签2"],
      "naming": {"template": "author_year_short_title", "filename": "作者-年份-短标题.pdf", "confidence": "high"},
      "duplicate_of": "S3",
      "version_of": "S4",
      "version_role": "published",
      "keep": true,
      "archived_path": "/app/output/library/20_journal_articles/作者-年份-短标题.pdf",
      "evidence": [
        {"source_id": "S1", "locator": "/input/materials/example.pdf#page=1", "quote": "原文标题", "assertion": "title"}
      ],
      "confidence": "high"
    }
  ],
  "conflicts": [
    {"source_ids": ["S1", "S3"], "type": "duplicate_content", "decision": "keep_published", "evidence": []}
  ],
  "pending_human": [],
  "rejected_auto": []
}

draft.json 中每一条决策都必须能回到 source_id 和 locator。不能只写结论。

### 3.3 build：校验、兜底抽取、渲染全部产物、finalize result.json

build 必须：

1. 读取 /app/work/draft.json。
2. 如果 draft.json 存在且通过 schema 校验，则优先使用 draft；如果不存在、不合法或字段不完整，则使用 init 台账确定性兜底生成 auto_draft.json。
3. 确定性兜底抽取必须达到“实质工作稿”水平：
   - 逐文件给出 classification、metadata、tags、naming、duplicate_of、version_of 候选；
   - 每条关键字段必须有逐字 quote 和 locator；
   - 无法可靠确认的字段写 null、unknown 或 pending_human；
   - 冲突项必须显式进入 conflicts，禁止静默覆盖、删除或猜测保留哪一份。
4. 如果 build 使用了兜底抽取，必须在 result.json.summary.extraction_mode 写 "auto"，并在 degradations 或 gaps 中记录 AUTO_EXTRACT 以及原因。
5. 渲染全套交付物到 /app/output：
   - result.json
   - inventory.csv
   - library_manifest.json
   - version_chain.json
   - duplicates.json
   - operations.log
   - rollback.sh
   - library/ 内按分类和命名模板复制后的实际文件
   - verify_report.json
   - deliverable.md，若输出契约要求正文型交付物
6. finalize result.json：
   - 顶层必须包含 status、sources、uncertainty、pending_human、errors、degradations；
   - 原始 output_contract 字段必须同时出现在 result.json 顶层和 result.json.output_contract 内；
   - case_id 必须同时出现在顶层和 output_contract 回显区；
   - 如果原始契约键名与顶层字段冲突，冲突键写入 contract_backfill.base_key_collisions。
7. 所有写文件操作中途失败时，保留已完成的 partial 文件，并将失败写入 errors、pending_human，然后继续尝试 finalize。

### 3.4 selfcheck：产物与契约自检

selfcheck 必须检查：

1. result.json 是否合法 JSON。
2. output_contract 的每个原始键是否在 result.json.output_contract 中保留，未知键是否保留；无值标量是否 null、列表是否 []。
3. inventory.csv 行数是否等于非控制文件材料数。
4. library/ 内每个落库文件是否有清单条目和 staged_sha256，且 staged_sha256 与源文件可复核。
5. operations.log 非注释行数是否等于 result.json.operations.count。
6. rollback.sh 是否只删除 /app/output/library 内副本，不删除 /input。
7. verify_report.json 中的 ok 是否 true。
8. 如果 selfcheck 失败，先补齐可自动修复项，再重新校验；无法修复的写入 errors 或 degradations，并在 result.json.status 中如实降级。

## 4. result.json 契约与双回显

result.json 顶层至少包含：

skill, case_id, status, generated_at, summary, library, inventory, classification, tags, naming, duplicates, versions, operations, metadata, coverage, evidence, sources, uncertainty, errors, degradations, pending_human, changes, runtime, output_contract, contract_backfill

关键要求：

1. status 只能是 ok、partial、needs_human 之一。
2. sources 为 S1..Sn 的来源索引，包含 path、sha256、size、role、read_status、text_status。
3. evidence 中每条证据必须包含 source_id、locator、quote、assertion 和 strength。
4. uncertainty 记录低置信度项，不能把不确定写成确定。
5. errors 记录系统错误、解析失败、哈希不符等。
6. degradations 记录降级与兜底，如 AUTO_EXTRACT、encoding_fallback、pdf_no_text、low_confidence_batch。
7. pending_human 记录需要人工处理的加密 PDF、扫描件无文本层、OCR 需求、命名冲突、缺 DOI 等。
8. output_contract 必须原样保留输入契约的键名，并按同一套值回显到顶层可兼容位置。

## 5. 完整产物要求

除 result.json 外，最终输出应覆盖：

| 产物 | 用途 | 必须满足 |
|-|-|-|
| inventory.csv | 全量文件清单 | 每个材料一行，含 source_id、原路径、sha256、doctype、keep/archive、status |
| library_manifest.json | 落库清单 | 记录 source_id → library 副本路径、staged_sha256 |
| version_chain.json | 版本关系 | 区分 published、preprint、supplement、revised、unknown，记录哪份保留、哪份归档 |
| duplicates.json | 去重关系 | 基于哈希、DOI、标题+作者年份；记录保留项与归档项，不得只靠文件名 |
| operations.log | 操作日志 | 每行一个操作，含复制、跳过、冲突、失败、恢复 |
| rollback.sh | 回滚脚本 | 只删除 /app/output/library 内副本，可重复执行 |
| deliverable.md | 可读成稿 | 干净正文，不堆证据标记；关键数字与论断用 [S#] 标注 |
| verify_report.json | 自检结果 | 含 ok、checks、failed_items |

deliverable.md 中每个关键数字、分类、版本判断、去重结论必须标注 [S#] 来源。来源定位格式采用文件路径#页码/段落号/行号，例如 /input/materials/paper.pdf#page=1。

材料缺失必须显式登记 gaps，不得编造。

## 6. 隐藏案例鲁棒性

### 6.1 正常输入

混合 PDF、DOCX、CSV、TXT、图片，带任务说明和 materials。此时必须产出完整的目录树、元数据、标签、命名、去重、版本链、操作日志和 result.json。重点是每个结论都有原文和哈希可核对。

### 6.2 边界输入

| 情形 | 正确处置 |
|-|-|
| 同名文件但内容不同 | 使用 sha256 区分，不得覆盖 |
| 同内容但文件名不同 | 进入 duplicates 组，保留合适版本，其余归档到 superseded |
| 预印本与正式版共存 | 进入版本链，正式版 role=published 优先保留，预印本 role=preprint 归 superseded |
| 标题相同但年份不同 | 不自动合并，标记为 conflict 或 distinct editions |
| DOI 缺失 | DOI 写 null，不补造，naming 使用作者-年份-短标题降级模板 |
| 作者缺失 | authors=[]，naming 降级为 unknown_author_年份_短标题 |
| 超长标题 | 按规则截断，并在 original_title 保留完整题名 |
| 多语言标题 | 保留主语言标题，其他语言标题写入 alternate_titles |

### 6.3 异常输入

| 情形 | 正确处置 |
|-|-|
| /input 为空 | 生成空清单，status=partial，pending_human.no_materials |
| case.json 缺失或损坏 | 记录 pending_human.case_json_repair，继续目录扫描，case_id 无法恢复则 null |
| output_contract 缺失 | 使用通用 schema 回填，pending_human.contract_absent |
| 加密 PDF | 不尝试破解，置入 90_quarantine，errors.encrypted_pdf |
| 扫描件无文本层 | 置入 30_scans，pdf_no_text，不伪造 OCR 文本 |
| 损坏或零字节文件 | 置入 90_quarantine，read_status=empty |
| 中文乱码 | 回退 GB18030/Big5 并记录 encoding_fallback |
| 权限不足 | 记 unreadable，不落库，pending_human 给出源路径 |
| 复制后哈希不符 | 删除副本并记 errors.staged_hash_mismatch |
| 重复运行 | 同哈希同目标文件已存在则 skipped_exists，保持幂等 |
| 不支持格式 | unsupported_format，pending_human；不伪造内容 |
| 时间或请求预算耗尽 | finalize partial，记录 budget_stop，保存诚实 partial |

## 7. 预算策略

1. 主命令只占用运行时间，不消耗模型请求。first run 应优先让脚本完成 init + 确定性兜底 build + selfcheck，确保 baseline 完成。
2. Agent 模型请求只用于高价值核验，不用于重复全量解析所有文件。
3. 典型分配：
   - 读 case.json、task.md：2–3 次
   - 读 init 台账和冲突：2–4 次
   - 核验关键材料：10–20 次
   - 修正 draft 与结果：4–8 次
   - 收尾自检：2–4 次
4. 当剩余约 15% 时间或模型请求少于 8 次时，停止新增核验，保存已有 review，写 pending_issues，并确保 verify_report 和 result.json 合法。
5. 确定性兜底保证即使 Agent 不做任何增强，也有一份完整、可复核的 partial/ok 成果。

## 8. 五维评分对准与增益证据

### 8.1 实际效果 40 分

- 必须形成真实 library/ 落库副本，而不是只写建议。
- 分类、标签、命名、去重、版本结论均需 quote + locator。
- inventory 必须覆盖输入批次的全部文件，包括控制文件、跳过项、异常项。
- 文件类型、元数据字段、目录层级、重复文件、版本差异、权限与来源六类要素必须逐一交代。

### 8.2 使用增益 25 分

- 在 result.json.summary.work_stats 中记录客观处理量：输入文件数、成功分类数、自动命名数、去重对数、版本链数、跳过/失败数。
- 让 inventory 和 operations.log 足以证明哪些步骤是自动完成、哪些需要人工复核。
- 不写与基础 Agent 的主观比较分数，不编造 benchmark；只写可复核的实际处理量与产物证据。

### 8.3 创新增益 15 分

- 方法上落实：init/build/selfcheck 分离、draft.json 与 AUTO_EXTRACT 双路径、冲突分组、版本链保留策略、哈希去重、可回滚复制。
- 在 deliverable.md 或 method_evidence.md 中说明这些做法相对“只给建议不改文件”的具体差异，但避免夸大。

### 8.4 可靠体验 10 分

- 一条命令可运行；init/build/selfcheck 幂等。
- 对损坏文件、加密 PDF、扫描件、编码、权限、同名不同版本均有明确处置。
- 重复运行结果一致；异常时 exit 0 且保留 partial。

### 8.5 生态贡献 10 分

- 包内应附带 SELFTEST.md、environment/resources.yaml、references/guide.md、references/output_schema.md、references/rules.json。
- SELFTEST.md 给出自检清单和预期输出示意。
- environment/resources.yaml 声明预装依赖、版本、运行假设。
- references/guide.md 说明 draft.json 形状、工作流与失败恢复。
- 不提供隐藏测试答案、不提供正式案例白板。

## 9. 包结构与关键文件

建议包结构如下，总大小不超过 2MB，UTF-8 文本文件不超过 50 个，单文件不超过 500KB，不使用 symlink：

- SKILL.md
- GITHUB_URL.txt
- SELFTEST.md
- environment/resources.yaml
- references/guide.md
- references/method.md
- references/output_schema.md
- references/rules.json
- scripts/organize.py
- scripts/organize.py
- scripts/verify.py

如果 main.py 未打包，SKILL.md 中已给回退命令。无论主命令还是回退命令，最终产品与 result.json 契约必须一致。

## 10. Agent 修改边界

1. 禁止手工重写 result.json、inventory.csv、library_manifest.json、version_chain.json、operations.log 的结构。结构化修正必须通过脚本函数或新增 draft.json 后重新 build。
2. 允许 Agent 新增 /app/output/agent_review.json，记录核验样本、解析方法、发现、纠正项、未解决问题。
3. 允许 Agent 写 deliverable.md 的正文，但关键论断必须能在 evidence 表中找到来源。
4. 所有修正追加到 result.json.changes，每条包含 item、before、after、reason、timestamp。
5. 发现错误但来不及修正时，写 pending_human 和 degradations，不硬改造成更严重错误。
6. 不要生成或引用虚假的 golden_standard、diff_report、加权自评分。自检只依据 verify_report.json。

## 11. 最终收尾清单

结束前逐项确认：

- result.json 存在且合法。
- result.json 顶层包含 case_id 与 output_contract。
- result.json.output_contract 原样回填输入契约字段。
- inventory.csv 覆盖全部源文件。
- library/ 与 library_manifest.json 一致。
- operations.log 可复核、可回滚。
- rollback.sh 不触碰 /input。
- verify_report.json.ok 为 true，或失败项已如实记入 errors/degradations。
- 所有不确定性、缺失、跳过、异常均在 pending_human/uncertainty/gaps 中显式登记。
- exit code 为 0。

完成以上清单后即视为本次 Skill 运行收尾完毕。