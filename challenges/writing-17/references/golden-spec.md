# 金标准 / 对照 / 自检：schema 与复用方法

本文件配合 `scripts/report.py`。目标是让"导图做得对不对"变成**可复核的对照**，而不是自述。

## 1. 五项资产与生成时机

| 资产 | `init` | `build` | 说明 |
|---|---|---|---|
| `golden_standard.json` | 骨架（含来源） | 覆盖为实测 | 期望清单，不依赖实际产物 |
| `diff_report.md` | 全部"待定" | 逐项判定 | 达标/偏差/缺失/待定 |
| `version_history.md` | 追加 v0 | 追加 v1 | 检查点与回退 |
| `run.log` | 起写 | 追加 | 耗时、降级、异常 |
| `self_check.json` | 起写 | 覆盖（含探针） | 10 项自检 + 探针实测 |

## 2. `golden_standard.json`

```json
{
  "schema": "mindmap-golden/1.0",
  "center_topic": {"expect": "...", "source": {"kind": "material", "material": "M1", "locator": "¶1",
                   "quote": "原文逐字片段", "verified": true}},
  "branches_expected": [{"id": "B01", "dimension": "method", "branch": "方法与材料", "expect": "...",
                         "source": {"kind": "material", "material": "M1", "locator": "¶6", "quote": "...", "verified": true}}],
  "structural_requirements": [{"id": "G01", "category": "中心主题", "expect": "...", "check": "theme_grounded",
                               "tolerance": "...", "source": {"kind": "skill_rule", "locator": "SKILL.md#L57",
                                                              "quote": "可逐字命中的规则句", "verified": true}}],
  "edge_semantics": [{"type": "cause", "direction": "因 → 果", "when": "材料明说 A 导致 B",
                      "source": {"kind": "skill_rule", "locator": "SKILL.md#L88", "quote": "| `cause` | 因 → 果 | ... |"}}],
  "contract_expectations": [{"id": "C01", "field": "deliverable",
                             "source": {"kind": "case_json", "locator": "case.json#/output_contract/deliverable",
                                        "quote": "\"可编辑的思维导图\"", "verified": true}}],
  "pending_policy": {"rule": "无 quote 支撑的关系不画，标注 pending"},
  "totals": {"structural": 13, "branch_anchors": 4, "contract_fields": 5}
}
```

`source.kind` 只有三种，且都必须可回溯：

1. `material` — 材料 locator + 逐字 quote（材料没有的维度**不写进**期待清单）。
2. `case_json` — `case.json#/output_contract/<key>` 的 JSON Pointer + 原值。
3. `skill_rule` — 本 Skill 文档规则句；运行时逐字回查，命中才 `verified:true`，未命中保留原句并标 `false`（防文档与代码脱节）。

## 3. `diff_report.md` 判定口径

| 结论 | 含义 | 处理 |
|---|---|---|
| 达标 | 实测符合期望 | — |
| 偏差 | 做了但不合要求（层级过深、分支越界、引用过短、数字对不上…） | 按第 3 节修正后 rebuild |
| 缺失 | 没做（无主题/节点/证据、契约字段空） | 补齐或标 `pending_human` |
| 待定 | 无法判定（`init` 阶段、材料无文本） | 报告给原因，不冒充结论 |

计数写入 `result.json.diff_report.verdict_counts`，可直接做回归对比。

## 4. `self_check.json`

`checks[]` 固定 10 项：C1 契约完整性、C2 证据覆盖率、C3 数字/引用一致性、C4 节点 15–40、C5 层级正确性、
C6 SVG 可解析且带 `data-quote`/`data-locator`、C7 空输入兜底、C8 坏 JSON 兜底、C9 退出码、C10 异常与降级记录。

C7/C8 是**真实子进程**：在临时目录里用 `BOHR_INPUT_DIR/WORK/OUTPUT` 指向空输入与坏 JSON，
跑一次 `main.py build`，记录 `exit_code`、`result.json` 是否合法、产物数量。跑不动或超时记 `pass:false`，
不写"应该没问题"。赶时间可 `--no-probe`，此时 `probes:[]` 并在 `summary` 里标注未探测。

## 5. 复用方法（换题型时改哪里）

| 想改的东西 | 改哪里 |
|---|---|
| 结构期望（分支数/节点数/深度） | `report.py` 的 `golden()` 里 `add(...)` + 同步 SKILL.md 规则句 |
| 维度词表（研究问题/方法/结果…） | `report.py` 的 `DIMS` |
| 边类型与方向 | `verify.py` 的 `EDGE_TYPES`/`REL` + SKILL.md §6 表（金标准自动读表） |
| 自检项 | `report.py` 的 `self_check()` |

换题型只需替换 `golden()` 与 `DIMS`，其余骨架原样复用——本包因此可被直接搬去做"实验方案图""会议纪要图"。

## 6. 已知限制

- 覆盖判定是确定性匹配（locator/role/关键词），人工认可的等价表述可能被判"缺失"（报告第 5 节已声明）。
- 材料无文本（纯图片 PDF）时金标准只剩规则类条目，`status=insufficient_evidence`。
- 金标准说"应有什么"，不替代"分支该不该合并"的判断——那仍由 Agent 写稿时决定。
