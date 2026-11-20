---
name: patent-topic-search
description: 专利与技术文献检索 Skill。给定公开号/申请号/授权号/优先权号或技术主题，由 Harness Agent 在授权来源（输入材料与本地语料）内真实解析材料，完成号码规范化、同族（仅观测链接）归并、法律状态分级核验、权利要求范围取证、技术文献候选检索与筛选留痕；脚本仅提供基线，最终交付物由 Agent 亲自核验、撰写并落盘 result.json + candidates.csv/json + query_log.json + verify_report.json，并对空结果、限流、鉴权失败、状态冲突、字段缺失给出降级与人工复核清单。不用于专利撰写、侵权判定、FTO 结论或价值评估。
version: 1.2.0
---

# 专利与技术文献检索（patent-topic-search）

## 0. 最高优先级：真实、完整、可核验，脚本只是工具

本 Skill 用于在有限、有授权的输入材料与本地语料中完成一次可复核的专利/技术文献检索。**脚本只是工具，最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把 `scripts/main.py` 生成的结果、CSV 骨架或模板字段直接当成品提交；你必须对关键结论做来源核验，并把核验证据写回 `result.json` 与 `verify_report.json`。

评审最看重的是：结果是否真实来自输入材料、公开号/申请号/授权号是否规范、同族与法律状态是否对得上官方登记、每条结果能否被独立复核。任何“看起来完整但经不起原文核对”的输出都会被判低分。

完整性优先策略：
1. 先运行本 Skill 自带脚本，产出全套基线交付物（所有 output_contract 字段、所有题面要求文件、所有 result.json 字段）。
2. 在基线之上，由你亲自核验关键论断、数字、引用的来源一致性；不得删除、清空或遗漏任何基线与契约字段。
3. 若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`、`pending_human` 或 `limitations`。
4. 提交前逐项核对「output_contract 字段 × 磁盘文件 × result.json 键」三者一一对应；partial 状态必须列出缺失项。

## 1. 用途与边界

**做**：从号码或主题出发，在**有授权的来源**内定位专利与相关技术文献，产出可被他人按记录复跑的证据集：
号码规范化 → 同族（仅观测链接）归并 → 法律状态分级 → 权利要求取证 → 主题检索与筛选 → 契约回填与自检。

**不做**（越界即失分）：
- 专利撰写与权利要求起草；侵权判定、FTO 结论、专利价值评估；替代专利律师意见；
- 绕过付费墙、上传受限数据、对外展示受限库原文；
- **不补造**号码、文献、DOI、法律状态、引用、分数或“最新进展”；
- 不依据文件名、领域标签或“常识”猜测材料内容；必须读取实际输入文件。

**三个硬边界**（题面点名的失败模式，本 Skill 专门规避）：
1. 公开号/授权号/申请号**混用** → 每个号码带 `number_kind` 与 `role`，未知即标 `unknown` + `warnings`。
2. **同族当权威结论** → 只按语料中**观测到的**优先权/申请号连边，标注 `observed_links_only` 与“非穷尽”，不等同于权利要求范围相同。
3. **法律状态来自转载页** → 无官方登记定位时状态一律为 `not_in_corpus`，进 `pending_human`，绝不用 kind code 推断有效/失效。

## 2. 运行契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`（或 `task.md`）与 `/input/**` 内的材料；**只读** |
| 输出 | `/app/output/`：`result.json`、`candidates.csv`、`candidates.json`、`query_log.json`、`verify_report.json` |
| 工作目录 | `/app/work`；执行前创建 `/app/work` 与 `/app/output` |
| 脚本入口 | `python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output` |
| 依赖 | Python 3.8+ **标准库**；平台预装 PDF 文本提取工具（如 `pdf-text-tool`、`pdftotext`）可用于 Agent 亲自复核；**不联网** |
| 退出码 | **恒为 0**（含参数错误、空输入、坏 JSON、阶段异常） |
| 预算 | 64 次模型请求 / 900 秒 / 单次响应 16384 tokens（含推理）。脚本本身不消耗模型请求；Agent 的工具调用与读写则计入预算 |
| 首次落盘 | 第 0 步一开始就写合法 `result.json`（`status=partial`），随后在步骤 1 由脚本覆盖为基线，Agent 增强后再覆盖为最终版 |

脚本分工（共 2 个，均在 `scripts/`，各 ≤20KB）：
- `scripts/main.py`：编排 / 候选组装 / 筛选 / 契约回填 / 自检 artefact；
- `scripts/ptcore.py`：输入发现、号码规则、同族、状态分级、权利要求、检索打分。

不要重写或绕过脚本的核心规则，除非你有明确证据表明脚本输出与输入材料冲突；此时保留原始输出，并在 `changes[]` 中记录你做了什么、为什么。

## 3. 输入发现（语义识别，不假设键名）

1. 读 `/input/case.json`；不存在则找任意 `**/case*.json`；仍无则退回 `task.md` 文本（并写 degradation）。
2. 原样保留 `case_id` 与 `output_contract`（不改键名、不丢未知键）。
3. 递归扫描 `/input/**`，按**扩展名 + 内容语义**识别：
   - `.json/.jsonl`：记录、查询、缓存响应；
   - `.csv`：记录表；
   - `.pdf`：专利传真件/论文；
   - `.md/.txt`：正文、权利要求、任务说明；
   - 图片：记缺口，不硬 OCR（除非平台工具明确可用且结果可复核）。
   记录判定看是否存在公开号/申请号/优先权/分类号类字段；文献判定看 DOI/题名/作者/期刊。
4. 文件名含 `quer` → 视为**声明的检索式**（写入 query_log，标 `explicit`）；含 `response/hit/api/result` → 视为**缓存响应**（记录 `http_status`，429/401/403 走降级）。
5. 材料未给的对象**明确列缺口**（`gaps` / `pending_human`），不构造内容。

**你亲自复核时**：不要只看文件名；对每个关键文件读取实际开头/字段，确认它是不是你以为的类型。如果文件名与内容不符，以内容为准，并在 `degradations[]` 中说明。

## 4. 输出契约（`result.json`）

```text
case_id, status, skill, generated_at, input_case
<output_contract 的每一个键，原样键名>
sources[], uncertainty[], errors[], degradations[], pending_human[], changes[], runtime{}
contract_fill{contract_echo, filled_from_payload, placeholder_only}
candidates[], queries[], screening[], coverage{}, families[], clusters[], legal_status[], claims[],
citations[], metrics{}, gaps[], summary{}, gain{}, artefacts[], self_check{}, verification{}
```

- **契约回填**：`output_contract` 每个键都出现在根级；语义匹配（如 `results/papers/documents` → `candidates`）则填真实数据，否则按原值类型给空占位（`[]`/`{}`/`""`/`null`），并在 `degradations` 记录“未映射键已空占位、未编造”。`contract_echo` 保留原始契约。
- `status`：`ok`（有候选且无 error）/ `partial`（有材料但未完成或有 error）/ `insufficient_evidence`（无可检索内容或输入缺失）。输入缺失不单列 `input_error`，而是 `insufficient_evidence` + `errors[]`（说明“输入缺失”）。
- `reviewed_by_agent`：在 `result.json` 根级或 `self_check` 中记录哪些字段被 Agent 亲自复核过。推荐在 `changes[]` 中记录每一项 Agent 增强动作。
- 字段级说明见 `references/output_fields.md`。

## 5. 核心执行流程（6 步：先基线，后亲自核验与撰写）

### 步骤 0：盘点输入与契约，立即落盘最小 partial（约 1–3 个模型动作）

**输入**：`/input` 目录。

**动作**：
1. 列出 `/input` 下所有文件，读取 `case.json` 与 `task.md` 的关键字段：`case_id`、`output_contract`、任务指令。
2. 若 `case.json` 不存在，找任意 `**/case*.json`；仍无则读 `task.md` 全文，并把任务文本作为后续解析对象。
3. 创建 `/app/work` 与 `/app/output`。
4. 立即写一个最小合法 `/app/output/result.json`：包含 `case_id`、`status=partial`、`skill`、`generated_at`、`input_case`、根级 output_contract 空占位，以及空的 `errors/degradations/pending_human/changes`。

**输出**：可读的最小 partial `result.json`；输入文件清单记在上下文中。

**失败分支**：如果连 `case_id` 都无法确定，使用 `case_id="UNKNOWN"`，`status="insufficient_evidence"`，`errors[]` 写入“输入缺失/不可读”，仍退出 0。

### 步骤 1：运行脚本生成全套基线交付物（0–1 个模型动作）

**动作**：
```bash
cd /app/work && python3 -B /skills/weekly-skill/scripts/main.py --input /input --output /app/output
```
脚本会生成 `/app/output/result.json`、`candidates.csv`、`candidates.json`、`query_log.json`、`verify_report.json`。**这次运行是基线，之后不要无差别重跑**，否则会覆盖你后续的 Agent 增强。

**输出**：全套基线产物，状态可能为 `ok` 或 `partial`。

**失败分支**：如果脚本崩溃或没有生成 `result.json`，你自己按本文件第 4 节字段构造最小合法 `result.json`，并在 `errors[]` 记录 `stage=script_baseline` 的异常；继续后续流程。

**关键**：从这一步起，脚本生成的字段是基线；后续你可以在基线上修改/增强，但**不得删除、清空或遗漏任何基本字段**。若对字段有疑问，保留原值并新增 `warnings` 或 `changes`。

### 步骤 2：真实解析材料，核对脚本产物（约 8–18 个模型/工具动作）

**输入**：`/input` 文件清单 + 基线产物。

**动作**：
1. 对每类关键材料亲自解析：
   - **PDF**：用平台预装 PDF 文本提取工具（如 `pdf-text-tool` 或 `pdftotext`）提取文本，记录提取器名和页数。若 PDF 无文本层或为扫描传真件，记录 `errors[]` 或 `gaps[]`，不猜测文字。
   - **JSON/JSONL/CSV**：读取记录字段，确认公开号/申请号/优先权号/分类号、来源、日期、响应状态。不要只读第一行就下结论。
   - **MD/TXT**：读取权利要求、技术主题、任务说明；对关键句记录 `locator` 和逐字 `quote`。
2. **核对基线候选**：对 `candidates[]` 中每个高相关候选，检查：
   - `source_file` 与 `locator` 是否真的指向原文；
   - `evidence.quote` 是否逐字存在；
   - `numbers` 的 `number_kind/role/kind_code` 是否与原文一致；
   - `legal_status` 是否有官方登记依据；
   - `family` 是否只基于材料中观测到的优先权/申请