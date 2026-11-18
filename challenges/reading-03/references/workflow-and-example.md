# 调用流程、最小示例与自检清单

> 本文所有输入与输出均为**示例，非正式案例结果**，仅用于说明接口与流程；不构成任何真实文献的译文或评测结论。

## 1. 端到端流程（Agent 执行顺序）

```bash
# 0) 环境（默认 /input、/app/output、/app/work；可用参数或环境变量覆盖）
python3 -B scripts/main.py --help

# 1) 发现输入 → 抽取 → 分段 → 术语候选 → 写 partial result.json
python3 -B scripts/main.py prepare

# 2) 读 work/source_units.md（分段原文）与 work/glossary.csv（术语模板）
#    填 glossary.csv 的 translation 列；按段号写 work/translations/batch_01.json
#    {"P001": "译文", "P002": "译文", ...}

# 3) 装配 + 校验（可重复执行，后写的译文覆盖同名段号）
python3 -B scripts/main.py finalize
```

- `prepare` 与 `finalize` 可分开进程执行（`finalize` 会自动重读 `case.json` 与 `segments.json`）。
- 单次 `run` = `prepare` + `finalize`，用于无人工介入的完整性检查（此时 coverage=0，status=partial，产物齐全）。
- 批处理建议：每批 5–6 段或约 1500 字符；每批写一个 `work/translations/batch_NN.json`，先落盘再继续，避免长回复被截断导致丢段。

## 2. 最小输入示例（示例，非正式案例结果）

`/input/case.json`

```json
{
  "case_id": "DEMO-001",
  "task_instruction": "把摘要与结果段译为简体中文，保留数字、单位与文献标记。",
  "glossary": {"siRNA": "小干扰RNA"},
  "output_contract": {
    "case_id": "string",
    "translation": {"paragraphs": "array", "coverage": "object"},
    "glossary": "array",
    "claims": "array",
    "status": "string",
    "uncertainty": "array",
    "pending_human": "array"
  }
}
```

`/input/paper.txt`（节选，仅示例）

```
Abstract
Small interfering RNA (siRNA) reduced target protein by 80% at 5 mg/kg [12] (Fig. 2A).

2. Results
Serum cholesterol fell from 3.4 mmol/L to 1.9 mmol/L (n = 24), whereas controls showed no change [13,14].
```

`prepare` 后 `work/` 关键片段：

```
### P001 · p.1 · heading · Abstract
Abstract
### P002 · p.1 · body · Abstract
Small interfering RNA (siRNA) reduced target protein by 80% at 5 mg/kg [12] (Fig. 2A).
```

`work/translations/batch_01.json`

```json
{"P001": "摘要",
 "P002": "小干扰RNA（siRNA）在 5 mg/kg 剂量下使靶蛋白降低 80% [12]（Fig. 2A）。"}
```

`finalize` 后 `output/`：

| 文件 | 内容 |
|-|-|
| `result.json` | `status`、`translation.paragraphs[]`、`glossary`、`claims`、`verification`、`uncertainty`、`pending_human` |
| `translation_bilingual.md` | 每段 `### P002 · p.1 · body · Abstract` + 原文行 + 译文行 + `标记 4/4 · 术语 1 · ok` |
| `alignment.csv` | 段号/页码/状态/字数/标记数/flags/原文摘录/译文 |
| `glossary.csv` | `siRNA,小干扰RNA,2,,locked` |
| `verification.json` | `checks{}` 与 `summary{}`（覆盖率、保真率、术语一致率、被拒 claim） |

示意 `result.json` 片段（示例，非正式案例结果）：

```json
{"case_id": "DEMO-001", "status": "ok",
 "translation": {"coverage": {"paragraphs": 3, "translated": 3, "references_preserved": 0,
                              "coverage_rate": 1.0},
                 "token_fidelity": {"expected": 9, "kept": 9, "missing": 0, "rate": 1.0}},
 "verification": {"passed": true, "checks": {"C1_contract": true, "C3_coverage": true, "C4_tokens": true}},
 "pending_human": []}
```

## 3. 自检清单（交付前逐项过）

1. `ls work/`：`segments.json`、`source_units.md`、`glossary.csv` 存在且段号连续（P001…P00N 无跳号）。
2. `work/glossary.csv`：关键术语 `translation` 列已填；未填的行不影响运行，但会拉低 `C5_glossary`。
3. `work/translations/*.json`：键名与段号严格一致；抽查 3 段与 `source_units.md` 对齐无错位。
4. `output/result.json`：`status` 与 `status_reason` 一致；`output_contract` 深拷贝存在；契约字段齐全（看 `verification.summary.contract_missing` 应为空）。
5. `output/result.json`：`translation.paragraphs[]` 每条有 `seg_id/page/kind/section`；未译段 `status=untranslated` 且 `translation=""`。
6. `output/translation_bilingual.md`：没有“摘要代替译文”的段落；未译处显示 `【未译 untranslated】`。
7. `output/alignment.csv`：行数 = `translation.paragraphs` 长度；`flags` 中 `token_missing` 的段能指回原文标记。
8. `output/verification.json`：`checks` 全 true 才算 `ok`；`rejected_claim_ids` 非空说明 quote 未逐字命中，需修 claim 或原文。
9. `errors`/`degradations`/`uncertainty`/`pending_human` 四项逐条读过，确认没有把“不确定”写成事实。

## 4. 失败与降级分支

| 情形 | 脚本行为 | 结果字段 | 人工/Agent 动作 |
|-|-|-|-|
| 无 `case.json` | 继续执行，`case_id=null` | `errors[discover]`、`status=input_error` 或 partial | 检查 `/input`，或按语义键补 `case*.json` |
| `case.json` 非法 JSON | 捕获，保留其他材料继续 | `errors[discover]` | 手工修 JSON 后重跑 |
| PDF 无文字层/扫描件 | 内置扫描结果不可读 → 记录降级，不臆造 | `degradations`、`uncertainty.U1` | 用 OCR 或人工转录成 `work/clean.txt`，`prepare --text work/clean.txt` |
| 环境无 `pdftotext` | 用内置扫描，记录降级 | `degradations` | 若文本质量差，同上改用 `--text` |
| 图片材料 | 不 OCR，不编造图内文字 | `degradations` | 需要图表数据时人工补录并标注“人工转录” |
| `.doc/.xls/.xlsx/.pptx` | 明确不支持，记录降级 | `degradations` | 先转 pdf/docx/txt |
| 无 `translations/*.json` | 仍产出全部文件，译文标未译 | `uncertainty.U2`、`pending_human.H1`、`status=partial` | 补译文后重跑 `finalize` |
| 部分段未译 | 覆盖率 <1，列未译段号 | `coverage_rate`、`pending_human.H1` | 补译或确认属参考文献 |
| 标记缺失 | 该段 `missing` + `token_missing` | `token_fidelity` | 回填数字/单位/编号后重跑 |
| 术语不一致 | 该段 `gviol` + 全局 `violations` | `glossary.consistency` | 统一译名后重跑 |
| claim 引文无法定位 | 剔除并记 ID | `verification.rejected_claim_ids` | 改引原文原句 |
| 运行异常 | 捕获、保留已写产物、退出码仍 0 | `errors[stage]` | 读 `errors.trace` 定位，重跑 `finalize` |

## 5. 复用与扩展

- 换学科：只改 `work/glossary.csv`（术语表即学科适配层），脚本与分段规则不变。
- 换译入语：`target_language` 由案例判定；术语表 `translation` 列填目标语即可，校验逻辑与语言无关（数字/单位/编号体系通用）。
- 换材料：`main.py --input <dir>` 指向任意目录；PDF/DOCX/TXT/MD/HTML 自动识别，其余格式按第 4 节降级。
- 做对照评测：同一案例分别跑「无 Skill 的基础 Agent」与「加载本 Skill 的 Agent」，比较 `coverage_rate`、`token_fidelity.rate`、`glossary.consistency.rate` 与 `pending_human` 条数即可形成可复核的增益证据。
