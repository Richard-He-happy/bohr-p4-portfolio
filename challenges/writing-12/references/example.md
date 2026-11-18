# 端到端示例（示例，非正式案例结果）

下面是一个**为了演示接口而构造的小工程**，不是平台正式案例，也不是提交答案。数字与结论
仅用于说明字段如何产生。真实运行时，事实与引用全部来自 `/input` 材料。

## 1. 输入

```
/input/case.json
/input/main.tex
/input/refs.bib
/input/artifacts/material.md
```

`case.json`（节选）：

```json
{
  "case_id": "demo-latex-01",
  "task_instruction": "Fix the manuscript so that it compiles and keep every reported number.",
  "organizer_workorder": [
    {"id": "WO-1", "action": "use booktabs three-line tables"},
    {"id": "WO-2", "action": "cite smith2020 for the yield of 45.2 %"}
  ],
  "output_contract": {
    "manuscript_tex": null, "preserved_facts": [], "evidence_map": [],
    "change_log": [], "compile_status": null, "reviewer_notes": null
  }
}
```

`main.tex` 里刻意埋了四类问题：

```latex
\documentclass{article}
\usepackage{graphicx}
...
The conversion reached 45.2 % after 30 min at 298 K and the sample size was 128.   % ← E19：% 之后整行被注释
A mis-typed identifier like sample_id breaks the build, as does R&D shorthand.      % ← E18：裸 _ 与 &
\begin{tabular}{lcccccc}                                                            % ← 5 列内容 / 7 列声明
```

## 2. 调用

```bash
python3 -B scripts/latex_doctor.py --input /input --out /app/output --work /app/work
```

## 3. 实际运行结果（示例工程，本机 TeX Live，pdflatex 三轮）

```json
{"status": "partial", "case_id": "demo-latex-01", "diagnostics": 7,
 "facts": "9/9", "changes": 7}
```

- `diagnostics`（修复前）：`E19_PERCENT` ×2（11、12 行）、`E18_MATH_MODE` ×2（13、26 行）、
  `E08_TABLE_CELLS`、`H_WIDE_TABLE`、`E03_PACKAGE`（`\toprule` 缺 `booktabs`）。
- `change_log`：`R06_percent` ×2、`R02_package` ×1、`R04_escape` ×2，另有 2 条 `model_edit`
  （baseline diff 生成）。
- `diagnostics_residual`：`E08_TABLE_CELLS`、`H_WIDE_TABLE`（列声明需作者决定是否增列）、
  `E09_REF`、`E10_CITE`（引用了不存在的图与未提供的文献 → 进 `pending_human`）。
- `compile`：`passes = [pdflatex exit 0, pdflatex exit 0, pdflatex exit 0]`、
  `pdf_exists = true`、`pdf_pages = 2`、`errors = []`（bibtex 未触发：文档未声明 `\bibliography`）。
- `preserved_facts`：9 条数字（45.2 %、30 min、298 K、128、12.7 % 等）全部 `present = true`；
  这正是 `R06_percent` 的价值——不转义 `%`，后半行的数字与引用会整段消失。
- `workorder_receipt`：`WO-1 → done_verified`（`booktabs` 锚点命中）、
  `WO-2 → manual_review_required`（「cite smith2020 ...」无机器可判锚点，需人工/模型确认）。
- `verification.json`：`{"status": "ok", "issues": []}`。

## 4. 产物

| 文件 | 说明 |
|---|---|
| `out/deliverable.tex` | 已修复主文件（`45.2 \%`、`sample\_id`、`R\&D`、补 `booktabs`） |
| `out/deliverable.pdf` | 2 页编译产物 |
| `out/tex_project/` | 完整工程，可直接再编译 |
| `out/baseline/` | 原始快照，供 `change_log` 逐字回查 |
| `out/result.json` | 全部结构化记录 + 契约回填 + `contract_fill` |
| `out/build_report.md` | 人读摘要 + 复现命令 |

## 5. 边界情况实测

| 输入 | 结果 |
|---|---|
| 空目录（无 `case.json`、无材料） | `status=input_error`，`errors[case_missing]`，退出码 0，`result.json` 合法 |
| `case.json` 截断（坏 JSON） | `status=insufficient_evidence`，`errors[case_json_invalid]`，退出码 0 |
| 只有 `material.md`、没有 `.tex` | 生成 `% SCAFFOLD` 骨架并编译成功（1 页），`degradations[scaffold_used]`，事实列表提示作者补写 |

## 6. 这个示例说明了什么、没说明什么

说明：错误分类与 `file:line` 定位、自动修复的保守边界、事实逐字守恒、契约回填与独立审计
可以在一次运行内闭环。

没说明：真实期刊模板（`elsarticle`/`IEEEtran`/学位论文类）的版式合规程度、跨 TeX 发行版的
差异、以及正式案例的评分——这些必须在平台案例上运行后才能下结论。
