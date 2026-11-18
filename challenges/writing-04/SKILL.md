---
name: citation-manager
description: 参考文献与引用管理 Skill。读取真实稿件与真实文献库（BibTeX / RIS / CSL-JSON / GB/T 7714 文本），完成论断级引用插入定位、顺序编码制编号连锁更新、文献去重归并（可解释判据）、GB/T 7714—2015 或 APA 7 格式转换、DOI 与元数据核验、正文—文献表一致性检查，产出可继续编辑的稿件、同步的文献表与逐条可回溯的 result.json。当用户要求"整理参考文献""补插引用""更新/重排编号""文献去重合并""改成 GB/T 7714 或 APA""核对正文引用与文献表是否一致"时使用。
version: 1.0.0
license: MIT
entrypoint: scripts/main.py
runtime: python3 >=3.9，仅标准库，无网络
---

# citation-manager（写作04｜参考文献与引用管理）

## 1. 用途与边界

一次运行完成六类动作中的可自动化部分：

| 动作 | 实现 | 主要产物 |
|-|-|-|
| A 引用插入与定位 | 识别缺来源的论断句（数字/百分比/统计与结论动词），按题名+摘要词项覆盖率匹配文献库，句末插入编号 | `change_log` / `citation_map` |
| B 编号连锁更新 | 按正文**首次出现**顺序重排 `[n]`，同步正文标记与文末列表；`[3-5]`、`[1,3]`、`^[1]^` 上标形式保留并按连续段压缩 | `manuscript.md` / `changes` |
| C 文献去重归并 | DOI 精确 → 规范化题名相等 → 题名相似+同作者+年份接近；冲突进入 `ambiguous_pairs`（不合并） | `dedup_decisions` / `merge_groups` |
| D 格式转换 | 统一条目模型 → GB/T 7714—2015（顺序编码制）或 APA 7th；保留 DOI、卷期页、类型标识 | `references_formatted.md` |
| E 来源核验 | DOI 语法、重复 DOI、按类型缺字段、孤立引用、编号连续性、数字/单位保留 | `verification` |
| F 论断–文献匹配 | 每条引用所在句与被引条目题名/摘要的词项重叠，低重叠标 `weak_match` → `pending_human` | `citation_map` |

**不做**：不联网检索、不补造 DOI/卷期页/作者、不改写事实与结论、不臆造文献条目。所有条目只来自输入文献库或稿件自带的参考文献表。

## 2. 适用条件

- 稿件为 Markdown/TXT（`.docx` 会抽取正文文本，但版式与上标样式丢失，需人工复核）；含或不含文末参考文献表均可。
- 文献库为 `.bib` / `.ris` / `.json`（CSL-JSON）或 GB/T 7714 文本列表。
- 需要中文顺序编码制或英文 APA 7；其他规范（Vancouver、Nature 等）需改 `references/styles.md` 的渲染规则，不在当前版本内。
- `.xlsx` / `.csv` / `.enw` 文献库**未内置解析器**：会被记为 `degradations: unsupported_or_unrecognized_format`，此时请先导出为 RIS/CSL-JSON 再运行。

## 3. 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`，材料在 `/input/**`（任意文件名与层级）。
- 工作目录 `/app/work`；产物写 `/app/output/`（不可写时退到包根同级 `output/`）。
- 只用 Python 标准库；不联网；不依赖当前目录（资源路径基于 `__file__`）。
- **退出码恒 0**；启动即写 partial `result.json`，结束时无条件 finalize 覆盖；任何异常写入 `errors`/`degradations`。

## 4. 调用方式

```bash
python3 -B scripts/main.py --help
python3 -B scripts/main.py                                   # /input -> /app/output, GB/T 7714
python3 -B scripts/main.py --input /input --output /app/output --style apa
python3 -B scripts/main.py --input ./caseA --output ./outA --no-insert   # 只出建议，不改稿
```

| 参数 | 说明 |
|-|-|
| `--input` | 输入目录，默认 `/input`；不存在时回退到 `/input`、包根同级 `input/` |
| `--output` | 输出目录，默认 `/app/output`；不可写时回退 |
| `--style` | `gbt7714`（默认）或 `apa` |
| `--no-insert` | 只登记引用插入建议（`change_log.applied=false`），不修改稿件 |
| `--version` | 打印版本 |

## 5. 输入发现（语义识别，不假设键名）

1. `case*.json`（含 `case.json`）逐个尝试解析；全部失败时递归找含 `case_id`/`output_contract`/`task_instruction` 的 JSON。
2. 语义读取 `case_id`、`output_contract`、`organizer_workorder`、`organizer_edit_workorder`、`task_instruction`、`formal_inputs`、`artifacts`…；键名不写死。
3. 递归扫描输入目录（≤120 个文件），按**扩展名+文件头魔数**判定类型：`docx`（zip+`word/document.xml`）、`bib`（`@type{`）、`ris`（`TY  -`）、`json`、`gbt`（含 `[J].` 等类型标识且可解析 ≥2 条）。
4. 稿件选择：在非文献库文件中按「是否含引用标记 + 是否含参考文献标题 + 长度」打分取最高；文献库为空时退回最长文本。
5. `case.json` 与选中的稿件文件**不参与**文献库解析，避免把稿件自带文献表重复计入库。
6. 材料未给出的对象写入 `missing_materials`，不构造内容。

## 6. 输出（`/app/output/`）

| 文件 | 内容 |
|-|-|
| `manuscript.md` | 主产物：编号已重排、缺引论断已补引、文末附目标规范文献表 |
| `references_formatted.md` | 目标规范文献表（可单独复制） |
| `references.json` | 规范化条目（含 `source`、`line`、`merged_from`、`type_code`） |
| `result.json` | 契约回填 + 全部结构化结果 |
| `report.md` | 人读摘要（计数、校验、待人工确认、错误/降级） |

`result.json` 固定字段：`case_id`、`skill`、`skill_version`、`status`、`generated_at`、`sources`、`manuscript`、`citation_map`、`evidence_map`、`preserved_facts`、`change_log`、`dedup_decisions`、`ambiguous_pairs`、`merge_groups`、`verification`、`counts`、`uncertainty`、`pending_human`、`missing_materials`、`errors`、`degradations`、`workorder_receipt`、`runtime`、`output_contract`、`outputs`，以及 `output_contract` 中声明的其余字段（原样回填）。

`status`：`ok` | `partial`（有 `pending_human`）| `insufficient_evidence`（无可解析文献库）| `input_error`（无稿件且无文献库）。

## 7. 核心流程

`discover → 选稿件 → parse_library（逐文件容错）→ 去重归并 → 文末表↔库对齐 → 论断级插入 → 首现编号重排 → 渲染 → 校验 → 落盘 → 契约回填`

关键算法（详见 `references/rules.md`）：

1. **条目规范化**：短键（t/a/y/j/v/i/p/d/pb/u/ab/ty）→ 统一字段；类型码统一映射到 GB/T 7714（J/M/C/D/R/S/P/N/EB/OL/DS/Z）。
2. **去重**：并查集 + 判据链（DOI 0.99 / 题名相等 0.95 / 题名相等但作者不同 0.80 / 题名相似≥0.93+同作者 0.88 / 同作者同年同刊 0.80）；阈值 0.80 合并，相似但无作者证据 → `ambiguous_pairs` 保留两条；题名相同但年份差 ≥3 → 拒绝合并。
3. **编号**：扫描正文标记，解析顺序编号（含区间）、`\cite{}`、`[@key]`、`^[n]^` 与内部插入令牌；首现顺序赋 1..n；输出时连续段压缩。
4. **论断匹配**：中文二元组 + 英文实词（去停用词）的词项集合；覆盖度 = |交集| / |条目词项|，≥0.20 且命中 ≥3 个实词才插入；被引过的条目降权 0.85 以鼓励多样化。

## 8. 质量规则（rubric → 字段 / 检查 / 产物）

| 评分要点 | 落点 | 判定方式 |
|-|-|-|
| 任务完成度 | `actions_done`、`counts` | 六类动作各自计数；`manuscript.md` 为可编辑 Markdown |
| 结果正确性 | `citation_map`、`evidence_map`、`dedup_decisions` | 每条引用有 key + 匹配证据；合并有理由 |
| 结果完整性 | `counts`（章节/引用点/条目/合并/插入/未解析/未引用） | 计数覆盖全部章节与引用点 |
| 结果可核验性 | 每条 `locator`（`manuscript.md#p<段>s<句>`、`library:<file>#<key>`）、`quote`、`sources[].sha16` | 可从成品回溯到原稿、库文件与每步改动 |
| 使用增益 | `verification`（10 项确定性检查） | 编号连续、无孤立引用、无重复 DOI、事实保留 |
| 效率增益 | `counts.auto_applied` vs `counts.pending_human` | 自动动作占比 |
| 创新增益 | `dedup_decisions[].reasons`、`merge_groups[].fills`、`change_log` 中 `kind=renumber` 的前后对照 | 判据可解释、编号可复现 |
| 可靠体验 | `errors`、`degradations`、`pending_human`、退出码 0 | 单文件失败只降级该文件 |
| 生态贡献 | `references/*.md`、本文件 | 说明与代码一致 |

## 9. 证据与定位规范

- `locator`：正文用 `manuscript.md#p<段落序号>s<句序号>`（1 基，段落=非空行），库条目用 `library:<源文件名>#<key>`。
- `quote`：取自源文件逐字内容（文献题名或论断原句），不改写、不拼接。
- `preserved_facts`：源稿中所有数字/单位 token（去除引用标记后提取），逐项标注 `kept` 是否仍在新稿中。
- `sources[]`：每个输入文件的 `id`、`kind`、`bytes`、`sha16`（SHA-256 前 16 位），用于对齐快照。

## 10. 冲突与人工确认

进入 `pending_human` 的情形：原文献表条目在库中找不到对应；论断与所引文献词项重叠过低（`weak_match`）；条目缺 volume/pages/DOI 等关键字段；文献库格式不支持。

原则：**保留原值 + 标注 + 不补造**。缺失字段在输出条目中写 `[待补]`，绝不填看似合理的值。

## 11. 预算与断点

单次运行秒级完成（纯正则与集合运算，无模型调用）。启动即写 partial `result.json`，此后任何异常都保留已写文件；`runtime.seconds` 记录真实耗时。

## 12. 异常降级分支

| 情形 | 处置 | 状态 |
|-|-|-|
| `case.json` 缺失 | 记 `errors`，仍扫描材料 | `input_error`（若无稿件/库） |
| `case.json` 坏 JSON | 记 `errors`，继续用文件扫描 | `insufficient_evidence` |
| 文献库空/无法识别 | 不造条目，稿件只做结构回显 | `insufficient_evidence` |
| 单文件解析异常 | 只降级该文件（`degradations`） | 继续 |
| 条目缺字段 | `[待补]` 占位 + `pending_human` | `partial` |
| DOI 非法 | 保留原值 + `doi_syntax=false` | 继续 |
| 编号指向文末表外 | 原样保留 + `unresolved_markers` | 继续 |
| 条目歧义 | 不合并 + `ambiguous_pairs` | 继续 |
| `.docx` 稿件 | 抽取正文文本，版式/上标丢失需复核 | `partial` |
| `.pdf` 材料 | 不解析正文，记 `unsupported_binary_pdf`（degradations） | 视其余材料 |
| `.csv`/`.xlsx`/`.enw` 库 | `unsupported_or_unrecognized_format` | 视其余材料 |

## 13. 自检清单

1. `result.json` 是合法 JSON，`output_contract` 的每个键都存在。
2. 正文编号为 1..n 连续，且每个编号在文末列表都有对应条目。
3. `citation_map` 每条都有 `key`、`locator`、`claim_quote`。
4. `dedup_decisions` 每条都有 `reasons`；`ambiguous_pairs` 未被强行合并。
5. `preserved_facts` 中 `kept=false` 的项已复核（多为引用标记内的数字）。
6. 文献表条目数 = 被引条目数；未引用条目记入 `counts.uncited_entries` 并未出现在列表中。
7. 无网络、无第三方依赖；`--help` 退出码 0。

## 14. 最小调用示例（**示例，非正式案例结果**）

输入（`/input`）：`case.json`（`case_id: "demo-A-001"`）、`manuscript.md`（含 `[1] [2] [3-4] [1,3]` 标记与 4 条 GB/T 文献表）、`refs.bib`（4 条）、`refs_dup.ris`（含 1 条与 bib 重复的 DOI 条目）。

```bash
python3 -B scripts/main.py --input /input --output /app/output --style gbt7714
```

示意输出（示例数值，非正式案例结果）：

```text
status: partial
library_records_raw: 7 -> dedup: 6 (merged_groups: 1, 以 doi_exact 合并)
citation_points: 7, inserted_citations: 1, unresolved_markers: 0
render_entries: 4, uncited_entries: 2
verification: 9/9 通过
manuscript.md#p13s1 ── 论断补引 [1]（score 0.20，命中 根系/胁迫/镉胁）
```

完整操作步骤见 `references/usage.md` §2，字段说明见 §4，限制见 §6。

## 15. 文件清单与版本

| 文件 | 作用 | 约 |
|-|-|-|
| `SKILL.md` | 入口说明（本文件） | 8 KB |
| `scripts/main.py` | 编排：发现/选稿/插入/编号/落盘/契约回填 | 20 KB |
| `scripts/reftool.py` | 文献库解析、规范化、去重、渲染、校验、workorder 回执 | 20 KB |
| `references/usage.md` | 完整调用步骤、字段说明、方法、限制、失败处理、示例 | 6 KB |
| `references/styles.md` | GB/T 7714—2015 与 APA 7 的字段映射与条目模板、类型码表 | 5 KB |
| `references/rules.md` | 去重判据、匹配阈值、检索正则、失败模式与调参指引 | 5 KB |

维护：改格式规则只动 `references/styles.md` 与 `reftool.render()`；改判据只动 `reftool.dec()` 与 `references/rules.md`；两者都不改 `main.py` 的流程结构。回归测试见 `references/usage.md` §7。
