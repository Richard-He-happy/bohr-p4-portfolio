# SELFTEST — 提交前自检清单

- [ ] `python3 scripts/main.py run --input /input --output /app/output --work /app/work` 退出码 0
- [ ] `/app/output/result.json` 存在且合法；`output_contract` 全部字段（含 case_id）在顶层与 nested 双回显
- [ ] 交付物文件齐全（与 SKILL.md 列出的产物清单一致）
- [ ] 关键数字/论断带 `[S#]` 来源与 `文件#行号` locator；未命中项写入 gaps/pending_human
- [ ] 材料缺失/异常输入时仍 exit 0 并诚实标注 status
- [ ] 无网络依赖；纯标准库；python3>=3.8
