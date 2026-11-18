---
name: intro-related-work-writer
description: 为学术论文起草或改写"引言 + 相关工作 + 研究空白 + 贡献"四段式正文，把每条引用绑定到材料原文的逐字证据。当用户要求"写引言""整理相关工作""补引用""核对贡献""推导研究空白""检查引用元数据/格式"时使用。输出可编辑 manuscript.md、evidence_map、preserved_facts、change_log、result.json。
version: 1.0.0
---

# 引言与相关工作写作（intro-related-work-writer）

## 1. 用途与边界

**做什么**：围绕一份真实论文材料（作者手稿 / 摘要 / 方法 / 结果 / 参考文献表），产出可直接进论文的四段式写作产物：

| 段落 | 必须交代 | 证据要求 |
|-|-|-|
| 研究背景 | 领域任务与技术约束 → 现有能力边界 → 具体未解问题 | 每条陈述挂 `[k]` 或 `[own]`，指向材料原文 |
| 相关工作 | 按问题/方法路线分组，同维度比较结论、适用条件、局限 | 每篇工作至少 1 条逐字 quote |
| 研究空白 | 由**已引文献**的共同限制/未覆盖场景/结论冲突推出，并落到本文对应动作 | 空白条目必须列出支撑引用 ID |
| 贡献 | 可核对条目，一条对应方法/图表/实验的一处 locator | 每条贡献 → 材料 locator |

**不做什么**（越界即降级，不静默编造）：
- 不新增材料外的文献、DOI、数值、图元素、统计量；
- 不替作者下"首次""最优"这类无材料支撑的断言（材料没写就标注为作者判断待确认）；
- 不做排版终稿（LaTeX 模板套版、期刊投稿系统适配）与查重。

## 2. 运行契约

- 输入：`/input/case.json`（+ `/input/task.md` 及 `/input/**` 材料：`.md/.txt/.json/.csv/.docx/.pdf/.xlsx`、图片名可在材料中仅作定位，不做像素推断）。
- 工作目录 `/app/work`，产物写 `/app/output/`。
- 入口：`python3 -B scripts/main.py --input /input --output /app/output`（可加 `--manuscript <已改写稿>` 复查）。
- 退出码恒为 0；任何异常进 `errors/degradations`；**先写 partial `result.json`**，结束无条件 finalize 覆盖。
- 只用 Python 标准库，不联网，不依赖 CWD（资源用 `Path(__file__).resolve().parent` 定位）。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `case.json`；不存在则递归找 `case*.json` / `task.md` 继续（找不到 → `input_error` + 仍写合法 result.json）。
2. `case_id`、`output_contract` **原样透传**；再按语义取用：`task_instruction` / `organizer_supplied_scope` / `organizer_workorder` / `organizer_edit_workorder` / `formal_inputs` / `runtime_files` / `artifacts` / `material` / `references` / `manuscript`；键名不固定时按内容形态判断（列表+含 year/title/abstract → 文献；长文本 → 手稿；含 `field/type` → 契约）。
3. 递归扫描材料目录，按扩展名 + 魔数（`%PDF`、`PK\x03\x04`）识别，**不用标签猜内容**。
4. 材料缺失的对象逐条进 `pending_human`（如"未提供参考文献表 → 相关工作只能写到本文自述层面"）。

## 4. 输出契约

`/app/output/` 下：

| 文件 | 内容 |
|-|-|
| `result.json` | 回填 `output_contract` 全部字段 + 下列结构化字段 |
| `manuscript.md` | 主产物：四段式可编辑稿（含 `## References`） |
| `related_work_matrix.md` | 分组 × 比较维度矩阵（路线/问题设定/数据与评价/结论/局限/引用 ID） |
| `evidence_map.json` | 论断 → source_id + locator + 逐字 quote + `quote_verified` |
| `preserved_facts.json` | 数字/单位/引用标记/术语逐字保留表 |
| `change_log.json` | 每条 `original_quote → revised_quote + reason + locator` |
| `sources_index.json` | 供独立复核的抽取文本索引（source_id → 路径/字符数/偏移） |

`result.json` 必备：`case_id`、`status`(`ok|partial|insufficient_evidence|input_error`)、`deliverables`、`sections_present`、`citations`、`evidence_map`、`preserved_facts`、`groups`、`gap_derivation`、`contribution_alignment`、`coverage`、`workorder_receipts`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`。详见 `references/output_schema.md`。

## 5. 核心流程（写—核分离）

1. **抽取**：把每个材料切块，记录 `(source_id, locator, text)`；PDF 走启发式文本抽取并标 `pdf_text_heuristic` 降级。
2. **分拣**：结构化条目 → 文献记录（authors/year/title/venue/doi/abstract）；长文本 → 本文材料；两处都不像 → `pending_human`。
3. **分组**：按路线词表对 title+abstract 打分聚类（title 权重 ×2），输出分组矩阵；无命中归 `unclassified` 并列入 `pending_human`。
4. **空白推导**：只在被引文献的句子里取带 `however/limited/cannot/fail/remains/仅/难以/缺乏` 等线索的**逐字**句子，按"共同限制 / 未覆盖场景 / 冲突结论"三类归并，再把本文材料中的对应动作接上。
5. **贡献对账**：从本文材料取含 `we propose/we introduce/本文提出/我们构建` 的句子 + `Table n`/`Fig. n` 引用，逐条给 locator；找不到依据的贡献条目标 `unaligned`。
6. **落稿**：用 `references/frames.json` 的框架拼装 `manuscript.md`（证据句 + 引用标记 + 改写指引注释），写 `change_log`（抽象句 → 稿中句）。框架内不含任何事实；文件缺失时降级为内置最小框架并记 `degradations`。
7. **复查**：`python3 -B scripts/verify.py --result output/result.json --sources output/sources_index.json` → quote 命中率、契约缺失字段、引用覆盖计数。作者改写后传 `--manuscript` 复跑，未命中 quote 一律降级/进 `pending_human`，不改原文凑通过。

## 6. 任务质量规则（rubric → 字段/检查/产物）

| 评分点 | 落地字段/检查 | 产物 |
|-|-|-|
| 四段齐全且承接 | `sections_present`（4 项布尔）+ 承接检查（空白条目必挂已引 ID；贡献条目必挂 locator） | `manuscript.md` |
| 转述与原文一致 | `evidence_map[].quote_verified`（归一化后逐字命中） | `evidence_map.json` |
| 引用元数据真实 | `citations[].metadata_status`（complete/partial/missing，缺 authors/year/title 即 partial↓） | `citations` + References |
| 空白由缺口推出 | `gap_derivation[].supports`（≥1 已引 ID）+ `basis_quote` | `result.json` |
| 贡献与实际结果相符 | `contribution_alignment[].aligned` + locator | `result.json` |
| 覆盖度完整 | `coverage`：路线数、文献数、带 abstract 比例、近 3 年占比、未分类数 | `related_work_matrix.md` |
| 可独立复核 | `sources_index.json` + locator 规范（`L12-L14`/`para7`/`c1024-1300`/`$.references[2]`/`row5`） | 全部 |

## 7. 证据与定位规范

- quote 必须能在 `sources_index.json` 对应 `source_id` 的原文中**逐字**找到（仅允许空白归一化）。
- locator 与源类型绑定：文本 `L<起>-<止>`；docx `para<n>`；pdf `c<起>-<止>`（抽取文本字符偏移）；json `$.a.b[0]`；csv `row<n>`。
- 同一论断多来源 → 多条 evidence 记录，不合并 quote。
- 无法定位 → `quote_verified=false` + `pending_human`，稿中该句改为 `[待核实]` 标注。

## 8. 冲突与人工确认

- 材料间数字/年份冲突：两条都留，进 `uncertainty`，稿中用首次出现者并标 `[conflict]`。
- 目标期刊格式未知：默认 author-year（`[k]` 编号 + References 列表），在 `uncertainty` 写明"格式未给定，按 author-year 输出，需按目标刊调整"。
- 语言切换：跟随 `task_instruction` 语言；未指定则按材料 CJK 占比判定（>15% → 中文）。
- 文献库为空 / 参考文献表缺失 → `status=insufficient_evidence`，仍交四段骨架与空白清单。

## 9. 预算与断点

64 次模型请求 / 900 秒 / 单回复 16384 tokens。脚本单次运行 <10 秒；>780 秒立即 finalize。中途任何阶段失败只降级该阶段（`degradations`），其余继续。

## 10. 异常降级分支表

| 情况 | 处置 | 字段 |
|-|-|-|
| `/input` 不存在或空 | 写默认骨架 + `input_error` | `status`, `errors` |
| `case.json` 坏 JSON | 记错、尝试同目录其他 json、继续 | `errors` |
| PDF 抽取乱码/过短 | 标 `pdf_text_heuristic`，只做粗粒度引用，不引具体数字 | `degradations`, `uncertainty` |
| docx/xlsx 损坏 | 跳过该文件，其余继续 | `errors` |
| 文献无 abstract | 只用 title/venue 归类，转述降为"标题层面"，标 `partial` | `citations` |
| quote 校验失败 | 稿中保留但标 `[待核实]`，进 `pending_human` | `evidence_map` |
| 无 output_contract | 用内置默认契约，仍输出全字段 | `runtime.contract_source` |

## 11. 自检清单（交付前）

1. `sections_present` 4 项全 true（或写明缺哪项及原因）。
2. `evidence_map` 非空，且 `quote_verified` 比例 ≥0.8 才可 `status=ok`。
3. References 每条有 authors/year/title；`metadata_status` 与之一致。
4. 每条 `gap_derivation` 有 `supports`；每条 `contribution_alignment` 有 locator。
5. `result.json` 中 `output_contract` 的每个键都存在（缺值 null/[]）。
6. 稿中无材料外数字/文献；数字全部能在 `preserved_facts` 找到。
7. 无 `__pycache__`、无临时文件、退出码 0。

## 12. 最小调用示例（示例，非正式案例结果）

输入 `input/case.json`：

```json
{"case_id": "demo-001",
 "task_instruction": "为本文写引言与相关工作，author-year 格式",
 "output_contract": {"manuscript_md": "path", "evidence_map": [], "status": ""},
 "material": {"manuscript": "本文提出一种…（材料原文）",
   "references": [{"key": "K1", "authors": "Li et al.", "year": 2021,
     "title": "A rule-based scheduler", "venue": "J. Sched.",
     "abstract": "Rule-based schedulers handle static workloads; however they cannot adapt to bursty arrival."}]}}
```

调用：

```bash
python3 -B scripts/main.py --input input --output out
```

示意输出（`out/`，**示例，非正式案例结果**）：`result.json`（`status="ok"`，`sections_present` 4×true，`citations[0].metadata_status="complete"`，1 条 `gap_derivation` 由 K1 的 "cannot adapt to bursty arrival" 支撑）、`manuscript.md`（4 节 + References）、`related_work_matrix.md`、`evidence_map.json`、`preserved_facts.json`、`change_log.json`。

## 13. 文件清单与版本

| 文件 | 作用 |
|-|-|
| `SKILL.md` | 本说明（流程、契约、rubric 映射、异常分支） |
| `scripts/main.py` | 主流程：发现→抽取→分拣→分组→空白→贡献→组稿→result.json（18KB） |
| `scripts/verify.py` | 共享库 + 独立核对 CLI：文本/PDF/DOCX 抽取、文献解析、路线词表、组稿模板、quote 命中与契约校验（19KB） |
| `references/frames.json` | 中英文组稿框架（标题/引导语/空白与参考文献模板），事实为空、只提供承接 |
| `references/writing_playbook.md` | 四段写法、分组维度、空白推导协议、贡献规范、路线词表、反模式 |
| `references/output_schema.md` | `result.json` 字段表、locator 规范、异常处置、引用格式、自检与维护 |

版本 `1.0.0`；纯标准库；无外部数据依赖；资源全部 UTF-8 文本。

## 14. 维护说明

- 路线词表在 `scripts/main.py::ROUTES` 与 `references/writing_playbook.md` 各存一份，改动需同步并升 version。
- 新增学科：在 `ROUTES` 增补领域术语即可，不改流程。
- 回归方式：用 `--input <新案例> --output out` 跑，检查 `coverage.quote_verified_rate` 与 `pending_human` 是否只含真缺口。
