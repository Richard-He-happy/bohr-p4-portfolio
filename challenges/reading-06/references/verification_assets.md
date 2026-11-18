# 五个可核验资产（v2.0.0）

`build` 结束时在 `/app/output/` 与 `extraction.*` 并列产出。它们回答的是评审最常追问的四句话：
**期望交付什么、实际交付了什么、差在哪、凭什么相信**。

| 资产 | 谁写 | 回答的问题 |
|---|---|---|
| `golden_standard.json` | `audit.py` | 每个 `field_id` 应该交出什么（状态/值/单位/条件/locator/quote） |
| `diff_report.md` | `audit.py` | 实际产物逐项对上了吗，差在哪一项、哪一段原文 |
| `version_history.md` | `audit.py`（复制本包 `references/version_history.md` + 追加本次运行段） | 改了什么、为什么、怎么回退 |
| `run.log` | `audit.py`（每次命令后由 `main.py` 重写） | 实际跑了哪些步骤、退出码、耗时、降级、异常 |
| `self_check.json` | `audit.py` | 契约/证据/数字/兜底/退出码的自检回执 |

## 1. `golden_standard.json`

**它不是组织方隐藏的期望读数。** 隐藏读数只在评测平台内部，作者阶段从未可见。
它是**自建基准**：把字段表的义务（`row_contract`）与对同一批材料的**独立词面重扫**（`independent_anchors`）写成逐字段条目。

```json
{"schema": "golden-standard/v1", "case_id": "...", "provenance": {"is_organizer_key": false},
 "rules": {...}, "row_contract": {"required_keys": [...], "obligations": [...]}, "counts": {...},
 "source_scope": {"materials": [...], "kinds_scanned": ["pdf","md"]},
 "fields": [{"field_id": "F1", "label": "IC50",
             "terms_searched": ["IC50","compound"],
             "expected_status": "reported",
             "expected": {"value": 12.4, "unit": "nM", "statistic": "95% CI 10.1-15.2 nM", "condition": "..."},
             "evidence": {"quote": "逐字原文", "locator": "material_id=M1; paragraph_id=M1-p0001",
                          "quote_level": "quote_strict", "anchor": {...}},
             "independent_anchors": [{"score": 2, "quote": "...", "locator": {...}}],
             "confidence": "high", "basis": "为什么这样判定", "verdict": "match"},
            {"field_id": "F3", "expected_status": "not_reported",
             "evidence": {"quote": null, "locator": null,
                          "search_ledger": {"terms": ["funding"], "materials_scanned": ["M1"], "hits": 0}}}]}
```

`expected_status` 取值与判据（与 `rules` 同步）：

| 值 | 判据 | 强度 |
|---|---|---|
| `reported` | 交付 quote 在语料中逐字命中（strict/normalized）**且**值出现在一条独立锚点句里 | 高 |
| `not_reported` | 该字段检索词在全部可读段落/表行/图注中 0 命中（纯词面证据） | 中；同义改写可能漏检 |
| `source_conflict` | 交付的冲突双方 quote 都在语料中命中 | 高 |
| `extraction_failed` | 材料中不存在可读锚点，失败与材料状态一致 | 中 |
| `undetermined` | 有锚点但无法确认唯一值 → 必须人工读那段原文 | — |

## 2. `diff_report.md`

表头固定：`field_id | label | golden expected_status | actual status | verdict | basis`，下面每个字段一段明细
（实际值+单位+条件、golden 证据、实际 quote 与 locator、判定依据），末尾给汇总、剩余缺口、复跑命令。

| verdict | 含义 | 处置 |
|---|---|---|
| `match` | 交付满足 golden 条目 | 无 |
| `deviation` | 状态/值/quote 与 golden 不符 | 返工该字段 |
| `gap` | 请求的 `field_id` 没有交付行 | 补抽 |
| `needs_review` | 自动判定settle 不了 | 人工读一段锚点原文；**不是失败** |

达标率 = `match / 字段数`；`needs_review` 不计为失败，也不粉饰成 match。

## 3. `version_history.md`

包内 `references/version_history.md` 是权威版本（v1 文件清单与字节、v2 八项变更表、回退方式），
运行时应复制到 `/app/output/` 并追加"本次运行"段（status、四状态计数、golden/diff 计数）。
一键回退：`build --no-audit`；彻底回退见该文件末节。

## 4. `run.log`

事件源是 `/app/work/run_events.jsonl`（每条一行 JSON：`at`/`step`/`exit_code`/`duration_ms`/`argv`），
每次命令结束时由 `main.py` 重新渲染成 `run.log`，所以**当前命令的退出码也在里面**。
表头给出首个/末个事件、步骤数、总耗时；正文分四节：步骤表、降级、异常、产物文件（含字节数）。

## 5. `self_check.json`

```json
{"schema": "self-check/v1", "summary": {"checks": 17, "passed": 17, "failed": 0, "pass_rate_pct": 100.0},
 "checks": [{"id": "C07_evidence_coverage", "ok": true, "detail": "2/2 = 100.0%"}],
 "exit_codes": {"init": 0, "check": 0, "help": 0},
 "evidence_coverage": {...}, "fallback_tests": [...], "files": [...]}
```

| id | 证明什么 |
|---|---|
| `C01_contract_keys` | 输入 `output_contract` 的每个键都出现在 `result.json`（缺哪个列哪个） |
| `C02_core_fields` | `case_id/status/sources/uncertainty/pending_human/errors/degradations/changes/runtime` 齐全 |
| `C03_new_assets_fields` | `result.json` 带 `golden_standard/diff_report/version_history/self_check` |
| `C04_row_keys` | 每个结果行 11 个文档化键齐全 |
| `C05_status_enum` | 状态合法且四状态之和 = `target_fields` |
| `C06_reported_has_value_quote` | `reported` 必有值 + quote |
| `C07_evidence_coverage` | `reported` 行 quote 逐字命中率（≥90% 通过） |
| `C08_nonreported_basis` | 非 `reported` 行都有依据文本 |
| `C09_number_quote_consistency` | 值里的数字在 quote 中逐字出现（不改写/不换算） |
| `C10_locator_granularity` | `reported` 定位到段落/表指针；PDF 行带 `page` |
| `C11/C12` | golden 条目状态合法、有 basis、quote 可核验 |
| `C13_diff_parity` | diff 覆盖每个 golden 字段与每个交付字段 |
| `C14/C15` | **真实跑过**空输入、坏 JSON：仍写合法 `result.json`、退出码 0（`fallback_tests` 有实测记录） |
| `C16_exit_codes_zero` | 已记录步骤的退出码全为 0（`--help` 是现跑的探针） |
| `C17_package_budget` | 包内文件数/字节在 10 文件 / 120000 B 内 |

## 复跑与迁移

```bash
python3 -B scripts/main.py build --input /input --work /app/work --output /app/output   # 全流程 + 5 资产
python3 -B scripts/main.py audit --work /app/work --output /app/output                  # 只重算 5 资产
python3 -B scripts/main.py build ... --no-audit                                          # 回到 v1 产物
```

换论文：只放新材料到 `/input`；换字段表：只换 `target-fields.json`——golden/diff 会自动按新字段表重建，
无硬编码字段名、无预置答案。

## 限制（写在这里以免被当成保证）

1. **自建基准不是标准答案**：`not_reported` 的独立性只到词面，同义表述会漏检，故 confidence 封顶 `medium`。
2. **扫描件无文本层**：无 OCR，golden 只能记 `extraction_failed` + 人工接管，不猜内容。
3. **自检开销**：`build` 会真跑两次空/坏输入子流程（约 5–6 s），并有 `SKILL_SELFTEST=1` 递归保护；
   900 s 预算下足够，但不必每字段重跑。
4. **`self_check.json` 的 `files` 不含 `result.json`**（它在自检之后定稿）；以 `run.log` 的产物表为最终字节清单。
