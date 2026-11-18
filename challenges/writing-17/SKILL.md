---
name: sci-mindmap-builder
description: 从论文/材料生成可编辑、可核验的思维导图（mindmap.svg + mindmap.json + content_map + PNG 预览 + result.json），并随产物落盘五项可核验资产（golden_standard.json 金标准、diff_report.md 逐项对照、version_history.md 版本记录、self_check.json 自检、run.log 日志）。Agent 主导提炼层级与关系，脚本负责索引、逐字证据校验、渲染与自检，工作稿缺失时兜底成稿。适用于文献结构梳理、研究方案、概念关系等材料→导图任务。
version: 1.1.0
---

# 材料 → 思维导图（sci-mindmap-builder）

## 1. 用途与边界

**做**：把 `/input` 中的论文/材料整理成一张分层思维导图——中心主题、若干分支、分支下的要点节点，节点带
材料 locator 与逐字 quote；输出可编辑 SVG、结构 JSON、预览 PNG、来源映射与 `result.json`。

**不做**：不新增材料里没有的事实、数值、文献或结论；不做 OCR（图片材料只登记、不臆造内容）；
不把"看起来像结论"的句子升格为结论——没有 quote 支撑的节点必须标 `status: "inference"` 并在
`pending_human` 中列出。

## 2. 运行契约

- 输入：`/input/case.json`、`/input/task.md` 与 `/input/**` 材料（PDF/DOCX/MD/TXT/JSON/CSV/图片…）。
- 工作区：`/app/work`（`index.json`、`mindmap.json` 工作稿、`check.json`）。
- 产物：`/app/output/{mindmap.svg, mindmap.json, content_map.json, mindmap.png, result.json}`，外加五项可核验资产
  `{golden_standard.json, diff_report.md, version_history.md, self_check.json, run.log}`（见 §15）。
- 命令：`python3 /skills/weekly-skill/scripts/main.py {init|show|check|build}`；退出码恒 0。
  `init`/`build` 可加 `--no-probe` 跳过空输入/坏输入子进程探针（赶时间时用，`self_check.json` 会显式标注未探测）。
- 依赖：仅 Python 3 标准库；`pdftotext`/`rsvg-convert`/`convert` 存在则优先使用，缺失即降级并记录。

## 3. 输入发现（不假设字段名）

`init` 会递归扫描 `/input`，按扩展名 **+ 魔数** 双识别（PDF `%PDF`、PNG `\x89PNG`、ZIP 系按
`word/document.xml` 等内部路径判定 docx/xlsx/pptx），读 JSON 用 `utf-8-sig`（防 BOM）；键名按语义匹配
（`case_id` / `output_contract` / `task_instruction` / `workorder` 等）。任何材料解析失败只降级该材料，
其余继续。

## 4. 输出契约（result.json）

原样回填 `output_contract` 的**全部**字段（不改名，缺值 `null`/`[]`），并附加：
`case_id`、`status`（ok|partial|insufficient_evidence|input_error）、`sources`、`uncertainty`、
`pending_human`、`errors`、`degradations`、`changes`、`runtime`、`artifacts`、`coverage`。
契约字段按语义映射：`deliverable`→产物摘要、`evidence_map`/`preserved_facts`→节点证据表、
`change_log`→变更记录、`content_map`→来源映射、`mindmap`/`structure`→结构摘要。

v1.1 追加四个字段（不动原契约）：`golden_standard`、`diff_report`、`version_history`、`self_check`，
各含 `path` 与可判读的摘要计数。**契约字段优先级更高**：若契约里出现同名键，保留契约回填值，
新字段降级为 `self_check.json` 里的说明。

## 5. 核心流程（4 步，必须按序）

**第 1 步：建索引（脚本）**
```
python3 /skills/weekly-skill/scripts/main.py init
```
打印任务摘要、契约字段、材料清单（id / 类型 / 字节 / 单元数 / 首段）。同时已写好 partial `result.json`
与工作稿骨架 `/app/work/mindmap.json`。**此时不要 build**。

**第 2 步：读材料并亲手写工作稿（Agent 的活）**
```
python3 /skills/weekly-skill/scripts/main.py show --material M1 --start 1 --limit 20
```
按 `[p.3¶2]` 这类 locator 读原文；先写 `theme`，再写 3–6 个主分支（level 1），每个分支下 2–5 个子节点
（level 2/3），最后补跨分支关系。**你写的每一个节点都要有 quote**。
节点总数 15–40（< 15 视为覆盖不足，> 40 视为规模失控）；当前的覆盖缺口会被 `diff_report.md` 逐条点名。

**第 3 步：自校验**
```
python3 /skills/weekly-skill/scripts/main.py check
```
`error` 必须修（quote 未命中、节点无证据、父子链断裂、关系类型非法）；`warn` 视情况修（标签过长、
层级过深、角色缺失、节点重复）。目标：`可 build`。

**第 4 步：成稿**
```
python3 /skills/weekly-skill/scripts/main.py build
```
渲染 SVG/PNG、写 `mindmap.json` 与 `content_map.json`、回填 `result.json`。工作稿缺失或全无效时脚本
仍会用材料要点兜底成稿（`status=partial`，`degradations` 说明）。

## 6. 导图设计规则

**层级**：`root`(中心主题) → level 1 分支（研究问题/方法/证据/发现/结论/局限/空白/任务/风险）→ level 2 要点 →
必要时 level 3 细化。深度 ≤ 4；同一父节点下 2–5 个子节点；同级粒度对齐（同一层不混"一句话结论"和"章节名"）。
层级用 parent 表达，父子链不得成环。同一父节点下的子节点标签不重复。
中心主题取自材料主题，不写“思维导图”这类元词。

**标签**：名词短语，≤ 20 字（超 30 字会被 warn），不带"综上所述""值得注意的是"等装饰语；一句话结论可放
`summary` 而不是 `label`。

**角色**（`role`）：`question` `method` `evidence` `finding` `conclusion` `limitation` `gap` `task` `risk`
`concept` `subtopic`。

**关系方向**（`edges`，只写跨分支关系；层级用 `parent` 表达）：

| type | 方向语义 | 何时用 |
|---|---|---|
| `cause` | 因 → 果 | 材料明说 A 导致 B |
| `contrast` | A ↔ B 对照 | 两组条件/结论相反或对照 |
| `support` | 证据 → 论断 | 某结果支撑某结论 |
| `conflict` | A ↔ B 冲突 | 两处材料结论不一致 |
| `sequence` | 先 → 后 | 步骤、时间线、阶段 |
| `depends` | 依赖 → 被依赖 | 方法/分析依赖某数据或前序 |
| `cite` | 引用方 → 被引 | 明确引用关系 |
| `example` | 概念 → 例证 | 例子支撑概念 |
| `definition` | 术语 → 定义 | 概念界定 |

无 quote 支撑的关系**不要画**（`build` 会自动丢弃并在 `degradations` 记录），宁缺勿造。
**关系证据**：无 quote 支撑的关系不画，标注 pending。

关系表逐行即"方向语义"的权威定义：`build` 会把本表逐行写进 `golden_standard.json` 的 `edge_semantics`，
评审可据此核对每条边的 from→to 是否符合语义（因→果、证据→论断、先→后…）。

## 7. 评分点 → 落地检查

| 评分关注 | 在产物中如何体现 |
|---|---|
| 抓得准 | 每个 `label` 是概念/方法/结论，不写装饰语；`role` 区分事实与推断 |
| 理得清 | `level` 由 `parent` 决定，深度 ≤ 4，同级 2–6 个；`depth`/`node_many` 有告警兜底 |
| 连得对 | `edges` 用上表类型与方向；无证据关系被丢弃并记录 |
| 证据可追溯 | 每节点 `evidence[{material, locator, quote}]`；`quote` 逐字命中才算 verified |
| 实际有用 | SVG 文字可改、节点有 id、PNG 可看；16–35 节点的一屏可读导图 |

## 8. 证据与定位规范

- `quote`：从材料**复制**的连续片段，10–200 字，不改写、不拼接、不翻译；中文标点保持原样。
- 引文保真：quote 从材料复制，不改写、不拼接、不翻译；长度 ≥6 字（建议 10–200，过短会失去定位价值）。比对做 NFKC 与空白折叠，仍不命中即 `verified:false`。
- `locator`：PDF `p.3¶2`（第 3 页第 2 段）、DOCX `¶7`、Markdown/文本 `¶12`、CSV `row5`、
  JSON `json:/path/key`、幻灯片 `slide3`、图片/表格 `figure2`（此类可无 quote，但须在 `summary` 说明）。
- 脚本比对时会做 NFKC、空白折叠与去连字符归一；仍不命中即判未命中——**不要为了过检改原文**。
- `status`：`fact`（原文直述）、`summary`（材料内的概括）、`inference`（你的推断，必须进 `pending_human`）。

## 9. 冲突、缺口与人工确认

材料互相矛盾：两个节点都保留，用 `conflict` 关系相连，`uncertainty` 写明分歧位置。
材料缺失（无该章节/无该数据）：不补，写 `pending_human`。
图片材料无文本：登记 existence，`uncertainty` 标注"未 OCR"，需要时请人工读图。

## 10. 预算与断点

单案例 64 次模型请求 / 900 秒。`init` 后即有合法 partial 产物；`build` 幂等，可反复运行覆盖。
接近 780 秒立即执行 `build` 收尾，不再扩写。

## 11. 异常降级表

| 情况 | 处置 | 记录位置 |
|---|---|---|
| `case.json` 缺失/坏 JSON | 仍跑 `init`，从 `task.md` 取名与契约空表 | `errors` / `degradations` |
| PDF 无文本层 | `pdftotext` 空 → 正则解流兜底；仍空则标无文本 | `uncertainty` |
| 无 pdftotext / 无 SVG 渲染器 | 用内置回退；PNG 缺失则保留 SVG | `degradations` |
| 工作稿缺失/全无效 | 确定性要点抽取兜底成稿 | `degradations` + `status=partial` |
| quote 命中失败 | 该证据标 `verified:false`，节点标 `unverified`，进 `pending_human` | `pending_human` |
| 节点爆炸（> 60） | 保留但告警，建议合并同级 | `degradations` |
| 材料全无文本 | `status=insufficient_evidence` | `status` |

## 12. 自检清单（build 前）

1. `theme.label` 是材料主题，不是"思维导图"。
2. 每个分支下 ≥ 2 个要点；总节点 12–35；深度 ≤ 4。
3. 每条 `quote` 都为原文连续片段，locator 指向具体页/段。
4. 跨分支关系 ≤ 6 条，方向符合第 6 节表。
5. `check` 输出 0 error；`pending_human` 里没有你能补的证据。
6. `build` 后确认 `mindmap.svg` 文字可编辑、`g#node-*` 数量 = `mindmap.json` 节点数。
7. 每个节点至少一条 evidence：material + locator + 逐字 quote；命中率应为 100%。
8. 节点里的数字必须能在材料或该节点 quote 中找到（对不上就是编造，删掉或补证据）。
9. 原样回填 output_contract 的全部字段，不改名、不遗漏。
10. SVG 每个节点带 id 与 data-quote/data-locator，文字可编辑。
11. `diff_report.md` 的缺失/偏差两栏应清零；`self_check.json.summary.pass` 应为 `true`。

## 13. 最小调用示例（示例，非正式案例结果）

输入（`/input/case.json` 片段）：
```json
{"case_id": "EXAMPLE", "task_instruction": "把材料整理成思维导图",
 "output_contract": {"deliverable": "可编辑导图", "evidence_map": "节点→来源", "change_log": "变更"}}
```
调用：
```
python3 scripts/main.py init
python3 scripts/main.py show --material M1 --limit 5
python3 scripts/main.py check
python3 scripts/main.py build
```
工作稿片段（示例）：
```json
{"theme": {"label": "催化剂的稳定性"},
 "nodes": [{"id": "n1", "label": "研究问题", "parent": "root", "role": "question",
            "evidence": [{"material": "M1", "locator": "p.1¶2", "quote": "原文连续片段"}]}],
 "edges": []}
```
产物：`mindmap.svg`（可编辑）、`mindmap.json`、`content_map.json`、`mindmap.png`、`result.json`。

## 14. 文件清单与维护

```
SKILL.md                      本文件（用途/契约/流程/规则/降级/可核验资产）
scripts/main.py               流程：init / show / check / build（纯标准库）
scripts/verify.py             模型库：证据核验、结构校验、布局与 SVG/PNG 渲染、契约回填
scripts/report.py             可核验资产层：金标准生成、逐项对照、版本记录、自检（含子进程探针）
references/mindmap-spec.md    工作稿 schema、关系词表、检查规则
references/golden-spec.md     金标准/对照/自检的 schema 与复用方法
references/example.md         端到端示例（示例，非正式案例结果）
```
修改规则：改 schema 需同步 `verify.py` 的 `normalize_model`/`validate` 与 `references/mindmap-spec.md`；
`quote` 校验口径只允许收紧不允许放宽；每次改动后跑一次空输入与坏 JSON 用例确认退出码 0。

## 15. 可核验资产（v1.1 新增，随产物落盘）

`init` 落骨架（对照为"待定"），`build` 覆盖为实测值；任一项失败只降级并记 `errors`。

| 资产 | 内容 | 复核方式 |
|---|---|---|
| `golden_standard.json` | 金标准：中心主题、主分支与分支规模、层级与父子关系、9 类边方向语义、节点→locator+quote 映射、契约字段 | 读 `structural_requirements[].source`：来源仅材料 locator+quote、`case.json#/output_contract/<key>`、本文件规则句 |
| `diff_report.md` | 实际 vs 金标准逐项：达标/偏差/缺失/待定 + 依据 + 待人工项 | 重跑 `build` 应复现计数 |
| `version_history.md` | v0 骨架 → v1 成稿：改了什么、为什么、检查点、回退 | 按文中步骤从 `work/history/` 回退 |
| `run.log` | 耗时、降级、异常 | 与 `degradations`/`errors` 对照 |
| `self_check.json` | 契约完整性、证据覆盖、数字一致、节点 15–40、层级、SVG、空/坏输入兜底（真实子进程）、退出码 | `summary.pass` 与 `checks[].observed` |

金标准不臆造：材料里找不到逐字引用的维度不进期待清单；`source.verified=false` 的条目在 diff 报告里单独暴露。
