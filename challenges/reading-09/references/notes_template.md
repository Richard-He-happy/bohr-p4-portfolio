# 结构化阅读笔记 / Section-anchored reading notes

<!-- 本文件由 scripts/main.py 填充（占位符见下，未提供的替换为 "—"），改版式无需改脚本。
{{title}} {{case_id}} {{status}} {{skill}} {{version}} {{ts}} {{run_table}} {{card_table}}
{{section_map}} {{section_notes}} {{media}} {{gaps}} -->

> {{title}}
> case `{{case_id}}` · status `{{status}}` · {{skill}} v{{version}} · {{ts}}
> 每条笔记带 `claim_id · 页 · 章节 · 句序` 锚点；逐字 quote 与字符区间见 `claims.csv`，未报告项不写成事实。

## 0. 运行与来源 / Run and sources

{{run_table}}

## 1. 论文卡片 / Paper card

{{card_table}}

## 2. 章节地图 / Section map

{{section_map}}

## 3. 逐章笔记 / Section notes

{{section_notes}}

## 4. 图表 / Figures and tables

{{media}}

## 5. 缺口、不确定、待人工 / Gaps, uncertainty, pending human

{{gaps}}

## 6. 复用 / Reuse

- `result.json`：主结果 + `output_contract` 全字段回填 + `coverage`（含 page_map、命中率、计数）。
- `claims.csv`：一行一条证据（quote, source_id, page, section_id, sentence_index, char_start, char_end, anchor, readability, verified_quote_hit, conditions, numbers）。
- `verify_report.json`：本次运行的机器自检（quote 命中数、契约字段数、缺失字段、产物存在性）。
- 复核：重跑 `python3 scripts/main.py --input <in> --output <out>`（确定性，同一输入得到同一 claim_id 序列）。
- 边界：只记录原文可读内容；图表像素读数、扫描件文字、参考文献列表不纳入证据集，缺口记入 §5。
