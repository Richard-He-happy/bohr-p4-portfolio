# references/guide.md — 工作流与 draft.json 形状

本 Skill 支持两条路径：
1. **确定性兜底路径**：`python3 scripts/main.py run --input /input --output /app/output --work /app/work`
   无 draft.json 也产出完整交付物与 result.json。
2. **Agent 增强路径**：先读原文 → 写 `${WORK}/draft.json` → 再 `check` → `build`。

## draft.json 建议形状
```json
{
  "language": "zh|en",
  "sections": [{"id": "S1", "title": "...", "claims": [{"text": "...", "sources": ["S1#L12"], "strength": "high|medium|low"}]}],
  "gaps": ["材料未报告的要素"],
  "decisions": [{"item": "...", "choice": "...", "reason": "..."}]
}
```
- 每个数字/论断必须带来源定位（文件#行号或段落号）；
- 缺失信息写入 gaps，不得编造；
- 两条路径必须产出同一套产物与同一份 result.json 契约（含顶层与 nested output_contract 双回显）。
