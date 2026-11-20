---
name: bilin-paper-translator
description: "Paragraph-aligned, terminology-locked bilingual translation and verification skill for scientific papers. Extracts actual source text, creates stable paragraph IDs, enforces a reusable glossary, protects numbers/units/citations/cross-references/formulas, and produces bilingual, alignment, glossary, verification, and honest partial deliverables with evidence locators. Use when translating a paper/PDF/DOCX/section/abstract into Chinese or another target language, producing side-by-side translation, or verifying an existing translation against source. The Harness Agent must read the actual source; scripts provide utilities and final assembly."
version: 3.0.0
license: MIT
---

# bilin-paper-translator

## 0. 最高优先级：交付、诚实、可复核

本 Skill 的最终目标不是“看起来像翻译”，而是产出可用、可回原文、可机检、可复用的科研文献双语成果。执行顺序始终是：

1. 先产出合法基线，再增量补全；
2. 真实读取材料，不依据文件名或领域标签猜测内容；
3. 术语不摇摆、段落不丢错、数字公式引用不篡改；
4. 不确定、缺失、失败均显式标注，绝不写成人造事实；
5. 任何一步失败都要降级继续，最终必须落盘合法 `result.json` 并让脚本退出码 0。

**修改边界**：结构化产物（`result.json`、`claims.json`、`evidence_table.json` 的结构键、来源编号、locator、quote、覆盖统计等）由 `scripts/main.py` 与 `scripts/engine.py` 生成和回填。Agent 不应手改 JSON 结构；Agent 的真实判断写入 `/app/work/draft.json`、`/app/work/agent_review.json`、`/app/work/pending_human.json`，再由脚本装配。

## 1. Skill 边界

**做**：

- 真实提取 PDF/DOCX/TXT/MD/HTML 论文中的文字层；
- 将全文或任务指定区间切成稳定段号 `P001`、`P002`…；
- 逐段给原文和译文，形成段落级双语对照；
- 锁定术语表并全篇回填同一译名；
- 保护数字、单位、公式、文献引用、图表编号、交叉引用；
- 为每段译文给出来源 `[S#]`、页码/段落/句子级 locator、译法依据；
- 输出双语稿、对齐表、术语表、核验记录。

**不做**：

- 不做摘要式翻译或“大意”改写；
- 不对扫描件/图片做 OCR，不编造图内文字；
- 不联网，不检索，不补造材料外文献、数据或结论；
- 不用预置答案代替实际运行；
- 不生成无依据的 golden_standard、diff_report 或自封分数。

## 2. 单命令入口与双路径

### 主入口

```
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部按以下顺序执行：

1. **init**：盘点 `/input`，识别 case/task/material，抽取真实文本，生成来源编号 `[S#]`、候选分段、候选术语、冲突分组；
2. **build**：
   - 若存在有效 `/app/work/draft.json`，则用 Agent draft 装配；
   - 若不存在 draft，则按确定性兜底：用 init 台账生成逐字 quote + locator 的工作稿，并诚实记录 `AUTO_EXTRACT`；
3. **selfcheck**：校验 `output_contract` 字段、产物文件、`result.json` 合法性、段落/译文/对齐表一致性；
4. **finalize**：写最终 `result.json` 与交付文件；异常也写 partial，并保证退出码 0。

### 旧版/兼容入口

若 `/skills/weekly-skill/scripts/main.py` 没有 `run` 子命令，则按等价两阶段执行：

```
python3 -B scripts/main.py prepare --input /input --output /app/output --work /app/work
```

然后 Agent 阅读材料并写 `/app/work/draft.json`，最后：

```
python3 -B scripts/main.py finalize --input /input --output /app/output --work /app/work
```

不要因 `run` 不存在而停止；两阶段产出的产物与契约完全一致。

## 3. 输入发现

1. 在 `/input` 下递归寻找 `case.json`、`case*.json`、`task.md` 和论文材料。
2. 从 `case.json` 提取：
   - `case_id`；
   - `output_contract`：原样保留所有字段，字段名不重命名、不删除；
   - 任务说明：`task_instruction|instruction|prompt|task|request`，缺失则读 `task.md`。
3. 材料识别优先级：PDF > DOCX > TXT/MD > HTML > CSV/JSON；用魔数识别，不只认扩展名。
4. 术语种子来源：`glossary|terminology|term_list|glossary_seed|terms` 或 `glossary.csv/glossary.json`。
5. 材料没有的对象显式登记，不构造像素、图注、数据或文献。

**核心原则**：必须读实际文件。若抽取文本可疑，Agent 应使用平台可用工具直接查看原 PDF/DOCX，抽查关键段落。

## 4. 输出产物

以下文件必须完整出现；若某类无法生成，也要落空文件或空数组，并在 `result.json` 说明。

| 文件 | 内容 |
|---|---|
| `output/result.json` | 主结果：`case_id/status/status_reason/task/output_contract` + 顶层契约镜像 + `translation/glossary/claims/sources/segments/coverage/verification/uncertainty/pending_human/errors/degradations/changes/runtime/artifacts` |
| `output/translation_bilingual.md` | 逐段：`### P001 · p.3 · body · Results` + 原文行 + 译文行 + 标记 n/m + 术语 k + flags |
| `output/alignment.csv` | 段号/页码/状态/字数/标记数/flags/原文摘录/译文 |
| `output/glossary.csv` | `term,translation,freq,violation_seg_ids,status` |
| `output/verification.json` | `checks{}` + `summary{}` + `rejected_claim_ids` + 启发式说明 |
| `work/segments.json` | 全文分段台账 |
| `work/source_units.md` | 人读原文抽取稿 |
| `work/glossary.csv` | 待填/锁定术语表 |
| `work/draft.json` | Agent 翻译判断草稿 |
| `work/state.json` | 跨进程元数据 |
| `work/translations/*.json` | 分批译文 |

若 `output_contract` 要求额外正文文件（如 `translated_text`、`summary`、`answers`），应按契约生成对应文件，并在 `result.json` 顶层镜像契约字段。

## 5. 工作流：Agent 路径优先，确定性兜底

### 步骤 1：运行基线

先运行主入口命令。脚本完成 init + build/selfcheck/finalize，产出 baseline。此时即使 draft 不存在，也要得到 partial `result.json`、分段台账、来源编号、格式框架。

### 步骤 2：读台账与原文

Agent 阅读：

- `work/source_units.md`；
- `work/segments.json`；
- 原始材料关键页/段。

确认段号、页码、章节、图注、表头是否与实际材料一致；发现漏段、错位、乱码时修正 `work/segments.json` 或记录 `degradations`。

### 步骤 3：写 Agent draft

在 `/app/work/draft.json` 写入真实翻译判断。最小形状：

```
{
  "case_id": "从输入透传",
  "translations": [
    {
      "seg_id": "P001",
      "translation": "忠实完整译文",
      "source_quote": "原文逐字引用",
      "locator": "S1#paper.pdf#p.3#Results#para.1",
      "uncertain": false,
      "note": "术语锁定：..."
    }
  ],
  "glossary": [
    {
      "term": "原文术语",
      "translation": "锁定译名",
      "reason": "全篇统一/学科惯例",
      "source_locator": "S1#paper.pdf#p.1#Abstract"
    }
  ],
  "review": [],
  "changes": []
}
```

规则：

- 每段必须有 `seg_id`；
- 译文必须对应原文内容，不是摘要或改写；
- 数字、单位、公式、引用标记、图表编号必须原样保留；
- 不确定的句子在 `note` 或 `uncertain` 中标注；
- 若时间不足以逐段精译，先完成标题、摘要、图注、表头、含数字/引用的正文段，其余显式标 `"translation": ""` 或 `"untranslated"`。

### 步骤 4：build + selfcheck

再次运行主入口或 `finalize`。脚本校验 draft，按锁定术语表回填，生成双语稿、对齐表、术语表、核验记录，并写 result。

### 步骤 5：人工/Agent 复核

最后检查 `output/result.json`：

- 可解析；
- `case_id` 顶层与 `output_contract` 内各出现一次；
- 所有 `output_contract` 字段被保留并镜像；
- `status` 诚实：`ok` / `partial` / `input_error` / `failed`；
- `errors`、`degradations`、`uncertainty`、`pending_human` 真实；
- `translation.coverage` 数值来自脚本计算，不写假满分。

## 6. 翻译规则：术语稳、段落全、关系准、可核验

### 术语稳

- `work/glossary.csv` 一旦锁定，全篇同译名。
- 标题、摘要、正文、图注、结论中的同一术语不得出现多个译名。
- 若必须改译，只改术语表，并由脚本全篇回填；否则记为 `term_inconsistency`。
- 术语表条目至少包含：`term,translation,freq,violation_seg_ids,status`。

### 段落全

- 段号 `P###` 必须稳定且与 `alignment.csv`、译文文件一一对应。
- 跨页、跨栏、跨章节时，不允许漏段、重复、错位。
- 每页/每节完成后核对段号连续性。

### 关系准

翻译时必须保护：

- 数字与单位：`12.5 mg/kg/d` 不改成 `12.5 mg`；
- 公式与编号：原式、编号、符号不重排；
- 文献引用：`[1]`、`(Smith et al., 2020)` 不丢、不改；
- 图表编号：`Fig. 3`、`Table 2` 保持；
- 否定关系、限定条件、因果/让步关系不翻转；
- 指代对象不混淆。

### 可核验

- 每段译文必须能指回 `seg_id`、页码、章节、原文 quote。
- 译不准的内容标 `uncertain` 或写入 `pending_human`；
- 无法判断或材料缺失写 `undetermined`，不写成事实。

## 7. result.json 双回显与契约

`finalize` 必须：

1. 原样保留平台提供的 `output_contract` 全部字段；
2. 在 `result.json` 顶层也写入每个契约字段的镜像键；
3. `case_id` 至少出现在顶层与 `output_contract` 内；
4. 顶层至少包含：
   - `status`
   - `status_reason`
   - `sources`
   - `segments`
   - `translation`
   - `glossary`
   - `coverage`
   - `verification`
   - `uncertainty`
   - `pending_human`
   - `errors`
   - `degradations`
   - `changes`
   - `runtime`
   - `artifacts`
5. 数组字段缺失时用 `[]`，不要用 `null` 代替预期数组；
6. 未知字段保留，不删除。

示意：

```
{
  "case_id": "...",
  "output_contract": {
    "case_id": "...",
    "...原契约字段": "..."
  },
  "status": "partial",
  "status_reason": "...",
  "task": {...},
  "translation": {...},
  "glossary": {...},
  "sources": [...],
  "segments": [...],
  "verification": {...},
  "uncertainty": [...],
  "pending_human": [...],
  "errors": [],
  "degradations": [...],
  "changes": [...],
  "runtime": {...},
  "artifacts": [...]
}
```

## 8. Rubric 自检清单

### 实际效果 40 分

- [ ] 不是摘要式翻译；每段有完整原文与译文；
- [ ] 术语、指代、否定/限定、数字、单位、公式、文献编号与原文一致；
- [ ] 覆盖任务要求要素：段落、图注/表头、公式编号、文献标记、术语条目；
- [ ] 每段译文有 `seg_id/page/kind/section` 和原文 quote。

### 使用增益 25 分

- [ ] `verification.summary` 中的 `term_consistency_rate`、`coverage_rate`、`token_fidelity.rate` 来自真实脚本检查；
- [ ] 一次运行产出双语稿、对齐表、术语表、核验记录；
- [ ] 不伪造 baseline 对照或白板分数。

### 创新增益 15 分

- [ ] 术语表强制执行，而非只写在提示里；
- [ ] 跨页/跨栏段落接续与段号对齐；
- [ ] 数字/公式/引用/交叉引用保护；
- [ ] 译文自检清单和机器可查核验。

### 可靠体验 10 分

- [ ] Agent 可正确触发；
- [ ] 重复运行稳定；
- [ ] 扫描件、缺文字层、公式图片、损坏材料均有降级路径；
- [ ] 脚本退出码恒 0，异常写入 `errors`。

### 生态贡献 10 分

- [ ] 本文件说明用途、调用方式、输入输出、异常处理；
- [ ] `references/output-schema.md` 与 `references/translation-rules.md` 可供新学科文献复用；
- [ ] 术语表格式、段号约定、未译标注规则清晰。

## 9. 异常与降级

| 情形 | 处置 |
|---|---|
| 材料缺失 | 继续用 `task.md` 与 `case.json` 推导；`status=input_error`，`errors` 说明；产出空段落表 |
| 材料损坏/无法解析 | `errors` + `degradations`；尝试其他格式；若失败，保留文件信息，翻译标 `unavailable` |
| PDF 无文字层/扫描件 | `degradations` 记录 `U1 文字层低可读`；不 OCR，不臆造；有校对稿则用 `--text` 输入 |
| 图片材料 | 标 `image-no-ocr`；图注可读则译，否则 `pending_human` |
| `.doc/.xls/.xlsx/.pptx` | 标 `unsupported`，建议转 pdf/docx/txt |
| `case.json` 损坏/字段缺失 | 捕获解析错误，继续；缺失 `case_id` 置 `"unknown"`，`output_contract={}`，写 `errors` |
| 空输入 | `status=input_error`；字段填 `[]` 或 `null` |
| 无 `output_contract` | 用本 Skill 默认契约，记录 `contract_missing` |
| 接近 780 秒 | 只 finalize，不扩展翻译；未完成段 `untranslated` |
| Agent 未写 draft | build 用 deterministic fallback 生成 quote+locator 工作稿，记录 `AUTO_EXTRACT`，译文列可为空 |

## 10. 预算策略

- 64 次模型请求 / 900 秒 / 16384 tokens per response。
- 先跑脚本基线，保证 partial。
- 预算建议：
  - 盘点与解析 ≤ 10 次；
  - 证据核验 ≤ 20 次；
  - 翻译/修订 ≤ 20 次，按 5–6 段一批写 draft；
  - 自检与 finalize ≤ 10 次；
  - 留 4 次处理异常。
- 优先翻译高权重内容：标题、摘要、正文关键论证段、图表题注、公式/引用周围段。
- 接近预算立即收尾，保证 `result.json` 合法。

## 11. 禁止项

1. 禁止手工修改 `result.json`、`verification.json`、`claims.json` 的结构键和统计值；
2. 禁止生成无来源的 `golden_standard`、自评增益、白板或基准分；
3. 禁止把未译段伪填为译文；
4. 禁止把不确定内容写成事实；
5. 禁止把摘要/大意当译文；
6. 禁止依赖文件名或领域标签补造数据；
7. 禁止在缺失扫描件/图片中编造文字；
8. 禁止不读原文直接复制脚本骨架作为最终成果。

## 12. 最小调用示例

输入：

- `/input/case.json`
- `/input/task.md`
- `/input/paper.pdf`

调用：

```
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出：

- `/app/output/result.json`
- `/app/output/translation_bilingual.md`
- `/app/output/alignment.csv`
- `/app/output/glossary.csv`
- `/app/output/verification.json`

示意输出须标记为示例，不冒充正式案例结果。

## 13. 文档

- `references/output-schema.md`：字段级契约说明；
- `references/translation-rules.md`：分段、术语、保护标记、自检规则；
- `references/workflow-and-example.md`：工作流与示例。

若文档与本文件冲突，以本文件为执行政策；脚本已实现功能以 `scripts/main.py --help` 为准。