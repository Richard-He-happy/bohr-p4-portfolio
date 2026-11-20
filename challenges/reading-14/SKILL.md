---
name: literature-knowledge-graph
description: 从科研材料构建可回源、可查询的文献知识图谱；抽取实体与关系、别名归一与跨篇对齐、来源绑定，执行至少 3 个真实图谱查询，并导出 result.json、graph_raw.json、claims.json、queries.md、nodes.csv、edges.csv 与核验报告。Use when the task asks to turn papers into a queryable knowledge graph with nodes, edges, evidence locators, entity alignment, merge/conflict records or literature-graph queries. Not for single-paper translation, pure summarisation or generic QA without evidence.
version: 2.0.0
---

# 文献知识图谱构建：可复核、可回源、确定性兜底

## 0. 最高优先级：真实、可回源、先交付

本 Skill 的目标不是“生成一个好看的图”，而是：**每个实质节点和每条边都能回到某一篇论文的具体段落与原文短引；实体真实出现在原文中；关系方向与原文一致；跨篇合并有依据；不能合并的冲突被保留；查询实际执行且有证据。**

执行顺序固定为：

1. 先跑脚本获得全量确定性基线。
2. Agent 读原文，核验、修正、增强。
3. 再跑核验脚本，回填 `result.json`。
4. 任何情况下都优先保存合法 partial，不空手退出。

---

## 1. 运行入口

必须使用 `/app/work` 作为工作区，最终产物写入 `/app/output`。先建立目录，再执行基线命令：

```bash
mkdir -p /app/work /app/output
python3 -B /skills/weekly-skill/scripts/build_graph.py --input /input --output /app/output
python3 -B /skills/weekly-skill/scripts/verify.py --input /input --output /app/output
```

可合并为一条入口命令：

```bash
mkdir -p /app/work /app/output && python3 -B /skills/weekly-skill/scripts/build_graph.py --input /input --output /app/output && python3 -B /skills/weekly-skill/scripts/verify.py --input /input --output /app/output
```

说明：

- `build_graph.py` 是主流程：材料盘点、来源索引、候选抽取、实体/关系抽取、跨篇对齐、图导出、初始 `result.json`。
- `verify.py` 是核验与收口：引文核验、查询执行、CSV/报告导出、契约字段回填。
- 若 `build_graph.py` 已内部调用 `verify.py`，仍可在 Agent 修正后显式再跑一次 `verify.py`。
- 只用包内脚本与 Python 标准库；不联网；不依赖当前工作目录；退出码恒为 `0`。
- 第一阶段就要写 partial `result.json`。任何异常都被捕获并落盘，不能因异常导致空退出。

---

## 2. 输入与来源模型

固定案例通常提供：

- `/input/case.json`
- `/input/task.md`
- `/input/corpus-manifest.json`
- `/input/material.json`
- `/input/primary-material.json`
- `/input/secondary-material.json`
- 可能需要核对的 `/input/secondary-publisher.xml`
- 其他材料文件

关键规则：

1. **这是两篇独立论文**，不是同一篇 JSON 与 Markdown 的重复。
2. `primary-material.json` 保留第一篇论文；`secondary-material.json` 是新增的第二篇论文。
3. 根 `DOI/title/authors` 属于第一篇；**不得套用到第二篇**。
4. `corpus-manifest.json` 列出各篇 DOI、作者、来源哈希、许可证；来源元数据以 manifest 为准。
5. `material.json` 是正文段落汇总索引，不是原文本身；定位仍以 `primary-material.json` / `secondary-material.json` 的段落 ID 为准。
6. 位置字段使用组织方 JATS `paragraph_id`，**不是 PDF 页码**；不得生成“第 1 页”冒充原 PDF 页。
7. 正文行内公式/上下标可能已线性化；可参考 `secondary-publisher.xml`，但**不得推断底层数值**。
8. 不解析图像像素、补充附件、底层临床/实验数据；缺失时登记为缺口。
9. 同一篇存在多种文件格式，**不算跨篇证据**。

---

## 3. Agent-first 双路径

### 3.1 确定性兜底路径

如果 Agent 没有写下 `/app/work/draft.json`，`build_graph.py` 仍必须根据材料台账确定性地生成实质工作稿：

- 每个实体/边必须带逐字 `quote`。
- 每个实体/边必须带 `source_id`、`paragraph_id`、`char_span` 或等价定位。
- 自动抽取的内容必须诚实记录为 `AUTO_EXTRACT`，写入 `degradations` 或 `changes`。
- 不因缺少 Agent 草案而产出空图；只有材料确实不可解析时才允许空图。

### 3.2 Agent 增量路径

Agent 可写 `/app/work/draft.json`，其中包含对候选实体、关系、合并、冲突、查询问题的判断。随后再运行 `build_graph.py` / `verify.py` 将其并入最终产物。

允许 Agent：

- 读原文核验 `quote`、`locator`、数字是否与原文一致；
- 核验关系方向、合并依据、冲突保留；
- 把核验结论写入 `agent_review.json`；
- 亲自撰写/改写正文型交付物。

禁止 Agent：

- 手改 `claims.json`、`evidence_table.json`、`result.json` 等结构化 JSON 的字段结构；
- 删除脚本已产出的基线字段；
- 用文本编辑器覆盖 CSV/JSON 后伪装成脚本输出；
- 生成无来源的 `golden_standard`、白板分数或自评分数。

---

## 4. 材料解析与来源索引

### 4.1 来源盘点

先读 `/input/case.json`，提取：

- `case_id`
- `task_instruction`
- `output_contract`
- 材料清单或提示字段

若 `case.json` 缺失：

- 递归查找 `/input/case*.json`；
- 仍失败则扫描 `/input` 目录继续执行；
- 记入 `uncertainty[U-CASE]`。

### 4.2 来源划分

来源 ID 必须满足：

- 第一篇与第二篇使用不同 `source_id`；
- 首选 `corpus-manifest.json` 中每篇的 DOI 或 manifest 条目 ID；
- 无 manifest 时，使用 `primary-material` / `secondary-material` 的元数据；
- 同一段正文只保留一份；去重按内容哈希 + 文件优先级：
  `primary-material.json` > `secondary-material.json` > 其他原文文件 > `material.json` 汇总索引。

### 4.3 段落定位

- 优先读取 JATS 段落 ID，例如各 JSON/XML 中的段落 `id`；
- 若材料提供 `paragraph_id`，原样保留；
- 若没有组织方 ID，则生成合成 ID，并写入 `degradations[PID_SYNTHETIC]`；
- 合成 ID 不得冒充原 JATS/PDF 页码。

---

## 5. 实体、关系、对齐与冲突

### 5.1 实体抽取

可抽取的实体类型优先包括但不限于：

- 研究者 `researcher`
- 材料 `material`
- 方法 `method`
- 任务 `task`
- 指标 `metric`
- 结论 `conclusion`

抽取规则：

1. 实体必须是论文里真实出现的科研对象，**不得用常识补全概念**。
2. 优先使用 `references/graph_rules.json` 中声明的词表、cue、缩写/型号模式。
3. 同一段落内匹配不重叠，取最长匹配。
4. 规范化后分配稳定节点 ID，如 `n-<sha1[:8]>`。
5. 每个实体保留原始表述和至少一处 `quote`。

### 5.2 关系抽取

只建立有证据支持的关系。关系类型可包括：

- `uses`
- `compares`
- `outperforms`
- `supports`
- `contradicts`
- `derived_from`
- `same_as`

规则：

1. 必须存在句内 cue 与左右实体；
2. 不把共现、综述转述或推测当成直接证据；
3. 明确关系类型、方向和适用条件；
4. 每个实质边必须带来源与原文短引；
5. 线索不足时不建边；
6. 冲突处同时保留对立证据，各自带段号与引文，不覆盖、不裁决。

### 5.3 别名归一与实体对齐

同一论文内：

- 同一规范化形式可合并；
- 必须记录 `merge` 依据；
- 字符串字形相同或缩写相同但全称不同时，不得强制合并，保留不同节点并写入 `merge.non_merge_conflicts`。

跨篇对齐：

- 只有两篇文本能明确指向同一具体对象、样品、模型实例、数据集、注册标识时才合并；
- “相同通用方法/材料术语”不代表两篇使用了相同物理样品、模型实例、数据集或实验条件；
- 不能把两篇的条件、样本、数值结果合成一个结论；
- 每个指标只按来源分别列出，不做跨篇算术合并。

合并记录应包含：

```json
{
  "same_paper_merges": [],
  "cross_paper_merges": [],
  "non_merge_conflicts": []
}
```

---

## 6. 来源绑定与证据字段

每个实质节点/边必须至少满足：

```json
{
  "source_id": "来自 corpus-manifest 或材料元数据",
  "paragraph_id": "组织方 JATS 段落 ID",
  "evidence": {
    "quote": "原文短引，不超过 400 字符",
    "location": {
      "kind": "jats_paragraph_id",
      "paragraph_id": "同上"
    },
    "evidence_class": "direct|paraphrase|author_claim|other_reported"
  }
}
```

要求：

- `quote` 必须可在对应 `paragraph_id` 原文中找到或近于逐字；
- 不得用材料文件标签代替原文内容；
- 无法核验时保留条目，但在 `verify_report.quotes_failed` 中计数，并写入 `uncertainty[U-QUOTE]`；
- 不删除失败条目，保留原始证据供人工接管。

---

## 7. 图谱导出与查询要求

### 7.1 导出文件

至少导出：

- `graph_raw.json`：原始图
- `nodes.csv`：节点表
- `edges.csv`：边表
- `claims.json`：证据化论断
- `queries.md`：查询说明与结果
- `verification.json`：核验输出
- `result.json`：最终契约结果

其他题目要求的可编辑产物按 `output_contract` 补齐。

### 7.2 至少 3 个真实查询

每个查询对象必须包含：

```json
{
  "query_id": "Q1",
  "query_text": "...",
  "status": "executed|no_result|answered",
  "result_summary": "...",
  "evidence": [],
  "unresolved": [],
  "last_verified_at": "..."
}
```

要求：

- 至少 3 个查询实际执行；
- 每个查询展示结果子图、支撑证据以及无法确定的关系；
- `no_result` 也必须是真实执行后的结果，并说明可人工接管位置；
- 查询问题应覆盖图谱价值：例如实体查找、关系路径、跨篇对齐冲突、指标来源差异。

---

## 8. 最终 result.json 契约

最终 `result.json` 必须合法 JSON，UTF-8，退出码恒为 `0`。

结构要求：

```json
{
  "case_id": "...",
  "status": "ok|partial|insufficient_evidence|input_error",
  "sources": [],
  "nodes": [],
  "edges": [],
  "claims": [],
  "queries": [],
  "merge": {
    "same_paper_merges": [],
    "cross_paper_merges": [],
    "non_merge_conflicts": []
  },
  "uncertainty": [],
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "changes": [],
  "runtime": {
    "started_at": "",
    "finished_at": "",
    "python_version": "",
    "commands": []
  },
  "artifacts": [],
  "contract_coverage": {
    "filled": [],
    "unmapped_nulled": []
  },
  "verify_report": {
    "quotes_checked": 0,
    "quotes_failed": 0,
    "relation_direction_checked": 0,
    "relation_direction_failed": 0,
    "query_results_checked": 0
  },
  "output_contract": {}
}
```

关键要求：

1. 从 `/input/case.json` 读取的每个 `output_contract` 字段，必须在 `result.json` 顶层原样出现一次。
2. 这些契约字段，包括 `case_id`，还必须在 `result.json.output_contract` 中再出现一次。
3. 顶层 `case_id` 与 `output_contract.case_id` 必须一致。
4. 缺值用 `null` 或 `[]` 表示，并在 `contract_coverage.unmapped_nulled` 说明。
5. `status` 取值：
   - `ok`：关键契约字段非空，引文核验通过；
   - `partial`：已有实质交付但存在缺口或核验失败；
   - `insufficient_evidence`：材料可读但证据不足；
   - `input_error`：输入完全不可用。
6. 不得编造来源、引文、分数、白板结果、模型版本或 benchmark 分数。

---

## 9. 异常与隐藏案例鲁棒性

| 情形 | 必须行为 | 落点 |
|-|-|-|
| `case.json` 缺失或坏 JSON | 递归查找 `case*.json`；仍失败则扫描目录继续 | `uncertainty[U-CASE]` |
| `corpus-manifest.json` 缺失 | 从段落自带 `source_id`/`doi` 或正文 DOI 分篇；无法确定则标出 | `uncertainty[U-SOURCE]` |
| 输入为空或目录不存在 | 空图 partial，退出码 0 | `status=input_error` 或 `insufficient_evidence` |
| 无任何可解析段落 | 空图，退出码 0 | `pending_human[H-NOMAT]` |
| PDF 无文本层或图像型材料 | 跳过并列出人工项，不猜测数值 | `degradations[PDF_UNPARSED]` |
| 段落无组织方 ID | 生成合成 ID 并标注 | `degradations[PID_SYNTHETIC]` |
| 单文件解析异常 | 仅跳过该文件，保留其他材料结果 | `errors[stage=parse]` |
| 引文核验失败 | 不删除条目；计数并降级 | `uncertainty[U-QUOTE]` |
| 查询无结果 | 保留查询，`status=no_result`，说明人工接管位置 | `queries[]` |
| `output_contract` 缺失 | 使用默认字段集合并说明 | `uncertainty[U-CONTRACT]` |
| 超时或请求将尽 | 停止新工作，保存当前最完整 partial，退出码 0 | `degradations[TIMEOUT]` |

任何情况下都必须产出合法 `result.json`，退出码 `0`。

---

## 10. 预算策略：64 次模型请求 / 900 秒

优先级：

1. `output_contract` 字段完整
2. 节点/边/证据可回源
3. 跨篇对齐与冲突记录
4. 至少 3 个查询
5. 格式美化

建议分配：

- 第 1–3 次：读 `case.json`、`task.md`、`corpus-manifest.json`，锁定契约与两篇来源。
- 第 4–8 次：运行脚本，检查 stdout/stderr，记录已生成文件与缺失字段。
- 第 9–24 次：分批读取两篇论文的关键段落，重点核验脚本生成的实体/边对应原文。
- 第 25–36 次：核验重点实体/边，生成或修正跨篇对齐与 `non_merge_conflicts`。
- 第 37–46 次：执行并核验查询；为每类查询写结果、证据和不确定项。
- 第 47–56 次：回填或修正 `result.json`、`queries.md`、`claims.json`、CSV；必要时补 `pending_human`。
- 第 57–64 次：最终自检与兜底；若已接近 840 秒或请求接近上限，停止新工作，把当前最完整 partial 写成合法 `result.json`。

不要死循环读同一批大文件。脚本失败、解析失败、超时时仍要输出合法 `result.json`。

---

## 11. Rubric 自检清单

提交前逐项确认：

- [ ] `result.json` 合法且退出码为 0。
- [ ] `output_contract` 每个字段在顶层和嵌套 `output_contract` 中均存在。
- [ ] `case_id` 顶层与嵌套一致。
- [ ] `status` 诚实；缺口写入 `partial` / `pending_human` / `errors`。
- [ ] 两篇论文均进入图谱，第二篇未被第一篇元数据覆盖。
- [ ] 每个实质节点/边有 `source_id`、`paragraph_id`、`quote`。
- [ ] 没有 PDF 页码冒充。
- [ ] 没有把同篇多格式当成跨篇证据。
- [ ] 没有把通用方法/材料术语强制合并。
- [ ] 跨篇合并有明确依据；不合并项记录在 `non_merge_conflicts`。
- [ ] 至少 3 个查询实际执行并带证据；`no_result` 也保留。
- [ ] 自动抽取基线被记录为 `AUTO_EXTRACT`。
- [ ] 未报告、源内冲突、材料缺失全部显式登记。
- [ ] 未生成任何自评 `golden_standard`、白板分数或 benchmark 分数。

---

## 12. 禁区

1. 不编造原文没有的实体、关系、数值、引用或证据。
2. 不依据文件名或错误领域标签补造数据。
3. 不把 PDF 页码、自建页面号称为原 PDF 页。
4. 不推断图像像素、底层临床/实验数据或缺失附件中的数值。
5. 不把两篇论文的条件、样本、数值结果合并成一个结论。
6. 不删除脚本生成的契约字段或结构化 JSON 结构。
7. 不生成无来源的“金标准”或评分证据。
8. 失败时不以空结果或无退出码失败结束；必须保存 partial 并退出 0。