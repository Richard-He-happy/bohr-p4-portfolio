---
name: sciviz-figure-forge
description: 把一份科研数据表做成可直接用于投稿或正式报告的图件：清洗记录 + 图表选型理由 + 编码映射 + 统计标注与图注 + 发表级矢量导出 + 图元与原数据逐项一致性校验。输入 /input/case.json 与数据材料，输出 /app/output 下的 result.json、cleaned.csv、stats.json、tables/、figures/、quality_report.json、analysis.md。当用户要求「画图/可视化/出图/figures/plots/图表规范/期刊导出」并提供了数据或数据路径时使用。
version: 1.0.0
---

# sciviz-figure-forge（科研数据可视化）

## 1. 用途与边界

（骨架，正文在构建过程中补全）

## 2. 调用方式

```bash
python3 scripts/viz_skill.py --help
python3 scripts/viz_skill.py --input /input --output /app/output
```

## 3. 输出

`result.json` / `cleaned.csv` / `stats.json` / `tables/*.csv` / `figures/*` / `quality_report.json` / `analysis.md` / `run.log`
