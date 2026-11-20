---
name: research-file-library
description: 面向科研文件库的文件组织、版本关系、章节级语义检索与证据回链 Skill。先由确定性脚本生成可复核基线，Agent 必须真实阅读实际材料、核验 quote/locator、补齐 output_contract，并对缺失、失败、权限与不确定性做诚实留痕。适用于 PDF/Word/Excel/PPT/TXT/CSV/图片文件库的可交接整理与检索。
version: 2.2.0
---

# research-file-library（科研文件智能检索：整理文件，也保留版本关系）

## 0. 高分执行摘要（先读）

本 Skill 的目标是完成“文件盘点 → 版本/重复关系 → 章节级索引 → 硬过滤检索 → 逐字证据回链 → 可复核交付”。正式运行必须使用：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 内部按 `init → build → selfcheck` 执行，生成全套基线。Agent 的第一优先级不是重写脚本输出，而是读真实材料、核验证据、补齐契约、诚实记录限制。

关键原则：
- 单命令完成全流程；异常也必须让脚本/收尾写出合法 `result.json`，整体退出码 0。
- 有 Agent 判断时写 `/app/work/draft.json` 改进；无 draft 时走确定性兜底，并在 gaps/degradations 中诚实记录 AUTO_EXTRACT。
- 每个关键结论必须带 `[S#]` 来源与 `文件#页/段/行/幻灯片` locator；没有依据不写。
- `result.json` 的契约字段必须在**顶层**和 `nested output_contract` 中双回显。

---

## 1. Agent 修改边界（最高优先级）

1. **可以修改**：
   - 真实读 `/input` 实际文件，核验脚本抽出的 `quote`、`locator`、哈希、版本关系是否与原文一致。
   - 把核验结论写入 `/app/work/agent_review.json`、`/app/work/pending_human.json`、`/app/work/evidence_checks.md`。
   - 改写正文型交付物，如 `deliverable.md`、`manuscript.md`、`summary.md`，但所有数字/引用/论断必须能在 `evidence_table.json` 或 `result.json.sources` 中找到依据。
   - 补齐 `output_contract` 要求的字段、生成可编辑产物及 PDF/PNG 预览。

2. **禁止手改结构化产物**：
   - 不得用文本编辑覆盖 `claims.json`、`evidence_table.json`、`inventory.csv`、`version_chain.json`、`result.json` 的结构字段。
   - 发现脚本缺陷时，写临时 Python 调用脚本函数重算，并把修复记录写入 `agent_review.json.script_fixes`。

3. **禁止伪造**：
   - 不编造文件内容、页码、哈希、权限、版本、分数、金标准、基准成绩。
   - 不把文件名猜测或领域标签当事实依据。
   - 不把未完成写成完成；缺失、无文本层、加密、无权限、路径失效必须分类记录。

---

## 2. 目录与运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md`，材料位于 `/input/**`，可用 `--input` 覆盖 |
| 工作区 | `/app/work`：台账、草稿、核验笔记、中间 JSON 放这里 |
| 最终输出 | `/app/output`：`result.json` 及全部可检查交付物 |
| 主入口 | `python3 scripts/main.py run --input /input --output /app/output --work /app/work` |
| 兼容入口 | 若 `run` 子命令不可用，退回 `python3 scripts/main.py --input /input --output /app/output --work /app/work` |
| 退出码 | 脚本应保证 0；即使失败，收尾也必须写合法 `result.json` 后退出 0 |
| 依赖 | Python 3.8+，仅标准库；离线运行 |
| 规模 | 默认 `--max-files 4000`，单文件不应超过 500KB 文本资源，总文本资源 ≤2MB |

### 2.1 单命令全流程入口

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

`run` 至少应完成：
- **init**：盘点文件、目录、权限、魔数、哈希、候选抽取、版本/重复/冲突分组，生成 `/app/work/ledger.json`。
- **build**：校验 init 结果，必要时兜底抽取，渲染全部规定产物，写入 `result.json` 契约键。
- **selfcheck**：核对契约字段、来源、locator、quote、文件产物是否齐全，生成 `verification.json`。

Agent 路径可进一步：
```bash
python3 scripts/main.py check --input /input --output /app/output --work /app/work --draft /app/work/draft.json
python3 scripts/main.py build --input /input --output /app/output --work /app/work --draft /app/work/draft.json
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

如果子命令不可用，不要反复试错，退回 `run` 兼容入口，并把 Agent 改进写进文本型交付物。

---

## 3. 输出产物清单

`/app/output` 中应至少有：

| 文件 | 内容 |
|---|---|
| `result.json` | 最终结构化结果：顶层契约字段 + `output_contract` 嵌套字段、状态、来源、不确定性、失败、核对记录 |
| `inventory.csv` | 每文件一行：`source_id, path, name, type, size_bytes, sha256, permission, status, duplicate_of, version_group, version_label, meta_sources` |
| `version_chain.json` | 版本链、重复组、版本冲突、时间戳异常 |
| `operations.log` | 制表符分隔操作轨迹：`time, action, path, status, detail` |
| `evidence_table.json` | 每条 claim 的 `claim_id, source_id, locator, quote, strength, support_scope, quote_verified, backlink` |
| `agent_review.json` | Agent 核验结论：`claim_id → verified/rejected/reason`、`script_fixes` |
| `pending_human.json` | 待人工确认项、无法自动解决的问题 |
| `verification.json` | selfcheck/脚本复核结果 |
| 可编辑交付物 | 若契约要求 Office/幻灯片/图表，需有真实可编辑文件，并渲染 PDF/PNG 预览 |

---

## 4. 输入发现规则

1. 在 `/input` 递归找 `case*.json`，优先 `case.json` / `input.json` / `task.json`。
2. `case_id` 依次尝试 `case_id` / `caseId` / `case` / `id`；均无则用输入目录名，并原样保留。
3. `output_contract` 原样取出，支持 dict 或 list-of-dict；所有契约键最终都要出现在 `result.json` 顶层及嵌套 `output_contract`。
4. 提问按语义发现，不假设固定键名：键名含 `query/question/ask/request/检索/提问/问题`，值可为字符串、对象（取 `text/query/question/内容`）或列表。
5. 文件识别按**魔数优先、扩展名其次**：`%PDF` → PDF；`PK\x03\x04` → DOCX/XLSX/PPTX/ZIP；OLE → 旧式二进制 Office；PNG/JPEG/TIFF → 图片。
6. 组织方备注/别名：键名含 `note/alias/rename/metadata/version/admin/备注/别名` 的字典或列表，按文件名或路径子串匹配后作为权威覆盖写入，`meta_sources` 记 `case_note`。

---

## 5. 标准执行流程

### 步骤 0：读任务、写 partial、跑基线

1. 读 `/input/task.md` 和 `/input/case.json`。
2. 提取 `case_id`、`output_contract`、问题列表、材料路径、组织方备注/别名。
3. 先在 `/app/output/result.json` 写 partial skeleton：`status="partial"`，`case_id` 正确，`output_contract` 每个键为 `null`/`[]`。
4. 建 `/app/work/working_notes.md` 记录任务要点。
5. 运行：
   ```bash
   python3 scripts/main.py run --input /input --output /app/output --work /app/work
   ```

失败分支：读不到 `case.json` 时继续，`case_id` 用目录名，`output_contract` 空对象；任何读取异常进入 `errors`，但仍写 partial。

### 步骤 1：盘点材料与真实解析

1. 递归列出文件，忽略 symlink，记录大小、权限、魔数、sha256。
2. 对每个可解析文件真实解析：
   - PDF：抽取文本层；无文本层则标记为 `scanned/no_text_layer`，不假装 OCR。
   - DOCX/XLSX/PPTX：抽取段落/单元格/幻灯片文本。
   - TXT/CSV：直接读。
   - 图片：只记录元数据，不 OCR。
3. 将关键内容摘入 `/app/work/parsed_materials.md`。
4. 核对目录、文件名、哈希、来源是否真实来自材料内容或 `case_note`。

失败分支：无权限、损坏、加密 PDF、无文本层扫描件、旧式二进制 Office 等分别写入 `permissions`、`failures`、`pending_human`，不阻塞整体。

### 步骤 2：核对重复、版本与证据

1. 重复组：相同 sha256 的文件归为一组，`duplicates` 记录 canonical 与所有副本。
2. 版本链：按“项目号/归一化文件名 + 版本标签/时间”形成链；识别 `version_conflicts`、`timestamp_anomaly`。
3. 对每个提问：
   - 提取硬过滤条件：年份、项目编号、文件类型、实验批次、版本、权限等。
   - 过滤条件必须硬执行。无法满足时保持空命中，写入 `queries[].notes` 和 `queries[].filtered_out`，不得放宽。
   - 每条命中必须回到原文核验 `quote` 与 `locator` 是否逐字存在。
4. 核验不一致时设 `quote_verified=false`，写入 `pending_human`，不改写原文凑数。
5. 核验结论写入 `/app/work/evidence_checks.md` 和 `agent_review.json`。

### 步骤 3：Agent 产出完整成品

1. 保留并增强基线四件套：`result.json`、`inventory.csv`、`version_chain.json`、`operations.log`。
2. 确保 `output_contract` 全部字段出现在 `result.json` 顶层和嵌套 `output_contract`。
3. 若契约要求可编辑 Office/幻灯片/图形，生成真实可编辑文件，并渲染 PDF/PNG 预览；在 `result.json.artifacts` 记录路径、类型、sha256。
4. 补齐顶层字段：
   - `status`
   - `case_id`
   - `files`
   - `directories`
   - `duplicates`
   - `version_chains`
   - `queries`
   - `sources`
   - `failures`
   - `skipped`
   - `permissions`
   - `pending_human`
   - `errors`
   - `degradations`
   - `counts`
   - `verification`
   - `runtime`
   - `uncertainty`
   - `change_records`
   - `reviewed_by_agent`
   - `artifacts`
5. 更新 `operations.log`，追加 Agent 动作：`reverify/enhance/render/write`。

### 步骤 4：selfcheck

必须逐项检查：
- `result.json` 合法：`python3 -m json.tool /app/output/result.json > /dev/null`
- `case_id` 与输入一致。
- `output_contract` 每个键在顶层和嵌套 `output_contract` 都存在，未知道键保留。
- 每个文件在 `inventory.csv` 有对应行，关键文件有 sha256。
- 每个 query hit 有 `source_id`、`locator`、`quote`、`quote_verified`、`backlink`。
- 失败、跳过、权限、空结果、路径失效均已分类记录。
- 磁盘产物与 `result.json.artifacts` 一致。
- 所有可验证结论均有 locator；不能验证的写入 `pending_human` 或 `uncertainty`。

自检记录写入 `/app/work/self_check.md` 或 `verification.json`。

### 步骤 5：最终收尾

1. 最终写回 `result.json`，保证完整字段和双回显。
2. 状态只允许：
   - `ok`：全部完成且证据通过。
   - `partial_with_limitations`：完成大部分，但有明确限制。
   - `partial`：仅完成基础结构，关键检索未完成。
   - `failed`：脚本失败但已写入诚实错误信息；退出码仍是 0。
3. 确认退出码 0。

---

## 6. `result.json` 双回显与契约字段

```json
{
  "case_id": "<从输入原样保留>",
  "status": "ok|partial|partial_with_limitations|failed",
  "output_contract": {
    "case_id": "<同顶层 case_id>",
    "<contract_key_1>": "<对应结果或 null>",
    "<contract_key_2>": "<对应结果或 null>"
  },
  "files": [],
  "directories": [],
  "duplicates": [],
  "version_chains": [],
  "queries": [],
  "sources": [],
  "failures": [],
  "skipped": [],
  "permissions": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "counts": {
    "files": 0,
    "directories": 0,
    "duplicates": 0,
    "version_chains": 0,
    "queries": 0,
    "hits": 0,
    "verified_hits": 0,
    "unverified_hits": 0
  },
  "verification": {},
  "runtime": {},
  "uncertainty": [],
  "change_records": [],
  "reviewed_by_agent": {},
  "artifacts": []
}
```

**关键规则**：
- `output_contract` 的每个键必须在顶层也出现，不能只放在嵌套对象里。
- 契约中的未知键原样保留；语义对不上的填 `null` 或 `[]`，不删除。
- `case_id` 在顶层和 `output_contract` 中都必须有。
- `sources` 每条至少包含：`source_id, path, name, type, size, sha256, permission, status, meta_sources`。
- `queries[]` 每条至少包含：`query_id, question_text, filter_conditions, filters_satisfied, hits[], filtered_out[], notes`。
- 每一条 `hit` 至少包含：`hit_id, source_id, locator, quote, quote_verified, backlink, relevance`。

---

## 7. 检索、定位与证据回链方法

### 7.1 跨文件语义检索
- 不以文件名命中为终点，必须进入文本内容。
- 对同义表述、缩写、中英文写法、上下位词做归一化和扩展匹配。
- 所有命中必须落到文件内容中的具体片段，而不是整篇文件。

### 7.2 章节定位
- locator 必须可复现：
  - PDF：`path/to/file.pdf#page14/para3`
  - DOCX：`path/to/file.docx#section=Methods/para=2`
  - XLSX：`path/to/file.xlsx#sheet=实验记录#row=12`
  - PPTX：`path/to/file.pptx#slide7`
- 若印刷页码与物理页不同，记录 `physical_page` 和 `printed_page`；无法判断时写 `page_unknown`，不伪造页码。
- 跨页表格、图注、双栏排版要给出可核对的上下文定位。

### 7.3 硬过滤
- 年份、项目编号、文件类型、实验批次、版本、权限等条件必须作为硬约束。
- 没有满足条件的记录时，返回 `hits=[]`，在 `filters_satisfied=false` 和 `filtered_out` 中说明，不自动放宽。

### 7.4 证据回链
- 所有 claim 必须带 `quote`：原文逐字片段。
- 所有 claim 必须带 `locator`：文件路径 + 页/段/行/幻灯片。
- `quote_verified=true` 只表示 Agent 或脚本已回到原文逐字核验过。
- 关键数字/论断在成稿中用 `[S#]` 标注，对应 `sources` 中的 `source_id`。

---

## 8. 失败、跳过与恢复记录

| 情形 | 识别 | 处置 | 记录位置 |
|---|---|---|---|
| 无权限文件 | PermissionError / mode | 不强行读取；记录路径和权限 | `permissions` |
| 损坏文件 | 解析异常、魔数不符 | 跳过并记录异常 | `failures` / `skipped` |
| 加密 PDF | PDF 解析报加密 | 标记 `encrypted`，不伪造正文 | `failures` / `pending_human` |
| 无文本层扫描件 | PDF 无抽取文本 | 标记 `scanned/no_text_layer`，不 OCR | `failures` / `pending_human` |
| 旧式二进制 Office | OLE 魔数 | 标记 `unsupported_legacy_office` | `skipped` |
| 重名文件 | 同 basename 不同路径/哈希 | 在 `sources` 中保留路径区分 | `duplicates` / `sources` |
| 空结果 | 无命中 | 保持空 hits，写 `filters_satisfied` | `queries[]` |
| 路径失效 | symlink/文件消失 | 不跟随 symlink，记录失效路径 | `errors` |
| 版本冲突 | 版本标签与时间不一致 | 不强行排序；写 `version_conflicts` | `version_chain.json` / `pending_human` |
| 材料缺失 | 契约要求但输入无对应材料 | 填 `null`/`[]`，写缺失说明 | `degradations` / `pending_human` |

---

## 9. 确定性兜底与 Agent 增益

### 9.1 无 `draft.json` 时
- `build` 使用 init 台账确定性抽取，生成实质工作稿。
- 每条 AUTO_EXTRACT 的 claim 必须有逐字 `quote` 和 `locator`。
- 在 `gaps`/`degradations` 中诚实写入 `AUTO_EXTRACT`，不冒充人工核验结论。

### 9.2 有 Agent `draft.json` 时
- Agent 在 `/app/work/draft.json` 中写入判断；再用 `check → build → selfcheck`。
- `reviewed_by_agent` 记录 Agent 增强点、核验数量、被拒绝/修正的 claim、未决问题。

### 9.3 增益证据
- 章节级 locator + 逐字 quote + `quote_verified` 证明定位准确性和回链可靠性。
- 版本链 + 重复组 + 硬过滤记录证明减少了人工比对和翻页成本。
- `verification.json` 与 `operations.log` 证明可复跑、可复核。
- 不写“相比基础 Agent 提升了 X%”这类自造分数，只写可检查的证据。

---

## 10. 预算策略（64 次模型请求 / 900 秒）

| 阶段 | 请求参考 | 说明 |
|---|---|---|
| 步骤 0：读任务、跑基线 | 3-6 | 脚本扫描不占或低占模型请求 |
| 步骤 1：解析与盘点核验 | 5-10 | 优先核验关键文件 |
| 步骤 2：检索命中逐字核验 | 10-20 | 最高优先级，实际效果 40 分核心 |
| 步骤 3：补全契约与预览 | 8-15 | 完整性交付 |
| 步骤 4-5：自检与修复 | 5-12 | 结构、字段、JSON 合法 |
| 储备 | 5-10 | 失败重试、边缘材料处理 |

落盘优先级：
1. 先写 partial `result.json`。
2. 再保证 `queries`、证据回链、失败记录。
3. 再补齐契约字段和渲染预览。
4. 最后做 selfcheck。
任何阶段结束都覆盖写 `result.json`，不能因单点失败丢光成果。

---

## 11. 隐藏案例鲁棒性

可能输入类型：
1. **正常案例**：混合 PDF/DOCX/XLSX/PPTX/TXT/CSV，存在重名、不同版本、多目录。
2. **边界案例**：扫描 PDF、加密 PDF、旧式 Office、图片文件、空目录、权限限制、路径中文/空格、年份/项目号缺失。
3. **异常案例**：缺 `case.json`、契约字段不完整、材料路径失效、任务说明与材料不符、无 query。

应对：
- 不假设文件类型，魔数识别。
- 不因某个文件失败而阻塞整体。
- 不填充缺失的合同字段为虚构值。
- 对不可识别/不可解析对象只记录元数据，不猜测内容。
- 对路径失效/权限问题分类记录，不重复尝试浪费请求。
- 对空结果保持空结果，不降低过滤标准。

---

## 12. rubric → 交付证据对照

| 维度 | 主要交付证据 |
|---|---|
| 实际效果：任务完成度 | `inventory.csv`、`version_chain.json`、`operations.log`、`result.json.status`、`counts` |
| 实际效果：结果正确性 | `queries[].hits[].quote`、`locator`、`quote_verified=true`、`verification.checks` |
| 实际效果：结果完整性 | 契约字段全覆盖、`files` 完整、过滤维度记录、可编辑产物及预览 |
| 实际效果：可核验性 | `sources[].sha256`、`backlink`、`operations.log`、`verification.json` |
| 使用增益：质量 | 章节级 locator + 逐字 quote + 版本/重复标注 |
| 使用增益：效率 | 一次运行同时产出清单、版本链、索引、检索、复核 |
| 使用增益：可验证性 | `reviewed_by_agent`、`verification`、`change_records` |
| 创新增益：新增能力 | 跨文件语义命中、硬过滤不可满足空结果、章节继承定位 |
| 创新增益：方法改进 | `references/method.md`、哈希去重、版本链、locator 规则 |
| 创新增益：创新证据 | 真实 query 结果展示定位类型与过滤处理 |
| 可靠体验：调用易用 | 单命令 `run`、`--help`、清晰流程 |
| 可靠体验：稳定性 | 同一输入重复运行确定，异常分支完整 |
| 可靠体验：异常处理 | `permissions`、`failures`、`skipped`、`pending_human`、`errors` |
| 生态贡献：文档 | `SKILL.md`、`references/output-schema.md`、`references/method.md`、`references/example.md` |
| 生态贡献：可复用 | `scripts/main.py`、`scripts/engine.py`、标准库依赖 |
| 生态贡献：分享 | 方法说明、示例标为示例，不冒充正式案例结果 |

---

## 13. 必须避免的扣分项

1. 只按文件名搜索，不读文件内容。
2. 只给整篇文件，不给章节/页/段/行级 locator。
3. 引用无逐字 quote 或 quote 与原文不一致。
4. 滤条件不满足时自动放宽或伪造命中。
5. 把副本/旧版本当独立证据，不识别重复组和版本链。
6. 把无文本层扫描件、加密文件、无权限文件当成成功解析。
7. 把缺失材料、未核验 claim、未生成预览写成完成。
8. 自造 benchmark 分数、golden_standard、加权自评分，或引用不存在于 `verification.json` 的结果。
9. 结构产物手改导致字段不一致或 JSON 非法。
10. `result.json` 契约字段只在嵌套里，顶层缺失；或 `case_id` 不一致。

---

## 14. 最小调用示例

输入 `/input` 包含 `case.json`、`task.md` 和科研材料后，执行：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出 `/app/output/result.json`：

```json
{
  "case_id": "demo_001",
  "status": "partial_with_limitations",
  "counts": {"files": 12, "queries": 2, "hits": 3, "verified_hits": 2},
  "output_contract": {"case_id": "demo_001", "query_results": ["h1", "h2"]}
}
```

> 该输出仅用于说明接口；正式案例必须由实际 `/input` 材料生成。  
> 样例与正式结果不得互相冒充。