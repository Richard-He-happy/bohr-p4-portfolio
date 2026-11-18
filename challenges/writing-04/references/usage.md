# citation-manager 使用与方法说明

## 1. 依赖与环境

| 项 | 要求 |
|-|-|
| Python | ≥ 3.9（开发验证 3.12） |
| 第三方包 | 无。仅 `re`, `json`, `pathlib`, `difflib`, `unicodedata`, `zipfile`, `hashlib`, `csv`（标准库） |
| 网络 | 不需要，且不会发起请求 |
| 安装 | 无需安装：把 `submission/` 放到 `/skills/weekly-skill/`（或任意目录）即可 |
| 资源定位 | 脚本以 `Path(__file__).resolve().parent` 定位自身，`main.py` 用 `sys.path` 引入同目录 `reftool.py`；与 CWD 无关 |

## 2. 一次完整调用（5 步）

```bash
# 1) 确认输入：case.json + 稿件 + 文献库（任意文件名）
ls /input

# 2) 干跑帮助，确认参数
python3 -B scripts/main.py --help

# 3) 正式运行（默认 GB/T 7714—2015）
python3 -B scripts/main.py --input /input --output /app/output

# 4) 检查结构化结果
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(d['status'],d['counts'])"

# 5) 人工过一遍台账
python3 -c "import json;d=json.load(open('/app/output/result.json'));[print(x) for x in d['pending_human']]"
```

需要 APA 7 时加 `--style apa`；只想要"该在哪里补引"而不改稿时加 `--no-insert`。

## 3. 输入约定

| 输入 | 必需 | 说明 |
|-|-|-|
| `case.json` | 建议 | `case_id`、`output_contract` 原样回传；`organizer_workorder`/`organizer_edit_workorder` 逐项回执 |
| 稿件 | 是 | `.md`/`.txt` 最佳；`.docx` 只抽正文文本 |
| 文献库 | 是 | `.bib` / `.ris` / CSL-JSON `.json` / GB/T 7714 文本列表；可多个文件混用 |
| `task.md` | 否 | 仅作为上下文，事实以实际稿件与文献库为准 |

支持的引用标记：`[1]`、`[1,3]`、`[3-5]`、`^[1]^`、`\cite{key}`、`[@key]`。文末标题识别：`参考文献`/`引用文献`/`References`/`Bibliography`/`注释与参考文献`。

## 4. 输出字段说明

| 字段 | 含义 | 用法 |
|-|-|-|
| `case_id` | 原样回传 | 与平台案例对齐 |
| `status` | `ok`/`partial`/`insufficient_evidence`/`input_error` | 决定是否需要人工介入 |
| `manuscript` | 源稿件路径、类型、标题数、段落数、字符数 | 了解成品规模 |
| `citation_map[]` | 每条正文引用：`number`/`key`/`locator`/`claim_quote`/`overlap`/`verdict`/`evidence_terms` | 论断级核对 |
| `evidence_map[]` | 同上投影：`claim`/`key`/`locator`/`quote` | 引用→条目→原文的追溯链 |
| `preserved_facts[]` | 源稿数字/单位 token 与 `kept` | 事实未被改动 |
| `change_log[]` | 插入引用、编号重排、条目渲染的 `original_quote`→`revised_quote`+`reason`+`locator` | 逐条复核改动 |
| `dedup_decisions[]` / `ambiguous_pairs[]` | 合并/保留分开的判据与分值 | 解释"为什么合并" |
| `merge_groups[]` | 每组的成员、合并后补齐的字段（`fills`） | 审计字段来源 |
| `verification` | 10 项确定性检查 + `passed/total/pass_rate` | 质量闸门 |
| `counts` | 章节、引用点、库记录、合并组、插入、未解析、未引用、渲染条目、自动动作、待确认、错误 | 覆盖率证据 |
| `pending_human[]` | 需人工确认项 | 交付前逐条处理 |
| `workorder_receipt[]` | 组织方工作单逐项回执（`done`/`unmet`+计数证据） | 对齐 `organizer_workorder` |
| `runtime` | 秒数、Python 版本、模型请求数（恒 0） | 运行可核验 |

## 5. 最小调用示例（**示例，非正式案例结果**）

输入目录：

```text
/input/case.json          case_id=demo-A-001，output_contract 含 manuscript_path/reference_list_path/citation_map…
/input/manuscript.md      4 条 [n] 引用标记 + 文末 4 条 GB/T 文献表
/input/refs.bib           4 条 BibTeX（含 1 条与 RIS 重复的 DOI 条目）
/input/refs_dup.ris       3 条 RIS（1 条与 bib 重复）
```

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

示意输出（示例，非正式案例结果）：`status=partial`；库 7 条→去重 6 条（1 组以 `doi_exact` 合并）；引用点 7 个；补引 1 处（讨论段"本研究结果与已有报道一致…"→`[1]`，score 0.20，命中 根系/胁迫/镉胁）；未解析标记 0；校验 9/9；`pending_human` 8 项（6 条弱匹配 + 2 条缺字段）。

## 6. 适用场景与限制

**适用**：中文/英文期刊稿件引用整理；多来源文献库合并去重；由任意引用格式统一到 GB/T 7714 或 APA 7；投稿前一致性自查；审稿意见要求"补齐引用与编号"。

**限制（必须知道）**：

1. 只做**顺序编码制**与 **APA 7 作者—年份制**；Vancouver、Nature、ACS 等需扩展 `reftool.render()`。
2. 论断匹配是词项覆盖度启发式，**不是语义理解**：同义改写、跨语言（中文论断引英文文献）时覆盖率会偏低，表现为 `weak_match` 进入 `pending_human`——这是刻意保守，不是已完成判定。
3. 不解析 `.xlsx`/`.csv`/`.enw` 文献库；不解析 PDF 正文（只登记文件）。
4. `.docx` 稿件只抽文本：上标、脚注、域代码、交叉引用会丢失。
5. 中英文姓名转写不做拼音转换：中文条目在 APA 输出中保留原字符。
6. 不校验文献真实性（无网络）：`doi_syntax` 只查格式，真实存在性需人工或联网工具兜底。

## 7. 失败处理与自查

| 症状 | 定位 | 处理 |
|-|-|-|
| `status=input_error` | `errors[0].stage=discover` | 确认 `/input` 内有稿件或文献库 |
| `status=insufficient_evidence` | `counts.library_records_raw=0` | 检查库格式是否在支持列表；`degradations` 会写明 `unsupported_or_unrecognized_format` |
| 编号有跳号 | `verification.checks[numbering_continuous].detail` | 多为原文文献表与正文编号不一致，看 `unresolved_markers` |
| 大量 `weak_match` | `citation_map[].overlap` | 论断与文献主题确实不匹配，或文献题名过短；可人工补引或调整阈值（`main.py` 中 `sc >= 0.2`） |
| 条目出现 `[待补]` | `pending_human[].item=missing_fields` | 库里就没有该字段，补齐原始库文件后重跑 |

自查命令：

```bash
python3 -c "import json;d=json.load(open('/app/output/result.json'));print(d['verification']['pass_rate']);print([c['id'] for c in d['verification']['checks'] if not c['pass']])"
```

## 8. 维护与回归

- 改格式规则：只动 `references/styles.md` 与 `reftool.render()`，不碰流程。
- 改去重判据：只动 `reftool.dec()` 与 `references/rules.md`，阈值改动须同步更新 `SKILL.md` §7。
- 回归清单：① `--help` 退出码 0；② 最小案例六类动作计数均 >0；③ 空输入与坏 JSON 仍产出合法 `result.json` 且退出码 0；④ 两脚本均 ≤20 KiB。
- 版本记录：1.0.0 首版（GB/T 7714 + APA 7；bib/ris/json/gbt 解析；去重判据链；workorder 回执）。
