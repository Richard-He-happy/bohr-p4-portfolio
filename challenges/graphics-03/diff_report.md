# 实际产物 vs 金标准：逐项对照

case_id `SYN-DEMO-3NODE` · 生成 2026-11-13T16:56:06Z · 金标准 3 实体/2 关系/9 规则（证据 19 条，未回查 0）· 图面 区室3/实体3/关系2
判定：达标=存在且类型方向一致；偏差=kind/type/图例/区室顺序不符（方向反转点名）；缺失=金标准要而图面无；金标准外=图面多画；达标(部分)=仅核存在性。

## 1 汇总

| 项目 | 计数 |
|---|---|
| 金标准 实体/关系 | 3 / 2 |
| 实体 达标/缺失/kind偏差/仅存在性 | 3 / 0 / 0 / 0 |
| 关系 达标/缺失/type偏差/方向反转/金标准外 | 2 / 0 / 0 / 0 / 0 |
| 图面多画实体 | 0 |
| 图例 缺项/多项 | 0 / 0 |
| 布局规则 通过/未通过 | 2 / 0 |
| 金标准覆盖率 | 100.0%（5/5） |
| 总体判定 | **达标** |

## 2 实体逐项

| # | 金标准项 | 期望 | 判定 | 说明 | 证据locator |
|---|---|---|---|---|---|
| 1 | EGF | ligand | 达标 | id=EGF | case.json@case.json#organizer_workorder.required_elements[0] |
| 2 | EGFR | protein | 达标 | id=EGFR | case.json@case.json#organizer_workorder.required_elements[1] |
| 3 | ERK | protein | 达标 | id=ERK | case.json@case.json#organizer_workorder.required_elements[2] |

## 3 关系逐项（方向敏感）

| # | 金标准项 | 期望 | 判定 | 说明 | 证据locator |
|---|---|---|---|---|---|
| 1 | EGF -> EGFR | binding | 达标 | rel r1 type=binding | case.json@case.json#organizer_workorder.required_relations[0] |
| 2 | EGFR -> ERK | activation | 达标 | rel r2 type=activation | case.json@case.json#organizer_workorder.required_relations[1] |

## 4 图例与布局

| 类别 | 项 | 判定 | 说明 |
|---|---|---|---|
| 图例 | activation | 达标 | 图例与图面一致 |
| 图例 | binding | 达标 | 图例与图面一致 |
| 区室顺序 | Extracellular>Plasma membrane | 达标 | 上游在上 |
| 区室顺序 | Plasma membrane>Cytoplasm | 达标 | 上游在上 |

## 5 未达标项与人工动作

- 无：全部金标准项达标。

## 6 复核与局限

重跑 `python3 -B scripts/main.py build --input /input --output /app/output --work /app/work` 除首行时间戳外确定性复现；`len(content_map.entities)` 须等于 `figure.svg` 中 `id="ent-*"` 个数。
只对照有逐字证据的项目；「达标」只表示与可回查原文一致，不等于机制结论正确。
