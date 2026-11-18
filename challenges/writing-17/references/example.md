# 端到端示例（示例，非正式案例结果）

下面的输入与输出均为**人工构造的接口示例**，用于说明字段与调用方式，不代表任何官方测试案例，也不是预生成答案。

## 1. 示例输入

`/input/case.json`：

```json
{
  "case_id": "EXAMPLE-ONLY",
  "task_instruction": "把材料整理成一张要点思维导图，节点需可回溯来源。",
  "output_contract": {
    "deliverable": "可编辑的思维导图",
    "evidence_map": "关键节点到来源定位的映射",
    "change_log": "修改动作与人工确认项"
  }
}
```

`/input/material.md`（虚构材料，仅用于演示）：

```
# 光催化产氢的稳定性问题

## 研究问题
在连续 24 h 光照下,催化剂的产氢速率是否保持稳定,以及失活的主要原因是什么。

## 方法
采用 300 W 氙灯,光强 100 mW/cm2,每 4 h 取样一次的间歇式反应器。
以 5% 负载量的样品为主体系,并设置无牺牲剂的对照。

## 结果
前 12 h 产氢速率稳定在 1.2 mmol/g/h,之后下降约 35%。
XPS 显示反应后表面金属态比例下降。

## 结论
失活主要来自表面活性位点的氧化,可通过二次还原部分恢复活性。
```

## 2. 调用

```bash
python3 scripts/main.py init
python3 scripts/main.py show --material M1 --limit 6
# Agent 读材料并写 /app/work/mindmap.json
python3 scripts/main.py check
python3 scripts/main.py build
```

## 3. 示例工作稿（Agent 手写）

```json
{
  "theme": {"label": "光催化产氢催化剂的稳定性"},
  "nodes": [
    {"id": "q", "label": "研究问题", "parent": "root", "role": "question",
     "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶3",
                   "quote": "在连续 24 h 光照下,催化剂的产氢速率是否保持稳定,以及失活的主要原因是什么。"}]},
    {"id": "q1", "label": "24 h 内是否稳定", "parent": "q", "role": "question", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶3", "quote": "产氢速率是否保持稳定"}]},
    {"id": "q2", "label": "失活原因", "parent": "q", "role": "gap", "status": "summary",
     "evidence": [{"material": "M1", "locator": "¶3", "quote": "失活的主要原因是什么"}]},
    {"id": "m", "label": "方法与条件", "parent": "root", "role": "method", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶6", "quote": "采用 300 W 氙灯,光强 100 mW/cm2"}]},
    {"id": "m1", "label": "300 W 氙灯 / 100 mW·cm⁻²", "parent": "m", "role": "method", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶6", "quote": "光强 100 mW/cm2"}]},
    {"id": "m2", "label": "5% 负载量主体系", "parent": "m", "role": "method", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶7", "quote": "以 5% 负载量的样品为主体系"}]},
    {"id": "r", "label": "结果", "parent": "root", "role": "finding", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶10", "quote": "前 12 h 产氢速率稳定在 1.2 mmol/g/h"}]},
    {"id": "r1", "label": "前 12 h 稳定 1.2 mmol/g/h", "parent": "r", "role": "finding", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶10", "quote": "前 12 h 产氢速率稳定在 1.2 mmol/g/h"}]},
    {"id": "r2", "label": "12 h 后下降 35%", "parent": "r", "role": "finding", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶10", "quote": "之后下降约 35%"}]},
    {"id": "c", "label": "结论", "parent": "root", "role": "conclusion", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶13", "quote": "失活主要来自表面活性位点的氧化"}]},
    {"id": "c1", "label": "表面活性位点氧化致失活", "parent": "c", "role": "conclusion", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶13", "quote": "失活主要来自表面活性位点的氧化"}]},
    {"id": "c2", "label": "二次还原可部分恢复", "parent": "c", "role": "conclusion", "status": "fact",
     "evidence": [{"material": "M1", "locator": "¶13", "quote": "可通过二次还原部分恢复活性"}]}
  ],
  "edges": [
    {"from": "r2", "to": "c1", "type": "support", "label": "XPS 佐证",
     "evidence": [{"material": "M1", "locator": "¶11", "quote": "XPS 显示反应后表面金属态比例下降"}]}
  ]
}
```

> 说明：示例中 `¶n` 的 n 按空行分段编号，实际以 `init/show` 打印的 locator 为准。

## 4. 示例输出（`build` 后）

```
== build | status=ok mode=agent nodes=12 edges=1 evidence=13 depth=3
  mindmap.svg          18432 B
  mindmap.json          6150 B
  content_map.json      5930 B
  mindmap.png         118220 B
```

- `mindmap.svg`：12 个 `<g id="node-…">`，每条 `<path id="edge-h-…">` 为父子连线，`support` 关系为虚线箭头；
  所有文字在 `<text>/<tspan>` 中，可直接用编辑器改字。
- `result.json`：`deliverable` 写"12 节点 / 1 跨分支关系 / 13 条逐字证据；主题「光催化产氢催化剂的稳定性」"，
  `evidence_map` 列出每条 quote + locator + `verified`，`status=ok`。

## 5. 兜底行为示例

若 `build` 时 `/app/work/mindmap.json` 不存在：脚本为每份材料建一个分支、取首/中/末段作叶子，
`status=partial`，`degradations` 写"工作稿缺失或为空：按材料确定性兜底生成最小完整导图"，
`pending_human` 提示复核。产物结构与正常流程完全一致，可直接打开继续改。
