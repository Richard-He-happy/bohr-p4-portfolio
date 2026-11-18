---
name: bilin-paper-translator
description: Paragraph-aligned bilingual translation of scientific papers with a locked glossary, verbatim protection of numbers/units/citations/cross-references/formulas, and per-paragraph evidence locations. Use when a user asks to translate a paper, PDF, DOCX, section or abstract into Chinese (or another target language), to produce a source/translation side-by-side table, to enforce terminology consistency across a manuscript, or to verify an existing translation against the source.
version: 1.0.0
license: MIT
---

# bilin-paper-translator（文献翻译：术语锁定 + 段落对齐 + 标记保护 + 自校验）

## 1. 用途与边界

**做**：把一篇真实文献（或 `case` 指定的段落区间）切成稳定段号 `P###`，产出**段落级双语对照**（`translation_bilingual.md`）、可复核对齐表（`alignment.csv`）、可复用术语表（`glossary.csv`），并给出机器可查的保真证据（`result.json` + `verification.json`）。

**不做**：不联网、不检索、不生成材料外的文献/数值/结论；不把“摘要/大意”当译文；不对扫描件做 OCR（无 OCR 时明确降级并要求人工补录）；不自动判定“翻译质量合格”，只报告可机检指标。

**适用**：有文字层的 PDF、DOCX、TXT/MD/HTML 论文或段落；需要术语统一、跨页不漏段、编号与公式不被改写的翻译任务。

## 2. 运行契约

- 入口：`SKILL.md`（本文件）；执行物：`scripts/main.py` + `scripts/engine.py`（纯标准库，无第三方依赖，不联网，不依赖 CWD）。
- 默认目录：输入 `/input`、输出 `/app/output`、中间 `/app/work`；可用 `--input/--output/--work` 或 `INPUT_DIR/OUTPUT_DIR/WORK_DIR` 覆盖。资源路径由 `Path(__file__).resolve().parent` 定位。
- 第一次落盘即为 **partial `result.json`**；任何异常被捕获写入 `errors`，最终无条件 finalize 覆盖；**退出码恒 0**。
- `output_contract` 深拷贝回填，契约字段全部出现（缺值 `null`/`[]`），键名不改、未知字段保留，`case_id` 原样透传。
- 预算：单案例 900s / 64 次模型请求；脚本内超过 780s 只做收尾，脚本本身不调用模型。

## 3. 输入发现（语义识别，不假设键名）

1. 找 `case.json` / `case*.json` / `**/case*.json`（非法 JSON 被捕获，继续用其他材料）。
2. `case_id`、`output_contract` 原样透传；任务说明按语义键取（`task_instruction|instruction|prompt|task|request`），缺省用 `task.md` 前 1000 字。
3. 术语表按语义键取（`glossary|terminology|term_list|glossary_seed|terms`），或 `glossary.csv|glossary.json`；随后 `work/glossary.csv` 覆盖。
4. 递归扫描输入目录，按扩展名 + 魔数识别 PDF/DOCX/TXT/MD/HTML/CSV/JSON/图片；主材料按 `pdf>docx>text/html>csv/json` 与体积择一，其余材料登记在 `sources`。
5. 材料未给的对象明确列缺口（`errors`/`uncertainty`），不构造像素、图注或数据。

## 4. 输出契约

| 文件 | 内容 |
|-|-|
| `output/result.json` | 主结果：`case_id/status/status_reason/task/output_contract` + 契约镜像字段 + `translation{paragraphs,coverage,token_fidelity,source_text}` + `glossary` + `claims` + `sources` + `segments` + `coverage` + `verification` + `uncertainty` + `pending_human` + `errors` + `degradations` + `changes` + `runtime` + `artifacts` |
| `output/translation_bilingual.md` | 逐段：`### P001 · p.3 · body · Results` + 原文行 + 译文行 + `标记 n/m · 术语 k · flags` |
| `output/alignment.csv` | 段落级对齐表（段号/页码/状态/字数/标记数/flags/原文摘录/译文） |
| `output/glossary.csv` | 术语表（`term,translation,freq,violation_seg_ids,status`） |
| `output/verification.json` | `checks{}` + `summary{}` + `rejected_claim_ids` + 启发式说明 |
| `work/` | `segments.json`（全文分段）、`source_units.md`（人读原文）、`glossary.csv`（待填模板）、`state.json`（跨进程元数据，finalize 还原用）、`translations/*.json`（译文） |

字段级定义见 `references/output-schema.md`。

## 5. 核心流程

```
prepare  : 发现输入 → 抽取文本 → 分段 P### → 术语候选 → work/* → partial result.json
translate: 填 work/glossary.csv 的 translation 列；按 work/source_units.md 写
           work/translations/batch_NN.json = {"P001": "译文", ...}（每批 5–6 段）
finalize : 读译文 → 逐段校验 → 双语稿 + 3 个结构化文件 → final result.json
```

- 分段规则：空行/标题/题注/公式/参考文献为界，段内软换行合并（行尾连字符且下行小写时去连字符）；参考文献只在命中 References 标题后按行切分并标 `reference`（不翻译，逐字保留）。
- 术语锁定：`translation` 列非空即视为锁定；此后原文出现该术语的段落，译文必须含同一译名（忽略空白/连字符），违反写入该段并聚合到 `glossary.consistency`。
- 标记保护：公式、`[n]`/作者-年份引用、`Fig./Table/Eq.` 编号、数字、单位全部抽为受保护标记，译文中逐字比对。
- 幂等：可重复 `prepare`/`finalize`；后写入的同段号译文覆盖前者；`--text` 可用人工/OCR 校对稿重建分段。

## 6. 质量规则（rubric → 字段/检查/产物）

| 评分要点 | 实现 | 落点 |
|-|-|-|
| 任务完成度（真译非改写） | 逐段译文 + 未译显式标注，禁止摘要替代 | `translation.paragraphs[].status/translation`、`translation_bilingual.md` |
| 结果正确性（术语/指代/否定/数字/公式/引用） | 标记逐字比对 + 术语强制 + 否定线索 | `token_fidelity`、`glossary.consistency`、`flags` |
| 结果完整性（段落/题注/表头/公式/引用/术语表） | `kind` 分类分段 + 覆盖率（分母=可译段） | `translation.coverage`、`C3_coverage` |
| 结果可核验性 | 每段可回指 + claim 逐字 quote + JSON Pointer | `paragraphs`、`claims`、`verification.json` |
| 使用增益（术语一致率/完整率/准确率） | 同一口径下的三项率值，可与他法对照 | `verification.summary` |
| 效率增益 | 一次调用产出对齐表+术语表+校验，免手工排版 | `alignment.csv`、`verification.json` |
| 新增能力 | 术语强制回填、标记保护、段落对齐、自检清单 | `C4_tokens`、`C5_glossary`、`C6_claims` |
| 可靠体验 | 恒退出 0、partial 先落盘、分阶段降级、可重跑 | `errors`、`degradations`、`status` |
| 生态贡献 | 术语表即学科适配层、schema/规则/示例可复用 | `references/*.md` |

## 7. 证据与定位规范

- 段号：`P###` 稳定，三处一致（`work/segments.json`、双语稿、`alignment.csv`）。
- 定位：`seg_id + page + kind + section`；claim 另带 `pointer: /translation/paragraphs/<seg_id>`。
- quote：必须逐字来自原文分段文本（`quote_status()` 复核，`exact|casefold` 才收）；找不到即剔除并记 `rejected_claim_ids`。
- 可读性分级：`directly_read`（脚本产出，均为原文原句）/ `inferred` / `undetermined`（Agent 追加结论时自行标注，不得冒充原文）。
- 冲突：同一数字/术语在原文出现两种写法时，两种都保留并在 `pending_human` 记“原文冲突”，不擅自统一数值。

## 8. 冲突与人工确认

以下一律进 `pending_human`（含 `reason` 与 `action`）：未译段、术语表空缺、标记缺失段、否定线索不一致段、quote 无法定位的结论、文字层不可读。`uncertainty` 另记 `U1 文字层低可读`、`U2 无译文输入`。**未报告/无法判断的内容不写成事实。**

## 9. 预算与断点

先 `prepare` 落盘 → 分批写译文（每批先写文件）→ `finalize`；任何一步中断，`result.json` 仍为合法 partial，重跑 `finalize` 即可续。脚本 780s 后只收尾不扩展。

## 10. 异常降级分支

| 情形 | 行为 |
|-|-|
| PDF 无文字层/扫描件 | 记录 `degradations`+`U1`，不臆造；改用 `prepare --text <校对稿>` |
| 无 `pdftotext` | 用内置 stdlib 扫描（`extraction_method=stdlib-pdf-scan`，如实记录） |
| 图片材料 | `image-no-ocr`，不编造图内文字 |
| `.doc/.xls/.xlsx/.pptx` | `unsupported`，提示转 pdf/docx/txt |
| `case.json` 损坏 | 捕获，继续用材料；`errors[discover]` |
| 无材料 | `status=input_error`，仍写合法 result.json |
| 无译文输入 | 全部文件照出，译文标未译，`status=partial` |

## 11. 自检清单（交付前）

1. `result.json` 可 `json.load`；`output_contract` 每个字段在顶层存在（`verification.summary.contract_missing` 为空）。
2. `translation.paragraphs` 每条有 `seg_id/page/kind/section`；未译段 `status=untranslated` 且 `translation=""`。
3. `alignment.csv` 行数 = `paragraphs` 长度；段号无重复。
4. `verification.checks` 全 `true` 才可称 `ok`；否则 `status=partial` 且 `status_reason` 说明缺口。
5. `errors/degradations/uncertainty/pending_human` 逐条读过，确认没有把不确定写成事实。

## 12. 最小调用示例（示例，非正式案例结果）

```bash
python3 -B scripts/main.py prepare --input /input --output /app/output --work /app/work
#   → work/source_units.md, work/glossary.csv, work/segments.json, partial result.json
#   → 填 glossary.csv 的 translation 列；写 work/translations/batch_01.json
#     {"P001": "摘要", "P002": "小干扰RNA（siRNA）在 5 mg/kg 下使靶蛋白降低 80% [12]（Fig. 2A）。"}
python3 -B scripts/main.py finalize
#   → status=ok/partial；coverage_rate、token_fidelity.rate、glossary.consistency.rate
```

完整输入/输出示例与失败分支见 `references/workflow-and-example.md`（已标注“示例，非正式案例结果”）。

## 13. 文件清单与版本

```
SKILL.md                          本文件（入口与契约）
scripts/main.py                   驱动：发现/流程编排/装配/result.json
scripts/engine.py                 抽取（PDF/DOCX/HTML/TXT）、分段、标记与术语校验、产物写出
references/output-schema.md       字段字典与未译/拒收约定
references/translation-rules.md   翻译与术语执行口径（术语/标记/关系/对齐/未译）
references/workflow-and-example.md 流程、示例、自检清单、失败分支、复用方式
```

版本 `1.0.0`；依赖：Python ≥3.6 标准库（`zlib/zipfile/json/re/csv/subprocess`）；可选外部命令 `pdftotext`（缺失自动降级）。

## 14. 维护说明

- 换学科只改 `work/glossary.csv`（术语即适配层）；换译入语只改 `translation` 列与 `target_language`。
- 术语候选规则（缩写、二元短语、`全称(缩写)`）在 `engine.build_glossary()`；如需更细候选，扩充 `references/translation-rules.md` 第 1 节并在 CSV 中补行，不改代码。
- 校验阈值（覆盖率 0.999、标记保真 0.9、术语一致 0.8）在 `main.fin()`；调整须同步更新本文与 `references/output-schema.md`。
- 已知限制：无 OCR；`doc/xls/pptx` 不支持；表格逐格文本化后不做行列语义还原；否定/限定为启发式线索，只作人工复核，不作否决。
