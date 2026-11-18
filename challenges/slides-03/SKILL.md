---
name: academic-talk-organizer
description: 把论文/研究材料组织成可上台的学术汇报：按听众、时长、页数生成逐页主张与要点、真实可编辑的 pptx（含逐页讲稿备注）、逐页证据映射（locator + 逐字 quote）、页数与版式合规检查，并导出 PDF 预览。适用于组会/答辩/评审等"从材料到可讲页面"的任务；不适用于论文精读、成稿写作或科研绘图本身。
version: 1.1.0
---

# 学术汇报内容组织（academic-talk-organizer）

## 1. 用途与边界

把**已有**研究材料（PDF/DOCX/MD/TXT/CSV/XLSX/PPTX）转成一份可上台的学术汇报：页级主张、要点、讲稿、证据定位、可编辑 pptx、PDF 预览。

- **做**：内容取舍、叙事顺序、页级组织、图表引用绑定、模板/母版适配、导出与合规检查。
- **不做**：论文精读与翻译、论文成稿写作、科研绘图本身、编造数据或参考文献。
- **不适用**：材料为空或全部为图像且无文字层时，只能给缺口页，不能生成"看似完整"的科学内容。

## 2. 运行契约（评测时的实际路径）

| 项 | 值 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/` 下材料（递归） |
| 工作区 | `/app/work`（本 Skill 写 `materials.json`、`index.md`、`slide_plan.json`、`check_report.json`） |
| 产物 | `/app/output/`：`presentation.pptx`、`preview.pdf`、`slide_plan.md`、`content_map.json`、`compliance_checks.json`、`result.json`，以及 5 个核验资产（见第 11 节） |
| 依赖 | Python 3 标准库；不联网；不依赖 CWD。`soffice/libreoffice`、`pdftotext` 可选，缺失自动降级 |
| 退出码 | 恒 0；任何异常都写进 `result.json.errors` |
| 预算 | 64 次模型请求 / 900 秒；脚本内部 ~5 秒完成 |

`result.json` 原样回填 `output_contract` 全部字段（缺值 `null`/`[]`），并带 `case_id`、`status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`deliverables`，以及 `golden_standard`、`diff_report`、`version_history`、`self_check` 四个核验字段（路径+计数，文件见第 11 节）。

## 3. 工作流（顺序执行，不要跳步）

```bash
cd /app/work 2>/dev/null || cd .
python3 /skills/weekly-skill/scripts/main.py init
python3 /skills/weekly-skill/scripts/main.py show --grep '<关键词>'
#   ← 你（Agent）据此手写 work/slide_plan.json（见第 4 节）
python3 /skills/weekly-skill/scripts/main.py check          # 逐字 quote 校验，FAIL 就地修
python3 /skills/weekly-skill/scripts/main.py build          # 渲染 pptx + 预览 + 全部结果文件
```

脚本路径若不是 `/skills/weekly-skill`，用 `$(dirname $(dirname ...))` 或直接 `python3 scripts/main.py`；脚本内部按 `__file__` 定位资源，与 CWD 无关。

**为什么必须由你先写计划**：`init` 只建立材料索引（`[M1#p7]` 这类 locator），`build` 不会替你"读懂论文"。你读 `show` 的原文、判断听众与取舍、写 `slide_plan.json`，脚本只负责校验与渲染——这是本 Skill 与"一键模板生成"的区别。

## 4. `work/slide_plan.json` 结构（本 Skill 的输入契约）

```json
{
  "deck_title": "总标题",
  "subtitle": "副标题",
  "audience": "听众（如：课题组组会 / 答辩评委）",
  "duration_min": 12,
  "target_slides": 8,
  "goal": "这次汇报要达成的可检查目标",
  "narrative": [{"act": "动机", "slides": "2-3", "purpose": "建立共识"}],
  "slides": [
    {"n": 1, "title": "标题页", "layout": "title", "subtitle": "副标题", "bullets": [],
     "notes": "开场 30 秒说什么"},
    {"n": 2, "title": "页标题（一句话结论）", "claim": "本页唯一主张",
     "bullets": [{"text": "听众能听懂的要点", "locator": "M1#p12",
                  "quote": "源材料中逐字出现的一段原文"}],
     "visual": "用哪张图/表；无图则写'无'", "evidence_strength": "strong|moderate|weak",
     "notes": "讲解口径：先给什么、被追问时先答什么"}
  ],
  "qa": [{"q": "可能的追问", "a": "口径一致的回答", "backup": "备用页/页码"}]
}
```

字段规则：每张内容页 **3–5 条** `bullets`；每条至少给 `quote`（逐字）或 `locator`；`notes` 必须**新增信息**（讲法、条件、风险），不能复述页面文字；`layout: "title"` 仅用于首页。

## 5. 内容组织规则（评分看这里）

1. **从约束反推结构**：先读 `init` 输出的 `hints`（audience/duration/slides）。无页数要求时按 `1 页 ≈ 1.2–1.5 分钟` 估算并写入 `target_slides`。
2. **听众决定取舍**：组会→方法与进度、风险优先，背景 1 页；答辩/评审→创新点与边界，证据强度优先。术语只解释听众可能不懂的。
3. **叙事不按论文目录搬运**：问题 →（为什么现有做法不够）→ 方法 → 关键结果 → 边界与结论；每页回答一个问题。
4. **页标题写结论，不写章名**：`"Top-1 从 31.4% 到 46.8%"` 优于 `"结果"`。
5. **数字只在源材料里有理**：百分比、样本量、时长、p 值必须能在 `quote` 中逐字找到；跨页引用同一数字要口径一致。
6. **证据强度**：单数据集/单模型/无对照 → `moderate` 或 `weak`，并在 `notes` 写清适用条件；不要把相关性写成因果。
7. **问答准备**：至少 2 条，覆盖机制、数据、对照、局限；答案与页面口径一致，并指向备用页。

## 6. 证据规范（可核验性的全部来源）

- locator 形如 `M<序号>#p<段号>`：`M1` 是 `init` 生成的材料编号，`p12` 是该材料的第 12 段（PDF 为 pdftotext 的段落切分）。用 `show` 复制，不要手写猜。
- `quote` 必须与原文**逐字一致**（可跨行，脚本按去空白后比对）。改写、翻译、拼接都会 FAIL。
- 一条断言对应一条证据；同一段可支撑多条，但不要一页只用一条证据堆 5 条要点。
- 材料没给的（图、数值、对照）写进 `pending_human` 或 `visual: "无（材料未提供）"`，**绝不补造**。
- `content_map.json` 会记录每条要点的 `quote`、`locator` 与脚本解析出的 `verified` 位置，供他人复核。

## 7. 模板与导出

- 输入含 `.pptx`（模板/起始稿）时，`build` 默认继承其 **母版、版式、主题与字体**，替换幻灯片内容；`compliance_checks.template` 记录 `mode`（`template_rebuilt` / `builtin_master`）。模板继承失败会自动回落到内置母版并写入 `degradations`——不要因此中断。
- 无模板时用内置母版：16:9（12192000×6858000 EMU）、深蓝标题（1F4E79）、Arial / Microsoft YaHei。
- 预览：优先 `soffice --convert-to pdf` 生成 `preview.pdf`；不可用时用标准库生成文本版 PDF 并如实记录降级。pptx 与 pdf 页数由脚本交叉核对。
- pptx 为真实 OOXML（zip 可解、含 `ppt/slides/slideN.xml` 与 `ppt/notesSlides/`），可直接在 PowerPoint/WPS/LibreOffice 中编辑。

## 8. 兜底与异常分支（脚本已实现，不要自己绕过）

| 情况 | 脚本行为 | 你要做的 |
|-|-|-|
| `slide_plan.json` 缺失/不合法（quote 找不到、页数不符、要点不在 3–5） | 用确定性兜底计划：直接取源材料句子分段成页，每页 3–5 条，带 locator+quote | 尽量先 `check` 修好；兜底内容不体现你的判断，质量分低 |
| 材料解析失败（个别文件） | 该材料记为 `errors`，其它材料继续 | 在 `uncertainty` 说明影响 |
| 材料全为图像/无文字层 | 只给缺口页 + `input_error`/`partial` | 在 `pending_human` 要求提供文字版 |
| 模板继承失败 | 回落内置母版 + `degradations` | 交付时提示复核版式 |
| LibreOffice 缺失 | 标准库文本 PDF + `degradations` | 提示桌面端复核字体/换行 |
| 输入为空/`case.json` 坏 JSON | 仍写合法 `result.json`（`input_error`/`partial`）与 5 个最小核验资产，退出 0 | 报告缺什么 |

## 9. 完成前自检（逐条核对）

- [ ] `check` 无 error：`quotes_checked == quotes_verified`，且 `usable: true`
- [ ] 页数 = `hints.slides`（或你说清为什么不同）；每页 3–5 条要点
- [ ] 每页 `notes` 非空且不是页面文字的复述（`compliance_checks.notes_not_repeating`）
- [ ] `content_map.json` 每条要点都有 `locator` 与 `verified`
- [ ] `presentation.pptx` 存在且 `pptx_editable.pass = true`；`preview.pdf` 页数与 pptx 一致
- [ ] `result.json` 的 `output_contract` 字段齐全，`status` 与真实完成度一致
- [ ] 缺口都进了 `pending_human`／`uncertainty`，没有把推断写成事实
- [ ] 5 个核验资产在 `output/`；`self_check.overall` 与 deviation 处置见 `diff_report.md` 第 4 节

## 10. 最小调用示例（示例，非正式案例结果）

输入（`/input/case.json` 摘要）：
```json
{"case_id":"demo-001","audience":"课题组组会","duration_minutes":12,"slide_count":8,
 "output_contract":{"slide_plan":null,"presentation_file":null,"content_map":null,
   "compliance_checks":null,"preview":null,"coverage":{"slides":null,"quotes_checked":null}}}
```
材料 `paper.md` 含 `Top-1 accuracy improves from 31.4% to 46.8% on the 500-reaction subset.`

调用与示意输出（**示例，非正式案例结果**）：
```bash
python3 scripts/main.py init      # materials=1, hints={"audience":"课题组组会","duration":12,"slides":8}
python3 scripts/main.py show --grep accuracy
#   [M1#p12] Top-1 accuracy improves from 31.4% to 46.8% on the 500-reaction subset.
# → 手写 work/slide_plan.json（4 页内容页 + 标题页，12 条 quote）
python3 scripts/main.py check     # {"quotes_checked":12,"quotes_verified":12,"usable":true}
python3 scripts/main.py build     # status=partial（页数 5≠要求 8，已写 pending_human）
```
产物：`presentation.pptx`（5 页，含逐页备注）、`preview.pdf`（5 页）、`slide_plan.md`、`content_map.json`、`compliance_checks.json`、`result.json`。

## 11. 核验资产（v1.1.0 新增，`build` 自动生成）

- `golden_standard.json` — 金标准：约束 K1–K5、幕结构与预算秒、逐页期望（`locator`+`quote`，缺证页标 `expected_gap`）、讲解逻辑 L1–L7（带 task.md 引文）、验收项 C01–C20。复核：按 `pages[].n` 与产物逐页对齐。
- `diff_report.md` — 逐项对照 `pass`/`deviation`/`missing`/`unmeasured`+依据，含幕结构、页级证据、处置。
- `version_history.md` — 包版本 v1.0.0→v1.1.0 与产物 v0 骨架→v1 成稿：改了什么、为什么、**如何回退**（可照抄命令）。
- `run.log` — 追加式 `[+秒]` 步骤、耗时、降级、异常（`init→show→check→build` 累积）。
- `self_check.json` — 契约字段、证据覆盖率、数字一致、3 个兜底探针；`overall` 只看运行完整性（gates+缺失项），质量看 `diff.coverage`。

- 由 `scripts/audit.py` 生成，`build` 重跑即重算，无手写答案。
- 单项失败只降级该项并写 `degradations`。

## 12. 文件清单与维护

```
SKILL.md                         本说明（用途/契约/流程/规则/异常/核验资产）
scripts/main.py                  init|show|check|build（索引、校验、编排、结果）
scripts/makeppt.py               OOXML pptx 生成（内置母版/模板继承）+ LibreOffice 导出
scripts/audit.py                 金标准/差异对照/版本记录/运行日志/自检（纯规则，无 LLM）
references/slide_plan_schema.md  slide_plan.json 字段、locator 约定
references/organizing_rules.md   听众/时长/叙事/问答规则与检查清单
```
版本 1.1.0（v1.0.0 + 核验资产），纯标准库、无网络。维护：新增材料类型只需扩展 `main.py: extract()`；新增版式只需改 `makeppt.py` 的 `LAYOUT`。已知限制见第 1 节与 `references/organizing_rules.md` 末节。
