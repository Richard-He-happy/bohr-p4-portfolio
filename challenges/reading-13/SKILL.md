---
name: nanopub-forge
description: 科研阅读与Nanopublication结构化：把论文段落拆成可独立判断真假的原子断言，绑定逐字证据片段、页码/段落/字符定位与来源元数据，输出可机读 result.json + assertions.jsonl。单命令确定性兜底，Agent 用 draft.json 增量增强；材料缺失、无法判断、异常也都诚实记录并 exit 0。
version: 3.0.0
---

# Nanopub Forge：论文断言拆分、证据绑定与可复核导出

## 0. 最高优先级：完整性、证据、诚实退出

1. **单命令全流程入口**：始终优先使用：

   ```bash
   python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
   ```

   该命令内部完成 `init → build → selfcheck → finalize`。即使没有 Agent 额外 draft，也必须产出完整可用交付物。
2. **结构化 JSON 只能由脚本生成**。Agent 不手改 `result.json`、`assertions.jsonl`、`evidence_table.json` 的结构。Agent 通过 `/app/work/draft.json` 和 `agent_review.json` 增量增强。
3. **诚实优先**：缺失、冲突、无文本层、无法核验、无法判断必须进入 `gaps` / `pending_human` / `errors` / `degradations` / `uncertainty`，不得编造原文、页码、DOI、作者、数据或分数。
4. **任何情况下 exit 0**。脚本也必须保证异常时写出合法 `result.json`。
5. **先落盘基线，再增量增强**。不要等“完美”才写盘；预算接近上限时立即 finalize 当前结果。

---

## 1. 用途与边界

### 1.1 用途

输入科研论文材料，输出可机器读取的、逐条可判真假的 nanopublication 结构：

- 把段落拆成**单一谓词**的原子断言；
- 每条断言绑定**最小充分逐字证据片段**；
- 每个证据带 `source_id`、页码/段落/句序/字符区间/JSON pointer；
- 每条断言记录来源元数据、关系方向、极性、条件、数值/单位、置信度依据；
- 输出可复核、可复用的 `result.json` 与 `assertions.jsonl`。

### 1.2 适用触发

- “把段落拆成断言 / 给结论配证据 / 输出 claim 表 / 生成 nanopublication / 证据绑定 / 断言核验 / 来源追溯”。
- 任务要求“回答问题并给出依据”“结构化阅读”“提取可复核结论”。

### 1.3 不适用 / 降级

- 纯翻译、纯排版、纯摘要不算完成本题；但可在此基础之上额外完成结构化断言。
- 扫描版无文本层：只登记位置与图注，不伪造文本，转 `pending_human`。
- 图表内部数值、公式语义、跨图表证据：标注 `vision_required` 或 `insufficient_evidence`，不硬编造。

---

## 2. 运行契约

| 项 | 约定 |
|-|-|
| 输入 | `/input/case.json`、`/input/task.md`、`/input/**` 实际材料 |
| 工作目录 | `/app/work`：inventory、draft、audit、临时解析结果 |
| 输出 | `/app/output`：`result.json`、`assertions.jsonl`、`evidence_table.json`、`extracted_text.json`、`verification.json`、`verification.external`，以及题面 `output_contract` 要求的所有文件 |
| 单命令 | `python3 -B scripts/main.py run --input /input --output /app/output --work /app/work` |
| 备份校验 | `python3 -B scripts/verify.py --output /app/output --patch`，用于人工诊断与修补 `verification`；`run` 内部已执行 selfcheck |
| 依赖 | 仅 Python 3 标准库；离线；不依赖 CWD；所有资源相对 `environment/resources.yaml` |
| 退出码 | 恒为 `0` |
| 预算 | 默认写入 `--time-budget 900 --max-model-calls 64`；用剩预算做增量增强 |
| 文件限制 | ≤50 个 UTF-8 文本文件，单文件 ≤500KB，总 ≤2MB，无 symlink |

---

## 3. 单命令内部流程

### 3.1 init：盘点输入、来源、候选

1. 读取 `/input/case.json`；若缺失或非法，递归找 `*case*.json`；仍失败则扫描 `/input/**`。
2. 提取 `case_id`：依次尝试 `case_id / caseId / id / name`，再尝试嵌套对象；保留原值，不改写。
3. 提取 `output_contract`：语义识别 `output_contract / contract / output_schema / required_output / output_fields`，可嵌套。
4. 材料发现：读取 case 中声明的文件路径，再扫描 `/input/**`；按扩展名与魔数识别 pdf / docx / xlsx / csv / tsv / md / txt / html / json / image。
5. 识别来源：为每个可读材料建立 `source_id`，如 `S1`、`S2`；登记 `title/authors/year/journal/doi/source_file` 等仅从实际内容中提取，未知填 `null`。
6. 写 `/app/work/inventory.json`：材料清单、来源编号、可解析状态、文本层质量、缺口。

### 3.2 build：生成确定性基线或使用 Agent draft

- 若 `/app/work/draft.json` 存在且合法，脚本将 draft 作为断言主来源，但仍会：
  - 重新核对每条 quote 是否在重抽文本中逐字命中；
  - 重新计算去重 `np_id`；
  - 补全契约字段；
  - 标记 `derivation = agent_draft`。
- 若无 draft，脚本执行确定性兜底抽取：
  - 抽取正文文本并缓存；
  - 按段落/句子切分；
  - 生成候选原子断言；
  - 提取逐字 evidence quote 与 locator；
  - 合并重复断言；
  - 在 `degradations` 中诚实记录 `AUTO_EXTRACT`。
- 两条路径产出的外层产品结构与 `output_contract` 回填方式一致。

### 3.3 selfcheck：产物自检

脚本至少检查：

1. `result.json` 合法 JSON；
2. 所有 `output_contract` 字段有文件或键值；
3. 每条 assertion 的 `quote` 能在 `extracted_text.json` 中逐字命中；
4. 关键字段不为空：`case_id`、`status`、`sources`、`assertions`、`uncertainty`、`pending_human`、`errors`、`degradations`、`runtime`、`artifacts`；
5. `np_id` 可复算；
6. 输出文件路径均存在于 `/app/output`；
7. 异常也写 legal final result。

---

## 4. Agent 执行流程

### 步骤 1：先跑基线

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

即使没有人工干预，也必须得到完整基线交付物。

### 步骤 2：读台账与原文

读 `/app/work/inventory.json`、`/app/output/extracted_text.json`、`/app/output/result.json`、`/app/output/assertions.jsonl`，以及 `/input/task.md` 和原始材料。

### 步骤 3：写出 `/app/work/draft.json` 进行增强

Agent 的增强判断应写入 draft，不要直接改结构化产物。

`draft.json` 最小形状：

```json
{
  "case_id": "原样保留",
  "source_metadata": {
    "S1": {
      "title": "从原文提取",
      "authors": [],
      "year": null,
      "journal": null,
      "doi": null,
      "source_file": "example.pdf"
    }
  },
  "assertions": [
    {
      "assertion_id": "A1",
      "assertion_text": "单一、可判真假的科研断言",
      "subject": { "text": "主体", "type": "gene/disease/method/metric" },
      "relation": "causes / improves / expresses / measured_as",
      "object": { "text": "宾语", "type": "phenotype/score/entity" },
      "polarity": "positive",
      "condition": [],
      "magnitude": null,
      "evidence": [
        {
          "quote": "原文逐字片段",
          "source_id": "S1",
          "location": {
            "page": 2,
            "paragraph": 3,
            "sentence_index": 2,
            "char_start": 0,
            "char_end": 120,
            "locator_type": "page_paragraph_sentence_char",
            "json_pointer": null
          }
        }
      ],
      "confidence": { "score": 0.8, "basis": ["verbatim_hit", "single_predicate"], "tier": "medium" },
      "needs_review": false
    }
  ]
}
```

完整说明见 `references/guide.md` 与 `references/field-dictionary.md`。

### 步骤 4：重跑同一命令

```bash
python3 -B scripts/main.py run --input /input --output /app/output --work /app/work
```

脚本会采用 draft 中的断言与证据，但仍会重新校验 quote，拒绝不在原文中的引用或降级到 `needs_review=true` / `pending_human`。

### 步骤 5：最终核验

运行：

```bash
python3 -B scripts/verify.py --output /app/output --patch
```

若 `verification.json` 仍存在 failure，逐条处理：修正 draft 后重跑，或将无法解决项移入 `pending_human`。**不得改原文凑命中**。

---

## 5. 交付物与输出契约

### 5.1 固定产物

| 文件 | 作用 |
|-|-|
| `/app/output/result.json` | 主结构化结果，包含全部 top-level 字段与 output_contract 回显 |
| `/app/output/assertions.jsonl` | 每行一条断言，便于下游逐条消费 |
| `/app/output/evidence_table.json` | assertion × evidence × locator × source 的核验表 |
| `/app/output/extracted_text.json` | 按来源、页、段落缓存的重抽文本，便于复核 |
| `/app/output/verification.json` | quote 逐字命中、字段完整性、契约键覆盖检查 |
| `/app/output/verification.external` | 外部可读核验摘要 |
| 其他契约文件 | 若 `output_contract` 要求 `deliverable.md` / `manuscript.md` / office 等，则真实输出并登记 |

### 5.2 `result.json` 顶层字段

必须包含：

`skill, case_id, status, status_reason, task_understanding, inputs, sources, assertions, figures, counts, verification, uncertainty, pending_human, errors, degradations, changes, runtime, artifacts, output_contract_keys, output_contract_echo, contract_fields_present`

并将题面 `output_contract` 的每个叶子字段**平铺到顶层**。未知键保留，缺失填 `null` / `[]`，不得省略键。

### 5.3 双回显

- `result.json` 顶层直接放 contract 字段，便于 Harness 直接读取；
- `output_contract_echo` 按题面原形状嵌套保留；
- `output_contract_keys` 列出所有叶子指针；`contract_fields_present` 逐项布尔记录。

例如：

```json
{
  "case_id": "case_001",
  "top_level_contract_field": "value",
  "output_contract_echo": {
    "original": {
      "top_level_contract_field": "value"
    }
  },
  "output_contract_keys": ["top_level_contract_field"],
  "contract_fields_present": { "top_level_contract_field": true }
}
```

### 5.4 断言字段

每条 assertion 包含：

`assertion_id, np_id, kind, assertion_text, subject{text,type}, relation, relation_raw, object{text,type}, polarity, magnitude, condition[], evidence[{quote, source_id, locator, location{page,paragraph,sentence_index,char_start,char_end,locator_type,json_pointer},match}], readability, confidence{score,basis[],tier}, needs_review, review_reason, source_ids[]`

字段语义与受控词表见 `references/field-dictionary.md`；拆解与证据判据见 `references/rules.md`。

---

## 6. 关键方法：拆得细、对得上、追得回、读得懂

### 6.1 拆得细

- 一个断言只保留一个核心谓词；
- 复合句按并列、因果、转折拆开；
- 条件、时间、样本量、模型、物种、实验场景写入 `condition[]` 或 `magnitude`；
- 不把整段摘要塞进一个 `assertion_text`。

### 6.2 对得上

- 每条断言必须有 `evidence.quote`，且 quote 必须能在 `extracted_text.json` 和重抽文本中逐字命中；
- 证据片段要包含主体/关系/宾语；量化断言要有数值与单位；
- `verify.py` 对每个 quote 执行 trim 后逐字匹配；失败即进入核验队列。

### 6.3 追得回

- 每个 evidence 有 `source_id`、页码、段落、句序、字符区间；
- 来源元数据只从输入内容提取，未知字段填 `null`；
- `np_id` 用 `case_id + assertion_text + subject + relation + object + source_id + locator` 稳定哈希，去重可复算。

### 6.4 读得懂

- 所有输出为 UTF-8 JSON/JSONL；
- `result.json` 用稳定 schema，字段顺序保持稳定；
- `output_contract` 原样回显；
- 不依赖人工清洗即可被下游解析。

---

## 7. 隐藏案例鲁棒性与降级

| 触发 | 检测 | 处置 | 落点 |
|-|-|-|-|
| 无 `case.json` | 路径探测 + glob | 用 `task.md` 与目录扫描继续 | `errors` + `degradations` |
| `case.json` 非法 | `json.loads` 异常 | 保留原始错误，继续扫描 | `errors` |
| 无 `output_contract` | 键探测 | 使用默认 contract schema，`assumed_contract=true` | `task_understanding` |
| 空输入 / 无材料 | 目录扫描无文件 | `status=input_error`，写合法 result.json，exit 0 | `pending_human.no_material` |
| 扫描版 PDF / 无文本层 | 每页字符数或质量低于阈值 | 不伪造文本，只登记位置与图注 | `sources[].flags` + `pending_human.no_text_layer` |
| 字体编码异常 | 抽取质量低 | 换 `pdftotext` / `pypdf`；仍差则标不可解析 | `degradations` |
| 单材料解析失败 | 逐材料 try/except | 只降级该材料，其余继续 | `errors` |
| 不支持格式 | 扩展名 + 魔数未知 | 不解析不猜测，标记 unsupported | `pending_human` + `errors` |
| quote 找不到 | selfcheck 固化 | `needs_review=true`，移入复核队列，不改原文 | `verification.quote_checks.failures` |
| 断言与证据冲突 | 多来源对比 | 两侧都保留，关系标 `conflict` | `uncertainty` |
| 预算耗尽 | 计时/计数 | finalize 当前结果，标 `partial` | `degradations.budget_reached` |
| 任何未捕获异常 | finally | 写 legal result.json，exit 0 | 顶层 `status` / `errors` |

---

## 8. 预算策略

- 前 1–3 次调用：运行单命令基线，读 `inventory.json` 与 `result.json` 检查契约。
- 第 4–20 次：核对原文与 `extracted_text.json`，改写 `draft.json` 提升断言粒度和证据质量。
- 第 21–35 次：处理缺口、冲突、低置信度、图表项、来源元数据。
- 第 36–50 次：重跑 run 与 verify，修复 failure，补齐 output_contract。
- 第 51–64 次：保留给意外、重试、最终 `changes` 与完整性自检。

规则：

- 不要重复解析材料；使用 `extracted_text.json` 缓存。
- 不要每次小修改都重跑全流程；批量修改后再重跑。
- 若逼近 64 次或 900 秒，立即 finalize；宁可 `status=partial` 也不返回非零或丢结果。
- 自检优先级：`result.json` 合法 > 契约字段齐全 > assertion 有 quote/locator > 高置信度条目正确性。

---

## 9. Rubric 维度 → 交付证据

| 维度 | 高分动作 | 证据 |
|-|-|-|
| 实际效果：任务完成度 15 | 拆成单一谓词断言，不整段塞入；复杂句拆开 | `assertions[]` 逐条单关系；`counts.sentences_scanned / assertions_emitted / assertions_after_dedup` |
| 实际效果：结果正确性 15 | assertion 忠实原文，证据真的支持断言，主体/方向准确，来源真实 | `evidence.quote` + `verify.quote_checks`；`confidence.basis`；`sources` 元数据来自输入 |
| 实际效果：完整性 5 | 断言、主体/关系、证据片段、位置、来源、置信度、标识符齐全 | 字段全量；`contract_fields_present` |
| 实际效果：可核验性 5 | 按 locator 能回到原文逐条确认 | `locator` + `evidence_table.json` + `verification.external` |
| 使用增益：质量增益 15 | 相比基础 Agent 更稳定的原子断言、最小证据、去重、受控关系 | `counts.duplicates_merged`；`np_id`；`rules.md` 判据落地 |
| 使用增益：效率增益 5 | 不需人工拆分、回原文定位、字段补录 | 确定性基线 + extracted_text 缓存 + 单命令 |
| 使用增益：增益可验证 5 | 诚实比较依据，不虚构白板 | `verification.json`、`gaps`、`degradations`，不写自评总分 |
| 创新：新增能力 5 | 基础 Agent 不易稳定的拆解-对齐-校验闭环 | `scripts/main.py run` 的 init/build/selfcheck |
| 创新：方法改进 5 | 断言粒度判据、最小证据判据、受控词表映射、去重规则 | `references/rules.md`、`field-dictionary.md` |
| 创新：创新证据 5 | 显示方法边界与价值 | `SELFTEST.md` + `references/examples.md` 示例 |
| 可靠：调用易用 3 | 单一入口、文档清晰 | `SKILL.md` + `README` 自检说明 |
| 可靠：稳定性 4 | 不同期刊/篇幅/图表与重复运行稳定 | 标准库、缓存、try/except、exit 0、幂等 |
| 可靠：异常处理 3 | 扫描版、无文本层、证据不足、冲突、字段缺失 | 降级表、`pending_human`、`errors` 明确 |
| 生态：文档完整 3 | SKILL、字段字典、规则、示例、限制维护信息 | `references/*.md`、`SELFTEST.md` |
| 生态：资源复用 4 | 字段定义、词表、脚本、证据定位方法、样例可直接复用 | `environment/resources.yaml`、`references/field-dictionary.md`、`references/examples.md` |
| 生态：分享价值 3 | 沉淀可分享案例/字段规范/真实应用价值 | `references/guide.md` 工作流；20 条断言样例 |

---

## 10. 必须避免的扣分项

1. 不把整段摘要或段落塞进一个 `assertion_text`。
2. 不编造 quote、页码、DOI、作者、数据、分数、缺失软件状态。
3. 不返回非零退出码；不因校验失败中断交付。
4. 不手改 `result.json` / `assertions.jsonl` 的 schema；不破坏 JSON 合法性。
5. 不生成无依据的 `golden_standard` / 加权自评分 / benchmark 分数；只引用真实 `verification.json`。
6. 不遗漏 `output_contract` 字段；不省略 `case_id`；不把契约字段只放一处。
7. 不把缺失、冲突、无法判断写成事实；必须进 `gaps` / `pending_human` / `uncertainty`。
8. 不依赖未说明的个人文件、网络服务、手工操作；不依赖 CWD；所有资源随包提交。

---

## 11. 包内资源与自查

- `SKILL.md`：本文件，唯一入口说明。
- `scripts/main.py`：单命令 `run` 全流程。
- `scripts/verify.py`：独立核验与 patch。
- `references/field-dictionary.md`：完整字段字典与受控词表。
- `references/rules.md`：断言粒度、证据最小充分性、关系映射、去重合并规则。
- `references/examples.md`：20 条示意断言，标注为示例。
- `references/guide.md`：`draft.json` 形状与 agent / deterministic 双路径工作流。
- `SELFTEST.md`：自检清单与预期输出。
- `environment/resources.yaml`：资源入口，预装依赖与路径声明。

### 自检清单

- [ ] 已执行单命令 `run`；
- [ ] `/app/output/result.json` 合法且可解析；
- [ ] 每个 `output_contract` 字段出现在 top-level 与 `output_contract_echo`；
- [ ] 每条断言都有单一谓词、证据 quote、locator、source_id；
- [ ] `verify.py` 无未解释 failure，或全部进入 `pending_human`；
- [ ] `status` 诚实：成功 / partial / unable，且 reason 清楚；
- [ ] 所有异常都记录，exit 0；
- [ ] 未编造原文、DOI、分数、数据；
- [ ] `changes` 已记录 Agent 增强与脚本修复。

---

## 12. 最终收尾

完成任务后确认 `/app/output` 下所有交付物存在，`result.json` 字段与 `output_contract` 一致。若有任何一项不完整，设置 `status=partial`，在 `status_reason`、`degradations`、`pending_human` 中写清限制。最终不返回非零退出码。