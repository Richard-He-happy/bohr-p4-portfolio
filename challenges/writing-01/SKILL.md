---
name: writing-01-academic-writing
description: 学术论文写作最小稳健流程。读取 /input/case.json 与科研材料，产出可编辑章节稿 manuscript.md、金标准 golden_standard.json、差异报告 diff_report.md、版本记录 version_history.md、运行日志 run.log、自检 self_check.json 与契约齐全的 result.json；支持 init/show/check/build/audit，无 Agent 草稿时也能按材料定位语句组装完整章节稿。
version: 5.0.0
---

# writing-01 学术论文写作（v5 最小稳健版 + 可核验资产）

## 1. 用途与边界
材料 → 可编辑章节稿（摘要/引言/方法/结果/讨论/结论/参考文献/数据可得性声明 + 附录），
每条论断附逐字引用与 `文件:行号` 定位；并给出「期望交付」的金标准与逐项差异报告。
不生成材料外数值/文献/图注；不解析 PDF 二进制；不调外部程序、不联网。

## 2. 运行契约
- 输入 `/input/case.json` + 材料；工作 `/app/work`；产物 `/app/output`。
- 子命令 `init | show | check | build | audit`，退出码恒 0；`build` 先落盘 partial `result.json` 再覆盖终稿。
- 可选参数 `--no-audit`（跳过 4 个审计资产，稿件照旧产出）、`--draft`、`--input/--output/--work`；原有调用方式不变。
- 加固：单文件读 2MB、每文件 5s 超时、≤200 文件 / 累计 20MB、45s 软截止；异常只降级不中断。
- 仅标准库、不依赖 CWD（`Path(__file__).resolve().parent` 定位 `audit.py`）。

## 3. 输入发现
读 `/input/case.json`（`utf-8-sig`；缺失则找 `case*.json`，仍无记 `case_json_missing` 并按材料继续），
语义取 `case_id`、`output_contract`、`task_instruction`、`organizer_workorder`、`organizer_edit_workorder`、`source.title`。
递归扫描全部材料，按扩展名+魔数识别：文本类直读；`.docx` 只读 `word/document.xml`；
`.pdf` 仅识别 `%PDF` 头 → `pdf_unparsed` + pending，改从同案例文本材料取证；图片/`.xlsx`/`.pptx`/`.bin` → `binary_skipped`。
参考文献条目（`[n]` 起始或含 DOI/`doi:`）整行保留、不拆句——拆句会拆断作者、卷期与 DOI，导致引用无法逐字核验。

## 4. 输出契约
`/app/output/` 下共 7 个产物：

| 文件 | 作用 |
|-|-|
| `manuscript.md` | 主产物：H2 分级章节稿，每条引用带 locator |
| `golden_standard.json` | 期望交付的金标准：章节六要素 + 每节锚句（locator + 逐字 quote）+ 事实/数字保全清单 + 引用条目 |
| `diff_report.md` | 实际稿件 vs 金标准逐项对照（达标/偏差/缺失 + 判定方法 + 复核步骤） |
| `version_history.md` | v0 骨架 → v1 成稿（改了什么/为什么/如何回退），含 sha256 |
| `run.log` | 步骤、耗时、逐文件扫描、降级、异常、收尾状态 |
| `self_check.json` | 契约字段、证据覆盖率、数字/引用一致性、空输入与坏 JSON 探测、退出码、文件预算 |
| `result.json` | 契约回填 + 主结果 + 4 个新字段 + 状态/证据/降级 |

`result.json`：原样回填 `output_contract` 全部字段（dict/list 均可，未知字段置 null），
固定写入 `case_id/deliverable/preserved_facts/evidence_map/change_log`，
新增 `golden_standard/diff_report/version_history/self_check/artifacts/exceptions`，
以及 `status`、`sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes`、`coverage`、`runtime`。

## 5. 核心流程
```bash
S=/skills/weekly-skill  # 本地为包根
python3 -B "$S/scripts/main.py" init       # 材料索引：id/类型/字节/可读性
python3 -B "$S/scripts/main.py" show       # 带 locator 的证据句
# （可选）写 /app/work/draft.json，schema 见 references/schema.md
python3 -B "$S/scripts/main.py" check      # 校验草稿：引用逐字命中？缺哪些章节？
python3 -B "$S/scripts/main.py" build      # 成稿 + 5 个资产 + result.json
python3 -B "$S/scripts/main.py" audit      # 只读复核：由 golden + manuscript 重算 diff_report
```
**没有草稿也必须跑 `build`**：按材料可定位语句组装完整章节稿，`status=partial`，`change_log` 记录来源。

## 6. 金标准与差异报告的生成规则（v5 新增）
- 金标准只从材料派生：每节锚句 = 该节已校验的逐字引用（含 `source_id`/`locator`），每节 ≤3 条；
  事实清单 = 含数字的原句，`must_keep` = 其中数值 token（DOI 段先剥离，DOI 由引用检查单独核）。
- 差异报告逐项判定：
  - `anchor_quote`：去空白子串命中 → 达标；trigram 覆盖 ≥0.60 → 偏差（疑改写/截断）；否则 缺失。
  - `section_content`：该节含逐字引用 → 达标；仅占位句/空节 → 缺失；只有成段文字无引用 → 偏差（防「只有标题的空节」假达标）。
  - `fact_number`：原句落地且数值齐全 → 达标；数值被改/缺失 → 偏差/缺失。
  - `citation`：整条或分片（≥18 字）全中 → 达标；部分命中 → 偏差；否则 缺失。
  - `declaration`：附录缺口行/待确认行、数据可得性声明是否存在。
- 任何未达标项写入 `pending_human`（`item/reason/action`），不改材料凑通过。

## 7. 草稿要点（可选增强）
`sections[].heading` + `paragraphs[].text` + `paragraphs[].quotes[]`（`quote`/`locator`/`source_id`）。
`quote` 须与材料逐字一致（忽略空白）；未命中者拒收、不计入 `evidence_map`、进 `pending_human`。
正文只改表达：数值、单位、样本量、`p` 值、术语、引用编号沿用原文；缺章节由 `build` 补占位，不编造。

## 8. 证据与定位
定位符 `文件名:L行号`（docx 为提取文本行；JSON 材料为展平行）。`evidence_map` 含
`claim_id/section/quote/source_id/locator/verified`；`preserved_facts` 收含数字原句；同句只归一个章节。

## 9. 冲突与人工确认
摘要/结果数值不一致、方法步骤可疑、文献信息不全、图注缺数值、材料未覆盖的章节：不改数字，
记入 `pending_human`（`item/reason/action`）与稿件附录，交作者确认；`diff_report` 第 3 节给处置建议。

## 10. 降级分支
| 情况 | 处置 | 记录 |
|-|-|-|
| PDF | 不解析，用文本材料 | `pdf_unparsed` + pending |
| 二进制/图片/xlsx/pptx | 跳过 | `binary_unparsed` / `binary_skipped` + pending |
| JSON 坏 | 按纯文本行 | `json_parse_failed` |
| 单文件 >2MB | 读前 2MB | `file_truncated` |
| 读超时/异常 | 跳过该文件 | `file_timeout` / `file_error` |
| 超限/输出不可写 | 截断扫描 / 回落 work | `file_capped` / `bytes_capped` / `output_dir_fallback` |
| `scripts/audit.py` 缺失或报错 | 主稿照常，缺的资产置 `unavailable` | `audit_module_missing` / `audit_failed` / `golden_failed` / `diff_failed` / `version_history_failed` / `selfcheck_failed` |

## 11. 预算与断点
正常 1–4s（含 2 次子进程探测），200 文件慢盘 <10s。`build` 首行即写 partial `result.json`；
审计资产按 golden → diff → version → self-check 顺序各自 try/except 独立落盘；
`result.json` 在自检前先落盘一次、自检后再覆盖。未捕获异常兜底写 `status=input_error` + 4 个 `unavailable` 字段，退出码仍为 0。

## 12. 自检清单
`python3 -B scripts/main.py --help` 退出码 0；`manuscript.md` 的 `grep -c '^## '` ≥ 5；
`result.json` 含 5 个固定键 + 4 个新字段且 `coverage` 有计数；7 个产物齐备；
`python3 -B scripts/main.py audit` 与运行期 `diff_report.md` 结论一致；
空输入 / 坏 JSON 各跑一次，均应退出码 0 且 `result.json` 合法（这两条已由 `self_check.json` 实跑记录）。

## 13. 最小调用示例（示例，非正式案例结果）
```bash
python3 -B scripts/main.py build --input /input --output /app/output --work /app/work
# built /app/output/manuscript.md | status=partial sections=8 evidence=11 h2=9 chars=1576
# 同目录生成 golden_standard.json / diff_report.md / version_history.md / run.log / self_check.json
```

## 14. 文件清单与版本
`SKILL.md`（本文件）、`scripts/main.py`（主流程）、`scripts/audit.py`（审计资产生成）、
`references/schema.md`（字段与定位规则）。v5.0.0；Python ≥3.8；无依赖；4 个文件 <80KB。

## 15. 维护说明
章节模板见 `scripts/main.py` 的 `SE`/`AL`；扫描上限见 `MF/MT/MB/FT/DL`；定位格式见 `sents()`；
金标准/差异判定阈值见 `scripts/audit.py` 的 `ANCHOR_CAP/FACT_CAP/NEAR`。
回归：跑第 12 节清单 + 空目录/坏 JSON/带假数字草稿三种坏输入，应退出码 0，
且 `self_check.json` 对假数字报 `untraceable`、对未命中引用报 `quotes_rejected`。
