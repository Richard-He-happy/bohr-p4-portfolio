---
name: bio-mechanism-figure
description: 把机制文本/通路描述/工单材料变成可回溯、可编辑的生物学机制图（分层 SVG + 真实单页矢量 PDF + content_map + 合规检查 + 金标准/diff/自检 + result.json）。Agent 亲自读材料并写 plan.json（实体/关系/证据/区室），脚本只做索引、逐字校验、渲染与可核验资产生成。Use when the task asks for a biological mechanism diagram, pathway figure, signalling schematic, graphical abstract of a mechanism, or a source-preserving edit of one.
version: 2.0.0
---

# 生物机制图与通路图（Agent 主导，v2）

## 1. 用途与边界

把「材料里写明的机制」画成一张**可以被逐条质疑**的机制图：实体（基因/蛋白/复合物/细胞/区室）、关系
（激活/抑制/结合/修饰/转运）、方向与区室位置、图例与数据编码，全部要能回溯到逐字原文。做：实体与关系抽取、
箭头语义、区室分层、图例一致性、可编辑 SVG + 矢量 PDF、逐元素来源映射、金标准与对照。不做：统计检验/显著性
结论、实验设计、版式美化、材料里没有的数值或分子名。

**责任划分（重要）**：脚本不判断生物学。它提供材料索引、逐字引文校验、确定性渲染、金标准差集与自检；
**实体、关系、方向、区室必须由你读完材料后写进 `plan.json`**。`plan.json` 缺失/不可用时脚本用确定性兜底
（工单条目 → 语义句挖掘 → 材料清单）产出最小但完整的图，并标 `status=partial`。

## 2. 运行契约

- 输入：`/input/case.json` 与材料（`/input/**`：PDF、DOCX、XLSX、PNG、MD、CSV、JSON…）。
- 主产物：`figure.svg`（可编辑源）、`figure.pdf`（真实单页矢量）、`content_map.json`、`compliance_checks.json`、
  `plan.normalized.json`、`result.json`；工作区 `/app/work`（`materials.json`、`plan.json`、`check_report.json`、`run.log`）。
- 可核验资产（v2 新增，同一次 build 产出）：`golden_standard.json`、`diff_report.md`、`version_history.md`、
  `self_check.json`、`run.log`（compact JSON 用于机器复核，人读版是 `diff_report.md`）。
- `result.json` 原样回填 `case.json` 里 `output_contract` 的**全部字段**（不改名、不遗漏；缺值 null/[]），另带
  `case_id`/`status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`，以及
  v2 的 `golden_standard`/`diff_report`/`version_history`/`self_check`（文件指针 + 摘要 + 判定）。
- 调用：`python3 -B <SKILL>/scripts/main.py <子命令> --input /input --output /app/output --work /app/work`
  （不依赖 CWD，纯标准库，不联网，`--help` 退出码 0）。
- **第一步先写合法 partial `result.json`**（`init` 与 `build` 开头各写一次）；异常全部捕获进
  `errors`/`degradations`，**退出码恒为 0**。

## 3. 五步流程（build 前必须写好 plan.json）

**① 索引** `init`：材料清单（kind/字节/块数/locator）。文本切块 `文件#paraN`，PDF 切块 `文件#streamN`；
读不出的材料（扫描 PDF、位图）带 `NOTE`，只能作为缺口，不许猜。

**② 读原文** `show --doc <材料名子串> [--locator para3]`：带 locator 打印逐字原文，**真的去读**，不凭文件名推断。

**③ 写 `/app/work/plan.json`**（schema 见 `references/plan-schema.md`）：每实体/关系带 `evidence.quote`
（原文逐字，≥6 字符）+ `locator`；区室按上游→下游排序；方向=原文语序；材料没写的进 `gaps`，类型用 `unspecified`。

**④ 校验** `check`：quote 回正文逐字（空白归一）匹配，报 `rejected`（找不到）、`issues`（缺 id/type/compartment）、
workorder 缺口。`CLEAN` 再进下一步。

**⑤ 渲染 + 资产** `build`：写出第 2 节全部文件。被拒引文或金标准偏差会把 `status` 降为 `partial` 并进
`uncertainty`/`pending_human`，但**不影响出图**。`build` 可重复运行；`--no-probe` 跳过子进程兜底探针
（默认开启，约 1–2 秒）。时间紧就先 `init` → 3–8 实体 + 关键边 → `build`，再补全重跑。

## 4. 关系语义（图元即论断，改一处即改一论断）

| type | 画法 | 含义 | 典型原文词 |
|---|---|---|---|
| `activation` | 实线 + 实心箭头 | 促进/激活/上调 | activates, promotes, induces, 促进, 激活 |
| `inhibition` | 实线 + T 形端 | 抑制/阻断/负反馈 | inhibits, represses, suppresses, 抑制, 阻断 |
| `binding` | 实线 + 空心箭头 | 结合/募集/互作 | binds, recruits, associates, 结合, 募集 |
| `modification` | 虚线 + 实心箭头 + `P`/`Ub` | 磷酸化/泛素化/剪切 | phosphorylates, ubiquitinates, 磷酸化 |
| `transport` | 粗实线 + 双箭头 | 转运/转位/分泌 | translocates, transports, secretes, 转运 |
| `indirect`/`unspecified` | 点线/灰点线 | 间接推断/原文未说明 | implied, unknown |

图例由脚本按**实际出现的**类型与节点种类生成，图例与图面必然自洽；不要手写与图不一致的图例。颜色只编码
「实体种类」，除非 `plan.data_encoding` 给出带出处的数值。

## 5. 可核验资产（v2）与证据规范

| 资产 | 回答的问题 | 关键字段 |
|---|---|---|
| `golden_standard.json` | 这张图**应该**有什么？ | `entities[]`/`relations[]`（`type`、`direction`）、`rules.legend/layout/export`，每条带 `evidence{source,locator,quote,quote_verified}`；另有 `verification`、`gaps` |
| `diff_report.md` | 实际产物**差在哪**？ | 汇总计数、实体/关系逐项表（方向反转点名）、图例与区室顺序、未达标项与动作 |
| `version_history.md` | v0→v1→v2 改了什么、怎么回退 | 每版变更/原因/回退命令 + 本次运行时记录 |
| `self_check.json` | 契约/证据/数字/兜底/退出码 | `contract_fields`、`assets`、`svg`、`map_1to1`、`pdf`、`evidence`、`numeric_trace`、`consistency`、`fallback`（4 探针）、`verdict` |
| `run.log` | 这次真实跑了什么 | 逐行 `时间 级别 事件`（降级、异常、耗时、DONE 汇总） |

- 金标准**只**来自工单条目（`declared`）与材料原文中显式的主谓宾机制句（`verbatim`）；规则项取自
  `references/*.md` 原文并逐字回查。原文没有的不补，方向不凭常识，判不准记 `unspecified`。所以 diff 的
  「缺失/偏差」是**可复核的缺口**，不是脚本判定生物学错了。
- `quote` 必须是正文**逐字切片**（允许换行/多空格差异），≥6 字符；改写、拼接、翻译都算未命中。工单声明条目
  的 locator 用 `case.json#<json-path>[i]`，计入 `*_declared`，与 `*_verified` 分开报。
- 实体只写「最小可判定标签」：基因/蛋白大小写、物种前缀、复合物成员按原文写法，不擅自归一化。图上任何数值
  都必须有 `plan.data_encoding` 条目 + quote；`self_check.numeric_trace` 会把图面文字的数字逐个回查材料。

## 6. 质量规则（rubric → 检查点）

| 评分关注 | 可核验落点 |
|---|---|
| 任务完成度 | 主产物 + 5 资产齐备；`compliance_checks.verdict.all_pass`；`self_check.assets.pass` |
| 结果正确性 | 每条关系有 type 与方向；`check` 报 0 rejected；diff 的 kind/type/方向偏差为 0 |
| 完整性 | workorder 覆盖计数写入 `counts`；金标准项逐条对照，缺口进 `pending_human` |
| 可核验性 | `content_map` 与 `golden_standard` 每条含 `locator`+`quote`+`quote_verified`；`map_1to1` 证明图元↔映射一一对应 |
| 稳定性 | 空输入/坏 JSON/坏 plan 均退出 0 并产出合法 result.json；`self_check.fallback` 给 4 探针真实退出码 |
| 可编辑性 | SVG 分层 `<g id="layer-*">` + `<text>`；PDF 单页、`%%EOF` 完整、含 `Tj`（文字可选中） |

## 7. 降级与人工确认

| 情况 | 行为 | 落点 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 抢救 `case_id`/`output_contract`，继续跑 | `errors`，`status=partial/input_error` |
| 无 `plan.json` | 兜底：工单条目 → 语义句挖掘 → 材料清单 | `degradations`、`subtitle` |
| 引文找不到 | 仍画但标未核验，整体 partial | `uncertainty`、`counts.rejected_quotes` |
| 金标准为空 | 不补造实体，说明缺口 | `golden_standard.gaps`、`pending_human` |
| diff 有缺失/偏差 | 图仍出，降 partial，动作逐条列出 | `diff_report` §5、`result.diff_report.actions` |
| 材料是位图/扫描 PDF | 不进正文，只列缺口 | 材料 `note`、`gaps` |
| 实体歧义（基因/蛋白） | 保留原文写法，用 `kind` 区分，不合并 | `gaps`、`kind_basis=not_stated` |
| PDF 非拉丁字符 | SVG 保留原文，PDF 丢字并计数 | `compliance_checks.pdf.chars_dropped_for_winansi` |
| 无位图渲染器 | 不出 PNG，用 PDF 作检视件 | `raster_preview`、`degradations` |
| 探针子进程失败 | 记 `pass=false`，不中断主流程 | `self_check.fallback`、`verdict.failures` |

无法判断的一律写进 `pending_human` 并说明「需要人确认什么」，不要写成事实。

## 8. 预算、自检与调用示例

预算 64 次模型请求 / 900 秒 / 单次 16384 tokens；超约 780 秒立即 `build` 收尾。每步可重入。

交付前自检：① `contract_fields.null_fields` 为空或原因已写 `degradations`；② `check` 为 `CLEAN` 或 rejected
全进 `uncertainty`；③ `figure.svg` 有 `<text>` 与 ≥4 个 `layer-*`，`figure.pdf` 以 `%PDF-` 开头、`%%EOF` 结尾；
④ `content_map` 条目数 = 图面实体 + 关系，`self_check.map_1to1.pass == true`；⑤ diff 判定与
`result.diff_report.verdict` 一致且非达标项都有人工动作；⑥ `self_check.verdict.all_pass == true`，否则逐条看
`failures`（是可复现缺口，不是崩溃）；⑦ 只验健壮性：`main.py selftest --output /app/output --work /app/work`。

```bash
python3 -B scripts/main.py init  --input /input --output /app/output --work /app/work
python3 -B scripts/main.py show  --doc note --locator para3     # 读原文
python3 -B scripts/main.py check --input /input --output /app/output --work /app/work
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
```

示例 `plan.json`（**示例，非正式案例结果**，虚构标签仅示字段）：

```json
{"title": "示意：A 激活 B，B 抑制 C",
 "compartments": [{"id": "cyto", "label": "Cytoplasm", "order": 0}],
 "entities": [{"id": "A", "label": "A", "kind": "protein", "compartment": "cyto",
               "evidence": {"quote": "<材料原文片段>", "locator": "note.md#para3"}}],
 "relations": [{"source": "A", "target": "B", "type": "activation",
                "evidence": {"quote": "<材料原文片段>", "locator": "note.md#para3"}}],
 "gaps": ["C 的区室原文未说明"]}
```

## 9. 文件清单与维护

包内 10 个文件：`SKILL.md`（12 KB）、`scripts/main.py`（67 KB，五子命令与全部生成逻辑）、`scripts/render.py`
（显示列表 → SVG + PDF）、`references/plan-schema.md`、`references/render-rules.md`（金标准规则项的引用
来源），以及示例运行的 5 个资产（`golden_standard.json`/`diff_report.md`/`version_history.md`/`self_check.json`/
`run.log`，`demo:true`，仅示格式与判定口径，**非正式案例结果**）。

依赖 Python ≥3.8 标准库（json/re/zipfile/zlib/math/argparse/pathlib/subprocess/xml.etree），无第三方包、无网络、
无字体文件。维护：语义词表改 `render.py:_AL`；画法改 `REL`/`HEAD`；布局改 `build_display`；金标准规则改
`main.py:RULES`（quote 必须在 `references/render-rules.md` 逐字命中，否则 `quote_verified=false` 被自检抓到）。
新增题型只在 `plan.json` 层扩展，不回改脚本分支。**版本**：v2 纯增补 5 个资产与 4 个 result 字段，入口与调用
方式不变；回退见 `version_history.md`。
