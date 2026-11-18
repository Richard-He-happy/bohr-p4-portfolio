# 方法说明：拆解、比较、判定阈值与降级

## 1. 判定链条

```
case.json / task.md → 语义键名取值（topic、idea、time_window、inclusion、output_contract）
  → 材料扫描（扩展名+魔数识别，sha256 去重）→ 块级解析（p./para./rec./blk. 定位）
  → 术语抽取 → 证据单元筛选 → 四项交付 → 冲突/空白/覆盖 → 落盘 + 复核
```

## 2. 术语抽取（`appraise.tk`）

1. 拉丁词：≥3 字符、去掉英文停用词，小写计数。
2. 中文二元组：对每个 CJK 连续段取重叠二元组，剔除停用二元组（`ZH`）与含功能字（`的/对/在/为/是/和/与/及/等` 等，见 `FUNC`）的跨界二元组。
3. 跨界剪枝：若 `g` 的左邻词频与右邻词频都不低于 `g`，判定 `g` 是「某词 + 某词」的跨界产物并删除（例：`放速 = 释放 + 速率`）。
4. 包含剪枝：按频次降序保留，若 `g` 是已保留词的子串则丢弃。

> 这是**统计式切词**，不是词典分词。术语只用于检索式拼装与覆盖统计，不作为领域概念断言；报告中明确标注「术语拼装，需改写」。

## 3. 证据单元（`appraise.evid`）

- 句子切分按 `。！？!?；;` 与英文句末；长度 ≥12 字符。
- 入选条件：命中至少 1 个关键术语（case 术语 ∪ 各来源高频术语前 25）**且** 含结果提示词（`FC`：结果/表明/显示/发现/显著/found/show/indicat/…）。
- 排序分：命中术语数 + 提示词数；上限 60 条。
- `stance`：正负极性词表（`POS`/`NEG`）净差；`strength` 默认 `directly_supported`（原文直接陈述）。

## 4. 创新覆盖判定（`assess.dnov`）

- 陈述取 `innovation/novelty/创新点` 字段，按 `；;。` 切分；缺失时退回 `idea` 中含创新提示词（`CC`）的分句。
- 相似度 `overlap_score` = 陈述词集中出现在某来源词集的**比例**（未加权 Jaccard 变体，避免长文占优）。
- 阈值：`≥0.55` → `covered`；`0.30–0.55` → `partially_covered`；`<0.30` → `not_covered_in_materials`；无任何来源 → `undetermined`。
- 每条附「最近来源 + 定位 + 逐字引文 + 边界说明」。**判定范围仅为所给材料**，`scope_note` 强制写入。

## 5. 可行性前提（`assess.dfea`）

| 前提 | 识别线索（节选） |
|---|---|
| data | 数据/队列/样本/病例/dataset/cohort |
| compute | 算力/计算资源/gpu/集群/服务器 |
| experiment | 实验/仪器/平台/动物/细胞/伦理/审批 |
| time | 周期/随访/年限/follow/timeline |
| capability | 团队/人员/作者/合作/专家/expertise |

状态三分：`material_supported`（命中线索**且**含可获得性断言 `AC`：可用/已获得/具备/available/collected…）、`mentioned_not_confirmed`（只提及未确认）、`assumed_not_documented`（材料无）。

结论：支持 ≥4 → `feasible_with_conditions`；2–3 → `conditionally_feasible_pending_premises`；<2 → `insufficient_information`。

## 6. 冲突（`assess.dcon`）

对每个关键术语 `t`，收集含 `t` 的证据；若同时出现 `supports` 与 `contradicts`，登记一条冲突（支持/反对各带定位与引文）。处置：提及「指标/不同」→ 记为口径差异可并存；否则「材料内无法裁定」并置 `needs_human=true`。

**空集合的含义**：未检出 ≠ 不存在冲突，报告明确写出这一限定。

## 7. 纳排与时间窗

- 有 `time_window`（解析出 ≥2 个年份）：年份越界 → `included=false`，理由写入 `inclusion_reason`。
- 无年份 → `纳入(缺年份)`，不参与时间窗统计，并计入 `gaps.元数据`。
- 内容重复（sha256 相同）→ 只保留首个，其余不进入来源表。
- 无 DOI → 计入 `gaps.元数据`，`uncertainty.metadata`。

## 8. 状态判定

| 条件 | status |
|---|---|
| 无可用文本材料 | `insufficient_evidence` |
| 证据 <5 条或纳入来源 <2 | `partial`（并写 pending_human） |
| 证据 ≥5 且纳入 ≥2 | `ok` |
| 无输入目录 / case 不可读 | `input_error`（仍写合法 partial 结果） |

## 9. 预算与降级

- 目标 <60 s；`BUD=700 s` 软预算，超出即在 `runtime.within_budget=false` 记录并立即 finalize。
- 六级降级：无输入目录、case JSON 损坏、材料不可解析、PDF 无文本层、材料过少、判定层模块缺失——每级都只影响对应部分，其余照常产出，退出码恒 0。

## 10. 复核方法（`assess.py --check`）

1. `result.json` 可解析；
2. `output_contract` 每个键都在顶层；
3. 每个 claim 的 `evidence_ids` 都能在 `evidence` 中找到；
4. 重新解析原始材料，逐条验证 quote 是否为归一化原文子串（`quote_hit`）；
5. `evidence_map.csv` 行数 = evidence 条数。

`pass=true` 才可作为「可核验」依据；否则按 `misses` 定位并把该条降级为待人工。

## 11. 已知局限

- 规则法而非语义理解：术语切分、极性判断、覆盖阈值都可能误判；阈值集中在文件头常量，可改。
- 不支持 DOCX/XLSX 结构化解析（`degradations` 记 `unsupported`）；扫描件 PDF 无文本层需 OCR。
- 不联网：学术新颖性只能在材料范围内判定，报告中禁止外推为「全球首次」。
