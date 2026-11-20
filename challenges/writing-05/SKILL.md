---
name: evidence-driven-writing
description: 文献证据驱动写作。把写作任务拆成“论断清单 → 证据表 → 证据支撑成稿”三段可复核产物；每条实质论断必须落到具体材料段落、逐字原文与定位，并给出四因子证据强度和不确定性改写；冲突、缺口、缺失材料显式登记。Agent 路径与确定性兜底共享同一套产物与 result.json 契约。脚本只是本地抽取、校验与自检工具，最终事实判断必须回到真实输入材料。适用于学术段落写作、补引用、论断核验、证据强度评估、不确定性改写和引用一致性检查。
version: 4.0.0
license: MIT
---

# 文献证据驱动写作

## 0. 最高优先级：单命令完整流程

进入任务后，优先执行：

    python3 scripts/main.py run --input /input --output /app/output --work /app/work

该命令内部完成：

1. `init`：盘点输入、确认 `case_id` 与 `output_contract`、解析材料、分配来源编号 `S#`、抽取候选论断、构建冲突分组。
2. `build`：校验证据、执行确定性兜底抽取、渲染全部交付物、生成/更新 `result.json`。
3. `selfcheck`：检查产物与契约字段、证据覆盖率、quote 命中、locator 有效性、`result.json` 合法性与诚实状态。

**即使发生异常也必须 exit 0**；异常写入 `result.json.errors` 与 `degradations`，已完成的合法 partial 必须保留。

若已写好 `${WORK}/draft.json`，`run` 命令必须优先采用 Agent 判断；若不存在或不可用，`run` 必须使用确定性兜底抽取生成实质工作稿，并在 `degradations` 中记录 `AUTO_EXTRACT`。

兼容入口：

    python3 -B scripts/main.py --input /input --output /app/output
    python3 -B scripts/verify.py --input /input --output /app/output
    python3 -B scripts/gold.py   --input /input --output /app/output

`main.py` 是基线与最终产物生成入口；`verify.py` 生成独立复核；`gold.py` 仅用于本地自查证据，不替代平台评分。

---

## 1. 本题评分内核：四类要求必须同时成立

| 要求 | 本 Skill 的硬性落法 |
|---|---|
| 找得到 | 每个实质性论断拆成 `claim_id`，关联到 `source_id`，并给 `locator`：相对文件路径 + 块/段位置 + 句位置 + 可选页/段号 + chars 偏移。禁止只写“有引用”。 |
| 对得上 | `quote` 必须从解析后的真实材料逐字复制；元数据只转录，不补造 DOI、作者、年份、期刊；不确定项写入 `pending_human`。 |
| 说得准 | 证据强度用四因子：研究设计、样本量/重复验证、共识程度、直接性；正文语气必须与该强度相称。相关性不写成因果；冲突证据必须出现在 `conflicts` 与成稿中。 |
| 复得现 | 论断清单、证据表、成稿之间用 `claim_id` / `source_id` 可 join；`verify.py` 独立重读材料复算；计数写入 `metrics`。 |

**硬边界**：不联网、不从记忆补文献、不补造数值/DOI/结论、不把相关写成因果、不把模型记忆写成来源、不把脚本相似度当作证据、不伪造渲染文件或预览。材料没有的内容进入 `pending_human` 或 `gaps`，不得构造。

---

## 2. 触发与适用边界

触发：用户要求“为这段文字补引用 / 核对论断 / 评估证据强度 / 改写过度推断段落 / 按证据强度重写讨论段 / 做文献证据表”；或输入目录含 `case.json`、`task.md` 与材料。

适用：学术段落、综述、讨论段、摘要、结论的文献证据核对与改写；尤其适合需要把“看似有引用”升级为“论断—证据—原文定位”的写作任务。

不适用：凭空生成研究问题、伪造文献、无需来源的创意写作、以及只能依赖模型记忆的外部知识问答。

---

## 3. 输入输出契约

输入：

- `/input/case.json`：含 `case_id`、`task_instruction`、`output_contract`、`source` 等。
- `/input/task.md`：任务说明、体裁、受众、格式、边界。
- `/input/**`：PDF、DOCX、CSV、MD、JSON、TXT、图片等真实材料。PDF 应读取实际 PDF，不得依赖预先抽取好的答案层。

输出：

- `/app/output`：最终结果与全部产物。
- `/app/work`：中间台账、草稿、解析文本、临时计数。

`result.json` 必须满足双回显：

- 契约字段在顶层各出现一次。
- 同时完整嵌套在 `output_contract` 中。
- `case_id` 在顶层与 `output_contract.case_id` 各出现一次。

顶层至少包含：

    case_id
    status
    sources
    uncertainty
    pending_human
    errors
    degradations
    changes
    runtime
    output_contract

其余 `output_contract` 中出现的键，也必须在顶层同名回显。未知字段原样保留，不删除、不重命名、不假设语义。

`status` 只能取：

- `ok`
- `partial`
- `insufficient_evidence`
- `input_error`

必须与缺口、失败和人工确认项一一对应，不美化。

---

## 4. 交付物完整清单

每个案例至少应形成“三段式”可复核产物：

1. **论断清单**：`claims.json`
   - `claim_id`、`statement`、`type`、`source_ids`、`quote`、`locator`、`strength`、`support_scope`、`uncertainty`、`action`。
   - 论断必须来自任务稿或材料可明确支持的句子；每条论断控制在可判定范围内。

2. **证据表**：`evidence_table.json`
   - `source_id`、`file`、`locator`、`quote`、`support_scope`、`strength`、`supports_claims`、`conflicts_claims`、`notes`。
   - 一行证据可支撑多条论断；一条论断可引用多行证据。

3. **证据支撑成稿**：`deliverable.md` 或题面指定的可编辑交付物
   - 每句实质性论断标注 `[C#][S#]`。
   - 关键数字、术语、结论后的方括号内给出对应 `evidence_table.json` 中的来源与定位。
   - 语气与证据强度相称；冲突和缺口显式写出，不隐藏。

同时生成：

- `preserved_facts.json` / `preserved_facts.md`：记录不可凭空改变的数字、条件、术语、来源。
- `change_log.json` / `change_log.md`：修改动作、原因、人工确认项、未解决问题。
- `evidence_driven_draft.md`：带 `[C#][S#]` 标记的核验草稿；若与 `deliverable.md` 同时存在，两者不能相同。
- `agent_review.json`：Agent 或规则核验记录，逐条列出核验结果与理由。
- `verification.json`：`verify.py` 真实输出，不手改。
- `self_check.json`：产物与契约自检结果。
- `run.log`：时间戳日志。
- 若任务要求 Office / 幻灯片 / 图形产物，例如 `.docx`、`.pptx`、`.xlsx`，必须额外生成真实 PDF/PNG 预览；若无法渲染，在 `result.json` 标注 `preview_unavailable`，写入 `limitations`。

---

## 5. Agent-first 双路径

### 5.1 Agent 路径

优先按下列顺序：

1. 阅读 `/input/case.json`、`/input/task.md`、全部材料。
2. 基于 `init` 台账和真实材料判断，写 `/app/work/draft.json`。
3. 执行：

       python3 scripts/main.py run --input /input --output /app/output --work /app/work

`run` 检测到有效 `draft.json` 后，必须采用其中 Agent 判断进行 `build`，不得用规则覆盖 Agent 已确认的证据匹配。

`draft.json` 最小形状：

    {
      "case_id": "...",
      "claims": [
        {
          "claim_id": "C01",
          "statement": "...",
          "source_ids": ["S1"],
          "locator": "materials/xxx.pdf [B2.S3] chars:120-150",
          "quote": "逐字原文",
          "strength": {
            "design": "RCT|cohort|case_series|review|expert_opinion|unclear",
            "sample_size_or_replication": "...",
            "consensus": "...",
            "directness": "...",
            "level": "high|moderate|low|very_low|unknown",
            "hedge": "..."
          },
          "support_scope": "supports|partial|insufficient|conflict",
          "uncertainty": "...",
          "action": "keep|add|revise|flag"
        }
      ],
      "conflicts": [
        {
          "conflict_id": "X01",
          "description": "...",
          "source_ids": ["S2", "S3"],
          "resolution_or_status": "unresolved|resolved_as|needs_human"
        }
      ],
      "pending_human": [
        {
          "item": "...",
          "reason": "..."
        }
      ],
      "changes": [
        {
          "target": "...",
          "action": "...",
          "reason": "..."
        }
      ]
    }

### 5.2 无 draft 时的确定性兜底

如果 `${WORK}/draft.json` 不存在、非法或为空：

- `build` 必须用 `init` 台账确定性抽取生成实质工作稿。
- 逐字 `quote` 必须来自解析文本；`locator` 必须来自解析块句。
- 所有兜底结论必须标记 `AUTO_EXTRACT`，写入 `result.json.degradations` 和 `gaps`。
- 兜底路径也必须产出与 Agent 路径相同的完整产品与同一份 `result.json` 契约。
- 不得因无 Agent 判断而输出空壳模板；宁可为 low/unknown 强度，也要给出可核验的证据表。

### 5.3 增量改进

若先跑了确定性兜底，之后 Agent 读材料后写出 `draft.json`，重新执行同一 `run` 命令即可改进。再次执行时必须：

- 保留已有有效产物。
- 仅覆盖被 Agent 核验改变的字段。
- 更新 `change_log` 与 `agent_review.json`。
- 重新运行 `selfcheck` 并最终 `result.json` 合法落盘。

---

## 6. 确定性抽取与核验规则

### 6.1 来源编号与定位

- 每个可用来源分配 `S1, S2, ...`。
- 文件内定位统一为：

      <相对路径> [B<块号>.<句号>] chars:<start>-<end>

- 若有页码或段落号，也写入 `locator` 附注，例如 `page:3 para:2`。
- 禁止仅凭文件名或领域标签猜测内容；一切事实以解析出的文本和题面说明为准。

### 6.2 quote 核验

- `quote` 必须逐字来自材料。
- 允许去除换行/连字符产生的排版噪声，但不得改写词句、不得省略关键限定词。
- `verify.py` 必须执行“规范化后 quote 是否在材料文本中命中”的检查；未命中项标记 `quote_unverified`，不得静默当作 verified。
- 若原文与摘要矛盾，记录冲突，成稿中显式提示摘要不可作为唯一依据。

### 6.3 证据强度

四因子：

1. `design`：RCT、meta-analysis、systematic review、cohort、case-control、case series、cross-sectional、in vitro、animal、expert opinion。
2. `sample_size_or_replication`：样本量、置信区间、重复验证情况。
3. `consensus`：单篇、多篇一致、指南推荐、争议。
4. `directness`：是否直接支撑该论断，是否为代理终点，人群是否一致。

强度分级与语气映射：

- `high`：可直接陈述，如“证据支持……”“试验显示……”。
- `moderate`：用“提示”“与……相关”“支持该可能性”。
- `low`：用“初步证据”“可能”“有限数据提示”。
- `very_low` / `unknown`：用“尚不能确定”“证据不足”“需要进一步研究”。

因果表达限制：

- 没有干预设计或明确时间—剂量—效应时，不得写因果动词。
- 相关、关联、观察性差异只能在观察设计下表达。
- 单篇小样本不得写“领域共识”。

### 6.4 冲突与不确定性

- 冲突证据必须进入 `conflicts`。
- 成稿中不得只保留对结论有利的证据；至少以一个 however / but / “另有证据显示”句显式披露冲突。
- 对“材料未说明”“证据不一致”“仅有摘要”“无全文”等必须进入 `pending_human` 或 `gaps`。
- 材料不足不得推断为“不存在”。

---

## 7. result.json 双回显模板

`result.json` 的合法最小形态示例：

    {
      "case_id": "CASE-EXAMPLE",
      "status": "partial",
      "deliverable": "output/deliverable.md",
      "preserved_facts": "output/preserved_facts.json",
      "evidence_map": "output/evidence_table.json",
      "change_log": "output/change_log.md",
      "sources": [
        {
          "source_id": "S1",
          "file": "input/material/article.pdf",
          "type": "pdf",
          "locator": "materials/article.pdf",
          "usable": true
        }
      ],
      "uncertainty": {
        "unresolved_conflicts": 1,
        "abstract_only_sources": [],
        "quote_unverified": [],
        "needs_human": [
          "是否存在撤稿版本需人工确认"
        ]
      },
      "pending_human": [],
      "errors": [],
      "degradations": [
        "AUTO_EXTRACT: no draft.json present"
      ],
      "changes": [
        {
          "target": "deliverable.md",
          "action": "added locator to all substantive claims",
          "reason": "traceability"
        }
      ],
      "runtime": {
        "command": "python3 scripts/main.py run --input /input --output /app/output --work /app/work",
        "exit_code": 0
      },
      "output_contract": {
        "case_id": "CASE-EXAMPLE",
        "deliverable": "output/deliverable.md",
        "preserved_facts": "output/preserved_facts.json",
        "evidence_map": "output/evidence_table.json",
        "change_log": "output/change_log.md"
      }
    }

以上为示例，实际字段以 `/input/case.json` 中的 `output_contract` 为准。未知字段不能丢弃。

---

## 8. 自检与复核

### 8.1 必须先跑自检

单命令 `run` 内的 `selfcheck` 必须至少检查：

- `output_contract` 每个字段是否有对应文件或 JSON 值。
- `claims.json` 与 `evidence_table.json` 是否可 join。
- 每个关键数字、术语、引用是否有 `[S#]` 与 locator。
- 每个 `quote` 是否来自材料。
- `result.json` 是否合法 JSON，并且 `case_id` 顶层与嵌套一致。
- 兜底路径是否记录 `AUTO_EXTRACT`。
- 不可判定的办公/图形预览是否诚实标记。

### 8.2 独立复核

完成主流程后，可继续执行：

    python3 -B scripts/verify.py --input /input --output /app/output
    python3 -B scripts/gold.py   --input /input --output /app/output

必须三者退出码 0。`verification.json` 与 `self_check.json` 是真实自检证据，不手改。

---

## 9. 可靠性、异常与隐藏案例鲁棒性

### 9.1 正常案例

- 给定草稿、文献材料、任务格式。
- 应产出完整三段式交付物，不做多余改写。
- 所有改写句都降低泛化级别，并补上可追溯来源。

### 9.2 边界案例

- 只有摘要、缺全文。
- 原文与摘要矛盾。
- 材料有多种文件格式或混合语言。
- 材料有参考文献表但正文无定位信息。
- 遇到这些情况：标记 `abstract_only` / `conflict` / `mixed_language`，强度最高不得高于 `moderate`，locator 注明可得范围。

### 9.3 异常案例

- PDF 扫描件无文本层。
- DOCX/PDF 损坏、编码错误。
- 空输入、缺 `case.json`。
- 权限不足或路径错误。

处理原则：

- 单文件失败不中断整体。
- 可读材料继续处理。
- 空输入或完全不可读时，写出 `status=input_error` 或 `partial` 的合法 result.json，并 exit 0。
- 需要 OCR 的扫描件进入 `pending_human`，不得伪造文本层。

---

## 10. 预算感知

官方预算：64 次模型请求，900 秒，单次响应 16384 tokens 含推理。

执行策略：

1. 优先落盘基线，确保 `result.json` 和核心产物存在。
2. 用最少请求完成完整契约。
3. 剩余预算用于逐条 Agent 核验与成稿改进。
4. 接近限制时立即 finalize，不追求完美，不丢已完成的 partial。
5. 每次运行都应在 `runtime` 中记录时间、命令、状态。

---

## 11. 禁止事项

- 禁止手改 `claims.json`、`evidence_table.json`、`result.json` 的结构字段。
- 禁止生成无依据的 `golden_standard` 或自制评分并以平台分数自居。
- 禁止用脚本模板/骨架直接当最终成稿。
- 禁止隐藏冲突证据或缺口。
- 禁止把 memorized reference 写入来源。
- 禁止用不可复现的方法生成 PDF/PNG 预览。
- 禁止依赖网络、固定 CWD、未声明的个人文件。
- 禁止把“无证据”写成“证明不存在”。

---

## 12. 文档与资源

本 Skill 的精确 schema、强度分级和字段口径见：

- `references/evidence_schema.md`
- `references/method_and_runbook.md`
- `references/lexicon_zh_en.txt`

执行时先读 `references/evidence_schema.md` 确认字段；执行边界与失败处理以 `references/method_and_runbook.md` 为准；中英文不确定性表达可查阅 `references/lexicon_zh_en.txt`。

若包内存在 `SELFTEST.md`、`environment/resources.yaml`、`references/guide.md`，应作为自检与资源声明证据；若不存在，则以 `/app/output/self_check.json` 和 `/app/output/verification.json` 作为实际自检证据，不得在 `result.json` 中声称未生成的文件存在。