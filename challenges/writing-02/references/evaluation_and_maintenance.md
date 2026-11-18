# 评分项映射、A/B 评测与维护（evaluation_and_maintenance）

## 1. 评分项 → 字段/检查/产物

| 评分维度（分值） | 具体考察 | 本包对应实现 | 核验方式 |
|---|---|---|---|
| 任务完成度（15） | 交付「润色后全文 + 逐句修改说明」，而非建议 | `manuscript.md` + `change_log[]`/`change_log.csv`；`edits` 逐条 `original_quote→revised_quote` | 打开 `manuscript.md` 与 `change_log.csv`，抽查 5 条引文是否可定位 |
| 结果正确性（15） | 主张与限定强度不变；数字/单位/引用/图表指向对齐；术语合惯例 | `locks`（数字、引用、xref、hedge、booster、缩写）+ `checks.fact_locks`/`hedge_strength`/`terminology` + `preserved_facts`/`evidence_map` | `result.json.checks` 无 `fail`；`preserved_facts[].present_in_revision` 全 true |
| 结果完整性（5） | 指定章节逐段处理、术语表建全、缩写首次出现统一、双语对照与修改清单齐全 | `coverage`（段落覆盖）、`glossary`、`checks.terminology`、`bilingual`、`workorder_receipts` | `coverage.ratio`、`workorder_receipts[].status` |
| 结果可核验性（5） | 原文—改文对照、类型标签、理由足以判断该不该改 | `edits[].type`（受控词表）+ `reason` + `locator`；`checks.edit_traceability` | 任取一条，按 `locator` 回到原文段落找到 `original_quote` |
| 质量增益（15） | 同输入同条件下语法/术语/语义/语气稳定更好 | `references/polish_protocol.md` 的 7 步流程与受控错误分类，减少「换说法掩盖错误」 | §2 盲评协议，跨条件同一 rubric |
| 效率增益（5） | 减少人工返修与往返轮次 | 一次运行即产出稿+清单+CSV；`checks` 把返修点前置；`pending_human` 只留真正需要人判断的条目 | 统计人工返修条目数与轮次 |
| 增益可验证性（5） | 对照条件一致（同原文、同术语表、同评分人、同验收标准，最好盲评） | 固定 `case_id`、固定 `workpack.json`、`revision_hash` 记录同一段落重复运行是否漂移 | §2 记录表 + `revision_hash` 比对 |
| 新增能力（5） | 术语表驱动全篇回扫、限定强度守恒、双语对齐、按期刊风格整体改写 | `locks.hedges/boosters` 逐段守恒检查；`glossary` 注入与回扫；`bilingual` 对齐；`genre` 语域基线 | `checks` 输出 + 术语/强度档案 |
| 方法改进（5） | 最小编辑、分句级策略、注入方式、回读校验、改写/审校双通道 | 最小编辑 7 步、`edits` 粒度控制、`verify` 双通道（检查通道不改文）、`pending_human` 兜底 | §3 测试小样与 `checks` 结果 |
| 创新证据（5） | 相对基础 Agent / 通用写作工具 / 翻译工具 / 人工基线的边界与价值 | §2 四点对照 + §4 边界声明 | 对照记录 + 失败案例 |
| 调用与易用性（3） | 准确触发；纯文本/Markdown/LaTeX/章节稿输出可直接用 | `SKILL.md` §2 触发与不触发；`manuscript.md` 为纯文本稿 | 用三种输入格式各跑一次 |
| 运行稳定性（4） | 长文本、分章、重复运行、跨学科术语稳定 | 逐段处理 + `revision_hash`；`long_input` 降级；无随机性（纯规则） | 同一 case 跑 3 次比对 `revision_hash` |
| 异常处理（3） | 超长、编码、公式引用混杂、中英日混排、术语冲突、文体不明 | `SKILL.md` §10 降级表 + `degradations`/`errors`/`pending_human`；退出码恒 0 | 空输入、坏 JSON、坏 payload、扫描版 PDF 各跑一次 |
| 文档完整性（3） | 用途/边界/接口/示例/限制/维护齐全 | `SKILL.md` 14 节 + 本文件 + schema 文件 | 按 `SKILL.md` 第 12 节示例能否独立复现 |
| 资源可复用性（4） | 术语表/风格规则/测试文本/评分表可被他人在自己学科使用 | `glossary` 结构通用；§3 提供 3 组可替换测试小样；§1 映射表可直接改学科 | 替换 `case.json` 与材料即可复用 |
| 分享推广价值（3） | 沉淀案例、评测集、术语治理经验 | 本文件 §2–§4 | 他人按文档可复现一次对照评测 |

## 2. 盲评对照协议（可直接执行）

准备：
1. 同一 `case.json` + 同一材料目录，复制两份：`run_base`（不加载 Skill）与 `run_skill`（加载本 Skill）。
2. 同一术语表、同一风格要求、同一评分表；评分人不知道哪份来自哪个条件（文件名改为 A/B）。
3. 每个条件跑 3 次（重复运行），记录 `revision_hash`、耗时、模型请求数。

评分表（每项 0–4 分，4=可直接投稿）：

| 维度 | 判据 | A | B |
|---|---|---|---|
| 语法硬错 | 主谓/时态/冠词/标点 | | |
| 术语一致 | 同概念单一写法；缩写首次定义 | | |
| 语义保持 | 数字/单位/引用/图表指向/否定范围 | | |
| 强度保持 | hedge 未削、booster 未加 | | |
| 语域贴合 | 符合目标体裁 | | |
| 说明可核验 | 每条改动可定位、理由成立 | | |

记录模板：

```json
{"case_id":"CASE-1","condition":"skill","repeat":1,"runtime_s":12.3,
 "revision_hash":"…","scores":{"grammar":4,"terminology":4,"meaning":4,"hedge":4,"register":3,"traceability":4},
 "manual_fix_items":["P004 冠词仍缺"],"rounds":1,
 "notes":"P003 术语 table 与正文一致"}
```

对照结论只写可核验的差异（分数、返修条目、轮次、`revision_hash` 是否稳定），不写主观「更专业」。

## 3. 回归测试小样（自备，非正式案例）

**T-A 摘要/限定强度**（英文）：

```
Reactive oxygen species (ROS) accumulate in the tumor microenvironment and may promote
epithelial-mesenchymal transition. We treated 48 mice with 25 mg/kg of the inhibitor for
14 days and observed a 32% reduction in tumor volume (p = 0.003) [12].
```

期望：`may promote`、`48`、`25 mg/kg`、`14 days`、`32%`、`p = 0.003`、`[12]` 全保留；`tumor→tumour` 需全篇一致；不得把 `may promote` 改为 `promotes`。

**T-B 术语漂移**（中英混排）：

```
材料与方法：细胞在 37 °C、5% CO2 条件下培养。活性氧（reactive oxygen species, ROS）水平用 DCFH-DA 法测定。
Results: intracellular ROS levels increased 2.1-fold (Fig. 3A).
```

期望：中文段与英文段使用同一缩写 `ROS`；`2.1-fold`、`37 °C`、`5% CO2`、`Fig. 3A` 保留；`reactive oxygen species` 只在首次出现处展开一次。

**T-C 中译英直译腔**：

```
通过我们的研究发现，在一定的实验条件下，该抑制剂对于肿瘤的生长起到了明显的抑制作用。
```

期望：拆为「主句 + 条件」结构，保留「一定实验条件」的限定（`under the tested conditions`），不得把「明显的抑制」升级为 `completely abolished`。

## 4. 已知边界与失败模式

- 扫描版 PDF（无文本层）：只能登记材料并请求可读版本，不能凭空生成稿件（记 `pdf_text` 降级）。
- 图片中的表格/图注：脚本不 OCR，图注内容未读 → `pending_human`。
- 引用编号存在而文献表缺失：只保留编号，不补文献。
- 术语表内部冲突（同一源词两种目标写法）：不自选，进 `pending_human`。
- 公式与 LaTeX：只改公式外文字；公式内的符号不改。
- 长文档（>20 万字符）：清单截断，正文全量保留，需分段处理时按 section 分批写 payload。
- 检查器是启发式：`fact_locks` 只做 token 级守恒（数/单位/引用），不判断语义等价；`hedge_strength` 只比对计数，不判断句法位置。因此 `checks` 全 pass ≠ 稿件一定合格，人工仍需读稿。

## 5. 维护

| 想改什么 | 改哪里 |
|---|---|
| hedge/booster 词表 | `scripts/main.py` 顶部 `HE / HZ / BE / BZ` |
| 数字/单位识别 | `scripts/main.py` 的 `NUM` 正则 |
| 段落切分与 heading 判定 | `scripts/main.py::seg`、`HEAD` |
| 新增检查项 | `scripts/verify.py::verify_all` 内 `add(id, status, detail, counts)`，并在 `SKILL.md` §11 与本文件 §1 登记 |
| 契约字段映射 | `scripts/verify.py` 的 `MAP` |
| 润色方法/语域 | `references/polish_protocol.md` |

版本策略：`SKILL.md` frontmatter 的 `version` 与 `main.py` 的 `V` 同步递增；行为变更需附一次 §3 小样的回归结果（`checks` 前后对比）。

体积约束：包内只保留 `SKILL.md` + `scripts/*.py` + `references/*.md`；单脚本 ≤20KB，文件总数 ≤12，总大小 ≤150KB，无 `__pycache__`/`.pyc`/示例大文件。
