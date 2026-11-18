# Rubric → 产物对照 + 失败分支速查

## 1. 评分维度对照（题面 rubric）

| 维度（分值） | 交付物中的证据 | 自检动作 |
|-|-|-|
| 任务完成度 15 | 4 个 panel（problem/method/results/implication）+ `graphical_abstract.svg` + `graphical_abstract.pdf` | `check` PASS；打开 PDF 确认单页 |
| 结果正确性 15 | `content_map[].evidence.quote` 与原文逐字一致；关系方向写在 `flow`/`detail` | `check` 无 `unverified`；数字全部在引文中 |
| 结果完整性 5 | 图例（`legend` 或角色图例）、单位、条件词、`caption`；缺口在 `pending_human` | 手工扫一遍四个 panel 是否都能读懂 |
| 可核验性 5 | `sources[].sha1`、`changes`、`runtime`、`compliance_checks` | 任取 1 个图元，用 `show --grep` 30 秒内复现其 quote |
| 使用增益 25 | 一次 init→plan→check→build 出稿；改图只改 `plan.json` 重跑 | 连续两次 build，SVG 结构一致（确定性网格） |
| 创新增益 15 | 引文校验 + 数字校验 + 确定性版式 + content_map 几何 | 说明「为什么不是随便画一张图」 |
| 可靠体验 10 | 恒 0 退出码、先写 partial、单材料失败只降级该材料 | 空输入 / 坏 JSON 各跑一次 |
| 生态贡献 10 | `plan.json` schema、图层命名、导出参数、本目录两份说明 | 换一份材料能否直接复用 |

## 2. 常用调用

```bash
python3 scripts/main.py init  --input /input --work /app/work --output /app/output
python3 scripts/main.py show  --work /app/work --grep "2.4-fold"
python3 scripts/main.py show  --work /app/work --sid m2 --limit 10
python3 scripts/main.py check --work /app/work          # 只校验，不渲染
python3 scripts/main.py build --input /input --work /app/work --output /app/output
```

全部子命令支持 `--input/--work/--output`；`-h` 可查参数。退出码恒 0，看 `[build] status=` 与 `result.json`。

## 3. 失败分支 → 处置

| check/运行现象 | 原因 | 处置 |
|-|-|-|
| `E3: unverified - quote not found verbatim` | 改写原文 / 跨段拼接 / 抄摘要 | `show --grep` 取回原句整段引用 |
| `E3: number(s) ['145'] not in its quote` | 图元里有数字但引文没有 | 换成含该数字的句子（如数据行），或删掉数字 |
| `E3: relocated` | 句子对、locator 写错 | 无需处理，`content_map` 已用改正后的 locator |
| `missing panel role: implication` | 少了结论段 | 补 panel；结论文本必须来自原文（"suggest/indicate" 照抄语气） |
| `no items` | panel 为空 | 每 panel 至少 1 个带 evidence 的 item |
| build 报 `PNG preview unavailable` | 无 matplotlib/pdftoppm | 正常交付 SVG+PDF；在回复里说明 |
| `[init] ... [PDF text not extracted]` | 无 pdftotext | 自己读 PDF 页面，`locator` 写页码，quote 逐字 |
| `status=insufficient_evidence` | 材料没有可引用句子 | 明确说缺什么，不要补造 |

## 4. 交付前 60 秒自检

1. `check` → `PASS`，`coverage ≥ 0.9`。
2. `result.json`：contract 键齐全、`status` 如实、`errors/degradations` 已解释。
3. SVG 文字可编辑（`<text>`）+ 6 图层；PDF 单页、文字可选中。
4. 抽 2 条 `content_map` quote，用 `show --grep` 复现。
5. 图里没有材料外的实体名/数值/单位。
