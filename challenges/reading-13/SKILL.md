---
name: nanopub-forge
description: 把科研论文正文拆成可独立判断真假的原子断言，为每条断言绑定逐字证据片段与页码/段落/字符定位，记录来源元数据与置信度依据，导出可机器读取的 nanopublication 结构（result.json + assertions.jsonl）。脚本是工具，最终交付物由 Harness Agent 亲自读材料、推导、撰写/制作。
version: 2.0.0
---

# nanopub-forge · 论文段落 → 原子断言 + 逐字证据

## 0. 执行铁律：完整性优先，脚本不是成品

1. **脚本只是工具**：`scripts/main.py` 与 `scripts/verify.py` 只负责生成候选、抽取文本、校验定位。最终交付物必须由你（Harness Agent）亲自读材料、推导、撰写/制作。禁止把脚本骨架或模板直接当成品。
2. **先跑基线，再增强**：进入任务后先运行主脚本，产出全套基线交付物（包括 `result.json`、`assertions.jsonl`、`extracted_text.json` 以及所有输出契约要求字段）。后续复核与改写只能在基线上增强，不得删除、清空或遗漏任何基线字段或产物。
3. **完整交付优先**：提交前逐项核对「`output_contract` 字段 × 磁盘文件 × `result.json` 键」三者一致；缺任何一项先补齐再收尾。`partial` 状态必须列出缺失项。
4. **可核验增强**：在基线产物之上，由 Agent 亲自核验关键论断、数字、引用的来源一致性，把核验结果写进 `result.json`（`verified / pending_human / conflicts`），这才是“genuinely-derived”的证据。

## 1. 用途与边界

输入一篇（或若干）科研材料，输出一份**逐条可判真假**的断言表：每条断言只有一个谓词，带主体、关系、宾语、极性、限定条件、**逐字证据片段**、**页码/段落/句序/字符区间**定位、来源元数据、`np_id`（可重算的去重标识）与置信度依据。

适用：Nanopublication 生成（assertion/provenance/pubinfo）、断言拆解与校验、证据绑定、结构化导出、文献知识单元抽取。  
不适用：需要 OCR 的扫描件、需要读图表内部数值的任务（本 Skill 只登记题注位置并转人工/视觉核对）、需要联网核对 DOI 真伪的任务。

触发条件：任务要求“把段落拆成断言 / 给结论配证据 / 输出可机读的 claim 表 / 追来源 / 生成 nanopublication”。  
不触发：纯翻译、纯摘要、纯排版。摘要式输出不算完成本题。

## 2. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`（或任意 `*case*.json`）、`/input/task.md`、`/input/**` 材料 |
| 输出 | `--output`（默认 `/app/output`）下 `result.json`、`assertions.jsonl`、`extracted_text.json`；`verify.py --patch` 追加 `verification.json` 并回写 `verification.external` |
| 依赖 | 仅 Python 3 标准库；离线；不依赖 CWD（用 `Path(__file__).resolve().parent`） |
| 退出码 | **恒 0** |
| 先落盘 | 进材料前先写一次 partial `result.json`；结束无条件 finalize 覆盖 |
| 预算 | 默认写在脚本参数中（`--time-budget`、`--max-assertions`）；到限即降级 finalize |
| 工作目录 | 中间文件写 `/app/work`；最终产物写 `/app/output` |

调用：

    python3 -B scripts/main.py --input /input --output /app/output
    python3 -B scripts/verify.py --output /app/output --patch

## 3. 输入发现（语义识别，不假设键名）

1. `case.json`：若不存在或解析失败，递归找 `*case*.json`；仍失败则只靠目录扫描，并在 `errors` 记录解析异常。
2. `case_id`：依次尝试 `case_id/caseId/id/name`，再试 `case/task/meta/input` 下的同名键；都没有则用输入目录名。**原样保留，不改写**。
3. `output_contract`：在 case 元数据里按语义找 `output_contract / contract / output_schema / required_output / output_fields`（可嵌套）。
4. 材料：先读 case 中出现的文件路径（`/input/x` 会被展开），再递归扫描 `/input/**`，按扩展名+魔数识别 pdf / docx / xlsx / csv / tsv / md / txt / html / json / 图片。
5. 声明了但打不开的材料 → `input_gaps`；没有文本层的材料 → `pending_human(no_text_layer)`。**不构造内容**。

## 4. 输出与字段

`result.json` 顶层：`skill, case_id, status, status_reason, task_understanding, inputs, sources, assertions, figures, counts, verification, uncertainty, pending_human, errors, degradations, changes, runtime, artifacts, output_contract_keys, output_contract_echo, contract_fields_present`，并把契约键平铺到顶层（同名以 Skill 结构为准，但键一定存在）。

`assertions[]` 每条含：`assertion_id, np_id, kind, assertion_text, subject{text,type}, relation, relation_raw, object{text,type}, polarity, magnitude, condition[], evidence[{quote, source_id, locator, location{page,paragraph,sentence_index,char_start,char_end,locator_type,json_pointer},match}], readability, confidence{score,basis[],tier}, needs_review, review_reason, source_ids[]`。

完整字段语义、受控词表、定位符规则见 **`references/field-dictionary.md`**；判据见 **`references/rules.md`**；20 条示意样例见 **`references/examples.md`**。

契约回填：`output_contract` 原样按形状回填到 `output_contract_echo`（键名不改、缺失为 `null`/`[]`、未知键保留），叶子指针写入 `output_contract_keys`，`verification.contract` 给出键数与是否取到值。

## 5. 本题专属执行流程（每步输入/动作/输出/失败分支）

### 步骤 1：盘点输入与契约

- **输入**：`/input/case.json`、`/input/task.md`、`/input/**` 材料。
- **动作**：读取 `case.json`；若不存在，搜索 `*case*.json`；仍失败则扫描目录。解析任务说明；提取 `case_id` 与 `output_contract` 形状；建立材料清单与输入缺口。
- **输出**：`task_understanding` 草稿、`inputs` 清单、`output_contract` 结构、缺口记录。
- **失败分支**：case.json 缺失 → 用 `task.md` + 目录扫描继续；JSON 损坏 → 保存原始错误到 `errors`，继续扫描；`output_contract` 缺失 → 使用默认 schema 并置 `assumed_contract=true`。

### 步骤 2：真实解析材料并生成基线

- **输入**：材料清单。
- **动作**：运行 `python3 -B scripts/main.py --input /input --output /app/output`，生成基线 `result.json`、`assertions.jsonl`、`extracted_text.json`。**必须真实解析材料内容**：优先使用平台提供的 PDF 文本抽取工具（如 pdf-text-tool）或系统 `pdftotext`；若不可用，由 `scripts/main.py` 内置解析器抽取。不得依据文件名或领域标签猜测/补造内容。
- **输出**：基线产物；逐页文本缓存 `extracted_text.json`；来源、页码、段落、句子、字符区间。
- **失败分支**：脚本启动失败 → 记录 `errors`，使用简单标准库脚本或手工构造最小合法 `result.json`，保证退出码 0；单个材料解析失败 → 只降级该材料，其他材料继续处理。

### 步骤 3：亲自复核文本与证据

- **输入**：`extracted_text.json`、原始材料路径、基线 `assertions.jsonl`。
- **动作**：逐页阅读 `extracted_text.json` 文本，确认文本层有效；对候选断言逐条或抽样复核：每条是否只有单一谓词、主体/关系方向是否正确、证据 quote 是否逐字存在于对应页（仅做空白折叠比较）；若某页文本为空或质量差，该页结论一律不写成事实。
- **输出**：确认或修正的断言列表；`needs_review` 标记；逐字命中记录。
- **失败分支**：材料无文本层/扫描版 → 该页只登记位置，不生成事实断言，进 `pending_human(no_text_layer / vision_required)`；引用无法在 `extracted_text.json` 定位 → `needs_review=true`，尝试回原文核对；仍失败则进 `pending_human(quote_not_traceable)`。

### 步骤 4：构建/强化证据与来源元数据

- **输入**：已复核的断言、材料元数据。
- **动作**：为每条断言裁剪最小充分证据片段；确保证据含主体、关系、宾语（量化断言含数值与单位）；补 `subject.type/object.type`、`magnitude`、`condition`、`polarity`；将 `other_relation` 映射到受控词表或降级；来源元数据只从输入实际内容提取，不填充未提供的 DOI 或分数。
- **输出**：增强版断言列表，每条具有 `locator/json_pointer/char区间`。
- **失败分支**：证据不足 → 降低 `tier` 或进 `pending_human(insufficient_evidence)`；材料冲突 → 两侧都留，写入 `uncertainty`。

### 步骤 5：产出完整成品并保留基线

- **输入**：增强后的结果。
- **动作**：写回 `/app/output` 的 `result.json` 与 `assertions.jsonl`；保留基线字段，只覆盖增强内容；确保 `output_contract` 的每个字段以相同键名平铺到顶层或写入 `output_contract_echo`；若存在可编辑 Office/幻灯片/图形产物，调用渲染工具生成真实 PDF/PNG 预览并登记到 `artifacts`；否则 `artifacts` 只列 JSON 与文本文件。
- **输出**：全套交付物。
- **失败分支**：写盘失败 → 保留 `/app/work` 副本，状态 `partial`，错误记录。

### 步骤 6：运行校验与自检

- **输入**：`/app/output` 产物。
- **动作**：运行 `python3 -B scripts/verify.py --output /app/output --patch`，逐条核对 quote 是否在 `extracted_text.json` 和原始重抽文本中逐字命中；检查 `failures`；若有失败，逐条修正或移入 `pending_human`，不允许改原文凑命中；然后再次运行，直到 `failures` 为空或所有失败已解释。
- **输出**：`verification.json`、`verification.external`、修改后的 `result.json`。
- **失败分支**：`verify.py` 无法运行 → 手工执行等价校验并记录到 `verification`；无法解决的失败 → 标 `partial`，对应断言 `needs_review=true`，并进 `pending_human`。

### 步骤 7：回填 result.json 与契约核对

- **输入**：所有产物。
- **动作**：确保 `result.json` 包含 `case_id`（原样保留）、`status`、`status_reason`、`sources`、`assertions`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`output_contract_keys`、`output_contract_echo`、`contract_fields_present`；将输出契约每个字段回填到顶层或 echo；写 `changes` 记录本次 Agent 的修正与复核数量。最终确认 JSON 合法，所有文件在 `/app/output`，退出码 0。
- **输出**：最终 `result.json`。
- **失败分支**：任何字段缺失 → 补默认 `null/[]/空字符串` 并记录 `missing_fields`；存在未解决的 `blocking` 项时 `status=partial`，但绝不返回非零退出码。

## 6. 预算策略（64 次模型请求 / 900 秒）

优先保证 rubric 权重最高的“实际效果 40 分”与“使用增益 25 分”所依赖的交付物：完整断言、逐字证据、真实来源、contract 字段全量。

大致分配：

- 前 3 次：盘点输入、读 `task.md` 与 `case.json`，确定契约与材料。
- 第 4–8 次：运行主脚本，检查基线产物与契约字段是否齐全；若需补充抽取，调用外部 PDF 工具。
- 第 9–25 次：阅读 `extracted_text.json` 与关键页原文，复核并修正断言；优先处理 `tier=low`、`needs_review=true`、量化和方向性强的条目。
- 第 26–35 次：处理证据不足、冲突、图表人工接管、来源元数据。
- 第 36–42 次：运行 `verify.py`，修复 `failures`。
- 第 43–50 次：完整性自检、对照 rubric 表、补字段、写 `changes`。
- 第 51–64 次：留作重试与意外情况。

尽早落盘：脚本运行后 `/app/output` 已有 baseline；每次批量复核后写一次 `result.json`，不要最后才写。避免重复解析同一材料；使用 `extracted_text.json` 缓存；仅当 `verify.py` 失败时回原文。若接近 64 次请求或 900 秒，立即停止改进并 finalize 当前结果；`status=partial` 并记录 `budget_reached` 到 `degradations`。

## 7. 隐藏案例鲁棒性与降级表

| 触发 | 检测 | 处置 | 落点 |
|-|-|-|-|
| 无 case.json | 路径探测 + glob | 用 task.md 与目录扫描继续 | `errors` + `degradations` |
| case.json 非法 JSON | `json.loads` 异常 | 保留错误、按扫描继续，`status=partial` | `errors` |
| 无 output_contract | 键探测 | 用 schema 默认字段，`assumed_contract=true` | `task_understanding` |
| 空输入 / 无材料 | 目录扫描无文件 | `status=input_error`，退出码 0，合法 result.json | `pending_human.no_material` |
| 扫描版 PDF（无文本层） | 每页字符<50 或质量<0.55 | 不伪造文本，该页只登记、进人工 | `sources[].flags` + `pending_human` |
| 字体编码不支持 | 抽取质量低 | 换手 `pdftotext`/`pypdf`（有则用），仍差则标不可解析 | `degradations` |
| 单材料解析失败 | 逐材料 try/except | 只降级该材料，其余继续 | `errors` |
| 格式不支持 | 扩展名+魔数未知 | 不解析不编造，标记 unsupported | `pending_human` + `errors` |
| quote 找不到 | 固化校验 | `needs_review=true` + 复核队列，**不改原文** | `verification.quote_checks.failures` |
| 预算耗尽 | 计时/计数 | finalize 已有结果，标 `partial` | `degradations` |
| 任何异常 | finally | 必须写出合法 `result.json` 且退出码 0 | 顶层 `status` |

任何情况下都不允许返回非零退出码，不允许因校验失败而中断交付。

## 8. Rubric 维度 → 交付要求 → 自证方式

| 评分维度 | 交付要求 | 自证方式 |
|-|-|-|
| 实际效果 / 任务完成度（拆得细） | 每条断言只有一个谓词，复合句拆开；段落不整段塞入一个字段；字段结构齐全 | `counts.sentences_scanned / assertions_emitted / assertions_after_dedup / duplicates_merged`；`assertions[]` 每条的 `kind` 与单关系 |
| 实际效果 / 结果正确性（对得上） | 断言忠实原文，证据片段