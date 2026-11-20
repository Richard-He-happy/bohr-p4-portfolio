---
name: academic-format-template-adapter
description: 将真实学术稿件按给定模板/格式要求（期刊投稿、学位论文规范、docx 模板）重新排版。读取真实稿件与格式来源，抽取 32 项可核对规格（字体/字号/行距/页边距/栏数/标题层级/题注位置/三线表/参考文献样式/页脚页码），产出可编辑 docx、markdown、format_spec.json、fidelity_report.json、真实 PDF 预览与 result.json。脚本确定性落版；Agent 负责读原文、写判断、核验与诚实回填。纯格式适配/模板套用/期刊格式检查时使用；纯写作、润色、翻译、文献综述不要使用。
version: 5.0.0
---

# 学术格式与模板适配 v5（单命令全流程 + Agent 双路径）

## ★ Agent 修改边界（最高优先级，先读）

1. **禁止手改结构化产物**：`spec_table.json`、`format_spec.json`、`fidelity_report.json`、`result.json` 的键名、claim_id、source_id、locator、quote、strength、support_scope、counts 等结构字段必须由脚本生成；不要用文本编辑覆盖它们。
2. **允许 Agent 做的事**：
   - 真实阅读 `/input` 材料，核验脚本抽取的 quote / locator / 数字与原文是否一致；
   - 把核验结论写入 `/app/work/agent_review.json`（逐条列出 field → verified/rejected/reason）与 `result.json` 的 `pending_human`、`conflicts`、`changes` 补充项；
   - 亲自撰写或改进正文型交付物（`deliverable.md` / 各 content 单元），但每个数字、引用、论断必须能在 `fidelity_report.json` 或 `format_spec.json` 找到依据；
   - 若发现脚本缺陷：写一个临时 Python 调用脚本函数重算并覆盖（记录在 `agent_review.json` 的 `script_fixes`），不得手工篡改 JSON。
3. **禁止生成无依据的评分/金标准**：不要自造 `golden_standard`、加权自评分；核验只引用 `selfcheck_report.json` 或 `check_report.json` 的真实输出。
4. **完整性自检**：结束前核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；`deliverable.md` 与带证据标记草稿如同时存在，内容必须不同，不得复制粘贴同一文本。
5. **预算意识**：优先运行单命令 `run` 获得全套基线（通常 1–2 次工具调用即可），再用剩余请求做最大价值的核验与改进；接近 64 次模型请求或 780 秒时立即收尾，保证 `result.json` 合法且 `status` 诚实。

## 1. 运行契约与单命令入口

- 输入：`/input/case.json` 与 `/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。工作目录 `/app/work`；最终产物必须落在 `/app/output`。
- 必须真实解析材料内容（优先使用 `scripts/main.py` 的解析能力，必要时 `pdftotext` 等工具），不得依据文件名、领域标签或先验猜测补造内容。
- 最终必须有 `/app/output/result.json`，且包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`；可编辑 Office 产物（`deliverable.docx`）必须额外给出真实渲染的 PDF 预览（`preview.pdf`；若无 LibreOffice 则给出 `preview.txt` 并在 `result.json` 中说明）。
- 首选单命令全流程入口：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

- `run` 内部严格按顺序执行：
  - `init`：盘点材料、来源编号、候选抽取、冲突分组，写 `/app/work/index.json` 与 `/app/work/spec_table.draft.json`；
  - `build`：校验/兜底抽取/渲染全部产物/写回最终 `result.json`；
  - `selfcheck`：产物与契约自检，写 `/app/work/selfcheck_report.json`。
- `run` 任何异常也必须 exit 0，并写合法 `result.json`。若 `run` 不可用（旧包），按顺序执行：

```bash
python3 scripts/main.py init --input /input --work /app/work --out /app/output
python3 scripts/main.py build --input /input --work /app/work --out /app/output
python3 scripts/main.py selfcheck --input /input --work /app/work --out /app/output
```

- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本执行不占模型请求，但要避免冗余调用。

## 2. 双路径协议（同一套产物，同一份 result.json 契约）

### 路径 A：Agent-first 增量路径（推荐）

1. `run` 先创建全套基线。
2. Agent 读取 `/app/work/index.json` 台账，据此识别材料角色（原稿/模板文件/格式要求/补充规定）。
3. Agent 用 `show` 真正读取关键原文，把判断写入 `/app/work/draft.json`（形状见下文）。
4. 运行 `check` 验证证据，再 `build` 重新渲染，最后 `selfcheck`。
5. `draft.json` 只表达 Agent 对格式规格、内容单元保留、不确定项的判断；脚本负责合并为 `spec_table.json`。

`draft.json` 推荐形状：

```json
{
  "case_id": "来自 /input/case.json",
  "style_choices": [
    {
      "field": "body.font",
      "value": "Liberation Serif",
      "source": "m02",
      "locator": "m02#L0005",
      "quote": "3. Body text: Liberation Serif, 12 pt, 1.5 line spacing, justified.",
      "confidence": "explicit"
    }
  ],
  "content_preservation": true,
  "notes": "toc not required by this journal; figure images not present in source"
}
```

- `field` 只能取 `references/format_spec_schema.md` 列出的 32 个字段；`value` 可写 `12pt`、`2.5cm`、`小四`、`below`，脚本会规范化。
- `quote` 必须**逐字**出现在源文件里（空白差异可忽略）。查不到 → 该条被拒收并记 `degradations`，绝不改原文凑通过。
- 有 `quote` 且 `confidence=explicit` = `explicit`；无 `quote` = `inferred`（沿用 Agent 值，但计入不确定性）。
- 与脚本材料挖出的候选冲突时，以 Agent `draft.json` 为准，但脚本会把冲突双方 locator 写入 `result.json.conflicts`。

### 路径 B：无 draft 的确定性兜底

- 当 Agent 时间/预算严重不足、未写 `draft.json` 时，`build` 必须用 init 台账**确定性抽取**生成实质工作稿：逐字 quote + locator，不猜测。
- 该路径由脚本自动完成，所有自动抽取判断记入 `result.json.degradations`，且必须包含 `"handled_by": "AUTO_EXTRACT"` 与 `"reason": "no agent draft; deterministic extraction from init inventory"`。
- 若台账中有 ≥8 条 explicit 且 quote 命中率达标，产物可标 `status=ok`，但 `degradations` 仍必须说明 AUTO_EXTRACT；否则标 `partial`。
- 两条路径产出**同一套文件**：`deliverable.docx`、`deliverable.md`、`format_spec.json`、`fidelity_report.json`、`preview.pdf/preview.txt`、`result.json`。不得因路径不同而改变契约字段。

## 3. 输入发现与材料盘点（init 已实现；Agent 只需复核）

1. 递归扫描 `/input/**`（≤80 文件，跳过 output/work/隐藏目录），按魔数 + 扩展名判断类型：`%PDF`→pdf、`PK`+`word/document.xml`→docx、图片签名→image。
2. `case.json` 缺失或非法 JSON → 记 `result.json.errors[stage=case]`，改用目录扫描 + `task.md` 继续。
3. **原稿判定**：字符量 × 类型权重（docx×1.3）；文件名含 `templ|模板|requir|format|spec|要求|须知` 降权 95%；自身挖到 ≥3 条规格的降权到 30%。结果写 `/app/work/index.json` 的 `manuscript`。
4. **格式来源判定**：除原稿外，任何挖出规格的材料都算格式来源，按条数排序；同一字段多个取值 → 记 `conflicts`（保留首个来源的值，双方 locator 都留档）。
5. 材料没给的对象一律进 `pending_human`，不猜、不补。

**Agent 必须核验内容**：至少快速读取 `index.json` 中 `manuscript`、`format_sources` 的角色判断是否合理；若原稿/格式来源角色错配，写入 `result.json.changes`（例如“原稿被识别为模板；已修正”），但不手改 index.json。

## 4. 执行流程（严格按序，每步写清输入/动作/输出/失败分支）

### 第 0 步：一键基线（必做，最快产出全套合法产物）

**输入**：`/input` 目录。  
**动作**：运行：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

**输出**：`/app/output` 下全套基线产物，`result.json` 合法 partial 或更优；`/app/work` 下台账与自检报告。  
**失败分支**：任何一步异常都必须 exit 0 并写合法 `result.json`。若 `run` 命令不存在，按第 1 节 fallback 命令执行；仍然要保证产物齐全。

### 第 1 步：读台账与判断材料角色

**输入**：`/app/work/index.json`。  
**动作**：你（Agent）打开 `index.json`，查看案件、`output_contract` 键、材料表（角色/块数/字符数/挖到的规格条数）、候选规格清单、冲突项、原稿前 36 段（带 locator）。  
**输出**：向自己确认哪份是原稿、哪份是模板/格式要求、哪些字段有显式规格、哪些是 NOT STATED。  
**失败分支**：台账缺失 → 重新运行 `init` 生成；仍失败则将 `result.json.status` 改成 `input_error` 并退出 0。

### 第 2 步：用 show 真实读取关键材料

**输入**：`/app/work/index.json` 材料清单。  
**动作**：读取关键材料实际内容，优先格式要求文件和原稿开头/结尾。通常 2–4 次读取足够：

```bash
python3 scripts/main.py show --input /input --work /app/work --material m03 --from 1 --to 60
python3 scripts/main.py show --input /input --work /app/work --material m02 --items
```

需要确认的规格点：字体、字号、行距、页边距、栏数、标题层级、题注位置、三线表、参考文献样式、页脚页码。每条后续写入 `draft.json` 的 explicit 规格都必须有逐字 quote（去空白后比对，不近似匹配）。  
**输出**：对材料内容的真实理解，准备写入 `/app/work/draft.json`。  
**失败分支**：某材料解析失败或损坏 → 只降级该材料，记录 `result.json.sources[].read_note`，将该材料可提供的规格记为 NOT STATED；其他材料继续。

### 第 3 步：写 `/app/work/draft.json`（核心判断，脚本不替你做）

**输入**：第 2 步读到的材料原文。  
**动作**：按 32 项规格逐条判断，写 `draft.json`。规则：
- `field` 只能取 `references/format_spec_schema.md` 的 32 个字段；`value` 规范化。
- `quote` 必须逐字命中；查不到 → 不写 quote，写 `confidence: "inferred"` 并计入不确定性。
- 显式规格至少覆盖：字体、字号、行距、页边距、标题层级、参考文献样式、图表题注。若仅 5 条显式，也可以，但 result 会体现不足。
- 写清 `notes`：哪些规格未给、哪些内容单元缺失、哪些需人工确认。
- **不要手改 `spec_table.draft.json` 或 `spec_table.json`**。脚本会在 `check`/`build` 时合并本 draft。

**输出**：`/app/work/draft.json`。  
**失败分支**：材料规格不足 → 保留默认值并标 inferred，逐条写入 `result.json.uncertainty`；无法安全判断（如参考文献样式只写 GB/T 7714 未给版本）→ 写入 `pending_human` 并给出可执行动作。

### 第 4 步：check 验证证据链

**输入**：`/app/work/draft.json` 与 `/app/work/index.json`。  
**动作**：运行：

```bash
python3 scripts/main.py check --input /input --work /app/work --out /app/output
```

检查项：索引/原稿存在、规格表存在、32 字段齐全、explicit ≥8、quote 逐字命中率、块数、标题数、verbatim 1.0、数字保留、引用保留。结果写 `/app/work/check_report.json`，逐条 PASS/FAIL。  
**输出**：`/app/work/check_report.json`。  
**失败分支**：FAIL 先修 draft（quote 未命中 → 用 `show` 复制原文；数字丢失 → 说明内容改动）。若时间不够，可保留 FAIL 项，继续 build 并在 `result.json` 如实记录；但 `status` 不得为 `ok`。

### 第 5 步：build 生成完整成品（无条件 finalize）

**输入**：`/app/work/draft.json`（如有）、`/app/work/index.json`、`/app/work/check_report.json`。  
**动作**：运行：

```bash
python3 scripts/main.py build --input /input --work /app/work --out /app/output
```

脚本确定性落版并生成全套交付物：`deliverable.docx`（可编辑，style 绑定）、`deliverable.md`、`format_spec.json`、`fidelity_report.json`、`preview.pdf`（有 LibreOffice 时）、`result.json`。  
兜底顺序（任一步失败都不中断）：
1. 有 `draft.json` → 逐条校验后应用；
2. 无/坏 draft → 使用 init 挖到的规格 + 默认值确定性落版，`status=partial`，并记录 `AUTO_EXTRACT`；
3. 原稿不可解析 → 写「说明文档」（非空、可打开），`status=insufficient_evidence`；
4. docx 写入异常 → 立即用默认规格重写一次最小 docx，错误入 `result.json.errors`。

**输出**：完整基线交付物。  
**失败分支**：任何单一产物失败不影响其他产物和 `result.json` 生成。

### 第 6 步：Agent 亲核增强与完整性回填

你不能只跑完脚本就结束。必须亲自核验：
1. 随机抽查 3 段原文与 `deliverable.md` 对应段落，确认正文/数字/引用标记未改；
2. 核对 `format_spec.json` 的 explicit 条目与源材料 locator/quote 是否一致；
3. 核对 `result.json` 是否完整回填 `output_contract` 全部字段，并双回显；
4. 如有缺失、冲突或不确定，写回 `result.json` 的 `reviewed_by_agent`、`verified`、`pending_human`、`conflicts`、`changes` 字段；
5. 保留全部基线产物，不删除、不覆盖关键证据。  
**输出**：增强后的 `result.json`（仍保持原契约全字段）与 `/app/work/agent_review.json`。  
**失败分支**：发现关键内容被篡改或丢失 → 立即从 `work` 中恢复原始段落，重新 build 或直接修复 `deliverable.md`，并在 `changes` 记录修复动作。若无法确认，标 `pending_human`，不得伪造通过。

### 第 7 步：selfcheck 与最终收尾

**输入**：第 6 步产物。  
**动作**：运行：

```bash
python3 scripts/main.py selfcheck --input /input --work /app/work --out /app/output
```

按第 8 节自检清单逐项检查；确认 `result.json` 中 `output_contract` 键、原生字段、文件路径全部有效。  
**输出**：最终 `/app/output/result.json`，退出码 0。  
**失败分支**：缺字段 → 先补齐 `result.json`；缺文件 → 先补文件；无法补齐则标 `partial` 并列出缺口。

## 5. 预算策略（64 次模型请求 / 900 秒）

**优先级**：实际效果（40 分）权重最高，先保证全套交付物、格式正确性与保真度；再保证可核验性（sources/uncertainty/changes 真实）；最后补创新和生态说明。

**分配建议**：
- 必须执行：第 0 步 `run` 基线（1 次工具调用）；第 1 步读台账（文件读取，不占大请求）；第 2 步至少读 2 个关键材料（2 次工具调用）；第 3 步写 `draft.json`（文件写）；第 4 步 check（1 次工具调用）；第 5 步 build（1 次工具调用）；第 6 步至少 1 次核验；第 7 步 selfcheck（1 次工具调用）。合计约 8–12 次模型请求（含工具调用）。
- 可选执行：用 `show` 读更多材料（最多 4 次）；深度核对 5 段原文（2–3 次）；重新 build（1–2 次）。
- 何时落盘 partial：第 0 步 `run` 已落盘 partial 或更优；第 5 步 build 刷新；第 6 步核验后回填。任何中断前都确保 `result.json` 已写盘。
- 超时阈值：> 780 秒立即执行第 5 步 build（即使 draft 未写完也产出合法 partial），随后用剩余时间做第 6 步核验。
- 避免无意义循环：同一 `show` 命令不要重复；不逐字读完整个材料；不重复 check 超过 2 次。

## 6. 隐藏案例鲁棒性与异常处理

| 情况 | 行为 | 记录 |
|---|---|---|
| `/input` 为空 | 仍产出 md/docx/format_spec/fidelity/preview，退出 0 | `status=insufficient_evidence`、`degradations` |
| `case.json` 缺失或非法 JSON | 目录扫描 + `task.md` 继续，仍出全产物 | `errors[stage=case]` |
| 无 `output_contract` | 只写 Skill 原生字段 + 不确定性，但保留最小交付 | `uncertainty` |
| 材料缺失/损坏/格式不支持 | 跳过该材料，记录 `sources[].read_note`，继续其他材料 | `sources[].read_note`、`degradations` |
| 无 `draft.json` 或坏 JSON | 确定性兜底抽取；`status=partial` 或 `ok` 但注明 AUTO_EXTRACT | `degradations[handled_by=AUTO_EXTRACT]` |
| 规格 quote 不命中 | 拒收该条，回退挖掘值/默认值 | `degradations[stage=spec]` |
| 无格式要求 | 全套默认规格（默认字体 Liberation Serif） | 每条 `status=inferred` |
| 无 LibreOffice | 保留 docx/md，另写 `preview.txt`，`export_artifact=null` | `degradations[stage=preview]` |
| docx 写入异常 | 用默认规格重写最小 docx | `errors[stage=docx]` |
| 冲突的格式来源（如学校补充规定与期刊模板不同） | 保留首个来源值，双方 locator 写入 conflicts | `result.json.conflicts` |
| 字体缺失（Liberation Serif 不存在） | 回退系统 Serif，但明确记录 | `degradations[stage=font]` |
| 超时（>780s） | 强制 build + 写 result.json；不再新增复杂解析 | `runtime.timeout=true` |

**任何情况下**：退出码 0；`result.json` 必须合法且包含全部必要字段；缺失内容明确标注，不得编造数据或分数。

## 7. result.json 契约与双回显

- 必须动态读取 `/input/case.json` 中的 `output_contract` 字段名，并在 `result.json` 中同时出现在：
  - **顶层**：每个契约字段直接作为顶层键，值与最终交付一致；
  - **嵌套 `output_contract` 对象**：完全复制一份相同的键值。
- `case_id` 必须与 `case.json` 一致（若存在），且顶层和嵌套 `output_contract` 各出现一次。
- 除契约字段外，还必须包含：
  - `status`: 枚举 `ok|partial|insufficient_evidence|input_error`；
  - `sources`: 数组，每项含 `source_id`、`locator`、`quote`、`read_note`；
  - `uncertainty`: 数组，逐条说明不确定项；
  - `pending_human`: 数组，逐条说明需人工确认项；
  - `errors`: 数组，运行错误；
  - `degradations`: 数组，降级说明，含 `handled_by`；
  - `changes`: 数组，修改记录；
  - `coverage`: 内容单元覆盖统计；
  - `compliance_checks`: 逐项格式合规结果；
  - `runtime`: 耗时、命令、时间戳；
  - `reviewed_by_agent`: 布尔或对象，记录 Agent 核验；
  - `verified`: 核验结论；
  - `conflicts`: 冲突项。
- 所有 `output_contract` 字段即使无值也必须保留，置 `null`，不得删除键。

## 8. 自检清单（提交前逐项检查）

- [ ] `python3 -B scripts/main.py --help` 退出码 0。
- [ ] 空 `/input`：`/app/output/` 有 md+docx+format_spec.json+fidelity_report.json+result.json，`result.json` 合法，退出码 0。
- [ ] 契约：`set(output_contract) ⊆ set(result.json)`；`status` 属于四个枚举之一；契约字段顶层与 nested `output_contract` 双回显。
- [ ] `format_spec.json.fields` 32 条，每条有 `value/status`，explicit 都有 `quote` + `locator`。
- [ ] `fidelity_report.json.summary.verbatim_ratio == 1.0`，`numbers_preserved` / `citations_preserved` 为 true。
- [ ] `deliverable.docx` 可被 `zipfile` 打开，含 `word/document.xml`、`word/styles.xml`、`word/footer1.xml`；正文 run 带 `w:rFonts`（字体真进了 run，不只是 style）。
- [ ] `preview.pdf` 存在时页数 ≥1，`pdffonts` 显示字体嵌入；否则有 `preview.txt` 且 `export_artifact=null`。
- [ ] 无 `__pycache__`、`.pyc`、临时文件。
- [ ] 所有 `output_contract` 字段均有值（缺失为 `null`）且未改名。
- [ ] `result.json` 中有 Agent 核验痕迹：`reviewed_by_agent`、`verified`、`pending_human`、`conflicts` 至少一项非空。
- [ ] 未删除或清空任何基线产物，`changes` 只记录增强和修复。
- [ ] `result.json.case_id` 与 `case.json` 一致（若存在）。
- [ ] 若使用路径 A，`/app/work/draft.json` 存在且未被脚本结构化表覆盖。
- [ ] 若使用路径 B，`result.json.degradations` 必须含 `handled_by=AUTO_EXTRACT`。

## 9. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式 |
|---|---|---|---|
| 实际效果·任务完成度 | 15 | 真正把真实稿件按目标模板改到可交付，而非只改几处格式 | `coverage` 列出所有内容单元；`compliance_checks` 逐项通过；`deliverable.docx` 可打开 |
| 实际效果·结果正确性 | 15 | 字号、行距、页边距、栏数、题注位置、参考文献样式符合模板；正文/图表/引用不被错误改动 | `format_spec.json` 每条 explicit 带 quote/locator；`fidelity_report.json.verbatim_ratio=1.0`；`compliance_checks` 全 pass |
| 实际效果·结果完整性 | 5 | 模板要求检查项 32 项全覆盖；原稿内容单元全覆盖 | `format_spec.json.fields` 32 条；`coverage` 统计；`result.json` 无缺键 |
| 实际效果·结果可核验性 | 5 | 他人可按记录复现“从输入件到成品”的过程 | `sources` 带 locator/quote；`changes` 记录修改；`runtime` 记录命令和时间；`references/checklist.md` 提供判定口径 |
| 使用增益·质量增益 | 15 | 与不加载 Skill 相比，格式适配质量提升 | `result.json.compliance_checks`；`fidelity_report.json` 证明保真；文档说明如何对比 |
| 使用增益·效率增益 | 5 | 减少逐项核对、重复排版、试错导出与人工返工 | `runtime` 记录耗时；`result.json.changes` 记录自动处理项；文档说明自动化步骤 |
| 使用增益·增益可验证性 | 5 | 公平对照证明质量或效率改善 | `references/example-trial.md` 提供试跑记录（标注示例）；`runtime` 保留原生 traces；不编造基准分数 |
| 创新增益·新增能力 | 5 | 形成基础 Agent 或现有排版工具难以稳定实现的能力（如从模板反推检查项、保真度比对） | `format_spec.json` 的挖掘证据；`fidelity_report.json` 的逐单元比对；`scripts/main.py` 的 `check` 逻辑 |
| 创新增益·方法改进 | 5 | 模板解析、样式映射、内容锚定、转换与导出校验有实质改进 | `SKILL.md` 第 10 节字段规范；`scripts/docxlib.py` 的 OOXML 落版与读回探针 |
| 创新增益·创新证据 | 5 | 证明创新点相对已有方案的边界和价值 | `references/example-trial.md` 展示实际运行；`references/checklist.md` 记录判定口径；文档说明边界与限制 |
| 可靠体验·调用与易用性 | 3 | Agent 能正确触发和调用，用户能按说明完成一次完整适配 | 单命令 `run` 清晰；frontmatter 描述准确；`--help` 可用 |
| 可靠体验·运行稳定性 | 4 | 不同模板类型、稿件长度、重复运行下持续产出可用文件 | 脚本无外部依赖、幂等；异常降级表覆盖；`result.json` 记录 `status` |
| 可靠体验·异常处理 | 3 | 对模板缺失/版本不明、字体缺失、样式冲突、转换失败、内容无法保真等情况识别与处置 | 第 6 节降级表；`result.json.errors`、`degradations`、`pending_human` 真实填写 |
| 生态贡献·文档完整性 | 3 | 使用说明、依赖环境、支持模板范围、示例、限制与维护信息齐全 | `SKILL.md` 全文；`references/checklist.md`；`references/format_spec_schema.md` |
| 生态贡献·资源可复用性 | 4 | Skill 本体、检查项清单、样式映射脚本、样例输入输出可复用 | 脚本标准库、参数可配置；`references/format_spec_schema.md` 是检查项清单；示例标明 |
| 生态贡献·分享推广价值 | 3 | 沉淀可分享的模板检查清单、案例、实践经验和真实应用价值 | `references/example-trial.md`、`references/checklist.md`、维护说明 |

## 10. 32 项格式规格字段（写 draft 必查）

完整字段名、候选值、判定口径见 `references/format_spec_schema.md`。常用字段如下：

`title.font`, `title.size`, `title.align`, `abstract.font`, `abstract.size`, `body.font`, `body.size`, `body.line_spacing`, `paragraph.spacing`, `first_line_indent`, `page.size`, `page.margin.top`, `page.margin.bottom`, `page.margin.left`, `page.margin.right`, `columns`, `heading.level1.font`, `heading.level1.size`, `heading.level1.numbering`, `heading.level2.font`, `heading.level2.size`, `heading.level2.numbering`, `figure.caption.position`, `table.caption.position`, `table.style`, `reference.style`, `header.content`, `footer.page_number`, `footnote.style`, `formula.style`, `toc.required`, `export.format`.

- `field` 必须精确匹配上述名称；`value` 可为具体值或枚举，如 `Liberation Serif`、`12pt`、`1.5`、`2.5cm`、`below`、`GB/T 7714`、`three-line`。
- 任何披露了具体规格的源材料都应产生一条记录；同一字段多个来源有不同值 → `conflicts` 记录。
- 默认字体：当所有格式来源未规定正文字体时，使用组织方指定 `Liberation Serif`，并标记 `status=inferred`。

## 11. 脚本命令参考（包内真实存在）

- 帮助：`python3 -B scripts/main.py --help`
- 一键全流程：`python3 scripts/main.py run --input /input --output /app/output --work /app/work`
- 初始化索引与 partial 结果：`python3 scripts/main.py init --input /input --work /app/work --out /app/output`
- 查看材料内容：`python3 scripts/main.py show --input /input --work /app/work --material m03 --from 1 --to 60`  
  `python3 scripts/main.py show --input /input --work /app/work --material m02 --items`
- 证据链检查：`python3 scripts/main.py check --input /input --work /app/work --out /app/output`
- 生成完整成品：`python3 scripts/main.py build --input /input --work /app/work --out /app/output`
- 最终自检：`python3 scripts/main.py selfcheck --input /input --work /app/work --out /app/output`

## 12. 生态文档与资源

- `references/format_spec_schema.md`：32 项规格字段定义、候选值与判定口径，是可复用检查清单。
- `references/checklist.md`：提交前自检清单与预期输出。
- `references/example-trial.md`：最小调用示例与示意输出（必须标注为示例，不冒充正式案例结果）。
- `scripts/docxlib.py`：OOXML 落版与读回探针，保持正文 run 字体/样式绑定，验证字体嵌入。
- `scripts/main.py`：命令入口，实现 init/build/selfcheck/show/check/run 与确定性兜底。
- 包内文件均 UTF-8 文本，无 symlink，无外部运行时依赖；离线、纯 Python 3.8+ 标准库可用。

## 13. 必须避免的扣分项

1. 不预设正式答案、不提交预生成案例输出；
2. 不用文件名/领域标签猜测内容，必须解析真实材料原文；
3. 不手工篡改脚本生成的 JSON 结构；
4. 不删除、清空或覆盖基线产物；
5. 不伪造 `golden_standard`、基准分数或未经验证的评分；
6. 不忽略 `output_contract` 字段，必须双回显并保存全部键；
7. 不为追求 `status=ok` 隐瞒 FAIL、缺项或 AUTO_EXTRACT；
8. 不在接近预算时进行无意义的重复解析，导致 `result.json` 缺失或不合法。