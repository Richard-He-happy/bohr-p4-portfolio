# 可核验资产 schema 与复核步骤（v1.4.0）

`build`（或 `audit`）在 `/app/output` 生成 5 个可核验资产。它们**只描述本次运行实际读到的输入与实际写下的产物**，不含预制译文。

## 1. `golden_standard.json`

| 键 | 说明 |
|---|---|
| `case_id` / `target_lang` / `generated_at` | 运行标识 |
| `provenance` | 派生来源（`work/index.json` 段落 + `case.output_contract` + 给定/工作稿术语）、`source_index_sha1`、材料清单 |
| `expected_deliverables[]` | 6 个主产物及其用途 |
| `units[]` | 每个来源段一条：`req_id`(`U-<para_id>`)、`para_id`、`locator`、`kind`、`position`、`source_sha1`、逐字 `source_quote` |
| `glossary[]` | `req_id`(`G01`…)、`term`、`expected_target`、`status_expected`(`locked|pending_human`)、`origin`、`occurrences[]`（含逐字 quote） |
| `facts[]` | `kind`=`number|unit|citation`、`value`、逐字 `source_quote` |
| `evidence[]` | 每段一条证据要求：逐字 quote + locator + target |
| `meta_checks[]` | M01 契约完整性、M02 顺序、M03 状态诚实、M04 退出码、M05 partial-first |
| `totals` | 各类要求计数与 `all` |

quote 来源：段内整段（≤260 字符）或围绕目标 token 的窗口，均为索引文本的连续子串——因此可用 `quote in 原文` 机械校验。

## 2. `diff_report.md`

逐项状态四种：`ok`（达标）/ `missing`（产物缺该项）/ `deviated`（产物有但不符）/ `na`（本次不适用，如 build-only 运行的 M05）。`na` 不计入分母。
判定：`total>0 且 ok==total` → `pass`，否则 `review_needed`。M04（退出码）由 `self_check.json` 的真实子进程结果核验，不在 diff 表重复计分。

## 3. `version_history.md`

Skill 版本线（含回退方式）+ 产物 v0 骨架 → v1 成稿（段落/术语/事实/金标准对照/修改记录）+ 产物 sha256 + 运行日志节选。

## 4. `run.log`

`work/run.log` 逐事件追加，`build` 收尾时整理输出。每行：`UTC 时间戳 | 阶段 | 事件 | dur`。阶段 `init/show/check/build/audit/selfcheck`。异常以 `EXCEPTION` 开头。运行结束后由 `flush_log` 重渲染一次，确保「回读验证」行不丢。

## 5. `self_check.json`

| id | 判据 | 模式 |
|---|---|---|
| SC01 | `output_contract` 字段在 `result.json` 中齐全 | runtime |
| SC02 | 每段有非空译文且 locator 一致 | runtime |
| SC03 | 数字/单位逐字落地 | runtime |
| SC04 | 引用标记原样保留 | runtime |
| SC05 | 术语同一译名；无译名者 `pending_human` | runtime |
| SC06 | 证据 quote 为原文子串 | runtime |
| SC07 | 6 个主产物非空 | runtime |
| SC08 | 退出码 0（build + 两次子进程） | executed |
| SC09 | 空输入 → `insufficient_evidence` + 骨架 + 5 资产 | executed |
| SC10 | 坏 `case.json` → 捕获异常、仍产出 | executed |
| SC11 | diff 项守恒（ok+missing+deviated==total） | runtime |

`mode=executed` 的项由 `subprocess` 真实运行 `main.py` 得到（`work/selfcheck/{empty_input,bad_json}`，退出码与产物清单写入该条 `observed`）；嵌套运行以 `ATB_NO_SMOKE=1` 跳过自身自检，避免递归。

## 6. 人工复核路线

1. `diff_report.md` §7「待处置明细」逐条看：要吗改产物，要吗进 `result.json.pending_human` 说明原因。
2. `golden_standard.json` 与原文对读：确认 quote 确实是原文（脚本已机械校验，人工只看语义是否被曲解）。
3. `run.log` 看降级与异常：`EXCEPTION`、`degraded`、`selfcheck ... pass=False`。
4. `self_check.json.limits` 明确未覆盖维度：译文语域、否定范围与因果强度需人工判断，脚本不判定「译得好不好」。

## 7. 限制

- 数字/引用/术语核对是**字符级**判断：`12.5` 落地即视为通过，不判断该数字是否被放错段落语境。
- 术语一致性按 `kit.tfound` 容忍英文词形变化（前 6 字符前缀），不做语义消歧。
- PDF 文本层稀薄时 quote 来自脚本抽取结果，须对照页面复核。
- `na` 项说明该检查在本次运行不适用，不等于通过。
