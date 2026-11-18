# 最小调用示例（示例，非正式案例结果）

> 本文件中的输入片段与输出数值均为**示意**，用于说明接口与流程，不是任何正式案例的结果，也不构成评测证据。

## 1. 最小输入

`demo_input/case.json`（示例）：

```json
{
  "case_id": "DEMO-01",
  "task_instruction": "依据所供论文写七要素基金申请章节草稿",
  "output_contract": {
    "case_id": "原样保留",
    "deliverable": "可编辑的目标文稿",
    "preserved_facts": "数字、条件、术语和来源不可凭空改变",
    "evidence_map": "关键论断到来源定位的映射",
    "change_log": "修改动作、原因、人工确认项和未解决问题"
  },
  "organizer_workorder": {
    "id": "DEMO-WO", "authority": "organizer-workorder-not-funder-policy",
    "source_basis": {"published_paper": "DEMO-PAPER", "external_authors": ["A. Author"],
                     "applicant_owned_preliminary_results_supplied": false,
                     "actual_funder_notice_supplied": false,
                     "resource_availability_evidence_supplied": false},
    "sections": [{"id": "background", "title": "立项依据", "minimum": "实质正文"},
                 {"id": "question", "title": "科学问题", "minimum": "实质正文"},
                 {"id": "goals", "title": "研究目标", "minimum": "实质正文"},
                 {"id": "content", "title": "研究内容", "minimum": "实质正文"},
                 {"id": "innovation", "title": "创新点", "minimum": "实质正文"},
                 {"id": "route", "title": "技术路线", "minimum": "实质正文"},
                 {"id": "foundation", "title": "研究基础与可行性", "minimum": "实质正文"}],
    "draft_size": "正文七节合计约1600–2600汉字",
    "planning_months": 12, "planning_unit_cap": 100,
    "planning_unit_meaning": "非货币规划单位",
    "consistency": "3个目标G1/G2/G3",
    "required_supporting_files": ["七要素可编辑正文"]
  }
}
```

`demo_input/paper.md`（示例材料）：任意含数值句的论文正文片段，例如
"Specimens were printed with a 0.4 mm nozzle at 210 ℃ and tested under three-point bending."

## 2. 调用

```bash
python3 -B scripts/skill_main.py init     --input demo_input --output demo_out
# 用文件写入工具改写 demo_out/proposal.md 及 evidence_map.json / planning_units.json /
# goal_matrix.md / risks.md / pending_human.json / draft_boundary.md
python3 -B scripts/skill_main.py finalize --input demo_input --output demo_out
python3 -B scripts/verify.py --output demo_out
```

`init` 即时输出（示意）：

```json
{"stage": "init", "case_id": "DEMO-01", "sources": 1,
 "sections": ["立项依据", "科学问题", "研究目标", "研究内容", "创新点", "技术路线", "研究基础与可行性"],
 "chars_range": [1600, 2600], "next": "编辑 proposal.md 后 finalize"}
```

## 3. 产出清单

| 文件 | 内容 |
|-|-|
| `proposal.md` | 七节正文（可编辑 Markdown） |
| `workorder.json` | workorder 原样留痕 |
| `quote_bank.md` | 逐字候选引文（含 locator）+ 执行约束 |
| `proposal_skeleton.md` | 骨架与每节字数预算 |
| `evidence_map.json` | 论断 → locator → 逐字 quote |
| `preserved_facts.json` | 数字/单位/条件/归属 |
| `change_log.json` | original_quote → revised_quote + reason + locator |
| `goal_matrix.md` | G × WP × 里程碑 × 指标 |
| `planning_units.json` | 分项 + 合计（≤cap，非货币） |
| `risks.md` | ≥3 风险 + 触发信号 + 备选 |
| `pending_human.json` | ≥2 人工确认（申请人证据、真实资助要求） |
| `draft_boundary.md` | 已完成（外部作者）/ 拟开展 双栏 |
| `result.json` | 契约回填 + 回执 + 审计 |

`finalize` 输出（示意，非正式案例结果）：

```json
{"stage": "final", "case_id": "DEMO-01", "status": "ok",
 "char_count": 2130, "planning_units_total": 96,
 "issues": {"critical": 0, "major": 0, "minor": 2}, "result": "demo_out/result.json"}
```

`result.json` 关键字段（示意）：

```json
{"case_id": "DEMO-01",
 "deliverable": {"file": "proposal.md", "char_count": 2130, "char_range": [1600, 2600]},
 "status": "ok",
 "workorder_execution": {"sections_satisfied": 7, "char_count_in_range": true,
   "goals_count": 3, "max_month_found": 12, "planning_units_total": 96,
   "planning_units_in_cap": true, "risks_count": 3, "pending_human_count": 2}}
```

## 4. 失败路径示例

| 输入 | 结果 |
|-|-|
| `/input` 空目录 | `status="partial"`，`errors[0].code="case_json_unreadable"`，仍生成骨架与合法 `result.json`，退出码 0 |
| `case.json` 坏 JSON | 同上，`degradations` 含 `case_json_unreadable` |
| 无 workorder | 默认七节/12 月/100 单位，`degradations` 含 `workorder_absent_defaults_applied` |
| 未写 proposal.md 就 finalize | 复制骨架为 `proposal.md` 并标 `proposal_absent_fallback_generated`，`status="partial"` |
| 引文在抽取文本中找不到 | 该条 `verified=false`，新增 `PHQ` 人工确认项 |
