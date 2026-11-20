---
name: literature-field-extraction
description: Extract per-field results from a paper (PDF/DOCX/XLSX/CSV/MD) against a supplied target-fields.json, with a verbatim quote and paragraph/page/table locator for every field, four honest statuses (reported / not_reported / source_conflict / extraction_failed), and a result.json filling every output_contract key. Use when a case ships a field list plus source material and asks for structured literature data, conclusions or conditions rather than a prose summary.
version: 2.1.0
license: MIT
---

# 文献结论与数据提取（逐字段 + 原文证据 + 完整性优先）

## 0. 最高优先级：完整性优先与真实推导

本 Skill 的脚本只是工具。**最终交付物由你（Harness Agent）亲自读材料、推导、撰写/制作。** 禁止把脚本骨架、模板、示例输出或未经验证的候选结果直接当成品。运行本 Skill 后必须形成“基线 + Agent 增强”的完整交付：

1. **先跑基线，再改进**：进入任务后先运行本 Skill 自带的主脚本/流程，产出全套基线交付物，包括所有 `output_contract` 字段、所有题面要求文件、所有 `result.json` 字段。
2. **保留全部基线产物**：后续 Agent 的校验与改写只能在此基线上增强；不得删除、清空或遗漏任何基线与契约字段。若不确定，保留原产物并在 `result.json` 中标注 `reviewed_by_agent`。
3. **完整性自检（提交前必做）**：逐项核对「output_contract 字段 list × 磁盘文件 × result.json 键」三者一一对应；缺任何一项先补齐再收尾；`partial` 状态必须列出缺失项。
4. **可核验增强**：在基线产物之上，由 Agent 亲自核验关键论断/数字/引用的来源一致性，把核验结果写进 `result.json`（`verified` / `pending_human` / `conflicts`），这才是“genuinely-derived”的证据。

## 1. 用途与边界

把案例（`/input/case.json` + `target-fields.json` + 论文/表格）转成**逐字段可核对**的结果：每个 `field_id` 一行，含值、单位、统计量、条件、对照、四状态之一、逐字 `quote`、可定位 `locator`。

- 适用：结论/条件/数值/证据定位；正文、表格、图注、补充材料同表处理。
- 不适用：替作者补结论、跨文献合并、把摘要式总结当交付。
- 铁律：猜出来的值不算抽取；原文没有 ≠ 0；quote 字面命中 ≠ 语义正确——语义由你判断，脚本只校验字面与覆盖。

## 2. 运行契约

| 项 | 值 |
|---|---|
| Skill 目录 | `$SKILL_DIR`（评测机 `/skills/weekly-skill`，勿写死） |
| 输入 | `/input/case.json`、`task.md`、`target-fields.json`、材料 |
| 工作/产物 | `/app/work` 草稿与索引；`/app/output` 交付 |
| 依赖 | `python3 -B`，纯标准库，不联网，不依赖 CWD |
| 退出码 | 恒 0；失败也写合法 `result.json` |

脚本命令（只能调用包内真实文件）：

```bash
S=$SKILL_DIR/scripts
python3 -B $S/main.py init     # 建索引 + 首份 partial result.json
python3 -B $S/main.py show --grep "IC50" --limit 20
python3 -B $S/main.py show --para M1-p0002
python3 -B $S/main.py check    # 校验草稿
python3 -B $S/main.py build    # 定稿产 extraction.* + result.json + 5 个可核验资产
python3 -B $S/main.py audit    # 只重算 golden_standard/diff_report/version_history/self_check/run.log
python3 -B $S/main.py build --no-audit   # 只出 v1 产物（不生成可核验资产）
```

`main.py check|build` 转发到 `build.py`（也可直接调用）。不要引用包内不存在的文件或命令。

## 3. 输入发现与真实解析（脚本已实现）

1. 递归扫 `/input`；`case.json` 缺失时取 `case*.json`，按 `utf-8-sig` 读、容忍尾逗号。
2. 字段表取 `target-fields.json` 或 case 内 `target_fields|fields`；语义键：`field_id|id|key`、`label|name|question`、`aliases|keywords`。
3. 材料按**扩展名 + 魔数**识别：`%PDF`（优先 `pdftotext -layout`，缺失时 zlib 流解析并记降级）、`PK`+`word/|xl/`（DOCX/XLSX）、CSV/TSV、MD/TXT/JSON；图片无 OCR 只记降级，不造内容。
4. 排除自身产物与配置；段落 id `M1-p0002`，PDF 另给 `page`；索引写 `/app/work/index.json`、`paragraphs.json`。

**必须真实解析材料内容。** 用 `main.py show` 或直接查看 `/app/work/paragraphs.json` 读取实际文本。不得依据文件名或领域标签猜测/补造内容。失败或降级必须记录到 `degradations`。

## 4. 核心执行流程（Agent 主导，逐步完成）

### 步骤 1：盘点输入与确认契约

- **输入**：`/input/case.json`、`task.md`、`target-fields.json`（若存在）、材料文件。
- **动作**：运行 `python3 -B $S/main.py init` 生成 `/app/work/workorder.md`，阅读其中任务、字段表、材料表、契约键。确认 `output_contract` 的全部键名，后续 `result.json` 必须原样回填这些键。
- **输出**：明确任务边界、字段清单、契约键清单、材料清单、时间预算。
- **失败分支**：`case.json` 缺失或坏：记录 `input_error`，但仍继续用可用材料+字段表构造结果。`target-fields.json` 缺失：若 case 内有字段表则用 case 内；否则降级为从任务说明中提取字段，并在 `uncertainties` 说明字段来源不完整。

### 步骤 2：用工具真实解析材料并建立索引

- **输入**：步骤 1 得到的材料清单。
- **动作**：`init` 已经完成解析。用 `python3 -B $S/main.py show --grep "<关键词>" --limit 20` 和 `show --para <paragraph_id>` 亲自读原文。对每个候选字段，至少读该字段所在段落及前后一段；若来自表格/图注，读取对应表/图附近文本。
- **输出**：候选段落、表格行、图注原文，归档到 `/app/work/draft.json` 草稿或 notes。
- **失败分支**：材料损坏/无法解析：对应材料所有字段标 `extraction_failed` 或 `not_reported`（视有无证据），写入 `degradations` 与 `pending_human`。PDF 无文本层：降级为 `pdf_no_text_layer`，不 OCR 编造。

### 步骤 3：构建/核对证据并逐字段判定

- **输入**：步骤 2 的原文片段与字段表。
- **动作**：按 §8 四状态判定顺序（有无 → 是否一致 → 是否读得出）为每个 `field_id` 确定状态。对 `reported`，保留值、单位、统计量、条件、对照，并从原文复制逐字 `quote` 与 `locator`。对非 `reported`，写清搜索词、已查章节/表/补充材料范围。对 `source_conflict`，保留双方 `quote` 与可定位信息。对 `extraction_failed`，写清失败点与已试手段。
- **输出**：写入 `/app/work/draft.json`（schema 见 §7）。
- **失败分支**：候选段歧义/跨页缺行/单位缺失：不推测，标 `extraction_failed` 并在 `pending_human` 说明可人工接管位置。

### 步骤 4：Agent 亲自产出完整成品（基线 + 增强）

- **输入**：步骤 3 草稿。
- **动作**：
  1. 运行 `python3 -B $S/main.py check` 校验草稿，按 §12 错误码逐条修；
  2. 运行 `python3 -B $S/main.py build` 生成基线交付物（`extraction.*`、`result.json`、五个可核验资产）；
  3. **Agent 亲自复核关键字段**：打开 `result.json`、`extraction.csv`、`golden_standard.json`、`diff_report.md`，核对每个 `reported` 的值/单位/条件/引用是否与原文一致，状态是否诚实，定位是否可复核；
  4. 在基线上增强：修正错误、补充缺失项、完善 `claims`/`uncertainties`/`pending_human`，随后再次 `build` 覆盖。
- **输出**：完整交付物与增强后的 `result.json`，保留基线全部字段，新增 `reviewed_by_agent` 等核验标记。
- **失败分支**：时间或请求预算不足时，保留最近一次合法 `result.json`，标注 `partial` 和 `missing` 列表；绝不清空基线。

### 步骤 5：自检 rubric 与修复

- **输入**：步骤 4 的全部产物。
- **动作**：对照 §13 rubric 维度自证表逐项检查。运行 `python3 -B $S/main.py audit` 重新生成可核验资产或检查现有资产。检查 `self_check.json` 的 `summary.failed` 是否为 0；若有失败项，在 `uncertainties` 写明失败项与原因。
- **输出**：`self_check.json`、`diff_report.md`、`version_history.md`、`run.log` 与更新后的 `result.json`。
- **失败分支**：审计发现 `gap` 或 `deviation`：返工对应字段；`needs_review` 写进 `pending_human`。若单项确实无法解决，诚实标注 `insufficient_evidence` 或 `partial`，不删除项。

### 步骤 6：回填 result.json 并落盘最终产物

- **输入**：步骤 5 修复后的所有数据。
- **动作**：确保 `/app/output/result.json` 包含：
  - 原 `output_contract` 的全部字段（键名不改，未知键也保留，缺值 `null`/`[]`）；
  - `case_id` 原样保留；
  - `status` 根据实际完成度选择：`answered`/`ok`（全部字段已处理且无未解决 gap）、`partial`（有未解决但已标注）、`insufficient_evidence`（证据不足）、`input_error`（输入错误）；
  - `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`；
  - 若 Agent 已复核，加入 `reviewed_by_agent`、`verified`、`conflicts` 等字段。
- **输出**：最终 `/app/output` 下所有交付物；退出码 0。
- **失败分支**：任何异常都写合法 `result.json`，退出码恒 0。绝不因单字段失败导致整体无输出。

## 5. 预算策略：64 次模型请求 / 900 秒 / 16384 tokens 单响应

预算感知原则：**先完成 rubric 权重最高的交付物，优先落盘 honest partial，再增量改进。**

建议分配（按模型请求数）：

| 阶段 | 请求数范围 | 必须做/可跳过 |
|---|---|---|
| `init` + 读 workorder | 1–2 | 必须做；确认字段与契约 |
| 批量 `show` 读原文候选段 | 5–15 | 必须做；优先覆盖所有字段，表格/图注附近至少一次 |
| 写 draft + `check` 修复 | 2–5 | 必须做；可先写部分字段即 check |
| `build` 生成基线 | 1–2 | 必须做；尽早落盘 partial |
| Agent 复核 + 增量修复 + 再 `build` | 3–8 | 按剩余时间做；优先修正 `reported` 和 high-weight 字段 |
| `audit` + 最终自检 | 1–2 | 必须做；产出可核验资产 |
| 总预算上限 | ≤64 | 若接近 80% 预算，停止检索，直接 `build` 并标注 `partial` |

- 不要重复解析同一段落或反复 `check`；一次批量读取多个段落。
- 优先处理字段表中出现次数多、评分权重高的字段（如结论、条件、数值）。
- 每完成一批字段就运行 `build` 落盘（幂等覆盖）。任何时候 `/app/output/result.json` 都应是合法 JSON。
- 剩余 <150 秒：停止一切非必要检索/审计，只执行 `build` 保证产物完整。

## 6. 隐藏案例鲁棒性与降级

任何情况下都必须产出合法 `result.json` 并退出码 0。以下场景按优先级处理：

| 场景 | 降级策略 |
|---|---|
| `case.json` 缺失/坏 | 记 `errors`，继续用材料+字段表，`status=partial`；完全没有字段表则 `input_error`，仍写全部契约键。 |
| `target-fields.json` 缺失 | 若 case 内无字段表，从 `task.md` 提取可能字段，并在 `uncertainties` 注明“字段来源于任务卡而非正式字段表”。 |
| 材料缺失/损坏 | `input_error` 或 `partial`；对应字段标 `extraction_failed`，写入 `degradations`。 |
| PDF 无文本层 | `degradations: pdf_no_text_layer`，所有相关字段 `extraction_failed`，`pending_human` 说明需 OCR 或人工。 |
| 表格跨页/缺行/合并单元格 | 不推测缺失行，标 `extraction_failed` 或 `source_conflict`；在 `locator` 和 `reasoning` 写两页页码及已读内容。 |
| 单材料解析失败 | 只降级该材料涉及的字段；其他材料正常处理。 |
| 草稿缺失/坏 JSON | 关键词检索候选 quote，字段标 `extraction_failed` + `fallback_used`，覆盖率写进 `counts`。 |
| 空输入/无字段 | 产出最小合法 `result.json`：`fields:[]`、`claims:[]`、`uncertainties:["no target fields found"]`、`status=input_error`。 |
| 输出契约缺失键 | 在 `result.json` 中原样回填全部已知契约键；未知键也保留，缺少值用 `null`/`[]`。 |
| 超时/请求用尽 | 保留最近一次 `build` 产物，标注 `partial`，在 `uncertainties` 写“未完成字段清单”。 |
| 冲突/无法判断 | 标 `source_conflict` 或 `insufficient_evidence`，保留双方证据，不偏袒不合成。 |

## 7. 草稿 schema（`draft.json`）与 result.json 字段

草稿写 `/app/work/draft.json`：

```json
{"case_id": "原样", "fields": [
  {"field_id": "F1", "label": "IC50", "value": 12.4, "unit": "nM",
   "statistic": "95% CI 10.1-15.2 nM", "condition": "25 degrees C, 30 min, triplicate",
   "comparator": "vehicle", "source_kind": "text|table|figure|abstract|supplement",
   "status": "reported", "quote": "原文逐字片段",
   "locator": {"material_id": "M1", "paragraph_id": "M1-p0002", "page": 3,
               "table": "Table 2", "row": "control", "col": "mean"},
   "reasoning": "怎么读出：句子/单元格/图注；单位与统计量来源", "conflict": null}],
 "claims": [{"id": "C1", "kind": "author_conclusion|limitation|speculation|data_point",
             "text": "结论", "quote": "逐字", "locator": "M1-p0005", "field_ids": ["F1"]}],
 "uncertainties": [], "pending_human": []
}
```

最终 `result.json` 必须包含：

- 原 `output_contract` 全部字段：`case_id`、`status`、`result`、`claims`、`uncertainties`；
- 额外字段：`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`runtime`；
- Agent 增强字段（可选）：`reviewed_by_agent`、`verified`、`conflicts`；
- `status` 取值：`answered`/`ok`、`partial`、`insufficient_evidence`、`input_error`。若原契约要求 `status` 为 `answered|partial|insufficient_evidence|input_error`，则适配该集合，优先用 `answered` 代替 `ok`。

## 8. 四状态判定

| status | 含义 | 必填 |
|---|---|---|
| `reported` | 原文明确给出 | `value`+`quote`+`locator`（+`unit`/`statistic`/`condition`） |
| `not_reported` | 材料范围内确实没有 | `reasoning`：搜索词、已查章节/表/补充材料 |
| `source_conflict` | 多处说法不一致 | 双方 `conflict.quote_a`/`quote_b`（可加 `value_a`/`value_b`），`value` 写首选并注明 |
| `extraction_failed` | 有候选但读不出（无文本层、跨页缺行、单位缺失） | `reasoning` 写失败点与已试手段 |

判定顺序：材料里有没有 → 多处是否一致 → 能不能读出来。`not_reported`（原文没有）与 `extraction_failed`（有但没读成）不得互换。

## 9. 证据与定位

- `quote` **逐字复制**（可省略号截连续片段；不改词、数、标点顺序，不翻译）。脚本三级校验：`quote_strict` > `quote_normalized`（大小写/空白）> `quote_loose`（去标点，记 warning）；找不到即 error。
- `locator` 至少 `material_id`+`paragraph_id`；PDF 加 `page`；表格给 `table`+`row`+`col`（跨页写两页页码）；图给 `figure` 子图号。"结果段"这类二手定位不可接受。
- 数值在正文、CI 在表格时：`quote` 取主值处，另一处写进 `reasoning`。
- `claims.kind` 区分作者结论、限制、推测、数据点；推测不得升格为事实。

## 10. 数值、单位与条件

- 保留原值形态：`12.4` 不写 `12`；`10.1–15.2 nM` 不改写成 `±2.5`；不换算单位（换算值只进 `reasoning`）。
- `statistic` 存误差/区间/检验量原文（`SD 0.4`、`p = 0.03`）；`condition` 存温度/时间/剂量/样本/基线；`comparator` 存对照或比较组；原文没有就留空，不写 "N/A" 猜测。
- 表格：数字与表头逐字保留，列不交换，合并单元格跨行时 `locator.row` 写所属组；表格与正文数值不同即 `source_conflict`。
- 图注只取文字明确写出的数值；像素读数标 `approximate: true` 并给误差。

## 11. 冲突与人工复核

- 冲突**保留双方**，两侧 quote 都要能在原文查到（否则 warning `conflict_sides`）。
- 不自造 `field_id`；`pending_human` 用于扫描件、单位缺失、跨页缺行、quote 仅 `loose` 命中、需领域换算。

## 12. check 错误码 → 处置

| code | 处置 |
|---|---|
| `missing_field` | 补该 `field_id` |
| `bad_status` | 改四状态之一（小写） |
| `quote_not_found` | 回 `show` 复制原文（多为改写/断字） |
| `bad_locator` | 段落 id 不存在，用真实 `M*-pNNNN` |
| `empty_value` / `quote_missing` | 补齐，或降级 `extraction_failed` 并写依据 |
| `no_justification` | 非 `reported` 补搜索词与范围 |
| `quote_loose` / `number_not_in_quote` / `conflict_sides` / `no_reasoning` | warning：核对后修，或保留并在 `uncertainties` 说明 |

`result.json` **原样回填** `output_contract` 全部键（不改名、不遗漏未知键，缺值 `null`/`[]`），并补 §7 列出的额外字段。

## 13. Rubric 维度 → 交付要求 → 自证方式对照表

| Rubric 维度 | 交付要求 | 自证方式 |
|---|---|---|
| 实际效果：任务完成度 15 分 | 按字段表覆盖全字段，不遗漏；正文/表格/图注/补充材料同表处理 | `fields` 数组长度等于 `counts.target_fields`；`extraction.csv` 行数等于字段数；`source_kind` 覆盖多种来源 |
| 实际效果：结果正确性 15 分 | 值与原文一致，单位/误差/统计量/条件不被改写、合并、换算；结论/限制/推测分层 | `reported` 字段的 `quote` 可严格命中；`claims.kind` 分类正确；`conflict` 保留双方 |
| 实际效果：结果完整性 5 分 | 缺项区分为“原文未报告”与“抽取失败”，不填猜测值 | 非 `reported` 字段提供 `reasoning` 与搜索词；`counts` 四状态之和等于字段总数 |
| 实际效果：结果可核验性 5 分 | 每个字段可回到页码/段落/表格行/图注；字段定义与口径随结果提交 | `locator` 含真实 `paragraph_id`/`page`；`references/field_dictionary.md` 与 `extraction` 口径一致；`self_check` 中 locator 粒度通过 |
| 使用增益：质量增益 15 分 | 加载 Skill 后比基础 Agent 抽取质量稳定提升 | 基线 `build` 后 Agent 复核增强；`reviewed_by_agent` 记录核验项；`diff_report.md` 显示 match/deviation/gap 与修正 |
| 使用增益：效率增益 5 分 | 单篇耗时、人工核对条目、重试成本下降 | `run.log` 记录步骤耗时；脚本自动建索引/校验/产出，Agent 只需复核；`self_check` 记录退出码与失败重试 |
| 使用增益：增益可验证性 5 分 | 公平对照证明改善 | 保留基线产物与增强产物路径；`version_history.md` 记录修改与回退；`audit` 重新生成同一口径的可核验资产 |
| 创新增益：新增能力 5 分 | 条件与数值同源绑定、跨页表格还原、字段级证据定位、结论与推测分层 | `fields` 中 `condition`/`comparator` 与 `value` 同时出现；`locator` 支持 `table`/`row`/`col`；`claims.kind` 区分四类 |
| 创新增益：方法改进 5 分 | 字段表设计、来源切分、多来源对齐、证据定位、校验回填策略有实质改进 | `references/field_dictionary.md` 记录字段词典与口径；`golden_standard.json` 自建基准与词面重扫；`self_check` 17 项真跑空/坏输入 |
| 创新增益：创新证据 5 分 | 证明创新点相对已有方案边界和价值 | `references/verification_assets.md` 说明资产 schema、verdict 口径、复跑方法、限制；`version_history.md` 版本对比 |
| 可靠体验：调用与易用性 3 分 | 用户/Agent 可按说明完成“给论文、出字段表”流程 | `SKILL.md` 命令清晰；`references/example.md` 端到端示例（合成数据） |
| 可靠体验：运行稳定性 4 分 | 不同论文、版式、重复运行下一致；长文多表跑完 | 脚本标准库、无网络、固定路径；`run.log` 展示真实执行；`self_check` 包含重复运行一致性 |
| 可靠体验：异常处理 3 分 | 扫描件、跨页表格、单位缺失、未报告、冲突、权限不足识别与处置 | §6 降级表；`degradations` 与 `pending_human` 记录；非零退出码不被接受，恒 0 |
| 生态贡献：文档完整性 3 分 | 字段词典、口径、证据规则、依赖、配置、示例、限制、维护信息齐全 | `references/field_dictionary.md`、`verification_assets.md`、`version_history.md`、`example.md` 均存在且被引用 |
| 生态贡献：资源可复用性 4 分 | Skill、脚本、字段表模板、证据定位规则、题集与参考答案可复跑迁移 | `scripts/main.py`/`build.py`/`audit.py` 可直接运行；`references/verification_assets.md` 给出复跑命令；字段表只需替换 `target-fields.json` |
| 生态贡献：分享推广价值 3 分 | 沉淀案例、字段规范、Benchmark 和经验 | `references/version_history.md` 记录迭代；`golden_standard.json` 可作为自建基准；`diff_report.md` 展示对照 |

## 14. 完整性与自检清单（提交前逐项检查）

1. `/app/output/result.json` 存在且为合法 JSON；含原 `output_contract` 全部字段 + `case_id`/`status`/`sources`/`uncertainty`/`pending_human`/`errors`/`degradations`/`changes`/`runtime`。
2. `counts.target_fields` = 字段表条数，四个状态之和等于它。
3. 每个 `reported` 有 `value`、`quote`、`paragraph_id`，且 `counts.quote_failed = 0`。
4. 每个非 `reported` 有可读依据且确实查过对应关键词。
5. 冲突字段双方 quote 都能查到；`extraction.csv` 行数 = 字段数。
6. `self_check.json` 的 `summary.failed = 0`；有失败项就在 `uncertainties` 写明是哪一条、为什么。
7. `diff_report.md` 里没有 `gap`；`deviation` 必须返工，`needs_review` 写进 `pending_human`。
8. `run.log` 只含真实执行过的步骤（不许补写未跑的步骤），退出码列全为 0。
9. 磁盘文件与 `result.json` 键一一对应：`extraction.csv`、`result.json`、`golden_standard.json`、`diff_report.md`、`version_history.md`、`run.log`、`self_check.json` 均存在；缺失任何一项立即补齐。
10. 若 `status=partial`，`result.json` 中列出 `missing` 字段或未完成项；若 `status=input_error`，说明原因与可人工接管位置。
11. 所有可编辑 Office/幻灯片/图形产物（若题目要求）均额外输出真实渲染 PDF/PNG 预览。
12. 不编造数据、引用、分数；不确定项写入 `pending_human` 或 `limitations`。

## 15. 最小示例（示例，非正式案例结果）

```bash
python3 -B $S/main.py init          # materials=1 target_fields=2 | M1 paper.pdf pdf paras=2
python3 -B $S/main.py show --para M1-p0001
# M1-p0001 [M1 p1] Results: compound A inhibited the kinase with an IC50 of 12.4 nM.
python3 -B $S/main.py check         # => PASS
python3 -B $S/main.py build         # fields=2 reported=1 not_reported=1 -> /app/output/result.json
python3 -B $S/main.py audit         # 重算五个可核验资产
```

最终 `result.json` 形如（仅示意，非实际结果）：

```json
{
  "case_id": "EXAMPLE-NOT-A-TEST-CASE",
  "status": "answered",
  "result": {"fields": [...]},
  "claims": [...],
  "uncertainties": [],
  "sources": [...],
  "uncertainty": null,
  "pending_human": [],
  "errors": [],
  "degradations": [],
  "changes": ["baseline_build", "agent_reviewed"],
  "runtime": {"requests_used": 12, "seconds": 180},
  "reviewed_by_agent": true
}
```

## 16. 五个可核验资产（`build`/`audit` 自动产出）

`build` 在 `/app/output` 与 `extraction.*` 并列写出下列文件；详细 schema 与判定口径见 `references/verification_assets.md`，`result.json` 同时用 `golden_standard`/`diff_report`/`version_history`/`self_check` 四个字段回填摘要（原 `output_contract` 字段一个不减）。

| 资产 | 内容 | 关键点 |
|---|---|---|
| `golden_standard.json` | 逐字段期望：`expected_status`、`expected{value,unit,statistic,condition}`、`evidence{locator,quote}` 或 `search_ledger`、`basis`、`confidence`、`verdict` | **自建基准**：字段表义务 + 对同一批材料的独立词面重扫；`is_organizer_key: false`，不得当成组织方隐藏答案 |
| `diff_report.md` | 逐项对照表 + 明细 + 汇总 + 复跑命令 | verdict 只有 `match/deviation/gap/needs_review`；达标率 = match/字段数 |
| `version_history.md` | 复制 `references/version_history.md` 并追加本次运行段 | 改了什么、为什么、如何回退 |
| `run.log` | 步骤表（at/step/exit/ms/argv）、降级、异常、产物字节 | 事件来自真实执行；每次命令后由 `main.py` 重写，含当前命令退出码 |
| `self_check.json` | 17 项自检（契约键、行键、四状态计数、证据覆盖率、数字一致性、locator 粒度、golden 一致性、diff 覆盖、空/坏输入实测、退出码、包预算） | 自检**真跑**空输入与坏