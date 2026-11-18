---
name: academic-language-polish
description: Polish, copy-edit or translate academic prose sentence by sentence while locking numbers, units, citation markers, figure/table pointers, terminology and hedge strength. Use when a manuscript, abstract, thesis chapter, grant text, response-to-reviewers or bilingual abstract is supplied for language polishing, terminology unification, register adjustment or Chinese-English revision. Returns an editable manuscript plus a per-edit change log (original quote, revised quote, type, reason, locator), a preserved-fact inventory and a claim-to-source evidence map. Do not use it for content questions where no rewrite of the supplied text is requested.
version: 1.0.0
license: MIT
---

# 学术语言润色（writing-02）

## 1. 用途与边界

对**已有稿件**做语言层润色：语法、句法、搭配、标点、术语一致、缩写首次出现、学术语气、中译英表达。产出是**可编辑改稿 + 逐条修改说明 + 保留事实清单 + 证据定位**。

不做：代写新章节、补造数据/文献/结论、审稿意见的真实性判断、把材料外知识写入稿件。原文是唯一事实依据；材料未给的内容一律不补。

## 2. 触发条件

**触发**：用户给出稿件/摘要/章节/基金文本/审稿回复，要求「润色、改写语言、校订英文、统一术语、改成期刊语气、中译英」。
**不触发**：只问内容、只要提纲、只要翻译一句术语、只要文献清单、要求评价研究优劣而不改文本。此时说明本 Skill 的适用范围，不改写用户文本。

## 3. 运行契约

- 输入：`/input/case.json` + `/input/**` 材料（md/txt/tex/docx/pdf/csv/json，可能含图片）；工作目录 `/app/work`；产物 `/app/output`。
- 只依赖 Python 标准库；不联网；不依赖当前目录（脚本用 `Path(__file__).resolve().parent`）。
- **退出码恒为 0**；任何异常写入 `errors`/`degradations`/`pending_human`。
- **先落盘**：`main.py` 启动即写 partial `result.json`，结束时无条件覆盖为终版。
- 预算：单次 64 次模型请求 / 900 秒。接近 780 秒时停止新增段落，直接重跑 `main.py` 落盘并说明未完成范围。

## 4. 输入发现（按语义，不假设键名）

1. 读 `case.json`；不存在时递归找 `case*.json`，仍无则用 `task.md` + 材料。
2. 指令语义键：`task_instruction / instruction / task / brief / goal / requirement(s) / deliverable_request / edit_instruction`（可嵌套）。
3. 工单：`organizer_workorder / organizer_edit_workorder / workorder / checklist` —— **逐项执行并在 `workorder_receipts` 回报**。
4. 术语：`glossary / termbase / terminology / terms`，支持 dict / list / `"a → b"` 三种写法；冲突进 `pending_human`。
5. 材料：递归扫描 `/input/**` + `formal_inputs / runtime_files / materials / artifacts / attachments` 中列出的路径；PDF 走 `pdftotext` → `pypdf` → 内置 FlateDecode；DOCX 走 zip XML；图片只登记不 OCR（记降级）。
6. 材料缺失（未给原稿、只给图片、PDF 无文本层）→ 明确写缺口，不推测内容。

## 5. 输出契约

`/app/output/` 下：

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 润色后全文，可直接编辑/粘贴 |
| `deliverable.md` | 交付包：全文 + 修改清单表 + 术语表 + 待确认项 |
| `change_log.csv` | 每条修改：段落/类型/原文/改文/理由/定位/校验 |
| `result.json` | 结构化结果，**原样回填 `output_contract` 全部键**（键名不改、缺值 null/[]），保留未知字段 |

`result.json` 必含：`case_id`、`status`（ok / partial / insufficient_evidence / input_error）、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`glossary`、`bilingual`、`workorder_receipts`、`checks`、`coverage`、`counts`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。

## 6. 工作流（三阶段，命令可直接执行）

```bash
# 阶段 1：取件 + 逐段工作单（不润色）
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
# 读 work/workpack.json：每段的 id、text、section、locks（numbers / citations / xrefs / hedges / boosters / abbreviations）
```

阶段 2（**你来做**）：逐段润色，把结果写进 `work/polish_payload.json`（骨架已生成）：

```json
{"paragraphs": [{"id": "P002", "revised": "改后整段",
  "edits": [{"type": "collocation", "original_quote": "原文片段", "revised_quote": "改后片段",
             "reason": "为什么改，如何保持语义", "locator": "P002"}]}],
 "glossary": [{"source": "reactive oxygen species", "target": "ROS"}],
 "workorder_receipts": [{"id": "WO01", "status": "done", "evidence": "…", "locator": "P002"}],
 "pending_human": [], "uncertainty": []}
```

阶段 3：落盘 + 自检，读表修正后重跑（最多 2 轮）：

```bash
python3 -B scripts/main.py --input /input --output /app/output --work /app/work
python3 -B scripts/verify.py --output /app/output   # 打印检查表
```

`edits` 的 `original_quote` 必须能在原段落里**逐字**找到，`revised_quote` 必须能在改后段落里找到；不满足的条目会被拒收并进入 `pending_human`。

## 7. 润色规程（每段照做）

1. **读锁**：该段的 numbers / units / citations / xrefs / hedges / boosters / abbreviations 是硬约束。
2. **找硬错**：主谓一致、时态、冠词/介词、单复数、悬垂修饰、标点、断句、搭配、重复。
3. **最小编辑**：先改词、再改短语、最后才重排句子；一个改动能用 3 个词解决就不用 10 个。保留作者信息顺序与句间逻辑连接。
4. **守住主张**：hedge（may / suggest / could / 可能 / 提示）与 booster（demonstrate / prove / 证明 / 首次 / 显著）的强度不得增删；因果（cause）与相关（associate with）不得互换；否定范围、条件句、量词不得改动。
5. **守住事实**：数字、单位、样本量、p 值、引用编号、图表指向原样保留；必须改数值时停手，写入 `pending_human`。
6. **术语落地**：使用术语表写法；全篇回扫同义变体（tumor/tumour、normalize/normalise、缩写大小写）。
7. **写说明**：每条改动给出类型、原文、改文、理由（≥6 字，说明改什么、为何不改变语义）、定位。
8. **回读**：改完通读该段，检查（a）意思是否仍等于原文（b）锁是否齐全（c）是否像同行写的（d）有无新增信息。任一项失败就回退该处。

无错可改时把 `revised` 填回原文并给 `unchanged_reason`，不要为改而改。

## 8. 语气与文体

按 `workpack.json` 的 `genre` 选基线：期刊论文=中性客观、方法过去时、结论现在时；摘要=单段无引用除非原文有；学位论文=可展开、允许第一人称复数；基金=问题—缺口—方案—影响，避免绝对化；审稿回复=逐条对应、礼貌但明确。删口语化（a lot of、非常）、宣传化（novel、revolutionary、首次）、绝对化（proves、always、完全）。详见 `references/polish_protocol.md`。

## 9. 冲突、缺口、人工确认

以下一律进 `pending_human` 并说明为什么无法自动决定：材料冲突（同一数字两处不同）、术语表内部冲突、数值/单位疑似笔误、引用编号与文献表不匹配、图片/扫描件内容不可读、目标期刊格式不明、需新增文献支撑的论断。

## 10. 异常降级表

| 情况 | 处置 |
|---|---|
| 无 `case.json` | 用 `task.md` + 材料，`status=partial`，`input.case_path=null` |
| `case.json` 解析失败 | 记 `errors: case_json_parse`，继续用 `task.md` |
| 无可读文本 | `status=insufficient_evidence`，`pending_human` 写「源文本」缺口 |
| PDF 无文本层 | 记 `pdf_text` 降级；若确无内容则请求可读版本 |
| 编码混乱 | 依次尝试 utf-8/gb18030/big5/cp1252/latin-1，仍乱码则记 `encoding` |
| payload 缺失或损坏 | 交付原文基线 + `pending_human`，`status=partial` |
| 某段无 payload | 该段保留原文，段号写入 `pending_human`，其他段照常交付 |
| 超长输入（>200k 字符） | 记 `long_input`，清单截断，正文全量保留 |
| 公式/LaTeX 混杂 | 公式原样保留，只改公式外文字 |
| `python3` 不可用或脚本报错 | 按 `references/payload_and_result_schema.md` 手工产出 `manuscript.md`、`change_log.csv`、`result.json`，`status=partial`，`degradations` 记 `script_unavailable`（**不得**因此省略修改说明或保留事实清单） |

## 11. 自检清单（交付前）

- [ ] `result.json` 合法 JSON，`case_id` 与 `output_contract` 键齐全，未知字段仍在。
- [ ] `checks` 无 `fail`：契约、fact_locks、hedge_strength、terminology、edit_traceability、coverage。
- [ ] 每条 `edits` 的原文/改文引用都能在对应段落中找到。
- [ ] `preserved_facts` 中 `present_in_revision=false` 的条目已解释或修正。
- [ ] workorder 每项有回执；`pending_human` 写清缺口与需人工做的动作。
- [ ] 人工复核（脚本不自动判定）：缩写首次出现处有定义且全篇只定义一次；`glossary` 每条目目标写法在改文中真实出现；目标语言无残留（中译英时无中文句、英译中时无整句英文）。
- [ ] `manuscript.md` 可直接编辑，无脚本标记、无 TODO。

## 12. 最小调用示例（示例，非正式案例结果）

输入：`case.json` 含 `case_id:"DEMO"`、`output_contract:{polished_text, change_log}`、`materials:["abstract.md"]`；`abstract.md` 为两段英文摘要（含 `48 mice`、`25 mg/kg`、`[12]`、`may promote`）。

```bash
python3 -B scripts/main.py --input demo --output demo/out --work demo/work   # 生成工作单
# 填写 work/polish_payload.json 后
python3 -B scripts/main.py --input demo --output demo/out --work demo/work   # 交付
```

示意输出（节选）：`manuscript.md` 中 `may promote` 保留、`48 mice / 25 mg/kg / [12]` 原样；`change_log.csv` 一行 `P002,collocation,"These results suggest that","These findings suggest that","避免与上句重复，hedge 强度不变","P002",True`；`result.json` 的 `checks` 全 pass、`status:"ok"`。此为示意，不代表任何正式案例结果。

### 12.1 编辑粒度示例（示例，非案例结果，仅示范写法与理由口径）

| 原文（示意） | 改文（示意） | type | reason 写法 |
|---|---|---|---|
| `measured by DCFH-DA assay` | `measured with the DCFH-DA assay` | `preposition` | 测定方法与试剂用 with，并补定冠词；数值与结论不受影响 |
| `All data are mean ± SD of three independent experiments.` | `Data are means ± SD of three independent experiments.` | `grammar` | `means ± SD` 为统计惯例复数形式，删去冗余 All；实验次数不变 |
| `These results suggest that … may be mediated …` | `These findings suggest that … may be mediated …` | `collocation` | 上句已用 results，换 findings 避免重复；suggest 与 may be 保留，结论强度不变 |
| `通过我们的研究发现，该抑制剂对肿瘤生长起到了明显的抑制作用。` | `Under the tested conditions, the inhibitor markedly suppressed tumour growth.` | `translation` | 补出原文「一定实验条件下」的限定；「明显」译为 markedly 而非 abolished，强度不升级 |

反例（不要这样改）：`may promote` → `promotes`（升级强度）、`48 mice` → `approximately 50 mice`（改数值）、`associated with` → `caused by`（相关改因果）、整段重写但不给 `edits`（不可核验）。

## 13. 文件清单与版本

```
SKILL.md                              本文件（协议、契约、边界）
scripts/main.py       ~20KB           阶段 1 取件/工作单 + 编排 + 落盘
scripts/verify.py     ~20KB           阶段 2 抽取/装配/契约回填/确定性检查/交付
references/polish_protocol.md         润色方法、错误分类、语域与双语规则
references/payload_and_result_schema.md  输入负载与输出字段规范、示例
references/evaluation_and_maintenance.md 评分项映射、A/B 评测与维护
```

版本 1.0.0；标准库 Python ≥3.8；无外部依赖，无网络。

## 14. 维护

- 改协议只改 `references/polish_protocol.md`，脚本行为由 `main.py`/`verify.py` 的常量决定（hedge/booster 词表在 `main.py` 顶部）。
- 新增检查项：在 `verify.py::verify_all` 中 `add(id, status, detail, counts)`，同时在本文第 11 节与 `evaluation_and_maintenance.md` 的映射表登记。
- 回归测试：用 `evaluation_and_maintenance.md` 的 3 组小样稿跑 intake→payload→full，确认 `checks` 不出现新的 `fail`。
