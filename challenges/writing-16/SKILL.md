---
name: research-translation-writing
description: 把科研材料（论文、技术报告、数据表、图表说明）改写成面向指定受众与体裁的可直接使用稿件（产业转化简报、项目申报摘要、科普稿、论文摘要等），逐段保留来源定位、数字与论断强度，并交付必保留项清单、逐段来源对照、change log 与 result.json。当任务要求"把这项成果写给某类读者""改写成申报/科普/简报""同一成果多文体转换"时使用。
version: 1.0.0
---

# 科研成果转化写作（受众/体裁改写）

## 1. 用途与边界

做一件事：**读源材料 → 按目标受众与体裁重写 → 每处保留可回溯的来源、数字、限定条件与论断强度**。

- 适用：论文→产业简报/申报摘要/科普稿；技术报告→项目材料；多文体并行改写；篇幅压缩但不丢证据。
- 不适用：从零创作无源材料的文章；编造数据或前景；替代同行评审；需要实验数据的统计推断。
- 硬边界：不新增源材料没有的数字、文献、机构、商业结论；源材料没有的应用前景只能标 `pending_human`。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（含 `output_contract`）、`/input/task.md`、`/input/` 下材料（PDF/DOCX/XLSX/CSV/MD/JSON/图片） |
| 工作目录 | `/app/work`（`index.json`、`draft.json`、`check.json`） |
| 产物 | `/app/output/deliverable.md` + `/app/output/result.json` |
| 依赖 | 仅 Python3 标准库；离线；不依赖当前工作目录（脚本用 `Path(__file__).resolve()`） |
| 退出码 | 恒为 0；异常写入 `result.json.errors` 并保留已有产物 |
| 预算 | 64 次模型请求 / 900 秒 / 单次回复 16384 tokens；接近 780 秒立即 `build` 收口 |

## 3. 谁写什么（关键）

- **脚本**：索引材料、打印带定位的原文、校验工作稿、排版成稿、回填契约。
- **Agent（你）**：判断受众与取舍，**逐段写出真正的转化稿正文**（不是提纲、不是润色建议），填写必保留项、逐段对照、change log。
- 判定失败的最常见原因就是"只给了写作建议/提纲"。`check` 会在正文不足目标篇幅 45% 时直接报 `too_short`。

## 4. 流程（按序执行）

1. `python3 scripts/main.py init`
   - 递归扫描 `/input`，按扩展名+魔数识别材料，切段编号 `M1:P3`，抽取数字/单位/缩写；
   - 立即写出合法的 partial `result.json`，并生成 `/app/work/draft.json` 模板；
   - 打印材料清单、工作单摘要（受众/体裁/篇幅/契约字段）、段落清单、关键数字、缩写。
2. `python3 scripts/main.py show --ids M1:P1-M1:P8`（或 `--grep 关键词`）读原文。
   - 至少读：摘要/引言、含数字的段落、局限与结论段、图表标题。**按实际文本判断，不按文件名或领域标签猜内容。**
3. 写 `/app/work/draft.json`（结构见 `references/draft-schema.md`）：
   - `audience`/`genre`：按题面受众与体裁填写画像与策略（可用 `references/genre-playbook.md` 的对照表）；
   - `sections`：**成稿正文**，按目标体裁组织；每段 `cites` 标 `M1:P3`；
   - `preserved`：必保留项（数字+单位、样本/条件、图表引用、关键结论、限定语），带逐字 `quote` 与 `locator`；
   - `map`：逐段来源对照；`changes`：每处删改的原文→改后+理由；`removed`：删了什么、为什么不是证据；
   - `glossary`：缩写首次展开与全文统一说法；`pending`/`uncertainty`：待确认与不确定。
4. `python3 scripts/main.py check` → 按报告修 `draft.json`，直到无 `[错误]`（引文未命中、数字不在源文、缺字段、篇幅不足）。
5. `python3 scripts/main.py build` → 生成 `deliverable.md`，无条件 finalize `result.json`。
6. 回报：状态、字数、引文命中率、数字校验结果、待确认项。

## 5. 输出契约（result.json）

- 原样回填 `case.json` 的 `output_contract` **全部字段**（不改名、不缺项；无对应内容填 `null`/`[]`），并写 `contract_fill` 统计。
- 固定字段：`case_id`、`status`(ok|partial|insufficient_evidence|input_error)、`deliverable`、`preserved_facts`、`evidence_map`、`change_log`、`changes`、`glossary`、`removed`、`transformation_spec`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`self_check`、`runtime`。
- `status` 规则：结构/引文/数字全过 → `ok`；有缺口但已交付 → `partial`（缺口写进 `errors`/`pending_human`）；无可用材料 → `insufficient_evidence`；输入本身不可解析 → `input_error`。
- `sources` 记录每份材料的 `method`（`pdftotext`/`builtin-pdf`/`docx-xml`/`xlsx-xml`/`text`/`image-no-ocr`），解析降级同时写入 `degradations`。

## 6. 证据与定位规范

- 定位格式：`M<材料号>:P<段号>`，段落号取自 `init` 输出；也接受 `M1:P3-M1:P6`。
- `quote` 必须**逐字**取自源材料（允许空白/全半角差异，不允许改词、补字、翻译）。
- 核验不过的处理顺序：改 quote → 改 locator → 把该项移入 `pending_human`。**禁止为了通过校验而修改原文。**
- 成稿中出现的每个数字都必须能在源材料找到（含单位写法）；换算须在 `note` 说明，并把该书放进 `pending`。

## 7. 受众 / 体裁 / 论断强度

- 三要素判定：读者知识背景 → 解释深度与术语密度 → 例子与篇幅分配（详见 `references/genre-playbook.md`）。
- 论断强度只用三级并写进 `sections[].strength`：
  - `established`：源文明确结论（含"显著""证明"等）；
  - `preliminary`：初步/单一实验/体外结果，须保留 "初步""有待验证"；
  - `hypothesis`：机制推测、外推应用、商业前景 → 转写时必须降级表述并进 `pending_human`。
- 相关不写成因果；样本量与条件（物种、剂量、时长、平台）随结论一起搬。

## 8. 取舍规则（删什么不是删证据）

| 优先级 | 内容 | 处理 |
|---|---|---|
| P0 必保留 | 主结论、关键数字+单位、条件与样本、图表编号、局限与不确定性 | 逐字或等价保留，进 `preserved` |
| P1 可压缩 | 方法细节、参数罗列、文献堆叠 | 一句话概括，不改数值 |
| P2 可删 | 重复表述、与目标读者无关的推导、致谢与投稿信息 | 进 `removed` 并写理由 |

压缩后如果某结论失去限定条件，就把限定条件补回；**宁可多一句限定，不可少一个条件**。

## 9. 冲突、缺口与人工确认

- 受众与体裁冲突（如"面向公众"却要求"完整方法"）→ 以受众为纲，方法压缩为一句，冲突写 `pending_human`。
- 篇幅与内容冲突 → 保 P0，删 P2；在 `deliverable.md` 首节说明篇幅取舍。
- 数据自相矛盾（同一指标两个值）→ 两值都列，标 `uncertainty`，不擅自选一个。
- 材料涉密/未发表/含个人信息 → 不做外推，`pending_human` 写"需授权确认后发布"。
- 缺引用/缺图表编号 → 不用占位数字补，写"（原文未给编号，需补）"并进 `pending`。

## 10. 异常降级分支

| 情形 | 行为 |
|---|---|
| `case.json` 缺失/坏 JSON | 递归找含 `output_contract` 的 json；仍无则用内置字段，`degradations` 记录 |
| PDF 无 `pdftotext` | 内置流解析；质量低时标 `builtin-pdf-lowconf`，并提示人工核对 |
| 材料是图片 | 不 OCR，记 `image-no-ocr` 缺口，不臆造图注 |
| 材料解析失败 | 只降级该文件，其余继续；`degradations` 记文件名与原因 |
| `draft.json` 缺失/不合格 | `build` 用源文句子做确定性抽取兜底，`status=partial` 并在稿首标注"兜底稿，未完成受众改写" |
| 运行超时/异常 | 仍有 partial `result.json`；`build` 可重跑覆盖 |

## 11. 自检清单（交付前）

- [ ] `deliverable.md` 含：适配说明、转化稿正文、逐段对照、必保留项清单、删改/change log、术语表、待确认、自检。
- [ ] `check` 无 `[错误]`；引文命中率 100%；数字不匹配 0。
- [ ] 每个关键论断能在 `evidence_map` 找到 `locator`。
- [ ] 每位读者视角通读：无未展开缩写、无裸公式、无自造术语。
- [ ] `result.json` 契约字段齐全，`status` 与实况一致。

## 12. 最小调用示例（示例，非正式案例结果）

```
$ python3 scripts/main.py init
== 材料索引 ==
M1   demo_paper.md   text   text        820字/  6段 [material]
...
受众: 产业界  <- `产业界`
体裁: 技术转化简报   篇幅: 1200 字
契约: case_id, deliverable, preserved_facts, evidence_map, change_log（5 字段）

# Agent 写 /app/work/draft.json（sections 为完整正文）
$ python3 scripts/main.py check
状态 ok | 段落 5 | 正文 1106 字 | 引文 9/9 | 数字 12（不匹配 0）
$ python3 scripts/main.py build
status=ok fallback=False 字数=1106 目标=1200 文件=['deliverable.md', 'result.json']
```

（上例材料与数字为构造示例，仅说明接口；正式案例以平台 `/input` 为准。）

## 13. 文件清单与版本

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本说明（流程、契约、规则、降级） |
| `scripts/main.py` | `init`/`show`/`check`/`build` 主流程 |
| `scripts/verify.py` | 确定性校验（引文/数字/覆盖/契约），可单独 `--help` |
| `references/draft-schema.md` | 工作稿字段结构与校验口径 |
| `references/genre-playbook.md` | 受众×体裁矩阵、取舍与强度词表、反模式 |

版本 1.0.0；仅标准库；无网络；无外部服务。示例输出均标注"示例"。

## 14. 维护说明

- 换新领域材料无需改脚本：`init` 按扩展名+魔数识别，段落编号自动生成。
- 想加新体裁：在 `genre-playbook.md` 增一行矩阵 + 一段结构模板，脚本不动。
- 校验口径调整只改 `verify.py`（`check_draft`），`main.py` 复用其结果。
- 脚本改完必须跑：`--help` 退出码 0、空输入与坏 JSON 各一次，确认仍写 partial `result.json`。
