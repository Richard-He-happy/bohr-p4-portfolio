---
name: academic-compliance-review
description: 对论文/科研材料做学术规范与合规检查，输出逐条带原文定位、逐字引用、依据、严重度与修改建议的结构化审查报告。用于审稿、投稿前自查，以及学术诚信、引用、隐私、版权、伦理、投稿要求的合规审查；产出 result.json + review_report.md + issues.csv。Agent 先读原文并写 draft.json，脚本提供确定性兜底抽取与契约回填；所有产物可复核、可复跑。
version: 3.0.0
---

# 学术规范与合规检查 Skill

## 0. 最高优先级：交付可复核的审查结论

你要完成的是“学术规范与合规审查”，不是泛泛提醒。每个问题必须能回指原文具体位置，并给出可独立核对的依据。评分最高权重是实际效果 40 分与使用增益 25 分，因此：

1. **禁止无依据结论**：不得凭文件名、领域标签、写作风格判断违规；不得编造参考文献、期刊指南、伦理批件、数据许可或统计结果。
2. **禁止只报泛化问题**：每条 `issues[]` 必须包含 `quote`、`locator`、`severity`、`verdict_type`、`reason`、`suggestion`、`evidence`。
3. **禁止偏科漏项**：必须覆盖材料中实际存在的风险面，六面检查逐面给状态；有证据不足就标 `insufficient_evidence`，有缺失就进 `pending_human` 或 `missing_materials`。
4. **禁止破坏基线产物**：脚本生成的基线候选、契约字段、来源台账不得删除。Agent 只能增量增强、核验、补漏或标记误报。
5. **诚实降级**：材料无法解析、PDF 无文本层、目标期刊指南缺失、文献无法离线核验时，必须写入 `errors`/`degradations`/`pending_human`，不得补齐成“通过”。

---

## 1. 单命令入口与运行策略

### 1.1 主命令（优先使用）

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部完成：

- **init**：盘点 `/input` 全部材料，建立来源编号 `S1..Sn`，抽取候选，按六面分组；
- **build**：校验 quote/locator，按 `draft.json` 或确定性兜底生成 issues、checks、report、CSV、result.json；
- **selfcheck**：检查 quote 是否逐字命中、契约字段是否双回显、CSV 与 JSON 是否一致、所有产物是否存在。

### 1.2 兼容旧版命令

若 `run` 子命令不可用，使用：

```bash
python3 scripts/main.py --input /input --output /app/output --stage scaffold
# 完成人工裁定并写入 /app/work/draft.json 后：
python3 scripts/main.py --input /input --output /app/output --stage finalize
```

无论哪条路径，都必须先落 partial，最终退出码必须为 0，任何异常也必须有合法 `result.json`。

---

## 2. 输入发现与契约解析

1. 递归扫描 `/input`，文件按名排序，最多 50 个；超出记 `degradations:file_cap`。
2. 读取 `case.json`，必须保留原始 `case_id`；递归查找 `output_contract`、`contract`、`result_contract` 任意键名。
3. 所有材料按**扩展名 + 实际内容**解析，不按文件名猜测：
   - PDF：使用环境提供的 `pdf-text-tool` 或 `scripts/extract.py` 提取文本；无文本层记 `pdf_no_text_layer`，该来源标 `unreadable`。
   - DOCX：读 `word/document.xml`。
   - XLSX：读 `sharedStrings` + `sheet*.xml`。
   - 文本类：直接按 UTF-8 读取。
   - 图片：只登记 `image_not_read`，不读取像素、不做图内推断。
4. `case.json` 中 ≥60 字符的字符串按 JSON Pointer 建为独立来源。
5. `/app/work/review/text/*.txt` 若存在，可作为转写补充文本，支持 `[[p3]]` 分页标记。
6. 材料未提供的对象（文献表、图、补充材料、伦理附件、期刊指南）必须列缺口，不构造。

---

## 3. Agent-first 双路径工作流

### 3.1 Agent 路径（有 draft）

1. 先运行主命令或 init，查看 `/app/work/review/packets.md` 与 `/app/work/review/candidates.json`。
2. 真实阅读 `/input` 全部原文材料，逐条核对候选中的 `quote`、`locator`、数字、统计量、引用、伦理/版权/投稿表述。
3. 将你的独立判断写入 `/app/work/draft.json`，每条问题可四选一：
   - **成立** → 进入 `issues`；
   - **证据不足** → 进入 `issues` 且 `verdict_type=insufficient_evidence`，同时进 `pending_human`；
   - **误报/风格差异** → 进入 `rejected_candidates`，写理由；
   - **脚本漏报** → 亲自追加 issue。
4. 写完后再次运行主命令，让 build 使用 draft 生成最终产物。

### 3.2 无 draft 时确定性兜底

如果 `/app/work/draft.json` 不存在，脚本必须仍生成实质工作稿：

- 抽取逐字 `quote` 与 `locator`；
- 生成六面候选 issues；
- 在 `review_records` 中写 `AUTO_EXTRACT: true`；
- 在 `degradations` 中写 `auto_extract_baseline`；
- 每条自动抽取的问题仍遵守 issue 字段契约，不得用模板句替代 reason/suggestion。

Agent 的目标是把自动基线升级为人工裁定，但不能删除自动基线，除非已用更高质量 draft 覆盖。

---

## 4. draft.json 形状

`/app/work/draft.json` 建议结构：

```json
{
  "case_id": "原始 case_id",
  "sources": [],
  "issues": [],
  "face_status": {},
  "pending_human": [],
  "rejected_candidates": [],
  "missing_materials": [],
  "assumptions": []
}
```

每个 issue 至少包含：

- `id`
- `check_face`
- `verdict_type`
- `severity`
- `locator`
- `quote`
- `basis`
- `reason`
- `suggestion`
- `evidence`
- `confidence`
- `pending_human`

---

## 5. 六面检查清单

必须逐面输出状态：`pass`、`issues_found`、`incomplete`、`not_applicable` 之一。

1. **学术诚信**：数据与图像复用、重复发表、不当署名、利益冲突声明、致谢与基金一致性。
2. **引用规范**：引文是否真实可核、元数据是否一致、正文论断与引文是否对应、引而不证、张冠李戴、格式不统一。
3. **隐私与数据合规**：可识别个人信息、受限数据、未公开数据，是否具备授权/伦理审批依据、脱敏建议。
4. **版权与许可**：图片、表格、代码、数据集等第三方材料来源标注、许可类型、复用条件。
5. **伦理审查**：人的研究知情同意、伦理批件编号与适用范围，动物实验规范，风险/获益表述。
6. **投稿要求**：将目标期刊/会议指南拆成可核对条目，逐条映射到稿件，报告缺失、超限、格式冲突，注明指南版本与日期。

离线无法验证文献是否存在、DOI 是否有效、批件真假时，统一标为：

- `verdict_type = insufficient_evidence`
- 进入 `pending_human`
- 不判成“事实错误”。

---

## 6. 问题分类与严重度

### 6.1 类型

- `factual_error`：可被原文或可核验依据证伪的事实错误。
- `insufficient_evidence`：原文依据不足、离线无法确认、需人工复核。
- `compliance_issue`：事实层面可能成立，但违反引用、隐私、版权、伦理或投稿规范。
- `suggestion`：风格、清晰度、结构、低风险改进建议，不得写成学术不端。

### 6.2 严重度

- `critical`：影响结论可信性、存在伦理/版权/隐私重大风险；
- `major`：影响审查通过或需作者必须处理；
- `minor`：局部规范问题；
- `suggestion`：改进建议。

### 6.3 locator 格式

使用 `S#|file#L行号|para段落号`，例如：

```text
S2|main.pdf#L142|para3
```

若来源是内联 JSON 文本，可用：

```text
S5|case.json#/materials/0/text|para2
```

---

## 7. 结果产物与 result.json 契约

### 7.1 必须交付

| 文件 | 说明 |
|---|---|
| `/app/output/result.json` | 主结果，契约双回显 |
| `/app/output/review_report.md` | 人读报告，六面覆盖、逐条问题、待复核/拒收、材料与运行说明 |
| `/app/output/issues.csv` | 与 `issues[]` 行一致，可排序、批注、交办 |
| `/app/work/review/packets.md` | 六面候选证据包 |
| `/app/work/review/candidates.json` | 机读候选 |
| `/app/work/draft.json` | Agent 判断稿，若存在 |

### 7.2 result.json 双回显

`result.json` 必须同时包含：

1. 顶层字段：
   - `case_id`
   - `status`
   - `issues`
   - `checks`
   - `summary`
   - `sources`
   - `uncertainty`
   - `pending_human`
   - `review_records`
   - `errors`
   - `degradations`
   - `changes`
   - `artifacts`
   - `runtime`
   - `contract_fields`
2. 嵌套 `output_contract`：原始 `output_contract` 要求的每个字段也必须在 `output_contract` 对象中出现一次，且 `case_id` 与顶层一致。

如果原始 `output_contract` 缺失或为空，依据 Runtime contract 默认字段准备回填；无对应值的键置 `null` 并记入 `contract_fields.unfilled`。

### 7.3 可编辑 Office/幻灯片/图形产物

若 `output_contract` 或题面要求 Office/slide/diagram 产物：

- 必须同时产生真实渲染的 PDF/PNG 预览；
- 若环境无渲染工具，写 `degradations:preview_missing`，`status` 不得为 `pass`；
- 不得伪造预览或谎称已渲染。

---

## 8. 隐藏案例鲁棒性

| 情况 | 表现 | 处置 |
|---|---|---|
| 正常学术论文/结题材料 | 有可提取文本，有引用/方法/统计/伦理/版权等风险面 | 按六面逐项审，产出完整 issues/report/csv |
| 边界材料：PDF 无文本层、扫描件、图片、内联文本 | 可解析部分仍可审；不可解析部分登记 | 可解析来源继续六面检查；不可解析来源标 `unreadable` 或 `image_not_read`；不猜测内容 |
| 材料非常短/只有任务说明 | 检查项仍需建立 | 对每面标 `not_applicable` 或 `incomplete`，说明材料不足以触发该面；不得编造候选 |
| 异常：缺 `case.json`、坏 JSON、空输入 | `status=input_error` | 退出码 0；输出合法 `result.json`；`case_id` 若能恢复则恢复，否则写 `case_id: null`；契约字段尽量置空并记 unfilled |
| 异常：特定工具不可用 | `errors` 记录工具名与失败原因 | 回退到标准库解析；仍无法解析则标 unreadable |
| 异常：材料缺失承诺的附录/文献/伦理附件 | `missing_materials` 列缺项 | 相关检查面标 `incomplete`，不要把“未提供”判成“违规” |
| 异常：目标期刊指南缺失 | 投稿要求面标 `incomplete` | 不编造期刊要求；写 `journal_guide_missing` |

---

## 9. 预算优先级：64 次模型请求 / 900 秒 / 16384 tokens

预算优先保证高权重项：实际效果 40 分 > 使用增益 25 分 > 创新/可靠/生态。

| 阶段 | 请求估算 | 策略 |
|---|---|---|
| 盘点输入、读 case/task/契约 | 2-4 | 一次性读取 |
| 运行 init/scaffold，读候选 | 1-3 | 脚本调用不计模型请求，但读产物计 |
| 按面读原文关键片段 | 8-15 | 合并读取，避免重复打开 |
| 六面逐条裁定 | 6-12 | 每面批量处理，不逐句循环 |
| 补漏、核验关键数字/引用 | 3-6 | 高权重面优先 |
| 写 draft、写报告、回填 result | 3-5 | 尽量一次生成 |
| 自检与契约核对 | 2-4 | 发现缺失低成本补齐 |
| 安全缓冲 | 5-10 | 保留，不主动用满 |

**落盘纪律：**

- 脚本 init/scaffold 完成后立即落 partial。
- 每完成一个检查面并可写回 issue，可增量更新一次。
- 约 50 次请求或约 700 秒时，停止新增检查，进入 finalize。
- 只剩 2-3 次请求时，只补契约字段与 status，不再扩写报告。

---

## 10. 误报抑制与正确性红线

以下情况**不得**直接判为问题：

- 仅因“用词风格/句式/学科惯例不同”；
- 仅因“没有主动声明某项非强制性内容”；
- 仅因“材料未提供”，除非该缺失本身构成规范问题；
- 仅因“引文无法离线核验”，必须标 `insufficient_evidence`，不写“引文不存在”；
- 仅因“疑似不当”，没有原文证据。

误报的每一条都会同时损害“正确性 15 分”和“质量增益 15 分”。宁可把不确定项留在 `pending_human`，也不要把启发式候选全量进 `issues`。

---

## 11. 自检清单（最终落盘前必须逐项核对）

1. `result.json` 顶层与嵌套 `output_contract` 都有原始 `case_id`。
2. 每个 `issue` 都有 `locator`、`quote`、`severity`、`verdict_type`、`reason`、`suggestion`、`evidence`。
3. `quote` 与原文逐字一致。
4. 六面检查都有状态；未检查项在 `summary.unaddressed` 或 `checks` 中说明。
5. `review_report.md` 与 `issues.csv` 与 `result.json.issues` 一致。
6. `sources` 中来源编号与正文 locator 对应。
7. 无对应值的契约字段置 `null` 并记入 `contract_fields.unfilled`。
8. 没有删除或清空 scaffold 基线产物。
9. 有异常时 `errors`/`degradations` 已写，`status` 诚实。
10. 退出码为 0。

---

## 12. 生态与复用声明

本 Skill 的资源与脚本应保持纯 Python 标准库、离线可用、`python3 >= 3.8`、不依赖当前工作目录。使用以下现有资源：

- `references/checklist.md`：六面详细检查项与触发条件；
- `references/examples.md`：问题写法、误报示例、建议措辞；
- `references/schema.md`：`result.json` 契约与 `draft.json` 字段说明；
- `scripts/extract.py`：PDF/DOCX/XLSX/文本提取；
- `scripts/main.py`：init/build/selfcheck 全流程入口。

如包内存在 `SELFTEST.md` 或 `environment/resources.yaml`，按其中说明执行；如不存在，则以本 SKILL 第 11 节作为自检清单。不得声称未随包提供的文件存在。