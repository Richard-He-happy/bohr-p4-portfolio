---
name: academic-format-template-adapter
description: 把一份真实稿件按给定模板/格式要求（期刊投稿要求、学位论文规范、docx 模板）重新排版：从模板文件与格式要求中抽取可逐项核对的 32 项规格（字体/字号/行距/页边距/栏数/标题层级/题注位置/三线表/参考文献样式/页脚页码），产出可编辑 docx + markdown + format_spec.json + fidelity_report.json + 真实 PDF 预览 + result.json。脚本只负责确定性落版与兜底，最终交付物由 Agent 亲自读材料、推导、撰写/制作并完成可核验增强。当任务涉及“按模板排版”“套用格式要求”“检查格式是否合规”“学位论文/期刊格式适配”“只改格式不改内容”时使用；纯写作、润色、翻译、文献综述不要用它。
version: 4.0.0
---

# 学术格式与模板适配 v4（Agent 亲自推导 + 脚本确定性落版 + 完整交付与可核验增强）

## 0. 核心承诺（必读）

本 Skill 用于把一份真实稿件按给定模板/格式要求重新排版，并交付可复核的结果。**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、默认模板或未经验证的中间文件直接当作成品。所有 `format_spec.json` 的规格判断、`fidelity_report.json` 的保真结论、`result.json` 中的核验记录，都必须来自对实际材料内容的阅读与逐条判断，而不是根据文件名、领域标签或先验猜测补造。

**完整交付优先策略**：进入任务后，先运行本 Skill 脚本产出**全套基线交付物**（所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 必填字段）。后续 Agent 的校验与增强只能在基线上进行；**不得删除、清空或遗漏任何基线与契约字段**。若不确定某项增强是否安全，保留原产物并在 `result.json` 中标注 `reviewed_by_agent` 与 `uncertainty`。

## 1. 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`，以及题面规定的材料（PDF/DOCX/CSV/图片等）。工作目录 `/app/work`；最终产物必须落在 `/app/output`。
- 必须真实解析材料内容（用 `scripts/main.py` 的解析能力或 `pdftotext` 等工具），不得依据文件名或领域标签猜测/补造内容。
- 最终必须有 `/app/output/result.json`，且包含原 `output_contract` 的**全部字段**（键名不改）与 `case_id`；可编辑 Office 产物（`deliverable.docx`）必须额外给出真实渲染的 PDF 预览（`preview.pdf`，若无 LibreOffice 则给出 `preview.txt` 并在 `result.json` 中说明）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本执行时间不占用模型请求，但要避免冗余调用。
- 诚实性：`status`、`sources`、`uncertainty`、`pending_human`、`changes`、`errors` 必须真实；不确定或材料不足要显式标注，不得编造数据、引用、分数。
- 退出码恒为 0：任何异常都捕获进 `result.json.errors` 并 finalize，不得因崩溃导致无 `result.json`。
- 资源限制：Skill 最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无 symlink。运行期产物可为二进制，独立保留。

## 2. 输入发现与材料盘点（脚本支持 + Agent 判断）

1. 递归扫描 `/input/**`（≤80 文件，跳过 `output`/`work`/隐藏目录），按**魔数 + 扩展名**判类型：`%PDF`→pdf、`PK`+`word/document.xml`→docx、图片签名→image。
2. `case.json` 缺失或非法 JSON → 记 `errors[stage=case]`，改用目录扫描 + `task.md` 继续。
3. **原稿判定**：字符量 × 类型权重（docx×1.3）；文件名含 `templ|模板|requir|format|spec|要求|须知` 降权 95%；自身挖到 ≥3 条规格的降权到 30%。结果写 `work/index.json` 的 `manuscript`。
4. **格式来源判定**：除原稿外，任何挖出规格的材料都算格式来源，按条数排序；同一字段多个取值 → 记 `conflicts`（保留首个来源的值，双方 locator 都留档）。
5. 材料没给的对象一律进 `pending_human`，不猜、不补。

## 3. 执行流程（严格按序，每步写清输入/动作/输出/失败分支）

### 第 1 步：盘点输入并立刻落盘 partial result.json

**输入**：`/input` 目录。  
**动作**：运行 `init`，让脚本扫描材料、建索引、打印格式要求清单。  
```bash
python3 scripts/main.py init --input /input --work /app/work --out /app/output
```
同时打印：案件与 `output_contract` 键、材料表（角色/块数/字符数/挖到的规格条数）、32 项规格清单（候选值/来源/locator/逐字 quote，未给出的明确标 `NOT STATED`）、冲突项、原稿前 36 段（带 locator）。  
**输出**：`work/index.json`（后续唯一数据源）、`work/spec_table.draft.json`（预填骨架）、`out/result.json`（合法 partial）。  
**失败分支**：`/input` 为空或 `case.json` 非法 → 继续目录扫描；脚本仍必须写出 `out/result.json` 且退出码 0。记录 `errors[stage=case]` 或 `insufficient_evidence`。

### 第 2 步：用工具真实解析关键材料（Agent 亲自读）

**输入**：第 1 步的 `work/index.json` 与材料清单。  
**动作**：你（Agent）必须读取关键材料的实际内容，而不是只看 `init` 摘要。优先读取格式要求文件和原稿开头/结尾。  
```bash
python3 scripts/main.py show --input /input --work /app/work --material m03 --from 1 --to 60
python3 scripts/main.py show --input /input --work /app/work --material m02 --items
```
需要确认的规格点：字体、字号、行距、页边距、栏数、标题层级、题注位置、三线表、参考文献样式、页脚页码等。每条后续写入的 `explicit` 规格都必须有逐字 quote（去空白后比对，不近似匹配）。  
**输出**：你对材料内容的真实理解，准备写入 `work/spec_table.json`。  
**失败分支**：某材料解析失败或损坏 → 只降级该材料，记录 `sources[].read_note`，将该材料可提供的规格记为 `NOT STATED`；其他材料继续。

### 第 3 步：构建/核对证据 —— 写 `work/spec_table.json`（核心判断，脚本不替你做）

**输入**：第 2 步读到的材料原文。  
**动作**：逐条核对 `init` 的 32 项规格清单，写 `work/spec_table.json`。规则：
- `field` 只能取第 10 节的 32 个字段名；`value` 可写 `12pt`/`2.5 cm`/`小四`/`below`，脚本会规范化。
- `quote` 必须**逐字**出现在源文件里（空白差异可忽略）。查不到 → 该条被拒收并记 `degradations`，绝不改原文凑通过。
- 有 `quote` = `explicit`；无 `quote` = `inferred`（沿用你的值，但仍计入不确定性）。
- 只有 `spec_table.json` 会被当作**已确认**；`spec_table.draft.json` 只是骨架，用它跑 `build` 结果最多 `partial`。
- 示例：
```json
{"case_id": "…",
 "spec": [
  {"field": "body.font", "value": "Liberation Serif", "source": "m02",
   "locator": "m02#L0005",
   "quote": "3. Body text: Liberation Serif, 12 pt, 1.5 line spacing, justified."},
  {"field": "page.margin.left", "value": "3.0cm", "source": "m02",
   "locator": "m02#L0004",
   "quote": "2. Page margins: 2.5 cm top and bottom, 3.0 cm left and right."}
 ],
 "notes": "toc not required by this journal; figure images not present in source"}
```
**输出**：`work/spec_table.json`。  
**失败分支**：材料规格不足 → 保留默认值并标 `inferred`，逐条写进 `uncertainty`；无法安全判断（如“参考文献样式只写了 GB/T 7714 未给版本”）→ 进 `pending_human` 并给出可执行动作。

### 第 4 步：`check` 验证证据链

**输入**：`work/spec_table.json` 与 `work/index.json`。  
**动作**：运行检查。  
```bash
python3 scripts/main.py check --input /input --work /app/work --out /app/output
```
11 项：索引/原稿存在、规格表存在、32 字段齐全、explicit ≥8、quote 逐字命中率、块数、标题数、verbatim 1.0、数字保留、引用保留。结果写 `work/check_report.json`，逐条 PASS/FAIL。  
**输出**：`work/check_report.json`。  
**失败分支**：FAIL 先修规格表（quote 未命中 → 用 `show` 复制原文；数字丢失 → 说明你改动了内容）。若时间不够，可保留 FAIL 项，继续 build 并在 `result.json` 中如实记录；但 `status` 不得为 `ok`。

### 第 5 步：`build` 生成完整成品（无条件 finalize）

**输入**：`work/spec_table.json`、`work/index.json`、`work/check_report.json`。  
**动作**：运行 build，脚本确定性落版并生成全套交付物。  
```bash
python3 scripts/main.py build --input /input --work /app/work --out /app/output
```
产出：`deliverable.docx`（可编辑，style 绑定）、`deliverable.md`、`format_spec.json`、`fidelity_report.json`、`preview.pdf`（有 LibreOffice 时）、`result.json`。  
兜底顺序（任一步失败都不中断）：
1. 有 `spec_table.json` → 逐条校验后应用；
2. 无/坏规格表 → 用挖掘到的规格 + 默认值确定性落版，`status=partial`，并进 `pending_human`；
3. 原稿不可解析 → 写「说明文档」（非空、可打开），`status=insufficient_evidence`；
4. docx 写入异常 → 立即用默认规格重写一次最小 docx，错误入 `errors`。

**输出**：完整基线交付物。  
**失败分支**：任何单一产物失败不影响其他产物和 `result.json` 生成。

### 第 6 步：Agent 亲核增强与完整性回填（关键，防止“不像 Agent 真实推导”）

**输入**：第 5 步的 `format_spec.json`、`fidelity_report.json`、`deliverable.md`、`result.json`。  
**动作**：你不能只跑完脚本就结束。必须亲自核验：
1. 随机抽查 3 段原文与 `deliverable.md` 对应段落，确认正文/数字/引用标记未改；
2. 核对 `format_spec.json` 的 `explicit` 条目与源材料 `locator`/`quote` 是否一致；
3. 核对 `result.json` 是否完整回填了 `output_contract` 全部字段；
4. 如有缺失、冲突或不确定，写回 `result.json` 的 `reviewed_by_agent`、`verified`、`pending_human`、`conflicts`、`changes` 字段；
5. 保留全部基线产物，不删除、不覆盖关键证据。  
**输出**：增强后的 `result.json`（仍保持原契约全字段）与核对记录。  
**失败分支**：发现关键内容被篡改或丢失 → 立即从 `work` 中恢复原始段落，重新运行 build 或直接修复 `deliverable.md`，并在 `changes` 中记录修复动作。若无法确认，标 `pending_human`，不得伪造通过。

### 第 7 步：自检 rubric 与最终回填 result.json

**输入**：第 6 步产物。  
**动作**：按照第 7 节自检清单逐项检查；确认 `result.json` 中 `output_contract` 键、原生字段、文件路径全部有效。  
**输出**：最终 `/app/output/result.json`，退出码 0。  
**失败分支**：缺字段 → 先补齐 `result.json`；缺文件 → 先补文件；无法补齐则标 `partial` 并列出缺口。

## 4. 预算策略（64 次模型请求 / 900 秒）

**优先级**：实际效果（40 分）权重最高，先保证全套交付物、格式正确性和保真度；再保证可核验性（sources/uncertainty/changes 真实）；最后补创新和生态说明。

**分配建议**：
- 必须执行：第 1 步 init、第 2 步至少读 2 个关键材料、第 3 步写 `spec_table.json`、第 4 步 check、第 5 步 build、第 6 步至少 1 次核验、第 7 步收尾。这些是骨架，约 8-12 次模型请求（含工具调用）。
- 可选执行：用 `show` 读更多材料（最多 4 次）；深度核对 5 段原文（2-3 次）；重新 build（1-2 次）。
- 何时落盘 partial：第 1 步 init 已落盘 partial；第 5 步 build 会刷新为完整；第 6 步核验后再次回填。任何中断前都确保 `result.json` 已写盘。
- 超时阈值：> 780 秒立即执行第 5 步 build（即使规格表未写完也产出合法 partial），随后用剩余时间做第 6 步核验。
- 避免无意义循环：同一 `show` 命令不要重复；不逐字读完整个材料；不重复 check 超过 2 次。

## 5. 隐藏案例鲁棒性与异常处理

| 情况 | 行为 | 记录 |
|---|---|---|
| `/input` 为空 | 仍产出 md/docx/spec/fidelity/preview，退出 0 | `status=insufficient_evidence`、`degradations` |
| `case.json` 缺失或非法 JSON | 目录扫描 + `task.md` 继续，仍出全产物 | `errors[stage=case]` |
| 无 `output_contract` | 只写 Skill 原生字段 + `uncertainty` | `uncertainty` |
| 材料缺失/损坏/格式不支持 | 跳过该材料，记录 `sources[].read_note`，继续其他材料 | `sources[].read_note`、`degradations` |
| 规格表缺失/坏 JSON | 确定性落版，`status=partial` | `degradations`、`pending_human` |
| 规格 quote 不命中 | 拒收该条，回退挖掘值/默认值 | `degradations[stage=spec]` |
| 无格式要求 | 全套默认规格（题面字体 Liberation Serif） | 每条 `status=inferred` |
| 无 LibreOffice | 保留 docx/md，另写 `preview.txt`，`export_artifact=null` | `degradations[stage=preview]` |
| docx 写入异常 | 用默认规格重写最小 docx | `errors[stage=docx]` |
| 超时（>780s） | 强制 build + 写 result.json；不再新增复杂解析 | `runtime.timeout=true` |
| 空输入或仅 task.md | 生成说明文档，仍落盘全套骨架 | `status=insufficient_evidence`、`pending_human` |

**任何情况下**：退出码 0；`result.json` 必须合法且包含全部必要字段；缺失内容明确标注，不得编造数据或分数。

## 6. rubric 维度 → 交付要求 → 自证方式对照表

| 评分维度 | 分值 | 交付要求 | 自证方式（写入 result.json 或文件元数据） |
|---|---|---|---|
| 实际效果·任务完成度 | 15 | 真正把真实稿件按目标模板改到可交付，而非只改几处格式 | `coverage` 列出所有内容单元；`compliance_checks` 逐项通过；`deliverable.docx` 可打开 |
| 实际效果·结果正确性 | 15 | 字号、行距、页边距、栏数、题注位置、参考文献样式符合模板；正文/图表/引用不被错误改动 | `format_spec.json` 每条 explicit 带 quote/locator；`fidelity_report.json.verbatim_ratio=1.0`；`compliance_checks` 全 pass |
| 实际效果·结果完整性 | 5 | 模板要求检查项 32 项全覆盖；原稿内容单元全覆盖 | `format_spec.json.fields` 32 条；`coverage` 统计；`result.json` 无缺键 |
| 实际效果·结果可核验性 | 5 | 他人可按记录复现“从输入件到成品”的过程 | `sources` 带 locator/quote；`changes` 记录修改；`runtime` 记录命令和时间；文档含 `references/checklist.md` |
| 使用增益·质量增益 | 15 | 与不加载 Skill 相比，格式适配质量提升 | `result.json.compliance_checks` 全 pass；`fidelity_report.json` 证明保真；文档说明如何对比 |
| 使用增益·效率增益 | 5 | 减少逐项核对、重复排版、试错导出与人工返工 | `runtime` 记录耗时；`result.json.changes` 记录自动处理项；文档说明自动化步骤 |
| 使用增益·增益可验证性 | 5 | 公平对照证明质量或效率改善 | 文档 `references/example-trial.md` 提供试跑记录（标注示例）；`runtime` 保留原生 traces；不编造基准分数 |
| 创新增益·新增能力 | 5 | 形成基础 Agent 或现有排版工具难以稳定实现的能力（如从模板反推检查项、保真度比对） | `format_spec.json` 的挖掘证据；`fidelity_report.json` 的逐单元比对；`scripts/main.py` 的 `check` 逻辑 |
| 创新增益·方法改进 | 5 | 模板解析、样式映射、内容锚定、转换与导出校验有实质改进 | `SKILL.md` 第 10-12 节的字段与证据规范；`scripts/docxlib.py` 的 OOXML 落版与读回探针 |
| 创新增益·创新证据 | 5 | 证明创新点相对已有方案的边界和价值 | `references/example-trial.md` 展示实际运行；`references/checklist.md` 记录判定口径；文档说明边界与限制 |
| 可靠体验·调用与易用性 | 3 | Agent 能正确触发和调用，用户能按说明完成一次完整适配 | `SKILL.md` 第 8 节命令清晰；frontmatter 描述准确；`--help` 可用 |
| 可靠体验·运行稳定性 | 4 | 不同模板类型、稿件长度、重复运行下持续产出可用文件 | 脚本无外部依赖、幂等；异常降级表覆盖；`result.json` 记录 `status` |
| 可靠体验·异常处理 | 3 | 对模板缺失/版本不明、字体缺失、样式冲突、转换失败、内容无法保真等情况识别与处置 | 第 5 节降级表；`result.json.errors`、`degradations`、`pending_human` 真实填写 |
| 生态贡献·文档完整性 | 3 | 使用说明、依赖环境、支持模板范围、示例、限制与维护信息齐全 | `SKILL.md` 第 15-16 节；`references/checklist.md`；`references/format_spec_schema.md` |
| 生态贡献·资源可复用性 | 4 | Skill 本体、检查项清单、样式映射脚本、样例输入输出可复用 | 脚本标准库、参数可配置；`references/format_spec_schema.md` 是检查项清单；示例标明 |
| 生态贡献·分享推广价值 | 3 | 沉淀可分享的模板检查清单、案例、实践经验和真实应用价值 | `references/example-trial.md`、`references/checklist.md`、维护说明；README 内容在本 SKILL.md |

**注意**：质量与增益以平台固定案例、基础 Agent/Skill Agent 对照结果和可核验记录为依据；文字自述不能替代实际运行证据。本 Skill 必须保留每步运行数据，便于平台复核。

## 7. 自检清单（提交前逐项检查）

- [ ] `python3 -B scripts/main.py --help` 退出码 0。
- [ ] 空 `/input`：`out/` 有 md+docx+2 个 json，`result.json` 合法，退出码 0。
- [ ] 契约：`set(output_contract) ⊆ set(result.json)`，`status` 属于四个枚举值之一（`ok|partial|insufficient_evidence|input_error`）。
- [ ] `format_spec.json.fields` 32 条，每条有 `value/status`，`explicit` 都有 `quote` + `locator`。
- [ ] `fidelity_report.json.summary.verbatim_ratio == 1.0`，`numbers_preserved`/`citations_preserved` 为 true。
- [ ] `deliverable.docx` 可被 `zipfile` 打开，含 `word/document.xml`、`word/styles.xml`、`word/footer1.xml`；正文 run 带 `w:rFonts`（字体真进了 run，不只是 style）。
- [ ] `preview.pdf` 存在时页数 ≥1，`pdffonts` 显示字体嵌入；否则有 `preview.txt` 且 `export_artifact=null`。
- [ ] 无 `__pycache__`、`.pyc`、临时文件。
- [ ] 所有 `output_contract` 字段均有值（缺失为 `null`）且未改名。
- [ ] `result.json` 中有 Agent 核验痕迹：`reviewed_by_agent`、`verified`、`pending_human`、`conflicts` 至少一项非空。
- [ ] 未删除或清空任何基线产物，`changes` 只记录增强和修复。
- [ ] `result.json.case_id` 与 `case.json` 一致（若存在）。

## 8. 脚本调用命令（包内真实存在）

- 帮助：`python3 -B scripts/main.py --help`
- 初始化索引与 partial 结果：
  ```bash
  python3 scripts/main.py init --input /input --work /app/work --out /app/output
  ```
- 查看材料内容：
  ```bash
  python3 scripts/main.py show --input /input --work /app/work --material m03 --from 1 --to 60
  python3 scripts/main.py show --input /input --work /app/work --material m02 --items