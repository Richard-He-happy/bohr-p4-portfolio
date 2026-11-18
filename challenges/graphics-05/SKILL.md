---
name: scientific-graphical-abstract
description: Build a single-page, editable graphical abstract (problem → method → key results → implication) from supplied paper materials, delivered as layered SVG + vector PDF (+PNG) with a per-element evidence map. Use when the task asks for a graphical abstract, TOC figure, mechanism/pipeline summary figure, or a figure that must stay editable and traceable to the source text.
version: 1.0.0
---

# Scientific Graphical Abstract

## 1. 用途与边界

把一份论文材料压缩成**单页四段式图形摘要**：研究问题 → 方法路线 → 核心结果 → 结论/意义。
交付物是**可继续编辑**的分层 SVG、真实矢量 PDF（尽力附 PNG），以及「每个图元 → 来源 locator + 逐字 quote」的 content_map。

做：实体/关系/数值的抽取与版面化、四段结构、图例与单位、可编辑源文件、导出检查、来源映射。
不做：论文正文写作、统计分析、新实验设计；**不补造材料里没有的基因名、数值、时间点、单位或结论**。

判断标准：每个实体/数值都能追到逐字证据；重复运行结构一致；交付源文件而非截图。

## 2. 触发与前提

用户要 graphical abstract / 图文摘要 / 机制图 / 流程总结图，并给了论文材料（PDF、md/txt、csv）。材料里没有可引用句子时，交付 `insufficient_evidence` 并说明缺什么，不画空图。

## 3. 运行契约

- 输入 `/input/case.json`（可能缺失）+ `/input/task.md` + `/input/` 材料；工作目录 `/app/work`，产物 `/app/output`。
- 脚本参数 `--input/--work/--output` 可覆盖（评测用默认值）。只用标准库、不联网、不依赖当前目录。
- 任何子命令**退出码恒 0**，失败写进 `result.json`；`init` 一定先写 partial `result.json`，中断也留下合法结果。
- 预算 64 次请求 / 900 秒：先落盘，再优化。

## 4. 输入发现（脚本已完成，了解即可）

`case.json` 用 `utf-8-sig` 读（防 BOM）；键名不固定时按语义取 `output_contract`、`task_instruction`、`organizer_workorder`、`formal_inputs`。
材料按「魔数 + 扩展名」识别：`%PDF` → PDF（`pdftotext -layout`，locator `p.<页> b.<块>`）；可打印文本 → `para.<n>`（CSV 按行）；docx/xlsx/图片不解析，标注 *not parsed*。
PDF 抽不出文本时会明确记录，此时**你必须自己读页面**并引用页码，不能凭标题猜内容。

## 5. 输出契约

`/app/output/`：

| 文件 | 作用 |
|-|-|
| `graphical_abstract.svg` | 分层可编辑源文件（6 个命名图层，文字是 `<text>` 节点，每图元有 `id`） |
| `graphical_abstract.pdf` | 真实矢量 PDF（1 页，12×7.6 in，Helvetica base-14 + 中文 CID 字体） |
| `graphical_abstract.png` | 预览位图（尽力：matplotlib / pdftoppm） |
| `content_map.json` | element_id → panel/role/text/svg_id/bbox + evidence{source,locator,quote,status} |
| `compliance_checks.json` | 画布、字号、图层、字体、色彩、覆盖率等检查结果 |
| `result.json` | 主结果：`output_contract` 全字段 + case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime |

`result.json` 规则：`output_contract` 的**每个键原样保留**（语义匹配到对应产物，无对应则 `null`，不删键、不改名）；`status ∈ {ok, partial, insufficient_evidence, input_error}`。

## 6. 核心流程（Agent 主导）

```bash
cd /app
python3 scripts/main.py init   --input /input --work /app/work --output /app/output
python3 scripts/main.py show   --work /app/work --grep "proton relay"      # 逐字读证据
python3 scripts/main.py check  --work /app/work                            # 校验工作稿
python3 scripts/main.py build  --input /input --work /app/work --output /app/output
```

1. **init**：打印材料清单、段落/页码 locator、workorder 摘要、contract 字段数；写出 `work/index.json` 与 partial `result.json`。
2. **读**：读 `/input/task.md` 与 init 摘要；再用 `show --grep "<关键词>"`、`show --sid m2 --limit 10` 把要引用的句子连同 locator 抄下来。先想清楚：这张图的一句话结论是什么？哪 3–6 个事实/数值必须上图。
3. **写工作稿** `work/plan.json`（见 §7）：由你决定分段内容、措辞、选哪些数值；脚本只负责排版与校验。
4. **check**：只跑校验，打印 PASS/NEEDS WORK 与逐条 FAIL。必须清零后再 build：
   - `evidence unverified` → quote 在原文找不到（改词/跨段/抄错）→ 用 `show` 重新逐字复制；
   - `number(s) [...] not in its quote` → 图元里出现的数字不在引文里 → 换引文或删数字；
   - `missing panel role` → 补齐 problem/method/results/implication。
5. **build**：渲染三件套 + content_map + compliance，最终覆盖 `result.json`；无法验证的图元会被剔除并写入 `exceptions`。
6. 汇报：`status`、图元数、被剔除数、缺口。

## 7. `work/plan.json` 结构

```json
{
  "title": "Cryo-EM structure of the V-ATPase rotor reveals a proton relay switch",
  "subtitle": "How ATP hydrolysis drives proton translocation",
  "caption": "Single page summary; every element traces back through content_map.json.",
  "panels": [
    {"id": "P1", "role": "problem", "heading": "Problem", "flow": "how?",
     "items": [
       {"id": "E1", "kind": "text", "label": "Coupling unresolved",
        "detail": "How ATP hydrolysis couples to proton translocation is unresolved.",
        "evidence": {"source": "paper.pdf", "locator": "p.1 b3",
                     "quote": "how ATP hydrolysis is coupled to proton translocation has remained unresolved"}},
       {"id": "E2", "kind": "value", "value": "2.4-fold",
        "detail": "lower pumping in E145Q vs wild type.",
        "evidence": {"source": "paper.pdf", "locator": "p.4 b2",
                     "quote": "the E145Q mutant reduced proton pumping by 2.4-fold compared with wild type"}}
     ]}
  ],
  "legend": [{"label": "E145Q", "meaning": "relay mutant"}]
}
```

- `role` 只用 4 个：`problem` / `method` / `results` / `implication`（顺序即阅读顺序，2–4 个 panel，最好 4 个）。
- `kind`：`text`（label 粗体 + detail）或 `value`（大字号数字/量，detail 说明条件）。
- `flow`（可选）：写在两个 panel 之间的箭头上，表示关系（`how?`、`quantified by`）。
- 不要写坐标：版面由脚本确定性生成（4 panel 一排，>4 切两排），同输入必得同版式。

## 8. 证据与定位规范

- `quote` 必须是**原文逐字片段**（可跨行但不要跨段），从 `show` 输出复制；不要改写、不要拼接两段。
- `locator` 用 `show` 打印的 locator（`p.3 b2` / `para.5`）。位置错但句子对 → 记 `relocated` 并自动改正。
- 一个图元一个引文；`label`/`detail`/`value` 里的数字必须出现在该引文里（check 会拒收）。
- 推断与限定词（"suggests"）保留原文语气；材料没给的不写。
- 剔除的图元、被改正的 locator 都进 `exceptions`；缺口进 `pending_human`。

## 9. 质量规则（rubric → 产物）

| rubric 关注 | 本 Skill 的落点 |
|-|-|
| 完成度 15 | 四段齐全 + 单页 + 可编辑 SVG + PDF，`compliance_checks` 记页数/尺寸 |
| 正确性 15 | 实体/关系/数值 → 逐字 quote；方向写在 `flow`/`detail` 且来自原文 |
| 完整性 5 | 图例、单位、条件标签、caption；缺口进 `pending_human` |
| 可核验 5 | `content_map[].evidence` + `sources[].sha1` + `changes` + `runtime` |
| 使用增益 25 | 一次 init→plan→check→build 出稿；改图只改 plan.json 重跑 |
| 创新增益 15 | 证据约束排版：quote 校验 + 数字校验 + 确定性布局 |
| 可靠体验 10 | 恒 0 退出码、partial 先落盘、单材料失败只降级该材料 |
| 生态贡献 10 | schema、模板、图层命名、导出参数见 references/ |

## 10. 图面规则（脚本执行，必要时你知道即可）

- 画布 1200×760 → PDF 12×7.6 in（864×547.2 pt），单页。
- 配色 Okabe-Ito 子集：problem `#D55E00`、method `#0072B2`、results `#009E73`、implication `#CC79A7`；**颜色不是唯一编码**——panel 头部写角色名。
- 字号：标题 30 / panel 头 14.5 / label 13.5 / detail 11.8 / 图例 10.5（最小 ≈9）。
- 溢出：先逐级缩字号（1.0→0.76），仍放不下按序丢 item 并记 `degradations`（status 转 partial）。
- 图层：`background, structure, content, legend, footer, titles`（`<g id="layer-*">`）。

## 11. 异常与降级

| 现象 | 处置 | result.json 体现 |
|-|-|-|
| `case.json` 缺失/坏 JSON | 递归找 `case*.json`；仍无则只用材料 + task.md | `errors[]`，contract 字段无法回填时留空并 `status=partial` |
| 材料抽不出文本 | 该材料 `method` 标注 not parsed，其余材料照常 | `degradations[]` + 提示人工读页面 |
| 无 `plan.json` | build 用**确定性兜底**：从原文取 4 句覆盖四段，逐字引用 | `status=partial`、`exceptions[plan_missing]` |
| quote 找不到 | 剔除该图元；panel 空则放 "No verified evidence" 占位 | `exceptions[element_dropped]`、`pending_human` |
| 无 matplotlib/pdftoppm | 保留 SVG+PDF，PNG 缺省 | `degradations[]`，PDF 即导出件 |
| 渲染/导入异常 | 捕获后仍 finalize `result.json` | `errors[]`，退出码 0 |

## 12. 人工确认

写进 `pending_human` 并在回复点明：材料自相矛盾、图元被剔除、合同字段无对应产物、PDF 文本不可抽、数值口径不明（sd vs sem）。不猜。

## 13. 自检清单（交付前）

- [ ] `check` 输出 PASS 或 FAIL 原因已解释；`coverage` ≥ 0.9。
- [ ] `result.json` 含 `output_contract` 全部键；`status` 与实情一致。
- [ ] `graphical_abstract.svg` 打开后文字可编辑、图层可见；PDF 单页且文字可选中。
- [ ] `content_map.json` 每条都有 source/locator/quote/status。
- [ ] 没有材料外的基因名、数值、单位。

## 14. 最小调用示例（示例，非正式案例结果）

```bash
python3 scripts/main.py init  --input ./example/input --work ./example/work --output ./example/out
# 读 show 输出 -> 写 work/plan.json ->
python3 scripts/main.py check --input ./example/input --work ./example/work --output ./example/out
python3 scripts/main.py build --input ./example/input --work ./example/work --output ./example/out
# 出: graphical_abstract.svg/pdf/png, content_map.json, compliance_checks.json, result.json
```

示例（4 panel、6 图元、全 `verified`）与正式案例无关，仅说明接口形状。

文件清单：`SKILL.md`、`scripts/main.py`（init/show/check/build）、`scripts/draw.py`（布局与 SVG/PDF/PNG 渲染）、`references/plan-schema.md`、`references/rubric-map.md`。版本 1.0.0；维护：改 schema 需同步 `check` 与 `content_map`，改版式只动 `draw.py` 的 `build_model`。
