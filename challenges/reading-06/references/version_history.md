# 版本记录（随包静态文件，运行时复制到 `/app/output/version_history.md` 并追加本次运行段）

只记录能核实的变更；无法核实的版本不补写。基线来源：`baseline_v1.zip`（5 文件，61405 B）。

## v0 — 骨架（**无法据实记录差异**）

- 本次材料中的 `baseline_minimal.zip` 与 `baseline_v1.zip` 内容完全相同
  （两者 sha256 均为 `22d81d135dcf861305b7deac561f4e7c819a428d3e30fa7d7b2464b722b8bef5`），
  因此无法从手中材料还原 v0 的独立内容，也不猜写它改过什么。
- 需要追溯 v0 时，以组织方留存的 `baseline_minimal.zip` 为准；本文件不回填。

## v1.0.0 — 成稿（v2 的起点，逐字沿用）

| 文件 | 字节 | 作用 |
|---|---|---|
| `SKILL.md` | 9981 | 用途、运行契约、字段 schema、四状态口径、异常降级 |
| `scripts/main.py` | 20449 | 输入发现、材料解析、段落索引、`init`/`show` |
| `scripts/build.py` | 20460 | `check`/`build`、四状态校验、契约回填、`extraction.*` |
| `references/field_dictionary.md` | 5555 | 字段词典、状态判据、locator 与 quote 规范、check 码表 |
| `references/example.md` | 4960 | 端到端合成示例（标注"非正式案例结果"） |

能力：`init` → `show` → 写 `draft.json` → `check` → `build`；四状态
（`reported`/`not_reported`/`source_conflict`/`extraction_failed`）+ 逐字 `quote` + `locator`；
`output_contract` 原样回填；未写草稿时 fallback 并降级为 `partial`；退出码恒 0。

v1 缺口（v2 要补的就是这几条）：

1. 产物只有 `extraction.json|csv|md` + `result.json`，**没有**"期望交付内容"的可核对基准。
2. 没有"实际产物 vs 期望"的逐项对照，评审只能自己比对。
3. 没有运行日志：步骤、耗时、降级、异常只散落在 `result.json` 的 `changes` 里。
4. 没有自检回执：契约字段完整性、证据覆盖率、数字一致性、空/坏输入兜底只是文档里的口头承诺。
5. 版本演进无记录，回退方式未写。

## v2.0.0 — 本次 patch（最小增补，不重写、不改原调用方式）

| # | 变更 | 为什么 | 回退方式 |
|---|---|---|---|
| 1 | 新增 `scripts/audit.py`（约 34 KB，纯标准库） | 生成 5 个可核验资产；与抽取主链路解耦 | 删该文件即回到 v1（build.py 里 import 失败会记 `audit_assets_skipped`，不崩溃） |
| 2 | `build.py`：`build` 末尾调用 `audit.emit()`，`result.json` 追加 4 个字段 + `audit_run` | 让 5 个资产随一次 `build` 自动产出 | 加 `--no-audit`，或删该调用块 |
| 3 | `main.py`：`--work/--output` 解析 + 每次命令后追加一条 run event 并重写 `run.log` | 日志必须来自真实执行，且要能记录当前命令的退出码 | 删 `main()` 包装，恢复 `_main` 直接作为入口 |
| 4 | `main.py`：新增可选子命令 `audit`（转发 `audit.py assets`） | 产物已存在时可只重算资产，不必重跑抽取 | 不调用即可；不影响原有四个子命令 |
| 5 | `main.py`：`V = "2.0.0"` | 版本与资产自述一致 | 改回 `"1.0.0"` |
| 6 | 新增 `references/verification_assets.md` | 说明 5 个资产的 schema、判定口径、复跑与迁移方式 | 删文件（`SKILL.md` §15 引用它，需同步删该节） |
| 7 | 新增 `references/version_history.md`（本文件） | 版本与回退可追溯 | 删文件；运行时自动退回内置精简版模板 |
| 8 | `SKILL.md`：frontmatter `version: 2.0.0`；§2 增 `audit` 命令；新增 §15 五资产；文件清单与自检清单同步 | 文档与提交版本一致 | 按 diff 逐节回退 |

**不变量（v2 未触碰）**：`init/show/check/build` 的调用方式与参数、`extraction.*` 的列与结构、
四状态判据、`quote` 三级校验、`output_contract` 回填逻辑、异常降级分支、退出码恒 0。

**产物差异**：`result.json` 从 13 个顶层键变为 18 个（新增 `golden_standard`、`diff_report`、
`version_history`、`self_check`、`audit_run`），原有 `output_contract` 键一个不少；
`/app/output` 新增 `golden_standard.json`、`diff_report.md`、`version_history.md`、
`self_check.json`、`run.log`。

**一键回退 v1**：

```bash
python3 -B scripts/main.py build --input /input --work /app/work --output /app/output --no-audit
# 或彻底回退：删除 scripts/audit.py，去掉 build.py 中的 audit 调用块与 main.py 的 audit 分支
```
