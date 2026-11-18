# 版本记录（v0 骨架 → v1 成稿 → v2 增补）

## v0 骨架（仅记录，无可运行包）
单脚本 + 说明：能读材料、能出 SVG，但无逐字引文校验、无 content_map、无区室语义。
`baseline_minimal.zip` 与 `baseline_v1.zip` 内容一致（md5 `c662b963766ef056b63799a363d094ea`），
故 v0 只记录于此；本次基线 = v1（69.67）。

## v1 成稿（= 提交基线包）
`init/show/check/build` 四步；`plan.json` 由 Agent 写、脚本只校验与渲染；quote 逐字回查
（rejected/declared/verified 分开计数）；区室横带布局；分层 SVG 与单页矢量 PDF 同遍生成；
`content_map.json` + `compliance_checks.json`；异常全捕获、退出码恒 0、先写 partial result.json。
为什么：生物学判断留在 Agent，可复核性交给确定性脚本。
回退：`unzip baseline_v1.zip -d /tmp/v1` 覆盖 `SKILL.md`、`scripts/*.py`、`references/*.md`。

## v2（本次，纯增补）
`build` 在原有产物之外生成 5 个可核验资产（golden_standard.json / diff_report.md / version_history.md /
self_check.json / run.log）；`result.json` 增加同名 4 字段，原 `output_contract` 字段全部保留；
新增可选子命令 `selftest`、可选参数 `--no-probe`。
为什么：rubric 的「可核验性/完整性/生态贡献」需要能被独立重算的中间件，而非自述。
不变：入口与调用方式、纯标准库、离线、不依赖 CWD、退出码恒 0、先写 partial、原主产物与证据字段。
回退（v2→v1）：删掉新增 5 个资产即可；v1 不读它们，4 个新字段为增量字段。

## 运行时记录（本次 build 追加）

- 生成 2026-11-13T16:56:06Z　case_id `SYN-DEMO-3NODE`　status `ok`
- 金标准 3 实体 / 2 关系 / 9 规则项；对照 达标（偏差 0，缺失 0，覆盖率 100.0%）
- 图面修改：无（plan.json 未声明 edits；图为一次性生成，未做源内编辑）
- 降级：no PNG preview (stdlib renderer); figure.pdf supplied for inspection

回退本次运行：重跑 build 覆盖产物；本文只记真实发生的事。
