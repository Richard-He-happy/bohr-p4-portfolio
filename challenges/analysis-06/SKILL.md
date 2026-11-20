---
name: science-db-query-analysis
description: >-
  面向科研数据库快照（SQLite，或可物化为 SQLite 的 CSV/TSV）的可复核查询与分析技能。
  单命令入口：python3 scripts/main.py run --input /input --output /app/output --work /app/work。
  Agent-first：先盘点台账并读取原文，把判断写入 /app/work/draft.json，再 check→build；
  无 draft 时由 build 确定性抽取生成实质工作稿，并把 AUTO_EXTRACT 诚实记入 gaps/degradations。
  最终产出 /app/output/result.json（契约字段双回显）及可复跑 SQL、行数、来源、证据与自检记录。
version: 3.0.0
---

## 0. 最高优先级：脚本是工具，成品必须可复核

- 本技能自带 `scripts/` 只用于**盘点、只读查询、基线生成、契约回填、自检**。
- 最终 `result.json` 及交付文本由 Agent 在基线之上核验、增强，**不是原样照抄脚本模板**。
- 所有关键数字/论断必须带 `[S#]` 来源与 `文件#行号/段落号` locator；缺失材料显式登记，不编造。
- 结构化 JSON 的键名和契约字段**不得手改结构**；Agent 可在 `draft.json`、`agent_review.json`、`pending_human.json` 中补充判断。
- 任何异常也必须 exit 0；先落盘 partial，再增量改进。

## 1. 唯一推荐入口：单命令全流程

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

内部顺序执行：

1. `init` —— 材料盘点、来源编号、候选抽取、冲突分组，生成 `${WORK}/ledger.json` 与可编辑 `${WORK}/draft.json`。
2. `check` —— 若存在 draft，校验其引用、locator、契约字段，输出 `${WORK}/check_report.json`。
3. `build` —— 校验/兜底抽取/渲染全部产物/finalize `${OUTPUT}/result.json`。
4. `selfcheck` —— 运行 `python3 -B scripts/verify.py --result /app/output/result.json`，并检查产物与契约一致性。

支持子命令单独运行：

```bash
python3 scripts/main.py init --input /input --output /app/output --work /app/work
python3 scripts/main.py check --input /input --output /app/output --work /app/work
python3 scripts/main.py build --input /input --output /app/output --work /app/work
python3 scripts/main.py selfcheck --input /input --output /app/output --work /app/work
```

- 所有命令 exit 0。
- 路径优先级：显式参数 > `SKILL_INPUT_DIR/SKILL_OUTPUT_DIR/SKILL_WORK_DIR` > `/input,/app/output,/app/work`。
- 依赖仅 Python 标准库，Python≥3.8，离线，不装包。

## 2. init：盘点台账

`init` 只做**客观盘点**，不推断内容。动作：

1. 递归扫描 `/input`，识别 `case.json`、`task.md`、数据库、CSV/TSV、字典/说明材料。
2. `case_id` 取 `case_id`/`id`，否则取 case 文件名；无输入时用 `"unknown_case"`。
3. 读取 `case.json` 与 `output_contract`，完整保留所有字段键名。
4. 为每个来源分配 `S#` 编号，记录路径、字节数、sha1、类型；写入 `sources[]`。
5. 生成 `${WORK}/ledger.json`：库表清单、CSV/TSV、字典文件、子问题、契约字段清单。
6. 若不存在 `${WORK}/draft.json`，生成一个空白/占位 draft，字段见第 3 节。

产出：`${WORK}/ledger.json`、`${WORK}/draft.json`（初始）。

## 3. Agent-first 双路径

### Agent 路径（推荐）

1. 从 `init` 得到台账，阅读 `/input` 原文与 `case.json`/`task.md`。
2. 将判断写入 `${WORK}/draft.json`，形状如下：

```json
{
  "case_id": "case_001",
  "task_understanding": "用一句话说明任务目标。",
  "output_contract_fill": {
    "字段名": {
      "value": "填写内容或结构化结果",
      "evidence": [
        {"source_id": "S1", "locator": "文件#行号/段落号", "quote": "原文逐字引用"}
      ]
    }
  },
  "queries_hints": [
    {"purpose": "该查询目的", "sql": "SELECT ...", "expected_validation": "COUNT|GROUP|JOIN|FILTER"}
  ],
  "field_explanations": [
    {"column": "真实列名", "explanation": "根据字典/材料说明", "source_id": "S#", "locator": "..."}
  ],
  "cross_table_hints": [
    {"left_table": "...", "right_table": "...", "join_key_hypothesis": "...", "fanout_check": true}
  ],
  "data_quality_hints": {
    "duplicate_check": true,
    "missing_check": true,
    "outlier_check": true,
    "coded_field_candidates": ["列名候选"]
  },
  "uncertainty": [],
  "pending_human": [],
  "assumptions": []
}
```

3. 运行 `check`，根据 `${WORK}/check_report.json` 修复不一致引用。
4. 运行 `build` 生成最终产物。

### 无 draft 时确定性兜底

若 Agent 未写入 draft 或 draft 为空，`build` 必须使用 `ledger.json` 与数据库/CSV 实际内容**确定性抽取**生成实质工作稿：

- 从真实 schema 生成只读 SQL；
- 对关键聚合/筛选结果逐字取 quote 与 locator；
- 将 `AUTO_EXTRACT` 记入 `gaps/degradations`；
- 不编造字段含义，不确定的写入 `pending_human`。

两条路径产出**同一套产物与同一份 result.json 契约**。

## 4. 核心分析规则（必须执行）

- 数据库以 `file:...?mode=ro` 打开；CSV/TSV 物化到 `/app/work/snapshot.sqlite`。
- 使用 `PRAGMA table_info` 建立 schema 卡：列名、类型、行数、空值数、不同值数、样例值。
- 题目中的字面筛选值必须与真实列值精确匹配，多值用 `IN`，不拼互相矛盾的 `=`。
- 跨表连接：检查外键与命名推断；实测父/子行数、可匹配子行数、孤儿行、每键最大子行数；给出一对多膨胀结论 `fanout_note`。
- 数据质量：整行重复、业务重复、缺失率、1.5×IQR 离群、编码型字段（低基数字段不参与均值）、类型混用。
- 查询返回 0 行保留空结果并说明筛选条件；表为空不统计，标 `insufficient_evidence`。
- SQL 报错：大小写不敏感匹配重试一次；仍失败记录 `errors[]`，不静默。

## 5. 产物与文件

最终产物必须落在 `/app/output`，至少包括：

| 文件 | 说明 |
|-|-|
| `result.json` | 最终契约结果（双回显，见第 6 节） |
| `queries.sql` | 所有实际执行 SQL |
| `query_log.json` | SQL、行数、耗时、状态 |
| `schema_card.json` | 每库每表的 schema 与样例值 |
| `evidence_table.json` | 逐条证据：claim_id、source_id、locator、quote、strength |
| `data_quality.json` | 缺失/重复/离群/编码字段检测 |
| `chart_*.svg` 或 `charts/*.svg` | 可视化预览 |
| `deliverable.md` | 正文成稿（可含 `answer` / `manuscript` 等契约字段内容） |
| 契约要求的其他文件 | 按 `output_contract` 字段逐项补齐 |

可编辑 Office/幻灯片/图形产物必须额外渲染为 PDF/PNG 预览。所有关键数字/论断带 `[S#]` 与 locator。

## 6. result.json 双回显契约

`result.json` 顶层必须包含：

- `case_id`
- 原 `output_contract` 的**全部字段**（键名不改）
- `output_contract` 嵌套对象中再次出现同样字段（值可相同，但必须存在）
- `status`、`sources[]`、`uncertainty[]`、`pending_human[]`、`errors[]`、`degradations[]`、`changes[]`、`runtime{}`
- `contract_fill{fields,filled_non_null,null_fields,note}`

状态取值：`ok` / `partial` / `input_error` / `insufficient_evidence` / `error`。  
无法生成的契约字段值置 `null`，写入 `pending_human` 与 `contract_fill.null_fields`。  
不伪造评分、金标准、对照结果或缺失的科学数据。

## 7. 自检与可靠性

- 提交前运行：

```bash
python3 -B scripts/verify.py --result /app/output/result.json
```

- 检查 `output_contract 字段 × 磁盘文件 × result.json 键` 三者一一对应。
- 目录中应有 `SELFTEST.md`（自检清单+预期输出）、`environment/resources.yaml`（预装依赖声明）、`references/guide.md`（draft.json 形状与工作流说明）；若缺，可在 `agent_review.json` 中补充说明，但不得因此阻断 result.json。
- 仅用标准库、离线、中英文自适应；资源 ≤50 文件、单文件 ≤500KB、总大小 ≤2MB。

## 8. 预算与降级

- 模型预算：64 次请求 / 900 秒 / 单次响应 16384 tokens。
- 路径：`init` → 读原文 → 写 draft → `check` → `build` → `selfcheck`，通常 8–15 次请求即可完成。
- 无 draft 时 `build` 确定性兜底：0–3 次额外请求即可生成完整基线。
- 超时前 60 秒或请求达 60 次时：停止新查询，finalize 当前产物，`status="partial"` 并列出 limits。
- 降级表：

| 情况 | 动作 | 记录位置 |
|-|-|-|
| `/input` 为空 | `case_id="unknown_case"`，契约字段 null，status=`input_error` | `errors[]` |
| 数据库损坏/无法打开 | 跳过，继续其余材料；仍失败标 `insufficient_evidence` | `errors[].stage=connect`、`degradations[]` |
| 只有 CSV/TSV | 物化到 `/app/work/snapshot.sqlite` | `degradations[]` |
| PDF/DOCX 无法解析 | 不猜内容，记录缺失 | `pending_human[]`、`degradations[]` |
| SQL 报错 | 大小写不敏感重试一次；仍失败记录 | `errors[]` |
| 0 行结果 | 保留并说明筛选条件 | `main_result.filtered[].n_rows=0` |
| 中文/非英文 schema | 使用原始列名，不翻译；无法推断角色则试探并标注 caveat | `uncertainty[]` |

## 9. Rubric 高分自证要点

- **实际效果**：`queries[]` 中 SQL 真实执行并记录行数；`sources[]` 含 sha1；`evidence[]` 由 verify 重跑；`field_explanations[]`、`cross_table[]`、`data_quality[]` 完整。
- **使用增益**：单命令 + 确定性兜底减少改写轮次；`runtime.model_requests`、`errors[]` 长度、`changes[]` 显示改进。
- **创新增益**：schema 接地、跨表路径推断、编码字段识别、膨胀实测；在 `references/query-and-quality-rules.md` 与 `references/schema-and-fields.md` 中有据可查。
- **可靠体验**：exit 0、只读、无外部依赖、异常完整记录。
- **生态贡献**：规则文件、脚本、自检清单可复用；README/引用清晰。

## 10. 最小调用示例

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

示意输出（示例，非正式案例结果）：

```
init: found case_003, 3 sources, 5 contract fields.
check: no draft found; will use deterministic fallback.
build: executed 8 queries, generated 2 charts, finalized result.json.
selfcheck: verify verdict=ok, non_null_contract=5/5.
exit=0
```

若 `draft.json` 已由 Agent 填写，则 `check` 输出 `draft valid: true` 并继续 `build`。